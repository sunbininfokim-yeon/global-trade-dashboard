// Read-only official notice discovery. This module never edits rate/stage catalogs.
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';

import { REMEDY_MONITOR_CATALOG, scheduleReviews } from '../../New for anti/policy-simulator/remedy-monitor-catalog.mjs';

const API = 'https://www.federalregister.gov/api/v1/documents.json';
const isoDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const digest = text => createHash('sha256').update(text).digest('hex');
const canonical = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const normalized = text => text.replace(/&(?:ndash|mdash);|&#(?:8211|8212);/g, '-')
  .replace(/[\u2010-\u2015\u2212]/g, '-')
  // GovInfo's fixed-width tables can put the right-hand POR column between
  // "A-" on one line and "580-867" on the following line.
  .replace(/\b([AC]-(?:\d{3}-)?)[ \t]+\d{1,2}\/\d{1,2}\/\d{2,4}-\d{1,2}\/\d{1,2}\/\d{2,4}[ \t]*\r?\n[ \t]*(\d{3}(?:-\d{3})?)\b/g, '$1$2')
  .replace(/\b([AC]-(?:\d{3}-)?)[ \t]+[A-Za-z .'-]+\(\d{3}\)[ \t]*\d{3}-\d{4}\.[ \t]*\r?\n[ \t]*(\d{3}(?:-\d{3})?)\b/g, '$1$2')
  .replace(/\b([AC])\s*-\s*(\d{3})\s*-\s*(\d{3})\b/g, '$1-$2-$3');
export function queryURL(caseId, from, through, page = 1) {
  const u = new URL(API);
  for (const [k, v] of Object.entries({ 'conditions[term]': `"${caseId}"`, 'conditions[publication_date][gte]': from,
    'conditions[publication_date][lte]': through, 'conditions[agencies][]': 'international-trade-administration',
    per_page: '100', order: 'newest', page: String(page) })) u.searchParams.set(k, v);
  for (const f of ['document_number', 'publication_date', 'title', 'docket_ids', 'html_url', 'correction_of', 'corrections']) u.searchParams.append('fields[]', f);
  return u.href;
}
export function normalizeNotice(d, caseId, from, through) {
  if (!/^\d{4}-\d{5}$/.test(d.document_number || '') || !isoDate(d.publication_date || '') || d.publication_date < from || d.publication_date > through
      || typeof d.title !== 'string' || !d.title.trim() || !Array.isArray(d.docket_ids)) throw new Error('Invalid official notice metadata');
  const id = d.document_number, day = d.publication_date;
  return { document_id: id, published: day, title: d.title, case_id: caseId,
    docket_ids: d.docket_ids.map(x => normalized(String(x))),
    url: `https://www.govinfo.gov/content/pkg/FR-${day}/html/${id}.htm`,
    pdf_url: `https://www.govinfo.gov/content/pkg/FR-${day}/pdf/${id}.pdf`,
    correction_of: d.correction_of ?? null, corrections: d.corrections ?? [] };
}
export async function atomicJSON(path, value) {
  await writeFile(`${path}.tmp`, JSON.stringify(value, null, 2) + '\n');
  await rename(`${path}.tmp`, path);
}
export async function discoverNotices({ previous = null, from = '2026-01-01', through = new Date().toISOString().slice(0, 10),
  fetchImpl = fetch, wait = ms => new Promise(r => setTimeout(r, ms)), now = () => new Date().toISOString(),
  persist = async () => {}, cache = async () => {}, catalog = AD_CATALOG, minIntervalMs = 1500, maxRequests = 80, resumeIncomplete = false } = {}) {
  if (!isoDate(from) || !isoDate(through) || from > through || through > now().slice(0, 10)) throw new Error('Invalid discovery date window');
  if (previous && (previous.schema_version !== 1 || !previous.cases || previous.from !== from)) throw new Error('Incompatible checkpoint/window; use a separate state directory');
  if (Object.values(previous?.cases || {}).some(c => c.searched_through > through)) throw new Error('Cannot move an existing checkpoint backwards');
  if (previous?.blocked_until && Date.parse(previous.blocked_until) > Date.parse(now())) throw new Error(`Source cooldown until ${previous.blocked_until}`);
  const state = structuredClone(previous || { schema_version: 1, from, cases: {} });
  state.last_attempt_at = now(); state.requested_through = through; state.status = 'running'; delete state.blocked_until;
  let requests = 0, fatal = false;
  const request = async url => {
    if (requests >= maxRequests) throw new Error('Bounded request budget exhausted');
    if (requests++) await wait(minIntervalMs);
    const res = await fetchImpl(url, { headers: { Accept: url.startsWith(API) ? 'application/json' : 'text/html', 'User-Agent': 'ChokeMonitor-AD-Review/1.0' }, signal: AbortSignal.timeout(30000), redirect: 'error' });
    if (!res.ok) {
      // Stop the entire run on blocking/rate limits; never retry through them.
      if (res.status === 403 || res.status === 429) {
        fatal = true;
        const retry = res.headers.get('retry-after'), seconds = /^\d+$/.test(retry || '') ? Number(retry) : 0;
        const retryAt = seconds ? Date.parse(now()) + seconds * 1000 : Date.parse(retry || '');
        state.blocked_until = new Date(Math.max(Date.parse(now()) + 4 * 3600000, Number.isFinite(retryAt) ? retryAt : 0)).toISOString();
      }
      throw new Error(`Official source HTTP ${res.status}`);
    }
    return res;
  };
  for (const c of catalog.cases) {
    if (fatal) break;
    const old = state.cases[c.case_id];
    // Registry metadata is regenerated from the reviewed case universe, not source titles.
    if(old && catalog===REMEDY_MONITOR_CATALOG)Object.assign(old,{product:c.product,country:c.country,duty:c.duty});
    if (resumeIncomplete && old?.status === 'complete' && old.searched_through === through) continue;
    try {
      // Each case is a transaction boundary. No successful watermark until every
      // list page and every candidate's source body have been received and checked.
      let pages = 1, expectedCount = null; const found = new Map();
      for (let page = 1; page <= pages; page++) {
        const body = await (await request(queryURL(c.case_id, from, through, page))).json();
        if (!Array.isArray(body.results) || !Number.isInteger(body.count) || body.count < 0 || !Number.isInteger(body.total_pages)
            || body.total_pages < 0 || body.total_pages > 2 || (expectedCount !== null && body.count !== expectedCount)) throw new Error('Incomplete or oversized official search result');
        expectedCount = body.count; pages = Math.max(1, body.total_pages);
        for (const d of body.results) {
          const n = normalizeNotice(d, c.case_id, from, through);
          if (found.has(n.document_id)) throw new Error('Duplicate notice across pages; rerun stable snapshot');
          found.set(n.document_id, n);
        }
      }
      if (found.size !== expectedCount) throw new Error('Official result count mismatch');
      const notices = []; const currentIds = new Set();
      for (const n of found.values()) {
        const source = await (await request(n.url)).text();
        const plain = normalized(source.replace(/<[^>]*>/g, ' '));
        if (!plain.includes(n.document_id) || !plain.includes(c.case_id) || !plain.includes('Federal Register')) throw new Error(`Source identity mismatch: ${n.document_id}`);
        // Search may find a footnote/reference. Bind only official docket metadata
        // or an explicit bracketed docket in collective initiation/opportunity notices.
        const bracket = new RegExp(`\\[[^\\]]{0,1000}\\b${c.case_id}\\b[^\\]]{0,1000}\\]`).test(plain);
        const collective = /Initiation of .*Reviews|Opportunity To Request Administrative Review|Advance Notification of Sunset Review/i.test(n.title);
        if (!n.docket_ids.includes(c.case_id) && !bracket && !collective) continue;
        const before = old?.notices?.find(x => x.document_id === n.document_id);
        const content_hash = digest(source), metadata_hash = digest(canonical(n));
        const changed = Boolean(before && (before.content_hash !== content_hash || before.metadata_hash !== metadata_hash));
        const inCatalog = Boolean(catalog.documents[n.document_id]);
        const record = { ...n, content_hash, metadata_hash, first_seen_at: before?.first_seen_at || now(), last_seen_at: now(),
          catalogued: inCatalog, review_status: changed || before?.review_status === 'changed_needs_review' ? 'changed_needs_review' : inCatalog ? 'catalogued_not_reconciled' : 'needs_review',
          previous_content_hash: changed ? before.content_hash : before?.previous_content_hash || null,
          legal_effect_verified: false, rate_activation_allowed: false };
        await cache(n.document_id, content_hash, source); notices.push(record); currentIds.add(n.document_id);
      }
      // Never silently remove a previously discovered record when search stops
      // returning it. Retain it and flag the disappearance for review.
      for (const n of old?.notices || []) if (!currentIds.has(n.document_id)) notices.push({ ...n, review_status: 'missing_from_search_needs_review', rate_activation_allowed: false });
      notices.sort((a, b) => b.published.localeCompare(a.published) || a.document_id.localeCompare(b.document_id));
      state.cases[c.case_id] = { case_id: c.case_id, product: c.product, country: c.country ?? 'KOR', duty: c.duty ?? 'AD', last_attempt_at: now(), last_success_at: now(), searched_through: through, status: 'complete', error: null, notices };
    } catch (e) {
      state.cases[c.case_id] = { ...(old || { case_id: c.case_id, product: c.product, last_success_at: null, searched_through: null, notices: [] }), last_attempt_at: now(), status: 'failed_preserved', error: String(e.message).slice(0, 200) };
    }
    await persist(state);
  }
  state.requests_this_run = requests;
  if(catalog===REMEDY_MONITOR_CATALOG)state.schedule_reviews=scheduleReviews(through);
  state.status = catalog.cases.every(c => state.cases[c.case_id]?.status === 'complete' && state.cases[c.case_id]?.searched_through === through) && !fatal ? 'complete' : 'partial';
  state.completed_at = now(); await persist(state); return state;
}

async function main() {
  const args = process.argv.slice(2), allowed = new Set(['--state-dir', '--from', '--through', '--snapshot']);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--all-remedies') { opts.allRemedies = true; continue; }
    if (args[i] === '--resume') { opts.resume = true; continue; }
    if (!allowed.has(args[i]) || !args[i + 1] || args[i + 1].startsWith('--')) throw new Error('Usage: node discover_antidumping_notices.mjs --state-dir /tmp/chokemonitor-ad-review [--from YYYY-MM-DD --through YYYY-MM-DD --snapshot path.mjs --resume]');
    opts[args[i]] = args[++i];
  }
  const dir = resolve(opts['--state-dir'] || (opts.allRemedies ? '/tmp/chokemonitor-remedy-review' : '/tmp/chokemonitor-ad-review')), file = join(dir, 'state.json');
  await mkdir(dir, { recursive: true });
  try { await readFile(join(dir,'STOP')); throw new Error('STOP file present; monitor not started'); } catch(e) { if(e.code!=='ENOENT')throw e; }
  // A second process must not race the checkpoint or double the source traffic.
  const lock = join(dir, 'running.lock');
  await mkdir(lock);
  try {
    await writeFile(join(lock, 'owner.json'), JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() }));
    let previous = null;
    try { previous = JSON.parse(await readFile(file, 'utf8')); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const state = await discoverNotices({ previous, from: opts['--from'] || '2026-01-01', through: opts['--through'] || new Date().toISOString().slice(0, 10),
      catalog: opts.allRemedies ? REMEDY_MONITOR_CATALOG : AD_CATALOG, resumeIncomplete: Boolean(opts.resume), persist: s => atomicJSON(file, s), cache: async (id, hash, source) => writeFile(join(dir, `${id}-${hash}.html`), source) });
    if (opts['--snapshot']) {
      const output = resolve(opts['--snapshot']);
      if (!output.endsWith(opts.allRemedies ? 'remedy-discovery-snapshot.mjs' : 'antidumping-discovery-snapshot.mjs')) throw new Error('Snapshot output must be antidumping-discovery-snapshot.mjs');
      await writeFile(`${output}.tmp`, '// Generated discovery evidence only. Never a rate/stage input.\nexport const ' + (opts.allRemedies ? 'REMEDY_DISCOVERY' : 'AD_DISCOVERY') + ' = ' + JSON.stringify(state, null, 2) + ';\n');
      await rename(`${output}.tmp`, output);
    }
    console.log(JSON.stringify({ status: state.status, requests: state.requests_this_run, cases: Object.values(state.cases).map(c => ({ case_id: c.case_id, status: c.status, notices: c.notices.length, pending: c.notices.filter(n => n.review_status !== 'catalogued_not_reconciled').length, error: c.error })) }));
    if (state.status !== 'complete') process.exitCode = 1;
  } finally { const { rm } = await import('node:fs/promises'); await rm(lock, { recursive: true }); }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
