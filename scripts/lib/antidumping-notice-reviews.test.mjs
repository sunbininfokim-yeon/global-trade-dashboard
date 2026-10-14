import test from 'node:test';
import assert from 'node:assert/strict';
import { AD_DISCOVERY } from '../../New for anti/policy-simulator/antidumping-discovery-snapshot.mjs';
import { AD_NOTICE_REVIEWS, resolveNoticeReview } from '../../New for anti/policy-simulator/antidumping-notice-reviews.mjs';
import { noticeReviewMarkup } from '../../New for anti/policy-simulator/antidumping-notice-view.mjs';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import { reviewRecords, reviewProgress } from '../../New for anti/policy-simulator/antidumping-guide.mjs';
import { lookupAD } from '../../New for anti/policy-simulator/antidumping-model.mjs';
const notice = (caseId, doc) => AD_DISCOVERY.cases[caseId].notices.find(n => n.document_id === doc);

test('all 15 pending notices have bounded reviews: 8 history, 6 informational, 1 held; existing 8 are not silently approved', () => {
  assert.equal(AD_NOTICE_REVIEWS.length, 15);
  const counts = {};
  for (const r of AD_NOTICE_REVIEWS) {
    counts[r.disposition] = (counts[r.disposition] || 0) + 1;
    assert.deepEqual(resolveNoticeReview(notice(r.case_id, r.document_id), r.case_id), r);
    assert.equal(r.rate_activation_allowed, false);
    assert.ok(r.note && r.source_anchor);
    for (const companyId of r.company_ids) {
      assert.ok(AD_CATALOG.cases.find(c => c.case_id === r.case_id).companies.some(c => c.id === companyId));
      assert.ok(r.record_ids.every(id => reviewRecords(r.case_id, companyId).some(x => x.id === id)));
    }
  }
  assert.deepEqual(counts, { informational_no_rate_change: 6, held_conflict: 1, applied_history: 8 });
  assert.equal(resolveNoticeReview(notice('A-580-897', '2026-08489'), 'A-580-897'), null);
});
test('changed body, correction metadata, publication, search omission and case mismatch all invalidate prior review', () => {
  const n = notice('A-580-908', '2026-18185');
  for (const change of [{ content_hash: 'changed' }, { metadata_hash: 'changed' }, { published: '2026-09-05' }, { review_status: 'changed_needs_review' }, { review_status: 'missing_from_search_needs_review' }, { case_id: 'A-580-867' }, { content_hash: null }]) {
    assert.equal(resolveNoticeReview({ ...n, ...change }, 'A-580-908'), null);
  }
  const r = resolveNoticeReview(n, 'A-580-908'); r.company_ids.push('fake');
  assert.ok(!resolveNoticeReview(n, 'A-580-908').company_ids.includes('fake'));
});
test('review UI keeps held sunset conflict pending, separates information and invalidates stale labels', () => {
  const html = noticeReviewMarkup(AD_DISCOVERY, 'A-580-908');
  assert.match(html, /검토 반영 6건 · 검토 대기 1건 \(보류 1건\)/);
  assert.match(html, /국가 표기 불일치/); assert.match(html, /예치율 변경 없음/);
  const changed = structuredClone(AD_DISCOVERY);
  changed.cases['A-580-897'].notices.find(n => n.document_id === '2026-13892').content_hash = 'changed';
  assert.match(noticeReviewMarkup(changed, 'A-580-897'), /검토 반영 1건 · 검토 대기 1건/);
});
test('each new latest POR begins only at sourced initiation; prior POR outcomes and deadlines cannot advance it', () => {
  for (const [caseId, companyId, id, date] of [
    ['A-580-908', 'kumho', 'tires-2025-26', '2026-09-04'],
    ['A-580-883', 'posco-pic', 'hot-rolled-2024-25', '2026-01-05'],
    ['A-580-897', 'aju', 'welded-pipe-2025-26', '2026-07-09'],
    ['A-580-914', 'lg-chem', 'sap-2024-25', '2026-02-20'],
  ]) {
    assert.equal(reviewRecords(caseId, companyId)[0].id, id);
    const p = reviewProgress(caseId, id, companyId);
    assert.equal(p.checked_on, '2026-10-12'); assert.equal(p.latest_stage, 'initiation');
    assert.equal(p.stages[0].event.date, date); assert.ok(p.stages.slice(1).every(s => s.state === 'unknown'));
    assert.equal(p.deposit, undefined); assert.equal(p.status, undefined);
  }
  assert.throws(() => reviewProgress('A-580-908', 'tires-2025-26', 'ls'));
});
test('nonselected companies never receive other respondents selection lamps in tires or transformers', () => {
  for (const [caseId, record, selected, nonselected] of [
    ['A-580-908', 'tires-2023-24', 'hankook', 'kumho'],
    ['A-580-867', 'lpt-2023-24', 'iljin', 'hyosung'],
  ]) {
    const selectedStage = reviewProgress(caseId, record, selected).stages.find(s => s.id === 'selection');
    assert.equal(selectedStage.state, 'confirmed');
    const nonselectedStage = reviewProgress(caseId, record, nonselected).stages.find(s => s.id === 'selection');
    assert.equal(nonselectedStage.state, 'unknown'); assert.equal(nonselectedStage.event, null);
  }
});
test('tires withdrawal is POR-specific rescission, never zero duty, order revocation or completed liquidation', () => {
  const p = reviewProgress('A-580-908', 'tires-2024-25-rescinded', 'hankook');
  assert.equal(p.latest_stage, 'rescinded'); assert.equal(p.status_event.date, '2026-04-29');
  assert.ok(p.stages.slice(1).every(s => s.state === 'unknown')); assert.equal(p.deposit, undefined);
  assert.equal(lookupAD({ case_id: 'A-580-908', company_id: 'hankook', entry_date: '2026-10-11' }).rate_pct, '13.03');
});
test('new preliminary margins are historical only; no reviewed opportunity, sunset or initiation becomes a deposit segment', () => {
  for (const [caseId, doc, values, beforeFinal, companyId] of [
    ['A-580-908', '2026-00190', ['9.10', '5.57', '7.34'], '2026-07-12', 'kumho'],
    ['A-580-883', '2026-00181', ['1.49', '1.22'], '2026-05-13', 'posco-pic'],
    ['A-580-914', '2026-10344', ['0.00'], '2026-09-24', 'lg-chem'],
  ]) {
    const s = AD_CATALOG.cases.find(c => c.case_id === caseId).segments.find(s => s.document_id === doc);
    assert.equal(s.stage, 'preliminary'); assert.equal(s.cash_deposit_effective, null);
    assert.deepEqual(s.rates.map(r => r.margin_pct), values); assert.ok(s.rates.every(r => r.deposit_rate_pct === null));
    assert.equal(lookupAD({ case_id: caseId, company_id: companyId, entry_date: beforeFinal }).rate_pct, null);
  }
  const segmentDocs = AD_CATALOG.cases.flatMap(c => c.segments.map(s => s.document_id));
  for (const r of AD_NOTICE_REVIEWS.filter(r => r.classification !== 'preliminary')) assert.ok(!segmentDocs.includes(r.document_id));
  assert.ok(!AD_CATALOG.documents['2026-19931']);
});
