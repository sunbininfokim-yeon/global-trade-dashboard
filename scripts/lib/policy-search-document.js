'use strict';
const crypto = require('node:crypto');
const VERSION = 'policy-document-v1';
const MODEL = 'gemini-embedding-001';
const DIMENSIONS = 1536;
const hash = text => crypto.createHash('sha256').update(text).digest('hex');
function plain(value) {
  return String(value || '').replace(/<script\b[^>]*>[\s\S]*?<\/script>|<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]*>/g, ' ').replace(/&#x([\da-f]+);/gi, (_, n) => parseInt(n, 16) <= 0x10ffff ? String.fromCodePoint(parseInt(n, 16)) : ' ')
    .replace(/&#(\d+);/g, (_, n) => Number(n) <= 0x10ffff ? String.fromCodePoint(Number(n)) : ' ')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"').replace(/&apos;|&#39;/gi, "'")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ' ').replace(/\s+/g, ' ').trim();
}
function officialUrl(value) {
  try {
    const u = new URL(value);
    if (u.protocol !== 'https:' || u.username || u.password || u.port || !/(^|\.)(congress\.gov|govinfo\.gov|federalregister\.gov|archives\.gov|uscode\.house\.gov)$/.test(u.hostname)) return null;
    u.searchParams.delete('api_key'); u.searchParams.delete('key');
    return u.href;
  } catch { return null; }
}
function citations(text) {
  const refs = [];
  for (const m of plain(text).matchAll(/\b(?:Executive\s+Order|E\.?\s*O\.?)\s*(?:No\.?\s*)?(\d{4,5})\b/gi))
    refs.push({ target_type: 'executive_order', target_id: m[1], citation: m[0] });
  for (const m of plain(text).matchAll(/\b(?:Public\s+Law|Pub\.?\s*L\.?|P\.?\s*L\.?)\s*(?:No\.?\s*)?(\d{2,3})\s*[-–—]\s*(\d{1,4})\b/gi))
    refs.push({ target_type: 'public_law', target_id: `${m[1]}-public-${m[2]}`, citation: m[0] });
  return [...new Map(refs.map(r => [`${r.target_type}:${r.target_id}`, r])).values()];
}
function chunks(text, size = 2200, overlap = 160) {
  const result = [];
  for (let start = 0; start < text.length;) {
    let end = Math.min(start + size, text.length);
    if (end < text.length) { const gap = text.lastIndexOf(' ', end); if (gap > start + size / 2) end = gap; }
    result.push(text.slice(start, end));
    if (end === text.length) break;
    start = Math.max(start + 1, end - overlap);
  }
  return result;
}
function buildDocument({ type, id, title, date, sourceUrl, summary, summaryUrl, subjects = [], body, bodyUrl,
  bodyStatus = 'unavailable', references = [], contexts = [], sourceVersion = null, maxPassages = 24 }) {
  if (!Number.isInteger(maxPassages) || maxPassages < 12 || maxPassages > 24) throw new Error('Passage budget must be between 12 and 24');
  sourceUrl = officialUrl(sourceUrl) || officialUrl(bodyUrl);
  const parts = [];
  const add = (field, text, url, extra = {}) => {
    text = plain(text); url = officialUrl(url);
    if (text && url) parts.push({ field, text, source_url: url, ...extra });
  };
  add('title', title, sourceUrl); add('summary', summary, summaryUrl || sourceUrl);
  add('subjects', [...new Set(subjects.map(plain).filter(Boolean))].sort().join('; '), sourceUrl);
  const cleaned = plain(body), retained = cleaned.slice(0, 1000000);
  add('body', retained, bodyUrl || sourceUrl);
  const ownRefs = citations(retained).filter(r => !(r.target_type === type && r.target_id === String(id)));
  const explicitRefs = [...new Map([...references, ...ownRefs].map(r => [`${r.target_type}:${r.target_id}`, r])).values()];
  for (const c of contexts) {
    // Only explicit citations can contribute linked-document context. Never
    // infer applicability, repeal, enactment or a legal authority from similarity.
    const ref = explicitRefs.find(r => r.target_type === c.target_type && r.target_id === c.target_id);
    if (ref && officialUrl(c.citation_url)) add('cited_document', c.text, c.source_url,
      { target_type: c.target_type, target_id: c.target_id, citation: ref.citation, citation_url: officialUrl(c.citation_url) });
  }
  if (!parts.length) throw new Error('A search document requires text with an official source URL');
  const input = { version: VERSION, source_type: type, source_id: String(id), title: plain(title), document_date: date || null,
    source_url: officialUrl(sourceUrl), evidence_parts: parts, references: explicitRefs, source_version: sourceVersion,
    text_status: retained ? (cleaned.length > retained.length ? 'partial_body' : 'body') : bodyStatus,
    body_characters: cleaned.length, retained_body_characters: retained.length,
    resolved_references: parts.filter(p=>p.field==='cited_document').length, reference_count: explicitRefs.length };
  const candidates = parts.flatMap(p => chunks(p.text).map(text => ({ field: p.field, source_url: p.source_url,
    target_type: p.target_type || null, target_id: p.target_id || null, text,
    input_text: `${input.title.slice(0,500)}\nDocument type: ${type}\n${p.field === 'cited_document' ? `Explicitly cites ${p.citation}. Related document context (not this document's operative text):\n` : ''}${text}` })));
  // Reserve room for cited context even when a long source uses the chunk cap.
  const contextChunks = candidates.filter(p => p.field === 'cited_document');
  const headers = candidates.filter(p => !['body','cited_document'].includes(p.field));
  const bodyChunks = candidates.filter(p => p.field === 'body');
  const spread = (list, n) => list.length <= n ? list : Array.from({length:n},(_,i)=>list[Math.round(i*(list.length-1)/Math.max(1,n-1))]);
  // Keep the entire retained body for lexical proof. A bounded vector budget
  // samples across the body (including its tail), rather than just its prefix.
  const selectedHeaders = headers.slice(0,8), selectedContext = spread(contextChunks,Math.min(contextChunks.length,4));
  const selected = [...selectedHeaders,...spread(bodyChunks,Math.max(0,maxPassages-selectedHeaders.length-selectedContext.length)),...selectedContext];
  input.embedding_coverage = selected.length < candidates.length ? 'partial' : 'complete';
  input.available_passages = candidates.length;
  const passages = selected.map((p, index) => ({ ...p, passage_index: index, input_hash: hash(p.input_text) }));
  const inputHash = hash(JSON.stringify({ ...input, passages: passages.map(p => p.input_hash) }));
  return { ...input, document_id: `${type}:${id}`, search_text: parts.map(p => p.text).join('\n'), input_hash: inputHash, passages };
}
module.exports = { VERSION, MODEL, DIMENSIONS, hash, plain, officialUrl, citations, chunks, buildDocument };
