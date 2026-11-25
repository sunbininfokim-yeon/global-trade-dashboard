/* World oil balance and a Brent fair value from OECD stocks, on the crude-oil trade view.
 *
 * Data: public/data/oil_balance_v1.json, built from EIA's Short-Term Energy Outlook (current workbook and
 * December archives back to 2007) and FRED Brent by scripts/oil_balance/build_oil_balance.py. The fair
 * value is log(Brent) on OECD days-of-cover against their five-year average, fitted over 2015-2025; the
 * forward path runs EIA's own stock forecast through it. The scenario buttons replace EIA's 2027 OECD
 * stock build with a flat daily rate and recompute the fair value here, from the same coefficients.
 */
(() => {
    const VIEWS = ['oil'];
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const usd = (v, d = 0) => (Number.isFinite(v) ? `$${v.toFixed(d)}` : '—');
    const num = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '—');
    let pending;
    let generation = 0;
    let scenario = 'eia';

    if (!document.querySelector('style[data-oilbal-style]')) {
        const css = document.createElement('style');
        css.dataset.oilbalStyle = '1';
        css.textContent = `
            [data-oilbal] .ob-line { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#e2e8f0; padding:5px 0; border-top:1px solid rgba(255,255,255,0.06); }
            [data-oilbal] table.ob-tab { width:100%; border-collapse:collapse; font-size:12px; color:#e2e8f0; margin-top:4px; }
            [data-oilbal] table.ob-tab th { color:#94a3b8; font-weight:500; text-align:right; padding:4px 2px; border-bottom:1px solid rgba(255,255,255,0.08); }
            [data-oilbal] table.ob-tab td { text-align:right; padding:4px 2px; border-bottom:1px solid rgba(255,255,255,0.04); font-variant-numeric:tabular-nums; }
            [data-oilbal] table.ob-tab th:first-child, [data-oilbal] table.ob-tab td:first-child { text-align:left; }
            [data-oilbal] .ob-chart { width:100%; height:170px; display:block; margin-top:6px; }
            [data-oilbal] .ob-key { font-size:11px; color:#94a3b8; display:flex; flex-wrap:wrap; gap:10px; margin-top:2px; }
            [data-oilbal] .ob-key i { display:inline-block; width:14px; height:0; border-top:2px solid; vertical-align:middle; margin-right:4px; }
            [data-oilbal] .ob-btns { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0; }
            [data-oilbal] .ob-btns button { font-size:12px; padding:3px 8px; border-radius:6px; border:1px solid rgba(148,163,184,0.3); background:transparent; color:#cbd5e1; cursor:pointer; }
            [data-oilbal] .ob-btns button.on { background:rgba(167,139,250,0.2); border-color:#a78bfa; color:#e9d5ff; }
            [data-oilbal] .ob-gap-up { color:#fca5a5; } [data-oilbal] .ob-gap-dn { color:#86efac; }`;
        document.head.appendChild(css);
    }

    function load() {
        pending ||= fetch('/public/data/oil_balance_v1.json', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return pending;
    }

    // Replace EIA's OECD stock path from the first forecast month with a flat daily build `rate` (mb/d) and
    // recompute the fair value with the fitted line. 'eia' keeps EIA's path.
    function scenarioPath(d, rate) {
        const b = d.model.b;
        const path = d.path;
        const i0 = path.findIndex((p) => p.forecast);
        if (rate === 'eia' || i0 < 1) return path.map((p) => p.fair_value);
        let stocks = path[i0 - 1].oecd_stocks_mb;
        return path.map((p, i) => {
            if (i < i0) return p.fair_value;
            stocks += rate * 30.4;
            const days = stocks / p.oecd_demand_mbd;
            const dev = days - (p.days - p.dev_days);           // same five-year baseline
            return Math.exp(d.model.a + b * dev);
        });
    }

    function chart(d, fvAlt) {
        const P = d.path;
        const W = 600, H = 170, L = 34, R = 6, T = 8, B = 18;
        const vals = P.flatMap((p, i) => [p.brent, p.brent_eia, fvAlt[i]]).filter(Number.isFinite);
        const lo = Math.min(...vals) * 0.92, hi = Math.max(...vals) * 1.04;
        const x = (i) => L + (i / (P.length - 1)) * (W - L - R);
        const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
        const line = (arr, color, dash) => {
            let s = '', pen = false;
            arr.forEach((v, i) => { if (!Number.isFinite(v)) { pen = false; return; } s += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
            return `<path d="${s}" fill="none" stroke="${color}" stroke-width="1.6" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
        };
        const i0 = P.findIndex((p) => p.forecast);
        const shade = i0 > 0 ? `<rect x="${x(i0).toFixed(1)}" y="${T}" width="${(W - R - x(i0)).toFixed(1)}" height="${H - T - B}" fill="rgba(148,163,184,0.08)"/>` : '';
        const ticks = [lo, (lo + hi) / 2, hi].map((v) => `<text x="${L - 4}" y="${(y(v) + 3).toFixed(1)}" font-size="9" fill="#64748b" text-anchor="end">${v.toFixed(0)}</text>`).join('');
        const yrs = P.map((p, i) => [p.month, i]).filter(([m]) => m.endsWith('-01'))
            .map(([m, i]) => `<text x="${x(i).toFixed(1)}" y="${H - 5}" font-size="9" fill="#64748b" text-anchor="middle">${m.slice(0, 4)}</text>`).join('');
        const actual = P.map((p) => (p.forecast ? null : p.brent));
        const eia = P.map((p, i) => (i >= i0 - 1 ? p.brent_eia : null));
        return `<svg class="ob-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="브렌트와 재고 기준 적정가">
                ${shade}${ticks}${yrs}
                ${line(fvAlt, '#a78bfa')}
                ${line(actual, '#38bdf8')}
                ${line(eia, '#38bdf8', '4 3')}
            </svg>
            <div class="ob-key"><span><i style="border-color:#38bdf8"></i>브렌트 실적(월평균)</span><span><i style="border-color:#38bdf8;border-top-style:dashed"></i>EIA 전망</span>
                <span><i style="border-color:#a78bfa"></i>재고 기준 적정가</span><span>음영 = 전망 구간</span></div>`;
    }

    function cardHtml(d) {
        const m = d.model, g = m.gaps, sf = g.since_fit || {};
        const jp = (d.bank_views || [])[0];
        const rates = [['eia', 'EIA 경로'], ['0', '0 (재고 정체)'], ['0.4', '0.4 (JP모건 OECD 가정)'], ['1.5', '1.5']];
        const alt = scenarioPath(d, scenario === 'eia' ? 'eia' : Number(scenario));
        const yrAvg = (y) => { const v = d.path.map((p, i) => [p.month, alt[i]]).filter(([mm]) => mm.startsWith(y)).map(([, v]) => v); return v.length === 12 ? v.reduce((a, b) => a + b, 0) / 12 : null; };
        const last = d.brent_last || {};
        const gapNow = Number.isFinite(last.value) && Number.isFinite(last.fair_value_month) ? last.value - last.fair_value_month : null;
        const rows = d.annual.map((a) => `<tr><td>${esc(a.year)}</td><td>${num(a.supply)}</td><td>${num(a.demand)}</td>
            <td>${Number.isFinite(a.balance) ? `${a.balance > 0 ? '+' : ''}${a.balance.toFixed(1)}` : '—'}</td>
            <td>${usd(a.year >= '2027' ? yrAvg(a.year) : a.fair_value)}</td>
            <td>${usd(a.brent ?? a.brent_eia)}${a.brent ? '' : a.brent_ytd ? ` <span class="stock-note">(연초~ ${usd(a.brent_ytd)})</span>` : ''}</td>
            <td>${jp && jp.brent_annual?.[a.year] ? usd(jp.brent_annual[a.year]) : '—'}</td></tr>`).join('');
        return `<p class="section-title">세계 원유 수급 · 재고 기준 적정가 <span class="stock-note">EIA STEO ${esc(d.steo.vintage || '')}</span></p>
            <div class="ob-line"><span>브렌트 ${esc(last.date || '')}</span><span>${usd(last.value, 1)} · 적정가 ${usd(last.fair_value_month, 1)}
                ${Number.isFinite(gapNow) ? `<b class="${gapNow > 0 ? 'ob-gap-up' : 'ob-gap-dn'}">${gapNow > 0 ? '+' : ''}${gapNow.toFixed(1)}</b>` : ''}</span></div>
            ${chart(d, alt)}
            <p class="trade-rank-group-head" style="margin-top:8px;">연간 수급과 가격 (백만 배럴/일 · 달러/배럴)</p>
            <table class="ob-tab"><thead><tr><th>연도</th><th>공급</th><th>수요</th><th>과잉</th><th>적정가</th><th>브렌트·EIA</th><th>JP모건</th></tr></thead><tbody>${rows}</tbody></table>
            <p class="trade-rank-group-head" style="margin-top:10px;">시나리오: 전망 기간 OECD 재고 증가 속도 (백만 배럴/일)</p>
            <div class="ob-btns">${rates.map(([k, lab]) => `<button type="button" data-ob-rate="${k}" class="${String(scenario) === k ? 'on' : ''}">${esc(lab)}</button>`).join('')}</div>
            <div class="stock-note">재고 증가가 빠를수록 재고 일수가 평년을 웃돌아 적정가가 내려갑니다. 버튼은 EIA 재고 경로만 바꾸고 공급·수요 표는 그대로입니다.</div>
            <p class="trade-rank-group-head" style="margin-top:10px;">적정가 대비 괴리</p>
            <div class="ob-line"><span>${esc(m.from)}~${esc(m.to)} 최대</span><span>+${num(g.max_premium)} (${esc(g.max_premium_month)}) / ${num(g.max_discount)} (${esc(g.max_discount_month)})</span></div>
            <div class="ob-line"><span>+$${num(g.band, 0)} 넘는 괴리</span><span>${g.episodes_above_band}번 · 평균 ${num(g.avg_months_above_band)}개월</span></div>
            ${sf.max_premium != null ? `<div class="ob-line"><span>${esc(sf.from)} 이후 최대</span><span class="ob-gap-up">+${num(sf.max_premium)} (${esc(sf.max_premium_month)})</span></div>` : ''}
            <div class="stock-note">2026년 괴리가 과거 최대의 두 배 가까이 됩니다. 재고 지표는 '앞으로 흐름이 끊길 위험'(호르무즈)을 담지 못하므로, 그 차이는 지정학 프리미엄으로 읽는 게 맞습니다.</div>
            ${jp ? `<details style="margin-top:8px;"><summary class="stock-note" style="cursor:pointer;">${esc(jp.name)} 전망 메모 · ${esc(jp.read_from)}</summary>
                ${(jp.notes_ko || []).map((t) => `<div class="stock-note" style="margin:4px 0;">· ${esc(t)}</div>`).join('')}</details>` : ''}
            <div class="stock-note" style="margin-top:8px;">모형: log(브렌트) = ${num(m.a, 3)} ${m.b < 0 ? '−' : '+'} ${Math.abs(m.b).toFixed(4)} × (OECD 재고 일수 − 같은 달 5년 평균), ${esc(m.from)}~${esc(m.to)} 월별, R² ${num(m.r2, 2)}.
                재고 1일이 평년보다 많으면 적정가 ${num(m.per_day_pct)}%. 2015년 이전(셰일 이전)은 같은 식이 맞지 않아 뺐습니다.
                출처: <a href="${esc(d.steo.url)}" target="_blank" rel="noopener" style="color:#7dd3fc;">EIA 단기에너지전망</a> · FRED DCOILBRENTEU</div>`;
    }

    async function render() {
        const token = ++generation;
        const host = document.getElementById('news-content');
        host?.querySelector('[data-oilbal]')?.remove();
        if (typeof currentCommodity === 'undefined' || !VIEWS.includes(currentCommodity)) return;
        const doc = await load();
        if (token !== generation || currentCommodity !== 'oil' || !doc?.path?.length) return;
        const card = host?.querySelector('.trade-focus-card');
        if (!card) return;
        const slot = document.createElement('div');
        slot.dataset.oilbal = '1';
        slot.className = 'stock-card';
        slot.style.marginBottom = '10px';
        const paint = () => { slot.innerHTML = cardHtml(doc); };
        paint();
        slot.addEventListener('click', (e) => {
            const b = e.target.closest('[data-ob-rate]');
            if (!b) return;
            scenario = b.getAttribute('data-ob-rate');
            paint();
        });
        const futures = card.querySelector('#futures-slot');
        if (futures) futures.after(slot); else card.prepend(slot);
    }

    window.OilBalance = { render, VIEWS, scenarioPath };
})();
