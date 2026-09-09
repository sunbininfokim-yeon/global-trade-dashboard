import { escapeHtml, formatDate } from '../../ui.js';

// race_progress is schema-generic (race_progress_v1), not USA-only: the
// manifest already declares it for JPN/USA/RUS/CHN/DEU/KOR/GBR/FRA/IND/TWN/
// BRA/ZAF/ISR/NGA/IRN/IDN/TUR/SAU/ARE, but only USA and KOR ship data today.
// Dispatch is by `mode`, not `iso3`, so a third country landing in one of
// these two modes (or a future mode this file grows a branch for) picks up
// the same renderer without touching country-shell.js again.

const partyKo = (abbr) => ({ D: '민주당', R: '공화당', I: '무소속' }[abbr] || abbr || '불명');
const partyClass = (abbr) => ({ D: 'elections-party-d', R: 'elections-party-r' }[abbr] || '');

const statCard = (label, value, note = '') => `
    <article class="elections-card">
        <div class="elections-card-label">${escapeHtml(label)}</div>
        <div class="elections-card-value">${escapeHtml(value)}</div>
        ${note ? `<div class="elections-event-meta">${escapeHtml(note)}</div>` : ''}
    </article>`;

// The pipeline ships an `aggregation` block precisely so the UI never has to
// guess how interim numbers combine (equal-weight schedule counter vs. a
// 70/30 weighted convention). Surfacing summary_ko + components verbatim
// keeps that explanation attached to the numbers instead of re-derived here.
const aggregationBox = (race) => {
    const agg = race.aggregation;
    if (!agg?.model_id) return '';
    const rows = (agg.components || []).map((component) => {
        const weight = component.final_weight_pct != null ? ` · 최종 반영 ${component.final_weight_pct}%` : '';
        const modifier = component.modifier_pct != null
            ? ` · 가중 +${component.modifier_pct}%${(component.applies_to || []).length ? ` (${component.applies_to.join('·')})` : ''}`
            : '';
        return `<div><span>${escapeHtml(component.label_ko || component.id)}</span><strong>${escapeHtml(`${component.unit || ''}${weight}${modifier}`)}</strong></div>`;
    });
    const caution = agg.interim_display?.user_caution_ko;
    return `
        <details class="elections-disclosure" open>
            <summary>${escapeHtml(agg.model_label_ko || agg.model_id)}${agg.interim_display?.is_final_score === false ? ' · 중간 집계 (최종 아님)' : ''}</summary>
            ${agg.summary_ko ? `<p class="elections-panel-note">${escapeHtml(agg.summary_ko)}</p>` : ''}
            ${rows.length ? `<div class="elections-disclosure-rows">${rows.join('')}</div>` : ''}
            ${caution ? `<p class="elections-panel-note">${escapeHtml(caution)}</p>` : ''}
        </details>`;
};

const leaderBar = (sharePct) => {
    const entries = Object.entries(sharePct || {}).filter(([, pct]) => pct != null);
    if (!entries.length) return '';
    const colors = ['#38bdf8', '#f28b8b', '#94a3b8', '#34d399'];
    const bar = entries.map(([name, pct], index) => `<span style="width:${pct}%;background:${colors[index % colors.length]}"></span>`).join('');
    const legend = entries.map(([name, pct], index) => `<span class="elections-race-legend-item"><i style="background:${colors[index % colors.length]}"></i>${escapeHtml(`${name} ${pct}%`)}</span>`).join('');
    return `<div class="elections-race-leader-bar">${bar}</div><div class="elections-race-legend">${legend}</div>`;
};

// office is a raw pipeline id like "house AR-01"; office_kind picks the
// Korean label and, for house seats, the district number is the only part
// of that id worth keeping (the state is already the enclosing unit).
const officeLabel = (contest) => {
    if (contest.office_kind === 'senate') return '상원';
    if (contest.office_kind === 'governor') return '주지사';
    if (contest.office_kind === 'house') {
        const district = String(contest.office || '').split('-').pop();
        return district && district !== contest.office ? `하원 ${district}구` : '하원';
    }
    return contest.office || '불명';
};

// usa_election_finance_index_v1.json's rules_ko is explicit: only the
// `super_pac` category may be labeled "슈퍼팩" -- the other 6 categories
// (hybrid_pac, unclassified, ...) are real but different spender types.
// null means "not yet observed", never "$0" (same file, same rule); the two
// render differently below rather than collapsing null to 0.
const officeKo = { governor: '주지사', senate: '연방 상원', house: '연방 하원(주 전체 합산)' };
const formatUsd = (cents) => {
    const dollars = cents / 100;
    if (Math.abs(dollars) >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
    if (Math.abs(dollars) >= 1_000) return `$${(dollars / 1_000).toFixed(0)}K`;
    return `$${dollars.toLocaleString('en-US')}`;
};
const superPacRow = (officeKind, totals) => {
    const superPac = totals?.super_pac;
    if (!superPac) return '';
    const label = officeKo[officeKind] || officeKind;
    if (superPac.support_cents == null && superPac.oppose_cents == null) {
        return `<div><span>${escapeHtml(label)}</span><strong>관측 없음</strong></div>`;
    }
    const support = superPac.support_cents != null ? formatUsd(superPac.support_cents) : '관측 없음';
    const oppose = superPac.oppose_cents != null ? formatUsd(superPac.oppose_cents) : '관측 없음';
    return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(`지지 ${support} · 반대 ${oppose}`)}</strong></div>`;
};
const superPacBlock = (unit, financeByState) => {
    const totalsByOffice = financeByState?.[unit.id]?.totals_by_office;
    if (!totalsByOffice) return '';
    const officeKinds = [...new Set((unit.contests || []).map((contest) => contest.office_kind))];
    const rows = officeKinds.map((kind) => superPacRow(kind, totalsByOffice[kind])).filter(Boolean);
    if (!rows.length) return '';
    return `
        <p class="elections-panel-note">슈퍼팩(super_pac) 독립지출 · 후보 대상 외부 지출이며 캠프 후원금이 아닙니다. 하원은 그 주 선거구 전체 합산입니다.</p>
        <div class="elections-disclosure-rows">${rows.join('')}</div>`;
};

const usaUnit = (unit, financeByState) => {
    const rows = (unit.contests || []).map((contest) => {
        return `<tr><td>${escapeHtml(officeLabel(contest))}</td><td class="${partyClass(contest.party)}">${escapeHtml(partyKo(contest.party))}</td><td>${escapeHtml(contest.winner)}</td></tr>`;
    }).join('');
    const empty = unit.status === 'completed' ? '주 전체 승자 파싱 없음 · 하원 확장 중' : '미실시';
    return `
        <details class="elections-race-unit is-${unit.status || 'scheduled'}">
            <summary>
                <span class="elections-race-unit-date">${escapeHtml(formatDate(unit.date))}</span>
                <span class="elections-race-unit-label">${escapeHtml(unit.name_ko || unit.id)}<em>${escapeHtml(unit.id)}</em></span>
                <span class="elections-race-unit-headline">${escapeHtml(unit.headline)}</span>
            </summary>
            <table class="elections-race-table">
                <thead><tr><th>직위</th><th>당</th><th>승자</th></tr></thead>
                <tbody>${rows || `<tr><td colspan="3">${escapeHtml(empty)}</td></tr>`}</tbody>
            </table>
            ${superPacBlock(unit, financeByState)}
        </details>`;
};

const renderUsaRace = (race, financeByState) => {
    const c = race.cumulative || {};
    return `
        ${race.race?.note_ko ? `<p class="elections-panel-note">${escapeHtml(race.race.note_ko)}</p>` : ''}
        <div class="elections-card-grid">
            ${statCard('완료 주', `${c.states_completed ?? 0} / ${c.states_in_calendar ?? 0}`)}
            ${statCard('남은 주', `${c.states_pending ?? 0}`)}
            ${statCard('총선일', c.general_election)}
            ${statCard('주 전체 승자 파싱', `${c.states_with_statewide_winners_parsed ?? 0}주`)}
        </div>
        ${aggregationBox(race)}
        <p class="section-title">주별 진행 · 눌러서 공천 승자와 슈퍼팩 지출을 펼칩니다</p>
        <div class="elections-race-unit-list">${(race.units || []).map((unit) => usaUnit(unit, financeByState)).join('')}</div>
    `;
};

const korUnit = (unit) => {
    const rows = (unit.results || []).map((result) => `<tr><td>${escapeHtml(result.name_ko)}</td><td>${result.pct != null ? `${result.pct}%` : '불명'}</td><td>${result.votes != null ? result.votes.toLocaleString('ko-KR') : '불명'}</td></tr>`).join('');
    const subunitRows = (unit.subunits || []).map((sub) => {
        const winnerPct = sub.winner && sub.results_pct?.[sub.winner] != null ? `${sub.results_pct[sub.winner]}%` : '';
        return `<tr><td colspan="3" class="elections-race-subunit">${escapeHtml(sub.label_ko || sub.id)} · ${escapeHtml([sub.winner, winnerPct].filter(Boolean).join(' '))}</td></tr>`;
    }).join('');
    return `
        <details class="elections-race-unit is-${unit.status || 'scheduled'}">
            <summary>
                <span class="elections-race-unit-date">${escapeHtml(formatDate(unit.date))}</span>
                <span class="elections-race-unit-label">${escapeHtml(unit.label_ko || unit.id)}</span>
                <span class="elections-race-unit-headline">${unit.status === 'completed' ? escapeHtml(unit.winner) : '예정'}</span>
            </summary>
            <table class="elections-race-table">
                <thead><tr><th>후보</th><th>비중</th><th>표</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="3">불명</td></tr>'}${subunitRows}</tbody>
            </table>
        </details>`;
};

const renderKorRace = (race) => {
    const c = race.cumulative || {};
    return `
        <p class="elections-panel-note">${escapeHtml(['최종', race.race?.final_date, race.race?.venue_final].filter(Boolean).join(' '))}${c.scope ? ` · ${escapeHtml(c.scope)}` : ''}</p>
        <div class="elections-card-grid">
            ${statCard('누적 선두', c.leader)}
            ${statCard('격차', c.margin_pp != null ? `${c.margin_pp}pp` : '불명')}
            ${statCard('권역 진행', `${c.stops_completed ?? 0} / ${(c.stops_completed ?? 0) + (c.stops_remaining ?? 0)}`)}
        </div>
        ${leaderBar(c.share_pct)}
        ${aggregationBox(race)}
        <p class="section-title">권역별 순회 · 눌러서 중간 집계를 펼칩니다</p>
        <div class="elections-race-unit-list">${(race.units || []).map(korUnit).join('')}</div>
        ${c.source ? `<p class="elections-panel-note">출처: ${escapeHtml(c.source)}</p>` : ''}
    `;
};

export const raceProgressContent = (country) => {
    const race = country.race_progress;
    if (!race) return null;
    if (race.mode === 'rolling_state_primary_midterms') return renderUsaRace(race, country.election_finance?.states);
    if (race.mode === 'party_leadership_tour_interim') return renderKorRace(race);
    return '<p class="elections-muted">이 국가의 선거 진행 형식은 아직 대시보드에 연결되지 않았습니다.</p>';
};
