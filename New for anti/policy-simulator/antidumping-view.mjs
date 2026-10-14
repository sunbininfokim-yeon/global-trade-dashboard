import { AD_CATALOG as catalog } from './antidumping-catalog.mjs';
import { AD_DISCOVERY } from './antidumping-discovery-snapshot.mjs';
import { industryMonitorMarkup } from './industry-monitor.mjs';
import { noticeReviewMarkup } from './antidumping-notice-view.mjs';
import { COMPANY_INDUSTRIES, COMPANY_PROFILES, INDUSTRY_FAMILIES, companyCalibration } from './company-profiles.mjs';
import { productVerification, verificationMarkup, adCoverageStatus, coverageStatusMarkup } from './product-verification.mjs';
import { lookupAD, depositPer100k, simulateDeposit, nonSelectedScenario, AD_MODEL_VERSION } from './antidumping-model.mjs';
import { firstFormIssue, clearFormErrors, showFormError } from './form-validation.mjs';
import { createADExample, describeADInputs, AD_GUIDE_FIELDS, AD_PROCESS_SOURCES, AD_PROCESS_STEPS, reviewRecords, caseReviewRecords, reviewProgress } from './antidumping-guide.mjs';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = v => v == null ? '미확인' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: 2 });
const money = v => { if (v == null) return '산출 불가'; const negative = v.startsWith('-'), [whole, fraction] = v.replace(/^-/, '').split('.'); return `${negative ? '-' : ''}${BigInt(whole).toLocaleString('en-US')}.${fraction}`; };
const link = d => `<a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.document_id || d.label)}</a>`;
const selectedCase = () => catalog.cases.find(c => c.case_id === draft.case_id);
const initial = () => {
  const context = { reference_mode: 'published', case_id: 'A-580-867', company_id: 'hyosung', entry_date: catalog.checked_on };
  return { ...context, ...createADExample(context).values, scope_confirmed: false, identity_confirmed: false,
    manual_case_id: '', company_name: '', reference_rate_pct: '', reference_url: '', reference_note: '' };
};
let draft = initial(), result = null, dirty = true, methodResult = null;
let industryId = 'transformer', profileId = '';
let companySearch = '', allCompaniesOpen = false, overview = true, calculatorOpen = false;
const selectedIndustry = () => COMPANY_INDUSTRIES.find(x => x.id === industryId);
const hasADCase = () => Boolean(selectedIndustry().case_id);
let example = createADExample(draft), editedFields = new Set(), processRecordId = '';
let methodSegment = '2026-16663', methodRows = [], equalWeights = false;
function seedMethod() {
  const s = selectedCase().segments.find(s => s.document_id === methodSegment) || selectedCase().segments.at(-1);
  methodSegment = s.document_id;
  methodRows = s.rates.filter(r => r.examined).map(r => ({ name: selectedCase().companies.find(c => c.id === r.company_id).name, margin_pct: r.margin_pct, weight: '', entirely_facts_available: r.entirely_facts_available }));
  equalWeights = false; methodResult = null;
}
seedMethod();
export function selectAntidumping({ case_id, company_id }) {
  const c = catalog.cases.find(c => c.case_id === case_id);
  if (!c?.companies.some(x => x.id === company_id)) return;
  industryId = COMPANY_INDUSTRIES.find(x => x.case_id === case_id).id; profileId = ''; overview = false; calculatorOpen = true;
  companySearch = ''; allCompaniesOpen = false;
  draft = { ...initial(), case_id, company_id }; example = createADExample(draft); Object.assign(draft, example.values);
  editedFields = new Set(); processRecordId = ''; result = null; dirty = true;
  methodSegment = c.segments.at(-1).document_id; seedMethod();
}
function input(key, label, { type = 'number', min = '0', max = '10000', value = draft[key], help = '', step = '0.000001', required = true } = {}) {
  return `<label>${label}<input data-ad-key="${key}" aria-label="${label}" type="${type}" value="${esc(value)}"${type === 'number' ? ` min="${min}" max="${max}" step="${step}"` : ''}${type === 'text' ? ' maxlength="500"' : ''}${required ? ' required' : ''}>${help ? `<small>${help}</small>` : ''}</label>`;
}
function unitReferencePanel() {
  if (overview || draft.reference_mode !== 'published' || !hasADCase()) return '';
  let r; try { r = lookupAD(draft); } catch { return ''; }
  return `<p class="ts-basis" data-ad-unit-reference><b>신고가격 10만 USD당 예치 참고액: ${r.rate_pct == null ? '미확인' : `$${money(depositPer100k(r.rate_pct))}`}</b><br><small>선택 법인·통관 가정일의 조건부 공표 참고율 기준. 실제 거래액·최종 관세 아님. 제품·법인 조건 추가 확인 필요.</small></p>`;
}
function referencePanel() {
  if (draft.reference_mode === 'manual') return `<div class="ts-fields">
    ${input('manual_case_id', 'AD 사건번호', { type: 'text', help: 'A-000-000 · 공고에서 확인한 사건' })}${input('company_name', '생산자·수출자 법인명', { type: 'text' })}
    ${input('reference_rate_pct', '직접 확인한 AD 예치율 %')}${input('reference_url', '예치율 출처 URL', { type: 'url' })}
    ${input('reference_note', '예치율 적용 근거', { type: 'text', help: '발효일·제품·생산자/수출자 조건을 기록하세요.' })}</div><p class="ts-help">직접 입력은 사용자 확인값입니다. 등록되지 않은 기업을 무관세로 처리하지 않습니다.</p>`;
  const c = selectedCase(); let reference;
  try { reference = lookupAD(draft); } catch (e) { reference = { reason: e.message, rate_pct: null }; }
  return `<div class="ts-fields"><label>반덤핑 사건<select data-ad-key="case_id" aria-label="반덤핑 사건">${catalog.cases.map(c => `<option value="${c.case_id}"${c.case_id === draft.case_id ? ' selected' : ''}>${c.product} · ${c.case_id}</option>`).join('')}</select></label>
    <label>공고에 기재된 법인<select data-ad-key="company_id" aria-label="반덤핑 기업">${c.companies.map(x => `<option value="${x.id}"${x.id === draft.company_id ? ' selected' : ''}>${x.name}</option>`).join('')}<option value="unknown"${draft.company_id === 'unknown' ? ' selected' : ''}>목록에 없는 법인 · 미확인</option></select></label></div>
    <div class="ts-ad-reference" data-ad-reference><span>선별 최종 공고의 AD 예치 참고율</span><strong>${reference.rate_pct == null ? '미확인' : `${fmt(reference.rate_pct)}%`}</strong>
    ${reference.document ? `<p>${esc(reference.company.official_name)}<br>${reference.effective ? `예치 발효 ${reference.effective}` : `배정 마진 ${fmt(reference.margin_pct)}% · 예치율 미확인`} · POR ${reference.por_start} ~ ${reference.por_end}<br>공식 공고 ${link(reference.document)}</p>` : ''}<p>${esc(reference.reason)}</p>${c.case_id === 'A-580-867' && reference.document?.document_id === '2026-16663' && ['ls', 'hyosung'].includes(draft.company_id) ? `<details><summary>4.32%의 근거 확인</summary><p>효성의 과거 개별조사 마진은 ${link(catalog.documents['2023-05386'])}에서 4.32%였습니다. 2026년 상무부는 과거 마진 변동과 이번 조사기업의 0% 결과 등을 고려해 효성은 4.32%를 유지하고, 개별조사 이력이 없는 LS에는 종전 배정 16.87% 대신 효성의 4.32%를 부여했습니다.</p><p>${link(catalog.documents['ACCESS-4943770-02'])} · 바코드 4943770-02, Comment 7, pp.23–24. 이는 상무부가 밝힌 판단 근거입니다. 비공개 거래자료 없이 실제 계산 마진을 재현하거나 소송 결론을 단정하지 않습니다.</p></details>` : ''}</div>
    <p class="ts-product-scope"><b>대상 범위 확인</b><br>${esc(c.scope.description)}<br>${c.scope.hts.length ? `HTS 참고: ${esc(c.scope.hts.join(', '))} · ` : ''}범위 근거 ${link(catalog.documents[c.scope.document_id])}</p>`;
}
function history() {
  const c = selectedCase();
  const shown = !overview && c.companies.length > 8 ? c.companies.filter(x => x.id === draft.company_id || c.segments.some(s => s.rates.some(r => r.company_id === x.id && r.examined))) : c.companies;
  return `<section class="ts-result-block"><h3>${esc(c.product)} · 공표 마진 이력</h3>${!overview && c.companies.length > 8 ? '<p class="ts-help">선택 기업과 개별조사 기업을 비교합니다. 다른 법인의 이력은 기업 선택을 바꾸면 볼 수 있습니다.</p>' : ''}<div class="ts-scroll"><table class="ts-output-table"><thead><tr><th>발행일·단계</th><th>조사대상 기간 (POR)</th>${shown.map(x => `<th>${esc(x.name)}</th>`).join('')}<th>공고</th></tr></thead><tbody>${c.segments.map(s => `<tr><th>${catalog.documents[s.document_id].published}<br>${s.stage === 'final' ? '최종' : '예비 · 예치율 변경 아님'}</th><td>${s.por_start}<br>~ ${s.por_end}</td>${shown.map(x => { const r = s.rates.find(r => r.company_id === x.id); return `<td>${r ? `${fmt(r.margin_pct)}%<br><small>${r.examined ? '개별조사' : '비선정'}${r.deposit_rate_pct === null ? ' · 예치율 미확인' : ''}</small>` : '미수록'}</td>`; }).join('')}<td>${link(catalog.documents[s.document_id])}</td></tr>`).join('')}</tbody></table></div>
    ${c.segments.map(s => `<p class="ts-help">${link(catalog.documents[s.document_id])} · ${esc(s.reason)}</p>`).join('')}
    ${c.reviews.map(r => `<p class="ts-basis">재심 개시 · POR ${r.por_start} ~ ${r.por_end} · ${link(catalog.documents[r.document_id])}<br>새 세율·조사기업 선정·확정 종료일은 이 자료에서 확인되지 않았습니다.</p>`).join('')}
    <p class="ts-help">미수록은 0%가 아닙니다. 수록한 최종 공고의 참고율이며 모든 후속 변경을 확인한 실시간 적용 세율은 아닙니다.</p></section>`;
}
function editor() {
  if (!hasADCase()) return '<p class="ts-help">기업별 예치율 미확정 · 위 공식 자료 확인 결과를 참고하세요.</p>';
  return `<form data-ad-form novalidate><div class="ts-ad-example"><b>계산 예시 · 업계 평균 아님</b><p>선택한 품목에 계산용 거래 총액을 넣었습니다. 금리·기간·비교율은 산업 평균이나 해당 회사의 실제 값이 아닙니다. 직접 입력으로 바꿀 수 있습니다.</p><button type="button" data-ad-example>품목 예시 적용</button><div data-ad-input-guide>${inputGuide()}</div></div><label>예치율 근거<select data-ad-key="reference_mode" aria-label="예치율 근거"><option value="published"${draft.reference_mode === 'published' ? ' selected' : ''}>등록된 공식 공고</option><option value="manual"${draft.reference_mode === 'manual' ? ' selected' : ''}>다른 사건·기업 · 직접 확인한 예치율</option></select></label>
    ${input('entry_date', '통관일', { type: 'date', help: `공식 공고 자료 확인일 ${catalog.checked_on}. POR와 통관 발효일은 다릅니다.` })}${referencePanel()}
    <h3>거래 금액·비교 예치율</h3><div class="ts-fields">${input('entered_value_usd', '대상 수입 신고가격 · USD', { min: '0.01', max: '1000000000000', help: '해당 거래 전체 금액. 1개 제품 가격·회사 매출과 다릅니다.' })}${input('scenario_rate_pct', '가정 AD 예치율 %', { help: '초기값: 공표 참고율 +5%p. 미래 판정 예측값이 아닙니다.' })}${input('annual_finance_pct', '연 금융비용률 %', { max: '100', help: '예시 5%. 실제 자금조달 금리로 수정. 0이면 미반영.' })}${input('holding_days', '예치 기간 · 일', { max: '36500', step: '1', help: '예시 365일. 재심 종료일·환급일을 뜻하지 않습니다.' })}</div>
    <div class="ts-ad-periods" aria-label="예치 기간 비교"><span>기간 가정 바꾸기</span>${[90, 365, 730].map(days => `<button type="button" data-ad-days="${days}">${days}일</button>`).join('')}</div>
    <label class="ts-confirm"><input type="checkbox" data-ad-key="scope_confirmed" aria-label="AD 제품 범위 확인"${draft.scope_confirmed ? ' checked' : ''} required><span>제품 사양·원산지가 사건의 서술 범위에 포함되는지 확인했습니다.</span></label>
    <label class="ts-confirm"><input type="checkbox" data-ad-key="identity_confirmed" aria-label="AD 법인 적용 조건 확인"${draft.identity_confirmed ? ' checked' : ''} required><span>생산자·수출자의 정확한 법인명과 예치율 적용 조건을 확인했습니다.</span></label>
    <div class="ts-actions"><button class="ts-primary" type="submit">AD 예치 부담 계산</button><button type="button" data-ad-reset>반덤핑 입력 초기화</button></div><p class="ts-error" data-ad-error role="alert" hidden></p></form>`;
}
const fieldNames = { entered_value_usd: '거래 총액', scenario_rate_pct: '비교 예치율', annual_finance_pct: '연 자금비용률', holding_days: '묶이는 기간', entry_date: '통관 가정일' };
function inputGuide() {
  const notes = describeADInputs(draft, example, [...editedFields]);
  return `<details><summary>입력값의 의미와 예시 근거</summary><dl>${notes.map(x => `<div><dt>${fieldNames[x.key]} · ${x.origin === 'editable_example' ? '예시' : '직접 입력'} ${esc(x.value || '미입력')}${x.key.includes('pct') ? '%' : x.key === 'entered_value_usd' ? ' USD' : x.key === 'holding_days' ? '일' : ''}</dt><dd>${esc(x.note)}</dd></div>`).join('')}</dl><p>거래 규모가 달라도 예치액은 신고가격에 비례합니다. 업종 평균 거래액·기업 차입금리·정산일은 공개 공고에서 확인할 수 없어 실제 값으로 단정하지 않았습니다.</p></details>`;
}
function processStepsMarkup(steps, guide = false) {
  return `<ol class="ts-ad-steps">${steps.map(s => `<li data-ad-stage="${s.id}" data-state="${s.state || 'guide'}"><details><summary><i aria-hidden="true"></i><span><b>${esc(s.label)}</b><small>${esc(s.agency)}</small><em>${s.event ? `${s.event.date || '날짜 미수록'} · ${s.state === 'latest' ? '수록 최신 근거' : '확인됨'}` : guide ? '일반 절차 안내' : '진행 근거 미확인'}</em></span></summary><p>${esc(s.description)}</p>${s.event ? `<p>${esc(s.event.note)}</p><p>${link(s.event.document)}</p>` : ''}<p>${link(AD_PROCESS_SOURCES[s.source])}</p></details></li>`).join('')}</ol>`;
}
function companyButton(x) {
  let reference;
  try { reference = lookupAD({ ...draft, company_id: x.id }); } catch { reference = { rate_pct: null }; }
  const status = reference.rate_pct == null ? (reference.margin_pct == null ? '예치율 미확인' : `배정 마진 ${fmt(reference.margin_pct)}% · 예치율 미확인`) : `예치 참고율 ${fmt(reference.rate_pct)}%`;
  return `<button type="button" data-ad-company="${x.id}" aria-label="${esc(x.name)}" aria-pressed="${!overview && draft.reference_mode !== 'manual' && x.id === draft.company_id}"><b>${esc(x.name)}</b><small>${esc(status)}</small></button>`;
}
function featuredCompanies() {
  const c = selectedCase(), ids = c.featured_company_ids || c.companies.slice(0, 8).map(x => x.id);
  return c.companies.filter(x => ids.includes(x.id));
}
function companySearchResults() {
  const c = selectedCase(), query = companySearch.trim().toLocaleLowerCase(), featured = featuredCompanies();
  const matches = c.companies.filter(x => query ? [x.name, x.official_name, ...x.aliases].some(n => n.toLocaleLowerCase().includes(query)) : !featured.includes(x));
  return `<p class="ts-help" role="status">${query ? `검색 결과 ${matches.length}개` : `추가 법인 ${matches.length}개`} · 회사 규모·시장점유율 순위가 아닙니다.</p><div class="ts-ad-companies">${matches.map(companyButton).join('')}</div>`;
}
function verificationLabel(product) {
  const c = adCoverageStatus(product);
  return `${c.research.label} · ${c.procedure.label}`;
}
function processSelection() {
  const industry = selectedIndustry(), c = selectedCase(), manual = draft.reference_mode === 'manual';
  if (!industry.case_id) return `<div class="ts-ad-selection" aria-label="산업과 기업 선택">${industryPicker()}${overviewButton()}
    <fieldset><legend>2. 기업 선택 · 선택사항 <span>${industry.profiles.length}개 기업</span></legend><div class="ts-ad-companies">${industry.profiles.map(id => `<button type="button" data-ad-profile="${id}" aria-label="${esc(COMPANY_PROFILES[id].name)}" aria-pressed="${!overview && profileId === id}"><b>${esc(COMPANY_PROFILES[id].name)}</b><small>${esc(verificationLabel(industry.product))}</small></button>`).join('')}</div></fieldset>
    <p class="ts-ad-selection-context" role="status">선택: ${esc(industry.label)} → <b>${overview ? '품목 전체' : esc(COMPANY_PROFILES[profileId].name)}</b> · 기업별 예치율 미확정</p>
    <p class="ts-help">공식 제품군과 한국 활성 사건 목록의 확인 결과를 연결했습니다. 아래 공식 자료 확인 결과에서 조사 범위와 남은 확인사항을 볼 수 있습니다. 기업별 AD 예치율 미확정은 0%를 뜻하지 않습니다.${industry.source ? ` <a href="${esc(industry.source)}" target="_blank" rel="noopener noreferrer">기업 제품 원문</a>` : ''}</p></div>`;
  const company = c.companies.find(x => x.id === draft.company_id);
  return `<div class="ts-ad-selection" aria-label="산업과 기업 선택">
    ${industryPicker()}${overviewButton()}
    <fieldset><legend>2. 기업 선택 · 선택사항 <span>관보 기재 ${c.companies.length}개 기업·법인그룹</span></legend><div class="ts-ad-companies" data-ad-featured${companySearch.trim() ? ' hidden' : ''}>${featuredCompanies().map(companyButton).join('')}</div>
    ${c.companies.length > 8 ? `<details class="ts-ad-all" data-ad-all${allCompaniesOpen ? ' open' : ''}><summary>전체 기업 보기·검색 · ${c.companies.length}개</summary><label>기업명 검색<input type="search" data-ad-search aria-label="반덤핑 전체 기업 검색" maxlength="100" value="${esc(companySearch)}" placeholder="한글 또는 관보의 영문 법인명"></label><div data-ad-search-results>${companySearchResults()}</div></details>` : ''}</fieldset>
    <p class="ts-ad-selection-context" role="status">${overview ? `선택: ${esc(c.product)} · 한국산 · 품목 전체 · ${esc(c.case_id)}` : manual ? '다른 사건·기업 직접 입력 중 · 위 기업을 누르면 등록된 공식 공고로 전환합니다.' : `선택: ${esc(c.product)} → <b>${esc(company?.name || '목록에 없는 법인 · 미확인')}</b> · ${esc(c.case_id)}`}</p>
    <p class="ts-help">한국산 제품의 수록 사건입니다. 위 버튼은 빠른 선택용이며 시장점유율·국내 순위가 아닙니다. 관보에 나온 법인은 규모와 관계없이 전체 목록에 포함합니다. 통관 가정일 ${esc(draft.entry_date)}의 예치 참고율과 최신 재심의 진행 단계는 별개입니다.</p>
  </div>`;
}
function overviewButton() {
  return `<div class="ts-ad-companies ts-ad-overview"><button type="button" data-ad-overview aria-label="품목 전체" aria-pressed="${overview}"><b>품목 전체</b><small>기업 선택 없이 사건 흐름 확인 · 기업별 적용과 구분</small></button></div>`;
}
function industryPicker() {
  const family = selectedIndustry().family;
  return `<fieldset><legend>1. 산업 → 품목 선택</legend><label class="ts-ad-family">산업 분야<select data-ad-family aria-label="산업 분야">${INDUSTRY_FAMILIES.map(x => `<option value="${x.id}"${x.id === family ? ' selected' : ''}>${esc(x.label)}</option>`).join('')}</select></label><div class="ts-ad-industries">${COMPANY_INDUSTRIES.filter(x => x.family === family).map(x => `<button type="button" ${x.case_id ? `data-ad-case="${x.case_id}"` : `data-ad-industry="${x.id}"`} aria-label="${esc(x.label)}" aria-pressed="${x.id === industryId}">${esc(x.label)}<small>${esc(x.description)}</small><small>${x.case_id ? '공식 AD 공고 연결' : esc(verificationLabel(x.product))}</small></button>`).join('')}</div></fieldset>`;
}
function monitorNotices() {
  return hasADCase() ? noticeReviewMarkup(AD_DISCOVERY, draft.case_id) : industryMonitorMarkup(selectedIndustry().product);
}
function coverageGap() {
  const industry = selectedIndustry(), p = overview ? null : COMPANY_PROFILES[profileId];
  const productSource = p ? companyCalibration(profileId, industry.product).selected_product_source?.url : null;
  const verification = productVerification(industry.product);
  const gap = verification?.ad.status === 'official_case_confirmed_deposit_unresolved' ? '공식 사건과 과거 최종 마진을 확인했습니다. 예치율 적용 조건은 추가 검토 중입니다.' : verification?.ad.status === 'related_scope_review_required' ? '관련 조사 공고 확인 · 실제 제품 범위와 기업별 예치율은 추가 확인이 필요합니다.' : verification?.ad.status === 'bounded_search_no_confirmed_case' ? '품목별 공식 조사 근거 연결 · 한국산 대응 사건·기업별 예치율 미확인. 아래에서 다른 제품·원산지 사건의 구분 근거를 볼 수 있습니다.' : '이 기업·품목의 반덤핑 공고와 예치율은 아직 연결하지 않았습니다.';
  return `<div class="ts-ad-gap" data-ad-gap><h3>${p ? `${esc(p.name)} · ` : ''}${esc(industry.label)}</h3><p class="ts-unverified">${esc(gap)}</p>${verification ? verificationMarkup(industry.product) : coverageStatusMarkup(industry.product)}<p>계산에 필요한 사건번호, 대상 제품·원산지, 정확한 생산자·수출자 법인, 적용일과 세율의 공식 근거를 추가 확인해야 합니다. 다른 제품의 세율이나 계열사 세율을 대신 사용하지 않습니다.</p>${industry.id === 'switchgear' ? '<p class="ts-help">LS일렉트릭·효성중공업의 변압기 공고는 차단기·배전기기에 자동 적용되지 않습니다.</p>' : ''}${industry.family === 'auto' ? '<p class="ts-help">자동차 232 관세는 반덤핑과 별도입니다. 기업·품목 손익 분석에서 제품 원산지와 확인한 관세를 선택할 수 있습니다. 한국 기업의 미국 생산품에 한국산 수입관세를 적용하지 않습니다.</p>' : ''}${productSource ? `<p class="ts-help"><a href="${esc(productSource)}" target="_blank" rel="noopener noreferrer">선택 기업·품목의 공식 원문 ↗</a></p>` : ''}${p ? '<button type="button" class="ts-text-button" data-ad-open-company>기업·품목 손익 분석 →</button>' : '<p class="ts-help">기업별 확인은 위 기업 선택에서 이어집니다.</p>'}<p class="ts-help">기업 계산에는 실제 원산지·거래·원가와 확인한 관세 입력이 필요합니다.${industry.id === 'cable' ? ' 케이블은 사양 확인 전 대표 HTS를 지정하지 않고 직접 정의 품목으로 시작합니다.' : ''}</p></div>`;
}
function processMarkup() {
  if (!hasADCase()) return `<section class="ts-ad-process" aria-label="반덤핑 조사 재심 소송 단계"><div class="ts-section-label"><h2>산업·기업 선택</h2><span>기업 제품군 연결 · AD 적용 여부 별도 확인</span></div>${processSelection()}<p class="ts-basis">확인한 공식 공고·관세 근거는 아래에 표시합니다. AD 예치율이나 기업별 적용이 미확정이어도 공고를 볼 수 있으며, 다른 제도의 공고로 AD 단계 불을 켜지 않습니다.</p></section>`;
  const c = selectedCase(), records = overview ? caseReviewRecords(draft.case_id) : reviewRecords(draft.case_id, draft.company_id);
  const record = records.find(r => r.id === processRecordId) || records[0];
  processRecordId = record?.id || '';
  const progress = record ? reviewProgress(draft.case_id, record.id, overview ? null : draft.company_id) : null, manual = !overview && draft.reference_mode === 'manual';
  return `<section class="ts-ad-process" aria-label="반덤핑 조사 재심 소송 단계"><div class="ts-section-label"><h2>조사·재심·소송 진행</h2><span>진행 근거 확인 ${progress?.checked_on || catalog.checked_on}</span></div>
    ${processSelection()}${unitReferencePanel()}
    <div class="ts-ad-roles"><p><b>상무부</b><span>덤핑 여부·마진과 재심 결과</span></p><p><b>USITC</b><span>신규 조사 등의 미국 산업피해</span></p><p><b>CBP · 세관</b><span>예치금 수납·수입 건별 관세 정산</span></p><p><b>CIT · 항소법원</b><span>행정판단의 적법성 심사</span></p></div>
    <p class="ts-help">예치금은 최종 세금이 아닙니다. 재심·적용되는 법원 판단과 세관 정산에 따라 추가 납부 또는 환급이 생길 수 있습니다. 소송에서 졌다고 예치금 전액이 그대로 최종 관세가 되는 구조는 아닙니다.</p>
    ${!manual && progress ? `<label class="ts-ad-process-picker">진행을 볼 재심 대상 기간<select data-ad-process-record aria-label="진행을 볼 재심 대상 기간">${records.map(r => `<option value="${r.id}"${r.id === record.id ? ' selected' : ''}>${r.por_start} ~ ${r.por_end}${r.id === records[0].id ? ' · 수록 최신 기간' : ''}</option>`).join('')}</select></label><p class="ts-help">${esc(c.case_id)} · ${esc(c.product)} · 이 기간의 사건 진행 표시입니다. 위 통관일의 예치 참고율과 별개이며, 기간을 바꿔도 계산 세율은 바뀌지 않습니다. 기업별 재심 취소·후속 정정 등 미수록 변경은 추가 확인이 필요합니다.</p><div class="ts-ad-legend"><span>● 확인됨</span><span>● 수록 최신 근거</span><span>○ 미확인</span></div>${!overview && progress.status_event ? `<p class="ts-ad-rescinded" data-ad-rescinded><b>${progress.status_event.date} · 이 기업의 해당 POR 재심 철회</b><br>${esc(progress.status_event.note)} · ${link(catalog.documents[progress.status_event.source])}</p>` : ''}${processStepsMarkup(progress.stages)}
    ${!overview && progress.deposit ? `<p class="ts-basis">별도 경로 · 이후 통관의 새 예치율: ${progress.deposit.date}부터 해당 공고의 조건에 따라 적용 · ${link(catalog.documents[progress.deposit.source])}. 과거 POR 거래의 정산 완료·환급일을 뜻하지 않습니다.</p>` : `<p class="ts-basis">${overview ? '품목 전체에서는 기업별 예치율·선정·철회를 일괄 적용하지 않습니다. 기업을 선택하면 해당 법인의 기록을 확인할 수 있습니다.' : '이 재심의 새 예치율은 아직 수록하지 않았습니다. 개시만으로 기존 참고율을 바꾸지 않습니다.'}</p>`}` : '<p class="ts-basis">다른 사건·미확인 법인은 실제 진행 기록이 연결되지 않았습니다. 아래는 일반 절차 안내이며 해당 기업이 도달한 단계 표시가 아닙니다.</p>'}
    <details class="ts-ad-route"><summary>소송·항소 경로 · CIT → 환송 또는 판결 → Federal Circuit → 대법원 심리허가</summary><p>선택한 재심·기업의 법원 사건번호·명령을 이 자료에서 확인하지 못했습니다. 소송이 없다는 뜻이 아닙니다. 접수·금지명령·판결·항소를 각각 확인해야 불이 들어옵니다. 환송은 상무부 재결정과 CIT 재심사로 되돌아갈 수 있으며, 재심과 소송은 병행될 수 있습니다.</p>${processStepsMarkup(progress && !manual ? progress.litigation : AD_PROCESS_STEPS.litigation, manual || !progress)}</details>
    <details class="ts-ad-route"><summary>신규 조사·반덤핑 명령 절차</summary><p>기존 명령의 연례 재심과 구분합니다. 상무부가 덤핑을, USITC가 산업피해를 따로 판단합니다. 아래는 일반 경로로, 특정 사건의 앞 단계를 자동 완료 처리하지 않습니다. 조사 중지·철회 등 별도 경로도 가능합니다. ${link(AD_PROCESS_SOURCES.injury)}</p>${processStepsMarkup(AD_PROCESS_STEPS.investigation, true)}</details>
    <p class="ts-help">날짜 경과만으로 다음 단계에 불이 켜지지 않습니다. 수록 공고에 나온 사건·POR·공식 행위만 표시합니다. 법원·CBP의 실제 진행 자동 갱신은 아직 연결되지 않았습니다.</p></section>`;
}
function output() {
  if (!hasADCase()) return '<div class="ts-empty"><h2>기업별 AD 예치율 미확정</h2><p>이 선택에는 예치액·공표 세율·단계 결과를 표시하지 않습니다. 기업 손익 시나리오는 별도 화면에서 입력할 수 있습니다.</p></div>';
  if (!result) return `<div class="ts-empty"><h2>반덤핑 예치 부담 비교</h2><p>예시 금액·기간이 채워져 있습니다. 실제 거래에 맞게 수정하고 제품 범위·법인 조건을 확인하면 계산할 수 있습니다.</p></div>`;
  const r = result;
  return `<div data-ad-calculated class="${dirty ? 'is-stale' : ''}"><div class="ts-section-label"><h2>AD 현금예치 부담 비교</h2><button type="button" class="ts-export" data-ad-export${dirty ? ' disabled' : ''}>반덤핑 JSON 저장</button></div><p data-ad-stale class="ts-stale"${dirty ? '' : ' hidden'}>입력이 바뀌었습니다. 다시 계산하세요.</p>
    ${r.status === 'unresolved' ? `<p class="ts-unverified">${esc(r.reference.reason)}</p><p>예치액을 산출하지 않았습니다. 공식 자료를 추가 확인하거나 출처를 남기고 직접 입력하세요.</p>` : `<p>${esc(r.reference.company.name)} · ${esc(r.reference.case_id)} · ${esc(r.reference.entry_date)} 통관 가정</p><p class="ts-help">${r.reference.status === 'published_reference' ? `선별 공표 참고율 ${fmt(r.reference.rate_pct)}% · ${link(r.reference.document)}` : `사용자 확인 참고율 ${fmt(r.reference.rate_pct)}% · ${link({ url: r.reference.source.url, label: '입력 출처' })}`}</p>
    <p class="ts-basis" data-ad-normalized><b>신고가격 10만 USD당 비교: 기준 $${money(r.normalized_reference.reference_deposit_usd)} / 가정 $${money(r.normalized_reference.scenario_deposit_usd)}</b><br><small>단위 금액에 대한 비교이며 실제 거래금액이 아닙니다. 금리5%·365일·+5%p는 계산 예시이며 업계 평균·예상 판정이 아닙니다.</small></p>
    <p class="ts-help">거래금액·금리·기간·비교율은 ${r.input_guidance.some(x => x.origin === 'editable_example') ? '예시 또는 사용자 입력' : '사용자 입력'}입니다. 최종 관세나 회사의 실제 수입 실적을 확정하지 않습니다.</p><div class="ts-kpis"><div><span>기준 AD 예치액</span><strong>$${money(r.reference_deposit_usd)}</strong></div><div><span>가정 AD 예치액</span><strong>$${money(r.scenario_deposit_usd)}</strong></div><div><span>추가로 묶이는 현금</span><strong>$${money(r.deposit_change_usd)}</strong></div></div>
    <section class="ts-result-block"><h3>자금 부담</h3><div class="ts-scroll"><table class="ts-output-table"><thead><tr><th>USD</th><th>공표·확인 참고율</th><th>가정 예치율</th><th>차이</th></tr></thead><tbody><tr><th>현금예치</th><td>${money(r.reference_deposit_usd)}</td><td>${money(r.scenario_deposit_usd)}</td><td>${money(r.deposit_change_usd)}</td></tr><tr><th>가정 기간 금융비용</th><td>${money(r.reference_financing_cost_usd)}</td><td>${money(r.scenario_financing_cost_usd)}</td><td>${money(r.financing_change_usd)}</td></tr></tbody></table></div><p class="ts-help">${esc(r.limitations.join(' '))}</p></section>`}</div>`;
}
function methodOutput() {
  if (!methodResult) return '<p>조사기업 마진을 확인하고 산정 경로를 비교하세요.</p>';
  return `<p><b>${methodResult.rate_pct == null ? '세율 자동 산정 불가' : `교육용 산정값 ${fmt(methodResult.rate_pct)}%`}</b><br>${esc(methodResult.reason)}</p>${methodResult.excluded.map(x => `<p class="ts-help">제외: ${esc(x.name)} ${fmt(x.margin_pct)}% · ${esc(x.reason)}</p>`).join('')}`;
}
function methodEditor() {
  if (!hasADCase()) return '';
  const c = selectedCase();
  return `<details class="ts-ad-method"><summary>비선정 기업 세율 산정 · 교육용</summary><p>시장경제 국가의 행정재심 원리 비교입니다. 조사기업의 0%·미소마진·전적으로 가용정보에 의존한 마진을 제외합니다. 모두 제외되면 다른 합리적 방법이 필요합니다.</p>
    <label>공표 사례 불러오기<select data-ad-segment aria-label="비선정 산정 사례">${c.segments.map(s => `<option value="${s.document_id}"${s.document_id === methodSegment ? ' selected' : ''}>${s.document_id} · ${s.stage === 'final' ? '최종' : '예비'}</option>`).join('')}</select></label>
    <form data-ad-method-form novalidate><div class="ts-ad-method-rows">${methodRows.map((r, i) => `<div class="ts-tariff-card" data-ad-method-row="${i}"><div class="ts-fields"><label>조사기업 이름<input data-ad-method-key="name" aria-label="조사기업 ${i + 1} 이름" value="${esc(r.name)}" maxlength="100" required></label><label>조사기업 마진 %<input type="number" data-ad-method-key="margin_pct" aria-label="조사기업 ${i + 1} 마진" value="${esc(r.margin_pct)}" min="0" max="10000" step="0.000001" required></label><label>가중치<input type="number" data-ad-method-key="weight" aria-label="조사기업 ${i + 1} 가중치" value="${esc(r.weight)}" min="0" max="1000000000000" step="0.000001"${equalWeights ? ' disabled' : ''}><small>공개되지 않은 실제 가중치는 역추정하지 않습니다.</small></label></div><label class="ts-confirm"><input type="checkbox" data-ad-method-key="entirely_facts_available" aria-label="조사기업 ${i + 1} 전적으로 가용정보"${r.entirely_facts_available ? ' checked' : ''}>전적으로 가용정보에 의존한 마진</label><button type="button" data-ad-remove="${i}"${methodRows.length <= 1 ? ' disabled' : ''}>조사기업 삭제</button></div>`).join('')}</div>
    <button type="button" data-ad-add${methodRows.length >= 30 ? ' disabled' : ''}>조사기업 추가</button><label class="ts-confirm"><input type="checkbox" data-ad-equal aria-label="동일 가중치 가정"${equalWeights ? ' checked' : ''}><span>동일 가중치로 비교합니다 · 실제 산정 가중치가 아닌 사용자 가정</span></label><button type="submit" class="ts-primary">비선정 산정 경로 비교</button><p class="ts-error" data-ad-method-error role="alert" hidden></p></form>
    <div data-ad-method-output aria-live="polite">${methodOutput()}</div><p class="ts-help">이 결과를 기업의 예치율로 자동 적용하지 않습니다. ${link(catalog.documents[methodSegment])} · <a href="https://www.govinfo.gov/content/pkg/USCODE-2024-title19/pdf/USCODE-2024-title19-chap4-subtitleIV-partII-sec1673d.pdf" target="_blank" rel="noopener noreferrer">19 U.S.C. §1673d(c)(5) · 2024 법전</a>. 신규 조사·중국 등 비시장경제의 별도율·CVD에는 이 경로를 적용하지 않습니다.</p></details>`;
}
export function antidumpingMarkup() {
  return `<div data-ad-simulator><div class="ts-intro"><div><span class="ts-eyebrow">반덤핑 · 사건과 법인별 공식 공고</span><h1>통상 공고·반덤핑 재심 현황</h1><p>대상 품목의 공식 공고와 조사·재심 흐름을 확인합니다. 기업 선택과 거래 계산은 필요할 때 이용합니다.</p></div><span class="ts-badge">${catalog.cases.length}개 사건 · ${catalog.cases.reduce((sum, c) => sum + c.companies.length, 0)}개 기업·법인그룹</span></div>
    <p class="ts-model-source">근거: 미국 상무부의 Federal Register 공고 · 자료 확인 ${catalog.checked_on}. 공표 마진, 현금예치, 사후 관세 확정을 구분합니다.</p><div class="ts-basis">${esc(catalog.coverage_note)}</div>
    <details class="ts-explainer ts-logic"><summary>계산 원리·용어</summary>
      <p class="ts-logic-flow">사건·제품·법인·통관일 확인 → 예치 참고율 확인 → 신고가격 × 예치율 ÷ 100</p>
      <dl><div><dt>현금예치율</dt><dd>통관 시 반덤핑 관세를 위해 미리 맡기는 금액의 비율입니다. 최종 확정 관세와 달라 추가 납부나 환급이 생길 수 있습니다.</dd></div>
      <div><dt>재심 대상 기간 (POR)</dt><dd>상무부가 과거 거래를 검토하는 기간입니다. 이후 통관에 적용되는 새 예치율의 발효일과 구분합니다.</dd></div>
      <div><dt>개별조사·비선정</dt><dd>직접 조사한 기업의 마진과 비선정 기업에 배정한 마진을 구분합니다. 배정 마진을 예치율로 자동 적용하지 않습니다.</dd></div>
      <div><dt>자금 부담</dt><dd>예치액 × 연 금융비용률 ÷ 100 × 예치 일수 ÷ 365. 사용자 금리·기간에 따른 가정 비용이며 세관이 확정한 이자가 아닙니다.</dd></div></dl>
      <p><a href="https://www.trade.gov/antidumping-and-countervailing-duty-frequently-asked-questions" target="_blank" rel="noopener noreferrer">상무부 재심·예치금 안내 ↗</a> · <a href="https://www.ecfr.gov/current/title-19/chapter-III/part-351/subpart-B/section-351.212" target="_blank" rel="noopener noreferrer">관세 확정 규정 19 CFR §351.212 ↗</a>. 선택한 사건·기업의 근거 공고는 단계 카드와 세율 이력에서 확인할 수 있습니다.</p>
    </details>
    <p class="ts-help" data-ad-origin>대상 원산지: 한국 · 현재 수록 사건은 한국산입니다. 기업 본사·선적 항구와 구분하며 다른 원산지의 AD 적용은 미검토입니다.</p><div data-ad-process>${processMarkup()}</div><div data-ad-history>${hasADCase() ? history() : coverageGap()}</div><div data-ad-notice-review>${monitorNotices()}</div><details class="ts-ad-calculator" data-ad-calculator${calculatorOpen ? ' open' : ''}><summary>선택 · 예치 부담 계산</summary><p class="ts-help">실제 거래의 통관일·신고가격·생산자/수출자 조건이 필요합니다. 품목 전체의 공고 흐름과 계산에 선택한 법인의 예치 참고율은 별개입니다.</p><div class="ts-layout"><section class="ts-editor" aria-label="반덤핑 시나리오 입력"><div class="ts-panel-title"><span>AD</span><h2>사건·거래 조건</h2></div><div data-ad-editor>${editor()}</div></section><section class="ts-results" data-ad-results aria-label="반덤핑 계산 결과">${output()}</section></div></details><div data-ad-method>${methodEditor()}</div>
    <footer class="ts-footer"><details><summary>반덤핑 모델·데이터 확보 범위·공식 출처</summary><p>예치액 = 대상 수입 신고가격 × AD 현금예치율. 금융비용 = 예치액 × 연 금리 × 일수 ÷ 365. USD 센트에서 한 번 반올림합니다.</p><p>공개 공고로 사건·법인별 마진·예비/최종·POR·예치 발효 조건을 확보할 수 있습니다. 제품 범위·생산자/수출자 조합·CBP 지침은 별도 확인해야 합니다. 실제 덤핑마진에는 거래별 미국 판매가격·정상가격·조정비용이 필요합니다.</p><p>로컬 수집기의 공고 발견 목록을 별도로 제공합니다. 세율·단계의 자동 적용과 메일 알림은 아직 연결되지 않았습니다. 예비판정·재심 개시·소송 접수만으로 예치율을 변경하지 않습니다.</p><p>${catalog.legal_sources.map(link).join(' · ')} · ${AD_MODEL_VERSION}</p></details></footer></div>`;
}
export function mountAntidumping(root, { openCompany } = {}) {
  const controller = new AbortController(), signal = controller.signal;
  const paint = () => { root.querySelector('[data-ad-calculator]').open = calculatorOpen; root.querySelector('[data-ad-history]').innerHTML = hasADCase() ? history() : coverageGap(); root.querySelector('[data-ad-editor]').innerHTML = editor(); root.querySelector('[data-ad-results]').innerHTML = output(); root.querySelector('[data-ad-process]').innerHTML = processMarkup(); root.querySelector('[data-ad-method]').innerHTML = methodEditor(); root.querySelector('[data-ad-notice-review]').innerHTML = monitorNotices(); };
  const updateGuide = () => { const panel = root.querySelector('[data-ad-input-guide]'), open = panel.querySelector('details')?.open; panel.innerHTML = inputGuide(); panel.querySelector('details').open = Boolean(open); };
  const clear = () => { clearFormErrors(root); dirty = true; const box = root.querySelector('[data-ad-error]'); if (box) box.hidden = true; root.querySelector('[data-ad-results]').innerHTML = output(); updateGuide(); root.querySelector('[data-ad-process]').innerHTML = processMarkup(); };
  const unconfirm = () => { draft.scope_confirmed = false; draft.identity_confirmed = false; };
  const syncExample = () => {
    example = createADExample(draft);
    for (const key of AD_GUIDE_FIELDS) if (key !== 'entry_date' && !editedFields.has(key)) draft[key] = example.values[key];
  };
  const chooseContext = (caseId, companyId) => {
    const c = catalog.cases.find(x => x.case_id === caseId);
    if (!c?.companies.some(x => x.id === companyId)) return;
    const changedCase = draft.case_id !== caseId;
    if (hasADCase() && !changedCase && draft.reference_mode === 'published' && draft.company_id === companyId) { paint(); return; }
    industryId = COMPANY_INDUSTRIES.find(x => x.case_id === caseId).id; profileId = '';
    draft.reference_mode = 'published'; draft.case_id = caseId; draft.company_id = companyId;
    try { if (lookupAD(draft).status === 'unresolved') result = null; } catch { result = null; }
    if (changedCase) { companySearch = ''; allCompaniesOpen = false; processRecordId = ''; methodSegment = c.segments.at(-1).document_id; seedMethod(); root.querySelector('[data-ad-method]').innerHTML = methodEditor(); }
    unconfirm(); syncExample(); dirty = true; paint();
  };
  const chooseIndustry = industry => {
    companySearch = ''; allCompaniesOpen = false;
    overview = true; calculatorOpen = false; processRecordId = '';
    if (industry.case_id) chooseContext(industry.case_id, catalog.cases.find(c => c.case_id === industry.case_id).companies[0].id);
    else { industryId = industry.id; profileId = industry.profiles[0]; result = null; dirty = true; unconfirm(); paint(); }
  };
  root.addEventListener('toggle', event => { if (root.contains(event.target) && event.target.hasAttribute('data-ad-all')) allCompaniesOpen = event.target.open; if (event.target.hasAttribute('data-ad-calculator')) calculatorOpen = event.target.open; }, { capture: true, signal });
  root.addEventListener('input', event => {
    const el = event.target;
    if (el.hasAttribute('data-ad-search')) {
      companySearch = el.value; allCompaniesOpen = true;
      root.querySelector('[data-ad-featured]').hidden = Boolean(companySearch.trim());
      root.querySelector('[data-ad-search-results]').innerHTML = companySearchResults();
      return;
    }
    if (el.hasAttribute('data-ad-family')) { chooseIndustry(COMPANY_INDUSTRIES.find(x => x.family === el.value)); root.querySelector('[data-ad-family]').focus({ preventScroll: true }); return; }
    if (el.dataset.adKey) {
      const key = el.dataset.adKey; if (['case_id','company_id','reference_mode'].includes(key)) overview = false; draft[key] = el.type === 'checkbox' ? el.checked : el.value;
      if (AD_GUIDE_FIELDS.includes(key)) editedFields.add(key);
      if (['reference_mode', 'case_id', 'company_id', 'entry_date', 'manual_case_id', 'company_name', 'reference_rate_pct', 'reference_url', 'reference_note'].includes(key)) {
        unconfirm();
        if (key === 'case_id') { companySearch = ''; allCompaniesOpen = false; industryId = COMPANY_INDUSTRIES.find(x => x.case_id === draft.case_id).id; profileId = ''; draft.company_id = selectedCase().companies[0].id; methodSegment = selectedCase().segments.at(-1).document_id; seedMethod(); root.querySelector('[data-ad-method]').innerHTML = methodEditor(); }
        if (['reference_mode', 'case_id', 'company_id', 'entry_date'].includes(key)) syncExample();
        if (draft.reference_mode === 'published') { try { if (lookupAD(draft).status === 'unresolved') result = null; } catch { result = null; } }
        if (el.matches('select')) paint();
        else { root.querySelectorAll('[data-ad-key$="confirmed"]').forEach(c => { c.checked = false; }); if (key === 'entry_date' && draft.reference_mode === 'published') { root.querySelector('[data-ad-reference]').outerHTML = (() => { const t = document.createElement('div'); t.innerHTML = referencePanel(); return t.querySelector('[data-ad-reference]').outerHTML; })(); root.querySelector('[data-ad-key="scenario_rate_pct"]').value = draft.scenario_rate_pct; } }
      }
      clear();
    } else if (el.hasAttribute('data-ad-process-record')) { processRecordId = el.value; root.querySelector('[data-ad-process]').innerHTML = processMarkup(); }
    else if (el.hasAttribute('data-ad-segment')) { methodSegment = el.value; seedMethod(); root.querySelector('[data-ad-method]').innerHTML = methodEditor(); root.querySelector('.ts-ad-method').open = true; }
    else if (el.hasAttribute('data-ad-equal')) { equalWeights = el.checked; methodResult = null; root.querySelector('[data-ad-method]').innerHTML = methodEditor(); root.querySelector('.ts-ad-method').open = true; }
    else if (el.dataset.adMethodKey) { methodRows[Number(el.closest('[data-ad-method-row]').dataset.adMethodRow)][el.dataset.adMethodKey] = el.type === 'checkbox' ? el.checked : el.value; methodResult = null; clearFormErrors(root.querySelector('[data-ad-method]')); root.querySelector('[data-ad-method-error]').hidden = true; root.querySelector('[data-ad-method-output]').innerHTML = methodOutput(); }
  }, { signal });
  root.addEventListener('submit', event => {
    const form = event.target; if (!form.matches('[data-ad-form], [data-ad-method-form]')) return; event.preventDefault();
    const method = form.matches('[data-ad-method-form]'), box = root.querySelector(method ? '[data-ad-method-error]' : '[data-ad-error]');
    const issue = firstFormIssue(form);
    if (issue) { showFormError(root, box, issue); return; }
    try {
      clearFormErrors(root); box.hidden = true;
      if (method) { methodResult = nonSelectedScenario({ rows: methodRows, equal_weights_assumption: equalWeights }); root.querySelector('[data-ad-method-output]').innerHTML = methodOutput(); }
      else { result = { ...simulateDeposit({ ...draft, case_id: draft.reference_mode === 'manual' ? draft.manual_case_id : draft.case_id }), input_guidance: describeADInputs(draft, example, [...editedFields]) }; dirty = false; root.querySelector('[data-ad-results]').innerHTML = output(); }
    } catch (err) { showFormError(root, box, { message: err.message }); }
  }, { signal });
  root.addEventListener('click', event => {
    const el = event.target.closest('button'); if (!el || !root.contains(el)) return;
    if (el.hasAttribute('data-ad-overview')) { overview = true; calculatorOpen = false; processRecordId = ''; paint(); return; }
    if (el.hasAttribute('data-ad-case')) {
      overview = true; calculatorOpen = false; processRecordId = '';
      const caseId = el.dataset.adCase, c = catalog.cases.find(x => x.case_id === caseId);
      if (!c) return;
      chooseContext(caseId, caseId === draft.case_id && c.companies.some(x => x.id === draft.company_id) ? draft.company_id : c.companies[0].id);
      root.querySelector(`[data-ad-case="${caseId}"]`).focus({ preventScroll: true });
    }
    else if (el.hasAttribute('data-ad-company')) {
      overview = false;
      const companyId = el.dataset.adCompany;
      chooseContext(draft.case_id, companyId);
      [...root.querySelectorAll(`[data-ad-company="${companyId}"]`)].find(b => b.getClientRects().length)?.focus({ preventScroll: true });
    }
    else if (el.hasAttribute('data-ad-industry')) {
      const industry = COMPANY_INDUSTRIES.find(x => x.id === el.dataset.adIndustry);
      if (!industry || industry.case_id || industry.id === industryId) return;
      chooseIndustry(industry);
      root.querySelector(`[data-ad-industry="${industryId}"]`).focus({ preventScroll: true });
    }
    else if (el.hasAttribute('data-ad-profile')) {
      if (!selectedIndustry().profiles.includes(el.dataset.adProfile) || (!overview && profileId === el.dataset.adProfile)) return;
      overview = false;
      profileId = el.dataset.adProfile; paint(); root.querySelector(`[data-ad-profile="${profileId}"]`).focus({ preventScroll: true });
    }
    else if (el.hasAttribute('data-ad-open-company') && !hasADCase()) openCompany?.(profileId, selectedIndustry().product);
    else if (el.hasAttribute('data-ad-reset')) { overview = true; calculatorOpen = true; companySearch = ''; allCompaniesOpen = false; draft = initial(); industryId = 'transformer'; profileId = ''; example = createADExample(draft); editedFields = new Set(); processRecordId = ''; result = null; dirty = true; methodSegment = '2026-16663'; seedMethod(); root.innerHTML = antidumpingMarkup(); }
    else if (el.hasAttribute('data-ad-example')) { draft.entry_date = catalog.checked_on; example = createADExample(draft); Object.assign(draft, example.values); editedFields = new Set(); unconfirm(); dirty = true; paint(); }
    else if (el.hasAttribute('data-ad-days')) { draft.holding_days = el.dataset.adDays; editedFields.add('holding_days'); root.querySelector('[data-ad-key="holding_days"]').value = draft.holding_days; clear(); }
    else if (el.hasAttribute('data-ad-add') || el.hasAttribute('data-ad-remove')) { if (el.hasAttribute('data-ad-add') && methodRows.length < 30) methodRows.push({ name: '', margin_pct: '', weight: '', entirely_facts_available: false }); else if (el.hasAttribute('data-ad-remove') && methodRows.length > 1) methodRows.splice(Number(el.dataset.adRemove), 1); methodResult = null; root.querySelector('[data-ad-method]').innerHTML = methodEditor(); root.querySelector('.ts-ad-method').open = true; }
    else if (el.hasAttribute('data-ad-export') && !dirty && result) { const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), ...result }, null, 2)], { type: 'application/json' }), url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = 'antidumping-deposit-scenario.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  }, { signal });
  return () => controller.abort();
}
