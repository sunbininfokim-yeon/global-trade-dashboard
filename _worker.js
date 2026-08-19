export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);

        // API Route: UN Comtrade Proxy
        if (url.pathname.startsWith('/api/comtrade')) {
            return await handleComtrade(request, env, ctx);
        }

        // API Route: USDA NASS Quick Stats Proxy
        if (url.pathname.startsWith('/api/usda-nass')) {
            return await handleUsdaNass(request, env, ctx);
        }

        // API Route: USDA FAS PSD (Production, Supply & Distribution) Proxy
        if (url.pathname.startsWith('/api/usda-fas')) {
            return await handleUsdaFas(request, env, ctx);
        }

        // API Route: USDA FAS ESR (weekly US export sales by destination)
        if (url.pathname.startsWith('/api/usda-esr/commodities')) {
            return await handleUsdaEsrCommodities(request, env);
        }
        if (url.pathname.startsWith('/api/usda-esr')) {
            return await handleUsdaEsr(request, env, ctx);
        }

        // Macro monitor, sliced per country (see handleMacroMonitor).
        // Must precede /api/macro: these are prefix matches, and the shorter
        // one swallows this path otherwise.
        if (url.pathname.startsWith('/api/macro-monitor')) {
            return await handleMacroMonitor(request, env);
        }

        // API Route: Macro Financial Data Proxy (FRED, BOK, EIA, Yahoo Finance)
        if (url.pathname.startsWith('/api/macro')) {
            return await handleMacro(request, env, ctx);
        }

        // Commodity / diplomacy ticker (RSS model snapshot + IP-locale display)
        if (url.pathname.startsWith('/api/ticker')) {
            return await handleTicker(request, env);
        }

        // Official macro / QRA / Beige Book / priority reporters
        if (url.pathname.startsWith('/api/liquidity')) {
            return await handleLiquidity(request, env);
        }

        // Instrument lookup + daily price history for the portfolio panel
        if (url.pathname.startsWith('/api/quote')) {
            return await handleQuote(request, env);
        }

        // Front-month futures quote for the commodity currently on screen
        if (url.pathname.startsWith('/api/futures')) {
            return await handleFutures(request, env);
        }

        // Filed financial statements for the company calculator
        if (url.pathname.startsWith('/api/financials')) {
            return await handleFinancials(request, env);
        }

        // Live OpenDART lookup for KRX-listed filers with no pre-generated
        // kfa_<code>_v1.json snapshot (see handleDartFinancials).
        if (url.pathname.startsWith('/api/dart-financials')) {
            return await handleDartFinancials(request, env);
        }

        // Multi-country official reports (US/JP/CN/EU…)
        if (url.pathname.startsWith('/api/official-reports')) {
            return await handleOfficialReports(request, env);
        }

        // Default: Serve Static Assets
        return serveAsset(request, env);
    },

    // Cron-driven cache warm-up (see "triggers" in wrangler.jsonc).
    // Without this the first visitor to open each commodity pays the full
    // UN Comtrade round trip -- half a minute on a 60+ country query. Each run
    // fills the commodities that have gone cold, up to a budget; see
    // warmComtradeCache for why it does not refill all of them at once.
    async scheduled(event, env, ctx) {
        ctx.waitUntil(warmComtradeCache(env));
    }
};

// One commodity costs ceil(76 reporters / REPORTER_CHUNK_SIZE) upstream calls,
// and a Worker invocation may only make so many subrequests. Refilling every
// commodity in a single run exceeded that once the metals were added, and the
// overflow fails silently inside waitUntil -- the tail of the list would simply
// never warm, with nothing in the metrics to say so. Capping the run keeps each
// tick inside the ceiling; whatever is left stays cold until the next tick
// (four a day, see wrangler.jsonc) and gets picked up then, because entries
// already in KV are skipped.
const WARM_FETCH_BUDGET = 8;

async function warmComtradeCache(env) {
    if (!env.COMTRADE_API_KEY || !env.API_CACHE) {
        console.log('[warm] skipped: COMTRADE_API_KEY or API_CACHE binding missing');
        return;
    }

    // One listing instead of a lookup per commodity: KV list returns names
    // without values, so this stays cheap no matter how large the entries are.
    const warm = new Set();
    let cursor;
    do {
        const page = await env.API_CACHE.list({ prefix: 'comtrade:A:', cursor }).catch(() => null);
        if (!page) break;
        for (const k of page.keys) warm.add(k.name);
        cursor = page.list_complete ? null : page.cursor;
    } while (cursor);

    let filled = 0, fresh = 0, failed = 0, deferred = 0;

    // Sequential on purpose: firing these at once risks tripping Comtrade's
    // rate limiting, and the cron run has no deadline pressure.
    for (const hs of Object.keys(COMTRADE_TTL)) {
        const key = comtradeCacheKey(hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, COMTRADE_PERIOD, 'A');
        if (warm.has(key)) { fresh++; continue; }
        if (filled >= WARM_FETCH_BUDGET) { deferred++; continue; }

        try {
            const result = await fetchComtrade(env, hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, COMTRADE_PERIOD, 'A');
            if (!result.ok) {
                failed++;
                console.log(`[warm] ${hs} upstream ${result.status}`);
                continue;
            }
            await env.API_CACHE.put(key, JSON.stringify(result.body), { expirationTtl: COMTRADE_TTL[hs] });
            filled++;
        } catch (err) {
            failed++;
            console.log(`[warm] ${hs} error: ${err.message}`);
        }
    }

    console.log(`[warm] done: ${filled} filled, ${fresh} already warm, ${deferred} deferred, ${failed} failed`);
}

const JSON_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
};

function missingKey(name) {
    return new Response(
        JSON.stringify({ error: `Server misconfiguration: ${name} is not set.` }),
        { status: 500, headers: JSON_HEADERS }
    );
}

// --- Commodity ticker ------------------------------------------------------------
// Snapshot is built offline/CI by scripts/commodity_news/build_ticker.py into
// public/data/ticker_v1.json. This handler only applies visitor-locale display
// rules: main line stays Korean; original title is preferred when the visitor
// IP language matches the article language.
async function handleTicker(request, env) {
    const url = new URL(request.url);
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '24', 10) || 24, 80);
    const forcedLang = (url.searchParams.get('lang') || '').trim();

    let doc = null;
    // Prefer ASSETS (static deploy path). Try both common prefixes used by the app.
    const candidates = [
        '/public/data/ticker_v1.json',
        '/data/ticker_v1.json',
        'public/data/ticker_v1.json',
    ];
    for (const path of candidates) {
        try {
            const assetUrl = new URL(path.startsWith('/') ? path : `/${path}`, url.origin);
            const res = await env.ASSETS.fetch(new Request(assetUrl.toString()));
            if (res.ok) {
                doc = await res.json();
                break;
            }
        } catch (_) {
            // try next
        }
    }
    if (!doc && env.API_CACHE) {
        try {
            const cached = await env.API_CACHE.get('ticker:v1', 'json');
            if (cached) doc = cached;
        } catch (_) { /* ignore */ }
    }
    if (!doc) {
        return new Response(
            JSON.stringify({
                error: 'ticker_v1.json not found — run scripts/commodity_news/build_ticker.py',
                items: [],
            }),
            { status: 404, headers: JSON_HEADERS }
        );
    }

    const ipCountry = (request.cf && request.cf.country) || url.searchParams.get('country') || '';
    const ipMap = (doc.model && doc.model.ip_lang_map) || {};
    const defaultLang = (doc.model && doc.model.default_lang) || 'en';
    const mainLang = (doc.model && doc.model.main_display_lang) || 'ko';
    const visitorLang = forcedLang || ipMap[ipCountry] || defaultLang;

    const items = (doc.items || []).slice(0, limit).map((it) => {
        const origLang = (it.title && it.title.original_lang) || 'en';
        const original = (it.title && it.title.original) || '';
        const ko = (it.title && it.title.ko) || null;
        const langMatches =
            visitorLang === origLang ||
            (visitorLang && origLang && visitorLang.split('-')[0] === origLang.split('-')[0]);
        const display_title = langMatches ? original : (ko || original);
        return {
            ...it,
            display_lang: langMatches ? origLang : (ko ? mainLang : origLang),
            display_title,
            title_ko: ko,
            visitor_lang: visitorLang,
            visitor_country: ipCountry || null,
        };
    });

    return new Response(
        JSON.stringify({
            schema_version: doc.schema_version,
            generated_at: doc.generated_at,
            model: doc.model,
            stats: doc.stats,
            visitor: { country: ipCountry || null, lang: visitorLang, main_lang: mainLang },
            items,
        }),
        {
            status: 200,
            headers: {
                ...JSON_HEADERS,
                // Revalidate often; snapshot itself is rebuilt by Actions.
                'Cache-Control': 'public, max-age=120',
            },
        }
    );
}

// Official liquidity intel (QRA, Beige Book, priority reporters).
// Built offline by scripts/macro_intel/build_liquidity.py.
async function handleLiquidity(request, env) {
    const url = new URL(request.url);
    let doc = null;
    const candidates = [
        '/public/data/liquidity_intel_v1.json',
        '/data/liquidity_intel_v1.json',
        'public/data/liquidity_intel_v1.json',
    ];
    for (const path of candidates) {
        try {
            const assetUrl = new URL(path.startsWith('/') ? path : `/${path}`, url.origin);
            const res = await env.ASSETS.fetch(new Request(assetUrl.toString()));
            if (res.ok) {
                doc = await res.json();
                break;
            }
        } catch (_) { /* next */ }
    }
    if (!doc) {
        return new Response(
            JSON.stringify({
                error: 'liquidity_intel_v1.json missing — run scripts/macro_intel/build_liquidity.py',
                liquidity: null,
                ticker_items: [],
            }),
            { status: 404, headers: JSON_HEADERS }
        );
    }
    return new Response(JSON.stringify(doc), {
        status: 200,
        headers: { ...JSON_HEADERS, 'Cache-Control': 'public, max-age=120' },
    });
}

// Official multi-country report intel snapshot.
async function handleOfficialReports(request, env) {
    const url = new URL(request.url);
    let doc = null;
    const candidates = [
        '/public/data/official_reports_v1.json',
        '/data/official_reports_v1.json',
        'public/data/official_reports_v1.json',
    ];
    for (const path of candidates) {
        try {
            const assetUrl = new URL(path.startsWith('/') ? path : `/${path}`, url.origin);
            const res = await env.ASSETS.fetch(new Request(assetUrl.toString()));
            if (res.ok) {
                doc = await res.json();
                break;
            }
        } catch (_) { /* next */ }
    }
    if (!doc) {
        return new Response(
            JSON.stringify({
                error: 'official_reports_v1.json missing — run scripts/official_reports/build_reports.py build',
                ticker_items: [],
                indicators: [],
            }),
            { status: 404, headers: JSON_HEADERS }
        );
    }
    return new Response(JSON.stringify(doc), {
        status: 200,
        headers: { ...JSON_HEADERS, 'Cache-Control': 'public, max-age=180' },
    });
}

// Shared response cache backed by the API_CACHE KV namespace.
//
// A Cache-Control header on a Response the Worker returns only tells the
// *visitor's browser* it may reuse that response -- Cloudflare does not
// automatically cache Worker output at the edge just because the header is set.
// Without KV, every visitor arrives with an empty browser cache and triggers a
// fresh upstream call, so API usage scales with visitor count. That matters for
// keys like USDA FAS, capped at 50 requests/day per IP -- and every visitor
// shares this Worker's egress IP, so that cap applies to the whole site at once.
// Storing responses in KV makes them genuinely shared across all visitors.
//
// `doFetch` must resolve to { ok, status, statusText, body }, where `body` is
// the already-parsed JSON to cache.
async function kvCachedJson(env, cacheKey, ttlSeconds, doFetch) {
    const kv = env.API_CACHE;

    if (kv) {
        // A cache read must never be able to fail the request -- an over-long
        // key or a KV hiccup should degrade to a live fetch, not a 500.
        try {
            const cached = await kv.get(cacheKey);
            if (cached !== null) {
                return new Response(cached, { headers: { ...JSON_HEADERS, "X-Cache": "HIT" } });
            }
        } catch (err) {
            console.log(`[cache] get failed for ${cacheKey}: ${err.message}`);
        }
    }

    const result = await doFetch();
    if (!result.ok) {
        return new Response(
            JSON.stringify({ error: `Upstream error: ${result.status}${result.statusText ? ' ' + result.statusText : ''}` }),
            { status: 502, headers: JSON_HEADERS }
        );
    }

    const json = JSON.stringify(result.body);
    if (kv) {
        // Never let a cache write failure take down a request that already has
        // its data -- serve the response and just skip caching this time.
        try {
            await kv.put(cacheKey, json, { expirationTtl: ttlSeconds });
        } catch (err) {
            console.log(`[cache] put failed for ${cacheKey}: ${err.message}`);
        }
    }
    return new Response(json, { headers: { ...JSON_HEADERS, "X-Cache": "MISS" } });
}

// Canonical reporter/partner list, mirroring M49_MAP in data.js.
// The Worker owns this rather than the browser so the scheduled warm-up and a
// live page request build byte-identical cache keys -- if the two lists ever
// drifted, every "warmed" entry would be a key nobody reads.
// 842 is the US: Comtrade reports US trade as "USA, PR and USVI" (842), and
// querying the plain geographic code 840 returns zero rows.
//
// Five more countries carry the same trap, found by noticing they never once
// appeared as reporter or partner across ~22,000 rows spanning 8 commodities:
// France 250->251, India 356->699, Norway 578->579, Taiwan 158->490
// ("Other Asia, nes"), Switzerland 756->757 (this one alone was erasing
// ~$60B of gold trade -- the map's own "top exporter: Switzerland" label
// pointed at a country the map could never draw a route for). Old codes stay
// in the list so any legacy cache entry still resolves; see M49_MAP in
// data.js for the matching name table. Also added seven producers that were
// invisible even as a trading partner, not filtered out: Gabon (266,
// manganese ore), Mozambique (508) and Madagascar (450, graphite), Zambia
// (894) and Finland (246, cobalt), Bolivia (68, refined tin), Rwanda
// (646, tin concentrate).
const DEFAULT_M49_CODES = "842,840,156,76,32,643,804,699,356,124,36,251,250,276,360,458,764,704,818,484,392,410,826,380,724,792,682,784,710,566,586,50,608,364,12,504,616,528,56,757,756,170,604,152,554,398,642,348,112,600,858,231,800,634,579,578,368,344,180,490,158,404,834,104,116,384,288,686,860,266,508,450,894,246,68,646";

// Every commodity the dashboard can show, keyed by HS code -> cache TTL.
// Doubles as the work list for the scheduled cache warm-up.
const COMTRADE_TTL = {
    "2709": 172800,  // Oil: 48h
    "2711": 172800,  // Gas: 48h
    "2701": 604800,  // Thermal coal: weekly
    "2704": 604800,  // Met coal: weekly
    "7108": 86400,   // Gold: 24h
    "7106": 86400,   // Silver: 24h
    "7403": 86400,   // Copper: 24h
    "7901": 604800,  // Zinc: weekly
    "7601": 604800,  // Aluminum: weekly
    "1001": 1209600, // Wheat: 14 days
    "1005": 1209600, // Corn: 14 days
    "1201": 1209600, // Soybeans: 14 days
    "1701": 1209600, // Sugar: 14 days
    "0901": 1209600, // Coffee: 14 days

    // Battery and steel-chain minerals. Annual Comtrade data that moves once a
    // year, so a week of staleness costs nothing.
    "7502": 604800,  // Nickel
    "8105,2822,283329": 604800, // Cobalt: mattes + oxides/hydroxides + sulphate
    "283691,2530,282520": 604800, // Lithium: carbonate + spodumene ore + hydroxide
    "2504,3801": 604800, // Graphite: natural + artificial
    "280530": 604800,// Rare earths
    "2601": 604800,  // Iron ore
    "2602,720211,720219": 604800, // Manganese: ore + ferromanganese
    "2610,720241,720249": 604800, // Chromium: ore + ferrochromium
    "8001,2609": 604800, // Tin: unwrought metal + ore/concentrate
    "7801": 604800,  // Lead
    "7110": 604800   // Platinum group
};

const COMTRADE_PERIOD = "2023";

// USDA FAS Export Sales Report: weekly US export sales by destination country.
// This is US-only -- it answers "who bought from the US this week", not who
// bought from Brazil. Its value over Comtrade is freshness: Comtrade's annual
// feed lags by a year, ESR lands weekly.
async function fetchEsrCountries(env) {
    // Country list is effectively static; cache it hard so the weekly export
    // pull doesn't burn two calls against the 50/day FAS quota every time.
    const cached = env.API_CACHE ? await env.API_CACHE.get('esr:countries', 'json').catch(() => null) : null;
    if (cached) return cached;

    const res = await fetch('https://api.fas.usda.gov/api/esr/countries', {
        headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" }
    });
    if (!res.ok) return null;

    const map = {};
    for (const c of await res.json()) {
        map[c.countryCode] = {
            // FAS pads these to fixed width; trim so they render cleanly.
            name: (c.countryDescription || c.countryName || '').trim(),
            iso3: c.gencCode || null
        };
    }
    if (env.API_CACHE) {
        await env.API_CACHE.put('esr:countries', JSON.stringify(map), { expirationTtl: 2592000 }).catch(() => {});
    }
    return map;
}

/**
 * The commodity list FAS itself publishes, so callers can map a name to a code
 * instead of guessing. Cached for a week -- this list changes about never.
 */
/**
 * Static assets, with HTML held out of every cache.
 *
 * A deployed update was not reaching visitors: the site was serving
 * `cache-control: public, max-age=0, must-revalidate` for index.html and
 * Cloudflare was still answering `cf-cache-status: HIT`. Reloading the page --
 * or opening a shared portfolio link a second time -- returned the previous
 * build, whose <script src="app.js?v=..."> pointed at the previous bundle. The
 * versioned query strings only bust caches if the HTML naming them is fresh.
 *
 * So HTML is `no-store`: it is small, it changes on every deploy, and it is the
 * one file that decides which version of everything else the browser loads.
 * Fingerprinted assets keep their long cache, which is where caching earns its
 * keep anyway.
 */
async function serveAsset(request, env) {
    const res = await env.ASSETS.fetch(request);
    const type = res.headers.get('content-type') || '';
    if (!type.includes('text/html')) return res;

    const headers = new Headers(res.headers);
    headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    headers.set('CDN-Cache-Control', 'no-store');
    headers.set('Pragma', 'no-cache');
    // Lets anyone confirm which build they are looking at without guessing.
    headers.set('X-Deployed-At', new Date().toISOString());
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

async function handleUsdaEsrCommodities(request, env) {
    if (!env.USDA_FAS_API_KEY) return missingKey('USDA_FAS_API_KEY');
    const body = await kvCachedJson(env, 'usda-esr:commodities', 604800, async () => {
        const res = await fetch('https://api.fas.usda.gov/api/esr/commodities', {
            headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" }
        });
        if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };
        return { ok: true, body: await res.json() };
    });
    return body;
}

/** Market year for a Sep-start commodity. Wheat starts in June -- see below. */
function currentEsrMarketYear() {
    const now = new Date();
    return String(now.getUTCFullYear() + (now.getUTCMonth() >= 8 ? 1 : 0));
}

async function handleUsdaEsr(request, env, ctx) {
    const url = new URL(request.url);

    if (!env.USDA_FAS_API_KEY) return missingKey('USDA_FAS_API_KEY');

    // Reject unknown params instead of ignoring them.
    //
    // `commodityCode` used to fall back to 801 (soybeans) whenever it was
    // absent, so a caller asking for `?commodity=corn` -- a plausible typo, and
    // the exact one made while wiring the UI -- got a full, valid-looking
    // soybean series it would then have labelled as corn. Silently serving the
    // wrong commodity is worse than an error, so this now fails loudly and
    // points at the list endpoint.
    const commodityCode = url.searchParams.get('commodityCode');
    if (!commodityCode) {
        return new Response(JSON.stringify({
            error: "commodityCode is required",
            hint: "GET /api/usda-esr/commodities for the code list. There is no default: "
                + "a wrong default silently mislabels one commodity as another.",
        }), { status: 400, headers: JSON_HEADERS });
    }

    // Market year is derived, not pinned. It was hardcoded to '2025', which is
    // why every response carried a weekEndingDate almost a year stale.
    // Caveat: this assumes a September market-year start (corn, soybeans).
    // Wheat's runs June-May, so wheat callers should pass marketYear explicitly
    // between June and August.
    const marketYear = url.searchParams.get('marketYear') || currentEsrMarketYear();

    const SAFE = /^[0-9]+$/;
    if (!SAFE.test(commodityCode) || !SAFE.test(marketYear)) {
        return new Response(
            JSON.stringify({ error: "commodityCode and marketYear must be numeric" }),
            { status: 400, headers: JSON_HEADERS }
        );
    }

    // ESR publishes once a week, so a 24h cache is plenty and keeps us well
    // inside the 30/hour, 50/day per-IP FAS limit that the whole site shares.
    return kvCachedJson(env, `usda-esr:${commodityCode}:${marketYear}`, 86400, async () => {
        try {
            const res = await fetch(
                `https://api.fas.usda.gov/api/esr/exports/commodityCode/${commodityCode}/allCountries/marketYear/${marketYear}`,
                { headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" } }
            );
            if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };

            const rows = await res.json();
            if (!Array.isArray(rows) || rows.length === 0) {
                return { ok: true, body: { weekEndingDate: null, count: 0, data: [] } };
            }

            // The feed is one row per country per week for the whole season.
            // Only the most recent week is useful for a map, and returning just
            // that keeps the payload ~200 rows instead of ~2,600.
            let latest = '';
            for (const r of rows) {
                if (r.weekEndingDate > latest) latest = r.weekEndingDate;
            }

            const countries = await fetchEsrCountries(env);

            const data = [];
            for (const r of rows) {
                if (r.weekEndingDate !== latest) continue;
                const meta = countries ? countries[r.countryCode] : null;
                data.push({
                    countryCode: r.countryCode,
                    countryName: meta ? meta.name : null,
                    iso3: meta ? meta.iso3 : null,
                    weeklyExports: r.weeklyExports,
                    accumulatedExports: r.accumulatedExports,
                    outstandingSales: r.outstandingSales,
                    currentMYTotalCommitment: r.currentMYTotalCommitment
                });
            }
            data.sort((a, b) => (b.accumulatedExports || 0) - (a.accumulatedExports || 0));

            return { ok: true, body: { weekEndingDate: latest, count: data.length, data } };
        } catch (err) {
            return { ok: false, status: 502, statusText: err.message };
        }
    });
}

// KV keys are capped at 512 bytes. Embedding the country lists verbatim put a
// 64-country key at 518 bytes, so kv.get() threw before any fetch ran -- the
// request died as Cloudflare error 1101 in ~250ms and the map lost every line.
// (62 countries came to 502 bytes and worked, which is why the break looked
// like a country-count limit.) Hash any non-default list instead so the key
// stays short no matter how long the list grows.
function shortHash(str) {
    // FNV-1a, 32-bit -- short, stable, and enough to separate cache entries.
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(36);
}

// Bumped whenever DEFAULT_M49_CODES changes. The 'default' scope below
// collapses the whole reporter/partner list to a literal token -- cheap, but
// it means the cache key for the default list never changes on its own even
// when the list's *contents* do, so a code fix (e.g. Switzerland 756->757)
// would keep serving the pre-fix cached payload for up to COMTRADE_TTL
// without this. Bump on any DEFAULT_M49_CODES edit; nothing else needs to.
const DEFAULT_SCOPE_VERSION = 2;

function comtradeCacheKey(hs, reporters, partners, period, freq) {
    const scope = (reporters === DEFAULT_M49_CODES && partners === DEFAULT_M49_CODES)
        ? `default${DEFAULT_SCOPE_VERSION}`
        : shortHash(`${reporters}|${partners}`);
    return `comtrade:${freq}:${hs}:${period}:${scope}`;
}

// Comtrade returns 47 fields per row; the map only ever reads these five.
// Keeping the rest ballooned a 64-country query past what the Worker could
// parse, stringify and hand to KV in one request -- it threw (error 1101) and
// every trade line vanished. Slimming here cuts the payload to ~10% and keeps
// the limit far away as the country list grows.
// "period" is carried so monthly rows stay distinguishable (e.g. 202403);
// on annual queries it is just the year and costs almost nothing.
const COMTRADE_FIELDS = ["reporterCode", "partnerCode", "flowCode", "primaryValue", "netWgt", "period"];

function slimComtradeBody(body) {
    const rows = Array.isArray(body?.data) ? body.data : [];
    return {
        count: rows.length,
        data: rows.map(row => {
            const slim = {};
            for (const f of COMTRADE_FIELDS) slim[f] = row[f];
            return slim;
        })
    };
}

// Reporters per upstream request. A single 64-reporter query returns ~2 MB of
// JSON, and parsing that in one go blew a Worker limit -- the isolate was killed
// before any catch could run (opaque Cloudflare error 1101), so /api/comtrade
// 500'd and every trade line vanished. Chunking keeps each parse small and lets
// the previous chunk's full response be collected before the next arrives.
const REPORTER_CHUNK_SIZE = 16;

async function fetchComtradeChunk(env, hs, reporters, partners, period, freq) {
    // freq A = annual (period "2023"), M = monthly (period "202403").
    // X = Exports, M = Imports (mirror data, so non-reporting countries still appear)
    const comtradeUrl = `https://comtradeapi.un.org/data/v1/get/C/${freq}/HS?reporterCode=${reporters}&period=${period}&partnerCode=${partners}&cmdCode=${hs}&flowCode=X,M`;

    const res = await fetch(comtradeUrl, {
        headers: {
            "Ocp-Apim-Subscription-Key": env.COMTRADE_API_KEY,
            "Accept": "application/json"
        }
    });

    if (!res.ok) {
        return { ok: false, status: res.status, statusText: res.statusText };
    }
    // Slim immediately so only the five needed fields per row are retained.
    return { ok: true, rows: slimComtradeBody(await res.json()).data };
}

async function fetchComtrade(env, hs, reporters, partners, period, freq) {
    const codes = reporters.split(',').filter(Boolean);
    const merged = [];

    try {
        for (let i = 0; i < codes.length; i += REPORTER_CHUNK_SIZE) {
            const chunk = codes.slice(i, i + REPORTER_CHUNK_SIZE).join(',');
            const result = await fetchComtradeChunk(env, hs, chunk, partners, period, freq);

            // One bad chunk shouldn't discard the countries that did come back.
            if (!result.ok) {
                if (merged.length === 0) return result;
                console.log(`[comtrade] ${hs} chunk ${i} failed: ${result.status}`);
                continue;
            }
            for (const row of result.rows) merged.push(row);
        }
    } catch (err) {
        // Catchable failures (bad JSON, network) surface as a labelled 502
        // rather than an opaque 1101 with an empty map behind it.
        if (merged.length === 0) return { ok: false, status: 502, statusText: err.message };
        console.log(`[comtrade] ${hs} partial result after error: ${err.message}`);
    }

    return { ok: true, body: { count: merged.length, data: merged } };
}

async function handleComtrade(request, env, ctx) {
    const url = new URL(request.url);
    const hs = url.searchParams.get('hs') || '2709';
    const reporters = url.searchParams.get('reporters') || DEFAULT_M49_CODES;
    const partners = url.searchParams.get('partners') || DEFAULT_M49_CODES;
    // freq=M returns monthly rows (period must then look like "202403").
    const freq = url.searchParams.get('freq') === 'M' ? 'M' : 'A';
    const period = url.searchParams.get('period') || (freq === 'M' ? '202403' : COMTRADE_PERIOD);

    if (!env.COMTRADE_API_KEY) return missingKey('COMTRADE_API_KEY');

    const cacheTtl = COMTRADE_TTL[hs] || 604800; // Default: weekly

    return kvCachedJson(env, comtradeCacheKey(hs, reporters, partners, period, freq), cacheTtl,
        () => fetchComtrade(env, hs, reporters, partners, period, freq));
}

async function handleUsdaNass(request, env, ctx) {
    const url = new URL(request.url);

    const NASS_KEY = env.USDA_NASS_API_KEY;
    if (!NASS_KEY) return missingKey('USDA_NASS_API_KEY');

    // Forward the caller's query params, then attach the key server-side.
    const nassParams = new URLSearchParams(url.searchParams);
    nassParams.set('key', NASS_KEY);
    nassParams.set('format', nassParams.get('format') || 'JSON');

    // Cache key is built from the caller's params only, never the secret.
    const cacheKey = `usda-nass:${new URLSearchParams(url.searchParams).toString()}`;

    return kvCachedJson(env, cacheKey, 86400, async () => {
        const nassUrl = `https://quickstats.nass.usda.gov/api/api_GET/?${nassParams.toString()}`;
        const nassRes = await fetch(nassUrl, { headers: { "Accept": "application/json" } });

        if (!nassRes.ok) {
            return { ok: false, status: nassRes.status, statusText: nassRes.statusText };
        }
        return { ok: true, body: await nassRes.json() };
    });
}

async function handleUsdaFas(request, env, ctx) {
    const url = new URL(request.url);

    const FAS_KEY = env.USDA_FAS_API_KEY;
    if (!FAS_KEY) return missingKey('USDA_FAS_API_KEY');

    const commodityCode = url.searchParams.get('commodityCode');
    const countryCode = url.searchParams.get('countryCode');
    const year = url.searchParams.get('year');

    // These become URL path segments below, so restrict them to a safe charset
    // (this also stops anyone using the proxy to reach an arbitrary FAS path).
    const SAFE = /^[A-Za-z0-9]+$/;
    if (!commodityCode || !countryCode || !year || ![commodityCode, countryCode, year].every(v => SAFE.test(v))) {
        return new Response(
            JSON.stringify({ error: "commodityCode, countryCode and year (alphanumeric) are required" }),
            { status: 400, headers: JSON_HEADERS }
        );
    }

    // FAS allows 30 requests/hour and 50/day per IP, shared by the whole site.
    // PSD figures are only revised monthly, so a 24h shared cache is plenty.
    const cacheKey = `usda-fas:${commodityCode}:${countryCode}:${year}`;

    return kvCachedJson(env, cacheKey, 86400, async () => {
        const fasUrl = `https://api.fas.usda.gov/api/psd/commodity/${commodityCode}/country/${countryCode}/year/${year}`;
        const fasRes = await fetch(fasUrl, { headers: { "X-Api-Key": FAS_KEY, "Accept": "application/json" } });

        if (!fasRes.ok) {
            return { ok: false, status: fasRes.status, statusText: fasRes.statusText };
        }
        return { ok: true, body: await fasRes.json() };
    });
}

// Upstream routes /api/macro?source=eia may proxy. Without this allowlist the
// `route` param would let a caller aim our API key at any EIA endpoint.
const EIA_ROUTES = {
    "petroleum/pri/spt/data/": { frequency: "daily" },
    "natural-gas/pri/spt/data/": { frequency: "daily" },
    // Stocks: the Strategic Petroleum Reserve and the Cushing hub. EIA reports
    // these weekly, not daily -- asking for daily returns an empty series, which
    // is why the frequency now travels with the route instead of being pinned.
    "petroleum/stoc/wstk/data/": { frequency: "weekly" },
    "petroleum/stoc/typ/data/": { frequency: "weekly" }
};

async function handleMacro(request, env, ctx) {
    const url = new URL(request.url);
    const source = url.searchParams.get('source');

    try {
        if (source === 'fred') {
            const series_id = url.searchParams.get('series_id');
            const FRED_KEY = env.FRED_API_KEY;
            if (!FRED_KEY) return missingKey('FRED_API_KEY');

            // FRED writes "." for a day a daily series has no reading -- weekends
            // and market holidays on DGS10, DEXJPUS and friends. With limit=1 the
            // newest observation is then a dot and the tile has nothing to show,
            // so callers may ask for a few extra rows and take the first real one.
            // Capped at 10: this route exists to fill one tile, not to serve history.
            const limitParam = parseInt(url.searchParams.get('limit'), 10);
            const limit = Number.isFinite(limitParam) ? Math.min(Math.max(limitParam, 1), 10) : 1;

            return kvCachedJson(env, `fred:${series_id}:${limit}`, 3600, async () => {
                const fredUrl = `https://api.stlouisfed.org/fred/series/observations?series_id=${encodeURIComponent(series_id)}&api_key=${FRED_KEY}&file_type=json&sort_order=desc&limit=${limit}`;
                const res = await fetch(fredUrl);
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        if (source === 'bok') {
            const BOK_KEY = env.BOK_API_KEY;
            if (!BOK_KEY) return missingKey('BOK_API_KEY');

            return kvCachedJson(env, 'bok:keystats', 3600, async () => {
                const bokUrl = `https://ecos.bok.or.kr/api/KeyStatisticList/${BOK_KEY}/json/kr/1/100/`;
                const res = await fetch(bokUrl);
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        if (source === 'eia') {
            const route = url.searchParams.get('route');
            const seriesId = url.searchParams.get('seriesId');
            const EIA_KEY = env.EIA_API_KEY;
            if (!EIA_KEY) return missingKey('EIA_API_KEY');

            if (!EIA_ROUTES[route]) {
                return new Response(JSON.stringify({ error: "Unsupported EIA route" }), { status: 400, headers: JSON_HEADERS });
            }

            const freq = EIA_ROUTES[route].frequency;
            // Stocks move weekly and the panel shows a change, so keep a
            // year of history (52 points) rather than one point -- long
            // enough to tell a seasonal drawdown from a genuine trend.
            const length = freq === 'weekly' ? 52 : 1;
            return kvCachedJson(env, `eia:${route}:${seriesId}:${length}`, 3600, async () => {
                const eiaUrl = `https://api.eia.gov/v2/${route}?api_key=${EIA_KEY}&frequency=${freq}&data[0]=value&facets[series][]=${encodeURIComponent(seriesId)}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=${length}`;
                const res = await fetch(eiaUrl);
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        if (source === 'cnbc') {
            // CNBC's unofficial quote API -- the same one behind cnbc.com/quotes/<symbol>
            // -- for instruments Yahoo prices oddly or not at all, e.g. sovereign
            // bond yields (JP10Y, UK10Y). No API key; a plain browser UA is enough
            // to get past their edge. Not FRED/BOK/EIA-official, so callers treat a
            // miss here as routine and fall back rather than surfacing an error.
            const symbol = url.searchParams.get('symbol');
            if (!symbol) return new Response(JSON.stringify({ error: "symbol required" }), { status: 400, headers: JSON_HEADERS });

            return kvCachedJson(env, `cnbc:${symbol}`, 3600, async () => {
                const cnbcUrl = `https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol`
                    + `?symbols=${encodeURIComponent(symbol)}&requestMethod=itv&noform=1&partnerId=2`
                    + `&fund=1&exthrs=1&output=json&events=1`;
                const res = await fetch(cnbcUrl, {
                    headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
                });
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        if (source === 'yfinance') {
            const symbol = url.searchParams.get('symbol');

            // The chart modal wants 5 years of monthly bars; the home panel's
            // JP/UK 10Y bond tiles want just today's close, so they ask for
            // interval=1d&range=5d instead. Both keep hitting this one route
            // rather than duplicating the Yahoo fetch, and each combination
            // gets its own cache entry.
            const interval = url.searchParams.get('interval') || '1mo';
            const rangeParam = url.searchParams.get('range');

            return kvCachedJson(env, `yfinance:${symbol}:${interval}:${rangeParam || '5y'}`, 3600, async () => {
                const period2 = Math.floor(Date.now() / 1000);
                const period1 = rangeParam === '5d'
                    ? period2 - 5 * 86400
                    : Math.floor(new Date().setFullYear(new Date().getFullYear() - 5) / 1000);
                const yfUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?period1=${period1}&period2=${period2}&interval=${encodeURIComponent(interval)}`;

                const res = await fetch(yfUrl, {
                    headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
                });
                // Yahoo rate-limits datacenter IPs and answers 429 with plain
                // text, so res.json() must not be called blindly.
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        return new Response(JSON.stringify({ error: "Invalid macro source" }), { status: 400, headers: JSON_HEADERS });

    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: JSON_HEADERS });
    }
}

// --- Instrument lookup + daily prices -------------------------------------
// The portfolio panel computes covariance in the browser, which needs daily
// closes -- the existing /api/macro yfinance route returns monthly, far too
// coarse to estimate a covariance matrix from. Kept separate rather than
// widening that route because the cache lifetimes differ by an order of
// magnitude: a ticker's name never changes, its price does.
const YF_HEADERS = { "User-Agent": "Mozilla/5.0", "Accept": "application/json" };

// Returns null (not an error) when Yahoo declines, so the caller can fall back
// rather than surface a failure the visitor can do nothing about.
async function yahooSearch(q) {
    try {
        const yf = `https://query1.finance.yahoo.com/v1/finance/search`
            + `?q=${encodeURIComponent(q)}&quotesCount=12&newsCount=0&listsCount=0`;
        const res = await fetch(yf, { headers: YF_HEADERS });
        if (!res.ok) return null;
        const body = await res.json();
        // Indices, futures and currencies are all legitimate holdings here;
        // options and anything without a symbol are not.
        const quotes = (body.quotes || [])
            .filter((x) => x.symbol && x.quoteType !== 'OPTION')
            .map((x) => ({
                symbol: x.symbol,
                name: x.longname || x.shortname || x.symbol,
                exchange: x.exchDisp || x.exchange || '',
                type: x.quoteType || '',
            }));
        return quotes.length ? quotes : null;
    } catch (_) {
        return null;
    }
}

const SEC_TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json';

async function secIndex(env) {
    const KEY = 'sec:tickers:v2';   // v2 carries the CIK, needed for filings
    if (env.API_CACHE) {
        try {
            const hit = await env.API_CACHE.get(KEY, 'json');
            if (hit) return hit;
        } catch (_) { /* fall through to fetch */ }
    }
    // SEC asks that automated clients identify themselves with a contact address.
    const res = await fetch(SEC_TICKERS_URL, {
        headers: { 'User-Agent': 'global-trade-dashboard overideal@gmail.com', 'Accept': 'application/json' },
    });
    if (!res.ok) return [];
    const raw = await res.json();
    const rows = Object.values(raw).map((v) => [v.ticker, v.title, v.cik_str]);
    if (env.API_CACHE) {
        // The filer list changes on the scale of weeks; a day of staleness is
        // invisible and keeps this off SEC's servers.
        try { await env.API_CACHE.put(KEY, JSON.stringify(rows), { expirationTtl: 86400 }); } catch (_) { /* ignore */ }
    }
    return rows;
}

// --- Filed financials -----------------------------------------------------
// SEC publishes every filer's XBRL facts free and without a key, which is why
// the US half of the company calculator works before the Korean DART key
// exists. One company's full fact set is several megabytes, so the extraction
// happens here and the browser receives a few kilobytes.
const SEC_HEADERS = {
    'User-Agent': 'global-trade-dashboard overideal@gmail.com',
    'Accept': 'application/json',
};

// us-gaap tags, in the order they should be tried: filers disagree about which
// concept a line belongs to, and the first one present wins.
const SEC_TAGS = {
    revenue: ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'],
    operating_income: ['OperatingIncomeLoss'],
    net_income: ['NetIncomeLoss', 'ProfitLoss'],
    assets: ['Assets'],
    assets_current: ['AssetsCurrent'],
    liabilities: ['Liabilities'],
    liabilities_current: ['LiabilitiesCurrent'],
    equity: ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    cash: ['CashAndCashEquivalentsAtCarryingValue'],
    debt_long: ['LongTermDebtNoncurrent', 'LongTermDebt'],
    cfo: ['NetCashProvidedByUsedInOperatingActivities',
          'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    capex: ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets',
            'PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets'],
    shares: ['WeightedAverageNumberOfDilutedSharesOutstanding',
             'CommonStockSharesOutstanding', 'EntityCommonStockSharesOutstanding'],

    // Debt broken out by when it comes due. "부채비율" alone hides the thing
    // that actually sinks companies -- not how much they owe, but how soon.
    debt_short: ['ShortTermBorrowings', 'CommercialPaper', 'DebtCurrent'],
    debt_current_portion: ['LongTermDebtCurrent'],
    payables: ['AccountsPayableCurrent'],
    accrued: ['AccruedLiabilitiesCurrent'],
    deferred_revenue: ['ContractWithCustomerLiabilityCurrent'],
    lease_current: ['OperatingLeaseLiabilityCurrent'],
    lease_noncurrent: ['OperatingLeaseLiabilityNoncurrent'],
    other_current: ['OtherLiabilitiesCurrent'],
    other_noncurrent: ['OtherLiabilitiesNoncurrent'],
    deferred_tax: ['DeferredIncomeTaxLiabilitiesNet'],

    // Asset side, for the same structural read.
    receivables: ['AccountsReceivableNetCurrent'],
    inventory: ['InventoryNet'],
    securities_current: ['MarketableSecuritiesCurrent', 'ShortTermInvestments'],
    ppe: ['PropertyPlantAndEquipmentNet'],
    goodwill: ['Goodwill'],
    intangibles: ['IntangibleAssetsNetExcludingGoodwill'],
    retained_earnings: ['RetainedEarningsAccumulatedDeficit'],

    // DCF inputs.
    interest_expense: ['InterestExpense'],
    tax_expense: ['IncomeTaxExpenseBenefit'],
    dna: ['DepreciationDepletionAndAmortization'],
};

// Which SEC_TAGS keys are period flows rather than point-in-time balances.
// Only a flow can be summed across quarters, and only a flow has a missing
// fiscal Q4 to reconstruct (see secFillFiscalQ4). Mirrors DART_FLOW_KEYS.
const SEC_FLOW_KEYS = new Set([
    'revenue', 'operating_income', 'net_income', 'cfo', 'capex',
    'interest_expense', 'tax_expense', 'dna',
]);

// Merges every candidate tag by year instead of committing to the first one
// that has any data. Filers migrate between concepts mid-history -- NVIDIA
// reports capex under PropertyPlantAndEquipment in older years and
// ProductiveAssets in newer ones -- so taking a single tag leaves the recent
// years blank, which is exactly the part anyone is looking at.
const SEC_DAY = 86400000;

// The `fy` on an XBRL fact is the fiscal year of the FILING, not of the figure.
// A 10-K carries two or three comparative years and stamps all of them with the
// filing's own year -- Microsoft's FY2026 report tags FY2024, FY2025 and FY2026
// alike as fy=2026. Keying on it silently shifts every company's history.
// The period end date is the only field that says what the number covers.
function secFiscalYear(p) {
    const end = p.end && new Date(p.end);
    return (end && !Number.isNaN(end.getTime())) ? end.getUTCFullYear() : null;
}

// Flow concepts (revenue, cash flow) span a period; stock concepts (assets)
// are a snapshot. Only the former can be a multi-year cumulative by mistake.
function secIsFullYear(p) {
    if (!p.start) return true;
    const days = (new Date(p.end) - new Date(p.start)) / SEC_DAY;
    return days >= 340 && days <= 380;
}

// A discrete three-month span. Balance-sheet concepts carry no `start` at all
// (they are a point in time, not a period), so those are excluded here rather
// than being counted once per filing that restated them.
function secIsOneQuarter(p) {
    if (!p.start) return false;
    const days = (new Date(p.end) - new Date(p.start)) / SEC_DAY;
    return days >= 80 && days <= 100;
}

// Calendar quarter of the period end, as `2025Q3`. Fiscal quarter labels are
// deliberately not reconstructed: a company whose FY ends in September would
// need its own offset, and the end date is the only thing every filer agrees
// on (same reasoning as secFiscalYear above).
function secQuarterLabel(p) {
    const end = p.end && new Date(p.end);
    if (!end || Number.isNaN(end.getTime())) return null;
    return `${end.getUTCFullYear()}Q${Math.floor(end.getUTCMonth() / 3) + 1}`;
}

function secPickAnnual(facts, names) {
    const byYear = new Map();
    const used = [];
    let unit = null;
    for (const tag of names) {
        const node = facts[tag];
        if (!node || !node.units) continue;
        const u = Object.keys(node.units)[0];
        const annual = (node.units[u] || []).filter((p) =>
            p.form === '10-K' && p.end && secIsFullYear(p) && secFiscalYear(p));
        if (!annual.length) continue;
        unit = unit || u;
        used.push(tag);

        // Two precedence rules, easy to conflate. Within one tag a period shows
        // up once per filing that repeated it, so the most recently FILED entry
        // is the current restatement and wins. Across tags the earlier-listed
        // concept is the better match and must not be overwritten by a fallback.
        const perTag = new Map();
        for (const p of annual.slice().sort((a, b) => String(a.filed).localeCompare(String(b.filed)))) {
            perTag.set(secFiscalYear(p), { val: p.val, start: p.start, end: p.end });
        }
        for (const [fy, row] of perTag) if (!byYear.has(fy)) byYear.set(fy, row);
    }
    if (!byYear.size) return null;
    // `years` stays a fy -> value map so existing callers are unaffected;
    // `bounds` carries the period each annual figure covers, which is what
    // lets the fiscal-Q4 fill below know which quarters belong to which year
    // without having to guess a filer's fiscal calendar.
    return {
        tag: used.join('+'),
        unit,
        years: new Map([...byYear].map(([fy, r]) => [fy, r.val])),
        bounds: new Map([...byYear].map(([fy, r]) => [fy, { start: r.start, end: r.end }])),
    };
}

// A fiscal Q4 is never filed as its own 10-Q, and the 10-K reports the full
// year rather than restating that quarter -- so a quarterly series built from
// filings alone is missing every fourth point (verified live: NVDA had 5 of 18
// quarters empty, all of them its fiscal Q4). The missing quarter is the
// arithmetic remainder: FY minus the three quarters that fall inside the same
// annual period.
//
// Bounds come from the annual fact itself, so this works for a January or June
// fiscal year without knowing anything about the filer's calendar. It fills
// only when exactly three quarters are present -- with two, the remainder
// would silently be a half-year on a bar labelled as one quarter.
function secFillFiscalQ4(quarterlyMap, annualYears, annualBounds) {
    if (!quarterlyMap || !annualBounds) return quarterlyMap;
    for (const [fy, bounds] of annualBounds) {
        const total = annualYears.get(fy);
        if (!Number.isFinite(total) || !bounds.start || !bounds.end) continue;
        const inYear = [...quarterlyMap.entries()]
            .filter(([, row]) => row.end > bounds.start && row.end <= bounds.end);
        if (inYear.length !== 3) continue;
        const label = secQuarterLabel({ end: bounds.end });
        if (!label || quarterlyMap.has(label)) continue;
        const sum = inYear.reduce((acc, [, row]) => acc + row.value, 0);
        quarterlyMap.set(label, { value: total - sum, end: bounds.end, form: 'derived:FY-9M' });
    }
    return quarterlyMap;
}

// Same shape and precedence rules as secPickAnnual, keyed by `2025Q3` instead
// of a fiscal year. The quarterly tape lives in the very same companyfacts
// response the annual one is read from -- it was simply filtered out by the
// `form === '10-K'` test, so no extra upstream call is needed for any of this.
//
// 10-K is included alongside 10-Q because some filers do restate a
// three-month period inside the annual report. Most do not: a fiscal Q4 is
// never filed as its own 10-Q, and the 10-K carries the full year instead --
// verified live, NVDA had 5 of 18 quarters empty and every one was its fiscal
// Q4. secFillFiscalQ4 reconstructs those by subtraction after the fact.
function secPickQuarterly(facts, names) {
    const byQuarter = new Map();
    for (const tag of names) {
        const node = facts[tag];
        if (!node || !node.units) continue;
        const u = Object.keys(node.units)[0];
        const quarters = (node.units[u] || []).filter((p) =>
            (p.form === '10-Q' || p.form === '10-K') && p.end && secQuarterLabel(p)
            // A balance-sheet concept carries no `start` -- it is the value at
            // one instant, already "the quarter's" figure, so the duration
            // test that isolates a three-month flow must not be applied to it.
            // Without this branch every ratio card (current ratio, ROE, ...)
            // would have an empty quarterly series while revenue had a full one.
            && (p.start ? secIsOneQuarter(p) : true));
        if (!quarters.length) continue;

        const perTag = new Map();
        for (const p of quarters.slice().sort((a, b) => String(a.filed).localeCompare(String(b.filed)))) {
            perTag.set(secQuarterLabel(p), { value: p.val, end: p.end, form: p.form });
        }
        for (const [q, row] of perTag) if (!byQuarter.has(q)) byQuarter.set(q, row);
    }
    return byQuarter.size ? byQuarter : null;
}

async function handleFinancials(request, env) {
    const url = new URL(request.url);
    const symbol = (url.searchParams.get('symbol') || '').trim().toUpperCase();
    if (!symbol) {
        return new Response(JSON.stringify({ error: 'symbol required' }), { status: 400, headers: JSON_HEADERS });
    }

    try {
        return await kvCachedJson(env, `fin:sec:${symbol}`, 86400, async () => {
            const rows = await secIndex(env);
            const hit = rows.find((r) => String(r[0]).toUpperCase() === symbol);
            if (!hit) return { ok: false, status: 404, statusText: 'not a US filer' };

            const cik = String(hit[2]).padStart(10, '0');
            const res = await fetch(`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`, { headers: SEC_HEADERS });
            if (!res.ok) return { ok: false, status: res.status };
            const doc = await res.json();
            const gaap = (doc.facts && doc.facts['us-gaap']) || {};

            const picked = {}, used = {}, bounds = {};
            for (const [key, names] of Object.entries(SEC_TAGS)) {
                const got = secPickAnnual(gaap, names);
                if (got) { picked[key] = got.years; used[key] = got.tag; bounds[key] = got.bounds; }
            }

            const years = [...new Set(Object.values(picked).flatMap((m) => [...m.keys()]))]
                .sort((a, b) => b - a).slice(0, 5);

            const statements = years.map((fy) => {
                const row = { fy };
                for (const key of Object.keys(SEC_TAGS)) {
                    const v = picked[key] ? picked[key].get(fy) : undefined;
                    row[key] = (v === undefined) ? null : v;
                }
                return row;
            });

            // Quarterly runs on its own axis rather than being folded into
            // `statements`: the two cover different spans (a quarter is not a
            // year) and a row carrying both would invite summing across them.
            const quarterlyByKey = {};
            for (const [key, names] of Object.entries(SEC_TAGS)) {
                const got = secPickQuarterly(gaap, names);
                if (!got) continue;
                // Balance-sheet keys are point-in-time and already complete --
                // there is no "missing Q4 balance" to reconstruct, and the
                // subtraction would be meaningless on a level anyway.
                quarterlyByKey[key] = (picked[key] && bounds[key] && SEC_FLOW_KEYS.has(key))
                    ? secFillFiscalQ4(got, picked[key], bounds[key])
                    : got;
            }
            const oldestKeptYear = years.length ? Math.min(...years) : null;
            const quarterLabels = [...new Set(Object.values(quarterlyByKey).flatMap((m) => [...m.keys()]))]
                // Same 5-year window the annual series uses, so the two views of
                // one card cover the same stretch of history.
                .filter((q) => oldestKeptYear === null || Number(q.slice(0, 4)) >= oldestKeptYear)
                .sort();
            const quarterly = quarterLabels.map((q) => {
                const row = { period: q };
                for (const key of Object.keys(SEC_TAGS)) {
                    const got = quarterlyByKey[key] ? quarterlyByKey[key].get(q) : undefined;
                    row[key] = got ? got.value : null;
                    if (got && !row.end) row.end = got.end;
                }
                return row;
            });

            return {
                ok: true,
                body: {
                    source: 'SEC XBRL',
                    symbol,
                    cik,
                    name: doc.entityName || hit[1],
                    currency: 'USD',
                    statements,
                    quarterly,
                    tags_used: used,
                },
            };
        });
    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: JSON_HEADERS });
    }
}

// --- Korean listings (DART/KFA), live fetch --------------------------------
// scripts/dart/fetch_kfa_snapshot.py pre-generates a handful of full
// kfa_<code>_v1.json snapshots (16 expert cards + 9 valuation models) into
// public/data/. This covers the other ~3,978 KRX-listed filers on demand,
// but deliberately only the 12 Basic-view cards -- app.js already renders an
// uncomputed card as "준비 중" (see renderKfaResult), so Investor/PE/Deal
// stay pending here rather than needing a parallel JS port of that heavier
// calculation logic (CAGR, aligned ratio series, DCF models, ...), which is
// out of scope for this endpoint. app.js falls back here only when the
// static snapshot 404s (see loadKfaCompany).
//
// Mirrors scripts/dart/dart_kfa/dart_facts.py's XBRL_TAGS -- keep both in
// sync if a tag mapping changes. Verified live against Samsung Electronics
// (00126380) and SK Hynix (00164779), FY2025 CFS.
const DART_XBRL_TAGS = {
    revenue: ['ifrs-full_Revenue'],
    operating_income: ['dart_OperatingIncomeLoss', 'ifrs-full_OperatingIncomeLoss'],
    net_income: ['ifrs-full_ProfitLoss'],
    interest_expense: ['ifrs-full_FinanceCosts'],
    // Present in dart_facts.py's XBRL_TAGS but never ported to this Worker --
    // the live path has been shipping one fewer field than the Python source
    // it mirrors. No new endpoint needed: already inside the same
    // fnlttSinglAcntAll response every other tag here reads from.
    eps: ['ifrs-full_BasicEarningsLossPerShare'],
    cfo: ['ifrs-full_CashFlowsFromUsedInOperatingActivities'],
    capex: ['ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'],
    cash: ['ifrs-full_CashAndCashEquivalents'],
    current_assets: ['ifrs-full_CurrentAssets'],
    current_liabilities: ['ifrs-full_CurrentLiabilities'],
    // Samsung Electronics' short-term borrowings has no standard XBRL id at
    // all ("-표준계정코드 미사용-") -- null + reason for that filer is
    // correct, not a bug. SK Hynix and most other filers do carry this tag.
    short_term_debt: ['ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings'],
    long_term_debt: ['ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived', 'ifrs-full_LongtermBorrowings'],
    // Not in dart_facts.py's verified table (only P&L/CF/short-debt tags were
    // checked live there) -- ifrs-full_Equity is the standard IFRS total-
    // equity element, added for PBR's denominator. Confirmed live below.
    equity: ['ifrs-full_Equity'],
};
// Rows filed under Statement of Changes in Equity repeat the same account_id
// once per equity column with genuinely different values -- keying a flat
// dict by account_id on this section would silently pick whichever column
// happened to be inserted last.
const DART_COLLIDING_SJ_DIV = new Set(['SCE']);

// OpenDART's four periodic report codes. Korean interim reports are
// year-to-date cumulative, not standalone quarters: H1 covers Q1+Q2 and Q3
// covers Q1..Q3, so a discrete quarter is a difference between neighbours
// (see dartQuarterlySeries).
const DART_REPRT = {
    Q1: '11013', // 1분기보고서
    H1: '11012', // 반기보고서   (cumulative through Q2)
    Q3: '11014', // 3분기보고서 (cumulative through Q3)
    FY: '11011', // 사업보고서   (full year)
};

// Which DART_XBRL_TAGS keys are period flows vs point-in-time balances.
// Differencing a cumulative flow yields the quarter; differencing a balance
// yields the change in that balance, which is a different quantity entirely
// and must never be labelled "Q3 cash".
const DART_FLOW_KEYS = new Set([
    'revenue', 'operating_income', 'net_income', 'interest_expense', 'eps', 'cfo', 'capex',
]);

// public/data/dart_corp_codes_v1.json is a one-time offline export of
// OpenDART's corpCode.xml (see scripts/dart/ for how it was built): the KRX
// 6-digit stock code -> [OpenDART 8-digit corp_code, entity name] for every
// listed filer. Refreshed rarely (new listings/delistings only), so a day of
// KV staleness is invisible -- same reasoning as secIndex() below.
async function dartCorpIndex(env, origin) {
    const KEY = 'dart:corp_codes:v1';
    if (env.API_CACHE) {
        try {
            const hit = await env.API_CACHE.get(KEY, 'json');
            if (hit) return hit;
        } catch (_) { /* fall through to asset fetch */ }
    }
    for (const path of ['/public/data/dart_corp_codes_v1.json', '/data/dart_corp_codes_v1.json']) {
        try {
            const res = await env.ASSETS.fetch(new Request(new URL(path, origin).toString()));
            if (!res.ok) continue;
            const doc = await res.json();
            const index = doc.index || {};
            if (env.API_CACHE) {
                try { await env.API_CACHE.put(KEY, JSON.stringify(index), { expirationTtl: 86400 }); } catch (_) { /* ignore */ }
            }
            return index;
        } catch (_) { /* try next */ }
    }
    return {};
}

// Same credential under either name: scripts/dart/ reads DART_API_KEY
// locally, and the Worker secret has also been stored as OPEN_DART_API.
// Accept both -- a naming mismatch would make every lookup return "no facts",
// which is indistinguishable from a company genuinely having no filing.
// A binding is either a plain string (Workers "Secret" / plaintext var) or a
// Secrets Store binding object, which only yields its value via async get().
// Interpolating the object form into a URL throws instead of stringifying, so
// both shapes have to be unwrapped here. Trimmed because a secret pasted into
// the dashboard often carries a trailing newline, which OpenDART rejects as a
// malformed key.
async function dartApiKey(env) {
    for (const binding of [env.OPEN_DART_API, env.DART_API_KEY]) {
        if (!binding) continue;
        if (typeof binding === 'string') return binding.trim();
        if (typeof binding.get === 'function') {
            try {
                const value = await binding.get();
                if (value) return String(value).trim();
            } catch (_) { /* try the next binding */ }
        }
    }
    return '';
}

function dartPick(facts, candidates) {
    for (const tag of candidates) {
        const raw = facts[tag];
        if (raw === undefined || raw === null) continue;
        const num = Number(raw);
        if (Number.isFinite(num)) return num;
    }
    return null;
}

const dartSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Returns { facts, reason }. Every failure path used to collapse to a bare
// {}, which made four very different problems -- no secret bound, OpenDART
// refusing the Worker's egress, a rejected key, a company with no filing --
// look identical from the outside and impossible to tell apart without
// redeploying. reason names which one it was; it never carries the key.
//
// One retry on status 020 (rate limited): the multi-year loop this now feeds
// makes 3+ sequential OpenDART calls per request where there used to be at
// most 2, so a transient throttle is more likely to be hit mid-loop than it
// was for a single fetch. A second 020 is treated as real backpressure, not
// retried further.
async function fetchDartXbrlFacts(env, corpCode, year, fsDiv, { retriedOn020 = false, reprtCode = DART_REPRT.FY } = {}) {
    // Missing key must degrade to empty (no network call), same contract as
    // the Python adapter -- a snapshot without a live key still has to render.
    const key = await dartApiKey(env);
    if (!key) return { facts: {}, reason: 'no_key_bound' };
    const params = new URLSearchParams({
        crtfc_key: key,
        corp_code: corpCode,
        bsns_year: String(year),
        reprt_code: reprtCode, // see DART_REPRT -- 11011 is the annual report
        fs_div: fsDiv,
    });
    try {
        const res = await fetch(`https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?${params}`, {
            headers: { 'User-Agent': 'global-trade-dashboard/1.0', Accept: 'application/json' },
        });
        if (!res.ok) return { facts: {}, reason: `http_${res.status}` };
        const data = await res.json();
        // OpenDART's own status codes: 013 = no data for this query, 020 =
        // rate limited, 100/800/900 = bad key or unregistered caller.
        if (data.status === '020' && !retriedOn020) {
            await dartSleep(400);
            return fetchDartXbrlFacts(env, corpCode, year, fsDiv, { retriedOn020: true, reprtCode });
        }
        if (data.status !== '000') return { facts: {}, reason: `dart_status_${data.status}` };
        const facts = {};
        const isInterim = reprtCode !== DART_REPRT.FY;
        for (const item of data.list || []) {
            if (DART_COLLIDING_SJ_DIV.has(item.sj_div)) continue;
            const accountId = item.account_id;
            // Korean interim filings report income-statement and cash-flow
            // lines twice: thstrm_amount is that quarter alone (3 months) and
            // thstrm_add_amount is the year-to-date cumulative. Which one a
            // given filer populates is not consistent, so prefer the explicit
            // cumulative field and fall back to the plain one. Balance-sheet
            // rows are a point in time and carry no add_amount at all, which
            // this fallback handles without a separate branch.
            const amount = (isInterim && item.thstrm_add_amount !== undefined && item.thstrm_add_amount !== null
                && String(item.thstrm_add_amount).trim() !== '')
                ? item.thstrm_add_amount
                : item.thstrm_amount;
            if (!accountId || accountId.startsWith('-') || amount === undefined || amount === null) continue;
            if (!(accountId in facts)) facts[accountId] = amount;
        }
        return { facts, reason: Object.keys(facts).length ? 'ok' : 'no_usable_account_ids' };
    } catch (err) {
        // Workers put the failing URL in fetch error messages, and this one
        // carries crtfc_key -- the reason travels to the client, so redact.
        const detail = String(err.message || '').split(key).join('<key>');
        return { facts: {}, reason: `fetch_failed:${err.name}:${detail}` };
    }
}

// Returns { sharesOutstanding, reason }. OpenDART's "주식의 총수 현황"
// (stockTotqySttus) disclosure has one row per share class (보통주/우선주)
// plus a 합계 (total) row; the total row is what market_cap needs, not a
// single class. No prior integration of this endpoint exists anywhere in
// this repo (checked both engines) -- the row-shape assumptions below (a
// `se` field marking the total row, `distb_stock_co` as the outstanding-
// share count) are unverified against a live response and MUST be confirmed
// against real output for at least one filer before this ships; see the
// verification note in the PR.
async function fetchDartSharesOutstanding(env, corpCode, year) {
    const key = await dartApiKey(env);
    if (!key) return { sharesOutstanding: null, reason: 'no_key_bound' };
    const params = new URLSearchParams({
        crtfc_key: key,
        corp_code: corpCode,
        bsns_year: String(year),
        reprt_code: '11011',
    });
    try {
        const res = await fetch(`https://opendart.fss.or.kr/api/stockTotqySttus.json?${params}`, {
            headers: { 'User-Agent': 'global-trade-dashboard/1.0', Accept: 'application/json' },
        });
        if (!res.ok) return { sharesOutstanding: null, reason: `http_${res.status}` };
        const data = await res.json();
        if (data.status !== '000') return { sharesOutstanding: null, reason: `dart_status_${data.status}` };
        const rows = data.list || [];
        const toNum = (s) => {
            const n = Number(String(s ?? '').replace(/,/g, ''));
            return Number.isFinite(n) ? n : null;
        };
        // Prefer an explicit total row; some filers omit it, so fall back to
        // summing 보통주+우선주 rows rather than reporting nothing.
        const totalRow = rows.find((r) => String(r.se || '').includes('합계'));
        let shares = totalRow ? toNum(totalRow.distb_stock_co) : null;
        if (shares === null) {
            const classRows = rows.filter((r) => /보통주|우선주/.test(String(r.se || '')));
            if (classRows.length) {
                const summed = classRows.reduce((acc, r) => {
                    const v = toNum(r.distb_stock_co);
                    return v === null ? acc : acc + v;
                }, 0);
                shares = summed > 0 ? summed : null;
            }
        }
        return {
            sharesOutstanding: shares,
            reason: shares !== null ? 'ok' : 'no_usable_row',
        };
    } catch (err) {
        const detail = String(err.message || '').split(key).join('<key>');
        return { sharesOutstanding: null, reason: `fetch_failed:${err.name}:${detail}` };
    }
}

// Returns { price, reason }. Reuses the Yahoo chart endpoint the futures/
// history quote paths already call (see YF_HEADERS above) rather than adding
// a new price source -- market_cap/PE/PB are the only cards that need a live
// price, and this Worker otherwise has no reason to know today's quote for
// an arbitrary DART filer. The DART corp-code index carries no market field
// (KOSPI vs KOSDAQ), so this tries `.KS` then falls back to `.KQ`.
//
// Deliberately NOT wrapped in kvCachedJson: that helper returns a Response
// object (it's built for top-level HTTP handlers), not a plain value, so
// nesting it here would hand the caller a Response instead of {price,
// reason}. It would also be redundant -- the whole /api/dart-financials
// response this feeds is already cached for 24h by its own kvCachedJson
// call, so a separate short-TTL cache on just the price leg buys nothing.
async function fetchDartKrPrice(symbol) {
    for (const suffix of ['.KS', '.KQ']) {
        try {
            const res = await fetch(
                `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}${suffix}?interval=1d&range=5d`,
                { headers: YF_HEADERS });
            if (!res.ok) continue;
            const meta = (await res.json())?.chart?.result?.[0]?.meta;
            const price = Number(meta?.regularMarketPrice);
            if (Number.isFinite(price)) return { price, reason: 'ok', exchange_suffix: suffix };
        } catch { /* try the next suffix */ }
    }
    return { price: null, reason: 'no_price_ks_or_kq' };
}

// Discrete quarterly series per card key, from the cumulative interim filings.
//
// `factsByPeriod` is {year: {Q1|H1|Q3|FY: facts}}. Korean interim reports are
// year-to-date, so a standalone quarter is the difference between neighbouring
// cumulatives -- Q2 = H1 - Q1, Q3 = 3Q - H1, Q4 = FY - 3Q. Only flows work that
// way: a balance sheet line is already the value at that date, so differencing
// it would produce the *change* in cash and label it "Q3 cash". Hence the
// DART_FLOW_KEYS split.
//
// Quarter ends assume a December fiscal year (acc_mt '12'), which is what the
// response's own meta claims and what nearly every KRX filer uses. A March-FY
// filer would need its own offset; that is not handled here, and its quarters
// would be labelled by calendar position.
function dartQuarterlySeries(factsByPeriod, years) {
    const QUARTER_END = { Q1: '03-31', Q2: '06-30', Q3: '09-30', Q4: '12-31' };
    // Which cumulative to subtract to isolate each quarter. Q1 stands alone.
    const FROM_CUMULATIVE = { Q1: ['Q1', null], Q2: ['H1', 'Q1'], Q3: ['Q3', 'H1'], Q4: ['FY', 'Q3'] };
    const out = {};

    for (const key of Object.keys(DART_XBRL_TAGS)) {
        const points = [];
        for (const year of [...years].sort((a, b) => a - b)) {
            const buckets = factsByPeriod[year] || {};
            for (const q of ['Q1', 'Q2', 'Q3', 'Q4']) {
                const [curCode, prevCode] = FROM_CUMULATIVE[q];
                const curFacts = buckets[curCode];
                if (!curFacts) continue;
                const cur = dartPick(curFacts, DART_XBRL_TAGS[key]);
                if (cur === null) continue;

                let value = cur;
                if (DART_FLOW_KEYS.has(key) && prevCode) {
                    const prevFacts = buckets[prevCode];
                    // Without the prior cumulative the quarter cannot be
                    // isolated. Emitting the raw cumulative here would put a
                    // year-to-date figure on a bar labelled as one quarter.
                    if (!prevFacts) continue;
                    const prev = dartPick(prevFacts, DART_XBRL_TAGS[key]);
                    if (prev === null) continue;
                    value = cur - prev;
                }
                points.push({ period: `${year}${q}`, end: `${year}-${QUARTER_END[q]}`, value });
            }
        }
        if (points.length) out[key] = points;
    }
    return out;
}

// Ported from dart_kfa/dart_facts.py's map_facts_to_pack() and
// dart_kfa/derived_cards.py's basic_cards_from_pack(), collapsed into one
// function since the Worker only ever needs the flat basic_cards bag, not
// the intermediate accounting_pack shape.
//
// `factsByYear` is `{year: facts}` for every fiscal year the caller managed
// to fetch (see handleDartFinancials' bsns_year loop) and `years` is that
// same set, descending -- years[0] is "as of". A year with no filing simply
// has no key in factsByYear; series are built by filtering, not by assuming
// every year in `years` produced a point, so a gap (recent listing, a filing
// OpenDART hasn't ingested yet) leaves a shorter series rather than a null.
function dartBasicCardsFromFacts(factsByYear, years, { sharesOutstanding = null, price = null, quarterly = {} } = {}) {
    const latestYear = years[0];
    const factsOf = (y) => factsByYear[y] || {};
    const latestFacts = factsOf(latestYear);

    // One year's value for `key`, or null if that year's facts don't carry it.
    const valueIn = (y, key) => dartPick(factsOf(y), DART_XBRL_TAGS[key]);

    const seriesFor = (key) => years
        .map((y) => {
            const v = valueIn(y, key);
            return v === null ? null : { year: y, end: `${y}-12-31`, value: v };
        })
        .filter(Boolean)
        .sort((a, b) => a.year - b.year); // oldest first, so [-2]/[-1] below is prev/latest

    const point = (key) => {
        const series = seriesFor(key);
        if (!series.length) return { value: null, series: [], reason: 'missing:not_in_opendart' };
        return { value: series[series.length - 1].value, series };
    };

    const revenue = point('revenue');
    const operatingIncome = point('operating_income');
    const netIncome = point('net_income');
    const cfo = point('cfo');
    const capex = point('capex');
    const cash = point('cash');
    const eps = point('eps');

    const revV = revenue.value, opV = operatingIncome.value, niV = netIncome.value;
    // yoy compares the series' own last two points, not two calendar years --
    // a missing filing in between should not silently compare non-adjacent
    // years as if they were consecutive.
    if (revenue.series.length >= 2) {
        const [prev, last] = revenue.series.slice(-2);
        revenue.yoy = prev.value ? (last.value - prev.value) / Math.abs(prev.value) : null;
    } else {
        revenue.yoy = null;
    }
    operatingIncome.margin = (opV !== null && revV) ? opV / revV : null;
    netIncome.margin = (niV !== null && revV) ? niV / revV : null;

    const capexV = capex.value, cfoV = cfo.value;
    const fcfValue = (cfoV !== null && capexV !== null) ? cfoV - Math.abs(capexV) : null;
    const fcfSeries = years
        .map((y) => {
            const c = valueIn(y, 'cfo'), cx = valueIn(y, 'capex');
            return (c !== null && cx !== null) ? { year: y, end: `${y}-12-31`, value: c - Math.abs(cx) } : null;
        })
        .filter(Boolean)
        .sort((a, b) => a.year - b.year);
    const fcf = { value: fcfValue, definition: 'cfo - abs(capex)', series: fcfSeries };
    if (fcfValue === null) fcf.reason = 'missing:cfo_or_capex';

    // Balance-sheet levels and the ratios built from them stay latest-year
    // point-in-time (a multi-year BS series is future work, not this pass).
    const currentAssets = dartPick(latestFacts, DART_XBRL_TAGS.current_assets);
    const currentLiabilities = dartPick(latestFacts, DART_XBRL_TAGS.current_liabilities);
    const currentRatio = (currentAssets !== null && currentLiabilities)
        ? { value: currentAssets / currentLiabilities, series: [] }
        : { value: null, series: [], reason: 'missing:current_assets_or_current_liabilities' };

    const shortTerm = dartPick(latestFacts, DART_XBRL_TAGS.short_term_debt);
    const longTerm = dartPick(latestFacts, DART_XBRL_TAGS.long_term_debt);
    const cashV = cash.value;
    let netDebt;
    if ((shortTerm !== null || longTerm !== null) && cashV !== null) {
        const interestBearing = (shortTerm || 0) + (longTerm || 0);
        netDebt = {
            value: interestBearing - cashV,
            series: [],
            definition: 'short_term_borrowings + long_term_debt - cash_and_equivalents (marketable_securities not fetched)',
        };
    } else {
        netDebt = { value: null, series: [], reason: 'missing:interest_bearing_debt_or_cash' };
    }

    // Only the short-term-borrowings component is ever fetchable here --
    // current_portion_lt_debt/leases_current have no verified tag, so the
    // total stays null rather than presenting a partial sum as complete.
    const debtDueWithin1y = {
        value: null,
        components: { short_term_borrowings: shortTerm, current_portion_lt_debt: null, leases_current: null },
        reason: shortTerm !== null
            ? 'missing:current_portion_lt_debt_and_lease_current_not_separately_tagged'
            : 'missing:not_in_opendart',
    };

    const interestCoverageSeries = years
        .map((y) => {
            const op = valueIn(y, 'operating_income');
            const ie = valueIn(y, 'interest_expense');
            if (op === null || !ie) return null;
            const v = op / Math.abs(ie);
            return Number.isFinite(v) ? { year: y, end: `${y}-12-31`, value: v } : null;
        })
        .filter(Boolean)
        .sort((a, b) => a.year - b.year);
    const interestCoverage = interestCoverageSeries.length
        ? {
            value: interestCoverageSeries[interestCoverageSeries.length - 1].value,
            series: interestCoverageSeries,
            reason: 'approx:ifrs_finance_costs_not_pure_interest',
            definition: 'operating_income / abs(interest_expense)',
        }
        : { value: null, series: [], reason: 'missing:operating_income_or_nonzero_interest_expense' };

    // market_cap/pe_ratio/pb_ratio need a live price this endpoint does not
    // otherwise fetch (see handleDartFinancials); shares_outstanding comes
    // from a separate stockTotqySttus call. Either being unavailable nulls
    // just these three cards, never the filing-only ones above.
    const marketCap = (price !== null && sharesOutstanding !== null)
        ? { value: price * sharesOutstanding, series: [], definition: 'price × shares_outstanding' }
        : {
            value: null, series: [],
            reason: price === null ? 'missing:price' : 'missing:shares_outstanding',
        };

    const epsV = eps.value;
    const peRatio = (price !== null && epsV)
        ? { value: price / epsV, series: [], definition: 'price / eps (trailing FY, basic EPS)' }
        : { value: null, series: [], reason: price === null ? 'missing:price' : 'missing:eps' };

    const equityV = dartPick(latestFacts, DART_XBRL_TAGS.equity);
    const bps = (equityV !== null && sharesOutstanding) ? equityV / sharesOutstanding : null;
    const pbRatio = (price !== null && bps !== null)
        ? { value: price / bps, series: [], definition: 'price / (equity / shares_outstanding)' }
        : {
            value: null, series: [],
            reason: price === null ? 'missing:price' : (equityV === null ? 'missing:equity' : 'missing:shares_outstanding'),
        };

    const cards = {
        revenue, operating_income: operatingIncome, net_income: netIncome, cfo, fcf, cash, eps,
        net_debt: netDebt,
        current_ratio: currentRatio,
        debt_due_within_1y: debtDueWithin1y,
        liquidity_coverage_1y: {
            value: null, status: null,
            rule: 'buffer / debt_due_within_1y; <1 stressed, 1–1.5 tight, >2 comfortable',
        },
        interest_coverage: interestCoverage,
        ccc_days: { value: null, series: [], reason: 'missing:dso_dio_dpo_inputs_not_fetched' },
        market_cap: marketCap,
        pe_ratio: peRatio,
        pb_ratio: pbRatio,
    };

    // Attached rather than merged into `series`: annual and quarterly points
    // cover different spans, so one array holding both would be summable into
    // nonsense. The UI toggles between them.
    for (const [key, points] of Object.entries(quarterly)) {
        if (cards[key]) cards[key].quarterly = points;
    }
    // FCF has no XBRL tag of its own -- it is cfo - |capex| at every period,
    // so its quarterly series is derived the same way its annual one is.
    const qCfo = quarterly.cfo || [];
    const qCapex = new Map((quarterly.capex || []).map((p) => [p.period, p.value]));
    const fcfQuarterly = qCfo
        .map((p) => (qCapex.has(p.period)
            ? { period: p.period, end: p.end, value: p.value - Math.abs(qCapex.get(p.period)) }
            : null))
        .filter(Boolean);
    if (fcfQuarterly.length) cards.fcf.quarterly = fcfQuarterly;

    return cards;
}

// Mirrors dart_kfa/view_presets.py's get_view_presets() -- Investor/PE/Deal
// list their real card/model keys so the UI's tabs and "준비 중" fallback
// look identical to a full snapshot, even though this endpoint only ever
// populates the Basic view's cards (filing facts + eps/market_cap/pe/pb;
// margins_trend/earnings_quality/owner_earnings and friends in the other
// views have no calc logic here yet -- multi-year facts alone don't fill
// those in, they need dedicated derivation code this pass didn't add).
const DART_VIEW_PRESETS = {
    default_view: 'basic',
    views: {
        basic: {
            cards: ['revenue', 'operating_income', 'net_income', 'eps', 'cfo', 'fcf', 'cash',
                'net_debt', 'current_ratio', 'debt_due_within_1y', 'liquidity_coverage_1y',
                'interest_coverage', 'ccc_days', 'market_cap', 'pe_ratio', 'pb_ratio'],
            models: [],
        },
        investor: {
            cards: ['revenue', 'operating_income', 'net_income', 'fcf', 'owner_earnings',
                'earnings_quality', 'margins_trend', 'capex_to_da', 'net_debt_to_oe', 'interest_coverage'],
            models: ['oe_hurdle', 'reverse_dcf', 'oe_yield'],
        },
        pe: {
            cards: ['revenue', 'ebitda_or_op', 'fcf', 'net_debt_to_ebitda', 'fcf_to_ebitda',
                'interest_coverage', 'maint_capex_burden', 'nwc_change_to_sales',
                'debt_due_within_1y', 'liquidity_coverage_1y'],
            models: ['delever_path', 'coverage_capacity', 'fcf_yield_entry'],
        },
        deal: {
            cards: ['revenue', 'operating_income', 'ebitda', 'trading_multiples', 'ev_bridge',
                'qoe_flags', 'segment', 'nwc_to_sales', 'net_debt'],
            models: ['fcff_dcf', 'trading_comps', 'sotp_or_ev_bridge'],
        },
    },
    rules: { overlap_allowed: true, max_models_per_non_basic_view: 3, no_price_target: true, null_with_reason: true },
};

async function handleDartFinancials(request, env) {
    const url = new URL(request.url);
    const symbol = (url.searchParams.get('symbol') || '').trim();
    if (!/^\d{6}$/.test(symbol)) {
        return new Response(JSON.stringify({ error: 'symbol must be a 6-digit KRX stock code' }), { status: 400, headers: JSON_HEADERS });
    }

    try {
        return await kvCachedJson(env, `fin:dart:${symbol}`, 86400, async () => {
            const index = await dartCorpIndex(env, url.origin);
            const hit = index[symbol];
            if (!hit) return { ok: false, status: 404, statusText: 'not a KRX-listed filer' };
            const [corpCode, nameKo] = hit;

            // Annual reports for FY(Y) file the following spring; before that
            // OpenDART has nothing for FY(currentYear-1) yet, so start one
            // year further back. firstYear is recomputed from the clock on
            // every cold-cache run, not hardcoded, so this keeps rolling
            // forward on its own each spring.
            const now = new Date();
            const firstYear = now.getUTCFullYear() - (now.getUTCMonth() >= 3 ? 1 : 2);
            const candidateYears = [firstYear, firstYear - 1, firstYear - 2];

            // Sequential, not Promise.all: each fetchDartXbrlFacts call may
            // itself retry once on a 020 (rate-limited) response, so racing
            // three of these against the same key risks tripping the limit
            // rather than backing off from it.
            const factsByYear = {};
            const failReasons = [];
            for (const y of candidateYears) {
                const { facts, reason } = await fetchDartXbrlFacts(env, corpCode, y, 'CFS');
                if (Object.keys(facts).length > 0) {
                    factsByYear[y] = facts;
                } else {
                    failReasons.push(`FY${y}:${reason}`);
                }
            }
            const years = candidateYears.filter((y) => y in factsByYear);
            if (!years.length) {
                return {
                    ok: false, status: 404,
                    statusText: `no OpenDART CFS facts for FY${candidateYears.join('/FY')} (${failReasons.join(', ')})`,
                };
            }
            const latestYear = years[0];

            // Interim filings, for the quarterly view. Three more calls per
            // year on top of the annual one, so this is the single most
            // expensive part of a cold-cache request -- but the whole body is
            // cached 24h, and a year whose interims are missing simply yields
            // no quarterly points for that year rather than failing the
            // request. Sequential for the same 020 reason as the loop above.
            const factsByPeriod = {};
            for (const y of years) {
                factsByPeriod[y] = { FY: factsByYear[y] };
                for (const code of ['Q1', 'H1', 'Q3']) {
                    const { facts } = await fetchDartXbrlFacts(env, corpCode, y, 'CFS', { reprtCode: DART_REPRT[code] });
                    if (Object.keys(facts).length > 0) factsByPeriod[y][code] = facts;
                }
            }
            const quarterly = dartQuarterlySeries(factsByPeriod, years);

            // Independent of the facts loop above -- neither blocks the other,
            // and either failing still leaves the filing-derived cards intact.
            const [sharesResult, priceResult] = await Promise.all([
                fetchDartSharesOutstanding(env, corpCode, latestYear),
                fetchDartKrPrice(symbol),
            ]);

            return {
                ok: true,
                body: {
                    schema: 'kfa_engine_v1',
                    label: symbol,
                    view_presets: DART_VIEW_PRESETS,
                    as_of: `${latestYear}-12-31`,
                    currency: 'KRW',
                    meta: {
                        ticker: symbol, corp_code: corpCode, entity: nameKo, entity_eng: null,
                        stock_code: symbol, source: 'opendart', fs_div: 'CFS', acc_mt: '12',
                        shares_outstanding: sharesResult.sharesOutstanding,
                        shares_outstanding_reason: sharesResult.sharesOutstanding === null ? sharesResult.reason : undefined,
                        price: priceResult.price,
                        price_reason: priceResult.price === null ? priceResult.reason : undefined,
                    },
                    basic_cards: dartBasicCardsFromFacts(factsByYear, years, {
                        sharesOutstanding: sharesResult.sharesOutstanding,
                        price: priceResult.price,
                        quarterly,
                    }),
                    data_quality: {
                        input_kind: years.length > 1 ? 'live_fetch_multi_fiscal_year' : 'live_fetch_single_fiscal_year',
                        source_claim: 'opendart',
                        raw_filing_facts_embedded: true,
                        period_alignment: years.length > 1 ? 'multi_fiscal_year' : 'single_fiscal_year_no_history',
                        fiscal_years_fetched: years,
                        fiscal_years_missing: candidateYears.filter((y) => !years.includes(y)),
                        facts_fetched: years.reduce((sum, y) => sum + Object.keys(factsByYear[y]).length, 0),
                        // Which interim reports actually came back, per year --
                        // a quarterly gap in the UI is explained here rather
                        // than looking like a rendering bug.
                        interim_reports_fetched: Object.fromEntries(
                            years.map((y) => [y, Object.keys(factsByPeriod[y] || {}).filter((k) => k !== 'FY')])),
                        quarterly_derivation: 'flows differenced from YTD cumulatives (Q2=H1-Q1, Q3=3Q-H1, Q4=FY-3Q); balances point-in-time',
                        // Reaching here at all required a keyed OpenDART fetch.
                        live_key_present: true,
                    },
                },
            };
        });
    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: JSON_HEADERS });
    }
}

// --- Macro monitor --------------------------------------------------------
// The engine (scripts/macro_monitor, Cursor's) emits one document holding all
// 18 countries with five and ten years of history per indicator -- 2.4 MB. The
// schema is theirs and stays untouched; what changes here is only how much of
// it crosses the wire. The map stage needs the 17 KB shell, and a country click
// needs that one country, so the split happens on this side instead of asking
// the browser to download eighteen countries to draw one.
const MACRO_DOC_PATHS = [
    '/public/data/macro_monitor_v1.json',
    '/data/macro_monitor_v1.json',
];

// Python writes Infinity and NaN as bare literals; JSON has neither, so a
// document containing them cannot be parsed by anything on this side of the
// wire. The engine emitting them is a bug to fix upstream (a percent change
// against a zero base), but a malformed number in one country's ten-year
// series should not take the whole monitor down -- null is what "no value"
// means here, and every reader already skips it.
const MACRO_NONFINITE = /(:|\[|,)(\s*)-?(?:Infinity|NaN)(?=\s*[,\]}])/g;

function macroParse(text) {
    let cleaned = text, pass = 0;
    // One pass leaves neighbours unmatched because the regex consumes the comma
    // that the next value needs as its own prefix.
    while (MACRO_NONFINITE.test(cleaned) && pass++ < 12) {
        MACRO_NONFINITE.lastIndex = 0;
        cleaned = cleaned.replace(MACRO_NONFINITE, '$1$2null');
    }
    return JSON.parse(cleaned);
}

async function macroDoc(env, origin) {
    for (const path of MACRO_DOC_PATHS) {
        try {
            const res = await env.ASSETS.fetch(new Request(new URL(path, origin).toString()));
            if (!res.ok) continue;
            const text = await res.text();
            try {
                return JSON.parse(text);
            } catch (_) {
                return macroParse(text);
            }
        } catch (_) { /* try next */ }
    }
    return null;
}

async function handleMacroMonitor(request, env) {
    const url = new URL(request.url);
    const iso3 = (url.searchParams.get('country') || '').trim().toUpperCase();

    try {
        return await kvCachedJson(env, `macro:v1:${iso3 || 'index'}`, 21600, async () => {
            const doc = await macroDoc(env, url.origin);
            if (!doc) return { ok: false, status: 404, statusText: 'macro_monitor_v1.json not found' };

            if (!iso3) {
                // Everything except the per-country payloads: tab definitions,
                // the reasoning caveats, and enough per-country data to draw
                // and label the map.
                const { countries, ...shell } = doc;
                return {
                    ok: true,
                    body: {
                        ...shell,
                        countries_index: (doc.countries || []).map((c) => ({
                            iso3: c.iso3,
                            iso2: c.iso2,
                            name_ko: c.name_ko,
                            name_en: c.name_en,
                            aliases: c.aliases || [],
                            coords: c.coords,
                            kit: c.kit,
                            benchmark: !!c.benchmark,
                            featured: !!c.featured,
                            asof: c.asof,
                            active_categories: c.active_categories || [],
                            headlines: c.headlines || [],
                            data_status_summary: c.data_status_summary || {},
                        })),
                    },
                };
            }

            const country = (doc.countries || []).find((c) => String(c.iso3).toUpperCase() === iso3);
            if (!country) return { ok: false, status: 404, statusText: `no country ${iso3}` };
            return {
                ok: true,
                body: {
                    schema_version: doc.schema_version,
                    generated_at: doc.generated_at,
                    source: doc.source,
                    disclaimer_ko: doc.disclaimer_ko,
                    // The badge on every chip resolves against this legend, so
                    // it has to ride along with the per-country payload too.
                    data_status_legend: doc.data_status_legend || {},
                    country,
                },
            };
        });
    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: JSON_HEADERS });
    }
}

async function secSearch(env, q) {
    const rows = await secIndex(env);
    const s = q.toLowerCase();
    const starts = [], contains = [];
    for (const [ticker, title] of rows) {
        const t = ticker.toLowerCase(), n = title.toLowerCase();
        if (t === s) starts.unshift([ticker, title]);
        else if (t.startsWith(s) || n.startsWith(s)) starts.push([ticker, title]);
        else if (n.includes(s)) contains.push([ticker, title]);
        if (starts.length >= 12) break;
    }
    return [...starts, ...contains].slice(0, 12).map(([symbol, name]) => ({
        symbol, name, exchange: 'SEC', type: 'EQUITY',
    }));
}

/**
 * Front-month futures/proxy price beside the trade-flow ranking.
 *
 * A flow map says who ships to whom and nothing about what the cargo is worth
 * today, which is the number that moves first when a route is threatened.
 *
 * Where there is no free price the response says which and why rather than
 * pretending: LME's real-time feed is licensed, so nickel, tin, lead and zinc
 * are absent instead of being filled with a COMEX contract that is not the
 * same benchmark, and cobalt, lithium, graphite and rare earths have no
 * liquid contract at all -- those are assessed prices sold by Fastmarkets and
 * Benchmark Mineral. Manganese and chromium have no contract either. Naming
 * the gap is more useful than hiding it behind an empty card.
 *
 * Yahoo publishes agricultural contracts in US cents (`USX`); wheat comes
 * back as 638.25 meaning $6.3825/bu. The conversion happens once, here.
 */
const FUTURES = {
    oil:       { symbol: "CL=F",  unit: "배럴",      exchange: "NYMEX" },
    gas:       { symbol: "NG=F",  unit: "MMBtu",     exchange: "NYMEX" },
    wheat:     { symbol: "ZW=F",  unit: "부셸",      exchange: "CBOT" },
    corn:      { symbol: "ZC=F",  unit: "부셸",      exchange: "CBOT" },
    soybeans:  { symbol: "ZS=F",  unit: "부셸",      exchange: "CBOT" },
    sugar:     { symbol: "SB=F",  unit: "파운드",    exchange: "ICE" },
    coffee:    { symbol: "KC=F",  unit: "파운드",    exchange: "ICE" },
    copper:    { symbol: "HG=F",  unit: "파운드",    exchange: "COMEX" },
    gold:      { symbol: "GC=F",  unit: "온스",      exchange: "COMEX" },
    silver:    { symbol: "SI=F",  unit: "온스",      exchange: "COMEX" },
    platinum:  { symbol: "PL=F",  unit: "온스",      exchange: "NYMEX" },
    aluminum:  { symbol: "ALI=F", unit: "톤",        exchange: "COMEX" },
    // SGX/DCE iron-ore swaps have no free real-time Yahoo ticker; CME's
    // HRC (hot-rolled coil steel) futures track the same demand cycle and are
    // the closest free proxy, labelled as one rather than passed off as an
    // iron-ore price.
    iron_ore:  { symbol: "HRC=F", unit: "톤",        exchange: "COMEX", proxy: "철광석 대신 열연코일(HRC) 선물 프록시" },
};

// No free real-time source. Named so the panel can say which and why, rather
// than rendering an empty box that looks like a bug.
const FUTURES_UNPRICED = {
    nickel: "LME 실시간 시세는 유료입니다 (라이선스 제한)",
    tin: "LME 실시간 시세는 유료입니다 (라이선스 제한)",
    lead: "LME 실시간 시세는 유료입니다 (라이선스 제한)",
    zinc: "LME 실시간 시세는 유료입니다 (라이선스 제한)",
    cobalt: "유동성 있는 선물 계약이 없습니다 (Fastmarkets 등 유료 평가가)",
    lithium: "유동성 있는 선물 계약이 없습니다 (Fastmarkets 등 유료 평가가)",
    graphite: "유동성 있는 선물 계약이 없습니다 (Benchmark Mineral 등 유료 평가가)",
    rare_earths: "유동성 있는 선물 계약이 없습니다 (Benchmark Mineral 등 유료 평가가)",
    manganese: "거래되는 선물 계약이 없습니다",
    chromium: "거래되는 선물 계약이 없습니다",
    thermal_coal: "무료로 확인 가능한 실시간 선물가가 없습니다 (장외 지수 가격)",
    met_coal: "무료로 확인 가능한 실시간 선물가가 없습니다 (장외 지수 가격)",
};

async function handleFutures(request, env) {
    const url = new URL(request.url);
    const want = (url.searchParams.get('commodity') || '').trim();

    if (want && FUTURES_UNPRICED[want]) {
        return new Response(
            JSON.stringify({ commodity: want, priced: false, reason: FUTURES_UNPRICED[want] }),
            { headers: JSON_HEADERS });
    }
    const cfg = FUTURES[want];
    if (!cfg) {
        return new Response(JSON.stringify({ error: `no futures config for: ${want}` }),
            { status: 404, headers: JSON_HEADERS });
    }

    // 15 minutes: this is a delayed quote, and a dashboard reload should not
    // cost an upstream call every time.
    return kvCachedJson(env, `futures:${want}`, 900, async () => {
        const res = await fetch(
            `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(cfg.symbol)}?interval=1d&range=5d`,
            { headers: YF_HEADERS });
        if (!res.ok) return { ok: false, status: res.status };
        const meta = (await res.json())?.chart?.result?.[0]?.meta;
        const last = Number(meta?.regularMarketPrice);
        if (!Number.isFinite(last)) return { ok: false, status: 502, statusText: 'no price in Yahoo response' };

        // USX is US cents; normalise once so the panel never has to remember.
        const cents = meta.currency === 'USX';
        const prev = Number(meta?.chartPreviousClose);
        const px = cents ? last / 100 : last;
        return {
            ok: true,
            body: {
                commodity: want, priced: true, symbol: cfg.symbol,
                exchange: cfg.exchange, proxy: cfg.proxy || null,
                price: Math.round(px * 10000) / 10000,
                currency: "USD", unit: cfg.unit,
                change_pct: Number.isFinite(prev) && prev > 0
                    ? Math.round(((last - prev) / prev) * 1000) / 10 : null,
                as_of: meta?.regularMarketTime
                    ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
                source: "Yahoo Finance", delayed: true,
            },
        };
    });
}

async function handleQuote(request, env) {
    const url = new URL(request.url);
    const action = url.pathname.replace(/^\/api\/quote\/?/, '') || 'search';

    try {
        if (action === 'search') {
            const q = (url.searchParams.get('q') || '').trim();
            if (!q) return new Response(JSON.stringify({ quotes: [] }), { headers: JSON_HEADERS });

            return kvCachedJson(env, `qsearch:${q.toLowerCase()}`, 86400, async () => {
                const yahoo = await yahooSearch(q);
                if (yahoo) return { ok: true, body: { quotes: yahoo, source: 'yahoo' } };

                // Yahoo throttles search far harder than it throttles prices, and
                // it is the only piece of this with a usable substitute: the SEC
                // publishes its filer list as a plain file with no rate limit.
                // Narrower than Yahoo (US filers only, misses some ETFs), but a
                // degraded picker beats a dead one.
                const sec = await secSearch(env, q);
                return { ok: true, body: { quotes: sec, source: 'sec', degraded: true } };
            });
        }

        if (action === 'history') {
            const symbol = (url.searchParams.get('symbol') || '').trim();
            if (!symbol) {
                return new Response(JSON.stringify({ error: 'symbol required' }), { status: 400, headers: JSON_HEADERS });
            }
            const range = ['1y', '2y', '5y'].includes(url.searchParams.get('range'))
                ? url.searchParams.get('range') : '2y';

            // An hour of staleness is immaterial to a covariance estimate built
            // from two years of closes, and it keeps Yahoo from rate-limiting
            // this Worker's shared egress IP.
            return kvCachedJson(env, `yfhist:${symbol}:${range}`, 3600, async () => {
                const yf = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`
                    + `?range=${range}&interval=1d`;
                const res = await fetch(yf, { headers: YF_HEADERS });
                if (!res.ok) return { ok: false, status: res.status };
                const raw = await res.json();

                const r = raw && raw.chart && raw.chart.result && raw.chart.result[0];
                if (!r) return { ok: false, status: 404 };

                const ts = r.timestamp || [];
                const quote = (r.indicators && r.indicators.quote && r.indicators.quote[0]) || {};
                const adj = r.indicators && r.indicators.adjclose && r.indicators.adjclose[0];
                // Adjusted closes when present: splits and dividends otherwise
                // show up as one-day crashes and poison the volatility estimate.
                const closes = (adj && adj.adjclose) || quote.close || [];

                const points = [];
                for (let i = 0; i < ts.length; i++) {
                    const c = closes[i];
                    if (c === null || c === undefined || Number.isNaN(c)) continue;
                    points.push([ts[i], c]);
                }

                const meta = r.meta || {};
                return {
                    ok: true,
                    body: {
                        symbol: meta.symbol || symbol,
                        currency: meta.currency || null,
                        exchange: meta.fullExchangeName || meta.exchangeName || null,
                        price: meta.regularMarketPrice ?? (points.length ? points[points.length - 1][1] : null),
                        points,
                    },
                };
            });
        }

        return new Response(JSON.stringify({ error: 'Invalid quote action' }), { status: 400, headers: JSON_HEADERS });

    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: JSON_HEADERS });
    }
}
