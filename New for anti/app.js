// Application Logic for Global Trade Dashboard
const { DeckGL, LineLayer, ArcLayer, ScatterplotLayer, GeoJsonLayer, _GlobeView, MapView } = deck;

// DOM Elements
const tooltipEl = document.getElementById('tooltip');
const newsContentEl = document.getElementById('news-content');
const newsPanelEl = document.getElementById('news-panel');
const forecastPanelEl = document.getElementById('climate-forecast-panel');
const forecastContentEl = document.getElementById('forecast-content');
const forecastCountryTitle = document.getElementById('forecast-country-title');

// Right panel elements
const macroPanelEl = document.getElementById('macro-panel');
const countryStatsPanelEl = document.getElementById('country-stats-panel');
const countryStatsTitleEl = document.getElementById('country-stats-title');
const countryStatsContentEl = document.getElementById('country-stats-content');

const totalVolumeEl = document.getElementById('total-volume');
const topExporterEl = document.getElementById('top-exporter');
const currentViewTitle = document.getElementById('current-view-title');
const currentViewDesc = document.getElementById('current-view-desc');
const mapContainer = document.getElementById('map');
const chartView = document.getElementById('chart-view');
const navLinks = document.querySelectorAll('.dropdown a');

// State management
let selectedCountry = null;
let currentCommodity = null; // 'coal', 'oil', 'gold', 'climate'
let forecastData = {};

window.initApp = function() {
    forecastData = window.ForecastData || {};
    if (window.MacroData) {
        updateMacroPanel(window.MacroData);
    }
};

if (window.MacroData) {
    window.initApp();
}

// Update Macro Panel with FRED Data
const updateMacroPanel = (macro) => {
    const formatVal = (id, val) => {
        if (!val || val === "N/A") return "N/A";
        const num = parseFloat(val);
        if (id === "EUR/USD" || id === "USD/JPY") return num.toFixed(4);
        if (id === "NASDAQ") return num.toLocaleString();
        if (id === "WTI_OIL") {
            if (isNaN(num)) return val;
            return `$${num.toFixed(2)}`;
        }
        if (id === "NAT_GAS") {
            if (isNaN(num)) return val;
            return `$${num.toFixed(3)}`; // Natural Gas prices are typically quoted to 3 decimal places (e.g. $2.145)
        }
        if (id === "FED_BS") return `$${(num / 1000000).toFixed(2)} Trillion`;
        if (id === "TGA") return `$${(num / 1000).toFixed(0)} Billion`;
        if (id === "KRW_USD") return `${num.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} 원`;
        if (id === "BOK_RATE") return `${num.toFixed(2)}%`;
        return val;
    };

    if(macro["EUR/USD"]) document.getElementById('macro-eur-usd').innerText = formatVal("EUR/USD", macro["EUR/USD"].value);
    if(macro["USD/JPY"]) document.getElementById('macro-usd-jpy').innerText = formatVal("USD/JPY", macro["USD/JPY"].value);
    if(macro["NASDAQ"]) document.getElementById('macro-nasdaq').innerText = formatVal("NASDAQ", macro["NASDAQ"].value);
    if(macro["WTI_OIL"]) document.getElementById('macro-wti').innerText = formatVal("WTI_OIL", macro["WTI_OIL"].value);
    if(macro["NAT_GAS"]) document.getElementById('macro-natgas').innerText = formatVal("NAT_GAS", macro["NAT_GAS"].value);
    if(macro["FED_BS"]) {
        document.getElementById('macro-fed-bs').innerText = formatVal("FED_BS", macro["FED_BS"].value);
        document.getElementById('macro-fed-bs-date').innerText = `최근 업데이트: ${macro["FED_BS"].date}`;
    }
    if(macro["TGA"]) {
        document.getElementById('macro-tga').innerText = formatVal("TGA", macro["TGA"].value);
        document.getElementById('macro-tga-date').innerText = `최근 업데이트: ${macro["TGA"].date}`;
    }
    if(macro["KRW_USD"]) document.getElementById('macro-krw-usd').innerText = formatVal("KRW_USD", macro["KRW_USD"].value);
    if(macro["BOK_RATE"]) document.getElementById('macro-bok-rate').innerText = formatVal("BOK_RATE", macro["BOK_RATE"].value);
};

// Deck.GL Map Initialization
const mapStyle = {
    "version": 8,
    "sources": {
        "carto-dark": {
            "type": "raster",
            "tiles": [
                "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
                "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png"
            ],
            "tileSize": 256
        }
    },
    "layers": [
        {
            "id": "carto-dark-layer",
            "type": "raster",
            "source": "carto-dark",
            "minzoom": 0,
            "maxzoom": 22
        }
    ]
};

// Home globe zoom. Higher = the sphere fills more of the viewport, so the
// horizon curve reads as a gentle bend rather than a small ball in space.
const GLOBE_ZOOM = 2.5;

let currentViewState = {
    longitude: 0,
    latitude: 20,
    zoom: GLOBE_ZOOM,
    pitch: 0,
    bearing: 0
};

let autoRotate = true;
let rotationAnimation = null;
let resumeRotationTimer = null;

// One animation frame of spin. Never call directly -- go through startRotation()
// so we can't end up with several chains running at once.
const rotationStep = () => {
    if (!autoRotate || currentCommodity !== 'home') {
        rotationAnimation = null;
        return;
    }
    currentViewState = {
        ...currentViewState,
        longitude: currentViewState.longitude + 0.05 // 서서히 자전
    };
    deckgl.setProps({ viewState: currentViewState });
    rotationAnimation = requestAnimationFrame(rotationStep);
};

const startRotation = () => {
    // Bail if a chain is already live. onViewStateChange fires on every frame of
    // a drag, so without this one drag would spawn dozens of parallel loops and
    // the globe would spin faster and faster.
    if (rotationAnimation !== null) return;
    autoRotate = true;
    rotationAnimation = requestAnimationFrame(rotationStep);
};

const stopRotation = () => {
    autoRotate = false;
    if (rotationAnimation !== null) {
        cancelAnimationFrame(rotationAnimation);
        rotationAnimation = null;
    }
};

// Initialize DeckGL Map
const deckgl = new DeckGL({
    container: 'map',
    mapStyle: mapStyle,
    initialViewState: currentViewState,
    controller: true,
    views: [new _GlobeView({ id: 'globe', resolution: 2 })], // Start with GlobeView
    layers: [],
    onViewStateChange: ({ viewState, interactionState }) => {
        currentViewState = viewState;
        deckgl.setProps({ viewState: currentViewState });

        // 드래그로 지구를 직접 잡고 있을 때만 회전 멈춤.
        // Zooming is deliberately excluded: scrolling to resize the globe should
        // not stop the spin, and rotationStep preserves whatever zoom the user
        // lands on. Debounced -- this fires once per interaction frame, so
        // re-arm a single timer instead of queueing one per frame.
        if (interactionState.isDragging) {
            stopRotation();
            clearTimeout(resumeRotationTimer);
            resumeRotationTimer = setTimeout(() => {
                if (currentCommodity === 'home') startRotation();
            }, 2000);
        }
    }
});

// Tooltip handler
const handleHover = (info) => {
    if (info.object) {
        const { sourceName, targetName, volume, percentage } = info.object;
        tooltipEl.style.left = `${info.x}px`;
        tooltipEl.style.top = `${info.y}px`;
        tooltipEl.classList.remove('hidden');
        
        tooltipEl.innerHTML = `
            <div class="tooltip-title">${sourceName} → ${targetName}</div>
            <div class="tooltip-stat">
                <span>무역량:</span>
                <span style="color: #38bdf8; font-weight: bold;">${volume} ${currentCommodity === 'oil' ? 'M bpd' : (currentCommodity === 'gold' || currentCommodity === 'silver' ? 'Tonnes' : 'Mt')}</span>
            </div>
            ${info.object.typeName !== "General" ? `
            <div class="tooltip-stat">
                <span>분류:</span>
                <span>${info.object.typeName}</span>
            </div>` : ''}
            <div class="tooltip-stat">
                <span>비중/상대규모:</span>
                <span>${percentage}%</span>
            </div>
        `;
    } else {
        tooltipEl.classList.add('hidden');
    }
};

const handleNodeClick = (info) => {
    if (info.object) {
        selectedCountry = info.object.name;
        if (currentCommodity === 'climate') {
            updateForecastPanel(selectedCountry).catch(err =>
                console.error('[Forecast] panel update failed', err));
        } else {
            updateNewsPanel(selectedCountry);
            updateCountryStatsPanel(selectedCountry);
        }
    }
};

const handleLineClick = (info) => {
    if (info.object) {
        selectedCountry = info.object.sourceName;
        if (currentCommodity === 'climate') {
            updateForecastPanel(selectedCountry).catch(err =>
                console.error('[Forecast] panel update failed', err));
        } else {
            updateNewsPanel(selectedCountry);
            updateCountryStatsPanel(selectedCountry);
        }
    }
};

const updateCountryStatsPanel = async (countryName) => {
    if (!currentCommodity || !window.TradeData[currentCommodity]) return;
    
    const commodityData = window.TradeData[currentCommodity];
    let statsData = commodityData.countryStats ? 
        (commodityData.countryStats[countryName] || commodityData.countryStats['default']) : 
        { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A", endingStocks: "N/A" };
        
    // --- LIVE OVERRIDE FOR CHINA (USDA PSD) ---
    let dataSourceText = "UN FAO / World Bank (Mock)";
    if (countryName === "China" && currentCommodity === "soybeans") {
        try {
            const res = await fetch('/public/data/live_override.json');
            if (res.ok) {
                const liveData = await res.json();
                if (liveData.usda_psd && liveData.usda_psd.china_soybean) {
                    const usdaRecords = liveData.usda_psd.china_soybean;
                    
                    const endingStocks = usdaRecords.find(r => r.attribute === "estoque_final")?.value || "N/A";
                    const imports = usdaRecords.find(r => r.attribute === "importacao")?.value || "N/A";
                    
                    statsData.endingStocks = endingStocks !== "N/A" ? `${endingStocks.toLocaleString()} k MT` : "N/A";
                    statsData.import = imports !== "N/A" ? `${imports.toLocaleString()} k MT` : "N/A";
                    dataSourceText = "USDA PSD API (Live Data)";
                }
            }
        } catch (e) {
            console.warn("Could not load live_override.json for China stats");
        }
    }
        
    countryStatsTitleEl.textContent = countryName;
    
    countryStatsContentEl.innerHTML = `
        <div style="font-size: 11px; color: #00d2ff; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 5px;">
            <i class="fas fa-database"></i> Source: ${dataSourceText}
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">생산량 (Production)</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.production}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">수입량 (Import)</span></div>
            <div class="ind-value" style="font-size: 20px; color: ${statsData.import !== 'N/A' ? '#ff3366' : 'white'};">${statsData.import}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">소비량 (Consumption)</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.consumption}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title" style="color: #00d2ff;">식량 안보 (기말 재고량)</span></div>
            <div class="ind-value" style="font-size: 20px; color: #00d2ff; font-weight: bold;">${statsData.endingStocks || 'N/A'}</div>
        </div>
    `;
    
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.remove('hidden');
};

const updateNewsPanel = (countryName) => {
    if (!currentCommodity || !window.TradeData[currentCommodity]) return;
    
    const commodityNews = window.TradeData[currentCommodity].news;
    const newsData = commodityNews[countryName] || commodityNews['default'];
    
    if (!newsData || newsData.length === 0) {
        newsContentEl.innerHTML = `<p class="empty-state">해당 지역의 최근 뉴스가 없습니다.</p>`;
        return;
    }
    
    document.querySelector('#news-panel .section-title').textContent = `주요 지역 뉴스: ${countryName}`;
    
    newsContentEl.innerHTML = newsData.map(news => `
        <a href="${news.url}" target="_blank" rel="noopener noreferrer" class="news-item">
            <div class="news-title">${news.title}</div>
            <div class="news-meta">
                <span>${news.source}</span>
                <span>${news.date}</span>
            </div>
        </a>
    `).join('');
};

// Renders the statistical yield forecast for the US Corn Belt.
// Kept separate from the hardcoded forecastData panels: these numbers come
// from a model fitted on 33 seasons of NASA POWER weather and USDA NASS
// yields, so the panel also shows how much of the season is actually
// observed and how the model scored out of sample.
const US_REGION_KEYS = {
    'US Corn Belt': 'corn_belt',
    'US Great Plains': 'great_plains',
    'US Northern Plains': 'northern_plains',
};

// Why each region's model is shaped the way it is, and which finding drove it.
// Written per region rather than once for the country: the three share a
// skeleton (trend + weather anomaly + ridge) but differ in the physics that
// actually moves yield, and a single blurb would hide that.
const US_REGION_METHOD = {
    corn_belt: {
        headline: '추세수확량 + 기상편차 회귀',
        refs: 'Thompson (1969, 1986) · Schlenker & Roberts (2009) · Lobell / Urban / Roberts',
        notes: [
            '추세가 품종·비료·경영 개선을 흡수하고, 기상은 추세로부터의 편차만 설명합니다 (FAO 작황예측 리뷰).',
            '고온은 일수 카운트가 아니라 임계 초과분 적산(EDD)으로 넣습니다 — 손상이 비선형이기 때문입니다 (옥수수 −8.2%/°C, 대두 −5.7%/°C).',
            'VPD로 고온·건조 복합 스트레스를, 파종전 강수(9~6월)로 토양수분 충전을 봅니다.',
        ],
        finding: '데이터가 뽑아낸 상위 변수(7월 기온 r=−0.635, 7월 EDD −0.632, VPD −0.536)가 '
               + '40년 전 논문이 지목한 시기·변수와 그대로 일치했습니다.',
    },
    great_plains: {
        headline: '추세수확량 + 기상편차 회귀 (겨울밀)',
        refs: 'Kansas State (hot-dry-windy) · 대평원 겨울밀 모델링 가이드',
        notes: [
            '가을 파종 → 월동 → 초여름 수확. 생육창이 해를 넘기므로 전년 9월부터 봅니다.',
            '반건조 지대라 물이 지배합니다: 봄철 토양수분(r=+0.732), 겨울 토양수분(+0.654), 봄 강수(+0.565).',
        ],
        finding: '참고 가이드가 강조한 춘화처리·동해·서리 패널티는 신호가 없었습니다 '
               + '(r=+0.020 / −0.104 / −0.071). 서리 최다 3개년 중 2019년은 오히려 증수라 방향도 '
               + '엇갈립니다. 공식대로 구현했으나 이 지역·이 기간에서는 지배 요인이 아니었습니다.',
    },
    northern_plains: {
        headline: '추세수확량 + 기상편차 회귀 (봄밀, 20년 이동창)',
        refs: 'Lanning et al. (2010), Crop Science',
        notes: [
            '봄 파종 → 늦여름 수확. 생육창이 짧아 개화기가 한여름 폭염과 겹칩니다.',
            '밀은 옥수수보다 고온에 취약해 EDD 임계를 28°C로 낮춰 잡았습니다.',
        ],
        finding: '고정 계수로는 추세만 쓰는 것보다 나빴습니다(−1.0%). 봄밀이 조기 파종·조기출수 '
               + '품종으로 7월 더위를 회피하도록 적응해와서, "고온→감수" 관계 자체가 약해졌기 '
               + '때문입니다. 최근 20년만 재적합해 +13.4%로 돌렸습니다 — 다만 여전히 낮습니다.',
    },
};

const renderYieldForecast = async (regionName) => {
    const regionKey = US_REGION_KEYS[regionName];
    if (!regionKey) return false;

    const fc = await window.loadYieldForecast?.();
    if (!fc || !fc.regions || !fc.regions[regionKey]) return false;

    const region = fc.regions[regionKey];
    const method = US_REGION_METHOD[regionKey] || US_REGION_METHOD.corn_belt;
    let html = '';

    for (const [crop, d] of Object.entries(region.crops)) {
        const vsLast = d.point - d.last_actual.yield;
        const color = d.weather_effect < 0 ? '#fca5a5' : '#4ade80';
        const pct = Math.round(d.season_progress.observed_share * 100);

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header">
                <span class="ind-title">${d.label_ko || crop}</span>
                ${d.skill.low_confidence ? `<span style="font-size:10px; padding:2px 6px;
                   border-radius:4px; background:rgba(251,191,36,0.15); color:#fbbf24;">신뢰도 낮음</span>` : ''}
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${d.last_actual.year} 실적</span>
                    <div style="font-size:15px;">${d.last_actual.yield.toFixed(1)} ${d.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${color};">${d.point} ${d.unit}</div>
                </div>
            </div>
            <div style="text-align:right; font-size:13px; margin-top:4px; color:${vsLast >= 0 ? '#4ade80' : '#fca5a5'};">
                전년 대비 ${vsLast >= 0 ? '+' : ''}${vsLast.toFixed(1)} ${d.unit}
            </div>
            <div style="margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.1); font-size:12px;">
                <div style="display:flex; justify-content:space-between; color:#cbd5e1;">
                    <span>68% 신뢰구간</span><span>${d.range_68[0]} – ${d.range_68[1]}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:2px;">
                    <span>95% 신뢰구간</span><span>${d.range_95[0]} – ${d.range_95[1]}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>기술 추세</span><span>${d.trend} ${d.unit}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:${color}; margin-top:2px;">
                    <span>기상 효과</span><span>${d.weather_effect >= 0 ? '+' : ''}${d.weather_effect}</span>
                </div>
            </div>
            <div style="margin-top:10px; padding:8px; background:rgba(0,0,0,0.2); border-radius:6px; font-size:11px; color:#94a3b8;">
                생육 결정기 관측률 <strong style="color:#cbd5e1;">${pct}%</strong>
                (나머지는 예보·평년값)<br>
                모델 검증: 추세 대비 오차 <strong style="color:#cbd5e1;">${(d.skill.skill_vs_trend_only * 100).toFixed(0)}%</strong> 감소,
                학습 ${d.trained_years[0]}–${d.trained_years[1]}${d.skill.train_window_years ? ` · 최근 ${d.skill.train_window_years}년 이동창` : ''}
            </div>
        </div>`;
    }

    const enso = fc.enso.oni_growing_season;
    forecastCountryTitle.textContent = `${region.label_ko} 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">엘니뇨/라니냐 (ONI)</span>
                <span class="forecast-val">${enso === null ? 'N/A' : enso.toFixed(2)} · ${fc.enso.state}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:11px;">${region.note}</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>${method.headline}</strong><br>
                <span style="font-size:11px; font-weight:400;">
                기술 추세가 품종·비료·경영 개선을 흡수하고, 기상은 추세로부터의 편차를 설명합니다.
                </span>
            </div>
        </div>

        <div style="margin-top:14px; padding:10px; background:rgba(0,0,0,0.2); border-radius:6px;">
            <div style="font-size:11px; color:#94a3b8; margin-bottom:6px;">모델 설계 근거</div>
            <div style="font-size:11px; color:#64748b; margin-bottom:8px;">${method.refs}</div>
            <ul style="margin:0; padding-left:16px; font-size:11px; color:#cbd5e1; line-height:1.7;">
                ${method.notes.map(n => `<li>${n}</li>`).join('')}
            </ul>
            <div style="margin-top:10px; padding-top:8px; border-top:1px dashed rgba(255,255,255,0.1);
                        font-size:11px; color:#94a3b8; line-height:1.7;">
                <strong style="color:#cbd5e1;">검증에서 확인된 것</strong><br>${method.finding}
            </div>
        </div>

        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-top:10px; margin-bottom:4px;">
            갱신: ${new Date(fc.generated_at).toLocaleString()}
        </p>
        <p style="font-size:11px; color:#64748b; text-align:right;">
            출처: USDA NASS(수확량) · NASA POWER(기상) · NOAA CPC(ONI) · Open-Meteo(예보)
        </p>`;

    countryStatsTitleEl.textContent = region.label_ko;
    document.getElementById('country-stats-desc').textContent = method.refs;
    countryStatsContentEl.innerHTML = html;
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.remove('hidden');
    return true;
};

// Which model keys belong to each clickable Brazilian region on the map.
// One region shows several crops because the models are built per region-crop:
// Mato Grosso soy and safrinha corn are separate methodologies over the same
// ground, and the southern states carry three crops on one weather history.
// === Climate view: country -> producing region drill-down ===
//
// The climate map is two levels. Level 1 shows the world with modelled
// countries outlined; level 2 zooms into one country and marks its producing
// regions. Only countries that actually have a fitted model appear -- putting
// a marker on a country with no model would imply a forecast that does not
// exist.
const CLIMATE_COUNTRIES = {
    'United States': {
        label: '미국',
        iso: 'USA',
        view: { longitude: -96.0, latitude: 39.5, zoom: 3.6 },
        summaryKey: 'us',
        // Each entry maps to a region key in yield_forecast.json. Wheat sits
        // apart from the Corn Belt because it is a different geography with
        // its own states and weights.
        regions: [
            { name: 'US Corn Belt', label: '콘벨트 (옥수수·대두)',
              coordinates: [-91.0, 41.5], regionKey: 'corn_belt' },
            { name: 'US Great Plains', label: '대평원 (겨울밀)',
              coordinates: [-99.0, 38.0], regionKey: 'great_plains' },
            { name: 'US Northern Plains', label: '북부대평원 (봄밀)',
              coordinates: [-100.5, 47.0], regionKey: 'northern_plains' },
        ],
    },
    'Brazil': {
        label: '브라질',
        iso: 'BRA',
        view: { longitude: -52.0, latitude: -13.0, zoom: 3.6 },
        summaryKey: 'brazil',
        // Coordinates are stated here rather than looked up in CountriesData:
        // that map is built for trade routes and is missing several of these
        // producing regions, which silently dropped their markers.
        regions: [
            { name: 'Mato Grosso (Brazil)', label: '마투그로수 (대두·옥수수)', coordinates: [-55.4, -12.6] },
            { name: 'Rio Grande do Sul (Brazil)', label: '파라나·히우그란지두술', coordinates: [-52.3, -27.0] },
            { name: 'MATOPIBA (Brazil)', label: 'MATOPIBA (대두·면화)', coordinates: [-45.5, -10.5] },
            { name: 'Sao Paulo (Brazil)', label: '상파울루 (사탕수수·커피)', coordinates: [-47.8, -21.4] },
        ],
    },
};

// Which level the climate view is currently showing.
let climateLevel = 'world';
let climateCountry = null;

const BRAZIL_REGION_MODELS = {
    'Mato Grosso (Brazil)': ['mato_grosso_soja', 'mato_grosso_milho'],
    'Rio Grande do Sul (Brazil)': ['parana_soja', 'parana_milho', 'parana_trigo'],
    'MATOPIBA (Brazil)': ['matopiba_soja', 'matopiba_algodao'],
    'Sao Paulo (Brazil)': ['sp_cana', 'sp_cafe', 'sp_laranja'],
};

// Korean copy for the "not weather" callout. The model artifacts carry the
// canonical English in provenance.non_weather_drivers; this is the display
// layer, so the translation lives here rather than being duplicated into the
// JSON the pipeline writes.
const BRAZIL_NON_WEATHER_KO = {
    parana_milho:
        'SIDRA는 주별 옥수수를 1기작·2기작 합산 단일 수치로 발표합니다. 파라나는 두 작기가 모두 크고 ' +
        '재배 면적 배분이 대두·옥수수 가격에 따라 해마다 바뀌므로, 이 목표값의 연간 변동 중 일부는 ' +
        '날씨가 아니라 면적 배분 의사결정입니다. ' +
        '다만 "옥수수엔 날씨가 안 통한다"는 뜻은 아닙니다 — 방향은 대두와 같습니다. 같은 지역 ' +
        '탈추세 로그수확량으로 옥수수·대두 상관을 재보면 +0.70이고, 옥수수 자체 기상 피처(VPD_peak ' +
        '−0.52, SPI3_Jan +0.42)도 농학적으로 맞는 방향으로 옥수수 수확량을 움직입니다. 그런데 ' +
        '같은 기상 변수가 옥수수 자기 수확량보다 대두 수확량과 더 강하게 상관됩니다(−0.61, +0.59). ' +
        '즉 옥수수 목표값엔 진짜 날씨 신호가 있고, 그 위에 비기상 잡음이 얹혀 있는 것이지, 날씨가 ' +
        '이 작물을 안 움직이는 게 아닙니다.',
    sp_cana:
        '사탕수수는 5~7년에 한 번만 갱신하는 ratoon(그루터기) 작물이라, 특정 해의 수확량은 상당 부분 ' +
        '식재 연차 구성(상파울루 면적 중 1번지기 대 5번지기 비율)에 좌우됩니다. 이는 갱신 투자·품종 ' +
        '교체·제당공장 경제성이 정하는 값이며 어떤 기상 데이터에도 나타나지 않습니다. ' +
        '이건 이 모델의 한계가 아니라 학계의 정설입니다 — Dias & Sentelhas(2017)가 표준 시뮬레이터 ' +
        '3종(FAO-AZM·DSSAT/CANEGRO·APSIM)을 브라질 상업 포장에 적용했을 때 MAE 29 t/ha 초과, ' +
        'R² 0.54 미만이었고, 원인을 "경영을 반영하는 계수의 부재"로 지목했습니다. 그루터기 감퇴 ' +
        '계수(kdec)를 넣자 MAE 13~15 t/ha, R² 0.58~0.72로 개선됐습니다. 기후만으로는 누구도 이 ' +
        '작물을 예측하지 못합니다. ' +
        '팜유·커피 같은 다른 다년생 작물과는 성격이 다른 문제입니다. 팜유의 다년성은 고정된 생리 ' +
        '시차입니다 — 가뭄이 오면 24개월 뒤 열릴 열매의 성별이 강제로 바뀌므로, 12~24개월 누적 ' +
        '수분적자를 시차로 넣으면 실제로 잡힙니다(업계 표준 관행). 사탕수수를 지배하는 그루터기 ' +
        '연차는 그런 날씨-시차 메커니즘이 아예 없습니다 — 언제 갈아엎어 재식할지의 투자 결정입니다. ' +
        '문서가 요구한 다년 누적 방식(12~18개월 수분적자, SPI-12)을 이미 넣어봤는데도 날씨만의 ' +
        '기여는 −3.1%로 그대로 마이너스였습니다. 시차를 늘려도 안 됐다는 건, 애초에 빠진 게 ' +
        '"더 긴 날씨 기억"이 아니라 "날씨로 환원 안 되는 변수"라는 뜻입니다.',
    sp_cafe:
        '해걸이(격년결실)는 기상이 아니라 생리 현상입니다. 많이 열린 해에 나무가 소진되면 이듬해는 ' +
        '날씨와 무관하게 적게 열립니다. lag1·lag2가 이 주기를 담고 있고 이 둘이 모델의 최강 피처이므로, ' +
        '이 모델 성능의 상당 부분은 기후가 아니라 생물학적 기억입니다. ' +
        'lag1·lag2를 빼고 기상 피처만 남기면 스킬이 +1.6%로 줄어듭니다(전체는 +8.6%). 서리·개화기 ' +
        '수분결핍이라는 진짜 기후 메커니즘은 있지만(문서에도 명시, 물리적으로도 잘 알려짐), 주(州) ' +
        '단위 연간 데이터에서는 해걸이 주기가 그 변동을 압도합니다. "다년 메모리를 넣었다"가 ' +
        '자동으로 "날씨가 이긴다"를 보장하진 않는다는 걸 이 작물이 가장 명확하게 보여줍니다.',
    sp_laranja:
        '이 문서는 첫 문단부터 "이 시장은 기후가 아닌 감귤 녹화병(HLB)에 의해 붕괴되고 있다"고 ' +
        '명시하며, 처방된 모델링도 드론 CNN과 공간 확산 모델이지 기상 모델이 아닙니다. 데이터도 ' +
        '같은 말을 합니다 — HLB는 나무를 죽이지 헥타르당 수확량을 낮추지 않습니다. 상파울루 오렌지 ' +
        '재배면적은 1991년 정점 대비 55% 감소(789,329→354,562 ha)했는데, 살아남은 면적의 단수는 ' +
        '2005년 이후 오히려 35% 상승했습니다. 감염목을 뽑아내면 남은 과수원이 더 젊고 관리가 좋기 ' +
        '때문입니다. 따라서 이 kg/ha 수치는 산업이 축소되는 중에도 우상향으로 보입니다. ' +
        '반드시 재배면적과 함께 읽어야 하며, 단독으로 해석하면 안 됩니다.',
    matopiba_algodao:
        '1999→2000년의 도약은 세하두 이전·신품종·규모화·경영의 생산 체계 전환이지 기상 호조가 ' +
        '아닙니다(관개가 아닙니다 — 브라질 면화 재배면적의 약 92%가 천수답이며, 천수답 섬유 단수 ' +
        '세계 1위입니다). 현대 체계 내부의 최대 비기상 요인은 목화바구미로, 최대 70%까지 감수를 ' +
        '일으키지만 그 압력은 파종기 조율과 방제 프로그램에 달려 있지 기후에 달려 있지 않습니다. ' +
        'MODIS NDVI가 면화 단수 모델에서 추세선 대비 거의 기여하지 못한다는 연구(Johnson, ORNL)도 ' +
        '있어, 위성 식생지수로 이 공백을 메우기는 어렵습니다.',
};

// Open hypotheses -- explicitly NOT established findings like the map above,
// but real gaps worth stating so a low score isn't read as "weather doesn't
// matter" when it might just mean "we're missing the right weather feature".
const BRAZIL_OPEN_QUESTIONS_KO = {
    matopiba_algodao:
        '검증되지 않은 가설입니다. 이 모델은 면화에 토양수분·근권 저류량 피처를 하나도 안 씁니다 — ' +
        '강수·폭염·VPD뿐입니다. MATOPIBA 세하두 토양은 모래질이라(대두 모델의 "유효수분용량" ' +
        '로직이 이걸 전제하지만, 그 처리는 면화가 아니라 대두에만 적용됨) 정확히 강수량만으론 ' +
        '식물이 실제 쓸 수 있는 물을 못 잡는 지역입니다. NASA POWER의 근권 토양수분(GWETROOT) — ' +
        '예전 brazil_soy_model에서 썼지만 이번 패키지에선 아예 안 불러온 변수 — 을 붙이면 비용 ' +
        '없이 바로 검증 가능합니다. 위성 토양수분(SMAP)이나 GRACE 총저류량을 더하면 더 확장됩니다.',
};

// Renders the Brazil regional yield forecasts.
//
// Deliberately shows the models that failed validation alongside the ones that
// passed, because hiding them would leave the reader assuming every number is
// weather-driven. Where `beats_trend` is false the figure is a trend
// extrapolation and is labelled as one; where a crop is moved mainly by
// something that is not weather at all -- cane's ratoon age profile, coffee's
// biennial bearing -- that reason is printed rather than left to be guessed at
// from a low score.
const renderBrazilYieldForecast = async (regionName) => {
    const keys = BRAZIL_REGION_MODELS[regionName];
    if (!keys) return false;

    const fc = await window.loadBrazilYieldForecast?.();
    if (!fc || !fc.regions) return false;

    const shown = keys.map(k => [k, fc.regions[k]]).filter(([, d]) => d);
    if (!shown.length) return false;

    const fmt = n => Math.round(n).toLocaleString();
    let html = '';

    for (const [key, d] of shown) {
        const vsLast = d.point - d.last_actual.yield;
        // The badge keys off weather skill, not the headline number. A model
        // can beat the trend on the strength of its lagged-yield features
        // while adding nothing meteorological -- São Paulo cane scores +8.2%
        // overall and -3.1% on weather alone -- and a climate panel must not
        // present that as a weather forecast.
        const skilled = d.skill.weather_driven;
        const color = d.weather_effect_pct < 0 ? '#fca5a5' : '#4ade80';
        // How much of the yield-deciding window has actually been observed.
        // Without this a mid-season projection off climatology looks identical
        // to a settled post-harvest number.
        const obsPct = d.provenance.critical_window_observed === null
            || d.provenance.critical_window_observed === undefined
            ? null
            : Math.round(d.provenance.critical_window_observed * 100);

        let badge;
        if (skilled) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(74,222,128,0.15); color:#4ade80;">검증 통과 · 기상 기여
                 ${(d.skill.weather_skill * 100).toFixed(0)}%</span>`;
        } else if (d.skill.beats_trend) {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(148,163,184,0.18); color:#cbd5e1;">추세는 이기나 기상 기여는 없음
                 (${(d.skill.non_weather_features || []).join(', ') || '비기상 요인'} 기여)</span>`;
        } else {
            badge = `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(251,191,36,0.15); color:#fbbf24;">기상 신호 없음 · 추세 외삽값</span>`;
        }

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header"><span class="ind-title">${d.label}</span></div>
            <div style="margin-top:6px;">${badge}</div>
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${d.last_actual.year} 실적</span>
                    <div style="font-size:15px;">${fmt(d.last_actual.yield)} ${d.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${skilled ? color : '#cbd5e1'};">
                        ${fmt(d.point)} ${d.unit}</div>
                </div>
            </div>
            <div style="text-align:right; font-size:13px; margin-top:4px; color:${vsLast >= 0 ? '#4ade80' : '#fca5a5'};">
                전년 대비 ${vsLast >= 0 ? '+' : ''}${fmt(vsLast)} ${d.unit}
            </div>
            <div style="margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.1); font-size:12px;">
                <div style="display:flex; justify-content:space-between; color:#cbd5e1;">
                    <span>68% 신뢰구간</span><span>${fmt(d.range_68[0])} – ${fmt(d.range_68[1])}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>기술 추세</span><span>${fmt(d.trend)} ${d.unit}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:${color}; margin-top:2px;">
                    <span>기상 효과</span>
                    <span>${d.weather_effect_pct >= 0 ? '+' : ''}${d.weather_effect_pct.toFixed(1)}%</span>
                </div>
            </div>
            ${d.provenance.non_weather_drivers ? `
            <div style="margin-top:8px; padding:8px; background:rgba(251,191,36,0.08);
                        border-left:2px solid rgba(251,191,36,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#fbbf24;">날씨가 아닌 요인</strong><br>${
                    BRAZIL_NON_WEATHER_KO[key] || d.provenance.non_weather_drivers}
            </div>` : ''}
            ${BRAZIL_OPEN_QUESTIONS_KO[key] ? `
            <div style="margin-top:8px; padding:8px; background:rgba(96,165,250,0.08);
                        border-left:2px solid rgba(96,165,250,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#60a5fa;">미검증 가설 · 결측 가능성</strong><br>${
                    BRAZIL_OPEN_QUESTIONS_KO[key]}
            </div>` : ''}
            ${obsPct === null ? '' : `
            <div style="margin-top:10px; font-size:11px; color:#94a3b8;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>${d.provenance.season_complete
                        ? '수확기 종료 · 생육기 기상 확정'
                        : '생육 진행 중 · 결정 구간 관측률'}</span>
                    <span style="color:#cbd5e1;">${obsPct}%</span>
                </div>
                <div style="height:4px; background:rgba(255,255,255,0.08); border-radius:2px;">
                    <div style="height:100%; width:${obsPct}%; border-radius:2px;
                                background:${d.provenance.season_complete ? '#4ade80' : '#60a5fa'};"></div>
                </div>
            </div>`}
            <div style="margin-top:8px; padding:8px; background:rgba(0,0,0,0.2); border-radius:6px;
                        font-size:11px; color:#94a3b8;">
                기상 관측 ${d.provenance.weather_through}까지 · 방법론
                <span style="color:#cbd5e1;">${d.provenance.guide.split('/').slice(-2, -1)}</span>
            </div>
        </div>`;
    }

    const skippedNote = Object.entries(fc.skipped || {})
        .filter(([k]) => keys.includes(k))
        .map(([k]) => k);

    forecastCountryTitle.textContent = `브라질 지역 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:12px;">${regionName.replace(' (Brazil)', '')}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">작물 수</span>
                <span class="forecast-val">${shown.length}개 모델</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>지역별 개별 방법론 + 추세·기상편차 분해</strong><br>
                <span style="font-size:11px; font-weight:400;">
                지역마다 다른 수식을 씁니다. 마투그로수는 우기 시작일(Liebmann 이상누적),
                남부는 SPI·엘니뇨, 사프리냐 옥수수는 FAO-56 물수지입니다.
                </span>
            </div>
            ${skippedNote.length ? `
            <p style="font-size:11px; color:#fbbf24; margin-top:10px;">
                ${skippedNote.join(', ')}: 해당 생육 단계가 아직 도래하지 않아 예측하지 않음
            </p>` : ''}
        </div>
        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-bottom:4px;">
            갱신: ${new Date(fc.generated_at).toLocaleString()}
        </p>
        <p style="font-size:11px; color:#64748b; text-align:right;">
            출처: IBGE SIDRA(주별 수확량) · NASA POWER(기상) · NOAA CPC(ONI)
        </p>`;

    countryStatsTitleEl.textContent = regionName.replace(' (Brazil)', '');
    document.getElementById('country-stats-desc').textContent =
        '기후 모델링 문서(Regions/브라질) 지역별 수식 구현 · log 추세 + 기상편차';
    countryStatsContentEl.innerHTML = html;
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.remove('hidden');
    return true;
};

// Level 1 -- the world, with modelled countries picked out.
// Countries without a fitted model are drawn but not clickable, so the map
// never suggests a forecast exists where it does not.
const showClimateWorld = () => {
    climateLevel = 'world';
    climateCountry = null;

    const modelled = new Set(Object.values(CLIMATE_COUNTRIES).map(c => c.iso));

    currentViewTitle.textContent = '기후·작황 예측';
    currentViewDesc.textContent = '모델이 있는 국가를 클릭하면 해당 국가의 산지로 들어갑니다';

    deckgl.setProps({
        views: [new MapView({ id: 'mapview' })],
        viewState: { longitude: 0, latitude: 20, zoom: 1.5, pitch: 0, bearing: 0 },
        layers: [
            new GeoJsonLayer({
                id: 'climate-countries',
                data: 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json',
                stroked: true,
                filled: true,
                lineWidthMinPixels: 1,
                getFillColor: f => modelled.has(f.id)
                    ? [56, 189, 248, 90]      // modelled: highlighted
                    : [30, 41, 59, 40],       // everything else: context only
                getLineColor: f => modelled.has(f.id)
                    ? [56, 189, 248, 220]
                    : [255, 255, 255, 45],
                pickable: true,
                autoHighlight: true,
                highlightColor: [56, 189, 248, 160],
                onClick: info => {
                    const entry = Object.entries(CLIMATE_COUNTRIES)
                        .find(([, c]) => c.iso === info.object?.id);
                    if (entry) showClimateCountry(entry[0]);
                },
            }),
        ],
    });

    renderClimateWorldPanel(modelled);
};

const renderClimateWorldPanel = () => {
    forecastCountryTitle.textContent = '기후·작황 예측';
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div style="font-size:12px; color:#cbd5e1; line-height:1.7;">
                지도에서 <strong style="color:#38bdf8;">파란색으로 표시된 국가</strong>를
                클릭하면 해당 국가의 주요 산지와 올해 작황 전망을 볼 수 있습니다.
            </div>
            <div style="margin-top:14px;">
                ${Object.entries(CLIMATE_COUNTRIES).map(([k, c]) => `
                <div class="forecast-item" style="display:flex; justify-content:space-between; cursor:pointer;"
                     onclick="showClimateCountry('${k}')">
                    <span>${c.label}</span>
                    <span style="color:#94a3b8; font-size:12px;">${c.regions.length}개 산지 →</span>
                </div>`).join('')}
            </div>
        </div>
        <p style="font-size:11px; color:#64748b; text-align:right; margin-top:8px;">
            모델이 검증된 국가만 표시됩니다
        </p>`;
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.add('hidden');
};

// Level 2 -- one country, with its producing regions marked.
// The world layer stays underneath so the country is seen in context rather
// than floating on an empty canvas.
const showClimateCountry = async (countryName) => {
    const cfg = CLIMATE_COUNTRIES[countryName];
    if (!cfg) return;

    climateLevel = 'country';
    climateCountry = countryName;

    const points = cfg.regions.map(r => ({
        ...r,
        coordinates: r.coordinates || window.CountriesData[r.name],
    })).filter(r => r.coordinates);

    currentViewTitle.textContent = `${cfg.label} 작황 예측`;
    currentViewDesc.textContent = '산지를 클릭하면 전년 실적·올해 전망·모델 성능을 확인할 수 있습니다';

    deckgl.setProps({
        views: [new MapView({ id: 'mapview' })],
        viewState: { ...cfg.view, pitch: 0, bearing: 0 },
        layers: [
            new GeoJsonLayer({
                id: 'climate-countries',
                data: 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json',
                stroked: true,
                filled: true,
                lineWidthMinPixels: 1,
                // The selected country is lifted out of the background rather
                // than the rest being hidden, so it reads as "zoomed in on the
                // world map", not "a different map".
                getFillColor: f => f.id === cfg.iso ? [56, 189, 248, 55] : [30, 41, 59, 70],
                getLineColor: f => f.id === cfg.iso ? [56, 189, 248, 230] : [255, 255, 255, 35],
                pickable: false,
            }),
            new ScatterplotLayer({
                id: 'climate-regions',
                data: points,
                pickable: true,
                stroked: true,
                filled: true,
                opacity: 0.9,
                radiusMinPixels: 9,
                radiusMaxPixels: 26,
                lineWidthMinPixels: 2,
                getPosition: d => d.coordinates,
                getRadius: 90000,
                getFillColor: [250, 204, 21, 220],
                getLineColor: [255, 255, 255],
                autoHighlight: true,
                highlightColor: [255, 255, 255, 220],
                onClick: info => {
                    if (info.object) updateForecastPanel(info.object.name);
                },
            }),
        ],
    });

    renderCountryPanel(cfg);
};
window.showClimateCountry = showClimateCountry;

const renderCountryPanel = async (cfg) => {
    forecastCountryTitle.textContent = `${cfg.label} 주요 산지`;

    let rows = '';
    if (cfg.summaryKey === 'us') {
        const fc = await window.loadYieldForecast?.();
        if (fc && fc.regions) {
            // Grouped by region so wheat is not read as part of the Corn Belt.
            rows = Object.values(fc.regions).map(region => {
                const crops = Object.values(region.crops).map(d => {
                    const diff = d.point - d.last_actual.yield;
                    return `<div class="forecast-item" style="display:flex; justify-content:space-between;">
                        <span style="font-size:12px;">${d.label_ko}${d.skill.low_confidence
                            ? ' <span style="color:#fbbf24; font-size:10px;">(신뢰도 낮음)</span>' : ''}</span>
                        <span><strong style="color:#e2e8f0;">${d.point}</strong>
                        <span style="color:${diff >= 0 ? '#4ade80' : '#fca5a5'}; font-size:12px;">
                        ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}</span>
                        <span style="color:#64748b; font-size:11px;"> ${d.unit}</span></span>
                    </div>`;
                }).join('');
                return `<div style="margin-bottom:8px;">
                    <div style="font-size:11px; color:#64748b; margin:6px 0 2px;">${region.label_ko}</div>
                    ${crops}</div>`;
            }).join('');
        }
    } else if (cfg.summaryKey === 'brazil') {
        const fc = await window.loadBrazilYieldForecast?.();
        if (fc && fc.regions) {
            rows = Object.values(fc.regions).map(d => {
                const diff = d.point - d.last_actual.yield;
                return `<div class="forecast-item" style="display:flex; justify-content:space-between;">
                    <span style="font-size:12px;">${d.label}</span>
                    <span><strong style="color:#e2e8f0;">${Math.round(d.point).toLocaleString()}</strong>
                    <span style="color:${diff >= 0 ? '#4ade80' : '#fca5a5'}; font-size:12px;">
                    ${diff >= 0 ? '+' : ''}${Math.round(diff)}</span></span>
                </div>`;
            }).join('');
        }
    }

    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:12px; color:#94a3b8;">국가 전체 요약</span>
                <span style="font-size:11px; color:#38bdf8; cursor:pointer;"
                      onclick="showClimateWorld()">← 세계 지도</span>
            </div>
            ${rows || '<p class="empty-state">요약 데이터를 불러오지 못했습니다.</p>'}
        </div>
        <div style="margin-top:14px;">
            <div style="font-size:12px; color:#94a3b8; margin-bottom:6px;">산지 목록</div>
            ${cfg.regions.map(r => `
            <div class="forecast-item" style="display:flex; justify-content:space-between; cursor:pointer;"
                 onclick="updateForecastPanel('${r.name}')">
                <span style="font-size:12px;">${r.label}</span>
                <span style="color:#94a3b8; font-size:11px;">상세 →</span>
            </div>`).join('')}
        </div>
        <p style="font-size:11px; color:#64748b; text-align:right; margin-top:10px;">
            노란 점을 클릭해도 동일합니다
        </p>`;
    macroPanelEl.classList.add('hidden');
};
window.showClimateWorld = showClimateWorld;

const updateForecastPanel = async (regionName) => {
    if (await renderYieldForecast(regionName)) return;
    if (await renderBrazilYieldForecast(regionName)) return;

    const data = forecastData[regionName];
    forecastCountryTitle.textContent = `지역 기상 및 기후 요인: ${regionName}`;

    if (!data) {
        forecastContentEl.innerHTML = `<p class="empty-state">해당 지역의 상세 기상 예측 데이터가 없습니다. 지도에서 활성화된 지역(예: Mato Grosso)을 선택해주세요.</p>`;
        // Clear right panel
        macroPanelEl.classList.add('hidden');
        countryStatsPanelEl.classList.add('hidden');
        return;
    }
    
    // Left panel: Climate factors only
    const isGood = data.precip_anomaly_mm > 0;
    const alertClass = (data.climate_status.includes('가뭄') || data.climate_status.includes('홍수')) ? 'forecast-alert' : 'forecast-good';
    
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">적산온도(GDD)</span>
                <span class="forecast-val">${data.gdd_total} 도일</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">강수량 편차</span>
                <span class="forecast-val">${data.precip_anomaly_mm > 0 ? '+' : ''}${data.precip_anomaly_mm} mm</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">토양 수분 (0~7cm)</span>
                <span class="forecast-val">${data.soil_moisture} m³/m³</span>
            </div>
            
            <div class="${alertClass}" style="margin-top:16px;">
                <strong>${data.climate_status}</strong>
            </div>
        </div>
        <p style="font-size: 11px; color: #94a3b8; text-align: right; margin-bottom: 4px;">업데이트: ${new Date(data.last_updated).toLocaleString()}</p>
        <p style="font-size: 11px; color: #64748b; text-align: right;">출처: Open-Meteo 기상 관측망 / 기관별 과거 작황 데이터 기반 예측</p>
    `;
    
    // Right panel: Multi-crop predictions
    if (data.crops && data.crops.length > 0) {
        countryStatsTitleEl.textContent = `${regionName}`;
        // These regional figures are still hardcoded reference values, not model
        // output -- the label says so rather than claiming an AI forecast.
        document.getElementById('country-stats-desc').textContent = "지역 참고 작황 데이터 (기관 발표 기준값)";
        
        let cropHtml = '';
        data.crops.forEach(crop => {
            const isCropGood = crop.change_pct > 0;
            const sign = isCropGood ? '+' : '';
            const color = isCropGood ? '#4ade80' : '#fca5a5';
            
            // CEPEA Price UI
            let cepeaHtml = '';
            if (crop.cepea_price_usd) {
                const trendColor = crop.cepea_trend.startsWith('-') ? '#fca5a5' : '#4ade80';
                cepeaHtml = `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1);">
                    <span style="font-size:12px; color: #94a3b8;">CEPEA 현물 가격지수</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-size: 15px; color: #facc15;">$${crop.cepea_price_usd} <span style="font-size: 11px; color:#64748b;">(R$${crop.cepea_price_brl || '-'})</span></span>
                        <span style="font-size: 13px; color: ${trendColor};">${crop.cepea_trend}</span>
                    </div>
                </div>`;
            }

            // IBGE Municipalities UI
            let ibgeHtml = '';
            if (crop.ibge_top_municipalities && crop.ibge_top_municipalities.length > 0) {
                let muniList = crop.ibge_top_municipalities.map((m, idx) => `
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                        <span style="color: #cbd5e1;">${idx + 1}. ${m.city}</span>
                        <span style="color: #94a3b8;">${m.production_tonnes} 톤</span>
                    </div>
                `).join('');
                ibgeHtml = `
                <div style="margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.2); border-radius: 6px;">
                    <div style="font-size:11px; color: #94a3b8; margin-bottom: 6px;">IBGE 주요 생산 시정촌 랭킹</div>
                    <div style="font-size:12px;">${muniList}</div>
                </div>`;
            }

            cropHtml += `
            <div class="indicator-item" style="cursor: default; transform: none; border-color: rgba(255,255,255,0.1);">
                <div class="ind-header"><span class="ind-title">${crop.name}</span></div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                    <div>
                        <span style="font-size:12px; color: #94a3b8;">평균(기준)</span>
                        <div style="font-size: 15px;">${crop.avg_yield}</div>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size:12px; color: #94a3b8;">AI 예측치</span>
                        <div style="font-size: 18px; font-weight: bold; color: ${color};">${crop.pred_yield}</div>
                    </div>
                </div>
                <div style="text-align: right; font-size: 13px; margin-top:4px; color: ${color};">
                    전망: ${sign}${crop.change_pct}%
                </div>
                ${cepeaHtml}
                ${ibgeHtml}
            </div>`;
        });
        
        countryStatsContentEl.innerHTML = cropHtml;
        macroPanelEl.classList.add('hidden');
        countryStatsPanelEl.classList.remove('hidden');
    }
};

const generateNodeData = (arcs) => {
    // Collect unique countries from arcs
    const countriesSet = new Set();
    arcs.forEach(arc => {
        countriesSet.add(arc.sourceName);
        countriesSet.add(arc.targetName);
    });

    return Array.from(countriesSet).map(country => {
        let totalTrade = 0;
        arcs.forEach(arc => {
            if(arc.sourceName === country || arc.targetName === country) {
                totalTrade += arc.volume;
            }
        });
        
        const scaleFactor = (currentCommodity === 'gold') ? 50 : 20; // Reduced base scale
        return {
            name: country,
            coordinates: window.CountriesData[country],
            radius: Math.max(30000, totalTrade * scaleFactor), // Drastically reduced base radius
            totalTrade
        };
    });
};

// Cap on rendered routes. A global commodity query returns 300+ valid routes;
// this keeps the map readable without silently hiding mid-sized trade flows.
const MAX_RENDERED_ARCS = 250;

// Framing for the flat commodity map. The globe runs at GLOBE_ZOOM, which is far
// too tight for a world map, so the view has to be reset on the way in.
const FLAT_VIEW_STATE = { longitude: 0, latitude: 20, zoom: 1.5, pitch: 0, bearing: 0 };

const renderMapLayers = (arcs) => {
    // Drop only empty routes, then cap by size. The old `percentage >= 1` filter
    // discarded ~95% of real routes because one mega-route dominates each commodity.
    const filteredArcs = arcs
        .filter(arc => arc.volume > 0)
        .slice(0, MAX_RENDERED_ARCS);

    const nodeData = generateNodeData(filteredArcs);

    const arcLayer = new ArcLayer({
        id: `arc-layer-${currentCommodity}`,
        data: filteredArcs,
        pickable: true,
        getWidth: d => Math.min(Math.max(1.5, d.volume / 15), 8),
        getSourcePosition: d => d.sourcePosition,
        getTargetPosition: d => d.targetPosition,
        getSourceColor: d => d.sourceColor,
        getTargetColor: d => [56, 189, 248, 255], // Light blue target
        onHover: handleHover,
        onClick: handleLineClick,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 200]
    });

    const scatterLayer = new ScatterplotLayer({
        id: `scatter-layer-${currentCommodity}`,
        data: nodeData,
        pickable: true,
        opacity: 0.8,
        stroked: true,
        filled: true,
        radiusScale: 1,
        radiusMinPixels: 4,
        radiusMaxPixels: 30,
        lineWidthMinPixels: 1,
        getPosition: d => d.coordinates,
        getRadius: d => d.radius,
        getFillColor: [15, 23, 42],
        getLineColor: [255, 255, 255],
        onClick: handleNodeClick
    });

    const countriesLayer = new GeoJsonLayer({
        id: 'countries-layer',
        data: 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json',
        stroked: true,
        filled: false,
        lineWidthMinPixels: 1,
        getLineColor: [255, 255, 255, 80], // Bright contrast for borders
        pickable: false
    });

    deckgl.setProps({
        views: [new MapView({ id: 'mapview' })],
        layers: [countriesLayer, arcLayer, scatterLayer]
    });
};

const togglePanels = ({ macro = false, countryStats = false, news = false, forecast = false, left = true, chart = false, map = true }) => {
    const leftPaneContainer = document.getElementById('left-pane'); // Target the whole container
    const commodityInfoPanel = document.getElementById('commodity-info-panel');
    
    macro ? macroPanelEl.classList.remove('hidden') : macroPanelEl.classList.add('hidden');
    countryStats ? countryStatsPanelEl.classList.remove('hidden') : countryStatsPanelEl.classList.add('hidden');
    news ? newsPanelEl.classList.remove('hidden') : newsPanelEl.classList.add('hidden');
    forecast ? forecastPanelEl.classList.remove('hidden') : forecastPanelEl.classList.add('hidden');
    
    if (left) {
        leftPaneContainer.style.display = 'flex'; // Show the whole container
        commodityInfoPanel.classList.remove('hidden'); // Show info content
    } else {
        leftPaneContainer.style.display = 'none'; // Hide the whole left pane
        commodityInfoPanel.classList.add('hidden');
    }
    
    chart ? chartView.classList.remove('hidden') : chartView.classList.add('hidden');
    mapContainer.style.display = map ? 'block' : 'none';
};

const setView = (target) => {
    // Reset active states
    navLinks.forEach(link => link.classList.remove('active'));
    
    // Find target link
    const targetLink = document.querySelector(`[data-target="${target}"]`);
    if (targetLink) targetLink.classList.add('active');

    const coalLegend = document.getElementById('coal-legend');

    if (target === 'home') {
        // Initial empty state
        currentCommodity = 'home';
        togglePanels({ macro: true, left: false });
        
        // No GeoJson globe layer here: filled countries with a neon-blue outline
        // rendered as a distinct blue sphere sitting on top of the carto-dark
        // basemap, so the home screen showed two overlapping worlds. The
        // basemap alone already gives the rotating dark map we want.
        currentViewState = { ...currentViewState, zoom: GLOBE_ZOOM, pitch: 0, bearing: 0 };

        deckgl.setProps({
            views: [new _GlobeView({ id: 'globe', resolution: 2 })],
            viewState: currentViewState,
            layers: []
        });

        // Restart rotation
        startRotation();

    } else if (target === 'inst_intl' || target === 'inst_country') {
        currentCommodity = target;
        togglePanels({ forecast: true, left: true });
        
        deckgl.setProps({ layers: [] }); // Clear map
        
        if (target === 'inst_intl') {
            currentViewTitle.textContent = "데이터 출처: 국제 기구";
            currentViewDesc.textContent = "글로벌 거시 및 무역 지표를 제공하는 주요 국제 기구 API 현황";
            forecastCountryTitle.textContent = "국제 기구 리스트";
            forecastContentEl.innerHTML = `
                <div class="forecast-box">
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>UN Comtrade</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">전 세계 170여 개국의 수출입 통계 데이터</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>USDA (미 농무부)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">글로벌 농산물 수급 전망 (WASDE) 및 작황 데이터</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>World Bank / IMF</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">원자재 가격 지수 및 주요 거시 경제 지표</span>
                    </div>
                </div>
            `;
        } else {
            currentViewTitle.textContent = "데이터 출처: 국가별 주요 기관";
            currentViewDesc.textContent = "각 국가의 1차 데이터(Primary Data)를 제공하는 핵심 정부/공공 기관 API";
            forecastCountryTitle.textContent = "국가별 기관 리스트";
            forecastContentEl.innerHTML = `
                <div class="forecast-box">
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>CONAB (브라질 국가식량공급공사)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">브라질 대두/옥수수 생산량 및 기후 리포트</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>BCCR (아르헨티나 로사리오 곡물거래소)</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">팜파스 지역 작황 동향 및 무역 전망치</span>
                    </div>
                    <div class="forecast-item" style="display:block; margin-bottom:12px;">
                        <strong>Open-Meteo</strong><br>
                        <span style="color:#94a3b8; font-size:12px;">전 세계 고해상도 실시간 기상/기후 API</span>
                    </div>
                </div>
            `;
        }
        
        totalVolumeEl.textContent = "API / Data Sources";
        topExporterEl.textContent = "-";
    } else if (target === 'climate') {
        currentCommodity = 'climate';
        togglePanels({ forecast: true, left: true });
        
        currentViewTitle.textContent = "AI 작황 예측 (주요 산지별 다중 작물)";
        currentViewDesc.textContent = "미국 콘벨트는 통계 작황 모델 예측, 그 외 지역은 기관 발표 참고값";
        totalVolumeEl.textContent = "US Corn Belt Model";
        topExporterEl.textContent = "Trend + Weather Anomaly";
        
        showClimateWorld();

    } else if (window.TradeData[target]) {
        // Render a supported commodity map
        currentCommodity = target;
        const data = window.TradeData[target];
        
        togglePanels({ news: true, left: true });
        
        // Update Panel Info
        currentViewTitle.textContent = data.title;
        totalVolumeEl.textContent = data.totalVolume;
        topExporterEl.textContent = data.topExporter;

        // Reset news and map
        updateNewsPanel('Global Market');

        // Lazy Loading: if arcs are empty, fetch real data from UN Comtrade
        if (data.arcs.length === 0 && window.fetchComtradeArcs) {
            currentViewDesc.textContent = "📡 UN Comtrade API에서 실시간 무역 데이터 로딩 중...";
            
            // Leaving the globe behind: commodity views are always the flat map.
            // Switch immediately so the user sees the map while data loads,
            // instead of staring at a spinning globe for several seconds.
            stopRotation();
            currentViewState = { ...FLAT_VIEW_STATE };
            deckgl.setProps({
                views: [new MapView({ id: 'mapview' })],
                viewState: currentViewState,
                layers: [
                    new GeoJsonLayer({
                        id: 'countries-layer',
                        data: 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json',
                        stroked: true,
                        filled: false,
                        lineWidthMinPixels: 1,
                        getLineColor: [255, 255, 255, 80],
                        pickable: false
                    })
                ]
            });

            window.fetchComtradeArcs(target).then(arcs => {
                // Check if user hasn't navigated away
                if (currentCommodity !== target) return;
                
                if (arcs.length > 0) {
                    data.arcs = arcs; // Cache for future clicks
                    currentViewDesc.textContent = data.desc + ` (데이터 출처: UN Comtrade API | ${arcs.length}개 무역 루트)`;
                    renderMapLayers(data.arcs);
                } else {
                    currentViewDesc.textContent = data.desc + " (UN Comtrade 데이터 로딩 실패 — 재시도 필요)";
                }
            }).catch(err => {
                if (currentCommodity !== target) return;
                currentViewDesc.textContent = data.desc + " (API 연결 오류: " + err.message + ")";
                console.error('[Comtrade] Lazy load error:', err);
            });
        } else {
            // Already have data (cached from previous click or hardcoded)
            stopRotation();
            currentViewState = { ...FLAT_VIEW_STATE };
            deckgl.setProps({ viewState: currentViewState });
            currentViewDesc.textContent = data.desc + ` (데이터 출처: UN Comtrade API | ${data.arcs.length}개 무역 루트)`;
            renderMapLayers(data.arcs);
        }

    } else {
        // Unsupported/Placeholder view
        currentCommodity = null;
        togglePanels({ chart: true, left: false, map: false });
        
        const categoryName = targetLink ? targetLink.textContent : target;
        currentViewTitle.textContent = `데이터 준비 중: ${categoryName}`;
        currentViewDesc.textContent = "API 연동 및 백엔드 파이프라인 구축 후 제공됩니다.";
        
        // Update placeholder text
        chartView.innerHTML = `
            <div class="placeholder-content">
                <h3>${categoryName} 시각화 준비 중</h3>
                <p>상단 메뉴에서 원자재, 에너지, 농산물 등 지원되는 상품을 선택해 보세요.</p>
            </div>
        `;
    }
};

// ==========================================
// 6. Chart.js Modal Logic for Macro Indicators
// ==========================================
const chartModal = document.getElementById('chart-modal');
const closeModal = document.getElementById('close-modal');
const modalTitle = document.getElementById('modal-chart-title');
let macroChartInstance = null;

const openChartModal = async (indicatorTitle) => {
    modalTitle.textContent = `${indicatorTitle} (최근 5년 실데이터)`;
    chartModal.classList.remove('hidden');
    
    // Map indicator title to Yahoo Finance Symbol
    let symbol = "";
    if (indicatorTitle.includes('KRW/USD')) symbol = "KRW=X";
    else if (indicatorTitle.includes('WTI')) symbol = "CL=F";
    else if (indicatorTitle.includes('NAT GAS')) symbol = "NG=F";
    else if (indicatorTitle.includes('EUR')) symbol = "EUR=X";
    else if (indicatorTitle.includes('JPY')) symbol = "JPY=X";
    else if (indicatorTitle.includes('NASDAQ')) symbol = "^IXIC";
    else symbol = "^GSPC"; // default S&P 500

    let labels = [];
    let data = [];

    try {
        const res = await fetch(`/api/macro?source=yfinance&symbol=${symbol}`);
        const result = await res.json();
        
        if (result.chart && result.chart.result && result.chart.result[0]) {
            const chartData = result.chart.result[0];
            const timestamps = chartData.timestamp || [];
            const closePrices = chartData.indicators.quote[0].close || [];
            
            for (let i = 0; i < timestamps.length; i++) {
                if (closePrices[i] !== null) {
                    const d = new Date(timestamps[i] * 1000);
                    labels.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
                    data.push(closePrices[i]);
                }
            }
        }
    } catch (e) {
        console.error("Failed to load real chart data", e);
        modalTitle.textContent = `${indicatorTitle} (데이터 연동 실패)`;
        return; // Don't chart on error
    }
    
    // Find High and Low
    const maxVal = Math.max(...data);
    const minVal = Math.min(...data);
    const maxIdx = data.indexOf(maxVal);
    const minIdx = data.indexOf(minVal);
    
    // Create point radius array (only highlight max/min)
    const pointRadius = data.map((v, i) => (i === maxIdx || i === minIdx) ? 6 : 0);
    const pointColors = data.map((v, i) => {
        if (i === maxIdx) return '#ef4444'; // Red for high
        if (i === minIdx) return '#3b82f6'; // Blue for low
        return '#4ade80';
    });

    const ctx = document.getElementById('macroChart').getContext('2d');
    
    if (macroChartInstance) {
        macroChartInstance.destroy();
    }
    
    macroChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: indicatorTitle,
                data: data,
                borderColor: '#4ade80',
                borderWidth: 2,
                tension: 0.1,
                pointRadius: pointRadius,
                pointBackgroundColor: pointColors,
                pointBorderColor: '#ffffff',
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            let label = context.parsed.y.toFixed(2);
                            if (context.dataIndex === maxIdx) label += ' (전고점)';
                            if (context.dataIndex === minIdx) label += ' (전저점)';
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8', maxTicksLimit: 12 }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
};

closeModal.addEventListener('click', () => {
    chartModal.classList.add('hidden');
});

chartModal.addEventListener('click', (e) => {
    if (e.target === chartModal) {
        chartModal.classList.add('hidden');
    }
});

// Attach clicks to indicator items
document.querySelectorAll('.indicator-item').forEach(item => {
    item.addEventListener('click', () => {
        const title = item.querySelector('.ind-title').textContent;
        openChartModal(title);
    });
});

// Event Listeners for Nav
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const target = e.target.getAttribute('data-target');
        setView(target);
    });
});

// Home Logo click event
document.getElementById('home-logo').addEventListener('click', () => {
    setView('home');
});

// Date Picker Event (Historical Data Simulation)
document.getElementById('historical-date').addEventListener('change', (e) => {
    const selectedDate = e.target.value;
    console.log(`Loading historical data for: ${selectedDate}`);
    
    // UI Feedback
    const originalTitle = currentViewTitle.textContent;
    currentViewTitle.textContent = "과거 데이터 불러오는 중...";
    
    setTimeout(() => {
        // Simulate data swapping by modifying the mock data slightly
        // In a real app, this would fetch data from Cloudflare D1/KV via an API endpoint.
        const randomFactor = 0.5 + Math.random(); // 0.5 to 1.5
        
        if (window.TradeData[currentCommodity] && window.TradeData[currentCommodity].arcs) {
            window.TradeData[currentCommodity].arcs.forEach(arc => {
                arc.volume = Math.round(arc.volume * randomFactor);
            });
            // Re-render the map if we are on a commodity view
            if (currentCommodity !== 'home' && currentCommodity !== 'climate' && !currentCommodity.startsWith('inst_')) {
                setView(currentCommodity);
            }
        }
        
        currentViewTitle.textContent = `${selectedDate} 기준 데이터 조회됨`;
        setTimeout(() => {
            currentViewTitle.textContent = originalTitle; // Revert after 3 seconds
        }, 3000);
        
    }, 500); // 500ms mock network delay
});

// Panels render clickable region lists, so these need to be reachable
// from inline handlers.
window.updateForecastPanel = updateForecastPanel;

// Initialize home view
setView('home');
updateNewsPanel('Global Market');
