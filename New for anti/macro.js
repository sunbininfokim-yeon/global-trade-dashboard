// Macro monitor for Global Trade Dashboard -- world map, per-country
// indicator chips, and the drawer with history charts and status panels.
//
// Split out of app.js (2026-08-20). app.js is shared by several parallel
// sessions, and a squash merge replaces whole regions rather than diffing
// them, which has silently deleted unrelated work from main before (see
// trade.js). This domain calls nothing outside itself.
//
// Loaded BEFORE market-microstructure.js and calculator.js, which call
// mmLineChart and mmFmt from here. Non-module scripts share one global scope,
// so these top-level declarations are visible to them the same as before.
// Relies on globals still in app.js: finEsc and the DOM helpers.

// === 매크로 모니터 =========================================================
//
// Engine and schema are Cursor's (scripts/macro_monitor); this file only draws.
// The map is the view -- no side dashboards -- so a country opens as an overlay
// on top of the globe rather than pushing it aside.
let MM_INDEX = null;
let MM_COUNTRY = null;          // currently opened country payload
let MM_TAB = 'liquidity';
let MM_CHART = null;            // { indicatorId, window }

const mmFetch = async (iso3) => {
    const q = iso3 ? `?country=${encodeURIComponent(iso3)}` : '';
    const res = await fetch(`/api/macro-monitor${q}`);
    if (!res.ok) throw new Error(`매크로 데이터를 못 받았습니다 (${res.status})`);
    return res.json();
};

const mmDelta = (v) => {
    if (v === null || v === undefined || !Number.isFinite(v)) return '';
    const cls = v > 0 ? 'mm-up' : (v < 0 ? 'mm-down' : 'mm-flat');
    const sign = v > 0 ? '+' : '';
    return `<span class="mm-delta ${cls}">${sign}${v.toFixed(1)}%</span>`;
};

// Most of this pack is synthetic. Without a visible state a fixture and a real
// quote look identical, and the per-metric note ("당국 공표·추정") then reads as
// a source claim for a number nobody fetched. The badge carries the state; the
// note stays as the metric's definition.
const MM_STATUS = {
    live: { label: '실데이터', cls: 'live' },
    live_latest: { label: '최근값 실데이터', cls: 'latest' },
    official_snapshot: { label: '공식 문서 스냅샷', cls: 'official' },
    delayed_official: { label: '공식 지연 데이터', cls: 'delayed' },
    demo: { label: '합성 데모', cls: 'demo' },
    unknown: { label: '상태 미확인', cls: 'unknown' },
};
const mmStatus = (s) => MM_STATUS[s] || MM_STATUS.unknown;
const mmStatusBadge = (s) => {
    const st = mmStatus(s);
    return `<span class="mm-data-status mm-data-status-${st.cls}">${st.label}</span>`;
};
// A synthetic series has no observation behind it, so its note has to be read
// as "what this metric means", never as "where this number came from".
// A monthly inflation print is read as four numbers: this month's YoY and MoM,
// each against what the market expected. Consensus has no free public source,
// so its slot renders as a dash -- an empty expectation is information, an
// invented one is not.
const mmPrintPair = (item) => {
    const modes = item.modes || {};
    if (!modes.yoy && !modes.mom) return '';
    const f = item.forecast || {};
    const cell = (mode, fc, tag) => {
        if (!mode) return '';
        const exp = Number.isFinite(fc) ? `${fc.toFixed(2)}%` : '—';
        return `<span class="mm-print">
            <span class="mm-print-tag">${tag}</span>
            <span class="mm-print-act">${finEsc(mode.display ?? '—')}</span>
            <span class="mm-print-exp">(${exp})</span>
        </span>`;
    };
    return `<span class="mm-prints">
        ${cell(modes.yoy, f.yoy_pct, 'YoY')}
        ${cell(modes.mom, f.mom_pct, 'MoM')}
    </span>`;
};

const mmNoteWithState = (item) => {
    const note = item.note_ko || '';
    if (item.data_status !== 'demo') return note;
    return `${note ? note + ' ' : ''}— 이 값은 합성 데모입니다. 위 설명은 지표의 정의이지 이 숫자의 출처가 아닙니다.`;
};

const mmFmt = (v, digits) => {
    if (!Number.isFinite(v)) return '—';
    const a = Math.abs(v);
    const dg = digits ?? (a >= 1000 ? 0 : (a >= 10 ? 1 : 2));
    return v.toLocaleString('ko-KR', { minimumFractionDigits: dg, maximumFractionDigits: dg });
};

// Inline SVG rather than a charting library: the drawer opens and closes on
// every chip click, and avoiding a canvas lifecycle at that rate is worth more
// than the features a library would add. Hover is wired after paint (mmWire).
const MM_W = 760, MM_H = 260, MM_L = 52, MM_R = 16, MM_T = 14, MM_B = 30;

// The Fed balance sheet drawn as two stacks -- what it bought, and who ended
// up holding the cash it paid with -- plus reserves as a share of GDP.
//
// The total-assets line answers "how big" but not "made of what", and the
// composition is where the liquidity signal is: the same 6.7T means different
// things depending on whether the liabilities sit in reserve balances (banks'
// usable cash) or in currency and the TGA, which are not. Reserve balances are
// the bottom band, against the axis, because the question is how much room is
// left before reserves get scarce -- a band floating on three others has no
// readable distance to zero.
//
// Both sides total the same by construction, so they share one y-scale. Drawing
// them to separate scales would make the taller-looking side the bigger one and
// invite a comparison that is not there.
const MM_BS_H = 210, MM_BS_T = 12, MM_BS_B = 26;

const mmStackSide = (side, dates, hi, sideIdx) => {
    const layers = side.layers || [];
    const n = dates.length;

    // A week missing any layer cannot be stacked -- the bands above it would
    // slide down and silently misattribute the gap to a neighbour.
    const ok = [];
    for (let i = 0; i < n; i++) {
        if (layers.every((l) => Number.isFinite((l.values || [])[i]))) ok.push(i);
    }
    if (!ok.length) return '<p class="fin-note">완전한 주차가 없어 누적 그래프를 그릴 수 없습니다.</p>';

    const sx = (k) => MM_L + (k / Math.max(ok.length - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => MM_BS_T + (1 - v / hi) * (MM_BS_H - MM_BS_T - MM_BS_B);

    // Each band is its own closed polygon between the running total below it
    // and the running total including it, so the fills abut exactly.
    let below = new Array(ok.length).fill(0);
    const bands = layers.map((l) => {
        const above = ok.map((i, k) => below[k] + l.values[i]);
        const up = above.map((v, k) => `${sx(k).toFixed(1)},${sy(v).toFixed(1)}`);
        const down = below.map((v, k) => `${sx(k).toFixed(1)},${sy(v).toFixed(1)}`).reverse();
        below = above;
        return `<polygon points="${up.concat(down).join(' ')}" fill="${finEsc(l.color)}" fill-opacity="0.85"/>`;
    }).join('');

    const ticks = [0, 0.5, 1].map((t) => hi * t);
    const last = ok.length - 1;

    return `
    <div class="mm-bs-side" data-mm-bs="${sideIdx}"
         data-rows='${finEsc(JSON.stringify(ok))}'>
        <div class="mm-bs-head">
            <span class="mm-bs-title">${finEsc(side.label_ko || '')}</span>
            <span class="mm-bs-sub">${finEsc(side.note_ko || '')}</span>
        </div>
        <svg class="mm-chart mm-bs-chart" viewBox="0 0 ${MM_W} ${MM_BS_H}" preserveAspectRatio="none"
             role="img" aria-label="${finEsc(side.label_ko || '')} 구성 누적 그래프">
            ${ticks.map((t) => `
                <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t, 1)}</text>`).join('')}
            ${bands}
            ${[0, Math.floor(last / 2), last].map((k) => `<text x="${sx(k).toFixed(1)}" y="${MM_BS_H - 7}"
                class="mm-tick" text-anchor="${k === 0 ? 'start' : (k === last ? 'end' : 'middle')}">${finEsc(dates[ok[k]] || '')}</text>`).join('')}
            <line class="mm-cross mm-bs-cross" x1="0" y1="${MM_BS_T}" x2="0" y2="${MM_BS_H - MM_BS_B}" style="display:none"/>
        </svg>
    </div>`;
};

// Reserves as a share of nominal GDP, with the 10% reference line. The line is
// drawn red because the ratio is currently under it, not to assert that
// crossing it triggers anything -- the caption says so in as many words.
const mmReservesRatio = (r, dates) => {
    const vals = r.values || [];
    const idx = vals.map((v, i) => [i, v]).filter(([, v]) => Number.isFinite(v));
    if (!idx.length) return '';

    const th = Number.isFinite(r.threshold_pct) ? r.threshold_pct : null;
    const ys = idx.map(([, v]) => v).concat(th === null ? [] : [th]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pad = (hi - lo || 1) * 0.15;
    lo = Math.max(0, lo - pad); hi += pad;

    const H = 150, T = 10, B = 26;
    const sx = (i) => MM_L + (i / Math.max(vals.length - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const path = idx.map(([i, v], k) => `${k ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join('');

    const [li, lv] = idx[idx.length - 1];
    const under = th !== null && lv < th;

    return `
    <div class="mm-ratio-panel">
        <div class="mm-ratio-head">
            <span class="mm-ratio-label">${finEsc(r.label_ko || '')}</span>
            <span class="mm-ratio-now ${under ? 'is-under' : ''}">${mmFmt(lv, 2)}%</span>
        </div>
        <svg class="mm-chart mm-ratio-chart" viewBox="0 0 ${MM_W} ${H}" preserveAspectRatio="none" role="img"
             aria-label="${finEsc(r.label_ko || '')} 추이">
            ${th === null ? '' : `
                <line x1="${MM_L}" y1="${sy(th).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(th).toFixed(1)}" class="mm-threshold"/>
                <text x="${MM_W - MM_R}" y="${(sy(th) - 5).toFixed(1)}" class="mm-threshold-tag" text-anchor="end">${finEsc(r.threshold_label_ko || '')}</text>`}
            <path d="${path}" class="mm-ratio-line"/>
            <circle cx="${sx(li).toFixed(1)}" cy="${sy(lv).toFixed(1)}" r="3.5" class="mm-ratio-dot"/>
            <text x="${MM_L}" y="${H - 8}" class="mm-tick">${finEsc(dates[idx[0][0]] || '')}</text>
            <text x="${MM_W - MM_R}" y="${H - 8}" class="mm-tick" text-anchor="end">${finEsc(dates[li] || '')}</text>
        </svg>
        <p class="fin-note">${finEsc(r.threshold_note_ko || '')} ${finEsc(r.gdp_note_ko || '')}</p>
    </div>`;
};

const mmBalanceSheetView = (ind) => {
    const bs = ind.balance_sheet;
    const sides = (bs || {}).sides || [];
    if (!sides.length) return '<p class="fin-note">대차대조표 구성 자료가 없습니다.</p>';

    const dates = bs.dates || [];
    // One scale across both sides: they are equal totals by definition, and
    // separate scales would make one look larger than the other.
    let hi = 0;
    sides.forEach((s) => (s.layers || []).forEach((_, li) => {
        dates.forEach((__, i) => {
            const tot = (s.layers || []).reduce(
                (acc, l) => acc + (Number.isFinite(l.values[i]) ? l.values[i] : 0), 0);
            if (tot > hi) hi = tot;
        });
    }));
    hi *= 1.04;

    return `
    <div class="mm-bs" data-mm-bs-root="1"
         data-dates='${finEsc(JSON.stringify(dates))}'
         data-sides='${finEsc(JSON.stringify(sides.map((s) => ({
             label_ko: s.label_ko,
             layers: (s.layers || []).map((l) => ({ label_ko: l.label_ko, color: l.color, values: l.values })),
         }))))}'>
        ${sides.map((s, k) => mmStackSide(s, dates, hi, k)).join('')}
        <div class="mm-bs-tip" style="display:none"></div>
    </div>
    <p class="fin-note">${finEsc(bs.stack_note_ko || '')} ${finEsc(bs.sampling_note_ko || '')}</p>
    ${bs.ratio ? mmReservesRatio(bs.ratio, dates) : ''}`;
};

// Hovering a stack reads the composition at that week for both sides at once:
// the question "what was it made of then" is never about one side alone, and
// the shares are what the eye cannot recover from band thickness.
const mmWireBalanceHover = (root) => {
    const dates = JSON.parse(root.getAttribute('data-dates') || '[]');
    const sides = JSON.parse(root.getAttribute('data-sides') || '[]');
    const tip = root.querySelector('.mm-bs-tip');
    const panels = Array.from(root.querySelectorAll('.mm-bs-side'));
    if (!tip || !panels.length) return;

    const hide = () => {
        tip.style.display = 'none';
        panels.forEach((p) => {
            const c = p.querySelector('.mm-bs-cross');
            if (c) c.style.display = 'none';
        });
    };

    panels.forEach((panel) => {
        const rows = JSON.parse(panel.getAttribute('data-rows') || '[]');
        const svg = panel.querySelector('svg');
        if (!svg || !rows.length) return;

        svg.addEventListener('mousemove', (ev) => {
            const box = svg.getBoundingClientRect();
            const frac = (ev.clientX - box.left) / box.width;
            const span = (MM_W - MM_L - MM_R) / MM_W;
            const k = Math.round(((frac - MM_L / MM_W) / span) * (rows.length - 1));
            const kk = Math.max(0, Math.min(rows.length - 1, k));
            const i = rows[kk];
            const x = MM_L + (kk / Math.max(rows.length - 1, 1)) * (MM_W - MM_L - MM_R);

            panels.forEach((p) => {
                const c = p.querySelector('.mm-bs-cross');
                if (!c) return;
                c.setAttribute('x1', x); c.setAttribute('x2', x);
                c.style.display = '';
            });

            tip.innerHTML = `
                <div class="mm-bs-tip-date">${finEsc(dates[i] || '')}</div>
                ${sides.map((s) => {
                    const rowsOut = s.layers.map((l) => [l, l.values[i]])
                        .filter(([, v]) => Number.isFinite(v));
                    const tot = rowsOut.reduce((a, [, v]) => a + v, 0);
                    return `
                    <div class="mm-bs-tip-side">
                        <div class="mm-bs-tip-head">${finEsc(s.label_ko)}<b>${mmFmt(tot, 2)}조</b></div>
                        ${rowsOut.slice().reverse().map(([l, v]) => `
                            <div class="mm-bs-tip-row">
                                <i style="background:${finEsc(l.color)}"></i>
                                <span>${finEsc(l.label_ko)}</span>
                                <b>${mmFmt(v, 2)}조</b>
                                <em>${tot ? (v / tot * 100).toFixed(1) : '—'}%</em>
                            </div>`).join('')}
                    </div>`;
                }).join('')}`;

            tip.style.display = '';
            const rootBox = root.getBoundingClientRect();
            const px = ev.clientX - rootBox.left;
            // Flip to the left of the cursor near the right edge so the panel
            // never leaves the drawer.
            tip.style.left = `${px > rootBox.width * 0.55 ? px - tip.offsetWidth - 14 : px + 14}px`;
            tip.style.top = `${Math.max(4, ev.clientY - rootBox.top - 40)}px`;
        });
        svg.addEventListener('mouseleave', hide);
    });
};

// US general elections are on a fixed public schedule (first Tue after first
// Mon in Nov), not something to fetch or estimate -- presidential years are
// divisible by 4, midterms are the even years between. Shaded as the 3 months
// running into the vote, matching how a pre-election cash drawdown would
// actually show up in TGA: a fiscal decision made ahead of it, not on the day.
const mmUsElectionBands = (dates) => {
    if (!dates.length) return [];
    const years = dates.map((d) => Number(String(d).slice(0, 4)));
    const yLo = Math.min(...years), yHi = Math.max(...years);
    const months = [];
    for (let y = yLo - 1; y <= yHi + 1; y++) {
        if (y % 2 !== 0) continue;
        const kind = y % 4 === 0 ? 'president' : 'midterm';
        for (let m = 9; m <= 11; m++) months.push({ ym: `${y}-${String(m).padStart(2, '0')}`, kind });
    }
    const bands = [];
    let cur = null;
    dates.forEach((d, i) => {
        const ym = String(d).slice(0, 7);
        const hit = months.find((m) => m.ym === ym);
        if (hit) {
            if (cur && cur.kind === hit.kind && i === cur.end + 1) cur.end = i;
            else { if (cur) bands.push(cur); cur = { start: i, end: i, kind: hit.kind }; }
        } else if (cur) { bands.push(cur); cur = null; }
    });
    if (cur) bands.push(cur);
    return bands;
};

// Monthly prints (CPI, PCE) are discrete releases, not a continuous level: a
// line between two months implies values in between that were never measured,
// and MoM in particular crosses zero every few months, where a filled line
// reads as one shape instead of alternating months of rises and falls.
const mmBarSeries = (dates, values, opts = {}) => {
    const idx = values.map((v, i) => [i, v]).filter(([, v]) => Number.isFinite(v));
    if (!idx.length) return '<p class="fin-note">그릴 수 있는 시계열이 없습니다.</p>';

    const ys = idx.map(([, y]) => y);
    let lo = Math.min(...ys, 0), hi = Math.max(...ys, 0);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;

    const n = values.length;
    const sx = (i) => MM_L + (i / Math.max(n - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => MM_T + (1 - (v - lo) / (hi - lo)) * (MM_H - MM_T - MM_B);
    const bw = Math.max((MM_W - MM_L - MM_R) / Math.max(n, 1) * 0.72, 1);
    const zero = sy(0);

    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + (hi - lo) * t);
    const xAt = [0, Math.floor((n - 1) / 2), n - 1];

    return `
    <div class="mm-chart-box" data-mm-chart-box="1"
         data-dates='${finEsc(JSON.stringify(dates))}'
         data-values='${finEsc(JSON.stringify(values.map((v) => Number.isFinite(v) ? v : null)))}'
         data-geom='${finEsc(JSON.stringify({ lo, hi, n }))}'
         data-unit="${finEsc(opts.unit || '')}">
        <svg class="mm-chart" viewBox="0 0 ${MM_W} ${MM_H}" preserveAspectRatio="none" role="img"
             aria-label="${finEsc(opts.label || '월별 시계열')} 막대 차트">
            ${ticks.map((t) => `
                <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t)}</text>`).join('')}
            ${idx.map(([i, v]) => {
                const y = sy(v);
                return `<rect class="mm-bar-col${v < 0 ? ' neg' : ''}"
                    x="${(sx(i) - bw / 2).toFixed(1)}" y="${Math.min(y, zero).toFixed(1)}"
                    width="${bw.toFixed(1)}" height="${Math.max(Math.abs(zero - y), 0.6).toFixed(1)}"/>`;
            }).join('')}
            <line x1="${MM_L}" y1="${zero.toFixed(1)}" x2="${MM_W - MM_R}" y2="${zero.toFixed(1)}" class="mm-zero"/>
            ${xAt.map((i) => `<text x="${sx(i).toFixed(1)}" y="${MM_H - 8}" class="mm-tick"
                text-anchor="${i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle')}">${finEsc(dates[i] || '')}</text>`).join('')}
            <line class="mm-cross" x1="0" y1="${MM_T}" x2="0" y2="${MM_H - MM_B}" style="display:none"/>
            <circle class="mm-hover-dot" r="4" style="display:none"/>
        </svg>
        <div class="mm-tip-box" style="display:none"></div>
    </div>`;
};

const mmLineChart = (dates, values, opts = {}) => {
    const idx = values.map((v, i) => [i, v]).filter(([, v]) => Number.isFinite(v));
    if (idx.length < 2) return '<p class="fin-note">그릴 수 있는 시계열이 없습니다.</p>';
    const ma = Array.isArray(opts.ma5) ? opts.ma5 : null;

    const ys = idx.map(([, y]) => y).concat(ma ? ma.filter(Number.isFinite) : []);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    // A series that crosses zero reads wrong without the zero line on the axis.
    if (lo > 0 && lo < (hi - lo) * 0.5) lo = 0;

    const n = values.length;
    const sx = (i) => MM_L + (i / Math.max(n - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => MM_T + (1 - (v - lo) / (hi - lo)) * (MM_H - MM_T - MM_B);

    const path = (arr, loI = 0, hiI = arr.length - 1) => {
        let dstr = '', pen = false;
        for (let i = loI; i <= hiI; i++) {
            const v = arr[i];
            if (!Number.isFinite(v)) { pen = false; continue; }
            dstr += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
            pen = true;
        }
        return dstr;
    };

    const line = path(values);
    const first = idx[0][0], last = idx[idx.length - 1][0];
    const area = `${line}L${sx(last).toFixed(1)},${sy(lo).toFixed(1)}L${sx(first).toFixed(1)},${sy(lo).toFixed(1)}Z`;

    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + (hi - lo) * t);
    const xAt = [0, Math.floor((n - 1) / 2), n - 1];
    const bands = opts.electionBands ? mmUsElectionBands(dates) : [];

    // _pin_latest() (macro_monitor/live_overlay.py) only overwrites the last
    // realFromEnd points; everything before that is fixture_synth wearing the
    // same "live_latest" badge. Drawing it as one uninterrupted line reads as
    // a real trend -- or a real cliff, if the fixture tail happens to sit far
    // from the one real value, which is exactly what on_rrp did. The synthetic
    // run gets its own muted/dashed style and the real tail gets a marker, so
    // the eye doesn't read a drop that never happened.
    const realFromEnd = Number.isInteger(opts.realFromEnd) && opts.realFromEnd > 0 && opts.realFromEnd < n
        ? opts.realFromEnd : null;
    const realStartIdx = realFromEnd ? n - realFromEnd : null;

    return `
    <div class="mm-chart-box" data-mm-chart-box="1"
         data-dates='${finEsc(JSON.stringify(dates))}'
         data-values='${finEsc(JSON.stringify(values.map((v) => Number.isFinite(v) ? v : null)))}'
         ${ma ? `data-ma='${finEsc(JSON.stringify(ma.map((v) => Number.isFinite(v) ? v : null)))}'` : ''}
         data-geom='${finEsc(JSON.stringify({ lo, hi, n }))}'
         data-unit="${finEsc(opts.unit || '')}">
        <svg class="mm-chart" viewBox="0 0 ${MM_W} ${MM_H}" preserveAspectRatio="none" role="img"
             aria-label="${finEsc(opts.label || '시계열')} 차트">
            <defs><linearGradient id="mmg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.26"/>
                <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
            </linearGradient></defs>
            ${bands.map((b) => `<rect x="${sx(b.start).toFixed(1)}" y="${MM_T}"
                width="${(sx(b.end) - sx(b.start) + 1).toFixed(1)}" height="${(MM_H - MM_T - MM_B).toFixed(1)}"
                class="mm-election-band mm-election-${b.kind}"><title>${b.kind === 'president' ? '대통령선거' : '중간선거'} 직전 3개월</title></rect>`).join('')}
            ${ticks.map((t) => `
                <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t)}</text>`).join('')}
            ${(lo < 0 && hi > 0) ? `<line x1="${MM_L}" y1="${sy(0).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(0).toFixed(1)}" class="mm-zero"/>` : ''}
            <path d="${area}" fill="url(#mmg)"/>
            ${ma ? `<path d="${path(ma)}" class="mm-ma"/>` : ''}
            ${realFromEnd ? `
                <path d="${path(values, 0, realStartIdx)}" class="mm-line mm-line-synthetic"/>
                <line x1="${sx(realStartIdx).toFixed(1)}" y1="${MM_T}" x2="${sx(realStartIdx).toFixed(1)}" y2="${MM_H - MM_B}" class="mm-real-divider"/>
                <circle cx="${sx(n - 1).toFixed(1)}" cy="${sy(values[n - 1]).toFixed(1)}" r="4" class="mm-real-point">
                    <title>실측값 (이전 구간은 합성)</title>
                </circle>`
                : `<path d="${line}" class="mm-line"/>`}
            ${xAt.map((i) => `<text x="${sx(i).toFixed(1)}" y="${MM_H - 8}" class="mm-tick"
                text-anchor="${i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle')}">${finEsc(dates[i] || '')}</text>`).join('')}
            <line class="mm-cross" x1="0" y1="${MM_T}" x2="0" y2="${MM_H - MM_B}" style="display:none"/>
            <circle class="mm-hover-dot" r="4" style="display:none"/>
        </svg>
        <div class="mm-tip-box" style="display:none"></div>
        ${ma ? '<p class="mm-legend-note"><i class="mm-swatch-ma"></i>MA5 (5기간 이동평균)</p>' : ''}
        ${bands.length ? `<p class="mm-legend-note">
            <i class="mm-swatch mm-swatch-president"></i>대통령선거 직전 3개월
            <i class="mm-swatch mm-swatch-midterm"></i>중간선거 직전 3개월
        </p>` : ''}
        ${realFromEnd ? `<p class="mm-legend-note mm-legend-warn">
            <i class="mm-swatch mm-swatch-synthetic"></i>회색 구간은 합성 데이터 · 마지막 점(●)만 실측치입니다
        </p>` : ''}
    </div>`;
};

// Grouped bars for a handful of labelled values -- QRA compare, energy mix,
// FedWatch outcomes and maturity buckets all reduce to this shape.
const mmBars = (rows, opts = {}) => {
    const vals = rows.map((r) => Number(r.value)).filter(Number.isFinite);
    if (!vals.length) return '<p class="fin-note">표시할 값이 없습니다.</p>';
    const hi = Math.max(...vals, 0), lo = Math.min(...vals, 0);
    const span = (hi - lo) || 1;
    return `
    <div class="mm-bars ${opts.compact ? 'mm-bars-compact' : ''}">
        ${rows.map((r) => {
            const v = Number(r.value);
            const w = Number.isFinite(v) ? Math.abs(v) / span * 100 : 0;
            return `
            <div class="mm-bar-row${r.highlight ? ' mm-bar-hi' : ''}">
                <span class="mm-bar-label">${finEsc(r.label)}${r.sub ? `<span class="mm-bar-sub">${finEsc(r.sub)}</span>` : ''}</span>
                <span class="mm-bar-track"><span class="mm-bar-fill${v < 0 ? ' mm-bar-neg' : ''}" style="width:${w.toFixed(1)}%"></span></span>
                <span class="mm-bar-value">${finEsc(r.display ?? (mmFmt(v) + (opts.unit || '')))}</span>
            </div>`;
        }).join('')}
    </div>`;
};

// The Treasury's FX report is a three-test rule, and the designation only means
// something once you know which tests a country actually tripped. The published
// pack carries the outcome ("관찰대상") but not the per-test figures, so the
// tests are listed with their thresholds and each is marked 미공개 rather than
// filled with a plausible number.
// Thresholds as of the 2024-06 semiannual report ($20bn / 2% / 2%, verified
// 2026-08-14) -- Treasury has moved these before (the trade-surplus bar was
// $15bn in earlier vintages) and will again, so re-check against the current
// report before trusting this without a date check.
const MM_FX_WATCH_TESTS = [
    { ko: '대미 무역흑자', rule: '200억 달러 이상', key: 'trade_surplus_bn' },
    { ko: '경상수지 흑자', rule: 'GDP 대비 2% 이상', key: 'current_account_pct_gdp' },
    { ko: '일방향 외환개입', rule: '지속적·일방향 순매수 · GDP 대비 2% 이상', key: 'fx_intervention_pct_gdp' },
];

const mmFxWatchView = (ind) => {
    const c = ind.criteria || {};
    const met = MM_FX_WATCH_TESTS.filter((t) => c[t.key] && c[t.key].met === true).length;
    const known = MM_FX_WATCH_TESTS.filter((t) => c[t.key] && typeof c[t.key].met === 'boolean').length;
    return `
    <div class="mm-status-view">
        <div class="mm-status-headline">
            <span class="mm-status-big">${finEsc(ind.display || '—')}</span>
            <span class="mm-status-sub">${known ? `3개 요건 중 ${met}개 충족` : '요건별 충족 여부 미공개'}</span>
        </div>
        <div class="mm-crit-list">
            ${MM_FX_WATCH_TESTS.map((t) => {
                const hit = c[t.key] || {};
                const state = hit.met === true ? 'on' : (hit.met === false ? 'off' : 'unknown');
                const mark = state === 'on' ? '충족' : (state === 'off' ? '미충족' : '미공개');
                return `<div class="mm-crit mm-crit-${state}">
                    <span class="mm-crit-dot" aria-hidden="true"></span>
                    <span class="mm-crit-body">
                        <strong>${finEsc(t.ko)}</strong>
                        <span class="mm-crit-rule">기준 ${finEsc(t.rule)}</span>
                    </span>
                    <span class="mm-crit-mark">${mark}${hit.display ? ` · ${finEsc(hit.display)}` : ''}</span>
                </div>`;
            }).join('')}
        </div>
        <p class="fin-note">
            2개 충족이면 관찰대상, 3개 모두면 심층분석 대상입니다.
            이 스냅샷에는 요건별 수치가 들어 있지 않아 충족 여부를 채우지 않았습니다 — 추정하지 않습니다.
        </p>
    </div>`;
};

const mmRatingView = (ind) => {
    const rows = (ind.components || []).filter((c) => c.rating);
    if (!rows.length) return `<p class="fin-note">${finEsc(ind.display || '—')}</p>`;
    return `
    <div class="mm-status-view">
        <div class="mm-status-headline">
            <span class="mm-status-big">${finEsc(ind.display || '—')}</span>
            <span class="mm-status-sub">3대 평가사 현재 등급</span>
        </div>
        <div class="mm-rating-grid">
            ${rows.map((r) => `
                <div class="mm-rating-cell">
                    <span class="mm-rating-agency">${finEsc(r.label_ko || r.agency || r.id)}</span>
                    <span class="mm-rating-grade">${finEsc(r.rating)}</span>
                    <span class="mm-rating-outlook">${finEsc(r.outlook || '—')}</span>
                </div>`).join('')}
        </div>
        <p class="fin-note">등급은 사건이 있을 때만 바뀝니다. 추세선이 아니라 현재 상태와 전망으로 읽습니다.</p>
    </div>`;
};

const mmStatusView = (ind) => {
    if (ind.id === 'us_fx_watch') return mmFxWatchView(ind);
    if ((ind.components || []).some((c) => c.rating)) return mmRatingView(ind);
    return `
    <div class="mm-status-view">
        <div class="mm-status-headline">
            <span class="mm-status-big">${finEsc(ind.display || '—')}</span>
        </div>
        <p class="fin-note">상태 지표입니다. 시계열 추세로 읽지 않습니다.</p>
    </div>`;
};

// Which items moved most in the latest print. Ranked on each item's own MoM,
// not on its weighted contribution to the headline -- the published artifact
// carries no relative-importance weights, and calling an unweighted mover a
// "contribution" would overstate how much it moved the index.
const mmMoversView = (ind) => {
    const mv = ind.movers || {};
    const row = (r, dir) => `
        <div class="mm-mover mm-mover-${dir}">
            <span class="mm-mover-name">${finEsc(r.label_ko)}</span>
            <span class="mm-mover-mom">${r.mom_pct >= 0 ? '+' : ''}${r.mom_pct.toFixed(2)}%</span>
            <span class="mm-mover-yoy">YoY ${r.yoy_pct === null ? '—' : `${r.yoy_pct >= 0 ? '+' : ''}${r.yoy_pct.toFixed(1)}%`}</span>
        </div>`;
    if (!(mv.up || []).length && !(mv.down || []).length) {
        return `<p class="fin-note">${finEsc('항목별 변동 자료가 없습니다.')}</p>`;
    }
    return `
    <div class="mm-movers">
        <div class="mm-mover-col">
            <h4 class="mm-mover-head">가장 오른 항목</h4>
            ${(mv.up || []).map((r) => row(r, 'up')).join('')}
        </div>
        <div class="mm-mover-col">
            <h4 class="mm-mover-head">가장 내린 항목</h4>
            ${(mv.down || []).map((r) => row(r, 'down')).join('')}
        </div>
    </div>
    <p class="fin-note">${finEsc(mv.reference_period || '')} 발표 기준. ${finEsc(mv.note_ko || '')}</p>`;
};

// Which panels an indicator can show, in the order they should appear. The
// engine names the primary view (ui.click_view); chart_type covers the rest.
const mmViewsFor = (ind) => {
    const views = [];
    const cv = (ind.ui || {}).click_view;
    const has = (a) => Array.isArray(a) && a.length;

    // A rating and a watch-list designation are states, not quantities. Drawing
    // them as a line asks the reader to see a slope in AA -> AA, and the engine
    // even emits change_1m_pct on them (-100% for a rating that never moved).
    // These get their own panel and no history tab.
    if (ind.chart_type === 'status') {
        return [{ id: 'status', label: '상태' }];
    }

    if (cv === 'compare_bar_table' && has((ind.compare || {}).series)) {
        views.push({ id: 'compare', label: '비교' });
    }
    if (cv === 'energy_mix' && has((ind.energy_mix || {}).series)) {
        views.push({ id: 'mix', label: '연료 비중' });
    }
    if (ind.chart_type === 'stack' && has(ind.components)) {
        views.push({ id: 'stack', label: '구성' });
    }
    if (ind.chart_type === 'bar' && has(ind.outcomes)) {
        views.push({ id: 'outcomes', label: '확률' });
    }
    if (has((ind.movers || {}).up) || has((ind.movers || {}).down)) {
        views.push({ id: 'movers', label: '항목별' });
    }
    if (has((ind.balance_sheet || {}).layers)) {
        views.push({ id: 'balance', label: '부채 구성' });
    }
    if (has(((ind.history || {})['5y'] || {}).values) || ind.modes) {
        views.push({ id: 'history', label: '추이' });
    }
    // Secondary panels come last so the engine's primary view stays default.
    const sv = (ind.ui || {}).secondary_view;
    if (sv === 'maturity_components' && has(ind.components)) {
        views.push({ id: 'components', label: '만기별' });
    } else if (has(ind.components) && !views.some((v) => v.id === 'stack')
               && ind.chart_type === 'line+components') {
        views.push({ id: 'components', label: '구성' });
    }
    return views.length ? views : [{ id: 'history', label: '추이' }];
};

// GDP arrives as two series under `modes`; the drawer swaps between them
// rather than showing an annualised figure the engine deliberately dropped.
const mmModeSeries = (ind, mode) => {
    const m = (ind.modes || {})[mode];
    return m || null;
};

const mmCompareView = (ind) => {
    const c = ind.compare || {};
    const rows = (c.series || []).map((s) => ({
        label: s.label_ko,
        sub: s.period,
        value: s.value,
        display: `${mmFmt(s.value, 0)}B`,
        highlight: s.id === 'current',
    }));
    const table = c.table || [];
    return `
        ${c.title_ko ? `<p class="mm-view-title">${finEsc(c.title_ko)}</p>` : ''}
        ${mmBars(rows, { unit: 'B' })}
        ${table.length ? `
        <div class="co-table-wrap mm-table">
            <table class="co-table">
                <thead><tr>
                    <th>구분</th><th>대상 분기</th><th>순발행 ($B)</th><th>기말 현금 ($B)</th><th>공시일</th>
                </tr></thead>
                <tbody>
                    ${table.map((r) => `
                        <tr>
                            <td class="co-label">${finEsc(r.label_ko)}</td>
                            <td>${finEsc(r.period || '—')}</td>
                            <td>${mmFmt(r.net_borrowing_bn, 0)}</td>
                            <td>${mmFmt(r.end_cash_bn, 0)}</td>
                            <td>${finEsc(r.announcement_date || '—')}</td>
                        </tr>`).join('')}
                </tbody>
            </table>
        </div>` : ''}
        ${c.note_ko ? `<p class="fin-note">${finEsc(c.note_ko)}</p>` : ''}`;
};

const mmMixView = (ind) => {
    const em = ind.energy_mix || {};
    const rows = (em.series || []).map((s) => ({
        label: s.label_ko || s.id,
        value: s.value,
        display: `${mmFmt(s.value, 1)}%${Number.isFinite(s.twh) ? ` · ${mmFmt(s.twh, 0)}TWh` : ''}`,
    }));
    return `
        <p class="mm-view-title">연료별 발전 비중${em.asof_year ? ` · ${em.asof_year}년` : ''}</p>
        ${mmBars(rows, { unit: '%' })}
        <p class="fin-note">발전량 기준 비중입니다. 설비용량이 아니라 실제로 만들어낸 전력의 몫입니다.</p>`;
};

const mmComponentsView = (ind, title) => mmBars(
    (ind.components || []).map((c) => ({
        label: c.label_ko || c.id,
        value: c.value,
        display: c.display ?? (mmFmt(c.value, 0) + (c.unit === 'pct' ? '%' : '')),
    })), {}) + (title ? `<p class="fin-note">${finEsc(title)}</p>` : '');

const mmOutcomesView = (ind) => {
    const rows = (ind.outcomes || []).map((o) => ({
        label: o.label_ko,
        value: o.prob,
        display: `${mmFmt(o.prob, 0)}%`,
        highlight: o.prob === Math.max(...ind.outcomes.map((x) => x.prob)),
    }));
    return `
        <p class="mm-view-title">회의 결과별 시장 내재 확률</p>
        ${mmBars(rows, { unit: '%' })}
        <p class="fin-note">선물 가격에서 역산한 확률입니다. 예측이 아니라 시장이 지금 무엇에 값을 매기고 있는지입니다.</p>`;
};

const mmChartDrawer = () => {
    if (!MM_CHART || !MM_COUNTRY) return '';
    const ind = (MM_COUNTRY.country.indicators || []).find((x) => x.id === MM_CHART.indicatorId);
    if (!ind) return '';

    const views = mmViewsFor(ind);
    const view = views.some((v) => v.id === MM_CHART.view) ? MM_CHART.view : views[0].id;
    MM_CHART.view = view;

    const dual = (ind.ui || {}).dual;
    const mode = MM_CHART.mode || (ind.ui || {}).default || (dual ? dual[0] : null);
    const modeSeries = dual ? mmModeSeries(ind, mode) : null;

    let body = '';
    if (view === 'balance') body = mmBalanceSheetView(ind);
    else if (view === 'movers') body = mmMoversView(ind);
    else if (view === 'status') body = mmStatusView(ind);
    else if (view === 'compare') body = mmCompareView(ind);
    else if (view === 'mix') body = mmMixView(ind);
    else if (view === 'outcomes') body = mmOutcomesView(ind);
    else if (view === 'stack') body = mmComponentsView(ind, '연준이 보유한 국채를 잔존만기로 나눈 잔액입니다. 시장금리가 아니라 대차대조표입니다.');
    else if (view === 'components') body = mmComponentsView(ind, ind.chart_type === 'line+components' ? '' : '만기별 발행 구성입니다.');
    else {
        const src = modeSeries || ind;
        const hist = (src.history || {})[MM_CHART.window] || {};
        if (ind.chart_type === 'bar') {
            body = mmBarSeries(hist.dates || [], hist.values || [], {
                unit: src.unit === 'pct' ? '%' : (src.unit || ''),
                label: src.label_ko || ind.label_ko,
            });
        } else
        // VIX and other fear gauges have no moving average by design: a smoothed
        // fear index invites reading a trend into what is meant to be a level.
        body = mmLineChart(hist.dates || [], hist.values || [], {
            ma5: hist.ma5,
            unit: src.unit === 'pct' ? '%' : (src.unit || ''),
            label: src.label_ko || ind.label_ko,
            electionBands: ind.id === 'tga',
            realFromEnd: hist.real_points_from_end,
        });
    }

    const meta = [
        ind.display != null ? String(ind.display) : null,
        ind.asof ? `기준 ${ind.asof}` : null,
        ind.source ? (typeof ind.source === 'string' ? ind.source : ind.source.name) : null,
        ind.refresh_tier || null,
    ].filter(Boolean);

    const showWindow = view === 'history';

    return `
    <div class="mm-drawer" role="dialog" aria-label="${finEsc(ind.label_ko)}">
        <div class="mm-drawer-head">
            <div>
                <h3>${finEsc(ind.label_ko)} ${mmStatusBadge(ind.data_status)}</h3>
                <p class="mm-drawer-sub">${meta.map((m) => finEsc(m)).join(' · ')}</p>
            </div>
            <div class="mm-drawer-actions">
                ${dual ? `<div class="pf-mode">
                    ${dual.map((m) => `<button type="button" class="pf-mode-btn ${m === mode ? 'on' : ''}"
                        data-mm-mode="${finEsc(m)}">${finEsc(((ind.modes || {})[m] || {}).label_ko || m.toUpperCase())}</button>`).join('')}
                </div>` : ''}
                ${showWindow ? `<div class="pf-mode">
                    ${['5y', '10y'].map((w) => `<button type="button" class="pf-mode-btn ${MM_CHART.window === w ? 'on' : ''}"
                        data-mm-window="${w}">${w === '5y' ? '5년' : '10년'}</button>`).join('')}
                </div>` : ''}
                <button class="mm-close" data-mm-chart-close="1" aria-label="닫기">✕</button>
            </div>
        </div>

        ${views.length > 1 ? `<div class="mm-views">
            ${views.map((v) => `<button class="mm-view-btn ${v.id === view ? 'on' : ''}"
                data-mm-view="${finEsc(v.id)}">${finEsc(v.label)}</button>`).join('')}
        </div>` : ''}

        <div class="mm-drawer-body">
            <div class="mm-drawer-main">
                ${body}
                ${mmNoteWithState(ind) ? `<p class="fin-note mm-note">${finEsc(mmNoteWithState(ind))}</p>` : ''}
                ${ind.reference ? `<p class="fin-note">${finEsc(typeof ind.reference === 'string' ? ind.reference : JSON.stringify(ind.reference))}</p>` : ''}
            </div>
            ${mmNewsRail(ind)}
        </div>
    </div>`;
};

// The news API is not wired yet. An empty rail that says so is honest; a
// spinner that never resolves is not, and fabricated articles would be worse.
const mmNewsRail = (ind) => {
    const items = Array.isArray(ind.news) ? ind.news : null;
    return `
    <aside class="mm-news">
        <p class="mm-news-head">관련 뉴스</p>
        ${items && items.length ? items.map((it) => `
            <a class="mm-news-item" href="${finEsc(it.url)}" target="_blank" rel="noopener noreferrer">
                <span class="mm-news-title">${finEsc(it.title)}</span>
                <span class="mm-news-meta">${finEsc(it.source || '')}${it.published_at ? ` · ${finEsc(String(it.published_at).slice(0, 10))}` : ''}</span>
            </a>`).join('')
        : `<p class="mm-news-empty">관련 뉴스 없음 · API 연결 대기</p>
           ${ind.news_query ? `<p class="mm-news-q">검색어: <code>${finEsc(ind.news_query)}</code></p>` : ''}`}
        <p class="mm-news-foot">투자 권유 아님 · 뉴스 요약은 참고용</p>
    </aside>`;
};

// Central bank head + finance minister only. Financial-supervision chiefs are
// deliberately left out, and Korea's slot is the finance ministry rather than
// the budget office or the financial regulator. China names two people per
// institution -- party secretary and governor/minister -- with separate
// appointment dates even when it is the same person.
const mmPerson = (p) => `${finEsc(p.title_ko || '')} <strong>${finEsc(p.name_ko || '')}</strong>`
    + (p.appointed ? `<span class="mm-off-date">${finEsc(p.appointed)} 임명</span>` : '');

const mmOfficialSlot = (slot) => {
    if (!slot) return '';
    const people = Array.isArray(slot.set) ? slot.set : [slot];
    return `
    <div class="mm-official">
        <span class="mm-off-inst">${finEsc(slot.institution_ko || '')}</span>
        ${people.map((p) => `<span class="mm-off-person">${mmPerson(p)}</span>`).join('')}
    </div>`;
};

const mmOfficials = (off) => {
    if (!off || (!off.central_bank && !off.finance)) return '';
    return `
    <div class="mm-officials">
        ${mmOfficialSlot(off.central_bank)}
        ${mmOfficialSlot(off.finance)}
        ${off.asof ? `<span class="mm-off-asof">${finEsc(off.asof)} 기준</span>` : ''}
    </div>`;
};

const mmOverlay = () => {
    if (!MM_COUNTRY) return '';
    const c = MM_COUNTRY.country;
    const tabs = (MM_INDEX.ui && MM_INDEX.ui.category_tabs) || [];
    const active = (c.active_categories || []).includes(MM_TAB) ? MM_TAB
        : (c.active_categories || [])[0] || 'liquidity';
    MM_TAB = active;
    const chips = (c.categories || {})[active] || [];
    const tabMeta = tabs.find((t) => t.id === active) || {};
    const lim = c.limitations || {};

    return `
    <div class="mm-overlay" role="dialog" aria-label="${finEsc(c.name_ko)} 매크로">
        <div class="mm-head">
            <div class="mm-title">
                <h2>${finEsc(c.name_ko)}
                    ${c.benchmark ? '<span class="mm-badge">벤치마크</span>' : ''}</h2>
                <p>${finEsc(c.name_en || '')} · 기준 ${finEsc(c.asof || '')} · 키트 <code>${finEsc(c.kit || '')}</code></p>
                ${mmOfficials(c.officials)}
            </div>
            <button class="mm-close" data-mm-close="1" aria-label="닫기">✕</button>
        </div>

        ${(c.headlines || []).length ? `
        <div class="mm-headlines">
            ${c.headlines.map((h) => `
                <button class="mm-headline" data-mm-tab="${finEsc(h.category)}"
                        title="${finEsc(mmStatus(h.data_status).label)}">
                    <span class="mm-headline-label">
                        <i class="mm-headline-dot mm-data-status-${mmStatus(h.data_status).cls}"></i>${finEsc(h.label_ko)}
                    </span>
                    <span class="mm-headline-value">${finEsc(h.display ?? '—')}</span>
                </button>`).join('')}
        </div>` : ''}

        <div class="mm-tabs" role="tablist">
            ${tabs.map((t) => {
                const on = t.id === active;
                const has = (c.active_categories || []).includes(t.id);
                return `<button class="mm-tab ${on ? 'on' : ''}" data-mm-tab="${finEsc(t.id)}"
                        ${has ? '' : 'disabled'} role="tab">${finEsc(t.label_ko)}</button>`;
            }).join('')}
        </div>
        ${tabMeta.description_ko ? `<p class="mm-tab-desc">${finEsc(tabMeta.description_ko)}</p>` : ''}

        <div class="mm-chips">
            ${chips.length ? chips.map((ch) => `
                <button class="mm-chip" data-mm-chip="${finEsc(ch.id)}">
                    <span class="mm-chip-head">
                        <span class="mm-chip-label">${finEsc(ch.label_ko)}</span>
                        ${mmStatusBadge(ch.data_status)}
                    </span>
                    ${ch.modes ? mmPrintPair(ch)
                        : `<span class="mm-chip-value">${finEsc(ch.display ?? '—')}</span>`}
                    ${ch.chart_type === 'status' ? '' : `
                        <span class="mm-chip-foot">
                            ${mmDelta(ch.change_1m_pct)}<span class="mm-chip-win">1M</span>
                            ${mmDelta(ch.change_1y_pct)}<span class="mm-chip-win">1Y</span>
                        </span>
                    `}
                    ${mmNoteWithState(ch) ? `<span class="mm-chip-note">${finEsc(mmNoteWithState(ch))}</span>` : ''}
                </button>`).join('')
              : '<p class="fin-note">이 항목은 이 국가에서 아직 제공되지 않습니다.</p>'}
        </div>

        ${mmChartDrawer()}

        ${(lim.items || []).length ? `
        <details class="mm-limits">
            <summary>${finEsc(lim.title_ko || '해석의 한계')}</summary>
            ${lim.items.map((it) => `
                <div class="mm-limit">
                    <strong>${finEsc(it.title_ko)}</strong>
                    <p>${finEsc(it.body_ko)}</p>
                </div>`).join('')}
        </details>` : ''}

        <p class="mm-disclaimer">${finEsc(MM_COUNTRY.disclaimer_ko || MM_INDEX.disclaimer_ko || '')}</p>
    </div>`;
};

// Re-run after every paint: mmPaint replaces innerHTML, so listeners attached
// to the previous SVG are gone with it.
const mmWireCharts = (host) => {
    host.querySelectorAll('[data-mm-bs-root]').forEach(mmWireBalanceHover);
    host.querySelectorAll('[data-mm-chart-box]').forEach((box) => {
        const svg = box.querySelector('svg');
        const cross = box.querySelector('.mm-cross');
        const dot = box.querySelector('.mm-hover-dot');
        const tip = box.querySelector('.mm-tip-box');
        if (!svg || !cross || !dot || !tip) return;

        let dates, values, ma, geom, unit;
        try {
            dates = JSON.parse(box.dataset.dates);
            values = JSON.parse(box.dataset.values);
            ma = box.dataset.ma ? JSON.parse(box.dataset.ma) : null;
            geom = JSON.parse(box.dataset.geom);
            unit = box.dataset.unit || '';
        } catch (_) { return; }

        const hide = () => {
            cross.style.display = 'none';
            dot.style.display = 'none';
            tip.style.display = 'none';
        };

        svg.addEventListener('mousemove', (e) => {
            const r = svg.getBoundingClientRect();
            if (!r.width) return;
            // Pointer is in CSS pixels; the chart is drawn in viewBox units.
            const vx = (e.clientX - r.left) / r.width * MM_W;
            const t = (vx - MM_L) / (MM_W - MM_L - MM_R);
            let i = Math.round(t * (geom.n - 1));
            i = Math.max(0, Math.min(geom.n - 1, i));
            if (!Number.isFinite(values[i])) { hide(); return; }

            const px = MM_L + (i / Math.max(geom.n - 1, 1)) * (MM_W - MM_L - MM_R);
            const py = MM_T + (1 - (values[i] - geom.lo) / (geom.hi - geom.lo)) * (MM_H - MM_T - MM_B);
            cross.setAttribute('x1', px); cross.setAttribute('x2', px);
            cross.style.display = '';
            dot.setAttribute('cx', px); dot.setAttribute('cy', py);
            dot.style.display = '';

            const maTxt = (ma && Number.isFinite(ma[i])) ? `<span class="mm-tip-ma">MA5 ${mmFmt(ma[i])}${unit}</span>` : '';
            tip.innerHTML = `<span class="mm-tip-date">${finEsc(dates[i] || '')}</span>`
                + `<span class="mm-tip-val">${mmFmt(values[i])}${unit}</span>${maTxt}`;
            tip.style.display = '';
            // Flip before the tooltip would run off the right edge.
            const leftPct = px / MM_W * 100;
            tip.style.left = `${Math.min(Math.max(leftPct, 4), 78)}%`;
        });
        svg.addEventListener('mouseleave', hide);
    });
};

const mmPaint = () => {
    const host = document.getElementById('macro-layer');
    if (!host) return;
    host.innerHTML = MM_COUNTRY ? mmOverlay() : `
        <div class="mm-hint">
            <span class="mm-hint-dot"></span>
            국가를 클릭하세요 · <strong>미국</strong>은 벤치마크입니다
            <span class="mm-hint-count">${(MM_INDEX?.countries_index || []).length}개국</span>
        </div>`;
    host.classList.toggle('mm-open', !!MM_COUNTRY);
    mmWireCharts(host);
};

const mmOpenCountry = async (iso3) => {
    const host = document.getElementById('macro-layer');
    if (host) {
        host.innerHTML = `<div class="mm-overlay"><p class="fin-loading">${finEsc(iso3)} 지표를 받는 중…</p></div>`;
        host.classList.add('mm-open');
    }
    try {
        MM_COUNTRY = await mmFetch(iso3);
        MM_TAB = (MM_COUNTRY.country.active_categories || ['liquidity'])[0];
        MM_CHART = null;
    } catch (err) {
        if (host) host.innerHTML = `<div class="mm-overlay"><p class="fin-p">${finEsc(err.message)}</p>
            <button class="mm-close" data-mm-close="1">✕</button></div>`;
        return;
    }
    mmPaint();
};

const mmDrawMap = () => {
    const rows = (MM_INDEX?.countries_index || []).filter((c) => c.coords);
    deckgl.setProps({
        views: [new MapView({ id: 'map', controller: true, repeat: true })],
        viewState: currentViewState,
        controller: { dragRotate: false, touchRotate: false },
        onHover: null,
        getTooltip: ({ object }) => object && object.name_ko
            ? { html: `<div class="mm-tip">${finEsc(object.name_ko)}${object.benchmark ? ' · 벤치마크' : ''}</div>` }
            : null,
        onClick: ({ object }) => { if (object && object.iso3) mmOpenCountry(object.iso3); },
        layers: [
            ...worldBaseLayers({ id: 'macro' }),
            new ScatterplotLayer({
                id: 'macro-pins',
                data: rows,
                pickable: true,
                stroked: true,
                filled: true,
                opacity: 0.9,
                radiusMinPixels: 9,
                radiusMaxPixels: 26,
                lineWidthMinPixels: 2,
                getPosition: (d) => [d.coords.lon, d.coords.lat],
                // The benchmark is the one everything else is read against, so
                // it is the only marker that differs.
                getRadius: (d) => d.benchmark ? 220000 : 150000,
                getFillColor: (d) => d.benchmark ? [56, 189, 248, 230] : [148, 163, 184, 200],
                getLineColor: (d) => d.benchmark ? [255, 255, 255, 230] : [255, 255, 255, 120],
                autoHighlight: true,
                highlightColor: [125, 211, 252, 220],
            }),
        ],
    });
};

const renderMacroMonitor = async () => {
    currentCommodity = 'macro_monitor';
    stopTradeAnim();
    stopRotation();
    document.body.classList.remove('trade-map-mode', 'shipping-mode', 'finance-mode');
    document.body.classList.add('macro-mode');
    togglePanels({ left: false, right: false, chart: false, map: true });
    if (mapContainer) {
        mapContainer.style.display = 'block';
        mapContainer.style.pointerEvents = 'auto';
    }

    let host = document.getElementById('macro-layer');
    if (!host) {
        host = document.createElement('div');
        host.id = 'macro-layer';
        (mapContainer || document.body).appendChild(host);
        host.addEventListener('click', (e) => {
            const t = e.target instanceof Element ? e.target : null;
            if (!t) return;
            if (t.closest('[data-mm-close]')) { MM_COUNTRY = null; MM_CHART = null; mmPaint(); return; }
            if (t.closest('[data-mm-chart-close]')) { MM_CHART = null; mmPaint(); return; }
            const tab = t.closest('[data-mm-tab]');
            if (tab) { MM_TAB = tab.getAttribute('data-mm-tab'); MM_CHART = null; mmPaint(); return; }
            const chip = t.closest('[data-mm-chip]');
            if (chip) {
                const id = chip.getAttribute('data-mm-chip');
                MM_CHART = (MM_CHART && MM_CHART.indicatorId === id)
                    ? null : { indicatorId: id, window: '5y', view: null, mode: null };
                mmPaint();
                return;
            }
            const win = t.closest('[data-mm-window]');
            if (win && MM_CHART) { MM_CHART.window = win.getAttribute('data-mm-window'); mmPaint(); return; }
            const vw = t.closest('[data-mm-view]');
            if (vw && MM_CHART) { MM_CHART.view = vw.getAttribute('data-mm-view'); mmPaint(); return; }
            const md = t.closest('[data-mm-mode]');
            if (md && MM_CHART) { MM_CHART.mode = md.getAttribute('data-mm-mode'); mmPaint(); return; }
        });
    }

    currentViewState = clampGlobeView({ ...currentViewState, zoom: GLOBE_ZOOM });

    if (!MM_INDEX) {
        host.innerHTML = `<div class="mm-hint">매크로 지표를 받는 중…</div>`;
        try {
            MM_INDEX = await mmFetch(null);
        } catch (err) {
            host.innerHTML = `<div class="mm-hint mm-hint-warn">${finEsc(err.message)}</div>`;
            return;
        }
    }
    MM_COUNTRY = null;
    MM_CHART = null;
    mmDrawMap();
    mmPaint();
};
