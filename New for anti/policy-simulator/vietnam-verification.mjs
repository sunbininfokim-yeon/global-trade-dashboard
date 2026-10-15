// Bounded US official-source review, not a clearance or a live rate service.
const source = (title,url) => ({title,url});
const yarn = source('Commerce · 가공사 AD 명령 · 2021-27003','https://www.govinfo.gov/content/pkg/FR-2021-12-14/html/2021-27003.htm');
const order = source('Commerce · 베트남 타이어 CVD 명령 · 2021-15271','https://www.govinfo.gov/content/pkg/FR-2021-07-19/html/2021-15271.htm');
const sunset = source('Commerce · CVD 일몰재심 결과 · 2026-20377','https://www.govinfo.gov/content/pkg/FR-2026-10-05/html/2026-20377.htm');
const termination = source('USITC · 베트남 타이어 AD 조사 종료 · 2021-06-23','https://www.usitc.gov/press_room/news_release/2021/er0623ll1785.htm');
const schedule = source('Commerce · C-552-829 공식 사건·발표 예정','https://beta.trade.gov/adcvd?adcvdcase=C-552-829');
const reviews = {
  fiber: { scope:'베트남산 폴리에스터 타이어코드 직물. 가공사·단섬유·스틸코드·완성 타이어와 구분합니다.', terms:['Vietnam tire cord 5902 antidumping','Vietnam polyester textured yarn antidumping'],
    findings:[{title:'폴리에스터 가공사 · 별도 제품 사건',case_id:'A-552-832',country:'VNM',disposition:'different_product',document_id:'2021-27003',published:'2021-12-14',source:yarn,
      note:'명령은 폴리에스터 가공사(주요 참고 HTS 5402.33 등)의 서술 범위입니다. 5902.20 타이어코드 직물이나 HS효성 전 제품에 적용하지 않습니다.'}], sources:[yarn], remaining:'실제 직물/원사 사양·생산/수출 법인·최신 scope ruling 확인 필요. 미국 외 국가의 조사를 미국 AD로 연결하지 않습니다.' },
  'carbon-fiber': {scope:'베트남산 탄소섬유·직물·복합재는 형태별 검토가 필요합니다.',terms:['Vietnam carbon fiber antidumping','Vietnam carbon fiber countervailing'],findings:[],sources:[source('USITC · 탄소섬유 분류','https://hts.usitc.gov/search?query=6815.11')],remaining:'이번 공식 검색에서 베트남산 직접 대응 사건 미확인. 실제 생산국·제품 형태·법인·우회수출 결정 추가 확인 필요.'},
  aramid: {scope:'베트남산 아라미드 원사·단섬유·직물. 한국 본사 소재지와 생산국을 구분합니다.',terms:['Vietnam aramid antidumping','Vietnam aramid fiber countervailing'],findings:[],sources:[source('USITC · 아라미드 분류','https://hts.usitc.gov/search?query=5402.11')],remaining:'이번 공식 검색에서 베트남산 직접 대응 사건 미확인. 한국산 연구나 네덜란드 과거 철회를 적용하지 않습니다. 실제 법인·제품 범위 추가 확인 필요.'},
  tire: {scope:'베트남산 승용차·경트럭 타이어. 타이어코드나 트럭·버스 타이어 전체에 확대하지 않습니다.',terms:['Vietnam passenger light truck tires C-552-829','Vietnam tires 2026 sunset review'],findings:[
    {title:'베트남 타이어 AD 조사 종료 · 당시 조사',case_id:'A-552-828',country:'VNM',disposition:'historical_ad_terminated',published:'2021-06-23',source:termination,note:'USITC는 해당 AD 조사 대상 수입의 미소성(negligibility)을 근거로 종료했습니다. 현재 모든 AD 부존재·무관세 인증은 아닙니다.'},
    {title:'베트남 타이어 CVD 명령',case_id:'C-552-829',country:'VNM',disposition:'cvd_order',document_id:'2021-15271',published:'2021-07-19',source:order,note:'상계관세(CVD) 명령입니다. Kumho Tire (Vietnam), Sailun (Vietnam) 법인이 기재되어 있습니다. 한국 본사·한국타이어 등 다른 법인의 세율로 이식하지 않습니다.'},
    {title:'CVD 일몰재심 최종결과',case_id:'C-552-829',country:'VNM',disposition:'cvd_sunset',document_id:'2026-20377',published:'2026-10-05',source:sunset,note:'명령 철회 시 보조금 재발 가능성에 대한 Commerce 결과입니다. 연례 행정재심 최종결과·현행 예치율 변경과 다릅니다.'},
  ],sources:[termination,order,sunset,schedule],remaining:'기업별 최신 예치율·생산자/수출자 조합·CBP 지침·후속 변경 확인 필요. CVD는 AD 계산기에 사용하지 않습니다.'},
};
export const VIETNAM_VERIFICATIONS = Object.fromEntries(Object.entries(reviews).map(([product,research])=>[product,{checked_on:'2026-10-15',ad:{
  status:product==='tire'?'cvd_confirmed_ad_terminated':'bounded_search_no_confirmed_case',
  label:product==='tire'?'CVD 명령 확인 · 과거 AD 조사 종료':'공식 검색 검토 · 베트남산 대응 사건 미확인',
  rate_pct:null,case_ids:product==='tire'?['C-552-829']:[],
  note:'한정된 미국 공식 자료 조사입니다. ACCESS 활성 목록 전수조회가 아니며 사건 미발견은 면제나 0% 판정이 아닙니다.',
  research:{checked_on:'2026-10-15',method:'미국 공식 도메인 검색·공개 원문 대조. 활성 사건 목록 전수 재조회는 미실행.',...research},sources:research.sources,
  ...(product==='tire'?{official_schedule:{case_id:'C-552-829',por_start:'2024-01-01',por_end:'2024-12-31',stage:'final',announced_for:'2026-10-22',checked_on:'2026-10-15',source:schedule,note:'공식 페이지의 예정일이며 연장·변경될 수 있습니다. 날짜 경과만으로 발표 완료 처리하지 않습니다.'}}:{}),
}}]));
