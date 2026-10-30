import { canCalculate, dayAge, sourceHref } from './israel-analysis.js';
import { groupSeatSummary } from './israel-context.js?v=2';

const categories = [
    ['likud', '리쿠드 측'], ['change', '반리쿠드 측'],
    ['arab', '아랍계'], ['independent', '그외'],
];

// A row is one reviewed poll, never a daily average or a filled-in day.
export const weeklySeatRows = (board, today) => (board?.observations || []).flatMap((poll) => {
    if (!canCalculate(poll, board) || !sourceHref(poll.source_url) || !poll.published_at) return [];
    const published = new Date(poll.published_at);
    if (!Number.isFinite(published.getTime())) return [];
    const publishedDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Jerusalem',
        year: 'numeric', month: '2-digit', day: '2-digit' }).format(published);
    const age = dayAge(publishedDay, today);
    const fieldAge = dayAge(poll.field_end, today);
    if (age === null || age < 0 || age >= 7 || fieldAge === null || fieldAge < 0) return [];
    const groups = categories.map(([id, label]) => {
        const context = board.coalition_context?.groups?.find((g) => g.id === id);
        return { id, label, color: /^#[0-9a-fA-F]{6}$/.test(context?.color) ? context.color : '#a6b3c8',
            ...groupSeatSummary(board, poll, id) };
    });
    // Missing classification must not silently shorten a 120-seat bar.
    if (groups.reduce((sum, g) => sum + (g.total ?? 0), 0) !== 120) return [];
    return [{ poll, publishedDay, groups }];
}).sort((a, b) => Date.parse(b.poll.published_at) - Date.parse(a.poll.published_at));
