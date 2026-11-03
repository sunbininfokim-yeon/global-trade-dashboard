// Shipping carbon-finance scenario (해운 › 탄소금융).
//
// The reference implementation is tools/shipping_carbon/{engine,funding}.py
// (PR #789). Every input here is a free-form what-if, so a precomputed grid
// like the blockade simulator's is impossible and the Worker cannot run
// Python -- the calculation is ported line for line below and held to the
// Python output by tests/shipping-carbon/engine.test.mjs. Change both sides
// together.
//
// Prices are the explicit synthetic fixture only. Redistributing real EEX
// auction prices on a public page is unconfirmed, so nothing here fetches them.
(() => {
  // ------------------------------------------------------------------ engine

  const NUMBER_RE = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/;
  const DAY_MS = 86400000;

  const SYNTHETIC_SNAPSHOT = {
    as_of: '2026-11-01',
    retrieved_at: null,
    status: 'synthetic',
    sources: {
      eex_eua_auction: {
        status: 'synthetic', unit: 'EUR/EUA', price_type: 'auction_clearing',
        source_url: 'https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download',
        latest_observations: [{ price: '80', observation_date: '2026-10-30' }]
      },
      ecb_eurkrw: {
        status: 'synthetic', unit: 'KRW/EUR', price_type: 'reference_fx',
        source_url: 'https://data.ecb.europa.eu/help/api/data-examples',
        latest_observations: [{ price: '1500', observation_date: '2026-10-30' }]
      }
    }
  };

  const blank = v => v === null || v === undefined || v === '';

  const number = (value, name, minimum = null) => {
    if (blank(value) || !NUMBER_RE.test(String(value))) throw new Error(`${name}: 숫자를 입력하세요`);
    const n = Number(value);
    if (!Number.isFinite(n) || Math.abs(n) > 1e18 || (minimum !== null && n < minimum)) {
      throw new Error(`${name}: 허용 범위 밖입니다`);
    }
    return n;
  };

  const parseDate = text => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text ?? ''));
    const t = m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
    if (!Number.isFinite(t)) throw new Error(`날짜 형식을 확인하세요: ${text}`);
    return t / DAY_MS;  // whole days since epoch, so differences are calendar days
  };
  const isoDate = day => new Date(day * DAY_MS).toISOString().slice(0, 10);

  const reference = (snapshot, key, priceType, unit, asOf) => {
    const source = snapshot.sources?.[key] ?? {};
    const records = source.latest_observations ?? [];
    const result = { value: null, status: 'missing', price_type: priceType, unit,
      source_url: source.source_url ?? null, retrieved_at: snapshot.retrieved_at ?? null };
    if (!['observed', 'synthetic'].includes(source.status) || source.price_type !== priceType || source.unit !== unit) return result;
    if (records.length !== 1) return { ...result, status: records.length ? 'ambiguous' : 'missing' };
    const r = records[0];
    const age = asOf - parseDate(r.observation_date);
    if (age < 0) return { ...result, status: 'future_observation_rejected' };
    return { ...result, value: number(r.price, key, 0), observation_date: r.observation_date,
      calendar_age_days: age,
      status: source.status === 'synthetic' ? 'synthetic' : (age > 7 ? 'stale' : 'observed'),
      stale_policy: 'calendar_age_gt_7_days' };
  };

  const defaults = snapshot => ({
    as_of: snapshot.as_of ?? '2026-11-01', scope_confirmed: true, preset_id: '',
    emissions_tco2e: '200000', emissions_basis: 'raw',
    route_weight: '0.5', phase_factor: '1', gases_complete: true,
    emissions_year: 2026, available_eua: '20000',
    scheduled_eua: '30000', delivery_date: '2027-09-01',
    surrender_date: '2027-09-30', price_mode: 'auction_reference',
    manual_price: null, price_shock: '-10', ship_hedge_delta: '20000',
    dealer_role: 'principal', dealer_lots: '50', future_price: '80',
    customer_bucket: '2027-09', future_bucket: '2027-09',
    future_delivery_date: '2027-09-01', cash_buffer: '100000',
    initial_margin: null, fuel_target: '89.3368', fuel_actual: '90',
    fuel_energy_mj: '1000000000', pool_quote: '200',
    hedge_basis_shock: '0', customer_price: '85',
    customer_delivery_date: '2027-09-30', customer_payment_date: '2027-10-15',
    replacement_price: null, trade_fees: '1000', funding_rate_pct: '5',
    price_path: 'recovery'
  });

  // Dated end-of-day funding for a principal supply trade. VM plus the final
  // physical invoice reproduce the futures acquisition cost; interest is
  // actual days / 365 on the previous negative closing cash only.
  const schedule = ({ as_of, delivery, customer_delivery, customer_payment, customer_q,
    future_q, future_price, customer_price, replacement_price, shock,
    recovery, cash_buffer, initial_margin, fees, annual_rate, principal }) => {
    const dates = [as_of, delivery, customer_delivery, customer_payment].map(parseDate);
    const [start, deliveryDay, customerDelivery, customerPayment] = dates;
    if (dates.some(x => x < start)) throw new Error('지급·인도·수금일은 분석 기준일 이후여야 합니다');
    if (!principal) {
      return { status: 'not_applicable', events: [], days: [], missing_inputs: [],
        peak_funding_gap_eur: 0, financing_cost_eur: 0, gross_spread_eur: null,
        net_contribution_eur: null, residual_inventory_eua: 0 };
    }
    if (customer_q === null) {
      return { status: 'held', events: [], days: [], missing_inputs: ['customer_supply_eua'],
        peak_funding_gap_eur: null, financing_cost_eur: null, gross_spread_eur: null,
        net_contribution_eur: null, residual_inventory_eua: null };
    }
    const terminalShock = recovery ? 0 : shock;
    if (future_price !== null && Math.min(future_price, future_price + shock) < 0) throw new Error('선물 가격 경로는 음수가 될 수 없습니다');
    if (replacement_price !== null && replacement_price < 0) throw new Error('보충 매입가격은 음수가 될 수 없습니다');
    const allocated = deliveryDay <= customerDelivery ? Math.min(customer_q, future_q) : 0;
    const replacementQ = customer_q - allocated;
    const residualInventory = future_q - allocated;
    const events = [], missing = [];
    const add = (day, kind, amount) => {
      if (amount === null) missing.push(kind);
      else events.push({ date: isoDate(day), kind, cash_eur: amount });
    };
    if (future_q) {
      // A short-dated scenario must not put simulated VM after physical delivery.
      if (deliveryDay < start + 2) throw new Error('선물 인도일은 2일의 가상 가격 경로 이후여야 합니다');
      add(start, 'initial_margin_post', initial_margin !== null ? -initial_margin : null);
      add(start + 1, 'variation_margin', future_q * shock);
      if (recovery) add(start + 2, 'variation_margin', -future_q * shock);
      add(deliveryDay, 'physical_future_payment', future_price !== null ? -future_q * (future_price + terminalShock) : null);
      add(deliveryDay, 'initial_margin_release', initial_margin);
    }
    add(start, 'fees', -fees);
    if (replacementQ) add(customerDelivery, 'replacement_purchase', replacement_price !== null ? -replacementQ * replacement_price : null);
    if (customer_q) add(customerPayment, 'customer_receipt', customer_price !== null ? customer_q * customer_price : null);
    // Same-day events are netted before measuring end-of-day funding.
    events.sort((a, b) => a.date.localeCompare(b.date) || a.kind.localeCompare(b.kind));
    const grouped = new Map();
    events.forEach(e => { if (!grouped.has(e.date)) grouped.set(e.date, []); grouped.get(e.date).push(e); });
    let balance = cash_buffer, peak = 0, interestTotal = 0, previousDay = start;
    const days = [];
    [...grouped.keys()].sort().forEach(text => {
      const items = grouped.get(text);
      const day = parseDate(text);
      const interest = Math.max(0, -balance) * annual_rate / 100 * (day - previousDay) / 365;
      const flow = items.reduce((sum, e) => sum + e.cash_eur, 0);
      balance += flow - interest;
      interestTotal += interest;
      const need = Math.max(0, -balance);
      peak = Math.max(peak, need);
      days.push({ date: text, flow_eur: flow, financing_eur: interest, closing_cash_eur: balance,
        funding_gap_eur: need, kinds: items.map(e => e.kind) });
      previousDay = day;
    });
    const complete = !missing.length;
    // Only matched, timely physical supply has a comparable spread here.
    const spread = future_q === customer_q && allocated === customer_q
      && customer_price !== null && future_price !== null
      ? customer_q * (customer_price - future_price) : null;
    return { status: complete ? 'scenario' : 'partial', missing_inputs: missing, events, days,
      known_components_peak_eur: peak,
      peak_funding_gap_eur: complete ? peak : null,
      financing_cost_eur: complete ? interestTotal : null,
      closing_cash_eur: complete ? balance : null,
      gross_spread_eur: spread,
      net_contribution_eur: spread !== null && complete ? spread - fees - interestTotal : null,
      replacement_eua: replacementQ, residual_inventory_eua: residualInventory,
      measurement: 'end_of_day_same_date_netting',
      interest_convention: 'negative_closing_cash_actual_calendar_days_365',
      horizon_end: isoDate(previousDay) };
  };

  const calculate = (p, snapshot) => {
    const asOf = parseDate(p.as_of);
    const auction = reference(snapshot, 'eex_eua_auction', 'auction_clearing', 'EUR/EUA', asOf);
    const fx = reference(snapshot, 'ecb_eurkrw', 'reference_fx', 'KRW/EUR', asOf);
    const n = key => number(p[key], key, 0);
    const signed = key => number(p[key], key);
    const optional = key => blank(p[key]) ? null : n(key);
    const emissions = n('emissions_tco2e'), route = n('route_weight'), phase = n('phase_factor');
    if (route > 1 || phase > 1) throw new Error('적용비중·단계비율은 0~1 사이입니다');
    if (!['raw', 'scope_adjusted'].includes(p.emissions_basis)) throw new Error('배출량 입력 기준을 확인하세요');
    if (!['principal', 'agency'].includes(p.dealer_role)) throw new Error('금융사 거래 역할을 확인하세요');
    if (!['auction_reference', 'manual'].includes(p.price_mode)) throw new Error('가격 종류를 확인하세요');
    const known = p.scope_confirmed === true && p.gases_complete === true;
    const obligation = known ? emissions * (p.emissions_basis === 'raw' ? route : 1) * phase : null;
    const due = parseDate(p.surrender_date);
    const timely = parseDate(p.delivery_date) <= due;
    const scheduled = timely ? n('scheduled_eua') : 0;
    const gap = known ? Math.max(0, obligation - n('available_eua') - scheduled) : null;
    const price = p.price_mode === 'auction_reference' ? auction.value : optional('manual_price');
    const shock = signed('price_shock');
    const basis = number(p.hedge_basis_shock ?? '0', 'hedge_basis_shock');
    const futureShock = shock + basis;
    if (price !== null && price + shock < 0) throw new Error('가격 충격 후 EUA 가격은 음수가 될 수 없습니다');
    const baseline = optional('future_price');
    if (baseline !== null && baseline + futureShock < 0) throw new Error('가격 충격 후 선물 가정가격은 음수가 될 수 없습니다');
    const budget = gap !== null && price !== null ? gap * price : null;
    const hedge = n('ship_hedge_delta');
    const ship = { status: known ? 'scenario' : 'held', obligation_eua: obligation,
      scheduled_eua: scheduled, late_delivery_eua: timely ? 0 : n('scheduled_eua'),
      procurement_gap_eua: gap, budget_eur: budget,
      budget_krw: budget !== null && fx.value !== null ? budget * fx.value : null,
      gross_cost_change_eur: gap !== null ? gap * shock : null,
      hedge_gain_eur: hedge * shock,
      net_cost_change_eur: gap !== null ? (gap - hedge) * shock : null,
      overhedged_eua: gap !== null ? Math.max(0, hedge - gap) : null };
    const principal = p.dealer_role === 'principal';
    const lots = n('dealer_lots');
    if (!Number.isInteger(lots)) throw new Error('선물 계약 수는 정수 lot으로 입력하세요');
    const futureQ = principal ? lots * 1000 : 0;
    const customerQ = principal ? gap : 0;
    const buckets = {};
    if (customerQ !== null) buckets[p.customer_bucket] = -customerQ;
    buckets[p.future_bucket] = (buckets[p.future_bucket] ?? 0) + futureQ;
    const pnl = futureQ * futureShock;
    const customerPnl = customerQ !== null ? -customerQ * shock : null;
    const cash = n('cash_buffer');
    const margin = principal ? optional('initial_margin') : 0;
    const pricePath = p.price_path ?? 'recovery';
    if (!['recovery', 'persistent'].includes(pricePath)) throw new Error('가격 경로를 확인하세요');
    // VM is the cash realization of futures P&L, not an extra P&L.
    let vmCash = 0, peak = 0, previous = 0;
    const path = [0, futureShock, pricePath === 'recovery' ? 0 : futureShock].map((level, day) => {
      const vm = futureQ * (level - previous);
      previous = level;
      vmCash += vm;
      const gapCash = Math.max(0, -vmCash - cash);
      peak = Math.max(peak, gapCash);
      return { day, price_change: level, vm_flow_eur: vm, cumulative_vm_eur: vmCash, vm_only_funding_gap_eur: gapCash };
    });
    const timelyFuture = parseDate(p.future_delivery_date) <= due;
    const dealer = { role: p.dealer_role, customer_supply_eua: customerQ,
      hedge_eua: futureQ, delta_by_bucket: buckets,
      net_delta_eua: customerQ !== null ? futureQ - customerQ : null,
      futures_pnl_eur: pnl, customer_pnl_eur: customerPnl,
      net_pnl_eur: customerPnl !== null ? pnl + customerPnl : null,
      vm_outflow_at_shock_eur: Math.max(0, -pnl), cash_path: path,
      vm_only_peak_funding_gap_eur: peak,
      vm_and_im_peak_funding_gap_eur: margin !== null ? Math.max(0, Math.max(0, -pnl) + margin - cash) : null,
      initial_margin_eur: margin, future_price_input: baseline,
      future_price_status: baseline !== null ? 'synthetic' : 'missing',
      delivery_gap_eua: customerQ !== null ? Math.max(0, customerQ - (timelyFuture ? futureQ : 0)) : null,
      curve_risk: Object.values(buckets).filter(v => v !== 0).length > 1 };
    dealer.funding = schedule({
      as_of: p.as_of, delivery: p.future_delivery_date,
      customer_delivery: p.customer_delivery_date ?? p.surrender_date,
      customer_payment: p.customer_payment_date ?? p.surrender_date,
      customer_q: customerQ, future_q: futureQ, future_price: baseline,
      customer_price: optional('customer_price'), replacement_price: optional('replacement_price'),
      shock: futureShock, recovery: pricePath === 'recovery', cash_buffer: cash,
      initial_margin: margin, fees: number(p.trade_fees ?? '0', 'trade_fees', 0),
      annual_rate: number(p.funding_rate_pct ?? '0', 'funding_rate_pct', 0), principal });
    dealer.hedge_shock_eur = futureShock;
    dealer.basis_shock_eur = basis;
    dealer.valuation_method = 'customer_and_hedge_shock_delta_approximation';
    dealer.hedge_comparison = customerQ === null ? [] : [['미헤지', 0], ['50% 목표', 0.5], ['100% 목표', 1]].map(([label, ratio]) => {
      // Float division can land a hair above an integer; Decimal in the reference cannot.
      const targetLots = Math.ceil(customerQ * ratio / 1000 - 1e-9);
      const qh = targetLots * 1000;
      return { label, lots: targetLots, hedge_eua: qh, residual_delta_eua: qh - customerQ,
        net_shock_pnl_eur: qh * futureShock - customerQ * shock,
        vm_outflow_eur: Math.max(0, -qh * futureShock) };
    });
    const customerPrice = optional('customer_price');
    ship.customer_contract_payment_eur = gap !== null && customerPrice !== null ? gap * customerPrice : null;
    const balance = (n('fuel_target') - n('fuel_actual')) * n('fuel_energy_mj') / 1e6;
    const pool = optional('pool_quote');
    const fuel = { status: 'illustrative', balance_tco2e: balance,
      pool_cost_eur: pool !== null ? Math.max(0, -balance) * pool : null,
      penalty_eur: null, penalty_status: 'held_pending_annex_verification' };
    return { schema: 'shipping_carbon_scenario_v2', as_of: isoDate(asOf), scenario_data: true,
      references: { auction, fx }, price_mode: p.price_mode, budget_price_eur: price,
      shipowner: ship, dealer, fueleu: fuel };
  };

  const engine = { calculate, defaults, schedule, SYNTHETIC_SNAPSHOT };
  if (typeof module !== 'undefined' && module.exports) module.exports = engine;
  if (typeof window === 'undefined') return;

  // ---------------------------------------------------------------------- UI

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, unit = '') => {
    if (v === null || v === undefined) return '미확인';
    // Ten-digit won amounts wrap inside a KPI card; 억 is how the rest of the site reads them.
    if (unit === '원' && Math.abs(v) >= 1e8) return `${(v / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억 원`;
    return `${Number(v).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}${unit ? ' ' + unit : ''}`;
  };
  const kpi = (label, value, unit, note = '', featured = false) => `
    <div class="shipping-kpi${featured ? ' featured' : ''}">
      <span class="shipping-kpi-label">${esc(label)}</span>
      <strong>${esc(fmt(value, unit))}</strong>
      <small>${esc(note)}</small>
    </div>`;
  const panel = (kicker, title, body, id = '') => `
    <section class="shipping-panel"${id ? ` id="${id}"` : ''}>
      <div class="shipping-panel-heading"><div>
        <p class="shipping-panel-kicker">${esc(kicker)}</p><h2>${esc(title)}</h2>
      </div></div>${body}
    </section>`;
  const table = (heads, rows) => `
    <div class="shipping-table-wrap"><table class="shipping-table compact-table">
      <thead><tr>${heads.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div>`;
  const note = text => `<p class="sc-note">${text}</p>`;

  const EVENT_LABELS = {
    initial_margin_post: 'IM 납입', initial_margin_release: 'IM 반환',
    variation_margin: 'VM 정산', physical_future_payment: '선물 실물 대금',
    replacement_purchase: '보충 실물 매입', customer_receipt: '고객 수금', fees: '수수료'
  };

  const field = (label, name, attrs = '', hint = '') =>
    `<label class="sc-field"><span>${label}</span><input name="${name}" ${attrs}>${hint ? `<small>${hint}</small>` : ''}</label>`;
  const select = (label, name, options) =>
    `<label class="sc-field"><span>${label}</span><select name="${name}">${options.map(([v, t]) => `<option value="${v}">${t}</option>`).join('')}</select></label>`;
  const pair = (a, b) => `<div class="sc-pair">${a}${b}</div>`;

  const FORM = `
    <form class="sc-form" novalidate>
      <p class="sc-form-lede">2026년 배출분 · 적용 범위·가스 입력 완료를 가정합니다. 적용비중과 단계비율은 자동 법률 판정이 아닙니다.</p>
      <fieldset><legend>해운사 공통 사례</legend>
        ${field('배출량 (tCO₂e)', 'emissions_tco2e', 'type="number" min="0" step="any"')}
        ${select('배출량 기준', 'emissions_basis', [['raw', '항로비중 적용 전'], ['scope_adjusted', '항로비중 이미 적용']])}
        ${pair(field('항로비중', 'route_weight', 'type="number" min="0" max="1" step="0.1"'), field('단계비율', 'phase_factor', 'type="number" min="0" max="1" step="0.1"'))}
        ${field('현재 배정 가능한 EUA', 'available_eua', 'type="number" min="0"')}
        ${field('계약 인도예정 EUA', 'scheduled_eua', 'type="number" min="0"')}
        ${pair(field('계약 인도일', 'delivery_date', 'type="date"'), field('제출기한 가정', 'surrender_date', 'type="date"'))}
        ${select('예산 가격', 'price_mode', [['auction_reference', 'EEX 경매 기준가격 (가상 샘플)'], ['manual', '직접 입력한 가정가격']])}
        ${field('가정가격 (EUR/EUA, 선택)', 'manual_price', 'type="number" min="0" step="any" placeholder="미입력"')}
        ${field('공통 가격충격 (EUR/EUA)', 'price_shock', 'type="number" step="1"')}
        ${field('해운사 현금결제 헤지 (EUA 상당)', 'ship_hedge_delta', 'type="number" min="0"')}
      </fieldset>
      <details open><summary>금융사 거래 가정</summary>
        ${select('거래 역할', 'dealer_role', [['principal', '자기계정 공급·헤지'], ['agency', '중개 — 자기계정 제외']])}
        ${field('선물 매수 (lot, 1 lot=1,000 EUA)', 'dealer_lots', 'type="number" min="0" step="1"')}
        ${field('선물 기준가격 가정 (EUR/EUA)', 'future_price', 'type="number" min="0" step="any"', '합성 입력값입니다. 경매가로 대체하지 않습니다.')}
        ${pair(field('고객 인도 월물', 'customer_bucket', 'type="month"'), field('선물 월물 가정', 'future_bucket', 'type="month"'))}
        ${field('선물 실물 인도일 가정', 'future_delivery_date', 'type="date"')}
        ${field('선물 추가 가격충격 (EUR/EUA)', 'hedge_basis_shock', 'type="number" step="any"', '선물 충격 = 공통 충격 + 이 값. 월물 간 움직임 차이를 가정합니다.')}
        ${field('현금 여유 (EUR)', 'cash_buffer', 'type="number" min="0"')}
        ${field('초기 증거금 (EUR, 선택)', 'initial_margin', 'type="number" min="0" placeholder="미입력 — 전체 자금소요 미확정"')}
      </details>
      <details><summary>계약별 자금 일정</summary>
        ${field('고객 고정 공급가격 (EUR/EUA)', 'customer_price', 'type="number" min="0" step="any"')}
        ${pair(field('고객 실물 인도일', 'customer_delivery_date', 'type="date"'), field('고객 수금일', 'customer_payment_date', 'type="date"'))}
        ${field('부족 실물 보충가격 (EUR/EUA, 선택)', 'replacement_price', 'type="number" min="0" step="any" placeholder="보충 필요 시 입력"')}
        ${field('거래 수수료 합계 (EUR)', 'trade_fees', 'type="number" min="0" step="any"')}
        ${field('추가 차입 금리 (연 %, 가정)', 'funding_rate_pct', 'type="number" min="0" step="any"')}
        ${select('선물 충격 이후 경로', 'price_path', [['recovery', '다음 날 기준가격 복귀'], ['persistent', '인도일까지 충격 유지']])}
        <small class="sc-hint">가격 경로의 날짜는 분석일+1일 충격, +2일 복귀의 가정입니다. 거래소 캘린더가 아닙니다.</small>
      </details>
      <div class="sc-actions">
        <button type="button" class="sc-reset">초기 사례로</button>
        <button type="button" class="sc-export" disabled>결과 JSON 저장</button>
      </div>
    </form>`;

  const fundingChart = f => {
    if (f.status !== 'scenario' || !f.days.length) return note('필수 자금 입력을 완료하면 일말 자금 경로를 표시합니다.');
    const max = Math.max(1, ...f.days.map(x => x.funding_gap_eur));
    const start = Date.parse(f.days[0].date), span = Math.max(1, Date.parse(f.days.at(-1).date) - start);
    const coords = f.days.map(x => ({ x: 50 + 620 * (Date.parse(x.date) - start) / span,
      y: 160 - 120 * x.funding_gap_eur / max, label: `${x.date}: ${fmt(x.funding_gap_eur, 'EUR')}` }));
    const points = coords.flatMap((pt, i) => i ? [`${pt.x},${coords[i - 1].y}`, `${pt.x},${pt.y}`] : [`${pt.x},${pt.y}`]);
    return `<svg class="sc-chart" viewBox="0 0 730 210" role="img" aria-label="날짜별 일말 추가 조달 필요액, 이벤트일 계단 표시">
      <line x1="50" y1="160" x2="670" y2="160" stroke="rgba(148,163,184,0.35)"/>
      <polyline fill="none" stroke="#38bdf8" stroke-width="2.5" points="${points.join(' ')}"/>
      ${coords.map(pt => `<circle cx="${pt.x}" cy="${pt.y}" r="4" fill="#38bdf8"><title>${esc(pt.label)}</title></circle>`).join('')}
      <text x="50" y="25" fill="#94a3b8" font-size="12">최대 ${esc(fmt(max, 'EUR'))}</text>
      <text x="50" y="190" fill="#64748b" font-size="11">${esc(f.days[0].date)}</text>
      <text x="670" y="190" text-anchor="end" fill="#64748b" font-size="11">${esc(f.days.at(-1).date)}</text>
    </svg>`;
  };

  const shipView = (r, p) => {
    const s = r.shipowner;
    return `
      <div class="shipping-kpi-grid">
        ${kpi('제출 필요량', s.obligation_eua, 'EUA', '가상 배출량에 입력 비율 적용')}
        ${kpi('추가 조달 필요량', s.procurement_gap_eua, 'EUA', '현금결제 헤지는 실물 확보량에 미포함', true)}
        ${kpi('추가 조달 참고 예산', s.budget_eur, 'EUR', r.price_mode === 'auction_reference' ? '경매 기준가격 (가상 샘플)' : '사용자 가정가격')}
        ${kpi('원화 환산 참고 예산', s.budget_krw, '원', '참고환율 (가상 샘플)로 단순 환산')}
      </div>
      ${panel('PRICE SHOCK', '공통 가격충격의 영향', `
        ${table(['구분', '금액'], [
          ['추가 조달비용 변화', fmt(s.gross_cost_change_eur, 'EUR')],
          ['기존 현금결제 헤지 평가손익', fmt(s.hedge_gain_eur, 'EUR')],
          ['헤지 반영 후 경제적 비용 변화', fmt(s.net_cost_change_eur, 'EUR')]
        ])}
        ${note(`계약 인도예정 중 기한 내 ${esc(fmt(s.scheduled_eua, 'EUA'))}, 기한 후 ${esc(fmt(s.late_delivery_eua, 'EUA'))}. 초과 가격헤지 ${esc(fmt(s.overhedged_eua, 'EUA'))}. 헤지 이익의 실제 수취일과 배출권 매입 지급일은 다를 수 있습니다.`)}`)}
      ${panel('SUPPLY CONTRACT', '금융사 공급계약 대금 가정', `
        ${note(`${esc(fmt(s.customer_contract_payment_eur, 'EUR'))} · 추가 조달량 × 고객 고정 공급가격입니다. 경매 참고 예산과 구분합니다.`)}
        ${note(`고객 인도일 ${esc(p.customer_delivery_date)}, 지급일 ${esc(p.customer_payment_date)}. 이 거래 외 기존 계약의 지급금은 포함하지 않습니다.`)}`)}`;
  };

  const dealerView = r => {
    const d = r.dealer, f = d.funding;
    const principal = d.role === 'principal';
    return `
      <div class="shipping-kpi-grid sc-kpi-3">
        ${kpi('고객 공급 수량', d.customer_supply_eua, 'EUA', '해운사 추가 조달량과 연결')}
        ${kpi('합산 순가격노출', d.net_delta_eua, 'EUA', '만기별 위험은 아래 표에서 확인')}
        ${kpi('가격충격 시 순평가손익', d.net_pnl_eur, 'EUR', '고객·선물 추가충격 반영 · 델타 근사')}
        ${kpi('충격 시 VM 현금 유출', d.vm_outflow_at_shock_eur, 'EUR', '평가이익과 현금 유입 시점은 별개', true)}
        ${kpi('VM 경로상 추가 자금', d.vm_only_peak_funding_gap_eur, 'EUR', '입력한 현금 여유 차감 · IM 제외')}
        ${kpi('IM 포함 추가 자금', d.vm_and_im_peak_funding_gap_eur, 'EUR', 'IM 미입력 시 전체 자금소요 미확정')}
      </div>
      ${principal ? '' : note('중개 거래 — 자기계정 포지션은 계산에서 제외합니다.')}
      ${panel('FUNDING SCHEDULE', '계약 일정과 추가 자금', `
        <div class="shipping-kpi-grid sc-kpi-2">
          ${kpi('계약 일정상 최대 추가자금', f.peak_funding_gap_eur, 'EUR', '일말 잔액 · IM·실물 지급·고객수금·수수료·차입비용', true)}
          ${kpi('비용 반영 기여이익 가정', f.net_contribution_eur, 'EUR', '일치 수량·기한 내 인도 시 계산 · 신용/자본비용·세금 제외')}
        </div>
        ${note(`계산 상태: ${esc(f.status)}${f.missing_inputs.length ? ' · 미입력: ' + esc(f.missing_inputs.map(k => EVENT_LABELS[k] ?? k).join(', ')) : ''}`)}
        ${fundingChart(f)}
        ${table(['날짜 / 내역', '유입·유출 (EUR)', '차입비용 (EUR)', '일말 현금 (EUR)', '추가자금 (EUR)'],
          f.days.map(x => [`${x.date} / ${x.kinds.map(k => EVENT_LABELS[k] ?? k).join(', ')}`, fmt(x.flow_eur), fmt(x.financing_eur), fmt(x.closing_cash_eur), fmt(x.funding_gap_eur)]))}
        ${note(f.status === 'partial'
          ? '표는 확인된 항목만 합산한 부분 경로입니다. 전체 최대자금·기여이익은 미확인으로 유지합니다.'
          : '현금 여유를 먼저 사용하고 음수 일말 잔액을 추가 차입으로 가정합니다. 실제 달력일/365 단리로 다음 이벤트일까지 이자를 계산합니다.')}
        ${note(`차입비용 합계 ${esc(fmt(f.financing_cost_eur, 'EUR'))}, 원가 대비 공급 차액 ${esc(fmt(f.gross_spread_eur, 'EUR'))}. 고객 인도일의 보충 실물 ${esc(fmt(f.replacement_eua, 'EUA'))}, 고객에게 배정되지 않는 선물 인수량 ${esc(fmt(f.residual_inventory_eua, 'EUA'))} — 잔여 재고의 평가이익은 확정 수익에 더하지 않습니다.`)}`, 'sc-funding')}
      <div class="shipping-grid sc-two">
        ${panel('HEDGE RATIO', '헤지 비율별 가격위험과 VM', `
          ${note(`선물 충격 ${esc(fmt(d.hedge_shock_eur, 'EUR/EUA'))}, 그중 추가 충격 ${esc(fmt(d.basis_shock_eur, 'EUR/EUA'))}. 계약 수는 1,000 EUA 단위로 올림합니다.`)}
          ${table(['헤지 목표', 'lot', '잔여 델타', '순손익 (EUR)', 'VM 유출 (EUR)'],
            d.hedge_comparison.map(x => [x.label, fmt(x.lots), fmt(x.residual_delta_eua), fmt(x.net_shock_pnl_eur), fmt(x.vm_outflow_eur)]))}
          ${note('추가 충격이 있으면 합산 델타가 0이어도 손익이 남습니다. 최적전략 판정이 아닙니다.')}`)}
        ${panel('MATURITY', '만기와 실물 인도', `
          ${note(`선물 기준가격 ${esc(fmt(d.future_price_input, 'EUR/EUA'))} · ${d.future_price_status === 'synthetic' ? '사용자 가정값' : '가격 미입력'}. 경매가와 독립 입력입니다.`)}
          ${table(['월물', '순가격노출 (EUA)'], Object.entries(d.delta_by_bucket).map(([k, v]) => [k, fmt(v)]))}
          ${note(`${d.curve_risk ? '월물이 달라 곡선 위험이 남습니다.' : '동일 월물도 실제 베이시스·인도 조건은 추가 확인이 필요합니다.'} 선물 인도계획 반영 후 기한 내 부족량: ${esc(fmt(d.delivery_gap_eua, 'EUA'))}.`)}`)}
      </div>
      ${panel('VARIATION MARGIN', '가격 경로별 VM 현금흐름', `
        ${table(['단계', '가격변화', 'VM 유입/유출', '추가 자금'], d.cash_path.map(x => [String(x.day), fmt(x.price_change, 'EUR'), fmt(x.vm_flow_eur, 'EUR'), fmt(x.vm_only_funding_gap_eur, 'EUR')]))}
        ${note('VM은 선물 손익의 현금 정산이며 별도 손익으로 더하지 않습니다. 이 표는 VM만 대상으로 하며 인도대금·수수료·고객수금은 위 자금 일정에 있습니다.')}`)}`;
  };

  const fuelView = f => panel('FUELEU', 'FuelEU 연간 잔액 예제', `
    ${table(['항목', '결과'], [
      ['가상 준수 잔액', fmt(f.balance_tco2e, 'tCO₂e')],
      ['풀링 견적 가정으로 계산한 비용', fmt(f.pool_cost_eur, 'EUR')],
      ['법정 미준수 부담금', '부속서 대조 대기']
    ])}
    ${note('목표 89.3368, 실제 90 gCO₂e/MJ, 대상 에너지 10억 MJ, 풀링 단가 200 EUR/t 잔액의 가정입니다. EUA 수량과 별도이며 거래 적격성·풀 구성 검증은 하지 않습니다.')}`);

  const sourcesView = r => {
    const a = r.references.auction, fx = r.references.fx;
    return `<div class="sc-sources" role="note">
      <strong>가상 샘플 가격</strong>
      <span>EUA 경매 기준가격 ${esc(fmt(a.value, 'EUR/EUA'))} · 관측일 ${esc(a.observation_date ?? '미확인')}</span>
      <span>EUR/KRW 참고환율 ${esc(fmt(fx.value, 'KRW/EUR'))} · 관측일 ${esc(fx.observation_date ?? '미확인')}</span>
      <span>분석 기준일 ${esc(r.as_of)} · 실제 시세가 아닙니다</span>
    </div>`;
  };

  const render = host => {
    const initial = defaults(SYNTHETIC_SNAPSHOT);
    let view = 'ship', exportData = null;
    host.innerHTML = `
      <div class="shipping-grid sc-layout">
        <aside class="shipping-panel sc-inputs">${FORM}</aside>
        <div class="sc-results">
          <div class="sc-error" role="alert" hidden></div>
          <div class="sc-sources-slot"></div>
          <nav class="sc-switch" aria-label="분석 관점">
            <button type="button" data-sc-view="ship" aria-pressed="true">해운사 관점</button>
            <button type="button" data-sc-view="dealer" aria-pressed="false">금융사 관점</button>
          </nav>
          <div class="sc-view"></div>
          <div class="sc-fuel"></div>
          ${panel('SCOPE', '계산의 범위와 근거', `
            ${note('배출량·보유량·계약·헤지 포지션은 가상 입력이고 가격은 명시된 가상 샘플입니다. 배출권 조달 예산은 실제 체결 견적과 다릅니다.')}
            ${note('금융사 평가손익은 고객과 선물의 가격충격을 적용한 델타 근사입니다. 자금 일정은 단일 계약의 일말 잔액이며 장중 자금 피크·세금·신용/자본비용·복수 계약은 반영하지 않습니다.')}
            ${note('<a href="https://climate.ec.europa.eu/areas-action/transport-decarbonisation/reducing-emissions-shipping-sector/faq-maritime-transport-eu-emissions-trading-system-ets_en" target="_blank" rel="noopener">EU ETS 공식 설명 ↗</a> · <a href="https://transport.ec.europa.eu/transport-modes/maritime/decarbonising-maritime-transport-fueleu-maritime_en" target="_blank" rel="noopener">FuelEU 공식 설명 ↗</a>')}`)}
        </div>
      </div>`;
    const form = host.querySelector('.sc-form');
    const errorBox = host.querySelector('.sc-error');
    const exportButton = host.querySelector('.sc-export');
    const populate = p => { for (const el of form.elements) if (el.name && Object.hasOwn(p, el.name)) el.value = p[el.name] ?? ''; };
    const run = () => {
      const p = { ...initial };
      for (const el of form.elements) if (el.name) p[el.name] = el.value;
      exportData = null;
      exportButton.disabled = true;
      try {
        const r = calculate(p, SYNTHETIC_SNAPSHOT);
        errorBox.hidden = true;
        host.querySelector('.sc-sources-slot').innerHTML = sourcesView(r);
        host.querySelector('.sc-view').innerHTML = view === 'ship' ? shipView(r, p) : dealerView(r);
        host.querySelector('.sc-fuel').innerHTML = fuelView(r.fueleu);
        exportData = { schema: 'shipping_carbon_export_v1', generated_at: new Date().toISOString(), inputs: p, result: r };
        exportButton.disabled = false;
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
        host.querySelector('.sc-view').innerHTML = '';
        host.querySelector('.sc-fuel').innerHTML = '';
      }
    };
    host.querySelectorAll('[data-sc-view]').forEach(button => button.addEventListener('click', () => {
      view = button.dataset.scView;
      host.querySelectorAll('[data-sc-view]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      run();
    }));
    form.addEventListener('input', run);
    form.addEventListener('change', run);
    host.querySelector('.sc-reset').addEventListener('click', () => { populate(initial); run(); });
    exportButton.addEventListener('click', () => {
      if (!exportData) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'shipping-carbon-scenario.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    populate(initial);
    run();
  };

  window.ShippingCarbon = { render, engine };
})();
