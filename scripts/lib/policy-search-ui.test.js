'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../../New for anti/policy.js'),'utf8').replace('  window.USPolicy = {','  window.searchResultsMarkup = searchResultsMarkup;\n  window.USPolicy = {');
function render(body,compact=false){const window={};vm.runInNewContext(source,{window,console,URLSearchParams,setTimeout,clearTimeout});return window.searchResultsMarkup(body,{compact});}
const row=(id,count,type='bill')=>({id,type,title:`Result ${id}`,total_condition_count:3,matched_condition_count:count,match_level:count===3?'all':'partial',condition_matches:[{term:'니켈',matched:true,field:'title',snippet:'nickel battery'},{term:'수출통제',matched:count===3,field:'summary',snippet:'export controls'},{term:'배터리',matched:true,field:'title',snippet:'nickel battery'}]});
test('four document lanes remain separate while each lane sorts matches',()=>{
 for(const compact of [true,false]) {
  const html=render({search_mode:'conditions',items:[row('partial',2),row('all',3),row('law',1,'public_law'),row('eo',1,'executive_order'),row('reg',1,'regulation')]},compact);
  assert.ok(html.indexOf('Result all')<html.indexOf('Result partial'));
  assert.match(html,/3개 중 2개 일치/);
  assert.ok(!html.includes('<details'));
  assert.ok(!html.includes('근거 ('));
  assert.equal(html.includes('data-search-order="latest"'),!compact);
  assert.equal((html.match(/<section class="policy-search-group"/g)||[]).length,4);
  assert.ok(html.indexOf('Result partial')<html.indexOf('Result law'));
  assert.ok(html.indexOf('Result law')<html.indexOf('Result eo'));
  assert.ok(html.indexOf('Result eo')<html.indexOf('Result reg'));
 }
});
test('card titles and terms are escaped and external links reject unsafe schemes',()=>{
 const r=row('p',2,'public_law');r.source_url='javascript:alert(1)';r.title='<img src=x onerror=alert(1)>';
 const html=render({search_mode:'conditions',items:[r]});
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/&lt;img/);
});
test('relevance uses match count then semantic score; dates reorder within lanes',()=>{
 const window={};vm.runInNewContext(source.replace('  window.searchResultsMarkup =','  window.searchOrderCompare = searchOrderCompare;\n  window.searchResultsMarkup ='),{window,console,URLSearchParams,setTimeout,clearTimeout});
 const a={...row('a',3),latest_action_date:'2025-01-01'},b={...row('b',2,'regulation'),publication_date:'2026-10-01'};
 assert.ok(window.searchOrderCompare(a,b,'matches')<0);
 assert.ok(window.searchOrderCompare(a,b,'latest')>0);
 assert.ok(window.searchOrderCompare(b,row('unknown',3),'latest')<0);
 assert.match(render({search_mode:'conditions',items:[b]}),/data-search-date="2026-10-01"/);
 assert.ok(window.searchOrderCompare({...a,similarity_score:0.9},{...a,similarity_score:0.5,latest_action_date:'2026-10-01'},'matches')<0);
});

test('full page keeps empty lanes visible and semantic search uses the same four-lane contract',()=>{
 const html=render({items:[{id:'x',type:'bill',title:'Semantic',similarity_score:0.8}]});
 assert.equal((html.match(/<section class="policy-search-group"/g)||[]).length,4);
 assert.equal((html.match(/검색 결과 없음/g)||[]).length,3);
 assert.match(html,/연관도 높은 순/);
 assert.match(html,/data-similarity="0.8"/);
 const compact=render({items:[]},true);assert.ok(!compact.includes('<section'));
});
