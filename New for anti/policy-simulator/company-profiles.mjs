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
    'https://worldwide.kia.com/en/company/investor-relations/financial/summary-statements', '대표 자동차 입력은 가솔린 1.5~3L 범위입니다. EV·다른 차종이나 미국 현지 생산에 그대로 적용할 수 없습니다. 연결 매출을 대미 수출 매출로 사용하지 않습니다.'),
  hyosung: profile('hyosung', '효성중공업', 'transformer', '전력용 변압기·차단기·배전반 및 건설', 5968512, 746968, '효성중공업 연결 손익계산서',
    'https://www.hyosungheavyindustries.com/kr/company/ir/financial/income-statement', '전사 실적에는 다른 전력기기·건설도 포함됩니다. 한국산 60MVA 이상 대형 변압기는 A-580-867 공식 공고에서 별도로 확인할 수 있습니다.', { case_id: 'A-580-867', company_id: 'hyosung' }),
  'hs-materials': profile('hs-materials', 'HS효성첨단소재', 'fiber', '타이어보강재·탄소재료·아라미드·산업용 원사', 3283045, 157433, 'HS효성첨단소재 연결 손익계산서',
    'https://www.hshyosungadvancedmaterials.com/kr/ir/balance-sheet?tabId=pills-balanceSheet2-tab', '대표 품목은 폴리에스터 타이어코드 직물만 포함합니다. 탄소섬유·아라미드·강선·다른 원산지에는 해당 HTS를 자동 확대하지 않습니다. 효성중공업과 별도 법인입니다.'),
  hankook: profile('hankook', '한국타이어앤테크놀로지', 'tire', '승용차·경트럭 등 타이어', 10318600, 1684300, '타이어 사업부 · 전 세계 실적 · 회사 발표',
    'https://www.hankooktire.com/us/en/company/media-center/media-detail.632666.html?contentType=&tabCode=', '한온시스템을 포함한 연결 전사 매출 21,202,200백만원과 구분한 타이어 부문입니다. 북미 매출은 한국산 수입액과 다릅니다. 한국산 승용차·경트럭 타이어는 A-580-908 공고를 확인하세요.', { case_id: 'A-580-908', company_id: 'hankook' }),
};
export function companyCalibration(id) {
  const p = COMPANY_PROFILES[id];
  return { company_data_basis: 'user_product_inputs', firm_elasticity_basis: 'user_assumption', ...(p ? { public_company_context: structuredClone(p) } : {}) };
}
