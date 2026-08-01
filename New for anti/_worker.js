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

        // API Route: Macro Financial Data Proxy (FRED, BOK, EIA, Yahoo Finance)
        if (url.pathname.startsWith('/api/macro')) {
            return await handleMacro(request, env, ctx);
        }

        // Default: Serve Static Assets
        return env.ASSETS.fetch(request);
    }
};

async function handleComtrade(request, env, ctx) {
    const url = new URL(request.url);
    const hs = url.searchParams.get('hs') || '2709';
    const reporters = url.searchParams.get('reporters') || 'all';
    const partners = url.searchParams.get('partners') || 'all';
    const period = url.searchParams.get('period') || '2023';

    const COMTRADE_KEY = env.COMTRADE_API_KEY;
    if (!COMTRADE_KEY) {
        return new Response("Server misconfiguration: COMTRADE_API_KEY is not set.", { status: 500 });
    }

    // Set Cache TTL based on commodity type
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

    // Build UN Comtrade API URL (X = Exports, M = Imports for Mirror Data)
    const comtradeUrl = `https://comtradeapi.un.org/data/v1/get/C/A/HS?reporterCode=${reporters}&period=${period}&partnerCode=${partners}&cmdCode=${hs}&flowCode=X,M`;

    try {
        const comtradeRes = await fetch(comtradeUrl, {
            headers: {
                "Ocp-Apim-Subscription-Key": COMTRADE_KEY,
                "Accept": "application/json"
            }
        });

        if (!comtradeRes.ok) {
            return new Response(`Comtrade API Error: ${comtradeRes.status} ${comtradeRes.statusText}`, { status: 502 });
        }

        const data = await comtradeRes.json();

        // Return the data with aggressive Edge Caching and CORS headers
        return new Response(JSON.stringify(data), {
            headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": `public, max-age=${cacheTtl}, s-maxage=${cacheTtl}`,
                "Cloudflare-CDN-Cache-Control": `max-age=${cacheTtl}`
            }
        });
    } catch (err) {
        return new Response(`Proxy Error: ${err.message}`, { status: 500 });
    }
}

async function handleUsdaNass(request, env, ctx) {
    const url = new URL(request.url);

    const NASS_KEY = env.USDA_NASS_API_KEY;
    if (!NASS_KEY) {
        return new Response("Server misconfiguration: USDA_NASS_API_KEY is not set.", { status: 500 });
    }

    // Forward all incoming query params except our own, then attach the key server-side.
    const nassParams = new URLSearchParams(url.searchParams);
    nassParams.set('key', NASS_KEY);
    nassParams.set('format', nassParams.get('format') || 'JSON');

    const nassUrl = `https://quickstats.nass.usda.gov/api/api_GET/?${nassParams.toString()}`;

    try {
        const nassRes = await fetch(nassUrl, { headers: { "Accept": "application/json" } });

        if (!nassRes.ok) {
            return new Response(`USDA NASS API Error: ${nassRes.status} ${nassRes.statusText}`, { status: 502 });
        }

        const data = await nassRes.json();

        return new Response(JSON.stringify(data), {
            headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400, s-maxage=86400",
                "Cloudflare-CDN-Cache-Control": "max-age=86400"
            }
        });
    } catch (err) {
        return new Response(`Proxy Error: ${err.message}`, { status: 500 });
    }
}

// Upstream routes that /api/macro?source=eia is allowed to proxy. Without this
// allowlist the `route` param would let a caller aim our API key at any EIA path.
const EIA_ROUTES = {
    "petroleum/pri/spt/data/": true,
    "natural-gas/pri/spt/data/": true
};

const JSON_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    // Macro series update at most daily; cache at the edge for an hour.
    "Cache-Control": "public, max-age=3600, s-maxage=3600"
};

function missingKey(name) {
    return new Response(
        JSON.stringify({ error: `Server misconfiguration: ${name} is not set.` }),
        { status: 500, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } }
    );
}

async function handleMacro(request, env, ctx) {
    const url = new URL(request.url);
    const source = url.searchParams.get('source');

    try {
        if (source === 'fred') {
            const series_id = url.searchParams.get('series_id');
            const FRED_KEY = env.FRED_API_KEY;
            if (!FRED_KEY) return missingKey('FRED_API_KEY');

            const fredUrl = `https://api.stlouisfed.org/fred/series/observations?series_id=${encodeURIComponent(series_id)}&api_key=${FRED_KEY}&file_type=json&sort_order=desc&limit=1`;

            const res = await fetch(fredUrl);
            if (!res.ok) {
                return new Response(JSON.stringify({ error: `FRED API Error: ${res.status}` }), { status: 502, headers: JSON_HEADERS });
            }
            const data = await res.json();
            return new Response(JSON.stringify(data), { headers: JSON_HEADERS });
        }

        if (source === 'bok') {
            const BOK_KEY = env.BOK_API_KEY;
            if (!BOK_KEY) return missingKey('BOK_API_KEY');

            const bokUrl = `https://ecos.bok.or.kr/api/KeyStatisticList/${BOK_KEY}/json/kr/1/100/`;

            const res = await fetch(bokUrl);
            if (!res.ok) {
                return new Response(JSON.stringify({ error: `BOK API Error: ${res.status}` }), { status: 502, headers: JSON_HEADERS });
            }
            const data = await res.json();
            return new Response(JSON.stringify(data), { headers: JSON_HEADERS });
        }

        if (source === 'eia') {
            const route = url.searchParams.get('route');
            const seriesId = url.searchParams.get('seriesId');
            const EIA_KEY = env.EIA_API_KEY;
            if (!EIA_KEY) return missingKey('EIA_API_KEY');

            if (!EIA_ROUTES[route]) {
                return new Response(JSON.stringify({ error: "Unsupported EIA route" }), { status: 400, headers: JSON_HEADERS });
            }

            const eiaUrl = `https://api.eia.gov/v2/${route}?api_key=${EIA_KEY}&frequency=daily&data[0]=value&facets[series][]=${encodeURIComponent(seriesId)}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1`;

            const res = await fetch(eiaUrl);
            if (!res.ok) {
                return new Response(JSON.stringify({ error: `EIA API Error: ${res.status}` }), { status: 502, headers: JSON_HEADERS });
            }
            const data = await res.json();
            return new Response(JSON.stringify(data), { headers: JSON_HEADERS });
        }

        if (source === 'yfinance') {
            const symbol = url.searchParams.get('symbol');
            // Fetch 5 years of monthly data
            const period1 = Math.floor(new Date().setFullYear(new Date().getFullYear() - 5) / 1000);
            const period2 = Math.floor(Date.now() / 1000);
            const yfUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?period1=${period1}&period2=${period2}&interval=1mo`;

            const res = await fetch(yfUrl, {
                headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
            });
            // Yahoo rate-limits datacenter IPs and answers 429 with plain text,
            // so res.json() must not be called blindly.
            if (!res.ok) {
                return new Response(
                    JSON.stringify({ error: `Yahoo Finance unavailable (${res.status})` }),
                    { status: 502, headers: JSON_HEADERS }
                );
            }
            const data = await res.json();
            return new Response(JSON.stringify(data), { headers: JSON_HEADERS });
        }

        return new Response(JSON.stringify({ error: "Invalid macro source" }), { status: 400, headers: JSON_HEADERS });

    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { 
            status: 500, 
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
    }
}
