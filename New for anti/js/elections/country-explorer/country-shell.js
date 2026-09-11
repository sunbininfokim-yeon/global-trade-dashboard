import { countryEvents, readableSpectrum, screenStatus } from '../data/selectors.js';
import { escapeHtml, formatDate, stateLabel } from '../ui.js';
import { usaSections } from './special/usa.js';
import { usaLegislature } from './special/usa-legislature.js';
import { usaExecutive } from './special/usa-executive.js';
import { chinaSections } from './special/china.js';
import { chnParty, chnMilitary, chnStateCouncil } from './special/chn-org.js';
import { jpnSections } from './special/jpn.js';
import { jpnExecutive } from './special/jpn-executive.js';
import { jpnLegislature } from './special/jpn-legislature.js';
import { jpnFactions } from './special/jpn-factions.js';
import { jpnSubnational } from './special/jpn-subnational.js';
import { iranSections } from './special/iran.js';
import { raceProgressContent } from './special/race-progress.js';

const RACE_PROGRESS_TAB = ['선거 진행 상황', 'race_progress'];
const genericSections = [['지도', 'subnational_map'], ['행정부·정부', 'executive'], ['의회', 'legislature'], ['정당', 'factions'], ['일정', 'calendar'], RACE_PROGRESS_TAB];
// USA already declares its own race_progress tab (2026 선거 과정); China/Iran's
// custom tab sets predate this screen, so it's appended here rather than
// duplicated into their own files.
const sectionsFor = (iso3) => iso3 === 'USA' ? usaSections
    : iso3 === 'JPN' ? jpnSections
    : iso3 === 'CHN' ? [...chinaSections, RACE_PROGRESS_TAB]
    : iso3 === 'IRN' ? [...iranSections, RACE_PROGRESS_TAB]
    : genericSections;

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

// Country-specific screens declared by the manifest (CHN's party/state_council/
// military, USA's congress) have no generic equivalent, so they render from the
// country's own module rather than through the shared flattener.
const specialContent = (country, section) => {
    if (section === 'race_progress') return raceProgressContent(country);
    if (country.iso3 === 'CHN' && section === 'party') return chnParty(country);
    if (country.iso3 === 'CHN' && section === 'military') return chnMilitary(country);
    if (country.iso3 === 'CHN' && section === 'state_council') return chnStateCouncil(country);
    if (country.iso3 === 'USA' && section === 'legislature') return usaLegislature(country);
    if (country.iso3 === 'USA' && section === 'executive') return usaExecutive(country);
    if (country.iso3 === 'JPN' && section === 'executive') return jpnExecutive(country);
    if (country.iso3 === 'JPN' && section === 'legislature') return jpnLegislature(country);
    if (country.iso3 === 'JPN' && section === 'factions') return jpnFactions(country);
    if (country.iso3 === 'JPN' && section === 'subnational_map') return jpnSubnational(country);
    return null;
};

// A screen the manifest calls `disabled` but this module can actually draw --
// 중국 행정부 is built from leadership.*, which the manifest only blesses under
// its own power_structure key -- is not "데이터 수집 예정". Reporting it as such
// while the screen is full of names is the one reading that is definitely
// wrong, so a renderable screen reports 일부 표시 instead. It never upgrades a
// screen the manifest already rates, and never invents content: it only
// believes the renderer that just produced some.
const effectiveStatus = (manifest, country, section) => {
    const status = screenStatus(manifest, country.iso3, section);
    if (status !== 'disabled' || section === 'calendar') return status;
    return specialContent(country, section) ? 'partial' : status;
};

const sectionContent = (country, section, status) => {
    if (section === 'calendar') return calendar(country);
    // Tried before the disabled bail: a renderer that produces content proves
    // the data is there, whatever the manifest says about the screen key.
    const special = specialContent(country, section);
    if (special) return special;
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

// The map block is the one that must not be covered: opening a window on top
// of the map to describe the map helps nobody, so it closes the window instead
// and its short subnational summary sits in the right pane permanently.
const MAP_SECTION = 'subnational_map';

export const renderCountryShell = (root, { country, manifest, onBack, modal, host, onRoute }) => {
    const tabs = sectionsFor(country.iso3);
    const hasMapBlock = tabs.some(([, key]) => key === MAP_SECTION);
    let active = null;

    const screenFor = (key) => manifest?.countries?.[country.iso3]?.screens?.[key];

    const openSection = (key) => {
        const label = tabs.find(([, tabKey]) => tabKey === key)?.[0] || '';
        const status = effectiveStatus(manifest, country, key);
        const missing = screenFor(key)?.missing || [];
        active = key;
        markActive();
        onRoute?.({ screen: key });
        modal.open({
            title: label,
            subtitle: country.name_ko || country.iso3,
            status: stateLabel(status),
            body: sectionContent(country, key, status),
            footnote: missing.length ? `미확보: ${missing.join(', ')}` : '',
            onClose: () => { active = null; markActive(); onRoute?.({ screen: null }); },
            // The 상임위 chips leave the election module entirely, so the jump
            // goes back out through the host adapter rather than this module
            // reaching into the legacy router itself.
            onAction: (action, dataset) => {
                if (action === 'policy-committee') host?.openPolicyCommittee?.(dataset.committeeId);
                if (action === 'policy-committees') host?.openPolicyCommittee?.();
            },
        });
    };

    const markActive = () => {
        root.querySelectorAll('[data-election-tab]').forEach((button) => {
            button.classList.toggle('is-active', button.dataset.electionTab === active);
        });
    };

    const draw = () => {
        const mapStatus = hasMapBlock ? effectiveStatus(manifest, country, MAP_SECTION) : null;
        root.className = 'panel-section elections-country';
        root.innerHTML = `
            <div class="elections-country-actions"><button class="elections-button" type="button" data-election-back>← 세계 지도</button></div>
            <div class="panel-header"><h2>${escapeHtml(country.name_ko || country.iso3)}</h2><p>확보된 공개 데이터만 표시합니다.</p></div>
            ${overview(country)}
            <p class="section-title">권력 구조 · 블록을 누르면 지도 위에 펼쳐집니다</p>
            <div class="elections-block-grid">${tabs.map(([label, key]) => {
                const status = effectiveStatus(manifest, country, key);
                return `<button class="elections-block" type="button" data-election-tab="${key}" ${status === 'disabled' ? 'data-election-disabled="1"' : ''}>
                    <span class="elections-block-label">${escapeHtml(label)}</span>
                    <span class="elections-block-state">${escapeHtml(stateLabel(status))}</span>
                </button>`;
            }).join('')}</div>
            ${hasMapBlock ? `<section class="elections-detail-section">
                <p class="section-title">지도 요약</p>
                ${sectionContent(country, MAP_SECTION, mapStatus)}
            </section>` : ''}
        `;
        root.querySelector('[data-election-back]')?.addEventListener('click', () => {
            modal.close();
            onBack();
        });
        root.querySelectorAll('[data-election-tab]').forEach((button) => button.addEventListener('click', () => {
            const key = button.dataset.electionTab;
            if (key === MAP_SECTION) {
                // Uncover the map rather than describing it in a window.
                modal.close();
                active = null;
                markActive();
                return;
            }
            openSection(key);
        }));
        markActive();
    };
    draw();
    // The explorer needs this to reopen a screen named in the URL.
    return { openSection: (key) => { if (tabs.some(([, tabKey]) => tabKey === key)) openSection(key); } };
};
