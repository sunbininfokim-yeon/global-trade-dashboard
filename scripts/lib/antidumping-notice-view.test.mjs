import test from 'node:test';
import assert from 'node:assert/strict';
import { noticeReviewMarkup } from '../../New for anti/policy-simulator/antidumping-notice-view.mjs';
const id = 'A-580-897';
const n = { document_id: '2026-08489', published: '2026-05-01', title: 'Final Results', review_status: 'needs_review' };
const snapshot = { from: '2026-01-01', cases: { [id]: { notices: [n], status: 'complete', searched_through: '2026-10-12', last_success_at: '2026-10-12T00:00:00Z' } } };
test('review UI separates discovery, existing catalog status and actual rate activation', () => {
  const html = noticeReviewMarkup(snapshot, id);
  assert.match(html, /검토 대기 1건/); assert.match(html, /검증하기 전에는 계산과 단계 표시에 반영하지 않습니다/);
  assert.match(html, /재심 개시·신청 기회 공고는 세율 변경이 아닙니다/);
  assert.ok(!html.includes('검증 완료'));
});
test('case switch never leaks previous case candidates; failures preserve meaningful dates', () => {
  assert.match(noticeReviewMarkup(snapshot, 'A-580-914'), /목록은 아직 없습니다/);
  assert.ok(!noticeReviewMarkup(snapshot, 'A-580-914').includes(n.document_id));
  const bad = structuredClone(snapshot); bad.cases[id].status = 'failed_preserved';
  assert.match(noticeReviewMarkup(bad, id), /이전 성공 자료를 보존/); assert.match(noticeReviewMarkup(bad, id), /2026-10-12/);
});
test('untrusted titles and URLs cannot inject markup or outbound credential links', () => {
  const malicious = structuredClone(snapshot); malicious.cases[id].notices = [{ ...n, title: '<img onerror=alert(1)>', url: 'javascript:alert(1)' }];
  const html = noticeReviewMarkup(malicious, id); assert.ok(!html.includes('<img')); assert.ok(!html.includes('javascript:'));
  assert.match(html, /&lt;img/); assert.match(html, /https:\/\/www.govinfo.gov\/content\/pkg\/FR-2026-05-01\/html\/2026-08489.htm/);
});
