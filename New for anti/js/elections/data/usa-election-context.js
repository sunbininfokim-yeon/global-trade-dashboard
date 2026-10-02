// A historical map key, not a forecast for the 2026 midterms. Cook's 2024
// Swing State Project covered these seven states. The remaining red/blue
// classification follows the certified 2024 presidential statewide winner.
export const SWING_STATES_2024 = new Set(['AZ', 'GA', 'MI', 'NV', 'NC', 'PA', 'WI']);
const BLUE_STATES_2024 = new Set([
    'CA', 'CO', 'CT', 'DE', 'HI', 'IL', 'ME', 'MD', 'MA', 'MN', 'NH',
    'NJ', 'NM', 'NY', 'OR', 'RI', 'VT', 'VA', 'WA', 'DC',
]);
const STATE_IDS = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

export const STATE_CLASSIFICATION_SOURCES = {
    winner: 'https://www.fec.gov/resources/cms-content/documents/2024presgeresults.pdf',
    swing: 'https://www.cookpolitical.com/analysis/survey-research/2024-swing-state-project/key-battlegrounds-trumps-best-bet-remains-high',
};

export const stateClass2024 = (stateId) => {
    if (!STATE_IDS.has(stateId)) return 'unknown';
    if (SWING_STATES_2024.has(stateId)) return 'swing';
    return BLUE_STATES_2024.has(stateId) ? 'blue' : 'red';
};

export const classColors = {
    blue: [37, 99, 235, 225],
    red: [220, 38, 38, 225],
    swing: [147, 51, 234, 230],
    unknown: [71, 85, 105, 230],
};

export const classLabels = {
    blue: '블루', red: '레드', swing: '스윙', unknown: '분류 없음',
};

export const normalizeParty = (party) => party === 'GOP' ? 'REP' : party === 'DFL' ? 'DEM' : party;

export const pollSourceReady = (board, health, now = Date.now()) => {
    if (!board || board.schema !== 'usa_live_polls_v1' || board.source_status !== 'ok' || health?.status !== 'ok') return false;
    const fetched = Date.parse(board.fetched_at);
    const hours = Number(board.stale_after_hours) || 48;
    return Number.isFinite(fetched) && now >= fetched && now - fetched <= hours * 3600000;
};

export const pollSignal = (race, board, health, days = 7, now = Date.now()) => {
    if (!race) return { status: 'unavailable', party: null };
    if (race.phase === 'certified_result' && race.result?.status === 'certified') {
        return { status: 'certified_result', party: normalizeParty(race.result.party), leader: race.result.winner };
    }
    if (race.phase === 'awaiting_certified_result') return { status: 'awaiting_certified_result', party: null };
    if (!pollSourceReady(board, health, now)) return { status: 'stale', party: null };
    const window = race.windows?.[String(days)];
    if (!window) return { status: 'unavailable', party: null };
    const party = window.status === 'poll_lead' ? normalizeParty(window.party) : null;
    return { status: window.status, party: party === 'DEM' || party === 'REP' ? party : null,
        leader: window.leader || null, window };
};
