const finite = n => typeof n === 'number' && Number.isFinite(n);
const near = (a, b, tolerance = 1) => finite(a) && finite(b) && Math.abs(a - b) <= tolerance;
const monthNumber = m => /^\d{4}-(0[1-9]|1[0-2])$/.test(m) ? Number(m.slice(0, 4)) * 12 + Number(m.slice(5)) : NaN;
const dated = d => typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d) && !Number.isNaN(Date.parse(d));

export function usableLive(live) {
  if (live?.schema_version !== 1 || live.unit !== 'USD' || !dated(live.mts_record_date)
      || !Array.isArray(live.months) || live.months.length !== 36) return null;
  for (const [i, row] of live.months.entries()) {
    if (!Number.isFinite(monthNumber(row.month)) || !near(row.outlays - row.receipts, row.deficit)
        || ![row.receipts, row.outlays, row.deficit].every(finite)
        || !dated(row.vintage) || row.vintage > live.mts_record_date || row.month > row.vintage.slice(0, 7)
        || (i && monthNumber(row.month) - monthNumber(live.months[i - 1].month) !== 1)) return null;
  }
  if (live.months.at(-1).month !== live.mts_record_date.slice(0, 7)) return null;
  const y = live.fytd;
  if (y) {
    const year = Number(live.mts_record_date.slice(0, 4)) + (Number(live.mts_record_date.slice(5, 7)) >= 10 ? 1 : 0);
    if (y.fy !== year || y.through !== live.months.at(-1).month
        || y.complete !== live.mts_record_date.endsWith('09-30')
        || !near(y.outlays - y.receipts, y.deficit)) return null;
  }
  return live;
}

function rollup(row) {
  if (![row.value, row.prior].every(finite) || !Array.isArray(row.children)) return false;
  return !row.children.length || (near(row.children.reduce((n, c) => n + c.value, 0), row.value)
    && near(row.children.reduce((n, c) => n + c.prior, 0), row.prior) && row.children.every(rollup));
}

export function usableBundle(bundle) {
  try {
    const a = bundle?.annual, p = a?.proposal, b = a?.budget;
    if (bundle?.schema_version !== 1 || !usableLive(bundle.live) || a?.schema_version !== 2
        || a.normalized_unit !== 'USD' || !/^\d{4}\/\d{2}$/.test(a.publication)
        || !/^[a-f0-9]{64}$/.test(bundle.dataset_id) || !p?.year?.estimate
        || p.year.fy !== a.proposal_fy || p.year.status !== 'proposal_estimate'
        || !near(p.year.outlays - p.year.receipts, p.year.deficit)
        || a.enacted_budget?.status !== 'not_collected' || a.enacted_budget.amount !== null) return null;
    if (Object.keys(b.years).length !== 5) return null;
    const years = Object.keys(b.years).map(Number).sort((x, y) => x - y);
    if (years.some((y, i) => i && y !== years[i - 1] + 1)) return null;
    for (const [key, y] of Object.entries(b.years)) {
      if (y.fy !== Number(key) || y.status !== 'actual' || y.estimate === true || Number(key) >= a.proposal_fy
          || !near(y.outlays - y.receipts, y.deficit)
          || !Array.isArray(b.receipts[key]) || b.receipts[key].some(r => !finite(r.value))
          || !near(b.receipts[key].reduce((n, r) => n + r.value, 0), y.receipts, 1e6)) return null;
    }
    for (const [kind, total] of [['discretionary', p.types.discretionary], ['mandatory', p.types.mandatory], ['interest', p.types.interest]]) {
      if (!Array.isArray(p[kind]) || !p[kind].every(rollup)
          || !near(p[kind].reduce((n, r) => n + r.value, 0), total)) return null;
    }
    if (!near(p.types.discretionary + p.types.mandatory + p.types.interest, p.year.outlays)
        || !near(p.receipts.reduce((n, r) => n + r.value, 0), p.year.receipts)) return null;
    for (const [year, details] of Object.entries(a.agency_details || {})) {
      const expected = Number(year)===p.year.fy ? 'proposal_estimate' : 'actual';
      if (details.status!==expected || details.metric!=='outlays' || details.baseline_fy!==Number(year)-1
          || details.baseline_status!==(expected==='actual'?'actual':'estimate')) return null;
      for (const kind of ['discretionary','mandatory','interest']) {
        if (!Array.isArray(details[kind]) || !details[kind].every(rollup)
            || !near(details[kind].reduce((n,r)=>n+r.value,0),details.totals[kind])) return null;
      }
      const reference = Number(year)===p.year.fy ? p.year.outlays : b.years[year]?.outlays;
      if (!near(Object.values(details.totals).reduce((n,v)=>n+v,0),reference,1e6)) return null;
    }
    return bundle;
  } catch { return null; }
}

export function collectionState(bundle, status, now = new Date()) {
  const checked = Date.parse(status?.last_checked_at);
  const good = Date.parse(status?.last_success_at);
  if (status?.state === 'failed') return { state: 'failed', text: '수집·검증 실패: 마지막 정상 자료를 표시합니다.', checked, good };
  if (!bundle || status?.state !== 'ok' || status.dataset_id !== bundle.dataset_id || !Number.isFinite(checked)
      || checked > now.getTime() + 5 * 60 * 1000) {
    return { state: 'unverified', text: '자동 갱신 확인 불가: 보관 자료의 기준일을 확인하세요.', checked, good };
  }
  if (now.getTime() - checked > 96 * 3600 * 1000) {
    return { state: 'stale_check', text: '최근 수집 확인이 4일 이상 지연됐습니다. 마지막 정상 자료를 표시합니다.', checked, good };
  }
  const period = Date.parse(bundle.live.mts_record_date + 'T00:00:00Z');
  if (now.getTime() - period > 65 * 86400 * 1000) {
    return { state: 'stale_period', text: '자료 기준일이 65일 이상 지났습니다. 새 월별 실적 발행 여부를 확인해야 합니다.', checked, good };
  }
  return { state: 'ok', text: '예산 금액 자료 수집·검증 정상', checked, good };
}
