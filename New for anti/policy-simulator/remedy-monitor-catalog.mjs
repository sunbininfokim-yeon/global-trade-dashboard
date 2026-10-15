import {AD_CATALOG} from './antidumping-catalog.mjs';
// Only confirmed case/product/origin pairs. A terminated or other-product case
// must not enter this active review universe merely because search mentioned it.
const products={'A-580-867':'transformer','A-580-908':'tire','A-580-883':'hot-rolled','A-580-897':'welded-pipe','A-580-914':'sap'};
const cases=AD_CATALOG.cases.map(c=>({...c,product:products[c.case_id],country:'KOR',duty:'AD'}));
for(const [country,product,ids] of [
 ['KOR','octg',['A-580-870']],['VNM','tire',['C-552-829']],
 ['CHN','tire',['A-570-016','C-570-017']],['CHN','truck-tire',['A-570-040','C-570-041']],
 ['JPN','hot-rolled',['A-588-874']],['JPN','welded-pipe',['A-588-857']],
])for(const case_id of ids)cases.push({country,product,case_id,duty:case_id[0]==='C'?'CVD':'AD'});
export const REMEDY_MONITOR_CATALOG={cases,documents:{...AD_CATALOG.documents,...Object.fromEntries(['2026-19529','2026-20377','2026-14293','2024-19390','2026-20934','2026-00784'].map(id=>[id,{}]))}};
export const REMEDY_SCHEDULES=[{case_id:'C-552-829',country:'VNM',product:'tire',por_start:'2024-01-01',por_end:'2024-12-31',stage:'final',announced_for:'2026-10-22',checked_on:'2026-10-15',url:'https://beta.trade.gov/adcvd?adcvdcase=C-552-829'}];
export function scheduleReviews(through){return REMEDY_SCHEDULES.map(s=>({...s,status:through>=s.announced_for?'due_requires_official_result_or_extension':'planned_not_completed',note:'선별 확인 일정입니다. 날짜 경과는 완료가 아니며 최신 연장·결과 공고의 검토가 필요합니다.'}));}
