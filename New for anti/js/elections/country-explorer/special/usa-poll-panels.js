import { escapeHtml } from '../../ui.js';
import { ELECTION_OFFICES } from '../../data/election-overview.js?v=5';
import { summarizePollPresentation, pollRaceAssessment } from '../../data/poll-presentation.js';

export const pollOfficePanelsHtml = (races, board, health, days, renderRace, { open = {}, now = Date.now() } = {}) => {
    days = days === 14 ? 14 : 7;
    const context = summarizePollPresentation([], board, health, days, now).context;
    const through = new Date(context.now).toISOString().slice(0,10);
    const from = new Date(Date.parse(through) - ((days === 14 ? 14 : 7) - 1) * 86400000).toISOString().slice(0,10);
    return `<p class="elections-panel-note${context.stale ? ' is-warning' : ''}">${!context.available ? '자료 연결·수집 상태 확인 필요'
        : context.stale ? `갱신 지연 · 마지막 정상 수집 ${context.collectedOn} 기준 요약. 현재 우세 판정은 중단합니다.`
            : `수집 ${context.collectedOn} · 현재 날짜 기준 최근 ${days}일`} · 집계 기간 ${from}~${through}</p>
        <div class="elections-poll-offices">${ELECTION_OFFICES.map(([office, label]) => {
            const selected = races.filter((race) => race.office === office).sort((a,b) => {
                const x = pollRaceAssessment(a,context,days), y = pollRaceAssessment(b,context,days);
                const latest = (race) => (race.observations || []).map((row) => row.field_end || '').sort().at(-1) || '';
                return Number(!!y.rows.length) - Number(!!x.rows.length)
                    || Number(!!b.observations?.length) - Number(!!a.observations?.length)
                    || latest(b).localeCompare(latest(a)) || String(a.race_id).localeCompare(String(b.race_id));
            });
            const s = summarizePollPresentation(selected, board, health, days, now);
            const unit = office === 'governor' ? '곳' : '석';
            const extras = [['mixed', '동률·조사 방향 엇갈림'], ['other', '제3당·무소속 앞섬'],
                ['missing', '최근 조사 없음'], ['reference', '참고 조사만 있음'], ['conflict', '수치 상충'],
                ['review', '대진·자료 검토 필요'], ['singleCandidate', '단독 후보 명부'],
                ['closed', '공식 결과 대기'], ['certified', '공식 확정'], ['unavailable', '자료 연결 대기']]
                .filter(([key]) => s[key]).map(([key, title]) => `${title} ${s[key]}${unit}`).join(' · ');
            const key = `poll-${office}`;
            return `<details class="elections-poll-office" data-evidence-section="${key}"${open[key] ? ' open' : ''}>
                <summary><span class="elections-poll-office-title"><strong>${label}</strong><small>감시 ${s.watched}${unit} · 누적 조사 확보 ${s.observed}${unit}<br>최근 채택 ${s.recent}${unit} · ${s.states}개 주${context.stale ? ' · 마지막 수집 기준' : ''}</small></span>
                    <span class="elections-poll-tallies"><span class="is-dem">최근 ${days}일 DEM 수치상 우세<strong>${s.dem}${unit}</strong></span><span class="is-gop">최근 ${days}일 GOP 수치상 우세<strong>${s.rep}${unit}</strong></span><span class="is-close">최근 ${days}일 오차구간 겹침<strong>${s.within}${unit}</strong></span></span>
                    <small>${escapeHtml(extras || '클릭하여 선거별 조사 보기')}</small><span class="elections-expand-icon" aria-hidden="true">＋</span></summary>
                <div class="elections-poll-office-body"><p class="elections-panel-note">아래 누적 자료에는 기간 밖·참고 전용 조사도 보관됩니다. 카드의 후보 지지율과 위 최근 우세 합계는 범위가 다를 수 있습니다. 기관별 최신 파동 1건 · LV 우선, RV 별도 · 다수 방향 기준. 단일 기관 ${s.single}${unit} 포함(참고), 오차 미확인 ${s.precisionUnknown}${unit}. 수치상 우세는 당선 예측이 아닙니다.</p>
                ${selected.filter((race) => race.observations?.length).map(renderRace).join('')}
                ${selected.some((race) => !race.observations?.length) ? `<details class="elections-disclosure"><summary>조사 미연결 선거 ${selected.filter((race) => !race.observations?.length).length}${unit} 보기</summary>${selected.filter((race) => !race.observations?.length).map(renderRace).join('')}</details>` : ''}
                ${!selected.length ? '<p class="elections-muted">이 직위의 감시 자료가 연결되지 않았습니다.</p>' : ''}</div></details>`;
        }).join('')}</div><details class="elections-disclosure"><summary>오차구간과 집계 기준</summary><p class="elections-panel-note">오차구간 겹침은 같은 모집단·표본에 대해 원문에서 확인한 후보별 ±표본오차 구간이 겹치는 참고 분류입니다. 후보 격차 ≤ 후보별 오차의 2배를 사용하며 격차의 통계적 유의성을 계산한 값은 아닙니다. 오차 미공개·모형 오차·전체 조사 오차는 임의로 대입하지 않습니다. 조사 없음·참고 전용·상충은 우세로 세지 않습니다. 공식 결과는 조사 집계와 분리합니다. <a href="https://www.pewresearch.org/short-reads/2016/09/08/understanding-the-margin-of-error-in-election-polls/" target="_blank" rel="noopener noreferrer">오차 해석 근거</a></p></details>`;
};
