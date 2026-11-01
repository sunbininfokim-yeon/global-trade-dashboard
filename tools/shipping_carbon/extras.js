const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));
const fmt = (v, unit = '') => v == null ? '미확인' :
  `${Number(v).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}${unit ? ' ' + unit : ''}`;
const metric = (title, value, note = '') =>
  `<div class="metric"><span>${esc(title)}</span><strong>${esc(fmt(value, 'EUR'))}</strong><small>${esc(note)}</small></div>`;
const table = (heads, rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
let exportData = null;
const eventLabels = {
  initial_margin_post: 'IM 납입', initial_margin_release: 'IM 반환',
  variation_margin: 'VM 정산', physical_future_payment: '선물 실물 대금',
  replacement_purchase: '보충 실물 매입', customer_receipt: '고객 수금', fees: '수수료'
};

function fundingChart(f) {
  if (f.status !== 'scenario' || !f.days.length) return '<p>필수 자금 입력을 완료하면 일말 자금 경로를 표시합니다.</p>';
  const max = Math.max(1, ...f.days.map(x => Number(x.funding_gap_eur)));
  const start = Date.parse(f.days[0].date), span = Math.max(1, Date.parse(f.days.at(-1).date) - start);
  const coords = f.days.map(x => ({x: 50 + 620 * (Date.parse(x.date) - start) / span,
    y: 160 - 120 * Number(x.funding_gap_eur) / max, label: x.date + ': ' + fmt(x.funding_gap_eur, 'EUR')}));
  const points = coords.flatMap((p, i) => i ? [`${p.x},${coords[i-1].y}`, `${p.x},${p.y}`] : [`${p.x},${p.y}`]);
  return `<svg class="funding-chart" viewBox="0 0 730 210" role="img" aria-label="날짜별 일말 추가 조달 필요액, 이벤트일 계단 표시"><line x1="50" y1="160" x2="670" y2="160" stroke="#577089"/><polyline fill="none" stroke="#61d9c1" stroke-width="3" points="${points.join(' ')}"/>${coords.map(p => `<circle cx="${p.x}" cy="${p.y}" r="4" fill="#61d9c1"><title>${esc(p.label)}</title></circle>`).join('')}<text x="50" y="25" fill="#b8c8da">최대 ${esc(fmt(max, 'EUR'))}</text><text x="50" y="190" fill="#b8c8da">${esc(f.days[0].date)}</text><text x="670" y="190" text-anchor="end" fill="#b8c8da">${esc(f.days.at(-1).date)}</text></svg>`;
}

export function invalidateExport() {
  exportData = null;
  $('#export').disabled = true;
}

export function renderExtras(r, inputs) {
  const d = r.dealer, f = d.funding;
  $('#ship-view').insertAdjacentHTML('beforeend', `<section class="panel"><h2>금융사 공급계약 대금 가정</h2>
    <p>${esc(fmt(r.shipowner.customer_contract_payment_eur, 'EUR'))} · 추가 조달량 × 고객 고정 공급가격입니다. 경매 참고 예산과 구분합니다.</p>
    <p>고객 인도일 ${esc(inputs.customer_delivery_date)}, 지급일 ${esc(inputs.customer_payment_date)}. 이 거래 외 기존 계약의 지급금은 포함하지 않습니다.</p></section>`);
  $('#dealer-view').insertAdjacentHTML('beforeend', `<section class="panel" id="comparison-panel"><h2>헤지 비율별 가격위험과 VM</h2>
    <p>선물 충격 ${esc(fmt(d.hedge_shock_eur, 'EUR/EUA'))}, 그중 추가 충격 ${esc(fmt(d.basis_shock_eur, 'EUR/EUA'))}. 계약 수는 1,000 EUA 단위로 올림합니다.</p>
    ${table(['헤지 목표', 'lot', '잔여 델타 (EUA)', '순손익 (EUR)', 'VM 유출 (EUR)'], d.hedge_comparison.map(x => [x.label, fmt(x.lots), fmt(x.residual_delta_eua), fmt(x.net_shock_pnl_eur), fmt(x.vm_outflow_eur)]))}
    <p>추가 충격이 있으면 합산 델타가 0이어도 손익이 남습니다. 이 표는 최적전략 판정이 아닙니다.</p></section>
    <section class="panel" id="funding-panel"><h2>계약 일정과 추가 자금</h2><div class="cards">
    ${metric('계약 일정상 최대 추가자금', f.peak_funding_gap_eur, '일말 잔액 · IM·실물 지급·고객수금·수수료·차입비용')}
    ${metric('비용 반영 기여이익 가정', f.net_contribution_eur, '일치 수량·기한 내 인도 시 계산 · 신용/자본비용·세금 제외')}
    </div><p>계산 상태: ${esc(f.status)}${f.missing_inputs.length ? ' · 미입력: ' + esc(f.missing_inputs.map(k => eventLabels[k] ?? k).join(', ')) : ''}</p>
    ${fundingChart(f)}
    ${table(['날짜 / 내역', '유입·유출 (EUR)', '차입비용 (EUR)', '일말 현금 (EUR)', '추가자금 (EUR)'], f.days.map(x => [x.date + ' / ' + x.kinds.map(k => eventLabels[k] ?? k).join(', '), fmt(x.flow_eur), fmt(x.financing_eur), fmt(x.closing_cash_eur), fmt(x.funding_gap_eur)]))}
    <p>${f.status === 'partial' ? '표는 확인된 항목만 합산한 부분 경로입니다. 전체 최대자금·기여이익은 미확인으로 유지합니다.' : '현금 여유를 먼저 사용하고 음수 일말 잔액을 추가 차입으로 가정합니다. 실제 달력일/365 단리로 다음 이벤트일까지 이자를 계산하며 비용은 잔액에 반영합니다.'}</p>
    <p>차입비용 합계 ${esc(fmt(f.financing_cost_eur, 'EUR'))}, 원가 대비 공급 차액 ${esc(fmt(f.gross_spread_eur, 'EUR'))}.</p>
    <p>고객 인도일의 보충 실물 ${esc(fmt(f.replacement_eua, 'EUA'))}, 고객에게 배정되지 않는 선물 인수량 ${esc(fmt(f.residual_inventory_eua, 'EUA'))}. 잔여 재고의 평가이익을 확정 수익에 더하지 않습니다.</p>
    <p>VM과 실물 인수대금을 함께 반영하며 VM을 다시 손익에 가산하지 않습니다. 동일 날짜의 유입·유출은 일말에 합산하며 장중 자금 피크는 포함하지 않습니다.</p></section>`);
  exportData = { schema: 'shipping_carbon_export_v1', generated_at: new Date().toISOString(), inputs, result: r };
  $('#export').disabled = false;
}

$('#export').onclick = () => {
  if (!exportData) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = 'shipping-carbon-scenario.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
