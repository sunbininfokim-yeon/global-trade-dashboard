import {test} from 'node:test';import assert from 'node:assert/strict';
import {effectLabel} from '../../New for anti/indonesia-policy/legal-effect.mjs';
import {createHandler} from './search-api.mjs';
test('effect labels separate amendment, repeal and unverified current validity',()=>{
 assert.match(effectLabel({status:'amended'}),/개정/);assert.ok(!effectLabel({status:'amended'}).includes('폐지'));
 assert.match(effectLabel({status:'fully_repealed'}),/전부 폐지/);assert.match(effectLabel({status:'commenced_review_needed'}),/후속 개폐 미확인/);
 assert.equal(effectLabel(null),'현행 효력 미확인');assert.equal(effectLabel({status:'invented'}),'현행 효력 미확인');
});
test('legal annotations preserve search candidates on success, unavailable service and invalid country',async()=>{
 const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'sb_secret_test'};let fail=false,wrong=false;
 const handler=createHandler(async(url,options)=>{
  if(url.endsWith('/idn_search_documents_v2'))return Response.json({country:'IDN',total:1,items:[{document_id:'idn-test'}]});
  assert.ok(url.endsWith('/idn_legal_effect'));assert.deepEqual(JSON.parse(options.body).p_document_ids,['idn-test']);
  if(fail)return new Response('Unavailable',{status:503});
  return Response.json({country:wrong?'USA':'IDN',items:[{document_id:'idn-test',status:'amended'},{document_id:'idn-other',status:'fully_repealed'}]});
 });
 const request=()=>handler(new Request('https://site/api/idn/search'),env).then(r=>r.json());
 let r=await request();assert.equal(r.items.length,1);assert.equal(r.items[0].legal_effect.status,'amended');assert.equal(r.legal_effect_available,true);
 fail=true;r=await request();assert.equal(r.total,1);assert.equal(r.legal_effect_available,false);assert.equal(r.items[0].legal_effect,undefined);
 fail=false;wrong=true;r=await request();assert.equal(r.legal_effect_available,false);
 const res=await handler(new Request('https://site/api/idn/legal-effect?ids=us-test'),env);assert.equal(res.status,400);
});
