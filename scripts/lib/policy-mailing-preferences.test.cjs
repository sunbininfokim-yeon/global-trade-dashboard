const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PGlite } = require('@electric-sql/pglite');
const migration = fs.readFileSync(path.join(__dirname, '../../supabase/migrations/20261002020000_mailing_subscription_preferences.sql'), 'utf8');
const U = '00000000-0000-0000-0000-000000000001';
async function fixture(fn) {
  const db = new PGlite();
  try {
    await db.exec(`create table public.mailing_preferences(user_id uuid,policy_enabled boolean,commodity_enabled boolean);
      create table public.profiles(id uuid,bill_notifications_paused boolean);
      create table public.user_favorites(user_id uuid,item_kind text,item_id text,created_at timestamptz,notify_enabled boolean);
      create table public.commodity_report_notifications(user_id uuid,report_id text);
      create table public.commodity_digest_source_prefs(user_id uuid,source_id text);
      create table public.mailing_outbox(user_id uuid,kind text,item_kind text,item_id text,favorite_created_at timestamptz,content jsonb);
      insert into profiles values('${U}',false);
      insert into user_favorites values('${U}','bill','119-hr-3633','2026-09-01',true),('${U}','commodity','crude_oil','2026-09-01',true);
      insert into mailing_outbox values('${U}','policy','bill','119-hr-3633','2026-09-01','{}'),
        ('${U}','commodity','commodity','report-1',null,'{"commodities":["crude_oil"],"published_at":"2026-09-20T00:00:00Z","source_id":"eia"}');`);
    await db.exec(migration); await db.exec(migration);
    const active = async kind => (await db.query('select public.mail_item_active(o) value from public.mailing_outbox o where kind=$1', [kind])).rows[0].value;
    await fn({ db, active });
  } finally { await db.close(); }
}
test('policy respects per-item opt-out, account pause, channel preference and re-created favorites', () => fixture(async ({ db, active }) => {
  assert.equal(await active('policy'), true);
  await db.exec("update user_favorites set notify_enabled=false where item_kind='bill'"); assert.equal(await active('policy'), false);
  await db.exec("update user_favorites set notify_enabled=true; update profiles set bill_notifications_paused=true"); assert.equal(await active('policy'), false);
  await db.exec(`update profiles set bill_notifications_paused=false; insert into mailing_preferences values('${U}',false,true)`); assert.equal(await active('policy'), false);
  await db.exec('update mailing_preferences set policy_enabled=true'); assert.equal(await active('policy'), true);
  await db.exec("update user_favorites set created_at='2026-09-02' where item_kind='bill'"); assert.equal(await active('policy'), false);
}));
test('commodity respects item/channel/source preferences, receipts and subscription start', () => fixture(async ({ db, active }) => {
  assert.equal(await active('commodity'), true);
  await db.exec("update user_favorites set notify_enabled=false where item_kind='commodity'"); assert.equal(await active('commodity'), false);
  await db.exec(`update user_favorites set notify_enabled=true; insert into mailing_preferences values('${U}',true,false)`); assert.equal(await active('commodity'), false);
  await db.exec(`update mailing_preferences set commodity_enabled=true; insert into commodity_digest_source_prefs values('${U}','eia')`); assert.equal(await active('commodity'), false);
  await db.exec(`delete from commodity_digest_source_prefs; insert into commodity_report_notifications values('${U}','report-1')`); assert.equal(await active('commodity'), false);
  await db.exec('delete from commodity_report_notifications'); assert.equal(await active('commodity'), true);
  await db.exec("update user_favorites set created_at='2026-09-21' where item_kind='commodity'"); assert.equal(await active('commodity'), false);
}));
