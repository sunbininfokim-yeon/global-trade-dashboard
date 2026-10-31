// 정책 › 미국 › 예산. Ported from the reviewed prototype in PR #758
// (docs/prototypes/us-budget) into the policy surface's lazy-view contract
// used by the tariff simulator: prepare() loads data + style, markup() is the
// static frame, mount(el) wires it and returns a cleanup.
//
// Data: annual_v1.json is the reviewed snapshot (OMB actuals FY2022-2025,
// MTS FY2026 actual, April OMB proposal for the next year compared with the
// same publication's estimate). mts_live_v1.json carries the monthly MTS
// actuals the scheduled refresher appends; when it is missing or fails its
// checks the snapshot's own months are shown instead.
// User decisions kept from the handoff: 세출 → 세입 → 재정적자 (default 세출),
// 의무·재량·순이자 donut, 지출액순 → 증가율순 → 증가액순 (default 지출액순,
// also for sub-rows), defense down to accounts, proposal never shown as actual,
// monthly view shows observed months only.

const DATA = '/public/data/us_budget/';
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let stylePromise = null;
let bundlePromise = null;

function loadStyle() {
  return (stylePromise ||= new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = new URL('./style.css?v=1', import.meta.url).href;
    link.onload = resolve;
    link.onerror = () => { link.remove(); stylePromise = null; reject(new Error('예산 화면 스타일을 불러오지 못했습니다.')); };
    document.head.appendChild(link);
  }));
}

async function getJson(name) {
  const res = await fetch(DATA + name, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${name} HTTP ${res.status}`);
  return res.json();
}

// Monthly actuals the page will trust: 36 consecutive months whose deficit is
// outlays - receipts. Anything else falls back to the reviewed snapshot.
export function usableLive(live) {
  const months = live?.months;
  if (!Array.isArray(months) || months.length !== 36) return null;
  for (let i = 0; i < months.length; i += 1) {
    const m = months[i];
    if (![m.receipts, m.outlays, m.deficit].every(Number.isFinite)) return null;
    if (Math.abs(m.outlays - m.receipts - m.deficit) > 1) return null;
    if (i) {
      const [ya, ma] = months[i - 1].month.split('-').map(Number);
      const [yb, mb] = m.month.split('-').map(Number);
      if (yb * 12 + mb - (ya * 12 + ma) !== 1) return null;
    }
  }
  return live;
}

export function prepare() {
  bundlePromise ||= Promise.all([
    getJson('annual_v1.json'),
    getJson('mts_live_v1.json').catch(() => null),
  ]).catch((err) => { bundlePromise = null; throw err; });
  return Promise.all([loadStyle(), bundlePromise]);
}

export function markup() {
  return `<div id="budget-flow" class="bf-body" aria-label="미국 연방예산">
 <div class="bf-head"><div><h2>미국 연방예산</h2><div class="bf-muted">지출 구조부터 세부 내역까지 · 공식 공개자료</div></div><label class="bf-muted">회계연도 <select id="bf-year" aria-label="회계연도"></select></label></div>
 <div class="bf-top" aria-label="재정 항목"><button type="button" data-main="outlays" aria-pressed="true"><span>세출</span><strong id="bf-outlays"></strong><span class="bf-muted">조 달러</span></button><button type="button" data-main="receipts" aria-pressed="false"><span>세입</span><strong id="bf-receipts"></strong><span class="bf-muted">조 달러</span></button><button type="button" data-main="deficit" aria-pressed="false"><span>재정적자</span><strong id="bf-deficit"></strong><span class="bf-muted">조 달러</span></button></div>
 <div class="bf-muted" id="bf-source"></div>
 <div class="bf-panel" id="bf-proposal-note" hidden></div>
 <div class="bf-panel bf-ytd" id="bf-ytd" hidden></div>
 <section class="bf-panel" id="bf-content" aria-live="polite"></section>
 <details class="bf-history" id="bf-history"><summary id="bf-history-title">추이 펼치기</summary><div class="bf-toolbar"><button type="button" data-period="annual" aria-pressed="true">연간 실적·정부안</button><button type="button" data-period="monthly" aria-pressed="false">36개월 전체 실적</button></div><div id="bf-history-chart"></div><div id="bf-month-box" hidden><div class="bf-message" id="bf-month-range"></div><svg id="bf-month-chart" role="img" aria-label="36개월 월별 세입과 세출"></svg><label class="bf-muted">월 <select id="bf-month" aria-label="상세 월"></select></label><div id="bf-month-info" class="bf-message"></div></div></details>
 <div class="bf-footer" id="bf-footer"></div>
</div>`;
}

export function mount(root) {
  if (!root || !bundlePromise) return () => {};
  let alive = true;
  const observers = [];
  bundlePromise.then(([annual, live]) => { if (alive) start(root, annual, usableLive(live), observers); })
    .catch((err) => {
      if (!alive) return;
      const area = root.querySelector('#bf-content');
      area.setAttribute('role', 'alert');
      area.textContent = '예산 데이터를 읽지 못했습니다. 잠시 후 다시 열어 주세요.';
      console.error('[us-budget]', err);
    });
  return () => { alive = false; observers.forEach((o) => o.disconnect()); };
}

function start(root, annual, live, observers) {
  // Work on a copy: the cached bundle is shared across visits.
  const bundle = JSON.parse(JSON.stringify(annual));
  const data = bundle.budget;
  const $ = (s) => root.querySelector(s);
  const $$ = (s) => [...root.querySelectorAll(s)];
  for (const [year, children] of Object.entries(bundle.defense)) {
    const node = data.discretionary[year]?.find((r) => r.id === '7');
    if (node) node.children = children;
  }
  const future = bundle.fy2027;
  const PROPOSAL = Number(future.year.fy);
  const BASE = PROPOSAL - 1; // same-publication estimate year used as the comparison base
  data.years[PROPOSAL] = future.year;
  data.receipts[PROPOSAL] = future.receipts;
  data.types[PROPOSAL] = future.types;
  data.discretionary[PROPOSAL] = future.discretionary;
  const actualYears = Object.keys(data.years).map(Number).filter((y) => y !== PROPOSAL);
  const LATEST_ACTUAL = Math.max(...actualYears);
  const monthly = live ? live.months : data.monthly;
  const fytd = live?.fytd && live.fytd.fy === PROPOSAL && !live.fytd.complete ? live.fytd : null;

  const state = { fy: PROPOSAL, main: 'outlays', bucket: 'discretionary', sort: 'value', expanded: false, period: 'annual', month: monthly.at(-1).month };
  const isProposal = () => state.fy === PROPOSAL;
  const valueStatus = () => (isProposal() ? '정부안·추정' : '실적');
  const comparison = () => (isProposal() ? future.baseline : `${state.fy - 1} 실적 → ${state.fy} 실적`);
  const changeLabel = () => (isProposal() ? `FY${BASE} 정부 추정 대비` : '전년 대비');
  const yearLabel = (y) => `FY${y}${isProposal() ? (Number(y) === PROPOSAL ? ' 정부안' : ' 정부 추정') : ''}`;
  const palette = ['var(--bf-one)', 'var(--bf-two)', 'var(--bf-three)', 'var(--bf-four)', 'var(--bf-five)', 'var(--bf-muted)', 'var(--bf-edge)'];
  const bn = (n) => `${(n / 1e9).toLocaleString('ko-KR', { maximumFractionDigits: 3 })} B$`;
  const tr = (n) => `${(n / 1e12).toFixed(3)}조 $`;
  const signed = (n) => (n > 0 ? '+' : '') + bn(n);
  const rate = (n, p) => (p > 0 && n >= 0 ? (n / p - 1) * 100 : null);
  const pct = (n, p) => { const v = rate(n, p); return v === null ? '증감률 제외' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`; };

  $('#bf-year').innerHTML = Object.keys(data.years).map((y) => `<option value="${y}">FY${y} ${Number(y) === PROPOSAL ? '정부안' : '실적'}</option>`).join('');
  $('#bf-month').innerHTML = monthly.map((r) => `<option>${esc(r.month)}</option>`).join('');
  $('#bf-history-title').textContent = `추이 펼치기 · 최근 ${actualYears.length}개 실적 연도 + FY${PROPOSAL} 정부안 / 36개월 실적`;
  $('#bf-month-range').textContent = `월별 실적: ${monthly[0].month}~${monthly.at(-1).month} · Treasury MTS${live ? ` ${live.mts_record_date} 발표본까지` : ''} · FY${PROPOSAL} 월별 전망은 포함하지 않습니다.`;
  $('#bf-proposal-note').innerHTML = `<strong>FY${PROPOSAL} 정부 예산안 · 추정</strong><div class="bf-muted">대상 기간: ${PROPOSAL - 1}-10-01~${PROPOSAL}-09-30 · ${esc(future.year.source)}<br>아래 금액은 의회 최종 확정액·실제 집행액과 구분됩니다.<br>증감 비교: ${esc(future.baseline)}. 중간수정 전망은 혼합하지 않았습니다.</div>`;
  if (fytd) {
    $('#bf-ytd').innerHTML = `<strong>FY${fytd.fy} 진행 중 실적 · ${esc(fytd.through)}까지</strong><span class="bf-badge">부분 연도</span><div class="bf-muted">세출 ${bn(fytd.outlays)} · 세입 ${bn(fytd.receipts)} · 적자 ${bn(fytd.deficit)} · Treasury MTS 누계<br>정부안 연간 금액과 합치거나 비교 기준으로 쓰지 않습니다.</div>`;
  }
  $('#bf-footer').innerHTML = `FY${Math.min(...actualYears)}–${LATEST_ACTUAL - 1} 실적·FY${PROPOSAL} 정부안: OMB FY${PROPOSAL} Historical Tables 1.1·2.1·8.1·8.5·8.7 및 Public Budget Database. FY${LATEST_ACTUAL}·월별 실적: Treasury MTS.<br>FY${PROPOSAL}은 정부 제출본 추정 · 명목 달러 · 계약·수령기업 연결은 아직 없습니다.`;

  function donut(items, total, label) {
    let at = 0;
    const segments = items.map((r, i) => { const a = at; at += Math.max(0, r.value) / total * 100; return `${palette[i]} ${a}% ${at}%`; });
    return `<div class="bf-donut" style="background:conic-gradient(${segments.join(',')})" role="img" aria-label="${esc(label)} ${valueStatus()} ${items.map((r) => `${esc(r.name)} ${(r.value / total * 100).toFixed(1)}%`).join(', ')}"><div class="bf-hole"><span class="bf-muted">${esc(label)}</span><strong>${tr(total)}</strong><span class="bf-muted">FY${state.fy} ${valueStatus()}</span></div></div>`;
  }

  function outlays() {
    const c = data.types[state.fy];
    if (!c) {
      const fallback = Math.max(...Object.keys(data.types).map(Number).filter((y) => y !== PROPOSAL));
      $('#bf-content').innerHTML = `<h3>FY${state.fy} 세출</h3><div class="bf-message">총지출 실적은 확보했으나 의무·재량별 실적 분류는 미확인입니다. 추정치로 채우지 않습니다.</div><button type="button" id="bf-actual">FY${fallback} 분류·세부 내역 보기</button>`;
      $('#bf-actual').onclick = () => { state.fy = fallback; render(); };
      return;
    }
    const items = [{ id: 'mandatory', name: '의무지출(비재량)', value: c.mandatory }, { id: 'discretionary', name: '재량지출', value: c.discretionary }, { id: 'interest', name: '순이자', value: c.interest }];
    $('#bf-content').innerHTML = `<h3>세출은 어디에 쓰이나</h3><div class="bf-overview">${donut(items, c.total, '세출 구성')}<div class="bf-legend">${items.map((r, i) => `<button type="button" data-bucket="${r.id}" aria-pressed="${state.bucket === r.id}"><span class="bf-dot" style="background:${palette[i]}"></span><span>${r.name}</span><b>${bn(r.value)}<br><span class="bf-muted">${(r.value / c.total * 100).toFixed(1)}%</span></b></button>`).join('')}<div class="bf-muted">분류를 선택하면 아래 내역이 바뀝니다.<br>의무지출은 지급 기준이 법에 정해진 지출입니다.</div></div></div><div id="bf-breakdown"></div>`;
    $$('[data-bucket]').forEach((b) => { b.onclick = () => { state.bucket = b.dataset.bucket; state.expanded = false; outlays(); }; });
    breakdown();
  }

  function getRows() {
    if (isProposal()) return future[state.bucket];
    const c = data.types[state.fy];
    const p = data.types[state.fy - 1];
    if (state.bucket === 'discretionary') return data.discretionary[state.fy];
    if (state.bucket === 'interest') return [{ id: 'interest', name: '순이자', value: c.interest, prior: p?.interest ?? null, children: [] }];
    return [['socialSecurity', 'Social Security · 연금 등'], ['medicare', 'Medicare'], ['medicaid', 'Medicaid'], ['meansTested', '기타 소득 기준 급여'], ['otherMandatory', '기타 의무지출'], ['offsets', '공통 차감 수입']]
      .filter(([id]) => Number.isFinite(c[id]))
      .map(([id, name]) => ({ id, name, value: c[id], prior: Number.isFinite(p?.[id]) ? p[id] : null, children: [] }));
  }

  function renderChildren(children) {
    const metric = (r) => (state.sort === 'value' ? r.value : r.prior === null ? null : state.sort === 'delta' ? r.value - r.prior : rate(r.value, r.prior));
    const sorted = children.slice().sort((a, b) => (metric(b) ?? -Infinity) - (metric(a) ?? -Infinity));
    const max = Math.max(1, ...children.map((r) => Math.abs(r.value)));
    const renderChild = (ch) => {
      const delta = ch.prior === null ? '미확인' : `${signed(ch.value - ch.prior)}<br><span class="bf-muted">${pct(ch.value, ch.prior)}</span>`;
      const values = `<span class="bf-num">${bn(ch.value)}</span><span class="bf-num">${delta}</span>`;
      if (ch.children?.length) return `<details class="bf-subitem" ${ch.id === 'military-051' ? 'open' : ''}><summary><span class="bf-subname">${esc(ch.name)}</span>${values}</summary><div class="bf-subbar" role="img" aria-label="${esc(ch.name)} ${bn(ch.value)}"><span style="width:${ch.value > 0 ? ch.value / max * 100 : 0}%"></span></div><div class="bf-subbody">${renderChildren(ch.children)}</div></details>`;
      return `<div class="bf-subline"><span>${esc(ch.name)}${ch.code ? `<br><span class="bf-account">계정 ${esc(ch.code)}</span>` : ''}</span>${values}</div>`;
    };
    if (sorted.length > 8 && sorted.every((ch) => !ch.children?.length)) return sorted.slice(0, 8).map(renderChild).join('') + `<details class="bf-more-accounts"><summary>나머지 ${sorted.length - 8}개 계정 보기</summary>${sorted.slice(8).map(renderChild).join('')}</details>`;
    return sorted.map(renderChild).join('');
  }

  function breakdown() {
    const rows = getRows().map((r) => ({ ...r, children: r.children || [], delta: r.prior === null ? null : r.value - r.prior, rate: r.prior === null ? null : rate(r.value, r.prior) }));
    const metric = (r) => r[state.sort];
    rows.sort((a, b) => (metric(b) ?? -Infinity) - (metric(a) ?? -Infinity));
    const shown = state.expanded ? rows : rows.slice(0, 6);
    const max = Math.max(1, ...rows.map((r) => Math.abs(metric(r) ?? 0)));
    const title = state.bucket === 'discretionary' ? (state.sort === 'value' ? '재량지출 · 분야별 지출 규모' : state.sort === 'rate' ? '재량지출 · 증가율 비교' : '재량지출 · 증가액 비교') : state.bucket === 'mandatory' ? '의무지출 · 주요 사업별 내역' : '순이자 · 연간 부담';
    $('#bf-breakdown').innerHTML = `<div class="bf-rank-head"><h3>${title}</h3><span class="bf-muted">B$ = 십억 달러 = 10억 달러</span></div><div class="bf-toolbar">${[['value', '지출액순'], ['rate', '증가율순'], ['delta', '증가액순']].map(([k, n]) => `<button type="button" data-sort="${k}" aria-pressed="${state.sort === k}">${n}</button>`).join('')}</div><div class="bf-muted">${state.bucket === 'discretionary' ? '재량지출 분야별 비교 · 항목을 누르면 하위 분류 · 국방은 예산계정까지' : '해당 지출 성격에 속하는 금액만 표시'} · ${esc(comparison())}</div>`
      + shown.map((r) => {
        const v = metric(r);
        const width = v === null ? 0 : Math.abs(v) / max * (state.sort === 'value' ? 100 : 50);
        const position = v < 0 ? 50 - width : 50;
        const bar = state.sort === 'value'
          ? `<span class="bf-track"><span class="bf-fill" style="display:block;width:${r.value < 0 ? 0 : width}%"></span></span>`
          : `<span class="bf-track bf-zero"><span class="bf-fill" style="width:${width}%;left:${position}%;background:${v < 0 ? 'var(--bf-one)' : 'var(--bf-two)'}"></span></span>`;
        const display = v === null ? '비교 제외' : state.sort === 'rate' ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : state.sort === 'delta' ? signed(v) : bn(v);
        return `<details class="bf-item" data-item="${esc(r.id)}"><summary><span class="bf-name">${esc(r.name)}</span>${bar}<span class="bf-num">${display}<br><span class="bf-muted">${state.sort === 'value' ? (isProposal() ? '연간 순지출 추정' : '연간 순지출') : changeLabel()}</span></span></summary><div class="bf-detail"><div class="bf-split"><span class="bf-muted">${yearLabel(state.fy - 1)}<strong>${r.prior === null ? '미확인' : bn(r.prior)}</strong></span><span class="bf-muted">${yearLabel(state.fy)}<strong>${bn(r.value)}</strong></span><span class="bf-muted">증감<strong>${r.delta === null ? '미확인' : signed(r.delta)}</strong>${r.prior === null ? '' : pct(r.value, r.prior)}</span></div>${r.children.length ? `<h4>하위 지출 분류</h4><div class="bf-subhead"><span>항목</span><span class="bf-num">${yearLabel(state.fy)}</span><span class="bf-num">증감액·증감률</span></div>${renderChildren(r.children)}` : '<div class="bf-muted">현재 확보한 분류표의 최하위 항목입니다.</div>'}<div class="bf-message">${r.id === '7' ? '국방 하위 분류·계정도 해당 연도·지출 성격만 포함합니다. 계약·수령기업 연결은 추가 예정입니다.' : '사업·계약·수령기업 상세는 추가 연결 예정입니다.'}${r.value < 0 ? ' 음수는 차감 항목을 반영한 순액입니다.' : ''}</div></div></details>`;
      }).join('')
      + (rows.length > 6 ? `<button type="button" id="bf-expand" style="margin-top:12px" aria-expanded="${state.expanded}">${state.expanded ? '상위 항목만 보기' : `전체 ${rows.length}개 항목 보기`}</button>` : '');
    $$('[data-sort]').forEach((b) => { b.onclick = () => { state.sort = b.dataset.sort; breakdown(); }; });
    if ($('#bf-expand')) $('#bf-expand').onclick = () => { state.expanded = !state.expanded; breakdown(); };
  }

  function receipts() {
    const y = data.years[state.fy];
    const items = data.receipts[state.fy];
    if (!items) { $('#bf-content').innerHTML = `<h3>FY${state.fy} 세입</h3><div class="bf-message">세목별 금액이 아직 없습니다.</div>`; return; }
    $('#bf-content').innerHTML = `<h3>세입은 어디에서 들어오나</h3><div class="bf-overview">${donut(items, y.receipts, '세입 구성')}<div class="bf-legend">${items.map((r, i) => `<button type="button" data-tax="${i}" aria-pressed="false"><span class="bf-dot" style="background:${palette[i]}"></span><span>${esc(r.name)}</span><b>${bn(r.value)}<br><span class="bf-muted">${(r.value / y.receipts * 100).toFixed(1)}%</span></b></button>`).join('')}</div></div><div id="bf-tax-detail" class="bf-muted">세목을 선택하면 확인된 연도별 금액이 나옵니다.</div><div class="bf-message">국채 발행은 세입에 포함되지 않습니다.</div>`;
    $$('[data-tax]').forEach((b) => {
      b.onclick = () => {
        const r = items[Number(b.dataset.tax)];
        $$('[data-tax]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        $('#bf-tax-detail').innerHTML = `<h4>${esc(r.name)}</h4>${Object.keys(data.receipts).map((yr) => {
          const match = data.receipts[yr].find((x) => x.name === r.name);
          return match ? `<div class="bf-line"><span>FY${yr} ${Number(yr) === PROPOSAL ? '정부안·추정' : '실적'}</span><span>${bn(match.value)}</span></div>` : '';
        }).join('')}`;
      };
    });
  }

  function deficit() {
    const y = data.years[state.fy];
    const finance = data[`finance${state.fy}`];
    $('#bf-content').innerHTML = `<h3>세입으로 충당하지 못한 지출 ${isProposal() ? '· 정부안 추정' : ''}</h3><div class="bf-line"><span>세출</span><span class="bf-money">${tr(y.outlays)}</span></div><div class="bf-line"><span>− 세입</span><span class="bf-money">${tr(y.receipts)}</span></div><div class="bf-line"><strong>= 재정적자</strong><strong class="bf-money">${tr(y.deficit)}</strong></div><div class="bf-stack" role="img" aria-label="세출 중 세입 충당 비율 ${(y.receipts / y.outlays * 100).toFixed(1)}%, 적자 비율 ${(y.deficit / y.outlays * 100).toFixed(1)}%"><span style="width:${y.receipts / y.outlays * 100}%;background:var(--bf-one)"></span><span style="width:${y.deficit / y.outlays * 100}%;background:var(--bf-three)"></span></div><div class="bf-head"><span>세입 충당 ${(y.receipts / y.outlays * 100).toFixed(1)}%</span><span>적자 ${(y.deficit / y.outlays * 100).toFixed(1)}%</span></div><div class="bf-message">국채 총발행에는 만기상환을 위한 차환도 포함됩니다. 적자와 순차입의 차이는 현금잔액 변화·기타 자금조달로 연결합니다.</div>${finance ? `<details><summary>FY${state.fy} 자금조달 내역</summary><div class="bf-line"><span>정부 외부로부터 순차입</span><b>${bn(finance.borrowing)}</b></div><div class="bf-line"><span>재무부 연준계좌 잔액 증가</span><b>${bn(finance.cashIncrease)}</b></div><div class="bf-line"><span>기타 조달·조정 순액</span><b>${bn(finance.other)}</b></div></details>` : ''}`;
  }

  function history() {
    const area = $('#bf-history-chart');
    area.hidden = state.period !== 'annual';
    $('#bf-month-box').hidden = state.period !== 'monthly';
    $$('[data-period]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.period === state.period)));
    if (state.period === 'monthly') { monthlyView(); return; }
    const ys = Object.keys(data.years);
    const max = Math.max(...ys.map((y) => data.years[y][state.main]));
    area.innerHTML = `<div class="bf-muted">연간 금액 · 조 달러 · FY${ys[0]}–${LATEST_ACTUAL - 1} OMB 실적, FY${LATEST_ACTUAL} MTS 실적, FY${PROPOSAL} 정부안 추정</div>${ys.map((y) => {
      const v = data.years[y][state.main];
      const c = data.types[y];
      const segments = state.main === 'outlays' && c ? [c.mandatory, c.discretionary, c.interest] : state.main === 'receipts' && data.receipts[y] ? data.receipts[y].map((r) => r.value) : [v];
      return `<div class="bf-year"><span>${Number(y) === PROPOSAL ? `${y}안` : y}</span><div class="bf-stack" role="img" aria-label="FY${y} ${Number(y) === PROPOSAL ? '정부안·추정' : '실적'} ${tr(v)}" style="opacity:${Number(y) === PROPOSAL ? 0.65 : 1}">${segments.map((n, i) => `<span style="width:${Math.max(0, n) / max * 100}%;background:${state.main === 'outlays' && !c ? 'var(--bf-muted)' : palette[i]}"></span>`).join('')}</div><span class="bf-num">${(v / 1e12).toFixed(3)}</span></div>`;
    }).join('')}<div class="bf-muted">${state.main === 'outlays' ? `파랑: 의무 · 초록: 재량 · 보라: 순이자 · 회색: 분류 미확인 총액 · FY${PROPOSAL} 옅은색: 정부안·추정` : '서로 다른 발표본 간 수정 차이가 있을 수 있습니다.'}</div>`;
  }

  // Inline SVG instead of the prototype's D3 (no third-party script on the site).
  function monthlyView() {
    const r = monthly.find((x) => x.month === state.month) || monthly.at(-1);
    $('#bf-month').value = r.month;
    $('#bf-month-info').textContent = `${r.month} · 세출 ${bn(r.outlays)} · 세입 ${bn(r.receipts)} · ${r.deficit < 0 ? '흑자' : '적자'} ${bn(Math.abs(r.deficit))} · MTS 실적`;
    if (!$('#bf-history').open) return;
    const svg = $('#bf-month-chart');
    const width = Math.max(250, Math.round($('#bf-month-box').getBoundingClientRect().width));
    const height = 240;
    const m = { left: 48, right: 14, top: 26, bottom: 30 };
    const top = Math.max(...monthly.map((x) => Math.max(x.outlays, x.receipts))) / 1e9 * 1.05;
    const step = 10 ** Math.floor(Math.log10(top / 4));
    const tick = Math.ceil(top / 4 / step) * step;
    const yMax = tick * 4;
    const x = (i) => m.left + i / (monthly.length - 1) * (width - m.left - m.right);
    const y = (v) => height - m.bottom - v / yMax * (height - m.top - m.bottom);
    const line = (key) => monthly.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key] / 1e9).toFixed(1)}`).join('');
    const xticks = (width < 500 ? [0, 12, 24, 35] : [0, 6, 12, 18, 24, 30, 35]).filter((i) => i < monthly.length);
    const sel = monthly.indexOf(r);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.innerHTML = [
      `<text x="0" y="13">십억 USD</text><text x="75" y="13" style="fill:var(--bf-two)">세출</text><text x="120" y="13" style="fill:var(--bf-one)">세입</text>`,
      ...[0, 1, 2, 3, 4].map((k) => `<line class="bf-axis" x1="${m.left}" x2="${width - m.right}" y1="${y(k * tick)}" y2="${y(k * tick)}" stroke-width="${k ? 0.5 : 1}"/><text x="${m.left - 6}" y="${y(k * tick) + 4}" text-anchor="end">${(k * tick).toLocaleString('ko-KR')}</text>`),
      ...xticks.map((i) => `<text x="${x(i)}" y="${height - 10}" text-anchor="middle">${esc(monthly[i].month.slice(2))}</text>`),
      `<path d="${line('outlays')}" stroke="var(--bf-two)" stroke-width="2" fill="none"/><path d="${line('receipts')}" stroke="var(--bf-one)" stroke-width="2" fill="none"/>`,
      `<line x1="${x(sel)}" x2="${x(sel)}" y1="${m.top}" y2="${height - m.bottom}" stroke="var(--bf-muted)" stroke-dasharray="3 3"/>`,
    ].join('');
  }

  function render() {
    const y = data.years[state.fy];
    $('#bf-year').value = String(state.fy);
    $('#bf-proposal-note').hidden = !isProposal();
    $('#bf-ytd').hidden = !(isProposal() && fytd);
    for (const k of ['outlays', 'receipts', 'deficit']) $(`#bf-${k}`).textContent = (y[k] / 1e12).toFixed(3);
    $('#bf-source').textContent = `FY${state.fy} · ${y.source} · 분류 금액은 원표 단위로 반올림`;
    $$('[data-main]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.main === state.main)));
    if (state.main === 'outlays') outlays();
    else if (state.main === 'receipts') receipts();
    else deficit();
    history();
  }

  $$('[data-main]').forEach((b) => { b.onclick = () => { state.main = b.dataset.main; state.expanded = false; render(); }; });
  $('#bf-year').onchange = (e) => { state.fy = Number(e.target.value); render(); };
  $$('[data-period]').forEach((b) => { b.onclick = () => { state.period = b.dataset.period; history(); }; });
  $('#bf-month').onchange = (e) => { state.month = e.target.value; monthlyView(); };
  $('#bf-history').ontoggle = () => { if (state.period === 'monthly') monthlyView(); };
  const ro = new ResizeObserver(() => { if (state.period === 'monthly') monthlyView(); });
  ro.observe($('#bf-month-box'));
  observers.push(ro);
  render();
}
