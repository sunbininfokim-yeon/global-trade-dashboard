'use strict';

const ALLOWED_ROLES = new Set(['member', 'chair', 'vice_chair', 'ranking_member', 'ex_officio']);
const OFFICIAL_HOST_PATTERN = /(^|\.)(house\.gov|senate\.gov|congress\.gov)$/i;

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

function normalizedRecord(record, congress, sourceName, sourceUpdatedAt) {
  const role = String(record?.role || 'member').trim();
  const committeeId = String(record?.committee_id || '').trim();
  const bioguideId = String(record?.bioguide_id || '').trim().toUpperCase();
  const sourceUrl = officialSourceUrl(record?.source_url);
  if (!committeeId || !bioguideId || !ALLOWED_ROLES.has(role) || !sourceUrl) return null;
  return {
    committee_id: committeeId,
    bioguide_id: bioguideId,
    role,
    congress_number: congress,
    source_url: sourceUrl,
    source_name: sourceName,
    source_updated_at: record.source_updated_at || sourceUpdatedAt || null,
    raw_source: record.raw_source || { source_url: sourceUrl, curated_record: true },
  };
}

function parseCommitteeMembershipSource(source) {
  const congress = positiveCongress(source?.congress_number);
  const sourceName = String(source?.source_name || '').trim();
  const coverage = source?.coverage || {};
  const roles = [...new Set((Array.isArray(coverage.roles) ? coverage.roles : []).map(String))];
  if (!congress) throw new Error('committee membership source must contain a positive congress_number.');
  if (!sourceName) throw new Error('committee membership source must contain source_name.');
  if (!roles.length || roles.some((role) => !ALLOWED_ROLES.has(role))) {
    throw new Error('committee membership source coverage.roles must contain valid roles.');
  }
  if (typeof coverage.complete !== 'boolean') {
    throw new Error('committee membership source coverage.complete must be true or false.');
  }
  const rows = (Array.isArray(source?.records) ? source.records : [])
    .map((record) => normalizedRecord(record, congress, sourceName, source.source_updated_at))
    .filter(Boolean);
  if (!rows.length) throw new Error('committee membership source contains no valid official records.');
  const duplicate = new Set();
  for (const row of rows) {
    const identity = `${row.committee_id}:${row.bioguide_id}:${row.role}`;
    if (duplicate.has(identity)) throw new Error(`duplicate committee membership record: ${identity}`);
    duplicate.add(identity);
  }
  if (coverage.complete) {
    const minimum = roles.includes('member') ? 250 : 20;
    if (rows.length < minimum) {
      throw new Error(`complete ${roles.includes('member') ? 'membership' : 'leadership'} snapshot needs at least ${minimum} records; received ${rows.length}.`);
    }
  }
  return { congress, sourceName, coverage: { complete: coverage.complete, roles }, rows };
}

module.exports = { ALLOWED_ROLES, officialSourceUrl, parseCommitteeMembershipSource };
