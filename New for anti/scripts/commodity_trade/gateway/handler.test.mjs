import test from 'node:test';
import assert from 'node:assert/strict';
import { timingSafeEqual } from 'node:crypto';
import { handleTradePipeline, validateQuery, boundedText } from './handler.mjs';

// Node-only shim for the documented Workers-native constant-time primitive.
Object.defineProperty(crypto.subtle, 'timingSafeEqual', {value: (a,b) => timingSafeEqual(new Uint8Array(a), new Uint8Array(b))});
const env = {TRADE_PIPELINE_TOKEN: 'synthetic-runner-token', COMTRADE_API_KEY: 'synthetic-upstream-token'};
const q = {query_id: 'a'.repeat(24), source: 'comtrade', reporter: '152', hs: '2603',
  frequency: 'M', period: '202606', flow: 'X', partners: ['*']};
function req(query=q, auth=true) {
  return new Request('https://example.test/api/trade-pipeline/query', {method: 'POST',
    headers: auth ? {Authorization: 'Bearer ' + env.TRADE_PIPELINE_TOKEN} : {}, body: JSON.stringify(query)});
}

test('unauthorized callers never reach upstream', async () => {
  const r = await handleTradePipeline(req(q,false), env, () => assert.fail('network'));
  assert.equal(r.status, 401);
});
test('arbitrary URLs and invalid dates rejected', () => {
  for (const query of [{...q, url:'http://localhost'}, {...q, period:'202613'}, {...q, reporter:'0'},
    {...q, partners:['*','0']}, {...q, hs:'26'}, {...q, flow:'all'}]) assert.throws(() => validateQuery(query));
});
test('valid response preserves HS units flags and discards unrelated text', async () => {
  const r = await handleTradePipeline(req(), env, async (url, options) => {
    assert.equal(url.hostname, 'comtradeapi.un.org');
    assert.equal(options.headers['Ocp-Apim-Subscription-Key'], env.COMTRADE_API_KEY);
    assert.equal(options.redirect, 'error');
    return Response.json({count:1, data:[{cmdCode:'2603', qtyUnitCode:8, isNetWgtEstimated:true, unwanted:'discard'}]});
  });
  const data = JSON.parse((await r.json()).payload).data[0];
  assert.equal(data.cmdCode, '2603'); assert.equal(data.isNetWgtEstimated, true);
  assert.equal(data.qtyUnitCode, 8); assert.equal(data.unwanted, undefined);
  assert.equal(r.headers.get('cache-control'), 'no-store');
});
test('rate limit or request failure is not a partial success', async () => {
  const rate = await handleTradePipeline(req(), env, async () => new Response('', {status:429}));
  assert.equal((await rate.json()).status, 'rate_limited');
  const failure = await handleTradePipeline(req(), env, async () => {throw new Error('serviceKey=synthetic-private');});
  const text = await failure.text();
  assert.equal(failure.status, 502); assert.ok(!text.includes('synthetic-private'));
});
test('Korea partner query keeps key server-side and blocks service errors', async () => {
  const query = {...q, source:'korea_customs', reporter:'410', partners:['682'], partner_iso2:'SA'};
  const r = await handleTradePipeline(req(query), {...env, KOREA_CUSTOMS_SERVICE_KEY:'synthetic%2Bupstream'}, async (url) => {
    assert.equal(url.pathname, '/1220000/nitemtrade/getNitemtradeList');
    assert.equal(url.searchParams.get('cntyCd'), 'SA');
    assert.equal(url.searchParams.get('serviceKey'), 'synthetic+upstream');
    return new Response('<response><header><resultCode>20</resultCode></header></response>');
  });
  const text = await r.text(); assert.ok(text.includes('auth_required')); assert.ok(!text.includes('upstream'));
});
test('bounded bodies and secret echo are rejected', async () => {
  await assert.rejects(boundedText(new Response('12345'), 4));
  const r = await handleTradePipeline(req(), env, async () => Response.json({count:1,data:[{partnerDesc:env.COMTRADE_API_KEY}]}));
  assert.equal((await r.json()).status, 'error');
});
test('missing key has explicit status; no hidden fallback', async () => {
  const r = await handleTradePipeline(req(), {TRADE_PIPELINE_TOKEN:env.TRADE_PIPELINE_TOKEN}, () => assert.fail('network'));
  assert.equal((await r.json()).status, 'auth_required');
});
