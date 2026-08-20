import { escapeHtml } from '../../ui.js';

export const usaSections = [
    ['지도', 'subnational_map'],
    ['행정부', 'executive'],
    ['상원·하원', 'legislature'],
    ['정당·계파', 'factions'],
    ['2026 선거 과정', 'race_progress'],
];

const partyKo = (abbr) => ({ GOP: '공화당', DEM: '민주당', IND: '무소속' }[abbr] || abbr || '불명');

// Seat counts are printed exactly as the board publishes them.  The handoff
// fixes house_by_party (voting members) and the 437-row roster as two separate
// numbers on purpose -- the roster carries DC and the five territory delegates
// -- so nothing here adds a party column up to reach a chamber total.
const seatLine = (byParty) => Object.entries(byParty || {})
    .map(([abbr, seats]) => `${partyKo(abbr)} ${seats}`).join(' · ') || '불명';

const card = (label, value, note = '') => `
    <article class="elections-card">
        <div class="elections-card-label">${escapeHtml(label)}</div>
        <div class="elections-card-value">${escapeHtml(value)}</div>
        ${note ? `<div class="elections-event-meta">${escapeHtml(note)}</div>` : ''}
    </article>`;

const leadershipRows = (leadership, chamber) => leadership
    .filter((row) => row.chamber === chamber)
    .map((row) => `<div><span>${escapeHtml(row.title || row.office || '직책')}</span><strong>${escapeHtml(row.name || '불명')}</strong></div>`);

const memberRow = (member) => {
    const seat = member.chamber === 'house'
        ? `${member.state} ${member.district ?? 'AL'}구`
        : member.state;
    return `<div class="elections-member-row"><span>${escapeHtml(seat)}</span><span>${escapeHtml(`${member.name} · ${partyKo(member.abbr)}`)}</span></div>`;
};

const byStateThenDistrict = (a, b) => String(a.state).localeCompare(String(b.state))
    || String(a.district ?? '').localeCompare(String(b.district ?? ''), undefined, { numeric: true });

const roster = (summary, members) => members.length
    ? `<details class="elections-disclosure"><summary>${escapeHtml(summary)}</summary><div class="elections-member-list">${[...members].sort(byStateThenDistrict).map(memberRow).join('')}</div></details>`
    : '';

// The common shell's legislature renderer reads the Japanese/Korean key names
// (shugiin_by_party_abbr, summary.by_party_abbr), which leaves the USA tab with
// no seat cards at all.  Congress publishes its counts under ui_ready.congress.
export const usaLegislature = (country) => {
    const congress = country.ui_ready?.congress;
    const summary = congress?.summary || country.legislature_live?.summary;
    if (!summary) return null;
    const leadership = congress?.floor_leadership || country.legislature_live?.floor_leadership || [];

    return `
        <div class="elections-card-grid">
            ${card('하원 정당 의석', seatLine(summary.house_by_party), `표결권 현원 ${summary.house_voting_members} / ${summary.house_voting_seats}석`)}
            ${card('하원 공석', `${summary.house_vacancies}석`)}
            ${card('상원 정당 의석', seatLine(summary.senate_by_party), '100석')}
            ${card('상임위', '데이터 수집 예정', (congress?.missing_fields || []).join(', '))}
        </div>
        ${leadershipRows(leadership, 'house').length ? `<details class="elections-disclosure"><summary>하원 의장·원내지도부</summary><div class="elections-disclosure-rows">${leadershipRows(leadership, 'house').join('')}</div></details>` : ''}
        ${leadershipRows(leadership, 'senate').length ? `<details class="elections-disclosure"><summary>상원 원내지도부</summary><div class="elections-disclosure-rows">${leadershipRows(leadership, 'senate').join('')}</div></details>` : ''}
        ${roster(`하원 명부 ${summary.house_roster_rows_including_delegates}행 · 주·선거구 순`, congress?.house_members || [])}
        ${roster(`상원 명부 ${(congress?.senate_members || []).length}인 · 주 순`, congress?.senate_members || [])}
        <p class="elections-panel-note">하원 명부 ${summary.house_roster_rows_including_delegates}행에는 DC·5개 준주 대표단 ${Object.values(summary.house_delegates_by_party || {}).reduce((sum, value) => sum + value, 0)}명이 포함됩니다. 정당 의석은 위 카드의 표결권 기준 값을 사용하고, 명부 행 수와 합산하지 않습니다.</p>
        <p class="elections-panel-note">상원의원 임기 종료일과 상임위 정보는 공개 정본이 확보되지 않아 표시하지 않습니다.</p>
    `;
};
