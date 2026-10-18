const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{createHash}=require('node:crypto');
const paths=[process.env.IDN_TEST_NODE_MODULES||__dirname];
const {PGlite}=require(require.resolve('@electric-sql/pglite',{paths}));
const files=['20261017080335_indonesia_policy_corpus.sql','20261017080543_indonesia_policy_source_checks.sql','20261018112152_indonesia_policy_isolation.sql','20261018112503_indonesia_policy_biofuel.sql','20261018113918_indonesia_policy_search.sql','20261018161434_indonesia_policy_government_sources.sql','20261018223817_indonesia_policy_value_chain_search.sql','20261018223822_indonesia_policy_document_embeddings.sql','20261018224504_indonesia_policy_keyword_boundaries.sql'];
test('value-chain hard filters, current-version embeddings, replay and server-only vector access',async()=>{
 const {vector}=await import(pathToFileURL(require.resolve('@electric-sql/pglite-pgvector',{paths})).href);
 const db=new PGlite({extensions:{vector}});
 try{
  await db.exec("create role anon;create role authenticated;create role service_role bypassrls;create schema extensions;create table public.bills(id text);insert into public.bills values('us-sentinel');");
  for(const file of files)await db.exec(fs.readFileSync(path.join(__dirname,'../../supabase/migrations',file),'utf8'));
  const text='UNDANG-UNDANG kepentingan TEST CURRENT FINAL TEXT '+ 'Test '.repeat(60),hash=createHash('sha256').update(text).digest('hex');
  const d={document_id:'idn-test-copper-vector',country_code:'IDN',title:'Exploration',title_ko:'탐사',issuer_name:'Ministry',issuer_level:'national',jurisdiction:'Indonesia',document_type:'Perpres',document_number:'test-copper',document_year:2026,topics:['copper','stream_upstream'],primary_stage:'mineral_mining',scope_note:'Test only',source_url:'https://example.go.id/doc',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-19T00:00:00Z',content_hash:hash,content_kind:'official_text',text_content:text,text_truncated:false};
  await db.query('select public.idn_store_document($1)',[JSON.stringify(d)]);
  await db.exec('set role service_role');
  assert.equal((await db.query("select policy_idn.matches_alias('kepentingan','tin') m")).rows[0].m,false);
  assert.equal((await db.query("select policy_idn.matches_alias('tin exports','tin') m")).rows[0].m,true);
  const queued=(await db.query('select public.idn_embedding_queue() q')).rows[0].q;assert.equal(queued.length,1);
  const v=Array(1536).fill(0);v[0]=1;
  const payload={document_id:d.document_id,source_hash:hash,metadata_hash:queued[0].metadata_hash,input_hash:'a'.repeat(64),model:'gemini-embedding-001',profile_version:'overview-v1',input_chars:100,embedding:v};
  const save=async p=>db.query('select public.idn_store_embedding($1)',[JSON.stringify(p)]);
  await assert.rejects(save({...payload,source_hash:'b'.repeat(64)}));await save(payload);await save(payload);
  assert.equal((await db.query('select public.idn_embedding_queue() q')).rows[0].q.length,0);
  const search=async(stream,all=false,topic='copper',vec=v)=>(await db.query("select public.idn_search_documents_v2(p_terms=>'[{\"term\":\"unmatched\",\"aliases\":[\"unmatched\"]}]',p_topic=>$1,p_stream=>$2,p_require_all=>$3,p_query_embedding=>$4) s",[topic,stream,all,vec])).rows[0].s;
  let r=await search('upstream');assert.equal(r.total,1);assert.equal(r.items[0].matched_condition_count,0);assert.ok(r.items[0].semantic_similarity>0.999);assert.equal(r.search_mode,'hybrid_overview');
  assert.equal((await search('midstream')).total,0);assert.equal((await search('upstream',false,'tin')).total,0);assert.equal((await search('upstream',true)).total,0);
  await assert.rejects(search('invalid'));await assert.rejects(search('upstream',false,'copper',[1]));
  await db.exec('reset role');
  for(const file of files.slice(-3))await db.exec(fs.readFileSync(path.join(__dirname,'../../supabase/migrations',file),'utf8'));
  assert.equal((await search('upstream')).total,1);
  await db.query("update policy_idn.documents set scope_note='new metadata' where document_id=$1",[d.document_id]);
  assert.equal((await search('upstream')).total,0);await assert.rejects(save(payload));
  assert.equal((await db.query('select public.idn_embedding_queue() q')).rows[0].q.length,1);
  for(const role of ['anon','authenticated']){
   await db.exec('reset role;set role '+role);await assert.rejects(search('upstream'));await assert.rejects(db.query('select public.idn_embedding_queue()'));await assert.rejects(db.query('select * from policy_idn.document_embeddings'));
  }
  await db.exec('reset role');assert.equal((await db.query('select * from public.bills')).rows[0].id,'us-sentinel');
 }finally{await db.close();}
});
