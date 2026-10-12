// Product-specific starting points, not universal industry constants. Missing
// parameters remain explicit assumptions; sources never imply an HTS-level fit.
const source = (title, url) => ({ title, url });
const lpt = source('USITC Pub.5531 (2024), II-30~31', 'https://www.usitc.gov/sites/default/files/publications/701_731/pub5531.pdf#page=122');
const armington = page => source(`USITC 연구진 (2004), 표 1 · p.${page}`, `https://www.usitc.gov/publications/332/ec200401a.pdf#page=${page + 1}`);
const tire = source('USITC Pub.5212 (2021), II-30~31', 'https://www.usitc.gov/sites/default/files/publications/701_731/pub5212.pdf#page=124');
export const ELASTICITIES = {
  transformer: { sigma: 3.5, range: [2, 5], eta: -0.15, eta_range: [-0.25, -0.05], source: lpt, year: 2024,
    kind: 'literature_range_midpoint', scope: '미국 대형 전력용 변압기(60MVA 이상)',
    note: 'USITC 제시 범위 σ=2~5, η=-0.25~-0.05의 중간값입니다. 대표 HTS의 10~60MVA 제품까지 검증된 값은 아니며, 미국산·수입산 간 대체를 모든 공급국에 공통 적용하는 근사입니다.' },
  switchgear: { sigma: 3, source: armington(13), year: 2004, kind: 'historical_sector_proxy', scope: 'BEA 530300 · Switchgear and switchboard apparatus',
    note: '2004년 연구진의 배전·개폐장치 산업 모형값 σ=3.0을 넓은 산업 대용값으로 사용합니다. 현재 1~72.5kV 차단기만의 실측값은 아닙니다. η 문헌값은 미확보입니다.' },
  semiconductor: { sigma: 3.32, source: source('USITC 연구진 (2023), 표 4 · 메모리', 'https://www.usitc.gov/sites/default/files/publications/332/working_papers/us_exposure_to_the_taiwanese_semiconductor_industry_11-21-2023_508.pdf#page=23'),
    year: 2023, kind: 'literature_proxy', scope: '메모리 반도체 · 2021년 자료',
    note: '메모리 부문 보정값입니다. 현재 기업·규격별 추정치는 아니며, η=-1은 별도의 사용자 가정입니다.' },
  vehicle: { sigma: 7.58, source: source('USITC Pub.5443 (2023), p.163 · σ=7.58', 'https://www.usitc.gov/publications/332/pub5443.pdf#page=165'),
    year: 2023, kind: 'literature_proxy', scope: '승용차·경트럭(light vehicles) · 2021년 무역자료',
    eta: -0.82, eta_range: [-1.27, -0.37], eta_kind: 'literature_review_midpoint', eta_year: 2021,
    eta_source: source('EPA-420-R-21-019 (2021), §5.1 · 신차 총수요', 'https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1013TYN.TXT'),
    eta_scope: '미국 신차시장 전체 · 여러 연구의 총수요 추정치 범위',
    note: 'σ는 경트럭을 포함한 추정치이며 가솔린 1.5~3L만의 값은 아닙니다. η는 EPA 문헌 검토 범위 -1.27~-0.37의 중간값을 이 도구가 선택했습니다. 단일 공식 권장값·메타분석 평균이 아니며 중고차시장 피드백은 재현하지 않습니다.' },
  tire: { sigma: 4.5, range: [3, 6], eta: -0.375, eta_range: [-0.5, -0.25], source: tire, year: 2021,
    kind: 'literature_range_midpoint', scope: '미국 승용차·경트럭용 타이어(PVLT)',
    note: 'USITC 제시 범위 σ=3~6, η=-0.50~-0.25의 중간값입니다. 승용차용 대표 사양에 쓰는 근사이며 미국산·수입산 간 대체를 모든 공급국에 공통 적용합니다.' },
  fiber: { sigma: 3.5, source: armington(15), year: 2004, kind: 'historical_sector_proxy', scope: 'BEA 170700 · Tire cord and fabrics',
    note: '2004년 연구진의 타이어코드·직물 산업 모형값입니다. 폴리에스터만의 현재 실측값은 아니며, η 문헌값은 미확보입니다.' },
};

// Broad light-vehicle proxies, explicitly not powertrain-specific estimates.
for (const [id, label] of [['vehicle-hev', 'HEV'], ['vehicle-phev', 'PHEV'], ['vehicle-ev', 'BEV']]) {
  ELASTICITIES[id] = { ...ELASTICITIES.vehicle, note: `${label} 전용 추정치는 미확보입니다. 승용차·경트럭 전체의 σ와 신차 총수요 η를 넓은 산업 대용값으로 사용합니다. ${ELASTICITIES.vehicle.note}` };
}

export function elasticityCalibration(draft) {
  const e = ELASTICITIES[draft.product];
  const parameter = key => {
    const value = Number(draft[key]);
    const applied = e?.[key] !== undefined && value === e[key] && draft.elasticity_basis !== 'manual' && !draft.elasticity_overrides?.[key];
    if (!applied) return { value, kind: 'user_assumption' };
    return { value, default_value: e[key], kind: key === 'eta' ? e.eta_kind || e.kind : e.kind,
      source: key === 'eta' ? e.eta_source || e.source : e.source,
      year: key === 'eta' ? e.eta_year || e.year : e.year,
      scope: key === 'eta' ? e.eta_scope || e.scope : e.scope,
      ...(e[key === 'sigma' ? 'range' : 'eta_range'] ? { range: [...e[key === 'sigma' ? 'range' : 'eta_range']] } : {}) };
  };
  const sigma = parameter('sigma'), eta = parameter('eta');
  const kind = sigma.kind === eta.kind ? sigma.kind : 'mixed';
  return { kind, applied_sigma: sigma.value, applied_eta: eta.value, eta_basis: eta.kind, sigma, eta };
}
