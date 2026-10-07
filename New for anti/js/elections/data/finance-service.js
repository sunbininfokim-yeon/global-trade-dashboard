const DATA_ROOT = '/public/data';

// 파일 하나를 읽는다. 못 읽으면 **예외**를 던진다 -- 호출한 쪽이 "자료가 없다"와 "받다가
// 실패했다"를 구분할 수 있어야, 실패를 "자료 없음"으로 영구히 굳히지 않는다.
const fetchJson = async (path) => {
    const response = await fetch(`${DATA_ROOT}/${path}`, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`${path} (${response.status})`);
    return response.json();
};

// 실패한 읽기는 기억하지 않는다 (geo-service 와 같은 이유). 예전에는 `.catch(() => null)` 이
// 캐시된 promise 안쪽에 있어서, 네트워크가 한 번 끊기면 그 주의 선거 자금이 세션이 끝날
// 때까지 null 로 굳었다 -- 나갔다 들어와도 "자금 자료 연결 대기"가 계속 떴다.
const memo = new Map();
const once = (key, load) => {
    if (!memo.has(key)) {
        const promise = load().catch((error) => {
            if (memo.get(key) === promise) memo.delete(key);
            throw error;
        });
        memo.set(key, promise);
    }
    return memo.get(key);
};

const strictIndex = () => once('index', () => fetchJson('usa_election_finance_index_v1.json'));

const strictNational = () => once('national', async () => {
    const index = await strictIndex();
    const nationalFile = index?.cycles?.['2026']?.national_file;
    return nationalFile ? fetchJson(nationalFile) : null;
});

const strictStateIndex = (stateId) => once(`state-index:${stateId}`, async () => {
    const national = await strictNational();
    const file = national?.states?.[stateId]?.data_file;
    return file ? fetchJson(file) : null;
});

// 레이스 파일은 파일 단위로 기억한다. 55개 중 하나만 실패했을 때, 재시도가 나머지 54개를
// 다시 받지 않는다.
const strictRace = (file) => once(`race:${file}`, () => fetchJson(file));

// Which spending categories a screen may add up, and what it may call them, is
// the index's call rather than this app's: federal races are 슈퍼팩
// (`super_pac`), a governor's money arrives through state disclosure with the
// spender type unverified. Null means the contract has not shipped yet, and
// callers fall back to the federal category alone.
export const loadFinanceDisplayContract = () => strictIndex()
    .then((index) => index?.display_contract || null).catch(() => null);

// A null amount is "not yet observed" and must never be rendered as $0 -- the
// same index's rules_ko.
export const loadUsaElectionFinance = () => strictNational().catch(() => null);

// The national watch panel only needs race-level totals. Keep candidate-level
// files lazy until a state is opened.
export const loadStateFinanceIndex = (stateId) => strictStateIndex(stateId).catch(() => null);

// Per-candidate amounts and per-party totals live only in the individual race
// files, so a state's 선거 panel needs all of them: national index -> that
// state's race list -> every race file it names.
//
// 돌려주는 값은 `{ races, failed }` 다. 파일 몇 개를 못 받았을 때 그 레이스가 조용히
// 빠지면 화면이 "해당 선거 없음"으로 읽힌다 -- 실패한 개수를 같이 줘서 화면이 "일부를 못
// 불러왔다"고 말할 수 있게 한다. 자료 자체가 없는 주는 null.
export const loadStateFinance = async (stateId) => {
    let index;
    try {
        index = await strictStateIndex(stateId);
    } catch {
        return { races: null, failed: 1, indexFailed: true };
    }
    if (!index?.races?.length) return null;
    const settled = await Promise.all(index.races.map((race) => {
        if (!race.data_file) return { ok: false, missing: true };
        return strictRace(race.data_file).then((value) => ({ ok: true, value }), () => ({ ok: false }));
    }));
    return {
        races: settled.filter((row) => row.ok).map((row) => row.value),
        failed: settled.filter((row) => !row.ok && !row.missing).length,
    };
};

// 주를 누르기 전에 그 주의 자금 자료를 데워 둔다 (호버·포커스). 실패는 조용히 넘긴다.
export const prefetchStateFinance = (stateId) => { loadStateFinance(stateId).catch(() => {}); };
