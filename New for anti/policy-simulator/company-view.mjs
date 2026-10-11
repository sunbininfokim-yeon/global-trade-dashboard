import { simulateCompany, COMPANY_SOURCES, COMPANY_MODEL_VERSION } from './company-model.mjs';
import { COUNTRIES, PRODUCTS, POLICY_AS_OF, newRow, policyOptions, tariffPair, missingPolicyReason } from './policy-catalog.mjs';
import { firstFormIssue, clearFormErrors, showFormError } from './form-validation.mjs';
import { COMPANY_PROFILES, companyCalibration } from './company-profiles.mjs';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, p = 2) => v == null ? '산출 불가' : Number(v).toLocaleString('ko-KR', { minimumFractionDigits: p, maximumFractionDigits: p });
const signed = v => `${v > 0 ? '+' : ''}${fmt(Math.abs(v) < 1e-8 ? 0 : v)}`;
const options = (values, selected) => Object.entries(values).map(([key, label]) => `<option value="${key}"${key === selected ? ' selected' : ''}>${esc(label)}</option>`).join('');
const initial = (profileId = 'hyosung') => ({ profile_id: profileId, company: COMPANY_PROFILES[profileId]?.name || '', product: COMPANY_PROFILES[profileId]?.product || 'custom', origin: '', period: '', price: '', quantity: '', cost: '', fixed_cost: '',
  cost_change_pct: 0, absorption_pct: 50, price_elasticity: 2, locked_share_pct: 0, competitor_change_pct: 0, market_change_pct: 0,
  capacity: '', competitor_price: '', response_mode: 'manual', policy_confirmed: false, country_inputs: null,
  tariff: newRow(COMPANY_PROFILES[profileId]?.product || 'custom', ''), source_note: '기업 공식 재무는 참고용입니다. 이 제품의 실제 미국향 거래·원가·계약 자료를 입력하세요. 반응 계수는 사용자 가정입니다.' });
let draft = initial(), result = null, dirty = true, error = '';
function publicContext() {
  const p = COMPANY_PROFILES[draft.profile_id];
  if (!p) return '<p class="ts-help">분석할 실제 기업·제품의 자료를 입력하세요. 제품별 미국 판매와 원가는 별도 자료가 필요합니다.</p>';
  const f = p.financial;
  return `<div class="ts-company-public" data-company-public><h3>${esc(p.name)} · 확보한 공식 자료</h3><p>${esc(p.products)}</p><div class="ts-fields"><div><small>2025 매출 · 억원</small><strong>${fmt(f.revenue / 100, 2)}</strong></div><div><small>2025 영업이익 · 억원</small><strong>${fmt(f.operating_profit / 100, 2)}</strong></div></div><p class="ts-help">${esc(f.scope)} · <a href="${esc(f.source_url)}" target="_blank" rel="noopener noreferrer">공식 원문</a> · 확인 ${esc(f.checked_on)}</p><p>${esc(p.note)}</p><p class="ts-help"><b>추가로 필요한 거래 자료:</b> ${esc(p.missing.join(' / '))}. 위 재무 수치를 제품 손익 입력칸에 자동 대입하지 않습니다.</p>${p.ad ? '<button type="button" class="ts-text-button" data-company-ad>이 기업의 반덤핑 사건 보기 →</button>' : '<p class="ts-unverified">이 기업·제품의 AD 적용 여부는 이번 등록 사건에서 확인하지 않았습니다. 미확인은 무관세를 뜻하지 않습니다.</p>'}</div>`;
}
function field(key, label, min, max, help = '', optional = false) {
  return `<label>${label}<input type="number" inputmode="decimal" step="any" data-company-key="${key}" aria-label="기업 ${label}" value="${esc(draft[key])}" min="${min}" max="${max}"${optional ? '' : ' required'}>${help ? `<small>${help}</small>` : ''}</label>`;
}
function tariffEditor() {
  if (!draft.origin) return '<p class="ts-unverified">제품의 실제 원산지를 선택하면 관세 입력란이 나타납니다.</p>';
  const row = draft.tariff, choices = policyOptions(draft.product, draft.origin);
  const choicesMap = Object.fromEntries(choices.map(c => [c.id, `${c.label} · ${fmt(c.rate, 1)}%`]));
  const base = { ...(choices.length ? {} : { unresolved: '현행 조합 미확인' }), ...choicesMap, manual: '확인한 현행 총 세율 직접 입력' };
  const scenario = { current: '현재 관세 유지', ...choicesMap, manual: '직접 입력' };
  let badge = '현행 관세 확인 필요';
  try { const p = tariffPair(draft.product, row); badge = `${fmt(p.tariff_before, 1)}% → ${fmt(p.tariff_after, 1)}%`; } catch {}
  const chosen = choices.filter(c => [row.baseline_policy, row.scenario_policy].includes(c.id));
  return `<div class="ts-tariff-card"><div class="ts-section-label"><h3>원산지 ${esc(COUNTRIES[draft.origin])} · 관세</h3><strong data-company-rate>${badge}</strong></div>
    ${draft.origin === 'USA' ? '<p class="ts-help">미국산 국내 판매 · 수입관세 0%. 수입산과의 경쟁 반응은 국가 연결로 비교할 수 있습니다.</p>' : `<div class="ts-fields">
    <label>현행 관세 조합<select data-company-tariff="baseline_policy" aria-label="기업 현행 관세 조합">${options(base, row.baseline_policy)}</select></label>
    <label>비교할 관세<select data-company-tariff="scenario_policy" aria-label="기업 비교할 관세">${options(scenario, row.scenario_policy)}</select></label>
    ${row.baseline_policy === 'manual' ? `<label>확인한 현행 총 관세 %<input type="number" data-company-tariff="manual_before" aria-label="기업 현행 총 관세" value="${esc(row.manual_before)}" min="0" max="300" step="any" required></label><label>현행 관세 출처<input data-company-tariff="tariff_note" aria-label="기업 관세 출처" value="${esc(row.tariff_note)}" maxlength="500" required></label>` : ''}
    ${row.scenario_policy === 'manual' ? `<label>직접 입력한 가정 총 관세 %<input type="number" data-company-tariff="manual_after" aria-label="기업 가정 총 관세" value="${esc(row.manual_after)}" min="0" max="300" step="any" required></label>` : ''}</div>
    ${!choices.length ? `<p class="ts-help ts-unverified">${esc(missingPolicyReason(draft.product, draft.origin))}</p>` : ''}
    <details class="ts-policy-details"><summary>조건·별도 추가세·출처</summary>${chosen.map(c => `<p>${esc(c.condition)}<br>${c.sources.map(s => `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`).join(' · ')}</p>`).join('')}
    ${row.linked_provenance ? `<p>연결한 국가 관세의 근거: ${row.linked_provenance.sources.map(s => `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`).join(' · ')}<br>${esc(row.linked_provenance.conditions.join(' / '))}</p>` : ''}
    <label>별도 추가종가세 %<input type="number" data-company-tariff="extra_duty" aria-label="기업 별도 추가세" value="${esc(row.extra_duty)}" min="0" max="300" step="any" required><small>정책 조합에만 합산. 직접 입력은 총 세율입니다. AD 예치율을 확정 관세로 자동 변환하지 않습니다.</small></label></details>`}</div>`;
}
function editor() {
  const p = PRODUCTS[draft.product], isProxy = draft.response_mode === 'country';
  return `<form data-company-form novalidate><label>실제 기업 선택<select data-company-profile aria-label="실제 기업 선택">${options({ ...Object.fromEntries(Object.entries(COMPANY_PROFILES).map(([id, p]) => [id, p.name])), manual: '다른 기업 · 직접 입력' }, draft.profile_id)}</select></label>${publicContext()}<div class="ts-fields">
    <label class="ts-wide">기업·사업 이름<input data-company-key="company" aria-label="기업 이름" value="${esc(draft.company)}" maxlength="100"${draft.profile_id !== 'manual' ? ' readonly' : ''} required><small>공시 참고 자료와 이 제품의 거래 입력은 구분합니다.</small></label>
    <label>분석 품목<select data-company-key="product" aria-label="기업 분석 품목">${options(Object.fromEntries(Object.entries(PRODUCTS).map(([id, v]) => [id, v.label])), draft.product)}</select></label>
    <label>제품 원산지<select data-company-key="origin" aria-label="기업 제품 원산지" required>${options({ '': '제품 원산지 선택', ...Object.fromEntries(Object.entries(COUNTRIES).filter(([id]) => id !== 'ROW')) }, draft.origin)}</select><small>기업 본사 소재지가 아닌 제품의 실제 원산지</small></label>
    <label class="ts-wide">분석 기간<input data-company-key="period" aria-label="기업 분석 기간" value="${esc(draft.period)}" maxlength="100" required></label></div>
    <p class="ts-product-scope"><b>대표 HTS ${esc(p.hts || '직접 정의')}</b><br>${esc(p.scope)}</p>
    <div class="ts-section-label"><h3>기준 판매와 원가</h3><span>단가·금액: USD</span></div>
    <p class="ts-help">동일한 한 제품의 판매 단위를 사용하세요. 통관 단가는 관세 제외 수취단가와 같다고 가정합니다. 변동원가에는 기업이 부담하는 제조·수출 운송비 등을 포함합니다.</p>
    <div class="ts-fields">${field('price', '기준 통관 단가', 0.000001, 1e12)}${field('quantity', '기준 판매량', 0.000001, 1e12)}${field('cost', '단위 변동원가', 0, 1e12)}${field('fixed_cost', '기간 고정비', 0, 1e15, '이 제품·사업에 배분한 분석 기간의 고정비')}${field('cost_change_pct', '변동원가 변화율 %', -100, 1000)}${field('capacity', '최대 공급 가능 물량', 0.000001, 1e12, '선택 사항 · 공란이면 공급 한도 미반영', true)}</div>
    ${tariffEditor()}
    <label class="ts-confirm"><input type="checkbox" data-company-key="policy_confirmed" aria-label="기업 관세 적용 조건 확인" required${draft.policy_confirmed ? ' checked' : ''}>제품·원산지·예외·별도 추가세와 양쪽 관세 조건을 확인했습니다.</label>
    <div class="ts-section-label"><h3>가격과 판매량 반응</h3></div>
    <label>반응 방식<select data-company-key="response_mode" aria-label="기업 반응 방식"><option value="manual"${!isProxy ? ' selected' : ''}>기업 가정으로 가격·판매량 계산</option><option value="country"${isProxy ? ' selected' : ''}>국가 계산의 원산지 평균 반응 연결</option></select></label>
    ${isProxy ? `<p class="ts-help" data-company-link-note>${draft.country_inputs ? `연결됨: ${esc(draft.country_inputs.period)} · ${esc(COUNTRIES[draft.origin])}. 연결 시점의 국가 평균 반응을 기업에 적용하는 대용 시나리오입니다. 국가 입력의 후속 변경은 자동 반영되지 않습니다.` : '국가 탭에서 같은 품목·원산지·관세로 계산한 후 아래 버튼을 누르세요.'}</p>
    <button type="button" class="ts-text-button" data-company-link>최신 국가 계산 결과 연결</button><p class="ts-help">수동 방식의 흡수율·탄력성·계약·경쟁 가격·시장 수요 가정은 중복 적용하지 않습니다. 원가 변화와 공급 한도는 반영합니다.</p>` : `<div class="ts-fields ts-elasticities">
      ${field('absorption_pct', '수출자 흡수율 %', 0, 100, '0%: 관세 변화를 구매자에게 전가 · 100%: 구매가격 유지하도록 수취단가 조정')}
      ${field('price_elasticity', '기업 가격반응 탄력성', 0, 20, '사용자 가정. 산업 대체탄력성 σ와 다릅니다. 상대가격 1% 상승 시 경쟁 가능한 물량이 약 이 값% 감소')}
      ${field('locked_share_pct', '계약 고정 물량 비중 %', 0, 100, '상대가격 변화에 반응하지 않는 기준 물량 비중. 시장 전체 수요 변화는 반영')}
      ${field('competitor_change_pct', '경쟁 제품 가격 변화 %', -90, 300, '같은 사양 경쟁 제품의 관세 포함 가격 변화 가정')}
      ${field('market_change_pct', '시장 전체 수요 변화 %', -100, 300, '수동 가정 · 경쟁 제품 가격 변화와 별도로 입력. 국가 모형과 중복 적용하지 않음')}
      ${field('competitor_price', '경쟁 제품 기준 가격', 0.000001, 1e12, '선택 사항 · 같은 사양·단위의 관세 포함 비교가격', true)}</div>
      <p class="ts-help">초기 기업 탄력성 2, 계약 비중 0%, 경쟁 가격·시장 수요 변화 0%는 모두 사용자 가정입니다. 고객 인증·납기·품질 효과는 실측 모델로 추정하지 않습니다.</p>`}
    <label class="ts-source-label">자료 출처·가정 메모<textarea data-company-key="source_note" aria-label="기업 자료 출처 메모" maxlength="1500" rows="2">${esc(draft.source_note)}</textarea></label>
    <div class="ts-actions"><button class="ts-primary" type="submit">기업 시나리오 계산 →</button><button type="button" data-company-reset>기업 입력 초기화</button></div>
    <p class="ts-error" role="alert" data-company-error${error ? '' : ' hidden'}>${esc(error)}</p></form>`;
}
function results() {
  if (!result) return `<div class="ts-empty-result"><span class="ts-eyebrow">실제 기업 자료 · 제품별 사용자 시나리오</span><h2>관세 대응이 제품 손익에 미치는 영향</h2><p>공식 재무를 참고하고 분석할 한 제품의 원가·미국 거래·경쟁 반응을 입력하면 판매량과 손익을 계산합니다. 공개자료로 확인되지 않은 단가·원가·물량은 공란입니다.</p><p>반덤핑 예치 부담은 반덤핑 탭에서 별도로 비교할 수 있습니다.</p></div>`;
  const r = result;
  const cell = (title, before, after, suffix = '', digits = 2) => `<tr><th>${title}</th><td>${fmt(before, digits)}${suffix}</td><td>${fmt(after, digits)}${suffix}</td></tr>`;
  return `<div class="ts-result-heading"><div><span class="ts-eyebrow">${r.inputs.response_mode === 'country' ? '국가 평균 반응을 적용한 기업 시나리오' : '기업 가정에 따른 조건부 시나리오'}</span><h2>${esc(r.inputs.company)} · 제품 손익</h2><p>${esc(r.inputs.period)} · ${esc(COUNTRIES[r.inputs.origin])} · 관세 ${fmt(r.inputs.tariff_before, 1)}% → ${fmt(r.inputs.tariff_after, 1)}%</p></div><button type="button" class="ts-export" data-company-export${dirty ? ' disabled' : ''}>기업 JSON 저장</button></div>
    <p class="ts-stale" data-company-stale${dirty ? '' : ' hidden'}>입력이 바뀌었습니다. 재계산 전 결과입니다.</p><div data-company-calculated class="ts-calculated${dirty ? ' is-stale' : ''}">
    <div class="ts-kpis"><div><span>미국 판매량 변화</span><strong class="${r.quantity_change_pct < 0 ? 'ts-down' : 'ts-up'}">${signed(r.quantity_change_pct)}<small>%</small></strong></div><div><span>관세 제외 매출 변화</span><strong>${signed(r.revenue_change_pct)}<small>%</small></strong></div><div><span>제품 손익 변화</span><strong class="${r.profit_change < 0 ? 'ts-down' : 'ts-up'}">${signed(r.profit_change / 1000)}<small>천 USD</small></strong><small>전사 순이익 아님</small></div></div>
    <section class="ts-result-block"><h3>가격·원가·손익 비교</h3><div class="ts-scroll"><table class="ts-output-table"><thead><tr><th>항목</th><th>기준</th><th>시나리오</th></tr></thead><tbody>
      ${cell('수취·통관 단가', r.price_before, r.price_after)}${cell('관세 포함 구매가격', r.buyer_price_before, r.buyer_price_after)}${cell('단위 변동원가', r.unit_cost_before, r.unit_cost_after)}${cell('판매량', r.quantity_before, r.quantity_after)}${cell('매출 · USD', r.revenue_before, r.revenue_after, '', 0)}${cell('기여이익 · USD', r.contribution_before, r.contribution_after, '', 0)}${cell('제품 손익 · USD', r.profit_before, r.profit_after, '', 0)}${cell('제품 손익률', r.margin_before_pct, r.margin_after_pct, '%')}
      </tbody></table></div><p class="ts-help">제품 손익 = (수취단가 − 단위 변동원가) × 판매량 − 기간 고정비. 수입자 납부 관세는 기업 비용에서 다시 차감하지 않습니다.</p></section>
    <section class="ts-result-block"><h3>손익분기점과 경쟁 조건</h3><dl class="ts-company-metrics"><div><dt>손익분기 판매량</dt><dd>${fmt(r.break_even_quantity)}${r.break_even_status === 'above_capacity' ? ' · 공급 한도 초과' : r.break_even_status === 'nonpositive_contribution' ? ' · 단위 기여이익이 0 이하' : ''}</dd></div><div><dt>현재 판매량에서 감당 가능한 단위 변동원가</dt><dd>${fmt(r.unit_cost_ceiling)} USD</dd></div><div><dt>경쟁 제품 대비 구매가격 차이</dt><dd>${r.price_gap_pct == null ? '경쟁 제품 가격 미입력' : `${signed(r.price_gap_pct)}%`}</dd></div></dl><p class="ts-help">손익분기 판매량은 현재 시나리오 단가·원가가 유지된다는 조건입니다. 가격 차이만으로 고객 전환 여부를 확정하지 않습니다.</p>${r.capacity_binding ? '<p class="ts-unverified">입력한 공급 한도 때문에 판매량 증가가 제한됐습니다.</p>' : ''}</section>
    ${r.sensitivity.length ? `<section class="ts-result-block"><h3>수출자 흡수율별 대응 비교</h3><div class="ts-scroll"><table class="ts-output-table"><thead><tr><th>흡수율</th><th>수취단가</th><th>물량 변화</th><th>제품 손익 · USD</th></tr></thead><tbody>${r.sensitivity.map(s => `<tr${s.absorption_pct === r.inputs.absorption_pct ? ' class="ts-focus-row"' : ''}><th>${fmt(s.absorption_pct, 0)}%</th><td>${fmt(s.price_after)}</td><td>${signed(s.quantity_change_pct)}%</td><td>${fmt(s.profit_after, 0)}</td></tr>`).join('')}</tbody></table></div><p class="ts-help">다른 가정은 고정한 비교입니다. 최적 계약이나 발생 확률을 추정한 값은 아닙니다.</p></section>` : '<p class="ts-help">국가 결과의 원산지 평균 가격·물량을 적용했습니다. 기업별 고객·제품 경쟁력은 별도로 보정해야 합니다.</p>'}
    </div>`;
}
export function companyMarkup() {
  return `<div data-company-simulator><div class="ts-intro"><div><span class="ts-eyebrow">기업 · 한 제품 · 한 원산지</span><h1>관세 부담을 나누면, 제품 손익은 어떻게 바뀔까요?</h1><p>가격 전가·단가 인하·고객 전환과 원가를 함께 비교합니다.</p></div><span class="ts-badge">${Object.keys(COMPANY_PROFILES).length}개 실제 기업 · 공식 자료</span></div>
    <p class="ts-model-source">계산 근거: 기업 가격·손익의 명시적 산식. 국가 연결은 <a href="https://www.usitc.gov/ces_tariff_model" target="_blank" rel="noopener noreferrer">USITC CES 기반 시장 반응</a>을 참고합니다.</p>
    <div class="ts-basis"><strong>제품 손익 스트레스 테스트</strong> 관세는 ${POLICY_AS_OF} 부분 검토 스냅샷. 기업 원가·계약·탄력성은 사용자 가정입니다. 입력값은 브라우저 안에서만 계산합니다.</div>
    <div class="ts-layout"><section class="ts-editor" aria-label="기업 시나리오 입력"><div class="ts-panel-title"><span>02</span><h2>기업의 판매와 원가를 입력하세요</h2></div><div data-company-editor>${editor()}</div></section><section class="ts-results" data-company-results aria-label="기업 계산 결과">${results()}</section></div>
    <footer class="ts-footer"><details><summary>기업 모형 산식·출처·계산 범위</summary><p>수출자 흡수율은 기존 통관 단가 기준 관세 변화분을 나누는 가정입니다. 바뀐 통관 단가에 새 관세를 적용하므로 관세 과세표준과 할인 효과를 중복 계산하지 않습니다.</p>
    <pre class="ts-company-formula">수취단가₁ = 수취단가₀ × [1 + 관세₀ + (1 − 흡수율) × (관세₁ − 관세₀)] ÷ (1 + 관세₁)
구매가격 = 수취단가 × (1 + 관세)
판매량₁ = 판매량₀ × [계약 비중 + (1 − 계약 비중) × 상대가격 변화비율^(−기업 탄력성)] × 시장 수요 변화비율
제품 손익 = (수취단가 − 단위 변동원가) × 판매량 − 기간 고정비</pre>
    <p>경쟁 가능한 물량은 상대 구매가격의 변화에 일정 탄력성으로 반응하며 계약 고정 비중은 상대가격에 반응하지 않습니다. 입력한 시장 수요 변화와 공급 한도도 적용합니다. 기업 탄력성 초기값 2는 문헌에서 추정한 기업값이 아닙니다. 공급 한도를 적용한 뒤 경쟁국 물량을 다시 배분하는 균형은 계산하지 않습니다.</p><p>기업명으로 실제 재무·원산지를 추정하지 않습니다. 전사 손익·AD 예치와 사후 확정·환율·다른 국가 재판매·고객 인증 비용은 계산 범위 밖입니다.</p><p>${COMPANY_SOURCES.map(s => `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`).join(' · ')} · 버전 ${COMPANY_MODEL_VERSION}</p></details></footer></div>`;
}

export function mountCompany(root, { getCountryResult, openAntidumping }) {
  const controller = new AbortController(), signal = controller.signal;
  const paint = () => { root.querySelector('[data-company-editor]').innerHTML = editor(); };
  const markDirty = () => {
    clearFormErrors(root);
    dirty = true; error = '';
    const exp = root.querySelector('[data-company-export]'), stale = root.querySelector('[data-company-stale]'), output = root.querySelector('[data-company-calculated]');
    if (exp) exp.disabled = true; if (stale) stale.hidden = false; if (output) output.classList.add('is-stale');
    root.querySelector('[data-company-error]').hidden = true;
  };
  const fail = (err, element) => { error = err.message; showFormError(root, root.querySelector('[data-company-error]'), { message: error, element }); };
  const unconfirm = () => { draft.policy_confirmed = false; const c = root.querySelector('[data-company-key="policy_confirmed"]'); if (c) c.checked = false; };
  root.addEventListener('input', event => {
    const el = event.target;
    if (el.hasAttribute('data-company-profile')) { draft = initial(el.value); result = null; dirty = true; error = ''; root.innerHTML = companyMarkup(); }
    else if (el.dataset.companyKey) {
      const key = el.dataset.companyKey;
      draft[key] = key === 'policy_confirmed' ? el.checked : el.value;
      if (key === 'product' || key === 'origin') { draft.tariff = newRow(draft.product, draft.origin); draft.country_inputs = null; unconfirm(); paint(); }
      else if (key === 'response_mode') paint();
      markDirty();
    } else if (el.dataset.companyTariff) {
      const key = el.dataset.companyTariff; draft.tariff[key] = el.value; draft.country_inputs = null; delete draft.tariff.linked_provenance; unconfirm();
      if (key === 'baseline_policy') { draft.tariff.manual_before = ''; draft.tariff.tariff_note = ''; }
      if (key === 'scenario_policy') draft.tariff.manual_after = '';
      if (['baseline_policy', 'scenario_policy'].includes(key)) paint();
      markDirty();
      try { const p = tariffPair(draft.product, draft.tariff); root.querySelector('[data-company-rate]').textContent = `${fmt(p.tariff_before, 1)}% → ${fmt(p.tariff_after, 1)}%`; } catch { root.querySelector('[data-company-rate]').textContent = '현행 관세 확인 필요'; }
    }
  }, { signal });
  root.addEventListener('submit', event => {
    if (!event.target.matches('[data-company-form]')) return;
    event.preventDefault();
    try {
      const issues = [];
      try { tariffPair(draft.product, draft.tariff); } catch (err) { issues.push({ element: root.querySelector(`[data-company-tariff="${err.field}"]`), message: err.message }); }
      if (draft.capacity !== '' && Number(draft.capacity) < Number(draft.quantity)) issues.push({ element: root.querySelector('[data-company-key="capacity"]'), message: '최대 공급 가능 물량은 기준 판매량 이상이어야 합니다.' });
      if (draft.response_mode === 'country' && (!draft.country_inputs || draft.country_inputs.product !== draft.product || !draft.country_inputs.rows.some(r => r.country === draft.origin))) issues.push({ element: root.querySelector('[data-company-link]'), message: '같은 품목·원산지의 국가 결과를 먼저 연결하세요.' });
      const issue = firstFormIssue(event.target, issues);
      if (issue) { markDirty(); fail(new Error(issue.message), issue.element); return; }
      clearFormErrors(root);
      const p = tariffPair(draft.product, draft.tariff);
      const next = simulateCompany({ ...draft, ...p, tariff_provenance: { ...p.provenance, ...(draft.tariff.linked_provenance ? { status: 'linked_country_scenario', linked_provenance: draft.tariff.linked_provenance } : {}) },
        calibration: { policy_as_of: POLICY_AS_OF, hts: PRODUCTS[draft.product].hts || null, scope: PRODUCTS[draft.product].scope, ...companyCalibration(draft.profile_id) } });
      result = next; dirty = false; error = ''; root.querySelector('[data-company-results]').innerHTML = results(); root.querySelector('[data-company-error]').hidden = true;
    } catch (err) { markDirty(); fail(err); }
  }, { signal });
  root.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-company-ad')) { const ad = COMPANY_PROFILES[draft.profile_id]?.ad; if (ad) openAntidumping?.(ad); }
    else if (button.hasAttribute('data-company-reset')) { draft = initial(); result = null; dirty = true; error = ''; root.innerHTML = companyMarkup(); }
    else if (button.hasAttribute('data-company-link')) {
      markDirty();
      try {
        const country = getCountryResult();
        if (!country || country.inputs.product !== draft.product) throw new Error('국가 탭에서 같은 품목으로 유효한 계산을 완료한 뒤 연결하세요.');
        const row = country.inputs.rows.find(r => r.country === draft.origin);
        if (!row) throw new Error('국가 결과에 기업 원산지가 없습니다. 국가 탭에 공급국을 추가하세요.');
        draft.country_inputs = structuredClone(country.inputs);
        draft.tariff = { ...newRow(draft.product, draft.origin), baseline_policy: draft.origin === 'USA' ? 'domestic' : 'manual', scenario_policy: draft.origin === 'USA' ? 'current' : 'manual',
          manual_before: row.tariff_before, manual_after: row.tariff_after, tariff_note: `국가 시나리오 연결 · ${country.inputs.period}`, linked_provenance: row.provenance };
        unconfirm(); paint();
      } catch (err) { fail(err, button); }
    } else if (button.hasAttribute('data-company-export') && !dirty && result) {
      const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), sources: COMPANY_SOURCES, ...result }, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = 'company-tariff-scenario.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }, { signal });
  return () => controller.abort();
}
