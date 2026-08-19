// Portfolio lab for Global Trade Dashboard -- holdings input, covariance and
// correlation, HRP/IVP allocation, and the risk views.
//
// Split out of app.js (2026-08-20). app.js is shared by parallel sessions and
// a squash merge replaces whole regions instead of diffing them. This domain
// calls nothing outside itself.
//
// Relies on globals still in app.js: finEsc, finPct, and the DOM helpers.

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

const PF_MODE_KEY = 'portfolioLab.mode';
const pfGetMode = () => (localStorage.getItem(PF_MODE_KEY) === 'expert') ? 'expert' : 'basic';
const pfSetMode = (m) => { try { localStorage.setItem(PF_MODE_KEY, m); } catch (_) { /* quota */ } };

const renderPfResult = async (host) => {
    host.innerHTML = `<p class="fin-loading">진단 리포트 불러오는 중…</p>`;

    let data = null;
    for (const path of ['/public/data/portfolio_analysis_v1.json', '/data/portfolio_analysis_v1.json']) {
        try {
            const res = await fetch(path, { cache: 'no-store' });
            if (res.ok) { data = await res.json(); break; }
        } catch (_) { /* try next */ }
    }

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
const pfSetView = (v) => { try { localStorage.setItem(PF_VIEW_KEY, v); } catch (_) { /* quota */ } };

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
