'use strict';

// Imports the current House/Senate roster already maintained by the politics-
// US product. It intentionally does not infer committee chairs or membership:
// that data is absent from this source and needs an official committee source.
const fs = require('node:fs');
const path = require('node:path');
const {
  asArray, finishSyncRun, requireEnv, startSyncRun, supabasePatch, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');

const RESOURCE = 'politics.us:legislator-roster';
const DEFAULT_ROSTER_PATH = path.resolve(__dirname, '..', 'New for anti', 'public', 'data', 'elections_board_v1.json');
const ROSTER_PATH = process.env.US_POLITICS_ROSTER_PATH || DEFAULT_ROSTER_PATH;
const MIN_CURRENT_MEMBERS = 400;

requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

function parseGeneratedAt(value) {
  const time = Date.parse(value || '');
  return Number.isFinite(time) ? new Date(time).toISOString() : null;
}

function rowsFromRoster(document, rosterSeenAt) {
  const usa = asArray(document?.countries).find((country) => country?.iso3 === 'USA');
  const congress = usa?.ui_ready?.congress;
  if (!congress) throw new Error('The politics-US roster has no ui_ready.congress section.');
  const generatedAt = parseGeneratedAt(document?.generated_at);
  const sourceName = 'politics-us/elections_board_v1';
  const byId = new Map();
  for (const member of [...asArray(congress.house_members), ...asArray(congress.senate_members)]) {
    const bioguideId = String(member?.bioguideId || '').trim();
    const chamber = String(member?.chamber || '').toLowerCase();
    if (!bioguideId || !member?.name || !['house', 'senate'].includes(chamber)) continue;
    byId.set(bioguideId, {
      bioguide_id: bioguideId,
      full_name: member.name,
      party: member.party || null,
      party_abbr: member.abbr || null,
      state: member.state || null,
      district: Number.isInteger(member.district) ? member.district : null,
      chamber,
      current_member: true,
      source_name: sourceName,
      source_updated_at: generatedAt,
      roster_seen_at: rosterSeenAt,
      raw_source: member,
    });
  }
  const rows = [...byId.values()];
  // A malformed or partial source must never retire every previously current
  // legislator simply because no fresh rows were produced.
  if (rows.length < MIN_CURRENT_MEMBERS) {
    throw new Error(`Refusing roster sync: expected at least ${MIN_CURRENT_MEMBERS} current legislators, received ${rows.length}.`);
  }
  return rows;
}

async function run() {
  const runId = await startSyncRun(RESOURCE, { roster_path: path.basename(ROSTER_PATH) });
  let rows = [];
  try {
    if (!fs.existsSync(ROSTER_PATH)) throw new Error(`Politics-US roster not found: ${ROSTER_PATH}`);
    const document = JSON.parse(fs.readFileSync(ROSTER_PATH, 'utf8'));
    const rosterSeenAt = new Date().toISOString();
    rows = rowsFromRoster(document, rosterSeenAt);
    for (let index = 0; index < rows.length; index += 100) {
      await supabaseUpsert('us_legislators', rows.slice(index, index + 100), 'bioguide_id');
    }
    // The source is a complete current-Congress roster. Only after every
    // current row is safely written can a formerly current row be retired.
    await supabasePatch('us_legislators',
      `source_name=eq.${encodeURIComponent('politics-us/elections_board_v1')}&roster_seen_at=lt.${encodeURIComponent(rosterSeenAt)}`,
      { current_member: false });
    await updateSyncState(RESOURCE, {
      source_path: path.basename(ROSTER_PATH), source_generated_at: document?.generated_at || null,
      roster_seen_at: rosterSeenAt, members: rows.length,
    });
    await finishSyncRun(runId, { status: 'succeeded', records_read: rows.length, records_written: rows.length,
      metadata: { source: 'politics-us/elections_board_v1', chambers: ['house', 'senate'] } });
    console.log(`US legislator roster complete: ${rows.length} current House/Senate members upserted.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: rows.length, error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
