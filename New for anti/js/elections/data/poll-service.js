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
        ]).then(([board, health]) => ({ board, health })).catch(() => {
            expiresAt = Date.now() + 60 * 1000;
            return { board: null, health: null };
        });
    }
    return currentPromise;
};
