'use strict';

// Federal Register API가 차단된 동안에도, 별도로 확보한 공식 EO 원문 캐시에서
// 근거 법령과 명시적 기관 역할을 적재하는 보조 백필이다. 캐시에 없는 EO는
// 건너뛰며 Federal Register나 Gemini에 요청하지 않는다.
const {
  finishSyncRun, requireEnv, startSyncRun, supabaseGet,
} = require('./lib/sync-utils');
const { hasCachedOfficialEoText } = require('./lib/eo-authorities');
const { saveOfficialEoTextRelations } = require('./lib/eo-official-relations');

const RESOURCE = 'official-eo-text-cache:relationships';
const MAX_DOCUMENTS = Math.min(250, Math.max(1, Number(process.env.MAX_EO_TEXT_CACHE_DOCUMENTS || 50)));

async function run() {
  requireEnv('SUPABASE_URL');
  requireEnv('SUPABASE_SERVICE_ROLE_KEY');
  if (!process.env.EO_OFFICIAL_TEXT_CACHE_DIR) {
    throw new Error('Missing EO_OFFICIAL_TEXT_CACHE_DIR. Point it to the directory containing official EO JSON cache files.');
  }
  const rows = await supabaseGet('executive_orders', {
    select: 'eo_number,document_number,federal_register_url,executive_order_url',
    order: 'eo_number.asc', limit: '2000',
  });
  const candidates = (rows || []).filter((row) => hasCachedOfficialEoText(row)).slice(0, MAX_DOCUMENTS);
  const runId = await startSyncRun(RESOURCE, { cache_documents_found: candidates.length, max_documents: MAX_DOCUMENTS });
  let authorityLinks = 0;
  let agencyLinks = 0;
  try {
    for (const row of candidates) {
      const relations = await saveOfficialEoTextRelations(row.eo_number, {
        document_number: row.document_number,
        html_url: row.federal_register_url,
        raw_text_url: row.executive_order_url,
      }, { cacheOnly: true });
      authorityLinks += relations.authorityLinks;
      agencyLinks += relations.agencyLinks;
    }
    await finishSyncRun(runId, {
      status: 'succeeded', records_read: candidates.length, records_written: authorityLinks + agencyLinks,
      metadata: { cache_documents_processed: candidates.length, authority_links: authorityLinks, agency_links: agencyLinks },
    });
    console.log(`EO official-text cache backfill complete: ${candidates.length} documents, ${authorityLinks} authority links, ${agencyLinks} agency directive links.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
