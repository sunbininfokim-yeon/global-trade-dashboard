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
// The engines live outside this file: portfolio risk in
// scripts/금융_재무분석 (portfolio_analysis_v1.json), corporate financials in
// scripts/dart. This side only renders. Per DATA_CONTRACT.md the wording comes
// from the payload's own ui_copy_* block rather than being written here, so the
// engine stays the single source of both the numbers and how they read.
const FIN_LOCALE = 'ko';

const finSignedPct = (x, digits = 1) => {
    if (x === null || x === undefined || Number.isNaN(x)) return '—';
    const v = x * 100;
    return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%p`;
};

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

// Reads the file, resolves each row to a registry/remote instrument, and
// merges the results into the same portfolioLab.v1 list the manual form
// edits -- so the existing holdings list (with its delete buttons) is also
// the review/undo step for anything the importer got wrong.
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
    if (!qtyCol && !valueCol) throw new Error('수량 또는 금액 열을 찾지 못했습니다. 헤더(예: 종목명/수량/금액)를 확인해 주세요.');

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
                종목명·티커 열과 수량 또는 금액 열이 있는 파일이면 헤더 이름은 대략 맞아도 됩니다(예: 종목명/수량/금액, name/qty/value).
                이 브라우저 안에서만 읽습니다 — 파일도, 그 안의 수량·금액도 서버로 올라가지 않습니다. 종목명만 검색에 쓰입니다.
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
            const { added, unresolved } = await pfImportSpreadsheet(file, (msg) => { uploadStatusEl.textContent = msg; });
            pfLastUnresolved = unresolved;
            pfLastUploadStatus = unresolved.length
                ? `${added}건 추가, ${unresolved.length}건 인식 실패`
                : `${added}건 추가했습니다.`;
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

const renderPfResult = async (host) => {
    host.innerHTML = `<p class="fin-loading">진단 리포트 불러오는 중…</p>`;

    const data = await loadFirstJson(finDataPaths('portfolio_analysis_v1.json'));

    if (!data) {
        host.innerHTML = `
            <div class="fin-empty">
                <p class="fin-empty-title">진단 리포트가 없습니다</p>
                <p>로컬에서 <code>scripts/금융_재무분석/run_pipeline.py</code> 를 돌리면
                   <code>public/data/portfolio_analysis_v1.json</code> 이 만들어지고 여기에 표시됩니다.</p>
                <p class="fin-note pf-privacy">이 파일은 <code>.gitignore</code> 처리돼 커밋·배포되지 않습니다 —
                   실제 보유 내역은 본인 컴퓨터에만 남고, 대시보드 운영자를 포함해 누구에게도 전송되지 않습니다.</p>
            </div>`;
        return;
    }

    const mode = pfGetMode();
    const u = (mode === 'expert' ? data[`ui_copy_${FIN_LOCALE}`] : data[`ui_copy_basic_${FIN_LOCALE}`])
        || data[`ui_copy_${FIN_LOCALE}`] || {};
    const S = (k) => u[`${k}_${FIN_LOCALE}`];
    const cards = u.metric_cards || [];
    const breaches = (data.profile_check && data.profile_check[`breaches_${FIN_LOCALE}`]) || S('profile_breaches') || [];
    const movesUp = S('moves_up') || [];
    const movesDown = S('moves_down') || [];
    const proxies = (data.data_quality && data.data_quality.proxies) || [];
    const dq = data.data_quality || {};

    const baseCcy = data.base_currency || 'KRW';
    const acct = data.accounting || null;
    const cash = data.cash_breakdown || null;
    const nav = acct ? (acct.net_asset_value ?? null) : null;
    const gross = acct ? (acct.gross_exposure ?? null) : null;
    const grossOfNav = acct ? (acct.gross_exposure_of_nav ?? null) : null;
    const creditUsed = acct ? (acct.credit_used ?? null) : null;
    const varShort = data.risk && data.risk.short;
    const varOfNav = varShort ? (varShort.var_10d_95 ?? null) : null;
    const sizeGuide = data.size_guide || null;

    host.innerHTML = `
        <div class="pf-mode" role="group" aria-label="보기 수준">
            <button type="button" class="pf-mode-btn ${mode === 'basic' ? 'on' : ''}" data-mode="basic">기본</button>
            <button type="button" class="pf-mode-btn ${mode === 'expert' ? 'on' : ''}" data-mode="expert">전문가</button>
        </div>

        <div class="fin-head fin-head-sub">
            <p class="fin-headline">${finEsc(S('headline'))}</p>
            <div class="fin-meta">
                <span class="fin-chip">${finEsc(u.profile?.[`label_${FIN_LOCALE}`] || data.risk_profile_id)}</span>
                <span>${finEsc(u.profile?.[`blurb_${FIN_LOCALE}`] || '')}</span>
                <span class="fin-meta-sep">·</span>
                <span>기준통화 ${finEsc(baseCcy)}</span>
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

        ${(nav !== null || gross !== null || varOfNav !== null) ? `
        <div class="fin-cards">
            ${nav !== null ? `
            <div class="fin-card">
                <span class="fin-card-title">순자산(NAV)</span>
                <span class="fin-card-value">${finEsc(baseCcy)} ${Number(nav).toLocaleString()}</span>
                ${creditUsed ? `<p class="fin-card-plain">신용·미수 ${finEsc(baseCcy)} ${Number(creditUsed).toLocaleString()}은 이미 뺀 값입니다.</p>` : ''}
            </div>` : ''}
            ${gross !== null ? `
            <div class="fin-card">
                <span class="fin-card-title">총 노출(gross)</span>
                <span class="fin-card-value">${finEsc(baseCcy)} ${Number(gross).toLocaleString()}${(grossOfNav !== null) ? ` · NAV 대비 ${finPct(grossOfNav)}` : ''}</span>
                <p class="fin-card-plain">공매도·신용을 포함한 총 노출입니다. NAV와 다를 수 있습니다.</p>
            </div>` : ''}
            ${varOfNav !== null ? `
            <div class="fin-card">
                <span class="fin-card-title">10일 VaR (95%, NAV 대비)</span>
                <span class="fin-card-value">${finPct(varOfNav)}</span>
            </div>` : ''}
        </div>` : ''}

        ${cash ? `
        <section class="fin-block fin-block-wide">
            <h2>현금 구성</h2>
            <p class="fin-p">
                성향 현금(${finEsc(baseCcy)}) ${finPct(cash.base_cash_weight_of_nav)}
                · 외화 현금(환위험) ${finPct(cash.foreign_cash_weight_of_nav)}
            </p>
            <p class="fin-note">${finEsc(cash.policy_ko || '성향 현금 밴드는 기준통화 현금만 검사합니다. 외화 현금은 환율 노출로 별도 표시됩니다.')}</p>
        </section>` : ''}

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
            ${sizeGuide ? `<p class="fin-note">${finEsc(sizeGuide[`footnote_${FIN_LOCALE}`] || '')}
               (보유 ${sizeGuide.vs_actual?.n_names ?? '—'}종 · 권장 ${sizeGuide.names_min ?? '—'}–${sizeGuide.names_max ?? '—'}종)</p>` : ''}
            ${proxies.length ? `<p class="fin-proxy">프록시 사용: ${proxies.map((p) =>
                finEsc(typeof p === 'string' ? p : (p.name_ko || p.id || JSON.stringify(p)))).join(' · ')}</p>` : ''}
            <p class="fin-engine">엔진: <code>scripts/금융_재무분석</code> ·
               방식: ${finEsc((data.advice && data.advice.method) || '')} ·
               스키마 ${finEsc(data.schema_version || '')}</p>
            <p class="pf-privacy">이 리포트는 로컬 파일만 읽습니다 — 서버에 저장되지 않고, 대시보드 운영자는 이 데이터를 볼 수 없습니다.</p>
        </div>`;

    host.querySelectorAll('.pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.mode === mode) return;
        pfSetMode(b.dataset.mode);
        renderPfResult(host);
    }));
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
            <h1>포트폴리오 진단</h1>
            <p>보유 자산의 위험이 어디에 몰려 있는지 봅니다. 수익 예측이 아닙니다.</p>
        </div>
        <div class="pf-mode pf-view-tabs" role="tablist" aria-label="보기 방식">
            <button type="button" class="pf-mode-btn ${view === 'report' ? 'on' : ''}" data-view="report">진단 리포트</button>
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

    const renderReport = () => renderPfResult(panel);

    host.querySelectorAll('.pf-view-tabs .pf-mode-btn').forEach((b) => b.addEventListener('click', () => {
        const v = b.dataset.view;
        if (v === pfGetView()) return;
        pfSetView(v);
        host.querySelectorAll('.pf-view-tabs .pf-mode-btn').forEach((x) => x.classList.toggle('on', x === b));
        if (v === 'manual') renderManual(); else renderReport();
    }));

    if (view === 'manual') renderManual(); else renderReport();
};
