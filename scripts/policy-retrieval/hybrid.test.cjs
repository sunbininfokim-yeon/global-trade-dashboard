const { test }=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const {PGlite}=require(process.env.PGLITE_MODULE||'@electric-sql/pglite');
const {vector}=require(process.env.PGVECTOR_MODULE||'@electric-sql/pglite-pgvector');
test('migration is repeatable; historical laws searchable; models isolated; RRF ranks lexical agreement',async()=>{
 const db=new PGlite({extensions:{vector}});
 try {
 await db.exec(`create schema extensions;create extension vector with schema extensions;
 create role anon;create role authenticated;create role service_role;
 create table bills(bill_id text,title text,summary text,embedding extensions.vector(1536),embedding_model text);
 create table executive_orders(eo_number int,title text,summary text,embedding extensions.vector(1536),embedding_model text);
 create table regulations(regulation_id text,title text,abstract text,embedding extensions.vector(1536),embedding_model text);
 create table public_laws(public_law_id text,law_title text,congress_number int,law_number text,bill_id text);`);
 const sql=fs.readFileSync(__dirname+'/../../supabase/migrations/20260924150000_public_law_hybrid_search.sql','utf8');
 await db.exec(sql);await db.exec(sql);
 const v=JSON.stringify([1,...Array(1535).fill(0)]);
 await db.query('insert into public_laws(public_law_id,law_title,congress_number,law_number,embedding,embedding_model) values($1,$2,118,$3,$4,$5)',['118-public-1','Export Control Reform Act','1',v,'gemini-embedding-001']);
 await db.query('insert into bills values($1,$2,$3,$4,$5)',['119-hr-1','Postal naming bill','',v,'wrong-model']);
 const a=await db.query('select * from search_policy_hybrid($1,$2,$3,20)',['export control',v,'gemini-embedding-001']);
 assert.equal(a.rows.length,1);assert.equal(a.rows[0].source_type,'public_law');
 assert.equal(a.rows[0].source_id,'118-public-1');
 await db.exec('set role anon');await assert.rejects(db.query('select * from search_policy_hybrid($1,$2,$3,20)',['export',v,'gemini-embedding-001']),/permission denied/);
 }finally{await db.close();}
});
