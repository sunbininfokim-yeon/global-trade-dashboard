// Company valuation calculator for Global Trade Dashboard -- DART filing
// cards, DCF and reverse-DCF panels, sensitivity, and the level-by-level
// breakdown.
//
// Split out of app.js (2026-08-20). app.js is shared by parallel sessions and
// a squash merge replaces whole regions instead of diffing them.
//
// Loaded AFTER macro.js -- coDcfPanel and coReversePanel format with mmFmt.
// Relies on globals still in app.js: finEsc, finFmt, FIN_SERIES_MODE, and the
// DOM helpers. Shows no price target by design.

// A KRX listing arrives either bare (from the filer index) or suffixed (from
// Yahoo); both name the same company, so dedupe has to compare them stripped.
const coSymKey = (sym) => String(sym || '').toUpperCase().replace(/\.(KS|KQ)$/, '');

// --- 기업 가치 계산기 ---------------------------------------------------------
// The same statements read at three depths. Named for what each view is for,
// not for who is supposed to be reading it -- a label like "취준생용" tells the
// reader what the site thinks of them rather than what the numbers show.
const CO_LEVELS = [
    { id: 'health',    label: '재무 건전성', blurb: '빚을 감당할 수 있는가, 이익은 나는가' },
    { id: 'valuation', label: '투자 판단',   blurb: '벌어들이는 현금 대비 값이 어떤가' },
    { id: 'deep',      label: '심층 분석',   blurb: '자산과 부채가 실제로 어떤 모양인가' },
];

// Levels stack rather than replace. Moving up a level is a request for more,
// not for something else -- valuation still wants the health numbers in view.
const CO_LEVEL_ORDER = CO_LEVELS.map((l) => l.id);
const coLevelsUpTo = (id) => CO_LEVEL_ORDER.slice(0, CO_LEVEL_ORDER.indexOf(id) + 1);

const coNum = (v, currency = 'KRW') => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const a = Math.abs(v);
    if (currency === 'KRW') {
        if (a >= 1e12) return `${(v / 1e12).toFixed(2)}조원`;
        if (a >= 1e8) return `${(v / 1e8).toFixed(1)}억원`;
        if (a >= 1e4) return `${(v / 1e4).toFixed(0)}만원`;
        return `${Math.round(v).toLocaleString('ko-KR')}원`;
    }
    const sym = currency === 'USD' ? '$' : `${currency} `;
    if (a >= 1e9) return `${sym}${(v / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `${sym}${(v / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `${sym}${(v / 1e3).toFixed(1)}K`;
    return `${sym}${Math.round(v).toLocaleString('en-US')}`;
};

const coRatio = (v, digits = 1) =>
    (v === null || v === undefined || !Number.isFinite(v)) ? '—' : `${v.toFixed(digits)}`;

const coPct = (v, digits = 1) =>
    (v === null || v === undefined || !Number.isFinite(v)) ? '—' : `${(v * 100).toFixed(digits)}%`;

const coDiv = (a, b) => (a === null || b === null || !b) ? null : a / b;

// Ratios follow the same definitions the KFA engine uses, so the two can be
// checked against each other the way the portfolio maths already is.
const coDerive = (s) => {
    const sum = (...xs) => {
        const vals = xs.filter((x) => Number.isFinite(x));
        return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
    };
    const interestBearingShort = sum(s.debt_short, s.debt_current_portion);
    const debtTotal = sum(interestBearingShort, s.debt_long);
    return {
        fy: s.fy,
        // Annual rows are keyed by fiscal year, quarterly ones by `2025Q3`.
        // Carrying both lets one derived row feed either series without the
        // chart having to know which kind of filing produced it.
        period: s.period ?? (s.fy === undefined ? undefined : String(s.fy)),
        current_ratio: coDiv(s.assets_current, s.liabilities_current),
        quick_ratio: coDiv(sum(s.cash, s.securities_current, s.receivables), s.liabilities_current),
        debt_ratio: coDiv(s.liabilities, s.assets),
        equity_ratio: coDiv(s.equity, s.assets),
        roe: coDiv(s.net_income, s.equity),
        roa: coDiv(s.net_income, s.assets),
        operating_margin: coDiv(s.operating_income, s.revenue),
        net_margin: coDiv(s.net_income, s.revenue),
        fcf: (s.cfo === null || s.capex === null) ? null : s.cfo - s.capex,
        fcf_margin: (s.cfo === null || s.capex === null) ? null : coDiv(s.cfo - s.capex, s.revenue),
        // Net debt counts what carries interest, not every payable.
        interest_bearing_short: interestBearingShort,
        debt_total: debtTotal,
        net_debt: (debtTotal === null) ? null : debtTotal - (s.cash ?? 0) - (s.securities_current ?? 0),
        // How much of the interest-bearing debt falls due inside a year.
        short_share: coDiv(interestBearingShort, debtTotal),
        interest_cover: coDiv(s.operating_income, s.interest_expense),
        effective_tax: coDiv(s.tax_expense, sum(s.net_income, s.tax_expense)),
        raw: s,
    };
};

// --- 한국 상장사 (DART/KFA) ---------------------------------------------------
// scripts/dart owns the extraction (OpenDART -> normalized cards); this side
// only fetches the static per-company snapshot it produces and renders
// whichever view the payload's own view_presets describe. No card copy comes
// from the engine, so the Korean label/plain-text for each metric key lives
// here, same as CO_LEVELS does for the SEC calculator.
const KFA_VIEW_LABELS = { basic: '기본', investor: '투자자', pe: 'PE', deal: '딜' };

const KFA_CARD_META = {
    revenue: { label: '매출', unit: 'money', plain: '한 해 동안 벌어들인 전체 매출입니다.' },
    operating_income: { label: '영업이익', unit: 'money', plain: '매출에서 원가·판관비를 뺀, 본업으로 남긴 돈입니다.' },
    net_income: { label: '순이익', unit: 'money', plain: '세금·이자 등을 모두 뺀 최종 이익입니다.' },
    cfo: { label: '영업활동현금흐름', unit: 'money', plain: '실제로 영업에서 걷어들인 현금입니다. 회계상 이익과 다를 수 있습니다.' },
    fcf: { label: '잉여현금흐름(FCF)', unit: 'money', plain: '영업현금흐름에서 설비투자를 뺀, 자유롭게 쓸 수 있는 현금입니다.' },
    cash: { label: '현금성자산', unit: 'money', plain: '즉시 쓸 수 있는 현금·예금입니다.' },
    net_debt: { label: '순부채', unit: 'money', plain: '이자부 부채에서 현금·단기금융상품을 뺀 값입니다. 음수면 순현금 상태입니다.' },
    current_ratio: { label: '유동비율', unit: 'ratio', plain: '1년 내 갚을 부채 대비 1년 내 현금화할 자산의 비율입니다.' },
    debt_due_within_1y: { label: '1년 내 만기부채', unit: 'money', plain: '앞으로 1년 안에 갚아야 하는 차입금입니다.' },
    liquidity_coverage_1y: { label: '유동성 커버리지', unit: 'ratio', plain: '1년 내 만기부채를 현금성자산으로 얼마나 덮을 수 있는지입니다.' },
    interest_coverage: { label: '이자보상배율', unit: 'ratio', plain: '영업이익이 이자비용의 몇 배인지입니다. 낮을수록 이자 부담이 큽니다.' },
    ccc_days: { label: '현금전환주기(CCC)', unit: 'days', plain: '재고·매출을 현금으로 바꾸는 데 걸리는 평균 일수입니다.' },
    eps: { label: '주당순이익(EPS)', unit: 'money', plain: '보통주 1주가 벌어들인 순이익입니다(기본 EPS).' },
    market_cap: { label: '시가총액', unit: 'money', plain: '현재가 × 발행주식수. 회사 전체를 지금 가격으로 산다면 드는 돈입니다.' },
    pe_ratio: { label: 'PER(주가수익비율)', unit: 'ratio', plain: '현재가를 EPS로 나눈 값입니다. 낮을수록 이익 대비 주가가 싼 편입니다.' },
    pb_ratio: { label: 'PBR(주가순자산비율)', unit: 'ratio', plain: '현재가를 주당순자산(BPS)으로 나눈 값입니다. 1보다 낮으면 장부가보다 싸게 거래 중입니다.' },
    owner_earnings: { label: '오너어닝스', unit: 'money', plain: '버핏식으로 어림한 실질 이익입니다.' },
    earnings_quality: { label: '이익의 질', unit: 'ratio', plain: '회계상 이익이 실제 현금흐름으로 얼마나 뒷받침되는지입니다.' },
    margins_trend: { label: '마진 추이', unit: 'text', plain: '최근 몇 년간 이익률이 개선·악화되는 방향입니다.' },
    capex_to_da: { label: '설비투자/감가상각', unit: 'ratio', plain: '설비투자가 감가상각을 웃도는지, 자산이 늘고 있는지 봅니다.' },
    net_debt_to_oe: { label: '순부채/오너어닝스', unit: 'ratio', plain: '오너어닝스 기준으로 부채를 갚는 데 몇 년 걸리는지입니다.' },
    ebitda_or_op: { label: 'EBITDA(또는 영업이익)', unit: 'money', plain: '감가상각 반영 전 영업 현금창출력입니다.' },
    net_debt_to_ebitda: { label: '순부채/EBITDA', unit: 'ratio', plain: 'PE 딜에서 흔히 쓰는 레버리지 배수입니다.' },
    fcf_to_ebitda: { label: 'FCF/EBITDA', unit: 'ratio', plain: '벌어들인 현금창출력 중 실제 자유현금흐름으로 남는 비율입니다.' },
    maint_capex_burden: { label: '유지보수 설비투자 부담', unit: 'ratio', plain: '현상 유지에 필요한 설비투자가 얼마나 무거운지입니다.' },
    nwc_change_to_sales: { label: '운전자본 변동/매출', unit: 'ratio', plain: '매출 대비 운전자본이 얼마나 늘거나 줄었는지입니다.' },
    ebitda: { label: 'EBITDA', unit: 'money', plain: '이자·세금·감가상각 전 이익입니다.' },
    trading_multiples: { label: '거래 배수', unit: 'text', plain: 'EV/EBITDA 등 비교기업 대비 밸류에이션 배수입니다.' },
    ev_bridge: { label: 'EV 브릿지', unit: 'text', plain: '시가총액에서 기업가치(EV)까지의 조정 항목입니다.' },
    qoe_flags: { label: '이익품질 플래그', unit: 'text', plain: '일회성 항목 등 이익의 질을 흔드는 신호입니다.' },
    segment: { label: '세그먼트', unit: 'text', plain: '사업부문별 실적 분해입니다.' },
    nwc_to_sales: { label: '운전자본/매출', unit: 'ratio', plain: '매출 대비 운전자본이 차지하는 비중입니다.' },
};

const kfaFmt = (key, v, currency) => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const unit = (KFA_CARD_META[key] || {}).unit;
    if (unit === 'money') return coNum(v, currency || 'KRW');
    if (unit === 'days') return `${Math.round(v)}일`;
    if (unit === 'ratio') return `${v.toFixed(2)}배`;
    return String(v);
};

const renderKfaResult = (out, data) => {
    const views = (data.view_presets && data.view_presets.views) || {};
    const viewIds = Object.keys(views);
    if (!viewIds.includes(KFA_VIEW)) KFA_VIEW = data.view_presets?.default_view || viewIds[0] || 'basic';
    const cardKeys = (views[KFA_VIEW] && views[KFA_VIEW].cards) || [];
    const models = (views[KFA_VIEW] && views[KFA_VIEW].models) || [];
    const cards = data.basic_cards || {};
    const currency = data.currency || 'KRW';

    out.innerHTML = `
        <div class="fin-head fin-head-sub">
            <p class="fin-headline">${finEsc(data.meta?.entity || data.label)}
               <span class="fin-chip">${finEsc(data.meta?.ticker || data.label)}</span></p>
            <div class="fin-meta">
                <span>DART 공시 (${finEsc(data.meta?.fs_div || '')}) 기준 ${finEsc(data.as_of || '')}</span>
                ${data.reasons?.length ? `<span class="fin-meta-sep">·</span><span>${finEsc(data.reasons.join(' · '))}</span>` : ''}
            </div>
        </div>

        <div class="pf-mode" role="tablist" aria-label="분석 단계">
            ${viewIds.map((v) => `<button type="button" class="pf-mode-btn ${v === KFA_VIEW ? 'on' : ''}"
                data-kfa-view="${finEsc(v)}">${finEsc(KFA_VIEW_LABELS[v] || v)}</button>`).join('')}
        </div>

        <div class="fin-cards co-kfa-cards">
            ${cardKeys.map((key) => {
                const meta = KFA_CARD_META[key] || { label: key, unit: 'text', plain: '' };
                const card = cards[key];
                if (!card) return `
                    <div class="fin-card co-kfa-card co-kfa-pending">
                        <span class="fin-card-title">${finEsc(meta.label)}</span>
                        <span class="fin-card-value">준비 중</span>
                        <p class="fin-card-plain">엔진이 아직 이 항목을 계산하지 않았습니다.</p>
                    </div>`;
                const open = KFA_OPEN_CARD === key;
                const hasSeries = (card.series || []).length >= 2 || (card.quarterly || []).length >= 2;
                return `
                    <div class="fin-card co-kfa-card ${open ? 'open' : ''} ${hasSeries ? 'co-clickable' : ''}"
                        data-kfa-card="${finEsc(key)}">
                        <span class="fin-card-title">${finEsc(meta.label)}</span>
                        <span class="fin-card-value">${kfaFmt(key, card.value, currency)}</span>
                        <p class="fin-card-plain">${finEsc(meta.plain)}${card.reason ? ` (${finEsc(card.reason)})` : ''}</p>
                        ${hasSeries && open ? `<div class="co-kfa-chart">${finSeriesBlock(card.series, card.quarterly,
                            (v) => kfaFmt(key, v, currency))}</div>` : ''}
                    </div>`;
            }).join('')}
        </div>

        ${models.length ? `
        <div class="fin-note">이 단계는 다음 모델도 다룹니다: ${models.map(finEsc).join(', ')} —
            계산 로직은 아직 엔진에 없어 카드 값만 우선 표시합니다.</div>` : ''}

        <div class="fin-foot">
            <p class="fin-disclaimer">투자 판단의 책임은 본인에게 있습니다. 목표주가·매수매도 의견을 포함하지 않습니다.</p>
            <p class="fin-engine">엔진: <code>scripts/dart</code> (OpenDART) · 스키마 ${finEsc(data.schema || '')}</p>
        </div>`;

    out.querySelectorAll('[data-kfa-view]').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.kfaView === KFA_VIEW) return;
        KFA_VIEW = b.dataset.kfaView;
        KFA_OPEN_CARD = null;
        renderKfaResult(out, data);
    }));

    // The whole card opens its chart on click -- no separate "추이 보기"
    // button, so one press is one action. The mode toggle buttons live
    // inside the open card, so their clicks are excluded here or every
    // 연도별/분기별 press would also re-close the card it lives in.
    out.querySelectorAll('.co-kfa-card.co-clickable').forEach((el) => el.addEventListener('click', (e) => {
        if (e.target.closest('[data-fin-mode]')) return;
        const key = el.dataset.kfaCard;
        KFA_OPEN_CARD = (KFA_OPEN_CARD === key) ? null : key;
        renderKfaResult(out, data);
    }));

    out.querySelectorAll('[data-fin-mode]').forEach((b) => b.addEventListener('click', (e) => {
        e.stopPropagation();
        FIN_SERIES_MODE = b.dataset.finMode;
        renderKfaResult(out, data);
    }));
};

const loadKfaCompany = async (out, inst, code) => {
    out.innerHTML = `<div class="fin-block fin-block-wide"><p class="fin-loading">DART 공시 자료를 받는 중…</p></div>`;

    let data = null;
    for (const path of [`/public/data/kfa_${code}_v1.json`, `/data/kfa_${code}_v1.json`]) {
        try {
            const res = await fetch(path, { cache: 'no-store' });
            if (res.ok) { data = await res.json(); break; }
        } catch (_) { /* try next */ }
    }

    // No pre-generated snapshot for this ticker (only a handful exist under
    // public/data/) -- fall back to a live OpenDART lookup, which covers
    // every KRX-listed filer but only the 12 Basic-view cards (see
    // handleDartFinancials in _worker.js for why Investor/PE/Deal stay
    // "준비 중" here instead of getting a parallel calculation port).
    let liveOnly = false;
    if (!data) {
        try {
            const res = await fetch(`/api/dart-financials?symbol=${encodeURIComponent(code)}`, { cache: 'no-store' });
            if (res.ok) { data = await res.json(); liveOnly = true; }
        } catch (_) { /* fall through to empty state */ }
    }

    if (!data) {
        out.innerHTML = `
            <div class="fin-empty">
                <p class="fin-empty-title">${finEsc(inst.name_ko)}는 아직 DART 데이터가 없습니다</p>
                <p>OpenDART에 이 종목의 연결재무제표 공시가 없거나(최근 2개 회계연도 기준), 상장 종목이 아닙니다.</p>
            </div>`;
        return;
    }

    if (liveOnly) {
        data.reasons = [...(data.reasons || []), '실시간 조회: 기본 12개 지표만 제공 (투자자/PE/딜 카드는 준비 중)'];
    }

    KFA_VIEW = data.view_presets?.default_view || 'basic';
    KFA_OPEN_CARD = null;
    renderKfaResult(out, data);
};

const coTable = (rows, cols) => `
    <div class="co-table-wrap">
        <table class="co-table">
            <thead><tr><th>항목</th>${rows.map((r) => `<th>${r.fy}</th>`).join('')}</tr></thead>
            <tbody>
                ${cols.map((c) => `
                    <tr>
                        <td class="co-label">${finEsc(c.label)}${c.hint ? `<span class="co-hint">${finEsc(c.hint)}</span>` : ''}</td>
                        ${rows.map((r) => `<td>${c.fmt(r)}</td>`).join('')}
                    </tr>`).join('')}
            </tbody>
        </table>
    </div>`;

// --- DCF ---------------------------------------------------------------------
// Every number here is a consequence of three inputs the reader chooses. That is
// not a flaw to hide behind a single "fair value" figure -- it is the whole
// point, so the assumptions stay on screen and adjustable.
const CO_DCF = { growth: null, terminal: 2.5, discount: 9.0, years: 5 };
const CO_PRICE = { value: null, status: 'idle' };
let CO_DATA = null;   // 현재 렌더 중인 기업 페이로드 (통화 등)

const coDcf = (rows) => {
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;

    const g = (CO_DCF.growth ?? 0) / 100;
    const tg = CO_DCF.terminal / 100;
    const r = CO_DCF.discount / 100;
    if (!(r > tg)) return { invalid: '할인율이 영구성장률보다 커야 합니다.' };

    const flows = [];
    let f = base;
    for (let i = 1; i <= CO_DCF.years; i++) {
        f = f * (1 + g);
        flows.push({ year: i, fcf: f, pv: f / Math.pow(1 + r, i) });
    }
    const tail = flows[flows.length - 1].fcf * (1 + tg) / (r - tg);
    const tailPv = tail / Math.pow(1 + r, CO_DCF.years);
    const ev = flows.reduce((a, x) => a + x.pv, 0) + tailPv;
    const equity = ev - (latest.net_debt ?? 0);
    const shares = latest.raw.shares;
    return {
        base, flows, tail, tailPv, ev, equity,
        tailShare: tailPv / ev,
        perShare: Number.isFinite(shares) && shares > 0 ? equity / shares : null,
        shares,
    };
};

// Historical FCF growth, as a starting point for the input rather than a
// forecast. Clamped because a single recovery year can imply 300% forever.
const coDefaultGrowth = (rows) => {
    const fcfs = rows.map((r) => r.fcf).filter((x) => Number.isFinite(x) && x > 0);
    if (fcfs.length < 3) return 5;
    const newest = fcfs[0], oldest = fcfs[fcfs.length - 1], n = fcfs.length - 1;
    const cagr = (Math.pow(newest / oldest, 1 / n) - 1) * 100;
    return Math.max(-10, Math.min(20, Math.round(cagr * 10) / 10));
};

// Forward DCF answers "what is it worth if I am right about growth". Reverse
// DCF asks the better question: at today's price, what growth is already being
// assumed? That turns a number the reader must trust into one they can judge.
const coImpliedGrowth = (rows, marketCap) => {
    if (!Number.isFinite(marketCap) || marketCap <= 0) return null;
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;
    const targetEv = marketCap + (latest.net_debt ?? 0);

    const evAt = (g) => {
        const tg = CO_DCF.terminal / 100, r = CO_DCF.discount / 100;
        if (!(r > tg)) return null;
        let f = base, pv = 0;
        for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + g); pv += f / Math.pow(1 + r, i); }
        return pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
    };
    if (evAt(0) === null) return null;

    // EV rises monotonically in g below the discount rate, so bisection is both
    // sufficient and stable here.
    let lo = -0.5, hi = (CO_DCF.discount / 100) - 0.001;
    if (evAt(hi) < targetEv) return { unreachable: true, cap: hi * 100 };
    if (evAt(lo) > targetEv) return { unreachable: true, below: true, cap: lo * 100 };
    for (let k = 0; k < 60; k++) {
        const mid = (lo + hi) / 2;
        if (evAt(mid) < targetEv) lo = mid; else hi = mid;
    }
    return { growth: (lo + hi) / 2 * 100 };
};

const coSensitivity = (rows) => {
    const latest = rows[0];
    const base = latest.fcf;
    if (!Number.isFinite(base) || base <= 0) return null;
    const shares = latest.raw.shares;
    if (!Number.isFinite(shares) || shares <= 0) return null;

    const gs = [-5, 0, 5, 10, 15];
    const rs = [7, 8, 9, 10, 12];
    const tg = CO_DCF.terminal / 100;
    const cells = rs.map((rp) => ({
        r: rp,
        row: gs.map((gp) => {
            const g = gp / 100, r = rp / 100;
            if (!(r > tg)) return null;
            let f = base, pv = 0;
            for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + g); pv += f / Math.pow(1 + r, i); }
            const ev = pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
            return (ev - (latest.net_debt ?? 0)) / shares;
        }),
    }));
    return { gs, cells };
};

const coSensPanel = (rows, CUR) => {
    const sens = coSensitivity(rows);
    if (!sens) return '';
    const flat = sens.cells.flatMap((c) => c.row).filter(Number.isFinite);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    const tone = (v) => {
        if (!Number.isFinite(v) || hi === lo) return '';
        const t = (v - lo) / (hi - lo);
        return `background: rgba(56,189,248,${(0.05 + t * 0.24).toFixed(3)})`;
    };
    return `
    <h3 class="fin-sub">민감도 — 주당 가치</h3>
    <p class="fin-note">가로: 성장률 · 세로: 할인율 · 영구성장률 ${CO_DCF.terminal}% 고정.
       한 칸만 옮겨도 값이 크게 달라진다면, 그건 이 방법의 성질이지 계산 오류가 아닙니다.</p>
    <div class="co-table-wrap">
        <table class="co-table co-sens">
            <thead><tr><th>할인율 \\ 성장률</th>${sens.gs.map((g) => `<th>${g}%</th>`).join('')}</tr></thead>
            <tbody>
                ${sens.cells.map((c) => `
                    <tr><td class="co-label">${c.r}%</td>
                        ${c.row.map((v) => `<td style="${tone(v)}">${Number.isFinite(v) ? coNum(v, CUR) : '—'}</td>`).join('')}
                    </tr>`).join('')}
            </tbody>
        </table>
    </div>`;
};

const coReversePanel = (rows, CUR, data) => {
    const price = CO_PRICE.value;
    const shares = rows[0].raw.shares;
    const mcap = (Number.isFinite(price) && Number.isFinite(shares)) ? price * shares : null;
    const imp = mcap ? coImpliedGrowth(rows, mcap) : null;

    return `
    <h3 class="fin-sub">역방향 DCF — 시장은 몇 %를 가정하고 있나</h3>
    <p class="fin-note">
        위가 "이 가정이면 얼마인가" 라면, 이건 "지금 값이 맞으려면 무엇을 믿어야 하나" 입니다.
        ${CO_PRICE.status === 'loading' ? '현재가 조회 중…'
          : CO_PRICE.status === 'fail' ? `현재가를 못 받았습니다 — 직접 넣어 보세요.` : ''}
    </p>
    <div class="co-dcf-inputs">
        <label class="co-dcf-input">
            <span>현재 주가 (${finEsc(data.currency || '')})</span>
            <input type="number" data-co-price="1" value="${Number.isFinite(price) ? price : ''}" step="0.01" min="0">
        </label>
    </div>
    ${!Number.isFinite(price) ? `<p class="fin-note">주가를 넣으면 역산합니다.</p>`
      : !Number.isFinite(shares) ? `<p class="fin-note">희석주식수를 못 읽어 시가총액을 낼 수 없습니다.</p>`
      : !imp ? `<p class="fin-note">잉여현금흐름이 없거나 음수라 역산할 수 없습니다.</p>`
      : imp.unreachable ? `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">시가총액</span>
                <span class="fin-card-value">${coNum(mcap, data.currency)}</span>
                <p class="fin-card-plain">주가 × 희석주식수 ${mmFmt(shares, 0)}</p></div>
            <div class="fin-card"><span class="fin-card-title">FCF 배수</span>
                <span class="fin-card-value">${(mcap / rows[0].fcf).toFixed(0)}배</span>
                <p class="fin-card-plain">시가총액 ÷ 최근 잉여현금흐름입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">필요 영구성장률</span>
                <span class="fin-card-value">${(() => {
                    // 성장률로는 못 닿으니, 영구성장률을 역산해 격차의 크기를 보인다.
                    const r = CO_DCF.discount / 100, base = rows[0].fcf;
                    const target = mcap + (rows[0].net_debt ?? 0);
                    let lo = 0, hi = r - 0.0005;
                    const ev = (tg) => {
                        let f = base, pv = 0;
                        for (let i = 1; i <= CO_DCF.years; i++) { f *= (1 + tg); pv += f / Math.pow(1 + r, i); }
                        return pv + (f * (1 + tg) / (r - tg)) / Math.pow(1 + r, CO_DCF.years);
                    };
                    if (ev(hi) < target) return '해당 없음';
                    for (let k = 0; k < 60; k++) { const m = (lo + hi) / 2; if (ev(m) < target) lo = m; else hi = m; }
                    return `${((lo + hi) / 2 * 100).toFixed(1)}%`;
                })()}</span>
                <p class="fin-card-plain">할인율 ${CO_DCF.discount}% 를 유지할 때, 지금 값이 설명되려면 현금흐름이 영구히 이만큼 자라야 합니다.</p></div>
        </div>
        <p class="fin-note">
            ${imp.below ? '이 주가를 설명할 만큼 낮은 성장률이 없습니다.'
            : `성장률만으로는 닿지 않습니다 — 할인율(${CO_DCF.discount}%) 근처까지 올려도 지금 시가총액에 못 미칩니다.
               <strong>모델이 틀렸다기보다 가정이 시장과 다르다</strong>는 뜻입니다.
               장기 성장을 더 믿거나, 할인율을 더 낮게 보거나, 현금흐름 외의 것에 값이 매겨져 있거나입니다.`}
        </p>`
      : `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">시가총액</span>
                <span class="fin-card-value">${coNum(mcap, data.currency)}</span>
                <p class="fin-card-plain">주가 × 희석주식수 ${mmFmt(shares, 0)}</p></div>
            <div class="fin-card"><span class="fin-card-title">시장 내재 성장률</span>
                <span class="fin-card-value">${imp.growth.toFixed(1)}%</span>
                <p class="fin-card-plain">향후 5년 FCF가 매년 이만큼 늘어야 지금 값이 설명됩니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">과거 5년 실적</span>
                <span class="fin-card-value">${coDefaultGrowth(rows).toFixed(1)}%</span>
                <p class="fin-card-plain">같은 기간 실제 FCF 연평균 증가율입니다.</p></div>
        </div>
        <p class="fin-note">
            두 숫자의 간격이 이 주식에 걸린 기대입니다. 어느 쪽이 맞는지는 이 화면이 답하지 않습니다 —
            <strong>판단은 보는 사람의 몫</strong>이고, 이 도구는 그 판단이 무엇에 대한 것인지만 분명히 합니다.
        </p>`}`;
};

const coDcfPanel = (rows, CUR) => {
    if (CO_DCF.growth === null) CO_DCF.growth = coDefaultGrowth(rows);
    const d = coDcf(rows);
    const input = (key, label, step, min, max) => `
        <label class="co-dcf-input">
            <span>${finEsc(label)}</span>
            <input type="number" data-co-dcf="${key}" value="${CO_DCF[key]}"
                   step="${step}" min="${min}" max="${max}"><i>%</i>
        </label>`;

    return `
    <section class="fin-block fin-block-wide">
        <h2>DCF — 현금흐름 할인</h2>
        <p class="fin-lead">
            앞으로 벌어들일 잉여현금흐름을 오늘 가치로 당겨 더한 값입니다.
            <strong>세 가지 가정이 결과를 지배합니다</strong> — 그래서 숨기지 않고 여기 둡니다. 직접 바꿔 보세요.
        </p>
        <div class="co-dcf-inputs">
            ${input('growth', '향후 5년 FCF 성장률', 0.5, -30, 60)}
            ${input('terminal', '영구성장률', 0.1, 0, 5)}
            ${input('discount', '할인율 (WACC)', 0.25, 1, 30)}
            <button class="pf-btn pf-btn-ghost" data-co-dcf-reset="1">기본값</button>
        </div>
        ${!d ? '<p class="fin-note">잉여현금흐름이 음수이거나 없어 DCF를 낼 수 없습니다. 현금을 쓰는 국면의 기업에는 이 방법이 맞지 않습니다.</p>'
          : d.invalid ? `<p class="fin-note">${finEsc(d.invalid)}</p>` : `
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">기업가치 (EV)</span>
                <span class="fin-card-value">${coNum(d.ev, CUR)}</span>
                <p class="fin-card-plain">향후 현금흐름 + 잔존가치의 현재가치 합입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">주주가치</span>
                <span class="fin-card-value">${coNum(d.equity, CUR)}</span>
                <p class="fin-card-plain">기업가치에서 순부채를 뺀 값입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">주당 가치</span>
                <span class="fin-card-value">${d.perShare === null ? '—' : coNum(d.perShare, CUR)}</span>
                <p class="fin-card-plain">${d.shares ? `희석주식수 ${mmFmt(d.shares, 0)}주 기준` : '주식수를 못 읽어 계산하지 못했습니다.'}</p></div>
            <div class="fin-card"><span class="fin-card-title">잔존가치 비중</span>
                <span class="fin-card-value">${coPct(d.tailShare)}</span>
                <p class="fin-card-plain">전체 가치 중 6년차 이후가 차지하는 몫입니다. 이 값이 높을수록 결과가 영구성장률 가정에 좌우됩니다.</p></div>
        </div>
        <div class="co-table-wrap">
            <table class="co-table">
                <thead><tr><th>연차</th>${d.flows.map((f) => `<th>${f.year}년</th>`).join('')}<th>잔존</th></tr></thead>
                <tbody>
                    <tr><td class="co-label">예상 FCF</td>${d.flows.map((f) => `<td>${coNum(f.fcf, CUR)}</td>`).join('')}<td>${coNum(d.tail, CUR)}</td></tr>
                    <tr><td class="co-label">현재가치</td>${d.flows.map((f) => `<td>${coNum(f.pv, CUR)}</td>`).join('')}<td>${coNum(d.tailPv, CUR)}</td></tr>
                </tbody>
            </table>
        </div>
        <p class="fin-note">
            기준 FCF ${coNum(d.base, CUR)} (FY${rows[0].fy} 실적) 에서 출발합니다.
        </p>
        ${coSensPanel(rows, CUR)}`}
        ${coReversePanel(rows, CUR, CO_DATA || {})}
    </section>`;
};

// --- 구조 (심층) --------------------------------------------------------------
const coStructRows = (r, CUR) => {
    const R = r.raw;
    const liab = [
        ['단기차입금·기업어음', R.debt_short],
        ['유동성 장기부채', R.debt_current_portion],
        ['매입채무', R.payables],
        ['미지급비용', R.accrued],
        ['이연수익(선수금)', R.deferred_revenue],
        ['리스부채 (유동)', R.lease_current],
        ['기타 유동부채', R.other_current],
        ['장기차입금', R.debt_long],
        ['리스부채 (비유동)', R.lease_noncurrent],
        ['이연법인세', R.deferred_tax],
        ['기타 비유동부채', R.other_noncurrent],
    ].filter(([, v]) => Number.isFinite(v));
    const asset = [
        ['현금성자산', R.cash],
        ['단기투자·유가증권', R.securities_current],
        ['매출채권', R.receivables],
        ['재고자산', R.inventory],
        ['유형자산', R.ppe],
        ['영업권', R.goodwill],
        ['무형자산', R.intangibles],
    ].filter(([, v]) => Number.isFinite(v));
    return { liab, asset };
};

const coBarList = (rows, total, CUR) => {
    const max = Math.max(...rows.map(([, v]) => Math.abs(v)), 1);
    return `<div class="mm-bars mm-bars-compact">
        ${rows.map(([label, v]) => `
            <div class="mm-bar-row">
                <span class="mm-bar-label">${finEsc(label)}</span>
                <span class="mm-bar-track"><span class="mm-bar-fill" style="width:${(Math.abs(v) / max * 100).toFixed(1)}%"></span></span>
                <span class="mm-bar-value">${coNum(v, CUR)}${total ? `<span class="co-share">${(v / total * 100).toFixed(0)}%</span>` : ''}</span>
            </div>`).join('')}
    </div>`;
};

let CO_STRUCT_OPEN = null;   // 'liab' | 'asset' | null

const coDeepPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    const { liab, asset } = coStructRows(latest, CUR);

    return `
    <section class="fin-block fin-block-wide">
        <h2>부채 구조 — 언제 갚아야 하는가</h2>
        <p class="fin-lead">
            부채비율 하나로는 보이지 않는 것이 있습니다. 회사를 어렵게 만드는 건 <strong>얼마를 빚졌는지가 아니라 언제 갚아야 하는지</strong>입니다.
        </p>
        <div class="fin-cards">
            <div class="fin-card"><span class="fin-card-title">이자부 부채 합계</span>
                <span class="fin-card-value">${coNum(latest.debt_total, CUR)}</span>
                <p class="fin-card-plain">매입채무 같은 영업부채를 뺀, 이자를 무는 빚만 모은 값입니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">1년 내 만기 비중</span>
                <span class="fin-card-value">${coPct(latest.short_share)}</span>
                <p class="fin-card-plain">이자부 부채 중 1년 안에 갚거나 차환해야 하는 몫입니다. 높을수록 금리·자금시장 경색에 민감합니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">이자보상배율</span>
                <span class="fin-card-value">${coRatio(latest.interest_cover, 1)}배</span>
                <p class="fin-card-plain">영업이익이 이자비용의 몇 배인가. 1배 아래면 본업으로 이자도 못 냅니다.</p></div>
            <div class="fin-card"><span class="fin-card-title">당좌비율</span>
                <span class="fin-card-value">${coPct(latest.quick_ratio)}</span>
                <p class="fin-card-plain">재고를 뺀 유동자산으로 단기부채를 갚을 수 있는 정도입니다.</p></div>
        </div>
        ${coTable(rows, [
            { label: '이자부 부채', fmt: (r) => coNum(r.debt_total, CUR) },
            { label: '1년 내 만기', fmt: (r) => coNum(r.interest_bearing_short, CUR) },
            { label: '순부채', fmt: (r) => coNum(r.net_debt, CUR) },
            { label: '이자보상배율', fmt: (r) => coRatio(r.interest_cover, 1) },
        ])}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>자산·자본 구조</h2>
        <p class="fin-lead">항목을 눌러 구성을 펼쳐 보세요.</p>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${CO_STRUCT_OPEN === 'asset' ? 'on' : ''}" data-co-struct="asset">자산 구성 (${asset.length})</button>
            <button class="mm-view-btn ${CO_STRUCT_OPEN === 'liab' ? 'on' : ''}" data-co-struct="liab">부채 구성 (${liab.length})</button>
        </div>
        ${CO_STRUCT_OPEN === 'asset' ? `
            ${coBarList(asset, latest.raw.assets, CUR)}
            <p class="fin-note">비율은 총자산 ${coNum(latest.raw.assets, CUR)} 대비입니다. 합이 100%가 되지 않는 것은 위에 없는 잔여 항목이 있기 때문입니다.</p>`
        : CO_STRUCT_OPEN === 'liab' ? `
            ${coBarList(liab, latest.raw.liabilities, CUR)}
            <p class="fin-note">비율은 총부채 ${coNum(latest.raw.liabilities, CUR)} 대비입니다.</p>`
        : ''}
        ${coTable(rows, [
            { label: '총자산', fmt: (r) => coNum(r.raw.assets, CUR) },
            { label: '총부채', fmt: (r) => coNum(r.raw.liabilities, CUR) },
            { label: '자기자본', fmt: (r) => coNum(r.raw.equity, CUR) },
            { label: '이익잉여금', fmt: (r) => coNum(r.raw.retained_earnings, CUR) },
            { label: '자기자본비율', fmt: (r) => coPct(r.equity_ratio) },
        ])}
    </section>`;
};

const coHealthPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    return `
        <div class="fin-cards">
            ${coSeriesCard('revenue', '매출', '한 해 동안 벌어들인 전체 매출입니다.',
                (r) => r.raw.revenue, (v) => coNum(v, CUR))}
            ${coSeriesCard('current_ratio', '유동비율',
                '1년 안에 갚을 빚 대비 1년 안에 현금이 되는 자산. 100%를 밑돌면 단기 자금이 빠듯하다는 뜻입니다.',
                (r) => r.current_ratio, (v) => coPct(v))}
            ${coSeriesCard('debt_ratio', '부채비율 (부채/자산)',
                '자산 중 남의 돈이 차지하는 비율입니다. 업종마다 정상 범위가 크게 달라 같은 업종끼리 비교해야 합니다.',
                (r) => r.debt_ratio, (v) => coPct(v))}
            ${coSeriesCard('operating_margin', '영업이익률', '매출 100원으로 본업에서 남긴 이익입니다.',
                (r) => r.operating_margin, (v) => coPct(v))}
            ${coSeriesCard('roe', 'ROE',
                '주주 돈으로 낸 수익률입니다. 빚을 많이 쓰면 자연히 높아지므로 부채비율과 같이 봐야 합니다.',
                (r) => r.roe, (v) => coPct(v))}
        </div>
        <section class="fin-block fin-block-wide">
            <h2>연도별 추이</h2>
            ${coTable(rows, [
                { label: '매출', fmt: (r) => coNum(r.raw.revenue, CUR) },
                { label: '영업이익', fmt: (r) => coNum(r.raw.operating_income, CUR) },
                { label: '순이익', fmt: (r) => coNum(r.raw.net_income, CUR) },
                { label: '영업이익률', fmt: (r) => coPct(r.operating_margin) },
                { label: '유동비율', fmt: (r) => coPct(r.current_ratio) },
                { label: '부채비율', fmt: (r) => coPct(r.debt_ratio) },
            ])}
        </section>`;
};

const coValuationPanel = (rowsDesc, CUR) => {
    const rows = [...rowsDesc].reverse();
    const latest = rowsDesc[0];
    return `
        <div class="fin-cards">
            ${coSeriesCard('fcf', '잉여현금흐름 (FCF)',
                '영업으로 번 현금에서 설비투자를 뺀 값입니다. 배당·자사주·부채상환에 쓸 수 있는 실제 여윳돈입니다.',
                (r) => r.fcf, (v) => coNum(v, CUR))}
            ${coSeriesCard('cfo', '영업활동현금흐름',
                '실제로 영업에서 걷어들인 현금입니다. 회계상 이익과 다를 수 있습니다.',
                (r) => r.raw.cfo, (v) => coNum(v, CUR))}
            ${coSeriesCard('fcf_margin', 'FCF 마진',
                '매출이 현금으로 남는 비율입니다. 이익은 나는데 이 값이 낮으면 회계 이익과 현금이 어긋난다는 신호입니다.',
                (r) => r.fcf_margin, (v) => coPct(v))}
            ${coSeriesCard('net_debt', '순부채',
                '이자부 부채에서 현금·단기투자를 뺀 값입니다. 음수면 빚보다 현금이 많다는 뜻입니다.',
                (r) => r.net_debt, (v) => coNum(v, CUR))}
            ${coSeriesCard('roa', 'ROA',
                '자산 전체로 낸 수익률입니다. ROE와 벌어지면 그 차이가 레버리지에서 옵니다.',
                (r) => r.roa, (v) => coPct(v))}
        </div>
        <section class="fin-block fin-block-wide">
            <h2>현금 흐름</h2>
            ${coTable(rows, [
                { label: '영업현금흐름', fmt: (r) => coNum(r.raw.cfo, CUR) },
                { label: '설비투자 (CapEx)', fmt: (r) => coNum(r.raw.capex, CUR) },
                { label: '잉여현금흐름', fmt: (r) => coNum(r.fcf, CUR) },
                { label: 'FCF 마진', fmt: (r) => coPct(r.fcf_margin) },
                { label: '순이익', hint: '현금과 비교', fmt: (r) => coNum(r.raw.net_income, CUR) },
            ])}
            <p class="fin-note">
                순이익과 영업현금흐름이 오래 벌어져 있으면 이유를 봐야 합니다 — 매출채권이 쌓였거나, 재고가 늘었거나,
                회계상 이익이 현금으로 들어오지 않는 구조일 수 있습니다.
            </p>
        </section>
        ${coDcfPanel(rowsDesc, CUR)}`;
};

// The SEC side's counterpart to the DART cards' 추이 보기 -- same component
// underneath (finSeriesBlock), so one filer's chart cannot drift from the
// other's. `pick` reads this card's value out of a derived row, which is what
// lets a single definition serve both the headline figure and every point in
// the series behind it.
let CO_OPEN_CARD = null;
let CO_SERIES_ROWS = { annual: [], quarterly: [] };

const coSeriesCard = (key, title, plain, pick, fmt) => {
    const { annual, quarterly } = CO_SERIES_ROWS;
    const latest = annual.length ? annual[annual.length - 1] : null;
    const toPoints = (rowsAsc) => rowsAsc
        .map((r) => ({ period: r.period, value: pick(r) }))
        .filter((p) => p.period && Number.isFinite(p.value));
    const a = toPoints(annual);
    const q = toPoints(quarterly);
    const open = CO_OPEN_CARD === key;
    const hasSeries = a.length >= 2 || q.length >= 2;

    return `<div class="fin-card co-kfa-card ${open ? 'open' : ''} ${hasSeries ? 'co-clickable' : ''}"
        data-co-card="${finEsc(key)}">
        <span class="fin-card-title">${finEsc(title)}</span>
        <span class="fin-card-value">${latest ? fmt(pick(latest)) : '—'}</span>
        <p class="fin-card-plain">${finEsc(plain)}</p>
        ${hasSeries && open ? `<div class="co-kfa-chart">${finSeriesBlock(a, q, fmt)}</div>` : ''}
    </div>`;
};

const coRenderLevel = (level, rowsDesc, data, qrowsDesc = []) => {
    const CUR = data.currency || 'KRW';
    // Oldest-first is what the chart wants; the panels' own tables still take
    // the descending list they were written against.
    CO_SERIES_ROWS = {
        annual: [...rowsDesc].reverse(),
        quarterly: [...qrowsDesc].slice().sort((x, y) => String(x.period).localeCompare(String(y.period))),
    };
    const parts = coLevelsUpTo(level).map((id) => {
        if (id === 'health') return coHealthPanel(rowsDesc, CUR);
        if (id === 'valuation') return coValuationPanel(rowsDesc, CUR);
        return coDeepPanel(rowsDesc, CUR);
    });
    return parts.join('\n<hr class="co-sep">\n');
};
