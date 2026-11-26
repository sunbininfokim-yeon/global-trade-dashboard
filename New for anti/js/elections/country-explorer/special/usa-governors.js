import { escapeHtml, personLinkHtml } from '../../ui.js';
import { seatLegend } from './hemicycle.js';

const PARTIES = {
    DEM: { label: '민주당', color: '#2563eb' },
    GOP: { label: '공화당', color: '#dc2626' },
    IND: { label: '무소속', color: '#94a3b8' },
};
const party = (id) => PARTIES[id] || { label: '미확인', color: '#64748b' };
const link = (label, url) => personLinkHtml(escapeHtml(label), /^https:\/\//i.test(url || '') ? url : '');
const localDate = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/New_York' }).format(new Date());
const knownWinner = (race) => race?.name && PARTIES[race.party]
    && ['reported_winner', 'certified'].includes(race.result_status);

const tallies = (ids) => {
    const counts = {};
    for (const value of ids) {
        const id = PARTIES[value] ? value : 'unknown';
        counts[id] = (counts[id] || 0) + 1;
    }
    return seatLegend([...Object.keys(PARTIES), 'unknown']
        .filter((id) => counts[id]).map((id) => ({ ...party(id), count: counts[id] })));
};

const comparison = (states, source) => {
    const races = states.filter((row) => row.transition);
    const wins = races.map((row) => knownWinner(row.transition) ? row.transition.party : null);
    const after = states.map((row) => row.transition
        ? (knownWinner(row.transition) ? row.transition.party : null)
        : row.party);
    const flips = races.filter((row) => knownWinner(row.transition) && row.party && row.party !== row.transition.party);
    return `<p class="elections-party-card-label">현직 · 명부 기준</p>
        ${tallies(states.map((row) => row.party))}
        <p class="elections-party-card-label">2026년 주지사 선거 ${races.length}곳 · 비선거 ${states.length - races.length}곳</p>
        ${tallies(wins)}
        <p class="elections-party-card-label">취임 후 예상 구성 · ${states.length}개 주</p>
        ${tallies(after)}
        <p class="elections-panel-note">${link('공개 승자 발표 기준', source.results_url)}</p>
        ${flips.length ? `<details class="elections-disclosure"><summary>정당 교체 예정 ${flips.length}곳</summary>
            <div class="elections-disclosure-rows">${flips.map((row) => `<div>
                <span>${escapeHtml(row.state_ko)} · ${escapeHtml(party(row.party).label)} → ${escapeHtml(party(row.transition.party).label)}</span>
                <strong>${link(row.transition.name, row.transition.result_url)}</strong>
            </div>`).join('')}</div></details>` : ''}`;
};

const leadershipRows = (entries) => entries.length
    ? `<div class="elections-disclosure-rows elections-leader-rows">${entries.map(({ role_ko, basis_ko, source_url, governor }) => `<div>
        <span>${link(role_ko, source_url)}${basis_ko ? ` · ${escapeHtml(basis_ko)}` : ''}</span>
        <strong><i aria-hidden="true" class="elections-party-dot" style="background:${party(governor.party).color}"></i>${link(governor.name, governor.office_url)} · ${escapeHtml(governor.state_ko)}</strong>
    </div>`).join('')}</div>`
    : '<p class="elections-muted">확인된 협회 직책이 없습니다.</p>';

const inaugurationStatus = (race, today) => {
    if (!race.start_date) return '취임일 확인 중';
    if (race.start_date < today) return '예정일 경과 · 취임 확인 대기';
    return race.date_status === 'state_schedule' ? '주 공식 일정' : '공개 예정일';
};

const inaugurationRow = (row, today) => {
    const race = row.transition;
    return `<div><span>${escapeHtml(row.state_ko)} · ${escapeHtml(race.start_date || '날짜 미확인')}</span>
        <strong>${knownWinner(race) ? link(race.name, race.result_url) : '결과 확인 중'} · ${link(inaugurationStatus(race, today), race.date_url)}</strong></div>`;
};

const agenda = (states, events, source, today) => {
    const dated = states.filter((row) => row.transition?.start_date)
        .sort((a, b) => a.transition.start_date.localeCompare(b.transition.start_date));
    const rows = [...dated, ...states.filter((row) => row.transition && !row.transition.start_date)];
    const next = dated.find((row) => row.transition.start_date >= today)?.transition.start_date;
    return `${next ? `<div class="elections-disclosure-rows">${dated.filter((row) => row.transition.start_date === next)
        .map((row) => inaugurationRow(row, today)).join('')}</div>` : ''}
        ${rows.length ? `<details class="elections-disclosure"><summary>전체 취임 일정 ${rows.length}개 주</summary>
            <div class="elections-disclosure-rows">${rows.map((row) => inaugurationRow(row, today)).join('')}</div>
        </details>` : ''}
        ${(events || []).filter((event) => (event.end_date || event.start_date) >= today)
        .map((event) => `<article class="elections-event"><div class="elections-event-title">${link(event.title_ko, event.url)}</div>
            <div class="elections-event-meta">${escapeHtml([event.start_date, event.end_date, event.status_ko, event.location_ko].filter(Boolean).join(' · '))}</div></article>`).join('')}
        <p class="elections-panel-note">${link('공개 취임 일정표', source.dates_url)} · 날짜는 해당 주 현지 기준입니다.</p>`;
};

const stateList = (rows) => `<div class="elections-disclosure-rows">${rows.map((row) => `<div>
    <span>${escapeHtml(row.state_ko)} · ${escapeHtml(row.state)}</span>
    <strong>${link(row.name, row.office_url)}${row.profile_url ? ` · ${link('NGA 약력', row.profile_url)}` : ''}</strong>
</div>`).join('')}</div>`;

const groupList = (groups, roster) => {
    const selected = new Set(roster.map((row) => row.state));
    const classified = new Set();
    const lists = groups.map((group) => {
        const people = group.governors.filter((member) => selected.has(member.state));
        people.forEach((row) => classified.add(row.state));
        return people.length ? `<details class="elections-disclosure">
            <summary>${escapeHtml(group.label_ko)} · 확인 ${people.length}명</summary>
            ${stateList(people)}
            <p class="elections-panel-note">${link(group.basis_ko, group.source_url)}</p>
        </details>` : '';
    }).join('');
    const unverified = roster.filter((row) => !classified.has(row.state));
    return `${lists}<details class="elections-disclosure"><summary>추가 협의체 소속 미확인 · ${unverified.length}명</summary>
        ${unverified.length ? stateList(unverified) : '<p class="elections-muted">해당 주지사 없음</p>'}
    </details>`;
};

const transitionRoster = (rows, today) => rows.length
    ? `<div class="elections-disclosure-rows elections-leader-rows">${rows.map(({ state_ko, transition: race }) => `<div>
        <span>${escapeHtml(state_ko)} · ${race.same_governor ? '현직 승리 · 새 임기' : '새 주지사'} · ${link(race.result_status === 'certified' ? '주 인증 확인' : '승자 발표', race.result_url)}</span>
        <strong>${link(race.name, race.result_url)}</strong>
        <span>${race.start_date ? escapeHtml(race.start_date) + ' · ' : ''}${link(inaugurationStatus(race, today), race.date_url)}</span>
    </div>`).join('')}</div>`
    : '<p class="elections-muted">확인된 승자 발표가 없습니다.</p>';

const partyCard = (id, states, leaders, groups, today) => {
    const current = states.filter((row) => row.party === id);
    const politicians = leaders.filter(({ governor }) => governor.party === id);
    const incoming = states.filter((row) => knownWinner(row.transition) && row.transition.party === id);
    return `<article class="elections-party-card">
        <header class="elections-party-card-head"><i aria-hidden="true" class="elections-party-dot" style="background:${party(id).color}"></i>
            <h3 style="font-size:1.125rem;margin:0">${escapeHtml(party(id).label)}</h3><span>현직 ${current.length}석</span></header>
        <p class="elections-party-card-label">주별 분포</p>
        <details class="elections-disclosure"><summary>현직 주지사 ${current.length}명</summary>${stateList(current)}</details>
        <p class="elections-party-card-label">주요 협회 당직자</p>
        ${leadershipRows(politicians)}
        <p class="elections-party-card-label">공개 협의체 명단</p>
        ${groupList(groups, current)}
        <details class="elections-disclosure"><summary>2026년 선거 승자 ${incoming.length}명</summary>
            ${transitionRoster(incoming, today)}</details>
    </article>`;
};

export const usaGovernorDashboard = (data, { today = localDate() } = {}) => {
    if (!data?.states?.length) {
        return '<p class="elections-muted">주지사 명부를 불러오지 못했습니다.</p>';
    }
    const states = data.states;
    const source = data.sources || {};
    const byState = new Map(states.map((row) => [row.state, row]));
    const leaders = (data.leadership || []).map((row) => ({ ...row, governor: byState.get(row.state) }))
        .filter((row) => row.governor?.name === row.name);
    const groups = (data.groups || []).map((group) => ({ ...group,
        governors: group.members.filter((member) => byState.get(member.state)?.name === member.name)
            .map((member) => byState.get(member.state)),
    }));
    return `<div data-usa-governors>
        <p class="elections-panel-note">50개 주 · 현직 명부 ${escapeHtml(data.as_of)} 기준</p>
        <div class="elections-chamber-quadrants">
            <section class="elections-quadrant" aria-label="전미주지사협회 지도부">
                <h4 class="section-title">전미주지사협회 지도부</h4>${leadershipRows(leaders.filter((row) => row.association === 'NGA'))}
            </section>
            <section class="elections-quadrant" aria-label="주지사 의석 분포">
                <h4 class="section-title">정당별 주지사</h4>${comparison(states, source)}
            </section>
        </div>
        <div class="elections-chamber-quadrants" style="margin-top:10px">
            <section class="elections-quadrant" aria-label="협의체 원문">
                <h4 class="section-title">협의체 · 명부</h4>
                <div class="elections-disclosure-rows">${groups.map((group) => `<div>
                    <span>${link(group.label_ko, group.source_url)}</span><strong>${group.governors.length}명</strong>
                </div>`).join('')}</div>
                <p class="elections-panel-note">${link('전미주지사협회 명부', source.roster_url)} · ${link('미 정부 주지사실 디렉터리', source.office_url)}</p>
                <p class="elections-panel-note">공개 협의체 명단에는 확인된 소속을 표시합니다. 한 주지사가 여러 협의체에 포함될 수 있습니다.</p>
            </section>
            <section class="elections-quadrant" aria-label="취임과 주요 일정">
                <h4 class="section-title">취임 · 주요 일정</h4>${agenda(states, data.events, source, today)}
            </section>
        </div>
        <div class="elections-party-card-grid" style="grid-template-columns:minmax(0,1fr)">
            ${Object.keys(PARTIES).filter((id) => id !== 'IND' || states.some((row) => row.party === id || row.transition?.party === id))
                .map((id) => partyCard(id, states, leaders, groups, today)).join('')}
        </div>
    </div>`;
};

export const usaExecutivePanels = (federal, governors) => `<div class="elections-chamber-wrap">
    <input type="radio" class="elections-chamber-radio" id="elections-chamber-1" name="usa-executive-level" checked>
    <input type="radio" class="elections-chamber-radio" id="elections-chamber-2" name="usa-executive-level">
    <div class="elections-chamber-tabs"><label for="elections-chamber-1" id="usa-federal-executive-label">연방 행정부</label>
        <label for="elections-chamber-2" id="usa-governors-label">주지사</label></div>
    <section class="elections-chamber-panel" data-chamber-slot="1" aria-labelledby="usa-federal-executive-label">
        ${federal || '<p class="elections-muted">연방 행정부 명부 미확보</p>'}</section>
    <section class="elections-chamber-panel" data-chamber-slot="2" aria-labelledby="usa-governors-label">
        ${usaGovernorDashboard(governors)}</section>
</div>`;
