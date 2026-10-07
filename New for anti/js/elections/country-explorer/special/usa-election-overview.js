import { escapeHtml } from '../../ui.js';
import { currentElectionSeats, electionRatingSummary, electionOutlook, ELECTION_OFFICES } from '../../data/election-overview.js';
import { pollSignal, raceClosedByDate } from '../../data/usa-election-context.js?v=2';

const number = (value) => Number.isFinite(value) ? String(value) : '—';
const tile = (label, value, cls, caption = '') => `<div class="elections-rating-tile ${cls}"><span>${label}</span><strong>${number(value)}</strong>${caption ? `<small>${caption}</small>` : ''}</div>`;

export const electionOverviewHtml = (country, ratings, { state = null, board = null, health = null, days = 7, now = Date.now() } = {}) => {
    const current = currentElectionSeats(country, state);
    const summary = country?.ui_ready?.congress?.summary;
    const afterElection = raceClosedByDate({ election_date: '2026-11-03' }, now);
    return `<section class="elections-seat-overview" aria-label="현재 정당별 보유와 2026 선거 분류">
        <p class="elections-panel-note">${afterElection ? '공식 확정 승자를 반영합니다. 결과 미확정은 미정으로 남깁니다.' : `조건부 전망 · 최근 ${days}일 · 미정=판정 보류`}</p>
        ${ELECTION_OFFICES.map(([office, label]) => {
            const row = current[office];
            const rating = electionRatingSummary(ratings, office, country, state?.id, now);
            const resultUniverse = rating || electionRatingSummary(ratings, office, country, state?.id, now, { resultsOnly: true });
            const outlook = electionOutlook(country, office, resultUniverse, { state, board, health, days, now });
            const others = row.counts?.IND ? `무소속 ${row.counts.IND}` : '';
            const unknown = row.counts?.unknown ? `정당 미확인 ${row.counts.unknown}` : '';
            const vacant = row.vacancies ? `공석 ${row.vacancies}` : '';
            return `<article class="elections-seat-card" data-office="${office}">
                <header><h3>${label}</h3><span>${number(row.total)}${office === 'governor' ? '개 주' : '석'}</span></header>
                <div class="elections-seat-row"><span class="elections-seat-row-label">현재</span>
                <div class="elections-current-parties" aria-label="현재 보유">
                    <div class="is-dem"><span>민주당</span><strong>${number(row.counts?.DEM)}</strong></div>
                    <div class="is-gop"><span>공화당</span><strong>${number(row.counts?.GOP)}</strong></div>
                </div></div>
                ${[others, unknown, vacant].filter(Boolean).length ? `<p class="elections-seat-extras">${[others, unknown, vacant].filter(Boolean).join(' · ')}</p>` : ''}
                <div class="elections-seat-row"><span class="elections-seat-row-label">${resultUniverse?.afterElection ? '결과' : '전망'}</span>
                <div class="elections-outlook-parties" aria-label="${resultUniverse?.afterElection ? '선거 후 · 공식 결과' : `전망 · 최근 ${days}일 반영`}">
                    <span class="is-dem">민주 <strong>${number(outlook?.counts.DEM)}</strong></span>
                    <span class="is-gop">공화 <strong>${number(outlook?.counts.GOP)}</strong></span>
                    <span>미정 <strong>${number(outlook?.pending)}</strong></span>
                </div></div>
                ${outlook?.counts.IND ? `<p class="elections-seat-extras">전망 무소속 ${outlook.counts.IND}</p>` : ''}
                ${outlook?.single ? `<p class="elections-seat-extras">단일 기관 참고 ${outlook.single}${office === 'governor' ? '곳' : '석'} 포함</p>` : ''}
                ${rating ? `<div class="elections-rating-grid" aria-label="2026 선거 분류">
                    ${tile('블루', rating.blue, 'is-dem')}
                    ${tile('레드', rating.red, 'is-gop')}
                    ${tile('Lean', rating.lean, 'is-lean')}
                    ${tile('Toss-up', rating.toss, 'is-toss')}
                </div><p class="elections-rating-date"><a href="${escapeHtml(rating.sourceUrl)}" target="_blank" rel="noopener noreferrer">Cook ${escapeHtml(rating.asOf)}</a> · 선거 ${rating.contested}${outlook?.retained ? ` · 비선거 유지 ${outlook.retained}` : ''}</p>
                ${rating.additional.length ? `<details class="elections-disclosure elections-extra-contests"><summary>Cook ${rating.cookToss} + 추가 경합 ${rating.additional.length}곳</summary>
                    <p>추가 경합은 사용자 기준입니다. Cook 원본 등급을 보존하고 전망에서는 경합으로 보류합니다. 주의 대선 색과 지역구 보유 정당의 차이는 동일 지역구의 교차투표와 구분합니다.</p>
                    ${rating.additional.map((r) => `<p><strong>${escapeHtml(r.state)}-${escapeHtml(r.district)}</strong> · Cook ${escapeHtml(r.rating.replaceAll('_',' '))}<br>${r.reasons.map((reason) => `${escapeHtml(reason.basis_ko)} <a href="${escapeHtml(reason.source_url)}" target="_blank" rel="noopener noreferrer">근거</a>`).join('<br>')}<br>${board?.races?.[r.race_id] ? escapeHtml(compactPollLabel(board.races[r.race_id], board, health, days)) : '여론조사 감시 미연결 · 전망 미정'}</p>`).join('')}
                </details>` : ''}`
                    : `<p class="elections-panel-note">${resultUniverse?.afterElection ? '지난 Cook 등급의 우세 가정은 중단합니다.' : '미연결·오래된 등급은 전망과 함께 —로 표시합니다.'}</p>`}
            </article>`;
        }).join('')}
        <details class="elections-disclosure elections-overview-basis"><summary>숫자와 색의 기준</summary>
            <p>현재 보유는 공개 현직 명부 기준입니다. 무소속·공석은 따로 셉니다. ${state ? '상원·하원은 주 의회가 아닌 연방 의회입니다.' : `하원 현원 ${number(summary?.house_voting_members)}명 / 정원 ${number(summary?.house_voting_seats)}석.`}</p>
            <p>전망은 비선거 현직 유지 + Cook Solid/Likely 우세 가정 + Lean/Toss-up의 최근 조사 우세를 더한 조건부 수치입니다. 조사 없음·동률·갱신 지연은 미정이며 당선확률이 아닙니다. 공식 결과가 확인되면 승자를 반영합니다.</p>
            <p>블루·레드는 Cook Solid/Likely의 민주·공화 우세입니다. 지도 색은 2024 대선 기준의 주 분류이고, 하원 선거 분류는 지역구별 Cook 등급입니다. 주 색으로 의석을 계산하지 않습니다. Cook 등급은 검토 스냅샷이며 21일 경과 시 집계를 멈춥니다.</p>
            <p>같은 지역구의 대선·하원 승자 불일치는 경계가 검증된 이력만 추가합니다. 전국 지역구별 대선 결과는 아직 미연동입니다. PVI는 대선 승자와 다릅니다.</p>
            <p>현재 명부: 하원 ${escapeHtml(country?.ui_ready?.congress?.context_coverage?.house_source_published_on || '시점 미기재')} · 상원 ${escapeHtml((country?.ui_ready?.congress?.context_coverage?.senate_roster_as_of || '').slice(0,10) || '시점 미기재')} · 주지사 ${escapeHtml((country?.ui_ready?.state_drilldown?.source_as_of?.governors || '').slice(0,10) || '시점 미기재')}.</p>
        </details>
    </section>`;
};

export const evidenceSectionHtml = (kind, title, caption, content, open = false) => `<details class="elections-evidence-section" data-evidence-section="${kind}"${open ? ' open' : ''}>
    <summary><span><strong>${title}</strong><small>${escapeHtml(caption)}</small></span><span class="elections-expand-icon" aria-hidden="true">＋</span></summary>
    <div class="elections-evidence-content">${content}</div></details>`;

export const compactPollLabel = (race, board, health, days) => {
    const signal = pollSignal(race, board, health, days);
    return signal.status === 'certified_result' ? '공식 결과'
        : signal.status === 'single_poll_lead' ? '단일 기관 참고'
        : signal.status === 'poll_lead' ? '복수 기관 우세'
        : signal.status === 'tie' ? '조사 동률'
        : signal.status === 'awaiting_certified_result' ? '공식 결과 대기'
        : signal.status === 'stale' ? '갱신 대기'
        : !race?.required_candidates?.length ? '후보 검토 대기' : '최근 조사 없음';
};
