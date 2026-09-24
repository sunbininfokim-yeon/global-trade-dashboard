// Monthly trade view for a focused country (stage 2 of the trade map).
//
// The map itself stays annual: UN Comtrade's yearly bilateral table is the
// only source that covers every reporter, so it is the only one that can draw
// world routes. Monthly data exists for a subset of countries and commodities
// (the commodity_trade pipeline, scripts/commodity_trade/), and this file adds
// a 연간 / 월별 toggle to the country card only where that subset has
// something to show. No monthly data -> no toggle, just the annual year badge.
//
// Sources, each shown as its own series and never added together:
//   commodity_trade_comtrade_priority_v1.json  Comtrade monthly preview, X/M vs World
//   commodity_trade_national_priority_v1.json  national statistics offices, native units
//   commodity_trade_monthly_v1.json            JODI / ERS / Cochilco / ABS, exports vs World
//   commodity_trade_bilateral_v1/              partner breakdown for one month
//   commodity_trade_saudi_bulletin_v1.json     Saudi petroleum export VALUE (not crude, not by
//                                              destination) -- a reference card only
// An empty series is "not reported", not zero, and is never drawn as zero.
//
// Loaded after trade.js; uses its sparkChartHtml / wireSparkCharts and
// app.js's countryCode / resolveCountry (shared classic-script scope).

(() => {
    const DATA = '/public/data/';

    // Dashboard commodity key -> commodity_id used by the monthly pipeline.
    // Only pairs where the pipeline tracks the same product. HS can still be
    // narrower on the monthly side (gas 2711 vs LNG 271111, copper 7403 vs
    // ore 2603), so every series carries its own HS label.
    const MONTHLY_ID = {
        oil: 'crude_oil',
        gas: 'lng',
        thermal_coal: 'coal',
        copper: 'copper',
        aluminum: 'aluminum',
        nickel: 'nickel',
        cobalt: 'cobalt',
        graphite: 'graphite',
        iron_ore: 'iron_ore',
        wheat: 'wheat',
        corn: 'corn',
        soybeans: 'soybeans',
        sugar: 'sugar',
        palm_oil: 'palm_oil',
    };

    const SOURCE_LABEL = {
        comtrade_preview: 'UN Comtrade',
        jodi_oil: 'JODI-Oil',
        jodi_gas: 'JODI-Gas',
        ers_fatus_top10_world_total: 'USDA ERS',
        cochilco_bulletin: 'Cochilco',
        abs_5368032a: '호주 통계청(ABS)',
        norway_ssb_11008: '노르웨이 통계청(SSB)',
        india_tradestat: '인도 TradeStat',
        saudi_gastat_tableau_monthly: '사우디 통계청(GASTAT)',
        mexico_inegi_bcmm_monthly: '멕시코 INEGI',
        thailand_customs_statistics_report: '태국 관세청',
    };

    const UNIT_LABEL = {
        usd_m: 'M USD',
        kt: '천 톤',
        KTONS: '천 톤',
        KBBL: '천 배럴',
        metric_tons: '톤',
        USD_million: 'M USD',
        AUD_million_fob: 'M AUD (FOB)',
        kMT_cu_content: '천 톤 (구리 함량)',
        THB_FOB: '바트 (FOB)',
        THB_CIF: '바트 (CIF)',
        USD_FOB: 'USD (FOB)',
        usd_m_fob: 'M USD (FOB)',
        thb_m_fob: '백만 바트 (FOB)',
        thb_m_cif: '백만 바트 (CIF)',
        M3: '백만 ㎥',
        SAR_million: 'M SAR',
    };

    const FLOW_LABEL = { X: '수출', M: '수입' };

    // Exact rescaling to millions; the unit key keeps FOB and CIF apart.
    const UNIT_TO_MILLIONS = { USD_FOB: 'usd_m_fob', THB_FOB: 'thb_m_fob', THB_CIF: 'thb_m_cif' };

    // ---- small pure helpers (exported for tests) ---------------------------

    const monthKey = (m) => {
        const s = String(m || '');
        if (/^\d{6}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4)}`;
        return /^\d{4}-\d{2}$/.test(s) ? s : null;
    };
    const monthLabel = (m) => {
        const k = monthKey(m);
        return k ? `${k.slice(0, 4)}년 ${Number(k.slice(5))}월` : '';
    };
    const monthsBetween = (a, b) =>
        (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + Number(b.slice(5)) - Number(a.slice(5));

    // Publication hold, set by the pipeline (scripts/commodity_trade/
    // preview_quality.py, policy comtrade-preview-publication-v1): a Comtrade
    // preview month that collapsed below 1% of its own recent median is marked
    // points[].publication.eligible_for_display = false. Brazil's June 2026
    // soybean exports ($2,312 against $6.29B in May) are the case that
    // prompted it. Held months stay out of the headline, the chart and the
    // ranking, but are listed on the card: the raw value is kept, and a hold is
    // a suspicion of a partial count, not a finding. Only the pipeline decides
    // what is held -- JODI and national-office zeros are real and never are.
    const isHeld = (p) => p?.publication?.eligible_for_display === false;

    const MAX_SERIES_AGE_MONTHS = 24;

    // Latest month back 12 inclusive -- the pipeline's own window_rule.
    const trailing12 = (points) => {
        if (!points.length) return points;
        const last = points[points.length - 1].month;
        return points.filter((p) => monthsBetween(p.month, last) < 12);
    };

    const fmtValue = (v) => {
        const a = Math.abs(v);
        // Held months are tiny ($2,312 = 0.0023 M USD); rounding them to "0"
        // would restate exactly the misreading they are held for.
        if (a > 0 && a < 0.01) return v.toPrecision(2);
        const digits = a >= 100 ? 0 : a >= 10 ? 1 : 2;
        return v.toLocaleString(undefined, { maximumFractionDigits: digits });
    };

    /**
     * One card per (flow, source, unit). A series whose unit changes midway
     * (Thailand reports both FOB and CIF) splits instead of mixing.
     */
    const seriesFromPoints = (raw, { flow, hs, preferUsd }) => {
        const byKey = new Map();
        for (const p of raw || []) {
            const month = monthKey(p.month);
            if (!month) continue;
            let value;
            let unit;
            if (preferUsd && Number.isFinite(p.primary_value_usd)) {
                value = p.primary_value_usd / 1e6;
                unit = 'usd_m';
            } else if (p.unit === 'kg' && Number.isFinite(p.value)) {
                value = p.value / 1e6;
                unit = 'kt';
            } else if (UNIT_TO_MILLIONS[p.unit] && Number.isFinite(p.value)) {
                // National offices that report in single currency units
                // (Thailand 1,936,186,680 바트) read better in millions.
                value = p.value / 1e6;
                unit = UNIT_TO_MILLIONS[p.unit];
            } else if (p.unit === 'KTONS' && Number.isFinite(p.value)) {
                // JODI's thousand tonnes: same key as the kg / tonne series so
                // two sources of one volume land on one comparable unit.
                value = p.value;
                unit = 'kt';
            } else if (p.unit === 'metric_tons' && Number.isFinite(p.value)) {
                // Exact, and puts GASTAT and ERS on the same 천 톤 scale JODI uses.
                value = p.value / 1e3;
                unit = 'kt';
            } else if (Number.isFinite(p.value)) {
                value = p.value;
                unit = p.unit || '';
            } else {
                continue;
            }
            const source = p.source || '';
            const key = `${source}|${unit}`;
            if (!byKey.has(key)) byKey.set(key, { flow, hs, source, unit, byMonth: new Map() });
            const ratio = p.publication?.evidence?.ratio;
            byKey.get(key).byMonth.set(month, {
                month, value, held: isHeld(p), ratio: Number.isFinite(ratio) ? ratio : null,
            });
        }
        return [...byKey.values()].map((s) => {
            const window12 = trailing12([...s.byMonth.values()]
                .sort((a, b) => (a.month < b.month ? -1 : 1)));
            const points = window12.filter((p) => !p.held).map(({ month, value }) => ({ month, value }));
            return {
                held: window12.filter((p) => p.held),
                flow: s.flow,
                hs: s.hs,
                source: s.source,
                sourceLabel: SOURCE_LABEL[s.source] || s.source,
                unit: s.unit,
                unitLabel: UNIT_LABEL[s.unit] || s.unit,
                points,
                latest: points.length ? points[points.length - 1].month : null,
            };
        }).filter((s) => s.points.length);
    };

    const panelSeries = (doc, cid, iso3, preferUsd) => {
        const flows = doc?.reporters?.[iso3]?.flows;
        if (!flows) return [];
        const out = [];
        for (const [name, flow] of [['exports', 'X'], ['imports', 'M']]) {
            const c = flows[name]?.commodities?.[cid];
            if (c?.points?.length) out.push(...seriesFromPoints(c.points, { flow, hs: c.hs, preferUsd }));
        }
        return out;
    };

    const monthlyDocSeries = (doc, cid, iso3) => {
        for (const sector of Object.values(doc?.sectors || {})) {
            const c = sector?.commodities?.[cid];
            const s = c?.countries?.[iso3];
            if (s?.points?.length) {
                return seriesFromPoints(s.points, { flow: 'X', hs: (c.hs_stems || []).join('/') || null });
            }
        }
        return [];
    };

    const monthlyHsSet = (docs, cid) => {
        const hs = new Set();
        for (const doc of [docs.comtrade, docs.national]) {
            for (const r of Object.values(doc?.reporters || {})) {
                for (const f of Object.values(r?.flows || {})) {
                    const c = f?.commodities?.[cid];
                    if (c?.hs) hs.add(String(c.hs));
                }
            }
        }
        for (const sector of Object.values(docs.monthly?.sectors || {})) {
            for (const h of sector?.commodities?.[cid]?.hs_stems || []) hs.add(String(h));
        }
        return hs;
    };

    /** Newest bilateral part this reporter published for the commodity. */
    const bilateralEntry = (index, hsSet, iso3) => {
        const entries = (index?.entries || []).filter((e) => e.frequency === 'M'
            && e.reporter_iso3 === iso3 && hsSet.has(String(e.hs))
            && /^parts\/[a-f0-9]{64}\.json$/.test(e.path || ''));
        entries.sort((a, b) => (a.period < b.period ? 1 : a.period > b.period ? -1 : 0));
        return entries[0] || null;
    };

    /**
     * Everything the monthly view shows for one commodity x country, or null
     * when there is nothing -- the only signal the toggle keys off.
     */
    /**
     * Two sources for the same flow answer different questions or the same
     * one: a value series (M USD) and a volume series (천 톤) cannot be set
     * against each other at all, while two volume series can be checked on
     * the months they share. Saudi crude is the case: JODI and GASTAT agree
     * within about 1% on 2025-06..09, and their headline numbers differ only
     * because JODI runs to 2026-05 and GASTAT stops at 2025-09.
     */
    const compareSources = (series) => {
        const out = [];
        for (const flow of ['X', 'M']) {
            const same = series.filter((s) => s.flow === flow);
            for (let i = 0; i < same.length; i++) {
                for (let j = i + 1; j < same.length; j++) {
                    const a = same[i];
                    const b = same[j];
                    if (a.source === b.source) continue;
                    if (a.unit !== b.unit) {
                        // One note per source pair is enough.
                        if (!out.some((o) => o.kind === 'units' && o.flow === flow
                            && o.a.source === a.source && o.b.source === b.source)) {
                            out.push({ flow, a, b, kind: 'units' });
                        }
                        continue;
                    }
                    const bm = new Map(b.points.map((p) => [p.month, p.value]));
                    const both = a.points.filter((p) => bm.has(p.month) && (p.value > 0 || bm.get(p.month) > 0));
                    if (both.length < 2) {
                        out.push({ flow, a, b, kind: 'no_overlap' });
                        continue;
                    }
                    const gap = both.reduce((sum, p) => {
                        const q = bm.get(p.month);
                        return sum + Math.abs(p.value - q) / ((p.value + q) / 2);
                    }, 0) / both.length;
                    out.push({ flow, a, b, kind: 'overlap', months: both.map((p) => p.month), gap });
                }
            }
        }
        return out;
    };

    const buildView = (docs, commodityKey, iso3) => {
        const cid = MONTHLY_ID[commodityKey];
        if (!cid || !iso3) return null;
        const series = [
            ...panelSeries(docs.comtrade, cid, iso3, true),
            ...panelSeries(docs.national, cid, iso3, false),
            ...monthlyDocSeries(docs.monthly, cid, iso3),
        ];
        // A "latest 12 months" view has no place for a series that stopped
        // years ago (JODI-Gas has the UAE ending in 2016). Counted, not shown.
        const now = new Date();
        const nowKey = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`;
        const dormant = series.filter((s) => monthsBetween(s.latest, nowKey) > MAX_SERIES_AGE_MONTHS);
        series.splice(0, series.length, ...series.filter((s) => !dormant.includes(s)));
        // Exports first (the map colours countries as sellers first), then
        // freshest, then longest.
        series.sort((a, b) => (a.flow === b.flow ? 0 : a.flow === 'X' ? -1 : 1)
            || (a.latest < b.latest ? 1 : a.latest > b.latest ? -1 : 0)
            || b.points.length - a.points.length);
        const bilateral = bilateralEntry(docs.bilateralIndex, monthlyHsSet(docs, cid), iso3);
        const saudi = cid === 'crude_oil' && iso3 === 'SAU' && docs.saudi?.points?.length
            ? docs.saudi : null;
        if (!series.length && !bilateral && !saudi) return null;
        const months = series.map((s) => s.latest).filter(Boolean);
        if (bilateral) months.push(monthKey(bilateral.period));
        months.sort();
        return { cid, iso3, series, bilateral, saudi, dormant: dormant.length,
            comparisons: compareSources(series), latest: months[months.length - 1] || null };
    };

    // ---- data loading ------------------------------------------------------

    let docsPromise = null;
    const getJson = async (path) => {
        try {
            const r = await fetch(DATA + path);
            return r.ok ? await r.json() : null;
        } catch {
            return null;
        }
    };
    // All-or-nothing per file: a missing file just contributes no series, so
    // this works the same before and after the monthly data is deployed.
    const loadDocs = () => {
        if (!docsPromise) {
            docsPromise = Promise.all([
                getJson('commodity_trade_comtrade_priority_v1.json'),
                getJson('commodity_trade_national_priority_v1.json'),
                getJson('commodity_trade_monthly_v1.json'),
                getJson('commodity_trade_bilateral_v1/index.json'),
                getJson('commodity_trade_saudi_bulletin_v1.json'),
            ]).then(([comtrade, national, monthly, bilateralIndex, saudi]) =>
                ({ comtrade, national, monthly, bilateralIndex, saudi }));
        }
        return docsPromise;
    };

    const partCache = new Map();
    const loadPart = (path) => {
        if (!partCache.has(path)) partCache.set(path, getJson(`commodity_trade_bilateral_v1/${path}`));
        return partCache.get(path);
    };

    // ---- rendering ---------------------------------------------------------

    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    const seriesCardHtml = (s, newest) => {
        const last = s.points[s.points.length - 1];
        const stale = newest && s.latest && monthsBetween(s.latest, newest) > 3;
        const chart = typeof sparkChartHtml === 'function' ? sparkChartHtml({
            points: s.points.map((p) => ({ label: p.month, value: p.value })),
            unit: s.unitLabel,
            formatValue: fmtValue,
            ariaLabel: `${FLOW_LABEL[s.flow]} ${s.sourceLabel} 월별 추이`,
        }) : '';
        return `<div class="tm-series">
            <div class="tm-series-head">
                <span class="tm-flow tm-flow-${s.flow}">${FLOW_LABEL[s.flow] || s.flow}</span>
                <span class="tm-src">${esc(s.sourceLabel)}${s.hs ? ` · HS ${esc(s.hs)}` : ''}</span>
            </div>
            <div class="tm-latest">
                <strong>${fmtValue(last.value)}</strong> <span class="tm-unit">${esc(s.unitLabel)}</span>
                <span class="tm-when${stale ? ' is-stale' : ''}">${monthLabel(last.month)}${stale ? ' · 최신 아님' : ''}</span>
            </div>
            ${chart || `<p class="tm-note">관측 ${s.points.length}개월 — 추이를 그리기엔 부족합니다</p>`}
            ${s.source === 'comtrade_preview' && s.points.length + (s.held?.length || 0) < 2
                ? '<p class="tm-note is-warn">비교할 이전 달이 없어 부분 집계인지 확인되지 않은 값입니다.</p>' : ''}
            ${s.held?.length ? `<p class="tm-note is-warn">보류: ${s.held.map((p) =>
                `${monthLabel(p.month)} ${fmtValue(p.value)} ${esc(s.unitLabel)}${p.ratio != null
                    ? ` (직전 중앙값의 ${p.ratio < 0.001 ? '0.1% 미만' : `${(p.ratio * 100).toFixed(1)}%`})` : ''}`).join(', ')}
                — 부분 집계로 의심되어 대표값·추이에서 뺐습니다. 확정된 값은 아닙니다.</p>` : ''}
        </div>`;
    };

    const saudiCardHtml = (doc) => {
        const p = doc.points[doc.points.length - 1];
        const share = Number.isFinite(p.share_of_total_goods_export_value)
            ? ` · 전체 상품 수출의 ${(p.share_of_total_goods_export_value * 100).toFixed(1)}%` : '';
        return `<div class="tm-series tm-ref">
            <div class="tm-series-head">
                <span class="tm-flow tm-flow-X">참고</span>
                <span class="tm-src">사우디 통계청 월간 무역 보고서</span>
            </div>
            <div class="tm-latest">
                <strong>${fmtValue(p.value)}</strong> <span class="tm-unit">M SAR</span>
                <span class="tm-when">${monthLabel(p.month)}${p.preliminary ? ' · 잠정' : ''}</span>
            </div>
            <p class="tm-note">석유류 전체 수출 <b>금액</b>${share}. 원유(HS2709) 물량도, 목적국별 값도 아닙니다.</p>
        </div>`;
    };

    // Partners the dashboard's own M49 table (data.js) does not name. Plain
    // M49 = ISO 3166 numeric for these; 899 is Comtrade's "Areas, nes".
    const M49_ISO3 = {
        24: 'AGO', 40: 'AUT', 44: 'BHS', 90: 'SLB', 100: 'BGR', 120: 'CMR', 132: 'CPV',
        178: 'COG', 188: 'CRI', 203: 'CZE', 208: 'DNK', 218: 'ECU', 222: 'SLV', 340: 'HND',
        352: 'ISL', 376: 'ISR', 400: 'JOR', 426: 'LSO', 434: 'LBY', 478: 'MRT', 496: 'MNG',
        512: 'OMN', 516: 'NAM', 558: 'NIC', 591: 'PAN', 598: 'PNG', 620: 'PRT', 702: 'SGP',
        703: 'SVK', 716: 'ZWE', 748: 'SWZ', 752: 'SWE',
    };

    /** [short code for the row, full name for the tooltip] */
    const partnerLabel = (code) => {
        const name = window.ComtradeM49Names?.[code];
        if (name) {
            const full = (typeof resolveCountry === 'function' && resolveCountry(name)?.label) || name;
            return [typeof countryCode === 'function' ? countryCode(name) : name, full];
        }
        if (String(code) === '899') return ['기타', 'Areas, not elsewhere specified'];
        const iso = M49_ISO3[code];
        return iso ? [iso, iso] : [String(code), `M49 ${code}`];
    };

    const bilateralHtml = (part, entry) => {
        const blocks = [];
        for (const [flow, block] of Object.entries(part?.flows || {})) {
            const rows = (block?.rows || [])
                .filter((r) => Number.isFinite(r?.metrics?.trade_value_usd) && r.metrics.trade_value_usd > 0)
                .sort((a, b) => b.metrics.trade_value_usd - a.metrics.trade_value_usd);
            if (!rows.length) continue;
            const total = block?.metrics?.trade_value_usd?.world_total;
            const max = rows[0].metrics.trade_value_usd;
            const list = rows.slice(0, 8).map((r, i) => {
                const usdM = r.metrics.trade_value_usd / 1e6;
                const share = Number.isFinite(total) && total > 0 ? `${((r.metrics.trade_value_usd / total) * 100).toFixed(1)}%` : '—';
                const [code, full] = partnerLabel(r.partner);
                return `<div class="trade-rank-row trade-bar-row${flow === 'M' ? ' is-inbound' : ''}"
                             title="${FLOW_LABEL[flow] || flow} · ${esc(full)} · ${fmtValue(usdM)} M USD">
                    <span class="tr-i">${i + 1}</span>
                    <span class="tr-dir"></span>
                    <span class="tr-name tr-code">${esc(code)}</span>
                    <span class="tr-bar"><i style="width:${Math.max(3, (r.metrics.trade_value_usd / max) * 100)}%"></i></span>
                    <span class="tr-pct">${share}</span>
                    <span class="tr-vol">${fmtValue(usdM)} M USD</span>
                </div>`;
            }).join('');
            blocks.push(`<p class="trade-rank-group-head">${FLOW_LABEL[flow] || flow} 상대국 · ${monthLabel(entry.period)} · HS ${esc(entry.hs)}</p>
                <div class="trade-rank-list">${list}</div>`);
        }
        if (!blocks.length) return '';
        return `${blocks.join('')}
            <p class="tm-note">UN Comtrade 보고국 기준 · 비중은 그 달 세계 합계 대비 · 표에 없는 상대국은 0이 아니라 미보고입니다.</p>`;
    };

    const MEASURE = (s) => (/usd|thb|aud|sar/i.test(s.unit) ? '금액' : '물량');
    const comparisonHtml = (list) => {
        const lines = list.slice(0, 3).map(({ flow, a, b, kind, months, gap }) => {
            const who = `${FLOW_LABEL[flow]} · ${esc(a.sourceLabel)} vs ${esc(b.sourceLabel)}`;
            if (kind === 'units') {
                return `${who}: ${MEASURE(a)}(${esc(a.unitLabel)})과 ${MEASURE(b)}(${esc(b.unitLabel)})은 다른 지표라 숫자를 직접 비교하지 않습니다. 둘 다 맞을 수 있습니다.`;
            }
            if (kind === 'no_overlap') {
                return `${who}: 겹치는 달이 없어 서로 검증할 수 없습니다 (${monthLabel(a.latest)} / ${monthLabel(b.latest)} 기준).`;
            }
            const pct = (gap * 100).toFixed(gap < 0.1 ? 1 : 0);
            const verdict = gap < 0.05 ? '서로 일치' : gap < 0.2 ? '대체로 비슷' : '크게 다름 — 정의나 집계 범위가 다를 수 있음';
            const lag = a.latest !== b.latest ? ` 최신 값이 다른 건 기준 월이 달라서입니다 (${monthLabel(a.latest)} / ${monthLabel(b.latest)}).` : '';
            return `${who}: 겹치는 ${months.length}개월(${monthLabel(months[0])}~${monthLabel(months[months.length - 1])}) 평균 차이 ${pct}% · ${verdict}.${lag}`;
        });
        return lines.length ? `<div class="tm-compare"><b>출처 비교</b>${lines.map((l) => `<p>${l}</p>`).join('')}</div>` : '';
    };

    const monthlyHtml = (view) => {
        const cards = view.series.slice(0, 6).map((s) => seriesCardHtml(s, view.latest)).join('');
        return `<p class="trade-focus-sub">월별 · 최근 12개월 · 출처마다 따로 표시하며 합산하지 않습니다 · 지도의 노선은 연간 데이터입니다</p>
            ${comparisonHtml(view.comparisons || [])}
            ${view.saudi ? saudiCardHtml(view.saudi) : ''}
            ${cards}
            ${view.series.length > 6 ? `<p class="tm-note">최근 갱신 순 6개만 표시 · 나머지 ${view.series.length - 6}개 계열 생략</p>` : ''}
            ${view.dormant ? `<p class="tm-note">2년 넘게 갱신되지 않은 계열 ${view.dormant}개는 표시하지 않았습니다.</p>` : ''}
            <div class="tm-bilateral"></div>`;
    };

    // ---- wiring ------------------------------------------------------------

    // The choice follows the user from country to country, as long as the
    // next one has monthly data too.
    let preferred = 'annual';

    const setMode = (card, mode) => {
        const annual = card.querySelector('.tm-annual');
        const monthly = card.querySelector('.tm-monthly');
        if (!annual || !monthly) return;
        annual.hidden = mode !== 'annual';
        monthly.hidden = mode !== 'monthly';
        card.querySelectorAll('.tm-toggle button').forEach((b) => {
            const on = b.dataset.mode === mode;
            b.classList.toggle('is-on', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    };

    /**
     * Called by focusTradeCountry after it renders the country card. Swaps the
     * annual year badge for a 연간 / 월별 toggle once monthly data is known to
     * exist for this commodity and country; otherwise leaves the badge alone.
     */
    const attach = async (card, { commodity, countryName, annualLabel }) => {
        if (!card) return;
        const iso3 = typeof countryCode === 'function' ? countryCode(countryName) : null;
        if (!MONTHLY_ID[commodity] || !iso3) return;
        const token = `${commodity}|${iso3}|${Date.now()}`;
        card.dataset.tmToken = token;

        const view = buildView(await loadDocs(), commodity, iso3);
        // The user may have clicked elsewhere while the files loaded.
        if (!view || !card.isConnected || card.dataset.tmToken !== token) return;

        const badge = card.querySelector('.tm-period-badge');
        const monthly = card.querySelector('.tm-monthly');
        if (!badge || !monthly) return;
        badge.outerHTML = `<div class="tm-toggle" role="group" aria-label="기간 단위">
            <button type="button" data-mode="annual">${esc(annualLabel || '연간')}</button>
            <button type="button" data-mode="monthly">월별 · ${esc(monthLabel(view.latest))}</button>
        </div>`;
        monthly.innerHTML = monthlyHtml(view);
        if (typeof wireSparkCharts === 'function') wireSparkCharts(monthly);

        card.querySelectorAll('.tm-toggle button').forEach((b) => b.addEventListener('click', (e) => {
            e.preventDefault();
            preferred = b.dataset.mode;
            setMode(card, preferred);
        }));
        setMode(card, preferred);

        if (view.bilateral) {
            const part = await loadPart(view.bilateral.path);
            if (!card.isConnected || card.dataset.tmToken !== token) return;
            const slot = monthly.querySelector('.tm-bilateral');
            if (slot && part?.meta?.reporter_iso3 === iso3) slot.innerHTML = bilateralHtml(part, view.bilateral);
        }
    };

    window.TradeMonthly = {
        attach,
        // exposed for tests
        _internal: { compareSources, comparisonHtml, MONTHLY_ID, buildView, seriesFromPoints, trailing12, isHeld, monthLabel, bilateralHtml, seriesCardHtml, partnerLabel },
    };
})();
