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

// Explain the SAME assessment used by the office tally. Historical cards can
// show a numerical leader without contributing to the selected recent window.
export const pollSummaryNote = (race, context, days = 7) => {
    days = days === 14 ? 14 : 7;
    const assessment = pollRaceAssessment(race, context, days);
    const labels = {dem:'DEM 수치상 우세', rep:'GOP 수치상 우세', within:'오차구간 겹침',
        mixed:'동률·조사 방향 엇갈림', other:'제3당·무소속 앞섬',
        missing:'기간 내 채택 조사 없음', reference:'참고 조사만 있음', conflict:'수치 상충',
        review:'대진·자료 검토 필요', singleCandidate:'단독 후보 명부',
        unavailable:'자료 연결 대기', closed:'공식 결과 대기', certified:'공식 확정'};
    const window = assessment.window;
    const details = [];
    if (window) details.push(`집계 기간 ${window.from}~${window.through}`);
    const observations = race?.observations || [];
    const latest = observations.map((row) => row.field_end || '').filter((day) => /^\d{4}-\d{2}-\d{2}$/.test(day)).sort().at(-1);
    if (latest) details.push(`누적 자료의 최신 조사 종료 ${latest}`);
    if (!assessment.rows.length && latest && window && latest < window.from) details.push('보유 조사는 선택 기간 밖이므로 최근 우세 합계에서 제외');
    const reasons = new Set(observations.filter((row) => row.aggregation_eligibility?.eligible === false)
        .flatMap((row) => row.aggregation_eligibility.reasons || []));
    const exclusions = [];
    if (reasons.has('methodology_incomplete_reference')) exclusions.push('방법론 미확인');
    if (reasons.has('party_commissioned_reference') || reasons.has('party_internal_reference')) exclusions.push('정파 의뢰·내부 조사');
    if (reasons.has('forced_choice_after_undecided_probe')) exclusions.push('미정층 재질문');
    if (exclusions.length) details.push(`참고 전용 자료(${exclusions.join(' · ')})는 우세 합계에 포함하지 않음`);
    if (assessment.status === 'within') details.push('후보 지지율 차이가 있어도 확인된 후보별 오차구간이 겹쳐 이 항목으로 분류');
    if (context.stale) details.push('마지막 정상 수집 당시 기준이며 현재 판세 판정이 아님');
    return {status:assessment.status, label:`최근 ${days}일 요약: ${labels[assessment.status] || '자료 검토 필요'}`,
        detail:details.join(' · ')};
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
