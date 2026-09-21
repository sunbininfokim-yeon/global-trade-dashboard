'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {PGlite}=require(process.env.PGLITE_MODULE||'@electric-sql/pglite');
test('JEC identity preserves sources, unions future links, rejects cycles, seeds CRS idempotently',async()=>{
 const db=new PGlite();try{
 await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create table committees(committee_id text primary key,congress_number int,chamber text,name text,parent_committee_id text);
 create table bill_committees(bill_id text,committee_id text references committees,primary key(bill_id,committee_id));
 create table policy_areas(policy_area_id text primary key,name text unique,source text,source_url text,active boolean);
 insert into committees values('119-joint-jjec00',119,'joint','Joint Economic Committee',null),('119-joint-jhje00',119,'joint','Joint Economic Committee',null),('119-joint-jsec00',119,'joint','Joint Economic Committee',null);
 insert into bill_committees values('a','119-joint-jjec00'),('a','119-joint-jsec00'),('b','119-joint-jhje00');
 insert into policy_areas values('existing-energy-id','Energy','congress.gov','original',true);`);
 const sql=fs.readFileSync(path.join(__dirname,'../../supabase/migrations/20260921110000_jec_identity_crs_dictionary.sql'),'utf8');
 await db.exec(sql);await db.exec(sql);
 const directory=(await db.query('select * from committee_directory')).rows;
 assert.equal(directory.length,1);assert.equal(Number(directory[0].canonical_bill_count),2);assert.equal(directory[0].source_committee_ids.length,3);
 assert.equal((await db.query('select * from committees')).rows.length,3);
 assert.equal((await db.query('select * from bill_committees')).rows.length,3);
 assert.equal((await db.query('select * from committee_canonical_bill_links')).rows.length,2);
 assert.equal((await db.query('select * from policy_areas')).rows.length,32);
 assert.equal((await db.query("select policy_area_id from policy_areas where name='Energy'")).rows[0].policy_area_id,'existing-energy-id');
 await assert.rejects(db.exec("insert into committee_identity_aliases(alias_committee_id,canonical_committee_id,source_url) values('119-joint-jjec00','119-joint-jsec00','test')"),/chains and cycles/);
 await db.exec("insert into bill_committees values('c','119-joint-jsec00')");
 assert.equal(Number((await db.query('select canonical_bill_count from committee_directory')).rows[0].canonical_bill_count),3);
 await db.exec('set role anon');await assert.rejects(db.query('select * from committee_identity_aliases'),/permission denied/);
 }finally{await db.close();}
});
