import { bioguideUrl, escapeHtml, personLinkHtml } from '../../ui.js';
import { hemicycle, seatLegend } from './hemicycle.js';
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

const chamberGroups = (chamber, summary, vacancies) => {
    const byParty = chamber === 'house' ? summary.house_by_party : summary.senate_by_party;
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

const committeeLeadership = (label, cards, people) => cards?.length
    ? `<details class="elections-disclosure"><summary>${label}</summary>
        ${cards.map((card) => `<article class="elections-event">
            <div class="elections-event-title">${sourceLink(card.name, card.committee_url)}</div>
            <div class="elections-disclosure-rows">${[['위원장', card.chair], [card.ranking_member?.role_ko || '간사', card.ranking_member]]
                .map(([title, member]) => `<div><span>${escapeHtml(title)}</span><strong>${member
                    ? nameHtml(displayName(member.name), member.bioguide, people) : '공개 명단 미확인'}</strong></div>`).join('')}</div>
        </article>`).join('')}
    </details>` : '';

const committeePanel = (chamber, committees, cards, people, specialCommittees) => {
    const links = chamber === 'senate'
        ? `<p class="elections-panel-note">${sourceLink('공식 위원회 배정', 'https://www.senate.gov/general/committee_assignments/assignments.htm')} · ${sourceLink('전체 청문회 일정', 'https://www.senate.gov/committees/hearings_meetings.htm')}</p>`
        : '';
    if (!Array.isArray(committees)) {
        return `<p class="elections-muted">상임위 목록은 정책 데이터에서 불러옵니다.</p>
            <button class="elections-button" type="button" data-election-action="policy-committees">정책 › 미국 상임위 열기</button>
            ${committeeLeadership('상임위별 위원장 · 간사', cards, people)}
            ${committeeLeadership('특별·선출위원회 지도부', specialCommittees, people)}
            ${links}`;
    }
    const rows = committees.filter((row) => row.chamber === chamber);
    if (!rows.length) return '<p class="elections-muted">이 원의 상임위 목록이 비어 있습니다.</p>';
    // chamber + name (not row.committee_id) travel to the handoff: this
    // panel's own code scheme (election_watch's usa_committees.json) doesn't
    // match Congress.gov's systemCode the policy module keys its committees
    // on -- see openPolicyCommittee() in app.js for how the two get matched.
    return `<div class="elections-committee-chips">${rows.map((row) => `
        <button class="elections-committee-chip" type="button"
            data-election-action="policy-committee"
            data-chamber="${escapeHtml(row.chamber)}"
            data-committee-name="${escapeHtml(row.name || '')}"
            title="${escapeHtml(row.name || '')}">${escapeHtml(row.short_name || row.name || row.committee_id)}</button>`).join('')}</div>
        <p class="elections-panel-note">누르면 정책 › 미국 › 상임위 화면으로 이동합니다.</p>
        ${committeeLeadership('상임위별 위원장 · 간사', cards, people)}
        ${committeeLeadership('특별·선출위원회 지도부', specialCommittees, people)}
        ${links}`;
};

const httpsUrl = (value) => /^https:\/\//i.test(value || '') ? value : '';
const sourceLink = (label, url) => personLinkHtml(escapeHtml(label), httpsUrl(url));
const displayName = (name) => {
    const [last, first] = String(name || '').split(', ');
    return first ? `${first} ${last}` : last;
};

const nameHtml = (name, id, people) => personLinkHtml(
    escapeHtml(name || people[id]?.name || '이름 미확인'),
    httpsUrl(people[id]?.official_url) || (id ? bioguideUrl(id) : ''),
);

const OFFICES = {
    speaker: '하원의장',
    majority_leader: '다수당 원내대표',
    minority_leader: '소수당 원내대표',
    majority_whip: '다수당 원내총무',
    minority_whip: '소수당 원내총무',
    caucus_chair: '민주당 의원총회 의장',
    conference_chair: '공화당 의원총회 의장',
    assistant_democratic_leader: '민주당 원내 보좌역',
};

const leadersHtml = (rows, people) => rows.length
    ? `<div class="elections-disclosure-rows elections-leader-rows">${rows.map((row) => `<div>
        <span>${escapeHtml(row.title)}${row.status_ko ? ` · ${escapeHtml(row.status_ko)}` : ''}${row.source_url ? ` · ${sourceLink('근거', row.source_url)}` : ''}</span>
        <strong><i aria-hidden="true" class="elections-party-dot" style="background:${partyColor(row.party_abbr)}"></i>${nameHtml(row.name, row.bioguide_id, people)}</strong>
    </div>`).join('')}</div>`
    : '<p class="elections-muted">공개된 지도부 명부가 없습니다.</p>';

const leadershipRows = (congress, chamber, members, people, byParty) => {
    const officeIds = new Map(Object.entries(people).flatMap(([id, item]) =>
        (item.aliases || []).map((alias) => [alias, id])));
    const memberById = new Map(members.map((member) => [member.bioguideId, member]));
    return (congress.floor_leadership || []).filter((row) => row.chamber === chamber).map((row) => {
        const name = row.name?.replace(/^(Rep|Sen)\.\s+/, '');
        const id = row.bioguide_id || officeIds.get(name)
            || members.find((member) => displayName(member.name) === name)?.bioguideId;
        return {
            name,
            bioguide_id: id,
            title: OFFICES[row.office?.replace(/^senate_/, '')] || row.title || row.office,
            party_abbr: row.party_abbr || memberById.get(id)?.abbr
                || (leadershipSide(row.office) === 'majority' ? majorityAbbr(byParty) : minorityAbbr(byParty)),
        };
    });
};

const incomingHtml = (incoming, people, today) => {
    if (!incoming?.leaders?.length) return '';
    const rows = incoming.leaders.map((row) => {
        return row.decision_date && row.decision_date < today ? { ...row, status_ko: '결과 확인 대기' } : row;
    });
    return `<details class="elections-disclosure">
        <summary>120대 지도부 선출 · 후보 (${escapeHtml(incoming.as_of)} 기준)</summary>
        ${leadersHtml(rows, people)}
        <p class="elections-panel-note">${(incoming.sources || []).map((source) => sourceLink(source.title, source.url)).join(' · ')}</p>
    </details>`;
};

const vacancyPanel = (chamber, congress, count, senateSource) => {
    const rows = (congress.vacancies || []).filter((row) => row.chamber === chamber);
    const status = Number.isInteger(count) ? `${count}석` : '공개 집계 미확인';
    return `<p class="elections-panel-note">의원 공석 · <strong>${status}</strong></p>
        ${rows.length ? `<div class="elections-disclosure-rows">${rows.map((row) => `<div>
            <span>${escapeHtml([row.state, row.district].filter(Boolean).join('-'))} · ${escapeHtml(row.prior_member)}</span>
            <strong>${escapeHtml(row.special_election_date ? `보궐 ${row.special_election_date}`
                : row.special_election_date_status === 'unannounced' ? '보궐일 미발표' : '보궐 일정 미수집')}</strong>
        </div>`).join('')}</div>` : ''}
        ${chamber === 'house' ? `<p class="elections-panel-note">${sourceLink('하원 사무처 공석 공고', 'https://clerk.house.gov/Members/ViewVacancies')}</p>`
            : senateSource ? `<p class="elections-panel-note">${sourceLink('상원 공식 의석·공석 집계', senateSource)}</p>` : ''}`;
};

const dateInWashington = () => new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

const eventHtml = (item) => `<article class="elections-event">
    <div class="elections-event-title">${sourceLink(item.title_ko || item.title, item.url)}</div>
    <div class="elections-event-meta">${escapeHtml([item.date, item.date_note_ko, item.description_ko].filter(Boolean).join(' · '))}</div>
</article>`;

const agendaPanel = (chamber, agenda, today) => {
    const upcoming = (agenda?.milestones || []).filter((item) =>
        item.chambers?.includes(chamber) && item.date >= today).sort((a, b) => a.date.localeCompare(b.date));
    const sources = (agenda?.sources || []).filter((source) => source.chamber === chamber);
    const meetings = upcoming.filter((item) => item.kind === 'committee');
    return `<div class="elections-screen-list">${upcoming.filter((item) => item.kind !== 'committee').map(eventHtml).join('')}</div>
        ${meetings.length ? `<details class="elections-disclosure"><summary>상원 청문회·위원회 일정 ${meetings.length}건</summary>
            <div class="elections-screen-list">${meetings.map(eventHtml).join('')}</div>
            <p class="elections-panel-note">주요 공고를 선별해 표시합니다. ${sourceLink('상원 전체 청문회 일정', 'https://www.senate.gov/committees/hearings_meetings.htm')}</p>
        </details>` : ''}
        ${sources.map((source) => `<details class="elections-disclosure">
            <summary>${escapeHtml(source.label_ko)}${source.date ? ` · ${escapeHtml(source.date)}` : ''}</summary>
            ${source.status === 'stale' ? '<p class="elections-panel-note">수집 장애 · 마지막 확인 자료</p>'
                : source.status === 'unavailable' ? '<p class="elections-panel-note">수집 장애 · 공식 일정 원문을 열 수 있습니다.</p>' : ''}
            ${source.entries?.length ? `<div class="elections-screen-list">${source.entries.map(eventHtml).join('')}</div>` : ''}
            <p class="elections-panel-note">${sourceLink('공식 일정 원문', source.page_url || source.url)}${source.checked_at ? ` · 확인 ${escapeHtml(source.checked_at.slice(0, 10))}` : ''}</p>
        </details>`).join('')}
        ${!upcoming.length && !sources.length ? '<p class="elections-muted">공개 일정 연결 대기</p>' : ''}
        ${upcoming.length || sources.length ? '<p class="elections-panel-note">일정은 미국 동부 날짜 기준입니다.</p>' : ''}`;
};

const rosterHtml = (members, people) => `<div class="elections-disclosure-rows">
    ${members.map((member) => `<div>
        <span>${nameHtml(people[member.bioguideId]?.name || displayName(member.name), member.bioguideId, people)}</span>
        <strong>${escapeHtml(member.state_abbr
            ? [member.state_abbr, member.district == null ? '' : member.district === 0 ? 'AL' : String(member.district).padStart(2, '0')].filter(Boolean).join('-')
            : member.state)}</strong>
    </div>`).join('')}
</div>`;

const FACTION_TYPES = {
    voting_profile: '119대 상원 표결 성향 · 당내 3구간',
    research_snapshot: '공개 자료로 재구성한 명단',
    affiliated_roster: '연계 PAC 공개 명단',
    public_membership: '공개 회원 명단',
    named_cochairs: '원문에서 확인한 공동의장',
    named_participants: '원문에서 이름을 확인한 의원',
};

const factionRows = (groups, members, people, chamber) => {
    const byId = new Map(members.map((row) => [row.bioguideId, row]));
    const assigned = new Set();
    const rosterDetails = (label, list, caption = '', extra = '', partial = false) => `<details class="elections-disclosure">
        <summary>${escapeHtml(label)} · ${partial ? '확인 ' : ''}${list.length}명</summary>
        ${caption ? `<p class="elections-panel-note">${caption}</p>` : ''}
        ${list.length ? rosterHtml(list, people) : '<p class="elections-muted">해당 의원 없음</p>'}
        ${extra}
    </details>`;
    const details = (groups || []).map((group) => {
        const list = [...new Set(group.member_ids || [])].map((id) => byId.get(id)).filter(Boolean);
        if (group.kind !== 'voting_profile') list.forEach((member) => assigned.add(member.bioguideId));
        list.sort((a, b) => (a.state_abbr || a.state || '').localeCompare(b.state_abbr || b.state || '')
            || (a.district ?? 0) - (b.district ?? 0) || a.name.localeCompare(b.name));
        const caption = [FACTION_TYPES[group.kind], group.as_of].filter(Boolean).map(escapeHtml).join(' · ');
        const links = [group.source_url, group.additional_source_url].filter(Boolean);
        const votingProfile = group.kind === 'voting_profile';
        const partial = ['named_cochairs', 'named_participants'].includes(group.kind);
        return rosterDetails(group.name_ko, list, caption,
            links.length ? `<p class="elections-panel-note">${links.map((url) => sourceLink(votingProfile ? 'Voteview 원자료' : '명단 원문', url)).join(' · ')}</p>` : '',
            partial);
    });
    const unclassified = members.filter((row) => !assigned.has(row.bioguideId))
        .sort((a, b) => a.state.localeCompare(b.state) || a.name.localeCompare(b.name));
    return `${chamber === 'senate' && (groups || []).some((group) => group.kind === 'voting_profile')
        ? '<p class="elections-panel-note">표결 성향은 119대 Voteview DW-NOMINATE 1차원 점수를 정당별로 정렬해 세 구간으로 나눈 자체 분류입니다. 공개 코커스 소속은 별도로 표시합니다.</p>' : ''}
        ${details.join('')}${rosterDetails(chamber === 'senate' ? '공개 계파·연대 미확인' : '계파 미확인', unclassified, (groups || []).length
            ? '표시된 명단과 연결되지 않은 의원입니다.' : '공개 명단을 확보하면 반영합니다.')}
        ${details.length ? '<p class="elections-panel-note">한 의원이 여러 명단에 포함될 수 있습니다.</p>' : ''}`;
};

const partyCard = (abbr, { chamber, members, leaders, total, groups, people, swingSeats, term }) => {
    const partyMembers = members.filter((row) => row.abbr === abbr);
    const states = new Map();
    for (const member of partyMembers) {
        const state = member.state || member.state_abbr;
        if (!states.has(state)) states.set(state, []);
        states.get(state).push(member);
    }
    const stateRows = [...states.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
    return `<article class="elections-party-card">
        <header class="elections-party-card-head">
            <i aria-hidden="true" class="elections-party-dot" style="background:${partyColor(abbr)}"></i>
            <h3 style="font-size:1.125rem;margin:0">${escapeHtml(partyKo(abbr))}</h3>
            <span>${Number.isFinite(total) ? `${total}석` : '집계 없음'}</span>
        </header>
        <p class="elections-party-card-label">주별 분포</p>
        ${stateRows.length ? `<details class="elections-disclosure"><summary>${stateRows.length}개 주</summary>
            <div class="elections-disclosure-rows">${stateRows.map(([state, roster]) => `<div><span>${escapeHtml(state)}${chamber === 'senate' ? ` · ${roster.length}명` : ''}</span>
                <strong>${chamber === 'senate' ? roster.map((member) =>
                    nameHtml(people[member.bioguideId]?.name || displayName(member.name), member.bioguideId, people)).join(' · ') : `${roster.length}명`}</strong></div>`).join('')}</div>
        </details>` : '<p class="elections-muted">명부가 없습니다.</p>'}
        ${swingSeats.length ? `<details class="elections-disclosure"><summary>확인된 경합 이력 ${swingSeats.length}곳</summary>
            <div class="elections-disclosure-rows">${swingSeats.map((row) => `<div><span>${escapeHtml([row.state, row.district].filter(Boolean).join('-'))}</span><strong>${escapeHtml(row.basis_ko)}</strong></div>`).join('')}</div>
        </details>` : ''}
        <p class="elections-party-card-label">주요 당직자</p>
        ${leadersHtml(leaders.filter((row) => row.party_abbr === abbr || row.caucus_party_abbr === abbr), people)}
        <p class="elections-party-card-label">계파 분류${term ? ` · ${term}대` : ''}</p>
        ${factionRows(groups, partyMembers, people, chamber)}
    </article>`;
};

export const usaLegislature = (country, chamber, { today = dateInWashington() } = {}) => {
    const congress = country.ui_ready?.congress;
    if (!congress?.summary || !['house', 'senate'].includes(chamber)) return null;
    const { rosters, agenda } = country.us_congress_dashboard || {};
    const people = rosters?.people || {};
    const chamberData = rosters?.chambers?.[chamber];
    const summary = congress.summary;
    const byParty = summary[`${chamber}_by_party`];
    const members = (congress[`${chamber}_members`] || []).filter((row) => !row.is_delegate);
    const current = chamberData?.current;
    const senateCurrent = chamber === 'senate' && current?.checked_on <= today && today < current.ends_before
        ? current : null;
    const officialLeaders = (senateCurrent?.leaders || []).filter((row) =>
        members.some((member) => member.bioguideId === row.bioguide_id && member.abbr === row.party_abbr));
    const leaders = officialLeaders.length ? officialLeaders : leadershipRows(congress, chamber, members, people, byParty);
    const coreLeaders = officialLeaders.length ? leaders.filter((row) => row.featured) : leaders;
    const additionalLeaders = officialLeaders.length ? leaders.filter((row) => !row.featured) : [];
    const caucusing = senateCurrent?.independent_caucus;
    const allies = (caucusing?.member_ids || []).filter((id) =>
        members.some((member) => member.bioguideId === id && member.abbr === 'IND'));
    const senateOccupied = seatEntries(summary.senate_by_party).reduce((count, [, seats]) => count + seats, 0);
    const officialVacancies = senateCurrent?.vacancies;
    const currentVacancies = Number.isInteger(officialVacancies) && senateOccupied + officialVacancies === 100
        ? officialVacancies : summary.senate_vacancies;
    const vacancies = chamber === 'house' ? summary.house_vacancies : currentVacancies;
    const groups = chamberGroups(chamber, summary, vacancies);
    const date = chamber === 'house' ? congress.context_coverage?.house_source_published_on
        : congress.context_coverage?.senate_roster_as_of?.slice(0, 10);
    const committees = flattenCommittees(congress.committees);
    const standingCards = (congress.standing_committee_cards?.[chamber] || []).map((card) => {
        const correction = senateCurrent?.standing_committee_roles?.[card.system_code];
        if (!correction || correction.bioguide_id !== card.ranking_member?.bioguide) return card;
        return { ...card, committee_url: correction.source_url,
            ranking_member: { ...card.ranking_member, role_ko: correction.role_ko } };
    });

    return `<div class="elections-usa-legislature" data-usa-chamber="${chamber}">
        <div class="elections-chamber-quadrants">
            <section class="elections-quadrant" aria-label="원내 지도부">
                <h4 class="section-title">원내 지도부</h4>
                ${leadersHtml(coreLeaders, people)}
                ${additionalLeaders.length ? `<details class="elections-disclosure">
                    <summary>주요 당직 ${additionalLeaders.length}개 더 보기</summary>${leadersHtml(additionalLeaders, people)}
                </details>` : ''}
                ${senateCurrent?.leadership_url ? `<p class="elections-panel-note">${sourceLink('상원 공식 지도부 명단', senateCurrent.leadership_url)} · 확인 ${escapeHtml(senateCurrent.checked_on)}</p>` : ''}
                ${incomingHtml(chamberData?.incoming, people, today)}
            </section>
            <section class="elections-quadrant" aria-label="의석 분포">
                <h4 class="section-title">의석 분포</h4>
                ${hemicycle(groups)}
                ${seatLegend(groups)}
                <p class="elections-panel-note">재임 의원${date ? ` · 명부 ${escapeHtml(date)}` : ''}${chamber === 'house' ? ' · 표결권 기준' : ''}</p>
                ${senateCurrent?.members_url ? `<p class="elections-panel-note">${sourceLink('50개 주 상원 공식 명부', senateCurrent.members_url)} · 확인 ${escapeHtml(senateCurrent.checked_on)}</p>` : ''}
                ${allies.length ? `<p class="elections-panel-note">${allies.map((id) => nameHtml('', id, people)).join(' · ')} · 무소속이며 ${sourceLink(partyKo(caucusing.party_abbr) + ' 의원총회에 참여', caucusing.source_url)}</p>` : ''}
            </section>
        </div>
        <div class="elections-chamber-quadrants" style="margin-top:10px">
            <section class="elections-quadrant" aria-label="상임위">
                <h4 class="section-title">상임위</h4>
                ${committeePanel(chamber, committees, standingCards, people,
                    senateCurrent ? chamberData?.special_committees : null)}
            </section>
            <section class="elections-quadrant" aria-label="공석과 주요 일정">
                <h4 class="section-title">공석 · 주요 일정</h4>
                ${vacancyPanel(chamber, congress, vacancies, senateCurrent?.seats_url)}
                ${agendaPanel(chamber, agenda, today)}
            </section>
        </div>
        <div class="elections-party-card-grid" style="grid-template-columns:minmax(0,1fr)">
            ${['DEM', 'GOP', 'IND'].filter((abbr) => abbr !== 'IND' || byParty?.IND > 0).map((abbr) => partyCard(abbr, {
                chamber, members, leaders, total: byParty?.[abbr], people, groups: chamberData?.factions?.[abbr], term: rosters?.congress,
                swingSeats: (congress.swing_seats || []).filter((row) => row.chamber === chamber && row.party_abbr === abbr),
            })).join('')}
        </div>
    </div>`;
};
