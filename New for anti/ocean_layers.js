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

    const { BitmapLayer } = deck;

    const META_URL = 'public/data/sst_anomaly_meta.json';
    const STORAGE_KEY = 'climate.oceanSst';

    // 래스터 자체 알파 위에 곱해지는 값. 이 둘의 곱이 최종 농도다.
    // 세계 줌에서 편차 큰 해역이 넓게 잡히면 금세 탁해진다. 0.4 가 '바다에 뭔가
    // 있다'는 건 읽히되 국가 핀·해안선을 안 덮는 지점.
    const LAYER_OPACITY = 0.4;

    const OceanLayers = {
        enabled: false,
        meta: null,
        _metaPromise: null,
        // app.js 가 등록한다. 토글 시 세계지도를 다시 그리기 위한 훅.
        onChange: null,
    };

    // localStorage 접근은 사파리 프라이빗 모드 등에서 던질 수 있어 감싼다.
    const readStored = () => {
        try {
            return window.localStorage.getItem(STORAGE_KEY) === '1';
        } catch (e) {
            return false;
        }
    };
    const writeStored = (on) => {
        try {
            window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0');
        } catch (e) { /* 저장 실패는 무시 — 세션 한정으로만 동작 */ }
    };

    OceanLayers.enabled = readStored();

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

    OceanLayers.setEnabled = function (on) {
        this.enabled = !!on;
        writeStored(this.enabled);
        const apply = () => {
            if (typeof this.onChange === 'function') this.onChange();
        };
        // 처음 켤 때는 메타를 받아온 뒤에 다시 그려야 레이어가 실제로 붙는다.
        if (this.enabled && !this.meta) this.loadMeta().then(apply);
        else apply();
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
                <div class="ocean-note">OISST v2.1 · ${obs} 관측 · 배경 컨텍스트</div>` : ''}
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
        const box = e.target.closest && e.target.closest('[data-ocean-sst]');
        if (!box) return;
        OceanLayers.setEnabled(box.checked);
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
        `;
        document.head.appendChild(style);
    }

    window.OceanLayers = OceanLayers;

    // 켜진 상태로 새로고침한 경우를 대비해 메타를 미리 받아둔다.
    if (OceanLayers.enabled) OceanLayers.loadMeta();
})();
