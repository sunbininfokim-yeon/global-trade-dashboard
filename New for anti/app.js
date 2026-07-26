// Application Logic for Global Trade Dashboard
const { DeckGL, PathLayer, ScatterplotLayer } = deck;

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

// Fetch forecast data
fetch('cloudflare_crop_forecast.json')
    .then(response => response.json())
    .then(data => { forecastData = data; })
    .catch(err => console.error("Forecast data load error:", err));

// Mock Data is loaded from data.js
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

// Initialize DeckGL Map
const deckgl = new DeckGL({
    container: 'map',
    mapStyle: mapStyle,
    initialViewState: {
        longitude: 0,
        latitude: 20,
        zoom: 1.5,
        pitch: 0,
        bearing: 0
    },
    controller: true,
    layers: []
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

const updateCountryStatsPanel = (countryName) => {
    if (!currentCommodity || !window.TradeData[currentCommodity]) return;
    
    const commodityData = window.TradeData[currentCommodity];
    const statsData = commodityData.countryStats ? 
        (commodityData.countryStats[countryName] || commodityData.countryStats['default']) : 
        { production: "N/A", import: "N/A", consumption: "N/A", price: "N/A" };
        
    countryStatsTitleEl.textContent = countryName;
    
    countryStatsContentEl.innerHTML = `
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">생산량 (Production)</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.production}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">수입량 (Import)</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.import}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">소비량 (Consumption)</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.consumption}</div>
        </div>
        <div class="indicator-item">
            <div class="ind-header"><span class="ind-title">소비자/수출 가격</span></div>
            <div class="ind-value" style="font-size: 20px;">${statsData.price}</div>
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
        
        // Scale radius differently based on commodity to keep dots visible
        let scaleFactor = 4000;
        if(currentCommodity === 'gold' || currentCommodity === 'silver') scaleFactor = 500;
        else if (currentCommodity === 'oil') scaleFactor = 40000;
        
        return {
            name: country,
            coordinates: window.CountriesData[country],
            radius: Math.max(100000, totalTrade * scaleFactor)
        };
    });
};

// Generate a curved sea route (bezier curve) that mimics avoiding land
const generateSeaRoute = (source, target) => {
    // Hardcoded mock sea routes for demonstration
    // Australia to Japan
    if (source[0] > 130 && source[1] < -20 && target[0] > 130 && target[1] > 30) {
        return [
            source,
            [155, -15], // Coral Sea
            [145, 10],  // Philippine Sea
            target
        ];
    }
    // Indonesia to China
    if (source[0] > 100 && source[0] < 120 && source[1] < 10 && target[0] > 100 && target[1] > 30) {
        return [
            source,
            [115, 15], // South China Sea
            [125, 25], // East China Sea
            target
        ];
    }
    // Default Quadratic Bezier Curve to mimic ocean path (bend east/west)
    const midX = (source[0] + target[0]) / 2;
    const midY = (source[1] + target[1]) / 2;
    // Bend outward based on distance
    const dx = target[0] - source[0];
    const dy = target[1] - source[1];
    const bendFactor = 0.3;
    const controlPoint = [midX - dy * bendFactor, midY + dx * bendFactor];

    const path = [];
    for (let t = 0; t <= 1; t += 0.1) {
        const x = (1 - t) * (1 - t) * source[0] + 2 * (1 - t) * t * controlPoint[0] + t * t * target[0];
        const y = (1 - t) * (1 - t) * source[1] + 2 * (1 - t) * t * controlPoint[1] + t * t * target[1];
        path.push([x, y]);
    }
    return path;
};

const renderMapLayers = (arcs) => {
    // Filter out trades < 1%
    const filteredArcs = arcs.filter(arc => arc.percentage >= 1);
    
    // Attach generated sea routes
    filteredArcs.forEach(arc => {
        if (!arc.path) {
            arc.path = generateSeaRoute(arc.sourcePosition, arc.targetPosition);
        }
    });

    const nodeData = generateNodeData(filteredArcs);

    const pathLayer = new PathLayer({
        id: `path-layer-${currentCommodity}`,
        data: filteredArcs,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 2,
        getPath: d => d.path,
        getColor: d => d.sourceColor,
        getWidth: d => Math.min(Math.max(1.5, d.volume / 15), 8),
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
        radiusMinPixels: 2,
        radiusMaxPixels: 12,
        lineWidthMinPixels: 1,
        getPosition: d => d.coordinates,
        getRadius: d => d.radius,
        getFillColor: [15, 23, 42],
        getLineColor: [255, 255, 255],
        onClick: handleNodeClick
    });

    deckgl.setProps({ layers: [pathLayer, scatterLayer] });
};

// View Switcher Logic
const togglePanels = ({ macro = false, countryStats = false, news = false, forecast = false, left = true, chart = false, map = true }) => {
    const commodityInfoPanel = document.getElementById('commodity-info-panel');
    const leftPane = document.getElementById('left-pane');
    
    macro ? macroPanelEl.classList.remove('hidden') : macroPanelEl.classList.add('hidden');
    countryStats ? countryStatsPanelEl.classList.remove('hidden') : countryStatsPanelEl.classList.add('hidden');
    news ? newsPanelEl.classList.remove('hidden') : newsPanelEl.classList.add('hidden');
    forecast ? forecastPanelEl.classList.remove('hidden') : forecastPanelEl.classList.add('hidden');
    left ? commodityInfoPanel.classList.remove('hidden') : commodityInfoPanel.classList.add('hidden');
    
    // Hide the entire left pane if all its children are hidden
    if (!news && !forecast && !left) {
        leftPane.classList.add('hidden');
    } else {
        leftPane.classList.remove('hidden');
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
        currentCommodity = null;
        togglePanels({ macro: true, left: false });
        
        // Render map with no data layers
        deckgl.setProps({ layers: [] });

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
                radiusScale: 2,
                radiusMinPixels: 5,
                radiusMaxPixels: 15,
                lineWidthMinPixels: 1,
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
        currentViewDesc.textContent = data.desc;
        totalVolumeEl.textContent = data.totalVolume;
        topExporterEl.textContent = data.topExporter;

        // Reset news and map
        updateNewsPanel('Global Market');
        renderMapLayers(data.arcs);

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

// Generate 5-year mock data
const generateMockChartData = (baseValue, volatility) => {
    const labels = [];
    const data = [];
    let currentVal = baseValue;
    
    // Monthly data for 5 years = 60 points
    for (let i = 60; i >= 0; i--) {
        const d = new Date();
        d.setMonth(d.getMonth() - i);
        labels.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
        
        currentVal = currentVal * (1 + (Math.random() * volatility * 2 - volatility));
        data.push(currentVal);
    }
    return { labels, data };
};

const openChartModal = (indicatorTitle, baseValue, volatility) => {
    modalTitle.textContent = `${indicatorTitle} (최근 5년)`;
    chartModal.classList.remove('hidden');
    
    const { labels, data } = generateMockChartData(baseValue, volatility);
    
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
        // Mock base values and volatility based on title
        let baseVal = 100;
        let vol = 0.02;
        if (title.includes('EUR')) { baseVal = 1.1; vol = 0.01; }
        else if (title.includes('JPY')) { baseVal = 140; vol = 0.015; }
        else if (title.includes('NASDAQ')) { baseVal = 12000; vol = 0.03; }
        else if (title.includes('FED')) { baseVal = 8.0; vol = 0.005; }
        else if (title.includes('TGA')) { baseVal = 500; vol = 0.05; }
        
        openChartModal(title, baseVal, vol);
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
        
        if (TradeData[currentCommodity] && TradeData[currentCommodity].arcs) {
            TradeData[currentCommodity].arcs.forEach(arc => {
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
