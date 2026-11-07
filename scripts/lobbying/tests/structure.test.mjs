import test from 'node:test';
import assert from 'node:assert/strict';
import { passages, validateExtraction, ldaUnits, sourceVersion } from '../structure.mjs';

test('long pages keep all source characters and page/offset locators', () => {
  const text = 'a'.repeat(9300);
  const pieces = passages({source: 'fara', pages: [{page: 7, text}]});
  assert.equal(pieces.map(p => p.content).join(''), text);
  assert.deepEqual(pieces.map(p => p.locator.start), [0, 4000, 8000]);
  assert.ok(pieces.every(p => p.locator.page === 7));
});

const passage = {content: 'On March 1, 2025 we emailed Senator Smith about steel tariffs.', locator: {page: 4}};
const unit = () => ({grain: 'contact', date: '2025-03-01', summary_ko: '철강 관세에 관한 이메일', issue: 'steel tariffs', method: 'email',
  quote: passage.content, principal: null, recipients: [{name: 'Smith', quote: 'Senator Smith', kind: 'individual', branch: 'legislative',
    country: null, organization: null, department: null, role: 'Senator'}]});

test('unsupported contacts, affiliations and dates are held', () => {
  const good = validateExtraction({units: [unit()]}, passage);
  assert.equal(good[0].principal, null);
  assert.equal(good[0].review_status, 'machine_extracted');
  const fake = unit(); fake.recipients[0].name = 'Jones';
  assert.throws(() => validateExtraction({units: [fake]}, passage), /anchored/);
  const affiliation = unit(); affiliation.recipients[0].department = 'Commerce';
  assert.throws(() => validateExtraction({units: [affiliation]}, passage), /affiliation/);
  assert.throws(() => validateExtraction({units: [{...unit(), date: '2025-02-31'}]}, passage), /date/);
  assert.throws(() => validateExtraction({units: [{...unit(), recipients: []}]}, passage), /recipient/);
});

test('LDA institutions remain one issue group with no inferred date or meetings', () => {
  const record = {source: 'lda', client_name: 'Example', country_codes: ['KR'], raw_payload: {
    lobbying_activities: [{description: 'General trade policy', government_entities: [{name: 'SENATE'}, {name: 'Commerce, Dept of'}]}],
  }};
  const [piece] = passages(record);
  const units = ldaUnits(record, piece);
  assert.equal(units.length, 1);
  assert.equal(units[0].recipients.length, 2);
  assert.equal(units[0].grain, 'filing_issue_block');
  assert.equal(units[0].date, null);
  assert.equal(units[0].principal.kind, 'unknown');
  assert.equal(units[0].recipients[1].branch, 'executive');
  assert.equal(units[0].recipients[1].department, 'Commerce, Dept of');
});

test('metadata and text revisions independently invalidate derived evidence', () => {
  assert.notEqual(sourceVersion({payload_hash: 'a', body_sha256: 'b'}), sourceVersion({payload_hash: 'a', body_sha256: 'c'}));
  assert.notEqual(sourceVersion({payload_hash: 'a', body_sha256: 'b'}), sourceVersion({payload_hash: 'c', body_sha256: 'b'}));
});
