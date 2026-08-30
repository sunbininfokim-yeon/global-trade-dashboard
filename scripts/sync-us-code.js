'use strict';

// Lightweight U.S. Code reference sync. It refreshes the official release
// point for the 54 seeded Titles; it never downloads or stores statutory text.
const {
  fetchJson, finishSyncRun, requireEnv, startSyncRun, supabaseGet, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');

const RESOURCE = 'uscode.house.gov:titles';
const DOWNLOAD_URL = 'https://uscode.house.gov/download/download.shtml';

requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

async function run() {
  const runId = await startSyncRun(RESOURCE, {});
  try {
    const html = await fetchJson(DOWNLOAD_URL, { headers: { accept: 'text/html' } }, {
      label: 'U.S. Code download page', maxRetries: 4,
    });
    const release = html.match(/Public\s+Law\s+(\d+-\d+)/i)?.[1] || null;
    const existing = await supabaseGet('us_code_titles', { select: 'title_number,title_name,is_reserved,official_url,raw_source' });
    const rows = existing.map((title) => ({
      ...title, source_release_point: release, source_updated_at: new Date().toISOString(),
      raw_source: { ...(title.raw_source || {}), source: 'uscode.house.gov', download_url: DOWNLOAD_URL },
    }));
    if (rows.length) await supabaseUpsert('us_code_titles', rows, 'title_number');
    await updateSyncState(RESOURCE, { release_point: release, completed_at: new Date().toISOString() });
    await finishSyncRun(runId, { status: 'succeeded', records_read: rows.length, records_written: rows.length, metadata: { release_point: release } });
    console.log(`U.S. Code reference complete: ${rows.length} titles, release ${release || 'unknown'}.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}
run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
