const { test } = require('node:test');
const assert = require('node:assert/strict');
const { resumeTime } = require('./policy-mac-resume');
const now = Date.parse('2026-10-02T04:00:00Z');
test('restart preserves the remaining wait instead of repeating a finished collection', () => {
  assert.equal(resumeTime('2026-10-02T07:50:12.624Z', now), '2026-10-02T07:50:12.624Z');
});
test('due or absent schedules run normally', () => {
  assert.equal(resumeTime(null, now), null);
  assert.equal(resumeTime('2026-10-02T03:00:00Z', now), null);
});
test('invalid or unexpectedly distant schedules stop instead of starting collection', () => {
  assert.throws(() => resumeTime('invalid', now), /invalid_resume_schedule/);
  assert.throws(() => resumeTime('2026-10-03T00:00:00Z', now), /invalid_resume_schedule/);
});
