// Recompute display windows from admitted observations between weekly runs.
// Source admission stays in the backend; this never admits a rejected record.
const DAY = 86400000;
const answerKey = (answers) => JSON.stringify([...answers].sort((a, b) => a.name.localeCompare(b.name))
    .map(({ name, pct, party }) => ({ name, pct, party })));

export const currentPollWindow = (race, days = 7, now = Date.now()) => {
    days = days === 14 ? 14 : 7;
    if (!Array.isArray(race?.observations)) return race?.windows?.[String(days)] || null;
    const through = new Date(now).toISOString().slice(0, 10);
    const from = new Date(Date.parse(`${through}T00:00:00Z`) - (days - 1) * DAY).toISOString().slice(0, 10);
    const inRange = race.observations.filter((p) => /^\d{4}-\d{2}-\d{2}$/.test(p.field_end || '')
        && p.field_end >= from && p.field_end <= through);
    const references = inRange.filter((p) => p.aggregation_eligibility?.eligible === false);
    let eligible = inRange.filter((p) => p.aggregation_eligibility?.eligible !== false);
    const population = eligible.some((p) => p.population === 'lv') ? 'lv' : 'rv';
    eligible = eligible.filter((p) => p.population === population);
    const groups = new Map();
    for (const row of eligible) {
        if (!row.pollster_group || !Array.isArray(row.answers) || row.answers.length < 2) continue;
        const rows = groups.get(row.pollster_group) || [];
        rows.push(row); groups.set(row.pollster_group, rows);
    }
    const chosen = [], conflicting = [];
    for (const [group, rows] of [...groups].sort(([a], [b]) => a.localeCompare(b))) {
        const latest = rows.map((p) => p.field_end).sort().at(-1);
        const wave = rows.filter((p) => p.field_end === latest);
        if (new Set(wave.map((p) => answerKey(p.answers))).size !== 1) conflicting.push(group);
        else chosen.push(wave.sort((a, b) => String(a.id).localeCompare(String(b.id)))[0]);
    }
    const counts = {}, parties = {};
    let ties = 0;
    for (const row of chosen) {
        const high = Math.max(...row.answers.map((a) => a.pct));
        const leaders = row.answers.filter((a) => a.pct === high);
        if (leaders.length !== 1) ties++;
        else {
            const leader = leaders[0];
            counts[leader.name] = (counts[leader.name] || 0) + 1;
            parties[leader.name] = leader.party;
        }
    }
    const most = Math.max(0, ...Object.values(counts));
    const leaders = Object.keys(counts).filter((name) => counts[name] === most);
    const name = leaders.length === 1 ? leaders[0] : null;
    let status = chosen.length ? 'tie' : 'no_recent_poll';
    let party = null;
    if (chosen.length && name && counts[name] > chosen.length / 2) {
        party = parties[name];
        status = party ? (chosen.length === 1 ? 'single_poll_lead' : 'poll_lead') : 'unknown_leader_party';
    }
    return { window_days: days, from, through, population: chosen.length ? population : null,
        status, party, leader: ['poll_lead', 'single_poll_lead'].includes(status) ? name : null,
        pollster_count: chosen.length, lead_counts: counts, tie_count: ties,
        included_ids: chosen.map((p) => p.id), conflicting_pollsters: conflicting,
        reference_ids: references.map((p) => p.id), reference_poll_count: references.length,
        status_note_ko: references.length && !chosen.length ? '기간 내 참고 전용 자료만 있으며 우세 집계에서는 제외합니다.' : null,
        latest_field_end: chosen.map((p) => p.field_end).sort().at(-1) || null,
        poll_details: chosen.map((p) => ({ id: p.id, source_quality: p.source_quality })) };
};
