const finite=n=>typeof n==='number' && Number.isFinite(n);
export function completedAgencyActuals(live,annual,fy) {
  const y=annual.budget.agency_actuals?.[fy] || live?.fytd,ref=annual.budget.years[fy];
  const actual=ref?.status==='actual' || (annual.schema_version===1 && ref && !ref.status && !ref.estimate);
  if(!y || !ref || !y.complete || y.fy!==fy || y.through!==`${fy}-09` || !actual
     || !finite(y.outlays) || !finite(ref.outlays) || Math.abs(y.outlays-ref.outlays)>1 || !Array.isArray(y.agencies) || !y.agencies.length)return null;
  const seen=new Set();
  for(const r of y.agencies) {
    if(seen.has(r.id) || !r.id || typeof r.name!=='string' || !(r.value===null || finite(r.value))
       || !(r.prior===null || finite(r.prior)) || !['actual','missing'].includes(r.status)
       || (r.value===null && r.status!=='missing'))return null;
    seen.add(r.id);
  }
  const observed=y.agencies.filter(r=>finite(r.value));
  const total=observed.reduce((n,r)=>n+r.value,0);
  if(Math.abs(total-y.outlays)>1)return null;
  return {rows:y.agencies,fy,baseline_fy:fy-1,through:y.through,observed:observed.length,missing:y.agencies.length-observed.length,
    note:'Treasury MTS 표 6의 부처·조정항목별 순현금지출입니다. 의무/재량 및 계정별 분류와 구분합니다.'};
}

export function actualMetric(row,sort) {
  if(!finite(row.value))return null;
  if(sort==='value')return row.value;
  if(!finite(row.prior))return null;
  if(sort==='delta')return row.value-row.prior;
  if(sort==='rate')return row.prior>0 && row.value>=0 ? (row.value/row.prior-1)*100 : null;
  return null;
}
export function sortActuals(rows,sort) {
  return rows.slice().sort((a,b)=>{
    const x=actualMetric(a,sort),y=actualMetric(b,sort);
    return x===null?(y===null?0:1):y===null?-1:y-x;
  });
}
