'use strict';
// Independent, leased search-index jobs. Source collectors remain untouched.
const fs = require('node:fs'), path = require('node:path');
const { sourceLoader, SOURCES } = require('./lib/policy-search-source');
const { MODEL } = require('./lib/policy-search-document');
const { acquireLock, releaseLock } = require('./lib/policy-search-lock');
const { supabaseGet, supabaseRpc, geminiEmbeddings, isOptionalEmbeddingError, requireEnv, sleep } = require('./lib/sync-utils');

function failureReason(error) {
  // Only static classifications are persisted. Provider messages may include
  // credentials, request URLs or private details and must stay out of logs.
  const status = Number(error.status || String(error.message || '').match(/\bHTTP (\d{3})\b/)?.[1]);
  if (status >= 100 && status <= 599) return `http_${status}`;
  const message = String(error.message || '');
  if (/requires .*official.*source URL/.test(message)) return 'missing_official_source';
  if (message === 'Source document no longer exists') return 'source_deleted';
  if (message === 'Unsupported official source URL') return 'unsupported_source_url';
  if (message === 'Official source exceeds 5MB text limit') return 'official_text_too_large';
  if (message.startsWith('Missing required environment variable:')) return 'missing_environment';
  if (isOptionalEmbeddingError(error)) return 'embedding_provider_unavailable';
  if (['TimeoutError', 'AbortError'].includes(error.name)) return 'request_timeout';
  return 'unexpected_error';
}

async function processJob(job, loader, embed = true, {
  get = supabaseGet,
  rpc = supabaseRpc,
  embedTexts = (inputs) => geminiEmbeddings(inputs, requireEnv('GEMINI_API_KEY'), MODEL),
} = {}) {
  const document = await loader.document(job.source_type, job.source_id);
  const existing = await get('policy_search_passages', {
    select: 'passage_index,input_hash,embedding_model',
    document_id: `eq.${job.document_id}`,
    embedding: 'not.is.null',
  });
  const existingByIndex = new Map(existing.map(passage => [passage.passage_index, passage]));
  const dirty = document.passages.filter(passage => {
    const stored = existingByIndex.get(passage.passage_index);
    return stored?.input_hash !== passage.input_hash || stored?.embedding_model !== MODEL;
  });
  const pendingEmbeddings = !embed && dirty.length > 0;
  const result = {
    embedded: 0,
    text_status: document.text_status,
    coverage: document.embedding_coverage,
    pending_embeddings: pendingEmbeddings,
  };

  // 텍스트만 갱신하는 실행에서도 이미 검색되는 문서는 벡터와 함께 교체할 때까지 보존한다.
  if (pendingEmbeddings && existing.length > 0) return { ...result, preserved_existing: true };

  // 외부 호출이 실패하면 저장 RPC를 호출하지 않는다. 새 문단과 벡터는 한 번에 저장한다.
  if (embed && dirty.length > 0) {
    const vectors = await embedTexts(dirty.map(passage => passage.input_text));
    dirty.forEach((passage, index) => {
      passage.embedding = vectors[index];
      passage.embedding_model = MODEL;
    });
  }
  const saved = await rpc('save_policy_search_document', {
    p_document: document,
    p_passages: document.passages,
    p_token: job.claim_token,
  }, 'return=representation');
  if (!saved) return { superseded: true, embedded: 0 };
  return { ...result, embedded: embed ? dirty.length : 0 };
}
async function seed(types, limit, after = '') {
  let enqueued = 0;
  for (const type of types) {
    const config = SOURCES[type];
    const rows = await supabaseGet(config.table, { select: config.key, order: `${config.key}.asc`, limit: String(limit),
      ...(after ? { [config.key]: `gt.${after}` } : {}) });
    for (const row of rows) { await supabaseRpc('enqueue_policy_search_document', { p_type: type, p_id: String(row[config.key]) }); enqueued++; }
    console.log(JSON.stringify({ source_type: type, enqueued: rows.length, next_after: rows.at(-1)?.[config.key] || null }));
  }
  return enqueued;
}
async function reconcileMissingText({ get = supabaseGet, rpc = supabaseRpc, now = Date.now() } = {}) {
  // Publication can lag Congress's enactment metadata without changing the
  // original row. Recheck a bounded set once a day, retaining its searchable
  // metadata and unchanged vectors. Never reset an active/queued/failed lease.
  const rows = await get('policy_search_documents', { select:'document_id,source_type,source_id',
    'coverage->>text_status':'eq.unavailable', refreshed_at:`lt.${new Date(now - 86400000).toISOString()}`,
    order:'refreshed_at.asc,document_id.asc', limit:'25' });
  if (!rows.length) return 0;
  const jobs = await get('policy_search_jobs', { select:'document_id,status',
    document_id:`in.(${rows.map(row => JSON.stringify(row.document_id)).join(',')})` });
  const done = new Set(jobs.filter(job => job.status === 'done').map(job => job.document_id));
  let count = 0;
  for (const row of rows) if (done.has(row.document_id)) {
    await rpc('enqueue_policy_search_document', { p_type:row.source_type, p_id:row.source_id }); count++;
  }
  return count;
}
async function run() {
  requireEnv('SUPABASE_URL'); requireEnv('SUPABASE_SERVICE_ROLE_KEY');
  const args = process.argv.slice(2), val = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : undefined;
  const limit = Math.min(1000, Math.max(1, Number(val('--limit')) || 100));
  if (args.includes('--bootstrap')) {
    let total=0, count;
    do { count=await supabaseRpc('seed_policy_search_jobs', {p_limit:1000}); total+=count; }
    while (count===1000);
    console.log(JSON.stringify({bootstrap_enqueued:total})); return total;
  }
  if (args.includes('--seed')) {
    const types = (val('--types') || 'bill,public_law,executive_order,regulation').split(',');
    if (types.some(t => !SOURCES[t])) throw new Error('Unknown --types source');
    return seed(types, limit, args.includes('--after') ? val('--after') : '');
  }
  if (args.includes('--enqueue')) {
    const key = val('--enqueue'), sep = key.indexOf(':');
    if (sep < 0 || !SOURCES[key.slice(0, sep)]) throw new Error('--enqueue requires source_type:source_id');
    return supabaseRpc('enqueue_policy_search_document', { p_type: key.slice(0, sep), p_id: key.slice(sep + 1) });
  }
  const root = requireEnv('POLICY_SEARCH_CACHE_DIR');
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const lock = path.join(root, 'RUNNING');
  try { acquireLock(lock, {pid:process.pid,started_at:new Date().toISOString()}); }
  catch (e) { if(e.message==='collector_already_running'){console.log('Search indexer already running; skipped.');process.exitCode=75;return;}throw e; }
  const loader = sourceLoader({ cacheDir: root });
  const summary = {
    attempted: 0,
    completed: 0,
    failed: 0,
    superseded: 0,
    text_only_pending: 0,
    embedded_passages: 0,
    stop_reason: 'batch_limit',
  };
  const deadline=Date.now()+Math.max(1,Number(val('--max-minutes'))||60)*60000;
  try {
    if (!fs.existsSync(path.join(root, 'STOP')) && !(process.env.POLICY_COLLECTOR_STOP_FILE && fs.existsSync(process.env.POLICY_COLLECTOR_STOP_FILE))) {
      const requeued = await reconcileMissingText();
      if (requeued) console.log(JSON.stringify({ missing_text_requeued:requeued }));
    }
    for (let i = 0; i < limit; i++) {
      if (Date.now() >= deadline) { summary.stop_reason = 'time_limit'; break; }
      if (fs.existsSync(path.join(root, 'STOP')) || (process.env.POLICY_COLLECTOR_STOP_FILE && fs.existsSync(process.env.POLICY_COLLECTOR_STOP_FILE))) {
        summary.stop_reason = 'stop_file';
        break;
      }
      if (i%25===0) {
        const status=await supabaseRpc('policy_search_status', {});
        const budget=Number(process.env.POLICY_SEARCH_DB_BUDGET_BYTES)||6*1024**3;
        if (!Number.isFinite(Number(status.database_bytes)) || Number(status.database_bytes)<=0) throw new Error('Database size check unavailable');
        if (Number(status.database_bytes) >= budget) {
          summary.stop_reason = 'storage_budget';
          console.warn('Search indexing paused: database storage budget reached.');
          process.exitCode = 73;
          break;
        }
      }
      const job = (await supabaseRpc('claim_policy_search_job', {}, 'return=representation'))?.[0];
      if (!job) { summary.stop_reason = 'no_claimable_jobs'; break; }
      summary.attempted++;
      try {
        const result = await processJob(job, loader, !args.includes('--text-only'));
        summary.embedded_passages += result.embedded;
        const finished = await supabaseRpc('finish_policy_search_job', { p_id: job.document_id, p_token: job.claim_token,
          p_error: result.pending_embeddings ? 'Text-only run; embeddings pending' : null });
        if (result.superseded || !finished) summary.superseded++;
        else if (result.pending_embeddings) summary.text_only_pending++;
        else summary.completed++;
        console.log(JSON.stringify({ document_id: job.document_id, ...result, job_finished: Boolean(finished) }));
      } catch (e) {
        // Do not persist raw provider errors or URLs with credentials.
        const reason = failureReason(e);
        await supabaseRpc('finish_policy_search_job', { p_id: job.document_id, p_token: job.claim_token,
          p_error: `Index refresh failed: ${reason}` });
        console.error(`Index refresh failed for ${job.document_id}: ${reason}`);
        summary.failed++;
        process.exitCode=2;
        if (['http_403','http_429','missing_environment'].includes(reason) || isOptionalEmbeddingError(e)) {
          summary.stop_reason = reason;
          break;
        }
      }
      await sleep(300);
    }
    // 집계 일시 장애가 색인 결과를 바꾸지 않도록, 확인하지 못한 건수는 null로 남긴다.
    let finalStatus;
    try { finalStatus = await supabaseRpc('policy_search_status', {}); }
    catch (error) { console.warn(`Search queue summary unavailable: ${failureReason(error)}`); }
    console.log(JSON.stringify({
      ...summary,
      queue_pending: finalStatus?.pending ?? null,
      queue_failed: finalStatus?.failed ?? null,
    }));
  } finally { releaseLock(lock,process.pid); }
}
module.exports = { processJob, seed, run, failureReason, reconcileMissingText };
if (require.main === module) run().catch(e => { console.error(`Search indexer stopped: ${failureReason(e)}`); process.exitCode = 1; });
