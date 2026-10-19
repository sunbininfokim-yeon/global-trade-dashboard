'use strict';
// Explicit bounded import; read-only validation by default. No collector or AI calls.
const fs=require('node:fs');
const {loadEnvFile}=require('../lib/load-env'),{request}=require('./client.cjs');
async function main(){
 const args=process.argv.slice(2),i=args.indexOf('--env-file');if(!args[0]||i<0)throw Error('PACK --env-file PATH [--write]');
 const pack=JSON.parse(fs.readFileSync(args[0],'utf8'));
 if(pack.country!=='IDN'||!Array.isArray(pack.inventory)||pack.inventory.length>200||!Array.isArray(pack.records)||pack.records.length>100)throw Error('Invalid review pack');
 if(new Set(pack.inventory.map(x=>x.document_id)).size!==pack.inventory.length||new Set(pack.records.map(x=>x.review_id)).size!==pack.records.length)throw Error('Duplicate review IDs');
 for(const r of pack.records){const {review_id}=r;
  // Do not trust pack-generated IDs as proof of a legal fact: DB checks the source/quote.
  if(!/^idn-review-[a-f0-9]{64}$/.test(review_id)||!/^idn-/.test(r.document_id)||r.quote.length<60||r.quote.length>12000||!['relation','applicability','passage'].includes(r.record_type))throw Error('Invalid evidence');
 }
 console.log(JSON.stringify({mode:args.includes('--write')?'write':'preview',inventory:pack.inventory.length,records:pack.records.length,passages:pack.records.filter(r=>r.record_type==='passage').length}));
 if(!args.includes('--write'))return;
 loadEnvFile(args[i+1]);let inventoryChanged=0,evidenceAdded=0;
 for(const item of pack.inventory)inventoryChanged+=Number(await request('rpc/idn_store_coverage',{method:'POST',body:{p_item:item}}));
 for(const record of pack.records)evidenceAdded+=Number(await request('rpc/idn_store_review',{method:'POST',body:{p_record:record}}));
 console.log(JSON.stringify({inventoryChanged,evidenceAdded}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
