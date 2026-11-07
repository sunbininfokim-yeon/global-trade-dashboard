import { allDatedEvents, splitByToday, groupByMonth, EVENT_KINDS, kindOf } from '../data/selectors.js';
import { escapeHtml, formatMonth } from '../ui.js';
import { renderDateGroups } from './group-by-date.js?v=2';

// 좌측 `세계 선거 일정`. '예정 선거'(기본)와 '끝난 선거'를 토글로 나눈다 (2026-11-07).
// 끝난 선거는 최근 것부터, 줄마다 결과 한 줄을 붙인다. 나라 화면은 세계 지도에서 연다.
// 종류 칩(대선·총선·지방·재보궐·당권)은 두 목록 모두에 쓴다.

let activeWhen = 'upcoming';
let activeKind = 'all';

const filterRows = (rows) => (activeKind === 'all' ? rows : rows.filter((event) => kindOf(event) === activeKind));

const shortcutChips = (shortcuts) => (shortcuts.length ? `<span class="elections-kind-divider" aria-hidden="true"></span>
        ${shortcuts.map(({ key, ko, title }) => `<button class="elections-tab elections-country-jump" type="button"
        data-election-jump="${key}" title="${title}">${ko}</button>`).join('')}` : '');

const chips = (rows, shortcuts) => {
    const counts = new Map();
    rows.forEach((event) => {
        const key = kindOf(event);
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    const chip = (key, ko, count) => `<button class="elections-tab${activeKind === key ? ' is-active' : ''}" type="button"
        data-election-kind="${key}"${count ? '' : ' disabled'}>${ko}<span>${count}</span></button>`;
    return `<div class="elections-tab-row elections-kind-filter">
        ${chip('all', '전체', rows.length)}
        ${EVENT_KINDS.map((kind) => chip(kind.key, kind.ko, counts.get(kind.key) || 0)).join('')}
        ${counts.get('other') ? chip('other', '기타', counts.get('other')) : ''}
        ${shortcutChips(shortcuts)}
    </div>`;
};

const toggle = (attr, items, active) => `<div class="elections-part-toggle" role="tablist">${items.map(([key, label, count]) => `
    <button class="elections-part-tab${active === key ? ' is-active' : ''}" type="button" role="tab" aria-selected="${active === key}"
        data-${attr}="${key}">${escapeHtml(label)}${count != null ? `<span>${count}</span>` : ''}</button>`).join('')}</div>`;

const monthBlocks = (rows, countries, briefFor, today, resultFor, newestFirst) => {
    const months = groupByMonth(rows);
    return (newestFirst ? [...months].reverse() : months).map(([month, monthRows]) => `
    <section class="elections-month-block">
        <h3 class="elections-month-head">${formatMonth(month)}<span>${monthRows.length}건</span></h3>
        ${renderDateGroups(monthRows, countries, briefFor, { today, resultFor, newestFirst })}
    </section>`).join('');
};

// 끝난 선거 줄에 붙일 결과 한 줄. 달력 행에는 결과가 없어서, 보드의 같은 id 행에서 읽는다.
const resultIndex = (countries) => {
    const map = new Map();
    countries.forEach((country) => (country.events || []).forEach((event) => {
        const winner = typeof event.winner === 'string' ? event.winner
            : event.winner ? [event.winner.name_ko || event.winner.name_en, event.winner.party].filter(Boolean).join(' · ') : '';
        const result = typeof event.result === 'string' ? event.result : '';
        if (winner || result) map.set(event.id, { winner, result });
    }));
    return (event) => map.get(event.id) || null;
};

export const renderTimeline = (root, { calendar, countries, briefFor, onBriefOpen, shortcuts = [], onShortcut, today = new Date().toISOString().slice(0, 10) }) => {
    const { upcoming, past } = splitByToday(allDatedEvents(calendar), today);
    const pastNewest = [...past].reverse();
    const resultFor = resultIndex(countries);
    root.className = 'panel-section elections-timeline';

    const electionsPart = () => {
        const base = activeWhen === 'past' ? pastNewest : upcoming;
        const rows = filterRows(base);
        return `
            ${toggle('election-when', [['upcoming', '예정 선거', upcoming.length], ['past', '끝난 선거', past.length]], activeWhen)}
            ${chips(base, shortcuts)}
            <div class="elections-date-list">
                ${rows.length ? monthBlocks(rows, countries, briefFor, today, resultFor, activeWhen === 'past')
                : `<p class="elections-muted">${activeWhen === 'past' ? '이 종류로 끝난 선거 기록이 없습니다.' : '이 종류로 다가오는 확정 일정이 없습니다. 수집되지 않았다는 뜻일 수도 있습니다.'}</p>`}
            </div>`;
    };

    const paint = () => {
        root.innerHTML = `
            <div class="panel-header">
                <h2>세계 선거 일정</h2>
            </div>
            ${electionsPart()}
            <p class="elections-panel-note">세계 지도에서 국가를 누르면 그 나라의 선거·행정부·의회 블록이 열립니다.</p>
        `;
        bind();
    };

    // 목록은 수십 줄이라 줄마다 리스너를 달지 않고 한 번만 위임한다.
    const bind = () => {
        root.querySelectorAll('[data-election-when]').forEach((button) => button.addEventListener('click', () => {
            activeWhen = button.dataset.electionWhen;
            activeKind = 'all';
            paint();
        }));
        root.querySelectorAll('[data-election-kind]').forEach((button) => button.addEventListener('click', () => {
            activeKind = button.dataset.electionKind;
            paint();
        }));
        root.querySelectorAll('[data-election-jump]').forEach((button) => button.addEventListener('click', () => {
            onShortcut?.(button.dataset.electionJump);
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
