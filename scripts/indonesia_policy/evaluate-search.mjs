// Explicit read-only live evaluation. Keyword mode never calls a paid AI provider.
import fs from 'node:fs';
import path from 'node:path';
import {loadEnvFile} from '../lib/load-env.js';
import {handleIdnPolicy,parseTerms,TOPICS} from './search-api.mjs';

export function validateCases(pack){
 if(pack?.country!=='IDN'||!Array.isArray(pack.cases)||!pack.cases.length||pack.cases.length>20)throw Error('Invalid bounded IDN evaluation');
 for(const c of pack.cases){
  if(typeof c.query!=='string'||!c.query.trim()||!Object.hasOwn(TOPICS,c.topic)||!/^idn-[a-z0-9-]+$/.test(c.expected_id)||parseTerms(c.query).length!==c.condition_count)throw Error('Invalid IDN evaluation case');
 }
 return pack.cases;
}
export function evaluateResult(c,data){
 const hit=data?.items?.find(d=>d.document_id===c.expected_id);
 const failures=[];
 if(data?.country!=='IDN')failures.push('wrong_country');
 if(data?.search_mode!=='keyword_alias')failures.push('wrong_search_mode');
 if(!hit)failures.push('expected_document_missing');
 if(hit&&(hit.matched_condition_count!==c.condition_count||hit.total_condition_count!==c.condition_count))failures.push('conditions_not_all_matched');
 if(data?.passage_annotations_available!==true||!hit?.matched_passages?.length)failures.push('reviewed_passage_missing_or_unavailable');
 return {query:c.query,expected_id:c.expected_id,total:data?.total??null,matched:hit?.matched_condition_count??null,passages:hit?.matched_passages?.length??0,passed:failures.length===0,failures};
}
async function main(){
 const args=process.argv.slice(2),at=args.indexOf('--env-file');
 if(!args[0]||at<0||!args[at+1])throw Error('CASES.json --env-file /ABS/ENV');
 const cases=validateCases(JSON.parse(fs.readFileSync(args[0],'utf8')));
 loadEnvFile(args[at+1]);let failed=0;
 for(const c of cases){
  const url=new URL('http://localhost/api/idn/search');
  for(const [k,v] of Object.entries({q:c.query,topic:c.topic,match:'all',mode:'keyword',limit:'50'}))url.searchParams.set(k,v);
  const r=await handleIdnPolicy(new Request(url),process.env);
  if(!r.ok){failed++;console.log(JSON.stringify({query:c.query,passed:false,http_status:r.status}));continue;}
  const result=evaluateResult(c,await r.json());failed+=Number(!result.passed);console.log(JSON.stringify(result));
 }
 console.log(JSON.stringify({cases:cases.length,failed,mode:'keyword',paid_ai_calls:0}));
 if(failed)process.exitCode=1;
}
if(process.argv[1]&&path.resolve(process.argv[1])===path.resolve(new URL(import.meta.url).pathname))main().catch(e=>{console.error(e.message);process.exitCode=1;});
