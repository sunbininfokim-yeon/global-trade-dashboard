const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const terms=require('../../scripts/lib/policy-search-terms');
const source=fs.readFileSync(require.resolve('../../_worker.js'),'utf8').replace(/^import .*;\n/gm,'').replace('export default {','const handler = {');
function harness(fetch) {
  const ctx={URL,URLSearchParams,Response,Request,Headers,AbortSignal,console,fetch,PolicySearchTerms:terms,PolicyEvidence:{},setTimeout,clearTimeout};
  vm.createContext(ctx);vm.runInContext(source+'\nthis.api={usConditionSearch,usHybridSearch,usCorpusVectors};',ctx);return ctx.api;
}
const base={bill_id:'119-hjres-72',title:'Relating to a national emergency',summary:null,congress_number:119,bill_type:'hjres',bill_number:72,congress_url:'https://www.congress.gov/bill/119th-congress/house-joint-resolution/72'};
const proof=[{field:'cited_document',text:'Canada tariffs',source_url:'https://www.govinfo.gov/content/pkg/DCPD-202500209/html/DCPD-202500209.htm',target_type:'executive_order',target_id:'14193',citation_url:base.congress_url}];
test('Worker conditions retain refreshed evidence when legacy rows are hydrated again; no provider required',async()=>{
  const fetch=async(url,options={})=>{
    const u=new URL(url);
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
    if(u.pathname.endsWith('/rpc/search_policy_document_terms'))return Response.json([{source_type:'public_law',source_id:'118-public-1',evidence_parts:[{field:'body',text:'Canada tariffs',source_url:'https://www.govinfo.gov/x'}],coverage:{text_status:'body'},refresh_pending:false}]);
    if(u.pathname.endsWith('/public_laws'))return Response.json([{public_law_id:'118-public-1',law_title:'Trade law',govinfo_url:'https://www.govinfo.gov/x'}]);
    return Response.json([]);
  };
  const result=await harness(fetch).usHybridSearch({SUPABASE_URL:'https://example.test',SUPABASE_SERVICE_ROLE_KEY:'test'},{query:'캐나다',limit:20});
  assert.equal(result.body.items[0].source_url,'https://www.govinfo.gov/x');assert.equal(result.body.items[0].type,'public_law');
});
