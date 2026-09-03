'use strict';

// Manual Congress rollover cleanup. It is intentionally local-first and dry
// run by default: no date-based trigger can delete records on its own.
const {
  fetchJson, finishSyncRun, requireEnv, startSyncRun, supabaseRpc,
} = require('./lib/sync-utils');

const API_BASE = 'https://api.congress.gov/v3';
const API_KEY = process.env.CONGRESS_API_KEY || process.env.DATA_GOV_API_KEY;
const APPROVED = process.env.ALLOW_CONGRESS_ROLLOVER_PURGE === 'true';
const MAX_BILLS = Number(process.env.ROLLOVER_PURGE_MAX_BILLS || 1000);
const PREVIEW_LIMIT = Number(process.env.ROLLOVER_PREVIEW_LIMIT || 25);

if (!API_KEY) throw new Error('Missing CONGRESS_API_KEY (DATA_GOV_API_KEY may be used as fallback).');
requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

function bounded(value, fallback, minimum, maximum) {
  const number = Number(value);
  return Number.isInteger(number) && number >= minimum && number <= maximum ? number : fallback;
}

async function activeCongress() {
  if (process.env.CONGRESS_NUMBER) return bounded(process.env.CONGRESS_NUMBER, 0, 1, 999);
  const url = `${API_BASE}/congress/current?${new URLSearchParams({ format: 'json', api_key: API_KEY })}`;
  const body = await fetchJson(url, {}, { label: 'Congress.gov current Congress', maxRetries: 3 });
  const congress = Number(body?.congress?.number);
  if (!Number.isInteger(congress) || congress < 1) throw new Error('Congress.gov did not return a valid active Congress number.');
  return congress;
}

function scalar(response, field) {
  const value = Array.isArray(response) ? response[0]?.[field] : response?.[field] ?? response;
  return Number(value) || 0;
}

async function run() {
  const active = await activeCongress();
  const previous = bounded(process.env.ROLLOVER_PREVIOUS_CONGRESS, active - 1, 1, active - 1);
  if (previous !== active - 1) throw new Error(`Refusing purge for Congress ${previous}: active Congress is ${active}; only the immediately prior Congress may be targeted.`);
  const maxBills = bounded(MAX_BILLS, 1000, 1, 10000);
  const runId = await startSyncRun('congress.gov:rollover', {
    active_congress: active, previous_congress: previous, dry_run: !APPROVED, max_bills: maxBills,
  });

  try {
    const preview = await supabaseRpc('preview_congress_rollover_purge', {
      p_previous_congress: previous,
      p_result_limit: bounded(PREVIEW_LIMIT, 25, 1, 1000),
    }, 'return=representation');
    const previewRows = Array.isArray(preview) ? preview : [];
    // The preview is deliberately capped for human inspection, but its window
    // count represents every eligible bill. Never mistake the sample size for
    // the candidate count that a person must approve before a purge.
    const previewCount = Number(previewRows[0]?.total_candidate_count) || 0;
    const previewSampleCount = previewRows.length;

    if (!APPROVED) {
      await finishSyncRun(runId, { status: 'succeeded', records_read: previewCount, records_written: 0,
        metadata: { active_congress: active, previous_congress: previous, dry_run: true,
          candidate_count: previewCount, preview_sample_count: previewSampleCount } });
      console.log(`Congress rollover dry run: ${previewCount} total candidates for Congress ${previous}; showing a ${previewSampleCount}-row sample. No records were deleted.`);
      return;
    }

    const deleted = await supabaseRpc('purge_congress_rollover', {
      p_previous_congress: previous, p_max_bills: maxBills, p_confirm: true,
    }, 'return=representation');
    const deletedBills = scalar(deleted, 'deleted_bill_count');
    const deletedQueue = scalar(deleted, 'deleted_queue_count');
    await finishSyncRun(runId, { status: 'succeeded', records_read: previewCount, records_written: deletedBills,
      metadata: { active_congress: active, previous_congress: previous, dry_run: false,
        candidate_count: previewCount, preview_sample_count: previewSampleCount,
        deleted_bills: deletedBills, deleted_queue_rows: deletedQueue } });
    console.log(`Congress rollover complete: deleted ${deletedBills} non-enacted bills and ${deletedQueue} matching queue rows for Congress ${previous}.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
