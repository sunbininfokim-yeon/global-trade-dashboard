const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../../_worker.js'),'utf8').replace(/^import [^\n]*\n/gm,'').replace('export default {','globalThis.worker = {');
test('shared Worker dispatches IDN reads to the isolated handler, never the US path',async()=>{
 const {createHandler}=await import('./search-api.mjs');let calls=0;
 const handleIdnPolicy=createHandler(async(url,options)=>{
  calls++;assert.equal(new URL(url).pathname,'/rest/v1/rpc/idn_search_documents_v2');
  assert.equal(JSON.parse(options.body).p_terms.length,2);
  return Response.json({country:'IDN',items:[{document_id:'idn-test',matched_condition_count:2}],total:1});
 });
 const context=vm.createContext({handleIdnPolicy,URL,URLSearchParams,Request,Response,Headers,console,setTimeout,clearTimeout});
 vm.runInContext(source,context);
 const response=await context.worker.fetch(new Request('https://site/api/idn/search?q=니켈,수출'),{SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'sb_secret_test'},{});
 assert.equal(response.status,200);assert.equal((await response.json()).items[0].document_id,'idn-test');assert.equal(calls,1);
 assert.equal((await context.worker.fetch(new Request('https://site/api/idn/missing'),{},{})).status,404);
 assert.equal(calls,1);
});
