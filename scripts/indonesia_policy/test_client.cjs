const {test}=require('node:test');
const assert=require('node:assert/strict');
const {request}=require('./client.cjs');
test('IDN client refuses US tables, RPC fallback and ambiguous GET requests',async()=>{
 for(const path of ['bills','rpc/store_idn_policy_document','rpc/search_policy_corpus','policy_search_documents']){
  await assert.rejects(request(path,{method:'POST',body:{}}),/Not an IDN gateway/);
 }
 await assert.rejects(request('rpc/idn_status'),/Not an IDN gateway/);
});
