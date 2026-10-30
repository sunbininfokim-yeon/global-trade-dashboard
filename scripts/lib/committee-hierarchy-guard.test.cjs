const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
// Use PGLITE_MODULE to point at the existing local test dependency.
const { PGlite } = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
test('verified hierarchy survives legacy upsert; explicit repair works', async () => {
 const db = new PGlite();
 try {
 await db.exec(`create table committees(committee_id text primary key,committee_type text,parent_committee_id text,raw_source jsonb default '{}');
 insert into committees values('119-senate-ssfr09','subcommittee','119-senate-ssfr00','{"_verified_hierarchy":{"committee_type":"subcommittee","parent_committee_id":"119-senate-ssfr00"}}');`);
 await db.exec(fs.readFileSync(__dirname+'/committee-hierarchy-guard.sql','utf8'));
 await db.exec("update committees set committee_type='standing',parent_committee_id=null,raw_source='{\"activities\":[1]}'");
 const row=(await db.query('select * from committees')).rows[0];
 assert.equal(row.committee_type,'subcommittee');assert.equal(row.parent_committee_id,'119-senate-ssfr00');assert.deepEqual(row.raw_source.activities,[1]);assert.ok(row.raw_source._verified_hierarchy);
 await db.exec("begin;set local app.committee_hierarchy_repair='on';update committees set parent_committee_id='119-senate-other',raw_source='{}';commit;");
 assert.equal((await db.query('select parent_committee_id from committees')).rows[0].parent_committee_id,'119-senate-other');
 await db.exec(fs.readFileSync(__dirname+'/committee-hierarchy-guard.sql','utf8'));
 } finally { await db.close(); }
});
