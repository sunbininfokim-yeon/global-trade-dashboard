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

const verdict = (race) => {
    const w = race.windows?.['14'] || {};
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

const raceRow = (race, now) => {
    const dots = dotsFor(race, now);
    const v = verdict(race);
    const names = dots[0]?.s ? `${dots[0].s.left.name.split(' ').at(-1)} vs ${dots[0].s.rep.name.split(' ').at(-1)}` : '';
    const leftParty = dots[0]?.s?.left.party || 'DEM';
    const dotHtml = dots.map(({ o, s, counted }) => {
        const side = s.margin > 0 ? (s.left.party === 'DEM' ? 'is-dem' : 'is-ind') : s.margin < 0 ? 'is-gop' : 'is-close';
        const label = `${o.pollster} · ${o.field_end} · ${o.population?.toUpperCase() || ''} · ${s.left.name} ${s.left.pct} / ${s.rep.name} ${s.rep.pct}${counted ? ' · 14일 집계 포함' : ' · 참고'}`;
        return `<span class="elections-senate-dot ${side}${counted ? ' is-counted' : ''}${Math.abs(s.margin) > AXIS ? ' is-clamped' : ''}" style="left:${position(s.margin).toFixed(1)}%" title="${escapeHtml(label)}"></span>`;
    }).join('');
    const counted = dots.filter((d) => d.counted);
    const leftLead = counted.filter((d) => d.s.margin > 0).length, repLead = counted.filter((d) => d.s.margin < 0).length;
    return `<button type="button" class="elections-senate-row" data-poll-race="${escapeHtml(race.race_id)}" data-overview-state="${escapeHtml(race.state)}" data-overview-office="senate">
        <span class="elections-senate-state"><strong>${escapeHtml(race.state)}</strong><small>${escapeHtml(names)}${leftParty === 'IND' ? ' (무소속)' : ''}</small></span>
        <span class="elections-senate-axis" aria-hidden="true"><i class="elections-senate-zero"></i>${dotHtml}</span>
        <span class="elections-senate-verdict ${v.cls}">${escapeHtml(v.text)}${counted.length ? `<small>집계 ${counted.length}곳: ${leftParty === 'IND' ? 'I' : 'D'} ${leftLead} · R ${repLead}</small>` : `<small>참고 ${dots.length}건</small>`}</span>
    </button>`;
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
