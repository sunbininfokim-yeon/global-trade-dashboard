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
 assert.throws(()=>parseTerms('a,b,c,d,e,f,g'));
});
test('IDN handler calls only IDN RPC and keeps the server key out of responses',async()=>{
 const handler=createHandler(async(url,options)=>{
  assert.equal(url,'https://db.test/rest/v1/rpc/idn_search_documents');
  assert.equal(options.headers.Authorization,undefined);
  const args=JSON.parse(options.body);assert.equal(args.p_terms.length,2);assert.equal(args.p_topic,'coal');
  return Response.json({country:'IDN',items:[],total:0});
 });
 const response=await handler(new Request('https://site/api/idn/search?q=석탄,수출&topic=coal'),env);
 assert.equal(response.status,200);assert.ok(!(await response.text()).includes(env.SUPABASE_SERVICE_ROLE_KEY));
});
test('invalid filters and requests never hit upstream; missing records and failures stay distinct',async()=>{
 let calls=0;const handler=createHandler(async()=>{calls++;return Response.json(null);});
 for(const url of ['/api/idn/search?topic=us','/api/idn/search?limit=999','/api/idn/documents/us-test'])assert.equal((await handler(new Request('https://site'+url),env)).status,400);
 assert.equal((await handler(new Request('https://site/api/idn/search',{method:'POST'}),env)).status,405);assert.equal(calls,0);
 assert.equal((await handler(new Request('https://site/api/idn/documents/idn-missing'),env)).status,404);
 assert.equal((await handler(new Request('https://site/api/idn/search'),{})).status,503);
 const failed=createHandler(async()=>new Response('sensitive upstream',{status:500}));
 const r=await failed(new Request('https://site/api/idn/search'),env);assert.equal(r.status,502);assert.ok(!(await r.text()).includes('sensitive'));
 const mixed=createHandler(async()=>Response.json({country:'USA',items:[]}));
 assert.equal((await mixed(new Request('https://site/api/idn/search'),env)).status,502);
});
