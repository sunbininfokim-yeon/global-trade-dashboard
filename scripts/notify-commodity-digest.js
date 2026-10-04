'use strict';

// Weekly digest for commodity favorites. Runs from a repo checkout (see
// commodity-digest.yml) so it can read the JSON file the Phase 2-2 pipeline
// (New for anti/scripts/commodity_reports) already refreshes every 4 hours --
// no separate fetch/parse of USDA/EIA/etc. feeds here.
//
// Unlike notify-favorites.js (one row per favorited bill, diffed in place),
// a report is a new, immutable item every time one is published. So instead
// of a baseline-then-diff per favorite, this just mails whatever published
// in the last WINDOW_DAYS that hasn't been sent to that user before --
// dedup is an append-only sent-log (commodity_report_notifications), not a
// per-favorite state comparison.
const fs = require('node:fs');
const path = require('node:path');
const {
  requireEnv, supabaseGet, supabaseUpsert, fetchJson,
} = require('./lib/sync-utils');

// DRY_RUN=1: read Supabase and the reports file, print what each favorite
// would receive (counts only -- no addresses), send nothing, record nothing.
// For checking the Supabase wiring without mailing anyone.
const DRY_RUN = process.env.DRY_RUN === '1' || process.env.DRY_RUN === 'true';
requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');
const RESEND_API_KEY = DRY_RUN ? process.env.RESEND_API_KEY : requireEnv('RESEND_API_KEY');
const FROM_EMAIL = process.env.NOTIFY_FROM_EMAIL || 'alerts@chokemonitor.com';
const REPORTS_JSON = path.join(__dirname, '..', 'New for anti', 'public', 'data', 'commodity_reports_v1.json');
const WINDOW_DAYS = 8; // a little over a week, so a cadence slip never silently drops a report
const MAX_PER_COMMODITY = 8; // newest first; keeps one busy board from swamping the mail
const SITE_URL = 'https://chokemonitor.com/';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// When a report became news for the digest. A dated report counts from its
// publication date. A list-page report has no date (ANRPC, VRA, CONAB, USGS)
// and a GAIN page may only have its month; those count from when the
// pipeline first saw them (first_seen_at), and a month-only one must also be
// from the last ~6 weeks so an old report newly linked is not mailed as new.
function newsTime(item) {
  const first = item.first_seen_at ? new Date(item.first_seen_at).getTime() : NaN;
  if (item.published_at && item.published_precision !== 'month') return new Date(item.published_at).getTime();
  if (item.published_at && item.published_precision === 'month') {
    const month = new Date(item.published_at).getTime();
    return Date.now() - month > 45 * 86_400_000 ? NaN : first;
  }
  return first;
}

function loadRecentReports() {
  const data = JSON.parse(fs.readFileSync(REPORTS_JSON, 'utf8'));
  const cutoff = Date.now() - WINDOW_DAYS * 86_400_000;
  const items = (data.items || [])
    .filter((item) => newsTime(item) >= cutoff)
    .sort((a, b) => newsTime(b) - newsTime(a));
  return { items, labels: data.commodity_labels || {} };
}

async function fetchCommodityFavorites() {
  return supabaseGet('user_favorites', { select: 'user_id,item_id', item_kind: 'eq.commodity' });
}

async function fetchSentReportIds() {
  const rows = await supabaseGet('commodity_report_notifications', { select: 'user_id,report_id' });
  return new Set(rows.map((row) => `${row.user_id}:${row.report_id}`));
}

async function fetchDisabledSourcesByUser() {
  // A row is a source the user turned OFF; absence means every source
  // stays on (see 20260904_commodity_digest_source_prefs.sql) -- so a user
  // with no rows here must not be treated as "nothing enabled".
  const rows = await supabaseGet('commodity_digest_source_prefs', { select: 'user_id,source_id' });
  const map = new Map();
  for (const row of rows) {
    if (!map.has(row.user_id)) map.set(row.user_id, new Set());
    map.get(row.user_id).add(row.source_id);
  }
  return map;
}

async function fetchProfiles(userIds) {
  if (!userIds.length) return new Map();
  const rows = await supabaseGet('profiles', { select: 'id,email', id: `in.(${userIds.join(',')})` });
  return new Map(rows.map((row) => [row.id, row.email]));
}

function sendDigestEmail(email, groups) {
  const sections = groups.map(({ label, items }) => `
    <h3 style="margin:20px 0 8px;font-size:15px;">${esc(label)}</h3>
    <ul style="padding-left:20px;margin:0;">
      ${items.map((item) => `
        <li style="margin-bottom:10px;">
          <a href="${esc(item.url)}" style="color:#1c2b33;font-weight:600;">${esc(item.title?.original)}</a><br>
          <span style="color:#4a5a61;font-size:13px;">${esc((item.summary || '').slice(0, 240))}</span>
        </li>`).join('')}
    </ul>`).join('');
  const html = `
    <div style="font-family:-apple-system,sans-serif;max-width:560px;">
      <h2 style="margin:0 0 4px;">이번 주 즐겨찾기 원자재 리포트</h2>
      <p style="color:#4a5a61;margin:0 0 12px;">최근 ${WINDOW_DAYS}일 내 발행되었거나 새로 확인된, 아직 안 보내드린 리포트입니다.</p>
      ${sections}
      <p style="margin-top:24px;"><a href="${SITE_URL}">ChokePoint Monitor에서 전체 보기 →</a></p>
    </div>`;
  return fetchJson('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: email,
      subject: `[ChokePoint Monitor] 주간 원자재 리포트 다이제스트`,
      html,
    }),
  }, { label: 'Resend send' });
}

async function run() {
  const { items, labels } = loadRecentReports();
  if (!items.length) {
    console.log(`No commodity reports published in the last ${WINDOW_DAYS} days.`);
    return;
  }

  const favorites = await fetchCommodityFavorites();
  if (!favorites.length) {
    console.log('No commodity favorites to check.');
    return;
  }

  const favoritesByUser = new Map(); // user_id -> Set(commodity keys)
  for (const fav of favorites) {
    if (!favoritesByUser.has(fav.user_id)) favoritesByUser.set(fav.user_id, new Set());
    favoritesByUser.get(fav.user_id).add(fav.item_id);
  }

  const [sentIds, disabledSourcesByUser] = await Promise.all([
    fetchSentReportIds(),
    fetchDisabledSourcesByUser(),
  ]);
  const digestByUser = new Map(); // user_id -> Map(commodityKey -> [item])
  const sentInserts = [];

  for (const [userId, commodityKeys] of favoritesByUser) {
    const disabledSources = disabledSourcesByUser.get(userId);
    const seenItemIds = new Set(); // an item tagged with 2 favorited commodities lists once
    for (const item of items) {
      if (disabledSources && disabledSources.has(item.source_id)) continue;
      const matchedKey = item.commodities.find((c) => commodityKeys.has(c));
      if (!matchedKey || seenItemIds.has(item.id)) continue;
      if (sentIds.has(`${userId}:${item.id}`)) continue;
      seenItemIds.add(item.id);
      if (!digestByUser.has(userId)) digestByUser.set(userId, new Map());
      const byCommodity = digestByUser.get(userId);
      if (!byCommodity.has(matchedKey)) byCommodity.set(matchedKey, []);
      if (byCommodity.get(matchedKey).length >= MAX_PER_COMMODITY) continue;
      byCommodity.get(matchedKey).push(item);
    }
  }

  if (DRY_RUN) {
    const favCount = {};
    for (const keys of favoritesByUser.values()) for (const k of keys) favCount[k] = (favCount[k] || 0) + 1;
    const recentCount = {};
    for (const item of items) for (const c of item.commodities) recentCount[c] = (recentCount[c] || 0) + 1;
    console.log(`[dry-run] Supabase reachable: ${favorites.length} commodity favorites from ${favoritesByUser.size} user(s).`);
    console.log(`[dry-run] favorites by commodity: ${JSON.stringify(favCount)}`);
    console.log(`[dry-run] reports new in the last ${WINDOW_DAYS} days by commodity: ${JSON.stringify(recentCount)}`);
    console.log(`[dry-run] already-sent log rows: ${sentIds.size}; users with a source turned off: ${disabledSourcesByUser.size}`);
  }

  if (!digestByUser.size) {
    console.log('No new commodity reports for any favorited commodity.');
    return;
  }

  const emails = await fetchProfiles([...digestByUser.keys()]);
  let sent = 0;
  for (const [userId, byCommodity] of digestByUser) {
    const email = emails.get(userId);
    // No address, no mail -- and no sent-log row, so the report is still
    // mailed if the address turns up within the window.
    if (!email) continue;
    const groups = [...byCommodity.entries()].map(([key, groupItems]) => ({
      label: labels[key] || key,
      items: groupItems,
    }));
    if (DRY_RUN) {
      const summary = groups.map((g) => `${g.label} ${g.items.length}`).join(', ');
      console.log(`[dry-run] user ${userId.slice(0, 8)}… would get: ${summary}`);
      continue;
    }
    await sendDigestEmail(email, groups);
    for (const groupItems of byCommodity.values()) {
      for (const item of groupItems) sentInserts.push({ user_id: userId, report_id: item.id });
    }
    sent += 1;
  }
  if (DRY_RUN) {
    console.log('[dry-run] nothing sent, nothing recorded.');
    return;
  }
  console.log(`Sent ${sent} weekly commodity digest(s).`);

  if (sentInserts.length) {
    // ignore-duplicates, not merge: a retry after a partial failure must not
    // error on rows a prior attempt already recorded.
    await supabaseUpsert('commodity_report_notifications', sentInserts, 'user_id,report_id', 'resolution=ignore-duplicates,return=minimal');
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
