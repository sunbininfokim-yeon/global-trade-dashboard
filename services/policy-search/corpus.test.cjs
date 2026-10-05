const { test } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs');
const { PGlite } = require('@electric-sql/pglite');
const { vector } = require('@electric-sql/pglite-pgvector');
const { buildDocument, citations, chunks, officialUrl, hash } = require('../../scripts/lib/policy-search-document');
const { parse, annotate, rank } = require('../../scripts/lib/policy-search-terms');
const sql = fs.readFileSync(require.resolve('../../supabase/migrations/20261005010000_policy_search_documents.sql'), 'utf8');
const url = 'https://www.congress.gov/bill/119th-congress/house-joint-resolution/72/text';
const eoUrl = 'https://www.govinfo.gov/content/pkg/DCPD-202500209/html/DCPD-202500209.htm';
const document = () => buildDocument({ type: 'bill', id: '119-hjres-72', title: 'Relating to a national emergency', sourceUrl: url,
  body: 'The national emergency declared in Executive Order 14193 is hereby terminated.', bodyUrl: url,
  contexts: [{ target_type: 'executive_order', target_id: '14193', text: 'Tariffs on products of Canada. Additional 25 percent ad valorem duty.', source_url: eoUrl, citation_url: url }] });
async function fixture(fn) {
  const db = new PGlite({ extensions: { vector } });
  try {
    await db.exec(`create schema extensions; create extension vector with schema extensions;
      create role anon; create role authenticated; create role service_role;
      create table bills(bill_id text primary key,title text,summary text,source_updated_at timestamptz,congress_number int,latest_action_date date);
      create table executive_orders(eo_number int primary key,title text,summary text,source_updated_at timestamptz,signed_date date,publication_date date);
      create table public_laws(public_law_id text primary key,law_title text,official_text_url text,source_updated_at timestamptz,bill_id text,congress_number int,enacted_date date);
      create table regulations(regulation_id text primary key,title text,abstract text,source_updated_at timestamptz,publication_date date);`);
    await db.exec('create table bill_text_versions(bill_id text,html_url text);create table bill_subjects(bill_id text,subject_id text);');
    await db.exec(sql); await db.exec(sql);
    const enqueue = async (id='119-hjres-72') => db.query('select enqueue_policy_search_document($1,$2)', ['bill',id]);
    const claim = async () => (await db.query('select * from claim_policy_search_job()')).rows[0];
    const save = async (doc, job, passages=doc.passages) => (await db.query('select save_policy_search_document($1,$2,$3) saved', [JSON.stringify(doc),JSON.stringify(passages),job.claim_token])).rows[0].saved;
    const finish = async job => db.query('select finish_policy_search_job($1,$2)', [job.document_id, job.claim_token]);
    await fn({ db, enqueue, claim, save, finish });
  } finally { await db.close(); }
}
test('generic bill title retrieves Canada tariffs through an explicit EO citation; original summary stays empty',()=>{
  const doc=document(); const result=annotate({ title:doc.title,evidence_parts:doc.evidence_parts },parse('캐나다, 관세'));
  assert.equal(result.matched_condition_count,2); assert.equal(result.condition_matches[0].field,'cited_document');
  assert.equal(result.condition_matches[0].target_id,'14193'); assert.equal(result.condition_matches[0].citation_url,url);
  assert.ok(!doc.evidence_parts.some(p=>p.field==='summary'));
});
test('uncited context cannot manufacture matches, agency duties are not tariffs, semantic-only is not N/N proof',()=>{
  const doc=buildDocument({type:'public_law',id:'118-public-1',title:'Agency responsibilities',sourceUrl:url,body:'The agency performs additional duties in Canada.',contexts:[{target_type:'executive_order',target_id:'14193',text:'Canada tariffs',source_url:eoUrl,citation_url:url}]});
  assert.equal(annotate({title:doc.title,evidence_parts:doc.evidence_parts},parse('캐나다, 관세')).matched_condition_count,1);
  const results=rank([{id:'x',title:'Other',semantic_candidate:true,similarity_score:0.8}],parse('캐나다, 관세'),10);
  assert.equal(results[0].match_level,'semantic_only');assert.equal(results[0].matched_condition_count,0);
});
test('citation variants, chunk tail, bounded inputs, changed-source hash and transparent coverage',()=>{
  assert.equal(citations('Pub. L. No. 119–45; P.L. 118-1; Executive Order No. 14193').length,3);
  assert.equal(citations('Public Law 119-45')[0].target_id,'119-public-45');
  const text='first '.repeat(500)+'last clause'; assert.ok(chunks(text).at(-1).endsWith('last clause'));
  const long=buildDocument({type:'bill',id:'x',title:'Long',sourceUrl:url,body:'word '.repeat(250000)});
  assert.equal(long.passages.length,24);assert.equal(long.embedding_coverage,'partial');assert.equal(long.text_status,'partial_body');
  assert.ok(long.passages.every(p=>p.input_text.length<6000));assert.notEqual(document().input_hash,hash('other'));
  assert.equal(officialUrl('https://congress.gov.evil.com/x'),null);assert.equal(officialUrl('https://api.govinfo.gov/x?api_key=private'),'https://api.govinfo.gov/x');
  const base={type:'bill',id:'x',title:'Title',body:'Text',bodyUrl:url};
  assert.equal(buildDocument({...base,subjects:['Trade','Canada','Trade']}).input_hash,buildDocument({...base,subjects:['Canada','Trade']}).input_hash);
  assert.equal(buildDocument(base).source_url,url);
});
test('fresh install and rerun; lexical proof and vector dedup across document types',()=>fixture(async({db,enqueue,claim,save,finish})=>{
  await enqueue();const job=await claim();const doc=document();
  const embedding=[1,...Array(1535).fill(0)];
  await save(doc,job,doc.passages.map(p=>({...p,embedding,embedding_model:'gemini-embedding-001'})));await finish(job);
  const hits=(await db.query('select * from search_policy_document_terms($1)',[JSON.stringify(parse('캐나다, 관세'))])).rows;
  assert.equal(hits.length,1);assert.equal(annotate(hits[0],parse('캐나다, 관세')).matched_condition_count,2);
  const vectors=(await db.query('select * from search_policy_document_vectors($1,$2)',[JSON.stringify(embedding),'gemini-embedding-001'])).rows;
  assert.equal(vectors.length,1);assert.equal(vectors[0].similarity_score,1);
  assert.equal((await db.query('select * from search_policy_document_vectors($1,$2)',[JSON.stringify(embedding),'other-model'])).rows.length,0);
}));
test('source changes during processing reject old snapshot; old token cannot finish a new lease',()=>fixture(async({db,enqueue,claim,save,finish})=>{
  await enqueue();const job=await claim();await enqueue();assert.equal(await save(document(),job),false);await finish(job);
  assert.equal((await db.query('select status from policy_search_jobs')).rows[0].status,'queued');
  const next=await claim();await assert.rejects(()=>save(document(),job),/lease/);assert.ok(await save(document(),next));
  await db.exec("update policy_search_jobs set lease_until=now()-interval '1 second'");const recovered=await claim();
  assert.notEqual(recovered.claim_token,next.claim_token);
  assert.equal((await db.query('select finish_policy_search_job($1,$2) done',[next.document_id,next.claim_token])).rows[0].done,false);
}));
test('citation dependency refresh and source deletion preserve other sources; changed chunk clears old vector',()=>fixture(async({db,enqueue,claim,save,finish})=>{
  await db.exec("insert into bills(bill_id,title) values('119-hjres-72','Bill');insert into executive_orders(eo_number,title) values(14193,'EO')");
  // Choose the bill job explicitly in a fixture, without changing production ordering.
  await db.exec("delete from policy_search_jobs where source_type='executive_order'");
  const job=await claim(),doc=document(),embedding=[1,...Array(1535).fill(0)];
  await save(doc,job,doc.passages.map(p=>({...p,embedding,embedding_model:'gemini-embedding-001'})));await finish(job);
  await db.exec("update executive_orders set title='Changed' where eo_number=14193");
  assert.equal((await db.query("select status from policy_search_jobs where source_type='bill'")).rows[0].status,'queued');
  const next=await claim();const changed={...doc,passages:doc.passages.map(p=>({...p,input_hash:hash(p.text+'changed')}))};
  await save(changed,next);assert.equal((await db.query('select count(*) n from policy_search_passages where embedding is not null')).rows[0].n,0);
  await db.exec("delete from bills where bill_id='119-hjres-72'");
  assert.equal((await db.query('select count(*) n from policy_search_documents')).rows[0].n,0);
  assert.equal((await db.query('select count(*) n from executive_orders')).rows[0].n,1);
}));
test('bootstrap is idempotent and live changes outrank historical jobs; unchanged writes preserve done state',()=>fixture(async({db,claim,save,finish})=>{
  await db.exec("insert into bills(bill_id,title,congress_number,latest_action_date) values('118-hr-1','Old',118,'2024-01-01'),('119-hjres-72','Bill',119,'2026-02-11');delete from policy_search_jobs");
  assert.equal((await db.query('select seed_policy_search_jobs() n')).rows[0].n,2);
  assert.equal((await db.query('select seed_policy_search_jobs() n')).rows[0].n,0);
  const job=await claim();assert.equal(job.source_id,'119-hjres-72');await save(document(),job);await finish(job);
  await db.exec("update bills set title=title where bill_id='119-hjres-72'");
  assert.equal((await db.query("select status from policy_search_jobs where source_id='119-hjres-72'")).rows[0].status,'done');
  await db.exec("update bills set latest_action_date='2026-02-12' where bill_id='119-hjres-72'");
  assert.equal((await claim()).source_id,'119-hjres-72');
  assert.equal((await db.query('select seed_policy_search_jobs() n')).rows[0].n,0);
}));
test('child deletion refreshes bill without deleting snapshot; linked-law summary and exhausted retry reset',()=>fixture(async({db,claim,save,finish})=>{
  await db.exec("insert into bills(bill_id,title,congress_number) values('119-hjres-72','Bill',119)");
  const job=await claim();await save(document(),job);await finish(job);
  await db.exec("insert into bill_text_versions values('119-hjres-72','https://www.govinfo.gov/example');delete from bill_text_versions");
  assert.equal((await db.query('select count(*) n from policy_search_documents')).rows[0].n,1);
  await db.exec("insert into public_laws(public_law_id,law_title,bill_id,congress_number) values('119-public-1','Law','119-hjres-72',119);update policy_search_jobs set status='failed',attempts=8;update bills set summary='Official new summary' where bill_id='119-hjres-72'");
  const jobs=(await db.query('select * from policy_search_jobs')).rows;
  assert.ok(jobs.every(j=>j.status==='queued'&&j.attempts===0&&j.priority===20));
}));
test('search lock refuses live owners and only recovers a verified dead owner',()=>{
  const os=require('node:os'),path=require('node:path');const {acquireLock,releaseLock}=require('../../scripts/lib/policy-search-lock');
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'policy-search-lock-')),lock=path.join(root,'RUNNING');
  try {
    acquireLock(lock,{pid:101},()=>true);assert.throws(()=>acquireLock(lock,{pid:202},()=>true),/already_running/);
    acquireLock(lock,{pid:202},()=>false);assert.equal(releaseLock(lock,101),false);assert.equal(releaseLock(lock,202),true);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('Mac cycle is bounded, reads existing Gemini key, respects explicit disable and collector STOP',()=>{
  const {searchCycle}=require('../../scripts/lib/policy-search-cycle');
  assert.equal(searchCycle({POLICY_SEARCH_ENABLED:'false'},'/tmp/user'),null);
  const cycle=searchCycle({AI_STUDIO_API_KEY:'fixture'},'/tmp/user');
  assert.deepEqual(cycle.args,['--limit','1000','--max-minutes','60']);assert.equal(cycle.env.GEMINI_API_KEY,'fixture');
  assert.ok(cycle.env.POLICY_COLLECTOR_STOP_FILE.endsWith('/mac-20260930/STOP'));
});
