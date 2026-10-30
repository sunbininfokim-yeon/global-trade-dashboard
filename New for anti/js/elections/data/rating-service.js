let inflight = null;
// Reviewed public snapshot, deliberately separate from automated polling.
export const loadUsaElectionRatings = () => {
    if (!inflight) inflight = fetch('/public/data/usa_election_ratings_review_v1.json', { cache: 'no-cache' })
        .then((r) => r.ok ? r.json() : null).catch(() => null).finally(() => { inflight = null; });
    return inflight;
};
