'use strict';

// Local-only semantic-search preparation. It never downloads source data and
// only fills rows whose embedding is still NULL, so rerunning it is safe.
const {
  finishSyncRun, geminiEmbeddings, geminiModelName, isOptionalEmbeddingError,
  requireEnv, sleep, startSyncRun, supabaseGet, supabasePatch, supabaseRpc,
} = require('./lib/sync-utils');

const RESOURCE = 'policy:embedding-backfill';
const SOURCE_ORDER = ['public_laws', 'executive_orders', 'regulations', 'bills'];
const DEFAULT_LIMIT = 100;
const MAX_BATCH_SIZE = 50;

const SOURCES = {
  public_laws: {
    table: 'public_laws', key: 'public_law_id',
    select: 'public_law_id,law_title,congress_number,law_number',
    text: row => `${row.law_title}\nPublic Law ${row.congress_number}-${row.law_number}`,
  },
  bills: {
    table: 'bills',
    key: 'bill_id',
    select: 'bill_id,title,summary',
    text: (row) => `${row.title}\n\n${row.summary || ''}`,
  },
  executive_orders: {
    table: 'executive_orders',
    key: 'eo_number',
    select: 'eo_number,title,summary',
    text: (row) => `${row.title}\n\n${row.summary || ''}`,
  },
  regulations: {
    table: 'regulations',
    key: 'regulation_id',
    select: 'regulation_id,title,abstract',
    text: (row) => `${row.title}\n\n${row.abstract || ''}`,
  },
};

function positiveInteger(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function backfillLimit() {
  // 0 means "keep going until every selected row is embedded". Start with
  // the default cap first, then use 0 only after confirming Gemini quota.
  const parsed = Number(process.env.EMBEDDING_BACKFILL_LIMIT ?? DEFAULT_LIMIT);
  if (parsed === 0) return Infinity;
  return positiveInteger(parsed, DEFAULT_LIMIT);
}

function selectedSources() {
  const raw = String(process.env.EMBEDDING_BACKFILL_TARGETS || SOURCE_ORDER.join(','));
  const targets = [...new Set(raw.split(',').map((value) => value.trim()).filter(Boolean))];
  if (!targets.length || targets.some((target) => !SOURCES[target])) {
    throw new Error(`EMBEDDING_BACKFILL_TARGETS must use only: ${SOURCE_ORDER.join(', ')}`);
  }
  return SOURCE_ORDER.filter((source) => targets.includes(source));
}

function keyFilter(column, value) {
  // supabasePatch appends this filter to the URL directly (unlike
  // supabaseGet), so encode only the record key here.
  return `${column}=eq.${encodeURIComponent(value)}`;
}

async function loadUnembedded(source, limit) {
  const config = SOURCES[source];
  return supabaseGet(config.table, {
    select: config.select,
    embedding: 'is.null',
    order: `${config.key}.asc`,
    limit: String(limit),
  });
}

async function countUnembedded(source) {
  const config = SOURCES[source];
  // This project disables PostgREST aggregates. Page only primary keys so
  // dry-run works without count() or downloading vectors/document bodies.
  let total = 0;
  for (;;) {
    const rows = await supabaseGet(config.table, {
      select: config.key, embedding: 'is.null',
      order: `${config.key}.asc`, offset: String(total), limit: '1000',
    });
    total += rows.length;
    if (rows.length < 1000) return total;
  }
}

async function refreshBillRelations(row, vector, model) {
  if (process.env.REFRESH_BILL_SEMANTIC_RELATIONS === 'false') return 0;
  try {
    return Number(await supabaseRpc('refresh_bill_semantic_relations', {
      p_source_bill_id: row.bill_id,
      p_source_embedding: vector,
      p_embedding_model: model,
    }, 'return=representation')) || 0;
  } catch (error) {
    // Search remains useful even if the optional bill-to-bill relation RPC was
    // not installed in this Supabase project. Do not waste embedding work.
    console.warn(`Bill ${row.bill_id}: semantic relation refresh skipped: ${error.message}`);
    return 0;
  }
}

async function embedBatch(source, rows, apiKey, model, dryRun) {
  const config = SOURCES[source];
  if (dryRun) return { embedded: 0, relations: 0 };
  const vectors = await geminiEmbeddings(rows.map(config.text), apiKey, model);
  let relations = 0;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    await supabasePatch(config.table, `${keyFilter(config.key, row[config.key])}&embedding=is.null`, {
      embedding: vectors[index], embedding_model: model, embedded_at: new Date().toISOString(),
    });
    if (source === 'bills') relations += await refreshBillRelations(row, vectors[index], model);
  }
  return { embedded: rows.length, relations };
}

async function run() {
  requireEnv('SUPABASE_URL');
  requireEnv('SUPABASE_SERVICE_ROLE_KEY');

  const targets = selectedSources();
  const limit = backfillLimit();
  const batchSize = Math.min(MAX_BATCH_SIZE, positiveInteger(process.env.EMBEDDING_BACKFILL_BATCH_SIZE, 25));
  const intervalMs = positiveInteger(process.env.EMBEDDING_BACKFILL_BATCH_INTERVAL_MS, 1_500);
  const dryRun = process.env.EMBEDDING_BACKFILL_DRY_RUN === 'true';
  const model = geminiModelName();
  const runId = dryRun ? null : await startSyncRun(RESOURCE, {
    targets, limit: Number.isFinite(limit) ? limit : 'unlimited', batch_size: batchSize,
    batch_interval_ms: intervalMs, model,
  });
  const result = { embedded: {}, candidates: {}, semantic_relations: 0, stopped_for_quota: false };
  let remainingBudget = limit;

  try {
    if (dryRun) {
      for (const source of targets) {
        const total = await countUnembedded(source);
        result.candidates[source] = total;
        const requests = Math.ceil(total / MAX_BATCH_SIZE);
        console.log(`Dry run: ${source} has ${total} unembedded rows; estimated Gemini requests at ${MAX_BATCH_SIZE} rows/request: ${requests}.`);
      }
      console.log(`Policy embedding backfill dry_run: 0 rows embedded with ${model}.`);
      return;
    }

    for (const source of targets) {
      result.embedded[source] = 0;
      result.candidates[source] = 0;
      while (remainingBudget > 0) {
        const requestLimit = Number.isFinite(remainingBudget) ? Math.min(batchSize, remainingBudget) : batchSize;
        const rows = await loadUnembedded(source, requestLimit);
        result.candidates[source] += rows.length;
        if (!rows.length) break;

        let batch;
        try {
          batch = await embedBatch(source, rows, requireEnv('GEMINI_API_KEY'), model, false);
        } catch (error) {
          if (!isOptionalEmbeddingError(error)) throw error;
          result.stopped_for_quota = true;
          console.warn(`${source}: embedding backfill paused without changing remaining rows: ${error.message}`);
          break;
        }
        result.embedded[source] += batch.embedded;
        result.semantic_relations += batch.relations;
        if (Number.isFinite(remainingBudget)) remainingBudget -= batch.embedded;
        console.log(`${source}: embedded ${batch.embedded}; total in this run ${result.embedded[source]}.`);
        if (rows.length < requestLimit) break;
        if (remainingBudget > 0) await sleep(intervalMs);
      }
      if (result.stopped_for_quota || remainingBudget <= 0) break;
    }

    const totalEmbedded = Object.values(result.embedded).reduce((sum, count) => sum + count, 0);
    const status = dryRun ? 'dry_run' : (result.stopped_for_quota || remainingBudget <= 0 ? 'partial' : 'succeeded');
    if (runId) await finishSyncRun(runId, {
      status, records_read: Object.values(result.candidates).reduce((sum, count) => sum + count, 0),
      records_written: totalEmbedded,
      metadata: { ...result, model, targets, limit: Number.isFinite(limit) ? limit : 'unlimited', batch_size: batchSize },
    });
    console.log(`Policy embedding backfill ${status}: ${totalEmbedded} rows embedded with ${model}.`);
  } catch (error) {
    if (runId) await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
