import { escapeHtml } from '../../ui.js';
import { usaStateNameKo } from '../../data/election-matchups.js?v=2';

export const originLink = (url, label = '원문 ↗') => {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' && !parsed.username && !parsed.password
            ? `<a href="${escapeHtml(parsed.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : '';
    } catch { return ''; }
};
const reviewed = (day, now) => /^\d{4}-\d{2}-\d{2}$/.test(day || '') && Number.isFinite(Date.parse(`${day}T00:00:00Z`))
    && new Date(`${day}T00:00:00Z`).toISOString().slice(0,10) === day && Date.parse(`${day}T00:00:00Z`) <= now;
const usd = (value) => Number.isSafeInteger(value) ? `$${(value / 100).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 2})}` : '미수집·미확인';
const metric = (label, value) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(usd(value))}</strong></div>`;
export const ensureElectionContextStyle = () => {
    if (typeof document === 'undefined' || document.querySelector('link[data-election-context-style]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = new URL('./usa-candidate-context.css', import.meta.url).href;
    link.dataset.electionContextStyle = '1'; document.head.append(link);
};

const governorStatus = {
    term_limited_reported: '현직 연임 제한', running_reported: '현직 출마',
    not_seeking_reelection_reported: '현직 불출마', primary_defeated_reported: '현직 경선 탈락',
    not_on_cycle_ballot: '2026 주지사 선거 없음', incumbent_identity_conflict: '현직 신원 재확인 필요',
    not_verified: '현직 출마 사유 확인 중',
};
const validContext = (row, state, now) => /^[A-Z]{2}$/.test(state || '') && row?.state === state && row.cycle === 2026
    && typeof row.election_in_cycle === 'boolean' && reviewed(row.reviewed_on, now)
    && originLink(row.source?.url || row.source?.source_url)
    && (row.election_in_cycle ? row.race_id === `USA:${state}:governor` && row.election_date === '2026-11-03' : row.race_id == null && row.election_date == null);
export const governorContextHtml = (state, now = Date.now()) => {
    const row = state?.governor_election;
    if (!validContext(row, state?.id, now)) return '<p class="elections-panel-note">주지사 선거·현직 출마 정보 연결 대기</p>';
    return `<div class="elections-governor-context"><strong>${row.election_in_cycle ? '2026-11-03 주지사 선거' : '2026 주지사 선거 없음'}</strong>
        <p>${escapeHtml(row.incumbent?.name || '현직 명부 확인 필요')} · ${escapeHtml(governorStatus[row.incumbent_ballot_status] || '출마 정보 확인 중')}</p>
        <small class="elections-origin-links">${originLink(row.source.url || row.source.source_url, '선거·출마 사유 원문 ↗')}${row.source.source_grade === 'secondary_explicit_note' ? '<span>270toWin 명시 노트 · 2차 출처</span>' : ''}<span>검토 ${escapeHtml(row.reviewed_on)}</span></small>
        ${row.legal_rule_review ? `<small class="elections-origin-links">${originLink(row.legal_rule_review.source_url || row.legal_rule_review.url, '연임 제한 법령 ↗')}</small>` : ''}</div>`;
};
export const governorElectionSummaryHtml = (country, now = Date.now()) => {
    const context = country?.ui_ready?.state_drilldown?.governor_elections;
    const rows = Object.values(context?.states || {});
    if (context?.schema !== 'usa_governor_election_context_v1' || rows.length !== 50
        || !rows.every((r) => validContext(r, r.state, now)) || new Set(rows.map((r) => r.state)).size !== 50) return '';
    const contested = rows.filter((r) => r.election_in_cycle).length;
    return `<div class="elections-governor-context"><div class="elections-gov-scope"><span>이번 선거 <strong>${contested}주</strong></span><span>비선거 <strong>${50-contested}주</strong></span></div>
        <details class="elections-disclosure"><summary>주별 선거·현직 출마 사유와 원문</summary>
        <p class="elections-panel-note">연임 제한·자진 불출마·경선 탈락은 구분합니다. 현직의 불출마가 후보 미확정을 뜻하지 않습니다.</p>
        <div class="elections-governor-list">${rows.sort((a,b) => a.state.localeCompare(b.state)).map((r) => `<div><button type="button" data-overview-state="${r.state}" data-overview-office="governor" data-overview-district=""><strong>${escapeHtml(usaStateNameKo(r.state))} · ${r.election_in_cycle ? '선거' : '비선거'}</strong><span>${escapeHtml(governorStatus[r.incumbent_ballot_status] || '확인 중')}</span></button>${originLink(r.source.url || r.source.source_url, '근거 ↗')}</div>`).join('')}</div></details></div>`;
};

export const campaignFundraisingHtml = (candidate, race, contract, now = Date.now()) => {
    const row = candidate?.campaign_fundraising;
    if (race?.office === 'governor') return '<div class="elections-campaign-summary is-missing"><strong>후보 캠프 모금</strong><small>주별 캠프 공시 미연결 · 연방 FEC·슈퍼팩 금액으로 대신 채우지 않습니다.</small></div>';
    const linked = row?.status === 'reported_campaign_summary_ballot_unverified'
        && row.candidate_id === candidate?.candidate_id && row.race_id === race?.race_id
        && row.state === (race?.state_id || race?.state) && row.office === race?.office
        && row.election_year === 2026 && Number(race?.cycle) === 2026
        && row.currency === 'USD' && row.amount_unit === 'cents' && row.includes_outside_spending === false
        && reviewed(row.coverage_end, now) && reviewed(row.snapshot_as_of, now)
        && row.amounts && originLink(row.source_url);
    if (!linked) return `<div class="elections-campaign-summary is-missing"><strong>후보 캠프 모금</strong><small>${row?.status === 'candidate_identity_scope_conflict' || row?.amounts ? '후보·지역구·공시 범위 대조 필요 · 금액 보류' : '캠프 모금 자료 연결 대기 · 0달러가 아닙니다.'}</small></div>`;
    const a = row.amounts, health = contract?.source_status?.candidate_fundraising;
    const delayed = row.carried_forward_reason || health?.status === 'failed_last_good_preserved';
    return `<section class="elections-campaign-summary" aria-label="후보 캠프 모금과 현금"><strong>후보 캠프 모금${delayed ? ' · 이전 유효 공시 보존' : ''}</strong>
        <div class="elections-campaign-metrics">${metric('개인 기부', a.individual_contributions_cents)}${metric('캠프 보유 현금', a.cash_on_hand_cents)}${metric('캠프 총수입', a.receipts_cents)}${metric('캠프 지출', a.disbursements_cents)}</div>
        <small>공시 기준 ${escapeHtml(row.coverage_end)} · 수집 ${escapeHtml(row.snapshot_as_of)} · USD · 2026 이년 보고주기</small>
        <small class="elections-origin-links">${originLink(row.source_url, 'FEC 후보 공시 원문 ↗')}${originLink(row.source_receipts?.summary?.url, 'FEC 집계 원자료 ↗')}</small>
        <details class="elections-disclosure"><summary>본인 출연·대출·부채와 산정 범위</summary><div class="elections-campaign-metrics">${metric('후보 본인 출연', a.candidate_contributions_cents)}${metric('후보 본인 대출', a.candidate_loans_cents)}${metric('기타 대출', a.other_loans_cents)}${metric('부채', a.debts_owed_cents)}${metric('수권 위원회 유입 이체', a.transfers_from_authorized_cents)}${metric('수권 위원회 유출 이체', a.transfers_to_authorized_cents)}</div>
        <p>총수입에는 대출·본인 출연·이체가 포함됩니다. 개인 기부와 별개이며 슈퍼팩 지출·후보 개인 재산과 합산하지 않습니다. 상원 6년 전체 모금이 아닙니다.</p>${row.transfer_double_count_risk ? '<p>수권 위원회 간 유입·유출 이체가 모두 있어 중복 위험이 있습니다. 임의 순모금을 계산하지 않습니다.</p>' : ''}</details></section>`;
};

export const candidateBiographyHtml = (candidate, now = Date.now()) => {
    const bio = candidate?.biography;
    if (!bio || bio.name !== candidate.name || bio.party !== candidate.party) return '';
    const field = (key, title, display) => {
        const f = bio[key];
        const valid = f?.value != null && ['verified','self_reported'].includes(f.status)
            && reviewed(f.reviewed_on, now) && f.evidence_locator && originLink(f.source_url)
            && (key !== 'race_ethnicity' || ['explicit_self_identification','explicit_official_biography'].includes(f.identity_basis));
        const value = valid ? display(f.value) : f?.status === 'source_unavailable' ? '원문 접근 장애 · 미확인' : '미확인';
        return `<div class="elections-biography-field"><span>${title}</span><div>${escapeHtml(value)}${valid ? `<small class="elections-origin-links">${originLink(f.source_url, '약력 원문 ↗')}<span>${f.status === 'self_reported' ? '캠프·본인 서술' : '공식 자료'} · 검토 ${escapeHtml(f.reviewed_on)}</span></small>` : ''}</div></div>`;
    };
    const career = (v) => Array.isArray(v) ? v.map((r) => typeof r === 'string' ? r : `${r.role_ko || r.role || ''}${r.from_year ? ` (${r.from_year}${r.to_year ? `–${r.to_year}` : '–'})` : ''}`).join(' · ') : typeof v === 'string' ? v : '확인 항목 없음';
    const born = (value) => {
        if (bio.birth_date.precision !== 'day' || !reviewed(value, now)) return '생년월일 미확인';
        const b = new Date(`${value}T00:00:00Z`), d = new Date(now);
        const age = d.getUTCFullYear()-b.getUTCFullYear()-Number(d.getUTCMonth()<b.getUTCMonth() || d.getUTCMonth()===b.getUTCMonth() && d.getUTCDate()<b.getUTCDate());
        return `${age}세 · ${value}생 (${d.toISOString().slice(0,10)} 기준)`;
    };
    return `<details class="elections-disclosure elections-candidate-biography"><summary>확인된 약력 · 원문 보기</summary>${field('birth_date','나이',born)}${field('career','주요 경력',career)}${field('military_service','군 경력',career)}${field('race_ethnicity','공개 인종·민족 정보',(v) => typeof v === 'string' ? v : '명시 정보 재확인 필요')}<small>약력에 없는 항목은 추정하지 않습니다. 경력은 당선 가능성 점수가 아닙니다.</small></details>`;
};

export const outsideSpendingSourceHtml = (race, contract) => {
    const health = contract?.source_status?.[race?.source_status_key];
    const sources = contract?.source_provenance || [];
    const selected = sources.filter((s) => {
        try { const h = new URL(s.url).hostname; return race?.office === 'governor'
            ? ({CA:'campaignfinance.cdn.sos.ca.gov',NY:'data.ny.gov',WA:'data.wa.gov'}[race.state_id || race.state] === h)
            : ['api.open.fec.gov','www.fec.gov'].includes(h); } catch { return false; }
    });
    return `<small class="elections-origin-links">${race?.office && race.office !== 'governor' ? originLink('https://www.fec.gov/data/independent-expenditures/', 'FEC 독립지출 공시 조회 ↗') : ''}${selected.map((s) => originLink(s.url, race?.office === 'governor' ? '주 공시 원자료 ↗' : s.url.includes('/schedule_e/') ? 'FEC 수집 경로(API) ↗' : 'FEC 후보 식별 원자료 ↗')).join(' ')}${health?.last_success_at ? `<span>수집 ${escapeHtml(health.last_success_at.slice(0,10))}</span>` : ''}${health?.last_filing_date ? `<span>최신 공시 ${escapeHtml(health.last_filing_date)}</span>` : ''}</small>`;
};
