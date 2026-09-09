// Integration helper only: no DOM, map mutation, credentials, or deployment code.
export function createFinanceClient(fetcher = fetch, base = '/public/data/') {
    let catalogPromise;
    const cache = new Map();
    const load = async (path, fresh = false) => {
        if (!/^(usa_election_finance_(index|refresh_status)_v1\.json|usa_election_finance\/[A-Za-z0-9_/-]+\.json)$/.test(path)) throw new Error('Invalid finance asset reference');
        if (!fresh && cache.has(path)) return cache.get(path);
        const pending = fetcher(base + path, { cache: fresh ? 'no-store' : 'default' }).then(response => {
            if (!response.ok) throw new Error(`Finance asset unavailable: ${response.status}`);
            return response.json();
        });
        if (!fresh) cache.set(path, pending);
        try { return await pending; } catch (error) { cache.delete(path); throw error; }
    };
    const getCatalog = () => catalogPromise ||= load('usa_election_finance_index_v1.json', true).catch(error => { catalogPromise = null; throw error; });
    const getNational = async (cycle) => {
        const catalog = await getCatalog();
        const meta = catalog.cycles[String(cycle)];
        if (!meta) throw new Error('Reporting cycle not collected');
        return { data: await load(meta.national_file), sourceStatus: meta.source_status, limitations: meta.limitations_ko };
    };
    const getState = async (cycle, stateId) => {
        const { data } = await getNational(cycle);
        const state = data.states[stateId];
        if (!state) throw new Error('State not collected');
        return load(state.data_file);
    };
    const getRace = async (cycle, stateId, office, district = null) => {
        const state = await getState(cycle, stateId);
        const code = office === 'house' ? String(district).padStart(2, '0') : null;
        const summary = state.races.find(r => r.office === office && r.district === code);
        if (!summary) return null;
        return load(summary.data_file);
    };
    return { getCatalog, getNational, getState, getRace,
        getHealth: () => load('usa_election_finance_refresh_status_v1.json', true),
        refresh: () => { catalogPromise = null; } };
}

export function selectCandidateSpending(race, { phase = null, category = 'super_pac', party = null } = {}) {
    return race.candidates.filter(c => !party || c.reported_parties.includes(party)).map(candidate => {
        const allocations = Object.entries(candidate.election_types)
            .filter(([code]) => !phase || code === phase)
            .flatMap(([, value]) => value.allocations)
            .filter(row => (!category || row.category === category) && (!party || row.party === party));
        const sum = (key) => {
            if (!allocations.length) return null;
            const total = allocations.reduce((value, row) => value + row[key], 0);
            if (!Number.isSafeInteger(total)) throw new Error('Amount exceeds safe integer range');
            return total;
        };
        return { candidate_id: candidate.candidate_id, name: candidate.name,
            reported_parties: candidate.reported_parties, registration_status: candidate.registration_status,
            support_cents: sum('support_cents'), oppose_cents: sum('oppose_cents'),
            status: allocations.length ? 'observed_partial' : 'no_observed_records', allocations };
    });
}
