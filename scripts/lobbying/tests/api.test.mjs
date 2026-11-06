import test from 'node:test';
import assert from 'node:assert/strict';
import {handleLobbying} from '../api.mjs';

const request=path=>new Request('https://example.test/api/us/lobbying/'+path);
test('public endpoint rejects writes without touching DB',async()=>{
  const res=await handleLobbying(new Request(request('records'),{method:'POST'}),{},()=>{throw Error('DB called')});
  assert.equal(res.status,405);
});
test('untrusted filter cannot become a PostgREST expression',async()=>{
  for(const query of ['country=KR%29%2Cor%28x','topic=unknown','policy_type=bill&policy_id=x%29%2Csecret','q=foo%26select%3Draw_payload']){
    const res=await handleLobbying(request('records?'+query),{},()=>{throw Error('DB called')});assert.equal(res.status,400);
  }
});
test('list selects bounded metadata, with all-source default',async()=>{
  let query;
  const res=await handleLobbying(request('records'),{},async(_env,table,q)=>{assert.equal(table,'lobby_records');query=new URLSearchParams(q);return [];});
  assert.equal(res.status,200);assert.equal(query.get('source'),null);assert.equal(query.get('country_codes'),null);
  assert.equal(query.get('limit'),'26');assert.equal(query.get('select').includes('raw_payload'),false);
});
test('only confirmed policy links are used and empty is not an invented activity',async()=>{
  const res=await handleLobbying(request('records?policy_type=bill&policy_id=119-hr-1234'),{},async(_env,table,q)=>{
    assert.equal(table,'lobby_policy_links');assert.equal(new URLSearchParams(q).get('resolution_status'),'eq.confirmed');return [];
  });
  const body=await res.json();assert.deepEqual(body.items,[]);assert.equal(body.link_status,'confirmed_only');
});
test('DB errors do not become empty/zero results or expose diagnostics',async()=>{
  const res=await handleLobbying(request('coverage'),{},null,async()=>{throw new Error('sensitive diagnostic')});
  assert.equal(res.status,503);assert.equal((await res.text()).includes('sensitive diagnostic'),false);
});
test('Coupang case preserves investor petition and contextual lobbying',async()=>{
  const res=await handleLobbying(request('cases/coupang-korea-data-and-trade'),{});
  const c=await res.json();assert.match(c.events[0].actor,/Greenoaks/);assert.equal(c.events[0].type,'petition');
  assert.equal(c.contextual_records[0].link_strength,'contextual');
});
