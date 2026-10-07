import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';
import { renderDelivery } from '../core.mjs';
const migration = readFileSync(new URL('../../../supabase/migrations/20260920020000_mailing_bill_lifecycle.sql', import.meta.url), 'utf8');
const snapshot = { version: 1, origin_chamber: 'house', current: { stage: 'second_chamber', step_id: 'senate_reported', label: '상원 상임위 보고' }, latest_event: { kind: 'procedural_vote', chamber: 'senate', date: '2026-09-15', source_url: 'https://www.congress.gov/bill/119th-congress/house-bill/3633', vote: { kind: 'cloture', result: 'failed', yea_count: 49, nay_count: 50 } }, procedural_alert: { label: '상원 토론 종결 표결 부결' }, next: { label: '상원 본회의 통과' } };
test('lifecycle trigger: baseline silent, same-stage procedural change captured once, metadata edit silent', async () => {
  const db = new PGlite();
  try {
    await db.exec(`create table public.bills(bill_id text,title text,current_stage text,latest_action_text text,status_updated_at timestamptz,raw_source jsonb);
      create table public.user_favorites(user_id uuid,item_kind text,item_id text,created_at timestamptz default now());
      create table public.mailing_outbox(user_id uuid,event_key text,kind text,item_kind text,item_id text,favorite_created_at timestamptz,content jsonb,due_at timestamptz);
      create function public.mail_next_due(text,timestamptz) returns timestamptz language sql as $$ select $2 + interval '1 day' $$;
      insert into public.bills values ('119-hr-3633','CLARITY','reported','reported',now(),'{}');
      insert into public.user_favorites values ('00000000-0000-0000-0000-000000000001','bill','119-hr-3633',now());`);
    await db.exec(migration); await db.exec(migration);
    const patch = async life => db.query("update public.bills set current_stage='second_chamber',raw_source=$1::jsonb", [JSON.stringify({ lifecycle: life })]);
    await patch(snapshot);
    assert.equal((await db.query('select count(*)::int n from mailing_outbox')).rows[0].n, 0);
    const updated = structuredClone(snapshot); updated.latest_event.date = '2026-09-16';
    await patch(updated); await patch(updated);
    updated.current.label = '상원 위원회 보고';
    await patch(updated);
    const rows = (await db.query('select content from mailing_outbox')).rows;
    assert.equal(rows.length, 1);
    assert.equal(rows[0].content.lifecycle.latest_event.vote.result, 'failed');
    assert.equal(rows[0].content.from_stage, 'second_chamber');
    assert.equal(rows[0].content.to_stage, 'second_chamber');
  } finally { await db.close(); }
});
test('mail shows origin, procedural result, tally and safe evidence link without asserting Senate passage', () => {
  const mail = renderDelivery({ kind: 'policy', recipient: 'test@example.com', items: [{ item_kind: 'bill', item_id: '119-hr-3633', content: { title: 'CLARITY', lifecycle: snapshot, from_stage: 'second_chamber', to_stage: 'second_chamber' } }] }, 'alerts@chokemonitor.com');
  assert.match(mail.text, /발의: 하원/); assert.match(mail.text, /현재: 상원 상임위 보고/);
  assert.match(mail.text, /토론 종결 표결 부결/); assert.match(mail.text, /찬성 49 · 반대 50/);
  assert.match(mail.text, /다음 확인: 상원 본회의 통과/);
  const unsafe = structuredClone(snapshot); unsafe.latest_event.source_url = 'javascript:alert(1)'; unsafe.current.label = '<script>bad</script>';
  const html = renderDelivery({ kind: 'policy', recipient: 'test@example.com', items: [{ item_kind: 'bill', content: { lifecycle: unsafe } }] }, 'alerts@chokemonitor.com').html;
  assert.doesNotMatch(html, /javascript:|<script>/);
});
