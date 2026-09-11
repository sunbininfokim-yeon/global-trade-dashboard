export const escapeHtml = (value) => String(value ?? '불명')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

export const formatMonth = (month) => {
    const [year, value] = String(month || '').split('-');
    return year && value ? `${year}년 ${Number(value)}월` : '일정 없음';
};

export const formatDate = (date) => {
    if (!date || date === '불명') return '날짜 불명';
    if (/^\d{4}-\d{2}$/.test(date)) return `${Number(date.slice(5))}월 (일자 미정)`;
    if (/^\d{4}-\d{2}-\d{2}$/.test(date)) return `${Number(date.slice(5, 7))}월 ${Number(date.slice(8))}일`;
    return date;
};

// bioguide.congress.gov's Biographical Directory keys every current and
// former member of Congress by their bioguideId alone -- no name-slug to get
// wrong, no per-person URL to source. Every member/committee row the board
// already publishes carries this id, so this is the one "link a person to
// their official page" case that needs nothing from Cursor: confirmed live
// 2026-09-11 against two real members (Lindsey Graham -> G000359, Mike
// Johnson -> J000299) before wiring it in.
export const bioguideUrl = (bioguideId) => `https://bioguide.congress.gov/search/bio/${String(bioguideId).toLowerCase()}`;

// Wraps an already-escaped name in a link to that person's bioguide page when
// an id is available, otherwise returns the escaped name plain. Callers pass
// the label already through escapeHtml() themselves so this stays a pure
// wrapper, not a second place deciding how a name gets escaped.
export const personLinkHtml = (escapedLabel, bioguideId) => bioguideId
    ? `<a class="elections-person-link" href="${bioguideUrl(bioguideId)}" target="_blank" rel="noopener noreferrer">${escapedLabel}</a>`
    : escapedLabel;

export const stateLabel = (status) => ({
    ready: '표시 가능',
    partial: '일부 표시',
    disabled: '데이터 수집 예정',
    scheduled: '예정',
    tentative: '잠정',
    completed: '완료',
}[status] || status || '상태 불명');
