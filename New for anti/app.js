// Application Logic for Global Trade Dashboard
const { DeckGL, LineLayer, ArcLayer, ScatterplotLayer, GeoJsonLayer, _GlobeView, MapView,
        WebMercatorViewport } = deck;

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
const climateRightPanelEl = document.getElementById('climate-right-panel');
const climateRightTitleEl = document.getElementById('climate-right-title');
const climateRightDescEl = document.getElementById('climate-right-desc');
const climateRightContentEl = document.getElementById('climate-right-content');
const climateMapLegendEl = document.getElementById('climate-map-legend');

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
    'US Cotton Belt': 'cotton_belt',
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
    cotton_belt: {
        headline: '추세수확량 + 기상편차 회귀 (면화, 파종면적 기준)',
        refs: 'Pettigrew (2004), Agronomy Journal · Scanlon et al. (2012), PNAS',
        notes: [
            '개화~꼬투리 충실기(7~9월) 수분이 꼬투리 수를 결정합니다. 면화는 고온 내성이 높아 EDD 임계를 32°C로 잡았습니다.',
            '텍사스 하이플레인스는 오갈라라 대수층 관개 의존도가 높아, 파종 전(11~4월) 토양수분 충전이 함께 들어갑니다.',
        ],
        finding: '수확면적이 아니라 파종면적 기준으로 단수를 계산했습니다. 텍사스 수확포기율이 '
               + '연도별 4~75%로 요동치는데, 가뭄해에 농민이 망한 밭을 갈아엎으면 살아남은 '
               + '관개 밭만 측정돼 단수가 오히려 높게 찍힙니다(2022년 포기율 74.5%인데 단수 734 lb/ac로 '
               + '평년 이상). 파종면적 기준으로 바꾸니 변동계수가 10.0%→37.1%로 커지고 최악 3개년이 '
               + '2022·2011·2023 — 실제 텍사스 가뭄해와 일치합니다.',
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
// Fetched once and shared by both climate levels; deck.gl caches the parsed
// result per URL, so repeating it across layers costs nothing.
const COUNTRIES_GEOJSON =
    'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json';

const CLIMATE_COUNTRIES = {
    'United States': {
        label: '미국',
        modelName: 'US Corn Belt Model',
        iso: 'USA',
        view: { longitude: -96.0, latitude: 39.5, zoom: 3.6 },
        dataFile: 'yield_forecast.json',
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
            { name: 'US Cotton Belt', label: '남부 텍사스 (면화)',
              coordinates: [-101.9, 33.6], regionKey: 'cotton_belt' },
        ],
    },
    'Brazil': {
        label: '브라질',
        modelName: 'Brazil Regional Model',
        iso: 'BRA',
        view: { longitude: -52.0, latitude: -13.0, zoom: 3.6 },
        dataFile: 'brazil_yield_forecast.json',
        // Coordinates are stated here rather than looked up in CountriesData:
        // that map is built for trade routes and is missing several of these
        // producing regions, which silently dropped their markers.
        regions: [
            { name: 'Mato Grosso (Brazil)', label: '마투그로수 (대두·옥수수)',
              coordinates: [-55.4, -12.6],
              regionKeys: ['mato_grosso_soja', 'mato_grosso_milho'] },
            { name: 'Rio Grande do Sul (Brazil)', label: '파라나·히우그란지두술',
              coordinates: [-52.3, -27.0],
              regionKeys: ['parana_soja', 'parana_milho', 'parana_trigo'] },
            { name: 'MATOPIBA (Brazil)', label: 'MATOPIBA (대두·면화)',
              coordinates: [-45.5, -10.5],
              regionKeys: ['matopiba_soja', 'matopiba_algodao'] },
            { name: 'Sao Paulo (Brazil)', label: '상파울루 (사탕수수·커피)',
              coordinates: [-47.8, -21.4],
              regionKeys: ['sp_cana', 'sp_cafe', 'sp_laranja'] },
        ],
    },
    // Forecast JSON is produced by Actions; if the file is absent the country
    // panel shows empty rather than inventing numbers (see loadClimateForecast).
    'India': {
        label: '인도',
        iso: 'IND',
        view: { longitude: 78.0, latitude: 23.5, zoom: 3.8 },
        dataFile: 'india_yield_forecast.json',
        regions: [
            { name: 'Punjab (India)', label: '펀자브·하리아나 (밀)',
              coordinates: [75.8, 30.4], regionKeys: ['punjab_wheat'] },
            { name: 'Madhya Pradesh (India)', label: '마디아프라데시 (대두)',
              coordinates: [77.0, 23.2], regionKeys: ['mp_soybean'] },
            { name: 'Vidarbha (India)', label: '비다르바·마라트와다·구자라트 (면화)',
              coordinates: [76.5, 21.0], regionKeys: ['vidarbha_cotton'] },
        ],
    },
    'Argentina': {
        label: '아르헨티나',
        modelName: 'Pampas + Norte Model',
        iso: 'ARG',
        view: { longitude: -64.0, latitude: -34.0, zoom: 3.8 },
        dataFile: 'argentina_yield_forecast.json',
        regions: [
            { name: 'Pampas soy (Argentina)', label: '팜파스 (대두)',
              coordinates: [-61.5, -34.0], regionKeys: ['pampas_soja'] },
            { name: 'Pampas corn (Argentina)', label: '팜파스 (옥수수)',
              coordinates: [-62.2, -32.5], regionKeys: ['pampas_maiz'] },
            { name: 'Norte soy (Argentina)', label: '북부 NOA/NEA (대두)',
              coordinates: [-62.5, -26.5], regionKeys: ['norte_soja'] },
            { name: 'Chaco cotton (Argentina)', label: '차코 (면화)',
              coordinates: [-60.5, -26.8], regionKeys: ['chaco_algodon'] },
        ],
    },
    'Australia': {
        label: '호주',
        modelName: 'Wheat Belt Model',
        iso: 'AUS',
        view: { longitude: 134.0, latitude: -27.0, zoom: 3.4 },
        dataFile: 'australia_yield_forecast.json',
        regions: [
            { name: 'WA wheat (Australia)', label: '서호주 밀',
              coordinates: [117.0, -31.5], regionKeys: ['wa_wheat'] },
            { name: 'SA wheat (Australia)', label: '남호주 밀',
              coordinates: [138.0, -34.0], regionKeys: ['sa_wheat'] },
            { name: 'VIC wheat (Australia)', label: '빅토리아 밀',
              coordinates: [143.0, -36.5], regionKeys: ['vic_wheat'] },
        ],
    },
    'China': {
        label: '중국',
        modelName: 'Regional crop suite',
        iso: 'CHN',
        view: { longitude: 105.0, latitude: 35.0, zoom: 3.5 },
        dataFile: 'china_yield_forecast.json',
        // All three currently fail beats_trend (skill deeply negative) — UI
        // still shows them with low-confidence badges so we do not hide failure.
        regions: [
            { name: 'Henan wheat (China)', label: '허난·황화이하이 (겨울밀)',
              coordinates: [113.7, 34.0], regionKeys: ['henan_wheat'] },
            { name: 'Yangtze rice (China)', label: '장강 유역 (벼)',
              coordinates: [114.3, 30.6], regionKeys: ['yangtze_rice'] },
            { name: 'Shandong vegetables (China)', label: '산둥 (채소)',
              coordinates: [118.0, 36.5], regionKeys: ['shandong_vegetables'] },
        ],
    },
    'Indonesia': {
        label: '인도네시아',
        modelName: 'National panel (baseline)',
        iso: 'IDN',
        view: { longitude: 118.0, latitude: -2.5, zoom: 3.6 },
        dataFile: 'indonesia_yield_forecast.json',
        // climate_gate often stops weather features (short sample); forecasts
        // are trend baselines with low_confidence in skill.yield.
        regions: [
            { name: 'Indonesia rice', label: '쌀 (전국)',
              coordinates: [112.5, -7.5], regionKeys: ['indonesia_rice'] },
            { name: 'Indonesia oil palm', label: '팜유 과실',
              coordinates: [113.9, -2.2], regionKeys: ['indonesia_oil_palm'] },
            { name: 'Indonesia coffee', label: '커피',
              coordinates: [110.4, -7.8], regionKeys: ['indonesia_coffee'] },
            { name: 'Indonesia rubber', label: '천연고무',
              coordinates: [104.0, -3.0], regionKeys: ['indonesia_rubber'] },
        ],
    },
};

// 무역·수출 통제 seed (지도 국가 색). 실제 정책 피드 연동 전까지 UI 규칙용.
// blue=정상 · yellow=restricted · orange=금지 1개 · red=곡물 금지 2개+
const CLIMATE_TRADE_POLICY = {
    'United States': { restricted: false, prohibitedCrops: [], note: '정상 수출' },
    'Brazil': { restricted: false, prohibitedCrops: [], note: '정상' },
    'India': { restricted: true, prohibitedCrops: [], note: '수출 인허가·쿼터 등 제한적 조치 (seed)' },
    'Argentina': { restricted: false, prohibitedCrops: ['corn'], note: '옥수수 관련 수출 통제 seed (1품목 → 주황)' },
    'Australia': { restricted: false, prohibitedCrops: [], note: '정상' },
    'China': { restricted: false, prohibitedCrops: ['corn', 'wheat'], note: '주요 곡물 수출 제한 seed (2+ → 적)' },
    'Indonesia': { restricted: true, prohibitedCrops: ['palm_oil'], note: '팜 등 통제 seed (1품목 금지 → 주황 우선)' },
};

const TRADE_FILL = {
    blue:   [56, 189, 248, 125],
    yellow: [250, 204, 21, 145],
    orange: [251, 146, 60, 155],
    red:    [248, 113, 113, 160],
    none:   [30, 41, 59, 55],
};
const TRADE_LINE = {
    blue:   [125, 211, 252, 235],
    yellow: [253, 224, 71, 240],
    orange: [253, 186, 116, 240],
    red:    [252, 165, 165, 245],
    none:   [255, 255, 255, 30],
};

const tradePolicyLevel = (countryName) => {
    const p = CLIMATE_TRADE_POLICY[countryName] || {};
    const n = (p.prohibitedCrops || []).length;
    if (n >= 2) return 'red';
    if (n === 1) return 'orange';
    if (p.restricted) return 'yellow';
    return 'blue';
};

const tradePolicyLabelKo = (level) => ({
    blue: '정상',
    yellow: 'Restricted',
    orange: 'Prohibited 1',
    red: 'Prohibited 2+',
}[level] || level);

// Which level the climate view is currently showing.
let climateLevel = 'world';
let climateCountry = null;

const BRAZIL_REGION_MODELS = {
    'Mato Grosso (Brazil)': ['mato_grosso_soja', 'mato_grosso_milho'],
    'Rio Grande do Sul (Brazil)': ['parana_soja', 'parana_milho', 'parana_trigo'],
    'MATOPIBA (Brazil)': ['matopiba_soja', 'matopiba_algodao'],
    'Sao Paulo (Brazil)': ['sp_cana', 'sp_cafe', 'sp_laranja'],
};

// Which model key belongs to each clickable Indian region on the map. One
// model per point here, unlike Brazil -- the three guides in Regions/인도
// each cover exactly one region-crop.
const INDIA_REGION_MODELS = {
    'Punjab (India)': ['punjab_wheat'],
    'Madhya Pradesh (India)': ['mp_soybean'],
    'Vidarbha (India)': ['vidarbha_cotton'],
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
        '기여는 −13.6%로 그대로 마이너스였습니다. 시차를 늘려도 안 됐다는 건, 애초에 빠진 게 ' +
        '"더 긴 날씨 기억"이 아니라 "날씨로 환원 안 되는 변수"라는 뜻입니다. ' +
        '경영 대리변수인 lag1조차 표준화 효과가 +0.1%로, 11개 피처 중 가장 약합니다 — ' +
        '그루터기 연차 대리변수마저 이 정도로 안 움직인다는 게 사탕수수 변동성이 얼마나 안 ' +
        '잡히는지를 보여줍니다.',
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

// Korean copy for India's "not weather" callout, same role as
// BRAZIL_NON_WEATHER_KO above: the model artifacts carry the canonical
// English in provenance.non_weather_drivers, this is the display layer.
const INDIA_NON_WEATHER_KO = {
    punjab_wheat:
        '펀자브·하리아나 밀은 정책이 날씨만큼 수확량을 흔듭니다. 최저지지가격(MSP) 보장 수매, ' +
        '관정 전력 보조금, 운하 로테이션 일정이 투입 강도와 파종 시기 자체를 정하며 어떤 기상 ' +
        '피처에도 잡히지 않습니다. 지하수 고갈은 이보다 느리게 진행되는 제약으로, 개별 시즌이 ' +
        '아니라 기술 추세선 자체를 서서히 끌어내리는 방향으로 작용합니다.',
    mp_soybean:
        '마디아프라데시 대두 재배면적은 대두·옥수수·두류의 상대가격에 따라 해마다 이동합니다. ' +
        '면적 배분이 바뀌면 날씨가 그대로여도 평균 단수가 달라집니다. 종자 갱신률과 황색모자이크 ' +
        '바이러스 발병 압력도 실질적인 해거리 요인이지만 어떤 기후 피처로도 포착되지 않습니다.',
    vidarbha_cotton:
        '이 세트에서 날씨로 가장 설명하기 어려운 작물입니다. 2002년 이후 Bt 면화 전환, 종자 ' +
        '가격·공급, 2015년 무렵부터 확산된 핑크볼웜의 Bt 저항성, 대두·비둘기콩 대비 최저지지가격 ' +
        '상대값이 매년 재배면적과 투입 강도를 움직입니다. ICRISAT은 면화를 섬유(lint) 기준으로 ' +
        '발표하므로, 조면율(ginning ratio)이 바뀌기만 해도 밭에서 아무 변화가 없어도 수치가 ' +
        '움직입니다.',
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
        // while adding nothing meteorological, or the whole model can simply
        // fail to beat trend on any feature at all -- a climate panel must
        // not present either case as a working weather forecast.
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
            ${d.last_actual.note ? `
            <div style="margin-top:6px; font-size:11px; color:#94a3b8;">
                ※ IBGE가 ${d.last_actual.year + 1}년${
                    fc.season - d.last_actual.year > 2 ? `~${fc.season - 1}년` : ''
                } 확정 단수를 아직 발표하지 않았습니다. 결측이 아니라
                <strong style="color:#cbd5e1;">미발표</strong>이며, 현재 확보된 가장 최근 실적은
                ${d.last_actual.year}년입니다.
            </div>` : ''}
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
            ${(d.skill.top_effects || []).length ? `
            <div style="margin-top:8px; font-size:11px; color:#94a3b8;">
                <div style="margin-bottom:4px;">실제로 무엇이 이 모델을 움직이는가 (1σ당 수확량 효과)</div>
                ${d.skill.top_effects.slice(0, 3).map(e => `
                <div style="display:flex; justify-content:space-between; margin-top:2px;">
                    <span style="color:${e.is_weather ? '#cbd5e1' : '#fbbf24'};">
                        ${e.is_weather ? '🌦️' : '📋'} ${e.feature}
                    </span>
                    <span style="color:${e.effect_pct >= 0 ? '#4ade80' : '#fca5a5'};">
                        ${e.effect_pct >= 0 ? '+' : ''}${e.effect_pct.toFixed(1)}%
                    </span>
                </div>`).join('')}
            </div>` : ''}
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

// Renders the India regional yield forecasts.
//
// Same discipline as renderBrazilYieldForecast: a model that fails validation
// is shown, not hidden, flagged so the trend-extrapolation reads as one. India
// additionally carries the Indian Ocean Dipole alongside ENSO -- the soybean
// guide asks for both, since a positive IOD can hold the monsoon up through an
// El Nino year that ONI alone would score as a bad one.
const renderIndiaYieldForecast = async (regionName) => {
    const keys = INDIA_REGION_MODELS[regionName];
    if (!keys) return false;

    const fc = await window.loadIndiaYieldForecast?.();
    if (!fc || !fc.regions) return false;

    const shown = keys.map(k => [k, fc.regions[k]]).filter(([, d]) => d);
    if (!shown.length) return false;

    const fmt = n => Math.round(n).toLocaleString();
    let html = '';

    for (const [key, d] of shown) {
        const vsLast = d.point - d.last_actual.yield;
        const skilled = d.skill.weather_driven;
        const color = d.weather_effect_pct < 0 ? '#fca5a5' : '#4ade80';
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

        const enso = d.enso || {};
        const iod = d.iod || {};

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
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:6px;">
                    <span>엘니뇨/라니냐 (ONI)</span>
                    <span>${enso.oni_growing_season == null ? 'N/A' : enso.oni_growing_season.toFixed(2)} · ${enso.state || 'N/A'}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-top:2px;">
                    <span>인도양 쌍극자 (IOD)</span>
                    <span>${iod.dmi_growing_season == null ? 'N/A' : iod.dmi_growing_season.toFixed(2)} · ${iod.state || 'N/A'}</span>
                </div>
            </div>
            ${d.provenance.non_weather_drivers ? `
            <div style="margin-top:8px; padding:8px; background:rgba(251,191,36,0.08);
                        border-left:2px solid rgba(251,191,36,0.5); border-radius:4px;
                        font-size:11px; color:#cbd5e1; line-height:1.5;">
                <strong style="color:#fbbf24;">날씨가 아닌 요인</strong><br>${
                    INDIA_NON_WEATHER_KO[key] || d.provenance.non_weather_drivers}
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

    forecastCountryTitle.textContent = `인도 지역 작황 예측 (${fc.season})`;
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">대상 지역</span>
                <span class="forecast-val" style="font-size:12px;">${regionName.replace(' (India)', '')}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">작물 수</span>
                <span class="forecast-val">${shown.length}개 모델</span>
            </div>
            <div class="forecast-good" style="margin-top:16px;">
                <strong>지역별 개별 방법론 + 추세·기상편차 분해</strong><br>
                <span style="font-size:11px; font-weight:400;">
                펀자브 밀은 등숙기 종말기 열 스트레스(THSDD), 마디아프라데시 대두는 몬순 개시
                지연·개화기 무강우 연속일수, 비다르바 면화는 수분적자·해충 적합일수로 각각
                다른 수식을 씁니다.
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
            출처: ICRISAT DLD(지구별 수확량) · NASA POWER(기상) · NOAA CPC(ONI) · NOAA PSL(IOD)
        </p>`;

    countryStatsTitleEl.textContent = regionName.replace(' (India)', '');
    document.getElementById('country-stats-desc').textContent =
        '기후 모델링 문서(Regions/인도) 지역별 수식 구현 · log 추세 + 기상편차';
    countryStatsContentEl.innerHTML = html;
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.remove('hidden');
    return true;
};

// Level 1 -- the world, with modelled countries picked out.
// Countries without a fitted model are drawn but not clickable, so the map
// never suggests a forecast exists where it does not.

// ---------------------------------------------------------------------------
// Climate view: world -> country drill-down.
//
// Level 1 is the world with modelled countries filled; hovering one shows a
// summary card, clicking enters it. Level 2 zooms to that country and marks
// its producing regions; clicking the country again (or the breadcrumb)
// returns to level 1.
// ---------------------------------------------------------------------------

let climateHover = null;

// --- Generic forecast loading -------------------------------------------
// One loader for every country, keyed on the `dataFile` in CLIMATE_COUNTRIES.
// Adding a country is then: drop the JSON in public/data/ and add a config
// entry -- no new loader, no new render branch.
const climateForecastCache = {};
const loadClimateForecast = async (cfg) => {
    if (!cfg.dataFile) return null;
    if (cfg.dataFile in climateForecastCache) return climateForecastCache[cfg.dataFile];
    try {
        const res = await fetch(`/public/data/${cfg.dataFile}`);
        climateForecastCache[cfg.dataFile] = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn(`[Climate] ${cfg.dataFile} unavailable`, err);
        climateForecastCache[cfg.dataFile] = null;
    }
    return climateForecastCache[cfg.dataFile];
};

// --- Shape normalisation -------------------------------------------------
// The per-country pipelines were written at different times against different
// guides, so the same quantity goes by several names. Rather than force a
// migration of every producer, the reader accepts the known spellings and
// hands the renderers one shape. A country whose JSON uses none of these
// still renders -- it just contributes no rows, instead of throwing.
//
// Two structural families exist:
//   nested  regions[k].crops[c]  -- one region hosting several crops (US)
//   flat    regions[k]           -- the region entry *is* the crop
const num = v => (typeof v === 'number' && isFinite(v) ? v : null);

const normalizeCrop = (entry, group, label, parent = {}, regionKey = null) => {
    // Indonesia puts the whole forecast under `yield_kg_ha`; everyone else
    // has `point` as a plain number at the top level.
    const f = (entry.point && typeof entry.point === 'object') ? entry.point
        : (entry.yield_kg_ha && typeof entry.yield_kg_ha === 'object') ? entry.yield_kg_ha
        : entry;

    // Most countries use a flat skill object. Indonesia nests yield/area/
    // production under skill.yield with climate_gate metadata.
    const skillRoot = entry.skill || f.skill || {};
    const skill = (skillRoot.yield && typeof skillRoot.yield === 'object')
        ? skillRoot.yield
        : skillRoot;
    const la = entry.last_actual || {};
    const trend = num(f.trend) ?? num(f.diagnostic_trend);
    const weather = num(f.weather_effect);
    const skillVs = num(skill.skill_vs_trend_only);
    const climateGate = skill.climate_gate || f.climate_gate || null;
    const gateStopped = climateGate
        && String(climateGate.status || '').includes('insufficient');

    return {
        group,
        regionKey,
        label: label || entry.label_ko || entry.label || entry.target_label || entry.crop || '—',
        point: num(f.point),
        unit: entry.unit || f.unit || 'kg/ha',
        lastActual: num(la.yield) ?? num(la.value) ?? num(la.yield_kg_ha),
        lastActualYear: num(la.year),
        // Four ways to say "do not trust this as weather skill":
        // low_confidence flag, beats_trend false, skill_vs_trend < 0.20,
        // climate_gate stopped for short sample (Indonesia).
        lowConfidence: skill.low_confidence === true
            || skillRoot.low_confidence === true
            || entry.low_confidence === true
            || skill.beats_trend === false
            || skillRoot.beats_trend === false
            || (skillVs !== null && skillVs < 0.20)
            || gateStopped,
        skillVsTrend: skillVs,
        climateGate,
        // Percent deviation from trend -- the number that says whether the
        // season is running hot or cold.
        pct: num(entry.weather_effect_pct)
            ?? (trend && weather !== null && Math.abs(trend) > 1e-9
                ? (weather / trend) * 100 : null),
        // "no forecast here" is declared on the region, not on each crop under
        // it (see DATA_LAYOUT.md), so the flag and its explanation are
        // inherited downward.
        forecastAvailable: entry.forecast_available !== false
            && parent.forecast_available !== false
            && num(f.point) !== null,
        reason: entry.reason_ko || entry.reason
            || parent.reason_ko || parent.reason
            || (gateStopped
                ? `기상 피처 게이트 정지 (표본 ${climateGate.available_seasons ?? '?'} / 필요 ${climateGate.required_seasons ?? '?'})`
                : null),
    };
};

const normalizeForecast = (fc, onlyKeys = null) => {
    if (!fc || !fc.regions) return [];
    const out = [];
    const keySet = onlyKeys ? new Set(onlyKeys) : null;
    for (const [regionKey, region] of Object.entries(fc.regions)) {
        if (keySet && !keySet.has(regionKey)) continue;
        const regionLabel = region.label_ko || region.label || null;
        if (region.crops && typeof region.crops === 'object') {
            for (const crop of Object.values(region.crops)) {
                out.push(normalizeCrop(
                    crop, regionLabel, crop.label_ko || crop.label, region, regionKey));
            }
        } else {
            out.push(normalizeCrop(region, null, regionLabel, {}, regionKey));
        }
    }
    return out;
};

// --- Climate dashboard v2 (world global climate + country drill-down) -----

let climateGlobalCache = null;
let climateCityWx = {};

const loadClimateGlobal = async () => {
    if (climateGlobalCache) return climateGlobalCache;
    try {
        const res = await fetch('/public/data/climate_global_v1.json', { cache: 'no-cache' });
        climateGlobalCache = res.ok ? await res.json() : null;
    } catch (err) {
        console.warn('[Climate] climate_global_v1 unavailable', err);
        climateGlobalCache = null;
    }
    return climateGlobalCache;
};

const refreshClimateCityTemps = async () => {
    const g = await loadClimateGlobal();
    if (!g?.cities?.length) return;
    await Promise.all(g.cities.map(async (c) => {
        try {
            const url = `https://api.open-meteo.com/v1/forecast?latitude=${c.lat}&longitude=${c.lon}&current=temperature_2m`;
            const res = await fetch(url);
            if (!res.ok) return;
            const j = await res.json();
            const t = j.current?.temperature_2m;
            if (typeof t === 'number') climateCityWx[c.name] = t;
        } catch (_) { /* offline ok */ }
    }));
};

const climateCountrySummary = async (cfg) => {
    const fc = await loadClimateForecast(cfg);
    if (!fc) return null;
    const crops = normalizeForecast(fc);
    if (!crops.length) return null;
    const scored = crops.filter(c => c.pct !== null);
    const meanPct = scored.length
        ? scored.reduce((s, c) => s + c.pct, 0) / scored.length
        : null;
    return {
        season: fc.season,
        regionCount: cfg.regions.length,
        cropCount: crops.length,
        meanPct,
        lowShare: crops.length
            ? crops.filter(c => c.lowConfidence).length / crops.length
            : 0,
    };
};

const regionStressFromPct = (pct) => {
    if (pct === null || pct === undefined) return { level: 'neutral', rgba: [148, 163, 184, 180], ko: '데이터 부족' };
    if (pct <= -4) return { level: 'high', rgba: [248, 113, 113, 210], ko: '고스트레스' };
    if (pct <= -1.5) return { level: 'warn', rgba: [251, 146, 60, 210], ko: '주의' };
    return { level: 'ok', rgba: [74, 222, 128, 210], ko: '양호' };
};

const isoToCountryName = () => {
    const m = {};
    for (const [name, cfg] of Object.entries(CLIMATE_COUNTRIES)) m[cfg.iso] = name;
    return m;
};

const climateWorldViewState = () => {
    const fallback = { longitude: 10, latitude: 20, zoom: 1.45, pitch: 0, bearing: 0 };
    const pts = Object.values(CLIMATE_COUNTRIES)
        .flatMap(c => c.regions.map(r => r.coordinates).filter(Boolean));
    const rect = mapContainer.getBoundingClientRect();
    const vp = deckgl.getViewports?.()[0];
    const canvas = rect.width && rect.height
        ? { width: rect.width, height: rect.height }
        : { width: vp?.width, height: vp?.height };
    if (pts.length < 2 || !canvas.width || !canvas.height) return fallback;
    const lons = pts.map(p => p[0]);
    const lats = pts.map(p => p[1]);
    try {
        const fitted = new WebMercatorViewport({
            width: canvas.width, height: canvas.height,
        }).fitBounds(
            [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
            { padding: 48 },
        );
        return {
            longitude: fitted.longitude, latitude: fitted.latitude,
            zoom: Math.min(Math.max(fitted.zoom, 1.05), 2.4), pitch: 0, bearing: 0,
        };
    } catch (err) {
        console.warn('[Climate] world framing failed', err);
        return fallback;
    }
};

const setClimateMapLegend = (mode) => {
    if (!climateMapLegendEl) return;
    if (mode === 'world') {
        climateMapLegendEl.classList.remove('hidden');
        climateMapLegendEl.innerHTML = `
            <h4>무역·수출 통제 (모델 보유국)</h4>
            <div class="leg-row"><span class="swatch" style="background:#38bdf8"></span> 정상 (Blue)</div>
            <div class="leg-row"><span class="swatch" style="background:#facc15"></span> Restricted (Yellow)</div>
            <div class="leg-row"><span class="swatch" style="background:#fb923c"></span> Prohibited 1품목 (Orange)</div>
            <div class="leg-row"><span class="swatch" style="background:#f87171"></span> Prohibited 곡물 2+ (Red)</div>
            <div class="leg-row"><span class="swatch" style="background:#1e293b"></span> 미대상</div>
            <div style="margin-top:8px;color:#64748b;font-size:10px;">seed 정책표 · 실시간 정책 피드는 추후</div>`;
    } else if (mode === 'country') {
        climateMapLegendEl.classList.remove('hidden');
        climateMapLegendEl.innerHTML = `
            <h4>산지 기상 스트레스 (추세 대비)</h4>
            <div class="leg-row"><span class="swatch" style="background:#f87171"></span> 고스트레스 (≤ −4%)</div>
            <div class="leg-row"><span class="swatch" style="background:#fb923c"></span> 주의 (−4 ~ −1.5%)</div>
            <div class="leg-row"><span class="swatch" style="background:#4ade80"></span> 양호</div>
            <div style="margin-top:8px;color:#64748b;font-size:10px;">배경 지도 클릭 → 세계 지도</div>`;
    } else {
        climateMapLegendEl.classList.add('hidden');
        climateMapLegendEl.innerHTML = '';
    }
};

const renderEnsoBars = (series) => {
    if (!series?.length) return '';
    const vals = series.map(s => s.oni);
    const maxAbs = Math.max(0.5, ...vals.map(v => Math.abs(v)));
    return `<div class="climate-bars" title="ONI 최근 궤적">
        ${series.map(s => {
            const h = Math.max(4, Math.round((Math.abs(s.oni) / maxAbs) * 46));
            const col = s.oni < 0 ? 'rgba(56,189,248,0.75)' : 'rgba(248,113,113,0.75)';
            return `<span style="height:${h}px;background:${col}" title="${s.label}: ${s.oni}"></span>`;
        }).join('')}
    </div>`;
};

const renderClimateWorldLeft = async () => {
    const g = await loadClimateGlobal();
    const enso = g?.enso || {};
    const iod = g?.iod || {};
    const amo = g?.north_atlantic || {};
    const continents = g?.continent_temp_anomaly?.values || [];
    const maxAbsC = Math.max(0.5, ...continents.map(c => Math.abs(c.anomaly || 0)));

    forecastCountryTitle.textContent = '전역 기후 모니터';
    forecastContentEl.innerHTML = `
        <div class="climate-scroll">
            <div class="climate-card">
                <h3>ENSO · Niño 3.4 (NOAA CPC seed)</h3>
                <div class="climate-big ${enso.latest_c < 0 ? 'neg' : 'pos'}">
                    ${enso.latest_c != null ? (enso.latest_c > 0 ? '+' : '') + enso.latest_c.toFixed(1) + '°C' : '—'}
                </div>
                <div class="climate-sub">${enso.state_ko || '상태 미정'}
                    ${enso.prob_continue_pct != null ? ` · 지속 확률 ${enso.prob_continue_pct}%` : ''}</div>
                ${renderEnsoBars(enso.series)}
            </div>
            <div class="climate-card">
                <h3>IOD · 인도양 쌍극자</h3>
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div class="climate-big ${ (iod.latest||0) >= 0 ? 'pos' : 'neg'}" style="font-size:22px;">
                        ${iod.latest != null ? ((iod.latest >= 0 ? '+' : '') + iod.latest.toFixed(2)) : '—'}
                    </div>
                    <span class="climate-status-pill ${ (iod.latest||0) >= 0 ? 'red' : 'blue' }">${iod.state_ko || '—'}</span>
                </div>
                <div class="climate-sub">${iod.note_ko || ''}</div>
            </div>
            <div class="climate-card">
                <h3>북대서양 SST (요약 seed)</h3>
                <div class="climate-metric-row">
                    <span class="nm">${amo.index || 'AMO'}</span>
                    <span class="vl">${amo.anomaly_c != null ? ((amo.anomaly_c>=0?'+':'') + amo.anomaly_c.toFixed(2) + '°C') : '—'}</span>
                </div>
                <div class="climate-sub">${amo.state_ko || ''} · 시계열 연동 예정</div>
            </div>
            <div class="climate-card">
                <h3>대륙 평균 기온 편차 (${g?.continent_temp_anomaly?.baseline || 'baseline'})</h3>
                ${continents.map(c => {
                    const w = Math.round((Math.abs(c.anomaly) / maxAbsC) * 100);
                    return `<div class="climate-hbar">
                        <span>${c.name}</span>
                        <div class="track"><div class="fill" style="width:${w}%"></div></div>
                        <span style="color:#fca5a5;text-align:right;">+${Number(c.anomaly).toFixed(2)}</span>
                    </div>`;
                }).join('') || '<div class="climate-sub">데이터 없음</div>'}
            </div>
            <div class="climate-card">
                <h3>주요 산지 도시 기온 (Open-Meteo)</h3>
                ${(g?.cities || []).map(c => {
                    const t = climateCityWx[c.name];
                    return `<div class="climate-city-row">
                        <span class="nm">${c.label_ko || c.name}</span>
                        <span class="vl">${t != null ? t.toFixed(1) + '°C' : '…'}</span>
                    </div>`;
                }).join('') || '<div class="climate-sub">도시 seed 없음</div>'}
            </div>
            <p style="font-size:10px;color:#64748b;line-height:1.5;">
                지수 seed: <code>climate_global_v1.json</code>. 상세 시계열·파생상품 풀셋은 이후 갱신.
            </p>
        </div>`;
};

const renderClimateWorldRight = async () => {
    const g = await loadClimateGlobal();
    const deriv = g?.climate_derivatives || {};
    if (climateRightTitleEl) climateRightTitleEl.textContent = '모델 국가 · 무역 상태';
    if (climateRightDescEl) climateRightDescEl.textContent = '클릭 시 국가 상세 · seed 정책색';
    if (!climateRightContentEl) return;

    const rows = Object.entries(CLIMATE_COUNTRIES).map(([name, cfg]) => {
        const lv = tradePolicyLevel(name);
        const pol = CLIMATE_TRADE_POLICY[name] || {};
        const bans = (pol.prohibitedCrops || []).join(', ') || '—';
        return `<div class="climate-table-row" style="cursor:pointer;" onclick="showClimateCountry('${name}')">
            <span class="nm">${cfg.label}
                <span class="climate-status-pill ${lv}" style="margin-left:6px;">${tradePolicyLabelKo(lv)}</span>
            </span>
            <span class="vl" style="font-size:11px;color:#94a3b8;">${cfg.regions.length}산지 →</span>
        </div>
        <div style="font-size:10px;color:#64748b;margin:-4px 0 8px;">금지/통제: ${bans}</div>`;
    }).join('');

    climateRightContentEl.innerHTML = `
        <div class="climate-card">
            <h3>보유 모델 ${Object.keys(CLIMATE_COUNTRIES).length}개국</h3>
            ${rows}
        </div>
        <div class="climate-card">
            <h3>기후 파생 (요약만 · 추후 업데이트)</h3>
            <div class="climate-sub" style="margin-bottom:8px;">${deriv.note_ko || ''}</div>
            ${(deriv.items || []).map(it => `
                <div class="climate-metric-row">
                    <span class="nm">${it.name}</span>
                    <span class="vl">${it.price}${it.chg_pct != null ? ` <span style="color:${it.chg_pct>=0?'#4ade80':'#fca5a5'};font-size:11px;">(${it.chg_pct>=0?'+':''}${it.chg_pct}%)</span>` : ''}</span>
                </div>`).join('') || '<div class="climate-sub">항목 없음</div>'}
        </div>`;
};

const showClimateWorld = async () => {
    climateLevel = 'world';
    climateCountry = null;
    climateHover = null;
    hideClimateTooltip();

    const isoMap = isoToCountryName();
    currentViewTitle.textContent = '기후·작황 예측';
    currentViewDesc.textContent = '모델 보유국 hover=요약 · 클릭=국가 상세 · 배경 클릭으로 복귀';
    totalVolumeEl.textContent = `${Object.keys(CLIMATE_COUNTRIES).length}개국`;
    topExporterEl.textContent = 'Trade status colors';

    // left commodity panel meta already from climate setView
    document.getElementById('commodity-info-panel')?.classList.remove('hidden');

    setClimateMapLegend('world');
    await renderClimateWorldLeft();
    await renderClimateWorldRight();
    if (climateRightPanelEl) climateRightPanelEl.classList.remove('hidden');
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.add('hidden');
    forecastPanelEl.classList.remove('hidden');

    const g = await loadClimateGlobal();
    const tempSeed = g?.map_temp_anomaly_seed || {};

    // Label points at approx country centroid from first region
    const labels = Object.entries(CLIMATE_COUNTRIES).map(([name, cfg]) => {
        const coords = cfg.regions[0]?.coordinates;
        if (!coords) return null;
        const t = tempSeed[name];
        return {
            name, label: cfg.label, coordinates: coords,
            temp: typeof t === 'number' ? t : null,
            level: tradePolicyLevel(name),
        };
    }).filter(Boolean);

    deckgl.setProps({
        views: [new MapView({ id: 'mapview' })],
        viewState: climateWorldViewState(),
        onClick: null,
        onResize: () => {
            if (climateLevel === 'world') {
                deckgl.setProps({ viewState: climateWorldViewState() });
            }
        },
        layers: [
            new GeoJsonLayer({
                id: 'climate-countries',
                data: COUNTRIES_GEOJSON,
                stroked: true,
                filled: true,
                lineWidthMinPixels: 1,
                getFillColor: f => {
                    const name = isoMap[f.id];
                    if (!name) return TRADE_FILL.none;
                    return TRADE_FILL[tradePolicyLevel(name)] || TRADE_FILL.blue;
                },
                getLineColor: f => {
                    const name = isoMap[f.id];
                    if (!name) return TRADE_LINE.none;
                    return TRADE_LINE[tradePolicyLevel(name)] || TRADE_LINE.blue;
                },
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 80],
                updateTriggers: {
                    getFillColor: [climateLevel, Object.keys(CLIMATE_TRADE_POLICY).join()],
                    getLineColor: [climateLevel],
                },
                onHover: async info => {
                    if (!info.object) { hideClimateTooltip(); return; }
                    const entry = Object.entries(CLIMATE_COUNTRIES)
                        .find(([, c]) => c.iso === info.object.id);
                    if (!entry) { hideClimateTooltip(); return; }
                    showClimateTooltip(info, entry[0], entry[1]);
                },
                onClick: info => {
                    const entry = Object.entries(CLIMATE_COUNTRIES)
                        .find(([, c]) => c.iso === info.object?.id);
                    if (entry) showClimateCountry(entry[0]);
                },
            }),
            new ScatterplotLayer({
                id: 'climate-country-pins',
                data: labels,
                pickable: false,
                stroked: true,
                filled: true,
                opacity: 0.95,
                radiusMinPixels: 4,
                radiusMaxPixels: 8,
                getPosition: d => d.coordinates,
                getRadius: 40000,
                getFillColor: d => TRADE_FILL[d.level] || TRADE_FILL.blue,
                getLineColor: [255, 255, 255, 180],
                lineWidthMinPixels: 1,
            }),
        ],
    });

    // non-blocking city temps
    refreshClimateCityTemps().then(() => {
        if (climateLevel === 'world') renderClimateWorldLeft();
    });
};
window.showClimateWorld = showClimateWorld;

const showClimateTooltip = async (info, name, cfg) => {
    const s = await climateCountrySummary(cfg);
    if (climateLevel !== 'world') return;
    const g = await loadClimateGlobal();
    const tAnom = g?.map_temp_anomaly_seed?.[name];
    const lv = tradePolicyLevel(name);
    const pol = CLIMATE_TRADE_POLICY[name] || {};
    const color = s?.meanPct != null && s.meanPct < 0 ? '#fca5a5' : '#4ade80';
    tooltipEl.style.left = `${info.x + 12}px`;
    tooltipEl.style.top = `${info.y + 12}px`;
    tooltipEl.classList.remove('hidden');
    tooltipEl.innerHTML = `
        <div class="tooltip-title">${cfg.label}${cfg.modelName ? ` · ${cfg.modelName}` : ''}</div>
        <div class="tooltip-stat"><span>무역 상태</span>
            <span class="climate-status-pill ${lv}">${tradePolicyLabelKo(lv)}</span></div>
        ${tAnom != null ? `<div class="tooltip-stat"><span>기온 편차 seed</span>
            <span style="color:${tAnom >= 0 ? '#fca5a5' : '#7dd3fc'};font-weight:bold;">
            ${tAnom >= 0 ? '+' : ''}${tAnom.toFixed(1)}°C</span></div>` : ''}
        ${s ? `
        <div class="tooltip-stat"><span>작황 기상효과</span>
            ${s.meanPct === null
                ? '<span style="color:#94a3b8;">요약 불가</span>'
                : `<span style="color:${color}; font-weight:bold;">
                   ${s.meanPct >= 0 ? '+' : ''}${s.meanPct.toFixed(1)}%</span>`}</div>
        <div class="tooltip-stat"><span>대상 작물 / 산지</span>
            <span>${s.cropCount}개 · ${s.regionCount}개</span></div>`
        : '<div class="tooltip-stat"><span>예측 로딩…</span></div>'}
        <div style="margin-top:6px;font-size:10px;color:#64748b;">${pol.note || ''} · 클릭하여 상세</div>`;
};

const hideClimateTooltip = () => tooltipEl.classList.add('hidden');

const buildRegionPoints = async (cfg) => {
    const fc = await loadClimateForecast(cfg);
    return cfg.regions.map(r => {
        const keys = r.regionKeys || (r.regionKey ? [r.regionKey] : []);
        const crops = normalizeForecast(fc, keys.length ? keys : null)
            .filter(c => !keys.length || keys.includes(c.regionKey));
        // if keys empty, don't attach all country crops
        const relevant = keys.length
            ? normalizeForecast(fc, keys)
            : [];
        const scored = relevant.filter(c => c.pct != null);
        const meanPct = scored.length
            ? scored.reduce((s, c) => s + c.pct, 0) / scored.length
            : null;
        const stress = regionStressFromPct(meanPct);
        const unit = relevant[0]?.unit || 'kg/ha';
        const point = relevant[0]?.point;
        return {
            ...r,
            coordinates: r.coordinates || window.CountriesData?.[r.name],
            meanPct,
            stress,
            unit,
            point,
            cropCount: relevant.length,
        };
    }).filter(r => r.coordinates);
};

const showClimateCountry = async (countryName) => {
    const cfg = CLIMATE_COUNTRIES[countryName];
    if (!cfg) return;

    climateLevel = 'country';
    climateCountry = countryName;
    hideClimateTooltip();
    document.getElementById('commodity-info-panel')?.classList.remove('hidden');

    const points = await buildRegionPoints(cfg);
    const lv = tradePolicyLevel(countryName);
    const pol = CLIMATE_TRADE_POLICY[countryName] || {};

    currentViewTitle.textContent = `${cfg.label} ${cfg.iso || ''}`.trim();
    currentViewDesc.textContent = `${cfg.regions.length}개 산지 · 배경 클릭 시 세계 지도로 복귀`;
    totalVolumeEl.textContent = cfg.modelName || cfg.label;
    topExporterEl.textContent = tradePolicyLabelKo(lv);

    setClimateMapLegend('country');

    deckgl.setProps({
        views: [new MapView({ id: 'mapview' })],
        viewState: { ...cfg.view, pitch: 0, bearing: 0 },
        onClick: info => {
            if (climateLevel !== 'country') return;
            // Region layer eats its own clicks; anything else returns to world.
            if (info.layer?.id === 'climate-regions') return;
            showClimateWorld();
        },
        layers: [
            new GeoJsonLayer({
                id: 'climate-countries',
                data: COUNTRIES_GEOJSON,
                stroked: true,
                filled: true,
                lineWidthMinPixels: f => f.id === cfg.iso ? 2.5 : 1,
                getFillColor: f => f.id === cfg.iso
                    ? (TRADE_FILL[lv] || TRADE_FILL.blue).map((v, i) => i === 3 ? 70 : v)
                    : [30, 41, 59, 70],
                getLineColor: f => f.id === cfg.iso
                    ? (TRADE_LINE[lv] || TRADE_LINE.blue)
                    : [255, 255, 255, 30],
                pickable: true,
                updateTriggers: { getFillColor: [cfg.iso, lv], getLineColor: [cfg.iso, lv] },
                onClick: () => showClimateWorld(),
            }),
            new ScatterplotLayer({
                id: 'climate-regions',
                data: points,
                pickable: true,
                stroked: true,
                filled: true,
                opacity: 0.92,
                radiusMinPixels: 14,
                radiusMaxPixels: 42,
                lineWidthMinPixels: 2,
                getPosition: d => d.coordinates,
                getRadius: 140000,
                getFillColor: d => d.stress.rgba,
                getLineColor: [255, 255, 255, 220],
                autoHighlight: true,
                highlightColor: [255, 255, 255, 200],
                onClick: info => { if (info.object) updateForecastPanel(info.object.name); },
                onHover: info => {
                    if (!info.object) { hideClimateTooltip(); return; }
                    const d = info.object;
                    tooltipEl.style.left = `${info.x + 10}px`;
                    tooltipEl.style.top = `${info.y + 10}px`;
                    tooltipEl.classList.remove('hidden');
                    const pctStr = d.meanPct == null ? '—'
                        : `${d.meanPct >= 0 ? '+' : ''}${d.meanPct.toFixed(1)}%`;
                    const ptStr = d.point == null ? '—'
                        : (d.unit === 'bu/acre' ? d.point.toFixed(1) : Math.round(d.point).toLocaleString());
                    tooltipEl.innerHTML = `
                        <div class="tooltip-title">${d.label}</div>
                        <div class="tooltip-stat"><span>상태</span>
                            <span class="climate-status-pill ${d.stress.level === 'ok' ? 'green' : d.stress.level === 'high' ? 'red' : 'orange'}">${d.stress.ko}</span></div>
                        <div class="tooltip-stat"><span>예측/기상효과</span>
                            <span>${ptStr} ${d.unit || ''} · ${pctStr}</span></div>`;
                },
            }),
        ],
    });

    await renderCountryPanel(cfg, points, { lv, pol });
};
window.showClimateCountry = showClimateCountry;

const fmtYield = (v, unit) => {
    if (v === null || v === undefined) return '—';
    return unit === 'bu/acre' ? Number(v).toFixed(1) : Math.round(v).toLocaleString();
};

const renderCountryPanel = async (cfg, points = null, meta = {}) => {
    const fc = await loadClimateForecast(cfg);
    const crops = normalizeForecast(fc);
    const lv = meta.lv || tradePolicyLevel(climateCountry);
    const pol = meta.pol || CLIMATE_TRADE_POLICY[climateCountry] || {};
    points = points || await buildRegionPoints(cfg);

    // Left: model brief + structure chips (major only)
    forecastCountryTitle.textContent = cfg.modelName || cfg.label;
    const skillVals = crops.map(c => c.skillVsTrend).filter(v => v != null);
    const meanSkill = skillVals.length
        ? skillVals.reduce((a, b) => a + b, 0) / skillVals.length
        : null;
    const lowN = crops.filter(c => c.lowConfidence).length;

    forecastContentEl.innerHTML = `
        <div class="climate-scroll">
            <div style="font-size:11px;margin-bottom:4px;">
                <span class="climate-back" onclick="showClimateWorld()">← 세계 지도</span>
                <span style="color:#64748b;"> · ${cfg.label}</span>
            </div>
            <div class="climate-card">
                <h3>모델 개요</h3>
                <div style="font-size:13px;color:#e2e8f0;line-height:1.55;">
                    <strong>${cfg.modelName || cfg.label}</strong><br>
                    추세(기술 진보) + 기상 편차 분해. 산지 ${cfg.regions.length}곳 ·
                    작물 슬롯 ${crops.length}개.
                </div>
                <div class="climate-chip-row">
                    <span class="climate-chip">Trend</span>
                    <span class="climate-chip">Weather anomaly</span>
                    <span class="climate-chip">Forward skill</span>
                    <span class="climate-chip">DATA_LAYOUT</span>
                </div>
                <div class="climate-metric-row" style="margin-top:10px;">
                    <span class="nm">무역 상태</span>
                    <span class="climate-status-pill ${lv}">${tradePolicyLabelKo(lv)}</span>
                </div>
                <div class="climate-sub">${pol.note || ''}</div>
            </div>
            <div class="climate-card">
                <h3>검증 요약 (주요만)</h3>
                <div class="climate-metric-row">
                    <span class="nm">평균 skill vs trend</span>
                    <span class="vl">${meanSkill == null ? '—' : (meanSkill * 100).toFixed(0) + '%'}</span>
                </div>
                <div class="climate-metric-row">
                    <span class="nm">신뢰도 낮음 배지</span>
                    <span class="vl">${lowN} / ${crops.length}</span>
                </div>
                <div class="climate-sub">R²·MAPE 상세 차트는 이후 업데이트</div>
            </div>
            <div class="climate-card">
                <h3>산지 바로가기</h3>
                ${cfg.regions.map(r => `
                    <div class="climate-table-row" style="cursor:pointer;"
                         onclick="updateForecastPanel('${r.name.replace(/'/g, "\\'")}')">
                        <span class="nm">${r.label}</span>
                        <span class="vl" style="color:#94a3b8;font-size:11px;">상세 →</span>
                    </div>`).join('')}
            </div>
        </div>`;

    // Right: national aggregates + weather effect table (major)
    if (climateRightTitleEl) climateRightTitleEl.textContent = '국가 집계 · 전망';
    if (climateRightDescEl) climateRightDescEl.textContent = `시즌 ${fc?.season ?? '—'} · 주요 지표만`;
    if (climateRightContentEl) {
        climateRightContentEl.innerHTML = `
            <div class="climate-card">
                <h3>작물 전망</h3>
                ${crops.length ? crops.map(c => {
                    const diff = c.lastActual != null && c.point != null ? c.point - c.lastActual : null;
                    const pct = c.pct;
                    return `<div class="climate-metric-row">
                        <span class="nm">${c.label}${c.lowConfidence ? ' <span style="color:#fbbf24">⚠</span>' : ''}</span>
                        <span class="vl">${c.forecastAvailable === false ? '예측없음' : fmtYield(c.point, c.unit)}
                        ${pct != null ? `<span style="color:${pct < 0 ? '#fca5a5' : '#4ade80'};font-size:11px;">
                            (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)</span>` : ''}
                        </span>
                    </div>
                    <div style="font-size:10px;color:#64748b;margin:-2px 0 6px;">
                        ${c.lastActualYear ?? ''} 실적 ${fmtYield(c.lastActual, c.unit)} ${c.unit || ''}
                        ${diff != null ? ` · Δ ${diff >= 0 ? '+' : ''}${fmtYield(diff, c.unit)}` : ''}
                    </div>`;
                }).join('') : '<div class="climate-sub">forecast JSON 없음 (예: 인도 미배포 시)</div>'}
            </div>
            <div class="climate-card">
                <h3>지역 전망 요약</h3>
                ${points.map(p => `
                    <div class="climate-metric-row">
                        <span class="nm">${p.label}</span>
                        <span class="climate-status-pill ${p.stress.level === 'ok' ? 'green' : p.stress.level === 'high' ? 'red' : p.stress.level === 'warn' ? 'orange' : 'blue'}">${p.stress.ko}</span>
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin:-2px 0 6px;">
                        ${p.meanPct == null ? '기상효과 요약 없음'
                            : `기상효과 ${p.meanPct >= 0 ? '+' : ''}${p.meanPct.toFixed(1)}%`}
                        ${p.point != null ? ` · ${fmtYield(p.point, p.unit)} ${p.unit}` : ''}
                    </div>`).join('')}
            </div>
            <div class="climate-card">
                <h3>가격 민감도 / 파생</h3>
                <div class="climate-sub">국가별 선물 연동·CBOT 시나리오는 추후 업데이트. 현재는 작황 시그널만 제공합니다.</div>
            </div>
            <p style="font-size:10px;color:#64748b;">갱신: ${fc?.generated_at ? new Date(fc.generated_at).toLocaleString() : '—'}</p>`;
    }
    if (climateRightPanelEl) climateRightPanelEl.classList.remove('hidden');
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.add('hidden');
};


// Generic region detail for countries that declare regionKeys
// Generic region detail for countries that declare regionKeys (Argentina,
// Australia, China, Indonesia, and any future country). Brazil/India/US keep
// their richer specialised renderers above; this path only runs when those
// return false.
const renderClimateRegionForecast = async (regionName) => {
    if (climateLevel !== 'country' || !climateCountry) return false;
    const cfg = CLIMATE_COUNTRIES[climateCountry];
    if (!cfg) return false;

    const regionCfg = cfg.regions.find(r => r.name === regionName);
    if (!regionCfg) return false;

    const keys = regionCfg.regionKeys
        || (regionCfg.regionKey ? [regionCfg.regionKey] : null);
    if (!keys?.length) return false;

    const fc = await loadClimateForecast(cfg);
    if (!fc?.regions) return false;

    const crops = normalizeForecast(fc, keys);
    if (!crops.length) return false;

    const fmt = (v, unit) => {
        if (v === null || v === undefined) return '—';
        return unit === 'bu/acre' ? Number(v).toFixed(1) : Math.round(v).toLocaleString();
    };

    let html = '';
    for (const c of crops) {
        const color = c.pct !== null && c.pct < 0 ? '#fca5a5' : '#4ade80';
        const badge = c.lowConfidence
            ? `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(251,191,36,0.15); color:#fbbf24;">신뢰도 낮음
                 ${c.skillVsTrend !== null ? `· skill ${(c.skillVsTrend * 100).toFixed(0)}%` : ''}
                 </span>`
            : `<span style="font-size:10px; padding:2px 6px; border-radius:4px;
                 background:rgba(74,222,128,0.15); color:#4ade80;">검증 통과</span>`;

        html += `
        <div class="indicator-item" style="cursor:default; transform:none; border-color:rgba(255,255,255,0.1);">
            <div class="ind-header"><span class="ind-title">${c.label}</span></div>
            <div style="margin-top:6px;">${badge}</div>
            ${!c.forecastAvailable ? `
            <div style="margin-top:8px; font-size:12px; color:#94a3b8;">
                예측 없음${c.reason ? ` — ${c.reason}` : ''}
                ${c.lastActual !== null ? `<br>${c.lastActualYear ?? ''} 실적 ${fmt(c.lastActual, c.unit)} ${c.unit}` : ''}
            </div>` : `
            <div style="display:flex; justify-content:space-between; margin-top:8px;">
                <div>
                    <span style="font-size:12px; color:#94a3b8;">${c.lastActualYear ?? '—'} 실적</span>
                    <div style="font-size:15px;">${fmt(c.lastActual, c.unit)} ${c.unit}</div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:12px; color:#94a3b8;">${fc.season ?? ''} 예상</span>
                    <div style="font-size:20px; font-weight:bold; color:${c.lowConfidence ? '#cbd5e1' : color};">
                        ${fmt(c.point, c.unit)} ${c.unit}</div>
                </div>
            </div>
            ${c.pct !== null ? `
            <div style="margin-top:8px; font-size:12px; color:${color};">
                기상 효과(추세 대비) ${c.pct >= 0 ? '+' : ''}${c.pct.toFixed(1)}%
            </div>` : ''}
            ${c.reason ? `
            <div style="margin-top:8px; font-size:11px; color:#94a3b8; line-height:1.5;">${c.reason}</div>` : ''}
            `}
        </div>`;
    }

    forecastCountryTitle.textContent =
        `${cfg.label} · ${regionCfg.label}${fc.season ? ` (${fc.season})` : ''}`;
    forecastContentEl.innerHTML = `
        <div class="forecast-box">
            <div class="forecast-item">
                <span class="forecast-label">산지</span>
                <span class="forecast-val" style="font-size:12px;">${regionCfg.label}</span>
            </div>
            <div class="forecast-item">
                <span class="forecast-label">모델 수</span>
                <span class="forecast-val">${crops.length}</span>
            </div>
            <div class="forecast-good" style="margin-top:12px;">
                <strong style="font-size:12px;">${cfg.modelName || cfg.label}</strong><br>
                <span style="font-size:11px; font-weight:400;">
                추세 + 기상편차 분해 · 검증 실패·게이트 정지도 숨기지 않습니다.
                </span>
            </div>
        </div>
        <p style="font-size:11px; color:#94a3b8; text-align:right; margin-top:8px;">
            갱신: ${fc.generated_at ? new Date(fc.generated_at).toLocaleString() : '—'}
        </p>`;

    countryStatsTitleEl.textContent = regionCfg.label;
    document.getElementById('country-stats-desc').textContent =
        '공용 forecast JSON (DATA_LAYOUT) · 국가 파이프라인 산출';
    countryStatsContentEl.innerHTML = html;
    macroPanelEl.classList.add('hidden');
    countryStatsPanelEl.classList.remove('hidden');
    return true;
};

const updateForecastPanel = async (regionName) => {
    if (await renderYieldForecast(regionName)) return;
    if (await renderBrazilYieldForecast(regionName)) return;
    if (await renderIndiaYieldForecast(regionName)) return;
    if (await renderClimateRegionForecast(regionName)) return;

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

const togglePanels = ({ macro = false, countryStats = false, news = false, forecast = false, climateRight = false, left = true, right = true, chart = false, map = true }) => {
    const leftPaneContainer = document.getElementById('left-pane'); // Target the whole container
    const rightPaneContainer = document.getElementById('right-pane');
    const commodityInfoPanel = document.getElementById('commodity-info-panel');
    
    macro ? macroPanelEl.classList.remove('hidden') : macroPanelEl.classList.add('hidden');
    countryStats ? countryStatsPanelEl.classList.remove('hidden') : countryStatsPanelEl.classList.add('hidden');
    news ? newsPanelEl.classList.remove('hidden') : newsPanelEl.classList.add('hidden');
    forecast ? forecastPanelEl.classList.remove('hidden') : forecastPanelEl.classList.add('hidden');
    if (climateRightPanelEl) {
        climateRight ? climateRightPanelEl.classList.remove('hidden') : climateRightPanelEl.classList.add('hidden');
    }
    
    if (left) {
        leftPaneContainer.style.display = 'flex'; // Show the whole container
        commodityInfoPanel.classList.remove('hidden'); // Show info content
    } else {
        leftPaneContainer.style.display = 'none'; // Hide the whole left pane
        commodityInfoPanel.classList.add('hidden');
    }

    rightPaneContainer.style.display = right ? 'flex' : 'none';
    
    chart ? chartView.classList.remove('hidden') : chartView.classList.add('hidden');
    mapContainer.style.display = map ? 'block' : 'none';
};

const setView = (target) => {
    const isShippingView = target && target.startsWith('shipping_');
    if (!isShippingView && window.ShippingDashboard) {
        window.ShippingDashboard.unmount(chartView);
    }

    // Leaving the climate view by the top menu bypasses showClimateWorld(), so
    // reset its state here too -- otherwise climateLevel stays 'country' and a
    // click on some other commodity map would jump back into the climate view.
    if (target !== 'climate') {
        climateLevel = 'world';
        climateCountry = null;
        hideClimateTooltip();
        if (climateMapLegendEl) climateMapLegendEl.classList.add('hidden');
        if (climateRightPanelEl) climateRightPanelEl.classList.add('hidden');
    }

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

    } else if (isShippingView) {
        currentCommodity = target;
        stopRotation();
        deckgl.setProps({ layers: [] });
        togglePanels({ left: false, right: false, chart: true, map: false });
        window.ShippingDashboard.render(target, chartView);

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
        togglePanels({ forecast: true, climateRight: true, left: true, right: true });
        
        currentViewTitle.textContent = '기후·작황 예측';
        currentViewDesc.textContent = '전역 기후 신호 + 모델 국가. hover 요약 · 클릭 상세 · 지도 배경 클릭으로 복귀';
        totalVolumeEl.textContent = `${Object.keys(CLIMATE_COUNTRIES).length}개국`;
        topExporterEl.textContent = 'Status coloring';
        
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
        if (target?.startsWith('shipping_')) {
            window.history.replaceState(null, '', `#/${target}`);
        } else if (window.location.hash.startsWith('#/shipping_')) {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
        setView(target);
    });
});

// Home Logo click event
document.getElementById('home-logo').addEventListener('click', () => {
    if (window.location.hash) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
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

// Live commodity ticker (Worker /api/ticker with locale, static JSON fallback).
// Without this the UI stayed on hardcoded placeholder headlines while CI
// already rebuilt ticker_v1.json.
const loadTicker = async () => {
    const el = document.getElementById('ticker-content');
    if (!el) return;
    let items = null;
    try {
        const res = await fetch('/api/ticker?limit=24');
        if (res.ok) {
            const doc = await res.json();
            items = doc.items || [];
        }
    } catch (_) { /* local file:// or worker missing */ }
    if (!items?.length) {
        try {
            const res = await fetch('/public/data/ticker_v1.json', { cache: 'no-cache' });
            if (res.ok) {
                const doc = await res.json();
                items = doc.items || [];
            }
        } catch (err) {
            console.warn('[ticker] unavailable', err);
            return;
        }
    }
    if (!items?.length) return;

    const parts = items.map((it) => {
        const title = it.display_title
            || (it.title && (it.title.ko || it.title.original))
            || it.title
            || '';
        if (!title) return '';
        const tag = (it.commodities && it.commodities[0])
            || it.category
            || (it.source && it.source.region)
            || '뉴스';
        const safeTag = String(tag).replace(/</g, '');
        const safeTitle = String(title).replace(/</g, '');
        return `<span class="ticker-item"><span class="ticker-hl">[${safeTag}]</span> ${safeTitle}</span>`;
    }).filter(Boolean);

    if (!parts.length) return;
    // Duplicate once so CSS marquee loops without a visible gap.
    el.innerHTML = parts.join('<span class="ticker-divider">·</span>')
        + '<span class="ticker-divider">·</span>'
        + parts.join('<span class="ticker-divider">·</span>');
};

// Initialize a shareable shipping deep link when present; otherwise home.
const initialShippingTarget = window.location.hash.startsWith('#/shipping_')
    ? window.location.hash.slice(2)
    : null;
const initialView = initialShippingTarget && document.querySelector(`[data-target="${initialShippingTarget}"]`)
    ? initialShippingTarget
    : 'home';
setView(initialView);
updateNewsPanel('Global Market');
loadTicker();
