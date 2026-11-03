const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = v => v == null ? '미확보' : Number(v).toLocaleString('ko-KR', {maximumFractionDigits: 2});
function mode(scenario) {
  $('#scenario-inputs').hidden = !scenario;
  $('#scenario-results').hidden = !scenario;
  $('#observed-view').hidden = scenario;
  $('#observed-mode').setAttribute('aria-pressed', String(!scenario));
  $('#scenario-mode').setAttribute('aria-pressed', String(scenario));
  $('#mode-label').textContent = scenario ? '가상 계약·교육용 시나리오' : '공개 관측자료 · 부족 항목은 미확보';
}
$('#observed-mode').onclick = () => mode(false);
$('#scenario-mode').onclick = () => mode(true);
async function load() {
  const response = await fetch('/api/observations');
  if (!response.ok) throw Error('관측자료를 불러오지 못했습니다');
  const data = await response.json();
  const sources = data.prices.sources ?? {};
  const cards = Object.entries(sources).map(([key, s]) => {
    const rows = s.latest_observations ?? [];
    return `<section class="panel"><h2>${key === 'eex_eua_auction' ? 'EUA 경매 낙찰가' : 'ECB 원화/유로 참고환율'}</h2>
      <p>자료 상태: ${esc(s.status)} · 관측일 ${esc(s.latest_observation_date ?? rows[0]?.observation_date ?? '미확보')} · 수집 기준일 ${esc(data.prices.as_of)}</p>
      ${rows.map(r => `<div class="metric"><span>${esc(r.auction_name ?? 'KRW per EUR')}</span><strong>${fmt(r.price)} ${esc(s.unit)}</strong><small>${esc(r.observation_date)}${r.auction_volume_tco2 ? ' · 경매 물량 ' + fmt(r.auction_volume_tco2) + ' tCO₂' : ''}</small></div>`).join('')}
      <p>수집 기록 ${fmt(s.count)}건. ${key === 'eex_eua_auction' ? '실시간 현물·선물 체결가격과 다릅니다.' : '거래용 환율과 다릅니다.'}</p>
      <p><a href="${esc(s.source_url)}" target="_blank" rel="noreferrer">공식 출처</a></p></section>`;
  }).join('');
  const v = data.vessels;
  const records = v.records ?? [];
  $('#observed-view').innerHTML = `<h2>${Object.values(sources).some(s => s.status === 'synthetic') ? '합성 샘플 — 실데이터 아님' : '실제 관측자료'}</h2><p>가상 포지션의 손익을 실적처럼 표시하지 않습니다. 아래는 수집한 원본의 가격·환율·선박 자료입니다.</p>
    ${cards || '<section class="panel">가격 수집 파일이 없습니다. collect_prices.py로 수집하면 표시됩니다. 가상 가격으로 자동 대체하지 않습니다.</section>'}
    <section class="panel"><h2>공개 선박 배출량</h2><p>자료 상태 ${esc(v.status)} · full ${fmt(v.counts_by_scope?.full)}, partial ${fmt(v.counts_by_scope?.partial)} · 보고연도 ${esc(v.reporting_year ?? '미확인')} · ${fmt(v.count ?? records.length)}건</p>
    <p>공식 파일 버전 ${esc(v.version ?? '미확인')} · 파일 생성 표기 ${esc(v.generation_date_source ?? '미확인')}. 연간 보고와 부분기간 보고를 합산해 선박 연간 총량으로 만들지 않습니다.</p><label>선박 이름·IMO 검색<input id="vessel-search" type="search" placeholder="선박 이름 또는 IMO"></label><div id="vessel-rows"></div>
    <p>과거 보고연도 배출량은 현재 항차 배출량이나 2026년 제출 의무의 확정값이 아닙니다. 선박 연간 MRV 총량에 항로비중을 다시 일괄 적용하지 않습니다.</p>
    <a href="https://mrv.emsa.europa.eu/#public/emission-report" target="_blank" rel="noreferrer">EMSA 공개 MRV</a></section>
    <section class="panel"><h2>다음에 확보할 입력</h2><div class="table-wrap"><table><tr><th>항목</th><th>현재 상태</th><th>확보 방법</th></tr>
    <tr><td>거래소·만기별 선물 결제가격</td><td>미확보</td><td>이용권한 있는 데이터 또는 계약별 업로드</td></tr>
    <tr><td>선사 배출권 보유·계약 인도량</td><td>미확보</td><td>선사 자료·등록부 계정 내역</td></tr>
    <tr><td>금융사 포지션·IM/VM</td><td>미확보</td><td>내부 포지션·브로커 명세</td></tr>
    <tr><td>FuelEU 연료 인증·풀링 견적</td><td>미확보</td><td>검증자료·공급 견적</td></tr></table></div><p>이 값들이 없으면 실제 기업의 조달 부족량·손익·최대 자금소요를 확정할 수 없습니다. 가상 시나리오는 상단에서 별도로 열 수 있습니다.</p></section>`;
  function showVessels() {
    const q = $('#vessel-search').value.toLowerCase();
    const selected = records.filter(r => `${r.name} ${r.imo}`.toLowerCase().includes(q));
    $('#vessel-rows').innerHTML = `<p>검색 ${selected.length}건 · 처음 50건 표시</p><div class="table-wrap"><table><tr><th>IMO</th><th>선박</th><th>선종</th><th>보고 구분</th><th>MRV CO₂ (t)</th><th>ETS 보고 CO₂ (t)</th><th>DoC 발행</th></tr>${selected.slice(0,50).map(r => `<tr><td>${esc(r.imo)}</td><td>${esc(r.name)}</td><td>${esc(r.ship_type)}</td><td>${esc(r.report_scope)}</td><td>${fmt(r.total_co2_t)}</td><td>${fmt(r.ets_reported_co2_t)}</td><td>${esc(r.doc_issue_date)}</td></tr>`).join('')}</table></div>`;
  }
  $('#vessel-search').value = records.some(r => String(r.name).includes('HMM')) ? 'HMM' : '';
  $('#vessel-search').oninput = showVessels; showVessels();
}
load().catch(e => { $('#observed-view').textContent = e.message; });
