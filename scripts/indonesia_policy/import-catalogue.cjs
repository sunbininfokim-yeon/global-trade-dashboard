'use strict';
// Inventory is not a law import or embedding job. Safe preview by default.
const fs=require('node:fs'),path=require('node:path');
const {loadEnvFile}=require('../lib/load-env'),{request}=require('./client.cjs');
async function main(){
 const args=process.argv.slice(2),i=args.indexOf('--env-file'),r=args.indexOf('--report-dir');
 if(!args[0]||i<0||!args[i+1])throw Error('CATALOGUE --env-file PATH [--write] [--report-dir OUTSIDE_REPO]');
 const data=JSON.parse(fs.readFileSync(args[0],'utf8'));
 if(data.country!=='IDN'||!Array.isArray(data.sources)||data.sources.length>30)throw Error('Invalid IDN inventory');
 const sources=data.sources.filter(s=>s.status!=='pending');
 console.log(JSON.stringify({mode:args.includes('--report-only')?'reconcile':args.includes('--write')?'write':'preview',sources:sources.map(s=>({id:s.source_id,status:s.status,records:s.records.length,pages:s.pages.length,pending:s.pending_urls.length}))}));
 if(args.includes('--report-only')&&args.includes('--write'))throw Error('Choose write or report-only');
 if(!args.includes('--write')&&!args.includes('--report-only'))return;
 loadEnvFile(args[i+1]);
 if(args.includes('--write'))for(const s of sources){
  if(!Array.isArray(s.records)||s.records.length>5000)throw Error('Inventory budget');
  console.log(JSON.stringify({source:s.source_id,...await request('rpc/idn_store_catalogue',{method:'POST',body:{p_snapshot:s}})}));
 }
 const status=await request('rpc/idn_catalogue_status',{method:'POST',body:{}});console.log(JSON.stringify(status));
 if(r>=0){
  const out=path.resolve(args[r+1]||''),repo=path.resolve(__dirname,'../..');
  if(out===repo||out.startsWith(repo+path.sep))throw Error('Report directory must be outside repository');
  fs.mkdirSync(out,{recursive:true,mode:0o700});fs.chmodSync(out,0o700);
  const items=[];let counts;
  for(let offset=0;offset<150000;offset+=200){
   const page=await request('rpc/idn_catalogue_gaps',{method:'POST',body:{p_limit:200,p_offset:offset}});
   if(page.country!=='IDN'||!Array.isArray(page.items))throw Error('Invalid gap response');
   counts=page.counts;items.push(...page.items);if(items.length>=page.total)break;
   if(offset>=10000)throw Error('Reconciliation report exceeds bounded offset');
  }
  fs.writeFileSync(path.join(out,'reconciliation.json'),JSON.stringify({status,counts,items},null,2),{mode:0o600});
  console.log(JSON.stringify({reconciliation:counts,reportItems:items.length}));
 }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
