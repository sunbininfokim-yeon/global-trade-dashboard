const DATA_ROOT = '/public/data';
let financePromise = null;

const loadJson = async (path) => {
    const response = await fetch(`${DATA_ROOT}/${path}`, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`${path} (${response.status})`);
    return response.json();
};

// usa_election_finance_index_v1.json's own rules_ko says it plainly:
// "super_pac만 슈퍼팩 필터에 포함하고 주 미분류 독립지출은 별도 표시하세요"
// -- of the 7 spender categories the pipeline classifies, only `super_pac`
// is safe to label "슈퍼팩" in the UI. The national file's per-state
// `totals_by_office` already carries that category pre-aggregated (governor/
// senate/house), so the country map's race_progress screen (PR #260 data)
// can join it by state id without fetching all ~580 individual race files.
export const loadUsaElectionFinance = () => {
    if (!financePromise) {
        financePromise = loadJson('usa_election_finance_index_v1.json')
            .then((index) => {
                const nationalFile = index?.cycles?.['2026']?.national_file;
                return nationalFile ? loadJson(nationalFile) : null;
            })
            .catch(() => null);
    }
    return financePromise;
};
