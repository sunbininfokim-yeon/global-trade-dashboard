// US measures on Chinese-origin products. No rates inferred from sunset findings.
const src=(title,url)=>({title,url});
const pvlt=src('Commerce · 중국 PVLT AD/CVD 명령 유지 · 2026-14293','https://www.govinfo.gov/content/pkg/FR-2026-07-16/html/2026-14293.htm');
const tbt=src('Commerce · 중국 트럭·버스 타이어 AD/CVD 명령 유지 · 2024-19390','https://www.govinfo.gov/content/pkg/FR-2024-08-29/html/2024-19390.htm');
const yarn=src('Commerce · 중국 폴리에스터 가공사 AD 최종판정 · 2019-25088','https://www.govinfo.gov/content/pkg/FR-2019-11-19/html/2019-25088.htm');
const reviews={
  fiber:{scope:'중국산 폴리에스터 타이어코드 직물. 가공사·단섬유·나일론 직물·완성 타이어와 구분합니다.',terms:['China polyester tire cord antidumping','China polyester textured yarn antidumping'],findings:[
    {title:'폴리에스터 가공사 · 제품 범위 불일치',case_id:'A-570-097',country:'CHN',disposition:'different_product',document_id:'2019-25088',published:'2019-11-19',source:yarn,note:'대상은 폴리에스터 가공사입니다. 타이어코드 직물에 적용할 사건·예치율로 등록하지 않습니다. 미국 외 국가의 타이어코드 조사도 미국 조치로 연결하지 않습니다.'},
  ],sources:[yarn],remaining:'직물/원사·처리 방식·법인·실제 생산국과 미국 최신 scope ruling 확인 필요. 미국 직접 대응 사건은 이번 검색에서 미확인.'},
  'carbon-fiber':{scope:'중국산 탄소섬유·직물·프리프레그·복합재를 구분합니다.',terms:['China carbon fiber antidumping 2026','China carbon fiber countervailing'],findings:[],sources:[src('USITC · 탄소섬유 분류','https://hts.usitc.gov/search?query=6815.11')],remaining:'이번 공식 검색에서 원재료 탄소섬유 직접 대응 사건 미확인. 탄소강·활성탄 사건이나 탄소섬유를 재료로 쓰는 완제품 사건을 원재료에 확대하지 않습니다. 제품 형태·제조/수출 법인 추가 확인 필요.'},
  aramid:{scope:'중국산 아라미드 원사·단섬유·펄프·직물을 구분합니다.',terms:['China aramid antidumping 2026','China aramid fiber countervailing'],findings:[],sources:[src('USITC · 아라미드 분류','https://hts.usitc.gov/search?query=5402.11')],remaining:'이번 미국 공식 검색에서 직접 대응 사건 미확인. 다른 원산지의 과거 사건·철회를 적용하지 않습니다. 실제 사양·법인·최신 scope ruling 추가 확인 필요.'},
  tire:{scope:'중국산 승용차·경트럭용 신품 공기타이어. 트럭·버스 타이어 사건과 구분하며 측면 표시·규격·제외 조건 대조 필요.',terms:['China passenger light truck tires 2026 continuation'],case_ids:['A-570-016','C-570-017'],findings:[
    {title:'PVLT AD/CVD 명령 유지',case_id:'A-570-016 / C-570-017',country:'CHN',disposition:'ad_cvd_continued',document_id:'2026-14293',published:'2026-07-16',continuation_effective_date:'2026-07-07',source:pvlt,note:'명령 유지 효력은 7/7, 공표는 7/16입니다. 일몰재심 후 명령 유지이며 기업별 새 예치율을 확정하는 행정재심 결과가 아닙니다. 베트남의 과거 AD 조사 종료와 다른 중국산 사건입니다.'},
  ],sources:[pvlt],remaining:'기업별 최신 AD·CVD 예치율, 생산자/수출자 조합·CBP 지침·후속 정정 확인 필요. 기존 301 등 다른 추가관세와의 합산은 이번 조사 범위 밖입니다.'},
  'truck-tire':{scope:'중국산 트럭·버스 신품 공기타이어. TR/HC·규격·제외 조건을 확인하며 차량에 장착되어 들어오는 타이어 등은 서술 범위와 대조합니다.',terms:['China truck bus tires continuation orders','A-570-040 C-570-041 official announcements'],case_ids:['A-570-040','C-570-041'],findings:[
    {title:'트럭·버스 타이어 AD/CVD 명령 유지',case_id:'A-570-040 / C-570-041',country:'CHN',disposition:'ad_cvd_continued',document_id:'2024-19390',published:'2024-08-29',continuation_effective_date:'2024-08-21',source:tbt,note:'명령 유지 효력은 8/21, 공표는 8/29입니다. PVLT와 별도 사건·규격입니다. 일몰재심 수치를 현행 예치율로 사용하지 않습니다.'},
  ],sources:[tbt,src('Commerce · 트럭·버스 AD 사건','https://beta.trade.gov/adcvd?adcvdcase=A-570-040'),src('Commerce · 트럭·버스 CVD 사건','https://beta.trade.gov/adcvd?adcvdcase=C-570-041')],remaining:'10/15 확인한 공식 사건 페이지에는 향후 발표 일정이 표시되지 않았습니다. 이는 절차 종료나 예정 없음의 확정이 아닙니다. 기업별 현행 AD/CVD 예치율·CBP 지침·후속 변경 확인 필요.'},
};
export const CHINA_VERIFICATIONS=Object.fromEntries(Object.entries(reviews).map(([product,research])=>[product,{checked_on:'2026-10-15',ad:{
  status:research.case_ids?'ad_cvd_order_confirmed':'bounded_search_no_confirmed_case',
  label:research.case_ids?'AD·CVD 명령 유지 확인 · 현행 예치율 검토':'공식 검색 검토 · 중국산 대응 사건 미확인',
  rate_pct:null,case_ids:research.case_ids||[],note:'미국 공식 자료 선별 조사입니다. 사건 전수조회·적용 제외 확정이 아니며 사건 미발견은 면제나 0% 판정이 아닙니다.',
  research:{checked_on:'2026-10-15',method:'미국 공식 도메인 검색·Commerce 원문 범위 대조. 활성 사건·scope ruling 전수조사는 미실행.',...research},sources:research.sources,
}}]));
