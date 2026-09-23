import { escapeHtml } from '../../ui.js';

// A Wikipedia-style hemicycle: seats spread over concentric arcs, each arc
// holding a share proportional to its radius, then coloured left to right in
// the order the groups are given. Seat position carries no meaning beyond the
// grouping -- no member is bound to a dot.
//
// Written for the US Congress screen first, then pulled out here because every
// chamber draws the same picture: 중의원·참의원, 전인대, a state legislature.
// The caller decides the seating order (the convention is 소수당 왼쪽,
// 다수당 오른쪽, 공석은 그 경계) and the colours; this file only places dots.
export const hemicycle = (groups) => {
    const total = groups.reduce((sum, group) => sum + group.count, 0);
    if (!total) return '';
    const rowCount = total > 300 ? 12 : total > 120 ? 8 : 5;
    const radii = Array.from({ length: rowCount }, (_, index) => 42 + 58 * (rowCount === 1 ? 0 : index / (rowCount - 1)));
    const weight = radii.reduce((sum, radius) => sum + radius, 0);
    const perRow = radii.map((radius) => Math.max(1, Math.round((total * radius) / weight)));
    for (let drift = total - perRow.reduce((a, b) => a + b, 0), i = perRow.length - 1; drift !== 0; i = (i - 1 + perRow.length) % perRow.length) {
        const step = drift > 0 ? 1 : -1;
        if (perRow[i] + step >= 1) { perRow[i] += step; drift -= step; }
    }
    const seats = [];
    radii.forEach((radius, rowIndex) => {
        const count = perRow[rowIndex];
        for (let index = 0; index < count; index += 1) {
            const t = count === 1 ? 0.5 : index / (count - 1);
            seats.push({ t, rowIndex, radius });
        }
    });
    seats.sort((a, b) => a.t - b.t || a.rowIndex - b.rowIndex);

    let cursor = 0;
    const dots = [];
    groups.forEach((group) => {
        for (let i = 0; i < group.count && cursor < seats.length; i += 1, cursor += 1) {
            const seat = seats[cursor];
            const angle = Math.PI * (1 - seat.t);
            const x = (100 + seat.radius * Math.cos(angle)).toFixed(2);
            const y = (104 - seat.radius * Math.sin(angle)).toFixed(2);
            dots.push(`<circle cx="${x}" cy="${y}" r="2.1" fill="${group.color}"${group.stroke ? ` stroke="${group.stroke}" stroke-width="0.7"` : ''}/>`);
        }
    });
    return `
        <svg class="elections-hemicycle" viewBox="0 0 200 112" role="img" aria-label="${escapeHtml(`의석 ${total}석 정당별 분포`)}">
            ${dots.join('')}
            <text x="100" y="100" text-anchor="middle" class="elections-hemicycle-total">${total}</text>
        </svg>`;
};

export const seatLegend = (groups) => `
    <div class="elections-seat-legend">
        ${groups.map((group) => `<span class="elections-seat-legend-item"><i style="background:${group.color}"></i>${escapeHtml(`${group.label} ${group.count}석`)}</span>`).join('')}
    </div>`;

// Minority left, majority right, everyone else between: the seating order the
// reference charts use. `entries` is [[key, seats], ...] already sorted by
// seats descending.
export const seatingOrder = (entries) => {
    if (entries.length < 2) return entries;
    const [majority, minority, ...rest] = entries;
    return [minority, ...rest, majority];
};
