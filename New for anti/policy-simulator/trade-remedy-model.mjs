// Public, date-bounded deposit evidence. Historical audit coverage is NOT expiry.
const doc=(id,published)=>({id,published,url:`https://www.govinfo.gov/content/pkg/FR-${published}/html/${id}.htm`});
export const REMEDY_QUOTES=[
  ...[['transamerica','Qingdao Transamerica Tire Industrial Co., Ltd.','59.15'],['haohua','Shandong Haohua Tire Co., Ltd.','78.33'],['triangle','Triangle Tyre Co., Ltd.','59.77']].map(([id,company,rate_pct])=>({id:`cn-${id}-2026`,country:'CHN',product:'tire',duty:'AD',case_id:'A-570-016',company,rate_pct,effective:'2026-08-14',verified_through:'2026-08-14',source:doc('2026-16662','2026-08-14'),status:'publication_snapshot',note:'Final Results와 Cash Deposit Requirements (1) 대조. 해당 separate-rate 수출 법인의 공표 시점 이력이며, CVD·다른 기업·오늘의 유효율에 자동 적용하지 않습니다.'})),
  {id:'vn-bridgestone-2023',country:'VNM',product:'tire',duty:'CVD',case_id:'C-552-829',company:'Bridgestone Tire Manufacturing Vietnam, LLC',rate_pct:'0.00',effective:'2023-09-29',verified_through:'2023-09-29',source:doc('2023-21450','2023-09-29'),status:'publication_snapshot',note:'2020년 보조금률1.34%와 구분. Cash Deposit Instructions는2021년0%를 지정합니다. 이후 변경 전수 확인은 미완료입니다.'},
  ...[['kumho','Kumho Tire (Vietnam) Co., Ltd.','7.89'],['sailun','Sailun (Vietnam) Co., Ltd.','6.23']].map(([id,company,rate_pct])=>({id:`vn-${id}-2021`,country:'VNM',product:'tire',duty:'CVD',case_id:'C-552-829',company,rate_pct,effective:'2021-07-16',verified_through:'2021-07-19',effective_source:doc('2021-15108','2021-07-16'),source:doc('2021-15271','2021-07-19'),status:'publication_snapshot',note:'명령 공표 2021-07-19, 예치 재개는 ITC 판정 공표 2021-07-16을 기준으로 합니다. 후속 행정재심·소송을 포함한 현재 예치율 확인이 아닙니다.'})),
];
export const REMEDY_HOLDS=[
  {country:'JPN',product:'hot-rolled',case_id:'A-588-874',status:'held_conflict',source:doc('2026-20934','2026-10-14'),note:'최종표와 비선정 설명 문단의 법인·13.96% 연결 불일치. 공식 정정·IDM 확인 전 계산 보류.'},
  {country:'KOR',product:'octg',case_id:'A-580-870',status:'held_conflict',source:doc('2026-19529','2026-09-24'),note:'개별 최종마진9.80/29.94와 예치 조항 simple-average의 적용 관계 불명확. 임의 평균 또는 개별마진을 예치율로 확정하지 않음.'},
];
const day=v=>{if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v)||!Number.isFinite(Date.parse(v))||new Date(v).toISOString().slice(0,10)!==v)throw Error('유효한 통관일 필요');return v;};
const dec=(v,max=1e12)=>{if(!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(String(v)))throw Error('0 이상 소수점6자리 이내 숫자 필요');if(Number(v)>max)throw Error('입력 범위 초과');const[a,b='']=String(v).split('.');return BigInt(a)*1000000n+BigInt(b.padEnd(6,'0'));};
const usd=(n,d)=>{const sign=n<0n?'-':'',x=n<0n?-n:n,c=(x*200n+d)/(2n*d);return `${c?sign:''}${c/100n}.${String(c%100n).padStart(2,'0')}`;};
export function lookupRemedy(input,quotes=REMEDY_QUOTES){
  const entry=day(input.entry_date),q=quotes.find(x=>x.id===input.quote_id);
  if(!q||q.country!==input.country||q.product!==input.product||q.duty!==input.duty||q.company!==input.company)return {status:'unresolved',rate_pct:null,reason:'공고의 원산지·품목·제도·정확한 법인 일치 필요'};
  if(q.status!=='publication_snapshot'||entry<q.effective||entry>q.verified_through)return {status:'unresolved',rate_pct:null,reason:'자료 검증 범위 밖 통관일. 예치율 만료를 뜻하지 않으며 최신 지침 추가 확인 필요'};
  return {...structuredClone(q),status:'historical_published_reference',entry_date:entry};
}
export function simulateRemedy(input){
  if(!['AD','CVD'].includes(input.duty))throw Error('AD 또는 CVD 선택 필요');
  if(input.scope_confirmed!==true||input.identity_confirmed!==true)throw Error('제품·원산지와 생산자/수출자 법인 적용 조건 확인 필요');
  if(!/^[A-Z]{3}$/.test(input.country||'')||!input.product?.trim())throw Error('제품·원산지 선택 필요');
  const entry=day(input.entry_date);let ref;
  if(input.mode==='published'){
    ref=lookupRemedy(input);if(ref.status==='unresolved')return {status:'unresolved',reference:ref,reference_deposit_usd:null};
  }else if(input.mode==='manual'){
    if(REMEDY_HOLDS.some(h=>h.country===input.country&&h.product===input.product&&h.case_id===input.case_id))throw Error('공식 원문 불일치로 보류된 사건입니다. 정정·지침 검증 전 계산 불가');
    if(!new RegExp(`^${input.duty==='AD'?'A':'C'}-\\d{3}-\\d{3}$`).test(input.case_id||''))throw Error('제도와 사건번호 A-/C- 일치 필요');
    if(!input.company?.trim()||!input.note?.trim()||input.company.length>300||input.note.length>2000)throw Error('법인명·적용 근거 필요');
    const u=new URL(input.source_url);if(u.protocol!=='https:'||u.username||u.password)throw Error('인증정보 없는 HTTPS 출처 필요');
    dec(input.reference_rate_pct,10000);
    ref={status:'user_supplied_not_independently_verified',country:input.country,product:input.product,duty:input.duty,case_id:input.case_id,company:input.company,rate_pct:String(input.reference_rate_pct),source:{url:u.href,note:input.note},entry_date:entry};
  }else throw Error('공표 이력 또는 직접 확인 선택 필요');
  const value=dec(input.entered_value_usd),a=dec(ref.rate_pct,10000),b=dec(input.scenario_rate_pct,10000),f=dec(input.annual_finance_pct,100),days=dec(input.holding_days,36500);
  if(!value||days%1000000n)throw Error('신고가격 양수·기간 정수 일수 필요');
  const d=100000000000000n,fd=d*1000000000000n*36500n;
  return {status:'calculated',model_version:'trade-remedy-deposit-1',duty:input.duty,reference:ref,inputs:structuredClone(input),
    reference_deposit_usd:usd(value*a,d),scenario_deposit_usd:usd(value*b,d),deposit_change_usd:usd(value*(b-a),d),
    reference_financing_usd:usd(value*a*f*days,fd),scenario_financing_usd:usd(value*b*f*days,fd),
    limitations:['AD와 CVD는 별도 계산이며 일반관세·수수료와 합산하지 않음','최종 관세·환급·실제 덤핑마진 예측 아님','원산지는 본사·선적국이 아님','과거 검증 범위 밖을 현행 세율로 연장하지 않음']};
}
