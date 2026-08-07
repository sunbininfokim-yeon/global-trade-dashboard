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

        // Multi-country official reports (US/JP/CN/EU…)
        if (url.pathname.startsWith('/api/official-reports')) {
            return await handleOfficialReports(request, env);
        }

        // Default: Serve Static Assets
        return serveAsset(request, env);
    },

    // Cron-driven cache warm-up (see "triggers" in wrangler.jsonc).
    // Without this the first visitor to open each commodity pays the full
    // UN Comtrade round trip -- several seconds on a 40+ country query. This
    // refreshes every commodity overnight so every real visit is a cache hit.
    async scheduled(event, env, ctx) {
        ctx.waitUntil(warmComtradeCache(env));
    }
};

async function warmComtradeCache(env) {
    if (!env.COMTRADE_API_KEY || !env.API_CACHE) {
        console.log('[warm] skipped: COMTRADE_API_KEY or API_CACHE binding missing');
        return;
    }

    let ok = 0, failed = 0;

    // Sequential on purpose: firing 14 heavy queries at once risks tripping
    // Comtrade's rate limiting, and the cron run has no deadline pressure.
    for (const hs of Object.keys(COMTRADE_TTL)) {
        try {
            const result = await fetchComtrade(env, hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, COMTRADE_PERIOD, 'A');
            if (!result.ok) {
                failed++;
                console.log(`[warm] ${hs} upstream ${result.status}`);
                continue;
            }
            await env.API_CACHE.put(
                comtradeCacheKey(hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, COMTRADE_PERIOD, 'A'),
                JSON.stringify(result.body),
                { expirationTtl: COMTRADE_TTL[hs] }
            );
            ok++;
        } catch (err) {
            failed++;
            console.log(`[warm] ${hs} error: ${err.message}`);
        }
    }

    console.log(`[warm] done: ${ok} cached, ${failed} failed`);
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
    "7108": 86400,   // Gold: 24h
    "7106": 86400,   // Silver: 24h
    "7403": 86400,   // Copper: 24h
    "7901": 604800,  // Zinc: weekly
    "7601": 604800,  // Aluminum: weekly
    "1001": 1209600, // Wheat: 14 days
    "1005": 1209600, // Corn: 14 days
    "1201": 1209600, // Soybeans: 14 days
    "1701": 1209600, // Sugar: 14 days
    "0901": 1209600  // Coffee: 14 days
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
    "petroleum/pri/spt/data/": true,
    "natural-gas/pri/spt/data/": true
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

            return kvCachedJson(env, `eia:${route}:${seriesId}`, 3600, async () => {
                const eiaUrl = `https://api.eia.gov/v2/${route}?api_key=${EIA_KEY}&frequency=daily&data[0]=value&facets[series][]=${encodeURIComponent(seriesId)}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1`;
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
