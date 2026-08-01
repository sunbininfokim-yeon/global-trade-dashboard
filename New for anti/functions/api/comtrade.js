// Cloudflare Pages Function — CORS Proxy for UN Comtrade API
// Endpoint: /api/comtrade?hs=2709&reporters=682,643&partners=156,392&period=2023
// 출처: UN Comtrade (https://comtradeapi.un.org)

const COMTRADE_KEY = "82e21c24672d4610815c5e45f92f5fca";

// Smart Scheduling: 상품별 캐시 TTL (초)
const CACHE_TTL = {
    // 에너지 — 매일
    "2709": 86400,      // Crude Oil (원유)
    "2711": 86400,      // Natural Gas (천연가스)
    // 에너지 — 주 1회
    "2701": 604800,     // Thermal Coal (연료탄)
    "2704": 604800,     // Met Coal (원료탄)
    // 귀금속
    "7108": 86400,      // Gold (금) — 매일
    "7106": 172800,     // Silver (은) — 격일
    // 비철금속
    "7403": 172800,     // Copper (구리) — 격일
    "7901": 604800,     // Zinc (아연) — 주 1회
    "7601": 604800,     // Aluminum (알루미늄) — 주 1회
    // 농산물
    "1001": 604800,     // Wheat (밀) — 주 1회
    "1005": 604800,     // Corn (옥수수) — 주 1회
    "1201": 604800,     // Soybeans (대두) — 주 1회
    "1701": 1209600,    // Sugar (설탕) — 격주
    "0901": 1209600,    // Coffee (커피) — 격주
};

export async function onRequest(context) {
    // Handle CORS preflight
    if (context.request.method === "OPTIONS") {
        return new Response(null, {
            headers: {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "86400",
            }
        });
    }

    const url = new URL(context.request.url);
    const hs = url.searchParams.get("hs");
    const reporters = url.searchParams.get("reporters");
    const partners = url.searchParams.get("partners");
    const period = url.searchParams.get("period") || "2023";

    if (!hs || !reporters || !partners) {
        return new Response(JSON.stringify({
            error: "Missing required parameters: hs, reporters, partners",
            usage: "/api/comtrade?hs=2709&reporters=682,643,840&partners=156,392,410&period=2023"
        }), {
            status: 400,
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
    }

    const cacheTtl = CACHE_TTL[hs] || 604800; // Default: weekly

    // Build UN Comtrade API URL
    // flowCode=X means Exports, flowCode=M means Imports
    const comtradeUrl = `https://comtradeapi.un.org/data/v1/get/C/A/HS?reporterCode=${reporters}&period=${period}&partnerCode=${partners}&cmdCode=${hs}&flowCode=X`;

    try {
        const comtradeRes = await fetch(comtradeUrl, {
            headers: {
                "Ocp-Apim-Subscription-Key": COMTRADE_KEY
            },
            cf: {
                cacheTtl: cacheTtl,
                cacheEverything: true
            }
        });

        if (!comtradeRes.ok) {
            const errorText = await comtradeRes.text();
            return new Response(JSON.stringify({
                error: `UN Comtrade API returned ${comtradeRes.status}`,
                detail: errorText,
                source: "UN Comtrade (comtradeapi.un.org)"
            }), {
                status: comtradeRes.status,
                headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
            });
        }

        const data = await comtradeRes.json();

        return new Response(JSON.stringify({
            ...data,
            _meta: {
                source: "UN Comtrade (comtradeapi.un.org)",
                hsCode: hs,
                cacheTtlSeconds: cacheTtl,
                fetchedAt: new Date().toISOString(),
                proxy: "Cloudflare Pages Function"
            }
        }), {
            headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": `public, max-age=${cacheTtl}`,
                "X-Data-Source": "UN Comtrade",
                "X-Cache-TTL": `${cacheTtl}s`
            }
        });

    } catch (e) {
        return new Response(JSON.stringify({
            error: "Proxy fetch failed",
            message: e.message,
            source: "UN Comtrade (comtradeapi.un.org)"
        }), {
            status: 502,
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
    }
}
