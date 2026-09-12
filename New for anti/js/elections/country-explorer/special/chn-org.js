import { escapeHtml } from '../../ui.js';
import { orgBox, orgGrid, rowList, disclosure, noteLine, expandableGrid } from './org-chart.js';
import { personName, personLine, isFallen, statusKo } from './china.js';

// 중국 우측 대시보드의 세 화면 -- 공산당 / 군부 / 국무원. 셋 다 미국 행정부 화면과
// 같은 조직도(단 + 박스 격자)이고, 블록을 누르면 그 조직도가 뜬다. 미국이 행정부 ·
// 상원·하원 · 정당·계파를 각각의 블록으로 여는 것과 같은 구조다.
//
//   공산당   1 정치국 상무위원회 7인
//            2 중앙정치국 (앞 7인 · 눌러서 전원)
//            3 공산당 주요 직위 (3대 부장·정법위·서기처·기율위·각 판공실)
//
//   군부     1 중앙군사위 (CMC)
//            2 전구 사령원·정치위원
//            3 군종 사령원
//            4 전투경찰 · 공안 · 정보계통
//
//   국무원   1 총리
//            2 부총리 (눌러서 부처장)
//
// 낙마 표기 규칙: 후임 취임이 확인되지 않은 자리는 빈칸으로 두지 않고 전임자 이름에
// 삭선을 그어 남긴다 (leadership.display_rules 의 strikethrough 규칙). 자리가 비어
// 있다는 사실과 누가 어떻게 비웠는가는 다른 정보이고, 후자를 지우면 숙청이 화면에서
// 사라진다.
//
// 세 화면에 같은 이름이 나오는 것은 중복이 아니라 겸직이다 -- 이 체제에서는 그것이
// 구조 자체라서 감추지 않고, 대신 어느 자리로 거기 있는지를 박스마다 적는다.

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

// 국무원 구성 부문의 내장 사본. 같은 골격이 elections_cn_party_v1.json 에 있고,
// 그 파일을 못 읽을 때만 이쪽이 그려진다.
let MINISTRIES = [
    { ko: "외교부", en: "Ministry of Foreign Affairs", head_title_ko: "부장", match_ko: ["외교부장"] },
    { ko: "국방부", en: "Ministry of National Defense", head_title_ko: "부장", match_ko: ["국방부장"] },
    { ko: "국가발전개혁위원회", en: "National Development and Reform Commission", head_title_ko: "주임", match_ko: ["발전개혁", "발개위"] },
    { ko: "교육부", en: "Ministry of Education", head_title_ko: "부장", match_ko: ["교육부장"] },
    { ko: "과학기술부", en: "Ministry of Science and Technology", head_title_ko: "부장", match_ko: ["과학기술부장"] },
    { ko: "공업정보화부", en: "Ministry of Industry and Information Technology", head_title_ko: "부장", match_ko: ["공업정보화"] },
    { ko: "국가민족사무위원회", en: "National Ethnic Affairs Commission", head_title_ko: "주임", match_ko: ["민족사무"] },
    { ko: "공안부", en: "Ministry of Public Security", head_title_ko: "부장", match_ko: ["공안부장"] },
    { ko: "국가안전부", en: "Ministry of State Security", head_title_ko: "부장", match_ko: ["국가안전부장"] },
    { ko: "민정부", en: "Ministry of Civil Affairs", head_title_ko: "부장", match_ko: ["민정부장"] },
    { ko: "사법부", en: "Ministry of Justice", head_title_ko: "부장", match_ko: ["사법부장"] },
    { ko: "재정부", en: "Ministry of Finance", head_title_ko: "부장", match_ko: ["재정부장"] },
    { ko: "인력자원사회보장부", en: "Ministry of Human Resources and Social Security", head_title_ko: "부장", match_ko: ["인력자원"] },
    { ko: "자연자원부", en: "Ministry of Natural Resources", head_title_ko: "부장", match_ko: ["자연자원"] },
    { ko: "생태환경부", en: "Ministry of Ecology and Environment", head_title_ko: "부장", match_ko: ["생태환경", "환경부장"] },
    { ko: "주택도농건설부", en: "Ministry of Housing and Urban-Rural Development", head_title_ko: "부장", match_ko: ["주택도농"] },
    { ko: "교통운수부", en: "Ministry of Transport", head_title_ko: "부장", match_ko: ["교통운수"] },
    { ko: "수리부", en: "Ministry of Water Resources", head_title_ko: "부장", match_ko: ["수리부장"] },
    { ko: "농업농촌부", en: "Ministry of Agriculture and Rural Affairs", head_title_ko: "부장", match_ko: ["농업농촌"] },
    { ko: "상무부", en: "Ministry of Commerce", head_title_ko: "부장", match_ko: ["상무부장"] },
    { ko: "문화여유부", en: "Ministry of Culture and Tourism", head_title_ko: "부장", match_ko: ["문화여유", "문화관광"] },
    { ko: "국가위생건강위원회", en: "National Health Commission", head_title_ko: "주임", match_ko: ["위생건강"] },
    { ko: "퇴역군인사무부", en: "Ministry of Veterans Affairs", head_title_ko: "부장", match_ko: ["퇴역군인"] },
    { ko: "응급관리부", en: "Ministry of Emergency Management", head_title_ko: "부장", match_ko: ["응급관리"] },
    { ko: "중국인민은행", en: "People's Bank of China", head_title_ko: "행장", match_ko: ["인민은행"] },
    { ko: "심계서", en: "National Audit Office", head_title_ko: "심계장", match_ko: ["심계"] },
];

export const applyCnPartyChart = (chart) => {
    if (Array.isArray(chart?.party_posts) && chart.party_posts.length) PARTY_POSTS = chart.party_posts;
    if (Array.isArray(chart?.state_council_ministries) && chart.state_council_ministries.length) {
        MINISTRIES = chart.state_council_ministries;
    }
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
        // 4대 판공(판공청·정책연구실·재경위·군민융합)은 head 필드가 `minister`가
        // 아니라 `director`다 -- 부장이 아니라 주임이라서다. 둘 중 있는 쪽을 쓴다.
        ...Object.values(partyState.central_departments || {})
            .filter((value) => value && typeof value === 'object' && (value.minister || value.director))
            .map((value) => {
                const head = value.minister || value.director;
                return { ...head, role_ko: head.role_ko || value.title_ko };
            }),
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

// 부총리급까지만 박스로 낸다. 부처는 박스를 누르면 그 아래로 펼쳐진다.
const vicePremierBoxes = (leadership) => {
    const council = leadership.party_state?.state_council || {};
    return [
        ...(council.vice_premiers || []).map((row, index) => orgBox({
            ko: index === 0 ? '상무부총리' : '부총리',
            title: shortTitle(index === 0 ? '상무부총리' : '부총리', row.title_ko),
            person: personWithStatus(row),
            strike: isFallen(row),
        })),
    ];
};

// 국무위원. 왕샤오훙처럼 부처장을 겸하는 자리도 있다 -- 부처 단에 또 나와도 중복이
// 아니라 겸직이고, title_ko 자체가 "국무위원·공안부장"처럼 겸직을 적고 있다.
const stateCouncilorBoxes = (leadership) => {
    const council = leadership.party_state?.state_council || {};
    return (council.state_councilors || []).map((row) => orgBox({
        ko: row.title_ko || '국무위원',
        person: personWithStatus(row),
        strike: isFallen(row),
        note: row.note_ko,
    }));
};

// 부처 박스. `state_council.constituent_departments`(부처별 id·정본 명칭·부장·당위
// 서기)가 있으면 그것을 그대로 26개 다 그린다 -- 이름이 확보된 곳만 골라내지 않는다.
// 그 배열이 없는(더 오래된) 보드에서만 아래 골격 + cmc/security_organs 키워드
// 매칭으로 내려앉는다.
//
// 골격 매칭은 골격의 match_ko 를 사람 행의 title_ko·role_ko 에 대는 것뿐이다. 왕이처럼
// 데이터가 '외교·중앙외사판공실'로만 적어 둔 사람은 외교부장으로 끌어오지 않는다 --
// 실제로 겸하더라도 이 데이터가 말한 적 없는 자리를 화면이 지어내면 안 된다.
const legacyMinistryPool = (leadership) => {
    const cmc = leadership.cmc || {};
    const organs = leadership.security_organs || {};
    return [cmc.defense_minister, ...Object.values(organs)]
        .filter((row) => row && typeof row === 'object' && (row.name_ko || row.name_en));
};

// 부장·당서기가 다른 사람인 곳이 26곳 중 대다수다 (외교부 왕이 vs 당위서기 제위,
// 생태환경부 황룬추 vs 당조서기 쑨진룽 등) -- `party_group_secretary.title_ko`가
// 당위서기/당조서기 구분을 데이터가 직접 갖고 있으므로 하나로 뭉뚱그리지 않는다.
// `same_as_minister: true`인 곳은 같은 사람을 두 번 적지 않도록 줄을 넣지 않는다.
// `predecessor`(면직된 전임)가 있으면 박스 하단에 삭선으로 남긴다 -- 자연자원부처럼
// 부장이 공석인 자리도 "명단 미수집"이 아니라 실제로 비어 있다는 뜻이라 `isVacant`로
// 구분해 표기한다. 국방부처럼 애초에 민간 당조가 없는 곳은 `party_group_secretary`가
// 이름 없는 `organ: "not_applicable"` 객체로 온다 -- personName()이 "불명"을 돌려주는
// 이 자리에 이름 줄을 만들지 않고, 대신 그 객체 자신의 note_ko("민간 당조 없음")를 쓴다.
const constituentDepartmentBox = (dept) => {
    const minister = dept.minister;
    const vacant = isVacant(minister);
    const secretary = dept.party_group_secretary;
    const secretaryNamed = secretary && personName(secretary) !== '불명';
    const showSecretaryName = secretaryNamed && secretary.same_as_minister !== true;
    return orgBox({
        ko: dept.title_ko,
        en: dept.title_en || dept.title_zh || '',
        title: minister?.title_ko || '',
        person: vacant ? personName(minister) : personWithStatus(minister),
        vacant,
        strike: isFallen(minister),
        former: formerNames([dept.predecessor].filter(Boolean)),
        note: [
            minister?.note_ko || minister?.note,
            showSecretaryName ? `${secretary.title_ko || '당위 서기'} ${personName(secretary)}` : (secretary?.note_ko || ''),
        ].filter(Boolean).join(' · '),
    });
};

const legacyMinistryBox = (ministry, pool) => {
    const supplied = ministry.name_ko || ministry.name_en ? ministry : null;
    const match = supplied || pool.find((row) => (ministry.match_ko || [])
        .some((needle) => String(row.title_ko || row.role_ko || '').includes(needle)));
    return orgBox({
        ko: ministry.ko,
        en: ministry.en,
        title: ministry.head_title_ko,
        person: personWithStatus(match),
        strike: isFallen(match),
        note: [
            match?.note_ko || match?.note,
            match && match.on_cmc === false ? '중앙군사위 위원 아님' : '',
        ].filter(Boolean).join(' · '),
    });
};

const constituentDepartments = (leadership) => leadership.party_state?.state_council?.constituent_departments || [];

const ministryBoxes = (leadership) => {
    const departments = constituentDepartments(leadership);
    if (departments.length) return departments.map(constituentDepartmentBox);
    const pool = legacyMinistryPool(leadership);
    return MINISTRIES.map((ministry) => legacyMinistryBox(ministry, pool));
};

const ministryFilledCount = (leadership) => {
    const departments = constituentDepartments(leadership);
    if (departments.length) {
        return departments.filter((dept) => personName(dept.minister) !== '불명').length;
    }
    const pool = legacyMinistryPool(leadership);
    return MINISTRIES.filter((ministry) => ministry.name_ko || ministry.name_en || pool.some((row) => (ministry.match_ko || [])
        .some((needle) => String(row.title_ko || row.role_ko || '').includes(needle)))).length;
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

// 세 화면이 공유하는 꼬리: 명부 기준일과 겸직 안내. 실각 전체 명부는 공산당 화면에만
// 붙인다 -- 군 쪽 실각은 군부 화면의 각 자리에 삭선으로 이미 서 있다.
const footer = (leadership) => `
    ${noteLine(leadership.as_of ? `명부 기준일 ${leadership.as_of} · 갱신 주기 ${leadership.review_cadence || '불명'}` : '')}
    <p class="elections-panel-note">한 사람이 당·국가·군의 여러 자리를 겸합니다. 다른 화면에 같은 이름이 나오는 것은 중복이 아니라 겸직입니다.</p>`;

export const chnParty = (country) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    const partyState = leadership.party_state || {};
    const standing = partyState.politburo_standing_committee || {};
    const politburo = partyState.politburo || {};
    const nonPsc = politburoMembers(politburo, standing);
    const roster = politburoRoster(politburo, standing);

    // 정치국과 중앙군사위 명부에 같은 사람이 두 번 나온다 (허웨이둥·장유샤는 둘 다
    // 겸직이었다). 두 줄로 세면 실각 인원이 부풀려지므로 이름으로 한 번만 센다.
    const fallen = new Map();
    (politburo.fallen || []).forEach((row) => fallen.set(personName(row), personLine(row, row.was)));
    ((leadership.cmc || {}).fallen || []).forEach((row) => {
        const key = personName(row);
        if (!fallen.has(key)) fallen.set(key, personLine(row, row.role_ko));
    });
    const fallenRows = [...fallen.values()];

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

        ${disclosure(`당·군 실각·조사 ${fallenRows.length}인 · 전체`, fallenRows)}
        ${footer(leadership)}
    `;
};

export const chnMilitary = (country) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    const cmc = leadership.cmc || {};
    const branches = leadership.service_branches || {};
    return `
        <p class="section-title">1 · 중앙군사위원회</p>
        ${orgGrid(cmcBoxes(leadership))}
        ${noteLine(cmc.notes_ko)}
        ${cmc.defense_minister && cmc.defense_minister.on_cmc === false ? noteLine(`국방부장 ${personName(cmc.defense_minister)} — 중앙군사위 위원이 아닌 국무원 부처장입니다. 국무원 화면에 있습니다.`) : ''}
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
        ${footer(leadership)}
    `;
};

export const chnStateCouncil = (country) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    const council = leadership.party_state?.state_council || {};
    const vicePremiers = vicePremierBoxes(leadership);
    const councilors = stateCouncilorBoxes(leadership);
    const ministries = ministryBoxes(leadership);
    const filled = ministryFilledCount(leadership);
    const ministrySection = councilors.length ? 4 : 3;
    return `
        <p class="section-title">1 · 총리</p>
        ${orgGrid([orgBox({ ko: '국무원 총리', person: personWithStatus(council.premier) })])}

        <p class="section-title">2 · 부총리 ${vicePremiers.length ? `${vicePremiers.length}인` : ''}</p>
        ${vicePremiers.length ? orgGrid(vicePremiers) : '<p class="elections-muted">확보된 부총리 명부가 없습니다.</p>'}

        ${councilors.length ? `
        <p class="section-title">3 · 국무위원 ${councilors.length}인</p>
        ${orgGrid(councilors)}
        ` : ''}

        <p class="section-title">${ministrySection} · 부처 ${ministries.length}곳</p>
        ${orgGrid(ministries)}
        ${noteLine(`구성 부문 ${ministries.length}곳 가운데 이름이 확보된 곳은 ${filled}곳입니다. 비어 있는 칸은 명단 미수집이며, 그 부처가 없거나 부처장이 공석이라는 뜻이 아닙니다.`)}
        ${noteLine('부처 박스의 둘째 줄(당위서기/당조서기)은 그 부처 당 조직의 서기입니다. 부장과 다른 사람인 곳이 대부분입니다 -- 당위·당조가 국가기구의 인사보다 앞섭니다.')}

        ${noteLine('국무원은 국가기구입니다. 실제 의사결정은 공산당 화면의 당 기구에서 먼저 이뤄집니다 — 두 화면을 같이 보셔야 합니다.')}
        ${noteLine('전국인민대표대회 화면은 데이터 계약상 만들지 않습니다.')}
        ${footer(leadership)}
    `;
};
