'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../sync-congress.js'),'utf8');
function setup(failOnce=false){
 const events=[];
 const ctx={Date,Number,firstNonEmpty:(...x)=>x.find(v=>v!==undefined&&v!==null&&v!==''),asArray:x=>x||[],
  parseDateOnly:x=>x?.slice(0,10),parseTimestamp:x=>x||null,actionChamber:()=> 'house',stage:()=> 'introduced',withoutKey:x=>x,officialUrl:()=> 'https://www.congress.gov/test',
  latestActionOf:(a,f)=>a.at(-1)||f,actionId:(id,a)=>id+':'+a.text,saveVote:async()=>{},queue:async()=>{},
  supabaseGet:async()=>[{current_status:'Introduced',embedding:[1]}],
  supabaseUpsert:async(t,r)=>events.push({t,r}),
  supabaseInsertIgnore:async(t,r,key)=>{if(failOnce){failOnce=false;throw Error('history failed');}events.push({t,r,key});}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function saveBundle('),source.indexOf('async function saveVote(')),ctx);
 return {ctx,events};
}
const data=()=>({billId:'119-hr-1',ref:{type:'hr',congress:119},detailLevel:'index',row:{current_status:'Introduced',current_stage:'introduced',status_updated_at:'2026-10-01T00:00:00Z',latest_action_date:'2026-10-01',latest_action_text:'Introduced'},summaries:[],subjects:[],committees:[],actions:[],textVersions:[],relatedBills:[],law:{}});
test('index-level monitoring stores latest official action and idempotent history even after bill upsert already succeeded',async()=>{
 const {ctx,events}=setup();await ctx.saveBundle(data());
 assert.ok(events.some(e=>e.t==='bill_actions'));
 const h=events.find(e=>e.t==='bill_status_history');assert.equal(h.r.status,'Introduced');assert.equal(h.key,'bill_id,status,changed_at');
});
test('retry repairs missing history after interrupted write and records same-day changed action text',async()=>{
 const {ctx,events}=setup(true);await assert.rejects(ctx.saveBundle(data()),/history failed/);await ctx.saveBundle(data());
 const next=data();next.row.current_status='Referred to Committee';next.row.latest_action_text=next.row.current_status;await ctx.saveBundle(next);
 const rows=events.filter(e=>e.t==='bill_status_history');assert.equal(rows.length,2);assert.equal(rows[0].r.changed_at,rows[1].r.changed_at);assert.notEqual(rows[0].r.status,rows[1].r.status);
});
