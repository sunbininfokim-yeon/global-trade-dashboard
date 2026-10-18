'use strict';
// One-time administrative backup of the old IDN tables before schema move.
const fs=require('node:fs');
const {loadEnvFile}=require('../lib/load-env');
const {supabaseGet}=require('../lib/sync-utils');
async function main(){
 const [envPath,outputPath]=process.argv.slice(2);
 if(!envPath||!outputPath)throw Error('env path and private backup path required');
 loadEnvFile(envPath);
 const backup={at:new Date().toISOString(),tables:{}};
 for(const table of ['idn_policy_documents','idn_policy_versions','idn_policy_source_checks']){
  backup.tables[table]=await supabaseGet(table,{select:'*',limit:1000});
  if(backup.tables[table].length===1000)throw Error('Refuse a possibly truncated backup');
 }
 fs.writeFileSync(outputPath,JSON.stringify(backup,null,2),{mode:0o600,flag:'wx'});
 console.log(JSON.stringify({backup:outputPath,counts:Object.fromEntries(Object.entries(backup.tables).map(([k,v])=>[k,v.length]))}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
