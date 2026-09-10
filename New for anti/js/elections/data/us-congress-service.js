let committeesPromise = null;

// The 상임위 chips on the 의회 screen come from the same /api/us overview the
// 정책 › 미국 screen already renders, so the two screens can never disagree
// about which committees exist, and a chip can hand its committee_id straight
// to that screen. Static local servers have no /api/*, so a failure resolves
// to null and the panel falls back to a plain link rather than throwing.
export const loadUsCommittees = () => {
    if (!committeesPromise) {
        committeesPromise = fetch('/api/us/congress/overview', { cache: 'no-store' })
            .then((response) => (response.ok ? response.json() : null))
            .then((data) => (data?.congress_overview?.committees || null))
            .catch(() => null);
    }
    return committeesPromise;
};

let eopPromise = null;

// The EOP org chart: institutional structure, edited as content rather than
// collected, so it is a plain file rather than a pipeline asset. A failure
// resolves to null and usa-executive.js keeps its built-in copy.
export const loadEopChart = () => {
    if (!eopPromise) {
        eopPromise = fetch('/public/data/elections_us_eop_v1.json', { cache: 'force-cache' })
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null);
    }
    return eopPromise;
};
