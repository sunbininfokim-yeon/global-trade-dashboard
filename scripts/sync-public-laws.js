'use strict';

// GovInfo Public Law indexer. It stores official metadata and citations only;
// statutory text, PDF, and USLM bodies remain at their official source URLs.
const {
  asArray, checkpointSyncState, enqueuePolicyItem, fetchJson, finishSyncRun, firstNonEmpty,
  mapWithConcurrency, markPolicyQueue, parseDateOnly, parseTimestamp, requireEnv, startSyncRun,
  supabaseGet, supabaseInsert, supabasePatch, supabaseUpsert, takePolicyQueue, updateSyncState,
} = require('./lib/sync-utils');

const API_BASE = 'https://api.govinfo.gov';
const API_KEY = process.env.DATA_GOV_API_KEY;
const RESOURCE = 'govinfo:public-laws';
const MAX_PUBLIC_LAWS = Number(process.env.MAX_PUBLIC_LAWS || 100);
const PAGE_SIZE = Math.min(100, Number(process.env.PUBLIC_LAW_DISCOVERY_PAGE_SIZE || 100));
const BOOTSTRAP = process.env.PUBLIC_LAW_MODE === 'bootstrap';
// Public Law metadata is compact (no PDF/body storage), so the default covers
// the complete Congress.gov/GovInfo historical series rather than only recent law.
const START_CONGRESS = Number(process.env.PUBLIC_LAW_START_CONGRESS || 1);

requireEnv('DATA_GOV_API_KEY');
requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

function apiUrl(path) { return `${API_BASE}${path}${path.includes('?') ? '&' : '?'}api_key=${encodeURIComponent(API_KEY)}`; }
function publicLawIdentity(packageId) {
  const match = String(packageId || '').match(/^PLAW-(\d+)publ(\d+)$/i);
  return match ? { congress: Number(match[1]), number: Number(match[2]) } : null;
}
function publicLawId(identity) { return `${identity.congress}-public-${identity.number}`; }
function govInfoDetailsUrl(packageId) { return `https://www.govinfo.gov/app/details/${packageId}`; }

async function get(path, options = {}) {
  return fetchJson(apiUrl(path), options, { label: `GovInfo ${path}`, maxRetries: 6 });
}
async function loadState() {
  return (await supabaseGet('data_sync_state', { select: 'cursor,last_successful_at', sync_resource: `eq.${RESOURCE}`, limit: '1' }))?.[0] || null;
}
async function searchPage(state) {
  const cursor = state?.cursor || {};
  const body = {
    query: 'collection:(PLAW)', pageSize: String(PAGE_SIZE), offsetMark: BOOTSTRAP ? (cursor.offset_mark || '*') : '*',
    sorts: [{ field: BOOTSTRAP ? 'publishdate' : 'lastModified', sortOrder: 'DESC' }],
  };
  if (!BOOTSTRAP && state?.last_successful_at) body.modifiedSince = state.last_successful_at.replace(/\.\d{3}Z$/, 'Z');
  const response = await get('/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const results = asArray(response?.results).filter((row) => {
    const id = publicLawIdentity(row.packageId);
    return id && id.congress >= START_CONGRESS;
  });
  const nextOffsetMark = response?.offsetMark || cursor.offset_mark || '*';
  const nextCursor = BOOTSTRAP
    ? { mode: 'bootstrap', offset_mark: nextOffsetMark, complete: !results.length || nextOffsetMark === cursor.offset_mark }
    : { mode: 'incremental', completed_at: new Date().toISOString() };
  return { results, cursor: nextCursor };
}
async function stage(results) {
  let changed = 0;
  for (const item of results) {
    const identity = publicLawIdentity(item.packageId);
    if (!identity) continue;
    const result = await enqueuePolicyItem(RESOURCE, item.packageId, {
      package_id: item.packageId, congress: identity.congress, law_number: identity.number,
      title: item.title || null, issued_on: item.dateIssued || null,
    }, { sourceUpdatedAt: item.lastModified || item.dateIssued, priority: identity.congress === 119 ? 20 : 0 });
    if (result !== 'unchanged') changed += 1;
  }
  return changed;
}
function statuteCitation(summary) {
  const parts = [];
  for (const ref of asArray(summary?.references)) {
    if (ref?.collectionCode !== 'STATUTE') continue;
    for (const item of asArray(ref.contents)) {
      const pages = asArray(item.pages).filter(Boolean);
      if (item.title) parts.push(`${item.title} Stat.${pages.length ? ` ${pages.join(', ')}` : ''}`);
    }
  }
  return parts.join('; ') || null;
}
function codeCitations(summary) {
  const rows = [];
  for (const ref of asArray(summary?.references)) {
    if (ref?.collectionCode !== 'USCODE') continue;
    for (const item of asArray(ref.contents)) {
      const title = Number(item.title);
      if (!Number.isInteger(title) || title < 1 || title > 54) continue;
      const sections = asArray(item.sections);
      if (!sections.length) rows.push({ title, citation: `${title} U.S.C.` });
      for (const section of sections) rows.push({ title, citation: `${title} U.S.C. ${section}` });
    }
  }
  return [...new Map(rows.map((row) => [`${row.title}:${row.citation}`, row])).values()];
}
async function ensureCodeSection(citation, sourceReleasePoint) {
  const match = citation.citation.match(/^(\d+) U\.S\.C\. (.+)$/);
  if (!match) return null;
  const id = `usc-${citation.title}-${match[2]}`;
  await supabaseUpsert('us_code_sections', [{
    us_code_section_id: id, title_number: citation.title, section_number: match[2],
    official_url: `https://uscode.house.gov/view.xhtml?req=(title:${citation.title}+section:${encodeURIComponent(match[2])}+edition:prelim)`,
    source_release_point: sourceReleasePoint || null,
    raw_source: { source: 'govinfo.gov', citation: citation.citation },
  }], 'us_code_section_id');
  return id;
}
async function savePackage(entry) {
  const packageId = entry.payload?.package_id || entry.source_key;
  const identity = publicLawIdentity(packageId);
  if (!identity) throw new Error(`Unsupported Public Law package id: ${packageId}`);
  const summary = await get(`/packages/${encodeURIComponent(packageId)}/summary`);
  if (String(summary.documentType || summary.docClass || '').toUpperCase() !== 'PUBLIC') return { skipped: true };
  const lawId = publicLawId(identity);
  const existing = (await supabaseGet('public_laws', { select: 'public_law_id', public_law_id: `eq.${lawId}`, limit: '1' }))?.[0];
  const bill = (await supabaseGet('bills', {
    select: 'bill_id', congress_number: `eq.${identity.congress}`, law_type: 'eq.public', law_number: `eq.${identity.number}`, limit: '1',
  }))?.[0];
  const citations = codeCitations(summary);
  const classification = citations.length ? 'classified' : 'pending';
  await supabaseUpsert('public_laws', [{
    public_law_id: lawId, congress_number: identity.congress, law_number: identity.number,
    law_title: firstNonEmpty(asArray(summary.shortTitle).at(0)?.title, summary.title, entry.payload?.title),
    enacted_date: parseDateOnly(summary.dateIssued || entry.payload?.issued_on), bill_id: bill?.bill_id || null,
    govinfo_url: summary.detailsLink || govInfoDetailsUrl(packageId), source_package_id: packageId,
    statutes_at_large_citation: statuteCitation(summary), official_pdf_url: summary.download?.pdfLink || null,
    official_text_url: summary.download?.txtLink || null, classification_status: classification,
    source_updated_at: parseTimestamp(summary.lastModified), last_synced_at: new Date().toISOString(),
    raw_source: { source: 'govinfo.gov', package_id: packageId, references: asArray(summary.references) },
  }], 'public_law_id');
  if (!existing) {
    for (const citation of citations) {
      const sectionId = await ensureCodeSection(citation, null);
      await supabaseInsert('public_law_code_impacts', {
      public_law_id: lawId, title_number: citation.title, us_code_section_id: sectionId, section_citation: citation.citation,
      impact_type: 'unknown', classification_status: 'classified', source_url: summary.detailsLink || govInfoDetailsUrl(packageId),
    });
    }
  }
  return { skipped: false, citations: citations.length };
}
async function run() {
  const state = await loadState();
  const runId = await startSyncRun(RESOURCE, { mode: BOOTSTRAP ? 'bootstrap' : 'incremental', max_public_laws: MAX_PUBLIC_LAWS, start_congress: START_CONGRESS });
  let read = 0; let written = 0;
  try {
    const discovered = await searchPage(state);
    const staged = await stage(discovered.results);
    await checkpointSyncState(RESOURCE, discovered.cursor);
    const queued = await takePolicyQueue(RESOURCE, MAX_PUBLIC_LAWS); read = queued.length;
    for (const entry of queued) {
      await markPolicyQueue(entry.queue_id, { status: 'processing', claimed_at: new Date().toISOString(), attempts: entry.attempts + 1 });
      try {
        const result = await savePackage(entry);
        await markPolicyQueue(entry.queue_id, { status: result.skipped ? 'skipped' : 'succeeded', completed_at: new Date().toISOString(), last_error: null });
        if (!result.skipped) written += 1;
      } catch (error) {
        await markPolicyQueue(entry.queue_id, { status: 'pending', available_at: new Date(Date.now() + 300_000).toISOString(), last_error: error.message });
        console.error(`Public Law ${entry.source_key} deferred: ${error.message}`);
      }
    }
    await updateSyncState(RESOURCE, { ...discovered.cursor, completed_at: new Date().toISOString() });
    await finishSyncRun(runId, { status: written === read ? 'succeeded' : 'partial', records_read: read, records_written: written, metadata: { discovered: discovered.results.length, staged } });
    console.log(`GovInfo Public Laws complete: ${written}/${read} records.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: read, records_written: written, error_summary: error.message });
    throw error;
  }
}
run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
