// ==========================================
// Mock Data Structure for Global Trade Dashboard
// ==========================================

// 1. 공통 국가 좌표 [longitude, latitude]
const COUNTRIES = {
    "Australia": [151.7817, -32.9283], // Newcastle Port
    "Indonesia": [106.8828, -6.1039], // Tanjung Priok (Jakarta)
    "Russia": [132.8933, 42.8105], // Nakhodka (East)
    "USA": [-94.9774, 29.6848], // Houston Port
    "South Africa": [32.0436, -28.7942], // Richards Bay
    "China": [121.9426, 30.8653], // Yangshan (Shanghai)
    "India": [72.9490, 18.9496], // Nhava Sheva (Mumbai)
    "Japan": [139.7753, 35.6171], // Tokyo Port
    "South Korea": [129.0833, 35.1028], // Busan Port
    "Colombia": [-74.2255, 11.2404], // Santa Marta
    "Ethiopia": [41.8387, 11.5950], // Djibouti (Port for Ethiopia)
    "Uganda": [39.6682, -4.0435], // Mombasa (Port for Uganda)
    "UAE": [56.3414, 25.1666], // Fujairah

    
    // Regions for Climate Model
    "Mato Grosso (Brazil)": [-56.9211, -12.6819],
    "Rio Grande do Sul (Brazil)": [-53.2000, -30.0346],
    "Iowa (USA)": [-93.0977, 41.8780],
    "Pampas (Argentina)": [-62.0000, -35.0000],
    "Sumatra (Indonesia)": [101.6865, -0.5897],
    "Germany": [10.4515, 51.1657],
    "Netherlands": [5.2913, 52.1326],
    "Brazil": [-46.2973, -23.9717], // Santos Port
    "Saudi Arabia": [50.1584, 26.6575], // Ras Tanura
    "Canada": [-123.1162, 49.2827], // Vancouver
    "Switzerland": [8.5417, 47.3769], // Zurich (Inland)
    "UK": [1.2950, 51.9540], // Felixstowe
    "Peru": [-77.1466, -12.0528], // Callao
    "Chile": [-71.6214, -33.0472], // Valparaiso
    "Argentina": [-58.3772, -34.6037], // Buenos Aires
    "Vietnam": [106.7381, 10.7590] // Ho Chi Minh (Cat Lai)
};

// 2. 주요 항구 다중 좌표 (항구 중심 무역)
const PORTS = {
    "Australia": [
        {name: "Newcastle", coord: [151.7817, -32.9283]},
        {name: "Port Hedland", coord: [118.5755, -20.3138]},
        {name: "Brisbane", coord: [153.1670, -27.3820]}
    ],
    "South Korea": [
        {name: "Busan", coord: [129.0833, 35.1028]},
        {name: "Incheon", coord: [126.6025, 37.4562]},
        {name: "Yeosu", coord: [127.7669, 34.7604]} 
    ],
    "China": [
        {name: "Shanghai", coord: [121.9426, 30.8653]},
        {name: "Ningbo", coord: [121.8540, 29.9328]},
        {name: "Qingdao", coord: [120.3200, 36.0691]}
    ],
    "USA": [
        {name: "Houston", coord: [-94.9774, 29.6848]},
        {name: "Los Angeles", coord: [-118.2590, 33.7292]},
        {name: "New York", coord: [-74.0060, 40.7128]}
    ],
    "Japan": [
        {name: "Tokyo", coord: [139.7753, 35.6171]},
        {name: "Yokohama", coord: [139.6542, 35.4526]},
        {name: "Kobe", coord: [135.2167, 34.6667]}
    ],
    "Brazil": [
        {name: "Santos", coord: [-46.2973, -23.9717]},
        {name: "Paranagua", coord: [-48.5139, -25.5033]}
    ]
};

// 3. 유틸리티 함수 (랜덤 모의 데이터 생성)
const generateMockArcs = (sources, targets, minVol, maxVol, colorType) => {
    const arcs = [];
    sources.forEach(source => {
        targets.forEach(target => {
            if(source === target) return;
            
            const sourcePorts = PORTS[source] || [{name: "Main", coord: COUNTRIES[source]}];
            const targetPorts = PORTS[target] || [{name: "Main", coord: COUNTRIES[target]}];
            
            sourcePorts.forEach(sPort => {
                targetPorts.forEach(tPort => {
                    // 랜덤하게 연결 생성 (확률 조정)
                    if(Math.random() > 0.6) {
                        const vol = Math.floor(Math.random() * (maxVol - minVol)) + minVol;
                        
                        // Color preset
                        let sColor, tColor;
                        if(colorType === 'energy') { sColor = [239, 68, 68]; tColor = [248, 113, 113]; }
                        else if(colorType === 'precious') { sColor = [250, 204, 21]; tColor = [253, 224, 71]; }
                        else if(colorType === 'metals') { sColor = [14, 165, 233]; tColor = [56, 189, 248]; }
                        else if(colorType === 'agri') { sColor = [34, 197, 94]; tColor = [74, 222, 128]; }
                        else { sColor = [255, 140, 0]; tColor = [250, 204, 21]; } // Default

                        arcs.push({
                            sourceName: sPort.name === "Main" ? source : `${source} (${sPort.name})`,
                            targetName: tPort.name === "Main" ? target : `${target} (${tPort.name})`,
                            sourcePosition: sPort.coord,
                            targetPosition: tPort.coord,
                            volume: vol,
                            percentage: Math.floor(Math.random() * 40) + 10,
                            typeName: "General",
                            sourceColor: sColor,
                            targetColor: tColor
                        });
                    }
                });
            });
        });
    });
    return arcs;
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

// ==========================================
// 3. 상품별 데이터 베이스 (TradeData)
// ==========================================
window.TradeData = {
    // --------------------------------
    // 기타 원자재: 석탄 (기존) -> 에너지 산하로 분리
    // --------------------------------
    thermal_coal: {
        title: "에너지: 연료탄 (Thermal Coal)",
        desc: "전 세계 발전용 연료탄 수출입 무역 흐름",
        totalVolume: "980 Mt",
        topExporter: "인도네시아",
        arcs: [
            { sourceName: "Australia", targetName: "Japan", sourcePosition: COUNTRIES["Australia"], targetPosition: COUNTRIES["Japan"], volume: 80, percentage: 25, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "Indonesia", targetName: "India", sourcePosition: COUNTRIES["Indonesia"], targetPosition: COUNTRIES["India"], volume: 120, percentage: 28, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "Russia", targetName: "China", sourcePosition: COUNTRIES["Russia"], targetPosition: COUNTRIES["China"], volume: 30, percentage: 15, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "South Africa", targetName: "India", sourcePosition: COUNTRIES["South Africa"], targetPosition: COUNTRIES["India"], volume: 40, percentage: 12, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "South Africa", targetName: "UAE", sourcePosition: COUNTRIES["South Africa"], targetPosition: COUNTRIES["UAE"], volume: 15, percentage: 4, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "Colombia", targetName: "Netherlands", sourcePosition: COUNTRIES["Colombia"], targetPosition: COUNTRIES["Netherlands"], volume: 20, percentage: 6, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] },
            { sourceName: "Indonesia", targetName: "South Korea", sourcePosition: COUNTRIES["Indonesia"], targetPosition: COUNTRIES["South Korea"], volume: 35, percentage: 10, typeName: '연료탄 (Thermal)', sourceColor: [255, 140, 0], targetColor: [250, 204, 21] }
        ],
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
        arcs: [
            { sourceName: "Australia", targetName: "China", sourcePosition: COUNTRIES["Australia"], targetPosition: COUNTRIES["China"], volume: 55, percentage: 16, typeName: '원료탄 (Metallurgical)', sourceColor: [147, 51, 234], targetColor: [236, 72, 153] },
            { sourceName: "USA", targetName: "Netherlands", sourcePosition: COUNTRIES["USA"], targetPosition: COUNTRIES["Netherlands"], volume: 15, percentage: 18, typeName: '원료탄 (Metallurgical)', sourceColor: [147, 51, 234], targetColor: [236, 72, 153] },
            { sourceName: "Brazil", targetName: "China", sourcePosition: COUNTRIES["Brazil"], targetPosition: COUNTRIES["China"], volume: 5, percentage: 50, typeName: '원료탄 (Metallurgical)', sourceColor: [147, 51, 234], targetColor: [236, 72, 153] }
        ],
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
    // --------------------------------
    // 에너지: 원유
    // --------------------------------
    oil: {
        title: "글로벌 에너지: 원유",
        desc: "전 세계 주요 산유국 및 소비국 간 원유 물동량 흐름",
        totalVolume: "98.5 Million bpd",
        topExporter: "사우디아라비아",
        arcs: generateMockArcs(["Saudi Arabia", "USA", "Russia", "Brazil"], ["China", "India", "Japan", "South Korea", "Germany"], 10, 100, 'energy'),
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
    // --------------------------------
    // 귀금속: 금, 은
    // --------------------------------
    gold: {
        title: "글로벌 귀금속: 금 (Gold)",
        desc: "스위스 정련소 및 주요 소비국 간의 금 무역 흐름",
        totalVolume: "4,741 Tonnes",
        topExporter: "스위스",
        arcs: generateMockArcs(["Switzerland", "UK", "USA", "Australia"], ["China", "India", "UAE", "Germany"], 50, 300, 'precious'),
        news: defaultNews("Gold")
    },
    silver: {
        title: "글로벌 귀금속: 은 (Silver)",
        desc: "산업용 및 투자용 은 글로벌 무역 흐름",
        totalVolume: "32,000 Tonnes",
        topExporter: "멕시코 / 페루",
        arcs: generateMockArcs(["Peru", "Chile", "China"], ["USA", "Japan", "South Korea", "Germany"], 100, 500, 'precious'),
        news: defaultNews("Silver")
    },
    // --------------------------------
    // 비철금속: 구리, 아연, 알루미늄
    // --------------------------------
    copper: {
        title: "글로벌 비철금속: 구리 (Copper)",
        desc: "전기차/인프라 핵심 소재인 구리의 물동량 (정광 및 제련)",
        totalVolume: "26.5 Million Tonnes",
        topExporter: "칠레",
        arcs: generateMockArcs(["Chile", "Peru", "Australia"], ["China", "USA", "Japan", "South Korea"], 500, 2000, 'metals'),
        news: defaultNews("Copper")
    },
    zinc: {
        title: "글로벌 비철금속: 아연 (Zinc)",
        desc: "도금용 주요 소재 아연 무역 흐름",
        totalVolume: "13.2 Million Tonnes",
        topExporter: "호주",
        arcs: generateMockArcs(["Australia", "Peru", "USA"], ["China", "South Korea", "Germany"], 200, 1000, 'metals'),
        news: defaultNews("Zinc")
    },
    aluminum: {
        title: "글로벌 비철금속: 알루미늄",
        desc: "경량화 핵심 소재 알루미늄 무역 흐름",
        totalVolume: "68.9 Million Tonnes",
        topExporter: "중국 (가공품)",
        arcs: generateMockArcs(["China", "Russia", "Canada"], ["USA", "Japan", "Germany", "South Korea"], 300, 1500, 'metals'),
        news: defaultNews("Aluminum")
    },
    // --------------------------------
    // 농산물: 밀, 옥수수, 대두, 설탕, 커피
    // --------------------------------
    wheat: {
        title: "글로벌 농산물: 밀 (Wheat)",
        desc: "글로벌 주요 식량 자원인 밀의 무역 흐름",
        totalVolume: "215 Million Tonnes",
        topExporter: "러시아",
        arcs: generateMockArcs(["Russia", "USA", "Australia", "Canada"], ["China", "Brazil", "Japan"], 1000, 5000, 'agri'),
        news: defaultNews("Wheat")
    },
    corn: {
        title: "글로벌 농산물: 옥수수 (Corn)",
        desc: "사료 및 바이오연료용 옥수수 무역 흐름",
        totalVolume: "190 Million Tonnes",
        topExporter: "미국",
        arcs: generateMockArcs(["USA", "Brazil", "Argentina"], ["China", "Japan", "South Korea"], 1500, 6000, 'agri'),
        news: defaultNews("Corn")
    },
    soybeans: {
        title: "글로벌 농산물: 대두 (Soybeans)",
        desc: "단백질 사료 및 식용유의 핵심, 대두 무역 흐름",
        totalVolume: "172 Million Tonnes",
        topExporter: "브라질",
        arcs: generateMockArcs(["Brazil", "USA", "Argentina"], ["China", "Netherlands", "Japan"], 2000, 8000, 'agri'),
        news: defaultNews("Soybeans")
    },
    sugar: {
        title: "글로벌 농산물: 설탕 (Sugar)",
        desc: "사탕수수 기반 설탕 수출입 무역 흐름",
        totalVolume: "64 Million Tonnes",
        topExporter: "브라질",
        arcs: generateMockArcs(["Brazil", "India"], ["USA", "China", "Indonesia"], 500, 2500, 'agri'),
        news: defaultNews("Sugar")
    },
    coffee: {
        title: "글로벌 농산물: 커피 (Coffee)",
        desc: "전 세계 원두(아라비카/로부스타) 수출입 무역 흐름",
        totalVolume: "140 Million Bags",
        topExporter: "브라질 / 에티오피아",
        arcs: generateMockArcs(["Brazil", "Vietnam", "Indonesia", "Ethiopia", "Uganda", "Colombia"], ["USA", "Germany", "Japan", "South Korea", "UAE"], 200, 1200, 'agri'),
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

window.CountriesData = COUNTRIES;
