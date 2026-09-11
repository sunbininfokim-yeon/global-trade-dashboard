'use strict';

const assert = require('node:assert/strict');
const { parseCommitteeAgencyJurisdictions } = require('./committee-agency-jurisdiction-source');

const parsed = parseCommitteeAgencyJurisdictions({
  congress_number: 119,
  source_name: 'house-rule-x-senate-rule-xxv',
  coverage: { complete: false },
  records: [{
    committee_id: '119-house-hsag00',
    agency_id: 'fr-agriculture-department',
    relationship_type: 'oversight',
    mapping_source: 'official',
    source_url: 'https://www.govinfo.gov/content/pkg/HMAN-118/html/HMAN-118-pg459.htm',
  }],
});
assert.equal(parsed.rows[0].agency_id, 'fr-agriculture-department');
assert.equal(parsed.coverage.complete, false);
assert.throws(() => parseCommitteeAgencyJurisdictions({
  congress_number: 119,
  source_name: 'x',
  records: [{
    committee_id: '119-house-hsag00',
    agency_id: 'fr-agriculture-department',
    relationship_type: 'oversight',
    mapping_source: 'official',
    source_url: 'https://example.org/not-official',
  }],
}), /no valid official records/);

console.log('Committee agency jurisdiction parser tests passed');
