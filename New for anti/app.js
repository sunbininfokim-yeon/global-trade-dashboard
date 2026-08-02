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

        // 사용자가 지도를 건드리면 잠시 회전 멈춤.
        // Debounced: this fires once per drag frame, so re-arm a single timer
        // rather than queueing one per frame.
        if (interactionState.isDragging || interactionState.isZooming || interactionState.isPanning) {
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
            updateForecastPanel(selectedCountry);
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
            updateForecastPanel(selectedCountry);
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

const updateForecastPanel = (regionName) => {
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
        document.getElementById('country-stats-desc').textContent = "AI 다중 작물 산출량 예측 (XGBoost Model)";
        
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
        
        // Render map with Globe view and empty layers (or a basic geojson layer for aesthetics)
        const countriesLayer = new GeoJsonLayer({
            id: 'countries-layer-home',
            data: 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json',
            stroked: true,
            filled: true,
            lineWidthMinPixels: 1,
            getFillColor: [15, 23, 42],
            getLineColor: [56, 189, 248, 80], // Neon blue border
            pickable: false
        });
        
        // Reset to the framing that keeps the curve gentle rather than ball-like
        currentViewState = { ...currentViewState, zoom: GLOBE_ZOOM, pitch: 0, bearing: 0 };

        deckgl.setProps({
            views: [new _GlobeView({ id: 'globe', resolution: 2 })],
            viewState: currentViewState,
            layers: [countriesLayer]
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
        currentViewDesc.textContent = "지역별 실시간 기후 데이터와 XGBoost 알고리즘을 통한 멀티 작황 모니터링";
        totalVolumeEl.textContent = "AI Model Active";
        topExporterEl.textContent = "XGBoost Regressor";
        
        updateForecastPanel('Global');
        
        // Render a generic map highlighting key agricultural regions
        const climateArcs = []; // No lines for climate view
        deckgl.setProps({ layers: [
            new ScatterplotLayer({
                id: `scatter-layer-climate`,
                data: [
                    {name: 'Mato Grosso (Brazil)', coordinates: window.CountriesData['Mato Grosso (Brazil)'], radius: 100000},
                    {name: 'Rio Grande do Sul (Brazil)', coordinates: window.CountriesData['Rio Grande do Sul (Brazil)'], radius: 100000},
                    {name: 'Iowa (USA)', coordinates: window.CountriesData['Iowa (USA)'], radius: 100000},
                    {name: 'Pampas (Argentina)', coordinates: window.CountriesData['Pampas (Argentina)'], radius: 100000},
                    {name: 'Sumatra (Indonesia)', coordinates: window.CountriesData['Sumatra (Indonesia)'], radius: 100000}
                ],
                pickable: true,
                opacity: 0.8,
                stroked: true,
                filled: true,
                radiusScale: 4,
                radiusMinPixels: 10,
                radiusMaxPixels: 40,
                lineWidthMinPixels: 2,
                getPosition: d => d.coordinates,
                getRadius: d => d.radius,
                getFillColor: [74, 222, 128, 200], // Green
                getLineColor: [255, 255, 255],
                onClick: handleNodeClick
            })
        ]});

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

// Initialize home view
setView('home');
updateNewsPanel('Global Market');
