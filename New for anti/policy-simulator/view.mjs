import { example, simulate, MODEL_VERSION, SOURCES } from './country-model.mjs';

const COUNTRIES = { USA: '미국', KOR: '한국', CHN: '중국', JPN: '일본', VNM: '베트남', MEX: '멕시코',
  CAN: '캐나다', IND: '인도', DEU: '독일', FRA: '프랑스', GBR: '영국', TWN: '대만', BRA: '브라질', ROW: '기타국 합계' };
const PRODUCTS = { transformer: '전력용 변압기', cable: '전력 케이블', switchgear: '차단기·배전기기',
  semiconductor: '반도체', vehicle: '자동차', tire: '타이어', fiber: '산업용 섬유', custom: '직접 정의한 품목' };
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, places = 2) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: places, maximumFractionDigits: places });
const signed = v => `${v > 0.00001 ? '+' : ''}${fmt(Math.abs(v) < 0.00001 ? 0 : v)}`;
const name = code => COUNTRIES[code] || code;
const options = (values, selected) => Object.entries(values).map(([key, label]) => `<option value="${key}"${key === selected ? ' selected' : ''}>${esc(label)}</option>`).join('');
let draft = example(), result = simulate(draft), dirty = false, error = '';
let stylePromise;

export function prepare() {
  if (!stylePromise) stylePromise = new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = new URL('./style.css?v=1', import.meta.url).href;
    link.onload = resolve;
    link.onerror = () => { link.remove(); stylePromise = null; reject(new Error('시뮬레이터 스타일을 불러오지 못했습니다.')); };
    document.head.appendChild(link);
  });
  return stylePromise;
}

function numberInput(value, attrs) {
  return `<input type="number" inputmode="decimal" step="any" value="${esc(value)}" ${attrs} required>`;
}
function editor() {
  const focusChoices = Object.fromEntries(draft.rows.filter(row => !['USA', 'ROW'].includes(row.country)).map(row => [row.country, name(row.country)]));
  return `<form data-sim-form>
    <div class="ts-fields">
      <label>분석 품목<select data-key="product" aria-label="분석 품목">${options(PRODUCTS, draft.product)}</select></label>
      <label>관심 공급국<select data-key="focus" aria-label="관심 공급국">${options(focusChoices, draft.focus)}</select></label>
      <label class="ts-wide">기준 기간<input data-key="period" aria-label="기준 기간" value="${esc(draft.period)}" maxlength="80" required></label>
    </div>
    <div class="ts-section-label"><h3>공급국과 관세 가정</h3><span>구매액 단위: 백만 달러</span></div>
    <div class="ts-scroll"><table class="ts-input-table"><caption class="ts-sr">같은 품목·기간·관세 포함 구매액을 입력하세요.</caption>
      <thead><tr><th>공급국</th><th>기준 구매액</th><th>기존 관세 %</th><th>가정 관세 %</th><th>공급탄력성</th><th><span class="ts-sr">제거</span></th></tr></thead>
      <tbody>${draft.rows.map((row, i) => {
        const countries = Object.fromEntries(Object.entries(COUNTRIES).filter(([key]) => key === row.country || !draft.rows.some(r => r.country === key)));
        return `<tr${row.country === draft.focus ? ' class="ts-focus-row"' : ''}>
          <td><select data-row="${i}" data-field="country" aria-label="공급국 ${i + 1}">${options(countries, row.country)}</select></td>
          <td>${numberInput(row.expenditure, `data-row="${i}" data-field="expenditure" min="0.000001" max="1000000000" aria-label="${name(row.country)} 기준 구매액"`)}</td>
          <td>${numberInput(row.tariff_before, `data-row="${i}" data-field="tariff_before" min="0" max="300" aria-label="${name(row.country)} 기존 관세"${row.country === 'USA' ? ' readonly' : ''}`)}</td>
          <td>${numberInput(row.tariff_after, `data-row="${i}" data-field="tariff_after" min="0" max="300" aria-label="${name(row.country)} 가정 관세"${row.country === 'USA' ? ' readonly' : ''}`)}</td>
          <td>${numberInput(row.supply_elasticity, `data-row="${i}" data-field="supply_elasticity" min="0" max="100" aria-label="${name(row.country)} 공급탄력성"`)}</td>
          <td><button type="button" class="ts-remove" data-remove="${i}" aria-label="${name(row.country)} 제거"${draft.rows.length <= 2 ? ' disabled' : ''}>×</button></td>
        </tr>`;
      }).join('')}</tbody></table></div>
    <p class="ts-mobile-hint">표를 좌우로 밀면 공급탄력성·제거 열도 볼 수 있습니다.</p>
    <button type="button" class="ts-text-button" data-add${draft.rows.length >= 8 ? ' disabled' : ''}>+ 공급국 추가 <span>최대 8개</span></button>
    <p class="ts-help">구매액은 미국 구매자가 지출한 관세 포함 금액입니다. 국가를 추가하면 ‘기타국 합계’에서 해당 국가를 빼서 중복을 피하세요. 구매액 0인 공급국은 제거하세요.</p>
    <div class="ts-fields ts-elasticities">
      <label>대체탄력성 σ ${numberInput(draft.sigma, 'data-key="sigma" aria-label="대체탄력성" min="0.1" max="20" aria-describedby="ts-sigma-help"')}<small id="ts-sigma-help">클수록 다른 공급국으로 쉽게 전환</small></label>
      <label>시장 수요탄력성 η ${numberInput(draft.eta, 'data-key="eta" aria-label="시장 수요탄력성" min="-10" max="-0.05" aria-describedby="ts-eta-help"')}<small id="ts-eta-help">음수 · 절댓값이 클수록 가격에 민감</small></label>
    </div>
    <details class="ts-explainer"><summary>탄력성과 관세율은 어떻게 입력하나요?</summary>
      <p>공급탄력성은 생산자가격 변화에 대한 공급량 반응입니다. 0은 생산량 고정, 값이 크면 공급 확대가 쉽다는 가정입니다. 자동 추정값이 아닙니다.</p>
      <p>기존 10%, 가정 30%이면 구매가격의 관세 인자는 1.30 ÷ 1.10입니다. 입력한 관세율은 적용 가능성을 검토한 종가세 시나리오이며, 정책 카드의 문장을 숫자로 변환하지 않습니다.</p>
      <p>제품을 바꿔도 구매액과 탄력성은 실제 산업 자료로 바뀌지 않습니다. 같은 품목 범위와 기간으로 다시 보정하세요. DataWeb의 통관가액은 국내 출하·관세·유통 마진을 맞추기 전에는 이 구매액과 다릅니다.</p>
    </details>
    <label class="ts-source-label">입력 자료·가정 메모<textarea data-key="source_note" aria-label="입력 자료·가정 메모" maxlength="1000" rows="2">${esc(draft.source_note)}</textarea></label>
    <div class="ts-actions"><button class="ts-primary" type="submit">시나리오 계산 <span aria-hidden="true">→</span></button><button type="button" data-reset>가상 예시로 초기화</button></div>
    <p class="ts-error" role="alert" data-sim-error${error ? '' : ' hidden'}>${esc(error)}</p>
  </form>`;
}

function results() {
  const r = result, focus = r.rows.find(row => row.country === r.inputs.focus);
  const country = name(focus.country), input = r.inputs.rows.find(row => row.country === focus.country);
  return `<div class="ts-result-heading"><div><span class="ts-eyebrow">조건부 시뮬레이션 · 가정값</span><h2>${esc(country)} 공급에 미치는 영향</h2>
    <p>${esc(PRODUCTS[r.inputs.product] || r.inputs.product)} · ${esc(r.inputs.period)} · 관세 ${fmt(input.tariff_before, 1)}% → ${fmt(input.tariff_after, 1)}%</p></div>
    <button type="button" class="ts-export" data-export${dirty ? ' disabled' : ''}>결과 JSON 저장</button></div>
    <p class="ts-stale" data-stale role="status"${dirty ? '' : ' hidden'}>입력이 바뀌었습니다. 아래는 이전 계산 결과입니다. 다시 계산하세요.</p>
    <div class="ts-calculated${dirty ? ' is-stale' : ''}" data-calculated>
      <div class="ts-kpis">
        <div><span>${esc(country)} 판매량</span><strong class="${focus.volume_change_pct < 0 ? 'ts-down' : 'ts-up'}">${signed(focus.volume_change_pct)}<small>%</small></strong><small>미국 시장 내 물량 변화</small></div>
        <div><span>${esc(country)} 공급자 매출</span><strong>${signed(focus.revenue_change_pct)}<small>%</small></strong><small>관세 제외 · 기업 이익 아님</small></div>
        <div><span>미국 시장 가격지수</span><strong>${signed(r.market_price_change_pct)}<small>%</small></strong><small>해당 품목의 구매가격</small></div>
      </div>
      <section class="ts-result-block"><div class="ts-section-label"><h3>공급은 어디로 이동하나요?</h3><span>국가별 판매량 변화</span></div>
        <div class="ts-bars">${r.rows.map(row => {
          const change = row.volume_change_pct, max = Math.max(1, ...r.rows.map(x => Math.abs(x.volume_change_pct)));
          return `<div class="ts-bar-row"><span>${esc(name(row.country))}</span><div class="ts-bar-track"><span class="ts-zero"></span><i class="${change < 0 ? 'ts-negative' : 'ts-positive'}" style="width:${Math.abs(change) / max * 48}%;${change < 0 ? `right:50%` : 'left:50%'}"></i></div><b>${signed(change)}%</b></div>`;
        }).join('')}</div>
        <p class="ts-help">가격 상승에 따른 수요 감소와 공급국 전환을 함께 계산합니다. 톤·대수처럼 다른 물리 단위를 합치지는 않습니다.</p>
      </section>
      <section class="ts-result-block"><h3>가격·점유율·매출 비교</h3><div class="ts-scroll"><table class="ts-output-table"><caption class="ts-sr">기준 대비 변화. 매출 단위는 백만 달러입니다.</caption>
        <thead><tr><th>공급국</th><th>구매가격</th><th>생산자가격</th><th>구매액 점유율</th><th>관세 제외 매출<br><small>백만 달러</small></th></tr></thead>
        <tbody>${r.rows.map(row => `<tr${row.country === r.inputs.focus ? ' class="ts-focus-row"' : ''}><th>${esc(name(row.country))}</th>
          <td>${signed(row.price_change_pct)}%</td><td>${signed(row.producer_price_change_pct)}%</td>
          <td>${fmt(row.share_before_pct, 1)} → ${fmt(row.share_after_pct, 1)}%<small>${signed(row.share_change_pp)}%p</small></td>
          <td>${fmt(row.revenue_before)} → ${fmt(row.revenue_after)}</td></tr>`).join('')}</tbody></table></div>
        <p class="ts-help">생산자가격은 관세를 제외한 가격입니다. 수출자가 가격을 낮춰 관세 부담 일부를 흡수할 수 있습니다.</p>
      </section>
      <section class="ts-result-block"><div class="ts-section-label"><h3>다른 가정이면 얼마나 달라지나요?</h3><span>대체탄력성만 변경</span></div>
        <div class="ts-sensitivity">${r.sensitivity.map(s => `<div${s.sigma === r.inputs.sigma ? ' class="is-selected"' : ''}><span>σ = ${fmt(s.sigma, 1)}${s.sigma === r.inputs.sigma ? ' · 입력값' : ''}</span>
          ${s.status === 'calculated' ? `<strong>${signed(s.volume_change_pct)}%</strong><small>${esc(country)} 판매량</small>` : '<strong>계산 불가</strong>'}</div>`).join('')}</div>
        <p class="ts-help">가능한 가정을 비교한 값입니다. 발생 확률이나 통계적 신뢰구간이 아닙니다.</p>
      </section>
      <details class="ts-explainer ts-market-totals"><summary>미국 전체 품목시장·관세수입 보기</summary>
        <dl><div><dt>CES 집계 수량지수 변화</dt><dd>${signed(r.market_quantity_change_pct)}%</dd></div>
          <div><dt>관세 포함 전체 구매액</dt><dd>${fmt(r.spending_before)} → ${fmt(r.spending_after)} 백만 달러</dd></div>
          <div><dt>미국 관세수입</dt><dd>${fmt(r.duties_before)} → ${fmt(r.duties_after)} 백만 달러</dd></div></dl>
        <p>가격·수량이 달라진 후의 과세표준으로 계산합니다. 반덤핑 현금예치나 사후 확정 관세를 계산하는 모듈은 아닙니다.</p>
      </details>
    </div>`;
}

export function markup() {
  return `<div class="ts-app">
    <nav class="ts-tabs" aria-label="시뮬레이터 유형"><button type="button" aria-pressed="true">국가</button><button type="button" disabled aria-pressed="false">기업 <span>준비 중</span></button></nav>
    <div class="ts-intro"><div><span class="ts-eyebrow">미국 수입시장 · 국가별 공급 반응</span><h1>관세가 바뀌면, 공급은 어디로 이동할까요?</h1>
      <p>같은 품목을 공급하는 국가들의 가격·판매량·점유율을 비교합니다.</p></div><span class="ts-badge">가상 데이터로 시작</span></div>
    <div class="ts-basis"><strong>현재 입력은 학습용 가정입니다.</strong> 실제 적용 세율·산업 전망이 아닙니다. 국가 GDP가 아닌 미국 단일 품목시장을 계산합니다.</div>
    <div class="ts-layout"><section class="ts-editor" aria-label="시나리오 입력"><div class="ts-panel-title"><span>01</span><h2>비교할 시장을 설정하세요</h2></div><div data-editor>${editor()}</div></section>
      <section class="ts-results" data-results aria-label="시나리오 계산 결과">${results()}</section></div>
    <footer class="ts-footer"><details><summary>모형 근거와 계산 범위</summary><p>USITC 연구진의 비중첩 CES 부분균형 모형(2020, §2.1)을 참고했습니다. 공급국별 수요와 공급이 같아지는 가격을 직접 계산하며, 공식 USITC 전망이나 Excel 실행 결과가 아닙니다.</p>
      <p>완전경쟁·고정된 공급국 구성·동일 품목·기간을 가정합니다. 신규 진입, 생산능력 한도, 환율, 보복관세, 제3국 재판매, 공급망 연쇄효과, GDP·고용, 기업 이익과 AD/CVD 법적 세율은 계산하지 않습니다.</p>
      <p>실제 분석에는 HS/HTS 범위, 국내 출하·수입을 맞춘 구매액, 검토된 종가세율과 문헌·자료 기반 탄력성이 필요합니다. 품목 선택만으로 보정되지 않습니다.</p>
      <p>${SOURCES.map(source => `<a href="${source.url}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>`).join(' · ')}</p>
      <p>버전 ${MODEL_VERSION} · 브라우저 내 계산 · 입력값은 서버로 전송하거나 자동 저장하지 않습니다.</p></details></footer>
  </div>`;
}

export function mount(root) {
  const controller = new AbortController(), signal = controller.signal;
  const markDirty = () => {
    dirty = true;
    root.querySelector('[data-stale]').hidden = false;
    root.querySelector('[data-calculated]').classList.add('is-stale');
    root.querySelector('[data-export]').disabled = true;
    error = ''; root.querySelector('[data-sim-error]').hidden = true;
  };
  const paintEditor = () => { root.querySelector('[data-editor]').innerHTML = editor(); };
  const update = event => {
    const el = event.target;
    if (el.dataset.key) {
      draft[el.dataset.key] = el.value;
      if (el.dataset.key === 'focus') root.querySelectorAll('.ts-input-table tbody tr').forEach((row, i) => row.classList.toggle('ts-focus-row', draft.rows[i].country === draft.focus));
      markDirty();
    }
    if (el.dataset.row !== undefined) {
      const row = draft.rows[Number(el.dataset.row)], old = row.country;
      row[el.dataset.field] = el.value;
      if (el.dataset.field === 'country') {
        if (row.country === 'USA') row.tariff_before = row.tariff_after = 0;
        if (draft.focus === old) draft.focus = row.country;
        if (['USA', 'ROW'].includes(draft.focus)) draft.focus = draft.rows.find(r => !['USA', 'ROW'].includes(r.country))?.country || '';
        paintEditor();
      }
      markDirty();
    }
  };
  root.addEventListener('input', update, { signal });
  root.addEventListener('submit', event => {
    if (!event.target.matches('[data-sim-form]')) return;
    event.preventDefault();
    try {
      const next = simulate(draft);
      result = next; dirty = false; error = '';
      root.querySelector('[data-results]').innerHTML = results();
      root.querySelector('[data-sim-error]').hidden = true;
    } catch (err) {
      markDirty(); error = err.message;
      const box = root.querySelector('[data-sim-error]'); box.textContent = error; box.hidden = false;
    }
  }, { signal });
  root.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-reset')) {
      draft = example(); result = simulate(draft); dirty = false; error = ''; root.innerHTML = markup();
    } else if (button.hasAttribute('data-add') && draft.rows.length < 8) {
      const country = Object.keys(COUNTRIES).find(code => code !== 'USA' && code !== 'ROW' && !draft.rows.some(row => row.country === code));
      if (country) { draft.rows.push({ country, expenditure: '', tariff_before: 0, tariff_after: 0, supply_elasticity: 3 }); paintEditor(); markDirty(); }
    } else if (button.dataset.remove !== undefined && draft.rows.length > 2) {
      draft.rows.splice(Number(button.dataset.remove), 1);
      if (!draft.rows.some(row => row.country === draft.focus)) draft.focus = draft.rows.find(row => !['USA', 'ROW'].includes(row.country))?.country || '';
      paintEditor(); markDirty();
    } else if (button.hasAttribute('data-export') && !dirty) {
      const payload = { exported_at: new Date().toISOString(), sources: SOURCES, ...result };
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
      const a = document.createElement('a'); a.href = url; a.download = 'country-tariff-scenario.json'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }, { signal });
  return () => controller.abort();
}
