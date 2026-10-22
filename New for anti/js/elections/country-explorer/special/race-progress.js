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

const usaUnit = (unit) => {
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
        </details>`;
};

const renderUsaRace = (race) => {
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
        <p class="section-title">주별 진행 · 눌러서 공천 승자를 펼칩니다</p>
        <div class="elections-race-unit-list">${(race.units || []).map(usaUnit).join('')}</div>
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

// A plenum's phase comes from its dates against today in Beijing, not from a
// stored status: the file is written before the meeting opens and must not
// keep saying 예정 while it runs, or 진행 중 after it closes. Closed without a
// communique in the file reads as 공보 반영 대기 -- never as a settled outcome.
const beijingToday = (now) => new Date(now + 8 * 3600 * 1000).toISOString().slice(0, 10);
const plenumPhase = (plenum, today) => {
    if (today < plenum.start) return { status: 'scheduled', label: '예정' };
    if (today <= plenum.end) return { status: 'ongoing', label: '진행 중' };
    return plenum.outcome_ko ? { status: 'completed', label: '완료' } : { status: 'ongoing', label: '폐막 · 공보 반영 대기' };
};
const sourceLink = (url, label = '원문 ↗') => /^https:\/\//.test(url || '')
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : '';
// Plenums span five years, so the year has to stay on every row (formatDate
// drops it, which turned 2022's 1중전회 into "10월 23일").
const ymd = (iso) => { const [y, m, d] = String(iso).split('-'); return `${y}.${Number(m)}.${Number(d)}`; };
const dateRange = (start, end) => start === end ? ymd(start)
    : start.slice(0, 7) === end.slice(0, 7) ? `${ymd(start)}~${Number(end.slice(8))}` : `${ymd(start)}~${ymd(end).slice(5)}`;

const chnPlenum = (plenum, today) => {
    const phase = plenumPhase(plenum, today);
    return `
        <details class="elections-race-unit is-${phase.status}"${phase.status === 'completed' ? '' : ' open'}>
            <summary>
                <span class="elections-race-unit-date">${escapeHtml(dateRange(plenum.start, plenum.end))}</span>
                <span class="elections-race-unit-label">${escapeHtml(plenum.label_ko)}</span>
                <span class="elections-race-unit-headline">${escapeHtml(phase.label)}</span>
            </summary>
            <p class="elections-panel-note"><b>의제</b> ${escapeHtml(plenum.agenda_ko)}</p>
            <p class="elections-panel-note"><b>결과</b> ${escapeHtml(plenum.outcome_ko || '공보 전 · 미확정')}</p>
            ${plenum.note_ko ? `<p class="elections-panel-note">${escapeHtml(plenum.note_ko)}</p>` : ''}
            ${plenum.source_url ? `<p class="elections-panel-note elections-origin-links">${sourceLink(plenum.source_url)}</p>` : ''}
        </details>`;
};

const renderChnPlenums = (race, now = Date.now()) => {
    const today = beijingToday(now);
    const plenums = [...(race.plenums || [])].sort((a, b) => a.start.localeCompare(b.start));
    const next = plenums.find((p) => plenumPhase(p, today).status !== 'completed');
    const done = plenums.filter((p) => plenumPhase(p, today).status === 'completed').length;
    const pending = race.pending_confirmations || [];
    return `
        ${race.race?.note_ko ? `<p class="elections-panel-note">${escapeHtml(race.race.note_ko)}</p>` : ''}
        <div class="elections-card-grid">
            ${statCard('다음 전회', next ? next.label_ko : '없음', next ? `${dateRange(next.start, next.end)} · ${plenumPhase(next, today).label}` : '')}
            ${statCard('20기 전회 진행', `${done}회 완료`, `기준 ${race.as_of}`)}
            ${statCard('추인 대기 제명', `${pending.length}건`, '전회 공보로 확정')}
            ${statCard('다음 당대회', '21차', race.race?.congress_ko ? '관례상 2027년 · 공식 일정 미발표' : '')}
        </div>
        <p class="section-title">20기 중앙위원회 전체회의 · 눌러서 의제와 결과를 펼칩니다</p>
        <div class="elections-race-unit-list">${plenums.slice().reverse().map((p) => chnPlenum(p, today)).join('')}</div>
        ${(race.politburo_meetings || []).length ? `
        <p class="section-title">전회 준비 정치국 회의</p>
        <div class="elections-screen-list">${race.politburo_meetings.map((m) => `<article class="elections-event"><div class="elections-event-title">${escapeHtml(m.summary_ko)}</div><div class="elections-event-meta">${escapeHtml(ymd(m.date))} · 정치국 회의 <span class="elections-origin-links">${sourceLink(m.source_url)}</span></div></article>`).join('')}</div>` : ''}
        ${pending.length ? `
        <p class="section-title">전회 추인을 기다리는 인사</p>
        <table class="elections-race-table">
            <thead><tr><th>인물</th><th>상태</th><th>근거</th></tr></thead>
            <tbody>${pending.map((p) => `<tr><td>${escapeHtml(p.name_ko)}</td><td>${escapeHtml(p.status_ko)}</td><td>${escapeHtml(`${p.basis_ko} · ${p.source_ko}`)}</td></tr>`).join('')}</tbody>
        </table>` : ''}
        ${(race.communique_checks_ko || []).length || (race.watch_words || []).length ? `
        <details class="elections-disclosure">
            <summary>공보가 나오면 대조할 항목</summary>
            ${(race.communique_checks_ko || []).length ? `${race.communique_checks_ko.map((c, i) => `<p class="elections-panel-note"><b>인사 ${i + 1}</b> ${escapeHtml(c)}</p>`).join('')}` : ''}
            ${(race.watch_words || []).length ? `<p class="elections-panel-note">${escapeHtml(race.watch_words_note_ko || '')} ${race.watch_words.map((w) => `<code>${escapeHtml(w)}</code>`).join(' ')}</p>` : ''}
        </details>` : ''}
        ${race.outside_slots_ko ? `<p class="elections-panel-note">${escapeHtml(race.outside_slots_ko)}</p>` : ''}
        ${race.race?.congress_ko ? `<p class="elections-panel-note">${escapeHtml(race.race.congress_ko)}</p>` : ''}
    `;
};

export const raceProgressContent = (country, now = Date.now()) => {
    const race = country.race_progress;
    if (!race) return null;
    if (race.mode === 'rolling_state_primary_midterms') return renderUsaRace(race);
    if (race.mode === 'party_leadership_tour_interim') return renderKorRace(race);
    if (race.mode === 'party_plenum_cycle') return renderChnPlenums(race, now);
    return '<p class="elections-muted">이 국가의 선거 진행 형식은 아직 대시보드에 연결되지 않았습니다.</p>';
};
