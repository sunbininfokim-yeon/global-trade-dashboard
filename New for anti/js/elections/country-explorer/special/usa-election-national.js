import { escapeHtml } from '../../ui.js';
import { STATE_CLASSIFICATION_SOURCES, classLabels, stateClass2024, pollSourceReady } from '../../data/usa-election-context.js';
import { financeEvidenceHtml, pollEvidenceHtml, raceLabel } from './usa-election-evidence.js';

export const NATIONAL_WATCH_STATES = ['NY', 'TN', 'GA', 'FL', 'AZ', 'MI', 'NV', 'NC', 'PA', 'WI', 'TX'];

const raceRank = (race, days) => (race.windows?.[String(days)]?.status === 'poll_lead' ? 200 :
    race.windows?.[String(days)]?.pollster_count ? 150 : race.observations?.length ? 100 + race.observations.length : 0)
    + (stateClass2024(race.state) === 'swing' ? 12 : 0)
    + (race.office === 'senate' ? 3 : race.office === 'governor' ? 2 : 1);

const watchRaces = (board, indexes, days) => {
    const races = board?.races ? Object.values(board.races).filter((race) =>
        ['house', 'senate', 'governor'].includes(race.office) && NATIONAL_WATCH_STATES.includes(race.state)) : [];
    if (races.length) return races.sort((a, b) => raceRank(b, days) - raceRank(a, days)).slice(0, 18);
    // Polling PR not deployed yet: disclose the missing join rather than
    // inventing poll rows, but keep independently published finance visible.
    return NATIONAL_WATCH_STATES.flatMap((state) => (indexes[state]?.races || [])
        .filter((race) => race.office === 'senate' || race.office === 'governor')
        .map((race) => ({ ...race, state, race_id: race.race_id }))).slice(0, 18);
};

export const renderUsaElectionNational = (root, {
    board, health, indexes = {}, contract, days = 7, onBack, onToggle, onWindowChange, onStateOpen,
}) => {
    const races = watchRaces(board, indexes, days);
    const ready = pollSourceReady(board, health);
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
        <p class="elections-panel-note">${ready ? `조사 수집 ${escapeHtml(board.fetched_at || '')}` : '여론조사 데이터 연결 또는 갱신 대기'} · 조사 우세는 예측이나 당선 확정이 아닙니다.</p>
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
                </article>`).join('') || '<p class="elections-muted">주목 선거 데이터를 아직 불러오지 못했습니다.</p>'}</div>
        </section>
        <p class="elections-panel-note">대상: NY·TN·FL·TX와 2024 경합주 7곳(조지아 포함). 공개 자료가 없는 선거는 관측 없음으로 표시합니다.</p>`;
    root.querySelector('[data-election-back]')?.addEventListener('click', onBack);
    root.querySelector('[data-election-mode]')?.addEventListener('click', onToggle);
    root.querySelectorAll('[data-window]').forEach((button) => button.addEventListener('click', () => onWindowChange(Number(button.dataset.window))));
    root.querySelectorAll('[data-open-state]').forEach((button) => button.addEventListener('click', () =>
        onStateOpen(button.dataset.openState, button.dataset.openDistrict || null)));
};
