'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseReleasePoint } = require('../sync-us-code');

test('release parser accepts official heading markup and rejects stale/error pages', () => {
  assert.equal(parseReleasePoint('<h2>Current Release Point</h2>\n<h3>Public Law 119-142</h3>'), '119-142');
  assert.equal(parseReleasePoint('Current&nbsp;Release Point Public Law 119-143'), '119-143');
  for (const html of ['Access denied', '<h1>Not found</h1>', 'Prior release Public Law 119-100', 'Current Release Point unavailable']) {
    assert.throws(() => parseReleasePoint(html), /current release point missing/);
  }
});

const workflow = fs.readFileSync(path.join(__dirname, '../../.github/workflows/sync-congress.yml'), 'utf8');
function condition(stepName, context) {
  const block = workflow.split(`- name: ${stepName}\n`)[1].split('\n      - name:')[0];
  const expression = block.match(/if: \$\{\{ (.*?) \}\}/)[1];
  return Function('steps', 'vars', 'cancelled', `return (${expression});`)(context.steps, context.vars, () => context.cancelled);
}
function context(overrides = {}) {
  return { steps: { validate: { outcome: 'success' }, congress: { outcome: 'success' }, federal_register: { outcome: 'success' }, public_laws: { outcome: 'failure' } }, vars: { POLICY_FAVORITES_MAIL_ENABLED: 'true' }, cancelled: false, ...overrides };
}
test('reference or embedding failure does not suppress independently eligible notifications', () => {
  const c = context(); // Global success() would be false after a failed reference step.
  assert.equal(condition('Refresh policy document embeddings', c), true);
  assert.equal(condition('Notify favorited bill/EO changes', c), true);
  c.vars.POLICY_FAVORITES_MAIL_ENABLED = 'false';
  assert.equal(condition('Notify favorited bill/EO changes', c), false);
});
test('cancellation, validation failure and failed source collectors keep downstream gates closed', () => {
  for (const outcome of ['failure', 'skipped', 'cancelled']) {
    const c = context(); c.steps.validate.outcome = outcome;
    assert.equal(condition('Refresh policy document embeddings', c), false);
    assert.equal(condition('Notify favorited bill/EO changes', c), false);
  }
  const c = context(); c.cancelled = true;
  assert.equal(condition('Refresh policy document embeddings', c), false);
  assert.equal(condition('Notify favorited bill/EO changes', c), false);
  for (const key of ['congress', 'federal_register']) {
    const failed = context(); failed.steps[key].outcome = 'failure';
    assert.equal(condition('Notify favorited bill/EO changes', failed), false);
  }
  const allFailed = context();
  for (const key of ['congress', 'federal_register', 'public_laws']) allFailed.steps[key].outcome = 'failure';
  assert.equal(condition('Refresh policy document embeddings', allFailed), false);
});
