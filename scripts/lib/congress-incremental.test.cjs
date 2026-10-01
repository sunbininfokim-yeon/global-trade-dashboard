'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../sync-congress.js'),'utf8');
function setup({failStage=false,pages=1,body={bills:[{number:1}],pagination:{next:'next'}}}={}) {
 const events=[];
 const ctx={process:{env:{SYNC_MODE:'incremental'}},Date,JSON,MAX_DISCOVERY_PAGES:pages,DISCOVERY_PAGE_SIZE:250,STATE_RESOURCE:'congress.gov:bills:incremental',
  congressDateTime:v=>new Date(v).toISOString().replace(/\.\d{3}Z$/,'Z'),
  asArray:x=>x||[],unique:x=>x,refFrom:(x,c)=>({...x,congress:c}),
  apiGet:async(p,q)=>{events.push(['api',p,q]);return body;},
  stageCandidates:async x=>{events.push(['queue',x]);if(failStage)throw Error('queue failed');},
  checkpointSyncState:async(r,c)=>events.push(['checkpoint',r,{...c}])};
 vm.createContext(ctx);
 vm.runInContext(source.slice(source.indexOf('function shouldBootstrap('),source.indexOf('function detailLevel(')),ctx);
 return {ctx,events};
}
const cursor={mode:'incremental',window_from:'2026-09-28T00:00:00Z',window_to:'2026-09-30T00:00:00Z',next_congress_index:0,next_offset:250,complete:false};
test('explicit incremental ignores incomplete bootstrap',()=>{const {ctx}=setup();assert.equal(ctx.shouldBootstrap({cursor:{mode:'bootstrap',complete:false}}),false);});
test('resumes Mac cursor and persists queue before advancing fixed window',async()=>{
 const {ctx,events}=setup();const result=await ctx.candidates([119],{cursor},false);
 assert.equal(events[0][2].offset,250);assert.equal(events[0][2].toDateTime,cursor.window_to);
 assert.deepEqual(events.map(e=>e[0]),['api','queue','checkpoint']);
 assert.equal(events[2][1],'congress.gov:bills:incremental');assert.equal(result.cursor.next_offset,251);
 assert.deepEqual(Array.from(result.cursor.congresses),[119]);
});
test('failed durable enqueue leaves cursor untouched for replay',async()=>{const {ctx,events}=setup({failStage:true});await assert.rejects(ctx.candidates([119],{cursor},false),/queue failed/);assert.equal(events.some(e=>e[0]==='checkpoint'),false);});
test('terminal page marks discovery complete',async()=>{const {ctx}=setup({body:{bills:[]}});const r=await ctx.candidates([119],{cursor},false);assert.equal(r.cursor.complete,true);});
test('changed scope cannot reuse unfinished offset',async()=>{const {ctx,events}=setup();await assert.rejects(ctx.candidates([118,119],{cursor},false),/scope differs/);assert.equal(events.length,0);});
test('new window overlaps completed window rather than processing timestamp',async()=>{const {ctx,events}=setup();await ctx.candidates([119],{cursor:{...cursor,complete:true},last_successful_at:'2026-10-01T00:00:00Z'},false);assert.equal(events[0][2].fromDateTime,'2026-09-28T12:00:00Z');assert.equal(events[0][2].offset,0);});
