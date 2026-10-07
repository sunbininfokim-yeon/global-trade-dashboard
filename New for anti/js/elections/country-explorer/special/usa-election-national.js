import { escapeHtml } from '../../ui.js';
import { STATE_CLASSIFICATION_SOURCES, classLabels, stateClass2024, pollSignal, pollSourceReady } from '../../data/usa-election-context.js?v=2';
import { financeEvidenceHtml, pollEvidenceHtml, raceLabel } from './usa-election-evidence.js?v=2';

export const NATIONAL_WATCH_STATES = ['NY', 'TN', 'GA', 'FL', 'AZ', 'MI', 'NV', 'NC', 'PA', 'WI', 'TX'];

export const nationalMonitoringStates = (board) => [...new Set([
    ...NATIONAL_WATCH_STATES, ...Object.values(board?.races || {}).map((race) => race.state),
])].filter((id) => /^[A-Z]{2}$/.test(id));

const monitoredNationalRaces = (board) => Object.values(board?.races || {}).filter((race) =>
    ['house', 'senate', 'governor'].includes(race.office)
    && (NATIONAL_WATCH_STATES.includes(race.state) || race.monitor_priority || race.collection_priority));

const eligibleNationalRaces = (board) => monitoredNationalRaces(board).filter((race) =>
    race.schedule_status === 'reported_general_matchup' || race.phase === 'certified_result');

const raceRank = (race, board, health, days, now) => {
    const signal = pollSignal(race, board, health, days, now);
    return (4 - (race.collection_priority?.order || 4)) * 1000
        + (signal.status === 'poll_lead' ? 200 : signal.status === 'single_poll_lead' ? 150
            : race.observations?.length ? 100 : 0)
        + (stateClass2024(race.state) === 'swing' ? 12 : 0)
        + (race.office === 'senate' ? 3 : race.office === 'governor' ? 2 : 1);
};

export const selectNationalRaces = (board, days = 7, health = null, now = Date.now()) =>
    eligibleNationalRaces(board).sort((a, b) => raceRank(b, board, health, days, now)
        - raceRank(a, board, health, days, now)).slice(0, 18);

export const summarizeNationalRaces = (board, health, days = 7, now = Date.now()) => {
    const empty = () => ({ dem: 0, rep: 0, pending: 0, certifiedDem: 0, certifiedRep: 0, singleDem: 0, singleRep: 0 });
    const summary = { total: empty(), governor: empty(), senate: empty(), house: empty() };
    for (const race of eligibleNationalRaces(board)) {
        const signal = pollSignal(race, board, health, days, now);
        for (const bucket of [summary.total, summary[race.office]]) {
            if (signal.status === 'certified_result' && signal.party === 'DEM') bucket.certifiedDem++;
            else if (signal.status === 'certified_result' && signal.party === 'REP') bucket.certifiedRep++;
            else if (signal.status === 'single_poll_lead' && signal.party === 'DEM') bucket.singleDem++;
            else if (signal.status === 'single_poll_lead' && signal.party === 'REP') bucket.singleRep++;
            else if (signal.status === 'poll_lead' && signal.party === 'DEM') bucket.dem++;
            else if (signal.status === 'poll_lead' && signal.party === 'REP') bucket.rep++;
            else bucket.pending++;
        }
    }
    return summary;
};

export const renderUsaElectionNational = (root, {
    board, health, indexes = {}, contract, forecast = null, days = 7, onBack, onToggle, onWindowChange, onStateOpen, onStatePrefetch,
}) => {
    const races = selectNationalRaces(board, days, health);
    const summary = summarizeNationalRaces(board, health, days);
    const ready = pollSourceReady(board, health);
    const conditional = ready && forecast?.schema === 'usa_midterms_forecast_v1' && forecast.as_of === board?.as_of
        ? forecast.windows?.[String(days)]?.chambers : null;
    const allMonitored = monitoredNationalRaces(board).sort((a, b) => (a.collection_priority?.order || 4)
        - (b.collection_priority?.order || 4) || a.race_id.localeCompare(b.race_id));
    const unresolved = allMonitored.filter((race) => (race.required_candidates || []).length < 2);
    const cadence = board?.refresh_cadence?.interval_days === 7 ? '매주 월요일 06:10 KST 수집' : '정기 수집';
    const financeById = new Map(Object.entries(indexes).flatMap(([, index]) =>
        (index?.races || []).map((race) => [race.race_id, race])));
    root.className = 'panel-section elections-country elections-national-mode';
    root.innerHTML = `
        <div class="elections-country-actions">
            <button class="elections-button" type="button" data-election-back>← 세계 지도</button>
            <button class="elections-button is-active" type="button" data-election-mode aria-pressed="true">선거·슈퍼팩</button>
        </div>
        <div class="panel-header"><h2>미국 선거</h2><p>주목 선거의 여론조사와 외부 독립지출을 함께 봅니다.</p></div>
        <div class="elections-map-legend" aria-label="지도 색상 기준">
            <span><i class="is-blue"></i>블루</span><span><i class="is-red"></i>레드</span>
            <span><i class="is-swing"></i>스윙 · 퍼플</span>
        </div>
        <p class="elections-panel-note">지도 색은 <a href="${STATE_CLASSIFICATION_SOURCES.winner}" target="_blank" rel="noopener noreferrer">2024 대선 주별 승자</a>와
            <a href="${STATE_CLASSIFICATION_SOURCES.swing}" target="_blank" rel="noopener noreferrer">Cook의 2024 경합주 7곳</a> 기준입니다.
            퍼플은 해당 7개 주를 뜻하며 2026 선거의 승패 예측이 아닙니다.</p>
        <div class="elections-window-switch" role="group" aria-label="최근 여론조사 집계 기간">
            <span>최근 조사</span><button type="button" data-window="7" aria-pressed="${days === 7}">7일</button>
            <button type="button" data-window="14" aria-pressed="${days === 14}">14일</button>
        </div>
        <p class="elections-panel-note">${ready ? `조사 수집 ${escapeHtml(board.fetched_at || '')}` : '여론조사 데이터 연결 또는 갱신 대기'} · ${cadence} · 현재 날짜로 7/14일 범위를 다시 계산합니다.</p>
        <section class="elections-detail-section" aria-label="정당별 조사 우세 레이스 수">
            <p class="section-title">최근 ${days}일 조사 우세 · 확인된 본선 레이스 ${Object.values(summary.total).reduce((sum, n) => sum + n, 0)}곳</p>
            <div class="elections-evidence-grid">
                <div class="elections-evidence-poll"><strong>민주당 우세</strong><span class="is-dem">${summary.total.dem}곳</span></div>
                <div class="elections-evidence-poll"><strong>공화당 우세</strong><span class="is-gop">${summary.total.rep}곳</span></div>
                <div class="elections-evidence-poll"><strong>판정 대기·최근 조사 부족</strong><span>${summary.total.pending}곳</span></div>
            </div>
            <p class="elections-panel-note">단일 기관 참고: 민주 ${summary.total.singleDem}곳 · 공화 ${summary.total.singleRep}곳. 위 복수 기관 우세와 별도입니다.</p>
            <p class="elections-panel-note">주지사 민주 ${summary.governor.dem} · 공화 ${summary.governor.rep} · 대기 ${summary.governor.pending} / 상원 민주 ${summary.senate.dem} · 공화 ${summary.senate.rep} · 대기 ${summary.senate.pending} / 하원 민주 ${summary.house.dem} · 공화 ${summary.house.rep} · 대기 ${summary.house.pending}</p>
            ${summary.total.certifiedDem + summary.total.certifiedRep ? `<p class="elections-panel-note">공식 확정 결과: 민주 ${summary.total.certifiedDem} · 공화 ${summary.total.certifiedRep} (조사 우세와 별도)</p>` : ''}
            <p class="elections-panel-note">이는 관심 주의 확인된 레이스만 센 수이며, 전국 의석 전망이나 확정 의석 수가 아닙니다. 블루·레드·퍼플 지도색은 집계에 넣지 않습니다.</p>
        </section>
        ${conditional ? `<section class="elections-detail-section" aria-label="수집 시점 전국 조건부 집계">
            <p class="section-title">전국 조건부 집계 · ${escapeHtml(forecast.as_of)} 수집 시점</p>
            ${[['house','하원'],['senate','상원'],['governor','주지사']].map(([office,label]) => {
                const row=conditional[office]; if (!row || !row.scenario_counts) return '';
                return `<p>${label} · 민주 ${row.scenario_counts.DEM ?? 0} · 공화 ${row.scenario_counts.GOP ?? 0} · 무소속 ${row.scenario_counts.IND ?? 0} · 미정 ${row.unresolved_seats ?? '?'}</p>`;
            }).join('')}
            <p class="elections-panel-note">${escapeHtml(forecast.method_ko || '')} 매주 수집 시점의 조건부 값이며 현재 날짜의 조사 우세 표와 구분합니다. 확정 의석·당선확률이 아닙니다.</p>
        </section>` : ''}
        <section class="elections-detail-section"><p class="section-title">주목 선거 · 주를 누르면 지역구까지 보기</p>
            <div class="elections-national-races">${races.map((race) => `
                <article class="elections-race-card">
                    <button type="button" data-open-state="${escapeHtml(race.state)}" data-open-district="${escapeHtml(race.office === 'house' ? race.district || '' : '')}">
                        <strong>${escapeHtml(raceLabel(race))}</strong><span>${escapeHtml(classLabels[stateClass2024(race.state)])} 주 →</span>
                    </button>
                    <div class="elections-evidence-grid">
                        ${pollEvidenceHtml(board?.races?.[race.race_id] || null, board, health, days)}
                        ${financeById.has(race.race_id) ? financeEvidenceHtml(financeById.get(race.race_id), contract)
                            : '<div class="elections-evidence-finance"><strong>외부 독립지출</strong><span>자료 연결 대기</span></div>'}
                    </div>
                </article>`).join('') || '<p class="elections-muted">확인된 2026 본선 선거 목록을 아직 불러오지 못했습니다. 감시 슬롯을 실제 선거로 표시하지 않습니다.</p>'}</div>
        </section>
        <details class="elections-disclosure elections-monitoring-list">
            <summary>전체 감시 목록 ${allMonitored.length}곳 · 후보 대진 검토 대기 ${unresolved.length}곳</summary>
            <p class="elections-panel-note">감시 슬롯은 실제 선거·확정 후보 명부와 구분합니다. 현재 API 미발견은 여론조사 자체가 없다는 뜻이 아닙니다.</p>
            ${allMonitored.map((race) => {
                const coverage = board?.monitoring?.race_coverage?.[race.race_id];
                const signal = pollSignal(race, board, health, days);
                const label = (race.required_candidates || []).length < 2 ? '후보 대진 검토 대기'
                    : !race.observations?.length ? '현재 수집 자료 없음'
                    : signal.status === 'single_poll_lead' ? '최근 단일 기관 참고'
                    : signal.status === 'poll_lead' ? '최근 복수 기관 우세'
                    : signal.status === 'tie' ? '최근 조사 동률' : '최근 적격 자료 없음';
                return `<button class="elections-monitoring-row" type="button" data-open-state="${escapeHtml(race.state)}" data-open-district="${escapeHtml(race.office === 'house' ? race.district || '' : '')}">
                    <strong>${escapeHtml(raceLabel(race))}</strong><span>${escapeHtml(label)} · 누적 ${coverage?.accepted_count || 0}건${race.monitor_priority ? ' · Cook 감시' : ''}</span></button>`;
            }).join('')}
        </details>
        <p class="elections-panel-note">대상: 요청 주 → 전국 Cook Toss-up/Lean → 검토한 한국기업 소재지 순서. 위 카드는 본선 대진 검토 완료 선거 중 상위18곳입니다.</p>`;
    root.querySelector('[data-election-back]')?.addEventListener('click', onBack);
    root.querySelector('[data-election-mode]')?.addEventListener('click', onToggle);
    root.querySelectorAll('[data-window]').forEach((button) => button.addEventListener('click', () => onWindowChange(Number(button.dataset.window))));
    root.querySelectorAll('[data-open-state]').forEach((button) => button.addEventListener('click', () =>
        onStateOpen(button.dataset.openState, button.dataset.openDistrict || null)));
    // 누르기 전에 그 주의 자료를 미리 받는다. 지나가다 스친 것까지 받지 않도록 150ms 머문 뒤에만,
    // 한 주는 한 번만. 터치 기기는 hover 가 없으므로 touchstart 도 같은 신호로 본다.
    if (onStatePrefetch) {
        const warmed = new Set();
        root.querySelectorAll('[data-open-state]').forEach((button) => {
            let timer = null;
            const arm = () => {
                const id = button.dataset.openState;
                if (!id || warmed.has(id) || timer) return;
                timer = setTimeout(() => { timer = null; warmed.add(id); onStatePrefetch(id); }, 150);
            };
            const disarm = () => { if (timer) { clearTimeout(timer); timer = null; } };
            button.addEventListener('pointerenter', arm);
            button.addEventListener('pointerleave', disarm);
            button.addEventListener('focus', arm);
            button.addEventListener('blur', disarm);
            button.addEventListener('touchstart', () => { const id = button.dataset.openState; if (id && !warmed.has(id)) { warmed.add(id); onStatePrefetch(id); } }, { passive: true });
        });
    }
};
