// Pure numerical port of portfolio_lab/{covariance,allocate,risk}.py.
// No dependencies or host APIs. All return inputs are LOG returns unless stated.
export const sum = a => a.reduce((s, v) => s + v, 0);
const zeros = n => Array.from({length: n}, () => Array(n).fill(0));
const dot = (a, b) => sum(a.map((v, i) => v * b[i]));
const clip = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
export function finite(x, name = 'number') {
  if (typeof x !== 'number' || !Number.isFinite(x)) throw new TypeError(`${name} must be finite`);
  return x;
}
export function vector(a, name = 'vector', min = 1) {
  if (!Array.isArray(a) || a.length < min) throw new RangeError(`${name}: insufficient observations`);
  for (const x of a) finite(x, name);
  return a;
}
export function matrix(x, minRows = 2) {
  if (!Array.isArray(x) || x.length < minRows || !Array.isArray(x[0]) || !x[0].length)
    throw new RangeError('matrix: insufficient observations/assets');
  for (const row of x) { vector(row); if (row.length !== x[0].length) throw new RangeError('ragged matrix'); }
  return x[0].length;
}
function square(c) {
  const n = matrix(c, 1);
  if (c.length !== n) throw new RangeError('covariance must be square');
  for (let i = 0; i < n; i++) {
    if (c[i][i] < 0) throw new RangeError('negative variance');
    for (let j = 0; j < i; j++) if (Math.abs(c[i][j] - c[j][i]) > 1e-12)
      throw new RangeError('covariance must be symmetric');
  }
  return n;
}
function centered(x) {
  const n = matrix(x), means = Array(n).fill(0);
  x.forEach(row => row.forEach((v, j) => { means[j] += v / x.length; }));
  return x.map(row => row.map((v, j) => v - means[j]));
}
function cross(x, divisor) {
  const c = zeros(x[0].length);
  for (let i = 0; i < c.length; i++) for (let j = i; j < c.length; j++) {
    c[i][j] = finite(sum(x.map(row => row[i] * row[j])) / divisor, 'covariance');
    c[j][i] = c[i][j];
  }
  return c;
}
export function sampleCov(x) { return cross(centered(x), x.length - 1); }
export function ewmaCov(x, lambda = 0.94) {
  finite(lambda); if (lambda < 0 || lambda > 1) throw new RangeError('lambda outside [0,1]');
  const y = centered(x), c = sampleCov(x);
  if (x.length < 5) return c;
  for (const row of y) for (let i = 0; i < c.length; i++) for (let j = 0; j < c.length; j++)
    c[i][j] = lambda * c[i][j] + (1 - lambda) * row[i] * row[j];
  return c;
}
// Symmetric Jacobi eigensolver: reproduce numpy eigh's eigenvalue floor,
// without importing a server/CDN numerical library. Eigenvector signs are irrelevant.
function eigenFloor(c, floor = 1e-12) {
  const n = c.length, a = c.map(row => row.slice()), v = zeros(n);
  v.forEach((row, i) => { row[i] = 1; });
  const tolerance = Math.max(...c.map((row, i) => Math.abs(row[i])), 1e-30) * 1e-15;
  let converged = false;
  for (let iter = 0; iter < 100 * n * n; iter++) {
    let p = 0, q = 0, largest = 0;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++)
      if (Math.abs(a[i][j]) > largest) { largest = Math.abs(a[i][j]); p = i; q = j; }
    if (largest <= tolerance) { converged = true; break; }
    const theta = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]);
    const cs = Math.cos(theta), sn = Math.sin(theta), ap = a[p][p], aq = a[q][q], off = a[p][q];
    a[p][p] = cs * cs * ap - 2 * sn * cs * off + sn * sn * aq;
    a[q][q] = sn * sn * ap + 2 * sn * cs * off + cs * cs * aq;
    a[p][q] = a[q][p] = 0;
    for (let k = 0; k < n; k++) {
      if (k !== p && k !== q) {
        const kp = a[k][p], kq = a[k][q];
        a[k][p] = a[p][k] = cs * kp - sn * kq;
        a[k][q] = a[q][k] = sn * kp + cs * kq;
      }
      const vp = v[k][p], vq = v[k][q];
      v[k][p] = cs * vp - sn * vq; v[k][q] = sn * vp + cs * vq;
    }
  }
  if (!converged) throw new RangeError('eigendecomposition did not converge');
  return c.map((row, i) => row.map((_, j) =>
    sum(v[i].map((vik, k) => vik * Math.max(a[k][k], floor) * v[j][k]))));
}
export function ledoitWolfCov(x) {
  const y = centered(x), t = x.length, n = x[0].length;
  // The Python single-asset branch uses ddof=1, no shrinkage/floor.
  if (n === 1) return {covariance: sampleCov(x), shrinkage: null, mean_corr: null};
  const s = cross(y, t), std = s.map((r, i) => Math.sqrt(Math.max(r[i], 1e-18)));
  let meanCorr = 0;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++)
    if (i !== j) meanCorr += s[i][j] / (std[i] * std[j]);
  meanCorr /= n * (n - 1);
  const prior = s.map((row, i) => row.map((val, j) => i === j ? val : meanCorr * std[i] * std[j]));
  const x2cross = cross(y.map(row => row.map(val => val * val)), t);
  let phi = 0, gamma = 0;
  s.forEach((row, i) => row.forEach((val, j) => {
    phi += x2cross[i][j] - val * val; gamma += (val - prior[i][j]) ** 2;
  }));
  const shrinkage = clip((gamma > 1e-18 ? phi / gamma : 1) / t, 0, 1);
  const sigma = s.map((row, i) => row.map((val, j) => shrinkage * prior[i][j] + (1 - shrinkage) * val));
  return {covariance: eigenFloor(sigma), shrinkage, mean_corr: meanCorr};
}
export function corrFromCov(c) {
  square(c);
  const d = c.map((row, i) => Math.sqrt(Math.max(row[i], 1e-18)));
  return c.map((row, i) => row.map((val, j) => i === j ? 1 : val / (d[i] * d[j])));
}
export function hierarchicalClusters(corr) {
  const n = square(corr), dist = corr.map(row => row.map(v => Math.sqrt(0.5 * (1 - clip(v, -1, 1)))));
  const groups = new Map(Array.from({length: n}, (_, i) => [i, [i]])), merges = [];
  let next = n;
  while (groups.size > 1) {
    const ids = [...groups.keys()].sort((a, b) => a - b);
    let pair, best = Infinity;
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const a = ids[i], b = ids[j], ga = groups.get(a), gb = groups.get(b);
      const val = sum(ga.map(x => sum(gb.map(y => dist[x][y])))) / (ga.length * gb.length);
      // Strict < plus sorted ids matches Python's deterministic tie policy.
      if (val < best) { best = val; pair = [a, b]; }
    }
    const [a, b] = pair;
    groups.set(next, [...groups.get(a), ...groups.get(b)]);
    groups.delete(a); groups.delete(b); merges.push([a, b, next++]);
  }
  return {order: [...groups.values()][0], merges};
}
const variance = (c, w) => dot(w, c.map(row => dot(row, w)));
export function hierarchicalRiskParity(c) {
  const n = square(c);
  if (n === 1) return [1];
  const {order} = hierarchicalClusters(corrFromCov(c)), weights = Array(n).fill(1);
  function clusterVar(items) {
    const iv = items.map(i => 1 / Math.max(c[i][i], 1e-18)), total = sum(iv), w = iv.map(v => v / total);
    return variance(items.map(i => items.map(j => c[i][j])), w);
  }
  function bisect(items) {
    if (items.length < 2) return;
    const mid = Math.floor(items.length / 2), left = items.slice(0, mid), right = items.slice(mid);
    const vl = clusterVar(left), vr = clusterVar(right);
    // Python divides by zero on all-flat data. Explicit neutral split keeps this finite.
    const alpha = vl + vr > 0 ? 1 - vl / (vl + vr) : 0.5;
    left.forEach(i => { weights[i] *= alpha; }); right.forEach(i => { weights[i] *= 1 - alpha; });
    bisect(left); bisect(right);
  }
  bisect(order);
  return weights.map(w => w / sum(weights));
}
export function riskContribution(weights, cov) {
  vector(weights); if (square(cov) !== weights.length) throw new RangeError('weight length mismatch');
  const pv = variance(cov, weights);
  if (pv <= 0) return weights.map(() => 0);
  return weights.map((w, i) => w * dot(cov[i], weights) / pv);
}
export function portfolioReturns(x, weights) {
  const n = matrix(x); vector(weights);
  if (n !== weights.length) throw new RangeError('weight length mismatch');
  return x.map(row => {
    const r = dot(row.map(Math.expm1), weights);
    // No silent clipping of insolvency into a finite log return.
    if (!Number.isFinite(r) || r <= -1) throw new RangeError('portfolio simple return <= -100% or overflow');
    return Math.log1p(r);
  });
}
export function annVol(r, periods = 252) {
  vector(r, 'returns', 2); finite(periods);
  if (periods <= 0) throw new RangeError('periods must be positive');
  const mean = sum(r) / r.length;
  return Math.sqrt(sum(r.map(v => (v - mean) ** 2)) / (r.length - 1) * periods);
}
export function annReturn(r, periods = 252) {
  vector(r, 'returns', 0); finite(periods);
  if (periods <= 0) throw new RangeError('periods must be positive');
  return finite(r.length ? Math.expm1(sum(r) * periods / r.length) : 0, 'annual return');
}
export function sharpe(r, rfAnn = 0.03, periods = 252) {
  finite(rfAnn); const vol = annVol(r, periods);
  return vol <= 1e-12 ? 0 : (annReturn(r, periods) - rfAnn) / vol;
}
// Input is SIMPLE returns, numpy linear quantile + inclusive tail mean.
export function histVarCvar(simple, alpha = 0.95) {
  vector(simple, 'simple returns', 0); finite(alpha);
  if (alpha <= 0 || alpha >= 1) throw new RangeError('confidence outside (0,1)');
  if (!simple.length) return [0, 0];
  const sorted = simple.slice().sort((a, b) => a - b), index = (sorted.length - 1) * (1 - alpha);
  const lo = Math.floor(index), hi = Math.ceil(index), q = sorted[lo] + (sorted[hi] - sorted[lo]) * (index - lo);
  const tail = simple.filter(v => v <= q);
  return [Math.max(-q, 0), Math.max(-sum(tail) / tail.length, 0)];
}
export function parametricVar(volAnn, alpha = 0.95, horizonDays = 1) {
  finite(volAnn); finite(horizonDays);
  if (volAnn < 0 || horizonDays <= 0 || ![0.95, 0.99].includes(alpha)) throw new RangeError('invalid VaR parameters');
  return (alpha === 0.99 ? 2.3263478740408408 : 1.6448536269514722) * volAnn / Math.sqrt(252) * Math.sqrt(horizonDays);
}
