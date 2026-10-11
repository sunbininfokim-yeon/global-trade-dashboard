import { AD_CATALOG } from './antidumping-catalog.mjs';

export const AD_MODEL_VERSION = 'ad-deposit-1';
const SCALE = 1000000n;
// Decimal input and rational money arithmetic. Round once, half up, at USD cents.
function decimal(value, label, min = 0, max = 1e12) {
  if (!['string', 'number'].includes(typeof value) || !/^\d+(?:\.\d{1,6})?$/.test(String(value).trim())) throw new Error(`${label}: 소수점 6자리 이내의 0 이상 숫자를 입력하세요.`);
  const text = String(value).trim(), [whole, fraction = ''] = text.split('.');
  if (!Number.isFinite(Number(text)) || Number(text) < min || Number(text) > max) throw new Error(`${label}: ${min}~${max} 범위로 입력하세요.`);
  return BigInt(whole) * SCALE + BigInt(fraction.padEnd(6, '0'));
}
function money(numerator, denominator) {
  const negative = numerator < 0n, n = negative ? -numerator : numerator;
  const cents = (n * 100n * 2n + denominator) / (2n * denominator);
  return `${negative && cents ? '-' : ''}${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
}
function date(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw new Error('통관일을 유효한 날짜로 입력하세요.');
  return value;
}
export function lookupAD(input, catalog = AD_CATALOG) {
  const entry = date(input.entry_date), c = catalog.cases.find(x => x.case_id === input.case_id);
  if (!c) throw new Error('등록된 반덤핑 사건을 선택하세요.');
  const company = c.companies.find(x => x.id === input.company_id || x.official_name === input.company_id || x.aliases.includes(input.company_id));
  const base = { case_id: c.case_id, company: company ? structuredClone(company) : null, entry_date: entry, rate_pct: null, status: 'unresolved', checked_on: catalog.checked_on, coverage: catalog.coverage, coverage_note: catalog.coverage_note };
  if (!company) return { ...base, reason: '등록된 법인과 일치하지 않습니다. 다른 계열사·미등록 기업에 all-others 세율을 자동 적용하지 않습니다.' };
  if (entry > catalog.checked_on) return { ...base, reason: '자료 확인일 이후 통관입니다. 최신 공식 공고·예치 지침 확인 또는 출처가 있는 직접 입력이 필요합니다.' };
  const candidates = c.segments.filter(s => s.stage === 'final' && s.cash_deposit_effective && s.cash_deposit_effective <= entry && s.rates.some(r => r.company_id === company.id));
  const segment = candidates.sort((a, b) => b.cash_deposit_effective.localeCompare(a.cash_deposit_effective))[0];
  if (!segment) return { ...base, reason: '이 날짜·기업의 최종 공고가 수록되지 않았습니다. 미확인을 0%로 계산하지 않습니다.' };
  const rate = segment.rates.find(r => r.company_id === company.id);
  return { ...base, status: 'published_reference', rate_pct: Number(rate.margin_pct) < 0.5 ? '0' : rate.margin_pct, margin_pct: rate.margin_pct,
    effective: segment.cash_deposit_effective, por_start: segment.por_start, por_end: segment.por_end, examined: rate.examined,
    document: structuredClone(catalog.documents[segment.document_id]), reason: segment.reason };
}
export function simulateDeposit(input) {
  if (input.scope_confirmed !== true) throw new Error('제품 범위와 실제 원산지의 포함 조건을 확인해 주세요.');
  if (input.identity_confirmed !== true) throw new Error('생산자·수출자의 법인명과 공고의 예치율 적용 조건을 확인해 주세요.');
  const entry = date(input.entry_date), mode = input.reference_mode || 'published';
  if (!['published', 'manual'].includes(mode)) throw new Error('예치율 근거를 선택하세요.');
  let reference;
  if (mode === 'published') {
    reference = lookupAD(input);
    if (reference.status === 'unresolved') return { model_version: AD_MODEL_VERSION, status: 'unresolved', reference, reference_deposit_usd: null, scenario_deposit_usd: null };
  } else {
    for (const [key, label] of [['case_id', '사건번호'], ['company_name', '생산자·수출자 법인명'], ['reference_note', '적용 근거']]) {
      if (typeof input[key] !== 'string' || !input[key].trim() || input[key].length > 500) throw new Error(`${label}을 입력하세요.`);
    }
    if (!/^A-\d{3}-\d{3}$/.test(input.case_id)) throw new Error('반덤핑 사건번호는 A-000-000 형식으로 입력하세요.');
    let url; try { url = new URL(input.reference_url); } catch { throw new Error('예치율 출처 URL을 입력하세요.'); }
    if (url.protocol !== 'https:' || url.username || url.password) throw new Error('예치율 출처는 HTTPS URL을 입력하세요.');
    decimal(input.reference_rate_pct, '직접 확인한 예치율', 0, 10000);
    reference = { status: 'user_verified_reference', rate_pct: String(input.reference_rate_pct), case_id: input.case_id, company: { name: input.company_name }, entry_date: entry,
      source: { url: url.href, note: input.reference_note }, coverage: 'user_supplied_not_independently_verified' };
  }
  const value = decimal(input.entered_value_usd, '대상 수입 신고가격', 0.01), before = decimal(reference.rate_pct, '기준 AD 예치율', 0, 10000), after = decimal(input.scenario_rate_pct, '가정 AD 예치율', 0, 10000);
  const finance = decimal(input.annual_finance_pct, '연 금융비용률', 0, 100), days = decimal(input.holding_days, '예치 기간', 0, 36500);
  if (days % SCALE) throw new Error('예치 기간은 정수 일수로 입력하세요.');
  const denominator = SCALE * SCALE * 100n;
  const financingDenominator = denominator * SCALE * SCALE * 100n * 365n;
  return { model_version: AD_MODEL_VERSION, status: 'calculated', unit: 'USD', reference,
    inputs: { reference_mode: mode, entry_date: entry, entered_value_usd: String(input.entered_value_usd), scenario_rate_pct: String(input.scenario_rate_pct), annual_finance_pct: String(input.annual_finance_pct), holding_days: String(input.holding_days), scope_confirmed: true, identity_confirmed: true },
    reference_deposit_usd: money(value * before, denominator), scenario_deposit_usd: money(value * after, denominator), deposit_change_usd: money(value * (after - before), denominator),
    reference_financing_cost_usd: money(value * before * finance * days, financingDenominator), scenario_financing_cost_usd: money(value * after * finance * days, financingDenominator), financing_change_usd: money(value * (after - before) * finance * days, financingDenominator),
    limitations: ['AD 현금예치 부담 비교입니다. 최종 확정 관세·환급액·실제 덤핑마진을 예측하지 않습니다.', '일반·추가 관세, CVD, 수수료와 합산하지 않습니다. 예치금 전액은 비용 확정액이 아닙니다.', '금융비용은 입력한 금리·기간의 단리 365일 기준입니다. 실제 환급 시점·이자는 추정하지 않습니다.'] };
}

// Educational market-economy administrative-review path; not an official rate.
export function nonSelectedScenario(input) {
  if (input.process != null && input.process !== 'administrative_review') throw new Error('이 산정 경로는 시장경제 국가의 행정재심 교육용입니다.');
  if (input.equal_weights_assumption != null && typeof input.equal_weights_assumption !== 'boolean') throw new Error('동일 가중치 사용 여부를 확인하세요.');
  if (!Array.isArray(input.rows) || input.rows.length < 1 || input.rows.length > 30) throw new Error('조사기업을 1~30개 입력하세요.');
  const included = [], excluded = [];
  for (const row of input.rows) {
    if (row.entirely_facts_available != null && typeof row.entirely_facts_available !== 'boolean') throw new Error('전적으로 가용정보에 의존하는지 확인하세요.');
    const rate = decimal(row.margin_pct, '조사기업 마진', 0, 10000);
    const item = { name: String(row.name || '조사기업').slice(0, 100), margin_pct: String(row.margin_pct) };
    if (rate < 500000n || row.entirely_facts_available) excluded.push({ ...item, reason: row.entirely_facts_available ? '전적으로 가용정보에 의존' : '0% 또는 미소마진(<0.5%)' });
    else included.push({ ...item, rate, weight: row.weight });
  }
  const out = { educational_only: true, process: 'market_economy_administrative_review', included: included.map(({ rate, weight, ...x }) => x), excluded, rate_pct: null };
  if (!included.length) return { ...out, status: 'requires_reasonable_method', reason: '통상 가중평균에 포함할 마진이 없습니다. 기대방법을 포함한 합리적 산정과, 그 방법에서 벗어날 경우 근거 검토가 필요합니다. 0% 배정이 가능한 경우도 있지만 이 교육용 계산에서 자동으로 0%나 다른 양의 세율을 확정하지 않습니다. Commerce의 다른 합리적 방법 판단은 해당 결정문에서 확인하세요.' };
  if (included.length === 1) return { ...out, status: 'single_eligible_scenario', rate_pct: included[0].margin_pct, reason: '제외 조건 후 남은 한 마진을 반영한 원리 예시입니다.' };
  if (!input.equal_weights_assumption && included.some(r => r.weight == null || String(r.weight).trim() === '')) return { ...out, status: 'weights_required', reason: '공개된 산정 가중치가 없으면 실제 비선정 기업 세율을 재구성할 수 없습니다. 가중치를 입력하거나 동일 가중 가정을 선택하세요.' };
  let sum = 0n, weighted = 0n;
  for (const row of included) { const w = input.equal_weights_assumption === true ? SCALE : decimal(row.weight, '가중치'); sum += w; weighted += row.rate * w; }
  if (!sum) throw new Error('유효한 마진의 가중치 합은 0보다 커야 합니다.');
  const rate = (weighted * 2n + sum) / (2n * sum);
  return { ...out, status: input.equal_weights_assumption === true ? 'equal_weight_scenario' : 'weighted_scenario', rate_pct: `${rate / SCALE}.${String(rate % SCALE).padStart(6, '0')}`, reason: '입력 가중치의 교육용 결과입니다. Commerce의 공표 세율이나 판단 예측이 아닙니다.' };
}
