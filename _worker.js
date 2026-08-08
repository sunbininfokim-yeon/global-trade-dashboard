export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);

        // API Route: UN Comtrade Proxy
        if (url.pathname.startsWith('/api/comtrade')) {
            return await handleComtrade(request, env, ctx);
        }

        // Front-month futures for the commodities the map draws.
        if (url.pathname.startsWith('/api/futures')) {
            return await handleFutures(request, env, ctx);
        }

        // One country's staple-crop net position, aggregated from the same
        // cached Comtrade payloads the trade map uses.
        if (url.pathname.startsWith('/api/crop-trade')) {
            return await handleCropTrade(request, env, ctx);
        }

        // API Route: USDA NASS Quick Stats Proxy
        if (url.pathname.startsWith('/api/usda-nass')) {
            return await handleUsdaNass(request, env, ctx);
        }

        // API Route: USDA FAS PSD (Production, Supply & Distribution) Proxy
        if (url.pathname.startsWith('/api/usda-fas')) {
            return await handleUsdaFas(request, env, ctx);
        }

        // PSD production, resolved by attribute name rather than a guessed id.
        if (url.pathname.startsWith('/api/psd-production')) {
            return await handlePsdProduction(request, env, ctx);
        }

        // API Route: USDA FAS ESR (weekly US export sales by destination)
        if (url.pathname.startsWith('/api/usda-esr/commodities')) {
            return await handleUsdaEsrCommodities(request, env);
        }
        if (url.pathname.startsWith('/api/usda-esr')) {
            return await handleUsdaEsr(request, env, ctx);
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

        // Filed financial statements for the company calculator
        if (url.pathname.startsWith('/api/financials')) {
            return await handleFinancials(request, env);
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

// One commodity costs ceil(64 reporters / REPORTER_CHUNK_SIZE) upstream calls,
// and a Worker invocation may only make so many subrequests. Refilling every
// commodity in a single run exceeded that once the metals were added, and the
// overflow fails silently inside waitUntil -- the tail of the list would simply
// never warm, with nothing in the metrics to say so. Capping the run keeps each
// night inside the ceiling; whatever is left stays cold for a night and gets
// picked up by the next run, because entries already in KV are skipped.
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
const DEFAULT_M49_CODES = "842,840,156,76,32,643,804,356,124,36,250,276,360,458,764,704,818,484,392,410,826,380,724,792,682,784,710,566,586,50,608,364,12,504,616,528,56,756,170,604,152,554,398,642,348,112,600,858,231,800,634,578,368,344,180,158,404,834,104,116,384,288,686,860";

// Every commodity the dashboard can show, keyed by HS code -> cache TTL.
// Doubles as the work list for the scheduled cache warm-up.
const COMTRADE_TTL = {
    "2709": 172800,  // Oil: 48h
    "2711": 172800,  // Gas: 48h
    "2701": 604800,  // Thermal coal: weekly
    "2704": 604800,  // Met coal: weekly
    "261210,284410,284420": 604800, // Uranium: ore + natural + enriched
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
    "8105": 604800,  // Cobalt
    "283691": 604800,// Lithium carbonate
    "2504": 604800,  // Graphite
    "280530": 604800,// Rare earths
    "2601": 604800,  // Iron ore
    "2602,720211,720219": 604800, // Manganese: ore + ferromanganese
    "2610,720241,720249": 604800, // Chromium: ore + ferrochromium
    "8001": 604800,  // Tin
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

function comtradeCacheKey(hs, reporters, partners, period, freq) {
    const scope = (reporters === DEFAULT_M49_CODES && partners === DEFAULT_M49_CODES)
        ? 'default'
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

/**
 * Front-month futures for the commodities the map draws.
 *
 * LME is the right benchmark for nickel, tin, lead and zinc and its real-time
 * feed is licensed, so those are absent rather than substituted -- an aluminium
 * price off COMEX is not the LME cash price and labelling it as one would be
 * worse than the gap. Cobalt, lithium, graphite and rare earths have no liquid
 * contract at all: those are assessed prices from Fastmarkets and Benchmark
 * Mineral, and there is no free equivalent. The panel says so instead of
 * showing a number from somewhere else.
 *
 * Yahoo publishes agricultural contracts in US cents (`USX`), so wheat comes
 * back as 638.25 meaning $6.3825/bu. The currency travels with the quote and
 * the conversion happens once, here, rather than in whichever panel renders it.
 */
const FUTURES = {
    oil:       { symbol: "CL=F",  unit_ko: "배럴",    exchange: "NYMEX" },
    gas:       { symbol: "NG=F",  unit_ko: "MMBtu",  exchange: "NYMEX" },
    uranium:   { symbol: "UX=F",  unit_ko: "파운드",   exchange: "COMEX" },
    wheat:     { symbol: "ZW=F",  unit_ko: "부셸",    exchange: "CBOT" },
    corn:      { symbol: "ZC=F",  unit_ko: "부셸",    exchange: "CBOT" },
    soybeans:  { symbol: "ZS=F",  unit_ko: "부셸",    exchange: "CBOT" },
    sugar:     { symbol: "SB=F",  unit_ko: "파운드",   exchange: "ICE" },
    coffee:    { symbol: "KC=F",  unit_ko: "파운드",   exchange: "ICE" },
    copper:    { symbol: "HG=F",  unit_ko: "파운드",   exchange: "COMEX" },
    gold:      { symbol: "GC=F",  unit_ko: "온스",    exchange: "COMEX" },
    silver:    { symbol: "SI=F",  unit_ko: "온스",    exchange: "COMEX" },
    platinum:  { symbol: "PL=F",  unit_ko: "온스",    exchange: "NYMEX" },
    aluminum:  { symbol: "ALI=F", unit_ko: "톤",     exchange: "COMEX" },
    iron_ore:  { symbol: "HRC=F", unit_ko: "톤",     exchange: "COMEX", proxy_ko: "열연강판 (철광석 대리)" },
};

// No free real-time source. Named so the panel can say which and why, rather
// than rendering an empty box that looks like a bug.
const FUTURES_UNPRICED = {
    nickel:      "LME 실시간은 유료",
    tin:         "LME 실시간은 유료",
    lead:        "LME 실시간은 유료",
    zinc:        "LME 실시간은 유료",
    cobalt:      "거래소 상장 없음 · 평가가격(유료)",
    lithium:     "거래소 상장 없음 · 평가가격(유료)",
    graphite:    "거래소 상장 없음 · 평가가격(유료)",
    rare_earths: "거래소 상장 없음 · 평가가격(유료)",
    manganese:   "거래소 상장 없음",
    chromium:    "거래소 상장 없음",
};

async function handleFutures(request, env, ctx) {
    const url = new URL(request.url);
    const want = (url.searchParams.get('commodity') || '').trim();

    if (want && FUTURES_UNPRICED[want]) {
        return new Response(
            JSON.stringify({ commodity: want, priced: false, reason_ko: FUTURES_UNPRICED[want] }),
            { headers: JSON_HEADERS });
    }
    const keys = want ? (FUTURES[want] ? [want] : []) : Object.keys(FUTURES);
    if (!keys.length) {
        return new Response(JSON.stringify({ error: `unknown commodity: ${want}` }),
            { status: 404, headers: JSON_HEADERS });
    }

    // 15 minutes: these are delayed quotes, and a dashboard reload should not
    // cost an upstream call each time.
    return kvCachedJson(env, `futures:${keys.join(',')}`, 900, async () => {
        const out = [];
        await Promise.all(keys.map(async (key) => {
            const cfg = FUTURES[key];
            try {
                const res = await fetch(
                    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(cfg.symbol)}?interval=1d&range=5d`,
                    { headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" } });
                if (!res.ok) return;
                const meta = (await res.json())?.chart?.result?.[0]?.meta;
                const last = Number(meta?.regularMarketPrice);
                if (!Number.isFinite(last)) return;

                // USX is US cents; normalise once so no panel has to remember.
                const cents = meta.currency === 'USX';
                const prev = Number(meta?.chartPreviousClose);
                const px = cents ? last / 100 : last;
                out.push({
                    commodity: key, priced: true, symbol: cfg.symbol,
                    exchange: cfg.exchange, proxy_ko: cfg.proxy_ko || null,
                    price: Math.round(px * 10000) / 10000,
                    currency: "USD", unit_ko: cfg.unit_ko,
                    change_pct: Number.isFinite(prev) && prev > 0
                        ? Math.round(((last - prev) / prev) * 1000) / 10 : null,
                    as_of: meta?.regularMarketTime
                        ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
                });
            } catch (_) { /* one missing quote must not empty the panel */ }
        }));
        out.sort((a, b) => keys.indexOf(a.commodity) - keys.indexOf(b.commodity));
        return { ok: true, body: { source: "Yahoo Finance (지연 시세)", quotes: out } };
    });
}

/**
 * One country's net position in the staple crops, in tonnes.
 *
 * The crop monitor wants "wheat: net importer, N tonnes" next to a yield
 * forecast, and the raw Comtrade payloads that answer it are 3.4 MB across this
 * basket -- too much to ship to a browser that needs six numbers. The Worker
 * already holds those payloads in KV for the trade map, so it aggregates here
 * and returns a few hundred bytes.
 *
 * Weight, not value: a forecast is in tonnes per hectare, and putting dollars
 * beside it would invite comparing quantities against prices. Rows without
 * netWgt are dropped rather than converted -- an estimated tonnage would look
 * exactly like a reported one.
 */
const CROP_TRADE_BASKET = [
    { key: "wheat",    hs: "1001", label_ko: "밀",    label_en: "Wheat" },
    { key: "corn",     hs: "1005", label_ko: "옥수수", label_en: "Corn" },
    { key: "rice",     hs: "1006", label_ko: "쌀",    label_en: "Rice" },
    { key: "soybeans", hs: "1201", label_ko: "대두",   label_en: "Soybeans" },
    { key: "sugar",    hs: "1701", label_ko: "설탕",   label_en: "Sugar" },
];

async function handleCropTrade(request, env, ctx) {
    const url = new URL(request.url);
    const reporter = (url.searchParams.get('reporter') || '').trim();
    if (!/^\d{1,4}$/.test(reporter)) {
        return new Response(JSON.stringify({ error: "reporter must be an M49 numeric code" }),
            { status: 400, headers: JSON_HEADERS });
    }
    if (!env.COMTRADE_API_KEY) return missingKey('COMTRADE_API_KEY');

    const period = url.searchParams.get('period') || COMTRADE_PERIOD;
    // The US reports as 842; 840 returns nothing. Accept either and read both.
    const wanted = new Set(reporter === '840' || reporter === '842'
        ? ['840', '842'] : [reporter]);

    const out = [];
    for (const crop of CROP_TRADE_BASKET) {
        // Same key the trade map and the nightly warm-up build, so this route
        // rides their cache instead of opening a second one.
        const body = await kvCachedJson(
            env,
            comtradeCacheKey(crop.hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, period, 'A'),
            COMTRADE_TTL[crop.hs] || 604800,
            () => fetchComtrade(env, crop.hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, period, 'A'),
        ).then((r) => r.json()).catch(() => null);

        const rows = body?.data || [];

        // Largest row per counterparty, not the sum of them. One query can come
        // back with the heading total and its subheadings as separate rows for
        // the same pair -- Brazil files soybeans that way, six rows for
        // Brazil-Argentina alone -- and adding them counted the same cargo
        // twice. Summed, Brazil exported 197 Mt of soybeans in 2023, more than
        // it grew; taking the largest row gives 98.7 Mt against an actual ~101.
        // Where a reporter files one row per partner, as Egypt and the US do,
        // the largest row is the only row and nothing changes. data.js resolves
        // the map's arcs the same way, so the two agree.
        const best = new Map();
        let missing = 0;
        for (const r of rows) {
            if (!wanted.has(String(r.reporterCode))) continue;
            if (r.flowCode !== 'X' && r.flowCode !== 'M') continue;
            const w = Number(r.netWgt);
            if (!Number.isFinite(w) || w <= 0) { missing++; continue; }
            const k = `${r.flowCode}:${r.partnerCode}`;
            if (w > (best.get(k) || 0)) best.set(k, w);
        }
        let exp = 0, imp = 0;
        for (const [k, w] of best) {
            if (k.startsWith('X:')) exp += w; else imp += w;
        }
        if (exp === 0 && imp === 0) continue;
        out.push({
            ...crop,
            // Comtrade reports netWgt in kilograms.
            export_t: Math.round(exp / 1000),
            import_t: Math.round(imp / 1000),
            net_t: Math.round((exp - imp) / 1000),
            rows_without_weight: missing,
        });
    }

    return new Response(
        JSON.stringify({ reporter, period, source: "UN Comtrade", unit: "tonnes", crops: out }),
        { headers: JSON_HEADERS });
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

/**
 * PSD's attributeId -> name table.
 *
 * The commodity/country/year endpoint returns rows tagged only with a numeric
 * attributeId -- no name travels with the data. Hardcoding "28 means
 * Production" from a guess is exactly the kind of error this project has been
 * catching all week (chromium and manganese read as barely-traded because an
 * HS code was assumed instead of checked). FAS publishes its own reference
 * list; this resolves attributeId to name from that list instead, so a wrong
 * guess is structurally impossible -- the worst case is an unresolved id,
 * which shows up as a gap, not a wrong number wearing a right label.
 *
 * Cached for a month: this is a code table, not a data series.
 */
async function fetchPsdAttributeNames(env) {
    return kvCachedJson(env, 'usda-fas:attributes', 2592000, async () => {
        const res = await fetch('https://api.fas.usda.gov/api/psd/attributes',
            { headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" } });
        if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };
        const rows = await res.json();
        const byId = {};
        for (const r of rows) {
            const id = r.attributeId ?? r.AttributeId ?? r.id;
            const name = r.attributeName ?? r.AttributeName ?? r.name;
            if (id != null && name) byId[id] = name;
        }
        return { ok: true, body: byId };
    }).then((r) => r.json());
}

/**
 * PSD's own country code -> name table, same reasoning as the attributes
 * table above: FAS uses its own numbering (not ISO or M49), and guessing a
 * two-letter code risks silently querying the wrong country. Resolved by
 * name instead.
 */
async function fetchPsdCountryCodes(env) {
    return kvCachedJson(env, 'usda-fas:countries', 2592000, async () => {
        const res = await fetch('https://api.fas.usda.gov/api/psd/countries',
            { headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" } });
        if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };
        const rows = await res.json();
        const byName = {};
        for (const r of rows) {
            const code = r.countryCode ?? r.CountryCode;
            const name = r.countryName ?? r.CountryName;
            if (code != null && name) byName[name.trim().toLowerCase()] = code;
        }
        return { ok: true, body: byName };
    }).then((r) => r.json());
}

/** PSD's own commodity code -> name table, same reasoning again. */
async function fetchPsdCommodityCodes(env) {
    return kvCachedJson(env, 'usda-fas:commodities', 2592000, async () => {
        const res = await fetch('https://api.fas.usda.gov/api/psd/commodities',
            { headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" } });
        if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };
        const rows = await res.json();
        const byName = {};
        for (const r of rows) {
            const code = r.commodityCode ?? r.CommodityCode;
            const name = r.commodityName ?? r.CommodityName;
            if (code != null && name) byName[name.trim().toLowerCase()] = code;
        }
        return { ok: true, body: byName };
    }).then((r) => r.json());
}

/**
 * One country's PSD production figure for one commodity/marketing year,
 * resolved by attribute name rather than a hardcoded id. countryCode accepts
 * either FAS's own code (if the caller already knows it) or a plain English
 * name to resolve through fetchPsdCountryCodes -- the crop-trade panel has
 * country names on hand already and should not have to carry a second code
 * table just to call this route.
 */
async function handlePsdProduction(request, env, ctx) {
    const url = new URL(request.url);
    let commodityCode = url.searchParams.get('commodityCode');
    const commodityName = url.searchParams.get('commodityName');
    let countryCode = url.searchParams.get('countryCode');
    const countryName = url.searchParams.get('countryName');
    const year = url.searchParams.get('year');

    const SAFE = /^[A-Za-z0-9]+$/;
    if (!year || !SAFE.test(year) || (!commodityCode && !commodityName) || (!countryCode && !countryName)) {
        return new Response(
            JSON.stringify({ error: "year, one of commodityCode/commodityName, and one of countryCode/countryName are required" }),
            { status: 400, headers: JSON_HEADERS });
    }
    if (!env.USDA_FAS_API_KEY) return missingKey('USDA_FAS_API_KEY');

    if (!countryCode || !SAFE.test(countryCode)) {
        const countries = await fetchPsdCountryCodes(env);
        if (!countries.ok) {
            return new Response(JSON.stringify({ error: 'PSD country reference unavailable', detail: countries }),
                { status: 502, headers: JSON_HEADERS });
        }
        countryCode = countries.body[String(countryName).trim().toLowerCase()];
        if (!countryCode) {
            return new Response(JSON.stringify({ error: `PSD has no country named "${countryName}"` }),
                { status: 404, headers: JSON_HEADERS });
        }
    }
    if (!commodityCode || !SAFE.test(commodityCode)) {
        const commodities = await fetchPsdCommodityCodes(env);
        if (!commodities.ok) {
            return new Response(JSON.stringify({ error: 'PSD commodity reference unavailable', detail: commodities }),
                { status: 502, headers: JSON_HEADERS });
        }
        commodityCode = commodities.body[String(commodityName).trim().toLowerCase()];
        if (!commodityCode) {
            return new Response(JSON.stringify({ error: `PSD has no commodity named "${commodityName}"` }),
                { status: 404, headers: JSON_HEADERS });
        }
    }

    const attrNames = await fetchPsdAttributeNames(env);
    if (!attrNames.ok) {
        return new Response(JSON.stringify({ error: 'PSD attribute reference unavailable', detail: attrNames }),
            { status: 502, headers: JSON_HEADERS });
    }

    const cacheKey = `usda-fas:${commodityCode}:${countryCode}:${year}`;
    const dataRes = await kvCachedJson(env, cacheKey, 86400, async () => {
        const fasUrl = `https://api.fas.usda.gov/api/psd/commodity/${commodityCode}/country/${countryCode}/year/${year}`;
        const res = await fetch(fasUrl, { headers: { "X-Api-Key": env.USDA_FAS_API_KEY, "Accept": "application/json" } });
        if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };
        return { ok: true, body: await res.json() };
    });
    const rows = await dataRes.json();
    if (!Array.isArray(rows)) {
        return new Response(JSON.stringify({ error: 'PSD data unavailable', detail: rows }),
            { status: 502, headers: JSON_HEADERS });
    }

    // Latest month on file for this MY, so a mid-year revision is picked up
    // rather than the first estimate PSD ever published for it.
    let latestMonth = null;
    for (const r of rows) {
        if (!latestMonth || String(r.month) > latestMonth) latestMonth = String(r.month);
    }
    const production = rows.find((r) => r.month === latestMonth
        && (attrNames.body[r.attributeId] || '').toLowerCase() === 'production');

    if (!production) {
        return new Response(JSON.stringify({
            commodityCode, countryCode, year, production: null,
            reason: 'no row named "Production" in this response',
        }), { headers: JSON_HEADERS });
    }
    // unitId 8 is "(1000 MT)" in every PSD series this proxy has been asked
    // for; carrying the raw id rather than a hardcoded label so a commodity
    // reported in a different unit is visible as a mismatch, not silently
    // mislabelled the way the attribute id would have been.
    return new Response(JSON.stringify({
        commodityCode, countryCode, year,
        production: production.value, unit_id: production.unitId,
        marketing_year: production.marketYear, as_of_month: production.month,
    }), { headers: JSON_HEADERS });
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

            return kvCachedJson(env, `fred:${series_id}`, 3600, async () => {
                const fredUrl = `https://api.stlouisfed.org/fred/series/observations?series_id=${encodeURIComponent(series_id)}&api_key=${FRED_KEY}&file_type=json&sort_order=desc&limit=1`;
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
            // Stocks move weekly and the panel shows a change, so keep a short
            // history rather than one point.
            const length = freq === 'weekly' ? 12 : 1;
            return kvCachedJson(env, `eia:${route}:${seriesId}:${length}`, 3600, async () => {
                const eiaUrl = `https://api.eia.gov/v2/${route}?api_key=${EIA_KEY}&frequency=${freq}&data[0]=value&facets[series][]=${encodeURIComponent(seriesId)}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=${length}`;
                const res = await fetch(eiaUrl);
                if (!res.ok) return { ok: false, status: res.status };
                return { ok: true, body: await res.json() };
            });
        }

        if (source === 'yfinance') {
            const symbol = url.searchParams.get('symbol');

            return kvCachedJson(env, `yfinance:${symbol}`, 3600, async () => {
                // Fetch 5 years of monthly data
                const period1 = Math.floor(new Date().setFullYear(new Date().getFullYear() - 5) / 1000);
                const period2 = Math.floor(Date.now() / 1000);
                const yfUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?period1=${period1}&period2=${period2}&interval=1mo`;

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
    shares: ['CommonStockSharesOutstanding', 'EntityCommonStockSharesOutstanding'],
};

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
            perTag.set(secFiscalYear(p), p.val);
        }
        for (const [fy, val] of perTag) if (!byYear.has(fy)) byYear.set(fy, val);
    }
    return byYear.size ? { tag: used.join('+'), unit, years: byYear } : null;
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

            const picked = {}, used = {};
            for (const [key, names] of Object.entries(SEC_TAGS)) {
                const got = secPickAnnual(gaap, names);
                if (got) { picked[key] = got.years; used[key] = got.tag; }
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

            return {
                ok: true,
                body: {
                    source: 'SEC XBRL',
                    symbol,
                    cik,
                    name: doc.entityName || hit[1],
                    currency: 'USD',
                    statements,
                    tags_used: used,
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
