// Reference analytics. No synthetic fallback, forward-filled FX, or executable quotes.
export function dailyAuctions(source, auction = 'all') {
  if (source?.status !== 'observed') return [];
  const groups = new Map();
  for (const r of source.observations ?? []) {
    if (auction !== 'all' && r.auction_name !== auction) continue;
    const price = Number(r.price), volume = Number(r.auction_volume_tco2);
    if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(volume) || volume <= 0) continue;
    const item = groups.get(r.observation_date) ?? { date: r.observation_date, value: 0, volume: 0, count: 0 };
    item.value += price * volume; item.volume += volume; item.count++;
    groups.set(item.date, item);
  }
  return [...groups.values()].sort((a, b) => a.date.localeCompare(b.date)).map(r => ({ ...r, price: r.value / r.volume }));
}

export function windowRows(rows, days) {
  if (!rows.length || days === 'all') return rows;
  const last = Date.parse(rows.at(-1).date + 'T00:00:00Z');
  return rows.filter(r => Date.parse(r.date + 'T00:00:00Z') >= last - (Number(days) - 1) * 86400000);
}

export function auctionStats(rows) {
  if (!rows.length) return null;
  const latest = rows.at(-1), prior = rows.at(-2);
  return { latest, prior, change: prior ? latest.price - prior.price : null,
    changePct: prior ? (latest.price / prior.price - 1) * 100 : null,
    periodChangePct: rows.length > 1 ? (latest.price / rows[0].price - 1) * 100 : null,
    volume: rows.reduce((n, r) => n + r.volume, 0), days: rows.length };
}

export function exactFx(source, observationDate) {
  if (source?.status !== 'observed' || source.unit !== 'KRW/EUR') return null;
  const row = source.observations?.find(r => r.observation_date === observationDate);
  return row && Number.isFinite(Number(row.price)) && Number(row.price) > 0 ? Number(row.price) : null;
}

function nonnegative(v, name, integer = false) {
  if (v === '' || v == null) throw Error(name + ' 입력이 필요합니다');
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > 1e10 || (integer && !Number.isInteger(n))) throw Error(name + ' 범위를 확인하세요');
  return n;
}

export function procurement(input, price, fx) {
  if (!Number.isFinite(price) || price <= 0) throw Error('사용 가능한 관측가격이 없습니다');
  const demand = nonnegative(input.demand, '예상 의무량', true);
  const inventory = nonnegative(input.inventory, '보유량', true);
  const forward = nonnegative(input.forward, '인도예정량', true);
  const pct = nonnegative(input.hedge, '헤지 비율');
  if (pct > 100) throw Error('헤지 비율은 0~100%');
  const shortage = Math.max(0, demand - inventory - forward);
  const lots = Math.floor(shortage * pct / 100 / 1000);
  const unhedged = shortage - lots * 1000;
  return { shortage, lots, unhedged, roundingEua: shortage * pct / 100 - lots * 1000,
    budgetEur: shortage * price, budgetKrw: fx == null ? null : Math.round(shortage * price * fx),
    costUp5Eur: shortage * 5, netCostUp5Eur: unhedged * 5, futuresDown5VmEur: lots * 1000 * 5 };
}

export function dealerRisk(input) {
  const inventory = nonnegative(input.inventory, '자기계정 현물', true);
  const delivery = nonnegative(input.delivery, '고객 고정가격 공급량', true);
  if (input.lots === '' || input.lots == null) throw Error('선물 순매수 lot 입력이 필요합니다');
  const lots = Number(input.lots);
  if (!Number.isSafeInteger(lots) || Math.abs(lots) > 1e7) throw Error('선물 lot은 정수로 입력하세요');
  const delta = inventory + lots * 1000 - delivery;
  return { delta, pnlUp5Eur: delta * 5, futuresDown5CashEur: -lots * 5000 };
}

function parseCsv(text) {
  const rows = []; let row = [], value = '', quoted = false;
  const input = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === '"') {
      if (quoted && input[i + 1] === '"') { value += '"'; i++; } else quoted = !quoted;
    } else if (c === ',' && !quoted) { row.push(value); value = ''; }
    else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && input[i + 1] === '\n') i++;
      row.push(value); if (row.some(v => v.trim())) rows.push(row); row = []; value = '';
    } else value += c;
  }
  if (quoted) throw Error('CSV 따옴표가 닫히지 않았습니다');
  row.push(value); if (row.some(v => v.trim())) rows.push(row);
  return rows;
}

export const curveHeader = 'observation_date,venue,product,expiry_month,settlement_eur,volume_lots,open_interest_lots,price_type,source_url';
export function parseCurve(text, asOf) {
  if (text.length > 64000) throw Error('CSV는 64KB 이하로 제한합니다');
  const [header, ...rows] = parseCsv(text);
  if (!header || header.join(',') !== curveHeader) throw Error('CSV 헤더가 양식과 다릅니다');
  if (!rows.length || rows.length > 100) throw Error('1~100개 월물 행을 입력하세요');
  const seen = new Set(); const snapshots = new Set();
  const data = rows.map((row, i) => {
    if (row.length !== header.length) throw Error(`${i + 2}행 열 수 오류`);
    const r = Object.fromEntries(header.map((key, n) => [key, row[n].trim()]));
    const d = new Date(r.observation_date + 'T00:00:00Z');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.observation_date) || !Number.isFinite(+d) || d.toISOString().slice(0, 10) !== r.observation_date || r.observation_date > asOf) throw Error('미래 또는 잘못된 관측일');
    if (!['EEX', 'ICE Endex'].includes(r.venue) || r.product !== 'EUA' || r.price_type !== 'settlement') throw Error('EUA 결제가격·거래소를 확인하세요');
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(r.expiry_month) || r.expiry_month < r.observation_date.slice(0, 7)) throw Error('월물 범위 오류');
    r.settlement_eur = nonnegative(r.settlement_eur, '결제가격');
    if (!r.settlement_eur) throw Error('결제가격은 양수여야 합니다');
    for (const key of ['volume_lots', 'open_interest_lots']) r[key] = r[key] === '' ? null : nonnegative(r[key], key, true);
    if (!/^https:\/\//.test(r.source_url)) throw Error('공급자 출처 HTTPS URL 필요');
    try { new URL(r.source_url); } catch { throw Error('잘못된 출처 URL'); }
    snapshots.add(r.observation_date + '|' + r.venue);
    if (seen.has(r.expiry_month)) throw Error('중복 월물'); seen.add(r.expiry_month);
    return r;
  });
  if (snapshots.size !== 1) throw Error('동일 관측일·거래소의 곡선만 비교할 수 있습니다');
  return data.sort((a, b) => a.expiry_month.localeCompare(b.expiry_month));
}
