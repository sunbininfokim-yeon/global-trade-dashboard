import { countryEvents, readableSpectrum, screenStatus } from '../data/selectors.js';
import { escapeHtml, formatDate, stateLabel } from '../ui.js';
import { usaSections } from './special/usa.js';
import { chinaSections } from './special/china.js';
import { iranSections } from './special/iran.js';

const genericSections = [['지도', 'subnational_map'], ['행정부·정부', 'executive'], ['의회', 'legislature'], ['정당', 'factions'], ['일정', 'calendar']];
const sectionsFor = (iso3) => iso3 === 'USA' ? usaSections : iso3 === 'CHN' ? chinaSections : iso3 === 'IRN' ? iranSections : genericSections;

// This is presentation-only flattening, not a political calculation or an
// attempt to join missing records.  It lets the common shell surface nested
// public summaries such as legislature_live.summary and state_council.
const values = (object) => {
    const output = [];
    for (const [key, value] of Object.entries(object || {})) {
        if (value === null || value === undefined) continue;
        if (typeof value !== 'object') output.push([key, value]);
        if (Array.isArray(value)) continue;
        if (typeof value === 'object') {
            for (const [childKey, childValue] of Object.entries(value)) {
                if (childValue !== null && childValue !== undefined && typeof childValue !== 'object') {
                    output.push([`${key} · ${childKey}`, childValue]);
                }
            }
        }
        if (output.length >= 8) break;
    }
    return output.slice(0, 8);
};
const partyName = (party) => party?.name_ko || party?.display || party?.name_en || party?.abbr || '불명';
const affiliation = (abbr) => ({ LDP: '자민당', DPK: '더불어민주당', PPP: '국민의힘', IND: '무소속' }[abbr] || abbr || '');
const personLabel = (row) => [row?.name_ko || row?.name_en || '불명', affiliation(row?.party_abbr)].filter(Boolean).join(' · ');

const executiveContent = (country) => {
    const executive = country.executive_live;
    if (!executive) return null;
    const core = executive.core || [];
    const cabinet = executive.cabinet || [];
    const sourceLabels = (executive.sources || []).map((source) => [source.org, source.as_of ? `${source.as_of} 기준` : '공개 명부'].filter(Boolean).join(' · '));
    const coverageNotice = executive.coverage?.includes('source_aged') ? '이 행은 출처 기준일이 오래되어 최신 공식 명부 재확인이 필요합니다.' : '';
    return `
        <div class="elections-card-grid">${core.map((row) => `<article class="elections-card"><div class="elections-card-label">${escapeHtml(row.office_ko || row.portfolio_ko || '직책')}</div><div class="elections-card-value">${escapeHtml(personLabel(row))}</div></article>`).join('')}</div>
        ${cabinet.length ? `<details class="elections-disclosure elections-cabinet-list"><summary>국무위원 ${cabinet.length}명 보기</summary><div class="elections-disclosure-rows">${cabinet.map((row) => `<div><span>${escapeHtml(row.portfolio_ko || '직책')}</span><strong>${escapeHtml(personLabel(row))}</strong></div>`).join('')}</div></details>` : ''}
        ${sourceLabels.length ? `<p class="elections-panel-note">공개 명부: ${escapeHtml(sourceLabels.join(' / '))}</p>` : ''}
        ${coverageNotice ? `<p class="elections-panel-note">${escapeHtml(coverageNotice)}</p>` : ''}
        ${(executive.source_conflicts_excluded || []).length ? `<p class="elections-panel-note">공개 명부 충돌로 이번 행에서는 보류: ${escapeHtml(executive.source_conflicts_excluded.join(', '))}</p>` : ''}
    `;
};

const seatSummary = (label, seats) => {
    const entries = Object.entries(seats || {});
    return entries.length ? `<article class="elections-card"><div class="elections-card-label">${escapeHtml(label)}</div><div class="elections-card-value">${escapeHtml(entries.map(([party, count]) => `${party} ${count}`).join(' · '))}</div></article>` : '';
};

const legislatureContent = (country) => {
    const legislature = country.legislature_live;
    if (!legislature) return null;
    const cards = [
        seatSummary('중의원 정당별 의석', legislature.shugiin_by_party_abbr || legislature.house_composition_wikipedia),
        seatSummary('참의원 정당별 의석', legislature.sangiin_by_abbr),
        seatSummary('국회 정당별 의석', legislature.summary?.by_party_abbr),
    ].filter(Boolean).join('');
    const leaders = legislature.chamber_leadership || legislature.floor_leadership || [];
    return `
        ${cards ? `<div class="elections-card-grid">${cards}</div>` : ''}
        ${leaders.length ? `<details class="elections-disclosure"><summary>의장단·원내지도부 보기</summary><div class="elections-disclosure-rows">${leaders.map((row) => `<div><span>${escapeHtml(row.office_ko || row.office || row.title || row.chamber || '직책')}</span><strong>${escapeHtml(personLabel(row))}</strong></div>`).join('')}</div></details>` : ''}
        ${!cards && !leaders.length ? '<p class="elections-muted">확보된 공개 의회 요약이 없습니다.</p>' : ''}
    `;
};

const overview = (country) => `
    <div class="elections-card-grid">
        <article class="elections-card"><div class="elections-card-label">국가 수반</div><div class="elections-card-value">${escapeHtml(country.head?.name_ko || country.head?.name_en || '불명')}</div></article>
        <article class="elections-card"><div class="elections-card-label">집권 축</div><div class="elections-card-value">${escapeHtml(partyName(country.ruling_party))}</div></article>
        <article class="elections-card"><div class="elections-card-label">정치 지형</div><div class="elections-card-value">${escapeHtml(readableSpectrum(country.map_spectrum))}</div></article>
        <article class="elections-card"><div class="elections-card-label">정치 제도</div><div class="elections-card-value">${escapeHtml(country.system || '불명')}</div></article>
    </div>`;

const calendar = (country) => {
    const events = countryEvents(country).slice(0, 12);
    return events.length ? `<div class="elections-screen-list">${events.map((event) => `<article class="elections-event"><div class="elections-event-title">${escapeHtml(event.label_ko || event.label_en)}</div><div class="elections-event-meta">${escapeHtml(formatDate(event.date))} · ${escapeHtml(stateLabel(event.status))}</div></article>`).join('')}</div>` : '<p class="elections-muted">공개된 일정 행이 없습니다.</p>';
};

const sourceObject = (country, section) => {
    if (section === 'executive') return country.executive_live || country.leadership?.party_state?.state_council || country.head || null;
    if (section === 'legislature') return country.legislature_live || country.legislature || null;
    if (section === 'factions') return country.factions || null;
    if (section === 'power_structure') return country.leadership || null;
    if (section === 'subnational_map') return country.subnational_live?.summary || country.subnational || null;
    if (section === 'race_progress') return country.race_progress || null;
    return null;
};

const sectionContent = (country, section, status) => {
    if (section === 'calendar') return calendar(country);
    if (status === 'disabled') return '<p class="elections-muted">이 화면은 공개 데이터가 확보되면 연결됩니다.</p>';
    if (section === 'executive') {
        const live = executiveContent(country);
        if (live) return live;
    }
    if (section === 'legislature') {
        const live = legislatureContent(country);
        if (live) return live;
    }
    const rows = values(sourceObject(country, section));
    return rows.length ? `<div class="elections-card-grid">${rows.map(([key, value]) => `<article class="elections-card"><div class="elections-card-label">${escapeHtml(key.replaceAll('_', ' '))}</div><div class="elections-card-value">${escapeHtml(value)}</div></article>`).join('')}</div>` : '<p class="elections-muted">확보된 공개 데이터 범위에서 표시할 요약 항목이 없습니다.</p>';
};

export const renderCountryShell = (root, { country, manifest, onBack }) => {
    const tabs = sectionsFor(country.iso3);
    let active = tabs[0][1];
    const draw = () => {
        const screen = manifest?.countries?.[country.iso3]?.screens?.[active];
        const status = screenStatus(manifest, country.iso3, active);
        root.className = 'panel-section elections-country';
        root.innerHTML = `
            <div class="elections-country-actions"><button class="elections-button" type="button" data-election-back>← 세계 지도</button></div>
            <div class="panel-header"><h2>${escapeHtml(country.name_ko || country.iso3)}</h2><p>확보된 공개 데이터만 표시합니다.</p></div>
            ${overview(country)}
            <div class="elections-tab-row">${tabs.map(([label, key]) => `<button class="elections-tab ${key === active ? 'is-active' : ''}" type="button" data-election-tab="${key}">${escapeHtml(label)}</button>`).join('')}</div>
            <div class="elections-screen-row"><span>${escapeHtml(tabs.find(([, key]) => key === active)?.[0] || '')}</span><span class="elections-screen-state">${escapeHtml(stateLabel(status))}</span></div>
            ${sectionContent(country, active, status)}
            ${screen?.missing?.length ? `<p class="elections-panel-note">미확보: ${escapeHtml(screen.missing.join(', '))}</p>` : ''}
        `;
        root.querySelector('[data-election-back]')?.addEventListener('click', onBack);
        root.querySelectorAll('[data-election-tab]').forEach((button) => button.addEventListener('click', () => {
            active = button.dataset.electionTab;
            draw();
        }));
    };
    draw();
};
