// 선거별 대진(정당·후보·현재 의석) 로더.
//
// 목차(`elections_contests_index_v1.json`)는 번들에서 한 번만 읽고, **이벤트 파일은
// 창을 열 때 읽는다.** 선거 하나의 대진은 수백 선거구가 될 수 있어(영국 650, 인도 543)
// 첫 화면에서 다 받아 둘 것이 아니다.
//
// 형식은 `scripts/election_watch/HANDOFF_CURSOR_ELECTION_CONTESTS.md` 의 계약이다.

const DATA_ROOT = '/public/data';

const loadJson = async (path) => {
    const response = await fetch(`${DATA_ROOT}/${path}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path} (${response.status})`);
    return response.json();
};

// 일정 한 줄 → 목차의 한 행. 이벤트 id 가 정본이고, 없으면 (국가, 날짜)로 찾는다 --
// 타임라인에는 id 없는 수기 행도 섞여 있다.
export const contestEntryFor = (event, index) => {
    const rows = index?.events || [];
    if (!event || !rows.length) return null;
    return rows.find((row) => row.event_id && row.event_id === event.id)
        || rows.find((row) => row.iso3 === event.iso3 && row.date === event.date)
        || null;
};

const cache = new Map();

// 큰 선거는 열 단위로 쪼개져 있다(`districts_path`). 화면은 그 사정을 몰라도 되게
// 여기서 합쳐서 돌려준다.
const resolveColumns = async (contest) => {
    const columns = await Promise.all((contest.columns || []).map(async (column) => {
        if (Array.isArray(column.districts)) return column;
        if (!column.districts_path) return { ...column, districts: [] };
        const part = await loadJson(column.districts_path).catch(() => null);
        return { ...column, districts: part?.districts || [] };
    }));
    return { ...contest, columns };
};

export const loadContest = (entry) => {
    if (!entry?.path) return Promise.resolve(null);
    if (!cache.has(entry.path)) {
        cache.set(entry.path, loadJson(entry.path).then(resolveColumns).catch(() => null));
    }
    return cache.get(entry.path);
};
