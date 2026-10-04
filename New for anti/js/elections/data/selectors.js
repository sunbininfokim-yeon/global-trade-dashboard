export const monthKeys = (calendar) => Object.keys(calendar?.world_by_month || []).sort();

export const initialMonth = (calendar) => {
    const current = new Date().toISOString().slice(0, 7);
    const months = monthKeys(calendar);
    return months.includes(current) ? current : months.find((month) => month >= current) || months.at(-1) || null;
};

export const eventsForMonth = (calendar, month) => calendar?.world_by_month?.[month] || [];

export const eventsByDate = (events) => {
    const groups = new Map();
    [...events].sort((a, b) => String(a.date || '').localeCompare(String(b.date || ''))).forEach((event) => {
        const key = event.date || '불명';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(event);
    });
    return [...groups.entries()];
};

export const countryEvents = (country) => (country?.events || []).filter((event) => event?.date !== '없음');

export const readableSpectrum = (spectrum) => ({
    conservative: '보수',
    nationalist_conservative: '국가주의·보수',
    progressive: '진보',
    centrist: '중도',
    catch_all_governing_party: '집권당 중심',
    authoritarian_personalist: '권위주의 체제',
    authoritarian_party_state: '당국가 체제',
    authoritarian_cpc: '공산당 일당 체제',
    authoritarian_monarchy: '권위주의 군주정',
    authoritarian_ur: '지배정당 권위주의 체제',
    theocratic_authoritarian: '신정 체제',
}[spectrum] || spectrum || '불명');

export const screenStatus = (manifest, iso3, screen) => manifest?.countries?.[iso3]?.screens?.[screen]?.status || 'disabled';

// 다가오는 일정 — 좌측 목록이 읽는다.
//
// 달력에는 블록이 둘이다. `world_by_month` 는 화면이 읽는 블록이고,
// `board_tracked_all_events` 는 수집기가 생성하는 블록이다. 지금 후자가 109건인데
// 전자는 38건뿐이라, **확정 일자가 있는데 화면에 없는 일정이 36건**이다
// (미국 하원 재보궐 13건, 일본 도도부현 지사 15건 등).
//
// 그래서 여기서 둘을 합쳐 읽는다. 달력 생성기가 `world_by_month` 를 파생물로 바꾸면
// (인계 문서 작업 A-1) 이 합치기는 저절로 무의미해진다 -- 같은 행이 두 번 들어와도
// (iso3, 날짜, 이름)으로 한 번만 남기기 때문이다.
const DATE_FULL = /^\d{4}-\d{2}-\d{2}$/;

// 선거 종류 묶음. 달력의 `type` 어휘를 화면 말로 한 번만 옮긴다.
export const EVENT_KINDS = [
    { key: 'presidential', ko: '대선', types: ['presidential'] },
    { key: 'general', ko: '총선', types: ['general'] },
    { key: 'local', ko: '지방', types: ['local'] },
    { key: 'by_election', ko: '재보궐', types: ['by_election'] },
    { key: 'party', ko: '당권', types: ['party_leadership', 'party_convention', 'leadership_review'] },
];

const KIND_OF = new Map(EVENT_KINDS.flatMap((kind) => kind.types.map((type) => [type, kind.key])));
export const kindOf = (event) => KIND_OF.get(event?.type) || 'other';
export const kindKo = (key) => (EVENT_KINDS.find((kind) => kind.key === key)?.ko) || '기타';

// 같은 선거가 두 블록에 다 있을 때. `world_by_month` 는 사람이 정리한 요약이라 여러
// 건을 한 줄로 묶어 두기도 한다(예: "베를린·MV 주의회"). board 쪽은 생성물이라 주별로
// 나뉘어 있다. 그래서 같은 (국가, 날짜, 종류)에 board 행이 하나라도 있으면 board 쪽만
// 쓴다 -- 요약 한 줄과 낱개 두 줄이 같이 뜨면 같은 선거가 세 번 보인다.
const bucket = (event) => [event.iso3, event.date, kindOf(event)].join('|');

export const allDatedEvents = (calendar) => {
    const dated = (rows) => (rows || []).filter((event) => event && DATE_FULL.test(String(event.date || '')));
    const board = dated(calendar?.board_tracked_all_events);
    const covered = new Set(board.map(bucket));
    const world = Object.values(calendar?.world_by_month || {})
        .flatMap((rows) => dated(rows))
        .filter((event) => !covered.has(bucket(event)));
    return [...board, ...world].sort((a, b) => String(a.date).localeCompare(String(b.date))
        || String(a.iso3).localeCompare(String(b.iso3)));
};

// 오늘을 경계로 가른다. 지난 일정은 지우지 않고 접어 둔다 -- 직전에 무엇이 있었는지가
// 다음 선거를 읽는 맥락이다.
export const splitByToday = (events, today = new Date().toISOString().slice(0, 10)) => ({
    upcoming: events.filter((event) => String(event.date) >= today),
    past: events.filter((event) => String(event.date) < today).reverse(),
});

export const groupByMonth = (events) => {
    const months = new Map();
    events.forEach((event) => {
        const month = String(event.date).slice(0, 7);
        if (!months.has(month)) months.set(month, []);
        months.get(month).push(event);
    });
    return [...months.entries()];
};

// D-day. 오늘이면 0, 지난 일정은 음수.
export const daysUntil = (date, today = new Date().toISOString().slice(0, 10)) => {
    const ms = Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`);
    return Number.isFinite(ms) ? Math.round(ms / 86400000) : null;
};

// 국가 이름 보조표. 상세 화면이 있는 19개국은 board 에 한국어 이름이 있지만, 달력에는
// 그 밖의 나라도 올라온다. 그 행이 "BIH" 로 뜨면 목록에서 읽히지 않으므로 이름만
// 채운다 -- 좌표·정치 데이터가 아니라 표시용 이름이고, 여기 없는 코드는 코드 그대로
// 둔다(새 나라가 들어와도 깨지지 않는다).
const ISO_KO = {
    BIH: '보스니아헤르체고비나', CHE: '스위스', COL: '콜롬비아', CPV: '카보베르데',
    DZA: '알제리', HTI: '아이티', HUN: '헝가리', NZL: '뉴질랜드', PRT: '포르투갈',
    PSE: '팔레스타인', THA: '태국',
};

export const countryKo = (iso3, countries) => countries?.get?.(iso3)?.name_ko || ISO_KO[iso3] || iso3 || '국가 미상';
