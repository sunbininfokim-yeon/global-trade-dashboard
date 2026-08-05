// 기후 세계지도의 해양 레이어 블록.
//
// app.js 와 분리해 둔 이유: 기후 지도 코드는 Cursor 소유 영역이라 같은 파일을
// 동시에 건드리면 충돌한다. 여기에 상태·렌더·범례를 전부 담고, app.js 쪽은
// 세 줄(레이어 주입 · 범례 마운트 · 재렌더 콜백 등록)만 빌린다.
//
// 그리는 것: NOAA OISST v2.1 해수면온도 **편차** 래스터.
// 절대 수온이 아니라 편차라서 평년과 같은 바다는 투명하게 빠지고 이상역만 남는다.
// 알파는 PNG 에 이미 |편차| 비례로 구워져 있고, 여기서 opacity 로 한 번 더 눌러
// 육지 폴리곤과 국가 핀의 가독성을 지킨다.
//
// 데이터: scripts/climate_ocean/build_sst_anomaly.py 가 생성
//         public/data/sst_anomaly.png + sst_anomaly_meta.json

(function () {
    'use strict';

    const { BitmapLayer, PathLayer, TextLayer } = deck;

    const META_URL = 'public/data/sst_anomaly_meta.json';
    const STORAGE_KEY = 'climate.oceanSst';
    const CURRENTS_KEY = 'climate.oceanCurrents';

    // 래스터 자체 알파 위에 곱해지는 값. 이 둘의 곱이 최종 농도다.
    // 세계 줌에서 편차 큰 해역이 넓게 잡히면 금세 탁해진다. 0.4 가 '바다에 뭔가
    // 있다'는 건 읽히되 국가 핀·해안선을 안 덮는 지점.
    const LAYER_OPACITY = 0.4;

    // 주요 표층 해류. 실측 벡터장(OSCAR/GLORYS)이 아니라 **모식도**다.
    // 실벡터장을 쓰려면 격자 보간 + 입자 추적이 필요한데, 이 대시보드에서
    // 해류는 예측 인자가 아니라 배경 맥락이라 그 비용을 쓸 이유가 없다.
    // 좌표는 교과서적 주경로를 따라 손으로 찍은 것이며 해마다 사행(meander)한다.
    const CURRENTS = [
        { ko: '멕시코만류 · 북대서양해류', type: 'warm', path: [
            [-80, 25], [-79.5, 28], [-78.5, 31], [-76, 34], [-72, 37], [-65, 39],
            [-55, 41], [-45, 44], [-35, 47], [-25, 50], [-18, 54], [-12, 58], [-8, 62]] },
        { ko: '래브라도 한류', type: 'cold', path: [
            [-55, 65], [-57, 62], [-58, 58], [-55, 54], [-52, 50], [-50, 46], [-52, 43]] },
        { ko: '쿠로시오 난류', type: 'warm', path: [
            [122, 22], [124, 26], [128, 30], [133, 33], [140, 35], [145, 36],
            [152, 38], [160, 40], [170, 41]] },
        { ko: '캘리포니아 한류', type: 'cold', path: [
            [-128, 48], [-126, 43], [-124, 38], [-121, 33], [-117, 28], [-113, 24]] },
        { ko: '훔볼트(페루) 한류', type: 'cold', path: [
            [-75, -45], [-74, -40], [-73, -34], [-72, -28], [-75, -22],
            [-79, -16], [-82, -10], [-85, -5]] },
        { ko: '벵겔라 한류', type: 'cold', path: [
            [15, -34], [13, -30], [12, -25], [11, -20], [11, -15], [10, -10]] },
        { ko: '아굴라스 난류', type: 'warm', path: [
            [40, -15], [38, -20], [35, -25], [31, -29], [27, -33], [22, -36], [18, -37]] },
        { ko: '카나리아 한류', type: 'cold', path: [
            [-13, 33], [-15, 29], [-17, 25], [-18, 21], [-19, 17]] },
        { ko: '동호주 난류', type: 'warm', path: [
            [153, -25], [153, -30], [151, -34], [150, -38], [148, -41]] },
    ];

    const CURRENT_COLOR = {
        warm: [214, 118, 90],
        cold: [94, 166, 200],
    };

    const OceanLayers = {
        enabled: false,
        currentsEnabled: false,
        meta: null,
        _metaPromise: null,
        // app.js 가 등록한다. 토글 시 세계지도를 다시 그리기 위한 훅.
        onChange: null,
    };

    // localStorage 접근은 사파리 프라이빗 모드 등에서 던질 수 있어 감싼다.
    const readStored = (key) => {
        try {
            return window.localStorage.getItem(key) === '1';
        } catch (e) {
            return false;
        }
    };
    const writeStored = (key, on) => {
        try {
            window.localStorage.setItem(key, on ? '1' : '0');
        } catch (e) { /* 저장 실패는 무시 — 세션 한정으로만 동작 */ }
    };

    OceanLayers.enabled = readStored(STORAGE_KEY);
    OceanLayers.currentsEnabled = readStored(CURRENTS_KEY);

    // 화살촉 위치·각도. 경로를 몇 점씩 건너뛰며 진행 방향을 재서 심는다.
    //
    // 각도는 화면(Web Mercator) 기준으로 재야 PathLayer 가 그린 선과 어긋나지 않는다.
    // Mercator 는 위도가 높을수록 y 를 1/cos(lat) 로 늘리므로, 지리적 방위각을
    // 그대로 쓰면 고위도에서 화살표가 선을 벗어나 기운다.
    const arrowsFor = (cur, every = 3) => {
        const out = [];
        for (let i = 0; i + 1 < cur.path.length; i += every) {
            const [lon1, lat1] = cur.path[i];
            const [lon2, lat2] = cur.path[i + 1];
            const latRad = ((lat1 + lat2) / 2) * Math.PI / 180;
            const dx = lon2 - lon1;
            const dy = (lat2 - lat1) / Math.max(0.2, Math.cos(latRad));
            out.push({
                position: [(lon1 + lon2) / 2, (lat1 + lat2) / 2],
                angle: Math.atan2(dy, dx) * 180 / Math.PI,
                type: cur.type,
                ko: cur.ko,
            });
        }
        return out;
    };

    OceanLayers.loadMeta = function () {
        if (this._metaPromise) return this._metaPromise;
        this._metaPromise = fetch(META_URL)
            .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
            .then(m => { this.meta = m; return m; })
            .catch(err => {
                // 래스터가 아직 생성 안 된 배포본일 수 있다. 조용히 레이어만 비운다.
                console.warn('[Ocean] SST 메타 로드 실패 — 레이어 생략', err);
                this.meta = null;
                return null;
            });
        return this._metaPromise;
    };

    // 세계지도 레이어 배열. 항상 배열을 돌려주므로 호출부에서 스프레드만 하면 된다.
    // 국가 폴리곤보다 **앞에** 펼쳐 넣어야 육지가 래스터를 덮는다.
    OceanLayers.buildLayers = function () {
        const layers = [];
        if (this.enabled && this.meta) layers.push(...this.buildSstLayers());
        if (this.currentsEnabled) layers.push(...this.buildCurrentLayers());
        return layers;
    };

    // 해류 모식도. 선 + 화살촉 두 겹.
    OceanLayers.buildCurrentLayers = function () {
        const arrows = CURRENTS.flatMap(c => arrowsFor(c));
        return [
            new PathLayer({
                id: 'ocean-currents-path',
                data: CURRENTS,
                getPath: d => d.path,
                getColor: d => [...CURRENT_COLOR[d.type], 165],
                // 굵기를 픽셀로 고정해야 줌아웃에서 실오라기가 되지 않는다.
                widthUnits: 'pixels',
                getWidth: 2.5,
                widthMinPixels: 2,
                capRounded: true,
                jointRounded: true,
                pickable: false,
            }),
            new TextLayer({
                id: 'ocean-currents-arrows',
                data: arrows,
                getPosition: d => d.position,
                getText: () => '▶',
                // 기본 characterSet 은 ASCII 라 '▶' 를 넣지 않으면 빈 칸으로 나온다.
                characterSet: ['▶'],
                getAngle: d => d.angle,
                getColor: d => [...CURRENT_COLOR[d.type], 210],
                sizeUnits: 'pixels',
                getSize: 13,
                billboard: false,
                pickable: false,
            }),
        ];
    };

    OceanLayers.buildSstLayers = function () {
        if (!this.enabled || !this.meta) return [];
        return [
            new BitmapLayer({
                id: 'ocean-sst-anomaly',
                image: `public/data/${this.meta.image}`,
                bounds: this.meta.bounds,
                opacity: LAYER_OPACITY,
                // 배경 래스터일 뿐이라 클릭·호버를 먹으면 안 된다.
                pickable: false,
                // 1도 격자를 확대해도 격자 계단이 안 보이게.
                textureParameters: {
                    minFilter: 'linear',
                    magFilter: 'linear',
                },
            }),
        ];
    };

    const applyChange = (self) => {
        if (typeof self.onChange === 'function') self.onChange();
    };

    OceanLayers.setEnabled = function (on) {
        this.enabled = !!on;
        writeStored(STORAGE_KEY, this.enabled);
        // 처음 켤 때는 메타를 받아온 뒤에 다시 그려야 레이어가 실제로 붙는다.
        if (this.enabled && !this.meta) this.loadMeta().then(() => applyChange(this));
        else applyChange(this);
    };

    // 해류는 좌표가 코드에 박혀 있어 받아올 게 없다. 바로 다시 그린다.
    OceanLayers.setCurrentsEnabled = function (on) {
        this.currentsEnabled = !!on;
        writeStored(CURRENTS_KEY, this.currentsEnabled);
        applyChange(this);
    };

    // ---- 범례 + 토글 -------------------------------------------------------
    // #climate-map-legend 는 app.js 의 setClimateMapLegend 가 innerHTML 로 갈아끼운다.
    // 그래서 매번 다시 붙여야 하고, 클릭은 위임으로 받아야 한다.

    const gradientCss = (m) => {
        const c = m ? m.cold_rgb : [56, 132, 190];
        const w = m ? m.warm_rgb : [200, 86, 66];
        return `linear-gradient(90deg, rgb(${c}) 0%, rgba(${c},0.15) 42%,`
             + ` rgba(255,255,255,0.06) 50%, rgba(${w},0.15) 58%, rgb(${w}) 100%)`;
    };

    OceanLayers.legendHtml = function () {
        const m = this.meta;
        const scale = m ? m.scale_c : 3;
        const obs = m && m.obs_date ? m.obs_date : '—';
        const on = this.enabled;
        const cur = this.currentsEnabled;
        const warm = `rgb(${CURRENT_COLOR.warm})`;
        const cold = `rgb(${CURRENT_COLOR.cold})`;
        return `
            <div class="ocean-legend-block">
                <label class="ocean-toggle">
                    <input type="checkbox" data-ocean-sst ${on ? 'checked' : ''}>
                    <span>해수면온도 편차</span>
                </label>
                ${on ? `
                <div class="ocean-scale" style="background:${gradientCss(m)}"></div>
                <div class="ocean-scale-ticks">
                    <span>−${scale}°C</span><span>평년</span><span>+${scale}°C</span>
                </div>
                <div class="ocean-note">OISST v2.1 · ${obs} 관측</div>` : ''}

                <label class="ocean-toggle" style="margin-top:8px;">
                    <input type="checkbox" data-ocean-currents ${cur ? 'checked' : ''}>
                    <span>주요 해류</span>
                </label>
                ${cur ? `
                <div class="ocean-cur-keys">
                    <span><i style="background:${warm}"></i>난류</span>
                    <span><i style="background:${cold}"></i>한류</span>
                </div>
                <div class="ocean-note">모식도 (실측 벡터장 아님) · 방향만 표시</div>` : ''}

                <div class="ocean-note" style="margin-top:6px;">
                    둘 다 배경 컨텍스트 · 예측 인자 아님
                </div>
            </div>`;
    };

    // 범례 컨테이너가 새로 그려진 뒤 호출한다. world 레벨에서만 붙인다.
    OceanLayers.mountLegend = function (el) {
        if (!el || el.classList.contains('hidden')) return;
        const render = () => el.insertAdjacentHTML('beforeend', this.legendHtml());
        if (this.meta || !this.enabled) render();
        else this.loadMeta().then(render);
    };

    // 체크박스는 innerHTML 교체로 계속 새로 생기므로 document 위임으로 받는다.
    document.addEventListener('change', (e) => {
        const t = e.target;
        if (!t || !t.closest) return;
        if (t.closest('[data-ocean-sst]')) OceanLayers.setEnabled(t.checked);
        else if (t.closest('[data-ocean-currents]')) OceanLayers.setCurrentsEnabled(t.checked);
    });

    // ---- 스타일 -----------------------------------------------------------
    // style.css 도 Cursor 소유라 손대지 않는다. 이 블록에 필요한 규칙만 주입한다.
    const STYLE_ID = 'ocean-layers-style';
    if (!document.getElementById(STYLE_ID)) {
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .ocean-legend-block {
                margin-top: 10px;
                padding-top: 8px;
                border-top: 1px solid rgba(255,255,255,0.08);
            }
            .ocean-toggle {
                display: flex; align-items: center; gap: 6px;
                cursor: pointer; font-size: 11px; color: #cbd5e1;
                user-select: none;
            }
            .ocean-toggle input { cursor: pointer; margin: 0; accent-color: #38bdf8; }
            .ocean-scale {
                height: 8px; margin-top: 6px; border-radius: 2px;
                border: 1px solid rgba(255,255,255,0.12);
            }
            .ocean-scale-ticks {
                display: flex; justify-content: space-between;
                font-size: 9px; color: #94a3b8; margin-top: 2px;
            }
            .ocean-note { margin-top: 4px; font-size: 9px; color: #64748b; line-height: 1.4; }
            .ocean-cur-keys {
                display: flex; gap: 12px; margin-top: 5px;
                font-size: 10px; color: #94a3b8;
            }
            .ocean-cur-keys i {
                display: inline-block; width: 14px; height: 3px;
                border-radius: 2px; margin-right: 4px; vertical-align: middle;
            }
        `;
        document.head.appendChild(style);
    }

    window.OceanLayers = OceanLayers;

    // 켜진 상태로 새로고침한 경우를 대비해 메타를 미리 받아둔다.
    if (OceanLayers.enabled) OceanLayers.loadMeta();
})();
