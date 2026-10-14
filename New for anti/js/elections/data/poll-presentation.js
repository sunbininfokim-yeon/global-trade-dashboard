import { currentPollWindow } from './poll-window.js';
import { normalizeParty, pollSourceReady, raceClosedByDate } from './usa-election-context.js?v=2';

// Presentation only: these counts never feed the map, seat forecast or results.
// A stale, valid snapshot remains inspectable at its ORIGINAL collection date.
export const pollPresentationContext = (board, health, now = Date.now()) => {
    const fetched = Date.parse(board?.fetched_at);
    const available = board?.schema === 'usa_live_polls_v1' && board.source_status === 'ok'
        && Number.isFinite(fetched) && fetched <= now
        && /^\d{4}-\d{2}-\d{2}$/.test(board.as_of || '')
        && Number.isFinite(Date.parse(board.as_of)) && board.as_of <= new Date(now).toISOString().slice(0,10)
        && !(health?.as_of && health.as_of !== board.as_of);
    const stale = available && !pollSourceReady(board, health, now);
    return { available, stale, now: stale ? Date.parse(`${board.as_of}T12:00:00Z`) : now,
        collectedOn: available ? board.fetched_at.slice(0, 10) : null, actualNow: now };
};

// Compare candidate intervals, not a fabricated MOE of the difference.
// Only an explicitly reviewed sampling-MOE for this SAME population/sample is
// usable. Credibility/modelled/whole-survey error cannot become ballot MOE.
export const pollPrecision = (row) => {
    const quality = row?.source_quality;
    const p = quality?.reported_precision;
    const scope = String(p?.scope || '').toLowerCase().replace(/[_-]/g, ' ');
    const populationMatches = row?.population === 'lv' ? /\blv\b|likely/.test(scope)
        : row?.population === 'rv' && /\brv\b|registered/.test(scope);
    if (quality?.verification_level !== 'primary_toplines_checked'
        || !['margin_of_error', 'reported_margin_of_error', 'publisher_reported_margin_of_error',
            'publisher_reported_margin_of_sampling_error'].includes(p?.kind)
        || !Number.isFinite(p.half_width_pp) || p.half_width_pp <= 0 || p.half_width_pp >= 100
        || !populationMatches || !Number.isInteger(row.sample_n) || row.sample_n <= 0
        || quality.question_sample_n !== row.sample_n) return null;
    return { halfWidth: p.half_width_pp, scope: p.scope };
};

export const pollRowAssessment = (row) => {
    const answers = [...(row?.answers || [])].sort((a, b) => b.pct - a.pct);
    if (answers.length < 2 || answers.some((a) => !Number.isFinite(a.pct) || a.pct < 0 || a.pct > 100)) {
        return { status: 'review', precisionKnown: false };
    }
    const precision = pollPrecision(row);
    const margin = answers[0].pct - answers[1].pct;
    if (precision && margin <= precision.halfWidth * 2) {
        return { status: 'within', precisionKnown: true, margin, precision };
    }
    if (margin === 0) return { status: 'mixed', precisionKnown: !!precision, margin };
    const party = normalizeParty(answers[0].party);
    return { status: party === 'DEM' ? 'dem' : party === 'REP' ? 'rep' : party ? 'other' : 'review',
        precisionKnown: !!precision, margin, leader: answers[0].name, party, precision };
};

export const pollRaceAssessment = (race, context, days = 7) => {
    if (race?.phase === 'certified_result' && race.result?.status === 'certified') return { status: 'certified', rows: [] };
    if (race?.phase === 'awaiting_certified_result' || raceClosedByDate(race, context.actualNow)) {
        return { status: 'closed', rows: [] };
    }
    if (!context.available) return { status: 'unavailable', rows: [] };
    if (race?.schedule_status === 'single_candidate_ballot_listing') return { status: 'singleCandidate', rows: [] };
    if (race?.schedule_status !== 'reported_general_matchup') return { status: 'review', rows: [] };
    const sourceRows = (race.observations || []).filter((row) => row.aggregation_eligibility?.eligible === true
        && row.display_group === 'general' && row.contest_id === race.contest_id
        && (race.required_candidates || []).every((name) => row.answers?.some((a) => a.name === name)));
    const window = currentPollWindow({ ...race, observations: sourceRows }, days, context.now);
    const rows = sourceRows.filter((row) => window.included_ids.includes(row.id));
    if (!rows.length) return { status: window.conflicting_pollsters.length ? 'conflict'
        : (race.observations || []).some((row) => row.aggregation_eligibility?.eligible === false
            && row.field_end >= window.from && row.field_end <= window.through) ? 'reference' : 'missing', rows, window };
    const classified = rows.map(pollRowAssessment);
    const counts = classified.reduce((acc, row) => ({ ...acc, [row.status]: (acc[row.status] || 0) + 1 }), {});
    const majority = Object.keys(counts).find((key) => counts[key] > rows.length / 2);
    return { status: majority || 'mixed', rows, window, single: rows.length === 1,
        precisionUnknown: classified.some((row) => !row.precisionKnown) };
};

export const summarizePollPresentation = (races, board, health, days = 7, now = Date.now()) => {
    const context = pollPresentationContext(board, health, now);
    const summary = { watched: races.length, observed: 0, recent: 0, states: new Set(), single: 0,
        precisionUnknown: 0, dem: 0, rep: 0, within: 0, mixed: 0, other: 0, missing: 0,
        reference: 0, conflict: 0, review: 0, singleCandidate: 0, closed: 0, certified: 0, unavailable: 0 };
    for (const race of races) {
        if (race.observations?.length) summary.observed++;
        const assessment = pollRaceAssessment(race, context, days);
        summary[assessment.status]++;
        if (assessment.rows.length) { summary.recent++; summary.states.add(race.state); }
        if (assessment.single) summary.single++;
        if (assessment.precisionUnknown) summary.precisionUnknown++;
    }
    return { ...summary, states: summary.states.size, context };
};
