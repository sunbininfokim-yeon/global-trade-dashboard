'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../sync-congress.js'),'utf8'),utils=fs.readFileSync(require.resolve('./sync-utils.js'),'utf8');
test('favorites are checked independently of the discovery cursor and scoped to selected Congress',async()=>{
 const calls=[],ctx={PolicyEvidence:require('../../New for anti/policy-evidence.js'),supabaseGet:async()=>[{item_id:'119-hr-3'},{item_id:'119-hr-3'},{item_id:'118-s-2'}],
 apiGet:async(path)=>{calls.push(path);return {bill:{number:3,type:'hr'}};},refFrom:x=>x,stageCandidates:async(refs,priority)=>calls.push(priority)};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function discoverFavorites('),source.indexOf('async function memberName(')),ctx);
 assert.equal(await ctx.discoverFavorites([119]),1);assert.deepEqual(calls,['/bill/119/hr/3',100]);
});
test('unchanged pending favorite is promoted without requeueing completed or claimed records',async()=>{
 for(const status of ['pending','processing','succeeded']){
  const patches=[],ctx={Date,Number,queueKeyFilter:x=>'eq.'+x,supabaseGet:async()=>[{queue_id:'q',status,priority:0,source_updated_at:'2026-10-01'}],supabasePatch:async(t,q,x)=>patches.push(x)};
  vm.createContext(ctx);vm.runInContext(utils.slice(utils.indexOf('async function enqueuePolicyItem('),utils.indexOf('async function takePolicyQueue(')),ctx);
  const result=await ctx.enqueuePolicyItem('congress.gov:bills','119-hr-3',{}, {sourceUpdatedAt:'2026-10-01',priority:100});
  assert.equal(result,status==='pending'?'reprioritized':'unchanged');assert.equal(patches.length,status==='pending'?1:0);
  if(patches.length){assert.equal(patches[0].priority,100);assert.equal(patches[0].status,undefined);}
 }
});
