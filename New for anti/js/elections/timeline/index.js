import { eventsForMonth, monthKeys } from '../data/selectors.js';
import { formatMonth } from '../ui.js';
import { renderDateGroups } from './group-by-date.js';

export const renderTimeline = (root, { calendar, countries, month, onMonthChange }) => {
    const months = monthKeys(calendar);
    const index = months.indexOf(month);
    const eventRows = eventsForMonth(calendar, month);
    root.className = 'panel-section elections-timeline';
    root.innerHTML = `
        <div class="panel-header">
            <h2>세계 선거 일정</h2>
            <p>날짜 순으로 정리한 대통령·의회·지방·당권·재보궐 일정</p>
        </div>
        <div class="elections-month-nav">
            <button class="elections-button" type="button" data-election-month="prev" ${index <= 0 ? 'disabled' : ''}>이전 달</button>
            <strong>${formatMonth(month)}</strong>
            <button class="elections-button" type="button" data-election-month="next" ${index < 0 || index >= months.length - 1 ? 'disabled' : ''}>다음 달</button>
        </div>
        <p class="elections-panel-note">국가를 선택하면 이 전 세계 일정은 닫히고 해당 국가 상세로 전환됩니다.</p>
        <div class="elections-date-list">${eventRows.length ? renderDateGroups(eventRows, countries) : '<p class="elections-muted">이 달에 표시할 확정 일정이 없습니다.</p>'}</div>
    `;
    root.querySelector('[data-election-month="prev"]')?.addEventListener('click', () => onMonthChange(months[index - 1]));
    root.querySelector('[data-election-month="next"]')?.addEventListener('click', () => onMonthChange(months[index + 1]));
};
