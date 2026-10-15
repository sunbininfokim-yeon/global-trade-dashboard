// A reviewed research snapshot. No seat-to-vote inversion, averaging or forecast.
export const koreaToday = (now = Date.now()) => new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(now);
const validDay = (day) => /^\d{4}-\d{2}-\d{2}$/.test(day || '')
    && Number.isFinite(Date.parse(`${day}T00:00:00Z`))
    && new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) === day;
export const dayAge = (day, today) => validDay(day) && validDay(today)
    ? Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / 86400000) : null;

export const validSeatPoll = (row, board) => {
    if (!row || row.question_id !== 'reported_seats' || row.unit !== 'seats'
        || !['accepted', 'partial'].includes(row.review_status)) return false;
    const known = new Set(board.lists.map((list) => list.id));
    const ids = new Set();
    const values = row.values || [];
    for (const value of values) {
        if (!known.has(value.list_id) || ids.has(value.list_id)
            || !Number.isInteger(value.seats) || value.seats < 0 || value.seats > 120) return false;
        ids.add(value.list_id);
    }
    return values.length > 0 && row.seat_sum === 120
        && values.reduce((total, value) => total + value.seats, 0) === 120;
};

export const validateIsraelBoard = (board, status, today = koreaToday()) => {
    if (board?.schema !== 'israel_election_analysis_v1' || board.iso3 !== 'ISR'
        || board.cycle !== 'knesset-26' || board.collection_mode !== 'reviewed_snapshot'
        || board.automatic_refresh !== false || !validDay(board.evidence_as_of)
        || !Array.isArray(board.lists) || !Array.isArray(board.observations)
        || board.assembly_seats !== 120 || board.arithmetic_majority !== 61
        || status?.schema !== 'israel_election_analysis_status_v1'
        || status.status !== 'reviewed_snapshot' || status.automatic_refresh !== false
        || status.evidence_as_of !== board.evidence_as_of || status.built_at !== board.built_at) {
        throw new Error('이스라엘 검토 자료와 상태 파일이 일치하지 않습니다.');
    }
    if (dayAge(board.evidence_as_of, today) === null || dayAge(board.evidence_as_of, today) < 0) {
        throw new Error('이스라엘 검토 자료의 기준일을 확인하세요.');
    }
    if (new Set(board.lists.map((list) => list.id)).size !== board.lists.length) throw new Error('명부 식별자가 중복됩니다.');
    const context = board.coalition_context;
    const translations = board.localization;
    if (context?.schema !== 'israel_coalition_context_v1' || !Array.isArray(context.groups)
        || !Array.isArray(context.parties) || !Array.isArray(context.relationships)
        || translations?.schema !== 'israel_ko_translations_v1' || translations.provider !== 'Google Gemini API'
        || !Array.isArray(translations.translations) || !translations.translations.length
        || translations.translations.some((row) => typeof row.ko !== 'string'
            || !/[가-힣]/u.test(row.ko) || /[\u0590-\u05ff]/u.test(row.ko))) {
        throw new Error('이스라엘 한국어 설명과 관계 자료를 확인하지 못했습니다.');
    }
    const polls = board.observations.filter((row) => row.question_id === 'reported_seats');
    if (polls.some((row) => row.review_status !== 'held' && !validSeatPoll(row, board))) {
        throw new Error('의석 조사 자료를 검증하지 못했습니다.');
    }
    return board;
};

export const seatPolls = (board, { days = null, today = koreaToday() } = {}) => {
    if (!board) return [];
    return board.observations.filter((row) => validSeatPoll(row, board))
        .filter((row) => {
            // Unknown fieldwork must not become a recent poll via publication date.
            const day = row.field_end || (days === null ? row.published_at?.slice(0, 10) : null);
            const age = dayAge(day, today);
            if (age === null || age < 0) return days === null && !day;
            return days === null || age < days;
        }).sort((a, b) => {
            const first = a.field_end || a.published_at?.slice(0, 10) || '';
            const second = b.field_end || b.published_at?.slice(0, 10) || '';
            return second.localeCompare(first) || String(b.published_at || '').localeCompare(String(a.published_at || ''));
        });
};

export const listSeats = (poll, listId) => poll?.values?.find((row) => row.list_id === listId)?.seats ?? null;
export const canCalculate = (poll, board) => poll?.review_status === 'accepted' && validSeatPoll(poll, board)
    && poll.scenario === 'actual_lists_if_election_today';

export const selectedSeatSum = (poll, selected, board) => {
    if (!canCalculate(poll, board)) return { status: 'held', total: null, gap: null };
    const ids = [...new Set(selected)];
    const numbers = ids.map((id) => listSeats(poll, id));
    if (numbers.some((value) => value === null)) return { status: 'held', total: null, gap: null };
    const total = numbers.reduce((sum, number) => sum + number, 0);
    return { status: 'arithmetic_only', total, gap: Math.max(0, 61 - total), reachesMajority: total >= 61 };
};

export const sourceHref = (url) => {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' && !parsed.username && !parsed.password ? parsed.href : null;
    } catch { return null; }
};
