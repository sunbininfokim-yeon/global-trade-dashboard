'use strict';
// Offline preparation/evaluation only. No API calls or writes to production.
const { createHash } = require('node:crypto');
const hash = value => createHash('sha256').update(value).digest('hex');

function chunks(document, { maxChars = 2400, overlap = 360 } = {}) {
  if (!Number.isInteger(maxChars) || !Number.isInteger(overlap) || maxChars < 100 || overlap < 0 || overlap >= maxChars / 2) throw new Error('Invalid chunk bounds');
  for (const key of ['source_type', 'source_id', 'version', 'source_url', 'text']) {
    if (typeof document[key] !== 'string' || !document[key].trim()) throw new Error(`Missing ${key}`);
  }
  if (!['bill', 'public_law', 'executive_order', 'regulation'].includes(document.source_type)) throw new Error('Unknown source_type');
  if (!/^https:\/\//.test(document.source_url)) throw new Error('HTTPS source_url required');
  // Offsets are Unicode code points; original input is never normalized/truncated.
  const chars = Array.from(document.text);
  const contentHash = hash(document.text);
  const out = [];
  for (let start = 0; start < chars.length;) {
    let end = Math.min(start + maxChars, chars.length);
    if (end < chars.length) {
      // Prefer a paragraph/sentence boundary in the final quarter of the window.
      const floor = start + Math.ceil(maxChars * 0.75);
      for (let i = end; i >= floor; i--) {
        if (chars[i - 1] === '\n' || (/[.!?]/.test(chars[i - 1]) && /\s/.test(chars[i] || ''))) { end = i; break; }
      }
    }
    const text = chars.slice(start, end).join('');
    if (text.trim()) out.push({
      source_type: document.source_type, source_id: document.source_id,
      version: document.version, source_url: document.source_url,
      title: document.title || '', section: document.section || null,
      content_hash: contentHash, start, end, text,
      chunk_id: hash(JSON.stringify([document.source_type, document.source_id, document.version, document.section || null, contentHash, start, end])),
    });
    if (end === chars.length) break;
    start = end - overlap;
  }
  return out;
}

// IDs must be namespaced (e.g. bill:119-hr-3633) and each list already ranked.
// Duplicate chunks of one document must not multiply its votes in one channel.
function fuse({ lexical = [], semantic = [], exact = [] }, { limit = 20, k = 60 } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || !Number.isFinite(k) || k <= 0) throw new Error('Invalid ranking bounds');
  for (const list of [lexical, semantic, exact]) {
    if (!Array.isArray(list) || list.some(id => typeof id !== 'string' || !id.includes(':'))) throw new Error('Namespaced document IDs required');
  }
  const scores = new Map();
  for (const list of [lexical, semantic]) {
    [...new Set(list)].forEach((id, rank) => scores.set(id, (scores.get(id) || 0) + 1 / (k + rank + 1)));
  }
  const exactIds = [...new Set(exact)];
  return [...exactIds, ...[...scores.keys()].filter(id => !exactIds.includes(id)).sort((a, b) => scores.get(b) - scores.get(a) || a.localeCompare(b))]
    .slice(0, limit).map(id => ({ id, rrf_score: scores.get(id) || 0, exact: exactIds.includes(id) }));
}

function evaluate(cases) {
  if (!Array.isArray(cases) || !cases.length) throw new Error('Nonempty labeled cases required');
  return [5, 10, 20].map(limit => {
    const recalls = cases.map(c => {
      if (!Array.isArray(c.expected) || !c.expected.length) throw new Error('Expected relevance labels required');
      const expected = new Set(c.expected);
      const found = new Set(fuse(c, { limit }).map(r => r.id));
      return [...expected].filter(id => found.has(id)).length / expected.size;
    });
    return { top_k: limit, cases: cases.length, mean_recall: recalls.reduce((a, b) => a + b, 0) / cases.length };
  });
}
module.exports = { chunks, fuse, evaluate };
if (require.main === module) {
  const fs = require('node:fs');
  const [mode, input] = process.argv.slice(2);
  if (!['chunks', 'evaluate'].includes(mode) || !input) throw new Error('Usage: node prepare.cjs chunks|evaluate input.json');
  const data = JSON.parse(fs.readFileSync(input, 'utf8'));
  if (mode === 'evaluate') console.log(JSON.stringify(evaluate(data), null, 2));
  else {
    const prepared = data.flatMap(doc => chunks(doc));
    console.log(JSON.stringify({ mode: 'offline_only', documents: data.length, chunks: prepared.length,
      raw_vector_bytes_float32_1536: prepared.length * 1536 * 4,
      note: 'Excludes text, indexes, row overhead and API cost. Token counts must be checked before embedding.', items: prepared }, null, 2));
  }
}
