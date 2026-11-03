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
$('#pool').value = latest ?? '';
if (latest == null) $('#pool').placeholder = '가격 직접 입력';
document.addEventListener('change', e => { if (e.target.closest('main') && !e.target.closest('#market, #quick')) run(); });
$('#legs').addEventListener('click', e => { if (e.target.classList.contains('del')) { e.target.closest('tr').remove(); run(); } });
$('#add').onclick = () => { legs = readLegs(); legs.push({ id: `L${legs.length + 1}`, status: 'planned', origin: { country: 'NL' }, destination: { country: 'NL' }, at_sea: { mdo_mgo: 100 }, at_berth: {} }); drawLegs(); run(); };
$('#reset').onclick = reset;
$('#q-f1').innerHTML = fuelSelect('lng_otto_ss', '').replace(/^<select class="">|<\/select>$/g, '');
$('#q-f2').innerHTML = fuelSelect('mdo_mgo', '').replace(/^<select class="">|<\/select>$/g, '');
$('#quick').addEventListener('change', quickCheck);
quickCheck();
reset();
