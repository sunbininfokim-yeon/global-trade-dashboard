'use strict';
// Service-only review CLI. Never enables delivery or calls Resend.
const fs=require('node:fs');
const {loadEnvFile}=require('../lib/load-env'),{request}=require('./client.cjs');
async function main(){
 const args=process.argv.slice(2),i=args.indexOf('--env-file');
 if(i<0||!args[i+1])throw Error('--env-file PATH [--review FILE --write] [--enqueue CHANGE_ID --write]');
 loadEnvFile(args[i+1]);const review=args.indexOf('--review'),enqueue=args.indexOf('--enqueue'),write=args.includes('--write');
 if(review>=0){
  const pack=JSON.parse(fs.readFileSync(args[review+1],'utf8'));
  if(pack.country!=='IDN'||!pack.change_id||!pack.review)throw Error('Invalid review pack');
  if(write)await request('rpc/idn_review_mail_change',{method:'POST',body:{p_change_id:pack.change_id,p_review:pack.review}});
  console.log(JSON.stringify({mode:write?'reviewed':'preview','change_id':pack.change_id,note:write?'Review saved; eligible events enqueue automatically when IDN delivery is enabled':'Local preview only; DB evidence validation runs on --write'}));return;
 }
 if(enqueue>=0){console.log(JSON.stringify(await request('rpc/idn_enqueue_mail_change',{method:'POST',body:{p_change_id:args[enqueue+1],p_write:write}})));return;}
 console.log(JSON.stringify(await request('rpc/idn_mail_review_queue',{method:'POST',body:{p_limit:20}})));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
