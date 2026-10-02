import { escapeHtml } from '../../ui.js';
import { normalizeParty, pollSignal } from '../../data/usa-election-context.js';

const money = (cents) => {
    if (cents == null) return '관측 없음';
    const dollars = cents / 100;
    if (Math.abs(dollars) >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
    if (Math.abs(dollars) >= 1_000) return `$${(dollars / 1_000).toFixed(0)}K`;
    return `$${Math.round(dollars).toLocaleString('en-US')}`;
};

const sumObserved = (totals, categories, field) => {
    let sum = null;
    for (const category of categories) {
        const value = totals?.[category]?.[field];
        if (value != null) sum = (sum ?? 0) + value;
    }
    return sum;
};

export const financeEvidence = (race, contract) => {
    if (!race) return { label: '외부 독립지출', support: null, oppose: null };
    const governor = race.office === 'governor';
    const categories = governor
        ? (contract?.governor_independent_expenditure_categories || [])
        : (contract?.federal_superpac_categories || ['super_pac']);
    return {
        label: governor ? (contract?.governor_label_ko || '주 공시 독립지출') : '연방 슈퍼팩 독립지출',
        support: sumObserved(race.totals_by_category, categories, 'support_cents'),
        oppose: sumObserved(race.totals_by_category, categories, 'oppose_cents'),
    };
};

export const financeEvidenceHtml = (race, contract) => {
    const evidence = financeEvidence(race, contract);
    return `<div class="elections-evidence-finance">
        <strong>${escapeHtml(evidence.label)}</strong>
        <span>후보 지지 ${escapeHtml(money(evidence.support))}</span>
        <span>후보 반대 ${escapeHtml(money(evidence.oppose))}</span>
        <small>캠프 후원금이 아니며, 반대 지출을 상대 지지액에 더하지 않습니다.</small>
    </div>`;
};

const sourceLink = (url) => {
    try {
        const parsed = new URL(url);
        if (parsed.protocol !== 'https:') return '';
        return `<a href="${escapeHtml(parsed.href)}" target="_blank" rel="noopener noreferrer">원문 ↗</a>`;
    } catch {
        return '';
    }
};

const observationHtml = (row) => {
    const answers = (row.answers || []).map((answer) => `${answer.name} ${answer.pct}%`).join(' · ');
    const sponsors = (row.sponsors || []).length ? ` · 의뢰 ${row.sponsors.join(', ')}` : '';
    return `<li><span>${escapeHtml(row.pollster || '조사기관 미기재')} · ${escapeHtml(row.field_end || '')}
        · ${escapeHtml((row.population || '').toUpperCase())} · n=${escapeHtml(row.sample_n ?? '?')}${escapeHtml(sponsors)}</span>
        <span>${escapeHtml(answers)}</span>${sourceLink(row.source_url)} ${row.methodology_url ? sourceLink(row.methodology_url).replace('원문 ↗', '방법론 ↗') : ''}</li>`;
};

const statusLabel = {
    poll_lead: '최근 조사상 우세', no_recent_poll: '최근 조사 없음',
    insufficient_pollsters: '독립 조사기관 부족', tie: '조사 우세 동률',
    unknown_leader_party: '우세 정당 확인 대기', stale: '수집 자료 갱신 대기',
    unavailable: '여론조사 데이터 연결 대기', awaiting_certified_result: '선거 종료 · 공식 결과 대기',
    certified_result: '공식 확정 결과', election_closed: '선거 종료',
};

export const pollEvidenceHtml = (race, board, health, days = 7) => {
    const signal = pollSignal(race, board, health, days);
    const observations = race?.phase === 'pre_election' && signal.status !== 'awaiting_certified_result'
        && signal.status !== 'certified_result' ? (race.observations || []) : [];
    const hasPoll = observations.length > 0;
    const name = signal.leader ? ` · ${signal.leader}` : '';
    const party = normalizeParty(signal.party);
    const partyLabel = party === 'DEM' ? '민주' : party === 'REP' ? '공화' : '';
    const counts = signal.window?.pollster_count
        ? ` · 독립 기관 ${signal.window.pollster_count}곳` : '';
    const leads = Object.entries(signal.window?.lead_counts || {});
    const leadCountText = leads.length ? `조사별 우세 횟수: ${leads.map(([candidate, count]) => `${candidate} ${count}회`).join(' · ')}${signal.window?.tie_count ? ` · 동률 ${signal.window.tie_count}회` : ''}` : '';
    const note = race?.schedule_status === 'watch_slot_unverified' && !hasPoll
        ? '<small>선거 일정·본선 대진 확인 전 감시 슬롯입니다. 이 목록만으로 실제 선거를 뜻하지 않습니다.</small>' : '';
    return `<div class="elections-evidence-poll">
        <strong>여론조사 · 최근 ${days}일</strong>
        <span class="${partyLabel ? (party === 'DEM' ? 'is-dem' : 'is-gop') : ''}">
            ${escapeHtml(statusLabel[signal.status] || signal.status)}
            ${partyLabel ? ` · ${partyLabel}` : ''}${escapeHtml(name + counts)}
        </span>
        ${signal.status === 'certified_result' ? `<small>확정 ${escapeHtml(race?.result?.certified_on || '')} ${sourceLink(race?.result?.source_url)}</small>` : ''}
        ${leadCountText ? `<small>${escapeHtml(leadCountText)}</small>` : ''}
        ${note}
        ${hasPoll ? `<details class="elections-disclosure">
            <summary>누적 조사 ${observations.length}건 보기</summary>
            <ol class="elections-poll-observations">${observations.map(observationHtml).join('')}</ol>
            <small>선정 기관의 자동 수집값입니다. 원문 수치를 이번 실행에서 재전사한 자료는 아닙니다.</small>
        </details>` : ''}
    </div>`;
};

export const raceLabel = (race) => {
    if (!race) return '선거 미확인';
    const office = race.office === 'house' ? `하원 ${Number(race.district)}구`
        : race.office === 'senate' ? '상원' : '주지사';
    return `${race.state} · ${office}`;
};
