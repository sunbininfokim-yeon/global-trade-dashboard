import { eventsByDate } from '../data/selectors.js';
import { escapeHtml, formatDate, stateLabel } from '../ui.js';

// 브리핑을 띄울 수 있는 행만 버튼이 된다. 누를 수 있게 생겼는데 아무 일도 일어나지
// 않는 줄이 제일 나쁘므로, 화면이 못 그리는 일정은 <article> 그대로 둔다.
export const renderDateGroups = (events, countries, briefFor = () => null) => eventsByDate(events).map(([date, rows]) => `
    <section class="elections-day-group">
        <div class="elections-day-label">${escapeHtml(formatDate(date))}</div>
        ${rows.map((event) => {
            const country = countries.get(event.iso3);
            const briefKey = briefFor(event);
            const inner = `<div class="elections-event-country">${escapeHtml(country?.name_ko || event.iso3 || '국가 미상')}</div>
                <div class="elections-event-title">${escapeHtml(event.label_ko || event.label_en || '선거 일정')}</div>
                <div class="elections-event-meta">${escapeHtml(event.type || '일정')} · ${escapeHtml(stateLabel(event.status))}</div>`;
            return briefKey
                ? `<button class="elections-event is-openable" type="button" data-election-brief="${escapeHtml(briefKey)}">${inner}</button>`
                : `<article class="elections-event">${inner}</article>`;
        }).join('')}
    </section>`).join('');
