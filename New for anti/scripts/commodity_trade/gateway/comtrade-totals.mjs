// A total is identified by scope, not by its amount or position in the response.
export function selectComtradeTotals(rows) {
  const grouped = new Map();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error('invalid_row');
    if (Object.entries({partner2Code:'0', customsCode:'C00', motCode:'0'})
      .some(([k,v]) => row[k] != null && String(row[k]) !== v)) continue;
    for (const k of ['netWgt','primaryValue']) {
      if (row[k] != null && (typeof row[k] !== 'number' || !Number.isFinite(row[k]) || row[k] < 0)) throw new Error('invalid_metric');
    }
    const key = ['reporterCode','period','cmdCode','flowCode','partnerCode'].map(k=>row[k]??'').join('|');
    const prior = grouped.get(key);
    if (prior && ['netWgt','primaryValue'].some(k=>prior[k] !== row[k])) throw new Error('conflicting_totals');
    grouped.set(key,row);
  }
  return [...grouped.values()];
}
