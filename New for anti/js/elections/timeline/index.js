import { allDatedEvents, splitByToday, groupByMonth, EVENT_KINDS, kindOf } from '../data/selectors.js';
import { formatMonth } from '../ui.js';
import { renderDateGroups } from './group-by-date.js';

// 좌측 `세계 선거 일정`. 달을 한 칸씩 넘기는 화면이었는데, 그러면 "앞으로 무엇이
// 있는가"가 한 번에 안 보인다. 지금은 오늘 이후를 달 구분만 두고 **쭉** 늘어놓는다.
//
// 목록이 길어지는 것은 감수한다. 대신 두 가지로 줄여 준다:
//   종류 칩   대선·총선·지방·재보궐·당권 중 하나만 보기
//   지난 일정  접어서 아래에 둔다 (지우지 않는다 -- 직전 결과가 맥락이다)

let activeKind = 'all';

const filterRows = (rows) => (activeKind === 'all' ? rows : rows.filter((event) => kindOf(event) === activeKind));

const chips = (upcoming) => {
    const counts = new Map();
    upcoming.forEach((event) => {
        const key = kindOf(event);
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    const chip = (key, ko, count) => `<button class="elections-tab${activeKind === key ? ' is-active' : ''}" type="button"
        data-election-kind="${key}"${count ? '' : ' disabled'}>${ko}<span>${count}</span></button>`;
    return `<div class="elections-tab-row elections-kind-filter">
        ${chip('all', '전체', upcoming.length)}
        ${EVENT_KINDS.map((kind) => chip(kind.key, kind.ko, counts.get(kind.key) || 0)).join('')}
        ${counts.get('other') ? chip('other', '기타', counts.get('other')) : ''}
    </div>`;
};

const monthBlocks = (rows, countries, briefFor, today) => groupByMonth(rows).map(([month, monthRows]) => `
    <section class="elections-month-block">
        <h3 class="elections-month-head">${formatMonth(month)}<span>${monthRows.length}건</span></h3>
        ${renderDateGroups(monthRows, countries, briefFor, { today })}
    </section>`).join('');

export const renderTimeline = (root, { calendar, countries, briefFor, onBriefOpen, today = new Date().toISOString().slice(0, 10) }) => {
    const { upcoming, past } = splitByToday(allDatedEvents(calendar), today);
    root.className = 'panel-section elections-timeline';

    const paint = () => {
        const rows = filterRows(upcoming);
        root.innerHTML = `
            <div class="panel-header">
                <h2>세계 선거 일정</h2>
                <p>오늘 이후 ${upcoming.length}건 — 대통령·의회·지방·재보궐·당권</p>
            </div>
            ${chips(upcoming)}
            <div class="elections-date-list">
                ${rows.length ? monthBlocks(rows, countries, briefFor, today)
                : '<p class="elections-muted">이 종류로 다가오는 확정 일정이 없습니다. 수집되지 않았다는 뜻일 수도 있습니다.</p>'}
            </div>
            ${past.length ? `<details class="elections-timeline-past">
                <summary>지난 일정 ${past.length}건</summary>
                <div class="elections-date-list">${monthBlocks(filterRows(past), countries, briefFor, today)}</div>
            </details>` : ''}
            <p class="elections-panel-note">국가를 선택하면 이 전 세계 일정은 닫히고 해당 국가 상세로 전환됩니다.</p>
        `;
        bind();
    };

    // 목록은 수십 줄이라 줄마다 리스너를 달지 않고 한 번만 위임한다.
    const bind = () => {
        root.querySelectorAll('[data-election-kind]').forEach((button) => button.addEventListener('click', () => {
            activeKind = button.dataset.electionKind;
            paint();
        }));
        // 브리핑은 일정 행 자체를 읽는다(날짜·개선 규모 등). 키만 넘기면 창이 그 맥락을
        // 잃으므로 눌린 행의 일정도 같이 넘긴다.
        root.querySelectorAll('[data-election-brief]').forEach((button) => button.addEventListener('click', () => {
            const event = [...upcoming, ...past].find((row) => `${row.iso3}:${row.date}` === button.dataset.electionEvent) || null;
            onBriefOpen?.(button.dataset.electionBrief, event);
        }));
    };

    paint();
};
