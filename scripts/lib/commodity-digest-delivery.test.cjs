const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const {digestIdempotencyKey}=require('../notify-commodity-digest');
test('provider retries share a stable per-user report-set key, regardless of report or commodity order',()=>{
 const groups=[{items:[{id:'b'},{id:'a'}]},{items:[{id:'a'}]}];
 assert.equal(digestIdempotencyKey('one',groups),digestIdempotencyKey('one',[{items:[{id:'a'},{id:'b'}]}]));
 assert.notEqual(digestIdempotencyKey('two',groups),digestIdempotencyKey('one',groups));
 assert.notEqual(digestIdempotencyKey('one',[{items:[{id:'new'}]}]),digestIdempotencyKey('one',groups));
 assert.ok(!digestIdempotencyKey('one',groups).includes('one'));
});
test('legacy sender requires provider acceptance and includes the stable idempotency key',async()=>{
 let body={id:'accepted'},headers;
 const module={exports:{}};
 const nativeRequire=require('node:module').createRequire(require.resolve('../notify-commodity-digest'));
 vm.runInNewContext(fs.readFileSync(require.resolve('../notify-commodity-digest'),'utf8'),{module,require:name=>name==='./lib/sync-utils'?{fetchJson:async(_url,options)=>{headers=options.headers;return body}}:nativeRequire(name),__dirname:require('node:path').dirname(require.resolve('../notify-commodity-digest')),process:{env:{}},console});
 const groups=[{label:'Oil',items:[{id:'a',url:'https://eia.gov',title:{original:'Oil report'}}]}];
 assert.equal(await module.exports.sendDigestEmail('example@example.com',groups,'one'),'accepted');
 assert.equal(headers['Idempotency-Key'],digestIdempotencyKey('one',groups));
 body={};await assert.rejects(module.exports.sendDigestEmail('example@example.com',groups,'one'),/resend_acceptance_unconfirmed/);
});
test('a later recipient failure cannot discard the first accepted recipient receipt',async()=>{
 let sent=0;const receipts=[];const module={exports:{}};
 const nativeRequire=require('node:module').createRequire(require.resolve('../notify-commodity-digest'));
 const utils={requireEnv:()=> 'test',supabaseGet:async table=>({user_favorites:[{user_id:'one',item_id:'oil'},{user_id:'two',item_id:'oil'}],commodity_report_notifications:[],commodity_digest_source_prefs:[],profiles:[{id:'one',email:'one@example.com'},{id:'two',email:'two@example.com'}]})[table],supabaseUpsert:async(_table,rows)=>receipts.push(...rows),fetchJson:async()=>{if(++sent===2)throw Error('provider unavailable');return {id:'first'}}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../notify-commodity-digest'),'utf8'),{module,require:name=>name==='./lib/sync-utils'?utils:name==='node:fs'?{readFileSync:()=>JSON.stringify({items:[{id:'report',source_id:'eia',commodities:['oil'],published_at:new Date().toISOString(),url:'https://eia.gov',title:{original:'Oil'}}]})}:nativeRequire(name),__dirname:require('node:path').dirname(require.resolve('../notify-commodity-digest')),process:{env:{}},console:{log(){}}});
 await assert.rejects(module.exports.run(),/provider unavailable/);
 assert.equal(receipts.length,1);assert.equal(receipts[0].user_id,'one');assert.equal(receipts[0].report_id,'report');
});
