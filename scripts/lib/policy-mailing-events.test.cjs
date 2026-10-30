const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PGlite } = require('@electric-sql/pglite');

const migration = fs.readFileSync(path.join(__dirname, '../../supabase/migrations/20261002010000_mailing_bill_event_identity.sql'), 'utf8');
const base = {
  version: 1,
  current: { stage: 'second_chamber', step_id: 'senate_reported', label: '상원 상임위 보고' },
  latest_event: { kind: 'procedural_vote', chamber: 'senate', date: '2026-09-15', text: 'Cloture on the motion to proceed rejected. 49-50.',
    vote: { kind: 'cloture', result: 'failed', yea_count: 49, nay_count: 50 } }
};

async function fixture(fn) {
  const db = new PGlite();
  try {
    await db.exec(`create table public.bills(bill_id text primary key,title text,current_stage text,latest_action_text text,status_updated_at timestamptz,raw_source jsonb);
      create table public.user_favorites(user_id uuid,item_kind text,item_id text,created_at timestamptz default now());
      create table public.mailing_outbox(user_id uuid,event_key text,kind text,item_kind text,item_id text,favorite_created_at timestamptz,content jsonb,due_at timestamptz);
      create function public.mail_next_due(text,timestamptz) returns timestamptz language sql as $$ select $2+interval '1 day' $$;
      insert into public.bills values('119-hr-3633','CLARITY','second_chamber','',now(),'{}');
      insert into public.user_favorites values('00000000-0000-0000-0000-000000000001','bill','119-hr-3633',now());`);
    await db.exec(migration);
    await db.exec(`create trigger mail_bill_stage_changed after update of current_stage,raw_source on public.bills for each row execute function public.mail_capture_bill_stage()`);
    const patch = life => db.query("update public.bills set raw_source=$1::jsonb", [JSON.stringify({ lifecycle: life })]);
    const count = async () => (await db.query('select count(*)::int n from mailing_outbox')).rows[0].n;
    await fn({ db, patch, count });
  } finally { await db.close(); }
}

test('baseline and repeat snapshots stay silent; migration is rerunnable', () => fixture(async ({ db, patch, count }) => {
  await patch(base); await patch(base); await db.exec(migration); await patch(base);
  assert.equal(await count(), 0);
}));
test('same-day same-result vote with different question/type is captured exactly once', () => fixture(async ({ patch, count, db }) => {
  await patch(base);
  const vote = structuredClone(base);
  vote.latest_event.text = 'Motion to proceed rejected. 49-50.';
  vote.latest_event.vote.kind = 'motion_to_proceed';
  await patch(vote); await patch(vote);
  assert.equal(await count(), 1);
  const row = (await db.query('select content from mailing_outbox')).rows[0].content;
  assert.equal(row.from_stage, row.to_stage);
  assert.equal(row.lifecycle.latest_event.vote.kind, 'motion_to_proceed');
}));
test('same type/date with a distinct action text is a separate event', () => fixture(async ({ patch, count }) => {
  await patch(base);
  const next = structuredClone(base); next.latest_event.text = 'Cloture on H.R. 3633 rejected. 49-50.';
  await patch(next); await patch(next); assert.equal(await count(), 1);
}));
test('official tally correction survives, while presentation and whitespace edits stay silent', () => fixture(async ({ patch, count }) => {
  await patch(base);
  const meta = structuredClone(base);
  meta.current.label = '상원 위원회 보고';
  meta.latest_event.source_url = 'https://www.congress.gov/bill/119th-congress/house-bill/3633';
  meta.latest_event.action_id = 456;
  meta.latest_event.vote.tally_source = 'recorded_vote';
  meta.latest_event.text = '  Cloture  on the motion to proceed rejected. 49-50. \n';
  await patch(meta); assert.equal(await count(), 0);
  meta.latest_event.vote.yea_count = 50; await patch(meta); await patch(meta);
  assert.equal(await count(), 1);
}));
test('stage change and notification roll back together; nonfavorites produce no rows', () => fixture(async ({ db, patch, count }) => {
  await patch(base);
  await db.exec('begin');
  const changed = structuredClone(base); changed.current.step_id = 'senate_passage'; changed.current.stage = 'passed_both_chambers';
  await patch(changed); assert.equal(await count(), 1);
  await db.exec('rollback'); assert.equal(await count(), 0);
  await db.exec('delete from user_favorites'); await patch(changed); assert.equal(await count(), 0);
}));
