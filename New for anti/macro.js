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
let MM_CPI_STRUCTURE = null;    // U.S. CPI relationship map/snapshot, loaded on demand
let MM_CPI_STRUCTURE_PROMISE = null;
let MM_CPI_STRUCTURE_ERROR = '';
let MM_QUALITY_PROMISE = null;  // U.S. official-document layer; loaded only for USA

const mmFetch = async (iso3) => {
    const q = iso3 ? `?country=${encodeURIComponent(iso3)}` : '';
    const res = await fetch(`/api/macro-monitor${q}`);
    if (!res.ok) throw new Error(`매크로 데이터를 못 받았습니다 (${res.status})`);
    return res.json();
};

// us_macro_quality_v1.json is built from point-in-time official-release
// extracts (build_us_macro_quality.py), not the FRED/Yahoo overlay the rest
// of the country pack uses -- fetched as its own static asset rather than
// folded into /api/macro-monitor, which has no notion of this document layer.
const mmQualityFetch = async () => {
    if (!MM_QUALITY_PROMISE) {
        MM_QUALITY_PROMISE = fetch('/public/data/us_macro_quality_v1.json', { cache: 'no-cache' })
            .then((res) => {
                if (!res.ok) throw new Error(`정책 문서 데이터를 못 받았습니다 (${res.status})`);
                return res.json();
            });
    }
    return MM_QUALITY_PROMISE;
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

// Assets and liabilities as two separate blocks -- separate tabs, separate
// scroll position, separate scale -- rather than one panel with both stacks
// glued together. Each still scales to its own max rather than a shared one:
// once they are no longer side by side for a visual "same total" check, a
// shared scale only wastes vertical room in whichever block has the smaller
// swing across the window.
const mmBalanceSideBlock = (side, dates) => {
    let hi = 0;
    dates.forEach((_, i) => {
        const tot = (side.layers || []).reduce(
            (acc, l) => acc + (Number.isFinite(l.values[i]) ? l.values[i] : 0), 0);
        if (tot > hi) hi = tot;
    });
    hi *= 1.04;

    return `
    <div class="mm-bs mm-bs-solo" data-mm-bs-root="1"
         data-dates='${finEsc(JSON.stringify(dates))}'
         data-side='${finEsc(JSON.stringify({
             label_ko: side.label_ko,
             layers: (side.layers || []).map((l) => ({ label_ko: l.label_ko, color: l.color, values: l.values })),
         }))}'>
        ${mmStackSide(side, dates, hi, 0)}
        <div class="mm-bs-tip" style="display:none"></div>
    </div>`;
};

const mmBalanceAssetsView = (ind) => {
    const bs = ind.balance_sheet;
    const side = ((bs || {}).sides || []).find((s) => s.id === 'assets');
    if (!side) return '<p class="fin-note">자산 구성 자료가 없습니다.</p>';
    return `
    ${mmBalanceSideBlock(side, bs.dates || [])}
    <p class="fin-note">${finEsc(bs.stack_note_ko || '')} ${finEsc(bs.sampling_note_ko || '')}</p>`;
};

// The reserves/GDP ratio used to repeat here as a full chart under the stack
// AND as a mini spark in the rail (mmReservesRatioRail) -- the same number
// twice on one screen. The rail already carries it, so the tab body stays to
// just the stack.
const mmBalanceLiabilitiesView = (ind) => {
    const bs = ind.balance_sheet;
    const side = ((bs || {}).sides || []).find((s) => s.id === 'liabilities');
    if (!side) return '<p class="fin-note">부채 구성 자료가 없습니다.</p>';
    return `
    ${mmBalanceSideBlock(side, bs.dates || [])}
    <p class="fin-note">${finEsc(bs.stack_note_ko || '')} ${finEsc(bs.sampling_note_ko || '')}</p>`;
};

// Hovering a stack reads that block's own composition at the hovered week --
// each block is a separate tab now, so there is never a second stack visible
// to pair it with.
const mmWireBalanceHover = (root) => {
    const dates = JSON.parse(root.getAttribute('data-dates') || '[]');
    const side = JSON.parse(root.getAttribute('data-side') || 'null');
    const tip = root.querySelector('.mm-bs-tip');
    const panel = root.querySelector('.mm-bs-side');
    if (!tip || !panel || !side) return;

    const rows = JSON.parse(panel.getAttribute('data-rows') || '[]');
    const svg = panel.querySelector('svg');
    if (!svg || !rows.length) return;

    const cross = panel.querySelector('.mm-bs-cross');
    const hide = () => {
        tip.style.display = 'none';
        if (cross) cross.style.display = 'none';
    };

    svg.addEventListener('mousemove', (ev) => {
        const box = svg.getBoundingClientRect();
        const frac = (ev.clientX - box.left) / box.width;
        const span = (MM_W - MM_L - MM_R) / MM_W;
        const k = Math.round(((frac - MM_L / MM_W) / span) * (rows.length - 1));
        const kk = Math.max(0, Math.min(rows.length - 1, k));
        const i = rows[kk];
        const x = MM_L + (kk / Math.max(rows.length - 1, 1)) * (MM_W - MM_L - MM_R);

        if (cross) { cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.display = ''; }

        const rowsOut = side.layers.map((l) => [l, l.values[i]]).filter(([, v]) => Number.isFinite(v));
        const tot = rowsOut.reduce((a, [, v]) => a + v, 0);
        tip.innerHTML = `
            <div class="mm-bs-tip-date">${finEsc(dates[i] || '')}</div>
            <div class="mm-bs-tip-side">
                <div class="mm-bs-tip-head">${finEsc(side.label_ko)}<b>${mmFmt(tot, 2)}조</b></div>
                ${rowsOut.slice().reverse().map(([l, v]) => `
                    <div class="mm-bs-tip-row">
                        <i style="background:${finEsc(l.color)}"></i>
                        <span>${finEsc(l.label_ko)}</span>
                        <b>${mmFmt(v, 2)}조</b>
                        <em>${tot ? (v / tot * 100).toFixed(1) : '—'}%</em>
                    </div>`).join('')}
            </div>`;

        tip.style.display = '';
        const rootBox = root.getBoundingClientRect();
        const px = ev.clientX - rootBox.left;
        tip.style.left = `${px > rootBox.width * 0.55 ? px - tip.offsetWidth - 14 : px + 14}px`;
        tip.style.top = `${Math.max(4, ev.clientY - rootBox.top - 40)}px`;
    });
    svg.addEventListener('mouseleave', hide);
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

// Monthly Fed purchases/runoff, Treasuries and MBS as two diverging bar
// series sharing a zero line: above is net buying (QE-style), below is net
// runoff (QT-style), for 280+ months back through QE1 -- the sign already
// carries what "QE" or "QT" would have labelled, without this repo curating
// a policy-era calendar it doesn't have and would otherwise be guessing at.
const MM_QQ_H = 220, MM_QQ_T = 12, MM_QQ_B = 24;

// A percentile of a plain array, index-based (no interpolation -- fine at
// this sample size and this is a display cap, not a statistic reported
// anywhere).
const mmPct = (sortedArr, q) => sortedArr[Math.min(sortedArr.length - 1, Math.floor(sortedArr.length * q))];

const mmQeQtBars = (qq, window) => {
    const allRows = qq.rows || [];
    if (!allRows.length) return '<p class="fin-note">매입·런오프 시계열이 없습니다.</p>';

    const years = window === '20y' ? 20 : 5;
    const cutoff = allRows[allRows.length - 1].month.slice(0, 4) - years;
    const rows = allRows.filter((r) => Number(r.month.slice(0, 4)) > cutoff);
    const n = rows.length;

    // COVID's two emergency months are ~5-10x every other month on record;
    // scaling the axis to fit them would flatten every ordinary QE/QT month
    // into a hairline. Cap is computed from whatever window is on screen
    // (not a fixed COVID date) so it adapts if the window changes or new
    // months arrive -- a bar past the cap is drawn clipped, marked with a
    // break, and labelled with its real value rather than hidden.
    const magnitudes = rows.flatMap((r) => [Math.abs(r.treasuries_bn), Math.abs(r.mbs_bn)])
        .filter(Number.isFinite).sort((a, b) => a - b);
    const cap = magnitudes.length ? mmPct(magnitudes, 0.95) * 2.2 : 0;
    const hasBreak = magnitudes.length && magnitudes[magnitudes.length - 1] > cap;

    const clamp = (v) => Math.max(-cap, Math.min(cap, v));
    const allVals = rows.flatMap((r) => [clamp(r.treasuries_bn), clamp(r.mbs_bn)]).filter(Number.isFinite);
    let lo = Math.min(0, ...allVals), hi = Math.max(0, ...allVals);
    const pad = (hi - lo || 1) * 0.1;
    lo -= pad; hi += pad;

    const sx = (i) => MM_L + (i / Math.max(n - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => MM_QQ_T + (1 - (v - lo) / (hi - lo)) * (MM_QQ_H - MM_QQ_T - MM_QQ_B);
    const zero = sy(0);
    const colW = (MM_W - MM_L - MM_R) / n;
    const bw = Math.max(colW * 0.42, 0.6);

    // A short zigzag at the clipped edge -- the standard "broken axis" mark
    // -- plus the real value written past it, so clipping a bar never hides
    // its number, only its height.
    const breakMark = (x, y, up) => {
        const s = 3.2, dir = up ? -1 : 1;
        const pts = [[x - bw / 2 - 1, y], [x - bw / 4, y + dir * s], [x, y - dir * s],
                     [x + bw / 4, y + dir * s], [x + bw / 2 + 1, y]];
        return `<polyline points="${pts.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(' ')}" class="mm-qq-break"/>`;
    };

    const bar = (i, v, dx, cls) => {
        if (!Number.isFinite(v) || v === 0) return '';
        const clipped = Math.abs(v) > cap;
        const drawV = clamp(v);
        const y = sy(drawV);
        const x = sx(i) + dx;
        const rect = `<rect class="${cls}${clipped ? ' mm-qq-clipped' : ''}" x="${(x - bw / 2).toFixed(2)}" y="${Math.min(y, zero).toFixed(1)}"
            width="${bw.toFixed(2)}" height="${Math.max(Math.abs(zero - y), 0.5).toFixed(1)}"/>`;
        if (!clipped) return rect;
        return rect + breakMark(x, y, v > 0)
            + `<text x="${x.toFixed(1)}" y="${(v > 0 ? y - 5 : y + 11).toFixed(1)}" class="mm-qq-clip-label"
                text-anchor="middle">${v > 0 ? '+' : ''}${v.toFixed(0)}B</text>`;
    };

    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + (hi - lo) * t);
    const yearTicks = [];
    let lastYear = null;
    const yearStep = years > 10 ? 2 : 1;
    rows.forEach((r, i) => {
        const y = r.month.slice(0, 4);
        if (y !== lastYear && Number(y) % yearStep === 0) { yearTicks.push({ i, y }); lastYear = y; }
        else if (y !== lastYear) lastYear = y;
    });

    return `
    <div class="mm-chart-box mm-qq-box" data-mm-qeqt-root="1"
         data-rows='${finEsc(JSON.stringify(rows))}'>
        <svg class="mm-chart mm-qq-chart" viewBox="0 0 ${MM_W} ${MM_QQ_H}" preserveAspectRatio="none" role="img"
             aria-label="연준 국채·MBS 월별 매입·런오프">
            ${ticks.map((t) => `
                <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t, 0)}</text>`).join('')}
            ${rows.map((r, i) => bar(i, r.treasuries_bn, -bw * 0.55, 'mm-qq-bar mm-qq-treas')
                + bar(i, r.mbs_bn, bw * 0.55, 'mm-qq-bar mm-qq-mbs')).join('')}
            <line x1="${MM_L}" y1="${zero.toFixed(1)}" x2="${MM_W - MM_R}" y2="${zero.toFixed(1)}" class="mm-zero"/>
            ${yearTicks.map((t) => `<text x="${sx(t.i).toFixed(1)}" y="${MM_QQ_H - 8}" class="mm-tick" text-anchor="middle">${t.y}</text>`).join('')}
            <line class="mm-cross mm-qq-cross" x1="0" y1="${MM_QQ_T}" x2="0" y2="${MM_QQ_H - MM_QQ_B}" style="display:none"/>
        </svg>
        <div class="mm-qq-legend">
            <span><i class="mm-qq-swatch mm-qq-treas"></i>국채</span>
            <span><i class="mm-qq-swatch mm-qq-mbs"></i>MBS</span>
            <span class="mm-qq-legend-note">위 = 순매입 · 아래 = 런오프(만기상환 후 미재투자)${hasBreak ? ' · ⌇ 표시는 축을 벗어난 값(실제값 표기)' : ''}</span>
        </div>
    </div>`;
};

// Treasury buckets share their colors with the assets stack's own SOMA
// bands (mmBalanceStack); MBS gets its own shades off the same purple the
// assets stack already uses for MBS as a whole, so a reader who has seen
// that chart recognizes the palette here.
const MM_QQ_BUCKET_META = {
    treasuries: {
        le_1y: { label: '국채 ≤1년', color: '#38bdf8' },
        '1_5y': { label: '국채 1–5년', color: '#0ea5e9' },
        '5_10y': { label: '국채 5–10년', color: '#0369a1' },
        gt_10y: { label: '국채 >10년', color: '#0c4a6e' },
    },
    mbs: {
        '30yr': { label: 'MBS 30년물', color: '#8b5cf6' },
        '15yr': { label: 'MBS 15년물', color: '#a78bfa' },
        other: { label: 'MBS 기타', color: '#c4b5fd' },
    },
};

// Slice size is each bucket's share of gross activity (sum of magnitudes) --
// a pie can't show a bucket buying while another runs off in the same wedge
// set, so sign lives in the label/legend instead, and the wedge only ever
// answers "how much of this month's total activity was in this bucket."
const mmQeQtPie = (buckets) => {
    const rows = [];
    for (const product of ['treasuries', 'mbs']) {
        const vals = buckets[product] || {};
        for (const [bid, v] of Object.entries(vals)) {
            if (!Number.isFinite(v) || v === 0) continue;
            const meta = (MM_QQ_BUCKET_META[product] || {})[bid];
            if (!meta) continue;
            rows.push({ ...meta, value: v });
        }
    }
    if (!rows.length) return { svg: '', rows: [] };

    const total = rows.reduce((a, r) => a + Math.abs(r.value), 0);
    const R = 46, CX = 52, CY = 52;
    let angle = -Math.PI / 2;
    const arcs = rows.map((r) => {
        const frac = Math.abs(r.value) / total;
        const a0 = angle;
        angle += frac * Math.PI * 2;
        const a1 = angle;
        const large = (a1 - a0) > Math.PI ? 1 : 0;
        const x0 = CX + R * Math.cos(a0), y0 = CY + R * Math.sin(a0);
        const x1 = CX + R * Math.cos(a1), y1 = CY + R * Math.sin(a1);
        // A single-bucket month (frac ~1) draws as a degenerate arc back to
        // its own start point -- drawn as a full circle instead so one active
        // bucket doesn't render as an invisible sliver.
        if (frac > 0.9995) {
            return `<circle cx="${CX}" cy="${CY}" r="${R}" fill="${finEsc(r.color)}"/>`;
        }
        return `<path d="M${CX},${CY} L${x0.toFixed(2)},${y0.toFixed(2)} A${R},${R} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)} Z" fill="${finEsc(r.color)}"/>`;
    }).join('');

    return {
        svg: `<svg class="mm-qq-pie" viewBox="0 0 104 104" role="img" aria-label="이번 달 매입·런오프 구성">${arcs}</svg>`,
        rows: rows.map((r) => ({ ...r, share: total ? Math.abs(r.value) / total * 100 : 0 })),
    };
};

// Empty state before any hover, and the filled state after -- same shape so
// hovering only ever swaps numbers in, never restructures the panel.
const mmQeQtRailBody = (row) => {
    if (!row) {
        return `<p class="mm-news-empty">막대 위에 마우스를 올리면 그 달의 국채·MBS 매입·런오프 금액과 비중이 여기 표시됩니다.</p>`;
    }
    const t = row.treasuries_bn, m = row.mbs_bn;
    const totalAbs = Math.abs(t) + Math.abs(m);
    const share = (v) => totalAbs ? `${(Math.abs(v) / totalAbs * 100).toFixed(0)}%` : '—';
    const row1 = (label, v) => `
        <div class="mm-qq-rail-row">
            <span>${finEsc(label)}</span>
            <b class="${v > 0 ? 'mm-up' : (v < 0 ? 'mm-down' : '')}">${v >= 0 ? '+' : ''}${v.toFixed(1)}B</b>
            <em>${share(v)}</em>
        </div>`;

    // Bucket detail only exists for the recent window this repo has pulled
    // CUSIP-level holdings for; older months keep the two-line product-only
    // breakdown with no pie, rather than a pie with invented slices.
    const pie = row.buckets ? mmQeQtPie(row.buckets) : null;

    return `
        <p class="mm-qq-rail-month">${finEsc(row.month)}</p>
        ${row1('국채', t)}
        ${row1('MBS', m)}
        ${pie && pie.rows.length ? `
        <div class="mm-qq-pie-wrap">
            ${pie.svg}
            <div class="mm-qq-pie-legend">
                ${pie.rows.map((r) => `
                    <div class="mm-qq-pie-row">
                        <i style="background:${finEsc(r.color)}"></i>
                        <span>${finEsc(r.label)}</span>
                        <b class="${r.value > 0 ? 'mm-up' : 'mm-down'}">${r.value >= 0 ? '+' : ''}${r.value.toFixed(1)}B</b>
                        <em>${r.share.toFixed(0)}%</em>
                    </div>`).join('')}
            </div>
        </div>
        <p class="mm-qq-rail-note">만기별·상품별 매입 비중 (뉴욕연준 SOMA 실측, 위 국채·MBS 합계와 회계 기준 차이로 소폭 다를 수 있음)</p>`
        : (row.buckets === undefined ? '' : '<p class="mm-qq-rail-note">이 달은 만기별 세부 자료가 없습니다.</p>')}`;
};

const mmQeQtRail = (row) => `
    <aside class="mm-news mm-qq-rail" id="mm-qeqt-rail">
        <p class="mm-news-head">매입·런오프 상세</p>
        <div id="mm-qeqt-rail-body">${mmQeQtRailBody(row)}</div>
        <p class="mm-news-foot">FRED TREAST·WSHOMCB 실측 · 월간</p>
    </aside>`;

const mmWireQeQtHover = (root) => {
    const box = root.querySelector('[data-mm-qeqt-root]');
    const railBody = root.querySelector('#mm-qeqt-rail-body');
    if (!box || !railBody) return;
    const rows = JSON.parse(box.getAttribute('data-rows') || '[]');
    const svg = box.querySelector('svg');
    const cross = box.querySelector('.mm-qq-cross');
    if (!svg || !rows.length) return;

    svg.addEventListener('mousemove', (ev) => {
        const b = svg.getBoundingClientRect();
        const frac = (ev.clientX - b.left) / b.width;
        const span = (MM_W - MM_L - MM_R) / MM_W;
        const i = Math.round(((frac - MM_L / MM_W) / span) * (rows.length - 1));
        const ii = Math.max(0, Math.min(rows.length - 1, i));
        const x = MM_L + (ii / Math.max(rows.length - 1, 1)) * (MM_W - MM_L - MM_R);
        if (cross) { cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.display = ''; }
        railBody.innerHTML = mmQeQtRailBody(rows[ii]);
    });
    svg.addEventListener('mouseleave', () => {
        if (cross) cross.style.display = 'none';
        railBody.innerHTML = mmQeQtRailBody(null);
    });
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

// Same fetch and computation as app.js's openChartModal (the 원자재/금융 home
// chart modal): daily bars over the /api/macro?source=yfinance Worker route,
// 5/20/60/120/240-day running-sum averages. Ported rather than shared because
// that modal is Chart.js datasets and this drawer is hand-drawn SVG paths --
// the fetch and the O(1)-per-point running sum are identical, only what
// happens to the numbers afterward differs.
const MM_MA_SPECS = [
    { window: 5, label: '5일선', color: '#f87171' },
    { window: 20, label: '20일선', color: '#facc15' },
    { window: 60, label: '60일선', color: '#4ade80' },
    { window: 120, label: '120일선', color: '#60a5fa' },
    { window: 240, label: '240일선', color: '#c084fc' },
];
const MM_MA_CACHE = new Map();  // "symbol:range" -> { dates, close } | 'loading' | Error

// range is the same '5y'/'10y' window string the rest of the drawer already
// uses (windowOpts) -- MA240 only needs ~1 trading year of run-up, but once
// the toggle exists there's no reason its two options should mean something
// different here than they do on every other tab.
const mmFetchDailyForMa = (symbol, range) => {
    const key = `${symbol}:${range}`;
    const cached = MM_MA_CACHE.get(key);
    if (cached && cached !== 'loading') return cached;
    if (cached === 'loading') return null;
    MM_MA_CACHE.set(key, 'loading');
    fetch(`/api/macro?source=yfinance&symbol=${encodeURIComponent(symbol)}&interval=1d&range=${encodeURIComponent(range)}`)
        .then((res) => res.json())
        .then((result) => {
            const chart = (result.chart || {}).result || [];
            const row = chart[0];
            if (!row) throw new Error('no chart data');
            const ts = row.timestamp || [];
            const closes = ((row.indicators || {}).quote || [{}])[0].close || [];
            const dates = [], close = [];
            for (let i = 0; i < ts.length; i++) {
                if (closes[i] === null || closes[i] === undefined) continue;
                const d = new Date(ts[i] * 1000);
                dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
                close.push(closes[i]);
            }
            MM_MA_CACHE.set(key, { dates, close });
        })
        .catch((err) => MM_MA_CACHE.set(key, err))
        // The fetch is fire-and-forget from the view's point of view: this
        // repaints once the promise lands so the loading state resolves into
        // a chart without the reader having to reopen the tab.
        .finally(() => { if (MM_CHART) mmPaint(); });
    return null;
};

const mmEquityMaView = (ind, range) => {
    const symbol = String(ind.source || '').slice('yahoo:'.length);
    if (!symbol) return '<p class="fin-note">연결된 시세 심볼이 없습니다.</p>';

    const data = mmFetchDailyForMa(symbol, range);
    if (data instanceof Error) {
        return `<p class="fin-note">일봉 데이터를 못 받았습니다 — ${finEsc(data.message)}</p>`;
    }
    if (!data) {
        return `<p class="fin-loading">일봉 ${finEsc(range.replace('y', '년'))}치를 불러오는 중…</p>`;
    }
    const { dates, close } = data;
    if (close.length < 240) {
        return `<p class="fin-note">일봉이 ${close.length}개뿐이라 240일선을 그릴 수 없습니다.</p>`;
    }

    const mas = MM_MA_SPECS.map((spec) => {
        let sum = 0;
        const series = close.map((v, i) => {
            sum += v;
            if (i >= spec.window) sum -= close[i - spec.window];
            return i >= spec.window - 1 ? sum / spec.window : null;
        });
        return { ...spec, series };
    });

    const n = close.length;
    const allVals = close.concat(...mas.map((m) => m.series)).filter(Number.isFinite);
    let lo = Math.min(...allVals), hi = Math.max(...allVals);
    const pad = (hi - lo) * 0.06;
    lo -= pad; hi += pad;
    const sx = (i) => MM_L + (i / Math.max(n - 1, 1)) * (MM_W - MM_L - MM_R);
    const sy = (v) => MM_T + (1 - (v - lo) / (hi - lo)) * (MM_H - MM_T - MM_B);
    const path = (arr) => {
        let d = '', pen = false;
        for (let i = 0; i < arr.length; i++) {
            const v = arr[i];
            if (!Number.isFinite(v)) { pen = false; continue; }
            d += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
            pen = true;
        }
        return d;
    };
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + (hi - lo) * t);
    const xAt = [0, Math.floor((n - 1) / 2), n - 1];

    // Moving averages exist to be read against price, so once there are five
    // of them, price recedes to a thin neutral trace rather than competing
    // with them in the same color -- same rule as the home chart modal.
    return `
    <svg class="mm-chart" viewBox="0 0 ${MM_W} ${MM_H}" preserveAspectRatio="none" role="img"
         aria-label="${finEsc(ind.label_ko)} 일봉 및 이동평균">
        ${ticks.map((t) => `
            <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
            <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t)}</text>`).join('')}
        <path d="${path(close)}" class="mm-ma-price"/>
        ${mas.map((m) => `<path d="${path(m.series)}" fill="none" stroke="${finEsc(m.color)}" stroke-width="1.5"/>`).join('')}
        ${xAt.map((i) => `<text x="${sx(i).toFixed(1)}" y="${MM_H - 8}" class="mm-tick"
            text-anchor="${i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle')}">${finEsc(dates[i] || '')}</text>`).join('')}
    </svg>
    <div class="mm-ma-legend">
        ${mas.map((m) => `<span class="mm-ma-key"><i style="background:${finEsc(m.color)}"></i>${finEsc(m.label)}</span>`).join('')}
    </div>
    <p class="fin-note">일별 종가, 최근 ${finEsc(range.replace('y', '년'))}(${n}거래일) · Yahoo Finance ${finEsc(symbol)}. 5/20/60/120/240일 이동평균은 단순이동평균(SMA)입니다.</p>`;
};

const mmLineChart = (dates, values, opts = {}) => {
    const idx = values.map((v, i) => [i, v]).filter(([, v]) => Number.isFinite(v));
    if (idx.length < 2) return '<p class="fin-note">그릴 수 있는 시계열이 없습니다.</p>';
    const ma = Array.isArray(opts.ma5) ? opts.ma5 : null;

    const ths = (opts.thresholds || []).filter((t) => t && Number.isFinite(t.level));
    // Every threshold has to be in view even if the series never gets near
    // it -- "설비투자 18% 초과" means nothing if the axis tops out at 15% and
    // the line is drawn off the top of the chart.
    const ys = idx.map(([, y]) => y).concat(ma ? ma.filter(Number.isFinite) : [])
        .concat(ths.map((t) => t.level));
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
            ${ths.map((t) => `
                <line x1="${MM_L}" y1="${sy(t.level).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t.level).toFixed(1)}" class="mm-threshold"/>
                <text x="${MM_W - MM_R}" y="${(sy(t.level) - 5).toFixed(1)}" class="mm-threshold-tag" text-anchor="end">${finEsc(t.label_ko || '')}</text>`).join('')}
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
// Thresholds match the report currently wired in (July 2026): $15B and 3% of
// GDP. Treasury has moved these over time -- $20B and 2% in earlier reports
// -- so this isn't a fixed constant to set once; it has to track whichever
// edition wire_us_fx_watch.py last pulled from, or the panel would show a
// threshold the badge above it was never actually tested against.
const MM_FX_WATCH_TESTS = [
    { ko: '대미 무역흑자', rule: '150억 달러 이상', key: 'trade_surplus_bn' },
    { ko: '경상수지 흑자', rule: 'GDP 대비 3% 이상', key: 'current_account_pct_gdp' },
    { ko: '일방향 외환개입', rule: '12개월 중 8개월 이상 지속 · GDP 대비 2% 이상', key: 'fx_intervention_pct_gdp' },
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
            2개 이상 충족하면 관찰대상, 3개 모두 충족하면 환율조작국입니다.
            ${finEsc(ind.monitoring_note_ko || ind.manipulator_note_ko || '')}
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

const MM_CPI_RELATION_TYPES = {
    measurement_link: {
        label: '측정상 연결', icon: '◇', cls: 'measurement',
        state: '방법론으로 확인', stateCls: 'measured',
    },
    common_driver: {
        label: '공통 요인', icon: '◎', cls: 'common',
        state: '구조 후보', stateCls: 'candidate',
    },
    external_input_required: {
        label: '외부 입력 필요', icon: '⊕', cls: 'external',
        state: '외부 데이터 미결합', stateCls: 'candidate',
    },
    market_hypothesis: {
        label: '시장 가설', icon: '⇢', cls: 'hypothesis',
        state: '검증 전 후보 경로', stateCls: 'candidate',
    },
};

const mmIsCpiStructureIndicator = (ind) => (
    MM_COUNTRY?.country?.iso3 === 'USA'
    && ['cpi_yoy', 'core_cpi_yoy'].includes(String(ind?.id || ''))
);

const mmCpiInlineStructure = (ind) => (
    ind?.cpi_structure
    || ind?.relationship_structure
    || (Array.isArray(ind?.relationship_catalog) ? ind : null)
    || (Array.isArray(ind?.relationships) ? ind : null)
    || MM_COUNTRY?.country?.cpi_structure
    || MM_COUNTRY?.cpi_structure
    || null
);

// Prefer the release-vintage snapshot when it is published. The checked-in
// map is a metadata-only fallback, so the UI still explains configured paths
// without pretending that current effects or validations were calculated.
const mmEnsureCpiStructure = async (ind) => {
    const inline = mmCpiInlineStructure(ind);
    if (inline) {
        MM_CPI_STRUCTURE = inline;
        MM_CPI_STRUCTURE_ERROR = '';
        return inline;
    }
    if (MM_CPI_STRUCTURE) return MM_CPI_STRUCTURE;
    if (MM_CPI_STRUCTURE_PROMISE) return MM_CPI_STRUCTURE_PROMISE;

    const candidates = [
        '/public/data/us_cpi_structure_v1.json',
        '/scripts/macro_monitor/config/cpi_structure.map.json',
    ];
    MM_CPI_STRUCTURE_ERROR = '';
    MM_CPI_STRUCTURE_PROMISE = (async () => {
        let lastError = null;
        for (const url of candidates) {
            try {
                const res = await fetch(url, { cache: 'no-cache' });
                if (!res.ok) throw new Error(`${res.status}`);
                const doc = await res.json();
                const rows = doc.relationship_catalog || doc.relationships;
                if (!Array.isArray(rows)) throw new Error('relationship 배열 없음');
                return doc;
            } catch (err) {
                lastError = err;
            }
        }
        throw new Error(`CPI 관계 지도를 못 받았습니다${lastError ? ` (${lastError.message})` : ''}`);
    })()
        .then((doc) => {
            MM_CPI_STRUCTURE = doc;
            return doc;
        })
        .catch((err) => {
            MM_CPI_STRUCTURE_ERROR = err.message;
            throw err;
        })
        .finally(() => {
            MM_CPI_STRUCTURE_PROMISE = null;
            if (MM_CHART && ['cpi_yoy', 'core_cpi_yoy'].includes(MM_CHART.indicatorId)) mmPaint();
        });
    return MM_CPI_STRUCTURE_PROMISE;
};

const mmCpiEndpointIds = (relation, side) => {
    const ids = relation?.[`${side}_ids`];
    if (Array.isArray(ids)) return ids.map(String);
    const rows = relation?.[`${side}s`];
    return Array.isArray(rows) ? rows.map((row) => String(row?.id || '')).filter(Boolean) : [];
};

const mmCpiItemIndex = (doc) => {
    const index = new Map();
    const add = (row) => {
        if (!row?.id) return;
        const id = String(row.id);
        index.set(id, { ...index.get(id), ...row, id });
    };
    [...(doc?.driver_frontier || []), ...(doc?.items || []), ...(doc?.mapped_components || [])].forEach(add);
    (doc?.relationship_catalog || []).forEach((rel) => {
        [...(rel.sources || []), ...(rel.targets || [])].forEach(add);
    });
    return index;
};

const mmCpiRelationshipIndex = (doc) => {
    const index = new Map();
    const rows = doc?.relationship_catalog || doc?.relationships || [];
    rows.forEach((relation) => {
        const itemIds = new Set([
            ...mmCpiEndpointIds(relation, 'source'),
            ...mmCpiEndpointIds(relation, 'target'),
        ]);
        itemIds.forEach((itemId) => {
            if (!index.has(itemId)) index.set(itemId, []);
            index.get(itemId).push(relation);
        });
    });
    return index;
};

const mmCpiRelationsForItem = (doc, itemId) => (
    mmCpiRelationshipIndex(doc).get(String(itemId || '')) || []
);

const mmCpiItemLabel = (itemId, items, fallback = '') => (
    items.get(String(itemId || ''))?.label_ko || fallback || String(itemId || '')
);

const mmCpiLagText = (lag) => {
    if (!Array.isArray(lag) || !lag.length) return '고정 시차 없음';
    if (lag.length === 1) return `${lag[0]}개월`;
    const sorted = lag.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return '고정 시차 없음';
    return `${sorted[0]}–${sorted[sorted.length - 1]}개월 후보`;
};

const mmCpiPathNode = (itemId, items, selectedId) => `
    <span class="mm-cpi-node ${itemId === selectedId ? 'is-selected' : ''}">
        ${finEsc(mmCpiItemLabel(itemId, items))}
    </span>`;

const mmCpiPathCard = (relation, items, selectedId) => {
    const type = MM_CPI_RELATION_TYPES[relation.type] || {
        label: relation.type || '관계', icon: '·', cls: 'unknown', state: '상태 미확인', stateCls: 'candidate',
    };
    const sources = mmCpiEndpointIds(relation, 'source');
    const targets = mmCpiEndpointIds(relation, 'target');
    const neutral = ['measurement_link', 'common_driver'].includes(relation.type);
    const mapping = relation.mapping_status && relation.mapping_status !== 'mapped'
        ? `<span class="mm-cpi-map-state">${finEsc(relation.mapping_status)}</span>` : '';
    return `
    <article class="mm-cpi-path mm-cpi-path-${type.cls}">
        <div class="mm-cpi-path-head">
            <span class="mm-cpi-type"><i aria-hidden="true">${type.icon}</i>${finEsc(type.label)}</span>
            <span class="mm-cpi-evidence mm-cpi-evidence-${type.stateCls}">${finEsc(type.state)}</span>
        </div>
        <div class="mm-cpi-flow" aria-label="${finEsc(type.label)} 관계 흐름">
            <div class="mm-cpi-node-group"><small>출발 항목</small>${sources.map((id) => mmCpiPathNode(id, items, selectedId)).join('')}</div>
            <span class="mm-cpi-arrow" aria-hidden="true">${neutral ? '—' : '→'}</span>
            <div class="mm-cpi-relation-hub"><strong>${type.icon}</strong><span>${finEsc(type.label)}</span><small>${finEsc(mmCpiLagText(relation.lag_months))}</small></div>
            <span class="mm-cpi-arrow" aria-hidden="true">${neutral ? '—' : '→'}</span>
            <div class="mm-cpi-node-group"><small>연결 항목</small>${targets.map((id) => mmCpiPathNode(id, items, selectedId)).join('')}</div>
        </div>
        <p class="mm-cpi-mechanism">${finEsc(relation.mechanism_ko || '')}</p>
        <details class="mm-cpi-validation">
            <summary>근거·검증 조건 ${mapping}</summary>
            ${relation.evidence_status ? `<p><b>현재 근거</b> ${finEsc(relation.evidence_status)}</p>` : ''}
            ${relation.validation_required ? `<p><b>추가 검증</b> ${finEsc(relation.validation_required)}</p>` : ''}
            ${relation.evidence_source ? `<p><b>근거 출처</b> ${finEsc(relation.evidence_source)}</p>` : ''}
        </details>
    </article>`;
};

const mmCpiPathPanel = (ind, movers) => {
    if (!mmIsCpiStructureIndicator(ind)) return '';
    const doc = mmCpiInlineStructure(ind) || MM_CPI_STRUCTURE;
    if (!doc) {
        if (MM_CPI_STRUCTURE_ERROR) return `<section class="mm-cpi-panel mm-cpi-panel-error">
            <p>${finEsc(MM_CPI_STRUCTURE_ERROR)}</p><span>항목 수치는 그대로 표시되며 관계 경로만 사용할 수 없습니다.</span>
        </section>`;
        return `<section class="mm-cpi-panel mm-cpi-panel-loading"><span class="mm-cpi-spinner"></span>CPI 관계 지도를 불러오는 중…</section>`;
    }

    const items = mmCpiItemIndex(doc);
    const relationIndex = mmCpiRelationshipIndex(doc);
    const moverRows = [...(movers.up || []), ...(movers.down || [])];
    const requested = MM_CHART?.cpiItemId;
    const selected = moverRows.find((row) => row.id === requested)
        || moverRows.find((row) => (relationIndex.get(row.id) || []).length)
        || moverRows[0]
        || null;
    if (selected && MM_CHART) MM_CHART.cpiItemId = selected.id;
    if (!selected) return '<section class="mm-cpi-panel"><p class="fin-note">선택할 CPI 항목이 없습니다.</p></section>';

    const relations = mmCpiRelationsForItem(doc, selected.id);
    const policy = doc.relationship_policy || doc.mapping_policy || {};
    const configuredRule = String(policy.rule_ko || policy.rule || '');
    const policyText = /[가-힣]/.test(configuredRule) ? configuredRule
        : '표시된 관계는 인과관계·방향 신호·예측이 아닙니다. 시장 가설은 시점 보존 표본외 검증을 통과하기 전까지 후보 경로로만 읽습니다.';
    return `
    <section class="mm-cpi-panel" aria-live="polite">
        <div class="mm-cpi-panel-head">
            <div><span class="mm-cpi-kicker">선택 항목</span><h4>${finEsc(mmCpiItemLabel(selected.id, items, selected.label_ko))}</h4></div>
            <span class="mm-cpi-count">관계 ${relations.length}개</span>
        </div>
        <div class="mm-cpi-legend" aria-label="관계 상태 범례">
            <span class="mm-cpi-evidence mm-cpi-evidence-measured">측정상 연결</span>
            <span class="mm-cpi-evidence mm-cpi-evidence-candidate">검증 전 후보</span>
        </div>
        ${relations.length ? relations.map((relation) => mmCpiPathCard(relation, items, selected.id)).join('')
            : '<p class="mm-cpi-empty">이 항목에 직접 연결된 관계 정의가 없습니다. 상·하위 CPI 항목을 자동으로 인과 연결하지 않습니다.</p>'}
        <p class="mm-cpi-policy">${finEsc(policyText)}</p>
    </section>`;
};

// Which items moved most in the latest print. Ranked on each item's own MoM,
// not on its weighted contribution to the headline -- the published artifact
// carries no relative-importance weights, and calling an unweighted mover a
// "contribution" would overstate how much it moved the index.
const mmMoversView = (ind) => {
    const mv = ind.movers || {};
    const doc = mmCpiInlineStructure(ind) || MM_CPI_STRUCTURE;
    const relationIndex = doc ? mmCpiRelationshipIndex(doc) : null;
    const moverRows = [...(mv.up || []), ...(mv.down || [])];
    if (doc && MM_CHART && mmIsCpiStructureIndicator(ind)
        && !moverRows.some((row) => row.id === MM_CHART.cpiItemId)) {
        MM_CHART.cpiItemId = moverRows.find((row) => (relationIndex.get(row.id) || []).length)?.id
            || moverRows[0]?.id
            || null;
    }
    const row = (r, dir) => {
        const interactive = mmIsCpiStructureIndicator(ind);
        const selected = MM_CHART?.cpiItemId === r.id;
        const relationCount = relationIndex ? (relationIndex.get(r.id) || []).length : null;
        const tag = interactive ? 'button' : 'div';
        return `
        <${tag} ${interactive ? 'type="button"' : ''} class="mm-mover mm-mover-${dir} ${selected ? 'is-selected' : ''}"
                ${interactive ? `data-mm-cpi-item="${finEsc(r.id)}" aria-pressed="${selected}"` : ''}>
            <span class="mm-mover-name">${finEsc(r.label_ko)}</span>
            <span class="mm-mover-mom">${r.mom_pct >= 0 ? '+' : ''}${r.mom_pct.toFixed(2)}%</span>
            <span class="mm-mover-yoy">YoY ${r.yoy_pct === null ? '—' : `${r.yoy_pct >= 0 ? '+' : ''}${r.yoy_pct.toFixed(1)}%`}</span>
            ${interactive ? `<span class="mm-mover-path-count">${relationCount === null ? '경로 확인' : `경로 ${relationCount}`}</span>` : ''}
        </${tag}>`;
    };
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
    ${mmCpiPathPanel(ind, mv)}
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
    // Assets and liabilities are two separate blocks -- two tabs -- not one
    // panel with both stacks in it. 부채 first: the reserves-against-the-axis
    // question is what this card exists to answer.
    const hasBalanceSheet = has((ind.balance_sheet || {}).sides);
    if (hasBalanceSheet) {
        views.push({ id: 'balance_liabilities', label: '부채' });
        views.push({ id: 'balance_assets', label: '자산' });
    }
    // fed_ust_ops carries a monthly, signed purchases/runoff series in place
    // of the generic '추이' -- that generic tab was drawing a fixture history
    // array frozen around -29B, untouched by the headline's earlier switch to
    // real data, because the two lived in separate fields. Real data replaces
    // both here, not just the number on top.
    const hasQeQt = has((ind.qe_qt_history || {}).rows);
    if (hasQeQt) {
        views.push({ id: 'qeqt', label: '매입 추이' });
    }
    // A plain level line is redundant once the level is already visible as
    // the top of a stack -- skipped here so fed_total_assets doesn't carry
    // both '추이' and '자산'/'부채' saying the same 6.7T two different ways.
    if (!hasBalanceSheet && !hasQeQt && (has(((ind.history || {})['5y'] || {}).values) || ind.modes)) {
        views.push({ id: 'history', label: '추이' });
    }
    // 5/20/60/120/240-day moving averages are a daily-chart convention
    // (Korean HTS terminology) and meaningless on the 5-year monthly bars
    // every other indicator uses -- a 240-period average over monthly data
    // would need 20 years of history to draw a single point. Offered only
    // for the equity indices that actually have a Yahoo symbol behind them
    // (source starts "yahoo:"); the equity ids with no live source yet
    // (csi300, hsi, sensex, ...) have no daily bars to compute this from
    // either, and this tab would just be a permanent loading spinner for them.
    if (ind.category === 'equity' && String(ind.source || '').startsWith('yahoo:')) {
        views.push({ id: 'ma', label: '이동평균' });
    }
    // Secondary panels come last so the engine's primary view stays default.
    const sv = (ind.ui || {}).secondary_view;
    // fed_total_assets shares this ui flag with qra_issuance, but its own
    // maturity split is no longer a separate tab -- it's the colour bands in
    // 자산's own stack (and the mini rail beside it). A second, static "만기별"
    // tab next to that would just repeat the same four numbers.
    if (sv === 'maturity_components' && has(ind.components) && !hasBalanceSheet) {
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
    // Headline/core swap the series without closing the drawer. Only offered
    // when both peers are actually in this country's indicator list -- a switch
    // to a series that is not there would just blank the panel.
    const byId = new Map((MM_COUNTRY.country.indicators || []).map((i) => [i.id, i]));
    const rawPeers = ind.peers;
    const peers = rawPeers && (rawPeers.options || []).filter((o) => byId.has(o.id)).length > 1
        ? { ...rawPeers, options: rawPeers.options.filter((o) => byId.has(o.id)) }
        : null;
    const modeSeries = dual ? mmModeSeries(ind, mode) : null;

    // qeqt spans 2003-present (23+ years), so 5y/10y (built for shorter
    // fixture-era series) would either show almost nothing or almost
    // everything -- 5y/20y actually brackets "recent" against "across
    // multiple QE/QT cycles" for this one.
    const windowOpts = view === 'qeqt' ? ['5y', '20y'] : ['5y', '10y'];
    const showWindow = view === 'history' || view === 'qeqt' || view === 'ma';

    let body = '';
    if (view === 'ma') body = mmEquityMaView(ind, windowOpts.includes(MM_CHART.window) ? MM_CHART.window : '5y');
    else if (view === 'balance_assets') body = mmBalanceAssetsView(ind);
    else if (view === 'balance_liabilities') body = mmBalanceLiabilitiesView(ind);
    else if (view === 'qeqt') body = mmQeQtBars(ind.qe_qt_history, MM_CHART.window || '5y');
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
            thresholds: Array.isArray(ind.thresholds) && ind.thresholds.length
                ? ind.thresholds.filter((t) => t.kind === 'threshold')
                : ((ind.reference || {}).kind === 'threshold' ? [ind.reference] : []),
        });
    }

    // With a mode selected the header has to follow it. The label carries the
    // engine's default window ("근원 CPI YoY"), so on MoM the title claimed YoY
    // while the bars below were monthly, and the value beside it stayed the YoY
    // print. The mode buttons already name the window, so the title drops the
    // suffix and the value comes from the active series.
    const modeLabel = modeSeries ? (modeSeries.label_ko || String(mode).toUpperCase()) : null;
    const title = modeLabel
        ? `${finEsc(ind.label_ko.replace(/\s*(YoY|MoM|QoQ)\s*$/i, ''))} <span class="mm-drawer-mode">${finEsc(modeLabel)}</span>`
        : finEsc(ind.label_ko);

    const meta = [
        (modeSeries ? modeSeries.display : ind.display) != null
            ? String(modeSeries ? modeSeries.display : ind.display) : null,
        ind.asof ? `기준 ${ind.asof}` : null,
        ind.source ? (typeof ind.source === 'string' ? ind.source : ind.source.name) : null,
        ind.refresh_tier || null,
    ].filter(Boolean);

    return `
    <div class="mm-drawer" role="dialog" aria-label="${finEsc(ind.label_ko)}">
        <div class="mm-drawer-head">
            <div>
                <h3>${title} ${mmStatusBadge(ind.data_status)}</h3>
                <p class="mm-drawer-sub">${meta.map((m) => finEsc(m)).join(' · ')}</p>
            </div>
            <div class="mm-drawer-actions">
                <div class="mm-toggle-grid">
                    ${peers ? `<div class="pf-mode">
                        ${peers.options.map((o) => `<button type="button" class="pf-mode-btn ${o.id === ind.id ? 'on' : ''}"
                            data-mm-peer="${finEsc(o.id)}">${finEsc(o.label_ko)}</button>`).join('')}
                    </div>` : ''}
                    ${dual ? `<div class="pf-mode">
                        ${dual.map((m) => `<button type="button" class="pf-mode-btn ${m === mode ? 'on' : ''}"
                            data-mm-mode="${finEsc(m)}">${finEsc(((ind.modes || {})[m] || {}).label_ko || m.toUpperCase())}</button>`).join('')}
                    </div>` : ''}
                    ${showWindow ? `<div class="pf-mode">
                        ${windowOpts.map((w) => `<button type="button" class="pf-mode-btn ${MM_CHART.window === w ? 'on' : ''}"
                            data-mm-window="${w}">${w.replace('y', '년')}</button>`).join('')}
                    </div>` : ''}
                </div>
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
                ${(() => {
                    // Threshold lines already render on the chart above (each
                    // with its own label); these notes are only their
                    // citations. Anything else under `reference` still falls
                    // back to a readable string -- but never a raw JSON dump,
                    // which is what an object here rendered as before.
                    const list = Array.isArray(ind.thresholds) && ind.thresholds.length
                        ? ind.thresholds
                        : (ind.reference && ind.reference.kind === 'threshold' ? [ind.reference] : []);
                    if (list.length) {
                        return list.filter((t) => t.source_ko).map((t) =>
                            `<p class="fin-note">기준선(${finEsc(t.label_ko || '')}): ${finEsc(t.source_ko)}</p>`).join('');
                    }
                    if (typeof ind.reference === 'string') return `<p class="fin-note">${finEsc(ind.reference)}</p>`;
                    return '';
                })()}
            </div>
            ${view === 'qeqt' ? mmQeQtRail(null)
                : view === 'balance_liabilities' && (ind.balance_sheet || {}).ratio
                ? mmReservesRatioRail(ind.balance_sheet.ratio, ind.balance_sheet.dates || [])
                : view === 'balance_assets'
                ? mmSomaMaturityRail(ind)
                : mmNewsRail(ind)}
        </div>
    </div>`;
};

// 자산's rail carries the SOMA maturity split instead of news -- read from
// balance_sheet's own layers (live, CUSIP-derived), not the fed_ust_le_1y-
// style `components` field, which is still the old seeded-fixture numbers
// nothing has repointed since the stack itself moved to real data.
const mmSomaMaturityRail = (ind) => {
    const bs = ind.balance_sheet;
    const side = ((bs || {}).sides || []).find((s) => s.id === 'assets');
    const buckets = (side ? side.layers : []).filter((l) => l.id.startsWith('treasuries_'));
    if (!buckets.length) return mmNewsRail({});

    const last = (l) => {
        for (let i = l.values.length - 1; i >= 0; i--) {
            if (Number.isFinite(l.values[i])) return l.values[i];
        }
        return null;
    };
    const rows = buckets.map((l) => [l, last(l)]).filter(([, v]) => v !== null);
    const total = rows.reduce((a, [, v]) => a + v, 0);

    return `
    <aside class="mm-news mm-soma-rail">
        <p class="mm-news-head">국채(SOMA) 만기 구성</p>
        <div class="mm-ratio-rail-now">${mmFmt(total, 2)}조</div>
        ${rows.map(([l, v]) => `
            <div class="mm-bs-tip-row">
                <i style="background:${finEsc(l.color)}"></i>
                <span>${finEsc((l.label_ko || '').replace('국채 ', '').replace(' (SOMA)', ''))}</span>
                <b>${mmFmt(v, 2)}조</b>
                <em>${total ? (v / total * 100).toFixed(1) : '—'}%</em>
            </div>`).join('')}
        <p class="mm-news-foot">${finEsc(bs.asof || '')} 기준 · 비중 뉴욕연준 SOMA 실측</p>
    </aside>`;
};

// The news API is not wired yet. An empty rail that says so is honest; a
// spinner that never resolves is not, and fabricated articles would be worse.
// The 부채 tab's rail carries the reserves/GDP number instead of the news
// stub: that ratio is the one figure the stack itself cannot show (a stack
// draws levels, not a ratio against an outside series), and it belongs next
// to the liabilities it is computed from rather than buried under the chart.
const mmReservesRatioRail = (r, dates) => {
    const vals = r.values || [];
    const idx = vals.map((v, i) => [i, v]).filter(([, v]) => Number.isFinite(v));
    if (!idx.length) return mmNewsRail({});
    const [li, lv] = idx[idx.length - 1];
    const th = Number.isFinite(r.threshold_pct) ? r.threshold_pct : null;
    const under = th !== null && lv < th;

    const RW = 160, RH = 60, RT = 4, RB = 4;
    const sx = (i) => (i / Math.max(vals.length - 1, 1)) * RW;
    const ys = idx.map(([, v]) => v).concat(th === null ? [] : [th]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pad = (hi - lo || 1) * 0.15;
    lo = Math.max(0, lo - pad); hi += pad;
    const sy = (v) => RT + (1 - (v - lo) / (hi - lo)) * (RH - RT - RB);
    const path = idx.map(([i, v], k) => `${k ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join('');

    return `
    <aside class="mm-news mm-ratio-rail">
        <p class="mm-news-head">${finEsc(r.label_ko || '')}</p>
        <div class="mm-ratio-rail-now ${under ? 'is-under' : ''}">${mmFmt(lv, 2)}%</div>
        <svg class="mm-ratio-rail-spark" viewBox="0 0 ${RW} ${RH}" preserveAspectRatio="none" role="img" aria-label="추이">
            ${th === null ? '' : `<line x1="0" y1="${sy(th).toFixed(1)}" x2="${RW}" y2="${sy(th).toFixed(1)}" class="mm-threshold"/>`}
            <path d="${path}" class="mm-ratio-line"/>
            <circle cx="${sx(li).toFixed(1)}" cy="${sy(lv).toFixed(1)}" r="2.6" class="mm-ratio-dot"/>
        </svg>
        <p class="mm-news-empty">${finEsc(r.threshold_note_ko || '')}</p>
        <p class="mm-news-foot">${finEsc(dates[li] || '')} 기준 · ${finEsc(r.threshold_label_ko || '')}</p>
    </aside>`;
};

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

const mmExcerpt = (value, max = 210) => {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
};

// This is an evidence panel, not an FOMC forecast panel. It lives inside the
// existing U.S. overlay so the published vote and the Beige Book context are
// read next to the ordinary macro indicators rather than as a second dashboard.
const mmUsPolicyQuality = (quality) => {
    if (!quality || quality.schema_version !== 'us-macro-quality-v1') return '';
    const policy = quality.policy_committee || {};
    const cmp = policy.comparison || {};
    const roster = policy.current_roster || {};
    const documents = ((quality.official_documents || {}).items || []);
    const latestStatement = documents.find((row) => row.document_type === 'fomc_statement');
    const beige = documents.find((row) => row.document_type === 'beige_book' && row.extracted_evidence);
    const evidence = (beige || {}).extracted_evidence || {};
    const dissent = cmp.current_dissents || {};
    const direction = Object.entries(dissent.directions || {}).map(([key, value]) => {
        const label = ({ tighter: '인상 선호', easier: '인하 선호', other_public_dissent: '기타 공개 반대' })[key] || key;
        return `${label} ${value}명`;
    }).join(' · ') || '공개 반대 없음';
    const transitions = cmp.public_vote_transitions || [];
    const sections = evidence.national_sections || [];
    const districts = evidence.districts || [];
    const sourceDate = beige ? String(beige.reference_period || '').slice(0, 10) : '';

    if (!cmp.current_meeting && !beige && !roster.members) return '';
    return `
    <section class="mm-quality" aria-label="미국 정책 및 현장 진단">
        <div class="mm-quality-head">
            <div>
                <p class="mm-quality-kicker">공식 문서 · 공개 표결</p>
                <h3>정책·현장 진단</h3>
            </div>
            <span class="mm-quality-status">예측·성향 점수 아님</span>
        </div>
        <div class="mm-quality-grid">
            <div class="mm-quality-card">
                <span class="mm-quality-label">FOMC 공개 표결</span>
                <strong>${finEsc(cmp.previous_meeting || '—')} → ${finEsc(cmp.current_meeting || '—')}</strong>
                <p>반대 ${Number(dissent.count || 0)}명 · ${finEsc(direction)}</p>
                ${transitions.length ? `<div class="mm-quality-names">${transitions.map((row) =>
                    `<span>${finEsc(row.name)} · ${finEsc(({ tighter: '인상 선호', easier: '인하 선호' })[row.to_direction] || '공개 반대')}</span>`
                ).join('')}</div>` : '<span class="mm-quality-muted">직전 회의 대비 공개 표결 변화 없음</span>'}
                ${latestStatement ? `<a class="mm-quality-link" href="${finEsc(latestStatement.source_url)}" target="_blank" rel="noopener noreferrer">최근 결정문 보기 ↗</a>` : ''}
            </div>
            <div class="mm-quality-card">
                <span class="mm-quality-label">투표권 구성</span>
                <strong>${finEsc(String(roster.roster_year || ''))}년 ${Array.isArray(roster.members) ? roster.members.length : 0}명</strong>
                <p>위원 변화는 공개 투표권 기준으로만 비교합니다.</p>
                ${Array.isArray(roster.members) && roster.members.length ? `<details class="mm-quality-details">
                    <summary>현재 투표권자 보기</summary>
                    <p>${roster.members.map((member) => `${member.name} (${member.role})`).join(' · ')}</p>
                </details>` : ''}
            </div>
            <div class="mm-quality-card mm-quality-beige">
                <span class="mm-quality-label">Beige Book ${finEsc(sourceDate)}</span>
                <strong>${districts.length ? `12개 District 현장 의견` : '공식 현장 보고서'}</strong>
                ${sections.length ? `<details class="mm-quality-details">
                    <summary>전국 요약 보기</summary>
                    ${sections.map((section) => `<p><b>${finEsc(section.section)}</b> ${finEsc(mmExcerpt(section.text))}</p>`).join('')}
                </details>` : '<p class="mm-quality-muted">발행본 수집 대기</p>'}
                ${beige ? `<a class="mm-quality-link" href="${finEsc(beige.source_url)}" target="_blank" rel="noopener noreferrer">원문 보기 ↗</a>` : ''}
            </div>
        </div>
        <p class="mm-quality-foot">공개 표결은 회의 당시의 행동 기록이고, Beige Book은 접촉자 의견입니다. 둘 다 다음 회의나 시장의 방향을 자동 예측하지 않습니다.</p>
    </section>`;
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

        ${c.iso3 === 'USA' ? mmUsPolicyQuality(MM_COUNTRY.quality) : ''}

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
    if (host.querySelector('[data-mm-qeqt-root]')) mmWireQeQtHover(host);
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
        // The quality/policy-document fetch is USA-only and independent of
        // the country pack -- fetched alongside it, not blocking it, since a
        // slow or missing document snapshot should never delay the ordinary
        // indicator overlay every other country also needs.
        const [countryPayload, quality] = await Promise.all([
            mmFetch(iso3),
            iso3 === 'USA' ? mmQualityFetch().catch(() => null) : Promise.resolve(null),
        ]);
        MM_COUNTRY = countryPayload;
        if (quality) MM_COUNTRY.quality = quality;
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
                const ind = (MM_COUNTRY?.country?.indicators || []).find((row) => row.id === id);
                if (MM_CHART && mmIsCpiStructureIndicator(ind)) {
                    mmEnsureCpiStructure(ind).catch(() => {});
                }
                mmPaint();
                return;
            }
            const cpiItem = t.closest('[data-mm-cpi-item]');
            if (cpiItem && MM_CHART) {
                MM_CHART.cpiItemId = cpiItem.getAttribute('data-mm-cpi-item');
                MM_CHART.view = 'movers';
                mmPaint();
                return;
            }
            const win = t.closest('[data-mm-window]');
            if (win && MM_CHART) { MM_CHART.window = win.getAttribute('data-mm-window'); mmPaint(); return; }
            const vw = t.closest('[data-mm-view]');
            if (vw && MM_CHART) { MM_CHART.view = vw.getAttribute('data-mm-view'); mmPaint(); return; }
            const md = t.closest('[data-mm-mode]');
            if (md && MM_CHART) { MM_CHART.mode = md.getAttribute('data-mm-mode'); mmPaint(); return; }
            // Swapping headline for core keeps the window, view and YoY/MoM
            // choice -- those are what the reader set up to make the comparison.
            const pr = t.closest('[data-mm-peer]');
            if (pr && MM_CHART) {
                MM_CHART = { ...MM_CHART, indicatorId: pr.getAttribute('data-mm-peer') };
                mmPaint();
                return;
            }
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
