'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const data=JSON.parse(fs.readFileSync(path.join(root,'New for anti/public/data/trade_policy/country_announcements_v1.json')));
const source=fs.readFileSync(path.join(root,'New for anti/export-controls.js'),'utf8');
function harness(input=data){
 const window={};
 const code=source.replace('    window.ExportControls = {',`announcements = input;
 window.testNotices={ui,pageNotices,pagedNoticesHtml,announcementEligible,announcementsHtml,announcementHtml,onPanelClick};
 window.ExportControls = {`);
 class Element {constructor(attrs){this.attrs=attrs;} closest(sel){return sel.startsWith('[')&&Object.hasOwn(this.attrs,sel.slice(1,-1))?this:null;} getAttribute(a){return this.attrs[a]??null;} matches(){return false;}}
 vm.runInNewContext(code,{window,input,console,URL,Element,CSS:{escape:s=>s}});
 return {...window.testNotices,Element};
}
test('curated coverage has 16 US official announcements and two verified cabinet statements',()=>{
 const h=harness(); const rows=data.countries.KOR;
 assert.equal(rows.length,18);assert.equal(rows.filter(r=>r.issuer==='USA').length,16);
 assert.equal(new Set(rows.map(r=>r.id)).size,rows.length);
 assert.ok(rows.every(r=>h.announcementEligible(r,'KOR')));
 for(let i=1;i<rows.length;i++)assert.ok(rows[i-1].published_at>=rows[i].published_at);
 assert.ok(rows.some(r=>r.kind==='cooperation'));assert.ok(rows.some(r=>r.kind==='joint_statement'));
});
test('Korean lower officials, generic ministry announcements and misleading Minister for Trade are excluded',()=>{
 const h=harness();const r=data.countries.KOR.find(r=>r.issuer==='KOR');
 for(const rank of ['vice_minister','director','minister_for_trade',null]) assert.equal(h.announcementEligible({...r,speaker:{name:'Minister for Trade',rank,statement_verified:true}},'KOR'),false);
 assert.equal(h.announcementEligible({...r,speaker:{rank:'cabinet_minister',statement_verified:false}},'KOR'),false);
 assert.equal(h.announcementEligible({...r,speaker:null},'KOR'),false);
});
test('unknown, out-of-window, nonofficial and third-country items do not enter Korean reviewed list',()=>{
 const h=harness();const r=data.countries.KOR[0];
 for(const published_at of [null,'','2026-07-09','2026-10-11'])assert.equal(h.announcementEligible({...r,published_at},'KOR'),false);
 assert.equal(h.announcementEligible({...r,url:'https://news.example.com/a'},'KOR'),false);
 assert.equal(h.announcementEligible({...r,issuer:'CHN'},'KOR'),false);
});
test('five per page, stable newest-first, deduplication, unknown last, boundary clamp and independent lists',()=>{
 const h=harness();const rows=Array.from({length:12},(_,i)=>({id:String(i),published_at:`2026-09-${String(i+1).padStart(2,'0')}`}));
 rows.push(rows[0]); rows.reverse();
 const first=h.pageNotices(rows,'KOR:announcements');assert.equal(first.rows.length,5);assert.equal(first.rows[0].id,'11');assert.equal(first.total,12);
 h.ui.noticePages['KOR:announcements']=2;
 const second=h.pageNotices(rows,'KOR:announcements');assert.ok(second.rows.every(r=>!first.rows.find(x=>x.id===r.id)));
 assert.equal(h.pageNotices(rows,'KOR:issued').page,1);
 h.ui.noticePages['KOR:announcements']=999;assert.equal(h.pageNotices(rows,'KOR:announcements').page,3);
 assert.equal(h.pageNotices([],'KOR:announcements').page,1);
 assert.equal(h.pageNotices([{id:'unknown'},{id:'dated',published_at:'2026-09-01'}],'x').rows[1].id,'unknown');
});
test('numeric navigation has current-page accessibility and uses the actual click handler',()=>{
 const h=harness();h.ui.iso='KOR';h.ui.panel={innerHTML:'',scrollTop:123,querySelector:()=>null};
 const html=h.announcementsHtml('KOR');assert.match(html,/aria-current="page"/);assert.equal((html.match(/class="ec-notice"/g)||[]).length,5);
 h.onPanelClick({target:new h.Element({'data-ec-notice-page':'2','data-ec-notice-key':'KOR:announcements'})});
 assert.equal(h.ui.noticePages['KOR:announcements'],2);assert.equal(h.ui.panel.scrollTop,123);
 assert.match(h.ui.panel.innerHTML,/6–10 \/ 18건/);
});
test('rendering escapes public text and discloses partial evidence; unavailable data is not zero coverage',()=>{
 const h=harness(); const html=h.announcementHtml({...data.countries.KOR[0],title:{ko:'<script>bad</script>'},url:'javascript:alert(1)',summary_ko:'<img src=x>'});
 assert.doesNotMatch(html,/<script>|<img|javascript:/);assert.match(html,/&lt;script&gt;/);
 assert.match(h.announcementsHtml('KOR'),/본문 상세 미검증/);
 assert.match(harness({error:true}).announcementsHtml('KOR'),/불러오지 못/);
});
