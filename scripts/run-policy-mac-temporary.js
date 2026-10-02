'use strict';
// Temporary collection operator; never sends email or changes GitHub settings.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawnSync,spawn}=require('node:child_process');
const {remoteState}=require('./lib/policy-remote-guard');
const dir=path.join(os.homedir(),'Documents/policy-downloads/mac-20260930');
const lock=path.join(os.tmpdir(),'chokemonitor-policy-local.lock');
const gh=path.join(os.homedir(),'.local/bin/gh');
const repo='sunbininfokim-yeon/global-trade-dashboard';
let child,halt=false;
function remoteCheck(){try{
 const w=spawnSync(gh,['api',`repos/${repo}/actions/workflows/sync-congress.yml`],{encoding:'utf8',timeout:20000});
 const r=spawnSync(gh,['run','list','--repo',repo,'--workflow','sync-congress.yml','--limit','20','--json','status'],{encoding:'utf8',timeout:20000});
 if(w.status!==0||r.status!==0)return 'unknown';
 return remoteState(JSON.parse(w.stdout),JSON.parse(r.stdout));
}catch{return 'unknown'}}
const state={pid:process.pid,started_at:new Date().toISOString()};
function save(){fs.writeFileSync(path.join(dir,'status.json'),JSON.stringify(state,null,2),{mode:0o600})}
async function main(){
 fs.mkdirSync(dir,{recursive:true,mode:0o700});
 if(fs.existsSync(path.join(dir,'STOP')))throw Error('STOP exists');
 fs.mkdirSync(lock);fs.writeFileSync(path.join(lock,'owner.json'),JSON.stringify(state));
 for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{halt=true;child?.kill('SIGTERM')});
 try {while(!halt&&!fs.existsSync(path.join(dir,'STOP'))){
  const remote=remoteCheck();
  if(remote!=='safe'){
   state.status='paused_remote_guard';state.pause_reason=remote;state.retry_at=new Date(Date.now()+300000).toISOString();save();
   console.log(`Local collection paused: remote=${remote}; retry in 5 minutes.`);
   while(!halt&&!fs.existsSync(path.join(dir,'STOP'))&&Date.now()<Date.parse(state.retry_at))await new Promise(r=>setTimeout(r,1000));
   continue;
  }
  delete state.pause_reason;delete state.retry_at;
  state.cycle_started_at=new Date().toISOString();state.status='running';save();
  let interrupted=false;
  const code=await new Promise((resolve,reject)=>{
   child=spawn(process.execPath,['scripts/sync-congress.js'],{cwd:path.resolve(__dirname,'..'),env:{...process.env,SYNC_MODE:'incremental',CONGRESS_NUMBER:'119',CONGRESS_NUMBERS:'119',MAX_BILLS:'100',MAX_DISCOVERY_PAGES:'4',DETAIL_CONCURRENCY:'2',CONGRESS_REQUEST_INTERVAL_MS:'1200',MAX_EMBEDDINGS:'100',PRUNE_TERMINAL_BILLS:'false',REFRESH_BILL_SEMANTIC_RELATIONS:'false'},stdio:['ignore','pipe','pipe']});
   const output=b=>{let t=b.toString();for(const [k,v]of Object.entries(process.env))if(/KEY|TOKEN|SECRET|PASSWORD/.test(k)&&v)t=t.split(v).join('[redacted]');process.stdout.write(t.replace(/([?&](?:api_key|key)=)[^&\s]+/gi,'$1[redacted]'))};
   child.stdout.on('data',output);child.stderr.on('data',output);
   const guard=setInterval(()=>{
    const remote=remoteCheck();
    if(remote!=='safe'||fs.existsSync(path.join(dir,'STOP'))){interrupted=true;state.pause_reason=remote;child?.kill('SIGTERM')}
   },60000);
   child.once('error',reject);child.once('close',c=>{clearInterval(guard);child=null;resolve(c)});
  });
  if(interrupted&&!halt&&!fs.existsSync(path.join(dir,'STOP')))continue;
  state.exit_code=code;state.completed_at=new Date().toISOString();state.status=code===0?'waiting':'failed';
  state.next_cycle_at=new Date(Date.now()+4*3600000).toISOString();save();
  while(!halt&&!fs.existsSync(path.join(dir,'STOP'))&&Date.now()<Date.parse(state.next_cycle_at))await new Promise(r=>setTimeout(r,1000));
 }}finally{state.status='stopped';save();fs.rmSync(lock,{recursive:true})}
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
