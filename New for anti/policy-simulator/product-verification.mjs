import { JAPAN_VERIFICATIONS } from './japan-verification.mjs';
import { CHINA_VERIFICATIONS } from './china-verification.mjs';
import { VIETNAM_VERIFICATIONS } from './vietnam-verification.mjs';
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
// A bounded search is evidence of what was checked, never a legal clearance.
// Historical / mismatched cases stay here, outside AD_CATALOG and stage events.
const materialSearches = {
  fiber: {
    terms: ['polyester tire cord Korea antidumping', 'tire cord fabric Korea 5902 antidumping'],
    scope: '한국산 폴리에스터 고강력사 타이어코드 직물 대표 사양. 단섬유·원사·스틸코드·완성 타이어와 구분합니다.',
    findings: [
      { title: '폴리에스터 단섬유 사건 · 제품 불일치', case_id: 'A-580-839', country: 'KOR', disposition: 'different_product', document_id: '2017-02790', published: '2017-02-10',
        note: '공고의 대상은 절단된 폴리에스터 단섬유입니다. 타이어코드 직물에 이 사건의 마진·예치율을 이식하지 않습니다. 현재 직물의 적용 제외 판정이나 scope ruling은 아닙니다.',
        source: { title: 'Commerce · 폴리에스터 단섬유 명령 범위 · 2017-02790', url: 'https://www.govinfo.gov/content/pkg/FR-2017-02-10/pdf/2017-02790.pdf' } },
    ],
    sources: [hts('5902.20.00'), { title: 'USITC · 한국·대만 폴리에스터 단섬유 일몰재심 · 2022-07-26', url: 'https://www.usitc.gov/press_room/news_release/2022/er0726ll1965.htm' }],
    remaining: '직물/원사·수지 처리·실제 생산국과 제조/수출 법인 확인 및 최신 사건·scope ruling 대조 필요.',
  },
  'carbon-fiber': {
    terms: ['carbon fiber Korea antidumping duty', 'carbon fibers antidumping Japan'],
    scope: '한국산 탄소섬유. 탄소섬유 자체·직물·프리프레그·활성탄·탄소강을 구분합니다.',
    findings: [],
    sources: [hts('6815.11'), hts('6815.12'), hts('6815.13')],
    remaining: '직접 대응 AD/CVD 사건은 이번 검색에서 확인하지 못했습니다. PAN 원료·수지 함침·복합재 등 실제 형태와 최신 사건·scope ruling 확인 필요. 탄소강 AD 공고나 FTZ 생산 허가를 탄소섬유 AD 판정으로 연결하지 않습니다.',
  },
  aramid: {
    terms: ['aramid Korea antidumping duty', 'aramid fiber Netherlands revocation antidumping'],
    scope: '한국산 아라미드. 파라/메타·원사·단섬유·펄프·직물과 생산국을 구분합니다.',
    findings: [
      { title: '네덜란드산 아라미드 과거 사건 · 철회', case_id: 'A-421-805', country: 'NLD', disposition: 'historical_other_origin_revoked', document_id: '01-6226', published: '2001-03-13', revoked_effective_date: '2000-01-01',
        note: '2001년 공고는 네덜란드산 PPD-T 아라미드 명령 철회를 알리며 효력일은 2000-01-01입니다. 한국산 ALKEX·HS효성의 현재 사건·예치율이 아닙니다. 당시 명령 범위는 타이어코드를 제외했습니다.',
        source: { title: 'Commerce · 네덜란드산 아라미드 명령 철회 · 01-6226', url: 'https://www.govinfo.gov/content/pkg/FR-2001-03-13/pdf/01-6226.pdf' } },
    ],
    sources: [hts('5402.11'), hts('5503.11')],
    remaining: '한국산 직접 대응 사건 미확인. 실제 섬유 형태·법인·생산국 및 최신 사건·scope ruling 대조 필요. 네덜란드 과거 세율을 한국산에 적용하지 않습니다.',
  },
};
for (const [product, research] of Object.entries(materialSearches)) {
  rows[product] = { checked_on: '2026-10-14', ad: {
    status: 'bounded_search_no_confirmed_case', label: '공식 자료 조사 · 한국산 대응 AD/CVD 사건 미확인',
    rate_pct: null, case_ids: [],
    note: '품목별 공식 검색과 공개 원문을 대조한 결과입니다. 사건 전수조회·적용 제외 확인이 아니며 면제나 0% 판정이 아닙니다.',
    research: { checked_on: '2026-10-14', method: '공식 도메인 웹 검색·공개 원문 범위 대조. ACCESS 활성 목록 전수 재조회는 미실행.', ...research },
    sources: [...research.sources, ...research.findings.map(f => f.source)],
  } };
}
export const PRODUCT_VERIFICATIONS = rows;

// Our investigation coverage and the government's proceeding are independent.
// Missing data must never be relabelled as an official pending determination.
export function adCoverageStatus(product, country = 'KOR') {
  const row = country === 'KOR' ? rows[product] : country === 'VNM' ? VIETNAM_VERIFICATIONS[product] : country === 'CHN' ? CHINA_VERIFICATIONS[product] : country === 'JPN' ? JAPAN_VERIFICATIONS[product] : null, status = row?.ad.status;
  const basic = {
    research: { state: 'not_recorded', label: '조사 기록 없음', note: '이 품목·원산지의 조사 기록이 없습니다.' },
    procedure: { state: 'unconfirmed', label: '공식 절차 미확인', note: '사건 존재·판정 대기 여부를 확인하지 못했습니다.' },
    integration: { state: 'not_ready', label: '계산 미연결', note: '적용 사건·기업별 예치율 근거가 필요합니다.' },
    checked_on: null, next_step: '공식 사건·제품 범위 조사 필요',
  };
  if (!row) return basic;
  basic.checked_on = row.checked_on || KOREA_AD_REVIEW.checked_on;
  if (status === 'reviewed_no_direct_match') {
    basic.research = { state: 'roster_reviewed', label: '사건 목록 조사 완료 · 제한 범위', note: '한국 활성 사건의 제품명 대조만 완료했습니다. 개별 제품·법인 적용 검토는 미완료입니다.' };
    basic.procedure = { state: 'case_unconfirmed', label: '대응 사건 미확인', note: '검토한 목록에서 직접 대응 사건을 찾지 못했습니다. 정부 판정 대기로 확인된 상태가 아닙니다.' };
    basic.next_step = '제품 사양·최신 공고·개별 적용 범위 추가 확인 필요';
  } else if (status === 'bounded_search_no_confirmed_case') {
    basic.research = { state: 'product_search_reviewed', label: '품목별 조사 완료 · 제한 범위', note: '공식 검색·공개 원문 대조 완료. 사건 전수조사는 아닙니다.' };
    basic.procedure = { state: 'case_unconfirmed', label: '대응 사건 미확인', note: '선택 원산지의 적용 사건과 기업별 예치율 미확인. 정부 판정 대기로 확인된 상태가 아닙니다.' };
    basic.next_step = row.ad.research.remaining;
  } else if (status === 'related_scope_review_required') {
    basic.research = { state: 'related_notice_reviewed', label: '관련 공고 조사 완료', note: '관련 제품의 조사 개시·정정 공고를 확인했습니다.' };
    basic.procedure = { state: 'related_case_scope_unresolved', label: '관련 조사 개시 · 적용 대상 미확인', note: '선택 제품·기업이 해당 조사 대상인지 미확정입니다. 이 선택의 판정 대기로 단정하지 않습니다.' };
    basic.next_step = '실제 제품 사양·제조/수출 법인과 명령 범위 대조 필요';
  } else if (status === 'official_case_confirmed_deposit_unresolved') {
    basic.research = { state: 'final_notice_reviewed', label: '최종결과 공고 조사 완료', note: '해당 POR의 공식 사건과 기업별 최종 마진을 확인했습니다.' };
    basic.procedure = { state: 'final_published', label: '해당 POR 최종결과 공표', note: '정부 판정은 공표됐습니다. 현행 예치 지침·후속 변경은 별도 확인 대상입니다.' };
    basic.integration = { state: 'deposit_interpretation_pending', label: '예치율 적용 검토 · 계산 보류', note: '자료 해석·연결 보류이며 정부의 최종결과 대기가 아닙니다.' };
    basic.next_step = '기업별 현행 예치 지침 확인·계산 연결 필요';
  }
  if (status === 'ad_cvd_order_confirmed') {
    basic.research = {state:'official_notices_reviewed',label:'AD·CVD 명령 유지 공고 확인',note:'두 제도의 사건번호·제품 범위·공표일과 명령 유지 효력일을 구분했습니다.'};
    basic.procedure = {state:'orders_continued',label:'AD·CVD 명령 유지 확인',note:'수록 공고 기준입니다. 현행 기업별 예치율·최신 행정재심·판정 대기 여부는 별도 확인 대상입니다.'};
    basic.integration = {state:'current_rates_unresolved',label:'공고 연결 · 현행 예치율 계산 보류',note:'기업별 최신 AD/CVD 예치율·지침 미확인. 명령 유지·일몰재심 수치를 새 세율로 사용하지 않습니다.'};
    basic.next_step = row.ad.research.remaining;
  }
  if (['historical_order_revoked','ad_order_confirmed','final_notice_source_conflict'].includes(status)) {
    const states = {
      historical_order_revoked: ['historical_revocation','과거 AD finding 철회 확인','과거 사건의 철회이며 현재 모든 조치 부존재를 뜻하지 않습니다.'],
      ad_order_confirmed: ['ad_order_continued','AD 명령 유지 확인','수록 공고 기준입니다. 기업별 현행 예치율·후속 변경은 별도 확인 대상입니다.'],
      final_notice_source_conflict: ['final_published_conflict','최종결과 공표 · 본문 불일치 확인','최종 마진표를 연결했습니다. 정부 판정 대기가 아니라 자료 불일치 검토 중입니다.'],
    };
    const [state,label,note] = states[status];
    basic.research = {state:'official_notices_reviewed',label:'공식 공고 조사 완료 · 제한 범위',note:'서로 다른 제품·사건·공표일·효력일을 구분했습니다.'};
    basic.procedure = {state,label,note};
    basic.integration = status === 'final_notice_source_conflict'
      ? {state:'source_discrepancy_held',label:'공표 표 연결 · 본문 불일치로 계산 보류',note:'표 수치 확인과 자동 예치율 적용을 구분합니다. 공식 정정·결정문·지침 확인이 필요합니다.'}
      : {state:'not_ready',label:'공고 연결 · 예치율 계산 미연결',note:'과거 철회나 명령 유지에서 현행 예치율을 생성하지 않습니다.'};
    basic.next_step = row.ad.research.remaining;
  }
  if (status === 'cvd_confirmed_ad_terminated') {
    basic.research = {state:'official_notices_reviewed',label:'AD·CVD 구분 조사 완료',note:'과거 AD 종료·CVD 명령·일몰재심 결과·별도 행정재심 예정을 구분했습니다.'};
    basic.procedure = {state:'official_schedule_recorded',label:'CVD 행정재심 최종결과 발표 예정',note:`POR 2024-01-01~2024-12-31 · 공식 예정 2026-10-22 (10/15 확인). 변경 가능·완료 아님. 10/5 일몰재심 결과와 별개입니다.`};
    basic.integration = {state:'cvd_not_calculable',label:'CVD 공고 연결 · AD 계산 대상 아님',note:'최신 기업별 CVD 예치율·지침 미확인. AD 세율을 대신 쓰지 않습니다.'};
    basic.next_step = row.ad.research.remaining;
  }
  return basic;
}

export function productVerification(product, country = 'KOR') {
  const row = country === 'VNM' ? VIETNAM_VERIFICATIONS[product] : country === 'CHN' ? (CHINA_VERIFICATIONS[product] || rows[product]) : country === 'JPN' ? (JAPAN_VERIFICATIONS[product] || rows[product]) : rows[product];
  if (!row) return null;
  const result = structuredClone({ product, checked_on: KOREA_AD_REVIEW.checked_on, ...row });
  result.ad = country === 'KOR' ? { ...result.ad, country: 'KOR', review: structuredClone(KOREA_AD_REVIEW) } : country === 'VNM' ? { ...result.ad, country: 'VNM' } : country === 'CHN' && CHINA_VERIFICATIONS[product] ? { ...result.ad, country: 'CHN' } : country === 'JPN' && JAPAN_VERIFICATIONS[product] ? { ...result.ad, country: 'JPN' }
    : { status: 'origin_not_reviewed', country: country || null, rate_pct: null, case_ids: [], label: '이 원산지의 AD/CVD 검토 자료 미수록', note: '한국산 검토 결과를 다른 원산지 또는 미선택 원산지에 적용하지 않습니다.' };
  result.coverage = adCoverageStatus(product, country);
  return result;
}
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`;
export function coverageStatusMarkup(product, country = 'KOR') {
  const c = adCoverageStatus(product, country);
  return `<section class="ts-basis" data-ad-coverage><h3>자료·공식 절차·계산 연결</h3>${[['research','자료 조사'],['procedure','공식 절차'],['integration','계산 연결']].map(([key,label]) => `<p data-coverage-${key}="${esc(c[key].state)}"><b>${label}: ${esc(c[key].label)}</b><br><small>${esc(c[key].note)}</small></p>`).join('')}<p class="ts-help">${c.checked_on ? `자료 확인 ${esc(c.checked_on)} · ` : ''}다음 확인: ${esc(c.next_step)}</p><small>자료 미확인과 정부 판정 대기는 다릅니다. ‘확인 필요’는 예약된 조사 일정이 아니며, 사건 미확인은 AD 면제·0% 판정이 아닙니다.</small></section>`;
}
export function verificationMarkup(product, country = 'KOR') {
  const r = productVerification(product, country);
  if (!r) return '';
  return `${coverageStatusMarkup(product, country)}<details class="ts-basis" data-product-verification><summary>공식 자료 확인 결과 · ${esc(r.coverage.checked_on || '조사 기록 없음')}</summary>
    ${r.classification ? `<p><b>품목 분류:</b> ${esc(r.classification.hts ? `대표 HTS ${r.classification.hts} · 기본관세 ${r.classification.mfn_pct}%` : r.classification.label)}<br><small>${esc(r.classification.scope || r.classification.note)}</small></p><p>${r.classification.sources.map(link).join(' · ')}</p>` : ''}
    ${r.tariff ? `<p><b>관세 조건:</b> 한국·일본 승용차·경트럭용 지정 부품의 조건부 합산 ${r.tariff.total_pct}% 경로 확인<br><small>${esc(r.tariff.note)}</small></p><p>${r.tariff.sources.map(link).join(' · ')}</p>` : ''}
    <p><b>AD/CVD:</b> ${esc(r.ad.label)}${r.ad.case_ids.length ? ` · ${esc(r.ad.case_ids.join(' / '))}` : ''}<br><small>${esc(r.ad.note)}</small></p>
    ${r.ad.margins ? `<p>POR ${r.ad.por_start}~${r.ad.por_end} · 공표 ${r.ad.published}<br>${r.ad.margins.map(m=>`${esc(m.official_name)}: 최종 마진 ${esc(m.margin_pct)}%`).join('<br>')}<br><small>과거 재심 마진 · 현재 예치율 아님</small></p>` : ''}
    ${r.ad.published_margins ? `<section data-published-margins><h3>공표 최종 마진표 · 계산 연결 보류</h3><p>POR ${esc(r.ad.published_margins.por_start)}~${esc(r.ad.published_margins.por_end)} · 공표 ${esc(r.ad.published_margins.published)}</p><div class="ts-scroll"><table class="ts-output-table"><thead><tr><th>공고 법인·그룹</th><th>조사 구분</th><th>최종 마진 %</th></tr></thead><tbody>${r.ad.published_margins.rows.map(x=>`<tr><th>${esc(x.company)}</th><td>${esc(x.role)}</td><td>${esc(x.rate_pct)}</td></tr>`).join('')}</tbody></table></div><p class="ts-help">${esc(r.ad.published_margins.note)}</p>${link(r.ad.published_margins.source)}</section>` : ''}
    ${r.ad.research ? `<section data-material-research><h3>품목별 조사 근거</h3><p>${esc(r.ad.research.scope)}</p><p class="ts-help">확인 ${esc(r.ad.research.checked_on)} · ${esc(r.ad.research.method)}<br>검색어: ${r.ad.research.terms.map(esc).join(' / ')}</p>${r.ad.research.findings.map(f => `<p><b>${esc(f.title)}</b> · ${esc(f.case_id)} · 원산지 ${esc(f.country)}<br><small>공표 ${esc(f.published)}${f.continuation_effective_date ? ` · 명령 유지 효력 ${esc(f.continuation_effective_date)}` : ''}${f.revoked_effective_date ? ` · 철회 효력 ${esc(f.revoked_effective_date)}` : ''}<br>${esc(f.note)}</small><br>${link(f.source)}</p>`).join('')}<p><small>남은 확인: ${esc(r.ad.research.remaining)}</small></p></section>` : ''}
    ${r.ad.review ? `<p class="ts-help">${link(KOREA_AD_REVIEW.source)} · 목록 검토 ${esc(KOREA_AD_REVIEW.checked_on)} · 검색어 Korea · 6페이지/51개 사건 · 제품명 수동 대조</p>` : ''}
    ${r.ad.official_schedule ? `<p data-official-schedule>CVD 최종결과 예정: ${esc(r.ad.official_schedule.announced_for)} · POR ${esc(r.ad.official_schedule.por_start)}~${esc(r.ad.official_schedule.por_end)}<br><small>${esc(r.ad.official_schedule.note)}</small></p>` : ''}${(r.ad.sources || []).map(link).join(' · ')}
  </details>`;
}
