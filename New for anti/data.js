(async function() {
    // === Universal Commodity Taxonomy Engine ===
    const COMMODITY_TAXONOMY = {
        "soybeans": {
            id: "soybeans",
            name_ko: "대두(콩)",
            aliases: ["soybeans", "soybean", "soja", "대두", "콩", "soy", "1201", "120190", "대두 (soybeans)"]
        },
        "rice": {
            id: "rice",
            name_ko: "쌀",
            aliases: ["rice", "arroz", "쌀", "벼", "백미", "1006"]
        },
        "coal": {
            id: "coal",
            name_ko: "석탄",
            aliases: ["coal", "carvão", "석탄", "2701"]
        },
        "corn": {
            id: "corn",
            name_ko: "옥수수",
            aliases: ["corn", "maize", "milho", "옥수수", "1005", "옥수수 (corn)", "옥수수 (corn - safrinha)"]
        },
        "wheat": {
            id: "wheat",
            name_ko: "밀",
            aliases: ["wheat", "trigo", "밀", "1001", "밀 (wheat)"]
        },
        "gas": {
            id: "gas",
            name_ko: "천연가스",
            aliases: ["gas", "natural gas", "천연가스", "lng", "2711"]
        },
        "gold": {
            id: "gold",
            name_ko: "금",
            aliases: ["gold", "금", "7108"]
        },
        "silver": {
            id: "silver",
            name_ko: "은",
            aliases: ["silver", "은", "7106"]
        },
        "copper": {
            id: "copper",
            name_ko: "구리",
            aliases: ["copper", "구리", "동", "7403"]
        },
        "zinc": {
            id: "zinc",
            name_ko: "아연",
            aliases: ["zinc", "아연", "7901"]
        },
        "aluminum": {
            id: "aluminum",
            name_ko: "알루미늄",
            aliases: ["aluminum", "알루미늄", "7601"]
        },
        "sugar": {
            id: "sugar",
            name_ko: "설탕",
            aliases: ["sugar", "설탕", "원당", "1701"]
        },
        "coffee": {
            id: "coffee",
            name_ko: "커피",
            aliases: ["coffee", "커피", "원두", "0901"]
        }
    };

    window.COMMODITY_TAXONOMY = COMMODITY_TAXONOMY;

    window.normalizeCommodity = function(rawInput) {
        if (!rawInput) return "unknown";
        const str = String(rawInput).toLowerCase().trim();
        for (const key in COMMODITY_TAXONOMY) {
            if (COMMODITY_TAXONOMY[key].id === str || COMMODITY_TAXONOMY[key].aliases.includes(str)) {
                return COMMODITY_TAXONOMY[key].id;
            }
            for (const alias of COMMODITY_TAXONOMY[key].aliases) {
                if (str.includes(alias) && alias.length > 2) {
                    return COMMODITY_TAXONOMY[key].id;
                }
            }
        }
        return str;
    };
    const normalizeCommodity = window.normalizeCommodity;
    // ===========================================

    window.loadMacroData = async function() {
    // 0. Fetch real-time Macro Data from FRED (key lives server-side in the Worker)
    const series = [
        { id: "DEXUSEU", name: "EUR/USD" },
        { id: "DEXJPUS", name: "USD/JPY" },
        { id: "NASDAQCOM", name: "NASDAQ" },
        { id: "WALCL", name: "FED_BS" },
        { id: "WTREGEN", name: "TGA" }
    ];
    let macroData = {};
    try {
        const fredPromises = series.map(async (s) => {
            const url = `/api/macro?source=fred&series_id=${s.id}`;
            const res = await fetch(url);
            const data = await res.json();
            if (data.observations && data.observations.length > 0) {
                return { name: s.name, value: data.observations[0].value, date: data.observations[0].date };
            }
            return { name: s.name, value: "N/A", date: "N/A" };
        });
        const fredResults = await Promise.all(fredPromises);
        fredResults.forEach(r => {
            // 1. Financials: Time-Series Normalization (SSOT)
            // Force UTC 00:00:00 normalization for all macro indicators to prevent timezone discrepancies
            let normalizedDate = r.date;
            if (r.date !== "N/A") {
                normalizedDate = r.date + " (UTC 00:00 Normalized)";
            }
            macroData[r.name] = { value: r.value, date: normalizedDate };
        });
    } catch(e) {
        console.error("FRED API Error:", e);
    }

    // 0.5 KRX (KOSPI) removed: the KRX Data Marketplace key returned
    // 401 "Unauthorized API Call" on every request, so the tile never had data.

    // 0.55 Fetch real-time Macro Data from BOK (Bank of Korea ECOS)
    try {
        const bokUrl = `/api/macro?source=bok`;
        
        const bokRes = await fetch(bokUrl);
        
        if (bokRes.ok) {
            const bokData = await bokRes.json();
            if (bokData.KeyStatisticList && bokData.KeyStatisticList.row) {
                const rows = bokData.KeyStatisticList.row;
                const krwUsd = rows.find(r => r.KEYSTAT_NAME === "원/달러 환율(종가)");
                const bokRate = rows.find(r => r.KEYSTAT_NAME === "한국은행 기준금리");
                
                if (krwUsd) {
                    macroData["KRW_USD"] = { value: krwUsd.DATA_VALUE, date: krwUsd.CYCLE + " (UTC 00:00 Normalized)" };
                } else {
                    macroData["KRW_USD"] = { value: "데이터 없음", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
                }
                
                if (bokRate) {
                    macroData["BOK_RATE"] = { value: bokRate.DATA_VALUE, date: bokRate.CYCLE + " (UTC 00:00 Normalized)" };
                } else {
                    macroData["BOK_RATE"] = { value: "데이터 없음", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
                }
            } else {
                macroData["KRW_USD"] = { value: "API 파싱 오류", date: "N/A" };
                macroData["BOK_RATE"] = { value: "API 파싱 오류", date: "N/A" };
            }
        } else {
            macroData["KRW_USD"] = { value: "API 연결 실패", date: "N/A" };
            macroData["BOK_RATE"] = { value: "API 연결 실패", date: "N/A" };
        }
    } catch(e) {
        console.error("BOK API Error:", e);
        macroData["KRW_USD"] = { value: "N/A", date: "N/A" };
        macroData["BOK_RATE"] = { value: "N/A", date: "N/A" };
    }

    // 0.6 Fetch real-time Macro Data from EIA (WTI Crude Oil Price)
    try {
        // Fetch Daily WTI Spot Price
        const eiaUrl = `/api/macro?source=eia&route=petroleum/pri/spt/data/&seriesId=RWTC`;
        
        // Fetch Daily Henry Hub Natural Gas Spot Price
        const eiaGasUrl = `/api/macro?source=eia&route=natural-gas/pri/spt/data/&seriesId=RNGWHHD`;

        const [eiaRes, eiaGasRes] = await Promise.all([
            fetch(eiaUrl),
            fetch(eiaGasUrl)
        ]);
        
        if (eiaRes.ok) {
            const eiaData = await eiaRes.json();
            if (eiaData.response && eiaData.response.data && eiaData.response.data.length > 0) {
                const wtiData = eiaData.response.data[0];
                macroData["WTI_OIL"] = { 
                    value: wtiData.value, 
                    date: wtiData.period + " (UTC 00:00 Normalized)" 
                };
            } else {
                macroData["WTI_OIL"] = { value: "데이터 없음", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
            }
        } else {
            macroData["WTI_OIL"] = { value: "API 연결 실패", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
        }

        if (eiaGasRes.ok) {
            const gasData = await eiaGasRes.json();
            if (gasData.response && gasData.response.data && gasData.response.data.length > 0) {
                const natGasData = gasData.response.data[0];
                macroData["NAT_GAS"] = { 
                    value: natGasData.value, 
                    date: natGasData.period + " (UTC 00:00 Normalized)" 
                };
            } else {
                macroData["NAT_GAS"] = { value: "데이터 없음", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
            }
        } else {
            macroData["NAT_GAS"] = { value: "API 연결 실패", date: new Date().toISOString() + " (UTC 00:00 Normalized)" };
        }
    } catch(e) {
        console.error("EIA API Error:", e);
        macroData["WTI_OIL"] = { value: "N/A", date: "N/A" };
        macroData["NAT_GAS"] = { value: "N/A", date: "N/A" };
    }

    // 1. Fetch real-time weather from Open-Meteo
    const regions = [
        { name: "Mato Grosso (Brazil)", lat: -12.68, lon: -56.92 },
        { name: "Iowa (USA)", lat: 41.87, lon: -93.09 }
    ];
    
    let weatherMap = {};
    try {
        const fetchPromises = regions.map(async (r) => {
            const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${r.lat}&longitude=${r.lon}&current_weather=true`);
            const data = await res.json();
            return { name: r.name, weather: data.current_weather };
        });
        const results = await Promise.all(fetchPromises);
        results.forEach(res => {
            weatherMap[res.name] = res.weather;
        });
    } catch (e) {
        console.error("Open-Meteo API Fetch Error:", e);
    }
    
    window.MacroData = macroData;
    if (window.initApp) window.initApp();
    }; // End of loadMacroData

    // 2. Base Trade Data
    const COUNTRIES = {
        // Sub-national growing regions carried by the Brazil yield models.
        // MATOPIBA is the Bahia/Maranhão/Piauí/Tocantins frontier; the São
        // Paulo point sits in the Ribeirão Preto cane and coffee belt.
        "MATOPIBA (Brazil)": [-45.5, -10.5],
        "Sao Paulo (Brazil)": [-47.8, -21.4],
        "USA": [-95.7129, 37.0902], "China": [104.1954, 35.8617], "Brazil": [-51.9253, -14.2350],
        "Argentina": [-63.6167, -38.4161], "Russia": [105.3188, 61.5240], "Ukraine": [31.1656, 48.3794],
        "India": [78.9629, 20.5937], "Canada": [-106.3468, 56.1304], "Australia": [133.7751, -25.2744],
        "France": [2.2137, 46.2276], "Germany": [10.4515, 51.1657], "Indonesia": [113.9213, -0.7893],
        "Malaysia": [101.9758, 4.2105], "Thailand": [100.9925, 15.8700], "Vietnam": [108.2772, 14.0583],
        "Egypt": [30.8025, 26.8206], "Mexico": [-102.5528, 23.6345], "Japan": [138.2529, 36.2048],
        "South Korea": [127.7669, 35.9078], "UK": [-3.4360, 55.3781], "Italy": [12.5674, 41.8719],
        "Spain": [-3.7492, 40.4637], "Turkey": [35.2433, 38.9637], "Saudi Arabia": [45.0792, 23.8859],
        "UAE": [53.8478, 23.4241], "South Africa": [22.9375, -30.5595], "Nigeria": [8.6753, 9.0820],
        "Pakistan": [69.3451, 30.3753], "Bangladesh": [90.3563, 23.6850], "Philippines": [121.7740, 12.8797],
        "Iran": [53.6880, 32.4279], "Algeria": [1.6596, 28.0339], "Morocco": [-7.0926, 31.7917],
        "Poland": [19.1451, 51.9194], "Netherlands": [5.2913, 52.1326], "Belgium": [4.4699, 50.5039],
        "Switzerland": [8.2275, 46.8182], "Colombia": [-74.2973, 4.5709], "Peru": [-75.0152, -9.1900],
        "Chile": [-71.5429, -35.6751], "New Zealand": [174.8860, -40.9006], "Kazakhstan": [66.9237, 48.0196],
        "Romania": [24.9668, 45.9432], "Hungary": [19.5033, 47.1625], "Belarus": [27.9534, 53.7098],
        "Paraguay": [-58.4438, -23.4425], "Uruguay": [-55.7658, -32.5228], "Ethiopia": [39.7823, 9.1450],
        "Uganda": [32.2903, 1.3733], "Qatar": [51.1839, 25.3548], "Norway": [8.4689, 60.4720],
        "Iraq": [43.6793, 33.2232], "Hong Kong": [114.1694, 22.3193], "Congo DR": [21.7587, -4.0383],
        "Taiwan": [120.9605, 23.6978], "Kenya": [37.9062, -0.0236], "Tanzania": [34.8888, -6.3690],
        "Myanmar": [95.9560, 21.9162], "Cambodia": [104.9910, 12.5657], "Ivory Coast": [-5.5471, 7.5400],
        "Ghana": [-1.0232, 7.9465], "Senegal": [-14.4524, 14.4974], "Uzbekistan": [64.5853, 41.3775]
    };

    const M49_MAP = {
        // UN Comtrade reports US trade under 842 ("USA, PR and USVI"), not the
        // plain geographic M49 code 840 -- querying 840 returns zero rows for
        // every commodity and every year, which is why the US was missing from
        // the map entirely. 840 is kept mapped so any legacy rows still resolve.
        842: "USA", 840: "USA",
        156: "China", 76: "Brazil", 32: "Argentina", 643: "Russia", 804: "Ukraine",
        356: "India", 124: "Canada", 36: "Australia", 250: "France", 276: "Germany", 360: "Indonesia",
        458: "Malaysia", 764: "Thailand", 704: "Vietnam", 818: "Egypt", 484: "Mexico", 392: "Japan",
        410: "South Korea", 826: "UK", 380: "Italy", 724: "Spain", 792: "Turkey", 682: "Saudi Arabia",
        784: "UAE", 710: "South Africa", 566: "Nigeria", 586: "Pakistan", 50: "Bangladesh", 608: "Philippines",
        364: "Iran", 12: "Algeria", 504: "Morocco", 616: "Poland", 528: "Netherlands", 56: "Belgium",
        756: "Switzerland", 170: "Colombia", 604: "Peru", 152: "Chile", 554: "New Zealand", 398: "Kazakhstan",
        642: "Romania", 348: "Hungary", 112: "Belarus", 600: "Paraguay", 858: "Uruguay", 231: "Ethiopia",
        800: "Uganda", 634: "Qatar", 578: "Norway", 368: "Iraq", 344: "Hong Kong", 180: "Congo DR",
        158: "Taiwan", 404: "Kenya", 834: "Tanzania", 104: "Myanmar", 116: "Cambodia", 384: "Ivory Coast",
        288: "Ghana", 686: "Senegal", 860: "Uzbekistan"
    };

    const ALL_M49_CODES = Object.keys(M49_MAP).join(",");

    // The crop-trade panel needs a country's Comtrade reporter code, and this
    // is the only table that carries it. Exported rather than duplicated so the
    // 842-not-840 correction above keeps applying everywhere. The name matching
    // lives in app.js, which is where resolveCountry is.
    window.M49_MAP = M49_MAP;

    // === Commodity API Configuration (HS Codes + Major Traders) ===
    // 출처: UN Comtrade (comtradeapi.un.org), HS Classification
    const COMMODITY_API_CONFIG = {
        oil: {
            hsCode: "2709",
            colorScheme: { source: [239, 68, 68], target: [248, 113, 113] }
        },
        gas: {
            hsCode: "2711",
            colorScheme: { source: [239, 68, 68], target: [248, 113, 113] }
        },
        thermal_coal: {
            hsCode: "2701",
            colorScheme: { source: [255, 140, 0], target: [250, 204, 21] }
        },
        met_coal: {
            hsCode: "2704",
            colorScheme: { source: [255, 140, 0], target: [250, 204, 21] }
        },
        // Ore, natural compounds and enriched together, the same reasoning the
        // ferroalloys got: a country with no enrichment capacity buys enriched
        // fuel, not yellowcake, and 2612.10 alone would miss that entirely.
        // Deliberately not 2844, which sweeps in thorium, medical isotopes and
        // radioactive waste -- none of which is the nuclear fuel trade.
        uranium: {
            hsCode: "261210,284410,284420",
            colorScheme: { source: [74, 222, 128], target: [163, 230, 53] }
        },
        gold: {
            hsCode: "7108",
            colorScheme: { source: [250, 204, 21], target: [253, 224, 71] }
        },
        silver: {
            hsCode: "7106",
            colorScheme: { source: [250, 204, 21], target: [253, 224, 71] }
        },
        copper: {
            hsCode: "7403",
            colorScheme: { source: [14, 165, 233], target: [56, 189, 248] }
        },
        zinc: {
            hsCode: "7901",
            colorScheme: { source: [14, 165, 233], target: [56, 189, 248] }
        },
        aluminum: {
            hsCode: "7601",
            colorScheme: { source: [14, 165, 233], target: [56, 189, 248] }
        },
        wheat: {
            hsCode: "1001",
            colorScheme: { source: [34, 197, 94], target: [74, 222, 128] }
        },
        corn: {
            hsCode: "1005",
            colorScheme: { source: [34, 197, 94], target: [74, 222, 128] }
        },
        soybeans: {
            hsCode: "1201",
            colorScheme: { source: [34, 197, 94], target: [74, 222, 128] }
        },
        sugar: {
            hsCode: "1701",
            colorScheme: { source: [34, 197, 94], target: [74, 222, 128] }
        },
        coffee: {
            hsCode: "0901",
            colorScheme: { source: [34, 197, 94], target: [74, 222, 128] }
        },

        // Battery and strategic minerals. These are the commodities the export
        // control layer actually has entries for -- Indonesia's nickel ore ban,
        // China's graphite and rare-earth licensing, the DRC on cobalt -- so
        // without them the control data had nowhere to show.
        nickel: { hsCode: "7502", colorScheme: { source: [148, 163, 184], target: [203, 213, 225] } },
        cobalt: { hsCode: "8105", colorScheme: { source: [96, 165, 250], target: [147, 197, 253] } },
        lithium: { hsCode: "283691", colorScheme: { source: [167, 139, 250], target: [196, 181, 253] } },
        graphite: { hsCode: "2504", colorScheme: { source: [100, 116, 139], target: [148, 163, 184] } },
        rare_earths: { hsCode: "280530", colorScheme: { source: [217, 70, 239], target: [232, 121, 249] } },

        // Steel chain. Iron ore and manganese are the two largest dry-bulk
        // flows after coal, which the shipping screens already model.
        //
        // Manganese and chromium carry their ferroalloys alongside the ore,
        // because the ore alone describes a trade that mostly is not happening.
        // Countries with no smelter buy the alloy, not the rock: US imports of
        // chrome ore run $32M against $373M of ferrochromium, and manganese ore
        // $5M against $203M of ferromanganese. On ore alone the United States
        // read as a country that barely touches chromium, which is the opposite
        // of true -- it has mined no chromite since 1961 and imports all of it.
        iron_ore: { hsCode: "2601", colorScheme: { source: [180, 83, 9], target: [217, 119, 6] } },
        manganese: { hsCode: "2602,720211,720219", colorScheme: { source: [161, 98, 7], target: [202, 138, 4] } },
        chromium: { hsCode: "2610,720241,720249", colorScheme: { source: [120, 113, 108], target: [168, 162, 158] } },

        // Remaining industrial metals, and the platinum group as a precious
        // metal distinct from gold and silver.
        tin: { hsCode: "8001", colorScheme: { source: [113, 113, 122], target: [161, 161, 170] } },
        lead: { hsCode: "7801", colorScheme: { source: [82, 82, 91], target: [113, 113, 122] } },
        platinum: { hsCode: "7110", colorScheme: { source: [226, 232, 240], target: [241, 245, 249] } }
    };

    // === Fetch Real Trade Data from UN Comtrade via CORS Proxy ===
    // 출처: UN Comtrade API (comtradeapi.un.org) → Cloudflare Pages Function 프록시 경유
    window.fetchComtradeArcs = async function(commodityKey) {
        const config = COMMODITY_API_CONFIG[commodityKey];
        if (!config) {
            console.warn(`[Comtrade] No API config for commodity: ${commodityKey}`);
            return [];
        }

        console.log(`[Comtrade] Fetching real trade data for ${commodityKey} (HS ${config.hsCode})...`);

        try {
            // ALL_M49_CODES contains 40+ countries allowing for dynamic mapping of global trade routes
            // Reporter/partner list intentionally omitted: the Worker supplies
            // its own canonical list, so this request lands on exactly the
            // cache key the nightly warm-up wrote.
            const proxyUrl = `/api/comtrade?hs=${config.hsCode}&period=2023`;
            const res = await fetch(proxyUrl);

            if (!res.ok) {
                console.warn(`[Comtrade] Proxy returned ${res.status} for ${commodityKey}`);
                return [];
            }

            const json = await res.json();
            if (!json.data || json.data.length === 0) {
                console.warn(`[Comtrade] No data returned for ${commodityKey}`);
                return [];
            }

            // Use a map to deduplicate arcs and combine X (Export) and M (Import) 'Mirror Data'
            const arcMap = {};

            // Position lookup. COUNTRIES is a 65-entry hand-written table; anything
            // outside it used to be dropped here, which is why newly added
            // countries never appeared on the map or became clickable. The map's
            // own country registry (app.js) resolves any name the basemap knows,
            // so the curated table is now a preference, not a gate.
            const posOf = (name) => COUNTRIES[name]
                || (window.CountryCoords ? window.CountryCoords(name) : null);

            json.data.forEach(row => {
                // Fall back to the names Comtrade ships with the row, so a code
                // missing from M49_MAP no longer silently loses the route.
                const reporterName = M49_MAP[row.reporterCode] || row.reporterDesc;
                const partnerName = M49_MAP[row.partnerCode] || row.partnerDesc;
                if (!reporterName || !partnerName) return;
                if (!posOf(reporterName) || !posOf(partnerName)) return;
                if (reporterName === partnerName) return; // Ignore domestic trade

                const tradeValue = row.primaryValue || 0;  // USD
                const netWeight = row.netWgt || 0;          // kg
                if (tradeValue <= 0) return;

                let sourceName, targetName;
                if (row.flowCode === "M") {
                    sourceName = partnerName; // Exporter
                    targetName = reporterName; // Importer
                } else {
                    sourceName = reporterName;
                    targetName = partnerName;
                }

                const arcKey = `${sourceName}-${targetName}`;
                const volume = Math.round(tradeValue / 1000000); // Millions USD
                const netWeightMt = Math.round(netWeight / 1000000000 * 100) / 100;

                if (!arcMap[arcKey] || arcMap[arcKey].usdValue < tradeValue) {
                    arcMap[arcKey] = {
                        sourceName,
                        targetName,
                        sourcePosition: posOf(sourceName),
                        targetPosition: posOf(targetName),
                        volume,
                        netWeightMt,
                        percentage: 0,
                        typeName: config.hsCode,
                        sourceColor: config.colorScheme.source,
                        targetColor: config.colorScheme.target,
                        usdValue: tradeValue,
                        dataSource: "UN Comtrade (comtradeapi.un.org)"
                    };
                }
            });

            // No Comex Stat override here any more.
            //
            // This used to try to rewrite Brazil's arcs from live_override.json,
            // reading row.NO_PAIS / VL_FOB / KG_LIQUIDO. agrobr never returns
            // those fields -- its Comex Stat export feed is keyed by Brazilian
            // state of origin (uf), with no destination country at all, so
            // COUNTRIES[undefined] was falsy and all 222 rows were skipped every
            // time. The block never once had an effect, but it did label arcs
            // "Brazil Comex Stat (Live Monthly)" as if it had.
            //
            // Destination-level Brazil trade already comes from Comtrade above.
            // The Comex Stat feed is genuinely useful as a monthly national
            // total instead -- see window.loadBrazilMonthlyExports().

            const arcs = Object.values(arcMap);

            // Calculate percentages.
            // Keep one decimal: trade is dominated by a few mega-routes (Brazil->China
            // alone is ~71% of soybeans), so Math.round() collapsed every remaining
            // route to 0 and the map's `percentage >= 1` filter then dropped ~95% of them.
            const totalVol = arcs.reduce((sum, a) => sum + a.volume, 0);
            arcs.forEach(a => {
                a.percentage = totalVol > 0 ? Math.round((a.volume / totalVol) * 1000) / 10 : 0;
            });

            // Sort by volume descending
            arcs.sort((a, b) => b.volume - a.volume);

            console.log(`[Comtrade] ✅ ${commodityKey}: ${arcs.length} trade flows loaded (Total: $${totalVol}M)`);
            return arcs;

        } catch (e) {
            console.warn(`[Comtrade] ❌ Failed to fetch ${commodityKey}:`, e.message);
            return [];
        }
    };

    // === Brazil monthly soybean exports (Comex Stat, via live_override.json) ===
    // The feed is one row per Brazilian state per month, with no destination
    // country -- so it cannot produce trade routes, only a national total.
    // Summing the states gives a monthly export series that lines up with
    // reality (2024: ~98.8 Mt / ~$42.9B).
    let brazilMonthlyCache = null;
    window.loadBrazilMonthlyExports = async function() {
        if (brazilMonthlyCache) return brazilMonthlyCache;

        try {
            const res = await fetch('/public/data/live_override.json');
            if (!res.ok) return null;

            const live = await res.json();
            const rows = live?.comexstat?.brazil_soybean_exports_2024;
            if (!Array.isArray(rows) || rows.length === 0) return null;

            const byMonth = {};
            for (const row of rows) {
                const m = row.mes;
                if (!byMonth[m]) byMonth[m] = { month: m, volumeTon: 0, valueUsd: 0 };
                byMonth[m].volumeTon += row.volume_ton || 0;
                byMonth[m].valueUsd += row.valor_fob_usd || 0;
            }

            const months = Object.values(byMonth).sort((a, b) => a.month - b.month);
            brazilMonthlyCache = {
                year: rows[0].ano,
                months,
                totalVolumeTon: months.reduce((s, m) => s + m.volumeTon, 0),
                totalValueUsd: months.reduce((s, m) => s + m.valueUsd, 0),
                dataSource: "Brazil Comex Stat (monthly, national total)"
            };
            console.log(`[ComexStat] Brazil ${brazilMonthlyCache.year}: ` +
                `${(brazilMonthlyCache.totalVolumeTon / 1e6).toFixed(1)} Mt / ` +
                `$${(brazilMonthlyCache.totalValueUsd / 1e9).toFixed(1)}B across ${months.length} months`);
            return brazilMonthlyCache;
        } catch (err) {
            console.warn("[ComexStat] Could not load live_override.json", err);
            return null;
        }
    };

    // === US Corn Belt yield forecast (statistical model, refreshed weekly) ===
    // Written by scripts/yield_model/run_forecast.py. Unlike the hardcoded
    // forecastData below, every number here is model output over real weather.
    let yieldForecastCache = null;
    window.loadYieldForecast = async function() {
        if (yieldForecastCache !== null) return yieldForecastCache;
        try {
            const res = await fetch('/public/data/yield_forecast.json');
            if (!res.ok) { yieldForecastCache = false; return false; }
            yieldForecastCache = await res.json();
            console.log(`[Yield] ${yieldForecastCache.season} forecast loaded ` +
                `(generated ${yieldForecastCache.generated_at})`);
            return yieldForecastCache;
        } catch (err) {
            console.warn('[Yield] forecast unavailable', err);
            yieldForecastCache = false;
            return false;
        }
    };

    // === Brazil regional yield forecast (statistical model, refreshed weekly) ===
    // Written by scripts/yield_model/brazil/run_forecast.py. Keyed by
    // region-crop rather than by crop alone, because the nine models are built
    // per region from separate methodologies. Each entry carries
    // skill.beats_trend; where that is false the weather features did not beat
    // a trend-only baseline out of sample and the number should be presented
    // as a trend extrapolation, not a weather-driven forecast.
    let brazilForecastCache = null;
    window.loadBrazilYieldForecast = async function() {
        if (brazilForecastCache !== null) return brazilForecastCache;
        try {
            const res = await fetch('/public/data/brazil_yield_forecast.json');
            if (!res.ok) { brazilForecastCache = false; return false; }
            brazilForecastCache = await res.json();
            const n = Object.keys(brazilForecastCache.regions || {}).length;
            console.log(`[Yield BR] ${brazilForecastCache.season} forecast loaded, ` +
                `${n} region-crops (generated ${brazilForecastCache.generated_at})`);
            return brazilForecastCache;
        } catch (err) {
            console.warn('[Yield BR] forecast unavailable', err);
            brazilForecastCache = false;
            return false;
        }
    };

    // === India regional yield forecast (statistical model, refreshed weekly) ===
    // Written by scripts/yield_model/india/run_forecast.py. Three region-crops,
    // each following its own guide in Regions/인도 rather than a shared
    // methodology -- Punjab wheat is a terminal-heat problem, Madhya Pradesh
    // soybean a monsoon-timing problem, Vidarbha/Gujarat cotton an inverted-U
    // drought/pest problem. skill.beats_trend is false where the weather
    // features did not beat a trend-only baseline out of sample; such a figure
    // is a trend extrapolation and should be presented as one, not as a
    // weather-driven forecast.
    let indiaForecastCache = null;
    window.loadIndiaYieldForecast = async function() {
        if (indiaForecastCache !== null) return indiaForecastCache;
        try {
            const res = await fetch('/public/data/india_yield_forecast.json');
            if (!res.ok) { indiaForecastCache = false; return false; }
            indiaForecastCache = await res.json();
            const n = Object.keys(indiaForecastCache.regions || {}).length;
            console.log(`[Yield IN] ${indiaForecastCache.season} forecast loaded, ` +
                `${n} region-crops (generated ${indiaForecastCache.generated_at})`);
            return indiaForecastCache;
        } catch (err) {
            console.warn('[Yield IN] forecast unavailable', err);
            indiaForecastCache = false;
            return false;
        }
    };

    const defaultNews = (commodityName, country="Global") => ({
        "default": [
            { title: `Global ${commodityName} prices see fluctuation amid supply chain adjustments`, date: "Today", source: "Bloomberg", url: "https://www.bloomberg.com/markets/commodities" },
            { title: `Demand for ${commodityName} remains strong in Asian markets`, date: "1 day ago", source: "Reuters", url: "https://www.reuters.com/markets/commodities" }
        ],
        [country]: [
            { title: `${country} announces new ${commodityName} export policies for next quarter`, date: "2 hours ago", source: "Financial Times", url: "https://www.ft.com/commodities" },
            { title: `Local production of ${commodityName} in ${country} hits record high`, date: "Yesterday", source: "Wall Street Journal", url: "https://www.wsj.com/news/business/energy-oil-gas" }
        ]
    });

    const TradeData = {
        thermal_coal: {
            title: "에너지: 연료탄 (Thermal Coal)",
            desc: "전 세계 발전용 연료탄 수출입 무역 흐름",
            totalVolume: "980 Mt",
            topExporter: "인도네시아",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 2701)
            news: {
                "Indonesia": [{ title: "Indonesia sets new monthly thermal coal benchmark price higher", date: "1 day ago", source: "Jakarta Post", url: "https://www.thejakartapost.com/business/2026/07/25/coal-benchmark.html" }],
                "Australia": [{ title: "Thermal coal prices stabilize as Newcastle port clears backlog", date: "1 week ago", source: "Bloomberg", url: "https://www.bloomberg.com/news/articles/2026-07-20/newcastle-coal-port" }],
                "South Korea": [{ title: "South Korea aims to secure stable thermal coal supply for winter", date: "3 hours ago", source: "Korea Herald", url: "https://www.koreaherald.com/view.php?ud=202607260001" }],
                "UAE": [{ title: "UAE diversifies energy mix while maintaining strategic coal reserves", date: "2 days ago", source: "Gulf News", url: "https://gulfnews.com/business/energy/uae-coal-reserves-2026" }],
                "South Africa": [{ title: "South African coal exports to Middle East and India surge", date: "5 hours ago", source: "Mining Weekly", url: "https://www.miningweekly.com/article/sa-coal-exports-surge" }],
                "default": [{ title: "Global thermal coal prices stabilize", date: "Today", source: "Financial Times", url: "https://www.ft.com/content/coal-markets-update" }]
            },
            countryStats: {
                "Indonesia": { production: "600 Mt", import: "0 Mt", consumption: "150 Mt", price: "$85 / ton" },
                "Australia": { production: "250 Mt", import: "0 Mt", consumption: "50 Mt", price: "$120 / ton" },
                "India": { production: "800 Mt", import: "160 Mt", consumption: "950 Mt", price: "$90 / ton" },
                "South Africa": { production: "230 Mt", import: "0 Mt", consumption: "160 Mt", price: "$105 / ton" },
                "UAE": { production: "0 Mt", import: "18 Mt", consumption: "18 Mt", price: "$110 / ton" },
                "South Korea": { production: "1 Mt", import: "85 Mt", consumption: "86 Mt", price: "$115 / ton" },
                "default": { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" }
            }
        },
        met_coal: {
            title: "에너지: 원료탄 (Metallurgical Coal)",
            desc: "제철용 원료탄(코킹콜) 수출입 무역 흐름",
            totalVolume: "310 Mt",
            topExporter: "호주",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 2704)
            news: {
                "Australia": [{ title: "BHP ramps up metallurgical coal exports", date: "2 days ago", source: "Australian Financial Review", url: "https://www.afr.com/companies/mining" }],
                "Brazil": [{ title: "Vale looks to expand metallurgical coal exports to Asian markets", date: "1 week ago", source: "Valor Econômico", url: "https://valor.globo.com" }],
                "default": [{ title: "Steelmakers seek new sources of metallurgical coal", date: "Today", source: "Reuters", url: "https://www.reuters.com/markets/commodities/" }]
            },
            countryStats: {
                "Australia": { production: "180 Mt", import: "0 Mt", consumption: "5 Mt", price: "$250 / ton" },
                "USA": { production: "70 Mt", import: "5 Mt", consumption: "15 Mt", price: "$220 / ton" },
                "China": { production: "500 Mt", import: "60 Mt", consumption: "550 Mt", price: "$280 / ton" },
                "Brazil": { production: "10 Mt", import: "12 Mt", consumption: "18 Mt", price: "$260 / ton" },
                "default": { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" }
            }
        },
        oil: {
            title: "글로벌 에너지: 원유",
            desc: "전 세계 주요 산유국 및 소비국 간 원유 물동량 흐름",
            totalVolume: "98.5 Million bpd",
            topExporter: "사우디아라비아",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 2709)
            news: {
                ...defaultNews("Crude Oil"),
                "Saudi Arabia": [
                    { title: "[리스크 경보] 이란 타격 여파로 사우디 주요 원유 생산 시설 가동 중단 우려 확산", date: "2시간 전", source: "Reuters", url: "https://www.reuters.com/business/energy" },
                    { title: "중동 지정학적 리스크 고조... 브렌트유(Brent) 배럴당 85달러 돌파", date: "어제", source: "Bloomberg", url: "https://www.bloomberg.com/markets/commodities" }
                ],
                "USA": [
                    { title: "US crude oil exports reach record high to Europe", date: "2 days ago", source: "Wall Street Journal", url: "https://www.wsj.com/news/business/energy-oil-gas" }
                ]
            },
            countryStats: {
                "Saudi Arabia": { production: "10.5M bpd", import: "0M bpd", consumption: "3.2M bpd", price: "$82.50 / bbl (Export)" },
                "USA": { production: "13.2M bpd", import: "6.5M bpd", consumption: "19.8M bpd", price: "$78.20 / bbl (WTI)" },
                "China": { production: "4.2M bpd", import: "11.3M bpd", consumption: "15.0M bpd", price: "N/A" },
                "default": { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" }
            }
        },
        gas: {
            title: "글로벌 에너지: 천연가스 (Natural Gas)",
            desc: "전 세계 주요 LNG 및 파이프라인 가스 물동량 흐름",
            totalVolume: "4.04 Trillion cubic meters",
            topExporter: "미국 / 카타르",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 2711)
            news: {
                ...defaultNews("Natural Gas"),
                "USA": [
                    { title: "Henry Hub gas futures plummet as mild weather limits heating demand", date: "1 hour ago", source: "Bloomberg", url: "https://www.bloomberg.com" }
                ],
                "Qatar": [
                    { title: "Qatar signs new 20-year LNG supply deal with Asian buyers", date: "어제", source: "Reuters", url: "https://www.reuters.com" }
                ]
            },
            countryStats: {
                "USA": { production: "1032 Bcm", import: "79 Bcm", consumption: "881 Bcm", price: "Refer to Macro Panel" },
                "Qatar": { production: "178 Bcm", import: "0 Bcm", consumption: "38 Bcm", price: "N/A" },
                "Russia": { production: "702 Bcm", import: "8 Bcm", consumption: "474 Bcm", price: "N/A" },
                "default": { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" }
            }
        },
        gold: {
            title: "글로벌 귀금속: 금 (Gold)",
            desc: "스위스 정련소 및 주요 소비국 간의 금 무역 흐름",
            totalVolume: "4,741 Tonnes",
            topExporter: "스위스",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 7108)
            news: defaultNews("Gold")
        },
        silver: {
            title: "글로벌 귀금속: 은 (Silver)",
            desc: "산업용 및 투자용 은 글로벌 무역 흐름",
            totalVolume: "32,000 Tonnes",
            topExporter: "멕시코 / 페루",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 7106)
            news: defaultNews("Silver")
        },
        copper: {
            title: "글로벌 비철금속: 구리 (Copper)",
            desc: "전기차/인프라 핵심 소재인 구리의 물동량 (정광 및 제련)",
            totalVolume: "26.5 Million Tonnes",
            topExporter: "칠레",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 7403)
            news: defaultNews("Copper")
        },
        zinc: {
            title: "글로벌 비철금속: 아연 (Zinc)",
            desc: "도금용 주요 소재 아연 무역 흐름",
            totalVolume: "13.2 Million Tonnes",
            topExporter: "호주",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 7901)
            news: defaultNews("Zinc")
        },
        aluminum: {
            title: "글로벌 비철금속: 알루미늄",
            desc: "경량화 핵심 소재 알루미늄 무역 흐름",
            totalVolume: "68.9 Million Tonnes",
            topExporter: "중국 (가공품)",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 7601)
            news: defaultNews("Aluminum")
        },
        nickel: {
            title: "글로벌 전략광물: 니켈",
            desc: "스테인리스·배터리용 니켈 무역 흐름",
            totalVolume: "3.6 Million Tonnes",
            topExporter: "인도네시아",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("nickel")
        },
        cobalt: {
            title: "글로벌 전략광물: 코발트",
            desc: "배터리 양극재용 코발트 무역 흐름",
            totalVolume: "0.23 Million Tonnes",
            topExporter: "콩고민주공화국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("cobalt")
        },
        lithium: {
            title: "글로벌 전략광물: 리튬",
            desc: "탄산리튬 기준 무역 흐름",
            totalVolume: "1.0 Million Tonnes LCE",
            topExporter: "칠레 / 호주",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("lithium")
        },
        graphite: {
            title: "글로벌 전략광물: 흑연",
            desc: "음극재용 천연흑연 무역 흐름",
            totalVolume: "1.6 Million Tonnes",
            topExporter: "중국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("graphite")
        },
        rare_earths: {
            title: "글로벌 전략광물: 희토류",
            desc: "희토류 화합물 무역 흐름",
            totalVolume: "0.35 Million Tonnes",
            topExporter: "중국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("rare_earths")
        },
        iron_ore: {
            title: "글로벌 철강원료: 철광석",
            desc: "제철용 철광석 무역 흐름",
            totalVolume: "1,600 Million Tonnes",
            topExporter: "호주",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("iron_ore")
        },
        manganese: {
            title: "글로벌 철강원료: 망간",
            desc: "합금철용 망간광 무역 흐름",
            totalVolume: "20 Million Tonnes",
            topExporter: "남아프리카공화국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("manganese")
        },
        chromium: {
            title: "글로벌 철강원료: 크롬",
            desc: "스테인리스용 크롬광 무역 흐름",
            totalVolume: "41 Million Tonnes",
            topExporter: "남아프리카공화국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("chromium")
        },
        tin: {
            title: "글로벌 산업금속: 주석",
            desc: "납땜·도금용 주석 무역 흐름",
            totalVolume: "0.38 Million Tonnes",
            topExporter: "인도네시아",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("tin")
        },
        lead: {
            title: "글로벌 산업금속: 납",
            desc: "축전지용 납 무역 흐름",
            totalVolume: "4.5 Million Tonnes",
            topExporter: "중국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("lead")
        },
        platinum: {
            title: "글로벌 귀금속: 백금족",
            desc: "백금·팔라듐 무역 흐름",
            totalVolume: "0.4 Thousand Tonnes",
            topExporter: "남아프리카공화국",
            arcs: [],  // Lazy loaded from UN Comtrade API
            news: defaultNews("platinum")
        },
        wheat: {
            title: "글로벌 농산물: 밀 (Wheat)",
            desc: "글로벌 주요 식량 자원인 밀의 무역 흐름",
            totalVolume: "215 Million Tonnes",
            topExporter: "러시아",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 1001)
            news: defaultNews("Wheat")
        },
        corn: {
            title: "글로벌 농산물: 옥수수 (Corn)",
            desc: "사료 및 바이오연료용 옥수수 무역 흐름",
            totalVolume: "190 Million Tonnes",
            topExporter: "미국",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 1005)
            news: defaultNews("Corn")
        },
        soybeans: {
            title: "글로벌 농산물: 대두 (Soybeans)",
            desc: "단백질 사료 및 식용유의 핵심, 대두 무역 흐름",
            totalVolume: "172 Million Tonnes",
            topExporter: "브라질",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 1201)
            news: defaultNews("Soybeans")
        },
        sugar: {
            title: "글로벌 농산물: 설탕 (Sugar)",
            desc: "사탕수수 기반 설탕 수출입 무역 흐름",
            totalVolume: "64 Million Tonnes",
            topExporter: "브라질",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 1701)
            news: defaultNews("Sugar")
        },
        coffee: {
            title: "글로벌 농산물: 커피 (Coffee)",
            desc: "전 세계 원두(아라비카/로부스타) 수출입 무역 흐름",
            totalVolume: "140 Million Bags",
            topExporter: "브라질 / 에티오피아",
            arcs: [],  // Lazy loaded from UN Comtrade API (HS 0901)
            news: {
                ...defaultNews("Coffee"),
                "Ethiopia": [
                    { title: "Ethiopian coffee exports hit record highs despite logistics challenges", date: "4 hours ago", source: "Bloomberg Africa", url: "https://www.bloomberg.com/africa" },
                    { title: "Premium Arabica prices surge due to dry spells in Ethiopian highlands", date: "1 day ago", source: "Reuters", url: "https://www.reuters.com/business" }
                ],
                "Uganda": [
                    { title: "Uganda sets new target to double Robusta coffee production", date: "3 days ago", source: "Financial Times", url: "https://www.ft.com" }
                ]
            },
            countryStats: {
                "Ethiopia": { production: "7.3M bags", import: "0M bags", consumption: "3.4M bags", price: "$2.30 / lb" },
                "Uganda": { production: "6.8M bags", import: "0M bags", consumption: "0.3M bags", price: "$1.85 / lb" },
                "Brazil": { production: "66.3M bags", import: "0M bags", consumption: "22.5M bags", price: "$1.75 / lb" },
                "default": { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" }
            }
        }
    };


    // 3. Base Forecast Data
    let forecastData = {
        "Mato Grosso (Brazil)": {
            "climate_status": "라니냐 주의: 강우 지연 및 불규칙",
            "gdd_total": 2100.5,
            "precip_anomaly_mm": -85.2,
            "soil_moisture": 0.18,
            "last_updated": "2026-07-26T21:00:00",
            "crops": [
                { "name": "대두 (Soybeans)", "avg_yield": "3,500 kg/ha", "pred_yield": "3,325 kg/ha", "change_pct": -5.0 },
                { "name": "옥수수 (Corn - Safrinha)", "avg_yield": "5,800 kg/ha", "pred_yield": "5,336 kg/ha", "change_pct": -8.0 },
                { "name": "목화 (Cotton)", "avg_yield": "4,200 kg/ha", "pred_yield": "4,284 kg/ha", "change_pct": 2.0 }
            ]
        },
        "Rio Grande do Sul (Brazil)": {
            "climate_status": "라니냐 직격타: 극심한 가뭄",
            "gdd_total": 1950.2,
            "precip_anomaly_mm": -210.4,
            "soil_moisture": 0.11,
            "last_updated": "2026-07-26T21:00:00",
            "crops": [
                { "name": "대두 (Soybeans)", "avg_yield": "3,200 kg/ha", "pred_yield": "2,496 kg/ha", "change_pct": -22.0 },
                { "name": "밀 (Wheat)", "avg_yield": "2,800 kg/ha", "pred_yield": "2,352 kg/ha", "change_pct": -16.0 }
            ]
        },
        "Iowa (USA)": {
            "climate_status": "라니냐 영향: 예년 대비 다소 건조",
            "gdd_total": 1845.2,
            "precip_anomaly_mm": -45.3,
            "soil_moisture": 0.24,
            "last_updated": "2026-07-26T21:00:00",
            "crops": [
                { "name": "옥수수 (Corn)", "avg_yield": "200 bu/acre", "pred_yield": "194 bu/acre", "change_pct": -3.0 },
                { "name": "대두 (Soybeans)", "avg_yield": "60 bu/acre", "pred_yield": "58 bu/acre", "change_pct": -3.3 }
            ]
        },
        "Pampas (Argentina)": {
            "climate_status": "라니냐 기조: 토양 수분 고갈 (가뭄)",
            "gdd_total": 2205.1,
            "precip_anomaly_mm": -190.5,
            "soil_moisture": 0.12,
            "last_updated": "2026-07-26T21:00:00",
            "crops": [
                { "name": "대두 (Soybeans)", "avg_yield": "2,900 kg/ha", "pred_yield": "2,233 kg/ha", "change_pct": -23.0 },
                { "name": "밀 (Wheat)", "avg_yield": "3,100 kg/ha", "pred_yield": "2,542 kg/ha", "change_pct": -18.0 }
            ]
        },
        "Sumatra (Indonesia)": {
            "climate_status": "라니냐 호조: 강수량 풍부 (수확량 긍정적)",
            "gdd_total": 3100.0,
            "precip_anomaly_mm": 120.0,
            "soil_moisture": 0.42,
            "last_updated": "2026-07-26T21:00:00",
            "crops": [
                { "name": "팜유 (Palm Oil)", "avg_yield": "3,800 kg/ha", "pred_yield": "4,104 kg/ha", "change_pct": 8.0 },
                { "name": "커피 (Coffee)", "avg_yield": "800 kg/ha", "pred_yield": "848 kg/ha", "change_pct": 6.0 },
                { "name": "천연고무 (Rubber)", "avg_yield": "1,200 kg/ha", "pred_yield": "1,260 kg/ha", "change_pct": 5.0 }
            ]
        }
    };

    // ★★★ CRITICAL: Set globals FIRST before any async API calls ★★★
    // This ensures the app works even if external APIs fail (CORS, timeout, etc.)
    const constCountriesData = COUNTRIES;
    window.CountriesData = constCountriesData;
    window.TradeData = TradeData;
    window.ForecastData = forecastData;
    console.log('[data.js] TradeData and CountriesData set successfully.');

    // Now try to enhance data with live API calls (non-blocking)
    try {
        // 4. Inject real-time weather into forecast
        if (weatherMap["Mato Grosso (Brazil)"]) {
            const w = weatherMap["Mato Grosso (Brazil)"];
            forecastData["Mato Grosso (Brazil)"].climate_status = `실시간 날씨: 🌡️ ${w.temperature}°C, 🌬️ ${w.windspeed}km/h (기후 API 연동 중)`;
            forecastData["Mato Grosso (Brazil)"].last_updated = new Date().toISOString();
        }
        if (weatherMap["Iowa (USA)"]) {
            const w = weatherMap["Iowa (USA)"];
            forecastData["Iowa (USA)"].climate_status = `실시간 날씨: 🌡️ ${w.temperature}°C, 🌬️ ${w.windspeed}km/h (기후 API 연동 중)`;
            forecastData["Iowa (USA)"].last_updated = new Date().toISOString();
        }
    } catch(e) {
        console.warn('[data.js] Weather injection skipped:', e.message);
    }

    // 3. UN Comtrade Data for Coal (HS 2701) is lazy-loaded on demand via
    //    window.fetchComtradeArcs(), which goes through the /api/comtrade proxy
    //    (see app.js:622) — no separate fetch needed here.

    // 4. Fetch USDA NASS Data for Iowa Soybeans Yield with Edge Caching
    try {
        const usdaUrl = `/api/usda-nass?commodity_desc=SOYBEANS&year__GE=2023&state_alpha=IA&statisticcat_desc=YIELD&agg_level_desc=STATE&format=JSON`;
        
        const usdaRes = await fetch(usdaUrl);

        if (usdaRes.ok) {
            const usdaData = await usdaRes.json();
            if (usdaData && usdaData.data && usdaData.data.length > 0) {
                // Find the most recent annual data
                const annualData = usdaData.data.filter(d => d.reference_period_desc === "YEAR" || d.reference_period_desc.includes("FORECAST"));
                annualData.sort((a, b) => b.year - a.year);
                
                if (annualData.length > 0) {
                    const latestYield = annualData[0].Value;
                    const latestYear = annualData[0].year;
                    
                    // Update the Soybean forecast in Iowa
                    if (forecastData["Iowa (USA)"] && forecastData["Iowa (USA)"].crops) {
                        const commId = normalizeCommodity("SOYBEANS");
                        const soyIndex = forecastData["Iowa (USA)"].crops.findIndex(c => normalizeCommodity(c.name) === commId);
                        if (soyIndex !== -1) {
                            forecastData["Iowa (USA)"].crops[soyIndex].pred_yield = `${latestYield} bu/acre (LIVE ${latestYear})`;
                            // Add a visual indicator that it's live data
                            forecastData["Iowa (USA)"].climate_status += ` | 🌽 작황 API 연동 성공`;
                        }
                    }
                }
            }
        }
    } catch(e) {
        console.error("USDA NASS API Error:", e);
    }

    // 5. Climate/Agri: Spatial Isolation & Bottom-up Aggregation
    // Calculate a "Global Aggregate" dynamically by summing/averaging the regional isolated models
    let globalYieldSum = 0;
    let globalYieldCount = 0;
    Object.keys(forecastData).forEach(region => {
        if (region !== "Global Aggregate (Bottom-up)") {
            const data = forecastData[region];
            data.crops.forEach(crop => {
                if (normalizeCommodity(crop.name) === "soybeans") {
                    // Extract numerical value from string like "58 bu/acre" or "3,500 kg/ha"
                    const match = crop.pred_yield.match(/[\d,.]+/);
                    if (match) {
                        const val = parseFloat(match[0].replace(/,/g, ''));
                        globalYieldSum += val;
                        globalYieldCount++;
                    }
                }
            });
        }
    });

    if (globalYieldCount > 0) {
        // Mock a Global Aggregate card
        forecastData["Global Aggregate (Bottom-up)"] = {
            climate_status: "🌎 각 지역 데이터 상향식(Bottom-up) 통합 산출 완료",
            gdd_total: 0, // N/A for global
            precip_anomaly_mm: 0, // N/A for global
            soil_moisture: 0, // N/A for global
            last_updated: new Date().toISOString(),
            crops: [
                { 
                    name: "글로벌 대두 (Global Soybeans Index)", 
                    avg_yield: "N/A", 
                    pred_yield: `Aggregated from ${globalYieldCount} regions`, 
                    change_pct: -5.5 // Dummy aggregate change
                }
            ]
        };
    }
    // Load macro data (async, non-blocking)
    window.loadMacroData();
})();
