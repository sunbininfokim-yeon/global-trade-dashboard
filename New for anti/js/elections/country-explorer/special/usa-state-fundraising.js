import { escapeHtml } from '../../ui.js';
import { normalizeParty } from '../../data/usa-election-context.js?v=2';
import { electionMatchup } from '../../data/election-matchups.js?v=2';
import { matchFinanceCandidate } from './usa-candidate-matchup.js?v=4';
import { linkedCampaignRow, originLink } from './usa-candidate-context.js';

const money = (cents) => Number.isSafeInteger(cents) ? `$${(cents/100).toLocaleString('en-US',{maximumFractionDigits:2})}` : '미연결';
const bucket = () => ({amount:null,nominees:0,observed:0,overflow:false});
const add = (target,value) => {
    if (target.overflow) return;
    const sum=(target.amount ?? 0)+value;
    if (!Number.isSafeInteger(sum)) {target.overflow=true;target.amount=null;}
    else target.amount=sum;
};
const unique = (rows) => [...new Map(rows.map((r) => [JSON.stringify(r),r])).values()];
const emptySummary = (state,office) => ({office,state:state?.id,status:'not_connected',total:bucket(),parties:{DEM:bucket(),REP:bucket(),OTHER:bucket()},
    targetRaces:0,reviewedRaces:0,missingRosters:0,identityConflicts:0,duplicatesRemoved:0,sources:[],carriedForward:false});

// Reviewed ballot identities define the sum; neither FEC registration nor a
// financial file can promote a primary loser onto the current ballot.
export const stateFundraisingSummary = (state,office,financeRaces,board=null,now=Date.now()) => {
    const summary=emptySummary(state,office);
    if (!/^[A-Z]{2}$/.test(state?.id || '') || !['governor','senate','house'].includes(office)) return summary;
    const inScope = (r) => r?.state===state.id && r.office===office && r.schedule_status!=='watch_slot_unverified' && r.election_date==='2026-11-03'
        && r.race_id===`USA:${state.id}:${office}`+(office==='house'?`:${r.district}`:'');
    const targets=new Map([...Object.values(board?.races || {}),...Object.values(state.election_matchups || {})]
        .filter(inScope).map((r)=>[r.race_id,r]));
    summary.targetRaces=targets.size;
    const governor=state.governor_election;
    const noGovernor=office==='governor' && governor?.cycle===2026 && governor.election_in_cycle===false
        && Date.parse(`${governor.reviewed_on}T00:00:00Z`)<=now;
    const senators=state.federal_delegation?.senators || [];
    const noSenate=office==='senate' && !targets.size && senators.length===2 && senators.every((s)=>s.up_in_2026===false);
    if (noGovernor || noSenate) {summary.status='not_scheduled';return summary;}
    const byRace=new Map();
    for (const r of financeRaces || []) {
        if (office==='governor') continue; // State campaign adapter is not implemented.
        if (r?.office!==office || (r.state_id || r.state)!==state.id || Number(r.cycle)!==2026) continue;
        const records=byRace.get(r.race_id)||[];records.push(r);byRace.set(r.race_id,records);
    }
    const identities=new Map();
    for (const [rid] of targets) {
        const matchup=electionMatchup(state,rid,board?.races?.[rid],now);
        if (!matchup) {summary.missingRosters++;continue;}
        summary.reviewedRaces++;
        const copies=unique(byRace.get(rid)||[]);
        summary.duplicatesRemoved+=(byRace.get(rid)?.length || 0)-copies.length;
        const race=copies.length===1?{...copies[0],candidates:unique(copies[0].candidates || [])}:null;
        if (copies.length>1) summary.identityConflicts++;
        for (const nominee of matchup.candidates) {
            const candidate=matchFinanceCandidate(nominee.name,nominee,race);
            const row=linkedCampaignRow(candidate,race,now);
            const party=normalizeParty(nominee.party);
            const key=nominee.candidate_id || candidate?.candidate_id || `${rid}|${party}|${nominee.name}`;
            const records=identities.get(key)||[];records.push({rid,party,name:nominee.name,row});identities.set(key,records);
        }
    }
    for (const records of identities.values()) {
        const entry=records[0];
        const party=['DEM','REP'].includes(entry.party)?entry.party:'OTHER';
        const b=summary.parties[party];b.nominees++;summary.total.nominees++;
        // Identical candidate appearances count once; conflicting offices,
        // parties or reports with the same identity are held in their entirety.
        const signature=(r)=>JSON.stringify([r.rid,r.party,r.row]);
        if (new Set(records.map(signature)).size>1) {summary.identityConflicts++;continue;}
        summary.duplicatesRemoved+=records.length-1;
        const row=entry.row,value=row?.amounts?.receipts_cents;
        if (!row || !Number.isSafeInteger(value)) continue;
        add(b,value);add(summary.total,value);b.observed++;summary.total.observed++;
        summary.carriedForward ||= !!row.carried_forward_reason;
        summary.sources.push({candidate_id:row.candidate_id,race_id:entry.rid,office,receipts_cents:value,name:entry.name,party:entry.party,source_url:row.source_url,
            coverage_end:row.coverage_end,collected_on:row.snapshot_as_of,bulk_url:row.source_receipts?.summary?.url,
            transfer_risk:row.transfer_double_count_risk===true});
    }
    summary.sources.sort((a,b)=>a.candidate_id.localeCompare(b.candidate_id));
    summary.status=office==='governor'?'state_adapter_not_connected':!summary.total.observed?'not_connected':summary.total.observed<summary.total.nominees
        || summary.missingRosters || summary.identityConflicts || summary.total.overflow?'partial':'reviewed_roster_connected';
    return summary;
};

export const stateFundraisingHtml = (state,office,financeRaces,board=null,contract=null,now=Date.now()) => {
    const s=stateFundraisingSummary(state,office,financeRaces,board,now);
    const title='<strong>펀드레이징 · 캠프 총수입</strong>';
    if (s.status==='not_scheduled') return `<div class="elections-office-fundraising">${title}<small>이번 선거 없음 · 비선거 현직 모금은 합산하지 않습니다.</small></div>`;
    if (s.status==='state_adapter_not_connected') return `<div class="elections-office-fundraising">${title}<small>주지사 캠프 모금 · 주별 공시 미연결</small></div>`;
    const dates=s.sources.map((r)=>r.coverage_end).sort(),collected=s.sources.map((r)=>r.collected_on).sort();
    const range=(values)=>values[0]===values.at(-1)?values[0]:`${values[0]}~${values.at(-1)}`;
    const delayed=s.carriedForward || contract?.source_status?.candidate_fundraising?.status==='failed_last_good_preserved';
    return `<div class="elections-office-fundraising" data-fundraising-office="${office}">${title}<small>이번 선거 검토 명부 · USD</small>
        <div class="elections-office-fundraising-parties">${[['DEM','DEM','is-dem'],['REP','GOP','is-gop']].map(([key,label,cls])=>{
            const b=s.parties[key];return `<div class="${cls}"><span>${label}</span><b>${escapeHtml(money(b.amount))}</b><small>검토 명부 ${b.nominees}명 · 금액 연결 ${b.observed}명</small></div>`;
        }).join('')}</div>
        <p>전체 관측 합계 <strong>${escapeHtml(money(s.total.amount))}</strong>${s.status==='partial'?' · 일부 집계':''}</p>
        ${s.parties.OTHER.nominees?`<small>기타·무소속 관측 ${escapeHtml(money(s.parties.OTHER.amount))} · ${s.parties.OTHER.observed}/${s.parties.OTHER.nominees}명 연결</small>`:''}
        <small>${s.targetRaces?`검토 명부 ${s.reviewedRaces}/${s.targetRaces}개 선거 · `:''}후보 ${s.total.observed}/${s.total.nominees}명 금액 연결${s.identityConflicts?` · 중복·신원 충돌 ${s.identityConflicts}건 보류`:''}${s.total.overflow?' · 합계 정밀도 재확인 필요':''}${delayed?' · 이전 유효 공시 보존':''}</small>
        ${dates.length?`<small>공시 기준 ${escapeHtml(range(dates))} · 수집 ${escapeHtml(range(collected))}</small>`:'<small>후보 명부 또는 모금 자료 연결 대기 · 0달러가 아닙니다.</small>'}
        <details class="elections-disclosure"><summary>합산 범위 · 후보별 원문</summary><p>이번 선거 검토 명부에 연결한 후보 캠프 총수입입니다. FEC 등록 후보 전체·경선 탈락자·비선거 현직·슈퍼팩을 더하지 않습니다. 총수입은 개인 기부만의 합계가 아니며 본인 출연·대출·이체를 포함합니다. 2026 이년 보고주기이며 본선 후보의 경선 기간 모금도 포함될 수 있습니다. 후보별 공시 기준일이 다를 수 있습니다. 누락은 0으로 채우지 않습니다.</p>
        ${s.sources.map((r)=>`<p>${escapeHtml(r.name)} · ${escapeHtml(r.party==='REP'?'GOP':r.party || '정당 미확인')} · 공시 ${escapeHtml(r.coverage_end)} ${originLink(r.source_url,'FEC 후보 원문 ↗')}${r.transfer_risk?' · 수권 위원회 이체 중복 위험':''}</p>`).join('')}
        ${s.sources.length?originLink(s.sources[0].bulk_url,'FEC 집계 원자료 ↗'):''}<p>이체를 임의로 차감한 순모금이 아닙니다. 여러 캠프 간 이체가 있으면 합산에도 중복 위험이 남으므로 후보별 원문을 확인합니다.</p></details></div>`;
};
