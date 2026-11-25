'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { assessFreshness, run } = require('../check-policy-search-freshness');

const now = Date.parse('2026-11-24T14:00:00Z');
const oldVector = '2026-11-23T12:00:00Z';

test('pending search jobs alert after eight hours without a document refresh', () => {
  const queue = { pending: 25, failed: 0, last_refreshed_at: '2026-11-24T06:00:00Z' };
  assert.equal(assessFreshness(queue, oldVector, now, 8).status, 'stalled');
  assert.equal(assessFreshness({ ...queue, last_refreshed_at: null }, null, now, 8).status, 'stalled');
});

test('recent document refresh is progress even when existing vectors were reused', () => {
  const queue = { pending: 25, failed: 0, last_refreshed_at: '2026-11-24T13:00:00Z' };
  const result = assessFreshness(queue, oldVector, now, 8);
  assert.equal(result.status, 'progressing');
  assert.equal(result.last_vector_at, oldVector);
});

test('an empty queue and a failed-only queue have separate states', () => {
  assert.equal(assessFreshness({ pending: 0, failed: 0 }, null, now, 8).status, 'idle');
  assert.equal(assessFreshness({ pending: 0, failed: 3 }, null, now, 8).status, 'failed_only');
  assert.throws(() => assessFreshness({ pending: null, failed: 0 }, null, now, 8), /invalid_queue_counts/);
  assert.throws(() => assessFreshness({ pending: 0, failed: 0, last_refreshed_at: 'bad' }, null, now, 8), /invalid_index_timestamp/);
});

test('monitor reads the queue and only the newest stored vector timestamp', async () => {
  const result = await run({
    rpc: async (name, params) => {
      assert.equal(name, 'policy_search_status');
      assert.deepEqual(params, {});
      return { pending: 0, failed: 0 };
    },
    get: async (table, query) => {
      assert.equal(table, 'policy_search_passages');
      assert.equal(query.embedding, 'not.is.null');
      assert.equal(query.select, 'embedded_at');
      assert.equal(query.limit, '1');
      return [{ embedded_at: oldVector }];
    },
  });
  assert.equal(result.status, 'idle');
  assert.equal(result.last_vector_at, oldVector);
});
