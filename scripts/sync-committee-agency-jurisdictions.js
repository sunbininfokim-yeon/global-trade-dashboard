'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  finishSyncRun, requireEnv, startSyncRun, supabaseGet, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');
const { parseCommitteeAgencyJurisdictions } = require('./lib/committee-agency-jurisdiction-source');

const ROOT = path.resolve(__dirname, '..');
const SOURCE_PATH = path.resolve(ROOT, process.env.COMMITTEE_AGENCY_JURISDICTION_FILE || 'data/policy/committee-agency-jurisdictions.json');
const RESOURCE = 'official-committee-roster:agency-jurisdictions';

function readSource() {
  if (!fs.existsSync(SOURCE_PATH)) return null;
  try {
    return JSON.parse(fs.readFileSync(SOURCE_PATH, 'utf8'));
  } catch (error) {
    throw new Error(`Committee agency jurisdictions source is not valid JSON: ${error.message}`);
  }
}

function chunks(values, size = 100) {
  const output = [];
  for (let start = 0; start < values.length; start += size) output.push(values.slice(start, start + size));
  return output;
}

async function knownValues(table, column, values) {
  const output = new Set();
  for (const group of chunks([...new Set(values)])) {
    const rows = await supabaseGet(table, { select: column, [column]: `in.(${group.join(',')})`, limit: String(group.length) });
    for (const row of rows || []) output.add(row[column]);
  }
  return output;
}

async function validateForeignKeys(rows) {
  const committees = await knownValues('committees', 'committee_id', rows.map((row) => row.committee_id));
  const agencies = await knownValues('agencies', 'agency_id', rows.map((row) => row.agency_id));
  const unknownCommittee = rows.find((row) => !committees.has(row.committee_id));
  if (unknownCommittee) throw new Error(`Unknown committee_id: ${unknownCommittee.committee_id}`);
  const unknownAgency = rows.find((row) => !agencies.has(row.agency_id));
  if (unknownAgency) {
    throw new Error(
      `Unknown agency_id: ${unknownAgency.agency_id}. Federal Register agencies must already exist in agencies before this mapping can load.`,
    );
  }
}

async function run() {
  const source = readSource();
  if (!source) {
    console.log('Committee agency jurisdictions skipped: data/policy/committee-agency-jurisdictions.json is not present yet.');
    return;
  }
  requireEnv('SUPABASE_URL');
  requireEnv('SUPABASE_SERVICE_ROLE_KEY');
  const parsed = parseCommitteeAgencyJurisdictions(source);
  const runId = await startSyncRun(RESOURCE, {
    congress: parsed.congress,
    coverage: parsed.coverage,
    source_name: parsed.sourceName,
    source_file: path.relative(ROOT, SOURCE_PATH),
  });
  try {
    await validateForeignKeys(parsed.rows);
    await supabaseUpsert('committee_agency_jurisdictions', parsed.rows, 'committee_id,agency_id,relationship_type');
    await updateSyncState(RESOURCE, {
      congress: parsed.congress,
      coverage: parsed.coverage,
      source_name: parsed.sourceName,
      source_file: path.relative(ROOT, SOURCE_PATH),
      records: parsed.rows.length,
      completed_at: new Date().toISOString(),
    });
    await finishSyncRun(runId, {
      status: 'succeeded', records_read: parsed.rows.length, records_written: parsed.rows.length,
      metadata: { congress: parsed.congress, coverage: parsed.coverage, source_name: parsed.sourceName },
    });
    console.log(`Committee agency jurisdictions complete: ${parsed.rows.length} verified records for Congress ${parsed.congress}.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
