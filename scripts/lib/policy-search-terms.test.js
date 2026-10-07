'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {parse,annotate,rank,clause}=require('./policy-search-terms');
test('comma terms normalize aliases, empty parts, duplicates and full-width commas',()=>{
 assert.equal(parse('배터리용 니켈의 수출통제'),null);
 const terms=parse(' 니켈， nickel, 수출통제, 배터리,,');
 assert.equal(terms.length,3);assert.equal(terms[1].aliases.includes('export licensing'),true);
 assert.throws(()=>parse('a,b,c,d,e,f'),/5개/);assert.throws(()=>parse('nickel,foo).or(*)'),/문자/);
});
test('all/partial evidence is grounded in title and summary, not high similarity',()=>{
 const terms=parse('니켈, 수출통제, 배터리');
 const rows=rank([
 {id:'partial',title:'Nickel batteries',summary:'Domestic production support',similarity_score:0.99},
 {id:'none',title:'Semiconductor trade',similarity_score:1},
 {id:'all',title:'Nickel supply',summary:'Export controls for rechargeable batteries',similarity_score:0.2},
 ],terms,20);
 assert.deepEqual(rows.map(x=>x.id),['all','partial']);
 assert.equal(rows[1].matched_condition_count,2);assert.equal(rows[1].condition_matches[1].matched,false);
 assert.equal(rows[0].condition_matches[1].field,'summary');assert.match(rows[0].condition_matches[1].snippet,/export controls/);
});
test('word boundaries prevent nickelodeon and batteryless false matches; HTML tags do not count',()=>{
 const x=annotate({title:'Nickelodeon batteryless device',summary:'<nickel>note</nickel>'},parse('nickel,battery'));
 assert.equal(x.matched_condition_count,0);
 assert.equal(annotate({title:'Nickel battery export-control rules'},parse('니켈, 수출통제, 배터리')).matched_condition_count,3);
});
test('unknown terms remain literal and filters quote literal validated text',()=>{
 const t=parse('unknown concept, 배터리');assert.deepEqual(t[0].aliases,['unknown concept']);
 assert.match(clause(['title','summary'],t[0]),/title\.ilike\."\*unknown\*concept\*"/);
});
