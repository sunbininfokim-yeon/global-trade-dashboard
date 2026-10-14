import { normalizeParty, stateClass2024, STATE_CLASSIFICATION_SOURCES, pollSignal, raceClosedByDate } from './usa-election-context.js?v=2';
import { electionMatchup, pollMatchesMatchup } from './election-matchups.js';

export const ELECTION_OFFICES = [['governor', '주지사'], ['senate', '연방 상원'], ['house', '연방 하원']];
const DAY = 86400000;
const partyKey = (value) => normalizeParty(value) === 'REP' ? 'GOP' : normalizeParty(value);
const countMembers = (members) => {
    if (!Array.isArray(members)) return null;
    const counts = { DEM: 0, GOP: 0, IND: 0, unknown: 0 };
    for (const member of members) {
        const key = partyKey(member?.abbr);
        if (key === 'DEM' || key === 'GOP' || key === 'IND') counts[key]++;
        else counts.unknown++;
    }
    return counts;
};
const summaryCounts = (value) => {
    if (!value || !Object.values(value).every((n) => Number.isInteger(n) && n >= 0)) return null;
    return { DEM: value.DEM ?? 0, GOP: value.GOP ?? value.REP ?? 0, IND: value.IND ?? 0,
        unknown: Object.entries(value).filter(([key]) => !['DEM', 'GOP', 'REP', 'IND'].includes(key)).reduce((n, [, v]) => n + v, 0) };
};

export const currentElectionSeats = (country, state = null) => {
    const congress = country?.ui_ready?.congress;
    const summary = congress?.summary || {};
    const states = country?.ui_ready?.state_drilldown?.states;
    if (!state) return {
        governor: { counts: Array.isArray(states) ? countMembers(states.map((s) => s.governor)) : null,
            total: Array.isArray(states) ? states.length : null, vacancies: null },
        senate: { counts: summaryCounts(summary.senate_by_party), total: 100, vacancies: null },
        house: { counts: summaryCounts(summary.house_by_party), total: summary.house_voting_seats ?? null,
            vacancies: summary.house_vacancies ?? null },
    };
    const delegation = state.federal_delegation || {};
    const members = Array.isArray(delegation.house_members)
        ? delegation.house_members.filter((m) => !m.is_delegate) : null;
    const vacancies = Array.isArray(congress?.vacancies)
        ? congress.vacancies.filter((v) => v.chamber === 'house' && v.state === state.id).length : null;
    return {
        governor: { counts: state.governor ? countMembers([state.governor]) : null, total: 1, vacancies: null },
        senate: { counts: countMembers(delegation.senators), total: 2, vacancies: null },
        house: { counts: countMembers(members), total: members && vacancies !== null ? members.length + vacancies : null, vacancies },
    };
};

const RATINGS = new Set(['solid_dem', 'likely_dem', 'lean_dem', 'toss_up', 'lean_rep', 'likely_rep', 'solid_rep']);
const competitive = (rating) => ['lean_dem', 'lean_rep', 'toss_up'].includes(rating);
const stableParty = (rating) => ['solid_dem', 'likely_dem'].includes(rating) ? 'DEM'
    : ['solid_rep', 'likely_rep'].includes(rating) ? 'GOP' : null;

// Preserve Cook's original rating. A user-defined caution is a separate flag,
// not a claim that Cook assessed the district as a toss-up.
export const classifyElectionRace = (race, country) => {
    const reasons = [];
    if (race.race_id.includes(':house:')) {
        const stateClass = stateClass2024(race.state);
        if ((stateClass === 'blue' && race.cook_held_party === 'GOP')
            || (stateClass === 'red' && race.cook_held_party === 'DEM')) {
            reasons.push({ criterion: 'state_presidential_held_party_mismatch',
                basis_ko: `2024 대선 ${stateClass === 'blue' ? '민주' : '공화'} 승리 주 · Cook 표기 ${race.cook_held_party === 'DEM' ? '민주' : '공화'} 보유 지역구 (주 전체 기준)`,
                source_url: STATE_CLASSIFICATION_SOURCES.winner });
        }
        for (const record of country?.ui_ready?.congress?.swing_seats || []) {
            if (record.chamber !== 'house' || record.state !== race.state || record.district !== race.district) continue;
            const evidence = record.evidence || [];
            const sourcesKnown = evidence.length > 0 && evidence.every((e) => /^https:\/\//.test(e.source_url || ''));
            // An unchanged at-large state can be reconciled; numbered districts
            // require an explicitly reviewed 2026 boundary lineage.
            const sameBoundary = record.boundary_lineage_verified === true || race.district === '00';
            const parties = evidence.map((e) => partyKey(e.party_abbr));
            const changes = parties.slice(1).filter((p, i) => p !== parties[i]).length;
            const validHistory = record.criterion === 'two_party_changes_last_three_general_elections'
                && evidence.length === 3 && evidence.map((e) => e.year).join(',') === '2020,2022,2024'
                && parties.every((p) => ['DEM', 'GOP'].includes(p)) && changes >= 2;
            const validSplit = record.criterion === 'presidential_congressional_split_ticket'
                && evidence.some((e) => e.year === 2024 && ['DEM', 'GOP'].includes(partyKey(e.presidential_party_abbr))
                    && ['DEM', 'GOP'].includes(partyKey(e.party_abbr)) && partyKey(e.presidential_party_abbr) !== partyKey(e.party_abbr));
            if (sourcesKnown && sameBoundary && (validHistory || validSplit)) reasons.push({
                criterion: record.criterion, basis_ko: record.basis_ko, source_url: evidence.at(-1).source_url,
            });
        }
    }
    const additional = reasons.length > 0 && !competitive(race.rating);
    return { ...race, effective_rating: additional ? 'toss_up' : race.rating, additional, reasons };
};

export const electionRatingSummary = (ratings, office, country = null, stateId = null, now = Date.now(), { resultsOnly = false } = {}) => {
    const row = ratings?.schema === 'usa_election_ratings_review_v1' && ratings.cycle === 2026 ? ratings.offices?.[office] : null;
    const date = Date.parse(`${row?.as_of}T00:00:00Z`);
    const expected = { house: 435, senate: 35, governor: 36 }[office];
    // After election day, an old reviewed universe may reconcile certified
    // results, but cannot supply stale Cook-based assumptions or rating tiles.
    const afterElection = raceClosedByDate({ election_date: '2026-11-03' }, now);
    if (!Number.isFinite(date) || now < date || (now - date > 21 * DAY && !(resultsOnly && afterElection)) || !Array.isArray(row?.races)
        || row.races.length !== expected || row.total_contests !== expected
        || new Set(row.races.map((r) => r.race_id)).size !== expected
        || row.races.some((r) => !RATINGS.has(r.rating) || !/^USA:[A-Z]{2}:(?:house:\d{2}|senate|governor)$/.test(r.race_id)
            || r.race_id !== `USA:${r.state}:${office}${office === 'house' ? `:${r.district}` : ''}`)) return null;
    const races = row.races.filter((r) => !stateId || r.state === stateId).map((r) => classifyElectionRace(r, country));
    const count = (rating) => races.filter((r) => r.effective_rating === rating).length;
    const leanDem = count('lean_dem'), leanRep = count('lean_rep');
    return { blue: count('solid_dem') + count('likely_dem'), red: count('solid_rep') + count('likely_rep'),
        leanDem, leanRep, lean: leanDem + leanRep, toss: count('toss_up'),
        cookBlue: races.filter((r) => stableParty(r.rating) === 'DEM').length,
        cookRed: races.filter((r) => stableParty(r.rating) === 'GOP').length,
        cookToss: races.filter((r) => r.rating === 'toss_up').length, additional: races.filter((r) => r.additional),
        contested: races.length, races, asOf: row.as_of, sourceUrl: row.source_url, afterElection };
};

const retainedMembers = (country, office, rating, state) => {
    if (office === 'house') return [];
    const states = state ? [state] : country?.ui_ready?.state_drilldown?.states;
    if (!Array.isArray(states) || (!state && states.length !== 50)) return null;
    const contests = new Map(rating.races.map((r) => [r.state, r]));
    const result = [];
    for (const s of states) {
        const contest = contests.get(s.id);
        if (office === 'governor') {
            if (!contest) { if (!s.governor) return null; result.push(s.governor); }
        } else {
            const senators = s.federal_delegation?.senators;
            if (!Array.isArray(senators) || senators.length !== 2) return null;
            const retained = contest ? senators.filter((m) => m.senate_class !== contest.senate_class) : senators;
            if (retained.length !== (contest ? 1 : 2)) return null;
            result.push(...retained);
        }
    }
    return result;
};

// This is a conditional tally, not an election call or a probability. Stable
// Cook races form a baseline; Lean/Toss-up and user-added races require polls.
export const electionOutlook = (country, office, rating, { state = null, board = null, health = null, days = 7, now = Date.now() } = {}) => {
    if (!rating) return null;
    const retained = retainedMembers(country, office, rating, state);
    const counts = countMembers(retained);
    if (!counts) return null;
    const retainedCounts = { ...counts };
    let contestedCurrentCounts = null;
    if (office === 'senate') {
        const states = state ? [state] : country?.ui_ready?.state_drilldown?.states;
        const contested = rating.races.flatMap((r) => states.find((s) => s.id === r.state)?.federal_delegation?.senators?.filter((m) => m.senate_class === r.senate_class) || []);
        if (contested.length !== rating.contested) return null;
        contestedCurrentCounts = countMembers(contested);
    }
    let pending = counts.unknown;
    delete counts.unknown;
    let single = 0, pollResolved = 0, certified = 0;
    for (const race of rating.races) {
        const pollRace = board?.races?.[race.race_id];
        const raceState = state || country?.ui_ready?.state_drilldown?.states?.find((s) => s.id === race.state);
        const ballot = electionMatchup(raceState, race.race_id, pollRace, now);
        const signal = pollSignal(pollRace || { election_date: '2026-11-03' }, board, health, days, now);
        const party = partyKey(signal.party);
        if (signal.status === 'certified_result' && ['DEM', 'GOP', 'IND'].includes(party)) { counts[party]++; certified++; }
        else if (signal.status === 'awaiting_certified_result') pending++;
        else if (stableParty(race.effective_rating)) counts[stableParty(race.effective_rating)]++;
        else if (pollMatchesMatchup(pollRace, ballot) && ['poll_lead', 'single_poll_lead'].includes(signal.status) && ['DEM', 'GOP'].includes(party)) {
            counts[party]++; pollResolved++; if (signal.status === 'single_poll_lead') single++;
        } else pending++;
    }
    const total = retained.length + rating.contested;
    if (!state && total !== { house: 435, senate: 100, governor: 50 }[office]) return null;
    return { counts, pending, total, retained: retained.length, retainedCounts, contestedCurrentCounts, single, pollResolved, certified };
};
