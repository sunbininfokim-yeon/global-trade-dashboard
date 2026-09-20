'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const p = require('../../New for anti/policy-evidence.js');
const fixture = require('../fixtures/clarity-119-hr-3633.json');
const sync = require('../sync-congress.js');
const action = (text, source, date = '2026-01-01') => ({ text, sourceSystem: { name: source }, actionDate: date });
const bill = (actions, type = 'hr') => ({ bill_type: type, bill_actions: actions });
test('exact citations accept spaces/dots/case and explicit Congress without fuzzy matches', () => {
  for (const q of ['HR 3633', 'Hr3633', 'H.R. 3633', 'h. r.3633']) assert.deepEqual(p.parseBillQuery(q), { type: 'hr', number: 3633, congress: null });
  assert.deepEqual(p.parseBillQuery('119-hr-3633'), { type: 'hr', number: 3633, congress: 119 });
  assert.equal(p.parseBillQuery('S. 42 (119th)').congress, 119);
  assert.equal(p.parseBillQuery('H.J.Res. 5').type, 'hjres');
  for (const q of ['CLARITY Act', '수출통제', 'HR 0', 'HR3633 or bill_number.gt.0', 'HR3633 policy']) assert.equal(p.parseBillQuery(q), null);
});
test('live DB fixture: House passage, Senate report, failed cloture; no Senate passage or enactment', () => {
  const l = p.buildLifecycle(fixture);
  assert.equal(l.origin_chamber, 'house');
  assert.equal(l.current.step_id, 'senate_reported');
  assert.equal(l.current.stage, 'second_chamber');
  assert.equal(l.steps.find(s => s.id === 'house_passage').state, 'observed');
  for (const id of ['senate_passage', 'passed_both_chambers', 'enacted']) assert.equal(l.steps.find(s => s.id === id).state, 'unconfirmed');
  assert.equal(l.procedural_alert.kind, 'cloture');
  assert.equal(l.procedural_alert.result, 'failed');
  assert.equal(l.procedural_alert.evidence.vote.yea_count, 49);
  assert.equal(l.procedural_alert.evidence.vote.nay_count, 50);
  assert.equal(l.next.id, 'senate_passage');
  assert.equal(l.steps.find(s => s.id === 'house_reported').evidence.some(e => /Rules Committee Resolution/.test(e.text)), false);
});
test('sourceSystem 0 is Senate, 1/2 House, Library of Congress not a chamber', () => {
  assert.equal(p.actionChamber({ sourceSystem: { code: 0 } }), 'senate');
  assert.equal(p.actionChamber({ sourceSystem: { code: 2 } }), 'house');
  assert.equal(p.actionChamber({ sourceSystem: { code: 9 }, text: 'The Senate amendment was discussed by the House.' }), null);
});
test('null vote result is unknown; procedural votes cannot prove passage', () => {
  assert.equal(p.voteEvidence({ question: 'On Passage', result: null }).result, 'unknown');
  const l = p.buildLifecycle({ bill_type: 'hr', bill_votes: [{ chamber: 'senate', question: 'Cloture on the motion to proceed', result: 'Invoked', vote_date: '2026-01-01' }] });
  assert.equal(l.steps.find(s => s.id === 'senate_passage').state, 'unconfirmed');
});
test('Senate-origin bills reverse chamber order; missing report is never inferred', () => {
  const l = p.buildLifecycle(bill([action('Passed Senate without amendment by Unanimous Consent.', 'Senate')], 's'));
  assert.equal(l.current.step_id, 'senate_passage');
  assert.equal(l.steps.find(s => s.id === 'senate_reported').state, 'unconfirmed');
  assert.equal(l.next.id, 'house_referred');
});
test('unknown chamber report stays unknown instead of choosing other chamber', () => {
  const l = p.buildLifecycle(bill([action('Reported by Committee.', 'Library of Congress')]));
  assert.equal(l.current.step_id, null);
  assert.equal(l.coverage.chamber_unknown, 1);
});
test('ordered reported is committee consideration; referrals beat incidental consideration wording', () => {
  assert.equal(p.classifyAction(action('Ordered to be Reported by the Yeas and Nays: 32 - 19.', 'House committee actions')).kind, 'committee_consideration');
  assert.equal(p.classifyAction(action('Referred to the Committee on X, for consideration of provisions', 'House floor actions')).kind, 'referred');
  assert.equal(p.classifyAction(action('Rules Committee Resolution H. Res. 580 Reported to House.', 'House floor actions')).kind, 'other');
});
test('later successful passage clears an earlier procedural alert regardless of input order', () => {
  const l = p.buildLifecycle(bill([action('Passed Senate with an amendment by Yea-Nay Vote. 80 - 20.', 'Senate', '2026-02-02'), action('Cloture not invoked in Senate by Yea-Nay Vote. 49 - 50.', 'Senate', '2026-02-01')]));
  assert.equal(l.current.step_id, 'senate_passage');
  assert.equal(l.procedural_alert, null);
  assert.equal(l.steps.find(s => s.id === 'passed_both_chambers').state, 'unconfirmed');
});
test('postponed/reconsideration/amendment votes are not bill passage; zero is preserved', () => {
  assert.equal(p.voteEvidence({ question: 'POSTPONED PROCEEDINGS - On passage the ayes prevailed.' }).result, 'unknown');
  assert.equal(p.classifyAction(action('On agreeing to the amendment Agreed to by voice vote.', 'House floor actions')).kind, 'other');
  assert.equal(p.voteEvidence({ question: 'On Passage', result: 'Passed', yea_count: 100, nay_count: 0 }).nay_count, 0);
});
test('enactment is definitive; procedural defeat alone is not terminal; resolutions omit presidential rail', () => {
  assert.equal(sync.stageFromActions([action('Became Private Law No: 119-1.', 'Library of Congress')], 'hr'), 'enacted');
  assert.notEqual(sync.stageFromActions([action('Cloture rejected in Senate', 'Senate')], 'hr'), 'failed');
  assert.equal(p.buildLifecycle(bill([], 'hres')).steps.some(s => s.id === 'presented_to_president'), false);
});
test('mail snapshot is compact and retains chamber, next required data and vote provenance', () => {
  const snapshot = p.notificationSnapshot(p.buildLifecycle(fixture));
  assert.equal(snapshot.current.label, '상원 상임위 보고');
  assert.ok(snapshot.latest_event.source_url);
  assert.ok(snapshot.next.required_data.includes('vote_result'));
  assert.equal(snapshot.steps, undefined);
});

test('second chamber passage without amendment proves agreement only with originating passage evidence', () => {
  const l = p.buildLifecycle(bill([action('Passed House by voice vote.', 'House floor actions', '2026-01-01'), action('Passed Senate without amendment by Unanimous Consent.', 'Senate', '2026-02-01')]));
  assert.equal(l.current.stage, 'passed_both_chambers');
  assert.equal(l.next.id, 'presented_to_president');
});
