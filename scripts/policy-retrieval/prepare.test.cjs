const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chunks, fuse, evaluate } = require('./prepare.cjs');
const doc = text => ({ source_type: 'public_law', source_id: '118-1', version: 'enrolled', source_url: 'https://example.gov/law', text });
test('full original coverage, bounded overlapping chunks and Unicode-safe offsets', () => {
  const d = doc(('Section 1. 🚢 Export controls apply.\n\n').repeat(100));
  const a = chunks(d, { maxChars: 200, overlap: 40 });
  const chars = Array.from(d.text), covered = new Set();
  for (const r of a) {
    assert.equal(r.text, chars.slice(r.start, r.end).join(''));
    assert.ok(r.end - r.start <= 200);
    for (let i = r.start; i < r.end; i++) covered.add(i);
  }
  assert.equal(covered.size, chars.length);
  for (let i = 1; i < a.length; i++) assert.equal(a[i - 1].end - a[i].start, 40);
  assert.deepEqual(chunks(d, { maxChars: 200, overlap: 40 }), a);
  assert.notEqual(chunks({ ...d, section: 'Sec. 2' })[0].chunk_id, chunks(d)[0].chunk_id);
  assert.notEqual(chunks({ ...d, version: 'amended' })[0].chunk_id, chunks(d)[0].chunk_id);
});
test('reject unsafe or incomplete preparation inputs', () => {
  assert.throws(() => chunks(doc('')), /Missing text/);
  assert.throws(() => chunks(doc('abc'), { maxChars: 200, overlap: 190 }));
  assert.throws(() => chunks({ ...doc('abc'), version: null }));
});
test('RRF rewards two-channel agreement, deduplicates chunks, keeps exact IDs first', () => {
  const a = fuse({ lexical: ['bill:a','bill:a','bill:b'], semantic: ['bill:b','bill:c'], exact: ['bill:z'] });
  assert.deepEqual(a.map(r => r.id), ['bill:z','bill:b','bill:a','bill:c']);
  assert.equal(a.find(r => r.id === 'bill:a').rrf_score, 1/61);
  assert.throws(() => fuse({ exact: ['unscoped'] }));
});
test('Top-K comparison reports recall, never answer accuracy', () => {
  const semantic = Array.from({ length: 20 }, (_, i) => `bill:${i}`);
  const result = evaluate([{ semantic, expected: ['bill:19'] }]);
  assert.deepEqual(result.map(r => r.mean_recall), [0,0,1]);
  assert.throws(() => evaluate([{ expected: [] }]));
});
