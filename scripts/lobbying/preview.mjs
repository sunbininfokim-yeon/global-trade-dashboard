// Local visual QA with an explicitly supplied source snapshot. Never a production sink.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {handleLobbying} from './api.mjs';

const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const input=process.argv[2];
if(!input)throw Error('Usage: node scripts/lobbying/preview.mjs <source-snapshot.json>');
const snapshot=JSON.parse(await fs.readFile(input,'utf8'));
const assets=path.join(repo,'New for anti');
const read=async(_env,table,query)=>{
  const q=new URLSearchParams(query);
  if(table!=='lobby_records')return [];
  let rows=snapshot.items;
  if(q.has('record_id'))rows=rows.filter(x=>x.record_id===q.get('record_id').slice(3));
  if(q.has('source'))rows=rows.filter(x=>x.source===q.get('source').slice(3));
  if(q.has('search_vector')){
    const term=q.get('search_vector').split('.').slice(1).join('.').toLowerCase();
    rows=rows.filter(x=>JSON.stringify([x.client_name,x.registrant_name,x.title,x.body_text]).toLowerCase().includes(term));
  }
  if(q.has('topics'))rows=rows.filter(x=>x.topics.includes(q.get('topics').slice(4,-1)));
  if(q.has('or')){const country=q.get('or').match(/\{([A-Z]{2})\}/)?.[1];rows=rows.filter(x=>x.country_codes.includes(country)||x.related_countries.includes(country));}
  const offset=Number(q.get('offset')||0);return rows.slice(offset,offset+Number(q.get('limit')||50));
};
const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://127.0.0.1:8769');
    if(url.pathname.startsWith('/api/us/lobbying')){
      const response=await handleLobbying(new Request(url),{},read,async()=>snapshot);
      res.writeHead(response.status,Object.fromEntries(response.headers));res.end(await response.text());return;
    }
    if(url.pathname==='/'||url.pathname.startsWith('/policy/us')){
      res.setHeader('Content-Type','text/html; charset=utf-8');
      res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>로비·사안 source snapshot preview</title><style>body{margin:0;background:#171d26;color:#e8edf4;font-family:system-ui}button,input,select{font:inherit}.policy-surface-inner{padding:18px}.policy-modes{display:flex;gap:8px;align-items:center}.policy-search,.policy-crumb{display:none}.policy-mode-btn{padding:9px;background:#26374b;color:white;border:0;border-radius:5px}.policy-country{margin-right:8px}</style><main id="surface"></main><script src="/policy-evidence.js"></script><script src="/policy.js"></script><script>USPolicy.render("us-policy-hub",document.getElementById("surface"))</script>');return;
    }
    const file=path.resolve(assets,'.'+decodeURIComponent(url.pathname));
    if(!file.startsWith(assets+path.sep)){res.writeHead(403);res.end();return;}
    const types={'.mjs':'text/javascript','.js':'text/javascript','.css':'text/css'};
    res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file));
  }catch(error){res.writeHead(500);res.end(error.message);}
});
server.listen(8769,'127.0.0.1',()=>console.log('Source snapshot preview http://127.0.0.1:8769/policy/us/lobbying'));
