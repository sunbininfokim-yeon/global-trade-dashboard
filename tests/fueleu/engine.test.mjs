// The browser ship check in shipping-fueleu.js must match tools/fueleu/engine.py.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = createRequire(import.meta.url)(path.join(here, '../../New for anti/shipping-fueleu.js'));

const CASES = [
  [95000, { lng_otto_ss: 12000, mdo_mgo: 600 }, { intra_eu: 0.1, at_berth: 0.05, extra_eu: 0.85 }],
  [50000, { hfo: 10000 }, { extra_eu: 1 }],
  [50000, { lfo: 3000, mdo_mgo: 800 }, { intra_eu: 1 }],
  [200000, { lng_diesel_ss: 30000 }, { extra_eu: 0.7, at_berth: 0.3 }],
  [8000, { lng_otto_ms: 900, hfo: 100 }, { intra_eu: 0.5, extra_eu: 0.5 }],
  [12000, { lng_lbsi: 2500 }, { at_berth: 1 }],
  [4000, { hfo: 100 }, { extra_eu: 1 }],
];
const py = JSON.parse(execFileSync('python3', ['-I', '-c', `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(here, '../../tools/fueleu'))})
import engine
cases = json.loads(sys.stdin.read())
print(json.dumps([engine.quick_check(gt, f, s) for gt, f, s in cases]))
`], { input: JSON.stringify(CASES), encoding: 'utf8' }));

const close = (a, b, where) => assert.ok(Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(b)), `${where}: ${a} != ${b}`);

CASES.forEach((c, i) => test(`case ${i}`, () => {
  const r = js.quickCheck(...c), p = py[i];
  assert.equal(r.in_scope, p.in_scope);
  if (!p.in_scope) return;
  for (const k of ['ghg_intensity', 'target', 'compliance_balance_tco2e', 'penalty_eur', 'margin_gco2e_per_mj']) close(r[k], p[k], k);
  assert.equal(r.position, p.position);
  assert.equal(r.first_deficit_period, p.first_deficit_period);
  r.timeline.forEach((t, j) => { close(t.compliance_balance_tco2e, p.timeline[j].compliance_balance_tco2e, `t${j}`); close(t.penalty_eur, p.timeline[j].penalty_eur, `pen${j}`); });
}));

test('fuel table matches Annex II defaults in the engine', () => {
  const pyFuels = JSON.parse(execFileSync('python3', ['-I', '-c',
    `import json,sys;sys.path.insert(0,${JSON.stringify(path.join(here, '../../tools/fueleu'))});import engine;print(json.dumps(engine.FUELS))`], { encoding: 'utf8' }));
  assert.deepEqual(Object.keys(js.FUELS).sort(), Object.keys(pyFuels).sort());
  for (const [k, f] of Object.entries(pyFuels)) for (const n of ['lcv', 'wtt', 'cf_co2', 'cf_ch4', 'cf_n2o', 'slip']) assert.equal(js.FUELS[k][n], f[n], `${k}.${n}`);
});

// ---------------------------------------------------------------- blends, voyages, pooling

const runPy = (code, input) => JSON.parse(execFileSync('python3', ['-I', '-c',
  `import json, sys\nsys.path.insert(0, ${JSON.stringify(path.join(here, '../../tools/fueleu'))})\nimport engine\n${code}`],
  { input: JSON.stringify(input), encoding: 'utf8' }));

const deepClose = (a, b, where) => {
  if (b === null || b === undefined) return assert.equal(a ?? null, null, where);
  if (typeof b === 'number') return close(a, b, where);
  if (Array.isArray(b)) { assert.equal(a.length, b.length, `${where}.length`); return b.forEach((v, i) => deepClose(a[i], v, `${where}[${i}]`)); }
  if (typeof b === 'object') return Object.keys(b).forEach(k => deepClose(a[k], b[k], `${where}.${k}`));
  assert.equal(a, b, where);
};

const BLENDS = [
  ['lfo', 0.3, 10000, { extra_eu: 1 }, 95.8, 300, 14.9, true],
  ['hfo', 0.05, 4000, { intra_eu: 0.4, extra_eu: 0.6 }, 120, null, 11.2, true],
  ['mdo_mgo', 1, 500, { at_berth: 1 }, 100, 500, 14.9, true],
  ['hfo', 0.3, 1000, { extra_eu: 1 }, 100, null, 14.9, false],
];
test('blend economics matches Python', () => {
  const py = runPy(`
print(json.dumps([engine.blend_economics(b, s, t, 2025, sh, pool, prem, e, cert) for b, s, t, sh, pool, prem, e, cert in json.loads(sys.stdin.read())]))`, BLENDS);
  BLENDS.forEach(([b, s, t, sh, pool, prem, e, cert], i) => {
    const r = js.blendEconomics(b, s, t, { share: sh, poolPrice: pool, premium: prem, eValue: e, certified: cert });
    const { bio_fuel, ...rest } = py[i];
    deepClose(r, rest, `blend${i}`);
  });
});

const LEGS = [
  { id: 'V1', status: 'actual', origin: { country: 'CN' }, destination: { country: 'NL' }, at_sea: { hfo: 4200 }, at_berth: { mdo_mgo: 60 } },
  { id: 'V2', status: 'actual', origin: { country: 'NL' }, destination: { country: 'DE' }, at_sea: { mdo_mgo: 140 }, at_berth: { mdo_mgo: 45 } },
  { id: 'V3', status: 'actual', origin: { country: 'DE' }, destination: { country: 'ES', outermost: true }, at_sea: { hfo: 520 }, at_berth: { mdo_mgo: 30 } },
  { id: 'V4', status: 'planned', origin: { country: 'ES', outermost: true }, destination: { country: 'SG' }, at_sea: { lng_otto_ss: 3900 } },
  { id: 'V5', status: 'planned', origin: { country: 'SG' }, destination: { country: 'CN' }, at_sea: { hfo: 900 } },
];
test('voyage year, options and fleet pooling match Python', () => {
  const py = runPy(`
legs = json.loads(sys.stdin.read())
y = engine.ship_year(legs, 2026, pool_price=95.8, consecutive_deficits=1)
out = {"year": y, "opt": engine.options(y["full_year"], 95.8, 60.0), "opt_now": engine.options(y["full_year"], 95.8),
       "fleet": engine.fleet_pool({"a": y["full_year"]["compliance_balance_tco2e"], "b": 3200.0, "c": -900.0}),
       "short": engine.fleet_pool({"a": 50.0, "b": -200.0})}
for l in out["year"]["legs"]: l.pop("route")
for k in ("lines",):
    out["year"]["full_year"].pop(k); out["year"]["actual_to_date"].pop(k)
print(json.dumps(out))`, LEGS);
  const y = js.shipYear(LEGS, 2026, 95.8, { consecutiveDeficits: 1 });
  for (const k of ['ghg_intensity', 'energy_mj', 'target', 'compliance_balance_tco2e', 'penalty_eur', 'penalty_eur_per_tco2e', 'consecutive_multiplier', 'borrow_limit_tco2e']) {
    close(y.full_year[k], py.year.full_year[k], `full.${k}`);
    close(y.actual_to_date[k], py.year.actual_to_date[k], `ytd.${k}`);
  }
  deepClose(y.legs, py.year.legs, 'legs');
  const strip = o => ({ ...o, rows: o.rows.map(({ label, ...r }) => r) });
  deepClose(strip(js.options(y.full_year, 95.8, 60)), strip(py.opt), 'options');
  deepClose(strip(js.options(y.full_year, 95.8)), strip(py.opt_now), 'options_now');
  const { check: c1, ...f1 } = js.fleetPool({ a: y.full_year.compliance_balance_tco2e, b: 3200, c: -900 });
  const { check: p1, ...pf1 } = py.fleet;
  deepClose(f1, pf1, 'fleet');
  assert.equal(c1.valid, p1.valid);
  const { check: c2, ...f2 } = js.fleetPool({ a: 50, b: -200 });
  const { check: p2, ...pf2 } = py.short;
  deepClose(f2, pf2, 'short');
  assert.equal(c2.valid, p2.valid);
});
