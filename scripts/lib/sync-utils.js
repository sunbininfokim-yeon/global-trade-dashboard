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
    if (!RETRYABLE_STATUS.has(response.status) || attempt === maxRetries) {
      const body = await response.text().catch(() => '');
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

async function openAiEmbeddings(inputs, apiKey, model = process.env.OPENAI_EMBEDDING_MODEL || 'text-embedding-3-small') {
  if (!inputs.length) return [];
  const body = await fetchJson('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, input: inputs }),
  }, { label: 'OpenAI embeddings' });
  return body.data.sort((a, b) => a.index - b.index).map((item) => item.embedding);
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

function queueKeyFilter(value) { return `eq.${encodeURIComponent(value)}`; }

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
  openAiEmbeddings, parseDateOnly, parseTimestamp, requireEnv, sleep, slug, startSyncRun,
  supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch, supabaseRpc,
  supabaseUpsert, updateSyncState, enqueuePolicyItem, takePolicyQueue, markPolicyQueue,
};
