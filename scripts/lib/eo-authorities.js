'use strict';

// EO legal authority extraction is intentionally narrow. We retain exact
// citations only from the order's opening authority clause; a title keyword or
// an arbitrary later mention never becomes a legal-authority relationship.
const {
  asArray, fetchJson, firstNonEmpty, supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch,
} = require('./sync-utils');
const { publicLawBillLink } = require('./public-law-links');

const ALLOWED_TYPES = new Set([
  'constitution', 'usc', 'public_law', 'statutes_at_large', 'executive_order', 'regulation', 'other',
]);

function plainText(value) {
  return String(value || '')
    .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"')
    .replace(/&#(?:x[0-9a-f]+|\d+);/gi, ' ')
    .replace(/\s+/g, ' ').trim();
}

function authorityClause(value) {
  const source = plainText(value);
  const start = source.search(/\bby the authority vested\b/i);
  if (start < 0) return null;
  const afterStart = source.slice(start, start + 6_000);
  const end = afterStart.search(/\bit is hereby ordered\b/i);
  return end < 0 ? null : afterStart.slice(0, end);
}

function cleanCitation(value) {
  return String(value || '').replace(/\s+/g, ' ')
    .replace(/^[\s,;:(\[]+|[\s,;:.\)\]]+$/g, '').trim();
}

function addMatches(output, type, expression, clause) {
  for (const match of clause.matchAll(expression)) {
    const citation = cleanCitation(match[0]);
    if (citation) output.push({ authority_type: type, citation });
  }
}

function officialTextAuthorities(value, officialUrl) {
  const clause = authorityClause(value);
  if (!clause) return [];
  const authorities = [];
  if (/\bconstitution\b/i.test(clause)) {
    authorities.push({ authority_type: 'constitution', citation: 'Constitution of the United States' });
  }
  addMatches(authorities, 'public_law', /\b(?:public\s+law|pub\.?\s*l(?:aw)?\.?)\s*(?:no\.?\s*)?\d{1,3}\s*[-–—]\s*\d{1,5}\b/gi, clause);
  addMatches(authorities, 'usc', /\b(?:(?:section|sections)\s+[\dA-Za-z.,()\-–—\s]+?\s+of\s+)?(?:title\s+)?\d{1,2}\s*,?\s*(?:U\.?\s*S\.?\s*C\.?|United\s+States\s+Code)(?:\s*(?:§{1,2}|section|sections)?\s*[\dA-Za-z().\-–—]+(?:\s+et\s+seq\.)?)?/gi, clause);
  addMatches(authorities, 'statutes_at_large', /\b\d{1,4}\s+Stat\.\s+\d{1,5}\b/gi, clause);
  addMatches(authorities, 'executive_order', /\bExecutive Order\s+\d{3,5}\b/gi, clause);
  const seen = new Set();
  return authorities
    .map((authority) => ({ ...authority, citation: cleanCitation(authority.citation), official_url: officialUrl || null,
      extraction_method: 'official_text_citation', verification_status: 'unverified' }))
    .filter((authority) => authority.citation && !seen.has(`${authority.authority_type}:${authority.citation.toLowerCase()}`)
    && Boolean(seen.add(`${authority.authority_type}:${authority.citation.toLowerCase()}`)));
}

function structuredAuthorities(document) {
  return asArray(firstNonEmpty(document?.legal_authorities, document?.legal_authority))
    .filter((authority) => authority?.citation && ALLOWED_TYPES.has(String(authority.authority_type).toLowerCase()))
    .map((authority) => ({
      authority_type: String(authority.authority_type).toLowerCase(), citation: cleanCitation(authority.citation),
      title: authority.title || null, official_url: authority.official_url || document?.html_url || null,
      extraction_method: 'official_metadata', verification_status: 'verified',
    }));
}

async function citationAuthorities(document) {
  const officialUrl = firstNonEmpty(document?.html_url, document?.raw_text_url, document?.body_html_url);
  const rawTextUrl = firstNonEmpty(document?.raw_text_url, document?.body_html_url);
  if (!rawTextUrl) return [];
  try {
    const body = await fetchJson(rawTextUrl, {}, { label: 'Federal Register EO authority text', maxRetries: 3 });
    return officialTextAuthorities(typeof body === 'string' ? body : '', officialUrl);
  } catch (error) {
    // Authority extraction enriches the record but must not make the source
    // of record fail. The error contains no source text or credentials.
    console.warn(`EO authority text skipped: ${error.message}`);
    return [];
  }
}

async function saveEoAuthorities(eoNumber, document) {
  const publicLawCache = new Map();
  const candidates = [...structuredAuthorities(document), ...await citationAuthorities(document)];
  const deduped = new Map();
  for (const authority of candidates) {
    if (!authority.citation || !ALLOWED_TYPES.has(authority.authority_type)) continue;
    const key = `${authority.authority_type}:${authority.citation.toLowerCase()}`;
    // Structured metadata is more authoritative than the same text citation.
    if (!deduped.has(key) || authority.extraction_method === 'official_metadata') deduped.set(key, authority);
  }
  let linked = 0;
  for (const authority of deduped.values()) {
    const link = authority.authority_type === 'public_law'
      ? await publicLawBillLink(authority.citation, publicLawCache)
      : null;
    const existing = await supabaseGet('legal_authorities', {
      select: 'legal_authority_id,linked_bill_id', authority_type: `eq.${authority.authority_type}`,
      citation: `eq.${authority.citation}`, limit: '1',
    });
    let legalAuthorityId = existing?.[0]?.legal_authority_id;
    if (!legalAuthorityId) {
      const inserted = await supabaseInsert('legal_authorities', [{
        authority_type: authority.authority_type, citation: authority.citation, title: authority.title || null,
        official_url: authority.official_url || null, linked_bill_id: link?.billId || null,
        extraction_method: authority.extraction_method, verification_status: authority.verification_status,
        verified_at: authority.verification_status === 'verified' ? new Date().toISOString() : null,
      }], 'return=representation');
      legalAuthorityId = inserted?.[0]?.legal_authority_id;
    } else if (link?.billId && existing[0].linked_bill_id !== link.billId) {
      await supabasePatch('legal_authorities', `legal_authority_id=eq.${legalAuthorityId}`, { linked_bill_id: link.billId });
    }
    if (legalAuthorityId) {
      await supabaseInsertIgnore('executive_order_authorities', {
        eo_number: eoNumber, legal_authority_id: legalAuthorityId, source_url: document?.html_url || authority.official_url || null,
      }, 'eo_number,legal_authority_id');
      linked += 1;
    }
  }
  return linked;
}

module.exports = { authorityClause, officialTextAuthorities, saveEoAuthorities };
