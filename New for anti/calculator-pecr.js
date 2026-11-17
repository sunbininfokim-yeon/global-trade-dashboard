// CR(구조조정) · PE/LBO · 딜 views for the company calculator.
//
// Every number shown here comes from an engine snapshot,
// public/data/kfa_pecr/<corp_code>_v1.json, built offline by
// tools/ops/build_kfa_pecr_snapshots.py around Codex's
// scripts/dart/build_pe_cr.py. Nothing in this file re-derives an engine
// card. The one thing computed in the browser is the LBO what-if, which runs
// on the user's own inputs and says so.
//
// Strict vs reported basis: the engine keeps strict cards (reviewed note
// inputs) and, under separate keys, reported-basis fallbacks built from the
// tagged statement lines. A card shows the strict value when it exists and
// otherwise the fallback, with a "공시계정 기준" badge -- never the two mixed.
//
// Loaded after calculator.js; reads finEsc / coNum / loadFirstJson /
// finDataPaths / kfaReason from the shared global scope at call time.

const PECR_FALLBACK = {
    ebitda: 'ebitda_cf', ebitda_margin: 'ebitda_cf_margin', interest_coverage: 'interest_coverage_cash',
    net_debt: 'net_debt_reported', net_debt_to_ebitda: 'net_debt_reported_to_ebitda',
    ev: 'ev_reported', ev_to_ebitda: 'ev_reported_to_ebitda', ev_to_sales: 'ev_reported_to_sales',
    per: 'per_basic', pbr: 'pbr_basic',
};
const PECR_IS_FALLBACK = new Set(Object.values(PECR_FALLBACK));

// fmt: money | pct (0.15 -> 15%) | x (배) | days
const PECR_META = {
    operating_income: ['영업이익', 'money', '손익계산서 영업이익입니다.'],
    operating_margin: ['영업이익률', 'pct', '영업이익 ÷ 매출.'],
    cogs_to_sales: ['매출원가율', 'pct', '매출원가 ÷ 매출. 3년 연속 오르면 원가 압박 신호입니다.'],
    ebitda: ['EBITDA', 'money', '영업이익 + 감가상각 + 무형자산상각. 상각비는 공시 주석(XBRL)에서 가져옵니다.'],
    ebitda_margin: ['EBITDA 마진', 'pct', 'EBITDA ÷ 매출.'],
    ebit: ['EBIT', 'money', '세전이익 + 이자비용 − 이자수익. 영업이익과 정의가 다릅니다.'],
    cfo: ['영업활동현금흐름', 'money', '영업으로 실제 들어온 현금입니다.'],
    cfi: ['투자활동현금흐름', 'money', '설비·지분 투자 등에 쓴(−) 또는 회수한(+) 현금입니다.'],
    cff: ['재무활동현금흐름', 'money', '차입·상환·배당 등 자금조달 현금입니다.'],
    cash_flow_net_activities: ['현금 순증감', 'money', '세 활동의 합계입니다.'],
    cash_flow_fx_effect: ['환율효과', 'money', '외화 현금의 환산 차이입니다.'],
    fcf: ['잉여현금흐름(FCF)', 'money', '영업현금흐름 − 유형·무형자산 투자.'],
    fcf_to_ebitda: ['FCF 전환율', 'pct', 'FCF ÷ EBITDA. LBO에서 부채 상환 속도를 정합니다.'],
    operating_nwc: ['영업운전자본', 'money', '매출채권 + 재고 − 매입채무.'],
    operating_nwc_change: ['영업운전자본 증감', 'money', '증가하면 그만큼 현금이 묶였다는 뜻입니다.'],
    ccc_days: ['현금전환주기(CCC)', 'days', '매출채권일수 + 재고일수 − 매입채무일수.'],
    interest_coverage: ['이자보상배율', 'x', '영업이익 ÷ 이자비용. 3년 연속 1배 미만이면 한계기업(한국은행 기준)입니다.'],
    finance_cost_coverage: ['금융원가 커버리지', 'x', '영업이익 ÷ 금융원가 총액(환손실 등 포함). 이자보상배율과 다릅니다.'],
    dscr: ['DSCR', 'x', '원리금 상환 전 현금 ÷ 원리금. 1 미만이면 상환 재원 부족.'],
    net_debt: ['순차입금', 'money', '차입금·사채·리스부채 − 현금. 음수면 순현금입니다.'],
    net_debt_to_ebitda: ['순차입금/EBITDA', 'x', '몇 년치 EBITDA로 빚을 갚을 수 있는지. PE 레버리지의 기준입니다.'],
    debt_ratio: ['부채비율', 'pct', '총부채 ÷ 자본.'],
    capital_erosion_ratio: ['자본잠식률', 'pct', '(자본금 − 자본) ÷ 자본금. 0보다 크면 자본잠식입니다.'],
    current_ratio: ['유동비율', 'x', '유동자산 ÷ 유동부채.'],
    current_liabilities_share: ['유동부채 비중', 'pct', '총부채 중 1년 안에 갚을 부채의 비중입니다.'],
    debt_due_within_1y: ['1년 내 만기 원금', 'money', '차입·사채·리스의 12개월 내 약정 원금.'],
    liquidity_coverage_1y: ['1년 유동성 커버리지', 'x', '가용현금 ÷ 1년 내 만기 원금.'],
    financing_principal_due_1y_share: ['1년 내 만기 비중', 'pct', '전체 차입 원금 중 1년 안에 돌아오는 비중.'],
    market_cap: ['시가총액(보통주)', 'money', '보통주 주가 × 유통주식수 (기준일 표시).'],
    per: ['PER', 'x', '보통주 시가총액 ÷ 지배주주 순이익.'],
    pbr: ['PBR', 'x', '보통주 시가총액 ÷ 지배주주 자본.'],
    ev: ['EV(기업가치)', 'money', '보통·우선주 시가 + 순차입금 + 비지배지분.'],
    ev_to_ebitda: ['EV/EBITDA', 'x', '인수 가격을 EBITDA 몇 배로 치르는지. 딜·PE의 기본 배수입니다.'],
    ev_to_sales: ['EV/매출', 'x', '적자 기업 비교에 씁니다.'],
    roe: ['ROE', 'pct', '지배주주 순이익 ÷ 평균 지배주주 자본.'],
    roa: ['ROA', 'pct', '순이익 ÷ 평균 총자산.'],
    order_backlog: ['수주잔고', 'money', '회사가 공시한 확정 수주잔고.'],
    new_orders: ['신규 수주', 'money', '기간 중 신규 확정 수주.'],
    book_equity: ['자본총계', 'money', '장부상 자본.'],
};

const PECR_REASON_PREFIX = [
    ['not_applicable:financial_entity', '금융회사에는 적용하지 않음'],
    ['not_applicable:industry_ccc', '이 업종에는 적용하지 않음'],
    ['not_applicable:not_listed', '비상장 — 시세 없음'],
    ['missing:market_observation', '시세 없음 (비상장 또는 주식수 미확인)'],
    ['missing:dated_preferred', '우선주 시가 미확인'],
    ['missing:tagged_borrowings', '표준 차입금 계정 없음 (회사 확장태그)'],
    ['missing:dart_fact_', '공시 재무제표에 해당 계정 없음'],
    ['missing:opening_', '전기 기초잔액 없음'],
    ['missing:reviewed_', '주석 검토 입력 필요'],
    ['missing:card_', '앞 단계 값이 없음'],
    ['missing_or_incompatible:strict_ebitda', '상각비 주석값 없음'],
    ['missing:strict', '상각비 주석값 없음'],
    ['missing:cf_depreciation', '상각비 공시 없음'],
    ['requires:', '추가 공시 입력 필요'],
    ['nonpositive:', '분모가 0 이하 (적자 등)'],
];
const pecrReason = (r) => {
    if (!r) return '';
    const hit = PECR_REASON_PREFIX.find(([p]) => r.startsWith(p));
    return hit ? hit[1] : (typeof kfaReason === 'function' ? kfaReason(r) : r);
};

const pecrFmt = (fmt, v) => {
    if (v === null || v === undefined || !Number.isFinite(v)) return '—';
    if (fmt === 'money') return coNum(v, 'KRW');
    if (fmt === 'pct') return `${(v * 100).toFixed(1)}%`;
    if (fmt === 'days') return `${Math.round(v)}일`;
    return `${v.toFixed(Math.abs(v) >= 100 ? 0 : 1)}배`;
};

// Strict card if it has a value, else its reported-basis fallback.
const pecrCard = (snap, key) => {
    const cards = snap?.pe_cr?.cards || {};
    const strict = cards[key];
    const alt = PECR_FALLBACK[key] && cards[PECR_FALLBACK[key]];
    if (strict && strict.value !== null && strict.value !== undefined) return { ...strict, key, basis: 'strict' };
    if (alt && alt.value !== null && alt.value !== undefined) return { ...alt, key, basis: 'reported' };
    return strict ? { ...strict, key, basis: 'strict' } : null;
};

const pecrCardHtml = (snap, key) => {
    const card = pecrCard(snap, key);
    const [label, fmt, plain] = PECR_META[key] || [key, 'x', ''];
    if (!card) return '';
    const badge = card.basis === 'reported'
        ? '<span class="pecr-badge" title="주석 검토값이 없어 공시 재무제표 계정으로 계산했습니다">공시계정 기준</span>' : '';
    const date = key === 'market_cap' && card.market_date ? ` · ${finEsc(card.market_date)} 기준` : '';
    return `
        <div class="fin-card pecr-card${card.value === null || card.value === undefined ? ' pecr-empty' : ''}">
            <span class="fin-card-title">${finEsc(label)} ${badge}</span>
            <span class="fin-card-value">${pecrFmt(fmt, card.value)}</span>
            <p class="fin-card-plain">${finEsc(plain)}${date}${card.reason ? ` <span class="pecr-reason">(${finEsc(pecrReason(card.reason))})</span>` : ''}</p>
        </div>`;
};

const pecrSection = (snap, sectionId, { hideEmpty = false } = {}) => {
    const screen = snap?.pe_cr?.cr_pe_screen;
    const sec = (screen?.sections || []).find((s) => s.id === sectionId);
    if (!sec) return '';
    const keys = sec.card_ids.filter((k) => !PECR_IS_FALLBACK.has(k) && PECR_META[k]);
    const cards = keys.filter((k) => !hideEmpty || pecrCard(snap, k)?.value != null);
    if (!cards.length) return '';
    return `
        <section class="pecr-section">
            <h3>${finEsc(sec.label_ko)}</h3>
            <div class="fin-cards">${cards.map((k) => pecrCardHtml(snap, k)).join('')}</div>
        </section>`;
};

const PECR_SIGNAL_STATE = {
    triggered: ['pecr-sig-on', '해당'],
    not_triggered: ['pecr-sig-off', '해당 없음'],
    unavailable: ['pecr-sig-na', '판단 불가'],
};
// Unit of each trend signal's yearly observations.
const PECR_SIGNAL_FMT = {
    operating_loss_2y: 'money', negative_cfo_2y: 'money', rising_cost_ratio_3y: 'pct',
    interest_coverage_under_1_3y: 'x', interest_coverage_cash_under_1_3y: 'x',
    negative_equity: 'money', equity_below_issued_capital: 'pct', dscr_under_1: 'x', cash_below_1y_principal: 'x',
};
const pecrSignals = (snap) => {
    const all = (snap?.pe_cr?.cr_pe_screen?.signals || []).filter((s) => s.status !== 'not_applicable');
    const decided = all.filter((s) => s.status === 'triggered' || s.status === 'not_triggered')
        .sort((a, b) => (a.status === 'triggered' ? -1 : 0) - (b.status === 'triggered' ? -1 : 0));
    const open = all.filter((s) => s.status === 'unavailable');
    if (!all.length) return '';
    return `
        <section class="pecr-section">
            <h3>구조조정 체크리스트</h3>
            <ul class="pecr-signals">
                ${decided.map((s) => {
                    const [cls, word] = PECR_SIGNAL_STATE[s.status];
                    const fmt = PECR_SIGNAL_FMT[s.id] || 'x';
                    const obs = (s.observations || []).filter((o) => Number.isFinite(o.value));
                    const trail = obs.map((o) => `${o.fiscal_year ? `${o.fiscal_year} ` : ''}${pecrFmt(fmt, o.value)}`).join(' · ');
                    return `<li class="${cls}"><span class="pecr-sig-dot"></span><b>${finEsc(s.label_ko)}</b>
                        <span class="pecr-sig-word">${word}</span>
                        ${trail ? `<span class="pecr-sig-trail">${finEsc(trail)}</span>` : ''}</li>`;
                }).join('')}
            </ul>
            ${open.length ? `<p class="fin-note">공시만으로 판단할 수 없는 항목 ${open.length}개: ${open.map((s) => finEsc(s.label_ko)).join(', ')}
                — 주석 검토·사업계획·감사보고서 입력이 필요합니다.</p>` : ''}
        </section>`;
};

// 회사채·CP·단기사채 미상환 잔액 만기 (OpenDART 정기보고서 표 그대로).
const pecrFunding = (snap) => {
    const im = snap?.pe_cr?.disclosure_profile?.instrument_maturity;
    const rows = (im?.rows || []).filter((r) => r.outstanding != null || r.status === 'reported');
    if (!rows.length) return '';
    const LABEL = { corporate_bond: '회사채', commercial_paper: '기업어음(CP)', short_term_bond: '단기사채' };
    const cols = ['10d', '30d', '90d', '180d', '1y'];
    const cell = (c) => (c && c.value != null ? coNum(c.value) : '<span class="pecr-na" title="원표에 이 구간 경계가 없음">—</span>');
    return `
        <section class="pecr-section">
            <h3>자금조달 만기 (발행사 기준, 누적)</h3>
            <div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>상품</th><th>미상환 잔액</th>${cols.map((c) => `<th>${c.replace('d', '일').replace('1y', '1년')} 이내</th>`).join('')}</tr></thead>
                <tbody>${rows.map((r) => `<tr><td>${finEsc(LABEL[r.instrument] || r.instrument)}</td>
                    <td>${r.outstanding != null ? coNum(r.outstanding) : '—'}</td>
                    ${cols.map((c) => `<td>${cell((r.cumulative || {})[c])}</td>`).join('')}</tr>`).join('')}</tbody>
            </table></div>
            <p class="fin-note">사업보고서 "증권의 발행을 통한 자금조달" 표의 미상환 잔액입니다. 발행사 단독 기준이라 연결 전체 차입금이나 1년 내 만기 원금 전체와는 다릅니다.
                ${im.issuer_type?.label_ko ? `발행사 유형: ${finEsc(im.issuer_type.label_ko)}.` : ''}</p>
        </section>`;
};

// --- Regulatory capital (K-ICS / Basel / NCR / 조정자기자본비율) -----------------
// snapshot.regulatory comes from scripts/dart/dart_kfa/regulatory_capital.py:
// the filer's own 재무건전성 table in its 사업·분기보고서, never estimated.
const PECR_REG = {
    kics: { title: '지급여력비율 (K-ICS)', ratio: 'ratio', amounts: [['available', '가용자본 (A)'], ['required', '요구자본 (B)']],
        plain: '가용자본 ÷ 요구자본. 요구자본은 1년 99.5% 신뢰수준의 손실 규모(보험·시장·신용·운영 위험)입니다.' },
    ncr: { title: '순자본비율 (NCR)', ratio: 'ratio', amounts: [['ncr_capital', '영업용순자본 (A)'], ['total_risk', '총위험액 (B)'], ['required_equity', '필요유지자기자본 (C)']],
        plain: '(영업용순자본 − 총위험액) ÷ 필요유지자기자본.' },
    credit_finance: { title: '조정자기자본비율', ratio: 'ratio', amounts: [['adjusted_equity', '조정자기자본'], ['adjusted_assets', '조정총자산']],
        plain: '조정자기자본 ÷ 조정총자산. 여신전문금융업 경영지도비율입니다.' },
    basel: { title: 'BIS 자기자본비율 (바젤 III)', ratio: 'cet1_ratio', amounts: [['cet1', '보통주자본'], ['tier1', '기본자본'], ['total_capital', '총자본'], ['rwa', '위험가중자산']],
        plain: '자본 ÷ 위험가중자산(RWA). 보통주자본비율(CET1)이 가장 엄격한 기준입니다.' },
};
const pecrPct = (v) => (Number.isFinite(v) ? `${(v * 100).toFixed(v >= 10 ? 0 : 1)}%` : '—');

const pecrRegulatory = (snap) => {
    const r = snap?.regulatory;
    const spec = r && PECR_REG[r.kind];
    if (!spec || !(r.series || []).length) return '';
    const series = r.series;
    const last = series[series.length - 1];
    const cards = [];
    const card = (label, value, plain, extra = '') => cards.push(`
        <div class="fin-card pecr-card"><span class="fin-card-title">${finEsc(label)}</span>
            <span class="fin-card-value">${value}</span><p class="fin-card-plain">${finEsc(plain)}${extra}</p></div>`);
    if (r.kind === 'basel') {
        for (const [k, label] of [['cet1_ratio', '보통주자본비율 (CET1)'], ['tier1_ratio', '기본자본비율 (Tier 1)'], ['total_ratio', '총자본비율']]) {
            const m = (r.minimums || {})[k] || {};
            card(label, pecrPct(last[k]), `최저 ${pecrPct(m.minimum)} · 완충자본 포함 ${pecrPct(m.with_conservation_buffer)}`,
                Number.isFinite(last[k]) && Number.isFinite(last.rwa) ? ` · 완충 포함 기준 대비 여력 ${coNum((last[k] - m.with_conservation_buffer) * last.rwa)}` : '');
        }
    } else {
        const ratio = last[spec.ratio];
        const floor = (r.thresholds || [])[0];
        card(spec.title, pecrPct(ratio), `${finEsc(last.period_end)} 기준${r.transitional_applied ? ' · 경과조치 후' : ''}`,
            floor ? ` · ${finEsc(floor.label)} 기준 ${pecrPct(floor.ratio)}` : '');
        const pre = r.pre_transitional;
        if (pre && Number.isFinite(pre.ratio)) {
            card('경과조치 전 지급여력비율', pecrPct(pre.ratio), `${finEsc(pre.period_end)} 각주 공시. 경과조치(요구자본 인식 유예)를 빼면 이만큼입니다.`,
                Number.isFinite(pre.required) ? ` · 요구자본 ${coNum(pre.required)}` : '');
        }
        if (r.kind === 'kics' && Number.isFinite(last.available) && Number.isFinite(last.required)) {
            card('100% 기준 자본 여력', coNum(last.available - last.required),
                `가용자본 − 요구자본. 요구자본이 ${pecrPct(ratio - 1)} 늘어나도 100%를 지킵니다.`);
        }
        if (r.kind === 'ncr' && Number.isFinite(last.ncr_capital) && Number.isFinite(last.total_risk)) {
            card('잉여자본 (A − B)', coNum(last.ncr_capital - last.total_risk), '영업용순자본에서 총위험액을 뺀 값입니다.');
        }
        if (r.kind === 'credit_finance' && floor && Number.isFinite(last.adjusted_assets)) {
            card('경영지도비율 대비 여력', coNum((ratio - floor.ratio) * last.adjusted_assets), `조정총자산 × (현재 비율 − ${pecrPct(floor.ratio)}).`);
        }
    }
    for (const [k, label] of spec.amounts) if (Number.isFinite(last[k])) card(label, coNum(last[k]), `${last.period_end} 기준`);
    const ratioKeys = r.kind === 'basel' ? [['cet1_ratio', 'CET1'], ['tier1_ratio', 'Tier 1'], ['total_ratio', '총자본']] : [[spec.ratio, '비율']];
    const REPORT = { FY: '사업', H1: '반기', Q1: '1분기', Q3: '3분기' };
    const thresholds = r.kind === 'basel'
        ? '바젤 III 최저: CET1 4.5% · Tier 1 6% · 총자본 8%, 자본보전완충 2.5%p 포함 7% · 8.5% · 10.5%. D-SIB·경기대응완충은 은행별로 더해집니다.'
        : (r.thresholds || []).map((t) => `${t.label} ${pecrPct(t.ratio)} 미만`).join(' · ');
    return `
        <section class="pecr-section">
            <h3>규제 자본 — ${finEsc(spec.title)}</h3>
            <div class="fin-cards">${cards.join('')}</div>
            <div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>기준일</th>${ratioKeys.map(([, l]) => `<th>${l}</th>`).join('')}${spec.amounts.filter(([k]) => series.some((p) => Number.isFinite(p[k]))).map(([, l]) => `<th>${finEsc(l)}</th>`).join('')}<th>보고서</th></tr></thead>
                <tbody>${series.slice().reverse().map((p) => `<tr><td>${finEsc(p.period_end)}</td>
                    ${ratioKeys.map(([k]) => `<td>${pecrPct(p[k])}</td>`).join('')}
                    ${spec.amounts.filter(([k]) => series.some((q) => Number.isFinite(q[k]))).map(([k]) => `<td>${coNum(p[k])}</td>`).join('')}
                    <td><a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${finEsc(p.receipt || '')}" target="_blank" rel="noopener">${REPORT[p.report] || ''}보고서</a></td></tr>`).join('')}</tbody>
            </table></div>
            <p class="fin-note">${finEsc(spec.plain)} 규제 기준: ${finEsc(thresholds)}.
                출처: 각 보고서 "재무건전성" 표 (${r.scope === 'CFS' ? '연결 기준' : r.scope === 'OFS' ? '별도 기준' : '기준 표기 없음'}). 추정하지 않은 공시값입니다.</p>
        </section>`;
};

// --- LBO what-if (browser-side, user inputs) ----------------------------------
const PECR_LBO = { entry: null, lev: null, rate: 6, growth: 3, conv: null, years: 5, exit: null };

const pecrLboDefaults = (snap) => {
    const evx = pecrCard(snap, 'ev_to_ebitda')?.value;
    const conv = pecrCard(snap, 'fcf_to_ebitda')?.value;
    const entry = Number.isFinite(evx) && evx > 0 ? Math.round(Math.min(evx, 25) * 10) / 10 : 8;
    return {
        entry, exit: entry,
        lev: Math.round(Math.min(5, entry * 0.5) * 10) / 10,
        conv: Number.isFinite(conv) ? Math.round(Math.max(0.1, Math.min(conv, 0.9)) * 100) : 40,
    };
};

const pecrLboRun = (ebitda0, p) => {
    const ev0 = ebitda0 * p.entry, debt0 = ebitda0 * p.lev, eq0 = ev0 - debt0;
    if (!(ebitda0 > 0) || !(eq0 > 0)) return null;
    let e = ebitda0, debt = debt0, cash = 0;
    const rows = [];
    for (let t = 1; t <= p.years; t++) {
        e *= 1 + p.growth / 100;
        const interest = debt * p.rate / 100;
        const free = e * p.conv / 100 - interest;
        const pay = Math.min(free, debt);   // negative free cash adds to debt
        debt -= pay;
        if (free > pay) cash += free - pay;
        rows.push({ t, ebitda: e, interest, free, debt, lev: debt / e });
    }
    const exitEv = e * p.exit, eqN = exitEv - debt + cash;
    const moic = eqN / eq0;
    return {
        ev0, debt0, eq0, exitEv, eqN, moic, irr: moic > 0 ? Math.pow(moic, 1 / p.years) - 1 : null, rows,
        bridge: { growth: (e - ebitda0) * p.entry, multiple: e * (p.exit - p.entry), delever: debt0 - debt + cash },
    };
};

const pecrLboResult = (snap) => {
    const ebitda0 = pecrCard(snap, 'ebitda')?.value;
    if (!(ebitda0 > 0)) return '<p class="fin-note">EBITDA가 없거나 0 이하라 LBO 계산을 할 수 없습니다.</p>';
    const r = pecrLboRun(ebitda0, PECR_LBO);
    if (!r) return '<p class="fin-note">차입 배수가 진입 배수보다 커서 지분 투자액이 0 이하입니다.</p>';
    return `
        <div class="pecr-lbo-kpis">
            <div><span>진입 EV</span><b>${coNum(r.ev0)}</b></div>
            <div><span>차입</span><b>${coNum(r.debt0)}</b></div>
            <div><span>지분 투자</span><b>${coNum(r.eq0)}</b></div>
            <div><span>${PECR_LBO.years}년 후 지분가치</span><b>${coNum(r.eqN)}</b></div>
            <div><span>MOIC</span><b>${r.moic.toFixed(2)}배</b></div>
            <div><span>IRR</span><b>${r.irr == null ? '—' : `${(r.irr * 100).toFixed(1)}%`}</b></div>
        </div>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>연차</th><th>EBITDA</th><th>이자</th><th>상환 재원</th><th>차입 잔액</th><th>차입/EBITDA</th></tr></thead>
            <tbody>${r.rows.map((x) => `<tr><td>${x.t}년</td><td>${coNum(x.ebitda)}</td><td>${coNum(x.interest)}</td>
                <td>${coNum(x.free)}</td><td>${coNum(x.debt)}</td><td>${x.lev.toFixed(1)}배</td></tr>`).join('')}</tbody>
        </table></div>
        <p class="fin-note">수익 분해: EBITDA 성장 ${coNum(r.bridge.growth)} · 배수 변화 ${coNum(r.bridge.multiple)} · 부채 상환·현금 ${coNum(r.bridge.delever)}.
            상환 재원 = EBITDA × 전환율 − 이자(세후 조정 없음). 입력값에 따른 시나리오이며 목표 가격이 아닙니다.</p>`;
};

const pecrLbo = (snap) => {
    if (PECR_LBO.entry == null || PECR_LBO._for !== snap.corp_code) {
        Object.assign(PECR_LBO, pecrLboDefaults(snap), { _for: snap.corp_code });
    }
    const field = (k, label, step, unit) => `
        <label class="pecr-lbo-field"><span>${label}</span>
            <input type="number" step="${step}" data-lbo="${k}" value="${PECR_LBO[k]}"><em>${unit}</em></label>`;
    return `
        <section class="pecr-section">
            <h3>LBO 간이 계산</h3>
            <p class="fin-note">기본값은 이 회사의 현재 EV/EBITDA와 FCF 전환율입니다. 값을 바꾸면 바로 다시 계산합니다.</p>
            <div class="pecr-lbo-inputs">
                ${field('entry', '진입 EV/EBITDA', 0.5, '배')}${field('lev', '총차입/EBITDA', 0.5, '배')}
                ${field('rate', '차입 금리', 0.25, '%')}${field('growth', 'EBITDA 성장률', 0.5, '%/년')}
                ${field('conv', 'FCF 전환율', 5, '%')}${field('years', '보유 기간', 1, '년')}
                ${field('exit', '청산 EV/EBITDA', 0.5, '배')}
            </div>
            <div class="pecr-lbo-out">${pecrLboResult(snap)}</div>
        </section>`;
};

// --- Peers: other snapshots on the same industry kit --------------------------
let PECR_INDEX = null;
const pecrIndex = async () => {
    if (PECR_INDEX) return PECR_INDEX;
    const doc = await loadFirstJson(finDataPaths('kfa_pecr/index_v1.json'));
    PECR_INDEX = (doc && doc.index) || {};
    return PECR_INDEX;
};

const pecrLoad = async (corpCode) => {
    if (!corpCode) return null;
    const idx = await pecrIndex();
    if (!idx[corpCode]) return null;
    const [snap] = await Promise.all([loadFirstJson(finDataPaths(`kfa_pecr/${corpCode}_v1.json`)), pecrMarket()]);
    return snap;
};

// --- Market multiples: 시가총액(Naver, daily) ÷ 분모(DART, engine snapshot) ------
// tools/ops/fetch_kfa_market.py writes the daily close and 시가총액 for every
// snapshot company; the snapshot's valuation_bases hold the denominators.
// Dividing here keeps PER/PBR/EV current without rerunning the engine.
let PECR_MARKET = null;
const pecrMarket = async () => {
    if (PECR_MARKET) return PECR_MARKET;
    const doc = await loadFirstJson(finDataPaths('kfa_market_v1.json')).catch(() => null);
    PECR_MARKET = doc || { quotes: {} };
    return PECR_MARKET;
};

const pecrLive = (snap) => {
    const q = snap?.stock_code && PECR_MARKET?.quotes?.[snap.stock_code];
    const vb = snap?.valuation_bases;
    if (!q || !vb) return null;
    const fy = vb.fy || {};
    const ltm = vb.ltm || null;
    const pick = (o, ...ks) => { for (const k of ks) if (o && Number.isFinite(o[k])) return o[k]; return null; };
    const prefExpected = /preferred/.test(snap.market_input || '');
    const prefCap = q.preferred ? q.preferred.market_cap : 0;
    const equity = q.market_cap + prefCap;
    const latest = ltm && Number.isFinite(pick(ltm, 'parent_equity', 'equity')) ? ltm : fy;
    const parentEq = pick(latest, 'parent_equity', 'equity');
    const nci = Number.isFinite(latest.equity) && Number.isFinite(latest.parent_equity) ? latest.equity - latest.parent_equity : 0;
    const niL = pick(ltm, 'net_income_parent', 'net_income');
    const niF = pick(fy, 'net_income_parent', 'net_income');
    const salesL = pick(ltm, 'revenue');
    const salesF = pick(fy, 'revenue');
    const financial = snap.pe_cr?.industry === 'financial';
    const ev = !financial && Number.isFinite(fy.net_debt) ? equity + fy.net_debt + nci : null;
    const div = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && b > 0 ? a / b : null);
    return {
        q, fy, ltm, latest, equity, prefCap, prefMissing: prefExpected && !q.preferred, nci, ev, financial,
        per_ltm: div(equity, niL), per_fy: div(equity, niF), niL, niF,
        pbr: div(equity, parentEq), parentEq,
        psr: div(equity, salesL ?? salesF), sales: salesL ?? salesF,
        ev_to_ebitda: div(ev, fy.ebitda), ev_to_sales: div(ev, salesL ?? salesF),
        p_fcf: div(equity, fy.fcf), fcf_yield: Number.isFinite(fy.fcf) && equity > 0 ? fy.fcf / equity : null,
        loss_ltm: Number.isFinite(niL) && niL <= 0, loss_fy: Number.isFinite(niF) && niF <= 0,
    };
};

const pecrMarketHtml = (snap) => {
    const m = pecrLive(snap);
    if (!m) {
        return snap?.stock_code
            ? '<p class="fin-note">이 종목의 일별 시세(kfa_market_v1.json)가 아직 없습니다. 아래 배수는 스냅샷 기준일 시세입니다.</p>' : '';
    }
    const { q } = m;
    const at = (q.traded_at || '').slice(0, 10);
    const ltmLabel = m.ltm ? `최근 4분기(~${m.ltm.period_end})` : null;
    const fyLabel = `FY${String(m.fy.period_end || '').slice(0, 4)}`;
    const capText = `${coNum(m.equity)}`;
    const row = (label, value, formula, basis, plain) => `<tr><td><b>${finEsc(label)}</b><br><span class="fin-note">${finEsc(plain)}</span></td>
        <td class="pecr-num">${value}</td><td>${formula}</td><td>${finEsc(basis)}</td></tr>`;
    const x = (v, loss) => (loss ? '적자' : pecrFmt('x', v));
    const rows = [
        row('PER', x(m.per_ltm, m.loss_ltm), `${capText} ÷ 지배주주 순이익 ${coNum(m.niL)}`, ltmLabel || '—', '시가총액 ÷ 순이익. 몇 년 치 이익에 거래되는지.'),
        row('PER (연간)', x(m.per_fy, m.loss_fy), `${capText} ÷ ${coNum(m.niF)}`, fyLabel, '직전 사업연도 순이익 기준.'),
        row('PBR', pecrFmt('x', m.pbr), `${capText} ÷ 지배주주 자본 ${coNum(m.parentEq)}`, `${m.latest.period_end} 재무상태표`, '시가총액 ÷ 장부상 자본.'),
    ];
    if (!m.financial) {
        rows.push(
            row('PSR', pecrFmt('x', m.psr), `${capText} ÷ 매출 ${coNum(m.sales)}`, ltmLabel || fyLabel, '시가총액 ÷ 매출. 적자 기업 비교에 씁니다.'),
            row('EV/EBITDA', pecrFmt('x', m.ev_to_ebitda), `EV ${coNum(m.ev)} ÷ EBITDA ${coNum(m.fy.ebitda)}`, fyLabel,
                'EV = 시가총액 + 순차입금 + 비지배지분. 부채 구조가 달라도 비교됩니다.'),
            row('EV/매출', pecrFmt('x', m.ev_to_sales), `EV ${coNum(m.ev)} ÷ 매출 ${coNum(m.sales)}`, ltmLabel || fyLabel, ''),
            row('P/FCF', m.fy.fcf > 0 ? pecrFmt('x', m.p_fcf) : '음(−) FCF', `${capText} ÷ FCF ${coNum(m.fy.fcf)}`, fyLabel,
                `잉여현금흐름 수익률 ${Number.isFinite(m.fcf_yield) ? (m.fcf_yield * 100).toFixed(1) + '%' : '—'}.`),
        );
    }
    const ref = q.naver_reference || {};
    const refTxt = [['per', 'PER'], ['pbr', 'PBR'], ['dividendYieldRatio', '배당수익률']]
        .filter(([k]) => ref[k]).map(([k, l]) => `${l} ${ref[k].value}${k === 'dividendYieldRatio' ? '%' : '배'}${ref[k].period ? ` (${finEsc(ref[k].period)})` : ''}`).join(' · ');
    const pref = q.preferred ? ` + 우선주 ${coNum(m.prefCap)} (${finEsc(q.preferred.name)} ${q.preferred.price.toLocaleString()}원)` : '';
    return `
        <section class="pecr-section"><h3>시장 배수 — 시가총액 ÷ 공시 분모</h3>
            <p class="fin-note">시가총액 <b>${capText}</b> = 보통주 ${coNum(q.market_cap)} (${finEsc(q.name)} ${q.price.toLocaleString()}원, ${finEsc(at)} 종가)${pref}.
                ${m.prefMissing ? '<b>우선주가 있으나 상장 시세가 없어 보통주만 반영했습니다.</b>' : ''}</p>
            <div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>지표</th><th>값</th><th>계산</th><th>분모 기준</th></tr></thead>
                <tbody>${rows.join('')}</tbody></table></div>
            <p class="fin-note">분자: Naver 금융 시가총액(상장주식수 × 종가, 자사주 포함), 매 영업일 장 마감 후 갱신. 분모: OpenDART 공시 재무제표
                (${m.ltm ? `최근 4분기 = FY + 당기 누적 − 전기 동기 누적, ${finEsc(m.ltm.report)} 보고서` : '연간'}).${m.financial ? '' : ` EBITDA·순차입금·FCF는 엔진 카드(${finEsc(m.fy.ebitda_card || '—')}, ${finEsc(m.fy.net_debt_card || '—')}), 순차입금은 FY말 기준.`}
                ${refTxt ? `대조용 Naver 표시값: ${refTxt}.` : ''}</p>
        </section>`;
};

const PECR_PEER_COLS = [
    ['ev_to_ebitda', 'EV/EBITDA', 'x'], ['per', 'PER', 'x'], ['pbr', 'PBR', 'x'], ['ebitda_margin', 'EBITDA 마진', 'pct'],
    ['net_debt_to_ebitda', '순차입/EBITDA', 'x'], ['interest_coverage', '이자보상', 'x'], ['roe', 'ROE', 'pct'],
];

// Market multiples on the same day for every peer when the daily file has them.
const PECR_LIVE_KEY = { per: 'per_ltm', pbr: 'pbr', ev_to_ebitda: 'ev_to_ebitda' };
const pecrPeerValue = (snap, key) => {
    const m = PECR_LIVE_KEY[key] && pecrLive(snap);
    if (m) return { value: key === 'per' && m.loss_ltm ? null : m[PECR_LIVE_KEY[key]], basis: 'strict' };
    return pecrCard(snap, key);
};

const pecrPeersHtml = (snap, peers) => {
    if (!peers) return '<p class="fin-note">피어를 불러오는 중…</p>';
    const rows = [snap, ...peers];
    const med = (key, fmt) => {
        const v = peers.map((p) => pecrPeerValue(p, key)?.value).filter(Number.isFinite).sort((a, b) => a - b);
        if (v.length < 2) return '—';
        const m = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
        return pecrFmt(fmt, m);
    };
    return `
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>기업</th>${PECR_PEER_COLS.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((s, i) => `<tr class="${i === 0 ? 'pecr-self' : ''}"><td>${finEsc((s.entity || '').replace(/\(주\)|주식회사/g, ''))}</td>
                ${PECR_PEER_COLS.map(([k, , f]) => { const c = pecrPeerValue(s, k); return `<td>${pecrFmt(f, c?.value)}${c?.basis === 'reported' && c.value != null ? '*' : ''}</td>`; }).join('')}</tr>`).join('')}
                ${peers.length >= 2 ? `<tr class="pecr-median"><td>피어 중앙값</td>${PECR_PEER_COLS.map(([k, , f]) => `<td>${med(k, f)}</td>`).join('')}</tr>` : ''}
            </tbody>
        </table></div>
        <p class="fin-note">${peers.length ? `같은 업종 분류(${finEsc(snap.pe_cr?.industry_profile?.label_ko || snap.pe_cr?.industry || '')})의 엔진 스냅샷 ${peers.length}개` : '같은 업종의 다른 스냅샷이 아직 없습니다'}.
            * = 공시계정 기준. PER·PBR·EV/EBITDA는 일별 시가총액이 있으면 같은 날 시세로 계산합니다(PER은 최근 4분기 이익).</p>`;
};

const pecrLoadPeers = async (snap) => {
    const idx = await pecrIndex();
    const ids = Object.entries(idx)
        .filter(([id, v]) => id !== snap.corp_code && !v.financial && v.industry === snap.pe_cr?.industry)
        .map(([id]) => id).slice(0, 8);
    const loaded = await Promise.all(ids.map((id) => loadFirstJson(finDataPaths(`kfa_pecr/${id}_v1.json`))));
    return loaded.filter(Boolean);
};

// --- Views ---------------------------------------------------------------------
const pecrHead = (snap) => {
    const p = snap.pe_cr || {};
    const mc = p.cards?.market_cap;
    const live = snap.stock_code && PECR_MARKET?.quotes?.[snap.stock_code];
    const mdate = live ? (live.traded_at || '').slice(0, 10) + ' (일별)' : mc?.market_date;
    return `<p class="fin-note pecr-head">엔진 스냅샷: FY${finEsc(snap.fiscal_year)} ${snap.fs_div === 'OFS' ? '별도' : '연결'} ·
        업종 ${finEsc(p.industry_profile?.label_ko || p.industry || '')}${mdate ? ` · 시세 ${finEsc(mdate)}` : ''} ·
        생성 ${finEsc(snap.generated_at || '')}</p>`;
};

const pecrViewHtml = (data, view) => {
    const snap = data.pecr;
    if (!snap) {
        return `<div class="fin-empty"><p class="fin-empty-title">이 기업은 아직 PE·CR 엔진 스냅샷이 없습니다</p>
            <p>스냅샷은 OpenDART 원본 공시로 미리 계산해 둡니다(tools/ops/build_kfa_pecr_snapshots.py). 기본 탭의 지표는 그대로 볼 수 있습니다.</p></div>`;
    }
    const financial = snap.pe_cr?.industry === 'financial';
    const lens = (snap.pe_cr?.cr_pe_screen?.lens_order || {})[view === 'cr' ? 'cr' : 'pe'] || [];
    if (view === 'cr') {
        return pecrHead(snap) + (financial
            ? pecrRegulatory(snap) + pecrFunding(snap) + pecrSection(snap, 'capital_structure', { hideEmpty: true }) + pecrSection(snap, 'cash_flow', { hideEmpty: true })
              + '<p class="fin-note">금융회사는 산업기업용 CR 지표(EBITDA, 순차입금, 이자보상배율 등)를 적용하지 않습니다. 업권별 지표는 기본 탭에 있습니다.</p>'
            : pecrSignals(snap) + lens.map((id) => pecrSection(snap, id)).join('') + pecrFunding(snap));
    }
    if (view === 'pe') {
        return pecrHead(snap) + ['profitability', 'cash_flow', 'capital_structure', 'repayment'].map((id) => pecrSection(snap, id)).join('')
            + pecrLbo(snap);
    }
    // deal
    if (financial) {
        return pecrHead(snap) + (pecrMarketHtml(snap) || '<p class="fin-note">비상장사라 시장 배수가 없습니다.</p>')
            + '<p class="fin-note">금융회사는 EV·EBITDA 배수를 쓰지 않습니다(부채가 영업 자산). PER·PBR과 규제 자본(CR 탭)을 함께 봅니다.</p>';
    }
    const c = (k) => pecrCard(snap, k)?.value;
    const ev = c('ev'), cap = c('market_cap'), nd = c('net_debt'), total = snap.pe_cr?.cards?.equity_market_value_total?.value;
    const pref = Number.isFinite(total) && Number.isFinite(cap) ? total - cap : null;
    const nci = Number.isFinite(ev) && Number.isFinite(total) && Number.isFinite(nd) ? ev - total - nd : null;
    return pecrHead(snap) + `
        ${pecrMarketHtml(snap)}
        <section class="pecr-section"><h3>밸류에이션 배수 — 스냅샷 기준일 시세</h3>
            <div class="fin-cards">${['market_cap', 'ev', 'ev_to_ebitda', 'ev_to_sales', 'per', 'pbr'].map((k) => pecrCardHtml(snap, k)).join('')}</div></section>
        ${Number.isFinite(ev) ? `<section class="pecr-section"><h3>EV 브릿지</h3>
            <div class="co-table-wrap"><table class="co-table pecr-table"><tbody>
                <tr><td>보통주 시가총액</td><td>${coNum(cap)}</td></tr>
                <tr><td>+ 우선주 시가</td><td>${coNum(pref)}</td></tr>
                <tr><td>+ 순차입금</td><td>${coNum(nd)}</td></tr>
                <tr><td>+ 비지배지분(장부)</td><td>${coNum(nci)}</td></tr>
                <tr class="pecr-median"><td>= EV</td><td>${coNum(ev)}</td></tr>
            </tbody></table></div></section>` : ''}
        <section class="pecr-section"><h3>피어 비교</h3><div class="pecr-peers">${pecrPeersHtml(snap, data.pecrPeers)}</div></section>`;
};

const pecrBind = (out, data, rerender) => {
    out.querySelectorAll('[data-lbo]').forEach((el) => el.addEventListener('input', () => {
        const v = Number(el.value);
        if (!Number.isFinite(v)) return;
        PECR_LBO[el.dataset.lbo] = el.dataset.lbo === 'years' ? Math.max(1, Math.min(10, Math.round(v))) : v;
        const box = out.querySelector('.pecr-lbo-out');
        if (box) box.innerHTML = pecrLboResult(data.pecr);
    }));
    if (KFA_VIEW === 'deal' && data.pecr && !data.pecrPeers && !data.pecrPeersLoading) {
        data.pecrPeersLoading = true;
        pecrLoadPeers(data.pecr).then((peers) => {
            data.pecrPeers = peers;
            const box = out.querySelector('.pecr-peers');
            if (box && KFA_VIEW === 'deal') box.innerHTML = pecrPeersHtml(data.pecr, peers);
        });
    }
};
