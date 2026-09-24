import test from 'node:test';
import assert from 'node:assert/strict';
import {availablePeriods, countryRows, loadBilateral} from './bilateral-loader.mjs';
const part = {meta:{reporter:'410',source:'korea_customs',hs:'2709',period:'202606',frequency:'M'},
  flows:{M:{rows:[{partner:'682', exporter:'682',importer:'410',analysis:{net_weight_kg:{share_pct:40,rank:1}}}]}}, acquisition:[]};
test('mirror preserves direction but never reuses Korean denominator', () => {
  const r = countryRows(part, '682')[0];
  assert.equal(r.focus_flow, 'X'); assert.equal(r.counterparty,'410');
  assert.equal(r.analysis.net_weight_kg.share_pct, null);
  assert.equal(countryRows(part,'410')[0].analysis.net_weight_kg.share_pct,40);
});
test('available months never include annual fallback', () => {
  const entries = [{...part.meta,partners:['682']},{...part.meta,partners:['682'],period:'2024',frequency:'A'}];
  assert.deepEqual(availablePeriods({entries},{countryCode:'682',hs:'2709'}), ['202606']);
});
test('missing month returns not_available, not a stale fallback', async () => {
  const result = await loadBilateral({baseUrl:'/public/data/trade',countryCode:'682',hs:'2709',period:'202607'},
    async () => Response.json({schema:'commodity-trade-bilateral-index-v1',entries:[]}));
  assert.equal(result.status,'not_available'); assert.deepEqual(result.rows,[]);
});
