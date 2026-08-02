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

        // API Route: Macro Financial Data Proxy (FRED, BOK, EIA, Yahoo Finance)
        if (url.pathname.startsWith('/api/macro')) {
            return await handleMacro(request, env, ctx);
        }

        // Default: Serve Static Assets
        return env.ASSETS.fetch(request);
    }
};

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
        const cached = await kv.get(cacheKey);
        if (cached !== null) {
            return new Response(cached, { headers: { ...JSON_HEADERS, "X-Cache": "HIT" } });
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
        await kv.put(cacheKey, json, { expirationTtl: ttlSeconds });
    }
    return new Response(json, { headers: { ...JSON_HEADERS, "X-Cache": "MISS" } });
}

async function handleComtrade(request, env, ctx) {
    const url = new URL(request.url);
    const hs = url.searchParams.get('hs') || '2709';
    const reporters = url.searchParams.get('reporters') || 'all';
    const partners = url.searchParams.get('partners') || 'all';
    const period = url.searchParams.get('period') || '2023';

    const COMTRADE_KEY = env.COMTRADE_API_KEY;
    if (!COMTRADE_KEY) return missingKey('COMTRADE_API_KEY');

    // Cache TTL by commodity -- how often each is worth re-querying.
    const CACHE_TTL = {
        "2709": 172800,  // Oil: 48h
        "2711": 172800,  // Gas: 48h
        "7108": 86400,   // Gold: 24h
        "7106": 86400,   // Silver: 24h
        "7403": 86400,   // Copper: 24h
        "1001": 1209600, // Wheat: 14 days
        "1005": 1209600, // Corn: 14 days
        "1201": 1209600, // Soybeans: 14 days
        "1701": 1209600, // Sugar: 14 days
        "0901": 1209600  // Coffee: 14 days
    };
    const cacheTtl = CACHE_TTL[hs] || 604800; // Default: weekly

    const cacheKey = `comtrade:${hs}:${reporters}:${partners}:${period}`;

    return kvCachedJson(env, cacheKey, cacheTtl, async () => {
        // Build UN Comtrade API URL (X = Exports, M = Imports for Mirror Data)
        const comtradeUrl = `https://comtradeapi.un.org/data/v1/get/C/A/HS?reporterCode=${reporters}&period=${period}&partnerCode=${partners}&cmdCode=${hs}&flowCode=X,M`;

        const comtradeRes = await fetch(comtradeUrl, {
            headers: {
                "Ocp-Apim-Subscription-Key": COMTRADE_KEY,
                "Accept": "application/json"
            }
        });

        if (!comtradeRes.ok) {
            return { ok: false, status: comtradeRes.status, statusText: comtradeRes.statusText };
        }
        return { ok: true, body: await comtradeRes.json() };
    });
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
