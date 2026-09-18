import { escapeHtml } from '../ui.js';
import { PARTY_KO, PARTY_COLOR, normalizeParty } from '../data/usa-midterms-model.js';

// 전망 칸. **브리핑 본문과 분리해서 나중에 갈아끼운다.**
//
// 여론조사는 들어올 때마다 우세 정당이 뒤집힌다. 그때 화면 전체를 다시 그리면 펼쳐 둔
// 주가 접히고 스크롤이 튄다. 그래서 브리핑은 빈 슬롯만 심어 두고(`forecastSlot`),
// 전망이 도착하면 그 노드의 내용만 바꾼다(`applyForecast`). 슬롯을 여러 번 갈아도
// 나머지 화면은 건드리지 않는다.
//
// 데이터 계약은 `docs/ops/handoff/` 의 여론조사 계약 문서에 있다. 요약하면:
//
//   { schema, as_of, method_ko, source_ko, refresh_seconds,
//     chambers: { house|senate|governor: {
//       lead_abbr: "DEM"|"GOP"|"없음",      // 우세 정당. 접전이면 "없음"
//       seats: { DEM: 219, GOP: 216 },       // 예상 의석 (선택)
//       win_prob: { DEM: 0.62, GOP: 0.38 },  // 0~1 (선택)
//       margin_note_ko: "..."                // 접전·오차 설명 (선택)
//     } } }
//
// `lead_abbr` 만 필수다. 의석·확률 없이 "누가 앞선다"만 와도 칸은 선다.

export const forecastSlot = (columnKey) => `<div class="elections-forecast-slot" data-forecast-slot="${escapeHtml(columnKey)}">${pendingHtml()}</div>`;

const pendingHtml = () => `
    <div class="elections-forecast is-pending">
        <span class="elections-forecast-label">전망</span>
        <span class="elections-forecast-lead">여론조사 연동 예정</span>
    </div>`;

const pct = (value) => (Number.isFinite(value) ? `${Math.round(value * 100)}%` : null);

const leadText = (chamber) => {
    const abbr = normalizeParty(chamber?.lead_abbr);
    if (!abbr) return { label: '접전 · 우세 판정 보류', color: '#94a3b8', abbr: null };
    return { label: `${PARTY_KO[abbr] || abbr} 우세`, color: PARTY_COLOR[abbr] || '#94a3b8', abbr };
};

const seatLine = (chamber) => {
    const seats = chamber?.seats;
    if (!seats || typeof seats !== 'object') return '';
    const rows = Object.entries(seats)
        .map(([key, value]) => [normalizeParty(key) || key, value])
        .filter(([, value]) => Number.isFinite(value))
        .sort((a, b) => b[1] - a[1]);
    if (!rows.length) return '';
    return rows.map(([abbr, value]) => `${PARTY_KO[abbr] || abbr} ${value}`).join(' · ');
};

const probLine = (chamber) => {
    const probs = chamber?.win_prob;
    if (!probs || typeof probs !== 'object') return '';
    const rows = Object.entries(probs)
        .map(([key, value]) => [normalizeParty(key) || key, pct(value)])
        .filter(([, value]) => value)
        .sort((a, b) => parseInt(b[1], 10) - parseInt(a[1], 10));
    if (!rows.length) return '';
    return rows.map(([abbr, value]) => `${PARTY_KO[abbr] || abbr} ${value}`).join(' · ');
};

const forecastHtml = (chamber, meta) => {
    if (!chamber) return pendingHtml();
    const lead = leadText(chamber);
    const seats = seatLine(chamber);
    const prob = probLine(chamber);
    return `
        <div class="elections-forecast">
            <span class="elections-forecast-label">전망</span>
            <span class="elections-forecast-lead" style="color:${lead.color}">${escapeHtml(lead.label)}</span>
            ${seats ? `<span class="elections-forecast-line">예상 ${escapeHtml(seats)}</span>` : ''}
            ${prob ? `<span class="elections-forecast-line">승리 확률 ${escapeHtml(prob)}</span>` : ''}
            ${chamber.margin_note_ko ? `<span class="elections-forecast-note">${escapeHtml(chamber.margin_note_ko)}</span>` : ''}
            ${meta?.as_of ? `<span class="elections-forecast-note">${escapeHtml(`${meta.as_of} 기준`)}</span>` : ''}
        </div>`;
};

// 열려 있는 화면의 전망 칸만 갈아끼운다. 몇 번을 불러도 안전하고, 전망이 null 이면
// "연동 예정"으로 되돌린다 -- 한 번 떴던 숫자가 출처 없이 남아 있으면 안 된다.
export const applyForecast = (root, forecast) => {
    if (!root) return 0;
    const slots = root.querySelectorAll('[data-forecast-slot]');
    slots.forEach((slot) => {
        const chamber = forecast?.chambers?.[slot.dataset.forecastSlot];
        slot.innerHTML = forecast ? forecastHtml(chamber, forecast) : pendingHtml();
    });
    return slots.length;
};

// 출처·방법론은 열마다 반복할 것이 아니라 화면 바닥에 한 번만 적는다.
export const forecastFooter = (forecast) => {
    if (!forecast) return '<p class="elections-panel-note">전망은 여론조사 파이프라인이 연결되면 표시됩니다. 지금 화면의 수치는 모두 확정된 현재 의석과 공식 경선 결과입니다.</p>';
    return `<p class="elections-panel-note">${escapeHtml([
        forecast.method_ko ? `전망 산출: ${forecast.method_ko}` : '',
        forecast.source_ko ? `출처: ${forecast.source_ko}` : '',
        forecast.as_of ? `${forecast.as_of} 기준` : '',
    ].filter(Boolean).join(' · '))}</p>`;
};
