import { escapeHtml } from '../../ui.js';
import { personnelKeyTiers } from './personnel-roster.js';

// 권력이 둘 이상으로 갈린 나라(리비아·예멘)의 '권력 구조' 화면. 중국 당·국가 화면처럼
// 번호 단과 조직도 박스로 그리되, 단 묶음을 '어느 쪽'으로 먼저 나눈다 -- 한 나라에
// 정부가 둘이면 한 줄의 조직도로 합치는 순간 사실이 아닌 그림이 된다.
// 쪽 구성(이름·설명·인사 명단 키)은 profile.authorities 가 정한다.
export const isDivided = (country) => country?.mode === 'divided_authority' && Array.isArray(country.authorities);

export const dividedAuthorityKeys = (country) => new Set((country?.authorities || []).flatMap((side) => side.keys || []));

export const dividedAuthorityHtml = (country) => {
    if (!isDivided(country)) return null;
    const data = country.personnel;
    let n = 0;
    const sides = country.authorities.map((side) => {
        const tiers = data ? personnelKeyTiers(data, side.keys || []) : [];
        return `<section class="da-side">
            <p class="da-side-title">${escapeHtml(side.label_ko)}</p>
            ${side.note_ko ? `<p class="elections-panel-note">${escapeHtml(side.note_ko)}</p>` : ''}
            ${tiers.length ? tiers.map((t) => { n += 1; return `<p class="section-title">${n} · ${escapeHtml(t.title)}${t.count > 1 ? ` ${t.count}인` : ''}</p>${t.html}`; }).join('')
        : '<p class="elections-muted">확보된 인사 명단이 없습니다.</p>'}
        </section>`;
    });
    const poles = data?.orientation?.poles || [];
    return `
        <p class="elections-panel-note">${escapeHtml(country.political_context?.note_ko || '한 나라 안에 서로 정통성을 주장하는 권력이 둘 이상 있습니다.')}</p>
        <div class="da-grid">${sides.join('')}</div>
        ${poles.length ? `<p class="section-title">${n + 1} · 권력 축</p>${poles.map((p) => `<p class="pr-note"><b>${escapeHtml(p.pole || '')}</b> ${escapeHtml(p.line || '')}</p>`).join('')}` : ''}
        <p class="elections-panel-note">각 쪽의 직함은 그쪽 공식 매체가 적은 대로입니다. 어느 쪽이 정통인지 판정하지 않습니다. 인사 기준일 ${escapeHtml(data?.as_of || '')}.</p>`;
};

// 우측 요약 카드: 국가 수반 한 명을 고를 수 없는 나라라 쪽 이름을 그대로 보인다.
export const dividedOverviewCards = (country) => (isDivided(country) ? [
    ['권력 구도', `${country.authorities.length}개 권력 병존`],
    ['병존 권력', country.authorities.map((side) => side.label_ko).join(' · ')],
] : null);

// ---- 쪽별 대시보드 (정부 측 / 반군·경쟁 세력) -------------------------------------
// profile.camps 가 쪽 이름·위상·색·배경 설명을 갖고, control_map 이 지역별 대략적 통제를
// 갖는다. 지도자 박스는 그 쪽 authorities 의 인사 명단 키에서 뽑는다.
export const campKey = (id) => `camp_${id}`;
export const campTabs = (country) => (isDivided(country) && Array.isArray(country.camps)
    ? country.camps.map((camp) => [camp.label_ko, campKey(camp.id)]) : []);

const rgb = (c) => `rgb(${(c || [148, 163, 184]).slice(0, 3).join(',')})`;

const campRegions = (country, campId) => Object.entries(country.control_map?.regions || {})
    .filter(([, r]) => r.camp === campId)
    .map(([code, r]) => ({ code, ...r }));

const BRIEF_ROWS = [
    ['status_ko', '위상'], ['base_ko', '근거지'], ['armed_ko', '무장 세력'], ['backers_ko', '대외 후원'], ['claim_ko', '정통성 주장'],
];

export const campHtml = (country, section) => {
    if (!isDivided(country)) return null;
    const camp = (country.camps || []).find((c) => campKey(c.id) === section);
    if (!camp) return null;
    const sides = (country.authorities || []).filter((side) => (camp.authority_ids || []).includes(side.id));
    const data = country.personnel;
    let n = 0;
    const leaders = sides.map((side) => {
        const tiers = data ? personnelKeyTiers(data, side.keys || []) : [];
        return tiers.map((t) => { n += 1; return `<p class="section-title">${n} · ${escapeHtml(side.label_ko)} · ${escapeHtml(t.title)}${t.count > 1 ? ` ${t.count}인` : ''}</p>${t.html}`; }).join('');
    }).join('');
    const regions = campRegions(country, camp.id);
    const firm = regions.filter((r) => !r.contested);
    const contested = regions.filter((r) => r.contested);
    const brief = camp.brief || {};
    return `
        <div class="da-camp-head"><i style="background:${rgb(camp.color)}"></i><b>${escapeHtml(camp.label_ko)}</b><em>${escapeHtml(camp.role_ko || '')}</em></div>
        <div class="elections-card-grid da-brief">
            ${BRIEF_ROWS.filter(([k]) => brief[k]).map(([k, label]) => `<article class="elections-card"><div class="elections-card-label">${label}</div><div class="elections-card-value da-brief-text">${escapeHtml(brief[k])}</div></article>`).join('')}
        </div>
        <p class="section-title">통제 지역 ${regions.length}곳${contested.length ? ` · 그중 혼재·전선 ${contested.length}곳` : ''}</p>
        <div class="pr-chips">${firm.map((r) => `<span style="border-color:${rgb(camp.color)}">${escapeHtml(r.name_ko || r.code)}</span>`).join('')}</div>
        ${contested.length ? `<div class="elections-disclosure-rows da-contested">${contested.map((r) => `<div><span>${escapeHtml(r.name_ko || r.code)}</span><strong class="da-pole">${escapeHtml(r.note_ko || '혼재')}</strong></div>`).join('')}</div>` : ''}
        ${leaders ? `<p class="section-title da-gap">지도부</p>${leaders}` : '<p class="elections-muted">확보된 인사 명단이 없습니다.</p>'}
        <p class="elections-panel-note">${escapeHtml(country.control_map?.basis_ko || '')} 통제 지역 기준 ${escapeHtml(country.control_map?.as_of || '')}, 대략적 구분.</p>`;
};

// 우측 패널의 '지도' 요약: 쪽별 색과 지역 수. 지도를 덮지 않고 패널에 상주한다.
export const controlMapSummaryHtml = (country) => {
    if (!isDivided(country) || !country.control_map) return null;
    return `<div class="da-legend">${(country.camps || []).map((camp) => {
        const regions = campRegions(country, camp.id);
        const contested = regions.filter((r) => r.contested).length;
        return `<div><i style="background:${rgb(camp.color)}"></i><b>${escapeHtml(camp.label_ko)}</b><span>${regions.length}곳${contested ? ` (혼재 ${contested})` : ''}</span></div>`;
    }).join('')}
    <p class="elections-panel-note">지도에서 지역을 누르면 그 쪽 대시보드가 열립니다. 옅은 색·흰 테두리는 혼재·전선 지역입니다. 대략적 구분(${escapeHtml(country.control_map.as_of || '')}).</p></div>`;
};

export const controlColor = (country, code) => {
    const region = country?.control_map?.regions?.[code];
    if (!region) return null;
    const camp = (country.camps || []).find((c) => c.id === region.camp);
    const [r, g, b] = camp?.color || [148, 163, 184];
    return region.contested ? [r, g, b, 120] : [r, g, b, 215];
};
export const controlCamp = (country, code) => country?.control_map?.regions?.[code]?.camp || null;
