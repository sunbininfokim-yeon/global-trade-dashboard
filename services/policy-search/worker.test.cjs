const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const terms=require('../../scripts/lib/policy-search-terms');
const source=fs.readFileSync(require.resolve('../../_worker.js'),'utf8').replace(/^import .*;\n/gm,'').replace('export default {','const handler = {');
function harness(fetch) {
  const ctx={URL,URLSearchParams,Response,Request,Headers,AbortSignal,console,fetch,PolicySearchTerms:terms,PolicyEvidence:{},setTimeout,clearTimeout};
  vm.createContext(ctx);vm.runInContext(source+'\nthis.api={usConditionSearch,usHybridSearch,usCorpusVectors,usDocumentCandidates};',ctx);return ctx.api;
}
const base={bill_id:'119-hjres-72',title:'Relating to a national emergency',summary:null,congress_number:119,bill_type:'hjres',bill_number:72,congress_url:'https://www.congress.gov/bill/119th-congress/house-joint-resolution/72'};
const proof=[{field:'cited_document',text:'Canada tariffs',source_url:'https://www.govinfo.gov/content/pkg/DCPD-202500209/html/DCPD-202500209.htm',target_type:'executive_order',target_id:'14193',citation_url:base.congress_url}];
test('Worker conditions retain refreshed evidence when legacy rows are hydrated again; no provider required',async()=>{
  const fetch=async(url,options={})=>{
    const u=new URL(url);
    if((u.pathname.includes('search_policy_balanced')||u.pathname.includes('search_policy_vectors_for_type')||u.pathname.includes('search_policy_document_terms_for_type')))return Response.json({message:'not installed'},{status:404});
    if(u.pathname.endsWith('/rpc/search_policy_document_terms'))return Response.json([{source_type:'bill',source_id:base.bill_id,evidence_parts:proof,coverage:{text_status:'body'},refresh_pending:false}]);
    if(u.pathname.endsWith('/bills'))return Response.json([base]);
    return Response.json([]);
  };
  const result=await harness(fetch).usConditionSearch({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},{query:'캐나다, 관세',conditions:terms.parse('캐나다, 관세'),limit:20});
  assert.equal(result.body.items.length,1);assert.equal(result.body.items[0].matched_condition_count,2);
  assert.equal(result.body.match_basis,'official_text_and_citations');assert.equal(result.body.semantic_available,false);
  assert.equal(result.body.items[0].condition_matches[0].target_id,'14193');
});
test('missing new schema keeps existing corpus search; refreshed passages override the same legacy identity',async()=>{
  let missing=true;
  const fetch=async(url)=>{
    if((url.includes('search_policy_balanced')||url.includes('search_policy_vectors_for_type')))return Response.json({message:'not installed'},{status:404});
    if(url.endsWith('/search_policy_document_vectors'))return missing ? Response.json({message:'not installed'},{status:404}) : Response.json([{source_type:'public_law',source_id:'118-public-1',title:'Enacted law',similarity_score:0.6}]);
    return Response.json([{source_type:'public_law',source_id:'118-public-1',title:'Legacy',similarity_score:0.9}]);
  };
  const api=harness(fetch),env={SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'};
  assert.equal((await api.usCorpusVectors(env,{p_result_limit:20}))[0].title,'Legacy');missing=false;
  assert.equal((await api.usCorpusVectors(env,{p_result_limit:20}))[0].title,'Enacted law');
});
test('single Korean concept uses official body evidence and preserves public-law source link',async()=>{
  const fetch=async(url)=>{
    const u=new URL(url);
    if((u.pathname.includes('search_policy_balanced')||u.pathname.includes('search_policy_vectors_for_type')||u.pathname.includes('search_policy_document_terms_for_type')))return Response.json({message:'not installed'},{status:404});
    if(u.pathname.endsWith('/rpc/search_policy_document_terms'))return Response.json([{source_type:'public_law',source_id:'118-public-1',evidence_parts:[{field:'body',text:'Canada tariffs',source_url:'https://www.govinfo.gov/x'}],coverage:{text_status:'body'},refresh_pending:false}]);
    if(u.pathname.endsWith('/public_laws'))return Response.json([{public_law_id:'118-public-1',law_title:'Trade law',govinfo_url:'https://www.govinfo.gov/x'}]);
    return Response.json([]);
  };
  const result=await harness(fetch).usHybridSearch({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},{query:'캐나다',limit:20});
  assert.equal(result.body.items[0].source_url,'https://www.govinfo.gov/x');assert.equal(result.body.items[0].type,'public_law');
});
test('four typed RPCs reuse one query vector and carries missing-body coverage',async()=>{
 let calls=0;
 const fetch=async(url,options)=>{
  calls++;assert.ok(url.endsWith('/search_policy_vectors_for_type'));
  const body=JSON.parse(options.body);assert.equal(body.p_per_type_limit,20);assert.equal(body.p_embedding_model,'gemini-embedding-001');
  assert.equal(body.p_query_embedding.length,1536);
  return Response.json(body.p_source_type==='executive_order'?[{source_type:'executive_order',source_id:'14154',similarity_score:0.8,coverage:{text_status:'unavailable'}}]:[]);
 };
 const rows=await harness(fetch).usCorpusVectors({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},
  {p_result_limit:20,p_query_embedding:Array(1536).fill(0),p_embedding_model:'gemini-embedding-001'});
 assert.equal(calls,4);assert.equal(rows[0].coverage.text_status,'unavailable');
});
test('twenty-result hybrid cap preserves four relevant lanes instead of thirty bills crowding them out',async()=>{
 const rows={bills:Array.from({length:30},(_,n)=>({bill_id:'b'+n,title:'Energy legislation',summary:'Energy'})),
 executive_orders:[{eo_number:1,title:'Energy order'}],public_laws:[{public_law_id:'law',law_title:'Energy law'}],regulations:[{regulation_id:'reg',title:'Energy regulation'}]};
 const fetch=async(url)=>{const name=new URL(url).pathname.split('/').at(-1);return Response.json(rows[name]||[]);};
 const result=await harness(fetch).usHybridSearch({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},{query:'에너지',limit:20});
 assert.equal(result.body.items.length,20);assert.equal(new Set(result.body.items.map(i=>i.type)).size,4);
});

test('finance and China body candidates use separate typed statement budgets',async()=>{
 const requested=[];
 const fetch=async(url,options)=>{
  if(url.includes('/rpc/')){
   assert.ok(url.endsWith('/search_policy_document_terms_for_type'));
   const body=JSON.parse(options.body);requested.push(body.p_source_type);
   return Response.json(body.p_source_type==='bill'?[{source_type:'bill',source_id:base.bill_id,evidence_parts:[{field:'body',text:"Financial regulation in the People's Republic of China"}],coverage:{text_status:'body'}}]:[]);
  }
  return Response.json(url.includes('/bills?')?[base]:[]);
 };
 const result=await harness(fetch).usDocumentCandidates({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},terms.parse('금융, 중국'));
 assert.equal(result.available,true);assert.deepEqual(requested.sort(),['bill','executive_order','public_law','regulation']);
 assert.equal(terms.annotate(result.items[0],terms.parse('금융, 중국')).matched_condition_count,2);
});
