import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {readIsraelFixture} from './fixtures/israel-snapshot.mjs';
import {validateCooperation,cooperationPartners} from '../data/israel-cooperation.js';
import {israelCooperationHtml} from '../country-explorer/special/israel-analysis.cooperation.js';
const board=JSON.parse(readIsraelFixture('israel_election_analysis_v1.json'));
board.cooperation_review=JSON.parse(readFileSync(new URL('../../../scripts/election_watch/tests/fixtures/israel/2026-10-31/cooperation_review.json',import.meta.url),'utf8'));
test('Raam and Joint List are different actors and component seats remain null',()=>{
 validateCooperation(board.cooperation_review,board,'2026-10-31');
 const p=board.cooperation_review.profiles;
 assert.notEqual(p.find(p=>p.list_id==='k26:עם').spectrum,p.find(p=>p.list_id==='k26:ודם').spectrum);
 assert.deepEqual(p.find(p=>p.list_id==='k26:ודם').components.map(c=>c.seats),[null,null,null]);
});
test('post-election talks lead and Joint List refusal never spreads to Raam',()=>{
 const partners=cooperationPartners(board,'k26:עם');
 assert.equal(partners[0].list_id,'k26:אמת');
 assert.equal(partners.find(p=>p.list_id==='k26:ל').records.length,0);
 const joint=cooperationPartners(board,'k26:ודם');
 assert.equal(joint[0].records[0].kind,'refusal');
 assert.equal(joint[0].list_id,'k26:ל');
});
test('every other party stays visible, unreviewed pairs are unknown, ideology never adds a relation',()=>{
 const p=cooperationPartners(board,'k26:מחל');assert.equal(p.length,10);
 assert.equal(p.find(p=>p.list_id==='k26:ב').records.length,0);
 const html=israelCooperationHtml(board,'k26:מחל');
 assert.match(html,/과거 검토 기록/);assert.match(html,/미확인/);assert.match(html,/입장 미확인|성사 가능성 순위/);
 assert.match(html,/통합토라유다/);assert.match(html,/세속/);assert.match(html,/초정통/);
});
test('labels escape markup and unsupported event promotion, source failure and score fail closed',()=>{
 const b=structuredClone(board);b.cooperation_review.profiles[0].religion_ko='<img src=x>';
 assert.match(israelCooperationHtml(b),/&lt;img/);
 for(const change of [d=>d.relations[0].kind='formed',d=>d.relations[0].source_ids=['ap-held'],d=>d.profiles[0].spectrum=5,d=>d.profiles.at(-1).components[0].seats=4]){
  const d=structuredClone(board.cooperation_review);change(d);assert.throws(()=>validateCooperation(d,board,'2026-10-31'));
 }
});
