import { escapeHtml } from '../../ui.js';
import { normalizeParty, raceClosedByDate } from '../../data/usa-election-context.js?v=2';
import { latestPollHtml, pollEvidenceHtml } from './usa-election-evidence.js?v=4';
import { ballotPartyLabel, pollMatchesMatchup } from '../../data/election-matchups.js';

const partyLabel = (p) => normalizeParty(p) === 'DEM' ? 'DEM' : normalizeParty(p) === 'REP' ? 'GOP' : p || '정당 미확인';
const nameKey = (value) => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').split(/\s+/).filter(Boolean).sort().join(' ');
const money = (cents) => cents == null ? '미수집·미확인' : `$${(cents / 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
const categoriesFor = (race, contract) => race?.office === 'governor' ? contract?.governor_independent_expenditure_categories || [] : contract?.federal_superpac_categories || ['super_pac'];
const total = (totals, categories, field) => {
    const values = categories.map((c) => totals?.[c]?.[field]).filter((n) => Number.isFinite(n));
    return values.length ? values.reduce((a,b) => a + b,0) : null;
};
export const matchFinanceCandidate = (name, info, race) => {
    const rows = (race?.candidates || []).filter((row) => {
        if (info?.candidate_id) return row.candidate_id === info.candidate_id;
        return (row.reported_names || [row.name]).some((n) => [name, ...(info?.finance_name_aliases || [])].some((alias) => nameKey(n) === nameKey(alias)))
            && (row.reported_parties || []).some((p) => normalizeParty(p) === normalizeParty(info?.party));
    });
    return rows.length === 1 ? rows[0] : null;
};
// Federal G2026 and explicit state general-phase records are the only inputs
// to the matchup amount. A cycle label alone cannot identify a ballot phase.
export const candidateGeneralMoney = (candidate, race, contract) => {
    const buckets = Object.entries(candidate?.election_types || {}).filter(([key]) => key === 'G2026');
    const categories = categoriesFor(race, contract);
    let support = null, oppose = null;
    for (const [, node] of buckets) {
        const s = total(node.totals_by_category, categories, 'support_cents');
        const o = total(node.totals_by_category, categories, 'oppose_cents');
        if (s != null) support = (support ?? 0) + s;
        if (o != null) oppose = (oppose ?? 0) + o;
    }
    if (!buckets.length) {
        for (const allocation of candidate?.allocations || []) {
            const explicit = allocation.election_type === 'G2026'
                || (allocation.ballot_year === 2026 && allocation.phase === 'general');
            if (!explicit || !categories.includes(allocation.spender_category) || !Number.isFinite(allocation.amount_cents)) continue;
            if (allocation.support_oppose === 'S') support = (support ?? 0) + allocation.amount_cents;
            if (allocation.support_oppose === 'O') oppose = (oppose ?? 0) + allocation.amount_cents;
        }
    }
    return {support, oppose};
};
const safeLink = (url, label) => {
    try { const u = new URL(url); return u.protocol === 'https:' ? `<a href="${escapeHtml(u.href)}" target="_blank" rel="noopener noreferrer">${label}</a>` : ''; } catch { return ''; }
};
const amountBoxes = ({support, oppose}) => `<div class="elections-candidate-money"><div><span>지지 지출</span><strong>${escapeHtml(money(support))}</strong></div><div><span>반대 지출</span><strong>${escapeHtml(money(oppose))}</strong></div></div>`;

export const candidateMatchupHtml = (pollRace, financeRace, contract, board, health, days = 7, { showPolls = true, now = Date.now(), matchup = null, openPrimary = false } = {}) => {
    const fallback = pollRace?.schedule_status === 'reported_general_matchup' ? pollRace.required_candidates || [] : [];
    const nominees = matchup?.candidates || fallback.map((name) => ({name, ...pollRace.candidates?.[name]}));
    const names = nominees.map((c) => c.name);
    const absent = matchup?.absent_parties || [];
    const missingParty = (party) => `<article class="elections-matchup-candidate ${party === 'DEM' ? 'is-dem' : 'is-gop'}"><header><span>${ballotPartyLabel(party)}</span><strong>${absent.includes(party) ? '본선 후보 없음' : '명부 확인 필요'}</strong></header><small>${absent.includes(party) ? '검토한 본선 명부 기준' : '후보가 아직 결정되지 않았다는 뜻은 아닙니다.'}</small></article>`;
    const closed = raceClosedByDate(pollRace || {election_date:'2026-11-03'},now) || ['certified_result','awaiting_certified_result'].includes(pollRace?.phase);
    const result = pollRace?.result?.status === 'certified' ? `<p>공식 확정 승자: ${escapeHtml(pollRace.result.winner)} ${safeLink(pollRace.result.source_url,'공식 결과')}</p>` : '';
    return `<div class="elections-candidate-matchup">
        <p class="elections-matchup-title"><strong>${closed ? '선거 결과' : '이번 선거 구도'}</strong>${result || (openPrimary ? '<span>11월 3일 공개 경선 · 필요 시 12월 결선</span>' : !names.length ? '<span>본선 명부 연결 대기</span>' : '')}</p>
        ${names.length ? `<p class="elections-matchup-versus">${names.map(escapeHtml).join(' <span>vs</span> ')}</p>` : ''}<div class="elections-matchup-candidates">${['DEM','REP',...new Set(nominees.map((c) => normalizeParty(c.party)).filter((p) => !['DEM','REP'].includes(p)))].map((party) => {
            const group = nominees.filter((c) => normalizeParty(c.party) === party);
            if (!group.length) return missingParty(party);
            return group.map((info) => {
            const name = info.name;
            const candidate = matchFinanceCandidate(name,info,financeRace);
            const amounts = candidateGeneralMoney(candidate,financeRace,contract);
            return `<article class="elections-matchup-candidate ${normalizeParty(info?.party) === 'DEM' ? 'is-dem' : normalizeParty(info?.party) === 'REP' ? 'is-gop' : ''}"><header><span>${escapeHtml(partyLabel(info?.party))}</span><strong>${escapeHtml(name)}</strong></header>
                ${amountBoxes(amounts)}<small>${safeLink(info?.source_url,'후보 대진 근거')}${!candidate ? ' · 공시 후보 연결 미확인' : ''}</small></article>`;
            }).join('');
        }).join('')}</div>
        ${matchup ? `<p class="elections-panel-note">${matchup.status === 'certified_ballot' ? '공식 인증 본선 명부' : '공개 보도·검토한 주요 본선 후보'} · ${escapeHtml(matchup.reviewed_on || '기존 검토')} ${safeLink(matchup.source_url,'명부 출처')}${matchup.coverage !== 'complete_ballot' ? ' · 제3당·기명투표 후보 전체 명부는 별도 확인 필요' : ''}</p>` : ''}
        <p class="elections-panel-note">2026 본선으로 구분된 외부 독립지출만 후보 옆에 표시합니다. 미수집·미확인은 0달러가 아닙니다.</p>
        ${showPolls ? !pollRace ? '<p class="elections-panel-note">여론조사 감시 미연결 · 후보 명부와 별도로 연결해야 합니다.</p>'
            : pollMatchesMatchup(pollRace,matchup) ? latestPollHtml(pollRace,board,health,now) + pollEvidenceHtml(pollRace,board,health,days)
            : '<p class="elections-panel-note">여론조사 후보와 본선 명부 대조 필요 · 조사 우세 표시 보류</p>' : ''}
    </div>`;
};

export const spendingHistoryHtml = (race, contract) => {
    const categories = categoriesFor(race,contract);
    const rows = [];
    for (const candidate of race?.candidates || []) {
        const buckets = Object.entries(candidate.election_types || {});
        if (!buckets.length) rows.push({name:candidate.name,phase:'선거 구분 미확인 · 본선 금액에서 제외',totals:candidate.totals_by_category});
        for (const [key,node] of buckets) {
            if (key === 'G2026') continue;
            const phase = /^P2026/.test(key) ? '2026 경선' : /^G\d{4}$/.test(key) ? `${key.slice(1)} 과거 본선` : /^P\d{4}$/.test(key) ? `${key.slice(1)} 과거 경선` : `선거 구분 미확인 (${key})`;
            rows.push({name:candidate.name,phase,totals:node.totals_by_category});
        }
    }
    const observed = rows.filter((r) => categories.some((key) => Number.isFinite(r.totals?.[key]?.support_cents) || Number.isFinite(r.totals?.[key]?.oppose_cents)));
    return `<details class="elections-disclosure elections-spending-history"><summary>경선·과거·구분 미확인 공시 ${observed.length}건</summary>
        ${observed.map((r) => `<article><strong>${escapeHtml(r.name)}</strong><small>${escapeHtml(r.phase)}</small>${amountBoxes({support:total(r.totals,categories,'support_cents'),oppose:total(r.totals,categories,'oppose_cents')})}</article>`).join('') || '<p class="elections-muted">분리해 표시할 관측 공시가 없습니다. 경선 지출이 없었다는 뜻은 아닙니다.</p>'}
        <p class="elections-panel-note">공시의 선거 구분을 그대로 표시합니다. 후보·공시 전체 명부가 아닙니다.</p></details>`;
};
