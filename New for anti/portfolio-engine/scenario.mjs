/** T25b: pure historical scenario / long-short research engine. No I/O.
 * Quotes, dated FX, exchange calendars and UI remain caller-owned.
 */
import {finite, vector, sum} from './math.mjs';
import {regression, summarizeReturns, blockBootstrapMean, rollingHistoricalVar} from './scenario-stats.mjs';
export {regression, summarizeReturns, blockBootstrapMean, rollingHistoricalVar} from './scenario-stats.mjs';

function date(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new TypeError('ISO date required');
  const value = Date.parse(s + 'T00:00:00Z');
  if (!Number.isFinite(value) || new Date(value).toISOString().slice(0, 10) !== s) throw new RangeError('invalid date');
  return value;
}
function validate(input) {
  const {dates, assets, factors = [], benchmark, baseCurrency = 'KRW'} = input;
  if (!['KRW', 'USD'].includes(baseCurrency)) throw new RangeError('base currency must be KRW/USD');
  if (!Array.isArray(dates) || dates.length < 3) throw new RangeError('at least three common closing observations required');
  let last = -Infinity;
  for (const d of dates) {
    const t = date(d);
    if (t <= last || [0, 6].includes(new Date(t).getUTCDay())) throw new RangeError('unique ordered common weekday dates required');
    last = t;
  }
  if (!Array.isArray(assets) || !assets.length || !Array.isArray(factors)) throw new TypeError('asset/factor arrays required');
  const seen = new Set();
  for (const series of [...assets, ...factors, ...(benchmark ? [benchmark] : [])]) {
    if (!series || typeof series.id !== 'string' || !series.id || seen.has(series.id)) throw new TypeError('unique series IDs required');
    seen.add(series.id);
    const values = series.prices ?? series.values;
    vector(values, 'positive aligned series', dates.length);
    if (values.length !== dates.length || (series.change !== 'difference' && values.some(v => v <= 0))) throw new RangeError('series length mismatch or nonpositive price; no missing-value filling');
  }
  for (const a of [...assets, ...(benchmark ? [benchmark] : [])]) {
    if (a.baseCurrency !== baseCurrency || !Array.isArray(a.prices) || a.prices.some(v => v <= 0)) throw new RangeError('positive prices must be converted to the selected base currency with dated FX');
  }
  for (const f of factors) if (!Array.isArray(f.values) || !['relative', 'difference'].includes(f.change ?? 'relative')) throw new RangeError('factor change must be relative or difference');
  // Validate the arrays actually consumed below, even if a caller supplied both fields.
  for (const f of factors) {
    vector(f.values, 'factor values', dates.length);
    if (f.values.length !== dates.length || ((f.change ?? 'relative') === 'relative' && f.values.some(v => v <= 0)))
      throw new RangeError('invalid aligned factor values');
  }
  const start = input.startDate ?? dates[0], end = input.endDate ?? dates.at(-1);
  if (date(start) >= date(end) || start < dates[0] || end > dates.at(-1)) throw new RangeError('requested period outside supplied history or inverted');
  const lo = dates.findIndex(d => d >= start), hi = dates.findLastIndex(d => d <= end);
  if (hi - lo < 2) throw new RangeError('selected period needs at least two return observations');
  if (input.holdoutStart !== undefined && (date(input.holdoutStart) <= date(dates[lo]) || input.holdoutStart > dates[hi]))
    throw new RangeError('holdoutStart must be inside the selected period');
  return {dates, assets, factors, benchmark, baseCurrency, lo, hi};
}
const simpleReturns = values => values.slice(1).map((v, i) => finite(v / values[i] - 1));
const changes = (values, kind) => kind === 'difference' ? values.slice(1).map((v, i) => v - values[i]) : simpleReturns(values);

function relationships(ctx, input) {
  const {assets, factors, lo, hi, dates} = ctx;
  const series = [...assets.map(a => ({id: a.id, role: 'asset', values: a.prices})),
    ...factors.map(f => ({id: f.id, role: 'factor', values: f.values, change: f.change ?? 'relative'}))];
  const observations = series.map(s => ({...s, r: changes(s.values.slice(lo, hi + 1), s.change)}));
  const matrix = observations.map(a => observations.map(b => regression(a.r, b.r).correlation));
  const exposures = assets.flatMap(a => factors.map(f => {
    const y = simpleReturns(a.prices.slice(lo, hi + 1)), x = changes(f.values.slice(lo, hi + 1), f.change);
    return {asset_id: a.id, factor_id: f.id, factor_change: f.change ?? 'relative', factor_unit: f.unit ?? null, contemporaneous: regression(x, y),
      factor_leads_one_bar: regression(x.slice(0, -1), y.slice(1)), causal: false};
  }));
  const requested = input.hypotheses ?? [];
  if (!Array.isArray(requested)) throw new TypeError('hypotheses must be an array');
  const hypotheses = requested.map(h => {
    const exp = exposures.find(e => e.asset_id === h.assetId && e.factor_id === h.factorId);
    if (!exp || ![-1, 1].includes(h.expectedSign)) throw new RangeError('invalid asset-factor sign hypothesis');
    const beta = exp.contemporaneous.beta;
    return {asset_id: h.assetId, factor_id: h.factorId, expected_sign: h.expectedSign, beta,
      observed_direction: beta === null || beta === 0 ? 'undetermined' : Math.sign(beta) === h.expectedSign ? 'consistent' : 'opposite',
      statistical_significance: 'not_tested', causal: false};
  });
  return {ids: observations.map(s => s.id), correlation: matrix, correlation_basis: 'asset_simple_returns_vs_factor_relative_or_absolute_changes',
    factor_exposures: exposures, hypotheses,
    series: observations.map(s => ({id: s.id, role: s.role,
      normalized: s.values.slice(lo, hi + 1).map((v, i) => ({date: dates[lo + i],
        value: s.change === 'difference' ? v - s.values[lo] : v / s.values[lo] * 100})),
      display_basis: s.change === 'difference' ? 'change_from_start_in_original_units' : 'index_100',
      metrics: s.change === 'difference' ? {n_obs: s.r.length, total_change: s.values[hi] - s.values[lo], return_metrics: null} : summarizeReturns(s.r, input.risk)}))};
}

function compileCondition(condition, ctx) {
  if (!condition) return null;
  const h = condition.holdingBars;
  if (!Number.isInteger(h) || h < 1) throw new RangeError('positive holdingBars required');
  function compile(node, depth = 0) {
    if (!node || depth > 8) throw new RangeError('invalid/deep condition tree');
    if (node.all || node.any) {
      if (node.all && node.any) throw new RangeError('use all OR any at a condition node');
      const members = node.all ?? node.any;
      if (!Array.isArray(members) || !members.length || members.length > 20) throw new RangeError('invalid condition group');
      const children = members.map(n => compile(n, depth + 1));
      return {ready: Math.max(...children.map(c => c.ready)),
        matched: i => node.all ? children.every(c => c.matched(i)) : children.some(c => c.matched(i))};
    }
    const f = ctx.factors.find(f => f.id === node.factorId);
    const {lookbackBars: k, threshold, operator = 'gte'} = node;
    finite(threshold);
    if (!f || !Number.isInteger(k) || k < 1 || !['gte', 'lte'].includes(operator)) throw new RangeError('invalid factor condition');
    return {ready: k, matched: i => {
      if (i < k) return false;
      const change = f.change === 'difference' ? f.values[i] - f.values[i - k] : f.values[i] / f.values[i - k] - 1;
      return operator === 'gte' ? change >= threshold : change <= threshold;
    }};
  }
  const root = compile(condition), matched = root.matched;
  // Strictly next COMMON closing bar. The price at the signal close cannot be used as a fill.
  return {holdingBars: h, signal: i => i >= root.ready + 1 && matched(i) && !matched(i - 1),
    matched, description: {rule: JSON.parse(JSON.stringify(condition)), holding_bars: h,
      trigger: 'false_to_true_crossing', execution_lag_common_bars: 1}};
}

function simulate(ctx, input, condition) {
  const {dates, assets, lo, hi} = ctx, spec = input.strategy;
  vector(spec.weights, 'signed NAV weights');
  if (spec.weights.length !== assets.length || sum(spec.weights.map(Math.abs)) === 0) throw new RangeError('strategy weights mismatch or zero exposure');
  const rebalance = spec.rebalance ?? 'buy_and_hold';
  if (!['buy_and_hold', 'monthly', 'daily'].includes(rebalance)) throw new RangeError('unknown rebalance rule');
  const capital = spec.initialCapital ?? null;
  if (capital !== null && finite(capital) <= 0) throw new RangeError('capital must be positive');
  const initial = capital ?? 100;
  assets.forEach((a, j) => { if (spec.weights[j] < 0 && a.shortable === false) throw new RangeError(`short unavailable: ${a.id}`); });
  let cash = initial, units = assets.map(() => 0), open = false, entry = -1, entryNav = initial, exitAt = hi, status = 'completed';
  const curve = [], returns = [], returnDates = [], trades = [], episodes = [], pnl = assets.map(() => 0);
  function setWeights(i, nav, weights, reason, signalIndex = null) {
    const newUnits = weights.map((w, j) => w * nav / assets[j].prices[i]);
    newUnits.forEach((u, j) => {
      const delta = u - units[j];
      if (Math.abs(delta) > 1e-12) trades.push({date: dates[i], asset_id: assets[j].id, reason,
        signal_date: signalIndex === null ? null : dates[signalIndex], delta_index_units: delta,
        price_base: assets[j].prices[i], signed_notional: delta * assets[j].prices[i]});
    });
    units = newUnits; cash = nav - sum(units.map((u, j) => u * assets[j].prices[i]));
  }
  for (let i = lo; i <= hi; i++) {
    if (i > lo) units.forEach((u, j) => { pnl[j] += u * (assets[j].prices[i] - assets[j].prices[i - 1]); });
    const nav = finite(cash + sum(units.map((u, j) => u * assets[j].prices[i])), 'NAV');
    if (i > lo) { returns.push(finite(nav / curve.at(-1).nav - 1)); returnDates.push(dates[i]); }
    if (nav <= 0) {
      status = 'insolvent'; curve.push({date: dates[i], nav, equity_index: nav / initial * 100, cash, gross_of_nav: null, net_of_nav: null});
      if (open) episodes.push({entry: dates[entry], exit: dates[i], return: nav / entryNav - 1, completed_holding: false, reason: 'insolvent'});
      break;
    }
    let closed = false;
    if (open && (i >= exitAt || i === hi)) {
      episodes.push({entry: dates[entry], exit: dates[i], return: nav / entryNav - 1,
        completed_holding: !condition || i >= exitAt, reason: i >= exitAt ? 'holding_complete' : 'period_end_censored'});
      setWeights(i, nav, assets.map(() => 0), 'exit'); open = false; closed = true;
    }
    if (!open && !closed && i < hi && (condition ? condition.signal(i - 1) : i === lo)) {
      setWeights(i, nav, spec.weights, 'entry', condition ? i - 1 : null);
      open = true; entry = i; entryNav = nav; exitAt = condition ? i + condition.holdingBars : hi;
    } else if (open && i !== entry && (rebalance === 'daily' || (rebalance === 'monthly' && dates[i].slice(0, 7) !== dates[i - 1].slice(0, 7)))) {
      setWeights(i, nav, spec.weights, 'rebalance');
    }
    const values = units.map((u, j) => u * assets[j].prices[i]);
    curve.push({date: dates[i], nav, equity_index: nav / initial * 100, cash,
      gross_of_nav: sum(values.map(Math.abs)) / nav, net_of_nav: sum(values) / nav});
  }
  const metrics = summarizeReturns(returns, input.risk), totalPnl = curve.at(-1).nav - initial;
  const completeEpisodes = episodes.filter(e => e.completed_holding);
  return {status, mode: condition ? 'conditional_long_short' : 'period_long_short', initial_capital: capital,
    normalized_initial_nav: initial, weight_basis: 'signed_fraction_of_NAV_not_net_exposure',
    monetary_results: capital === null ? null : {currency: ctx.baseCurrency, pnl: totalPnl,
      historical_var_amount_on_initial_nav: metrics.var_1bar * initial, historical_cvar_amount_on_initial_nav: metrics.cvar_1bar * initial},
    metrics, curve, simple_returns: returns, return_dates: returnDates, trade_ledger: trades, episodes,
    n_completed_episodes: completeEpisodes.length,
    episode_win_fraction: completeEpisodes.length ? completeEpisodes.filter(e => e.return > 0).length / completeEpisodes.length : null,
    pnl_attribution: assets.map((a, j) => ({asset_id: a.id, return_on_initial_nav: pnl[j] / initial,
      amount: capital === null ? null : pnl[j]})),
    attribution_residual: (totalPnl - sum(pnl)) / initial,
    rolling_var: rollingHistoricalVar(returnDates, returns, input.risk)};
}

function evidence(ctx, input, result, relation, condition) {
  const r = result.simple_returns, dates = result.return_dates;
  let benchmark = null;
  if (ctx.benchmark) {
    const b = ctx.benchmark.prices;
    const br = dates.map(d => { const i = ctx.dates.indexOf(d); return b[i] / b[i - 1] - 1; });
    benchmark = {id: ctx.benchmark.id, metrics: summarizeReturns(br, input.risk),
      excess_total_return: result.metrics.total_return - summarizeReturns(br, input.risk).total_return,
      beta: regression(br, r), active_returns: r.map((v, i) => v - br[i])};
  }
  const holdoutIndex = input.holdoutStart === undefined ? -1 : dates.findIndex(d => d >= input.holdoutStart);
  const split = holdoutIndex >= 0 ? {
    split_date: input.holdoutStart, rule_reoptimized: false, selection_independence_verified: false,
    earlier: summarizeReturns(r.slice(0, holdoutIndex), input.risk),
    later: summarizeReturns(r.slice(holdoutIndex), input.risk),
    later_mean_ci: blockBootstrapMean(r.slice(holdoutIndex), input.bootstrap),
  } : null;
  const ci = blockBootstrapMean(r, input.bootstrap);
  const checks = {
    positive_period_return: result.metrics.total_return > 0,
    beats_benchmark: benchmark ? benchmark.excess_total_return > 0 : null,
    later_period_positive: split ? split.later.total_return > 0 : null,
    later_mean_ci_above_zero: split?.later_mean_ci.lower == null ? null : split.later_mean_ci.lower > 0,
    enough_later_observations: split ? split.later.n_obs >= 60 : false,
    enough_completed_episodes: condition ? result.n_completed_episodes >= 10 : null,
    hypothesized_directions_consistent: relation.hypotheses.length ? relation.hypotheses.every(h => h.observed_direction === 'consistent') : null,
  };
  let label = 'insufficient_evidence';
  if (result.status === 'insolvent' || (r.length >= 40 && !checks.positive_period_return)) label = 'not_supported_in_period';
  else if (checks.enough_later_observations && (!condition || checks.enough_completed_episodes)) {
    label = checks.positive_period_return && checks.beats_benchmark === true && checks.later_mean_ci_above_zero === true
      && checks.hypothesized_directions_consistent !== false ? 'historical_support_only' : 'mixed_evidence';
  }
  const copy = {
    insufficient_evidence: '이 구간의 결과만으로 전략의 유효성을 판단하기에는 검증 근거가 부족합니다.',
    not_supported_in_period: '선택한 과거 구간에서는 이 전략의 수익 가설을 지지하지 못했습니다.',
    historical_support_only: '일부 과거 검증 조건이 가설을 지지합니다. 미래 수익이나 실거래 가능성을 보장하지 않습니다.',
    mixed_evidence: '구간 수익·비교지수·후반 검증 결과가 일관되게 가설을 지지하지는 않습니다.',
  };
  return {benchmark, split, mean_return_ci: ci, assessment: {status: label, headline_ko: copy[label], checks,
    policy: 'transparent_research_heuristic_not_significance_test', investment_decision: null, causal_claim: false,
    multiple_testing_adjusted: false, episode_independence_verified: false, execution_validated: false}};
}

/** Main entry: omit strategy for relation-only; omit initialCapital for index returns.
 * 'factor' (e.g. gas) is NOT a purchased position unless explicitly an asset too
 * under a distinct ID. No natural-language causal rule is turned into a forecast.
 */
export function runScenario(input) {
  const ctx = validate(input), condition = compileCondition(input.condition, ctx);
  const relation = relationships(ctx, input);
  const warnings = [
    {code: 'RETROSPECTIVE_SELECTION', message_ko: '기간·종목·규칙을 결과를 본 뒤 선택했다면 과적합될 수 있습니다. 후반 구간도 반복 조회했다면 독립 검증이 아닙니다.'},
    {code: 'NOT_CAUSAL', message_ko: '수익률 상관·민감도는 인과관계나 기업 이익 변화를 증명하지 않습니다.'},
    {code: 'CALENDAR_ASSUMPTION', message_ko: '입력은 공통 거래일·역사적 환율로 정렬한 가격이어야 합니다. 한 관측 구간이 여러 달력일일 수 있습니다.'},
  ];
  if (ctx.hi - ctx.lo < 60) warnings.push({code: 'SHORT_SAMPLE', message_ko: '60개 미만 수익률 관측: 위험·관계 추정이 불안정할 수 있습니다.'});
  if ((ctx.hi - ctx.lo) * (1 - (input.risk?.confidence ?? 0.95)) < 5) warnings.push({code: 'SPARSE_VAR_TAIL', message_ko: '꼬리 표본이 적어 VaR·CVaR를 정밀한 손실 한도로 해석하면 안 됩니다.'});
  const priced = [...ctx.assets, ...(ctx.benchmark ? [ctx.benchmark] : [])];
  if (priced.some(a => a.priceBasis !== 'adjusted_total_return')) warnings.push({code: 'CORPORATE_ACTIONS_UNVERIFIED', message_ko: '분할·배당 반영 여부가 확인되지 않은 가격이 포함됩니다.'});
  if (priced.some(a => !a.source) || ctx.factors.some(f => !f.source)) warnings.push({code: 'SOURCE_UNSPECIFIED', message_ko: '일부 시계열의 출처 메타데이터가 없습니다.'});
  if (ctx.factors.some(f => f.availability !== 'known_by_common_close')) warnings.push({code: 'POINT_IN_TIME_UNVERIFIED', message_ko: '관찰 변수의 당시 공표시각·수정 이력을 확인하지 않았습니다. 날짜만 과거라고 당시 이용 가능했던 데이터는 아닙니다.'});
  if (ctx.dates.some((d, i) => i > ctx.lo && i <= ctx.hi && (date(d) - date(ctx.dates[i - 1])) / 86400000 > 4))
    warnings.push({code: 'LONG_CALENDAR_GAPS', message_ko: '긴 관측 공백이 있습니다. 연환산 및 1일 위험으로 해석하지 마세요.'});
  const output = {schema_version: 'scenario_backtest_v1', base_currency: ctx.baseCurrency,
    run_config: JSON.parse(JSON.stringify({strategy: input.strategy ?? null, condition: input.condition ?? null,
      hypotheses: input.hypotheses ?? [], holdoutStart: input.holdoutStart ?? null,
      risk: {confidence: 0.95, window: 60, rfAnn: 0, periods: 252, ...input.risk},
      bootstrap: {blockLength: 5, replications: 500, seed: 1729, ...input.bootstrap}})),
    source_manifest: [...ctx.assets, ...ctx.factors, ...(ctx.benchmark ? [ctx.benchmark] : [])].map(s => ({id: s.id,
      source: s.source ?? null, dataset_version: s.datasetVersion ?? null, price_basis: s.priceBasis ?? null,
      factor_change: s.change ?? null, unit: s.unit ?? null, availability: s.availability ?? null})),
    period: {requested_start: input.startDate ?? ctx.dates[0], requested_end: input.endDate ?? ctx.dates.at(-1),
      actual_start: ctx.dates[ctx.lo], actual_end: ctx.dates[ctx.hi], n_return_observations: ctx.hi - ctx.lo},
    relationship: relation, condition: condition?.description ?? null, strategy: null, warnings,
    methodology: {hypothesis_test: 'historical_research_not_investment_advice', risk_window: 'entire_selected_period',
      risk_horizon: 'one_common_observation_bar', execution: 'common_close_fractional_total_return_index_units',
      signal_execution: 'signal_on_previous_common_close_execute_next_common_close',
      transaction_costs: 'excluded', borrow_fees: 'excluded', financing_and_cash_interest: 'excluded', taxes: 'excluded',
      short_recall_margin_liquidity: 'not_modeled', automatic_optimization: false, prediction: false}};
  if (!input.strategy) {
    if (condition) warnings.push({code: 'CONDITION_NOT_TRADED', message_ko: '관계 분석 모드입니다. 조건에 따른 진입·청산 검증은 롱·숏 비중 입력 후 수행합니다.'});
    return output;
  }
  warnings.push({code: 'GROSS_RESEARCH_PERFORMANCE', message_ko: '비용·세금·대차료·조달금리 차감 전 가상 성과이며, 체결·증거금·숏 리콜은 검증하지 않았습니다.'});
  if (input.strategy.weights?.some((w, j) => w < 0 && ctx.assets[j]?.shortable !== true))
    warnings.push({code: 'SHORT_AVAILABILITY_UNVERIFIED', message_ko: '공매도 대차 가능 여부가 확인되지 않은 종목이 있습니다.'});
  const result = simulate(ctx, input, condition);
  output.strategy = {...result, ...evidence(ctx, input, result, relation, condition)};
  if (result.status === 'insolvent') warnings.push({code: 'INSOLVENT_STOP', message_ko: '순자산이 0 이하가 되어 계산을 중단했습니다. 손실을 임의로 잘라내지 않았습니다.'});
  return output;
}

/** User-defined sensitivity comparisons, not an optimizer or a best-trade picker.
 * Overrides are complete top-level fields (strategy/condition are not deep merged).
 */
export function compareScenarioVariants(base, variants) {
  if (!Array.isArray(variants) || variants.length < 1 || variants.length > 30) throw new RangeError('provide 1..30 explicit variants');
  const seen = new Set();
  const results = variants.map(v => {
    if (!v || typeof v.id !== 'string' || !v.id || seen.has(v.id) || !v.overrides || typeof v.overrides !== 'object')
      throw new TypeError('unique variant id and overrides required');
    seen.add(v.id);
    const result = runScenario({...base, ...v.overrides});
    result.warnings.push({code: 'MULTIPLE_VARIANTS', message_ko: '여러 조건 중 좋은 결과만 고르면 과적합됩니다. 이 비교는 다중검정 보정을 수행하지 않습니다.'});
    return {id: v.id, result};
  });
  return {schema_version: 'scenario_comparison_v1', n_variants: variants.length, automatic_selection: false,
    multiple_testing_adjusted: false, results};
}
