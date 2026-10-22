import { test, before, beforeEach, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';
import { runMailing } from '../core.mjs';
const files = ['20260911010000_mailing_outbox.sql','20260919_bill_notification_pause.sql',
  '20260919_favorite_notify_enabled.sql','20260920020000_mailing_bill_lifecycle.sql',
  '20261002010000_mailing_bill_event_identity.sql','20261002020000_mailing_subscription_preferences.sql'];
const migration = readFileSync(new URL('../../../supabase/migrations/20261021042059_mailing_report_editions.sql', import.meta.url), 'utf8');
const sql = name => readFileSync(new URL(`../../../supabase/migrations/${name}`, import.meta.url), 'utf8');
const U = '00000000-0000-0000-0000-000000000001';
let db;
before(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth;
    create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
    create table profiles(id uuid primary key,email text);
    create table user_favorites(user_id uuid references profiles(id),item_kind text,item_id text,title text,created_at timestamptz default now(),primary key(user_id,item_kind,item_id));
    create table bills(bill_id text primary key,title text,current_stage text,latest_action_text text,status_updated_at timestamptz,raw_source jsonb);
    create table executive_orders(eo_number integer primary key,title text,summary text,updated_at timestamptz);
    create table commodity_report_notifications(user_id uuid,report_id text,sent_at timestamptz default now(),primary key(user_id,report_id));
    create table commodity_digest_source_prefs(user_id uuid,source_id text,primary key(user_id,source_id));`);
  for (const file of files) await db.exec(sql(file));
  await db.exec(migration);
});
after(async () => db.close());
beforeEach(async () => {
  await db.exec(`truncate mailing_outbox,mailing_deliveries,mailing_reports,mailing_report_edition_receipts,
    mailing_preferences,user_favorites,bills,executive_orders,commodity_report_notifications,
    commodity_digest_source_prefs,profiles,auth.users cascade;
    insert into auth.users values('${U}','verified@example.test',now());
    insert into profiles(id,email) values('${U}','profile@example.test');
    insert into user_favorites(user_id,item_kind,item_id,created_at)
    values('${U}','commodity','wheat',now()-interval '20 days'),('${U}','commodity','corn',now()-interval '20 days');`);
});
const count = async table => (await db.query(`select count(*)::int n from ${table}`)).rows[0].n;
async function report(daysAgo = 1, title = 'Official report', id = 'permanent') {
  // Date-only publications are kept stable across retry statements.
  await db.query(`insert into mailing_reports(report_id,source_id,title,summary,url,published_at,commodities)
    values($1,'usda',$2,'Summary','https://example.test/report',date_trunc('day',now())-$3::int*interval '1 day',array['wheat','corn'])
    on conflict(report_id) do update set title=excluded.title,published_at=excluded.published_at,commodities=excluded.commodities`, [id,title,daysAgo]);
}
async function rpc(name, args = {}) {
  const entries = Object.entries(args);
  return (await db.query(`select ${name}(${entries.map(([k],i) => `${k}=>$${i+1}`).join(',')}) as value`,
    entries.map(([,v]) => v!==null && typeof v==='object' ? JSON.stringify(v) : v))).rows[0].value;
}
const env = { MAIL_SEND_ENABLED: 'true', RESEND_API_KEY: 'mock', NOTIFY_FROM_EMAIL: 'alerts@example.test' };
async function send() {
  await db.exec("update mailing_outbox set due_at=now()-interval '1 minute' where delivery_id is null");
  let calls = 0;
  await runMailing(env, { rpc, fetcher: async () => { calls++; return Response.json({ id:crypto.randomUUID() }); } });
  return calls;
}
test('same URL weekly editions each reach the existing Worker despite legacy report-ID receipt', async () => {
  await report(7); assert.equal(await count('mailing_outbox'),1);
  assert.equal(await send(),1);
  assert.equal(await count('commodity_report_notifications'),1);
  await report(1);
  assert.equal(await count('mailing_reports'),1);
  assert.equal(await count('mailing_report_editions'),2);
  assert.equal(await count('mailing_outbox'),2);
  assert.equal(await send(),1);
  assert.equal(await count('mailing_report_edition_receipts'),2);
  await report(1); assert.equal(await send(),0);
  assert.equal(await count('mailing_outbox'),2);
});
test('same-edition title/tag corrections and replay do not create a second event', async () => {
  await report(); await report(1,'Corrected heading');
  assert.equal(await count('mailing_outbox'),1);
  assert.equal((await db.query('select content from mailing_outbox')).rows[0].content.title,'Corrected heading');
  assert.equal(await send(),1);
  await report(1,'Revised heading');
  assert.equal(await count('mailing_outbox'),1);
  assert.equal(await send(),0);
});
test('stale recovery cannot roll back latest edition or create another notification', async () => {
  await report(1,'New edition'); await report(7,'Stale artifact');
  assert.equal((await db.query('select title from mailing_reports')).rows[0].title,'New edition');
  assert.equal(await count('mailing_outbox'),1);
  assert.equal(await count('mailing_report_editions'),1);
});
test('legacy-only receipt blocks old publication, but allows a later official edition', async () => {
  await db.exec(`insert into commodity_report_notifications values('${U}','permanent',date_trunc('day',now())-interval '3 days')`);
  await report(7); assert.equal(await count('mailing_outbox'),0);
  await report(1); assert.equal(await count('mailing_outbox'),1);
  assert.equal(await send(),1);
});
test('late collection schedules next Monday 08:00 KST instead of immediate catch-up email', async () => {
  await report(7);
  const row = (await db.query(`select due_at>=now() as future,
    extract(isodow from due_at at time zone 'Asia/Seoul')::int dow,
    to_char(due_at at time zone 'Asia/Seoul','HH24:MI') as time from mailing_outbox`)).rows[0];
  assert.equal(row.future,true); assert.equal(row.dow,1); assert.equal(row.time,'08:00');
});
test('initial historical import is archived without mailing, and later current edition is eligible', async () => {
  await report(30); assert.equal(await count('mailing_report_editions'),1); assert.equal(await count('mailing_outbox'),0);
  await report(1); assert.equal(await count('mailing_outbox'),1);
});
test('unsubscribe, source opt-out, and preference are rechecked before provider call', async () => {
  for (const change of ["update user_favorites set notify_enabled=false",
    "insert into commodity_digest_source_prefs values('"+U+"','usda')",
    "insert into mailing_preferences(user_id,commodity_enabled) values('"+U+"',false)"]) {
    await db.exec("truncate mailing_outbox,mailing_deliveries,mailing_reports,mailing_report_edition_receipts,commodity_report_notifications,mailing_preferences,commodity_digest_source_prefs cascade; update user_favorites set notify_enabled=true");
    await report(); await db.exec(change); assert.equal(await send(),0);
  }
});
test('legacy acceptance arriving after claim still cancels an unsent initial edition', async () => {
  await report(); await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");
  let calls=0;
  await runMailing(env,{rpc:async(name,args) => {
    const value=await rpc(name,args);
    if(name==='mail_claim' && value) await db.exec(`insert into commodity_report_notifications values('${U}','permanent',now()) on conflict do nothing`);
    return value;
  },fetcher:async() => {calls++; return Response.json({id:crypto.randomUUID()});}});
  assert.equal(calls,0);
  assert.equal((await db.query('select state from mailing_deliveries')).rows[0].state,'cancelled');
});
test('retry and frozen payload remain unchanged if the next edition arrives mid-delivery', async () => {
  await report(7); await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'");
  let frozen;
  await runMailing(env,{rpc,fetcher:async(_url,request) => { frozen=request.body; return Response.json({}, {status:429}); }});
  await report(1,'Next edition');
  await db.exec("update mailing_deliveries set next_attempt_at=now()-interval '1 minute'");
  const requests=[];
  await runMailing(env,{rpc,fetcher:async(_url,request) => { requests.push(request.body); return Response.json({id:crypto.randomUUID()}); }});
  assert.equal(requests[0],frozen);
  assert.equal(await count('mailing_report_edition_receipts'),1);
  assert.equal(await send(),1);
  assert.equal(await count('mailing_report_edition_receipts'),2);
});
test('migration replay preserves current policy/Indonesia guards and never requeues history', async () => {
  await report(); assert.equal(await send(),1);
  const original=(await db.query("select pg_get_functiondef('mail_item_active(mailing_outbox)'::regprocedure) def")).rows[0].def;
  await db.exec(`create schema if not exists policy_idn;
    create or replace function policy_idn.mail_item_active(public.mailing_outbox) returns boolean language sql as $$select false$$`);
  // Simulate the deployed optional gateway without replacing its implementation.
  const legacy = original.replace("not public.mail_report_edition_sent(o.user_id,o.item_id,(o.content->>'published_at')::timestamptz)",
    'not exists(select 1 from public.commodity_report_notifications n where n.user_id=o.user_id and n.report_id=o.item_id)');
  assert.notEqual(legacy,original);
  await db.exec(legacy.replace("case when o.kind='policy'", "case when o.item_kind='idn_policy' then policy_idn.mail_item_active(o) when o.kind='policy'"));
  for (let i=0;i<2;i++) await db.exec(migration);
  const definition=(await db.query("select pg_get_functiondef('mail_item_active(mailing_outbox)'::regprocedure) def")).rows[0].def;
  for (const guard of ['policy_idn.mail_item_active','notify_enabled','bill_notifications_paused','mail_report_edition_sent']) assert.ok(definition.includes(guard));
  assert.equal(await count('mailing_outbox'),1);
  assert.equal(await count('mailing_report_edition_receipts'),1);
  assert.equal((await db.query("select count(*)::int n from pg_trigger where tgname='mail_report_archived' and not tgisinternal")).rows[0].n,1);
  await db.exec(original);
});
test('cutover seeds proven acceptances and baseline metadata without a historical queue replay', async () => {
  await report(7); assert.equal(await send(),1);
  await report(1);
  const before = await count('mailing_outbox');
  await db.exec('truncate mailing_report_editions,mailing_report_edition_receipts');
  await db.exec(migration);
  assert.equal(await count('mailing_outbox'),before);
  assert.equal(await count('mailing_report_editions'),1);
  assert.equal(await count('mailing_report_edition_receipts'),1);
  assert.equal(await send(),1);
  assert.equal(await count('mailing_report_edition_receipts'),2);
});
test('unknown active-function drift aborts all migration changes instead of overwriting guards', async () => {
  const original=(await db.query("select pg_get_functiondef('mail_item_active(mailing_outbox)'::regprocedure) def")).rows[0].def;
  await db.exec('create or replace function mail_item_active(o mailing_outbox) returns boolean language sql as $$select false$$');
  try {
    await assert.rejects(db.exec(migration), /mail_item_active drift/);
    await db.exec('rollback');
    assert.equal((await db.query("select mail_item_active(null::mailing_outbox) active")).rows[0].active,false);
  } finally { await db.exec(original); }
});
test('edition identity is timezone-independent and browser roles cannot read receipts or call helpers', async () => {
  const key=async () => (await db.query("select mail_report_event_key('r','2026-10-01T00:00:00Z') k")).rows[0].k;
  const first=await key(); await db.exec("set timezone='Asia/Seoul'"); assert.equal(await key(),first); await db.exec("set timezone='UTC'");
  for(const role of ['anon','authenticated']) {
    const result=(await db.query(`select has_table_privilege($1,'mailing_report_editions','select') metadata,
      has_table_privilege($1,'mailing_report_edition_receipts','select') receipts,
      has_function_privilege($1,'mail_report_edition_sent(uuid,text,timestamptz)','execute') helper`,[role])).rows[0];
    assert.deepEqual(result,{metadata:false,receipts:false,helper:false});
  }
  assert.equal((await db.query("select relrowsecurity from pg_class where oid='mailing_report_edition_receipts'::regclass")).rows[0].relrowsecurity,true);
});
test('service-role importer can insert and update through the protected triggers', async () => {
  await db.exec('set role service_role');
  try { await report(7); await report(1); } finally { await db.exec('reset role'); }
  assert.equal(await count('mailing_report_editions'),2);
  assert.equal(await count('mailing_outbox'),2);
});
