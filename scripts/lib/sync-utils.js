'use strict';

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeUrl(value) {
  return String(value).replace(/([?&](?:api_key|key)=)[^&]+/gi, '$1[redacted]');
}

function retryAfterMs(response, attempt) {
  const retryAfter = response.headers.get('retry-after');
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds)) return Math.min(seconds * 1_000, 60_000);
    const dateMs = Date.parse(retryAfter) - Date.now();
    if (Number.isFinite(dateMs) && dateMs > 0) return Math.min(dateMs, 60_000);
  }
  return Math.min(1_000 * (2 ** attempt) + Math.floor(Math.random() * 250), 30_000);
}

async function fetchJson(url, options = {}, config = {}) {
  const maxRetries = config.maxRetries ?? 5;
  const label = config.label || safeUrl(url);
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      if (attempt === maxRetries) throw new Error(`${label}: ${error.message}`);
      await sleep(Math.min(1_000 * (2 ** attempt), 30_000));
      continue;
    }
    if (response.ok) {
      if (response.status === 204) return null;
      return (response.headers.get('content-type') || '').includes('json') ? response.json() : response.text();
    }
    const body = await response.text().catch(() => '');
    // A billing/quota response cannot recover through a retry. Fail it at once
    // so the caller can skip optional embeddings without wasting an Actions run.
    if (!RETRYABLE_STATUS.has(response.status) || attempt === maxRetries || config.nonRetryableErrorPattern?.test(body)) {
      throw new Error(`${label}: HTTP ${response.status}${body ? ` ${body.slice(0, 300)}` : ''}`);
    }
    await sleep(retryAfterMs(response, attempt));
  }
  throw new Error(`${label}: exhausted retries`);
}

function createRequestGate(minIntervalMs) {
  let nextAllowedAt = 0;
  let queue = Promise.resolve();
  return async (task) => {
    const scheduled = queue.then(async () => {
      const wait = Math.max(0, nextAllowedAt - Date.now());
      if (wait) await sleep(wait);
      nextAllowedAt = Date.now() + minIntervalMs;
      return task();
    });
    queue = scheduled.catch(() => undefined);
    return scheduled;
  };
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function parseDateOnly(value) {
  const match = value && String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : null;
}

function parseTimestamp(value, fallback = null) {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? fallback : date.toISOString();
}

function asArray(value) {
  return Array.isArray(value) ? value : value == null ? [] : [value];
}

function firstNonEmpty(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== '') ?? null;
}

function slug(value) {
  const output = String(value || '').trim().toLowerCase().replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return output || null;
}

function supabaseConfig() {
  return {
    url: requireEnv('SUPABASE_URL').replace(/\/$/, ''),
    key: requireEnv('SUPABASE_SERVICE_ROLE_KEY'),
  };
}

async function supabaseRequest(path, options = {}) {
  const config = supabaseConfig();
  const headers = {
    apikey: config.key,
    Authorization: `Bearer ${config.key}`,
    Accept: 'application/json',
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };
  return fetchJson(`${config.url}/rest/v1/${path.replace(/^\//, '')}`, { ...options, headers }, {
    label: `Supabase ${options.method || 'GET'} ${path}`,
  });
}

async function supabaseGet(table, query = {}) {
  return supabaseRequest(`${table}?${new URLSearchParams(query).toString()}`);
}

async function supabaseInsert(table, rows, prefer = 'return=minimal') {
  const payload = Array.isArray(rows) ? rows : [rows];
  if (!payload.length) return [];
  return supabaseRequest(table, {
    method: 'POST', headers: { Prefer: prefer }, body: JSON.stringify(payload),
  });
}

async function supabaseUpsert(table, rows, onConflict, prefer = 'resolution=merge-duplicates,return=minimal') {
  const payload = Array.isArray(rows) ? rows : [rows];
  if (!payload.length) return [];
  return supabaseRequest(`${table}?on_conflict=${encodeURIComponent(onConflict)}`, {
    method: 'POST', headers: { Prefer: prefer }, body: JSON.stringify(payload),
  });
}

async function supabaseInsertIgnore(table, row, onConflict) {
  return supabaseRequest(`${table}?on_conflict=${encodeURIComponent(onConflict)}`, {
    method: 'POST', headers: { Prefer: 'resolution=ignore-duplicates,return=minimal' }, body: JSON.stringify([row]),
  });
}

async function supabasePatch(table, filter, row) {
  return supabaseRequest(`${table}?${filter}`, {
    method: 'PATCH', headers: { Prefer: 'return=minimal' }, body: JSON.stringify(row),
  });
}

async function supabaseRpc(name, args = {}) {
  return supabaseRequest(`rpc/${name}`, {
    method: 'POST', headers: { Prefer: 'return=minimal' }, body: JSON.stringify(args),
  });
}

const GEMINI_EMBEDDING_DIMENSIONS = 1536;
const GEMINI_EMBEDDING_INPUT_MAX_CHARS = 6000;

function geminiModelName(model = process.env.GEMINI_EMBEDDING_MODEL || 'gemini-embedding-001') {
  return String(model).replace(/^models\//, '');
}

function embeddingInput(text) {
  // gemini-embedding-001 accepts 2,048 input tokens. The input here is only
  // title + official summary/abstract; this cap prevents an unusually long
  // summary from failing an otherwise healthy source sync.
  return String(text || '').trim().slice(0, GEMINI_EMBEDDING_INPUT_MAX_CHARS);
}

function normalizeVector(values) {
  const vector = Array.isArray(values) ? values.map(Number) : [];
  if (vector.length !== GEMINI_EMBEDDING_DIMENSIONS || vector.some((value) => !Number.isFinite(value))) {
    throw new Error(`Gemini embeddings: expected ${GEMINI_EMBEDDING_DIMENSIONS} finite dimensions, received ${vector.length}`);
  }
  // Gemini Embedding 001 recommends normalization for reduced dimensions.
  const magnitude = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  if (!Number.isFinite(magnitude) || magnitude === 0) throw new Error('Gemini embeddings: zero-length vector');
  return vector.map((value) => value / magnitude);
}

function isOptionalEmbeddingError(error) {
  return /Missing required environment variable: GEMINI_API_KEY|API_KEY_INVALID|API key not valid|PERMISSION_DENIED|SERVICE_DISABLED|RESOURCE_EXHAUSTED|quota|billing/i.test(error?.message || '');
}

async function geminiEmbeddings(inputs, apiKey, model = geminiModelName()) {
  if (!inputs.length) return [];
  const modelName = geminiModelName(model);
  const modelResource = `models/${modelName}`;
  const body = await fetchJson(
    `https://generativelanguage.googleapis.com/v1beta/${modelResource}:batchEmbedContents`,
    {
      method: 'POST',
      headers: { 'x-goog-api-key': apiKey, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requests: inputs.map((input) => ({
          model: modelResource,
          content: { parts: [{ text: embeddingInput(input) }] },
          embedContentConfig: {
            taskType: 'RETRIEVAL_DOCUMENT',
            outputDimensionality: GEMINI_EMBEDDING_DIMENSIONS,
          },
        })),
      }),
    },
    {
      label: 'Gemini embeddings',
      nonRetryableErrorPattern: /API_KEY_INVALID|API key not valid|PERMISSION_DENIED|SERVICE_DISABLED|RESOURCE_EXHAUSTED|quota|billing/i,
    },
  );
  const embeddings = Array.isArray(body?.embeddings) ? body.embeddings : [];
  if (embeddings.length !== inputs.length) {
    throw new Error(`Gemini embeddings: expected ${inputs.length} vectors, received ${embeddings.length}`);
  }
  return embeddings.map((item) => normalizeVector(item?.values));
}

async function mapWithConcurrency(items, concurrency, worker) {
  const output = new Array(items.length);
  let cursor = 0;
  async function run() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      output[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), items.length) }, run));
  return output;
}

async function startSyncRun(syncResource, metadata = {}) {
  const rows = await supabaseInsert('data_sync_runs', { sync_resource: syncResource, metadata }, 'return=representation');
  return rows?.[0]?.sync_run_id;
}

async function finishSyncRun(syncRunId, fields) {
  if (syncRunId) await supabasePatch('data_sync_runs', `sync_run_id=eq.${encodeURIComponent(syncRunId)}`, {
    completed_at: new Date().toISOString(), ...fields,
  });
}

async function updateSyncState(syncResource, cursor) {
  await supabaseUpsert('data_sync_state', [{
    sync_resource: syncResource,
    cursor,
    last_attempt_at: new Date().toISOString(),
    last_successful_at: new Date().toISOString(),
  }], 'sync_resource');
}

async function checkpointSyncState(syncResource, cursor) {
  const existing = await supabaseGet('data_sync_state', {
    select: 'last_successful_at', sync_resource: `eq.${syncResource}`, limit: '1',
  });
  await supabaseUpsert('data_sync_state', [{
    sync_resource: syncResource,
    cursor,
    last_attempt_at: new Date().toISOString(),
    last_successful_at: existing?.[0]?.last_successful_at || null,
  }], 'sync_resource');
}

// URLSearchParams in supabaseGet performs URL encoding. Encoding here as well
// turns ':' into '%253A', so an existing queue row cannot be found and a
// duplicate insert follows. Keep the PostgREST operator/value unescaped here.
function queueKeyFilter(value) { return `eq.${value}`; }

async function enqueuePolicyItem(syncResource, sourceKey, payload, options = {}) {
  const existing = (await supabaseGet('policy_ingestion_queue', {
    select: 'queue_id,status,source_updated_at',
    sync_resource: queueKeyFilter(syncResource), source_key: queueKeyFilter(sourceKey), limit: '1',
  }))?.[0];
  const incoming = options.sourceUpdatedAt ? new Date(options.sourceUpdatedAt).valueOf() : NaN;
  const prior = existing?.source_updated_at ? new Date(existing.source_updated_at).valueOf() : NaN;
  const shouldRefresh = existing && Number.isFinite(incoming) && (!Number.isFinite(prior) || incoming > prior);
  if (!existing) {
    await supabaseInsert('policy_ingestion_queue', {
      sync_resource: syncResource, source_key: sourceKey, payload, priority: options.priority || 0,
      source_updated_at: options.sourceUpdatedAt || null,
    });
    return 'inserted';
  }
  if (shouldRefresh && existing.status !== 'processing') {
    await supabasePatch('policy_ingestion_queue', `queue_id=eq.${existing.queue_id}`, {
      payload, priority: options.priority || 0, source_updated_at: options.sourceUpdatedAt,
      status: 'pending', available_at: new Date().toISOString(), completed_at: null, last_error: null,
    });
    return 'refreshed';
  }
  return 'unchanged';
}

async function takePolicyQueue(syncResource, limit) {
  return supabaseGet('policy_ingestion_queue', {
    select: 'queue_id,source_key,payload,attempts', sync_resource: queueKeyFilter(syncResource), status: 'eq.pending',
    available_at: `lte.${new Date().toISOString()}`, order: 'priority.desc,created_at.asc', limit: String(limit),
  });
}

async function markPolicyQueue(queueId, fields) {
  await supabasePatch('policy_ingestion_queue', `queue_id=eq.${queueId}`, fields);
}

module.exports = {
  asArray, checkpointSyncState, createRequestGate, fetchJson, finishSyncRun, firstNonEmpty, mapWithConcurrency,
  geminiEmbeddings, geminiModelName, isOptionalEmbeddingError, parseDateOnly, parseTimestamp, requireEnv, sleep, slug, startSyncRun,
  supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch, supabaseRpc,
  supabaseUpsert, updateSyncState, enqueuePolicyItem, takePolicyQueue, markPolicyQueue,
};
