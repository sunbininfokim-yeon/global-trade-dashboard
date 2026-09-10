import { escapeHtml } from '../../ui.js';
import { card, rowList, disclosure, noteLine } from './org-chart.js';

// The manifest declares CHN's screens as party / state_council / military, not
// the generic executive/power_structure pair.  Pointing two tabs at one key
// made 공산당 and 군 render the same block and light up together, and the
// 국무원 tab inherited executive's `disabled` status even though
// leadership.party_state.state_council is populated.
// 행정부 탭이 앞에 붙는다: 당·국가·군을 한 장의 조직도로 보여 주는 화면이고,
// 뒤의 세 탭은 그 각 단의 전체 명부다 (조직도는 책임자만, 탭은 명단 전부).
export const chinaSections = [
    ['행정부', 'executive'],
    ['공산당', 'party'],
    ['국무원', 'state_council'],
    ['군', 'military'],
];

// `_internal` carries the pipeline's private faction tags; display_rules says
// they stay out of the UI.  Reading only the fields named here keeps them out
// by construction rather than by remembering to strip them.
export const personName = (person) => person?.name_ko || person?.name_en || '불명';

// status 는 파이프라인의 토큰(expelled_2025-10, investigating_2026-01_de_facto_fallen
// ...)이라 화면에 그대로 나오면 한국어 화면에 영문 코드가 박힌다. 동사만 옮기고
// 날짜는 원문 그대로 둔다 -- 날짜를 고쳐 쓰면 그게 새로운 주장이 된다. 표에 없는
// 코드는 번역하지 않고 그대로 보여, 새 코드가 조용히 사라지지 않게 한다.
const STATUS_VERBS = [
    ['acting_or_provisional', () => '대리·잠정'],
    ['expelled_', (rest) => `제명 ${rest}`],
    ['investigating_', (rest) => `조사 중 ${rest.replace('_de_facto_fallen', '')} · 사실상 실각`],
    ['likely_removed_', (rest) => `해임 추정 ${rest}`],
    ['removed_sentenced_death_reprieve_', (rest) => `해임 · 사형집행유예 선고 ${rest}`],
];
export const statusKo = (status) => {
    if (!status || status === 'incumbent') return '';
    const hit = STATUS_VERBS.find(([prefix]) => status === prefix || status.startsWith(prefix));
    return hit ? hit[1](status.slice(hit[0].length)) : status;
};
export const isFallen = (person) => person?.fallen === true || person?.display === 'strikethrough';

export const personLine = (person, fallbackTitle = '') => {
    if (!person) return '<div><span>직책</span><strong>불명</strong></div>';
    const title = person.title_ko || person.role_ko || fallbackTitle || '직책';
    const name = escapeHtml(personName(person));
    const marks = [statusKo(person.status), person.confidence ? `신뢰도 ${person.confidence}` : '']
        .filter(Boolean).map((mark) => escapeHtml(mark)).join(' · ');
    return `<div>
        <span>${escapeHtml(title)}</span>
        <strong class="${isFallen(person) ? 'elections-fallen' : ''}">${name}</strong>
        ${marks ? `<em class="elections-person-mark">${marks}</em>` : ''}
    </div>`;
};

const partyScreen = (leadership) => {
    const partyState = leadership.party_state || {};
    const secretary = partyState.general_secretary;
    const standing = partyState.politburo_standing_committee || {};
    const politburo = partyState.politburo || {};
    const departments = partyState.central_departments || {};
    const departmentRows = Object.entries(departments)
        .filter(([, value]) => value && typeof value === 'object' && value.minister)
        .map(([, value]) => personLine(value.minister, value.title_ko));

    return `
        <div class="elections-card-grid">
            ${card('총서기', personName(secretary), [statusKo(secretary?.status), secretary?.confidence && `신뢰도 ${secretary.confidence}`].filter(Boolean).join(' · '))}
            ${card('정치국 상무위원회', standing.n ? `${standing.n}인` : '불명', standing.source || '')}
            ${card('정치국', politburo.active_n_approx ? `현원 약 ${politburo.active_n_approx}인` : '불명', politburo.original_n_20th ? `20차 원구성 ${politburo.original_n_20th}인` : '')}
        </div>
        ${disclosure(`정치국 상무위원 ${(standing.rank_order || []).length}인 · 서열 순`, (standing.rank_order || []).map((row) => personLine(row)))}
        ${disclosure(`중앙 핵심 부서 ${departmentRows.length}곳`, departmentRows)}
        ${disclosure(`정치국 실각·조사 ${(politburo.fallen || []).length}인`, (politburo.fallen || []).map((row) => personLine(row, row.was)))}
        ${noteLine(politburo.note_ko)}
        ${noteLine(departments.note_ko)}
    `;
};

const stateCouncilScreen = (leadership) => {
    const council = leadership.party_state?.state_council;
    if (!council) return '<p class="elections-muted">확보된 공개 국무원 명부가 없습니다.</p>';
    const vicePremiers = council.vice_premiers || [];
    return `
        <div class="elections-card-grid">
            ${card('국무원 총리', personName(council.premier))}
            ${card('부총리', vicePremiers.length ? `${vicePremiers.length}인` : '불명')}
        </div>
        ${disclosure(`부총리 ${vicePremiers.length}인 보기`, vicePremiers.map((row) => personLine(row, '부총리')))}
        <p class="elections-panel-note">전국인민대표대회 화면은 데이터 계약상 만들지 않습니다.</p>
    `;
};

const militaryScreen = (leadership) => {
    const cmc = leadership.cmc || {};
    const branches = leadership.service_branches || {};
    const theaters = leadership.theater_commands || [];
    const organs = leadership.security_organs || {};

    const branchRows = Object.entries(branches)
        .filter(([, value]) => value && typeof value === 'object' && (value.commander || value.political_commissar))
        .flatMap(([, value]) => [
            personLine(value.commander, `${value.name_ko || '군종'} 사령`),
            personLine(value.political_commissar, `${value.name_ko || '군종'} 정치위원`),
        ]);
    const theaterRows = theaters.flatMap((theater) => [
        personLine(theater.commander, `${theater.name_ko || '전구'} 사령관`),
        personLine(theater.political_commissar, `${theater.name_ko || '전구'} 정치위원`),
    ]);
    const organRows = Object.entries(organs)
        .filter(([, value]) => value && typeof value === 'object' && (value.name_ko || value.name_en))
        .map(([, value]) => personLine(value));

    return `
        <div class="elections-card-grid">
            ${card('중앙군사위 활성 핵심', (cmc.active_core || []).length ? `${cmc.active_core.length}인` : '불명')}
            ${card('국방부장', personName(cmc.defense_minister), cmc.defense_minister?.on_cmc === false ? '중앙군사위 위원 아님' : '')}
            ${card('전구', theaters.length ? `${theaters.length}대 전구` : '불명')}
        </div>
        ${disclosure(`중앙군사위 ${(cmc.active_core || []).length}인`, (cmc.active_core || []).map((row) => personLine(row)))}
        ${disclosure(`중앙군사위 실각·조사 ${(cmc.fallen || []).length}인`, (cmc.fallen || []).map((row) => personLine(row)))}
        ${disclosure(`군종 사령·정치위원 ${branchRows.length}건`, branchRows)}
        ${disclosure(`전구 사령관·정치위원 ${theaterRows.length}건`, theaterRows)}
        ${disclosure(`공안·국가안전 축 ${organRows.length}건`, organRows)}
        ${noteLine(cmc.notes_ko)}
        ${noteLine(branches.note_ko)}
        ${noteLine(organs.note_ko)}
    `;
};

export const chinaContent = (country, section) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    if (section === 'party') return partyScreen(leadership);
    if (section === 'state_council') return stateCouncilScreen(leadership);
    if (section === 'military') return militaryScreen(leadership);
    return null;
};
