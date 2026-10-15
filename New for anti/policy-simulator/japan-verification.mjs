// Bounded US-source research. Published table values are not executable deposit rates.
const src=(title,url)=>({title,url});
const hts=code=>src(`USITC · 품목 분류 ${code}`,`https://hts.usitc.gov/search?query=${code}`);
const hot=src('Commerce · 일본 열연 최종결과 · 2026-20934','https://www.govinfo.gov/content/pkg/FR-2026-10-14/pdf/2026-20934.pdf');
const pipe=src('Commerce · 일본 용접 라인파이프 명령 유지 · 2026-00784','https://www.govinfo.gov/content/pkg/FR-2026-01-16/html/2026-00784.htm');
const revoked=src('Commerce · 1998-10-09 FR p.54441 · 98-27276 변압기 철회','https://www.govinfo.gov/content/pkg/FR-1998-10-09/pdf/FR-1998-10-09.pdf');
const reviews={};
for(const [product,label,code] of [['fiber','폴리에스터 타이어코드 직물','5902.20'],['carbon-fiber','탄소섬유','6815.11'],['aramid','아라미드','5402.11'],['tire','승용차·경트럭 타이어','4011.10'],['truck-tire','트럭·버스 타이어','4011.20']]) {
  reviews[product]={scope:`일본산 ${label}. 실제 제품 형태·사양·제조/수출 법인과 생산국을 구분합니다.`,terms:[`Japan ${product==='fiber'?'tire cord fabric':product==='tire'?'passenger light truck tires':product==='truck-tire'?'truck bus tires':product.replace('-',' ')} antidumping`,`Japan ${product.replace('-',' ')} countervailing`],findings:[],sources:[hts(code)],remaining:'이번 미국 공식 검색에서 직접 대응 사건 미확인. 최신 활성 사건·scope ruling 전수조사는 미실행입니다. 다른 원산지 사건·수입국의 조사를 적용하지 않습니다.'};
}
reviews.transformer={status:'historical_order_revoked',scope:'일본산 대형 변압기의 과거 AD finding. 한국산 A-580-867과 별도 사건이며 당시 제품 범위도 다릅니다.',terms:['Japan large power transformers revocation sunset','A-588-032 revoked'],findings:[
  {title:'일본산 변압기 과거 AD finding 철회',case_id:'A-588-032',country:'JPN',disposition:'historical_order_revoked',document_id:'98-27276',published:'1998-10-09',revoked_effective_date:'2000-01-01',source:revoked,note:'과거 finding의 철회 효력은 2000-01-01입니다. 과거 마진을 현재 예치율로 쓰지 않습니다. 현재 다른 AD/CVD 사건 부존재나 전체 관세 0%를 인증한 결과는 아닙니다.'},
],sources:[revoked,src('USITC · 대형 변압기 Pub.5531 · 과거 관련 조사','https://www.usitc.gov/sites/default/files/publications/701_731/pub5531.pdf')],remaining:'실제 변압기 사양·일본 생산/수출 법인·최신 별도 조치와 거래 조건 확인 필요.'};
reviews['welded-pipe']={status:'ad_order_confirmed',case_ids:['A-588-857'],scope:'일본산 특정 용접 탄소·합금강 라인파이프. 외경 16인치 초과~64인치 미만, 규격·두께·등급별 제외조건 대조 필요. 한국산 A-580-897 또는 OCTG 사건과 구분합니다.',terms:['Japan welded large diameter line pipe continuation 2026'],findings:[
  {title:'일본 용접 대구경 라인파이프 AD 명령 유지',case_id:'A-588-857',country:'JPN',disposition:'ad_order_continued',document_id:'2026-00784',published:'2026-01-16',continuation_effective_date:'2025-12-29',source:pipe,note:'AD 명령 유지 공고입니다. CVD 존재나 기업별 새 예치율은 이 공고로 확정하지 않습니다. 공표일과 유지 효력일을 구분합니다.'},
],sources:[pipe],remaining:'실제 제품의 용도·외경·벽두께·등급·제외 사양과 법인별 현행 예치율·CBP 지침 확인 필요.'};
reviews['hot-rolled']={status:'final_notice_source_conflict',case_ids:['A-588-874'],scope:'일본산 특정 열연 평판강. 한국 A-580-883·일본의 과거 A-588-846과 다른 사건입니다. 상세 제품 범위는 공고가 채택한 결정문 확인 필요.',terms:['Japan hot rolled steel final results 2026 2023 2024','2026-20934 correction'],findings:[
  {title:'일본 열연 2023~2024 재심 최종결과',case_id:'A-588-874',country:'JPN',disposition:'final_table_text_conflict',document_id:'2026-20934',published:'2026-10-14',source:hot,note:'최종 표는 NSC 그룹 13.96%, Tokyo Steel 0.00%이며 비선정 표는 13.96%입니다. 앞 설명에는 13.96%를 Tokyo Steel에서 산정했다고 적힌 불일치가 있습니다. 표를 임의 수정하거나 현금예치 계산에 자동 연결하지 않습니다.'},
],sources:[hot],remaining:'본문 불일치의 공식 정정·채택 IDM, 회사별 예치 지침·제품 범위·후속 변경 확인 후 계산 연결. 미수록 회사에 0% 또는 13.96%를 자동 적용하지 않습니다.',
  published_margins:{por_start:'2023-10-01',por_end:'2024-09-30',published:'2026-10-14',source:hot,note:'공표 최종 마진표의 전사입니다. 자동 적용 예치율·수입자별 확정 관세가 아닙니다. 본문 불일치 검토 중.',rows:[
    {company:'Nippon Steel Corporation / Nippon Steel Nisshin Co., Ltd. / Nippon Steel Trading Corporation',rate_pct:'13.96',role:'개별조사 · 공고의 단일 법인그룹'},
    {company:'Tokyo Steel Manufacturing Co., Ltd.',rate_pct:'0.00',role:'개별조사'},
    {company:'JFE Steel Corporation; JFE Shoji Trade Corporation; JFE Shoji Corporation',rate_pct:'13.96',role:'비선정 · 공고의 기재 단위'},
    ...['Honda Trading Corporation','Marubeni-Itochu Steel Inc.','Tetsusho Kayaba Corporation','Toyo Corporation'].map(company=>({company,rate_pct:'13.96',role:'비선정'})),
  ]},
};
export const JAPAN_VERIFICATIONS=Object.fromEntries(Object.entries(reviews).map(([product,research])=>[product,{checked_on:'2026-10-15',ad:{
  status:research.status||'bounded_search_no_confirmed_case',
  label:research.status==='historical_order_revoked'?'과거 AD finding 철회 확인 · 현재 적용 별도 확인':research.status==='ad_order_confirmed'?'AD 명령 유지 확인 · 현행 예치율 검토':research.status==='final_notice_source_conflict'?'최종결과 표 확인 · 공고 본문 불일치 검토':'공식 검색 검토 · 일본산 대응 사건 미확인',
  rate_pct:null,case_ids:research.case_ids||[],note:'미국 공식 자료 선별 조사입니다. 사건 미발견·과거 철회는 면제나 0% 판정이 아닙니다. 활성 사건·법인별 최신 적용을 전수 확인한 자료가 아닙니다.',
  research:{checked_on:'2026-10-15',method:'미국 공식 도메인 검색·공개 원문 대조. 활성 사건·scope ruling 전수조사는 미실행.',...research},sources:research.sources,
  ...(research.published_margins?{published_margins:research.published_margins}:{}),
}}]));
