const DATA_ROOT = '/public/data';
let indexPromise = null;
let nationalPromise = null;
const statePromises = new Map();
const stateIndexPromises = new Map();

const loadJson = async (path) => {
    const response = await fetch(`${DATA_ROOT}/${path}`, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`${path} (${response.status})`);
    return response.json();
};

const loadIndex = () => {
    if (!indexPromise) indexPromise = loadJson('usa_election_finance_index_v1.json').catch(() => null);
    return indexPromise;
};

// Which spending categories a screen may add up, and what it may call them, is
// the index's call rather than this app's: federal races are 슈퍼팩
// (`super_pac`), a governor's money arrives through state disclosure with the
// spender type unverified. Null means the contract has not shipped yet, and
// callers fall back to the federal category alone.
export const loadFinanceDisplayContract = () => loadIndex().then((index) => index?.display_contract || null);

// A null amount is "not yet observed" and must never be rendered as $0 -- the
// same index's rules_ko.
export const loadUsaElectionFinance = () => {
    if (!nationalPromise) {
        nationalPromise = loadIndex()
            .then((index) => {
                const nationalFile = index?.cycles?.['2026']?.national_file;
                return nationalFile ? loadJson(nationalFile) : null;
            })
            .catch(() => null);
    }
    return nationalPromise;
};

// The national watch panel only needs race-level totals. Keep candidate-level
// files lazy until a state is opened.
export const loadStateFinanceIndex = (stateId) => {
    if (!stateIndexPromises.has(stateId)) stateIndexPromises.set(stateId, loadUsaElectionFinance()
        .then((national) => national?.states?.[stateId]?.data_file)
        .then((file) => file ? loadJson(file) : null)
        .catch(() => null));
    return stateIndexPromises.get(stateId);
};

// Per-candidate amounts and per-party totals live only in the individual race
// files, so a state's 선거 panel needs all of them: national index -> that
// state's race list -> every race file it names. Memoised per state, and only
// ever reached when the 선거 toggle is switched on.
export const loadStateFinance = (stateId) => {
    if (!statePromises.has(stateId)) {
        statePromises.set(stateId, (async () => {
            const index = await loadStateFinanceIndex(stateId);
            if (!index?.races?.length) return null;
            const races = await Promise.all(index.races.map((race) => (
                race.data_file ? loadJson(race.data_file).catch(() => null) : null
            )));
            return races.filter(Boolean);
        })());
    }
    return statePromises.get(stateId);
};
