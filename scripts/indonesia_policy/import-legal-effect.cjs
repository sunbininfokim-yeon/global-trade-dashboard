'use strict';
// Reviewed evidence only. No AI, downloads, scheduler, mail or document mutation.
const fs=require('node:fs'),{createHash}=require('node:crypto');
const {loadEnvFile}=require('../lib/load-env'),{request}=require('./client.cjs');
async function main(){
 const args=process.argv.slice(2),i=args.indexOf('--env-file');
 if(!args[0]||i<0||!args[i+1])throw Error('PACK --env-file PATH [--write]');
 const pack=JSON.parse(fs.readFileSync(args[0],'utf8'));
 if(pack.country!=='IDN'||!Array.isArray(pack.findings)||pack.findings.length>100)throw Error('Invalid legal-effect pack');
 for(const f of pack.findings){
  const {finding_id,...r}=f;
  // IDs guard immutable replays; literal evidence and dates are separately reviewed.
  const sorted=Object.fromEntries(Object.entries(r).sort(([a],[b])=>a.localeCompare(b,'en')));
  if(finding_id!=='idn-effect-'+createHash('sha256').update(JSON.stringify(sorted)).digest('hex'))throw Error('Invalid immutable finding ID');
 }
 console.log(JSON.stringify({mode:args.includes('--write')?'write':'preview',findings:pack.findings.length,subjects:new Set(pack.findings.map(f=>f.subject_id)).size}));
 if(!args.includes('--write'))return;
 loadEnvFile(args[i+1]);let added=0;
 for(const item of pack.inventory||[])await request('rpc/idn_store_coverage',{method:'POST',body:{p_item:item}});
 for(const record of pack.findings)added+=Number(await request('rpc/idn_store_legal_effect',{method:'POST',body:{p_record:record}}));
 const result=await request('rpc/idn_legal_effect',{method:'POST',body:{p_document_ids:[...new Set(pack.findings.map(f=>f.subject_id))]}});
 console.log(JSON.stringify({added,assessments:result.items.map(({document_id,status,transition_review_required})=>({document_id,status,transition_review_required}))}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
