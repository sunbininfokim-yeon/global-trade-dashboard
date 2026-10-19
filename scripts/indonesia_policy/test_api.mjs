import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHandler,parseTerms} from './search-api.mjs';
const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'sb_secret_test'};
test('Korean topics and issuer-independent terms expand without paid AI',()=>{
 assert.ok(parseTerms('니켈, 수출')[0].aliases.includes('nikel'));
 assert.ok(parseTerms('바이오연료')[0].aliases.includes('bahan bakar nabati'));
 assert.equal(parseTerms('32/MK/BC')[0].aliases[0],'32/MK/BC');
 assert.equal(parseTerms('니켈 수출').length,2);assert.equal(parseTerms('palm oil').length,1);
 assert.equal(parseTerms('Permendag 15/2026').length,1);
 assert.ok(parseTerms('보조금')[0].aliases.includes('bantuan'));
 assert.ok(parseTerms('세금감면')[0].aliases.includes('pengurangan pajak'));
 assert.ok(!parseTerms('금융지원')[0].aliases.includes('tax_incentive'));
 assert.ok(parseTerms('환경영향평가')[0].aliases.includes('amdal'));
 assert.ok(parseTerms('폐수')[0].aliases.includes('air limbah'));
 assert.ok(parseTerms('니켈, 국산화율')[1].aliases.includes('tkdn'));
 assert.equal(parseTerms('local content').length,1);
 assert.ok(parseTerms('산업정보 보고')[0].aliases.includes('siinas'));
 assert.ok(!parseTerms('국산화율')[0].aliases.includes('subsidies_incentives'));
 assert.ok(!parseTerms('산업보고')[0].aliases.includes('rkab'));
 assert.ok(parseTerms('광산복구')[0].aliases.includes('reklamasi'));
 assert.throws(()=>parseTerms('a,b,c,d,e,f,g'));
});
test('business-law queries preserve distinct issues and multilingual phrases',()=>{
 const terms=parseTerms('니켈, 계약, 불가항력');
 assert.equal(terms.length,3);
 assert.ok(terms[1].aliases.includes('perjanjian'));
 assert.ok(terms[2].aliases.includes('keadaan memaksa'));
 assert.equal(parseTerms('security interest').length,1);
 assert.equal(parseTerms('kitab undang-undang hukum perdata').length,1);
 assert.ok(parseTerms('민법')[0].aliases.includes('kuhperdata'));
 assert.ok(!parseTerms('민법')[0].aliases.includes('kuhd'));
 assert.ok(parseTerms('석탄, 파산')[1].aliases.includes('kepailitan'));
 assert.ok(!parseTerms('파산')[0].aliases.includes('pkpu'));
 assert.ok(parseTerms('팜유, 양도담보')[1].aliases.includes('fidusia'));
 assert.ok(!parseTerms('투자')[0].aliases.includes('subsidies_incentives'));
 assert.ok(parseTerms('금')[0].aliases.includes('gold'));
 assert.ok(!parseTerms('금')[0].aliases.includes('금'));
 assert.ok(parseTerms('은광')[0].aliases.includes('perak'));
});
test('IDN handler calls only IDN RPC and keeps the server key out of responses',async()=>{
 const handler=createHandler(async(url,options)=>{
  assert.equal(url,'https://db.test/rest/v1/rpc/idn_search_documents_v2');
  assert.equal(options.headers.Authorization,undefined);
  const args=JSON.parse(options.body);assert.equal(args.p_terms.length,2);assert.equal(args.p_topic,'coal');
  return Response.json({country:'IDN',items:[],total:0});
 });
 const response=await handler(new Request('https://site/api/idn/search?q=석탄,수출&topic=coal'),env);
 assert.equal(response.status,200);assert.ok(!(await response.text()).includes(env.SUPABASE_SERVICE_ROLE_KEY));
});
test('invalid filters and requests never hit upstream; missing records and failures stay distinct',async()=>{
 let calls=0;const handler=createHandler(async()=>{calls++;return Response.json(null);});
 for(const url of ['/api/idn/search?topic=us','/api/idn/search?limit=999','/api/idn/documents/us-test','/api/idn/search?level=national&jurisdiction=Banten'])assert.equal((await handler(new Request('https://site'+url),env)).status,400);
 assert.equal((await handler(new Request('https://site/api/idn/search',{method:'POST'}),env)).status,405);assert.equal(calls,0);
 assert.equal((await handler(new Request('https://site/api/idn/documents/idn-missing'),env)).status,404);
 assert.equal((await handler(new Request('https://site/api/idn/search'),{})).status,503);
 const failed=createHandler(async()=>new Response('sensitive upstream',{status:500}));
 const r=await failed(new Request('https://site/api/idn/search'),env);assert.equal(r.status,502);assert.ok(!(await r.text()).includes('sensitive'));
 const mixed=createHandler(async()=>Response.json({country:'USA',items:[]}));
 assert.equal((await mixed(new Request('https://site/api/idn/search'),env)).status,502);
});
test('local government selection reaches the IDN query without including national issuers',async()=>{
 const handler=createHandler(async(url,options)=>{
  const args=JSON.parse(options.body);assert.equal(args.p_level,'local');assert.equal(args.p_jurisdiction,null);
  return Response.json({country:'IDN',items:[],total:0});
 });
 assert.equal((await handler(new Request('https://site/api/idn/search?level=local'),env)).status,200);
});
test('coverage, review context and combined national/regional business candidates use explicit IDN gateways',async()=>{
 const calls=[];
 const handler=createHandler(async(url,options)=>{calls.push({url,args:JSON.parse(options.body)});return Response.json({country:'IDN',items:[]});});
 for(const url of ['/api/idn/coverage?topic=coal&priority=1','/api/idn/context/idn-example','/api/idn/business?role=miner&region=Sulawesi%20Tengah&issue=licensing']){
  assert.equal((await handler(new Request('https://site'+url),env)).status,200);
 }
 assert.ok(calls[0].url.endsWith('/rpc/idn_coverage'));assert.equal(calls[0].args.p_priority,1);
 assert.ok(calls[1].url.endsWith('/rpc/idn_document_context'));
 assert.ok(calls[2].url.endsWith('/rpc/idn_business_search'));assert.equal(calls[2].args.p_region,'Sulawesi Tengah');
 for(const url of ['/api/idn/coverage?priority=0','/api/idn/context/us-example','/api/idn/business?role=unknown'])assert.equal((await handler(new Request('https://site'+url),env)).status,400);
 assert.equal(calls.length,3);
});
test('passage evidence cannot expand candidates or replace a failed evidence lookup with verified zero hits',async()=>{
 const doc={document_id:'idn-nickel-example',matched_condition_count:2};let failure=false;
 const handler=createHandler(async(url,options)=>{
  if(url.endsWith('/idn_search_documents_v2'))return Response.json({country:'IDN',total:1,items:[{...doc}]});
  assert.ok(url.endsWith('/idn_search_passages'));assert.deepEqual(JSON.parse(options.body).p_document_ids,[doc.document_id]);
  if(failure)return new Response('private failure',{status:500});
  return Response.json({country:'IDN',items:[{document_id:doc.document_id,article:'Pasal 52',matched_condition_count:1},{document_id:'idn-excluded',article:'Unrelated'}]});
 });
 let r=await (await handler(new Request('https://site/api/idn/search?q=니켈,국산화율'),env)).json();
 assert.equal(r.total,1);assert.equal(r.items.length,1);assert.equal(r.items[0].matched_condition_count,2);assert.equal(r.items[0].matched_passages.length,1);assert.equal(r.passage_annotations_available,true);
 failure=true;r=await (await handler(new Request('https://site/api/idn/search?q=니켈,국산화율'),env)).json();
 assert.equal(r.total,1);assert.equal(r.passage_annotations_available,false);assert.equal(r.items[0].matched_passages,undefined);
});
