// Manual, bounded official-source review. A search miss is never an AD exemption.
export const KOREA_AD_REVIEW = {
  checked_on: '2026-10-12', country: 'KOR', query: 'Korea', pages_reviewed: 6,
  source: { title: '상무부 ACCESS · 활성 AD/CVD 사건 검색', url: 'https://access.trade.gov/adcvd' },
  case_ids: ['A-580-852','A-580-876','A-580-886','A-580-893','A-580-914','A-580-921','C-580-920','A-580-872','A-580-881','A-580-890','A-580-908','C-580-910','C-580-882','C-580-888','A-580-834','A-580-859','A-580-897','C-580-917','A-580-810','A-580-867','A-580-885','A-580-902','C-580-879','A-580-919','A-580-892','A-580-916','A-580-878','A-580-899','A-580-904','C-580-837','C-580-898','C-580-913','A-580-887','A-580-922','A-580-874','A-580-895','A-580-891','A-580-836','A-580-870','C-580-835','A-580-889','A-580-809','A-580-880','A-580-903','A-580-829','A-580-911','A-580-839','A-580-883','A-580-909','C-580-884','A-580-923'],
  limitation: '한국 관련 활성 사건의 제품명을 검토한 결과입니다. 명령의 서술 범위·우회수출·개별 scope ruling·다른 원산지를 전수 판정한 자료가 아닙니다. 사건 미발견은 AD/CVD 면제나 0% 판정이 아닙니다.',
};
const hts = code => ({ title: `USITC HTS ${code}`, url: `https://hts.usitc.gov/search?query=${code}` });
const chapter99 = { title: 'USITC 현행 Chapter 99 · Note 33(g)/(t)', url: 'https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099' };
const rows = {};
for (const product of ['vehicle','vehicle-hev','vehicle-phev','vehicle-ev','auto-brake','auto-steering','auto-electric-drive','switchgear','power-cable','submarine-cable','industrial-cable','fiber','carbon-fiber','aramid','truck-tire']) {
  rows[product] = { ad: { status: 'reviewed_no_direct_match', label: '한국 활성 사건 목록 검토 · 직접 대응 사건 미발견', rate_pct: null, case_ids: [], note: KOREA_AD_REVIEW.limitation } };
}
for (const [product, code, scope] of [
  ['auto-brake','8708.30.50','농업용 트랙터 이외 차량의 브레이크·서보브레이크 및 그 부분품 대표 분류. 실제 전자제어 단품·구성에 따라 분류가 다를 수 있습니다.'],
  ['auto-steering','8708.94.50.00','농업용 트랙터 이외 차량의 조향 휠·칼럼·박스 완성품 대표 분류. 주철·기타 부분품은 8708.94.70/75 등과 구분합니다.'],
  ['auto-suspension','8708.80.16','농업용 트랙터 이외 차량의 현가 시스템 중 McPherson strut 이외 대표 분류. strut 및 주철·기타 부분품과 구분합니다.'],
]) {
  rows[product] ||= {};
  rows[product].classification = { status: 'representative_scope_confirmed', hts: code, mfn_pct: 2.5, scope, sources: [hts(code), chapter99] };
  rows[product].tariff = { status: 'conditional_rule_confirmed', countries: ['KOR','JPN'], total_pct: 15, note: 'Note 33(g)의 승용차·경트럭용 부품, 실제 HTS·원산지·용도 일치와 적용 조건 확인 필요. 일반관세를 15%에 다시 더하지 않습니다. AD/CVD·별도 추가세 및 수입조정 상계는 별도 검토합니다.', sources: [hts('9903.94.63'), hts('9903.94.43'), chapter99] };
}
rows['auto-electric-drive'].classification = { status: 'specification_required', label: '모터·인버터 분류 후보 확인 · 구체 사양 필요', note: '모터는 8501, 정지형 변환기는 8504.40 후보입니다. 정격 출력·AC/DC·변환 기능·단품/조립체에 따라 달라져 HTS8과 세율을 확정하지 않습니다. 자동차 전용이라는 이유만으로 8708을 적용하지 않습니다.', sources: [hts('8501'), hts('8504.40'), chapter99] };
rows['auto-suspension'].ad = { status: 'related_scope_review_required', label: '관련 유압실린더 조사 확인 · 현가 제품 범위 대조 필요', case_ids: ['A-580-923'], rate_pct: null,
  note: '2026-18706의 선형 유압실린더 조사와 정정 2026-19374를 확인했습니다. 현가장치 전체나 HL만도를 조사 대상으로 확정하지 않습니다. 실제 실린더 설계·치수·기능·구성품과 서술 범위 대조가 필요하며 제소 주장 마진을 예치율로 사용하지 않습니다.',
  sources: [{ title: '유압실린더 조사 개시 · 2026-18706', url: 'https://www.govinfo.gov/content/pkg/FR-2026-09-14/pdf/2026-18706.pdf' }, { title: '조사 개시 정정 · 2026-19374', url: 'https://www.govinfo.gov/content/pkg/FR-2026-09-22/pdf/2026-19374.pdf' }] };
rows.octg = { ad: { status: 'official_case_confirmed_deposit_unresolved', label: 'OCTG 공식 사건·최종 마진 확인 · 예치 적용 검토', case_ids: ['A-580-870','C-580-913'], rate_pct: null,
  document_id: '2026-19529', por_start: '2023-09-01', por_end: '2024-08-31', published: '2026-09-24',
  margins: [{ official_name: 'SeAH Steel Corporation', margin_pct: '9.80' }, { official_name: 'NEXTEEL Co., Ltd.', margin_pct: '29.94' }],
  note: '2026-19529의 기업별 최종 마진 표를 확인했습니다. Cash Deposit Requirements의 simple-average 문구와 개별 마진 표의 대응은 추가 지침 확인이 필요해 예치율 자동 계산에 사용하지 않습니다. 대구경 강관의 0.80%를 OCTG에 사용하지 않습니다. CVD 사건 존재는 ACCESS에서 확인했지만 이 화면에 CVD 세율을 확정하지 않았습니다.',
  sources: [{ title: 'OCTG 최종 결과 · 2026-19529', url: 'https://www.govinfo.gov/content/pkg/FR-2026-09-24/pdf/2026-19529.pdf' }] } };
export const PRODUCT_VERIFICATIONS = rows;

export function productVerification(product, country = 'KOR') {
  const row = rows[product];
  if (!row) return null;
  const result = structuredClone({ product, checked_on: KOREA_AD_REVIEW.checked_on, ...row });
  result.ad = country === 'KOR' ? { ...result.ad, country: 'KOR', review: structuredClone(KOREA_AD_REVIEW) }
    : { status: 'origin_not_reviewed', country: country || null, rate_pct: null, case_ids: [], label: '이 원산지의 AD/CVD 검토 자료 미수록', note: '한국산 검토 결과를 다른 원산지 또는 미선택 원산지에 적용하지 않습니다.' };
  return result;
}
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`;
export function verificationMarkup(product, country = 'KOR') {
  const r = productVerification(product, country);
  if (!r) return '';
  return `<details class="ts-basis" data-product-verification><summary>공식 자료 확인 결과 · ${esc(r.checked_on)}</summary>
    ${r.classification ? `<p><b>품목 분류:</b> ${esc(r.classification.hts ? `대표 HTS ${r.classification.hts} · 기본관세 ${r.classification.mfn_pct}%` : r.classification.label)}<br><small>${esc(r.classification.scope || r.classification.note)}</small></p><p>${r.classification.sources.map(link).join(' · ')}</p>` : ''}
    ${r.tariff ? `<p><b>관세 조건:</b> 한국·일본 승용차·경트럭용 지정 부품의 조건부 합산 ${r.tariff.total_pct}% 경로 확인<br><small>${esc(r.tariff.note)}</small></p><p>${r.tariff.sources.map(link).join(' · ')}</p>` : ''}
    <p><b>AD/CVD:</b> ${esc(r.ad.label)}${r.ad.case_ids.length ? ` · ${esc(r.ad.case_ids.join(' / '))}` : ''}<br><small>${esc(r.ad.note)}</small></p>
    ${r.ad.margins ? `<p>POR ${r.ad.por_start}~${r.ad.por_end} · 공표 ${r.ad.published}<br>${r.ad.margins.map(m=>`${esc(m.official_name)}: 최종 마진 ${esc(m.margin_pct)}%`).join('<br>')}<br><small>과거 재심 마진 · 현재 예치율 아님</small></p>` : ''}
    ${r.ad.review ? `<p class="ts-help">${link(KOREA_AD_REVIEW.source)} · 검색어 Korea · 6페이지/51개 사건 · 제품명 수동 대조</p>` : ''}
    ${(r.ad.sources || []).map(link).join(' · ')}
  </details>`;
}
