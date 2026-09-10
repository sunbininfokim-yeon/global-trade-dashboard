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

const { mapHouseClerkCode } = require('./committee-membership-roster');
const parentMap = { AG00: ['house', 'hsag00'], IG00: ['house', 'hlig00'] };
const allowed = new Set(['hsag00', 'hsag03', 'hlig00', 'hlig01']);
assert.deepEqual(mapHouseClerkCode('AG00', parentMap, allowed), ['house', 'hsag00']);
assert.deepEqual(mapHouseClerkCode('AG03', parentMap, allowed), ['house', 'hsag03']);
assert.deepEqual(mapHouseClerkCode('IG01', parentMap, allowed), ['house', 'hlig01']);
assert.equal(mapHouseClerkCode('QJ00', parentMap, allowed), null);
assert.equal(mapHouseClerkCode('AG99', parentMap, allowed), null);

console.log('Committee membership roster cache parser tests passed');
