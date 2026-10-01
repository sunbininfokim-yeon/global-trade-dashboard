'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../../New for anti/policy.js'),'utf8').replace('  window.USPolicy = {','  window.searchResultsMarkup = searchResultsMarkup;\n  window.USPolicy = {');
function render(body,compact=false){const window={};vm.runInNewContext(source,{window,console,URLSearchParams,setTimeout,clearTimeout});return window.searchResultsMarkup(body,{compact});}
const row=(id,count,type='bill')=>({id,type,title:`Result ${id}`,total_condition_count:3,matched_condition_count:count,match_level:count===3?'all':'partial',condition_matches:[{term:'니켈',matched:true,field:'title',snippet:'nickel battery'},{term:'수출통제',matched:count===3,field:'summary',snippet:'export controls'},{term:'배터리',matched:true,field:'title',snippet:'nickel battery'}]});
test('cards mix types in match order without left notes or disclosure groups',()=>{
 for(const compact of [true,false]) {
  const html=render({search_mode:'conditions',items:[row('partial',2),row('all',3,'executive_order')]},compact);
  assert.ok(html.indexOf('Result all')<html.indexOf('Result partial'));
  assert.match(html,/3개 중 2개 일치/);
  assert.ok(!html.includes('<details'));
  assert.ok(!html.includes('근거 ('));
  assert.equal(html.includes('data-search-order="latest"'),!compact);
 }
});
test('card titles and terms are escaped and external links reject unsafe schemes',()=>{
 const r=row('p',2,'public_law');r.source_url='javascript:alert(1)';r.title='<img src=x onerror=alert(1)>';
 const html=render({search_mode:'conditions',items:[r]});
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/&lt;img/);
});
test('newest ordering crosses document types and keeps match counts',()=>{
 const window={};vm.runInNewContext(source.replace('  window.searchResultsMarkup =','  window.searchOrderCompare = searchOrderCompare;\n  window.searchResultsMarkup ='),{window,console,URLSearchParams,setTimeout,clearTimeout});
 const a={...row('a',3),latest_action_date:'2025-01-01'},b={...row('b',2,'regulation'),publication_date:'2026-10-01'};
 assert.ok(window.searchOrderCompare(a,b,'matches')<0);
 assert.ok(window.searchOrderCompare(a,b,'latest')>0);
 assert.ok(window.searchOrderCompare(b,row('unknown',3),'latest')<0);
 assert.match(render({search_mode:'conditions',items:[b]}),/data-search-date="2026-10-01"/);
});
