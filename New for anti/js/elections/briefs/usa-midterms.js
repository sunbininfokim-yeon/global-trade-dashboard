import { escapeHtml, formatDate } from '../ui.js';
import { usaMidtermsModel, PARTY_KO, PARTY_COLOR } from '../data/usa-midterms-model.js';
import { forecastSlot, forecastFooterSlot } from './forecast-panel.js';

// 미국 중간선거 브리핑. 선거 종류 세 열(주지사·하원·상원)이 완전히 같은 구조라,
// 열 하나를 그리는 함수 하나로 셋을 다 그린다.
//
//   열 머리   현재 n VS m        ← 확정된 현재 의석
//   열 어깨   전망 슬롯          ← 여론조사가 오면 이 칸만 갈아끼운다
//   열 몸통   주별 대진 박스      ← 경선 승자 D vs R
//
// 하원처럼 주가 46개나 되는 열은 주를 눌러야 그 주의 선거구 대진이 펼쳐진다. 모달
// 본문은 리스너 없는 정적 HTML 이라 <details> 가 이 화면이 가질 수 있는 유일한
// 클릭이고, 그래서 주 이름 줄 자체가 <summary> 다.
//
// 숫자는 전부 수집된 값이다. 무소속을 어느 코커스로 셀지 같은 판정은 하지 않는다 --
// 그 계산은 usa-midterms-model.js 의 주석에 이유와 함께 적혀 있다.

const VS_MIN_WIDTH = 6;

const versusBar = (current) => {
    const dem = Number.isFinite(current.dem) ? current.dem : 0;
    const gop = Number.isFinite(current.gop) ? current.gop : 0;
    const others = current.others.reduce((sum, [, seats]) => sum + seats, 0);
    const total = dem + gop + others;
    if (!total) return '';
    const width = (value) => (value ? Math.max(VS_MIN_WIDTH, Math.round((value / total) * 100)) : 0);
    return `
        <div class="elections-vs-bar" role="img" aria-label="${escapeHtml(`민주 ${dem} 대 공화 ${gop}`)}">
            ${dem ? `<i style="width:${width(dem)}%;background:${PARTY_COLOR.DEM}"></i>` : ''}
            ${others ? `<i style="width:${width(others)}%;background:${PARTY_COLOR.IND}"></i>` : ''}
            ${gop ? `<i style="width:${width(gop)}%;background:${PARTY_COLOR.GOP}"></i>` : ''}
        </div>`;
};

const versusHead = (column) => {
    const { current } = column;
    const value = (seats) => (Number.isFinite(seats) ? seats : '—');
    return `
        <div class="elections-vs">
            <span class="elections-vs-side" style="color:${PARTY_COLOR.DEM}">
                <b>${value(current.dem)}</b><em>민주당</em>
            </span>
            <span class="elections-vs-mid">VS</span>
            <span class="elections-vs-side is-right" style="color:${PARTY_COLOR.GOP}">
                <b>${value(current.gop)}</b><em>공화당</em>
            </span>
        </div>
        ${versusBar(current)}
        ${current.others.length ? `<p class="elections-vs-other">${escapeHtml(current.others
        .map(([abbr, seats]) => `${PARTY_KO[abbr] || abbr} ${seats}`).join(' · '))} — 어느 쪽에도 합산하지 않습니다</p>` : ''}
        ${column.seatNoteKo ? `<p class="elections-vs-note">${escapeHtml(column.seatNoteKo)}</p>` : ''}`;
};

// 한 자리의 대진. D·R 이 둘 다 있으면 맞대결, 하나뿐이면 상대가 아직 정해지지 않은
// 것이다 -- "무투표 당선"이 아니므로 그렇게 읽히게 두지 않는다.
const matchupRow = (matchup) => {
    const of = (party) => matchup.runners.find((row) => row.party === party);
    const dem = of('DEM');
    const gop = of('GOP');
    const side = (runner, party) => (runner
        ? `<span class="elections-matchup-name" style="color:${PARTY_COLOR[party]}">${escapeHtml(runner.name || '불명')}</span>`
        : '<span class="elections-matchup-name is-empty">후보 미정</span>');
    return `
        <div class="elections-matchup">
            ${matchup.district ? `<span class="elections-matchup-seat">${escapeHtml(`${matchup.district}구`)}</span>` : ''}
            ${side(dem, 'DEM')}
            <span class="elections-matchup-vs">vs</span>
            ${side(gop, 'GOP')}
        </div>`;
};

const stateBlock = (row, { collapsible }) => {
    const head = `<span class="elections-brief-state-id">${escapeHtml(row.id)}</span>
        <span class="elections-brief-state-name">${escapeHtml(row.name || '')}</span>
        <span class="elections-brief-state-meta">${escapeHtml(`${row.matchups.length}자리`)}</span>`;
    const body = row.matchups.map(matchupRow).join('');

    // 자리가 하나뿐인 열(주지사·상원)은 접을 이유가 없다. 하원만 주를 눌러 편다.
    if (!collapsible) {
        return `<article class="elections-brief-state">
            <div class="elections-brief-state-head">${head}</div>
            ${body}
        </article>`;
    }
    return `<details class="elections-brief-state is-collapsible">
        <summary class="elections-brief-state-head">${head}</summary>
        <div class="elections-brief-state-body">${body}</div>
    </details>`;
};

const columnHtml = (column) => {
    const collapsible = column.key === 'house';
    // 대진이 잡힌 주와 아직 경선 전인 주를 섞어 늘어놓으면, 확정된 대진이 "경선 예정"
    // 줄 사이에 파묻힌다. 예정 주는 수만 세어 아래 한 줄로 접는다 -- 빠진 것이 아니라
    // 아직 치르지 않은 것이므로 지우지는 않는다.
    const decided = column.states.filter((row) => row.matchups.length);
    const pending = column.states.filter((row) => !row.matchups.length);
    const seats = decided.reduce((sum, row) => sum + row.matchups.length, 0);
    return `
        <section class="elections-brief-column">
            <header class="elections-brief-column-head">
                <h4>${escapeHtml(column.label)}</h4>
                ${column.contestedKo ? `<span>${escapeHtml(column.contestedKo)}</span>` : ''}
            </header>
            ${forecastSlot(column.key)}
            <p class="elections-brief-current-label">현재</p>
            ${versusHead(column)}
            <p class="elections-brief-column-sub">${escapeHtml(seats
        ? `본선 대진 ${seats}자리 · ${decided.length}개 주`
        : '확정된 본선 대진이 없습니다')}</p>
            <div class="elections-brief-states">
                ${decided.map((row) => stateBlock(row, { collapsible })).join('')
        || '<p class="elections-muted">확정된 대진이 아직 없습니다.</p>'}
            </div>
            ${pending.length ? `<details class="elections-brief-pending">
                <summary>${escapeHtml(`경선 예정 ${pending.length}개 주`)}</summary>
                <div class="elections-brief-pending-rows">${pending.map((row) => `<div>
                    <span>${escapeHtml(row.id)}</span>
                    <strong>${escapeHtml(row.name || '')}</strong>
                    <em>${escapeHtml(formatDate(row.primaryDate))}</em>
                </div>`).join('')}</div>
            </details>` : ''}
        </section>`;
};

export const usaMidtermsBrief = (country, { event } = {}) => {
    const model = usaMidtermsModel(country);
    if (!model) return null;
    return `
        <div class="elections-brief">
            ${event?.contested_ko ? `<p class="elections-brief-lede">${escapeHtml(event.contested_ko)}</p>` : ''}
            <div class="elections-brief-columns">${model.columns.map(columnHtml).join('')}</div>
            ${model.primaryPending ? `<p class="elections-panel-note">${escapeHtml(`${model.statesTotal}개 주 가운데 ${model.primaryPending}개 주는 경선이 아직입니다. 그 주의 대진이 비어 있는 것은 후보가 없다는 뜻이 아닙니다.`)}</p>` : ''}
            <p class="elections-panel-note">현재 의석과 본선 대진은 공식 명부·경선 결과입니다. 전망만 여론조사에서 옵니다.</p>
            ${forecastFooterSlot()}
        </div>`;
};
