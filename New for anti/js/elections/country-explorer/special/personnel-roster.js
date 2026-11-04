import { escapeHtml } from '../../ui.js';
import { orgBox, orgGrid, expandableGrid } from './org-chart.js';

// 국가별 '인사 명단' 화면. 자료는 public/data/personnel/<ISO3>.json
// (scripts/election_watch/build_personnel_public.py 가 config/*_personnel_*.json 에서 낸다).
//
// 나라마다 수집 범위가 달라 스키마가 하나가 아니다 (kor_personnel_v1, fra_personnel_v1 ...).
// 그래서 나라별 화면을 따로 짜지 않고 JSON 모양을 읽는 범용 렌더러를 둔다:
//   - name 이 있는 객체        → 사람 한 줄 (직함 · 이름 · 정당/지역 · 날짜 · 출처 링크)
//   - name + seats 류 객체     → 정당·교섭단체 의석 줄
//   - 값이 전부 숫자인 객체     → '정당 n' 칩 (by_party 등)
//   - 문자열 배열              → 글머리표 목록
//   - 그 밖의 객체·배열         → 접힌 하위 단락
// 자료에 없는 말은 지어내지 않는다. 키 이름을 한국어로 옮기는 것뿐이고, 표에 없는 키는
// 원래 이름을 그대로 보인다 -- 새 항목이 조용히 사라지지 않게.

const META_KEYS = new Set(['schema', 'country', 'as_of', 'cutoff_ko']);
const NOTE_KEYS = new Set(['not_in_this_file', 'not_in_this_file_ko', 'rules_ko', 'unknown_slots_ko']);
// 화면에 의미가 없는 내부 식별자.
const HIDDEN_KEYS = new Set(['source_grade', 'fetched', 'fetched_on', 'rechecked', 'rows_returned', 'mona_cd', 'cmt_id', 'hr_cmt_id', 'group_code', 'kana', 'name_hj', 'code', 'cmt_code']);

const LABELS = {
    president: '대통령', vice_president: '부통령', first_vice_president: '제1부통령', prime_minister: '총리',
    presidential_office: '대통령실', presidential_administration: '대통령 행정실', presidential_court: '대통령궁',
    cabinet_office: '내각사무처', cabinet_secretariat: '내각 사무국', prime_ministers_office: '총리실',
    prime_minister_advisors: '총리 보좌진', government: '정부', executive: '행정부', cabinet: '내각', ministers: '장관',
    secretariat: '비서실', special_advisors: '특별보좌관', national_security: '국가안보실', chief: '실장',
    deputies: '하원', deputy: '차장', senate: '상원', assembly: '의회', parliament: '의회', chamber: '의회',
    national_assembly: '국민의회', house: '하원', house_of_commons: '하원(서민원)', house_of_lords: '상원(귀족원)',
    commons: '하원', bundestag: '연방하원', bundesrat: '연방상원', federal_president: '연방대통령',
    governors: '주지사·지사', governors_elected_2026: '2026 선출 주지사', regional_governors: '지역 지사',
    regional_executives: '지역 행정수반', premiers: '주 총리', devolved: '자치정부', devolved_legislatures: '자치의회',
    england_mayor: '잉글랜드 시장', orientation: '정치 성향', poles: '축', emir: '에미르', crown_prince: '왕세자',
    king: '국왕', royal_court: '왕실', amiri_diwan: '에미르 궁정', shura: '슈라', supreme_council: '최고위원회',
    federal_national_council: '연방국가평의회', supreme_leader: '최고지도자', majlis: '의회(마즐리스)',
    guardian_council: '헌법수호위원회', assembly_of_experts: '전문가회의', irgc: '혁명수비대', basij: '바시즈',
    armed_forces_staff: '군 총참모부', council_of_representatives: '대표의회', kurdistan_region: '쿠르디스탄 지역',
    knesset_25: '제25대 크네세트', knesset_26: '제26대 크네세트', milli_majlis: '밀리 마즐리스', privy_council: '추밀원',
    dissolution: '의회 해산', election: '선거', elections: '선거', quebec_election: '퀘벡 선거',
    senate_2027_projection: '2027 상원 전망', demographics: '구성', alternatives: '대안', dated_titles: '날짜별 직함',
    elysee: '엘리제(대통령실)', regions: '지역', people: '명단', members: '의원', parties: '정당', groups: '교섭단체',
    speaker: '의장', deputy_speaker: '부의장', secretary_general: '사무총장', standing_committees: '상임위원회',
    committees: '위원회', seats: '의석', by_party: '정당별', local_election_2026: '2026 지방선거',
    congress_permanent_deputation: '하원 상임대표단', congress_groups_before_dissolution: '해산 전 하원 교섭단체',
    senate_permanent_deputation: '상원 상임대표단', no10_and_security: '총리실·안보', officers: '임원',
    directors: '이사', named: '명단', clubs: '의원단', leader: '지도자', women: '여성', vacancies: '공석',
    chancellor: '총리', reelected: '재선', succeeded: '승계', assumed_prime_minister_on: '총리 취임', pole: '축', line: '설명', as_of: '기준일', list: '명부', date: '날짜', day: '날짜', persian_date: '이란력 날짜',
    gregorian: '양력', number: '번호', proportional: '비례대표', negotiating_group: '교섭단체', emirate: '토후국',
    wording: '원문 표현', decision: '결정', text: '본문', period: '기간', attribute: '속성', individual: '개인',
    source_grade: '출처 등급', still_titled_on: '직함 확인일', election_day: '선거일', published: '게시일', men: '남성',
    invalid: '무효', founded: '창당', convocation: '대수', sources: '출처', valid: '유효', current: '현재',
    first_round: '1차 투표', majority: '과반', factions: '교섭단체·분파', representative: '대표', sitting: '회의',
    source_date: '출처 날짜', titles: '직함', rule: '규칙', registered: '등록', legislature: '입법기', chair: '위원장',
    session: '회기', present: '출석', status: '상태', caucuses: '교섭단체', decree: '법령', sessions: '회기',
    blocs: '블록', deputy_speakers: '부의장', share_of_valid: '유효표 비율', parties_represented: '의석 보유 정당',
    takes_office: '취임 예정', mean_age: '평균 연령', listed: '명부', turnout: '투표율', opening: '개회',
    chief_of_staff: '비서실장', source_note: '출처 메모', appointed_by: '임명권자', committee_chairs: '위원장',
    year: '연도', born: '출생', also: '겸직', oath: '선서', how_chosen: '선출 방식', began: '시작', gender: '성별',
    kind: '구분', candidates: '후보', heads: '수장', states: '주', offices: '직책', roles: '직책', names: '이름',
    secretary: '서기·비서', commander_in_chief: '총사령관', commander: '사령관', others: '기타', certified: '인증',
    runners: '차점자', threshold: '봉쇄조항', mandates: '의석', opposition_leader: '야당 대표', house_of_representatives: '중의원',
    house_of_councillors: '참의원', diet_session: '국회 회기', standing_committee_chairs: '상임위원장', tier: '구분',
    crisis_center: '위기관리센터', statutory: '법정', half: '반기', halves: '전·후반기', first: '첫째', second: '둘째',
    rules: '규칙', election_date: '선거일', dissolved: '해산', duration: '기간', powers: '권한', presidency: '대통령실',
    deputy_prime_minister: '부총리', deputy_prime_ministers: '부총리', chancellery: '총리실', sejm: '하원(세임)',
    deputy_emir: '부에미르', security_council: '안전보장회의', state_duma: '국가두마', federation_council: '연방평의회',
    first_deputies: '제1부의장', commission_chairs: '위원장', regional_heads: '지역 수장', composition: '구성',
    statute: '법규', decisions: '결정', round: '차수', sworn: '선서', presidential_secretariat: '총통부 비서실',
    national_security_council: '국가안전회의', deputy_secretaries: '부비서장', consultants: '자문', executive_yuan: '행정원',
    legislative_yuan: '입법원', procedure_committee: '절차위원회', local_executives: '지방 수장', special_municipalities: '직할시',
    county_and_city_mayors: '현·시장', presidential_leadership_council: '대통령 지도위원회', meeting: '회의', place: '장소',
    elected_speaker: '선출 의장', acting_prime_minister: '총리 대행', governorate: '주(州)', vice_presidents: '부의장',
    mesa: '의장단', moncloa: '총리실(몬클로아)', non_inscrits: '무소속', standing_committee_presidents: '상임위원장',
    no_group: '무소속', delegate: '대표', first_minister: '수석장관', deputy_first_minister: '부수석장관',
    scotland: '스코틀랜드', wales: '웨일스', northern_ireland: '북아일랜드', presiding_officer: '의장',
    first_deputy: '제1부의장', commander_in_chief_ko: '총사령관', rows: '행', bodies: '기구', local_executives_by_party: '기초단체장 정당별',
    metro_councils_by_party: '광역의회 정당별', local_councils_by_party: '기초의회 정당별', by_group: '교섭단체별',
    by_uf: '주별', districts: '선거구', women_caucus: '여성 의원단', independents: '무소속', majority_party: '다수당',
    state_ministers: '국무장관', vice_premier: '부총리', ruler_of_abu_dhabi: '아부다비 통치자', became_ruler_of_dubai: '두바이 통치자 즉위',
    source_url: '출처', url: '출처', note: '비고', note_ko: '비고', since: '취임', appointed: '임명', elected: '선출',
    term: '임기', term_ko: '임기', party: '정당', caucus: '교섭단체', faction: '계파', district: '지역구',
    region: '지역', province: '주', prefecture: '도도부현', role: '직함', title: '직함', office: '직책', office_ko: '직책',
    statutory_seats: '법정 의석', filled: '현원', vacant: '공석', total: '합계', listed_total: '명부 합계',
    working_majority: '작동 과반', member_count: '인원', count: '수', share: '비율', votes: '득표', vote_share: '득표율',
};
const PERSON_TITLE_KEYS = ['role', 'title', 'office_ko', 'office', 'portfolio', 'post_ko', 'kind', 'line', 'position'];
const PERSON_CHIP_KEYS = ['party', 'caucus', 'faction', 'district', 'region', 'province', 'prefecture', 'emirate', 'jurisdiction', 'uf'];
const PERSON_DATE_KEYS = ['since', 'appointed', 'elected', 'reelected', 'allegiance', 'formed', 'date', 'term'];
const URL_KEYS = ['source_url', 'url', 'official_url', 'profile_url'];
const SEAT_KEYS = ['seats', 'members', 'member_count', 'count', 'total'];

// 같은 키가 자리에 따라 뜻이 다르다: 맨 위의 deputies 는 하원(대의원)이고, 안보실 아래의
// deputies 는 차장들이다.
const TOP_LABELS = { deputies: '하원(대의원)', chamber: '의회' };
const label = (key, top = false) => {
    if (top && TOP_LABELS[key]) return TOP_LABELS[key];
    if (key === 'deputies') return '차장·부직';
    const base = key.replace(/_ko$/, '');
    if (LABELS[key] || LABELS[base]) return LABELS[key] || LABELS[base];
    if (/_urls?$/.test(base)) return '관련 페이지';
    if (/(^|_)note$/.test(base)) return '비고';
    const numbered = base.match(/^(.*)_(\d+)$/);
    if (numbered && LABELS[numbered[1]]) return `${LABELS[numbered[1]]} ${numbered[2]}`;
    return base.replaceAll('_', ' ');
};
// 수집 과정의 기록이라 화면 독자에게 뜻이 없는 값.
const PROVENANCE = /^(source_grade|fetched(_on)?|rechecked|rows_returned|page_updated|directory_updated|list_page_updated|interior_page_updated|source_label)$/;
const isUrlKey = (key) => URL_KEYS.includes(key) || key.endsWith('_url');
const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//.test(url) ? url : '');
const isScalar = (v) => v === null || ['string', 'number', 'boolean'].includes(typeof v);
const scalarText = (v) => (v === true ? '예' : v === false ? '아니오' : String(v));
const link = (url, text = '출처') => (safeUrl(url)
    ? `<a class="elections-person-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>` : '');
const firstUrl = (obj) => URL_KEYS.map((k) => obj[k]).find(safeUrl) || '';
const nameOf = (obj) => [obj.name_ko, obj.name, obj.name_en].find((v) => typeof v === 'string' && v.trim());

const isPerson = (v) => v && typeof v === 'object' && !Array.isArray(v) && Boolean(nameOf(v));
const seatValue = (v) => SEAT_KEYS.map((k) => v[k]).find((x) => typeof x === 'number');
const isGroup = (v) => isPerson(v) && typeof seatValue(v) === 'number';
const isCountMap = (v) => v && typeof v === 'object' && !Array.isArray(v)
    && Object.keys(v).length > 0 && Object.values(v).every((x) => typeof x === 'number');

const personRow = (p, fallbackTitle = '') => {
    const title = PERSON_TITLE_KEYS.map((k) => p[k]).find((v) => typeof v === 'string' && v.trim()) || fallbackTitle;
    const chips = PERSON_CHIP_KEYS.map((k) => p[k]).filter((v) => isScalar(v) && v !== null && v !== '').map(scalarText);
    const dates = PERSON_DATE_KEYS.filter((k) => isScalar(p[k]) && p[k] !== null && p[k] !== '')
        .map((k) => `${label(k)} ${scalarText(p[k])}`);
    const note = p.note_ko || p.note;
    const url = firstUrl(p);
    return `<div class="pr-person">
        <span class="pr-title">${escapeHtml(title || '')}</span>
        <strong>${url ? link(url, nameOf(p)) : escapeHtml(nameOf(p))}</strong>
        ${chips.length ? `<em>${escapeHtml(chips.join(' · '))}</em>` : ''}
        ${dates.length || (typeof note === 'string' && note) ? `<small>${escapeHtml([...dates, typeof note === 'string' ? note : ''].filter(Boolean).join(' · '))}</small>` : ''}
    </div>`;
};

const groupRows = (list) => {
    const max = Math.max(1, ...list.map((g) => seatValue(g) || 0));
    return `<div class="pr-groups">${list.map((g) => {
        const seats = seatValue(g);
        const extra = [g.leader && (nameOf(g.leader) || g.leader), g.pole, g.orientation].filter((v) => typeof v === 'string');
        return `<div class="pr-group"><span>${escapeHtml(nameOf(g))}${extra.length ? ` <small>${escapeHtml(extra.join(' · '))}</small>` : ''}</span>
            <i style="width:${Math.round((seats / max) * 100)}%"></i><b>${escapeHtml(String(seats))}</b></div>`;
    }).join('')}</div>`;
};

const countChips = (obj) => `<div class="pr-chips">${Object.entries(obj)
    .sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${escapeHtml(label(k))} <b>${escapeHtml(String(v))}</b></span>`).join('')}</div>`;

const scalarRows = (obj) => Object.entries(obj)
    .filter(([k, v]) => isScalar(v) && v !== null && v !== '' && !HIDDEN_KEYS.has(k) && !PROVENANCE.test(k) && !k.startsWith('name'))
    .map(([k, v]) => {
        if (isUrlKey(k) || (typeof v === 'string' && /^https?:\/\/\S+$/.test(v))) return safeUrl(v) ? `<div class="pr-kv"><span>${escapeHtml(label(k))}</span>${link(v, '열기')}</div>` : '';
        if (/^note|_note|note_ko$/.test(k) || (typeof v === 'string' && v.length > 60)) {
            return `<p class="pr-note"><b>${escapeHtml(label(k))}</b> ${escapeHtml(scalarText(v))}</p>`;
        }
        return `<div class="pr-kv"><span>${escapeHtml(label(k))}</span><strong>${escapeHtml(scalarText(v))}</strong></div>`;
    }).join('');

const MAX_DEPTH = 5;

const renderList = (key, list, depth) => {
    if (!list.length) return '';
    if (list.every((x) => typeof x === 'string' && safeUrl(x))) return `<div class="pr-chips">${list.map((x, i) => link(x, `출처 ${i + 1}`)).join('')}</div>`;
    if (list.every((x) => typeof x === 'string')) return `<ul class="pr-bullets">${list.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
    if (list.every(isGroup)) return groupRows(list);
    if (list.every(isPerson)) return list.map((p) => personRow(p)).join('');
    return list.map((item, i) => (isScalar(item)
        ? `<div class="pr-kv"><span>${i + 1}</span><strong>${escapeHtml(scalarText(item))}</strong></div>`
        : renderNode(`${label(key)} ${i + 1}`, item, depth + 1, true))).join('');
};

const hasPeople = (html) => /pr-person|pr-group|pr-chips">/.test(html);
const countLabel = (value) => (Array.isArray(value) ? ` · ${value.length}` : '');

// 객체 하나를 한 단락으로. 사람이면 한 줄, 아니면 스칼라 줄 + 하위 단락.
function renderNode(key, value, depth, inList = false) {
    if (value === null || value === undefined || HIDDEN_KEYS.has(key)) return '';
    if (isScalar(value)) return scalarRows({ [key]: value });
    if (Array.isArray(value)) {
        const body = renderList(key, value, depth);
        if (!body) return '';
        return depth === 0 ? body : `<details class="pr-sub"${value.length <= 40 && hasPeople(body) ? ' open' : ''}><summary>${escapeHtml(label(key))}${countLabel(value)}</summary>${body}</details>`;
    }
    if (isPerson(value) && !Object.values(value).some((v) => v && typeof v === 'object')) {
        return personRow(value, inList ? '' : label(key));
    }
    if (isCountMap(value)) {
        const chips = countChips(value);
        return depth === 0 ? chips : `<details class="pr-sub" open><summary>${escapeHtml(label(key))}</summary>${chips}</details>`;
    }
    if (depth >= MAX_DEPTH) return '';
    const head = isPerson(value) ? personRow(value, inList ? '' : label(key)) : '';
    const scalars = isPerson(value) ? '' : scalarRows(value);
    const children = Object.entries(value)
        .filter(([k, v]) => v && typeof v === 'object' && !HIDDEN_KEYS.has(k))
        .map(([k, v]) => renderNode(k, v, depth + 1)).join('');
    const body = `${head}${scalars}${children}`;
    if (!body) return '';
    return depth === 0 || (isPerson(value) && !children)
        ? body
        : `<details class="pr-sub"${depth <= 1 && hasPeople(body) ? ' open' : ''}><summary>${escapeHtml(inList ? key : label(key))}</summary>${body}</details>`;
}

const notesBlock = (data) => {
    const items = [...NOTE_KEYS].flatMap((k) => (Array.isArray(data[k]) ? data[k].map((t) => [k, t]) : []))
        .filter(([, t]) => typeof t === 'string');
    if (!items.length) return '';
    const title = (k) => (k.startsWith('not_in') ? '이 명단에 없는 것' : k.startsWith('unknown') ? '확인 못 한 자리' : '수집 규칙');
    const groups = new Map();
    items.forEach(([k, t]) => groups.set(title(k), [...(groups.get(title(k)) || []), t]));
    return `<details class="elections-disclosure"><summary>수집 범위·빠진 항목</summary>${[...groups.entries()]
        .map(([t, list]) => `<p class="pr-note"><b>${escapeHtml(t)}</b></p><ul class="pr-bullets">${list.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`).join('')}</details>`;
};

// 우측 '인사 명단' 창 안의 갈래. '국가원수' 한 칸으로 뭉치지 않고 그 나라에 실제로 있는
// 기관 이름으로 나눈다 -- 대통령제는 대통령실, 의원내각제는 총리실, 이원집정부제
// (프랑스·러시아·대만 등)는 대통령실·총리실·행정부가 각각 따로 뜬다. 왕정은 왕실,
// 이란은 최고지도자실. 자료에 그 기관이 없으면 그 탭도 없다.
// 맨 위 키를 갈래에 직접 짝짓고, 표에 없는 키는 이름의 낱말로 고른다.
const CATEGORIES = [
    ['leader', '최고지도자실'],
    ['monarch', '왕실'],
    ['president', '대통령실'],
    ['pm', '총리실'],
    ['executive', '행정부·내각'],
    ['legislature', '의회'],
    ['local', '지방'],
    ['other', '기타'],
];
const CATEGORY_OF = {
    supreme_leader: 'leader', irgc: 'leader', basij: 'leader', armed_forces_staff: 'leader', orientation: 'orientation',
    king: 'monarch', crown_prince: 'monarch', royal_court: 'monarch', emir: 'monarch', deputy_emir: 'monarch',
    amiri_diwan: 'monarch', supreme_council: 'monarch',
    president: 'president', vice_president: 'president', first_vice_president: 'president', federal_president: 'president',
    elysee: 'president', presidency: 'president', presidential_administration: 'president', presidential_chancellery: 'president',
    presidential_court: 'president', presidential_leadership_council: 'president', presidential_office: 'president',
    presidential_secretariat: 'president', national_security: 'president', national_security_council: 'president',
    security_council: 'president', secretariat: 'president', special_advisors: 'president',
    prime_minister: 'pm', prime_ministers_office: 'pm', prime_minister_advisors: 'pm',
    cabinet_office: 'executive', cabinet_secretariat: 'executive', cabinet_secretary_general: 'executive',
    deputy_prime_minister: 'executive', executive: 'executive', executive_yuan: 'executive', government: 'executive',
    presidency_minister: 'executive', privy_council: 'executive',
    assembly: 'legislature', assembly_of_experts: 'legislature', bundesrat: 'legislature', bundestag: 'legislature',
    chamber: 'legislature', commons: 'legislature', congress_groups_before_dissolution: 'legislature',
    congress_permanent_deputation: 'legislature', council_of_representatives: 'legislature', deputies: 'legislature',
    dissolution: 'legislature', federal_national_council: 'legislature', federation_council: 'legislature',
    guardian_council: 'legislature', house: 'legislature', house_of_commons: 'legislature', house_of_councillors: 'legislature',
    house_of_lords: 'legislature', house_of_representatives: 'legislature', houses: 'legislature', legislative_yuan: 'legislature',
    majlis: 'legislature', milli_majlis: 'legislature', national_assembly: 'legislature', parliament: 'legislature',
    sejm: 'legislature', senate: 'legislature', senate_2027_projection: 'legislature', senate_permanent_deputation: 'legislature',
    shura: 'legislature', state_duma: 'legislature',
    devolved: 'local', devolved_legislatures: 'local', england_mayor: 'local', governors: 'local', governors_elected_2026: 'local',
    kurdistan_region: 'local', local_election_2026: 'local', local_executives: 'local', premiers: 'local', quebec_election: 'local',
    regional_executives: 'local', regional_governors: 'local', regional_heads: 'local', regions: 'local',
};
export const personnelCategory = (key) => {
    if (CATEGORY_OF[key]) return CATEGORY_OF[key];
    if (/knesset|senate|house|assembly|parliament|chamber|deput|majlis|shura|congress|bundes|duma|sejm|legislat|diet/.test(key)) return 'legislature';
    if (/prime_minister|chancellor/.test(key)) return 'pm';
    if (/president|elysee|secretariat|advis/.test(key)) return 'president';
    if (/king|royal|emir|crown/.test(key)) return 'monarch';
    if (/minister|government|cabinet|executive/.test(key)) return 'executive';
    if (/governor|region|local|devolved|mayor|premier|province|municipal/.test(key)) return 'local';
    return 'other';
};

// '행정부'·'정부' 묶음 안에 총리·총리실이 들어 있는 나라가 많다 (영국 executive.prime_minister,
// 독일 government.chancellor, 스페인 executive.moncloa). 그 자식만 꺼내 총리실 탭으로 옮긴다.
const HOIST = [
    [/^(prime_minister|chancellor|chancellery|chancellery_chief|prime_ministers_office|no10.*|moncloa)$/, 'pm'],
    [/^(president|vice_president|elysee|presidency|presidential_.+)$/, 'president'],
];
const hoistCategory = (key) => HOIST.find(([re]) => re.test(key))?.[1] || null;

const splitEntries = (data) => {
    const entries = [];
    Object.entries(data)
        .filter(([k]) => !META_KEYS.has(k) && !NOTE_KEYS.has(k) && !HIDDEN_KEYS.has(k))
        .forEach(([k, v]) => {
            const cat = personnelCategory(k);
            if (cat === 'executive' && v && typeof v === 'object' && !Array.isArray(v)) {
                const rest = {};
                Object.entries(v).forEach(([ck, cv]) => {
                    const hc = hoistCategory(ck);
                    if (hc && cv && typeof cv === 'object') entries.push([ck, cv, hc]);
                    else rest[ck] = cv;
                });
                entries.push([k, rest, cat]);
            } else entries.push([k, v, cat]);
        });
    return entries;
};

// 갈래별 단락 HTML. 별도 '인사 명단' 창을 만들지 않고, 국가 화면의 기존 블록
// (대통령실·총리실·행정부·의회·지방자치단체·정당)에 각 갈래를 끼워 넣는다.
// 한 화면을 그리는 동안 블록마다 다시 부르므로 자료 객체별로 한 번만 만든다.
const categoryCache = new WeakMap();
export const personnelCategories = (data) => {
    if (!data || typeof data !== 'object') return new Map();
    if (categoryCache.has(data)) return categoryCache.get(data);
    const byCategory = new Map();
    categoryCache.set(data, byCategory);
    splitEntries(data).forEach(([k, v, cat]) => {
        if (!renderNode(k, v, 0)) return;
        byCategory.set(cat, [...(byCategory.get(cat) || []), [k, v]]);
    });
    return byCategory;
};

// ---- 미국 행정부·중국 당 조직도와 같은 양식 ---------------------------------------
// 단마다 '번호 · 이름' 제목을 달고 사람은 조직도 박스(org-chart.js)로 그린다. 많은 단은
// 중국 정치국처럼 앞 7인만 박스로 내고 박스를 누르면 전원이 펼쳐진다. 의석표는 막대다.
// 박스로 옮기지 못한 세부 값(근거 메모·날짜 표기 등)은 블록 끝 '세부 자료'에 남긴다 --
// 원본에 있는 것을 화면이 조용히 버리지 않게.
const HEADLINE = 7;

const personBox = (p, fallbackTitle) => {
    const title = PERSON_TITLE_KEYS.map((k) => p[k]).find((v) => typeof v === 'string' && v.trim()) || fallbackTitle || '';
    const chips = PERSON_CHIP_KEYS.map((k) => p[k]).filter((v) => isScalar(v) && v !== null && v !== '').map(scalarText);
    const dates = PERSON_DATE_KEYS.filter((k) => isScalar(p[k]) && p[k] !== null && p[k] !== '')
        .map((k) => `${label(k)} ${scalarText(p[k])}`);
    return orgBox({
        ko: title || '직책',
        person: nameOf(p),
        personUrl: firstUrl(p) || null,
        note: [...chips, ...dates].join(' · '),
    });
};

// 한 갈래를 단으로 편다. 사람이 바로 들어 있는 값은 그 단의 박스가 되고, 사람 목록이나
// 하위 묶음은 'A · B' 이름의 하위 단이 된다.
const collectTiers = (key, value, title, tiers, depth = 0) => {
    if (value === null || value === undefined || isScalar(value) || HIDDEN_KEYS.has(key) || depth > 3) return;
    if (Array.isArray(value)) {
        if (value.length && value.every(isGroup)) tiers.push({ title, seats: value });
        else if (value.length && value.every(isPerson)) tiers.push({ title, people: value.map((p) => [p, '']) });
        else value.forEach((item, i) => collectTiers(key, item, value.length > 1 ? `${title} ${i + 1}` : title, tiers, depth + 1));
        return;
    }
    if (isCountMap(value)) { tiers.push({ title, counts: value }); return; }
    const own = { title, people: [] };
    if (isPerson(value)) own.people.push([value, label(key)]);
    tiers.push(own);
    Object.entries(value).forEach(([k, v]) => {
        if (!v || typeof v !== 'object' || HIDDEN_KEYS.has(k)) return;
        if (isPerson(v) && !Array.isArray(v)) {
            own.people.push([v, label(k)]);
            Object.entries(v).forEach(([gk, gv]) => {
                if (gv && typeof gv === 'object' && (Array.isArray(gv) ? gv.some(isPerson) || gv.every(isGroup) : isPerson(gv))) {
                    collectTiers(gk, gv, `${title} · ${label(gk)}`, tiers, depth + 2);
                }
            });
        } else collectTiers(k, v, `${title} · ${label(k)}`, tiers, depth + 1);
    });
};

const tierBody = (tier) => {
    if (tier.seats) return groupRows(tier.seats);
    if (tier.counts) return countChips(tier.counts);
    const boxes = tier.people.map(([p, t]) => personBox(p, t));
    if (boxes.length <= HEADLINE + 1) return orgGrid(boxes);
    return expandableGrid({
        boxes: boxes.slice(0, HEADLINE),
        hint: `앞 ${HEADLINE}인 · 박스를 누르면 전원 ${boxes.length}인`,
        body: orgGrid(boxes.slice(HEADLINE)),
    });
};

export const personnelPartHtml = (data, categories) => {
    const byCategory = personnelCategories(data);
    const entries = categories.flatMap((cat) => byCategory.get(cat) || []);
    if (!entries.length) return '';
    const tiers = [];
    entries.forEach(([k, v]) => collectTiers(k, v, label(k, true), tiers));
    const shown = tiers.filter((t) => t.seats?.length || t.counts || t.people?.length);
    const detail = entries.map(([k, v]) => `<section class="pr-section"><p class="pr-note"><b>${escapeHtml(label(k, true))}</b></p>${renderNode(k, v, 0)}</section>`).join('');
    return `<div class="pr-roster">
        ${shown.map((t, i) => `<p class="section-title">${i + 1} · ${escapeHtml(t.title)}${t.people?.length > 1 ? ` ${t.people.length}인` : ''}${t.seats ? ` · 의석` : ''}</p>${tierBody(t)}`).join('')}
        <p class="elections-panel-note">인사 기준일 ${escapeHtml(data.as_of || '')} · 공식 사이트·관보·의회 페이지에서 확인한 이름입니다. 이름을 누르면 출처가 열립니다.</p>
        <details class="elections-disclosure"><summary>세부 자료·근거</summary>${detail}</details>
        ${notesBlock(data)}
    </div>`;
};

export const OFFICE_LABELS = Object.fromEntries(CATEGORIES);
