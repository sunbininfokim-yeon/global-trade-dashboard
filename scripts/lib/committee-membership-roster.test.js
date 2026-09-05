'use strict';

const assert = require('node:assert/strict');
const { parseSenateCvcXml } = require('./committee-membership-roster');

const parsed = parseSenateCvcXml(`<senators>
<lastUpdate><date>Wednesday, August 12, 2026</date></lastUpdate>
<senator lis_member_id="S000">
<bioguideId>A000382</bioguideId>
<committees>
<committee code="SSAP00" position="Chairman">Committee on Appropriations</committee>
<committee code="SSAF00">Committee on Agriculture, Nutrition, and Forestry</committee>
</committees>
</senator>
</senators>`);
assert.equal(parsed.lastUpdate, 'Wednesday, August 12, 2026');
assert.equal(parsed.senatorCount, 1);
assert.equal(parsed.rows[0].bioguide_id, 'A000382');
assert.equal(parsed.rows[0].committee_code, 'SSAP00');
assert.equal(parsed.rows[0].position, 'Chairman');
assert.equal(parsed.rows[1].position, 'Member');
assert.throws(() => parseSenateCvcXml('<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD></HTML>'), /Senate CVC XML/);

const { shouldRefreshCommitteeRoster, ROSTER_REFRESH_MONTHS } = require('./committee-membership-roster');
assert.deepEqual(ROSTER_REFRESH_MONTHS, [1, 2, 3, 4, 7, 10]);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-01-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-02-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-03-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-04-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-05-01T03:31:00Z')), false);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-07-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-08-01T03:31:00Z')), false);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-10-01T03:31:00Z')), true);
assert.equal(shouldRefreshCommitteeRoster(new Date('2026-11-01T03:31:00Z')), false);

console.log('Committee membership roster cache parser tests passed');
