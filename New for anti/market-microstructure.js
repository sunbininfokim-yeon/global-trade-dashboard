// Market microstructure for Global Trade Dashboard -- order-book pressure,
// funding and credit, price levels, and the derivatives/short-selling views.
//
// Named for what it shows rather than "derivatives", which described only one
// of its tabs. Split out of app.js (2026-08-20) for the same reason as the
// other finance domains: app.js is shared by parallel sessions and squash
// merges overwrite whole regions.
//
// Loaded AFTER macro.js -- msHistChart and msModalFor draw with mmLineChart.
// Relies on globals still in app.js: finEsc, finPct,
// loadFirstJson/finDataPaths, and the DOM helpers.

// === 시장 미시구조 / US→KR 관찰 ==============================================
//
// Engine and snapshots are Cursor's (scripts/market_microstructure); this file
// only reads them. Four tabs, because the four questions are separate ones:
// how tangled Korean flow is, where foreigners actually bought, and whether the
// US options tape is leaning on Korea. The rule throughout: a null stays blank.
// A plausible-looking number in a positioning panel is worse than an empty one.
const MS_FILES = {
    transmission: 'us_kr_transmission_v1.json',
    alerts: 'alert_levels_v1.json',
    conc: 'kospi_concentration_history_v1.json',
    board: 'derivatives_board_v1.json',
    brief: 'ai_casino_brief_v1.json',
    levels: 'investor_price_levels_v1.json',
    micro: 'market_microstructure_v1.json',
    overseas: 'overseas_letf_board_v1.json',
    // The micro snapshot carries a thin, older copy of deposit_credit: no
    // 미수금/반대매매 and no daily series. This is the full FreeSIS table.
    credit: 'deposit_credit_v1.json',
    // KRX 15007 투자자별 선물·콜·풋 거래실적, 2019~ (build_krx_deriv_flow.py).
    flow: 'krx_deriv_flow_v1.json',
};

// Prefer the standalone FreeSIS table, falling back to the micro snapshot's
// copy so the panel still renders if the daily publish has not run.
const msCredit = (D) => ((D.credit || {}).deposit_credit) || (D.micro || {}).deposit_credit || {};

const MS_TABS = [
    { id: 'tangle', label: '수급 불균형', blurb: '집중도와 단일종목 레버리지 ETF (Distortion & Squeeze)' },
    { id: 'overseas', label: '해외 LETF', blurb: '삼성전자·SK하이닉스 해외 상품과 미국 주요 비교 상품 · 거래·구성·추정 리밸런싱' },
    { id: 'levels', label: '가격대별 체결', blurb: '어느 가격에서 누가 샀는가 (Volume Profile)' },
    { id: 'uskr',   label: '해외-국내 선행', blurb: '미국 옵션 레짐이 한국으로 (Global Spillover)' },
    { id: 'derivatives', label: '파생 수급', blurb: '외국인 K200 선물·옵션 수급과 시장 전체 거래 활동' },
];

let MS_DATA = null;
let MS_TAB = 'tangle';
let MS_UNIVERSE = 'marcap';
let MS_TICKER = null;         // 가격대별 탭에서 선택한 종목 (null = 코스피 지수)
let MS_STOCK = null;          // 수급 꼬임 탭에서 선택한 종목
let MS_MODAL = null;          // { title, html }
let MS_MODAL_KEY = null;      // 열려 있는 모달의 키 (기간 전환 시 재렌더용)
let MS_PERIOD = '3m';         // 가격대별 표시 구간 — 1m / 2m / 3m / 6m / all
let MS_CREDIT_ON = false;     // 가격대별 탭에서 예탁·신용 추이를 펼쳤는지
let MS_OVERSEAS_GROUP = 'hynix';
let MS_OVERSEAS_PRODUCT = null;

const msGet = (name) => loadFirstJson(finDataPaths(name));

// --- 일별 히스토리 (JSONL) ----------------------------------------------------
// Everything above is one trading day per file. A trend needs an append-only
// log, which the daily job writes a line at a time. A missing log is the normal
// state until that job has run, so absence degrades to an observation count
// rather than an error -- and never to a drawn line through days nobody saw.
const MS_HIST_FILES = {
    activity: 'derivatives_activity_history_v1.jsonl',
    direction: 'leverage_direction_history_v1.jsonl',
    // One file, many tickers (000660 SK하이닉스, 005930 삼성전자, ...) -- both
    // are single-stock LETF names, so a per-ticker file per name does not scale.
    stockLetf: 'stock_letf_history_v1.jsonl',
    overseas: 'overseas_letf_history_v1.jsonl.gz',
};

let MS_HIST = null;
let MS_HIST_PERIOD = '30';
const MS_HIST_PERIODS = [['30', '30거래일'], ['90', '90거래일'], ['all', '전체']];

// JSONL, so it cannot go through loadFirstJson -- but it looks in the same two
// places, and finDataPaths keeps that list in one spot.
const msGetJsonl = async (name) => {
    for (const path of finDataPaths(name)) {
        try {
            const r = await fetch(path, { cache: 'no-store' });
            if (!r.ok) continue;
            const rows = [];
            // Fetch may already have decoded HTTP Content-Encoding. Detect
            // the file's gzip magic, not its extension, to avoid double unzip.
            let bytes = new Uint8Array(await r.arrayBuffer());
            if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
                bytes = new Uint8Array(await new Response(new Blob([bytes]).stream()
                    .pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
            }
            new TextDecoder().decode(bytes).split('\n').forEach((ln) => {
                const s = ln.trim();
                if (!s) return;
                try { rows.push(JSON.parse(s)); } catch (_) { /* one bad line must not void the log */ }
            });
            // A repeated (date, ticker) means the day was re-observed; the later
            // line wins. Files with no ticker field (activity, direction) key
            // on date alone, which is the same thing when ticker is always ''.
            const byKey = new Map();
            rows.forEach((row) => { if (row && row.date) byKey.set(`${row.date}|${row.product_id || row.ticker || ''}`, row); });
            return [...byKey.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
        } catch (_) { /* next base */ }
    }
    return [];
};

const msFinite = (v) => Number.isFinite(v) ? v : null;
const msToJo = (v) => Number.isFinite(v) ? v / 1e12 : null;
const msToEok = (v) => Number.isFinite(v) ? v / 1e8 : null;

// key → which log, which number, how it is labelled. Field names match the
// snapshot schemas so the ingestion side does not need a second vocabulary.
const MS_HIST_SERIES = {
    // Trading value reads the 2019~ KRX 15007 market totals when that file is
    // present (rowsFn); the daily activity log only started in 2026-08.
    'act:fut_tv':   { file: 'activity', rowsFn: () => msFlowActivityRows(), label: 'K200 선물 거래대금', unit: '조',
        pick: (r) => r.flow15007 ? msToJo(r.fut_tv) : msToJo(r.kospi200_futures?.trading_value_krw) },
    'act:fut_vol':  { file: 'activity', label: 'K200 선물 거래량', unit: '계약', pick: (r) => msFinite(r.kospi200_futures?.volume) },
    'act:call_tv':  { file: 'activity', rowsFn: () => msFlowActivityRows(), label: 'K200 콜옵션 거래대금', unit: '억',
        pick: (r) => r.flow15007 ? msToEok(r.call_tv) : msToEok(r.kospi200_options?.call_trading_value_krw) },
    'act:call_vol': { file: 'activity', label: 'K200 콜옵션 거래량', unit: '계약', pick: (r) => msFinite(r.kospi200_options?.call_volume) },
    'act:put_tv':   { file: 'activity', rowsFn: () => msFlowActivityRows(), label: 'K200 풋옵션 거래대금', unit: '억',
        pick: (r) => r.flow15007 ? msToEok(r.put_tv) : msToEok(r.kospi200_options?.put_trading_value_krw) },
    'act:put_vol':  { file: 'activity', label: 'K200 풋옵션 거래량', unit: '계약', pick: (r) => msFinite(r.kospi200_options?.put_volume) },
    'act:pc_vol':   { file: 'activity', label: '풋/콜 거래량 비율', unit: '', pick: (r) => msFinite(r.kospi200_options?.put_call_volume) },
    'act:pc_tv':    { file: 'activity', rowsFn: () => msFlowActivityRows(), label: '풋/콜 거래대금 비율', unit: '',
        pick: (r) => r.flow15007 ? msFinite(r.pc_tv) : msFinite(r.kospi200_options?.put_call_trading_value) },

    'lev:ratio':    { file: 'direction', label: '레버리지·인버스 ETF 거래대금 ÷ 코스피 현물 거래대금', unit: '%', pick: (r) => msFinite(r.levered_inverse_etf_tv_over_kospi_cash_tv_pct) },
    'lev:kospi_tv': { file: 'direction', label: '코스피 현물 거래대금', unit: '조', pick: (r) => msToJo(r.kospi_cash_tv_krw) },
};

// stock_letf_history_v1.jsonl carries every single-stock LETF ticker in one
// log (currently 000660 SK하이닉스, 005930 삼성전자), so the series has to
// filter to one ticker's rows rather than assume the file is already scoped.
// The last two are the modelled series -- signed 조원, not a share of
// anything -- so they always carry the estimate disclaimer in their own
// fin-note rather than relying on the reader to remember it from the title.
const MS_IMPLIED_REBALANCE_NOTE = '일일 리셋 공식 추정치이며 실제 ETF 주문·체결·가격영향이 아님';
const msStockLetfSeries = (ticker, ko) => [
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} LETF 거래대금`, unit: '조', pick: (r) => msToJo(r.letf_trading_value_krw) },
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} 현물 거래대금`, unit: '조', pick: (r) => msToJo(r.spot_trading_value_krw) },
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} LETF / 현물 거래대금 비율`, unit: '%', pick: (r) => Number.isFinite(r.letf_turnover_ratio) ? r.letf_turnover_ratio * 100 : null },
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} LETF 합계 순자산 (AUM)`, unit: '조', pick: (r) => msToJo(r.letf_aum_sum_krw) },
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} 추정 리밸런싱 압력 (부호 포함)`, unit: '조',
        pick: (r) => msToJo(r.implied_rebalance_krw), note: MS_IMPLIED_REBALANCE_NOTE },
    { file: 'stockLetf', filter: (r) => r.ticker === ticker, label: `${ko} 추정 압력 / 현물 당일 거래대금`, unit: '%',
        pick: (r) => msFinite(r.implied_ir_pct), note: MS_IMPLIED_REBALANCE_NOTE },
];

const msDirSeries = (dir, ko) => [
    { file: 'direction', label: `${ko} · 거래대금`, unit: '조', pick: (r) => msToJo(r.by_direction?.[dir]?.trading_value_krw) },
    { file: 'direction', label: `${ko} · 코스피 거래대금 대비 비율`, unit: '%', pick: (r) => msFinite(r.by_direction?.[dir]?.share_of_kospi_tv_pct) },
];

// KRX 15007 콜/풋 분리 외국인 수급. options_total(공개 대시보드)을 콜·풋으로
// 배분 추정하지 않는다 -- 이 파일이 다루는 값은 인증된 15007 원자료뿐이다.
// quality가 'observed'라 주장해도 매수-매도가 순매수와 안 맞으면 신뢰하지
// 않는다: 태그를 믿는 게 아니라 산수를 다시 확인한다.
const MS_15007_EPS_KRW = 1;
const msFlowConsistent = (f) => !!f && [f.buy_krw, f.sell_krw, f.net_krw].every(Number.isFinite)
    && Math.abs((f.buy_krw - f.sell_krw) - f.net_krw) <= MS_15007_EPS_KRW;
const ms15007State = (p) => {
    if (!p || !p.foreign) return { ok: false, reason: '인증된 KRX 15007 필요' };
    if (p.quality !== 'observed') return { ok: false, reason: `데이터 상태: ${p.quality || 'missing'}` };
    if (!msFlowConsistent(p.foreign)) return { ok: false, reason: '매수−매도≠순매수 (quality 오류)' };
    return { ok: true };
};
const ms15007Sorted = (series) => [...(series || [])].sort((a, b) => String(a.date).localeCompare(String(b.date)));
// Only pairs where BOTH sides are a validated observation on the same date --
// a relative flow built from one real and one broken/missing side would read
// as a real number while actually being half guesswork.
const ms15007RelSeries = (callSeries, putSeries) => {
    const byDate = new Map(ms15007Sorted(putSeries).map((r) => [r.date, r]));
    return ms15007Sorted(callSeries)
        .map((c) => {
            const p = byDate.get(c.date);
            if (!(c.quality === 'observed' && msFlowConsistent(c.foreign))) return null;
            if (!(p && p.quality === 'observed' && msFlowConsistent(p.foreign))) return null;
            return { date: c.date, put_minus_call_krw: p.foreign.net_krw - c.foreign.net_krw,
                source: c.source && p.source && c.source === p.source ? c.source : `콜 ${c.source || '—'} · 풋 ${p.source || '—'}` };
        })
        .filter(Boolean);
};
const ms15007Series = (callSeries, putSeries) => [
    { rows: ms15007Sorted(callSeries), label: '외국인 콜 매도', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.sell_krw) : null },
    { rows: ms15007Sorted(callSeries), label: '외국인 콜 매수', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.buy_krw) : null },
    { rows: ms15007Sorted(callSeries), label: '외국인 콜 순매수', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.net_krw) : null },
    { rows: ms15007Sorted(putSeries), label: '외국인 풋 매도', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.sell_krw) : null },
    { rows: ms15007Sorted(putSeries), label: '외국인 풋 매수', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.buy_krw) : null },
    { rows: ms15007Sorted(putSeries), label: '외국인 풋 순매수', unit: '억',
        pick: (r) => (r.quality === 'observed' && msFlowConsistent(r.foreign)) ? msToEok(r.foreign.net_krw) : null },
    { rows: ms15007RelSeries(callSeries, putSeries), label: '풋 순매수 − 콜 순매수 (상대 흐름)', unit: '억',
        pick: (r) => msToEok(r.put_minus_call_krw),
        note: '당일 거래 흐름의 상대값이며 방향 예측·외국인 OI·신규 포지션·헤지 의도의 확정 판정이 아님' },
];

const msHistRows = (file) => (MS_HIST || {})[file] || [];
// Filtering has to happen before the last-N-trading-days window is cut, or
// "last 30 days" on a shared multi-ticker file would mean 30 rows of mixed
// tickers rather than 30 observations of the one being charted.
// Most series live in an append-only JSONL log (spec.file). The KRX 15007
// call/put series instead arrives embedded in the daily snapshot itself
// (products.options_call.series), so its spec carries the rows directly.
const msSpecRows = (spec) => {
    const rows = spec.rows || (spec.rowsFn && spec.rowsFn()) || msHistRows(spec.file);
    return spec.filter ? rows.filter(spec.filter) : rows;
};

const msHistPeriodBar = () => `
    <div class="ms-hist-period" role="group" aria-label="표시 기간">
        ${MS_HIST_PERIODS.map(([id, ko]) => `<button class="mm-tab ${id === MS_HIST_PERIOD ? 'on' : ''}" data-ms-hist-period="${id}">${finEsc(ko)}</button>`).join('')}
    </div>`;

// Four points still reads as a trend line to the eye, so the honest floor is
// five: below that the output is the count of days actually observed. Non-
// trading days are absent rows and stay absent -- the x-axis is observations,
// never a filled calendar.
const MS_HIST_MIN_OBS = 5;

const msHistChart = (spec) => {
    const all = msSpecRows(spec);
    const win = MS_HIST_PERIOD === 'all' ? all : all.slice(-Number(MS_HIST_PERIOD));
    const values = win.map(spec.pick);
    const usable = values.filter(Number.isFinite).length;
    if (usable < MS_HIST_MIN_OBS) {
        return `<div class="ms-hist-empty">
            <strong>히스토리 축적 중 · ${usable}/${MS_HIST_MIN_OBS} 거래일</strong>
            <p>${finEsc(spec.label)} — 현재 관측 ${usable}일. 일별 로그가 ${MS_HIST_MIN_OBS}거래일 이상 쌓이면 추이선이 자동으로 표시됩니다.
            없는 날짜를 채워 그리지 않습니다.</p>
        </div>
        ${spec.note ? `<p class="fin-note ms-warn">${finEsc(spec.note)}</p>` : ''}`;
    }
    const soft = win.filter((r) => r.quality && r.quality !== 'observed').length;
    const last = win[win.length - 1] || {};
    return `
        ${mmLineChart(win.map((r) => r.date), values, { unit: spec.unit, label: spec.label })}
        <p class="fin-note">${finEsc(spec.label)} · 관측 ${usable}거래일 (${finEsc(win[0].date || '')} ~ ${finEsc(last.date || '')}) ·
            출처 ${finEsc(last.source || '—')}${soft ? ` · <span class="ms-missing">추정·부분 관측 ${soft}일 포함</span>` : ' · 전 구간 실측'}.
            휴장일은 채우지 않습니다.</p>
        ${spec.note ? `<p class="fin-note ms-warn">${finEsc(spec.note)}</p>` : ''}`;
};

// One window control per modal: the charts under it all read the same global,
// so repeating the buttons per chart would imply they can be set separately.
const msHistBlock = (specs) => {
    const list = specs.filter(Boolean);
    const drawable = list.some((s) => {
        const all = msSpecRows(s);
        const win = MS_HIST_PERIOD === 'all' ? all : all.slice(-Number(MS_HIST_PERIOD));
        return win.map(s.pick).filter(Number.isFinite).length >= MS_HIST_MIN_OBS;
    });
    return (drawable ? msHistPeriodBar() : '')
        + list.map((s, i) => (i ? `<h3 class="fin-sub">${finEsc(s.label)}</h3>` : '') + msHistChart(s)).join('');
};

const msMissing = (label) => `<span class="ms-missing">${finEsc(label || '데이터 없음')}</span>`;
const msNum = (v, d = 0) => Number.isFinite(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: d }) : '—';
const msJo = (v) => Number.isFinite(v) ? `${(v / 1e12).toFixed(2)}조` : '—';
// USD magnitudes. A null here means the issuer withheld a dated AUM or its
// daily target, which `null / 1e9` would have quietly rendered as $0.0B --
// the reading this panel exists to avoid.
const msUsdB = (v) => Number.isFinite(v) ? `$${(v / 1e9).toFixed(1)}B` : '미관측';
const msUsdM = (v) => Number.isFinite(v) ? `$${(v / 1e6).toFixed(0)}M` : '미관측';
// `letf_aum_quality`/product `aum_quality` distinguish KRX-reported net assets
// from a market-cap stand-in. Calling the MKTCAP fallback "실측" is exactly
// the overstatement this label exists to prevent.
const msAumProvenance = (q) => q === 'observed' ? '(순자산총액 관측)'
    : (q === 'proxy' || q === 'partial') ? '(시가총액 기반 순자산 프록시)' : '';

// Levered ETF turnover as a share of the two markets combined, rather than as
// a multiple of cash alone. Safe to add the two: FDR's KOSPI listing (개별
// 종목) and its ETF/KR listing are disjoint sets -- verified, zero overlapping
// codes -- so no trade is counted twice. Still not "all trading": non-levered
// ETFs and KOSDAQ are in neither term.
const msLevShareOfCombined = (cs) => {
    const cash = cs && cs.kospi_cash_tv_krw;
    const lev = cs && cs.levered_inverse_tv_krw;
    if (!Number.isFinite(cash) || !Number.isFinite(lev) || cash + lev <= 0) return null;
    return lev / (cash + lev);
};
const msSignedJo = (v) => Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${(v / 1e12).toFixed(2)}조` : '—';
const msEok = (v) => Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString('ko-KR')}억` : '—';
// msEok signs its output because it reports net flows. A balance is not a
// flow -- "+999,765억" of 예탁금 reads as an inflow of the entire deposit pool.
const msEokLevel = (v) => Number.isFinite(v) ? `${Math.round(v).toLocaleString('ko-KR')}억` : '—';
// KRW → 억 for option flows. A K200 option day is tens of 억, which the 조
// formatters above round to "-0.00조". Rounded before the sign is chosen so a
// −0.3억 day prints "0억", not "-0억".
const msKrwEok = (v) => {
    if (!Number.isFinite(v)) return '—';
    const r = Math.round(v / 1e8);
    return `${r > 0 ? '+' : ''}${r.toLocaleString('ko-KR')}억`;
};
const msKrwEokLevel = (v) => Number.isFinite(v) ? `${Math.round(v / 1e8).toLocaleString('ko-KR')}억` : '—';
const msShares = (v) => Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString('ko-KR')}` : '—';
const MS_LEVEL_CLASS = { '경계': 'ms-lv-3', '주의': 'ms-lv-2', '관찰': 'ms-lv-1', high: 'ms-lv-3', mid: 'ms-lv-2', watch: 'ms-lv-2', low: 'ms-lv-1', quiet: 'ms-lv-1' };

// Every summary box is a button that opens the table behind it. A card that
// shows a number but cannot be opened reads as data without an explanation.
const msCard = (title, value, sub, modalKey, cls) => `
    <button class="fin-card ms-card${modalKey ? ' ms-clickable' : ''}" ${modalKey ? `data-ms-modal="${finEsc(modalKey)}"` : 'disabled'}>
        <span class="fin-card-title">${finEsc(title)}</span>
        <span class="fin-card-value ${cls || ''}">${value}</span>
        ${sub ? `<p class="fin-card-plain">${sub}</p>` : ''}
        ${modalKey ? `<span class="ms-more">${/^(conc:|hist:|dir:|stock_letf:|letf_cat$|alert_letf$)/.test(String(modalKey)) ? '추이 보기' : '표 보기'} →</span>` : ''}
    </button>`;

// The three credit balances already have a same-date, per-series-scaled
// history view (the price-level chart's credit overlay) -- this opens that
// instead of a second chart, so 예탁금/신용융자/미수금 never end up compared
// on one shared numeric y-axis anywhere in the UI.
const msCreditCard = (title, value, sub) => `
    <button class="fin-card ms-card ms-clickable" data-ms-credit-open="1">
        <span class="fin-card-title">${finEsc(title)}</span>
        <span class="fin-card-value">${value}</span>
        ${sub ? `<p class="fin-card-plain">${sub}</p>` : ''}
        <span class="ms-more">추이 보기 →</span>
    </button>`;

const msTable = (head, rows) => `
    <div class="co-table-wrap">
        <table class="co-table">
            <thead><tr>${head.map((h) => `<th>${finEsc(h)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="co-label"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
    </div>`;

// Horizontal bars centred on zero: the Infomax-style read is "who bought at
// which price", and buying versus selling has to be legible at a glance.
const msDivergingBars = (rows, opts = {}) => {
    const all = rows.flatMap((r) => r.series.map((s) => s.value)).filter(Number.isFinite);
    const max = Math.max(...all.map(Math.abs), 1);
    return `
    <div class="ms-dist">
        ${rows.map((r) => `
            <div class="ms-dist-row${r.highlight ? ' on' : ''}">
                <span class="ms-dist-label">${finEsc(r.label)}${r.sub ? `<span>${finEsc(r.sub)}</span>` : ''}</span>
                <span class="ms-dist-bars">
                    ${r.series.map((sx) => {
                        const v = Number(sx.value);
                        const w = Number.isFinite(v) ? Math.abs(v) / max * 50 : 0;
                        const neg = v < 0;
                        return `<span class="ms-dist-track" title="${finEsc(sx.name)} ${msNum(v)}">
                            <span class="ms-dist-fill ms-${sx.key}${neg ? ' neg' : ''}"
                                  style="width:${w.toFixed(2)}%; ${neg ? 'right:50%' : 'left:50%'}"></span>
                        </span>`;
                    }).join('')}
                </span>
                <span class="ms-dist-val">${finEsc(r.valueText || '')}</span>
            </div>`).join('')}
        <div class="ms-dist-legend">
            ${(opts.legend || []).map((l) => `<span><i class="ms-sw ms-${l.key}"></i>${finEsc(l.name)}</span>`).join('')}
            <span class="ms-dist-zero">${finEsc(opts.zeroLabel || '가운데가 0 · 왼쪽 순매도 / 오른쪽 순매수')}</span>
        </div>
    </div>`;
};

// Bins are recomputed here rather than read from the snapshot because the
// shipped bins cover the whole 60-day window. Once the period can be narrowed,
// the bars have to be re-attributed over the same days the line is drawn from,
// or the profile would describe a window the chart is not showing.
const msBinDays = (pts, step) => {
    if (!pts.length) return [];
    const lo = Math.min(...pts.map((d) => d.close));
    const hi = Math.max(...pts.map((d) => d.close));
    const base = Math.floor(lo / step) * step;
    const map = new Map();
    pts.forEach((d) => {
        const b = Math.floor((d.close - base) / step);
        const cur = map.get(b) || { n_days: 0, retail: 0, foreign: 0, inst: 0 };
        cur.n_days += 1;
        cur.retail += d._retail || 0;
        cur.foreign += d._foreign || 0;
        cur.inst += d._inst || 0;
        map.set(b, cur);
    });
    return [...map.entries()].map(([b, v]) => ({
        price_lo: base + b * step, price_hi: base + (b + 1) * step, ...v,
    })).sort((a, b) => a.price_lo - b.price_lo).filter((r) => r.price_lo <= hi);
};

// Price-level distribution: the index path and the net-buying profile share one
// vertical price axis, so "where the index spent time" and "where each investor
// group actually bought" are read off the same rows. Two independent x scales
// overlay in one plot -- time for the line, net-buying value for the bars.
const MS_PLC_SERIES = [
    { key: 'retail', ko: '개인', cls: 'retail' },
    { key: 'foreign', ko: '외국인', cls: 'foreign' },
    { key: 'inst', ko: '기관', cls: 'inst' },
];

// Follows the cursor rather than snapping to a fixed offset from the chart,
// since the caller asked for the box to sit to the right of the pointer, not
// pinned above a data point the way the macro-tab tooltips are.
const msWirePlcHover = (host) => {
    host.querySelectorAll('.ms-plc-box').forEach((box) => {
        const tip = box.querySelector('.ms-plc-tip');
        if (!tip) return;
        let tips;
        try { tips = JSON.parse(box.dataset.msPlcTips || '[]'); } catch (_) { tips = []; }

        const place = (e) => {
            const margin = 12;
            let left = e.clientX + 16, top = e.clientY - 14;
            const tw = tip.offsetWidth, th = tip.offsetHeight;
            if (left + tw + margin > window.innerWidth) left = e.clientX - tw - 16;
            if (top + th + margin > window.innerHeight) top = window.innerHeight - th - margin;
            if (top < margin) top = margin;
            tip.style.left = `${left}px`;
            tip.style.top = `${top}px`;
        };

        box.querySelectorAll('[data-ms-tip-idx]').forEach((hit) => {
            const html = tips[Number(hit.dataset.msTipIdx)];
            if (!html) return;
            hit.addEventListener('mouseenter', (e) => { tip.innerHTML = html; tip.style.display = 'block'; place(e); });
            hit.addEventListener('mousemove', place);
            hit.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
        });
    });
};

const msPriceLevelChart = (pts, rows, opts = {}) => {
    if (pts.length < 2 || !rows.length) return '';
    // Wide: the bars fan out horizontally from a centre axis, so width is what
    // separates 개인/외국인/기관 at a glance -- a narrow box collapses them.
    const W = 1180, H = 440, L = 70, R = 110, T = 30, B = 34;
    const show = opts.series || MS_PLC_SERIES;

    const lo = Math.min(...pts.map((d) => d.close), ...rows.map((b) => b.price_lo));
    const hi = Math.max(...pts.map((d) => d.close), ...rows.map((b) => b.price_hi));
    const padY = (hi - lo) * 0.04 || 1;
    const yLo = lo - padY, yHi = hi + padY;
    const sy = (v) => T + (1 - (v - yLo) / (yHi - yLo)) * (H - T - B);

    // Bars are centred so net selling reads left of the axis.
    const vals = rows.flatMap((b) => show.map((s) => Number(b[s.key]))).filter(Number.isFinite);
    const vMax = Math.max(...vals.map(Math.abs), 1);
    const cx = L + (W - L - R) / 2;
    const halfW = (W - L - R) / 2;
    const sbx = (v) => (v / vMax) * halfW * 0.92;

    const sx = (i) => L + (i / Math.max(pts.length - 1, 1)) * (W - L - R);
    let line = '', pen = false;
    pts.forEach((d, i) => { line += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(d.close).toFixed(1)}`; pen = true; });

    // Credit rides the same date axis as the close line, so a deposit drain and
    // the index move it paid for line up vertically.
    //
    // Each series gets its OWN vertical range rather than a shared one. A shared
    // axis -- linear or log -- has to span 예탁금 ~127조 down to 미수금 ~1.9조,
    // and inside that span 신용융자 falling 38조 -> 27조 is a barely-tilted line,
    // even though a 29% drawdown in margin debt is the whole point of looking.
    // Normalising per series spends the full plot height on each one's own
    // move, so every slope is readable. The cost is that heights are no longer
    // comparable between lines -- which the legend and the note say outright,
    // and the hover still carries the real 조원 figures.
    const creditByDate = new Map((opts.credit || []).map((r) => [r.date, r]));
    const CREDIT_SERIES = [
        { key: 'investor_deposit_eok', ko: '투자자 예탁금', cls: 'deposit' },
        { key: 'credit_loan_eok', ko: '신용융자', cls: 'credit' },
        { key: 'uncollected_eok', ko: '미수금', cls: 'uncollected' },
        // 반대매매 is two orders of magnitude below 미수금 and spikier than
        // any of the others -- it is only legible at all because each series
        // gets its own vertical range.
        { key: 'forced_sale_eok', ko: '반대매매', cls: 'forced' },
    ];
    const creditJo = (d, key) => {
        const row = creditByDate.get(d.date);
        const v = row && row[key];
        return Number.isFinite(v) && v > 0 ? v / 10000 : null;
    };
    // Per-series span over the visible window, plus first/last for the legend.
    const creditStats = new Map(CREDIT_SERIES.map((s) => {
        const seen = pts.map((d) => creditJo(d, s.key)).filter((v) => v !== null);
        if (!seen.length) return [s.key, null];
        const lo2 = Math.min(...seen), hi2 = Math.max(...seen);
        const pad = (hi2 - lo2) * 0.12 || Math.abs(hi2) * 0.02 || 0.1;
        return [s.key, { lo: lo2 - pad, hi: hi2 + pad, first: seen[0], last: seen[seen.length - 1], min: lo2, max: hi2 }];
    }));
    const hasCredit = [...creditStats.values()].some((v) => v && v.hi > v.lo);
    const syC = (key, v) => {
        const st = creditStats.get(key);
        if (!st || st.hi === st.lo) return T + (H - T - B) / 2;
        return T + (1 - (v - st.lo) / (st.hi - st.lo)) * (H - T - B);
    };
    const creditPath = (key) => {
        let d = '', p = false;
        pts.forEach((pt, i) => {
            const v = creditJo(pt, key);
            if (v === null) { p = false; return; }
            d += `${p ? 'L' : 'M'}${sx(i).toFixed(1)},${syC(key, v).toFixed(1)}`;
            p = true;
        });
        return d;
    };
    // Everything here is carried in 조, but 반대매매 lives around 0.005~0.17조
    // and would print as "0.0조" for most of the window -- a real number
    // rendered as nothing. Below 0.5조 the label drops back to 억, its native
    // unit in the source.
    const joLabel = (v) => v < 0.5
        ? `${Math.round(v * 10000).toLocaleString('ko-KR')}억`
        : (v >= 10 ? v.toFixed(0) : v.toFixed(1)) + '조';
    const pctChg = (st) => (st && st.first ? ((st.last - st.first) / st.first) * 100 : null);

    const grid = Array.from({ length: 7 }, (_, i) => yLo + (yHi - yLo) * (i / 6));
    const fmt = opts.fmtX || msEok;

    // One tooltip box, precomputed per date so hover just swaps innerHTML --
    // no client-side re-formatting of krw/조/억 needed. 비중 is each group's
    // share of that day's total absolute flow, not a share of trading value
    // (which this chart doesn't carry), so it answers "who moved today" even
    // when the day's net is small.
    const flowRow = (label, v, pct) => `<span>${finEsc(label)}</span>
        <span class="${!Number.isFinite(v) || v === 0 ? '' : v > 0 ? 'fin-up' : 'fin-down'}">
            ${fmt(v)}${pct === null ? '' : ` <i>(${pct}%)</i>`}</span>`;
    const tipHtml = pts.map((d) => {
        const r = d._retail, f = d._foreign, ins = d._inst;
        const absSum = [r, f, ins].filter(Number.isFinite).reduce((s, v) => s + Math.abs(v), 0);
        const pct = (v) => (Number.isFinite(v) && absSum > 0) ? Math.round(Math.abs(v) / absSum * 100) : null;
        const credit = hasCredit ? CREDIT_SERIES.map((s) => {
            const v = creditJo(d, s.key);
            return v === null ? '' : `<span>${finEsc(s.ko)}</span><span>${joLabel(v)}</span>`;
        }).join('') : '';
        return `<div class="ms-plc-tip-date">${finEsc(d.date)}</div>
            <div class="ms-plc-tip-price">주가 ${msNum(d.close)}</div>
            <div class="ms-plc-tip-row">
                ${flowRow('개인', r, pct(r))}
                ${flowRow('외국인', f, pct(f))}
                ${flowRow('기관', ins, pct(ins))}
            </div>
            ${credit ? `<div class="ms-plc-tip-h">신용공여</div>
            <div class="ms-plc-tip-row">${credit}</div>` : ''}`;
    });

    return `
    <div class="ms-plc-box" data-ms-plc-tips='${finEsc(JSON.stringify(tipHtml))}'>
        <div class="ms-plc-tip"></div>
        <svg class="ms-plc" viewBox="0 0 ${W} ${H}" role="img"
             aria-label="${finEsc(opts.label || '가격대별 순매수 분포')}">
            ${grid.map((g) => `
                <line x1="${L}" y1="${sy(g).toFixed(1)}" x2="${W - R}" y2="${sy(g).toFixed(1)}" class="mm-grid"/>
                <text x="${L - 8}" y="${(sy(g) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${msNum(Math.round(g))}</text>`).join('')}
            ${[-1, -0.5, 0, 0.5, 1].map((t) => `
                <text x="${(cx + t * halfW * 0.92).toFixed(1)}" y="${H - 10}" class="mm-tick" text-anchor="middle">${fmt(t * vMax)}</text>`).join('')}
            ${rows.map((b, bi) => {
                const y0 = sy(b.price_hi), y1 = sy(b.price_lo);
                const band = Math.abs(y1 - y0);
                const h = Math.max(band / show.length - 1.5, 1.5);
                // rows here is msLevelsCompute's `bins` array, index-aligned with
                // the `rows` (label/series-shaped) array the modal reads --
                // "band:i" is only meaningful within one render, which is all
                // a click needs since it fires before the next repaint.
                const bandHit = opts.clickable === false ? '' : `<rect class="ms-plc-band-hit" data-ms-modal="band:${bi}"
                        x="${L}" y="${Math.min(y0, y1).toFixed(1)}" width="${(W - L - R).toFixed(1)}" height="${band.toFixed(1)}"/>`;
                return bandHit + show.map((s, si) => {
                    const v = Number(b[s.key]);
                    if (!Number.isFinite(v) || v === 0) return '';
                    const w = Math.abs(sbx(v));
                    const y = Math.min(y0, y1) + si * (band / show.length) + 0.75;
                    return `<rect class="ms-plc-bar ms-plc-${s.cls}${v < 0 ? ' neg' : ''}"
                        x="${(v < 0 ? cx - w : cx).toFixed(1)}" y="${y.toFixed(1)}"
                        width="${w.toFixed(1)}" height="${h.toFixed(1)}"><title>${
                        msNum(b.price_lo)}~${msNum(b.price_hi)} · ${s.ko} ${fmt(v)} · ${b.n_days}일</title></rect>`;
                }).join('');
            }).join('')}
            <line x1="${cx.toFixed(1)}" y1="${T}" x2="${cx.toFixed(1)}" y2="${H - B}" class="mm-zero"/>
            <path d="${line}" class="ms-plc-line"/>
            ${hasCredit ? CREDIT_SERIES.map((s) => `<path d="${creditPath(s.key)}" class="ms-plc-cr ms-plc-cr-${s.cls}"/>`).join('') : ''}
            ${hasCredit ? CREDIT_SERIES.map((s) => {
                const st = creditStats.get(s.key);
                if (!st) return '';
                // Each line ends at its own value, so the label goes at the line
                // end rather than on a shared axis that no longer exists.
                return `<text x="${W - R + 8}" y="${(syC(s.key, st.last) + 3.5).toFixed(1)}"
                    class="mm-tick ms-plc-cr-lab ms-plc-cr-${s.cls}">${joLabel(st.last)}</text>`;
            }).join('') : ''}
            ${pts.map((d, i) => `<rect x="${(sx(i) - (W - L - R) / pts.length / 2).toFixed(1)}" y="${T}"
                width="${((W - L - R) / pts.length).toFixed(1)}" height="${(H - T - B).toFixed(1)}" class="ms-plc-hit" data-ms-tip-idx="${i}"><title>${
                finEsc(d.date)} · ${finEsc(opts.lineName || '종가')} ${msNum(d.close)} · 개인 ${fmt(d._retail)} · 외국인 ${
                fmt(d._foreign)} · 기관 ${fmt(d._inst)}${hasCredit ? CREDIT_SERIES.map((s) => {
                    const v = creditJo(d, s.key);
                    return v === null ? '' : ` · ${s.ko} ${joLabel(v)}`;
                }).join('') : ''}</title></rect>`).join('')}
            <text x="${L - 8}" y="${T - 12}" class="mm-tick" text-anchor="end">${finEsc(opts.yLabel || '(pt)')}</text>
            <text x="${W - R + 8}" y="${(H - B).toFixed(1)}" class="mm-tick">${finEsc(opts.xLabel || '순매수')}</text>
        </svg>
        <p class="mm-legend-note">
            <i class="ms-plc-sw-line"></i>${finEsc(opts.lineName || '코스피 종가')}
            ${show.map((s) => `<i class="ms-plc-sw ms-plc-${s.cls}"></i>${finEsc(s.ko)}`).join('')}
        </p>
        ${hasCredit ? `<p class="mm-legend-note ms-plc-cr-legend">
            ${CREDIT_SERIES.map((s) => {
                const st = creditStats.get(s.key);
                if (!st) return '';
                const pc = pctChg(st);
                const cls = pc === null ? '' : (pc >= 0 ? 'fin-up' : 'fin-down');
                return `<span class="ms-plc-cr-item"><i class="ms-plc-sw-cr ms-plc-cr-${s.cls}"></i>${finEsc(s.ko)}
                    ${joLabel(st.first)} → ${joLabel(st.last)}
                    ${pc === null ? '' : `<b class="${cls}">${pc >= 0 ? '+' : ''}${pc.toFixed(1)}%</b>`}</span>`;
            }).join('')}
        </p>` : ''}
    </div>`;
};

// --- ① 수급 꼬임 -------------------------------------------------------------
// distortion_squeeze is documented as the top-level block, but the shipped
// snapshot has not produced it yet -- the same numbers live at the document's
// root instead (concentration, market_letf_derivatives_ratios,
// global_leverage_stack, stocks[]). DISTORTION_SQUEEZE.md names this fallback
// explicitly, so this reads the root fields rather than waiting on a key that
// may never land under that exact name.
const msTangle = (D) => {
    const m = D.micro || {};
    const conc = m.concentration || (D.conc || {}).latest || {};
    const stocks = Array.isArray(m.stocks) ? m.stocks : [];
    const sel = stocks.find((x) => x.ticker === MS_STOCK) || stocks[0] || null;
    const ratios = m.market_letf_derivatives_ratios || {};
    const stack = m.global_leverage_stack || {};
    const fvr = m.foreign_vs_retail || {};
    const dc = msCredit(D);
    const byDir = ratios.by_direction || {};
    const bands = m.ir_bands || {};
    const cs = m.letf_category_share || {};
    const ssCat = (cs.by_category || {}).single_stock || null;

    // Stress-sorted: the row worth looking at first is the one with the
    // biggest 10%-down impact, not the biggest name.
    const ranked = [...stocks].sort((a, b) =>
        (b.scenarios?.r_minus_10pct?.ir_pct ?? -1) - (a.scenarios?.r_minus_10pct?.ir_pct ?? -1));

    const bandCls = { low: 'ms-lv-1', mid: 'ms-lv-2', watch: 'ms-lv-2', high: 'ms-lv-3' };

    return `
    <section class="fin-block fin-block-wide">
        <h2>A · 코스피 집중도</h2>
        <p class="fin-lead">지수가 몇 종목에 얼마나 매달려 있는지입니다. 높을수록 그 종목의 사정이 곧 시장의 사정이 됩니다.</p>
        <div class="fin-cards">
            ${msCard('상위 2', Number.isFinite(conc.conc_top2_samsung_hynix_pct) ? conc.conc_top2_samsung_hynix_pct.toFixed(1) + '%' : '—',
                `상위 2종목 합계 · 전체 ${msNum((D.conc || {}).latest?.n_names)}종목 기준`, 'conc:top2')}
            ${msCard('상위 5', Number.isFinite(conc.conc_top5_pct) ? conc.conc_top5_pct.toFixed(1) + '%' : '—',
                `상위 5종목 합계 · 전체 ${msNum((D.conc || {}).latest?.n_names)}종목 기준`, 'conc:top5')}
            ${msCard('상위 10', Number.isFinite(conc.conc_top10_pct) ? conc.conc_top10_pct.toFixed(1) + '%' : '—',
                `상위 10종목 합계 · 전체 ${msNum((D.conc || {}).latest?.n_names)}종목 기준`, 'conc:top10')}
        </div>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>B · 시장 전체</h2>
        <p class="fin-lead">
            같은 분자(<strong>레버리지·인버스 ETF 거래대금</strong>)를 두 가지 분모로 나눠 나란히 둡니다.
            왼쪽은 코스피 현물만 분모로 둔 <em>배율</em>이라 100%를 넘을 수도 있고, 오른쪽은 둘을 합친
            <em>몫</em>이라 100%를 넘지 않습니다. 일반(비레버리지) ETF는 어느 쪽 분자에도 들어가지 않습니다.
        </p>
        <div class="fin-cards">
            ${msCard('레버·인버스 ETF ÷ 코스피 현물', Number.isFinite(ratios.levered_inverse_etf_tv_over_kospi_cash_tv_pct) ? ratios.levered_inverse_etf_tv_over_kospi_cash_tv_pct.toFixed(1) + '%' : '—',
                `정방향 ${msJo(ratios.long_tv_jo * 1e12)} · 인버스 ${msJo(ratios.inverse_tv_jo * 1e12)}`, 'letf_cat')}
            ${msCard('레버·인버스 ETF ÷ (코스피 현물 + 레버·인버스 ETF)', finPct(msLevShareOfCombined(cs), 1),
                Number.isFinite(cs.kospi_cash_tv_jo) && Number.isFinite(cs.levered_inverse_tv_jo)
                    ? `분모 ${(cs.kospi_cash_tv_jo + cs.levered_inverse_tv_jo).toFixed(2)}조 (현물 ${cs.kospi_cash_tv_jo.toFixed(2)}조 + 레버 ${cs.levered_inverse_tv_jo.toFixed(2)}조)`
                    : '', 'letf_cat')}
            ${ssCat ? msCard('그중 단일종목 (삼전·하닉)', msJo(ssCat.trading_value_krw),
                `레버·인버스 내 ${(ssCat.share_of_lev_tv_pct ?? 0).toFixed(1)}% · 코스피 현물 대비 ${(ssCat.share_of_kospi_tv_pct ?? 0).toFixed(2)}% · 상품 ${msNum(ssCat.n_products)}종`,
                'letf_cat') : ''}
        </div>
        <p class="fin-note">
            25%대로 보이는 값은 대부분 <strong>지수</strong> 레버리지(KODEX 레버리지·인버스 등)입니다.
            PDF/논문이 말하는 “AI 챔피언의 LETF 회전율”은 위 <strong>단일종목</strong> 카드 쪽입니다 —
            두 숫자를 같은 것으로 읽지 마세요.
        </p>
        <p class="fin-note">
            quality ${finEsc(ratios.quality || '—')} · 관측일 ${finEsc(m.as_of || '—')} · 출처 ${finEsc(ratios.source || '—')}.
            ${msHistRows('direction').length < MS_HIST_MIN_OBS ? '일별 이력이 쌓이는 중입니다 — 카드를 열면 관측일수가 표시되고, ' + MS_HIST_MIN_OBS + '거래일 이상 쌓이면 추이선이 나타납니다.' : '카드를 열면 일별 추이가 표시됩니다.'}
        </p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>C · 방향별 레버리지 상품</h2>
        <p class="fin-lead">인버스 안에서도 <strong>-2배</strong>는 따로 셉니다. 되사고 되파는 압력이 방향에 따라 다르게 쌓입니다.</p>
        ${Object.keys(byDir).length ? `
        <div class="fin-cards">
            ${[['long', '정방향 레버리지 (Long)'], ['inverse', '인버스 (-1X)'], ['inverse_2x', '인버스 (-2X)'], ['gobus_inverse_2x', '지수 인버스 (-2X)']].map(([k, ko]) => {
                const b = byDir[k]; if (!b) return '';
                return msCard(ko, msJo(b.trading_value_krw), `상품 ${msNum(b.n_products)}종 · 코스피 거래대금의 ${(b.share_of_kospi_tv_pct ?? 0).toFixed(1)}%`, `dir:${k}`);
            }).join('')}
        </div>` : `<p class="fin-note">${msMissing('라이브 재빌드 후 표시')}</p>`}
        <p class="fin-note">
            quality ${finEsc(ratios.quality || '—')} · 관측일 ${finEsc(m.as_of || '—')} · 출처 ${finEsc(ratios.source || '—')}.
            ${msHistRows('direction').length < MS_HIST_MIN_OBS ? '일별 이력이 쌓이는 중입니다 — 카드를 열면 관측일수가 표시되고, ' + MS_HIST_MIN_OBS + '거래일 이상 쌓이면 추이선이 나타납니다.' : '카드를 열면 일별 추이가 표시됩니다.'}
        </p>
        ${stack.global_stack_usd ? `
        <p class="fin-note">
            해외 레버 스택(규모 비교용, 국내 회전율에 합산하지 않음): KR ${msUsdB(stack.kr_single_stock_letf_notional_usd)} ·
            HK ${msUsdB(stack.hk_swap_letf_notional_usd)} · US ${msUsdB(stack.us_levered_etf_notional_usd)} ·
            crypto ${msUsdM(stack.crypto_perp_oi_notional_usd)}. ${finEsc(stack.hedge_channel_ko || '')}
        </p>
        ${(stack.global_stack_unobserved_venues || []).length ? `<p class="fin-note ms-warn">
            ${finEsc((stack.global_stack_unobserved_venues || []).join(' · ').toUpperCase())} 노셔널은 이 관측일에 비어 있어 합계에서 빠졌습니다 —
            규모가 줄어든 것이 아니라 <strong>관측되지 않은 것</strong>입니다. 합계를 전일과 비교하지 마세요.
        </p>` : ''}` : ''}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>D · 종목 스트레스</h2>
        <button class="mm-view-btn" data-ms-tab="overseas">삼성전자·하이닉스 해외 LETF 보기</button>
        <p class="fin-lead">
            2배 ETF 1좌는 기초자산 2좌만큼의 노출을 만듭니다. IR(Implied Rebalancing)은 그 노출을 되사고 되팔 때
            <strong>현물 당일 거래대금</strong> 대비 얼마나 큰 조정 노출이 되는지를 가정으로 표시합니다. 실제 리밸런싱 체결이나 가격 영향은 이 데이터만으로 확인할 수 없습니다.
        </p>
        <p class="fin-note">
            앞의 두 열은 <strong>분모의 정의가 같습니다</strong> — 둘 다 “해당 관측일의 한국 현물 거래대금”으로 나눈 값이라
            크기를 견줄 수 있습니다. 다만 <strong>같은 날이 아닙니다</strong>: 해외 수집은 국내 배치보다 보통 한 거래일 앞선 날짜까지만
            확정돼서, 홍콩 열에는 그 열의 관측일이 함께 표시됩니다. 날짜가 다르면 서로 다른 날의 거래대금으로 나눈 값입니다.
            그리고 <strong>더하지는 마세요.</strong> 국내 상품은 주문이 KRX에 직접 들어가지만, 홍콩 CSOP는 스왑이라 상대방(증권사)이
            자기 헤지를 하면서 <em>간접적으로</em> 현물에 닿습니다. 성격이 다른 압력입니다.
            −5%·−10% 가정 조정은 <strong>국내 상품만</strong> 계산에 넣습니다 — 홍콩 상품은 운용사가 당일 목표 배율을 공개하지 않아
            조정 물량을 계산할 수 없습니다 (가변 배율, 2026-08-03~).
        </p>
        ${stocks.length ? msTable(
            ['종목', '국내 LETF/현물 당일 거래대금', '홍콩 LETF/현물 당일 거래대금', '거래활동 밴드', '인버스 거래대금 비중', '−5% 가정 조정', '−10% 가정 조정', '밴드', ''],
            ranked.map((st) => {
                const t = st.flow_tangle || {};
                const s10 = st.scenarios?.r_minus_10pct, s5 = st.scenarios?.r_minus_5pct;
                // Same denominator as the domestic column -- the day's Korean
                // cash turnover -- which is the only reason these two can sit
                // side by side. They are still not added together: the CSOP
                // funds are swaps, so their pressure reaches KRX through a
                // counterparty's hedge rather than through the order book.
                const ext = st.external_vs_spot || {};
                const hkRatio = ext.hk_tv_over_kr_cash_tv;
                return [
                    `${finEsc(st.name)} <span class="co-hint">${finEsc(st.ticker)}</span>`,
                    finPct(st.letf_turnover_ratio),
                    Number.isFinite(hkRatio)
                        ? `${finPct(hkRatio)} <span class="co-hint">${finEsc((ext.hk_tv_tickers || []).join(' · '))}${
                            // Always shown, never only on mismatch: the day is
                            // what tells the reader whether the two columns
                            // share a denominator, and they usually do not.
                            ext.hk_tv_as_of ? ` · ${finEsc(ext.hk_tv_as_of)}${
                                ext.hk_tv_as_of !== m.as_of ? ` <b>(국내 ${finEsc(m.as_of || '—')})</b>` : ''}` : ''}</span>`
                        : '—',
                    `<span class="ms-badge ${bandCls[t.wag_the_dog_band] || ''}">${finEsc(t.wag_the_dog_band || '—')}</span>`,
                    finPct(t.inverse_tv_share),
                    Number.isFinite(s5?.ir_pct) ? s5.ir_pct.toFixed(1) + '%' : '—',
                    Number.isFinite(s10?.ir_pct) ? `<span class="ms-badge ${bandCls[s10.band] || ''}">${s10.ir_pct.toFixed(1)}%</span>` : '—',
                    `<span class="ms-badge ${bandCls[t.realized_band] || ''}">${finEsc(t.realized_band || '—')}</span>`,
                    `<button class="mm-view-btn" data-ms-stock="${finEsc(st.ticker)}" data-ms-modal="letf_products">상품별</button>`
                    // Every stock in this table routes to the same generic
                    // trend view, Hynix included. Its separate bucket-alert
                    // engine (win-rate by ratio band) still exists but only
                    // via the alert card in the US→KR tab -- routing the D
                    // row there too meant "추이" opened a different snapshot
                    // date than the rest of this table without saying so.
                    + (Number.isFinite(st.letf_turnover_ratio)
                        ? ` <button class="mm-view-btn" data-ms-modal="stock_letf:${finEsc(st.ticker)}">추이</button>`
                        : ''),
                ];
            })) : `<p class="fin-note">${msMissing('종목 스트레스 데이터 없음')}</p>`}
        <p class="fin-note">IR 밴드: 가정된 조정 노출 ÷ 현물 당일 거래대금입니다 (watch ≥ ${bands.watch_lt_pct ?? 10}% · low &lt; ${bands.low_lt_pct ?? 3}%). NAV는 공개 스냅샷에 없어 표시하지 않습니다 — 거래대금은 실측이며, 순자산(AUM)은 KRX 실측 또는 시가총액 기반 프록시입니다 (상품별 표에서 구분).</p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>E · 해석 힌트</h2>
        <ul class="fin-list">
            <li>거래활동 밴드가 높음 → LETF 거래대금이 현물 당일 거래대금과 비교해 큰 날이라는 관측값입니다. 실제 가격 영향은 별도 체결 자료로 검증해야 합니다.</li>
            <li>−10% 가정 조정 ≥ ${bands.watch_lt_pct ?? 10}% → 해당 가격 충격 가정에서 계산된 조정 노출이 현물 당일 거래대금 대비 큰 값입니다.</li>
            <li>인버스 비중은 당일 LETF 거래대금 중 인버스 상품의 비중입니다. 투자자 보유 포지션·숏커버·실제 리밸런싱 방향을 뜻하지 않습니다.</li>
        </ul>
        <p class="fin-note">${finEsc((m.broker_leverage_disclosure || {}).note_ko || '증권사 고객 레버리지 공시가 아닙니다. 공개 LETF AUM·거래대금 기반 프록시입니다.')}</p>
    </section>`;
};


// Overseas metrics are calculated by the collector, never by this renderer.
const MS_OVERSEAS_GROUPS = [
    ['hynix', 'SK하이닉스 · 한국 보통주', (p) => p.scope === 'kr_single_stock' && p.underlying_ticker === '000660'],
    ['samsung', '삼성전자 · 한국 보통주', (p) => p.scope === 'kr_single_stock' && p.underlying_ticker === '005930'],
    ['adr', 'SK하이닉스 · 미국 ADR', (p) => p.scope === 'kr_adr_single_stock'],
    ['global', '한국 바스켓·미국 지수·업종 비교', (p) => ['kr_basket', 'global_index', 'global_sector'].includes(p.scope)],
];
const MS_OVERSEAS_STRUCTURES = { swap: '스왑', futures: '선물', physical_margin: '현물·차입', derivatives_and_collateral: '파생·담보', mixed: '혼합' };
const msOverseas = (D) => {
    const board = D.overseas;
    if (!board?.products?.length) return '<section class="fin-block"><h2>해외 LETF</h2><p>해외 수집 자료를 아직 받지 못했습니다.</p></section>';
    const group = MS_OVERSEAS_GROUPS.find((g) => g[0] === MS_OVERSEAS_GROUP) || MS_OVERSEAS_GROUPS[0];
    const products = board.products.filter(group[2]);
    const p = products.find((x) => x.product_id === MS_OVERSEAS_PRODUCT) || products[0];
    if (!p) return '<p>선택한 대상의 상품이 없습니다.</p>';
    const latest = p.latest || {}, aum = p.latest_aum, cap = p.capital_structure;
    const usd = (v) => Number.isFinite(v) ? `$${msNum(v / 1e6, 2)}M` : '—';
    const leverage = (x) => Number.isFinite(x.latest?.leverage) ? `${x.latest.leverage > 0 ? '+' : ''}${x.latest.leverage}배`
        : Number.isFinite(x.leverage_ceiling) ? `최대 ${x.leverage_ceiling}배 · 실제 목표 미공개` : '목표 미확인';
    const label = (x) => x.listings.map((l) => l.ticker).join(' / ');
    const rows = msHistRows('overseas').filter((r) => r.product_id === p.product_id);
    const specs = [
        ['거래대금 프록시 · 확보분', 'USD M', (r) => Number.isFinite(r.covered_trading_value_usd) ? r.covered_trading_value_usd / 1e6 : null,
            '동일 거래일 종가 × 거래량. 확보한 거래통화의 합계이며 거래소 실측 거래대금과 다릅니다.'],
        [`거래량 · ${latest.primary_listing_id || p.listings[0]?.ticker || ''}`, '좌', (r) => msFinite(r.primary_volume)],
        ['순자산 (AUM)', 'USD M', (r) => Number.isFinite(r.aum_usd) ? r.aum_usd / 1e6 : null, '기준일이 있는 운용사 AUM만 사용합니다.'],
        ['LETF / 한국 현물 거래대금', '%', (r) => Number.isFinite(r.etf_to_kr_cash_tv_ratio) ? r.etf_to_kr_cash_tv_ratio * 100 : null,
            '같은 날짜의 해당 한국 보통주 현물 거래대금이 분모입니다. ADR·바스켓에는 적용하지 않습니다.'],
        ['추정 리밸런싱', 'USD M', (r) => Number.isFinite(r.implied_rebalance_usd) ? r.implied_rebalance_usd / 1e6 : null,
            '양수=매수 방향, 음수=매도 방향. 전일 AUM·실제 목표·동일 자산/통화 수익률이 있어야 계산하는 일일 리셋 추정치입니다. 실제 주문·체결이 아닙니다.'],
    ].map(([label, unit, pick, note]) => ({ rows, label, unit, pick, note }));
    const typeNames = { equity: '주식', futures: '선물', swap: '스왑', options: '옵션', cash_collateral: '현금·담보', fund: '펀드' };
    const composition = (p.composition || []).filter((c) => Number.isFinite(c.signed_weight_pct));
    const bars = (items, unit, zeroLabel) => msDivergingBars(items.map(([label, value]) => ({ label,
        series: [{ name: label, key: 'foreign', value }], valueText: `${msNum(value, 2)}${unit}` })), { zeroLabel });
    return `<section class="fin-block fin-block-wide" data-ms-overseas="1">
        <style>
            [data-ms-overseas] .mm-tabs { flex-wrap:wrap; }
            [data-ms-overseas] label { display:grid; gap:6px; max-width:100%; }
            [data-ms-overseas] select { max-width:100%; min-width:0; background:var(--bg-secondary); color:var(--text-primary); padding:8px; }
            [data-ms-overseas] .ms-dist-row { grid-template-columns:minmax(70px,1fr) minmax(50px,2fr) minmax(85px,auto); gap:8px; }
            [data-ms-overseas] .ms-dist-val { display:block; font-size:12px; }
        </style>
        <h2>해외 LETF · 거래와 상품 구성</h2>
        <div class="mm-tabs">
            <label>비교 대상 <select data-ms-overseas-group>${MS_OVERSEAS_GROUPS.map(([id, text]) => `<option value="${id}" ${id === group[0] ? 'selected' : ''}>${finEsc(text)}</option>`).join('')}</select></label>
            <label>상품 상세 <select data-ms-overseas-product>${products.map((x) => `<option value="${finEsc(x.product_id)}" ${x === p ? 'selected' : ''}>${finEsc(label(x))}</option>`).join('')}</select></label>
        </div>
        <p class="fin-note">선별 ${board.products.length}종 · 수집 ${finEsc(board.pipeline?.last_attempt_at || board.generated_at || '—')} ·
            ${finEsc(({ok:'정상', partial:'일부 자료 미확보', failed:'수집 실패 · 이전 정상 자료 표시'})[board.pipeline?.status] || '상태 미확인')} · 상품별 관측일을 확인하세요.</p>
        ${msTable(['상품 / 거래통화', '관측일', '목표', '구조', '거래대금 프록시 (USD)', '동일 대상 확보분 비중', '거래통화 확보'], products.map((x) => {
            const l = x.latest || {};
            return [finEsc(label(x)), finEsc(l.date || '—') + (x.stale ? ' · 지연' : ''), finEsc(leverage(x)),
                finEsc(MS_OVERSEAS_STRUCTURES[x.structure] || x.structure), usd(l.covered_trading_value_usd),
                Number.isFinite(l.covered_turnover_share_pct) ? `${msNum(l.covered_turnover_share_pct, 2)}%` : '—',
                `${l.valued_listing_count ?? l.observed_listing_count ?? 0}/${l.expected_listing_count ?? x.listings.length}`];
        }))}
        <p class="fin-note">비중의 분모는 같은 날짜·같은 기준자산의 선별 상품 확보분입니다. 세계 시장점유율이나 투자자 포지션이 아닙니다. 서로 다른 지수·ADR·보통주는 분모를 합치지 않습니다.</p>
        ${bars(products.filter((x) => Number.isFinite(x.latest?.covered_trading_value_usd)).map((x) => [x.listings[0].ticker, x.latest.covered_trading_value_usd / 1e6]), 'M USD', '거래대금 프록시 · 상품별 위 표의 관측일')}
        <h3>${finEsc(p.name)}</h3>
        <p class="fin-note">${finEsc(leverage(p))} · 구조 ${finEsc(MS_OVERSEAS_STRUCTURES[p.structure] || p.structure)} (${finEsc(p.structure_as_of || p.verified_on || '—')}) ·
            AUM ${aum ? `${msNum(aum.aum_native, 2)} ${finEsc(aum.currency)} (${finEsc(aum.date)})` : '미공개/미확보'}</p>
        ${msTable(['거래소', '거래통화', '통화별 거래량 (좌)', '상장 상태'], p.listings.map((l) => [finEsc(l.venue), finEsc(`${l.ticker} · ${l.currency}`),
            msNum(latest.volume_by_listing?.find((v) => v.listing_id === l.listing_id)?.volume),
            finEsc(l.last_trade_date ? `최종 거래 ${l.last_trade_date}` : l.status || '등록 상장')]))}
        <h3>상품 내부 구성 · NAV 대비 부호 있는 노출</h3>
        <p class="fin-note">${finEsc(p.holdings_as_of || '비중 기준일 미확보')} · 100% 초과·음수를 그대로 표시합니다. 투자 가능 수단과 실제 보유 비중은 다릅니다.</p>
        ${composition.length ? bars(composition.map((c) => [typeNames[c.holding_type] || c.holding_type, c.signed_weight_pct]), '%', '왼쪽 음수 / 오른쪽 양수 · 합계를 100%로 바꾸지 않음') : '<p>공식 상세 비중 미확보 · 확인된 상품 구조만 표시합니다.</p>'}
        ${(p.composition || []).filter((c) => !Number.isFinite(c.signed_weight_pct)).map((c) => `<p class="fin-note">${finEsc(typeNames[c.holding_type] || c.holding_type)}: 비중 미공개</p>`).join('')}
        ${cap ? `<h3>운용사 자산·차입 구성 (${finEsc(cap.date)})</h3>${bars([['기초자산', cap.underlying_assets_usd / 1e6], ['부채', -cap.liabilities_usd / 1e6], ['순자산', cap.aum_usd / 1e6]], 'M USD', '자산−부채=순자산 · 계약별 비중은 별도 미확보')}` : ''}
        <h3>상품별 일별 추이</h3>${msHistBlock(specs)}
        <p class="fin-note">상품·구성 근거: ${(p.source_urls || []).filter((u) => /^https:\/\//.test(u)).map((u, i) => `<a href="${finEsc(u)}" target="_blank" rel="noopener noreferrer">운용사 ${i + 1}</a>`).join(' · ')} · 시세 Yahoo Finance.</p>
    </section>`;
};

// --- ② 가격대별 수급 ---------------------------------------------------------
// Shared by the chart (msLevelsTab) and its detail modal so the two never
// disagree about which days/step/bins the ticker+period selection means.
const msLevelsCompute = (D) => {
    const lv = D.levels || {};
    const kl = lv.kospi_index_levels || {};
    const tickers = lv.tickers || {};
    const isIndex = !MS_TICKER;
    const src = isIndex ? kl : (tickers[MS_TICKER] || {});

    // Everything is normalised to 억원 so the index (already 억) and a single
    // ticker (raw 원) can be read on one axis without a unit toggle.
    const allDays = (src.days || []).filter((d) => Number.isFinite(d.close)).map((d) => ({
        date: d.date, close: d.close,
        _retail: isIndex ? d.retail_net_eok : (d.retail_net_krw || 0) / 1e8,
        _foreign: isIndex ? d.foreign_net_eok : (d.foreign_net_krw || 0) / 1e8,
        _inst: isIndex ? d.institution_net_eok : (d.institution_net_krw || 0) / 1e8,
    }));
    const nWindow = { '1m': 21, '2m': 42, '3m': 63, '6m': 126, all: allDays.length }[MS_PERIOD] ?? allDays.length;
    const pts = allDays.slice(-Math.max(nWindow, 2));
    // Index bins follow the published psychological step; a single name has no
    // such convention, so its range is split into a comparable number of rows.
    const step = isIndex ? (kl.step || 250)
        : Math.max((Math.max(...pts.map((d) => d.close)) - Math.min(...pts.map((d) => d.close))) / 12, 1);
    const bins = msBinDays(pts, step);

    const rows = bins.filter((b) => b.n_days > 0).map((b) => ({
        label: `${msNum(b.price_lo)} ~ ${msNum(b.price_hi)}`,
        sub: `${b.n_days}일`,
        series: [
            { key: 'retail', name: '개인', value: b.retail },
            { key: 'foreign', name: '외국인', value: b.foreign },
            { key: 'inst', name: '기관', value: b.inst },
        ],
        valueText: `개인 ${msEok(b.retail)} · 외인 ${msEok(b.foreign)}`,
    }));

    return { isIndex, src, tickers, allDays, pts, bins, rows };
};

// Ticker buttons follow the selected universe, in the engine's own order
// (market-cap rank, or realised-volatility rank). Object.keys(tickers) is
// neither: JS lists integer-like keys ("105560") ahead of zero-padded ones
// ("005930"), so the old slice(0, 8) showed whichever names sorted first --
// mid-caps ahead of Samsung and Hynix -- and cut the rest, regardless of
// which universe the toggle said was active.
const msUniverseTickers = (lv, tickers) => {
    const meta = lv.universe_meta || {};
    const codes = MS_UNIVERSE === 'high_vol'
        ? ((meta.high_vol_in_marcap_top || {}).pairs || []).map((p) => p[0])
        : ((meta.marcap_top || {}).tickers || []).map((t) => t.ticker);
    const list = codes.filter((c) => tickers[c]);
    // A name chosen earlier stays visible even if the other universe lacks it.
    if (MS_TICKER && tickers[MS_TICKER] && !list.includes(MS_TICKER)) list.push(MS_TICKER);
    return list.length ? list : Object.keys(tickers).slice(0, 10);
};

const msLevelsTab = (D) => {
    const lv = D.levels || {};
    const dc = msCredit(D);
    const kl = lv.kospi_index_levels || {};
    const { isIndex, src, tickers, allDays, pts, bins, rows } = msLevelsCompute(D);

    const table = MS_UNIVERSE === 'high_vol' ? (lv.close_day_table_high_vol || []) : (lv.close_day_table_marcap || []);
    const L = kl.latest || {};

    return `
    <section class="fin-block fin-block-wide">
        <h2>가격대별 누적 수급 <span class="ms-q">${finEsc(src.quality || '')}</span></h2>
        <p class="fin-lead">
            어느 가격대에서 누가 사고 팔았는지를 실측 일별 수급으로 쌓은 것입니다.
            <strong>체결 단위 매집도가 아닙니다</strong> — 그 데이터는 공개되지 않습니다.
        </p>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${isIndex ? 'on' : ''}" data-ms-ticker="">코스피 지수</button>
            ${msUniverseTickers(lv, tickers).map((tk) => `<button class="mm-view-btn ${MS_TICKER === tk ? 'on' : ''}"
                data-ms-ticker="${finEsc(tk)}">${finEsc(tickers[tk].label_ko || tk)}</button>`).join('')}
        </div>
        ${src.headline_ko && MS_PERIOD === 'all' ? `<p class="ms-lead-strong">${finEsc(src.headline_ko)}</p>` : ''}
        <div class="co-struct-toggle ms-period-row">
            ${[['1m', '1개월'], ['2m', '2개월'], ['3m', '3개월'], ['6m', '6개월'], ['all', `전체 (${allDays.length}일)`]]
                .filter(([k]) => k === 'all' || ({ '1m': 21, '2m': 42, '3m': 63, '6m': 126 })[k] < allDays.length)
                .map(([k, ko]) =>
                `<button class="mm-view-btn ${MS_PERIOD === k ? 'on' : ''}" data-ms-period="${k}">${finEsc(ko)}</button>`).join('')}
            <span class="ms-period-spacer"></span>
            <button class="mm-view-btn ${MS_CREDIT_ON ? 'on' : ''}" data-ms-credit="1">예탁금 · 신용공여 ${MS_CREDIT_ON ? '▲' : '▼'}</button>
        </div>
        ${MS_CREDIT_ON ? `<p class="fin-note ms-credit-hint">
            아래 그래프에 예탁금 · 신용융자 · 미수금 · 반대매매가 <strong>같은 날짜축</strong>으로 겹쳐집니다.
            셋은 규모가 100배 넘게 차이나서 <strong>각자의 범위로</strong> 그렸습니다 —
            선끼리 높이를 비교하지 마시고 <em>기울기</em>만 보세요. 실제 금액은 아래 범례와 마우스 올린 값에 있습니다.
            시장 전체 집계이며 종목별이 아닙니다.</p>` : ''}
        ${msPriceLevelChart(pts, bins, {
            label: `${isIndex ? '코스피' : (tickers[MS_TICKER] || {}).label_ko || MS_TICKER} 가격대별 투자자 순매수 분포`,
            lineName: isIndex ? '코스피 종가' : '종가',
            yLabel: isIndex ? '(pt)' : '(원)',
            xLabel: '순매수(억원)',
            credit: MS_CREDIT_ON ? (dc.history || []) : null,
        })}
        ${pts.length ? `<p class="fin-note">표시 구간 ${finEsc(pts[0].date)} ~ ${finEsc(pts[pts.length - 1].date)} · ${pts.length}거래일.
            막대는 이 구간의 일별 순매수를 종가 레벨에 귀속해 다시 합산한 값입니다.</p>` : ''}
        ${rows.length
            ? `<button class="mm-view-btn" data-ms-modal="price_level_detail">가격대별 상세 표 (${rows.length}개 구간) →</button>`
            : `<p class="fin-note">${msMissing('구간별 수급 없음')}</p>`}
        <p class="fin-note">
            ${finEsc(src.method_ko || '')} 단위 억원 · quality ${finEsc(src.quality || '—')} ·
            원본 ${src.n_days || 0}일 (${finEsc(src.date_start || '')} ~ ${finEsc(src.date_end || '')}) ·
            출처 ${finEsc([].concat(src.source || '—').join(' · '))}
        </p>
        ${isIndex && src.scope_ko ? `<p class="fin-note ms-warn">${finEsc(src.scope_ko)}</p>` : ''}
        ${isIndex ? msStaleNote('코스피 시장 투자자별 수급', src.flow_date_end || src.date_end) : ''}
        ${isIndex && src.quality !== 'observed' ? `<p class="fin-note">${msMissing('코스피 시장 수급이 비어 있습니다')} — 위 종목 버튼은 종목별 수급으로 따로 그려집니다.</p>` : ''}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>종가일 수급</h2>
        <div class="co-struct-toggle">
            <button class="mm-view-btn ${MS_UNIVERSE === 'marcap' ? 'on' : ''}" data-ms-univ="marcap">시총 상위</button>
            <button class="mm-view-btn ${MS_UNIVERSE === 'high_vol' ? 'on' : ''}" data-ms-univ="high_vol">시총 100위 내 고변동</button>
        </div>
        ${table.length ? msTable(['종목', '날짜', '종가', '개인(주)', '외국인(주)', '기관(주)', ''],
            table.map((r) => [
                `${finEsc(r.label_ko)} <span class="co-hint">${finEsc(r.ticker)}</span>`,
                finEsc(r.date || ''), msNum(r.close),
                `<span class="${r.retail_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.retail_net_shares)}</span>`,
                `<span class="${r.foreign_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.foreign_net_shares)}</span>`,
                `<span class="${r.institution_net_shares >= 0 ? 'fin-up' : 'fin-down'}">${msShares(r.institution_net_shares)}</span>`,
                tickers[r.ticker] ? `<button class="mm-view-btn" data-ms-ticker="${finEsc(r.ticker)}">가격대별</button>
                    <button class="mm-view-btn" data-ms-modal="week:${finEsc(r.ticker)}:${finEsc(r.date)}">그 주 →</button>` : '',
            ])) : `<p class="fin-note">${msMissing('종가일 표 없음')}</p>`}
        <p class="fin-note">지수 순매수 최근일: 개인 ${msEok(L.retail_net_eok)} · 외국인 ${msEok(L.foreign_net_eok)} · 기관 ${msEok(L.institution_net_eok)} (${finEsc(L.date || '')})</p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>투자자 예탁금 · 신용공여</h2>
        <p class="fin-lead">
            개인이 얼마를 들고 대기 중이고 얼마를 빌려서 사고 있는지입니다. 위 가격대별 수급이 <em>어디서</em> 샀는지라면,
            이건 <em>무슨 돈으로</em> 샀는지입니다.
        </p>
        <div class="fin-cards">
            ${msCard('신용공여 잔고 / 투자자 예탁금', Number.isFinite(dc.credit_over_deposit_pct) ? dc.credit_over_deposit_pct.toFixed(1) + '%' : '—',
                `기준일 ${finEsc(dc.as_of || '—')}`, null)}
            ${msCreditCard('투자자 예탁금', msEokLevel(dc.investor_deposit_eok),
                Number.isFinite(dc.investor_deposit_chg_eok) ? `전주 대비 ${msEok(dc.investor_deposit_chg_eok)}` : '')}
            ${msCreditCard('신용융자 잔고', msEokLevel(dc.credit_balance_eok),
                Number.isFinite(dc.credit_balance_chg_eok) ? `전주 대비 ${msEok(dc.credit_balance_chg_eok)}` : '')}
            ${msCreditCard('위탁매매 미수금', msEokLevel(dc.uncollected_eok),
                Number.isFinite(dc.uncollected_over_deposit_pct) ? `예탁금 대비 ${dc.uncollected_over_deposit_pct.toFixed(2)}%` : '')}
            ${msCreditCard('반대매매', msEokLevel(dc.forced_sale_eok),
                Number.isFinite(dc.forced_sale_over_uncollected_pct) ? `미수금 대비 ${dc.forced_sale_over_uncollected_pct.toFixed(1)}%` : '')}
        </div>
        <p class="fin-note">${finEsc(dc.note_ko || '')}
            추이 그래프는 위 <strong>가격대별 누적 수급</strong>의 “예탁금 · 신용공여” 버튼에 있습니다.</p>
        ${(lv.cannot_do_ko || []).length ? `
        <details class="mm-limits">
            <summary>이 데이터로 할 수 없는 것</summary>
            ${lv.cannot_do_ko.map((x) => `<div class="mm-limit"><p>${finEsc(x)}</p></div>`).join('')}
        </details>` : ''}
    </section>`;
};

// --- ③ US → KR 관찰 ----------------------------------------------------------
const msUsKr = (D) => {
    const t = D.transmission || {};
    const gs = t.global_spillover || {};
    const a = D.alerts || {};
    const b = D.board || {};
    const ch = t.channels || {};
    const [lvl, dir] = String(t.headline || '').split(':');
    const dirKo = { downside: '하방', upside: '상방', vol_up: '변동성 확대', vol_down: '변동성 축소' }[dir] || dir || '';
    const ev = Array.isArray(t.evidence_us) ? t.evidence_us : [];
    const letf = a.kr_hynix_letf || {};
    const vix = a.us_vix_to_kr || {};
    // `kospi_open30m_prior` is generated by the L3 pipeline.  It contains
    // driver-level return buckets, not a single forecast score.  Keep it
    // driver-level in the UI rather than synthesising a headline statistic.
    const open30m = t.kospi_open30m_prior || {};
    const open30mRows = Object.entries(open30m.channels || {}).map(([symbol, row]) => {
        const down = row?.open30m_us_down || {};
        const baseline = row?.open30m_baseline || {};
        return [
            finEsc(symbol),
            msNum(down.n),
            finPct(down.mean, 2),
            finPct(down.frac_neg),
            msNum(baseline.n),
            finPct(baseline.mean, 2),
            finPct(baseline.frac_neg),
        ];
    });

    return `
    <section class="fin-block fin-block-wide">
        <h2>현재 관찰되는 US → KR 연결</h2>
        <div class="ms-headline">
            <span class="ms-head-level ${MS_LEVEL_CLASS[lvl] || ''}">${finEsc(gs.headline_ko || t.headline_ko || `${lvl} · ${dirKo}`)}</span>
            <span class="ms-head-meta">기준 ${finEsc(gs.as_of || t.as_of || '')} · 모델 ${finEsc(t.model_version || '')}</span>
        </div>
        ${gs.why_short_ko || t.why_ko ? `<p class="ms-why">${finEsc(gs.why_short_ko || t.why_ko)}</p>` : ''}
        <p class="fin-note ms-warn">
            이는 공개 옵션·가격 데이터에서 잡힌 <strong>현재의 연결 상태</strong>입니다. 미래 수익률·방향을 예측하지 않으며,
            투자 주체나 실제 헤지 목적도 특정하지 않습니다.
        </p>
        ${ev.length ? `
        <h3 class="fin-sub">미국 쪽 실측 근거</h3>
        ${msTable(['심볼', '레짐', '스트레스', 'P/C 거래량', 'P/C OI', '옵션 거래량', '공매 증감'],
            ev.map((e) => [
                `<button class="ms-link" data-ms-modal="ev:${finEsc(e.symbol)}">${finEsc(e.symbol)}</button>`,
                (e.regimes || []).join(', '),
                `<span class="ms-badge ${MS_LEVEL_CLASS[e.stress_level] || ''}">${finEsc(e.stress_level || '')}</span>`,
                Number.isFinite(e.put_call_volume) ? e.put_call_volume.toFixed(2) : '—',
                Number.isFinite(e.put_call_oi) ? e.put_call_oi.toFixed(2) : '—',
                msNum(e.options_total_volume),
                Number.isFinite(e.short_chg_pct) ? `<span class="${e.short_chg_pct >= 0 ? 'fin-down' : 'fin-up'}">${e.short_chg_pct.toFixed(1)}%</span>` : '—',
            ]))}
        <p class="fin-note">P/C = 풋 ÷ 콜입니다. 1보다 크면 그날 풋 거래가 상대적으로 많았다는 관찰값일 뿐, 하락 예측이 아닙니다. 심볼을 누르면 산식이 나옵니다.</p>` : ''}
    </section>

    <section class="fin-block fin-block-wide">
        <h2>연결 채널</h2>
        <div class="ms-channels">
            ${[['downside', '하방'], ['upside', '상방'], ['vol_up', '변동성 확대'], ['vol_down', '변동성 축소']].map(([k, ko]) => {
                const c = ch[k] || {};
                // A single IV level plus call/put volume cannot tell long-vol
                // from short-vol apart -- the engine only fires vol_up/down
                // when a comparable IV-change observation exists, and flags
                // `observable:false` otherwise. Showing "quiet" in that case
                // would read as a judgement the data cannot support.
                const unobservable = (k === 'vol_up' || k === 'vol_down') && c.observable === false;
                return `
                <button class="ms-channel${k === dir ? ' on' : ''}${(c.drivers || []).length ? ' ms-clickable' : ''}"
                        ${(c.drivers || []).length ? `data-ms-modal="ch:${k}"` : 'disabled'}>
                    <span class="ms-ch-name">${finEsc(ko)}</span>
                    <span class="ms-ch-heat">${Number.isFinite(c.heat) ? c.heat.toFixed(1) : '—'}</span>
                    <span class="ms-ch-lv">${unobservable ? '판정 불가' : finEsc(c.level || '—')}</span>
                    ${unobservable && c.unavailable_reason_ko ? `<span class="ms-ch-tick">${finEsc(c.unavailable_reason_ko)}</span>`
                        : (c.kr_tickers || []).length ? `<span class="ms-ch-tick">${c.kr_tickers.map(finEsc).join(' · ')}</span>` : ''}
                </button>`;
            }).join('')}
        </div>
        <p class="fin-note">heat는 미국 쪽 레짐 강도 × 링크 가중의 합입니다. 채널을 누르면 어떤 연결이 얼마나 기여했는지 나옵니다.</p>
    </section>

    <section class="fin-block fin-block-wide">
        <h2>알림 레벨</h2>
        <div class="fin-cards">
            ${msCard('하닉 레버리지 ETF 비율',
                `<span class="ms-badge ${MS_LEVEL_CLASS[letf.today_level] || ''}">${finEsc(letf.today_level || '—')}</span> ${Number.isFinite(letf.today_ratio) ? finPct(letf.today_ratio) : ''}`,
                finEsc(letf.metric_ko || ''), 'alert_letf')}
            ${msCard('US VIX → KR',
                `<span class="ms-badge ${MS_LEVEL_CLASS[vix.latest_level] || ''}">${finEsc(vix.latest_level || '—')}</span>${
                    Number.isFinite(vix.latest_vix) ? ` VIX ${vix.latest_vix.toFixed(1)}` : ''}${
                    Number.isFinite(vix.latest_vix_r) ? ` (${(vix.latest_vix_r * 100).toFixed(1)}%)` : ''}`,
                finEsc(vix.metric_ko || ''), 'alert_vix')}
            ${msCard('US OI 룰 헤드라인',
                `<span class="ms-badge ${MS_LEVEL_CLASS[(b.us_kr_rules || {}).headline_level] || ''}">${finEsc((b.us_kr_rules || {}).headline_level || '—')}</span>`,
                '', null)}
        </div>
        <p class="fin-note">
            VIX 알림은 Cboe 공식 VIX의 전일 대비 변화율입니다 — <strong>풋 미결제약정(OI)이 아닙니다.</strong>
            종목 단위 풋 OI 히스토리가 공개되지 않아 그 임계값은 만들 수 없습니다.
        </p>
    </section>

    ${open30mRows.length ? `
    <section class="fin-block fin-block-wide">
        <h2>장초 30분 관찰 — 미국 하락 버킷</h2>
        ${msTable(['미국 드라이버', '하락 버킷 표본', 'KR 개장 30분 평균', '음수 비율', '전체 표본', '전체 평균', '전체 음수 비율'], open30mRows)}
        <p class="fin-note ms-warn">${finEsc(open30m.proxy || '미국 종가 하락 버킷으로 분류한 수익률 프록시입니다.')}
            옵션 포지션 히스토리나 예측 적중률이 아니며, 드라이버별 표본을 합산해 하나의 신호로 만들지 않습니다.</p>
    </section>` : ''}

    ${(gs.read_ko || []).length || (gs.data_limits_ko || []).length ? `
    <section class="fin-block fin-block-wide">
        ${(gs.read_ko || []).length ? `
        <h3 class="fin-sub">해석 힌트</h3>
        <ul class="fin-list">${gs.read_ko.map((x) => `<li>${finEsc(x)}</li>`).join('')}</ul>` : ''}
        ${(gs.data_limits_ko || []).length ? `
        <h3 class="fin-sub">이 데이터로 할 수 없는 것</h3>
        <ul class="fin-list">${gs.data_limits_ko.map((x) => `<li>${finEsc(x)}</li>`).join('')}</ul>` : ''}
    </section>` : ''}

    <p class="mm-disclaimer">${finEsc(t.disclaimer_ko || '')}</p>`;
};

// --- KRX 15007 투자자별 파생 순매수 히스토리 ---------------------------------
// krx_deriv_flow_v1.json (build_krx_deriv_flow.py) carries the full KRX 15007
// investor table -- K200 futures, calls and puts, four investor groups, every
// trading day since 2019 -- as columns in KRX's own unit, 백만원. A null cell
// is a day KRX did not publish or a row whose buy−sell failed to reproduce its
// own net; it stays a gap in the line, never a zero.
const MS_FLOW_INVESTORS = [
    { key: 'foreign', ko: '외국인', color: '#f472b6' },
    { key: 'institution', ko: '기관', color: '#a78bfa' },
    { key: 'retail', ko: '개인', color: '#38bdf8' },
    { key: 'other_corp', ko: '기타법인', color: '#94a3b8' },
];
// Futures nets run to whole 조 a day; option nets are tens of 억. One unit for
// both would print futures as six-digit 억 or options as 0.00조.
const MS_FLOW_PRODUCTS = [
    { key: 'futures', ko: 'K200 선물', div: 1e6, unit: '조', digits: 2 },
    { key: 'options_call', ko: 'K200 콜옵션', div: 100, unit: '억', digits: 0 },
    { key: 'options_put', ko: 'K200 풋옵션', div: 100, unit: '억', digits: 0 },
];
const MS_FLOW_WINDOWS = [['20', '20거래일'], ['60', '60거래일'], ['120', '120거래일'], ['250', '1년'], ['all', '2019~ 전체']];
let MS_FLOW_PRODUCT = 'futures';
let MS_FLOW_WIN = '60';

const msFlowOk = (F) => !!F && F.schema_version === 'krx-deriv-flow-v1'
    && Array.isArray(F.dates) && F.dates.length > 0 && !!F.flow;
const msFlowCol = (F, product, col) => ((F.flow || {})[product] || {})[col] || [];
const msFlowScale = (v, p) => Number.isFinite(v) ? v / p.div : null;
// Rounded before the sign is chosen, so a sub-unit day prints "0", not "-0".
const msFlowFmt = (v, p) => {
    if (!Number.isFinite(v)) return '—';
    const r = Number((v / p.div).toFixed(p.digits));
    return `${r > 0 ? '+' : ''}${(r === 0 ? 0 : r).toLocaleString('ko-KR', { minimumFractionDigits: p.digits, maximumFractionDigits: p.digits })}${p.unit}`;
};
const msSignCls = (v) => !Number.isFinite(v) ? '' : v >= 0 ? 'fin-up' : 'fin-down';
// Sum of the last n observed trading days. Reports how many of those days were
// actually present so a window with a gap never reads as a full one.
const msFlowTail = (arr, n) => {
    const tail = arr.slice(-n);
    const got = tail.filter(Number.isFinite);
    return { sum: got.length ? got.reduce((a, b) => a + b, 0) : null, obs: got.length, n: tail.length };
};

// The 15007 products in the shape the snapshot's detailed_15007 uses, so the
// existing call/put cards and 추이 modal read the full history unchanged.
const msFlowAs15007 = (F, product) => {
    const net = msFlowCol(F, product, 'foreign_net');
    const buy = msFlowCol(F, product, 'foreign_buy');
    const sell = msFlowCol(F, product, 'foreign_sell');
    const mkt = msFlowCol(F, product, 'market_total_buy');
    const partial = new Set((F.partial_days || {})[product] || []);
    const src = 'KRX 15007 투자자별 거래실적 (정규화 이력)';
    const series = F.dates.map((date, i) => {
        if (![net[i], buy[i], sell[i]].every(Number.isFinite)) return null;
        return { date, source: src, quality: partial.has(date) ? 'partial_observed' : 'observed',
            foreign: { buy_krw: buy[i] * 1e6, sell_krw: sell[i] * 1e6, net_krw: net[i] * 1e6 },
            market_total: Number.isFinite(mkt[i]) ? { buy_krw: mkt[i] * 1e6, sell_krw: mkt[i] * 1e6, net_krw: 0 } : null };
    }).filter(Boolean);
    const last = series[series.length - 1];
    if (!last) return null;
    return { ...last, as_of: last.date, series };
};

// Whichever of the two sources is newer wins, per product. The snapshot's own
// block comes from the newest raw CSV folder; the history comes from the
// normalized hive and is usually ahead of it.
const msPick15007 = (D) => {
    const board = ((((D.board || {}).kr || {}).investor_nets || {}).detailed_15007 || {}).products || {};
    const F = D.flow;
    if (!msFlowOk(F)) return board;
    const out = { ...board };
    ['options_call', 'options_put'].forEach((p) => {
        const fp = msFlowAs15007(F, p);
        const bp = board[p];
        if (fp && (!bp || String(fp.as_of) >= String(bp.as_of || ''))) out[p] = fp;
    });
    return out;
};

// Multi-series line / diverging-bar chart on the macro chart geometry. One
// y-axis, zero line always in view, gaps where the source has none.
const msMultiChart = (dates, series, opts = {}) => {
    const n = dates.length;
    const ys = series.flatMap((s) => s.values).filter(Number.isFinite);
    if (n < 2 || ys.length < 2) return '<p class="fin-note">그릴 수 있는 시계열이 없습니다.</p>';
    // Flows are signed, so zero stays on the axis; a price or OI level does
    // not need it (opts.zero === false) and would flatten against it.
    const withZero = opts.zero !== false;
    let lo = Math.min(...ys, ...(withZero ? [0] : [])), hi = Math.max(...ys, ...(withZero ? [0] : []));
    if (lo === hi) { lo -= 1; hi += 1; }
    // Round-number ticks (1/2/5 × 10^k) so zero and the gridlines land on
    // values a reader would say out loud, not 0.44 or -7.20.
    const raw = (hi - lo) / 4;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((m) => m >= raw) || raw;
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    const x0 = MM_L, x1 = MM_W - MM_R;
    const sy = (v) => MM_T + (1 - (v - lo) / (hi - lo)) * (MM_H - MM_T - MM_B);
    const ticks = [];
    for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Math.abs(t) < step / 1e6 ? 0 : t);
    let marks = '';
    if (opts.bars) {
        // Bars sit in equal slots; the gap disappears once they get too thin
        // to spare it, rather than letting the gap eat the bar.
        // Several series share a slot only when their signs differ (call OI up,
        // put OI drawn as negative), so they never overlap.
        const slot = (x1 - x0) / n;
        const gap = slot > 4 ? 1 : 0;
        const fade = series.length === 1;
        marks = series.map((s) => s.values.map((v, i) => {
            if (!Number.isFinite(v)) return '';
            const y = sy(Math.max(v, 0)), h = Math.max(Math.abs(sy(v) - sy(0)), 0.5);
            return `<rect x="${(x0 + i * slot + gap / 2).toFixed(2)}" y="${y.toFixed(1)}" width="${Math.max(slot - gap, 0.4).toFixed(2)}"
                height="${h.toFixed(1)}" fill="${finEsc(s.color)}" fill-opacity="${fade && v < 0 ? 0.5 : 0.85}"/>`;
        }).join('')).join('');
        if (Number.isInteger(opts.markIndex) && opts.markIndex >= 0 && opts.markIndex < n) {
            const mx = x0 + (opts.markIndex + 0.5) * slot;
            marks += `<line x1="${mx.toFixed(1)}" y1="${MM_T}" x2="${mx.toFixed(1)}" y2="${MM_H - MM_B}" class="ms-mark"/>
                <text x="${(mx + 4).toFixed(1)}" y="${MM_T + 10}" class="ms-mark-tag">${finEsc(opts.markLabel || '')}</text>`;
        }
    } else {
        const sx = (i) => x0 + (i / Math.max(n - 1, 1)) * (x1 - x0);
        marks = series.map((s) => {
            let d = '', pen = false;
            s.values.forEach((v, i) => {
                if (!Number.isFinite(v)) { pen = false; return; }
                d += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
                pen = true;
            });
            return `<path d="${d}" fill="none" stroke="${finEsc(s.color)}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
        }).join('');
    }
    const xAt = [0, Math.floor((n - 1) / 2), n - 1];
    const payload = { dates, n, bars: !!opts.bars, unit: opts.unit || '', digits: opts.digits ?? 0, signed: opts.signed !== false, abs: !!opts.abs,
        series: series.map((s) => ({ label: s.label, color: s.color, values: s.values.map((v) => Number.isFinite(v) ? v : null),
            ...(Array.isArray(s.daily) ? { daily: s.daily.map((v) => Number.isFinite(v) ? v : null) } : {}) })) };
    return `
    <div class="mm-chart-box ms-mc-box" data-ms-mc='${finEsc(JSON.stringify(payload))}'>
        <svg class="mm-chart" viewBox="0 0 ${MM_W} ${MM_H}" preserveAspectRatio="none" role="img" aria-label="${finEsc(opts.label || '시계열')} 차트">
            ${ticks.map((t) => `
                <line x1="${x0}" y1="${sy(t).toFixed(1)}" x2="${x1}" y2="${sy(t).toFixed(1)}" class="mm-grid"/>
                <text x="${x0 - 7}" y="${(sy(t) + 3.5).toFixed(1)}" class="mm-tick" text-anchor="end">${mmFmt(opts.abs ? Math.abs(t) : t)}</text>`).join('')}
            ${(lo < 0 && hi > 0) || (withZero && lo === 0) ? `<line x1="${x0}" y1="${sy(0).toFixed(1)}" x2="${x1}" y2="${sy(0).toFixed(1)}" class="mm-zero"/>` : ''}
            ${marks}
            ${xAt.map((i) => {
                const x = opts.bars ? x0 + (i + 0.5) * (x1 - x0) / n : x0 + (i / Math.max(n - 1, 1)) * (x1 - x0);
                return `<text x="${x.toFixed(1)}" y="${MM_H - 8}" class="mm-tick"
                    text-anchor="${i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle')}">${finEsc(dates[i] || '')}</text>`;
            }).join('')}
            <line class="mm-cross" x1="0" y1="${MM_T}" x2="0" y2="${MM_H - MM_B}" style="display:none"/>
        </svg>
        <div class="mm-tip-box" style="display:none"></div>
        ${series.length > 1 || opts.legend ? `<div class="mm-ma-legend">${series.map((s) => `<span class="mm-ma-key"><i style="background:${finEsc(s.color)}"></i>${finEsc(s.label)}</span>`).join('')}</div>` : ''}
    </div>`;
};

const msWireMultiCharts = (host) => {
    host.querySelectorAll('[data-ms-mc]').forEach((box) => {
        const svg = box.querySelector('svg');
        const cross = box.querySelector('.mm-cross');
        const tip = box.querySelector('.mm-tip-box');
        let P;
        try { P = JSON.parse(box.dataset.msMc); } catch (_) { return; }
        if (!svg || !cross || !tip || !P || !P.n) return;
        const x0 = MM_L, x1 = MM_W - MM_R;
        const hide = () => { cross.style.display = 'none'; tip.style.display = 'none'; };
        svg.addEventListener('mousemove', (e) => {
            const r = svg.getBoundingClientRect();
            if (!r.width) return;
            const vx = (e.clientX - r.left) / r.width * MM_W;
            const t = (vx - x0) / (x1 - x0);
            const i = Math.max(0, Math.min(P.n - 1, P.bars ? Math.floor(t * P.n) : Math.round(t * (P.n - 1))));
            const px = P.bars ? x0 + (i + 0.5) * (x1 - x0) / P.n : x0 + (i / Math.max(P.n - 1, 1)) * (x1 - x0);
            cross.setAttribute('x1', px); cross.setAttribute('x2', px);
            cross.style.display = '';
            const fmt = (v) => Number.isFinite(v)
                ? `${P.signed && v >= 0 ? '+' : ''}${(P.abs ? Math.abs(v) : v).toLocaleString('ko-KR', { minimumFractionDigits: P.digits, maximumFractionDigits: P.digits })}${P.unit}`
                : '관측 없음';
            tip.innerHTML = `<span class="mm-tip-date">${finEsc(P.dates[i] || '')}</span>`
                + P.series.map((s) => `<span class="ms-mc-tip-row"><i style="background:${finEsc(s.color)}"></i>${finEsc(s.label)} <b>${fmt(s.values[i])}</b>${
                    s.daily ? `<em>당일 ${fmt(s.daily[i])}</em>` : ''}</span>`).join('');
            tip.style.display = '';
            tip.style.left = `${Math.min(Math.max(px / MM_W * 100, 12), 82)}%`;
        });
        svg.addEventListener('mouseleave', hide);
    });
};

const msFlowSection = (D) => {
    const F = D.flow;
    if (!msFlowOk(F)) {
        return `
    <section class="fin-block fin-block-wide">
        <h2>투자자별 K200 파생 순매수 추이</h2>
        <div class="ms-hist-empty"><strong>KRX 15007 이력 파일 없음</strong>
            <p><code>krx_deriv_flow_v1.json</code> 이 아직 배포되지 않았습니다. 일일 워크플로가 krx-month-paste 정규화 이력에서 생성합니다.</p></div>
    </section>`;
    }
    const P = MS_FLOW_PRODUCTS.find((p) => p.key === MS_FLOW_PRODUCT) || MS_FLOW_PRODUCTS[0];
    const total = F.dates.length;
    const n = MS_FLOW_WIN === 'all' ? total : Math.min(total, Number(MS_FLOW_WIN));
    const dates = F.dates.slice(-n);
    const lastDate = F.dates[total - 1];

    // Latest-day board across all three products, 억 throughout so the rows
    // compare directly.
    const eok = (v) => Number.isFinite(v) ? msKrwEok(v * 1e6) : '—';
    const cell = (v) => `<span class="${msSignCls(v)}">${eok(v)}</span>`;
    const tailCell = (arr, k) => {
        const t = msFlowTail(arr, k);
        return `<span class="${msSignCls(t.sum)}">${eok(t.sum)}</span>${t.obs < t.n ? ` <span class="ms-q">${t.obs}/${t.n}일</span>` : ''}`;
    };
    const boardRows = MS_FLOW_PRODUCTS.map((p) => {
        const col = (inv) => msFlowCol(F, p.key, `${inv}_net`);
        const last = (inv) => col(inv)[total - 1];
        return [`${finEsc(p.ko)} <button class="mm-view-btn" data-ms-modal="flow_hist:${p.key}">추이</button>`,
            cell(last('foreign')), finEsc(msRankLabel(col('foreign'), last('foreign')) || '—'),
            tailCell(col('foreign'), 5), tailCell(col('foreign'), 20),
            cell(last('institution')), cell(last('retail')), cell(last('other_corp'))];
    });

    // Cumulative net from the window's first day. A missing day is a gap in
    // the line; the running total carries across it rather than restarting.
    const cumSeries = MS_FLOW_INVESTORS.map((inv) => {
        const raw = msFlowCol(F, P.key, `${inv.key}_net`).slice(-n);
        let acc = 0;
        return { label: inv.ko, color: inv.color, daily: raw.map((v) => msFlowScale(v, P)),
            values: raw.map((v) => { if (!Number.isFinite(v)) return null; acc += v; return msFlowScale(acc, P); }) };
    });
    // Days that dominate the window. A cumulative line is only as readable as
    // its biggest steps -- one block-sized day can outweigh a month -- so the
    // window's largest foreign days are listed with their counterparties and
    // a multiple of the product's usual (2019~ median) day.
    const fAll = msFlowCol(F, P.key, 'foreign_net');
    const absSorted = fAll.filter(Number.isFinite).map(Math.abs).sort((a, b) => a - b);
    const typical = absSorted.length ? absSorted[Math.floor(absSorted.length / 2)] : null;
    const bigDays = F.dates.map((d, i) => i).slice(-n)
        .filter((i) => Number.isFinite(fAll[i]))
        .sort((a, b) => Math.abs(fAll[b]) - Math.abs(fAll[a]))
        .slice(0, 5)
        .map((i) => [
            finEsc(F.dates[i]),
            ...MS_FLOW_INVESTORS.slice(0, 3).map((inv) => {
                const v = msFlowCol(F, P.key, `${inv.key}_net`)[i];
                return `<span class="${msSignCls(v)}">${msFlowFmt(v, P)}</span>`;
            }),
            msKrwEokLevel(Number.isFinite(msFlowCol(F, P.key, 'market_total_buy')[i]) ? msFlowCol(F, P.key, 'market_total_buy')[i] * 1e6 : null),
            typical ? `${(Math.abs(fAll[i]) / typical).toFixed(0)}배` : '—',
        ]);
    const foreignDaily = msFlowCol(F, P.key, 'foreign_net').slice(-n).map((v) => msFlowScale(v, P));

    const front = F.futures_front || {};
    const closeW = (front.close || []).slice(-n);
    const oiW = (front.open_interest || []).slice(-n);

    const recent = F.dates.map((d, i) => i).slice(-10).reverse().map((i) => [
        finEsc(F.dates[i]),
        ...MS_FLOW_INVESTORS.map((inv) => {
            const v = msFlowCol(F, P.key, `${inv.key}_net`)[i];
            return `<span class="${msSignCls(v)}">${msFlowFmt(v, P)}</span>`;
        }),
        ...(P.key === 'futures' ? [
            Number.isFinite((front.close || [])[i]) ? front.close[i].toFixed(2) : '—',
            Number.isFinite((front.open_interest || [])[i]) ? `${msNum(front.open_interest[i])}계약` : '—',
        ] : []),
    ]);
    const missing = (F.missing_trading_days || []).map((m) => m.date).filter(Boolean);

    return `
    <section class="fin-block fin-block-wide">
        <h2>투자자별 K200 파생 순매수 추이 · KRX 15007</h2>
        <p class="fin-lead">KRX 「투자자별 거래실적」 일별 거래대금 기준 순매수(매수−매도)입니다. ${finEsc(F.range?.start || '')} ~ ${finEsc(lastDate)} · ${msNum(total)}거래일.
            최근 거래일 ${finEsc(lastDate)}.</p>
        ${msStaleNote('KRX 15007 투자자별 수급', (F.last_dates || {}).flow || lastDate)}
        ${msTable(['상품 (억원)', '외국인 당일', '2019~ 위치', '외국인 5일 합', '외국인 20일 합', '기관 당일', '개인 당일', '기타법인 당일'], boardRows)}
        <p class="fin-note">2019~ 위치: 같은 상품의 외국인 일별 순매수 ${msNum(total)}거래일 분포에서 오늘 값이 놓인 자리입니다 (상위 = 순매수 쪽 극단).</p>

        <div class="ms-flow-controls">
            <div class="mm-tabs ms-flow-tabs" role="group" aria-label="상품">
                ${MS_FLOW_PRODUCTS.map((p) => `<button class="mm-tab ${p.key === P.key ? 'on' : ''}" data-ms-flow-product="${p.key}">${finEsc(p.ko)}</button>`).join('')}
            </div>
            ${msWinBar('ms-flow-win', MS_FLOW_WIN)}
        </div>

        <h3 class="fin-sub">${finEsc(P.ko)} · 주체별 누적 순매수 (${finEsc(dates[0])} = 0 에서 시작, ${P.unit}원)</h3>
        ${msMultiChart(dates, cumSeries, { unit: P.unit, digits: P.digits, label: `${P.ko} 누적 순매수` })}
        <p class="fin-note">누적은 선택한 기간의 첫날을 0으로 두고 더합니다. 그래서 기간(20·60·120일…)을 바꾸면 같은 날짜의 누적 수준은 달라지고,
            하루 사이의 계단 높이(그날 순매수)는 그대로입니다. 차트에 마우스를 올리면 누적과 함께 당일 값이 나옵니다.</p>
        ${bigDays.length ? `
        <h3 class="fin-sub">이 기간 외국인 순매수가 가장 컸던 날 · ${finEsc(P.ko)}</h3>
        ${msTable(['날짜', ...MS_FLOW_INVESTORS.slice(0, 3).map((i) => i.ko), '시장 전체 거래대금', '평소 대비'], bigDays)}
        <p class="fin-note">평소 대비 = 그날 외국인 순매수 절댓값 ÷ 2019년 이후 같은 상품의 일별 절댓값 중앙값(${typical ? msFlowFmt(typical, P).replace('+', '') : '—'}).
            한쪽이 크게 사고 다른 주체가 거의 같은 금액을 판 날은 한 번에 체결된 대량 거래일 가능성이 큽니다 — 원자료에서 확인되는 사실은 주체별 금액까지입니다.</p>` : ''}

        <h3 class="fin-sub">${finEsc(P.ko)} · 외국인 일별 순매수 (${P.unit}원)</h3>
        ${msMultiChart(dates, [{ label: '외국인', color: MS_FLOW_INVESTORS[0].color, values: foreignDaily }],
            { bars: true, unit: P.unit, digits: P.digits, label: `${P.ko} 외국인 일별 순매수` })}

        ${P.key === 'futures' ? `
        <h3 class="fin-sub">K200 선물 최근월물 종가 (정규장)</h3>
        ${msMultiChart(dates, [{ label: '종가', color: '#e2e8f0', values: closeW }],
            { zero: false, signed: false, digits: 2, label: 'K200 선물 최근월물 종가' })}
        <h3 class="fin-sub">K200 선물 최근월물 미결제약정 (시장 전체, 계약)</h3>
        ${msMultiChart(dates, [{ label: '미결제약정', color: '#94a3b8', values: oiW }],
            { zero: false, signed: false, unit: '계약', label: 'K200 선물 최근월물 미결제약정' })}
        <p class="fin-note">${finEsc(front.scope_ko || '시장 전체 미결제약정이며 외국인 보유분이 아닙니다.')} 분기 만기(3·6·9·12월) 롤오버 날 최근월물이 바뀌며 OI가 급변합니다.</p>` : ''}

        <h3 class="fin-sub">최근 10거래일 · ${finEsc(P.ko)}</h3>
        ${msTable(['날짜', ...MS_FLOW_INVESTORS.map((i) => i.ko), ...(P.key === 'futures' ? ['최근월 종가', '미결제약정'] : [])], recent)}

        <p class="fin-note ms-warn">순매수는 당일 거래 흐름입니다. 미결제약정·보유 포지션·신규/청산 구분·헤지 의도가 아니며 다음 방향을 예측하지 않습니다.
            네 주체 순매수의 합은 0이라, 한 주체의 매수는 다른 주체의 매도입니다. 옵션은 프리미엄 거래대금이며 계약 수·델타가 아닙니다.</p>
        <p class="fin-note">출처 ${finEsc((F.source || {}).flow || 'KRX 15007')}${P.key === 'futures' ? ` · ${finEsc((F.source || {}).futures_front || '')}` : ''}.
            휴장일은 날짜가 없고, 매수−매도≠순매수인 행은 비웁니다.${missing.length ? ` 미수집 거래일: ${missing.map(finEsc).join(', ')}.` : ''}
            ${((F.partial_days || {})[P.key] || []).length ? ` 부분 관측 ${F.partial_days[P.key].length}일은 값 없이 비어 있습니다.` : ''}
            생성 ${finEsc(F.generated_at || '—')}.</p>
    </section>`;
};

// --- 수집 지연 ----------------------------------------------------------------
// KRX publishes a trading day overnight and the Action picks it up the next
// morning, so one weekday of lag is normal. From three weekdays on, the block
// says so -- and keeps drawing everything up to its last observed day, since
// the builder never drops published history when a source stops. Holidays are
// not modelled, which is why the threshold leaves room for a long weekend.
const MS_STALE_WEEKDAYS = 3;
const msKstToday = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const msWeekdayLag = (from, to) => {
    const d = new Date(`${from}T00:00:00Z`);
    const end = new Date(`${to}T00:00:00Z`);
    if (Number.isNaN(d.getTime()) || Number.isNaN(end.getTime())) return 0;
    let n = 0;
    d.setUTCDate(d.getUTCDate() + 1);
    for (let guard = 0; d < end && guard < 5000; guard++) {
        const w = d.getUTCDay();
        if (w !== 0 && w !== 6) n++;
        d.setUTCDate(d.getUTCDate() + 1);
    }
    return n;
};
const msStaleNote = (label, last) => {
    if (!last) return '';
    const lag = msWeekdayLag(last, msKstToday());
    if (lag < MS_STALE_WEEKDAYS) return '';
    return `<p class="ms-stale"><strong>수집 멈춤</strong> · ${finEsc(label)} 마지막 관측 ${finEsc(last)} (평일 기준 ${lag}일 전, 공휴일 미반영).
        아래 표와 차트는 ${finEsc(last)}까지의 과거 데이터이며, 수집이 재개되면 이어서 갱신됩니다.</p>`;
};

// Where a value sits in its own 2019~ distribution. Twenty observations is the
// floor below which a percentile is noise.
const msRankLabel = (arr, v) => {
    const xs = (arr || []).filter(Number.isFinite);
    if (!Number.isFinite(v) || xs.length < 20) return '';
    const below = xs.filter((x) => x < v).length / xs.length;
    const atOrBelow = xs.filter((x) => x <= v).length / xs.length;
    return below >= 0.5 ? `상위 ${Math.max(1, Math.round((1 - below) * 100))}%` : `하위 ${Math.max(1, Math.round(atOrBelow * 100))}%`;
};

const msWinN = (win, total) => win === 'all' ? total : Math.min(total, Number(win));
const msWinBar = (attr, cur) => `
    <div class="ms-hist-period" role="group" aria-label="표시 기간">
        ${MS_FLOW_WINDOWS.map(([id, ko]) => `<button class="mm-tab ${id === cur ? 'on' : ''}" data-${attr}="${id}">${finEsc(ko)}</button>`).join('')}
    </div>`;

// 15007 market totals as activity-log-shaped rows, so the existing 거래대금
// cards open a 2019~ trend instead of the few weeks the activity log holds.
let MS_FLOW_ACT_CACHE = null;
const msFlowActivityRows = () => {
    const F = (MS_DATA || {}).flow;
    if (!msFlowOk(F)) return null;
    if (MS_FLOW_ACT_CACHE && MS_FLOW_ACT_CACHE.F === F) return MS_FLOW_ACT_CACHE.rows;
    const f = msFlowCol(F, 'futures', 'market_total_buy');
    const c = msFlowCol(F, 'options_call', 'market_total_buy');
    const p = msFlowCol(F, 'options_put', 'market_total_buy');
    const krw = (v) => Number.isFinite(v) ? v * 1e6 : null;
    const rows = F.dates.map((date, i) => ({ date, flow15007: true, quality: 'observed',
        source: 'KRX 15007 시장 전체 거래대금',
        fut_tv: krw(f[i]), call_tv: krw(c[i]), put_tv: krw(p[i]),
        pc_tv: Number.isFinite(p[i]) && c[i] > 0 ? p[i] / c[i] : null }))
        .filter((r) => [r.fut_tv, r.call_tv, r.put_tv].some(Number.isFinite));
    MS_FLOW_ACT_CACHE = { F, rows: rows.length ? rows : null };
    return MS_FLOW_ACT_CACHE.rows;
};

// Per-investor net history for one product, in that product's display unit.
const msFlowHistSpecs = (F, product) => {
    const P = MS_FLOW_PRODUCTS.find((x) => x.key === product) || MS_FLOW_PRODUCTS[0];
    const partial = new Set((F.partial_days || {})[product] || []);
    const cols = Object.fromEntries(MS_FLOW_INVESTORS.map((inv) => [inv.key, msFlowCol(F, product, `${inv.key}_net`)]));
    const rows = F.dates.map((date, i) => ({ date, i, quality: partial.has(date) ? 'partial_observed' : 'observed',
        source: 'KRX 15007 투자자별 거래실적' }));
    return MS_FLOW_INVESTORS.slice(0, 3).map((inv) => ({ rows, label: `${P.ko} ${inv.ko} 순매수`, unit: P.unit,
        pick: (r) => msFlowScale(cols[inv.key][r.i], P) }));
};

// --- K200 옵션 최근월물 미결제약정 (15018) ------------------------------------
const MS_CALL_COLOR = '#fbbf24';
const MS_PUT_COLOR = '#818cf8';
const MS_PX_COLOR = '#e2e8f0';
let MS_OI_WIN = '120';

const msOptionOiSection = (D) => {
    const F = D.flow;
    const O = msFlowOk(F) ? F.option_oi : null;
    if (!O || !Array.isArray(O.call_oi)) return '';
    const last = (F.last_dates || {}).option_oi;
    const li = F.dates.lastIndexOf(last);
    if (li < 0) return '';
    const total = li + 1;
    const n = msWinN(MS_OI_WIN, total);
    const from = total - n;
    const dates = F.dates.slice(from, total);
    const win = (arr) => (arr || []).slice(from, total);
    const front = F.futures_front || {};
    const iv = O.atm_iv[li];
    const pc = O.pc_oi[li];

    const prof = O.profile || {};
    const strikes = (prof.strikes || []);
    const fClose = prof.futures_close;
    let markIndex = null;
    if (Number.isFinite(fClose) && strikes.length) {
        markIndex = strikes.reduce((best, r, i) => Math.abs(r[0] - fClose) < Math.abs(strikes[best][0] - fClose) ? i : best, 0);
    }
    const strikeLabel = (v) => Number.isFinite(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: 1 }) : '—';

    return `
    <section class="fin-block fin-block-wide">
        <h2>K200 옵션 미결제약정 · 최근월물 체인 (KRX 15018)</h2>
        <p class="fin-lead">최근월물 ${finEsc(O.expiry[li] || '—')} 전 행사가의 시장 전체 미결제약정입니다. 기준일 ${finEsc(last)}.</p>
        ${msStaleNote('옵션 미결제약정', last)}
        <div class="fin-cards">
            ${msCard('콜 미결제약정 합계', Number.isFinite(O.call_oi[li]) ? `${msNum(O.call_oi[li])}계약` : '—',
                `최대 OI 행사가 ${strikeLabel(O.call_wall[li])}`, 'oi_hist:totals')}
            ${msCard('풋 미결제약정 합계', Number.isFinite(O.put_oi[li]) ? `${msNum(O.put_oi[li])}계약` : '—',
                `최대 OI 행사가 ${strikeLabel(O.put_wall[li])}`, 'oi_hist:totals')}
            ${msCard('풋/콜 OI 비율', Number.isFinite(pc) ? pc.toFixed(2) : '—',
                Number.isFinite(pc) ? `2019~ 분포 ${msRankLabel(O.pc_oi.slice(0, total), pc) || '—'}` : msMissing('콜·풋 OI 필요'), 'oi_hist:pc')}
            ${msCard('ATM 내재변동성', Number.isFinite(iv) ? `${iv.toFixed(1)}%` : '—',
                Number.isFinite(iv) ? `행사가 ${strikeLabel(O.atm_strike[li])} · 2019~ 분포 ${msRankLabel(O.atm_iv.slice(0, total), iv) || '—'}`
                    : msMissing('만기일이거나 호가 없음 — 산출 안 함'), 'oi_hist:iv')}
        </div>

        ${strikes.length ? `
        <h3 class="fin-sub">행사가별 미결제약정 · ${finEsc(prof.date || '')} · ${finEsc(prof.expiry || '')} (위: 콜, 아래: 풋)</h3>
        ${msMultiChart(strikes.map((r) => strikeLabel(r[0])),
            [{ label: '콜 OI', color: MS_CALL_COLOR, values: strikes.map((r) => r[1]) },
             { label: '풋 OI', color: MS_PUT_COLOR, values: strikes.map((r) => Number.isFinite(r[2]) ? -r[2] : null) }],
            { bars: true, abs: true, signed: false, unit: '계약', legend: true, markIndex,
              markLabel: Number.isFinite(fClose) ? `선물 ${fClose.toFixed(2)}` : '', label: '행사가별 미결제약정' })}
        <p class="fin-note">선물 종가 ±15% 행사가만 그립니다. 미결제약정은 매수·매도 양쪽이 같이 보유한 계약이라 방향이 없습니다 — 콜 OI가 많다고 상승 베팅이 많은 것이 아닙니다.</p>` : ''}

        <div class="ms-flow-controls">
            <span class="ms-sub-h">추이 · ${finEsc(dates[0])} ~ ${finEsc(last)}</span>
            ${msWinBar('ms-oi-win', MS_OI_WIN)}
        </div>
        <h3 class="fin-sub">최대 OI 행사가와 선물 최근월물 종가</h3>
        ${msMultiChart(dates, [
            { label: '콜 최대 OI 행사가', color: MS_CALL_COLOR, values: win(O.call_wall) },
            { label: '풋 최대 OI 행사가', color: MS_PUT_COLOR, values: win(O.put_wall) },
            { label: '선물 종가', color: MS_PX_COLOR, values: win(front.close) },
        ], { zero: false, signed: false, digits: 1, label: '최대 OI 행사가와 선물 종가' })}
        <h3 class="fin-sub">풋/콜 미결제약정 비율</h3>
        ${msMultiChart(dates, [{ label: '풋/콜 OI', color: MS_PUT_COLOR, values: win(O.pc_oi) }],
            { zero: false, signed: false, digits: 2, label: '풋/콜 OI 비율' })}
        <h3 class="fin-sub">ATM 내재변동성 (%)</h3>
        ${msMultiChart(dates, [{ label: 'ATM IV', color: MS_CALL_COLOR, values: win(O.atm_iv) }],
            { zero: false, signed: false, digits: 1, unit: '%', label: 'ATM 내재변동성' })}

        <p class="fin-note ms-warn">${finEsc(O.scope_ko || '시장 전체 미결제약정이며 외국인 보유분이 아닙니다.')}
            만기일에는 KRX가 미결제약정을 공시하지 않아 그날은 비어 있고, 다음 날 최근월물이 바뀌어 OI 합계와 최대 OI 행사가가 새 월물 기준으로 다시 시작합니다. 최대 OI 행사가는 거래가 몰린 자리일 뿐 지지·저항을 보장하지 않습니다.
            ATM IV는 KRX 공시 내재변동성(선물 종가에 가장 가까운 행사가의 콜·풋 평균)이며, 잔존가치가 없는 만기일은 비웁니다.</p>
        <p class="fin-note">출처 ${finEsc((F.source || {}).option_oi || 'KRX 15018')} · 관측 ${msNum(O.call_oi.filter(Number.isFinite).length)}거래일.</p>
    </section>`;
};

// --- 프로그램매매 (12012) -----------------------------------------------------
const MS_PROG_TYPES = [
    { key: 'arbitrage', ko: '차익', color: MS_CALL_COLOR },
    { key: 'non_arbitrage', ko: '비차익', color: '#38bdf8' },
    { key: 'total', ko: '전체', color: MS_PX_COLOR },
];
let MS_PROG_WIN = '60';

const msProgramSection = (D) => {
    const F = D.flow;
    const G = msFlowOk(F) ? F.program : null;
    if (!G || !Array.isArray(G.dates) || !G.dates.length) return '';
    const total = G.dates.length;
    const n = msWinN(MS_PROG_WIN, total);
    const dates = G.dates.slice(-n);
    const last = G.dates[total - 1];
    const col = (t) => (G[`${t}_net`] || []);
    const JO = { div: 1e6, unit: '조', digits: 2 };
    // The hive has long uncollected stretches, so N points here can span far
    // more than N trading days. Say how many of the window's trading days
    // (from the K200 calendar) were actually collected.
    const cal = F.dates.filter((d) => d >= dates[0] && d <= last);
    const have = new Set(dates);
    const covered = cal.filter((d) => have.has(d)).length;

    const cum = MS_PROG_TYPES.map((t) => {
        let acc = 0;
        return { label: t.ko, color: t.color,
            values: col(t.key).slice(-n).map((v) => { if (!Number.isFinite(v)) return null; acc += v; return acc / JO.div; }) };
    });
    const recent = G.dates.map((d, i) => i).slice(-10).reverse().map((i) => [
        finEsc(G.dates[i]),
        ...MS_PROG_TYPES.map((t) => { const v = col(t.key)[i]; return `<span class="${msSignCls(v)}">${msKrwEok(Number.isFinite(v) ? v * 1e6 : null)}</span>`; }),
    ]);
    const tail = (k) => msFlowTail(col('total'), k);
    const t5 = tail(5);

    return `
    <section class="fin-block fin-block-wide">
        <h2>프로그램매매 · 유가증권시장 (KRX 12012)</h2>
        <p class="fin-lead">차익(선물·현물 가격차를 이용한 바스켓)과 비차익(지수 바스켓) 프로그램의 현물 순매수입니다. 마지막 관측 ${finEsc(last)}.</p>
        ${msStaleNote('프로그램매매', last)}
        <div class="fin-cards">
            ${MS_PROG_TYPES.map((t) => {
                const v = col(t.key)[total - 1];
                return msCard(`${t.ko} 순매수`, `<span class="${msSignCls(v)}">${msKrwEok(Number.isFinite(v) ? v * 1e6 : null)}</span>`,
                    `${finEsc(last)} · 2019~ 수집일 중 ${msRankLabel(col(t.key), v) || '—'}`, null);
            }).join('')}
            ${msCard('전체 최근 5개 수집일 합', `<span class="${msSignCls(t5.sum)}">${msKrwEok(Number.isFinite(t5.sum) ? t5.sum * 1e6 : null)}</span>`,
                `${finEsc(G.dates[Math.max(0, total - 5)])} ~ ${finEsc(last)}`, null)}
        </div>
        <div class="ms-flow-controls">
            <span class="ms-sub-h">수집일 ${msNum(dates.length)}개 · ${finEsc(dates[0])} ~ ${finEsc(last)} · 이 구간 거래일 ${msNum(cal.length)}일 중 ${msNum(covered)}일 수집</span>
            ${msWinBar('ms-prog-win', MS_PROG_WIN)}
        </div>
        <h3 class="fin-sub">누적 순매수 (조원)</h3>
        ${msMultiChart(dates, cum, { unit: '조', digits: 2, label: '프로그램매매 누적 순매수' })}
        <h3 class="fin-sub">최근 10개 수집일</h3>
        ${msTable(['날짜', ...MS_PROG_TYPES.map((t) => t.ko)], recent)}
        <p class="fin-note ms-warn">수집된 날만 이어 그립니다 — 빈 기간은 가로축에서 압축되고 누적은 그 사이를 건너뜁니다.
            전 기간 수집률 ${Number.isFinite(G.coverage_pct) ? `${G.coverage_pct.toFixed(0)}%` : '—'}. 프로그램매매는 현물 주식 거래이며 파생 포지션이 아닙니다.</p>
        <p class="fin-note">출처 ${finEsc((F.source || {}).program || 'KRX 12012')}.</p>
    </section>`;
};

// --- ④ KRX 파생 수급 --------------------------------------------------------
// The public KRX dashboard identifies the foreign investor's K200 futures and
// options-total flow. It does *not* split that foreign options flow into calls
// and puts, so those two cells stay visibly missing until authenticated KRX
// investor-detail CSVs are supplied. Never infer the split from market volume.
const msDerivatives = (D) => {
    const kr = (D.board || {}).kr || {};
    const dashboard = (kr.investor_nets || {}).public_dashboard || {};
    const futuresFlow = ((dashboard.futures || {}).investors || {}).foreign || {};
    const optionsFlow = ((dashboard.options_total || {}).investors || {}).foreign || {};
    const futures = kr.kospi200_futures || {};
    const options = kr.kospi200_options || {};
    const observedAt = (dashboard.futures || {}).observed_at_krx
        || (dashboard.options_total || {}).observed_at_krx || '—';
    const foreignAsOf = (dashboard.futures || {}).as_of
        || (dashboard.options_total || {}).as_of || '—';
    const activityAsOf = kr.as_of || options.bas_dd || '—';
    const sourceNote = (kr.investor_nets || {}).note_ko
        || '공개 대시보드는 옵션 전체만 제공하며 콜/풋별 외국인 수급은 제공하지 않습니다.';

    // CLAUDE_HANDOFF_15007_CALL_PUT_UI.md: options_total is never split into
    // call/put by proportion or demo value. Only kr.investor_nets.detailed_15007
    // .products carries a real call/put split, and only for the days it has an
    // authenticated 15007 export -- most days this is entirely absent.
    // msPick15007 prefers the full normalized history when it is newer than
    // the snapshot's raw-CSV block -- same fields, same validation below.
    const products15007 = msPick15007(D);
    const callP = products15007.options_call || null;
    const putP = products15007.options_put || null;
    const callState = ms15007State(callP);
    const putState = ms15007State(putP);
    const relOk = callState.ok && putState.ok;
    const relKrw = relOk ? putP.foreign.net_krw - callP.foreign.net_krw : null;
    const relLabel = relKrw === null ? '판정 불가' : relKrw > 0 ? '풋 상대 우위' : relKrw < 0 ? '콜 상대 우위' : '동일';
    const has15007Hist = !!(callP || putP);

    const flowRow = (label, data, quality) => [
        finEsc(label),
        msJo(data.sell_krw),
        msJo(data.buy_krw),
        `<span class="${data.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msSignedJo(data.net_krw)}</span>`,
        finEsc(quality),
    ];
    const missingSplitRow = (label, reason) => [
        finEsc(label), '—', '—', '—',
        msMissing(reason) + (has15007Hist ? ` <button class="mm-view-btn" data-ms-modal="kr_15007_hist">추이</button>` : ''),
    ];
    const flowRow15007 = (label, p, state) => state.ok
        ? [finEsc(label), msKrwEokLevel(p.foreign.sell_krw), msKrwEokLevel(p.foreign.buy_krw),
            `<span class="${p.foreign.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msKrwEok(p.foreign.net_krw)}</span>`,
            `실측 · KRX 15007 (${finEsc(p.as_of || '—')}) <button class="mm-view-btn" data-ms-modal="kr_15007_hist">추이</button>`]
        : missingSplitRow(label, state.reason);

    return `
    <section class="fin-block fin-block-wide">
        <h2>외국인 KOSPI200 파생 수급</h2>
        <p class="fin-lead">매도·매수·순매수는 KRX 공개 대시보드(선물)와 인증된 KRX 15007 원자료(콜·풋)의 당일 거래 흐름입니다. 수급 기준일 ${finEsc(foreignAsOf)} · 표출 시각 ${finEsc(observedAt)}.</p>
        ${/^\d{4}-\d{2}-\d{2}$/.test(foreignAsOf) ? msStaleNote('KRX 공개 대시보드 수급', foreignAsOf) : ''}
        <div class="fin-cards">
            ${msCard('외국인 K200 선물 순매수', `<span class="${futuresFlow.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msSignedJo(futuresFlow.net_krw)}</span>`,
                `매수 ${msJo(futuresFlow.buy_krw)} · 매도 ${msJo(futuresFlow.sell_krw)}`, 'kr_investor')}
            ${msCard('외국인 콜 순매수', callState.ok ? `<span class="${callP.foreign.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msKrwEok(callP.foreign.net_krw)}</span>` : '—',
                callState.ok ? `${finEsc(callP.as_of || '')} · 매수 ${msKrwEokLevel(callP.foreign.buy_krw)} · 매도 ${msKrwEokLevel(callP.foreign.sell_krw)}` : msMissing(callState.reason),
                has15007Hist ? 'kr_15007_hist' : null)}
            ${msCard('외국인 풋 순매수', putState.ok ? `<span class="${putP.foreign.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msKrwEok(putP.foreign.net_krw)}</span>` : '—',
                putState.ok ? `${finEsc(putP.as_of || '')} · 매수 ${msKrwEokLevel(putP.foreign.buy_krw)} · 매도 ${msKrwEokLevel(putP.foreign.sell_krw)}` : msMissing(putState.reason),
                has15007Hist ? 'kr_15007_hist' : null)}
            ${msCard('풋 순매수 − 콜 순매수', relKrw === null ? '—' : `<span class="${relKrw >= 0 ? 'fin-up' : 'fin-down'}">${msKrwEok(relKrw)}</span>`,
                relKrw === null ? msMissing('콜·풋 모두 관측 필요') : `${relLabel} · 당일 거래 흐름의 상대값 — 방향·OI·헤지 판정 아님`,
                has15007Hist ? 'kr_15007_hist' : null)}
        </div>
        ${msTable(['구분', '매도', '매수', '순매수', '데이터 상태'], [
            (() => {
                const r = flowRow('K200 선물', futuresFlow, (dashboard.futures || {}).quality === 'observed' ? '실측' : '—');
                if (msFlowOk(D.flow)) r[4] += ' <button class="mm-view-btn" data-ms-modal="flow_hist:futures">추이</button>';
                return r;
            })(),
            flowRow15007('K200 콜옵션', callP, callState),
            flowRow15007('K200 풋옵션', putP, putState),
            [finEsc('K200 옵션 전체 (참고)'), msKrwEokLevel(optionsFlow.sell_krw), msKrwEokLevel(optionsFlow.buy_krw),
                `<span class="${optionsFlow.net_krw >= 0 ? 'fin-up' : 'fin-down'}">${msKrwEok(optionsFlow.net_krw)}</span>`,
                (dashboard.options_total || {}).quality === 'observed' ? '실측 · 콜/풋 미분리' : '—'],
        ])}
        <p class="fin-note ms-warn">${finEsc(sourceNote)} 콜/풋 행은 옵션 전체를 배분해 추정하지 않으며, KRX 15007 원자료가 있는 날에만 값을 보입니다.
            콜·풋 매수·매도·순매수는 당일 외국인 거래 흐름입니다. 외국인 미결제약정, 신규 포지션, 헤지 목적 또는 다음 가격 방향을 확정하지 않습니다.</p>
    </section>

    ${msFlowSection(D)}

    ${msOptionOiSection(D)}

    ${msProgramSection(D)}

    <section class="fin-block fin-block-wide">
        <h2>KOSPI200 시장 전체 거래 활동</h2>
        <p class="fin-lead">아래는 투자자별 수급과 별개인 시장 전체 체결 합계입니다. 활동 규모를 보되, 외국인 거래로 읽으면 안 됩니다.</p>
        ${msStaleNote('KRX OpenAPI 시장 활동 스냅샷', kr.as_of)}
        <div class="fin-cards">
            ${msCard('K200 선물 거래대금', msJo(futures.trading_value_krw),
                `거래량 ${msNum(futures.volume)}계약 · ${finEsc(futures.coverage_ko || '')}`, 'hist:act:fut_tv')}
            ${msCard('K200 콜옵션 거래량', Number.isFinite(options.call_volume) ? `${msNum(options.call_volume)}계약` : '—',
                `거래대금 ${msKrwEokLevel(options.call_trading_value_krw)}`, 'hist:act:call_vol')}
            ${msCard('K200 풋옵션 거래량', Number.isFinite(options.put_volume) ? `${msNum(options.put_volume)}계약` : '—',
                `거래대금 ${msKrwEokLevel(options.put_trading_value_krw)}`, 'hist:act:put_vol')}
            ${msCard('풋/콜 거래량 비율', Number.isFinite(options.put_call_volume) ? options.put_call_volume.toFixed(2) : '—',
                '시장 전체 풋 거래량 ÷ 콜 거래량', 'hist:act:pc_vol')}
            ${(() => {
                const rows = msFlowActivityRows();
                const lastR = rows ? rows[rows.length - 1] : null;
                if (!lastR || !Number.isFinite(lastR.pc_tv)) return '';
                return msCard('풋/콜 거래대금 비율 (15007)', lastR.pc_tv.toFixed(2),
                    `${finEsc(lastR.date)} · 2019~ ${msRankLabel(rows.map((r) => r.pc_tv), lastR.pc_tv) || '—'} · 콜 ${msKrwEokLevel(lastR.call_tv)} · 풋 ${msKrwEokLevel(lastR.put_tv)}`,
                    'hist:act:pc_tv');
            })()}
            ${msCard('오늘 전체 활동 표', '한 번에 보기', '선물·콜·풋 거래량과 거래대금', 'kr_activity')}
        </div>
        <p class="fin-note">시장 활동 기준일 ${finEsc(activityAsOf)} · 선물 ${finEsc(futures.source || '출처 미표기')} · 옵션 ${finEsc(options.source || '출처 미표기')}. 이 보드에서는 한국 OI를 표시하지 않습니다.
            ${msFlowActivityRows() ? ' 거래대금 추이는 KRX 15007 시장 전체 거래대금(2019~)으로, 거래량 추이는 일별 활동 로그로 그립니다.'
                : msHistRows('activity').length < MS_HIST_MIN_OBS ? ' 일별 이력이 쌓이는 중이라 카드를 열면 추이 대신 관측일수가 표시됩니다.' : ' 카드를 열면 일별 추이가 표시됩니다.'}</p>
        ${(callP || putP) ? `
        <h3 class="fin-sub">KOSPI200 콜·풋 시장 전체 거래대금 (체결 상대방 포함 활동 규모)</h3>
        ${msTable(['상품', '시장 전체 매도 거래대금', '시장 전체 매수 거래대금', '거래량', '방향 해석'], [
            ['K200 콜옵션',
                Number.isFinite(callP?.market_total?.sell_krw) ? msKrwEokLevel(callP.market_total.sell_krw) : '—',
                Number.isFinite(callP?.market_total?.buy_krw) ? msKrwEokLevel(callP.market_total.buy_krw) : '—',
                Number.isFinite(options.call_volume) ? `${msNum(options.call_volume)}계약` : '—', '활동 규모만'],
            ['K200 풋옵션',
                Number.isFinite(putP?.market_total?.sell_krw) ? msKrwEokLevel(putP.market_total.sell_krw) : '—',
                Number.isFinite(putP?.market_total?.buy_krw) ? msKrwEokLevel(putP.market_total.buy_krw) : '—',
                Number.isFinite(options.put_volume) ? `${msNum(options.put_volume)}계약` : '—', '활동 규모만'],
        ])}
        <p class="fin-note">시장 전체 매수·매도 거래대금은 체결 상대방을 포함한 활동 규모이며, 매수 우위 신호가 아닙니다.
            콜 기준일 ${finEsc(callP?.as_of || '—')} · 출처 ${finEsc(callP?.source || '—')} · quality ${finEsc(callP?.quality || '—')} ·
            풋 기준일 ${finEsc(putP?.as_of || '—')} · 출처 ${finEsc(putP?.source || '—')} · quality ${finEsc(putP?.quality || '—')}.</p>` : ''}
    </section>

    <p class="mm-disclaimer">${finEsc(kr.disclaimer_ko || '공개·신청 API 기반 관측값입니다. 투자 권유가 아닙니다.')}</p>`;
};

// --- 모달 --------------------------------------------------------------------
const msModalFor = (key, D) => {
    const t = D.transmission || {};
    const m = D.micro || {};
    const kr = (D.board || {}).kr || {};
    if (key === 'kr_investor') {
        const dashboard = (kr.investor_nets || {}).public_dashboard || {};
        const futures = ((dashboard.futures || {}).investors || {}).foreign || {};
        const options = ((dashboard.options_total || {}).investors || {}).foreign || {};
        const products15007 = msPick15007(D);
        const callP = products15007.options_call || null;
        const putP = products15007.options_put || null;
        const callState = ms15007State(callP);
        const putState = ms15007State(putP);
        const row15007 = (label, p, state) => state.ok
            ? [label, msKrwEokLevel(p.foreign.sell_krw), msKrwEokLevel(p.foreign.buy_krw), msKrwEok(p.foreign.net_krw), `KRX 15007 (${finEsc(p.as_of || '—')})`]
            : [label, '—', '—', '—', msMissing(state.reason)];
        return { title: '외국인 KOSPI200 파생 수급 — 원자료 구분',
            html: msTable(['구분', '매도', '매수', '순매수', '출처'], [
                ['K200 선물', msJo(futures.sell_krw), msJo(futures.buy_krw), msSignedJo(futures.net_krw), 'KRX 공개 대시보드'],
                row15007('K200 콜옵션', callP, callState),
                row15007('K200 풋옵션', putP, putState),
                ['K200 옵션 전체', msKrwEokLevel(options.sell_krw), msKrwEokLevel(options.buy_krw), msKrwEok(options.net_krw), 'KRX 공개 대시보드 · 콜/풋 미분리'],
            ]) + (() => {
                const inv = [['foreign', '외국인'], ['institution', '기관'], ['retail', '개인']];
                const f = (dashboard.futures || {}).investors || {};
                const o = (dashboard.options_total || {}).investors || {};
                const rows = inv.map(([k, ko]) => [ko,
                    `<span class="${msSignCls((f[k] || {}).net_krw)}">${msSignedJo((f[k] || {}).net_krw)}</span>`,
                    `<span class="${msSignCls((o[k] || {}).net_krw)}">${msKrwEok((o[k] || {}).net_krw)}</span>`]);
                return `<h3 class="fin-sub">주체별 순매수 · 공개 대시보드 (${finEsc((dashboard.futures || {}).as_of || '—')})</h3>`
                    + msTable(['주체', 'K200 선물', 'K200 옵션 전체'], rows);
            })() + '<p class="fin-note">공개 대시보드의 옵션 전체 금액을 콜·풋으로 나누어 추정하지 않습니다. 콜·풋은 인증된 KRX 15007 원자료가 있는 날에만 값을 보입니다. 매수·매도·순매수는 당일 거래 흐름이며 보유 포지션이나 헤지 방향이 아닙니다.</p>' };
    }
    if (key === 'kr_activity') {
        const futures = kr.kospi200_futures || {};
        const options = kr.kospi200_options || {};
        return { title: 'KOSPI200 시장 전체 거래 활동',
            html: msTable(['상품', '거래량', '거래대금', '범위'], [
                ['K200 선물', `${msNum(futures.volume)}계약`, msJo(futures.trading_value_krw), finEsc(futures.coverage_ko || '—')],
                ['K200 콜옵션', `${msNum(options.call_volume)}계약`, msKrwEokLevel(options.call_trading_value_krw), finEsc(options.coverage_ko || '—')],
                ['K200 풋옵션', `${msNum(options.put_volume)}계약`, msKrwEokLevel(options.put_trading_value_krw), finEsc(options.coverage_ko || '—')],
            ]) + '<p class="fin-note">시장 전체 체결 합계입니다. 외국인·개인·기관별 거래를 뜻하지 않으며 OI도 아닙니다.</p>' };
    }
    // Investor net history for one 15007 product (futures / call / put).
    if (key.startsWith('flow_hist:')) {
        const F = D.flow;
        if (!msFlowOk(F)) return { title: '추이', html: msMissing('KRX 15007 이력 없음') };
        const product = key.slice(10);
        const P = MS_FLOW_PRODUCTS.find((x) => x.key === product) || MS_FLOW_PRODUCTS[0];
        return { title: `${P.ko} 투자자별 순매수 추이 — KRX 15007`, key,
            html: msStaleNote('KRX 15007 투자자별 수급', (F.last_dates || {}).flow)
                + msHistBlock(msFlowHistSpecs(F, P.key))
                + '<p class="fin-note ms-warn">당일 거래대금 순매수입니다. 미결제약정·보유 포지션·헤지 의도가 아닙니다. 네 주체(기타법인 포함)의 합은 0입니다.</p>' };
    }
    if (key.startsWith('oi_hist:')) {
        const F = D.flow;
        const O = msFlowOk(F) ? F.option_oi : null;
        if (!O) return { title: '추이', html: msMissing('옵션 미결제약정 이력 없음') };
        const rows = F.dates.map((date, i) => ({ date, i, quality: 'observed', source: 'KRX 15018 최근월물 옵션' }))
            .filter((r) => Number.isFinite(O.call_oi[r.i]) || Number.isFinite(O.put_oi[r.i]));
        const specs = {
            totals: [{ rows, label: '콜 미결제약정 합계', unit: '계약', pick: (r) => O.call_oi[r.i] },
                { rows, label: '풋 미결제약정 합계', unit: '계약', pick: (r) => O.put_oi[r.i] }],
            pc: [{ rows, label: '풋/콜 미결제약정 비율', unit: '', pick: (r) => O.pc_oi[r.i] }],
            iv: [{ rows, label: 'ATM 내재변동성', unit: '%', pick: (r) => O.atm_iv[r.i] }],
        }[key.slice(8)] || [];
        return { title: `${(specs[0] || {}).label || '옵션'} 추이 — KRX 15018`, key,
            html: msStaleNote('옵션 미결제약정', (F.last_dates || {}).option_oi) + msHistBlock(specs)
                + '<p class="fin-note ms-warn">최근월물 시장 전체 미결제약정입니다 (외국인 보유분 아님). 만기 다음 날 월물이 바뀌어 합계가 끊깁니다.</p>' };
    }
    // KRX 15007 콜/풋 일자별 추이. options_total과 달리 이 계열은 배분 추정이
    // 아니라 인증된 원자료이므로, 관측되지 않은 날은 채우지 않고 그대로 빈다.
    if (key === 'kr_15007_hist') {
        const products15007 = msPick15007(D);
        const callSeries = (products15007.options_call || {}).series || [];
        const putSeries = (products15007.options_put || {}).series || [];
        return { title: '외국인 KOSPI200 콜·풋 순매수 — KRX 15007',
            html: msHistBlock(ms15007Series(callSeries, putSeries))
            + `<p class="fin-note ms-warn">콜·풋 매수·매도·순매수는 당일 외국인 거래 흐름입니다. 외국인 미결제약정, 신규 포지션, 헤지 목적 또는 다음 가격 방향을 확정하지 않습니다.
               풋 순매수 − 콜 순매수는 두 값이 모두 그 날짜의 인증된 관측치일 때만 계산되며, 휴장일이나 15007 미수신일은 채우지 않습니다.</p>` };
    }
    // A metric's own trend, plus the paired one that gives it scale: volume
    // beside turnover, a ratio beside the denominator it is drawn against.
    if (key.startsWith('hist:')) {
        const which = key.slice(5);
        const paired = {
            'act:fut_tv': 'act:fut_vol', 'act:fut_vol': 'act:fut_tv',
            'act:call_tv': 'act:call_vol', 'act:call_vol': 'act:call_tv',
            'act:put_tv': 'act:put_vol', 'act:put_vol': 'act:put_tv',
            'act:pc_vol': 'act:pc_tv', 'act:pc_tv': 'act:pc_vol',
            'lev:ratio': 'lev:kospi_tv',
        }[which];
        const specs = [MS_HIST_SERIES[which], paired ? MS_HIST_SERIES[paired] : null].filter(Boolean);
        if (!specs.length) return { title: '추이', html: '<p class="fin-note">알 수 없는 계열입니다.</p>', key };
        return { title: `${specs[0].label} 추이`,
            html: msHistBlock(specs)
                + '<p class="fin-note">당일 거래 흐름의 추이입니다. 미결제약정(OI)이나 보유 포지션이 아닙니다.</p>', key };
    }
    if (key === 'conc' || key.startsWith('conc:')) {
        const pts = (D.conc || {}).points || [];
        const which = key.split(':')[1] || 'top2';
        const spec = {
            top2: { f: 'conc_top2_samsung_hynix_pct', ko: '상위 2 (삼성·하닉)' },
            top5: { f: 'conc_top5_pct', ko: '상위 5' },
            top10: { f: 'conc_top10_pct', ko: '상위 10' },
        }[which] || { f: 'conc_top2_samsung_hynix_pct', ko: '상위 2 (삼성·하닉)' };
        const st = (D.conc || {}).stats || {};
        const latest = (D.conc || {}).latest || {};
        const dates = pts.map((p) => p.date);
        const values = pts.map((p) => Number(p[spec.f]));
        // The constituent names live on the snapshot, not on the history rows,
        // so they describe the latest ranking rather than the whole window.
        const names = { top2: (m.concentration || {}).top5_tickers?.slice(0, 2),
            top5: (m.concentration || {}).top5_tickers,
            top10: (m.concentration || {}).top10_tickers }[which] || [];
        const known = (D.levels || {}).tickers || {};
        (m.stocks || []).forEach((s) => { if (s.ticker && !known[s.ticker]) known[s.ticker] = { label_ko: s.name }; });
        // KRX preferred shares share the first five digits with the common
        // stock, so a name the payload never carried is still recoverable.
        const label = (tk) => {
            const hit = (known[tk] || {}).label_ko;
            if (hit) return `${hit} (${tk})`;
            const base = Object.keys(known).find((k) => k !== tk && k.slice(0, 5) === String(tk).slice(0, 5));
            return base ? `${known[base].label_ko}우 (${tk})` : tk;
        };
        return { title: `코스피 집중도 · ${spec.ko} 시가총액 비중 추이`,
            html: mmLineChart(dates, values, { unit: '%', label: spec.ko })
                + (names.length ? `<p class="ms-lead-strong">구성 종목 · ${names.map((t) => finEsc(label(t))).join(' · ')}</p>` : '')
                + `<p class="fin-note">${pts.length}거래일 (${finEsc(dates[0] || '')} ~ ${finEsc(dates[dates.length - 1] || '')})`
                + (which === 'top2' && Number.isFinite(st.conc_top2_chg_60d)
                    ? ` · 60일 변화 ${st.conc_top2_chg_60d > 0 ? '+' : ''}${st.conc_top2_chg_60d.toFixed(2)}%p` : '')
                + ` · quality ${finEsc(latest.quality || '—')} · 출처 ${finEsc(latest.source || '—')}`
                + `. 유니버스 시가총액 대비 비중이며 지수 산출 가중치가 아닙니다. 구성 종목은 최신일(${finEsc(latest.date || '—')}) 기준입니다.</p>` };
    }
    if (key.startsWith('dir:')) {
        const which = key.slice(4);
        const r = m.market_letf_derivatives_ratios || {};
        const b = (r.by_direction || {})[which] || {};
        const ko = { long: '정방향 레버리지 (Long)', inverse: '인버스 (-1X)',
            inverse_2x: '인버스 (-2X)', gobus_inverse_2x: '지수 인버스 (-2X)' }[which] || which;
        const named = (r.top_inverse_gobus_by_tv || []).filter((p) => p.direction === which);
        return { title: `${ko} — 추이와 구성`,
            html: msHistBlock(msDirSeries(which, ko))
            + `<h3 class="fin-sub">오늘 구성</h3>`
            + msTable(['항목', '값'], [
                ['거래대금', msJo(b.trading_value_krw)],
                ['상품 수', `${msNum(b.n_products)}종`],
                ['레버리지·인버스 거래대금 내 비중', `${(b.share_of_lev_tv_pct ?? 0).toFixed(2)}%`],
                ['코스피 현물 거래대금 대비', `${(b.share_of_kospi_tv_pct ?? 0).toFixed(2)}%`],
                ['순자산 프록시(AUM)', msJo(b.aum_proxy_krw)],
            ])
            + (named.length ? `<h4 class="ms-sub-h">거래대금 상위 상품</h4>` + msTable(['상품', '종목코드', '분류', '거래대금'],
                named.map((p) => [finEsc(p.name), finEsc(p.ticker), finEsc(p.category), msJo((p.trading_value_jo || 0) * 1e12)])) : '')
            + `<p class="fin-note">quality ${finEsc(r.quality || '—')} · 관측일 ${finEsc(m.as_of || '—')} · 출처 ${finEsc(r.source || '—')}.
               거래대금이며 미결제약정(OI)이나 보유 포지션이 아닙니다.</p>` };
    }
    if (key === 'alert_letf') {
        const h = (D.alerts || {}).kr_hynix_letf || {};
        const s = h.sample || {};
        return { title: 'SK하이닉스 단일종목 레버·인버스 ETF 비율',
            html: msHistBlock(msStockLetfSeries('000660', 'SK하이닉스'))
            + `<h3 class="fin-sub">오늘 값</h3>`
            + msTable(['항목', '값'], [
                ['오늘 비율', Number.isFinite(h.today_ratio) ? `${(h.today_ratio * 100).toFixed(2)}%` : '—'],
                ['관찰 레벨', finEsc(h.today_level || '—')],
                ['정의', finEsc(h.metric_ko || '—')],
                ['표본 시작', finEsc(s.start || '—')],
                ['표본 거래일', s.n_active_days ? `${msNum(s.n_active_days)}일` : '—'],
            ])
            + (h.levels ? `<h4 class="ms-sub-h">관찰 레벨 구간 (과거 표본 기준)</h4>` + msTable(
                ['레벨', '비율 구간', '표본일', '구간 중앙값', '다음날 -2% 이상 하락 비율'],
                Object.entries(h.levels).map(([k, v]) => [
                    finEsc(k),
                    `${Number.isFinite(v.ratio_min) ? (v.ratio_min * 100).toFixed(0) + '%' : '0%'} ~ ${Number.isFinite(v.ratio_max) ? (v.ratio_max * 100).toFixed(0) + '%' : '이상'}`,
                    `${msNum(v.n)}일`,
                    Number.isFinite(v.ratio_median_in_bucket) ? `${(v.ratio_median_in_bucket * 100).toFixed(1)}%` : '—',
                    Number.isFinite(v.frac_next_down2) ? `${(v.frac_next_down2 * 100).toFixed(1)}%` : '—',
                ]))
                + `<p class="fin-note">표본 ${msNum((h.sample || {}).n_active_days)}일은 통계로 쓰기에 짧습니다. 구간별 하락 비율이 서로 비슷해 이 지표만으로 방향을 예측할 수 없습니다.</p>` : '')
            + `<p class="fin-note">${finEsc(s.note_ko || '')} ${finEsc(h.limitation_ko || '')}
               출처 ${finEsc(h.data_source || '—')} · 관측일 ${finEsc((D.alerts || {}).as_of || '—')}.
               ${msHistRows('stockLetf').filter((r) => r.ticker === '000660').length < MS_HIST_MIN_OBS ? '일별 이력이 아직 쌓이지 않아 오늘 값과 표본 통계만 있습니다.' : '위 추이는 저장된 일별 관측치이며, 아래 표본 통계와는 별개입니다.'}</p>` };
    }
    // Samsung Electronics carries the same single-stock LETF fields as Hynix
    // but has no alert-bucket engine behind it -- just the trend plus today's
    // snapshot from market_microstructure_v1, not the win-rate-by-bucket table.
    if (key.startsWith('stock_letf:')) {
        const ticker = key.slice(11);
        const stocks = Array.isArray(m.stocks) ? m.stocks : [];
        const st = stocks.find((x) => x.ticker === ticker) || {};
        const ko = st.name || ticker;
        const spotTv = st.spot_trading_value_krw ?? st.adv_spot_krw;
        return { title: `${ko} 단일종목 레버·인버스 ETF 비율`,
            html: msHistBlock(msStockLetfSeries(ticker, ko))
            + `<h3 class="fin-sub">오늘 값</h3>`
            + msTable(['항목', '값'], [
                ['LETF 거래대금', msJo(st.letf_trading_value_krw)],
                ['현물 당일 거래대금', msJo(spotTv)],
                ['LETF / 현물 비율', finPct(st.letf_turnover_ratio)],
                ['LETF 합계 순자산 (AUM)', `${msJo(st.letf_aum_sum_krw)} <span class="ms-q">${finEsc(msAumProvenance(st.letf_aum_quality))}</span>`],
            ])
            + `<p class="fin-note">관측일 ${finEsc(m.as_of || '—')}. 거래대금 기준 관측치이며 보유 포지션이나 다음 가격 방향이 아닙니다.
               ${msHistRows('stockLetf').filter((r) => r.ticker === ticker).length < MS_HIST_MIN_OBS ? '일별 이력이 아직 쌓이지 않아 오늘 값만 있습니다.' : ''}</p>` };
    }
    if (key === 'letf_cat') {
        const cs = m.letf_category_share || {};
        const by = cs.by_category || {};
        const CAT_KO = { index: '지수', sector: '섹터', single_stock: '단일종목 (삼전·하닉)', overseas: '해외' };
        // Sorted by size: the point of this table is that 지수 dwarfs the rest,
        // which an insertion-ordered listing hides.
        const catRows = Object.entries(by).sort((a, b) =>
            (b[1].trading_value_krw || 0) - (a[1].trading_value_krw || 0));
        return { title: '레버리지·인버스 ETF 거래대금 비율 추이',
            html: msHistBlock([MS_HIST_SERIES['lev:ratio'], MS_HIST_SERIES['lev:kospi_tv']])
            + (catRows.length ? `<h3 class="fin-sub">오늘 분류별 거래대금</h3>`
                + msTable(['분류', '상품 수', '거래대금', '레버·인버스 내 비중', '코스피 현물 대비'],
                    catRows.map(([k, v]) => [
                        finEsc(CAT_KO[k] || k), msNum(v.n_products), msJo(v.trading_value_krw),
                        Number.isFinite(v.share_of_lev_tv_pct) ? `${v.share_of_lev_tv_pct.toFixed(1)}%` : '—',
                        Number.isFinite(v.share_of_kospi_tv_pct) ? `${v.share_of_kospi_tv_pct.toFixed(2)}%` : '—',
                    ])) : '')
            + `<p class="fin-note">
               <strong>레버·인버스 내 비중</strong> = 그 분류 ÷ 레버·인버스 ETF 전체(${msJo(cs.levered_inverse_tv_krw)}) — 네 분류를 더하면 100%입니다.<br>
               <strong>코스피 현물 대비</strong> = 그 분류 ÷ 코스피 현물 거래대금(${msJo(cs.kospi_cash_tv_krw)}) — 분모가 다른 시장이라 점유율이 아니고, 다 더해도 100%가 되지 않습니다.</p>` };
    }
    // The chart already shows the shape of this distribution; the modal is for
    // reading exact per-band figures, so it adds the numeric columns the bars
    // cannot carry rather than repeating the bars alone.
    if (key === 'price_level_detail') {
        const { isIndex, src, pts, rows } = msLevelsCompute(D);
        const who = isIndex ? '코스피 지수' : ((D.levels || {}).tickers || {})[MS_TICKER]?.label_ko || MS_TICKER;
        if (!rows.length) return { title: `${who} 가격대별 상세`, html: `<p class="fin-note">${msMissing('구간별 수급 없음')}</p>`, key };
        return { title: `${who} 가격대별 상세 · ${pts.length}거래일`,
            html: msDivergingBars(rows, {
                legend: [{ key: 'retail', name: '개인' }, { key: 'foreign', name: '외국인' }, { key: 'inst', name: '기관' }],
            })
            + msTable(['가격대', '거래일', '개인', '외국인', '기관', '합계'],
                rows.map((r) => {
                    const [rt, fg, it] = r.series.map((s) => s.value);
                    const sum = rt + fg + it;
                    const cell = (v) => `<span class="${v >= 0 ? 'fin-up' : 'fin-down'}">${msEok(v)}</span>`;
                    return [finEsc(r.label), finEsc(r.sub), cell(rt), cell(fg), cell(it), cell(sum)];
                }))
            + `<p class="fin-note">표시 구간 ${finEsc(pts[0]?.date || '')} ~ ${finEsc(pts[pts.length - 1]?.date || '')} · 단위 억원.
               일별 순매수를 종가 레벨에 귀속해 합산한 값이며, 체결 단위 매집도가 아닙니다.
               quality ${finEsc(src.quality || '—')} · 출처 ${finEsc(src.source || '—')}.</p>`, key };
    }
    // One price band, opened from a click on its row in the chart: which days
    // the price sat in that band, and who was buying on each of them. The
    // chart can only show the band's total, which hides a band where one
    // group bought early and sold late back to roughly zero.
    if (key.startsWith('band:')) {
        const { isIndex, tickers, pts, bins, rows } = msLevelsCompute(D);
        const bi = Number(key.slice(5));
        const band = bins[bi], row = rows[bi];
        if (!band || !row) return null;
        const who = isIndex ? '코스피 지수' : (tickers[MS_TICKER] || {}).label_ko || MS_TICKER;
        const inBand = pts.filter((d) => d.close >= band.price_lo && d.close < band.price_hi);
        const cell = (v) => `<span class="${v >= 0 ? 'fin-up' : 'fin-down'}">${msEok(v)}</span>`;
        return { title: `${who} · ${msNum(band.price_lo)} ~ ${msNum(band.price_hi)} 구간`,
            html: msDivergingBars([row], { legend: [{ key: 'retail', name: '개인' }, { key: 'foreign', name: '외국인' }, { key: 'inst', name: '기관' }] })
                + `<h3 class="fin-sub">이 구간에 있었던 ${inBand.length}거래일</h3>`
                + msTable(['날짜', '종가', '개인', '외국인', '기관'],
                    inBand.map((d) => [finEsc(d.date), msNum(d.close), cell(d._retail), cell(d._foreign), cell(d._inst)]))
                + `<p class="fin-note">단위 억원 · 위 막대는 이 구간 전체 합계, 아래 표는 그 합계를 만든 하루하루입니다.
                   합계가 0에 가까워도 안에서 크게 사고 판 날이 있을 수 있습니다.</p>`, key };
    }
    // "종가일 수급" names one day; a single day's net-buying has no price
    // spread to attribute it to, so this widens to the 5 trading days ending
    // there -- what the price-level chart calls a bin, here a single week is
    // short enough that per-day rows read cleaner than binning them again.
    if (key.startsWith('week:')) {
        const [, ticker, anchorDate] = key.split(':');
        const info = ((D.levels || {}).tickers || {})[ticker];
        const days = (info || {}).days || [];
        const idx = days.findIndex((d) => d.date === anchorDate);
        if (idx < 0) return { title: `${(info || {}).label_ko || ticker} 그 주`, html: `<p class="fin-note">${msMissing('해당 날짜 없음')}</p>`, key };
        const week = days.slice(Math.max(0, idx - 4), idx + 1);
        const rows = week.map((d) => ({
            label: finEsc(d.date), sub: `종가 ${msNum(d.close)}`,
            series: [
                { key: 'retail', name: '개인', value: (d.retail_net_krw || 0) / 1e8 },
                { key: 'foreign', name: '외국인', value: (d.foreign_net_krw || 0) / 1e8 },
                { key: 'inst', name: '기관', value: (d.institution_net_krw || 0) / 1e8 },
            ],
            valueText: `개인 ${msEok((d.retail_net_krw || 0) / 1e8)} · 외인 ${msEok((d.foreign_net_krw || 0) / 1e8)}`,
        }));
        return { title: `${(info || {}).label_ko || ticker} · ${finEsc(anchorDate)} 포함 그 주 (${week.length}거래일)`,
            html: msDivergingBars(rows, { legend: [{ key: 'retail', name: '개인' }, { key: 'foreign', name: '외국인' }, { key: 'inst', name: '기관' }] })
                + msTable(['날짜', '종가', '개인', '외국인', '기관'],
                    week.map((d) => {
                        const cell = (v) => `<span class="${v >= 0 ? 'fin-up' : 'fin-down'}">${msEok(v / 1e8)}</span>`;
                        return [finEsc(d.date), msNum(d.close), cell(d.retail_net_krw || 0), cell(d.foreign_net_krw || 0), cell(d.institution_net_krw || 0)];
                    }))
                + `<p class="fin-note">단위 억원 · 하루하루의 실측 순매수이며 체결 단위 매집도가 아닙니다.</p>`, key };
    }
    if (key === 'letf_products') {
        const stocks = Array.isArray(m.stocks) ? m.stocks : [];
        const sel = stocks.find((x) => x.ticker === MS_STOCK) || stocks[0];
        if (!sel) return null;
        return { title: `${sel.name} 단일종목 ETF 상품별`,
            html: msTable(['상품', '배수', '순자산(AUM)', '거래대금', '방향'],
                (sel.products || []).map((p) => [finEsc(p.name), `${p.L > 0 ? '+' : ''}${p.L}배`,
                    `${msJo(p.aum)} <span class="ms-q">${finEsc(msAumProvenance(p.aum_quality))}</span>`,
                    msJo(p.trading_value), p.direction === 'long' ? '정방향' : '인버스']))
                + '<p class="fin-note">NAV는 공개 스냅샷에 없습니다. 거래대금은 실측이며, 순자산(AUM)은 상품마다 관측 또는 시가총액 기반 프록시로 표시가 갈립니다 — 각 행의 괄호를 확인하세요.</p>' };
    }
    if (key.startsWith('ev:')) {
        const sym = key.slice(3);
        const e = (t.evidence_us || []).find((x) => x.symbol === sym);
        if (!e) return null;
        // rules_ko lists every condition that actually fired for this name;
        // the old single rule_ko string always named downside_put_bid even
        // when the row qualified on a gap or short-change rule instead.
        const rules = Array.isArray(e.rules_ko) && e.rules_ko.length ? e.rules_ko
            : e.rule_ko ? [e.rule_ko] : [];
        return { title: `${sym} — 판정 근거`,
            html: msTable(['항목', '값'], [
                ['P/C 거래량', Number.isFinite(e.put_call_volume) ? e.put_call_volume.toFixed(4) : '—'],
                ['P/C 미결제약정', Number.isFinite(e.put_call_oi) ? e.put_call_oi.toFixed(4) : '—'],
                ['옵션 총 거래량', msNum(e.options_total_volume)],
                ['프리마켓 갭', finPct(e.premarket_gap, 2)],
                ['공매도 잔고 증감', Number.isFinite(e.short_chg_pct) ? `${e.short_chg_pct.toFixed(3)}%` : '—'],
                ['당일 수익률', finPct(e.day_return, 3)],
                ['레짐', (e.regimes || []).join(', ')],
                ['스트레스', finEsc(e.stress_level || '')],
            ]) + (rules.length ? `<h4 class="ms-sub-h">발동 조건</h4><ul class="fin-list">${rules.map((r) => `<li>${finEsc(r)}</li>`).join('')}</ul>` : '')
              + (e.premarket_gap_quality && e.premarket_gap_quality !== 'observed'
                  ? `<p class="fin-note">프리마켓 갭 품질: ${finEsc(e.premarket_gap_quality)}</p>` : '') };
    }
    if (key.startsWith('ch:')) {
        const c = (t.channels || {})[key.slice(3)] || {};
        return { title: '관찰 채널 구성',
            html: msTable(['US', 'KR', 'heat', '연결 유형', 'tier', '레짐'],
                (c.drivers || []).map((d) => [finEsc(d.us), finEsc(d.kr),
                    Number.isFinite(d.heat) ? d.heat.toFixed(3) : '—',
                    finEsc(d.edge_type || ''), finEsc(d.tier || ''), (d.regimes || []).join(', ')]))
            + '<p class="fin-note"><code>etf_beta</code>는 미국 ETF 수익률과 국내 종목의 통계적 연동입니다 — 옵션 포지션이 아닙니다. <code>discovered_corr</code>(tier B)는 상관에서 발견된 것이라 가중이 낮습니다.</p>' };
    }
    if (key === 'alert_vix') {
        const a = (D.alerts || {}).us_vix_to_kr || {};
        const rows = Object.entries(a)
            .filter(([, v]) => typeof v !== 'object')
            .map(([k, v]) => [finEsc(k), finEsc(String(v))]);
        return { title: 'VIX → KR 알림 임계값', html: msTable(['항목', '값'], rows) };
    }
    return null;
};

const renderMicrostructure = async (host) => {
    host.innerHTML = `<div class="fin-wrap"><p class="fin-loading">시장 미시구조 자료를 받는 중…</p></div>`;

    if (!MS_DATA) {
        const keys = Object.keys(MS_FILES);
        const got = await Promise.all(keys.map((k) => msGet(MS_FILES[k])));
        MS_DATA = {};
        keys.forEach((k, i) => { MS_DATA[k] = got[i]; });
    }
    // The append-only logs are optional: absent until the daily job writes them,
    // so a failure here must not keep the snapshot panels from rendering.
    if (!MS_HIST) {
        const hk = Object.keys(MS_HIST_FILES);
        const hgot = await Promise.all(hk.map((k) => msGetJsonl(MS_HIST_FILES[k])));
        MS_HIST = {};
        hk.forEach((k, i) => { MS_HIST[k] = hgot[i]; });
    }
    const D = MS_DATA;
    if (!Object.values(D).some(Boolean)) {
        host.innerHTML = finPlaceholder('시장 미시구조', '수급 불균형 · 가격대별 체결 · 해외-국내 선행',
            '스냅샷 JSON을 찾지 못했습니다. 일일 워크플로가 <code>public/data/</code> 에 산출합니다.');
        return;
    }

    const paint = () => {
        const tab = MS_TABS.find((x) => x.id === MS_TAB) || MS_TABS[0];
        host.innerHTML = `
        <div class="fin-wrap">
            <div class="fin-head">
                <h1>시장 미시구조</h1>
                <p class="fin-head-en">Market Microstructure</p>
                <p>공개·지연 데이터입니다. 값이 없는 항목은 채우지 않고 비워 둡니다. 투자 권유가 아닙니다.</p>
            </div>
            <div class="mm-tabs" role="tablist">
                ${MS_TABS.map((x) => `<button class="mm-tab ${x.id === MS_TAB ? 'on' : ''}" data-ms-tab="${x.id}">${finEsc(x.label)}</button>`).join('')}
            </div>
            <p class="mm-tab-desc">${finEsc(tab.blurb)}</p>
            ${MS_TAB === 'tangle' ? msTangle(D)
                : MS_TAB === 'overseas' ? msOverseas(D)
                : MS_TAB === 'levels' ? msLevelsTab(D)
                : MS_TAB === 'derivatives' ? msDerivatives(D)
                : msUsKr(D)}
            ${MS_MODAL ? `
            <div class="ms-modal-back" data-ms-modal-close="1">
                <div class="ms-modal" role="dialog">
                    <div class="ms-modal-head">
                        <h3>${finEsc(MS_MODAL.title)}</h3>
                        <button class="mm-close" data-ms-modal-close="1" aria-label="닫기">✕</button>
                    </div>
                    ${MS_MODAL.html}
                </div>
            </div>` : ''}
        </div>`;

        const on = (sel, fn) => host.querySelectorAll(sel).forEach((b) => b.addEventListener('click', (e) => fn(b, e)));
        on('[data-ms-tab]', (b) => { MS_TAB = b.dataset.msTab; MS_MODAL = null; paint(); });
        host.querySelector('[data-ms-overseas-group]')?.addEventListener('change', (e) => {
            MS_OVERSEAS_GROUP = e.target.value; MS_OVERSEAS_PRODUCT = null; paint();
        });
        host.querySelector('[data-ms-overseas-product]')?.addEventListener('change', (e) => {
            MS_OVERSEAS_PRODUCT = e.target.value; paint();
        });
        on('[data-ms-stock]', (b) => {
            MS_STOCK = b.dataset.msStock;
            // The row's own button doubles as ticker-select + drilldown open,
            // so the modal has to look up the ticker that was just picked.
            if (b.dataset.msModal) { MS_MODAL_KEY = b.dataset.msModal; MS_MODAL = msModalFor(MS_MODAL_KEY, D); }
            paint();
        });
        on('[data-ms-univ]', (b) => { MS_UNIVERSE = b.dataset.msUniv; paint(); });
        // The price-level modal is computed from MS_PERIOD, so it has to be
        // rebuilt when the window changes rather than left showing stale bands.
        on('[data-ms-period]', (b) => {
            MS_PERIOD = b.dataset.msPeriod;
            if (MS_MODAL_KEY === 'price_level_detail') MS_MODAL = msModalFor(MS_MODAL_KEY, D);
            paint();
        });
        on('[data-ms-ticker]', (b) => { MS_TICKER = b.dataset.msTicker || null; MS_TAB = 'levels'; paint(); });
        on('[data-ms-credit]', () => { MS_CREDIT_ON = !MS_CREDIT_ON; paint(); });
        // The three balance cards jump to the same-date overlay rather than
        // opening a card-specific modal, so 예탁금/신용융자/미수금 stay on
        // the overlay's per-series scale instead of gaining a second,
        // shared-axis chart of their own.
        on('[data-ms-credit-open]', () => {
            MS_TAB = 'levels';
            MS_CREDIT_ON = true;
            paint();
            host.querySelector('.ms-plc')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        // :not([data-ms-stock]) because that combination is handled above --
        // otherwise this listener would double-fire on the same click and
        // paint() twice.
        on('[data-ms-modal]:not([data-ms-stock])', (b) => { MS_MODAL_KEY = b.dataset.msModal; MS_MODAL = msModalFor(MS_MODAL_KEY, D); paint(); });
        // Switching the window re-renders the modal that is already open, so the
        // chart changes under the same heading rather than closing.
        on('[data-ms-hist-period]', (b) => {
            MS_HIST_PERIOD = b.dataset.msHistPeriod;
            if (MS_MODAL_KEY) MS_MODAL = msModalFor(MS_MODAL_KEY, D);
            paint();
        });
        on('[data-ms-modal-close]', (b, e) => { if (e.target === b) { MS_MODAL = null; MS_MODAL_KEY = null; paint(); } });
        on('[data-ms-flow-product]', (b) => { MS_FLOW_PRODUCT = b.dataset.msFlowProduct; paint(); });
        on('[data-ms-flow-win]', (b) => { MS_FLOW_WIN = b.dataset.msFlowWin; paint(); });
        on('[data-ms-oi-win]', (b) => { MS_OI_WIN = b.dataset.msOiWin; paint(); });
        on('[data-ms-prog-win]', (b) => { MS_PROG_WIN = b.dataset.msProgWin; paint(); });
        mmWireCharts(host);
        msWireMultiCharts(host);
        msWirePlcHover(host);
    };
    paint();
};
