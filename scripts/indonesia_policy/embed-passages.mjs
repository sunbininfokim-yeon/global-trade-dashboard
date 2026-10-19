// Bounded reviewed passages only, explicitly invoked; private cache precedes DB writes.
import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {createRequire} from 'node:module';
import {MODEL,embedTexts,normalizeVector} from './embeddings.mjs';
const require=createRequire(import.meta.url),{loadEnvFile}=require('../lib/load-env.js'),{request}=require('./client.cjs');
export function passageText(d){
 const text=['Country: Indonesia. Reviewed source excerpt; current legal effect and applicability unverified.',d.document_id,d.article,d.interpretation_ko,d.quote].join('\n');
 if(text.length>6000)throw Error('Reviewed passage exceeds embedding budget');return text;
}
export async function main(args=process.argv.slice(2)){
 const val=k=>args[args.indexOf(k)+1];if(!args.includes('--env-file'))throw Error('--env-file required');loadEnvFile(val('--env-file'));
 if(args.includes('--gemini-env-file'))loadEnvFile(val('--gemini-env-file'));
 const limit=Number(args.includes('--limit')?val('--limit'):30);if(!Number.isInteger(limit)||limit<1||limit>100)throw Error('Invalid limit');
 const rows=await request('rpc/idn_passage_embedding_queue',{method:'POST',body:{p_limit:limit}}),texts=rows.map(passageText);
 console.log(JSON.stringify({mode:args.includes('--write')?'write':'preview',passages:rows.length,inputCharacters:texts.reduce((n,t)=>n+t.length,0),profile:'passage-v1'}));
 if(!args.includes('--write'))return;
 if(!args.includes('--cache-dir'))throw Error('--cache-dir required');
 const cache=path.resolve(val('--cache-dir')),repo=path.resolve(new URL('../..',import.meta.url).pathname);
 if(cache===repo||cache.startsWith(repo+path.sep))throw Error('Private cache must be outside repo');fs.mkdirSync(cache,{recursive:true,mode:0o700});fs.chmodSync(cache,0o700);
 let generated=0,cached=0,stored=0;
 for(let i=0;i<rows.length;i+=8){const b=rows.slice(i,i+8),t=texts.slice(i,i+8),hashes=t.map(x=>createHash('sha256').update(MODEL+'\npassage-v1\n'+x).digest('hex')),vectors=[],missing=[];
  for(let j=0;j<b.length;j++){const f=path.join(cache,hashes[j]+'.json');if(fs.existsSync(f)){vectors[j]=normalizeVector(JSON.parse(fs.readFileSync(f,'utf8')));cached++;}else missing.push(j);}
  if(missing.length){const v=await embedTexts(missing.map(j=>t[j]),process.env.GEMINI_API_KEY||process.env.GOOGLE_API_KEY);for(let k=0;k<missing.length;k++){const j=missing[k],f=path.join(cache,hashes[j]+'.json');vectors[j]=v[k];fs.writeFileSync(f+'.tmp',JSON.stringify(v[k]),{mode:0o600});fs.renameSync(f+'.tmp',f);generated++;}}
  for(let j=0;j<b.length;j++){await request('rpc/idn_store_passage_embedding',{method:'POST',body:{p_document:{review_id:b[j].review_id,input_hash:hashes[j],model:MODEL,profile_version:'passage-v1',input_chars:t[j].length,embedding:vectors[j]}}});stored++;}
  console.log(JSON.stringify({generated,cached,stored}));
 }
}
if(process.argv[1]&&path.resolve(process.argv[1])===path.resolve(new URL(import.meta.url).pathname))main().catch(e=>{console.error(e.message);process.exitCode=1;});
