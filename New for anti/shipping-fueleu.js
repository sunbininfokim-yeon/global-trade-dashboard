// 해운 › FuelEU 풀링: rules, pool-price history, MRV supply structure, ship check.
//
// Data: /public/data/fueleu_market_v1.json, built by tools/fueleu/build_site_data.py.
// The ship check, biofuel blend and voyage calculators run in the browser on a
// port of tools/fueleu/engine.py, held to the Python output by
// tests/fueleu/engine.test.mjs.
//
// The OPX series and the MRV estimate are shown for a limited time chosen by
// the user (redistribution terms unconfirmed). After data.display_until the tab
// keeps the regulation-only parts and drops both.
(() => {
  // ------------------------------------------------------------------ engine
  // Line-for-line port of tools/fueleu/engine.py. Change both together.

  const REFERENCE = 91.16;
  const REDUCTIONS = [[2025, 2], [2030, 6], [2035, 14.5], [2040, 31], [2045, 62], [2050, 80]];
  const GWP = { CH4: 25, N2O: 298 };
  const SCOPE_SHARE = { at_berth: 1, intra_eu: 1, extra_eu: 0.5 };
  const RFNBO_REWARD_UNTIL = 2033;
  const FUELS = {
    hfo: { label: 'HFO', lcv: 0.0405, wtt: 13.5, cf_co2: 3.114, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    lfo: { label: 'LFO', lcv: 0.041, wtt: 13.2, cf_co2: 3.151, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    mdo_mgo: { label: 'MDO/MGO', lcv: 0.0427, wtt: 14.4, cf_co2: 3.206, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    lng_otto_ms: { label: 'LNG 오토 중속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 3.1 },
    lng_otto_ss: { label: 'LNG 오토 저속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 1.7 },
    lng_diesel_ss: { label: 'LNG 디젤 저속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 0.2 },
    lng_lbsi: { label: 'LNG LBSI', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 2.6 }
  };
  const EU27 = new Set(['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT',
    'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE']);
  const UCO_FAME_E = { default: 14.9, typical: 11.2 };

  const target = year => {
    const step = [...REDUCTIONS].reverse().find(([start]) => year >= start);
    if (!step) throw new Error('FuelEU는 2025 보고연도부터 적용됩니다');
    return REFERENCE * (1 - step[1] / 100);
  };

  const fuelFactors = fuel => {
    if (typeof fuel === 'string') {
      if (!FUELS[fuel]) throw new Error(`알 수 없는 연료: ${fuel}`);
      return FUELS[fuel];
    }
    return fuel;
  };

  const bioFuel = (eValue = UCO_FAME_E.default, certified = true, lcv = 0.037, cfCo2 = 2.834) => certified
    ? { label: `UCO 바이오디젤 (E ${eValue})`, lcv, wtt: eValue - cfCo2 / lcv, cf_co2: cfCo2, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 }
    : { ...FUELS.hfo, label: '인증 없는 바이오연료 (최악 화석 계수)' };

  const intensity = (rows, year = 2025) => {
    let wtt = 0, ttw = 0, denom = 0, energy = 0;
    rows.forEach(row => {
      const f = fuelFactors(row.fuel);
      const share = row.share ?? SCOPE_SHARE[row.scope];
      if (share === undefined) throw new Error('적용 범위를 확인하세요');
      if (!(row.tonnes >= 0)) throw new Error('연료량은 0 이상이어야 합니다');
      const grams = row.tonnes * 1e6 * share;
      const mj = grams * f.lcv;
      const rwd = f.rfnbo && year <= RFNBO_REWARD_UNTIL ? 2 : 1;
      const slip = f.slip / 100;
      wtt += grams * f.wtt * f.lcv;
      ttw += grams * ((1 - slip) * (f.cf_co2 + f.cf_ch4 * GWP.CH4 + f.cf_n2o * GWP.N2O) + slip * GWP.CH4);
      denom += mj * rwd;
      energy += mj;
    });
    if (denom <= 0) throw new Error('EU 관련 연료 사용량을 입력하세요');
    return { ghg_intensity: (wtt + ttw) / denom, energy_mj: energy };
  };

  const penaltyEur = (cbG, actual, n = 1) => cbG >= 0 ? 0 : Math.abs(cbG) / (actual * 41000) * 2400 * (1 + (Math.max(1, n) - 1) / 10);

  const ship = (rows, year, consecutiveDeficits = 0, borrowedLastPeriod = false) => {
    const i = intensity(rows, year), tgt = target(year), cbG = (tgt - i.ghg_intensity) * i.energy_mj, n = consecutiveDeficits + 1;
    return { ...i, year, target: tgt, compliance_balance_tco2e: cbG / 1e6, penalty_eur: penaltyEur(cbG, i.ghg_intensity, n),
      penalty_eur_per_tco2e: penaltyEur(-1e6, i.ghg_intensity, n), consecutive_multiplier: 1 + (n - 1) / 10,
      borrow_limit_tco2e: borrowedLastPeriod ? 0 : 0.02 * tgt * i.energy_mj / 1e6 };
  };

  const quickCheck = (grossTonnage, fuels, share = { extra_eu: 1 }, year = 2025) => {
    if (grossTonnage !== null && grossTonnage <= 5000) return { in_scope: false };
    if (Math.abs(Object.values(share).reduce((a, b) => a + b, 0) - 1) > 1e-6) throw new Error('항해 비중의 합은 100%여야 합니다');
    const rows = Object.entries(fuels).flatMap(([fuel, t]) => Object.entries(share).filter(([, v]) => v).map(([scope, v]) => ({ fuel, tonnes: t * v, scope })));
    const now = ship(rows, year);
    const timeline = REDUCTIONS.map(([start]) => {
      const r = ship(rows, Math.max(start, year));
      return { from_year: start, target: r.target, compliance_balance_tco2e: r.compliance_balance_tco2e,
        position: r.compliance_balance_tco2e >= 0 ? 'surplus' : 'deficit', penalty_eur: r.penalty_eur };
    });
    return { in_scope: true, ghg_intensity: now.ghg_intensity, target: now.target, energy_mj: now.energy_mj,
      compliance_balance_tco2e: now.compliance_balance_tco2e, penalty_eur: now.penalty_eur,
      position: now.compliance_balance_tco2e >= 0 ? 'surplus' : 'deficit', margin_gco2e_per_mj: now.target - now.ghg_intensity,
      first_deficit_period: timeline.find(t => t.position === 'deficit')?.from_year ?? null, timeline };
  };

  const blendEconomics = (base, bioMassShare, tonnes, { year = 2025, share = { extra_eu: 1 }, poolPrice = null, premium = null, eValue = UCO_FAME_E.default, certified = true } = {}) => {
    if (!(bioMassShare >= 0 && bioMassShare <= 1)) throw new Error('바이오 비중은 0~100%입니다');
    const bio = bioFuel(eValue, certified);
    const run = s => ship([
      ...(s < 1 ? Object.entries(share).filter(([, f]) => f).map(([k, f]) => ({ fuel: base, tonnes: tonnes * (1 - s) * f, scope: k })) : []),
      ...(s > 0 ? Object.entries(share).filter(([, f]) => f).map(([k, f]) => ({ fuel: bio, tonnes: tonnes * s * f, scope: k })) : [])
    ], year);
    const without = run(0), withBlend = run(bioMassShare), pure = run(1);
    const span = pure.compliance_balance_tco2e - without.compliance_balance_tco2e;
    const gain = span / tonnes;
    const pick = r => ({ ghg_intensity: r.ghg_intensity, compliance_balance_tco2e: r.compliance_balance_tco2e, penalty_eur: r.penalty_eur });
    const out = { bio_fuel: bio.label, certified, e_value: eValue, bio_tonnes: tonnes * bioMassShare,
      without: pick(without), with_blend: pick(withBlend), pure_bio_intensity: pure.ghg_intensity,
      surplus_per_t_bio_tco2e: gain, bio_share_for_zero_balance: span <= 0 ? null : Math.max(0, -without.compliance_balance_tco2e / span),
      curve: Array.from({ length: 11 }, (_, i) => { const r = run(i / 10); return { bio_pct: i * 10, compliance_balance_tco2e: r.compliance_balance_tco2e, ghg_intensity: r.ghg_intensity }; }) };
    if (poolPrice !== null) out.breakeven_premium_eur_per_t = gain * poolPrice;
    if (premium !== null && gain > 0) out.cost_per_tco2e_of_blending = premium / gain;
    return out;
  };

  const portInScope = (port, extra = []) => EU27.has((port.country || '').toUpperCase()) || extra.includes((port.country || '').toUpperCase());

  const legShare = (o, d, extra = []) => {
    const a = portInScope(o, extra), b = portInScope(d, extra);
    if (!a && !b) return [0, 'out_of_scope'];
    if (a && b) return o.outermost || d.outermost ? [0.5, 'outermost_region'] : [1, 'intra_eu'];
    return [0.5, 'extra_eu'];
  };

  const legsToConsumption = (legs, extra = []) => legs.flatMap(leg => {
    const [share, basis] = legShare(leg.origin, leg.destination, extra);
    const rows = share ? Object.entries(leg.at_sea || {}).map(([fuel, t]) => ({ fuel, tonnes: t, share, scope: basis, leg: leg.id })) : [];
    if (portInScope(leg.destination, extra)) Object.entries(leg.at_berth || {}).forEach(([fuel, t]) => rows.push({ fuel, tonnes: t, share: 1, scope: 'at_berth', leg: leg.id }));
    return rows;
  });

  const shipYear = (legs, year, poolPrice = null, { consecutiveDeficits = 0, borrowedLastPeriod = false, extra = [] } = {}) => {
    const run = ls => ship(legsToConsumption(ls, extra), year, consecutiveDeficits, borrowedLastPeriod);
    const actual = legs.filter(l => (l.status || 'actual') === 'actual');
    const full = run(legs);
    const perLeg = legs.map(leg => {
      const [share, basis] = legShare(leg.origin, leg.destination, extra);
      const rest = legs.filter(l => l !== leg);
      const without = legsToConsumption(rest, extra).length ? run(rest).compliance_balance_tco2e : 0;
      const delta = full.compliance_balance_tco2e - without;
      return { id: leg.id, status: leg.status || 'actual', share, scope_basis: basis, cb_delta_tco2e: delta,
        cost_at_pool_eur: poolPrice === null ? null : Math.max(0, -delta) * poolPrice,
        value_at_pool_eur: poolPrice === null ? null : Math.max(0, delta) * poolPrice };
    });
    return { full_year: full, actual_to_date: actual.length && legsToConsumption(actual, extra).length ? run(actual) : null, legs: perLeg };
  };

  const options = (result, poolPrice, nextPoolPrice = null) => {
    const cb = result.compliance_balance_tco2e;
    if (cb < 0) {
      const deficit = -cb, borrow = Math.min(deficit, result.borrow_limit_tco2e), rest = deficit - borrow;
      const rows = [
        { option: 'pool_buy', label: '풀에서 잉여분 매입', cost_eur: deficit * poolPrice },
        { option: 'penalty', label: '부담금 납부', cost_eur: result.penalty_eur },
        { option: 'borrow_then_pool', label: `차입 ${Math.round(borrow).toLocaleString('ko-KR')} t + 나머지 풀 매입`,
          cost_eur: nextPoolPrice === null ? null : 1.1 * borrow * nextPoolPrice + rest * poolPrice,
          note: '차입분은 다음 기간에 1.1배를 갚는다. 다음 기간 풀 가격 가정이 필요하다.' }
      ];
      const best = rows.filter(r => r.cost_eur !== null).reduce((a, b) => (b.cost_eur < a.cost_eur ? b : a));
      return { position: 'deficit', tco2e: deficit, rows, cheapest: best.option, breakeven_pool_price: result.penalty_eur_per_tco2e, borrow_beats_pool_if_next_below: poolPrice / 1.1 };
    }
    const rows = [
      { option: 'pool_sell', label: '풀에 잉여분 판매', value_eur: cb * poolPrice },
      { option: 'bank', label: '다음 기간으로 이월', value_eur: nextPoolPrice === null ? null : cb * nextPoolPrice, note: '이월분 가치는 다음 기간 가격 가정에 달려 있다. 이월은 문서 발급 전에만 가능하다.' }
    ];
    const best = rows.filter(r => r.value_eur !== null).reduce((a, b) => (b.value_eur > a.value_eur ? b : a));
    return { position: 'surplus', tco2e: cb, rows, best: best.option, bank_beats_sale_if_next_above: poolPrice };
  };

  const poolValid = (before, after) => {
    const problems = [], sum = o => Object.values(o).reduce((a, b) => a + b, 0);
    if (sum(before) <= 0) problems.push('풀 합계가 양수가 아님');
    if (Math.abs(sum(after) - sum(before)) > 1e-6) problems.push('배분이 풀 합계를 바꿈');
    Object.entries(before).forEach(([k, cb]) => {
      if (cb < 0 && after[k] < cb) problems.push(`${k}: 부족 선박의 부족이 커짐`);
      if (cb >= 0 && after[k] < 0) problems.push(`${k}: 잉여 선박이 부족으로 바뀜`);
    });
    return { valid: !problems.length, problems };
  };

  const fleetPool = ships => {
    const total = Object.values(ships).reduce((a, b) => a + b, 0);
    const surplus = Object.entries(ships).filter(([, v]) => v > 0), deficit = Object.entries(ships).filter(([, v]) => v < 0);
    const need = -deficit.reduce((a, [, v]) => a + v, 0), have = surplus.reduce((a, [, v]) => a + v, 0);
    const after = { ...ships };
    let check;
    if (total > 0) {
      deficit.forEach(([k]) => { after[k] = 0; });
      let left = need;
      surplus.sort((a, b) => b[1] - a[1]).forEach(([k, v]) => { const take = Math.min(v, left); after[k] = v - take; left -= take; });
      check = poolValid(ships, after);
    } else check = { valid: false, problems: ['선대 합계가 양수가 아님: 외부 매입 또는 부담금'] };
    return { total_tco2e: total, internal_netting_tco2e: Math.min(need, have), external_need_tco2e: Math.max(0, -total),
      external_surplus_tco2e: Math.max(0, total), allocation: total > 0 ? after : { ...ships }, check };
  };

  const engine = { target, intensity, ship, quickCheck, bioFuel, blendEconomics, legShare, legsToConsumption, shipYear, options, fleetPool, poolValid, FUELS };
  if (typeof module !== 'undefined' && module.exports) module.exports = engine;
  if (typeof window === 'undefined') return;

  // ---------------------------------------------------------------------- UI

  const DATA_URL = '/public/data/fueleu_market_v1.json';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 0) => v === null || v === undefined ? '미확인' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: d });
  const eur = (v, d = 0) => v === null || v === undefined ? '미확인' : `€${fmt(v, d)}`;
  const kt = v => `${fmt(v / 1000, 0)}천 t`;
  const kpi = (label, value, note = '', featured = false) => `<div class="shipping-kpi${featured ? ' featured' : ''}"><span class="shipping-kpi-label">${esc(label)}</span><strong>${value}</strong><small>${esc(note)}</small></div>`;
  const panel = (kicker, title, body, extra = '') => `<section class="shipping-panel"><div class="shipping-panel-heading"><div><p class="shipping-panel-kicker">${esc(kicker)}</p><h2>${esc(title)}</h2></div>${extra}</div>${body}</section>`;
  const note = html => `<p class="sc-note">${html}</p>`;
  const table = (heads, rows, cls = '') => `<div class="shipping-table-wrap"><table class="shipping-table compact-table ${cls}"><thead><tr>${heads.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;

  const SHORT = { hfo: 'HFO', lfo: 'LFO', mdo_mgo: 'MGO', lng_otto_ms: 'LNG 오토 중속', lng_lbsi: 'LNG LBSI', lng_otto_ss: 'LNG 오토 저속', lng_diesel_ss: 'LNG 디젤 저속' };
  const FUEL_COLOR = { hfo: '#f97316', lfo: '#fb923c', mdo_mgo: '#fbbf24', lng_otto_ms: '#7dd3fc', lng_lbsi: '#38bdf8', lng_otto_ss: '#0ea5e9', lng_diesel_ss: '#0369a1' };
  const TYPE_KO = { 'Container ship': '컨테이너선', 'Bulk carrier': '벌크선', 'Oil tanker': '유조선', 'Chemical tanker': '케미컬 탱커', 'General cargo ship': '일반화물선',
    'LNG carrier': 'LNG 운반선', 'Gas carrier': '가스 운반선', 'Vehicle carrier': '자동차 운반선', 'Ro-pax ship': '로팩스', 'Ro-ro ship': '로로선', 'Passenger ship': '여객선',
    'Passenger ship (Cruise Passenger ship)': '크루즈선', 'Container/ro-ro cargo ship': '컨테이너·로로선', 'Refrigerated cargo carrier': '냉동선', 'Combination carrier': '겸용선',
    'Other ship types': '기타', 'Other ship types (Offshore)': '기타(해양작업)', 'Combined gas/LNG carrier': '가스·LNG 겸용' };

  function rulesChart(r) {
    const W = 900, H = 340, L = 46, R = 160, T = 18, B = 30, y0 = 2025, y1 = 2052, lo = 10, hi = 95;
    const x = y => L + (W - L - R) * (y - y0) / (y1 - y0);
    const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    const steps = r.periods.map((p, i) => ({ ...p, to: r.periods[i + 1]?.from_year ?? y1 }));
    const stair = steps.map(p => `${x(p.from_year)},${y(p.target)} ${x(p.to)},${y(p.target)}`).join(' ');
    const grid = [20, 40, 60, 80].map(v => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(148,163,184,.1)"/><text x="${L - 8}" y="${y(v) + 4}" font-size="11" fill="#64748b" text-anchor="end">${v}</text>`).join('');
    const xt = steps.map(p => `<text x="${x(p.from_year)}" y="${H - 8}" font-size="11" fill="#64748b" text-anchor="middle">${p.from_year}</text><text x="${(x(p.from_year) + x(p.to)) / 2}" y="${y(p.target) + 15}" font-size="10.5" fill="#94a3b8" text-anchor="middle">${fmt(p.target, 1)}</text>`).join('');
    const lab = r.fuels.map(f => ({ f, ly: y(f.intensity) }));
    lab.forEach((l, i) => { if (i && l.ly - lab[i - 1].ly < 14) l.ly = lab[i - 1].ly + 14; });
    const lines = lab.map(({ f, ly }) => {
      const c = FUEL_COLOR[f.key] || '#a3a3a3', fy = y(f.intensity);
      return `<line x1="${L}" x2="${W - R}" y1="${fy}" y2="${fy}" stroke="${c}" stroke-width="2" stroke-dasharray="${f.key.startsWith('lng') ? '0' : '6 4'}"/>
        ${f.first_deficit_period ? `<circle cx="${x(f.first_deficit_period)}" cy="${fy}" r="4.5" fill="${c}"><title>${esc(SHORT[f.key])}: ${f.first_deficit_period}년부터 부족</title></circle>` : ''}
        <path d="M${W - R} ${fy} L${W - R + 10} ${ly}" stroke="${c}" fill="none"/><text x="${W - R + 14}" y="${ly + 4}" font-size="11.5" fill="${c}">${esc(SHORT[f.key] || f.key)} ${fmt(f.intensity, 1)} → ${f.first_deficit_period ?? '–'}</text>`;
    }).join('');
    return `<svg class="fe-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="FuelEU 한도 계단과 연료별 집약도">
      <polygon points="${x(y0)},${y(hi)} ${stair} ${x(y1)},${y(hi)}" fill="rgba(239,68,68,.07)"/>
      <text x="${x(2045)}" y="${y(72)}" font-size="13" fill="rgba(252,165,165,.75)" text-anchor="middle">한도보다 높음 = 부족</text>
      <text x="${x(2026.5)}" y="${y(40)}" font-size="13" fill="rgba(134,239,172,.65)">한도보다 낮음 = 잉여</text>
      ${grid}<polyline points="${stair}" fill="none" stroke="#e2e8f0" stroke-width="2.5"/>${xt}${lines}
      <text x="${L}" y="${T}" font-size="11" fill="#64748b">gCO₂e/MJ</text></svg>`;
  }

  function priceChart(series) {
    const COLORS = { 2025: '#94a3b8', 2026: '#38bdf8', 2027: '#a78bfa' };
    const pts = Object.entries(series).flatMap(([cy, s]) => s.map(p => ({ ...p, cy })));
    const months = [...new Set(pts.map(p => p.month))].sort();
    const [fy, fm] = months[0].split('-').map(Number);
    const idx = m => { const [yy, mm] = m.split('-').map(Number); return (yy - fy) * 12 + (mm - fm); };
    const span = Math.max(1, idx(months.at(-1)));
    const vals = pts.flatMap(p => [p.value_eur_per_tco2e, p.offer_low_eur, p.offer_high_eur]).filter(v => v != null);
    const lo = Math.floor(Math.min(...vals) / 25) * 25, hi = Math.ceil(Math.max(...vals) / 25) * 25;
    const W = 900, H = 300, L = 52, R = 20, T = 34, B = 30;
    const x = m => L + (W - L - R) * idx(m) / span;
    const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    const grid = [];
    for (let v = lo; v <= hi; v += 25) grid.push(`<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(148,163,184,.1)"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#64748b">€${v}</text>`);
    for (let i = 0; i <= span; i += 2) {
      const d = new Date(Date.UTC(fy, fm - 1 + i, 1));
      grid.push(`<text x="${L + (W - L - R) * i / span}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#64748b">${String(d.getUTCFullYear()).slice(2)}.${String(d.getUTCMonth() + 1).padStart(2, '0')}</text>`);
    }
    const body = Object.entries(series).map(([cy, s]) => {
      const c = COLORS[cy] || '#f59e0b';
      const band = s.filter(p => p.offer_low_eur != null).map(p => `<line x1="${x(p.month)}" x2="${x(p.month)}" y1="${y(p.offer_low_eur)}" y2="${y(p.offer_high_eur)}" stroke="${c}" stroke-opacity=".28" stroke-width="10" stroke-linecap="round"><title>${esc(p.month)} 호가 €${p.offer_low_eur}–€${p.offer_high_eur}</title></line>`).join('');
      const segs = [[]];
      s.forEach((p, i) => { if (i && idx(p.month) - idx(s[i - 1].month) > 1) segs.push([]); segs.at(-1).push(p); });
      const line = segs.filter(g => g.length > 1).map(g => `<polyline fill="none" stroke="${c}" stroke-width="2.5" points="${g.map(p => `${x(p.month)},${y(p.value_eur_per_tco2e)}`).join(' ')}"/>`).join('');
      const dots = s.map(p => `<circle cx="${x(p.month)}" cy="${y(p.value_eur_per_tco2e)}" r="4" fill="${p.basis === 'monthly_commentary' ? c : '#0b1220'}" stroke="${c}" stroke-width="2"><title>${esc(p.month)} ${cy}년분 €${p.value_eur_per_tco2e}</title></circle>`).join('');
      return band + line + dots;
    }).join('');
    const legend = Object.keys(series).map((cy, i) => `<g transform="translate(${L + i * 150},8)"><rect width="14" height="3" y="5" fill="${COLORS[cy] || '#f59e0b'}"/><text x="20" y="10" font-size="12" fill="#cbd5e1">${cy}년분 잉여</text></g>`).join('');
    return `<svg class="fe-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="FuelEU 풀 가격 월별 추이">${grid.join('')}${body}${legend}</svg>`;
  }

  function supplyBlock(data, year, tgtYear) {
    const d = data[year], prev = data[String(Number(year) - 1)];
    const t = d.total, wb = d.total_with_bio_assumption, lng = d.by_propulsion.lng || {}, oil = d.by_propulsion.oil || {}, bio = d.by_propulsion.bio_blend;
    const PROP = { lng: 'LNG 추진선', oil: '석유 연료선', bio_blend: '바이오 혼합 (UCO 가정)' };
    const sf = d.size_filter && Object.keys(d.size_filter.dropped || {}).length ? d.size_filter : null;
    const types = Object.entries(d.by_ship_type).filter(([, v]) => v.ships >= 20).slice(0, 12);
    const max = Math.max(1, ...types.map(([, v]) => Math.max(v[`surplus_${tgtYear}`], v[`deficit_${tgtYear}`])));
    const rows = types.map(([k, v]) => `<tr><td>${esc(TYPE_KO[k] || k)}</td><td>${fmt(v.ships)}</td>
      <td class="fe-bar-cell fe-left"><span class="fe-bar fe-def" style="width:${v[`deficit_${tgtYear}`] / max * 100}%"></span></td>
      <td class="fe-bar-cell"><span class="fe-bar fe-sur" style="width:${v[`surplus_${tgtYear}`] / max * 100}%"></span></td>
      <td>${kt(-v[`deficit_${tgtYear}`])}</td><td>${kt(v[`surplus_${tgtYear}`])}</td></tr>`);
    const lngPrev = prev?.by_propulsion?.lng;
    return `
      <div class="shipping-kpi-grid">
        ${kpi(`LNG 추진선 (${year})`, `${fmt(lng.ships)}척`, lngPrev ? `${Number(year) - 1}년 ${fmt(lngPrev.ships)}척에서 ${fmt((lng.ships / lngPrev.ships - 1) * 100)}% 증가` : '', true)}
        ${kpi(`잉여 추정 (${tgtYear} 한도)`, kt(t[`surplus_${tgtYear}`]), `${fmt(t[`surplus_ships_${tgtYear}`])}척이 한도보다 깨끗함`)}
        ${kpi(`부족 추정 (${tgtYear} 한도)`, kt(t[`deficit_${tgtYear}`]), `석유선 평균 ${fmt(oil.avg_intensity, 2)} gCO₂e/MJ`)}
        ${kpi('장부상 순수급', kt(t[`net_${tgtYear}`]), wb ? `바이오 혼합 ${fmt(bio?.ships || 0)}척 가정 포함 시 ${kt(wb[`net_${tgtYear}`])}` : '잉여 − 부족')}
      </div>
      <div class="sc-sources fe-insight"><strong>읽는 법</strong><span>석유선의 구조적 부족이 LNG선 잉여보다 큽니다. 그런데도 시장 해설은 "공급이 수요를 넘는다"고 하고 가격은 내려갑니다. 차이는 바이오연료 혼합으로 필요할 때 만드는 잉여가 메웁니다. 그래서 풀 가격은 LNG 잉여량보다 바이오 혼합 비용에 끌려갑니다. 2030년 한도(−6%)가 오면 부족이 약 ${fmt(t.deficit_2030 / t.deficit_2025, 1)}배로 커집니다.</span></div>
      <div class="fe-legend"><span><i class="fe-def"></i>부족 (풀에서 사야 하는 양)</span><span><i class="fe-sur"></i>잉여 (풀에 팔 수 있는 양)</span></div>
      ${table(['선종', '척수', '부족', '잉여', '부족 t', '잉여 t'], rows, 'fe-supply')}
      <div class="shipping-grid sc-two">
        ${panel('BY PROPULSION', '추진 연료별', table(['구분', '척수', '평균 집약도', '2025 한도 순', '2030 한도 순'], [
          ...Object.entries(d.by_propulsion).map(([k, v]) => `<tr><td>${PROP[k] || k}</td><td>${fmt(v.ships)}</td><td>${fmt(v.avg_intensity, 2)}</td><td>${kt(v.net_2025)}</td><td>${kt(v.net_2030)}</td></tr>`),
          `<tr><td>메탄올·기타</td><td>${fmt(d.unestimated.other || 0)}</td><td colspan="3">계산 제외</td></tr>`]) +
          note('바이오 혼합 선박은 MRV의 CO₂/연료 비율로 혼합률을 추정하고, 바이오 부분을 RED II 기본값의 폐식용유(UCO) 바이오디젤로 가정해 계산했습니다. 그래서 위 상단 숫자(석유·LNG만)와 따로 둡니다.'))}
        ${panel('LIMITS', '이 추정의 한계', `<ul class="sc-note fe-list">
          <li>공식 FuelEU 잔액이 아닙니다. FuelEU 데이터베이스는 비공개입니다.</li>
          <li>${sf ? `MRV에 총톤수가 없어 대리 기준을 썼습니다: 해양작업선 ${fmt(sf.dropped['Other ship types (Offshore)'] || 0)}척은 화물·여객선이 아니라 제외, 일반화물선은 2024년 척수(${fmt(sf.baseline_counts['General cargo ship'])})만큼 시간당 연료가 큰 순으로 남기고 ${fmt(sf.dropped['General cargo ship'] || 0)}척 제외.` : '2024년 MRV는 5,000 GT 초과 선박만 담고 있습니다.'}</li>
          <li>바이오 혼합은 실제 원료·인증값을 모릅니다. UCO 기본값 가정이라 실제와 다를 수 있습니다.</li>
          <li>최외곽지역 항해(50%)가 EU 역내(100%)에 섞여 있고, 풍력·육상전원 보정과 기존 풀링은 반영하지 않았습니다.</li>
          <li>${year === '2024' ? '2024년은 FuelEU 시행 전이라 구조 비교용입니다.' : `연료량·배출이 없는 보고서 ${fmt(d.skipped)}건은 뺐습니다.`}</li></ul>`)}
      </div>`;
  }

  function quickPanel() {
    const opts = sel => Object.entries(FUELS).map(([k, f]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${esc(f.label)}</option>`).join('');
    return panel('SHIP CHECK', '이 선박은 잉여 선박인가, 부족 선박인가', `
      ${note('FuelEU 한도는 선종·크기와 상관없이 모든 선박에 같은 gCO₂e/MJ입니다. 크기는 적용 대상인지(5,000 GT 초과)와 잔액 규모만 바꾸고, 잉여냐 부족이냐는 연료 구성이 정합니다.')}
      <form class="sc-form fe-quick" novalidate>
        <label class="sc-field"><span>총톤수 (GT)</span><input name="gt" type="number" min="0" value="95000"></label>
        <label class="sc-field"><span>주 연료</span><select name="f1">${opts('lng_otto_ss')}</select></label>
        <label class="sc-field"><span>연간 t (EU 관련 항해)</span><input name="t1" type="number" min="0" value="12000"></label>
        <label class="sc-field"><span>보조 연료</span><select name="f2"><option value="">없음</option>${opts('mdo_mgo')}</select></label>
        <label class="sc-field"><span>연간 t</span><input name="t2" type="number" min="0" value="600"></label>
        <label class="sc-field"><span>EU↔EU 항해 %</span><input name="intra" type="number" min="0" max="100" value="10"></label>
        <label class="sc-field"><span>EU 항구 정박 %</span><input name="berth" type="number" min="0" max="100" value="5"></label>
      </form>
      <div class="fe-quick-out"></div>
      ${note('나머지 비중은 EU↔역외 항해(50% 반영)로 봅니다. LNG는 엔진 종류(메탄 슬립)에 따라 결과가 크게 달라집니다. 바이오·e-연료는 인증 배출계수가 필요해 여기서는 뺐습니다.')}`);
  }

  function runQuick(root, pool) {
    const f = root.querySelector('.fe-quick'), out = root.querySelector('.fe-quick-out');
    const v = n => f.elements[n].value;
    try {
      const intra = Number(v('intra')) / 100, berth = Number(v('berth')) / 100;
      if (intra + berth > 1) throw new Error('EU↔EU 항해와 정박 비중의 합은 100%를 넘을 수 없습니다');
      const share = { intra_eu: intra, at_berth: berth, extra_eu: 1 - intra - berth };
      const fuels = { [v('f1')]: Number(v('t1')) };
      if (v('f2') && v('t2') !== '') fuels[v('f2')] = (fuels[v('f2')] || 0) + Number(v('t2'));
      const r = quickCheck(v('gt') === '' ? null : Number(v('gt')), fuels, share);
      if (!r.in_scope) { out.innerHTML = note('FuelEU는 5,000 GT 초과 여객·화물선에만 적용됩니다 (제2조(1)).'); return; }
      const surplus = r.position === 'surplus';
      out.innerHTML = `<div class="shipping-kpi-grid">
          ${kpi('판정 (2025–2029)', surplus ? '잉여 선박' : '부족 선박', surplus ? '풀에 팔 수 있는 쪽' : '풀에서 사야 하는 쪽', true)}
          ${kpi('집약도 / 한도', `${fmt(r.ghg_intensity, 2)} / ${fmt(r.target, 2)}`, `여유 ${fmt(r.margin_gco2e_per_mj, 2)} gCO₂e/MJ`)}
          ${kpi('연간 준수 잔액', `${fmt(r.compliance_balance_tco2e)} tCO₂e`, pool ? `현재 풀 가격 기준 ${eur(Math.abs(r.compliance_balance_tco2e) * pool)}` : '')}
          ${kpi('부족으로 바뀌는 시점', r.first_deficit_period ? `${r.first_deficit_period}년` : '2050년까지 없음', '같은 연료·운항 유지 시')}
        </div>${table(['적용 기간', '한도', '잔액 (tCO₂e)', '판정', '미조치 시 부담금'], r.timeline.map(t =>
          `<tr><td>${t.from_year}~</td><td>${fmt(t.target, 2)}</td><td>${fmt(t.compliance_balance_tco2e)}</td><td>${t.position === 'surplus' ? '잉여' : '부족'}</td><td>${t.penalty_eur ? eur(t.penalty_eur) : '—'}</td></tr>`))}`;
    } catch (error) {
      out.innerHTML = `<div class="sc-error">${esc(error.message)}</div>`;
    }
  }

  // -------------------------------------------------------------- blend calculator

  function blendPanel() {
    const base = ['hfo', 'lfo', 'mdo_mgo'].map(k => `<option value="${k}"${k === 'lfo' ? ' selected' : ''}>${FUELS[k].label}</option>`).join('');
    return panel('BIOFUEL BLEND', '바이오 혼합 계산기: 몇 % 섞으면 되고, 웃돈이 얼마 이하면 풀보다 싼가', `
      <form class="sc-form fe-quick fe-blend" novalidate>
        <label class="sc-field"><span>기본 연료</span><select name="base">${base}</select></label>
        <label class="sc-field"><span>바이오 비중 % (B30 = 30)</span><input name="pct" type="number" min="0" max="100" step="1" value="30"></label>
        <label class="sc-field"><span>연간 t (EU 관련 항해)</span><input name="t" type="number" min="0" value="10000"></label>
        <label class="sc-field"><span>EU↔EU 항해 %</span><input name="intra" type="number" min="0" max="100" value="20"></label>
        <label class="sc-field"><span>바이오 배출값 E</span><select name="e"><option value="14.9">UCO 기본값 14.9</option><option value="11.2">UCO 대표값 11.2</option><option value="custom">직접 입력</option><option value="none">인증 없음 (식량작물 등)</option></select></label>
        <label class="sc-field"><span>직접 입력 E (gCO₂e/MJ)</span><input name="ecustom" type="number" min="0" step="0.1" placeholder="인증서 값"></label>
        <label class="sc-field"><span>바이오 웃돈 €/t (선택)</span><input name="prem" type="number" min="0" step="1" placeholder="화석 대비"></label>
      </form>
      <div class="fe-blend-out"></div>
      ${note('UCO 값은 RED II 부속서 V(폐식용유 바이오디젤 대표 11.2·기본 14.9 gCO₂e/MJ)와 부속서 III(FAME 37 MJ/kg), FuelEU 부속서 II(CO₂ 2.834 g/g)에서 가져왔습니다. 바이오 WtT = E − 2.834 ÷ 0.037이라 배 위에서 태운 생물기원 CO₂가 상쇄됩니다. 실제 계산은 벙커 인도증의 인증값을 써야 합니다. 바이오 웃돈 시세는 무료 공개 자료가 없어 입력값으로 둡니다.')}`);
  }

  function blendChart(curve, current) {
    const W = 900, H = 200, L = 60, R = 16, T = 14, B = 28;
    const vals = curve.map(c => c.compliance_balance_tco2e), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const x = p => L + (W - L - R) * p / 100, y = v => T + (H - T - B) * (1 - (v - lo) / ((hi - lo) || 1));
    const pts = curve.map(c => `${x(c.bio_pct)},${y(c.compliance_balance_tco2e)}`).join(' ');
    return `<svg class="fe-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="바이오 비중별 준수 잔액">
      <line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="rgba(226,232,240,.5)"/><text x="${L - 8}" y="${y(0) + 4}" font-size="11" fill="#94a3b8" text-anchor="end">0</text>
      <polyline points="${pts}" fill="none" stroke="#22c55e" stroke-width="2.5"/>
      ${[0, 20, 40, 60, 80, 100].map(p => `<text x="${x(p)}" y="${H - 8}" font-size="11" fill="#64748b" text-anchor="middle">B${p}</text>`).join('')}
      <circle cx="${x(current)}" cy="${y(curve[0].compliance_balance_tco2e + (curve.at(-1).compliance_balance_tco2e - curve[0].compliance_balance_tco2e) * current / 100)}" r="5" fill="#f8fafc"/>
      <text x="${L}" y="${T + 2}" font-size="11" fill="#64748b">준수 잔액 tCO₂e (위 = 잉여)</text></svg>`;
  }

  function runBlend(root, pool) {
    const f = root.querySelector('.fe-blend'), out = root.querySelector('.fe-blend-out');
    const v = n => f.elements[n].value;
    try {
      const intra = Number(v('intra')) / 100;
      if (intra > 1) throw new Error('EU↔EU 항해 비중은 100%를 넘을 수 없습니다');
      const eSel = v('e'), certified = eSel !== 'none';
      const eValue = eSel === 'custom' ? Number(v('ecustom')) : eSel === 'none' ? 14.9 : Number(eSel);
      if (eSel === 'custom' && v('ecustom') === '') throw new Error('인증서의 E 값을 입력하세요');
      const pct = Number(v('pct'));
      const r = blendEconomics(v('base'), pct / 100, Number(v('t')), { share: { intra_eu: intra, extra_eu: 1 - intra }, poolPrice: pool,
        premium: v('prem') === '' ? null : Number(v('prem')), eValue, certified });
      const zero = r.bio_share_for_zero_balance;
      out.innerHTML = `<div class="shipping-kpi-grid">
          ${kpi('혼합 후 잔액', `${fmt(r.with_blend.compliance_balance_tco2e)} tCO₂e`, `혼합 전 ${fmt(r.without.compliance_balance_tco2e)} · 집약도 ${fmt(r.with_blend.ghg_intensity, 1)}`, true)}
          ${kpi('바이오 1t이 만드는 잉여', `${fmt(r.surplus_per_t_bio_tco2e, 2)} tCO₂e`, `B100 집약도 ${fmt(r.pure_bio_intensity, 1)} gCO₂e/MJ`)}
          ${kpi('잔액 0이 되는 비중', zero === null ? '불가' : `B${fmt(zero * 100, 1)}`, zero === null ? '인증 없는 바이오는 혜택 없음' : '2025–2029 한도 기준')}
          ${kpi('손익분기 바이오 웃돈', r.surplus_per_t_bio_tco2e <= 0 ? '혜택 없음' : r.breakeven_premium_eur_per_t != null ? `${eur(r.breakeven_premium_eur_per_t)}/t` : '풀 가격 필요',
            r.cost_per_tco2e_of_blending != null ? `입력 웃돈이면 잉여 1t 만드는 데 ${eur(r.cost_per_tco2e_of_blending)} (풀 ${eur(pool, 1)})` : '이보다 싸면 풀 매입보다 혼합이 유리')}
        </div>${blendChart(r.curve, pct)}`;
    } catch (error) {
      out.innerHTML = `<div class="sc-error">${esc(error.message)}</div>`;
    }
  }

  // -------------------------------------------------------------- voyage calculator

  const EXAMPLE_LEGS = [
    { id: 'V1', status: 'actual', origin: { country: 'CN', name: '상하이' }, destination: { country: 'NL', name: '로테르담' }, at_sea: { hfo: 4200 }, at_berth: { mdo_mgo: 60 } },
    { id: 'V2', status: 'actual', origin: { country: 'NL', name: '로테르담' }, destination: { country: 'DE', name: '함부르크' }, at_sea: { mdo_mgo: 140 }, at_berth: { mdo_mgo: 45 } },
    { id: 'V3', status: 'actual', origin: { country: 'DE', name: '함부르크' }, destination: { country: 'ES', name: '라스팔마스', outermost: true }, at_sea: { hfo: 520 }, at_berth: { mdo_mgo: 30 } },
    { id: 'V4', status: 'planned', origin: { country: 'ES', name: '라스팔마스', outermost: true }, destination: { country: 'SG', name: '싱가포르' }, at_sea: { hfo: 3900 }, at_berth: {} },
    { id: 'V5', status: 'planned', origin: { country: 'SG', name: '싱가포르' }, destination: { country: 'CN', name: '상하이' }, at_sea: { hfo: 900 }, at_berth: {} }
  ];
  const SCOPE_KO = { intra_eu: 'EU↔EU 100%', extra_eu: 'EU↔역외 50%', outermost_region: '최외곽 50%', out_of_scope: '역외↔역외 0%' };

  const fuelOptions = sel => `<option value="">—</option>${Object.entries(FUELS).map(([k, f]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${esc(f.label)}</option>`).join('')}`;
  const legRow = leg => {
    const [sf, st] = Object.entries(leg.at_sea || {})[0] || ['', ''];
    const [bf, bt] = Object.entries(leg.at_berth || {})[0] || ['', ''];
    return `<tr>
      <td><input class="l-id" value="${esc(leg.id)}"></td>
      <td><select class="l-status"><option value="actual"${leg.status === 'actual' ? ' selected' : ''}>실적</option><option value="planned"${leg.status === 'planned' ? ' selected' : ''}>예정</option></select></td>
      <td><input class="l-o" maxlength="2" value="${esc(leg.origin.country)}" data-name="${esc(leg.origin.name || '')}"></td>
      <td><input class="l-d" maxlength="2" value="${esc(leg.destination.country)}" data-name="${esc(leg.destination.name || '')}"></td>
      <td><select class="l-outer"><option value="">아님</option><option value="o"${leg.origin.outermost ? ' selected' : ''}>출발</option><option value="d"${leg.destination.outermost ? ' selected' : ''}>도착</option></select></td>
      <td><select class="l-sf">${fuelOptions(sf)}</select></td><td><input class="l-st" type="number" min="0" step="any" value="${esc(st)}"></td>
      <td><select class="l-bf">${fuelOptions(bf)}</select></td><td><input class="l-bt" type="number" min="0" step="any" value="${esc(bt)}"></td>
      <td><button type="button" class="fe-del" aria-label="항차 삭제">×</button></td></tr>`;
  };

  function voyagePanel(pool) {
    return panel('VOYAGES', '항차 계산기: 연말 잔액, 항차별 비용, 메우는 방법', `
      ${note('업계 준수 관리 도구처럼 항차(출발항→도착항) 단위로 넣습니다. 국가 코드(ISO 2자리)로 적용 비율이 정해집니다: EU↔EU 100%, EU↔역외 50%, EU↔최외곽지역 50%, 역외↔역외 0%. 정박 연료는 도착항이 EU일 때만 100% 반영합니다. 예제는 가상 선박입니다.')}
      <div class="sc-form fe-quick fe-voy-ctl">
        <label class="sc-field"><span>보고연도</span><input name="year" type="number" min="2025" max="2050" value="2026"></label>
        <label class="sc-field"><span>풀 가격 €/t</span><input name="pool" type="number" min="0" step="any" value="${pool ?? 100}"></label>
        <label class="sc-field"><span>다음 기간 가격 가정</span><input name="next" type="number" min="0" step="any" placeholder="선택"></label>
        <label class="sc-field"><span>연속 미준수 기간</span><input name="consec" type="number" min="0" step="1" value="0"></label>
        <label class="sc-field"><span>같은 선대 선박 A 잔액 t</span><input name="fa" type="number" step="any" value="3200"></label>
        <label class="sc-field"><span>같은 선대 선박 B 잔액 t</span><input name="fb" type="number" step="any" value="-900"></label>
      </div>
      <div class="shipping-table-wrap"><table class="shipping-table compact-table fe-legs"><thead><tr>
        <th>항차</th><th>상태</th><th>출발국</th><th>도착국</th><th>최외곽</th><th>항해 연료</th><th>항해 t</th><th>정박 연료</th><th>정박 t</th><th></th>
      </tr></thead><tbody>${EXAMPLE_LEGS.map(legRow).join('')}</tbody></table></div>
      <div class="sc-actions fe-voy-actions"><button type="button" class="fe-add">항차 추가</button><button type="button" class="fe-reset">예제로 되돌리기</button></div>
      <div class="fe-voy-out"></div>`);
  }

  function readLegs(root) {
    return [...root.querySelectorAll('.fe-legs tbody tr')].map((tr, i) => {
      const v = c => tr.querySelector('.' + c).value.trim(), outer = v('l-outer');
      const leg = { id: v('l-id') || `L${i + 1}`, status: v('l-status'),
        origin: { country: v('l-o').toUpperCase(), name: tr.querySelector('.l-o').dataset.name || '', outermost: outer === 'o' },
        destination: { country: v('l-d').toUpperCase(), name: tr.querySelector('.l-d').dataset.name || '', outermost: outer === 'd' }, at_sea: {}, at_berth: {} };
      if (v('l-sf') && v('l-st') !== '') leg.at_sea[v('l-sf')] = Number(v('l-st'));
      if (v('l-bf') && v('l-bt') !== '') leg.at_berth[v('l-bf')] = Number(v('l-bt'));
      return leg;
    });
  }

  function runVoyages(root) {
    const out = root.querySelector('.fe-voy-out'), c = root.querySelector('.fe-voy-ctl');
    const v = n => c.querySelector(`[name="${n}"]`).value;
    try {
      const legs = readLegs(root), pool = Number(v('pool')), next = v('next') === '' ? null : Number(v('next'));
      const y = shipYear(legs, Number(v('year')), pool, { consecutiveDeficits: Number(v('consec')) || 0 });
      const f = y.full_year, a = y.actual_to_date, o = options(f, pool, next);
      const fleetIn = { '이 선박': f.compliance_balance_tco2e, '선박 A': Number(v('fa')) || 0, '선박 B': Number(v('fb')) || 0 };
      const fl = fleetPool(fleetIn);
      const routes = Object.fromEntries(legs.map(l => [l.id, `${l.origin.name || l.origin.country} → ${l.destination.name || l.destination.country}`]));
      const optRows = o.rows.map(r => `<tr class="${r.option === (o.cheapest || o.best) ? 'fe-best' : ''}"><td>${esc(r.label)}</td><td>${eur(o.position === 'deficit' ? r.cost_eur : r.value_eur)}</td><td>${esc(r.note || '')}</td></tr>`);
      out.innerHTML = `<div class="shipping-kpi-grid">
          ${kpi('연말 예측 준수 잔액', `${fmt(f.compliance_balance_tco2e, 1)} tCO₂e`, '실적 + 예정 항차', true)}
          ${kpi('현재까지 실적 잔액', a ? `${fmt(a.compliance_balance_tco2e, 1)} tCO₂e` : '실적 없음', '실적 항차만')}
          ${kpi('집약도 / 한도', `${fmt(f.ghg_intensity, 2)} / ${fmt(f.target, 2)}`, 'gCO₂e/MJ')}
          ${kpi('미조치 시 부담금', eur(f.penalty_eur), `tCO₂e당 ${eur(f.penalty_eur_per_tco2e)} · 배수 ${f.consecutive_multiplier}`)}
        </div>
        <div class="shipping-grid sc-two">
          ${panel('OPTIONS', o.position === 'deficit' ? '부족분을 메우는 방법' : '잉여분 활용', table(['선택', o.position === 'deficit' ? '비용' : '가치', '비고'], optRows) +
            note(o.position === 'deficit' ? `풀 가격이 ${eur(o.breakeven_pool_price)}/t를 넘으면 부담금이 더 쌉니다. 다음 기간 가격이 ${eur(o.borrow_beats_pool_if_next_below, 2)} 아래로 보이면 차입이 유리합니다(한도 ${fmt(f.borrow_limit_tco2e, 1)} t).` : `다음 기간 가격이 ${eur(o.bank_beats_sale_if_next_above, 2)}를 넘을 것으로 보면 이월이 유리합니다.`))}
          ${panel('FLEET POOL', '선대 내부 상쇄', table(['선박', '잔액 t', '배분 후'], Object.keys(fl.allocation).map(k => `<tr><td>${esc(k)}</td><td>${fmt(fleetIn[k], 1)}</td><td>${fmt(fl.allocation[k], 1)}</td></tr>`)) +
            note(`내부 상쇄 ${fmt(fl.internal_netting_tco2e, 1)} t · ${fl.external_need_tco2e > 0 ? `외부 매입 필요 ${fmt(fl.external_need_tco2e, 1)} t (${eur(fl.external_need_tco2e * pool)})` : `외부 판매 가능 ${fmt(fl.external_surplus_tco2e, 1)} t (${eur(fl.external_surplus_tco2e * pool)})`} · 제21조(4) ${fl.check.valid ? '충족' : '불충족: ' + esc(fl.check.problems.join(', '))}`))}
        </div>
        ${table(['항차', '상태', '구간', '적용', '잔액 변화 t', '풀 가격 기준 비용', '풀 가격 기준 가치'], y.legs.map(l =>
          `<tr><td>${esc(l.id)}</td><td>${l.status === 'actual' ? '실적' : '예정'}</td><td>${esc(routes[l.id])}</td><td>${SCOPE_KO[l.scope_basis]}</td><td>${fmt(l.cb_delta_tco2e, 1)}</td><td>${l.cost_at_pool_eur ? eur(l.cost_at_pool_eur) : '—'}</td><td>${l.value_at_pool_eur ? eur(l.value_at_pool_eur) : '—'}</td></tr>`))}
        ${note('항차별 값은 그 항차를 뺀 연간 결과와의 차이입니다(비례 배분 아님). 용선계약 FuelEU 조항으로 용선자에게 청구하는 근거가 됩니다. 수수료·자금비용·거래상대 신용은 빠져 있습니다.')}`;
    } catch (error) {
      out.innerHTML = `<div class="sc-error">${esc(error.message)}</div>`;
    }
  }

  const biofuelPanel = () => panel('BIOFUELS & RFNBO', '바이오연료·e-연료 관련 규정', `
    ${table(['조항', '내용'], [
      '<tr><td>제10조(1)(a)</td><td>RED II 제29조의 지속가능성·감축 기준을 못 맞추거나 식량·사료 작물로 만든 바이오연료는 같은 종류 화석연료 중 가장 불리한 배출계수로 계산. 혼합해도 혜택 없음.</td></tr>',
      '<tr><td>제10조(3)·(4)</td><td>바이오연료 혜택은 EU가 인정한 인증제도(RED II 제30조)의 실제 WtT 값이 벙커 인도증(BDN)에 있을 때만. 화석연료는 기본값에서 벗어날 수 없음.</td></tr>',
      '<tr><td>부속서 II</td><td>바이오연료 WtT는 RED II의 E 값에서 연소 CO₂분을 빼서 구함(이중 계산 방지). 고정 기본값이 없어 경로마다 다름.</td></tr>',
      '<tr><td>제5조(1)</td><td>RFNBO(e-메탄올 등 그린수소 기반 연료)는 2025~2033년 에너지를 2배로 인정.</td></tr>',
      '<tr><td>제5조(3)~(5)</td><td>2031년 RFNBO 비중이 1% 미만이면 2034년부터 2% 하위목표. 2033년 전 2%를 넘었거나 공급·가격 문제가 확인되면 적용 안 함.</td></tr>'
    ])}
    ${note('그래서 바이오 혼합은 인증된 폐기물·잔재물 원료(UCO 등) 바이오연료여야 잉여를 만듭니다. 이 원료의 프리미엄이 풀 가격의 실질적인 기준선입니다.')}`);

  const render = async host => {
    host.innerHTML = '<div class="shipping-loading"><span></span><p>FuelEU 자료를 불러오는 중입니다.</p></div>';
    let data;
    try {
      data = await (await fetch(DATA_URL, { cache: 'no-cache' })).json();
    } catch (error) {
      host.innerHTML = `<div class="shipping-error"><strong>FuelEU 자료를 불러오지 못했습니다.</strong><p>${esc(error.message)}</p></div>`;
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const live = today <= data.display_until && !!data.prices;
    const series = data.prices?.series || {};
    const latestKey = Object.keys(series).sort().at(-1);
    const latest = live && latestKey ? series[latestKey].at(-1) : null;
    const hfo = data.rules.fuels.find(f => f.key === 'hfo');
    const years = Object.keys(data.supply || {}).sort().reverse();
    host.innerHTML = `
      ${live ? '' : `<div class="sc-sources fe-insight"><strong>게시 종료</strong><span>풀 가격과 MRV 수급 추정은 ${esc(data.display_until)}까지만 게시했습니다. 규정 기반 계산은 계속 제공합니다.</span></div>`}
      <div class="shipping-kpi-grid">
        ${kpi('현재 풀 가격 (OPX)', latest ? `${eur(latest.value_eur_per_tco2e, 2)}` : '게시 안 함', latest ? `${latestKey}년분 · ${latest.month} · 공개 호가 지수` : '', true)}
        ${kpi('가격 상한 (부담금 환산)', `${eur(hfo.penalty_eur_per_tco2e)}`, `HFO 선박 기준 · 현재가는 상한의 ${latest ? fmt(latest.value_eur_per_tco2e / hfo.penalty_eur_per_tco2e * 100) + '%' : '—'}`)}
        ${kpi('2025–2029 한도', `${fmt(data.rules.periods[0].target, 2)}`, 'gCO₂e/MJ · 2030년 85.69로 강화')}
        ${kpi('총량 한도', '없음', 'ETS와 달리 선박별 집약도 기준')}
      </div>
      ${panel('1 · RULES', '한도는 5년마다 계단식으로 내려가고, 연료마다 부족으로 바뀌는 시점이 다르다', `
        ${rulesChart(data.rules)}
        ${note('흰 계단 = FuelEU 한도(91.16 gCO₂e/MJ에서 2025년 −2%, 2030년 −6%, 2035년 −14.5%, 2040년 −31%, 2045년 −62%, 2050년 −80%). 점선 = 석유 연료, 실선 = LNG 엔진별. 점은 그 연료가 부족으로 바뀌는 해입니다. 총량(cap)이 없어서 한도보다 깨끗하게 운항한 만큼 잉여가 새로 생기고, 시장 공급량은 정해져 있지 않습니다.')}
        ${table(['보고기간 다음 해', '할 일 (원문 확인분)'], ['<tr><td>4월 30일까지</td><td>차입분 등록 (제20조(3))</td></tr>', '<tr><td>5월 1일 전</td><td>풀링·이월·차입 반영 후 검증 잔액 기록 (제23조(1))</td></tr>', '<tr><td>6월 30일까지</td><td>부족 선박 부담금 납부 — |부족분| ÷ (실제 집약도 × 41,000 MJ) × €2,400, 연속 시 1 + (n−1)/10배 (제23조(2), 부속서 IV)</td></tr>'])}`,
        `<a class="shipping-source-link" href="${esc(data.regulation.url)}" target="_blank" rel="noopener">규정 원문 ↗</a>`)}
      ${live ? panel('2 · POOL PRICE', 'FuelEU 잉여분 풀 가격 (OPX, EUR/tCO₂e)', `
        ${priceChart(series)}
        ${note('FuelEU 잉여분은 거래소 상품이 아니라 선사 간 풀링 계약으로 거래되고 공식 가격이 없습니다. OceanScore Pool-Price Index(OPX) 공개 월간 해설의 지수이며 공개 호가 기반이라 체결가가 아닙니다. 옅은 막대 = 해설에 적힌 호가 범위, 속이 빈 점 = 다음 달 해설에 다시 적힌 값, 해설이 없는 달은 선을 잇지 않습니다.')}`,
        `<a class="shipping-source-link" href="${esc(data.prices.source_index_url)}" target="_blank" rel="noopener">OceanScore OPX ↗</a>`) : ''}
      ${live && years.length ? panel('3 · SUPPLY & DEMAND', '잉여는 누가 만들고, 부족은 누가 지는가 (EMSA MRV 기반 추정)', '<div class="fe-supply-body"></div>',
        `<div class="fe-controls"><label>보고연도 <select class="fe-year">${years.map(y => `<option>${y}</option>`).join('')}</select></label><label>적용 한도 <select class="fe-target"><option>2025</option><option>2030</option><option>2035</option></select></label></div>`) : ''}
      ${quickPanel()}
      ${blendPanel()}
      ${voyagePanel(latest?.value_eur_per_tco2e ?? null)}
      ${biofuelPanel()}`;
    const drawSupply = () => {
      const body = host.querySelector('.fe-supply-body');
      if (body) body.innerHTML = supplyBlock(data.supply, host.querySelector('.fe-year').value, host.querySelector('.fe-target').value);
    };
    host.querySelector('.fe-controls')?.addEventListener('change', drawSupply);
    drawSupply();
    const pool = latest?.value_eur_per_tco2e ?? null;
    host.querySelector('.fe-quick').addEventListener('input', () => runQuick(host, pool));
    host.querySelector('.fe-quick').addEventListener('change', () => runQuick(host, pool));
    runQuick(host, pool);
    const blend = host.querySelector('.fe-blend');
    ['input', 'change'].forEach(ev => blend.addEventListener(ev, () => runBlend(host, pool)));
    runBlend(host, pool);
    const legsBody = host.querySelector('.fe-legs tbody');
    const voyRoot = legsBody.closest('.shipping-panel');
    voyRoot.addEventListener('change', () => runVoyages(host));
    voyRoot.addEventListener('click', e => {
      if (e.target.classList.contains('fe-del')) { e.target.closest('tr').remove(); runVoyages(host); }
      if (e.target.classList.contains('fe-add')) {
        legsBody.insertAdjacentHTML('beforeend', legRow({ id: `L${legsBody.children.length + 1}`, status: 'planned', origin: { country: 'NL' }, destination: { country: 'DE' }, at_sea: { mdo_mgo: 100 }, at_berth: {} }));
        runVoyages(host);
      }
      if (e.target.classList.contains('fe-reset')) { legsBody.innerHTML = EXAMPLE_LEGS.map(legRow).join(''); runVoyages(host); }
    });
    runVoyages(host);
  };

  window.ShippingFuelEU = { render, engine };
})();
