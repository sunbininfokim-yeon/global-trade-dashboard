/* Official inventories and price benchmarks for the gas trade view. */
(() => {
    let pending;
    let generation = 0;
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const fmt = (v) => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('ko-KR', {maximumFractionDigits: 3}) : '—';
    const units = {Bcf:'Bcf', TWh:'TWh', TJ:'TJ', million_m3_gas:'백만㎥(기체)', thousand_m3_LNG:'천㎥(LNG 액체)'};
    const statusNames = {ok:'공식 관측', partial:'품질·범위 주의', stale:'오래된 관측', unsupported:'공개 재고 미확인', requires_key:'연결 대기', error:'수집 실패 · 이전 관측', provider_required:'제공업체 확인 필요'};
    const countries = {US:'United States of America', KR:'South Korea', JP:'Japan', TW:'Taiwan', TH:'Thailand', CN:'China', VN:'Vietnam', IN:'India', ID:'Indonesia', MY:'Malaysia', SG:'Singapore', CA:'Canada', AU:'Australia', DE:'Germany', FR:'France', IT:'Italy', NL:'Netherlands', AT:'Austria', PL:'Poland', CZ:'Czech Republic', ES:'Spain', GB:'United Kingdom', BE:'Belgium', PT:'Portugal'};
    const primary = ['png.nw2_epg0_swo_r48_bcf.w', 'agsi:EU', 'agsi:REHDEN', 'jodi:KR', 'jodi:JP', 'aemo:530042'];
    const sourceUrls = {eia:'https://ir.eia.gov/ngs/ngs.html', jodi:'https://www.jodidata.org/gas/database/data-downloads.aspx', aemo:'https://www.aemo.com.au/energy-systems/gas/gas-bulletin-board-gbb/data-gbb/gas-flows', agsi:'https://agsi.gie.eu/', alsi:'https://alsi.gie.eu/'};
    function effectiveStatus(s) {
        if (['error','requires_key','unsupported','provider_required'].includes(s.status)) return s.status;
        const p = s.latest?.period;
        if (!p) return 'unsupported';
        const stamp = p.length === 7 ? new Date(Date.UTC(+p.slice(0,4), +p.slice(5,7), 0)) : new Date(p+'T00:00:00Z');
        return (Date.now() - stamp.getTime()) / 86400000 > (s.stale_after_days || {daily:4,weekly:15,monthly:120}[s.frequency] || 4) ? 'stale' : s.status;
    }
    // Countries whose facility name alone doesn't say where it is (e.g.
    // AEMO's "Iona UGS" reads as a proper name, not a place) get a country
    // suffix appended to the displayed name.
    const countrySuffix = {AU:'호주'};
    function inventoryCard(s, alwaysOpen) {
        const p = s.latest;
        const status = effectiveStatus(s);
        const suffix = {day_on_day:'전일',week_on_week:'전주',month_on_month:'전월'}[s.change_period] || '이전';
        // Daily/weekly series show up to a year; monthly series (which tend to
        // carry much longer official history, e.g. JODI) show up to 5 years.
        const windowSize = {daily: 365, weekly: 52, monthly: 60}[s.frequency] || 52;
        const history = (s.observations || []).slice(-windowSize);
        const consecutive = history.every((p, i) => {
            if (!i) return true;
            const prev = history[i-1].period;
            if (s.frequency === 'monthly') return (+p.period.slice(0,4)*12 + +p.period.slice(5,7)) - (+prev.slice(0,4)*12 + +prev.slice(5,7)) === 1;
            return (new Date(p.period) - new Date(prev)) / 86400000 === (s.frequency === 'weekly' ? 7 : 1);
        });
        const chart = consecutive && history.length > 1 && history.every(p => typeof p.value === 'number' && Number.isFinite(p.value))
            ? sparkChartHtml({points:history.map(p => ({label:p.period,value:p.value})),unit:units[s.unit] || s.unit,formatValue:fmt,ariaLabel:`${esc(s.label_ko)} 최근 ${history.length}개 관측`}) : '';
        const special = s.id === 'agsi:REHDEN' ? '독일 합계에 포함되는 개별 시설' : s.provider === 'aemo' ? '호주 개별 시설 · 전국 합계 아님' : s.provider === 'jodi' ? '월말 국가 재고 · 기체 환산' : s.provider === 'alsi' ? 'LNG 터미널 재고' : '지하 가스 저장';
        const name = countrySuffix[s.country] ? `${s.label_ko} (${countrySuffix[s.country]})` : s.label_ko;
        return `<details class="stock-item"${alwaysOpen ? ' open' : ''}><summary style="cursor:pointer;padding:6px 0"><span class="stock-row" style="display:inline-grid;width:calc(100% - 14px);grid-template-columns:minmax(0,1fr) auto"><span class="nm">${esc(name)}</span><span class="vl">${fmt(p?.value)}<em>${esc(units[s.unit] || s.unit)}</em></span></span>
            <span class="stock-note" style="display:block">${esc(p?.period || '관측일 없음')} · ${esc(statusNames[status] || status)}${p?.fill_pct != null ? ` · 충전율 ${fmt(p.fill_pct)}%` : ''}</span></summary>
            <div class="stock-note">${esc(special)} · ${suffix} 대비 ${status === 'error' ? '—' : fmt(s.change)} · <a style="color:#7dd3fc" href="${sourceUrls[s.provider]}" target="_blank" rel="noopener noreferrer">${esc(s.provider.toUpperCase())}</a></div>
            ${chart}
        </details>`;
    }
    async function render(countryName = null) {
        const token = ++generation;
        if (typeof currentCommodity === 'undefined' || currentCommodity !== 'gas') return;
        const host = document.getElementById('news-content');
        if (!host) return;
        host.querySelector('[data-gas-storage]')?.remove();
        const slot = document.createElement('div');
        slot.dataset.gasStorage = '1';
        slot.className = 'stock-card';
        slot.textContent = '천연가스 재고를 불러오는 중…';
        const slotSpinner = document.createElement('span');
        slotSpinner.className = 'inline-spinner';
        slotSpinner.setAttribute('aria-hidden', 'true');
        slot.appendChild(slotSpinner);
        host.appendChild(slot);
        try {
            pending ||= fetch('/public/data/gas_storage_v1.json', {cache:'no-cache'}).then(r => {
                if (!r.ok) throw Error('unavailable');
                return r.json();
            }).catch(e => {pending = null; throw e;});
            const data = await pending;
            if (token !== generation || !slot.isConnected || currentCommodity !== 'gas' || (tradeFocusCountry || null) !== countryName) return;
            if (data.schema_version !== 'gas_storage_v1' || !Array.isArray(data.series)) throw Error('schema');
            let selected = data.series;
            if (countryName) {
                const key = resolveCountry(countryName)?.key;
                selected = selected.filter(s => countries[s.country] && key && resolveCountry(countries[s.country])?.key === key);
            }
            const top = countryName ? selected : primary.map(id => selected.find(s=>s.id === id)).filter(Boolean);
            const rest = countryName ? [] : selected.filter(s=>!primary.includes(s.id));
            const benchmarks = (data.benchmarks || []).map(b => `<div class="stock-item"><div class="stock-row" style="grid-template-columns:minmax(0,1fr) auto"><span class="nm">${esc(b.label_ko)}</span><span class="vl">${fmt(b.latest?.value)}<em>${esc(b.unit || '')}</em></span></div><div class="stock-note">${esc(b.latest?.period || '')} · ${esc(statusNames[effectiveStatus(b)] || effectiveStatus(b))} · ${esc(b.source || b.note_ko || '')}</div></div>`).join('');
            slot.innerHTML = `<p class="section-title">천연가스 저장 · 공식 통계</p><div class="stock-note">국가별 기준일·단위가 다릅니다. 재고와 용량, 지하 저장과 LNG 탱크 재고는 합산하지 않습니다.</div>
                ${top.map(s => inventoryCard(s, true)).join('') || '<p class="stock-note">이 국가의 공개 재고는 아직 연결되지 않았습니다.</p>'}
                ${rest.length ? `<details><summary>다른 국가·시설 ${rest.length}개</summary>${rest.map(s => inventoryCard(s, false)).join('')}</details>` : ''}
                <p class="section-title" style="margin-top:12px">가격 기준 · 저장시설과 별도</p>${benchmarks}
                <div class="stock-note">수집 시각 ${esc(data.fetched_at?.slice(0,16).replace('T',' '))} UTC${data.sources?.some(s=>s.status==='error') ? ' · 일부 출처 수집 실패' : ''}</div>`;
            wireSparkCharts(slot);
        } catch (_) {
            if (slot.isConnected) slot.textContent = '천연가스 재고를 불러오지 못했습니다.';
        }
    }
    window.GasStorage = {render};
})();
