import { escapeHtml, formatDate, personLinkHtml } from '../../ui.js';
import { seatLegend } from './hemicycle.js';

const PARTIES = {
    DEM: { label: '민주당', color: '#2563eb' },
    GOP: { label: '공화당', color: '#dc2626' },
    IND: { label: '무소속', color: '#94a3b8' },
    NPP: { label: '정당 선호 없음', color: '#94a3b8' },
    NP: { label: '비당파 선거', color: '#94a3b8' },
    LIB: { label: '자유당', color: '#eab308' },
    GRN: { label: '녹색당', color: '#16a34a' },
    pending: { label: '승자 미발표', color: '#64748b' },
};
const STATUS = {
    certified: '주정부 인증',
    reported_winner: '공개 출처 승자 발표',
    count_leader: '주정부 개표 선두',
    result_unverified: '결과 확인 중',
};
const link = (label, url) => personLinkHtml(escapeHtml(label), /^https:\/\//i.test(url || '') ? url : '');
const isWinner = (row) => row?.name && ['certified', 'reported_winner'].includes(row.result_status);
const legend = (counts) => seatLegend(Object.entries(PARTIES).filter(([key]) => counts[key])
    .map(([key, party]) => ({ ...party, count: counts[key] })));
const countParties = (rows, partyFor) => {
    const counts = {};
    for (const row of rows) {
        const key = partyFor(row) || 'pending';
        counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
};

const federalCard = (race) => `<article class="elections-quadrant">
    <h4 class="section-title">${escapeHtml(race.label_ko)} · 선거 ${escapeHtml(race.seats)}석</h4>
    ${legend(race.wins)}
    ${race.non_election ? `<p class="elections-party-card-label">비선거 ${escapeHtml(race.non_election.seats)}석</p>
        ${legend(race.non_election.parties)}` : ''}
    ${race.composition ? `<p class="elections-party-card-label">선거 후 전체 ${escapeHtml(race.composition.total)}석</p>
        ${legend(race.composition.seats)}` : ''}
    ${race.note_ko ? `<p class="elections-panel-note">${escapeHtml(race.note_ko)}</p>` : ''}
    <p class="elections-panel-note">${link('전국 결과와 지역별 명단', race.source_url)}</p>
</article>`;

const governorCard = (rows, source = {}) => {
    if (!rows.length) return '<article class="elections-quadrant"><h4 class="section-title">주지사</h4><p class="elections-muted">전국 주지사 결과를 불러오지 못했습니다.</p></article>';
    const races = rows.filter((row) => row.transition);
    const outcome = (row) => isWinner(row.transition) ? row.transition.party : null;
    return `<article class="elections-quadrant">
        <h4 class="section-title">주지사 · 선거 ${races.length}곳</h4>
        ${legend(countParties(races, outcome))}
        <p class="elections-party-card-label">취임 후 예상 · ${rows.length}개 주</p>
        ${legend(countParties(rows, (row) => row.transition ? outcome(row) : row.party))}
        <p class="elections-panel-note">현재 재임 중인 주지사는 아래 주별 카드에서 확인할 수 있습니다. ${link('전국 주지사 결과', source.results_url)}</p>
    </article>`;
};

const officesFor = (data, governor) => {
    const state = data.states[governor.state] || {};
    const { transition } = governor;
    const records = state.offices || [];
    if (!transition) return records;
    const local = records.find((row) => row.office === 'governor');
    const matched = local?.name === transition.name && local.party === transition.party ? local : null;
    const certified = transition.result_status === 'certified';
    return [{
        ...transition,
        office: 'governor',
        group: 'executive',
        ...matched,
        ...(certified ? { result_status: transition.result_status, result_url: transition.result_url } : {}),
    }, ...records.filter((row) => row.office !== 'governor')];
};

const profileField = (label, field) => `${label} ${field?.value && field.source_url
    ? link(field.value, field.source_url) : '미확인'}`;
const voteFormat = new Intl.NumberFormat('ko-KR');

const officeRow = (row, data) => {
    const office = data.offices[row.office] || {};
    const profile = row.profile || {};
    const resultUrl = row.result_url;
    const partyLabel = PARTIES[row.party]?.label || row.party || '정당 미확인';
    return `<article class="elections-card usa-results-office">
        <p class="elections-card-label">${escapeHtml(office.label_ko || row.office)}${row.district ? ` · ${escapeHtml(row.district)}` : ''}</p>
        <h5>${link(row.name || '결과 확인 중', profile.source_url || resultUrl)}
            ${row.name ? `<span class="usa-results-party">${PARTIES[row.party] ? `<i class="elections-party-dot" aria-hidden="true" style="background:${PARTIES[row.party].color}"></i>` : ''}${escapeHtml(partyLabel)}</span>` : ''}</h5>
        ${office.role_ko ? `<p class="elections-muted">${escapeHtml(office.label_en)} · ${escapeHtml(office.role_ko)}</p>` : ''}
        <p class="elections-panel-note">${link(STATUS[row.result_status] || STATUS.result_unverified, resultUrl)}
            ${row.selection === 'joint_ticket' ? ' · 주지사와 공동 후보' : ''}
            ${row.selection === 'outright_primary' ? ` · ${escapeHtml(formatDate(row.election_date))} 예비선거에서 당선` : ''}
            ${row.unopposed ? ' · 무경쟁' : ''}
            ${Number.isInteger(row.votes) ? ` · ${voteFormat.format(row.votes)}표 (${link(row.vote_as_of ? `${formatDate(row.vote_as_of)} 개표 원문` : '개표 원문', row.vote_url || resultUrl)})` : ''}
        </p>
        ${row.name ? `<p class="elections-muted">주요 약력 ${profile.career_ko && profile.source_url
            ? link(profile.career_ko, profile.source_url) : '미확인'}</p>
            <p class="elections-muted">${profileField('성별', profile.gender)} · ${profileField('인종·민족', profile.race_ethnicity)}</p>` : ''}
    </article>`;
};

const statePanel = (governor, data) => {
    const state = data.states[governor.state] || {};
    const records = officesFor(data, governor);
    const executive = records.filter((row) => row.group === 'executive');
    const boards = records.filter((row) => row.group === 'board');
    const courts = records.filter((row) => row.group === 'judicial');
    const cards = (rows) => rows.map((row) => officeRow(row, data)).join('');
    const details = (rows, label) => rows.length ? `<details class="elections-disclosure">
        <summary>${label} ${rows.length}석</summary><div class="usa-results-offices">${cards(rows)}</div></details>` : '';
    return `<article class="elections-party-card">
        <header class="elections-party-card-head"><h4>${escapeHtml(governor.state_ko)} · ${escapeHtml(governor.state)}</h4>
            <span>${state.coverage === 'ballot_reviewed' ? '주 공시 확인' : '확보된 자료 기준'}</span></header>
        <p class="elections-muted">현직 주지사 ${link(governor.name, governor.office_url)} · ${escapeHtml(PARTIES[governor.party]?.label || '정당 미확인')}${governor.transition ? '' : ' · 2026년 주지사 선거 없음'}</p>
        ${executive.length ? `<div class="usa-results-offices">${cards(executive)}</div>` : ''}
        ${details(boards, '주 위원회·교육기관')}
        ${details(courts, '주 최고법원·형사항소법원')}
        ${!records.length ? '<p class="elections-muted">전국 집계에 이 주의 2026년 주 행정부 선출직 선거가 없습니다.</p>' : ''}
        ${state.note_ko ? `<p class="elections-panel-note">${link(state.note_ko, state.note_url)}</p>` : ''}
        <p class="elections-panel-note">${state.official_url ? link('주정부 개표 원문', state.official_url) : link('전국 주별 선거 결과 목록', data.sources.state_directory)}</p>
    </article>`;
};

export const usaElectionResults = (data, governors) => {
    if (!data) return '<p class="elections-muted">2026년 선거 결과를 불러오지 못했습니다.</p>';
    const rows = governors?.states || [];
    const initial = rows.find((row) => row.state === 'TX') || rows[0];
    const counts = rows.map((row) => officesFor(data, row).filter((office) => office.group !== 'judicial'));
    const covered = counts.filter((offices) => offices.length).length;
    const offices = counts.flat();
    const confirmed = offices.filter(isWinner).length;
    return `<div class="usa-results" data-usa-election-results>
        <p class="elections-panel-note">${escapeHtml(formatDate(data.election_date))} 중간선거 · ${escapeHtml(data.as_of)} 확인</p>
        <div class="usa-results-summary">
            ${federalCard(data.federal.senate)}
            ${federalCard(data.federal.house)}
            ${governorCard(rows, governors?.sources)}
        </div>
        ${initial ? `<section class="usa-results-state" aria-labelledby="usa-results-state-title">
            <h4 id="usa-results-state-title" class="section-title">주별 선출직 결과</h4>
            <p class="elections-panel-note">${covered}개 주 · 행정부·위원회 ${offices.length}석 · 승자 확인 ${confirmed}석 · ${link('전국 주 선출직 선거 범위', data.sources.scope)}</p>
            <label for="usa-results-state-select">주 선택</label>
            <select id="usa-results-state-select" data-usa-results-state-select>${rows.map((row) =>
                `<option value="${escapeHtml(row.state)}"${row.state === initial.state ? ' selected' : ''}>${escapeHtml(row.state_ko)} · ${escapeHtml(row.state)}</option>`).join('')}</select>
            <div data-usa-results-state-panel>${statePanel(initial, data)}</div>
        </section>` : '<p class="elections-muted">주별 명부를 불러오지 못했습니다.</p>'}
    </div>`;
};

export const mountUsaElectionResults = (root, data, governors) => {
    if (!root) return;
    const document = root.ownerDocument;
    if (!document.querySelector('#usa-election-results-css')) {
        const style = document.createElement('link');
        style.id = 'usa-election-results-css';
        style.rel = 'stylesheet';
        style.href = new URL('./usa-election-results.css', import.meta.url).href;
        document.head.append(style);
    }
    const select = root.querySelector('[data-usa-results-state-select]');
    const panel = root.querySelector('[data-usa-results-state-panel]');
    select?.addEventListener('change', () => {
        const row = governors.states.find(({ state }) => state === select.value);
        if (row) panel.innerHTML = statePanel(row, data);
    });
};
