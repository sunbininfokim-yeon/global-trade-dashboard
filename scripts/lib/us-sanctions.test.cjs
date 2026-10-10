'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const root=path.resolve(__dirname,'../..');const data=JSON.parse(fs.readFileSync(path.join(root,'New for anti/public/data/trade_policy/us_sanctions_v1.json')));
const source=fs.readFileSync(path.join(root,'New for anti/export-controls.js'),'utf8');
function render(input=data){const window={};class Element{constructor(attrs){this.attrs=attrs;}closest(s){return Object.hasOwn(this.attrs,s.slice(1,-1))?this:null;}getAttribute(n){return this.attrs[n];}matches(){return false;}}
vm.runInNewContext(source.replace('    window.ExportControls = {',`sanctions=input; window.testSanctions={ui,sanctionsTiming,sanctionsSectionHtml,sanctionsCompanyHtml,sanctionsMeasureHtml,onPanelClick}; window.ExportControls = {`),{window,input,console,Element});return {...window.testSanctions,Element};}
test('four country sections keep country sanctions and conditional foreign bank exposure separate',()=>{
const r=render();for(const iso of ['RUS','CHN','KOR','JPN'])assert.match(r.sanctionsSectionHtml(iso),/미국 제재·거래 제한/);
assert.match(r.sanctionsSectionHtml('KOR'),/개별 은행 지정 여부를 판정하지 않습니다/);assert.equal(r.sanctionsSectionHtml('CAN'),'');
});
test('diesel license expires at exact offset, without lifting the underlying measure',()=>{
const r=render();const m=data.measures.find(m=>m.id==='ru-diesel-gl135');
assert.match(r.sanctionsTiming(m,Date.parse(m.expires_at)-1),/한시 허용/);assert.match(r.sanctionsTiming(m,Date.parse(m.expires_at)),/기한 경과/);assert.deepEqual(m.related_measure_ids,['ru-petroleum']);
});
test('bank, goods and companies clicks change the actual panel, five per page and state is country specific',()=>{
const r=render();r.ui.iso='RUS';r.ui.panel={innerHTML:'',scrollTop:42};
r.onPanelClick({target:new r.Element({'data-ec-sanctions-view':'companies'})});assert.match(r.ui.panel.innerHTML,/1–5 \/ 10/);
const before=r.ui.panel.innerHTML;r.onPanelClick({target:new r.Element({'data-ec-sanctions-page':'2'})});assert.match(r.ui.panel.innerHTML,/6–10 \/ 10/);assert.notEqual(before,r.ui.panel.innerHTML);assert.equal(r.ui.panel.scrollTop,42);
r.ui.iso='CHN';assert.match(r.sanctionsSectionHtml('CHN'),/쿤룬은행/);assert.equal(r.ui.sanctionsViews.CHN,undefined);
r.onPanelClick({target:new r.Element({'data-ec-sanctions-view':'goods'})});assert.match(r.ui.panel.innerHTML,/첨단 컴퓨팅/);
});
test('no exact match is not no sanctions; CMIC and EL are distinct; content is escaped',()=>{
const r=render();assert.match(r.sanctionsCompanyHtml(data.companies.find(c=>c.id==='kor-samsung')),/제재 면제·거래 허용 판정이 아닙니다/);
const h=r.sanctionsCompanyHtml(data.companies.find(c=>c.id==='chn-huawei'));assert.match(h,/증권투자 제한/);assert.match(h,/수출허가 요건/);
const x=r.sanctionsMeasureHtml({title_ko:'<img>',summary_ko:'<script>x</script>',source_url:'javascript:x'});assert.doesNotMatch(x,/<img>|<script>|javascript:/);
});
test('failed or malformed snapshot warns and never renders a zero-sanctions conclusion',()=>{
assert.match(render({error:true}).sanctionsSectionHtml('KOR'),/불러오지 못/);assert.match(render({countries:{KOR:{}}}).sanctionsSectionHtml('KOR'),/불러오지 못/);
});
