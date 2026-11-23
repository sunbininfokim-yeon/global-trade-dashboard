/* Northern Sea Route (북극항로) -- 해운 > 북극항로 tab.
 * Reads public/data/sea_route_v1.json (scripts/sea_route.py + sea_route_line.py,
 * refreshed daily by sea_ice_refresh.yml). Moved here from the crop monitor
 * on 2026-11-23 (sean): the crop monitor keeps only sea ice extent and SST.
 * Exposes window.ShippingArctic.render(slot); shipping.js frames it.
 */
(() => {
    const mdKo = (iso) => (iso ? `${Number(iso.slice(5, 7))}월 ${Number(iso.slice(8, 10))}일` : '');
    const SEA_ROUTE_DOY0 = 182;   // 7월 1일
    const SEA_ROUTE_DOY1 = 335;   // 12월 1일
    const doyOf = (iso) => {
        const d = new Date(`${iso}T00:00:00Z`);
        return Math.round((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 86400000) + 1;
    };
    /** One vertical bar per year from the opening to the closing day. */
    const seaRouteSeasonBars = (doc, h = 130) => {
        const rows = (doc.seasons || []).filter((r) => r.year >= 1979);
        if (!rows.length) return '';
        const span = SEA_ROUTE_DOY1 - SEA_ROUTE_DOY0;
        const y = (n) => ((Math.min(SEA_ROUTE_DOY1, Math.max(SEA_ROUTE_DOY0, n)) - SEA_ROUTE_DOY0) / span) * h;
        const w = 100 / rows.length;
        const last = doyOf(doc.latest_date);
        const bars = rows.map((r, i) => {
            const left = `left:${(i * w).toFixed(2)}%;width:calc(${w.toFixed(2)}% - 1px);`;
            if (!r.open) {
                return `<span title="${r.year}: 열리지 않음" style="position:absolute;${left}top:${h - 3}px;height:3px;background:rgba(148,163,184,.35);"></span>`;
            }
            const a = doyOf(r.open);
            const b = r.close ? doyOf(r.close) : last;
            const tip = `${r.year}: ${r.open.slice(5)} ~ ${r.close ? r.close.slice(5) : '열려 있음'} (${r.days}일)`;
            return `<span title="${tip}" style="position:absolute;${left}top:${y(a).toFixed(1)}px;height:${Math.max(2, y(b) - y(a)).toFixed(1)}px;
                background:${r.close ? (r.year >= 2007 ? 'rgba(251,191,36,.85)' : 'rgba(251,191,36,.5)') : '#fde68a'};border-radius:1px;"></span>`;
        }).join('');
        const ticks = [[182, '7월'], [213, '8월'], [244, '9월'], [274, '10월'], [305, '11월']].map(([n, t]) => `
            <div style="position:absolute;left:0;right:0;top:${y(n).toFixed(1)}px;border-top:1px dashed rgba(148,163,184,.18);">
                <span style="position:absolute;left:-30px;top:-6px;font-size:10px;color:#94a3b8;">${t}</span></div>`).join('');
        return `<div style="position:relative;height:${h}px;margin:10px 0 0 30px;">${ticks}${bars}</div>
            <div class="climate-sub" style="display:flex;justify-content:space-between;margin-left:30px;"><span>${rows[0].year}</span><span>${rows[rows.length - 1].year}</span></div>`;
    };

    const ROUTE_CLASS_COLOR = { open_water: '#fbbf24', arc4: '#38bdf8', arc7: 'rgba(148,163,184,.55)' };
    /** Route-line seasons by ship class, overlaid per year (widest class behind). */
    const seaRouteClassBars = (L, h = 140) => {
        const cls = [...(L.classes || [])].reverse();          // arc7 behind, open water in front
        const years = (L.classes?.[0]?.seasons || []).map((r) => r.year);
        if (!years.length) return '';
        const D0 = 121, D1 = 350, span = D1 - D0;               // 5월 1일 ~ 12월 16일
        const y = (n) => ((Math.min(D1, Math.max(D0, n)) - D0) / span) * h;
        const w = 100 / years.length;
        const last = doyOf(L.latest_date);
        const bars = cls.map((c) => c.seasons.map((r) => {
            if (!r.open) return '';
            const i = years.indexOf(r.year);
            const a = doyOf(r.open), b = r.close ? doyOf(r.close) : last;
            const inset = c.id === 'open_water' ? 0.25 : c.id === 'arc4' ? 0.12 : 0;
            return `<span title="${r.year} ${c.label_ko}: ${mdKo(r.open)} ~ ${r.close ? mdKo(r.close) : '열려 있음'} (${r.days}일)"
                style="position:absolute;left:calc(${(i * w + w * inset).toFixed(2)}%);width:calc(${(w * (1 - 2 * inset)).toFixed(2)}% - 1px);
                top:${y(a).toFixed(1)}px;height:${Math.max(2, y(b) - y(a)).toFixed(1)}px;background:${ROUTE_CLASS_COLOR[c.id]};border-radius:1px;"></span>`;
        }).join('')).join('');
        const ticks = [[121, '5월'], [182, '7월'], [244, '9월'], [305, '11월']].map(([n, t]) => `
            <div style="position:absolute;left:0;right:0;top:${y(n).toFixed(1)}px;border-top:1px dashed rgba(148,163,184,.18);">
                <span style="position:absolute;left:-30px;top:-6px;font-size:10px;color:#94a3b8;">${t}</span></div>`).join('');
        const val = (L.validation || []).map((v) => {
            const i = years.indexOf(v.year);
            if (i < 0) return '';
            const a = doyOf(v.first_entry), b = v.last_exit ? doyOf(v.last_exit) : null;
            const x = `left:calc(${(i * w + w / 2).toFixed(2)}% - 4px);`;
            return `<span title="${v.year} 실제 첫 통과" style="position:absolute;${x}top:${(y(a) - 4).toFixed(1)}px;color:#f472b6;font-size:9px;">▼</span>`
                + (b ? `<span title="${v.year} 실제 마지막 통과" style="position:absolute;${x}top:${(y(b) - 4).toFixed(1)}px;color:#f472b6;font-size:9px;">▲</span>` : '');
        }).join('');
        return `<div style="position:relative;height:${h}px;margin:10px 0 0 30px;">${ticks}${bars}${val}</div>
            <div class="climate-sub" style="display:flex;justify-content:space-between;margin-left:30px;"><span>${years[0]}</span><span>${years[years.length - 1]}</span></div>
            <div class="climate-sub" style="margin-top:2px;">
                ${(L.classes || []).map((c) => `<span style="display:inline-block;width:9px;height:9px;background:${ROUTE_CLASS_COLOR[c.id]};margin:0 3px 0 8px;"></span>${c.label_ko.split(' (')[0]}`).join('')}
                <span style="color:#f472b6;margin-left:8px;">▼▲</span> 실제 첫·마지막 통과 (CHNL)</div>`;
    };

    const renderSeaRouteLineCard = (doc) => {
        const L = doc.route_line;
        const legChips = (L.latest_legs || []).map((g) => {
            const c = g.concentration;
            const col = c == null ? '' : c <= 15 ? 'color:#86efac;' : c <= 50 ? 'color:#7dd3fc;' : c <= 80 ? 'color:#cbd5e1;' : 'color:#94a3b8;';
            return `<span class="oa-chip" style="${col}">${g.name_ko} ${c == null ? '-' : `${Math.round(c)}%`}</span>`;
        }).join('');
        const target = L.classes?.[0]?.outlook?.target_year;
        const rows = (L.classes || []).map((c) => {
            const o = c.outlook || {};
            const op = o.status === 'open' ? `<b style="color:#86efac;">열림</b> (${mdKo(o.open_observed)}~)` : o.open ? `<b>${o.open.date_ko}</b>` : '-';
            const cl = o.close ? `<b>${o.close.date_ko}</b>` : '-';
            const days = o.days ? `${Math.round(o.days.point)}일` : '-';
            return `<div class="climate-table-row" style="font-size:12px;align-items:flex-start;">
                <span style="flex:1.4;"><span style="display:inline-block;width:8px;height:8px;background:${ROUTE_CLASS_COLOR[c.id]};margin-right:5px;"></span>${c.label_ko}</span>
                <span style="flex:1;text-align:right;">${op}${o.open ? `<br><span class="climate-sub">${o.open.range_68_ko[0]}~${o.open.range_68_ko[1]}</span>` : ''}</span>
                <span style="flex:1;text-align:right;">${cl}${o.close ? `<br><span class="climate-sub">${o.close.range_68_ko[0]}~${o.close.range_68_ko[1]}</span>` : ''}</span>
                <span style="flex:.7;text-align:right;">${days}<br><span class="climate-sub">평소 ${o.last10_mean_days ?? '-'}</span></span>
            </div>`;
        }).join('');
        const methods = [...new Set((L.classes || []).flatMap((c) => ['open', 'close', 'days'].map((k) => c.outlook?.[k]?.method).filter(Boolean)))];
        const skill = (L.classes || []).map((c) => {
            const cells = ['open', 'close', 'days'].map((k) => {
                const ms = c.outlook?.skill_by_issue_month || [];
                const base = ms.find((r) => r[k])?.[k]?.mae_trend;
                const hit = ms.find((r) => r[k] && Math.max(r[k].skill_F ?? -9, r[k].skill_FV ?? -9) >= 0.1);
                const best = hit ? Math.max(hit[k].skill_F ?? -9, hit[k].skill_FV ?? -9) : null;
                const lab = { open: '열림', close: '닫힘', days: '기간' }[k];
                return base == null ? '' : hit
                    ? `<span style="color:#86efac;">${lab} ±${Math.round(base)}일 → ${hit.issue}부터 ±${Math.round(base * (1 - best))}일</span>`
                    : `<span>${lab} ±${Math.round(base)}일 (추세 이상 어려움)</span>`;
            }).filter(Boolean).join(' · ');
            return `<div class="climate-sub" style="margin-top:4px;"><b style="color:#cbd5e1;">${c.label_ko.split(' (')[0]}</b>: ${cells}</div>`;
        }).join('');
        const val = (L.validation || []).map((v) => {
            const c7 = v.arc7, c4 = v.arc4, ow = v.open_water;
            return `<div class="climate-table-row" style="font-size:11px;"><span style="flex:.5;">${v.year}</span>
                <span style="flex:1.2;">실제 ${mdKo(v.first_entry)} ~ ${v.last_exit ? mdKo(v.last_exit) : '?'} (${v.n}회)</span>
                <span style="flex:1.6;" class="climate-sub">Arc7 ${c7?.open ? `${mdKo(c7.open)}~${mdKo(c7.close)}` : '-'} · Arc4 ${c4?.open ? `${mdKo(c4.open)}~${mdKo(c4.close)}` : '-'} · 일반 ${ow?.open ? `${mdKo(ow.open)}~${mdKo(ow.close)}` : '안 열림'}</span></div>`;
        }).join('');
        const evs = (L.events || []).map((e) => `<div style="margin-top:4px;padding:6px 8px;border-radius:6px;font-size:12px;
                background:${e.kind === 'open' ? 'rgba(34,197,94,.14)' : 'rgba(248,113,113,.14)'};color:${e.kind === 'open' ? '#86efac' : '#fca5a5'};">
                ${e.kind === 'open' ? '🟢 열림' : '🔴 닫힘'} · ${e.label_ko.split(' (')[0]} · ${mdKo(e.date)}${e.days_ago ? ` (${e.days_ago}일 전)` : ' (오늘)'}</div>`).join('');
        const nowChips = (L.classes || []).map((c) => {
            const open = L.status_now?.[c.id] === 'open';
            return `<span class="oa-chip" style="${open ? 'color:#86efac;border-color:rgba(134,239,172,.5);' : ''}">${c.label_ko.split(' (')[0]} ${open ? '열림' : '닫힘'}</span>`;
        }).join('');
        const C = L.compare;
        const cmp = C ? `<div class="climate-sub" style="margin-top:10px;font-weight:600;color:#e2e8f0;">${C.from_ko}→${C.to_ko} 항로 비교</div>
            ${C.routes.map((r) => `<div class="climate-table-row" style="font-size:12px;">
                <span style="flex:1;">${r.id === 'nsr' ? `<b style="color:#fbbf24;">${r.name_ko}</b>` : r.name_ko}</span>
                <span style="width:30%;text-align:right;">${r.nm.toLocaleString()}해리</span>
                <span style="width:22%;text-align:right;"><b>${r.days}일</b></span></div>`).join('')}
            <div class="climate-sub" style="margin-top:4px;">북극항로가 수에즈보다 거리 ${C.saving_vs_suez_pct}%·약 ${Math.round(C.saving_vs_suez_days)}일 짧고, 희망봉 우회보다 약 ${Math.round(C.saving_vs_cape_days)}일 짧습니다.
                ${target ? ` ${target}년 일반 선박 기준 이 이점을 쓸 수 있는 기간은 약 ${Math.round(L.classes?.[0]?.outlook?.days?.point ?? 0)}일입니다.` : ''}</div>
            <div class="climate-sub" style="margin-top:2px;">${C.note_ko}</div>` : '';
        return `<div class="climate-card">
            <h3>북극항로(북동항로) 열리는 기간 <span class="src-tag">항로선 위 얼음 · 매일 자동 계산</span></h3>
            <div class="ocean-affects" style="margin-top:2px;">${nowChips}</div>
            ${evs}
            <div class="climate-sub" style="margin-top:6px;">지금 항로 구간별 얼음 (${L.latest_date})</div>
            <div class="ocean-affects" style="margin-top:4px;">${legChips}</div>
            <div class="climate-sub" style="margin-top:8px;font-weight:600;color:#e2e8f0;">${target}년 시즌 전망 (68% 범위)</div>
            <div class="climate-table-row" style="font-size:10px;color:#94a3b8;"><span style="flex:1.4;">선급</span><span style="flex:1;text-align:right;">열림</span><span style="flex:1;text-align:right;">닫힘</span><span style="flex:.7;text-align:right;">기간</span></div>
            ${rows}
            <div class="climate-sub" style="margin-top:4px;">방법: <b>${methods.join(', ') || '추세'}</b> · 범위는 2001년 이후 같은 날짜 전진 검증 오차 · "평소" = 최근 10년 평균 일수</div>
            ${seaRouteClassBars(L)}
            ${cmp}
            ${val ? `<div class="climate-sub" style="margin-top:8px;font-weight:600;color:#e2e8f0;">실제 운항 기록과 비교</div>${val}
                <div class="climate-sub" style="margin-top:2px;">실제 통과는 빙급선과 쇄빙선 호위를 포함하므로 Arc7 시즌과 비교하는 게 맞습니다.</div>` : ''}
            <details class="climate-fold" style="margin-top:6px;">
                <summary class="climate-click" style="cursor:pointer;font-size:11px;color:#7dd3fc;list-style:none;">발행 시점별 과거 성적 ▾</summary>
                ${skill}
                <div class="climate-sub" style="margin-top:4px;">±일 = 추세만 썼을 때 평균 오차. 초록 = 그 달 1일부터 항로 얼음·얼음 부피(PIOMAS)를 넣으면 오차가 줄어 엔진이 자동으로 바꿔 씀 (4~8월 1일 발행 기준 과거 검증).</div>
            </details>
            <div class="climate-sub" style="margin-top:6px;">${L.note_ko || ''}</div>
            ${doc.outlook?.days ? `<div class="climate-sub" style="margin-top:4px;">참고(바다 전체 평균 기준): ${doc.outlook.target_year}년 ${doc.outlook.open?.date_ko || ''}~${doc.outlook.close?.date_ko || ''}, 약 ${Math.round(doc.outlook.days.point)}일.</div>` : ''}
        </div>`;
    };

    const renderSeaRouteCard = (doc) => {
        if (doc?.route_line?.classes?.length) return renderSeaRouteLineCard(doc);
        if (!doc?.seasons?.length) return '';
        const o = doc.outlook || {};
        const pct = (v) => `${Math.round(v * 100)}%`;
        const seaChips = (doc.seas || []).map((s) => {
            const f = doc.latest_fraction?.[s.id];
            const open = f != null && f <= doc.rule.open_fraction;
            return `<span class="oa-chip" style="${open ? 'color:#86efac;' : ''}">${s.name_ko} 얼음 ${f != null ? pct(f) : '-'}</span>`;
        }).join('');
        const statusKo = o.status === 'open' ? `<b style="color:#86efac;">열려 있음</b> (${mdKo(o.open_observed)} 열림)`
            : '<b>닫힘</b>';
        const rng = (x) => (x ? `68% ${x.range_68_ko[0]}~${x.range_68_ko[1]}` : '');
        const thin = (x) => (x && x.n_test_years < 8 ? ` <span style="color:#fbbf24;">(검증 ${x.n_test_years}년뿐, 참고용)</span>` : '');
        const line = (label, x) => (x ? `<div class="climate-table-row" style="font-size:12px;">
                <span style="flex:1;">${label}</span><span style="text-align:right;"><b>${x.date_ko}</b> <span class="climate-sub">${rng(x)}</span>${thin(x)}</span></div>` : '');
        const d = o.days;
        const t = doc.trend || {};
        const strict = Object.entries(doc.sensitivity_days?.['0.15'] || {}).filter(([, n]) => n > 0).map(([y]) => y);
        return `<div class="climate-card">
            <h3>북극항로(북동항로) 열리는 기간 <span class="src-tag">매일 자동 계산</span></h3>
            <div class="climate-sub">지금 항로: ${statusKo} · ${doc.latest_date} 기준</div>
            <div class="ocean-affects" style="margin-top:4px;">${seaChips}</div>
            <div class="climate-sub" style="margin-top:8px;font-weight:600;color:#e2e8f0;">${o.target_year}년 시즌 전망</div>
            ${o.status === 'open' ? `<div class="climate-table-row" style="font-size:12px;"><span style="flex:1;">열림 (관측)</span><span><b>${mdKo(o.open_observed)}</b></span></div>` : line('열림', o.open)}
            ${line('닫힘', o.close)}
            ${d ? `<div class="climate-table-row" style="font-size:12px;"><span style="flex:1;">열린 기간</span>
                <span style="text-align:right;"><b>${Math.round(d.point)}일</b> <span class="climate-sub">68% ${Math.round(d.range_68[0])}~${Math.round(d.range_68[1])}일 · 95% ${Math.round(d.range_95[0])}~${Math.round(d.range_95[1])}일</span></span></div>` : ''}
            <div class="climate-sub" style="margin-top:4px;">방법: <b>${d?.method || '추세'}</b> · 범위는 2001년 이후 같은 날짜 전진 검증 오차 · ${o.opened_last10 || ''}</div>
            ${(o.skill_by_issue_month || []).length ? `<details class="climate-fold" style="margin-top:6px;">
                <summary class="climate-click" style="cursor:pointer;font-size:11px;color:#7dd3fc;list-style:none;">발행 시점별 과거 성적 ▾</summary>
                ${o.skill_by_issue_month.map((r) => `<div class="climate-table-row" style="font-size:11px;">
                    <span style="flex:1;">${r.issue} 발행</span>
                    ${['open', 'close', 'days'].map((k) => (r[k] ? `<span style="width:25%;text-align:right;color:${r[k].skill >= 0.1 ? '#86efac' : '#94a3b8'};">
                        ${{ open: '열림', close: '닫힘', days: '기간' }[k]} ±${Math.round(r[k].skill >= 0.1 ? r[k].mae_model : r[k].mae_trend)}일</span>` : '')).join('')}
                </div>`).join('')}
                <div class="climate-sub" style="margin-top:4px;">초록 = 그 시점의 얼음 상태를 넣으면 추세보다 10% 이상 정확해짐 (그때부터 엔진이 자동으로 바꿔 씀).
                    7월까지는 얼음이 아직 꽉 차 있어 추세 이상으로 맞히기 어렵습니다.</div>
            </details>` : ''}
            ${seaRouteSeasonBars(doc)}
            <div class="climate-sub" style="margin-top:4px;">막대 = 해마다 네 바다가 동시에 열린 기간 (회색 줄 = 안 열린 해).
                ${t.days_per_decade != null ? `열린 기간 추세 ${t.days_per_decade > 0 ? '+' : ''}${t.days_per_decade}일 / 10년 · ${t.first10} 평균 ${t.first10_mean_days}일 → ${t.last10} 평균 ${t.last10_mean_days}일.` : ''}</div>
            ${strict.length ? `<div class="climate-sub" style="margin-top:4px;">더 엄격하게 바다 전체가 85% 이상 녹아야 열림으로 보면: ${strict.join('·')}년만 열렸습니다.</div>` : ''}
            <div class="climate-sub" style="margin-top:6px;">${doc.rule?.note_ko || ''}</div>
        </div>`;
    };

    const render = async (slot) => {
        slot.innerHTML = '<p class="shipping-note">북극항로 자료를 불러오는 중…</p>';
        let doc = null;
        try {
            const r = await fetch('/public/data/sea_route_v1.json', { cache: 'no-cache' });
            doc = r.ok ? await r.json() : null;
        } catch (_) { doc = null; }
        if (!doc) {
            slot.innerHTML = '<div class="shipping-error"><strong>북극항로 자료를 불러오지 못했습니다.</strong></div>';
            return;
        }
        slot.innerHTML = `<div class="arctic-route-wrap">${renderSeaRouteCard(doc)}</div>`;
    };

    window.ShippingArctic = { render };
})();
