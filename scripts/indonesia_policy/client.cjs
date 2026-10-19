'use strict';
const SCHEMA = 'policy_idn';
const GATEWAY_SCHEMA = 'public';
const ROUTES = new Set(['rpc/idn_store_document','rpc/idn_store_source_check','rpc/idn_status','rpc/idn_embedding_queue','rpc/idn_store_embedding',
  'rpc/idn_store_coverage','rpc/idn_store_review','rpc/idn_passage_embedding_queue','rpc/idn_store_passage_embedding','rpc/idn_store_catalogue','rpc/idn_catalogue_status','rpc/idn_catalogue_gaps','rpc/idn_store_legal_effect','rpc/idn_legal_effect']);
async function request(path, {method='GET', body}={}) {
  if (!ROUTES.has(path) || method !== 'POST') throw Error('Not an IDN gateway RPC');
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw Error('Missing Supabase server credentials');
  // Dedicated IDN-only gateway; private policy_idn tables are not exposed.
  // Public is a transport namespace, never a fallback to US tables or RPCs.
  const headers = {apikey:key, 'Accept-Profile':GATEWAY_SCHEMA, 'Content-Profile':GATEWAY_SCHEMA};
  if (key.startsWith('eyJ')) headers.Authorization = `Bearer ${key}`;
  if (body !== undefined) headers['Content-Type']='application/json';
  const res=await fetch(`${url.replace(/\/$/,'')}/rest/v1/${path}`,{
    method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(45000),
  });
  const data=await res.json().catch(()=>null);
  if (!res.ok) {
    const error=Error(`IDN data API HTTP ${res.status} (${data?.code||'unknown'})`);
    error.code=data?.code;error.details=data;throw error;
  }
  return data;
}
module.exports={SCHEMA,request};
