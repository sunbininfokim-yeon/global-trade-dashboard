// Non-nested CES demand / constant-elasticity supply, in baseline ratios.
// Riker & Schreiber (2020), section 2.1, equations (1)-(8), sigma = theta.
// Direct nonlinear equilibrium, not the USITC workbook's Euler algorithm.
export const MODEL_VERSION = 'country-ces-1';
export const SOURCES = [
  { title: 'USITC CES Tariff Model', url: 'https://www.usitc.gov/ces_tariff_model' },
  { title: 'Riker & Schreiber (2020), §2.1', url: 'https://www.usitc.gov/sites/default/files/data/gravity/structural_equations_for_pe_models_in_group_1.pdf' },
];
export class ModelError extends Error {}

function number(value, label, low, high) {
  if (value === null || value === undefined || typeof value === 'boolean' ||
      (typeof value !== 'number' && typeof value !== 'string') || String(value).trim() === '') {
    throw new ModelError(`${label}: 숫자를 입력하세요.`);
  }
  const n = Number(value);
  if (!Number.isFinite(n) || n < low || n > high) throw new ModelError(`${label}: ${low}~${high} 범위로 입력하세요.`);
  return n;
}

export function validate(input) {
  if (!input || !Array.isArray(input.rows) || input.rows.length < 2 || input.rows.length > 8) {
    throw new ModelError('같은 제품시장의 공급국을 2~8개 입력하세요.');
  }
  const sigma = number(input.sigma, '대체탄력성', 0.1, 20);
  const eta = number(input.eta, '수요탄력성', -10, -0.05);
  const seen = new Set();
  const rows = input.rows.map(row => {
    if (!row || typeof row.country !== 'string' || !/^[A-Z]{3}$/.test(row.country) || seen.has(row.country)) {
      throw new ModelError('공급국 코드는 중복 없이 선택하세요.');
    }
    seen.add(row.country);
    const expenditure = number(row.expenditure, `${row.country} 구매액`, 0.000001, 1e9);
    const before = number(row.tariff_before, `${row.country} 기존 관세`, 0, 300);
    const after = number(row.tariff_after, `${row.country} 가정 관세`, 0, 300);
    if (row.country === 'USA' && (before !== 0 || after !== 0)) throw new ModelError('미국 국내 공급에는 수입관세를 적용할 수 없습니다.');
    return { country: row.country, expenditure, tariff_before: before, tariff_after: after,
      supply_elasticity: number(row.supply_elasticity, `${row.country} 공급탄력성`, 0, 100) };
  });
  if (!seen.has(input.focus) || input.focus === 'USA' || input.focus === 'ROW') throw new ModelError('입력한 수출국 중 관심국가를 선택하세요.');
  return { sigma, eta, rows, focus: input.focus,
    product: String(input.product || 'custom').slice(0, 80), period: String(input.period || '가상 연간 기준').slice(0, 80),
    // Editing a sample does not make it verified observed data.
    basis: 'user_scenario', source_note: String(input.source_note || '사용자 가정 · 실제 시장 보정 전').slice(0, 1000) };
}

function logSumExp(terms) {
  const peak = Math.max(...terms);
  return peak + Math.log(terms.reduce((sum, term) => sum + Math.exp(term - peak), 0));
}
function demand(logPrices, weights, sigma, eta) {
  let logIndex, shares;
  if (Math.abs(sigma - 1) < 1e-7) {
    logIndex = weights.reduce((sum, weight, i) => sum + weight * logPrices[i], 0);
    shares = weights.slice();
  } else {
    const terms = weights.map((weight, i) => Math.log(weight) + (1 - sigma) * logPrices[i]);
    const norm = logSumExp(terms);
    logIndex = norm / (1 - sigma);
    shares = terms.map(term => Math.exp(term - norm));
  }
  return { logIndex, shares, logQuantities: logPrices.map(price => (eta + sigma) * logIndex - sigma * price) };
}
function linearSolve(matrix, rhs) {
  const a = matrix.map((row, i) => [...row, rhs[i]]), n = rhs.length;
  for (let j = 0; j < n; j++) {
    let pivot = j;
    for (let i = j + 1; i < n; i++) if (Math.abs(a[i][j]) > Math.abs(a[pivot][j])) pivot = i;
    if (Math.abs(a[pivot][j]) < 1e-12) throw new ModelError('이 탄력성 조합에서는 균형이 유일하지 않습니다. 가정을 조정하세요.');
    [a[j], a[pivot]] = [a[pivot], a[j]];
    const divisor = a[j][j];
    a[j] = a[j].map(v => v / divisor);
    for (let i = 0; i < n; i++) if (i !== j) {
      const factor = a[i][j];
      a[i] = a[i].map((v, k) => v - factor * a[j][k]);
    }
  }
  return a.map(row => row[n]);
}
const norm = vector => Math.max(...vector.map(v => Math.abs(v)));
function newton(equations, initial) {
  let x = initial.slice();
  for (let iteration = 0; iteration < 70; iteration++) {
    const f = equations(x), error = norm(f);
    if (!Number.isFinite(error)) throw new ModelError('계산 범위를 벗어났습니다. 가정을 조정하세요.');
    if (error < 1e-10) return { x, error, iteration };
    const h = 1e-5, jac = x.map(() => x.map(() => 0));
    for (let j = 0; j < x.length; j++) {
      const trial = x.slice(); trial[j] += h;
      const g = equations(trial);
      for (let i = 0; i < x.length; i++) jac[i][j] = (g[i] - f[i]) / h;
    }
    const step = linearSolve(jac, f.map(v => -v));
    let accepted = false;
    for (let damping = 1; damping >= 1 / 4096; damping /= 2) {
      const trial = x.map((v, i) => v + damping * step[i]);
      if (norm(equations(trial)) < error) { x = trial; accepted = true; break; }
    }
    if (!accepted) throw new ModelError('이 가정에서는 균형을 찾지 못했습니다. 관세 또는 탄력성을 조정하세요.');
  }
  throw new ModelError('균형 계산이 수렴하지 않았습니다.');
}

function solve(config) {
  const { rows, sigma, eta } = config;
  const total = rows.reduce((sum, row) => sum + row.expenditure, 0);
  const weights = rows.map(row => row.expenditure / total);
  const t0 = rows.map(row => 1 + row.tariff_before / 100), t1 = rows.map(row => 1 + row.tariff_after / 100);
  let prices = rows.map(() => 0), residual = 0, iterations = 0;
  // Continuation from the calibrated baseline avoids a single large jump.
  for (let step = 1; step <= 20; step++) {
    const shocks = t0.map((old, i) => Math.log((old + (t1[i] - old) * step / 20) / old));
    const equations = lp => {
      const d = demand(lp.map((p, i) => p + shocks[i]), weights, sigma, eta);
      return rows.map((row, i) => row.supply_elasticity * lp[i] - d.logQuantities[i]);
    };
    const answer = newton(equations, prices);
    prices = answer.x; residual = answer.error; iterations += answer.iteration;
  }
  const consumer = prices.map((p, i) => p + Math.log(t1[i] / t0[i]));
  const d = demand(consumer, weights, sigma, eta);
  const outputs = rows.map((row, i) => {
    const rp = Math.exp(prices[i]), rq = Math.exp(d.logQuantities[i]), rc = Math.exp(consumer[i]);
    const revenue0 = row.expenditure / t0[i], revenue1 = revenue0 * rp * rq;
    return { country: row.country, price_change_pct: (rc - 1) * 100,
      producer_price_change_pct: (rp - 1) * 100, volume_change_pct: (rq - 1) * 100,
      revenue_before: revenue0, revenue_after: revenue1, revenue_change_pct: (rp * rq - 1) * 100,
      spending_before: row.expenditure, spending_after: row.expenditure * rc * rq,
      share_before_pct: weights[i] * 100, share_after_pct: d.shares[i] * 100,
      share_change_pp: (d.shares[i] - weights[i]) * 100,
      duties_before: revenue0 * (t0[i] - 1), duties_after: revenue1 * (t1[i] - 1) };
  });
  const priceIndex = Math.exp(d.logIndex), spendingAfter = outputs.reduce((sum, row) => sum + row.spending_after, 0);
  const output = { model_version: MODEL_VERSION, unit: 'USD million', inputs: config, rows: outputs,
    market_price_change_pct: (priceIndex - 1) * 100, market_quantity_change_pct: (priceIndex ** eta - 1) * 100,
    spending_before: total, spending_after: spendingAfter,
    duties_before: outputs.reduce((sum, row) => sum + row.duties_before, 0),
    duties_after: outputs.reduce((sum, row) => sum + row.duties_after, 0),
    checks: { max_log_residual: residual, iterations, shares_sum_pct: d.shares.reduce((a, b) => a + b, 0) * 100,
      expenditure_identity_error: spendingAfter - total * priceIndex ** (1 + eta) } };
  if (outputs.some(row => Object.values(row).some(v => typeof v === 'number' && !Number.isFinite(v)))) {
    throw new ModelError('계산 결과가 유한하지 않습니다. 가정을 조정하세요.');
  }
  return output;
}

export function simulate(input, includeSensitivity = true) {
  const config = validate(input), result = solve(config);
  if (includeSensitivity) result.sensitivity = [...new Set([Math.max(0.1, config.sigma / 2), config.sigma, Math.min(20, config.sigma * 1.5)])]
    .sort((a, b) => a - b).map(sigma => {
      try {
        const trial = solve({ ...config, sigma }), focus = trial.rows.find(row => row.country === config.focus);
        return { sigma, status: 'calculated', volume_change_pct: focus.volume_change_pct, revenue_change_pct: focus.revenue_change_pct };
      } catch (err) { return { sigma, status: 'unavailable', reason: err.message }; }
    });
  return result;
}

export function example() {
  return { product: 'transformer', period: '가상 연간 기준', sigma: 4, eta: -1, focus: 'KOR',
    source_note: '학습용 가정. 기업 실적·DataWeb 관측값·실제 적용 관세율이 아닙니다.',
    rows: [
      { country: 'USA', expenditure: 50, tariff_before: 0, tariff_after: 0, supply_elasticity: 1.5 },
      { country: 'KOR', expenditure: 25, tariff_before: 0, tariff_after: 25, supply_elasticity: 3 },
      { country: 'ROW', expenditure: 25, tariff_before: 0, tariff_after: 0, supply_elasticity: 3 },
    ] };
}
