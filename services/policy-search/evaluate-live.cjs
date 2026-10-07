// Read-only DB/embedding benchmark. Private env and vector cache never enter reports.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
require(root+'/scripts/lib/load-env').loadEnvFile(process.env.POLICY_ENV_FILE||path.join(process.env.HOME,'Documents/global-trade-dashboard-local/.env.local'));
require(root+'/scripts/lib/load-env').loadEnvFile(process.env.POLICY_EMBED_ENV_FILE||path.join(process.env.HOME,'Documents/New for anti/google_studio_key.env'));
const env={SUPABASE_URL:process.env.SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY:process.env.SUPABASE_SERVICE_ROLE_KEY,
 AI_STUDIO_API_KEY:process.env.AI_STUDIO_API_KEY||process.env.GEMINI_API_KEY||process.env.GOOGLE_API_KEY};
if(!env.SUPABASE_SERVICE_ROLE_KEY||!env.AI_STUDIO_API_KEY)throw Error('Required local credentials unavailable');
const baseline=process.env.POLICY_SEARCH_BASELINE_PREFIX;
if(!baseline)throw Error('Provide a frozen baseline prefix via POLICY_SEARCH_BASELINE_PREFIX');
const cacheDir=process.env.POLICY_SEARCH_EVAL_CACHE||'/private/tmp/policy-search-eval-20261006';fs.mkdirSync(cacheDir,{recursive:true,mode:0o700});
let providerCalls=0;const inflight=new Map();
async function cachedFetch(url,options={}){
 const key=crypto.createHash('sha256').update((url.includes('search_policy_vectors_for_type')?'quality-ann-v4:':url.includes('search_policy_balanced_terms')?'quality-ann-v2:':'')+url+String(options.body||'')).digest('hex'),file=path.join(cacheDir,key+'.json');
 if(fs.existsSync(file))return Response.json(JSON.parse(fs.readFileSync(file)),{status:200});
 if(process.env.POLICY_SEARCH_EVAL_CACHE_ONLY==='1')return Response.json({message:'snapshot not cached'},{status:503});
 if(inflight.has(key))return Response.json(await inflight.get(key));
 const request=(async()=>{
  if(url.includes('generativelanguage.googleapis.com'))providerCalls++;
  const response=await fetch(url,{...options,signal:AbortSignal.timeout(60000)});
  if(!response.ok)throw Object.assign(Error('Read-only request failed'),{status:response.status});
  const data=await response.json();fs.writeFileSync(file,JSON.stringify(data),{mode:0o600});return data;
 })();inflight.set(key,request);
 try{return Response.json(await request);}catch(e){return Response.json({message:'request failed'},{status:e.status||503});}finally{inflight.delete(key);}
}
function harness(workerFile,termFile){
 const terms=require(termFile);const source=fs.readFileSync(workerFile,'utf8').replace(/^import .*;\n/gm,'').replace('export default {','const handler = {');
 const ctx={URL,URLSearchParams,Response,Request,Headers,AbortSignal,console,fetch:cachedFetch,PolicySearchTerms:terms,
  PolicyEvidence:require(root+'/New for anti/policy-evidence'),setTimeout,clearTimeout};
 vm.createContext(ctx);vm.runInContext(source+'\nthis.search=usSearch;',ctx);
 return async query=>{const started=Date.now();try{
  const r=await ctx.search(env,{query,conditions:terms.parse(query),limit:20});
  return {semantic_available:r.body.semantic_available,elapsed_ms:Date.now()-started,items:r.body.items.map(i=>({id:i.type+':'+i.id,score:i.similarity_score,matched:i.matched_condition_count,relationship:i.condition_relationship}))};
 }catch{return {error:'search_unavailable',elapsed_ms:Date.now()-started,items:[]};}};
}
const before=harness(baseline+'-worker.js',baseline+'-terms.js'),after=harness(root+'/_worker.js',root+'/scripts/lib/policy-search-terms.js');
const cases=require('./evaluation/queries.json').cases.slice(0,Number(process.env.POLICY_SEARCH_EVAL_LIMIT)||50);
(async()=>{
 const rows=[];
 for(let offset=0;offset<cases.length;offset+=2){
  rows.push(...await Promise.all(cases.slice(offset,offset+2).map(async c=>{
   const b=await before(c.query),a=await after(c.query);
   const rank=r=>{const n=r.items.findIndex(i=>c.expected.includes(i.id));return n<0?null:n+1;};
   return {...c,before:{...b,expected_rank:rank(b)},after:{...a,expected_rank:rank(a)}};
  })));
  console.log(JSON.stringify({completed:rows.length,total:cases.length}));
 }
 const metric=kind=>({found_at_20:rows.filter(r=>r[kind].expected_rank).length,total:rows.length,
  mrr:rows.reduce((sum,r)=>sum+(r[kind].expected_rank?1/r[kind].expected_rank:0),0)/rows.length,
  known_negative_checks:rows.filter(r=>r.not_expected).length,known_negative_hits:rows.filter(r=>r.not_expected?.some(id=>r[kind].items.some(i=>i.id===id))).length,
  errors:rows.filter(r=>r[kind].error).length,semantic_available:rows.filter(r=>r[kind].semantic_available).length});
 const report={generated_at:new Date().toISOString(),scope:'Mac VM Worker with live public policy DB; not deployed UI; known positives only; REST/vector responses cached for comparable source snapshots',provider_calls:providerCalls,before:metric('before'),after:metric('after'),rows};
 const out=process.env.POLICY_SEARCH_EVAL_REPORT||path.join(root,'services/policy-search/evaluation/results-20261006.json');
 fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({...report,rows:undefined}));
})().catch(()=>{console.error('Evaluation failed; credentials and provider payloads omitted.');process.exitCode=1;});
