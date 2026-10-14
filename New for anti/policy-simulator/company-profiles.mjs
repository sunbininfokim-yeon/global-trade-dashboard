import { AD_CATALOG } from './antidumping-catalog.mjs';
// Public financial context only. Never use consolidated sales as US product sales.
export const COMPANY_DATA_CHECKED_ON = '2026-10-11';
const missing = ['미국향 제품별 신고가격·물량', '동일 제품의 단위 변동원가·배분 고정비', '계약별 가격 전가·고객 전환 탄력성'];
const profile = (id, name, product, products, revenue, profit, scope, url, note, ad = null, checkedOn = COMPANY_DATA_CHECKED_ON) => ({ id, name, product, products,
  financial: { period: '2025-01-01 ~ 2025-12-31', unit: 'KRW million', revenue, operating_profit: profit, scope, source_url: url, checked_on: checkedOn, use: 'context_only' },
  note, ad, missing: [...missing], product_origin: null, product_price: null, product_quantity: null, product_variable_cost: null, product_fixed_cost: null });
export const COMPANY_PROFILES = {
  'ls-cable': profile('ls-cable', 'LS전선', 'custom', '초고압·해저·배전 케이블, 통신 제품', 7588200, 279800, 'LS그룹이 공개한 LS전선 회사 실적',
    'https://lsholdings.com/ko/ir/investment', 'LS일렉트릭과 별도 법인입니다. 전선 도체·전압·커넥터·원산지를 확인해야 하며 대표 알루미늄 케이블 HTS를 자동 적용하지 않습니다.'),
  'ls-electric': profile('ls-electric', 'LS일렉트릭', 'transformer', '전력용 변압기·배전반·차단기 및 전력·자동화 시스템', 4965799, 426407, 'LS ELECTRIC K-IFRS 연결 요약손익계산서',
    'https://www.ls-electric.com/ko/company/invest/result', 'LS전선과 별도 법인입니다. 연결 실적에는 변압기 외 전력·자동화 사업과 자회사도 포함됩니다. 한국산 60MVA 이상 대형 변압기는 A-580-867에서 LS Electric Co., Ltd.의 공표 참고율을 확인하세요. 다른 제품·미국 현지 생산에는 자동 적용하지 않습니다.', { case_id: 'A-580-867', company_id: 'ls' }, '2026-10-12'),
  taihan: profile('taihan', '대한전선', 'custom', '초고압·해저 케이블, 산업전선', 3636000, 128600, '대한전선 연결 실적 · 회사 보도자료의 연간 비교표',
    'https://www.taihan.com/news/pr/releaseDetail?idx=439', '공시·IR과 생산거점 자료를 확보할 수 있습니다. 공개 전사 실적에서 미국향 특정 케이블의 가격·원가를 분리하지 않았습니다.'),
  kia: profile('kia', '기아', 'vehicle', '내연기관·하이브리드·전기차', 114140919, 9078148, '기아 K-IFRS 연결 손익계산서',
    'https://worldwide.kia.com/en/company/investor-relations/financial/summary-statements', '가솔린·HEV·PHEV·전기 승용차를 별도 품목으로 선택하세요. 제품의 실제 생산지·원산지와 사양을 확인하며 미국 현지 생산에 한국산 수입관세를 적용하지 않습니다. 연결 매출을 대미 수출 매출로 사용하지 않습니다.'),
  hyosung: profile('hyosung', '효성중공업', 'transformer', '전력용 변압기·차단기·배전반 및 건설', 5968512, 746968, '효성중공업 연결 손익계산서',
    'https://www.hyosungheavyindustries.com/kr/company/ir/financial/income-statement', '전사 실적에는 다른 전력기기·건설도 포함됩니다. 한국산 60MVA 이상 대형 변압기는 A-580-867 공식 공고에서 별도로 확인할 수 있습니다.', { case_id: 'A-580-867', company_id: 'hyosung' }),
  'hs-materials': profile('hs-materials', 'HS효성첨단소재', 'fiber', '타이어보강재·탄소재료·아라미드·산업용 원사', 3283045, 157433, 'HS효성첨단소재 연결 손익계산서',
    'https://www.hshyosungadvancedmaterials.com/kr/ir/balance-sheet?tabId=pills-balanceSheet2-tab', '대표 품목은 폴리에스터 타이어코드 직물만 포함합니다. 탄소섬유·아라미드·강선·다른 원산지에는 해당 HTS를 자동 확대하지 않습니다. 효성중공업과 별도 법인입니다.'),
  hankook: profile('hankook', '한국타이어앤테크놀로지', 'tire', '승용차·경트럭 등 타이어', 10318600, 1684300, '타이어 사업부 · 전 세계 실적 · 회사 발표',
    'https://www.hankooktire.com/us/en/company/media-center/media-detail.632666.html?contentType=&tabCode=', '한온시스템을 포함한 연결 전사 매출 21,202,200백만원과 구분한 타이어 부문입니다. 북미 매출은 한국산 수입액과 다릅니다. 한국산 승용차·경트럭 타이어는 A-580-908 공고를 확인하세요.', { case_id: 'A-580-908', company_id: 'hankook' }),
};
// Manufacturer product evidence only; no invented financial or US shipment inputs.
const autoProfile = (id, name, officialName, product, products, url, title) => ({ id, name, official_name: officialName, product, products,
  financial: null, source: { url, title, checked_on: '2026-10-12' },
  note: '기업 공식 제품 자료를 연결했습니다. 실제 제품의 생산지·원산지·사양·미국향 거래·원가는 별도 확인이 필요합니다. 완성차 232와 기업·품목별 반덤핑은 서로 다른 조치이며, 이 프로필의 AD 적용 여부는 미확인입니다.',
  ad: null, missing: [...missing], product_origin: null, product_price: null, product_quantity: null, product_variable_cost: null, product_fixed_cost: null });
Object.assign(COMPANY_PROFILES, {
  'hyundai-motor': autoProfile('hyundai-motor', '현대자동차', 'Hyundai Motor Company', 'vehicle', '가솔린·하이브리드·플러그인 하이브리드·전기 승용차',
    'https://www.hyundai.com/eu/en/models/suv-cars.html', '현대자동차 공식 SUV·동력원 소개'),
  'hyundai-mobis': autoProfile('hyundai-mobis', '현대모비스', 'Hyundai Mobis Co., Ltd.', 'auto-brake', '제동·조향·전동화 구동·전력변환 시스템',
    'https://www.mobis.com/en/aboutus/aboutus.do', '현대모비스 공식 제품·사업 소개'),
  'hl-mando': autoProfile('hl-mando', 'HL만도', 'HL Mando Corporation', 'auto-brake', '제동·조향·현가 시스템',
    'https://www.hlmando.com/en/hl-mando/global-network.do', 'HL만도 공식 제동·조향·현가 생산거점 소개'),
});
export function companyCalibration(id, product = COMPANY_PROFILES[id]?.product) {
  const p = COMPANY_PROFILES[id];
  const industry = COMPANY_INDUSTRIES.find(i => i.product === product && i.profiles.includes(id));
  const productSource = industry?.sources?.[id] || industry?.source;
  return { company_data_basis: 'user_product_inputs', firm_elasticity_basis: 'user_assumption', ...(p ? { public_company_context: structuredClone(p) } : {}),
    ...(productSource ? { selected_product_source: { product, url: productSource, checked_on: '2026-10-12' } } : {}) };
}

// Discovery groups are not AD scope determinations. Only case_id groups have
// curated AD evidence; a firm's transformer rate never applies to switchgear.
export const INDUSTRY_FAMILIES = [
  { id: 'power', label: '전력기기' }, { id: 'cables', label: '전선·케이블' },
  { id: 'steel', label: '철강·강관' }, { id: 'tires', label: '타이어' },
  { id: 'materials', label: '첨단 산업소재' }, { id: 'chemicals', label: '화학 소재' },
  { id: 'auto', label: '자동차·부품' },
];
export const COMPANY_INDUSTRIES = [
  { id: 'transformer', family: 'power', label: '변압기', product: 'transformer', description: '한국산 대형 전력용 변압기', case_id: 'A-580-867', profiles: ['ls-electric', 'hyosung'] },
  { id: 'switchgear', family: 'power', label: '차단기·배전기기', product: 'switchgear', description: '차단기·배전반 등 전력기기', case_id: null, profiles: ['ls-electric', 'hyosung'] },
  { id: 'cable', family: 'cables', label: '전력 케이블', product: 'power-cable', description: '초고압 전력 케이블 · 사양별 분류 필요', case_id: null, profiles: ['ls-cable', 'taihan'] },
  { id: 'submarine-cable', family: 'cables', label: '해저 케이블', product: 'submarine-cable', description: '해저 전력 케이블 · 도체·절연 확인', case_id: null, profiles: ['ls-cable', 'taihan'] },
  { id: 'industrial-cable', family: 'cables', label: '산업용 전선', product: 'industrial-cable', description: '산업용 전선 · 전압·커넥터 확인', case_id: null, profiles: ['ls-cable', 'taihan'] },
  { id: 'hot-rolled', family: 'steel', label: '철강 · 열연강판', product: 'hot-rolled', description: '한국산 특정 열연 평판강 제품', case_id: 'A-580-883', profiles: [] },
  { id: 'welded-pipe', family: 'steel', label: '강관 · 대구경 용접강관', product: 'welded-pipe', description: '한국산 대구경 용접강관', case_id: 'A-580-897', profiles: [] },
  { id: 'octg', family: 'steel', label: '유정용 강관 · OCTG', product: 'octg', description: '대구경 용접강관과 별도 사건·범위', case_id: null, profiles: ['ad-seah'], source: 'https://www.seahsteel.co.kr/eng/application/oil-gas.asp' },
  { id: 'tire', family: 'tires', label: '타이어', product: 'tire', description: '한국산 승용차·경트럭 타이어', case_id: 'A-580-908', profiles: ['hankook'] },
  { id: 'truck-tire', family: 'tires', label: '트럭·버스 타이어', product: 'truck-tire', description: '승용차·경트럭 사건과 분리', case_id: null, profiles: ['hankook'], source: 'https://www.hankooktire.com/us/en/tirelist/vehicle/truck-and-bus.html' },
  { id: 'fiber', family: 'materials', label: '산업용 섬유', product: 'fiber', description: '대표 입력은 폴리에스터 타이어코드 직물', case_id: null, profiles: ['hs-materials'] },
  { id: 'carbon-fiber', family: 'materials', label: '탄소섬유', product: 'carbon-fiber', description: 'TANSOME · 타이어코드와 분리', case_id: null, profiles: ['hs-materials'], source: 'https://www.hshyosungadvancedmaterials.com/en/business/carbon-fiber' },
  { id: 'aramid', family: 'materials', label: '아라미드', product: 'aramid', description: 'ALKEX · 타이어코드와 분리', case_id: null, profiles: ['hs-materials'], source: 'https://www.hshyosungadvancedmaterials.com/kr/business/aramid-yarn' },
  { id: 'sap', family: 'chemicals', label: '고흡수성 수지 · SAP', product: 'sap', description: '한국산 특정 고흡수성 수지', case_id: 'A-580-914', profiles: [] },
  { id: 'vehicle', family: 'auto', label: '가솔린 승용차', product: 'vehicle', description: '배기량 1.5~3L · 다른 동력원과 분리', case_id: null, profiles: ['kia', 'hyundai-motor'] },
  { id: 'vehicle-hev', family: 'auto', label: '하이브리드 · HEV', product: 'vehicle-hev', description: '가솔린·전기 겸용 · 외부 충전 불가', case_id: null, profiles: ['kia', 'hyundai-motor'], sources: { kia: 'https://www.kia.com/us/en/ev', 'hyundai-motor': 'https://www.hyundai.com/eu/en/models/suv-cars.html' } },
  { id: 'vehicle-phev', family: 'auto', label: '플러그인 하이브리드 · PHEV', product: 'vehicle-phev', description: '가솔린·전기 겸용 · 외부 충전 가능', case_id: null, profiles: ['kia', 'hyundai-motor'], sources: { kia: 'https://www.kia.com/us/en/ev', 'hyundai-motor': 'https://www.hyundai.com/eu/en/models/hybrid-cars/plug-in-hybrid.html' } },
  { id: 'vehicle-ev', family: 'auto', label: '전기 승용차 · BEV', product: 'vehicle-ev', description: '전기 모터만으로 구동 · 부품과 분리', case_id: null, profiles: ['kia', 'hyundai-motor'], sources: { kia: 'https://www.kia.com/us/en/ev', 'hyundai-motor': 'https://www.hyundai.com/eu/en/models/suv-cars.html' } },
  { id: 'auto-brake', family: 'auto', label: '제동 시스템', product: 'auto-brake', description: '브레이크·전자제동 · 형태별 HTS 확인', case_id: null, profiles: ['hyundai-mobis', 'hl-mando'], sources: { 'hyundai-mobis': 'https://www.mobis.com/en/aboutus/aboutus.do', 'hl-mando': 'https://www.hlmando.com/en/hl-mando/global-network.do' } },
  { id: 'auto-steering', family: 'auto', label: '조향 시스템', product: 'auto-steering', description: '조향장치·전자조향 · 부품별 분류', case_id: null, profiles: ['hyundai-mobis', 'hl-mando'], sources: { 'hyundai-mobis': 'https://www.mobis.com/en/aboutus/aboutus.do', 'hl-mando': 'https://www.hlmando.com/en/hl-mando/global-network.do' } },
  { id: 'auto-suspension', family: 'auto', label: '현가 시스템', product: 'auto-suspension', description: '서스펜션 · 개별 제품·원산지 확인', case_id: null, profiles: ['hl-mando'], source: 'https://www.hlmando.com/en/hl-mando/global-network.do' },
  { id: 'auto-electric-drive', family: 'auto', label: '전동화 구동·전력변환', product: 'auto-electric-drive', description: '구동 모터·인버터 · 완성차와 별도 분류', case_id: null, profiles: ['hyundai-mobis'], source: 'https://www.mobis.com/en/aboutus/aboutus.do' },
];

// Every named entity in the curated notices remains selectable, irrespective of
// size/rank. A notice proves review participation, not current market share.
const existingProfiles = { 'A-580-867:ls': 'ls-electric', 'A-580-867:hyosung': 'hyosung', 'A-580-908:hankook': 'hankook' };
for (const c of AD_CATALOG.cases) {
  const industry = COMPANY_INDUSTRIES.find(x => x.case_id === c.case_id);
  for (const company of c.companies) {
    const id = existingProfiles[`${c.case_id}:${company.id}`] || `ad-${company.id}`;
    if (COMPANY_PROFILES[id]?.ad && COMPANY_PROFILES[id].ad.case_id !== c.case_id) throw new Error(`Company profile requires an explicit case/product mapping: ${id}`);
    if (!COMPANY_PROFILES[id]) {
      const document = AD_CATALOG.documents[c.segments.find(s => s.rates.some(r => r.company_id === company.id)).document_id];
      COMPANY_PROFILES[id] = { id, name: company.name, official_name: company.official_name, product: industry.product, products: c.product,
        financial: null, source: { url: document.url, title: document.title, checked_on: document.verified_on },
        note: '관보에 기재된 법인·재심 자료를 연결했습니다. 현재 생산능력·시장점유율·재무·미국향 거래 자료는 별도로 확인하지 않았습니다. 법인그룹은 이 공고의 취급 단위이며 계열사 전체를 뜻하지 않습니다.',
        ad: { case_id: c.case_id, company_id: company.id }, missing: [...missing],
        product_origin: null, product_price: null, product_quantity: null, product_variable_cost: null, product_fixed_cost: null };
    }
    COMPANY_PROFILES[id].official_name ||= company.official_name;
    if (!industry.profiles.includes(id)) industry.profiles.push(id);
  }
}
export function companyADLink(profileId, product) {
  const p = COMPANY_PROFILES[profileId];
  return p?.ad && p.product === product ? structuredClone(p.ad) : null;
}
