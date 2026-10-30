'use strict';
const fs = require('node:fs/promises'), path = require('node:path');
const { plain, hash, officialUrl, citations, buildDocument } = require('./policy-search-document');
const { supabaseGet, createRequestGate, requireEnv } = require('./sync-utils');
const SOURCES = {
  bill: { table: 'bills', key: 'bill_id', select: 'bill_id,title,summary,congress_number,bill_type,bill_number,congress_url,latest_action_date,source_updated_at,policy_area_id' },
  public_law: { table: 'public_laws', key: 'public_law_id', select: 'public_law_id,law_title,enacted_date,govinfo_url,official_text_url,source_package_id,source_updated_at,bill_id' },
  executive_order: { table: 'executive_orders', key: 'eo_number', select: 'eo_number,title,summary,signed_date,publication_date,federal_register_url,executive_order_url,document_number,source_updated_at' },
  regulation: { table: 'regulations', key: 'regulation_id', select: 'regulation_id,title,abstract,publication_date,federal_register_url,document_number,source_updated_at' },
};
function publicTextUrl(url) {
  url = officialUrl(url); if (!url) return null;
  const u = new URL(url);
  const granule = u.pathname.match(/^\/packages\/([^/]+)\/granules\/([^/]+)\/(htm|txt)$/);
  if (u.hostname === 'api.govinfo.gov' && granule) return `https://www.govinfo.gov/content/pkg/${granule[1]}/${granule[3] === 'htm' ? 'html' : 'text'}/${granule[2]}.${granule[3] === 'htm' ? 'htm' : 'txt'}`;
  const bill = u.pathname.match(/(BILLS-[\w-]+)\.(?:xml|htm|html|txt)$/i);
  if (bill) return `https://www.govinfo.gov/content/pkg/${bill[1]}/html/${bill[1]}.htm`;
  return url;
}
function publicLawPackage(id) {
  const match = String(id).match(/^(\d{2,3})-public-(\d{1,4})$/);
  return match ? `PLAW-${Number(match[1])}publ${Number(match[2])}` : null;
}
function sourceLoader(options = {}) {
  const root = options.cacheDir || process.env.POLICY_SEARCH_CACHE_DIR;
  if (!root) throw new Error('POLICY_SEARCH_CACHE_DIR is required (private, outside git)');
  const gate = createRequestGate(1200);
  const get = options.get || supabaseGet, fetchSource = options.fetch || fetch;
  const requestGate = options.gate || gate;
  const request = async (url, version = '') => {
    const clean = officialUrl(url); if (!clean) throw new Error('Unsupported official source URL');
    const file = path.join(root, hash(`${clean}|${version}`) + '.json');
    try {
      const cached = JSON.parse(await fs.readFile(file, 'utf8'));
      // An empty official text listing is a temporary observation. It must
      // expire even when Congress hasn't changed the source row's revision.
      const unavailable = (Array.isArray(cached.textVersions) && !cached.textVersions.length) || cached.text === '';
      if (!unavailable || Date.now() - (await fs.stat(file)).mtimeMs < 86400000) return cached;
    } catch (e) { if (e.code !== 'ENOENT') throw e; }
    return requestGate(async () => {
      const u = new URL(url);
      if (u.hostname === 'api.congress.gov') u.searchParams.set('api_key', requireEnv('CONGRESS_API_KEY'));
      if (u.hostname === 'api.govinfo.gov') u.searchParams.set('api_key', process.env.GOVINFO_API_KEY || requireEnv('DATA_GOV_API_KEY'));
      const response = await fetchSource(u, { signal: AbortSignal.timeout(35000), redirect: 'manual', headers: { 'User-Agent': 'ChokeMonitor-policy-index/1.0' } });
      if ([301,302,303,307,308].includes(response.status)) {
        // GovInfo routes unpublished content to /error rather than returning
        // a 404. Do not index that HTML page or forward API credentials.
        let target; try { target = new URL(response.headers.get('location'), u); } catch {}
        const unavailable = u.hostname === 'www.govinfo.gov' && target?.origin === u.origin && target.pathname === '/error';
        const error = new Error(unavailable ? 'Official text unavailable (GovInfo error page)' : 'Official source redirect requires review');
        error.status = response.status; error.sourceUnavailable = unavailable; throw error;
      }
      if (!response.ok) { const error = new Error(`Official source HTTP ${response.status}`); error.status = response.status; throw error; }
      const reader = response.body.getReader(); const buffers = []; let bytes = 0;
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        bytes += value.length; if (bytes > 5_000_000) { await reader.cancel(); throw new Error('Official source exceeds 5MB text limit'); }
        buffers.push(Buffer.from(value));
      }
      const raw = Buffer.concat(buffers).toString('utf8');
      const result = (response.headers.get('content-type') || '').includes('json') ? JSON.parse(raw) : { text: plain(raw), source_url: clean };
      await fs.mkdir(root, { recursive: true, mode: 0o700 });
      const tmp = `${file}.${process.pid}.tmp`; await fs.writeFile(tmp, JSON.stringify(result), { mode: 0o600 }); await fs.rename(tmp, file);
      return result;
    });
  };
  async function load(type, id) {
    const config = SOURCES[type]; if (!config) throw new Error('Unsupported policy source type');
    const row = (await get(config.table, { select: config.select, [config.key]: `eq.${id}`, limit: '1' }))?.[0];
    if (!row) throw new Error('Source document no longer exists');
    const base = { type, id: String(id), title: row.title || row.law_title, summary: row.summary || row.abstract,
      date: row.latest_action_date || row.enacted_date || row.publication_date || row.signed_date,
      sourceUrl: row.congress_url || row.govinfo_url || row.federal_register_url, sourceVersion: row.source_updated_at,
      subjects: [], bodyStatus: 'unavailable' };
    let textUrl;
    if (type === 'bill') {
      const subjects = await get('bill_subjects', { select: 'legislative_subjects(name)', bill_id: `eq.${id}` });
      base.subjects = subjects.map(s => s.legislative_subjects?.name).filter(Boolean);
      if (row.policy_area_id) {
        const area = (await get('policy_areas', { select: 'name', policy_area_id: `eq.${row.policy_area_id}`, limit: '1' }))?.[0];
        if (area?.name) base.subjects.push(area.name);
      }
      let versions = await get('bill_text_versions', { select: 'issued_on,html_url,formatted_text_url,xml_url', bill_id: `eq.${id}`, order: 'issued_on.desc.nullslast,bill_text_version_id.desc', limit: '1' });
      // Existing DB versions can lag behind a bill's latest source update.
      // Revalidate the official listing once per source revision; cached
      // listing/body reads avoid repeated network calls for an unchanged bill.
      const listing = await request(`https://api.congress.gov/v3/bill/${row.congress_number}/${row.bill_type}/${row.bill_number}/text?format=json&limit=250`, base.sourceVersion);
      const officialVersions = (listing.textVersions || []).sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
      if (officialVersions.length) versions=officialVersions;
      const version = versions[0];
      textUrl = version?.html_url || version?.formatted_text_url || version?.xml_url ||
        version?.formats?.find(f => /formatted|html|xml/i.test(f.type))?.url;
    } else if (type === 'public_law') {
      // Congress can announce an enacted law before its GovInfo identifiers
      // reach the source row. Try the canonical package's official text;
      // a 404 remains unavailable, never substituted with a bill's text.
      const packageId = row.source_package_id || publicLawPackage(id);
      textUrl = row.official_text_url || (packageId ? `https://www.govinfo.gov/content/pkg/${packageId}/text/${packageId}.txt` : null);
      if (row.bill_id) {
        const bill = (await get('bills', { select: 'summary,congress_url', bill_id: `eq.${row.bill_id}`, limit: '1' }))?.[0];
        // The linked official bill page is provenance for law metadata and
        // CRS summary only, not evidence that the enrolled law text exists.
        base.sourceUrl = base.sourceUrl || officialUrl(bill?.congress_url);
        if (bill?.summary) { base.summary = bill.summary; base.summaryUrl = bill.congress_url; }
      }
    } else if (type === 'executive_order') {
      const eoRoot = process.env.EO_OFFICIAL_TEXT_CACHE_DIR;
      if (eoRoot && row.document_number) {
        try {
          const record = JSON.parse(await fs.readFile(path.join(eoRoot, path.basename(row.document_number) + '.json'), 'utf8'));
          if (Number(record.eo_number) === Number(id) && officialUrl(record.official_url) && record.text) {
            base.body = record.text; base.bodyUrl = publicTextUrl(record.official_url); base.bodyStatus = 'body';
          }
        } catch (e) { if (e.code !== 'ENOENT') throw e; }
      }
      textUrl = row.publication_date && row.document_number ? `https://www.govinfo.gov/content/pkg/FR-${row.publication_date}/html/${row.document_number}.htm` : row.executive_order_url;
    } else if (row.publication_date) textUrl = `https://www.govinfo.gov/content/pkg/FR-${row.publication_date}/html/${row.document_number}.htm`;
    if (!base.body && textUrl) {
      try {
        const result = await request(publicTextUrl(textUrl), base.sourceVersion);
        base.body = result.text; base.bodyUrl = publicTextUrl(textUrl); base.bodyStatus = base.body ? 'body' : 'unavailable';
      } catch (e) { if (![404,410].includes(e.status) && !e.sourceUnavailable) throw e; base.bodyStatus = 'unavailable'; }
    }
    return base;
  }
  async function document(type, id) {
    const base = await load(type, id);
    const references = citations(base.body).filter(r => !(r.target_type === type && r.target_id === String(id)));
    const contexts = [];
    for (const ref of [...references].sort((a,b)=>(a.target_type==='executive_order'?-1:0)-(b.target_type==='executive_order'?-1:0)).slice(0, 8)) {
      try {
        const target = await load(ref.target_type, ref.target_id);
        contexts.push({ ...ref, text: `${target.title}\n${target.summary || ''}\n${plain(target.body).slice(0, 7000)}`,
          source_url: target.bodyUrl || target.sourceUrl, citation_url: base.bodyUrl || base.sourceUrl });
      } catch (e) {
        if ([403,429].includes(e.status)) throw e;
        // Missing citations stay explicit but unresolved. They never invent text.
        console.warn(`Unresolved citation ${ref.target_type}:${ref.target_id}: ${e.status || e.name}`);
      }
    }
    return buildDocument({ ...base, references, contexts });
  }
  return { load, document };
}
module.exports = { SOURCES, publicTextUrl, publicLawPackage, sourceLoader };
