'use strict';

const assert = require('node:assert/strict');
const { approvedOfficialTextUrl, officialTextAuthorities } = require('./eo-authorities');

assert.equal(approvedOfficialTextUrl('https://www.govinfo.gov/content/pkg/FR-2024-01-01/html/2024-00001.htm'),
  'https://www.govinfo.gov/content/pkg/FR-2024-01-01/html/2024-00001.htm');
assert.equal(approvedOfficialTextUrl('https://example.org/eo.txt'), null);

const authorities = officialTextAuthorities(
  'By the authority vested in me as President by the Constitution and the laws of the United States, including Public Law 119-45 and 19 U.S.C. 2411, it is hereby ordered as follows:',
  'https://www.federalregister.gov/documents/example',
);
assert.deepEqual(authorities.map((item) => item.authority_type), ['constitution', 'public_law', 'usc']);

console.log('EO authority parser tests passed');
