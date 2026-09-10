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
