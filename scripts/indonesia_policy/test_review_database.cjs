const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{createHash}=require('node:crypto');
const paths=[process.env.IDN_TEST_NODE_MODULES||__dirname];
const {PGlite}=require(require.resolve('@electric-sql/pglite',{paths}));
const dir=path.join(__dirname,'../../supabase/migrations');
const files=fs.readdirSync(dir).filter(f=>f.includes('_indonesia_policy_')&&f.endsWith('.sql')).sort();
const hash=x=>createHash('sha256').update(x).digest('hex');
test('review evidence: literal source, immutable replay, missing targets, stale exclusion and national/local scope',async()=>{
 const {vector}=await import(pathToFileURL(require.resolve('@electric-sql/pglite-pgvector',{paths})).href),db=new PGlite({extensions:{vector}});
 try{
  await db.exec("create role anon;create role authenticated;create role service_role bypassrls;create schema extensions;create table public.bills(id text);insert into public.bills values('us-sentinel');");
  for(const f of files)await db.exec(fs.readFileSync(path.join(dir,f),'utf8'));
  await db.exec(fs.readFileSync(path.join(dir,files.at(-1)),'utf8'));
  const quote='Pasal 52 Menteri dapat memberikan fasilitas Sertifikasi berupa pembiayaan penghitungan dan verifikasi nilai TKDN.',text='PERATURAN 35 TAHUN 2025 '+quote+' Pasal 53 tata cara pelaporan. '.repeat(10);
  const d={document_id:'idn-test-review',country_code:'IDN',title:'TKDN',title_ko:'국산화율',issuer_name:'Ministry',issuer_level:'national',jurisdiction:'Indonesia',document_type:'Permenperin',document_number:'review-test',document_year:2025,topics:['nickel_mining','stream_midstream'],primary_stage:'mineral_mining',scope_note:'Test',source_url:'https://example.go.id/law',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-19T00:00:00Z',content_hash:hash(text),content_kind:'official_text',text_content:text,text_truncated:false};
  const saveDoc=doc=>db.query('select public.idn_store_document($1)',[JSON.stringify(doc)]);
  const save=rec=>db.query('select public.idn_store_review($1) changed',[JSON.stringify(rec)]);
  const item={document_id:'idn-test-missing',title:'Missing base',topics:['nickel_mining'],priority:1,reason:'Missing authoritative base text',discovery_url:'https://example.go.id/catalogue'};
  await db.exec('set role service_role');await saveDoc(d);await db.query('select public.idn_store_coverage($1)',[JSON.stringify(item)]);
  const coverage=(await db.query('select public.idn_coverage() s')).rows[0].s;assert.equal(coverage.missing,1);assert.equal(coverage.items[0].coverage_status,'missing');
  const base={document_id:d.document_id,source_hash:d.content_hash,article:'Pasal 52',quote,source_url:d.source_url,interpretation_ko:'인증 비용 지원 검토; 자동 지원 자격 아님'};
  const relation={...base,review_id:'idn-review-'+hash('relation'),record_type:'relation',target_id:item.document_id,relation_type:'implements'};
  assert.equal((await save(relation)).rows[0].changed,true);assert.equal((await save(relation)).rows[0].changed,false);
  await assert.rejects(save({...relation,interpretation_ko:'Different immutable review'}));
  await assert.rejects(save({...relation,review_id:'idn-review-'+hash('fake'),quote:'This quotation is invented and never appeared in the official legal document we collected.'}));
  await assert.rejects(save({...relation,review_id:'idn-review-'+hash('url'),source_url:'https://other.go.id/law'}));
  const app={...base,review_id:'idn-review-'+hash('app'),record_type:'applicability',operator_roles:['smelter'],business_issues:['local_content'],geographic_scope:'national_framework'};
  await save(app);
  const passage={...base,review_id:'idn-review-'+hash('passage'),record_type:'passage'};await save(passage);
  const context=async id=>(await db.query('select public.idn_document_context($1) s',[id])).rows[0].s;
  let c=await context(d.document_id);assert.equal(c.relations[0].target_stored,false);assert.equal(c.passages.length,1);assert.equal(c.legal_status,'unverified');
  assert.equal((await context(item.document_id)).relations.length,1);
  const business=async region=>(await db.query("select public.idn_business_search('smelter',$1) s",[region])).rows[0].s;
  assert.equal((await business('Kalimantan Timur')).items.length,1);
  const local={...app,review_id:'idn-review-'+hash('local'),geographic_scope:'specified_regions',applicable_regions:['Kalimantan Timur']};await save(local);
  assert.equal((await business('Kalimantan Timur')).items[0].evidence.length,2);
  assert.equal((await business('Sulawesi Tengah')).items[0].evidence.length,1);
  const terms=JSON.stringify([{term:'국산화율',aliases:['tkdn']}]);
  const search=async()=> (await db.query('select public.idn_search_passages($1,$2) s',[[d.document_id],terms])).rows[0].s;
  assert.equal((await search()).items[0].matched_condition_count,1);
  assert.equal((await db.query('select public.idn_search_passages($1,$2) s',[['idn-other'],terms])).rows[0].s.items.length,0);
  const queued=(await db.query('select public.idn_passage_embedding_queue() s')).rows[0].s;assert.equal(queued.length,1);
  const v=Array(1536).fill(0);v[0]=1;
  await db.query('select public.idn_store_passage_embedding($1)',[JSON.stringify({review_id:passage.review_id,input_hash:hash('input'),model:'gemini-embedding-001',profile_version:'passage-v1',input_chars:200,embedding:v})]);
  assert.equal((await db.query('select public.idn_passage_embedding_queue() s')).rows[0].s.length,0);
  const semantic=(await db.query('select public.idn_search_passages($1,$2,$3) s',[[d.document_id],JSON.stringify([{term:'unknown',aliases:['unknown']}]),v])).rows[0].s;assert.equal(semantic.items.length,1);assert.equal(semantic.items[0].matched_condition_count,0);assert.ok(semantic.items[0].semantic_similarity>0.999);
  await assert.rejects(db.query('select public.idn_search_passages($1,$2,$3)',[[d.document_id],terms,[1]]));
  await saveDoc({...d,text_content:text+' New official version.',content_hash:hash(text+' New official version.'),observed_at:'2026-10-20T00:00:00Z'});
  c=await context(d.document_id);assert.equal(c.passages.length,0);assert.equal(c.relations.length,0);assert.equal(c.stale_evidence_count,4);
  assert.equal((await search()).items.length,0);assert.equal((await business('Kalimantan Timur')).items.length,0);
  await assert.rejects(save({...passage,review_id:'idn-review-'+hash('stale')}));
  for(const role of ['anon','authenticated']){
   await db.exec('reset role;set role '+role);
   for(const sql of ["select public.idn_coverage()","select public.idn_document_context('idn-test-review')","select public.idn_business_search('smelter')","select public.idn_passage_embedding_queue()","select * from policy_idn.review_evidence","select * from policy_idn.passage_embeddings"]){await assert.rejects(db.query(sql));}
  }
  await db.exec('reset role');assert.equal((await db.query('select * from public.bills')).rows[0].id,'us-sentinel');
 }finally{await db.close();}
});
