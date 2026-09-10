'use strict';

// Federal Register only. No eCFR sync: cfr_titles is a static schema seed.
const {
  asArray, checkpointSyncState, fetchJson, finishSyncRun, firstNonEmpty, mapWithConcurrency,
  geminiEmbeddings, geminiModelName, isOptionalEmbeddingError, parseDateOnly, parseTimestamp, requireEnv, slug, startSyncRun,
  supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch, supabaseRpc, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');
const { classifyFederalAgency, federalRegisterParentId } = require('./lib/federal-agency-classifier');
const { reconcilePublicLawAuthorityLinks } = require('./lib/public-law-links');
const { saveOfficialEoTextRelations } = require('./lib/eo-official-relations');

const API_BASE = 'https://www.federalregister.gov/api/v1';
const EO_BACKFILL = process.env.EO_BACKFILL === 'true';
const EO_RELATION_BACKFILL = process.env.EO_RELATION_BACKFILL === 'true';
if (EO_BACKFILL && EO_RELATION_BACKFILL) throw new Error('EO_BACKFILL and EO_RELATION_BACKFILL cannot run together.');
const RESOURCE = EO_RELATION_BACKFILL
  ? 'federalregister.gov:eo-relationships:bootstrap'
  : EO_BACKFILL ? 'federalregister.gov:executive-orders:bootstrap' : 'federalregister.gov:documents';
const MAX_DOCUMENTS = Number(process.env.MAX_FR_DOCUMENTS || (EO_BACKFILL ? 100 : EO_RELATION_BACKFILL ? 25 : 50));
// EO 관계의 역사 백필은 Federal Register 상세 문서를 많이 읽는다. 기본값을
// 단일 요청으로 낮춰 공공 API의 자동 차단을 피한다. 일반 일일 동기화는 기존 4개를 유지한다.
const CONCURRENCY = Number(process.env.FR_DETAIL_CONCURRENCY || (EO_RELATION_BACKFILL ? 1 : 4));
// Historical EO metadata is useful without embeddings. Make Gemini opt-in for
// the historical pass so a 1994+ backfill does not unexpectedly consume quota.
const SKIP_EMBEDDINGS = process.env.SKIP_EMBEDDINGS === 'true'
  || EO_RELATION_BACKFILL
  || (EO_BACKFILL && process.env.EO_BACKFILL_EMBEDDINGS !== 'true');
const MAX_EMBEDDINGS = Number(process.env.MAX_EMBEDDINGS || 25);
const EO_BACKFILL_FROM_DATE = process.env.EO_BACKFILL_FROM_DATE || '1994-01-01';
const EO_BACKFILL_TO_DATE = process.env.EO_BACKFILL_TO_DATE || new Date().toISOString().slice(0, 10);
const EO_BACKFILL_PAGE_SIZE = Math.min(1_000, positiveInteger(process.env.EO_BACKFILL_PAGE_SIZE, 500));
// 관계 백필은 한 EO의 후보 문서가 많을 수 있으므로, 기본 페이지도 작게 유지한다.
const EO_RELATION_PAGE_SIZE = Math.min(100, positiveInteger(process.env.MAX_EO_RELATION_DOCUMENTS, 5));
const EO_RELATION_DETAIL_DELAY_MS = Math.min(60_000, positiveInteger(process.env.EO_RELATION_DETAIL_DELAY_MS, 1_000));
// A local backfill should make meaningful progress without requiring hundreds
// of manual restarts. Each finished page is checkpointed independently, so a
// bounded multi-page run remains safe to resume after an interruption.
const EO_RELATION_MAX_PAGES_PER_RUN = positiveInteger(process.env.MAX_EO_RELATION_PAGES, 25);
const EO_RELATION_MAX_RUNTIME_MS = positiveInteger(process.env.MAX_EO_RELATION_RUNTIME_MS, 10 * 60_000);

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
function isIsoDate(value) { return /^\d{4}-\d{2}-\d{2}$/.test(String(value || '')); }
function positiveInteger(value, fallback = 1) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
function eoBackfillCursor(state) {
  const cursor = state?.cursor || {};
  const sameRange = cursor.mode === 'eo_backfill'
    && cursor.from_date === EO_BACKFILL_FROM_DATE
    && cursor.to_date === EO_BACKFILL_TO_DATE;
  return sameRange ? cursor : { mode: 'eo_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE, page: 1 };
}
function eoRelationCursor(state) {
  const cursor = state?.cursor || {};
  const sameRange = cursor.mode === 'eo_relation_backfill'
    && cursor.from_date === EO_BACKFILL_FROM_DATE
    && cursor.to_date === EO_BACKFILL_TO_DATE;
  return sameRange
    ? cursor
    : {
      mode: 'eo_relation_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE,
      after_eo_number: 0, page: 1,
    };
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
async function loadEoBackfillCandidates(state) {
  if (!isIsoDate(EO_BACKFILL_FROM_DATE) || !isIsoDate(EO_BACKFILL_TO_DATE)) {
    throw new Error('EO_BACKFILL_FROM_DATE and EO_BACKFILL_TO_DATE must be YYYY-MM-DD');
  }
  const cursor = eoBackfillCursor(state);
  const page = positiveInteger(cursor.page);
  const body = await get('/documents.json', {
    'conditions[type][]': 'PRESDOCU',
    'conditions[presidential_document_type][]': 'executive_order',
    'conditions[publication_date][gte]': EO_BACKFILL_FROM_DATE,
    'conditions[publication_date][lte]': EO_BACKFILL_TO_DATE,
    per_page: EO_BACKFILL_PAGE_SIZE,
    page,
    order: 'oldest',
  });
  return {
    candidates: asArray(body?.results),
    cursor: {
      mode: 'eo_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE,
      page, total_pages: positiveInteger(body?.total_pages), processed_document_numbers: cursor.processed_document_numbers || [],
    },
  };
}

async function nextEoRelationTarget(cursor) {
  return (await supabaseGet('executive_orders', {
    select: 'eo_number,document_number', eo_number: `gt.${Number(cursor.after_eo_number) || 0}`,
    and: `(publication_date.gte.${EO_BACKFILL_FROM_DATE},publication_date.lte.${EO_BACKFILL_TO_DATE})`,
    order: 'eo_number.asc', limit: '1',
  }))?.[0] || null;
}

async function loadEoRelationCandidates(target, page) {
  const body = await get('/documents.json', {
    // The detail response below enforces RULE/PRORULE and an exact machine
    // readable EO number. Do not rely on a comma-joined type query here:
    // URLSearchParams would serialize it as one unsupported filter value.
    'conditions[term]': `Executive Order ${target.eo_number}`,
    per_page: EO_RELATION_PAGE_SIZE, page, order: 'oldest',
  });
  return { candidates: asArray(body?.results), totalPages: positiveInteger(body?.total_pages) };
}
async function documentBundle(item) {
  const detail = await get(`/documents/${encodeURIComponent(item.document_number)}.json`, {}, true) || {};
  return { item, document: { ...item, ...detail } };
}

function isFederalRegisterIpBlock(error) {
  return /HTTP 403[\s\S]*IP address has been blocked/i.test(String(error?.message || ''));
}

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function relationDocumentBundle(item) {
  try {
    // 관계 백필은 직렬 요청과 짧은 간격을 기본으로 해 Federal Register에 부담을 주지 않는다.
    await pause(EO_RELATION_DETAIL_DELAY_MS);
    return await documentBundle(item);
  } catch (error) {
    // IP 차단은 개별 문서 오류가 아니다. 이 예외를 페이지까지 전파해 체크포인트를
    // 그대로 보존하고, 차단이 풀린 뒤 같은 페이지부터 다시 시도하게 한다.
    if (isFederalRegisterIpBlock(error)) {
      throw new Error('Federal Register IP blocked (HTTP 403). Backfill stopped without advancing its checkpoint; wait before retrying.');
    }
    // A transient failure for one candidate must not discard the page's other
    // verified links or prevent its checkpoint from advancing.
    console.warn(`EO relationship backfill: skipped Federal Register document ${item.document_number}: ${error.message}`);
    return null;
  }
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

async function saveEoAgencyLinks(eoNumberValue, agencyIds, relationshipType, relationOrigin, sourceUrl) {
  for (const agencyId of agencyIds) await supabaseInsertIgnore('executive_order_agencies', {
    eo_number: eoNumberValue, agency_id: agencyId,
    relationship_type: relationshipType, relation_origin: relationOrigin, source_url: sourceUrl || null,
  }, 'eo_number,agency_id,relationship_type,relation_origin');
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
  await saveEoAgencyLinks(number, agencyIds, 'issuing_document', 'official_document_metadata', document.html_url);
  await saveOfficialEoTextRelations(number, document);
  await queue('eo_number', number, `${row.title}\n${row.summary || ''}`, {
    agency: agencyIds[0] || null,
    executive_order: String(number),
  });
  return { number, row, embed: !previous || !previous.embedding || previous.title !== row.title || previous.summary !== row.summary };
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
  const previous = (await supabaseGet('regulations', { select: 'title,abstract,embedding', regulation_id: `eq.${regulationId}`, limit: '1' }))?.[0];
  await supabaseUpsert('regulations', [row], 'regulation_id');
  for (const agencyId of agencyIds) await supabaseInsertIgnore('regulation_agencies', { regulation_id: regulationId, agency_id: agencyId }, 'regulation_id,agency_id');
  for (const cfr of cfrReferences(document)) {
    const existing = await supabaseGet('regulation_cfr_references', { select: 'regulation_cfr_reference_id', regulation_id: `eq.${regulationId}`,
      title_number: `eq.${cfr.title_number}`, part_number: cfr.part_number ? `eq.${cfr.part_number}` : 'is.null', limit: '1' });
    if (!existing?.length) await supabaseInsert('regulation_cfr_references', { regulation_id: regulationId, ...cfr });
  }
  const eoLinks = await saveOfficialEoLinks(document, regulationId, agencyIds);
  await queue('regulation_id', regulationId, `${row.title}\n${row.abstract || ''}`, { agency: agencyIds[0] || null, cfr_title: String(cfrReferences(document)[0]?.title_number || '') });
  return { regulationId, row, eoLinks, embed: !previous || !previous.embedding || previous.title !== row.title || previous.abstract !== row.abstract };
}

async function saveOfficialEoLinks(document, regulationId, agencyIds) {
  // Relations are created only from an explicit machine-readable EO number, not a keyword/LLM guess.
  const values = asArray(firstNonEmpty(document.executive_order_numbers, document.executive_order_number));
  let linked = 0;
  for (const value of values) {
    const eo = Number(value); if (!Number.isInteger(eo)) continue;
    const exists = await supabaseGet('executive_orders', { select: 'eo_number', eo_number: `eq.${eo}`, limit: '1' });
    if (exists?.length) await supabaseInsertIgnore('executive_order_regulations', {
      eo_number: eo, regulation_id: regulationId, relation_type: 'source_metadata', relation_origin: 'official_citation', source_url: document.html_url,
    }, 'eo_number,regulation_id,relation_type,relation_origin');
    if (exists?.length) {
      await saveEoAgencyLinks(eo, agencyIds, 'implementing_regulation', 'official_citation', document.html_url);
      linked += 1;
    }
  }
  return linked;
}

async function queue(column, value, text, categories) {
  if (!subscriptions) subscriptions = await supabaseGet('subscriptions', { select: 'subscription_id,keyword,category_type,category_id', active: 'eq.true' });
  const source = String(text || '').toLowerCase();
  for (const subscription of subscriptions) {
    if ((subscription.keyword && source.includes(subscription.keyword.toLowerCase())) ||
      (subscription.category_type && categories[subscription.category_type] === subscription.category_id)) {
      const existing = await supabaseGet('notifications_queued', { select: 'notification_id', subscription_id: `eq.${subscription.subscription_id}`, [column]: `eq.${value}`, limit: '1' });
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

function explicitEoNumbers(document) {
  return asArray(firstNonEmpty(document?.executive_order_numbers, document?.executive_order_number))
    .map(Number).filter((value) => Number.isInteger(value));
}

async function runEoRelationBackfill() {
  const state = await loadState();
  let cursor = eoRelationCursor(state);
  const initialTarget = await nextEoRelationTarget(cursor);
  if (!initialTarget) {
    await updateSyncState(RESOURCE, { ...cursor, complete: true, completed_at: new Date().toISOString() });
    console.log('EO relationship backfill is already complete.');
    return;
  }

  const runId = await startSyncRun(RESOURCE, {
    mode: 'eo_relation_backfill', eo_number: initialTarget.eo_number, page: positiveInteger(cursor.page),
    page_size: EO_RELATION_PAGE_SIZE, max_pages: EO_RELATION_MAX_PAGES_PER_RUN, max_runtime_ms: EO_RELATION_MAX_RUNTIME_MS,
  });
  const startedAt = Date.now();
  const totals = {
    pages: 0, eos: 0, read: 0, written: 0,
    authorityLinks: 0, agencyLinks: 0, regulationLinks: 0, skippedDocuments: 0,
  };

  try {
    while (totals.pages < EO_RELATION_MAX_PAGES_PER_RUN && Date.now() - startedAt < EO_RELATION_MAX_RUNTIME_MS) {
      const target = await nextEoRelationTarget(cursor);
      if (!target) {
        await updateSyncState(RESOURCE, { ...cursor, complete: true, completed_at: new Date().toISOString() });
        await finishSyncRun(runId, { status: 'succeeded', records_read: totals.read, records_written: totals.written, metadata: { ...totals, cursor } });
        console.log(`EO relationship backfill history complete: ${totals.pages} pages, ${totals.eos} EOs, ${totals.authorityLinks} authority links, ${totals.agencyLinks} agency directive links, ${totals.regulationLinks} regulation links; ${totals.skippedDocuments} documents skipped.`);
        return;
      }

      const page = positiveInteger(cursor.page);
      let authorityLinks = 0;
      let agencyLinks = 0;
      if (target.document_number) {
        try {
          const detail = await get(`/documents/${encodeURIComponent(target.document_number)}.json`, {}, true) || null;
          if (detail) {
            const relations = await saveOfficialEoTextRelations(target.eo_number, detail);
            authorityLinks = relations.authorityLinks;
            agencyLinks = relations.agencyLinks;
          }
        } catch (error) {
          if (isFederalRegisterIpBlock(error)) {
            throw new Error('Federal Register IP blocked (HTTP 403). Backfill stopped without advancing its checkpoint; wait before retrying.');
          }
          console.warn(`EO relationship backfill: skipped authority detail for EO ${target.eo_number}: ${error.message}`);
        }
      }

      const discovery = await loadEoRelationCandidates(target, page);
      const bundles = await mapWithConcurrency(discovery.candidates, CONCURRENCY, relationDocumentBundle);
      let regulationLinks = 0;
      let written = 0;
      const skippedDocuments = bundles.filter((bundle) => !bundle).length;
      for (const bundle of bundles) {
        if (!bundle) continue;
        const { item, document } = bundle;
        // The search term only finds candidates. Creating a link requires an
        // exact EO number in the source's own machine-readable metadata.
        if (!explicitEoNumbers(document).includes(target.eo_number)) continue;
        const regulation = await saveRegulation(item, document);
        if (regulation) {
          written += 1;
          regulationLinks += regulation.eoLinks;
        }
      }

      const pageComplete = page >= discovery.totalPages;
      const nextCursor = pageComplete
        ? {
          mode: 'eo_relation_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE,
          after_eo_number: target.eo_number, page: 1,
        }
        : {
          mode: 'eo_relation_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE,
          after_eo_number: Number(cursor.after_eo_number) || 0, page: page + 1,
        };
      // Checkpoint every successful page before continuing. Failed candidate
      // fetches are recorded above and deliberately do not block the cursor.
      await checkpointSyncState(RESOURCE, nextCursor);
      totals.pages += 1;
      totals.eos += Number(pageComplete);
      totals.read += discovery.candidates.length;
      totals.written += written;
      totals.authorityLinks += authorityLinks;
      totals.agencyLinks += agencyLinks;
      totals.regulationLinks += regulationLinks;
      totals.skippedDocuments += skippedDocuments;
      console.log(`EO relationship backfill: EO ${target.eo_number}, page ${page}/${discovery.totalPages}; ${authorityLinks} authority links, ${agencyLinks} agency directive links, ${regulationLinks} regulation links, ${skippedDocuments} documents skipped.`);
      cursor = nextCursor;
    }

    const stopReason = totals.pages >= EO_RELATION_MAX_PAGES_PER_RUN ? 'page budget reached' : 'runtime budget reached';
    await finishSyncRun(runId, { status: 'partial', records_read: totals.read, records_written: totals.written, metadata: { ...totals, cursor, stop_reason: stopReason } });
    console.log(`EO relationship backfill paused: ${stopReason} after ${totals.pages} pages and ${totals.eos} EOs. Resume by running the same command again.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: totals.read, records_written: totals.written, metadata: { ...totals, cursor }, error_summary: error.message });
    throw error;
  }
}

async function run() {
  if (EO_RELATION_BACKFILL) return runEoRelationBackfill();
  const state = await loadState();
  if (EO_BACKFILL && eoBackfillCursor(state).complete) {
    console.log(`EO backfill is already complete for ${EO_BACKFILL_FROM_DATE} through ${EO_BACKFILL_TO_DATE}.`);
    return;
  }
  const windowFrom = EO_BACKFILL ? null : currentWindow(state);
  const discovery = EO_BACKFILL ? await loadEoBackfillCandidates(state) : { candidates: await loadCandidates(windowFrom), cursor: null };
  const runId = await startSyncRun(RESOURCE, EO_BACKFILL
    ? { mode: 'eo_backfill', from_date: EO_BACKFILL_FROM_DATE, to_date: EO_BACKFILL_TO_DATE, page: discovery.cursor.page, max_documents: MAX_DOCUMENTS }
    : { window_from: windowFrom, max_documents: MAX_DOCUMENTS });
  let read = 0; let written = 0;
  try {
    const candidates = discovery.candidates;
    const priorProcessed = EO_BACKFILL
      ? discovery.cursor.processed_document_numbers
      : (state?.cursor?.window_from === windowFrom ? state.cursor.processed_document_numbers || [] : []);
    const completed = new Set(priorProcessed);
    const pending = candidates.filter((item) => !completed.has(item.document_number));
    const batch = pending.slice(0, MAX_DOCUMENTS); read = batch.length;
    console.log(EO_BACKFILL
      ? `EO backfill: page ${discovery.cursor.page}/${discovery.cursor.total_pages}, ${pending.length} pending; processing ${read}.`
      : `Federal Register: ${pending.length} pending documents since ${windowFrom}; processing ${read}.`);
    const bundles = await mapWithConcurrency(batch, CONCURRENCY, documentBundle); const eos = []; const regulations = [];
    for (const { item, document } of bundles) {
      const eo = await saveExecutiveOrder(item, document); const regulation = await saveRegulation(item, document);
      if (eo) eos.push(eo); if (regulation) regulations.push(regulation); written += Number(Boolean(eo || regulation));
      completed.add(item.document_number);
      await checkpointSyncState(RESOURCE, EO_BACKFILL
        ? { ...discovery.cursor, processed_document_numbers: [...completed] }
        : { mode: 'incremental', window_from: windowFrom, processed_document_numbers: [...completed] });
    }
    const classifiedAgencies = await supabaseRpc('refresh_federal_register_agency_classification');
    const authorityLinks = await reconcilePublicLawAuthorityLinks();
    const embedded = (await embed('executive_orders', 'eo_number', eos.filter((item) => item.embed).map((item) => ({ ...item.row, eo_number: item.number })), (row) => `${row.title}\n\n${row.summary || ''}`))
      + (await embed('regulations', 'regulation_id', regulations.filter((item) => item.embed).map((item) => ({ ...item.row, regulation_id: item.regulationId })), (row) => `${row.title}\n\n${row.abstract || ''}`));
    const newestBill = await supabaseGet('bills', { select: 'congress_number', order: 'congress_number.desc', limit: '1' });
    const active = Number(process.env.CONGRESS_NUMBER || newestBill?.[0]?.congress_number || 119);
    await supabaseRpc('refresh_policy_lifecycle_tiers', { active_congress_number: active });
    const remaining = pending.length - batch.length;
    const pageComplete = EO_BACKFILL && remaining === 0;
    const hasNextPage = pageComplete && discovery.cursor.page < discovery.cursor.total_pages;
    const backfillComplete = pageComplete && !hasNextPage;
    if (EO_BACKFILL && (remaining > 0 || hasNextPage)) {
      await checkpointSyncState(RESOURCE, hasNextPage
        ? { ...discovery.cursor, page: discovery.cursor.page + 1, processed_document_numbers: [] }
        : { ...discovery.cursor, processed_document_numbers: [...completed] });
    } else if (!EO_BACKFILL && remaining > 0) {
      await checkpointSyncState(RESOURCE, { mode: 'incremental', window_from: windowFrom, processed_document_numbers: [...completed] });
    } else if (EO_BACKFILL && backfillComplete) {
      await updateSyncState(RESOURCE, { ...discovery.cursor, complete: true, completed_at: new Date().toISOString() });
    } else {
      await updateSyncState(RESOURCE, { mode: 'incremental', completed_at: new Date().toISOString() });
    }
    const status = EO_BACKFILL ? (backfillComplete ? 'succeeded' : 'partial') : (remaining > 0 ? 'partial' : 'succeeded');
    await finishSyncRun(runId, { status, records_read: read, records_written: written, metadata: {
      mode: EO_BACKFILL ? 'eo_backfill' : 'incremental', window_from: windowFrom,
      eo_backfill_page: EO_BACKFILL ? discovery.cursor.page : null,
      eo_backfill_total_pages: EO_BACKFILL ? discovery.cursor.total_pages : null,
      embedded, remaining, classified_agencies: Number(classifiedAgencies) || 0, public_law_authority_links: authorityLinks,
    } });
    console.log(EO_BACKFILL
      ? `EO backfill complete: ${written} records on page ${discovery.cursor.page}/${discovery.cursor.total_pages}; ${backfillComplete ? 'history complete' : 'resume by running the same command again'}.`
      : `Federal Register complete: ${written} records, ${embedded} embeddings, ${remaining} deferred. Public Law authority links: ${authorityLinks.linked}/${authorityLinks.total} linked; ${authorityLinks.updated} updated.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: read, records_written: written, error_summary: error.message });
    throw error;
  }
}
run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
