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

export const stateLabel = (status) => ({
    ready: '표시 가능',
    partial: '일부 표시',
    disabled: '데이터 수집 예정',
    scheduled: '예정',
    tentative: '잠정',
    completed: '완료',
}[status] || status || '상태 불명');
