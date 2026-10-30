const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{createHash}=require('node:crypto');
const paths=[process.env.IDN_TEST_NODE_MODULES||__dirname],{PGlite}=require(require.resolve('@electric-sql/pglite',{paths}));
test('catalogue inventory: atomic replay, scoped completeness, candidate matching, disappearance and denied public access',async()=>{
 const {vector}=await import(pathToFileURL(require.resolve('@electric-sql/pglite-pgvector',{paths})).href),db=new PGlite({extensions:{vector}});
 try{
  await db.exec("create role anon;create role authenticated;create role service_role bypassrls;create schema extensions;create table public.bills(id text);insert into public.bills values('us-sentinel');");
  const dir=path.join(__dirname,'../../supabase/migrations'),files=fs.readdirSync(dir).filter(f=>f.includes('_indonesia_policy_')&&f.endsWith('.sql')).sort();
  for(const f of files)await db.exec(fs.readFileSync(path.join(dir,f),'utf8'));await db.exec(fs.readFileSync(path.join(dir,files.at(-1)),'utf8'));
  await db.exec('set role service_role');
  const text='PERATURAN PEMERINTAH NOMOR 19 TAHUN 2025 '+ 'Official legal text. '.repeat(20);
  const doc={document_id:'idn-test-pp',country_code:'IDN',title:'PP19',title_ko:'Royalty',issuer_name:'Pemerintah Pusat',issuer_level:'national',jurisdiction:'Indonesia',document_type:'PP',document_number:'19',document_year:2025,topics:['coal'],primary_stage:'coal',scope_note:'Test',source_url:'https://example.go.id/law.pdf',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-18T00:00:00Z',content_hash:createHash('sha256').update(text).digest('hex'),content_kind:'official_text',text_content:text,text_truncated:false};
  await db.query('select public.idn_store_document($1)',[JSON.stringify(doc)]);
  const record={source_record_id:'1',title:'PP19',page_url:'https://example.go.id/list',download_url:doc.source_url,document_type:'PP',document_number:'19',document_year:2025,issuer_key:'national'};
  const snapshot={run_id:'00000000-0000-0000-0000-000000000001',source_id:'test',source_config:{source_id:'test',url:'https://example.go.id/list',scope:'All rows of a bounded government catalogue'},finished_at:'2026-10-19T00:00:00Z',status:'enumerated_scope',stop_reason:'listing_exhausted',records:[record,{...record,source_record_id:'2',download_url:'https://other.go.id/law.pdf'},{...record,source_record_id:'3',document_type:'Pergub',download_url:null,issuer_key:null}],pending_urls:[],pages:[{url:'https://example.go.id/list',raw_sha256:'a'.repeat(64)}],failures:[]};
  const store=async s=>(await db.query('select public.idn_store_catalogue($1) s',[JSON.stringify(s)])).rows[0].s;
  const gaps=async()=>(await db.query('select public.idn_catalogue_gaps() s')).rows[0].s;
  assert.equal((await store(snapshot)).new_versions,3);assert.equal((await store(snapshot)).changed,false);
  let g=await gaps();assert.deepEqual(g.counts,{url_match:1,identity_candidate:1,unmatched:1});assert.equal(g.items[0].matches[0].content_kind,'official_text');
  await assert.rejects(store({...snapshot,status:'enumerated_scope',pending_urls:['https://example.go.id/next']}),/Incomplete/);
  await assert.rejects(store({...snapshot,records:[]}),/Incomplete/);
  await assert.rejects(store({...snapshot,records:[record,record]}),/duplicate/);
  const invalid={...record,source_record_id:'bad',download_url:'https://evil.example/doc.pdf'};
  await assert.rejects(store({...snapshot,records:[{...record,source_record_id:'new'},invalid]}),/Invalid catalogue/);
  assert.equal((await gaps()).total,3);assert.equal((await db.query('select count(*) n from policy_idn.catalogue_runs')).rows[0].n,1);
  const partial={...snapshot,finished_at:'2026-10-20T00:00:00Z',status:'failed',records:[record],pending_urls:['https://example.go.id/next'],failures:[{error:'403'}]};await store(partial);
  assert.equal((await gaps()).items.find(x=>x.source_record_id==='2').not_seen_in_latest_enumeration,false);
  await store({...snapshot,finished_at:'2026-10-21T00:00:00Z',records:[{...record,title:'Updated title'},snapshot.records[2]]});
  g=await gaps();assert.equal(g.total,3);assert.equal(g.items.find(x=>x.source_record_id==='2').not_seen_in_latest_enumeration,true);
  assert.equal((await db.query('select count(*) n from policy_idn.catalogue_versions')).rows[0].n,4);
  await store({...snapshot,finished_at:'2026-10-17T00:00:00Z',records:[{...record,title:'Older title'}]});
  assert.equal((await gaps()).items[0].metadata.title,'Updated title');
  assert.equal((await db.query('select public.idn_status() s')).rows[0].s.documents,1);
  for(const role of ['anon','authenticated']){await db.exec('reset role;set role '+role);for(const sql of ["select * from policy_idn.catalogue_entries","select * from policy_idn.catalogue_runs","select * from policy_idn.catalogue_versions","select public.idn_catalogue_status()","select public.idn_catalogue_gaps()","select public.idn_store_catalogue('{}')"]){await assert.rejects(db.query(sql));}}
  await db.exec('reset role');assert.equal((await db.query('select * from public.bills')).rows[0].id,'us-sentinel');
 }finally{await db.close();}
});
