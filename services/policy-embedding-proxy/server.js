'use strict';

const http = require('node:http');
const crypto = require('node:crypto');

const PORT = Number(process.env.PORT || 8080);
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const PROXY_TOKEN = process.env.WORKER_EMBEDDING_PROXY_TOKEN;
const MODEL = 'gemini-embedding-001';
const DIMENSIONS = 1536;
const MAX_QUERY_LENGTH = 2000;
const MAX_BODY_BYTES = 16 * 1024;

function sendJson(response, status, body) {
    response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(JSON.stringify(body));
}

function isAuthorized(request) {
    const value = request.headers.authorization || '';
    const prefix = 'Bearer ';
    if (!value.startsWith(prefix) || !PROXY_TOKEN) return false;
    const supplied = Buffer.from(value.slice(prefix.length));
    const expected = Buffer.from(PROXY_TOKEN);
    return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}

async function readJson(request) {
    let size = 0;
    const chunks = [];
    for await (const chunk of request) {
        size += chunk.length;
        if (size > MAX_BODY_BYTES) throw new Error('body_too_large');
        chunks.push(chunk);
    }
    try {
        return JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
        throw new Error('invalid_json');
    }
}

function normalizeEmbedding(values) {
    if (!Array.isArray(values) || values.length !== DIMENSIONS || !values.every(Number.isFinite)) {
        throw new Error('invalid_embedding');
    }
    const magnitude = Math.sqrt(values.reduce((sum, value) => sum + value * value, 0));
    if (!magnitude) throw new Error('invalid_embedding');
    return values.map((value) => value / magnitude);
}

async function embedQuery(query) {
    const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:embedContent`,
        {
            method: 'POST',
            headers: { 'x-goog-api-key': GEMINI_API_KEY, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: `models/${MODEL}`,
                content: { parts: [{ text: query }] },
                taskType: 'RETRIEVAL_QUERY',
                outputDimensionality: DIMENSIONS,
            }),
        },
    );
    if (!response.ok) throw new Error(`gemini_http_${response.status}`);
    const payload = await response.json();
    return normalizeEmbedding(payload?.embedding?.values);
}

const server = http.createServer(async (request, response) => {
    if (request.method === 'GET' && request.url === '/healthz') {
        response.writeHead(204, { 'Cache-Control': 'no-store' });
        return response.end();
    }
    if (request.method !== 'POST' || request.url !== '/embed') return sendJson(response, 404, { error: 'not_found' });
    if (!GEMINI_API_KEY || !PROXY_TOKEN) return sendJson(response, 503, { error: 'service_unavailable' });
    if (!isAuthorized(request)) return sendJson(response, 401, { error: 'unauthorized' });

    try {
        const body = await readJson(request);
        const query = typeof body?.query === 'string' ? body.query.trim().slice(0, MAX_QUERY_LENGTH) : '';
        if (!query) return sendJson(response, 400, { error: 'query_required' });
        const values = await embedQuery(query);
        return sendJson(response, 200, { values });
    } catch (error) {
        // 질의어·벡터·비밀값은 절대 로그에 남기지 않는다. 상태 코드만 남겨
        // 운영 장애 여부를 확인할 수 있게 한다.
        console.error(`embedding request failed: ${error.message}`);
        return sendJson(response, 503, { error: 'embedding_unavailable' });
    }
});

server.listen(PORT, () => console.log(`policy embedding proxy listening on ${PORT}`));
