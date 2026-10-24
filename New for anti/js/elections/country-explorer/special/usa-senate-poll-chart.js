import { escapeHtml } from '../../ui.js';

// 상원 여론조사 한눈에: one row per contested Senate race, each pollster's
// latest poll as a dot on a Democratic <-> Republican margin axis. This only
// draws what the pipeline already decided -- the row's verdict is the race's
// own 14-day window status, filled dots are that window's counted polls, and
// everything else is hollow reference. No averaging: the repo counts pollster
// directions, it never blends numbers into a synthetic margin.

const AXIS = 15;
const DOT_DAYS = 30;
const DAY = 86400000;
// Ranked-choice states publish first-preference and simulated final-round
// questions from one wave; only the head-to-head rows go on a two-sided axis.
const RANKED_CHOICE = new Set(['AK', 'ME']);

const sides = (answers) => {
    const rep = answers.filter((a) => a.party === 'REP').sort((a, b) => b.pct - a.pct)[0];
    const left = answers.filter((a) => a.party !== 'REP' && a.pct != null).sort((a, b) => (a.party === 'DEM' ? -1 : 0) - (b.party === 'DEM' ? -1 : 0) || b.pct - a.pct)[0];
    return rep && left ? { left, rep, margin: left.pct - rep.pct } : null;
};

const dotsFor = (race, now) => {
    const window = race.windows?.['14'] || {};
    const counted = new Set(window.included_ids || []);
    const cutoff = new Date(now - DOT_DAYS * DAY).toISOString().slice(0, 10);
    let rows = (race.observations || []).filter((o) => (o.field_end || '') >= cutoff && Array.isArray(o.answers));
    if (RANKED_CHOICE.has(race.state)) {
        const twoWay = rows.filter((o) => o.answers.length === 2);
        const waves = new Set(twoWay.map((o) => `${o.pollster}|${o.field_end}`));
        rows = rows.filter((o) => o.answers.length === 2 || !waves.has(`${o.pollster}|${o.field_end}`));
    }
    // Latest field end per pollster group; LV before RV on the same day.
    const latest = new Map();
    for (const o of rows) {
        const key = o.pollster_group || o.pollster;
        const prev = latest.get(key);
        const better = !prev || o.field_end > prev[0].field_end
            || (o.field_end === prev[0].field_end && o.population === 'lv' && prev[0].population !== 'lv');
        if (better) latest.set(key, [o]);
        else if (o.field_end === prev[0].field_end && o.population === prev[0].population) prev.push(o);
    }
    return [...latest.values()].flat().map((o) => ({ o, s: sides(o.answers), counted: counted.has(o.id) })).filter((d) => d.s);
};

// Lower-confidence layer (board.unreviewed): rows the board holds for review.
// Board reference observations are already on the race; only provider rows
// the board did not admit are added, flagged low so they draw as dashed dots.
const LOW_LABEL = { unreviewed: '원문 미검토', partisan_unreviewed: '당파 후원·원문 미검토', campaign_internal: '캠프 내부·미집계',
    provider_conflict: '원문 불일치·미집계', reference_reviewed: '참고용' };
const withLow = (race, low) => {
    if (!low?.polls?.length) return race;
    const extra = low.polls.filter((p) => p.tier !== 'reference_reviewed').map((p) => ({ id: p.id, pollster: p.pollster,
        field_end: p.field_end, population: p.population, answers: p.answers, low: p.tier }));
    return { ...race, observations: [...(race.observations || []), ...extra] };
};
const lowVerdict = (low) => {
    const c = low?.combined_14;
    const party = { DEM: 'D', REP: 'R', GOP: 'R', IND: 'I' }[c?.party];
    if (!party || !['poll_lead', 'single_poll_lead', 'mixed_lead'].includes(c.status)) return null;
    return { cls: `${party === 'R' ? 'is-gop' : party === 'I' ? 'is-ind' : 'is-dem'} is-low`,
        text: `${party} ${c.status === 'single_poll_lead' ? '앞섬' : '우세'} · 미검토 포함`, party };
};

const verdict = (race, low = null) => {
    const w = race.windows?.['14'] || {};
    const lv = !['poll_lead', 'single_poll_lead', 'tie'].includes(w.status) ? lowVerdict(low) : null;
    if (lv) return lv;
    const party = w.party === 'DEM' ? 'D' : w.party === 'REP' ? 'R' : w.party ? w.party : '';
    switch (w.status) {
        case 'poll_lead': return { cls: party === 'R' ? 'is-gop' : 'is-dem', text: `${party} 우세 (복수 기관)` };
        case 'single_poll_lead': return { cls: party === 'R' ? 'is-gop' : 'is-dem', text: `${party} 앞섬 (단일 기관)` };
        case 'tie': return { cls: 'is-close', text: '동률·엇갈림' };
        default: {
            const last = (race.observations || []).map((o) => o.field_end || '').sort().at(-1);
            return { cls: 'is-none', text: last ? `14일 집계 없음 · 최근 ${last.slice(5).replace('-', '/')}` : '조사 없음' };
        }
    }
};

const position = (margin) => 50 - Math.max(-AXIS, Math.min(AXIS, margin)) / AXIS * 50;

// Latest poll the board may count (aggregation eligible), else the latest
// reference row. Shown as text so the numbers are readable without hovering.
const latestPoll = (race) => {
    const rows = (race.observations || []).filter((o) => Array.isArray(o.answers) && sides(o.answers));
    const newest = (list) => [...list].sort((a, b) => (b.field_end || '').localeCompare(a.field_end || '')
        || (b.population === 'lv') - (a.population === 'lv'))[0];
    const eligible = newest(rows.filter((o) => o.aggregation_eligibility?.eligible));
    const o = eligible || newest(rows);
    return o ? { o, s: sides(o.answers), reference: !eligible, low: o.low } : null;
};
const pct = (v) => Number.isFinite(v) ? String(Math.round(v * 10) / 10) : '—';
const latestText = (race) => {
    const l = latestPoll(race);
    if (!l) return '';
    const day = (l.o.field_end || '').slice(5).replace('-', '/');
    return `최근 ${l.o.pollster} ${day} · ${l.s.left.name.split(' ').at(-1)} ${pct(l.s.left.pct)} · ${l.s.rep.name.split(' ').at(-1)} ${pct(l.s.rep.pct)}${l.low ? ` · ${LOW_LABEL[l.low] || '미검토'}` : l.reference ? ' · 참고' : ''}`;
};

const raceRow = (board_race, now, office = 'senate', low = null) => {
    const race = withLow(board_race, low);
    const lowCounted = new Set(lowVerdict(low) ? low.combined_14.unreviewed_ids || [] : []);
    const dots = dotsFor(race, now).map((d) => ({ ...d, lowCounted: lowCounted.has(d.o.id) }));
    const v = verdict(board_race, low);
    const names = dots[0]?.s ? `${dots[0].s.left.name.split(' ').at(-1)} vs ${dots[0].s.rep.name.split(' ').at(-1)}` : '';
    const leftParty = dots[0]?.s?.left.party || 'DEM';
    const dotHtml = dots.map(({ o, s, counted, lowCounted: lc }) => {
        const side = s.margin > 0 ? (s.left.party === 'DEM' ? 'is-dem' : 'is-ind') : s.margin < 0 ? 'is-gop' : 'is-close';
        const label = `${o.pollster} · ${o.field_end} · ${o.population?.toUpperCase() || ''} · ${s.left.name} ${pct(s.left.pct)} / ${s.rep.name} ${pct(s.rep.pct)}${counted ? ' · 14일 집계 포함' : o.low ? ` · ${LOW_LABEL[o.low] || '미검토'}${lc ? ' · 미검토 판정에 포함' : ''}` : lc ? ' · 참고 · 미검토 판정에 포함' : ' · 참고'}`;
        return `<span class="elections-senate-dot ${side}${counted ? ' is-counted' : ''}${o.low ? ' is-low' : ''}${lc ? ' is-low-counted' : ''}${Math.abs(s.margin) > AXIS ? ' is-clamped' : ''}" style="left:${position(s.margin).toFixed(1)}%" title="${escapeHtml(label)}"></span>`;
    }).join('');
    const counted = dots.filter((d) => d.counted);
    const leftLead = counted.filter((d) => d.s.margin > 0).length, repLead = counted.filter((d) => d.s.margin < 0).length;
    return `<button type="button" class="elections-senate-row" data-poll-race="${escapeHtml(race.race_id)}" data-overview-state="${escapeHtml(race.state)}" data-overview-office="${escapeHtml(office)}">
        <span class="elections-senate-state"><strong>${escapeHtml(race.state)}</strong><small>${escapeHtml(names)}${leftParty === 'IND' ? ' (무소속)' : ''}</small></span>
        <span class="elections-senate-latest">${escapeHtml(latestText(race))}</span>
        <span class="elections-senate-axis" aria-hidden="true"><i class="elections-senate-zero"></i>${dotHtml}</span>
        <span class="elections-senate-verdict ${v.cls}">${escapeHtml(v.text)}${counted.length ? `<small>집계 ${counted.length}곳: ${leftParty === 'IND' ? 'I' : 'D'} ${leftLead} · R ${repLead}</small>` : v.party ? `<small>신뢰도 낮음 · ${lowCounted.size}건 기준</small>` : `<small>참고 ${dots.length}건</small>`}</span>
    </button>`;
};

const leadParty = (race) => {
    const w = race.windows?.['14'] || {};
    return ['poll_lead', 'single_poll_lead'].includes(w.status) ? ({ DEM: 'DEM', REP: 'GOP', GOP: 'GOP', IND: 'IND' }[w.party] || null) : null;
};

// Card summary for one office: of this cycle's contests, how many have any
// poll on the board, and the 14-day pipeline verdict among them. Clicking opens
// the per-race rows underneath. Counts come from the board's own window status.
export const officePollSummaryHtml = (office, contests, board, { now = Date.now() } = {}) => {
    const unit = office === 'governor' ? '곳' : '석';
    const lowOf = (r) => board?.unreviewed?.races?.[r.race_id] || null;
    const races = (contests || []).map((c) => board?.races?.[c.race_id]).filter(Boolean);
    const polled = races.filter((r) => r.observations?.length || lowOf(r)?.polls?.length);
    if (!contests?.length) return '';
    const lead = { DEM: 0, GOP: 0, IND: 0 }, low = { DEM: 0, GOP: 0, IND: 0 };
    for (const r of polled) {
        const p = leadParty(r);
        if (p) { lead[p]++; continue; }
        const lv = lowVerdict(lowOf(r));
        if (lv) low[{ D: 'DEM', R: 'GOP', I: 'IND' }[lv.party]]++;
    }
    const lowTotal = low.DEM + low.GOP + low.IND;
    const held = polled.length - lead.DEM - lead.GOP - lead.IND - lowTotal;
    const order = (r) => (leadParty(r) ? 0 : lowVerdict(lowOf(r)) ? 1 : 2);
    const rows = [...polled].sort((a, b) => order(a) - order(b) || a.state.localeCompare(b.state));
    const single = contests.length === 1 && rows.length === 1;
    return `<details class="elections-office-polls" data-office-polls="${escapeHtml(office)}">
        <summary><span>여론조사 <strong>${polled.length}/${contests.length}${unit}</strong></span>
            <span><b class="is-dem">DEM 우세 ${lead.DEM + low.DEM}</b> · <b class="is-gop">GOP 우세 ${lead.GOP + low.GOP}</b>${lead.IND + low.IND ? ` · <b class="is-ind">무소속 우세 ${lead.IND + low.IND}</b>` : ''} · 판정 보류 ${held}</span>
            ${lowTotal ? `<small class="is-low-confidence">이 중 원문 미검토·참고 조사 판정 ${lowTotal}${unit} (DEM ${low.DEM} · GOP ${low.GOP}${low.IND ? ` · 무소속 ${low.IND}` : ''}) · 신뢰도 낮음</small>` : ''}
            ${single ? `<small>${escapeHtml(latestText(rows[0]))}</small>` : ''}<small>최근 14일 판정 · 눌러서 ${single ? '자세히' : '선거별 보기'}</small></summary>
        ${rows.length ? `<div class="elections-senate-scale" aria-hidden="true"><span class="is-dem">← 민주${office === 'senate' ? '·무소속' : ''}</span><span>±${AXIS}%p · 0</span><span class="is-gop">공화 →</span></div>
        <div class="elections-senate-rows">${rows.map((r) => raceRow(r, now, office, lowOf(r))).join('')}</div>` : ''}
        <p class="elections-panel-note">조사 없음 ${contests.length - polled.length}${unit}. 우세는 최근 14일 안의 조사 판정입니다. 검토 보드 판정이 없으면 원문 미검토·참고 조사로 판정하고 '미검토 포함'으로 표시합니다(신뢰도 낮음, 캠프 내부·원문 불일치는 제외). ● 검토 집계 포함, ◍ 미검토 판정 포함, ○ 참고, 점선=원문 미검토. 평균이나 당선 예측이 아닙니다.</p>
    </details>`;
};

export const senatePollChartHtml = (races, { now = Date.now() } = {}) => {
    const senate = (races || []).filter((r) => r.office === 'senate' && r.observations?.length);
    if (senate.length < 3) return '';
    const order = (r) => {
        const counted = dotsFor(r, now).filter((d) => d.counted).map((d) => Math.abs(d.s.margin));
        return counted.length ? Math.min(...counted) : 100 + (Date.parse('2027-01-01') - Date.parse((r.observations.map((o) => o.field_end).sort().at(-1)) || '2026-01-01')) / DAY / 1000;
    };
    const rows = [...senate].sort((a, b) => order(a) - order(b) || a.state.localeCompare(b.state));
    const hasRcv = rows.some((r) => RANKED_CHOICE.has(r.state));
    return `<section class="elections-senate-chart" aria-label="상원 여론조사 한눈에">
        <header><strong>상원 여론조사 한눈에</strong><small>${rows.length}개 선거 · 기관별 최신 조사(최근 ${DOT_DAYS}일)</small></header>
        <div class="elections-senate-scale" aria-hidden="true"><span class="is-dem">← 민주·무소속</span><span>±${AXIS}%p · 0</span><span class="is-gop">공화 →</span></div>
        <div class="elections-senate-rows">${rows.map((r) => raceRow(r, now)).join('')}</div>
        <p class="elections-panel-note">● 채운 점은 최근 14일 우세 판정에 들어간 조사, ○ 빈 점은 참고 조사입니다. 눈금 끝은 ±${AXIS}%p이고, 넘는 값은 끝에 붙입니다. 오른쪽 판정은 파이프라인의 14일 판정을 그대로 옮긴 것이며 평균이나 당선 예측이 아닙니다.${hasRcv ? ' 알래스카·메인은 순위선택투표라서 같은 조사에 결선 모의 문항이 있으면 그 문항만 점으로 찍습니다(1순위 문항은 제외).' : ''}</p>
    </section>`;
};
