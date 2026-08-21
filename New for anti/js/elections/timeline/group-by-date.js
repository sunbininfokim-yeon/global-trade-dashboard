import { eventsByDate } from '../data/selectors.js';
import { escapeHtml, formatDate, stateLabel } from '../ui.js';

export const renderDateGroups = (events, countries) => eventsByDate(events).map(([date, rows]) => `
    <section class="elections-day-group">
        <div class="elections-day-label">${escapeHtml(formatDate(date))}</div>
        ${rows.map((event) => {
            const country = countries.get(event.iso3);
            return `<article class="elections-event">
                <div class="elections-event-country">${escapeHtml(country?.name_ko || event.iso3 || '국가 미상')}</div>
                <div class="elections-event-title">${escapeHtml(event.label_ko || event.label_en || '선거 일정')}</div>
                <div class="elections-event-meta">${escapeHtml(event.type || '일정')} · ${escapeHtml(stateLabel(event.status))}</div>
            </article>`;
        }).join('')}
    </section>`).join('');
