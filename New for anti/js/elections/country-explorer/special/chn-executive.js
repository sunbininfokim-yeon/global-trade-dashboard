import { escapeHtml } from '../../ui.js';
import { orgBox, orgGrid, rowList, disclosure, noteLine, expandableGrid } from './org-chart.js';
import { chamberSwitch } from './chamber-switch.js';
import { personName, personLine, isFallen, statusKo } from './china.js';

// 중국 행정부 화면. 두 개의 조직도를 토글로 묶는다 -- 미국 의회 화면의 하원·상원
// 전환과 같은 장치, 같은 자리.
//
//   당·정   1 정치국 상무위원회 7인
//           2 중앙정치국
//           3 공산당 주요 직위 (3대 부장·정법위·서기처·기율위·각 판공실)
//           4 국무원
//
//   중공군  1 중앙군사위 (CMC)
//           2 전구 사령원·정치위원
//           3 군종 사령관
//           4 무장경찰 · 공안 · 정보계통
//
// 행정부만 떼어 그리면 국무원 하나가 남는데 실제 결정은 그 위 당 기구에서 나므로,
// 당 직위가 행정부 자리를 대신하고 국무원은 그 아래 단으로 내려간다.
//
// 낙마 표기 규칙: 후임 취임이 확인되지 않은 자리는 빈칸으로 두지 않고 전임자 이름에
// 삭선을 그어 남긴다 (leadership.display_rules 의 strikethrough 규칙). 자리가 비어
// 있다는 사실과 누가 어떻게 비웠는가는 다른 정보이고, 후자를 지우면 숙청이 화면에서
// 사라진다.

// 아래는 당 주요 직위 골격의 내장 사본이다. 실제 골격은
// public/data/elections_cn_party_v1.json 에 있어 코드를 건드리지 않고 칸을 더할 수
// 있고, 그 파일을 못 읽으면 이 사본으로 그린다.
let PARTY_POSTS = [
    { ko: '중앙판공청', en: 'General Office', head_title_ko: '주임', match_ko: ['중앙판공청', '판공청 주임'] },
    { ko: '중앙조직부', en: 'Organization Department', head_title_ko: '부장', match_ko: ['중앙조직부'] },
    { ko: '중앙선전부', en: 'Publicity Department', head_title_ko: '부장', match_ko: ['중앙선전부'] },
    { ko: '중앙통일전선공작부', en: 'United Front Work Department', head_title_ko: '부장', match_ko: ['중앙통전부', '통일전선'] },
    { ko: '중앙정법위원회', en: 'Political and Legal Affairs Commission', head_title_ko: '서기', match_ko: ['정법위'] },
    { ko: '중앙서기처', en: 'Central Secretariat', head_title_ko: '제1서기', match_ko: ['서기처'] },
    { ko: '중앙기율검사위원회', en: 'Central Commission for Discipline Inspection', head_title_ko: '서기', match_ko: ['중기위', '기율검사'] },
    { ko: '중앙외사공작위원회 판공실', en: 'Office of the Foreign Affairs Commission', head_title_ko: '주임', match_ko: ['외사판공실', '외교'] },
    { ko: '중앙정책연구실', en: 'Policy Research Office', head_title_ko: '주임', match_ko: ['정책연구실'] },
    { ko: '중앙재경위원회 판공실', en: 'Office of the Finance and Economy Commission', head_title_ko: '주임', match_ko: ['재경위'] },
    { ko: '중앙군민융합발전위원회 판공실', en: 'Office of the Military-Civil Fusion Commission', head_title_ko: '주임', match_ko: ['군민융합'] },
];

export const applyCnPartyChart = (chart) => {
    if (Array.isArray(chart?.party_posts) && chart.party_posts.length) PARTY_POSTS = chart.party_posts;
};

const personWithStatus = (person) => {
    if (!person) return '';
    const name = personName(person);
    if (name === '불명') return '';
    return [name, statusKo(person.status)].filter(Boolean).join(' · ');
};

// 이름 대신 "vacant_..." 가 들어 있는 행. 사람이 아니라 자리의 상태다.
const isVacant = (person) => String(person?.name_en || '').startsWith('vacant')
    || String(person?.name_ko || '').startsWith('공석');

const formerNames = (rows) => (rows || []).map((row) => personName(row)).filter((name) => name && name !== '불명');

// 박스 이름이 이미 직함을 말하고 있으면 직함 줄을 지운다 -- "부총리 / 부총리 / 허리펑"
// 처럼 같은 말이 두 번 나오면 읽는 사람이 둘을 다른 정보로 착각한다.
const shortTitle = (boxKo, title) => (!title || String(boxKo).includes(title) ? '' : title);

// ---------------------------------------------------------------- 당·정 -----

const pscBoxes = (standing) => (standing.rank_order || []).map((row, index) => orgBox({
    abbr: `서열 ${index + 1}`,
    ko: row.role_ko || row.title_ko || '상무위원',
    title: shortTitle(row.role_ko || row.title_ko, row.title_ko),
    person: personWithStatus(row),
    strike: isFallen(row),
}));

// 정치국은 상무위 7인을 포함한다. 같은 사람을 두 단에 두 번 그리면 인원이 부풀려
// 보이므로 이 단에는 상무위에 없는 위원만 세고, 그중 명부 앞 7인만 박스로 낸다.
// 나머지는 박스를 누르면 그 아래로 펼쳐진다 -- 21개 박스를 한 번에 늘어놓으면
// 상무위 7인 단과 무게가 같아 보여 두 단의 층위가 사라진다.
const POLITBURO_HEADLINE = 7;

const politburoMembers = (politburo, standing) => {
    const pscNames = new Set(formerNames(standing.rank_order));
    return (politburo.active || []).filter((row) => !pscNames.has(personName(row)));
};

const politburoBox = (row) => orgBox({
    ko: row.role_ko || row.title_ko || '정치국 위원',
    title: shortTitle(row.role_ko || row.title_ko, row.title_ko),
    person: personWithStatus(row),
    strike: isFallen(row),
});

// 펼쳐진 명부는 상무위원까지 포함한 정치국 전원이다 -- "전 인원"이 상무위를 빼고
// 센 수라면 그건 정치국 명부가 아니다. 어느 쪽이 상무위원인지는 줄마다 적는다.
const politburoRoster = (politburo, standing) => {
    const psc = standing.rank_order || [];
    const pscNames = new Set(formerNames(psc));
    const rows = [
        ...psc.map((row, index) => ({ row, mark: `상무위 서열 ${index + 1}` })),
        ...(politburo.active || [])
            .filter((member) => !pscNames.has(personName(member)))
            .map((row) => ({ row, mark: '정치국 위원' })),
    ];
    return rows.map(({ row, mark }) => `<div>
        <span>${escapeHtml(row.role_ko || row.title_ko || mark)}</span>
        <strong class="${isFallen(row) ? 'elections-fallen' : ''}">${escapeHtml(personWithStatus(row) || '불명')}</strong>
        <em class="elections-person-mark">${escapeHtml(mark)}</em>
    </div>`);
};

// 골격의 match_ko 키워드로 leadership 안의 사람을 찾는다. 파일이 직접 사람을 들고
// 있으면(name_ko/name_en) 그쪽이 우선이고, 아무것도 못 찾으면 '명단 수집 예정' --
// 공석이라는 뜻이 아니다.
const partyPostBoxes = (leadership) => {
    const partyState = leadership.party_state || {};
    const organs = leadership.security_organs || {};
    const pool = [
        ...(partyState.politburo_standing_committee?.rank_order || []),
        ...(partyState.politburo?.active || []),
        ...Object.values(partyState.central_departments || {})
            .filter((value) => value && typeof value === 'object' && value.minister)
            .map((value) => ({ ...value.minister, role_ko: value.minister.role_ko || value.title_ko })),
        ...Object.values(organs).filter((value) => value && typeof value === 'object' && (value.name_ko || value.name_en)),
    ];
    return PARTY_POSTS.map((post) => {
        const supplied = post.name_ko || post.name_en ? post : null;
        const match = supplied || pool.find((row) => (post.match_ko || [])
            .some((needle) => String(row.role_ko || row.title_ko || '').includes(needle)));
        return orgBox({
            ko: post.ko,
            en: post.en,
            title: post.head_title_ko || match?.title_ko,
            person: personWithStatus(match),
            strike: isFallen(match),
            note: match?.note_ko || match?.note,
        });
    });
};

// 국무원 단은 부총리급까지만 박스로 낸다. 부처는 박스를 누르면 그 아래로 펼쳐진다.
const stateCouncilBoxes = (leadership) => {
    const council = leadership.party_state?.state_council || {};
    return [
        orgBox({ ko: '국무원 총리', person: personWithStatus(council.premier) }),
        ...(council.vice_premiers || []).map((row, index) => orgBox({
            ko: index === 0 ? '상무부총리' : '부총리',
            title: shortTitle(index === 0 ? '상무부총리' : '부총리', row.title_ko),
            person: personWithStatus(row),
            strike: isFallen(row),
        })),
    ];
};

// 확보된 부처장은 셋뿐이다 (국방·공안·국가안전). 나머지 부처를 빈 줄로 만들어
// 채우지 않고, 몇 개를 들고 있는지와 전체 명부가 미수집이라는 사실만 적는다.
const ministerRows = (leadership) => {
    const cmc = leadership.cmc || {};
    const organs = leadership.security_organs || {};
    const entries = [
        ['국방부', cmc.defense_minister, cmc.defense_minister?.on_cmc === false ? '중앙군사위 위원 아님' : ''],
        ['공안부', organs.ministry_of_public_security, ''],
        ['국가안전부', organs.ministry_of_state_security, ''],
    ];
    return entries.filter(([, person]) => person).map(([ko, person, mark]) => `<div>
        <span>${escapeHtml(`${ko}${person.title_ko ? ` · ${person.title_ko}` : ''}`)}</span>
        <strong class="${isFallen(person) ? 'elections-fallen' : ''}">${escapeHtml(personWithStatus(person) || '불명')}</strong>
        ${mark ? `<em class="elections-person-mark">${escapeHtml(mark)}</em>` : ''}
    </div>`);
};

// ---------------------------------------------------------------- 중공군 ----

// 중앙군사위. 현직 2인 뒤에, 후임이 확인되지 않은 자리를 전임자 이름에 삭선을 그어
// 남긴다 -- 요청대로 "새로 취임 확인 안 되면 이름에 줄 그어 낙마 표기".
const cmcBoxes = (leadership) => {
    const cmc = leadership.cmc || {};
    const boxes = (cmc.active_core || []).map((row) => orgBox({
        abbr: 'CMC',
        ko: row.role_ko || row.title_ko || '중앙군사위',
        person: personWithStatus(row),
        note: [row.since ? `${row.since} 취임` : '', row.note].filter(Boolean).join(' · '),
    }));
    // cmc.fallen 에는 중앙군사위 자리가 아닌 사람도 섞여 있다 (린샹양은 동부전구
    // 사령관이었다). 전구·군종 자리는 아래 단에 자기 박스가 있으므로 여기서 빼고,
    // 그쪽 박스의 '전임' 줄에서만 삭선으로 남긴다 -- 두 곳에 그리면 중앙군사위가
    // 실제보다 많이 비어 있는 것처럼 보인다.
    const cmcSeat = (row) => !/전구|군종|육군|해군|공군|로켓군|무장경찰/.test(String(row.role_ko || ''));
    (cmc.fallen || []).filter(cmcSeat).forEach((row) => boxes.push(orgBox({
        abbr: 'CMC',
        ko: String(row.role_ko || '중앙군사위 위원').replace(/\(구\)$/, ''),
        title: '후임 미확인',
        person: personName(row),
        strike: true,
        note: statusKo(row.status),
    })));
    return boxes;
};

// 전구는 사령원과 정치위원이 한 쌍이라 한 박스에 둘을 같이 둔다. 둘 중 하나만
// 낙마한 경우가 있어(서부전구 정치위원) 삭선은 줄 단위로 건다.
const theaterBoxes = (leadership) => (leadership.theater_commands || []).map((theater) => {
    const commissar = theater.political_commissar;
    return orgBox({
        ko: theater.name_ko || '전구',
        title: theater.commander?.title_ko || '사령원',
        person: personWithStatus(theater.commander),
        strike: isFallen(theater.commander),
        commissarTitle: '정치위원',
        commissar: personWithStatus(commissar),
        commissarStrike: isFallen(commissar),
        former: formerNames(theater.fallen),
        note: theater.commander?.since ? `사령원 ${theater.commander.since} 취임` : '',
    });
});

// 군종. 무장경찰은 요청대로 군종이 아니라 아래 치안·정보 단으로 내린다.
const BRANCH_ORDER = ['army', 'navy', 'air_force', 'rocket_force'];
const branchBoxes = (leadership) => {
    const branches = leadership.service_branches || {};
    return BRANCH_ORDER.filter((key) => branches[key]).map((key) => {
        const branch = branches[key];
        return orgBox({
            ko: branch.name_ko || key,
            title: branch.commander?.title_ko || '사령원',
            person: isVacant(branch.commander) ? personName(branch.commander) : personWithStatus(branch.commander),
            vacant: isVacant(branch.commander),
            strike: isFallen(branch.commander),
            commissarTitle: '정치위원',
            commissar: personWithStatus(branch.political_commissar),
            commissarStrike: isFallen(branch.political_commissar),
            former: formerNames(branch.fallen_commanders),
            note: [
                branch.commander?.note,
                branch.alt_reported ? `다른 보도 ${personName(branch.alt_reported)} (공식 미확인)` : '',
            ].filter(Boolean).join(' · '),
        });
    });
};

// 전투경찰(무장경찰) · 공안 · 정보계통. 군 지휘계통은 아니지만 같은 무장·정보 축이라
// 군 조직도 아래 단에 둔다.
const SECURITY_BOXES = [
    { key: 'central_political_and_legal_affairs_commission', ko: '중앙정법위원회', en: 'Political and Legal Affairs Commission' },
    { key: 'ministry_of_public_security', ko: '공안부', en: 'Ministry of Public Security' },
    { key: 'ministry_of_state_security', ko: '국가안전부 (정보)', en: 'Ministry of State Security' },
];
const securityBoxes = (leadership) => {
    const armedPolice = leadership.service_branches?.armed_police;
    const organs = leadership.security_organs || {};
    const boxes = [];
    if (armedPolice) {
        boxes.push(orgBox({
            ko: `${armedPolice.name_ko || '무장경찰'} (전투경찰)`,
            title: armedPolice.commander?.title_ko || '사령원',
            person: isVacant(armedPolice.commander) ? personName(armedPolice.commander) : personWithStatus(armedPolice.commander),
            vacant: isVacant(armedPolice.commander),
            former: formerNames(armedPolice.fallen_commanders),
            note: armedPolice.commander?.note,
        }));
    }
    SECURITY_BOXES.forEach(({ key, ko, en }) => {
        const organ = organs[key];
        if (!organ) return;
        boxes.push(orgBox({
            ko, en,
            title: organ.title_ko || '책임자',
            person: personWithStatus(organ),
            strike: isFallen(organ),
            // also_hidden 은 같은 사람이 겸하는 다른 자리다. 이 체제에서 겸직은
            // 부가 정보가 아니라 그 사람의 실제 위치라서 지우지 않는다.
            note: [organ.note, (organ.also_hidden || []).length ? `겸직 ${organ.also_hidden.join(' · ')}` : '']
                .filter(Boolean).join(' · '),
        }));
    });
    return boxes;
};

// ------------------------------------------------------------------ 화면 ----

const partyPanel = (leadership) => {
    const partyState = leadership.party_state || {};
    const standing = partyState.politburo_standing_committee || {};
    const politburo = partyState.politburo || {};
    const nonPsc = politburoMembers(politburo, standing);
    const roster = politburoRoster(politburo, standing);
    const ministers = ministerRows(leadership);
    return `
        <p class="section-title">1 · 정치국 상무위원회 ${standing.n ? `${standing.n}인` : ''}</p>
        ${orgGrid(pscBoxes(standing))}
        ${noteLine(standing.source ? `서열은 공식 발표 순서입니다 · 출처 ${standing.source}` : '서열은 공식 발표 순서입니다.')}

        <p class="section-title">2 · 중앙정치국 ${politburo.active_n_approx ? `현원 약 ${politburo.active_n_approx}인` : ''}</p>
        ${nonPsc.length ? expandableGrid({
        boxes: nonPsc.slice(0, POLITBURO_HEADLINE).map(politburoBox),
        hint: `명부 순서 앞 ${Math.min(POLITBURO_HEADLINE, nonPsc.length)}인 · 박스를 누르면 정치국 전원 ${roster.length}인`,
        body: `${rowList(roster)}
            ${noteLine(`상무위원 ${standing.n || 0}인을 포함한 정치국 전원입니다. 위 박스는 상무위원을 뺀 명부의 앞 ${POLITBURO_HEADLINE}인이며, 순서는 공개 명부 순서일 뿐 서열 판정이 아닙니다.`)}
            ${politburo.fallen?.length ? `<p class="elections-party-card-label">실각·조사 ${politburo.fallen.length}인 · 현원에서 빠짐</p>
            ${rowList((politburo.fallen || []).map((row) => personLine(row, row.was)))}` : ''}`,
    }) : '<p class="elections-muted">확보된 정치국 명부가 없습니다.</p>'}
        ${noteLine(politburo.note_ko)}

        <p class="section-title">3 · 공산당 주요 직위</p>
        ${orgGrid(partyPostBoxes(leadership))}
        ${noteLine('사람이 비어 있는 칸은 명단 미수집이며, 그 자리가 공석이라는 뜻이 아닙니다.')}

        <p class="section-title">4 · 국무원</p>
        ${ministers.length ? expandableGrid({
        boxes: stateCouncilBoxes(leadership),
        hint: `부총리급까지 · 박스를 누르면 부처장 ${ministers.length}인`,
        body: `${rowList(ministers)}
            ${noteLine('확보된 부처장만 표시합니다. 국무원 전체 부처 명부는 아직 수집 대상이 아니며, 여기 없는 부처가 공석이라는 뜻이 아닙니다.')}`,
    }) : orgGrid(stateCouncilBoxes(leadership))}
        ${noteLine('국무원을 당 기구 아래 둔 것은 서열이 아니라 의사결정 순서를 따른 것입니다.')}
    `;
};

const militaryPanel = (leadership) => {
    const cmc = leadership.cmc || {};
    const branches = leadership.service_branches || {};
    return `
        <p class="section-title">1 · 중앙군사위원회</p>
        ${orgGrid(cmcBoxes(leadership))}
        ${noteLine(cmc.notes_ko)}
        ${cmc.defense_minister && cmc.defense_minister.on_cmc === false ? noteLine(`국방부장 ${personName(cmc.defense_minister)} — 중앙군사위 위원이 아닌 국무원 부처장입니다.`) : ''}
        ${noteLine('삭선 + "후임 미확인"은 그 자리의 전임자가 실각·조사로 물러났고 새 취임이 확인되지 않았다는 뜻입니다.')}

        <p class="section-title">2 · 전구 사령원 · 정치위원</p>
        ${orgGrid(theaterBoxes(leadership))}

        <p class="section-title">3 · 군종 사령원</p>
        ${orgGrid(branchBoxes(leadership))}
        ${noteLine(branches.note_ko)}

        <p class="section-title">4 · 전투경찰 · 공안 · 정보계통</p>
        ${orgGrid(securityBoxes(leadership))}
        ${noteLine(leadership.security_organs?.note_ko)}
        ${noteLine('무장경찰은 군종이 아니라 중앙군사위 직속 무장 조직이고, 공안·국가안전은 국무원 부처입니다. 지휘계통이 다르므로 같은 단에 두되 한 계통으로 읽지 마십시오.')}
    `;
};

export const chnExecutive = (country) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    const cmc = leadership.cmc || {};
    const politburo = leadership.party_state?.politburo || {};

    // 정치국과 중앙군사위 명부에 같은 사람이 두 번 나온다 (허웨이둥·장유샤는 둘 다
    // 겸직이었다). 두 줄로 세면 실각 인원이 부풀려지므로 이름으로 한 번만 센다.
    const fallen = new Map();
    (politburo.fallen || []).forEach((row) => fallen.set(personName(row), personLine(row, row.was)));
    (cmc.fallen || []).forEach((row) => {
        const key = personName(row);
        if (!fallen.has(key)) fallen.set(key, personLine(row, row.role_ko));
    });
    const fallenRows = [...fallen.values()];

    return `
        ${chamberSwitch([
        { label: '당 · 정', panel: partyPanel(leadership) },
        { label: '중공군', panel: militaryPanel(leadership) },
    ])}
        ${disclosure(`실각·조사 ${fallenRows.length}인 · 전체`, fallenRows)}
        ${noteLine(leadership.as_of ? `명부 기준일 ${leadership.as_of} · 갱신 주기 ${leadership.review_cadence || '불명'}` : '')}
        <p class="elections-panel-note">한 사람이 당·국가·군의 여러 자리를 겸합니다. 두 조직도에 같은 이름이 나오는 것은 중복이 아니라 겸직입니다.</p>
    `;
};
