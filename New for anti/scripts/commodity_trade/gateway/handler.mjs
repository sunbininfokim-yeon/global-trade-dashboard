// Importable protected acquisition handler. Claude wires ONLY the exact route
// /api/trade-pipeline/query before existing public handlers. Not deployed here.
// Secrets: TRADE_PIPELINE_TOKEN, COMTRADE_API_KEY, KOREA_CUSTOMS_SERVICE_KEY.
const encoder = new TextEncoder();
const FIELDS = ['typeCode', 'freqCode', 'period', 'reporterCode', 'reporterISO',
  'flowCode', 'partnerCode', 'partnerISO', 'partnerDesc', 'partner2Code',
  'classificationCode', 'cmdCode', 'customsCode', 'motCode', 'netWgt',
  'primaryValue', 'fobvalue', 'cifvalue', 'qty', 'qtyUnitCode', 'qtyUnitAbbr',
  'altQty', 'altQtyUnitCode', 'isNetWgtEstimated', 'isQtyEstimated',
  'isAltQtyEstimated', 'isOriginalClassification', 'isReported', 'isAggregate', 'legacyEstimationFlag'];

export async function boundedText(message, limit) {
  const reader = message.body?.getReader();
  if (!reader) return '';
  const chunks = []; let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error('size_limit');
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder('utf-8', {fatal: true}).decode(joined);
}

async function authenticated(request, env) {
  if (!env.TRADE_PIPELINE_TOKEN) return false;
  const supplied = request.headers.get('Authorization') || '';
  const hashes = await Promise.all([supplied, 'Bearer ' + env.TRADE_PIPELINE_TOKEN]
    .map(s => crypto.subtle.digest('SHA-256', encoder.encode(s))));
  return crypto.subtle.timingSafeEqual(hashes[0], hashes[1]);
}

export function validateQuery(q) {
  const keys = ['query_id', 'source', 'reporter', 'hs', 'period', 'frequency', 'flow', 'partners', 'partner_iso2'];
  if (!q || typeof q !== 'object' || Array.isArray(q) || Object.keys(q).some(k => !keys.includes(k))) throw new Error('query');
  if (!/^[a-f0-9]{24}$/.test(q.query_id) || !/^\d{4}(\d{2})?$/.test(q.hs)
    || !/^[1-9]\d{0,2}$/.test(q.reporter) || !['X', 'M'].includes(q.flow)
    || !['M', 'A'].includes(q.frequency) || typeof q.period !== 'string') throw new Error('query');
  const period = q.frequency === 'M' ? /^\d{4}(0[1-9]|1[0-2])$/ : /^\d{4}$/;
  if (!period.test(q.period) || Number(q.period.slice(0,4)) < 1962
    || Number(q.period.slice(0,4)) > new Date().getUTCFullYear()) throw new Error('period');
  if (!Array.isArray(q.partners) || !q.partners.length || q.partners.length > 50) throw new Error('partners');
  if (!(q.partners.length === 1 && q.partners[0] === '*')
    && q.partners.some(p => typeof p !== 'string' || !/^\d{1,3}$/.test(p))) throw new Error('partners');
  if (!['comtrade', 'korea_customs'].includes(q.source)) throw new Error('source');
  if (q.source === 'korea_customs' && (q.reporter !== '410' || q.frequency !== 'M'
      || q.partners.length !== 1 || q.partners[0] === '*'
      || (q.partners[0] === '0' ? q.partner_iso2 !== null : !/^[A-Z]{2}$/.test(q.partner_iso2)))) throw new Error('Korea');
  return q;
}

function upstream(q, env) {
  if (q.source === 'comtrade') {
    if (!env.COMTRADE_API_KEY) return null;
    const u = new URL(`https://comtradeapi.un.org/data/v1/get/C/${q.frequency}/HS`);
    u.search = new URLSearchParams({reporterCode: q.reporter, period: q.period,
      cmdCode: q.hs, flowCode: q.flow, partnerCode: q.partners[0] === '*' ? '' : q.partners.join(','),
      partner2Code: '0', customsCode: 'C00', motCode: '0', maxRecords: '500'});
    return {url: u, headers: {'Accept': 'application/json', 'Ocp-Apim-Subscription-Key': env.COMTRADE_API_KEY}};
  }
  if (!env.KOREA_CUSTOMS_SERVICE_KEY) return null;
  const op = q.partner_iso2 ? 'nitemtrade/getNitemtradeList' : 'Itemtrade/getItemtradeList';
  const u = new URL('https://apis.data.go.kr/1220000/' + op);
  u.search = new URLSearchParams({strtYymm: q.period, endYymm: q.period,
    hsSgn: q.hs, serviceKey: decodeURIComponent(env.KOREA_CUSTOMS_SERVICE_KEY)});
  if (q.partner_iso2) u.searchParams.set('cntyCd', q.partner_iso2);
  return {url: u, headers: {'Accept': 'application/xml'}};
}

function reply(query_id, status, payload, httpStatus=200) {
  return Response.json({query_id, status, ...(payload === undefined ? {} : {payload})},
    {status: httpStatus, headers: {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}});
}

export async function handleTradePipeline(request, env, fetcher=fetch) {
  let id = null;
  try {
    if (new URL(request.url).pathname !== '/api/trade-pipeline/query') return reply(id, 'error', undefined, 404);
    if (!await authenticated(request, env)) return reply(id, 'auth_required', undefined, 401);
    if (request.method !== 'POST') return reply(id, 'error', undefined, 405);
    let q;
    try { q = validateQuery(JSON.parse(await boundedText(request, 8192))); }
    catch { return reply(id, 'error', undefined, 400); }
    id = q.query_id;
    const target = upstream(q, env);
    if (!target) return reply(id, 'auth_required');
    // A single bounded request: no silent chunk failures, retries or redirects.
    const response = await fetcher(target.url, {headers: target.headers, redirect: 'error', signal: AbortSignal.timeout(30000)});
    if (!response.ok) {
      await response.body?.cancel();
      return reply(id, response.status === 429 ? 'rate_limited' : [401,403].includes(response.status) ? 'auth_required' : 'error');
    }
    let payload = await boundedText(response, 4 * 1024 * 1024);
    if (q.source === 'comtrade') {
      const body = JSON.parse(payload);
      if (!Array.isArray(body.data) || body.count !== body.data.length || body.data.length > 500) return reply(id, 'error');
      payload = JSON.stringify({count: body.count, mayBeTruncated: body.mayBeTruncated === true,
        data: body.data.map(row => Object.fromEntries(FIELDS.filter(f => Object.hasOwn(row, f)).map(f => [f, row[f]])))});
    } else {
      const code = payload.match(/<resultCode>\s*(\d+)\s*<\/resultCode>/)?.[1];
      if (code !== '00') return reply(id, ['20','30','31','32'].includes(code) ? 'auth_required' : ['22','23'].includes(code) ? 'rate_limited' : 'error');
      if (/<!DOCTYPE|<!ENTITY|servicekey/i.test(payload)) return reply(id, 'error');
    }
    // Defence in depth: even a faulty upstream may not echo credentials.
    for (const secret of [env.COMTRADE_API_KEY, env.KOREA_CUSTOMS_SERVICE_KEY, env.TRADE_PIPELINE_TOKEN].filter(Boolean)) {
      if ([secret, decodeURIComponent(secret), encodeURIComponent(secret)].some(s => payload.includes(s))) return reply(id, 'error');
    }
    return reply(id, 'ok', payload);
  } catch { return reply(id, 'error', undefined, 502); } // No raw exception/URL logs.
}
