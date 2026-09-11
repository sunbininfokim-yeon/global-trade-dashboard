import { escapeHtml } from '../../ui.js';
import { noteLine } from './org-chart.js';
import { jpnPartyKo } from './jpn.js';

// 자민당 파벌 화면.
//
// 2024년 정치자금 문제로 대부분의 파벌이 공식 해산했지만 언론은 여전히 옛 파벌
// 단위로 움직임을 센다. 데이터가 그 상태를 group_id 로 구분해서 주므로 -- 공식 존속 /
// 해산 후 비공식 블록 / 파벌이 아닌 신생 그룹 -- 화면도 그 셋을 절대 섞지 않는다.
// 한 덩어리로 늘어놓으면 해산한 파벌이 아직 있는 것처럼 읽힌다.
//
// 인원수도 마찬가지다. n_approx_latest 는 언론 추정이고 기준 시점(n_as_of)이 파벌마다
// 다르며, 아예 "불명" 인 곳도 있다. 그래서 합계를 내지 않는다 -- 더한 수가 자민당
// 의석과 맞을 이유가 없다.

const GROUP_ORDER = ['active_formal', 'dissolved_formal', 'dissolved_informal_bloc', 'emerging_not_faction'];

const STATUS_KO = {
    active_formal_faction: '공식 파벌 유지',
    dissolved_formal: '공식 해산',
    dissolved_formal_still_informal_bloc: '공식 해산 · 비공식 블록 유지',
    emerging_policy_group_not_classic_faction: '정책 그룹 · 전통적 파벌 아님',
};

const headText = (faction) => {
    if (faction.head) return faction.head.name_ko || faction.head.name_ja || faction.head.name_en || '불명';
    const figures = faction.head_figures;
    if (Array.isArray(figures) && figures.length) return `${figures.join(', ')} (구심 인물)`;
    if (typeof figures === 'string' && figures !== '불명') return `${figures} (구심 인물)`;
    return '좌장 공백';
};

const sizeText = (faction) => (Number.isFinite(faction.n_approx_latest)
    ? `약 ${faction.n_approx_latest}명`
    : '인원 집계 없음');

// 막대는 파벌 사이 상대 크기만 보여 준다. 분모가 자민당 의석이 아니라 이 화면에서
// 가장 큰 파벌이라는 뜻이고, 그래서 % 를 쓰지 않는다.
const factionRow = (faction, largest) => {
    const size = Number.isFinite(faction.n_approx_latest) ? faction.n_approx_latest : null;
    // 인원 추정이 없는 그룹은 막대를 아예 그리지 않는다. 빈 트랙만 남기면 회색
    // 막대가 "0명"이나 "가장 작음"처럼 읽힌다 -- 실제로는 세어 본 적이 없다는 뜻이다.
    const width = size && largest ? Math.max(4, Math.round((size / largest) * 100)) : 0;
    return `
        <article class="elections-faction-row">
            <div class="elections-faction-head">
                <strong>${escapeHtml(faction.name_ko || faction.abbr || '파벌')}</strong>
                <span>${escapeHtml(sizeText(faction))}</span>
            </div>
            ${faction.name_ja ? `<div class="elections-faction-ja">${escapeHtml(faction.name_ja)}</div>` : ''}
            ${width ? `<div class="elections-faction-bar"><i style="width:${width}%"></i></div>` : ''}
            <div class="elections-faction-meta">
                <span>${escapeHtml(headText(faction))}</span>
                ${faction.spectrum_ko && faction.spectrum_ko !== '불명' ? `<span>${escapeHtml(faction.spectrum_ko)}</span>` : ''}
                ${faction.n_as_of ? `<span>${escapeHtml(`${faction.n_as_of} 기준`)}</span>` : ''}
            </div>
            ${faction.note ? `<div class="elections-org-box-note">${escapeHtml(faction.note)}</div>` : ''}
            ${faction.status ? `<div class="elections-event-meta">${escapeHtml(STATUS_KO[faction.status] || faction.status)}</div>` : ''}
        </article>`;
};

export const jpnFactions = (country) => {
    const factions = country.factions;
    const list = factions?.factions;
    if (!Array.isArray(list) || !list.length) return null;

    const largest = list.reduce((max, faction) => (Number.isFinite(faction.n_approx_latest)
        ? Math.max(max, faction.n_approx_latest) : max), 0);

    const groups = new Map();
    list.forEach((faction) => {
        const key = faction.group_id || 'other';
        if (!groups.has(key)) groups.set(key, { label: faction.group_label_ko || key, rows: [] });
        groups.get(key).rows.push(faction);
    });
    const ordered = [...groups.entries()].sort((a, b) => {
        const rank = (key) => (GROUP_ORDER.indexOf(key) === -1 ? GROUP_ORDER.length : GROUP_ORDER.indexOf(key));
        return rank(a[0]) - rank(b[0]);
    });

    const counted = list.filter((faction) => Number.isFinite(faction.n_approx_latest)).length;

    return `
        <div class="elections-card-grid">
            <article class="elections-card"><div class="elections-card-label">대상 정당</div><div class="elections-card-value">${escapeHtml(jpnPartyKo(factions.party_abbr))}</div></article>
            <article class="elections-card"><div class="elections-card-label">추적 중인 그룹</div><div class="elections-card-value">${list.length}곳</div><div class="elections-event-meta">${escapeHtml(`인원 추정 있는 곳 ${counted}곳`)}</div></article>
            <article class="elections-card"><div class="elections-card-label">기준일</div><div class="elections-card-value">${escapeHtml(factions.as_of || '불명')}</div></article>
        </div>

        ${ordered.map(([, group]) => `
            <p class="section-title">${escapeHtml(group.label)} · ${group.rows.length}곳</p>
            <div class="elections-faction-list">${group.rows
        .sort((a, b) => (b.n_approx_latest || 0) - (a.n_approx_latest || 0))
        .map((faction) => factionRow(faction, largest)).join('')}</div>
        `).join('')}

        <p class="elections-panel-note">인원은 언론 추정이고 기준 시점이 파벌마다 다릅니다. 겹치는 소속이 가능하고 미분류 의원이 있어 합산하지 않습니다 — 막대 길이는 이 화면에서 가장 큰 그룹 대비 상대 크기입니다.</p>
        ${noteLine(factions.other_parties_factions === '없음'
        ? '다른 정당의 파벌 데이터는 수집 대상이 아닙니다(데이터에 "없음"으로 명시).'
        : factions.other_parties_factions)}
    `;
};
