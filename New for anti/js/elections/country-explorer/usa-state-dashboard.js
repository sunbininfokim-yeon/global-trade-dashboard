import { escapeHtml, formatDate, stateLabel } from '../ui.js';

const party = (value) => ({ DEM: '민주당', GOP: '공화당', IND: '무소속', NP: '무당파' }[value] || value || '');
const person = (row) => {
    if (!row) return '불명';
    if (typeof row === 'string') return row;
    if (row.not_applicable) return `해당 직위 없음${row.note ? ` · ${row.note}` : ''}`;
    const affiliation = party(row.abbr || row.party);
    return [row.name || '불명', affiliation, row.note].filter(Boolean).join(' · ');
};
const seatLine = (body) => {
    if (!body) return '해당 없음';
    const classification = `${party(body.abbr || body.control) || '구성'} ${body.majority ?? '불명'} · 상대 ${body.minority ?? '불명'}`;
    return body.nonpartisan_official ? `공식 비당파 · 분석 분류 ${classification}` : classification;
};
const leaderLine = (leader) => leader ? `${leader.title || '지도부'}: ${person(leader)}` : '공개 명부 미기재';
const chamberCard = (label, chamber) => {
    if (!chamber) {
        return `<article class="elections-card"><div class="elections-card-label">${escapeHtml(label)}</div><div class="elections-card-value">해당 없음</div></article>`;
    }
    const leadership = chamber.leadership || {};
    return `
        <article class="elections-card elections-chamber-card">
            <div class="elections-card-label">${escapeHtml(label)}</div>
            <div class="elections-card-value">${escapeHtml(seatLine(chamber))}</div>
            <details class="elections-disclosure">
                <summary>구조·지도부 보기</summary>
                <div class="elections-disclosure-rows">
                    <div>${escapeHtml(leaderLine(leadership.presiding_officer))}</div>
                    <div>${escapeHtml(leaderLine(leadership.second_party_floor_leader))}</div>
                </div>
            </details>
        </article>`;
};

export const renderUsaStateDashboard = (root, { state, districtMapReady, onBackToUsa }) => {
    const legislature = state.state_legislature || {};
    const delegation = state.federal_delegation || {};
    const members = [...(delegation.house_members || [])].sort((a, b) => String(a.district || '').localeCompare(String(b.district || ''), undefined, { numeric: true }));
    root.className = 'panel-section elections-country elections-state-dashboard';
    root.innerHTML = `
        <div class="elections-country-actions"><button class="elections-button" type="button" data-election-back-usa>← 미국 주 지도</button></div>
        <div class="panel-header"><h2>${escapeHtml(state.state)}</h2><p>${districtMapReady ? '연방 하원 선거구 지도 · 공개 결합 데이터' : '주 경계 지도 · 연방 하원 선거구 공식 도형 수집 대기'}</p></div>
        <section class="elections-detail-section">
            <p class="section-title">1 · 주 행정부</p>
            <div class="elections-card-grid">
                <article class="elections-card"><div class="elections-card-label">주지사</div><div class="elections-card-value">${escapeHtml(person(state.governor))}</div></article>
                <article class="elections-card"><div class="elections-card-label">부지사</div><div class="elections-card-value">${escapeHtml(person(state.lieutenant_governor))}</div></article>
                <article class="elections-card"><div class="elections-card-label">법무장관</div><div class="elections-card-value">${escapeHtml(person(state.attorney_general))}</div></article>
                <article class="elections-card"><div class="elections-card-label">주 단위 계파</div><div class="elections-card-value">공개 정본 없음</div></article>
            </div>
        </section>
        <section class="elections-detail-section">
            <p class="section-title">2 · 연방 의회</p>
            <div class="elections-card"><div class="elections-card-label">연방 상원의원</div><div class="elections-card-value">${escapeHtml((delegation.senators || []).map(person).join(' / ') || '불명')}</div></div>
            <details class="elections-disclosure elections-house-delegation">
                <summary>연방 하원의원 ${members.length}명 · 선거구 순으로 보기</summary>
                <div class="elections-member-list">${members.map((member) => `<div class="elections-member-row"><span>하원 ${escapeHtml(state.id)}-${escapeHtml(member.district ?? 'AL')}</span><span>${escapeHtml(person(member))}</span></div>`).join('') || '<p class="elections-muted">하원 명단 없음</p>'}</div>
            </details>
        </section>
        <section class="elections-detail-section">
            <p class="section-title">3 · 주 의회</p>
            <div class="elections-card-grid">
                ${chamberCard('주 상원', legislature.state_senate)}
                ${chamberCard(legislature.state_house?.label_ko || '주 하원', legislature.state_house)}
            </div>
            <p class="elections-panel-note">일반 주의원 개인 명단은 범위에서 제외합니다. 각 원의 의장·제2당 원내지도부만 표시합니다.</p>
        </section>
        ${state.primary_2026 ? `<section class="elections-detail-section"><p class="section-title">2026 선거 과정</p><div class="elections-card"><div class="elections-card-value">${escapeHtml(state.primary_2026.headline || '공개된 경선 요약 없음')}</div><div class="elections-event-meta">${escapeHtml(formatDate(state.primary_2026.date))} · ${escapeHtml(stateLabel(state.primary_2026.status))}</div></div></section>` : ''}
    `;
    root.querySelector('[data-election-back-usa]')?.addEventListener('click', onBackToUsa);
};
