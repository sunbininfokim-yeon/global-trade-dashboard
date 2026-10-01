'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../../New for anti/policy.js'),'utf8').replace('  window.USPolicy = {','  window.searchResultsMarkup = searchResultsMarkup;\n  window.USPolicy = {');
function render(body,compact=false){const window={};vm.runInNewContext(source,{window,console,URLSearchParams,setTimeout,clearTimeout});return window.searchResultsMarkup(body,{compact});}
const row=(id,count,type='bill')=>({id,type,title:`Result ${id}`,total_condition_count:3,matched_condition_count:count,match_level:count===3?'all':'partial',condition_matches:[{term:'니켈',matched:true,field:'title',snippet:'nickel battery'},{term:'수출통제',matched:count===3,field:'summary',snippet:'export controls'},{term:'배터리',matched:true,field:'title',snippet:'nickel battery'}]});
test('dropdown and full page place all-condition section before partial section with missing terms visible',()=>{
 for(const compact of [true,false]){
 const html=render({search_mode:'conditions',items:[row('p',2),row('a',3,'executive_order')]},compact);
 assert.ok(html.indexOf('전체 조건 일치')<html.indexOf('일부 조건 일치'));
 assert.match(html,/3개 중 2개 일치/);assert.match(html,/수출통제: 미확인/);
 if(!compact)assert.match(html,/수출통제 근거 \(요약\)/);
 }
});
test('evidence and terms are escaped and unsafe external source URLs are not links',()=>{
 const r=row('p',2,'public_law');r.source_url='javascript:alert(1)';r.condition_matches[0].snippet='<img src=x onerror=alert(1)>';
 const html=render({search_mode:'conditions',items:[r]});
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/&lt;img/);
});
test('empty and truncated candidate sets disclose scope without claiming no relevant law exists',()=>{
 const html=render({search_mode:'conditions',items:[],candidate_limited:true,semantic_available:false});
 assert.match(html,/후보·표시 수 제한/);assert.match(html,/단어·유사 표현 검색 결과만/);assert.match(html,/검색된 후보의 제목·요약/);
});
