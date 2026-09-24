// UN Comtrade period handling: the Worker picks the newest fully cached year
// (no hardcoded period), the cron promotes a year only when it is ready, and
// the browser aggregation stays correct for multi-month windows.
//
//   node --test tests/comtrade/period.test.mjs
//
// No network: KV and the Comtrade upstream are mocked; the real _worker.js
// and data.js are loaded as they are.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const floor = new Date().getUTCFullYear() - 3;

async function loadWorker() {
    // _worker.js imports a UI module the Comtrade path never touches; stub it
    // so the Worker loads under plain Node.
    const src = fs.readFileSync(path.join(repo, '_worker.js'), 'utf8')
        .replace("import PolicyEvidence from './New for anti/policy-evidence.js';", 'const PolicyEvidence = {};');
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'comtrade-')), 'worker.mjs');
    fs.writeFileSync(file, src);
    return (await import(pathToFileURL(file).href)).default;
}

function makeKV() {
    const store = new Map();
    return {
        store,
        async get(k, opts) {
            const e = store.get(k);
            if (!e) return null;
            const type = typeof opts === 'string' ? opts : opts?.type;
            return type === 'json' ? JSON.parse(e.value) : e.value;
        },
        async put(k, value, opts = {}) { store.set(k, { value, metadata: opts.metadata ?? null }); },
        async list({ prefix }) {
            const keys = [...store.entries()].filter(([k]) => k.startsWith(prefix))
                .map(([name, e]) => ({ name, metadata: e.metadata }));
            return { keys, list_complete: true };
        },
    };
}

// Upstream stand-in: for each year, the first N of every reporter chunk file
// one export row. `filers[year]` sets N per 16-reporter chunk.
function makeUpstream(filers) {
    const calls = [];
    const fetch = async (url) => {
        calls.push(url);
        const u = new URL(url);
        const rows = [];
        for (const p of u.searchParams.get('period').split(',')) {
            const n = filers[p.slice(0, 4)] ?? 0;
            u.searchParams.get('reporterCode').split(',').forEach((r, i) => {
                if (i < n) rows.push({ reporterCode: Number(r), partnerCode: 156, flowCode: 'X', primaryValue: 1e6, netWgt: 1, period: p });
            });
        }
        return new Response(JSON.stringify({ data: rows }), { status: 200 });
    };
    return { fetch, calls };
}

async function setup(filers = { [floor]: 12, [floor + 1]: 12, [floor + 2]: 8 }) {
    const worker = await loadWorker();
    const upstream = makeUpstream(filers);
    globalThis.fetch = upstream.fetch;
    const env = { COMTRADE_API_KEY: 'k', API_CACHE: makeKV() };
    const call = (qs) => worker.fetch(new Request(`https://x/api/comtrade?${qs}`), env, {});
    const cron = async () => {
        const waits = [];
        await worker.scheduled({}, env, { waitUntil: (p) => waits.push(p) });
        await Promise.all(waits);
    };
    const published = () => {
        const e = env.API_CACHE.store.get('comtrade:period:A');
        return e ? JSON.parse(e.value) : null;
    };
    return { env, call, cron, published, upstream, filers };
}

test('annual default is chosen by the Worker and reported back', async () => {
    const { call } = await setup();
    for (const qs of ['hs=7502', 'hs=7502&period=latest']) {
        const r = await call(qs);
        assert.equal(r.status, 200);
        assert.equal(r.headers.get('X-Comtrade-Period'), String(floor));
        const body = await r.json();
        assert.equal(body.period, String(floor));
        assert.equal(body.freq, 'A');
    }
    const r = await call('hs=7502&period=2024');
    assert.equal(r.headers.get('X-Comtrade-Period'), '2024');
});

test('codes and periods are validated before they reach the upstream URL', async () => {
    const { call, upstream } = await setup();
    for (const qs of [
        'hs=7502&freq=M',               // monthly has no default month
        'hs=7502&freq=M&period=2024',   // annual shape on a monthly request
        'hs=7502&period=202403',        // monthly shape on an annual request
        'hs=7502%26flowCode%3DX',       // parameter smuggling via hs
        'hs=7502&reporters=156;1',
    ]) {
        assert.equal((await call(qs)).status, 400, qs);
    }
    assert.equal(upstream.calls.length, 0);

    const r = await call('hs=7502&freq=M&period=202401,202402');
    assert.equal(r.status, 200);
    assert.equal(r.headers.get('X-Comtrade-Freq'), 'M');
});

test('cron promotes the next year only once it is cached and covered', async () => {
    const { call, cron, published, env, filers, upstream } = await setup();
    const log = console.log;
    console.log = () => {};
    try {
        // A complete (two-years-back) year is promoted as soon as all of it is cached.
        for (let i = 0; i < 20 && !published(); i++) await cron();
        assert.equal(published().period, String(floor + 1));
        assert.equal(published().coverage, null);

        // Visitors land on the promoted year, already warm.
        const r = await call('hs=7502');
        assert.equal(r.headers.get('X-Comtrade-Period'), String(floor + 1));
        assert.equal(r.headers.get('X-Cache'), 'HIT');

        // The year just ended, at 2/3 of last year's reporters: held back.
        for (let i = 0; i < 20; i++) await cron();
        assert.equal(published().period, String(floor + 1));

        // Reporters catch up; once those entries refresh, it is promoted.
        filers[floor + 2] = 12;
        for (const k of [...env.API_CACHE.store.keys()]) {
            if (k.includes(`:${floor + 2}:`)) env.API_CACHE.store.delete(k);
        }
        for (let i = 0; i < 20 && published().period !== String(floor + 2); i++) await cron();
        assert.equal(published().period, String(floor + 2));
        assert.equal(published().coverage, 1);

        // Nothing newer can exist yet, and everything is warm: no upstream calls.
        upstream.calls.length = 0;
        await cron();
        assert.equal(upstream.calls.length, 0);
    } finally {
        console.log = log;
    }
});

test('fetchComtradeArcs: mirror max within a period, summed across periods', async () => {
    let lastUrl = null;
    let payload = null;
    const fetchStub = async (url) => {
        if (!String(url).startsWith('/api/comtrade')) return new Response('{}', { status: 404 });
        lastUrl = url;
        return new Response(JSON.stringify(payload.body), { status: 200, headers: payload.headers });
    };
    const document = new Proxy({}, { get: () => () => null });
    const win = { fetch: fetchStub, document, addEventListener() {} };
    win.window = win;
    const ctx = vm.createContext({
        ...win, console: { log() {}, warn() {}, error() {} },
        URLSearchParams, Response, setTimeout, clearTimeout,
    });
    vm.runInContext(fs.readFileSync(path.join(repo, 'New for anti/data.js'), 'utf8'), ctx);
    const fetchArcs = ctx.window.fetchComtradeArcs;

    // Annual: exporter report and importer mirror of one route -> the larger.
    // 76 = Brazil, 156 = China.
    payload = {
        headers: { 'X-Comtrade-Period': '2025' },
        body: { data: [
            { reporterCode: 76, partnerCode: 156, flowCode: 'X', primaryValue: 40e9, netWgt: 90e9, period: '2025' },
            { reporterCode: 156, partnerCode: 76, flowCode: 'M', primaryValue: 42e9, netWgt: 95e9, period: '2025' },
        ] },
    };
    let arcs = await fetchArcs('soybeans');
    assert.equal(lastUrl, '/api/comtrade?hs=1201');
    assert.equal(arcs.length, 1);
    assert.equal(arcs[0].volume, 42000);
    assert.equal(arcs[0].netWeightMt, 95);
    assert.equal(arcs[0].period, '2025');
    assert.equal(arcs[0].freq, 'A');

    // Monthly window: the larger mirror per month, then months summed.
    payload = {
        headers: { 'X-Comtrade-Period': '202604,202605' },
        body: { data: [
            { reporterCode: 76, partnerCode: 156, flowCode: 'X', primaryValue: 5e9, netWgt: 10e9, period: '202604' },
            { reporterCode: 156, partnerCode: 76, flowCode: 'M', primaryValue: 6e9, netWgt: 11e9, period: '202604' },
            { reporterCode: 76, partnerCode: 156, flowCode: 'X', primaryValue: 7e9, netWgt: 12e9, period: '202605' },
        ] },
    };
    arcs = await fetchArcs('soybeans', { freq: 'M', period: '202604,202605' });
    assert.equal(lastUrl, '/api/comtrade?hs=1201&freq=M&period=202604%2C202605');
    assert.equal(arcs[0].volume, 13000);
    assert.equal(arcs[0].netWeightMt, 23);
    assert.equal(arcs[0].freq, 'M');
});

test('status endpoint reports the published year and next-year progress', async () => {
    const { env, cron } = await setup();
    const worker = await loadWorker();
    const status = async () => (await worker.fetch(new Request('https://x/api/comtrade/status'), env, {})).json();
    let st = await status();
    assert.equal(st.published, String(floor));
    assert.equal(st.next, String(floor + 1));
    assert.equal(st.cached[floor + 1], 0);
    const log = console.log;
    console.log = () => {};
    try { await cron(); } finally { console.log = log; }
    st = await status();
    assert.ok(st.cached[floor] + st.cached[floor + 1] > 0);
});
