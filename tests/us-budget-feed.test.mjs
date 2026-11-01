import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateFeed, sortedGroups } from '../docs/prototypes/us-budget/mts-feed.mjs';
const feed = JSON.parse(readFileSync(new URL('../docs/prototypes/us-budget/mts-live.json', import.meta.url)));

test('live source feed matches its 36-month actual and financing contract', () => {
  assert.equal(validateFeed(feed), feed);
  assert.equal(feed.coverage.start, feed.monthly[0].month);
  assert.equal(feed.coverage.end, feed.monthly.at(-1).month);
  for (const s of feed.sources) assert.match(s.response_sha256, /^[a-f0-9]{64}$/);
});

test('browser rejects duplicates, missing figures, wrong totals and untrusted source URLs', () => {
  for (const mutate of [
    f => { f.monthly[1].month = f.monthly[0].month; },
    f => { f.monthly[0].receipts = null; },
    f => { f.fiscal_ytd.receipts += 1e9; },
    f => { f.sources[0].url = 'https://example.com/untrusted'; },
    f => { f.monthly[0].status = 'estimate'; },
    f => { f.fiscal_ytd.finance.other += 100; }
  ]) {
    const bad = structuredClone(feed); mutate(bad);
    assert.throws(() => validateFeed(bad));
  }
});

test('amount, growth and change rankings keep unknown figures last', () => {
  const rows = [{name:'A',value:100,prior:90}, {name:'B',value:50,prior:10},
    {name:'C',value:-10,prior:20}, {name:'D',value:null,prior:30}];
  assert.deepEqual(sortedGroups(rows,'value').map(r => r.name), ['A','B','C','D']);
  assert.deepEqual(sortedGroups(rows,'rate').map(r => r.name), ['B','A','C','D']);
  assert.deepEqual(sortedGroups(rows,'delta').map(r => r.name), ['B','A','C','D']);
  assert.equal(rows[0].name,'A', 'sorting does not mutate source data');
});
