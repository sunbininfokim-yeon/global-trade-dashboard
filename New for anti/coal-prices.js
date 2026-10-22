/* Coal reference prices for the thermal-coal trade view.
 *
 * Two official series, shown as what they are: Indonesia's HBA (a government
 * reference price set twice a month, four calorific grades) and the World
 * Bank's monthly Newcastle / Richards Bay averages. Neither is a futures
 * price and they are not comparable with each other, so they sit as separate
 * rows under one note instead of being merged into one number.
 * Data: public/data/coal_prices_v1.json (scripts/coal_prices/collect.py).
 */
(() => {
    let pending;
    let generation = 0;
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const fmt = (v, digits = 2) => (typeof v === 'number' && Number.isFinite(v)
        ? v.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—');
    const dayMs = 86400000;
    // Kept here, not in style.css: the rows are this module's own, and the
    // futures card's colours (#86efac / #fca5a5) are reused for up and down.
    if (!document.querySelector('style[data-coal-prices-style]')) {
        const css = document.createElement('style');
        css.dataset.coalPricesStyle = '1';
        css.textContent = `
            [data-coal-prices] details.stock-item > summary { list-style: none; }
            [data-coal-prices] details.stock-item > summary::-webkit-details-marker { display: none; }
            [data-coal-prices] details.stock-item > summary .nm::after { content: ' ▾'; color: #7dd3fc; font-size: 10px; }
            [data-coal-prices] details.stock-item:not([open]) > summary .nm::after { content: ' ▸'; }
            [data-coal-prices] .up { color: #86efac; }
            [data-coal-prices] .down { color: #fca5a5; }`;
        document.head.appendChild(css);
    }
    const days = (iso) => (Date.now() - new Date(`${iso}T00:00:00Z`).getTime()) / dayMs;
    // Which country's screen shows which row. The world view shows them all.
    const COUNTRY_ROWS = { Indonesia: ['hba'], Australia: ['coal_australian'], 'South Africa': ['coal_south_african'] };
    const WB_LABEL = {
        coal_australian: '호주산 석탄 · 세계은행 월평균',
        coal_south_african: '남아공산 석탄 · 세계은행 월평균',
    };

    // A line drawn across a hole in the history would invent the values in between,
    // so a chart only covers the unbroken stretch that ends at the latest reading.
    const trailingRun = (items, follows) => {
        let from = items.length - 1;
        while (from > 0 && follows(items[from - 1], items[from])) from -= 1;
        return items.slice(Math.max(from, 0));
    };
    const nextMonth = (a, b) => (Number(b.label.slice(0, 4)) * 12 + Number(b.label.slice(5, 7))) - (Number(a.label.slice(0, 4)) * 12 + Number(a.label.slice(5, 7))) === 1;
    const nextHalf = (a, b) => (new Date(`${b.label}T00:00:00Z`) - new Date(`${a.end}T00:00:00Z`)) / dayMs <= 3 && b.label > a.end;

    const monthLabel = (period) => `${period.slice(0, 4)}년 ${Number(period.slice(5, 7))}월`;
    const halfMonth = (start, end) => {
        const m = Number(start.slice(5, 7));
        const first = Number(start.slice(8, 10)) < 15;
        return `${start.slice(0, 4)}년 ${m}월 ${first ? '전반' : '후반'} (${start.slice(5).replace('-', '.')}–${end.slice(5).replace('-', '.')})`;
    };
    const staleNote = (stale) => (stale ? ' · <span style="color:#fcd34d">오래된 값 — 새 고시를 아직 읽지 못했습니다</span>' : '');
    const chartFor = (points, unit, label) => (typeof sparkChartHtml === 'function' && points.length > 1
        ? sparkChartHtml({ points, unit, formatValue: (v) => fmt(v), ariaLabel: label }) : '');

    // Indonesia's row. ICI4 (Argus/Coalindo, ~4,200 GAR) is a paid index with no
    // free source, so the row is the nearest official price, HBA II (4,100 GAR),
    // and says so rather than wearing the ICI4 name.
    function hbaRows(hba, staleAfter) {
        const periods = (hba?.periods || []).filter((p) => p.grades?.some((g) => g.name === 'HBA II'));
        if (!periods.length) {
            return `<div class="stock-item"><div class="stock-note">인도네시아 HBA II를 아직 읽지 못했습니다${hba?.error ? ` (${esc(hba.error)})` : ''}.</div></div>`;
        }
        const last = periods[periods.length - 1];
        const g = last.grades.find((x) => x.name === 'HBA II');
        const stale = days(last.end) > staleAfter || hba.status === 'error';
        const ended = days(last.end) > 0;
        const series = periods.map((p) => ({ label: p.start, end: p.end, value: p.grades.find((x) => x.name === 'HBA II').usd_per_t }));
        const gaps = series.some((pt, i) => i && !nextHalf(series[i - 1], pt));
        const up = (g.change_pct ?? 0) >= 0;
        const chg = g.change_pct == null ? '' : ` · 직전 고시 대비 <span class="${up ? 'up' : 'down'}">${up ? '+' : ''}${fmt(g.change_pct)}%</span>`;
        return `<details class="stock-item" open><summary style="cursor:pointer;padding:6px 0"><span class="stock-row" style="display:inline-grid;width:calc(100% - 14px);grid-template-columns:minmax(0,1fr) auto"><span class="nm">인도네시아 HBA II · 4,100 GAR</span><span class="vl">$${fmt(g.usd_per_t)}<em>/톤</em></span></span>
            <span class="stock-note" style="display:block">${esc(halfMonth(last.start, last.end))} 고시${chg}${staleNote(stale)}${ended && !stale ? ' · 다음 고시는 아직 공개 문서에 없음' : ''}</span></summary>
            <div class="stock-note">ICI4(약 4,200 GAR, 유료 지수) 대신 열량이 가장 가까운 정부 기준가격입니다 ·
            <a style="color:#7dd3fc" href="${esc(last.url)}" target="_blank" rel="noopener noreferrer">${last.decree ? `장관결정문 ${esc(last.decree)}` : '고시 원문'}</a></div>
            ${chartFor(series, ' $/톤', 'HBA II 고시 추이') || '<div class="stock-note">고시 이력이 쌓이는 중입니다.</div>'}
            ${gaps ? '<div class="stock-note">일부 반월은 결정문이 스캔본이라 빠져 있습니다 — 선은 읽은 고시끼리 이은 것입니다.</div>' : ''}
        </details>`;
    }

    function worldBankRow(series, staleAfter, status) {
        const pts = series.points || [];
        if (!pts.length) return '';
        const [period, value] = pts[pts.length - 1];
        const prev = pts.length > 1 ? pts[pts.length - 2][1] : null;
        const stale = days(`${period}-28`) > staleAfter;
        const pct = prev ? Math.round(((value - prev) / prev) * 1000) / 10 : null;
        const up = (pct ?? 0) >= 0;
        const history = trailingRun(pts.slice(-60).map(([label, v]) => ({ label, value: v })), nextMonth);
        return `<details class="stock-item" open><summary style="cursor:pointer;padding:6px 0"><span class="stock-row" style="display:inline-grid;width:calc(100% - 14px);grid-template-columns:minmax(0,1fr) auto"><span class="nm">${esc(WB_LABEL[series.id] || series.label_ko)}</span><span class="vl">$${fmt(value)}<em>/톤</em></span></span>
            <span class="stock-note" style="display:block">${esc(monthLabel(period))} 평균${pct == null ? '' : ` · 전월 대비 <span class="${up ? 'up' : 'down'}">${up ? '+' : ''}${fmt(pct, 1)}%</span>`}${staleNote(stale || status === 'error')}</span></summary>
            <div class="stock-note">원자료 ‘${esc(series.source_name)}’${series.definition ? ` — ${esc(series.definition)}` : ''}</div>
            ${chartFor(history, ' $/톤', `${series.label_ko} 월평균 최근 ${history.length}개월`)}
        </details>`;
    }

    async function render(countryName = null) {
        const token = ++generation;
        if (typeof currentCommodity === 'undefined' || currentCommodity !== 'thermal_coal') return;
        const host = document.getElementById('news-content');
        if (!host) return;
        host.querySelector('[data-coal-prices]')?.remove();
        // A country screen only gets the price that is that country's own.
        const key = countryName ? (typeof resolveCountry === 'function' ? resolveCountry(countryName)?.label : null) : null;
        const wanted = countryName ? (COUNTRY_ROWS[key] || COUNTRY_ROWS[countryName] || []) : ['hba', 'coal_australian', 'coal_south_african'];
        if (!wanted.length) return;
        const slot = document.createElement('div');
        slot.dataset.coalPrices = '1';
        slot.className = 'stock-card';
        slot.textContent = '석탄 기준가격을 불러오는 중…';
        // World view: right under the futures card, whose note says there is no free
        // futures price -- this is what stands in for it.
        const anchor = countryName ? null : host.querySelector('#futures-slot');
        if (anchor) anchor.after(slot); else host.appendChild(slot);
        try {
            pending ||= fetch('/public/data/coal_prices_v1.json', { cache: 'no-cache' }).then((r) => {
                if (!r.ok) throw Error('unavailable');
                return r.json();
            }).catch((e) => { pending = null; throw e; });
            const data = await pending;
            if (token !== generation || !slot.isConnected || currentCommodity !== 'thermal_coal' || (tradeFocusCountry || null) !== countryName) return;
            if (data.schema_version !== 'coal_prices_v1') throw Error('schema');
            const stale = data.stale_after_days || {};
            const wb = data.worldbank || {};
            const parts = [];
            if (wanted.includes('hba')) parts.push(hbaRows(data.hba, stale.hba ?? 24));
            (wb.series || []).filter((s) => wanted.includes(s.id)).forEach((s) => parts.push(worldBankRow(s, stale.worldbank ?? 80, wb.status)));
            if (!parts.length) { slot.remove(); return; }
            const link = (href, text) => `<a style="color:#7dd3fc" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
            const sources = [];
            if (wanted.includes('hba') && data.hba?.source_url) sources.push(link(data.hba.source_url, '인도네시아 ESDM'));
            if (parts.length > (wanted.includes('hba') ? 1 : 0) && wb.source_url) sources.push(`${link(wb.source_url, 'World Bank Pink Sheet')} (CC BY 4.0)`);
            slot.innerHTML = `<p class="section-title">석탄 기준가격 · 선물가 아님</p>
                <div class="stock-note">공식 기준가격과 월평균 지수입니다. 실시간 시세가 아니며, 열량·산정 방식이 달라 서로 직접 비교할 수 없습니다.</div>
                ${parts.join('')}
                <div class="stock-note">출처 · ${sources.join(' · ')}</div>`;
            if (typeof wireSparkCharts === 'function') wireSparkCharts(slot);
        } catch (_) {
            if (slot.isConnected) slot.textContent = '석탄 기준가격을 불러오지 못했습니다.';
        }
    }
    window.CoalPrices = { render };
})();
