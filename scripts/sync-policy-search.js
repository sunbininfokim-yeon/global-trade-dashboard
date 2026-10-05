'use strict';
// Independent, leased search-index jobs. Source collectors remain untouched.
const fs = require('node:fs'), path = require('node:path');
const { sourceLoader, SOURCES } = require('./lib/policy-search-source');
const { MODEL } = require('./lib/policy-search-document');
const { acquireLock, releaseLock } = require('./lib/policy-search-lock');
const { supabaseGet, supabaseRpc, geminiEmbeddings, isOptionalEmbeddingError, requireEnv, sleep } = require('./lib/sync-utils');

async function processJob(job, loader, embed = true) {
  const document = await loader.document(job.source_type, job.source_id);
  const existing = await supabaseGet('policy_search_passages', { select: 'passage_index,input_hash,embedding_model,embedded_at', document_id: `eq.${job.document_id}` });
  const saved = await supabaseRpc('save_policy_search_document', { p_document: document, p_passages: document.passages, p_token: job.claim_token }, 'return=representation');
  if (!saved) return { superseded: true, embedded: 0 };
  const dirty = document.passages.filter(p => !existing.some(x => x.passage_index === p.passage_index && x.input_hash === p.input_hash && x.embedding_model === MODEL && x.embedded_at));
  if (embed && dirty.length) {
    const vectors = await geminiEmbeddings(dirty.map(p => p.input_text), requireEnv('GEMINI_API_KEY'), MODEL);
    dirty.forEach((p, i) => { p.embedding = vectors[i]; p.embedding_model = MODEL; });
    if (!await supabaseRpc('save_policy_search_document', { p_document: document, p_passages: document.passages, p_token: job.claim_token }, 'return=representation'))
      return { superseded: true, embedded: dirty.length };
  }
  // A text-only preview must remain queued for later embeddings.
  return { embedded: embed ? dirty.length : 0, text_status: document.text_status, coverage: document.embedding_coverage, pending_embeddings: !embed && dirty.length > 0 };
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
  const loader = sourceLoader({ cacheDir: root }); let completed = 0;
  const deadline=Date.now()+Math.max(1,Number(val('--max-minutes'))||60)*60000;
  try {
    for (let i = 0; i < limit; i++) {
      if (Date.now()>=deadline) break;
      if (fs.existsSync(path.join(root, 'STOP')) || (process.env.POLICY_COLLECTOR_STOP_FILE && fs.existsSync(process.env.POLICY_COLLECTOR_STOP_FILE))) break;
      if (i%25===0) {
        const status=await supabaseRpc('policy_search_status', {});
        const budget=Number(process.env.POLICY_SEARCH_DB_BUDGET_BYTES)||6*1024**3;
        if (!Number.isFinite(Number(status.database_bytes)) || Number(status.database_bytes)<=0) throw new Error('Database size check unavailable');
        if (Number(status.database_bytes)>=budget) { console.warn('Search indexing paused: database storage budget reached.');process.exitCode=73;break; }
      }
      const job = (await supabaseRpc('claim_policy_search_job', {}, 'return=representation'))?.[0]; if (!job) break;
      try {
        const result = await processJob(job, loader, !args.includes('--text-only'));
        await supabaseRpc('finish_policy_search_job', { p_id: job.document_id, p_token: job.claim_token,
          p_error: result.pending_embeddings ? 'Text indexed; embeddings pending' : null });
        completed++; console.log(JSON.stringify({ document_id: job.document_id, ...result }));
      } catch (e) {
        // Do not persist raw provider errors or URLs with credentials.
        await supabaseRpc('finish_policy_search_job', { p_id: job.document_id, p_token: job.claim_token,
          p_error: `Index refresh failed: ${e.status || e.name}` });
        console.error(`Index refresh failed for ${job.document_id}: ${e.status || e.name}`);
        process.exitCode=2;
        if ([403,429].includes(e.status) || isOptionalEmbeddingError(e)) break;
      }
      await sleep(300);
    }
    console.log(JSON.stringify({ completed }));
  } finally { releaseLock(lock,process.pid); }
}
module.exports = { processJob, seed, run };
if (require.main === module) run().catch(e => { console.error(e.message); process.exitCode = 1; });
