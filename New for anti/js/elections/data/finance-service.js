const DATA_ROOT = '/public/data';
let nationalPromise = null;
const statePromises = new Map();

const loadJson = async (path) => {
    const response = await fetch(`${DATA_ROOT}/${path}`, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`${path} (${response.status})`);
    return response.json();
};

// usa_election_finance_index_v1.json's own rules_ko is explicit: of the seven
// spender categories the pipeline classifies, only `super_pac` may be labelled
// 슈퍼팩, and a null amount is "not yet observed" -- never $0.
export const loadUsaElectionFinance = () => {
    if (!nationalPromise) {
        nationalPromise = loadJson('usa_election_finance_index_v1.json')
            .then((index) => {
                const nationalFile = index?.cycles?.['2026']?.national_file;
                return nationalFile ? loadJson(nationalFile) : null;
            })
            .catch(() => null);
    }
    return nationalPromise;
};

// Per-candidate amounts and per-party totals live only in the individual race
// files, so a state's 선거 panel needs all of them: national index -> that
// state's race list -> every race file it names. Memoised per state, and only
// ever reached when the 선거 toggle is switched on.
export const loadStateFinance = (stateId) => {
    if (!statePromises.has(stateId)) {
        statePromises.set(stateId, (async () => {
            const national = await loadUsaElectionFinance();
            const stateFile = national?.states?.[stateId]?.data_file;
            if (!stateFile) return null;
            const index = await loadJson(stateFile).catch(() => null);
            if (!index?.races?.length) return null;
            const races = await Promise.all(index.races.map((race) => (
                race.data_file ? loadJson(race.data_file).catch(() => null) : null
            )));
            return races.filter(Boolean);
        })());
    }
    return statePromises.get(stateId);
};
