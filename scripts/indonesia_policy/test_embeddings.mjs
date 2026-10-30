import {test} from 'node:test';import assert from 'node:assert/strict';
import {overviewText,embedTexts,normalizeVector} from './embeddings.mjs';
import {createHandler,parseTerms} from './search-api.mjs';
const unit=Array(1536).fill(0);unit[0]=1;
test('overview keeps provenance boundaries; provider task, dimension and failure are explicit',async()=>{
 const d={title:'test',title_ko:'시험',topics:['bauxite','stream_midstream'],scope_note:'Review only',source_excerpt:'NAVIGATION NOT LEGAL TEXT',content_kind:'official_metadata'};
 assert.ok(!overviewText(d).includes(d.source_excerpt));assert.ok(overviewText(d).includes('not a full statute'));
 assert.throws(()=>normalizeVector(Array(1536).fill(0)));assert.throws(()=>normalizeVector([NaN]));
 const vector=await embedTexts(['test'],'secret','RETRIEVAL_DOCUMENT',async(url,o)=>{
  const b=JSON.parse(o.body);assert.equal(b.requests[0].taskType,'RETRIEVAL_DOCUMENT');assert.equal(b.requests[0].outputDimensionality,1536);
  return Response.json({embeddings:[{values:unit}]});
 });assert.equal(vector.length,1);
 await assert.rejects(embedTexts(['test'],'secret','RETRIEVAL_QUERY',async()=>new Response('sensitive',{status:429})),/HTTP 429/);
});
test('hybrid calls are opt-in, validate before charging and reuse query vectors across pages',async()=>{
 let calls=0;const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'server',GEMINI_API_KEY:'private',IDN_SEMANTIC_ENABLED:'true'};
 const handler=createHandler(async(url,o)=>{
  if(url.includes('googleapis.com')){calls++;return Response.json({embeddings:[{values:unit}]});}
  assert.ok(url.endsWith('/idn_search_documents_v2'));
  const args=JSON.parse(o.body);assert.equal(args.p_stream,'midstream');assert.equal(args.p_topic,'bauxite');assert.equal(args.p_query_embedding.length,1536);
  return Response.json({country:'IDN',items:[],total:0});
 });
 const url='https://site/api/idn/search?q=보크사이트,제련&topic=bauxite&stream=midstream&mode=hybrid';
 assert.equal((await handler(new Request(url),{...env,IDN_SEMANTIC_ENABLED:'false'})).status,503);assert.equal(calls,0);
 assert.equal((await handler(new Request(url+'&type=invalid'),env)).status,400);assert.equal(calls,0);
 assert.equal((await handler(new Request(url),env)).status,200);
 assert.equal((await handler(new Request(url+'&offset=20'),env)).status,200);assert.equal(calls,1);
 assert.ok(parseTerms('보크사이트,제련')[0].aliases.includes('bauksit'));
});
