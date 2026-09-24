import PolicyEvidence from './New for anti/policy-evidence.js';

export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);

        // Which annual year the map is on, and how far the next one has got.
        if (url.pathname === '/api/comtrade/status') {
            return await handleComtradeStatus(env);
        }

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

        // US policy (bills / executive orders / regulations) out of Supabase
        if (url.pathname.startsWith('/api/us/')) {
            return await handleUsPolicy(request, env);
        }

        // Official crop/energy/metal reports for one commodity × country window
        if (url.pathname.startsWith('/api/commodity-reports')) {
            return await handleCommodityReports(request, env);
        }

        // NASA GIBS 야간광 타일 프록시 (매크로 지도 베이스맵)
        if (url.pathname.startsWith('/api/night-tile/')) {
            return await handleNightTile(request, url);
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


// === NASA 야간광 타일 프록시 =============================================
//
// 매크로 지도 베이스맵(VIIRS Black Marble)을 브라우저가 gibs.earthdata.nasa.gov
// 에 직접 붙어 받으면, 그 브라우저가 NASA 에 닿는지에 그림이 걸린다 -- 사내망
// 차단, 광고 차단기, 임베드 환경의 CSP 어느 하나만 걸려도 지도가 통째로 검게
// 남는다. 같은 출처로 받아 오면 그 실패면이 사라지고, 엣지 캐시가 한 번 받은
// 타일을 재사용한다.
const GIBS_TILE_BASE = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default';
const GIBS_MATRIX = 'GoogleMapsCompatible_Level8';
// 처음엔 jpeg + 2016-01-01 하나만 시도했고 502 로 떨어졌다. 조합을 여러 개 태워
// 상류에 직접 물어본 결과, 틀린 건 확장자 하나였다 -- Black Marble 은 png 로만
// 발행된다. 2026-09-03 프로덕션 확인: 첫 줄이 200 image/png 86,005 bytes (256×256).
// 나머지는 이름·표기가 바뀌었을 때를 위한 후퇴 경로이고, 전부 실패하면 각각이
// 무엇을 돌려줬는지 502 본문에 적힌다.
const GIBS_TILE_VARIANTS = [
    { label: '2016 png', path: `2016-01-01/${GIBS_MATRIX}`, ext: 'png' },
    { label: '2012 png', path: `2012-01-01/${GIBS_MATRIX}`, ext: 'png' },
    { label: 'no-time png', path: GIBS_MATRIX, ext: 'png' },
    { label: 'default png', path: `default/${GIBS_MATRIX}`, ext: 'png' },
    { label: '2016 jpeg', path: `2016-01-01/${GIBS_MATRIX}`, ext: 'jpeg' },
];
// 한 번 통한 조합은 이 아이솔레이트가 사는 동안 계속 쓴다. 그러지 않으면 캐시가
// 빈 타일마다 앞선 조합들의 404 를 다시 받아 낸다.
let GIBS_WINNER = null;
const NIGHT_TILE_MAX_Z = 8;

async function handleNightTile(request, url) {
    const m = url.pathname.match(/^\/api\/night-tile\/(\d+)\/(\d+)\/(\d+)(?:\.jpe?g)?$/);
    if (!m) return new Response('bad tile path', { status: 400 });
    const [z, y, x] = m.slice(1, 4).map(Number);
    const span = 2 ** z;
    if (z > NIGHT_TILE_MAX_Z || y >= span || x >= span) {
        return new Response('tile out of range', { status: 404 });
    }

    const cache = caches.default;
    const cacheKey = new Request(`${url.origin}/api/night-tile/${z}/${y}/${x}.jpg`, { method: 'GET' });
    const hit = await cache.match(cacheKey).catch(() => null);
    if (hit) return hit;

    // 실패했을 때 무엇이 막혔는지 말해야 한다. 그냥 502 만 뱉으면 상류가 404 인지
    // (레이어 이름이 틀렸다) 연결이 끊긴 건지(NASA 가 안 받는다) 구분할 수 없고,
    // 그 구분 없이는 고칠 수가 없다. 브라우저로 이 URL 을 열면 그대로 읽힌다.
    const tried = [];
    let upstream = null;
    let served = null;
    // 한 번 통한 조합을 맨 앞에 세운다. 첫 요청만 탐색하고, 그 뒤로는 곧장 간다.
    const order = GIBS_WINNER
        ? [GIBS_WINNER, ...GIBS_TILE_VARIANTS.filter((v) => v !== GIBS_WINNER)]
        : GIBS_TILE_VARIANTS;
    for (const variant of order) {
        const src = `${GIBS_TILE_BASE}/${variant.path}/${z}/${y}/${x}.${variant.ext}`;
        let res = null;
        let err = '';
        try {
            res = await fetch(src, { cf: { cacheEverything: true, cacheTtl: 2592000 } });
        } catch (e) {
            err = `${e && e.name}: ${e && e.message}`;
        }
        const type = res ? (res.headers.get('content-type') || '') : '';
        tried.push(`${variant.label} → ${res ? `${res.status} ${type}` : err || 'no response'}`);
        // 200 인데 이미지가 아닌 경우가 있다 (GIBS 는 오류를 XML 로 준다).
        if (res && res.ok && type.startsWith('image/')) {
            upstream = res;
            served = variant;
            GIBS_WINNER = variant;
            break;
        }
    }
    if (!upstream) {
        // 클라이언트의 onTileError 가 이걸 세고, 쌓이면 벡터 실루엣으로 내려앉는다.
        return new Response(
            `tile upstream failed\n${tried.join('\n')}\n`,
            { status: 502, headers: { 'Content-Type': 'text/plain; charset=utf-8' } },
        );
    }

    const out = new Response(upstream.body, {
        status: 200,
        headers: {
            'Content-Type': upstream.headers.get('content-type') || 'image/png',
            // 연간 합성이라 사실상 불변이다. 길게 잡아 둔다.
            'Cache-Control': 'public, max-age=2592000, immutable',
            'Access-Control-Allow-Origin': '*',
            // 어느 조합이 실제로 응답했는지. 상류 표기가 바뀌어도 curl -I 한 줄로 안다.
            'X-Night-Tile-Variant': served ? served.label : 'unknown',
        },
    });
    await cache.put(cacheKey, out.clone()).catch(() => {});
    return out;
}

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
    // (and the small metadata comtradeMeta() writes) without values, so this
    // stays cheap no matter how large the entries are.
    const warm = new Map();
    let cursor;
    do {
        const page = await env.API_CACHE.list({ prefix: 'comtrade:A:', cursor }).catch(() => null);
        if (!page) break;
        for (const k of page.keys) warm.set(k.name, k.metadata || null);
        cursor = page.list_complete ? null : page.cursor;
    } while (cursor);

    const published = publishedComtradeYear(await readComtradePeriodRecord(env));
    // The year after the published one, while it can exist at all.
    const next = published < comtradeYearBounds().fresh ? published + 1 : null;

    const keyFor = (hs, year) =>
        comtradeCacheKey(hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, String(year), 'A');

    // What visitors are looking at comes first; the next year only gets
    // whatever budget is left over.
    const work = [];
    for (const hs of Object.keys(COMTRADE_TTL)) work.push([hs, published]);
    if (next) for (const hs of Object.keys(COMTRADE_TTL)) work.push([hs, next]);

    let filled = 0, alreadyWarm = 0, failed = 0, deferred = 0;

    // Sequential on purpose: firing these at once risks tripping Comtrade's
    // rate limiting, and the cron run has no deadline pressure.
    for (const [hs, year] of work) {
        const key = keyFor(hs, year);
        if (warm.has(key)) { alreadyWarm++; continue; }
        if (filled >= WARM_FETCH_BUDGET) { deferred++; continue; }

        try {
            const result = await fetchComtrade(env, hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, String(year), 'A');
            if (!result.ok) {
                failed++;
                console.log(`[warm] ${hs}/${year} upstream ${result.status}`);
                continue;
            }
            const metadata = comtradeMeta(result.body);
            await env.API_CACHE.put(key, JSON.stringify(result.body),
                { expirationTtl: result.ttl || COMTRADE_TTL[hs], metadata });
            warm.set(key, metadata);
            filled++;
        } catch (err) {
            failed++;
            console.log(`[warm] ${hs}/${year} error: ${err.message}`);
        }
    }

    console.log(`[warm] ${published} (next ${next ?? '-'}): ${filled} filled, ${alreadyWarm} already warm, ${deferred} deferred, ${failed} failed`);

    if (next) await advanceComtradePeriod(env, warm, keyFor, published, next);
}

/**
 * Read-only progress report for the annual year: the published year, and how
 * many commodities are cached for it and for the next one. Without this the
 * only way to tell "still warming" from "stuck" was the Workers log.
 */
async function handleComtradeStatus(env) {
    const record = await readComtradePeriodRecord(env);
    const published = publishedComtradeYear(record);
    const bounds = comtradeYearBounds();
    const next = published < bounds.fresh ? published + 1 : null;
    const keys = new Map();
    if (env.API_CACHE) {
        let cursor;
        do {
            const page = await env.API_CACHE.list({ prefix: 'comtrade:A:', cursor }).catch(() => null);
            if (!page) break;
            for (const k of page.keys) keys.set(k.name, k.metadata || null);
            cursor = page.list_complete ? null : page.cursor;
        } while (cursor);
    }
    const hsList = Object.keys(COMTRADE_TTL);
    const keyOf = (hs, year) => comtradeCacheKey(hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, String(year), 'A');
    const count = (year) => hsList.filter(hs => keys.has(keyOf(hs, year)) && !keys.get(keyOf(hs, year))?.partial).length;
    const partial = (year) => hsList.filter(hs => keys.get(keyOf(hs, year))?.partial);
    const reporters = (year) => hsList.reduce((sum, hs) => {
        const m = keys.get(comtradeCacheKey(hs, DEFAULT_M49_CODES, DEFAULT_M49_CODES, String(year), 'A'));
        return sum + (Number.isFinite(m?.reporters) ? m.reporters : 0);
    }, 0);
    const body = {
        published: String(published),
        record: record || null,
        floor: String(bounds.floor),
        commodities: hsList.length,
        cached: { [published]: count(published) },
        partial: { [published]: partial(published) },
        reporters: { [published]: reporters(published) },
        next: next ? String(next) : null,
        next_rule: next ? (next > bounds.mature
            ? `all cached and reporters >= ${FRESH_YEAR_MIN_COVERAGE * 100}% of ${published}`
            : 'all cached (complete year)') : null,
    };
    if (next) {
        body.cached[next] = count(next);
        body.partial[next] = partial(next);
        body.reporters[next] = reporters(next);
    }
    return new Response(JSON.stringify(body), { headers: { ...JSON_HEADERS, 'Cache-Control': 'no-store' } });
}

// Move the published year forward by one, if the next year is ready. Ready
// means every commodity for it is already in KV -- so the switch never lands
// visitors on a cold query -- and, for the year that has only just ended,
// that enough reporters have filed (see FRESH_YEAR_MIN_COVERAGE).
async function advanceComtradePeriod(env, warm, keyFor, published, next) {
    const hsList = Object.keys(COMTRADE_TTL);
    // A partial entry (some reporter chunks failed) does not count: promoting
    // on it would publish a year with countries missing from the map.
    const cold = hsList.filter(hs => !warm.has(keyFor(hs, next)) || warm.get(keyFor(hs, next))?.partial);
    if (cold.length) {
        console.log(`[period] ${next} not promoted: ${cold.length}/${hsList.length} commodities not fully cached yet`);
        return;
    }

    let coverage = null;
    if (next > comtradeYearBounds().mature) {
        // Reporter counts come from KV metadata. A published entry written
        // before metadata existed has none; leave that commodity out of both
        // sides rather than count it as zero.
        let have = 0, had = 0;
        for (const hs of hsList) {
            const now = warm.get(keyFor(hs, next));
            const then = warm.get(keyFor(hs, published));
            if (!Number.isFinite(now?.reporters) || !Number.isFinite(then?.reporters)) continue;
            have += now.reporters;
            had += then.reporters;
        }
        if (had === 0) {
            console.log(`[period] ${next} not promoted: no ${published} reporter counts to compare against`);
            return;
        }
        coverage = Math.round((have / had) * 1000) / 1000;
        if (coverage < FRESH_YEAR_MIN_COVERAGE) {
            console.log(`[period] ${next} not promoted: reporter coverage ${coverage} < ${FRESH_YEAR_MIN_COVERAGE} (${have}/${had})`);
            return;
        }
    }

    const record = { period: String(next), previous: String(published), coverage, promotedAt: new Date().toISOString() };
    await env.API_CACHE.put(COMTRADE_PERIOD_KEY, JSON.stringify(record));
    console.log(`[period] promoted ${published} -> ${next}` + (coverage === null ? ' (complete year)' : ` (coverage ${coverage})`));
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

/**
 * Reports published about one commodity in one country.
 *
 * The snapshot stores each report once and indexes ids per window, so the
 * whole file is small enough to serve as-is; this endpoint resolves the ids
 * for the one window the panel is showing, which is what keeps the country
 * card's payload a handful of rows instead of the entire board.
 *
 * ?commodity=soybeans          -> world-level reports for that commodity
 * ?commodity=soybeans&country=USA -> that country's reports, then world ones
 */
async function handleCommodityReports(request, env) {
    const url = new URL(request.url);
    const commodity = (url.searchParams.get('commodity') || '').trim();
    const country = (url.searchParams.get('country') || '').trim().toUpperCase();
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '8', 10) || 8, 30);

    const doc = await loadStaticJson(env, url.origin, 'commodity_reports_v1.json');
    if (!doc) {
        return new Response(
            JSON.stringify({
                error: 'commodity_reports_v1.json missing — run scripts/commodity_reports/build_reports.py build',
                items: [],
            }),
            { status: 404, headers: JSON_HEADERS }
        );
    }

    // No commodity named: hand back the board itself, so a caller can see
    // which windows have anything at all without guessing keys.
    if (!commodity) {
        const windows = {};
        for (const [key, buckets] of Object.entries(doc.index || {})) {
            windows[key] = Object.fromEntries(
                Object.entries(buckets).map(([bucket, ids]) => [bucket, ids.length])
            );
        }
        return jsonWithCache({
            generated_at: doc.generated_at,
            commodity_labels: doc.commodity_labels || {},
            windows,
        });
    }

    const byId = new Map((doc.items || []).map((it) => [it.id, it]));
    const buckets = (doc.index || {})[commodity] || {};
    // Country rows first, then world balance sheets. A WASDE line on world
    // supply belongs on every country's board, but under what was published
    // about that country -- the specific report is the one being looked for.
    const ids = [];
    if (country) for (const id of buckets[country] || []) ids.push(id);
    for (const id of buckets._global || []) if (!ids.includes(id)) ids.push(id);
    if (!country) {
        // World view: after the global reports, fill with whatever else this
        // commodity produced, so a quiet week still shows the board's activity.
        for (const [bucket, rows] of Object.entries(buckets)) {
            if (bucket === '_global') continue;
            for (const id of rows) if (!ids.includes(id)) ids.push(id);
        }
    }

    const items = ids.slice(0, limit).map((id) => byId.get(id)).filter(Boolean);
    return jsonWithCache({
        generated_at: doc.generated_at,
        commodity,
        commodity_label: (doc.commodity_labels || {})[commodity] || commodity,
        country: country || null,
        country_name: country ? (doc.country_names || {})[country] || null : null,
        count: items.length,
        items,
    });
}

/** JSON response with the same edge cache window the other snapshot routes use. */
function jsonWithCache(body, maxAge = 180) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { ...JSON_HEADERS, 'Cache-Control': `public, max-age=${maxAge}` },
    });
}

/**
 * Read a built snapshot out of the deployed assets.
 *
 * Three candidate paths because the asset prefix has differed between the
 * Worker's own routing and the static-server layout, and a snapshot route
 * that 404s on a path change looks exactly like a pipeline that stopped
 * running.
 */
async function loadStaticJson(env, origin, filename) {
    for (const path of [`/public/data/${filename}`, `/data/${filename}`, `public/data/${filename}`]) {
        try {
            const assetUrl = new URL(path.startsWith('/') ? path : `/${path}`, origin);
            const res = await env.ASSETS.fetch(new Request(assetUrl.toString()));
            if (res.ok) return await res.json();
        } catch (_) { /* next candidate */ }
    }
    return null;
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
async function kvCachedJson(env, cacheKey, ttlSeconds, doFetch, metaOf) {
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
            const opts = { expirationTtl: result.ttl || ttlSeconds };
            if (metaOf) opts.metadata = metaOf(result.body);
            await kv.put(cacheKey, json, opts);
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
    "1511": 1209600, // Palm oil: 14 days
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

// Which annual Comtrade year the trade map shows. Not pinned: this was a
// literal "2023" until 2026-09, which left the map a year behind once 2024
// was complete and two behind once 2025 had filled in.
//
// The published year lives in KV under COMTRADE_PERIOD_KEY, and only the cron
// moves it -- one year at a time, and only once every commodity for the next
// year is already cached (advanceComtradePeriod). So a promotion never sends
// visitors to a cold UN Comtrade query.
//
// Annual data fills in over roughly 18 months: the large reporters file
// within a few months of year-end, the long tail much later. A year two or
// more back counts as complete. The year just ended is promoted only once
// its filing reporters reach FRESH_YEAR_MIN_COVERAGE of the year before on
// the same commodities -- a year with a third of the reporters missing would
// read on the map as trade collapsing.
const COMTRADE_PERIOD_KEY = 'comtrade:period:A';
const FRESH_YEAR_MIN_COVERAGE = 0.9;
// Last resort when KV holds no record (first deploy, namespace wiped) or the
// record has fallen this far behind because the cron stopped. Three years
// back is complete for every reporter -- and on the first deploy it is 2023,
// the year the cache is already warm for, so the switch costs visitors nothing
// while the cron walks the map forward.
const COMTRADE_FLOOR_LAG = 3;

function comtradeYearBounds(now = new Date()) {
    const year = now.getUTCFullYear();
    return {
        floor: year - COMTRADE_FLOOR_LAG,
        mature: year - 2, // newest year promoted without a coverage check
        fresh: year - 1   // newest year that can exist at all
    };
}

async function readComtradePeriodRecord(env) {
    if (!env.API_CACHE) return null;
    return env.API_CACHE.get(COMTRADE_PERIOD_KEY, { type: 'json', cacheTtl: 300 }).catch(() => null);
}

function publishedComtradeYear(record, now = new Date()) {
    const { floor, fresh } = comtradeYearBounds(now);
    const y = Number(record && record.period);
    if (!Number.isInteger(y)) return floor;
    return Math.min(Math.max(y, floor), fresh);
}

// Distinct reporters with a non-zero row. Stored as KV metadata next to each
// cached payload so the cron can compare two years' coverage from a key
// listing alone, without re-reading and parsing every body.
function comtradeMeta(body) {
    const reporters = new Set();
    for (const row of (body && body.data) || []) {
        if (row.primaryValue > 0) reporters.add(row.reporterCode);
    }
    return body && body.partial ? { reporters: reporters.size, partial: true } : { reporters: reporters.size };
}

// How long a result with missing reporter chunks is kept (see fetchComtrade).
const COMTRADE_PARTIAL_TTL = 3600;

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
 * Static assets, with HTML -- and unversioned public/data/*.json -- held out
 * of every cache.
 *
 * A deployed update was not reaching visitors: the site was serving
 * `cache-control: public, max-age=0, must-revalidate` for index.html and
 * Cloudflare was still answering `cf-cache-status: HIT`. Reloading the page --
 * or opening a shared portfolio link a second time -- returned the previous
 * build, whose <script src="app.js?v=..."> pointed at the previous bundle. The
 * versioned query strings only bust caches if the HTML naming them is fresh.
 *
 * public/data/*.json (e.g. shipping_capacity_v1.json) has the same exposure:
 * daily bots overwrite it in place at a URL with no version query string, so
 * the same stale-HIT behavior would keep serving yesterday's snapshot under
 * today's already-fresh HTML/JS.
 *
 * So both are `no-store`: they are small, they change on every deploy or
 * daily refresh, and index.html is the one file that decides which version of
 * everything else the browser loads. Fingerprinted assets keep their long
 * cache, which is where caching earns its keep anyway.
 */
async function serveAsset(request, env) {
    const res = await env.ASSETS.fetch(request);
    const type = res.headers.get('content-type') || '';
    const url = new URL(request.url);
    const isVersionlessData = url.pathname.startsWith('/public/data/') && url.pathname.endsWith('.json');
    if (!type.includes('text/html') && !isVersionlessData) return res;

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

// Comtrade rate-limits bursts. The 2026-09-24 probe got a 429 on the tenth
// chunk call in about 35 seconds, and the cron, which fires 8 commodities x 5
// chunks back to back, was being cut off the same way -- after 18 hours only 6
// of the 2024 commodities were cached. Chunks are spaced, and a 429 waits and
// retries instead of ending the commodity.
const COMTRADE_CHUNK_GAP_MS = 1500;
const COMTRADE_429_RETRIES = 2;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchComtradeChunk(env, hs, reporters, partners, period, freq) {
    // freq A = annual (period "2023"), M = monthly (period "202403").
    // X = Exports, M = Imports (mirror data, so non-reporting countries still appear)
    const comtradeUrl = `https://comtradeapi.un.org/data/v1/get/C/${freq}/HS?reporterCode=${reporters}&period=${period}&partnerCode=${partners}&cmdCode=${hs}&flowCode=X,M`;

    let res;
    for (let attempt = 0; ; attempt++) {
        res = await fetch(comtradeUrl, {
            headers: {
                "Ocp-Apim-Subscription-Key": env.COMTRADE_API_KEY,
                "Accept": "application/json"
            }
        });
        if (res.status !== 429 || attempt >= COMTRADE_429_RETRIES) break;
        await res.body?.cancel();
        const after = Number(res.headers.get('Retry-After'));
        const base = Number(env.COMTRADE_RETRY_BASE_MS ?? 4000);
        await sleep(Math.min(Number.isFinite(after) && after > 0 ? after * 1000 : base * (attempt + 1), 15000));
    }

    if (!res.ok) {
        return { ok: false, status: res.status, statusText: res.statusText };
    }
    // Slim immediately so only the five needed fields per row are retained.
    return { ok: true, rows: slimComtradeBody(await res.json()).data };
}

async function fetchComtrade(env, hs, reporters, partners, period, freq) {
    const codes = reporters.split(',').filter(Boolean);
    const merged = [];
    const chunks = Math.ceil(codes.length / REPORTER_CHUNK_SIZE);
    let failed = 0;
    let lastFailure = null;

    try {
        for (let i = 0; i < codes.length; i += REPORTER_CHUNK_SIZE) {
            // env override exists for tests only; production uses the constant.
            if (i > 0) await sleep(Number(env.COMTRADE_CHUNK_GAP_MS ?? COMTRADE_CHUNK_GAP_MS));
            const chunk = codes.slice(i, i + REPORTER_CHUNK_SIZE).join(',');
            const result = await fetchComtradeChunk(env, hs, chunk, partners, period, freq);

            // One bad chunk shouldn't discard the countries that did come back.
            if (!result.ok) {
                failed++;
                lastFailure = result;
                console.log(`[comtrade] ${hs}/${period} chunk ${i} failed: ${result.status}`);
                continue;
            }
            for (const row of result.rows) merged.push(row);
        }
    } catch (err) {
        // Catchable failures (bad JSON, network) surface as a labelled 502
        // rather than an opaque 1101 with an empty map behind it.
        failed = chunks;
        lastFailure = { ok: false, status: 502, statusText: err.message };
        console.log(`[comtrade] ${hs}/${period} error after ${merged.length} rows: ${err.message}`);
    }
    if (merged.length === 0 && failed) return lastFailure;

    // period/freq travel with the rows so a consumer never has to remember
    // what it asked for -- the default year is chosen here, not by the caller.
    const body = { count: merged.length, period, freq, data: merged };
    // Some reporters are missing. Still worth showing, but not worth keeping:
    // cached for the full TTL it would stand in for the complete answer for
    // up to two weeks (zinc 2024 came back with 49 reporters where every
    // neighbour had 57-60). It lives an hour and is refetched.
    if (failed) {
        body.partial = true;
        body.missing_chunks = failed;
        return { ok: true, body, ttl: COMTRADE_PARTIAL_TTL };
    }
    return { ok: true, body };
}

const NUMERIC_LIST = /^\d+(,\d+)*$/;
const PERIOD_SHAPE = { A: /^\d{4}(,\d{4})*$/, M: /^\d{6}(,\d{6})*$/ };

async function handleComtrade(request, env, ctx) {
    const url = new URL(request.url);
    const hs = url.searchParams.get('hs') || '2709';
    const reporters = url.searchParams.get('reporters') || DEFAULT_M49_CODES;
    const partners = url.searchParams.get('partners') || DEFAULT_M49_CODES;
    // freq=M returns monthly rows (period must then look like "202403").
    const freq = url.searchParams.get('freq') === 'M' ? 'M' : 'A';
    const periodParam = url.searchParams.get('period');

    const bad = (error, hint) => new Response(JSON.stringify(hint ? { error, hint } : { error }),
        { status: 400, headers: JSON_HEADERS });

    // Every one of these is spliced into the upstream query string, so
    // anything but digits and commas could append parameters of its own to a
    // request that carries our subscription key.
    if (![hs, reporters, partners].every(v => NUMERIC_LIST.test(v))) {
        return bad("hs, reporters and partners must be comma-separated numeric codes");
    }

    let period;
    if (periodParam && periodParam !== 'latest') {
        if (!PERIOD_SHAPE[freq].test(periodParam)) {
            return bad(`period does not match freq=${freq}`,
                freq === 'M' ? "monthly periods are YYYYMM[,YYYYMM...]" : "annual periods are YYYY[,YYYY...]");
        }
        period = periodParam;
    } else if (freq === 'A') {
        period = String(publishedComtradeYear(await readComtradePeriodRecord(env)));
    } else {
        // Monthly used to fall back to a fixed "202403", which served data two
        // and a half years stale without saying so. There is no latest-month
        // resolver yet; until one exists, the caller has to name the months.
        return bad("period is required when freq=M",
            "Pass YYYYMM[,YYYYMM...]. There is no default month.");
    }

    if (!env.COMTRADE_API_KEY) return missingKey('COMTRADE_API_KEY');

    const cacheTtl = COMTRADE_TTL[hs] || 604800; // Default: weekly

    const res = await kvCachedJson(env, comtradeCacheKey(hs, reporters, partners, period, freq), cacheTtl,
        () => fetchComtrade(env, hs, reporters, partners, period, freq), comtradeMeta);

    // Also in the headers: entries cached before the body carried `period`
    // stay readable until they expire, and a HIT returns them verbatim.
    const headers = new Headers(res.headers);
    headers.set('X-Comtrade-Period', period);
    headers.set('X-Comtrade-Freq', freq);
    headers.set('Access-Control-Expose-Headers', 'X-Comtrade-Period, X-Comtrade-Freq, X-Cache');
    return new Response(res.body, { status: res.status, headers });
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
            // so callers ask for extra rows and take the first real one. The home
            // panel's sparklines read the same rows as a short series, which is
            // why the cap is a few hundred rather than a handful.
            const limitParam = parseInt(url.searchParams.get('limit'), 10);
            const limit = Number.isFinite(limitParam) ? Math.min(Math.max(limitParam, 1), 400) : 1;

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
            // Daily spot prices carry a shorter window for the same reason:
            // the home panel draws a sparkline beside the latest print.
            const length = freq === 'weekly' ? 52 : 30;
            // A weekly series cannot have new data more than once a week, so
            // an hourly cache TTL was doing nothing but multiplying how often
            // this Worker hits EIA's own API -- and each of those live calls
            // is a chance to catch EIA mid-flake (occasional bare 502s from
            // api.eia.gov itself, unrelated to this key). A day-long TTL cuts
            // that exposure ~24x for no loss of freshness. Daily series keep
            // the shorter window since they do change every day.
            const ttlSeconds = freq === 'weekly' ? 86400 : 3600;
            return kvCachedJson(env, `eia:${route}:${seriesId}:${length}`, ttlSeconds, async () => {
                const eiaUrl = `https://api.eia.gov/v2/${route}?api_key=${EIA_KEY}&frequency=${freq}&data[0]=value&facets[series][]=${encodeURIComponent(seriesId)}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=${length}`;
                // EIA's own API occasionally bounces a request with a bare
                // 5xx/network error that succeeds a moment later -- one retry
                // after a short pause absorbs that instead of surfacing a 502
                // to every visitor until the next live fetch happens to land.
                for (let attempt = 0; attempt < 2; attempt++) {
                    try {
                        const res = await fetch(eiaUrl);
                        if (res.ok) return { ok: true, body: await res.json() };
                        if (attempt === 0) { await new Promise((r) => setTimeout(r, 400)); continue; }
                        return { ok: false, status: res.status };
                    } catch (err) {
                        if (attempt === 0) { await new Promise((r) => setTimeout(r, 400)); continue; }
                        return { ok: false, status: 0, statusText: err.message };
                    }
                }
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

            // The chart modal's default view wants 5 years of monthly bars;
            // the home panel's JP/UK 10Y bond tiles want just today's close
            // (range=5d); the stock modal's moving averages want two years of
            // daily bars (range=2y) -- enough trading days for a 240-day
            // average to have visible history rather than a single dot. All
            // three keep hitting this one route rather than duplicating the
            // Yahoo fetch, and each combination gets its own cache entry.
            const interval = url.searchParams.get('interval') || '1mo';
            const rangeParam = url.searchParams.get('range');
            const rangeMatch = /^(\d+)([dy])$/.exec(rangeParam || '');

            return kvCachedJson(env, `yfinance:${symbol}:${interval}:${rangeParam || '5y'}`, 3600, async () => {
                const period2 = Math.floor(Date.now() / 1000);
                let period1;
                if (rangeMatch) {
                    const [, n, unit] = rangeMatch;
                    period1 = unit === 'd'
                        ? period2 - Number(n) * 86400
                        : Math.floor(new Date().setFullYear(new Date().getFullYear() - Number(n)) / 1000);
                } else {
                    period1 = Math.floor(new Date().setFullYear(new Date().getFullYear() - 5) / 1000);
                }
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
// fiscal Q4 to reconstruct (see secQuarterlyFromCalendar). Mirrors DART_FLOW_KEYS.
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

// secQuarterLabel by calendar month of the period end was tried and is wrong:
// verified live on Intel (fiscal Q1 ends early April -> calendar "Q2") and
// would misfire the same way on any non-December fiscal year, AAPL included
// (FY ends late September). Worse than a mislabel -- Intel's fiscal Q3 (10-Q,
// end Oct 1, calendar "Q4") and its fiscal Q4 (10-K, end Dec 31, also calendar
// "Q4") collided under one label, and the later-filed one silently won,
// putting a full year's revenue on a bar marked as one quarter.
//
// Quarters are labelled instead by their ordinal position inside the fiscal
// year that contains them (secFiscalCalendar), which needs no assumption
// about which calendar month a filer's year starts in.

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

// One fiscal-quarter calendar for the whole company: {fy: [q1End, q2End,
// q3End, q4End]}, built once from `calendarBasis` (whichever key's annual
// bounds the caller passes -- normally revenue) and shared by every SEC_TAGS
// key below. Anchoring every key to the same four dates, rather than letting
// each key label its own quarters, is what stops two different tags from
// disagreeing on what "Q3" means.
//
// `anchorNames` restricts the quarter-end dates pooled here to one tag
// family (normally SEC_TAGS.revenue) rather than every SEC_TAGS candidate.
// Pooling everything was tried first and is wrong: verified live on Cisco,
// where a handful of unrelated concepts report period boundaries a day or two
// off from revenue's own, and one stray date shifted an entire fiscal year's
// grouping by one slot -- every quarter sum came out ~$1B short of the
// annual figure, silently, because the derived Q4 absorbed the drift. A
// concept filed less often than revenue simply locates fewer of its own
// four quarters; it does not need a different concept's dates standing in
// for the ones it is missing. Falls back to pooling only when the caller has
// no revenue bounds to anchor to at all (a filer that never reports revenue
// under any of the standard tags).
function secFiscalCalendar(gaap, annualBounds, anchorNames) {
    if (!annualBounds || !annualBounds.size) return null;

    const latestEnd = new Map(); // "start|end" -> {end, filed}
    const tagLists = anchorNames ? [anchorNames] : Object.values(SEC_TAGS);
    for (const names of tagLists) {
        for (const tag of names) {
            const node = gaap[tag];
            if (!node || !node.units) continue;
            const u = Object.keys(node.units)[0];
            for (const p of node.units[u] || []) {
                if (!(p.form === '10-Q' || p.form === '10-K') || !secIsOneQuarter(p)) continue;
                const key = `${p.start}|${p.end}`;
                const prior = latestEnd.get(key);
                if (!prior || String(p.filed) > String(prior.filed)) latestEnd.set(key, { end: p.end, filed: p.filed });
            }
        }
    }
    const ends = [...new Set([...latestEnd.values()].map((r) => r.end))];

    // Group each quarter's end date into the fiscal year whose annual period
    // contains it, order by date, and number 1..3. The fourth quarter is
    // appended rather than searched for -- it is never filed as its own
    // 3-month period, its end date is simply the annual period's own end.
    const calendar = {};
    for (const [fy, b] of annualBounds) {
        if (!b.start || !b.end) continue;
        const inYear = ends.filter((e) => e > b.start && e <= b.end).sort();
        if (inYear.length === 3) calendar[fy] = [...inYear, b.end];
        else if (inYear.length === 4) calendar[fy] = inYear; // filer restated Q4 as its own 3mo period
    }
    return Object.keys(calendar).length ? calendar : null;
}

// Reads one SEC_TAGS key's value at each date in the shared fiscal calendar.
// A flow (isFlow=true, has `start`) is read from a matching 3-month period
// when one is filed, or derived as FY minus the other three quarters when it
// is not -- filling exactly the fiscal Q4 that no filer submits on its own.
// A balance (no `start`, a point-in-time instant) is read directly at the
// date; there is nothing to derive because a balance is not summed across
// quarters -- differencing one would produce the *change* in that balance,
// not the balance itself.
function secQuarterlyFromCalendar(gaap, names, calendar, annualByYear, isFlow) {
    if (!calendar) return null;

    const atEnd = new Map(); // end -> value, latest-filed wins
    for (const tag of names) {
        const node = gaap[tag];
        if (!node || !node.units) continue;
        const u = Object.keys(node.units)[0];
        for (const p of (node.units[u] || []).slice().sort((a, b) => String(a.filed).localeCompare(String(b.filed)))) {
            if (!p.end) continue;
            if (isFlow ? (!p.start || !secIsOneQuarter(p)) : !!p.start) continue;
            atEnd.set(p.end, p.val);
        }
    }
    if (!atEnd.size) return null;

    const byQuarter = new Map();
    for (const [fy, dates] of Object.entries(calendar)) {
        const total = isFlow ? annualByYear?.get(Number(fy)) : null;
        const values = dates.map((d) => atEnd.get(d));
        dates.forEach((end, i) => {
            const label = `${fy}Q${i + 1}`;
            if (Number.isFinite(values[i])) {
                byQuarter.set(label, { value: values[i], end, form: 'filed' });
                return;
            }
            // Only the fourth slot is ever derived, and only when the other
            // three are all present -- two known quarters plus a remainder
            // would silently be a half-year on a bar labelled as one quarter.
            if (isFlow && i === 3 && Number.isFinite(total) && values.slice(0, 3).every(Number.isFinite)) {
                byQuarter.set(label, { value: total - values.slice(0, 3).reduce((a, b) => a + b, 0), end, form: 'derived:FY-9M' });
            }
        });
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
            //
            // One calendar for the whole company, anchored to revenue's own
            // filed quarters (falls back to whatever annual bounds exist, and
            // to pooling every tag, only when a filer has no revenue at all)
            // -- see secFiscalCalendar for why pooling by default corrupted
            // the grouping.
            const calendarBasis = bounds.revenue || Object.values(bounds).find(Boolean);
            const fiscalCalendar = secFiscalCalendar(gaap, calendarBasis, bounds.revenue ? SEC_TAGS.revenue : null);
            const quarterlyByKey = {};
            for (const [key, names] of Object.entries(SEC_TAGS)) {
                const got = secQuarterlyFromCalendar(gaap, names, fiscalCalendar, picked[key], SEC_FLOW_KEYS.has(key));
                if (got) quarterlyByKey[key] = got;
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
    // Denominator for ROA -- the one financial-entity-safe metric this
    // endpoint didn't already carry an input for (net_income and equity, for
    // ROE, were both already fetched above).
    total_assets: ['ifrs-full_Assets'],
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

// Codex's dart_kfa.entity_policy.classify_entity() gates banks/insurers/
// brokerages from industrial revenue, FCF, EBITDA, net-debt and DCF chains
// (see scripts/dart/docs/P0_WORKER_HANDOFF_FINANCIALS.md section 1). That
// classifier runs in Python and isn't reachable from a Worker, so this is a
// narrow JS-side mirror of the same fail-closed decision -- a name/corp-code
// check, not a recomputation of any financial model. Corp codes are the
// explicit KOSPI banks/financial holding companies named in that handoff doc
// plus other well-known listed financials; the name-hint list catches any
// filer this override set misses. Unrecognised filers default to false
// (industrial), matching the classifier's own "명확한 신호가 없으면 산업기업" stance --
// this list is reviewed by name/ticker only, not by live OpenDART account IDs.
const DART_FINANCIAL_ENTITY_OVERRIDES = new Set([
    '105560', // KB금융
    '055550', // 신한지주
    '086790', // 하나금융지주
    '316140', // 우리금융지주
    '032830', // 삼성생명
    '000810', // 삼성화재
    '138930', // BNK금융지주
    '139130', // DGB금융지주
    '175330', // JB금융지주
    '138040', // 메리츠금융지주
    '024110', // 기업은행
    '323410', // 카카오뱅크
    '005830', // DB손해보험
]);
const DART_FINANCIAL_NAME_HINTS = [
    '금융지주', '저축은행', '은행', '생명', '화재', '손해보험', '해상보험',
    '캐피탈', '카드', '증권', '보험',
];
function classifyDartFinancialEntity(nameKo, stockCode) {
    if (DART_FINANCIAL_ENTITY_OVERRIDES.has(stockCode)) {
        return { is_financial_entity: true, basis: 'corp_code_override' };
    }
    const hint = DART_FINANCIAL_NAME_HINTS.find((h) => (nameKo || '').includes(h));
    if (hint) return { is_financial_entity: true, basis: `name_hint:${hint}` };
    return { is_financial_entity: false, basis: 'default_industrial' };
}

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
function dartBasicCardsFromFacts(factsByYear, years, { sharesOutstanding = null, price = null, quarterly = {}, isFinancialEntity = false } = {}) {
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
    // A bank/insurer/brokerage's IFRS "Revenue" (or its absence) is not
    // industrial sales -- gate it to null before anything downstream (yoy,
    // margins, the quarterly attach loop below) reads its value or series.
    // See scripts/dart/docs/P0_WORKER_HANDOFF_FINANCIALS.md section 1.
    if (isFinancialEntity) {
        revenue.value = null;
        revenue.series = [];
        revenue.reason = 'not_applicable:financial_entity_industrial_revenue';
    }
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

    // FCF (and net debt, below) is an industrial leverage/cash-generation
    // frame that doesn't apply to a bank/insurer's balance sheet -- gated for
    // the same reason as revenue above, not computed and then hidden.
    let fcf;
    if (isFinancialEntity) {
        fcf = { value: null, definition: 'cfo - abs(capex)', series: [], reason: 'not_applicable:financial_entity' };
    } else {
        const capexV = capex.value, cfoV = cfo.value;
        const fcfValue = (cfoV !== null && capexV !== null) ? cfoV - Math.abs(capexV) : null;
        const fcfSeries = years
            .map((y) => {
                const c = valueIn(y, 'cfo'), cx = valueIn(y, 'capex');
                return (c !== null && cx !== null) ? { year: y, end: `${y}-12-31`, value: c - Math.abs(cx) } : null;
            })
            .filter(Boolean)
            .sort((a, b) => a.year - b.year);
        fcf = { value: fcfValue, definition: 'cfo - abs(capex)', series: fcfSeries };
        if (fcfValue === null) fcf.reason = 'missing:cfo_or_capex';
    }

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
    if (isFinancialEntity) {
        netDebt = { value: null, series: [], reason: 'not_applicable:financial_entity' };
    } else if ((shortTerm !== null || longTerm !== null) && cashV !== null) {
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

    // ROE/ROA are the metrics the entity policy asks to keep for financial
    // entities in place of FCF/EBITDA/net-debt -- computed for every filer,
    // not just gated ones, since they're informative for industrials too.
    const totalAssetsV = dartPick(latestFacts, DART_XBRL_TAGS.total_assets);
    const roe = (niV !== null && equityV) ? { value: niV / equityV, series: [], definition: 'net_income / equity' }
        : { value: null, series: [], reason: niV === null ? 'missing:net_income' : 'missing:equity' };
    const roa = (niV !== null && totalAssetsV) ? { value: niV / totalAssetsV, series: [], definition: 'net_income / total_assets' }
        : { value: null, series: [], reason: niV === null ? 'missing:net_income' : 'missing:total_assets' };

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
        roe, roa,
    };

    // Attached rather than merged into `series`: annual and quarterly points
    // cover different spans, so one array holding both would be summable into
    // nonsense. The UI toggles between them. revenue/fcf are skipped for a
    // gated financial entity -- a populated quarterly array would contradict
    // the card's own null+not_applicable annual value.
    for (const [key, points] of Object.entries(quarterly)) {
        if (isFinancialEntity && (key === 'revenue' || key === 'fcf')) continue;
        if (cards[key]) cards[key].quarterly = points;
    }
    // FCF has no XBRL tag of its own -- it is cfo - |capex| at every period,
    // so its quarterly series is derived the same way its annual one is.
    const qCfo = isFinancialEntity ? [] : (quarterly.cfo || []);
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
                'interest_coverage', 'ccc_days', 'market_cap', 'pe_ratio', 'pb_ratio', 'roe', 'roa'],
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
            const entityPolicy = classifyDartFinancialEntity(nameKo, symbol);

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
                    // Mirrors dart_kfa.entity_policy's classify_entity() output shape
                    // (see scripts/dart/docs/P0_WORKER_HANDOFF_FINANCIALS.md) so the
                    // static-snapshot and live-fetch paths carry the same field.
                    entity_policy: entityPolicy,
                    basic_cards: dartBasicCardsFromFacts(factsByYear, years, {
                        sharesOutstanding: sharesResult.sharesOutstanding,
                        price: priceResult.price,
                        quarterly,
                        isFinancialEntity: entityPolicy.is_financial_entity,
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
    palm_oil: "기준 계약인 Bursa Malaysia 원유 팜유 선물(FCPO) 시세는 무료로 제공되지 않습니다",
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

// --- US policy: Supabase-backed read API ------------------------------------
//
// schema.sql enables row level security on every policy table and defines *no*
// policies, so the anon/publishable key can read nothing at all -- PostgREST
// answers it with an empty array, not an error. Reads therefore have to run
// server-side under the service role, which is exactly what this Worker is for.
// SUPABASE_SERVICE_ROLE_KEY must be a Worker secret (`wrangler secret put`) and
// must never be echoed into a response body, a log line, or the asset bundle.
//
// Contract: docs/api-spec.md section 5. Only the paths the policy screens
// actually drill into are implemented here; public-laws and U.S. Code are in
// the spec but nothing navigates to them yet.

const SUPABASE_LIST_LIMIT = 50;
const SUPABASE_LIST_LIMIT_MAX = 200;

// Mirrors bills.current_stage / bill_actions.normalized_stage in schema.sql.
// Anything a visitor sends that is not on this list is dropped rather than
// forwarded, so no caller-supplied text ever reaches a PostgREST filter.
const BILL_STAGES = new Set([
    'introduced', 'referred', 'subcommittee', 'committee_consideration',
    'reported', 'passed_origin_chamber', 'second_chamber',
    'resolving_differences', 'passed_both_chambers', 'presented_to_president',
    'enacted', 'vetoed', 'failed', 'other',
]);

// Cache lifetimes. The directory screens (committee/agency/CRS/CFR tiles) change
// only when a sync run adds a body, so they can sit for an hour; lists and
// details move with each run and are kept short enough that a backfill batch
// shows up while it is still running.
const US_TTL = { overview: 3600, list: 600, detail: 1800, search: 300 };

async function handleUsPolicy(request, env) {
    if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
        return missingKey('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY');
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/api\/us\/?/, '').replace(/\/+$/, '');
    const q = url.searchParams;

    try {
        if (path === 'overview') {
            return await kvCachedJson(env, 'us:overview:v2', US_TTL.overview,
                () => usOverview(env));
        }

        // Ops-facing: "how much of each source has been pulled in so far",
        // not a screen the UI links to. Short TTL so a backfill in progress
        // shows up quickly on a re-check instead of the full overview hour.
        if (path === 'coverage') {
            return await kvCachedJson(env, 'us:coverage:v1', US_TTL.list,
                () => usCoverage(env));
        }

        if (path === 'congress/bills') {
            const filter = usBillFilter(q);
            return await kvCachedJson(env, `us:bills:v2:${filter.cacheKey}`, US_TTL.list,
                () => usBillList(env, filter));
        }

        let m = path.match(/^congress\/bills\/(.+)$/);
        if (m) {
            const billId = decodeURIComponent(m[1]);
            return await kvCachedJson(env, `us:bill:v3:${billId}`, US_TTL.detail,
                () => usBillDetail(env, billId));
        }

        if (path === 'executive/orders') {
            const filter = usEoFilter(q);
            return await kvCachedJson(env, `us:eos:v1:${filter.cacheKey}`, US_TTL.list,
                () => usEoList(env, filter));
        }

        m = path.match(/^executive\/orders\/(\d+)$/);
        if (m) {
            return await kvCachedJson(env, `us:eo:v1:${m[1]}`, US_TTL.detail,
                () => usEoDetail(env, Number(m[1])));
        }

        if (path === 'executive/regulations') {
            const filter = usRegulationFilter(q);
            return await kvCachedJson(env, `us:regs:v1:${filter.cacheKey}`, US_TTL.list,
                () => usRegulationList(env, filter));
        }

        if (path === 'congress/committees') {
            const id = q.get('committee_id');
            if (!id) return usError('committee_id is required', 400);
            return await kvCachedJson(env, `us:committee:v2:${id}`, US_TTL.detail,
                () => usCommitteeDetail(env, id));
        }

        if (path === 'executive/agencies') {
            const id = q.get('agency_id');
            if (!id) return usError('agency_id is required', 400);
            return await kvCachedJson(env, `us:agency:v1:${id}`, US_TTL.detail,
                () => usAgencyDetail(env, id));
        }

        m = path.match(/^executive\/cfr-titles\/(\d{1,2})$/);
        if (m) {
            return await kvCachedJson(env, `us:cfr:v1:${m[1]}`, US_TTL.detail,
                () => usCfrTitleDetail(env, Number(m[1])));
        }

        if (path === 'search') {
            const filter = usSearchFilter(q);
            if (!filter.query) return new Response(JSON.stringify({ query: '', items: [] }), { headers: JSON_HEADERS });
            if (!filter.billRef && !hasPolicyEmbeddingProvider(env)) return missingKey('POLICY_EMBEDDING_PROXY_URL/POLICY_EMBEDDING_PROXY_TOKEN');
            return await kvCachedJson(env, `us:search:v3:${filter.cacheKey}`, US_TTL.search,
                () => usSearch(env, filter));
        }

        return usError(`Unknown endpoint: ${url.pathname}`, 404);
    } catch (err) {
        // usFetch already stripped the upstream body of anything sensitive; the
        // message here is our own text plus a PostgREST status.
        console.log(`[us] ${url.pathname} failed: ${err.message}`);
        // 검색어와 상류 서비스의 오류 전문은 방문자에게 노출하지 않는다. 특히
        // Gemini의 지역 제한 같은 운영 정보는 Worker 로그에서만 확인한다.
        if (path === 'search') return usError('검색 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.', 503);
        return usError(err.message, err.status || 502);
    }
}

function usError(message, status) {
    return new Response(JSON.stringify({ error: message }), { status, headers: JSON_HEADERS });
}

// kvCachedJson turns every `ok: false` into a 502 "upstream error", which is the
// wrong answer for a row that simply is not in the table yet -- and during the
// backfill most rows are not. Throwing instead lets handleUsPolicy answer 404,
// and nothing gets cached.
function usNotFound(what) {
    const err = new Error(`${what} not found`);
    err.status = 404;
    return err;
}

// A single PostgREST GET. `query` is built entirely from code in this file plus
// values that have been whitelisted or encoded -- never a raw query string
// forwarded from the visitor.
async function usFetch(env, table, query, { count } = {}) {
    const base = env.SUPABASE_URL.replace(/\/+$/, '');
    const headers = {
        apikey: env.SUPABASE_SERVICE_ROLE_KEY,
        ...(String(env.SUPABASE_SERVICE_ROLE_KEY).startsWith('eyJ') ? { Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}` } : {}),
        Accept: 'application/json',
    };
    if (count) headers.Prefer = `count=${count}`;

    const res = await fetch(`${base}/rest/v1/${table}?${query}`, { headers });
    if (!res.ok) {
        const detail = await res.text().catch(() => '');
        // PostgREST error bodies name the table and the constraint, which is
        // useful and safe; they never carry the key. Trim so a stack of them
        // cannot blow past a log line.
        throw new Error(`Supabase ${table}: HTTP ${res.status} ${detail.slice(0, 300)}`);
    }
    const rows = await res.json();
    if (!count) return rows;

    // Content-Range is "0-24/1234" (or "*/1234" for an empty page).
    const total = Number((res.headers.get('content-range') || '').split('/')[1]);
    return { rows, total: Number.isFinite(total) ? total : null };
}

// A single PostgREST RPC call (POST /rest/v1/rpc/<name>). A 404 here means the
// function itself is not deployed yet -- distinguished from other failures so
// the caller can degrade to "search not ready" instead of a hard 502.
async function usRpc(env, name, args) {
    const base = env.SUPABASE_URL.replace(/\/+$/, '');
    const res = await fetch(`${base}/rest/v1/rpc/${name}`, {
        method: 'POST',
        headers: {
            apikey: env.SUPABASE_SERVICE_ROLE_KEY,
            ...(String(env.SUPABASE_SERVICE_ROLE_KEY).startsWith('eyJ') ? { Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}` } : {}),
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify(args),
    });
    if (!res.ok) {
        const detail = await res.text().catch(() => '');
        const err = new Error(`Supabase rpc ${name}: HTTP ${res.status} ${detail.slice(0, 300)}`);
        err.status = res.status === 404 ? 503 : 502;
        throw err;
    }
    return res.json();
}

const GEMINI_EMBEDDING_MODEL = 'gemini-embedding-001';
const GEMINI_EMBEDDING_DIMENSIONS = 1536;

function hasPolicyEmbeddingProvider(env) {
    // 운영에서는 미국 리전 Cloud Run 프록시를 사용한다. 직접 Gemini 호출은
    // 로컬 개발 호환성을 위해서만 남겨 둔다.
    return Boolean(
        (env.POLICY_EMBEDDING_PROXY_URL && env.POLICY_EMBEDDING_PROXY_TOKEN)
        || env.AI_STUDIO_API_KEY,
    );
}

function normalizeEmbedding(values, provider) {
    if (!Array.isArray(values) || values.length !== GEMINI_EMBEDDING_DIMENSIONS) {
        throw new Error(`${provider}: expected ${GEMINI_EMBEDDING_DIMENSIONS} dimensions, received ${values?.length || 0}`);
    }
    if (!values.every((v) => Number.isFinite(v))) throw new Error(`${provider}: vector contains non-finite values`);
    const magnitude = Math.sqrt(values.reduce((sum, v) => sum + v * v, 0));
    if (!magnitude) throw new Error(`${provider}: zero-length vector`);
    return values.map((v) => v / magnitude);
}

async function proxyEmbedQuery(env, text) {
    const res = await fetch(`${String(env.POLICY_EMBEDDING_PROXY_URL).replace(/\/+$/, '')}/embed`, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${env.POLICY_EMBEDDING_PROXY_TOKEN}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: String(text).trim().slice(0, 2000) }),
    });
    if (!res.ok) throw new Error(`Policy embedding proxy: HTTP ${res.status}`);
    const body = await res.json();
    return normalizeEmbedding(body?.values, 'Policy embedding proxy');
}

// Same model/dimensionality scripts/lib/sync-utils.js uses to embed bills, EOs
// and regulations at sync time -- a query embedded any other way would land in
// a different vector space and every cosine comparison downstream would be
// meaningless. RETRIEVAL_QUERY (vs. the documents' RETRIEVAL_DOCUMENT) is
// Gemini's intended asymmetric pairing for this exact search-a-corpus case.
async function geminiEmbedQuery(env, text) {
    if (env.POLICY_EMBEDDING_PROXY_URL && env.POLICY_EMBEDDING_PROXY_TOKEN) {
        return proxyEmbedQuery(env, text);
    }
    const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBEDDING_MODEL}:embedContent`,
        {
            method: 'POST',
            headers: { 'x-goog-api-key': env.AI_STUDIO_API_KEY, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: `models/${GEMINI_EMBEDDING_MODEL}`,
                content: { parts: [{ text: String(text).trim().slice(0, 2000) }] },
                taskType: 'RETRIEVAL_QUERY',
                outputDimensionality: GEMINI_EMBEDDING_DIMENSIONS,
            }),
        },
    );
    if (!res.ok) {
        throw new Error(`Gemini embedContent: HTTP ${res.status}`);
    }
    const body = await res.json();
    return normalizeEmbedding(body?.embedding?.values, 'Gemini embedContent');
}

function usSearchFilter(q) {
    const query = (q.get('q') || '').trim().slice(0, 200);
    const limit = Math.min(Math.max(Number(q.get('limit')) || 20, 1), 50);
    const billRef = PolicyEvidence.parseBillQuery(query);
    return { query, limit, billRef, cacheKey: `${query}|${limit}` };
}

// search_policy_corpus는 세 정책 테이블을 한 번에 검색하는 Supabase RPC다.
// 아직 마이그레이션되지 않은 환경에서는 빈 결과와 unavailable 표시로 완화한다.
async function usSearch(env, f) {
    if (f.billRef) {
        const ref = f.billRef;
        const query = new URLSearchParams({ select: 'bill_id,title,congress_number,bill_type,bill_number,congress_url,current_stage,origin_chamber,law_type,law_number,latest_action_date',
            bill_type: `eq.${ref.type}`, bill_number: `eq.${ref.number}`, order: 'congress_number.desc', limit: String(f.limit) });
        if (ref.congress) query.set('congress_number', `eq.${ref.congress}`);
        const rows = await usFetch(env, 'bills', query.toString());
        return { ok: true, body: { query: f.query, search_mode: 'bill_number', items: rows.map(r => ({
            type: 'bill', id: r.bill_id, title: r.title, congress_number: r.congress_number,
            bill_type: r.bill_type, bill_number: r.bill_number, current_stage: r.current_stage, origin_chamber: r.origin_chamber,
            law_type: r.law_type, law_number: r.law_number, latest_action_date: r.latest_action_date, match_type: 'exact_bill_number', source_url: PolicyEvidence.billUrl(r.congress_number, r.bill_type, r.bill_number) || r.congress_url,
        })) } };
    }
    const vector = await geminiEmbedQuery(env, f.query);
    let rows;
    try {
        rows = await usRpc(env, 'search_policy_corpus', {
            p_query_embedding: vector,
            p_embedding_model: GEMINI_EMBEDDING_MODEL,
            p_result_limit: f.limit,
        });
    } catch (err) {
        if (err.status === 503) return { ok: true, body: { query: f.query, items: [], unavailable: true } };
        throw err;
    }
    // Regulations have no drill-down screen of their own (they only ever show
    // up nested under an EO or a CFR title), so a regulation search hit needs
    // its official URL fetched separately -- bills and EOs already have an
    // internal detail view the result row can just navigate to.
    const regulationIds = [...new Set((rows || [])
        .filter((r) => r.source_type === 'regulation')
        .map((r) => r.source_id))];
    const regulationUrls = new Map();
    if (regulationIds.length) {
        const regRows = await usFetch(env, 'regulations',
            `select=regulation_id,federal_register_url&regulation_id=in.(${regulationIds.map((id) => encodeURIComponent(id)).join(',')})`);
        for (const reg of regRows) regulationUrls.set(reg.regulation_id, reg.federal_register_url);
    }
    // search_policy_corpus (Supabase RPC, owned separately -- see
    // supabase/migrations/20260902_policy_corpus_semantic_search.sql) only
    // returns source_type/source_id/title/similarity_score: a 'bill' hit
    // carries no signal for whether it's already a law or still moving
    // through Congress. The policy UI groups results into enacted/pending
    // blocks, so that needs law_number/current_stage -- fetched the same way
    // regulationUrls is above, a follow-up lookup keyed by the RPC's own
    // result ids rather than a change to the RPC itself.
    const billIds = [...new Set((rows || [])
        .filter((r) => r.source_type === 'bill')
        .map((r) => r.source_id))];
    const billMeta = new Map();
    if (billIds.length) {
        const billRows = await usFetch(env, 'bills',
            `select=bill_id,congress_number,bill_type,bill_number,origin_chamber,current_stage,law_type,law_number,latest_action_date`
            + `&bill_id=in.(${billIds.map((id) => encodeURIComponent(id)).join(',')})`);
        for (const b of billRows) billMeta.set(b.bill_id, b);
    }
    const items = (rows || []).map((r) => {
        const bill = r.source_type === 'bill' ? billMeta.get(r.source_id) : null;
        return {
            type: r.source_type,
            id: r.source_id,
            title: r.title,
            similarity_score: r.similarity_score,
            source_url: r.source_type === 'regulation' ? (regulationUrls.get(r.source_id) || null) : undefined,
            ...(bill ? {
                congress_number: bill.congress_number,
                bill_type: bill.bill_type,
                bill_number: bill.bill_number,
                origin_chamber: bill.origin_chamber,
                current_stage: bill.current_stage,
                law_type: bill.law_type,
                law_number: bill.law_number,
                latest_action_date: bill.latest_action_date,
            } : {}),
        };
    });
    return { ok: true, body: { query: f.query, items } };
}

// The obvious way to write this is a PostgREST group-by aggregate
// (`select=<col>,count()`), but that needs db-aggregates-enabled, which this
// project has off -- confirmed by /api/us/coverage coming back with every
// grouped field null while the plain totals worked fine. So this pages
// through the one column instead and tallies client-side; even the largest
// table here (bills, ~18k rows) is a handful of requests of a single short
// column each. Not worth failing a whole directory screen over a badge
// number, so a rejection still degrades to "no counts" rather than an error.
async function usCountBy(env, table, column, extra = '') {
    try {
        const out = {};
        const pageSize = 1000;
        let offset = 0;
        let total = Infinity;
        while (offset < total) {
            const query = `select=${column}${extra}&limit=${pageSize}&offset=${offset}`;
            const { rows, total: reportedTotal } = await usFetch(env, table, query, { count: 'exact' });
            total = Number.isFinite(reportedTotal) ? reportedTotal : offset + rows.length;
            for (const row of rows) {
                const key = row[column];
                if (key == null) continue;
                out[key] = (out[key] || 0) + 1;
            }
            if (rows.length < pageSize) break;
            offset += pageSize;
        }
        return out;
    } catch (err) {
        console.log(`[us] count by ${table}.${column} unavailable: ${err.message}`);
        return null;
    }
}

const countOf = (map, key) => (map ? (map[key] || 0) : null);

// Total row count for a table (optionally filtered), degrading to null the
// same way usCountBy does rather than failing the whole coverage screen.
async function usCountScalar(env, table, filter = '') {
    try {
        const query = ['select=*', filter, 'limit=1'].filter(Boolean).join('&');
        const { total } = await usFetch(env, table, query, { count: 'exact' });
        return total;
    } catch (err) {
        console.log(`[us] count of ${table} unavailable: ${err.message}`);
        return null;
    }
}

// How much of each source has actually been pulled in -- separate from
// usOverview's per-tile badges, this is the one place that answers "how far
// along is the backfill" without anyone needing direct SQL access. Every
// number here is a plain row count, nothing inferred.
async function usCoverage(env) {
    const [
        billsTotal, billsByStage, billsEmbedded,
        eoTotal, eoEmbedded, eoAgencyRelationsByType,
        publicLawsTotal,
        regulationsTotal, regulationsEmbedded,
        committeeMembersCurrentByRole, committeeMembersCurrentTotal,
        legislatorsTotal, committeesTotal,
    ] = await Promise.all([
        usCountScalar(env, 'bills'),
        usCountBy(env, 'bills', 'current_stage'),
        usCountScalar(env, 'bills', 'embedding=not.is.null'),
        usCountScalar(env, 'executive_orders'),
        usCountScalar(env, 'executive_orders', 'embedding=not.is.null'),
        usCountBy(env, 'executive_order_agencies', 'relationship_type'),
        usCountScalar(env, 'public_laws'),
        usCountScalar(env, 'regulations'),
        usCountScalar(env, 'regulations', 'embedding=not.is.null'),
        usCountBy(env, 'committee_members', 'role', '&current=is.true'),
        usCountScalar(env, 'committee_members', 'current=is.true'),
        usCountScalar(env, 'us_legislators'),
        usCountScalar(env, 'committees'),
    ]);
    return {
        ok: true,
        body: {
            generated_at: new Date().toISOString(),
            bills: { total: billsTotal, by_stage: billsByStage, embedded: billsEmbedded },
            executive_orders: { total: eoTotal, embedded: eoEmbedded, agency_relations_by_type: eoAgencyRelationsByType },
            public_laws: { total: publicLawsTotal },
            regulations: { total: regulationsTotal, embedded: regulationsEmbedded },
            committees: { total: committeesTotal },
            committee_members: { current_total: committeeMembersCurrentTotal, current_by_role: committeeMembersCurrentByRole },
            legislators: { total: legislatorsTotal },
        },
    };
}

// Directory payload behind the 미국 → 의회 / 행정부 screens: every tile the two
// grids draw, plus the CRS and CFR classification lists. One response because
// the screens are one screen -- eight round trips to Supabase collapse into a
// single hourly KV entry shared by every visitor.
async function usOverview(env) {
    const [
        committees, agencies, policyAreas, cfrTitles,
        billsPerArea, eosPerAgency, regsPerTitle,
        committeeAgencyRows,
    ] = await Promise.all([
        // Top-level bodies only. Subcommittees belong to the committee screen,
        // and mixing them into the grid would bury the standing committees.
        // committee_directory (docs/policy-jec-crs-handoff-20260921.md) reads
        // as `committees` but collapses a committee's alias codes (JEC's
        // three source ids) into one row, with canonical_bill_count already
        // deduplicated across them and source_committee_ids listing every
        // code that row stands in for -- both needed below.
        usFetch(env, 'committee_directory',
            'select=committee_id,name,chamber,committee_type,official_url,jurisdiction_summary,display_order,'
            + 'canonical_bill_count,source_committee_ids'
            + '&parent_committee_id=is.null&order=chamber.asc,name.asc&limit=500'),
        usFetch(env, 'agencies',
            'select=agency_id,name,short_name,agency_type,parent_agency_id,agency_url'
            + '&agency_type=in.(eop,department,independent)&order=name.asc&limit=1000'),
        usFetch(env, 'policy_areas',
            'select=policy_area_id,name&active=is.true&order=name.asc&limit=200'),
        usFetch(env, 'cfr_titles',
            'select=title_number,title_name,reserved&order=title_number.asc&limit=50'),
        usCountBy(env, 'bills', 'policy_area_id'),
        usCountBy(env, 'executive_order_agencies', 'agency_id'),
        usCountBy(env, 'regulation_cfr_references', 'title_number'),
        // committee_agency_jurisdictions only carries the FK id; the name a
        // committee card wants to show comes from the joined agencies row.
        // Degrades to "no agency tags" the same way usCountBy does, rather
        // than failing the whole directory screen.
        usFetch(env, 'committee_agency_jurisdictions', 'select=committee_id,agencies(name)&limit=5000')
            .catch((err) => { console.log(`[us] committee agency mapping unavailable: ${err.message}`); return []; }),
    ]);

    const agencyNamesByCommittee = new Map();
    for (const row of committeeAgencyRows) {
        const name = row.agencies?.name;
        if (!name) continue;
        const list = agencyNamesByCommittee.get(row.committee_id);
        if (list) list.push(name); else agencyNamesByCommittee.set(row.committee_id, [name]);
    }
    // A jurisdiction row could be filed under any of a committee's alias
    // codes, not just its canonical one, so this checks every code the
    // canonical row stands in for and dedupes across them.
    const agenciesFor = (c) => {
        const names = new Set();
        for (const sourceId of c.source_committee_ids?.length ? c.source_committee_ids : [c.committee_id]) {
            for (const name of agencyNamesByCommittee.get(sourceId) || []) names.add(name);
        }
        return [...names];
    };

    return {
        ok: true,
        body: {
            generated_at: new Date().toISOString(),
            congress_overview: {
                committees: committees.map((c) => ({
                    committee_id: c.committee_id,
                    name: c.name,
                    chamber: c.chamber,
                    committee_type: c.committee_type,
                    official_url: c.official_url,
                    jurisdiction_summary: c.jurisdiction_summary,
                    bill_count: c.canonical_bill_count ?? 0,
                    agencies: agenciesFor(c),
                })),
            },
            executive_overview: {
                agencies: agencies.map((a) => ({
                    agency_id: a.agency_id,
                    name: a.name,
                    short_name: a.short_name,
                    agency_type: a.agency_type,
                    parent_agency_id: a.parent_agency_id,
                    agency_url: a.agency_url,
                    executive_order_count: countOf(eosPerAgency, a.agency_id),
                })),
            },
            policy_areas: policyAreas.map((p) => ({
                policy_area_id: p.policy_area_id,
                name: p.name,
                bill_count: countOf(billsPerArea, p.policy_area_id),
            })),
            cfr_titles: cfrTitles.map((t) => ({
                title_number: t.title_number,
                name: t.title_name,
                reserved: t.reserved,
                regulation_count: countOf(regsPerTitle, String(t.title_number)),
            })),
        },
    };
}

// Offset paging rather than the keyset cursor api-spec.md recommends. Both
// order keys (latest_action_date, introduced_date) are nullable, and a keyset
// predicate over a nullable column needs a three-branch `or=(...)` that
// PostgREST cannot index-scan anyway. The envelope is the contract's, so the
// cursor stays opaque to the caller and can become a keyset token later without
// touching the frontend.
function pageParams(q) {
    const limit = Math.min(Math.max(Number(q.get('limit')) || SUPABASE_LIST_LIMIT, 1), SUPABASE_LIST_LIMIT_MAX);
    const cursor = q.get('cursor') || '';
    const offset = /^o:\d+$/.test(cursor) ? Number(cursor.slice(2)) : 0;
    return { limit, offset };
}

function pageEnvelope(items, { limit, offset }, total) {
    const hasMore = total === null ? items.length === limit : offset + items.length < total;
    return {
        items,
        total,
        next_cursor: hasMore ? `o:${offset + items.length}` : null,
        has_more: hasMore,
    };
}

function usBillFilter(q) {
    const committeeId = q.get('committee_id') || '';
    const policyAreaId = q.get('policy_area_id') || '';
    const stages = (q.get('stage') || '').split(',').map((s) => s.trim()).filter((s) => BILL_STAGES.has(s));
    const congress = /^\d{1,3}$/.test(q.get('congress_number') || '') ? q.get('congress_number') : '';
    const page = pageParams(q);
    return {
        committeeId, policyAreaId, stages, congress, ...page,
        cacheKey: [committeeId, policyAreaId, stages.join('+'), congress, page.limit, page.offset].join('|'),
    };
}

const BILL_LIST_COLUMNS = 'bill_id,congress_number,bill_type,bill_number,title,sponsor,'
    + 'introduced_date,current_stage,current_status,latest_action_date,latest_action_text,'
    + 'congress_url,policy_area_id,detail_level';

// A committee_id can be a JEC alias (jhje00/jsec00 -- see
// docs/policy-jec-crs-handoff-20260921.md) whose bills are filed under any
// of its three source codes. committee_identity resolves whichever id was
// requested to its canonical form; committee_directory's source_committee_ids
// then gives every code a bill list for that committee needs to search
// across. A non-aliased committee resolves to itself as a one-element array,
// so this is the same query shape for every committee, not a JEC special case.
async function resolveCommitteeSourceIds(env, committeeId) {
    const identityRows = await usFetch(env, 'committee_identity',
        `select=canonical_committee_id&source_committee_id=eq.${encodeURIComponent(committeeId)}&limit=1`);
    const canonicalId = identityRows[0]?.canonical_committee_id || committeeId;
    const dirRows = await usFetch(env, 'committee_directory',
        `select=source_committee_ids&committee_id=eq.${encodeURIComponent(canonicalId)}&limit=1`);
    const sourceIds = dirRows[0]?.source_committee_ids;
    return { canonicalId, sourceIds: sourceIds?.length ? sourceIds : [canonicalId] };
}

function usBillWhere(f) {
    const parts = [];
    // !inner turns the embed into a join filter, so this narrows bills rather
    // than merely attaching an empty bill_committees array to every row.
    if (f.committeeIds?.length === 1) parts.push(`bill_committees.committee_id=eq.${encodeURIComponent(f.committeeIds[0])}`);
    else if (f.committeeIds?.length) parts.push(`bill_committees.committee_id=in.(${f.committeeIds.map(encodeURIComponent).join(',')})`);
    if (f.policyAreaId) parts.push(`policy_area_id=eq.${encodeURIComponent(f.policyAreaId)}`);
    if (f.stages.length) parts.push(`current_stage=in.(${f.stages.join(',')})`);
    if (f.congress) parts.push(`congress_number=eq.${f.congress}`);
    return parts.join('&');
}

async function usBillList(env, f) {
    const committeeIds = f.committeeId ? (await resolveCommitteeSourceIds(env, f.committeeId)).sourceIds : null;
    const fIds = { ...f, committeeIds };
    const embed = committeeIds ? ',bill_committees!inner(committee_id)' : '';
    const where = usBillWhere(fIds);
    const query = [
        `select=${BILL_LIST_COLUMNS}${embed}`,
        where,
        'order=latest_action_date.desc.nullslast,introduced_date.desc.nullslast,bill_id.desc',
        `limit=${f.limit}`,
        `offset=${f.offset}`,
    ].filter(Boolean).join('&');

    // Stage counts drive the tab badges and must ignore the stage filter itself,
    // otherwise every tab would report only its own total.
    const stageQuery = [
        `select=current_stage,count()${committeeIds ? ',bill_committees!inner(committee_id)' : ''}`,
        usBillWhere({ ...fIds, stages: [] }),
    ].filter(Boolean).join('&');

    const [page, stageRows] = await Promise.all([
        usFetch(env, 'bills', query, { count: 'exact' }),
        usFetch(env, 'bills', stageQuery).catch(() => null),
    ]);

    const stageCounts = {};
    for (const row of stageRows || []) stageCounts[row.current_stage] = Number(row.count) || 0;

    return {
        ok: true,
        body: {
            filter: {
                type: f.committeeId ? 'committee' : f.policyAreaId ? 'policy_area' : 'all',
                id: f.committeeId || f.policyAreaId || null,
            },
            stage_counts: stageRows ? stageCounts : null,
            ...pageEnvelope(page.rows, f, page.total),
        },
    };
}

// bill_relations has no title column of its own -- a target that is not in
// our DB yet (target_bill_id null) carries only congress/type/number, and one
// that is carries a bill row to join for its title. Both branches assemble
// the same bill_id format the rest of the UI uses ("119-hr-1234").
function shapeRelations(rows, wantSemantic) {
    return rows
        .filter((r) => (r.relation_origin === 'semantic') === wantSemantic)
        .map((r) => ({
            bill_id: r.target_bill_id || `${r.target_congress_number}-${r.target_bill_type}-${r.target_bill_number}`,
            title: r.bills?.title || null,
            relation_type: r.relation_type,
            relation_origin: r.relation_origin,
            ...(wantSemantic ? { similarity_score: r.similarity_score } : {}),
        }));
}

async function usBillDetail(env, billId) {
    const id = encodeURIComponent(billId);
    const [rows, relations] = await Promise.all([
        usFetch(env, 'bills',
            `select=*,policy_areas(policy_area_id,name),`
            + `bill_summaries(action_date,action_description,version_code,summary_text),`
            + `bill_actions(bill_action_id,action_date,action_text,action_code,action_type,chamber,normalized_stage,source_url),`
            + `bill_votes(vote_id,chamber,vote_date,question,result,yea_count,nay_count,present_count,not_voting_count,source_url),`
            + `bill_text_versions(version_code,version_name,issued_on,html_url,pdf_url,formatted_text_url,source_url),`
            + `bill_committees(committee_id,activity_names,first_referred_at,last_activity_at,raw_source,committees(name,chamber,official_url)),`
            + `bill_subjects(legislative_subjects(subject_id,name))`
            + `&bill_id=eq.${id}&limit=1`),
        // !bill_relations_target_bill_id_fkey disambiguates from the other FK
        // this table has to `bills` (source_bill_id) -- Postgres's default name
        // for an inline `references` clause with no explicit constraint name.
        // A rejection (e.g. the name differs) degrades to no related bills
        // rather than failing the whole detail view.
        usFetch(env, 'bill_relations',
            `select=target_bill_id,target_congress_number,target_bill_type,target_bill_number,`
            + `relation_type,relation_origin,similarity_score,`
            + `bills!bill_relations_target_bill_id_fkey(title)`
            + `&source_bill_id=eq.${id}&limit=200`)
            .catch((err) => { console.log(`[us] bill_relations unavailable: ${err.message}`); return []; }),
    ]);

    if (!rows.length) throw usNotFound(`bill ${billId}`);

    const bill = rows[0];
    // embedding is a 1536-float vector -- ~30KB of JSON per bill, useless to the
    // browser and expensive in KV. raw_source is the whole Congress.gov payload.
    delete bill.embedding;
    delete bill.raw_source;
    for (const v of bill.bill_text_versions || []) delete v.raw_source;

    // A referral recorded against a JEC alias code (jhje00/jsec00) would
    // otherwise show a chip whose data-id the committee grid no longer has a
    // tile for (committee_directory collapsed it into jjec00) -- resolve
    // every referred committee_id to its canonical form before building chips.
    const referredIds = [...new Set((bill.bill_committees || []).map((bc) => bc.committee_id))];
    const canonicalByReferredId = new Map();
    if (referredIds.length) {
        const identityRows = await usFetch(env, 'committee_identity',
            `select=source_committee_id,canonical_committee_id&source_committee_id=in.(${referredIds.map((rid) => encodeURIComponent(rid)).join(',')})`)
            .catch((err) => { console.log(`[us] committee_identity lookup unavailable: ${err.message}`); return []; });
        for (const row of identityRows) canonicalByReferredId.set(row.source_committee_id, row.canonical_committee_id);
    }

    bill.committees = (bill.bill_committees || []).map((bc) => ({
        committee_id: canonicalByReferredId.get(bc.committee_id) || bc.committee_id,
        activity_names: bc.activity_names || [],
        activities: (bc.raw_source?.activities || []).map(a => ({ name: a.name, date: a.date || null })),
        first_referred_at: bc.first_referred_at,
        last_activity_at: bc.last_activity_at,
        name: bc.committees?.name,
        chamber: bc.committees?.chamber,
        official_url: bc.committees?.official_url,
    }));
    delete bill.bill_committees;

    bill.lifecycle = PolicyEvidence.buildLifecycle(bill);
    bill.congress_url = PolicyEvidence.billUrl(bill.congress_number, bill.bill_type, bill.bill_number) || bill.congress_url;

    bill.official_related_bills = shapeRelations(relations, false);
    bill.similar_bills = shapeRelations(relations, true);

    (bill.bill_actions || []).sort((a, b) => String(b.action_date).localeCompare(String(a.action_date)));
    return { ok: true, body: bill };
}

function usEoFilter(q) {
    const agencyId = q.get('agency_id') || '';
    const page = pageParams(q);
    return { agencyId, ...page, cacheKey: [agencyId, page.limit, page.offset].join('|') };
}

const EO_LIST_COLUMNS = 'eo_number,document_number,title,president_name,signed_date,'
    + 'publication_date,citation,federal_register_url,pdf_url,executive_order_url,summary';

async function usEoList(env, f) {
    const query = [
        `select=${EO_LIST_COLUMNS}${f.agencyId ? ',executive_order_agencies!inner(agency_id)' : ''}`,
        f.agencyId ? `executive_order_agencies.agency_id=eq.${encodeURIComponent(f.agencyId)}` : '',
        'order=signed_date.desc.nullslast,eo_number.desc',
        `limit=${f.limit}`,
        `offset=${f.offset}`,
    ].filter(Boolean).join('&');

    const page = await usFetch(env, 'executive_orders', query, { count: 'exact' });
    return {
        ok: true,
        body: {
            filter: { type: f.agencyId ? 'agency' : 'all', id: f.agencyId || null },
            ...pageEnvelope(page.rows, f, page.total),
        },
    };
}

async function usEoDetail(env, eoNumber) {
    const rows = await usFetch(env, 'executive_orders',
        `select=${EO_LIST_COLUMNS},`
        + `executive_order_agencies(relationship_type,relation_origin,source_url,evidence_excerpt,evidence_section,`
        + `agencies(agency_id,name,short_name,agency_type)),`
        + `executive_order_authorities(legal_authorities(citation,title,official_url,verification_status,linked_bill_id)),`
        + `executive_order_regulations(regulations(regulation_id,document_type,title,publication_date,effective_on,federal_register_url))`
        + `&eo_number=eq.${eoNumber}&limit=1`);

    if (!rows.length) throw usNotFound(`EO ${eoNumber}`);
    const eo = rows[0];

    // Kept per relationship_type rather than flattened to a bare agency list --
    // issuing_document/implementing_regulation carry no evidence text, while
    // the official_text_citation roles (directed/coordinating/consulted) do,
    // and the UI shows *why* an agency is attached only when it has one.
    eo.agency_relations = (eo.executive_order_agencies || [])
        .filter((x) => x.agencies)
        .map((x) => ({
            agency: x.agencies,
            relationship_type: x.relationship_type,
            relation_origin: x.relation_origin,
            source_url: x.source_url,
            evidence_excerpt: x.evidence_excerpt,
            evidence_section: x.evidence_section,
        }));
    delete eo.executive_order_agencies;

    // linked_bill_id -> bill_id: the UI's citation renderer only knows the
    // generic "bill_id" name, the same as everywhere else a bill is linked.
    eo.legal_authorities = (eo.executive_order_authorities || [])
        .map((x) => x.legal_authorities)
        .filter(Boolean)
        .map((a) => ({
            citation: a.citation,
            title: a.title,
            official_url: a.official_url,
            verification_status: a.verification_status,
            bill_id: a.linked_bill_id,
        }));
    delete eo.executive_order_authorities;

    eo.related_regulations = (eo.executive_order_regulations || []).map((x) => x.regulations).filter(Boolean);
    delete eo.executive_order_regulations;

    return { ok: true, body: eo };
}

function usRegulationFilter(q) {
    const raw = q.get('title_number');
    const titleNumber = /^\d{1,2}$/.test(raw || '') && Number(raw) >= 1 && Number(raw) <= 50 ? raw : '';
    const agencyId = q.get('agency_id') || '';
    const page = pageParams(q);
    return { titleNumber, agencyId, ...page, cacheKey: [titleNumber, agencyId, page.limit, page.offset].join('|') };
}

// Abstracts are deliberately not selected: docs/api-spec.md forbids storing or
// re-serving document full text, and the screen links out to Federal Register.
const REGULATION_LIST_COLUMNS = 'regulation_id,document_number,document_type,title,'
    + 'publication_date,effective_on,comments_close_on,federal_register_url,citation,rin';

async function usRegulationList(env, f) {
    const embeds = [];
    const filters = [];
    if (f.titleNumber) {
        embeds.push('regulation_cfr_references!inner(title_number,part_number)');
        filters.push(`regulation_cfr_references.title_number=eq.${f.titleNumber}`);
    }
    if (f.agencyId) {
        embeds.push('regulation_agencies!inner(agency_id)');
        filters.push(`regulation_agencies.agency_id=eq.${encodeURIComponent(f.agencyId)}`);
    }

    const query = [
        `select=${REGULATION_LIST_COLUMNS}${embeds.length ? ',' + embeds.join(',') : ''}`,
        ...filters,
        'order=publication_date.desc.nullslast,regulation_id.desc',
        `limit=${f.limit}`,
        `offset=${f.offset}`,
    ].filter(Boolean).join('&');

    const page = await usFetch(env, 'regulations', query, { count: 'exact' });
    return {
        ok: true,
        body: {
            filter: { title_number: f.titleNumber ? Number(f.titleNumber) : null, agency_id: f.agencyId || null },
            ...pageEnvelope(page.rows, f, page.total),
        },
    };
}

// Right-hand column of the committee screen: subcommittees. Everything else
// shown there (name, jurisdiction, the verified agency-name tags) is already
// on the committee's own /overview entry, which is where the UI reads it
// from -- this endpoint only adds what that list doesn't carry. Members are
// not in the schema yet, so the screen keeps its "위원장 정보 준비 중"
// placeholder for those regardless.
async function usCommitteeDetail(env, committeeId) {
    // committeeId may be a JEC alias code reached through an old link
    // (jhje00/jsec00) -- resolve it to the canonical id the overview grid
    // now uses (committee_directory) before looking up subcommittees, or a
    // stale link would 404 against an id that no longer heads its own row.
    const identityRows = await usFetch(env, 'committee_identity',
        `select=canonical_committee_id&source_committee_id=eq.${encodeURIComponent(committeeId)}&limit=1`);
    const canonicalId = identityRows[0]?.canonical_committee_id || committeeId;
    const subcommittees = await usFetch(env, 'committee_directory',
        `select=committee_id,name,chamber,official_url`
        + `&canonical_parent_committee_id=eq.${encodeURIComponent(canonicalId)}&order=name.asc&limit=100`);
    return { ok: true, body: { committee_id: canonicalId, requested_committee_id: committeeId, subcommittees } };
}

// The CFR title screen: regulations filed under the title, plus the executive
// orders reached through those regulations' own EO links. Per docs/api-spec.md
// ("분류 개수"), an EO is deliberately never classified against a CFR title
// directly -- only through a regulation that carries the title reference --
// so this is the one place that resolves that two-hop path.
async function usCfrTitleDetail(env, titleNumber) {
    const [titleRows, regs] = await Promise.all([
        usFetch(env, 'cfr_titles',
            `select=title_number,title_name,reserved&title_number=eq.${titleNumber}&limit=1`),
        usFetch(env, 'regulations',
            `select=${REGULATION_LIST_COLUMNS},regulation_cfr_references!inner(title_number),`
            + `executive_order_regulations(executive_orders(eo_number,title,signed_date))`
            + `&regulation_cfr_references.title_number=eq.${titleNumber}`
            + `&order=publication_date.desc.nullslast&limit=200`),
    ]);

    if (!titleRows.length) throw usNotFound(`CFR title ${titleNumber}`);
    const title = titleRows[0];

    // Regulations map 1:1 into the list the UI already knows how to render
    // (renderRegulations); EOs are collected into a title-wide set since the
    // same order can implement more than one regulation under this title.
    const eoByNumber = new Map();
    for (const r of regs) {
        for (const link of r.executive_order_regulations || []) {
            if (link.executive_orders) eoByNumber.set(link.executive_orders.eo_number, link.executive_orders);
        }
        delete r.executive_order_regulations;
        delete r.regulation_cfr_references;
    }

    return {
        ok: true,
        body: {
            title_number: title.title_number,
            name: title.title_name,
            reserved: title.reserved,
            regulations: regs,
            executive_orders: [...eoByNumber.values()],
        },
    };
}

// Agency screen: the agency itself plus its 하위 기관 (agency_type='sub'). The
// EO list on the left comes from /api/us/executive/orders?agency_id=...
async function usAgencyDetail(env, agencyId) {
    const id = encodeURIComponent(agencyId);
    const [rows, children] = await Promise.all([
        usFetch(env, 'agencies',
            `select=agency_id,name,short_name,agency_type,parent_agency_id,agency_url&agency_id=eq.${id}&limit=1`),
        usFetch(env, 'agencies',
            `select=agency_id,name,short_name,agency_type,agency_url&parent_agency_id=eq.${id}&order=name.asc&limit=200`),
    ]);

    if (!rows.length) throw usNotFound(`agency ${agencyId}`);
    return { ok: true, body: { ...rows[0], sub_agencies: children } };
}
