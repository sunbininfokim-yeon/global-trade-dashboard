const { test } = require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const os=require('node:os');const path=require('node:path');const {acquireLock}=require('./policy-mac-lock');
for(const [label,owner,alive,ok] of [['dead owner',{pid:123},false,true],['live owner',{pid:123},true,false],['invalid owner',{pid:0},false,false]])test(label+' cannot create overlapping collection',()=>{
 const base=fs.mkdtempSync(path.join(os.tmpdir(),'policy-lock-test-'));const lock=path.join(base,'lock');fs.mkdirSync(lock);fs.writeFileSync(path.join(lock,'owner.json'),JSON.stringify(owner));
 try{if(ok){acquireLock(lock,{pid:456},()=>alive);assert.equal(JSON.parse(fs.readFileSync(path.join(lock,'owner.json'))).pid,456)}else{assert.throws(()=>acquireLock(lock,{pid:456},()=>alive));assert.deepEqual(JSON.parse(fs.readFileSync(path.join(lock,'owner.json'))),owner)}}finally{fs.rmSync(base,{recursive:true})}
});
test('two real processes racing to recover one stale lock cannot both win', async () => {
 const {spawn}=require('node:child_process');
 const base=fs.mkdtempSync(path.join(os.tmpdir(),'policy-lock-race-')),lock=path.join(base,'lock');
 fs.mkdirSync(lock);fs.writeFileSync(path.join(lock,'owner.json'),JSON.stringify({pid:2147483647}));
 const script=`try{require(${JSON.stringify(require.resolve('./policy-mac-lock'))}).acquireLock(process.argv[1],{pid:process.pid});setTimeout(()=>{},800)}catch{process.exit(1)}`;
 try{
  const run=()=>new Promise(resolve=>{const child=spawn(process.execPath,['-e',script,lock],{stdio:'ignore'});child.on('close',resolve)});
  const results=await Promise.all([run(),run()]);assert.deepEqual(results.sort(),[0,1]);
 }finally{fs.rmSync(base,{recursive:true,force:true})}
});
test('cleanup cannot delete a replacement process lock',()=>{
 const {releaseLock}=require('./policy-mac-lock');const base=fs.mkdtempSync(path.join(os.tmpdir(),'policy-lock-owner-')),lock=path.join(base,'lock');
 try{acquireLock(lock,{pid:123});assert.equal(releaseLock(lock,456),false);assert.equal(fs.existsSync(lock),true);assert.equal(releaseLock(lock,123),true)}finally{fs.rmSync(base,{recursive:true,force:true})}
});
test('actual task process keeps its lock without a supervisor and a dead task may be recovered',async()=>{
 const {spawn}=require('node:child_process');const base=fs.mkdtempSync(path.join(os.tmpdir(),'policy-task-preload-'));
 const lock=path.join(base,'chokemonitor-policy-task.lock');const preload=require.resolve('./policy-task-lock');
 const env={...process.env,TMPDIR:base,TMP:base,TEMP:base};
 const first=spawn(process.execPath,['-r',preload,'-e','setTimeout(()=>{},10000)'],{env,stdio:'ignore'});
 const firstDone=new Promise(resolve=>first.on('close',resolve));
 try{
  for(let i=0;i<100&&!fs.existsSync(path.join(lock,'owner.json'));i++)await new Promise(r=>setTimeout(r,10));
  assert.equal(JSON.parse(fs.readFileSync(path.join(lock,'owner.json'))).pid,first.pid);
  const run=()=>new Promise(resolve=>spawn(process.execPath,['-r',preload,'-e','process.exit(0)'],{env,stdio:'ignore'}).on('close',resolve));
  assert.equal(await run(),1);first.kill('SIGTERM');await firstDone;assert.equal(await run(),0);
 }finally{first.kill('SIGTERM');await firstDone;fs.rmSync(base,{recursive:true,force:true})}
});
