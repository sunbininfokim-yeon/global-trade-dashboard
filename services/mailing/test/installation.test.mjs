import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';
const files = ['20260911010000_mailing_outbox.sql','20260919_bill_notification_pause.sql','20260919_favorite_notify_enabled.sql','20260920020000_mailing_bill_lifecycle.sql','20261002010000_mailing_bill_event_identity.sql','20261002020000_mailing_subscription_preferences.sql'];
const sql = name => readFileSync(new URL(`../../../supabase/migrations/${name}`, import.meta.url), 'utf8');
const U = '00000000-0000-0000-0000-000000000001';
async function fixture(fn) {
 const db = new PGlite();
 try {
  // Empty database: application's prerequisites, then real mailing migrations.
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
   create schema auth;
   create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
   create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
   create table profiles(id uuid primary key,email text);
   create table user_favorites(user_id uuid references profiles(id),item_kind text,item_id text,title text,created_at timestamptz default now(),primary key(user_id,item_kind,item_id));
   create table bills(bill_id text primary key,title text,current_stage text,latest_action_text text,status_updated_at timestamptz,raw_source jsonb);
   create table executive_orders(eo_number integer primary key,title text,summary text,updated_at timestamptz);
   create table commodity_report_notifications(user_id uuid,report_id text,sent_at timestamptz default now(),primary key(user_id,report_id));
   create table commodity_digest_source_prefs(user_id uuid,source_id text,primary key(user_id,source_id));`);
  for (const file of files) await db.exec(sql(file));
  await fn(db);
 } finally { await db.close(); }
}
test('empty mailing install and ordered replay preserve modern guards, single trigger and RPC isolation', () => fixture(async db => {
 for (const file of files) await db.exec(sql(file));
 assert.equal((await db.query("select count(*)::int n from pg_trigger where tgname='mail_bill_stage_changed' and not tgisinternal")).rows[0].n, 1);
 const definitions = await db.query("select pg_get_functiondef('public.mail_capture_bill_stage()'::regprocedure) capture, pg_get_functiondef('public.mail_item_active(public.mailing_outbox)'::regprocedure) active");
 assert.match(definitions.rows[0].capture, /yea_count/); assert.match(definitions.rows[0].active, /bill_notifications_paused/); assert.match(definitions.rows[0].active, /notify_enabled/);
 assert.equal((await db.query("select count(*)::int n from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('mail_claim','mail_prepare','mail_complete','mail_fail','mail_status') and (has_function_privilege('anon',p.oid,'execute') or has_function_privilege('authenticated',p.oid,'execute'))")).rows[0].n, 0);
}));
test('installed pipeline captures same-day votes once, next-day 06:00 KST and pause recheck before claim', () => fixture(async db => {
 await db.exec(`insert into auth.users values('${U}','verified@example.test',now()); insert into profiles(id,email) values('${U}','profile@example.test');
 insert into bills values('119-hr-3633','CLARITY','second_chamber','',now(),'{}');
 insert into user_favorites(user_id,item_kind,item_id) values('${U}','bill','119-hr-3633');`);
 const life = { version:1,current:{step_id:'senate_reported',stage:'second_chamber'},latest_event:{kind:'procedural_vote',chamber:'senate',date:'2026-09-15',text:'Cloture rejected',vote:{kind:'cloture',result:'failed',yea_count:49,nay_count:50}} };
 const patch = () => db.query("update bills set raw_source=$1::jsonb",[JSON.stringify({lifecycle:life})]);
 await patch(); life.latest_event.text='Motion to proceed rejected';life.latest_event.vote.kind='motion_to_proceed';await patch();await patch();
 assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n,1);
 assert.equal((await db.query("select to_char(due_at at time zone 'Asia/Seoul','HH24:MI') t from mailing_outbox")).rows[0].t,'06:00');
 await db.exec("update mailing_outbox set due_at=now()-interval '1 minute'; update profiles set bill_notifications_paused=true");
 assert.equal((await db.query('select mail_claim() value')).rows[0].value,null);
 assert.equal((await db.query('select count(*)::int n from mailing_deliveries')).rows[0].n,0);
}));
