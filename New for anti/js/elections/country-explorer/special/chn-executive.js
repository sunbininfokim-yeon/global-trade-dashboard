import { card, orgBox, orgGrid, disclosure, noteLine } from './org-chart.js';
import { personName, personLine, isFallen, statusKo } from './china.js';

// 중국 행정부 화면.
//
// 미국 화면과 같은 4단 조직도를 쓰지만, 단에 들어가는 것이 다르다. 중국에서
// 행정부만 떼어 그리면 국무원 하나가 남는데, 실제 결정은 그 위 당 기구에서 난다.
// 그래서 요청대로 두 가지를 이 화면 안에 넣는다:
//
//   2단 = 공산당 중앙 위원회·기구  (정치국 상무위·정치국·군사위·정법위·서기처·기율위·3대 부서)
//   4단 = 군                       (중앙군사위 → 군종 → 전구)
//
// 겸직이 이 체제의 핵심이라 1단에는 직책이 아니라 겸직 묶음을 적는다 (총서기·국가주석·
// 군위주석은 한 사람의 세 자리다). 직책이 여러 단에 다시 나오는 것은 중복이 아니라
// 구조이므로 감추지 않고, 대신 어느 자리로 거기 있는지를 박스마다 적는다.
//
// 실각·조사자는 leadership.display_rules 가 strikethrough 로 지정한 그대로 삭선으로
// 표시하고, 살아 있는 명부에 섞지 않는다.

const PSC_KEY_TITLES = ['총서기', '국무원 총리', '전인대 상무위원장'];

const personWithStatus = (person) => {
    if (!person) return '';
    const name = personName(person);
    if (name === '불명') return '';
    return [name, statusKo(person.status)].filter(Boolean).join(' · ');
};

const countLabel = (rows, unit = '인') => (Array.isArray(rows) && rows.length ? `${rows.length}${unit}` : '');

// 2단. "위원회" 칸은 당 기구다 -- 국가기구가 아니다. 상무위·정치국은 인원수가,
// 부서·위원회는 책임자가 박스의 내용이 된다.
const partyOrganBoxes = (leadership) => {
    const partyState = leadership.party_state || {};
    const standing = partyState.politburo_standing_committee || {};
    const politburo = partyState.politburo || {};
    const departments = partyState.central_departments || {};
    const cmc = leadership.cmc || {};
    const organs = leadership.security_organs || {};
    const rank = standing.rank_order || [];

    // 서기처·기율위 책임자는 별도 필드가 아니라 상무위원의 role_ko 안에 있다.
    const byRole = (needle) => rank.find((row) => String(row.role_ko || row.title_ko || '').includes(needle)) || null;
    const secretariat = byRole('서기처');
    const discipline = byRole('중기위');

    const boxes = [
        orgBox({
            abbr: 'PSC', ko: '정치국 상무위원회', en: 'Politburo Standing Committee',
            title: '상무위원', person: standing.n ? `${standing.n}인` : '', note: standing.source,
        }),
        orgBox({
            abbr: 'PB', ko: '정치국', en: 'Politburo',
            title: '위원', person: politburo.active_n_approx ? `현원 약 ${politburo.active_n_approx}인` : '',
            note: politburo.original_n_20th ? `20차 원구성 ${politburo.original_n_20th}인` : '',
        }),
        orgBox({
            abbr: 'CMC', ko: '중앙군사위원회', en: 'Central Military Commission',
            title: '주석', person: personWithStatus((cmc.active_core || [])[0]),
            note: countLabel(cmc.active_core) ? `활성 핵심 ${countLabel(cmc.active_core)}` : '',
        }),
        orgBox({
            abbr: 'CSec', ko: '중앙서기처', en: 'Central Secretariat',
            title: secretariat?.title_ko || '제1서기', person: personWithStatus(secretariat),
        }),
        orgBox({
            abbr: 'CCDI', ko: '중앙기율검사위원회', en: 'Central Commission for Discipline Inspection',
            title: discipline?.title_ko || '서기', person: personWithStatus(discipline),
        }),
    ];

    // 중앙 3대 부서 + 정법위. 정법위는 부서 표에서 minister 가 비어 있고
    // security_organs 쪽에 서기가 들어 있어, 두 곳을 합쳐 한 박스로 만든다.
    Object.entries(departments)
        .filter(([, value]) => value && typeof value === 'object')
        .forEach(([key, value]) => {
            const head = value.minister
                || (key === 'political_and_legal_affairs' ? organs.central_political_and_legal_affairs_commission : null);
            boxes.push(orgBox({
                ko: value.title_ko || key,
                title: head?.title_ko || '부장',
                person: personWithStatus(head),
                strike: isFallen(head),
            }));
        });
    return boxes;
};

// 3단. 국무원은 총리·부총리와, 당 기구가 아니라 국가기구로 걸리는 부처들이다.
const stateCouncilBoxes = (leadership) => {
    const council = leadership.party_state?.state_council || {};
    const cmc = leadership.cmc || {};
    const organs = leadership.security_organs || {};
    const boxes = [
        orgBox({ ko: '국무원 총리', title: '총리', person: personWithStatus(council.premier) }),
        ...(council.vice_premiers || []).map((row, index) => orgBox({
            ko: index === 0 ? '상무부총리' : '부총리',
            title: row.title_ko || (index === 0 ? '상무부총리' : '부총리'),
            person: personWithStatus(row),
            strike: isFallen(row),
        })),
        orgBox({
            ko: '국방부', title: cmc.defense_minister?.title_ko || '부장',
            person: personWithStatus(cmc.defense_minister),
            note: cmc.defense_minister?.on_cmc === false ? '중앙군사위 위원 아님' : '',
        }),
    ];
    ['ministry_of_public_security', 'ministry_of_state_security'].forEach((key) => {
        const organ = organs[key];
        if (!organ) return;
        boxes.push(orgBox({
            ko: key === 'ministry_of_public_security' ? '공안부' : '국가안전부',
            title: organ.title_ko || '부장',
            person: personWithStatus(organ),
            note: organ.note,
        }));
    });
    return boxes;
};

// 4단. 군종과 전구는 다른 축이다 -- 군종은 건설·관리, 전구는 작전 지휘라 한쪽이
// 다른 쪽 밑에 들어가지 않는다. 그래서 같은 단에 나란히 둔다.
const militaryBoxes = (leadership) => {
    const branches = leadership.service_branches || {};
    const theaters = leadership.theater_commands || [];
    const boxes = Object.entries(branches)
        .filter(([, value]) => value && typeof value === 'object' && value.name_ko)
        .map(([, value]) => orgBox({
            ko: value.name_ko,
            title: value.commander?.title_ko || '사령',
            person: personWithStatus(value.commander),
            strike: isFallen(value.commander),
            // 사령이 공석인 군종은 정치위원만으로 채우지 않는다. 공석 사유와,
            // 사령이 누구인지 보도가 갈리는 경우(alt_reported) 그 사실까지 적는다 --
            // 한쪽 보도를 골라 확정처럼 두면 그게 틀린 화면이 된다.
            note: [
                value.political_commissar ? `정치위원 ${personName(value.political_commissar)}` : '',
                value.commander?.note,
                value.alt_reported ? `다른 보도 ${personName(value.alt_reported)} (공식 미확인)` : '',
            ].filter(Boolean).join(' · '),
        }));
    theaters.forEach((theater) => boxes.push(orgBox({
        ko: theater.name_ko || '전구',
        title: theater.commander?.title_ko || '사령관',
        person: personWithStatus(theater.commander),
        strike: isFallen(theater.commander),
        note: theater.political_commissar ? `정치위원 ${personName(theater.political_commissar)}` : '',
    })));
    return boxes;
};

const topTier = (leadership) => {
    const rank = leadership.party_state?.politburo_standing_committee?.rank_order || [];
    const rows = rank.filter((row) => PSC_KEY_TITLES.includes(row.title_ko));
    const list = rows.length ? rows : rank.slice(0, 3);
    return list.map((row) => card(
        row.role_ko || row.title_ko || '직책',
        personWithStatus(row),
        row.confidence ? `신뢰도 ${row.confidence}` : '',
    )).join('');
};

export const chnExecutive = (country) => {
    const leadership = country.leadership;
    if (!leadership) return null;
    const cmc = leadership.cmc || {};
    const politburo = leadership.party_state?.politburo || {};
    const theaters = leadership.theater_commands || [];
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
        <p class="section-title">1 · 최고 지도부 (당·국가·군)</p>
        <div class="elections-card-grid">${topTier(leadership) || '<p class="elections-muted">확보된 공개 명부가 없습니다.</p>'}</div>
        <p class="elections-panel-note">한 사람이 당·국가·군 세 자리를 겸합니다. 아래 단에 같은 이름이 다시 나오는 것은 중복이 아니라 겸직입니다.</p>

        <p class="section-title">2 · 공산당 중앙 위원회·기구</p>
        ${orgGrid(partyOrganBoxes(leadership))}
        <p class="elections-panel-note">이 단은 국가기구가 아니라 당 기구입니다. 국무원보다 위에 놓은 것은 서열이 아니라 의사결정 순서를 따른 것입니다.</p>

        <p class="section-title">3 · 국무원</p>
        ${orgGrid(stateCouncilBoxes(leadership))}

        <p class="section-title">4 · 군 · 안보</p>
        ${orgGrid(militaryBoxes(leadership))}
        <p class="elections-panel-note">군종(军种)은 건설·관리, 전구(战区)는 작전 지휘로 축이 다릅니다 — 같은 단에 나란히 둔 이유입니다. 전구 ${theaters.length}곳.</p>

        ${disclosure(`실각·조사 ${fallenRows.length}인`, fallenRows)}
        ${fallenRows.length ? '<p class="elections-panel-note">삭선은 데이터의 display 규칙(실각·조사)을 그대로 옮긴 것이며, 후임이 정해졌다는 뜻이 아닙니다.</p>' : ''}
        ${noteLine(leadership.as_of ? `명부 기준일 ${leadership.as_of} · 갱신 주기 ${leadership.review_cadence || '불명'}` : '')}
        ${noteLine(politburo.note_ko)}
        ${noteLine(cmc.notes_ko)}
    `;
};
