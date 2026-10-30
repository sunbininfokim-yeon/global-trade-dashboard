// Explicit local operation. Dry run by default; cache vectors before DB commits.
import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {createRequire} from 'node:module';
import {MODEL,PROFILE,overviewText,embedTexts,normalizeVector} from './embeddings.mjs';
const require=createRequire(import.meta.url),{loadEnvFile}=require('../lib/load-env.js'),{request}=require('./client.cjs');
const args=process.argv.slice(2),value=(key)=>args[args.indexOf(key)+1];
if(!args.includes('--env-file'))throw Error('--env-file required');loadEnvFile(value('--env-file'));
if(args.includes('--gemini-env-file'))loadEnvFile(value('--gemini-env-file'));
const limit=Number(args.includes('--limit')?value('--limit'):100);if(!Number.isInteger(limit)||limit<1||limit>100)throw Error('limit must be 1..100');
const rows=await request('rpc/idn_embedding_queue',{method:'POST',body:{p_limit:limit}}),texts=rows.map(overviewText);
console.log(JSON.stringify({mode:args.includes('--write')?'write':'dry_run',documents:rows.length,inputCharacters:texts.reduce((n,t)=>n+t.length,0),model:MODEL,profile:PROFILE}));
if(args.includes('--write')){
 if(!args.includes('--cache-dir'))throw Error('--cache-dir outside repository required');
 const cache=path.resolve(value('--cache-dir')),repo=path.resolve(new URL('../..',import.meta.url).pathname);
 if(cache===repo||cache.startsWith(repo+path.sep))throw Error('Cache must be outside repository');
 fs.mkdirSync(cache,{recursive:true,mode:0o700});fs.chmodSync(cache,0o700);
 let providerVectors=0,cachedVectors=0,stored=0;
 for(let i=0;i<rows.length;i+=8){
  const batch=rows.slice(i,i+8),batchTexts=texts.slice(i,i+8),missing=[],vectors=[];
  const hashes=batchTexts.map(t=>createHash('sha256').update(MODEL+'\n'+PROFILE+'\n'+t).digest('hex'));
  for(let j=0;j<batch.length;j++){
   const file=path.join(cache,hashes[j]+'.json');
   if(fs.existsSync(file)){vectors[j]=normalizeVector(JSON.parse(fs.readFileSync(file,'utf8')));cachedVectors++;}else missing.push(j);
  }
  if(missing.length){
   const generated=await embedTexts(missing.map(j=>batchTexts[j]),process.env.GEMINI_API_KEY||process.env.GOOGLE_API_KEY);
   for(let k=0;k<missing.length;k++){
    const j=missing[k],file=path.join(cache,hashes[j]+'.json');vectors[j]=generated[k];
    fs.writeFileSync(file+'.tmp',JSON.stringify(vectors[j]),{mode:0o600});fs.renameSync(file+'.tmp',file);providerVectors++;
   }
  }
  for(let j=0;j<batch.length;j++){
   const d=batch[j];await request('rpc/idn_store_embedding',{method:'POST',body:{p_document:{document_id:d.document_id,source_hash:d.content_hash,metadata_hash:d.metadata_hash,input_hash:hashes[j],model:MODEL,profile_version:PROFILE,input_chars:batchTexts[j].length,embedding:vectors[j]}}});stored++;
  }
  console.log(JSON.stringify({stored,providerVectors,cachedVectors}));
 }
}
