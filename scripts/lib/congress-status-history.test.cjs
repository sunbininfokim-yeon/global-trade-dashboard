'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {prepareEmbedding,loadBillActions}=require('../sync-congress.js');
const source=fs.readFileSync(require.resolve('../sync-congress.js'),'utf8');
function setup(failOnce=false){
 const events=[];
 const ctx={Date,Number,prepareEmbedding,firstNonEmpty:(...x)=>x.find(v=>v!==undefined&&v!==null&&v!==''),asArray:x=>x||[],
  parseDateOnly:x=>x?.slice(0,10),parseTimestamp:x=>x||null,actionChamber:()=> 'house',stage:()=> 'introduced',withoutKey:x=>x,officialUrl:()=> 'https://www.congress.gov/test',
  latestActionOf:(a,f)=>a.at(-1)||f,actionId:(id,a)=>id+':'+a.text,saveVote:async()=>{},queue:async()=>{},
  supabaseGet:async()=>[{current_status:'Introduced',embedding:[1]}],
  supabaseUpsert:async(t,r)=>events.push({t,r}),
  supabaseInsertIgnore:async(t,r,key)=>{if(failOnce){failOnce=false;throw Error('history failed');}events.push({t,r,key});}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function saveBundle('),source.indexOf('async function saveVote(')),ctx);
 return {ctx,events};
}
const data=()=>({billId:'119-hr-1',ref:{type:'hr',congress:119},detailLevel:'index',row:{title:'Status history fixture',summary:'',raw_source:{},current_status:'Introduced',current_stage:'introduced',status_updated_at:'2026-10-01T00:00:00Z',latest_action_date:'2026-10-01',latest_action_text:'Introduced'},summaries:[],subjects:[],committees:[],actions:[],textVersions:[],relatedBills:[],law:{}});
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
test('Congress actions follow every official offset through the final page', async () => {
 const path='/bill/119/hr/1';
 const pages=[
  {actions:[{text:'Signed by President'},{text:'Presented to President'}],pagination:{count:3,next:'https://api.congress.gov/v3/bill/119/hr/1/actions?offset=2'}},
  {actions:[{text:'Passed Senate'}],pagination:{count:3}},
 ];
 const calls=[];
 const actions=await loadBillActions(path,async (...args)=>{calls.push(args);return pages.shift();});
 assert.deepEqual(actions.map(action=>action.text),['Signed by President','Presented to President','Passed Senate']);
 assert.deepEqual(calls,[
  [path+'/actions',{limit:250,offset:0},true],
  [path+'/actions',{limit:250,offset:2},false],
 ]);
});
test('incomplete or non-advancing Congress action pages fail for retry', async () => {
 const path='/bill/119/hr/1';
 await assert.rejects(loadBillActions(path,async ()=>({actions:[{text:'Introduced'}],pagination:{count:2}})),/incomplete action history/);
 await assert.rejects(loadBillActions(path,async ()=>({actions:[{text:'Introduced'}],pagination:{next:'?offset=0'}})),/invalid action pagination/);
 assert.deepEqual(await loadBillActions(path,async ()=>null),[]);
});
test('vetoed bill saves full official history while a routine index bill saves only the latest action',async()=>{
 const {ctx,events}=setup();
 const bill=data();
 bill.actions=[{actionDate:'2026-10-01',text:'Passed House'},{actionDate:'2026-10-02',text:'Presented to President'},{actionDate:'2026-10-03',text:'Vetoed by President'}];
 bill.row.current_stage='vetoed';
 bill.row.current_status=bill.actions.at(-1).text;
 await ctx.saveBundle(bill);
 assert.deepEqual(events.filter(e=>e.t==='bill_actions').map(e=>e.r[0].action_text),bill.actions.map(a=>a.text));
 const history=events.find(e=>e.t==='bill_status_history');
 assert.equal(history.r.source_action_id,'119-hr-1:Vetoed by President');
 events.length=0;
 bill.row.current_stage='referred';
 bill.actions=bill.actions.slice(0,1).concat({actionDate:'2026-10-02',text:'Referred to Committee'});
 bill.row.current_status=bill.actions.at(-1).text;
 await ctx.saveBundle(bill);
 assert.deepEqual(events.filter(e=>e.t==='bill_actions').map(e=>e.r[0].action_text),['Referred to Committee']);
});
