/* Brent: estimate, assumptions, forecast, score -- on the crude-oil trade view.
 *
 * Data: public/data/oil_balance_v1.json from scripts/oil_balance/build_oil_balance.py (EIA STEO, FRED Brent and
 * broad dollar, Yahoo Brent futures; all free). Three layers, kept apart:
 *   1 identity    supply - demand = OECD + China + other stock change (checks assumptions against each other)
 *   2 relation    log Brent = b0 + b1*OECD stock deviation (mb) + b2*OPEC spare capacity + b3*log dollar,
 *                 re-fitted every build, with rival structures, rolling windows and a back-test shown below
 *   3 assumptions the inputs panel (defaults and sources from config/assumptions_v1.json)
 * project() and simulate() are the same arithmetic as scripts/oil_balance/oil_balance/forecast.py: keep in step.
 */
(() => {
    const VIEWS = ['oil'];
    const DAYS = 30.4;
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const usd = (v, d = 0) => (Number.isFinite(v) ? `$${v.toFixed(d)}` : '—');
    const num = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '—');
    const sgn = (v, d = 1) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${v.toFixed(d)}` : '—');
    let pending;
    let generation = 0;
    let state = null;          // {inp, probs}; null = defaults from the file
    let cache = null;          // {key, sim, central}

    if (!document.querySelector('style[data-oilbal-style]')) {
        const css = document.createElement('style');
        css.dataset.oilbalStyle = '1';
        css.textContent = `
            [data-oilbal] .ob-line { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#e2e8f0; padding:5px 0; border-top:1px solid rgba(255,255,255,0.06); }
            [data-oilbal] table.ob-tab { width:100%; border-collapse:collapse; font-size:12px; color:#e2e8f0; margin-top:4px; }
            [data-oilbal] table.ob-tab th { color:#94a3b8; font-weight:500; text-align:right; padding:4px 2px; border-bottom:1px solid rgba(255,255,255,0.08); }
            [data-oilbal] table.ob-tab td { text-align:right; padding:4px 2px; border-bottom:1px solid rgba(255,255,255,0.04); font-variant-numeric:tabular-nums; }
            [data-oilbal] table.ob-tab th:first-child, [data-oilbal] table.ob-tab td:first-child { text-align:left; }
            [data-oilbal] table.ob-tab tr.ob-on td { background:rgba(167,139,250,0.12); }
            [data-oilbal] .ob-chart { width:100%; height:180px; display:block; margin-top:6px; }
            [data-oilbal] .ob-key { font-size:11px; color:#94a3b8; display:flex; flex-wrap:wrap; gap:10px; margin-top:2px; }
            [data-oilbal] .ob-key i { display:inline-block; width:14px; height:0; border-top:2px solid; vertical-align:middle; margin-right:4px; }
            [data-oilbal] .ob-key b { display:inline-block; width:14px; height:8px; background:rgba(167,139,250,0.25); vertical-align:middle; margin-right:4px; }
            [data-oilbal] .ob-btns { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0; }
            [data-oilbal] .ob-btns button { font-size:12px; padding:3px 8px; border-radius:6px; border:1px solid rgba(148,163,184,0.3); background:transparent; color:#cbd5e1; cursor:pointer; }
            [data-oilbal] .ob-in { display:grid; grid-template-columns: 1fr auto; gap:2px 8px; align-items:center; font-size:12px; color:#e2e8f0; padding:5px 0; border-top:1px solid rgba(255,255,255,0.06); }
            [data-oilbal] .ob-in input, [data-oilbal] .ob-in select { width:96px; font-size:12px; padding:2px 4px; background:rgba(15,23,42,0.6); color:#e2e8f0; border:1px solid rgba(148,163,184,0.3); border-radius:4px; text-align:right; }
            [data-oilbal] .ob-in select { width:auto; max-width:190px; text-align:left; }
            [data-oilbal] .ob-in .ob-src { grid-column:1 / span 2; font-size:10.5px; color:#64748b; }
            [data-oilbal] .ob-tag { font-size:10px; padding:0 5px; border-radius:8px; margin-left:4px; }
            [data-oilbal] .ob-tag.data { background:rgba(56,189,248,0.15); color:#7dd3fc; }
            [data-oilbal] .ob-tag.judgment { background:rgba(251,191,36,0.15); color:#fcd34d; }
            [data-oilbal] .ob-warn { font-size:12px; color:#fcd34d; background:rgba(251,191,36,0.08); border-radius:6px; padding:6px 8px; margin-top:6px; }
            [data-oilbal] .ob-ok { font-size:12px; color:#86efac; margin-top:6px; }
            [data-oilbal] details > summary { cursor:pointer; font-size:12.5px; color:#cbd5e1; margin-top:10px; }
            [data-oilbal] .ob-gap-up { color:#fca5a5; } [data-oilbal] .ob-gap-dn { color:#86efac; }`;
        document.head.appendChild(css);
    }

    function load() {
        pending ||= fetch('/public/data/oil_balance_v1.json', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
        return pending;
    }

    // ---------------------------------------------------------------- engine (mirror of forecast.py)

    function project(eng, inp, sc, beta, shocks, extraBuild = 0, spareOffset = 0) {
        beta = beta || eng.beta;
        sc = sc || {};
        const rho = Math.pow(0.5, 1 / inp.half_life);
        const s0 = sc.start || 0, n0 = sc.months || 0;
        let stocks = eng.stocks_anchor, cum = 0, r = eng.r0;
        const ldx = eng.log_dxy + Math.log(1 + inp.dxy_pct / 100);
        const out = [];
        for (let i = 0; i < eng.months.length; i++) {
            const live = i >= s0 && i < s0 + n0;
            const add = (live ? (sc.oecd_add || 0) : 0) + extraBuild;
            if (inp.oecd_mode === 'eia') {
                cum += add * DAYS;
                stocks = eng.stocks_eia[i] + cum;
            } else {
                const b = inp.oecd_mode === 'identity'
                    ? (eng.supply[i] + inp.supply_delta) - (eng.demand[i] + inp.demand_delta) - inp.china_build - inp.other_build
                    : inp.oecd_build;
                stocks += (b + add) * DAYS;
            }
            const spare = (inp.spare_mode === 'eia' ? eng.spare_eia[i] : inp.spare) + spareOffset + (live ? (sc.spare_add || 0) : 0);
            const lfv = beta[0] + beta[1] * (stocks - eng.base5[i]) + beta[2] * spare + beta[3] * ldx;
            r = r * rho + (shocks ? shocks[i] : 0);
            if (n0 && i === s0) r += Math.log(1 + (sc.premium_pct || 0) / 100);
            out.push({ stocks, fv: Math.exp(lfv), price: Math.exp(lfv + r) });
        }
        return out;
    }

    function rng(seed) {
        let a = seed >>> 0, spare = null;
        const u = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
        const g = () => {
            if (spare !== null) { const s = spare; spare = null; return s; }
            let x, y, q;
            do { x = 2 * u() - 1; y = 2 * u() - 1; q = x * x + y * y; } while (q >= 1 || q === 0);
            const f = Math.sqrt(-2 * Math.log(q) / q);
            spare = y * f;
            return x * f;
        };
        return { u, g, uni: () => 2 * u() - 1 };
    }

    function chol(a) {
        const n = a.length, L = a.map(() => new Array(n).fill(0));
        for (let i = 0; i < n; i++) for (let j = 0; j <= i; j++) {
            let s = a[i][j];
            for (let k = 0; k < j; k++) s -= L[i][k] * L[j][k];
            L[i][j] = i === j ? Math.sqrt(Math.max(s, 1e-18)) : s / L[j][j];
        }
        return L;
    }

    const quant = (sorted, q) => { const i = q * (sorted.length - 1), lo = Math.floor(i); return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (i - lo); };

    function simulate(eng, inp, scenarios, spreads, n = 1500, seed = 7) {
        const R = rng(seed);
        const L = chol(eng.cov);
        const tot = scenarios.reduce((s, x) => s + Math.max(x.prob || 0, 0), 0) || 1;
        let acc = 0;
        const cdf = scenarios.map((s) => (acc += Math.max(s.prob || 0, 0) / tot));
        const T = eng.months.length, paths = [];
        for (let k = 0; k < n; k++) {
            const u = R.u();
            let si = cdf.findIndex((c) => u <= c);
            if (si < 0) si = scenarios.length - 1;
            const z = eng.beta.map(() => R.g());
            const beta = eng.beta.map((b, i) => b + z.reduce((s, zj, j) => s + L[i][j] * zj, 0));
            const ji = { ...inp, dxy_pct: inp.dxy_pct + R.uni() * (spreads.dxy_pct || 0),
                half_life: Math.max(0.5, inp.half_life + R.uni() * (spreads.half_life || 0)) };
            const spOff = R.uni() * (spreads.spare || 0);
            const extra = R.uni() * (spreads.oecd_build || 0);
            const rho = Math.pow(0.5, 1 / ji.half_life);
            const sd = eng.sd * Math.sqrt(1 - rho * rho);
            const shocks = Array.from({ length: T }, () => R.g() * sd);
            paths.push(project(eng, ji, scenarios[si], beta, shocks, extra, spOff).map((p) => p.price));
        }
        const out = { p10: [], p50: [], p90: [], annual: {} };
        for (let t = 0; t < T; t++) {
            const col = paths.map((p) => p[t]).sort((a, b) => a - b);
            out.p10.push(quant(col, 0.1)); out.p50.push(quant(col, 0.5)); out.p90.push(quant(col, 0.9));
        }
        const years = [...new Set(eng.months.map((m) => m.slice(0, 4)))];
        years.forEach((y) => {
            const idx = eng.months.map((m, t) => (m.startsWith(y) ? t : -1)).filter((t) => t >= 0);
            const known = Object.entries(eng.actual || {}).filter(([m]) => m.startsWith(y)).map(([, v]) => v);
            if (idx.length + known.length !== 12) return;
            const kn = known.reduce((a, b) => a + b, 0);
            const avg = paths.map((p) => (idx.reduce((s, t) => s + p[t], 0) + kn) / 12).sort((a, b) => a - b);
            out.annual[y] = { p10: quant(avg, 0.1), p50: quant(avg, 0.5), p90: quant(avg, 0.9) };
        });
        return out;
    }

    // ---------------------------------------------------------------- state

    function current(d) {
        if (!state) {
            state = { inp: { ...d.inputs.resolved }, probs: Object.fromEntries(d.scenarios.list.map((s) => [s.id, s.prob])) };
        }
        return state;
    }

    function run(d) {
        const s = current(d);
        const key = JSON.stringify(s);
        if (cache?.key === key) return cache;
        const scen = d.scenarios.list.map((x) => ({ ...x, prob: Number(s.probs[x.id]) || 0 }));
        cache = { key, sim: simulate(d.engine, s.inp, scen, d.inputs.spreads), central: project(d.engine, s.inp) };
        return cache;
    }

    // fair value by month: history from the file, the projected months from the current inputs
    function fvByMonth(d, res) {
        const out = {};
        d.path.forEach((p) => { if (Number.isFinite(p.fair_value)) out[p.month] = p.fair_value; });
        d.engine.months.forEach((m, i) => { out[m] = res.central[i].fv; });
        return out;
    }

    // ---------------------------------------------------------------- views

    const CHART_FROM = '2023-01';            // the projection gets a third of the width instead of a tenth

    function chart(d, res) {
        const P = d.path.filter((p) => p.month >= CHART_FROM);
        const idx = Object.fromEntries(d.engine.months.map((m, i) => [m, i]));
        const fvm = fvByMonth(d, res);
        const fv = P.map((p) => fvm[p.month] ?? null);
        const at = (arr) => P.map((p) => (idx[p.month] != null ? arr[idx[p.month]] : null));
        const p10 = at(res.sim.p10), p50 = at(res.sim.p50), p90 = at(res.sim.p90);
        const actual = P.map((p) => p.brent);
        const i0 = P.findIndex((p) => p.projected);
        const eia = P.map((p, i) => (i >= i0 - 1 ? p.brent_eia : null));
        const fut = P.map((p) => p.futures ?? null);
        const W = 600, H = 180, L = 34, R = 6, T = 8, B = 18;
        const vals = [...actual, ...fv, ...p10, ...p90, ...eia, ...fut].filter(Number.isFinite);
        const lo = Math.min(...vals) * 0.92, hi = Math.max(...vals) * 1.04;
        const x = (i) => L + (i / (P.length - 1)) * (W - L - R);
        const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
        const line = (arr, color, dash, w = 1.6) => {
            let s = '', pen = false;
            arr.forEach((v, i) => { if (!Number.isFinite(v)) { pen = false; return; } s += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
            return `<path d="${s}" fill="none" stroke="${color}" stroke-width="${w}" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
        };
        const band = (() => {
            const pts = P.map((_, i) => i).filter((i) => Number.isFinite(p10[i]));
            if (!pts.length) return '';
            const up = pts.map((i) => `${x(i).toFixed(1)},${y(p90[i]).toFixed(1)}`).join('L');
            const dn = pts.slice().reverse().map((i) => `${x(i).toFixed(1)},${y(p10[i]).toFixed(1)}`).join('L');
            return `<path d="M${up}L${dn}Z" fill="rgba(167,139,250,0.18)" stroke="none"/>`;
        })();
        const shade = i0 > 0 ? `<rect x="${x(i0).toFixed(1)}" y="${T}" width="${(W - R - x(i0)).toFixed(1)}" height="${H - T - B}" fill="rgba(148,163,184,0.06)"/>` : '';
        const ticks = [lo, (lo + hi) / 2, hi].map((v) => `<text x="${L - 4}" y="${(y(v) + 3).toFixed(1)}" font-size="9" fill="#64748b" text-anchor="end">${v.toFixed(0)}</text>`).join('');
        const yrs = P.map((p, i) => [p.month, i]).filter(([m]) => m.endsWith('-01'))
            .map(([m, i]) => `<text x="${x(i).toFixed(1)}" y="${H - 5}" font-size="9" fill="#64748b" text-anchor="middle">${m.slice(0, 4)}</text>`).join('');
        return `<svg class="ob-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="브렌트, 적정가, 전망 범위">
                ${shade}${band}${ticks}${yrs}
                ${line(fv, '#a78bfa', '', 1.3)}
                ${line(p50, '#c4b5fd', '5 3', 1.8)}
                ${line(actual, '#38bdf8')}
                ${line(eia, '#38bdf8', '4 3', 1.2)}
                ${line(fut, '#fbbf24', '2 3', 1.6)}
            </svg>
            <div class="ob-key"><span><i style="border-color:#38bdf8"></i>브렌트 실적</span><span><i style="border-color:#a78bfa"></i>적정가</span>
                <span><i style="border-color:#c4b5fd;border-top-style:dashed"></i>전망 중앙값</span><span><b></b>P10~P90</span>
                <span><i style="border-color:#38bdf8;border-top-style:dashed"></i>EIA 전망</span><span><i style="border-color:#fbbf24;border-top-style:dotted"></i>선물</span></div>`;
    }

    const TAG = { data: '데이터', judgment: '판단' };

    function inputRow(spec, id, value) {
        const s = spec[id];
        if (!s) return '';
        const ctl = s.options
            ? `<select data-ob-in="${id}">${Object.entries(s.options).map(([k, lab]) => `<option value="${esc(k)}" ${k === value ? 'selected' : ''}>${esc(lab)}</option>`).join('')}</select>`
            : `<input type="number" step="0.1" data-ob-in="${id}" value="${esc(value)}">`;
        return `<div class="ob-in"><span>${esc(s.label)}${s.unit ? ` <span class="stock-note">(${esc(s.unit)})</span>` : ''}<span class="ob-tag ${esc(s.kind)}">${TAG[s.kind] || ''}</span></span>${ctl}
            <span class="ob-src">${esc(s.source)}${s.as_of ? ` · ${esc(s.as_of)}` : ''}${s.spread ? ` · 범위 ±${esc(s.spread)}` : ''}</span></div>`;
    }

    function identityView(d, inp) {
        const I = d.identity;
        const surplus = (I.supply + inp.supply_delta) - (I.demand + inp.demand_delta);
        // eia: OECD from EIA's path, 'other' is whatever is left. value: every slot typed in, so the leftover is
        // a contradiction. identity: OECD is the leftover.
        const mode = inp.oecd_mode;
        const oecd = mode === 'eia' ? I.oecd_build_eia : mode === 'value' ? inp.oecd_build : surplus - inp.china_build - inp.other_build;
        const other = mode === 'eia' ? surplus - oecd - inp.china_build : inp.other_build;
        const left = surplus - oecd - inp.china_build - other;
        const outside = surplus - oecd;
        const annual = Object.entries(I.outside_oecd_annual || {});
        const top = annual.reduce((a, b) => (b[1] > a[1] ? b : a), ['', -Infinity]);
        const rows = [['공급', I.supply + inp.supply_delta], ['수요', I.demand + inp.demand_delta], ['과잉 (공급−수요)', surplus],
            [`→ OECD 재고${mode === 'eia' ? ' (EIA 경로)' : mode === 'identity' ? ' (나머지 자동)' : ''}`, oecd], ['→ 중국 재고', inp.china_build],
            [`→ 기타 (해상·비OECD)${mode === 'eia' ? ' (나머지 자동)' : ''}`, other], ['어디에도 배정 안 됨', left]];
        let warn = Math.abs(left) > 0.3
            ? `<div class="ob-warn">가정끼리 맞지 않습니다. 하루 ${num(Math.abs(left), 2)}백만 배럴이 ${left > 0 ? '남는데 쌓일 곳이 없습니다' : '모자라 어디선가 재고가 빠져야 합니다'}. OECD 재고 경로를 '항등식'으로 바꾸거나 공급·수요·중국·기타 값을 고치세요.</div>`
            : '<div class="ob-ok">공급·수요와 재고 배분이 맞습니다 (차이 ±0.3 이내).</div>';
        if (Math.abs(left) <= 0.3 && Number.isFinite(top[1]) && outside > top[1] + 0.3) {
            warn += `<div class="ob-warn">OECD 밖(중국+기타)에 하루 ${num(outside, 2)}백만 배럴이 쌓인다는 가정입니다. ${esc(annual[0][0])}년 이후 연간 최대(${esc(top[0])}년 ${num(top[1], 2)})보다 ${num(outside - top[1], 1)} 많습니다 — 그 초과분이 OECD 재고로 넘어오면 적정가가 내려갑니다.</div>`;
        }
        return `<p class="trade-rank-group-head" style="margin-top:10px;">항등식 검사 · ${esc(I.months[0])}~${esc(I.months[1])} 평균 (백만 배럴/일)</p>
            <table class="ob-tab"><tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${num(v, 2)}</td></tr>`).join('')}</tbody></table>${warn}
            <div class="stock-note" style="margin-top:4px;">EIA 경로는 과잉 ${num(I.surplus, 2)} 중 ${num(I.outside_oecd_eia, 2)}가 OECD 밖(중국·비OECD·해상)으로 간다고 봅니다.
                같은 계산(공급−수요−OECD 재고 변화)의 과거 연평균: ${annual.map(([y, v]) => `${esc(y.slice(2))}년 ${sgn(v, 1)}`).join(' · ')}; 최근 12개월 ${sgn(I.outside_oecd_last12.value, 2)}(전쟁으로 재고가 빠진 기간).
                중국 재고를 직접 재는 무료 자료(해관 수입 통계)는 자동 수집이 막혀 있어, 이 차액이 'OECD 밖 흡수'의 대리 지표입니다.</div>`;
    }

    function competeView(d) {
        const c = d.compete, m = d.model;
        const on = (r) => r.vars.join() === m.vars.join() && r.from === m.from;
        const lab = (vs) => vs.map((v) => ({ dev_mb: '재고(mb)', dev_days: '재고(일수)', spare: '여유능력', log_dxy: '달러' }[v] || v)).join('+');
        return `<details><summary>구조 경쟁 — 후보 ${c.rows.length}개, 표본 밖 오차 순</summary>
            <table class="ob-tab"><thead><tr><th>구조</th><th>시작</th><th>R²</th><th>표본 밖 오차</th><th>최대 괴리</th><th>$10↑ 지속</th></tr></thead><tbody>
            ${c.rows.map((r) => `<tr class="${on(r) ? 'ob-on' : ''}"><td>${esc(lab(r.vars))}</td><td>${esc(r.from.slice(0, 4))}</td><td>${num(r.r2, 2)}</td>
                <td>${usd(r.oos_mae, 1)}</td><td>+${num(r.max_premium, 0)}</td><td>${num(r.avg_months_above_10)}개월</td></tr>`).join('')}</tbody></table>
            <div class="stock-note" style="margin-top:4px;">표본 밖 오차 = 전년 말까지로 맞춘 식에 그해 실제 재고·여유능력·달러를 넣었을 때의 월평균 오차(${esc(c.common_years[0])}~${esc(c.common_years.at(-1))}). 가정이 다 맞아도 구조 자체가 이만큼 틀립니다.
                보라색 줄이 쓰는 구조입니다. 오차 순위는 1위가 아니지만, 공개된 진단(2005년 이후 최대 괴리 약 $24, 괴리 평균 3.8개월)을 재현하는 건 이 구조뿐입니다 — 2015년 이후로 맞춘 식들은 최대 괴리가 $60 넘게 나옵니다.</div></details>`;
    }

    function stabilityView(d) {
        const m = d.model;
        const FL = { stable: ['안정', 'ob-gap-dn'], weakening: ['약해짐', ''], flipped: ['부호 바뀜', 'ob-gap-up'] };
        return `<details><summary>계수 안정성 — 5년 창별 재추정</summary>
            <table class="ob-tab"><thead><tr><th>기간</th>${m.labels.map((l) => `<th>${esc(l)}</th>`).join('')}<th>R²</th></tr></thead><tbody>
            <tr class="ob-on"><td>${esc(m.from.slice(0, 4))}~${esc(m.to.slice(0, 4))} 전체</td>${m.beta.slice(1).map((b, i) => `<td>${b.toFixed(4)} <span class="stock-note">±${(m.se[i + 1]).toFixed(4)}</span></td>`).join('')}<td>${num(m.r2, 2)}</td></tr>
            ${m.windows.map((w) => `<tr><td>${esc(w.from.slice(0, 4))}~${esc(w.to.slice(0, 4))}</td>${m.vars.map((v) => `<td>${w.beta[v].toFixed(4)}</td>`).join('')}<td>${num(w.r2, 2)}</td></tr>`).join('')}
            <tr><td>판정</td>${m.vars.map((v) => { const f = FL[m.stability[v]] || ['—', '']; return `<td class="${f[1]}">${f[0]}</td>`; }).join('')}<td></td></tr></tbody></table>
            <div class="stock-note" style="margin-top:4px;">재고 계수는 어느 기간이든 같은 방향·비슷한 크기입니다. 부호가 바뀐 변수는 전망에서 믿지 말고 입력 범위를 넓게 두세요(달러 ±${esc(d.inputs.spreads.dxy_pct)}%). ± 는 뉴이-웨스트 표준오차(잔차 자기상관 반영).</div></details>`;
    }

    function scoreView(d) {
        const bt = d.backtest || [];
        const done = bt.filter((r) => r.months === 12);
        const mean = (k) => { const v = done.map((r) => r[k]).filter(Number.isFinite); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
        const live = d.live_scores || [];
        const scored = live.filter((r) => r.months > 0);
        const lastS = scored.at(-1);
        return `<details><summary>예측 채점 — 매년 12월 STEO로 다시 돌려 본 결과</summary>
            <table class="ob-tab"><thead><tr><th>대상 연도</th><th>실제</th><th>모형</th><th>EIA</th><th>무변화</th><th>구간 적중</th></tr></thead><tbody>
            ${bt.map((r) => `<tr><td>${esc(r.target)}${r.months < 12 ? ` <span class="stock-note">(${r.months}개월)</span>` : ''}</td><td>${usd(r.avg_actual)}</td>
                <td>${usd(r.mae_model, 1)}</td><td>${usd(r.mae_eia, 1)}</td><td>${usd(r.mae_rw, 1)}</td><td>${Math.round(r.coverage * 100)}%</td></tr>`).join('')}
            <tr class="ob-on"><td>${esc(done[0]?.target)}~${esc(done.at(-1)?.target)} 평균</td><td></td><td>${usd(mean('mae_model'), 1)}</td><td>${usd(mean('mae_eia'), 1)}</td><td>${usd(mean('mae_rw'), 1)}</td><td>${Math.round((mean('coverage') || 0) * 100)}%</td></tr></tbody></table>
            <div class="stock-note" style="margin-top:4px;">칸 = 월평균 절대오차(달러). 각 12월 STEO의 재고·여유능력 전망을 넣고 11월 프리미엄을 반감기대로 줄여 다음 해를 예측했습니다. 무변화 = 11월 가격 유지.
                1년 앞 가격은 모형·EIA·무변화가 비슷하게 틀립니다 — 이 모형의 쓸모는 점 하나 맞히기보다 '어떤 가정이면 얼마'를 분해하는 데 있습니다.
                구간 적중은 P10~P90이 실제를 덮은 달의 비율로, 80%면 정직한 구간입니다. 평균이 그보다 낮으면 화면의 범위도 실제보다 좁다고 읽으세요.</div>
            <div class="stock-note" style="margin-top:4px;">실시간 기록: STEO가 나올 때마다 그 시점 전망(P10/P50/P90, EIA, 선물)을 저장합니다. 지금 ${live.length}건 저장,
                ${lastS ? `${scored.length}건 채점 — 최근 모형 ${usd(lastS.mae_model, 1)} · 무변화 ${usd(lastS.mae_rw, 1)}${Number.isFinite(lastS.mae_eia) ? ` · EIA ${usd(lastS.mae_eia, 1)}` : ''}${Number.isFinite(lastS.mae_futures) ? ` · 선물 ${usd(lastS.mae_futures, 1)}` : ''}` : '첫 채점은 다음 달 브렌트가 확정된 뒤'}.</div></details>`;
    }

    function cardHtml(d) {
        const m = d.model, res = run(d), s = state, inp = s.inp, spec = d.inputs.spec;
        const jp = (d.bank_views || [])[0];
        const last = d.brent_last || {};
        const prem = Number.isFinite(last.value) && Number.isFinite(last.fair_value_month) ? (last.value / last.fair_value_month - 1) * 100 : null;
        const fvm = fvByMonth(d, res);
        const fvYear = (y) => { const v = Object.entries(fvm).filter(([mm]) => mm.startsWith(y)).map(([, x]) => x); return v.length === 12 ? v.reduce((a, b) => a + b, 0) / 12 : null; };
        const rows = d.annual.map((a) => {
            const f = res.sim.annual[a.year];
            return `<tr><td>${esc(a.year)}</td><td>${sgn(a.balance)}</td><td>${usd(fvYear(a.year))}</td>
                <td>${f ? `${usd(f.p10)}~<b>${usd(f.p50)}</b>~${usd(f.p90)}` : usd(a.brent)}</td>
                <td>${usd(a.brent_eia)}</td><td>${usd(a.futures)}${a.futures_months && a.futures_months < 12 ? ` <span class="stock-note">(${a.futures_months}개월)</span>` : ''}</td>
                <td>${jp && jp.brent_annual?.[a.year] ? usd(jp.brent_annual[a.year]) : '—'}</td></tr>`;
        }).join('');
        const scen = d.scenarios.list;
        const probSum = scen.reduce((a, x) => a + (Number(s.probs[x.id]) || 0), 0);
        return `<p class="section-title">브렌트: 추정 · 가정 · 예측 <span class="stock-note">EIA STEO ${esc(d.steo.vintage || '')} · 무료 자료만</span></p>
            <div class="ob-line"><span>브렌트 ${esc(last.date || '')}</span><span>${usd(last.value, 1)} · 적정가 ${usd(last.fair_value_month, 1)}
                ${Number.isFinite(prem) ? `<b class="${prem > 0 ? 'ob-gap-up' : 'ob-gap-dn'}">${sgn(prem, 0)}%</b>` : ''}</span></div>
            <div class="ob-line"><span>프리미엄 반감기 (잔차 AR(1))</span><span>${num(m.half_life)}개월 · 한 달 뒤 ${Math.round(m.rho * 100)}% 남음 · 월 ±${num(m.resid_sd * 100)}%</span></div>
            ${chart(d, res)}
            <p class="trade-rank-group-head" style="margin-top:8px;">연간 (과잉 = EIA 공급−수요, 백만 배럴/일 · 가격 달러/배럴)</p>
            <table class="ob-tab"><thead><tr><th>연도</th><th>과잉</th><th>적정가</th><th>실적 · 전망<br>P10~P50~P90</th><th>EIA</th><th>선물</th><th>JP모건</th></tr></thead><tbody>${rows}</tbody></table>
            <div class="stock-note">적정가 = 프리미엄 0일 때 값. 전망 연도의 적정가와 P10~P90은 아래 입력으로 다시 계산됩니다.</div>

            <p class="trade-rank-group-head" style="margin-top:12px;">가정 입력 <span class="stock-note">값을 바꾸면 바로 다시 계산 · <span class="ob-tag data">데이터</span><span class="ob-tag judgment">판단</span></span></p>
            <div class="ob-btns"><button type="button" data-ob-preset="default">기본값 (EIA 경로)</button><button type="button" data-ob-preset="jpm">JP모건 가정 (OECD 0.4·중국 0.7)</button><button type="button" data-ob-preset="identity">항등식으로 OECD 계산</button></div>
            ${['oecd_mode', 'oecd_build', 'supply_delta', 'demand_delta', 'china_build', 'other_build', 'spare_mode', 'spare', 'dxy_pct', 'half_life'].map((k) => inputRow(spec, k, inp[k])).join('')}
            <p class="trade-rank-group-head" style="margin-top:10px;">시나리오 확률 (%) <span class="ob-tag judgment">판단</span> <span class="stock-note">합 ${num(probSum, 0)} — 100이 아니면 비율로 나눔</span></p>
            ${scen.map((x) => `<div class="ob-in"><span>${esc(x.label)}<span class="stock-note"> ${x.months ? `${esc(d.engine.months[x.start] || '')}부터 ${x.months}개월 · OECD ${sgn(x.oecd_add, 2)} · 여유능력 ${sgn(x.spare_add, 1)} · 프리미엄 ${sgn(x.premium_pct, 0)}%` : '추가 충격 없음'}</span></span>
                <input type="number" step="5" min="0" data-ob-prob="${esc(x.id)}" value="${esc(s.probs[x.id])}"></div>`).join('')}
            <div class="stock-note">${esc(d.scenarios.note)}</div>
            ${identityView(d, inp)}

            ${competeView(d)}
            ${stabilityView(d)}
            ${scoreView(d)}
            <details><summary>운영 주기 — 가정은 바뀌고 구조는 점검만</summary>
                ${(d.cadence || []).map((c) => `<div class="ob-line"><span>${esc(c.when)}</span><span style="text-align:right;">${esc(c.what)}</span></div>`).join('')}</details>
            ${jp ? `<details><summary>${esc(jp.name)} 전망 메모 · ${esc(jp.read_from)}</summary>
                ${(jp.notes_ko || []).map((t) => `<div class="stock-note" style="margin:4px 0;">· ${esc(t)}</div>`).join('')}</details>` : ''}
            <div class="stock-note" style="margin-top:8px;">식: log(브렌트) = ${num(m.beta[0], 2)} ${m.beta.slice(1).map((b, i) => `${b < 0 ? '−' : '+'} ${Math.abs(b).toFixed(4)}×${esc(m.labels[i])}`).join(' ')}
                (${esc(m.from)}~${esc(m.to)} 월별, R² ${num(m.r2, 2)}; 최대 괴리 +$${num(m.max_premium)} ${esc(m.max_premium_month)}, $10 넘는 괴리 평균 ${num(m.avg_months_above_10)}개월).
                전망 = 입력 경로의 적정가 + 지금 프리미엄 × ${num(m.rho, 2)}^개월. 범위 = 계수 오차 + 잔차 + 입력 범위 + 시나리오, 1,500회 모의.
                출처: <a href="${esc(d.steo.url)}" target="_blank" rel="noopener" style="color:#7dd3fc;">EIA 단기에너지전망</a> · FRED DCOILBRENTEU·DTWEXBGS · Yahoo 브렌트 선물(BZ)</div>`;
    }

    // The JP Morgan preset takes the bank's 2027 supply and surplus (bank_views) as deltas to EIA's year, so the
    // identity check balances on its own numbers: demand = supply - surplus.
    function jpmInputs(d) {
        const jp = (d.bank_views || [])[0] || {};
        const a = d.annual.find((x) => x.year === '2027') || {};
        const sup = jp.supply_mbd?.['2027'], bal = jp.balance_mbd?.['2027'];
        const ok = Number.isFinite(sup) && Number.isFinite(bal) && Number.isFinite(a.supply) && Number.isFinite(a.demand);
        return { ...d.inputs.resolved, oecd_mode: 'value', oecd_build: 0.4, china_build: 0.7, other_build: 0.5,
            supply_delta: ok ? +(sup - a.supply).toFixed(2) : 0, demand_delta: ok ? +((sup - bal) - a.demand).toFixed(2) : 0 };
    }

    const PRESETS = {
        default: (d) => { state.probs = Object.fromEntries(d.scenarios.list.map((s) => [s.id, s.prob])); return { ...d.inputs.resolved, oecd_mode: 'eia' }; },
        jpm: jpmInputs,
        identity: () => ({ ...state.inp, oecd_mode: 'identity' }),
    };

    async function render() {
        const token = ++generation;
        const host = document.getElementById('news-content');
        host?.querySelector('[data-oilbal]')?.remove();
        if (typeof currentCommodity === 'undefined' || !VIEWS.includes(currentCommodity)) return;
        const doc = await load();
        if (token !== generation || currentCommodity !== 'oil' || !doc?.engine?.months?.length) return;
        const card = host?.querySelector('.trade-focus-card');
        if (!card) return;
        const slot = document.createElement('div');
        slot.dataset.oilbal = '1';
        slot.className = 'stock-card';
        slot.style.marginBottom = '10px';
        const paint = () => {
            const was = [...slot.querySelectorAll('details')].map((x) => x.open);
            slot.innerHTML = cardHtml(doc);
            slot.querySelectorAll('details').forEach((x, i) => { if (was[i]) x.open = true; });
        };
        paint();
        slot.addEventListener('change', (e) => {
            const t = e.target;
            if (t.dataset.obIn) {
                const k = t.dataset.obIn;
                if (t.tagName === 'SELECT') state.inp[k] = t.value;
                else {
                    const v = Number(t.value);
                    state.inp[k] = Number.isFinite(v) && t.value !== '' ? v : doc.inputs.resolved[k];
                    if (k === 'half_life') state.inp[k] = Math.max(0.5, state.inp[k]);
                }
            } else if (t.dataset.obProb) {
                state.probs[t.dataset.obProb] = Math.max(0, Number(t.value) || 0);
            } else return;
            paint();
        });
        slot.addEventListener('click', (e) => {
            const b = e.target.closest('[data-ob-preset]');
            if (!b) return;
            state.inp = PRESETS[b.dataset.obPreset](doc);
            paint();
        });
        const futures = card.querySelector('#futures-slot');
        if (futures) futures.after(slot); else card.prepend(slot);
    }

    window.OilBalance = { render, VIEWS, project, simulate };
})();
