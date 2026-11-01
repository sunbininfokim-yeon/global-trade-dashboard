/* PKS (palm kernel shell) supply outlook, shown in the thermal-coal and palm-oil views.
 *
 * Korean power plants co-fire PKS with coal, so the fuel buyer reads it next
 * to the coal reference prices. Nothing here is a new number: each row is the
 * `pks_outlook` field the palm forecasts already publish (scripts/yield_model/
 * palm_oil/pks.py: ~25% of the CPO trend, moved by the palm weather call).
 * No country publishes PKS output; the panel says so.
 */
(() => {
    const COUNTRIES = [
        { file: 'indonesia', key: 'indonesia_palm_oil', label: '인도네시아', country: 'Indonesia' },
        { file: 'malaysia', key: 'malaysia_palm_oil', label: '말레이시아', country: 'Malaysia' },
        { file: 'thailand', key: 'thailand_palm_oil', label: '태국', country: 'Thailand' },
        { file: 'colombia', key: 'colombia_palm_oil', label: '콜롬비아', country: 'Colombia' },
        { file: 'nigeria', key: 'nigeria_palm_oil', label: '나이지리아', country: 'Nigeria' },
    ];
    const PILL = { unfavorable: { bg: 'rgba(251,146,60,0.18)', fg: '#fdba74' }, neutral: { bg: 'rgba(148,163,184,0.15)', fg: '#cbd5e1' } };
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    // 천 t -> 만 t
    const mt = (kt) => Math.round(kt / 10).toLocaleString('ko-KR');
    // Coal view (co-fired fuel) and palm oil view (where PKS comes from).
    const VIEWS = ['thermal_coal', 'palm_oil'];
    let pending;
    let generation = 0;

    if (!document.querySelector('style[data-pks-style]')) {
        const css = document.createElement('style');
        css.dataset.pksStyle = '1';
        css.textContent = `
            [data-pks] .pks-total { display:flex; align-items:baseline; gap:8px; margin:6px 0 2px; }
            [data-pks] .pks-total b { font-size:20px; color:#e2e8f0; }
            [data-pks] .pks-total s { color:#64748b; }
            [data-pks] .pks-down { color:#fdba74; }
            [data-pks] .pks-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:2px 8px; padding:7px 0; border-top:1px solid rgba(255,255,255,0.06); cursor:pointer; }
            [data-pks] .pks-row .nm { font-size:13px; color:#e2e8f0; }
            [data-pks] .pks-row:hover .nm { color:#7dd3fc; }
            [data-pks] .pks-bar { grid-column:1 / -1; height:6px; border-radius:3px; background:rgba(148,163,184,0.18); position:relative; overflow:hidden; }
            [data-pks] .pks-bar i { position:absolute; inset:0 auto 0 0; background:#38bdf8; border-radius:3px; }
            [data-pks] .pks-bar u { position:absolute; inset:0 auto 0 0; background:rgba(56,189,248,0.35); border-radius:3px; text-decoration:none; }
            [data-pks] .pks-pill { font-size:11px; padding:1px 7px; border-radius:9px; margin-left:6px; }`;
        document.head.appendChild(css);
    }

    function load() {
        pending ||= Promise.all(COUNTRIES.map((c) => fetch(`/public/data/${c.file}_yield_forecast.json`, { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null)).catch(() => null)
            .then((d) => {
                const e = d?.regions?.[c.key];
                const p = e?.pks_outlook;
                return p ? { ...c, p, wc: e.weather_conditions || {}, season: e.season } : null;
            }))).then((rows) => rows.filter(Boolean));
        return pending;
    }

    function rowHtml(r, max) {
        const v = r.p.adjusted_kt ?? r.p.trend_kt;
        const pill = PILL[r.wc.verdict] || PILL.neutral;
        const change = r.p.adjusted_kt != null
            ? `<span class="pks-down">${mt(r.p.trend_kt)} → ${mt(v)}만 t</span>`
            : `${mt(v)}만 t`;
        return `<div class="pks-row" data-pks-country="${esc(r.country)}" title="팜 카드에서 판정 근거 보기">
            <span class="nm">${esc(r.label)}<span class="pks-pill" style="background:${pill.bg};color:${pill.fg}">${esc(r.wc.verdict_ko || '—')}</span></span>
            <span class="vl" style="font-size:13px;">${change}</span>
            <div class="pks-bar"><u style="width:${(100 * r.p.trend_kt / max).toFixed(1)}%"></u><i style="width:${(100 * v / max).toFixed(1)}%"></i></div>
        </div>`;
    }

    async function render(countryName = null) {
        const token = ++generation;
        const host = document.getElementById('news-content');
        if (!host) return;
        host.querySelector('[data-pks]')?.remove();
        if (typeof currentCommodity === 'undefined' || !VIEWS.includes(currentCommodity)) return;
        const key = countryName ? (typeof resolveCountry === 'function' ? resolveCountry(countryName)?.label : countryName) : null;
        if (countryName && !COUNTRIES.some((c) => c.country === key || c.country === countryName)) return;
        const slot = document.createElement('div');
        slot.dataset.pks = '1';
        slot.className = 'stock-card';
        slot.textContent = 'PKS 공급 전망을 불러오는 중…';
        const coal = host.querySelector('[data-coal-prices]');
        if (coal) coal.after(slot); else host.appendChild(slot);
        try {
            let rows = await load();
            if (token !== generation || !slot.isConnected) return;
            if (countryName) rows = rows.filter((r) => r.country === key || r.country === countryName);
            if (!rows.length) { slot.remove(); return; }
            rows.sort((a, b) => b.p.trend_kt - a.p.trend_kt);
            const trend = rows.reduce((s, r) => s + r.p.trend_kt, 0);
            const adj = rows.reduce((s, r) => s + (r.p.adjusted_kt ?? r.p.trend_kt), 0);
            const pct = Math.round((1000 * (adj - trend)) / trend) / 10;
            const season = rows[0].season;
            slot.innerHTML = `<p class="section-title">바이오매스 · PKS(팜 껍질) 공급 전망 ${esc(season)}</p>
                <div class="stock-note">발전소 혼소 연료. 팜유 산지의 기상 판정을 PKS 물량으로 환산한 추정입니다.</div>
                <div class="pks-total"><b>${mt(adj)}만 t</b>${pct < 0 ? `<s>${mt(trend)}만 t</s><span class="pks-down">${pct}%</span>` : '<span class="stock-note">추세 수준</span>'}</div>
                <div class="stock-note" style="margin-bottom:4px;">${rows.length}개 산지 합계 · 흐린 막대 = 추세, 진한 막대 = 기상 판정 반영</div>
                ${rows.map((r) => rowHtml(r, rows[0].p.trend_kt)).join('')}
                <div class="stock-note" style="margin-top:6px;">PKS 생산 통계는 어느 나라도 공개하지 않습니다. CPO 추세의 약 25%(업계 경험치 22~30%)로 환산했고, 불리 판정은 과거 불리 해의 평균 감소폭을 적용했습니다. 행을 누르면 팜 카드의 판정 근거로 이동합니다.</div>`;
            slot.querySelectorAll('[data-pks-country]').forEach((el) => el.addEventListener('click', () => {
                // Crop monitor, then that country's regions (the palm card holds the call).
                if (typeof setView !== 'function' || typeof showClimateCountry !== 'function') return;
                setView('climate');
                const go = () => { if (currentCommodity === 'climate') showClimateCountry(el.dataset.pksCountry); };
                (typeof loadClimateRegistry === 'function' ? loadClimateRegistry() : Promise.resolve()).then(() => setTimeout(go, 0));
            }));
        } catch (_) {
            if (slot.isConnected) slot.textContent = 'PKS 공급 전망을 불러오지 못했습니다.';
        }
    }
    window.BiomassPks = { render };
})();
