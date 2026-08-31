'use strict';

// Federal Register only. No eCFR sync: cfr_titles is a static schema seed.
const {
  asArray, checkpointSyncState, fetchJson, finishSyncRun, firstNonEmpty, mapWithConcurrency,
  geminiEmbeddings, geminiModelName, isOptionalEmbeddingError, parseDateOnly, parseTimestamp, requireEnv, slug, startSyncRun,
  supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch, supabaseRpc, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');
const { classifyFederalAgency, federalRegisterParentId } = require('./lib/federal-agency-classifier');
const { publicLawBillLink, reconcilePublicLawAuthorityLinks } = require('./lib/public-law-links');

const API_BASE = 'https://www.federalregister.gov/api/v1';
const RESOURCE = 'federalregister.gov:documents';
const MAX_DOCUMENTS = Number(process.env.MAX_FR_DOCUMENTS || 50);
const CONCURRENCY = Number(process.env.FR_DETAIL_CONCURRENCY || 4);
const SKIP_EMBEDDINGS = process.env.SKIP_EMBEDDINGS === 'true';
const MAX_EMBEDDINGS = Number(process.env.MAX_EMBEDDINGS || 25);

requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');
let subscriptions;

function url(path, query = {}) { return `${API_BASE}${path}?${new URLSearchParams(query)}`; }
async function get(path, query = {}, optional = false) {
  try { return await fetchJson(url(path, query), {}, { label: `Federal Register ${path}`, maxRetries: 6 }); }
  catch (error) { if (optional && /HTTP 404/.test(error.message)) return null; throw error; }
}
function currentWindow(state) {
  if (state?.cursor?.window_from && state.cursor?.mode === 'incremental') return state.cursor.window_from;
  if (process.env.FR_FROM_DATE) return process.env.FR_FROM_DATE;
  const date = state?.last_successful_at ? new Date(state.last_successful_at) : new Date(Date.now() - 7 * 86_400_000);
  date.setUTCDate(date.getUTCDate() - 1); // date-level API filter gets a one-day overlap
  return date.toISOString().slice(0, 10);
}
function agencyRow(agency, parentAgencyId = null) {
  const name = firstNonEmpty(agency?.name, agency?.raw_name, agency?.short_name);
  const sourceId = firstNonEmpty(agency?.slug, agency?.id, slug(name));
  if (!name || !sourceId) return null;
  const parentId = federalRegisterParentId(agency);
  const row = {
    agency_id: `fr-${sourceId}`,
    name,
    short_name: agency.short_name || null,
    federal_register_id: Number(agency.id) || null,
    agency_type: classifyFederalAgency(agency),
    agency_url: agency.url || null,
    raw_source: agency,
  };
  // Do not overwrite a known parent with null when a child arrives before its
  // parent. The database refresh function resolves it once the parent exists.
  if (!parentId || parentAgencyId) row.parent_agency_id = parentAgencyId || null;
  return row;
}
function textFor(document) { return firstNonEmpty(document.abstract, document.summary, document.action); }
function eoNumber(document) {
  const direct = firstNonEmpty(document.executive_order_number, document.executiveOrderNumber);
  const titleMatch = String(document.title || '').match(/^executive order\s+(\d+)/i);
  const value = Number(firstNonEmpty(direct, titleMatch?.[1]));
  return Number.isInteger(value) ? value : null;
}
function isExecutiveOrder(document) {
  // Federal Register exposes executive_order_number on EO documents even when
  // the title does not start with “Executive Order”.
  return Boolean(eoNumber(document));
}
function cfrReferences(document) {
  const rows = [];
  for (const reference of asArray(document.cfr_references)) {
    const title = Number(firstNonEmpty(reference?.title, reference?.title_number, typeof reference === 'string' && reference.match(/(?:^|\s)(\d{1,2})\s*CFR/i)?.[1]));
    const part = firstNonEmpty(reference?.part, reference?.part_number, typeof reference === 'string' && reference.match(/part\s+([\w.-]+)/i)?.[1]);
    if (Number.isInteger(title) && title >= 1 && title <= 50) rows.push({ title_number: title, part_number: part ? String(part) : null });
  }
  return [...new Map(rows.map((row) => [`${row.title_number}:${row.part_number || ''}`, row])).values()];
}
function officialEoAuthority(document) {
  // Only structured source metadata is used. Abstract/body text is never mined for legal authority.
  return asArray(firstNonEmpty(document.legal_authorities, document.legal_authority)).filter((item) => item?.citation && item?.authority_type);
}

async function loadState() {
  return (await supabaseGet('data_sync_state', { select: 'cursor,last_successful_at', sync_resource: `eq.${RESOURCE}`, limit: '1' }))?.[0] || null;
}
// A single 1,000-item page silently dropped any window with more matching
// documents than that (rare, but possible on a busy Federal Register day or
// after a missed run). Page through up to MAX_DISCOVERY_PAGES per type
// instead of assuming page 1 is everything.
const MAX_DISCOVERY_PAGES = Number(process.env.MAX_DISCOVERY_PAGES || 5);

async function loadCandidates(windowFrom) {
  const types = ['PRESDOCU', 'RULE', 'PRORULE'];
  const all = [];
  for (const type of types) {
    for (let page = 1; page <= MAX_DISCOVERY_PAGES; page += 1) {
      const body = await get('/documents.json', {
        'conditions[type][]': type, 'conditions[publication_date][gte]': windowFrom,
        per_page: 1_000, page, order: 'newest',
      });
      const pageItems = asArray(body?.results);
      all.push(...pageItems);
      if (pageItems.length < 1_000 || page >= Number(body?.total_pages || 1)) break;
    }
  }
  return [...new Map(all.map((item) => [item.document_number, item])).values()];
}
async function documentBundle(item) {
  const detail = await get(`/documents/${encodeURIComponent(item.document_number)}.json`, {}, true) || {};
  return { item, document: { ...item, ...detail } };
}

async function saveAgencies(agencies) {
  const raw = asArray(agencies);
  const localAgencyIds = new Map(raw.map((agency) => {
    const name = firstNonEmpty(agency?.name, agency?.raw_name, agency?.short_name);
    const sourceId = firstNonEmpty(agency?.slug, agency?.id, slug(name));
    return [Number(agency?.id), name && sourceId ? `fr-${sourceId}` : null];
  }).filter(([id, agencyId]) => Number.isInteger(id) && id > 0 && agencyId));
  const parentIds = [...new Set(raw.map(federalRegisterParentId).filter(Boolean))];
  const knownParents = parentIds.length
    ? await supabaseGet('agencies', {
      select: 'agency_id,federal_register_id',
      federal_register_id: `in.(${parentIds.join(',')})`,
    })
    : [];
  const parentAgencyIds = new Map(knownParents.map((row) => [Number(row.federal_register_id), row.agency_id]));
  const rows = raw.map((agency) => agencyRow(
    agency,
    localAgencyIds.get(federalRegisterParentId(agency)) || parentAgencyIds.get(federalRegisterParentId(agency)) || null,
  )).filter(Boolean);
  if (rows.length) await supabaseUpsert('agencies', rows, 'agency_id');
  return rows.map((row) => row.agency_id);
}

async function saveExecutiveOrder(item, document) {
  if (!isExecutiveOrder(document)) return null;
  const number = eoNumber(document); const agencyIds = await saveAgencies(asArray(document.agencies));
  const row = {
    eo_number: number, document_number: document.document_number, title: firstNonEmpty(document.title, `Executive Order ${number}`),
    president_name: firstNonEmpty(document.president?.name, document.president_name), signed_date: parseDateOnly(firstNonEmpty(document.signing_date, document.presidential_document_date)),
    publication_date: parseDateOnly(document.publication_date), citation: firstNonEmpty(document.citation, document.citation_string),
    federal_register_url: firstNonEmpty(document.html_url, item.html_url, `https://www.federalregister.gov/d/${document.document_number}`),
    pdf_url: firstNonEmpty(document.pdf_url, item.pdf_url), executive_order_url: firstNonEmpty(document.raw_text_url, document.body_html_url),
    summary: textFor(document), summary_source: document.abstract ? 'Federal Register abstract' : document.summary ? 'Federal Register summary' : null,
    source_updated_at: parseTimestamp(firstNonEmpty(document.last_modified, document.publication_date)), last_synced_at: new Date().toISOString(),
    raw_source: { source: 'federalregister.gov', document_number: document.document_number, api_url: `${API_BASE}/documents/${document.document_number}.json` },
  };
  const previous = (await supabaseGet('executive_orders', { select: 'title,summary,embedding', eo_number: `eq.${number}`, limit: '1' }))?.[0];
  await supabaseUpsert('executive_orders', [row], 'eo_number');
  for (const agencyId of agencyIds) await supabaseInsertIgnore('executive_order_agencies', { eo_number: number, agency_id: agencyId }, 'eo_number,agency_id');
  await saveAuthorities(number, document);
  await queue('eo_number', number, `${row.title}\n${row.summary || ''}`, {
    agency: agencyIds[0] || null,
    executive_order: String(number),
  });
  return { number, row, embed: !previous || !previous.embedding || previous.title !== row.title || previous.summary !== row.summary };
}

async function saveAuthorities(eoNumberValue, document) {
  const publicLawCache = new Map();
  for (const authority of officialEoAuthority(document)) {
    // This branch is intentionally conservative; most FR EO records provide no structured authority field.
    const type = String(authority.authority_type).toLowerCase();
    if (!['constitution', 'usc', 'public_law', 'statutes_at_large', 'executive_order', 'regulation', 'other'].includes(type)) continue;
    // Only an explicit Public Law citation can be connected to a single bill.
    // U.S.C. and other authority types deliberately remain external links.
    const link = type === 'public_law' ? await publicLawBillLink(authority.citation, publicLawCache) : null;
    const existing = await supabaseGet('legal_authorities', { select: 'legal_authority_id,linked_bill_id', authority_type: `eq.${type}`, citation: `eq.${authority.citation}`, limit: '1' });
    let id = existing?.[0]?.legal_authority_id;
    if (!id) {
      const inserted = await supabaseInsert('legal_authorities', [{ authority_type: type, citation: authority.citation,
        title: authority.title || null, official_url: authority.official_url || null,
        linked_bill_id: link?.billId || null, extraction_method: 'official_metadata', verified_at: new Date().toISOString() }],
      'return=representation');
      id = inserted?.[0]?.legal_authority_id;
    } else if (link?.billId && existing[0].linked_bill_id !== link.billId) {
      await supabasePatch('legal_authorities', `legal_authority_id=eq.${id}`, { linked_bill_id: link.billId });
    }
    if (id) await supabaseInsertIgnore('executive_order_authorities', { eo_number: eoNumberValue, legal_authority_id: id, source_url: document.html_url }, 'eo_number,legal_authority_id');
  }
}

async function saveRegulation(item, document) {
  const type = String(document.type || item.type || 'OTHER').toUpperCase();
  if (!['RULE', 'PRORULE'].includes(type)) return null;
  const regulationId = String(document.document_number || item.document_number); const agencyIds = await saveAgencies(asArray(document.agencies));
  const row = {
    regulation_id: regulationId, document_number: regulationId, document_type: type,
    title: firstNonEmpty(document.title, item.title, regulationId), abstract: document.abstract || null, action_text: document.action || null,
    publication_date: parseDateOnly(document.publication_date), effective_on: parseDateOnly(document.effective_on), comments_close_on: parseDateOnly(document.comments_close_on),
    federal_register_url: firstNonEmpty(document.html_url, item.html_url, `https://www.federalregister.gov/d/${regulationId}`), pdf_url: firstNonEmpty(document.pdf_url, item.pdf_url),
    docket_ids: asArray(firstNonEmpty(document.docket_ids, document.docket_numbers)).filter(Boolean).map(String),
    rin: asArray(document.regulation_id_numbers).find((value) => /\d{4}-[A-Z]{2}\d{4}/i.test(String(value))) || null,
    citation: firstNonEmpty(document.citation, document.citation_string), source_updated_at: parseTimestamp(firstNonEmpty(document.last_modified, document.publication_date)),
    last_synced_at: new Date().toISOString(),
    raw_source: { source: 'federalregister.gov', document_number: regulationId, api_url: `${API_BASE}/documents/${regulationId}.json` },
  };
  const previous = (await supabaseGet('regulations', { select: 'title,abstract,embedding', regulation_id: `eq.${encodeURIComponent(regulationId)}`, limit: '1' }))?.[0];
  await supabaseUpsert('regulations', [row], 'regulation_id');
  for (const agencyId of agencyIds) await supabaseInsertIgnore('regulation_agencies', { regulation_id: regulationId, agency_id: agencyId }, 'regulation_id,agency_id');
  for (const cfr of cfrReferences(document)) {
    const existing = await supabaseGet('regulation_cfr_references', { select: 'regulation_cfr_reference_id', regulation_id: `eq.${regulationId}`,
      title_number: `eq.${cfr.title_number}`, part_number: cfr.part_number ? `eq.${encodeURIComponent(cfr.part_number)}` : 'is.null', limit: '1' });
    if (!existing?.length) await supabaseInsert('regulation_cfr_references', { regulation_id: regulationId, ...cfr });
  }
  await saveOfficialEoLinks(document, regulationId);
  await queue('regulation_id', regulationId, `${row.title}\n${row.abstract || ''}`, { agency: agencyIds[0] || null, cfr_title: String(cfrReferences(document)[0]?.title_number || '') });
  return { regulationId, row, embed: !previous || !previous.embedding || previous.title !== row.title || previous.abstract !== row.abstract };
}

async function saveOfficialEoLinks(document, regulationId) {
  // Relations are created only from an explicit machine-readable EO number, not a keyword/LLM guess.
  const values = asArray(firstNonEmpty(document.executive_order_numbers, document.executive_order_number));
  for (const value of values) {
    const eo = Number(value); if (!Number.isInteger(eo)) continue;
    const exists = await supabaseGet('executive_orders', { select: 'eo_number', eo_number: `eq.${eo}`, limit: '1' });
    if (exists?.length) await supabaseInsertIgnore('executive_order_regulations', {
      eo_number: eo, regulation_id: regulationId, relation_type: 'source_metadata', relation_origin: 'official_citation', source_url: document.html_url,
    }, 'eo_number,regulation_id,relation_type,relation_origin');
  }
}

async function queue(column, value, text, categories) {
  if (!subscriptions) subscriptions = await supabaseGet('subscriptions', { select: 'subscription_id,keyword,category_type,category_id', active: 'eq.true' });
  const source = String(text || '').toLowerCase();
  for (const subscription of subscriptions) {
    if ((subscription.keyword && source.includes(subscription.keyword.toLowerCase())) ||
      (subscription.category_type && categories[subscription.category_type] === subscription.category_id)) {
      const existing = await supabaseGet('notifications_queued', { select: 'notification_id', subscription_id: `eq.${subscription.subscription_id}`, [column]: `eq.${encodeURIComponent(value)}`, limit: '1' });
      if (!existing?.length) await supabaseInsert('notifications_queued', { subscription_id: subscription.subscription_id, [column]: value });
    }
  }
}

async function embed(table, keyColumn, rows, content) {
  if (SKIP_EMBEDDINGS || !rows.length) return 0;
  try {
    const selected = rows.slice(0, MAX_EMBEDDINGS);
    const key = requireEnv('GEMINI_API_KEY');
    for (let start = 0; start < selected.length; start += 50) {
      const group = selected.slice(start, start + 50); const vectors = await geminiEmbeddings(group.map(content), key);
      for (let index = 0; index < group.length; index += 1) await supabasePatch(table, `${keyColumn}=eq.${encodeURIComponent(group[index][keyColumn])}`, {
        embedding: vectors[index], embedding_model: geminiModelName(), embedded_at: new Date().toISOString(),
      });
    }
    if (rows.length > selected.length) console.warn(`Embedding cap reached: ${rows.length - selected.length} ${table} embeddings deferred.`);
    return selected.length;
  } catch (error) {
    if (isOptionalEmbeddingError(error)) {
      console.warn(`${table} embeddings skipped: ${error.message}`);
      return 0;
    }
    throw error;
  }
}

async function run() {
  const state = await loadState(); const windowFrom = currentWindow(state);
  const runId = await startSyncRun(RESOURCE, { window_from: windowFrom, max_documents: MAX_DOCUMENTS });
  let read = 0; let written = 0;
  try {
    const candidates = await loadCandidates(windowFrom); const completed = new Set(state?.cursor?.window_from === windowFrom ? state.cursor.processed_document_numbers || [] : []);
    const pending = candidates.filter((item) => !completed.has(item.document_number));
    const batch = pending.slice(0, MAX_DOCUMENTS); read = batch.length;
    console.log(`Federal Register: ${pending.length} pending documents since ${windowFrom}; processing ${read}.`);
    const bundles = await mapWithConcurrency(batch, CONCURRENCY, documentBundle); const eos = []; const regulations = [];
    for (const { item, document } of bundles) {
      const eo = await saveExecutiveOrder(item, document); const regulation = await saveRegulation(item, document);
      if (eo) eos.push(eo); if (regulation) regulations.push(regulation); written += Number(Boolean(eo || regulation));
      completed.add(item.document_number);
      await checkpointSyncState(RESOURCE, { mode: 'incremental', window_from: windowFrom, processed_document_numbers: [...completed] });
    }
    const classifiedAgencies = await supabaseRpc('refresh_federal_register_agency_classification');
    const authorityLinks = await reconcilePublicLawAuthorityLinks();
    const embedded = (await embed('executive_orders', 'eo_number', eos.filter((item) => item.embed).map((item) => ({ ...item.row, eo_number: item.number })), (row) => `${row.title}\n\n${row.summary || ''}`))
      + (await embed('regulations', 'regulation_id', regulations.filter((item) => item.embed).map((item) => ({ ...item.row, regulation_id: item.regulationId })), (row) => `${row.title}\n\n${row.abstract || ''}`));
    const newestBill = await supabaseGet('bills', { select: 'congress_number', order: 'congress_number.desc', limit: '1' });
    const active = Number(process.env.CONGRESS_NUMBER || newestBill?.[0]?.congress_number || 119);
    await supabaseRpc('refresh_policy_lifecycle_tiers', { active_congress_number: active });
    const remaining = pending.length - batch.length;
    if (remaining > 0) {
      await checkpointSyncState(RESOURCE, { mode: 'incremental', window_from: windowFrom, processed_document_numbers: [...completed] });
    } else {
      await updateSyncState(RESOURCE, { mode: 'incremental', completed_at: new Date().toISOString() });
    }
    await finishSyncRun(runId, { status: remaining > 0 ? 'partial' : 'succeeded', records_read: read, records_written: written, metadata: { window_from: windowFrom, embedded, remaining, classified_agencies: Number(classifiedAgencies) || 0, public_law_authority_links: authorityLinks } });
    console.log(`Federal Register complete: ${written} records, ${embedded} embeddings, ${remaining} deferred. Public Law authority links: ${authorityLinks.linked}/${authorityLinks.total} linked; ${authorityLinks.updated} updated.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: read, records_written: written, error_summary: error.message });
    throw error;
  }
}
run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
