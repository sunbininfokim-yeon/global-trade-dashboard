const DATA_ROOT = '/public/data';
let currentPromise = null;
let expiresAt = 0;

const fetchJson = async (name) => {
    const response = await fetch(`${DATA_ROOT}/${name}`, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`${name} (${response.status})`);
    return response.json();
};

// Both files are optional until the backend PR is deployed. A failed request
// stays visible as unavailable; it must not silently become an empty poll.
export const loadLivePolls = () => {
    if (!currentPromise || Date.now() >= expiresAt) {
        expiresAt = Date.now() + 15 * 60 * 1000;
        currentPromise = Promise.all([
        fetchJson('usa_election_live_polls_v1.json'),
        fetchJson('usa_election_live_polls_status_v1.json'),
        // Lower-confidence layer (원문 미검토). Optional: missing just means none.
        fetchJson('usa_election_unreviewed_polls_v1.json').catch(() => null),
        ]).then(([board, health, unreviewed]) => {
            if (board && unreviewed?.schema === 'usa_election_unreviewed_polls_v1' && unreviewed.as_of === board.as_of) board.unreviewed = unreviewed;
            return { board, health };
        }).catch(() => {
            expiresAt = Date.now() + 60 * 1000;
            return { board: null, health: null };
        });
    }
    return currentPromise;
};
