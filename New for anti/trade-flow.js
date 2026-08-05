// Trade-flow map — flat D3 SVG renderer for commodity views.
//
// Ported from the two local D3 mockups (trade-flow-map.html /
// export-flow-map.html): equirectangular projection, antimeridian-split arcs
// coloured by exporting continent, edge bundling, dash + highlight animation,
// migration-style ribbons on focus. Deliberately no deck.gl and no globe —
// the globe stays on the home view only.
//
// window.TradeFlowMap = { mount, unmount, destroy }
(function () {
    'use strict';

    const TOPO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';

    const CONT = {
        NA: { name: '북아메리카', c: '#e8388a' },
        SA: { name: '남아메리카', c: '#f2743d' },
        AF: { name: '아프리카', c: '#f2c53d' },
        EU: { name: '유럽', c: '#42c164' },
        AS: { name: '아시아', c: '#3273e6' },
        OC: { name: '오세아니아', c: '#7b3fd4' }
    };

    // Continent hubs for edge bundling (mockup 1 values).
    const CONT_HUB = {
        NA: [-100, 45], SA: [-58, -15], AF: [20, 2],
        EU: [15, 50], AS: [85, 35], OC: [135, -25]
    };

    const CONTINENT_BY_NAME = {
        'United States': 'NA', 'USA': 'NA', 'Canada': 'NA', 'Mexico': 'NA',
        'Brazil': 'SA', 'Argentina': 'SA', 'Chile': 'SA', 'Colombia': 'SA',
        'Peru': 'SA', 'Venezuela': 'SA', 'Ecuador': 'SA', 'Uruguay': 'SA',
        'Paraguay': 'SA', 'Bolivia': 'SA', 'Guyana': 'SA',
        'Russia': 'EU', 'Germany': 'EU', 'France': 'EU', 'United Kingdom': 'EU',
        'UK': 'EU', 'Netherlands': 'EU', 'Italy': 'EU', 'Spain': 'EU',
        'Belgium': 'EU', 'Poland': 'EU', 'Norway': 'EU', 'Sweden': 'EU',
        'Finland': 'EU', 'Switzerland': 'EU', 'Austria': 'EU', 'Portugal': 'EU',
        'Greece': 'EU', 'Czechia': 'EU', 'Czech Republic': 'EU', 'Romania': 'EU',
        'Ukraine': 'EU', 'Ireland': 'EU', 'Denmark': 'EU', 'Hungary': 'EU',
        'Belarus': 'EU', 'Turkey': 'EU',
        'Nigeria': 'AF', 'South Africa': 'AF', 'Egypt': 'AF', 'Angola': 'AF',
        'Algeria': 'AF', 'Libya': 'AF', 'Morocco': 'AF', 'Ghana': 'AF',
        'Kenya': 'AF', 'Ethiopia': 'AF', 'Mozambique': 'AF', 'Tanzania': 'AF',
        'Uganda': 'AF', 'Senegal': 'AF', 'Ivory Coast': 'AF', 'Congo DR': 'AF',
        'China': 'AS', 'India': 'AS', 'Japan': 'AS', 'South Korea': 'AS',
        'Korea': 'AS', 'Taiwan': 'AS', 'Singapore': 'AS', 'Thailand': 'AS',
        'Indonesia': 'AS', 'Malaysia': 'AS', 'Vietnam': 'AS', 'Philippines': 'AS',
        'Pakistan': 'AS', 'Bangladesh': 'AS', 'Saudi Arabia': 'AS',
        'United Arab Emirates': 'AS', 'UAE': 'AS', 'Iraq': 'AS', 'Iran': 'AS',
        'Kuwait': 'AS', 'Qatar': 'AS', 'Oman': 'AS', 'Kazakhstan': 'AS',
        'Uzbekistan': 'AS', 'Azerbaijan': 'AS', 'Israel': 'AS', 'Hong Kong': 'AS',
        'Myanmar': 'AS', 'Cambodia': 'AS',
        'Australia': 'OC', 'New Zealand': 'OC', 'Papua New Guinea': 'OC'
    };

    // Rough M49-style bins, used when the country name is unknown.
    const continentFromLonLat = (lon, lat) => {
        if (lon == null || lat == null || Number.isNaN(lon) || Number.isNaN(lat)) return 'AS';
        if (lat < -10 && lon >= 110 && lon <= 180) return 'OC';
        if (lat < -10 && lon >= -180 && lon < -120) return 'OC';
        if (lon >= -170 && lon <= -25) {
            if (lat >= 12) return 'NA';
            if (lat >= 7 && lon >= -90 && lon <= -60) return 'NA';
            return 'SA';
        }
        if (lon >= -25 && lon < 40 && lat >= 36) return 'EU';
        if (lon >= -20 && lon < 52 && lat < 37) return 'AF';
        if (lon >= 110 && lat >= -50 && lat < -10) return 'OC';
        return 'AS';
    };

    const originContinent = (name, pos) => {
        if (name && CONTINENT_BY_NAME[name]) return CONTINENT_BY_NAME[name];
        if (pos && pos.length >= 2) return continentFromLonLat(pos[0], pos[1]);
        return 'AS';
    };

    // Display names. Keys are the canonical English names the app's arc data
    // uses (data.js COUNTRIES), so panel wiring keeps working unchanged.
    const KO = {
        'USA': '미국', 'China': '중국', 'Brazil': '브라질', 'Argentina': '아르헨티나',
        'Russia': '러시아', 'Ukraine': '우크라이나', 'India': '인도', 'Canada': '캐나다',
        'Australia': '호주', 'France': '프랑스', 'Germany': '독일', 'Indonesia': '인도네시아',
        'Malaysia': '말레이시아', 'Thailand': '태국', 'Vietnam': '베트남', 'Egypt': '이집트',
        'Mexico': '멕시코', 'Japan': '일본', 'South Korea': '대한민국', 'UK': '영국',
        'Italy': '이탈리아', 'Spain': '스페인', 'Turkey': '튀르키예',
        'Saudi Arabia': '사우디아라비아', 'UAE': 'UAE', 'South Africa': '남아프리카',
        'Nigeria': '나이지리아', 'Pakistan': '파키스탄', 'Bangladesh': '방글라데시',
        'Philippines': '필리핀', 'Iran': '이란', 'Algeria': '알제리', 'Morocco': '모로코',
        'Poland': '폴란드', 'Netherlands': '네덜란드', 'Belgium': '벨기에',
        'Switzerland': '스위스', 'Colombia': '콜롬비아', 'Peru': '페루', 'Chile': '칠레',
        'New Zealand': '뉴질랜드', 'Kazakhstan': '카자흐스탄', 'Romania': '루마니아',
        'Hungary': '헝가리', 'Belarus': '벨라루스', 'Paraguay': '파라과이',
        'Uruguay': '우루과이', 'Ethiopia': '에티오피아', 'Uganda': '우간다',
        'Qatar': '카타르', 'Norway': '노르웨이', 'Iraq': '이라크', 'Hong Kong': '홍콩',
        'Congo DR': '콩고민주공화국', 'Taiwan': '대만', 'Kenya': '케냐',
        'Tanzania': '탄자니아', 'Myanmar': '미얀마', 'Cambodia': '캄보디아',
        'Ivory Coast': '코트디부아르', 'Ghana': '가나', 'Senegal': '세네갈',
        'Uzbekistan': '우즈베키스탄'
    };
    const ko = (n) => KO[n] || n;

    // world-atlas 110m `properties.name` → canonical app country name.
    // Alternates are listed because Natural Earth renames a few countries
    // between releases and the CDN copy is pinned but the app is not.
    const ATLAS_TO_APP = {
        'United States of America': 'USA', 'United States': 'USA',
        'United Kingdom': 'UK',
        'United Arab Emirates': 'UAE',
        'Dem. Rep. Congo': 'Congo DR', 'Democratic Republic of the Congo': 'Congo DR',
        "Côte d'Ivoire": 'Ivory Coast', 'Ivory Coast': 'Ivory Coast',
        'Turkey': 'Turkey', 'Türkiye': 'Turkey',
        'Czechia': 'Czechia', 'Czech Rep.': 'Czechia',
        'South Korea': 'South Korea', 'Republic of Korea': 'South Korea',
        'Myanmar': 'Myanmar', 'Burma': 'Myanmar'
    };
    // Everything whose atlas name already equals the app name resolves by identity.

    let landPromise = null;
    const loadLand = () => {
        if (!landPromise) {
            landPromise = fetch(TOPO_URL)
                .then((r) => r.json())
                .then((topo) => topojson.feature(topo, topo.objects.countries))
                .catch((err) => {
                    landPromise = null;
                    throw err;
                });
        }
        return landPromise;
    };

    let inst = null;

    const fmtV = (v) => {
        if (!isFinite(v)) return '—';
        if (v >= 1000) return Math.round(v).toLocaleString();
        if (v >= 10) return v.toFixed(0);
        return v.toFixed(2);
    };

    const CONTROLS_HTML = `
        <div class="tf-controls">
            <div class="tf-panel">
                <h3>표현</h3>
                <div class="tf-seg" data-seg="mode">
                    <button type="button" data-mode="arc" class="on">곡선 아크</button>
                    <button type="button" data-mode="bundle">엣지 번들링</button>
                </div>
                <h3>흐름</h3>
                <div class="tf-seg" data-seg="anim">
                    <button type="button" data-anim="off">꺼기</button>
                    <button type="button" data-anim="dash">점선</button>
                    <button type="button" data-anim="pulse" class="on">하이라이트</button>
                </div>
            </div>
            <div class="tf-panel tf-legend-panel">
                <h3>수출 대륙</h3>
                <div class="tf-legend"></div>
            </div>
        </div>
        <svg class="tf-map"></svg>
        <div class="tf-scale"></div>
        <div class="tf-hint">국가 호버 → 교역량 팝업 · 클릭 → 해당 국가 노선만 이동 표식으로 강조 · 배경 클릭 → 초기화</div>
        <div class="tf-tip"></div>
    `;

    function mount(container, options) {
        if (!container) return false;
        if (typeof d3 === 'undefined' || typeof topojson === 'undefined') {
            console.warn('[TradeFlowMap] d3 / topojson-client not loaded');
            return false;
        }
        unmount();

        const opts = options || {};
        const unit = opts.unit || '';
        const routesEl = opts.routesEl || null;
        const onCountrySelect = typeof opts.onCountrySelect === 'function' ? opts.onCountrySelect : null;

        container.innerHTML = CONTROLS_HTML;
        const svg = d3.select(container).select('svg.tf-map');
        const tip = container.querySelector('.tf-tip');
        const legendEl = container.querySelector('.tf-legend');
        const scaleEl = container.querySelector('.tf-scale');

        const gGrid = svg.append('g');
        const gLand = svg.append('g');
        const gFlow = svg.append('g');
        const gRib = svg.append('g');
        const gPulse = svg.append('g');
        const gNode = svg.append('g');
        const gLab = svg.append('g');

        // ---- data -------------------------------------------------------
        // One canonical node per country so an exporter and importer of the
        // same name do not split into two dots (mockup 1 CANON).
        const canon = new Map();
        const nodeOf = (name, pos) => {
            if (!name || !pos || pos.length < 2) return null;
            let n = canon.get(name);
            if (!n) {
                n = { n: name, lon: +pos[0], lat: +pos[1], cont: originContinent(name, pos) };
                canon.set(name, n);
            }
            return n;
        };

        const MAX_FLOWS = 400;
        const flows = [];
        (opts.arcs || [])
            .filter((a) => a && a.volume > 0 && a.sourcePosition && a.targetPosition)
            .slice()
            .sort((a, b) => b.volume - a.volume)
            .slice(0, MAX_FLOWS)
            .forEach((a) => {
                const from = nodeOf(a.sourceName, a.sourcePosition);
                const to = nodeOf(a.targetName, a.targetPosition);
                if (!from || !to || from === to) return;
                flows.push({ from, to, cont: from.cont, v: a.volume, pct: a.percentage });
            });
        // Paint low volume first so the trunk routes land on top.
        flows.sort((a, b) => a.v - b.v);

        const NODE_LIST = [...canon.values()];
        const vols = flows.map((f) => f.v);
        const vLo = vols.length ? d3.min(vols) : 0;
        const vHi = vols.length ? (d3.quantile(vols, 0.98) || d3.max(vols)) : 1;
        const wScale = d3.scaleSqrt().domain([vLo, vHi]).range([0.45, 6.5]).clamp(true);
        const oScale = d3.scaleSqrt().domain([vLo, vHi]).range([0.3, 0.9]).clamp(true);
        const rwScale = d3.scaleSqrt()
            .domain([vLo, vols.length ? (d3.quantile(vols, 0.93) || vHi) : 1])
            .range([3.5, 24]).clamp(true);

        let mode = 'arc';
        let anim = 'pulse';
        let focus = null;
        let projection = null;
        let W = 0;
        let H = 0;
        let land = null;
        let landSel = null;
        let ro = null;
        let destroyed = false;
        const active = new Set(Object.keys(CONT));

        // ---- chrome -----------------------------------------------------
        Object.entries(CONT).forEach(([k, v]) => {
            const el = document.createElement('div');
            el.className = 'tf-lg';
            el.innerHTML = `<span class="tf-bar" style="background:${v.c}"></span>${v.name}`;
            el.addEventListener('click', () => {
                if (active.has(k)) active.delete(k);
                else active.add(k);
                el.classList.toggle('off');
                paint();
            });
            legendEl.appendChild(el);
        });

        const scaleRow = (px) => {
            const v = wScale.invert(px);
            return `<div class="tf-scale-row"><i style="width:26px;height:${px}px"></i>` +
                `<span>${fmtV(v)}${unit ? ' ' + unit : ''}</span></div>`;
        };
        scaleEl.innerHTML = scaleRow(1) + scaleRow(3) +
            `<div class="tf-scale-row"><i style="width:26px;height:6px"></i>` +
            `<span>${fmtV(vHi)}${unit ? ' ' + unit : ''} 이상</span></div>`;

        container.querySelectorAll('.tf-seg[data-seg="mode"] button').forEach((b) => {
            b.addEventListener('click', () => {
                container.querySelectorAll('.tf-seg[data-seg="mode"] button')
                    .forEach((x) => x.classList.remove('on'));
                b.classList.add('on');
                mode = b.dataset.mode;
                paint();
            });
        });
        container.querySelectorAll('.tf-seg[data-seg="anim"] button').forEach((b) => {
            b.addEventListener('click', () => {
                container.querySelectorAll('.tf-seg[data-seg="anim"] button')
                    .forEach((x) => x.classList.remove('on'));
                b.classList.add('on');
                anim = b.dataset.anim;
                paint();
            });
        });

        const onStageClick = (e) => {
            if (e.target.closest('.tf-controls') || e.target.closest('.tf-route')) return;
            if (e.target.classList && e.target.classList.contains('tf-node')) return;
            if (e.target.dataset && e.target.dataset.hit === 'land') return;
            setFocus(null);
        };
        container.addEventListener('click', onStageClick);

        // ---- left-panel route list --------------------------------------
        const byExporter = d3.rollups(flows, (g) => d3.sum(g, (d) => d.v), (f) => f.from.n)
            .sort((a, b) => b[1] - a[1]).slice(0, 10);

        const renderRoutes = () => {
            if (!routesEl) return;
            routesEl.innerHTML = byExporter.map(([name, v]) => {
                const c = CONT[canon.get(name)?.cont || 'AS'].c;
                return `<div class="tf-route${focus === name ? ' on' : ''}" data-name="${name}">
                    <span class="tf-dot" style="background:${c}"></span>
                    <span class="tf-route-lbl">${ko(name)}</span>
                    <span class="tf-route-val">${fmtV(v)}${unit ? ' ' + unit : ''}</span>
                </div>`;
            }).join('') || '<p class="empty-state">표시할 무역 루트가 없습니다.</p>';
            routesEl.querySelectorAll('.tf-route').forEach((row) => {
                row.addEventListener('click', (e) => {
                    e.stopPropagation();
                    setFocus(focus === row.dataset.name ? null : row.dataset.name);
                });
            });
        };

        const syncRouteRows = () => {
            if (!routesEl) return;
            routesEl.querySelectorAll('.tf-route').forEach((row) => {
                row.classList.toggle('on', row.dataset.name === focus);
            });
        };

        function setFocus(name) {
            if (focus === name) return;
            focus = name;
            syncRouteRows();
            paint();
            if (name && onCountrySelect) onCountrySelect(name);
        }

        // ---- geometry helpers (mockup 1) --------------------------------
        function segs(pts) {
            const out = [[]];
            for (let i = 0; i < pts.length; i++) {
                if (i && Math.abs(pts[i][0] - pts[i - 1][0]) > W * 0.45) out.push([]);
                out[out.length - 1].push(pts[i]);
            }
            return out.filter((s) => s.length > 1);
        }
        function arcPtsAB(a, b, bowF) {
            const ip = d3.geoInterpolate(a, b);
            const n = 56;
            const pts = [];
            for (let i = 0; i <= n; i++) pts.push(projection(ip(i / n)));
            const p0 = pts[0];
            const pn = pts[n];
            const dx = pn[0] - p0[0];
            const dy = pn[1] - p0[1];
            const len = Math.hypot(dx, dy) || 1;
            const nx = -dy / len;
            const ny = dx / len;
            const bow = Math.min(len * bowF, 190);
            return pts.map((p, i) => {
                const k = Math.sin(Math.PI * i / n) * bow;
                return [p[0] + nx * k, p[1] + ny * k];
            });
        }
        const arcPts = (f) => arcPtsAB([f.from.lon, f.from.lat], [f.to.lon, f.to.lat], 0.13);
        function bundlePts(f) {
            const a = [f.from.lon, f.from.lat];
            const b = [f.to.lon, f.to.lat];
            const via = [a, CONT_HUB[f.cont] || a, CONT_HUB[f.to.cont] || b, b];
            const pts = [];
            for (let s = 0; s < via.length - 1; s++) {
                const ip = d3.geoInterpolate(via[s], via[s + 1]);
                const n = 18;
                for (let i = (s ? 1 : 0); i <= n; i++) pts.push(projection(ip(i / n)));
            }
            return pts;
        }
        // Migration-map ribbon: wide at the origin, arrowhead at the target.
        function ribbonAB(a, b, w0, bowF, head) {
            const all = segs(arcPtsAB(a, b, bowF));
            if (!all.length) return null;
            return all.map((s, i) => ribbonSeg(s, w0, head && i === all.length - 1))
                .filter(Boolean).join(' ');
        }
        function ribbonSeg(pts, w0, withHead) {
            const n = pts.length - 1;
            if (n < 2) return null;
            const head = withHead ? 0.86 : 1;
            const L = [];
            const R = [];
            const norm = (i) => {
                const a = pts[Math.max(0, i - 1)];
                const b = pts[Math.min(n, i + 1)];
                const dx = b[0] - a[0];
                const dy = b[1] - a[1];
                const l = Math.hypot(dx, dy) || 1;
                return [-dy / l, dx / l];
            };
            const iHead = withHead ? Math.min(n - 1, Math.floor(n * head)) : n;
            for (let i = 0; i <= iHead; i++) {
                const t = i / n;
                const [nx, ny] = norm(i);
                const w = w0 * (1 - 0.45 * Math.min(1, t / head)) / 2;
                L.push([pts[i][0] + nx * w, pts[i][1] + ny * w]);
                R.push([pts[i][0] - nx * w, pts[i][1] - ny * w]);
            }
            const [hx, hy] = norm(iHead);
            const hw = w0 * 1.45;
            const tipPt = pts[n];
            const c = d3.line().curve(d3.curveCatmullRom.alpha(0.6));
            if (!withHead) return c(L) + 'L' + c(R.slice().reverse()).slice(1) + 'Z';
            return c(L) + 'L' + (pts[iHead][0] + hx * hw) + ',' + (pts[iHead][1] + hy * hw)
                + 'L' + tipPt[0] + ',' + tipPt[1]
                + 'L' + (pts[iHead][0] - hx * hw) + ',' + (pts[iHead][1] - hy * hw)
                + 'L' + c(R.slice().reverse()).slice(1) + 'Z';
        }
        const lineArc = d3.line().curve(d3.curveBasis);
        const lineBun = d3.line().curve(d3.curveBundle.beta(0.82));

        // ---- land / tooltip ---------------------------------------------
        const toNode = (atlasName) => {
            if (!atlasName) return null;
            const key = ATLAS_TO_APP[atlasName] || atlasName;
            return canon.has(key) ? key : null;
        };

        function paintLand(hoverName) {
            if (!landSel) return;
            landSel.attr('fill', (d) => {
                const n = toNode(d.properties.name);
                if (n && n === focus) return '#3a4a5e';
                if (n && n === hoverName) return '#2c3a4c';
                return n ? '#1f2a38' : '#161e29';
            }).attr('stroke', (d) => {
                const n = toNode(d.properties.name);
                return n === focus ? '#8fc0ff' : (n === hoverName ? '#5a6b80' : '#2b3746');
            }).attr('stroke-width', (d) => (toNode(d.properties.name) === focus ? 1.2 : 0.6));
        }

        const showTip = (ev, html) => {
            const r = container.getBoundingClientRect();
            tip.style.opacity = 1;
            tip.style.left = (ev.clientX - r.left) + 'px';
            tip.style.top = (ev.clientY - r.top - 6) + 'px';
            tip.innerHTML = html;
        };
        const hideTip = () => { tip.style.opacity = 0; };

        const totalsFor = (name) => {
            let ex = 0;
            let im = 0;
            flows.forEach((f) => {
                if (!active.has(f.cont)) return;
                if (f.from.n === name) ex += f.v;
                if (f.to.n === name) im += f.v;
            });
            return { ex, im };
        };

        const tipHtml = (name, exv, imv) => {
            const cont = canon.get(name)?.cont || 'AS';
            return `<b>${ko(name)}</b> <span class="n">· ${CONT[cont].name}</span><br>` +
                `<span class="n">수출 ${fmtV(exv)} · 수입 ${fmtV(imv)}${unit ? ' ' + unit : ''}</span><br>` +
                '<span class="n">클릭 → 교역 노선 보기</span>';
        };

        // ---- paint -------------------------------------------------------
        function paint() {
            if (!projection) return;
            paintLand(null);
            const shown = flows.filter((f) => active.has(f.cont));
            const gen = mode === 'arc' ? lineArc : lineBun;

            const sel = gFlow.selectAll('path').data(shown, (d) => d.from.n + '>' + d.to.n);
            sel.exit().remove();
            sel.enter().append('path').attr('class', 'tf-flow').merge(sel)
                .attr('d', (f) => segs(mode === 'arc' ? arcPts(f) : bundlePts(f)).map((s) => gen(s)).join(' '))
                .attr('stroke', (f) => CONT[f.cont].c)
                .attr('stroke-width', (f) => wScale(f.v))
                .attr('stroke-opacity', (f) => (focus
                    ? (f.from.n === focus ? 0 : (f.to.n === focus ? oScale(f.v) * 0.55 : 0.035))
                    : oScale(f.v)))
                .attr('stroke-dasharray', (f) => ((!focus && anim === 'dash')
                    ? `${wScale(f.v) * 3.4} ${wScale(f.v) * 6}` : null))
                .style('animation', (f) => ((!focus && anim === 'dash')
                    ? `tfdash ${9 + (1 - oScale(f.v)) * 20}s linear infinite` : null));

            // Focus: thick trunk out of the origin that splits per destination.
            const parts = [];
            if (focus) {
                const org = canon.get(focus);
                if (org) {
                    const o = [org.lon, org.lat];
                    const outs = shown.filter((f) => f.from.n === focus);
                    d3.groups(outs, (f) => f.to.cont).forEach(([cont, list]) => {
                        const total = d3.sum(list, (f) => f.v);
                        const branch = list.length > 1;
                        const mid = [d3.mean(list, (f) => f.to.lon), d3.mean(list, (f) => f.to.lat)];
                        const sp = branch ? d3.geoInterpolate(o, mid)(0.34) : o;
                        if (branch) {
                            parts.push({ id: 'trunk-' + cont, a: o, b: sp, w: rwScale(total), cont, head: false, bow: 0.05 });
                        }
                        list.forEach((f) => parts.push({
                            id: cont + '>' + f.to.n,
                            a: sp,
                            b: [f.to.lon, f.to.lat],
                            w: rwScale(f.v),
                            cont,
                            head: true,
                            bow: branch ? 0.11 : 0.2
                        }));
                    });
                }
            }
            const rs = gRib.selectAll('path').data(parts, (p) => p.id);
            rs.exit().remove();
            rs.enter().append('path').merge(rs)
                .attr('d', (p) => ribbonAB(p.a, p.b, p.w, p.bow, p.head))
                .attr('fill', (p) => CONT[p.cont].c)
                .attr('fill-opacity', 0.66)
                .attr('stroke', (p) => CONT[p.cont].c)
                .attr('stroke-opacity', 0.9)
                .attr('stroke-width', 0.8);

            // Highlight sweep: short white dashes running along the top routes.
            const sweep = focus ? [] : (anim === 'pulse' ? shown.slice(-26) : []);
            const ov = gPulse.selectAll('path').data(sweep, (d) => 'p' + d.from.n + '>' + d.to.n);
            ov.exit().remove();
            ov.enter().append('path').attr('class', 'tf-flow').merge(ov)
                .attr('d', (f) => segs(mode === 'arc' ? arcPts(f) : bundlePts(f)).map((s) => gen(s)).join(' '))
                .attr('stroke', '#ffffff')
                .attr('stroke-width', (f) => wScale(f.v) * 0.55)
                .attr('stroke-opacity', 0.55)
                .attr('stroke-dasharray', '26 460')
                .style('animation', (f, i) => `tfdash ${11 + (i % 7) * 1.6}s linear infinite`);

            const nodes = NODE_LIST.map((a) => {
                let ex = 0;
                let im = 0;
                shown.forEach((f) => {
                    if (f.from.n === a.n) ex += f.v;
                    if (f.to.n === a.n) im += f.v;
                });
                return { ...a, exv: ex, imv: im, ex: ex >= im, v: ex + im };
            }).filter((d) => d.v > 0);

            const maxNode = d3.max(nodes, (d) => d.v) || 1;
            const r = d3.scaleSqrt().domain([0, maxNode]).range([2, 9.5]).clamp(true);
            const ns = gNode.selectAll('circle').data(nodes, (d) => d.n);
            ns.exit().remove();
            ns.enter().append('circle').attr('class', 'tf-node')
                .on('mousemove', (ev, d) => showTip(ev, tipHtml(d.n, d.exv, d.imv)))
                .on('mouseleave', hideTip)
                .on('click', (ev, d) => {
                    ev.stopPropagation();
                    setFocus(focus === d.n ? null : d.n);
                })
                .merge(ns)
                .attr('cx', (d) => projection([d.lon, d.lat])[0])
                .attr('cy', (d) => projection([d.lon, d.lat])[1])
                .attr('r', (d) => r(d.v))
                .attr('fill', (d) => (d.ex ? CONT[d.cont].c : '#0b1017'))
                .attr('fill-opacity', (d) => (d.ex ? 0.9 : 1))
                .attr('stroke', (d) => (d.ex ? '#fff' : CONT[d.cont].c))
                .attr('stroke-opacity', (d) => (focus && d.n !== focus ? 0.25 : 0.85))
                .attr('stroke-width', (d) => (d.ex ? 0.8 : 1.3));

            // Labels: focus + its destinations first, then de-collided vertically.
            const dests = new Set();
            if (focus) shown.forEach((f) => { if (f.from.n === focus) dests.add(f.to.n); });
            const rank = (d) => (d.n === focus ? 2 : (dests.has(d.n) ? 1 : 0));
            const labs = nodes.slice().sort((a, b) => (rank(b) - rank(a)) || (b.v - a.v));
            const cx = W / 2;
            const picked = [];
            const placed = [];
            const limit = focus ? 8 : 6;
            labs.forEach((d) => {
                const p = projection([d.lon, d.lat]);
                const right = p[0] <= cx;
                const must = d.n === focus;
                if (!must && picked.length >= limit) return;
                if (focus && !must && !dests.has(d.n)) return;
                let y = p[1] + 3.5;
                for (let pass = 0; pass < 24; pass++) {
                    const hit = placed.find((q) => Math.abs(q.y - y) < 13
                        && Math.abs(q.x - (right ? p[0] + 11 : p[0] - 11)) < 76);
                    if (!hit) break;
                    y = hit.y + 13;
                }
                const rec = { d, x: right ? p[0] + 11 : p[0] - 11, y, right };
                picked.push(rec);
                placed.push(rec);
            });
            const ls = gLab.selectAll('text').data(picked, (rec) => (rec.d.ex ? 'x' : 'm') + rec.d.n);
            ls.exit().remove();
            ls.enter().append('text').attr('class', 'tf-label')
                .attr('font-size', 10.5).attr('font-weight', 600)
                .attr('paint-order', 'stroke').attr('stroke', '#080b11').attr('stroke-width', 3.2)
                .merge(ls)
                .attr('x', (rec) => rec.x).attr('y', (rec) => rec.y)
                .attr('text-anchor', (rec) => (rec.right ? 'start' : 'end'))
                .attr('fill', (rec) => (rec.d.n === focus ? '#fff' : (rec.d.ex ? '#e6edf6' : '#aeb9c6')))
                .text((rec) => ko(rec.d.n));
        }

        function render() {
            if (destroyed) return;
            W = container.clientWidth;
            H = container.clientHeight;
            if (!W || !H) return;
            svg.attr('viewBox', `0 0 ${W} ${H}`);
            const top = (container.querySelector('.tf-controls')?.offsetHeight || 46) + 14;
            projection = d3.geoEquirectangular()
                .fitExtent([[24, top], [W - 24, H - 34]], { type: 'Sphere' });
            const path = d3.geoPath(projection);
            gGrid.selectAll('*').remove();
            gLand.selectAll('*').remove();
            gGrid.append('path').attr('d', path({ type: 'Sphere' }))
                .attr('fill', '#0c1219').attr('stroke', 'rgba(255,255,255,.09)');
            gGrid.append('path').attr('d', path(d3.geoGraticule10()))
                .attr('fill', 'none').attr('stroke', 'rgba(255,255,255,.05)');
            if (land) {
                landSel = gLand.selectAll('path').data(land.features).join('path')
                    .attr('d', path)
                    .attr('data-hit', 'land')
                    .style('cursor', (d) => (toNode(d.properties.name) ? 'pointer' : 'default'))
                    .on('mousemove', (ev, d) => {
                        const n = toNode(d.properties.name);
                        if (!n) { hideTip(); paintLand(null); return; }
                        paintLand(n);
                        const t = totalsFor(n);
                        showTip(ev, tipHtml(n, t.ex, t.im));
                    })
                    .on('mouseleave', () => { hideTip(); paintLand(null); })
                    .on('click', (ev, d) => {
                        const n = toNode(d.properties.name);
                        if (!n) return;
                        ev.stopPropagation();
                        setFocus(focus === n ? null : n);
                    });
            }
            paint();
        }

        renderRoutes();
        render();

        loadLand().then((features) => {
            if (destroyed) return;
            land = features;
            render();
        }).catch((err) => console.warn('[TradeFlowMap] world atlas load failed', err));

        ro = new ResizeObserver(() => render());
        ro.observe(container);

        inst = {
            container,
            teardown() {
                destroyed = true;
                if (ro) { ro.disconnect(); ro = null; }
                container.removeEventListener('click', onStageClick);
                container.innerHTML = '';
                if (routesEl) routesEl.innerHTML = '';
            }
        };
        return true;
    }

    function unmount() {
        if (!inst) return;
        try { inst.teardown(); } catch (err) { console.warn('[TradeFlowMap] teardown', err); }
        inst = null;
    }

    function destroy() {
        unmount();
        landPromise = null;
    }

    window.TradeFlowMap = {
        mount,
        unmount,
        destroy,
        CONT,
        originContinent,
        koName: ko,
        isMounted: () => !!inst
    };
})();
