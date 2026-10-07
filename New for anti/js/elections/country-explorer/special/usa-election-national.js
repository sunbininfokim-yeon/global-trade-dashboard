import { escapeHtml } from '../../ui.js';
import { STATE_CLASSIFICATION_SOURCES, classLabels, stateClass2024, pollSignal, pollSourceReady } from '../../data/usa-election-context.js?v=2';
import { financeEvidenceHtml, pollEvidenceHtml, raceLabel } from './usa-election-evidence.js?v=2';
import { electionOverviewHtml, bindElectionOverview, evidenceSectionHtml, compactPollLabel } from './usa-election-overview.js?v=3';

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
    country, board, health, indexes = {}, contract, ratings = null, days = 7, evidenceOpen = {}, onBack, onToggle, onWindowChange, onStateOpen, onStatePrefetch,
}) => {
    const races = selectNationalRaces(board, days, health);
    const summary = summarizeNationalRaces(board, health, days);
    const ready = pollSourceReady(board, health);
    const allMonitored = monitoredNationalRaces(board).sort((a, b) => (a.collection_priority?.order || 4)
        - (b.collection_priority?.order || 4) || a.race_id.localeCompare(b.race_id));
    const unresolved = allMonitored.filter((race) => (race.required_candidates || []).length < 2);
    const cadence = board?.refresh_cadence?.interval_days === 7 ? '매주 월요일 06:10 KST 수집' : '정기 수집';
    const financeById = new Map(Object.entries(indexes).flatMap(([, index]) =>
        (index?.races || []).map((race) => [race.race_id, race])));
    const raceButton = (race) => `<button class="elections-race-open" type="button" data-open-state="${escapeHtml(race.state)}" data-open-district="${escapeHtml(race.office === 'house' ? race.district || '' : '')}">
        <strong>${escapeHtml(raceLabel(race))}</strong><span>주·지역구 보기 →</span></button>`;
    const pollContent = `
        <div class="elections-window-switch" role="group" aria-label="최근 여론조사 집계 기간">
            <span>최근 조사</span><button type="button" data-window="7" aria-pressed="${days === 7}">7일</button>
            <button type="button" data-window="14" aria-pressed="${days === 14}">14일</button>
        </div>
        <p class="elections-panel-note">${ready ? `수집 ${escapeHtml((board.fetched_at || '').slice(0, 10))}` : '여론조사 갱신 대기'} · ${cadence}. 기간은 현재 날짜로 다시 계산합니다.</p>
        <div class="elections-poll-summary"><span class="is-dem">민주 우세 ${summary.total.dem}</span><span class="is-gop">공화 우세 ${summary.total.rep}</span><span>보류 ${summary.total.pending}</span></div>
        <p class="elections-panel-note">복수 기관 기준 · 단일 기관 참고는 민주 ${summary.total.singleDem}, 공화 ${summary.total.singleRep}곳으로 별도 표시합니다.</p>
        <div class="elections-national-races">${races.map((race) => `<article class="elections-race-card">${raceButton(race)}${pollEvidenceHtml(race, board, health, days)}</article>`).join('') || '<p class="elections-muted">확인된 본선 자료가 없습니다.</p>'}</div>
        <details class="elections-disclosure elections-monitoring-list">
            <summary>전체 감시 목록 ${allMonitored.length}곳 · 후보 검토 대기 ${unresolved.length}곳</summary>
            <p class="elections-panel-note">감시 대상이 실제 선거·확정 후보를 뜻하지는 않습니다. API 미발견은 여론조사 자체의 부재가 아닙니다.</p>
            ${allMonitored.map((race) => `<button class="elections-monitoring-row" type="button" data-open-state="${escapeHtml(race.state)}" data-open-district="${escapeHtml(race.office === 'house' ? race.district || '' : '')}">
                <strong>${escapeHtml(raceLabel(race))}</strong><span>${escapeHtml(compactPollLabel(race, board, health, days))} · 누적 ${race.observations?.length || 0}건</span></button>`).join('')}
        </details>
        `;
    const financeContent = `<p class="elections-panel-note">후보 대상 외부 독립지출입니다. 지지·반대를 따로 보며 후보 캠프 후원금과 구분합니다.</p>
        <div class="elections-national-races">${races.map((race) => `<article class="elections-race-card">${raceButton(race)}${financeEvidenceHtml(financeById.get(race.race_id) || null, contract)}</article>`).join('')}</div>
        <p class="elections-panel-note">지도를 누르면 해당 주 전체 지역구의 후보별 공시를 확인할 수 있습니다. 주지사 자료는 주별 공시이며 미수집 금액은 0이 아닙니다.</p>`;
    const observations = allMonitored.reduce((n, race) => n + (race.observations?.length || 0), 0);
    const observedRaces = allMonitored.filter((r) => r.observations?.length).length;
    root.className = 'panel-section elections-country elections-national-mode';
    root.innerHTML = `
        <div class="elections-country-actions">
            <button class="elections-button" type="button" data-election-back>← 세계 지도</button>
            <button class="elections-button is-active" type="button" data-election-mode aria-pressed="true">선거·슈퍼팩</button>
        </div>
        <div class="panel-header"><h2>미국 선거</h2><p>현재 보유 → 선거 구도 → 여론조사·외부 지출</p></div>
        ${electionOverviewHtml(country, ratings, { board, health, days })}
        <p class="elections-section-heading">선거별 자료 <small>눌러서 펼치기</small></p>
        ${evidenceSectionHtml('poll', '여론조사', `${observedRaces}개 선거 · 누적 ${observations}건 · 최근 ${days}일`, pollContent, evidenceOpen.poll)}
        ${evidenceSectionHtml('finance', '슈퍼팩 · 외부 독립지출', '후보별 지지·반대 금액', financeContent, evidenceOpen.finance)}
        <details class="elections-disclosure"><summary>지도 색상 기준</summary>
            <div class="elections-map-legend"><span><i class="is-blue"></i>블루</span><span><i class="is-red"></i>레드</span><span><i class="is-swing"></i>스윙 · 퍼플</span></div>
            <p class="elections-panel-note"><a href="${STATE_CLASSIFICATION_SOURCES.winner}" target="_blank" rel="noopener noreferrer">2024 대선 주별 승자</a>와 <a href="${STATE_CLASSIFICATION_SOURCES.swing}" target="_blank" rel="noopener noreferrer">Cook 경합주 7곳</a> 기준입니다. 이 지도 색을 민주·공화 의석으로 계산하지 않습니다.</p>
        </details>`;
    bindElectionOverview(root, onStateOpen);
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
