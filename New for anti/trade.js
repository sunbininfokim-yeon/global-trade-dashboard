// Trade panel logic for Global Trade Dashboard.
//
// Split out of app.js (2026-08-19) because app.js is shared by multiple
// parallel Claude sessions and a long-lived unrelated branch (DART/derivatives/
// company-financials work) had repeatedly squash-merged into main without
// rebasing, silently deleting this trade-panel code from app.js (no conflict
// marker -- squash merges replace whole regions instead of diffing). Moving it
// here removes the collision surface: sessions working on DART/derivatives/
// climate/shipping never touch this file.
//
// Loaded via a <script> tag AFTER app.js (non-module scripts share one global
// scope, so this file's top-level const/let declarations become globally
// visible the same as app.js's do). This file relies on globals still defined
// in app.js: currentCommodity, resolveCountry, countryCode, tooltipEl,
// positionTooltipAt, mapContainer, newsContentEl, newsPanelEl, topExporterEl,
// totalVolumeEl, panelHide, panelShow, countryStatsPanelEl, updateNewsPanel,
// tradeFocusCountry, selectedCountry, deckgl, window.TradeData,
// stopTradeAnim, tradeAnimRaf, tradeAnimPhase, clampGlobeView, currentViewState,
// worldBaseLayers, worldGeo, worldGeoData, featureIsCountry, featureCountryName,
// bowedPath, arcWidth, arcAlpha, MAX_RENDERED_ARCS, generateNodeData,
// TRADE_MAP_VIEW, macroPanelEl, currentViewDesc,
// concentrationHtml, normCountryName, commodityReportsPanelEl. (ISO3_FALLBACK
// stays in app.js, used only by its countryCode helper, which this file calls
// but does not own.)
//
// This is a pure move: no logic was rewritten, only relocated, in the same
// relative order the functions appeared in app.js.

// The right dashboard (rankings, rig count, gas storage, RSS reports) only
// makes sense once a country is focused (stage 2), and even then only for
// commodities that actually have RSS reports for that country -- see
// renderCommodityReports, the only place this is ever flipped back on.
const setRightDashboardVisible = (visible) => {
    const el = document.getElementById('right-pane');
    if (el) el.style.display = visible ? 'flex' : 'none';
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
    // Back to the world view (stage 1) -- no right dashboard here regardless
    // of commodity.
    setRightDashboardVisible(false);
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
    // Hidden until renderCommodityReports (below) confirms this commodity has
    // RSS reports for this country -- otherwise a country switch would flash
    // the previous country's dashboard while the new one is still loading.
    setRightDashboardVisible(false);
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
    // Which Comtrade year these routes are from (the Worker picks the
    // newest complete one), e.g. "2025년 연간".
    const annualLabel = typeof comtradePeriodLabel === 'function' ? comtradePeriodLabel(arcs) : '';
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
        // netWeightMt comes straight off the Comtrade row (data.js); the % bar
        // alone can't distinguish "49.9% of a small trade" from "49.9% of a
        // huge one" -- tonnage is what answers that, so put it one click away
        // instead of burying it in the title-attribute tooltip only.
        const mt = Number.isFinite(a.netWeightMt) && a.netWeightMt > 0 ? a.netWeightMt : null;
        // In a blended year, routes neither end has filed for yet carry the
        // previous year's value; say so on the row.
        const olderYear = a.blendFrom && a.dataYear && a.dataYear !== a.period ? ` · ${a.dataYear}년 값` : '';
        const volLabel = (mt != null
            ? `${a.volume.toLocaleString()} ${unit} · ${mt.toLocaleString(undefined, { maximumFractionDigits: 2 })} Mt`
            : `${a.volume.toLocaleString()} ${unit}`) + olderYear;
        return `<div class="trade-rank-row trade-bar-row${isIn ? ' is-inbound' : ''}"
                     role="button" tabindex="0" data-partner="${partner}"
                     title="${isIn ? '수입' : '수출'} · ${partner} · ${volLabel}">
            <span class="tr-i">${i + 1}</span>
            <span class="tr-dir" aria-label="${isIn ? '수입' : '수출'}"></span>
            <span class="tr-name tr-code">${countryCode(partner)}</span>
            <span class="tr-bar"><i style="width:${Math.max(3, (a.volume / maxVol) * 100)}%"></i></span>
            <span class="tr-pct">${share.toFixed(1)}%</span>
            <span class="tr-vol">${volLabel}</span>
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

    // Which side carries the dependency follows the country's net position.
    // A net exporter's exposure is who it sells to (판로: US soybeans hang on
    // China); a net importer's is who it buys from (공급). This used to show
    // suppliers whenever there was any import at all, so a large exporter with
    // a sliver of imports got a supplier-concentration card about its sliver.
    const netExporter = exportVol >= importVol && exports.length > 0;
    const depHtml = netExporter
        ? concentrationHtml(exports, (a) => a.targetName, '수출 판로', '순수출국 · 수출 대상국 기준')
        : concentrationHtml(imports, (a) => a.sourceName, '수입 공급', '순수입국 · 수입 공급국 기준');

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
                    ${annualLabel ? `<span class="tm-period-badge">${annualLabel}</span>` : ''}
                    <button type="button" class="trade-focus-clear" id="trade-focus-clear">전체 지도</button>
                </div>
                ${subProductsCardHtml(currentCommodity)}
                <div class="tm-annual">
                    <p class="trade-focus-sub">${annualLabel ? `${annualLabel} · ` : ''}수출·수입 양방향 · 비중은 각 방향 내 비중 · 물동량(${unit})</p>
                    ${statsHtml}
                    ${depHtml}
                    <div class="trade-rank-list">${rows || '<p class="empty-state">이 국가 루트 없음</p>'}</div>
                </div>
                <div class="tm-monthly" hidden></div>
            </div>`;
        document.getElementById('trade-focus-clear')?.addEventListener('click', (e) => {
            e.preventDefault();
            clearTradeFocus();
        });
        bindSubProducts(newsContentEl);
        // 연간 / 월별 toggle, only where monthly data exists (trade-monthly.js).
        window.TradeMonthly?.attach(newsContentEl.querySelector('.trade-focus-card'),
            { commodity: currentCommodity, countryName, annualLabel });
    }
    renderRigCountCountry(countryName);
    window.GasStorage?.render(countryName);
    renderCommodityReports(currentCommodity, countryName);

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

    // Export controls live in the 수출통제 모니터 only (2026-10-07), not on
    // a commodity's country card.

    currentViewDesc.textContent = `${displayName} ${roleKo} · ${focused.length}개 루트 · 배경 클릭 또는 「전체 지도」로 초기화`;
    renderMapLayers(arcs, { focus: countryName, asExporter, focused, inboundKeys, keepView: true });
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
 * level alone does not say whether a buffer is filling or draining. Three
 * years of weekly points is long enough to place the current level against
 * a couple of full seasonal drawdown/refill cycles, not just the last one.
 */
const EIA_STOCKS_WEEKS = 156;
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
                `/api/macro?source=eia&route=${encodeURIComponent(s.route)}&seriesId=${s.series}&length=${EIA_STOCKS_WEEKS}`);
            if (!r.ok) continue;
            const j = await r.json();
            const rows = j?.response?.data || j?.data || [];
            if (!rows.length) continue;
            const latest = Number(rows[0]?.value);
            const prev = rows.length > 1 ? Number(rows[1]?.value) : null;
            if (!Number.isFinite(latest)) continue;
            // rows arrive newest-first from EIA; the sparkline wants
            // oldest-first, so reverse after taking the most recent weeks.
            const history = rows.slice(0, EIA_STOCKS_WEEKS)
                .map((row) => ({ period: row.period, value: Number(row.value) }))
                .filter((row) => Number.isFinite(row.value))
                .reverse();
            out.push({
                ...s,
                value: latest,
                period: rows[0]?.period || '',
                change: Number.isFinite(prev) ? latest - prev : null,
                history,
            });
        } catch (err) {
            // The map is the point; a missing buffer card is not worth failing over.
            console.warn(`[EIA] ${s.id} unavailable`, err);
        }
    }
    eiaStocksCache = out;
    return out;
};

/**
 * Baker Hughes drilling rig count -- global monthly total and per-country
 * series, built offline from manually-exported Excel reports (no live API;
 * see scripts/rig_count/build_rig_count_v1.py). A static JSON snapshot next
 * to the app rather than a fetch proxy like the EIA cards above.
 */
let rigCountCache = null;
const loadRigCount = async () => {
    if (rigCountCache) return rigCountCache;
    try {
        const r = await fetch('/public/data/rig_count_v1.json', { cache: 'no-cache' });
        rigCountCache = r.ok ? await r.json() : null;
    } catch (err) {
        console.warn('[Rig count] unavailable', err);
        rigCountCache = null;
    }
    return rigCountCache;
};

// Bumped per chart instance so two sparklines open at once don't fight over
// the same data-* payload -- wireSparkCharts looks its data up by this id.
let sparkChartSeq = 0;
const sparkChartData = new Map();

/**
 * Sparkline with a real y-axis and a hover readout, for a value series in
 * chronological order.
 *
 * A level plus a rising/falling arrow says "falling", not "falling off a
 * cliff over three months" or "still near its year high" -- the shape and the
 * scale are both part of that answer, which a trend-only sparkline (no axis,
 * no hover) could not give. Axis labels sit beside the chart as plain HTML
 * rather than inside the SVG as <text>: this box is stretched to its
 * container with preserveAspectRatio="none" so line and area shapes stay
 * geometrically fine, but any <text> inside the same viewBox would stretch
 * with it and read as squashed or elongated depending on the panel's width.
 *
 * points: [{label, value}] oldest-first. unit/formatValue control how the
 * hover readout and axis labels are worded.
 *
 * shadeFromLabel: optional point label (e.g. a period string like
 * "2024-01") marking where a break in the series' own methodology sits.
 * Highlights a short band starting there, wide enough to catch the eye at
 * that one point without implying the difference is still ongoing --
 * everything after it is real values under the new methodology, not a
 * continued anomaly. shadeSpanPoints controls how many points wide that
 * band is (default: to the right edge, for a genuinely open-ended break).
 */
const sparkChartHtml = ({ points, unit, formatValue, ariaLabel, footNote, shadeFromLabel, shadeSpanPoints }) => {
    if (!points || points.length < 2) return '';
    const W = 100, H = 54, PAD = 3;
    const vals = points.map((p) => p.value);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    // A flat series must not divide by zero, and drawing it mid-height is
    // more honest than pinning it to the top or bottom of the box.
    const span = max - min || 1;
    const x = (i) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
    const y = (v) => PAD + (1 - (v - min) / span) * (H - PAD * 2);
    const fmt = formatValue || ((v) => String(v));

    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(p.value).toFixed(2)}`).join('');
    const area = `${line}L${x(points.length - 1).toFixed(2)},${H - PAD}L${x(0).toFixed(2)},${H - PAD}Z`;
    const last = points[points.length - 1];
    const rising = last.value >= points[0].value;

    // First point at or after the break, not the closest one either side --
    // an exact label match always exists here (both callers pass the same
    // "2024-01" the series itself is built from), but rounding to "at or
    // after" keeps this from silently drawing nothing if that ever drifts.
    const shadeIdx = shadeFromLabel
        ? points.findIndex((p) => p.label >= shadeFromLabel)
        : -1;
    // A single point's width is 0px, so a 1-point-wide band would be
    // invisible -- floor it to one point-to-point gap either way.
    const pointGap = (W - PAD * 2) / Math.max(1, points.length - 1);
    const shadeWidth = shadeIdx > 0
        ? Math.min(W - PAD - x(shadeIdx), Math.max(pointGap, pointGap * (shadeSpanPoints ?? (points.length - shadeIdx))))
        : 0;
    const shadeRect = shadeIdx > 0
        ? `<rect class="spark2-shade" x="${x(shadeIdx).toFixed(2)}" y="${PAD}"
               width="${shadeWidth.toFixed(2)}" height="${H - PAD * 2}"/>`
        : '';

    const id = `spk${++sparkChartSeq}`;
    sparkChartData.set(id, { points, x, y, unit: unit || '', fmt });

    return `<div class="spark2-wrap">
        <div class="spark2-row">
            <div class="spark2-axis">
                <span>${fmt(max)}</span>
                <span>${fmt(min)}</span>
            </div>
            <div class="spark2-chart" data-spark-id="${id}">
                <svg viewBox="0 0 ${W} ${H}" class="spark2-svg ${rising ? 'up' : 'down'}"
                     preserveAspectRatio="none" role="img" aria-label="${ariaLabel || ''}">
                    <line class="spark2-grid" x1="${PAD}" y1="${PAD}" x2="${W - PAD}" y2="${PAD}"/>
                    <line class="spark2-grid" x1="${PAD}" y1="${H - PAD}" x2="${W - PAD}" y2="${H - PAD}"/>
                    ${shadeRect}
                    <path class="spark2-area" d="${area}"/>
                    <path class="spark2-line" d="${line}" vector-effect="non-scaling-stroke"/>
                    <path class="spark2-dot-end" d="M${x(points.length - 1).toFixed(2)},${y(last.value).toFixed(2)}h0"/>
                    <line class="spark2-cross" x1="0" y1="${PAD}" x2="0" y2="${H - PAD}" style="display:none"/>
                    <path class="spark2-dot-hover" d="M0,0h0" style="display:none"/>
                </svg>
                <div class="spark2-tip" style="display:none"></div>
            </div>
        </div>
        <div class="spark2-foot">
            <span>${points[0].label}</span>
            ${footNote ? `<span class="spark2-footnote">${footNote}</span>` : ''}
            <span>${last.label}</span>
        </div>
    </div>`;
};

/**
 * Attaches hover tracking to every `.spark2-chart` under `root`. Call once
 * after inserting HTML built with sparkChartHtml -- innerHTML replacement
 * drops any listeners the previous copy had.
 */
const wireSparkCharts = (root = document) => {
    root.querySelectorAll('.spark2-chart[data-spark-id]').forEach((box) => {
        const data = sparkChartData.get(box.dataset.sparkId);
        const svg = box.querySelector('svg');
        const cross = box.querySelector('.spark2-cross');
        const dot = box.querySelector('.spark2-dot-hover');
        const tip = box.querySelector('.spark2-tip');
        if (!data || !svg || !cross || !dot || !tip) return;

        const hide = () => { cross.style.display = 'none'; dot.style.display = 'none'; tip.style.display = 'none'; };

        box.addEventListener('mousemove', (e) => {
            const r = box.getBoundingClientRect();
            if (!r.width) return;
            const t = (e.clientX - r.left) / r.width;
            const i = Math.max(0, Math.min(data.points.length - 1, Math.round(t * (data.points.length - 1))));
            const p = data.points[i];
            const px = data.x(i), py = data.y(p.value);
            cross.setAttribute('x1', px); cross.setAttribute('x2', px);
            cross.style.display = '';
            dot.setAttribute('d', `M${px.toFixed(2)},${py.toFixed(2)}h0`);
            dot.style.display = '';
            tip.innerHTML = `<span class="spark2-tip-date">${p.label}</span>`
                + `<span class="spark2-tip-val">${data.fmt(p.value)}${data.unit}</span>`;
            tip.style.display = '';
            // Flip before the tooltip would run off either edge of the box.
            const leftPct = (px / 100) * 100;
            tip.style.left = `${Math.min(Math.max(leftPct, 4), 96)}%`;
            tip.classList.toggle('is-right', leftPct > 60);
        });
        box.addEventListener('mouseleave', hide);
    });
};

/** Only meaningful for crude; other commodities have no equivalent series. */
const renderEmergencyStocks = async () => {
    const host = document.getElementById('news-content');
    if (!host || currentCommodity !== 'oil') return;
    const stocks = await loadEiaStocks();
    if (!stocks.length || currentCommodity !== 'oil') return;
    // renderTradeWorldPanel can call this more than once before the first
    // call's await resolves (e.g. a second data refresh landing mid-fetch);
    // each call is otherwise appending, not replacing, so drop any card a
    // previous call already left behind instead of stacking a duplicate.
    host.querySelector('.stock-card')?.remove();
    const weeks = stocks[0]?.history?.length || 0;
    // 156 weekly points reads as "156주" if spelled out literally -- round to
    // years once there's enough of them to actually span some, and only fall
    // back to a week count for a series EIA hasn't reported that far back for.
    const span = weeks >= 104 ? `${Math.round(weeks / 52)}년` : `${weeks}주`;
    host.insertAdjacentHTML('beforeend', `
        <div class="stock-card">
            <p class="section-title" style="margin:0 0 6px;">글로벌 비상 재고 · EIA 주간</p>
            ${stocks.map((s) => {
                const up = s.change != null && s.change > 0;
                const stockSpan = s.history.length >= 104
                    ? `${Math.round(s.history.length / 52)}년` : `${s.history.length}주`;
                const chart = sparkChartHtml({
                    points: s.history.map((h) => ({ label: h.period, value: h.value / 1000 })),
                    unit: 'M bbl',
                    formatValue: (v) => v.toFixed(1),
                    ariaLabel: `최근 ${stockSpan} 추이`,
                });
                return `<div class="stock-item">
                    <div class="stock-row${chart ? ' is-clickable' : ''}"
                         ${chart ? `role="button" tabindex="0" data-stock-toggle="${s.id}"` : ''}>
                        <span class="nm">${s.label_ko}${chart ? '<i class="stock-caret"></i>' : ''}</span>
                        <span class="vl">${(s.value / 1000).toFixed(1)}<em>백만 배럴</em></span>
                        <span class="ch ${s.change == null ? '' : (up ? 'up' : 'down')}">
                            ${s.change == null ? '—'
                                : `${up ? '+' : ''}${(s.change / 1000).toFixed(1)}`}</span>
                    </div>
                    ${chart}
                </div>`;
            }).join('')}
            <div class="stock-note">${stocks[0]?.period || ''} 기준 · 전주 대비 증감 · 이름을 누르면 최근 ${span} 추이(그래프 위에 마우스를 올리면 날짜·수량) · 출처 EIA</div>
        </div>`);
    wireSparkCharts(host);
};

/**
 * Global monthly rig count, world view -- directly below the SPR/Cushing
 * card. Called only after renderEmergencyStocks() has resolved (see the
 * `.then()` chain in renderTradeWorldPanel below): both cards insert with
 * `insertAdjacentHTML('beforeend', ...)`, so without that ordering this
 * card's local-JSON fetch (fast) could easily land before the SPR card's
 * live EIA proxy fetch (slower) and print above it instead of below.
 */
const renderRigCountWorld = async () => {
    const host = document.getElementById('news-content');
    if (!host || currentCommodity !== 'oil') return;
    const rig = await loadRigCount();
    if (!rig?.global?.length || currentCommodity !== 'oil') return;
    // Same idempotency guard the SPR/Cushing card needed after a real
    // production bug (a second world-panel render landing mid-fetch would
    // otherwise stack a duplicate card here too).
    host.querySelector('.rig-card')?.remove();
    const last = rig.global[rig.global.length - 1];
    // Baker Hughes changed how it counts Saudi Arabia partway through this
    // series (see build_rig_count_v1.py); the global total inherits that
    // jump. Shaded on the chart itself, not just noted below it, so the
    // level jump doesn't read as a sudden real drilling boom at a glance.
    const saudiNote = (rig.data_quality_notes || []).some((n) => n.includes('Saudi Arabia'));
    const chart = sparkChartHtml({
        points: rig.global.map((p) => ({ label: p.period, value: p.value })),
        unit: '기',
        formatValue: (v) => v.toFixed(0),
        ariaLabel: `${rig.global.length}개월 글로벌 Rig 수 추이`,
        shadeFromLabel: saudiNote ? '2024-01' : null,
        shadeSpanPoints: saudiNote ? 2 : undefined,
    });
    host.insertAdjacentHTML('beforeend', `
        <div class="rig-card">
            <p class="section-title" style="margin:0 0 6px;">글로벌 Rig 수 · Baker Hughes 월간</p>
            <div class="stock-item">
                <div class="stock-row">
                    <span class="nm">가동 리그 수</span>
                    <span class="vl">${last.value.toLocaleString()}<em>기</em></span>
                </div>
                ${chart}
            </div>
            <div class="stock-note">${last.period} 기준 · 출처 Baker Hughes${saudiNote
                ? ' · 사우디아라비아 2024년경 집계 방식 변경(Active Rigs → Operating Rigs)으로 전체 합계에 단절 있음 — 실제 시추 급증 아님'
                : ''}</div>
        </div>`);
    wireSparkCharts(host);
};

/**
 * Rig-count sparkline for the country focus panel (country view). Baker
 * Hughes covers roughly 90 countries; most focused countries have no series
 * here and that is a normal, silent no-op, not an error.
 */
const renderRigCountCountry = async (countryName) => {
    const host = document.getElementById('news-content');
    if (!host || currentCommodity !== 'oil') return;
    const target = resolveCountry(countryName);
    const rig = await loadRigCount();
    // The focus panel may have moved on to a different country (or the user
    // left the trade view, or switched commodity) while this fetch was in
    // flight -- a stale country's card landing inside whatever the panel now
    // shows is the exact bug the SPR/Cushing card shipped once already.
    if (currentCommodity !== 'oil' || tradeFocusCountry !== countryName) return;
    const card = host.querySelector('.trade-focus-card');
    card?.querySelector('.rig-card')?.remove();
    if (!card || !target || !rig?.by_country) return;
    // Identity match, not a raw key lookup: by_country's keys are built to
    // already equal resolveCountry(...).label, but comparing by .key (the
    // same pattern focusTradeCountry itself uses) survives that assumption
    // ever drifting instead of silently going blank.
    const entry = Object.entries(rig.by_country)
        .find(([name]) => resolveCountry(name)?.key === target.key);
    const series = entry?.[1];
    if (!series || series.length < 2) return;
    const last = series[series.length - 1];
    const saudiNote = target.key === 'Saudi Arabia'
        && (rig.data_quality_notes || []).some((n) => n.includes('Saudi Arabia'));
    const chart = sparkChartHtml({
        points: series.map((p) => ({ label: p.period, value: p.value })),
        unit: '기',
        formatValue: (v) => v.toFixed(0),
        ariaLabel: `${series.length}개월 ${target.label} Rig 수 추이`,
        shadeFromLabel: saudiNote ? '2024-01' : null,
        shadeSpanPoints: saudiNote ? 2 : undefined,
    });
    card.insertAdjacentHTML('beforeend', `
        <div class="rig-card">
            <p class="section-title" style="margin:0 0 6px;">${target.label} Rig 수 · Baker Hughes 월간</p>
            <div class="stock-item">
                <div class="stock-row">
                    <span class="nm">가동 리그 수</span>
                    <span class="vl">${last.value.toLocaleString()}<em>기</em></span>
                </div>
                ${chart}
            </div>
            <div class="stock-note">${last.period} 기준 · 출처 Baker Hughes${saudiNote
                ? ' · 2024년경 집계 방식 변경(Active Rigs → Operating Rigs)으로 이 시점에 단절 있음 — 실제 시추 급증 아님'
                : ''}</div>
        </div>`);
    wireSparkCharts(card);
};

// A country's export total and import total are different questions --
// Australia sells the most iron ore, China buys the most. Ranking only
// exporters used to hide the second answer entirely: China's ~$2B of
// re-export/border trade put it at #6 on the exporter list while its
// $128B+ of actual imports (the far bigger, more important number) never
// appeared anywhere on this screen.
const rankPartners = (arcs, side) => {
    const byCountry = new Map();
    for (const a of arcs) {
        if (!(a.volume > 0)) continue;
        const raw = side === 'export' ? a.sourceName : a.targetName;
        const key = resolveCountry(raw)?.label || raw;
        byCountry.set(key, (byCountry.get(key) || 0) + a.volume);
    }
    const ranked = [...byCountry.entries()].sort((x, y) => y[1] - x[1]);
    const total = ranked.reduce((s, [, v]) => s + v, 0) || 1;
    const max = ranked[0]?.[1] || 1;
    return { ranked, total, max };
};

const worldRankRows = ({ ranked, total, max }, n = 10) => ranked.slice(0, n).map(([name, vol], i) => {
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

/**
 * Official reports published about the commodity on screen -- and, in the
 * country view, about that country's side of it.
 *
 * Phase 2-2. The agencies that actually move these markets (USDA, CONAB,
 * FAO, EIA…) publish dozens of releases a day, and until now none of them
 * reached the screen where they would mean something. The pipeline in
 * scripts/commodity_reports tags each release with the commodity and the
 * country its *text* is about, not the one that published it: a USDA release
 * on Brazilian wheat is a Brazil·밀 report, and lands here when Brazil is the
 * focused country on the wheat map.
 *
 * Headline-and-link, deliberately. These are copyrighted publications; the
 * card quotes what the feed itself syndicates and sends the reader to the
 * agency's own page for the rest, the same posture the news ticker takes.
 */

// Feed text is written by whoever published it -- it reaches this file
// unescaped from an RSS body and goes straight into innerHTML.
const escapeFeedText = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

// Same reason: a javascript: or data: href out of a hijacked feed would run
// on click. Only http(s) links become anchors; anything else renders as text.
const safeReportHref = (raw) => {
    try {
        const u = new URL(String(raw), window.location.origin);
        return (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : null;
    } catch (_) {
        return null;
    }
};

// Reports keyed by `${commodity}|${iso3 or ''}`. The panel re-renders on every
// map interaction and the answer only changes when the pipeline reruns.
const commodityReportCache = new Map();
// The whole snapshot, fetched at most once, for the local static server and
// any deploy where /api is not in front of the assets (the Worker owns /api;
// a plain file server answers 404 there, which is normal, not an error).
let commodityReportSnapshot;

const loadCommodityReportSnapshot = async () => {
    if (commodityReportSnapshot !== undefined) return commodityReportSnapshot;
    try {
        const res = await fetch('/public/data/commodity_reports_v1.json', { cache: 'no-cache' });
        commodityReportSnapshot = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn('[commodity-reports] snapshot unavailable', err);
        commodityReportSnapshot = null;
    }
    return commodityReportSnapshot;
};

/**
 * Resolve one window out of the raw snapshot.
 *
 * Mirrors what the Worker's /api/commodity-reports does, so the static
 * fallback shows the same rows in the same order rather than a second,
 * subtly different ranking: the country's own reports first, then the world
 * balance sheets every country on that commodity inherits.
 */
const reportsFromSnapshot = (doc, commodity, iso3) => {
    const buckets = doc?.index?.[commodity];
    if (!buckets) return [];
    const byId = new Map((doc.items || []).map((it) => [it.id, it]));
    const ids = [];
    const push = (list) => (list || []).forEach((id) => { if (!ids.includes(id)) ids.push(id); });
    if (iso3) push(buckets[iso3]);
    push(buckets._global);
    if (!iso3) Object.entries(buckets).forEach(([b, rows]) => { if (b !== '_global') push(rows); });
    return ids.map((id) => byId.get(id)).filter(Boolean);
};

// A window keeps everything inside the pipeline's archive horizon -- no fixed
// count -- so the panel fetches it a chunk at a time and asks for the next
// chunk when the reader pages past the last one it has.
const REPORTS_CHUNK = 60;

/** One chunk of a window: { items, label, total } (total = the whole window). */
const fetchReportsChunk = async (commodity, iso3, offset, limit = REPORTS_CHUNK) => {
    try {
        const q = new URLSearchParams({ commodity, limit: String(limit), offset: String(offset) });
        if (iso3) q.set('country', iso3);
        const res = await fetch(`/api/commodity-reports?${q}`);
        if (res.ok) {
            const doc = await res.json();
            const items = doc.items || [];
            // A Worker from before `total` existed answers one capped page.
            const total = Number.isFinite(doc.total) ? doc.total : offset + items.length;
            return { items, label: doc.commodity_label || commodity, total };
        }
    } catch (err) {
        console.warn('[commodity-reports] api unavailable, falling back to snapshot', err);
    }
    const doc = await loadCommodityReportSnapshot();
    const all = reportsFromSnapshot(doc, commodity, iso3);
    return {
        items: all.slice(offset, offset + limit),
        label: doc?.commodity_labels?.[commodity] || commodity,
        total: all.length,
    };
};

const loadCommodityReports = async (commodity, iso3) => {
    const key = `${commodity}|${iso3 || ''}`;
    if (commodityReportCache.has(key)) return commodityReportCache.get(key);
    const first = await fetchReportsChunk(commodity, iso3, 0);
    // `breaks`: where each later chunk starts. Pages never straddle one, so
    // fetching a chunk adds pages after the last instead of re-cutting it.
    const window_ = { commodity, iso3, ...first, breaks: [], loading: null };
    commodityReportCache.set(key, window_);
    return window_;
};

/** Append the window's next chunk in place; resolves once it has landed. */
const loadMoreReports = (window_) => {
    if (window_.items.length >= window_.total) return Promise.resolve();
    if (!window_.loading) {
        window_.loading = fetchReportsChunk(window_.commodity, window_.iso3, window_.items.length)
            .then((next) => {
                const seen = new Set(window_.items.map((it) => it.id));
                const fresh = next.items.filter((it) => !seen.has(it.id));
                if (fresh.length) window_.breaks.push(window_.items.length);
                window_.items.push(...fresh);
                // An empty chunk means the snapshot moved under us; stop asking.
                window_.total = fresh.length ? Math.max(next.total, window_.items.length) : window_.items.length;
            })
            .finally(() => { window_.loading = null; });
    }
    return window_.loading;
};

// "2026-08-12T16:00:00+00:00" -> "2026.08.12". Some of these feeds (NASS's
// ASB/news syndication) return a rolling archive years deep, not just this
// week -- dropping the year made a 2020 notice and a 2026 one look identical.
// A dateless list-page row shows nothing rather than a fabricated today.
// A GAIN page that carries no date is placed by the /YYYY/MM/ in its URL
// (published_precision "month"); printing its day would invent one.
const reportDate = (iso, precision) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const ym = `${d.getUTCFullYear()}.${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
    if (precision === 'month') return ym;
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
};

// Long enough that the two-line clamp actually hides something worth opening.
const SUMMARY_EXPAND_CHARS = 110;

// Representative products inside one HS line (data.js TradeData[c].
// subProducts -- 경질유 271012: 납사, 휘발유). The trade map cannot split
// them, so the view lists them, badges each report with the one it is about,
// and lets the reader narrow the reports to one.
const subProductsOf = (commodity) => window.TradeData?.[commodity]?.subProducts || null;
const subProductRegexes = new Map();
const subProductOf = (item, commodity) => {
    const subs = subProductsOf(commodity);
    if (!subs?.length) return null;
    const text = [item.title?.original, item.title?.en, item.title?.ko, item.summary].filter(Boolean).join(' ');
    return subs.find((sp) => {
        if (!subProductRegexes.has(sp.match)) subProductRegexes.set(sp.match, new RegExp(sp.match, 'i'));
        return subProductRegexes.get(sp.match).test(text);
    }) || null;
};
// { commodity, id } -- a filter only applies on the commodity it was set on.
let reportsSubFilter = null;
const activeSubFilter = () => (reportsSubFilter && reportsSubFilter.commodity === currentCommodity
    && subProductsOf(currentCommodity) ? reportsSubFilter.id : null);

const subProductsCardHtml = (commodity) => {
    const subs = subProductsOf(commodity);
    if (!subs?.length) return '';
    const on = activeSubFilter();
    return `<div class="subprod-card">
        <p class="trade-rank-group-head">세부 품목</p>
        ${subs.map((sp) => `<button type="button" class="subprod-row${on === sp.id ? ' is-on' : ''}" data-sub="${escapeFeedText(sp.id)}" aria-pressed="${on === sp.id}">
            <strong>${escapeFeedText(sp.label)}</strong><span>${escapeFeedText(sp.desc || '')}</span>
        </button>`).join('')}
        <p class="subprod-note">무역 통계는 품목 구분 없이 합산 · 품목을 누르면 국가별 보고서를 그 품목만 봅니다</p>
    </div>`;
};

const bindSubProducts = (host) => {
    host?.querySelectorAll('.subprod-row[data-sub]').forEach((btn) => {
        btn.addEventListener('click', () => setReportsSubFilter(btn.dataset.sub));
    });
};

const setReportsSubFilter = async (id) => {
    const commodity = currentCommodity;
    reportsSubFilter = activeSubFilter() === id ? null : { commodity, id };
    const on = activeSubFilter();
    document.querySelectorAll('.subprod-row[data-sub]').forEach((b) => {
        b.classList.toggle('is-on', b.dataset.sub === on);
        b.setAttribute('aria-pressed', String(b.dataset.sub === on));
    });
    const pager = reportsPager;
    if (!pager) return;
    if (on) {
        // A filter reads the whole window, not just the chunks paged so far.
        while (pager.win.items.length < pager.win.total) {
            const before = pager.win.items.length;
            try { await loadMoreReports(pager.win); } catch (_) { break; }
            if (pager.win.items.length === before) break;
        }
    }
    if (reportsPager !== pager || currentCommodity !== commodity) return;
    pager.firstShown = 0;
    paintReportsPage();
};

const reportRowHtml = (item) => {
    const href = safeReportHref(item.url);
    const title = escapeFeedText(item.title?.ko || item.title?.original || '');
    const agency = escapeFeedText(item.agency_ko || item.agency || '');
    // The publisher's own site (pipeline: agency_url) -- the title links the report.
    const agencyHref = item.agency_url ? safeReportHref(item.agency_url) : null;
    const summary = String(item.summary || '').trim();
    const date = reportDate(item.published_at, item.published_precision);
    // A world balance sheet sitting on a country's board should say so --
    // otherwise "world wheat production at a record" reads as a claim about
    // the country whose window it is on.
    const scopeTag = item.scope === 'global'
        ? '<span class="rpt-scope">세계</span>'
        : '';
    const sub = subProductOf(item, currentCommodity);
    const subTag = sub ? `<span class="rpt-sub">${escapeFeedText(sub.label)}</span>` : '';
    const series = item.series_label_ko
        ? `<span class="rpt-series">${escapeFeedText(item.series_label_ko)}</span>`
        : '';
    const head = href
        ? `<a class="rpt-title" href="${escapeFeedText(href)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span class="rpt-title">${title}</span>`;
    const body = summary
        ? `<p class="rpt-summary${summary.length > SUMMARY_EXPAND_CHARS ? ' is-clamped' : ''}">${escapeFeedText(summary)}</p>`
          + (summary.length > SUMMARY_EXPAND_CHARS
              ? '<button type="button" class="rpt-more" aria-expanded="false">요약 더보기</button>'
              : '')
        : '';
    return `<li class="rpt-item">
        <div class="rpt-meta">
            ${agencyHref
                ? `<a class="rpt-agency" href="${escapeFeedText(agencyHref)}" target="_blank" rel="noopener noreferrer" title="발간처 사이트로 이동">${agency}</a>`
                : `<span class="rpt-agency">${agency}</span>`}${series}${subTag}${scopeTag}
            ${date ? `<span class="rpt-date">${date}</span>` : ''}
        </div>
        ${head}
        ${body}
    </li>`;
};

/**
 * Fill the standalone reports panel (right pane, #commodity-reports-panel).
 * `countryName` null means the world view.
 *
 * Renders into a slot the panel HTML already reserved rather than appending,
 * so a slow fetch can never land between other cards -- the ordering bug the
 * rig-count cards had to be chained to avoid. The panel is its own right-pane
 * section (not stacked under the trade ranking) so a busy day's reports don't
 * push the ranking below the fold.
 */
// Paging state for the reports panel: which window is on screen, its rows,
// and the page being read. Rebuilt whenever renderCommodityReports runs.
let reportsPager = null;

// Space the heading, the pager and the source note take around the list.
const REPORTS_CHROME_PX = 96;
const REPORTS_MIN_LIST_PX = 220;
const REPORTS_MAX_PER_PAGE = 10;

/**
 * Split the rows into pages that fit the panel as the reader's screen has it.
 *
 * Rows differ in height (one-line headline vs. headline + two-line summary),
 * so a fixed "N per page" either leaves a gap or pushes the pager below the
 * fold. The rows are laid out once, off screen, at the panel's real width,
 * and each page takes as many as fit the height left in the right pane.
 */
const paginateReports = (slot, items, breaks = []) => {
    const pane = document.getElementById('right-pane');
    const top = pane ? slot.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop : 0;
    const paneH = pane ? pane.clientHeight : window.innerHeight;
    const avail = Math.max(REPORTS_MIN_LIST_PX, paneH - top - REPORTS_CHROME_PX);

    const probe = document.createElement('ul');
    probe.className = 'rpt-list';
    probe.style.cssText = `position:absolute;visibility:hidden;left:-9999px;top:0;width:${slot.clientWidth || 300}px;`;
    probe.innerHTML = items.map(reportRowHtml).join('');
    slot.appendChild(probe);
    const heights = [...probe.children].map((li) => li.getBoundingClientRect().height || 72);
    probe.remove();

    const pages = [];
    const cut = new Set(breaks);
    let cur = [];
    let used = 0;
    items.forEach((_, i) => {
        const h = heights[i];
        if (cur.length && (cut.has(i) || used + h > avail || cur.length >= REPORTS_MAX_PER_PAGE)) {
            pages.push(cur);
            cur = [];
            used = 0;
        }
        cur.push(i);
        used += h;
    });
    if (cur.length) pages.push(cur);
    return pages;
};

// "‹ 1 2 3 4 … 9 ›": every page when there are few, else the first, the last
// and the two around the current one. `hasMore` means the window holds more
// than has been fetched: "›" stays live on the last page and fetches it.
const reportsPagerHtml = (count, current, hasMore = false) => {
    if (count <= 1 && !hasMore) return '';
    const shown = new Set([0, count - 1, current - 1, current, current + 1]);
    const parts = [];
    let gap = false;
    for (let p = 0; p < count; p += 1) {
        if (count <= 7 || shown.has(p)) {
            parts.push(`<button type="button" class="rpt-page${p === current ? ' is-on' : ''}" data-page="${p}"
                ${p === current ? 'aria-current="page"' : ''} aria-label="${p + 1}페이지">${p + 1}</button>`);
            gap = false;
        } else if (!gap) {
            parts.push('<span class="rpt-page-gap">…</span>');
            gap = true;
        }
    }
    if (hasMore) parts.push('<span class="rpt-page-gap" title="이전 보고서가 더 있습니다">…</span>');
    return `<nav class="rpt-pager" aria-label="보고서 페이지">
        <button type="button" class="rpt-page rpt-page-step" data-page="${current - 1}" ${current === 0 ? 'disabled' : ''} aria-label="이전 페이지">‹</button>
        ${parts.join('')}
        <button type="button" class="rpt-page rpt-page-step" data-page="${current + 1}" ${current === count - 1 && !hasMore ? 'disabled' : ''} aria-label="다음 페이지">›</button>
    </nav>`;
};

const paintReportsPage = () => {
    const live = document.getElementById('reports-slot');
    if (!live || !reportsPager) return;
    const { win, label, who } = reportsPager;
    const { total } = win;
    const subId = activeSubFilter();
    const subLabel = subId ? subProductsOf(currentCommodity).find((sp) => sp.id === subId)?.label : null;
    // A sub-product filter narrows the rows; paging then runs over those.
    const items = subId ? win.items.filter((it) => subProductOf(it, currentCommodity)?.id === subId) : win.items;
    const hasMore = !subId && items.length < total;
    if (!items.length) {
        live.innerHTML = `<div class="rpt-card">
            <p class="section-title" style="margin:0 0 6px;">${escapeFeedText(who)}${escapeFeedText(label)} 주요 보고서</p>
            <p class="empty-state">최근 12주 ${escapeFeedText(subLabel || '')} 관련 보고서가 없습니다 · 「세부 품목」에서 다시 누르면 전체 보기</p>
        </div>`;
        return;
    }
    const pages = paginateReports(live, items, subId ? [] : win.breaks);
    // Keep the reader on the same reports after a resize re-cuts the pages.
    const anchor = reportsPager.firstShown ?? 0;
    let page = pages.findIndex((idx) => idx.includes(anchor));
    if (page < 0) page = 0;
    reportsPager.page = page;
    reportsPager.firstShown = pages[page][0];
    const rows = pages[page].map((i) => reportRowHtml(items[i])).join('');
    live.innerHTML = `
        <div class="rpt-card">
            <p class="section-title" style="margin:0 0 6px;">${escapeFeedText(who)}${escapeFeedText(label)} 주요 보고서</p>
            <ul class="rpt-list">${rows}</ul>
            ${reportsPagerHtml(pages.length, page, hasMore)}
            <p class="rpt-note">공식 기관 발표 · 최근 12주 ${subLabel ? `${escapeFeedText(subLabel)} ${items.length}건 (전체 ${total}건)` : `총 ${total}건`} · 제목을 누르면 발간처 원문으로 이동</p>
        </div>`;

    live.querySelectorAll('.rpt-more').forEach((btn) => {
        btn.addEventListener('click', () => {
            const body = btn.previousElementSibling;
            const opened = body?.classList.toggle('is-clamped') === false;
            btn.setAttribute('aria-expanded', String(opened));
            btn.textContent = opened ? '요약 접기' : '요약 더보기';
        });
    });
    live.querySelectorAll('.rpt-page[data-page]').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const target = Number(btn.dataset.page);
            if (!Number.isInteger(target) || target < 0) return;
            if (target >= pages.length) {
                // Past the last fetched page: pull the next chunk, then open
                // on its first report.
                if (!hasMore) return;
                const pager = reportsPager;
                const from = items.length;
                btn.disabled = true;
                btn.textContent = '…';
                try {
                    await loadMoreReports(win);
                } catch (err) {
                    console.warn('[commodity-reports] next chunk failed', err);
                }
                if (reportsPager !== pager) return;
                if (win.items.length > from) pager.firstShown = from;
                paintReportsPage();
            } else {
                reportsPager.firstShown = pages[target][0];
                paintReportsPage();
            }
            live.querySelector('.rpt-card')?.scrollIntoView({ block: 'nearest' });
        });
    });
};

let reportsResizeTimer = null;
window.addEventListener('resize', () => {
    clearTimeout(reportsResizeTimer);
    reportsResizeTimer = setTimeout(paintReportsPage, 150);
});

/**
 * Fill the standalone reports panel (right pane, #commodity-reports-panel).
 * `countryName` null means the world view.
 *
 * Renders into a slot the panel HTML already reserved rather than appending,
 * so a slow fetch can never land between other cards -- the ordering bug the
 * rig-count cards had to be chained to avoid. The panel is its own right-pane
 * section (not stacked under the trade ranking) so a busy day's reports don't
 * push the ranking below the fold.
 *
 * The window carries every report of the last 12 weeks; the panel shows as
 * many as fit the reader's screen, pages through the rest (1 2 3 4 …), and
 * fetches further chunks when the reader pages past what it has.
 */
const renderCommodityReports = async (commodity, countryName = null) => {
    const slot = document.getElementById('reports-slot');
    if (!slot || !commodity) return;
    const iso3 = countryName ? countryCode(countryName) : null;
    // Country boxes for pipeline boards. Empty since 2026-10-07: China's
    // export-control notices moved to the 수출통제 모니터, the only place
    // export controls are shown.
    const boardSpec = REPORT_BOARDS_BY_COUNTRY[iso3] || null;
    const [win, board] = await Promise.all([
        loadCommodityReports(commodity, iso3),
        boardSpec ? loadReportBoard(boardSpec) : Promise.resolve(null),
    ]);
    const { items, label } = win;

    // The panel may have been rebuilt, the commodity switched, or the focus
    // moved to another country while this was in flight.
    const live = document.getElementById('reports-slot');
    if (!live || currentCommodity !== commodity) return;
    if (countryName ? tradeFocusCountry !== countryName : tradeFocusCountry !== null) return;
    const boardItems = board?.items || [];
    renderReportBoard(boardSpec, boardItems);
    if (!items.length && boardItems.length) {
        // China with no report on this commodity still has its export-control
        // notices: show the panel for them alone.
        live.innerHTML = '';
        reportsPager = null;
        if (countryName) setRightDashboardVisible(true);
        panelShow(commodityReportsPanelEl);
        return;
    }
    if (!items.length) {
        live.innerHTML = '';
        reportsPager = null;
        panelHide(commodityReportsPanelEl);
        // Stage 2, no RSS for this commodity+country -- no right dashboard at
        // all, not just an empty reports card (world view already has none).
        if (countryName) setRightDashboardVisible(false);
        return;
    }

    // This commodity+country has RSS reports -- open the right dashboard now
    // (rankings/rig count/gas storage were already rendered synchronously in
    // focusTradeCountry, just hidden until this resolved).
    if (countryName) setRightDashboardVisible(true);
    panelShow(commodityReportsPanelEl);
    const who = countryName ? `${resolveCountry(countryName)?.label || countryName} · ` : '';
    reportsPager = { win, label, who, page: 0, firstShown: 0 };
    paintReportsPage();
};

// Boards (pipeline "boards"): lists a source feeds whatever the commodity,
// shown on that country's screen above its reports. MOFCOM's export-control
// bureau posts entity-list additions, countermeasures and control-list
// notices that name no traded commodity, so they would never reach a
// commodity window -- but they are the news for anyone trading with China.
// The pipeline's export_controls board is every regulator's notices; a
// country's screen shows its own regulators' (control.issuer).
const REPORT_BOARDS_BY_COUNTRY = {};
// control.measure (pipeline gemini.MEASURES) in Korean.
const CONTROL_MEASURE_KO = {
    entity_list: '통제명단', export_restriction: '수출통제', export_ban: '수출금지',
    sanctions: '제재', countermeasure: '반제재', list_adjustment: '목록조정',
    suspension: '유예·해제', enforcement: '단속', dialogue: '대화·협의', guidance: '안내',
};
const REPORT_BOARD_SHOWN = 3;
const REPORT_BOARD_FETCH = 30;
const reportBoardCache = new Map();

const loadReportBoard = async ({ board, issuer }) => {
    const key = `${board}|${issuer || ''}`;
    if (reportBoardCache.has(key)) return reportBoardCache.get(key);
    let out = null;
    try {
        const q = new URLSearchParams({ board, limit: String(REPORT_BOARD_FETCH) });
        if (issuer) q.set('issuer', issuer);
        const res = await fetch(`/api/commodity-reports?${q}`);
        if (res.ok) {
            const doc = await res.json();
            if (Array.isArray(doc.items)) out = { items: doc.items, total: doc.total ?? doc.items.length };
        }
    } catch (err) {
        console.warn('[report-board] api unavailable, falling back to snapshot', err);
    }
    if (out === null) {
        const doc = await loadCommodityReportSnapshot();
        const byId = new Map((doc?.items || []).map((it) => [it.id, it]));
        const all = (doc?.boards?.[board] || []).map((id) => byId.get(id))
            .filter((it) => it && (!issuer || (it.control?.issuer || '').toUpperCase() === issuer));
        out = { items: all.slice(0, REPORT_BOARD_FETCH), total: all.length };
    }
    reportBoardCache.set(key, out);
    return out;
};

const renderReportBoard = (meta, items) => {
    const host = document.getElementById('ctl-board-slot');
    if (!host) return;
    if (!meta || !items.length) {
        host.innerHTML = '';
        return;
    }
    const first = items[0];
    const agency = escapeFeedText(first.agency_ko || first.agency || '');
    const agencyHref = first.agency_url ? safeReportHref(first.agency_url) : null;
    const row = (it) => {
        const href = safeReportHref(it.url);
        const title = escapeFeedText(it.title?.original || '');
        const lang = escapeFeedText(it.title?.original_lang || '');
        const ko = it.title?.ko ? escapeFeedText(it.title.ko) : '';
        const date = reportDate(it.published_at, it.published_precision);
        const measure = CONTROL_MEASURE_KO[it.control?.measure];
        return `<li class="ctlb-item">
            <div class="ctlb-text">
                ${href
                    ? `<a class="ctlb-title" href="${escapeFeedText(href)}" target="_blank" rel="noopener noreferrer" lang="${lang}">${title}</a>`
                    : `<span class="ctlb-title" lang="${lang}">${title}</span>`}
                ${ko ? `<span class="ctlb-ko">${ko}</span>` : ''}
            </div>
            <div class="ctlb-side">
                ${measure ? `<span class="ctlb-measure">${escapeFeedText(measure)}</span>` : ''}
                ${date ? `<span class="ctlb-date">${date}</span>` : ''}
            </div>
        </li>`;
    };
    const rest = items.slice(REPORT_BOARD_SHOWN);
    host.innerHTML = `
        <div class="ctlb-card">
            <div class="ctlb-head">
                <span class="ctlb-label">${escapeFeedText(meta.title)}</span>
                ${agencyHref
                    ? `<a class="ctlb-agency" href="${escapeFeedText(agencyHref)}" target="_blank" rel="noopener noreferrer" title="발간처 사이트로 이동">${agency} ↗</a>`
                    : `<span class="ctlb-agency">${agency}</span>`}
            </div>
            <ul class="ctlb-list">${items.slice(0, REPORT_BOARD_SHOWN).map(row).join('')}</ul>
            ${rest.length ? `<ul class="ctlb-list ctlb-more" hidden>${rest.map(row).join('')}</ul>
                <button type="button" class="ctlb-toggle" aria-expanded="false">이전 공고 ${rest.length}건 더보기</button>` : ''}
            <p class="ctlb-note">${escapeFeedText(meta.note)}</p>
        </div>`;
    const toggle = host.querySelector('.ctlb-toggle');
    toggle?.addEventListener('click', () => {
        const more = host.querySelector('.ctlb-more');
        const open = more.hidden;
        more.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        toggle.textContent = open ? '접기' : `이전 공고 ${rest.length}건 더보기`;
        paintReportsPage(); // the box changed height; re-fit the report pages below it
    });
};

// NOTICE FOR ANY BRANCH MERGING HERE FROM A STALE BASE: this function and
// its neighbors (renderFuturesCard, renderFuturesHistory, sparkChartHtml,
// wireSparkCharts, renderEmergencyStocks below) have been silently deleted
// by squash-merges from out-of-date branches three times in one day
// (2026-08-13, PRs #73/#75/#78 -- none touched trade code on purpose, all
// three carried a stale pre-fork copy of this file). If your branch is more
// than a few hours old, `git fetch origin main && git merge origin/main`
// before merging, and diff this function against origin/main afterward --
// don't trust a squash merge to catch this on its own, it won't conflict.
const renderTradeWorldPanel = (arcs) => {
    const exportRank = rankPartners(arcs, 'export');
    const importRank = rankPartners(arcs, 'import');
    const exportRows = worldRankRows(exportRank);
    const importRows = worldRankRows(importRank);

    // Replaces data.js's hand-written topExporter string the moment real arcs
    // are in: that string could go stale or, worse, name a country the map
    // has no route for (Switzerland's gold arcs were missing entirely before
    // the Comtrade area-code fix, so the label and the map disagreed). Left
    // untouched while arcs is still empty/loading, so the static string
    // serves as the loading placeholder instead of flashing blank.
    if (topExporterEl && exportRank.ranked.length) {
        topExporterEl.textContent = exportRank.ranked[0][0];
    }

    if (!newsContentEl) return;
    const newsTitle = document.querySelector('#news-panel .section-title');
    if (newsTitle) newsTitle.textContent = '주요 수출국 · 수입국';
    newsContentEl.innerHTML = `
        <div class="trade-focus-card">
            <div id="futures-slot"></div>
            ${subProductsCardHtml(currentCommodity)}
            <p class="trade-focus-sub">${typeof comtradePeriodLabel === 'function' && comtradePeriodLabel(arcs) ? `<span class="tm-period-badge">${comtradePeriodLabel(arcs)}</span> ` : ''}비중% · 막대는 각 방향 내 상대 물동량 · 국가를 누르면 그 나라 노선만 남습니다</p>
            <p class="trade-rank-group-head">주요 수출국</p>
            <div class="trade-rank-list">${exportRows || '<p class="empty-state">무역 루트 없음</p>'}</div>
            <p class="trade-rank-group-head">주요 수입국</p>
            <div class="trade-rank-list">${importRows || '<p class="empty-state">무역 루트 없음</p>'}</div>
        </div>`;
    bindSubProducts(newsContentEl);
    renderFuturesCard(currentCommodity);
    // No reports on the world view (stage 1) -- only once a country is
    // focused (stage 2, focusTradeCountry) does the right panel populate.
    // A world-level report has nowhere specific to point at yet; the
    // country view is where "which country does this apply to" is answered.
    panelHide(commodityReportsPanelEl);
    // Chained, not fired in parallel: renderRigCountWorld must not insert
    // before renderEmergencyStocks's own card exists (see its own comment).
    renderEmergencyStocks().then(renderRigCountWorld);
    window.GasStorage?.render();
};

const futuresCache = new Map();

/**
 * Front-month futures beside the flow ranking (world view, Stage 1).
 *
 * Fetched by commodity key, not by symbol -- the ranking already knows which
 * commodity is on screen, and keeping the Yahoo symbol server-side means a
 * bad ticker never leaks into a browser network tab.
 */
const renderFuturesCard = async (commodity) => {
    const slot = document.getElementById('futures-slot');
    if (!slot || !commodity) return;

    let doc = futuresCache.get(commodity);
    if (doc === undefined) {
        try {
            const res = await fetch(`/api/futures?commodity=${encodeURIComponent(commodity)}`);
            doc = res.ok ? await res.json() : null;
        } catch (err) {
            console.warn('[futures] unavailable', err);
            doc = null;
        }
        futuresCache.set(commodity, doc);
    }
    // The panel may have been rebuilt (or the commodity switched) while the
    // fetch was in flight -- re-fetch the live slot, and bail if it is gone
    // or if the visible commodity has since moved on.
    const live = document.getElementById('futures-slot');
    if (!live || currentCommodity !== commodity) return;
    if (!doc) { live.innerHTML = ''; return; }

    if (doc.priced === false) {
        live.innerHTML = `<div class="fut-card fut-none">
            <span class="fut-k">선물가</span>
            <span class="fut-none-note">${doc.reason}</span>
        </div>`;
        return;
    }
    if (!doc.priced) { live.innerHTML = ''; return; }

    const up = (doc.change_pct ?? 0) >= 0;
    live.innerHTML = `
        <div class="fut-card is-clickable" role="button" tabindex="0"
             data-fut-toggle="${doc.commodity}" data-fut-symbol="${doc.symbol}" data-fut-unit="${doc.unit}">
            <div class="fut-main">
                <span class="fut-px">$${doc.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                <span class="fut-unit">/ ${doc.unit}</span>
                ${doc.change_pct === null ? '' : `<span class="fut-chg ${up ? 'up' : 'down'}">
                    ${up ? '+' : ''}${doc.change_pct}%</span>`}
                <i class="stock-caret fut-caret"></i>
            </div>
            <div class="fut-meta">${doc.exchange} ${doc.symbol}
                ${doc.proxy ? ` · ${doc.proxy}` : ''} · 지연 시세 · 누르면 1년 추이</div>
        </div>
        <div class="fut-history"></div>`;
};

const futuresHistoryCache = new Map();

/**
 * 1-year daily history for whichever futures symbol is currently shown,
 * reusing the portfolio calculator's own history route (`/api/quote/history`)
 * rather than adding a second Yahoo-chart proxy -- the front-month card
 * already tells the browser the exact symbol, so there is nothing this needs
 * that route does not already fetch.
 */
const renderFuturesHistory = async (box) => {
    const symbol = box.dataset.futSymbol;
    const unit = box.dataset.futUnit || '';
    const host = box.nextElementSibling;
    if (!symbol || !host || !host.classList.contains('fut-history')) return;

    const opening = !box.classList.contains('is-open');
    box.classList.toggle('is-open', opening);
    if (!opening) { host.innerHTML = ''; return; }

    let doc = futuresHistoryCache.get(symbol);
    if (doc === undefined) {
        host.innerHTML = '<p class="empty-state" style="margin:6px 0;">불러오는 중…<span class="inline-spinner" aria-hidden="true"></span></p>';
        try {
            const res = await fetch(`/api/quote/history?symbol=${encodeURIComponent(symbol)}&range=1y`);
            doc = res.ok ? await res.json() : null;
        } catch (err) {
            console.warn('[futures history] unavailable', err);
            doc = null;
        }
        futuresHistoryCache.set(symbol, doc);
    }
    // The card may have been collapsed (or the panel rebuilt) while the fetch
    // was in flight.
    if (!box.classList.contains('is-open') || !box.isConnected) return;

    const points = (doc?.points || [])
        // Yahoo prices futures quoted in US cents (USX) the same way it does
        // equities; handleFutures already normalises the headline price, but
        // /api/quote/history does not, so cents-per-pound would otherwise
        // read 100x too high against the $/lb the card shows above it.
        .map(([ts, px]) => [ts, doc.currency === 'USX' ? px / 100 : px])
        .map(([ts, px]) => ({
            label: new Date(ts * 1000).toISOString().slice(0, 10),
            value: px,
        }));

    const chart = sparkChartHtml({
        points, unit: ` ${unit === '배럴' ? '$/bbl' : unit}`,
        formatValue: (v) => v.toLocaleString(undefined, { maximumFractionDigits: 2 }),
        ariaLabel: '최근 1년 가격 추이',
    });
    host.innerHTML = chart || '<p class="empty-state" style="margin:6px 0;">가격 이력을 불러오지 못했습니다.</p>';
    wireSparkCharts(host);
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

// Partner rows (country focus, Stage 2): click reveals the exact USD + tonnage
// behind the % bar. A separate listener from the one below because this one
// must not also re-focus the country the list is already showing.
document.getElementById('news-content')?.addEventListener('click', (e) => {
    const row = e.target instanceof Element ? e.target.closest('.trade-bar-row[data-partner]') : null;
    if (!row) return;
    row.classList.toggle('is-expanded');
});

// SPR / Cushing rows open their 3-year weekly sparkline underneath.
const toggleStockRow = (row) => {
    row.classList.toggle('is-open');
    row.closest('.stock-item')?.classList.toggle('is-open');
};
document.getElementById('news-content')?.addEventListener('click', (e) => {
    const row = e.target instanceof Element ? e.target.closest('[data-stock-toggle]') : null;
    if (row) toggleStockRow(row);
});
document.getElementById('news-content')?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const row = e.target instanceof Element ? e.target.closest('[data-stock-toggle]') : null;
    if (!row) return;
    e.preventDefault();
    toggleStockRow(row);
});

// Futures price card opens its 1-year history underneath, same pattern.
document.getElementById('news-content')?.addEventListener('click', (e) => {
    const box = e.target instanceof Element ? e.target.closest('[data-fut-toggle]') : null;
    if (box) renderFuturesHistory(box);
});
document.getElementById('news-content')?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const box = e.target instanceof Element ? e.target.closest('[data-fut-toggle]') : null;
    if (!box) return;
    e.preventDefault();
    renderFuturesHistory(box);
});

// Ranking rows focus a country, same as clicking it on the globe.
document.getElementById('news-content')?.addEventListener('click', (e) => {
    const row = e.target instanceof Element ? e.target.closest('[data-trade-country]') : null;
    if (!row || currentCommodity === 'climate') return;
    const label = row.getAttribute('data-trade-country');
    const arcs = window.TradeData?.[currentCommodity]?.arcs || [];
    // Rows carry the display label; find whatever spelling the data uses.
    // Checks both sides -- an importer-ranking row (e.g. China on iron ore)
    // can have zero arcs where it is the source, and source-only used to
    // make those rows a silent no-op click.
    const matches = (name) => (resolveCountry(name)?.label || name) === label;
    const hit = arcs.find((a) => matches(a.sourceName) || matches(a.targetName));
    if (hit) focusTradeCountry(matches(hit.sourceName) ? hit.sourceName : hit.targetName);
});

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

// RGB inversion, not a hue-rotate: cheap, deterministic, and reads as
// "the other direction" against the same background regardless of which
// commodity's base color it's inverting.
const complementaryColor = (c) => [255 - c[0], 255 - c[1], 255 - c[2]];

const buildTradeDashes = (arcs, phase, inboundKeys) => {
    const out = [];
    const n = Math.min(arcs.length, 60);
    for (let i = 0; i < n; i++) {
        const arc = arcs[i];
        if (!arc.sourcePosition || !arc.targetPosition) continue;
        const full = arc._dashPath ||= bowedPath(arc.sourcePosition, arc.targetPosition, DASH_RES);
        // Stagger start and speed so routes do not pulse in lockstep.
        const head = ((phase * (1 + (i % 5) * 0.13)) + (i % 7) / 7) % 1;
        const path = [];
        for (let s = 0; s <= DASH_STEPS; s++) {
            const f = head + (s / DASH_STEPS) * DASH_SPAN;
            if (f > 1) break;
            path.push(full[Math.round(f * DASH_RES)]);
        }
        if (path.length < 2) continue;
        // Only relative to a focused country do "export" and "import" mean
        // anything -- on the unfocused world map every arc is somebody's
        // export, so it stays the commodity's base color there. Focused,
        // inbound routes (this country buying) flip to the complementary
        // color so they read apart from outbound (this country selling)
        // instead of only the flow-particle direction telling them apart.
        const base = arc.sourceColor || [125, 211, 252];
        const isIn = inboundKeys && inboundKeys.has(`${arc.sourceName}>${arc.targetName}`);
        const c = isIn ? complementaryColor(base) : base;
        out.push({
            path,
            color: [Math.min(255, c[0] + 70), Math.min(255, c[1] + 70),
                    Math.min(255, c[2] + 70), 230],
            width: Math.max(1.5, arcWidth(arc.volume) * 0.9),
        });
    }
    return out;
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
    // No export-control colouring or legend on the trade map: controls are
    // shown in the 수출통제 모니터 only (2026-10-07).

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
                // outbound keeps the commodity colour, inbound flips to its
                // complement (same rule the animated dash trail uses), so
                // export/import read apart by colour and not only by which
                // way the flow particles happen to be moving.
                const base = d.sourceColor || [56, 189, 248];
                const c = (focus && opts._inbound?.has(key)) ? complementaryColor(base) : base;
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
                positionTooltipAt(info);
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
        ? buildTradeDashes(opts._focusedList || filteredArcs.slice(0, 40), tradeAnimPhase, opts._inbound)
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
