// Local-only review server: real IDN DB reads, no production writes/deploy.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {handleIdnPolicy} from './search-api.mjs';
const require=createRequire(import.meta.url),{loadEnvFile}=require('../lib/load-env.js');
const index=process.argv.indexOf('--env-file');
if(index<0||!process.argv[index+1])throw Error('--env-file PATH required');
loadEnvFile(process.argv[index+1]);
const geminiIndex=process.argv.indexOf('--gemini-env-file');
if(geminiIndex>=0&&process.argv[geminiIndex+1]){loadEnvFile(process.argv[geminiIndex+1]);process.env.IDN_SEMANTIC_ENABLED='true';}
if(!process.env.SUPABASE_URL||!process.env.SUPABASE_SERVICE_ROLE_KEY)throw Error('Missing server credentials');
const files={'/indonesia-policy/':['index.html','text/html; charset=utf-8'],
 '/indonesia-policy/mail-regions.json':['mail-regions.json','application/json; charset=utf-8'],
 '/indonesia-policy/search.mjs':['search.mjs','text/javascript; charset=utf-8'],
 '/indonesia-policy/source-links.mjs':['source-links.mjs','text/javascript; charset=utf-8'],
 '/indonesia-policy/legal-effect.mjs':['legal-effect.mjs','text/javascript; charset=utf-8'],
 '/indonesia-policy/result-groups.mjs':['result-groups.mjs','text/javascript; charset=utf-8'],
 '/indonesia-policy/subscriptions.mjs':['subscriptions.mjs','text/javascript; charset=utf-8'],
 '/indonesia-policy/subscription-client.mjs':['subscription-client.mjs','text/javascript; charset=utf-8'],
 '/auth-config.js':['../auth-config.js','text/javascript; charset=utf-8'],
 '/indonesia-policy/search.css':['search.css','text/css; charset=utf-8']};
http.createServer(async(req,res)=>{
 try{
  const path=new URL(req.url,'http://localhost').pathname;
  if(path.startsWith('/api/idn/')){
   const response=await handleIdnPolicy(new Request('http://localhost'+req.url,{method:req.method}),process.env);
   res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));return;
  }
  const file=files[path];if(!file){res.writeHead(404);res.end('Not found');return;}
  const data=await readFile(fileURLToPath(new URL('../../New for anti/indonesia-policy/'+file[0],import.meta.url)));
  res.writeHead(200,{'Content-Type':file[1],'Cache-Control':'no-store'});res.end(data);
 }catch{res.writeHead(500);res.end('Local preview unavailable');}
}).listen(4317,'127.0.0.1',()=>console.log('IDN preview: http://127.0.0.1:4317/indonesia-policy/'));
