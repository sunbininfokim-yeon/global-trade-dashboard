import { escapeHtml } from '../../ui.js';

// The 의회 screen is one fixed dashboard reused by both chambers -- 하원 and
// 상원 differ only in the numbers behind it, which is also what
// factions.ui_notes_ko.congress_panel asked for ("우측 위키 스타일 반원
// (hemicycle) — 상원·하원 탭").
//
// Quadrants: 의장·원내지도부 / 의석 반원 (top), 상임위 / 공석·일정 (bottom),
// then the two party cards underneath.
//
// Data contract for the parts the pipeline does not publish yet. All optional;
// each renders "수집 예정" until it arrives, which is not a claim that the
// thing is empty:
//
//   ui_ready.congress.vacancies:
//     [{ chamber, state, district, prior_party_abbr, vacated_on,
//        special_election_date, note_ko }]
//   ui_ready.congress.swing_seats:
//     [{ chamber, state, district, party_abbr, basis_ko }]
//        basis_ko says why the seat counts as swing (교차투표 / 3회 중 2회 이상
//        정당 교체 등) -- this file never derives that itself.

const PARTY = {
    GOP: { ko: '공화당', color: '#dc2626' },
    DEM: { ko: '민주당', color: '#2563eb' },
    IND: { ko: '무소속', color: '#94a3b8' },
};
const VACANT_COLOR = '#334155';
const partyKo = (abbr) => PARTY[abbr]?.ko || abbr || '불명';
const partyColor = (abbr) => PARTY[abbr]?.color || '#64748b';

// Leadership rows carry majority/minority in the office key rather than a
// party field, so the side is read from the key and only then mapped to a
// party through the seat counts -- arithmetic on published numbers, not an
// assumption about who holds the chamber.
const MAJORITY_OFFICES = new Set(['speaker', 'conference_chair']);
const leadershipSide = (office) => {
    const key = String(office || '').replace(/^senate_/, '');
    if (MAJORITY_OFFICES.has(key) || key.startsWith('majority')) return 'majority';
    return 'minority';
};

const seatEntries = (byParty) => Object.entries(byParty || {})
    .filter(([, seats]) => Number.isFinite(seats) && seats > 0)
    .sort((a, b) => b[1] - a[1]);

const majorityAbbr = (byParty) => seatEntries(byParty)[0]?.[0] || null;
const minorityAbbr = (byParty) => seatEntries(byParty)[1]?.[0] || null;

// A Wikipedia-style hemicycle: seats spread over concentric arcs, each arc
// holding a share proportional to its radius, then coloured left to right in
// the order the groups are given. Seat position carries no meaning beyond the
// grouping -- no member is bound to a dot.
const hemicycle = (groups) => {
    const total = groups.reduce((sum, group) => sum + group.count, 0);
    if (!total) return '';
    const rowCount = total > 300 ? 12 : total > 120 ? 8 : 5;
    const radii = Array.from({ length: rowCount }, (_, index) => 42 + 58 * (rowCount === 1 ? 0 : index / (rowCount - 1)));
    const weight = radii.reduce((sum, radius) => sum + radius, 0);
    const perRow = radii.map((radius) => Math.max(1, Math.round((total * radius) / weight)));
    for (let drift = total - perRow.reduce((a, b) => a + b, 0), i = perRow.length - 1; drift !== 0; i = (i - 1 + perRow.length) % perRow.length) {
        const step = drift > 0 ? 1 : -1;
        if (perRow[i] + step >= 1) { perRow[i] += step; drift -= step; }
    }
    const seats = [];
    radii.forEach((radius, rowIndex) => {
        const count = perRow[rowIndex];
        for (let index = 0; index < count; index += 1) {
            const t = count === 1 ? 0.5 : index / (count - 1);
            seats.push({ t, rowIndex, radius });
        }
    });
    seats.sort((a, b) => a.t - b.t || a.rowIndex - b.rowIndex);

    let cursor = 0;
    const dots = [];
    groups.forEach((group) => {
        for (let i = 0; i < group.count && cursor < seats.length; i += 1, cursor += 1) {
            const seat = seats[cursor];
            const angle = Math.PI * (1 - seat.t);
            const x = (100 + seat.radius * Math.cos(angle)).toFixed(2);
            const y = (104 - seat.radius * Math.sin(angle)).toFixed(2);
            dots.push(`<circle cx="${x}" cy="${y}" r="2.1" fill="${group.color}"${group.stroke ? ` stroke="${group.stroke}" stroke-width="0.7"` : ''}/>`);
        }
    });
    return `
        <svg class="elections-hemicycle" viewBox="0 0 200 112" role="img" aria-label="${escapeHtml(`의석 ${total}석 정당별 분포`)}">
            ${dots.join('')}
            <text x="100" y="100" text-anchor="middle" class="elections-hemicycle-total">${total}</text>
        </svg>`;
};

const seatLegend = (groups) => `
    <div class="elections-seat-legend">
        ${groups.map((group) => `<span class="elections-seat-legend-item"><i style="background:${group.color}"></i>${escapeHtml(`${group.label} ${group.count}석`)}</span>`).join('')}
    </div>`;

const chamberGroups = (chamber, summary) => {
    const byParty = chamber === 'house' ? summary.house_by_party : summary.senate_by_party;
    const vacancies = chamber === 'house' ? (summary.house_vacancies || 0) : 0;
    const majority = majorityAbbr(byParty);
    const minority = minorityAbbr(byParty);
    // Minority on the left, majority on the right, everyone else between --
    // the seating convention the reference chart uses.
    const ordered = [
        ...(minority ? [[minority, byParty[minority]]] : []),
        ...seatEntries(byParty).filter(([abbr]) => abbr !== majority && abbr !== minority),
    ];
    const groups = ordered.map(([abbr, count]) => ({ label: partyKo(abbr), count, color: partyColor(abbr) }));
    if (vacancies > 0) groups.push({ label: '공석', count: vacancies, color: VACANT_COLOR, stroke: '#64748b' });
    if (majority) groups.push({ label: partyKo(majority), count: byParty[majority], color: partyColor(majority) });
    return groups;
};

const leadershipPanel = (chamber, leadership, byParty) => {
    const rows = (leadership || []).filter((row) => row.chamber === chamber);
    if (!rows.length) return '<p class="elections-muted">공개된 지도부 명부가 없습니다.</p>';
    const partyFor = (office) => (leadershipSide(office) === 'majority' ? majorityAbbr(byParty) : minorityAbbr(byParty));
    return `<div class="elections-disclosure-rows elections-leader-rows">${rows.map((row) => {
        const abbr = partyFor(row.office);
        return `<div>
            <span>${escapeHtml(row.title || row.office || '직책')}</span>
            <strong><i class="elections-party-dot" style="background:${partyColor(abbr)}"></i>${escapeHtml(`${row.name || '불명'} · ${partyKo(abbr)}`)}</strong>
        </div>`;
    }).join('')}</div>`;
};

// ui_ready.congress.committees (usa_committees.json) is an object keyed by
// chamber with each chamber's own standing_committees[] -- not the flat,
// per-row `chamber`-tagged array this panel draws from. Flattening it once
// here keeps committeePanel() reading a single simple shape either way.
const flattenCommittees = (committeesData) => {
    if (!committeesData) return null;
    const rows = [];
    for (const chamber of ['house', 'senate']) {
        const list = committeesData[chamber]?.standing_committees;
        if (!Array.isArray(list)) continue;
        for (const row of list) {
            rows.push({
                chamber,
                committee_id: row.code,
                name: row.name,
                // No short_name in the source; trimming the common "Committee
                // on " prefix keeps chips readable without inventing an
                // abbreviation the source doesn't publish.
                short_name: (row.name || '').replace(/^Committee on\s+/i, ''),
            });
        }
    }
    return rows.length ? rows : null;
};

const committeePanel = (chamber, committees) => {
    if (!Array.isArray(committees)) {
        return `<p class="elections-muted">상임위 목록은 정책 데이터에서 불러옵니다.</p>
            <button class="elections-button" type="button" data-election-action="policy-committees">정책 › 미국 상임위 열기</button>`;
    }
    const rows = committees.filter((row) => row.chamber === chamber);
    if (!rows.length) return '<p class="elections-muted">이 원의 상임위 목록이 비어 있습니다.</p>';
    return `<div class="elections-committee-chips">${rows.map((row) => `
        <button class="elections-committee-chip" type="button"
            data-election-action="policy-committee"
            data-committee-id="${escapeHtml(row.committee_id)}"
            title="${escapeHtml(row.name || '')}">${escapeHtml(row.short_name || row.name || row.committee_id)}</button>`).join('')}</div>
        <p class="elections-panel-note">누르면 정책 › 미국 › 상임위 화면으로 이동합니다.</p>`;
};

const vacancyPanel = (chamber, congress, generalElection, members) => {
    const rows = (congress.vacancies || []).filter((row) => row.chamber === chamber);
    const count = chamber === 'house' ? (congress.summary?.house_vacancies || 0) : null;
    // Class II is up in the 2026-11-03 midterm; usa_senate_terms.json overlays
    // up_in_2026 onto each senator, so this is a straight count, not a
    // client-side election calculation.
    const upIn2026 = chamber === 'senate' ? (members || []).filter((row) => row.up_in_2026).length : null;
    // A null special_election_date can mean "not collected" or "officially not
    // announced yet"; special_election_date_status tells them apart, so the two
    // never read the same.
    const electionText = (row) => {
        if (row.special_election_date) return `보궐 ${row.special_election_date}`;
        if (row.special_election_date_status === 'unannounced') return '보궐일 미발표';
        return '보궐 일정 미수집';
    };
    const detail = rows.length ? `<div class="elections-disclosure-rows">${rows.map((row) => `<div>
            <span>${escapeHtml([row.state, row.district ? `${row.district}구` : ''].filter(Boolean).join(' '))}</span>
            <strong>${escapeHtml([
                row.prior_party_abbr ? `직전 ${partyKo(row.prior_party_abbr)}` : '',
                row.prior_member,
                electionText(row),
            ].filter(Boolean).join(' · '))}</strong>
        </div>`).join('')}</div>`
        : '<p class="elections-muted">공석별 지역구·보궐 일정·직전 의원 정당은 수집 예정입니다.</p>';
    return `
        <div class="elections-card-grid">
            ${count === null
                ? '<article class="elections-card"><div class="elections-card-label">공석</div><div class="elections-card-value">공개 집계 없음</div></article>'
                : `<article class="elections-card"><div class="elections-card-label">공석</div><div class="elections-card-value">${count}석</div></article>`}
            <article class="elections-card"><div class="elections-card-label">다음 총선</div><div class="elections-card-value">${escapeHtml(generalElection || '불명')}</div></article>
            ${upIn2026 !== null ? `<article class="elections-card"><div class="elections-card-label">2026 개선 (Class II)</div><div class="elections-card-value">${upIn2026}석</div></article>` : ''}
        </div>
        ${detail}`;
};

const stateTally = (members, abbr) => {
    const counts = new Map();
    members.filter((row) => row.abbr === abbr).forEach((row) => {
        counts.set(row.state, (counts.get(row.state) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
};

const factionRows = (factions, partyKey) => {
    const list = factions?.parties?.[partyKey]?.factions;
    if (!Array.isArray(list) || !list.length) return '';
    return `<div class="elections-disclosure-rows">${list.map((faction) => {
        // display_count is an object when counted and a bare string ("불명")
        // when it is not; never render the string as a number.
        const value = typeof faction.display_count === 'object' ? faction.display_count?.value : null;
        return `<div>
            <span>${escapeHtml(`${faction.name_ko || faction.abbr}${faction.spectrum_ko ? ` · ${faction.spectrum_ko}` : ''}`)}</span>
            <strong>${escapeHtml(Number.isFinite(value) ? `${value}명` : '집계 없음')}</strong>
        </div>`;
    }).join('')}</div>`;
};

const partyCard = (chamber, abbr, { members, leadership, byParty, factions, swingSeats, coverage }) => {
    const total = byParty?.[abbr];
    const states = stateTally(members, abbr);
    const leaders = (leadership || []).filter((row) => row.chamber === chamber
        && (leadershipSide(row.office) === 'majority' ? majorityAbbr(byParty) : minorityAbbr(byParty)) === abbr);
    const swing = (swingSeats || []).filter((row) => row.chamber === chamber && row.party_abbr === abbr);
    const partial = coverage?.swing_seats === 'partial_verified_examples';
    const partyKey = abbr === 'DEM' ? 'dem' : abbr === 'GOP' ? 'gop' : null;
    const factionsHtml = chamber === 'house' && partyKey ? factionRows(factions, partyKey) : '';

    return `
        <article class="elections-party-card">
            <header class="elections-party-card-head">
                <i class="elections-party-dot" style="background:${partyColor(abbr)}"></i>
                <strong>${escapeHtml(partyKo(abbr))}</strong>
                <span>${escapeHtml(Number.isFinite(total) ? `${total}석` : '집계 없음')}</span>
            </header>

            <p class="elections-party-card-label">1 · 의원 수</p>
            ${states.length ? `<details class="elections-disclosure"><summary>주별 분포 ${states.length}개 주</summary><div class="elections-disclosure-rows">${states.map(([state, count]) => `<div><span>${escapeHtml(state)}</span><strong>${count}명</strong></div>`).join('')}</div></details>` : '<p class="elections-muted">명부가 없습니다.</p>'}
            ${swing.length ? `<details class="elections-disclosure"><summary>검증된 경합 이력 ${swing.length}곳</summary><div class="elections-disclosure-rows">${swing.map((row) => `<div><span>${escapeHtml([row.state, row.district ? `${row.district}구` : ''].filter(Boolean).join(' '))}</span><strong>${escapeHtml(row.basis_ko || '근거 미기재')}</strong></div>`).join('')}</div>${
                // The source calls this a partial list of verified examples, so
                // the screen must not let an absent seat read as "safe" -- nor
                // turn a past result into a 2026 forecast.
                partial ? '<p class="elections-panel-note">공식 결과로 검증된 일부 목록입니다. 여기 없다고 경합이 아니라는 뜻은 아니며, 과거 당선 정당 이력일 뿐 2026 접전 예측이 아닙니다.</p>' : ''
            }</details>`
                : '<p class="elections-panel-note">경합 이력(교차투표·최근 3회 중 2회 이상 정당 교체)은 판정 기준이 담긴 데이터가 들어오면 표시합니다.</p>'}

            <p class="elections-party-card-label">2 · 주요 당직자</p>
            ${leaders.length ? `<div class="elections-disclosure-rows">${leaders.map((row) => `<div><span>${escapeHtml(row.title || row.office)}</span><strong>${escapeHtml(row.name || '불명')}</strong></div>`).join('')}</div>` : '<p class="elections-muted">공개된 당직자 명부가 없습니다.</p>'}

            <p class="elections-party-card-label">3 · 계파 분류</p>
            ${factionsHtml || `<p class="elections-muted">${chamber === 'senate' ? '상원 계파 데이터는 수집 대상이 아닙니다.' : '계파 데이터가 없습니다.'}</p>`}
            ${factionsHtml ? '<p class="elections-panel-note">계파는 중복 소속이 가능해 합산하지 않습니다.</p>' : ''}
        </article>`;
};

const chamberPanel = (chamber, ctx) => {
    const { congress, factions, committees, generalElection } = ctx;
    const summary = congress.summary || {};
    const byParty = chamber === 'house' ? summary.house_by_party : summary.senate_by_party;
    const members = (chamber === 'house' ? congress.house_members : congress.senate_members) || [];
    const groups = chamberGroups(chamber, summary);
    const majority = majorityAbbr(byParty);
    const minority = minorityAbbr(byParty);

    return `
        <div class="elections-chamber-quadrants">
            <section class="elections-quadrant">
                <p class="section-title">의장 · 원내지도부</p>
                ${leadershipPanel(chamber, congress.floor_leadership, byParty)}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">의석 분포</p>
                ${hemicycle(groups)}
                ${seatLegend(groups)}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">상임위</p>
                ${committeePanel(chamber, committees)}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">공석 · 일정</p>
                ${vacancyPanel(chamber, congress, generalElection, members)}
            </section>
        </div>
        <div class="elections-party-card-grid">
            ${[minority, majority].filter(Boolean).map((abbr) => partyCard(chamber, abbr, {
                members, leadership: congress.floor_leadership, byParty, factions, swingSeats: congress.swing_seats,
                coverage: congress.context_coverage,
            })).join('')}
        </div>`;
};

export const usaLegislature = (country) => {
    const congress = country.ui_ready?.congress;
    if (!congress?.summary) return null;
    const ctx = {
        congress,
        factions: country.factions,
        committees: flattenCommittees(congress.committees),
        generalElection: country.race_progress?.cumulative?.general_election,
    };
    const summary = congress.summary;

    // A CSS-only chamber switch: the modal body is inserted as static HTML, so
    // the two panels ship together and the checked radio decides which shows.
    // The radios stay focusable (clipped, not display:none) so arrow keys move
    // between chambers the way a native tab list does.
    return `
        <div class="elections-chamber-switch">
            <input class="elections-chamber-radio" type="radio" name="elections-chamber" id="elections-chamber-house" checked>
            <input class="elections-chamber-radio" type="radio" name="elections-chamber" id="elections-chamber-senate">
            <div class="elections-chamber-tabs" role="tablist">
                <label for="elections-chamber-house">하원 ${summary.house_voting_seats || ''}석</label>
                <label for="elections-chamber-senate">상원 ${Object.values(summary.senate_by_party || {}).reduce((sum, value) => sum + value, 0) || ''}석</label>
            </div>
            <div class="elections-chamber-panel" data-chamber="house">${chamberPanel('house', ctx)}</div>
            <div class="elections-chamber-panel" data-chamber="senate">${chamberPanel('senate', ctx)}</div>
        </div>
        <p class="elections-panel-note">하원 정당 의석은 표결권 기준(현원 ${summary.house_voting_members} / ${summary.house_voting_seats}석)이며, DC·준주 대표단 ${Object.values(summary.house_delegates_by_party || {}).reduce((sum, value) => sum + value, 0)}명이 포함된 명부 ${summary.house_roster_rows_including_delegates}행과 합산하지 않습니다.</p>`;
};
