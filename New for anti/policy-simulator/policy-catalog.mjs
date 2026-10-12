import { SUPPLIER_SNAPSHOT } from './suppliers-2025.mjs';
import { ELASTICITIES, elasticityCalibration } from './elasticities.mjs';
import { productVerification } from './product-verification.mjs';
export { elasticityCalibration };

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
export const PRODUCTS = {
  transformer: { label: '전력용 변압기', hts: '8504.23.00', hts6: '850423', mfn: 1.6, family: 'metal_floor',
    elasticity: ELASTICITIES.transformer,
    scope: '액체절연 · 10MVA 초과. 철강 중량 15% 이상인 Annex III 제품을 비교합니다. 60MVA 이상 한국산은 A-580-867 등 AD 적용 여부·기업 세율을 별도 확인하세요.' },
  cable: { label: '전력 케이블', hts: '8544.60.20.00', hts6: '854460', mfn: 3.7, family: 'metal_add',
    scope: '1,000V 초과 · 커넥터 장착 · 알루미늄 중량 15% 이상인 Annex I-B 대표 사양. 구리 케이블·커넥터 없는 제품에는 이 조합을 쓰지 마세요.' },
  switchgear: { label: '차단기·배전기기', hts: '8535.21.00.00', hts6: '853521', mfn: 2.7, family: 'ordinary',
    elasticity: ELASTICITIES.switchgear,
    scope: '1,000V 초과~72.5kV 미만 자동 차단기 대표 사양. 배전반·다른 전압·부품은 별도 HTS입니다.' },
  semiconductor: { label: '반도체 · 메모리', hts: '8542.32.00', hts6: '854232', mfn: 0, family: 'memory',
    scope: '메모리 집적회로만 포함. 301 강제노동 관세 Annex (b) 예외. 고성능 연산 칩·서버의 232 적용을 메모리에 일괄 적용하지 않습니다.',
    elasticity: ELASTICITIES.semiconductor },
  vehicle: { label: '자동차 · 가솔린 승용', hts: '8703.23.01', hts6: '870323', mfn: 2.5, family: 'auto',
    elasticity: ELASTICITIES.vehicle,
    scope: '배기량 1.5~3L 승용차 대표 사양. 한국·일본의 232 합산 15% 조합만 제공하며 다른 원산지는 직접 확인이 필요합니다.' },
  'vehicle-hev': { label: '자동차 · 하이브리드 HEV', hts: '8703.40.00', hts6: '870340', mfn: 2.5, family: 'auto', classification_checked_on: '2026-10-12',
    elasticity: ELASTICITIES['vehicle-hev'], scope: '가솔린 엔진·전기 모터 겸용, 외부 충전 불가 승용차. 디젤·PHEV·미국 현지 생산과 구분합니다. 한국·일본 232 조건부 조합만 제공하며 실제 차종의 HTS·원산지를 확인하세요.' },
  'vehicle-phev': { label: '자동차 · 플러그인 하이브리드 PHEV', hts: '8703.60.00', hts6: '870360', mfn: 2.5, family: 'auto', classification_checked_on: '2026-10-12',
    elasticity: ELASTICITIES['vehicle-phev'], scope: '가솔린 엔진·전기 모터 겸용, 외부 충전 가능 승용차. 일반 HEV·디젤 하이브리드와 구분합니다. 한국·일본 232 조건부 조합만 제공하며 실제 차종의 HTS·원산지를 확인하세요.' },
  'vehicle-ev': { label: '자동차 · 전기 승용차 BEV', hts: '8703.80.00', hts6: '870380', mfn: 2.5, family: 'auto', classification_checked_on: '2026-10-12',
    elasticity: ELASTICITIES['vehicle-ev'], scope: '전기 모터만으로 구동하는 완성 승용차. 트럭·버스·배터리·구동 부품과 구분합니다. 한국·일본 232 조건부 조합만 제공하며 중국 301·USMCA 원산지는 별도 확인합니다.' },
  'auto-brake': { label: '자동차 부품 · 제동 시스템', hts: '8708.30.50', hts6: '870830', mfn: 2.5, family: 'auto_parts', classification_checked_on: '2026-10-12', scope: '대표 사양: 농업용 트랙터 이외 차량의 브레이크·서보브레이크 및 부분품. 실제 전자제어 단품·구성에 따라 분류가 다를 수 있습니다. 한국·일본 승용차·경트럭용 지정 부품의 조건부 경로이며 회사 제품 전체에 적용하지 않습니다.' },
  'auto-steering': { label: '자동차 부품 · 조향 시스템', hts: '8708.94.50.00', hts6: '870894', mfn: 2.5, family: 'auto_parts', classification_checked_on: '2026-10-12', scope: '대표 사양: 농업용 트랙터 이외 차량의 조향 휠·칼럼·박스 완성품. 주철·기타 부분품과 전자제어 단품은 별도 분류. 한국·일본 승용차·경트럭용 지정 부품의 적용 조건을 확인하세요.' },
  'auto-suspension': { label: '자동차 부품 · 현가 시스템', hts: '8708.80.16', hts6: '870880', mfn: 2.5, family: 'auto_parts', classification_checked_on: '2026-10-12', scope: '대표 사양: 농업용 트랙터 이외 차량의 현가 시스템 중 McPherson strut 이외. strut·주철/기타 부분품은 별도 분류. 한국·일본 승용차·경트럭용 지정 부품의 적용 조건과 유압실린더 AD 조사 범위를 별도 확인하세요.' },
  'auto-electric-drive': { label: '자동차 부품 · 전동화 구동·전력변환', hts: '', scope: '모터·인버터·전력변환 장치는 각각 분류가 다를 수 있습니다. 실제 형태·HTS·원산지·232/다른 추가세를 확인하세요. 전기차 완성차 관세를 대신 적용하지 않습니다.' },
  tire: { label: '타이어 · 승용차용', hts: '4011.10.10', hts6: '401110', mfn: 4, family: 'ordinary',
    scope: '승용차용 신품 래디얼 타이어 대표 사양. AD/CVD는 기업·사건별이므로 추가세 입력에서 확인하세요.',
    elasticity: ELASTICITIES.tire },
  fiber: { label: '산업용 섬유 · 타이어코드', hts: '5902.20.00.00', hts6: '590220', mfn: 5.8, family: 'ordinary',
    elasticity: ELASTICITIES.fiber,
    scope: '폴리에스터 타이어코드 직물 대표 사양. 나일론·아라미드·탄소섬유는 별도 품목입니다. 일부 국가의 섬유 쿼터는 직접 확인합니다.' },
  custom: { label: '직접 정의한 품목', hts: '', scope: '품목·원산지별로 검토한 현행 합산 종가세율을 직접 입력하세요.' },
  'power-cable': { label: '초고압 전력 케이블', hts: '', scope: '도체·전압·절연·커넥터·원산지를 확인하세요. 대표 알루미늄 케이블의 HTS·세율을 자동 적용하지 않습니다.' },
  'submarine-cable': { label: '해저 전력 케이블', hts: '', scope: '도체·전압·절연·구조에 따른 실제 분류와 합산 관세를 확인하세요.' },
  'industrial-cable': { label: '산업용 전선', hts: '', scope: '전압·용도·도체·커넥터에 따른 실제 분류와 관세를 확인하세요.' },
  'hot-rolled': { label: '특정 열연 평판강', hts: '', scope: '성분·두께·폭·가공·원산지와 AD/CVD·232 적용을 개별 확인하세요.' },
  'welded-pipe': { label: '대구경 용접강관', hts: '', scope: '직경·소재·용도·제외 조건을 확인하세요. OCTG와 동일하지 않습니다.' },
  octg: { label: '유정용 강관 · OCTG', hts: '', scope: 'OCTG 사건·제품 범위를 별도로 확인하세요. 대구경 용접강관의 세율을 대신 쓰지 않습니다.' },
  'truck-tire': { label: '트럭·버스 타이어', hts: '', scope: '차종·사양·원산지·사건 범위를 확인하세요. 승용차·경트럭 타이어 공고를 자동 적용하지 않습니다.' },
  'carbon-fiber': { label: '탄소섬유', hts: '', scope: '섬유·직물·프리프레그 등 실제 형태를 확인하세요. 폴리에스터 타이어코드 HTS·탄력성·관세를 대신 쓰지 않습니다.' },
  aramid: { label: '아라미드', hts: '', scope: '원사·직물 등 형태와 원산지에 맞는 관세·제품 범위를 확인하세요.' },
  sap: { label: '고흡수성 수지 · SAP', hts: '', scope: '성분·형태·명령의 서술 범위를 확인하세요. 다른 석유화학 제품 전체에 확대하지 않습니다.' },
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
  if (p.family === 'auto_parts') return ['KOR','JPN'].includes(country) ? [make('standard', '지정 자동차 부품 232 · 조건부 합산 15%', Math.max(p.mfn, 15), [country === 'KOR' ? POLICY_SOURCES.koreaAuto : POLICY_SOURCES.japanAuto,
    { title: '현행 HTS 자동차 부품 232 · 2026-10-12 확인', url: `https://hts.usitc.gov/search?query=${country === 'KOR' ? '9903.94.63' : '9903.94.43'}` },
    { title: '현행 Chapter 99 · Note 33(g)/(l)/(t)', url: 'https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099' }], scope + 'Note 33(g)의 승용차·경트럭용 지정 부품에 한정. 일반관세를 다시 더하지 않음. 중대형 트럭·다른 부품·수입조정 상계·AD/CVD·별도 추가세는 별도 검토.')] : [];
  if (p.family === 'auto') return ['KOR', 'JPN'].includes(country) ? [make('standard', '일반관세 + 자동차 232 · 합산 15% 하한', Math.max(p.mfn, 15), [country === 'KOR' ? POLICY_SOURCES.koreaAuto : POLICY_SOURCES.japanAuto, { title: '현행 HTS 자동차 232 · 2026-10-12 확인', url: `https://hts.usitc.gov/search?query=${country === 'KOR' ? '9903.94.61' : '9903.94.41'}` }, POLICY_SOURCES.forcedLabor], scope + 'U.S. note 33(b)의 완성 승용차에 한정. 강제노동 301과 중복 합산하지 않습니다.')] : [];
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
function tariffError(message, field) { return Object.assign(new Error(message), { field }); }
function numeric(value, label, field) {
  if (value == null || !['string', 'number'].includes(typeof value) || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 300) throw tariffError(`${label}: 0~300%를 입력하세요.`, field);
  return Number(value);
}
export function tariffPair(product, row) {
  const choices = policyOptions(product, row.country), base = choices.find(c => c.id === row.baseline_policy);
  const extra = row.country === 'USA' ? 0 : numeric(row.extra_duty, `${row.country} 별도 추가세`, 'extra_duty');
  const before = row.baseline_policy === 'manual' ? numeric(row.manual_before, `${row.country} 확인한 현행 관세`, 'manual_before') : base?.rate;
  if (before === undefined) throw tariffError(`${row.country}: 현행 관세 조합 또는 직접 확인한 세율을 선택하세요.`, 'baseline_policy');
  if (row.baseline_policy === 'manual' && !row.tariff_note?.trim()) throw tariffError(`${row.country}: 현행 관세의 출처·확인 내용을 입력하세요.`, 'tariff_note');
  const alternative = choices.find(c => c.id === row.scenario_policy);
  const after = row.scenario_policy === 'current' ? before : row.scenario_policy === 'manual' ? numeric(row.manual_after, `${row.country} 직접 입력 가정 관세`, 'manual_after') : alternative?.rate;
  if (after === undefined) throw tariffError(`${row.country}: 비교할 관세 조합을 선택하세요.`, 'scenario_policy');
  // Manual values are already TOTAL rates. Adding extra_duty again would double count.
  const b = before + (row.baseline_policy === 'manual' ? 0 : extra);
  const a = after + (row.scenario_policy === 'manual' || (row.scenario_policy === 'current' && row.baseline_policy === 'manual') ? 0 : extra);
  if (b > 300 || a > 300) throw tariffError('합산 관세는 300%를 넘을 수 없습니다. 별도 추가세를 조정하세요.', 'extra_duty');
  return { tariff_before: b, tariff_after: a, provenance: { baseline_policy: row.baseline_policy, scenario_policy: row.scenario_policy,
    extra_duty: extra, note: row.tariff_note, status: row.baseline_policy === 'manual' ? 'user_verified_input' : 'conditional_policy_snapshot',
    conditions: [base?.condition, alternative?.condition].filter(Boolean), sources: [...(base?.sources || []), ...(alternative?.sources || [])] } };
}

export function initialDraft(product = 'transformer') {
  const p = PRODUCTS[product];
  return { product, period: '가상 연간 구매액 · 실제 통계로 보정 전', sigma: p.elasticity?.sigma ?? 4, eta: p.elasticity?.eta ?? -1,
    elasticity_basis: p.elasticity ? 'literature' : 'manual', elasticity_overrides: {}, focus: 'KOR', policy_confirmed: false,
    source_note: '구매액·공급탄력성은 학습용 가정. 별도 추가세 0%는 미적용 가정이며 확인이 필요합니다.',
    rows: [newRow(product, 'USA', 50), newRow(product, 'KOR', 25), newRow(product, 'JPN', 25)] };
}
export function modelInput(draft) {
  if (!draft.policy_confirmed) throw new Error('선택한 관세 조합의 적용 조건과 별도 추가세를 확인해 주세요.');
  const p = PRODUCTS[draft.product], elasticity = elasticityCalibration(draft), suppliers = SUPPLIER_SNAPSHOT.products[draft.product];
  return { ...draft, rows: draft.rows.map(row => ({ ...row, ...tariffPair(draft.product, row) })),
    calibration: { policy_as_of: POLICY_AS_OF, classification_checked_on: p.classification_checked_on || null, hts: p.hts, product_scope: p.scope, purchase_basis: 'user_assumption',
      policy_confirmation: 'user_confirmed_conditions', supplier_statistics_year: suppliers ? SUPPLIER_SNAPSHOT.year : null,
      supplier_source: suppliers ? { url: SUPPLIER_SNAPSHOT.url, fetched_at: SUPPLIER_SNAPSHOT.fetched_at, hts6: suppliers.hts6, flow: SUPPLIER_SNAPSHOT.flow, measure: SUPPLIER_SNAPSHOT.measure } : null,
      product_verification: draft.rows.map(row => productVerification(draft.product, row.country)).filter(Boolean), elasticity },
    ...(elasticity.sigma.range ? { sensitivity_sigmas: [elasticity.sigma.range[0], Number(draft.sigma), elasticity.sigma.range[1]] } : {}) };
}
