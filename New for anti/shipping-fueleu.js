// 해운 › FuelEU 풀링: rules, pool-price history, MRV supply structure, ship check.
//
// Data: /public/data/fueleu_market_v1.json, built by tools/fueleu/build_site_data.py.
// The ship check runs in the browser; its calculation is a port of
// tools/fueleu/engine.py (intensity, target, quick_check) for the Annex II
// fossil defaults, held to the Python output by tests/fueleu/engine.test.mjs.
//
// The OPX series and the MRV estimate are shown for a limited time chosen by
// the user (redistribution terms unconfirmed). After data.display_until the tab
// keeps the regulation-only parts and drops both.
(() => {
  // ------------------------------------------------------------------ engine

  const REFERENCE = 91.16;
  const REDUCTIONS = [[2025, 2], [2030, 6], [2035, 14.5], [2040, 31], [2045, 62], [2050, 80]];
  const GWP = { CH4: 25, N2O: 298 };
  const SCOPE_SHARE = { at_berth: 1, intra_eu: 1, extra_eu: 0.5 };
  const FUELS = {
    hfo: { label: 'HFO', lcv: 0.0405, wtt: 13.5, cf_co2: 3.114, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    lfo: { label: 'LFO', lcv: 0.041, wtt: 13.2, cf_co2: 3.151, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    mdo_mgo: { label: 'MDO/MGO', lcv: 0.0427, wtt: 14.4, cf_co2: 3.206, cf_ch4: 0.00005, cf_n2o: 0.00018, slip: 0 },
    lng_otto_ms: { label: 'LNG 오토 중속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 3.1 },
    lng_otto_ss: { label: 'LNG 오토 저속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 1.7 },
    lng_diesel_ss: { label: 'LNG 디젤 저속', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 0.2 },
    lng_lbsi: { label: 'LNG LBSI', lcv: 0.0491, wtt: 18.5, cf_co2: 2.75, cf_ch4: 0, cf_n2o: 0.00011, slip: 2.6 }
  };

  const target = year => {
    const step = [...REDUCTIONS].reverse().find(([start]) => year >= start);
    if (!step) throw new Error('FuelEU는 2025 보고연도부터 적용됩니다');
    return REFERENCE * (1 - step[1] / 100);
  };

  const intensity = rows => {
    let wtt = 0, ttw = 0, energy = 0;
    rows.forEach(({ fuel, tonnes, scope }) => {
      const f = FUELS[fuel];
      if (!f) throw new Error(`알 수 없는 연료: ${fuel}`);
      if (!(tonnes >= 0)) throw new Error('연료량은 0 이상이어야 합니다');
      const grams = tonnes * 1e6 * SCOPE_SHARE[scope];
      const slip = f.slip / 100;
      wtt += grams * f.wtt * f.lcv;
      ttw += grams * ((1 - slip) * (f.cf_co2 + f.cf_ch4 * GWP.CH4 + f.cf_n2o * GWP.N2O) + slip * GWP.CH4);
      energy += grams * f.lcv;
    });
    if (energy <= 0) throw new Error('EU 관련 연료 사용량을 입력하세요');
    return { ghg_intensity: (wtt + ttw) / energy, energy_mj: energy };
  };

  const penaltyEur = (cbG, actual) => cbG >= 0 ? 0 : Math.abs(cbG) / (actual * 41000) * 2400;

  const quickCheck = (grossTonnage, fuels, share = { extra_eu: 1 }, year = 2025) => {
    if (grossTonnage !== null && grossTonnage <= 5000) return { in_scope: false };
    if (Math.abs(Object.values(share).reduce((a, b) => a + b, 0) - 1) > 1e-6) throw new Error('항해 비중의 합은 100%여야 합니다');
    const rows = Object.entries(fuels).flatMap(([fuel, t]) => Object.entries(share).filter(([, v]) => v).map(([scope, v]) => ({ fuel, tonnes: t * v, scope })));
    const at = y => {
      const i = intensity(rows), tgt = target(y), cbG = (tgt - i.ghg_intensity) * i.energy_mj;
      return { target: tgt, ghg_intensity: i.ghg_intensity, energy_mj: i.energy_mj, compliance_balance_tco2e: cbG / 1e6, penalty_eur: penaltyEur(cbG, i.ghg_intensity) };
    };
    const now = at(year);
    const timeline = REDUCTIONS.map(([start]) => {
      const r = at(Math.max(start, year));
      return { from_year: start, target: r.target, compliance_balance_tco2e: r.compliance_balance_tco2e,
        position: r.compliance_balance_tco2e >= 0 ? 'surplus' : 'deficit', penalty_eur: r.penalty_eur };
    });
    return { in_scope: true, ...now, position: now.compliance_balance_tco2e >= 0 ? 'surplus' : 'deficit',
      margin_gco2e_per_mj: now.target - now.ghg_intensity,
      first_deficit_period: timeline.find(t => t.position === 'deficit')?.from_year ?? null, timeline };
  };

  const engine = { target, intensity, quickCheck, FUELS };
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
    const t = d.total, lng = d.by_propulsion.lng || {}, oil = d.by_propulsion.oil || {};
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
        ${kpi('장부상 순수급', kt(t[`net_${tgtYear}`]), '잉여 − 부족 · 바이오 혼합 제외')}
      </div>
      <div class="sc-sources fe-insight"><strong>읽는 법</strong><span>석유선의 구조적 부족이 LNG선 잉여보다 큽니다. 그런데도 시장 해설은 "공급이 수요를 넘는다"고 하고 가격은 내려갑니다. 차이는 바이오연료 혼합으로 필요할 때 만드는 잉여가 메웁니다. 그래서 풀 가격은 LNG 잉여량보다 바이오 혼합 비용에 끌려갑니다. 2030년 한도(−6%)가 오면 부족이 약 ${fmt(t.deficit_2030 / t.deficit_2025, 1)}배로 커집니다.</span></div>
      <div class="fe-legend"><span><i class="fe-def"></i>부족 (풀에서 사야 하는 양)</span><span><i class="fe-sur"></i>잉여 (풀에 팔 수 있는 양)</span></div>
      ${table(['선종', '척수', '부족', '잉여', '부족 t', '잉여 t'], rows, 'fe-supply')}
      <div class="shipping-grid sc-two">
        ${panel('BY PROPULSION', '추진 연료별', table(['구분', '척수', '평균 집약도', '2025 한도 순', '2030 한도 순'], [
          ...Object.entries(d.by_propulsion).map(([k, v]) => `<tr><td>${k === 'lng' ? 'LNG 추진선' : '석유 연료선'}</td><td>${fmt(v.ships)}</td><td>${fmt(v.avg_intensity, 2)}</td><td>${kt(v.net_2025)}</td><td>${kt(v.net_2030)}</td></tr>`),
          `<tr><td>바이오 혼합 추정</td><td>${fmt(d.unestimated.bio_blend_suspected || 0)}</td><td colspan="3">MRV에 바이오 WtW 혜택이 없어 계산 제외</td></tr>`,
          `<tr><td>메탄올·기타</td><td>${fmt(d.unestimated.other || 0)}</td><td colspan="3">계산 제외</td></tr>`]))}
        ${panel('LIMITS', '이 추정의 한계', `<ul class="sc-note fe-list">
          <li>공식 FuelEU 잔액이 아닙니다. FuelEU 데이터베이스는 비공개입니다.</li>
          <li>MRV에 총톤수가 없어 5,000 GT 이하 선박을 걸러내지 못했습니다. 부족이 과대 추정될 수 있습니다.</li>
          <li>바이오 혼합 선박이 빠져 잉여는 과소 추정입니다.</li>
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
    const live = today <= data.display_until;
    const series = data.prices.series;
    const latestKey = Object.keys(series).sort().at(-1);
    const latest = live && latestKey ? series[latestKey].at(-1) : null;
    const hfo = data.rules.fuels.find(f => f.key === 'hfo');
    const years = Object.keys(data.supply).sort().reverse();
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
  };

  window.ShippingFuelEU = { render, engine };
})();
