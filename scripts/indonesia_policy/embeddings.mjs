// Text only, IDN-only overview profile. No translations or legal conclusions.
export const MODEL='gemini-embedding-001';
export const DIMENSIONS=1536;
export const PROFILE='overview-v1';
export function normalizeVector(values){
 if(!Array.isArray(values)||values.length!==DIMENSIONS||!values.every(Number.isFinite))throw Error('Invalid embedding dimensions');
 const n=Math.hypot(...values);if(!n)throw Error('Invalid zero embedding');return values.map(x=>x/n);
}
export function overviewText(d){
 return [`Country: Indonesia. Retrieval overview; current legal effect unverified.`,
  d.title_ko,d.title,`Review scope tags (not legal applicability): ${d.topics.join(', ')}`,
  d.scope_note,`Source kind: ${d.content_kind}. This is an overview, not a full statute embedding.`,
  d.content_kind==='official_text'?String(d.source_excerpt||'').slice(0,3000):'Official metadata only; full legal text not acquired.'].join('\n').slice(0,5400);
}
export async function embedTexts(texts,key,task='RETRIEVAL_DOCUMENT',fetcher=fetch){
 if(!key)throw Error('Missing Gemini credentials');
 if(!texts.length||texts.length>8||texts.some(t=>typeof t!=='string'||!t.trim()||t.length>6000))throw Error('Invalid embedding batch');
 if(!['RETRIEVAL_DOCUMENT','RETRIEVAL_QUERY'].includes(task))throw Error('Invalid retrieval task');
 const response=await fetcher(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:batchEmbedContents`,{
  method:'POST',headers:{'x-goog-api-key':key,'Content-Type':'application/json'},
  body:JSON.stringify({requests:texts.map(text=>({model:`models/${MODEL}`,content:{parts:[{text}]},taskType:task,outputDimensionality:DIMENSIONS}))}),signal:AbortSignal.timeout(25000)});
 if(!response.ok){await response.body?.cancel();throw Error(`Embedding provider HTTP ${response.status}`);}
 const body=await response.json();if(body.embeddings?.length!==texts.length)throw Error('Invalid embedding count');
 return body.embeddings.map(e=>normalizeVector(e.values));
}
