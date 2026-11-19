/* Fertilizer prices on the urea and potash trade views.
 *
 * World Bank Pink Sheet monthly prices (USD/t), built monthly by
 * scripts/fertilizer/prices.py into public/data/fertilizer_prices_v1.json.
 * There is no free exchange quote for either, so this card stands where the
 * futures card sits on the other views.
 */
(() => {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const pct = (v) => (v == null ? '' : `<span style="color:${v >= 0 ? '#86efac' : '#fdba74'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span>`);
    const usd = (v) => `$${Math.round(v).toLocaleString('en-US')}`;
    const month = (m) => { const [y, mm] = String(m).split('-'); return `${y}년 ${Number(mm)}월`; };
    let pending;
    let generation = 0;

    if (!document.querySelector('style[data-fertilizer-style]')) {
        const css = document.createElement('style');
        css.dataset.fertilizerStyle = '1';
        css.textContent = `[data-fertilizer] .gb-line { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#e2e8f0; padding:5px 0; border-top:1px solid rgba(255,255,255,0.06); }`;
        document.head.appendChild(css);
    }

    function load() {
        pending ||= fetch('/public/data/fertilizer_prices_v1.json', { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return pending;
    }

    // 36-month line; the colour follows the year-on-year move.
    function spark(series, up) {
        const v = series.map((p) => p.usd_t);
        if (v.length < 2) return '';
        const w = 300, h = 54, lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
        const pts = v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 4 - (x - lo) / span * (h - 8)).toFixed(1)}`).join(' ');
        return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" style="display:block;margin:6px 0 2px;">
            <polyline points="${pts}" fill="none" stroke="${up ? '#86efac' : '#fdba74'}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>
            <div class="stock-note" style="display:flex;justify-content:space-between;"><span>${esc(month(series[0].month))}</span><span>최저 ${usd(lo)} · 최고 ${usd(hi)}</span><span>${esc(month(series[series.length - 1].month))}</span></div>`;
    }

    // Urea per tonne of corn over the winter buying window, and whether that
    // has moved the US corn/soy split in the past.
    function ratioHtml(a) {
        if (!a) return '';
        const bt = a.backtest;
        const vs = a.avg_10y ? ` <span class="stock-note">10년 평균 ${a.avg_10y}</span>` : '';
        const prev = a.prev_urea_per_corn ? ` <span class="stock-note">전년 ${a.prev_urea_per_corn}</span>` : '';
        let verdict = '';
        if (bt) {
            const msg = `요소/옥수수 가격비가 10% 오를 때 미국 옥수수 면적 비중 ${bt.coef_share_pp_per_10pct >= 0 ? '+' : ''}${bt.coef_share_pp_per_10pct}%p (t ${bt.t}, ${esc(bt.years)})`;
            verdict = bt.passed
                ? `<div class="gb-line"><span>과거 검증</span><span style="color:#86efac;">통과</span></div><div class="stock-note">${msg}</div>`
                : `<div class="gb-line"><span>과거 검증</span><span style="color:#94a3b8;">미통과 · 참고만</span></div><div class="stock-note">${msg} · 기준: ${esc(bt.rule_ko)}</div>`;
        }
        return `<p class="trade-rank-group-head" style="margin-top:10px;">${a.planting_year}년 파종 비료 부담 (요소 1t = 옥수수 몇 t)</p>
            <div class="gb-line"><span>${esc(a.window_ko)} 평균${a.months_in < 6 ? ` <span class="stock-note">${a.months_in}개월치</span>` : ''}</span><span><b>${a.urea_per_corn}</b>${prev}${vs}</span></div>
            ${a.pct_rank == null ? '' : `<div class="gb-line"><span>1980년 이후 순위</span><span>상위 ${100 - a.pct_rank}%</span></div>`}
            ${verdict}`;
    }

    function cardHtml(doc, lead) {
        const s = doc.series[lead];
        const others = Object.entries(doc.series).filter(([k]) => k !== lead)
            .map(([, o]) => `<div class="gb-line"><span>${esc(o.label_ko)}</span><span>${usd(o.usd_t)} ${pct(o.yoy_pct)}</span></div>`).join('');
        const rank = s.pct_rank_10y == null ? '' : ` · 최근 10년 중 상위 ${100 - s.pct_rank_10y}%`;
        return `<p class="section-title">국제가격 · ${esc(s.label_ko)} (${esc(month(s.month))})</p>
            <div class="gb-line"><span>가격 (톤당)</span><span><b>${usd(s.usd_t)}</b></span></div>
            <div class="gb-line"><span>전월 대비 · 전년 대비</span><span>${pct(s.mom_pct)} · ${pct(s.yoy_pct)}</span></div>
            <div class="gb-line"><span>5년 평균</span><span>${usd(s.avg_5y_usd_t)} <span class="stock-note">대비 ${s.vs_5y_pct >= 0 ? '+' : ''}${s.vs_5y_pct}%${rank}</span></span></div>
            ${spark(s.series || [], (s.yoy_pct ?? 0) >= 0)}
            ${lead === 'urea' ? ratioHtml(doc.affordability) : ''}
            ${others ? `<p class="trade-rank-group-head" style="margin-top:10px;">다른 비료 (전년 대비)</p>${others}` : ''}
            <div class="stock-note" style="margin-top:6px;">거래소 선물 시세는 무료로 제공되지 않아 월간 기준가를 씁니다 · 출처: <a href="${esc(doc.url)}" target="_blank" rel="noopener" style="color:#7dd3fc;">세계은행 Pink Sheet</a></div>`;
    }

    async function render() {
        const token = ++generation;
        const host = document.getElementById('news-content');
        host?.querySelector('[data-fertilizer]')?.remove();
        if (typeof currentCommodity === 'undefined') return;
        const view = currentCommodity;
        const doc = await load();
        if (token !== generation || currentCommodity !== view) return;
        const lead = doc?.views?.[view];
        if (!lead || !doc.series?.[lead]) return;
        const card = host?.querySelector('.trade-focus-card');
        if (!card) return;
        const slot = document.createElement('div');
        slot.dataset.fertilizer = '1';
        slot.className = 'stock-card';
        slot.style.marginBottom = '10px';
        slot.innerHTML = cardHtml(doc, lead);
        const futures = card.querySelector('#futures-slot');
        if (futures) futures.after(slot); else card.prepend(slot);
    }

    window.FertilizerPrices = { render };
})();
