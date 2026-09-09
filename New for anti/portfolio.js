// Portfolio lab for Global Trade Dashboard -- holdings input, covariance and
// correlation, HRP/IVP allocation, and the risk views.
//
// Split out of app.js (2026-08-20). app.js is shared by parallel sessions and
// a squash merge replaces whole regions instead of diffing them. This domain
// calls nothing outside itself.
//
// Relies on globals still in app.js: finEsc, finPct, loadFirstJson/finDataPaths,
// and the DOM helpers.

// --- 금융 진단 ---------------------------------------------------------------
// Both tabs' math lives outside this file, in New for anti/portfolio-engine/
// (index.mjs for direct-input holdings risk, scenario.mjs for the scenario
// backtester) -- pure ESM, no I/O. This file only resolves names to tickers,
// fetches/aligns public price history in the browser, and renders each
// engine's one result object. No offline Python pipeline is read anymore.
const finSignedPct = (x, digits = 1) => {
    if (x === null || x === undefined || Number.isNaN(x)) return '—';
    const v = x * 100;
    return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%p`;
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

// Three preferences write to localStorage and none of them is worth an
// exception: a full quota or a locked-down browser just means the next render
// falls back to the default.
const pfPersist = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) { /* quota */ }
};

const pfSave = (p) => pfPersist(PF_STORE, JSON.stringify(p));

const pfBlank = () => ({ risk_profile: 'balanced', base_currency: 'KRW', positions: [], net_asset_value: null });

// Covariance from ~250 daily observations needs comfortably more rows than
// assets or the estimate turns to noise -- and noisy covariance is exactly what
// the risk-contribution number is built on. 20 keeps that ratio above 12 while
// still fitting any portfolio a person actually holds.
const PF_MAX = 20;

let PF_REGISTRY = null;
let PF_PROFILES = null;

const pfLoadRefs = async () => {
    if (PF_REGISTRY && PF_PROFILES) return;
    const grab = (name) => loadFirstJson(finDataPaths(name));
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
    if (!keys.length) return { dates: [], cols: {}, perSymbol: {} };
    const daySets = {};
    let common = null;
    for (const k of keys) {
        const s = new Set(series[k].map(([t]) => Math.floor(t / 86400)));
        daySets[k] = s;
        common = common === null ? s : new Set([...common].filter((d) => s.has(d)));
    }
    const dates = [...common].sort((a, b) => a - b);
    const cols = {};
    for (const k of keys) {
        const m = new Map(series[k].map(([t, v]) => [Math.floor(t / 86400), v]));
        cols[k] = dates.map((d) => m.get(d));
    }
    // Per symbol: how many of ITS OWN trading days got excluded because some
    // other symbol in this alignment didn't trade that day -- the "how many
    // rows did the date intersection drop" transparency the scenario tab
    // surfaces per asset/factor/benchmark.
    const perSymbol = {};
    for (const k of keys) perSymbol[k] = { total: daySets[k].size, dropped: daySets[k].size - dates.length };
    return { dates, cols, perSymbol };
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

// The numerical core (covariance shrinkage, HRP, risk contribution, VaR,
// Sharpe) lives in portfolio-engine/, ported from and verified bit-for-bit
// against the offline Python engine (see its README/tests). This function
// keeps its old job: turn holdings + fetched prices into that engine's
// resolved/valued input, then reshape its output back into the exact result
// shape pfRenderResult already knows how to draw, so nothing downstream
// changes. Holdings and results still never leave the browser -- only
// tickers cross the network, through the existing quote proxy.
let pfEnginePromise = null;
const pfEngine = () => pfEnginePromise || (pfEnginePromise = import('/portfolio-engine/index.mjs'));

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
        p._class = it.asset_class || 'equity';
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
    const { dates: dayNums, cols } = pfAlign(series);
    if (dayNums.length < 60) throw new Error('공통 거래일이 60일 미만이라 계산이 불안정합니다.');

    // Each holding becomes one KRW-denominated price path (pre-return, pre-leverage);
    // pricesToLogReturns turns those into the aligned log-return matrix the engine wants.
    const priceCols = [], values = [], leverage = [], meta = [], seenId = new Set();
    for (const p of rows) {
        const signed = (p.side === 'short' ? -1 : 1) * Math.abs(pfValueOf(p));
        const fxSym = pfFxSymbol(p._cur);

        let krwPath;
        if (!p._sym) {
            // Base-currency cash: flat in KRW terms.
            krwPath = dayNums.map(() => 1);
        } else if (p._sym === fxSym) {
            krwPath = cols[p._sym];                        // holding the currency itself
        } else if (fxSym) {
            krwPath = cols[p._sym].map((v, i) => v * cols[fxSym][i]);
        } else {
            krwPath = cols[p._sym];
        }

        priceCols.push(krwPath);
        values.push(signed);
        leverage.push(p._lev);
        // The engine requires unique resolved ids; a long and a short of the
        // same underlying otherwise collide.
        let id = p.id;
        if (p.side === 'short' || seenId.has(id)) id = `${id}__${p.side || 'long'}`;
        seenId.add(id);
        meta.push({ name: p._name, currency: p._cur, side: p.side, lev: p._lev, signed, id, asset_class: p._class });
    }

    const isoDates = dayNums.map((d) => new Date(d * 86400000).toISOString().slice(0, 10));
    const priceMatrix = isoDates.map((_, t) => priceCols.map((col) => col[t]));

    const engine = await pfEngine();
    const { dates, logReturns } = engine.pricesToLogReturns({ dates: isoDates, prices: priceMatrix, syntheticLeverage: leverage });

    const positions = meta.map((m, i) => ({ id: m.id, currency: m.currency, asset_class: m.asset_class, value: values[i] }));
    const hasShort = values.some((v) => v < 0);
    const navRaw = Number(pf.net_asset_value);
    const navGiven = Number.isFinite(navRaw) && navRaw > 0;
    if (hasShort && !navGiven) throw new Error('공매도 보유가 있으면 순자산(NAV)을 직접 입력해야 계산할 수 있습니다.');

    let result;
    try {
        result = engine.analyzePortfolio({
            positions, dates, logReturns, baseCurrency: 'KRW',
            netAssetValue: navGiven ? navRaw : null,
            riskFreeRateAnn: PF_RF_ANNUAL,
        });
    } catch (err) {
        if (/exceed NAV|equal NAV/.test(err.message || '')) {
            throw new Error('입력한 순자산(NAV)이 보유 합계와 맞지 않습니다. NAV를 다시 확인해 주세요.');
        }
        throw err;
    }

    const hasResidual = result.asset_ids.length > meta.length;
    const names = meta.map((m) => m.name);
    if (hasResidual) {
        names.push('현금(잔여)');
        meta.push({ name: '현금(잔여)', currency: 'KRW', side: 'long', lev: 1, signed: null,
                    id: '__residual_base_cash__', asset_class: 'cash' });
    }

    const weights = result.advice.current_weights;
    // Same guard as the old HRP path: a suggestion needs at least two
    // non-fixed (non-cash, non-short) positions to say anything meaningful.
    const riskyCount = result.advice.fixed_mask.filter((f) => !f).length;
    const target = (result.advice.allocation_status === 'ok' && riskyCount >= 2)
        ? result.advice.target_weights : null;
    const deltas = target ? names.map((n, i) => ({
        name: n,
        delta: target[i] - weights[i],
        from: Math.abs(weights[i]),
        to: Math.abs(target[i]),
        riskless: result.advice.fixed_mask[i],
    })).sort((a, b) => b.delta - a.delta) : null;

    const currencyById = new Map(positions.map((p) => [p.id, p.currency]));
    const krwWeight = result.asset_ids.reduce((a, id, i) =>
        a + ((currencyById.get(id) || 'KRW') === 'KRW' ? Math.abs(weights[i]) : 0), 0);
    const foreignWeight = result.asset_ids.reduce((a, id, i) =>
        a + ((currencyById.get(id) || 'KRW') !== 'KRW' ? Math.abs(weights[i]) : 0), 0);

    return {
        names, weights, rc: result.risk_contribution, meta, corr: result.correlation_short,
        total: result.accounting.net_asset_value, target, deltas,
        obs: result.data_quality.n_obs,
        start: result.data_quality.start,
        end: result.data_quality.end,
        annVol: result.performance.ann_volatility_short,
        annRet: result.performance.ann_return_short,
        sharpe: result.performance.sharpe_short,
        var1d: result.risk.short.var_1d_95,
        cvar1d: result.risk.short.cvar_1d_95,
        var10d: result.risk.short.var_10d_95,
        var10dKrw: result.risk.short.var_10d_95_amount,
        krwWeight, foreignWeight,
        clusters: pfClusters(names, result.correlation_short).map((g) => ({
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

// A holding carries its own instrument record once added (pfInstOf reads it
// back), because a searched or uploaded ticker is not in the registry and
// would otherwise be unresolvable on the next page load. Shared by the
// manual add button and the spreadsheet importer so the two can't drift apart.
const pfInstFromPicked = (picked, spot) => ({
    name_ko: picked.name_ko,
    yahoo: picked.yahoo || null,
    currency: picked.currency || (spot && spot.currency) || 'KRW',
    asset_class: picked.asset_class || 'equity',
    leveraged: !!picked.leveraged,
    leverage_factor: picked.synthetic_leverage ? (picked.leverage_factor || 2) : 1,
    proxy: !!(picked.proxy || picked.synthetic_leverage),
});

// A holding carries its own instrument record once added, because a ticker
// found through search is not in the registry and would otherwise be
// unresolvable on the next page load.
const pfInstOf = (p) => p.inst || PF_REGISTRY.find((x) => x.id === p.id) || { name_ko: p.id };

// Adding a holding re-renders the whole form, so the unit toggle has to live
// outside it. Kept local once, it silently reverted to 금액 after every add and
// the next "5" meant five won instead of five shares.
let pfMode = 'value';

// --- 엑셀/CSV 가져오기 -------------------------------------------------------
// The file is parsed entirely in the browser (SheetJS, loaded on first use);
// only the resolved ticker text for each row is ever sent anywhere (through
// the existing search/quote proxy), same as typing it into the search box by
// hand -- quantities and amounts never leave this page. Loaded lazily so a
// visitor who never uploads a file never pays for the ~1MB library.
let pfSheetJsPromise = null;
const PF_SHEETJS_SRC = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
const pfLoadSheetJs = () => {
    if (window.XLSX) return Promise.resolve(window.XLSX);
    if (!pfSheetJsPromise) {
        pfSheetJsPromise = new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = PF_SHEETJS_SRC;
            s.onload = () => (window.XLSX ? resolve(window.XLSX) : reject(new Error('파일 처리 라이브러리를 불러오지 못했습니다.')));
            s.onerror = () => reject(new Error('파일 처리 라이브러리를 불러오지 못했습니다. 네트워크를 확인해 주세요.'));
            document.head.appendChild(s);
        });
    }
    return pfSheetJsPromise;
};

// Header aliases: a user's own spreadsheet rarely matches one exact schema,
// so this looks for the first column whose header even loosely names the
// thing, in Korean or English, rather than requiring an exact template.
const PF_UPLOAD_HEADERS = {
    name: [/종목/i, /티커/i, /symbol/i, /ticker/i, /^name/i],
    qty: [/수량/i, /주수/i, /^shares?$/i, /^qty$/i, /quantity/i],
    value: [/평가.?금액/i, /금액/i, /^value$/i, /^amount$/i],
    side: [/매수.?매도/i, /공매도/i, /^side$/i, /position/i],
    price: [/단가/i, /체결가/i, /^price$/i],
};
const pfDetectUploadColumn = (headers, kind) =>
    headers.find((h) => PF_UPLOAD_HEADERS[kind].some((p) => p.test(String(h).trim())));

const pfParseUploadNumber = (v) => {
    const n = Number(String(v ?? '').replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) ? n : 0;
};

// Local registry match first (it alone carries leverage/proxy flags); a
// remote symbol search only for names the registry doesn't know, exactly
// like typing into the search box.
const pfResolveUploadName = async (raw) => {
    const q = String(raw ?? '').trim();
    if (!q) return null;
    const local = pfSearchLocal(q);
    const exact = local.find((it) => [it.name_ko, it.id, ...(it.aliases || [])]
        .some((a) => String(a).toLowerCase() === q.toLowerCase()));
    if (exact) return exact;
    if (local.length === 1) return local[0];
    const { quotes } = await pfSearchRemote(q);
    if (quotes.length) return pfFromQuote(quotes[0]);
    return local[0] || null;
};

// A trade-log file (단가/체결가 column present) needs average-cost accounting
// before it can become a holding; a snapshot file (금액 or plain 수량, no
// per-trade price) already states what's held today. Detected by column
// shape rather than asked, since a user pasting a broker export doesn't
// know or care which of these two things this tool calls it.
const pfImportSpreadsheet = async (file, onProgress) => {
    const XLSX = await pfLoadSheetJs();
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(buf, { type: 'array' });
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' });
    if (!rows.length) throw new Error('파일에서 읽을 행이 없습니다.');

    const headers = Object.keys(rows[0]);
    const nameCol = pfDetectUploadColumn(headers, 'name') || headers[0];
    const qtyCol = pfDetectUploadColumn(headers, 'qty');
    const valueCol = pfDetectUploadColumn(headers, 'value');
    const sideCol = pfDetectUploadColumn(headers, 'side');
    const priceCol = pfDetectUploadColumn(headers, 'price');
    if (priceCol && qtyCol) return pfImportTransactionLog(rows, { nameCol, qtyCol, priceCol, sideCol }, onProgress);
    if (!qtyCol && !valueCol) throw new Error('수량 또는 금액 열을 찾지 못했습니다. 헤더(예: 종목명/수량/금액, 또는 거래내역이면 종목명/매수매도/수량/단가)를 확인해 주세요.');

    const pf = pfLoad() || pfBlank();
    const unresolved = [];
    let added = 0;

    for (let i = 0; i < rows.length; i++) {
        const raw = String(rows[i][nameCol] ?? '').trim();
        if (!raw) continue;
        if (pf.positions.length >= PF_MAX) { unresolved.push(`(정원 ${PF_MAX}종 초과로 중단) ${raw} 및 이후`); break; }

        onProgress && onProgress(`종목 확인 중… ${i + 1}/${rows.length}`);
        const picked = await pfResolveUploadName(raw).catch(() => null);
        if (!picked) { unresolved.push(raw); continue; }

        const side = /공매도|숏|short|매도/i.test(String(sideCol ? rows[i][sideCol] : '')) ? 'short' : 'long';
        const valueNum = valueCol ? pfParseUploadNumber(rows[i][valueCol]) : 0;
        const qtyNum = qtyCol ? pfParseUploadNumber(rows[i][qtyCol]) : 0;

        let row;
        if (valueNum > 0) {
            row = { id: picked.id, side, mode: 'value', value: valueNum, inst: pfInstFromPicked(picked) };
        } else if (qtyNum > 0) {
            const spot = await pfSpot(picked.yahoo || null, picked.currency).catch(() => null);
            if (!spot || !(spot.price > 0)) { unresolved.push(`${raw} (가격 조회 실패)`); continue; }
            row = { id: picked.id, side, mode: 'shares', shares: qtyNum, inst: pfInstFromPicked(picked, spot),
                     price: spot.price, fx: spot.fx, pricedAt: new Date().toISOString().slice(0, 10) };
        } else {
            unresolved.push(`${raw} (수량/금액 인식 실패)`);
            continue;
        }

        const same = (p) => p.id === row.id && p.side === row.side && (p.mode || 'value') === row.mode;
        const existing = pf.positions.findIndex(same);
        if (existing >= 0) {
            if (row.mode === 'shares') pf.positions[existing].shares += row.shares;
            else pf.positions[existing].value += row.value;
        } else if (pf.positions.length < PF_MAX) {
            pf.positions.push(row);
            added++;
        } else {
            unresolved.push(`(정원 ${PF_MAX}종 초과) ${raw}`);
        }
    }

    pfSave(pf);
    return { added, unresolved, total: rows.length };
};

// One row per trade, often several rows per name (매수 10주 @10만, 매도 3주
// @9만, 매수 4주 @12만, ...) -- reconstructed with the moving-average method
// Korean brokerage apps use: each buy blends into a running average cost,
// each sell realizes P&L against that average without moving it. A sell
// beyond what the log shows as bought is clamped (there is no opening trade
// to price it against) rather than guessed. Currently-held (net qty > 0)
// names become holdings, valued like any manual share entry at today's
// price; fully closed-out names still count toward the realized total but
// are not added, since there is nothing left to hold or to risk-analyze.
// Prices are read as already being in the base currency (KRW) -- a foreign
// trade log would need its own historical FX per trade, which this doesn't do.
const pfImportTransactionLog = async (rows, cols, onProgress) => {
    const { nameCol, qtyCol, priceCol, sideCol } = cols;
    const byName = new Map();
    for (const r of rows) {
        const raw = String(r[nameCol] ?? '').trim();
        const qty = pfParseUploadNumber(r[qtyCol]);
        const price = pfParseUploadNumber(r[priceCol]);
        if (!raw || !(qty > 0) || !(price > 0)) continue;
        const action = /매도|판매|sell/i.test(String(sideCol ? r[sideCol] : '')) ? 'sell' : 'buy';
        if (!byName.has(raw)) byName.set(raw, []);
        byName.get(raw).push({ action, qty, price });
    }
    if (!byName.size) throw new Error('종목명·수량·단가를 모두 갖춘 거래 행이 없습니다.');

    const pf = pfLoad() || pfBlank();
    const unresolved = [];
    let added = 0, realizedTotal = 0, i = 0;

    for (const [raw, txns] of byName) {
        i++;
        if (pf.positions.length >= PF_MAX) { unresolved.push(`(정원 ${PF_MAX}종 초과로 중단) ${raw} 및 이후`); break; }
        onProgress && onProgress(`거래 내역 정리 중… ${i}/${byName.size}`);

        let qty = 0, avgCost = 0, realized = 0;
        for (const t of txns) {
            if (t.action === 'buy') {
                avgCost = (qty + t.qty > 0) ? (qty * avgCost + t.qty * t.price) / (qty + t.qty) : t.price;
                qty += t.qty;
            } else {
                const sellQty = Math.min(t.qty, qty);
                realized += (t.price - avgCost) * sellQty;
                qty -= sellQty;
            }
        }
        realizedTotal += realized;
        if (qty <= 0) continue; // fully closed out: no holding, but its realized P&L still counted above

        const picked = await pfResolveUploadName(raw).catch(() => null);
        if (!picked) { unresolved.push(raw); continue; }
        const spot = await pfSpot(picked.yahoo || null, picked.currency).catch(() => null);
        if (!spot || !(spot.price > 0)) { unresolved.push(`${raw} (가격 조회 실패)`); continue; }

        const row = { id: picked.id, side: 'long', mode: 'shares', shares: qty,
            inst: pfInstFromPicked(picked, spot), price: spot.price, fx: spot.fx,
            pricedAt: new Date().toISOString().slice(0, 10), avgCost, realizedPnl: realized };

        const same = (p) => p.id === row.id && p.side === row.side && (p.mode || 'value') === row.mode;
        const existing = pf.positions.findIndex(same);
        if (existing >= 0) {
            pf.positions[existing].shares += row.shares;
            pf.positions[existing].avgCost = avgCost;
            pf.positions[existing].realizedPnl = (pf.positions[existing].realizedPnl || 0) + realized;
        } else if (pf.positions.length < PF_MAX) {
            pf.positions.push(row);
            added++;
        } else {
            unresolved.push(`(정원 ${PF_MAX}종 초과) ${raw}`);
        }
    }

    pfSave(pf);
    return { added, unresolved, total: byName.size, realizedTotal };
};

// Re-rendering the form (every add/delete does, including right after an
// upload finishes) would otherwise wipe these before anyone reads them.
let pfLastUnresolved = [];
let pfLastUploadStatus = '';

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

            <div class="pf-upload">
                <label for="pf-file" class="pf-btn pf-btn-ghost">엑셀·CSV로 가져오기</label>
                <input type="file" id="pf-file" accept=".csv,.xlsx,.xls" class="hidden">
                <span id="pf-upload-status" class="fin-note">${finEsc(pfLastUploadStatus)}</span>
            </div>
            <p class="fin-note">
                두 형식 다 헤더 이름은 대략 맞아도 됩니다. <strong>현재 보유 스냅샷</strong>(종목명/수량 또는 종목명/금액)이면
                그대로 보유 목록에 추가되고, <strong>거래내역</strong>(종목명/매수매도/수량/단가, 같은 종목이 여러 행)이면
                매수·매도를 순서대로 반영해 평단·평가손익까지 계산합니다.
                이 브라우저 안에서만 읽습니다 — 파일도, 그 안의 수량·금액·단가도 서버로 올라가지 않습니다. 종목명만 검색에 쓰입니다.
            </p>
            ${pfLastUnresolved.length ? `
            <div class="fin-alert">
                <span class="fin-alert-mark">인식하지 못한 행 ${pfLastUnresolved.length}건</span>
                <ul>${pfLastUnresolved.map((x) => `<li>${finEsc(x)}</li>`).join('')}</ul>
                <p class="fin-note">위 항목은 위 검색창으로 직접 추가해 주세요.</p>
                <button type="button" id="pf-upload-dismiss" class="pf-btn pf-btn-ghost">닫기</button>
            </div>` : ''}
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
                            ${p.avgCost ? (() => {
                                const cur = p.price * (p.fx || 1);
                                const pnl = (cur - p.avgCost) * p.shares;
                                const pct = p.avgCost > 0 ? (cur - p.avgCost) / p.avgCost * 100 : 0;
                                return `<span class="pf-row-sub">평단 ${pfKrw(p.avgCost)} ·
                                    평가손익 ${pnl >= 0 ? '+' : ''}${pfKrw(pnl)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)
                                    ${p.realizedPnl ? ` · 실현손익 ${p.realizedPnl >= 0 ? '+' : ''}${pfKrw(p.realizedPnl)}` : ''}</span>`;
                            })() : ''}
                        </span>
                        <span class="pf-row-val">${pfKrw(val)}</span>
                        <span class="pf-row-w">${(w * 100).toFixed(1)}%</span>
                        <button class="pf-del" data-i="${i}" aria-label="삭제">✕</button>
                    </div>`;
                }).join('')}
            </div>
            <div class="pf-total"><span>합계</span><strong>${pfKrw(total)}</strong></div>
            <div class="pf-nav-field">
                <label for="pf-nav">순자산(NAV, 원)</label>
                <input type="text" id="pf-nav" class="pf-field" inputmode="numeric"
                       value="${pf.net_asset_value ? Number(pf.net_asset_value).toLocaleString('ko-KR') : ''}"
                       placeholder="비워두면 보유 합계로 계산">
                ${pf.positions.some((p) => p.side === 'short')
                    ? '<p class="pf-limit">공매도 보유가 있어 순자산을 직접 입력해야 계산할 수 있습니다.</p>' : ''}
            </div>
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
        const inst = pfInstFromPicked(picked, spot);
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
        pfLastUnresolved = [];
        pfLastUploadStatus = '';
        renderPfInput(root, onDone);
    });

    root.querySelector('#pf-upload-dismiss')?.addEventListener('click', () => {
        pfLastUnresolved = [];
        renderPfInput(root, onDone);
    });

    const fileEl = root.querySelector('#pf-file');
    const uploadStatusEl = root.querySelector('#pf-upload-status');
    fileEl?.addEventListener('change', async () => {
        const file = fileEl.files[0];
        if (!file) return;
        fileEl.disabled = true;
        uploadStatusEl.textContent = '읽는 중…';
        try {
            const { added, unresolved, realizedTotal } = await pfImportSpreadsheet(file, (msg) => { uploadStatusEl.textContent = msg; });
            pfLastUnresolved = unresolved;
            pfLastUploadStatus = (unresolved.length
                ? `${added}건 추가, ${unresolved.length}건 인식 실패`
                : `${added}건 추가했습니다.`)
                + (realizedTotal ? ` · 실현손익 합계 ${realizedTotal >= 0 ? '+' : ''}${pfKrw(realizedTotal)}` : '');
        } catch (err) {
            pfLastUnresolved = [];
            pfLastUploadStatus = err.message || '파일을 읽지 못했습니다.';
        } finally {
            fileEl.value = '';
            renderPfInput(root, onDone);
        }
    });

    const navEl = root.querySelector('#pf-nav');
    navEl?.addEventListener('input', () => {
        const raw = String(navEl.value).replace(/[^0-9]/g, '');
        navEl.value = raw ? Number(raw).toLocaleString('ko-KR') : '';
    });
    navEl?.addEventListener('change', () => {
        const raw = String(navEl.value).replace(/[^0-9]/g, '');
        const next = pfLoad() || pfBlank();
        next.net_asset_value = raw ? Number(raw) : null;
        pfSave(next);
    });

    root.querySelector('#pf-run')?.addEventListener('click', () => onDone && onDone());
};

const PF_MODE_KEY = 'portfolioLab.mode';
const pfGetMode = () => (localStorage.getItem(PF_MODE_KEY) === 'expert') ? 'expert' : 'basic';
const pfSetMode = (m) => pfPersist(PF_MODE_KEY, m);

// --- 시나리오 백테스트 (T25b) -------------------------------------------------
// The engine (portfolio-engine/scenario.mjs) takes already-resolved, already-
// aligned, already-base-currency-converted series; this section's only job is
// resolving names to tickers, fetching public history, aligning/FX-converting
// it in the browser (same pfAlign/pfFxSymbol machinery pfCompute uses), and
// describing the one runScenario() result as Basic/Expert -- never recomputing
// it. No holdings/strategy/result ever leaves the browser; only ticker symbols
// cross the network through the existing quote proxy.
const PF_SCN_KEY = 'portfolioLab.scenario.v1';
const pfScnBlank = () => ({
    assets: [], factors: [], benchmark: null,
    startDate: '', endDate: '', holdoutStart: '',
    rebalance: 'buy_and_hold', initialCapital: null,
    conditionOn: false, conditionTree: { type: 'group', op: 'all', children: [] }, holdingBars: 10,
    compareOn: false, variants: [],
    hypotheses: [],
});
const pfScnLoad = () => {
    try {
        const raw = localStorage.getItem(PF_SCN_KEY);
        const p = raw && JSON.parse(raw);
        return (p && Array.isArray(p.assets)) ? { ...pfScnBlank(), ...p } : pfScnBlank();
    } catch (_) { return pfScnBlank(); }
};
const pfScnSave = (s) => pfPersist(PF_SCN_KEY, JSON.stringify(s));

// Same registry-first-then-remote-search resolution the spreadsheet importer
// uses (pfResolveUploadName), reused so "type a name, get a ticker" behaves
// identically everywhere in this file.
const pfScnResolve = async (raw, role, existingIds) => {
    const picked = await pfResolveUploadName(raw).catch(() => null);
    if (!picked) throw new Error(`'${raw}'을(를) 찾지 못했습니다.`);
    let id = picked.id;
    if (existingIds.has(id)) id = `${id}__${role}`;
    return { id, name_ko: picked.name_ko, yahoo: picked.yahoo || null, currency: picked.currency || 'KRW' };
};
const pfScnUsedIds = (s) => new Set([...s.assets, ...s.factors, ...(s.benchmark ? [s.benchmark] : [])].map((r) => r.id));

// Finds an asset-factor pair not already covered by an existing hypothesis,
// in asset-then-factor order, so "가설 추가" always proposes something new
// instead of a silent duplicate; null once every combination is used.
const pfScnNextHypothesisPair = (state) => {
    const used = new Set(state.hypotheses.map((h) => `${h.assetId}::${h.factorId}`));
    for (const a of state.assets) for (const f of state.factors)
        if (!used.has(`${a.id}::${f.id}`)) return { assetId: a.id, factorId: f.id };
    return null;
};

// Condition tree: {type:'group', op:'all'|'any', children:[...]} nesting
// leaves {type:'leaf', factorId, lookbackBars, operator, threshold} -- mirrors
// the engine's own {all:[...]}/{any:[...]} recursive shape (scenario.mjs
// compileCondition, up to depth 8 / 20 members per group), just wrapped with
// a UI-facing `type` tag so leaf vs. group is unambiguous while editing.
const pfScnBlankLeaf = (factorId) => ({ type: 'leaf', factorId, lookbackBars: 5, operator: 'gte', threshold: 0 });
const pfScnBlankGroup = (op = 'all') => ({ type: 'group', op, children: [] });
const pfScnParsePath = (s) => (s ? s.split('.').map(Number) : []);
const pfScnNodeAt = (tree, path) => path.reduce((n, i) => n.children[i], tree);
const pfScnGetParentAndIndex = (tree, path) => ({ parent: pfScnNodeAt(tree, path.slice(0, -1)), idx: path[path.length - 1] });
// Drops leaves referencing a deleted factor; groups (root included) always survive, even empty.
const pfScnPruneFactor = (node, factorId) => {
    if (node.type === 'leaf') return node.factorId === factorId ? null : node;
    return { ...node, children: node.children.map((c) => pfScnPruneFactor(c, factorId)).filter(Boolean) };
};
// Drops empty groups recursively; only used on a cloned tree right before
// handing it to the engine, so it never mutates the user's live editing state.
const pfScnPruneEmptyGroups = (node) => {
    if (node.type === 'leaf') return node;
    const children = node.children.map(pfScnPruneEmptyGroups).filter(Boolean);
    return children.length ? { ...node, children } : null;
};
const pfScnTreeToCondition = (node) => node.type === 'leaf'
    ? { factorId: node.factorId, lookbackBars: node.lookbackBars, threshold: node.threshold, operator: node.operator }
    : { [node.op]: node.children.map(pfScnTreeToCondition) };

// Describes ONE runScenario() result two ways; toggling never recomputes.
// null is always rendered as "산출 불가", never coerced to 0 or hidden.
const scnPct = (v, d = 1) => v === null || v === undefined ? '산출 불가' : finPct(v, d);
const scnNum = (v, d = 2) => v === null || v === undefined ? '산출 불가' : Number(v).toFixed(d);

// pfAlign only intersects trading days -- this turns that into a plain-language
// line so a user can see how many of each asset/factor/benchmark's own rows
// got excluded because some other symbol in the same run didn't trade that
// day, instead of the alignment silently shrinking the usable history.
const scnAlignmentNote = (alignment) => {
    if (!alignment || !alignment.rows.length) return '';
    const dropped = alignment.rows.filter((r) => r.dropped > 0);
    const detail = dropped.length
        ? dropped.map((r) => `${r.label} ${r.dropped}개`).join(', ') + ' 제외 — 다른 자산·변수와 거래일이 맞지 않았습니다'
        : '제외된 관측일 없음';
    return `<p class="fin-note">날짜 정렬: 공통 거래일 ${alignment.commonCount}개 사용 (${finEsc(detail)}).</p>`;
};

const renderScenarioResult = (out, result, mode, alignment) => {
    const strat = result.strategy, rel = result.relationship;
    const m = strat ? strat.metrics : null;

    const warningsHtml = result.warnings.length ? `
        <div class="fin-alert">
            <span class="fin-alert-mark">확인 필요</span>
            <ul>${result.warnings.map((w) => `<li>${finEsc(w.message_ko)}</li>`).join('')}</ul>
        </div>` : '';

    const assessmentHtml = strat ? `
        <section class="fin-block fin-block-wide">
            <h2>이 결과가 뜻하는 것</h2>
            <p class="fin-lead">${finEsc(strat.assessment.headline_ko)}</p>
            <p class="fin-note">${finEsc(strat.assessment.policy)} · 투자 추천/인과관계/유의성 검정이 아닙니다.
               완료 거래 표본 독립성·실거래 검증은 아직 확인되지 않았습니다(episode_independence_verified=false, execution_validated=false).</p>
        </section>` : '';

    const basicCards = strat ? `
        <div class="fin-cards">
            <div class="fin-card">
                <span class="fin-card-title">기간 수익률</span>
                <span class="fin-card-value">${scnPct(m.total_return)}</span>
                <p class="fin-card-plain">${finEsc(result.period.actual_start)} ~ ${finEsc(result.period.actual_end)}, 관측 ${result.period.n_return_observations}개 기준입니다.</p>
            </div>
            <div class="fin-card">
                <span class="fin-card-title">변동성(연환산)</span>
                <span class="fin-card-value">${scnPct(m.annualized_volatility)}</span>
            </div>
            <div class="fin-card">
                <span class="fin-card-title">최대 낙폭</span>
                <span class="fin-card-value">${scnPct(m.max_drawdown)}</span>
                <p class="fin-card-plain">${m.recovered === null ? '' : m.recovered ? `${m.recovery_bars}개 관측 만에 고점 회복` : '기간 내 미회복'}</p>
            </div>
            ${result.benchmark ? `
            <div class="fin-card">
                <span class="fin-card-title">비교지수(${finEsc(result.benchmark.id)}) 대비</span>
                <span class="fin-card-value">${scnPct(result.benchmark.excess_total_return)}</span>
                <p class="fin-card-plain">같은 기간 비교지수 수익률 ${scnPct(result.benchmark.metrics.total_return)} 대비 초과분입니다.</p>
            </div>` : ''}
            ${strat.monetary_results ? `
            <div class="fin-card">
                <span class="fin-card-title">투자금 기준 손익</span>
                <span class="fin-card-value">${pfKrw(strat.monetary_results.pnl)}</span>
                <p class="fin-card-plain">초기 투자금 ${pfKrw(strat.initial_capital)} 기준, 비용·세금 제외 가상 손익입니다.</p>
            </div>` : ''}
        </div>` : '';

    const relationHtml = `
        <section class="fin-block fin-block-wide">
            <h2>${strat ? '함께 움직임' : '관계'}</h2>
            ${rel.ids.length > 1 ? `
            <div class="fin-table-wrap"><table class="fin-table"><thead><tr><th></th>
                ${rel.ids.map((id) => `<th>${finEsc(id)}</th>`).join('')}</tr></thead><tbody>
                ${rel.ids.map((row, i) => `<tr><th>${finEsc(row)}</th>
                    ${rel.correlation[i].map((c) => `<td>${c === null ? '—' : c.toFixed(2)}</td>`).join('')}</tr>`).join('')}
                </tbody></table></div>
            <p class="fin-note">자산 단순수익률 vs 요인 변화량의 상관입니다. 가격 수준의 상관이 아니며, 표본이 짧으면 null입니다.</p>` : ''}
            ${rel.factor_exposures.length ? `
            <ul class="fin-list">
                ${rel.factor_exposures.map((e) => `<li>${finEsc(e.asset_id)} vs ${finEsc(e.factor_id)}:
                    베타 ${e.contemporaneous.beta === null ? '산출 불가' : e.contemporaneous.beta.toFixed(3)}
                    (동시점, r²=${e.contemporaneous.r_squared === null ? '—' : e.contemporaneous.r_squared.toFixed(2)})
                    ${e.factor_unit ? ` · 단위: ${finEsc(e.factor_unit)}` : ''}</li>`).join('')}
            </ul>
            <p class="fin-note">베타는 인과관계가 아닌 동시점 회귀 기울기입니다. 단위는 입력한 요인 단위를 따릅니다.</p>` : ''}
            ${rel.hypotheses.length ? `
            <h3 class="fin-sub">가설 검토</h3>
            <ul class="fin-list">
                ${rel.hypotheses.map((h) => `<li>${finEsc(h.asset_id)} vs ${finEsc(h.factor_id)}:
                    예상 ${h.expected_sign > 0 ? '같은 방향(+)' : '반대 방향(−)'}
                    → 관측 ${h.observed_direction === 'consistent' ? '일치' : h.observed_direction === 'opposite' ? '불일치' : '판단 불가'}
                    (베타 ${h.beta === null ? '산출 불가' : h.beta.toFixed(3)})</li>`).join('')}
            </ul>
            <p class="fin-note">계산 전에 정한 방향과 비교한 것입니다 — 결과를 본 뒤 가설을 바꿔 끼우면 검증력이 없습니다.
                통계적 유의성 검정은 하지 않았습니다(statistical_significance=not_tested), 인과관계도 아닙니다.</p>` : ''}
        </section>`;

    const conditionHtml = result.condition ? `
        <section class="fin-block fin-block-wide">
            <h2>진입 조건</h2>
            <p class="fin-p">조건이 전부(AND) 참이 된 다음 공통 종가에 진입, ${result.condition.holding_bars}개 관측 보유합니다.</p>
            <p class="fin-note">완료 거래 ${strat?.n_completed_episodes ?? 0}건
                ${strat?.episode_win_fraction != null ? ` · 승률 ${scnPct(strat.episode_win_fraction)}` : ''}
                (표본이 적으면 독립적인 통계 근거로 보기 어렵습니다).</p>
        </section>` : '';

    const expertHtml = mode === 'expert' && strat ? `
        <section class="fin-block fin-block-wide">
            <h2>전문가 지표</h2>
            <div class="fin-cards">
                <div class="fin-card"><span class="fin-card-title">산술 샤프(sharpe_arithmetic)</span>
                    <span class="fin-card-value">${scnNum(m.sharpe_arithmetic)}</span>
                    <p class="fin-card-plain">CAGR 기반 샤프(직접 입력 탭)와 정의가 다릅니다 — 그대로 비교하지 마세요.</p></div>
                <div class="fin-card"><span class="fin-card-title">CAGR</span><span class="fin-card-value">${scnPct(m.cagr)}</span></div>
                <div class="fin-card"><span class="fin-card-title">VaR / CVaR (1 관측)</span>
                    <span class="fin-card-value">${scnPct(m.var_1bar)} / ${scnPct(m.cvar_1bar)}</span>
                    <p class="fin-card-plain">신뢰수준 ${scnPct(m.confidence, 0)}, 꼬리 표본 ${m.historical_tail_count}개.
                       보장된 최대손실이 아니며, 여러 달력일이 한 관측일 수 있습니다.</p></div>
                <div class="fin-card"><span class="fin-card-title">승률(일 단위)</span><span class="fin-card-value">${scnPct(m.win_day_fraction)}</span></div>
            </div>
            ${strat.rolling_var.n_evaluated ? `<p class="fin-note">롤링 VaR(직전 ${strat.rolling_var.window}개 실현수익률 기준) 초과 비율
                ${scnPct(strat.rolling_var.breach_fraction)} (목표 ${scnPct(strat.rolling_var.target_exceedance_fraction)}), 평가 ${strat.rolling_var.n_evaluated}개.
                현재 보유 재평가 방식의 규제용 VaR 백테스트가 아닙니다.</p>` : ''}
            <p class="fin-note">손익귀속: ${strat.pnl_attribution.map((p) => `${finEsc(p.asset_id)} ${scnPct(p.return_on_initial_nav)}`).join(', ')}
                (잔여오차 ${scnPct(strat.attribution_residual)})</p>
            ${result.split ? `
            <h3 class="fin-sub">전후 분할 (${finEsc(result.split.split_date)} 기준)</h3>
            <p class="fin-p">전반 수익률 ${scnPct(result.split.earlier.total_return)}(관측 ${result.split.earlier.n_obs})
                · 후반 수익률 ${scnPct(result.split.later.total_return)}(관측 ${result.split.later.n_obs})</p>
            <p class="fin-note">후반 평균수익 95% block-bootstrap 구간: ${result.split.later_mean_ci.status === 'exploratory'
                ? `[${scnNum(result.split.later_mean_ci.lower, 4)}, ${scnNum(result.split.later_mean_ci.upper, 4)}]`
                : '표본 부족으로 산출 불가'}. 규칙을 재최적화하지 않은 고정 규칙의 전후 비교이며, 반복 walk-forward 검증이 아닙니다.</p>` : ''}
            <details><summary>재현용 run_config / source_manifest</summary>
                <pre class="fin-code">${finEsc(JSON.stringify({ run_config: result.run_config, source_manifest: result.source_manifest }, null, 2))}</pre>
            </details>
        </section>` : '';

    out.innerHTML = `
        <div class="pf-mode" role="group" aria-label="보기 수준">
            <button type="button" class="pf-mode-btn ${mode === 'basic' ? 'on' : ''}" data-mode="basic">기본</button>
            <button type="button" class="pf-mode-btn ${mode === 'expert' ? 'on' : ''}" data-mode="expert">전문가</button>
        </div>
        ${warningsHtml}
        ${basicCards}
        ${assessmentHtml}
        ${conditionHtml}
        ${relationHtml}
        ${expertHtml}
        <div class="fin-foot">
            ${scnAlignmentNote(alignment)}
            <p class="fin-engine">엔진: portfolio-engine/scenario.mjs · 스키마 ${finEsc(result.schema_version)} · 기준통화 ${finEsc(result.base_currency)}</p>
            <p class="pf-privacy">계산은 이 브라우저에서 수행됩니다 — 입력·결과는 서버에 저장되지 않습니다.</p>
        </div>`;

    out.querySelectorAll('.pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.mode === mode) return;
        pfSetMode(b.dataset.mode);
        renderScenarioResult(out, result, b.dataset.mode, alignment);
    }));
};

// One base run plus each variant, side by side. Never picks a "winner" --
// compareScenarioVariants() itself always returns automatic_selection: false,
// and this only ever renders exactly what it returned.
const renderScenarioComparison = (out, base, comparison, mode, alignment) => {
    const cols = [{ id: '기준(현재 설정)', result: base }, ...comparison.results];
    const row = (label, get, fmt = scnPct) => `
        <tr><th>${finEsc(label)}</th>${cols.map((c) => `<td>${fmt(get(c.result))}</td>`).join('')}</tr>`;
    const stratRow = (label, get, fmt) => cols.every((c) => c.result.strategy) ? row(label, (r) => get(r.strategy), fmt) : '';

    out.innerHTML = `
        <section class="fin-block fin-block-wide">
            <div class="pf-mode" role="group" aria-label="보기 수준">
                <button type="button" class="pf-mode-btn ${mode === 'basic' ? 'on' : ''}" data-mode="basic">기본</button>
                <button type="button" class="pf-mode-btn ${mode === 'expert' ? 'on' : ''}" data-mode="expert">전문가</button>
            </div>
            <h2>여러 시나리오 비교</h2>
            <p class="fin-note">비중·자산·조건은 전부 같고, 아래 표에 나온 항목만 다릅니다. 여러 결과 중 좋은 것만 골라 쓰면 과적합될 수 있습니다 — 다중검정 보정은 하지 않습니다.</p>
            <div class="fin-table-wrap"><table class="fin-table"><thead><tr><th></th>
                ${cols.map((c) => `<th>${finEsc(c.id)}</th>`).join('')}</tr></thead><tbody>
                <tr><th>기간</th>${cols.map((c) => `<td>${finEsc(c.result.period.actual_start)} ~ ${finEsc(c.result.period.actual_end)}</td>`).join('')}</tr>
                ${stratRow('기간 수익률', (s) => s.metrics.total_return)}
                ${stratRow('변동성(연환산)', (s) => s.metrics.annualized_volatility)}
                ${stratRow('최대 낙폭', (s) => s.metrics.max_drawdown)}
                ${stratRow('산술 샤프', (s) => s.metrics.sharpe_arithmetic, scnNum)}
                ${stratRow('VaR(1관측)', (s) => s.metrics.var_1bar)}
                ${mode === 'expert' ? stratRow('완료 거래', (s) => s.n_completed_episodes, (v) => v === null || v === undefined ? '산출 불가' : String(v)) : ''}
            </tbody></table></div>
            ${mode === 'expert' ? `<details><summary>변형별 run_config</summary>
                <pre class="fin-code">${finEsc(JSON.stringify(comparison.results.map((r) => ({ id: r.id, run_config: r.result.run_config })), null, 2))}</pre>
            </details>` : ''}
            ${scnAlignmentNote(alignment)}
        </section>`;

    out.querySelectorAll('.pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.mode === mode) return;
        pfSetMode(b.dataset.mode);
        renderScenarioComparison(out, base, comparison, b.dataset.mode, alignment);
    }));
};

// UI depth cap for nested condition groups (sanity vs. the engine's depth-8
// limit) -- past this a user is building something a spreadsheet formula
// would serve better, not something this form should encourage.
const SCN_COND_MAX_UI_DEPTH = 3;
const renderCondLeafRow = (node, path, factors) => {
    const p = path.join('.');
    return `
    <div class="pf-row">
        <select class="pf-field scn-cond-factor" data-path="${p}">
            ${factors.map((f) => `<option value="${finEsc(f.id)}" ${f.id === node.factorId ? 'selected' : ''}>${finEsc(f.name_ko)}</option>`).join('')}
        </select>
        <input type="number" class="pf-field scn-cond-lookback" data-path="${p}" value="${node.lookbackBars}" min="1" placeholder="관측 수(bar)">
        <select class="pf-field scn-cond-op" data-path="${p}">
            <option value="gte" ${node.operator === 'gte' ? 'selected' : ''}>이상(≥)</option>
            <option value="lte" ${node.operator === 'lte' ? 'selected' : ''}>이하(≤)</option>
        </select>
        <input type="number" step="any" class="pf-field scn-cond-threshold" data-path="${p}" value="${node.threshold}" placeholder="기준값">
        <button class="pf-del" data-kind="condleaf" data-path="${p}" aria-label="삭제">✕</button>
    </div>`;
};
const renderConditionTree = (node, path, factors, depth) => {
    const p = path.join('.');
    const full = node.children.length >= 20;
    return `
    <div class="scn-cond-group ${depth > 0 ? 'scn-cond-nested' : ''}" data-path="${p}">
        <div class="scn-cond-group-head">
            <select class="pf-field scn-cond-groupop" data-path="${p}">
                <option value="all" ${node.op === 'all' ? 'selected' : ''}>모두 만족(AND)</option>
                <option value="any" ${node.op === 'any' ? 'selected' : ''}>하나 이상 만족(OR)</option>
            </select>
            ${depth > 0 ? `<button class="pf-del" data-kind="condgroup" data-path="${p}" aria-label="그룹 삭제">✕ 그룹 삭제</button>` : ''}
        </div>
        ${node.children.length ? `<div class="pf-rows">${node.children.map((child, i) => child.type === 'leaf'
            ? renderCondLeafRow(child, [...path, i], factors)
            : renderConditionTree(child, [...path, i], factors, depth + 1)).join('')}</div>`
            : '<p class="fin-note">아직 없습니다.</p>'}
        <div class="pf-add scn-cond-add-row">
            <button class="scn-cond-add-leaf pf-btn pf-btn-ghost" data-path="${p}" ${full ? 'disabled' : ''}>조건 추가</button>
            ${depth < SCN_COND_MAX_UI_DEPTH ? `<button class="scn-cond-add-group pf-btn pf-btn-ghost" data-path="${p}" ${full ? 'disabled' : ''}>그룹 추가(AND/OR)</button>` : ''}
        </div>
    </div>`;
};

// Runs the scenario engine's actual computation (runScenario /
// compareScenarioVariants -- the part that can be slow, e.g. block-bootstrap
// resampling) in a Web Worker so a heavy calculation doesn't freeze the tab.
// Only the plain-JSON input/variants scenarioBuildInput() already builds
// cross the worker boundary, same as scenario.mjs's own zero-I/O contract --
// holdings/strategy/results never leave this browser either way. A worker
// created once and reused across runs; a load-time failure (some sandboxed
// embeds disallow Workers) rejects whatever was waiting and lets the next
// call retry fresh rather than hanging forever.
let pfScnWorker = null;
let pfScnWorkerReqId = 0;
const pfScnWorkerPending = new Map();
const pfScnGetWorker = () => {
    if (pfScnWorker) return pfScnWorker;
    pfScnWorker = new Worker('/portfolio-engine/scenario-worker.js', { type: 'module' });
    pfScnWorker.onmessage = (e) => {
        const { id, ok, result, error } = e.data;
        const pending = pfScnWorkerPending.get(id);
        if (!pending) return;
        pfScnWorkerPending.delete(id);
        ok ? pending.resolve(result) : pending.reject(new Error(error));
    };
    pfScnWorker.onerror = (e) => {
        for (const pending of pfScnWorkerPending.values()) pending.reject(new Error(e.message || 'Web Worker 오류'));
        pfScnWorkerPending.clear();
        pfScnWorker = null;
    };
    return pfScnWorker;
};
const pfScnWorkerCall = (kind, payload) => new Promise((resolve, reject) => {
    let worker;
    try { worker = pfScnGetWorker(); } catch (err) { reject(err); return; }
    const id = ++pfScnWorkerReqId;
    pfScnWorkerPending.set(id, { resolve, reject });
    worker.postMessage({ id, kind, ...payload });
});

const renderScenarioLab = async (host) => {
    const state = pfScnLoad();
    let result = null, resultError = null, resultAlignment = null;
    let compareResult = null, compareError = null, compareAlignment = null;

    const paint = () => {
        host.innerHTML = `
        <section class="fin-block fin-block-wide pf-input">
            <h2>자산 <span class="fin-note">(매매 대상, 비중 없이 두면 매매 없이 관계만 봅니다)</span></h2>
            <div class="pf-add">
                <input type="text" id="scn-a-q" class="pf-field" placeholder="종목명·티커 (예: 삼성전자, AAPL)">
                <input type="text" id="scn-a-w" class="pf-field pf-amt" inputmode="numeric" placeholder="비중 %(+롱/-숏)">
                <button id="scn-a-add" class="pf-btn">추가</button>
            </div>
            <p id="scn-a-err" class="pf-picked pf-picked-warn"></p>
            ${state.assets.length ? `<div class="pf-rows">${state.assets.map((a, i) => `
                <div class="pf-row"><span class="pf-row-name">${finEsc(a.name_ko)}
                    <span class="fin-tag">${finEsc(a.currency)}</span></span>
                    <span class="pf-row-val">${a.weightPct >= 0 ? '+' : ''}${a.weightPct}%</span>
                    <button class="pf-del" data-kind="asset" data-i="${i}" aria-label="삭제">✕</button></div>`).join('')}</div>`
                : '<p class="fin-note">아직 없습니다.</p>'}
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>관찰 변수 <span class="fin-note">(매매하지 않음, 조건·상관 분석용)</span></h2>
            <div class="pf-add">
                <input type="text" id="scn-f-q" class="pf-field" placeholder="예: 천연가스 선물, 달러/원">
                <select id="scn-f-change" class="pf-field">
                    <option value="relative">변화율(%)</option>
                    <option value="difference">변화폭(수준차, 예: 금리)</option>
                </select>
                <button id="scn-f-add" class="pf-btn">추가</button>
            </div>
            <p id="scn-f-err" class="pf-picked pf-picked-warn"></p>
            ${state.factors.length ? `<div class="pf-rows">${state.factors.map((f, i) => `
                <div class="pf-row"><span class="pf-row-name">${finEsc(f.name_ko)}
                    <span class="fin-tag">${f.change === 'difference' ? '변화폭' : '변화율'}</span></span>
                    <button class="pf-del" data-kind="factor" data-i="${i}" aria-label="삭제">✕</button></div>`).join('')}</div>`
                : '<p class="fin-note">아직 없습니다.</p>'}
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>요인 방향 가설 <span class="fin-note">(선택 — 결과를 보기 전에 정하는 자산-요인 기대 방향. 결과를 본 뒤 정하면 사후 끼워맞추기라 의미가 없습니다)</span></h2>
            ${(!state.assets.length || !state.factors.length) ? '<p class="fin-note">가설을 쓰려면 위에서 자산과 관찰 변수를 먼저 추가하세요.</p>' : `
            ${state.hypotheses.length ? `<div class="pf-rows">${state.hypotheses.map((h, i) => `
                <div class="pf-row">
                    <select class="pf-field scn-hyp-asset" data-i="${i}">
                        ${state.assets.map((a) => `<option value="${finEsc(a.id)}" ${a.id === h.assetId ? 'selected' : ''}>${finEsc(a.name_ko)}</option>`).join('')}
                    </select>
                    <select class="pf-field scn-hyp-factor" data-i="${i}">
                        ${state.factors.map((f) => `<option value="${finEsc(f.id)}" ${f.id === h.factorId ? 'selected' : ''}>${finEsc(f.name_ko)}</option>`).join('')}
                    </select>
                    <select class="pf-field scn-hyp-sign" data-i="${i}">
                        <option value="1" ${h.expectedSign === 1 ? 'selected' : ''}>같은 방향(+)일 것이다</option>
                        <option value="-1" ${h.expectedSign === -1 ? 'selected' : ''}>반대 방향(−)일 것이다</option>
                    </select>
                    <button class="pf-del" data-kind="hyp" data-i="${i}" aria-label="삭제">✕</button>
                </div>`).join('')}</div>`
                : '<p class="fin-note">아직 없습니다.</p>'}
            <div class="pf-add">
                <button id="scn-hyp-add" class="pf-btn pf-btn-ghost" ${pfScnNextHypothesisPair(state) ? '' : 'disabled'}>가설 추가</button>
            </div>`}
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>비교지수 <span class="fin-note">(선택, 전략 성과와 같은 기간 비교)</span></h2>
            <div class="pf-add">
                <input type="text" id="scn-b-q" class="pf-field" placeholder="예: KODEX 200, S&P 500 ETF">
                <button id="scn-b-add" class="pf-btn">추가</button>
                ${state.benchmark ? `<button id="scn-b-del" class="pf-btn pf-btn-ghost">${finEsc(state.benchmark.name_ko)} 지우기</button>` : ''}
            </div>
            <p id="scn-b-err" class="pf-picked pf-picked-warn"></p>
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>기간·재조정</h2>
            <div class="pf-add">
                <label class="pf-row-sub">시작<br><input type="date" id="scn-start" class="pf-field" value="${finEsc(state.startDate)}"></label>
                <label class="pf-row-sub">종료<br><input type="date" id="scn-end" class="pf-field" value="${finEsc(state.endDate)}"></label>
                <label class="pf-row-sub">후반검증 시작(선택)<br><input type="date" id="scn-holdout" class="pf-field" value="${finEsc(state.holdoutStart)}"></label>
            </div>
            <div class="pf-add">
                <select id="scn-rebalance" class="pf-field">
                    <option value="buy_and_hold" ${state.rebalance === 'buy_and_hold' ? 'selected' : ''}>매수 후 유지</option>
                    <option value="daily" ${state.rebalance === 'daily' ? 'selected' : ''}>매일 재조정</option>
                    <option value="monthly" ${state.rebalance === 'monthly' ? 'selected' : ''}>매월 재조정</option>
                </select>
                <input type="text" id="scn-capital" class="pf-field pf-amt" inputmode="numeric"
                    placeholder="투자금(원, 선택)" value="${state.initialCapital ? Number(state.initialCapital).toLocaleString('ko-KR') : ''}">
            </div>
            <p class="fin-note">투자금은 선택입니다. 넣지 않아도 수익률·위험 비율은 동일하고, 넣으면 그 비율에 금액만 곱해 보여줍니다.</p>
        </section>

        <section class="fin-block fin-block-wide pf-input">
            <h2>조건부 진입 <span class="fin-note">(선택 — 관찰 변수 기준, 전부 만족(AND) 다음 공통 종가에 진입)</span></h2>
            <label><input type="checkbox" id="scn-cond-on" ${state.conditionOn ? 'checked' : ''}> 조건부 진입을 사용합니다</label>
            ${state.conditionOn ? `
            <div id="scn-cond-block">
                ${!state.factors.length ? '<p class="fin-note">조건에 쓰려면 위에서 관찰 변수를 먼저 추가하세요.</p>' : `
                ${renderConditionTree(state.conditionTree, [], state.factors, 0)}
                <div class="pf-add">
                    <label class="pf-row-sub">보유 기간(bar)<br><input type="number" id="scn-holding" class="pf-field" min="1" value="${state.holdingBars}"></label>
                </div>`}
            </div>` : ''}
        </section>

        <div class="pf-actions">
            <button id="scn-run" class="pf-btn pf-btn-primary">실행</button>
            <button id="scn-clear" class="pf-btn pf-btn-ghost">전부 지우기</button>
        </div>
        <p class="fin-note pf-privacy">
            보유·전략·조건·결과는 서버로 나가지 않습니다. 가격 조회에는 종목 심볼만 나갑니다.
            현재가만으로 과거 성과를 만들지 않습니다 — 공개 역사 가격을 조회해 계산합니다.
        </p>
        <div id="scn-out">${resultError ? `
            <div class="fin-block fin-block-wide"><h2>계산하지 못했습니다</h2>
                <p class="fin-p">${finEsc(resultError)}</p></div>` : ''}</div>

        <section class="fin-block fin-block-wide pf-input">
            <h2>여러 시나리오 비교 <span class="fin-note">(선택 — 위 자산·조건은 그대로 두고, 항목별로 재조정 방식·기간만 바꿔 나란히 비교)</span></h2>
            <label><input type="checkbox" id="scn-cmp-on" ${state.compareOn ? 'checked' : ''}> 비교를 사용합니다</label>
            ${state.compareOn ? `
            <div id="scn-cmp-block">
                ${state.variants.length ? `<div class="pf-rows">${state.variants.map((v, i) => `
                    <div class="pf-row">
                        <input type="text" class="pf-field scn-cmp-label" data-i="${i}" placeholder="이름(예: 매일 재조정)" value="${finEsc(v.label || '')}">
                        <select class="pf-field scn-cmp-rebalance" data-i="${i}">
                            <option value="" ${!v.rebalance ? 'selected' : ''}>재조정: 기본과 동일</option>
                            <option value="buy_and_hold" ${v.rebalance === 'buy_and_hold' ? 'selected' : ''}>매수 후 유지</option>
                            <option value="daily" ${v.rebalance === 'daily' ? 'selected' : ''}>매일 재조정</option>
                            <option value="monthly" ${v.rebalance === 'monthly' ? 'selected' : ''}>매월 재조정</option>
                        </select>
                        <input type="date" class="pf-field scn-cmp-start" data-i="${i}" value="${finEsc(v.startDate || '')}" title="시작(선택, 비우면 기본과 동일)">
                        <input type="date" class="pf-field scn-cmp-end" data-i="${i}" value="${finEsc(v.endDate || '')}" title="종료(선택, 비우면 기본과 동일)">
                        <button class="pf-del" data-kind="variant" data-i="${i}" aria-label="삭제">✕</button>
                    </div>`).join('')}</div>` : '<p class="fin-note">아직 없습니다.</p>'}
                <div class="pf-add">
                    <button id="scn-cmp-add" class="pf-btn pf-btn-ghost" ${state.variants.length >= 10 ? 'disabled' : ''}>비교 항목 추가</button>
                    ${state.variants.length ? '<button id="scn-cmp-run" class="pf-btn pf-btn-primary">비교 실행</button>' : ''}
                </div>
                <p class="fin-note">각 항목에서 비운 값은 기본 설정과 같은 값을 씁니다. 최대 10개, 비중은 위 자산 설정을 그대로 씁니다 —
                    비교하려면 위에서 자산에 비중을 입력해 두어야 합니다. 좋은 결과만 골라 쓰면 과적합될 수 있습니다(다중검정 보정 없음).</p>
            </div>` : ''}
        </section>
        <div id="scn-cmp-out">${compareError ? `
            <div class="fin-block fin-block-wide"><h2>비교하지 못했습니다</h2>
                <p class="fin-p">${finEsc(compareError)}</p></div>` : ''}</div>`;

        if (result) renderScenarioResult(host.querySelector('#scn-out'), result, pfGetMode(), resultAlignment);
        if (compareResult) renderScenarioComparison(host.querySelector('#scn-cmp-out'), compareResult.base, compareResult.comparison, pfGetMode(), compareAlignment);
        wire();
    };

    const save = () => pfScnSave(state);

    const wire = () => {
        host.querySelector('#scn-a-add')?.addEventListener('click', async () => {
            const q = host.querySelector('#scn-a-q'), w = host.querySelector('#scn-a-w'), err = host.querySelector('#scn-a-err');
            const weightPct = Number(String(w.value).trim());
            err.textContent = '';
            if (!q.value.trim()) return;
            if (!Number.isFinite(weightPct)) { err.textContent = '비중을 숫자로(%) 입력하세요. 비워두면 0%(매매 없음)로 취급됩니다.'; }
            try {
                const row = await pfScnResolve(q.value, 'asset', pfScnUsedIds(state));
                state.assets.push({ ...row, weightPct: Number.isFinite(weightPct) ? weightPct : 0 });
                save(); paint();
            } catch (e) { err.textContent = e.message; }
        });
        host.querySelector('#scn-f-add')?.addEventListener('click', async () => {
            const q = host.querySelector('#scn-f-q'), change = host.querySelector('#scn-f-change'), err = host.querySelector('#scn-f-err');
            err.textContent = '';
            if (!q.value.trim()) return;
            try {
                const row = await pfScnResolve(q.value, 'factor', pfScnUsedIds(state));
                state.factors.push({ ...row, change: change.value, unit: null });
                save(); paint();
            } catch (e) { err.textContent = e.message; }
        });
        host.querySelector('#scn-b-add')?.addEventListener('click', async () => {
            const q = host.querySelector('#scn-b-q'), err = host.querySelector('#scn-b-err');
            err.textContent = '';
            if (!q.value.trim()) return;
            try {
                state.benchmark = await pfScnResolve(q.value, 'benchmark', pfScnUsedIds(state));
                save(); paint();
            } catch (e) { err.textContent = e.message; }
        });
        host.querySelector('#scn-b-del')?.addEventListener('click', () => { state.benchmark = null; save(); paint(); });
        host.querySelectorAll('.pf-del').forEach((b) => b.addEventListener('click', () => {
            const kind = b.dataset.kind;
            if (kind === 'asset') { const i = Number(b.dataset.i), removedId = state.assets[i].id; state.assets.splice(i, 1);
                state.hypotheses = state.hypotheses.filter((h) => h.assetId !== removedId); }
            else if (kind === 'factor') { const i = Number(b.dataset.i), removedId = state.factors[i].id; state.factors.splice(i, 1);
                state.conditionTree = pfScnPruneFactor(state.conditionTree, removedId);
                state.hypotheses = state.hypotheses.filter((h) => h.factorId !== removedId); }
            else if (kind === 'condleaf' || kind === 'condgroup') {
                const { parent, idx } = pfScnGetParentAndIndex(state.conditionTree, pfScnParsePath(b.dataset.path));
                parent.children.splice(idx, 1);
            }
            else if (kind === 'hyp') state.hypotheses.splice(Number(b.dataset.i), 1);
            else if (kind === 'variant') state.variants.splice(Number(b.dataset.i), 1);
            save(); paint();
        }));
        host.querySelector('#scn-hyp-add')?.addEventListener('click', () => {
            const pair = pfScnNextHypothesisPair(state);
            if (!pair) return;
            state.hypotheses.push({ ...pair, expectedSign: 1 });
            save(); paint();
        });
        host.querySelectorAll('.scn-hyp-asset, .scn-hyp-factor, .scn-hyp-sign').forEach((el) =>
            el.addEventListener('change', () => {
                const h = state.hypotheses[Number(el.dataset.i)];
                if (el.classList.contains('scn-hyp-asset')) h.assetId = el.value;
                else if (el.classList.contains('scn-hyp-factor')) h.factorId = el.value;
                else h.expectedSign = Number(el.value);
                save();
            }));
        host.querySelector('#scn-cond-on')?.addEventListener('change', (e) => { state.conditionOn = e.target.checked; save(); paint(); });
        host.querySelectorAll('.scn-cond-add-leaf').forEach((b) => b.addEventListener('click', () => {
            const group = pfScnNodeAt(state.conditionTree, pfScnParsePath(b.dataset.path));
            if (group.children.length >= 20) return;
            group.children.push(pfScnBlankLeaf(state.factors[0].id));
            save(); paint();
        }));
        host.querySelectorAll('.scn-cond-add-group').forEach((b) => b.addEventListener('click', () => {
            const group = pfScnNodeAt(state.conditionTree, pfScnParsePath(b.dataset.path));
            if (group.children.length >= 20) return;
            group.children.push(pfScnBlankGroup());
            save(); paint();
        }));
        host.querySelectorAll('.scn-cond-groupop').forEach((el) => el.addEventListener('change', () => {
            pfScnNodeAt(state.conditionTree, pfScnParsePath(el.dataset.path)).op = el.value;
            save();
        }));
        host.querySelectorAll('.scn-cond-factor, .scn-cond-lookback, .scn-cond-op, .scn-cond-threshold').forEach((el) =>
            el.addEventListener('change', () => {
                const node = pfScnNodeAt(state.conditionTree, pfScnParsePath(el.dataset.path));
                if (el.classList.contains('scn-cond-factor')) node.factorId = el.value;
                else if (el.classList.contains('scn-cond-lookback')) node.lookbackBars = Math.max(1, Math.round(Number(el.value) || 1));
                else if (el.classList.contains('scn-cond-op')) node.operator = el.value;
                else node.threshold = Number(el.value) || 0;
                save();
            }));
        host.querySelector('#scn-holding')?.addEventListener('change', (e) => {
            state.holdingBars = Math.max(1, Math.round(Number(e.target.value) || 1)); save();
        });
        host.querySelector('#scn-cmp-on')?.addEventListener('change', (e) => { state.compareOn = e.target.checked; save(); paint(); });
        host.querySelector('#scn-cmp-add')?.addEventListener('click', () => {
            if (state.variants.length >= 10) return;
            state.variants.push({ label: '', rebalance: '', startDate: '', endDate: '' });
            save(); paint();
        });
        host.querySelectorAll('.scn-cmp-label, .scn-cmp-rebalance, .scn-cmp-start, .scn-cmp-end').forEach((el) =>
            el.addEventListener('change', () => {
                const i = Number(el.dataset.i), v = state.variants[i];
                if (el.classList.contains('scn-cmp-label')) v.label = el.value;
                else if (el.classList.contains('scn-cmp-rebalance')) v.rebalance = el.value;
                else if (el.classList.contains('scn-cmp-start')) v.startDate = el.value;
                else v.endDate = el.value;
                save();
            }));
        host.querySelector('#scn-cmp-run')?.addEventListener('click', compareRun);
        ['scn-start', 'scn-end', 'scn-holdout'].forEach((id) => host.querySelector(`#${id}`)?.addEventListener('change', (e) => {
            state[{ 'scn-start': 'startDate', 'scn-end': 'endDate', 'scn-holdout': 'holdoutStart' }[id]] = e.target.value; save();
        }));
        host.querySelector('#scn-rebalance')?.addEventListener('change', (e) => { state.rebalance = e.target.value; save(); });
        host.querySelector('#scn-capital')?.addEventListener('input', (e) => {
            const raw = String(e.target.value).replace(/[^0-9]/g, '');
            e.target.value = raw ? Number(raw).toLocaleString('ko-KR') : '';
        });
        host.querySelector('#scn-capital')?.addEventListener('change', (e) => {
            const raw = String(e.target.value).replace(/[^0-9]/g, '');
            state.initialCapital = raw ? Number(raw) : null; save();
        });
        host.querySelector('#scn-clear')?.addEventListener('click', () => {
            if (!confirm('시나리오 입력을 전부 지웁니다. 되돌릴 수 없습니다.')) return;
            Object.assign(state, pfScnBlank());
            result = null; resultError = null; resultAlignment = null;
            compareResult = null; compareError = null; compareAlignment = null;
            save(); paint();
        });
        host.querySelector('#scn-run')?.addEventListener('click', run);
    };

    const run = async () => {
        const out = host.querySelector('#scn-out');
        out.innerHTML = `<div class="fin-block fin-block-wide"><p class="fin-loading" id="scn-prog">계산 준비 중…</p></div>`;
        out.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const prog = () => out.querySelector('#scn-prog');
        try {
            const { input, alignment } = await scenarioBuildInput(state, (msg) => { const p = prog(); if (p) p.textContent = msg; });
            const p = prog(); if (p) p.textContent = '계산 중… (백그라운드)';
            result = await pfScnWorkerCall('run', { input });
            resultError = null;
            resultAlignment = alignment;
        } catch (err) {
            result = null;
            resultError = err.message || String(err);
            resultAlignment = null;
        }
        paint();
    };

    // Runs the base scenario plus each variant override once, side by side --
    // never auto-picks a "winner" (the engine doesn't either: automatic_selection
    // is always false). A variant only overrides rebalance/period; it reuses the
    // exact same assets/factors/weights/condition as the base run above.
    const compareRun = async () => {
        const out = host.querySelector('#scn-cmp-out');
        out.innerHTML = `<div class="fin-block fin-block-wide"><p class="fin-loading" id="scn-cmp-prog">계산 준비 중…</p></div>`;
        out.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const prog = () => out.querySelector('#scn-cmp-prog');
        try {
            const { input, alignment } = await scenarioBuildInput(state, (msg) => { const p = prog(); if (p) p.textContent = msg; });
            if (!input.strategy) throw new Error('비교하려면 위 자산에 비중을 입력해 전략을 정해야 합니다.');
            if (!state.variants.length) throw new Error('비교할 항목을 하나 이상 추가하세요.');
            const variants = state.variants.map((v, i) => {
                const overrides = {};
                if (v.rebalance) overrides.strategy = { ...input.strategy, rebalance: v.rebalance };
                if (v.startDate) overrides.startDate = v.startDate;
                if (v.endDate) overrides.endDate = v.endDate;
                return { id: (v.label || '').trim() || `변형 ${i + 1}`, overrides };
            });
            const p = prog(); if (p) p.textContent = '계산 중… (백그라운드)';
            const { base, comparison } = await pfScnWorkerCall('compare', { input, variants });
            compareResult = { base, comparison };
            compareError = null;
            compareAlignment = alignment;
        } catch (err) {
            compareResult = null;
            compareError = err.message || String(err);
            compareAlignment = null;
        }
        paint();
    };

    paint();
};

// Fetches and aligns public price/FX history for every asset/factor/benchmark
// row (same pfFetchHistory + pfAlign machinery pfCompute uses), converts
// asset/benchmark prices to KRW with dated FX, and leaves factor levels in
// their own units -- then hands the engine already-resolved, already-aligned
// input. No leverage multiplier is applied: a real leveraged ETF's own price
// already carries it (scenario-README: don't multiply it again).
const scenarioBuildInput = async (state, onProgress) => {
    const rows = [...state.assets, ...state.factors, ...(state.benchmark ? [state.benchmark] : [])];
    if (!rows.length) throw new Error('자산 또는 관찰 변수를 하나 이상 추가하세요.');
    if (!state.assets.length) throw new Error('관계만 보더라도 최소 1개 자산이 필요합니다.');

    const needed = new Set();
    for (const r of rows) {
        if (!r.yahoo) throw new Error(`'${r.name_ko}'의 가격 심볼을 확인할 수 없습니다.`);
        needed.add(r.yahoo);
        const fx = pfFxSymbol(r.currency);
        if (fx && r.yahoo !== fx) needed.add(fx);
    }
    let done = 0;
    const fetched = {};
    for (const sym of needed) {
        onProgress && onProgress(`가격 조회 중… ${++done}/${needed.size}`);
        fetched[sym] = await pfFetchHistory(sym, '5y');
    }
    const series = {};
    for (const [sym, j] of Object.entries(fetched)) series[sym] = j.points;
    const { dates: dayNums, cols, perSymbol } = pfAlign(series);
    if (dayNums.length < 3) throw new Error('공통 거래일이 3개 미만이라 계산할 수 없습니다.');
    const isoDates = dayNums.map((d) => new Date(d * 86400000).toISOString().slice(0, 10));

    // Symbols fetched only to convert a currency (not an asset/factor/benchmark
    // in their own right) get their own label so the alignment note can still
    // say why a row's history looked shorter than requested.
    const rowYahoos = new Set(rows.map((r) => r.yahoo));
    const fxOnlySymbols = [...needed].filter((sym) => !rowYahoos.has(sym));
    const alignment = {
        commonCount: dayNums.length,
        rows: [
            ...rows.map((r) => ({ label: r.name_ko, dropped: perSymbol[r.yahoo]?.dropped ?? 0 })),
            ...fxOnlySymbols.map((sym) => ({ label: `환율(${sym})`, dropped: perSymbol[sym]?.dropped ?? 0 })),
        ],
    };

    const toKrw = (row) => {
        const fxSym = pfFxSymbol(row.currency);
        if (row.yahoo === fxSym) return cols[row.yahoo];
        if (fxSym) return cols[row.yahoo].map((v, i) => v * cols[fxSym][i]);
        return cols[row.yahoo];
    };

    const assets = state.assets.map((a) => ({ id: a.id, prices: toKrw(a), baseCurrency: 'KRW',
        priceBasis: 'adjusted_total_return', source: 'yahoo_finance_proxy' }));
    const factors = state.factors.map((f) => ({ id: f.id, values: cols[f.yahoo], change: f.change,
        unit: f.unit || null, source: 'yahoo_finance_proxy', availability: 'known_by_common_close' }));
    const benchmark = state.benchmark ? { id: state.benchmark.id, prices: toKrw(state.benchmark),
        baseCurrency: 'KRW', priceBasis: 'adjusted_total_return', source: 'yahoo_finance_proxy' } : undefined;

    const hasWeights = state.assets.some((a) => a.weightPct);
    const strategy = hasWeights ? {
        weights: state.assets.map((a) => (a.weightPct || 0) / 100), rebalance: state.rebalance,
        initialCapital: state.initialCapital || null,
    } : null;
    let condition = null;
    if (state.conditionOn) {
        const pruned = pfScnPruneEmptyGroups(JSON.parse(JSON.stringify(state.conditionTree)));
        if (pruned) condition = { ...pfScnTreeToCondition(pruned), holdingBars: state.holdingBars };
    }
    const hypotheses = state.hypotheses.map((h) => ({ assetId: h.assetId, factorId: h.factorId, expectedSign: h.expectedSign }));
    const input = { dates: isoDates, baseCurrency: 'KRW', assets, factors, benchmark,
        startDate: state.startDate || undefined, endDate: state.endDate || undefined,
        holdoutStart: state.holdoutStart || undefined, strategy, condition, hypotheses };
    return { input, alignment };
};

const PF_VIEW_KEY = 'portfolioLab.view';
const pfGetView = () => (localStorage.getItem(PF_VIEW_KEY) === 'manual') ? 'manual' : 'report';
const pfSetView = (v) => pfPersist(PF_VIEW_KEY, v);

const renderPortfolioLab = async (host) => {
    host.innerHTML = `<div class="fin-wrap"><p class="fin-loading">불러오는 중…</p></div>`;
    await pfLoadRefs();

    const view = pfGetView();

    host.innerHTML = `
    <div class="fin-wrap">
        <div class="fin-head">
            <h1>포트폴리오 랩</h1>
            <p>시나리오 백테스트로 과거 전략을 연구하거나, 직접 입력으로 지금 보유한 자산의 위험이 어디에 몰려 있는지 봅니다. 어느 쪽도 수익 예측이 아닙니다.</p>
        </div>
        <div class="pf-mode pf-view-tabs" role="tablist" aria-label="보기 방식">
            <button type="button" class="pf-mode-btn ${view === 'report' ? 'on' : ''}" data-view="report">시나리오 백테스트</button>
            <button type="button" class="pf-mode-btn ${view === 'manual' ? 'on' : ''}" data-view="manual">직접 입력</button>
        </div>
        <div id="pf-panel"></div>
    </div>`;

    const panel = host.querySelector('#pf-panel');

    const renderManual = () => {
        panel.innerHTML = `<div id="pf-form"></div><div id="pf-out"></div>`;
        const form = panel.querySelector('#pf-form');
        const out = panel.querySelector('#pf-out');

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
        const saved = pfLoad();
        if (saved && saved.positions.length >= 2) run();
    };

    const renderReport = () => renderScenarioLab(panel);

    host.querySelectorAll('.pf-view-tabs .pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        const v = b.dataset.view;
        if (v === pfGetView()) return;
        pfSetView(v);
        host.querySelectorAll('.pf-view-tabs .pf-mode-btn').forEach((x) => x.classList.toggle('on', x === b));
        if (v === 'manual') renderManual(); else renderReport();
    }));

    if (view === 'manual') renderManual(); else renderReport();
};
