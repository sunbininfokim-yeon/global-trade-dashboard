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
