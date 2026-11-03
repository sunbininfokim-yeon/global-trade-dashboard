/* Biomass fuels: PKS (palm kernel shell) supply outlook and wood pellet trade.
 *
 * The biomass view (energy menu) holds the whole panel: wood pellet imports
 * into Korea and Japan by supplier and the big exporters (UN Comtrade HS
 * 440131, scripts/yield_model/biomass/pellet_trade.py), then PKS. The
 * thermal-coal and palm-oil views keep a short PKS summary that links there.
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
    // Biomass view (full panel); coal view (co-fired fuel) and palm oil view
    // (where PKS comes from) get the summary.
    const VIEWS = ['thermal_coal', 'palm_oil', 'biomass'];
    const IMPORTERS = { 'South Korea': '한국', Japan: '일본' };
    const EXPORTERS = { USA: '미국', Canada: '캐나다', Vietnam: '베트남', Indonesia: '인도네시아', Malaysia: '말레이시아', Russia: '러시아', Latvia: '라트비아', Estonia: '에스토니아' };
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

    // Kernel-based actuals (MPOB, Malaysia only): last 12 months and the change.
    function monthlyHtml(m) {
        if (!m || m.last12_kt == null) return '';
        const yoy = m.last12_yoy_pct;
        const tone = yoy == null ? '' : ` style="color:${yoy >= 0 ? '#86efac' : '#fdba74'}"`;
        return `<span class="stock-note" style="grid-column:1 / -1;" title="${esc(m.note_ko || '')}">실측 기반 최근 12개월 ${mt(m.last12_kt)}만 t${yoy == null ? '' : ` <span${tone}>(전년비 ${yoy >= 0 ? '+' : ''}${yoy.toFixed(1)}%)</span>`} · 커널 생산 × 1.1</span>`;
    }

    // Actual PKS exports from Indonesia and Malaysia to every buyer (UN Comtrade,
    // exporter side; palm_oil/pks_trade.py).
    let importsPending = null;
    function loadImports() {
        importsPending ||= fetch('/public/data/pks_trade_v1.json', { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return importsPending;
    }
    function importsHtml(d) {
        const r = d?.recent;
        if (!r || r.total_kt == null) return '';
        const yoy = r.yoy_pct;
        const exporters = Object.entries(r.by_exporter_kt || {}).map(([k, v]) => `${esc(k)} ${mt(v)}만`).join(' · ');
        const dest = (r.top_destinations || []).map((x) => `<div class="pks-row" style="cursor:default;">
                <span class="nm">${esc(x.country)}</span><span class="vl" style="font-size:13px;">${mt(x.kt)}만 t <span class="stock-note">${x.share_pct}%</span></span>
                <div class="pks-bar"><i style="width:${Math.min(100, x.share_pct).toFixed(1)}%"></i></div></div>`).join('');
        const korea = (r.top_destinations || []).some((x) => x.country === '한국') ? ''
            : `<div class="stock-note">한국: ${r.korea_kt != null ? `${r.korea_kt.toLocaleString('ko-KR')}천 t` : '—'}</div>`;
        return `<p class="section-title" style="margin-top:10px;">PKS 수출 실적 (인니·말레이시아 → 전 세계)</p>
            <div class="pks-total"><b>${mt(r.total_kt)}만 t</b>${yoy == null ? '' : `<span style="color:${yoy >= 0 ? '#86efac' : '#fdba74'}">${yoy >= 0 ? '+' : ''}${yoy.toFixed(1)}%</span>`}<span class="stock-note">최근 12개월 ~${esc(r.last_month)} · 평균 $${Math.round(r.price_usd_t)}/t</span></div>
            <div class="stock-note" style="margin-bottom:4px;">${exporters} · 수입국별 상위</div>
            ${dest}${korea}
            <div class="stock-note" style="margin-top:4px;">${esc(d.note_ko || '')}</div>`;
    }

    // Wood pellets (HS 440131), UN Comtrade.
    let pelletsPending = null;
    function loadPellets() {
        pelletsPending ||= fetch('/public/data/pellet_trade_v1.json', { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return pelletsPending;
    }
    const yoyHtml = (v) => (v == null ? '' : `<span style="color:${v >= 0 ? '#86efac' : '#fdba74'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span>`);
    const barRow = (name, kt, share) => `<div class="pks-row" style="cursor:default;">
            <span class="nm">${esc(name)}</span><span class="vl" style="font-size:13px;">${mt(kt)}만 t <span class="stock-note">${share}%</span></span>
            <div class="pks-bar"><i style="width:${Math.min(100, share).toFixed(1)}%"></i></div></div>`;
    function importerHtml(label, r) {
        if (!r || r.total_kt == null) return '';
        return `<div class="pks-total"><b>${mt(r.total_kt)}만 t</b>${yoyHtml(r.yoy_pct)}<span class="stock-note">${esc(label)} 최근 12개월 ~${esc(r.last_month)}${r.price_usd_t ? ` · 평균 $${Math.round(r.price_usd_t)}/t` : ''}</span></div>
            <div class="stock-note" style="margin-bottom:4px;">공급국별 상위</div>
            ${(r.top_suppliers || []).map((x) => barRow(x.country, x.kt, x.share_pct)).join('')}`;
    }
    function exportersHtml(list) {
        if (!list?.length) return '';
        const max = list[0].kt || 1;
        return `<p class="section-title" style="margin-top:10px;">주요 수출국 (연간, 수출 신고)</p>
            ${list.map((e) => `<div class="pks-row" style="cursor:default;">
                <span class="nm">${esc(e.country)} <span class="stock-note">${e.year}</span></span>
                <span class="vl" style="font-size:13px;">${mt(e.kt)}만 t ${yoyHtml(e.yoy_pct)}</span>
                <div class="pks-bar"><i style="width:${(100 * e.kt / max).toFixed(1)}%"></i></div></div>`).join('')}`;
    }
    function pelletWorldHtml(d) {
        const kr = d?.recent?.['한국'];
        const jp = d?.recent?.['일본'];
        if (!kr && !jp && !d?.exporters?.length) return '';
        return `<p class="section-title">바이오매스 · 목재펠릿 수입 (한국·일본)</p>
            <div class="stock-note">발전소 혼소 연료. 한국은 PKS보다 목재펠릿을 훨씬 많이 들여옵니다.</div>
            ${importerHtml('한국', kr)}
            ${jp ? `<div style="margin-top:8px;">${importerHtml('일본', jp)}</div>` : ''}
            ${exportersHtml(d.exporters)}
            <div class="stock-note" style="margin-top:4px;">${esc(d.note_ko || '')}</div>`;
    }
    function pelletCountryHtml(d, names) {
        const imp = names.map((n) => IMPORTERS[n]).find(Boolean);
        if (imp && d?.recent?.[imp]) {
            return `<p class="section-title">목재펠릿 수입 · ${esc(imp)}</p>${importerHtml(imp, d.recent[imp])}`;
        }
        const exLabel = names.map((n) => EXPORTERS[n]).find(Boolean);
        const e = exLabel && (d?.exporters || []).find((x) => x.country === exLabel);
        if (!e) return '';
        const toKr = (d?.recent?.['한국']?.top_suppliers || []).find((x) => x.country === exLabel);
        return `<p class="section-title">목재펠릿 수출 · ${esc(exLabel)}</p>
            <div class="pks-total"><b>${mt(e.kt)}만 t</b>${yoyHtml(e.yoy_pct)}<span class="stock-note">${e.year}년 전 세계 수출${e.price_usd_t ? ` · $${Math.round(e.price_usd_t)}/t` : ''}</span></div>
            ${toKr ? `<div class="stock-note">한국 수입 중 ${toKr.share_pct}% (${mt(toKr.kt)}만 t, 최근 12개월)</div>` : ''}`;
    }

    // Coal and palm views: the PKS total and the pellet headline, with a way
    // to the biomass view where the detail lives.
    function summaryHtml(rows, adj, trend, pct, season, pellets) {
        const kr = pellets?.recent?.['한국'];
        const by = rows.map((r) => `${esc(r.label)} ${mt(r.p.adjusted_kt ?? r.p.trend_kt)}만`).join(' · ');
        return `<p class="section-title">바이오매스 · PKS(팜 껍질) 공급 전망 ${esc(season)}</p>
            <div class="pks-total"><b>${mt(adj)}만 t</b>${pct < 0 ? `<s>${mt(trend)}만 t</s><span class="pks-down">${pct}%</span>` : '<span class="stock-note">추세 수준</span>'}</div>
            <div class="stock-note">${by}</div>
            ${kr ? `<div class="stock-note" style="margin-top:4px;">목재펠릿 한국 수입 최근 12개월 ${mt(kr.total_kt)}만 t${kr.yoy_pct == null ? '' : ` (${kr.yoy_pct >= 0 ? '+' : ''}${kr.yoy_pct.toFixed(1)}%)`}</div>` : ''}
            <a href="#" class="stock-note" data-goto-biomass style="display:inline-block;margin-top:6px;color:#7dd3fc;">바이오매스 화면에서 산지별 판정·수출 실적·목재펠릿 보기 →</a>`;
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
            ${monthlyHtml(r.p.monthly)}
        </div>`;
    }

    async function render(countryName = null) {
        const token = ++generation;
        const host = document.getElementById('news-content');
        if (!host) return;
        host.querySelector('[data-pks]')?.remove();
        if (typeof currentCommodity === 'undefined' || !VIEWS.includes(currentCommodity)) return;
        const key = countryName ? (typeof resolveCountry === 'function' ? resolveCountry(countryName)?.label : countryName) : null;
        const isBio = currentCommodity === 'biomass';
        const names = [key, countryName].filter(Boolean);
        const producer = countryName && COUNTRIES.some((c) => names.includes(c.country));
        const pelletCountry = names.some((n) => IMPORTERS[n] || EXPORTERS[n]);
        if (countryName && !producer && !(isBio && pelletCountry)) return;
        const slot = document.createElement('div');
        slot.dataset.pks = '1';
        slot.className = 'stock-card';
        slot.textContent = isBio ? '바이오매스 자료를 불러오는 중…' : 'PKS 공급 전망을 불러오는 중…';
        const coal = host.querySelector('[data-coal-prices]');
        if (coal) coal.after(slot); else host.appendChild(slot);
        try {
            let [rows, imports, pellets] = await Promise.all([load(), loadImports(), loadPellets()]);
            if (token !== generation || !slot.isConnected) return;
            if (countryName) rows = rows.filter((r) => r.country === key || r.country === countryName);
            const pelletPart = !isBio ? '' : (countryName ? pelletCountryHtml(pellets, names) : pelletWorldHtml(pellets));
            if (!rows.length) {
                if (pelletPart) slot.innerHTML = pelletPart; else slot.remove();
                return;
            }
            rows.sort((a, b) => b.p.trend_kt - a.p.trend_kt);
            const trend = rows.reduce((s, r) => s + r.p.trend_kt, 0);
            const adj = rows.reduce((s, r) => s + (r.p.adjusted_kt ?? r.p.trend_kt), 0);
            const pct = Math.round((1000 * (adj - trend)) / trend) / 10;
            const season = rows[0].season;
            if (!isBio && !countryName) {
                slot.innerHTML = summaryHtml(rows, adj, trend, pct, season, pellets);
                slot.querySelector('[data-goto-biomass]')?.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    document.querySelector('[data-target="biomass"]')?.click();
                });
                return;
            }
            slot.innerHTML = `${pelletPart ? `${pelletPart}<div style="height:12px;"></div>` : ''}<p class="section-title">바이오매스 · PKS(팜 껍질) 공급 전망 ${esc(season)}</p>
                <div class="stock-note">발전소 혼소 연료. 팜유 산지의 기상 판정을 PKS 물량으로 환산한 추정입니다.</div>
                <div class="pks-total"><b>${mt(adj)}만 t</b>${pct < 0 ? `<s>${mt(trend)}만 t</s><span class="pks-down">${pct}%</span>` : '<span class="stock-note">추세 수준</span>'}</div>
                <div class="stock-note" style="margin-bottom:4px;">${rows.length}개 산지 합계 · 흐린 막대 = 추세, 진한 막대 = 기상 판정 반영</div>
                ${rows.map((r) => rowHtml(r, rows[0].p.trend_kt)).join('')}
                ${countryName ? '' : importsHtml(imports)}
                <div class="stock-note" style="margin-top:6px;">PKS 생산 통계는 어느 나라도 공개하지 않습니다. CPO 추세의 약 25%(업계 경험치 22~30%)로 환산했고, 말레이시아는 MPOB 월별 팜커널 생산으로 최근 12개월 실측 기반 추정을 함께 보여 줍니다. 불리 판정은 과거 불리 해의 평균 감소폭을 적용했습니다. 행을 누르면 팜 카드의 판정 근거로 이동합니다.</div>`;
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
