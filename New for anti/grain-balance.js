/* World balance for wheat, corn and soybeans on the trade view.
 *
 * The two stat boxes become last season's world production and USDA's
 * outlook for this one (the biggest exporter is already the first bar in the
 * ranking below). A card above the ranking adds world stocks-to-use, the big
 * producers and the main risks. Data: public/data/grain_balance_v1.json,
 * built monthly from USDA PSD by scripts/grain_balance/build.py, with the
 * weather risks taken from the crop monitor's stage calls.
 */
(() => {
    const VIEWS = ['wheat', 'corn', 'soybeans'];
    const MAX_WEATHER = 6;
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    // 천 t -> 백만 t
    const mt = (kt) => (kt / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    const pct = (v) => (v == null ? '' : `<span style="color:${v >= 0 ? '#86efac' : '#fdba74'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span>`);
    let pending;
    let generation = 0;

    if (!document.querySelector('style[data-grain-style]')) {
        const css = document.createElement('style');
        css.dataset.grainStyle = '1';
        css.textContent = `
            [data-grain] .gb-line { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#e2e8f0; padding:5px 0; border-top:1px solid rgba(255,255,255,0.06); }
            [data-grain] .gb-risk { font-size:13px; color:#e2e8f0; padding:6px 0 6px 10px; border-left:2px solid #fb923c; margin:6px 0; }
            [data-grain] .gb-risk.ref { color:#94a3b8; border-left-color:rgba(148,163,184,0.4); }
            [data-grain] .gb-risk .why { display:block; font-size:12px; color:#94a3b8; margin-top:2px; }
            [data-grain] .gb-tag { font-size:11px; padding:1px 6px; border-radius:8px; margin-right:6px; background:rgba(251,146,60,0.18); color:#fdba74; }
            [data-grain] .gb-risk.ref .gb-tag { background:rgba(148,163,184,0.15); color:#cbd5e1; }`;
        document.head.appendChild(css);
    }

    function load() {
        pending ||= fetch('/public/data/grain_balance_v1.json', { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return pending;
    }

    let touched = false;
    // Put the trade view's own labels back after a grain view rewrote them.
    function resetStats() {
        if (!touched) return;
        touched = false;
        const lv = document.getElementById('stat-label-volume');
        const lt = document.getElementById('stat-label-exporter');
        if (lv) { lv.textContent = '글로벌 무역량'; lv.removeAttribute('title'); }
        if (lt) { lt.textContent = '최대 수출국'; lt.removeAttribute('title'); }
    }

    function setStats(c) {
        touched = true;
        const lv = document.getElementById('stat-label-volume');
        const lt = document.getElementById('stat-label-exporter');
        const vv = document.getElementById('total-volume');
        const vt = document.getElementById('top-exporter');
        if (lv) { lv.textContent = `${c.prev.season} 세계 생산`; lv.title = `USDA PSD · ${c.release}`; }
        if (lt) { lt.textContent = `${c.current.season} 예상 생산 (USDA)`; lt.title = `USDA PSD · ${c.release}`; }
        if (vv) vv.textContent = `${mt(c.prev.production_kt)}백만 t`;
        if (vt) vt.innerHTML = `${mt(c.current.production_kt)}백만 t <span style="font-size:13px;">${pct(c.current.change_pct)}</span>`;
    }

    const TAG = { supply: '공급', stocks: '재고', weather: '날씨' };
    function riskHtml(r) {
        const why = r.kind === 'weather'
            ? `${esc(r.crop_ko)} ${esc(r.season)} · ${esc((r.reason || []).join(' / '))}${r.reference_only ? ' · 과거 판정이 실제 수확과 맞지 않아 참고만' : ''}`
            : '';
        return `<div class="gb-risk${r.reference_only ? ' ref' : ''}"><span class="gb-tag">${TAG[r.kind] || ''}</span>${esc(r.text_ko)}${why ? `<span class="why">${why}</span>` : ''}</div>`;
    }

    function cardHtml(c) {
        const cur = c.current;
        const weather = c.risks.filter((r) => r.kind === 'weather');
        const other = c.risks.filter((r) => r.kind !== 'weather');
        const shown = [...other, ...weather.slice(0, MAX_WEATHER)];
        const t = c.weather_tally || {};
        const more = weather.length > MAX_WEATHER ? `<div class="stock-note">날씨 불리 판정 ${weather.length - MAX_WEATHER}곳 더 (작황 모니터)</div>` : '';
        const producers = (c.producers || []).slice(0, 6).map((p) => `<div class="gb-line"><span>${esc(p.country_ko)} <span class="stock-note">${p.share_pct}%</span></span><span>${mt(p.production_kt)}백만 t ${pct(p.change_pct)}</span></div>`).join('');
        return `<p class="section-title">세계 수급 · ${esc(c.label_ko)} ${esc(cur.season)}</p>
            <div class="gb-line"><span>기말재고율</span><span>${cur.stocks_to_use_pct}% <span class="stock-note">5년 평균 ${cur.stocks_to_use_5y_avg_pct}%</span></span></div>
            <div class="gb-line"><span>세계 수출</span><span>${mt(cur.exports_kt)}백만 t</span></div>
            <div class="gb-line"><span>기말재고</span><span>${mt(cur.ending_stocks_kt)}백만 t</span></div>
            <p class="trade-rank-group-head" style="margin-top:10px;">주요 리스크</p>
            ${shown.length ? shown.map(riskHtml).join('') : '<div class="stock-note">눈에 띄는 리스크 없음</div>'}
            ${more}
            <div class="stock-note">생육 중인 산지 날씨 판정: 불리 ${t.unfavorable ?? 0} · 보통 ${t.neutral ?? 0} · 유리 ${t.favorable ?? 0}</div>
            <p class="trade-rank-group-head" style="margin-top:10px;">주요 생산국 (전년 대비)</p>
            ${producers}
            <div class="stock-note" style="margin-top:6px;">출처: <a href="${esc(c.url)}" target="_blank" rel="noopener" style="color:#7dd3fc;">${esc(c.release)}</a></div>`;
    }

    async function render() {
        const token = ++generation;
        const host = document.getElementById('news-content');
        host?.querySelector('[data-grain]')?.remove();
        if (typeof currentCommodity === 'undefined' || !VIEWS.includes(currentCommodity)) {
            resetStats();
            return;
        }
        const crop = currentCommodity;
        const doc = await load();
        if (token !== generation || currentCommodity !== crop) return;
        const c = doc?.crops?.[crop];
        if (!c) return;
        // A focused country rewrote the boxes for its own routes; leave them.
        if (typeof tradeFocusCountry === 'undefined' || !tradeFocusCountry) setStats(c);
        const card = host?.querySelector('.trade-focus-card');
        if (!card) return;
        const slot = document.createElement('div');
        slot.dataset.grain = '1';
        slot.className = 'stock-card';
        slot.style.marginBottom = '10px';
        slot.innerHTML = cardHtml(c);
        const futures = card.querySelector('#futures-slot');
        if (futures) futures.after(slot); else card.prepend(slot);
    }

    window.GrainBalance = { render, VIEWS };
})();
