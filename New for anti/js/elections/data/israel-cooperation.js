export const validateCooperation = (data, board, today) => {
    if (data == null) return;
    const fail=()=>{throw new Error('이스라엘 정당 관계의 검토 근거를 확인하지 못했습니다.');};
    const day=(d)=>typeof d==='string' && /^\d{4}-\d{2}-\d{2}$/.test(d) && Number.isFinite(Date.parse(d)) && new Date(d).toISOString().slice(0,10)===d;
    if(data.schema!=='israel_cooperation_review_v1' || !day(data.reviewed_on) || data.reviewed_on>today || !Array.isArray(data.profiles) || !Array.isArray(data.relations) || !data.sources)fail();
    const known=new Set(board.lists.map(p=>p.id)), ids=new Set(data.profiles.map(p=>p.list_id));
    const safe=(url)=>{try{const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password;}catch{return false;}};
    if(ids.size!==data.profiles.length || [...ids].some(id=>!known.has(id)))fail();
    if(Object.values(data.sources).some(s=>!safe(s.url)||typeof s.body_opened!=='boolean'||!day(s.checked_on)||s.checked_on>data.reviewed_on))fail();
    const refs=(r)=>Array.isArray(r.source_ids)&&r.source_ids.length&&r.source_ids.every(id=>data.sources[id]?.body_opened);
    for(const p of data.profiles){
        if(!['left','center','right','far-right','plural','unplaced'].includes(p.spectrum)||!p.spectrum_ko||!p.religion_ko||!p.issues_ko?.length||!refs(p))fail();
        const parts=p.components||[];
        if(new Set(parts.map(c=>c.id)).size!==parts.length||parts.some(c=>c.seats!==null||!refs(c)))fail();
    }
    if(new Set(data.relations.map(r=>r.id)).size!==data.relations.length)fail();
    for(const r of data.relations){
        if(!Array.isArray(r.parties)||new Set(r.parties).size!==r.parties.length||r.parties.length<2||r.parties.some(id=>!ids.has(id))
            ||!['talks','refusal','joint_principles'].includes(r.kind)||!['pre_election','post_election'].includes(r.phase)
            ||!day(r.event_date)||r.event_date>data.reviewed_on||((r.event_date>='2026-10-27')!==(r.phase==='post_election'))||!r.limit_ko||!refs(r))fail();
    }
};
// Sort evidence by time and scope, not a probability or recommendation ranking.
export const cooperationPartners = (board, anchor) => {
    const d=board.cooperation_review;
    if(!d)return [];
    return d.profiles.filter(p=>p.list_id!==anchor).map(p=>{
        const records=d.relations.filter(r=>r.parties.includes(anchor)&&r.parties.includes(p.list_id))
            .sort((a,b)=>(a.phase==='post_election'?0:1)-(b.phase==='post_election'?0:1)||b.event_date.localeCompare(a.event_date));
        return {...p,records,priority:records.some(r=>r.phase==='post_election')?0:records.length?1:2};
    }).sort((a,b)=>a.priority-b.priority||a.list_id.localeCompare(b.list_id));
};
