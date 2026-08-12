// Application Logic for Global Trade Dashboard
const { DeckGL, LineLayer, ArcLayer, PathLayer, ScatterplotLayer, GeoJsonLayer,
        SolidPolygonLayer, SimpleMeshLayer, COORDINATE_SYSTEM, TextLayer,
        _GlobeView, MapView, WebMercatorViewport } = deck;
const { SphereGeometry } = luma;

// DOM Elements
const tooltipEl = document.getElementById('tooltip');
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
        updateMacroPanel(window.MacroData);
    }
};

if (window.MacroData) {
    window.initApp();
}

// Update Macro Panel with FRED Data
const updateMacroPanel = (macro) => {
    const formatVal = (id, val) => {
        if (!val || val === "N/A") return "N/A";
        const num = parseFloat(val);
        if (id === "EUR/USD" || id === "USD/JPY") return num.toFixed(4);
        if (id === "NASDAQ") return num.toLocaleString();
        if (id === "WTI_OIL") {
            if (isNaN(num)) return val;
            return `$${num.toFixed(2)}`;
        }
        if (id === "NAT_GAS") {
            if (isNaN(num)) return val;
            return `$${num.toFixed(3)}`; // Natural Gas prices are typically quoted to 3 decimal places (e.g. $2.145)
        }
        if (id === "FED_BS") return `$${(num / 1000000).toFixed(2)} Trillion`;
        if (id === "TGA") return `$${(num / 1000).toFixed(0)} Billion`;
        if (id === "KRW_USD") return `${num.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} 원`;
        if (id === "BOK_RATE") return `${num.toFixed(2)}%`;
        return val;
    };

    if(macro["EUR/USD"]) document.getElementById('macro-eur-usd').innerText = formatVal("EUR/USD", macro["EUR/USD"].value);
    if(macro["USD/JPY"]) document.getElementById('macro-usd-jpy').innerText = formatVal("USD/JPY", macro["USD/JPY"].value);
    if(macro["NASDAQ"]) document.getElementById('macro-nasdaq').innerText = formatVal("NASDAQ", macro["NASDAQ"].value);
    if(macro["WTI_OIL"]) document.getElementById('macro-wti').innerText = formatVal("WTI_OIL", macro["WTI_OIL"].value);
    if(macro["NAT_GAS"]) document.getElementById('macro-natgas').innerText = formatVal("NAT_GAS", macro["NAT_GAS"].value);
    if(macro["FED_BS"]) {
        document.getElementById('macro-fed-bs').innerText = formatVal("FED_BS", macro["FED_BS"].value);
        document.getElementById('macro-fed-bs-date').innerText = `최근 업데이트: ${macro["FED_BS"].date}`;
    }
    if(macro["TGA"]) {
        document.getElementById('macro-tga').innerText = formatVal("TGA", macro["TGA"].value);
        document.getElementById('macro-tga-date').innerText = `최근 업데이트: ${macro["TGA"].date}`;
    }
    if(macro["KRW_USD"]) document.getElementById('macro-krw-usd').innerText = formatVal("KRW_USD", macro["KRW_USD"].value);
    if(macro["BOK_RATE"]) document.getElementById('macro-bok-rate').innerText = formatVal("BOK_RATE", macro["BOK_RATE"].value);
};

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
        tooltipEl.style.left = `${info.x}px`;
        tooltipEl.style.top = `${info.y}px`;
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

/** Clear trade country focus and redraw world flows. */
const clearTradeFocus = () => {
    tradeFocusCountry = null;
    selectedCountry = null;
    // Put the world-level labels back; stage 2 rewrote them in place.
    const d = window.TradeData?.[currentCommodity];
    const lv = document.getElementById('stat-label-volume');
    const lt = document.getElementById('stat-label-exporter');
    if (lv) lv.textContent = '글로벌 무역량';
    if (lt) lt.textContent = '최대 수출국';
    if (d) {
        if (totalVolumeEl) totalVolumeEl.textContent = d.totalVolume;
        if (topExporterEl) topExporterEl.textContent = d.topExporter;
    }
    if (currentCommodity && window.TradeData?.[currentCommodity]?.arcs?.length) {
        renderMapLayers(window.TradeData[currentCommodity].arcs);
        renderTradeWorldPanel(window.TradeData[currentCommodity].arcs);
        panelHide(countryStatsPanelEl);
        panelShow(newsPanelEl);
    }
};

/**
 * China-style country focus for every nation: show that country's export
 * (or import if it is mainly a buyer) routes with share %, destination
 * ranking on the left, and flowing highlight particles. Right pane stays
 * empty — user will fill country detail later.
 */
const focusTradeCountry = (countryName) => {
    if (!currentCommodity || !window.TradeData?.[currentCommodity]) return;
    const arcs = window.TradeData[currentCommodity].arcs || [];
    if (!arcs.length) return;

    tradeFocusCountry = countryName;
    selectedCountry = countryName;
    updateNewsPanel(countryName);

    // Identity, not string equality: the same country reaches this function as
    // "USA" from a curated node and as "United States of America" from a map
    // polygon, and newly uploaded data may spell it a third way.
    const target = resolveCountry(countryName);
    const displayName = target?.label || countryName;
    const sameCountry = (a, b) => {
        if (a === b) return true;
        const ra = resolveCountry(a);
        const rb = resolveCountry(b);
        return !!(ra && rb && ra.key === rb.key);
    };
    const exports = arcs.filter((a) => sameCountry(a.sourceName, countryName));
    const imports = arcs.filter((a) => sameCountry(a.targetName, countryName));
    const exportVol = exports.reduce((s, a) => s + a.volume, 0);
    const importVol = imports.reduce((s, a) => s + a.volume, 0);
    const asExporter = exportVol >= importVol && exports.length > 0;
    // Both directions, not just the larger one. US crude imports dwarf its
    // exports, so picking the bigger side dropped every US export route from
    // the map -- the country looked like a pure buyer, which it is not.
    const focused = [...exports, ...imports].sort((a, b) => b.volume - a.volume);
    const inboundKeys = new Set(imports.map((a) => `${a.sourceName}>${a.targetName}`));
    const total = focused.reduce((s, a) => s + a.volume, 0) || 1;

    // Left list: partner ranking with % (same pattern for China / USA / anyone)
    // Every commodity's `volume` is Millions USD -- data.js divides Comtrade's
    // primaryValue by 1e6 regardless of commodity. Gold and silver were labelled
    // "Tonnes eq.", which named a quantity the figure is not.
    const unit = 'M USD';
    const roleKo = asExporter ? '수출 → 대상국' : '수입 ← 공급국';
    const maxVol = focused[0]?.volume || 1;
    const rows = focused.slice(0, 14).map((a, i) => {
        const isIn = inboundKeys.has(`${a.sourceName}>${a.targetName}`);
        const partner = resolveCountry(isIn ? a.sourceName : a.targetName)?.label
            || (isIn ? a.sourceName : a.targetName);
        // Share is of that direction's own total; mixing the two would make
        // every percentage smaller than it is.
        const denom = (isIn ? importVol : exportVol) || 1;
        const share = (a.volume / denom) * 100;
        return `<div class="trade-rank-row trade-bar-row${isIn ? ' is-inbound' : ''}"
                     data-partner="${partner}" title="${isIn ? '수입' : '수출'} · ${partner} · ${a.volume.toLocaleString()} ${unit}">
            <span class="tr-i">${i + 1}</span>
            <span class="tr-dir" aria-label="${isIn ? '수입' : '수출'}"></span>
            <span class="tr-name tr-code">${countryCode(partner)}</span>
            <span class="tr-bar"><i style="width:${Math.max(3, (a.volume / maxVol) * 100)}%"></i></span>
            <span class="tr-pct">${share.toFixed(1)}%</span>
            <span class="tr-vol">${a.volume.toLocaleString()}</span>
        </div>`;
    }).join('');

    // Export / import / net, so a country reads as a position rather than a
    // one-directional list. Net is what says whether it is a seller or a buyer.
    const net = exportVol - importVol;
    const statsHtml = `
        <div class="trade-stat-row" data-unit="${unit}">
            <div class="ts-cell"><span class="ts-k">수출 (${unit})</span>
                <span class="ts-v">${exportVol.toLocaleString()}</span></div>
            <div class="ts-cell"><span class="ts-k">수입 (${unit})</span>
                <span class="ts-v">${importVol.toLocaleString()}</span></div>
            <div class="ts-cell"><span class="ts-k">순수지 (${unit})</span>
                <span class="ts-v ${net >= 0 ? 'pos' : 'neg'}">${net >= 0 ? '+' : ''}${net.toLocaleString()}</span></div>
        </div>`;

    // Which side carries the dependency. A buyer's exposure is its suppliers;
    // a country that only sells has no supply risk here, but it does have
    // customer risk, and that is the concentration worth showing instead.
    const depHtml = importVol > 0
        ? concentrationHtml(imports, (a) => a.sourceName, '공급')
        : concentrationHtml(exports, (a) => a.targetName, '판로');

    if (newsPanelEl) panelShow(newsPanelEl);
    panelHide(countryStatsPanelEl);
    panelHide(macroPanelEl);
    const newsTitle = document.querySelector('#news-panel .section-title');
    if (newsTitle) newsTitle.textContent = `${displayName} · ${roleKo}`;
    if (newsContentEl) {
        newsContentEl.innerHTML = `
            <div class="trade-focus-card">
                <div class="trade-focus-head">
                    <strong>${displayName}</strong>
                    <button type="button" class="trade-focus-clear" id="trade-focus-clear">전체 지도</button>
                </div>
                <p class="trade-focus-sub">수출·수입 양방향 · 비중은 각 방향 내 비중 · 물동량(${unit})</p>
                ${statsHtml}
                ${depHtml}
                <div class="trade-rank-list">${rows || '<p class="empty-state">이 국가 루트 없음</p>'}</div>
            </div>`;
        document.getElementById('trade-focus-clear')?.addEventListener('click', (e) => {
            e.preventDefault();
            clearTradeFocus();
        });
    }

    // Stage 2 stats become the country's, not the world's. "글로벌 무역량
    // 98.5 Million bpd" said the same thing on every country's screen, which
    // is the one number a country view should not repeat.
    const worldVol = arcs.reduce((s, a) => s + (a.volume > 0 ? a.volume : 0), 0) || 1;
    const countryVol = exportVol + importVol;
    const top = focused[0];
    if (top) {
        const isIn = inboundKeys.has(`${top.sourceName}>${top.targetName}`);
        const partner = resolveCountry(isIn ? top.sourceName : top.targetName)?.label
            || (isIn ? top.sourceName : top.targetName);
        const statLabelVol = document.getElementById('stat-label-volume');
        const statLabelTop = document.getElementById('stat-label-exporter');
        if (statLabelVol) statLabelVol.textContent = '글로벌 비중';
        if (statLabelTop) statLabelTop.textContent = isIn ? '최대 공급국' : '최대 수출 대상국';
        if (totalVolumeEl) {
            totalVolumeEl.textContent = `${((countryVol / worldVol) * 100).toFixed(1)}%`;
        }
        if (topExporterEl) topExporterEl.textContent = partner;
    }

    const ctl = controlsFor(currentCommodity).get(target?.key || countryName);
    if (ctl && newsContentEl) {
        const lv = exportControlsDoc?.levels?.[ctl.level]?.label_ko || ctl.level;
        newsContentEl.insertAdjacentHTML('afterbegin', `
            <div class="ctl-card ctl-${ctl.level}">
                <div class="ctl-head"><strong>${lv}</strong>
                    <span class="ctl-since">${ctl.since || ''}~</span></div>
                <div class="ctl-measure">${ctl.measure_ko || ''}</div>
                <div class="ctl-src">${ctl.source || ''}
                    ${ctl.url ? `<a href="${ctl.url}" target="_blank" rel="noopener">원문 ↗</a>` : ''}
                    · 신뢰도 ${ctl.confidence || '—'}</div>
            </div>`);
    }

    currentViewDesc.textContent = `${displayName} ${roleKo} · ${focused.length}개 루트 · 배경 클릭 또는 「전체 지도」로 초기화`;
    renderMapLayers(arcs, { focus: countryName, asExporter, focused, inboundKeys, keepView: true });
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
const countryCode = (name) => {
    const r = resolveCountry(name);
    if (r?.iso) return r.iso;
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

/**
 * US emergency crude stocks: the SPR and the Cushing hub.
 *
 * A flow map says who ships to whom but nothing about the buffer behind it.
 * Cushing is the WTI delivery point -- when it runs low the contract moves on
 * storage rather than supply -- and the SPR is the release valve a government
 * actually pulls. Neither is visible in trade data.
 *
 * EIA reports these weekly, so the card carries the week-on-week change; a
 * level alone does not say whether a buffer is filling or draining.
 */
const EIA_STOCKS = [
    { id: 'spr', label_ko: '미국 전략비축유 (SPR)', series: 'WCSSTUS1',
      route: 'petroleum/stoc/wstk/data/' },
    { id: 'cushing', label_ko: '쿠싱 원유 저장 (WTI 인도지점)', series: 'W_EPC0_SAX_YCUOK_MBBL',
      route: 'petroleum/stoc/wstk/data/' },
];
let eiaStocksCache = null;

const loadEiaStocks = async () => {
    if (eiaStocksCache) return eiaStocksCache;
    const out = [];
    for (const s of EIA_STOCKS) {
        try {
            const r = await fetch(
                `/api/macro?source=eia&route=${encodeURIComponent(s.route)}&seriesId=${s.series}`);
            if (!r.ok) continue;
            const j = await r.json();
            const rows = j?.response?.data || j?.data || [];
            if (!rows.length) continue;
            const latest = Number(rows[0]?.value);
            const prev = rows.length > 1 ? Number(rows[1]?.value) : null;
            if (!Number.isFinite(latest)) continue;
            out.push({
                ...s,
                value: latest,
                period: rows[0]?.period || '',
                change: Number.isFinite(prev) ? latest - prev : null,
            });
        } catch (err) {
            // The map is the point; a missing buffer card is not worth failing over.
            console.warn(`[EIA] ${s.id} unavailable`, err);
        }
    }
    eiaStocksCache = out;
    return out;
};

/** Only meaningful for crude; other commodities have no equivalent series. */
const renderEmergencyStocks = async () => {
    const host = document.getElementById('news-content');
    if (!host || currentCommodity !== 'oil') return;
    const stocks = await loadEiaStocks();
    if (!stocks.length || currentCommodity !== 'oil') return;
    host.insertAdjacentHTML('beforeend', `
        <div class="stock-card">
            <p class="section-title" style="margin:0 0 6px;">글로벌 비상 재고 · EIA 주간</p>
            ${stocks.map((s) => {
                const up = s.change != null && s.change > 0;
                return `<div class="stock-row">
                    <span class="nm">${s.label_ko}</span>
                    <span class="vl">${(s.value / 1000).toFixed(1)}<em>백만 배럴</em></span>
                    <span class="ch ${s.change == null ? '' : (up ? 'up' : 'down')}">
                        ${s.change == null ? '—'
                            : `${up ? '+' : ''}${(s.change / 1000).toFixed(1)}`}</span>
                </div>`;
            }).join('')}
            <div class="stock-note">${stocks[0]?.period || ''} 기준 · 전주 대비 증감 · 출처 EIA</div>
        </div>`);
};

const renderTradeWorldPanel = (arcs) => {
    const byExporter = new Map();
    for (const a of arcs) {
        if (!(a.volume > 0)) continue;
        const key = resolveCountry(a.sourceName)?.label || a.sourceName;
        byExporter.set(key, (byExporter.get(key) || 0) + a.volume);
    }
    const ranked = [...byExporter.entries()].sort((x, y) => y[1] - x[1]);
    const total = ranked.reduce((s, [, v]) => s + v, 0) || 1;
    const max = ranked[0]?.[1] || 1;

    const rows = ranked.slice(0, 10).map(([name, vol], i) => {
        const share = (vol / total) * 100;
        return `<div class="trade-rank-row trade-bar-row is-world climate-click"
                     role="button" tabindex="0" data-trade-country="${name}"
                     title="${name} · ${share.toFixed(1)}%">
            <span class="tr-i">${i + 1}</span>
            <span class="tr-name tr-code">${countryCode(name)}</span>
            <span class="tr-bar"><i style="width:${Math.max(3, (vol / max) * 100)}%"></i></span>
            <span class="tr-pct">${share.toFixed(1)}%</span>
        </div>`;
    }).join('');

    if (!newsContentEl) return;
    const newsTitle = document.querySelector('#news-panel .section-title');
    if (newsTitle) newsTitle.textContent = '주요 수출국 · 물동량 상위';
    newsContentEl.innerHTML = `
        <div class="trade-focus-card">
            <p class="trade-focus-sub">비중% · 막대는 상대 물동량 · 국가를 누르면 그 나라 노선만 남습니다</p>
            <div class="trade-rank-list">${rows || '<p class="empty-state">무역 루트 없음</p>'}</div>
        </div>`;
    renderEmergencyStocks();
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
            tooltipEl.style.left = `${info.x + 12}px`;
            tooltipEl.style.top = `${info.y + 12}px`;
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

// Flow particles are the one thing on this map that moves; some readers want
// the structure still. Toggling redraws rather than pausing, so a paused map is
// never a frame frozen mid-animation.
document.getElementById('trade-flow-toggle')?.addEventListener('click', (e) => {
    tradeFlowOn = !tradeFlowOn;
    const b = e.currentTarget;
    b.textContent = tradeFlowOn ? '켜기' : '끄기';
    b.classList.toggle('is-on', tradeFlowOn);
    const arcs = window.TradeData?.[currentCommodity]?.arcs;
    if (arcs?.length) renderMapLayers(arcs, { focus: tradeFocusCountry, keepView: true });
});

// Ranking rows focus a country, same as clicking it on the globe.
document.getElementById('news-content')?.addEventListener('click', (e) => {
    const row = e.target instanceof Element ? e.target.closest('[data-trade-country]') : null;
    if (!row || currentCommodity === 'climate') return;
    const label = row.getAttribute('data-trade-country');
    const arcs = window.TradeData?.[currentCommodity]?.arcs || [];
    // Rows carry the display label; find whatever spelling the data uses.
    const hit = arcs.find((a) => (resolveCountry(a.sourceName)?.label || a.sourceName) === label);
    if (hit) focusTradeCountry(hit.sourceName);
});

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
    tooltipEl.style.left = `${info.x + 12}px`;
    tooltipEl.style.top = `${info.y + 12}px`;
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
            tooltipEl.style.left = `${info.x + 10}px`;
            tooltipEl.style.top = `${info.y + 10}px`;
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

/**
 * Travelling dash segments along each route.
 *
 * These were circles sliding along the arc, which read as objects moving over
 * the map rather than the route itself being alive. The mockup animates a
 * dasharray of "34 452" -- one short dash inside a long gap -- so what travels
 * is a piece of the line. Rebuilt per frame because deck's dash support has no
 * animatable offset.
 */
const DASH_STEPS = 8;
const DASH_SPAN = 0.06;
const DASH_RES = 72;

const buildTradeDashes = (arcs, phase) => {
    const out = [];
    const n = Math.min(arcs.length, 60);
    for (let i = 0; i < n; i++) {
        const arc = arcs[i];
        if (!arc.sourcePosition || !arc.targetPosition) continue;
        const full = bowedPath(arc.sourcePosition, arc.targetPosition, DASH_RES);
        // Stagger start and speed so routes do not pulse in lockstep.
        const head = ((phase * (1 + (i % 5) * 0.13)) + (i % 7) / 7) % 1;
        const path = [];
        for (let s = 0; s <= DASH_STEPS; s++) {
            const f = head + (s / DASH_STEPS) * DASH_SPAN;
            if (f > 1) break;
            path.push(full[Math.round(f * DASH_RES)]);
        }
        if (path.length < 2) continue;
        const c = arc.sourceColor || [125, 211, 252];
        out.push({
            path,
            color: [Math.min(255, c[0] + 70), Math.min(255, c[1] + 70),
                    Math.min(255, c[2] + 70), 230],
            width: Math.max(1.5, arcWidth(arc.volume) * 0.9),
        });
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

let tradeFlowOn = true;

const renderMapLayers = (arcs, opts = {}) => {
    stopTradeAnim();
    document.body.classList.add('trade-map-mode');
    document.body.classList.remove('shipping-mode');
    document.getElementById('trade-overlay')?.classList.remove('hidden');

    const focus = opts.focus || tradeFocusCountry;
    const asExporter = opts.asExporter !== false;
    let filteredArcs = arcs.filter((arc) => arc.volume > 0);
    arcVolumeMax = filteredArcs.reduce((m, a) => Math.max(m, a.volume), 1);
    // The mockup drops flows under a threshold rather than drawing every pair.
    // Below ~1.5% of the largest route a line adds noise, not information.
    const arcFloor = arcVolumeMax * 0.015;
    filteredArcs = filteredArcs.filter((a) => a.volume >= arcFloor);

    if (focus) {
        const focusKey = resolveCountry(focus)?.key || focus;
        const focused = (opts.focused && opts.focused.length)
            ? opts.focused
            : filteredArcs.filter((a) => {
                const side = asExporter ? a.sourceName : a.targetName;
                return (resolveCountry(side)?.key || side) === focusKey;
            });
        const focusSet = new Set(focused.map((a) => `${a.sourceName}>${a.targetName}`));
        // Dim world context + bright focused routes (China-style for every country)
        filteredArcs = [
            ...filteredArcs
                .filter((a) => !focusSet.has(`${a.sourceName}>${a.targetName}`))
                .sort((a, b) => b.volume - a.volume)
                .slice(0, 80),
            ...focused.slice(0, 60),
        ];
        opts._focusedSet = focusSet;
        opts._inbound = opts.inboundKeys || new Set();
        opts._focusedList = focused.slice(0, 40);
    } else {
        // Sort first. This used to slice the array as it arrived, so the cap
        // kept the first 120 routes rather than the largest 120 -- Turkey is
        // the biggest reporter in the gold data with 69 routes and only three
        // survived, which read as Turkey being absent from the trade entirely.
        filteredArcs = filteredArcs
            .slice()
            .sort((a, b) => b.volume - a.volume)
            .slice(0, MAX_RENDERED_ARCS);
        opts._focusedList = filteredArcs.slice(0, 36);
    }

    const nodeData = generateNodeData(
        focus
            ? (opts._focusedList || filteredArcs)
            : filteredArcs
    );
    const totalFocus = (opts._focusedList || []).reduce((s, a) => s + a.volume, 0) || 1;
    const nodeTradeMax = nodeData.reduce((m, d) => Math.max(m, d.totalTrade), 1);

    if (!opts.keepView) currentViewState = clampGlobeView({ ...TRADE_MAP_VIEW });
    const tradeControls = controlsFor(currentCommodity);
    renderExportControlLegend(tradeControls);

    const baseLayers = () => [
        ...worldBaseLayers({ id: 'trade' }),
        // Exporters get a warm rim so source and destination read apart even
        // before the flow particles start moving.
        new GeoJsonLayer({
            id: 'trade-focus-outline',
            data: worldGeo(),
            stroked: true,
            filled: true,
            lineWidthMinPixels: 1.4,
            getFillColor: (f) => (focus && featureIsCountry(f, focus)
                ? [56, 189, 248, 55]
                : [0, 0, 0, 0]),
            getLineColor: (f) => (focus && featureIsCountry(f, focus)
                ? [125, 211, 252, 220]
                : [0, 0, 0, 0]),
            pickable: false,
            updateTriggers: { getFillColor: [focus], getLineColor: [focus] },
        }),
        // Countries under an export control on this commodity.
        new GeoJsonLayer({
            id: 'trade-export-controls',
            data: worldGeo(),
            stroked: true,
            filled: true,
            pickable: false,
            lineWidthMinPixels: 1,
            getFillColor: (f) => {
                const c = tradeControls.get(featureCountryName(f));
                return c ? (CONTROL_FILL[c.level] || CONTROL_FILL.watch) : [0, 0, 0, 0];
            },
            getLineColor: (f) => {
                const c = tradeControls.get(featureCountryName(f));
                return c ? (CONTROL_LINE[c.level] || CONTROL_LINE.watch) : [0, 0, 0, 0];
            },
            updateTriggers: {
                getFillColor: [currentCommodity, tradeControls.size],
                getLineColor: [currentCommodity, tradeControls.size],
            },
        }),
        new GeoJsonLayer({
            id: 'trade-countries-pick',
            data: worldGeo(),
            stroked: false,
            filled: true,
            pickable: true,
            getFillColor: [0, 0, 0, 0],
            autoHighlight: true,
            highlightColor: [125, 211, 252, 40],
        }),
        new PathLayer({
            id: `arc-layer-${currentCommodity}-${focus || 'world'}`,
            data: filteredArcs,
            pickable: true,
            widthUnits: 'pixels',
            capRounded: true,
            jointRounded: true,
            getPath: (d) => bowedPath(d.sourcePosition, d.targetPosition),
            getWidth: (d) => {
                const key = `${d.sourceName}>${d.targetName}`;
                const hot = !focus || opts._focusedSet?.has(key);
                const base = arcWidth(d.volume);
                return hot ? base : Math.max(0.3, base * 0.3);
            },
            getColor: (d) => {
                const key = `${d.sourceName}>${d.targetName}`;
                if (focus && !opts._focusedSet?.has(key)) return [90, 110, 140, 12];
                // With both directions shown, colour carries which is which:
                // outbound keeps the commodity colour, inbound goes slate.
                if (focus && opts._inbound?.has(key)) {
                    return [148, 163, 184, arcAlpha(d.volume)];
                }
                const c = d.sourceColor || [56, 189, 248];
                return [c[0], c[1], c[2], arcAlpha(d.volume)];
            },
            updateTriggers: { getWidth: [focus], getColor: [focus] },
            onHover: (info) => {
                if (!info.object) {
                    tooltipEl.classList.add('hidden');
                    return;
                }
                const d = info.object;
                const share = focus
                    ? ((d.volume / totalFocus) * 100).toFixed(1)
                    : d.percentage;
                tooltipEl.style.left = `${info.x + 12}px`;
                tooltipEl.style.top = `${info.y + 12}px`;
                tooltipEl.classList.remove('hidden');
                tooltipEl.innerHTML = `
                    <div class="tooltip-title">${d.sourceName} → ${d.targetName}</div>
                    <div class="tooltip-stat"><span>비중</span><span style="color:#38bdf8;font-weight:700;">${share}%</span></div>
                    <div class="tooltip-stat"><span>물동량</span><span>${d.volume.toLocaleString()}</span></div>`;
            },
            onClick: handleLineClick,
            autoHighlight: true,
            highlightColor: [255, 255, 255, 200],
        }),
        new ScatterplotLayer({
            id: `scatter-layer-${currentCommodity}`,
            data: nodeData,
            pickable: true,
            opacity: 0.9,
            stroked: true,
            filled: true,
            // Pixels on a sqrt curve, as the mockup does (2–9.5px). Sizing in
            // metres meant the biggest traders were drawn as discs wide enough
            // to cover the country underneath them, and they grew further on
            // zoom.
            radiusUnits: 'pixels',
            radiusMinPixels: 2,
            radiusMaxPixels: 10,
            lineWidthMinPixels: 0.8,
            getPosition: (d) => d.coordinates,
            getRadius: (d) => {
                const m = nodeTradeMax || 1;
                return 2 + 7.5 * Math.min(1, Math.sqrt(d.totalTrade / m));
            },
            updateTriggers: { getRadius: [currentCommodity, focus] },
            getFillColor: (d) => (d.name === focus ? [56, 189, 248, 230] : [15, 23, 42, 220]),
            getLineColor: (d) => (d.name === focus ? [255, 255, 255, 255] : [200, 220, 255, 160]),
            onClick: handleNodeClick,
        }),
    ];

    const trailData = () => (tradeFlowOn
        ? buildTradeDashes(opts._focusedList || filteredArcs.slice(0, 40), tradeAnimPhase)
        : []);

    deckgl.setProps({
        views: [new MapView({ id: 'map', controller: true, repeat: true })],
        viewState: currentViewState,
        controller: { dragRotate: false, touchRotate: false },
        layers: [
            ...baseLayers(),
            new PathLayer({
                id: `trade-trail-${currentCommodity}`,
                data: trailData(),
                pickable: false,
                widthUnits: 'pixels',
                capRounded: true,
                jointRounded: true,
                getPath: (d) => d.path,
                getColor: (d) => d.color,
                getWidth: (d) => d.width,
            }),
        ],
        onClick: (info) => {
            // Clicking the map away from a route clears the focus. The country
            // polygon layer is pickable, so a click on any other country counts
            // as "away" too -- previously only the ocean did, which made getting
            // back to the world map harder than getting into a country.
            if (!info.object) {
                if (tradeFocusCountry) clearTradeFocus();
                return;
            }
            if (tradeFocusCountry && info.layer?.id === 'trade-countries-pick') {
                const fname = info.object?.properties?.name;
                const same = fname && resolveCountry(fname)?.key
                    === resolveCountry(tradeFocusCountry)?.key;
                if (same) { clearTradeFocus(); return; }
            }
            // Country polygon click: focus it if it appears anywhere in the
            // current commodity's routes, so any country in the data works --
            // not only the ones large enough to have drawn a node.
            const fname = info.object?.properties?.name;
            if (fname && info.layer?.id === 'trade-countries-pick') {
                const rec = resolveCountry(fname);
                const arcsAll = window.TradeData?.[currentCommodity]?.arcs || [];
                const named = arcsAll.find((a) =>
                    resolveCountry(a.sourceName)?.key === rec?.key
                    || resolveCountry(a.targetName)?.key === rec?.key);
                const dataName = named
                    ? (resolveCountry(named.sourceName)?.key === rec?.key
                        ? named.sourceName : named.targetName)
                    : null;
                if (dataName) focusTradeCountry(dataName);
            }
        },
        onViewStateChange: ({ viewState }) => {
            if (!window.TradeData?.[currentCommodity]) return;
            const next = clampGlobeView(viewState);
            currentViewState = next;
            deckgl.setProps({ viewState: next });
        },
    });

    // Only the trail layer changes per frame. Rebuilding the basemap and the
    // arcs 22x a second re-uploaded the whole world geometry for no visual gain
    // (and, while `data` was a Promise, meant the land never finished loading).
    let staticLayers = baseLayers();
    let lastCenter = [currentViewState.longitude ?? 0, currentViewState.latitude ?? 0];
    let last = 0;
    const loop = (ts) => {
        if (!window.TradeData?.[currentCommodity] || currentCommodity === 'climate' || currentCommodity === 'home') {
            tradeAnimRaf = null;
            return;
        }
        if (ts - last > 45) {
            last = ts;
            tradeAnimPhase = (ts * 0.00008) % 1;
            // Rebuild the static half when the basemap lands, and when the
            // camera has moved far enough that the horizon clip is stale.
            // Two degrees, not every frame: re-slicing 250 polylines per frame
            // is the kind of work that shows up as jank while dragging.
            const center = [currentViewState.longitude ?? 0, currentViewState.latitude ?? 0];
            const moved = Math.abs(center[0] - lastCenter[0]) > 2
                || Math.abs(center[1] - lastCenter[1]) > 2;
            const basemapArrived = worldGeoData
                && staticLayers.find((l) => l.id.endsWith('-land'))?.props?.data !== worldGeoData;
            if (moved || basemapArrived) {
                lastCenter = center;
                staticLayers = baseLayers();
            }
            deckgl.setProps({
                layers: [
                    ...staticLayers,
                    new PathLayer({
                        id: `trade-trail-${currentCommodity}`,
                        data: trailData(),
                        pickable: false,
                        widthUnits: 'pixels',
                        capRounded: true,
                        jointRounded: true,
                        getPath: (d) => d.path,
                        getColor: (d) => d.color,
                        getWidth: (d) => d.width,
                    }),
                ],
            });
        }
        tradeAnimRaf = requestAnimationFrame(loop);
    };
    tradeAnimRaf = requestAnimationFrame(loop);
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

// --- 금융 진단 ---------------------------------------------------------------
// The engines live outside this file: portfolio risk in
// scripts/금융_재무분석 (portfolio_analysis_v1.json), corporate financials in
// scripts/dart. This side only renders. Per DATA_CONTRACT.md the wording comes
// from the payload's own ui_copy_* block rather than being written here, so the
// engine stays the single source of both the numbers and how they read.
const FIN_LOCALE = 'ko';

const finPct = (x, digits = 1) =>
    (x === null || x === undefined || Number.isNaN(x)) ? '—' : `${(x * 100).toFixed(digits)}%`;

const finSignedPct = (x, digits = 1) => {
    if (x === null || x === undefined || Number.isNaN(x)) return '—';
    const v = x * 100;
    return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%p`;
};

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

// Weight says where the money sits; risk contribution says where the account's
// movement actually comes from. Showing them on one row is the whole point of
// the panel -- a 5% position driving half the volatility is invisible otherwise.
const finRiskRows = (data) => {
    const contrib = (data.structure && data.structure.risk_contribution) || {};
    const byName = new Map((data.positions || []).map((p) => [p.name_ko, p]));
    const rows = Object.entries(contrib)
        .map(([name, rc]) => ({ name, rc, w: (byName.get(name) || {}).weight ?? null,
                                lev: (byName.get(name) || {}).leveraged,
                                proxy: (byName.get(name) || {}).proxy }))
        .sort((a, b) => b.rc - a.rc);
    const max = Math.max(...rows.map((r) => Math.abs(r.rc)), 0.0001);

    return rows.map((r) => `
        <div class="fin-risk-row">
            <div class="fin-risk-name">
                ${finEsc(r.name)}
                ${r.lev ? '<span class="fin-tag fin-tag-warn">레버리지</span>' : ''}
                ${r.proxy ? '<span class="fin-tag">프록시</span>' : ''}
            </div>
            <div class="fin-risk-bars">
                <div class="fin-bar-track" title="위험 기여 ${finPct(r.rc)}">
                    <div class="fin-bar fin-bar-risk" style="width:${Math.abs(r.rc) / max * 100}%"></div>
                </div>
                <div class="fin-bar-track" title="비중 ${finPct(r.w)}">
                    <div class="fin-bar fin-bar-weight" style="width:${(Math.abs(r.w ?? 0)) / max * 100}%"></div>
                </div>
            </div>
            <div class="fin-risk-nums">
                <span class="fin-risk-rc">${finPct(r.rc)}</span>
                <span class="fin-risk-w">${finPct(r.w)}</span>
            </div>
        </div>`).join('');
};

// Holdings never leave the browser. The engine that produced the reference
// payload runs offline; this input path keeps the portfolio in localStorage so
// there is no server that could hold someone else's positions. Price lookups
// still go through the Worker, which sees the tickers but not the amounts.
const PF_STORE = 'portfolioLab.v1';

const pfLoad = () => {
    try {
        const raw = localStorage.getItem(PF_STORE);
        if (!raw) return null;
        const p = JSON.parse(raw);
        return (p && Array.isArray(p.positions)) ? p : null;
    } catch (_) { return null; }
};

const pfSave = (p) => {
    try { localStorage.setItem(PF_STORE, JSON.stringify(p)); } catch (_) { /* quota */ }
};

const pfBlank = () => ({ risk_profile: 'balanced', base_currency: 'KRW', positions: [] });

// Covariance from ~250 daily observations needs comfortably more rows than
// assets or the estimate turns to noise -- and noisy covariance is exactly what
// the risk-contribution number is built on. 20 keeps that ratio above 12 while
// still fitting any portfolio a person actually holds.
const PF_MAX = 20;

let PF_REGISTRY = null;
let PF_PROFILES = null;

const pfLoadRefs = async () => {
    if (PF_REGISTRY && PF_PROFILES) return;
    const grab = async (name) => {
        for (const base of ['/public/data/', '/data/']) {
            try {
                const r = await fetch(base + name, { cache: 'no-store' });
                if (r.ok) return await r.json();
            } catch (_) { /* next */ }
        }
        return null;
    };
    const [reg, prof, ko] = await Promise.all([
        grab('instruments_v1.json'), grab('risk_profiles_v1.json'), grab('aliases_ko_v1.json'),
    ]);
    PF_PROFILES = (prof && prof.profiles) || {};

    // Neither Yahoo nor SEC indexes Korean names -- searching 삼성전자 through
    // either returns nothing at all. So the Korean table is not a convenience
    // layer over remote search, it is the only way a Korean name resolves.
    const engine = (reg && reg.instruments) || [];
    const known = new Set(engine.map((x) => String(x.yahoo || '').toUpperCase()));
    const koRows = ((ko && ko.instruments) || [])
        .filter((x) => !known.has(String(x.symbol).toUpperCase()))
        .map((x) => ({
            id: `ko:${x.symbol}`,
            name_ko: x.name_ko,
            yahoo: x.symbol,
            currency: 'USD',
            asset_class: x.asset_class || 'equity',
            aliases: [...(x.aliases || []), x.symbol],
            // TQQQ and SOXL are real funds: their quoted price already carries
            // the 3x. Multiplying returns again would triple-count it. The flag
            // is here for the risk-profile limit, not for the return maths --
            // which is why synthetic_leverage stays false.
            leveraged: !!x.leveraged,
            synthetic_leverage: false,
        }));

    // Engine entries first: only they carry proxy flags and leverage factors
    // that a plain ticker lookup cannot know.
    PF_REGISTRY = [...engine, ...koRows];
};

const pfKrw = (n) => (n === null || n === undefined || Number.isNaN(n))
    ? '—' : `${Math.round(n).toLocaleString('ko-KR')}원`;

// A holding is entered either as "how much it is worth" or "how many I hold".
// Shares are the honest unit for a stock -- the amount drifts with the price
// while the share count does not -- so the value is derived, and the price it
// was derived from is kept alongside it to show how stale the figure is.
const pfValueOf = (p) => {
    if (!p) return null;
    if (p.mode === 'shares') {
        if (!(p.shares > 0) || !(p.price > 0)) return null;
        return p.shares * p.price * (p.fx || 1);
    }
    const v = Number(p.value);
    return Number.isFinite(v) && v !== 0 ? v : null;
};

const pfPriceCache = new Map();

// Last close plus the exchange rate that puts it in KRW. Base-currency cash has
// neither, so it is priced at 1 and multiplied by nothing.
const pfSpot = async (symbol, currency) => {
    if (!symbol) return { price: 1, fx: 1, currency: 'KRW' };
    const key = `${symbol}|${currency || ''}`;
    if (pfPriceCache.has(key)) return pfPriceCache.get(key);
    const task = (async () => {
        const j = await pfFetchHistory(symbol, '1y');
        const cur = j.currency || currency || 'KRW';
        let fx = 1;
        const fxSym = pfFxSymbol(cur);
        if (fxSym && fxSym !== symbol) {
            const f = await pfFetchHistory(fxSym, '1y');
            fx = f.price || 1;
        }
        return { price: j.price, fx, currency: cur };
    })();
    pfPriceCache.set(key, task);
    return task;
};

// --- 계산 -------------------------------------------------------------------
// Runs entirely in the browser. The Worker only proxies public price series, so
// nobody's holdings reach a server. Deliberately mirrors the Python engine in
// scripts/금융_재무분석 so the two can be cross-checked -- that comparison is
// what surfaced the leverage bug in returns.py, and it only works if the
// formulas stay recognisably the same on both sides.
const PF_TRADING_DAYS = 252;
const PF_RF_ANNUAL = 0.03;
const PF_Z95 = 1.6448536269514722;

const pfQuoteCache = new Map();

const pfFetchHistory = async (symbol, range = '2y') => {
    const key = `${symbol}|${range}`;
    if (pfQuoteCache.has(key)) return pfQuoteCache.get(key);
    const p = (async () => {
        const res = await fetch(`/api/quote/history?symbol=${encodeURIComponent(symbol)}&range=${range}`);
        if (!res.ok) throw new Error(`${symbol}: 가격을 못 받았습니다 (${res.status})`);
        const j = await res.json();
        if (!j.points || j.points.length < 60) throw new Error(`${symbol}: 가격 이력이 너무 짧습니다`);
        return j;
    })();
    pfQuoteCache.set(key, p);
    return p;
};

// Yahoo quotes each instrument in its home currency, so a KRW-based portfolio
// has to convert before returns can be compared. Fetched as its own series
// because the exchange rate is a risk the holder actually carries.
const pfFxSymbol = (cur) => (!cur || cur === 'KRW') ? null : `${cur}KRW=X`;

const pfAlign = (series) => {
    // Intersect on trading days: markets keep different holidays, and pairing a
    // stale carried-forward close against a live one invents correlation.
    const keys = Object.keys(series);
    if (!keys.length) return { dates: [], cols: {} };
    let common = null;
    for (const k of keys) {
        const s = new Set(series[k].map(([t]) => Math.floor(t / 86400)));
        common = common === null ? s : new Set([...common].filter((d) => s.has(d)));
    }
    const dates = [...common].sort((a, b) => a - b);
    const cols = {};
    for (const k of keys) {
        const m = new Map(series[k].map(([t, v]) => [Math.floor(t / 86400), v]));
        cols[k] = dates.map((d) => m.get(d));
    }
    return { dates, cols };
};

const pfSimpleReturns = (arr) => {
    const out = [];
    for (let i = 1; i < arr.length; i++) out.push(arr[i] / arr[i - 1] - 1);
    return out;
};

const pfMean = (a) => a.reduce((x, y) => x + y, 0) / (a.length || 1);

const pfStd = (a) => {
    if (a.length < 2) return 0;
    const m = pfMean(a);
    return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1));
};

const pfCov = (cols) => {
    const n = cols.length;
    const means = cols.map(pfMean);
    const T = cols[0].length;
    const S = Array.from({ length: n }, () => new Array(n).fill(0));
    for (let i = 0; i < n; i++) {
        for (let j = i; j < n; j++) {
            let s = 0;
            for (let t = 0; t < T; t++) s += (cols[i][t] - means[i]) * (cols[j][t] - means[j]);
            const v = s / Math.max(T - 1, 1);
            S[i][j] = v; S[j][i] = v;
        }
    }
    return S;
};

const pfMatVec = (S, w) => S.map((row) => row.reduce((s, v, j) => s + v * w[j], 0));
const pfDot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
const pfQuantile = (sorted, p) => {
    if (!sorted.length) return 0;
    const i = (sorted.length - 1) * p;
    const lo = Math.floor(i), hi = Math.ceil(i);
    return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
};

// Assets that move together are one bet wearing several names. Single-link
// union-find over a correlation threshold, same as the Python side.
const pfClusters = (names, corr, thr = 0.6) => {
    const parent = names.map((_, i) => i);
    const find = (a) => { while (parent[a] !== a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; };
    const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent[rb] = ra; };
    for (let i = 0; i < names.length; i++) {
        for (let j = i + 1; j < names.length; j++) if (corr[i][j] >= thr) union(i, j);
    }
    const groups = new Map();
    names.forEach((_, i) => {
        const r = find(i);
        if (!groups.has(r)) groups.set(r, []);
        groups.get(r).push(i);
    });
    return [...groups.values()].filter((g) => g.length > 1);
};

// --- HRP (Hierarchical Risk Parity) ------------------------------------------
// López de Prado's method, and the reason it fits here: it never asks what an
// asset will return. Mean-variance optimisation needs expected returns, those
// guesses are usually wrong, and being wrong there moves the answer a lot. HRP
// uses only the covariance -- so the suggestion is "spread the risk more
// evenly", never "this will go up".

// Distance that turns correlation into a metric: identical series are 0 apart,
// perfectly opposed ones are 1.
const pfCorrDist = (corr) => corr.map((row) => row.map((c) =>
    Math.sqrt(Math.max(0, 0.5 * (1 - Math.min(Math.max(c, -1), 1))))));

// Single-linkage agglomerative clustering, returning the merge order.
const pfLinkage = (dist) => {
    const n = dist.length;
    const active = new Map();
    for (let i = 0; i < n; i++) active.set(i, [i]);
    const d = dist.map((r) => r.slice());
    const merges = [];
    let nextId = n;

    while (active.size > 1) {
        let best = Infinity, bi = -1, bj = -1;
        const ids = [...active.keys()];
        for (let a = 0; a < ids.length; a++) {
            for (let b = a + 1; b < ids.length; b++) {
                const i = ids[a], j = ids[b];
                let m = Infinity;
                for (const x of active.get(i)) for (const y of active.get(j)) m = Math.min(m, d[x][y]);
                if (m < best) { best = m; bi = i; bj = j; }
            }
        }
        const merged = [...active.get(bi), ...active.get(bj)];
        merges.push([bi, bj, nextId]);
        active.delete(bi); active.delete(bj);
        active.set(nextId++, merged);
    }
    return { merges, order: [...active.values()][0] || [] };
};

const pfIvp = (cov, idx) => {
    // Inverse-variance weights inside a cluster.
    const inv = idx.map((i) => (cov[i][i] > 0 ? 1 / cov[i][i] : 0));
    const s = inv.reduce((a, b) => a + b, 0);
    return s > 0 ? inv.map((v) => v / s) : idx.map(() => 1 / idx.length);
};

const pfClusterVar = (cov, idx) => {
    const w = pfIvp(cov, idx);
    let v = 0;
    for (let a = 0; a < idx.length; a++) {
        for (let b = 0; b < idx.length; b++) v += w[a] * cov[idx[a]][idx[b]] * w[b];
    }
    return v;
};

// Recursive bisection: split the ordered list, then give the safer half more.
const pfHrp = (cov, order) => {
    const w = new Array(cov.length).fill(0);
    order.forEach((i) => { w[i] = 1; });
    const stack = [order];
    while (stack.length) {
        const grp = stack.pop();
        if (grp.length <= 1) continue;
        const half = Math.floor(grp.length / 2);
        const left = grp.slice(0, half), right = grp.slice(half);
        const vl = pfClusterVar(cov, left), vr = pfClusterVar(cov, right);
        const alpha = (vl + vr) > 0 ? 1 - vl / (vl + vr) : 0.5;
        left.forEach((i) => { w[i] *= alpha; });
        right.forEach((i) => { w[i] *= (1 - alpha); });
        stack.push(left, right);
    }
    const s = w.reduce((a, b) => a + b, 0);
    return s > 0 ? w.map((x) => x / s) : w;
};

const pfCompute = async (pf, onProgress) => {
    const rows = pf.positions.filter((p) => pfValueOf(p) !== null && pfValueOf(p) !== 0);
    if (rows.length < 2) throw new Error('종목이 2개 이상이어야 계산할 수 있습니다.');

    // Cash in the base currency has no price series of its own; it is the
    // thing everything else is measured against.
    const needed = new Set();
    for (const p of rows) {
        const it = pfInstOf(p);
        p._sym = it.yahoo || null;
        p._cur = it.currency || 'KRW';
        p._lev = Number(it.leverage_factor) || 1;
        p._name = it.name_ko || p.id;
        if (p._sym) needed.add(p._sym);
        const fx = pfFxSymbol(p._cur);
        if (fx && p._sym !== fx) needed.add(fx);
    }

    let done = 0;
    const fetched = {};
    for (const sym of needed) {
        onProgress && onProgress(`가격 받는 중… ${++done}/${needed.size}`);
        fetched[sym] = await pfFetchHistory(sym);
    }

    const series = {};
    for (const [sym, j] of Object.entries(fetched)) series[sym] = j.points;
    const { dates, cols } = pfAlign(series);
    if (dates.length < 60) throw new Error('공통 거래일이 60일 미만이라 계산이 불안정합니다.');

    // Each holding becomes one KRW-denominated return series.
    const names = [], weights = [], meta = [];
    const retCols = [];
    const total = rows.reduce((a, p) => a + Math.abs(pfValueOf(p)), 0);

    for (const p of rows) {
        const signed = (p.side === 'short' ? -1 : 1) * Math.abs(pfValueOf(p));
        const fxSym = pfFxSymbol(p._cur);

        let krwPath;
        if (!p._sym) {
            // Base-currency cash: flat in KRW terms.
            krwPath = dates.map(() => 1);
        } else if (p._sym === fxSym) {
            krwPath = cols[p._sym];                        // holding the currency itself
        } else if (fxSym) {
            krwPath = cols[p._sym].map((v, i) => v * cols[fxSym][i]);
        } else {
            krwPath = cols[p._sym];
        }

        let r = pfSimpleReturns(krwPath);
        // A daily-rebalanced 2x fund doubles the SIMPLE return each day. Doubling
        // log returns instead squares the price path and quietly drops volatility
        // decay -- the exact bug found in the Python engine (returns.py:158).
        if (p._lev !== 1) r = r.map((x) => p._lev * x);

        names.push(p._name);
        weights.push(signed / total);
        retCols.push(r);
        meta.push({ name: p._name, currency: p._cur, side: p.side, lev: p._lev,
                    signed, weight: signed / total });
    }

    const T = Math.min(...retCols.map((c) => c.length));
    const cut = retCols.map((c) => c.slice(c.length - T));

    const logCols = cut.map((c) => c.map((x) => Math.log1p(Math.max(x, -0.999999))));
    const S = pfCov(logCols);
    const portVar = pfDot(weights, pfMatVec(S, weights));
    const dailyVol = Math.sqrt(Math.max(portVar, 0));
    const annVol = dailyVol * Math.sqrt(PF_TRADING_DAYS);

    const mrc = pfMatVec(S, weights);
    const rc = portVar > 0 ? weights.map((w, i) => w * mrc[i] / portVar) : weights.map(() => 0);

    // Portfolio return is a weighted sum of simple returns; compounding that
    // daily series is what an actual account does.
    const portR = [];
    for (let t = 0; t < T; t++) portR.push(weights.reduce((s, w, i) => s + w * cut[i][t], 0));

    const sorted = [...portR].sort((a, b) => a - b);
    const var1d = -pfQuantile(sorted, 0.05);
    const cvar1d = -pfMean(sorted.slice(0, Math.max(1, Math.floor(sorted.length * 0.05))));
    const var10d = PF_Z95 * dailyVol * Math.sqrt(10);

    const window = Math.min(PF_TRADING_DAYS, portR.length);
    const ret1y = portR.slice(-window).reduce((a, x) => a * (1 + x), 1) - 1;
    const annRet = window >= PF_TRADING_DAYS ? ret1y
        : Math.pow(1 + ret1y, PF_TRADING_DAYS / window) - 1;
    const sharpe = annVol > 0 ? (annRet - PF_RF_ANNUAL) / annVol : null;

    const sd = logCols.map(pfStd);
    const corr = S.map((row, i) => row.map((v, j) =>
        (sd[i] > 0 && sd[j] > 0) ? v / (sd[i] * sd[j]) : 0));

    const krwWeight = meta.filter((m) => m.currency === 'KRW')
        .reduce((a, m) => a + Math.abs(m.weight), 0);

    // HRP is defined over long-only weights, so shorts are compared on the size
    // of the bet rather than its direction, and the suggestion is read back as
    // "carry more/less of this" rather than "flip it".
    let target = null, deltas = null;
    try {
        // Cash has no variance, so inverse-variance weighting is undefined for
        // it -- and worse than undefined: a zero-variance cluster drives the
        // bisection's alpha to 0 and zeroes out whatever sits opposite it. How
        // much cash to hold is a policy question anyway, not something a
        // covariance matrix can answer, so it keeps its weight and HRP runs on
        // the risky sleeve alone.
        const risky = [], riskless = [];
        for (let i = 0; i < names.length; i++) {
            (S[i][i] > 1e-12 ? risky : riskless).push(i);
        }
        const gross = weights.reduce((a, w) => a + Math.abs(w), 0) || 1;
        const heldRiskless = riskless.reduce((a, i) => a + Math.abs(weights[i]), 0);
        const sleeve = gross - heldRiskless;

        if (risky.length >= 2 && sleeve > 0) {
            const subCorr = risky.map((i) => risky.map((j) => corr[i][j]));
            const subCov = risky.map((i) => risky.map((j) => S[i][j]));
            const { order } = pfLinkage(pfCorrDist(subCorr));
            const hrp = pfHrp(subCov, order);

            target = new Array(names.length).fill(0);
            riskless.forEach((i) => { target[i] = Math.abs(weights[i]); });
            risky.forEach((idx, k) => { target[idx] = hrp[k] * sleeve; });

            deltas = names.map((n, i) => ({
                name: n,
                delta: target[i] - Math.abs(weights[i]),
                from: Math.abs(weights[i]),
                to: target[i],
                riskless: riskless.includes(i),
            })).sort((a, b) => b.delta - a.delta);
        }
    } catch (_) { /* suggestion is optional; the diagnosis is not */ }

    return {
        names, weights, rc, meta, corr, total, target, deltas,
        obs: T,
        start: new Date(dates[dates.length - T] * 86400000).toISOString().slice(0, 10),
        end: new Date(dates[dates.length - 1] * 86400000).toISOString().slice(0, 10),
        annVol, annRet, sharpe,
        var1d, cvar1d, var10d,
        var10dKrw: var10d * total,
        krwWeight, foreignWeight: 1 - krwWeight,
        clusters: pfClusters(names, corr).map((g) => ({
            members: g.map((i) => names[i]),
            weight: g.reduce((a, i) => a + Math.abs(weights[i]), 0),
        })),
    };
};

// Alias match, not fuzzy search: the registry carries hand-written Korean
// aliases ("삼전", "하이닉스") precisely so a substring test is enough. These
// entries come first in the picker because only they carry the things the
// registry knows and a ticker lookup cannot -- leverage factors, proxy flags,
// and which instrument stands in for a Korean name.
const pfSearchLocal = (q) => {
    const s = (q || '').trim().toLowerCase();
    if (!s) return [];
    return PF_REGISTRY.filter((it) =>
        (it.name_ko || '').toLowerCase().includes(s) ||
        (it.id || '').toLowerCase().includes(s) ||
        (it.aliases || []).some((a) => String(a).toLowerCase().includes(s))
    ).slice(0, 6);
};

// Anything the registry does not know, looked up by ticker or company name.
const pfSearchRemote = async (q) => {
    try {
        const res = await fetch(`/api/quote/search?q=${encodeURIComponent(q)}`);
        if (!res.ok) return { quotes: [], degraded: true };
        const j = await res.json();
        return { quotes: j.quotes || [], degraded: !!j.degraded };
    } catch (_) {
        return { quotes: [], degraded: true };
    }
};

// A remote hit becomes a registry-shaped record so the rest of the panel does
// not need to care where a holding came from.
const pfFromQuote = (qt) => ({
    id: `yf:${qt.symbol}`,
    name_ko: qt.name || qt.symbol,
    yahoo: qt.symbol,
    currency: qt.currency || null,     // resolved on first price fetch
    asset_class: (qt.type || '').toLowerCase() === 'etf' ? 'etf' : 'equity',
    aliases: [qt.symbol],
    leveraged: false,
    _remote: true,
    _exchange: qt.exchange || '',
});

const PF_CLASS_KO = { cash: '현금', equity: '주식', etf: 'ETF', bond: '채권', commodity: '원자재', fx: '환율' };

// A holding carries its own instrument record once added, because a ticker
// found through search is not in the registry and would otherwise be
// unresolvable on the next page load.
const pfInstOf = (p) => p.inst || PF_REGISTRY.find((x) => x.id === p.id) || { name_ko: p.id };

// Adding a holding re-renders the whole form, so the unit toggle has to live
// outside it. Kept local once, it silently reverted to 금액 after every add and
// the next "5" meant five won instead of five shares.
let pfMode = 'value';

// Weight says where the money sits; risk contribution says where the account's
// movement comes from. Same pairing as the reference panel -- it is the one
// view that shows a small position driving most of the swings.
const pfRenderResult = (host, R, profile) => {
    const rows = R.names
        .map((n, i) => ({ n, rc: R.rc[i], w: R.weights[i], m: R.meta[i] }))
        .sort((a, b) => b.rc - a.rc);
    const max = Math.max(...rows.map((r) => Math.abs(r.rc)), 0.0001);

    const top = rows[0];
    const breaches = [];
    if (profile) {
        if (R.var10d > profile.var_10d_budget) {
            breaches.push(`10일 VaR ${finPct(R.var10d)}가 성향 한도 ${finPct(profile.var_10d_budget)}를 넘습니다.`);
        }
        const peak = rows.reduce((a, b) => Math.abs(b.w) > Math.abs(a.w) ? b : a, rows[0]);
        if (Math.abs(peak.w) > profile.single_name_max) {
            breaches.push(`'${peak.n}' 비중 ${finPct(Math.abs(peak.w))}가 단일종목 한도 ${finPct(profile.single_name_max)}를 넘습니다.`);
        }
        const lev = rows.filter((r) => r.m.lev !== 1).reduce((a, r) => a + Math.abs(r.w), 0);
        if (lev > profile.leveraged_max) {
            breaches.push(`레버리지 비중 ${finPct(lev)}가 한도 ${finPct(profile.leveraged_max)}를 넘습니다.`);
        }
    }

    host.innerHTML = `
        <div class="fin-head fin-head-sub">
            <p class="fin-headline">
                전체 변동의 약 ${finPct(Math.abs(top.rc))}가 '${finEsc(top.n)}'에서 나옵니다
                (비중은 ${finPct(Math.abs(top.w))}).
            </p>
            <div class="fin-meta">
                <span class="fin-chip">${finEsc(profile ? profile.label_ko : '')}</span>
                <span>관측 ${R.obs}일 (${finEsc(R.start)} ~ ${finEsc(R.end)})</span>
                <span class="fin-meta-sep">·</span>
                <span>평가액 ${pfKrw(R.total)}</span>
            </div>
        </div>

        ${breaches.length ? `
        <div class="fin-alert">
            <span class="fin-alert-mark">성향 한도 초과</span>
            <ul>${breaches.map((b) => `<li>${finEsc(b)}</li>`).join('')}</ul>
        </div>` : ''}

        <div class="fin-cards">
            <div class="fin-card">
                <span class="fin-card-title">변동성 (연환산)</span>
                <span class="fin-card-value">${finPct(R.annVol)}</span>
                <p class="fin-card-plain">한 해 기준으로 포트폴리오 가치가 대략 ±${finPct(R.annVol)} 범위에서 움직일 수 있다는 뜻입니다.</p>
            </div>
            <div class="fin-card">
                <span class="fin-card-title">10일 VaR (95%)</span>
                <span class="fin-card-value">${finPct(R.var10d)} · ${pfKrw(R.var10dKrw)}</span>
                <p class="fin-card-plain">최근과 비슷한 장세라면 앞으로 약 2주 동안 이 정도까지 손실이 날 수 있다고 보는 눈금입니다.</p>
            </div>
            <div class="fin-card">
                <span class="fin-card-title">샤프 비율</span>
                <span class="fin-card-value">${R.sharpe === null ? '—' : R.sharpe.toFixed(2)}</span>
                <p class="fin-card-plain">예금·국채 수준을 웃돈 수익을 변동성으로 나눈 값입니다. 과거 성적이지 앞으로의 보장은 아닙니다.</p>
            </div>
            <div class="fin-card">
                <span class="fin-card-title">최근 1년 수익률</span>
                <span class="fin-card-value">${finPct(R.annRet)}</span>
                <p class="fin-card-plain">지금 비중을 그대로 유지했다고 가정한 값입니다. 실제 매매 내역은 반영하지 않습니다.</p>
            </div>
        </div>

        <div class="fin-grid">
            <section class="fin-block fin-block-wide">
                <h2>위험이 어디서 나오는가</h2>
                <p class="fin-lead">비중은 어디에 돈을 넣었는지, 위험 기여는 계좌 변동에 실제로 얼마나 영향을 주는지입니다. 둘은 자주 다릅니다.</p>
                <div class="fin-legend">
                    <span><i class="fin-swatch fin-bar-risk"></i>위험 기여</span>
                    <span><i class="fin-swatch fin-bar-weight"></i>비중</span>
                </div>
                <div class="fin-risk-list">
                    ${rows.map((r) => `
                        <div class="fin-risk-row">
                            <div class="fin-risk-name">
                                ${finEsc(r.n)}
                                ${r.m.lev !== 1 ? '<span class="fin-tag fin-tag-warn">레버리지</span>' : ''}
                                ${r.m.side === 'short' ? '<span class="fin-tag fin-tag-warn">공매도</span>' : ''}
                            </div>
                            <div class="fin-risk-bars">
                                <div class="fin-bar-track"><div class="fin-bar fin-bar-risk"
                                     style="width:${Math.abs(r.rc) / max * 100}%"></div></div>
                                <div class="fin-bar-track"><div class="fin-bar fin-bar-weight"
                                     style="width:${Math.abs(r.w) / max * 100}%"></div></div>
                            </div>
                            <div class="fin-risk-nums">
                                <span class="fin-risk-rc">${finPct(r.rc)}</span>
                                <span class="fin-risk-w">${finPct(r.w)}</span>
                            </div>
                        </div>`).join('')}
                </div>
            </section>

            <section class="fin-block">
                <h2>통화 노출</h2>
                <p class="fin-p">원화에 묶인 비중 약 ${finPct(R.krwWeight)}, 외화 쪽 약 ${finPct(R.foreignWeight)}입니다.
                   달러 현금도 안전자산처럼 보여도 환율만큼은 흔들립니다.</p>
            </section>

            <section class="fin-block">
                <h2>함께 움직이는 묶음</h2>
                ${R.clusters.length
                    ? R.clusters.map((c) => `<p class="fin-p">'${finEsc(c.members.join(', '))}'이(가) 함께 움직이는 편이라,
                        종목 수와 달리 사실상 한 덩어리 위험(합 비중 약 ${finPct(c.weight)})일 수 있습니다.</p>`).join('')
                    : '<p class="fin-p">상관 0.6 이상으로 묶이는 무리는 없습니다.</p>'}
            </section>
        </div>

        ${R.deltas ? (() => {
            const up = R.deltas.filter((d) => d.delta > 0.005).slice(0, 4);
            const down = R.deltas.filter((d) => d.delta < -0.005).reverse().slice(0, 4);
            if (!up.length && !down.length) return '';
            return `
        <section class="fin-block fin-block-wide">
            <h2>조절 제안</h2>
            <p class="fin-note">
                미래 수익 예상이 아니라, <strong>위험을 더 고르게 나누는 방향</strong>입니다.
                기대수익을 가정하지 않는 방식(HRP)이라 "무엇이 오를지"는 말하지 않습니다.
                비중을 옮길 때는 수수료·세금·환전 비용이 있으니, 제안치를 한 번에 맞추기보다 큰 쏠림부터 줄이는 편이 현실적입니다.
            </p>
            <div class="fin-moves">
                <div class="fin-moves-col">
                    <h3 class="fin-sub fin-sub-up">비중을 키우는 방향</h3>
                    ${up.length ? up.map((d) => `
                        <div class="fin-move">
                            <div class="fin-move-head">
                                <span>${finEsc(d.name)}</span>
                                <span class="fin-move-delta fin-up">${finSignedPct(d.delta)}</span>
                            </div>
                            <p>위험이 한곳에 몰리는 걸 줄이려면 ${finPct(d.from)} → ${finPct(d.to)} 방향입니다.</p>
                        </div>`).join('') : '<p class="fin-p">키울 쪽은 뚜렷하지 않습니다.</p>'}
                </div>
                <div class="fin-moves-col">
                    <h3 class="fin-sub fin-sub-down">비중을 줄이는 방향</h3>
                    ${down.length ? down.map((d) => `
                        <div class="fin-move">
                            <div class="fin-move-head">
                                <span>${finEsc(d.name)}</span>
                                <span class="fin-move-delta fin-down">${finSignedPct(d.delta)}</span>
                            </div>
                            <p>변동이 여기에 몰려 있어 ${finPct(d.from)} → ${finPct(d.to)} 로 줄이면 분산에 도움이 됩니다.</p>
                        </div>`).join('') : '<p class="fin-p">줄일 쪽은 뚜렷하지 않습니다.</p>'}
                </div>
            </div>
        </section>`;
        })() : ''}

        <div class="fin-foot">
            <p>이 화면의 숫자는 과거 가격으로 돌린 계산 결과입니다. 매수·매도 지시가 아니며, '위험이 어디에 몰렸는지'를 보는 데 초점이 있습니다.</p>
            <p class="fin-disclaimer">투자 판단의 책임은 본인에게 있습니다. 과거 성과는 미래를 보장하지 않습니다.</p>
            <p class="fin-engine">계산: 브라우저에서 수행 · 가격 출처 Yahoo Finance ·
               ${R.obs}일 일간 종가(수정주가) 기준 · 무위험수익률 ${finPct(PF_RF_ANNUAL)} 가정</p>
        </div>`;
};

const renderPfInput = (root, onDone) => {
    const pf = pfLoad() || pfBlank();
    const total = pf.positions.reduce((a, p) => a + Math.abs(pfValueOf(p) || 0), 0);

    root.innerHTML = `
        <section class="fin-block fin-block-wide pf-input">
            <h2>투자 성향</h2>
            <p class="fin-note">성향은 한도 판정에만 씁니다. 목표 수익률은 받지 않습니다 — 기대수익 가정이 틀리기 쉬워서입니다.</p>
            <div class="pf-profiles">
                ${Object.entries(PF_PROFILES).map(([id, p]) => `
                    <label class="pf-profile ${pf.risk_profile === id ? 'on' : ''}">
                        <input type="radio" name="pf-profile" value="${finEsc(id)}" ${pf.risk_profile === id ? 'checked' : ''}>
                        <span class="pf-profile-label">${finEsc(p.label_ko)}</span>
                        <span class="pf-profile-blurb">${finEsc(p.blurb_ko)}</span>
                    </label>`).join('')}
            </div>
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>종목 추가</h2>
            <div class="pf-add">
                <div class="pf-search-wrap">
                    <input type="text" id="pf-q" class="pf-field" autocomplete="off"
                           placeholder="종목명·티커로 검색 (예: 삼전, 엔비디아, 달러)">
                    <div id="pf-sug" class="pf-sug hidden"></div>
                </div>
                <div class="pf-mode" role="group" aria-label="입력 단위">
                    <button type="button" class="pf-mode-btn ${pfMode === 'value' ? 'on' : ''}" data-mode="value">금액</button>
                    <button type="button" class="pf-mode-btn ${pfMode === 'shares' ? 'on' : ''}" data-mode="shares">주수</button>
                </div>
                <input type="text" id="pf-amt" class="pf-field pf-amt" inputmode="numeric"
                       placeholder="${pfMode === 'shares' ? '보유 주수' : '평가금액 (원)'}">
                <select id="pf-side" class="pf-field pf-side">
                    <option value="long">매수</option>
                    <option value="short">공매도</option>
                </select>
                <button id="pf-add" class="pf-btn" disabled>추가</button>
            </div>
            <p id="pf-picked" class="pf-picked"></p>
            <p class="fin-note">
                등록된 종목만 넣을 수 있습니다 (${PF_REGISTRY.length}종). 없는 종목은 엔진 쪽 종목표에 추가해야 합니다.
                최대 ${PF_MAX}종까지 — 종목이 더 늘면 과거 가격만으로는 종목 간 관계를 안정적으로 못 잡습니다.
            </p>
            ${pf.positions.length >= PF_MAX
                ? `<p class="pf-limit">${PF_MAX}종을 채웠습니다. 더 넣으려면 기존 종목을 지워 주세요.</p>` : ''}
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>보유 목록 <span class="pf-count">${pf.positions.length}건</span></h2>
            ${pf.positions.length ? `
            <div class="pf-rows">
                ${pf.positions.map((p, i) => {
                    const it = pfInstOf(p);
                    const val = pfValueOf(p);
                    const w = (total && val !== null) ? Math.abs(val) / total : 0;
                    return `
                    <div class="pf-row">
                        <span class="pf-row-name">
                            ${finEsc(it.name_ko || p.id)}
                            <span class="fin-tag">${finEsc(PF_CLASS_KO[it.asset_class] || it.asset_class || '')}</span>
                            ${it.leveraged ? '<span class="fin-tag fin-tag-warn">레버리지</span>' : ''}
                            ${it.proxy || it.synthetic_leverage ? '<span class="fin-tag">프록시</span>' : ''}
                            ${p.side === 'short' ? '<span class="fin-tag fin-tag-warn">공매도</span>' : ''}
                            ${p.mode === 'shares'
                                ? `<span class="pf-row-sub">${p.shares.toLocaleString('ko-KR')}주 ·
                                   ${pfKrw(p.price * (p.fx || 1))} 기준 (${finEsc(p.pricedAt || '')})</span>`
                                : ''}
                        </span>
                        <span class="pf-row-val">${pfKrw(val)}</span>
                        <span class="pf-row-w">${(w * 100).toFixed(1)}%</span>
                        <button class="pf-del" data-i="${i}" aria-label="삭제">✕</button>
                    </div>`;
                }).join('')}
            </div>
            <div class="pf-total"><span>합계</span><strong>${pfKrw(total)}</strong></div>
            <div class="pf-actions">
                <button id="pf-run" class="pf-btn pf-btn-primary">계산하기</button>
                <button id="pf-clear" class="pf-btn pf-btn-ghost">전부 지우기</button>
            </div>
            <p class="fin-note pf-privacy">
                입력한 내역은 이 브라우저에만 저장됩니다. 서버로 보내지 않습니다.
                가격 조회만 서버를 거치며, 종목은 지나가되 금액은 지나가지 않습니다.
            </p>
            ` : `<p class="fin-note">아직 없습니다. 위에서 종목을 추가하세요.</p>`}
        </section>`;

    const qEl = root.querySelector('#pf-q');
    const sugEl = root.querySelector('#pf-sug');
    const amtEl = root.querySelector('#pf-amt');
    const addEl = root.querySelector('#pf-add');
    const pickedEl = root.querySelector('#pf-picked');
    let picked = null;
    let spot = null;          // { price, fx, currency } for the picked instrument
    let mode = pfMode;

    const numOf = () => Number(String(amtEl.value).replace(/[^0-9.]/g, ''));

    const refreshAdd = () => {
        const full = (pfLoad() || pfBlank()).positions.length >= PF_MAX;
        const ready = mode === 'shares' ? (spot && spot.price > 0) : true;
        addEl.disabled = full || !picked || !(numOf() > 0) || !ready;
    };

    // In share mode the amount is unknown until a price arrives, so show the
    // arithmetic rather than a number that appeared from nowhere.
    const curOf = () => picked && (picked.currency || (spot && spot.currency) || '');

    const showPicked = () => {
        if (!picked) { pickedEl.textContent = ''; pickedEl.className = 'pf-picked'; return; }
        const cur = curOf();
        const label = `선택: ${picked.name_ko}${cur ? ` (${cur})` : ''}`;
        pickedEl.className = 'pf-picked';
        if (!spot && (mode === 'shares' || picked._remote)) {
            pickedEl.textContent = `${label} · 조회 중…`;
            return;
        }
        if (spot && !(spot.price > 0)) {
            pickedEl.textContent = `${label} · 가격을 못 받았습니다 — 다른 종목을 골라 주세요`;
            pickedEl.className = 'pf-picked pf-picked-warn';
            return;
        }
        if (mode !== 'shares') { pickedEl.textContent = label; return; }
        const n = numOf();
        const unit = spot.price * (spot.fx || 1);
        pickedEl.textContent = n > 0
            ? `${label} · 현재가 ${pfKrw(unit)} × ${n.toLocaleString('ko-KR')}주 = ${pfKrw(unit * n)}`
            : `${label} · 현재가 ${pfKrw(unit)}`;
    };

    // A ticker found through search arrives without a currency, and the whole
    // portfolio is measured in KRW -- so the price call runs even in 금액 mode,
    // where its only job is to tell us what currency the thing trades in.
    const loadSpot = async () => {
        if (!picked) return;
        if (mode !== 'shares' && !picked._remote) return;
        spot = null; showPicked(); refreshAdd();
        try {
            spot = await pfSpot(picked.yahoo || null, picked.currency);
            if (spot && spot.currency && !picked.currency) picked.currency = spot.currency;
        } catch (_) {
            spot = { price: 0, fx: 1, currency: picked.currency };
        }
        showPicked(); refreshAdd();
    };

    root.querySelectorAll('.pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        mode = pfMode = b.dataset.mode;
        root.querySelectorAll('.pf-mode-btn').forEach((x) => x.classList.toggle('on', x.dataset.mode === mode));
        amtEl.placeholder = mode === 'shares' ? '보유 주수' : '평가금액 (원)';
        amtEl.value = '';
        loadSpot();
        showPicked();
        refreshAdd();
    }));

    // Remote results are keyed by index into this array; registry hits keep
    // their own id so the two can share one click handler.
    let shown = [];
    let searchSeq = 0;
    let searchTimer = null;

    const paintSuggestions = (hits, note) => {
        shown = hits;
        if (!hits.length) {
            sugEl.innerHTML = note ? `<p class="pf-sug-note">${finEsc(note)}</p>` : '';
            sugEl.classList.toggle('hidden', !note);
            return;
        }
        sugEl.innerHTML = hits.map((h, i) => `
            <button class="pf-sug-item" data-i="${i}">
                <span>${finEsc(h.name_ko)}</span>
                <span class="pf-sug-meta">${finEsc(
                    h._remote ? `${h.yahoo}${h._exchange ? ' · ' + h._exchange : ''}`
                              : `${PF_CLASS_KO[h.asset_class] || ''} · ${h.currency}`)}</span>
            </button>`).join('') + (note ? `<p class="pf-sug-note">${finEsc(note)}</p>` : '');
        sugEl.classList.remove('hidden');
    };

    qEl.addEventListener('input', () => {
        picked = null; spot = null; pickedEl.textContent = ''; refreshAdd();
        const q = qEl.value.trim();
        clearTimeout(searchTimer);
        if (q.length < 1) { sugEl.classList.add('hidden'); return; }

        const local = pfSearchLocal(q);
        paintSuggestions(local, local.length ? '' : '찾는 중…');

        // The registry answers instantly; the network lookup is debounced so a
        // burst of keystrokes does not fire a request each.
        const seq = ++searchSeq;
        searchTimer = setTimeout(async () => {
            const { quotes, degraded } = await pfSearchRemote(q);
            if (seq !== searchSeq) return;             // a later keystroke won
            const ids = new Set(local.map((x) => (x.yahoo || '').toUpperCase()));
            const remote = quotes
                .filter((qt) => !ids.has(String(qt.symbol).toUpperCase()))
                .map(pfFromQuote);
            const all = [...local, ...remote];
            paintSuggestions(all, all.length
                ? (degraded ? '검색이 제한돼 미국 상장사만 나옵니다' : '')
                : '검색 결과가 없습니다. 티커를 직접 넣어 보세요.');
        }, 250);
    });

    sugEl.addEventListener('click', (e) => {
        const b = e.target.closest('.pf-sug-item');
        if (!b) return;
        picked = shown[Number(b.dataset.i)] || null;
        qEl.value = picked ? picked.name_ko : '';
        sugEl.classList.add('hidden');
        showPicked();
        loadSpot();
        amtEl.focus();
        refreshAdd();
    });

    // Thousands separators while typing; the raw number is parsed back on add.
    amtEl.addEventListener('input', () => {
        const raw = String(amtEl.value).replace(/[^0-9]/g, '');
        amtEl.value = raw ? Number(raw).toLocaleString('ko-KR') : '';
        showPicked();
        refreshAdd();
    });

    addEl.addEventListener('click', () => {
        const n = numOf();
        if (!picked || !(n > 0)) return;
        const side = root.querySelector('#pf-side').value;
        const next = pfLoad() || pfBlank();
        next.risk_profile = root.querySelector('input[name="pf-profile"]:checked')?.value || next.risk_profile;

        const same = (p) => p.id === picked.id && p.side === side && (p.mode || 'value') === mode;
        const existing = next.positions.findIndex(same);
        // Carry the instrument with the holding: a searched ticker is not in the
        // registry, so nothing could resolve it on the next page load.
        const inst = {
            name_ko: picked.name_ko,
            yahoo: picked.yahoo || null,
            currency: picked.currency || (spot && spot.currency) || 'KRW',
            asset_class: picked.asset_class || 'equity',
            leveraged: !!picked.leveraged,
            leverage_factor: picked.synthetic_leverage ? (picked.leverage_factor || 2) : 1,
            proxy: !!(picked.proxy || picked.synthetic_leverage),
        };
        const row = mode === 'shares'
            ? { id: picked.id, side, mode: 'shares', shares: n, inst,
                price: spot.price, fx: spot.fx, pricedAt: new Date().toISOString().slice(0, 10) }
            : { id: picked.id, side, mode: 'value', value: n, inst };

        // Topping up something already held is fine at the cap; only new rows count.
        if (existing >= 0) {
            if (mode === 'shares') {
                next.positions[existing].shares += n;
                next.positions[existing].price = spot.price;
                next.positions[existing].fx = spot.fx;
                next.positions[existing].pricedAt = row.pricedAt;
            } else {
                next.positions[existing].value += n;
            }
        } else if (next.positions.length < PF_MAX) {
            next.positions.push(row);
        } else return;

        pfSave(next);
        renderPfInput(root, onDone);
    });

    root.querySelectorAll('.pf-del').forEach((b) => b.addEventListener('click', () => {
        const next = pfLoad() || pfBlank();
        next.positions.splice(Number(b.dataset.i), 1);
        pfSave(next);
        renderPfInput(root, onDone);
    }));

    root.querySelectorAll('input[name="pf-profile"]').forEach((r) => r.addEventListener('change', () => {
        const next = pfLoad() || pfBlank();
        next.risk_profile = r.value;
        pfSave(next);
        renderPfInput(root, onDone);
    }));

    root.querySelector('#pf-clear')?.addEventListener('click', () => {
        if (!confirm('보유 목록을 전부 지웁니다. 되돌릴 수 없습니다.')) return;
        pfSave(pfBlank());
        renderPfInput(root, onDone);
    });

    root.querySelector('#pf-run')?.addEventListener('click', () => onDone && onDone());
};

const renderPfResult = async (host) => {
    host.innerHTML = `<p class="fin-loading">계산 결과 불러오는 중…</p>`;

    let data = null;
    for (const path of ['/public/data/portfolio_analysis_v1.json', '/data/portfolio_analysis_v1.json']) {
        try {
            const res = await fetch(path, { cache: 'no-store' });
            if (res.ok) { data = await res.json(); break; }
        } catch (_) { /* try next */ }
    }

    if (!data) {
        const saved = pfLoad();
        host.innerHTML = `
            <div class="fin-empty">
                <p class="fin-empty-title">아직 계산 결과가 없습니다</p>
                <p>${saved && saved.positions.length
                    ? `보유 ${saved.positions.length}건이 저장돼 있습니다. 계산 기능은 준비 중입니다 —
                       현재는 <code>run_pipeline.py</code> 로 만든 결과 파일만 읽습니다.`
                    : `「내 포트폴리오」 탭에서 보유 종목을 먼저 넣어 주세요.`}</p>
            </div>`;
        return;
    }

    const u = data[`ui_copy_${FIN_LOCALE}`] || {};
    const S = (k) => u[`${k}_${FIN_LOCALE}`];
    const cards = u.metric_cards || [];
    const breaches = S('profile_breaches') || [];
    const movesUp = S('moves_up') || [];
    const movesDown = S('moves_down') || [];
    const proxies = (data.data_quality && data.data_quality.proxies) || [];
    const dq = data.data_quality || {};

    host.innerHTML = `
        <div class="fin-head fin-head-sub">
            <p class="fin-headline">${finEsc(S('headline'))}</p>
            <div class="fin-meta">
                <span class="fin-chip">${finEsc(u.profile?.[`label_${FIN_LOCALE}`] || data.risk_profile_id)}</span>
                <span>${finEsc(u.profile?.[`blurb_${FIN_LOCALE}`] || '')}</span>
                <span class="fin-meta-sep">·</span>
                <span>기준 ${finEsc((data.generated_at || '').slice(0, 10))}</span>
                <span class="fin-meta-sep">·</span>
                <span>관측 ${dq.n_obs ?? '—'}일 (${finEsc(dq.start || '')} ~ ${finEsc(dq.end || '')})</span>
            </div>
        </div>

        ${breaches.length ? `
        <div class="fin-alert">
            <span class="fin-alert-mark">성향 한도 초과</span>
            <ul>${breaches.map((b) => `<li>${finEsc(b)}</li>`).join('')}</ul>
        </div>` : ''}

        <div class="fin-cards">
            ${cards.map((c) => `
                <div class="fin-card">
                    <span class="fin-card-title">${finEsc(c[`title_${FIN_LOCALE}`])}</span>
                    <span class="fin-card-value">${finEsc(c[`value_${FIN_LOCALE}`])}</span>
                    <p class="fin-card-plain">${finEsc(c[`plain_${FIN_LOCALE}`])}</p>
                    <p class="fin-card-analogy">${finEsc(c[`analogy_${FIN_LOCALE}`])}</p>
                </div>`).join('')}
        </div>

        <div class="fin-grid">
            <section class="fin-block fin-block-wide">
                <h2>위험이 어디서 나오는가</h2>
                <p class="fin-lead">${finEsc(S('risk_contribution_plain'))}</p>
                <div class="fin-legend">
                    <span><i class="fin-swatch fin-bar-risk"></i>위험 기여</span>
                    <span><i class="fin-swatch fin-bar-weight"></i>비중</span>
                </div>
                <div class="fin-risk-list">${finRiskRows(data)}</div>
            </section>

            <section class="fin-block">
                <h2>이 숫자 보는 법</h2>
                <ul class="fin-list">
                    ${(S('how_to_read') || []).map((x) => `<li>${finEsc(x)}</li>`).join('')}
                </ul>
            </section>

            <section class="fin-block">
                <h2>함께 움직이는 묶음</h2>
                ${(S('clusters_plain') || []).map((x) => `<p class="fin-p">${finEsc(x)}</p>`).join('')}
                <h3 class="fin-sub">통화 노출</h3>
                <p class="fin-p">${finEsc(S('currency_plain'))}</p>
            </section>

            <section class="fin-block">
                <h2>과거 급락 구간 대입</h2>
                ${(S('stress_plain') || []).map((x) => `<p class="fin-p">${finEsc(x)}</p>`).join('')}
            </section>

            <section class="fin-block fin-block-wide">
                <h2>조절 제안</h2>
                <p class="fin-note">${finEsc(S('rebalance_note'))}</p>
                <div class="fin-moves">
                    <div class="fin-moves-col">
                        <h3 class="fin-sub fin-sub-up">비중을 키우는 방향</h3>
                        ${movesUp.map((m) => `
                            <div class="fin-move">
                                <div class="fin-move-head">
                                    <span>${finEsc(m[`name_${FIN_LOCALE}`])}</span>
                                    <span class="fin-move-delta fin-up">${finSignedPct(m.delta)}</span>
                                </div>
                                <p>${finEsc(m[`plain_${FIN_LOCALE}`])}</p>
                            </div>`).join('')}
                    </div>
                    <div class="fin-moves-col">
                        <h3 class="fin-sub fin-sub-down">비중을 줄이는 방향</h3>
                        ${movesDown.map((m) => `
                            <div class="fin-move">
                                <div class="fin-move-head">
                                    <span>${finEsc(m[`name_${FIN_LOCALE}`])}</span>
                                    <span class="fin-move-delta fin-down">${finSignedPct(m.delta)}</span>
                                </div>
                                <p>${finEsc(m[`plain_${FIN_LOCALE}`])}</p>
                            </div>`).join('')}
                    </div>
                </div>
            </section>
        </div>

        <div class="fin-foot">
            <p>${finEsc(S('footer'))}</p>
            <p class="fin-disclaimer">${finEsc(data[`disclaimer_${FIN_LOCALE}`])}</p>
            ${proxies.length ? `<p class="fin-proxy">프록시 사용: ${proxies.map((p) =>
                finEsc(typeof p === 'string' ? p : (p.name_ko || p.id || JSON.stringify(p)))).join(' · ')}</p>` : ''}
            <p class="fin-engine">엔진: <code>scripts/금융_재무분석</code> ·
               방식: ${finEsc((data.advice && data.advice.method) || '')} ·
               스키마 ${finEsc(data.schema_version || '')}</p>
        </div>`;
};

const renderPortfolioLab = async (host) => {
    host.innerHTML = `<div class="fin-wrap"><p class="fin-loading">불러오는 중…</p></div>`;
    await pfLoadRefs();

    const saved = pfLoad();

    host.innerHTML = `
    <div class="fin-wrap">
        <div class="fin-head">
            <h1>포트폴리오 계산기</h1>
            <p>보유 자산의 위험이 어디에 몰려 있는지 봅니다. 수익 예측이 아닙니다.</p>
        </div>
        <div id="pf-form"></div>
        <div id="pf-out"></div>
    </div>`;

    const form = host.querySelector('#pf-form');
    const out = host.querySelector('#pf-out');

    const run = async () => {
        const pf = pfLoad() || pfBlank();
        out.innerHTML = `<div class="fin-block fin-block-wide"><p class="fin-loading" id="pf-prog">계산 준비 중…</p></div>`;
        out.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const prog = out.querySelector('#pf-prog');
        try {
            const R = await pfCompute(pf, (msg) => { if (prog) prog.textContent = msg; });
            pfRenderResult(out, R, PF_PROFILES[pf.risk_profile]);
        } catch (err) {
            out.innerHTML = `
                <div class="fin-block fin-block-wide">
                    <h2>계산하지 못했습니다</h2>
                    <p class="fin-p">${finEsc(err.message || String(err))}</p>
                    <p class="fin-note">가격 조회가 일시적으로 막혔을 수 있습니다. 잠시 뒤 다시 눌러 보세요.</p>
                </div>`;
        }
    };

    renderPfInput(form, run);

    // A saved portfolio is a standing request to see its numbers.
    if (saved && saved.positions.length >= 2) run();
};

// --- 기업 가치 계산기 ---------------------------------------------------------
// The same statements read at three depths. Named for what each view is for,
// not for who is supposed to be reading it -- a label like "취준생용" tells the
// reader what the site thinks of them rather than what the numbers show.
const CO_LEVELS = [
    { id: 'health',    label: '재무 건전성', blurb: '빚을 감당할 수 있는가, 이익은 나는가' },
    { id: 'valuation', label: '투자 판단',   blurb: '벌어들이는 현금 대비 값이 어떤가' },
    { id: 'deep',      label: '심층 분석',   blurb: '자산과 부채가 실제로 어떤 모양인가' },
];

// Levels stack rather than replace. Moving up a level is a request for more,
// not for something else -- valuation still wants the health numbers in view.
const CO_LEVEL_ORDER = CO_LEVELS.map((l) => l.id);
const coLevelsUpTo = (id) => CO_LEVEL_ORDER.slice(0, CO_LEVEL_ORDER.indexOf(id) + 1);

const coNum = (v, currency = 'KRW') => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const a = Math.abs(v);
    if (currency === 'KRW') {
        if (a >= 1e12) return `${(v / 1e12).toFixed(2)}조원`;
        if (a >= 1e8) return `${(v / 1e8).toFixed(1)}억원`;
        if (a >= 1e4) return `${(v / 1e4).toFixed(0)}만원`;
        return `${Math.round(v).toLocaleString('ko-KR')}원`;
    }
    const sym = currency === 'USD' ? '$' : `${currency} `;
    if (a >= 1e9) return `${sym}${(v / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `${sym}${(v / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `${sym}${(v / 1e3).toFixed(1)}K`;
    return `${sym}${Math.round(v).toLocaleString('en-US')}`;
};

const coRatio = (v, digits = 1) =>
    (v === null || v === undefined || !Number.isFinite(v)) ? '—' : `${v.toFixed(digits)}`;

const coPct = (v, digits = 1) =>
    (v === null || v === undefined || !Number.isFinite(v)) ? '—' : `${(v * 100).toFixed(digits)}%`;

const coDiv = (a, b) => (a === null || b === null || !b) ? null : a / b;

// Ratios follow the same definitions the KFA engine uses, so the two can be
// checked against each other the way the portfolio maths already is.
const coDerive = (s) => {
    const sum = (...xs) => {
        const vals = xs.filter((x) => Number.isFinite(x));
        return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
    };
    const interestBearingShort = sum(s.debt_short, s.debt_current_portion);
    const debtTotal = sum(interestBearingShort, s.debt_long);
    return {
        fy: s.fy,
        current_ratio: coDiv(s.assets_current, s.liabilities_current),
        quick_ratio: coDiv(sum(s.cash, s.securities_current, s.receivables), s.liabilities_current),
        debt_ratio: coDiv(s.liabilities, s.assets),
        equity_ratio: coDiv(s.equity, s.assets),
        roe: coDiv(s.net_income, s.equity),
        roa: coDiv(s.net_income, s.assets),
        operating_margin: coDiv(s.operating_income, s.revenue),
        net_margin: coDiv(s.net_income, s.revenue),
        fcf: (s.cfo === null || s.capex === null) ? null : s.cfo - s.capex,
        fcf_margin: (s.cfo === null || s.capex === null) ? null : coDiv(s.cfo - s.capex, s.revenue),
        // Net debt counts what carries interest, not every payable.
        interest_bearing_short: interestBearingShort,
        debt_total: debtTotal,
        net_debt: (debtTotal === null) ? null : debtTotal - (s.cash ?? 0) - (s.securities_current ?? 0),
        // How much of the interest-bearing debt falls due inside a year.
        short_share: coDiv(interestBearingShort, debtTotal),
        interest_cover: coDiv(s.operating_income, s.interest_expense),
        effective_tax: coDiv(s.tax_expense, sum(s.net_income, s.tax_expense)),
        raw: s,
    };
};

const renderCompanyCalc = async (host) => {
    host.innerHTML = `<div class="fin-wrap"><p class="fin-loading">불러오는 중…</p></div>`;
    await pfLoadRefs();

    host.innerHTML = `
    <div class="fin-wrap">
        <div class="fin-head">
            <h1>기업 가치 계산기</h1>
            <p>공시된 재무제표를 세 단계 깊이로 읽습니다. 투자 의견이 아니라, 그 단계에서 봐야 할 항목입니다.</p>
        </div>
        <section class="fin-block fin-block-wide pf-input">
            <h2>기업 찾기</h2>
            <div class="pf-add">
                <div class="pf-search-wrap">
                    <input type="text" id="co-q" class="pf-field" autocomplete="off"
                           placeholder="기업명·티커로 검색 (예: 애플, AAPL, NVDA)">
                    <div id="co-sug" class="pf-sug hidden"></div>
                </div>
            </div>
            <p id="co-picked" class="pf-picked"></p>
            <p class="fin-note">
                미국 상장사는 SEC 공시로 바로 계산됩니다. <strong>한국 상장사는 DART 키가 연결되면</strong> 같은 화면에서 열립니다.
            </p>
        </section>
        <div id="co-out"></div>
    </div>`;

    const qEl = host.querySelector('#co-q');
    const sugEl = host.querySelector('#co-sug');
    const pickedEl = host.querySelector('#co-picked');
    const out = host.querySelector('#co-out');
    let shown = [], seq = 0, timer = null;

    qEl.addEventListener('input', () => {
        const q = qEl.value.trim();
        clearTimeout(timer);
        if (!q) { sugEl.classList.add('hidden'); return; }
        const local = pfSearchLocal(q).filter((x) => x.asset_class === 'equity');
        shown = local;
        sugEl.innerHTML = local.map((h, i) =>
            `<button class="pf-sug-item" data-i="${i}"><span>${finEsc(h.name_ko)}</span>
             <span class="pf-sug-meta">${finEsc(h.yahoo || '')}</span></button>`).join('') || '<p class="pf-sug-note">찾는 중…</p>';
        sugEl.classList.remove('hidden');

        const my = ++seq;
        timer = setTimeout(async () => {
            const { quotes } = await pfSearchRemote(q);
            if (my !== seq) return;
            const have = new Set(local.map((x) => String(x.yahoo || '').toUpperCase()));
            const remote = quotes
                .filter((c) => (c.type || '').toUpperCase() === 'EQUITY')
                .filter((c) => !have.has(String(c.symbol).toUpperCase()))
                .map(pfFromQuote);
            shown = [...local, ...remote];
            sugEl.innerHTML = shown.map((h, i) =>
                `<button class="pf-sug-item" data-i="${i}"><span>${finEsc(h.name_ko)}</span>
                 <span class="pf-sug-meta">${finEsc(h.yahoo || '')}${h._exchange ? ' · ' + finEsc(h._exchange) : ''}</span></button>`
            ).join('') || '<p class="pf-sug-note">결과가 없습니다. 티커를 직접 넣어 보세요.</p>';
        }, 250);
    });

    sugEl.addEventListener('click', async (e) => {
        const b = e.target.closest('.pf-sug-item');
        if (!b) return;
        const it = shown[Number(b.dataset.i)];
        if (!it) return;
        qEl.value = it.name_ko;
        sugEl.classList.add('hidden');
        pickedEl.textContent = `선택: ${it.name_ko} (${it.yahoo})`;
        await loadCompany(out, it);
    });
};

const loadCompany = async (out, inst) => {
    const sym = String(inst.yahoo || '').toUpperCase();
    out.innerHTML = `<div class="fin-block fin-block-wide"><p class="fin-loading">공시 자료를 받는 중…</p></div>`;

    // A Korean listing carries a market suffix Yahoo uses and SEC does not.
    if (/\.(KS|KQ)$/.test(sym)) {
        out.innerHTML = `
            <div class="fin-empty">
                <p class="fin-empty-title">한국 상장사는 아직 연결되지 않았습니다</p>
                <p>${finEsc(inst.name_ko)}는 DART 공시가 필요합니다. API 키가 연결되면 같은 화면에서 열립니다.<br>
                   지금은 미국 상장사(SEC 공시)만 계산됩니다.</p>
            </div>`;
        return;
    }

    let data;
    try {
        const res = await fetch(`/api/financials?symbol=${encodeURIComponent(sym)}`);
        if (!res.ok) throw new Error(res.status === 502 ? '공시를 찾지 못했습니다' : `조회 실패 (${res.status})`);
        data = await res.json();
    } catch (err) {
        out.innerHTML = `<div class="fin-block fin-block-wide"><h2>불러오지 못했습니다</h2>
            <p class="fin-p">${finEsc(err.message)}</p>
            <p class="fin-note">미국 상장사가 아니거나 공시 형식이 달라 항목을 못 찾은 경우입니다.</p></div>`;
        return;
    }

    const rows = (data.statements || []).map(coDerive);
    if (!rows.length) {
        out.innerHTML = `<div class="fin-block fin-block-wide"><h2>공시 항목을 찾지 못했습니다</h2>
            <p class="fin-note">${finEsc(data.name || sym)}의 연차보고서에서 표준 항목을 읽지 못했습니다.</p></div>`;
        return;
    }

    let level = 'health';
    CO_DCF.growth = null;      // 새 기업이면 그 기업의 이력에서 다시 잡는다
    CO_STRUCT_OPEN = null;
    CO_DATA = data;
    CO_PRICE.value = null;
    CO_PRICE.status = 'loading';
    const paint = () => {
        out.innerHTML = `
        <div class="fin-head fin-head-sub">
            <p class="fin-headline">${finEsc(data.name)} · ${finEsc(data.symbol)}</p>
            <div class="fin-meta">
                <span class="fin-chip">${finEsc(data.source)}</span>
                <span>${rows[rows.length - 1].fy}~${rows[0].fy} 회계연도 · ${finEsc(data.currency)}</span>
            </div>
        </div>
        <div class="pf-mode co-levels" role="tablist">
            ${CO_LEVELS.map((L) => `
                <button type="button" class="pf-mode-btn ${L.id === level ? 'on' : ''}" data-level="${L.id}">
                    ${finEsc(L.label)}
                </button>`).join('')}
        </div>
        <p class="fin-note co-blurb">${finEsc(CO_LEVELS.find((L) => L.id === level).blurb)}</p>
        ${coRenderLevel(level, rows, data)}`;

        out.querySelectorAll('[data-level]').forEach((b) => b.addEventListener('click', () => {
            level = b.dataset.level; paint();
        }));

        out.querySelectorAll('[data-co-struct]').forEach((b) => b.addEventListener('click', () => {
            const k = b.dataset.coStruct;
            CO_STRUCT_OPEN = CO_STRUCT_OPEN === k ? null : k;
            paint();
        }));

        // Recompute on change rather than on every keystroke: a half-typed
        // discount rate briefly reads as 0 and the numbers jump.
        out.querySelectorAll('[data-co-dcf]').forEach((el) => el.addEventListener('change', () => {
            const v = Number(el.value);
            if (Number.isFinite(v)) CO_DCF[el.dataset.coDcf] = v;
            paint();
        }));
        out.querySelector('[data-co-dcf-reset]')?.addEventListener('click', () => {
            CO_DCF.growth = null; CO_DCF.terminal = 2.5; CO_DCF.discount = 9.0;
            paint();
        });
        out.querySelector('[data-co-price]')?.addEventListener('change', (e) => {
            const v = Number(e.target.value);
            CO_PRICE.value = Number.isFinite(v) && v > 0 ? v : null;
            CO_PRICE.status = 'manual';
            paint();
        });
    };
    paint();

    // The reverse DCF needs a price, and the quote proxy already exists for the
    // portfolio panel. Fetched after first paint so the statements are not held
    // up by a second network call.
    pfSpot(sym, data.currency).then((sp) => {
        if (CO_DATA !== data) return;                 // 사용자가 그새 다른 기업을 골랐다
        if (sp && Number.isFinite(sp.price) && sp.price > 0) {
            CO_PRICE.value = sp.price; CO_PRICE.status = 'ok';
        } else {
            CO_PRICE.status = 'fail';
        }
        paint();
    }).catch(() => { CO_PRICE.status = 'fail'; paint(); });
};

const coTable = (rows, cols) => `
    <div class="co-table-wrap">
        <table class="co-table">
            <thead><tr><th>항목</th>${rows.map((r) => `<th>${r.fy}</th>`).join('')}</tr></thead>
            <tbody>
                ${cols.map((c) => `
                    <tr>
                        <td class="co-label">${finEsc(c.label)}${c.hint ? `<span class="co-hint">${finEsc(c.hint)}</span>` : ''}</td>
                        ${rows.map((r) => `<td>${c.fmt(r)}</td>`).join('')}
                    </tr>`).join('')}
            </tbody>
        </table>
    </div>`;

// --- DCF ---------------------------------------------------------------------
// Every number here is a consequence of three inputs the reader chooses. That is
// not a flaw to hide behind a single "fair value" figure -- it is the whole
// point, so the assumptions stay on screen and adjustable.
const CO_DCF = { growth: null, terminal: 2.5, discount: 9.0, years: 5 };
const CO_PRICE = { value: null, status: 'idle' };
let CO_DATA = null;   // 현재 렌더 중인 기업 페이로드 (통화 등)

const coDcf = (rows) => {
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;

    const g = (CO_DCF.growth ?? 0) / 100;
    const tg = CO_DCF.terminal / 100;
    const r = CO_DCF.discount / 100;
    if (!(r > tg)) return { invalid: '할인율이 영구성장률보다 커야 합니다.' };

    const flows = [];
    let f = base;
    for (let i = 1; i <= CO_DCF.years; i++) {
        f = f * (1 + g);
        flows.push({ year: i, fcf: f, pv: f / Math.pow(1 + r, i) });
    }
    const tail = flows[flows.length - 1].fcf * (1 + tg) / (r - tg);
    const tailPv = tail / Math.pow(1 + r, CO_DCF.years);
    const ev = flows.reduce((a, x) => a + x.pv, 0) + tailPv;
    const equity = ev - (latest.net_debt ?? 0);
    const shares = latest.raw.shares;
    return {
        base, flows, tail, tailPv, ev, equity,
        tailShare: tailPv / ev,
        perShare: Number.isFinite(shares) && shares > 0 ? equity / shares : null,
        shares,
    };
};

// Historical FCF growth, as a starting point for the input rather than a
// forecast. Clamped because a single recovery year can imply 300% forever.
const coDefaultGrowth = (rows) => {
    const fcfs = rows.map((r) => r.fcf).filter((x) => Number.isFinite(x) && x > 0);
    if (fcfs.length < 3) return 5;
    const newest = fcfs[0], oldest = fcfs[fcfs.length - 1], n = fcfs.length - 1;
    const cagr = (Math.pow(newest / oldest, 1 / n) - 1) * 100;
    return Math.max(-10, Math.min(20, Math.round(cagr * 10) / 10));
};

// Forward DCF answers "what is it worth if I am right about growth". Reverse
// DCF asks the better question: at today's price, what growth is already being
// assumed? That turns a number the reader must trust into one they can judge.
const coImpliedGrowth = (rows, marketCap) => {
    if (!Number.isFinite(marketCap) || marketCap <= 0) return null;
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;
    const targetEv = marketCap + (latest.net_debt ?? 0);

    const evAt = (g) => {
        const tg = CO_DCF.terminal / 100, r = CO_DCF.discount / 100;
        if (!(r > tg)) return null;
        let f = base, pv = 0;
        for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + g); pv += f / Math.pow(1 + r, i); }
        return pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
    };
    if (evAt(0) === null) return null;

    // EV rises monotonically in g below the discount rate, so bisection is both
    // sufficient and stable here.
    let lo = -0.5, hi = (CO_DCF.discount / 100) - 0.001;
    if (evAt(hi) < targetEv) return { unreachable: true, cap: hi * 100 };
    if (evAt(lo) > targetEv) return { unreachable: true, below: true, cap: lo * 100 };
    for (let k = 0; k < 60; k++) {
        const mid = (lo + hi) / 2;
        if (evAt(mid) < targetEv) lo = mid; else hi = mid;
    }
    return { growth: (lo + hi) / 2 * 100 };
};

const coSensitivity = (rows) => {
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;
    const shares = latest.raw.shares;
    if (!Number.isFinite(shares) || shares <= 0) return null;

    const gs = [-5, 0, 5, 10, 15];
    const rs = [7, 8, 9, 10, 12];
    const tg = CO_DCF.terminal / 100;
    const cells = rs.map((rp) => ({
        r: rp,
        row: gs.map((gp) => {
            const g = gp / 100, r = rp / 100;
            if (!(r > tg)) return null;
            let f = base, pv = 0;
            for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + g); pv += f / Math.pow(1 + r, i); }
            const ev = pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
            return (ev - (latest.net_debt ?? 0)) / shares;
        }),
    }));
    return { gs, cells };
};

const coSensPanel = (rows, CUR) => {
    const sens = coSensitivity(rows);
    if (!sens) return '';
    const flat = sens.cells.flatMap((c) => c.row).filter(Number.isFinite);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    const tone = (v) => {
        if (!Number.isFinite(v) || hi === lo) return '';
        const t = (v - lo) / (hi - lo);
        return `background: rgba(56,189,248,${(0.05 + t * 0.24).toFixed(3)})`;
    };
    return `
    <h3 class="fin-sub">민감도 — 주당 가치</h3>
    <p class="fin-note">가로: 성장률 · 세로: 할인율 · 영구성장률 ${CO_DCF.terminal}% 고정.
       한 칸만 옮겨도 값이 크게 달라진다면, 그건 이 방법의 성질이지 계산 오류가 아닙니다.</p>
    <div class="co-table-wrap">
        <table class="co-table co-sens">
            <thead><tr><th>할인율 \\ 성장률</th>${sens.gs.map((g) => `<th>${g}%</th>`).join('')}</tr></thead>
            <tbody>
                ${sens.cells.map((c) => `
                    <tr><td class="co-label">${c.r}%</td>
                        ${c.row.map((v) => `<td style="${tone(v)}">${Number.isFinite(v) ? coNum(v, CUR) : '—'}</td>`).join('')}
                    </tr>`).join('')}
            </tbody>
        </table>
    </div>`;
};

const coReversePanel = (rows, CUR, data) => {
    const price = CO_PRICE.value;
    const shares = rows[0].raw.shares;
    const mcap = (Number.isFinite(price) && Number.isFinite(shares)) ? price * shares : null;
    const imp = mcap ? coImpliedGrowth(rows, mcap) : null;

    return `
    <h3 class="fin-sub">역방향 DCF — 시장은 몇 %를 가정하고 있나</h3>
    <p class="fin-note">
        위가 "이 가정이면 얼마인가" 라면, 이건 "지금 값이 맞으려면 무엇을 믿어야 하나" 입니다.
        ${CO_PRICE.status === 'loading' ? '현재가 조회 중…'
          : CO_PRICE.status === 'fail' ? `현재가를 못 받았습니다 — 직접 넣어 보세요.` : ''}
    </p>
    <div class="co-dcf-inputs">
        <label class="co-dcf-input">
            <span>현재 주가 (${finEsc(data.currency || '')})</span>
            <input type="number" data-co-price="1" value="${Number.isFinite(price) ? price : ''}" step="0.01" min="0">
        </label>
    </div>
    ${!Number.isFinite(price) ? `<p class="fin-note">주가를 넣으면 역산합니다.</p>`
      : !Number.isFinite(shares) ? `<p class="fin-note">희석주식수를 못 읽어 시가총액을 낼 수 없습니다.</p>`
      : !imp ? `<p class="fin-note">잉여현금흐름이 없거나 음수라 역산할 수 없습니다.</p>`
      : imp.unreachable ? `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">시가총액</span>
                <span class="fin-card-value">${coNum(mcap, data.currency)}</span>
                <p class="fin-card-plain">주가 × 희석주식수 ${mmFmt(shares, 0)}</p></div>
            <div class="fin-card"><span class="fin-card-title">FCF 배수</span>
                <span class="fin-card-value">${(mcap / rows[0].fcf).toFixed(0)}배</span>
                <p class="fin-card-plain">시가총액 ÷ 최근 잉여현금흐름입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">필요 영구성장률</span>
                <span class="fin-card-value">${(() => {
                    // 성장률로는 못 닿으니, 영구성장률을 역산해 격차의 크기를 보인다.
                    const r = CO_DCF.discount / 100, base = rows[0].fcf;
                    const target = mcap + (rows[0].net_debt ?? 0);
                    let lo = 0, hi = r - 0.0005;
                    const ev = (tg) => {
                        let f = base, pv = 0;
                        for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + tg); pv += f / Math.pow(1 + r, i); }
                        return pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
                    };
                    if (ev(hi) < target) return '해당 없음';
                    for (let k = 0; k < 60; k++) { const m = (lo + hi) / 2; if (ev(m) < target) lo = m; else hi = m; }
                    return `${((lo + hi) / 2 * 100).toFixed(1)}%`;
                })()}</span>
                <p class="fin-card-plain">할인율 ${CO_DCF.discount}% 를 유지할 때, 지금 값이 설명되려면 현금흐름이 영구히 이만큼 자라야 합니다.</p></div>
        </div>
        <p class="fin-note">
            ${imp.below ? '이 주가를 설명할 만큼 낮은 성장률이 없습니다.'
            : `성장률만으로는 닿지 않습니다 — 할인율(${CO_DCF.discount}%) 근처까지 올려도 지금 시가총액에 못 미칩니다.
               <strong>모델이 틀렸다기보다 가정이 시장과 다르다</strong>는 뜻입니다.
               장기 성장을 더 믿거나, 할인율을 더 낮게 보거나, 현금흐름 외의 것에 값이 매겨져 있거나입니다.`}
        </p>`
      : `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">시가총액</span>
                <span class="fin-card-value">${coNum(mcap, data.currency)}</span>
                <p class="fin-card-plain">주가 × 희석주식수 ${mmFmt(shares, 0)}</p></div>
            <div class="fin-card"><span class="fin-card-title">시장 내재 성장률</span>
                <span class="fin-card-value">${imp.growth.toFixed(1)}%</span>
                <p class="fin-card-plain">향후 5년 FCF가 매년 이만큼 늘어야 지금 값이 설명됩니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">과거 5년 실적</span>
                <span class="fin-card-value">${coDefaultGrowth(rows).toFixed(1)}%</span>
                <p class="fin-card-plain">같은 기간 실제 FCF 연평균 증가율입니다.</p></div>
        </div>
        <p class="fin-note">
            두 숫자의 간격이 이 주식에 걸린 기대입니다. 어느 쪽이 맞는지는 이 화면이 답하지 않습니다 —
            <strong>판단은 보는 사람의 몫</strong>이고, 이 도구는 그 판단이 무엇에 대한 것인지만 분명히 합니다.
        </p>`}`;
};

const coDcfPanel = (rows, CUR) => {
    if (CO_DCF.growth === null) CO_DCF.growth = coDefaultGrowth(rows);
    const d = coDcf(rows);
    const input = (key, label, step, min, max) => `
        <label class="co-dcf-input">
            <span>${finEsc(label)}</span>
            <input type="number" data-co-dcf="${key}" value="${CO_DCF[key]}"
                   step="${step}" min="${min}" max="${max}"><i>%</i>
        </label>`;

    return `
    <section class="fin-block fin-block-wide">
        <h2>DCF — 현금흐름 할인</h2>
        <p class="fin-lead">
            앞으로 벌어들일 잉여현금흐름을 오늘 가치로 당겨 더한 값입니다.
            <strong>세 가지 가정이 결과를 지배합니다</strong> — 그래서 숨기지 않고 여기 둡니다. 직접 바꿔 보세요.
        </p>
        <div class="co-dcf-inputs">
            ${input('growth', '향후 5년 FCF 성장률', 0.5, -30, 60)}
            ${input('terminal', '영구성장률', 0.1, 0, 5)}
            ${input('discount', '할인율 (WACC)', 0.25, 1, 30)}
            <button class="pf-btn pf-btn-ghost" data-co-dcf-reset="1">기본값</button>
        </div>
        ${!d ? '<p class="fin-note">잉여현금흐름이 음수이거나 없어 DCF를 낼 수 없습니다. 현금을 쓰는 국면의 기업에는 이 방법이 맞지 않습니다.</p>'
          : d.invalid ? `<p class="fin-note">${finEsc(d.invalid)}</p>` : `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">기업가치 (EV)</span>
                <span class="fin-card-value">${coNum(d.ev, CUR)}</span>
                <p class="fin-card-plain">향후 현금흐름 + 잔존가치의 현재가치 합입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">주주가치</span>
                <span class="fin-card-value">${coNum(d.equity, CUR)}</span>
                <p class="fin-card-plain">기업가치에서 순부채를 뺀 값입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">주당 가치</span>
                <span class="fin-card-value">${d.perShare === null ? '—' : coNum(d.perShare, CUR)}</span>
                <p class="fin-card-plain">${d.shares ? `희석주식수 ${mmFmt(d.shares, 0)}주 기준` : '주식수를 못 읽어 계산하지 못했습니다.'}</p></div>
            <div class="fin-card"><span class="fin-card-title">잔존가치 비중</span>
                <span class="fin-card-value">${coPct(d.tailShare)}</span>
                <p class="fin-card-plain">전체 가치 중 6년차 이후가 차지하는 몫입니다. 이 값이 높을수록 결과가 영구성장률 가정에 좌우됩니다.</p></div>
        </div>
        <div class="co-table-wrap">
            <table class="co-table">
                <thead><tr><th>연차</th>${d.flows.map((f) => `<th>${f.year}년</th>`).join('')}<th>잔존</th></tr></thead>
                <tbody>
                    <tr><td class="co-label">예상 FCF</td>${d.flows.map((f) => `<td>${coNum(f.fcf, CUR)}</td>`).join('')}<td>${coNum(d.tail, CUR)}</td></tr>
                    <tr><td class="co-label">현재가치</td>${d.flows.map((f) => `<td>${coNum(f.pv, CUR)}</td>`).join('')}<td>${coNum(d.tailPv, CUR)}</td></tr>
                </tbody>
            </table>
        </div>
        <p class="fin-note">
            기준 FCF ${coNum(d.base, CUR)} (FY${rows[0].fy} 실적) 에서 출발합니다.
        </p>
        ${coSensPanel(rows, CUR)}`}
        ${coReversePanel(rows, CUR, CO_DATA || {})}
    </section>`;
};

// --- 구조 (심층) --------------------------------------------------------------
const coStructRows = (r, CUR) => {
    const R = r.raw;
    const liab = [
        ['단기차입금·기업어음', R.debt_short],
        ['유동성 장기부채', R.debt_current_portion],
        ['매입채무', R.payables],
        ['미지급비용', R.accrued],
        ['이연수익(선수금)', R.deferred_revenue],
        ['리스부채 (유동)', R.lease_current],
        ['기타 유동부채', R.other_current],
        ['장기차입금', R.debt_long],
        ['리스부채 (비유동)', R.lease_noncurrent],
        ['이연법인세', R.deferred_tax],
        ['기타 비유동부채', R.other_noncurrent],
    ].filter(([, v]) => Number.isFinite(v));
    const asset = [
        ['현금성자산', R.cash],
        ['단기투자·유가증권', R.securities_current],
        ['매출채권', R.receivables],
        ['재고자산', R.inventory],
        ['유형자산', R.ppe],
        ['영업권', R.goodwill],
        ['무형자산', R.intangibles],
    ].filter(([, v]) => Number.isFinite(v));
    return { liab, asset };
};

const coBarList = (rows, total, CUR) => {
    const max = Math.max(...rows.map(([, v]) => Math.abs(v)), 1);
    return `<div class="mm-bars mm-bars-compact">
        ${rows.map(([label, v]) => `
            <div class="mm-bar-row">
                <span class="mm-bar-label">${finEsc(label)}</span>
                <span class="mm-bar-track"><span class="mm-bar-fill" style="width:${(Math.abs(v) / max * 100).toFixed(1)}%"></span></span>
                <span class="mm-bar-value">${coNum(v, CUR)}${total ? `<span class="co-share">${(v / total * 100).toFixed(0)}%</span>` : ''}</span>
            </div>`).join('')}
    </div>`;
};

let CO_STRUCT_OPEN = null;   // 'liab' | 'asset' | null

const coDeepPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    const { liab, asset } = coStructRows(latest, CUR);

    return `
    <section class="fin-block fin-block-wide">
        <h2>부채 구조 — 언제 갚아야 하는가</h2>
        <p class="fin-lead">
            부채비율 하나로는 보이지 않는 것이 있습니다. 회사를 어렵게 만드는 건 <strong>얼마를 빚졌는지가 아니라 언제 갚아야 하는지</strong>입니다.
        </p>
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">이자부 부채 합계</span>
                <span class="fin-card-value">${coNum(latest.debt_total, CUR)}</span>
                <p class="fin-card-plain">매입채무 같은 영업부채를 뺀, 이자를 무는 빚만 모은 값입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">1년 내 만기 비중</span>
                <span class="fin-card-value">${coPct(latest.short_share)}</span>
                <p class="fin-card-plain">이자부 부채 중 1년 안에 갚거나 차환해야 하는 몫입니다. 높을수록 금리·자금시장 경색에 민감합니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">이자보상배율</span>
                <span class="fin-card-value">${coRatio(latest.interest_cover, 1)}배</span>
                <p class="fin-card-plain">영업이익이 이자비용의 몇 배인가. 1배 아래면 본업으로 이자도 못 냅니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">당좌비율</span>
                <span class="fin-card-value">${coPct(latest.quick_ratio)}</span>
                <p class="fin-card-plain">재고를 뺀 유동자산으로 단기부채를 갚을 수 있는 정도입니다.</p></div>
        </div>
        ${coTable(rows, [
            { label: '이자부 부채', fmt: (r) => coNum(r.debt_total, CUR) },
            { label: '1년 내 만기', fmt: (r) => coNum(r.interest_bearing_short, CUR) },
            { label: '순부채', fmt: (r) => coNum(r.net_debt, CUR) },
            { label: '이자보상배율', fmt: (r) => coRatio(r.interest_cover, 1) },
        ])}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>자산·자본 구조</h2>
        <p class="fin-lead">항목을 눌러 구성을 펼쳐 보세요.</p>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${CO_STRUCT_OPEN === 'asset' ? 'on' : ''}" data-co-struct="asset">자산 구성 (${asset.length})</button>
            <button class="mm-view-btn ${CO_STRUCT_OPEN === 'liab' ? 'on' : ''}" data-co-struct="liab">부채 구성 (${liab.length})</button>
        </div>
        ${CO_STRUCT_OPEN === 'asset' ? `
            ${coBarList(asset, latest.raw.assets, CUR)}
            <p class="fin-note">비율은 총자산 ${coNum(latest.raw.assets, CUR)} 대비입니다. 합이 100%가 되지 않는 것은 위에 없는 잔여 항목이 있기 때문입니다.</p>`
        : CO_STRUCT_OPEN === 'liab' ? `
            ${coBarList(liab, latest.raw.liabilities, CUR)}
            <p class="fin-note">비율은 총부채 ${coNum(latest.raw.liabilities, CUR)} 대비입니다.</p>`
        : ''}
        ${coTable(rows, [
            { label: '총자산', fmt: (r) => coNum(r.raw.assets, CUR) },
            { label: '총부채', fmt: (r) => coNum(r.raw.liabilities, CUR) },
            { label: '자기자본', fmt: (r) => coNum(r.raw.equity, CUR) },
            { label: '이익잉여금', fmt: (r) => coNum(r.raw.retained_earnings, CUR) },
            { label: '자기자본비율', fmt: (r) => coPct(r.equity_ratio) },
        ])}
    </section>`;
};

const coHealthPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    return `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">유동비율</span>
                <span class="fin-card-value">${coPct(latest.current_ratio)}</span>
                <p class="fin-card-plain">1년 안에 갚을 빚 대비 1년 안에 현금이 되는 자산. 100%를 밑돌면 단기 자금이 빠듯하다는 뜻입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">부채비율 (부채/자산)</span>
                <span class="fin-card-value">${coPct(latest.debt_ratio)}</span>
                <p class="fin-card-plain">자산 중 남의 돈이 차지하는 비율입니다. 업종마다 정상 범위가 크게 달라 같은 업종끼리 비교해야 합니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">영업이익률</span>
                <span class="fin-card-value">${coPct(latest.operating_margin)}</span>
                <p class="fin-card-plain">매출 100원으로 본업에서 남긴 이익입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">ROE</span>
                <span class="fin-card-value">${coPct(latest.roe)}</span>
                <p class="fin-card-plain">주주 돈으로 낸 수익률입니다. 빚을 많이 쓰면 자연히 높아지므로 부채비율과 같이 봐야 합니다.</p></div>
        </div>
        <section class="fin-block fin-block-wide">
            <h2>연도별 추이</h2>
            ${coTable(rows, [
                { label: '매출', fmt: (r) => coNum(r.raw.revenue, CUR) },
                { label: '영업이익', fmt: (r) => coNum(r.raw.operating_income, CUR) },
                { label: '순이익', fmt: (r) => coNum(r.raw.net_income, CUR) },
                { label: '영업이익률', fmt: (r) => coPct(r.operating_margin) },
                { label: '유동비율', fmt: (r) => coPct(r.current_ratio) },
                { label: '부채비율', fmt: (r) => coPct(r.debt_ratio) },
            ])}
        </section>`;
};

const coValuationPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    return `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">잉여현금흐름 (FCF)</span>
                <span class="fin-card-value">${coNum(latest.fcf, CUR)}</span>
                <p class="fin-card-plain">영업으로 번 현금에서 설비투자를 뺀 값입니다. 배당·자사주·부채상환에 쓸 수 있는 실제 여윳돈입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">FCF 마진</span>
                <span class="fin-card-value">${coPct(latest.fcf_margin)}</span>
                <p class="fin-card-plain">매출이 현금으로 남는 비율입니다. 이익은 나는데 이 값이 낮으면 회계 이익과 현금이 어긋난다는 신호입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">순부채</span>
                <span class="fin-card-value">${coNum(latest.net_debt, CUR)}</span>
                <p class="fin-card-plain">이자부 부채에서 현금·단기투자를 뺀 값입니다. 음수면 빚보다 현금이 많다는 뜻입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">ROA</span>
                <span class="fin-card-value">${coPct(latest.roa)}</span>
                <p class="fin-card-plain">자산 전체로 낸 수익률입니다. ROE와 벌어지면 그 차이가 레버리지에서 옵니다.</p></div>
        </div>
        <section class="fin-block fin-block-wide">
            <h2>현금 흐름</h2>
            ${coTable(rows, [
                { label: '영업현금흐름', fmt: (r) => coNum(r.raw.cfo, CUR) },
                { label: '설비투자 (CapEx)', fmt: (r) => coNum(r.raw.capex, CUR) },
                { label: '잉여현금흐름', fmt: (r) => coNum(r.fcf, CUR) },
                { label: 'FCF 마진', fmt: (r) => coPct(r.fcf_margin) },
                { label: '순이익', hint: '현금과 비교', fmt: (r) => coNum(r.raw.net_income, CUR) },
            ])}
            <p class="fin-note">
                순이익과 영업현금흐름이 오래 벌어져 있으면 이유를 봐야 합니다 — 매출채권이 쌓였거나, 재고가 늘었거나,
                회계상 이익이 현금으로 들어오지 않는 구조일 수 있습니다.
            </p>
        </section>
        ${coDcfPanel(rowsDesc, CUR)}`;
};

const coRenderLevel = (level, rowsDesc, data) => {
    const CUR = data.currency || 'KRW';
    const parts = coLevelsUpTo(level).map((id) => {
        if (id === 'health') return coHealthPanel(rowsDesc, CUR);
        if (id === 'valuation') return coValuationPanel(rowsDesc, CUR);
        return coDeepPanel(rowsDesc, CUR);
    });
    return parts.join('\n<hr class="co-sep">\n');
};

// === 시장 미시구조 / US→KR ==================================================
//
// Engine and snapshots are Cursor's (scripts/market_microstructure); this file
// only reads them. Three tabs, because the three questions are separate ones:
// how tangled Korean flow is, where foreigners actually bought, and whether the
// US options tape is leaning on Korea. The rule throughout: a null stays blank.
// A plausible-looking number in a positioning panel is worse than an empty one.
const MS_FILES = {
    transmission: 'us_kr_transmission_v1.json',
    alerts: 'alert_levels_v1.json',
    conc: 'kospi_concentration_history_v1.json',
    board: 'derivatives_board_v1.json',
    brief: 'ai_casino_brief_v1.json',
    levels: 'investor_price_levels_v1.json',
    micro: 'market_microstructure_v1.json',
};

const MS_TABS = [
    { id: 'tangle', label: '수급 불균형', blurb: '집중도와 단일종목 레버리지 ETF (Distortion & Squeeze)' },
    { id: 'levels', label: '가격대별 체결', blurb: '어느 가격에서 누가 샀는가 (Volume Profile)' },
    { id: 'uskr',   label: '해외-국내 선행', blurb: '미국 옵션 레짐이 한국으로 (Global Spillover)' },
];

let MS_DATA = null;
let MS_TAB = 'tangle';
let MS_UNIVERSE = 'marcap';
let MS_TICKER = null;         // 가격대별 탭에서 선택한 종목 (null = 코스피 지수)
let MS_STOCK = null;          // 수급 꼬임 탭에서 선택한 종목
let MS_MODAL = null;          // { title, html }

const msGet = async (name) => {
    for (const base of ['/public/data/', '/data/']) {
        try {
            const r = await fetch(base + name, { cache: 'no-store' });
            if (r.ok) return await r.json();
        } catch (_) { /* next */ }
    }
    return null;
};

const msMissing = (label) => `<span class="ms-missing">${finEsc(label || '데이터 없음')}</span>`;
const msNum = (v, d = 0) => Number.isFinite(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: d }) : '—';
const msJo = (v) => Number.isFinite(v) ? `${(v / 1e12).toFixed(2)}조` : '—';
const msEok = (v) => Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString('ko-KR')}억` : '—';
const msShares = (v) => Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString('ko-KR')}` : '—';
const msPct = (v, d = 1) => Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : '—';
const MS_LEVEL_CLASS = { '경계': 'ms-lv-3', '주의': 'ms-lv-2', '관찰': 'ms-lv-1', high: 'ms-lv-3', mid: 'ms-lv-2', watch: 'ms-lv-2', low: 'ms-lv-1', quiet: 'ms-lv-1' };

// Every summary box is a button that opens the table behind it. A card that
// shows a number but cannot be opened reads as data without an explanation.
const msCard = (title, value, sub, modalKey, cls) => `
    <button class="fin-card ms-card${modalKey ? ' ms-clickable' : ''}" ${modalKey ? `data-ms-modal="${finEsc(modalKey)}"` : 'disabled'}>
        <span class="fin-card-title">${finEsc(title)}</span>
        <span class="fin-card-value ${cls || ''}">${value}</span>
        ${sub ? `<p class="fin-card-plain">${sub}</p>` : ''}
        ${modalKey ? '<span class="ms-more">표 보기 →</span>' : ''}
    </button>`;

const msTable = (head, rows) => `
    <div class="co-table-wrap">
        <table class="co-table">
            <thead><tr>${head.map((h) => `<th>${finEsc(h)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="co-label"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
    </div>`;

// Horizontal bars centred on zero: the Infomax-style read is "who bought at
// which price", and buying versus selling has to be legible at a glance.
const msDivergingBars = (rows, opts = {}) => {
    const all = rows.flatMap((r) => r.series.map((s) => s.value)).filter(Number.isFinite);
    const max = Math.max(...all.map(Math.abs), 1);
    return `
    <div class="ms-dist">
        ${rows.map((r) => `
            <div class="ms-dist-row${r.highlight ? ' on' : ''}">
                <span class="ms-dist-label">${finEsc(r.label)}${r.sub ? `<span>${finEsc(r.sub)}</span>` : ''}</span>
                <span class="ms-dist-bars">
                    ${r.series.map((sx) => {
                        const v = Number(sx.value);
                        const w = Number.isFinite(v) ? Math.abs(v) / max * 50 : 0;
                        const neg = v < 0;
                        return `<span class="ms-dist-track" title="${finEsc(sx.name)} ${msNum(v)}">
                            <span class="ms-dist-fill ms-${sx.key}${neg ? ' neg' : ''}"
                                  style="width:${w.toFixed(2)}%; ${neg ? 'right:50%' : 'left:50%'}"></span>
                        </span>`;
                    }).join('')}
                </span>
                <span class="ms-dist-val">${finEsc(r.valueText || '')}</span>
            </div>`).join('')}
        <div class="ms-dist-legend">
            ${(opts.legend || []).map((l) => `<span><i class="ms-sw ms-${l.key}"></i>${finEsc(l.name)}</span>`).join('')}
            <span class="ms-dist-zero">가운데가 0 · 왼쪽 순매도 / 오른쪽 순매수</span>
        </div>
    </div>`;
};

// --- ① 수급 꼬임 -------------------------------------------------------------
// distortion_squeeze is documented as the top-level block, but the shipped
// snapshot has not produced it yet -- the same numbers live at the document's
// root instead (concentration, market_letf_derivatives_ratios,
// global_leverage_stack, stocks[]). DISTORTION_SQUEEZE.md names this fallback
// explicitly, so this reads the root fields rather than waiting on a key that
// may never land under that exact name.
const msTangle = (D) => {
    const m = D.micro || {};
    const conc = m.concentration || (D.conc || {}).latest || {};
    const stocks = Array.isArray(m.stocks) ? m.stocks : [];
    const sel = stocks.find((x) => x.ticker === MS_STOCK) || stocks[0] || null;
    const ratios = m.market_letf_derivatives_ratios || {};
    const stack = m.global_leverage_stack || {};
    const fvr = m.foreign_vs_retail || {};
    const dc = m.deposit_credit || {};
    const byDir = ratios.by_direction || {};
    const bands = m.ir_bands || {};

    // Stress-sorted: the row worth looking at first is the one with the
    // biggest 10%-down impact, not the biggest name.
    const ranked = [...stocks].sort((a, b) =>
        (b.scenarios?.r_minus_10pct?.ir_pct ?? -1) - (a.scenarios?.r_minus_10pct?.ir_pct ?? -1));

    const bandCls = { low: 'ms-lv-1', mid: 'ms-lv-2', watch: 'ms-lv-2', high: 'ms-lv-3' };

    return `
    <section class="fin-block fin-block-wide">
        <h2>A · 코스피 집중도</h2>
        <p class="fin-lead">지수가 몇 종목에 얼마나 매달려 있는지입니다. 높을수록 그 종목의 사정이 곧 시장의 사정이 됩니다.</p>
        <div class="fin-cards">
            ${msCard('상위 2 (삼성·하닉)', Number.isFinite(conc.conc_top2_samsung_hynix_pct) ? conc.conc_top2_samsung_hynix_pct.toFixed(1) + '%' : '—',
                (conc.top5_tickers || []).slice(0, 2).join(' · '), 'conc')}
            ${msCard('상위 5', Number.isFinite(conc.conc_top5_pct) ? conc.conc_top5_pct.toFixed(1) + '%' : '—',
                (conc.top5_tickers || []).join(' · '), 'conc')}
            ${msCard('상위 10', Number.isFinite(conc.conc_top10_pct) ? conc.conc_top10_pct.toFixed(1) + '%' : '—',
                `종목 ${msNum((D.conc || {}).latest?.n_names)}개 기준`, 'conc')}
        </div>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>B · 시장 전체</h2>
        <div class="fin-cards">
            ${msCard('레버·곱버스 거래대금 / 코스피 현물', Number.isFinite(ratios.levered_inverse_etf_tv_over_kospi_cash_tv_pct) ? ratios.levered_inverse_etf_tv_over_kospi_cash_tv_pct.toFixed(1) + '%' : '—',
                `롱 ${msJo(ratios.long_tv_jo * 1e12)} · 인버스 ${msJo(ratios.inverse_tv_jo * 1e12)}`, 'letf_cat')}
            ${msCard('외국인 vs 개인 순매수', msEok((fvr.foreign_net_krw ?? 0) / 1e8),
                `개인 ${msEok((fvr.retail_net_krw ?? 0) / 1e8)} · 기관 ${msEok((fvr.institution_net_krw ?? 0) / 1e8)}${fvr.quality === 'estimated' ? ' · 추정' : ''}`, null,
                fvr.foreign_net_krw >= 0 ? 'fin-up' : 'fin-down')}
            ${msCard('신용융자 / 예탁금', Number.isFinite(dc.credit_over_deposit_pct) ? dc.credit_over_deposit_pct.toFixed(1) + '%' : '—',
                `예탁금 ${msEok(dc.investor_deposit_eok)} · 신용 ${msEok(dc.credit_balance_eok)} (${finEsc(dc.as_of || '')})`, null)}
        </div>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>D · 방향별 레버리지 상품 (곱버스 분리)</h2>
        <p class="fin-lead">인버스 안에서도 <strong>2배 곱버스</strong>는 따로 셉니다. 되사고 되파는 압력이 방향에 따라 다르게 쌓입니다.</p>
        ${Object.keys(byDir).length ? `
        <div class="fin-cards">
            ${[['long', '롱(추종)'], ['inverse', '인버스(1X)'], ['inverse_2x', '인버스(2X)'], ['gobus_inverse_2x', '곱버스(2X)']].map(([k, ko]) => {
                const b = byDir[k]; if (!b) return '';
                return msCard(ko, msJo(b.trading_value_krw), `상품 ${msNum(b.n_products)}종 · 코스피 거래대금의 ${(b.share_of_kospi_tv_pct ?? 0).toFixed(1)}%`, null);
            }).join('')}
        </div>` : `<p class="fin-note">${msMissing('라이브 재빌드 후 표시')}</p>`}
        ${stack.global_stack_usd ? `
        <p class="fin-note">
            해외 레버 스택(규모 비교용, 국내 회전율에 합산하지 않음): KR $${(stack.kr_single_stock_letf_notional_usd / 1e9).toFixed(1)}B ·
            HK $${(stack.hk_swap_letf_notional_usd / 1e9).toFixed(1)}B · US $${(stack.us_levered_etf_notional_usd / 1e9).toFixed(1)}B ·
            crypto $${(stack.crypto_perp_oi_notional_usd / 1e6).toFixed(0)}M. ${finEsc(stack.hedge_channel_ko || '')}
        </p>` : ''}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>E · 종목 스트레스</h2>
        <p class="fin-lead">
            2배 ETF 1좌는 기초자산 2좌만큼의 노출을 만듭니다. IR(Implied Rebalancing)은 그 노출을 되사고 되팔 때
            현물 ADV 대비 얼마나 큰 물량이 나오는지를 잽니다 — 클수록 리밸런싱 자체가 가격을 흔들 수 있습니다.
        </p>
        ${stocks.length ? msTable(
            ['종목', '회전율', 'wag-the-dog', '인버스 비중', '−5% IR', '−10% IR', '밴드', ''],
            ranked.map((st) => {
                const t = st.flow_tangle || {};
                const s10 = st.scenarios?.r_minus_10pct, s5 = st.scenarios?.r_minus_5pct;
                return [
                    `${finEsc(st.name)} <span class="co-hint">${finEsc(st.ticker)}</span>`,
                    msPct(st.letf_turnover_ratio),
                    `<span class="ms-badge ${bandCls[t.wag_the_dog_band] || ''}">${finEsc(t.wag_the_dog_band || '—')}</span>`,
                    msPct(t.inverse_tv_share),
                    Number.isFinite(s5?.ir_pct) ? s5.ir_pct.toFixed(1) + '%' : '—',
                    Number.isFinite(s10?.ir_pct) ? `<span class="ms-badge ${bandCls[s10.band] || ''}">${s10.ir_pct.toFixed(1)}%</span>` : '—',
                    `<span class="ms-badge ${bandCls[t.realized_band] || ''}">${finEsc(t.realized_band || '—')}</span>`,
                    `<button class="mm-view-btn" data-ms-stock="${finEsc(st.ticker)}" data-ms-modal="letf_products">상품별</button>`,
                ];
            })) : `<p class="fin-note">${msMissing('종목 스트레스 데이터 없음')}</p>`}
        <p class="fin-note">IR 밴드: watch ≥ ${bands.watch_lt_pct ?? 10}% · low &lt; ${bands.low_lt_pct ?? 3}%. NAV는 공개 스냅샷에 없어 표시하지 않습니다 — 상품별 순자산(AUM)과 거래대금만 실측입니다.</p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>F · 해석 힌트</h2>
        <ul class="fin-list">
            <li>wag-the-dog=high → LETF 거래대금이 현물 거래대금에 육박 → 리밸런싱이 현물가에 영향을 줄 수 있는 상태</li>
            <li>−10% IR ≥ ${bands.watch_lt_pct ?? 10}% → 기초자산이 10% 빠지면 리밸런싱 되팔기가 현물 ADV의 그만큼을 추가로 밀어냄</li>
            <li>인버스 비중이 높을수록 기초자산 하락 시 오히려 매수(숏커버 성격) 압력이 커짐</li>
        </ul>
        <p class="fin-note">${finEsc((m.broker_leverage_disclosure || {}).note_ko || '증권사 고객 레버리지 공시가 아닙니다. 공개 LETF AUM·거래대금 기반 프록시입니다.')}</p>
    </section>`;
};

// --- ② 가격대별 수급 ---------------------------------------------------------
const msLevelsTab = (D) => {
    const lv = D.levels || {};
    const kl = lv.kospi_index_levels || {};
    const tickers = lv.tickers || {};
    const isIndex = !MS_TICKER;
    const src = isIndex ? kl : (tickers[MS_TICKER] || {});
    const bins = Array.isArray(src.bins_by_close) ? src.bins_by_close : [];
    const unitEok = isIndex;

    const table = MS_UNIVERSE === 'high_vol' ? (lv.close_day_table_high_vol || []) : (lv.close_day_table_marcap || []);
    const L = kl.latest || {};

    const rows = bins.filter((b) => b.n_days > 0).map((b) => ({
        label: `${msNum(b.price_lo)} ~ ${msNum(b.price_hi)}`,
        sub: `${b.n_days}일`,
        series: [
            { key: 'retail', name: '개인', value: unitEok ? b.retail_net_krw : b.retail_net_shares },
            { key: 'foreign', name: '외국인', value: unitEok ? b.foreign_net_krw : b.foreign_net_shares },
            { key: 'inst', name: '기관', value: unitEok ? b.institution_net_krw : b.institution_net_shares },
        ],
        valueText: unitEok
            ? `개인 ${msEok(b.retail_net_krw)} · 외인 ${msEok(b.foreign_net_krw)}`
            : `개인 ${msShares(b.retail_net_shares)} · 외인 ${msShares(b.foreign_net_shares)}`,
    }));

    return `
    <section class="fin-block fin-block-wide">
        <h2>가격대별 누적 수급 <span class="ms-q">${finEsc(src.quality || '')}</span></h2>
        <p class="fin-lead">
            어느 가격대에서 누가 사고 팔았는지를 실측 일별 수급으로 쌓은 것입니다.
            <strong>체결 단위 매집도가 아닙니다</strong> — 그 데이터는 공개되지 않습니다.
        </p>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${isIndex ? 'on' : ''}" data-ms-ticker="">코스피 지수</button>
            ${Object.keys(tickers).slice(0, 8).map((tk) => `<button class="mm-view-btn ${MS_TICKER === tk ? 'on' : ''}"
                data-ms-ticker="${finEsc(tk)}">${finEsc(tickers[tk].label_ko || tk)}</button>`).join('')}
        </div>
        ${src.headline_ko ? `<p class="ms-lead-strong">${finEsc(src.headline_ko)}</p>` : ''}
        ${rows.length ? msDivergingBars(rows, {
            legend: [{ key: 'retail', name: '개인' }, { key: 'foreign', name: '외국인' }, { key: 'inst', name: '기관' }],
        }) : `<p class="fin-note">${msMissing('구간별 수급 없음')}</p>`}
        <p class="fin-note">
            ${finEsc(src.method_ko || '')} 단위 ${finEsc(unitEok ? (kl.unit || '억원') : '주')} ·
            ${src.n_days || 0}일 (${finEsc(src.date_start || '')} ~ ${finEsc(src.date_end || '')})
        </p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>종가일 수급</h2>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${MS_UNIVERSE === 'marcap' ? 'on' : ''}" data-ms-univ="marcap">시총 상위</button>
            <button class="mm-view-btn ${MS_UNIVERSE === 'high_vol' ? 'on' : ''}" data-ms-univ="high_vol">시총 100위 내 고변동</button>
        </div>
        ${table.length ? msTable(['종목', '날짜', '종가', '개인(주)', '외국인(주)', '기관(주)', ''],
            table.map((r) => [
                `${finEsc(r.label_ko)} <span class="co-hint">${finEsc(r.ticker)}</span>`,
                finEsc(r.date || ''), msNum(r.close),
                `<span class="${r.retail_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.retail_net_shares)}</span>`,
                `<span class="${r.foreign_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.foreign_net_shares)}</span>`,
                `<span class="${r.institution_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.institution_net_shares)}</span>`,
                tickers[r.ticker] ? `<button class="mm-view-btn" data-ms-ticker="${finEsc(r.ticker)}">가격대별</button>` : '',
            ])) : `<p class="fin-note">${msMissing('종가일 표 없음')}</p>`}
        <p class="fin-note">지수 순매수 최근일: 개인 ${msEok(L.retail_net_eok)} · 외국인 ${msEok(L.foreign_net_eok)} · 기관 ${msEok(L.institution_net_eok)} (${finEsc(L.date || '')})</p>
        ${(lv.cannot_do_ko || []).length ? `
        <details class="mm-limits">
            <summary>이 데이터로 할 수 없는 것</summary>
            ${lv.cannot_do_ko.map((x) => `<div class="mm-limit"><p>${finEsc(x)}</p></div>`).join('')}
        </details>` : ''}
    </section>`;
};

// --- ③ US → KR 조기경보 ------------------------------------------------------
const msUsKr = (D) => {
    const t = D.transmission || {};
    const gs = t.global_spillover || {};
    const a = D.alerts || {};
    const b = D.board || {};
    const ch = t.channels || {};
    const [lvl, dir] = String(t.headline || '').split(':');
    const dirKo = { downside: '하방', upside: '상방', vol_up: '변동성 확대', vol_down: '변동성 축소' }[dir] || dir || '';
    const ev = Array.isArray(t.evidence_us) ? t.evidence_us : [];
    const letf = a.kr_hynix_letf || {};
    const vix = a.us_vix_to_kr || {};
    const hit = gs.open30m_hit || {};

    return `
    <section class="fin-block fin-block-wide">
        <h2>왜 지금 ${finEsc(dirKo)}인가</h2>
        <div class="ms-headline">
            <span class="ms-head-level ${MS_LEVEL_CLASS[lvl] || ''}">${finEsc(gs.headline_ko || t.headline_ko || `${lvl} · ${dirKo}`)}</span>
            <span class="ms-head-meta">기준 ${finEsc(gs.as_of || t.as_of || '')} · 모델 ${finEsc(t.model_version || '')}</span>
        </div>
        ${gs.why_short_ko || t.why_ko ? `<p class="ms-why">${finEsc(gs.why_short_ko || t.why_ko)}</p>` : ''}
        <p class="fin-note ms-warn">
            <strong>하방 ≠ 미국 주가 급락.</strong> 공개 옵션에서 풋 쪽이 두드러진 상태가 한국 링크로 이어져 있다는 뜻입니다.
            주체를 특정하지 않으며, 방향을 맞힌다는 주장도 아닙니다.
        </p>
        ${ev.length ? `
        <h3 class="fin-sub">미국 쪽 실측 근거</h3>
        ${msTable(['심볼', '레짐', '스트레스', 'P/C 거래량', 'P/C OI', '옵션 거래량', '공매 증감'],
            ev.map((e) => [
                `<button class="ms-link" data-ms-modal="ev:${finEsc(e.symbol)}">${finEsc(e.symbol)}</button>`,
                (e.regimes || []).join(', '),
                `<span class="ms-badge ${MS_LEVEL_CLASS[e.stress_level] || ''}">${finEsc(e.stress_level || '')}</span>`,
                Number.isFinite(e.put_call_volume) ? e.put_call_volume.toFixed(2) : '—',
                Number.isFinite(e.put_call_oi) ? e.put_call_oi.toFixed(2) : '—',
                msNum(e.options_total_volume),
                Number.isFinite(e.short_chg_pct) ? `<span class="${e.short_chg_pct >= 0 ? 'fin-down' : 'fin-up'}">${e.short_chg_pct.toFixed(1)}%</span>` : '—',
            ]))}
        <p class="fin-note">P/C = 풋 ÷ 콜. 1보다 크면 풋 쪽이 많다는 뜻이고, 그 자체가 하락 예측은 아닙니다. 심볼을 누르면 판정 규칙이 나옵니다.</p>` : ''}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>전이 채널</h2>
        <div class="ms-channels">
            ${[['downside', '하방'], ['upside', '상방'], ['vol_up', '변동성 확대'], ['vol_down', '변동성 축소']].map(([k, ko]) => {
                const c = ch[k] || {};
                return `
                <button class="ms-channel${k === dir ? ' on' : ''}${(c.drivers || []).length ? ' ms-clickable' : ''}"
                        ${(c.drivers || []).length ? `data-ms-modal="ch:${k}"` : 'disabled'}>
                    <span class="ms-ch-name">${finEsc(ko)}</span>
                    <span class="ms-ch-heat">${Number.isFinite(c.heat) ? c.heat.toFixed(1) : '—'}</span>
                    <span class="ms-ch-lv">${finEsc(c.level || '—')}</span>
                    ${(c.kr_tickers || []).length ? `<span class="ms-ch-tick">${c.kr_tickers.map(finEsc).join(' · ')}</span>` : ''}
                </button>`;
            }).join('')}
        </div>
        <p class="fin-note">heat는 미국 쪽 레짐 강도 × 링크 가중의 합입니다. 채널을 누르면 어떤 연결이 얼마나 기여했는지 나옵니다.</p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>알림 레벨 · 파생 보드</h2>
        <div class="fin-cards">
            ${msCard('하닉 레버리지 ETF 비율',
                `<span class="ms-badge ${MS_LEVEL_CLASS[letf.today_level] || ''}">${finEsc(letf.today_level || '—')}</span> ${Number.isFinite(letf.today_ratio) ? msPct(letf.today_ratio) : ''}`,
                finEsc(letf.metric_ko || ''), 'alert_letf')}
            ${msCard('US VIX → KR',
                `<span class="ms-badge ${MS_LEVEL_CLASS[vix.today_level] || ''}">${finEsc(vix.today_level || '—')}</span>`,
                finEsc(vix.metric_ko || ''), 'alert_vix')}
            ${msCard('US OI 룰 헤드라인',
                `<span class="ms-badge ${MS_LEVEL_CLASS[(b.us_kr_rules || {}).headline_level] || ''}">${finEsc((b.us_kr_rules || {}).headline_level || '—')}</span>`,
                '', null)}
            ${msCard('코스피200 외인 콜/풋/선물', msMissing('데이터 없음'), 'KRX_API 키 또는 CSV 주입 필요', null)}
        </div>
        <p class="fin-note">
            VIX 알림은 Cboe 공식 VIX의 전일 대비 변화율입니다 — <strong>풋 미결제약정(OI)이 아닙니다.</strong>
            종목 단위 풋 OI 히스토리가 공개되지 않아 그 임계값은 만들 수 없습니다.
        </p>
    </section>

    ${Number.isFinite(hit.downside_hit_rate_mean) ? `
    <section class="fin-block fin-block-wide">
        <h2>장초 30분 백테스트</h2>
        <div class="fin-cards">
            ${msCard('하방 적중률', msPct(hit.downside_hit_rate_mean),
                '하방 드라이버가 뜬 날, 익일 KR 개장 30분 수익률이 실제로 음수였던 비율')}
            ${msCard('하방일 평균 개장 수익률', msPct(hit.downside_mean_open_r, 2), '', null,
                hit.downside_mean_open_r >= 0 ? 'fin-up' : 'fin-down')}
        </div>
        <p class="fin-note ms-warn">${finEsc(hit.note_ko || '옵션 히스토리가 아니라 수익률 버킷 프록시입니다. 과대해석하지 마세요.')}</p>
    </section>` : ''}

    ${(gs.read_ko || []).length || (gs.data_limits_ko || []).length ? `
    <section class="fin-block fin-block-wide">
        ${(gs.read_ko || []).length ? `
        <h3 class="fin-sub">해석 힌트</h3>
        <ul class="fin-list">${gs.read_ko.map((x) => `<li>${finEsc(x)}</li>`).join('')}</ul>` : ''}
        ${(gs.data_limits_ko || []).length ? `
        <h3 class="fin-sub">이 데이터로 할 수 없는 것</h3>
        <ul class="fin-list">${gs.data_limits_ko.map((x) => `<li>${finEsc(x)}</li>`).join('')}</ul>` : ''}
    </section>` : ''}

    <p class="mm-disclaimer">${finEsc(t.disclaimer_ko || '')}</p>`;
};

// --- 모달 --------------------------------------------------------------------
const msModalFor = (key, D) => {
    const t = D.transmission || {};
    const m = D.micro || {};
    if (key === 'conc') {
        const pts = (D.conc || {}).points || [];
        return { title: '코스피 집중도 추이',
            html: msTable(['날짜', '상위 2', '상위 5', '상위 10', '종목 수'],
                pts.slice(-24).reverse().map((p) => [finEsc(p.date),
                    `${(p.conc_top2_samsung_hynix_pct ?? 0).toFixed(2)}%`,
                    `${(p.conc_top5_pct ?? 0).toFixed(2)}%`,
                    `${(p.conc_top10_pct ?? 0).toFixed(2)}%`, msNum(p.n_names)])) };
    }
    if (key === 'letf_cat') {
        const by = ((m.letf_category_share || {}).by_category) || {};
        return { title: '레버·인버스 ETF 분류별 거래대금',
            html: msTable(['분류', '상품 수', '거래대금'],
                Object.entries(by).map(([k, v]) => [finEsc(k), msNum(v.n_products), msJo(v.trading_value_krw)])) };
    }
    if (key === 'letf_products') {
        const stocks = Array.isArray(m.stocks) ? m.stocks : [];
        const sel = stocks.find((x) => x.ticker === MS_STOCK) || stocks[0];
        if (!sel) return null;
        return { title: `${sel.name} 단일종목 ETF 상품별`,
            html: msTable(['상품', '배수', '순자산(AUM)', '거래대금', '방향'],
                (sel.products || []).map((p) => [finEsc(p.name), `${p.L > 0 ? '+' : ''}${p.L}배`,
                    msJo(p.aum), msJo(p.trading_value), p.direction === 'long' ? '롱' : '인버스']))
                + '<p class="fin-note">NAV는 공개 스냅샷에 없습니다. 순자산과 거래대금만 실측입니다.</p>' };
    }
    if (key.startsWith('ev:')) {
        const sym = key.slice(3);
        const e = (t.evidence_us || []).find((x) => x.symbol === sym);
        if (!e) return null;
        return { title: `${sym} — 판정 근거`,
            html: msTable(['항목', '값'], [
                ['P/C 거래량', Number.isFinite(e.put_call_volume) ? e.put_call_volume.toFixed(4) : '—'],
                ['P/C 미결제약정', Number.isFinite(e.put_call_oi) ? e.put_call_oi.toFixed(4) : '—'],
                ['옵션 총 거래량', msNum(e.options_total_volume)],
                ['공매도 잔고 증감', Number.isFinite(e.short_chg_pct) ? `${e.short_chg_pct.toFixed(3)}%` : '—'],
                ['당일 수익률', Number.isFinite(e.day_return) ? msPct(e.day_return, 3) : '—'],
                ['레짐', (e.regimes || []).join(', ')],
                ['스트레스', finEsc(e.stress_level || '')],
            ]) + `<p class="fin-note">${finEsc(e.rule_ko || '')}</p>` };
    }
    if (key.startsWith('ch:')) {
        const c = (t.channels || {})[key.slice(3)] || {};
        return { title: '채널 기여 내역',
            html: msTable(['US', 'KR', 'heat', '연결 유형', 'tier', '레짐'],
                (c.drivers || []).map((d) => [finEsc(d.us), finEsc(d.kr),
                    Number.isFinite(d.heat) ? d.heat.toFixed(3) : '—',
                    finEsc(d.edge_type || ''), finEsc(d.tier || ''), (d.regimes || []).join(', ')]))
            + '<p class="fin-note"><code>etf_beta</code>는 미국 ETF 수익률과 국내 종목의 통계적 연동입니다 — 옵션 포지션이 아닙니다. <code>discovered_corr</code>(tier B)는 상관에서 발견된 것이라 가중이 낮습니다.</p>' };
    }
    if (key === 'alert_letf' || key === 'alert_vix') {
        const a = (D.alerts || {})[key === 'alert_letf' ? 'kr_hynix_letf' : 'us_vix_to_kr'] || {};
        const rows = Object.entries(a)
            .filter(([, v]) => typeof v !== 'object')
            .map(([k, v]) => [finEsc(k), finEsc(String(v))]);
        return { title: key === 'alert_letf' ? '하닉 LETF 알림 임계값' : 'VIX → KR 알림 임계값',
            html: msTable(['항목', '값'], rows) };
    }
    return null;
};

const renderMicrostructure = async (host) => {
    host.innerHTML = `<div class="fin-wrap"><p class="fin-loading">호가 및 유동성 자료를 받는 중…</p></div>`;

    if (!MS_DATA) {
        const keys = Object.keys(MS_FILES);
        const got = await Promise.all(keys.map((k) => msGet(MS_FILES[k])));
        MS_DATA = {};
        keys.forEach((k, i) => { MS_DATA[k] = got[i]; });
    }
    const D = MS_DATA;
    if (!Object.values(D).some(Boolean)) {
        host.innerHTML = finPlaceholder('호가 및 유동성', '수급 불균형 · 가격대별 체결 · 해외-국내 선행',
            '스냅샷 JSON을 찾지 못했습니다. 일일 워크플로가 <code>public/data/</code> 에 산출합니다.');
        return;
    }

    const paint = () => {
        const tab = MS_TABS.find((x) => x.id === MS_TAB) || MS_TABS[0];
        host.innerHTML = `
        <div class="fin-wrap">
            <div class="fin-head">
                <h1>호가 및 유동성</h1>
                <p class="fin-head-en">Market Micro-metrics</p>
                <p>공개·지연 데이터입니다. 값이 없는 항목은 채우지 않고 비워 둡니다. 투자 권유가 아닙니다.</p>
            </div>
            <div class="mm-tabs" role="tablist">
                ${MS_TABS.map((x) => `<button class="mm-tab ${x.id === MS_TAB ? 'on' : ''}" data-ms-tab="${x.id}">${finEsc(x.label)}</button>`).join('')}
            </div>
            <p class="mm-tab-desc">${finEsc(tab.blurb)}</p>
            ${MS_TAB === 'tangle' ? msTangle(D) : MS_TAB === 'levels' ? msLevelsTab(D) : msUsKr(D)}
            ${MS_MODAL ? `
            <div class="ms-modal-back" data-ms-modal-close="1">
                <div class="ms-modal" role="dialog">
                    <div class="ms-modal-head">
                        <h3>${finEsc(MS_MODAL.title)}</h3>
                        <button class="mm-close" data-ms-modal-close="1" aria-label="닫기">✕</button>
                    </div>
                    ${MS_MODAL.html}
                </div>
            </div>` : ''}
        </div>`;

        const on = (sel, fn) => host.querySelectorAll(sel).forEach((b) => b.addEventListener('click', (e) => fn(b, e)));
        on('[data-ms-tab]', (b) => { MS_TAB = b.dataset.msTab; MS_MODAL = null; paint(); });
        on('[data-ms-stock]', (b) => {
            MS_STOCK = b.dataset.msStock;
            // The row's own button doubles as ticker-select + drilldown open,
            // so the modal has to look up the ticker that was just picked.
            if (b.dataset.msModal) MS_MODAL = msModalFor(b.dataset.msModal, D);
            paint();
        });
        on('[data-ms-univ]', (b) => { MS_UNIVERSE = b.dataset.msUniv; paint(); });
        on('[data-ms-ticker]', (b) => { MS_TICKER = b.dataset.msTicker || null; MS_TAB = 'levels'; paint(); });
        // :not([data-ms-stock]) because that combination is handled above --
        // otherwise this listener would double-fire on the same click and
        // paint() twice.
        on('[data-ms-modal]:not([data-ms-stock])', (b) => { MS_MODAL = msModalFor(b.dataset.msModal, D); paint(); });
        on('[data-ms-modal-close]', (b, e) => { if (e.target === b) { MS_MODAL = null; paint(); } });
        mmWireCharts(host);
    };
    paint();
};

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

    const path = (arr) => {
        let dstr = '', pen = false;
        arr.forEach((v, i) => {
            if (!Number.isFinite(v)) { pen = false; return; }
            dstr += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
            pen = true;
        });
        return dstr;
    };

    const line = path(values);
    const first = idx[0][0], last = idx[idx.length - 1][0];
    const area = `${line}L${sx(last).toFixed(1)},${sy(lo).toFixed(1)}L${sx(first).toFixed(1)},${sy(lo).toFixed(1)}Z`;

    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + (hi - lo) * t);
    const xAt = [0, Math.floor((n - 1) / 2), n - 1];

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
            ${ticks.map((t) => `
                <line x1="${MM_L}" y1="${sy(t).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${MM_L - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(t)}</text>`).join('')}
            ${(lo < 0 && hi > 0) ? `<line x1="${MM_L}" y1="${sy(0).toFixed(1)}" x2="${MM_W - MM_R}" y2="${sy(0).toFixed(1)}" class="mm-zero"/>` : ''}
            <path d="${area}" fill="url(#mmg)"/>
            ${ma ? `<path d="${path(ma)}" class="mm-ma"/>` : ''}
            <path d="${line}" class="mm-line"/>
            ${xAt.map((i) => `<text x="${sx(i).toFixed(1)}" y="${MM_H - 8}" class="mm-tick"
                text-anchor="${i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle')}">${finEsc(dates[i] || '')}</text>`).join('')}
            <line class="mm-cross" x1="0" y1="${MM_T}" x2="0" y2="${MM_H - MM_B}" style="display:none"/>
            <circle class="mm-hover-dot" r="4" style="display:none"/>
        </svg>
        <div class="mm-tip-box" style="display:none"></div>
        ${ma ? '<p class="mm-legend-note"><i class="mm-swatch-ma"></i>MA5 (5기간 이동평균)</p>' : ''}
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

// Which panels an indicator can show, in the order they should appear. The
// engine names the primary view (ui.click_view); chart_type covers the rest.
const mmViewsFor = (ind) => {
    const views = [];
    const cv = (ind.ui || {}).click_view;
    const has = (a) => Array.isArray(a) && a.length;

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
    if (view === 'compare') body = mmCompareView(ind);
    else if (view === 'mix') body = mmMixView(ind);
    else if (view === 'outcomes') body = mmOutcomesView(ind);
    else if (view === 'stack') body = mmComponentsView(ind, '연준이 보유한 국채를 잔존만기로 나눈 잔액입니다. 시장금리가 아니라 대차대조표입니다.');
    else if (view === 'components') body = mmComponentsView(ind, ind.chart_type === 'line+components' ? '' : '만기별 발행 구성입니다.');
    else {
        const src = modeSeries || ind;
        const hist = (src.history || {})[MM_CHART.window] || {};
        // VIX and other fear gauges have no moving average by design: a smoothed
        // fear index invites reading a trend into what is meant to be a level.
        body = mmLineChart(hist.dates || [], hist.values || [], {
            ma5: hist.ma5,
            unit: src.unit === 'pct' ? '%' : (src.unit || ''),
            label: src.label_ko || ind.label_ko,
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
                <h3>${finEsc(ind.label_ko)}</h3>
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
                ${ind.note_ko ? `<p class="fin-note mm-note">${finEsc(ind.note_ko)}</p>` : ''}
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
                <button class="mm-headline" data-mm-tab="${finEsc(h.category)}">
                    <span class="mm-headline-label">${finEsc(h.label_ko)}</span>
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
                    <span class="mm-chip-label">${finEsc(ch.label_ko)}</span>
                    <span class="mm-chip-value">${finEsc(ch.display ?? '—')}</span>
                    <span class="mm-chip-foot">
                        ${mmDelta(ch.change_1m_pct)}<span class="mm-chip-win">1M</span>
                        ${mmDelta(ch.change_1y_pct)}<span class="mm-chip-win">1Y</span>
                    </span>
                    ${ch.note_ko ? `<span class="mm-chip-note">${finEsc(ch.note_ko)}</span>` : ''}
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

const openChartModal = async (indicatorTitle) => {
    modalTitle.textContent = `${indicatorTitle} (최근 5년 실데이터)`;
    chartModal.classList.remove('hidden');
    
    // Map indicator title to Yahoo Finance Symbol
    let symbol = "";
    if (indicatorTitle.includes('KRW/USD')) symbol = "KRW=X";
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

    const ctx = document.getElementById('macroChart').getContext('2d');
    
    if (macroChartInstance) {
        macroChartInstance.destroy();
    }
    
    macroChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: indicatorTitle,
                data: data,
                borderColor: '#4ade80',
                borderWidth: 2,
                tension: 0.1,
                pointRadius: pointRadius,
                pointBackgroundColor: pointColors,
                pointBorderColor: '#ffffff',
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            let label = context.parsed.y.toFixed(2);
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
