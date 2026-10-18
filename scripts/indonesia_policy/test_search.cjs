const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {PGlite}=require(require.resolve('@electric-sql/pglite',{paths:[process.env.IDN_TEST_NODE_MODULES||__dirname]}));
const migrations=['20261017080335_indonesia_policy_corpus.sql','20261017080543_indonesia_policy_source_checks.sql','20261018112152_indonesia_policy_isolation.sql','20261018112503_indonesia_policy_biofuel.sql','20261018113918_indonesia_policy_search.sql'];
const text='PERATURAN MENTERI tentang perdagangan NIKEL dan EKSPOR. '.repeat(6);
const d={document_id:'idn-test-search',country_code:'IDN',title:'Ekspor Nikel',title_ko:'니켈 수출',issuer_name:'Ministry',issuer_level:'national',jurisdiction:'Indonesia',document_type:'Permen',document_number:'32/MK/BC',document_year:2026,topics:['nickel_mining'],primary_stage:'nickel_mining',scope_note:'Test only, unverified',source_url:'https://example.go.id/doc',legal_status:'unverified',status_note:'Unverified',observed_at:'2026-10-18T00:00:00Z',content_hash:createHash('sha256').update(text).digest('hex'),content_kind:'official_text',text_content:text,text_truncated:false};
test('IDN search: multilingual terms, evidence, partial/all, filters, details and denied public access',async()=>{
 const db=new PGlite();
 try{
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create table public.bills(id text);insert into public.bills values(\'us-nickel\');');
  for(const file of migrations)await db.exec(fs.readFileSync(path.join(__dirname,'../../supabase/migrations',file),'utf8'));
  await db.exec(fs.readFileSync(path.join(__dirname,'../../supabase/migrations',migrations.at(-1)),'utf8'));
  await db.query('select public.idn_store_document($1)',[JSON.stringify(d)]);
  const {parseTerms}=await import('./search-api.mjs');
  const search=async(q,all=false,topic=null)=> (await db.query('select public.idn_search_documents($1,$2,null,null,\'relevance\',$3) s',[JSON.stringify(parseTerms(q)),topic,all])).rows[0].s;
  await db.exec('set role service_role');
  let r=await search('니켈, 수출, 바이오연료');assert.equal(r.total,1);assert.equal(r.items[0].matched_condition_count,2);assert.equal(r.items[0].total_condition_count,3);
  assert.equal(r.items[0].legal_status,'unverified');assert.equal(r.country,'IDN');assert.equal(r.semantic_available,false);
  assert.equal((await search('니켈, 수출, 바이오연료',true)).total,0);
  assert.equal((await search('니켈',false,'coal')).total,0);
  assert.equal((await search('32/MK/BC')).total,1);
  assert.equal((await search('')).total,1);
  assert.equal((await search('존재하지않는검색어')).total,0);
  const detail=(await db.query('select public.idn_get_document($1) d',[d.document_id])).rows[0].d;
  assert.equal(detail.version.text_content,text);assert.equal(detail.country,'IDN');
  assert.equal((await db.query("select public.idn_get_document('us-nickel') d")).rows[0].d,null);
  await assert.rejects(db.query("select public.idn_search_documents('[{\"term\":\"x\",\"aliases\":[\"\"]}]')"));
  for(const role of ['anon','authenticated']){
   await db.exec('reset role;set role '+role);await assert.rejects(search('니켈'));
   await assert.rejects(db.query('select * from policy_idn.documents'));
  }
 }finally{await db.close();}
});
