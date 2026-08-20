// Application Logic for Global Trade Dashboard
const { DeckGL, LineLayer, ArcLayer, PathLayer, ScatterplotLayer, GeoJsonLayer,
        SolidPolygonLayer, SimpleMeshLayer, COORDINATE_SYSTEM, TextLayer,
        _GlobeView, MapView, WebMercatorViewport } = deck;
const { SphereGeometry } = luma;

// DOM Elements
const tooltipEl = document.getElementById('tooltip');

/**
 * deck.gl's onHover `info.x`/`info.y` are relative to the map canvas
 * container (id="map", the element deck.gl was constructed with as its
 * `container`). #tooltip itself sits outside .map-pane in the DOM (a
 * sibling of <main>) with no positioned ancestor of its own, so its
 * `position: absolute` resolves against the viewport instead -- using
 * info.x/info.y directly landed the tooltip offset by roughly the width of
 * the left sidebar. This adds the map container's own viewport offset back
 * in before positioning.
 */
const positionTooltipAt = (info, offset = 12) => {
    const rect = mapContainer ? mapContainer.getBoundingClientRect() : { left: 0, top: 0 };
    tooltipEl.style.left = `${rect.left + info.x + offset}px`;
    tooltipEl.style.top = `${rect.top + info.y + offset}px`;
};
const newsContentEl = document.getElementById('news-content');
const newsPanelEl = document.getElementById('news-panel');
const forecastPanelEl = document.getElementById('climate-forecast-panel');
const forecastContentEl = document.getElementById('forecast-content');
const forecastCountryTitle = document.getElementById('forecast-country-title');

// Right panel elements
const macroPanelEl = document.getElementById('macro-panel');
const countryStatsPanelEl = document.getElementById('country-stats-panel');
const countryStatsTitleEl = document.getElementById('country-stats-title');
const countryStatsContentEl = document.getElementById('country-stats-content');
const climateRightPanelEl = document.getElementById('climate-right-panel');
const climateRightTitleEl = document.getElementById('climate-right-title');
const climateRightDescEl = document.getElementById('climate-right-desc');
const climateRightContentEl = document.getElementById('climate-right-content');
const climateMapLegendEl = document.getElementById('climate-map-legend');

const panelHide = (el) => { if (el) el.classList.add('hidden'); };
const panelShow = (el) => { if (el) el.classList.remove('hidden'); };


const totalVolumeEl = document.getElementById('total-volume');
const topExporterEl = document.getElementById('top-exporter');
const currentViewTitle = document.getElementById('current-view-title');
const currentViewDesc = document.getElementById('current-view-desc');
const mapContainer = document.getElementById('map');
const chartView = document.getElementById('chart-view');
const navLinks = document.querySelectorAll('.dropdown a');

// State management
let selectedCountry = null;
let currentCommodity = null; // 'coal', 'oil', 'gold', 'climate'
let forecastData = {};
// Trade map: which country is focused (export→partner ranking). null = world flows.
let tradeFocusCountry = null;
let tradeAnimRaf = null;
let tradeAnimPhase = 0;

window.initApp = function() {
    forecastData = window.ForecastData || {};
    if (window.MacroData) {
        refreshSignalMarkets();
    }
};

if (window.MacroData) {
    window.initApp();
}

// ==========================================
// 「오늘 신호」 panel (home right pane)
// ==========================================
//
// Replaces the old flat column of macro tiles. Two zones:
//
//   고정 3   ENSO / chokepoint pressure / KOSPI risk -- never rotate, and speak
//            in state-and-deviation language (엘니뇨·중, −4.2%) because they are
//            standing conditions rather than prices.
//   순환 A–F Six pages of four slots, swapped a whole page at a time on a drum
//            flip every 8s. These are plain numbers with units.
//
// A slot with no feed behind it renders as a labelled 연동 예정 placeholder.
// That is deliberate: SCFI/BDI are licence-gated (see market_signals in the
// shipping snapshot), KOSPI waits on a KRX key, and bunker quotes wait on the
// weekly artifact -- none of them may be silently approximated from something
// else. Anything published on a lag carries an `as of` date.

// 4.5s per page (was 3.5s -- still too brisk to read four slots). The flip
// itself runs 0.45s (see .signal-page in style.css), leaving ~4s of still
// time; the page name and the dots make it clear another turn is coming, and
// hover freezes the drum.
const SIGNAL_ROTATE_MS = 4500;
// Kept in step with the CSS transition; the outgoing page is removed once it
// has finished rotating away.
const SIGNAL_FLIP_MS = 500;

// value: key into window.MacroData. fmt: how to print it. symbol: Yahoo ticker,
// which makes the slot clickable and opens the chart modal with a moving average.
const SIGNAL_PAGES = [
    {
        key: 'A', name: '에너지',
        slots: [
            { label: 'Brent 원유', value: 'BRENT', fmt: 'usd2', unit: '/bbl', symbol: 'BZ=F' },
            { label: 'Singapore VLSFO', pending: '주간 벙커 연동 예정' },
            { label: 'Henry Hub 가스', value: 'NAT_GAS', fmt: 'usd3', unit: '/MMBtu', symbol: 'NG=F' },
            { label: 'Newcastle 연료탄', pending: '주간 연동 예정' }
        ]
    },
    {
        // IMF monthly commodity prices: published with a lag, so every slot on
        // this page shows the month it is quoting.
        key: 'B', name: '농산물',
        slots: [
            { label: '밀', value: 'WHEAT', fmt: 'usd0', unit: '/t', symbol: 'ZW=F' },
            { label: '옥수수', value: 'CORN', fmt: 'usd0', unit: '/t', symbol: 'ZC=F' },
            { label: '대두', value: 'SOYBEANS', fmt: 'usd0', unit: '/t', symbol: 'ZS=F' },
            { label: '설탕 No.11', value: 'SUGAR', fmt: 'cents2', unit: '/lb', symbol: 'SB=F' }
        ]
    },
    {
        key: 'C', name: '환율',
        slots: [
            // ICE licenses DXY itself; the Fed's broad dollar index is the
            // standard public stand-in, hence the explicit label.
            { label: '달러지수 (광의)', value: 'DXY_BROAD', fmt: 'idx2', note: 'Fed 광의 달러' },
            { label: 'USD / JPY', value: 'USD/JPY', fmt: 'fx2', symbol: 'JPY=X' },
            { label: 'EUR / USD', value: 'EUR/USD', fmt: 'fx4', symbol: 'EUR=X' },
            { label: 'USD / KRW', value: 'KRW_USD', fmt: 'krw', symbol: 'KRW=X' }
        ]
    },
    {
        // Japan/UK are OECD monthly series (see data.js) -- everything else on
        // this page is a daily constant-maturity yield, so those two carry an
        // `as of` month where the US pair carries an `as of` day.
        key: 'D', name: '금리',
        slots: [
            { label: '미 국채 2년', value: 'US2Y', fmt: 'pct2' },
            { label: '미 국채 10년', value: 'US10Y', fmt: 'pct2' },
            { label: '일본 국채 10년', value: 'JP10Y', fmt: 'pct2', symbol: 'JP10Y' },
            { label: '영국 길트 10년', value: 'UK10Y', fmt: 'pct2', symbol: 'UK10Y' }
        ]
    },
    {
        // ma:true is exclusive to this page -- see the moving-average note in
        // openChartModal for why equities get one and the other pages don't.
        key: 'E', name: '주식',
        slots: [
            { label: 'S&P 500', value: 'SP500', fmt: 'idx2', symbol: '^GSPC', ma: true },
            { label: '나스닥 종합', value: 'NASDAQ', fmt: 'idx2', symbol: '^IXIC', ma: true },
            // No cheap spot quote for these two, but the chart route serves any
            // Yahoo symbol -- so the tile says 연동 예정 and the click still works.
            { label: '필라델피아 반도체', pending: '지수 연동 예정', symbol: '^SOX', ma: true },
            { label: 'KOSPI', pending: 'KRX 키 재발급 대기', symbol: '^KS11', ma: true }
        ]
    },
    {
        // Baltic Exchange and SCFI assessments need a redistribution licence,
        // so these stay empty until the weekly artifact lands. Do not substitute.
        key: 'F', name: '해운',
        slots: [
            { label: 'SCFI 컨테이너', pending: '주간 운임 연동 예정' },
            { label: 'BDI 벌크', pending: '주간 운임 연동 예정' },
            { label: 'CCFI 컨테이너', pending: '주간 운임 연동 예정' },
            { label: '탱커 운임', pending: '주간 운임 연동 예정' }
        ]
    }
];

const signalEls = {
    panel: () => document.getElementById('macro-panel'),
    fixed: () => document.getElementById('signal-fixed'),
    stage: () => document.getElementById('signal-stage'),
    rotator: () => document.getElementById('signal-rotator'),
    dots: () => document.getElementById('signal-dots')
};

const signalEsc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

// FRED and EIA hand back ISO dates; BOK hands back a compact CYCLE string
// (20260818 daily, 202608 monthly). Normalise all three to YYYY-MM-DD / YYYY-MM.
const signalAsOf = (raw) => {
    const s = String(raw || '').trim();
    if (!s || s === 'N/A') return '';
    if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    if (/^\d{6}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}`;
    return s.split(' ')[0];
};

const signalFormat = (fmt, raw) => {
    const num = parseFloat(raw);
    if (!isFinite(num)) return null;
    switch (fmt) {
        case 'usd0': return `$${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
        case 'usd2': return `$${num.toFixed(2)}`;
        case 'usd3': return `$${num.toFixed(3)}`;
        case 'cents2': return `${num.toFixed(2)}¢`;
        case 'fx2': return num.toFixed(2);
        case 'fx4': return num.toFixed(4);
        case 'idx2': return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
        case 'krw': return `${num.toLocaleString(undefined, { maximumFractionDigits: 1 })}원`;
        case 'pct2': return `${num.toFixed(2)}%`;
        case 'trillion': return `$${(num / 1000000).toFixed(2)}조`;
        case 'billion': return `$${(num / 1000).toFixed(0)}B`;
        default: return String(raw);
    }
};

// Compact sparkline for a signal slot: shape only, no axis or hover readout.
// The wide spark2 component in trade.js answers "how far from its range is
// this?" and needs the room to do it; here the number beside it already gives
// the level, and the line only has to say which way it has been going. Clicking
// through to the chart modal is where the full picture lives.
const signalSparkHtml = (points) => {
    if (!points || points.length < 3) return '';
    const W = 96, H = 34, PAD = 2;
    const vals = points.map(p => p.value);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    // A flat series must not divide by zero; drawing it mid-box is more honest
    // than pinning it to an edge.
    const span = max - min || 1;
    const x = (i) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
    const y = (v) => PAD + (1 - (v - min) / span) * (H - PAD * 2);

    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
    const area = `${line}L${x(points.length - 1).toFixed(1)},${H - PAD}L${x(0).toFixed(1)},${H - PAD}Z`;
    const last = points[points.length - 1];
    const rising = last.value >= points[0].value;

    return `<svg class="signal-spark ${rising ? 'up' : 'down'}" viewBox="0 0 ${W} ${H}"
                 preserveAspectRatio="none" aria-hidden="true">
        <path class="signal-spark-area" d="${area}"/>
        <path class="signal-spark-line" d="${line}" vector-effect="non-scaling-stroke"/>
        <circle class="signal-spark-dot" cx="${x(points.length - 1).toFixed(1)}" cy="${y(last.value).toFixed(1)}" r="1.6"/>
    </svg>`;
};

const signalSlotHtml = (slot) => {
    const macro = window.MacroData || {};
    const entry = slot.value ? macro[slot.value] : null;
    const shown = entry ? signalFormat(slot.fmt, entry.value) : null;
    const asOf = entry ? signalAsOf(entry.asOf || entry.date) : '';
    const clickable = !!slot.symbol;

    // A slot is pending either because it was declared that way, or because the
    // feed answered with something unparseable -- both read the same to a viewer.
    const body = shown
        ? `<span class="signal-slot-value">${signalEsc(shown)}${
              slot.unit ? `<span class="signal-slot-unit">${signalEsc(slot.unit)}</span>` : ''
          }</span>`
        : `<span class="signal-slot-value is-pending">${signalEsc(slot.pending || '연동 예정')}</span>`;

    // "차트만 제공" belongs only to a slot that was declared without a feed and
    // still has a chart behind it. A slot that has a feed and simply hasn't
    // answered yet gets no footnote -- claiming it is chart-only would be wrong.
    const foot = shown
        ? (asOf ? `as of ${signalEsc(asOf)}` : (slot.note ? signalEsc(slot.note) : ''))
        : (!slot.value && slot.symbol ? '차트만 제공' : '');

    // Only a slot showing a real number gets a line; a sparkline over a
    // pending tile would imply data the panel does not have.
    const spark = shown ? signalSparkHtml(entry.history) : '';

    return `<div class="signal-slot${clickable ? ' is-clickable' : ''}"${
        clickable
            ? ` role="button" tabindex="0" data-symbol="${signalEsc(slot.symbol)}" data-label="${signalEsc(slot.label)}"${slot.ma ? ' data-ma="1"' : ''}`
            : ''
    }>
        <div class="signal-slot-main">
            <span class="signal-slot-label">${signalEsc(slot.label)}</span>
            ${body}
            <span class="signal-slot-foot">${foot}</span>
        </div>
        <div class="signal-slot-chart">${spark}</div>
    </div>`;
};

let signalIndex = 0;
let signalTimer = null;
let signalPaused = false;

const signalBuildPage = (page) => {
    const el = document.createElement('div');
    el.className = 'signal-page';
    el.innerHTML = `<span class="signal-page-name">${signalEsc(page.name)}</span>`
        + page.slots.map(signalSlotHtml).join('');
    return el;
};

const signalRenderDots = () => {
    const host = signalEls.dots();
    if (!host) return;
    host.innerHTML = SIGNAL_PAGES.map((p, i) =>
        `<button type="button" class="signal-dot${i === signalIndex ? ' is-on' : ''}" data-idx="${i}" aria-label="${signalEsc(p.name)} 페이지"></button>`
    ).join('');
};

const signalShowPage = (idx, animate) => {
    const stage = signalEls.stage();
    if (!stage) return;
    signalIndex = ((idx % SIGNAL_PAGES.length) + SIGNAL_PAGES.length) % SIGNAL_PAGES.length;
    const page = SIGNAL_PAGES[signalIndex];

    const prev = stage.querySelector('.signal-page.is-active');
    const next = signalBuildPage(page);

    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!animate || !prev || reduced) {
        stage.innerHTML = '';
        stage.appendChild(next);
        next.classList.add('is-active');
    } else {
        next.classList.add('is-entering');
        stage.appendChild(next);
        // Force layout so the browser has an "entering" frame to animate from;
        // without it the class swap below collapses into no transition at all.
        void next.offsetWidth;
        next.classList.remove('is-entering');
        next.classList.add('is-active');
        prev.classList.remove('is-active');
        prev.classList.add('is-leaving');
        setTimeout(() => prev.remove(), SIGNAL_FLIP_MS);
    }
    signalRenderDots();
};

const signalTick = () => {
    const panel = signalEls.panel();
    // Hold position while the panel is off-screen (another view is up) or the
    // tab is in the background -- rotating unseen just means the viewer comes
    // back to an arbitrary page.
    if (signalPaused || document.hidden) return;
    if (!panel || panel.classList.contains('hidden')) return;
    signalShowPage(signalIndex + 1, true);
};

// Re-renders the visible page in place. Called when macro data lands after the
// first paint, so slots fill in without waiting for the next rotation.
function refreshSignalMarkets() {
    if (!signalEls.stage()) return;
    signalShowPage(signalIndex, false);
}

// ---- 고정 3 --------------------------------------------------------------

// `foot` carries the as-of date on its own line. Folding it into `sub` made the
// date wrap mid-token (2026-08-\n09) once the worst-point name grew.
const signalFixedCard = ({ id, title, value, sub, foot, tone, target }) => `
    <div class="signal-fixed-card${target ? ' is-clickable' : ''}${tone ? ` tone-${tone}` : ''}"
         id="${id}"${target ? ` role="button" tabindex="0" data-target="${signalEsc(target)}"` : ''}>
        <span class="signal-fixed-title">${signalEsc(title)}</span>
        <span class="signal-fixed-value">${signalEsc(value)}</span>
        <span class="signal-fixed-sub">${signalEsc(sub)}</span>
        ${foot ? `<span class="signal-fixed-foot">${signalEsc(foot)}</span>` : ''}
    </div>`;

const signalRenderFixed = (state) => {
    const host = signalEls.fixed();
    if (!host) return;
    host.innerHTML = [
        signalFixedCard(state.enso),
        signalFixedCard(state.choke),
        signalFixedCard(state.kospi)
    ].join('');
};

// Fixed-card state, filled in by the async loaders below. All three start as
// honest placeholders so the panel is never blank while data is in flight.
const signalFixedState = {
    enso: {
        id: 'signal-enso', title: 'ENSO 엘니뇨·라니냐',
        value: '불러오는 중', sub: 'NOAA CPC Niño 3.4', target: 'climate'
    },
    choke: {
        id: 'signal-choke', title: '초크포인트 압력 (통합)',
        value: '불러오는 중', sub: 'IMF PortWatch 7일 vs 28일', target: 'shipping_chokepoints'
    },
    kospi: {
        id: 'signal-kospi', title: 'K200 옵션 풋콜 비율',
        value: '불러오는 중', sub: 'KRX 코스피200 옵션 거래량', target: 'fin_derivatives'
    }
};

const signalLoadEnso = async () => {
    try {
        const res = await fetch('/public/data/climate_global_v1.json', { cache: 'no-cache' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const enso = (await res.json()).enso || {};
        const c = Number(enso.latest_c);
        if (!isFinite(c)) throw new Error('ONI 값 없음');
        const signed = `${c >= 0 ? '+' : '−'}${Math.abs(c).toFixed(2)}°C`;
        // Lead with the ONI reading itself -- "+1.39°C" is legible at a glance,
        // where "엘니뇨 · 중" makes the viewer already know the NOAA state
        // taxonomy to place it. The state word moves to the sub-line as
        // context, not the headline.
        signalFixedState.enso = {
            ...signalFixedState.enso,
            value: `Niño 3.4 ${signed}`,
            sub: `${enso.state_ko || 'ENSO 중립'}${enso.season ? ` · ${enso.season}` : ''} · NOAA CPC`,
            tone: c >= 0.5 ? 'warn' : (c <= -0.5 ? 'cool' : null)
        };
    } catch (e) {
        console.error('ENSO 신호 로드 실패:', e);
        signalFixedState.enso = { ...signalFixedState.enso, value: '연동 예정', sub: 'NOAA CPC 응답 없음', tone: 'muted' };
    }
    signalRenderFixed(signalFixedState);
};

const signalLoadChokepoints = async () => {
    try {
        const loader = window.ShippingDashboard && window.ShippingDashboard.loadData;
        const data = loader
            ? await loader()
            : await fetch('/public/data/shipping_capacity_v1.json', { cache: 'no-cache' }).then(r => r.json());

        const live = data.chokepoints_live || {};
        const names = new Map((data.chokepoints || []).map(p => [p.id, p.name_ko || p.id]));

        // Spec: one integrated stress index, not Suez alone. The snapshot has no
        // composite field yet (Codex owns adding one), so until it does this is
        // the arithmetic mean of every point's 7d-vs-28d change -- which the
        // ticket explicitly allows as the first pass. Prefer a published
        // composite the moment one appears.
        const published = Number(data.chokepoint_composite?.change_pct);
        const points = Object.entries(live)
            .map(([id, v]) => ({ id, name: names.get(id) || id, chg: Number(v?.metrics?.all?.change_pct) }))
            .filter(p => isFinite(p.chg));
        if (!points.length) throw new Error('초크포인트 관측값 없음');

        const worst = points.reduce((a, b) => (b.chg < a.chg ? b : a));
        const composite = isFinite(published)
            ? published
            : points.reduce((sum, p) => sum + p.chg, 0) / points.length;

        const asOf = signalAsOf(Object.values(live)[0]?.latest_date);
        const pct = (n) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}%`;
        signalFixedState.choke = {
            ...signalFixedState.choke,
            value: pct(composite),
            sub: `${points.length}개 지점 평균 · 최악: ${worst.name} ${pct(worst.chg)}`,
            foot: asOf ? `as of ${asOf}` : '',
            tone: composite <= -10 ? 'warn' : null
        };
    } catch (e) {
        console.error('초크포인트 신호 로드 실패:', e);
        signalFixedState.choke = { ...signalFixedState.choke, value: '연동 예정', sub: 'PortWatch 스냅샷 없음', tone: 'muted' };
    }
    signalRenderFixed(signalFixedState);
};

// KOSPI200 option put/call volume ratio. Ratio above 1 means more puts than
// calls traded -- the usual shorthand for hedging demand outpacing upside bets.
// The board is written by the KRX OpenAPI job (scripts/market_microstructure),
// so this card only reads what that job published; a missing file leaves the
// placeholder rather than reconstructing a ratio from anything else.
const signalLoadPutCall = async () => {
    try {
        const res = await fetch('/public/data/derivatives_board_v1.json', { cache: 'no-cache' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const kr = (await res.json()).kr || {};
        const opts = kr.kospi200_options || {};
        const ratio = Number(opts.put_call_volume);
        if (!isFinite(ratio)) throw new Error('풋콜 비율 없음');

        const contracts = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
        const asOf = signalAsOf(opts.bas_dd || kr.as_of);
        signalFixedState.kospi = {
            ...signalFixedState.kospi,
            value: ratio.toFixed(2),
            sub: `콜 ${contracts(opts.call_volume)} · 풋 ${contracts(opts.put_volume)} 계약`,
            foot: asOf ? `as of ${asOf} · KRX` : 'KRX',
            // Puts outnumbering calls is the state worth flagging.
            tone: ratio >= 1 ? 'warn' : null
        };
    } catch (e) {
        console.error('K200 풋콜 비율 로드 실패:', e);
        signalFixedState.kospi = {
            ...signalFixedState.kospi,
            value: '연동 예정', sub: 'KRX 파생 보드 없음', tone: 'muted'
        };
    }
    signalRenderFixed(signalFixedState);
};

// ---- wiring --------------------------------------------------------------

function initSignalPanel() {
    const stage = signalEls.stage();
    const rotator = signalEls.rotator();
    if (!stage || !rotator) return;

    signalRenderFixed(signalFixedState);
    signalShowPage(0, false);

    if (signalTimer) clearInterval(signalTimer);
    signalTimer = setInterval(signalTick, SIGNAL_ROTATE_MS);

    // Reading a slot should not be a race against the drum.
    rotator.addEventListener('mouseenter', () => { signalPaused = true; });
    rotator.addEventListener('mouseleave', () => { signalPaused = false; });
    rotator.addEventListener('focusin', () => { signalPaused = true; });
    rotator.addEventListener('focusout', () => { signalPaused = false; });

    const jump = (idx) => {
        signalShowPage(idx, true);
        // Restart the clock so a hand-picked page gets its full dwell.
        if (signalTimer) clearInterval(signalTimer);
        signalTimer = setInterval(signalTick, SIGNAL_ROTATE_MS);
    };

    signalEls.dots().addEventListener('click', (e) => {
        const dot = e.target.closest('.signal-dot');
        if (dot) jump(Number(dot.dataset.idx));
    });

    // Drag the page name to step by hand: right reveals the page to its
    // right (next), left reveals the page to its left (previous) -- the
    // same order the dots already walk. Delegated on `stage` because the
    // name node is rebuilt on every rotation (signalBuildPage), so a
    // listener bound to the element itself would be gone after one flip.
    const SIGNAL_SWIPE_PX = 32;
    let dragStartX = null;

    const onSignalDragMove = (e) => {
        // Dragging the name text would otherwise also select it or, on
        // touch, scroll the page horizontally.
        if (dragStartX !== null) e.preventDefault();
    };
    const onSignalDragEnd = (e) => {
        if (dragStartX === null) return;
        const endX = e.clientX ?? e.changedTouches?.[0]?.clientX ?? dragStartX;
        const deltaX = endX - dragStartX;
        dragStartX = null;
        window.removeEventListener('pointermove', onSignalDragMove);
        window.removeEventListener('pointerup', onSignalDragEnd);
        window.removeEventListener('pointercancel', onSignalDragEnd);
        if (deltaX >= SIGNAL_SWIPE_PX) jump(signalIndex + 1);
        else if (deltaX <= -SIGNAL_SWIPE_PX) jump(signalIndex - 1);
    };
    stage.addEventListener('pointerdown', (e) => {
        if (!e.target.closest('.signal-page-name')) return;
        dragStartX = e.clientX;
        // Bound to window, not the name element: the pointer regularly ends
        // up outside a small text label mid-drag, and the element itself may
        // be mid-flip-out by the time the gesture finishes.
        window.addEventListener('pointermove', onSignalDragMove, { passive: false });
        window.addEventListener('pointerup', onSignalDragEnd);
        window.addEventListener('pointercancel', onSignalDragEnd);
    });

    const openSlot = (slot) => {
        if (slot?.dataset.symbol) openChartModal(slot.dataset.label, slot.dataset.symbol, slot.dataset.ma === '1');
    };
    stage.addEventListener('click', (e) => openSlot(e.target.closest('.signal-slot.is-clickable')));
    stage.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const slot = e.target.closest('.signal-slot.is-clickable');
        if (!slot) return;
        e.preventDefault();
        openSlot(slot);
    });

    const followCard = (card) => {
        if (card?.dataset.target) setView(card.dataset.target);
    };
    signalEls.fixed().addEventListener('click', (e) => followCard(e.target.closest('.signal-fixed-card.is-clickable')));
    signalEls.fixed().addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const card = e.target.closest('.signal-fixed-card.is-clickable');
        if (!card) return;
        e.preventDefault();
        followCard(card);
    });

    // Both feeds are fetched without blocking first paint. The shipping snapshot
    // is ~1.1 MB, so it warms the same memoised promise the 해운 screens use
    // rather than being downloaded twice.
    signalLoadEnso();
    signalLoadChokepoints();
    signalLoadPutCall();
}

// Deck.GL Map Initialization
//
// No MapLibre raster basemap any more. Carto's dark tiles are flat Mercator
// images: MapLibre paints them on a plane, so every attempt at curvature ended
// up as either a tilted trapezoid (MapView + pitch) or a glass sphere floating
// over a flat world (GlobeView on top of tiles). The basemap is now drawn by
// deck itself -- a dark ocean rectangle, a graticule and country polygons -- on
// a flat MapView, which is what the mockup uses (d3.geoEquirectangular).
// Antarctica is dropped from the source data rather than covered with a strip.

// Home globe zoom. Higher = the sphere fills more of the viewport, so the
// horizon curve reads as a gentle bend rather than a small ball in space.
const GLOBE_ZOOM = 0.85;

let currentViewState = {
    longitude: 0,
    latitude: 20,
    zoom: GLOBE_ZOOM,
    pitch: 0,
    bearing: 0
};

let autoRotate = true;
let rotationAnimation = null;
let resumeRotationTimer = null;

// One animation frame of spin. Never call directly -- go through startRotation()
// so we can't end up with several chains running at once.
const rotationStep = () => {
    if (!autoRotate || currentCommodity !== 'home') {
        rotationAnimation = null;
        return;
    }
    currentViewState = {
        ...currentViewState,
        longitude: currentViewState.longitude + 0.05 // 서서히 자전
    };
    deckgl.setProps({ viewState: currentViewState });
    rotationAnimation = requestAnimationFrame(rotationStep);
};

const startRotation = () => {
    // Bail if a chain is already live. onViewStateChange fires on every frame of
    // a drag, so without this one drag would spawn dozens of parallel loops and
    // the globe would spin faster and faster.
    if (rotationAnimation !== null) return;
    autoRotate = true;
    rotationAnimation = requestAnimationFrame(rotationStep);
};

const stopRotation = () => {
    autoRotate = false;
    if (rotationAnimation !== null) {
        cancelAnimationFrame(rotationAnimation);
        rotationAnimation = null;
    }
};

// Initialize DeckGL Map
const deckgl = new DeckGL({
    container: 'map',
    initialViewState: currentViewState,
    controller: true,
    views: [new MapView({ id: 'map', repeat: true })], // Flat equirectangular, as the mockup
    layers: [],
    onViewStateChange: ({ viewState, interactionState }) => {
        currentViewState = viewState;
        // Avoid stomping climate MapView while interacting on other screens only
        if (currentCommodity === 'climate') {
            // Still track; controller needs viewState updates for pan/zoom
            deckgl.setProps({ viewState });
            return;
        }
        deckgl.setProps({ viewState: currentViewState });

        // 드래그로 지구를 직접 잡고 있을 때만 회전 멈춤.
        // Zooming is deliberately excluded: scrolling to resize the globe should
        // not stop the spin, and rotationStep preserves whatever zoom the user
        // lands on. Debounced -- this fires once per interaction frame, so
        // re-arm a single timer instead of queueing one per frame.
        if (interactionState.isDragging) {
            stopRotation();
            clearTimeout(resumeRotationTimer);
            resumeRotationTimer = setTimeout(() => {
                if (currentCommodity === 'home') startRotation();
            }, 2000);
        }
    }
});

// The home and climate maps draw once, so a basemap that arrives after that
// first paint would sit invisible until the next interaction. Redraw on arrival.
const redrawOnBasemapReady = () => {
    loadWorldGeo().then(() => {
        if (typeof deckgl === 'undefined' || !deckgl) return;
        const layers = deckgl.props.layers || [];
        if (layers.length) deckgl.setProps({ layers: [...layers] });
    });
};

// Deferred: loadWorldGeo is declared further down, so calling it here at
// module-evaluation time would hit the temporal dead zone.
queueMicrotask(redrawOnBasemapReady);

// Tooltip handler
const handleHover = (info) => {
    if (info.object) {
        const { sourceName, targetName, volume, percentage } = info.object;
        positionTooltipAt(info, 0);
        tooltipEl.classList.remove('hidden');
        
        tooltipEl.innerHTML = `
            <div class="tooltip-title">${sourceName} → ${targetName}</div>
            <div class="tooltip-stat">
                <span>무역량:</span>
                <span style="color: #38bdf8; font-weight: bold;">${volume} ${currentCommodity === 'oil' ? 'M bpd' : (currentCommodity === 'gold' || currentCommodity === 'silver' ? 'Tonnes' : 'Mt')}</span>
            </div>
            ${info.object.typeName !== "General" ? `
            <div class="tooltip-stat">
                <span>분류:</span>
                <span>${info.object.typeName}</span>
            </div>` : ''}
            <div class="tooltip-stat">
                <span>비중/상대규모:</span>
                <span>${percentage}%</span>
            </div>
        `;
    } else {
        tooltipEl.classList.add('hidden');
    }
};

const handleNodeClick = (info) => {
    if (info.object) {
        selectedCountry = info.object.name;
        if (currentCommodity === 'climate') {
            updateForecastPanel(selectedCountry).catch(err =>
                console.error('[Forecast] panel update failed', err));
        } else {
            focusTradeCountry(selectedCountry);
        }
    }
};

const handleLineClick = (info) => {
    if (info.object) {
        selectedCountry = info.object.sourceName;
        if (currentCommodity === 'climate') {
            updateForecastPanel(selectedCountry).catch(err =>
                console.error('[Forecast] panel update failed', err));
        } else {
            focusTradeCountry(selectedCountry);
        }
    }
};

// Kept for any legacy callers; trade UI no longer opens the right stats column.
const updateCountryStatsPanel = async (countryName) => {
    focusTradeCountry(countryName);
};

/**
 * Default commodity view: who ships the most, with a bar for scale.
 *
 * The left column used to open on news alone, which said nothing about the map
 * beside it. The mockup's reading order is structure first -- the ranking
 * explains the thick lines you are looking at -- so news moves below it.
 */
/**
 * Three-letter code for a rank row.
 *
 * The trade panel is a ranking, not prose: "United States of America" pushes
 * the bar out of the row while ISO codes line up and stay scannable. The crop
 * monitor keeps full names -- it reads as a country workspace, not a league
 * table.
 */
// Static ISO3 fallback for the reporter/partner names Comtrade uses most.
// resolveCountry needs the world GeoJSON in memory; when the trade panel
// renders before that fetch resolves, every unresolved name fell back to its
// first three letters, so "United States" and "United Arab Emirates" both
// showed as "UNI". This table keeps the code correct regardless of load order.
const ISO3_FALLBACK = {
    'united states': 'USA', 'usa': 'USA', 'us': 'USA', 'america': 'USA',
    'united arab emirates': 'ARE', 'uae': 'ARE',
    'united kingdom': 'GBR', 'uk': 'GBR', 'great britain': 'GBR',
    'south korea': 'KOR', 'korea rep': 'KOR', 'republic of korea': 'KOR',
    'north korea': 'PRK',
    'russia': 'RUS', 'russian federation': 'RUS',
    'china': 'CHN',
    'south africa': 'ZAF',
    'saudi arabia': 'SAU',
    'ivory coast': 'CIV', 'cote d ivoire': 'CIV',
    'democratic republic of the congo': 'COD',
    'republic of the congo': 'COG',
};

const countryCode = (name) => {
    const r = resolveCountry(name);
    if (r?.iso) return r.iso;
    const fallback = ISO3_FALLBACK[normCountryName(name)];
    if (fallback) return fallback;
    return String(name || '').slice(0, 3).toUpperCase();
};

/**
 * Supply concentration for one country's trade in one commodity.
 *
 * CR3 and HHI over whichever direction actually carries the dependency: for a
 * buyer, who it buys from; for a pure seller, who it sells to. Herfindahl fits
 * without stretching -- Hirschman published it in 1945 to measure how
 * concentrated a nation's trade was, and antitrust borrowed it afterwards.
 *
 * Labelled 집중도 and not 위험 on purpose. Concentration is half of supply risk:
 * three suppliers who are all allies is not the exposure that one supplier who
 * is not would be, which is why the EU multiplies its HHI by a governance
 * score. That weighting needs World Bank WGI data this page does not carry, so
 * the card reports what it can actually measure and says which half that is.
 */
const concentrationHtml = (arcs, partnerOf, dirKo) => {
    const byPartner = new Map();
    for (const a of arcs) {
        if (!(a.volume > 0)) continue;
        const p = partnerOf(a);
        byPartner.set(p, (byPartner.get(p) || 0) + a.volume);
    }
    const total = [...byPartner.values()].reduce((s, v) => s + v, 0);
    // Two partners cannot say anything about concentration that the ranking
    // below does not already show.
    if (byPartner.size < 3 || total <= 0) return '';

    const ranked = [...byPartner.entries()].sort((x, y) => y[1] - x[1]);
    const hhi = ranked.reduce((s, [, v]) => s + (v / total) ** 2, 0);
    const cr3 = ranked.slice(0, 3).reduce((s, [, v]) => s + v, 0) / total;

    // The 0.15 / 0.25 cutoffs are the ones competition authorities use, and the
    // EU's raw-materials assessment carries them over to supplier countries.
    const band = hhi >= 0.25 ? { ko: '높음', cls: 'hi' }
        : hhi >= 0.15 ? { ko: '보통', cls: 'mid' }
            : { ko: '낮음', cls: 'lo' };
    const top3 = ranked.slice(0, 3)
        .map(([p, v]) => `${countryCode(p)} ${((v / total) * 100).toFixed(1)}`)
        .join(' · ');

    return `
        <div class="dep-card">
            <div class="dep-head">
                <strong>${dirKo} 집중도</strong>
                <span class="dep-band dep-${band.cls}">${band.ko}</span>
            </div>
            <div class="dep-metrics">
                <div class="dep-m"><span class="dep-k">CR3</span>
                    <span class="dep-v">${(cr3 * 100).toFixed(1)}%</span></div>
                <div class="dep-m"><span class="dep-k">HHI</span>
                    <span class="dep-v">${hhi.toFixed(3)}</span></div>
            </div>
            <p class="dep-top">${top3}</p>
            <p class="dep-note">상위 3개국 비중과 허핀달 지수. 공급국의 정치적 신뢰도는
                반영하지 않은 순수 집중도다.</p>
        </div>`;
};

const updateNewsPanel = (countryName) => {
    if (!currentCommodity || !window.TradeData[currentCommodity]) return;
    
    const commodityNews = window.TradeData[currentCommodity].news;
    const newsData = commodityNews[countryName] || commodityNews['default'];
    
    if (!newsData || newsData.length === 0) {
        newsContentEl.innerHTML = `<p class="empty-state">해당 지역의 최근 뉴스가 없습니다.</p>`;
        return;
    }
    
    document.querySelector('#news-panel .section-title').textContent = `주요 지역 뉴스: ${countryName}`;
    
    newsContentEl.innerHTML = newsData.map(news => `
        <a href="${news.url}" target="_blank" rel="noopener noreferrer" class="news-item">
            <div class="news-title">${news.title}</div>
            <div class="news-meta">
                <span>${news.source}</span>
                <span>${news.date}</span>
            </div>
        </a>
    `).join('');
};

// Renders the statistical yield forecast for the US Corn Belt.
// Kept separate from the hardcoded forecastData panels: these numbers come
// from a model fitted on 33 seasons of NASA POWER weather and USDA NASS
// yields, so the panel also shows how much of the season is actually
// observed and how the model scored out of sample.
const US_REGION_KEYS = {
    'US Corn Belt': 'corn_belt',
    'US Great Plains': 'great_plains',
    'US Northern Plains': 'northern_plains',
    'US Cotton Belt': 'cotton_belt',
};

// Why each region's model is shaped the way it is, and which finding drove it.
// Written per region rather than once for the country: the three share a
// skeleton (trend + weather anomaly + ridge) but differ in the physics that
// actually moves yield, and a single blurb would hide that.
const US_REGION_METHOD = {
    corn_belt: {
        headline: '추세수확량 + 기상편차 회귀',
        refs: 'Thompson (1969, 1986) · Schlenker & Roberts (2009) · Lobell / Urban / Roberts',
        notes: [
            '추세가 품종·비료·경영 개선을 흡수하고, 기상은 추세로부터의 편차만 설명합니다 (FAO 작황예측 리뷰).',
            '고온은 일수 카운트가 아니라 임계 초과분 적산(EDD)으로 넣습니다 — 손상이 비선형이기 때문입니다 (옥수수 −8.2%/°C, 대두 −5.7%/°C).',
            'VPD로 고온·건조 복합 스트레스를, 파종전 강수(9~6월)로 토양수분 충전을 봅니다.',
        ],
        finding: '데이터가 뽑아낸 상위 변수(7월 기온 r=−0.635, 7월 EDD −0.632, VPD −0.536)가 '
               + '40년 전 논문이 지목한 시기·변수와 그대로 일치했습니다.',
    },
    great_plains: {
        headline: '추세수확량 + 기상편차 회귀 (겨울밀)',
        refs: 'Kansas State (hot-dry-windy) · 대평원 겨울밀 모델링 가이드',
        notes: [
            '가을 파종 → 월동 → 초여름 수확. 생육창이 해를 넘기므로 전년 9월부터 봅니다.',
            '반건조 지대라 물이 지배합니다: 봄철 토양수분(r=+0.732), 겨울 토양수분(+0.654), 봄 강수(+0.565).',
        ],
        finding: '참고 가이드가 강조한 춘화처리·동해·서리 패널티는 신호가 없었습니다 '
               + '(r=+0.020 / −0.104 / −0.071). 서리 최다 3개년 중 2019년은 오히려 증수라 방향도 '
               + '엇갈립니다. 공식대로 구현했으나 이 지역·이 기간에서는 지배 요인이 아니었습니다.',
    },
    cotton_belt: {
        headline: '추세수확량 + 기상편차 회귀 (면화, 파종면적 기준)',
        refs: 'Pettigrew (2004), Agronomy Journal · Scanlon et al. (2012), PNAS',
        notes: [
            '개화~꼬투리 충실기(7~9월) 수분이 꼬투리 수를 결정합니다. 면화는 고온 내성이 높아 EDD 임계를 32°C로 잡았습니다.',
            '텍사스 하이플레인스는 오갈라라 대수층 관개 의존도가 높아, 파종 전(11~4월) 토양수분 충전이 함께 들어갑니다.',
        ],
        finding: '수확면적이 아니라 파종면적 기준으로 단수를 계산했습니다. 텍사스 수확포기율이 '
               + '연도별 4~75%로 요동치는데, 가뭄해에 농민이 망한 밭을 갈아엎으면 살아남은 '
               + '관개 밭만 측정돼 단수가 오히려 높게 찍힙니다(2022년 포기율 74.5%인데 단수 734 lb/ac로 '
               + '평년 이상). 파종면적 기준으로 바꾸니 변동계수가 10.0%→37.1%로 커지고 최악 3개년이 '
               + '2022·2011·2023 — 실제 텍사스 가뭄해와 일치합니다.',
    },
    northern_plains: {
        headline: '추세수확량 + 기상편차 회귀 (봄밀, 20년 이동창)',
        refs: 'Lanning et al. (2010), Crop Science',
        notes: [
            '봄 파종 → 늦여름 수확. 생육창이 짧아 개화기가 한여름 폭염과 겹칩니다.',
            '밀은 옥수수보다 고온에 취약해 EDD 임계를 28°C로 낮춰 잡았습니다.',
        ],
        finding: '고정 계수로는 추세만 쓰는 것보다 나빴습니다(−1.0%). 봄밀이 조기 파종·조기출수 '
               + '품종으로 7월 더위를 회피하도록 적응해와서, "고온→감수" 관계 자체가 약해졌기 '
               + '때문입니다. 최근 20년만 재적합해 +13.4%로 돌렸습니다 — 다만 여전히 낮습니다.',
    },
};

const renderYieldForecast = async (regionName) => {
    const regionKey = US_REGION_KEYS[regionName];
    if (!regionKey) return false;

    const fc = await window.loadYieldForecast?.();
    if (!fc || !fc.regions || !fc.regions[regionKey]) return false;

    const region = fc.regions[regionKey];
    const method = US_REGION_METHOD[regionKey] || US_REGION_METHOD.corn_belt;
    let html = '';

    for (const [crop, d] of Object.entries(region.crops)) {
        const vsLast = d.point - d.last_actual.yield;
        const color = d.weather_effect < 0 ? '#fca5a5' : '#4ade80';
        const pct = Math.round(d.season_progress.observed_share * 100);

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header">
                <span class="ind-title">${d.label_ko || crop}</span>
                ${d.skill.low_confidence ? `<span style="font-size:10px; padding:2px 6px;
                   border-radius:4px; background:rgba(251,191,36,0.15); color:#fbbf24;">신뢰도 낮음</span>` : ''}
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${d.last_actual.year} 실적</span>
                    <div style="font-size:15px;">${d.last_actual.yield.toFixed(1)} ${d.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${color};">${d.point} ${d.unit}</div>
                </div>
            </div>
            <div style="text-align:right; font-size:13px; margin-top:4px; color:${vsLast >= 0 ? '#4ade80' : '#fca5a5'};">
                전년 대비 ${vsLast >= 0 ? '+' : ''}${vsLast.toFixed(1)} ${d.unit}
            </div>
            <div style="margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.1); font-size:12px;">
                <div style="display:flex; justify-content:space-between; color:#cbd5e1;">
                    <span>68% 신뢰구간</span><span>${d.range_68[0]} – ${d.range_68[1]}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:2px;">
                    <span>95% 신뢰구간</span><span>${d.range_95[0]} – ${d.range_95[1]}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>기술 추세</span><span>${d.trend} ${d.unit}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:${color}; margin-top:2px;">
                    <span>기상 효과</span><span>${d.weather_effect >= 0 ? '+' : ''}${d.weather_effect}</span>
                </div>
            </div>
            <div style="margin-top:10px; padding:8px; background:rgba(0,0,0,0.2); border-radius:6px; font-size:11px; color:#94a3b8;">
                생육 결정기 관측률 <strong style="color:#cbd5e1;">${pct}%</strong>
                (나머지는 예보·평년값)<br>
                모델 검증: 추세 대비 오차 <strong style="color:#cbd5e1;">${(d.skill.skill_vs_trend_only * 100).toFixed(0)}%</strong> 감소,
                학습 ${d.trained_years[0]}–${d.trained_years[1]}${d.skill.train_window_years ? ` · 최근 ${d.skill.train_window_years}년 이동창` : ''}
            </div>
        </div>`;
    }

    const enso = fc.enso.oni_growing_season;
    forecastCountryTitle.textContent = `${region.label_ko} 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        ${climateNavBackHtml(region.label_ko || '')}
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">엘니뇨/라니냐 (ONI)</span>
                <span class="forecast-val">${enso === null ? 'N/A' : enso.toFixed(2)} · ${fc.enso.state}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:11px;">${region.note}</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>${method.headline}</strong><br>
                <span style="font-size:11px; font-weight:400;">
                기술 추세가 품종·비료·경영 개선을 흡수하고, 기상은 추세로부터의 편차를 설명합니다.
                </span>
            </div>
        </div>

        <div style="margin-top:14px; padding:10px; background:rgba(0,0,0,0.2); border-radius:6px;">
            <div style="font-size:11px; color:#94a3b8; margin-bottom:6px;">모델 설계 근거</div>
            <div style="font-size:11px; color:#64748b; margin-bottom:8px;">${method.refs}</div>
            <ul style="margin:0; padding-left:16px; font-size:11px; color:#cbd5e1; line-height:1.7;">
                ${method.notes.map(n => `<li>${n}</li>`).join('')}
            </ul>
            <div style="margin-top:10px; padding-top:8px; border-top:1px dashed rgba(255,255,255,0.1);
                        font-size:11px; color:#94a3b8; line-height:1.7;">
                <strong style="color:#cbd5e1;">검증에서 확인된 것</strong><br>${method.finding}
            </div>
        </div>

        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-top:10px; margin-bottom:4px;">
            갱신: ${new Date(fc.generated_at).toLocaleString()}
        </p>
        <p style="font-size:11px; color:#64748b; text-align:right;">
            출처: USDA NASS(수확량) · NASA POWER(기상) · NOAA CPC(ONI) · Open-Meteo(예보)
        </p>`;

    countryStatsTitleEl.textContent = region.label_ko;
    document.getElementById('country-stats-desc').textContent = method.refs;
    countryStatsContentEl.innerHTML = html;
    panelHide(macroPanelEl);
    panelShow(countryStatsPanelEl);
    return true;
};

// Which model keys belong to each clickable Brazilian region on the map.
// One region shows several crops because the models are built per region-crop:
// Mato Grosso soy and safrinha corn are separate methodologies over the same
// ground, and the southern states carry three crops on one weather history.
// === Climate view: country -> producing region drill-down ===
//
// The climate map is two levels. Level 1 shows the world with modelled
// countries outlined; level 2 zooms into one country and marks its producing
// regions. Only countries that actually have a fitted model appear -- putting
// a marker on a country with no model would imply a forecast that does not
// exist.
// Fetched once and shared by both climate levels; deck.gl caches the parsed
// result per URL, so repeating it across layers costs nothing.
const COUNTRIES_GEOJSON =
    'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json';

// === Country registry (generated, not hand-written) =======================
//
// These two used to be object literals holding every modelled country. Adding a
// country meant editing this file, so two terminals adding two countries edited
// the same lines -- which is how a session's UI work was lost on 2026-08-05.
//
// They are now filled from public/data/climate_registry_v1.json, which CI builds
// from scripts/yield_model/*/model.yaml. A country lands entirely inside its own
// folder and never touches app.js.
//
// Deliberately `let` and initially empty: nothing renders the climate view
// before loadClimateRegistry() resolves, and an empty object renders an empty
// map rather than throwing.
let CLIMATE_COUNTRIES = {};
let CLIMATE_TRADE_POLICY = {};

const CLIMATE_REGISTRY_URL = '/public/data/climate_registry_v1.json';
let climateRegistryPromise = null;

/**
 * Registry entry -> the shape the rest of app.js already speaks.
 *
 * The manifest is written for whoever trains the model (snake_case, region keys
 * that match the forecast JSON); the UI grew up with camelCase and a `name`
 * per region. Translating here keeps both sides readable instead of forcing
 * either to adopt the other's vocabulary.
 */
const adaptRegistryCountry = (entry) => ({
    label: entry.label_ko || entry.label_en,
    modelName: entry.model_name || null,
    iso: entry.iso,
    panelMode: entry.panel_mode,
    aliases: entry.aliases || undefined,
    dataFile: entry.data_file,
    view: entry.view,
    // How much the numbers have earned. Surfaced as a badge so a country whose
    // regions all score worse than a trend baseline does not read as settled.
    modelStatus: entry.model_status || null,
    statusNote: entry.status_note_ko || null,
    sources: entry.sources || null,
    regions: (entry.regions || []).map((r) => ({
        name: r.ui_name || r.key,
        label: r.label_ko || r.key,
        coordinates: r.coordinates,
        regionKeys: r.crops_region_keys && r.crops_region_keys.length
            ? r.crops_region_keys
            : (r.key ? [r.key] : []),
    })),
});

const adaptRegistryPolicy = (entry) => {
    const p = entry.trade_policy || {};
    return {
        restricted: !!p.restricted,
        prohibitedCrops: p.prohibited_crops || [],
        note: p.note_ko || '',
    };
};

/** Fetch once; every caller shares the same promise. */
const loadClimateRegistry = () => {
    if (climateRegistryPromise) return climateRegistryPromise;
    climateRegistryPromise = fetch(CLIMATE_REGISTRY_URL, { cache: 'no-cache' })
        .then((res) => {
            if (!res.ok) throw new Error(`registry ${res.status}`);
            return res.json();
        })
        .then((doc) => {
            const countries = {};
            const policy = {};
            for (const [name, entry] of Object.entries(doc.countries || {})) {
                countries[name] = adaptRegistryCountry(entry);
                policy[name] = adaptRegistryPolicy(entry);
            }
            CLIMATE_COUNTRIES = countries;
            CLIMATE_TRADE_POLICY = policy;
            console.log(`[Climate] registry: ${Object.keys(countries).length} countries`);
            return doc;
        })
        .catch((err) => {
            // An empty climate map is a visible, honest failure. Falling back to
            // a stale hardcoded list would quietly show countries that no longer
            // match what the pipelines produce.
            console.error('[Climate] registry load failed — climate view will be empty', err);
            return null;
        });
    return climateRegistryPromise;
};


const TRADE_FILL = {
    // Softened fills — vivid pills were competing with the basemap / SST wash.
    blue:   [56, 189, 248, 72],
    yellow: [250, 204, 21, 78],
    orange: [251, 146, 60, 82],
    red:    [248, 113, 113, 88],
    none:   [30, 41, 59, 28],
};
const TRADE_LINE = {
    blue:   [125, 211, 252, 140],
    yellow: [253, 224, 71, 145],
    orange: [253, 186, 116, 145],
    red:    [252, 165, 165, 150],
    none:   [255, 255, 255, 18],
};

const isAntarcticaFeature = (feature) => {
    if (!feature) return false;
    const id = String(feature.id ?? feature.properties?.id ?? feature.properties?.ISO_A3 ?? '').toUpperCase();
    const name = String(feature.properties?.name || feature.properties?.NAME || '');
    return id === 'ATA' || /antarctica|남극/i.test(name);
};

// === World basemap (flat equirectangular, drawn by deck) ===================
//
// Antarctica is dropped from the source features instead of hidden under an
// opaque strip (req 12). The strip only ever existed to cover Carto's raster
// tiles; with our own vector basemap the continent does not exist at all, so
// no mask polygon floats over the sphere at low zoom.
let worldGeoPromise = null;
let worldGeoData = null;
const loadWorldGeo = () => {
    if (!worldGeoPromise) {
        worldGeoPromise = fetch(COUNTRIES_GEOJSON)
            .then((r) => r.json())
            .then((g) => {
                worldGeoData = {
                    type: 'FeatureCollection',
                    features: (g.features || []).filter((f) => !isAntarcticaFeature(f)),
                };
                return worldGeoData;
            })
            .catch((err) => {
                console.error('[Map] world geojson load failed', err);
                worldGeoData = { type: 'FeatureCollection', features: [] };
                return worldGeoData;
            });
    }
    return worldGeoPromise;
};

/**
 * Basemap `data` prop. Returns the parsed collection once it is in memory and
 * the pending promise before that.
 *
 * This matters because the trade map rebuilds its layers on every animation
 * frame: a fresh Promise each time means each new GeoJsonLayer starts loading
 * from zero and is discarded before it resolves, so the land never appears.
 * A stable object reference diffs as unchanged and draws immediately.
 */
const worldGeo = () => worldGeoData || loadWorldGeo();

// Dark-basemap palette, matched to the old carto dark_all so dropping raster
// tiles is not a visual break.
const OCEAN_RGBA = [9, 15, 27, 255];
const LAND_RGBA = [43, 52, 66, 255];
const LAND_LINE_RGBA = [128, 148, 176, 120];

// Earth radius in metres, for the sphere mesh that backs the globe.
const EARTH_RADIUS_M = 6370000;

/**
 * Ocean sphere + country polygons. Home, trade and climate all build on this so
 * the three screens share one basemap identity (req 2).
 */
// Flat equirectangular basemap, matching the mockup.
//
// This was a sphere for a while. The brief asked for "약간의 곡률" -- slight
// curvature -- and a globe is not that; the mockup uses d3.geoEquirectangular,
// a flat projection, and gets its depth from a graticule plus arcs that bow.
// The sphere also cost more than it looked: deck 9.3.7's _GlobeView draws no
// ArcLayer, LineLayer, TextLayer or IconLayer, so every one of those needed a
// hand-built substitute. Flat MapView draws them all.
const oceanRect = (id = 'base') => new SolidPolygonLayer({
    id: `${id}-ocean`,
    data: [[[-180, -85], [180, -85], [180, 85], [-180, 85]]],
    getPolygon: (d) => d,
    stroked: false,
    filled: true,
    pickable: false,
    getFillColor: OCEAN_RGBA,
});

// Graticule every 20 degrees. This is what reads as curvature on a flat map:
// meridians converging toward the poles give the plane a globe's geometry
// without pretending to be one.
const GRATICULE_PATHS = (() => {
    const out = [];
    for (let lon = -180; lon <= 180; lon += 20) {
        const line = [];
        for (let lat = -80; lat <= 80; lat += 5) line.push([lon, lat]);
        out.push(line);
    }
    for (let lat = -80; lat <= 80; lat += 20) {
        const line = [];
        for (let lon = -180; lon <= 180; lon += 5) line.push([lon, lat]);
        out.push(line);
    }
    return out;
})();

const graticuleLayer = (id = 'base') => new PathLayer({
    id: `${id}-graticule`,
    data: GRATICULE_PATHS,
    getPath: (d) => d,
    getColor: [255, 255, 255, 13],
    getWidth: 1,
    widthUnits: 'pixels',
    pickable: false,
});

const landLayer = ({
    id = 'base',
    landColor = LAND_RGBA,
    lineColor = LAND_LINE_RGBA,
    lineWidth = 0.6,
} = {}) => new GeoJsonLayer({
    id: `${id}-land`,
    data: worldGeo(),
    stroked: true,
    filled: true,
    pickable: false,
    lineWidthMinPixels: lineWidth,
    getFillColor: landColor,
    getLineColor: lineColor,
});

/**
 * Ocean, graticule and land, with an optional `water` slot between water and
 * coastline.
 *
 * The slot exists for the SST wash: drawn on top of the land it painted over
 * Argentina and smeared a basin-sized blob across Africa. It belongs on the
 * water, under the coastlines.
 */
const worldBaseLayers = ({ water = [], ...opts } = {}) => [
    oceanRect(opts.id || 'base'),
    ...water,
    graticuleLayer(opts.id || 'base'),
    landLayer(opts),
];


// === Country registry =====================================================
//
// Every country on the basemap is addressable without being listed anywhere by
// hand. Identity and centroid come from the world GeoJSON, so trade data that
// arrives later -- a new commodity, a wider Comtrade pull, a country we have
// never rendered before -- is clickable the moment it appears in the arcs.
//
// window.CountriesData stays as an override, not a gate: it holds nicer
// hand-placed points and covers three places the basemap does not carry as
// separate features (Hong Kong, Singapore, Taiwan).

/** Lowercase, strip punctuation/diacritics, collapse whitespace. */
const normCountryName = (s) => String(s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

// Short names and official long names that do not normalise onto the basemap's
// own label. Left side is what the data may call it, right side is the
// GeoJSON `properties.name`.
const COUNTRY_ALIASES = {
    'usa': 'United States of America',
    'us': 'United States of America',
    'united states': 'United States of America',
    'america': 'United States of America',
    'uk': 'United Kingdom',
    'great britain': 'United Kingdom',
    'england': 'United Kingdom',
    'russian federation': 'Russia',
    'korea rep': 'South Korea',
    'republic of korea': 'South Korea',
    'korea south': 'South Korea',
    'dem peoples rep of korea': 'North Korea',
    'korea north': 'North Korea',
    'iran islamic republic of': 'Iran',
    'iran islamic rep': 'Iran',
    'viet nam': 'Vietnam',
    'syrian arab republic': 'Syria',
    'lao peoples dem rep': 'Laos',
    'lao pdr': 'Laos',
    'united republic of tanzania': 'Tanzania',
    'bolivia plurinational state of': 'Bolivia',
    'venezuela bolivarian rep of': 'Venezuela',
    'republic of moldova': 'Moldova',
    'czechia': 'Czech Republic',
    'cote d ivoire': 'Ivory Coast',
    'cote divoire': 'Ivory Coast',
    'congo dr': 'Democratic Republic of the Congo',
    'dr congo': 'Democratic Republic of the Congo',
    'congo dem rep': 'Democratic Republic of the Congo',
    'democratic republic of congo': 'Democratic Republic of the Congo',
    'congo rep': 'Republic of the Congo',
    'burma': 'Myanmar',
    'uae': 'United Arab Emirates',
    'north macedonia': 'Macedonia',
    'eswatini': 'Swaziland',
    'brunei darussalam': 'Brunei',
    'cabo verde': 'Cape Verde',
    'turkiye': 'Turkey',
    'netherlands kingdom of the': 'Netherlands',
    'china hong kong sar': 'Hong Kong',
    'china macao sar': 'Macau',
    'other asia nes': 'Taiwan',
};

/**
 * Area-weighted centroid of a feature's largest ring.
 *
 * Largest ring rather than all rings: averaging every polygon would drag the
 * United States out into the Pacific between the mainland and Alaska, and put
 * Indonesia's marker in open water.
 */
const featureCentroid = (feature) => {
    const geom = feature?.geometry;
    if (!geom) return null;
    const polys = geom.type === 'Polygon' ? [geom.coordinates]
        : geom.type === 'MultiPolygon' ? geom.coordinates
        : [];
    let best = null;
    let bestArea = -1;
    for (const poly of polys) {
        const ring = poly[0];
        if (!ring || ring.length < 3) continue;
        let a = 0;
        let cx = 0;
        let cy = 0;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const cross = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
            a += cross;
            cx += (ring[j][0] + ring[i][0]) * cross;
            cy += (ring[j][1] + ring[i][1]) * cross;
        }
        a *= 0.5;
        const abs = Math.abs(a);
        if (abs < 1e-9 || abs <= bestArea) continue;
        bestArea = abs;
        best = [cx / (6 * a), cy / (6 * a)];
    }
    return best;
};

// Trading places the world basemap has no polygon for, because they are too
// small to survive its simplification. Without these a Singapore or Bahrain
// route resolves to nothing and disappears from the map.
const SUPPLEMENTAL_POINTS = {
    // [lon, lat, ISO3]. The code matters: rank rows show it, and without one
    // the fallback takes the first three letters, which turned Hong Kong into
    // "HON" instead of HKG.
    'Singapore': [103.82, 1.35, 'SGP'],
    'Hong Kong': [114.17, 22.32, 'HKG'],
    'Macau': [113.55, 22.20, 'MAC'],
    'Taiwan': [120.96, 23.70, 'TWN'],
    'Bahrain': [50.55, 26.07, 'BHR'],
    'Malta': [14.40, 35.90, 'MLT'],
    'Trinidad and Tobago': [-61.25, 10.70, 'TTO'],
    'Mauritius': [57.55, -20.35, 'MUS'],
    'Cape Verde': [-23.60, 15.10, 'CPV'],
    'Maldives': [73.50, 3.20, 'MDV'],
    'Barbados': [-59.55, 13.19, 'BRB'],
    'Bahamas': [-77.40, 24.25, 'BHS'],
    'Seychelles': [55.50, -4.60, 'SYC'],
    'Comoros': [43.35, -11.65, 'COM'],
    'Sao Tome and Principe': [6.61, 0.19, 'STP'],
};

let countryIndex = null;
const buildCountryIndex = (geo) => {
    const byKey = new Map();
    const records = [];
    const put = (k, rec) => {
        const n = normCountryName(k);
        if (n && !byKey.has(n)) byKey.set(n, rec);
    };
    for (const f of geo?.features || []) {
        const name = f.properties?.name || f.properties?.NAME;
        if (!name) continue;
        const iso = String(f.id ?? f.properties?.id ?? '').toUpperCase();
        const rec = { key: name, label: name, iso, coordinates: featureCentroid(f) };
        if (!rec.coordinates) continue;
        records.push(rec);
        put(name, rec);
        if (iso) put(iso, rec);
    }
    for (const [alias, target] of Object.entries(COUNTRY_ALIASES)) {
        const rec = byKey.get(normCountryName(target));
        if (rec) put(alias, rec);
    }
    // Curated points win on placement, and carry entries the basemap has no
    // separate feature for.
    for (const [name, coords] of Object.entries({
        ...SUPPLEMENTAL_POINTS,
        ...(window.CountriesData || {}),
    })) {
        if (!Array.isArray(coords)) continue;
        const n = normCountryName(name);
        const iso = SUPPLEMENTAL_POINTS[name]?.[2] || '';
        const existing = byKey.get(n);
        if (existing) {
            existing.coordinates = coords.slice(0, 2);
            existing.aliasOf = existing.key;
            if (!existing.iso && iso) existing.iso = iso;
            byKey.set(n, existing);
        } else {
            const rec = { key: name, label: name, iso, coordinates: coords.slice(0, 2) };
            records.push(rec);
            byKey.set(n, rec);
            if (iso) put(iso, rec);
        }
    }
    return { byKey, records };
};

const countryRegistry = () => {
    if (!countryIndex && worldGeoData) countryIndex = buildCountryIndex(worldGeoData);
    return countryIndex;
};

/**
 * Resolve any spelling of a country to one record with coordinates.
 * Returns null only when the name matches nothing on the map at all.
 */
const resolveCountry = (name) => {
    if (!name) return null;
    const reg = countryRegistry();
    const n = normCountryName(name);
    const direct = window.CountriesData?.[name];
    if (!reg) {
        return direct ? { key: name, label: name, iso: '', coordinates: direct } : null;
    }
    const hit = reg.byKey.get(n) || reg.byKey.get(normCountryName(COUNTRY_ALIASES[n] || ''));
    if (hit) return hit;
    // Last resort: unique containment, so "Korea, Rep." style labels still land.
    const partial = reg.records.filter((r) => {
        const rn = normCountryName(r.key);
        return rn.includes(n) || n.includes(rn);
    });
    if (partial.length === 1) return partial[0];
    return direct ? { key: name, label: name, iso: '', coordinates: direct } : null;
};

/** Coordinates for a country name, or null. Used for node/arc placement. */
const countryCoords = (name) => resolveCountry(name)?.coordinates || null;

/** Canonical country name for a GeoJSON feature, or ''. */
const featureCountryName = (feature) => {
    const n = feature?.properties?.name || feature?.properties?.NAME;
    return n ? (resolveCountry(n)?.key || n) : '';
};

/** True when a GeoJSON feature is the same country as `name`. */
const featureIsCountry = (feature, name) => {
    if (!feature || !name) return false;
    const target = resolveCountry(name);
    if (!target) return false;
    const fname = feature.properties?.name || feature.properties?.NAME;
    const fiso = String(feature.id ?? feature.properties?.id ?? '').toUpperCase();
    if (target.iso && fiso && target.iso === fiso) return true;
    return normCountryName(fname) === normCountryName(target.key);
};

// data.js builds arcs before app.js has a chance to; expose the resolver so it
// can place countries the curated table never listed.
window.ResolveCountry = resolveCountry;
window.CountryCoords = countryCoords;

// Admin-1 boundaries (states, provinces, oblasts) for the country drill-down.
//
// A country outline alone gives nothing to locate a producing region against.
// Served per country from public/data/admin1/{ISO}.json, cut at build time by
// scripts/build_admin1.py -- the full 10m Natural Earth file is 39MB and the
// 50m one covers only nine countries.
const admin1Cache = new Map();

const loadAdmin1 = (iso) => {
    const key = String(iso || '').toUpperCase();
    if (!key) return Promise.resolve(null);
    if (admin1Cache.has(key)) return admin1Cache.get(key);
    const req = fetch(`/public/data/admin1/${key}.json`, { cache: 'force-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .catch((err) => {
            // The country still renders with its outline; internal borders are
            // an aid, not a dependency.
            console.warn(`[Climate] admin-1 unavailable for ${key}`, err);
            return null;
        });
    admin1Cache.set(key, req);
    return req;
};

/** Internal borders for one country. */
const admin1Layer = (iso, data) => new GeoJsonLayer({
    id: 'climate-admin1',
    data: data || { type: 'FeatureCollection', features: [] },
    stroked: true,
    filled: false,
    pickable: false,
    lineWidthMinPixels: 0.7,
    getLineColor: [125, 211, 252, 95],
});

/**
 * Sea-surface-temperature anomaly, measured rather than inferred.
 *
 * This was sixteen hand-placed basin circles whose values were derived from ONI,
 * DMI and AMO. Deriving from three indices means the map can only ever show what
 * those three describe: the North Atlantic "blue blob" is a cold patch inside a
 * warm basin, so an AMO average paints over precisely the feature; and the
 * Mediterranean, Black Sea and Gulf have no open-ocean index at all. Drawing them
 * would have meant making numbers up.
 *
 * Now a real 1.5° grid from NOAA OISST v2.1, built by scripts/build_sst.py.
 */
const SST_URL = '/public/data/sst_anomaly_v1.json';
let sstDoc = null;
let sstPromise = null;

const loadSst = () => {
    if (sstPromise) return sstPromise;
    sstPromise = fetch(SST_URL, { cache: 'force-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { sstDoc = d; return d; })
        .catch((err) => {
            // The map is still readable without it; land and status fills are
            // what the screen is actually for.
            console.warn('[Climate] SST grid unavailable', err);
            return null;
        });
    return sstPromise;
};

/**
 * Muted teal (cool) to muted rust (warm), saturating at ±3°C.
 *
 * ±3 rather than the data's full ±12: the extremes are a handful of shallow
 * coastal cells, and scaling to them would flatten every basin-scale signal
 * into the middle of the ramp.
 */
const sstColor = (anomaly) => {
    const t = Math.max(-3, Math.min(3, anomaly)) / 3;
    const cool = [58, 132, 176];
    const warm = [198, 108, 66];
    const u = (t + 1) / 2;
    const mix = (a, b) => Math.round(a + (b - a) * u);
    return [
        mix(cool[0], warm[0]),
        mix(cool[1], warm[1]),
        mix(cool[2], warm[2]),
        // Kept low. Against a 1971-2000 baseline most of the ocean now reads
        // warm, so a bold ramp turns the whole map orange and buries the land
        // and trade-status fills the screen is actually for. This is a wash
        // under the coastlines; the tooltip carries the number.
        22 + Math.round(Math.abs(t) * 74),
    ];
};

// Clickable ocean regions with their own history.
//
// The grid shows one month. Whether the subpolar Atlantic is having a cold spell
// or has been cold for forty years is a different question, and the second one
// is why that patch matters -- it is read as a fingerprint of a weakening
// Atlantic overturning circulation (AMOC), which moves European rainfall and the
// monsoons West African cocoa and Indian wheat run on.
let sstRegionsDoc = null;
let sstRegionsPromise = null;
let selectedOceanRegion = null;

const loadSstRegions = () => {
    if (sstRegionsPromise) return sstRegionsPromise;
    sstRegionsPromise = fetch('/public/data/sst_regions_v1.json', { cache: 'force-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { sstRegionsDoc = d; return d; })
        .catch(() => null);
    return sstRegionsPromise;
};

const regionCentre = (r) => [
    (r.bounds.lon[0] + r.bounds.lon[1]) / 2,
    (r.bounds.lat[0] + r.bounds.lat[1]) / 2,
];

/**
 * Invisible hit targets over each ocean region.
 *
 * The old basin circles were visible marks the reader had to aim at. The grid
 * already carries the colour, so a second painted circle on top of it says
 * nothing -- the target only needs to be there, not seen. Radius matches the
 * circles it replaces so "click near the basin" still works.
 */
const oceanHitLayer = () => new ScatterplotLayer({
    id: 'climate-ocean-hits',
    data: sstRegionsDoc?.regions || [],
    pickable: true,
    stroked: true,
    filled: true,
    radiusUnits: 'pixels',
    radiusMinPixels: 26,
    radiusMaxPixels: 46,
    lineWidthMinPixels: 1,
    getPosition: regionCentre,
    getRadius: 34,
    // Fully transparent until selected or hovered; deck still picks it.
    getFillColor: (d) => (d.id === selectedOceanRegion ? [125, 211, 252, 30] : [0, 0, 0, 0]),
    getLineColor: (d) => (d.id === selectedOceanRegion ? [125, 211, 252, 150] : [0, 0, 0, 0]),
    autoHighlight: true,
    highlightColor: [125, 211, 252, 45],
    updateTriggers: { getFillColor: [selectedOceanRegion], getLineColor: [selectedOceanRegion] },
});

/** Sparkline of the monthly series, drawn as an inline SVG path. */
const sstSparkline = (series, w = 300, h = 64) => {
    if (!series?.length) return '';
    const vals = series.map((s) => s[1]);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const span = hi - lo || 1;
    const x = (i) => (i / (series.length - 1)) * w;
    const y = (v) => h - ((v - lo) / span) * h;
    const d = series.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(s[1]).toFixed(1)}`).join('');
    // Zero line, so "above or below normal" is readable without axis labels.
    const zeroY = lo <= 0 && hi >= 0 ? y(0) : null;
    return `<svg class="sst-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        ${zeroY != null ? `<line x1="0" y1="${zeroY.toFixed(1)}" x2="${w}" y2="${zeroY.toFixed(1)}"
             stroke="rgba(148,163,184,.35)" stroke-dasharray="3 3" stroke-width="1"/>` : ''}
        <path d="${d}" fill="none" stroke="#7dd3fc" stroke-width="1.2"/>
    </svg>`;
};

const renderOceanRegionPanel = (region) => {
    if (!climateRightContentEl || !region) return;
    const s = region.series || [];
    const trend = region.trend_c_per_decade;
    const sign = (v) => (v >= 0 ? '+' : '');
    if (climateRightTitleEl) climateRightTitleEl.textContent = region.label_ko;
    if (climateRightDescEl) {
        climateRightDescEl.textContent =
            `해수면 수온 편차 · ${s[0]?.[0] ?? ''}~${region.latest_month} · ${s.length}개월`;
    }
    climateRightContentEl.innerHTML = `
        <div class="climate-card">
            <div class="climate-nav-row" style="margin:0 0 8px;">
                <span class="climate-back climate-click" data-ocean-close="1"
                      role="button" tabindex="0">← 닫기</span>
            </div>
            <div class="climate-big ${region.latest < 0 ? 'neg' : 'pos'}">
                ${sign(region.latest)}${region.latest.toFixed(2)}°C
            </div>
            <div class="climate-sub">${region.latest_month} · 최근 12개월 평균 ${sign(region.mean_12m)}${region.mean_12m.toFixed(2)}°C</div>
            ${sstSparkline(s)}
            <div class="sst-axis"><span>${s[0]?.[0] ?? ''}</span><span>${region.latest_month}</span></div>
        </div>
        <div class="climate-card">
            <h3>장기 변화</h3>
            <div class="climate-metric-row">
                <span class="nm">추세</span>
                <span class="vl" style="color:${trend > 0 ? '#fca5a5' : '#7dd3fc'};">
                    ${trend == null ? '—' : `${sign(trend)}${trend.toFixed(3)}°C / 10년`}</span>
            </div>
            <div class="climate-metric-row">
                <span class="nm">1980년대 대비</span>
                <span class="vl">${region.vs_1980s == null ? '—'
                    : `${sign(region.vs_1980s)}${region.vs_1980s.toFixed(2)}°C`}</span>
            </div>
            <div class="climate-sub">${sstRegionsDoc?.baseline || ''} 기준 편차</div>
        </div>
        <div class="climate-card">
            <h3>왜 보는가</h3>
            <div class="climate-sub">${region.why_ko}</div>
            <div class="ocean-affects">
                ${(region.affects || []).map((a) => `<span class="oa-chip">${a}</span>`).join('')}
            </div>
        </div>
        <p style="font-size:10px;color:#64748b;">${sstRegionsDoc?.source || ''} · ${sstRegionsDoc?.note_ko || ''}</p>`;
    if (climateRightPanelEl) climateRightPanelEl.classList.remove('hidden');
    const rp = document.getElementById('right-pane');
    if (rp) rp.style.display = 'flex';
};

/** SST grid cells, shared by the climate world and country maps. */
const sstWashLayer = (_unused, id = 'climate-sst') => {
    const pts = sstDoc?.points || [];
    const half = (sstDoc?.resolution_deg || 1.5) / 2;
    return new GeoJsonLayer({
        id,
        // Squares rather than points: a grid cell covers an area, and drawing it
        // as a dot leaves gaps that read as structure the data does not have.
        data: {
            type: 'FeatureCollection',
            features: pts.map(([lon, lat, a]) => ({
                type: 'Feature',
                properties: { a },
                geometry: {
                    type: 'Polygon',
                    coordinates: [[
                        [lon - half, lat - half], [lon + half, lat - half],
                        [lon + half, lat + half], [lon - half, lat + half],
                        [lon - half, lat - half],
                    ]],
                },
            })),
        },
        stroked: false,
        filled: true,
        pickable: true,
        getFillColor: (f) => sstColor(f.properties.a),
        onHover: (info) => {
            if (!info.object) return;
            const a = info.object.properties.a;
            positionTooltipAt(info);
            tooltipEl.classList.remove('hidden');
            tooltipEl.innerHTML = `<div class="tooltip-title">해수면 수온 편차</div>
                <div class="tooltip-stat"><span>편차</span>
                <span style="color:${a >= 0 ? '#e0a084' : '#7fb6cc'};font-weight:700;">
                ${a >= 0 ? '+' : ''}${a.toFixed(1)}°C</span></div>
                <div style="font-size:10px;color:#94a3b8;margin-top:4px;">
                NOAA OISST v2.1 · ${sstDoc?.as_of || ''} · ${sstDoc?.resolution_deg}° 격자</div>`;
        },
    });
};

// Resolve ISO / name from a GeoJSON feature (johan world.geo.json uses top-level id).
const featureCountryKey = (feature) => {
    if (!feature) return null;
    const id = feature.id ?? feature.properties?.id ?? feature.properties?.ISO_A3
        ?? feature.properties?.iso_a3 ?? feature.properties?.ADM0_A3;
    if (id != null) {
        const s = String(id).toUpperCase();
        const byIso = Object.entries(CLIMATE_COUNTRIES).find(([, c]) => c.iso === s);
        if (byIso) return byIso[0];
    }
    const name = feature.properties?.name || feature.properties?.NAME;
    if (name && CLIMATE_COUNTRIES[name]) return name;
    // Fuzzy: "United States of America" → United States entry; aliases for Ivory Coast etc.
    if (name) {
        const hit = Object.entries(CLIMATE_COUNTRIES).find(([k, c]) => {
            const aliases = c.aliases || [];
            return name.includes(k) || name.includes(c.label) || k.includes(name)
                || aliases.some((a) => name.includes(a) || a.includes(name));
        });
        if (hit) return hit[0];
    }
    return null;
};

// Persistent back control for climate left panel (survives region panel swaps).
const climateNavBackHtml = (trail = '') => `
    <div class="climate-nav-row">
        <span class="climate-back climate-click" data-climate-back="1"
              role="button" tabindex="0" aria-label="세계 지도로 돌아가기">← 세계 지도</span>
        ${trail ? `<span class="climate-nav-trail">${trail}</span>` : ''}
    </div>`;

// Event-delegated climate UI clicks (large hit targets; rewire-safe after innerHTML).
const handleClimateDomAction = (e) => {
    const t = e.target instanceof Element ? e.target : null;
    if (!t) return;
    if (t.closest('[data-ocean-close]')) {
        e.preventDefault();
        selectedOceanRegion = null;
        showClimateWorld();
        return;
    }
    const back = t.closest('[data-climate-back]');
    if (back) {
        e.preventDefault();
        e.stopPropagation();
        showClimateWorld();
        return;
    }
    const national = t.closest('[data-climate-national]');
    if (national) {
        e.preventDefault();
        e.stopPropagation();
        if (climateCountry && CLIMATE_COUNTRIES[climateCountry]) {
            climateSelectedRegion = null;
            renderCountryPanel(CLIMATE_COUNTRIES[climateCountry]).catch(err =>
                console.error('[Climate] re-render national', err));
        }
        return;
    }
    const country = t.closest('[data-climate-country]');
    if (country) {
        e.preventDefault();
        e.stopPropagation();
        const name = country.getAttribute('data-climate-country');
        if (name) showClimateCountry(name);
        return;
    }
    const region = t.closest('[data-climate-region]');
    if (region) {
        e.preventDefault();
        e.stopPropagation();
        const name = region.getAttribute('data-climate-region');
        if (name) updateForecastPanel(name);
    }
};

const handleClimateDomKey = (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const t = e.target instanceof Element ? e.target : null;
    if (!t) return;
    if (!t.closest('[data-climate-country],[data-climate-region],[data-climate-back],[data-climate-national]')) return;
    e.preventDefault();
    handleClimateDomAction(e);
};

// Widget-stack swipe. Delegated on a durable root so it survives the panel
// being rebuilt, and pointer-based so trackpad, mouse and touch all work.
const wireWidgetStacks = (root) => {
    if (!root || root.dataset.wsWired === '1') return;
    root.dataset.wsWired = '1';

    const goTo = (stack, i) => {
        const track = stack.querySelector('.ws-track');
        const dots = [...stack.querySelectorAll('.ws-dot')];
        const n = dots.length || 1;
        const idx = Math.max(0, Math.min(n - 1, i));
        stack.dataset.index = String(idx);
        track.style.transform = `translateX(${-idx * 100}%)`;
        dots.forEach((d, k) => d.classList.toggle('is-on', k === idx));
    };

    root.addEventListener('click', (e) => {
        const dot = e.target instanceof Element ? e.target.closest('[data-ws-go]') : null;
        if (!dot) return;
        e.preventDefault();
        goTo(dot.closest('.widget-stack'), Number(dot.dataset.wsGo));
    });

    let drag = null;
    root.addEventListener('pointerdown', (e) => {
        const stack = e.target instanceof Element ? e.target.closest('.widget-stack') : null;
        // Links and buttons inside a card keep their own behaviour.
        if (!stack || e.target.closest('a,button')) return;
        drag = { stack, x: e.clientX, idx: Number(stack.dataset.index || 0) };
    });
    root.addEventListener('pointerup', (e) => {
        if (!drag) return;
        const dx = e.clientX - drag.x;
        // 40px, so a click that wobbles does not change card.
        if (Math.abs(dx) > 40) goTo(drag.stack, drag.idx + (dx < 0 ? 1 : -1));
        drag = null;
    });
    root.addEventListener('pointercancel', () => { drag = null; });

    root.addEventListener('keydown', (e) => {
        const stack = e.target instanceof Element ? e.target.closest('.widget-stack') : null;
        if (!stack || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
        e.preventDefault();
        goTo(stack, Number(stack.dataset.index || 0) + (e.key === 'ArrowRight' ? 1 : -1));
    });
};
wireWidgetStacks(forecastContentEl);

// One-time delegation on durable panel roots (survives innerHTML rebuilds).
const wireClimateDomClicks = (root) => {
    if (!root || root.dataset.climateDelegate === '1') return;
    root.dataset.climateDelegate = '1';
    root.addEventListener('click', handleClimateDomAction);
    root.addEventListener('keydown', handleClimateDomKey);
};
// Attach early so first render is always covered.
wireClimateDomClicks(climateRightContentEl);
wireClimateDomClicks(forecastContentEl);

// Map canvas pointer → pickObject (MapLibre/controller can swallow deck onClick).
let climateCanvasPointerWired = false;
let climatePointerDown = null;
const climateCanvasLocalXY = (clientX, clientY) => {
    if (!mapContainer) return null;
    const deckCanvas = mapContainer.querySelector('canvas:not(.maplibregl-canvas)')
        || mapContainer.querySelector('canvas');
    if (!deckCanvas) return null;
    const r = deckCanvas.getBoundingClientRect();
    const x = clientX - r.left;
    const y = clientY - r.top;
    if (x < 0 || y < 0 || x > r.width || y > r.height) return null;
    return { x, y };
};
const tryClimateMapPick = (clientX, clientY) => {
    if (currentCommodity !== 'climate' || !deckgl?.pickObject) return;
    const xy = climateCanvasLocalXY(clientX, clientY);
    if (!xy) return;
    // Fallback only acts on hits so empty picks do not burn the debounce window.
    const info = deckgl.pickObject({ x: xy.x, y: xy.y, radius: 20 });
    if (!info?.object) return;
    handleClimateDeckClick(info);
};
const ensureClimateMapPointerFallback = () => {
    if (climateCanvasPointerWired || !mapContainer) return;
    climateCanvasPointerWired = true;
    mapContainer.addEventListener('pointerdown', (e) => {
        if (currentCommodity !== 'climate') return;
        if (e.button !== 0) return;
        climatePointerDown = { x: e.clientX, y: e.clientY, t: performance.now() };
    }, true);
    const onPointerLikeClick = (e) => {
        if (currentCommodity !== 'climate') return;
        if (e.button != null && e.button !== 0) return;
        if (!climatePointerDown) {
            // `click` without prior pointerdown tracking (rare) — still try pick.
            if (e.type === 'click') tryClimateMapPick(e.clientX, e.clientY);
            return;
        }
        const dx = e.clientX - climatePointerDown.x;
        const dy = e.clientY - climatePointerDown.y;
        const dt = performance.now() - climatePointerDown.t;
        climatePointerDown = null;
        // Treat as click only if short & small movement (not pan/drag).
        if (dt > 600 || Math.hypot(dx, dy) > 8) return;
        tryClimateMapPick(e.clientX, e.clientY);
    };
    mapContainer.addEventListener('pointerup', onPointerLikeClick, true);
    mapContainer.addEventListener('click', onPointerLikeClick, true);
};

// Single deck click router for climate — layer onClick alone is flaky when
// basemap + MapView controller steal events after GlobeView switches.
// Debounce only after a successful action so pointerup+onClick do not double-fire.
let lastClimatePickAt = 0;
const handleClimateDeckClick = (info) => {
    if (currentCommodity !== 'climate') return;
    const now = performance.now();
    if (now - lastClimatePickAt < 300) return;
    const mark = () => { lastClimatePickAt = now; };

    if (climateLevel === 'world') {
        // Ocean region first: its hit target sits over water, so a pick there is
        // unambiguous and should not fall through to the country layer.
        if (info?.layer?.id === 'climate-ocean-hits' && info.object?.id) {
            mark();
            selectedOceanRegion = info.object.id;
            showClimateWorld();
            return;
        }
        // Prefer pin object (has .name), else GeoJSON feature
        if (info?.object?.name && CLIMATE_COUNTRIES[info.object.name]) {
            mark();
            showClimateCountry(info.object.name);
            return;
        }
        // Scatterplot pins may report layer id without going through featureCountryKey
        if (info?.layer?.id === 'climate-country-pins' && info.object?.name
            && CLIMATE_COUNTRIES[info.object.name]) {
            mark();
            showClimateCountry(info.object.name);
            return;
        }
        const key = featureCountryKey(info?.object);
        if (key) {
            mark();
            showClimateCountry(key);
        }
        // Non-model country / ocean → no-op (stay on world)
        return;
    }
    if (climateLevel === 'country') {
        // Region pin → detail panel (layer id when present; else region point fields).
        const isRegionPin = info?.layer?.id === 'climate-regions'
            || (info?.object?.name && info.object.stress != null && info.object.coordinates);
        if (isRegionPin && info.object?.name) {
            mark();
            updateForecastPanel(info.object.name);
            return;
        }
        // Pin miss or country fill → stay. Never auto-return to world on empty hits.
        // Optional: another modelled country poly → switch country view.
        if (!info?.object) return;
        const key = featureCountryKey(info.object);
        if (key && key !== climateCountry) {
            mark();
            showClimateCountry(key);
        }
    }
};

const handleClimateDeckHover = (info) => {
    if (currentCommodity !== 'climate' || climateLevel !== 'world') {
        return;
    }
    if (!info?.object) {
        hideClimateTooltip();
        return;
    }
    let key = null;
    if (info.object.name && CLIMATE_COUNTRIES[info.object.name]) key = info.object.name;
    else key = featureCountryKey(info.object);
    if (!key) {
        hideClimateTooltip();
        return;
    }
    showClimateTooltip(info, key, CLIMATE_COUNTRIES[key]);
};


const tradePolicyLevel = (countryName) => {
    const p = CLIMATE_TRADE_POLICY[countryName] || {};
    const n = (p.prohibitedCrops || []).length;
    if (n >= 2) return 'red';
    if (n === 1) return 'orange';
    if (p.restricted) return 'yellow';
    return 'blue';
};

const tradePolicyLabelKo = (level) => ({
    blue: '정상',
    yellow: 'Restricted',
    orange: 'Prohibited 1',
    red: 'Prohibited 2+',
}[level] || level);

// Which level the climate view is currently showing.
let climateLevel = 'world';
let climateCountry = null;
/** @type {string|null} region pin / list selection inside country view */
let climateSelectedRegion = null;

// Canonical crop identity for merging same crop across region slots (e.g. WA+SA+Vic wheat → 밀).
const CROP_CANON = {
    wheat: 'wheat', trigo: 'wheat', spring_wheat: 'wheat', winter_wheat: 'wheat',
    corn: 'corn', maize: 'corn', milho: 'corn', maiz: 'corn',
    soy: 'soy', soybean: 'soy', soybeans: 'soy', soja: 'soy',
    rice: 'rice',
    // algodao is Portuguese (MATOPIBA), algodon Spanish (Chaco). Without the
    // second spelling Argentine cotton falls through to "기타 작물".
    cotton: 'cotton', algodao: 'cotton', algodon: 'cotton',
    sugar: 'sugar', cane: 'sugar', cana: 'sugar', sugarcane: 'sugar',
    coffee: 'coffee', cafe: 'coffee',
    palm: 'palm', oil_palm: 'palm', palm_oil: 'palm',
    rubber: 'rubber',
    vegetables: 'vegetables',
    orange: 'orange', laranja: 'orange',
    sunflower: 'sunflower', podsolnechnik: 'sunflower',
    barley: 'barley',
    cocoa: 'cocoa', cacao: 'cocoa',
};
const CROP_LABEL_KO = {
    wheat: '밀', corn: '옥수수', soy: '대두', rice: '벼', cotton: '면화',
    sugar: '사탕수수', coffee: '커피', palm: '팜', rubber: '천연고무',
    vegetables: '채소', orange: '오렌지',
    sunflower: '해바라기', barley: '보리', cocoa: '코코아', other: '기타 작물',
};

// Crop calendar seed (month 1–12). No live phenology feed — heuristic stage only.
// Source discipline: agronomic calendar approximations per country × crop type.
const CROP_CALENDAR_SEED = {
    Australia: {
        wheat: { sow: [4, 5, 6], harvest: [10, 11, 12] },
    },
    'United States': {
        corn: { sow: [4, 5], harvest: [9, 10, 11] },
        soy: { sow: [5, 6], harvest: [9, 10] },
        wheat: { sow: [9, 10], harvest: [6, 7] },
        cotton: { sow: [4, 5], harvest: [9, 10, 11] },
    },
    Brazil: {
        soy: { sow: [10, 11, 12], harvest: [2, 3, 4] },
        corn: { sow: [1, 2, 9, 10], harvest: [5, 6, 7, 12] },
        wheat: { sow: [5, 6], harvest: [10, 11] },
        cotton: { sow: [11, 12], harvest: [6, 7, 8] },
        sugar: { sow: [2, 3, 4], harvest: [4, 5, 6, 7, 8, 9, 10, 11] },
        coffee: { sow: [10, 11], harvest: [5, 6, 7, 8] },
        orange: { sow: [8, 9], harvest: [6, 7, 8, 9] },
    },
    Argentina: {
        soy: { sow: [11, 12], harvest: [3, 4, 5] },
        corn: { sow: [9, 10, 11, 12], harvest: [3, 4, 5, 6] },
        wheat: { sow: [5, 6, 7], harvest: [11, 12, 1] },
        cotton: { sow: [10, 11], harvest: [3, 4, 5] },
        sugar: { sow: [3, 4], harvest: [5, 6, 7, 8, 9, 10] },
    },
    China: {
        wheat: { sow: [10, 11], harvest: [5, 6] },
        rice: { sow: [4, 5, 6], harvest: [9, 10] },
        vegetables: { sow: [3, 4, 5], harvest: [6, 7, 8, 9] },
    },
    India: {
        wheat: { sow: [11, 12], harvest: [3, 4] },
        soy: { sow: [6, 7], harvest: [10, 11] },
        cotton: { sow: [5, 6, 7], harvest: [10, 11, 12] },
    },
    Indonesia: {
        rice: { sow: [11, 12, 1], harvest: [3, 4, 5] },
        // Perennials are not sown and harvested on a season. Oil palm is cut on
        // a 10-14 day round and rubber is tapped through the year, so filling
        // every month as "sow" and "harvest" drew a bar that said nothing --
        // and implied a planting window that does not exist.
        palm: { perennial: true, note_ko: '연중 수확 (10~14일 주기 수확)' },
        coffee: { sow: [10, 11], harvest: [5, 6, 7, 8] },
        rubber: { perennial: true, note_ko: '연중 채취 (수액 채취, 저수기 2~3월 감소)' },
    },
    Russia: {
        // Winter wheat overwinters: sown late summer, dormant, harvested the
        // following July. Sunflower runs a spring-to-autumn window entirely
        // inside one calendar year -- which is why the same oblast can read
        // -9% for wheat and +8% for sunflower in the same season.
        wheat: { sow: [8, 9], harvest: [7, 8] },
        sunflower: { sow: [5], harvest: [9, 10] },
        barley: { sow: [4, 5], harvest: [8] },
    },
    Vietnam: {
        // Mekong Delta runs three rice crops; the modelled one is Winter-Spring.
        rice: { sow: [11, 12], harvest: [2, 3, 4] },
        coffee: { sow: [6, 7], harvest: [11, 12, 1] },
        rubber: { perennial: true, note_ko: '연중 채취 (낙엽기 2~4월 채취 중단)' },
    },
    Ghana: {
        cocoa: { perennial: true, note_ko: '다년생 · 주수확 10~2월, 중간수확 5~8월' },
    },
    'Ivory Coast': {
        cocoa: { perennial: true, note_ko: '다년생 · 주수확 10~3월, 중간수확 4~8월' },
    },
};

const cropIdentityFromText = (text) => {
    const s = String(text || '').toLowerCase().replace(/[^a-z_]/g, ' ');
    for (const token of s.split(/[\s_]+/)) {
        if (CROP_CANON[token]) return CROP_CANON[token];
    }
    for (const [raw, canon] of Object.entries(CROP_CANON)) {
        if (s.includes(raw)) return canon;
    }
    return 'other';
};

const cropIdentity = (c) => cropIdentityFromText(`${c.regionKey || ''} ${c.label || ''}`);

const mergeCropsByType = (crops) => {
    const map = new Map();
    for (const c of crops) {
        const id = cropIdentity(c);
        if (!map.has(id)) {
            map.set(id, {
                id,
                label: CROP_LABEL_KO[id] || c.label || id,
                unit: c.unit,
                points: [],
                pcts: [],
                lasts: [],
                regions: new Set(),
                lowN: 0,
                total: 0,
                noForecast: 0,
            });
        }
        const g = map.get(id);
        g.total += 1;
        if (c.regionKey) g.regions.add(c.regionKey);
        else if (c.group) g.regions.add(c.group);
        if (c.unit && !g.unit) g.unit = c.unit;
        if (c.forecastAvailable === false || c.point == null) g.noForecast += 1;
        if (c.point != null) g.points.push(c.point);
        if (c.pct != null) g.pcts.push(c.pct);
        if (c.lastActual != null) g.lasts.push(c.lastActual);
        if (c.lowConfidence) g.lowN += 1;
    }
    return [...map.values()].map((g) => {
        const avg = (arr) => (arr.length
            ? arr.reduce((a, b) => a + b, 0) / arr.length
            : null);
        return {
            id: g.id,
            label: g.label,
            unit: g.unit || 'kg/ha',
            meanPoint: avg(g.points),
            meanPct: avg(g.pcts),
            meanLast: avg(g.lasts),
            regionCount: Math.max(g.regions.size, g.total),
            lowShare: g.total ? g.lowN / g.total : 0,
            noForecast: g.noForecast,
            total: g.total,
        };
    }).sort((a, b) => a.label.localeCompare(b.label, 'ko'));
};

const monthInSpan = (months, m) => (months || []).includes(m);

// Spans may wrap (e.g. wheat sow Oct–Nov, harvest Jun–Jul).
const monthsToCssRange = (months) => {
    if (!months?.length) return [];
    const set = new Set(months);
    const ranges = [];
    let start = null;
    for (let m = 1; m <= 12; m++) {
        if (set.has(m)) {
            if (start == null) start = m;
        } else if (start != null) {
            ranges.push([start, m - 1]);
            start = null;
        }
    }
    if (start != null) ranges.push([start, 12]);
    return ranges;
};

const phenologyStageSeed = (cal, month) => {
    if (!cal) return { stage: '미정', detail: '캘린더 seed 없음', kind: 'unknown' };
    // A perennial has no sowing, no fallow and no single harvest window; asking
    // which growth stage it is in makes no sense for a tree or a tapped stand.
    if (cal.perennial) {
        return { stage: '다년생', detail: cal.note_ko || '연중 생육 · 파종/휴경 구분 없음', kind: 'perennial' };
    }
    const sow = cal.sow || [];
    const har = cal.harvest || [];
    if (monthInSpan(sow, month)) {
        return { stage: '파종·출아', detail: '씨를 넣고 싹이 나오는 창', kind: 'sow' };
    }
    if (monthInSpan(har, month)) {
        return { stage: '수확', detail: '수확·탈곡 창', kind: 'harvest' };
    }
    const grow = growMonthsBetween(cal);
    if (grow.includes(month)) {
        // Split early vs late grow when the window is long enough
        const mid = grow[Math.floor(grow.length / 2)];
        if (month <= mid) {
            return { stage: '영양생장', detail: '잎·줄기 생육 (파종 후~개화 전)', kind: 'veg' };
        }
        return { stage: '생식·충실', detail: '개화·결실·알곡 채움', kind: 'repro' };
    }
    return { stage: '비작기', detail: '휴경·휴지기 (밭이 쉬거나 다음 작기 준비)', kind: 'fallow' };
};

/** Months that sit between sow and harvest windows (growing season), wrapping OK. */
const growMonthsBetween = (cal) => {
    const sow = cal?.sow || [];
    const har = cal?.harvest || [];
    if (!sow.length || !har.length) return [];
    const sowSet = new Set(sow);
    const harSet = new Set(har);
    const maxSow = Math.max(...sow);
    const minHar = Math.min(...har);
    const out = [];
    for (let m = 1; m <= 12; m++) {
        if (sowSet.has(m) || harSet.has(m)) continue;
        if (maxSow < minHar) {
            if (m > maxSow && m < minHar) out.push(m);
        } else {
            // wrap: grow after late sow through year-end and/or early year until harvest
            if (m > maxSow || m < minHar) out.push(m);
        }
    }
    return out;
};

const fmtMonthList = (months) => {
    if (!months?.length) return '—';
    return months.map((m) => `${m}월`).join('·');
};

const renderCropCalendarHtml = (countryName, cropIds) => {
    const calRoot = CROP_CALENDAR_SEED[countryName] || {};
    const month = new Date().getMonth() + 1;
    const ids = cropIds?.length ? cropIds : Object.keys(calRoot);
    if (!ids.length) {
        return `<div class="climate-sub">캘린더 seed 준비 중</div>`;
    }
    const rows = ids.map((id) => {
        const cal = calRoot[id];
        if (!cal) return '';
        const label = CROP_LABEL_KO[id] || id;
        const stage = phenologyStageSeed(cal, month);
        if (cal.perennial) {
            const nowLeft = ((month - 0.5) / 12) * 100;
            return `<div class="climate-cal-row">
                <div class="cal-name">${label}
                    <span style="color:#64748b;font-weight:400;font-size:11px;"> · 다년생</span>
                </div>
                <div class="climate-cal-track">
                    <span class="climate-cal-bar perennial" style="left:0;width:100%"></span>
                    <span class="climate-cal-now" style="left:${nowLeft}%" title="현재 ${month}월"></span>
                </div>
                <div class="climate-cal-stage">${cal.note_ko || '연중 생육'}</div>
            </div>`;
        }
        const grow = growMonthsBetween(cal);
        const sowBars = monthsToCssRange(cal.sow).map(([a, b]) => {
            const left = ((a - 1) / 12) * 100;
            const width = ((b - a + 1) / 12) * 100;
            return `<span class="climate-cal-bar sow" style="left:${left}%;width:${width}%" title="파종 ${fmtMonthList(cal.sow)}"></span>`;
        }).join('');
        const growBars = monthsToCssRange(grow).map(([a, b]) => {
            const left = ((a - 1) / 12) * 100;
            const width = ((b - a + 1) / 12) * 100;
            return `<span class="climate-cal-bar grow" style="left:${left}%;width:${width}%" title="생육 ${fmtMonthList(grow)}"></span>`;
        }).join('');
        const harBars = monthsToCssRange(cal.harvest).map(([a, b]) => {
            const left = ((a - 1) / 12) * 100;
            const width = ((b - a + 1) / 12) * 100;
            return `<span class="climate-cal-bar harvest" style="left:${left}%;width:${width}%" title="수확 ${fmtMonthList(cal.harvest)}"></span>`;
        }).join('');
        const nowLeft = ((month - 0.5) / 12) * 100;
        return `<div class="climate-cal-row">
            <div class="cal-name">${label}
                <span style="color:#64748b;font-weight:400;font-size:11px;"> · 파종 ${fmtMonthList(cal.sow)} · 수확 ${fmtMonthList(cal.harvest)}</span>
            </div>
            <div class="climate-cal-track">${growBars}${sowBars}${harBars}
                <span class="climate-cal-now" style="left:${nowLeft}%" title="현재 ${month}월"></span>
            </div>
            <div class="climate-cal-stage">현재 추정 단계: <strong style="color:#e2e8f0;">${stage.stage}</strong>
                <span style="color:#64748b;"> · ${stage.detail}</span></div>
        </div>`;
    }).filter(Boolean).join('');
    return `${rows || '<div class="climate-sub">해당 작물 캘린더 없음</div>'}
        <div class="climate-cal-legend">
            <span><i class="sow"></i>파종·출아</span>
            <span><i class="grow"></i>생육(영양→생식)</span>
            <span><i class="har"></i>수확</span>
            <span><i class="fallow"></i>비작기</span>
            <span><i class="perennial"></i>다년생</span>
        </div>
        <div class="climate-sub" style="margin-top:8px;line-height:1.55;">
            <strong>단계 설명</strong><br>
            · <em>파종·출아</em>: 씨를 넣고 싹이 트는 달<br>
            · <em>영양생장</em>: 잎·줄기가 크는 달 (개화 전)<br>
            · <em>생식·충실</em>: 꽃·꼬투리·알곡이 차는 달<br>
            · <em>수확</em>: 거둬들이는 달<br>
            · <em>비작기</em>: 작기가 끝난 휴경·휴지 (다음 파종 전까지)<br>
            · <em>다년생</em>: 고무·팜·코코아처럼 심어두고 여러 해 수확 — 파종기·비작기가 없습니다<br>
            막대에 없는 달은 비작기로 보면 됩니다. (seed 휴리스틱 · 실측 위성 페놀이로지 아님)
        </div>`;
};

let usdaGainCache = null;
const loadUsdaGain = async () => {
    if (usdaGainCache) return usdaGainCache;
    try {
        const res = await fetch('/public/data/usda_gain_outlook_v1.json', { cache: 'no-cache' });
        usdaGainCache = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn('[Climate] USDA GAIN seed unavailable', err);
        usdaGainCache = null;
    }
    return usdaGainCache;
};

const fasSearchUrl = (keyword) => {
    const q = encodeURIComponent(String(keyword || '').trim());
    return `https://www.fas.usda.gov/data/search?keyword=${q}`;
};

/**
 * The country's own statistics office, beside USDA's view of it.
 *
 * USDA GAIN is a foreign attaché's read. Every country here also publishes its
 * own crop statistics -- CONAB, MAGyP, ABARES, BPS, Rosstat -- and that is what
 * the models are actually trained against, so the two belong side by side
 * rather than one standing in for the other.
 *
 * Where they disagree is the interesting part, which is a reason to show both
 * and not to merge them.
 */
const monthsSince = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const now = new Date();
    return (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
};

const renderNationalSourceCard = (cfg) => {
    const src = cfg?.sources || {};
    const lab = src.labels || {};
    const clim = src.climate || {};
    if (!lab.name && !clim.name) return '';

    const age = lab.updated ? monthsSince(lab.updated) : null;
    // Agricultural statistics normally run a season or two behind; past three
    // years the series is not "recent official data" in any useful sense.
    const tone = age == null ? '' : (age > 36 ? 'red' : age > 24 ? 'yellow' : 'green');
    const ageKo = age == null ? '갱신일 미상'
        : (age < 1 ? '이번 달' : age < 24 ? `${age}개월 전` : `${Math.floor(age / 12)}년 ${age % 12}개월 전`);

    return `<div class="climate-card">
        <h3>자국 공식 통계 <span class="src-tag">모델 학습 라벨</span></h3>
        <div class="climate-metric-row">
            <span class="nm">${lab.name || '—'}</span>
            ${tone ? `<span class="climate-status-pill ${tone}">${ageKo}</span>` : ''}
        </div>
        ${lab.updated ? `<div class="climate-sub">수록 최신 시점 ${lab.updated}</div>` : ''}
        ${lab.url ? `<div style="margin-top:6px;"><a class="climate-gain-link" href="${lab.url}"
             target="_blank" rel="noopener">원본 열기 ↗</a></div>` : ''}
        ${clim.name ? `<div class="climate-metric-row" style="margin-top:10px;">
            <span class="nm">기상 입력</span>
            <span class="vl" style="font-size:11px;">${clim.name}</span>
        </div>` : ''}
        <div class="climate-sub" style="margin-top:8px;">
            USDA/GAIN 은 외부 기관의 관측이고, 이 통계는 해당국이 직접 집계해 공표한 값입니다.
            모델의 정답지는 이쪽이며, 두 수치가 갈리는 지점이 곧 살펴볼 지점입니다.
        </div>
    </div>`;
};

/**
 * iPhone-style widget stack: several source cards in one slot, swiped between.
 *
 * Vertical space in this column is the constraint -- stacking every source
 * pushes the crop calendar below the fold. Sharing one slot keeps them at equal
 * weight instead of ranking them by scroll position.
 */
const renderSourceStack = (cards) => {
    const present = cards.filter(Boolean);
    if (present.length <= 1) return present[0] || '';
    return `<div class="widget-stack" data-count="${present.length}">
        <div class="ws-track">${present.map((c) => `<div class="ws-slide">${c}</div>`).join('')}</div>
        <div class="ws-dots">${present.map((_, i) =>
            `<button type="button" class="ws-dot${i === 0 ? ' is-on' : ''}" data-ws-go="${i}"
                     aria-label="${i + 1}번째 출처"></button>`).join('')}</div>
    </div>`;
};

const renderUsdaGainCard = async (countryName) => {
    const doc = await loadUsdaGain();
    const entry = doc?.countries?.[countryName];
    const portal = doc?.portal || {
        label: 'USDA FAS Data Search',
        url: 'https://www.fas.usda.gov/data/search',
    };
    const families = doc?.gain_families || {};

    if (!entry) {
        return `<div class="climate-card">
            <h3>USDA/GAIN 전망 (시즌)</h3>
            <div class="climate-sub">데이터 준비 중 — 이 국가의 생산 전망 seed가 아직 없습니다.</div>
            <div class="climate-sub" style="margin-top:8px;">
                <a href="${portal.url}" target="_blank" rel="noopener" style="color:#7dd3fc;">FAS Data Search ↗</a>
                에서 국가·GAIN 계열을 검색하세요.
            </div>
        </div>`;
    }

    const countryTerm = entry.search_country || countryName;
    const famIds = entry.gain_families?.length
        ? entry.gain_families
        : [...new Set((entry.items || []).map((it) => it.family).filter(Boolean))];

    const familyLinks = famIds.map((fid) => {
        const fam = families[fid];
        const q = fam
            ? `${countryTerm} ${fam.search_query || fam.label_en}`
            : `${countryTerm} ${fid}`;
        const label = fam?.label_ko || fam?.label_en || fid;
        return `<a class="climate-gain-link" href="${fasSearchUrl(q)}" target="_blank" rel="noopener">${label} ↗</a>`;
    }).join('');

    // Country-wide search (all GAIN families for this country)
    const countrySearch = fasSearchUrl(`${countryTerm} GAIN`);

    const items = (entry.items || []).map((it) => {
        const yoy = it.yoy_pct;
        const yoyColor = yoy == null ? '#94a3b8' : (yoy >= 0 ? '#4ade80' : '#fca5a5');
        const yoyStr = yoy == null ? '—' : `${yoy >= 0 ? '+' : ''}${Number(yoy).toFixed(1)}%`;
        const prod = it.production_mmt != null ? `${Number(it.production_mmt).toFixed(1)} MMT` : '—';
        const prior = it.prior_mmt != null ? ` / 전년 ${Number(it.prior_mmt).toFixed(1)}` : '';
        const fam = it.family && families[it.family];
        const famTag = fam
            ? `<span class="climate-chip" style="margin-left:6px;">${fam.label_en}</span>`
            : '';
        const itemSearch = fam
            ? fasSearchUrl(`${countryTerm} ${fam.search_query || fam.label_en}`)
            : countrySearch;
        return `<div class="climate-gain-item">
            <div class="gi-top">
                <span>${it.crop_ko || '작물'}${famTag}</span>
                <span>${prod}<span class="gi-yoy" style="color:${yoyColor};margin-left:6px;">${yoyStr}</span></span>
            </div>
            <div class="gi-note">전년 대비 생산${prior}${it.note_ko ? ` · ${it.note_ko}` : ''}
                · <a href="${itemSearch}" target="_blank" rel="noopener" style="color:#7dd3fc;">FAS 검색</a>
            </div>
        </div>`;
    }).join('');

    return `<div class="climate-card">
        <h3>USDA/GAIN 전망 (${entry.season || '시즌'})</h3>
        ${items || '<div class="climate-sub">항목 없음</div>'}
        <div class="climate-gain-links">
            <a class="climate-gain-link primary" href="${countrySearch}" target="_blank" rel="noopener">
                ${countryTerm} GAIN 검색 ↗
            </a>
            ${familyLinks}
            <a class="climate-gain-link" href="${portal.url}" target="_blank" rel="noopener">FAS 포털 ↗</a>
        </div>
        <div class="climate-sub" style="margin-top:8px;">
            ${entry.source_label || 'USDA GAIN seed'} · 정적 요약 · 실무 최신값은
            <a href="${portal.url}" target="_blank" rel="noopener" style="color:#7dd3fc;">fas.usda.gov/data/search</a>
            에서 계열별로 확인
        </div>
    </div>`;
};

const setClimateCommodityHeader = (mode) => {
    const panel = document.getElementById('commodity-info-panel');
    if (!panel) return;
    if (mode === 'climate') panel.classList.add('climate-mode');
    else panel.classList.remove('climate-mode');
};

const BRAZIL_REGION_MODELS = {
    'Mato Grosso (Brazil)': ['mato_grosso_soja', 'mato_grosso_milho'],
    'Rio Grande do Sul (Brazil)': ['parana_soja', 'parana_milho', 'parana_trigo'],
    'MATOPIBA (Brazil)': ['matopiba_soja', 'matopiba_algodao'],
    'Sao Paulo (Brazil)': ['sp_cana', 'sp_cafe', 'sp_laranja'],
};

// Which model key belongs to each clickable Indian region on the map. One
// model per point here, unlike Brazil -- the three guides in Regions/인도
// each cover exactly one region-crop.
const INDIA_REGION_MODELS = {
    'Punjab (India)': ['punjab_wheat'],
    'Madhya Pradesh (India)': ['mp_soybean'],
    'Vidarbha (India)': ['vidarbha_cotton'],
};

// Korean copy for the "not weather" callout. The model artifacts carry the
// canonical English in provenance.non_weather_drivers; this is the display
// layer, so the translation lives here rather than being duplicated into the
// JSON the pipeline writes.
const BRAZIL_NON_WEATHER_KO = {
    parana_milho:
        'SIDRA는 주별 옥수수를 1기작·2기작 합산 단일 수치로 발표합니다. 파라나는 두 작기가 모두 크고 ' +
        '재배 면적 배분이 대두·옥수수 가격에 따라 해마다 바뀌므로, 이 목표값의 연간 변동 중 일부는 ' +
        '날씨가 아니라 면적 배분 의사결정입니다. ' +
        '다만 "옥수수엔 날씨가 안 통한다"는 뜻은 아닙니다 — 방향은 대두와 같습니다. 같은 지역 ' +
        '탈추세 로그수확량으로 옥수수·대두 상관을 재보면 +0.70이고, 옥수수 자체 기상 피처(VPD_peak ' +
        '−0.52, SPI3_Jan +0.42)도 농학적으로 맞는 방향으로 옥수수 수확량을 움직입니다. 그런데 ' +
        '같은 기상 변수가 옥수수 자기 수확량보다 대두 수확량과 더 강하게 상관됩니다(−0.61, +0.59). ' +
        '즉 옥수수 목표값엔 진짜 날씨 신호가 있고, 그 위에 비기상 잡음이 얹혀 있는 것이지, 날씨가 ' +
        '이 작물을 안 움직이는 게 아닙니다.',
    sp_cana:
        '사탕수수는 5~7년에 한 번만 갱신하는 ratoon(그루터기) 작물이라, 특정 해의 수확량은 상당 부분 ' +
        '식재 연차 구성(상파울루 면적 중 1번지기 대 5번지기 비율)에 좌우됩니다. 이는 갱신 투자·품종 ' +
        '교체·제당공장 경제성이 정하는 값이며 어떤 기상 데이터에도 나타나지 않습니다. ' +
        '이건 이 모델의 한계가 아니라 학계의 정설입니다 — Dias & Sentelhas(2017)가 표준 시뮬레이터 ' +
        '3종(FAO-AZM·DSSAT/CANEGRO·APSIM)을 브라질 상업 포장에 적용했을 때 MAE 29 t/ha 초과, ' +
        'R² 0.54 미만이었고, 원인을 "경영을 반영하는 계수의 부재"로 지목했습니다. 그루터기 감퇴 ' +
        '계수(kdec)를 넣자 MAE 13~15 t/ha, R² 0.58~0.72로 개선됐습니다. 기후만으로는 누구도 이 ' +
        '작물을 예측하지 못합니다. ' +
        '팜유·커피 같은 다른 다년생 작물과는 성격이 다른 문제입니다. 팜유의 다년성은 고정된 생리 ' +
        '시차입니다 — 가뭄이 오면 24개월 뒤 열릴 열매의 성별이 강제로 바뀌므로, 12~24개월 누적 ' +
        '수분적자를 시차로 넣으면 실제로 잡힙니다(업계 표준 관행). 사탕수수를 지배하는 그루터기 ' +
        '연차는 그런 날씨-시차 메커니즘이 아예 없습니다 — 언제 갈아엎어 재식할지의 투자 결정입니다. ' +
        '문서가 요구한 다년 누적 방식(12~18개월 수분적자, SPI-12)을 이미 넣어봤는데도 날씨만의 ' +
        '기여는 −13.6%로 그대로 마이너스였습니다. 시차를 늘려도 안 됐다는 건, 애초에 빠진 게 ' +
        '"더 긴 날씨 기억"이 아니라 "날씨로 환원 안 되는 변수"라는 뜻입니다. ' +
        '경영 대리변수인 lag1조차 표준화 효과가 +0.1%로, 11개 피처 중 가장 약합니다 — ' +
        '그루터기 연차 대리변수마저 이 정도로 안 움직인다는 게 사탕수수 변동성이 얼마나 안 ' +
        '잡히는지를 보여줍니다.',
    sp_cafe:
        '해걸이(격년결실)는 기상이 아니라 생리 현상입니다. 많이 열린 해에 나무가 소진되면 이듬해는 ' +
        '날씨와 무관하게 적게 열립니다. lag1·lag2가 이 주기를 담고 있고 이 둘이 모델의 최강 피처이므로, ' +
        '이 모델 성능의 상당 부분은 기후가 아니라 생물학적 기억입니다. ' +
        'lag1·lag2를 빼고 기상 피처만 남기면 스킬이 +1.6%로 줄어듭니다(전체는 +8.6%). 서리·개화기 ' +
        '수분결핍이라는 진짜 기후 메커니즘은 있지만(문서에도 명시, 물리적으로도 잘 알려짐), 주(州) ' +
        '단위 연간 데이터에서는 해걸이 주기가 그 변동을 압도합니다. "다년 메모리를 넣었다"가 ' +
        '자동으로 "날씨가 이긴다"를 보장하진 않는다는 걸 이 작물이 가장 명확하게 보여줍니다.',
    sp_laranja:
        '이 문서는 첫 문단부터 "이 시장은 기후가 아닌 감귤 녹화병(HLB)에 의해 붕괴되고 있다"고 ' +
        '명시하며, 처방된 모델링도 드론 CNN과 공간 확산 모델이지 기상 모델이 아닙니다. 데이터도 ' +
        '같은 말을 합니다 — HLB는 나무를 죽이지 헥타르당 수확량을 낮추지 않습니다. 상파울루 오렌지 ' +
        '재배면적은 1991년 정점 대비 55% 감소(789,329→354,562 ha)했는데, 살아남은 면적의 단수는 ' +
        '2005년 이후 오히려 35% 상승했습니다. 감염목을 뽑아내면 남은 과수원이 더 젊고 관리가 좋기 ' +
        '때문입니다. 따라서 이 kg/ha 수치는 산업이 축소되는 중에도 우상향으로 보입니다. ' +
        '반드시 재배면적과 함께 읽어야 하며, 단독으로 해석하면 안 됩니다.',
    matopiba_algodao:
        '1999→2000년의 도약은 세하두 이전·신품종·규모화·경영의 생산 체계 전환이지 기상 호조가 ' +
        '아닙니다(관개가 아닙니다 — 브라질 면화 재배면적의 약 92%가 천수답이며, 천수답 섬유 단수 ' +
        '세계 1위입니다). 현대 체계 내부의 최대 비기상 요인은 목화바구미로, 최대 70%까지 감수를 ' +
        '일으키지만 그 압력은 파종기 조율과 방제 프로그램에 달려 있지 기후에 달려 있지 않습니다. ' +
        'MODIS NDVI가 면화 단수 모델에서 추세선 대비 거의 기여하지 못한다는 연구(Johnson, ORNL)도 ' +
        '있어, 위성 식생지수로 이 공백을 메우기는 어렵습니다.',
};

// Korean copy for India's "not weather" callout, same role as
// BRAZIL_NON_WEATHER_KO above: the model artifacts carry the canonical
// English in provenance.non_weather_drivers, this is the display layer.
const INDIA_NON_WEATHER_KO = {
    punjab_wheat:
        '펀자브·하리아나 밀은 정책이 날씨만큼 수확량을 흔듭니다. 최저지지가격(MSP) 보장 수매, ' +
        '관정 전력 보조금, 운하 로테이션 일정이 투입 강도와 파종 시기 자체를 정하며 어떤 기상 ' +
        '피처에도 잡히지 않습니다. 지하수 고갈은 이보다 느리게 진행되는 제약으로, 개별 시즌이 ' +
        '아니라 기술 추세선 자체를 서서히 끌어내리는 방향으로 작용합니다.',
    mp_soybean:
        '마디아프라데시 대두 재배면적은 대두·옥수수·두류의 상대가격에 따라 해마다 이동합니다. ' +
        '면적 배분이 바뀌면 날씨가 그대로여도 평균 단수가 달라집니다. 종자 갱신률과 황색모자이크 ' +
        '바이러스 발병 압력도 실질적인 해거리 요인이지만 어떤 기후 피처로도 포착되지 않습니다.',
    vidarbha_cotton:
        '이 세트에서 날씨로 가장 설명하기 어려운 작물입니다. 2002년 이후 Bt 면화 전환, 종자 ' +
        '가격·공급, 2015년 무렵부터 확산된 핑크볼웜의 Bt 저항성, 대두·비둘기콩 대비 최저지지가격 ' +
        '상대값이 매년 재배면적과 투입 강도를 움직입니다. ICRISAT은 면화를 섬유(lint) 기준으로 ' +
        '발표하므로, 조면율(ginning ratio)이 바뀌기만 해도 밭에서 아무 변화가 없어도 수치가 ' +
        '움직입니다.',
};

// Open hypotheses -- explicitly NOT established findings like the map above,
// but real gaps worth stating so a low score isn't read as "weather doesn't
// matter" when it might just mean "we're missing the right weather feature".
const BRAZIL_OPEN_QUESTIONS_KO = {
    matopiba_algodao:
        '검증되지 않은 가설입니다. 이 모델은 면화에 토양수분·근권 저류량 피처를 하나도 안 씁니다 — ' +
        '강수·폭염·VPD뿐입니다. MATOPIBA 세하두 토양은 모래질이라(대두 모델의 "유효수분용량" ' +
        '로직이 이걸 전제하지만, 그 처리는 면화가 아니라 대두에만 적용됨) 정확히 강수량만으론 ' +
        '식물이 실제 쓸 수 있는 물을 못 잡는 지역입니다. NASA POWER의 근권 토양수분(GWETROOT) — ' +
        '예전 brazil_soy_model에서 썼지만 이번 패키지에선 아예 안 불러온 변수 — 을 붙이면 비용 ' +
        '없이 바로 검증 가능합니다. 위성 토양수분(SMAP)이나 GRACE 총저류량을 더하면 더 확장됩니다.',
};

// Renders the Brazil regional yield forecasts.
//
// Deliberately shows the models that failed validation alongside the ones that
// passed, because hiding them would leave the reader assuming every number is
// weather-driven. Where `beats_trend` is false the figure is a trend
// extrapolation and is labelled as one; where a crop is moved mainly by
// something that is not weather at all -- cane's ratoon age profile, coffee's
// biennial bearing -- that reason is printed rather than left to be guessed at
// from a low score.
const renderBrazilYieldForecast = async (regionName) => {
    const keys = BRAZIL_REGION_MODELS[regionName];
    if (!keys) return false;

    const fc = await window.loadBrazilYieldForecast?.();
    if (!fc || !fc.regions) return false;

    const shown = keys.map(k => [k, fc.regions[k]]).filter(([, d]) => d);
    if (!shown.length) return false;

    const fmt = n => Math.round(n).toLocaleString();
    let html = '';

    for (const [key, d] of shown) {
        const vsLast = d.point - d.last_actual.yield;
        // The badge keys off weather skill, not the headline number. A model
        // can beat the trend on the strength of its lagged-yield features
        // while adding nothing meteorological, or the whole model can simply
        // fail to beat trend on any feature at all -- a climate panel must
        // not present either case as a working weather forecast.
        const skilled = d.skill.weather_driven;
        const color = d.weather_effect_pct < 0 ? '#fca5a5' : '#4ade80';
        // How much of the yield-deciding window has actually been observed.
        // Without this a mid-season projection off climatology looks identical
        // to a settled post-harvest number.
        const obsPct = d.provenance.critical_window_observed === null
            || d.provenance.critical_window_observed === undefined
            ? null
            : Math.round(d.provenance.critical_window_observed * 100);

        let badge;
        if (skilled) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(74,222,128,0.15); color:#4ade80;">검증 통과 · 기상 기여
                 ${(d.skill.weather_skill * 100).toFixed(0)}%</span>`;
        } else if (d.skill.beats_trend) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(148,163,184,0.18); color:#cbd5e1;">추세는 이기나 기상 기여는 없음
                 (${(d.skill.non_weather_features || []).join(', ') || '비기상 요인'} 기여)</span>`;
        } else {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(251,191,36,0.15); color:#fbbf24;">기상 신호 없음 · 추세 외삽값</span>`;
        }

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header"><span class="ind-title">${d.label}</span></div>
            <div style="margin-top:6px;">${badge}</div>
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${d.last_actual.year} 실적</span>
                    <div style="font-size:15px;">${fmt(d.last_actual.yield)} ${d.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${skilled ? color : '#cbd5e1'};">
                        ${fmt(d.point)} ${d.unit}</div>
                </div>
            </div>
            <div style="text-align:right; font-size:13px; margin-top:4px; color:${vsLast >= 0 ? '#4ade80' : '#fca5a5'};">
                전년 대비 ${vsLast >= 0 ? '+' : ''}${fmt(vsLast)} ${d.unit}
            </div>
            ${d.last_actual.note ? `
            <div style="margin-top:6px; font-size:11px; color:#94a3b8;">
                ※ IBGE가 ${d.last_actual.year + 1}년${
                    fc.season - d.last_actual.year > 2 ? `~${fc.season - 1}년` : ''
                } 확정 단수를 아직 발표하지 않았습니다. 결측이 아니라
                <strong style="color:#cbd5e1;">미발표</strong>이며, 현재 확보된 가장 최근 실적은
                ${d.last_actual.year}년입니다.
            </div>` : ''}
            <div style="margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.1); font-size:12px;">
                <div style="display:flex; justify-content:space-between; color:#cbd5e1;">
                    <span>68% 신뢰구간</span><span>${fmt(d.range_68[0])} – ${fmt(d.range_68[1])}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>기술 추세</span><span>${fmt(d.trend)} ${d.unit}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:${color}; margin-top:2px;">
                    <span>기상 효과</span>
                    <span>${d.weather_effect_pct >= 0 ? '+' : ''}${d.weather_effect_pct.toFixed(1)}%</span>
                </div>
            </div>
            ${(d.skill.top_effects || []).length ? `
            <div style="margin-top:8px; font-size:11px; color:#94a3b8;">
                <div style="margin-bottom:4px;">실제로 무엇이 이 모델을 움직이는가 (1σ당 수확량 효과)</div>
                ${d.skill.top_effects.slice(0, 3).map(e => `
                <div style="display:flex; justify-content:space-between; margin-top:2px;">
                    <span style="color:${e.is_weather ? '#cbd5e1' : '#fbbf24'};">
                        ${e.is_weather ? '🌦️' : '📋'} ${e.feature}
                    </span>
                    <span style="color:${e.effect_pct >= 0 ? '#4ade80' : '#fca5a5'};">
                        ${e.effect_pct >= 0 ? '+' : ''}${e.effect_pct.toFixed(1)}%
                    </span>
                </div>`).join('')}
            </div>` : ''}
            ${d.provenance.non_weather_drivers ? `
            <div style="margin-top:8px; padding:8px; background:rgba(251,191,36,0.08);
                        border-left:2px solid rgba(251,191,36,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#fbbf24;">날씨가 아닌 요인</strong><br>${
                    BRAZIL_NON_WEATHER_KO[key] || d.provenance.non_weather_drivers}
            </div>` : ''}
            ${BRAZIL_OPEN_QUESTIONS_KO[key] ? `
            <div style="margin-top:8px; padding:8px; background:rgba(96,165,250,0.08);
                        border-left:2px solid rgba(96,165,250,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#60a5fa;">미검증 가설 · 결측 가능성</strong><br>${
                    BRAZIL_OPEN_QUESTIONS_KO[key]}
            </div>` : ''}
            ${obsPct === null ? '' : `
            <div style="margin-top:10px; font-size:11px; color:#94a3b8;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>${d.provenance.season_complete
                        ? '수확기 종료 · 생육기 기상 확정'
                        : '생육 진행 중 · 결정 구간 관측률'}</span>
                    <span style="color:#cbd5e1;">${obsPct}%</span>
                </div>
                <div style="height:4px; background:rgba(255,255,255,0.08); border-radius:2px;">
                    <div style="height:100%; width:${obsPct}%; border-radius:2px;
                                background:${d.provenance.season_complete ? '#4ade80' : '#60a5fa'};"></div>
                </div>
            </div>`}
            <div style="margin-top:8px; padding:8px; background:rgba(0,0,0,0.2); border-radius:6px;
                        font-size:11px; color:#94a3b8;">
                기상 관측 ${d.provenance.weather_through}까지 · 방법론
                <span style="color:#cbd5e1;">${d.provenance.guide.split('/').slice(-2, -1)}</span>
            </div>
        </div>`;
    }

    const skippedNote = Object.entries(fc.skipped || {})
        .filter(([k]) => keys.includes(k))
        .map(([k]) => k);

    forecastCountryTitle.textContent = `브라질 지역 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        ${climateNavBackHtml(regionName.replace(' (Brazil)', ''))}
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:12px;">${regionName.replace(' (Brazil)', '')}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">작물 수</span>
                <span class="forecast-val">${shown.length}개 모델</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>지역별 개별 방법론 + 추세·기상편차 분해</strong><br>
                <span style="font-size:11px; font-weight:400;">
                지역마다 다른 수식을 씁니다. 마투그로수는 우기 시작일(Liebmann 이상누적),
                남부는 SPI·엘니뇨, 사프리냐 옥수수는 FAO-56 물수지입니다.
                </span>
            </div>
            ${skippedNote.length ? `
            <p style="font-size:11px; color:#fbbf24; margin-top:10px;">
                ${skippedNote.join(', ')}: 해당 생육 단계가 아직 도래하지 않아 예측하지 않음
            </p>` : ''}
        </div>
        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-bottom:4px;">
            갱신: ${new Date(fc.generated_at).toLocaleString()}
        </p>
        <p style="font-size:11px; color:#64748b; text-align:right;">
            출처: IBGE SIDRA(주별 수확량) · NASA POWER(기상) · NOAA CPC(ONI)
        </p>`;

    countryStatsTitleEl.textContent = regionName.replace(' (Brazil)', '');
    document.getElementById('country-stats-desc').textContent =
        '기후 모델링 문서(Regions/브라질) 지역별 수식 구현 · log 추세 + 기상편차';
    countryStatsContentEl.innerHTML = html;
    panelHide(macroPanelEl);
    panelShow(countryStatsPanelEl);
    return true;
};

// Renders the India regional yield forecasts.
//
// Same discipline as renderBrazilYieldForecast: a model that fails validation
// is shown, not hidden, flagged so the trend-extrapolation reads as one. India
// additionally carries the Indian Ocean Dipole alongside ENSO -- the soybean
// guide asks for both, since a positive IOD can hold the monsoon up through an
// El Nino year that ONI alone would score as a bad one.
const renderIndiaYieldForecast = async (regionName) => {
    const keys = INDIA_REGION_MODELS[regionName];
    if (!keys) return false;

    const fc = await window.loadIndiaYieldForecast?.();
    if (!fc || !fc.regions) return false;

    const shown = keys.map(k => [k, fc.regions[k]]).filter(([, d]) => d);
    if (!shown.length) return false;

    const fmt = n => Math.round(n).toLocaleString();
    let html = '';

    for (const [key, d] of shown) {
        const vsLast = d.point - d.last_actual.yield;
        const skilled = d.skill.weather_driven;
        const color = d.weather_effect_pct < 0 ? '#fca5a5' : '#4ade80';
        const obsPct = d.provenance.critical_window_observed === null
            || d.provenance.critical_window_observed === undefined
            ? null
            : Math.round(d.provenance.critical_window_observed * 100);

        let badge;
        if (skilled) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(74,222,128,0.15); color:#4ade80;">검증 통과 · 기상 기여
                 ${(d.skill.weather_skill * 100).toFixed(0)}%</span>`;
        } else if (d.skill.beats_trend) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(148,163,184,0.18); color:#cbd5e1;">추세는 이기나 기상 기여는 없음
                 (${(d.skill.non_weather_features || []).join(', ') || '비기상 요인'} 기여)</span>`;
        } else {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(251,191,36,0.15); color:#fbbf24;">기상 신호 없음 · 추세 외삽값</span>`;
        }

        const enso = d.enso || {};
        const iod = d.iod || {};

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header"><span class="ind-title">${d.label}</span></div>
            <div style="margin-top:6px;">${badge}</div>
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${d.last_actual.year} 실적</span>
                    <div style="font-size:15px;">${fmt(d.last_actual.yield)} ${d.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${skilled ? color : '#cbd5e1'};">
                        ${fmt(d.point)} ${d.unit}</div>
                </div>
            </div>
            <div style="text-align:right; font-size:13px; margin-top:4px; color:${vsLast >= 0 ? '#4ade80' : '#fca5a5'};">
                전년 대비 ${vsLast >= 0 ? '+' : ''}${fmt(vsLast)} ${d.unit}
            </div>
            <div style="margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.1); font-size:12px;">
                <div style="display:flex; justify-content:space-between; color:#cbd5e1;">
                    <span>68% 신뢰구간</span><span>${fmt(d.range_68[0])} – ${fmt(d.range_68[1])}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>기술 추세</span><span>${fmt(d.trend)} ${d.unit}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:${color}; margin-top:2px;">
                    <span>기상 효과</span>
                    <span>${d.weather_effect_pct >= 0 ? '+' : ''}${d.weather_effect_pct.toFixed(1)}%</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>엘니뇨/라니냐 (ONI)</span>
                    <span>${enso.oni_growing_season == null ? 'N/A' : enso.oni_growing_season.toFixed(2)} · ${enso.state || 'N/A'}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:2px;">
                    <span>인도양 쌍극자 (IOD)</span>
                    <span>${iod.dmi_growing_season == null ? 'N/A' : iod.dmi_growing_season.toFixed(2)} · ${iod.state || 'N/A'}</span>
                </div>
            </div>
            ${d.provenance.non_weather_drivers ? `
            <div style="margin-top:8px; padding:8px; background:rgba(251,191,36,0.08);
                        border-left:2px solid rgba(251,191,36,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#fbbf24;">날씨가 아닌 요인</strong><br>${
                    INDIA_NON_WEATHER_KO[key] || d.provenance.non_weather_drivers}
            </div>` : ''}
            ${obsPct === null ? '' : `
            <div style="margin-top:10px; font-size:11px; color:#94a3b8;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>${d.provenance.season_complete
                        ? '수확기 종료 · 생육기 기상 확정'
                        : '생육 진행 중 · 결정 구간 관측률'}</span>
                    <span style="color:#cbd5e1;">${obsPct}%</span>
                </div>
                <div style="height:4px; background:rgba(255,255,255,0.08); border-radius:2px;">
                    <div style="height:100%; width:${obsPct}%; border-radius:2px;
                                background:${d.provenance.season_complete ? '#4ade80' : '#60a5fa'};"></div>
                </div>
            </div>`}
            <div style="margin-top:8px; padding:8px; background:rgba(0,0,0,0.2); border-radius:6px;
                        font-size:11px; color:#94a3b8;">
                기상 관측 ${d.provenance.weather_through}까지 · 방법론
                <span style="color:#cbd5e1;">${d.provenance.guide.split('/').slice(-2, -1)}</span>
            </div>
        </div>`;
    }

    const skippedNote = Object.entries(fc.skipped || {})
        .filter(([k]) => keys.includes(k))
        .map(([k]) => k);

    forecastCountryTitle.textContent = `인도 지역 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        ${climateNavBackHtml(regionName.replace(' (India)', ''))}
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:12px;">${regionName.replace(' (India)', '')}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">작물 수</span>
                <span class="forecast-val">${shown.length}개 모델</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>지역별 개별 방법론 + 추세·기상편차 분해</strong><br>
                <span style="font-size:11px; font-weight:400;">
                펀자브 밀은 등숙기 종말기 열 스트레스(THSDD), 마디아프라데시 대두는 몬순 개시
                지연·개화기 무강우 연속일수, 비다르바 면화는 수분적자·해충 적합일수로 각각
                다른 수식을 씁니다.
                </span>
            </div>
            ${skippedNote.length ? `
            <p style="font-size:11px; color:#fbbf24; margin-top:10px;">
                ${skippedNote.join(', ')}: 해당 생육 단계가 아직 도래하지 않아 예측하지 않음
            </p>` : ''}
        </div>
        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-bottom:4px;">
            갱신: ${new Date(fc.generated_at).toLocaleString()}
        </p>
        <p style="font-size:11px; color:#64748b; text-align:right;">
            출처: ICRISAT DLD(지구별 수확량) · NASA POWER(기상) · NOAA CPC(ONI) · NOAA PSL(IOD)
        </p>`;

    countryStatsTitleEl.textContent = regionName.replace(' (India)', '');
    document.getElementById('country-stats-desc').textContent =
        '기후 모델링 문서(Regions/인도) 지역별 수식 구현 · log 추세 + 기상편차';
    countryStatsContentEl.innerHTML = html;
    panelHide(macroPanelEl);
    panelShow(countryStatsPanelEl);
    return true;
};

// Level 1 -- the world, with modelled countries picked out.
// Countries without a fitted model are drawn but not clickable, so the map
// never suggests a forecast exists where it does not.

// ---------------------------------------------------------------------------
// Climate view: world -> country drill-down.
//
// Level 1 is the world with modelled countries filled; hovering one shows a
// summary card, clicking enters it. Level 2 zooms to that country and marks
// its producing regions; clicking the country again (or the breadcrumb)
// returns to level 1.
// ---------------------------------------------------------------------------

let climateHover = null;

// --- Generic forecast loading -------------------------------------------
// One loader for every country, keyed on the `dataFile` in CLIMATE_COUNTRIES.
// Adding a country is then: drop the JSON in public/data/ and add a config
// entry -- no new loader, no new render branch.
const climateForecastCache = {};
const loadClimateForecast = async (cfg) => {
    if (!cfg.dataFile) return null;
    if (cfg.dataFile in climateForecastCache) return climateForecastCache[cfg.dataFile];
    try {
        const res = await fetch(`/public/data/${cfg.dataFile}`);
        climateForecastCache[cfg.dataFile] = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn(`[Climate] ${cfg.dataFile} unavailable`, err);
        climateForecastCache[cfg.dataFile] = null;
    }
    return climateForecastCache[cfg.dataFile];
};

// --- Shape normalisation -------------------------------------------------
// The per-country pipelines were written at different times against different
// guides, so the same quantity goes by several names. Rather than force a
// migration of every producer, the reader accepts the known spellings and
// hands the renderers one shape. A country whose JSON uses none of these
// still renders -- it just contributes no rows, instead of throwing.
//
// Two structural families exist:
//   nested  regions[k].crops[c]  -- one region hosting several crops (US)
//   flat    regions[k]           -- the region entry *is* the crop
const num = v => (typeof v === 'number' && isFinite(v) ? v : null);

const normalizeCrop = (entry, group, label, parent = {}, regionKey = null) => {
    // Indonesia puts the whole forecast under `yield_kg_ha`; everyone else
    // has `point` as a plain number at the top level.
    const f = (entry.point && typeof entry.point === 'object') ? entry.point
        : (entry.yield_kg_ha && typeof entry.yield_kg_ha === 'object') ? entry.yield_kg_ha
        : entry;

    // Most countries use a flat skill object. Indonesia nests yield/area/
    // production under skill.yield with climate_gate metadata.
    const skillRoot = entry.skill || f.skill || {};
    const skill = (skillRoot.yield && typeof skillRoot.yield === 'object')
        ? skillRoot.yield
        : skillRoot;
    const la = entry.last_actual || {};
    const trend = num(f.trend) ?? num(f.diagnostic_trend);
    const weather = num(f.weather_effect);
    const skillVs = num(skill.skill_vs_trend_only);
    const climateGate = skill.climate_gate || f.climate_gate || null;
    const gateStopped = climateGate
        && String(climateGate.status || '').includes('insufficient');

    return {
        group,
        regionKey,
        label: label || entry.label_ko || entry.label || entry.target_label || entry.crop || '—',
        point: num(f.point),
        unit: entry.unit || f.unit || 'kg/ha',
        lastActual: num(la.yield) ?? num(la.value) ?? num(la.yield_kg_ha),
        lastActualYear: num(la.year),
        // Four ways to say "do not trust this as weather skill":
        // low_confidence flag, beats_trend false, skill_vs_trend < 0.20,
        // climate_gate stopped for short sample (Indonesia).
        lowConfidence: skill.low_confidence === true
            || skillRoot.low_confidence === true
            || entry.low_confidence === true
            || skill.beats_trend === false
            || skillRoot.beats_trend === false
            || (skillVs !== null && skillVs < 0.20)
            || gateStopped,
        skillVsTrend: skillVs,
        climateGate,
        // Percent deviation from trend -- the number that says whether the
        // season is running hot or cold.
        pct: num(entry.weather_effect_pct)
            ?? (trend && weather !== null && Math.abs(trend) > 1e-9
                ? (weather / trend) * 100 : null),
        // "no forecast here" is declared on the region, not on each crop under
        // it (see DATA_LAYOUT.md), so the flag and its explanation are
        // inherited downward.
        forecastAvailable: entry.forecast_available !== false
            && parent.forecast_available !== false
            && num(f.point) !== null,
        reason: entry.reason_ko || entry.reason
            || parent.reason_ko || parent.reason
            || (gateStopped
                ? `기상 피처 게이트 정지 (표본 ${climateGate.available_seasons ?? '?'} / 필요 ${climateGate.required_seasons ?? '?'})`
                : null),
    };
};

const normalizeForecast = (fc, onlyKeys = null) => {
    if (!fc || !fc.regions) return [];
    const out = [];
    const keySet = onlyKeys ? new Set(onlyKeys) : null;
    for (const [regionKey, region] of Object.entries(fc.regions)) {
        if (keySet && !keySet.has(regionKey)) continue;
        const regionLabel = region.label_ko || region.label || null;
        if (region.crops && typeof region.crops === 'object') {
            for (const crop of Object.values(region.crops)) {
                out.push(normalizeCrop(
                    crop, regionLabel, crop.label_ko || crop.label, region, regionKey));
            }
        } else {
            out.push(normalizeCrop(region, null, regionLabel, {}, regionKey));
        }
    }
    return out;
};

// West Africa (and similar) countries publish outlooks without a yield model.
// Do NOT key only on forecast_available:false — some forecast countries have
// individual regions gated off (e.g. Argentina wheat) while still modelling others.
const isClimateReference = (fc, cfg = null) =>
    !!(cfg?.panelMode === 'reference'
        || fc?.panel_mode === 'reference'
        || (fc?.forecast_available === false
            && (Array.isArray(fc.government_outlooks) || Array.isArray(fc.research_notes))));

const fmtRefNumber = (v, unit) => {
    if (v == null || !isFinite(Number(v))) return '—';
    const n = Number(v);
    if (unit === 'ha' || unit === 'tonnes' || unit === 't') {
        return Math.round(n).toLocaleString('en-US');
    }
    return n.toLocaleString('en-US');
};

const renderSourceLink = (url, label) => {
    if (!url) return '';
    const text = label || '출처';
    return `<a class="climate-ref-link" href="${url}" target="_blank" rel="noopener noreferrer">${text} ↗</a>`;
};

const renderClimateReferencePanelHtml = (cfg, fc, meta = {}) => {
    const lv = meta.lv || 'blue';
    const pol = meta.pol || {};
    const title = fc.title_ko || cfg.modelName || `${cfg.label} 참고자료`;
    const reason = fc.reason_ko || fc.reason || '데이터 한계로 예측하지 않습니다.';
    const outlooks = Array.isArray(fc.government_outlooks) ? fc.government_outlooks : [];
    const notes = Array.isArray(fc.research_notes) ? fc.research_notes : [];
    const sources = Array.isArray(fc.sources) ? fc.sources : [];

    const outlookHtml = outlooks.length
        ? outlooks.map((o) => {
            const unit = o.unit || '';
            const unitKo = unit === 'tonnes' || unit === 't' ? 't'
                : unit === 'ha' ? 'ha' : unit;
            return `<div class="climate-ref-item">
                <div class="gi-top">
                    <span>${o.agency_ko || o.agency || '기관'}
                        ${o.season ? `<span class="climate-chip" style="margin-left:6px;">${o.season}</span>` : ''}
                    </span>
                    <span>${fmtRefNumber(o.value, unit)} ${unitKo}</span>
                </div>
                <div class="gi-note">
                    <strong style="color:#cbd5e1;font-weight:600;">${o.metric_ko || o.metric || ''}</strong>
                    ${o.status_ko ? ` · ${o.status_ko}` : ''}
                    ${o.note_ko ? ` · ${o.note_ko}` : ''}
                    ${o.url ? ` · ${renderSourceLink(o.url, o.url_label || o.agency || '원문')}` : ''}
                </div>
            </div>`;
        }).join('')
        : '<div class="climate-sub">등록된 기관 전망이 없습니다.</div>';

    const notesHtml = notes.length
        ? notes.map((n) => {
            const links = (n.links || []).map((l) => renderSourceLink(l.url, l.label)).join(' · ');
            return `<div class="climate-ref-note">
                <div class="cm-title" style="margin-bottom:4px;">${n.title_ko || n.title || '메모'}</div>
                <div class="climate-sub">${n.body_ko || n.body || ''}</div>
                ${links ? `<div class="climate-ref-links">${links}</div>` : ''}
            </div>`;
        }).join('')
        : '<div class="climate-sub">조사 메모 없음</div>';

    const sourcesHtml = sources.length
        ? `<ul class="climate-ref-source-list">${sources.map((s) => {
            const name = typeof s === 'string' ? s : (s.name || s.url);
            const url = typeof s === 'string' ? s : s.url;
            const supports = typeof s === 'object' && s.supports ? ` — ${s.supports}` : '';
            return `<li>${url
                ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${name}</a>${supports}`
                : `${name}${supports}`}</li>`;
        }).join('')}</ul>`
        : '';

    return `
        <div class="climate-scroll">
            ${climateNavBackHtml(cfg.label)}
            <div class="climate-trade-banner">
                <div>
                    <div class="tb-label">무역 · 수출 통제</div>
                    <div class="tb-note">${pol.note || '상태 메모 없음'}</div>
                </div>
                <span class="climate-status-pill ${lv}">${tradePolicyLabelKo(lv)}</span>
            </div>
            <div class="climate-card climate-ref-banner">
                <div class="climate-metric-row" style="border:none;padding:0;">
                    <span class="nm" style="font-size:13px;font-weight:600;color:#e2e8f0;">${title}</span>
                    <span class="climate-status-pill orange">예측 불가 / 참고 자료</span>
                </div>
                <div class="climate-sub" style="margin-top:8px;">시즌 ${fc.season || '—'} · ${reason}</div>
            </div>
            <div class="climate-card">
                <h3>주요 정부·기관 전망</h3>
                <div class="climate-sub" style="margin-bottom:8px;">
                    ICCO·USDA GAIN·FAOSTAT 등 출처별 수치 · 예측치가 아님
                </div>
                ${outlookHtml}
            </div>
            <div class="climate-card">
                <h3>조사 메모</h3>
                ${notesHtml}
            </div>
            ${sourcesHtml ? `<div class="climate-card">
                <h3>출처 링크</h3>
                ${sourcesHtml}
            </div>` : ''}
            <p style="font-size:10px;color:#64748b;">
                갱신: ${fc.generated_at ? new Date(fc.generated_at).toLocaleString() : '—'}
                · 서아프리카 코코아는 모델 forecast를 발행하지 않습니다.
            </p>
        </div>`;
};

// --- Climate dashboard v2 (world global climate + country drill-down) -----

let climateGlobalCache = null;
let climateCityWx = {};

const loadClimateGlobal = async () => {
    if (climateGlobalCache) return climateGlobalCache;
    try {
        const res = await fetch('/public/data/climate_global_v1.json', { cache: 'no-cache' });
        climateGlobalCache = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn('[Climate] climate_global_v1 unavailable', err);
        climateGlobalCache = null;
    }
    return climateGlobalCache;
};

let cityWxDoc = null;
let cityWxPromise = null;

/** Producing-region weather against local normals (scripts/build_city_wx.py). */
const loadCityWx = () => {
    if (cityWxPromise) return cityWxPromise;
    cityWxPromise = fetch('/public/data/city_wx_v1.json', { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { cityWxDoc = d; return d; })
        .catch(() => null);
    return cityWxPromise;
};

const refreshClimateCityTemps = async () => {
    const g = await loadClimateGlobal();
    if (!g?.cities?.length) return;
    await Promise.all(g.cities.map(async (c) => {
        try {
            const url = `https://api.open-meteo.com/v1/forecast?latitude=${c.lat}&longitude=${c.lon}&current=temperature_2m`;
            const res = await fetch(url);
            if (!res.ok) return;
            const j = await res.json();
            const t = j.current?.temperature_2m;
            if (typeof t === 'number') climateCityWx[c.name] = t;
        } catch (_) { /* offline ok */ }
    }));
};

const climateCountrySummary = async (cfg) => {
    const fc = await loadClimateForecast(cfg);
    if (!fc) return null;
    if (isClimateReference(fc, cfg)) {
        return {
            season: fc.season,
            regionCount: cfg.regions.length,
            cropCount: 0,
            meanPct: null,
            lowShare: 0,
            reference: true,
            titleKo: fc.title_ko || cfg.modelName || cfg.label,
            reason: fc.reason_ko || fc.reason || null,
        };
    }
    const crops = normalizeForecast(fc);
    if (!crops.length) return null;
    const scored = crops.filter(c => c.pct !== null);
    const meanPct = scored.length
        ? scored.reduce((s, c) => s + c.pct, 0) / scored.length
        : null;
    return {
        season: fc.season,
        regionCount: cfg.regions.length,
        cropCount: crops.length,
        meanPct,
        lowShare: crops.length
            ? crops.filter(c => c.lowConfidence).length / crops.length
            : 0,
        reference: false,
    };
};

const regionStressFromPct = (pct) => {
    if (pct === null || pct === undefined) return { level: 'neutral', rgba: [148, 163, 184, 180], ko: '데이터 부족' };
    if (pct <= -4) return { level: 'high', rgba: [248, 113, 113, 210], ko: '기상 불리' };
    if (pct <= -1.5) return { level: 'warn', rgba: [251, 146, 60, 210], ko: '기상 약세' };
    return { level: 'ok', rgba: [74, 222, 128, 210], ko: '기상 양호' };
};

const isoToCountryName = () => {
    const m = {};
    for (const [name, cfg] of Object.entries(CLIMATE_COUNTRIES)) m[cfg.iso] = name;
    return m;
};

/**
 * View-state guard. Curvature comes from the graticule and the bowed arcs, not
 * from tilting or rounding the map, so pitch stays at zero and only zoom is
 * clamped -- scrolling should grow the map (req 2) without losing the world.
 */
const MAP_MIN_ZOOM = 0.5;
const MAP_MAX_ZOOM = 7.5;
const clampGlobeView = (vs = {}) => ({
    ...vs,
    latitude: Math.min(80, Math.max(-70, vs.latitude ?? 15)),
    zoom: Math.min(MAP_MAX_ZOOM, Math.max(MAP_MIN_ZOOM, vs.zoom ?? 0.85)),
    // No pitch. Tilting the plane was the previous attempt at curvature and it
    // rendered the world as a trapezoid.
    pitch: 0,
    bearing: 0,
    minZoom: MAP_MIN_ZOOM,
    maxZoom: MAP_MAX_ZOOM,
});
// Old name kept for any caller still reaching for it.
const clampMapNoAntarctica = clampGlobeView;

/** HUD frame over the map during a country drill-down (req 4). */
const climateTargetHudEl = document.getElementById('climate-target-hud');
const setClimateTargetHud = (cfg, zoom = null) => {
    if (!climateTargetHudEl) return;
    if (!cfg) {
        climateTargetHudEl.classList.add('hidden');
        return;
    }
    climateTargetHudEl.classList.remove('hidden');
    climateTargetHudEl.innerHTML = `
        <span class="hud-corner tl"></span><span class="hud-corner tr"></span>
        <span class="hud-corner bl"></span><span class="hud-corner br"></span>
        <div class="hud-chip">
            <span class="hud-kicker">TARGET</span>
            <span class="hud-dot">·</span>
            <span class="hud-name">${(cfg.iso || cfg.label || '').toUpperCase()}</span>
            ${zoom ? `<span class="hud-zoom">ZOOM ${Number(zoom).toFixed(1)}×</span>` : ''}
        </div>`;
};

// --- Producing-region labels as projected HTML (req 4) --------------------
const climateRegionLabelsEl = document.getElementById('climate-region-labels');
let climateLabelPoints = [];

/** Great-circle distance in degrees, used to hide labels on the far hemisphere. */
const angularDistanceDeg = (a, b) => {
    const rad = Math.PI / 180;
    const [lon1, lat1] = a.map((v) => v * rad);
    const [lon2, lat2] = b.map((v) => v * rad);
    const d = Math.sin(lat1) * Math.sin(lat2)
        + Math.cos(lat1) * Math.cos(lat2) * Math.cos(lon1 - lon2);
    return Math.acos(Math.max(-1, Math.min(1, d))) / rad;
};

const positionClimateRegionLabels = () => {
    if (!climateRegionLabelsEl) return;
    if (!climateLabelPoints.length || climateLevel !== 'country' || currentCommodity !== 'climate') {
        climateRegionLabelsEl.classList.add('hidden');
        return;
    }
    const viewport = deckgl.getViewports?.()[0];
    if (!viewport) return;
    climateRegionLabelsEl.classList.remove('hidden');
    const center = [viewport.longitude, viewport.latitude];
    climateRegionLabelsEl.querySelectorAll('.region-label').forEach((el, i) => {
        const p = climateLabelPoints[i];
        if (!p) return;
        const [x, y] = viewport.project(p.coordinates);
        el.style.display = 'block';
        el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    });
};

const setClimateRegionLabels = (points) => {
    if (!climateRegionLabelsEl) return;
    climateLabelPoints = points || [];
    climateRegionLabelsEl.innerHTML = climateLabelPoints.map((p) => {
        const pctColor = p.meanPct == null ? '#94a3b8' : (p.meanPct < 0 ? '#fca5a5' : '#4ade80');
        const pct = p.meanPct == null ? ''
            : `<span class="rl-pct" style="color:${pctColor};">${p.meanPct >= 0 ? '+' : ''}${p.meanPct.toFixed(1)}%</span>`;
        const val = p.point == null ? '예측 없음'
            : `${fmtYield(p.point, p.unit)} <span class="rl-unit">${p.unit || ''}</span>`;
        return `<div class="region-label climate-click" role="button" tabindex="0"
                     data-climate-region="${p.name}" aria-label="${p.label} 상세">
            <div class="rl-name">${p.label}</div>
            <div class="rl-val">${val} ${pct}</div>
        </div>`;
    }).join('');
    positionClimateRegionLabels();
};
wireClimateDomClicks(climateRegionLabelsEl);

/**
 * Says how finished a country's model is, right where its numbers are.
 *
 * Without this China reads exactly like the US: same layout, same decimals.
 * Its three regions all score worse than a trend-only baseline (-0.57 to
 * -1.60) and India's single published region scores 0.009, so presenting
 * either as settled would be the interface lying on the model's behalf.
 */
const MODEL_STATUS_KO = {
    validated: { label: '검증 통과', cls: 'green' },
    provisional: { label: '부분 검증', cls: 'yellow' },
    training: { label: '학습 중', cls: 'orange' },
};

const setModelStatusBadge = (cfg) => {
    const host = document.getElementById('current-view-desc');
    if (!host) return;
    document.getElementById('model-status-badge')?.remove();
    if (!cfg?.modelStatus) return;
    const s = MODEL_STATUS_KO[cfg.modelStatus] || { label: cfg.modelStatus, cls: 'blue' };
    const el = document.createElement('div');
    el.id = 'model-status-badge';
    el.className = 'model-status-badge';
    el.innerHTML = `
        <span class="climate-status-pill ${s.cls}">${s.label}</span>
        ${cfg.statusNote ? `<span class="ms-note">${cfg.statusNote}</span>` : ''}`;
    host.insertAdjacentElement('afterend', el);
};

const climateWorldViewState = () => (
    // Latitude 15 centres the modelled belt -- US, Brazil, India, SE Asia --
    // rather than leaving it at the bottom of the frame.
    { longitude: 5, latitude: 12, zoom: 0.85, pitch: 0, bearing: 0 }
);

const setClimateMapLegend = (mode) => {
    if (!climateMapLegendEl) return;
    climateMapLegendEl.classList.remove('framed', 'world-mini', 'country-leg');
    if (mode === 'world') {
        climateMapLegendEl.classList.remove('hidden');
        climateMapLegendEl.classList.add('world-mini');
        // Top-right, no card frame — just soft color keys (req 11).
        climateMapLegendEl.innerHTML = `
            <div class="mini-leg-head">무역 · 수출 통제</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#38bdf8"></span>정상</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#facc15"></span>제한</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#fb923c"></span>금지1</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#f87171"></span>금지2+</div>
            <div class="mini-leg-head" style="margin-top:9px;">해수면 수온 편차</div>
            <div class="mini-leg-row"><span class="swatch sst-cool"></span>낮음 (−)</div>
            <div class="mini-leg-row"><span class="swatch sst-warm"></span>높음 (+)</div>
            <div class="mini-leg-note">1971–2000 평년 대비</div>`;
    } else if (mode === 'reference') {
        climateMapLegendEl.classList.remove('hidden');
        climateMapLegendEl.classList.add('world-mini');
        climateMapLegendEl.innerHTML = `
            <div class="mini-leg-row"><span class="swatch" style="background:#fb923c"></span>참고(예측없음)</div>`;
    } else if (mode === 'country') {
        climateMapLegendEl.classList.remove('hidden');
        climateMapLegendEl.classList.add('country-leg');
        climateMapLegendEl.innerHTML = `
            <div class="mini-leg-head">산지 기상효과</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#f87171"></span>고온·건조 스트레스</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#fb923c"></span>주의</div>
            <div class="mini-leg-row"><span class="swatch" style="background:#4ade80"></span>양호</div>
            <div class="mini-leg-head" style="margin-top:9px;">해수면 수온 편차</div>
            <div class="mini-leg-row"><span class="swatch sst-cool"></span>낮음 (−)</div>
            <div class="mini-leg-row"><span class="swatch sst-warm"></span>높음 (+)</div>
            <div class="mini-leg-note">1971–2000 평년 대비</div>`;
    } else {
        climateMapLegendEl.classList.add('hidden');
        climateMapLegendEl.innerHTML = '';
    }
};

const renderEnsoBars = (series) => {
    if (!series?.length) return '';
    const vals = series.map(s => s.oni);
    const maxAbs = Math.max(0.5, ...vals.map(v => Math.abs(v)));
    return `<div class="climate-bars" title="ONI 최근 궤적">
        ${series.map(s => {
            const h = Math.max(4, Math.round((Math.abs(s.oni) / maxAbs) * 46));
            const col = s.oni < 0 ? 'rgba(56,189,248,0.75)' : 'rgba(248,113,113,0.75)';
            return `<span style="height:${h}px;background:${col}" title="${s.label}: ${s.oni}"></span>`;
        }).join('')}
    </div>`;
};

const renderClimateWorldLeft = async () => {
    const g = await loadClimateGlobal();
    await loadCityWx();
    const enso = g?.enso || {};
    const iod = g?.iod || {};
    const amo = g?.north_atlantic || {};
    const continents = g?.continent_temp_anomaly?.values || [];
    const maxAbsC = Math.max(0.5, ...continents.map(c => Math.abs(c.anomaly || 0)));

    forecastCountryTitle.textContent = '전역 기후 모니터';
    forecastContentEl.innerHTML = `
        <div class="climate-scroll">
            <div class="climate-card">
                <h3>ENSO · Niño 3.4 <span class="src-tag">${enso.source || 'NOAA CPC'}</span></h3>
                <div class="climate-big ${enso.latest_c < 0 ? 'neg' : 'pos'}">
                    ${enso.latest_c != null ? (enso.latest_c > 0 ? '+' : '') + enso.latest_c.toFixed(1) + '°C' : '—'}
                </div>
                <div class="climate-sub">${enso.state_ko || '상태 미정'}
                    ${enso.prob_continue_pct != null ? ` · 지속 확률 ${enso.prob_continue_pct}%` : ''}</div>
                ${renderEnsoBars(enso.series)}
            </div>
            <div class="climate-card">
                <h3>IOD · 인도양 쌍극자 <span class="src-tag">${iod.source || 'NOAA PSL'}</span></h3>
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div class="climate-big ${ (iod.latest||0) >= 0 ? 'pos' : 'neg'}" style="font-size:22px;">
                        ${iod.latest != null ? ((iod.latest >= 0 ? '+' : '') + iod.latest.toFixed(2)) : '—'}
                    </div>
                    <span class="climate-status-pill ${ (iod.latest||0) >= 0 ? 'red' : 'blue' }">${iod.state_ko || '—'}</span>
                </div>
                <div class="climate-sub">${iod.note_ko || ''}</div>
            </div>
            <div class="climate-card">
                <h3>해수면 수온(SST) 편차 · 지도 워시</h3>
                <div class="climate-metric-row">
                    <span class="nm">Niño 3.4</span>
                    <span class="vl">${enso.latest_c != null ? ((enso.latest_c >= 0 ? '+' : '') + enso.latest_c.toFixed(1) + '°C') : '—'}</span>
                </div>
                <div class="climate-metric-row">
                    <span class="nm">IOD / 북대서양</span>
                    <span class="vl">${iod.latest != null ? ((iod.latest >= 0 ? '+' : '') + Number(iod.latest).toFixed(2)) : '—'}
                        · AMO ${amo.anomaly_c != null ? ((amo.anomaly_c >= 0 ? '+' : '') + amo.anomaly_c.toFixed(2) + '°C') : '—'}</span>
                </div>
                <div class="climate-sub">지도 바다 위 옅은 원 = 주요 해역 SST 편차 seed (격자 전체 수온 제품 아님). 색은 일부러 옅게.</div>
            </div>
            <div class="climate-card">
                <h3>북대서양 SST (요약 seed)</h3>
                <div class="climate-metric-row">
                    <span class="nm">${amo.index || 'AMO'}</span>
                    <span class="vl">${amo.anomaly_c != null ? ((amo.anomaly_c>=0?'+':'') + amo.anomaly_c.toFixed(2) + '°C') : '—'}</span>
                </div>
                <div class="climate-sub">${amo.state_ko || ''} · 시계열 연동 예정</div>
            </div>
            <div class="climate-card">
                <h3>대륙 평균 기온 편차 (${g?.continent_temp_anomaly?.baseline || 'baseline'})</h3>
                ${continents.map(c => {
                    const w = Math.round((Math.abs(c.anomaly) / maxAbsC) * 100);
                    return `<div class="climate-hbar">
                        <span>${c.name}</span>
                        <div class="track"><div class="fill" style="width:${w}%"></div></div>
                        <span style="color:#fca5a5;text-align:right;">+${Number(c.anomaly).toFixed(2)}</span>
                    </div>`;
                }).join('') || '<div class="climate-sub">데이터 없음</div>'}
            </div>
            <div class="climate-card">
                <h3>주요 산지 기상 <span class="src-tag">최근 ${cityWxDoc?.window?.days ?? 30}일 · ${cityWxDoc?.normal || '평년 대비'}</span></h3>
                ${(cityWxDoc?.cities || g?.cities || []).map(c => {
                    const w = (cityWxDoc?.cities || []).find(x => x.name === c.name) || {};
                    const live = climateCityWx[c.name];
                    // Departure carries the meaning: 27°C says nothing without
                    // knowing whether 27 is normal there this month.
                    const ta = w.temp_anom_c;
                    const pa = w.precip_anom_pct;
                    const tc = ta == null ? '#94a3b8' : (ta > 0 ? '#fca5a5' : '#7dd3fc');
                    const pc = pa == null ? '#94a3b8' : (pa < 0 ? '#fbbf24' : '#4ade80');
                    return `<div class="city-wx-row">
                        <span class="nm">${c.label_ko || c.name}</span>
                        <span class="wx-pair">
                            <span class="wx-v">${w.temp_c != null ? w.temp_c.toFixed(1)
                                : (live != null ? live.toFixed(1) : '—')}°C</span>
                            ${ta != null ? `<span class="wx-a" style="color:${tc}">${ta >= 0 ? '+' : ''}${ta.toFixed(1)}</span>` : ''}
                        </span>
                        <span class="wx-pair">
                            <span class="wx-v">${w.precip_mm != null ? Math.round(w.precip_mm) : '—'}mm</span>
                            ${pa != null ? `<span class="wx-a" style="color:${pc}">${pa >= 0 ? '+' : ''}${pa}%</span>` : ''}
                        </span>
                    </div>`;
                }).join('') || '<div class="climate-sub">도시 seed 없음</div>'}
            </div>
            <p style="font-size:10px;color:#64748b;line-height:1.5;">
                지수 seed: <code>climate_global_v1.json</code>. 상세 시계열·파생상품 풀셋은 이후 갱신.
            </p>
        </div>`;
};

const renderClimateWorldRight = async () => {
    // Req 11: climate world has no right column — trade colors live as a
    // frameless mini legend on the map. Keep this as a no-op for callers.
    if (climateRightPanelEl) climateRightPanelEl.classList.add('hidden');
    if (climateRightContentEl) climateRightContentEl.innerHTML = '';
};

const showClimateWorld = async () => {
    try {
    await loadClimateRegistry();
    climateLevel = 'world';
    climateCountry = null;
    climateHover = null;
    hideClimateTooltip();

    currentViewTitle.textContent = '작황 모니터';
    currentViewDesc.textContent = '작황·기후·수출통제 한눈에 · 국가를 클릭하면 산지별로 들어갑니다';
    setClimateCommodityHeader('climate');
    totalVolumeEl.textContent = `${Object.keys(CLIMATE_COUNTRIES).length}개국`;
    topExporterEl.textContent = 'Trade status';

    document.getElementById('commodity-info-panel')?.classList.remove('hidden');

    climateSelectedRegion = null;
    setClimateMapLegend('world');
    await renderClimateWorldLeft();
    await renderClimateWorldRight();
    // World: left only — no right dashboard
    togglePanels({
        forecast: true,
        climateRight: !!selectedOceanRegion,
        left: true,
        right: !!selectedOceanRegion,
        map: true,
    });
    if (selectedOceanRegion) {
        const r = (sstRegionsDoc?.regions || []).find((x) => x.id === selectedOceanRegion);
        if (r) renderOceanRegionPanel(r);
    }
    panelHide(macroPanelEl);
    panelHide(countryStatsPanelEl);
    panelShow(forecastPanelEl);

    await loadClimateGlobal();
    await loadSst();
    await loadSstRegions();

    const labels = Object.entries(CLIMATE_COUNTRIES).map(([name, cfg]) => {
        const coords = cfg.regions[0]?.coordinates;
        if (!coords) return null;
        return {
            name, label: cfg.label, coordinates: coords,
            level: tradePolicyLevel(name),
        };
    }).filter(Boolean);

    if (chartView) {
        chartView.classList.add('hidden');
        chartView.style.pointerEvents = 'none';
    }
    mapContainer.style.display = 'block';
    mapContainer.style.pointerEvents = 'auto';
    ensureClimateMapPointerFallback();

    setClimateTargetHud(null);
    setClimateRegionLabels([]);
    const worldView = clampGlobeView(climateWorldViewState());
    currentViewState = worldView;

    deckgl.setProps({
        // Real globe. The basemap is our own vector world (worldBaseLayers), so
        // there is no flat raster underneath for the sphere to fight with.
        views: [new MapView({ id: 'map', controller: true, repeat: true })],
        viewState: worldView,
        controller: { dragRotate: false, touchRotate: false },
        pickingRadius: 18,
        getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab'),
        onClick: handleClimateDeckClick,
        onHover: handleClimateDeckHover,
        onViewStateChange: ({ viewState }) => {
            if (climateLevel !== 'world' || currentCommodity !== 'climate') return;
            const next = clampGlobeView(viewState);
            currentViewState = next;
            deckgl.setProps({ viewState: next });
        },
        layers: [
            // Ocean sphere + land first; the SST wash then tints the water and
            // the trade-status fills paint over the countries.
            ...worldBaseLayers({
                id: 'climate-world',
                water: [sstWashLayer(null, 'climate-sst-wash')],
            }),
            new GeoJsonLayer({
                id: 'climate-countries',
                data: worldGeo(),
                stroked: true,
                filled: true,
                lineWidthMinPixels: 1,
                getFillColor: (f) => {
                    if (isAntarcticaFeature(f)) return [0, 0, 0, 0];
                    const key = featureCountryKey(f);
                    if (!key) return TRADE_FILL.none;
                    return TRADE_FILL[tradePolicyLevel(key)] || TRADE_FILL.blue;
                },
                getLineColor: (f) => {
                    if (isAntarcticaFeature(f)) return [0, 0, 0, 0];
                    const key = featureCountryKey(f);
                    if (!key) return TRADE_LINE.none;
                    return TRADE_LINE[tradePolicyLevel(key)] || TRADE_LINE.blue;
                },
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 70],
                updateTriggers: {
                    getFillColor: [climateLevel, Object.keys(CLIMATE_TRADE_POLICY).join()],
                    getLineColor: [climateLevel],
                },
            }),
            // Invisible until hovered or selected; the grid already carries the
            // colour, so a second painted circle would only repeat it.
            oceanHitLayer(),
            new ScatterplotLayer({
                id: 'climate-country-pins',
                data: labels,
                pickable: true,
                stroked: true,
                filled: true,
                opacity: 0.88,
                radiusMinPixels: 10,
                radiusMaxPixels: 28,
                lineWidthMinPixels: 1.5,
                getPosition: (d) => d.coordinates,
                getRadius: 140000,
                getFillColor: (d) => TRADE_FILL[d.level] || TRADE_FILL.blue,
                getLineColor: [255, 255, 255, 160],
                autoHighlight: true,
                highlightColor: [255, 255, 255, 160],
            }),
        ],
    });

    refreshClimateCityTemps().then(() => {
        if (climateLevel === 'world') renderClimateWorldLeft();
    });
    } catch (err) {
        console.error('[Climate] showClimateWorld failed', err);
    }
};
window.showClimateWorld = showClimateWorld;

const showClimateTooltip = async (info, name, cfg) => {
    const s = await climateCountrySummary(cfg);
    if (climateLevel !== 'world') return;
    const g = await loadClimateGlobal();
    const tAnom = g?.map_temp_anomaly_seed?.[name];
    const lv = tradePolicyLevel(name);
    const pol = CLIMATE_TRADE_POLICY[name] || {};
    const color = s?.meanPct != null && s.meanPct < 0 ? '#fca5a5' : '#4ade80';
    positionTooltipAt(info);
    tooltipEl.classList.remove('hidden');
    const body = s?.reference
        ? `<div class="tooltip-stat"><span>모드</span>
            <span class="climate-status-pill orange">예측 불가 · 참고</span></div>
           <div class="tooltip-stat"><span>시즌</span><span>${s.season || '—'}</span></div>
           <div style="margin-top:6px;font-size:10px;color:#94a3b8;line-height:1.4;">
             ${s.reason || '정부·기관 전망 + 조사 메모 (예측 아님)'}</div>`
        : (s ? `
        <div class="tooltip-stat"><span>작황 기상효과</span>
            ${s.meanPct === null
                ? '<span style="color:#94a3b8;">요약 불가</span>'
                : `<span style="color:${color}; font-weight:bold;">
                   ${s.meanPct >= 0 ? '+' : ''}${s.meanPct.toFixed(1)}%</span>`}</div>
        <div class="tooltip-stat"><span>대상 작물 / 산지</span>
            <span>${s.cropCount}개 · ${s.regionCount}개</span></div>`
        : '<div class="tooltip-stat"><span>예측 로딩…</span></div>');
    tooltipEl.innerHTML = `
        <div class="tooltip-title">${cfg.label}${cfg.modelName ? ` · ${cfg.modelName}` : ''}</div>
        <div class="tooltip-stat"><span>무역 상태</span>
            <span class="climate-status-pill ${lv}">${tradePolicyLabelKo(lv)}</span></div>
        ${tAnom != null ? `<div class="tooltip-stat"><span>기온 편차 seed</span>
            <span style="color:${tAnom >= 0 ? '#fca5a5' : '#7dd3fc'};font-weight:bold;">
            ${tAnom >= 0 ? '+' : ''}${tAnom.toFixed(1)}°C</span></div>` : ''}
        ${body}
        <div style="margin-top:6px;font-size:10px;color:#64748b;">${pol.note || ''} · 클릭하여 상세</div>`;
};

const hideClimateTooltip = () => tooltipEl.classList.add('hidden');

const buildRegionPoints = async (cfg) => {
    const fc = await loadClimateForecast(cfg);
    return cfg.regions.map(r => {
        const keys = r.regionKeys || (r.regionKey ? [r.regionKey] : []);
        const crops = normalizeForecast(fc, keys.length ? keys : null)
            .filter(c => !keys.length || keys.includes(c.regionKey));
        // if keys empty, don't attach all country crops
        const relevant = keys.length
            ? normalizeForecast(fc, keys)
            : [];
        const scored = relevant.filter(c => c.pct != null);
        const meanPct = scored.length
            ? scored.reduce((s, c) => s + c.pct, 0) / scored.length
            : null;
        const stress = regionStressFromPct(meanPct);
        const unit = relevant[0]?.unit || 'kg/ha';
        const point = relevant[0]?.point;
        return {
            ...r,
            coordinates: r.coordinates || window.CountriesData?.[r.name],
            meanPct,
            stress,
            unit,
            point,
            cropCount: relevant.length,
        };
    }).filter(r => r.coordinates);
};

const showClimateCountry = async (countryName) => {
    try {
    await loadClimateRegistry();
    const cfg = CLIMATE_COUNTRIES[countryName];
    if (!cfg) return;

    climateLevel = 'country';
    climateCountry = countryName;
    climateSelectedRegion = null;
    hideClimateTooltip();
    document.getElementById('commodity-info-panel')?.classList.remove('hidden');
    setClimateCommodityHeader('climate');

    const points = await buildRegionPoints(cfg);
    const lv = tradePolicyLevel(countryName);
    const pol = CLIMATE_TRADE_POLICY[countryName] || {};

    currentViewTitle.textContent = `${cfg.label} ${cfg.iso || ''}`.trim();
    setModelStatusBadge(cfg);
    currentViewDesc.textContent = isClimateReference(null, cfg) || cfg.panelMode === 'reference'
        ? `${cfg.regions.length}개 산지 · 예측 불가 · 좌측 정부 전망·조사 메모 · ← 세계 지도`
        : `국가 워크스페이스 · ${cfg.regions.length}개 산지 핀 · 좌측 기관/캘린더 · 우측 집계 · 핀→모델 설명`;
    totalVolumeEl.textContent = cfg.modelName || cfg.label;
    topExporterEl.textContent = tradePolicyLabelKo(lv);

    setClimateMapLegend(cfg.panelMode === 'reference' ? 'reference' : 'country');

    if (chartView) {
        chartView.classList.add('hidden');
        chartView.style.pointerEvents = 'none';
    }
    mapContainer.style.display = 'block';
    mapContainer.style.pointerEvents = 'auto';
    ensureClimateMapPointerFallback();

    await loadClimateGlobal();
    await loadSst();
    const admin1 = await loadAdmin1(cfg.iso);
    // Req 4: the country drill is a workspace, not just a zoom. The map keeps
    // the same globe but frames the target with a HUD, dims every other
    // country, and labels each producing region on the sphere.
    // Stage 2 hands the whole width to the map -- the right dashboard only
    // appears once a producing region is chosen -- so the country is framed
    // tighter than the manifest's default, which was set for a narrower pane.
    const countryView = clampGlobeView({ ...cfg.view, pitch: 0, bearing: 0 });
    currentViewState = countryView;
    setClimateTargetHud(cfg, countryView.zoom);

    deckgl.setProps({
        views: [new MapView({ id: 'map', controller: true, repeat: true })],
        viewState: countryView,
        controller: { dragRotate: false, touchRotate: false },
        onViewStateChange: ({ viewState }) => {
            if (climateLevel !== 'country' || currentCommodity !== 'climate') return;
            const next = clampGlobeView(viewState);
            currentViewState = next;
            setClimateTargetHud(cfg, next.zoom);
            deckgl.setProps({ viewState: next });
            positionClimateRegionLabels();
        },
        onAfterRender: positionClimateRegionLabels,
        pickingRadius: 18,
        getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab'),
        onClick: handleClimateDeckClick,
        onHover: (info) => {
            if (climateLevel !== 'country') return;
            if (!info.object || info.layer?.id !== 'climate-regions') {
                // keep last region tooltip only while over a marker
                if (!info.object) hideClimateTooltip();
                return;
            }
            const d = info.object;
            if (!tooltipEl) return;
            positionTooltipAt(info, 10);
            tooltipEl.classList.remove('hidden');
            const pctStr = d.meanPct == null ? '—'
                : `${d.meanPct >= 0 ? '+' : ''}${d.meanPct.toFixed(1)}%`;
            const ptStr = d.point == null ? '—'
                : (d.unit === 'bu/acre' ? d.point.toFixed(1) : Math.round(d.point).toLocaleString());
            tooltipEl.innerHTML = `
                <div class="tooltip-title">${d.label}</div>
                <div class="tooltip-stat"><span>상태</span>
                    <span class="climate-status-pill ${d.stress.level === 'ok' ? 'green' : d.stress.level === 'high' ? 'red' : 'orange'}">${d.stress.ko}</span></div>
                <div class="tooltip-stat"><span>예측/기상효과</span>
                    <span>${ptStr} ${d.unit || ''} · ${pctStr}</span></div>`;
        },
        layers: [
            // Dimmed basemap so the target country reads as the lit subject.
            ...worldBaseLayers({
                id: 'climate-country',
                landColor: [24, 30, 40, 255],
                lineColor: [96, 112, 136, 55],
                water: [sstWashLayer(null, 'climate-country-sst-wash')],
            }),
            new GeoJsonLayer({
                id: 'climate-countries',
                data: worldGeo(),
                stroked: true,
                filled: true,
                lineWidthMinPixels: 2,
                getFillColor: f => {
                    const key = featureCountryKey(f);
                    if (key === countryName)
                        return (TRADE_FILL[lv] || TRADE_FILL.blue).map((v, i) => (i === 3 ? 80 : v));
                    return [0, 0, 0, 0];
                },
                getLineColor: f => {
                    const key = featureCountryKey(f);
                    if (key === countryName) return [125, 211, 252, 230];
                    return [0, 0, 0, 0];
                },
                pickable: true,
                updateTriggers: { getFillColor: [cfg.iso, lv, countryName], getLineColor: [cfg.iso, lv] },
            }),
            admin1Layer(cfg.iso, admin1),
            new ScatterplotLayer({
                id: 'climate-regions',
                data: points,
                pickable: true,
                stroked: true,
                filled: true,
                opacity: 0.92,
                radiusMinPixels: 16,
                radiusMaxPixels: 48,
                lineWidthMinPixels: 2,
                getPosition: d => d.coordinates,
                getRadius: 160000,
                getFillColor: d => d.stress.rgba,
                getLineColor: d => (d.name === climateSelectedRegion
                    ? [255, 255, 255, 255]
                    : [255, 255, 255, 190]),
                autoHighlight: true,
                highlightColor: [255, 255, 255, 200],
                updateTriggers: { getLineColor: [climateSelectedRegion] },
            }),
        ],
    });
    // Region names are an HTML overlay rather than a TextLayer: it gives the
    // mockup's two-line label with a coloured delta, and lets the label itself
    // be clickable.
    setClimateRegionLabels(points);

    await renderCountryPanel(cfg, points, { lv, pol });
    // Stage 2: map full width, no right dashboard. renderCountryPanel opens it
    // when a region is selected (stage 3).
    togglePanels({
        forecast: true,
        climateRight: !!climateSelectedRegion,
        left: true,
        right: !!climateSelectedRegion,
        map: true,
    });
    } catch (err) {
        console.error('[Climate] showClimateCountry failed', err);
    }
};
window.showClimateCountry = showClimateCountry;

const fmtYield = (v, unit) => {
    if (v === null || v === undefined) return '—';
    return unit === 'bu/acre' ? Number(v).toFixed(1) : Math.round(v).toLocaleString();
};

const renderCountryPanel = async (cfg, points = null, meta = {}) => {
    const fc = await loadClimateForecast(cfg);
    const lv = meta.lv || tradePolicyLevel(climateCountry);
    const pol = meta.pol || CLIMATE_TRADE_POLICY[climateCountry] || {};
    points = points || await buildRegionPoints(cfg);
    const regionFocus = climateSelectedRegion;
    const regionCfg = regionFocus
        ? cfg.regions.find((r) => r.name === regionFocus)
        : null;

    // Reference / no-forecast countries: left panel is government outlooks + notes.
    // Do not invent crop-merge averages or fake yield points.
    if (isClimateReference(fc, cfg)) {
        forecastCountryTitle.textContent = fc?.title_ko || cfg.modelName || cfg.label;
        // A reference country has no forecast, but it still has a growing
        // season. Cocoa's main and mid crops are the whole reason West Africa
        // is on the map, so the calendar belongs here too.
        const refCrops = Object.keys(CROP_CALENDAR_SEED[climateCountry] || {});
        forecastContentEl.innerHTML = renderClimateReferencePanelHtml(cfg, fc || {}, { lv, pol })
            + (refCrops.length ? `<div class="climate-card">
                <h3>작물 캘린더 · 현재 단계 (seed)</h3>
                ${renderCropCalendarHtml(climateCountry, refCrops)}
            </div>` : '');
        if (climateRightTitleEl) climateRightTitleEl.textContent = '참고 모드';
        if (climateRightDescEl) {
            climateRightDescEl.textContent = '예측 없음 · 좌측 정부 전망·조사 메모';
        }
        if (climateRightContentEl) {
            climateRightContentEl.innerHTML = `
                <div class="climate-card">
                    <h3>예측 불가</h3>
                    <div class="climate-sub">${fc?.reason_ko || fc?.reason || '데이터 한계로 단수 예측을 제공하지 않습니다.'}</div>
                    <div class="climate-sub" style="margin-top:8px;">상세·링크는 좌측 패널을 보세요.</div>
                </div>
                <div class="climate-card">
                    <h3>산지 핀</h3>
                    ${cfg.regions.map((r) => `
                        <div class="climate-region-hit climate-click${regionFocus === r.name ? ' climate-region-active' : ''}"
                             role="button" tabindex="0"
                             data-climate-region="${r.name}" aria-label="${r.label}">
                            <div class="climate-table-row">
                                <span class="nm">${r.label}</span>
                                <span class="climate-status-pill orange">참고</span>
                            </div>
                        </div>`).join('') || '<div class="climate-sub">핀 없음</div>'}
                </div>`;
        }
        if (climateRightPanelEl) climateRightPanelEl.classList.remove('hidden');
        panelHide(macroPanelEl);
        panelHide(countryStatsPanelEl);
        return;
    }

    const crops = normalizeForecast(fc);
    const merged = mergeCropsByType(crops);

    // Left: trade + GAIN + crop-type merge + calendar (not commodity trade stats)
    forecastCountryTitle.textContent = cfg.modelName || cfg.label;
    const gainHtml = renderSourceStack([
        await renderUsdaGainCard(climateCountry || cfg.label),
        renderNationalSourceCard(cfg),
    ]);

    const mergeHtml = merged.length
        ? merged.map((m) => {
            const pct = m.meanPct;
            const pctColor = pct == null ? '#94a3b8' : (pct < 0 ? '#fca5a5' : '#4ade80');
            const pctStr = pct == null ? '—'
                : `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
            const pt = m.meanPoint == null
                ? (m.noForecast === m.total ? '예측없음' : '—')
                : fmtYield(m.meanPoint, m.unit);
            return `<div class="climate-crop-merge">
                <div class="cm-head">
                    <span class="cm-title">${m.label}</span>
                    <span class="cm-meta">${m.regionCount}개 산지 합산</span>
                </div>
                <div class="climate-metric-row" style="border:none;padding:2px 0;">
                    <span class="nm">평균 단수 전망</span>
                    <span class="vl">${pt}
                        <span style="color:${pctColor};font-size:11px;font-weight:600;"> ${pctStr}</span>
                    </span>
                </div>
                <div class="climate-sub">
                    기상효과(추세 대비) 평균 · 실적 평균 ${fmtYield(m.meanLast, m.unit)} ${m.unit || ''}
                    ${m.lowShare > 0 ? ` · 저신뢰 ${(m.lowShare * 100).toFixed(0)}%` : ''}
                </div>
            </div>`;
        }).join('')
        : '<div class="climate-sub">forecast JSON 없음 (미배포 시)</div>';

    const cropIds = merged.map((m) => m.id).filter((id) => id !== 'other');
    // Req 5: the institutional outlook and our model do not report the same
    // quantity, so the panel states the difference and gives the exact factors
    // rather than leaving the reader to guess whether 179 and 14.8 are comparable.
    const unitBridgeHtml = `
        <div class="climate-card climate-unit-bridge">
            <h3>단위 읽는 법 (기관 vs 자사 모델)</h3>
            <table class="climate-unit-table">
                <tr>
                    <th></th><th>기관 (USDA·GAIN·WASDE)</th><th>자사 AI 모델</th>
                </tr>
                <tr>
                    <td class="k">무엇을</td>
                    <td>국가 <strong>총생산량</strong></td>
                    <td>산지 <strong>단수</strong>(면적당 수확량)</td>
                </tr>
                <tr>
                    <td class="k">단위</td>
                    <td><strong>MMT</strong> (백만 톤)<br><span class="u">미국은 million bu 병기</span></td>
                    <td><strong>bu/acre</strong> (미국)<br><strong>kg/ha · t/ha</strong> (그 외)</td>
                </tr>
                <tr>
                    <td class="k">관계</td>
                    <td colspan="2">총생산 = 단수 × 수확면적 — <strong>같은 숫자가 아닙니다</strong></td>
                </tr>
            </table>
            <div class="climate-unit-conv">
                <div class="cu-title">환산 계수</div>
                <div class="cu-row"><span>옥수수·수수 1 bu</span><span>25.40 kg</span></div>
                <div class="cu-row"><span>대두·밀 1 bu</span><span>27.22 kg</span></div>
                <div class="cu-row"><span>1 acre</span><span>0.4047 ha</span></div>
                <div class="cu-row"><span>1 t/ha (옥수수)</span><span>≈ 15.93 bu/acre</span></div>
                <div class="cu-row"><span>1 t/ha (대두·밀)</span><span>≈ 14.87 bu/acre</span></div>
                <div class="cu-row"><span>1 MMT</span><span>1,000,000 t</span></div>
            </div>
            <div class="climate-sub" style="margin-top:8px;">
                예) 옥수수 <strong>179.4 bu/acre</strong> = 179.4 × 25.40 ÷ 1000 ÷ 0.4047
                ≈ <strong>11.26 t/ha</strong>. 여기에 수확면적을 곱해야 기관의 MMT와
                같은 축에 놓입니다. 면적 시계열이 없는 국가는 병기만 하고 억지로
                환산하지 않습니다 — 환산값이 면적 가정에 통째로 의존하기 때문입니다.
            </div>
        </div>`;

    forecastContentEl.innerHTML = `
        <div class="climate-scroll">
            ${climateNavBackHtml(cfg.label)}
            <div class="climate-trade-banner">
                <div>
                    <div class="tb-label">무역 · 수출 통제</div>
                    <div class="tb-note">${pol.note || '상태 메모 없음'}</div>
                </div>
                <span class="climate-status-pill ${lv}">${tradePolicyLabelKo(lv)}</span>
            </div>
            ${gainHtml}
            ${unitBridgeHtml}
            <div class="climate-card">
                <h3>작물 캘린더 · 현재 단계 (seed)</h3>
                ${renderCropCalendarHtml(climateCountry, cropIds)}
            </div>
            <div class="climate-card">
                <h3>산지 바로가기</h3>
                <div class="climate-sub" style="margin-bottom:6px;">클릭 시 왼쪽이 모델·데이터 설명으로 바뀌고, 오른쪽은 산지 전망</div>
                ${cfg.regions.map((r) => `
                    <div class="climate-region-hit climate-click${regionFocus === r.name ? ' climate-region-active' : ''}"
                         role="button" tabindex="0"
                         data-climate-region="${r.name}" aria-label="${r.label} 상세">
                        <div class="climate-table-row">
                            <span class="nm">${r.label}</span>
                            <span class="vl" style="color:#94a3b8;font-size:11px;">모델 설명 →</span>
                        </div>
                    </div>`).join('')}
            </div>
        </div>`;

    // Right: national rollup OR selected region crop detail
    if (regionCfg) {
        await renderClimateModelOnLeft(cfg, regionCfg, fc);
        await renderClimateRegionOnRight(cfg, regionCfg, fc, points);
    } else {
        if (climateRightTitleEl) climateRightTitleEl.textContent = '국가 집계 · 전망';
        if (climateRightDescEl) climateRightDescEl.textContent = `시즌 ${fc?.season ?? '—'} · 산지 클릭 시 지역 상세 + 좌측 모델 설명`;
        if (climateRightContentEl) {
            climateRightContentEl.innerHTML = `
                <div class="climate-card">
                    <h3>작물 유형 합산 (국가)</h3>
                    <div class="climate-sub" style="margin-bottom:6px;">같은 작물을 산지별로 두지 않고 하나로 묶음 · 단위는 단수</div>
                    ${mergeHtml}
                </div>
                <div class="climate-card">
                    <h3>지역 기상효과 요약</h3>
                    ${points.map((p) => `
                        <div class="climate-region-hit climate-click" role="button" tabindex="0"
                             data-climate-region="${p.name}" aria-label="${p.label} 상세">
                            <div class="climate-metric-row">
                                <span class="nm">${p.label}</span>
                                <span class="climate-status-pill ${p.stress.level === 'ok' ? 'green' : p.stress.level === 'high' ? 'red' : p.stress.level === 'warn' ? 'orange' : 'blue'}">${p.stress.ko}</span>
                            </div>
                            <div class="climate-country-sub">
                                ${p.meanPct == null ? '기상효과 요약 없음'
                                    : `기상효과 ${p.meanPct >= 0 ? '+' : ''}${p.meanPct.toFixed(1)}%`}
                                ${p.point != null ? ` · ${fmtYield(p.point, p.unit)} ${p.unit}` : ''}
                            </div>
                        </div>`).join('') || '<div class="climate-sub">산지 없음</div>'}
                </div>
                <p style="font-size:10px;color:#64748b;">갱신: ${fc?.generated_at ? new Date(fc.generated_at).toLocaleString() : '—'}</p>`;
        }
    }
    // Stage 3 only: the dashboard appears when a producing region is chosen.
    // At country level the map keeps the full width.
    const showRight = !!regionCfg;
    if (climateRightPanelEl) climateRightPanelEl.classList.toggle('hidden', !showRight);
    const rightPane = document.getElementById('right-pane');
    if (rightPane) rightPane.style.display = showRight ? 'flex' : 'none';
    panelHide(macroPanelEl);
    panelHide(countryStatsPanelEl);
};

/**
 * When each input was measured, and when it is refreshed.
 *
 * "출처: NASA POWER" says where a number came from but not whether it is
 * current. A forecast built on labels that stop in 2019 and weather from last
 * week is two different vintages in one figure, and only one of them is
 * visible unless both are stated.
 *
 * Cadences are the GitHub Actions schedules in .github/workflows, so this
 * matches what actually runs rather than an intention.
 */
const REFRESH_CADENCE = {
    forecast: { ko: '주 1회 (월요일)', detail: '국가별 yield_forecast 워크플로' },
    climate: { ko: '주 1회', detail: 'NASA POWER 일별 관측을 매 실행 시 재수집' },
    indices: { ko: '주 1회 (월요일)', detail: 'NOAA CPC ONI · NOAA PSL DMI' },
    sst: { ko: '주 1회 (화요일)', detail: 'NOAA OISST v2.1 격자' },
};

const fmtAge = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days < 1) return '오늘';
    if (days < 60) return `${days}일 전`;
    const m = Math.round(days / 30.4);
    return m < 24 ? `${m}개월 전` : `${Math.floor(m / 12)}년 ${m % 12}개월 전`;
};

const renderVintageRows = (cfg, fc) => {
    const src = cfg?.sources || {};
    const rows = [];

    const push = (what, when, cadence, extra) => {
        const age = when ? fmtAge(when) : null;
        rows.push(`<div class="vintage-row">
            <span class="vt-what">${what}</span>
            <span class="vt-when">${when || '—'}${age ? ` <em>${age}</em>` : ''}</span>
            <span class="vt-next">${cadence}</span>
        </div>${extra ? `<div class="climate-sub vt-note">${extra}</div>` : ''}`);
    };

    push('공식 통계 (모델 정답지)', src.labels?.updated,
         REFRESH_CADENCE.forecast.ko,
         src.labels?.name ? `출처 ${src.labels.name}` : '');
    push('기상 관측', src.climate?.updated, REFRESH_CADENCE.climate.ko,
         REFRESH_CADENCE.climate.detail);
    push('예측 산출', fc?.generated_at ? String(fc.generated_at).slice(0, 10) : null,
         REFRESH_CADENCE.forecast.ko, REFRESH_CADENCE.forecast.detail);
    push('기후 지수 (ENSO·IOD)', climateGlobalCache?.generated_at
         ? String(climateGlobalCache.generated_at).slice(0, 10) : null,
         REFRESH_CADENCE.indices.ko, REFRESH_CADENCE.indices.detail);
    push('해수면 수온 격자', sstDoc?.as_of, REFRESH_CADENCE.sst.ko,
         REFRESH_CADENCE.sst.detail);

    return `<div class="vintage-table">
        <div class="vintage-row vt-head">
            <span class="vt-what">항목</span>
            <span class="vt-when">데이터 시점</span>
            <span class="vt-next">갱신 주기</span>
        </div>
        ${rows.join('')}
    </div>`;
};

/**
 * Req 7: region click → left panel becomes model / data / paper provenance
 * (not a duplicate of the yield numbers that stay on the right).
 */
const renderClimateModelOnLeft = async (cfg, regionCfg, fc = null) => {
    fc = fc || await loadClimateForecast(cfg);
    const keys = regionCfg.regionKeys
        || (regionCfg.regionKey ? [regionCfg.regionKey] : []);
    const methodKey = keys[0];
    const usMethod = US_REGION_METHOD[methodKey];
    const crops = keys.length ? normalizeForecast(fc, keys) : [];
    const first = crops[0];
    const updated = fc?.generated_at
        ? new Date(fc.generated_at).toLocaleString()
        : '—';
    const dataSources = fc?.data_sources
        || fc?.sources
        || (Array.isArray(fc?.source) ? fc.source : null)
        || null;

    const skillBits = first && first.skillVsTrend != null
        ? `추세 대비 오차 ${(first.skillVsTrend * 100).toFixed(0)}% 감소`
        : (first?.lowConfidence ? '신뢰도 낮음 (검증 미통과·표본 부족 가능)' : '스킬 메타 없음');

    const notes = usMethod?.notes
        || [
            cfg.modelName ? `모델 라벨: ${cfg.modelName}` : '국가별 추세+기상편차 회귀 골격',
            '기상 입력은 NASA POWER 등 공개 재분석·관측을 씁니다 (국가 파이프라인 README 참고).',
        ];
    const refs = usMethod?.refs
        || fc?.method_refs
        || fc?.references
        || '논문·방법론은 해당국 yield_model 문서 / DATA_LAYOUT 참고';
    const headline = usMethod?.headline || '추세수확량 + 기상편차 회귀';

    forecastCountryTitle.textContent = `${regionCfg.label} · 모델·데이터`;
    forecastContentEl.innerHTML = `
        <div class="climate-scroll">
            ${climateNavBackHtml(cfg.label)}
            <div class="climate-card">
                <h3>사용 모델</h3>
                <div class="forecast-good" style="margin:0;">
                    <strong>${headline}</strong>
                    <div class="climate-sub" style="margin-top:6px;">${cfg.modelName || cfg.label}</div>
                </div>
                <ul class="climate-model-notes">
                    ${notes.map((n) => `<li>${n}</li>`).join('')}
                </ul>
                ${usMethod?.finding ? `<div class="climate-sub" style="margin-top:8px;"><strong>이 지역에서 확인된 점</strong><br>${usMethod.finding}</div>` : ''}
            </div>
            <div class="climate-card">
                <h3>참고 논문 · 방법론 출처</h3>
                <div class="climate-sub">${refs}</div>
            </div>
            <div class="climate-card">
                <h3>데이터 시점 · 갱신 주기</h3>
                ${renderVintageRows(cfg, fc)}
            </div>
            <div class="climate-card">
                <h3>데이터 출처</h3>
                <div class="climate-sub">
                    ${dataSources
                        ? (Array.isArray(dataSources)
                            ? dataSources.map((s) => (typeof s === 'string' ? s : (s.label || s.name || JSON.stringify(s)))).join(' · ')
                            : String(dataSources))
                        : '수확량 공식통계 + NASA POWER 기상 + (해당 시) ENSO/토양수분 파생'}
                </div>
                <div class="climate-metric-row" style="margin-top:8px;">
                    <span class="nm">예측 JSON 갱신</span>
                    <span class="vl" style="font-size:12px;">${updated}</span>
                </div>
                <div class="climate-sub">시즌 ${fc?.season ?? '—'} · ${skillBits}</div>
            </div>
            <div class="climate-card">
                <h3>단위</h3>
                <div class="climate-sub">
                    이 산지 전망 단위: <strong>${first?.unit || '단수'}</strong>.
                    기관 GAIN/WASDE의 MMT(국가 생산)와 직접 같지 않습니다 — 우측 수치와 좌측 기관 카드를 구분해 보세요.
                </div>
            </div>
        </div>`;
};

// Region yield numbers stay on the right; left holds model provenance.
const renderClimateRegionOnRight = async (cfg, regionCfg, fc = null, points = null) => {
    fc = fc || await loadClimateForecast(cfg);
    const keys = regionCfg.regionKeys
        || (regionCfg.regionKey ? [regionCfg.regionKey] : null);
    const crops = keys?.length ? normalizeForecast(fc, keys) : [];
    const p = (points || []).find((x) => x.name === regionCfg.name);

    if (climateRightTitleEl) climateRightTitleEl.textContent = regionCfg.label;
    if (climateRightDescEl) {
        climateRightDescEl.textContent = `${cfg.label} · 산지 상세 · 시즌 ${fc?.season ?? '—'}`;
    }
    if (!climateRightContentEl) return false;

    const cropCards = crops.length
        ? crops.map((c) => {
            const color = c.pct != null && c.pct < 0 ? '#fca5a5' : '#4ade80';
            const badge = c.forecastAvailable === false
                ? `<span class="climate-status-pill orange">예측 없음</span>`
                : c.lowConfidence
                    ? `<span class="climate-status-pill yellow">신뢰도 낮음</span>`
                    : `<span class="climate-status-pill green">검증 통과</span>`;
            return `<div class="climate-card" style="margin-bottom:8px;">
                <div class="climate-metric-row" style="border:none;">
                    <span class="nm" style="font-size:13px;font-weight:600;color:#e2e8f0;">${c.label}</span>
                    ${badge}
                </div>
                ${c.forecastAvailable === false ? `
                    <div class="climate-sub">${c.reason || '예측 없음'}
                    ${c.lastActual != null ? ` · ${c.lastActualYear ?? ''} 실적 ${fmtYield(c.lastActual, c.unit)} ${c.unit}` : ''}</div>`
                : `
                    <div class="climate-metric-row">
                        <span class="nm">${c.lastActualYear ?? '—'} 실적</span>
                        <span class="vl">${fmtYield(c.lastActual, c.unit)} ${c.unit || ''}</span>
                    </div>
                    <div class="climate-metric-row">
                        <span class="nm">${fc?.season ?? ''} 예상</span>
                        <span class="vl" style="color:${color};">${fmtYield(c.point, c.unit)} ${c.unit || ''}
                            ${c.pct != null ? ` (${c.pct >= 0 ? '+' : ''}${c.pct.toFixed(1)}%)` : ''}</span>
                    </div>
                    ${c.pct != null ? `<div class="climate-sub">기상 효과(추세 대비) ${c.pct >= 0 ? '+' : ''}${c.pct.toFixed(1)}%</div>` : ''}
                    ${c.reason ? `<div class="climate-sub">${c.reason}</div>` : ''}`}
            </div>`;
        }).join('')
        : `<div class="climate-card"><div class="climate-sub">이 산지의 작물 슬롯 없음</div></div>`;

    climateRightContentEl.innerHTML = `
        <div class="climate-card" style="margin-bottom:10px;">
            <div class="climate-nav-row" style="margin:0;">
                <span class="climate-back climate-click" data-climate-national="1"
                      role="button" tabindex="0">← 국가 집계</span>
                <span class="climate-nav-trail">${regionCfg.label}</span>
            </div>
            ${p ? `<div class="climate-metric-row" style="margin-top:8px;">
                <span class="nm">기상 효과 수준</span>
                <span class="climate-status-pill ${p.stress.level === 'ok' ? 'green' : p.stress.level === 'high' ? 'red' : p.stress.level === 'warn' ? 'orange' : 'blue'}">${p.stress.ko}</span>
            </div>
            <div class="climate-sub">${p.meanPct == null ? '요약 없음'
                : `평균 기상효과 ${p.meanPct >= 0 ? '+' : ''}${p.meanPct.toFixed(1)}%`}</div>` : ''}
        </div>
        <h3 style="font-size:12px;color:#94a3b8;margin:0 0 8px;">산지 작물 (지역 단위)</h3>
        ${cropCards}
        <p style="font-size:10px;color:#64748b;">갱신: ${fc?.generated_at ? new Date(fc.generated_at).toLocaleString() : '—'}</p>`;
    return true;
};

// Keep name for callers; country drill uses updateForecastPanel first.
const renderClimateRegionForecast = async (regionName) => {
    if (climateLevel !== 'country' || !climateCountry) return false;
    const cfg = CLIMATE_COUNTRIES[climateCountry];
    if (!cfg) return false;
    const regionCfg = cfg.regions.find((r) => r.name === regionName);
    if (!regionCfg) return false;
    const keys = regionCfg.regionKeys
        || (regionCfg.regionKey ? [regionCfg.regionKey] : null);
    if (!keys?.length) return false;
    climateSelectedRegion = regionName;
    const points = await buildRegionPoints(cfg);
    await renderCountryPanel(cfg, points, {
        lv: tradePolicyLevel(climateCountry),
        pol: CLIMATE_TRADE_POLICY[climateCountry] || {},
    });
    return true;
};

const updateForecastPanel = async (regionName) => {
    // Country-drill: region pin/list → right panel only (left stays crop merge).
    if (climateLevel === 'country' && climateCountry && CLIMATE_COUNTRIES[climateCountry]) {
        const cfg = CLIMATE_COUNTRIES[climateCountry];
        const regionCfg = cfg.regions.find((r) => r.name === regionName);
        if (regionCfg) {
            climateSelectedRegion = regionName;
            const points = await buildRegionPoints(cfg);
            await renderCountryPanel(cfg, points, {
                lv: tradePolicyLevel(climateCountry),
                pol: CLIMATE_TRADE_POLICY[climateCountry] || {},
            });
            return;
        }
    }

    if (await renderYieldForecast(regionName)) return;
    if (await renderBrazilYieldForecast(regionName)) return;
    if (await renderIndiaYieldForecast(regionName)) return;
    if (await renderClimateRegionForecast(regionName)) return;

    const data = forecastData[regionName];
    forecastCountryTitle.textContent = `지역 기상 및 기후 요인: ${regionName}`;

    if (!data) {
        forecastContentEl.innerHTML = `${climateLevel === 'country' ? climateNavBackHtml(regionName) : ''}
            <p class="empty-state">해당 지역의 상세 기상 예측 데이터가 없습니다. 지도에서 활성화된 지역(예: Mato Grosso)을 선택해주세요.</p>`;
        panelHide(macroPanelEl);
        panelHide(countryStatsPanelEl);
        return;
    }

    const alertClass = (data.climate_status.includes('가뭄') || data.climate_status.includes('홍수')) ? 'forecast-alert' : 'forecast-good';

    forecastContentEl.innerHTML = `
        ${climateLevel === 'country' ? climateNavBackHtml(regionName) : ''}
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">적산온도(GDD)</span>
                <span class="forecast-val">${data.gdd_total} 도일</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">강수량 편차</span>
                <span class="forecast-val">${data.precip_anomaly_mm > 0 ? '+' : ''}${data.precip_anomaly_mm} mm</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">토양 수분 (0~7cm)</span>
                <span class="forecast-val">${data.soil_moisture} m³/m³</span>
            </div>
            <div class="${alertClass}" style="margin-top:16px;">
                <strong>${data.climate_status}</strong>
            </div>
        </div>
        <p style="font-size: 11px; color: #94a3b8; text-align: right; margin-bottom: 4px;">업데이트: ${new Date(data.last_updated).toLocaleString()}</p>
        <p style="font-size: 11px; color: #64748b; text-align: right;">출처: Open-Meteo 기상 관측망 / 기관별 과거 작황 데이터 기반 예측</p>
    `;

    if (data.crops && data.crops.length > 0) {
        countryStatsTitleEl.textContent = `${regionName}`;
        document.getElementById('country-stats-desc').textContent = "지역 참고 작황 데이터 (기관 발표 기준값)";
        let cropHtml = '';
        data.crops.forEach(crop => {
            const isCropGood = crop.change_pct > 0;
            const sign = isCropGood ? '+' : '';
            const color = isCropGood ? '#4ade80' : '#fca5a5';
            let cepeaHtml = '';
            if (crop.cepea_price_usd) {
                const trendColor = crop.cepea_trend.startsWith('-') ? '#fca5a5' : '#4ade80';
                cepeaHtml = `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1);">
                    <span style="font-size:12px; color: #94a3b8;">CEPEA 현물 가격지수</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-size: 15px; color: #facc15;">$${crop.cepea_price_usd} <span style="font-size: 11px; color:#64748b;">(R$${crop.cepea_price_brl || '-'})</span></span>
                        <span style="font-size: 13px; color: ${trendColor};">${crop.cepea_trend}</span>
                    </div>
                </div>`;
            }
            let ibgeHtml = '';
            if (crop.ibge_top_municipalities && crop.ibge_top_municipalities.length > 0) {
                let muniList = crop.ibge_top_municipalities.map((m, idx) => `
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                        <span style="color: #cbd5e1;">${idx + 1}. ${m.city}</span>
                        <span style="color: #94a3b8;">${m.production_tonnes} 톤</span>
                    </div>
                `).join('');
                ibgeHtml = `
                <div style="margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.2); border-radius: 6px;">
                    <div style="font-size:11px; color: #94a3b8; margin-bottom: 6px;">IBGE 주요 생산 시정촌 랭킹</div>
                    <div style="font-size:12px;">${muniList}</div>
                </div>`;
            }
            cropHtml += `
            <div class="indicator-item" style="cursor: default; transform: none; border-color: rgba(255,255,255,0.1);">
                <div class="ind-header"><span class="ind-title">${crop.name}</span></div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                    <div>
                        <span style="font-size:12px; color: #94a3b8;">평균(기준)</span>
                        <div style="font-size: 15px;">${crop.avg_yield}</div>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size:12px; color: #94a3b8;">AI 예측치</span>
                        <div style="font-size: 18px; font-weight: bold; color: ${color};">${crop.pred_yield}</div>
                    </div>
                </div>
                <div style="text-align: right; font-size: 13px; margin-top:4px; color: ${color};">
                    전망: ${sign}${crop.change_pct}%
                </div>
                ${cepeaHtml}
                ${ibgeHtml}
            </div>`;
        });
        countryStatsContentEl.innerHTML = cropHtml;
        panelHide(macroPanelEl);
        panelShow(countryStatsPanelEl);
    }
};

const generateNodeData = (arcs) => {
    // Collect unique countries from arcs
    const countriesSet = new Set();
    arcs.forEach(arc => {
        countriesSet.add(arc.sourceName);
        countriesSet.add(arc.targetName);
    });

    return Array.from(countriesSet).map(country => {
        let totalTrade = 0;
        arcs.forEach(arc => {
            if(arc.sourceName === country || arc.targetName === country) {
                totalTrade += arc.volume;
            }
        });
        
        return {
            name: country,
            coordinates: countryCoords(country),
            totalTrade,
        };
    // A country with no resolvable position would render at [0,0] in the Gulf
    // of Guinea and swallow clicks meant for the map, so drop it instead.
    }).filter((d) => Array.isArray(d.coordinates));
};

// Cap on rendered routes. A global commodity query returns 300+ valid routes;
// this keeps the map readable without silently hiding mid-sized trade flows.
const MAX_RENDERED_ARCS = 120;

// Width and opacity both follow sqrt(volume), matching the mockup's
// d3.scaleSqrt ranges (width 0.45–6.5px, opacity 0.3–0.9). Opacity carrying
// volume is what keeps a dense commodity readable: 639 gold routes drawn at
// full alpha are a solid mat, the same 639 with alpha by size read as a few
// strong corridors over faint background trade.
const arcScale = (v, lo, hi, vmax) => {
    const x = Math.sqrt(Math.max(0, v) / vmax);
    return lo + (hi - lo) * Math.min(1, x);
};
let arcVolumeMax = 1;
const arcWidth = (v) => arcScale(v, 0.45, 6.5, arcVolumeMax);
const arcAlpha = (v) => Math.round(arcScale(v, 0.3, 0.9, arcVolumeMax) * 255);

// Commodity maps ride the same curved globe as the home screen (req 2, 13).
// Whole world in the frame, as the mockup's fitExtent does. Latitude 12 trims
// the empty polar bands without cutting the producing belt.
const TRADE_MAP_VIEW = { longitude: 5, latitude: 12, zoom: 0.85, pitch: 0, bearing: 0 };

const stopTradeAnim = () => {
    if (tradeAnimRaf) {
        cancelAnimationFrame(tradeAnimRaf);
        tradeAnimRaf = null;
    }
};

const slerpLonLat = (a, b, t) => {
    const toRad = Math.PI / 180;
    const lon1 = a[0] * toRad, lat1 = a[1] * toRad;
    const lon2 = b[0] * toRad, lat2 = b[1] * toRad;
    const x1 = Math.cos(lat1) * Math.cos(lon1), y1 = Math.cos(lat1) * Math.sin(lon1), z1 = Math.sin(lat1);
    const x2 = Math.cos(lat2) * Math.cos(lon2), y2 = Math.cos(lat2) * Math.sin(lon2), z2 = Math.sin(lat2);
    const dot = Math.max(-1, Math.min(1, x1 * x2 + y1 * y2 + z1 * z2));
    const omega = Math.acos(dot);
    if (omega < 1e-6) return a.slice();
    const s1 = Math.sin((1 - t) * omega) / Math.sin(omega);
    const s2 = Math.sin(t * omega) / Math.sin(omega);
    const x = s1 * x1 + s2 * x2, y = s1 * y1 + s2 * y2, z = s1 * z1 + s2 * z2;
    return [(Math.atan2(y, x) * 180) / Math.PI, (Math.atan2(z, Math.hypot(x, y)) * 180) / Math.PI];
};

/**
 * Great-circle route bowed sideways in the plane, with no altitude.
 *
 * ArcLayer lifts its curve on the z axis, which at pitch 0 still reads as a
 * ribbon arcing over the map. The mockup instead takes the chord, finds its
 * perpendicular, and pushes the midpoint out by 13% of its length -- the curve
 * stays on the surface. Doing the same in lon/lat gives a genuinely 2D route.
 */
const bowedPath = (src, dst, segments = 36, bowF = 0.13) => {
    // Take the shorter way round. A route from the Americas to Asia is closer
    // across the Pacific than back over Europe, and picking the long way is
    // what sent lines sweeping across the whole map.
    let lon0 = src[0];
    let lon1 = dst[0];
    if (Math.abs(lon1 - lon0) > 180) lon1 += lon1 > lon0 ? -360 : 360;

    const dx = lon1 - lon0;
    const dy = dst[1] - src[1];
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    // Cap the bow in degrees, not just as a fraction. An east-west route is
    // long enough that 13% of it lifted the curve ~26 degrees of latitude,
    // which near the poles shoots off the top of an equirectangular map.
    const bow = Math.min(len * bowF, 12);

    const out = [];
    for (let i = 0; i <= segments; i++) {
        const f = i / segments;
        // Interpolate in the unwrapped frame rather than slerping, so the path
        // stays continuous instead of jumping when it crosses ±180. deck's
        // repeat:true draws longitudes past the antimeridian into the next copy
        // of the world, which is what makes the crossing look seamless.
        const k = Math.sin(Math.PI * f) * bow;
        const lon = lon0 + dx * f + nx * k;
        const lat = src[1] + dy * f + ny * k;
        // Equirectangular stretches badly near the poles; keep the curve inside
        // the band the basemap actually draws.
        out.push([lon, Math.max(-78, Math.min(78, lat))]);
    }
    return out;
};

// Export controls on the commodity currently shown.
//
// The crop monitor already coloured countries by export status, but the
// commodity maps -- oil, gold, copper, aluminium -- had none, even though the
// controls that move those markets are exactly what a trade map should surface:
// Indonesia's nickel ore ban, China's gallium and graphite licensing.
//
// Curated, not live. Trade policy changes faster than a hand-maintained file,
// so every entry carries a source, a start date and a confidence, and the map
// shows the file's as_of rather than implying it is current.
let exportControlsDoc = null;
let exportControlsPromise = null;

const loadExportControls = () => {
    if (exportControlsPromise) return exportControlsPromise;
    exportControlsPromise = fetch('/public/data/export_controls_v1.json', { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { exportControlsDoc = d; return d; })
        .catch(() => null);
    return exportControlsPromise;
};

// A dashboard commodity maps to the terms the control file uses. Bauxite sits
// under aluminium because that is the map the user is looking at when the ore
// ban matters to them.
const CONTROL_ALIASES = {
    aluminum: ['aluminum', 'bauxite'],
    copper: ['copper'],
    zinc: ['zinc'],
    gold: ['gold'],
    silver: ['silver'],
    oil: ['oil', 'crude'],
    gas: ['gas', 'lng'],
    thermal_coal: ['coal', 'thermal_coal'],
    met_coal: ['coal', 'met_coal'],
    wheat: ['wheat'],
    corn: ['corn'],
    soybeans: ['soybeans', 'soy'],
    sugar: ['sugar'],
    coffee: ['coffee'],
};

/** Controls affecting `commodity`, keyed by resolved country. */
const controlsFor = (commodity) => {
    const out = new Map();
    const terms = CONTROL_ALIASES[commodity] || [commodity];
    for (const c of exportControlsDoc?.controls || []) {
        if (!(c.commodities || []).some((x) => terms.includes(x))) continue;
        const key = resolveCountry(c.country)?.key || c.country;
        const rank = exportControlsDoc?.levels?.[c.level]?.rank ?? 0;
        const prev = out.get(key);
        // A country can carry several measures on one commodity; show the
        // strongest rather than whichever was listed first.
        if (!prev || rank > prev.rank) out.set(key, { ...c, rank });
    }
    return out;
};

/**
 * Legend for the controls actually on screen.
 *
 * Listing every level regardless would imply the map shows all three; naming
 * the countries makes the colour readable without hovering, and carrying as_of
 * keeps a hand-maintained file from reading as a live feed.
 */
const renderExportControlLegend = (controls) => {
    const host = document.getElementById('trade-overlay');
    if (!host) return;
    host.querySelector('.to-controls-legend')?.remove();
    if (!controls || controls.size === 0) return;

    const byLevel = new Map();
    for (const [country, c] of controls) {
        if (!byLevel.has(c.level)) byLevel.set(c.level, []);
        byLevel.get(c.level).push(resolveCountry(country)?.iso || country);
    }
    const order = ['prohibited', 'restricted', 'watch'];
    const rows = order.filter((l) => byLevel.has(l)).map((l) => {
        const label = exportControlsDoc?.levels?.[l]?.label_ko || l;
        return `<div class="to-scale-row">
            <i class="ctl ctl-${l}"></i>${label}
            <span class="ctl-iso">${byLevel.get(l).join(' · ')}</span>
        </div>`;
    }).join('');

    const el = document.createElement('div');
    el.className = 'to-controls-legend';
    el.innerHTML = `<span class="to-label">수출 통제</span>${rows}
        <div class="to-hint ctl-asof">${exportControlsDoc?.as_of || ''} 기준 · 수기 정리본 · 국가 클릭 시 상세</div>`;
    host.insertBefore(el, host.querySelector('.to-hint'));
};

const CONTROL_FILL = {
    prohibited: [248, 113, 113, 70],
    restricted: [251, 146, 60, 62],
    watch: [250, 204, 21, 48],
};
const CONTROL_LINE = {
    prohibited: [252, 165, 165, 190],
    restricted: [253, 186, 116, 175],
    watch: [253, 224, 71, 160],
};

const togglePanels = ({ macro = false, countryStats = false, news = false, forecast = false, climateRight = false, left = true, right = true, chart = false, map = true }) => {
    const leftPaneContainer = document.getElementById('left-pane'); // Target the whole container
    const rightPaneContainer = document.getElementById('right-pane');
    const commodityInfoPanel = document.getElementById('commodity-info-panel');
    
    macro ? panelShow(macroPanelEl) : panelHide(macroPanelEl);
    countryStats ? panelShow(countryStatsPanelEl) : panelHide(countryStatsPanelEl);
    news ? panelShow(newsPanelEl) : panelHide(newsPanelEl);
    forecast ? panelShow(forecastPanelEl) : panelHide(forecastPanelEl);
    if (climateRightPanelEl) {
        climateRight ? climateRightPanelEl.classList.remove('hidden') : climateRightPanelEl.classList.add('hidden');
    }
    
    if (left) {
        leftPaneContainer.style.display = 'flex'; // Show the whole container
        commodityInfoPanel.classList.remove('hidden'); // Show info content
    } else {
        leftPaneContainer.style.display = 'none'; // Hide the whole left pane
        commodityInfoPanel.classList.add('hidden');
    }

    rightPaneContainer.style.display = right ? 'flex' : 'none';
    
    chart ? chartView.classList.remove('hidden') : chartView.classList.add('hidden');
    mapContainer.style.display = map ? 'block' : 'none';
};

const finPct = (x, digits = 1) =>
    (x === null || x === undefined || Number.isNaN(x)) ? '—' : `${(x * 100).toFixed(digits)}%`;

const finEsc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const finPlaceholder = (title, desc, detail) => `
    <div class="fin-wrap">
        <div class="fin-head"><h1>${finEsc(title)}</h1><p>${finEsc(desc)}</p></div>
        <div class="fin-empty">
            <p class="fin-empty-title">준비 중</p>
            <p>${detail}</p>
        </div>
    </div>`;

const renderFinanceView = async (target, host) => {
    if (target === 'fin_portfolio') return renderPortfolioLab(host);
    if (target === 'fin_valuation') return renderCompanyCalc(host);
    if (target === 'fin_derivatives') return renderMicrostructure(host);

    host.innerHTML = finPlaceholder(
        '옵션·공매도 동향',
        '무료 공개 소스 기반 파생상품 포지션 동향',
        `수집 파이프라인은 있으나 산출 JSON이 아직 배포본에 없습니다.
         <code>derivatives_intel</code> 파이프라인 결과가 <code>public/data/</code> 에 들어오면 연결됩니다.`);
};

const setView = (target) => {
    const isShippingView = target && target.startsWith('shipping_');
    const isFinanceView = target && target.startsWith('fin_');
    if (target !== 'macro_monitor') {
        document.body.classList.remove('macro-mode');
        document.getElementById('macro-layer')?.remove();
    }
    if (!isShippingView && window.ShippingDashboard) {
        window.ShippingDashboard.unmount(chartView);
    }
    if (!isShippingView) document.body.classList.remove('shipping-mode');
    if (!isFinanceView) {
        document.body.classList.remove('finance-mode');
        // Shipping owns chartView too, so only clear what this view wrote.
        if (chartView && chartView.querySelector('.fin-wrap')) chartView.innerHTML = '';
    }
    if (!(window.TradeData && window.TradeData[target])) {
        stopTradeAnim();
        document.body.classList.remove('trade-map-mode');
        document.getElementById('trade-overlay')?.classList.add('hidden');
        tradeFocusCountry = null;
    }

    // Leaving the climate view by the top menu bypasses showClimateWorld(), so
    // reset its state here too -- otherwise climateLevel stays 'country' and a
    // click on some other commodity map would jump back into the climate view.
    if (target !== 'climate') {
        climateLevel = 'world';
        climateCountry = null;
        climateSelectedRegion = null;
        hideClimateTooltip();
        setClimateTargetHud(null);
        setClimateRegionLabels([]);
        setModelStatusBadge(null);
        setClimateCommodityHeader(null);
        if (climateMapLegendEl) climateMapLegendEl.classList.add('hidden');
        if (climateRightPanelEl) climateRightPanelEl.classList.add('hidden');
    }

    // Reset active states
    navLinks.forEach(link => link.classList.remove('active'));
    
    // Find target link
    const targetLink = document.querySelector(`[data-target="${target}"]`);
    if (targetLink) targetLink.classList.add('active');

    const coalLegend = document.getElementById('coal-legend');

    if (target === 'home') {
        // Initial empty state
        currentCommodity = 'home';
        stopTradeAnim();
        document.body.classList.remove('trade-map-mode', 'shipping-mode');
        togglePanels({ macro: true, left: false, right: true });
        
        // The dark world is now deck's own vector basemap rather than raster
        // tiles, so the globe is a single sphere -- no second world underneath.
        currentViewState = clampGlobeView({ ...currentViewState, zoom: GLOBE_ZOOM });

        deckgl.setProps({
            views: [new MapView({ id: 'map', controller: true, repeat: true })],
            viewState: currentViewState,
            controller: { dragRotate: false, touchRotate: false },
            onClick: null,
            onHover: null,
            layers: worldBaseLayers({ id: 'home' }),
        });

        // Restart rotation
        startRotation();

    } else if (isShippingView) {
        currentCommodity = target;
        stopTradeAnim();
        stopRotation();
        document.body.classList.add('shipping-mode');
        document.body.classList.remove('trade-map-mode');
        deckgl.setProps({ layers: [] });
        togglePanels({ left: false, right: false, chart: true, map: false });
        if (mapContainer) {
            mapContainer.style.display = 'none';
            mapContainer.style.pointerEvents = 'none';
        }
        if (chartView) {
            chartView.classList.remove('hidden');
            chartView.style.pointerEvents = 'auto';
            chartView.style.zIndex = '40';
        }
        window.ShippingDashboard.render(target, chartView);

    } else if (target === 'macro_monitor') {
        renderMacroMonitor();

    } else if (isFinanceView) {
        // Document-style panel, same full-bleed treatment as shipping: there is
        // no map to show, so the globe would only steal room from the numbers.
        currentCommodity = target;
        stopTradeAnim();
        stopRotation();
        document.body.classList.remove('trade-map-mode');
        document.body.classList.add('finance-mode');
        deckgl.setProps({ layers: [] });
        togglePanels({ left: false, right: false, chart: true, map: false });
        if (mapContainer) {
            mapContainer.style.display = 'none';
            mapContainer.style.pointerEvents = 'none';
        }
        if (chartView) {
            chartView.classList.remove('hidden');
            chartView.style.pointerEvents = 'auto';
            chartView.style.zIndex = '40';
        }
        renderFinanceView(target, chartView);

    } else if (target === 'inst_intl' || target === 'inst_country') {
        currentCommodity = target;
        togglePanels({ forecast: true, left: true });
        
        deckgl.setProps({ layers: [] }); // Clear map
        
        if (target === 'inst_intl') {
            currentViewTitle.textContent = "데이터 출처: 국제 기구";
            currentViewDesc.textContent = "글로벌 거시 및 무역 지표를 제공하는 주요 국제 기구 API 현황";
            forecastCountryTitle.textContent = "국제 기구 리스트";
            forecastContentEl.innerHTML = `
                <div class="forecast-box">
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>UN Comtrade</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">전 세계 170여 개국의 수출입 통계 데이터</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>USDA (미 농무부)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">글로벌 농산물 수급 전망 (WASDE) 및 작황 데이터</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>World Bank / IMF</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">원자재 가격 지수 및 주요 거시 경제 지표</span>
                    </div>
                </div>
            `;
        } else {
            currentViewTitle.textContent = "데이터 출처: 국가별 주요 기관";
            currentViewDesc.textContent = "각 국가의 1차 데이터(Primary Data)를 제공하는 핵심 정부/공공 기관 API";
            forecastCountryTitle.textContent = "국가별 기관 리스트";
            forecastContentEl.innerHTML = `
                <div class="forecast-box">
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>CONAB (브라질 국가식량공급공사)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">브라질 대두/옥수수 생산량 및 기후 리포트</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>BCCR (아르헨티나 로사리오 곡물거래소)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">팜파스 지역 작황 동향 및 무역 전망치</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>Open-Meteo</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">전 세계 고해상도 실시간 기상/기후 API</span>
                    </div>
                </div>
            `;
        }
        
        totalVolumeEl.textContent = "API / Data Sources";
        topExporterEl.textContent = "-";
    } else if (target === 'climate') {
        currentCommodity = 'climate';
        setClimateCommodityHeader('climate');
        // The country list arrives over the network now, so everything below
        // has to wait for it -- otherwise the first paint is an empty world.
        loadClimateRegistry().then(() => {
            if (currentCommodity !== 'climate') return;
            totalVolumeEl.textContent = `${Object.keys(CLIMATE_COUNTRIES).length}개국`;
            showClimateWorld();
        });
        // World climate: no right pane (req 11). Country drill re-enables it.
        togglePanels({ forecast: true, climateRight: false, left: true, right: false });
        
        currentViewTitle.textContent = '작황 모니터';
        currentViewDesc.textContent = '작황·기후·수출통제 한눈에 · 국가를 클릭하면 산지별로 들어갑니다';
        topExporterEl.textContent = 'Status coloring';

    } else if (window.TradeData[target]) {
        // Render a supported commodity map
        currentCommodity = target;
        tradeFocusCountry = null;
        setClimateCommodityHeader(null);
        const data = window.TradeData[target];
        
        // Req 1: hide right pane so the pitched world map can be larger.
        // Country-click detail on the right is deferred — ranking lives on the left.
        togglePanels({ news: true, left: true, right: false });
        
        // Update Panel Info
        currentViewTitle.textContent = data.title;
        totalVolumeEl.textContent = data.totalVolume;
        topExporterEl.textContent = data.topExporter;

        // Ranking first (it explains the map), news below it.
        updateNewsPanel('Global Market');
        loadExportControls().then(() => {
            if (currentCommodity !== target) return;
            const arcs = window.TradeData?.[target]?.arcs;
            if (arcs?.length) renderMapLayers(arcs, { keepView: true });
        });

        // Lazy Loading: if arcs are empty, fetch real data from UN Comtrade
        if (data.arcs.length === 0 && window.fetchComtradeArcs) {
            currentViewDesc.textContent = "📡 UN Comtrade API에서 실시간 무역 데이터 로딩 중...";
            
            stopRotation();
            currentViewState = clampGlobeView({ ...TRADE_MAP_VIEW });
            deckgl.setProps({
                views: [new MapView({ id: 'map', controller: true, repeat: true })],
                viewState: currentViewState,
                layers: worldBaseLayers({ id: 'trade-loading' }),
            });

            window.fetchComtradeArcs(target).then(arcs => {
                // Check if user hasn't navigated away
                if (currentCommodity !== target) return;
                
                if (arcs.length > 0) {
                    data.arcs = arcs; // Cache for future clicks
                    currentViewDesc.textContent = data.desc + ` (데이터 출처: UN Comtrade API | ${arcs.length}개 무역 루트) · 국가 클릭 → 수출 대상 순위`;
                    renderTradeWorldPanel(data.arcs);
                    renderMapLayers(data.arcs);
                } else {
                    currentViewDesc.textContent = data.desc + " (UN Comtrade 데이터 로딩 실패 — 재시도 필요)";
                }
            }).catch(err => {
                if (currentCommodity !== target) return;
                currentViewDesc.textContent = data.desc + " (API 연결 오류: " + err.message + ")";
                console.error('[Comtrade] Lazy load error:', err);
            });
        } else {
            // Already have data (cached from previous click or hardcoded)
            stopRotation();
            currentViewState = clampGlobeView({ ...TRADE_MAP_VIEW });
            currentViewDesc.textContent = data.desc + ` (데이터 출처: UN Comtrade API | ${data.arcs.length}개 무역 루트) · 국가 클릭 → 수출 대상 순위`;
            renderTradeWorldPanel(data.arcs);
            renderMapLayers(data.arcs);
        }

    } else {
        // Unsupported/Placeholder view
        currentCommodity = null;
        togglePanels({ chart: true, left: false, map: false });
        
        const categoryName = targetLink ? targetLink.textContent : target;
        currentViewTitle.textContent = `데이터 준비 중: ${categoryName}`;
        currentViewDesc.textContent = "API 연동 및 백엔드 파이프라인 구축 후 제공됩니다.";
        
        // Update placeholder text
        chartView.innerHTML = `
            <div class="placeholder-content">
                <h3>${categoryName} 시각화 준비 중</h3>
                <p>상단 메뉴에서 원자재, 에너지, 농산물 등 지원되는 상품을 선택해 보세요.</p>
            </div>
        `;
    }
};

// ==========================================
// 6. Chart.js Modal Logic for Macro Indicators
// ==========================================
const chartModal = document.getElementById('chart-modal');
const closeModal = document.getElementById('close-modal');
const modalTitle = document.getElementById('modal-chart-title');
let macroChartInstance = null;

// symbolOverride lets a caller name the Yahoo ticker outright. The 오늘 신호
// slots carry their own symbol, so they no longer have to encode it in a title
// string and hope the substring match below picks the right branch.
// withMovingAverage is opt-in and only the equity slots set it -- see the
// moving-average block below for why the other asset classes stay bare.
const openChartModal = async (indicatorTitle, symbolOverride, withMovingAverage = false) => {
    modalTitle.textContent = `${indicatorTitle} (최근 5년 실데이터)`;
    chartModal.classList.remove('hidden');

    // Map indicator title to Yahoo Finance Symbol
    let symbol = "";
    if (symbolOverride) symbol = symbolOverride;
    else if (indicatorTitle.includes('KRW/USD')) symbol = "KRW=X";
    else if (indicatorTitle.includes('WTI')) symbol = "CL=F";
    else if (indicatorTitle.includes('NAT GAS')) symbol = "NG=F";
    else if (indicatorTitle.includes('EUR')) symbol = "EUR=X";
    else if (indicatorTitle.includes('JPY')) symbol = "JPY=X";
    else if (indicatorTitle.includes('NASDAQ')) symbol = "^IXIC";
    else symbol = "^GSPC"; // default S&P 500

    let labels = [];
    let data = [];

    try {
        const res = await fetch(`/api/macro?source=yfinance&symbol=${symbol}`);
        const result = await res.json();
        
        if (result.chart && result.chart.result && result.chart.result[0]) {
            const chartData = result.chart.result[0];
            const timestamps = chartData.timestamp || [];
            const closePrices = chartData.indicators.quote[0].close || [];
            
            for (let i = 0; i < timestamps.length; i++) {
                if (closePrices[i] !== null) {
                    const d = new Date(timestamps[i] * 1000);
                    labels.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
                    data.push(closePrices[i]);
                }
            }
        }
    } catch (e) {
        console.error("Failed to load real chart data", e);
        modalTitle.textContent = `${indicatorTitle} (데이터 연동 실패)`;
        return; // Don't chart on error
    }
    
    // Find High and Low
    const maxVal = Math.max(...data);
    const minVal = Math.min(...data);
    const maxIdx = data.indexOf(maxVal);
    const minIdx = data.indexOf(minVal);
    
    // Create point radius array (only highlight max/min)
    const pointRadius = data.map((v, i) => (i === maxIdx || i === minIdx) ? 6 : 0);
    const pointColors = data.map((v, i) => {
        if (i === maxIdx) return '#ef4444'; // Red for high
        if (i === minIdx) return '#3b82f6'; // Blue for low
        return '#4ade80';
    });

    // 12-month moving average -- equities only. A one-year average against a
    // price index is a convention traders already read; drawn over a bond
    // yield, an FX cross or a policy rate it suggests a signal those series
    // are not conventionally judged by, so those charts stay bare.
    const MA_WINDOW = 12;
    let runningSum = 0;
    const movingAvg = !withMovingAverage ? null : data.map((v, i) => {
        runningSum += v;
        if (i >= MA_WINDOW) runningSum -= data[i - MA_WINDOW];
        return i >= MA_WINDOW - 1 ? runningSum / MA_WINDOW : null;
    });

    const priceDataset = {
        label: indicatorTitle,
        data: data,
        borderColor: '#4ade80',
        borderWidth: 2,
        tension: 0.1,
        pointRadius: pointRadius,
        pointBackgroundColor: pointColors,
        pointBorderColor: '#ffffff',
        pointHoverRadius: 8
    };
    const maDataset = {
        label: '12개월 이동평균',
        data: movingAvg,
        borderColor: '#f59e0b',
        borderWidth: 1.5,
        borderDash: [6, 4],
        tension: 0.2,
        pointRadius: 0,
        pointHoverRadius: 0,
        spanGaps: false
    };
    const datasets = movingAvg ? [priceDataset, maDataset] : [priceDataset];

    const ctx = document.getElementById('macroChart').getContext('2d');

    if (macroChartInstance) {
        macroChartInstance.destroy();
    }

    macroChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    labels: { color: '#94a3b8', boxWidth: 18, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const val = context.parsed.y;
                            if (val === null || val === undefined) return null;
                            // The high/low marks belong to the price series only;
                            // annotating them on the moving average would claim a
                            // peak the averaged line never actually had.
                            if (context.datasetIndex !== 0) {
                                return `${context.dataset.label} ${val.toFixed(2)}`;
                            }
                            let label = val.toFixed(2);
                            if (context.dataIndex === maxIdx) label += ' (전고점)';
                            if (context.dataIndex === minIdx) label += ' (전저점)';
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8', maxTicksLimit: 12 }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
};

closeModal.addEventListener('click', () => {
    chartModal.classList.add('hidden');
});

chartModal.addEventListener('click', (e) => {
    if (e.target === chartModal) {
        chartModal.classList.add('hidden');
    }
});

// Attach clicks to indicator items
document.querySelectorAll('.indicator-item').forEach(item => {
    item.addEventListener('click', () => {
        const title = item.querySelector('.ind-title').textContent;
        openChartModal(title);
    });
});

// The 오늘 신호 panel binds its own listeners; run it here, after openChartModal
// and setView exist, since its slots and fixed cards call into both.
initSignalPanel();

// Event Listeners for Nav
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        // currentTarget is the <a data-target>; e.target can be a text node.
        const target = link.getAttribute('data-target') || e.currentTarget?.getAttribute?.('data-target');
        if (!target) return;
        if (target.startsWith('shipping_')) {
            window.history.replaceState(null, '', `#/${target}`);
        } else if (window.location.hash.startsWith('#/shipping_')) {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
        setView(target);
    });
});

// Parent menu labels with data-nav-default (e.g. 해운 → first shipping view).
// Capture phase on the whole .menu-item so padding clicks aren't swallowed by
// hover/dropdown quirks. Ignore .dropdown so submenu <a> still owns those.
document.querySelectorAll('.menu-item[data-nav-default]').forEach((item) => {
    const go = (e) => {
        const t = e.target instanceof Element ? e.target : item;
        if (t.closest('.dropdown')) return;
        e.preventDefault();
        e.stopPropagation();
        const target = item.getAttribute('data-nav-default');
        if (!target) return;
        if (target.startsWith('shipping_')) {
            window.history.replaceState(null, '', `#/${target}`);
        }
        setView(target);
    };
    item.addEventListener('click', go, true);
    const parent = item.querySelector(':scope > .menu-parent, :scope > span');
    if (parent) {
        parent.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                go(e);
            }
        });
    }
});

// Home Logo click event
document.getElementById('home-logo').addEventListener('click', () => {
    if (window.location.hash) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    setView('home');
});

// Date Picker Event (Historical Data Simulation)
document.getElementById('historical-date').addEventListener('change', (e) => {
    const selectedDate = e.target.value;
    console.log(`Loading historical data for: ${selectedDate}`);
    
    // UI Feedback
    const originalTitle = currentViewTitle.textContent;
    currentViewTitle.textContent = "과거 데이터 불러오는 중...";
    
    setTimeout(() => {
        // Simulate data swapping by modifying the mock data slightly
        // In a real app, this would fetch data from Cloudflare D1/KV via an API endpoint.
        const randomFactor = 0.5 + Math.random(); // 0.5 to 1.5
        
        if (window.TradeData[currentCommodity] && window.TradeData[currentCommodity].arcs) {
            window.TradeData[currentCommodity].arcs.forEach(arc => {
                arc.volume = Math.round(arc.volume * randomFactor);
            });
            // Re-render the map if we are on a commodity view
            if (currentCommodity !== 'home' && currentCommodity !== 'climate' && !currentCommodity.startsWith('inst_')) {
                setView(currentCommodity);
            }
        }
        
        currentViewTitle.textContent = `${selectedDate} 기준 데이터 조회됨`;
        setTimeout(() => {
            currentViewTitle.textContent = originalTitle; // Revert after 3 seconds
        }, 3000);
        
    }, 500); // 500ms mock network delay
});

// Panels render clickable region lists, so these need to be reachable
// from inline handlers.
window.updateForecastPanel = updateForecastPanel;

// Live commodity ticker (Worker /api/ticker with locale, static JSON fallback).
// Without this the UI stayed on hardcoded placeholder headlines while CI
// already rebuilt ticker_v1.json.
const loadTicker = async () => {
    const el = document.getElementById('ticker-content');
    if (!el) return;
    let items = null;
    try {
        const res = await fetch('/api/ticker?limit=24');
        if (res.ok) {
            const doc = await res.json();
            items = doc.items || [];
        }
    } catch (_) { /* local file:// or worker missing */ }
    if (!items?.length) {
        try {
            const res = await fetch('/public/data/ticker_v1.json', { cache: 'no-cache' });
            if (res.ok) {
                const doc = await res.json();
                items = doc.items || [];
            }
        } catch (err) {
            console.warn('[ticker] unavailable', err);
            return;
        }
    }
    if (!items?.length) return;

    const parts = items.map((it) => {
        const title = it.display_title
            || (it.title && (it.title.ko || it.title.original))
            || it.title
            || '';
        if (!title) return '';
        const tag = (it.commodities && it.commodities[0])
            || it.category
            || (it.source && it.source.region)
            || '뉴스';
        const safeTag = String(tag).replace(/</g, '');
        const safeTitle = String(title).replace(/</g, '');
        return `<span class="ticker-item"><span class="ticker-hl">[${safeTag}]</span> ${safeTitle}</span>`;
    }).filter(Boolean);

    if (!parts.length) return;
    // Duplicate once so CSS marquee loops without a visible gap.
    el.innerHTML = parts.join('<span class="ticker-divider">·</span>')
        + '<span class="ticker-divider">·</span>'
        + parts.join('<span class="ticker-divider">·</span>');
};

// Initialize a shareable shipping deep link when present; otherwise home.
const initialShippingTarget = window.location.hash.startsWith('#/shipping_')
    ? window.location.hash.slice(2)
    : null;
const initialView = initialShippingTarget && document.querySelector(`[data-target="${initialShippingTarget}"]`)
    ? initialShippingTarget
    : 'home';
setView(initialView);
updateNewsPanel('Global Market');
loadTicker();

window.__deckgl = typeof deckgl !== "undefined" ? deckgl : null;
