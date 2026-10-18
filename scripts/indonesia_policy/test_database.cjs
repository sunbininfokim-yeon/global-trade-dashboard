const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
// Use an installed PGlite or an operator-selected dependency directory.
const {PGlite}=require(require.resolve('@electric-sql/pglite',{paths:[process.env.IDN_TEST_NODE_MODULES||__dirname]}));
const sql=fs.readFileSync(path.join(__dirname,'../../supabase/migrations/20261017080335_indonesia_policy_corpus.sql'),'utf8');
const auditSql=fs.readFileSync(path.join(__dirname,'../../supabase/migrations/20261017080543_indonesia_policy_source_checks.sql'),'utf8');
const isolateSql=fs.readFileSync(path.join(__dirname,'../../supabase/migrations/20261018112152_indonesia_policy_isolation.sql'),'utf8');
const biofuelSql=fs.readFileSync(path.join(__dirname,'../../supabase/migrations/20261018112503_indonesia_policy_biofuel.sql'),'utf8');
const body='Official coal mining source '.repeat(10);
const d={document_id:'idn-test-coal',country_code:'IDN',title:'Coal',title_ko:'석탄',issuer_name:'Test ministry',issuer_level:'national',jurisdiction:'Indonesia',document_type:'Permen',document_number:'1',document_year:2026,topics:['coal'],primary_stage:'coal',scope_note:'Test',source_url:'https://example.go.id/doc',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-17T00:00:00Z',content_hash:createHash('sha256').update(body).digest('hex'),content_kind:'official_text',text_content:body,text_truncated:false};
test('fresh install, replay, immutable dedup, atomic rollback and client isolation',async()=>{
 const db=new PGlite();
 try{
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
  await db.exec(sql);await db.exec(auditSql);await db.exec(sql);await db.exec(auditSql);
  const save=x=>db.query('select public.store_idn_policy_document($1::jsonb) changed',[JSON.stringify(x)]);
  assert.equal((await save(d)).rows[0].changed,true);
  assert.equal((await save(d)).rows[0].changed,false);
  assert.equal((await db.query('select count(*)::int n from idn_policy_versions')).rows[0].n,1);
  await assert.rejects(save({...d,document_id:'idn-invalid',document_number:'2',text_content:'too short'}));
  assert.equal((await db.query('select count(*)::int n from idn_policy_documents')).rows[0].n,1);
  await assert.rejects(save({...d,country_code:'USA'}));
  await assert.rejects(save({...d,legal_status:'in_force'}));
  await db.exec('set role anon');
  await assert.rejects(db.query('select * from idn_policy_documents'));
  await assert.rejects(db.query('select * from idn_policy_source_checks'));
  await assert.rejects(save(d));
  await db.exec('reset role;set role service_role');
  assert.equal((await save(d)).rows[0].changed,false);
 }finally{await db.close();}
});
test('schema move preserves existing versions and excludes the US corpus and public clients',async()=>{
 const db=new PGlite();
 try{
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create table public.bills(id text);insert into public.bills values (\'us-sentinel\');');
  await db.exec(sql);await db.exec(auditSql);
  await db.query('select public.store_idn_policy_document($1)',[JSON.stringify(d)]);
  await db.exec(isolateSql);await db.exec(isolateSql);
  await db.exec(biofuelSql);await db.exec(biofuelSql);
  assert.equal((await db.query('select count(*)::int n from policy_idn.versions')).rows[0].n,1);
  assert.equal((await db.query("select to_regclass('public.idn_policy_documents') old_table")).rows[0].old_table,null);
  assert.equal((await db.query("select to_regprocedure('public.store_idn_policy_document(jsonb)') old_rpc")).rows[0].old_rpc,null);
  assert.equal((await db.query('select id from public.bills')).rows[0].id,'us-sentinel');
  const save=x=>db.query('select public.idn_store_document($1) changed',[JSON.stringify(x)]);
  await db.exec('set role service_role');
  assert.equal((await save(d)).rows[0].changed,false);
  assert.equal((await save({...d,document_id:'idn-test-biofuel',document_number:'2',primary_stage:'biofuel',topics:['biofuel','biodiesel']})).rows[0].changed,true);
  await assert.rejects(save({...d,document_id:'idn-test-us',document_number:'3',primary_stage:'us_bills'}));
  assert.equal((await db.query('select public.idn_status() s')).rows[0].s.schema,'policy_idn');
  await assert.rejects(save({...d,country_code:'USA'}));
  await db.exec('reset role;set role anon');
  await assert.rejects(save(d));
  await assert.rejects(db.query('select * from policy_idn.documents'));
 }finally{await db.close();}
});
