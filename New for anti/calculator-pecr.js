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
    return loadFirstJson(finDataPaths(`kfa_pecr/${corpCode}_v1.json`));
};

const PECR_PEER_COLS = [
    ['ev_to_ebitda', 'EV/EBITDA', 'x'], ['per', 'PER', 'x'], ['pbr', 'PBR', 'x'], ['ebitda_margin', 'EBITDA 마진', 'pct'],
    ['net_debt_to_ebitda', '순차입/EBITDA', 'x'], ['interest_coverage', '이자보상', 'x'], ['roe', 'ROE', 'pct'],
];

const pecrPeersHtml = (snap, peers) => {
    if (!peers) return '<p class="fin-note">피어를 불러오는 중…</p>';
    const rows = [snap, ...peers];
    const med = (key, fmt) => {
        const v = peers.map((p) => pecrCard(p, key)?.value).filter(Number.isFinite).sort((a, b) => a - b);
        if (v.length < 2) return '—';
        const m = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
        return pecrFmt(fmt, m);
    };
    return `
        <div class="co-table-wrap"><table class="co-table pecr-table">
            <thead><tr><th>기업</th>${PECR_PEER_COLS.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((s, i) => `<tr class="${i === 0 ? 'pecr-self' : ''}"><td>${finEsc((s.entity || '').replace(/\(주\)|주식회사/g, ''))}</td>
                ${PECR_PEER_COLS.map(([k, , f]) => { const c = pecrCard(s, k); return `<td>${pecrFmt(f, c?.value)}${c?.basis === 'reported' && c.value != null ? '*' : ''}</td>`; }).join('')}</tr>`).join('')}
                ${peers.length >= 2 ? `<tr class="pecr-median"><td>피어 중앙값</td>${PECR_PEER_COLS.map(([k, , f]) => `<td>${med(k, f)}</td>`).join('')}</tr>` : ''}
            </tbody>
        </table></div>
        <p class="fin-note">${peers.length ? `같은 업종 분류(${finEsc(snap.pe_cr?.industry_profile?.label_ko || snap.pe_cr?.industry || '')})의 엔진 스냅샷 ${peers.length}개` : '같은 업종의 다른 스냅샷이 아직 없습니다'}.
            * = 공시계정 기준. 시세는 각 회사의 스냅샷 기준일 값입니다.</p>`;
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
    return `<p class="fin-note pecr-head">엔진 스냅샷: FY${finEsc(snap.fiscal_year)} ${snap.fs_div === 'OFS' ? '별도' : '연결'} ·
        업종 ${finEsc(p.industry_profile?.label_ko || p.industry || '')}${mc?.market_date ? ` · 시세 ${finEsc(mc.market_date)}` : ''} ·
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
            ? pecrFunding(snap) + pecrSection(snap, 'capital_structure', { hideEmpty: true }) + pecrSection(snap, 'cash_flow', { hideEmpty: true })
              + '<p class="fin-note">금융회사는 산업기업용 CR 지표(EBITDA, 순차입금, 이자보상배율 등)를 적용하지 않습니다. 업권별 지표는 기본 탭에 있습니다.</p>'
            : pecrSignals(snap) + lens.map((id) => pecrSection(snap, id)).join('') + pecrFunding(snap));
    }
    if (view === 'pe') {
        return pecrHead(snap) + ['profitability', 'cash_flow', 'capital_structure', 'repayment'].map((id) => pecrSection(snap, id)).join('')
            + pecrLbo(snap);
    }
    // deal
    const c = (k) => pecrCard(snap, k)?.value;
    const ev = c('ev'), cap = c('market_cap'), nd = c('net_debt'), total = snap.pe_cr?.cards?.equity_market_value_total?.value;
    const pref = Number.isFinite(total) && Number.isFinite(cap) ? total - cap : null;
    const nci = Number.isFinite(ev) && Number.isFinite(total) && Number.isFinite(nd) ? ev - total - nd : null;
    return pecrHead(snap) + `
        <section class="pecr-section"><h3>밸류에이션 배수</h3>
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
