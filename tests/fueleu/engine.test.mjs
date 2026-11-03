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
