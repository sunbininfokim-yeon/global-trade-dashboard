import { SUPPLIER_SNAPSHOT } from './suppliers-2025.mjs';

// A bounded review snapshot, not a live tariff classification service. Rates are
// explicit rules; never extracted from the policy monitor's prose rate_ko.
export const POLICY_AS_OF = '2026-10-11';
export { SUPPLIER_SNAPSHOT };
export const COUNTRIES = { USA: '미국', KOR: '한국', JPN: '일본', CHN: '중국', TWN: '대만',
  MEX: '멕시코', CAN: '캐나다', VNM: '베트남', IND: '인도', DEU: '독일', FRA: '프랑스',
  GBR: '영국', BRA: '브라질', AUT: '오스트리아', NLD: '네덜란드', TUR: '튀르키예',
  POL: '폴란드', KHM: '캄보디아', ITA: '이탈리아', CHE: '스위스', AUS: '호주',
  MYS: '말레이시아', SGP: '싱가포르', THA: '태국', SWE: '스웨덴', SVK: '슬로바키아',
  IDN: '인도네시아', PRT: '포르투갈', ROW: '기타국 합계' };
export const POLICY_SOURCES = {
  hts: { title: 'USITC HTS · 일반/특혜 관세', url: 'https://hts.usitc.gov/' },
  metals: { title: '232 금속 · 2026-04-02 공고 §3·§5 / Annex I-B·III·IV', url: 'https://www.whitehouse.gov/presidential-actions/2026/04/strengthening-actions-taken-to-adjust-imports-of-aluminum-steel-and-copper-into-the-united-states/' },
  metalAnnex: { title: '232 금속 HTS·함량 부속서', url: 'https://www.whitehouse.gov/wp-content/uploads/2026/04/Metals-ANNEXES-I-A-I-B-II-III-IV.pdf' },
  currentMetalAnnex: { title: '232 현행 Annex III · 2026-06-01', url: 'https://www.whitehouse.gov/wp-content/uploads/2026/06/Annex-III.pdf' },
  metalUpdate: { title: '232 미국산 금속 85% 조건 · 2026-06-01 §4', url: 'https://www.whitehouse.gov/presidential-actions/2026/06/further-adjusting-the-tariff-regimes-for-imports-of-aluminum-steel-and-copper-into-the-united-states/' },
  forcedLabor: { title: 'CBP 301 강제노동 관세 지침 · 2026-07-24 시행', url: 'https://content.govdelivery.com/accounts/USDHSCBP/bulletins/421d887' },
  forcedLaborAnnex: { title: '301 국가별 HTS·예외·섬유 쿼터 부속서', url: 'https://www.whitehouse.gov/wp-content/uploads/2026/07/ANNEX.pdf' },
  koreaAuto: { title: '한국 자동차 232 시행 공고 · 2025-21940 Part A', url: 'https://www.govinfo.gov/content/pkg/FR-2025-12-04/pdf/2025-21940.pdf' },
  japanAuto: { title: '일본 자동차 232 시행 공고 · 2025-17908', url: 'https://www.govinfo.gov/content/pkg/FR-2025-09-16/pdf/2025-17908.pdf' },
  china: { title: 'USTR 중국 301 목록·예외', url: 'https://ustr.gov/issue-areas/enforcement/section-301-investigations/tariff-actions' },
};
const semiconductorSource = { title: 'USITC 연구진 (2023), 표 4 · 메모리 σ=3.32', url: 'https://www.usitc.gov/sites/default/files/publications/332/working_papers/us_exposure_to_the_taiwanese_semiconductor_industry_11-21-2023_508.pdf#page=23' };
const tireSource = { title: 'USITC Pub.5212 (2021), II-30~31 · σ=3~6 · η=-0.50~-0.25', url: 'https://www.usitc.gov/sites/default/files/publications/701_731/pub5212.pdf#page=124' };
export const PRODUCTS = {
  transformer: { label: '전력용 변압기', hts: '8504.23.00', hts6: '850423', mfn: 1.6, family: 'metal_floor',
    scope: '액체절연 · 10MVA 초과. 철강 중량 15% 이상인 Annex III 제품을 비교합니다. 60MVA 이상 한국산은 A-580-867 등 AD 적용 여부·기업 세율을 별도 확인하세요.' },
  cable: { label: '전력 케이블', hts: '8544.60.20.00', hts6: '854460', mfn: 3.7, family: 'metal_add',
    scope: '1,000V 초과 · 커넥터 장착 · 알루미늄 중량 15% 이상인 Annex I-B 대표 사양. 구리 케이블·커넥터 없는 제품에는 이 조합을 쓰지 마세요.' },
  switchgear: { label: '차단기·배전기기', hts: '8535.21.00.00', hts6: '853521', mfn: 2.7, family: 'ordinary',
    scope: '1,000V 초과~72.5kV 미만 자동 차단기 대표 사양. 배전반·다른 전압·부품은 별도 HTS입니다.' },
  semiconductor: { label: '반도체 · 메모리', hts: '8542.32.00', hts6: '854232', mfn: 0, family: 'memory',
    scope: '메모리 집적회로만 포함. 301 강제노동 관세 Annex (b) 예외. 고성능 연산 칩·서버의 232 적용을 메모리에 일괄 적용하지 않습니다.',
    elasticity: { sigma: 3.32, source: semiconductorSource, kind: 'literature_proxy',
      note: '2023년 연구의 메모리 부문 보정값(2021년 자료). 현재 기업·규격별 추정치는 아닙니다.' } },
  vehicle: { label: '자동차 · 가솔린 승용', hts: '8703.23.01', hts6: '870323', mfn: 2.5, family: 'auto',
    scope: '배기량 1.5~3L 승용차 대표 사양. 한국·일본의 232 합산 15% 조합만 제공하며 다른 원산지는 직접 확인이 필요합니다.' },
  tire: { label: '타이어 · 승용차용', hts: '4011.10.10', hts6: '401110', mfn: 4, family: 'ordinary',
    scope: '승용차용 신품 래디얼 타이어 대표 사양. AD/CVD는 기업·사건별이므로 추가세 입력에서 확인하세요.',
    elasticity: { sigma: 4.5, range: [3, 6], eta: -0.375, source: tireSource, kind: 'literature_range_midpoint',
      note: '2021년 PVLT 타이어 문헌 범위 σ=3~6, η=-0.50~-0.25의 중간값. 승용차용 대표 사양에 쓰는 근사이며 국가 간 동일 σ는 모형 가정입니다.' } },
  fiber: { label: '산업용 섬유 · 타이어코드', hts: '5902.20.00.00', hts6: '590220', mfn: 5.8, family: 'ordinary',
    scope: '폴리에스터 타이어코드 직물 대표 사양. 나일론·아라미드·탄소섬유는 별도 품목입니다. 일부 국가의 섬유 쿼터는 직접 확인합니다.' },
  custom: { label: '직접 정의한 품목', hts: '', scope: '품목·원산지별로 검토한 현행 합산 종가세율을 직접 입력하세요.' },
};
const EU = new Set(['DEU', 'FRA', 'AUT', 'NLD', 'POL', 'ITA', 'SWE', 'SVK', 'PRT']);
const ten = new Set(['IND', 'GBR', 'KHM', 'MYS', 'IDN']);
const reviewed = new Set(Object.keys(COUNTRIES).filter(c => !['USA', 'ROW', 'CHN', 'CAN', 'MEX'].includes(c)));

export function missingPolicyReason(product, country) {
  if (country === 'ROW') return '여러 원산지의 합계에는 단일 현행 관세를 자동 적용할 수 없습니다. 검토한 가중 세율을 입력하세요.';
  if (country === 'CHN') return '중국 기존 301 목록·제품별 예외와 다른 추가관세의 검증이 필요합니다.';
  if (['CAN', 'MEX'].includes(country)) return 'USMCA 원산지·미국산 함량과 2026년 추가 조치를 거래별로 확인하세요.';
  if (product === 'fiber' && ['KHM', 'MYS', 'IDN'].includes(country)) return '섬유 TRQ의 미국산 투입재·쿼터 조건을 확인해야 합니다.';
  return '이 품목·국가의 전체 조합은 아직 검증되지 않았습니다. 현행 합산율을 직접 확인하세요.';
}

// These alternatives are conditions under existing policy, not arbitrary new
// presidential rates. Selecting one does not establish that a shipment qualifies.
export function policyOptions(product, country) {
  if (country === 'USA') return [{ id: 'domestic', label: '미국 국내 공급 · 수입관세 없음', rate: 0, sources: [], condition: '미국에서 생산되어 미국에 공급되는 제품' }];
  const p = PRODUCTS[product];
  if (!p?.family || !reviewed.has(country) || (product === 'fiber' && ['KHM', 'MYS', 'IDN'].includes(country))) return [];
  const hts = `https://hts.usitc.gov/search?query=${encodeURIComponent(p.hts)}`;
  const sources = [{ title: `USITC HTS ${p.hts}`, url: hts }];
  const make = (id, label, rate, refs, condition) => ({ id, label, rate, sources: [...sources, ...refs], condition });
  const scope = '대표 HTS·제품 사양·원산지 일치, 별도 추가세는 아래 입력. ';
  if (p.family === 'metal_floor') return [
    make('standard', '일반관세 + 232 · 합산 15% 하한', Math.max(p.mfn, 15), [POLICY_SOURCES.metals, POLICY_SOURCES.metalAnnex, POLICY_SOURCES.currentMetalAnnex], scope + '철강 중량 15% 이상. 러시아산 금속 등 특별 조치 없음. 2027-12-31까지.'),
    make('us_metal', '미국산 금속 조건 · 합산 10% 하한', Math.max(p.mfn, 10), [POLICY_SOURCES.metals, POLICY_SOURCES.metalUpdate], scope + '해당 철강의 85% 이상이 미국에서 용해·주조된 경우. 조건 충족에 따른 비교이며 조달비 변화는 별도.'),
  ];
  if (p.family === 'metal_add') return [
    make('standard', '일반관세 + 232 25%p', p.mfn + 25, [POLICY_SOURCES.metals, POLICY_SOURCES.metalAnnex], scope + '알루미늄 중량 15% 이상 · 지정 사양. 러시아산 금속 등 특별 조치 없음.'),
    ...(country === 'KOR' ? [make('fta', 'KORUS 특혜 0% + 232 25%p', 25, [POLICY_SOURCES.metals], scope + 'KORUS 원산지·특혜 신청 요건 충족.')] : []),
    make('us_metal', '일반관세 + 미국산 금속 232 10%p', p.mfn + 10, [POLICY_SOURCES.metals, POLICY_SOURCES.metalUpdate], scope + '해당 알루미늄의 85% 이상이 미국에서 제련·주조된 경우.'),
    ...(country === 'KOR' ? [make('fta_us_metal', 'KORUS 0% + 미국산 금속 232 10%p', 10, [POLICY_SOURCES.metals, POLICY_SOURCES.metalUpdate], scope + 'KORUS 특혜와 미국산 금속 85% 요건을 함께 충족.')] : []),
  ];
  if (p.family === 'memory') return [make('standard', '일반관세 0% + 강제노동 301 품목 예외', 0, [POLICY_SOURCES.forcedLabor, POLICY_SOURCES.forcedLaborAnnex], scope + '메모리 HTS 8542.32.00의 Annex (b) 예외. 기존 중국 301은 이 예외와 다릅니다.')];
  if (p.family === 'auto') return ['KOR', 'JPN'].includes(country) ? [make('standard', '일반관세 + 자동차 232 · 합산 15% 하한', Math.max(p.mfn, 15), [country === 'KOR' ? POLICY_SOURCES.koreaAuto : POLICY_SOURCES.japanAuto, POLICY_SOURCES.forcedLabor], scope + '완성 승용차. 강제노동 301과 중복 합산하지 않습니다.')] : [];
  const floor = EU.has(country) || country === 'TWN' ? 10 : ['KOR', 'JPN', 'CHE'].includes(country) ? 12.5 : null;
  const additional = ten.has(country) ? 10 : 12.5;
  const total = floor === null ? p.mfn + additional : Math.max(p.mfn, floor);
  return [make('standard', floor === null ? `일반관세 + 강제노동 301 ${additional}%p` : `일반관세 + 강제노동 301 · 합산 ${floor}% 하한`, total,
    [POLICY_SOURCES.forcedLabor, POLICY_SOURCES.forcedLaborAnnex], scope + '232·Annex 제품 예외·TRQ 등 미적용을 전제로 한 일반 경로. 특혜세율 경로는 자동 확정하지 않습니다.')];
}

export function newRow(product, country, expenditure = '') {
  const candidates = policyOptions(product, country);
  return { country, expenditure, supply_elasticity: country === 'USA' ? 1.5 : 3,
    baseline_policy: candidates[0]?.id || 'unresolved', scenario_policy: 'current',
    manual_before: '', manual_after: '', extra_duty: 0, tariff_note: '' };
}
function numeric(value, label) {
  if (value == null || !['string', 'number'].includes(typeof value) || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 300) throw new Error(`${label}: 0~300%를 입력하세요.`);
  return Number(value);
}
export function tariffPair(product, row) {
  const choices = policyOptions(product, row.country), base = choices.find(c => c.id === row.baseline_policy);
  const extra = row.country === 'USA' ? 0 : numeric(row.extra_duty, `${row.country} 별도 추가세`);
  const before = row.baseline_policy === 'manual' ? numeric(row.manual_before, `${row.country} 확인한 현행 관세`) : base?.rate;
  if (before === undefined) throw new Error(`${row.country}: 현행 관세 조합 또는 직접 확인한 세율을 선택하세요.`);
  if (row.baseline_policy === 'manual' && !row.tariff_note?.trim()) throw new Error(`${row.country}: 현행 관세의 출처·확인 내용을 입력하세요.`);
  const alternative = choices.find(c => c.id === row.scenario_policy);
  const after = row.scenario_policy === 'current' ? before : row.scenario_policy === 'manual' ? numeric(row.manual_after, `${row.country} 직접 입력 가정 관세`) : alternative?.rate;
  if (after === undefined) throw new Error(`${row.country}: 비교할 관세 조합을 선택하세요.`);
  // Manual values are already TOTAL rates. Adding extra_duty again would double count.
  const b = before + (row.baseline_policy === 'manual' ? 0 : extra);
  const a = after + (row.scenario_policy === 'manual' || (row.scenario_policy === 'current' && row.baseline_policy === 'manual') ? 0 : extra);
  if (b > 300 || a > 300) throw new Error('합산 관세는 300%를 넘을 수 없습니다.');
  return { tariff_before: b, tariff_after: a, provenance: { baseline_policy: row.baseline_policy, scenario_policy: row.scenario_policy,
    extra_duty: extra, note: row.tariff_note, status: row.baseline_policy === 'manual' ? 'user_verified_input' : 'conditional_policy_snapshot',
    conditions: [base?.condition, alternative?.condition].filter(Boolean), sources: [...(base?.sources || []), ...(alternative?.sources || [])] } };
}

export function initialDraft(product = 'transformer') {
  const p = PRODUCTS[product];
  return { product, period: '가상 연간 구매액 · 실제 통계로 보정 전', sigma: p.elasticity?.sigma ?? 4, eta: p.elasticity?.eta ?? -1,
    elasticity_basis: p.elasticity ? 'literature' : 'manual', focus: 'KOR', policy_confirmed: false,
    source_note: '구매액·공급탄력성은 학습용 가정. 별도 추가세 0%는 미적용 가정이며 확인이 필요합니다.',
    rows: [newRow(product, 'USA', 50), newRow(product, 'KOR', 25), newRow(product, 'JPN', 25)] };
}
export function modelInput(draft) {
  if (!draft.policy_confirmed) throw new Error('선택한 관세 조합의 적용 조건과 별도 추가세를 확인해 주세요.');
  const p = PRODUCTS[draft.product], e = draft.elasticity_basis === 'literature' ? p.elasticity : null;
  return { ...draft, rows: draft.rows.map(row => ({ ...row, ...tariffPair(draft.product, row) })),
    calibration: { policy_as_of: POLICY_AS_OF, hts: p.hts, product_scope: p.scope, purchase_basis: 'user_assumption',
      policy_confirmation: 'user_confirmed_conditions', supplier_statistics_year: 2025,
      supplier_source: { url: SUPPLIER_SNAPSHOT.url, fetched_at: SUPPLIER_SNAPSHOT.fetched_at, hts6: p.hts6 || null, flow: SUPPLIER_SNAPSHOT.flow, measure: SUPPLIER_SNAPSHOT.measure },
      elasticity: e ? { ...e, applied_sigma: Number(draft.sigma), applied_eta: Number(draft.eta), eta_basis: e.eta === undefined ? 'user_assumption' : 'literature_range_midpoint' } : { kind: 'user_assumption', applied_sigma: Number(draft.sigma), applied_eta: Number(draft.eta) } },
    ...(e?.range ? { sensitivity_sigmas: [e.range[0], Number(draft.sigma), e.range[1]] } : {}) };
}
