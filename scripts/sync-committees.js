'use strict';

// Congress.gov committee directory sync. The API supplies authoritative
// committee metadata and may expose child committees in a detail response.
// It never guesses member/leadership data absent from that response.
const {
  asArray, createRequestGate, fetchJson, firstNonEmpty, requireEnv,
  startSyncRun, finishSyncRun, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');

const API_BASE = 'https://api.congress.gov/v3';
const API_KEY = process.env.CONGRESS_API_KEY || process.env.DATA_GOV_API_KEY;
const INTERVAL_MS = Number(process.env.CONGRESS_REQUEST_INTERVAL_MS || 850);
const PAGE_SIZE = Math.min(250, Number(process.env.COMMITTEE_DISCOVERY_PAGE_SIZE || 250));
const MAX_PAGES = Math.min(20, Number(process.env.MAX_COMMITTEE_DISCOVERY_PAGES || 10));

if (!API_KEY) throw new Error('Missing CONGRESS_API_KEY (DATA_GOV_API_KEY may be used as fallback).');
requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

const gate = createRequestGate(INTERVAL_MS);

function apiUrl(pathname, query = {}) {
  return `${API_BASE}${pathname}?${new URLSearchParams({ format: 'json', api_key: API_KEY, ...query })}`;
}

async function apiGet(pathname, query = {}) {
  return gate(() => fetchJson(apiUrl(pathname, query), {}, { label: `Congress.gov ${pathname}`, maxRetries: 5 }));
}

function chamber(value) {
  const text = String(value || '').toLowerCase();
  return ['house', 'senate', 'joint'].includes(text) ? text : null;
}

function codeOf(value) {
  const matched = String(value?.url || '').match(/\/committee\/(?:\d+\/)?(house|senate|joint)\/([^/?]+)/i);
  return String(firstNonEmpty(value?.systemCode, value?.committeeCode, value?.code, matched?.[2], '')).toLowerCase() || null;
}

function withoutKey(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    parsed.searchParams.delete('api_key');
    parsed.searchParams.delete('format');
    return parsed.toString();
  } catch { return url; }
}

function rowFrom(value, congress, parentCommitteeId = null) {
  const committeeChamber = chamber(firstNonEmpty(value?.chamber, String(value?.url || '').match(/\/committee\/(?:\d+\/)?(house|senate|joint)/i)?.[1]));
  const committeeCode = codeOf(value);
  if (!committeeChamber || !committeeCode) return null;
  return {
    committee_id: `${congress}-${committeeChamber}-${committeeCode}`,
    congress_number: congress,
    committee_code: committeeCode,
    chamber: committeeChamber,
    committee_type: value?.isSubcommittee || parentCommitteeId ? 'subcommittee' : firstNonEmpty(value?.committeeType, 'standing'),
    name: firstNonEmpty(value?.name, value?.committeeName, committeeCode),
    parent_committee_id: parentCommitteeId,
    jurisdiction_summary: firstNonEmpty(value?.jurisdiction, value?.jurisdictionSummary) || null,
    official_url: withoutKey(value?.url),
    raw_source: value,
  };
}

async function activeCongress() {
  if (process.env.CONGRESS_NUMBER) {
    const configured = Number(process.env.CONGRESS_NUMBER);
    if (!Number.isInteger(configured) || configured < 1) throw new Error('CONGRESS_NUMBER must be a positive integer.');
    return configured;
  }
  const body = await apiGet('/congress/current');
  const congress = Number(body?.congress?.number);
  if (!Number.isInteger(congress) || congress < 1) throw new Error('Congress.gov did not return a valid active Congress number.');
  return congress;
}

function detailCandidates(body) {
  const committee = body?.committee || body || {};
  return asArray(committee?.subcommittees?.item || committee?.subcommittees || committee?.subcommittees?.committees);
}

async function run() {
  const congress = await activeCongress();
  const runId = await startSyncRun('congress.gov:committees', { congress });
  let read = 0;
  let written = 0;
  try {
    const parents = [];
    for (let page = 0, offset = 0; page < MAX_PAGES; page += 1) {
      const body = await apiGet(`/committee/${congress}`, { limit: PAGE_SIZE, offset });
      const items = asArray(body?.committees);
      parents.push(...items);
      if (items.length < PAGE_SIZE || !body?.pagination?.next) break;
      offset += items.length;
    }
    read = parents.length;
    for (const item of parents) {
      const parent = rowFrom(item, congress);
      if (!parent) continue;
      await supabaseUpsert('committees', [parent], 'committee_id');
      written += 1;
      const detail = await apiGet(`/committee/${congress}/${parent.chamber}/${parent.committee_code}`);
      for (const child of detailCandidates(detail)) {
        const subcommittee = rowFrom(child, congress, parent.committee_id);
        if (!subcommittee) continue;
        await supabaseUpsert('committees', [subcommittee], 'committee_id');
        written += 1;
      }
    }
    await updateSyncState('congress.gov:committees', { congress, directory_records: read, committee_rows: written });
    await finishSyncRun(runId, { status: 'succeeded', records_read: read, records_written: written,
      metadata: { congress, source: 'Congress.gov committee directory' } });
    console.log(`Congress committees complete: ${written} committee/subcommittee rows from ${read} directory records.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: read, records_written: written, error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
