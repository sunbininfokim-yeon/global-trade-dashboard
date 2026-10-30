import { eventsByDate, daysUntil, kindOf, kindKo, countryKo } from '../data/selectors.js';
import { escapeHtml, formatDate, stateLabel } from '../ui.js';

// 남은 날. 오늘이면 "오늘", 지난 일정은 배지를 달지 않는다 -- "D+120" 은 읽는 사람에게
// 아무 정보가 아니다.
const ddayBadge = (date, today) => {
    const days = daysUntil(date, today);
    if (days === null || days < 0) return '';
    const text = days === 0 ? '오늘' : `D-${days}`;
    return `<span class="elections-event-dday${days <= 7 ? ' is-near' : ''}">${escapeHtml(text)}</span>`;
};

// 브리핑을 띄울 수 있는 행만 버튼이 된다. 누를 수 있게 생겼는데 아무 일도 일어나지
// 않는 줄이 제일 나쁘므로, 화면이 못 그리는 일정은 <article> 그대로 둔다.
export const renderDateGroups = (events, countries, briefFor = () => null, { today } = {}) => eventsByDate(events).map(([date, rows]) => `
    <section class="elections-day-group">
        <div class="elections-day-label">${escapeHtml(formatDate(date))}${ddayBadge(date, today)}</div>
        ${rows.map((event) => {
            const briefKey = briefFor(event);
            // 종류는 칩으로 이미 말했으므로 영문 type 을 되풀이하지 않는다. 상태도
            // 모르면 줄을 만들지 않는다 -- "상태 불명"이 줄마다 붙으면 읽을 것이 준다.
            const inner = `<div class="elections-event-country">${escapeHtml(countryKo(event.iso3, countries))}
                    <span class="elections-event-kind">${escapeHtml(kindKo(kindOf(event)))}</span></div>
                <div class="elections-event-title">${escapeHtml(event.label_ko || event.label_en || '선거 일정')}</div>
                ${event.contested_ko ? `<div class="elections-event-contested">${escapeHtml(event.contested_ko)}</div>` : ''}
                ${event.status ? `<div class="elections-event-meta">${escapeHtml(stateLabel(event.status))}</div>` : ''}`;
            return briefKey
                ? `<button class="elections-event is-openable" type="button" data-election-brief="${escapeHtml(briefKey)}" data-election-event="${escapeHtml(`${event.iso3}:${event.date}`)}">${inner}</button>`
                : `<article class="elections-event">${inner}</article>`;
        }).join('')}
    </section>`).join('');
