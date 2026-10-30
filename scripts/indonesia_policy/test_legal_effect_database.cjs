const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{createHash}=require('node:crypto');
const paths=[process.env.IDN_TEST_NODE_MODULES||__dirname],{PGlite}=require(require.resolve('@electric-sql/pglite',{paths}));
const hash=x=>createHash('sha256').update(x).digest('hex');
test('legal effect: time, amendment vs repeal, surviving rights, immutable literal sources and RLS',async()=>{
 const {vector}=await import(pathToFileURL(require.resolve('@electric-sql/pglite-pgvector',{paths})).href),db=new PGlite({extensions:{vector}});
 try{
  await db.exec("create role anon;create role authenticated;create role service_role bypassrls;create schema extensions;create table public.bills(id text);insert into public.bills values('us-sentinel');");
  const dir=path.join(__dirname,'../../supabase/migrations'),files=fs.readdirSync(dir).filter(f=>f.includes('_indonesia_policy_')&&f.endsWith('.sql')).sort();
  for(const f of files)await db.exec(fs.readFileSync(path.join(dir,f),'utf8'));await db.exec(fs.readFileSync(path.join(dir,files.at(-1)),'utf8'));
  const quote='Pasal 2 Peraturan lama dicabut dan dinyatakan tidak berlaku. Pasal 3 Sebagian ketentuan diubah sebagai berikut.',date='Diundangkan di Jakarta pada tanggal 1 Januari 2025',text='PERATURAN PEMERINTAH NOMOR 1 TAHUN 2025 '+quote+' '+date+' Peraturan ini mulai berlaku pada tanggal diundangkan. Sertifikat lama tetap berlaku.';
  const doc=id=>({document_id:id,country_code:'IDN',title:'Official test',title_ko:'테스트',issuer_name:'Ministry',issuer_level:'national',jurisdiction:'Indonesia',document_type:'PP',document_number:id,document_year:2025,topics:['coal'],primary_stage:'coal',scope_note:'Test',source_url:'https://example.go.id/law.pdf',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-19T00:00:00Z',content_hash:hash(text),content_kind:'official_text',text_content:text,text_truncated:false});
  const saveDoc=d=>db.query('select public.idn_store_document($1)',[JSON.stringify(d)]);
  await db.exec('set role service_role');
  for(const id of ['idn-source','idn-base','idn-partial','idn-future','idn-conflict','idn-undated','idn-expired','idn-repealed'])await saveDoc(doc(id));
  await db.query('select public.idn_store_coverage($1)',[JSON.stringify({document_id:'idn-reference',title:'Old law',topics:['coal'],priority:1,reason:'Historical reference without collected body',discovery_url:'https://example.go.id/catalogue'})]);
  const record=(subject,type,extra={})=>{const r={subject_id:subject,source_document_id:'idn-source',source_hash:hash(text),source_url:'https://example.go.id/law.pdf',finding_type:type,article:'Pasal 2',quote,effective_on:'2025-01-01',date_quote:date,date_basis:'promulgation',scope_note_ko:'실제 근거 검토 범위이며 모든 후속 개폐 검토가 아닙니다.',...extra};return {finding_id:'idn-effect-'+hash(JSON.stringify(r)),...r};};
  const store=async r=>(await db.query('select public.idn_store_legal_effect($1) changed',[JSON.stringify(r)])).rows[0].changed;
  const effects=async(ids,asof='2026-10-19')=>(await db.query('select public.idn_legal_effect($1,$2) s',[ids,asof])).rows[0].s.items;
  const amendment=record('idn-base','amendment');assert.equal(await store(amendment),true);assert.equal(await store(amendment),false);
  await assert.rejects(store({...amendment,quote:'This is fabricated literal evidence that does not appear in the source.'}),/immutable/);
  await assert.rejects(store(record('idn-base','amendment',{source_url:'https://other.go.id/law.pdf'})),/literal/);
  await assert.rejects(store(record('idn-base','amendment',{date_quote:null})),/check constraint/);
  await assert.rejects(store(record('idn-base','amendment',{date_quote:'An invented date provenance not in the original text.'})),/literal/);
  await assert.rejects(store(record('idn-missing','full_repeal')),/Unknown/);
  await store(record('idn-partial','partial_repeal'));await store(record('idn-reference','full_repeal'));
  await store(record('idn-reference','transition'));await store(record('idn-repealed','full_repeal'));
  await store(record('idn-repealed','commencement',{source_document_id:'idn-repealed',effective_on:'2024-01-01'}));
  await store(record('idn-expired','expiry'));
  await store(record('idn-future','commencement',{source_document_id:'idn-future',effective_on:'2027-01-01',date_basis:'explicit_date'}));
  await store(record('idn-undated','full_repeal',{effective_on:null,date_quote:null,date_basis:'unverified'}));
  await store(record('idn-conflict','full_repeal'));await store(record('idn-conflict','commencement',{source_document_id:'idn-conflict',effective_on:'2026-01-01'}));
  let result=await effects(['idn-base','idn-partial','idn-reference','idn-source','idn-future','idn-undated','idn-expired','idn-conflict','idn-repealed']);
  const by=id=>result.find(x=>x.document_id===id);
  assert.equal(by('idn-base').status,'amended');assert.equal(by('idn-partial').status,'partially_repealed');
  assert.equal(by('idn-reference').status,'fully_repealed');assert.equal(by('idn-reference').transition_review_required,true);assert.equal(by('idn-reference').document_stored,false);
  assert.equal(by('idn-future').status,'not_yet_effective');assert.equal(by('idn-undated').status,'effective_date_unverified');
  assert.equal(by('idn-expired').status,'expired');assert.equal(by('idn-source').status,'unverified');
  assert.equal(by('idn-conflict').status,'conflicting_evidence');assert.equal(by('idn-repealed').status,'fully_repealed');
  assert.ok(result.every(x=>x.current_validity_confirmed===false));
  assert.equal((await effects(['idn-reference'],'2024-12-31'))[0].status,'unverified');
  assert.equal((await effects(['idn-future'],'2027-01-01'))[0].status,'commenced_review_needed');
  const revised=text+' Source revised.';await saveDoc({...doc('idn-source'),observed_at:'2026-10-20T00:00:00Z',text_content:revised,content_hash:hash(revised)});
  result=await effects(['idn-reference']);assert.equal(result[0].status,'unverified');assert.equal(result[0].stale_evidence_count,2);assert.equal(result[0].findings.length,0);
  await assert.rejects(store(record('idn-base','transition')),/no longer current/);
  await assert.rejects(db.query("select public.idn_legal_effect(array['us-bill'])"),/Invalid/);
  for(const role of ['anon','authenticated']){await db.exec('reset role;set role '+role);for(const sql of ["select * from policy_idn.legal_effect_findings","select public.idn_legal_effect(array['idn-source'])","select public.idn_store_legal_effect('{}')"])await assert.rejects(db.query(sql));}
  await db.exec('reset role');assert.equal((await db.query('select * from public.bills')).rows[0].id,'us-sentinel');
 }finally{await db.close();}
});
