import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {PGlite} from '@electric-sql/pglite';
import {renderDelivery,runMailing} from '../core.mjs';
const U='00000000-0000-0000-0000-000000000001',V='00000000-0000-0000-0000-000000000002';
const migrations=['20260911010000_mailing_outbox.sql','20260919_bill_notification_pause.sql','20260919_favorite_notify_enabled.sql','20261002020000_mailing_subscription_preferences.sql',
 '20261017080335_indonesia_policy_corpus.sql','20261017080543_indonesia_policy_source_checks.sql','20261018112152_indonesia_policy_isolation.sql','20261018112503_indonesia_policy_biofuel.sql'];
const migration='20261020174850_indonesia_policy_mailing.sql';
const gateway='20261020213953_indonesia_mail_auth_gateways.sql';
const release='20261020214317_indonesia_mail_review_enqueue.sql';
const preserve='20261020215056_indonesia_preserve_source_text.sql';
const serialize='20261020230106_indonesia_ingest_serialization.sql';
const lease='20261020231311_indonesia_sync_lease.sql';
const completeSource='20261020231617_indonesia_mail_complete_source_gate.sql';
const multiScope='20261021040724_indonesia_multi_scope_subscriptions.sql';
const sql=name=>readFileSync(new URL('../../../supabase/migrations/'+name,import.meta.url),'utf8');
const hash=s=>createHash('sha256').update(s).digest('hex');
const body='Ketentuan batubara dan perlindungan lingkungan untuk usaha pertambangan. '.repeat(8);
const document=(id,level='national',region='Indonesia')=>({document_id:id,country_code:'IDN',title:id,title_ko:'환경·석탄 시험 문서',issuer_name:'Test',issuer_level:level,jurisdiction:region,document_type:'Permen',document_number:id,document_year:2026,topics:['coal','biofuel'],primary_stage:'coal',scope_note:'Reviewed test scope',source_url:'https://test.go.id/'+id,legal_status:'unverified',status_note:'Test',observed_at:'2026-10-01T00:00:00Z',content_hash:hash(body),content_kind:'official_text',text_content:body,text_truncated:false});
async function fixture(fn){
 const db=new PGlite();
 try{
  await db.exec(`create role anon;create role authenticated;create role service_role bypassrls; create schema auth;
   create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
   create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
   create table public.profiles(id uuid primary key,email text);
   create table user_favorites(user_id uuid,item_kind text,item_id text,title text,created_at timestamptz default now(),primary key(user_id,item_kind,item_id));
   create table bills(bill_id text primary key,title text,current_stage text,latest_action_text text,status_updated_at timestamptz);
   create table executive_orders(eo_number int primary key,title text,summary text,updated_at timestamptz);
   create table commodity_report_notifications(user_id uuid,report_id text,sent_at timestamptz default now(),primary key(user_id,report_id));
   create table commodity_digest_source_prefs(user_id uuid,source_id text,primary key(user_id,source_id));
   insert into auth.users values('${U}','verified@example.test',now()),('${V}','second@example.test',now());
   insert into profiles values('${U}','profile@example.test'),('${V}','profile2@example.test');`);
  for(const name of migrations)await db.exec(sql(name));
  const rpc=async(name,args=[])=> (await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) result`,args)).rows[0].result;
  const save=async d=>rpc('idn_store_document',[JSON.stringify(d)]);
  await save(document('idn-national'));
  await save(document('idn-east','provincial','Kalimantan Timur'));
  await save(document('idn-west','provincial','Kalimantan Barat'));
  await db.exec(sql(migration));
  await db.exec(sql(gateway));
  await db.exec(sql(release));
  await db.exec(sql(preserve));
  await db.exec(sql(serialize));
  await db.exec(sql(lease));
  await db.exec(sql(completeSource));
  await db.exec(sql(multiScope));
  const acting=async(id,fn)=>{
   await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id]);await db.exec('set role authenticated');
   try{return await fn();}finally{await db.exec('reset role');}
  };
  const sub=(user=U,topic='coal',region='Kalimantan Timur',enabled=true)=>acting(user,()=>rpc('idn_set_my_mail_subscription',[topic,region,enabled]));
  const change=async(id='idn-national',extra='New official requirement.')=>{
   const d=document(id,id==='idn-east'?'provincial':'national',id==='idn-east'?'Kalimantan Timur':'Indonesia');
   d.text_content=body+extra;d.content_hash=hash(d.text_content);d.observed_at=new Date().toISOString();
   await save(d);return (await db.query('select * from policy_idn.mail_changes where document_id=$1 and content_hash=$2',[id,d.content_hash])).rows[0];
  };
  const review=(c,patch={})=>rpc('idn_review_mail_change',[c.change_id,JSON.stringify({event_type:'official_content_changed',summary:'Official source content changed; legal effect requires separate review.',reviewer:'fixture-review',quote:body.slice(0,60),source_url:'https://test.go.id/'+c.document_id,topics:['coal'],scope:'national',regions:[],...patch})]);
  await fn({db,rpc,save,acting,sub,change,review});
 }finally{await db.close();}
}
test('multi-scope subscriptions expose nationwide plus 38 BPS provinces, preserve coverage gaps, and save combinations atomically',()=>fixture(async({db,rpc,acting})=>{
 const list=()=>acting(U,()=>rpc('idn_my_mail_subscriptions'));
 const options=(await list()).region_options;assert.equal(options.length,39);
 assert.equal(options[0].value,'__all__');assert.equal(options.find(r=>r.value==='Aceh').has_local_documents,false);
 assert.equal(options.find(r=>r.value==='Kalimantan Timur').has_local_documents,true);
 const batch=(topics,regions,enabled=true)=>acting(U,()=>rpc('idn_set_my_mail_subscriptions',[topics,regions,enabled]));
 assert.equal((await batch(['coal','nickel_mining'],['Kalimantan Timur','Sulawesi Tengah'])).affected,4);
 assert.equal((await list()).subscriptions.length,4);
 await assert.rejects(batch(['coal','us_bills'],['Aceh']));await assert.rejects(batch(['coal'],['not-a-region']));
 await assert.rejects(batch(['coal'],['__all__','Aceh']));await assert.rejects(batch([],['__all__']));
 assert.equal((await list()).subscriptions.length,4);
 assert.equal((await acting(V,()=>rpc('idn_my_mail_subscriptions'))).subscriptions.length,0);
 await db.exec(sql(multiScope));assert.equal((await list()).region_options.length,39);
 const source=JSON.parse(readFileSync(new URL('../../../scripts/indonesia_policy/mail-regions.json',import.meta.url),'utf8'));
 assert.equal(source.provinces.length,38);assert.equal(new Set(source.provinces.map(p=>p[0])).size,38);
 assert.deepEqual(options.filter(r=>r.level==='provincial').map(r=>r.value).sort(),source.provinces.map(p=>p[1]).sort());
 for(const role of ['anon','authenticated'])assert.equal((await db.query("select has_table_privilege($1,'policy_idn.mail_regions','select') allowed",[role])).rows[0].allowed,false);
 assert.equal((await db.query("select has_function_privilege('anon','public.idn_set_my_mail_subscriptions(text[],text[],boolean)','execute') allowed")).rows[0].allowed,false);
 assert.equal((await db.query("select prosecdef from pg_proc where oid='public.idn_set_my_mail_subscriptions(text[],text[],boolean)'::regprocedure")).rows[0].prosecdef,false);
}));
test('nationwide matches multiple products and every reviewed region, deduplicates overlap, and rechecks opt-out/generation before delivery',()=>fixture(async({db,rpc,acting,sub,change,save,review})=>{
 await acting(U,()=>rpc('idn_set_my_mail_subscriptions',[['coal','nickel_mining'],['__all__'],true]));
 await sub();await sub(V,'nickel_mining','Kalimantan Barat');await rpc('idn_set_mail_delivery_enabled',[true]);
 const east=await change('idn-east');await review(east,{scope:'regions',regions:['Kalimantan Timur']});
 const west=await change('idn-west');await review(west,{scope:'regions',regions:['Kalimantan Barat']});
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,2);
 assert.equal((await db.query('select count(*)::int n from mailing_outbox where user_id=$1',[V])).rows[0].n,0);
 const d={...document('idn-nickel','provincial','Sulawesi Tengah'),topics:['nickel_mining']};await save(d);
 const c=(await rpc('idn_mail_review_queue')).pending.find(x=>x.document_id===d.document_id);
 await review(c,{scope:'regions',regions:['Sulawesi Tengah'],topics:['nickel_mining']});
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,3);
 const national=await change();await assert.rejects(review(national,{scope:'regions',regions:['__all__']}));
 await review(national,{scope:'regions',regions:['Aceh']});
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,4);
 const active=()=>db.query("select public.mail_item_active(o) active from mailing_outbox o where o.content->>'change_id'=$1",[west.change_id]);
 assert.equal((await active()).rows[0].active,true);
 await sub(U,'coal','__all__',false);assert.equal((await active()).rows[0].active,false);
 await sub(U,'coal','__all__',true);assert.equal((await active()).rows[0].active,false);
 const context=(await db.query("select content from mailing_outbox where content->>'change_id'=$1",[west.change_id])).rows[0].content;
 assert.equal(context.scope,'regions');assert.deepEqual(context.regions,['Kalimantan Barat']);
}));
test('bulk subscription limits are atomic, count active combinations, and reuse disabled slots',()=>fixture(async({db,rpc,acting})=>{
 const batch=(topics,regions,enabled=true)=>acting(U,()=>rpc('idn_set_my_mail_subscriptions',[topics,regions,enabled]));
 const regions=(await acting(U,()=>rpc('idn_my_mail_subscriptions'))).region_options.filter(r=>r.value!=='__all__').map(r=>r.value);
 assert.equal((await batch(['coal','nickel_mining','palm_oil'],regions.slice(0,33))).active_combinations,99);
 assert.equal((await batch(['biofuel'],['__all__'])).active_combinations,100);
 await assert.rejects(batch(['gold_silver'],['__all__']),/limit/);
 assert.equal((await db.query('select count(*)::int n from policy_idn.mail_subscriptions where enabled')).rows[0].n,100);
 await batch(['biofuel'],['__all__'],false);assert.equal((await batch(['gold_silver'],['__all__'])).active_combinations,100);
}));
test('metadata/truncated changes stay auditable and held; only a new complete-text version enters review',()=>fixture(async({db,rpc,save,review})=>{
 for(const [id,kind,truncated] of [['idn-metadata','official_metadata',false],['idn-truncated','official_text',true]]){
  const d={...document(id),content_kind:kind,text_truncated:truncated};await save(d);
  const held=(await db.query('select * from policy_idn.mail_changes where document_id=$1',[id])).rows[0];
  assert.equal(held.state,'held');assert.equal(held.hold_reason,'incomplete_official_text');assert.ok(held.held_at);
  await assert.rejects(review(held),/not pending/);
  await db.query("update policy_idn.mail_changes set state='pending' where change_id=$1",[held.change_id]);
  assert.equal((await db.query('select state from policy_idn.mail_changes where change_id=$1',[held.change_id])).rows[0].state,'held');
  await assert.rejects(db.query("update policy_idn.mail_changes set state='reviewed' where change_id=$1",[held.change_id]),/complete official text/);
  const full={...document(id),text_content:body+' Full recovered official text.'};full.content_hash=hash(full.text_content);full.observed_at=new Date().toISOString();
  await save(full);
  const pending=(await rpc('idn_mail_review_queue')).pending.find(c=>c.document_id===id);
  assert.equal(pending.content_kind,'official_text');assert.equal(pending.text_truncated,false);
  assert.equal(await review(pending),true);
 }
 await db.exec(sql(completeSource));
 const q=await rpc('idn_mail_review_queue');assert.equal(q.states.held,2);assert.equal(q.states.reviewed,2);assert.equal(q.held.length,2);
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,0);
}));
test('source gate migration holds existing incomplete candidates without deleting versions or reopening held events',()=>fixture(async({db,rpc,save})=>{
 await db.exec('drop trigger idn_guard_mail_source on policy_idn.mail_changes');
 for(const id of ['idn-legacy-pending','idn-legacy-reviewed'])await save({...document(id),content_kind:'official_metadata'});
 await db.exec("update policy_idn.mail_changes set state='reviewed' where document_id='idn-legacy-reviewed'");
 const before=(await db.query('select count(*)::int n from policy_idn.versions')).rows[0].n;
 await db.exec(sql(completeSource));
 const q=await rpc('idn_mail_review_queue');assert.equal(q.states.held,2);assert.equal(q.pending.length,0);
 assert.equal((await db.query('select count(*)::int n from policy_idn.versions')).rows[0].n,before);
 const heldAt=q.held.map(c=>c.held_at);await db.exec(sql(completeSource));
 assert.deepEqual((await rpc('idn_mail_review_queue')).held.map(c=>c.held_at),heldAt);
}));
test('IDN cross-host lease excludes a second runner and expires without allowing stale writes or unlocks',()=>fixture(async({db,rpc})=>{
 await db.exec(sql(lease));
 const a=await rpc('idn_acquire_sync_lease',['mac:123',900]);assert.equal(a.acquired,true);
 const busy=await rpc('idn_acquire_sync_lease',['github:456',900]);assert.equal(busy.acquired,false);assert.equal(busy.lease_token,undefined);
 assert.equal(await rpc('idn_renew_sync_lease',[a.lease_token,900]),true);
 assert.equal(await rpc('idn_sync_store_document',[JSON.stringify(document('idn-lease')),a.lease_token]),true);
 await db.exec("update policy_idn.sync_lease set expires_at=clock_timestamp()-interval '1 second'");
 assert.equal(await rpc('idn_renew_sync_lease',[a.lease_token,900]),false);
 await assert.rejects(rpc('idn_sync_store_document',[JSON.stringify(document('idn-stale')),a.lease_token]),/lease lost/);
 const b=await rpc('idn_acquire_sync_lease',['github:456',900]);assert.equal(b.acquired,true);assert.notEqual(a.lease_token,b.lease_token);
 assert.equal(await rpc('idn_release_sync_lease',[a.lease_token]),false);
 await assert.rejects(rpc('idn_sync_store_source_check',[JSON.stringify({}),a.lease_token]),/lease lost/);
 const c={document_id:'idn-lease',checked_at:new Date().toISOString(),source_url:'https://test.go.id/idn-lease',outcome:'collected',detail:'official_text'};
 assert.equal(await rpc('idn_sync_store_source_check',[JSON.stringify(c),b.lease_token]),true);
 assert.equal(await rpc('idn_sync_store_source_check',[JSON.stringify(c),b.lease_token]),false);
 const health=await rpc('idn_sync_status');assert.equal(health.lease.active,true);assert.equal(health.lease.lease_token,undefined);assert.equal(health.delivery_enabled,false);
 assert.equal(health.documents,4);assert.equal(health.source_checks_24h.collected,1);
 assert.equal((await db.query("select count(*)::int n from policy_idn.documents where document_id='idn-stale'")).rows[0].n,0);
 assert.equal(await rpc('idn_release_sync_lease',[b.lease_token]),true);assert.equal((await rpc('idn_sync_status')).lease.active,false);
 await assert.rejects(rpc('idn_acquire_sync_lease',['private@example.test',900]));
 await assert.rejects(rpc('idn_acquire_sync_lease',['mac:123',null]));
 await assert.rejects(rpc('idn_acquire_sync_lease',['mac:123',1]));
}));
test('IDN sync coordination/status are service-only and never expose private lease rows to users',()=>fixture(async({db,rpc,acting})=>{
 for(const role of ['anon','authenticated']){
  const allowed=(await db.query(`select count(*)::int n from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public'
   and p.proname in ('idn_acquire_sync_lease','idn_renew_sync_lease','idn_release_sync_lease','idn_sync_store_document','idn_sync_store_source_check','idn_sync_status')
   and (has_function_privilege($1,p.oid,'execute') or p.prosecdef)`,[role])).rows[0].n;
  assert.equal(allowed,0);
 }
 await acting(U,async()=>{await assert.rejects(rpc('idn_sync_status'));await assert.rejects(db.query('select * from policy_idn.sync_lease'));});
 await db.exec('set role service_role');
 try{const a=await rpc('idn_acquire_sync_lease',['mac:123',900]);assert.equal(a.acquired,true);assert.equal(await rpc('idn_release_sync_lease',[a.lease_token]),true);}finally{await db.exec('reset role');}
}));
test('IDN install/replay establishes a quiet baseline and captures only newer version candidates',()=>fixture(async({db,rpc,change,save})=>{
 await db.exec(sql(migration));await db.exec(sql(gateway));await db.exec(sql(gateway));await db.exec(sql(release));assert.equal((await rpc('idn_mail_review_queue')).pending.length,0);
 const c=await change();assert.equal(c.candidate_kind,'content_changed');
 await save({...document('idn-national'),content_hash:hash(body+'older'),text_content:body+'older',observed_at:'2026-09-01T00:00:00Z'});
 await save(document('idn-new'));await db.exec(sql(migration));await db.exec(sql(gateway));
 const q=await rpc('idn_mail_review_queue');assert.equal(q.delivery_enabled,false);assert.equal(q.pending.length,2);
 assert.equal(q.pending.find(x=>x.document_id==='idn-new').candidate_kind,'new_document');
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,0);
}));
test('Auth RPCs isolate subscribers, reject forged input, and do not expose private tables or operator RPCs',()=>fixture(async({db,rpc,acting,sub})=>{
 await sub();await sub(V,'coal','Kalimantan Barat');
 assert.equal((await acting(U,()=>rpc('idn_my_mail_subscriptions'))).subscriptions.length,1);
 await assert.rejects(sub(U,'coal','Unknown Province'));
 await assert.rejects(sub(U,'us_bills'));
 await db.exec('set role anon');await assert.rejects(rpc('idn_my_mail_subscriptions'));await db.exec('reset role');
 await acting(U,async()=>{
  await assert.rejects(db.query('select * from policy_idn.mail_subscriptions'));
  await assert.rejects(rpc('idn_set_mail_delivery_enabled',[true]));
  await assert.rejects(rpc('idn_review_mail_change',[crypto.randomUUID(),'{}']));
 });
 assert.equal((await db.query("select has_function_privilege('anon','public.idn_set_my_mail_subscription(text,text,boolean)','execute') allowed")).rows[0].allowed,false);
 assert.equal((await db.query("select prosecdef from pg_proc where oid='public.idn_set_my_mail_subscription(text,text,boolean)'::regprocedure")).rows[0].prosecdef,false);
}));
test('review binds exact source/quote/topic/region; text hashes never imply a legal amendment',()=>fixture(async({rpc,change,review})=>{
 const c=await change('idn-east');
 await assert.rejects(review(c));
 await assert.rejects(review(c,{scope:'regions',regions:['Kalimantan Barat']}));
 await assert.rejects(review(c,{scope:'regions',regions:['Kalimantan Timur'],quote:'This quote is absent from the official version'}));
 await assert.rejects(review(c,{scope:'regions',regions:['Kalimantan Timur'],source_url:'https://evil.example/doc'}));
 await assert.rejects(review(c,{scope:'regions',regions:['Kalimantan Timur'],topics:['nickel_mining']}));
 assert.equal(await review(c,{scope:'regions',regions:['Kalimantan Timur']}),true);
 assert.equal(await review(c,{scope:'regions',regions:['Kalimantan Timur']}),false);
 assert.equal((await rpc('idn_enqueue_mail_change',[c.change_id,false])).enqueued,0);
 await assert.rejects(rpc('idn_enqueue_mail_change',[c.change_id,true]));
}));
test('product AND region/national matches deduplicate overlaps and send next-day policy mail through the existing lease',()=>fixture(async({db,rpc,sub,change,review})=>{
 await sub();await sub(U,'coal','Kalimantan Barat');await sub(V,'nickel_mining','Kalimantan Timur');
 await rpc('idn_set_mail_delivery_enabled',[true]);const c=await change();await review(c);
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,1);
 const dry=await rpc('idn_enqueue_mail_change',[c.change_id,false]);assert.equal(dry.matching_users,1);assert.equal(dry.enqueued,0);
 assert.equal((await rpc('idn_enqueue_mail_change',[c.change_id,true])).enqueued,0);
 assert.equal((await rpc('idn_enqueue_mail_change',[c.change_id,true])).enqueued,0);
 assert.equal(await rpc('mail_claim',['policy']),null);
 await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");
 let request;
 const result=await runMailing({MAIL_SEND_ENABLED:'true',RESEND_API_KEY:'mock'},{rpc:async(name,args={})=>{
  const entries=Object.entries(args);return (await db.query(`select public.${name}(${entries.map(([k],i)=>k+'=>$'+(i+1)).join(',')}) r`,entries.map(([,v])=>typeof v==='object'&&v!==null?JSON.stringify(v):v))).rows[0].r;
 },fetcher:async(_url,options)=>{request=JSON.parse(options.body);return Response.json({id:'fixture-idn-message'});}});
 assert.equal(result.accepted,1);assert.match(request.subject,/인도네시아/);assert.match(request.text,/전국 적용 범위 검토/);
 assert.match(request.html,/인도네시아 구독 해제/);
 assert.equal((await db.query("select count(*)::int n from mailing_deliveries where state='sent'")).rows[0].n,1);
}));
test('different region and late subscriptions are excluded; disable/re-enable cannot revive an old queued item',()=>fixture(async({db,rpc,sub,change,review})=>{
 await sub();await sub(V,'coal','Kalimantan Barat');await rpc('idn_set_mail_delivery_enabled',[true]);
 const c=await change('idn-east');await review(c,{scope:'regions',regions:['Kalimantan Timur']});
 await sub(V,'coal','Kalimantan Timur');assert.equal((await rpc('idn_enqueue_mail_change',[c.change_id,true])).matching_users,1);
 await sub(U,'coal','Kalimantan Timur',false);await sub();
 assert.equal((await db.query('select public.mail_item_active(o) active from mailing_outbox o')).rows[0].active,false);
 await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");assert.equal(await rpc('mail_claim',['policy']),null);
}));
test('last-moment review hold cancels prepared delivery; US favorite guards remain',()=>fixture(async({db,rpc,sub,change,review})=>{
 await sub();await rpc('idn_set_mail_delivery_enabled',[true]);const c=await change();await review(c);await rpc('idn_enqueue_mail_change',[c.change_id,true]);
 await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");const d=await rpc('mail_claim',['policy']);
 await rpc('idn_hold_mail_change',[c.change_id]);
 assert.equal(await rpc('mail_prepare',[d.delivery_id,d.lease_token,JSON.stringify(renderDelivery(d,'alerts@example.test'))]),null);
 const def=(await db.query("select pg_get_functiondef('public.mail_item_active(public.mailing_outbox)'::regprocedure) f")).rows[0].f;
 assert.match(def,/bill_notifications_paused/);assert.match(def,/notify_enabled/);assert.match(def,/commodity_report_notifications/);
}));
test('unsubscribe and global policy opt-out are rechecked after claim; activation does not revive old IDN jobs',()=>fixture(async({db,rpc,sub,change,review})=>{
 await sub();await rpc('idn_set_mail_delivery_enabled',[true]);const c=await change();await review(c);await rpc('idn_enqueue_mail_change',[c.change_id,true]);
 await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");const d=await rpc('mail_claim',['policy']);
 await sub(U,'coal','Kalimantan Timur',false);
 assert.equal(await rpc('mail_prepare',[d.delivery_id,d.lease_token,JSON.stringify(renderDelivery(d,'alerts@example.test'))]),null);
 await sub();const c2=await change('idn-national','Another changed requirement.');await review(c2);await rpc('idn_enqueue_mail_change',[c2.change_id,true]);
 await db.exec("insert into mailing_preferences(user_id,policy_enabled) values('"+U+"',false)");
 assert.equal((await db.query('select public.mail_item_active(o) active from mailing_outbox o where content->>\'change_id\'=$1',[c2.change_id])).rows[0].active,false);
 await db.exec('update mailing_preferences set policy_enabled=true');
 await rpc('idn_set_mail_delivery_enabled',[false]);await rpc('idn_set_mail_delivery_enabled',[true]);
 assert.equal((await db.query('select public.mail_item_active(o) active from mailing_outbox o where content->>\'change_id\'=$1',[c2.change_id])).rows[0].active,false);
}));
test('US bill notify switch and pause continue to suppress the existing branch after IDN migration',()=>fixture(async({db,rpc})=>{
 await db.exec(`insert into bills values('119-hr-test','US sentinel','introduced','',now());
 insert into user_favorites(user_id,item_kind,item_id) values('${U}','bill','119-hr-test');
 update bills set current_stage='reported';`);
 const active=async()=>(await db.query("select public.mail_item_active(o) a from mailing_outbox o where item_kind='bill'")).rows[0].a;
 assert.equal(await active(),true);await db.exec('update user_favorites set notify_enabled=false');assert.equal(await active(),false);
 await db.exec('update user_favorites set notify_enabled=true;update profiles set bill_notifications_paused=true');assert.equal(await active(),false);
 assert.equal((await rpc('idn_mail_review_queue')).pending.length,0);
}));
test('failed queue write rolls back review completion and retry releases exactly one event',()=>fixture(async({db,rpc,sub,change,review})=>{
 await sub();await rpc('idn_set_mail_delivery_enabled',[true]);const c=await change();
 await db.exec(`create function public.idn_fixture_failure() returns trigger language plpgsql as $$ begin raise exception 'fixture queue failure'; end $$;
 create trigger idn_fixture_failure before insert on mailing_outbox for each row execute function public.idn_fixture_failure();`);
 await assert.rejects(review(c));assert.equal((await db.query('select state from policy_idn.mail_changes where change_id=$1',[c.change_id])).rows[0].state,'pending');
 await db.exec('drop trigger idn_fixture_failure on mailing_outbox');assert.equal(await review(c),true);
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,1);
}));
test('metadata or truncated fallback preserves complete text, freshness and quiet mail state',()=>fixture(async({db,rpc,save})=>{
 const before=(await db.query("select last_observed_at from policy_idn.documents where document_id='idn-national'")).rows[0].last_observed_at;
 const fallback={...document('idn-national'),title_ko:'must not replace',content_kind:'official_metadata',observed_at:new Date().toISOString(),text_content:body+'catalogue fallback',content_hash:hash(body+'catalogue fallback')};
 assert.equal(await save(fallback),false);
 assert.equal(await save({...fallback,content_kind:'official_text',text_truncated:true}),false);
 assert.equal((await db.query("select last_observed_at from policy_idn.documents where document_id='idn-national'")).rows[0].last_observed_at.toISOString(),before.toISOString());
 assert.equal((await rpc('idn_mail_review_queue')).pending.length,0);
 assert.equal((await db.query("select outcome from policy_idn.source_checks where document_id='idn-national'")).rows[0].outcome,'failed');
 assert.equal(await save({...fallback,document_id:'idn-new-meta',document_number:'new-meta'}),true);
}));
