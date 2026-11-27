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
// Snapshots carry their currency (KRW for DART, USD for SEC); every amount in
// these views goes through pecrNum so a US filer reads in dollars.
let PECR_CUR = 'KRW';
const pecrNum = (v, cur) => coNum(v, cur || PECR_CUR);
const pecrPx = (v) => (!Number.isFinite(v) ? '—' : PECR_CUR === 'USD'
    ? `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : `${Math.round(v).toLocaleString()}원`);

const pecrReason = (r) => {
    if (!r) return '';
    const hit = PECR_REASON_PREFIX.find(([p]) => r.startsWith(p));
    return hit ? hit[1] : (typeof kfaReason === 'function' ? kfaReason(r) : r);
};

const pecrFmt = (fmt, v) => {
    if (v === null || v === undefined || !Number.isFinite(v)) return '—';
    if (fmt === 'money') return pecrNum(v);
    if (fmt === 'pct') return `${(v * 100).toFixed(1)}%`;
    if (fmt === 'days') return `${Math.round(v)}일`;
    return `${v.toFixed(Math.abs(v) >= 100 ? 0 : 1)}배`;
};

// Strict card if it has a value, else its reported-basis fallback.
const pecrCard = (snap, key) => {
    const cards = snap?.pe_cr?.cards || {};
    const strict = cards[key];
    const liq = snap?.liquidity;
    if (strict && (strict.value === null || strict.value === undefined) && liq) {
        if (key === 'debt_due_within_1y' && (liq.latest || liq.fy)) {
            const x = liq.latest || liq.fy;
            return { ...strict, key, basis: 'reported', value: x.total, reason: null, period_end: x.period_end,
                definition: x.basis, parts: x.parts.map((q) => ({ input: q.key, label: q.account || q.label, value: q.value, period_end: x.period_end })) };
        }
        if (key === 'ccc_days' && liq.ccc_wide && !/^not_applicable/.test(strict.reason || '')) {
            const c = liq.ccc_wide;
            return { ...strict, key, basis: 'reported', value: c.value, reason: null, definition: c.basis,
                parts: [{ input: 'dso', label: `매출채권 회전일수 (${c.receivables_account || ''})`, value: null, days: c.dso },
                    { input: 'dio', label: '재고 회전일수', value: null, days: c.dio },
                    { input: 'dpo', label: `− 매입채무 회전일수 (${c.payables_account || ''})`, value: null, days: c.dpo }] };
        }
    }
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
        <div class="fin-card pecr-card co-clickable${card.value === null || card.value === undefined ? ' pecr-empty' : ''}" data-pecr-detail="${finEsc(key)}" title="클릭: 계산 근거와 분기별 변화">
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
    const cell = (c) => (c && c.value != null ? pecrNum(c.value) : '<span class="pecr-na" title="원표에 이 구간 경계가 없음">—</span>');
    return `
        <section class="pecr-section">
            <h3>자금조달 만기 (발행사 기준, 누적)</h3>
            <div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>상품</th><th>미상환 잔액</th>${cols.map((c) => `<th>${c.replace('d', '일').replace('1y', '1년')} 이내</th>`).join('')}</tr></thead>
                <tbody>${rows.map((r) => `<tr><td>${finEsc(LABEL[r.instrument] || r.instrument)}</td>
                    <td>${r.outstanding != null ? pecrNum(r.outstanding) : '—'}</td>
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
                Number.isFinite(last[k]) && Number.isFinite(last.rwa) ? ` · 완충 포함 기준 대비 여력 ${pecrNum((last[k] - m.with_conservation_buffer) * last.rwa)}` : '');
        }
    } else {
        const ratio = last[spec.ratio];
        const floor = (r.thresholds || [])[0];
        card(spec.title, pecrPct(ratio), `${finEsc(last.period_end)} 기준${r.transitional_applied ? ' · 경과조치 후' : ''}`,
            floor ? ` · ${finEsc(floor.label)} 기준 ${pecrPct(floor.ratio)}` : '');
        const pre = r.pre_transitional;
        if (pre && Number.isFinite(pre.ratio)) {
            card('경과조치 전 지급여력비율', pecrPct(pre.ratio), `${finEsc(pre.period_end)} 각주 공시. 경과조치(요구자본 인식 유예)를 빼면 이만큼입니다.`,
                Number.isFinite(pre.required) ? ` · 요구자본 ${pecrNum(pre.required)}` : '');
        }
        if (r.kind === 'kics' && Number.isFinite(last.available) && Number.isFinite(last.required)) {
            card('100% 기준 자본 여력', pecrNum(last.available - last.required),
                `가용자본 − 요구자본. 요구자본이 ${pecrPct(ratio - 1)} 늘어나도 100%를 지킵니다.`);
        }
        if (r.kind === 'ncr' && Number.isFinite(last.ncr_capital) && Number.isFinite(last.total_risk)) {
            card('잉여자본 (A − B)', pecrNum(last.ncr_capital - last.total_risk), '영업용순자본에서 총위험액을 뺀 값입니다.');
        }
        if (r.kind === 'credit_finance' && floor && Number.isFinite(last.adjusted_assets)) {
            card('경영지도비율 대비 여력', pecrNum((ratio - floor.ratio) * last.adjusted_assets), `조정총자산 × (현재 비율 − ${pecrPct(floor.ratio)}).`);
        }
    }
    for (const [k, label] of spec.amounts) if (Number.isFinite(last[k])) card(label, pecrNum(last[k]), `${last.period_end} 기준`);
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
                    ${spec.amounts.filter(([k]) => series.some((q) => Number.isFinite(q[k]))).map(([k]) => `<td>${pecrNum(p[k])}</td>`).join('')}
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
            <div><span>진입 EV</span><b>${pecrNum(r.ev0)}</b></div>
            <div><span>차입</span><b>${pecrNum(r.debt0)}</b></div>
            <div><span>지분 투자</span><b>${pecrNum(r.eq0)}</b></div>
            <div><span>${PECR_LBO.years}년 후 지분가치</span><b>${pecrNum(r.eqN)}</b></div>
            <div><span>MOIC</span><b>${r.moic.toFixed(2)}배</b></div>
            <div><span>IRR</span><b>${r.irr == null ? '—' : `${(r.irr * 100).toFixed(1)}%`}</b></div>
        </div>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>연차</th><th>EBITDA</th><th>이자</th><th>상환 재원</th><th>차입 잔액</th><th>차입/EBITDA</th></tr></thead>
            <tbody>${r.rows.map((x) => `<tr><td>${x.t}년</td><td>${pecrNum(x.ebitda)}</td><td>${pecrNum(x.interest)}</td>
                <td>${pecrNum(x.free)}</td><td>${pecrNum(x.debt)}</td><td>${x.lev.toFixed(1)}배</td></tr>`).join('')}</tbody>
        </table></div>
        <p class="fin-note">수익 분해: EBITDA 성장 ${pecrNum(r.bridge.growth)} · 배수 변화 ${pecrNum(r.bridge.multiple)} · 부채 상환·현금 ${pecrNum(r.bridge.delever)}.
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
    const capText = `${pecrNum(m.equity)}`;
    const row = (label, value, formula, basis, plain) => `<tr${/^EV/.test(label) ? ' class="co-clickable" data-pecr-detail="live_ev" title="클릭: EV 계산 근거와 분기별 변화"' : ''}><td><b>${finEsc(label)}</b>${/^EV/.test(label) ? ' <span class="pecr-badge">근거 ▸</span>' : ''}<br><span class="fin-note">${finEsc(plain)}</span></td>
        <td class="pecr-num">${value}</td><td>${formula}</td><td>${finEsc(basis)}</td></tr>`;
    const x = (v, loss) => (loss ? '적자' : pecrFmt('x', v));
    const rows = [
        row('PER', x(m.per_ltm, m.loss_ltm), `${capText} ÷ 지배주주 순이익 ${pecrNum(m.niL)}`, ltmLabel || '—', '시가총액 ÷ 순이익. 몇 년 치 이익에 거래되는지.'),
        row('PER (연간)', x(m.per_fy, m.loss_fy), `${capText} ÷ ${pecrNum(m.niF)}`, fyLabel, '직전 사업연도 순이익 기준.'),
        row('PBR', pecrFmt('x', m.pbr), `${capText} ÷ 지배주주 자본 ${pecrNum(m.parentEq)}`, `${m.latest.period_end} 재무상태표`, '시가총액 ÷ 장부상 자본.'),
    ];
    if (!m.financial) {
        rows.push(
            row('PSR', pecrFmt('x', m.psr), `${capText} ÷ 매출 ${pecrNum(m.sales)}`, ltmLabel || fyLabel, '시가총액 ÷ 매출. 적자 기업 비교에 씁니다.'),
            row('EV/EBITDA', pecrFmt('x', m.ev_to_ebitda), `EV ${pecrNum(m.ev)} ÷ EBITDA ${pecrNum(m.fy.ebitda)}`, fyLabel,
                'EV = 시가총액 + 순차입금 + 비지배지분. 부채 구조가 달라도 비교됩니다.'),
            row('EV/매출', pecrFmt('x', m.ev_to_sales), `EV ${pecrNum(m.ev)} ÷ 매출 ${pecrNum(m.sales)}`, ltmLabel || fyLabel, ''),
            row('P/FCF', m.fy.fcf > 0 ? pecrFmt('x', m.p_fcf) : '음(−) FCF', `${capText} ÷ FCF ${pecrNum(m.fy.fcf)}`, fyLabel,
                `잉여현금흐름 수익률 ${Number.isFinite(m.fcf_yield) ? (m.fcf_yield * 100).toFixed(1) + '%' : '—'}.`),
        );
    }
    const ref = q.naver_reference || {};
    const refTxt = [['per', 'PER'], ['pbr', 'PBR'], ['dividendYieldRatio', '배당수익률']]
        .filter(([k]) => ref[k]).map(([k, l]) => `${l} ${ref[k].value}${k === 'dividendYieldRatio' ? '%' : '배'}${ref[k].period ? ` (${finEsc(ref[k].period)})` : ''}`).join(' · ');
    const pref = q.preferred ? ` + 우선주 ${pecrNum(m.prefCap)} (${finEsc(q.preferred.name)} ${pecrPx(q.preferred.price)})` : '';
    return `
        <section class="pecr-section"><h3>시장 배수 — 시가총액 ÷ 공시 분모</h3>
            <p class="fin-note">시가총액 <b>${capText}</b> = 보통주 ${pecrNum(q.market_cap)} (${finEsc(q.name)} ${pecrPx(q.price)}, ${finEsc(at)} 종가)${pref}.
                ${m.prefMissing ? '<b>우선주가 있으나 상장 시세가 없어 보통주만 반영했습니다.</b>' : ''}</p>
            <div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>지표</th><th>값</th><th>계산</th><th>분모 기준</th></tr></thead>
                <tbody>${rows.join('')}</tbody></table></div>
            <p class="fin-note">분자: Naver 금융 시가총액(상장주식수 × 종가, 자사주 포함), 매 영업일 장 마감 후 갱신. 분모: ${snap.source === 'SEC' ? 'SEC 10-K·10-Q (companyfacts)' : 'OpenDART 공시 재무제표'}
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
        .filter(([id, v]) => id !== snap.corp_code && !v.financial && v.industry === snap.pe_cr?.industry
            && (v.market || 'KR') === (snap.market || 'KR'))
        .map(([id]) => id).slice(0, 8);
    const loaded = await Promise.all(ids.map((id) => loadFirstJson(finDataPaths(`kfa_pecr/${id}_v1.json`))));
    return loaded.filter(Boolean);
};

// --- 업종 핵심 지표 (investor_metrics.industry; 종합상사 / 광업·제련) ---------
const KIT_TITLE = { trading_house: '종합상사', mining_smelting: '광업·비철 제련', conglomerate: '복합기업' };
const KIT_FMT = { dso: 'days', dio: 'days', impairment: 'money' };
const kitIndustryHtml = (snap) => {
    const ind = snap.investor_metrics?.industry;
    if (!ind || !ind.history) return '';
    const years = Object.keys(ind.history).sort().slice(-5);
    const keys = Object.keys(ind.labels).filter((k) => years.some((y) => Number.isFinite(ind.history[y][k])));
    const f = (k, v) => (!Number.isFinite(v) ? '—' : KIT_FMT[k] === 'days' ? `${Math.round(v)}일`
        : KIT_FMT[k] === 'money' ? pecrNum(v) : `${(v * 100).toFixed(1)}%`);
    let extra = '';
    if (ind.kit === 'trading_house') {
        const seg = (snap.segments?.breakdowns || []).find((b) => b.kind === 'segment' && b.has_operating_income);
        const rows = (seg?.rows || []).filter((r) => Number.isFinite(r.op));
        const opSum = rows.reduce((a, r) => a + Math.max(r.op, 0), 0);
        if (rows.length >= 2 && opSum > 0) {
            extra = `<div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>부문</th><th>매출</th><th>영업이익</th><th>이익률</th><th>이익 기여</th></tr></thead><tbody>
                ${rows.map((r) => `<tr><td>${finEsc(r.label)}</td><td class="pecr-num">${pecrNum(r.revenue)}</td><td class="pecr-num">${pecrNum(r.op)}</td>
                    <td class="pecr-num">${Number.isFinite(r.margin) ? `${(r.margin * 100).toFixed(1)}%` : '—'}</td>
                    <td class="pecr-num">${r.op > 0 ? `${(r.op / opSum * 100).toFixed(0)}%` : '—'}</td></tr>`).join('')}
                </tbody></table></div>
                <p class="fin-note">매출은 트레이딩이 크지만 이익은 자원·에너지·물류가 버는 경우가 많습니다. 이익 기여가 매출 비중과 얼마나 다른지 보세요.</p>`;
        } else if (snap.segments?.breakdowns?.length) {
            extra = '<p class="fin-note">사업부문별 영업이익은 주석에 태그되지 않아 매출 비중만 아래 "사업부문" 표에 있습니다.</p>';
        }
    }
    if (ind.kit === 'mining_smelting') {
        const prov = (snap.note_items?.provisions?.classes || []).find((c) => /Decommission|Restoration|Rehabilitation/i.test(c.member) || /복구/.test(c.label));
        if (prov) extra = `<p class="fin-note">복구충당부채 ${pecrNum(prov.value)} — 광산 폐쇄·원상복구 의무로 EV에 더할 부채성 항목입니다.</p>`;
    }
    const plain = {
        trading_house: '박마진 사업이라 매출보다 매출총이익률·이익 구성을, 무역금융 때문에 운전자본 일수를 봅니다. 지분법이익 비중이 크면 자원 투자 실적이 이익을 좌우합니다.',
        mining_smelting: '재투자율(설비투자 ÷ 감가상각)이 100%를 밑돌면 광산·설비가 닳는 속도보다 덜 투자하는 중입니다. EBITDA 마진은 원자재 가격에 따라 크게 출렁이니 여러 해를 함께 보세요.',
    }[ind.kit];
    return `<section class="pecr-section"><h3>업종 핵심 지표 — ${finEsc(KIT_TITLE[ind.kit] || ind.kit)}</h3>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>지표</th>${years.map((y) => `<th>FY${y}</th>`).join('')}</tr></thead>
            <tbody>${keys.map((k) => `<tr><td>${finEsc(ind.labels[k])}</td>${years.map((y) => `<td class="pecr-num">${f(k, ind.history[y][k])}</td>`).join('')}</tr>`).join('')}</tbody>
        </table></div>
        ${extra}
        <p class="fin-note">${finEsc(plain)}</p>
    </section>`;
};

// --- 주석 항목 (snapshot.note_items; dart_kfa/note_items.py) ------------------
const noteItemsHtml = (snap) => {
    const n = snap.note_items;
    if (!n) return '';
    const v = (k) => n[k]?.value;
    const pct = (x) => (Number.isFinite(x) ? `${(x * 100).toFixed(1)}%` : '—');
    const cards = [
        ['연구개발비 (비용)', pecrNum(v('rd_expensed')), Number.isFinite(v('rd_to_sales')) ? `자산화분 포함 매출 대비 ${pct(v('rd_to_sales'))}.` : '손익계산서에 비용으로 처리한 연구개발비.'],
        ['개발비 자산화', pecrNum(v('rd_capitalised')), Number.isFinite(v('capitalisation_ratio'))
            ? `연구개발 지출의 ${pct(v('capitalisation_ratio'))}를 비용 대신 자산으로 잡았습니다. 높을수록 영업이익이 실제 지출보다 좋아 보입니다.` : '자산화한 개발비 공시 없음.'],
        ['주식보상비용', pecrNum(v('sbc')), Number.isFinite(v('sbc_to_sales')) ? `매출 대비 ${pct(v('sbc_to_sales'))}. 현금은 안 나가지만 주주 몫을 나눠 주는 비용입니다.` : '현금 지출 없는 비용 — 희석으로 돌아옵니다.'],
        ['재고자산 평가손실', pecrNum(v('inventory_writedown')), Number.isFinite(v('inventory_writedown_reversal')) ? `평가손실 환입 ${pecrNum(v('inventory_writedown_reversal'))}.` : '재고 가치 하락으로 비용 처리한 금액.'],
    ].filter(([, val]) => val !== '—');
    const p = n.provisions;
    return `<section class="pecr-section"><h3>주석 항목 — 연구개발·주식보상·충당부채 (FY${finEsc(String(n.fiscal_year_end || '').slice(0, 4))})</h3>
        ${cards.length ? `<div class="fin-cards">${cards.map(([t, val, plain]) => `<div class="fin-card pecr-card"><span class="fin-card-title">${t}</span>
            <span class="fin-card-value">${val}</span><p class="fin-card-plain">${plain}</p></div>`).join('')}</div>` : ''}
        ${p && (p.classes || []).length ? `<div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>충당부채 종류</th><th>기말 잔액</th><th>비중</th></tr></thead><tbody>
            ${p.classes.map((c) => `<tr><td>${finEsc(c.label)}</td><td class="pecr-num">${pecrNum(c.value)}</td>
                <td class="pecr-num">${p.classes_sum ? pct(c.value / p.classes_sum) : '—'}</td></tr>`).join('')}
            <tr class="pecr-median"><td>합계${Number.isFinite(p.total) && p.classes_sum && Math.abs(p.total - p.classes_sum) > 0.01 * p.total ? ` (주석 총계 ${pecrNum(p.total)})` : ''}</td>
                <td class="pecr-num">${pecrNum(p.classes_sum)}</td><td></td></tr></tbody></table></div>
            <p class="fin-note">판매보증·공사손실(손실부담계약)·소송 충당부채가 매출보다 빨리 늘면 품질·원가 문제의 신호입니다. 조정 EV의 "보수적" 줄에 이 합계가 들어갑니다.</p>` : ''}
        <p class="fin-note">출처: FY 사업보고서 원본 XBRL 주석(접수 ${finEsc(n.receipt || '—')}). 이름이 회사마다 다른 태그는 접두어로 찾고, 맥락이 엇갈리는 값은 뺐습니다.</p>
    </section>`;
};

// --- 업권 지표 (snapshot.financial_kpis; dart_kfa/financial_kpis.py) ---------
const FIN_KIND = { basel: '은행(지주)', kics: '보험', ncr: '증권', credit_finance: '카드·캐피탈' };
const FIN_LABEL = {
    roe: ['ROE', 'pct'], roa: ['ROA', 'pct'], leverage: ['레버리지', 'x'],
    net_interest_income: ['순이자이익', 'money'], net_fee_income: ['순수수료이익', 'money'], nii_to_assets: ['순이자이익 ÷ 총자산', 'pct2'],
    cost_income: ['비용효율(CIR)', 'pct'], credit_cost: ['대손비용률', 'pct2'], loans_to_deposits: ['대출 ÷ 예수부채', 'pct'],
    loan_growth: ['대출 성장률', 'pct'], insurance_revenue: ['보험수익', 'money'], insurance_result: ['보험서비스결과', 'money'],
    insurance_margin: ['보험손익률', 'pct'], investment_result: ['투자손익', 'money'], insurance_share_of_profit: ['보험손익 비중', 'pct'],
    operating_revenue: ['영업수익', 'money'], credit_cost_to_revenue: ['대손비용 ÷ 영업수익', 'pct'],
    credit_cost_to_assets: ['대손비용 ÷ 총자산', 'pct2'], funding_cost: ['이자비용 ÷ 총자산', 'pct2'],
};
const finFmt = (fmt, v) => (!Number.isFinite(v) ? '—' : fmt === 'money' ? pecrNum(v) : fmt === 'x' ? `${v.toFixed(1)}배`
    : `${(v * 100).toFixed(fmt === 'pct2' ? 2 : 1)}%`);
const financialKpisHtml = (snap) => {
    const f = snap.financial_kpis;
    if (!f) return '';
    const comp = Object.entries(f.computed || {}).filter(([k]) => FIN_LABEL[k]);
    const rep = Object.entries(f.reported || {});
    return `<section class="pecr-section"><h3>업권 지표 — ${finEsc(FIN_KIND[f.kind] || f.kind)}</h3>
        ${rep.length ? `<div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>공시 지표</th><th>값</th><th>추이</th><th>출처 표</th></tr></thead><tbody>
            ${rep.map(([, v]) => `<tr><td><b>${finEsc(v.label)}</b>${v.subsidiary ? ' <span class="pecr-badge">주요 종속회사</span>' : ''}</td>
                <td class="pecr-num">${(v.value * 100).toFixed(2)}%</td>
                <td>${(v.series || []).map(([p, x]) => `${finEsc(p)} ${(x * 100).toFixed(2)}%`).join(' · ')}</td>
                <td class="fin-note">${finEsc(v.source)}</td></tr>`).join('')}
            </tbody></table></div>
            <p class="fin-note">${finEsc(f.reported_period_end || '')} 정기보고서(접수 ${finEsc(f.reported_receipt || '—')})의 표에서 그대로 읽은 값입니다. 외화 단위 표(해외 법인)는 제외했고,
                "주요 종속회사" 표시는 지주회사 연결이 아니라 핵심 자회사(예: 은행) 기준입니다.</p>` : ''}
        <div class="fin-cards">${comp.map(([k, v]) => `<div class="fin-card pecr-card"><span class="fin-card-title">${finEsc(FIN_LABEL[k][0])}</span>
            <span class="fin-card-value">${finFmt(FIN_LABEL[k][1], v.value)}</span><p class="fin-card-plain">${finEsc(v.basis || '')}</p></div>`).join('')}</div>
        <p class="fin-note">카드 아래 값은 FY${finEsc(f.fiscal_year || '')} 연결 재무제표 본문으로 계산했습니다. "대용"이라고 쓴 값은 감독기준 산식과 분모가 달라 공시 지표와 차이가 납니다.
            ${f.kind === 'kics' ? '보험계약마진(CSM) 잔액은 회사마다 공시 양식이 달라 아직 자동 추출하지 않습니다.' : ''}</p>
    </section>`;
};

// --- 사업부문·제품·지역 (snapshot.segments; dart_kfa/segments.py) ---------------
const SEG_CHECK = { segment_total: '보고서의 부문 합계 행', income_statement: '손익계산서 매출(조정 항목 반영)',
    income_statement_external: '손익계산서 매출(부문 매출이 이미 외부 매출 기준)' };
const segPct = (v, sign = false) => (Number.isFinite(v) ? `${sign && v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%` : '—');
const segTableHtml = (b, fy) => {
    const op = b.has_operating_income;
    const assets = b.has_assets && op;
    const opSum = op ? b.rows.reduce((a, r) => a + Math.max(r.op || 0, 0), 0) : 0;
    const adj = Object.entries(b.reconciling_items || {}).filter(([, v]) => Number.isFinite(v) && v !== 0);
    return `<div class="co-table-wrap"><table class="co-table pecr-table">
        <thead><tr><th>${finEsc(b.label)}</th><th>매출 FY${fy}</th><th>비중</th><th>전년비</th>${op ? '<th>영업이익</th><th>이익률</th><th>이익 전년비</th><th>이익 기여</th>' : ''}${assets ? '<th>부문 자산</th><th>자산수익률</th><th>EBITDA 마진</th>' : ''}</tr></thead>
        <tbody>${b.rows.map((r) => `<tr><td>${finEsc(r.label)}</td><td class="pecr-num">${pecrNum(r.revenue)}</td><td class="pecr-num">${segPct(r.share)}</td>
            <td class="pecr-num">${segPct(r.revenue_yoy, true)}</td>${op ? `<td class="pecr-num">${pecrNum(r.op)}</td><td class="pecr-num">${segPct(r.margin)}</td>
            <td class="pecr-num">${segPct(r.op_yoy, true)}</td><td class="pecr-num">${opSum > 0 && r.op > 0 ? segPct(r.op / opSum) : '—'}</td>` : ''}${assets
                ? `<td class="pecr-num">${pecrNum(r.assets)}</td><td class="pecr-num">${segPct(r.roa)}</td><td class="pecr-num">${segPct(r.ebitda_margin)}</td>` : ''}</tr>`).join('')}
        ${adj.map(([k, v]) => `<tr class="pecr-median"><td>${finEsc(/Elimination|제거/.test(k) ? '부문간 거래 제거' : /Reconcil|조정/.test(k) ? '연결 조정' : k)}</td><td class="pecr-num">${pecrNum(v)}</td><td colspan="${(op ? 6 : 2) + (assets ? 3 : 0)}"></td></tr>`).join('')}
        </tbody></table></div>`;
};
const segHistoryHtml = (snap) => {
    const h = snap.segments?.history;
    if (!h) return '';
    const labels = Object.keys(h).filter((k) => !/공통|합계/.test(k));
    const years = [...new Set(labels.flatMap((k) => Object.keys(h[k])))].sort().slice(-5);
    if (years.length < 2 || !labels.length) return '';
    const cell = (k, y, m) => pecrNum(h[k][y]?.[m]);
    return `<div class="co-table-wrap"><table class="co-table pecr-table">
        <thead><tr><th>부문</th>${years.map((y) => `<th>FY${y}</th>`).join('')}</tr></thead><tbody>
        ${labels.map((k) => `<tr><td><b>${finEsc(k)}</b> 매출</td>${years.map((y) => `<td class="pecr-num">${cell(k, y, 'revenue')}</td>`).join('')}</tr>
            ${years.some((y) => Number.isFinite(h[k][y]?.op)) ? `<tr><td class="fin-note">　영업이익</td>${years.map((y) => `<td class="pecr-num">${cell(k, y, 'op')}</td>`).join('')}</tr>` : ''}`).join('')}
        </tbody></table></div>
        <p class="fin-note">사업보고서 3개(각각 당기·전기)의 영업부문 주석을 부문 이름으로 이어 붙였습니다. 부문 매출은 부문간 거래 제거 전 기준일 수 있습니다.</p>`;
};

// 복합기업(삼성물산 등): 업종이 다른 사업이 한 회사에 묶여 있어 부문별로 나눠 본다.
const conglomerateHtml = (snap) => {
    if (snap.pe_cr?.industry !== 'conglomerate') return '';
    const seg = (snap.segments?.breakdowns || []).find((b) => b.kind === 'segment' && b.reconciles && b.has_operating_income);
    if (!seg) return '';
    const fy = String(snap.segments.fiscal_year_end || '').slice(0, 4);
    const bl = snap.order_backlog;
    const con = seg.rows.find((r) => /건설/.test(r.label));
    const backlogNote = bl && con?.revenue
        ? `<p class="fin-note"><b>건설 부문 수주잔고</b> ${pecrNum(bl.backlog)} — 건설 매출 ${pecrNum(con.revenue)}의 ${(bl.backlog / con.revenue).toFixed(1)}년치 (${finEsc(bl.period_end)} 기준).</p>` : '';
    return `<section class="pecr-section"><h3>부문별로 분리해 보기 — 복합기업 (FY${finEsc(fy)})</h3>
        <p class="fin-note">업종이 다른 사업이 한 회사에 묶여 있어 연결 합산 비율(이익률·회전율)은 평균이라 의미가 약합니다. 부문마다 매출·이익·자산수익률을 따로 보고,
            가치도 부문별로 매겨 더하는 방식(합산가치, SOTP)이 맞습니다.</p>
        ${segTableHtml(seg, fy)}${backlogNote}${segHistoryHtml(snap)}
    </section>`;
};

const segmentsHtml = (snap) => {
    const seg = snap.segments;
    if (!seg || !(seg.breakdowns || []).length) return '';
    const fy = String(seg.fiscal_year_end || '').slice(0, 4);
    const ok = seg.breakdowns.filter((b) => b.reconciles);
    const covered = new Set(ok.map((b) => b.kind));
    const shown = [...ok.filter((b, i) => ok.findIndex((x) => x.kind === b.kind) === i),
        // An unreconciled table is shown only if it covers 50-110% of sales (a partial
        // product list); one that is off by more is mis-tagged and hidden.
        ...seg.breakdowns.filter((b) => !b.reconciles && !covered.has(b.kind) && b.sum_revenue && b.face_revenue
            && b.sum_revenue / b.face_revenue >= 0.5 && b.sum_revenue / b.face_revenue <= 1.1 && (covered.add(b.kind) || true))];
    if (!shown.length) return '';
    return `<section class="pecr-section"><h3>사업부문·제품·지역별 실적 — FY${finEsc(fy)}</h3>
        ${shown.map((b) => `${segTableHtml(b, fy)}<p class="fin-note">${b.reconciles
            ? `항목의 합이 ${finEsc(SEG_CHECK[b.reconciled_against] || '총매출')}과 맞습니다(±1.5%).`
            : `<b class="pecr-flag">일부 항목만 공시 — 참고용.</b> 항목 합 ${pecrNum(b.sum_revenue)}, 손익계산서 매출 ${pecrNum(b.face_revenue)}의 ${Math.round(b.sum_revenue / b.face_revenue * 100)}%.`}</p>`).join('')}
        ${snap.pe_cr?.industry === 'conglomerate' ? '' : segHistoryHtml(snap)}
        <p class="fin-note">출처: FY${finEsc(fy)} 사업보고서 원본 XBRL의 영업부문·수익 구분 주석(접수 ${finEsc(seg.receipt || '—')}). 부문 매출은 부문간 거래 제거 전 금액일 수 있습니다.
            제품별 단가·출하량(예: HBM 비중)은 공시되지 않습니다.</p></section>`;
};

const backlogHtml = (snap) => {
    const b = snap.order_backlog;
    if (!b) return '';
    const rf = [['opening', '기초'], ['new_orders', '신규 수주'], ['contract_total', '수주 총액'], ['delivered', '매출 인식·납품'], ['backlog', '수주잔고']]
        .filter(([k]) => Number.isFinite(b[k]));
    const years = b.backlog_to_revenue;
    return `<section class="pecr-section"><h3>${finEsc(b.label || '수주잔고')} — ${finEsc(b.period_end)} 기준</h3>
        <div class="fin-cards">
            <div class="fin-card pecr-card"><span class="fin-card-title">수주잔고</span><span class="fin-card-value">${pecrNum(b.backlog)}</span>
                <p class="fin-card-plain">계약했지만 아직 매출로 잡지 않은 금액. 앞으로 들어올 매출의 바닥.</p></div>
            ${Number.isFinite(years) && years >= 0.25 ? `<div class="fin-card pecr-card"><span class="fin-card-title">수주잔고 ÷ 매출</span>
                <span class="fin-card-value">${years.toFixed(1)}년치</span>
                <p class="fin-card-plain">지금 매출 속도(${finEsc(b.revenue_basis || '')})로 잔고를 소화하는 데 걸리는 기간.</p></div>` : ''}
            ${Number.isFinite(b.book_to_bill) ? `<div class="fin-card pecr-card"><span class="fin-card-title">수주/매출 (Book-to-bill)</span>
                <span class="fin-card-value">${b.book_to_bill.toFixed(2)}배</span>
                <p class="fin-card-plain">올해 들어온 신규 수주 ÷ 같은 기간 매출 인식액. 1보다 크면 잔고가 늘고 있습니다.</p></div>` : ''}
        </div>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>항목</th>${rf.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead><tbody>
            ${(b.items || []).map((i) => `<tr><td>${finEsc(i.item)}</td>${rf.map(([k]) => `<td class="pecr-num">${pecrNum(i[k])}</td>`).join('')}</tr>`).join('')}
            <tr class="pecr-median"><td>합계</td>${rf.map(([k]) => `<td class="pecr-num">${pecrNum(b[k])}</td>`).join('')}</tr>
        </tbody></table></div>
        <p class="fin-note">${b.parts ? `회사별 표 합산: ${b.parts.map((p) => `${finEsc(p.part || '기타')} ${pecrNum(p.backlog)}`).join(' · ')}. ` : ''}
            ${b.item_count > (b.items || []).length ? `상위 ${(b.items || []).length}개 항목만 표시(전체 ${b.item_count}개). ` : ''}
            ${b.roll_forward_ok ? '합계 행이 기초 + 신규 − 매출 = 잔고(또는 총액 − 납품 = 잔고)로 맞는 것을 확인했습니다. ' : ''}
            ${b.source ? `출처: ${finEsc(b.source)}. 잔여 수행의무는 계약했지만 아직 수익으로 인식하지 않은 금액으로, 한국 공시의 수주잔고와 같은 개념입니다.`
                : `신규 수주는 연초부터 누적이며 환율 변동·계약 변경이 섞일 수 있습니다. 출처: ${finEsc(b.report || '')} 보고서 "매출 및 수주상황"(접수 ${finEsc(b.receipt || '—')}).`}</p>
    </section>`;
};

// --- 투자지표 (investor_metrics in the snapshot; dart_kfa/investor_metrics.py) ---
const INV_REASON = {
    'not_applicable:financial': '금융회사 미적용', turnaround: '흑자 전환', 'not_meaningful:base_nonpositive': '기준연도 적자',
    'not_meaningful:nonpositive_endpoint': '적자 연도 포함', 'not_meaningful:net_loss': '순손실',
    'not_meaningful:net_cash_exceeds_capital': '순현금이 자본보다 큼', 'missing:invested_capital': '차입금 계정 미확인',
};
const invReason = (r) => (r ? (INV_REASON[r] || (r.startsWith('missing') ? '자료 없음' : pecrReason(r))) : '');
const invPct = (m, d = 1) => (m && Number.isFinite(m.value) ? `${(m.value * 100).toFixed(d)}%` : `<span class="pecr-na">${finEsc(invReason(m?.reason) || '—')}</span>`);
const invX = (v, d = 2) => (Number.isFinite(v) ? `${v.toFixed(d)}` : '—');
const invZone = { safe: ['pecr-sig-off', '안전'], grey: ['', '회색'], distress: ['pecr-sig-on', '부실 위험'] };

const invGrowthHtml = (inv, live) => {
    const g = inv.growth || {};
    const years = (inv.years || []).slice(-5);
    const keys = ['revenue', 'op', 'parent_income', 'eps'].filter((k) => g[k] && !(inv.financial && (k === 'revenue' || k === 'op')));
    const cell = (k, y) => { const v = g[k].history?.[y]; return k === 'eps' ? pecrPx(v) : pecrNum(v); };
    const eps = g.eps?.cagr_3y?.value;
    const peg = live && Number.isFinite(live.per_ltm) && !live.loss_ltm && eps > 0 ? live.per_ltm / (eps * 100) : null;
    return `<section class="pecr-section"><h3>성장 — 최근 5개 사업연도</h3>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>항목</th>${years.map((y) => `<th>FY${y}</th>`).join('')}<th>전년비</th><th>3년 연평균</th></tr></thead>
            <tbody>${keys.map((k) => `<tr><td>${finEsc(g[k].label)}</td>${years.map((y) => `<td class="pecr-num">${cell(k, y)}</td>`).join('')}
                <td>${invPct(g[k].yoy)}</td><td>${invPct(g[k].cagr_3y)}</td></tr>`).join('')}</tbody></table></div>
        <p class="fin-note">사업보고서 3개(당기·전기·전전기씩)로 5년을 잇고, 두 보고서가 같은 연도를 보이면 최신 보고서(재작성 반영) 값을 씁니다.
            ${peg !== null ? `<b>PEG ${invX(peg)}</b> = PER(최근 4분기) ${invX(live.per_ltm, 1)} ÷ EPS 3년 연평균 성장률 ${(eps * 100).toFixed(1)}. 1 미만이면 성장 대비 싸다는 뜻으로 흔히 읽습니다.`
                : 'PEG는 PER과 EPS 3년 성장률이 모두 양수일 때만 계산합니다.'}</p></section>`;
};

const invReturnsHtml = (inv) => {
    const r = inv.returns || {};
    if (inv.financial) return '';
    const roic = r.roic || {}, d = r.dupont || {};
    const tax = roic.tax_basis === 'statutory_top_rate_assumed' ? '법정 최고세율 26.4% 가정(유효세율 산출 불가)'
        : roic.tax_basis === 'effective_3y_pooled' ? `3년 합산 유효세율 ${(roic.tax_rate * 100).toFixed(1)}%` : Number.isFinite(roic.tax_rate) ? `유효세율 ${(roic.tax_rate * 100).toFixed(1)}%` : '';
    return `<section class="pecr-section"><h3>자본 효율 — ROIC·듀퐁 분해</h3>
        <div class="fin-cards">
            <div class="fin-card pecr-card"><span class="fin-card-title">ROIC (세후)</span><span class="fin-card-value">${invPct(roic)}</span>
                <p class="fin-card-plain">영업이익 × (1 − 세율) ÷ 투하자본. 자본비용(대략 8~10%)보다 높으면 성장이 가치를 만듭니다.${tax ? ` ${finEsc(tax)}.` : ''}
                ${Number.isFinite(roic.invested_capital) ? ` 투하자본 ${pecrNum(roic.invested_capital)} (자본 + 차입금·사채·리스 − 현금·단기금융상품, 기초·기말 평균).` : ''}</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">ROIC (세전)</span><span class="fin-card-value">${invPct(r.roic_pretax)}</span>
                <p class="fin-card-plain">세율 영향을 뺀 영업이익 ÷ 투하자본. 세금 혜택 연도 비교용.</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">ROE (듀퐁)</span><span class="fin-card-value">${invPct(d)}</span>
                <p class="fin-card-plain">${Number.isFinite(d.value) ? `순이익률 ${(d.net_margin * 100).toFixed(1)}% × 총자산회전율 ${invX(d.asset_turnover)}회 × 자기자본승수 ${invX(d.equity_multiplier)}배.
                    ROE가 마진에서 오는지, 회전에서 오는지, 빚(레버리지)에서 오는지 나눠 봅니다.` : finEsc(invReason(d.reason))}</p></div>
        </div></section>`;
};

const invQualityHtml = (inv) => {
    if (inv.financial) return '';
    const q = inv.quality || {};
    const times = (m) => (Number.isFinite(m?.value) ? `${invX(m.value)}배` : `<span class="pecr-na">${finEsc(invReason(m?.reason))}</span>`);
    const row = (label, m, plain, flag, fmt = invPct) => `<tr><td><b>${finEsc(label)}</b><br><span class="fin-note">${finEsc(plain)}</span></td>
        <td class="pecr-num">${fmt(m)}</td><td>${flag ? '<b class="pecr-flag">확인 필요</b>' : ''}</td></tr>`;
    const pp = (m) => (Number.isFinite(m?.value) ? `${m.value >= 0 ? '+' : ''}${(m.value * 100).toFixed(1)}%p` : `<span class="pecr-na">${finEsc(invReason(m?.reason))}</span>`);
    const acc = q.accruals_ratio?.value, rec = q.receivables_vs_sales?.value, inv_ = q.inventory_vs_sales?.value, cfo = q.cfo_to_net_income?.value;
    return `<section class="pecr-section"><h3>이익의 질</h3>
        <div class="co-table-wrap"><table class="co-table pecr-table"><tbody>
            ${row('발생액 비율', q.accruals_ratio, '(순이익 − 영업현금흐름) ÷ 평균 총자산. 높을수록 이익이 현금 없이 장부상으로만 늘어난 것.', acc > 0.1)}
            ${row('영업현금흐름 ÷ 순이익', q.cfo_to_net_income, '1 이상이면 이익이 현금으로 들어오고 있다는 뜻.', Number.isFinite(cfo) && cfo < 0.8, times)}
            ${row('매출채권 증가율 − 매출 증가율', q.receivables_vs_sales, '+10%p 이상이면 외상 매출로 실적을 끌어올렸는지 확인.', rec > 0.1, pp)}
            ${row('재고 증가율 − 매출 증가율', q.inventory_vs_sales, '+10%p 이상이면 안 팔린 재고가 쌓이는지 확인.', inv_ > 0.1, pp)}
        </tbody></table></div></section>`;
};

const invScoresHtml = (inv, live) => {
    if (inv.financial) return '';
    const d = inv.distress || {};
    const z = d.z_double_prime || {}, zi = d.z_inputs, f = d.piotroski || {};
    const zone = invZone[z.zone] || ['', ''];
    let zMarket = null;
    if (zi && live && Number.isFinite(zi.x5) && zi.total_liabilities > 0) {
        zMarket = 1.2 * zi.x1 + 1.4 * zi.x2 + 3.3 * zi.x3 + 0.6 * (live.equity / zi.total_liabilities) + 1.0 * zi.x5;
    }
    const zmZone = zMarket === null ? null : zMarket > 2.99 ? invZone.safe : zMarket >= 1.81 ? invZone.grey : invZone.distress;
    const hist = Object.entries(z.history || {}).map(([y, h]) => `FY${y} ${invX(h.z)}`).join(' · ');
    const tests = (f.tests || []).map((t) => `<li class="${t.pass === true ? 'pecr-sig-off' : t.pass === false ? 'pecr-sig-on' : ''}">
        <span class="pecr-sig-dot"></span><span>${finEsc(t.label)}</span><span class="pecr-sig-word">${t.pass === true ? '충족' : t.pass === false ? '미충족' : '자료 없음'}</span></li>`).join('');
    return `<section class="pecr-section"><h3>재무 건전성 점수 — Altman Z · Piotroski F</h3>
        <div class="fin-cards">
            <div class="fin-card pecr-card"><span class="fin-card-title">Altman Z'' (장부가)</span>
                <span class="fin-card-value">${Number.isFinite(z.value) ? invX(z.value) : '—'} <small class="${zone[0]}">${finEsc(zone[1])}</small></span>
                <p class="fin-card-plain">운전자본·이익잉여금·영업이익·자본을 총자산·부채와 비교한 부도 예측 점수(비제조·신흥시장용). 2.6 초과 안전, 1.1 미만 부실 위험.
                    ${hist ? `<br>${finEsc(hist)}` : finEsc(invReason(z.reason))}</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">Altman Z (시가총액)</span>
                <span class="fin-card-value">${zMarket === null ? '—' : invX(zMarket)} ${zmZone ? `<small class="${zmZone[0]}">${finEsc(zmZone[1])}</small>` : ''}</span>
                <p class="fin-card-plain">원조 제조업 모형. 자본 항목에 오늘 시가총액을 씁니다. 2.99 초과 안전, 1.81 미만 부실 위험.${zMarket === null ? ' (상장사 일별 시세 필요)' : ''}</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">Piotroski F</span>
                <span class="fin-card-value">${Number.isFinite(f.value) ? `${f.value} / ${f.out_of}` : '—'}</span>
                <p class="fin-card-plain">수익성·현금흐름·부채·유동성·희석·마진·회전율 9개 항목의 전년 대비 개선 여부. 8~9 강함, 0~2 약함.</p></div>
        </div>
        ${tests ? `<ul class="pecr-signals">${tests}</ul>` : ''}
        <p class="fin-note">Z''는 영업이익을 EBIT로 씁니다. 소매·건설처럼 운전자본이 원래 음(−)인 업종은 점수가 낮게 나오므로 같은 업종끼리 비교하세요. F-score 레버리지 항목은 비유동부채로 대신합니다.</p>
    </section>`;
};

const invShareholderHtml = (inv, live) => {
    const s = inv.shareholder || {};
    const dv = s.dividends || {};
    const fy = String(inv.fiscal_year);
    const ys = Object.keys(dv.dps_common || dv.payout_ratio || {}).sort();
    const price = live?.q?.price;
    const dps = dv.dps_common?.[fy];
    const yieldLive = Number.isFinite(dps) && price ? dps / price : null;
    const tp = s.total_payout_ratio || {};
    const shYield = live && Number.isFinite(tp.returned) && live.equity > 0 ? tp.returned / live.equity : null;
    const t = s.treasury?.common;
    const dl = inv.dilution || {};
    const ins = Object.entries(dl.instruments || {}).filter(([, v]) => v.status === 'reported' && v.shares > 0);
    const INS = { convertible_bond: '전환사채(CB)', bond_with_warrant: '신주인수권부사채(BW)', contingent_convertible: '전환형 조건부자본증권' };
    const dilText = {
        none_declared: '보고서에 미상환 전환사채·BW 등이 없다고 명시돼 있습니다.',
        not_in_capital_section: '자본금 변동사항에 미상환 전환사채 등 항목이 없습니다(있으면 기재 의무).',
        undetermined: '최근 보고서에서 전환사채 현황을 찾지 못했습니다.',
        us_diluted_shares: Number.isFinite(dl.potential_ratio)
            ? `희석 가중평균 주식수가 기본보다 ${Math.round(dl.potential_shares).toLocaleString()}주(${(dl.potential_ratio * 100).toFixed(2)}%) 많습니다 — 스톡옵션·RSU·전환증권이 모두 주식이 되면 늘어나는 몫. 미국은 CB보다 주식보상이 희석의 대부분입니다.`
            : '희석 주식수 공시 없음.',
    }[dl.status];
    return `<section class="pecr-section"><h3>주주환원</h3>
        ${ys.length ? `<div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>항목</th>${ys.map((y) => `<th>FY${y}</th>`).join('')}</tr></thead><tbody>
            <tr><td>주당 배당금 (보통주)</td>${ys.map((y) => `<td class="pecr-num">${Number.isFinite(dv.dps_common?.[y]) ? pecrPx(dv.dps_common[y]) : '—'}</td>`).join('')}</tr>
            <tr><td>현금배당 총액</td>${ys.map((y) => `<td class="pecr-num">${pecrNum(dv.cash_dividends_total?.[y])}</td>`).join('')}</tr>
            <tr><td>배당성향 (연결)</td>${ys.map((y) => `<td class="pecr-num">${Number.isFinite(dv.payout_ratio?.[y]) ? `${(dv.payout_ratio[y] * 100).toFixed(1)}%` : '—'}</td>`).join('')}</tr>
            <tr><td>배당수익률 (공시)</td>${ys.map((y) => `<td class="pecr-num">${Number.isFinite(dv.dividend_yield_reported?.[y]) ? `${(dv.dividend_yield_reported[y] * 100).toFixed(1)}%` : '—'}</td>`).join('')}</tr>
            </tbody></table></div>` : `<p class="fin-note">${dv.none_paid ? '최근 3개 사업연도 현금배당이 없습니다(배당에 관한 사항 공시 기준).' : '배당에 관한 사항 공시가 없습니다.'}</p>`}
        <div class="fin-cards">
            <div class="fin-card pecr-card"><span class="fin-card-title">총주주환원율</span><span class="fin-card-value">${invPct(tp)}</span>
                <p class="fin-card-plain">(FY${finEsc(fy)} 현금배당 ${pecrNum(tp.dividends)} + 자사주 매입 ${pecrNum(tp.buyback)}) ÷ 지배주주 순이익.
                    자사주 매입은 연결 현금흐름표라 종속회사 매입분이 섞일 수 있습니다.</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">배당수익률 (오늘 주가)</span><span class="fin-card-value">${yieldLive === null ? '—' : `${(yieldLive * 100).toFixed(2)}%`}</span>
                <p class="fin-card-plain">FY${finEsc(fy)} 주당배당금 ${pecrPx(dps)} ÷ 종가 ${pecrPx(price)}.</p></div>
            <div class="fin-card pecr-card"><span class="fin-card-title">주주환원 수익률</span><span class="fin-card-value">${shYield === null ? '—' : `${(shYield * 100).toFixed(2)}%`}</span>
                <p class="fin-card-plain">(배당 + 자사주 매입) ÷ 오늘 시가총액. 배당만 보는 수익률보다 넓은 개념.</p></div>
            ${t ? `<div class="fin-card pecr-card"><span class="fin-card-title">자기주식 (보통주)</span><span class="fin-card-value">${invPct(s.treasury_ratio)}</span>
                <p class="fin-card-plain">기말 ${t.end.toLocaleString()}주 보유 · 당기 취득 ${t.acquired.toLocaleString()}주 · <b>소각 ${t.cancelled.toLocaleString()}주</b>
                    (발행주식의 ${invPct(s.cancelled_ratio, 2)}). 소각해야 주당 가치가 올라갑니다.</p></div>` : ''}
        </div></section>
        <section class="pecr-section"><h3>잠재 희석 — 미상환 전환사채·BW</h3>
            ${ins.length ? `<div class="co-table-wrap"><table class="co-table pecr-table">
                <thead><tr><th>종류</th><th>미상환 권면</th><th>전환·행사 가능 주식</th><th>기준일</th></tr></thead><tbody>
                ${ins.map(([k, v]) => `<tr><td>${finEsc(INS[k] || k)}</td><td class="pecr-num">${pecrNum(v.outstanding)}</td>
                    <td class="pecr-num">${v.shares.toLocaleString()}주</td><td>${finEsc(v.as_of || dl.period_end)}${v.after_period ? `<br><span class="fin-note">제출일 현재 ${v.after_period.shares.toLocaleString()}주</span>` : ''}</td></tr>`).join('')}
                </tbody></table></div>
                <p class="fin-note"><b>발행주식의 ${Number.isFinite(dl.potential_ratio) ? (dl.potential_ratio * 100).toFixed(1) : '—'}%</b>가 전환되면 새로 생깁니다
                    (보통주 ${Number.isFinite(dl.issued_common) ? dl.issued_common.toLocaleString() : '—'}주 기준). 전환가 조정(리픽싱)·조기상환을 반영한 정기보고서 표 기준입니다.</p>`
                : `<p class="fin-note">${finEsc(dilText || '전환·행사 가능한 미상환 증권이 없습니다.')}</p>`}
            <p class="fin-note">${dl.status === 'us_diluted_shares'
                ? `출처: SEC ${finEsc(dl.period_end || '')} 10-K 주당이익 주석(기본·희석 가중평균 주식수).`
                : `출처: ${finEsc(dl.period_end || '')} 정기보고서 자본금 변동사항 (접수 ${finEsc(dl.receipt || '—')}). 교환사채(EB)는 자기주식과 교환돼 발행주식이 늘지 않아 제외.`}</p>
        </section>`;
};

const invMetricsView = (snap) => {
    const inv = snap.investor_metrics;
    if (!inv) return '<p class="fin-note">이 스냅샷에는 투자지표가 아직 없습니다. 다음 엔진 재생성 때 채워집니다.</p>';
    const live = pecrLive(snap);
    return conglomerateHtml(snap) + financialKpisHtml(snap) + kitIndustryHtml(snap) + segmentsHtml(snap) + backlogHtml(snap) + invGrowthHtml(inv, live) + invReturnsHtml(inv) + invQualityHtml(inv) + noteItemsHtml(snap) + invScoresHtml(inv, live) + invShareholderHtml(inv, live)
        + `<p class="fin-note">재무제표: OpenDART 사업보고서 FY${(inv.years || [])[0] || ''}~FY${inv.fiscal_year} ${snap.fs_div === 'OFS' ? '별도' : '연결'}.
            배당: 사업보고서 배당에 관한 사항. 자기주식: 자기주식 취득 및 처분 현황. 시세가 필요한 값(PEG, 시가 Z, 수익률)은 일별 시가총액으로 계산합니다.</p>`;
};

// PE 실사: EV에 더하는 부채성 항목과 빼는 비영업자산.
const invBridgeHtml = (snap) => {
    const b = snap.investor_metrics?.ev_bridge;
    if (!b || !b.items) return '';
    const live = pecrLive(snap);
    const ev = live?.ev ?? pecrCard(snap, 'ev')?.value;
    const ebitda = live?.fy?.ebitda ?? pecrCard(snap, 'ebitda')?.value;
    const adj = Number.isFinite(ev) ? ev + b.adjustment_core : null;
    const cons = Number.isFinite(ev) ? ev + b.adjustment_conservative : null;
    const rows = b.items.map((i) => `<tr><td>${i.sign > 0 ? '+' : i.sign < 0 ? '−' : '·'} ${finEsc(i.label)}${i.core || !i.sign ? '' : ' <span class="pecr-badge">보수적</span>'}
        ${i.note ? `<br><span class="fin-note">${finEsc(i.note)}</span>` : ''}</td><td class="pecr-num">${pecrNum(i.value)}</td></tr>`).join('');
    return `<section class="pecr-section"><h3>조정 EV 브릿지 — PE 실사 항목</h3>
        <div class="co-table-wrap"><table class="co-table pecr-table"><tbody>
            <tr><td>EV (시가총액 + 순차입금 + 비지배지분)</td><td class="pecr-num">${pecrNum(ev)}</td></tr>
            ${rows}
            <tr class="pecr-median"><td>= 조정 EV</td><td class="pecr-num">${pecrNum(adj)}</td></tr>
            <tr><td>보수적 EV (충당부채까지)</td><td class="pecr-num">${pecrNum(cons)}</td></tr>
            <tr><td>조정 EV/EBITDA</td><td class="pecr-num">${Number.isFinite(adj) && ebitda > 0 ? `${invX(adj / ebitda, 1)}배` : '—'}${Number.isFinite(cons) && ebitda > 0 ? ` (보수적 ${invX(cons / ebitda, 1)}배)` : ''}</td></tr>
        </tbody></table></div>
        <p class="fin-note">인수가에는 차입금 말고도 갚아야 할 부채성 항목이 붙습니다. 퇴직급여 적립 부족분과 재무상태표에 따로 안 잡힌 리스부채를 더하고,
            관계기업 지분(비영업자산)은 따로 팔 수 있어 뺍니다. 순차입금에 리스가 ${b.lease_in_net_debt ? '이미 포함돼 리스는 더하지 않았습니다' : '빠져 있어 주석의 리스부채를 더했습니다'}. ${finEsc(b.period_end)} 기준.</p>
    </section>`;
};

const invFccrHtml = (snap) => {
    const f = snap.investor_metrics?.ev_bridge?.fixed_charge_coverage;
    if (!f) return '';
    return `<section class="pecr-section"><h3>고정비 보상배율 (FCCR)</h3>
        <div class="fin-cards"><div class="fin-card pecr-card"><span class="fin-card-title">FCCR</span>
            <span class="fin-card-value">${Number.isFinite(f.value) ? `${invX(f.value, 1)}배` : '—'}</span>
            <p class="fin-card-plain">${Number.isFinite(f.value) ? `(EBITDA ${pecrNum(f.ebitda)} − 설비투자 ${pecrNum(f.capex)}) ÷ (이자 지급 ${pecrNum(f.interest_paid)} + 리스 상환 ${f.lease_missing ? '미확인' : pecrNum(f.lease_principal_paid)}).
                투자까지 하고 남은 현금으로 이자·리스료를 몇 번 낼 수 있는지. 인수금융 약정은 보통 1.1~1.25배 이상을 요구합니다.` : finEsc(invReason(f.reason))}</p></div></div>
    </section>`;
};

// --- 1년 내 만기 차입금 · 만기 구간 · PF 보증 (snapshot.liquidity) ------------
const LADDER_ORDER = ['borrowings', 'bonds', 'lease', 'contingent', 'financial_liabilities'];
const liquidityHtml = (snap) => {
    const L = snap.liquidity;
    if (!L || !(L.fy || L.latest)) return '';
    const cols = [L.fy, L.latest].filter(Boolean);
    const keys = [...new Set(cols.flatMap((c) => c.parts.map((x) => x.key)))];
    const label = (k) => cols.flatMap((c) => c.parts).find((x) => x.key === k)?.label || k;
    const val = (c, k) => c.parts.find((x) => x.key === k)?.value;
    const ratio = (v, d = 2) => (Number.isFinite(v) ? `${v.toFixed(d)}배` : '—');
    const lad = L.ladders || {};
    const ladders = LADDER_ORDER.filter((k) => lad[k]).map((k) => {
        const x = lad[k];
        return `<tr><td>${finEsc(x.label)}${x.partial ? ' <span class="pecr-badge">일부(자회사 표)</span>' : ''}</td>
            <td>${x.buckets.map((b) => `${finEsc(b.bucket)} <b>${pecrNum(b.value)}</b>`).join(' · ')}</td></tr>`;
    }).join('');
    const pf = lad.contingent;
    return `<section class="pecr-section"><h3>1년 내 만기 차입금 — 갚거나 차환해야 할 이자부 부채</h3>
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>종류</th>${cols.map((c) => `<th>${finEsc(c.period_end)}</th>`).join('')}</tr></thead><tbody>
            ${keys.map((k) => `<tr><td>${finEsc(label(k))}</td>${cols.map((c) => `<td class="pecr-num">${pecrNum(val(c, k))}</td>`).join('')}</tr>`).join('')}
            <tr class="pecr-median"><td>합계</td>${cols.map((c) => `<td class="pecr-num">${pecrNum(c.total)}</td>`).join('')}</tr>
            <tr><td>현금·단기금융상품 ÷ 만기 차입</td>${cols.map((c) => `<td class="pecr-num">${ratio(c.cover_by_cash)}</td>`).join('')}</tr>
            <tr><td>총차입금 중 1년 내 비중</td>${cols.map((c) => `<td class="pecr-num">${Number.isFinite(c.share_of_debt) ? `${(c.share_of_debt * 100).toFixed(0)}%` : '—'}</td>`).join('')}</tr>
            ${Number.isFinite(L.fy?.to_ebitda) ? `<tr><td>만기 차입 ÷ EBITDA</td><td class="pecr-num">${ratio(L.fy.to_ebitda, 1)}</td>${L.latest ? '<td></td>' : ''}</tr>` : ''}
        </tbody></table></div>
        <p class="fin-note">유동부채 전체가 아니라 이자가 붙는 차입만 셉니다(매입채무·미지급금·선수금 같은 영업부채 제외). 현금 배수가 1 미만이면 1년 안에 차환하거나 영업현금으로 갚아야 합니다.</p>
        ${ladders ? `<div class="co-table-wrap"><table class="co-table pecr-table"><thead><tr><th>만기 구간 (${finEsc(L.ladders.period_end || '')})</th><th>금액</th></tr></thead>
            <tbody>${ladders}</tbody></table></div><p class="fin-note">${finEsc(L.ladders.basis || '')}</p>` : ''}
        ${pf ? `<p class="fin-note"><b>PF·보증 우발채무</b>: 1년 내 ${pecrNum(pf.within_1y)} — 재무상태표 차입금에는 없지만 시행사가 못 갚으면 떠안는 금액입니다.</p>` : ''}
        ${L.net_debt_wide && snap.valuation_bases?.fy?.net_debt_card === 'net_debt_name_matched'
            ? `<p class="fin-note">이 회사는 차입금 일부가 표준 계정코드 없이 공시돼, 계정명으로 찾은 순차입금 ${pecrNum(L.net_debt_wide.value)}을 EV에 씁니다.</p>` : ''}
    </section>`;
};

// --- 카드 상세: 계산 근거 + 분기별 변화 (card.parts, snapshot.quarterly) -------
// Clicking an engine card (or the live EV row) opens a box under it: how the
// value was built from which accounts of which filing, and the same quantity
// at every quarter end the filings allow.
const PART_LABEL = {
    cash: '현금및현금성자산', equity: '자본총계', parent_equity: '지배주주 자본', borrowings_short: '단기차입금',
    borrowings_current_portion: '유동성장기차입금', bonds_current: '유동성사채', borrowings_long: '장기차입금',
    bonds_noncurrent: '사채', lease_current: '유동리스부채', lease_noncurrent: '비유동리스부채', debt_current_total: '단기차입금(유동성 포함)',
};
const PART_SIGN = { cash: '−', parent_equity: '−' };
const REPORT_NAME = { 11011: '사업보고서', 11012: '반기보고서', 11013: '1분기보고서', 11014: '3분기보고서' };
const Q_FOR_CARD = {
    ev: 'ev', ev_reported: 'ev', market_cap: 'market_cap', net_debt: 'net_debt', net_debt_reported: 'net_debt',
    gross_debt_reported: 'gross_debt', current_ratio: 'current_ratio', debt_ratio: 'debt_ratio',
    ev_to_ebitda: 'ev_to_ebit', ev_to_ebit: 'ev_to_ebit', ev_reported_to_ebitda: 'ev_to_ebit',
    operating_income: 'op_ltm', debt_due_within_1y: 'short_term_debt',
};
const Q_LABEL = {
    ev: ['EV', 'money'], market_cap: ['시가총액', 'money'], common_cap: ['보통주 시가', 'money'], preferred_cap: ['우선주 시가', 'money'], net_debt: ['순차입금', 'money'], gross_debt: ['총차입금(리스 포함)', 'money'],
    nci: ['비지배지분', 'money'], cash: ['현금', 'money'], short_term_debt: ['단기 차입(1년 내)', 'money'],
    current_ratio: ['유동비율', 'x'], debt_ratio: ['부채비율', 'pct'], ev_to_ebit: ['EV/EBIT (LTM 영업이익)', 'x'],
    op_ltm: ['영업이익 (LTM)', 'money'], revenue_ltm: ['매출 (LTM)', 'money'],
};
const qFmt = (kind, v) => (!Number.isFinite(v) ? '—' : kind === 'money' ? pecrNum(v) : kind === 'pct' ? `${(v * 100).toFixed(0)}%` : `${v.toFixed(1)}배`);

// EV = 보통주 + 우선주 + 순차입금 + 비지배지분, one stacked bar per quarter.
// Net cash (negative net debt) hangs below zero, so the bar's net height still
// equals EV; a dot marks EV itself.
const EV_STACK = [
    ['common_cap', '보통주 시가총액', '#60a5fa'], ['preferred_cap', '우선주 시가총액', '#a78bfa'],
    ['net_debt', '순차입금 (음수면 순현금)', '#f59e0b'], ['nci', '비지배지분', '#34d399'],
];
const pecrEvStackHtml = (pts) => {
    const rows = pts.map((p) => ({
        p, segs: EV_STACK.map(([k]) => (k === 'common_cap' && !Number.isFinite(p.common_cap) ? p.market_cap : p[k]))
            .map((v) => (Number.isFinite(v) ? v : 0)),
    }));
    const hi = Math.max(0, ...rows.map((r) => r.segs.filter((v) => v > 0).reduce((a, b) => a + b, 0)));
    const lo = Math.min(0, ...rows.map((r) => r.segs.filter((v) => v < 0).reduce((a, b) => a + b, 0)));
    const W = 640, H = 170, top = 10, bottom = 18, span = (hi - lo) || 1;
    const y = (v) => top + (hi - v) / span * (H - top - bottom);
    const slot = W / rows.length, bw = Math.min(46, slot * 0.6);
    const bars = rows.map((r, i) => {
        const x = i * slot + (slot - bw) / 2;
        let up = 0, down = 0;
        const rects = r.segs.map((v, k) => {
            if (!v) return '';
            const from = v > 0 ? up : down;
            const to = from + v;
            if (v > 0) up = to; else down = to;
            const [, label, color] = EV_STACK[k];
            return `<rect x="${x.toFixed(1)}" y="${Math.min(y(from), y(to)).toFixed(1)}" width="${bw.toFixed(1)}"
                height="${Math.max(1, Math.abs(y(from) - y(to))).toFixed(1)}" fill="${color}"><title>${finEsc(r.p.period_end)} ${finEsc(label)} ${pecrNum(v)}</title></rect>`;
        }).join('');
        const ev = r.p.ev;
        const dot = Number.isFinite(ev) ? `<circle cx="${(x + bw / 2).toFixed(1)}" cy="${y(ev).toFixed(1)}" r="3.2" fill="#f1f5f9"><title>EV ${pecrNum(ev)}</title></circle>` : '';
        const lbl = `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 4}" text-anchor="middle" font-size="10" fill="#94a3b8">${finEsc(r.p.period_end.slice(2, 7).replace('-', '.'))}</text>`;
        return rects + dot + lbl;
    }).join('');
    const zero = `<line x1="0" x2="${W}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}" stroke="#475569" stroke-width="1"/>`;
    const used = EV_STACK.filter(([k]) => rows.some((r) => r.segs[EV_STACK.findIndex((e) => e[0] === k)]));
    return `<svg viewBox="0 0 ${W} ${H}" class="pecr-stack" role="img" aria-label="분기별 EV 구성">${zero}${bars}</svg>
        <div class="pecr-legend">${used.map(([, l, c]) => `<span><i style="background:${c}"></i>${finEsc(l)}</span>`).join('')}
            <span><i class="dot"></i>EV</span></div>`;
};

const pecrQuarterHtml = (snap, metric) => {
    const q = snap.quarterly;
    if (!q || !metric) return '';
    const pts = (q.points || []).filter((p) => Number.isFinite(p[metric]));
    if (pts.length < 2) return '<p class="fin-note">분기별 값을 만들 공시가 부족합니다.</p>';
    const [label, kind] = Q_LABEL[metric] || [metric, 'money'];
    const bars = metric === 'ev' ? pecrEvStackHtml(pts) : typeof finPeriodBars === 'function'
        ? finPeriodBars(pts.map((p) => ({ label: p.period_end.slice(2, 7).replace('-', '.'), value: p[metric] })), (v) => qFmt(kind, v)) : '';
    const comps = metric === 'ev' || metric === 'ev_to_ebit'
        ? (pts.some((p) => Number.isFinite(p.preferred_cap))
            ? ['common_cap', 'preferred_cap', 'net_debt', 'nci', 'ev', 'op_ltm', 'ev_to_ebit']
            : ['market_cap', 'net_debt', 'nci', 'ev', 'op_ltm', 'ev_to_ebit']) : metric === 'net_debt' || metric === 'gross_debt'
            ? ['gross_debt', 'cash', 'net_debt'] : [metric];
    return `<div class="pecr-q"><p class="pecr-q-title">분기별 ${finEsc(label)}</p>${bars}
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>분기말</th>${comps.map((c) => `<th>${finEsc((Q_LABEL[c] || [c])[0])}</th>`).join('')}</tr></thead>
            <tbody>${pts.map((p) => `<tr><td>${finEsc(p.period_end)} <span class="fin-note">${finEsc(p.report)}</span></td>
                ${comps.map((c) => `<td class="pecr-num">${qFmt((Q_LABEL[c] || [])[1] || 'money', p[c])}</td>`).join('')}</tr>`).join('')}</tbody>
        </table></div>
        <p class="fin-note">${finEsc(q.basis || '')}</p></div>`;
};

const pecrPartsHtml = (snap, card) => {
    const parts = card?.parts || [];
    if (!parts.length) return '';
    const fy = String(snap.fiscal_year || '');
    const rows = parts.map((x) => {
        if (x.input === 'market') {
            const pref = Number.isFinite(x.preferred_equity?.value) && x.preferred_equity.value > 0 ? ` (우선주 ${pecrNum(x.preferred_equity.value)} 포함)` : '';
            return `<tr><td>+ 시가총액${pref}</td><td class="pecr-num">${pecrNum(x.market_cap)}</td><td>스냅샷 기준일 시세 ${finEsc(x.as_of || '')}</td></tr>`;
        }
        const name = PART_LABEL[x.input] || x.label || x.input;
        const src = x.filing ? `${REPORT_NAME[x.report] || x.report || ''} ${x.period_end || ''}${x.opening ? ' (기초)' : ''} · 접수 ${x.filing}`
            : (x.period_end || '');
        return `<tr><td>${PART_SIGN[x.input] || ''} ${finEsc(name)}${x.label && x.label !== name ? ` <span class="fin-note">(공시 계정: ${finEsc(x.label)})</span>` : ''}</td>
            <td class="pecr-num">${Number.isFinite(x.days) ? `${Math.round(x.days)}일` : Number.isFinite(x.value) ? pecrNum(x.value) : '—'}</td><td class="fin-note">${finEsc(src)}</td></tr>`;
    });
    return `<div class="co-table-wrap"><table class="co-table pecr-table"><thead><tr><th>구성 요소</th><th>금액</th><th>출처</th></tr></thead>
        <tbody>${rows.join('')}</tbody></table></div>
        <p class="fin-note">비지배지분 = 자본총계 − 지배주주 자본. FY${finEsc(fy)} ${snap.source === 'SEC' ? 'SEC 10-K' : 'OpenDART 공시'} 기준.</p>`;
};

const pecrDetailHtml = (snap, key) => {
    if (key === 'live_ev') {
        const m = pecrLive(snap);
        if (!m) return '';
        const qq = m.q;
        return `<div class="pecr-detail"><p class="pecr-q-title">EV (오늘 시세 기준) = 시가총액 + 순차입금 + 비지배지분</p>
            <div class="co-table-wrap"><table class="co-table pecr-table"><tbody>
                <tr><td>+ 시가총액 (보통주${m.prefCap ? '·우선주' : ''})</td><td class="pecr-num">${pecrNum(m.equity)}</td><td class="fin-note">${finEsc((qq.traded_at || '').slice(0, 10))} 종가 ${pecrPx(qq.price)}</td></tr>
                <tr><td>+ 순차입금</td><td class="pecr-num">${pecrNum(m.fy.net_debt)}</td><td class="fin-note">${finEsc(m.fy.period_end || '')} 재무상태표 (${finEsc(m.fy.net_debt_card || '')})</td></tr>
                <tr><td>+ 비지배지분</td><td class="pecr-num">${pecrNum(m.nci)}</td><td class="fin-note">${finEsc(m.latest.period_end || '')} 자본총계 − 지배주주 자본</td></tr>
                <tr class="pecr-median"><td>= EV</td><td class="pecr-num">${pecrNum(m.ev)}</td><td></td></tr>
                <tr><td>÷ EBITDA</td><td class="pecr-num">${pecrNum(m.fy.ebitda)}</td><td class="fin-note">FY ${finEsc(m.fy.ebitda_card || '')}</td></tr>
                <tr class="pecr-median"><td>= EV/EBITDA</td><td class="pecr-num">${pecrFmt('x', m.ev_to_ebitda)}</td><td></td></tr>
            </tbody></table></div>
            ${pecrQuarterHtml(snap, 'ev')}</div>`;
    }
    // the card the screen shows: strict if it has a value, else its reported-basis fallback
    const card = pecrCard(snap, key) || snap.pe_cr?.cards?.[key];
    if (!card) return '';
    const [label, fmt, plain] = PECR_META[key] || [key, 'x', ''];
    return `<div class="pecr-detail"><p class="pecr-q-title">${finEsc(label)} = ${pecrFmt(fmt, card.value)}${card.basis === 'reported' ? ' <span class="pecr-badge">공시계정 기준</span>' : ''}</p>
        <p class="fin-note">${finEsc(plain)}${card.definition ? ` <span class="pecr-reason">(엔진 정의: ${finEsc(card.definition)})</span>` : ''}
            ${card.reason ? ` · 값이 없는 이유: ${finEsc(pecrReason(card.reason))}` : ''}</p>
        ${pecrPartsHtml(snap, card)}
        ${pecrQuarterHtml(snap, Q_FOR_CARD[key])}</div>`;
};

const pecrBindDetails = (out, snap) => {
    out.querySelectorAll('[data-pecr-detail]').forEach((el) => el.addEventListener('click', (e) => {
        if (e.target.closest('.pecr-detail')) return;
        const key = el.dataset.pecrDetail;
        const open = out.querySelector(`.pecr-detail[data-for="${key}"]`);
        out.querySelectorAll('.pecr-detail').forEach((d) => d.remove());
        out.querySelectorAll('[data-pecr-detail].open').forEach((d) => d.classList.remove('open'));
        if (open) return;
        const html = pecrDetailHtml(snap, key);
        if (!html) return;
        const box = document.createElement('div');
        box.innerHTML = html;
        const node = box.firstElementChild;
        node.dataset.for = key;
        el.classList.add('open');
        // inside a card grid the box spans the full row; in a table it follows the table
        (el.tagName === 'TR' ? el.closest('.co-table-wrap') : el).after(node);
    }));
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
    PECR_CUR = snap?.currency || 'KRW';
    if (!snap) {
        return `<div class="fin-empty"><p class="fin-empty-title">이 기업은 아직 PE·CR 엔진 스냅샷이 없습니다</p>
            <p>엔진 스냅샷은 OpenDART 원본 공시로 매일 새벽 미리 계산합니다. 대상은 코스피·코스닥 시가총액 상위 각 500개사이고, 새 정기보고서가 나온 회사부터 다시 만듭니다.
               이 회사는 아직 대상이 아니거나 이번 주기에서 아직 처리되지 않았습니다. 기본 탭의 지표는 그대로 볼 수 있습니다.</p></div>`;
    }
    const financial = snap.pe_cr?.industry === 'financial';
    if (view === 'metrics') return pecrHead(snap) + invMetricsView(snap);
    const lens = (snap.pe_cr?.cr_pe_screen?.lens_order || {})[view === 'cr' ? 'cr' : 'pe'] || [];
    if (view === 'cr') {
        return pecrHead(snap) + (financial
            ? pecrRegulatory(snap) + pecrFunding(snap) + pecrSection(snap, 'capital_structure', { hideEmpty: true }) + pecrSection(snap, 'cash_flow', { hideEmpty: true })
              + '<p class="fin-note">금융회사는 산업기업용 CR 지표(EBITDA, 순차입금, 이자보상배율 등)를 적용하지 않습니다. 업권별 지표는 기본 탭에 있습니다.</p>'
            : pecrSignals(snap) + liquidityHtml(snap) + (snap.investor_metrics ? invScoresHtml(snap.investor_metrics, pecrLive(snap)) : '')
              + lens.map((id) => pecrSection(snap, id)).join('') + pecrFunding(snap));
    }
    if (view === 'pe') {
        return pecrHead(snap) + ['profitability', 'cash_flow', 'capital_structure', 'repayment'].map((id) => pecrSection(snap, id)).join('')
            + invFccrHtml(snap) + pecrLbo(snap);
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
                <tr><td>보통주 시가총액</td><td>${pecrNum(cap)}</td></tr>
                <tr><td>+ 우선주 시가</td><td>${pecrNum(pref)}</td></tr>
                <tr><td>+ 순차입금</td><td>${pecrNum(nd)}</td></tr>
                <tr><td>+ 비지배지분(장부)</td><td>${pecrNum(nci)}</td></tr>
                <tr class="pecr-median"><td>= EV</td><td>${pecrNum(ev)}</td></tr>
            </tbody></table></div></section>` : ''}
        ${invBridgeHtml(snap)}
        <section class="pecr-section"><h3>피어 비교</h3><div class="pecr-peers">${pecrPeersHtml(snap, data.pecrPeers)}</div></section>`;
};

const pecrBind = (out, data, rerender) => {
    if (data.pecr) pecrBindDetails(out, data.pecr);
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
