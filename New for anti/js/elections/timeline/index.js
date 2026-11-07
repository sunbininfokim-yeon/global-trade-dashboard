import { allDatedEvents, splitByToday, groupByMonth, EVENT_KINDS, kindOf } from '../data/selectors.js';
import { escapeHtml, formatMonth } from '../ui.js';
import { renderDateGroups } from './group-by-date.js?v=2';

// 좌측 패널. 정치는 두 갈래다 (사용자 지시 2026-11-07):
//   선거  세계 선거 일정. '예정 선거'(기본)와 '끝난 선거'를 토글로 나눈다. 끝난 선거는
//         최근 것부터, 줄마다 결과 한 줄을 붙인다.
//   국가  나라 목록. 누르면 그 나라 화면(우측 대시보드: 지도·선거·행정부·의회 …)으로 간다.
//
// 종류 칩(대선·총선·지방·재보궐·당권)은 선거 갈래 안에서 그대로 쓴다.

let activePart = 'elections';
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

const REGION_KO = {
    east_asia: '동아시아', southeast_asia: '동남아시아', south_asia_se: '남아시아', oceania: '오세아니아', pacific: '오세아니아',
    north_america: '북미', americas: '중남미', europe: '유럽', middle_east: '중동', africa: '아프리카',
};
// 보드에 지역이 비어 있는 나라.
const REGION_FALLBACK = { USA: 'north_america', JPN: 'east_asia', RUS: 'europe' };
const SYSTEM_KO = { presidential: '대통령제', parliamentary: '의원내각제', semi_presidential: '이원집정부제', direct_democracy: '합의제(직접민주)', other: '기타 체제' };
const REGION_ORDER = ['동아시아', '북미', '유럽', '동남아시아', '남아시아', '중동', '중남미', '아프리카', '오세아니아', '기타'];

const countryList = (countries) => {
    const groups = new Map();
    countries.forEach((country) => {
        const region = REGION_KO[country.region || REGION_FALLBACK[country.iso3]] || '기타';
        if (!groups.has(region)) groups.set(region, []);
        groups.get(region).push(country);
    });
    return REGION_ORDER.filter((region) => groups.has(region)).map((region) => `
        <section class="elections-month-block">
            <h3 class="elections-month-head">${escapeHtml(region)}<span>${groups.get(region).length}개국</span></h3>
            <div class="elections-country-list">${groups.get(region)
                .sort((a, b) => (a.priority_tier ?? 9) - (b.priority_tier ?? 9) || String(a.name_ko).localeCompare(String(b.name_ko), 'ko'))
                .map((country) => `<button class="elections-country-row" type="button" data-election-country="${escapeHtml(country.iso3)}">
                    <span class="elections-country-name">${escapeHtml(country.name_ko || country.iso3)}</span>
                    <span class="elections-country-meta">${escapeHtml([country.head?.name_ko || country.head?.name_en, SYSTEM_KO[country.system] || country.system].filter(Boolean).join(' · '))}</span>
                </button>`).join('')}</div>
        </section>`).join('');
};

export const renderTimeline = (root, { calendar, countries, briefFor, onBriefOpen, shortcuts = [], onShortcut, onCountryOpen, today = new Date().toISOString().slice(0, 10) }) => {
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

    const countriesPart = () => `
        <p class="elections-panel-note">나라를 누르거나 지도에서 나라를 누르면 우측에 그 나라의 선거·행정부·의회·지방 블록이 열립니다.</p>
        <div class="elections-date-list">${countryList([...countries.values()])}</div>`;

    const paint = () => {
        root.innerHTML = `
            <div class="panel-header">
                <h2>정치</h2>
            </div>
            ${toggle('election-part', [['elections', '선거'], ['countries', '국가', countries.size]], activePart)}
            ${activePart === 'countries' ? countriesPart() : electionsPart()}
        `;
        bind();
    };

    // 목록은 수십 줄이라 줄마다 리스너를 달지 않고 한 번만 위임한다.
    const bind = () => {
        root.querySelectorAll('[data-election-part]').forEach((button) => button.addEventListener('click', () => {
            activePart = button.dataset.electionPart;
            paint();
        }));
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
        root.querySelectorAll('[data-election-country]').forEach((button) => button.addEventListener('click', () => {
            onCountryOpen?.(button.dataset.electionCountry);
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
