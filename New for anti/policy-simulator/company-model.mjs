import { simulate as simulateCountry } from './country-model.mjs';

export const COMPANY_MODEL_VERSION = 'company-stress-1';
export const COMPANY_SOURCES = [
  { title: '기업 가격·손익 산식 및 가정 · PR #528', url: 'https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/528' },
  { title: '국가 반응 참고: USITC CES', url: 'https://www.usitc.gov/ces_tariff_model' },
];

function number(value, label, low, high) {
  if (!['string', 'number'].includes(typeof value) || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < low || Number(value) > high) throw new Error(`${label}: ${low}~${high} 범위의 숫자를 입력하세요.`);
  return Number(value);
}
const optional = (v, label, low, high) => v === '' || v == null ? null : number(v, label, low, high);
export function validateCompany(input) {
  if (!input?.policy_confirmed) throw new Error('제품·원산지와 양쪽 관세 적용 조건을 확인해 주세요.');
  if (!/^[A-Z]{3}$/.test(input.origin) || input.origin === 'ROW') throw new Error('제품의 실제 원산지를 선택하세요.');
  const manual = input.response_mode !== 'country';
  const config = {
    company: String(input.company || '사용자 기업').slice(0, 100), product: String(input.product || 'custom').slice(0, 80), origin: input.origin,
    period: String(input.period || '사용자 분석 기간').slice(0, 100), source_note: String(input.source_note || '').slice(0, 1500),
    ...(input.transaction_evidence ? {transaction_evidence:structuredClone(input.transaction_evidence)} : {}),
    basis: 'user_scenario', policy_confirmed: true, response_mode: input.response_mode || 'manual',
    price: number(input.price, '기준 통관 단가', 0.000001, 1e12), quantity: number(input.quantity, '기준 판매량', 0.000001, 1e12),
    cost: number(input.cost, '단위 변동원가', 0, 1e12), fixed_cost: number(input.fixed_cost, '기간 고정비', 0, 1e15),
    cost_change_pct: number(input.cost_change_pct, '변동원가 변화율', -100, 1000),
    tariff_before: number(input.tariff_before, '현행 합산 관세', 0, 300), tariff_after: number(input.tariff_after, '가정 합산 관세', 0, 300),
    absorption_pct: manual ? number(input.absorption_pct, '수출자 흡수율', 0, 100) : 0,
    price_elasticity: manual ? number(input.price_elasticity, '기업 가격반응 탄력성', 0, 20) : 0, locked_share_pct: manual ? number(input.locked_share_pct, '계약 고정 물량 비중', 0, 100) : 0,
    competitor_change_pct: manual ? number(input.competitor_change_pct, '경쟁 제품 가격 변화', -90, 300) : 0, market_change_pct: manual ? number(input.market_change_pct, '시장 전체 수요 변화', -100, 300) : 0,
    capacity: optional(input.capacity, '최대 공급 가능 물량', 0.000001, 1e12),
    competitor_price: manual ? optional(input.competitor_price, '경쟁 제품 기준 가격', 0.000001, 1e12) : null,
    ...(input.tariff_provenance ? { tariff_provenance: structuredClone(input.tariff_provenance) } : {}),
    ...(input.calibration ? { calibration: structuredClone(input.calibration) } : {}),
  };
  if (!['manual', 'country'].includes(config.response_mode)) throw new Error('가격·물량 반응 방식을 선택하세요.');
  if (config.origin === 'USA' && (config.tariff_before !== 0 || config.tariff_after !== 0)) throw new Error('미국산 국내 판매에는 수입관세를 적용할 수 없습니다.');
  if (config.capacity != null && config.capacity < config.quantity) throw new Error('최대 공급 가능 물량은 기준 판매량 이상이어야 합니다.');
  if (config.response_mode === 'country') {
    if (!input.country_inputs || input.country_inputs.product !== config.product) throw new Error('같은 품목으로 계산한 국가 결과를 먼저 연결하세요.');
    const market = simulateCountry(input.country_inputs, false), row = market.rows.find(r => r.country === config.origin);
    const sourceRow = market.inputs.rows.find(r => r.country === config.origin);
    if (!row || Math.abs(sourceRow.tariff_before - config.tariff_before) > 1e-9 || Math.abs(sourceRow.tariff_after - config.tariff_after) > 1e-9) throw new Error('국가 결과의 원산지·관세가 기업 입력과 다릅니다. 국가에서 다시 계산해 연결하세요.');
    config.country_proxy = { inputs: market.inputs, model_version: market.model_version, row: structuredClone(row), market_price_change_pct: market.market_price_change_pct, max_log_residual: market.checks.max_log_residual };
  }
  return config;
}

function solve(c, absorption = c.absorption_pct) {
  const t0 = c.tariff_before / 100, t1 = c.tariff_after / 100;
  const buyer0 = c.price * (1 + t0);
  // Split the tariff shock measured at the original customs value. The new duty
  // is assessed on the reduced customs price; never subtract the full duty twice.
  const price1 = c.response_mode === 'country' ? c.price * (1 + c.country_proxy.row.producer_price_change_pct / 100)
    : c.price * (1 + t0 + (1 - absorption / 100) * (t1 - t0)) / (1 + t1);
  const buyer1 = price1 * (1 + t1), cost1 = c.cost * (1 + c.cost_change_pct / 100);
  const relative = (buyer1 / buyer0) / (1 + c.competitor_change_pct / 100);
  const lock = c.locked_share_pct / 100;
  const demanded = c.response_mode === 'country' ? c.quantity * (1 + c.country_proxy.row.volume_change_pct / 100)
    : c.quantity * (lock + (1 - lock) * relative ** -c.price_elasticity) * (1 + c.market_change_pct / 100);
  const quantity1 = Math.min(Math.max(0, demanded), c.capacity ?? Infinity);
  const revenue0 = c.price * c.quantity, revenue1 = price1 * quantity1;
  const contribution0 = (c.price - c.cost) * c.quantity, contribution1 = (price1 - cost1) * quantity1;
  const profit0 = contribution0 - c.fixed_cost, profit1 = contribution1 - c.fixed_cost;
  const unitContribution = price1 - cost1;
  const breakEven = unitContribution > 0 ? c.fixed_cost / unitContribution : null;
  const competitorAfter = c.competitor_price == null ? null : c.competitor_price * (1 + c.competitor_change_pct / 100);
  const out = {
    price_before: c.price, price_after: price1, buyer_price_before: buyer0, buyer_price_after: buyer1,
    quantity_before: c.quantity, quantity_after: quantity1, quantity_change_pct: (quantity1 / c.quantity - 1) * 100,
    demanded_quantity: demanded, capacity_binding: quantity1 < demanded - 1e-8,
    revenue_before: revenue0, revenue_after: revenue1, revenue_change_pct: (revenue1 / revenue0 - 1) * 100,
    unit_cost_before: c.cost, unit_cost_after: cost1, contribution_before: contribution0, contribution_after: contribution1,
    profit_before: profit0, profit_after: profit1, profit_change: profit1 - profit0,
    profit_change_pct: profit0 > 0 ? (profit1 / profit0 - 1) * 100 : null,
    margin_before_pct: profit0 / revenue0 * 100, margin_after_pct: revenue1 > 0 ? profit1 / revenue1 * 100 : null,
    break_even_quantity: breakEven, break_even_status: unitContribution <= 0 ? 'nonpositive_contribution' : c.capacity != null && breakEven > c.capacity ? 'above_capacity' : 'calculable',
    unit_cost_ceiling: quantity1 > 0 ? price1 - c.fixed_cost / quantity1 : null,
    duties_before: c.price * t0 * c.quantity, duties_after: price1 * t1 * quantity1,
    competitor_price_after: competitorAfter,
    price_gap_pct: competitorAfter == null ? null : (buyer1 / competitorAfter - 1) * 100,
  };
  if (Object.values(out).some(v => typeof v === 'number' && !Number.isFinite(v))) throw new Error('계산 범위를 벗어났습니다. 가격·물량 가정을 조정하세요.');
  return out;
}

export function simulateCompany(input) {
  const c = validateCompany(input), out = solve(c);
  const sensitivity = c.response_mode === 'manual' ? [...new Set([0, 25, 50, 75, 100, c.absorption_pct])].sort((a, b) => a - b).map(absorption => ({ absorption_pct: absorption, ...solve(c, absorption) })) : [];
  const { country_proxy, ...inputs } = c;
  const response_scenarios = sensitivity.filter(s => [0,50,100].includes(s.absorption_pct)).map(s=>({...s,label:s.absorption_pct===0?'흡수 없음':s.absorption_pct===50?'일부 흡수 가정':'전액 흡수 가정'}));
  return { model_version: COMPANY_MODEL_VERSION, capacity_status: c.capacity == null ? 'unbounded_assumption' : 'user_supplied_cap',
    input_basis: { transactions:'user_input_not_independently_verified', response: c.response_mode==='country'?'country_average_proxy':'user_assumption' }, response_scenarios, unit: 'USD; quantity in user-defined homogeneous product units', inputs,
    ...(country_proxy ? { country_proxy } : {}), ...out, sensitivity,
    checks: { profit_identity_error: out.profit_after - ((out.price_after - out.unit_cost_after) * out.quantity_after - c.fixed_cost),
      buyer_price_identity_error: out.buyer_price_after - out.price_after * (1 + c.tariff_after / 100) },
    limitations: ['단일 기업·제품·원산지·기간의 사용자 시나리오이며 전사 실적 예측이 아닙니다.',
      '기업 가격반응·계약 비중·경쟁 가격·시장 수요·원가는 사용자 가정입니다.',
      '국가 연결은 해당 원산지의 평균 가격·물량 반응을 적용한 대용 시나리오입니다. 기업 점유율의 실측 예측이 아닙니다.',
      '수입자가 납부하는 관세를 수출기업 원가에서 다시 차감하지 않습니다. AD 예치·사후 확정액·환율·세금·금융비용·다른 시장 판매는 계산하지 않습니다.'] };
}
