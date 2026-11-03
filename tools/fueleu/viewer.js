const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 0) => v === null || v === undefined ? '미확인' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: 0 });
const eur = (v, d = 0) => v === null || v === undefined ? '미확인' : `€${fmt(v, d)}`;
const SCOPE = { intra_eu: 'EU↔EU 100%', extra_eu: 'EU↔역외 50%', outermost_region: '최외곽 50%', out_of_scope: '역외↔역외 0%' };
const COLORS = { 2025: '#94a3b8', 2026: '#38bdf8', 2027: '#a78bfa' };

let fuels = {}, example = null, legs = [], fleet = {}, seq = 0;

// ------------------------------------------------------------ price history

function chart(series) {
  const pts = Object.entries(series).flatMap(([cy, s]) => s.map(p => ({ ...p, cy })));
  if (!pts.length) return '<p class="note">관측값이 없습니다.</p>';
  const months = [...new Set(pts.map(p => p.month))].sort();
  const first = months[0], last = months.at(-1);
  const idx = m => { const [y, mo] = m.split('-').map(Number); const [y0, m0] = first.split('-').map(Number); return (y - y0) * 12 + (mo - m0); };
  const span = Math.max(1, idx(last));
  const vals = pts.flatMap(p => [p.value_eur_per_tco2e, p.offer_low_eur, p.offer_high_eur]).filter(v => v != null);
  const lo = Math.floor(Math.min(...vals) / 25) * 25, hi = Math.ceil(Math.max(...vals) / 25) * 25;
  const W = 900, H = 320, L = 52, R = 20, T = 40, B = 38;
  const x = m => L + (W - L - R) * idx(m) / span;
  const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const grid = [];
  for (let v = lo; v <= hi; v += 25) grid.push(`<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(148,163,184,.12)"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#64748b">€${v}</text>`);
  const ticks = [];
  for (let i = 0; i <= span; i++) {
    const [y0, m0] = first.split('-').map(Number); const t = new Date(Date.UTC(y0, m0 - 1 + i, 1));
    const label = `${String(t.getUTCFullYear()).slice(2)}.${String(t.getUTCMonth() + 1).padStart(2, '0')}`;
    if (i % 2 === 0 || span < 10) ticks.push(`<text x="${L + (W - L - R) * i / span}" y="${H - 14}" text-anchor="middle" font-size="11" fill="#64748b">${label}</text>`);
  }
  const lines = Object.entries(series).map(([cy, s]) => {
    const c = COLORS[cy] || '#f59e0b';
    const band = s.filter(p => p.offer_low_eur != null).map(p => `<line x1="${x(p.month)}" x2="${x(p.month)}" y1="${y(p.offer_low_eur)}" y2="${y(p.offer_high_eur)}" stroke="${c}" stroke-opacity=".28" stroke-width="10" stroke-linecap="round"><title>${esc(p.month)} 호가 범위 €${p.offer_low_eur}–€${p.offer_high_eur}</title></line>`).join('');
    // Missing months stay as gaps: the line breaks instead of interpolating across them.
    const segs = []; let cur = [];
    s.forEach((p, i) => { if (i && idx(p.month) - idx(s[i - 1].month) > 1) { segs.push(cur); cur = []; } cur.push(p); });
    segs.push(cur);
    const path = segs.filter(g => g.length > 1).map(g => `<polyline fill="none" stroke="${c}" stroke-width="2.5" points="${g.map(p => `${x(p.month)},${y(p.value_eur_per_tco2e)}`).join(' ')}"/>`).join('');
    const dots = s.map(p => `<circle cx="${x(p.month)}" cy="${y(p.value_eur_per_tco2e)}" r="${p.basis === 'monthly_commentary' ? 4.5 : 3.5}" fill="${p.basis === 'monthly_commentary' ? c : '#070b14'}" stroke="${c}" stroke-width="2"><title>${esc(p.month)} CB${cy} €${p.value_eur_per_tco2e}${p.basis === 'monthly_commentary' ? '' : ' (다음 달 해설에서 재기재)'}</title></circle>`).join('');
    return band + path + dots;
  }).join('');
  const legend = Object.keys(series).map((cy, i) => `<g transform="translate(${L + i * 150},6)"><rect width="14" height="3" y="5" fill="${COLORS[cy] || '#f59e0b'}"/><text x="20" y="10" font-size="12" fill="#cbd5e1">${cy}년분 잉여</text></g>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="FuelEU 풀 가격 월별 추이">${grid.join('')}${ticks.join('')}${lines}${legend}</svg>
    <p class="note">선은 월별 OPX, 옅은 막대는 해설에 적힌 호가 범위입니다. 속이 빈 점은 해당 월 해설이 없어 다음 달 해설에 다시 적힌 값입니다. 해설이 없는 달은 선을 잇지 않습니다.</p>`;
}

async function loadMarket() {
  const m = await (await fetch('/api/market')).json();
  if (m.status === 'missing') {
    $('#chart').innerHTML = `<p class="warn">가격 자료가 없습니다. <code>${esc(m.hint)}</code> 를 실행하면 공개 해설에서 수집합니다. 예시 숫자로 대신 채우지 않습니다.</p>`;
    return null;
  }
  const latest = Object.entries(m.series).map(([cy, s]) => [cy, s.at(-1)]).sort().at(-1);
  $('#market-meta').innerHTML = `수집 ${esc(new Date(m.retrieved_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }))} KST<br>
    <a href="${esc(m.source_index_url)}" target="_blank" rel="noopener">OceanScore OPX ↗</a> · 공개 호가 지수 · 해설 없는 달: ${esc((m.missing_pages || []).join(', ') || '없음')}`;
  $('#chart').innerHTML = `<p class="warn">재배포 권한 미확인 — 로컬 분석용. 공개 사이트에 게시하지 마세요.</p>` + chart(m.series);
  const rows = Object.entries(m.series).flatMap(([cy, s]) => s.map(p => ({ ...p, cy }))).sort((a, b) => b.month.localeCompare(a.month) || b.cy - a.cy);
  $('#market-table').innerHTML = `<details><summary class="note">월별 값과 출처 (${rows.length})</summary><div class="table-wrap"><table>
    <thead><tr><th>월</th><th>대상</th><th class="num">OPX</th><th class="num">호가 범위</th><th>근거</th></tr></thead><tbody>
    ${rows.map(p => `<tr><td>${esc(p.month)}</td><td>${esc(p.cy)}년분${p.compliance_year_basis === 'stated' ? '' : ' (주기 추정)'}</td><td class="num">${eur(p.value_eur_per_tco2e, 2)}</td>
      <td class="num">${p.offer_low_eur != null ? `${eur(p.offer_low_eur)}–${eur(p.offer_high_eur)}` : '—'}</td>
      <td><a href="${esc(p.source_url)}" target="_blank" rel="noopener">${p.basis === 'monthly_commentary' ? '해당 월 해설' : '다음 달 해설'} ↗</a></td></tr>`).join('')}
    </tbody></table></div></details>`;
  return latest ? latest[1].value_eur_per_tco2e : null;
}

// ---------------------------------------------------------------- voyages

const fuelSelect = (value, cls) => `<select class="${cls}"><option value="">—</option>${Object.entries(fuels).map(([k, l]) => `<option value="${k}"${k === value ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;

function legRow(leg) {
  const [seaFuel, seaT] = Object.entries(leg.at_sea || {})[0] || ['', ''];
  const [berthFuel, berthT] = Object.entries(leg.at_berth || {})[0] || ['', ''];
  return `<tr data-id="${esc(leg.id)}">
    <td><input class="id" value="${esc(leg.id)}"></td>
    <td><select class="status"><option value="actual"${leg.status === 'actual' ? ' selected' : ''}>실적</option><option value="planned"${leg.status === 'planned' ? ' selected' : ''}>예정</option></select></td>
    <td><input class="o" maxlength="2" value="${esc(leg.origin.country)}" title="${esc(leg.origin.name || '')}"></td>
    <td><input class="d" maxlength="2" value="${esc(leg.destination.country)}" title="${esc(leg.destination.name || '')}"></td>
    <td><select class="outer"><option value="">아님</option><option value="o"${leg.origin.outermost ? ' selected' : ''}>출발</option><option value="d"${leg.destination.outermost ? ' selected' : ''}>도착</option></select></td>
    <td>${fuelSelect(seaFuel, 'sf')}</td><td><input class="st" type="number" min="0" step="any" value="${esc(seaT)}"></td>
    <td>${fuelSelect(berthFuel, 'bf')}</td><td><input class="bt" type="number" min="0" step="any" value="${esc(berthT)}"></td>
    <td><button type="button" class="del" aria-label="항차 삭제">×</button></td></tr>`;
}

function readLegs() {
  return [...document.querySelectorAll('#legs tbody tr')].map(tr => {
    const v = c => tr.querySelector('.' + c).value.trim();
    const outer = v('outer');
    const leg = { id: v('id') || `L${++seq}`, status: v('status'),
      origin: { country: v('o').toUpperCase(), name: tr.querySelector('.o').title || undefined, outermost: outer === 'o' },
      destination: { country: v('d').toUpperCase(), name: tr.querySelector('.d').title || undefined, outermost: outer === 'd' },
      at_sea: {}, at_berth: {} };
    if (v('sf') && v('st') !== '') leg.at_sea[v('sf')] = Number(v('st'));
    if (v('bf') && v('bt') !== '') leg.at_berth[v('bf')] = Number(v('bt'));
    return leg;
  });
}

function drawLegs() {
  $('#legs tbody').innerHTML = legs.map(legRow).join('');
}

// ---------------------------------------------------------------- results

const kpi = (label, value, note = '', tone = '') => `<div class="kpi ${tone}"><span>${esc(label)}</span><strong>${value}</strong><small>${esc(note)}</small></div>`;

function render(r, pool) {
  const f = r.year.full_year, a = r.year.actual_to_date, o = r.options;
  const cb = f.compliance_balance_tco2e;
  const optRows = o.position === 'deficit'
    ? o.rows.map(x => `<tr class="${x.option === o.cheapest ? 'best' : ''}"><td>${esc(x.label)}</td><td class="num">${eur(x.cost_eur)}</td><td>${esc(x.note || '')}</td></tr>`).join('')
    : o.rows.map(x => `<tr class="${x.option === o.best ? 'best' : ''}"><td>${esc(x.label)}</td><td class="num">${eur(x.value_eur)}</td><td>${esc(x.note || '')}</td></tr>`).join('');
  const fl = r.fleet;
  $('#results').innerHTML = `
    <div class="kpis">
      ${kpi('연말 예측 준수 잔액', `${fmt(cb, 1)} tCO₂e`, '실적 + 예정 항차', cb < 0 ? 'neg' : 'pos')}
      ${kpi('현재까지 실적 잔액', a ? `${fmt(a.compliance_balance_tco2e, 1)} tCO₂e` : '실적 없음', '실적 항차만')}
      ${kpi('GHG 집약도 / 목표', `${fmt(f.ghg_intensity, 2)} / ${fmt(f.target, 2)}`, 'gCO₂e/MJ · 낮을수록 좋음')}
      ${kpi('부담금 (미조치 시)', eur(f.penalty_eur), `tCO₂e당 ${eur(f.penalty_eur_per_tco2e)} 환산 · 배수 ${f.consecutive_multiplier}`)}
    </div>
    <div class="grid2">
      <section class="panel"><div class="head"><div><p class="kicker">OPTIONS</p><h2>${o.position === 'deficit' ? '부족분을 메우는 방법' : '잉여분 활용'} — 풀 가격 ${eur(pool, 2)}</h2></div></div>
        <div class="table-wrap"><table><thead><tr><th>선택</th><th class="num">${o.position === 'deficit' ? '비용' : '가치'}</th><th>비고</th></tr></thead><tbody>${optRows}</tbody></table></div>
        <p class="note">${o.position === 'deficit'
          ? `풀 가격이 ${eur(o.breakeven_pool_price)}/t를 넘으면 부담금이 더 싸집니다. 다음 기간 풀 가격이 ${eur(o.borrow_beats_pool_if_next_below, 2)} 아래일 것으로 보면 차입이 유리합니다. 차입 한도 ${fmt(f.borrow_limit_tco2e, 1)} t.`
          : `다음 기간 가격이 ${eur(o.bank_beats_sale_if_next_above, 2)}를 넘을 것으로 보면 이월이 유리합니다.`} 중개 수수료·자금비용·거래상대 신용은 빠져 있습니다.</p>
      </section>
      <section class="panel"><div class="head"><div><p class="kicker">FLEET POOL</p><h2>선대 내부 상쇄</h2></div></div>
        ${fl ? `<div class="table-wrap"><table><thead><tr><th>선박</th><th class="num">잔액 (t)</th><th class="num">풀 배분 후</th></tr></thead><tbody>
          ${Object.keys(fl.allocation).map(k => `<tr><td>${esc(k)}</td><td class="num">${fmt(r.fleetInput[k], 1)}</td><td class="num">${fmt(fl.allocation[k], 1)}</td></tr>`).join('')}
          </tbody></table></div>
          <p class="note">내부 상쇄 ${fmt(fl.internal_netting_tco2e, 1)} t · ${fl.external_need_tco2e > 0 ? `외부 매입 필요 ${fmt(fl.external_need_tco2e, 1)} t (${eur(fl.external_need_tco2e * pool)})` : `외부 판매 가능 ${fmt(fl.external_surplus_tco2e, 1)} t (${eur(fl.external_surplus_tco2e * pool)})`} · 제21조(4) ${fl.check.valid ? '충족' : '불충족: ' + esc(fl.check.problems.join(', '))}</p>`
          : '<p class="note">선대 자료가 없습니다.</p>'}
        <p class="note">다른 선박 잔액은 가상 값입니다.</p>
      </section>
    </div>
    <section class="panel" style="margin-top:18px"><div class="head"><div><p class="kicker">PER VOYAGE</p><h2>항차별 FuelEU 비용</h2></div></div>
      <div class="table-wrap"><table><thead><tr><th>항차</th><th>상태</th><th>구간</th><th>적용</th><th class="num">잔액 변화 (t)</th><th class="num">풀 가격 기준 비용</th><th class="num">풀 가격 기준 가치</th></tr></thead><tbody>
      ${r.year.legs.map(l => `<tr><td>${esc(l.id)}</td><td>${l.status === 'actual' ? '실적' : '예정'}</td><td>${esc(l.route)}</td><td>${esc(SCOPE[l.scope_basis])}</td>
        <td class="num">${fmt(l.cb_delta_tco2e, 1)}</td><td class="num">${l.cost_at_pool_eur ? eur(l.cost_at_pool_eur) : '—'}</td><td class="num">${l.value_at_pool_eur ? eur(l.value_at_pool_eur) : '—'}</td></tr>`).join('')}
      </tbody></table></div>
      <p class="note">항차별 값은 그 항차를 뺀 연간 결과와의 차이입니다(비례 배분 아님). 용선계약의 FuelEU 조항으로 용선자에게 청구하는 금액의 근거가 됩니다.</p>
    </section>`;
}

async function run() {
  legs = readLegs();
  const pool = Number($('#pool').value);
  const fleetInput = Object.fromEntries(Object.entries(fleet));
  const body = { year: $('#year').value, pool_price: pool, next_pool_price: $('#next').value, consecutive_deficits: $('#consec').value,
    legs, fleet: fleetInput };
  try {
    const res = await fetch('/api/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const r = await res.json();
    if (!res.ok) throw new Error(r.error);
    r.fleetInput = Object.fromEntries(Object.entries(fleetInput).map(([k, v]) => [k, v === null ? r.year.full_year.compliance_balance_tco2e : v]));
    $('#error').hidden = true;
    render(r, pool);
  } catch (e) {
    $('#error').textContent = e.message;
    $('#error').hidden = false;
    $('#results').innerHTML = '';
  }
}

function reset() {
  legs = structuredClone(example.legs);
  fleet = example.fleet;
  $('#year').value = example.year;
  $('#consec').value = example.consecutive_deficits;
  drawLegs();
  run();
}

// ------------------------------------------------------------ 1 rules

const FUEL_COLOR = k => k.startsWith('lng') ? ({ lng_otto_ms: '#7dd3fc', lng_lbsi: '#38bdf8', lng_otto_ss: '#0ea5e9', lng_diesel_ss: '#0369a1' }[k]) : ({ hfo: '#f97316', lfo: '#fb923c', mdo_mgo: '#fbbf24' }[k] || '#a3a3a3');

const SHORT = { hfo: 'HFO', lfo: 'LFO', mdo_mgo: 'MGO', lng_otto_ms: 'LNG 오토 중속', lng_lbsi: 'LNG LBSI', lng_otto_ss: 'LNG 오토 저속', lng_diesel_ss: 'LNG 디젤 저속' };

function rulesChart(r) {
  const W = 900, H = 360, L = 52, R = 170, T = 16, B = 34, y0 = 2025, y1 = 2052, lo = 10, hi = 95;
  const x = y => L + (W - L - R) * (y - y0) / (y1 - y0);
  const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const steps = r.periods.map((p, i) => ({ ...p, to: r.periods[i + 1]?.from_year ?? y1 }));
  const stair = steps.map(p => `${x(p.from_year)},${y(p.target)} ${x(p.to)},${y(p.target)}`).join(' ');
  const deficitZone = `${x(y0)},${y(hi)} ${stair} ${x(y1)},${y(hi)}`;
  const grid = [20, 40, 60, 80, 90].map(v => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(148,163,184,.1)"/><text x="${L - 8}" y="${y(v) + 4}" font-size="11" fill="#64748b" text-anchor="end">${v}</text>`).join('');
  const xt = r.periods.map(p => `<text x="${x(p.from_year)}" y="${H - 12}" font-size="11" fill="#64748b" text-anchor="middle">${p.from_year}</text><text x="${(x(p.from_year) + x(steps.find(s => s.from_year === p.from_year).to)) / 2}" y="${y(p.target) + 15}" font-size="10.5" fill="#94a3b8" text-anchor="middle">${fmt(p.target, 1)}</text>`).join('');
  // Labels on the right are spread out so close intensities (91.7 / 91.4 / 90.8) stay readable.
  const lab = r.fuels.map(f => ({ f, ly: y(f.intensity) }));
  lab.forEach((l, i) => { if (i && l.ly - lab[i - 1].ly < 14) l.ly = lab[i - 1].ly + 14; });
  const fuelsSvg = lab.map(({ f, ly }) => {
    const c = FUEL_COLOR(f.key), fy = y(f.intensity);
    const cross = f.first_deficit_period ? `<circle cx="${x(f.first_deficit_period)}" cy="${fy}" r="4.5" fill="${c}"><title>${esc(f.label)}: ${f.first_deficit_period}년부터 부족</title></circle>` : '';
    return `<line x1="${L}" x2="${W - R}" y1="${fy}" y2="${fy}" stroke="${c}" stroke-width="2" stroke-dasharray="${f.key.startsWith('lng') ? '0' : '6 4'}"/>${cross}
      <path d="M${W - R} ${fy} L${W - R + 10} ${ly}" stroke="${c}" fill="none"/><text x="${W - R + 14}" y="${ly + 4}" font-size="11.5" fill="${c}">${esc(SHORT[f.key] || f.key)} ${fmt(f.intensity, 1)} → ${f.first_deficit_period ?? '–'}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="FuelEU 한도 계단과 연료별 집약도">
    <polygon points="${deficitZone}" fill="rgba(239,68,68,.07)"/>
    <text x="${x(2045)}" y="${y(70)}" font-size="13" fill="rgba(252,165,165,.7)" text-anchor="middle">한도보다 높음 = 부족</text>
    <text x="${x(2026.5)}" y="${y(40)}" font-size="13" fill="rgba(134,239,172,.6)">한도보다 낮음 = 잉여</text>
    ${grid}<polyline points="${stair}" fill="none" stroke="#e2e8f0" stroke-width="2.5"/>${xt}${fuelsSvg}
    <text x="${L}" y="${T + 2}" font-size="11" fill="#64748b">gCO₂e/MJ (WtW)</text></svg>`;
}

async function loadRules(latestOpx) {
  const r = await (await fetch('/api/rules')).json();
  $('#rules-chart').innerHTML = rulesChart(r) + `<div class="legend"><span><i style="background:#e2e8f0"></i>한도 (91.16에서 단계 감축)</span><span><i style="background:#f97316"></i>석유 연료 (점선)</span><span><i style="background:#38bdf8"></i>LNG 엔진별 (실선, 메탄 슬립 차이)</span><span>점 = 부족으로 바뀌는 해 · 오른쪽 숫자 = 집약도 · 전환 연도</span></div>
    <p class="note">총량 한도(cap)가 없습니다. EU ETS와 달리 FuelEU는 선박마다 1MJ당 배출 한도만 정하고, 선종·크기와 상관없이 같습니다. 한도보다 깨끗한 연료를 쓴 만큼 잉여가 생기므로 시장 공급량은 정해져 있지 않습니다.</p>`;
  const hfo = r.fuels.find(f => f.key === 'hfo');
  $('#rules-side').innerHTML = `
    <div><h2 style="font-size:14px;margin-bottom:8px">가격의 위아래 범위</h2><div class="table-wrap"><table><tbody>
      <tr><td>상한: 부담금 환산 (HFO 선박)</td><td class="num">${eur(hfo.penalty_eur_per_tco2e)}/tCO₂e</td></tr>
      <tr><td>현재 OPX</td><td class="num">${latestOpx != null ? `${eur(latestOpx, 2)} (상한의 ${fmt(latestOpx / hfo.penalty_eur_per_tco2e * 100, 0)}%)` : '수집 전'}</td></tr>
      <tr><td>하한: 이미 지은 LNG선의 잉여</td><td class="num">추가 비용 거의 0</td></tr>
      <tr><td>그 사이: 바이오연료 혼합으로 잉여를 만드는 비용</td><td class="num">시장 가격을 정하는 쪽</td></tr>
    </tbody></table></div>
    <p class="note">부담금 = |부족분| ÷ (실제 집약도 × 41,000 MJ) × €2,400. 연속 미준수 시 1 + (n−1)/10 배.</p></div>
    <div><h2 style="font-size:14px;margin-bottom:8px">보고기간 다음 해의 일정 (원문 확인분)</h2><div class="table-wrap"><table><tbody>
      <tr><td>4월 30일까지</td><td>차입분 등록 (제20조(3))</td></tr>
      <tr><td>5월 1일 전</td><td>풀링·이월·차입 반영 후 검증 잔액 기록 (제23조(1))</td></tr>
      <tr><td>6월 30일까지</td><td>부족 선박 부담금 납부 (제23조(2))</td></tr>
    </tbody></table></div>
    <p class="note">2025년이 첫 보고기간이라 첫 풀링 마감은 2026년 4월이었습니다. 그래서 풀 가격은 매년 봄 마감 전 수요가 몰리고 그 뒤 새 연도 잉여로 넘어갑니다.</p></div>`;
}

// ------------------------------------------------------------ 3 supply

const PROP = { oil: '석유 연료선', lng: 'LNG 추진선' };
const TYPE_KO = { 'Container ship': '컨테이너선', 'Bulk carrier': '벌크선', 'Oil tanker': '유조선', 'Chemical tanker': '케미컬 탱커', 'General cargo ship': '일반화물선',
  'LNG carrier': 'LNG 운반선', 'Gas carrier': '가스 운반선', 'Vehicle carrier': '자동차 운반선', 'Ro-pax ship': '로팩스', 'Ro-ro ship': '로로선', 'Passenger ship': '여객선', 'Passenger ship (Cruise Passenger ship)': '크루즈선',
  'Container/ro-ro cargo ship': '컨테이너·로로선', 'Refrigerated cargo carrier': '냉동선', 'Combination carrier': '겸용선', 'Other ship types': '기타', 'Other ship types (Offshore)': '기타(해양작업)', 'Combined gas/LNG carrier': '가스·LNG 겸용' };
const kt = v => `${fmt(v / 1000, 0)}천 t`;

function supplyView(data, year, target) {
  const d = data[year], prev = data[String(Number(year) - 1)];
  const t = d.total, lng = d.by_propulsion.lng || {}, oil = d.by_propulsion.oil || {};
  const types = Object.entries(d.by_ship_type).filter(([, v]) => v.ships >= 20).slice(0, 12);
  const max = Math.max(...types.map(([, v]) => Math.max(v[`surplus_${target}`], v[`deficit_${target}`])), 1);
  const rows = types.map(([k, v]) => {
    const s = v[`surplus_${target}`], df = v[`deficit_${target}`];
    return `<tr><td>${esc(TYPE_KO[k] || k)}</td><td class="num">${fmt(v.ships)}</td>
      <td style="width:28%;text-align:right"><span class="bar" style="width:${df / max * 100}%;background:#ef4444aa"></span></td>
      <td style="width:28%"><span class="bar" style="width:${s / max * 100}%;background:#22c55eaa"></span></td>
      <td class="num">${kt(-df)}</td><td class="num">${kt(s)}</td><td class="num">${fmt(v[`surplus_ships_${target}`])}</td></tr>`;
  }).join('');
  const lngPrev = prev?.by_propulsion?.lng;
  return `
    <div class="kpis">
      ${kpi(`LNG 추진선 (${year})`, `${fmt(lng.ships)}척`, lngPrev ? `${Number(year) - 1}년 ${fmt(lngPrev.ships)}척 → ${fmt((lng.ships / lngPrev.ships - 1) * 100, 0)}% 증가` : '', 'pos')}
      ${kpi(`잉여 추정 (${target} 한도)`, kt(t[`surplus_${target}`]), `${fmt(t[`surplus_ships_${target}`])}척이 한도보다 깨끗함`, 'pos')}
      ${kpi(`부족 추정 (${target} 한도)`, kt(t[`deficit_${target}`]), `석유선 평균 ${fmt(oil.avg_intensity, 2)} gCO₂e/MJ`, 'neg')}
      ${kpi('장부상 순수급', kt(t[`net_${target}`]), '잉여 − 부족 · 바이오 혼합 제외', t[`net_${target}`] < 0 ? 'neg' : 'pos')}
    </div>
    <p class="warn">해석: 석유선의 구조적 부족이 LNG선 잉여보다 큽니다. 그런데도 시장 해설은 "공급이 수요를 넘는다"고 하고 가격은 내려갑니다. 차이는 바이오연료 혼합과 "필요할 때 만드는" 잉여가 메웁니다. 그래서 풀 가격은 LNG 잉여량보다 바이오 혼합으로 잉여를 만드는 비용에 끌려갑니다. 2030년 한도(−6%)가 오면 부족이 약 ${fmt(t.deficit_2030 / t.deficit_2025, 1)}배로 커집니다.</p>
    <div class="legend"><span><i style="background:#ef4444aa"></i>부족 (풀에서 사야 하는 양)</span><span><i style="background:#22c55eaa"></i>잉여 (풀에 팔 수 있는 양)</span></div>
    <div class="table-wrap"><table><thead><tr><th>선종</th><th class="num">척수</th><th class="num">부족</th><th>잉여</th><th class="num">부족 t</th><th class="num">잉여 t</th><th class="num">잉여 선박</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="grid2">
      <div><h2 style="font-size:14px;margin-bottom:8px">추진 연료별</h2><div class="table-wrap"><table><thead><tr><th>구분</th><th class="num">척수</th><th class="num">평균 집약도</th><th class="num">2025 한도 순</th><th class="num">2030 한도 순</th></tr></thead><tbody>
        ${Object.entries(d.by_propulsion).map(([k, v]) => `<tr><td>${esc(PROP[k] || k)}</td><td class="num">${fmt(v.ships)}</td><td class="num">${fmt(v.avg_intensity, 2)}</td><td class="num">${kt(v.net_2025)}</td><td class="num">${kt(v.net_2030)}</td></tr>`).join('')}
        <tr><td>바이오 혼합 추정 (계산 제외)</td><td class="num">${fmt(d.unestimated.bio_blend_suspected || 0)}</td><td colspan="3">MRV에 바이오 WtW 혜택이 없어 추정 불가</td></tr>
        <tr><td>메탄올·기타 (계산 제외)</td><td class="num">${fmt(d.unestimated.other || 0)}</td><td colspan="3"></td></tr>
      </tbody></table></div></div>
      <div><h2 style="font-size:14px;margin-bottom:8px">이 추정의 한계</h2><ul class="note" style="padding-left:18px;margin:0">
        <li>공식 FuelEU 잔액이 아닙니다. FuelEU 데이터베이스는 비공개입니다.</li>
        <li>MRV에 총톤수가 없어 5,000 GT 이하 선박(2025년부터 MRV에 일부 포함)을 걸러내지 못했습니다. 부족이 과대 추정될 수 있습니다.</li>
        <li>바이오 혼합 선박은 빠져 있어 잉여는 과소 추정입니다.</li>
        <li>최외곽지역 항해(FuelEU 50%)가 EU 역내(100%)에 섞여 있습니다. 풍력·육상전원 보정, 이미 맺은 풀링은 반영하지 않았습니다.</li>
        <li>${year === '2024' ? '2024년은 FuelEU 시행 전 해라 구조 비교용입니다.' : `연료량·배출이 없는 보고서 ${fmt(d.skipped)}건은 제외했습니다.`}</li>
      </ul></div>
    </div>`;
}

async function loadSupply() {
  const data = await (await fetch('/api/supply')).json();
  if (data.status === 'missing') {
    $('#supply-body').innerHTML = `<p class="warn">MRV 추정 자료가 없습니다. <code>${esc(data.hint)}</code> 를 실행하세요.</p>`;
    return;
  }
  const years = Object.keys(data).sort().reverse();
  $('#supply-meta').innerHTML = `EMSA MRV 공개 자료 (선박별 연간 연료·CO₂·CH₄·N₂O) · 버전 ${esc(years.map(y => `${y} v${data[y].source_version ?? '로컬'}`).join(', '))}<br>
    <label>보고연도 <select id="s-year">${years.map(y => `<option>${y}</option>`).join('')}</select></label>
    <label>적용 한도 <select id="s-target"><option>2025</option><option>2030</option><option>2035</option></select></label>`;
  const draw = () => { $('#supply-body').innerHTML = supplyView(data, $('#s-year').value, $('#s-target').value); };
  $('#supply-meta').addEventListener('change', draw);
  draw();
}

async function quickCheck() {
  const v = id => $(id).value;
  const body = { gross_tonnage: v('#q-gt'), intra_eu_pct: v('#q-intra'), at_berth_pct: v('#q-berth'), pool_price: $('#pool').value,
    fuels: { [v('#q-f1')]: v('#q-t1'), ...(v('#q-f2') ? { [v('#q-f2')]: v('#q-t2') } : {}) } };
  const res = await fetch('/api/quick', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const r = await res.json();
  if (!res.ok) { $('#q-out').innerHTML = `<p class="warn">${esc(r.error)}</p>`; return; }
  if (!r.in_scope) { $('#q-out').innerHTML = `<p class="warn">${esc(r.reason)}</p>`; return; }
  const surplus = r.position === 'surplus';
  $('#q-out').innerHTML = `<div class="kpis" style="margin-top:14px">
      ${kpi('판정 (2025–2029)', surplus ? '잉여 선박' : '부족 선박', surplus ? '풀에 팔 수 있는 쪽' : '풀에서 사야 하는 쪽', surplus ? 'pos' : 'neg')}
      ${kpi('집약도 vs 한도', `${fmt(r.ghg_intensity, 2)} / ${fmt(r.target, 2)}`, `여유 ${fmt(r.margin_gco2e_per_mj, 2)} gCO₂e/MJ`)}
      ${kpi('연간 준수 잔액', `${fmt(r.compliance_balance_tco2e, 0)} tCO₂e`, r.value_at_pool_eur != null ? `풀 가격 기준 ${eur(r.value_at_pool_eur)}` : '')}
      ${kpi('부족으로 바뀌는 시점', r.first_deficit_period ?? '2050년까지 없음', '같은 연료·운항을 유지할 때')}
    </div>
    <div class="table-wrap"><table><thead><tr><th>적용 기간</th><th class="num">한도</th><th class="num">잔액 (tCO₂e)</th><th>판정</th><th class="num">미조치 시 부담금</th></tr></thead><tbody>
    ${r.timeline.map(t => `<tr><td>${t.from_year}~</td><td class="num">${fmt(t.target, 2)}</td><td class="num">${fmt(t.compliance_balance_tco2e, 0)}</td><td>${t.position === 'surplus' ? '잉여' : '부족'}</td><td class="num">${t.penalty_eur ? eur(t.penalty_eur) : '—'}</td></tr>`).join('')}
    </tbody></table></div>
    <p class="note">LNG는 엔진 종류(메탄 슬립)에 따라 결과가 크게 달라집니다. 바이오·e-연료는 인증 배출계수가 필요해 이 빠른 판정에서는 뺐습니다.</p>`;
}

fuels = await (await fetch('/api/fuels')).json();
example = await (await fetch('/api/example')).json();
const latest = await loadMarket();
loadRules(latest);
loadSupply();
$('#pool').value = latest ?? '';
if (latest == null) $('#pool').placeholder = '가격 직접 입력';
document.addEventListener('change', e => { if (e.target.closest('#voyages')) run(); });
$('#legs').addEventListener('click', e => { if (e.target.classList.contains('del')) { e.target.closest('tr').remove(); run(); } });
$('#add').onclick = () => { legs = readLegs(); legs.push({ id: `L${legs.length + 1}`, status: 'planned', origin: { country: 'NL' }, destination: { country: 'NL' }, at_sea: { mdo_mgo: 100 }, at_berth: {} }); drawLegs(); run(); };
$('#reset').onclick = reset;
$('#q-f1').innerHTML = fuelSelect('lng_otto_ss', '').replace(/^<select class="">|<\/select>$/g, '');
$('#q-f2').innerHTML = fuelSelect('mdo_mgo', '').replace(/^<select class="">|<\/select>$/g, '');
$('#quick').addEventListener('change', quickCheck);
quickCheck();
reset();
