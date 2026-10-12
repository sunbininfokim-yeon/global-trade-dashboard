const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const statuses = { needs_review: '검토 대기', changed_needs_review: '원문·메타정보 변경 · 재검토', missing_from_search_needs_review: '검색에서 누락 · 재확인', catalogued_not_reconciled: '기존 수록 · 적용 조건 별도 확인' };
const localTime = value => value && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) + ' 한국시간' : '미확인';
export function noticeReviewMarkup(snapshot, caseId) {
  const c = snapshot.cases?.[caseId];
  if (!c) return '<p class="ts-help">이 품목의 공고 발견 목록은 아직 없습니다. 공고가 없거나 반덤핑 대상이 아니라는 뜻이 아닙니다.</p>';
  const notices = c.notices || [], pending = notices.filter(n => n.review_status !== 'catalogued_not_reconciled').length;
  const row = n => {
    const valid = /^\d{4}-\d{5}$/.test(n.document_id) && /^\d{4}-\d{2}-\d{2}$/.test(n.published);
    const href = valid ? `https://www.govinfo.gov/content/pkg/FR-${n.published}/html/${n.document_id}.htm` : null;
    return `<li><span>${esc(n.published)} · ${esc(statuses[n.review_status] || '검토 필요')}</span><b>${esc(n.title)}</b>${href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">공식 원문 ${esc(n.document_id)}</a>` : '<small>원문 식별자 미확인</small>'}</li>`;
  };
  return `<details class="ts-ad-notices" data-ad-notices><summary>새 공고 확인 · ${esc(caseId)} · 검토 대기 ${pending}건</summary>
    <p>조회 범위 ${esc(snapshot.from)} ~ ${esc(c.searched_through || '완료된 조회 없음')} · 마지막 성공 ${esc(localTime(c.last_success_at))}<br>원문 조회 목록입니다. 최종 공고를 발견해도 세율·발효일·기업·POR를 검증하기 전에는 계산과 단계 표시에 반영하지 않습니다.</p>
    ${c.status !== 'complete' ? '<p class="ts-unverified">최근 조회가 완료되지 않아 이전 성공 자료를 보존했습니다. 빈 목록도 공고 0건으로 확정하지 않습니다.</p>' : ''}
    ${notices.length ? `<ol class="ts-ad-notice-list">${notices.slice(0, 5).map(row).join('')}</ol>${notices.length > 5 ? `<details><summary>이전 공고 ${notices.length - 5}건 더 보기</summary><ol class="ts-ad-notice-list" start="6">${notices.slice(5).map(row).join('')}</ol></details>` : ''}` : '<p>조회된 후보가 없습니다. 전체 기간·법원·CBP 자료까지 확인한 결과는 아닙니다.</p>'}
    <p class="ts-help">기존 수록 공고도 이번 원문과 세율 데이터의 일치 검증이 자동으로 끝난 것은 아닙니다. 재심 개시·신청 기회 공고는 세율 변경이 아닙니다. 이 목록에는 세율 계산값이 없으며 자동 발송도 연결하지 않았습니다.</p></details>`;
}
