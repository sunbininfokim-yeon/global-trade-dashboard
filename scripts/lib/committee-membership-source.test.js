'use strict';

const assert = require('node:assert/strict');
const { officialSourceUrl, parseCommitteeMembershipSource } = require('./committee-membership-source');

assert.equal(officialSourceUrl('https://energycommerce.house.gov/subcommittees'), 'https://energycommerce.house.gov/subcommittees');
assert.equal(officialSourceUrl('https://example.org/committee'), null);

const parsed = parseCommitteeMembershipSource({
  congress_number: 119,
  source_name: 'cursor-verified-official-roster',
  coverage: { complete: false, roles: ['chair'] },
  records: [{
    committee_id: '119-house-if00', bioguide_id: 'A000001', role: 'chair',
    source_url: 'https://agriculture.house.gov/about/committee-members.htm',
  }],
});
assert.equal(parsed.rows[0].bioguide_id, 'A000001');
assert.throws(() => parseCommitteeMembershipSource({
  congress_number: 119, source_name: 'bad', coverage: { complete: false, roles: ['chair'] },
  records: [{ committee_id: '119-house-if00', bioguide_id: 'A000001', role: 'chair', source_url: 'https://example.org' }],
}), /no valid official records/);

console.log('Committee membership source parser tests passed');
