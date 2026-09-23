// Data-only browser integration. No DOM or UI mutation. Fetches only selected
// country/HS/period parts; monthly and annual fallback are never interchanged.
export function availablePeriods(index, {countryCode, hs, frequency='M'}) {
  return [...new Set(index.entries.filter(e => e.hs === hs && e.frequency === frequency
    && (e.reporter === countryCode || e.partners.includes(countryCode))).map(e => e.period))].sort().reverse();
}

export function countryRows(part, countryCode) {
  const reporter = part.meta.reporter;
  const rows = [];
  for (const [flow, block] of Object.entries(part.flows)) {
    for (const r of block.rows) {
      if (countryCode !== r.exporter && countryCode !== r.importer) continue;
      const direct = countryCode === reporter;
      rows.push({...r, source: part.meta.source, hs: part.meta.hs, hs_version: part.meta.hs_version,
        period: part.meta.period, frequency: part.meta.frequency, reporter, source_flow: flow,
        focus_flow: direct ? flow : flow === 'X' ? 'M' : 'X',
        counterparty: direct ? r.partner : reporter,
        reporting_basis: direct ? 'reporter_dataset' : 'partner_report_mirror',
        analysis: direct ? r.analysis : Object.fromEntries(Object.keys(r.analysis).map(k => [k,
          {share_pct:null, share_reason:'mirror_denominator_not_comparable', rank:null, rank_scope:'not_ranked'}])),
        acquisition: part.acquisition});
    }
  }
  return rows;
}

export async function loadBilateral({baseUrl, countryCode, hs, period, frequency='M', source, signal}, fetcher=fetch) {
  const base = baseUrl.endsWith('/') ? baseUrl : baseUrl + '/';
  async function get(path) {
    const response = await fetcher(base + path, {signal});
    if (!response.ok) throw new Error('bilateral_data_unavailable');
    return response.json();
  }
  const index = await get('index.json');
  if (index.schema !== 'commodity-trade-bilateral-index-v1') throw new Error('unsupported_schema');
  const entries = index.entries.filter(e => e.hs === hs && e.frequency === frequency && e.period === period
    && (!source || e.source === source) && (e.reporter === countryCode || e.partners.includes(countryCode)));
  const rows = [], failures = [];
  // Bounded concurrent downloads: sequential to avoid request spikes on a country click.
  for (const e of entries) {
    if (!/^parts\/[a-f0-9]{64}\.json$/.test(e.path)) throw new Error('invalid_part_path');
    try {
      const part = await get(e.path);
      if (part.meta.hs !== hs || part.meta.period !== period || part.meta.frequency !== frequency
        || part.meta.reporter !== e.reporter || part.meta.source !== e.source) throw new Error('part_scope_mismatch');
      rows.push(...countryRows(part, countryCode));
    } catch (error) {
      if (signal?.aborted) throw error;
      failures.push(e.path);
    }
  }
  return {schema:'country-bilateral-view-v1', rows, failures,
    status: failures.length ? 'partial' : rows.length ? 'available' : 'not_available',
    periods: availablePeriods(index, {countryCode, hs, frequency}),
    export_control_coverage:index.export_control_coverage,
    product_policy_screens:(index.product_policy_screens || []).filter(p => p.reporter === countryCode
      && p.hs === hs && p.period === period && p.frequency === frequency),
    note:'Direct and mirror observations are alternatives, never additive; empty is not zero.'};
}
