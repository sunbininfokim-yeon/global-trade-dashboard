'use strict';

const assert = require('node:assert/strict');
const { publicLawReference } = require('./public-law-links');

assert.deepEqual(publicLawReference('Pub. L. 119-45'), {
  congressNumber: 119, lawNumber: 45, publicLawId: '119-public-45',
});
assert.deepEqual(publicLawReference('Public Law No: 118–12'), {
  congressNumber: 118, lawNumber: 12, publicLawId: '118-public-12',
});
assert.equal(publicLawReference('19 U.S.C. 2411'), null);
assert.equal(publicLawReference('Pub. L. 119-1 and Pub. L. 119-2'), null);

console.log('public-law-links parser tests passed');
