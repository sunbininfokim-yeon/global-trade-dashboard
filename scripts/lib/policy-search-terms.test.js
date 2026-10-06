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
test('energy and other policy aliases are conservative and preserve natural-language queries',()=>{
 const {single}=require('./policy-search-terms');
 for(const [q,a] of [['에너지','energy'],['천연가스','natural gas'],['원유','crude oil'],['원자력','nuclear power'],['구리','copper'],['보건의료','health care']])assert.ok(single(q).aliases.includes(a));
 assert.ok(!single('원유').aliases.includes('oil'));assert.ok(!single('전력').aliases.includes('power'));
 assert.deepEqual(single('천연가스 수출을 제한하는 법').aliases,['천연가스 수출을 제한하는 법']);
 assert.equal(annotate({title:'Vegetable oil and political power'},parse('원유, 전력')).matched_condition_count,0);
});
test('same window, distant mentions and cited context are different evidence strengths',()=>{
 const terms=parse('니켈, 수출통제, 배터리');
 const together=annotate({title:'Policy',evidence_parts:[{field:'body',text:'Export controls for nickel used in batteries.'}]},terms);
 const separate=annotate({title:'Policy',evidence_parts:[{field:'body',text:'Nickel '+'. '.repeat(400)+'export controls '+'. '.repeat(400)+'batteries'}]},terms);
 assert.equal(together.condition_relationship,'shared_passage');assert.equal(separate.condition_relationship,'separate_mentions');
 assert.equal(separate.matched_condition_count,3);
 assert.equal(annotate({evidence_parts:[{field:'cited_document',text:'Export controls for nickel batteries',target_id:'1'}]},terms).condition_relationship,'cited_shared_passage');
 assert.equal(annotate({title:'Nickel batteries',evidence_parts:[{field:'cited_document',text:'export controls',target_id:'1'}]},terms).condition_relationship,'mixed_citation');
});
test('balanced truncation preserves relevant lanes; fusion rewards independent retrieval without losing exact titles',()=>{
 const {balancedLimit,fuse}=require('./policy-search-terms');
 const rows=Array.from({length:30},(_,n)=>({type:'bill',id:String(n)}));rows.push({type:'public_law',id:'law'},{type:'executive_order',id:'eo'},{type:'regulation',id:'reg'});
 assert.equal(new Set(balancedLimit(rows,20).map(i=>i.type)).size,4);assert.equal(balancedLimit(rows,20).length,20);
 const fused=fuse([{type:'bill',id:'exact',relevance_rank:4},{type:'bill',id:'both',relevance_rank:1,similarity_score:0.7},{type:'bill',id:'vector',relevance_rank:0,similarity_score:0.9}]);
 assert.deepEqual(fused.map(i=>i.id),['exact','both','vector']);
});

test('finance and China conditions use grounded English terms across all four source types',()=>{
 const conditions=parse('금융, 중국');
 for(const type of ['bill','public_law','executive_order','regulation']){
  const row=annotate({type,title:'Policy',evidence_parts:[{field:'body',text:"Financial regulation of investment in the People's Republic of China."}]},conditions);
  assert.equal(row.matched_condition_count,2);assert.equal(row.condition_relationship,'shared_passage');
 }
 assert.equal(annotate({title:'Financial policy in the People’s Republic of China'},conditions).matched_condition_count,2);
 assert.equal(parse('중국, 중화인민공화국').length,1);
});
test('popular finance policy concepts support singles and graded multi-condition search',()=>{
 const {single}=require('./policy-search-terms');
 assert.ok(single('금융').aliases.includes('financial'));assert.ok(single('스테이블코인').aliases.includes('stablecoins'));
 const rows=rank([{id:'both',title:'Banking regulation of Chinese commercial banks'},
  {id:'one',title:'Banking regulation in Canada'},
  {id:'none',title:'River banks and IndoChina tourism'}],parse('중국, 은행'),20);
 assert.deepEqual(rows.map(r=>[r.id,r.matched_condition_count]),[['both',2],['one',1]]);
 assert.equal(annotate({title:'Anti-money-laundering requirements for payment stablecoins'},parse('자금세탁방지, 스테이블코인')).matched_condition_count,2);
});
test('China, Taiwan and Hong Kong remain distinct and finance acronyms do not invent matches',()=>{
 const {single}=require('./policy-search-terms');
 assert.ok(!single('중국').aliases.includes('taiwan'));assert.ok(!single('중국').aliases.includes('hong kong'));
 assert.equal(annotate({title:'Commercial banking in Taiwan and Hong Kong'},parse('금융, 중국')).condition_matches[1].matched,false);
 assert.equal(annotate({title:'Social security, river banks, acute leukemia AML and PRC'},parse('증권, 은행, 자금세탁방지, 중국')).matched_condition_count,0);
});
