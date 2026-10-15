import { PRODUCTS, policyOptions } from './policy-catalog.mjs';
import { COMPANY_INDUSTRIES, COMPANY_PROFILES, companyCalibration } from './company-profiles.mjs';
import { productVerification } from './product-verification.mjs';

// Evidence for monitoring, never a source of automatic rates or company stages.
const autoProducts = ['vehicle', 'vehicle-hev', 'vehicle-phev', 'vehicle-ev', 'auto-brake', 'auto-steering', 'auto-suspension'];
const koreaAutoNotice = {
  document_id: '2025-21940', published: '2025-12-04', checked_on: '2026-10-13',
  kind: 'section_232', stage: '시행 공고', agency: '상무부·USTR',
  title: '한미 합의 관세 시행 · 자동차·자동차 부품 Part A',
  url: 'https://www.govinfo.gov/content/pkg/FR-2025-12-04/pdf/2025-21940.pdf',
  entry_effective_date: '2025-11-01',
  note: 'Part A의 한국산 대상 자동차·부품 통관 적용일과 공고 발행일을 구분합니다. 실제 HTS·원산지·용도·후속 변경 확인 필요. AD/CVD 판정이 아닙니다.',
};
export function industryMonitor(product, country = 'KOR') {
  const group = COMPANY_INDUSTRIES.find(i => i.product === product);
  if (!group || !PRODUCTS[product]) return null;
  if (['VNM','CHN','JPN'].includes(country)) {
    const countryName = ({VNM:'베트남',CHN:'중국',JPN:'일본'})[country];
    const v = productVerification(product,country);
    if (!v || v.ad.status === 'origin_not_reviewed') return {product,country,status:'origin_not_reviewed',events:[],sources:[],calculation_enabled:false};
    return {product,country,status:'sources_only',events:[],sources:v.ad.sources.map(s=>({...s,kind:`${countryName}산 미국 공식 조사 근거`})),calculation_enabled:false,review:v.ad.status,
      note:`${countryName}산 선별 조사입니다. AD/CVD·제품 범위·절차를 구분하며 한국산 예치율과 단계는 적용하지 않습니다.`};
  }
  if (country !== 'KOR') return { product, country, status: 'origin_not_reviewed', events: [], sources: [], calculation_enabled: false };
  const verification = productVerification(product, country), events = [];
  if (autoProducts.includes(product)) events.push({ ...koreaAutoNotice });
  if (product === 'octg') events.push({
    document_id: '2026-19529', published: '2026-09-24', checked_on: '2026-10-13',
    kind: 'antidumping', stage: '행정재심 최종결과', agency: '상무부',
    case_ids: ['A-580-870'], por_start: '2023-09-01', por_end: '2024-08-31',
    title: '한국산 OCTG · 2023~2024 재심 최종결과',
    url: 'https://www.govinfo.gov/content/pkg/FR-2026-09-24/pdf/2026-19529.pdf',
    note: '해당 POR의 최종결과 공고입니다. 기업별 마진은 위 공식 자료 확인 결과에 수록했습니다. 예치 조항의 적용은 추가 확인이 필요하며 마진을 현재 예치율로 사용하지 않습니다. CVD 사건 세율·소송·CBP 정산은 별도 미확인.',
  });
  if (product === 'auto-suspension') for (const [id,date,stage] of [['2026-18706','2026-09-14','관련 조사 개시'],['2026-19374','2026-09-22','관련 조사 개시 정정']]) events.push({
    document_id: id, published: date, checked_on: '2026-10-12', kind: 'related_scope', stage,
    agency: '상무부', case_ids: ['A-580-923'], title: '선형 유압실린더 · 현가 제품 범위 대조 필요',
    url: `https://www.govinfo.gov/content/pkg/FR-${date}/pdf/${id}.pdf`,
    note: '관련 제품 범위 검토용 공고입니다. 현가장치 전체 또는 HL만도에 대한 조사·세율·단계 확정이 아닙니다.',
  });
  const sources = [];
  const add = (source, kind) => { if (source?.url && !sources.some(s => s.url === source.url)) sources.push({ ...source, kind }); };
  for (const option of policyOptions(product, country)) for (const source of option.sources) add(source, '관세 정책');
  for (const source of verification?.classification?.sources || []) add(source, '품목 분류');
  for (const source of verification?.ad?.sources || []) add(source, 'AD/CVD 관련 원문');
  add(verification?.ad?.review?.source, '한국 활성 사건 목록 검토');
  if (PRODUCTS[product].hts) add({ title: `대표 HTS ${PRODUCTS[product].hts}`, url: `https://hts.usitc.gov/search?query=${PRODUCTS[product].hts}` }, '품목 분류');
  for (const id of group.profiles) {
    const p = COMPANY_PROFILES[id], source = companyCalibration(id, product).selected_product_source;
    add(source ? { title: `${p.name} · 선택 제품 공식 자료`, url: source.url } : p.source || (p.financial && { title: `${p.name} · 공식 기업 자료 (제품 범위 별도 확인)`, url: p.financial.source_url }), '기업 공개자료');
  }
  return structuredClone({ product, country, status: events.length ? 'selected_official_notices' : 'sources_only',
    events: events.sort((a,b) => b.published.localeCompare(a.published)), sources,
    calculation_enabled: false, review: verification?.ad.status || null,
    note: '선별 공고·기존 검토 근거입니다. 최신 공고 전수조회·자동 갱신 또는 모든 기업의 적용 확정이 아닙니다.' });
}
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function industryMonitorMarkup(product, country = 'KOR') {
  const r = industryMonitor(product, country);
  if (!r) return '';
  if (r.status === 'origin_not_reviewed') return '<p class="ts-help" data-industry-monitor>이 원산지의 공고 검토 자료 미수록 · 한국산 공고를 적용하지 않습니다.</p>';
  return `<section class="ts-ad-notices" data-industry-monitor data-monitor-product="${esc(product)}"><h2>공식 공고·정책 근거</h2><p>${esc(r.note)}</p>
    ${r.events.length ? `<ol class="ts-ad-notice-list">${r.events.map(e=>`<li data-monitor-document="${esc(e.document_id)}"><span>${esc(e.published)} 발행 · ${esc(e.agency)} · ${esc(e.stage)} · 확인 ${esc(e.checked_on)}</span><b>${esc(e.title)}</b>${e.entry_effective_date ? `<small>대상 통관 적용일: ${esc(e.entry_effective_date)} · 이후 통관의 조건부 관세 경로</small>` : ''}${e.por_start ? `<small>조사대상 기간 (POR): ${esc(e.por_start)} ~ ${esc(e.por_end)}</small>` : ''}<small>${esc(e.note)}</small><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">공식 원문 ${esc(e.document_id)} ↗</a></li>`).join('')}</ol>` : ['VNM','CHN','JPN'].includes(country) ? '<p class="ts-unverified">선택 원산지의 원문 목록 연결 · 법인별 현행 예치율·단계 계산 미연결</p>' : '<p class="ts-unverified">개별 시행·조사 공고 목록 미수록 · 아래 확인 근거를 연결했습니다. 공고가 없거나 관세·AD 적용이 없다는 뜻이 아닙니다.</p>'}
    <details><summary>관세·분류·기업 검토 근거 · ${r.sources.length}개</summary><ul>${r.sources.map(s=>`<li>${esc(s.kind)} · <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.label)} ↗</a></li>`).join('')}</ul></details>
    <p class="ts-help">공고 연결과 예치율 계산은 별개입니다. 다른 품목·기업의 세율을 상속하지 않습니다.</p></section>`;
}
