'use strict';

// A Public Law citation can identify one enacted bill through public_laws.bill_id.
// Do not apply this to U.S.C. or Statutes at Large citations: neither has a
// one-to-one bill mapping.
const { supabaseGet, supabasePatch } = require('./sync-utils');

const PUBLIC_LAW_CITATION = /\b(?:pub(?:lic)?\.?\s*l(?:aw)?\.?|public\s+law)(?:\s*(?:no\.?|number))?\s*[:#]?\s*(\d{1,3})\s*[-–—]\s*(\d{1,5})\b/gi;

function publicLawReference(citation) {
  const matches = [...String(citation || '').matchAll(PUBLIC_LAW_CITATION)];
  if (matches.length !== 1) return null;
  const congressNumber = Number(matches[0][1]);
  const lawNumber = Number(matches[0][2]);
  if (!Number.isInteger(congressNumber) || congressNumber < 1 || congressNumber > 999
    || !Number.isInteger(lawNumber) || lawNumber < 1 || lawNumber > 99_999) return null;
  return {
    congressNumber,
    lawNumber,
    publicLawId: `${congressNumber}-public-${lawNumber}`,
  };
}

async function publicLawBillLink(citation, cache = new Map()) {
  const reference = publicLawReference(citation);
  if (!reference) return { status: 'citation_unparseable', reference: null, billId: null };
  if (!cache.has(reference.publicLawId)) {
    cache.set(reference.publicLawId, supabaseGet('public_laws', {
      select: 'public_law_id,bill_id', public_law_id: `eq.${reference.publicLawId}`, limit: '1',
    }).then((rows) => rows?.[0] || null));
  }
  const law = await cache.get(reference.publicLawId);
  if (!law) return { status: 'public_law_not_indexed', reference, billId: null };
  if (!law.bill_id) return { status: 'bill_not_indexed', reference, billId: null };
  return { status: 'linked', reference, billId: law.bill_id };
}

async function loadPublicLawAuthorities() {
  const rows = [];
  let afterId = 0;
  const pageSize = 500;
  while (true) {
    const page = await supabaseGet('legal_authorities', {
      select: 'legal_authority_id,citation,linked_bill_id', authority_type: 'eq.public_law',
      legal_authority_id: `gt.${afterId}`, order: 'legal_authority_id.asc', limit: String(pageSize),
    });
    if (!page?.length) break;
    rows.push(...page);
    afterId = Number(page.at(-1).legal_authority_id);
    if (page.length < pageSize) break;
  }
  return rows;
}

async function reconcilePublicLawAuthorityLinks() {
  const cache = new Map();
  const stats = {
    total: 0,
    linked: 0,
    updated: 0,
    citation_unparseable: 0,
    public_law_not_indexed: 0,
    bill_not_indexed: 0,
  };
  for (const authority of await loadPublicLawAuthorities()) {
    stats.total += 1;
    const link = await publicLawBillLink(authority.citation, cache);
    if (link.status !== 'linked') {
      stats[link.status] += 1;
      continue;
    }
    stats.linked += 1;
    if (authority.linked_bill_id !== link.billId) {
      await supabasePatch('legal_authorities', `legal_authority_id=eq.${authority.legal_authority_id}`, { linked_bill_id: link.billId });
      stats.updated += 1;
    }
  }
  return stats;
}

module.exports = { publicLawReference, publicLawBillLink, reconcilePublicLawAuthorityLinks };
