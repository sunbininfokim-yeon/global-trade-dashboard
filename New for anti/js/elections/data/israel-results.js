// The separately dated media-reported count must never become an accepted poll.
export const validateIsraelResults = (data, board, today) => {
    if (data == null) return;
    const fail = () => { throw new Error('이스라엘 개표 결과의 검토 상태를 확인하지 못했습니다.'); };
    const validDate = (d) => typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d)
        && Number.isFinite(Date.parse(`${d}T00:00:00Z`)) && new Date(`${d}T00:00:00Z`).toISOString().slice(0,10) === d;
    const row = data.result_record;
    if (data.schema !== 'israel_post_election_v1' || data.cycle !== board.cycle
        || !validDate(data.evidence_as_of) || data.evidence_as_of > today
        || !validDate(data.result_as_of) || data.result_as_of > data.evidence_as_of
        || data.review_status !== 'partial' || data.official_table_verified !== false
        || data.government_status !== 'unverified'
        || ['official_certification_date','mandate_holder','mandate_date','government_formed'].some((k)=>data[k] !== null)
        || row?.question_id !== 'official_results' || row.unit !== 'seats' || row.cycle !== board.cycle
        || row.review_status !== 'partial' || row.average_eligible !== false || row.seat_sum !== 120
        || !Array.isArray(row.values) || !row.values.length) fail();
    const known = new Set(board.lists.map((l)=>l.id));
    if (new Set(row.values.map((v)=>v.list_id)).size !== row.values.length
        || row.values.some((v)=>!known.has(v.list_id) || !Number.isInteger(v.seats) || v.seats <= 0 || v.seats > 120)
        || row.values.reduce((sum,v)=>sum+v.seats,0) !== 120) fail();
    const votes = row.votes;
    if (!votes || ['counted','valid','invalid'].some((k)=>!Number.isInteger(votes[k]) || votes[k] <= 0)
        || votes.valid + votes.invalid !== votes.counted || !Number.isFinite(votes.turnout_pct)
        || votes.turnout_pct < 0 || votes.turnout_pct > 100) fail();
    const blocs = ['current_coalition','opposition','arab'].map((k)=>row.bloc_as_published?.[k]);
    if (blocs.some((n)=>!Number.isInteger(n) || n < 0) || blocs.reduce((a,b)=>a+b,0) !== 120) fail();
    if (!Array.isArray(data.sources) || !Array.isArray(data.steps) || !data.steps.length || !Array.isArray(data.fallback)) fail();
    const sources = new Map(data.sources.map((s)=>[s.id,s]));
    const safe = (url) => {try {const u=new URL(url);return u.protocol==='https:' && !u.username && !u.password;} catch {return false;}};
    if (sources.size !== data.sources.length || data.sources.some((s)=>!safe(s.url)
        || typeof s.body_opened !== 'boolean' || !validDate(s.checked_on) || s.checked_on > data.evidence_as_of)
        || !data.sources.some((s)=>s.body_opened && s.url === row.source_url)) fail();
    for (const step of [...data.steps,...data.fallback]) {
        if (!Array.isArray(step.source_ids) || !step.source_ids.length || step.source_ids.some((id)=>!sources.get(id)?.body_opened)) fail();
    }
    if (data.steps.some((s)=>!['conditional','reported_scheduled','reported_expected'].includes(s.status)
        || (s.status === 'conditional' ? s.date !== null : !validDate(s.date)))) fail();
};
