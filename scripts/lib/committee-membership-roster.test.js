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

console.log('Committee membership roster cache parser tests passed');
