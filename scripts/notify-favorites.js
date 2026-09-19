'use strict';

// Runs after sync-congress.js / sync-federal-register.js update bills and
// executive_orders. Compares each favorited item's current state against
// favorite_notifications' last-seen snapshot, and emails a per-user digest
// of what changed since they favorited it (or since the last email).
const {
  requireEnv, supabaseGet, supabaseUpsert, fetchJson,
} = require('./lib/sync-utils');

requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');
const RESEND_API_KEY = requireEnv('RESEND_API_KEY');
const FROM_EMAIL = process.env.NOTIFY_FROM_EMAIL || 'alerts@chokemonitor.com';
const SITE_URL = 'https://chokemonitor.com/policy/us';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function fetchFavorites() {
  return supabaseGet('user_favorites', { select: 'user_id,item_kind,item_id,title' });
}

async function fetchBills(ids) {
  if (!ids.length) return new Map();
  const rows = await supabaseGet('bills', {
    select: 'bill_id,title,current_status,current_stage,latest_action_text,status_updated_at,updated_at',
    bill_id: `in.(${ids.join(',')})`,
  });
  return new Map(rows.map((row) => [row.bill_id, {
    title: row.title,
    changedAt: row.status_updated_at || row.updated_at,
    summaryLine: row.current_status || row.current_stage,
    detailLine: row.latest_action_text || null,
  }]));
}

async function fetchExecutiveOrders(ids) {
  if (!ids.length) return new Map();
  const rows = await supabaseGet('executive_orders', {
    select: 'eo_number,title,summary,updated_at',
    eo_number: `in.(${ids.join(',')})`,
  });
  return new Map(rows.map((row) => [String(row.eo_number), {
    title: row.title,
    changedAt: row.updated_at,
    // Executive orders have no separate "status" -- a summary appearing
    // after the fact (Federal Register publishes text before Gemini
    // summarizes it) is the one thing worth telling a favoriter about.
    summaryLine: row.summary ? '요약 추가됨' : null,
    detailLine: row.summary || null,
  }]));
}

async function fetchProfiles(userIds) {
  if (!userIds.length) return new Map();
  const rows = await supabaseGet('profiles', {
    select: 'id,email,bill_notifications_paused',
    id: `in.(${userIds.join(',')})`,
  });
  return new Map(rows.map((row) => [row.id, { email: row.email, paused: !!row.bill_notifications_paused }]));
}

async function fetchLastSeen(pairs) {
  // favorite_notifications has no covering index for an arbitrary batch of
  // (user_id,item_kind,item_id) triples, so this pulls everything once and
  // filters in memory -- the table is bounded by favorite count, not by
  // policy-corpus size.
  const rows = await supabaseGet('favorite_notifications', {
    select: 'user_id,item_kind,item_id,last_seen_updated_at',
  });
  const map = new Map();
  for (const row of rows) map.set(`${row.user_id}:${row.item_kind}:${row.item_id}`, row.last_seen_updated_at);
  return map;
}

async function sendDigest(email, changes) {
  const items = changes.map((c) => `
    <li style="margin-bottom:12px;">
      <strong>${esc(c.title)}</strong><br>
      <span style="color:#4a5a61;">${esc(c.summaryLine || '상태 업데이트')}</span>
      ${c.detailLine ? `<br><span style="color:#6b7780;font-size:13px;">${esc(c.detailLine).slice(0, 200)}</span>` : ''}
    </li>`).join('');
  const html = `
    <div style="font-family:-apple-system,sans-serif;max-width:560px;">
      <h2 style="margin:0 0 16px;">즐겨찾기한 정책이 업데이트됐습니다</h2>
      <ul style="padding-left:20px;">${items}</ul>
      <p style="margin-top:24px;"><a href="${SITE_URL}">ChokePoint Monitor에서 전체 보기 →</a></p>
      <p style="margin-top:32px;color:#94a3b8;font-size:12px;">
        이 메일은 회원가입 시 즐겨찾기하신 정책의 변경 알림입니다.
      </p>
    </div>`;
  const res = await fetchJson('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: email,
      subject: `[ChokePoint Monitor] 즐겨찾기 정책 업데이트 ${changes.length}건`,
      html,
    }),
  }, { label: 'Resend send' });
  return res;
}

async function run() {
  const favorites = await fetchFavorites();
  if (!favorites.length) {
    console.log('No favorites to check.');
    return;
  }

  const billIds = [...new Set(favorites.filter((f) => f.item_kind === 'bill').map((f) => f.item_id))];
  const eoIds = [...new Set(favorites.filter((f) => f.item_kind === 'executive_order').map((f) => f.item_id))];
  const [bills, eos, lastSeen] = await Promise.all([
    fetchBills(billIds),
    fetchExecutiveOrders(eoIds),
    fetchLastSeen(favorites),
  ]);

  const byUser = new Map(); // user_id -> [{title, summaryLine, detailLine}]
  const seenUpdates = []; // rows to upsert into favorite_notifications

  for (const fav of favorites) {
    const source = fav.item_kind === 'bill' ? bills : eos;
    const item = source.get(fav.item_id);
    if (!item || !item.changedAt) continue; // retention may have pruned it out from under the favorite

    const key = `${fav.user_id}:${fav.item_kind}:${fav.item_id}`;
    const previouslySeen = lastSeen.get(key);
    const changed = previouslySeen && new Date(item.changedAt) > new Date(previouslySeen);

    if (changed) {
      if (!byUser.has(fav.user_id)) byUser.set(fav.user_id, []);
      byUser.get(fav.user_id).push({ title: fav.title || item.title, summaryLine: item.summaryLine, detailLine: item.detailLine });
      seenUpdates.push({
        user_id: fav.user_id, item_kind: fav.item_kind, item_id: fav.item_id,
        last_seen_updated_at: item.changedAt, last_notified_at: new Date().toISOString(),
      });
    } else if (!previouslySeen) {
      // First time this favorite has been checked: record its current state
      // as the baseline. Nothing changed *since favoriting it*, so no email.
      seenUpdates.push({
        user_id: fav.user_id, item_kind: fav.item_kind, item_id: fav.item_id,
        last_seen_updated_at: item.changedAt, last_notified_at: null,
      });
    }
  }

  if (!byUser.size) {
    console.log('No favorited items changed since they were last checked.');
  } else {
    const profiles = await fetchProfiles([...byUser.keys()]);
    let sent = 0;
    let paused = 0;
    for (const [userId, changes] of byUser) {
      const profile = profiles.get(userId);
      if (!profile || !profile.email) continue;
      // Paused users still get their favorite_notifications baseline
      // updated below, so nothing piles up into one email once resumed --
      // this only skips the send itself.
      if (profile.paused) { paused += 1; continue; }
      await sendDigest(profile.email, changes);
      sent += 1;
    }
    console.log(`Sent ${sent} digest email(s) for ${byUser.size} user(s) with changed favorites${paused ? ` (${paused} paused)` : ''}.`);
  }

  if (seenUpdates.length) {
    await supabaseUpsert('favorite_notifications', seenUpdates, 'user_id,item_kind,item_id');
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
