import { simulate, MODEL_VERSION, SOURCES } from './country-model.mjs';
import { COUNTRIES, PRODUCTS, POLICY_AS_OF, SUPPLIER_SNAPSHOT, initialDraft, newRow, policyOptions, missingPolicyReason, tariffPair, modelInput, elasticityCalibration } from './policy-catalog.mjs';
import { companyMarkup, mountCompany, selectCompanyProfile } from './company-view.mjs';
import { antidumpingMarkup, mountAntidumping, selectAntidumping } from './antidumping-view.mjs';
import { firstFormIssue, clearFormErrors, showFormError } from './form-validation.mjs';

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, places = 2) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: places, maximumFractionDigits: places });
const signed = v => `${v > 0.00001 ? '+' : ''}${fmt(Math.abs(v) < 0.00001 ? 0 : v)}`;
const name = code => COUNTRIES[code] || code;
const options = (values, selected) => Object.entries(values).map(([key, label]) => `<option value="${key}"${key === selected ? ' selected' : ''}>${esc(label)}</option>`).join('');
let draft = initialDraft(), result = null, dirty = true, error = '';
let activeTab = 'country';
const productLabels = Object.fromEntries(Object.entries(PRODUCTS).map(([id, p]) => [id, p.label]));
let stylePromise;

export function prepare() {
  if (!stylePromise) stylePromise = new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = new URL('./style.css?v=5', import.meta.url).href;
    link.onload = resolve;
    link.onerror = () => { link.remove(); stylePromise = null; reject(new Error('시뮬레이터 스타일을 불러오지 못했습니다.')); };
    document.head.appendChild(link);
  });
  return stylePromise;
}

function numberInput(value, attrs) {
  return `<input type="number" inputmode="decimal" step="any" value="${esc(value)}" ${attrs} required>`;
}
function rates(row) {
  try { const pair = tariffPair(draft.product, row); return `${fmt(pair.tariff_before, 1)}% → ${fmt(pair.tariff_after, 1)}%`; }
  catch { return '현행 관세 확인 필요'; }
}
function elasticitySources() {
  const e = PRODUCTS[draft.product].elasticity, c = elasticityCalibration(draft);
  const basis = { literature_range_midpoint: '문헌 범위의 중간값', literature_review_midpoint: '문헌 검토 범위의 중간값', historical_sector_proxy: '과거 산업 모형 대용값', literature_proxy: '문헌 기반 근사값' };
  const describe = p => p.kind === 'user_assumption' ? '사용자 가정 · 이 입력의 문헌값은 미확보이거나 직접 수정했습니다.'
    : `${basis[p.kind]} · <a href="${p.source.url}" target="_blank" rel="noopener noreferrer">${esc(p.source.title)}</a>${p.range ? ` · 범위 ${p.range.join('~')}` : ''}<br><small>${esc(p.scope)}</small>`;
  return `<p data-sigma-basis><b>대체탄력성 σ:</b> ${describe(c.sigma)}</p>
    <p data-eta-basis><b>시장 수요탄력성 η:</b> ${describe(c.eta)}</p>
    ${e ? `<p>${esc(e.note)}</p><button type="button" class="ts-text-button" data-literature>문헌 기본값 적용</button>` : '<p>이 대표 품목에 맞는 문헌값 미확보. 초기 σ=4, η=-1은 학습용 가정입니다.</p>'}
    <small data-elasticity-basis>σ: ${basis[c.sigma.kind] || '사용자 가정'} · η: ${basis[c.eta.kind] || '사용자 가정'}. 직접 수정하면 해당 값만 사용자 가정으로 전환됩니다.</small>
    <p>품목·시장·분석 기간에 따라 달라지는 값입니다. 모든 기업과 산업에 공통으로 적용되는 상수가 아닙니다. <a href="${SOURCES[1].url}" target="_blank" rel="noopener noreferrer">탄력성의 역할: 모형 원문 §2.1</a></p>`;
}
function tariffEditor(row, i) {
  if (row.country === 'USA') return '';
  const choices = policyOptions(draft.product, row.country);
  const current = { ...(choices.length ? {} : { unresolved: '현행 조합 미확인 · 아래에서 선택' }),
    ...Object.fromEntries(choices.map(c => [c.id, `${c.label} · ${fmt(c.rate, 1)}%`])), manual: '확인한 현행 합산율 직접 입력' };
  const scenarios = { current: '현재 관세 유지', ...Object.fromEntries(choices.map(c => [c.id, `${c.label} · ${fmt(c.rate, 1)}%`])), manual: '직접 입력' };
  const selected = choices.filter(c => [row.baseline_policy, row.scenario_policy].includes(c.id));
  const refs = [...new Map(selected.flatMap(c => c.sources).map(s => [s.url, s])).values()];
  return `<section class="ts-tariff-card" data-tariff-card="${i}">
    <div class="ts-section-label"><h3>${esc(name(row.country))} 관세</h3><strong data-rate="${i}">${rates(row)}</strong></div>
    <div class="ts-fields"><label>현행 관세 조합<select data-row="${i}" data-field="baseline_policy" aria-label="${name(row.country)} 현행 관세 조합">${options(current, row.baseline_policy)}</select></label>
      <label>비교할 관세<select data-row="${i}" data-field="scenario_policy" aria-label="${name(row.country)} 비교할 관세">${options(scenarios, row.scenario_policy)}</select></label>
      ${row.baseline_policy === 'manual' ? `<label>현행 합산 관세 %${numberInput(row.manual_before, `data-row="${i}" data-field="manual_before" min="0" max="300" aria-label="${name(row.country)} 확인한 현행 관세"`)}</label>
        <label>현행 관세 출처·확인 내용<input data-row="${i}" data-field="tariff_note" aria-label="${name(row.country)} 현행 관세 출처" value="${esc(row.tariff_note)}" maxlength="500" required></label>` : ''}
      ${row.scenario_policy === 'manual' ? `<label class="ts-wide">직접 입력한 가정 합산 관세 %${numberInput(row.manual_after, `data-row="${i}" data-field="manual_after" min="0" max="300" aria-label="${name(row.country)} 가정 관세"`)}<small>추가세까지 포함한 총 세율. 현행 정책으로 확정된 값이 아닙니다.</small></label>` : ''}
    </div>
    ${!choices.length ? `<p class="ts-help ts-unverified">${esc(missingPolicyReason(draft.product, row.country))}</p>` : ''}
    <details class="ts-policy-details"><summary>적용 조건·별도 추가세·공식 출처</summary>
      ${selected.map(c => `<p><b>${esc(c.label)}</b> — ${esc(c.condition)}</p>`).join('')}
      <label>별도 추가종가세 % · AD/CVD 등 확인한 가정${numberInput(row.extra_duty, `data-row="${i}" data-field="extra_duty" min="0" max="300" aria-label="${name(row.country)} 별도 추가세"`)}<small>정책 조합에만 합산합니다. 직접 입력한 총 세율에는 다시 더하지 않습니다. 0%는 미적용 가정이며, 반덤핑 예치율을 확정 관세로 판정하는 기능은 아닙니다.</small></label>
      <p>${refs.map(s => `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`).join(' · ')}</p>
    </details></section>`;
}
function editor() {
  const profile = PRODUCTS[draft.product];
  const focusChoices = Object.fromEntries(draft.rows.filter(row => !['USA', 'ROW'].includes(row.country)).map(row => [row.country, name(row.country)]));
  const suppliers = SUPPLIER_SNAPSHOT.products[draft.product];
  return `<form data-sim-form novalidate>
    <div class="ts-fields">
      <label>분석 품목<select data-key="product" aria-label="분석 품목">${options(productLabels, draft.product)}</select></label>
      <label>관심 공급국<select data-key="focus" aria-label="관심 공급국" required>${options(focusChoices, draft.focus)}</select></label>
      <label class="ts-wide">구매액 기준 연도·기간<input data-key="period" aria-label="구매액 기준 연도·기간" value="${esc(draft.period)}" maxlength="80" required><small>구매액을 집계한 기간입니다. 관세 검토일과 다를 수 있습니다.</small></label>
    </div>
    <p class="ts-product-scope"><b>대표 HTS ${esc(profile.hts || '직접 정의')}</b><br>${esc(profile.scope)}</p>${profile.classification_checked_on ? `<p class="ts-help" data-classification-basis>품목 분류·기본 관세 확인 ${profile.classification_checked_on} · <a href="https://hts.usitc.gov/search?query=${encodeURIComponent(profile.hts)}" target="_blank" rel="noopener noreferrer">USITC HTS 원문 ↗</a>. 이 날짜는 다른 품목의 관세·통계 갱신일이 아닙니다.</p>` : ''}
    <div class="ts-section-label"><h3>시장·공급국</h3><span>구매액 단위: 백만 달러</span></div>
    <p class="ts-help" data-purchase-help>기준 구매액은 관세 변경 전 기준 기간에 미국 구매자가 각 공급국의 해당 품목에 쓴 관세 포함 금액입니다. 한국 행의 25는 2,500만 달러입니다. 미국 행에는 미국산 제품 구매액을 넣습니다.</p>
    <div class="ts-scroll"><table class="ts-input-table"><caption class="ts-sr">같은 품목·기간·관세 포함 구매액을 입력하세요.</caption>
      <thead><tr><th>공급국</th><th>기준 구매액</th><th>공급탄력성</th><th><span class="ts-sr">제거</span></th></tr></thead>
      <tbody>${draft.rows.map((row, i) => {
        const countries = Object.fromEntries(Object.entries(COUNTRIES).filter(([key]) => key === row.country || !draft.rows.some(r => r.country === key)));
        return `<tr${row.country === draft.focus ? ' class="ts-focus-row"' : ''}>
          <td><select data-row="${i}" data-field="country" aria-label="공급국 ${i + 1}">${options(countries, row.country)}</select></td>
          <td>${numberInput(row.expenditure, `data-row="${i}" data-field="expenditure" min="0.000001" max="1000000000" aria-label="${name(row.country)} 기준 구매액"`)}</td>
          <td>${numberInput(row.supply_elasticity, `data-row="${i}" data-field="supply_elasticity" min="0" max="100" aria-label="${name(row.country)} 공급탄력성"`)}</td>
          <td><button type="button" class="ts-remove" data-remove="${i}" aria-label="${name(row.country)} 제거"${draft.rows.length <= 2 ? ' disabled' : ''}>×</button></td>
        </tr>`;
      }).join('')}</tbody></table></div>
    ${suppliers ? `<div class="ts-suppliers"><p>추가할 공급국 · <a href="${SUPPLIER_SNAPSHOT.url}" target="_blank" rel="noopener noreferrer">USITC 2025 수입액 상위 8개국</a> · HS ${suppliers.hts6}</p>
      <div>${suppliers.suppliers.map((s, i) => `<button type="button" data-supplier="${s.country}" title="2025 소비용 수입 통관가액 ${fmt(s.customs_value_usd / 1e6, 1)} 백만 달러"${draft.rows.length >= 8 || draft.rows.some(r => r.country === s.country) ? ' disabled' : ''}>${i + 1}. ${esc(s.label_ko)}</button>`).join('')}</div>
      <small>HS6 범위의 실제 수입 공급국입니다. 대표 HTS보다 범위가 넓을 수 있으며, 기업 소재지·제조지 순위와는 다릅니다.</small></div>` : ''}
    <button type="button" class="ts-text-button" data-add${draft.rows.length >= 8 ? ' disabled' : ''}>+ 다른 공급국 추가 <span>최대 8개</span></button>
    <p class="ts-help">구매액·공급탄력성은 가상 초기값입니다. 국가 추가 시 구매액은 비워 둡니다. 기타국 합계에서 새 국가를 빼서 중복을 피하세요. 미국 국내 공급은 수입 통계에 포함되지 않습니다.</p>
    <div class="ts-section-label"><h3>현행 관세·비교 시나리오</h3><span>${POLICY_AS_OF} 검토 스냅샷</span></div>
    <p class="ts-help">현재 제도의 조건별 조합입니다. 품목·원산지·소재 요건이 바뀌어야 적용되는 경로도 있습니다. 임의의 새 관세율은 ‘직접 입력’을 선택하세요.</p>
    ${draft.rows.map(tariffEditor).join('')}
    <label class="ts-confirm"><input type="checkbox" data-key="policy_confirmed" aria-label="관세 적용 조건 확인" required${draft.policy_confirmed ? ' checked' : ''}>선택한 양쪽 관세의 HTS·원산지·예외·별도 추가세 조건에 맞는 거래를 비교합니다.</label>
    <div class="ts-fields ts-elasticities">
      <label>대체탄력성 σ ${numberInput(draft.sigma, 'data-key="sigma" aria-label="대체탄력성" min="0.1" max="20" aria-describedby="ts-sigma-help"')}<small id="ts-sigma-help">공급국 간 상대가격 변화에 따른 구매 전환. 클수록 쉽게 다른 공급국으로 전환합니다.</small></label>
      <label>시장 수요탄력성 η ${numberInput(draft.eta, 'data-key="eta" aria-label="시장 수요탄력성" min="-10" max="-0.05"')}<small>미국 해당 품목시장 전체의 가격·수요 반응. η=-1이면 시장 가격지수 1% 상승 시 전체 수요가 약 1% 감소합니다.</small></label>
    </div>
    <div class="ts-elasticity-source" data-elasticity-source>${elasticitySources()}</div>
    <details class="ts-explainer"><summary>입력 기준과 계산 범위</summary>
      <p>공급탄력성 초기값은 미국 1.5, 외국 3인 학습용 가정입니다. 제품 선택만으로 시장 구매액·공급탄력성이 실측값으로 바뀌지 않습니다.</p>
      <p>구매액은 관세 포함 구매자 지출입니다. DataWeb 통관가액은 국내 출하·관세·유통 마진을 맞추기 전에는 이 구매액과 다릅니다.</p>
      <p>정책 조합은 확인한 대표 사양에만 적용합니다. 종량세·TRQ·환급·기업별 AD/CVD 판정·모든 예외를 자동 계산하지 않습니다. 미확인은 0%로 채우지 않습니다.</p>
    </details>
    <label class="ts-source-label">입력 자료·가정 메모<textarea data-key="source_note" aria-label="입력 자료·가정 메모" maxlength="1000" rows="2">${esc(draft.source_note)}</textarea></label>
    <div class="ts-actions"><button class="ts-primary" type="submit">시나리오 계산 <span aria-hidden="true">→</span></button><button type="button" data-reset>입력 초기화</button></div>
    <p class="ts-error" role="alert" data-sim-error${error ? '' : ' hidden'}>${esc(error)}</p>
  </form>`;
}

function results() {
  if (!result) return `<div class="ts-empty-result"><span class="ts-eyebrow">계산 전 · 관세 조건 확인</span><h2>국가별 영향 비교</h2><p>먼저 왼쪽에서 품목·공급국과 관세 조합을 선택하세요. 직접 입력은 선택했을 때만 열립니다.</p><p>시작 구매액은 가상값이며, 현재 관세 유지끼리 비교하면 변화는 0입니다.</p></div>`;
  const r = result, focus = r.rows.find(row => row.country === r.inputs.focus);
  const country = name(focus.country), input = r.inputs.rows.find(row => row.country === focus.country);
  return `<div class="ts-result-heading"><div><span class="ts-eyebrow">조건부 시뮬레이션 · 가정값</span><h2>${esc(country)} 공급 변화</h2>
    <p>${esc(PRODUCTS[r.inputs.product]?.label || r.inputs.product)} · ${esc(r.inputs.period)} · 관세 ${fmt(input.tariff_before, 1)}% → ${fmt(input.tariff_after, 1)}%</p></div>
    <button type="button" class="ts-export" data-export${dirty ? ' disabled' : ''}>결과 JSON 저장</button></div>
    <p class="ts-stale" data-stale role="status"${dirty ? '' : ' hidden'}>입력이 바뀌었습니다. 아래는 이전 계산 결과입니다. 다시 계산하세요.</p>
    <div class="ts-calculated${dirty ? ' is-stale' : ''}" data-calculated>
      <div class="ts-kpis">
        <div><span>${esc(country)} 판매량</span><strong class="${focus.volume_change_pct < 0 ? 'ts-down' : 'ts-up'}">${signed(focus.volume_change_pct)}<small>%</small></strong><small>미국 시장 내 물량 변화</small></div>
        <div><span>${esc(country)} 공급자 매출</span><strong>${signed(focus.revenue_change_pct)}<small>%</small></strong><small>관세 제외 · 기업 이익 아님</small></div>
        <div><span>미국 시장 가격지수</span><strong>${signed(r.market_price_change_pct)}<small>%</small></strong><small>해당 품목의 구매가격</small></div>
      </div>
      <section class="ts-result-block"><div class="ts-section-label"><h3>공급국별 물량 변화</h3><span>국가별 판매량 변화</span></div>
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
      <section class="ts-result-block"><div class="ts-section-label"><h3>대체탄력성별 민감도</h3><span>대체탄력성만 변경</span></div>
        <div class="ts-sensitivity">${r.sensitivity.map(s => `<div${s.sigma === r.inputs.sigma ? ' class="is-selected"' : ''}><span>σ = ${fmt(s.sigma, 1)}${s.sigma === r.inputs.sigma ? ' · 입력값' : ''}</span>
          ${s.status === 'calculated' ? `<strong>${signed(s.volume_change_pct)}%</strong><small>${esc(country)} 판매량</small>` : '<strong>계산 불가</strong>'}</div>`).join('')}</div>
        <p class="ts-help">가능한 가정을 비교한 값입니다. 발생 확률이나 통계적 신뢰구간이 아닙니다.</p>
      </section>
      <details class="ts-explainer ts-market-totals"><summary>미국 품목시장·관세수입</summary>
        <dl><div><dt>CES 집계 수량지수 변화</dt><dd>${signed(r.market_quantity_change_pct)}%</dd></div>
          <div><dt>관세 포함 전체 구매액</dt><dd>${fmt(r.spending_before)} → ${fmt(r.spending_after)} 백만 달러</dd></div>
          <div><dt>미국 관세수입</dt><dd>${fmt(r.duties_before)} → ${fmt(r.duties_after)} 백만 달러</dd></div></dl>
        <p>가격·수량이 달라진 후의 과세표준으로 계산합니다. 반덤핑 현금예치나 사후 확정 관세를 계산하는 모듈은 아닙니다.</p>
      </details>
    </div>`;
}

function countryMarkup() {
  return `<div data-country-simulator>
    <div class="ts-intro"><div><span class="ts-eyebrow">미국 수입시장 · 국가별 공급 반응</span><h1>국가별 관세 영향</h1>
      <p>같은 품목을 공급하는 국가들의 가격·판매량·점유율을 비교합니다.</p></div><span class="ts-badge">구매액은 가상 초기값</span></div>
    <p class="ts-model-source">모형 근거: <a href="${SOURCES[0].url}" target="_blank" rel="noopener noreferrer">USITC CES Tariff Model</a> · <a href="${SOURCES[1].url}" target="_blank" rel="noopener noreferrer">Riker & Schreiber (2020) §2.1</a>의 국가별 부분균형 구조를 참고했습니다.</p>
    <details class="ts-explainer ts-logic"><summary>계산 원리·용어</summary>
      <p class="ts-logic-flow">관세 변화 → 구매가격 변화 → 공급국 전환·시장 수요 변화 → 가격·판매량 비교</p>
      <dl><div><dt>계산 대상</dt><dd>미국의 한 품목시장입니다. 공급국별 수요와 공급이 같아지는 가격을 구합니다. 국가 경제 전체의 전망은 아닙니다.</dd></div>
      <div><dt>대체탄력성 σ</dt><dd>상대가격이 바뀔 때 다른 공급국 제품으로 구매를 옮기는 정도입니다. 클수록 쉽게 전환합니다.</dd></div>
      <div><dt>시장 수요탄력성 η</dt><dd>이 품목의 시장 가격이 바뀔 때 전체 수요가 변하는 정도입니다. 음수이며, 절댓값이 클수록 수요 반응이 큽니다.</dd></div>
      <div><dt>공급탄력성</dt><dd>생산자가 받는 가격이 바뀔 때 공급량이 반응하는 정도입니다. 초기값은 실측치가 아닌 학습용 가정입니다.</dd></div></dl>
      <p><a href="${SOURCES[0].url}" target="_blank" rel="noopener noreferrer">USITC 모형 소개·Excel 원본 ↗</a> · <a href="${SOURCES[1].url}" target="_blank" rel="noopener noreferrer">계산 구조 원문 §2.1 ↗</a>. 이 화면은 해당 구조를 참고한 자체 계산이며, 공식 전망이나 Excel 실행 결과가 아닙니다.</p>
    </details>
    <div class="ts-basis"><strong>현행 정책 조건 + 사용자 시장 가정</strong> 관세는 ${POLICY_AS_OF}의 제한된 검토 스냅샷입니다. 자동 갱신되지 않습니다. 국가 GDP가 아닌 미국 단일 품목시장을 계산합니다.</div>
    <div class="ts-layout"><section class="ts-editor" aria-label="시나리오 입력"><div class="ts-panel-title"><span>01</span><h2>시장·관세 조건</h2></div><div data-editor>${editor()}</div></section>
      <section class="ts-results" data-results aria-label="시나리오 계산 결과">${results()}</section></div>
    <footer class="ts-footer"><details><summary>모형 근거와 계산 범위</summary><p>USITC 연구진의 비중첩 CES 부분균형 모형(2020, §2.1)을 참고했습니다. 공급국별 수요와 공급이 같아지는 가격을 직접 계산하며, 공식 USITC 전망이나 Excel 실행 결과가 아닙니다.</p>
      <p>완전경쟁·고정된 공급국 구성·동일 품목·기간을 가정합니다. 신규 진입, 생산능력 한도, 환율, 보복관세, 제3국 재판매, 공급망 연쇄효과, GDP·고용, 기업 이익과 AD/CVD 법적 세율은 계산하지 않습니다.</p>
      <p>실제 분석에는 HS/HTS 범위, 국내 출하·수입을 맞춘 구매액, 검토된 종가세율과 문헌·자료 기반 탄력성이 필요합니다. 공급국 통계는 2025년 HS6 소비용 수입 통관가액 상위 8개국입니다. 관세 대표 HTS의 세부 사양과 다를 수 있으며 구매액에 자동 주입하지 않습니다.</p>
      <p>${SOURCES.map(source => `<a href="${source.url}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>`).join(' · ')}</p>
      <p>버전 ${MODEL_VERSION} · 브라우저 내 계산 · 입력값은 서버로 전송하거나 자동 저장하지 않습니다.</p></details></footer>
  </div>`;
}

function mountCountry(root) {
  const controller = new AbortController(), signal = controller.signal;
  const markDirty = () => {
    clearFormErrors(root);
    dirty = true;
    const stale = root.querySelector('[data-stale]'), calculated = root.querySelector('[data-calculated]'), exp = root.querySelector('[data-export]');
    if (stale) stale.hidden = false;
    if (calculated) calculated.classList.add('is-stale');
    if (exp) exp.disabled = true;
    error = ''; root.querySelector('[data-sim-error]').hidden = true;
  };
  const paintEditor = () => { root.querySelector('[data-editor]').innerHTML = editor(); };
  const unconfirm = () => { draft.policy_confirmed = false; const el = root.querySelector('[data-key="policy_confirmed"]'); if (el) el.checked = false; };
  const update = event => {
    const el = event.target;
    if (el.dataset.key) {
      const key = el.dataset.key;
      if (key === 'product') {
        const next = initialDraft(el.value);
        draft = { ...draft, ...next, period: draft.period, source_note: draft.source_note,
          rows: draft.rows.map(row => newRow(el.value, row.country, row.expenditure)) };
        draft.focus = draft.rows.find(row => row.country === draft.focus)?.country || draft.rows.find(row => !['USA', 'ROW'].includes(row.country))?.country || '';
        // Purchase values are retained only as user assumptions, never relabeled observations.
        paintEditor();
      } else {
        draft[key] = key === 'policy_confirmed' ? el.checked : el.value;
        if (key === 'sigma' || key === 'eta') {
          draft.elasticity_overrides[key] = true;
          root.querySelector('[data-elasticity-source]').innerHTML = elasticitySources();
        }
        if (key === 'focus') root.querySelectorAll('.ts-input-table tbody tr').forEach((row, i) => row.classList.toggle('ts-focus-row', draft.rows[i].country === draft.focus));
      }
      markDirty();
    }
    if (el.dataset.row !== undefined) {
      const row = draft.rows[Number(el.dataset.row)], field = el.dataset.field, old = row.country;
      row[field] = el.value;
      if (['country', 'baseline_policy', 'scenario_policy', 'manual_before', 'manual_after', 'extra_duty', 'tariff_note'].includes(field)) unconfirm();
      if (field === 'country') {
        draft.rows[Number(el.dataset.row)] = newRow(draft.product, el.value, row.expenditure);
        if (draft.focus === old) draft.focus = el.value;
        if (['USA', 'ROW'].includes(draft.focus)) draft.focus = draft.rows.find(r => !['USA', 'ROW'].includes(r.country))?.country || '';
        paintEditor();
      } else if (['baseline_policy', 'scenario_policy'].includes(field)) {
        // Do not carry a previously typed manual rate into another selected path.
        if (field === 'baseline_policy') { row.manual_before = ''; row.tariff_note = ''; }
        else row.manual_after = '';
        paintEditor();
      } else {
        const badge = root.querySelector(`[data-rate="${el.dataset.row}"]`); if (badge) badge.textContent = rates(row);
      }
      markDirty();
    }
  };
  root.addEventListener('input', update, { signal });
  root.addEventListener('submit', event => {
    if (!event.target.matches('[data-sim-form]')) return;
    event.preventDefault();
    try {
      const issues = draft.rows.map((row, i) => {
        try { tariffPair(draft.product, row); } catch (err) { return { element: root.querySelector(`[data-row="${i}"][data-field="${err.field}"]`), message: err.message }; }
        return null;
      });
      const issue = firstFormIssue(event.target, issues);
      if (issue) { markDirty(); error = issue.message; showFormError(root, root.querySelector('[data-sim-error]'), issue); return; }
      clearFormErrors(root);
      const next = simulate(modelInput(draft));
      result = next; dirty = false; error = '';
      root.querySelector('[data-results]').innerHTML = results();
      root.querySelector('[data-sim-error]').hidden = true;
    } catch (err) {
      markDirty(); error = err.message;
      showFormError(root, root.querySelector('[data-sim-error]'), { message: error });
    }
  }, { signal });
  root.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-reset')) {
      draft = initialDraft(); result = null; dirty = true; error = ''; root.innerHTML = countryMarkup();
    } else if (button.hasAttribute('data-literature')) {
      const e = PRODUCTS[draft.product].elasticity;
      if (e) { draft.sigma = e.sigma; if (e.eta !== undefined) draft.eta = e.eta; draft.elasticity_basis = 'literature'; draft.elasticity_overrides = {}; paintEditor(); markDirty(); }
    } else if ((button.hasAttribute('data-add') || button.dataset.supplier) && draft.rows.length < 8) {
      const country = button.dataset.supplier || Object.keys(COUNTRIES).find(code => code !== 'USA' && code !== 'ROW' && !draft.rows.some(row => row.country === code));
      if (country && !draft.rows.some(row => row.country === country)) { draft.rows.push(newRow(draft.product, country)); unconfirm(); paintEditor(); markDirty(); }
    } else if (button.dataset.remove !== undefined && draft.rows.length > 2) {
      draft.rows.splice(Number(button.dataset.remove), 1); unconfirm();
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

export function markup() {
  return `<div class="ts-app"><nav class="ts-tabs" aria-label="시뮬레이터 유형"><button type="button" data-simulator-tab="country" aria-pressed="${activeTab === 'country'}">국가</button><button type="button" data-simulator-tab="antidumping" aria-pressed="${activeTab === 'antidumping'}">반덤핑</button><button type="button" data-simulator-tab="company" aria-pressed="${activeTab === 'company'}">기업</button></nav><div data-simulator-view>${activeMarkup()}</div></div>`;
}
const activeMarkup = () => activeTab === 'country' ? countryMarkup() : activeTab === 'antidumping' ? antidumpingMarkup() : companyMarkup();
export function mount(root) {
  const controller = new AbortController();
  let cleanup;
  const attach = () => {
    const body = root.querySelector('[data-simulator-view]');
    cleanup = activeTab === 'country' ? mountCountry(body) : activeTab === 'antidumping' ? mountAntidumping(body, { openCompany: (profileId, product) => { selectCompanyProfile(profileId, product); switchTab('company'); } }) : mountCompany(body, { getCountryResult: () => dirty ? null : result, openAntidumping: selection => { selectAntidumping(selection); switchTab('antidumping'); } });
  };
  const switchTab = tab => {
    cleanup?.(); activeTab = tab;
    root.querySelectorAll('[data-simulator-tab]').forEach(t => t.setAttribute('aria-pressed', String(t.dataset.simulatorTab === activeTab)));
    root.querySelector('[data-simulator-view]').innerHTML = activeMarkup(); attach();
  };
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-simulator-tab]');
    if (!button || !root.contains(button) || button.dataset.simulatorTab === activeTab) return;
    if (['country', 'company', 'antidumping'].includes(button.dataset.simulatorTab)) switchTab(button.dataset.simulatorTab);
  }, { signal: controller.signal });
  attach();
  return () => { cleanup?.(); controller.abort(); };
}
