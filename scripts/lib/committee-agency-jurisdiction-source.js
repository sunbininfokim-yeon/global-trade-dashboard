'use strict';

const ALLOWED_RELATIONSHIP = new Set(['oversight', 'authorization', 'appropriations', 'related']);
const ALLOWED_MAPPING = new Set(['official', 'verified_manual']);
const OFFICIAL_HOST_PATTERN = /(^|\.)(house\.gov|senate\.gov|congress\.gov|govinfo\.gov)$/i;

function officialSourceUrl(value) {
  try {
    const parsed = new URL(String(value || ''));
    return parsed.protocol === 'https:' && OFFICIAL_HOST_PATTERN.test(parsed.hostname) ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function positiveCongress(value) {
  const congress = Number(value);
  return Number.isInteger(congress) && congress > 0 ? congress : null;
}

function parseCommitteeAgencyJurisdictions(source) {
  const congress = positiveCongress(source?.congress_number);
  const sourceName = String(source?.source_name || '').trim();
  if (!congress) throw new Error('committee agency jurisdictions must contain a positive congress_number.');
  if (!sourceName) throw new Error('committee agency jurisdictions must contain source_name.');
  if (source?.coverage && typeof source.coverage.complete !== 'boolean') {
    throw new Error('coverage.complete must be true or false when coverage is present.');
  }
  const rows = [];
  const duplicate = new Set();
  for (const record of Array.isArray(source?.records) ? source.records : []) {
    const committeeId = String(record?.committee_id || '').trim();
    const agencyId = String(record?.agency_id || '').trim();
    const relationshipType = String(record?.relationship_type || 'oversight').trim();
    const mappingSource = String(record?.mapping_source || '').trim();
    const sourceUrl = officialSourceUrl(record?.source_url);
    if (!committeeId || !agencyId || !ALLOWED_RELATIONSHIP.has(relationshipType) || !ALLOWED_MAPPING.has(mappingSource) || !sourceUrl) {
      continue;
    }
    const identity = `${committeeId}:${agencyId}:${relationshipType}`;
    if (duplicate.has(identity)) throw new Error(`duplicate committee_agency_jurisdictions record: ${identity}`);
    duplicate.add(identity);
    rows.push({
      committee_id: committeeId,
      agency_id: agencyId,
      relationship_type: relationshipType,
      mapping_source: mappingSource,
      source_url: sourceUrl,
      verified_at: record.verified_at || source.source_updated_at || null,
    });
  }
  if (!rows.length) throw new Error('committee agency jurisdictions contains no valid official records.');
  return {
    congress,
    sourceName,
    coverage: { complete: Boolean(source?.coverage?.complete) },
    rows,
  };
}

module.exports = { officialSourceUrl, parseCommitteeAgencyJurisdictions };
