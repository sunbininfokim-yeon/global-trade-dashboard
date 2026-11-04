// Product evidence and proceeding evidence are independent. A trader is not
// automatically the investigated producer/exporter. No executable duty rates.
export const INDUSTRIAL_CHECKED_ON = '2026-11-04';
export const INDUSTRIAL_COMPARISON_CHECKED_ON = '2026-11-05';
const source = (title, url) => ({title, url});
const fr = (id, date, title) => ({...source(title, `https://www.govinfo.gov/content/pkg/FR-${date}/html/${id}.htm`), document_id:id, published:date});
export const CHOSUN_SHAPED = source('조선내화 · 정형 제품 분류', 'https://www.chosunref.co.kr/pages/product/orthopedic.do');
export const CHOSUN_MONOLITHIC = source('조선내화 · 부정형 제품 분류', 'https://www.chosunref.co.kr/pages/product/irregular.do');
export const FOOSUNG_PRODUCTS = source('후성코퍼레이션 · 공식 취급 품목', 'https://www.foosungcorp.com/kr/mobile/business/business_item.asp');
export const INDUSTRIAL_PRODUCTS = [
  {id:'magnesia-carbon-bricks', label:'마그카본질 내화벽돌', family:'refractories', profile:'chosun-refractories', source:CHOSUN_SHAPED, scope:'마그네시아·카본 벽돌. MgO 함량·결합 방식·형상·생산국·생산자/수출자와 명령 서술 범위를 대조해야 합니다. 조선내화 전체 제품·한국 본사를 중국산 사건으로 확정하지 않습니다.'},
  {id:'high-alumina-bricks', label:'고알루미나 내화벽돌', family:'refractories', profile:'chosun-refractories', source:CHOSUN_SHAPED, scope:'고알루미나·특수 알루미나질 벽돌. 마그카본 벽돌과 성분·결합·형상이 다르며 동일 사건·세율을 상속하지 않습니다.'},
  {id:'monolithic-refractories', label:'부정형 내화재 · 캐스터블·몰탈', family:'refractories', profile:'chosun-refractories', source:CHOSUN_MONOLITHIC, scope:'캐스터블·스프레이재·몰탈 등 혼합물. 정형 내화벽돌과 다른 제품군이며 성분·용도·공급 형태에 따라 분류·사건 범위가 달라집니다.'},
  ...[['ethyl-acetate','초산에틸 · EA','초산에틸(Ethyl Acetate). 중국산 한국 수입 조사와 미국 수입 사건을 구분합니다. 초산·초산비닐·초산부틸로 확대하지 않습니다.'],['methyl-ethyl-ketone','메틸에틸케톤 · MEK','MEK(Methyl Ethyl Ketone). EA·아세톤과 다른 물질이며, 용제라는 이유로 다른 물질의 반덤핑을 적용하지 않습니다.'],['dimethylformamide','디메틸포름아미드 · DMF','DMF(Dimethylformamide). 순도·혼합물·원산지·실제 제조/수출 법인 확인이 필요합니다.'],['acetone','아세톤 · ACT','아세톤(Acetone). 중국산·한국산과 수입국을 구분합니다. 한국산 미국 사건의 공고 제조사 세율을 후성의 고유 세율로 사용하지 않습니다.']].map(([id,label,scope])=>({id,label,scope,family:'chemicals',profile:'foosung-corporation',source:FOOSUNG_PRODUCTS})),
];
const continuation = fr('2021-17790','2021-08-19','Commerce · 중국·멕시코 AD / 중국 CVD 명령 유지');
const mek = source('인도 DGTR · MEK 2018-02-01 최종 권고, 표 pp.40~41','https://dgtr.gov.in/sites/default/files/2024-07/FF%20NCV%201.2.18.pdf');
const mekTermination = source('WTO WT/TPR/OV/24/Add.1 p.26 · 인도 MEK 2021-04-23 종료 보고','https://www.wto.org/english/news_e/news21_e/ov24a1.pdf');
const chinaMEKTermination = source('MOFCOM 2019 제51호 · 일본·대만산 MEK 조치 종료','https://cacs.mofcom.gov.cn/cacscms/articleDetail/jkdc?articleId=161256&id=53d8a6e26e584780016e87820f590e18');
const dmf = source('인도 DGTR · DMF 2021-01-11 최종 권고, 표 pp.59~60','https://dgtr.gov.in/sites/default/files/2024-08/FF%20-%20DMF%20NCV.pdf');
const brickAD = fr('2026-22523','2026-11-04','Commerce · 마그카본 벽돌 AD 제3차 일몰 최종결과');
const brickCVD = fr('2026-22529','2026-11-04','Commerce · 중국산 마그카본 벽돌 CVD 제3차 일몰 최종결과');
const rescission = fr('2026-16051','2026-08-06','Commerce · 중국산 마그카본 벽돌 2024~2025 재심 철회');
const acetone = fr('2026-11549','2026-06-09','Commerce · 한국산 아세톤 2024~2025 최종결과');
const eaDetail = source('KTC · 중국산 초산에틸 원심 상세 / 수입자 제출 기록','https://www.ktc.go.kr/viewInvest.do?masterId=00000869&invstg_type_code=10100001');
const eaScope = source('KTC · 중국산 초산에틸 범위 안내서 / PDF 첨부','https://www.ktc.go.kr/qnaDetailView.do?invstg_mast_id=00000869&bbs_id=00000001&bbs_type_code=10700001');
const eaInitiation = source('KTC · 중국산 초산에틸 개시결정 공개 보고 / PDF 첨부','https://www.ktc.go.kr/procFileListView.do?invstg_mast_id=00000869&invstg_seq_no=0007');
const eaHistory = source('기재부 · 2019 초산에틸 AD 연장 공식 설명 (과거 자료)','https://www.korea.kr/briefing/actuallyView.do?newsId=148862628');
const ktc = source('한국 무역위원회 · 진행 중 반덤핑 조사 목록','https://www.ktc.go.kr/proInvestList.do');
export const INDUSTRIAL_CASES = [
  {id:'cn-jp-mek-terminated', product:'methyl-ethyl-ketone', import_country:'CHN', origin:'JPN', duty:'AD', case_id:'MOFCOM 2019 제51호', stage:'measure_terminated', procedure_label:'해당 중국 수입 AD 조치 종료 공고 확인', date:'2019-11-21', source:chinaMEKTermination, related_sources:[], rate_pct:null,
    steps:[['일몰재심·기존 조치 종료 공고','confirmed','2019-11-20'],['해당 AD 징수 중단','confirmed','2019-11-21'],['이후 신규 조치 전수 확인','unknown',null]],
    note:'중국이 일본·대만산 MEK에 부과하던 조치가 종료된 사건입니다. 공고는 2019-11-21부터 해당 AD를 징수하지 않는다고 명시합니다. 이 행은 일본산→중국 수입에 한정합니다. 중국산→한국/미국 사건이 아니며 현재 모든 관세가 0%이거나 규제가 없다는 뜻이 아닙니다.'},
  {id:'us-mx-mcb-ad', product:'magnesia-carbon-bricks', import_country:'USA', origin:'MEX', duty:'AD', case_id:'A-201-837', stage:'commerce_sunset_final', procedure_label:'상무부 제3차 일몰재심 최종결과 공표', date:'2026-11-04', source:brickAD, related_sources:[continuation], rate_pct:null,
    steps:[['상무부 일몰 최종결과','confirmed','2026-11-04'],['동일 차수 ITC 결과','unknown',null],['동일 차수 명령 유지·철회','unknown',null]],
    note:'2021년 명령 유지 공고와 2026년 상무부 일몰 결과를 확인했습니다. 일몰 재발 가능성 마진은 현행 예치율이 아닙니다. 멕시코산 AD 사건이며 중국산 CVD를 합산하지 않습니다. 한국 본사·선적국으로 제품 원산지를 확정하지 않습니다.'},
  {id:'in-cn-mek-historical', product:'methyl-ethyl-ketone', import_country:'IND', origin:'CHN', duty:'AD', case_id:'14/26/2016-DGAD', stage:'historical_measure_termination_reported', procedure_label:'과거 인도 조치 종료 · WTO 공식 보고 확인', date:'2021-04-23', date_kind:'termination_reported', source:mekTermination, related_sources:[mek], termination_date:'2021-04-23', recommendation_date:'2018-02-01', rate_pct:null,
    reported_values:[{kind:'historical_reference_price_recommendation',amount:1147.06,unit:'USD/MT',entity:'중국산 · 표의 원산지/수출국 조건 대조 필요'}],
    steps:[['최종 권고 공표','confirmed','2018-02-01'],['부과·종료의 WTO 공식 보고','confirmed','2021-04-23'],['종료 후 신규 조치 전수 확인','unknown',null]],
    note:'표의 1,147.06 USD/MT는 권고 기준가격입니다. 관세 정액이나 %가 아니며, 해당 landed value가 기준보다 낮을 때 차액을 부과하도록 3년을 권고했습니다. WTO 보고서는 인도 정부 대표부의 통보를 근거로 2018-04-24 확정 부과와 2021-04-23 종료를 기록합니다. 인도 국내 부과·종료 원문과 종료 후 모든 신규 조치까지 확인한 것은 아닙니다. 이 과거 기준가격을 현행 세율로 사용하지 않습니다. 인도 수입 사건으로 한국·미국 계산에 이식하지 않습니다. MEK와 MIBK는 다른 물질입니다.'},
  {id:'in-cn-dmf-historical', product:'dimethylformamide', import_country:'IND', origin:'CHN', duty:'AD', case_id:'6/37/2019-DGTR', stage:'historical_recommendation', procedure_label:'과거 인도 최종 권고 확인 · 현행 부과 미확인', date:'2021-01-11', source:dmf, related_sources:[], rate_pct:null,
    reported_values:[{kind:'historical_specific_duty_recommendation',amount:377.21,unit:'USD/MT',entity:'Liaocheng Luxi Methylamine Chemical Co., Ltd. · 중국산/중국 수출 행'}, {kind:'historical_specific_duty_recommendation',amount:405.75,unit:'USD/MT',entity:'위 생산자 외 · 중국산/중국 수출 행'}],
    steps:[['최종 권고 공표','confirmed','2021-01-11'],['현행 부과·연장·종료','unknown',null]],
    note:'2021년 최종 권고표의 종량세 금액입니다. % 세율이 아니며 중앙정부 부과 공고일부터 5년을 권고한 것입니다. 실제 부과·발효일·후속 재심·현재 유효성은 미확인입니다. 홈페이지 갱신일을 새 조사일로 사용하지 않습니다. 후성 또는 다른 중국 생산자의 현행 세율로 확정하지 않습니다. 한국·미국 수입 세율은 별도 미확인입니다.'},
  {id:'us-cn-mcb-ad', product:'magnesia-carbon-bricks', import_country:'USA', origin:'CHN', duty:'AD', case_id:'A-570-954', stage:'commerce_sunset_final', procedure_label:'상무부 제3차 일몰재심 최종결과 공표', date:'2026-11-04', source:brickAD, related_sources:[continuation,rescission], rate_pct:null,
    steps:[['상무부 일몰 최종결과','confirmed','2026-11-04'],['동일 차수 ITC 결과','unknown',null],['동일 차수 명령 유지·철회','unknown',null]],
    note:'일몰재심의 재발 가능성 판단입니다. 현재 예치율·최종 확정 관세·기업별 미래 세율이 아닙니다. 8/6의 연례재심 철회는 명령 철회가 아니며 공고는 예치율 변경 없음으로 명시합니다. 조선내화 또는 중국 관계사와 공고 법인의 동일성은 미확인입니다.'},
  {id:'us-cn-mcb-cvd', product:'magnesia-carbon-bricks', import_country:'USA', origin:'CHN', duty:'CVD', case_id:'C-570-955', stage:'commerce_sunset_final', procedure_label:'상무부 제3차 CVD 일몰재심 최종결과 공표', date:'2026-11-04', source:brickCVD, related_sources:[continuation], rate_pct:null,
    steps:[['상무부 CVD 일몰 최종결과','confirmed','2026-11-04'],['동일 차수 ITC 결과','unknown',null],['동일 차수 명령 유지·철회','unknown',null]],
    note:'AD와 별도 CVD 사건입니다. 공고의 일몰 보조금률은 계산 예치율로 연결하지 않습니다. 조선내화의 한국산·모든 내화재 또는 다른 법인에 이식하지 않습니다.'},
  {id:'kr-cn-ethyl-acetate', product:'ethyl-acetate', import_country:'KOR', origin:'CHN', duty:'AD', case_id:'구제23-2026-6호', stage:'investigation_in_progress', procedure_label:'한국 원심 개시 · 국내수입자 참여 기록 확인', date:'2026-08-18', date_kind:'investigation_initiated', source:eaDetail, related_sources:[ktc,eaScope,eaInitiation,eaHistory], rate_pct:null, checked_on:INDUSTRIAL_COMPARISON_CHECKED_ON,
    scope_reference:{hsk:'2915.31.0000',jurisdiction:'KOR',formula:'CH3COOC2H5',form:'liquid',classification_is_dispositive:false,source:eaScope},
    alleged_values:[{kind:'petitioner_alleged_dumping_margin',amount:28.80,unit:'%',source:eaInitiation}],
    investigation_period:{start:'2025-01-01',end:'2025-12-31',may_be_adjusted:true,source:eaInitiation},
    company_roles:[{profile:'foosung-corporation',name:'후성코퍼레이션',role:'domestic_importer',submitted:'2026-09-21',recorded:'2026-09-30',scope:'제출현황의 국내수입자 답변서',source:eaDetail}],
    steps:[['조사 개시','confirmed','2026-08-18'],['예비판정·잠정조치','unknown',null],['최종판정','unknown',null],['부과·가격약속','unknown',null]],
    note:'2026-11-05 상세·공개 개시보고·범위 PDF를 대조했습니다. 후성코퍼레이션은 9/21 국내수입자 답변서 제출(9/30 등록)이 확인됩니다. 이는 중국 생산자·수출자별 덤핑률 확인이 아닙니다. 범위는 제조공법·원료와 무관한 액체 초산에틸(CH3COOC2H5)이며 HSK2915.31.0000은 참고용입니다. 개시보고의 28.80%는 신청인 제시 덤핑률로 확정/잠정 관세가 아닙니다. 상세의 예비조사·최종판정 날짜와 판정결과는 비어 있어 부과 여부를 확정하지 않습니다. 과거 2019 연장 자료는 이번 원심과 분리합니다. 이 한국 사건을 미국 계산에 사용하지 않습니다.'},
  {id:'us-kr-acetone', product:'acetone', import_country:'USA', origin:'KOR', duty:'AD', case_id:'A-580-899', stage:'administrative_review_final', procedure_label:'2024~2025 POR 상무부 최종결과 공표', date:'2026-06-09', por_start:'2024-03-01', por_end:'2025-02-28', source:acetone, related_sources:[], rate_pct:null,
    steps:[['해당 POR 최종결과','confirmed','2026-06-09'],['거래별 현행 예치 지침','unknown',null],['소송·관세 정산','unknown',null]],
    note:'이 공고의 개별조사 법인은 Kumho P&B Chemicals, Inc.입니다. 최종 마진표·예치 조항이 있어도 후성의 제조사·수출자 조합을 확인하지 않고 적용하지 않습니다. 중국산 아세톤이나 초산에틸로 이식하지 않습니다. 최신 세그먼트 전수 검토·후성별 적용은 미확인입니다.'},
].map(r=>({...r,checked_on:r.checked_on||INDUSTRIAL_CHECKED_ON,calculation_ready:false,company_application:'unconfirmed'}));
export function industrialCases(product, origin=null, importCountry=null) {
  return INDUSTRIAL_CASES.filter(c=>c.product===product&&(!origin||c.origin===origin)&&(!importCountry||c.import_country===importCountry)).map(c=>structuredClone(c));
}
export function industrialUSVerification(product,origin) {
  const p=INDUSTRIAL_PRODUCTS.find(p=>p.id===product); if(!p)return null;
  const records=industrialCases(product,origin,'USA'), research=industrialResearchStatus(product,origin,'USA');
  return {checked_on:research.checked_on||INDUSTRIAL_CHECKED_ON,ad:{country:origin,import_country:'USA',status:records.length?'industrial_us_case_reviewed':research.state==='bounded_search_no_confirmed_case'?'industrial_bounded_search':'industrial_case_not_reviewed',label:records.length?'미국 수입 공식 사건 확인 · 기업별 적용 미확정':research.label,rate_pct:null,case_ids:records.map(r=>r.case_id),sources:[p.source,...research.sources,...records.flatMap(r=>[r.source,...r.related_sources])],note:research.note,research_status:research,records}};
}
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const country=c=>({USA:'미국',KOR:'한국',CHN:'중국',JPN:'일본',VNM:'베트남',MEX:'멕시코',IND:'인도'})[c]||c;
const link=s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`;
export function industrialEvidenceMarkup(product,origin=null,{originControls=true}={}) {
  const p=INDUSTRIAL_PRODUCTS.find(p=>p.id===product); if(!p)return '';
  const records=industrialCases(product),matched=records.filter(r=>r.origin===origin);
  return `<section class="ts-ad-notices" data-industrial-evidence><h2>수입국별 관련 사건</h2><p class="ts-help">기업의 취급·생산 품목과 실제 반덤핑 적용은 별개입니다. 현재 원산지 ${esc(country(origin)||'미선택')} · 기본 자료 확인 ${INDUSTRIAL_CHECKED_ON} / 추가 대조는 행별 확인일. 수입국별 조사·부과 절차를 합치지 않습니다. 과거 권고와 현행 부과를 구분합니다.</p>${link(p.source)}${INDUSTRIAL_IDENTITIES[product]?`<p class="ts-help" data-substance-identity>물질 식별 CAS ${INDUSTRIAL_IDENTITIES[product].cas} · ${esc(INDUSTRIAL_IDENTITIES[product].aliases.join(' / '))}. ${link(INDUSTRIAL_IDENTITIES[product].source)} · 물질 식별은 사건 범위·관세 적용 확정과 별개입니다.</p>`:''}${researchStatusMarkup(product,origin)}
    ${records.length?records.map(r=>{const same=r.origin===origin;return `<article data-industrial-case="${r.id}" data-import-country="${r.import_country}"><h3>${country(r.origin)}산 → ${country(r.import_country)} 수입 · ${r.duty}</h3><p><b>${esc(r.case_id)} · ${esc(r.procedure_label)}</b></p>${same?'':`<p class="ts-unverified">현재 선택 원산지와 다름 · 관련 사건 참고만</p>${originControls?`<button type="button" data-ad-related-origin="${r.origin}">${country(r.origin)}산 자료 선택</button>`:`<small>위 제품 원산지 입력에서 ${country(r.origin)}을 선택하면 일치 여부를 확인할 수 있습니다.</small>`}`}<p class="ts-help">${esc(r.note)}</p>${r.reported_values?.length?`<ul data-historical-recommendation>${r.reported_values.map(v=>`<li>${esc(v.entity)} · ${v.amount.toLocaleString('en-US',{minimumFractionDigits:2})} ${esc(v.unit)} · 과거 ${v.kind.includes('reference_price')?'기준가격 권고':'종량세 권고'} / ${r.stage==='historical_measure_termination_reported'?'기존 조치 종료 보고':'현행 부과 미확인'}</li>`).join('')}</ul>`:''}${r.alleged_values?.length?`<p data-petitioner-allegation>신청인 제시 덤핑률 ${r.alleged_values[0].amount.toFixed(2)}% · 개시보고의 주장 / 확정·잠정 관세 아님</p>`:''}${r.company_roles?.map(v=>`<p data-company-proceeding-role>${esc(v.name)} · 공식 기록 역할: 국내수입자 답변서 제출 ${v.submitted} / 중국 생산자·수출자 세율 아님</p>`).join('')||''}${r.por_start?`<small>POR ${r.por_start} ~ ${r.por_end}</small>`:''}${same?`<div class="ts-ad-stages" aria-label="${country(r.import_country)} 사건 확인 단계">${r.steps.map(([label,state,date])=>`<p data-evidence-stage="${state}">${state==='confirmed'?'●':'○'} ${esc(label)} · ${date||'근거 미확인'}</p>`).join('')}</div>`:''}<p>${link(r.source)}${r.related_sources.map(s=>' · '+link(s)).join('')}</p><small>자료 확인 ${r.checked_on} · 기업별 세율 적용 미확인 · 자동 세율·단계 계산 미반영</small></article>`;}).join(''):'<p class="ts-unverified">제품 취급 확인 · 해당 제품의 공식 반덤핑 사건 조사 미완료. 판정 대기나 0%가 아닙니다.</p>'}
    ${importRequirementsMarkup(product,origin)}${records.length&&!matched.length?'<p class="ts-help">현재 선택 원산지에 일치하는 확인 사건 없음 · 다른 원산지의 세율을 적용하지 않습니다.</p>':''}</section>`;
}

// Compliance evidence is not a duty quote or an assertion of shipment compliance.
export function industrialImportRequirements(product,origin) {
  if(!INDUSTRIAL_PRODUCTS.some(p=>p.id===product)) return [];
  const rows=[];
  if(product==='methyl-ethyl-ketone') rows.push({id:'kr-mek-precursor',import_country:'KOR',kind:'chemical_precursor_controls',origin_specific:false,status:'official_list_checked_transaction_requirements_unverified',label:'한국 · MEK 원료물질 2군 목록 확인',note:'관세청 자료에 MEK가 원료물질 2군으로 기재되어 있습니다. AD와 별개의 기록·거래 관리 요건 확인 대상입니다. 1군 수출입승인 규정을 2군에 그대로 적용하지 않습니다. 혼합물·거래별 예외·신고 요건은 추가 확인이 필요하며 수입금지로 판정하지 않습니다.',source:source('관세청 · 원료물질 및 최대거래량 / 시행령 별표8 안내','https://customs.go.kr/cclss/cm/cntnts/cntntsView.do?cntntsId=964&mi=3253')});
  if(origin==='CHN') rows.push({id:'us-section301-check',import_country:'USA',kind:'additional_tariff_scope_check',origin_specific:true,status:'framework_checked_hts_exclusions_unverified',label:'미국 · Section 301 품목·제외조건 대조',note:'중국산 적용 목록과 제외 절차가 별도로 있습니다. 정확한 HTS·통관일·유효한 제외를 확인해야 합니다. 이 제품의 적용 여부와 현행 추가세율은 미확인이며 AD/CVD와 자동 합산하지 않습니다.',source:source('USTR · China Section 301 Tariff Actions and Exclusion Process','https://ustr.gov/issue-areas/enforcement/section-301-investigations/tariff-actions')});
  if(origin==='CHN') rows.push({id:'us-uflpa',import_country:'USA',kind:'conditional_import_prohibition',origin_specific:true,status:'legal_basis_checked_shipment_unverified',label:'미국 · UFLPA 공급망 확인',note:'신장 지역에서 전부·일부 생산되거나 법률상 지정 목록의 기업이 생산한 물품은 수입금지 추정 대상입니다. 모든 중국산의 일괄 금지가 아닙니다. 실제 공급망·현행 지정 목록 대조는 미완료이며 조선내화·후성의 위반을 확인한 것이 아닙니다.',source:source('Public Law 117-78 §3 · 수입금지 추정과 예외','https://www.govinfo.gov/content/pkg/PLAW-117publ78/html/PLAW-117publ78.htm')});
  if(INDUSTRIAL_PRODUCTS.find(p=>p.id===product).family==='chemicals') rows.push({id:'us-tsca',import_country:'USA',kind:'chemical_import_compliance',origin_specific:false,status:'framework_checked_substance_conditions_unverified',label:'미국 · TSCA 화학물질 수입 요건',note:'중국 전용 관세가 아닙니다. 적용 대상 화학물질은 TSCA 적합성 인증과 해당 물질의 목록·신규용도·개별 규칙 등을 확인해야 합니다. CAS·조성·용도·거래별 적합성 검증은 미완료입니다.',source:source('EPA · TSCA Requirements for Importing Chemicals','https://www.epa.gov/tsca-import-export-requirements/tsca-requirements-importing-chemicals')});
  return rows.map(r=>({...r,checked_on:INDUSTRIAL_CHECKED_ON,calculation_ready:false,rate_pct:null}));
}
function importRequirementsMarkup(product,origin) {
 const rows=industrialImportRequirements(product,origin);
 return rows.length?`<details data-industrial-import-requirements><summary>관련 수입 규제 · 거래별 적용 확인</summary>${rows.map(r=>`<article><h3>${esc(r.label)}</h3><p class="ts-help">${esc(r.note)}</p>${link(r.source)}<small> · 법적 틀 확인 / 실제 거래 적용 미확인 · 세율 계산 제외</small></article>`).join('')}</details>`:'';
}


// A bounded search miss is a research result, never a legal exemption.
export function industrialResearchStatus(product,origin,importCountry) {
  const records=origin?industrialCases(product,origin,importCountry):[], comparisons=industrialComparisonEvidence(product,importCountry);
  let state='not_researched', label='사건 조사 미완료', note='이 품목·원산지·수입국 조합의 공식 사건 조사 기록이 충분하지 않습니다. 규제 없음·0%·판정 대기로 판단하지 않습니다.';
  let sources=records.flatMap(r=>[r.source,...r.related_sources]);
  if(records.length) {
    if(records.every(r=>r.stage==='measure_terminated')) {state='specific_measure_terminated';label='해당 조치 종료 공고 확인';}
    else if(records.every(r=>r.stage==='historical_measure_termination_reported')) {state='specific_measure_termination_reported';label='과거 조치 종료 · WTO 공식 보고 확인';}
    else if(records.every(r=>r.stage==='historical_recommendation')) {state='historical_recommendation_only';label='과거 권고 확인 · 현행 부과 미확인';}
    else if(records.every(r=>r.stage==='investigation_in_progress')) {state='official_investigation_identified';label='공식 조사 개시 확인 · 부과 미확인';}
    else {state='official_case_identified';label='공식 사건 확인 · 기업별 현행 세율 미확인';}
    note=records.map(r=>r.note).join(' ');
  } else if(origin==='CHN'&&['methyl-ethyl-ketone','dimethylformamide'].includes(product)&&['USA','KOR'].includes(importCountry)&&comparisons.length>0&&comparisons.every(verifiedEmptyComparison)) {
    state='bounded_search_no_confirmed_case';label=importCountry==='KOR'?'KTC 공식 품명검색 · 대응 사건 미발견':'USITC 공식 사건검색 · 대응 사건 미발견';
    note=importCountry==='USA'?'2026-11-05 USITC IDS 공개 사건 검색에 영문명·동의어·CAS를 직접 대조해 대응 사건을 찾지 못했습니다. 내화벽돌 검색 5건으로 양성 대조와 JSON 결과·검색어 반영을 검증했습니다. 이 검색은 모든 원산지의 사건 자료이며 현재 중국산 상무부 명령 전수 판정이 아닙니다. ACCESS 결과 오류로 현행 전체 명령·예치 지침 대조는 미완료입니다. USITC XLS는 실제 기준일이 2014-11-03이므로 현재 판정에서 제외했습니다. 규제 없음·면제·0%·정부 판정 대기를 뜻하지 않습니다.':'2026-11-05 KTC 내부 품목 검색에 한글명·약어·부분어를 직접 전달하고 검색어 반영 및 빈 결과를 확인했습니다. 초산에틸 검색에서 실제 사건이 나오는 대조도 수행했습니다. 현행 모든 부과 규칙·제품 범위 전수 검토는 아니며 규제 없음·면제·0%·판정 대기를 뜻하지 않습니다.';
    sources=comparisons.filter(verifiedEmptyComparison).map(r=>r.source);
  }
  return {state,label,note,checked_on:state==='not_researched'?null:(comparisons.length>0&&comparisons.every(verifiedEmptyComparison)||records.some(r=>r.checked_on===INDUSTRIAL_COMPARISON_CHECKED_ON))?INDUSTRIAL_COMPARISON_CHECKED_ON:INDUSTRIAL_CHECKED_ON,absence_confirmed:false,rate_pct:null,calculation_ready:false,sources};
}
function researchStatusMarkup(product,origin) {
 const markets=[...new Set(['USA','KOR',...industrialCases(product,origin).map(r=>r.import_country)])];
 return `<details data-industrial-research-status><summary>수입국별 확인 상태 · 미조사와 종료 구분</summary><p class="ts-help">선택 원산지 ${esc(country(origin)||'미선택')}. 해당 조치의 종료는 다른 규제·신규 조치까지 없다는 뜻이 아닙니다.</p><table><thead><tr><th>수입국</th><th>확인 상태</th><th>검토 범위·남은 자료</th></tr></thead><tbody>${markets.map(m=>{const r=industrialResearchStatus(product,origin,m);return `<tr data-research-state="${r.state}"><td>${country(m)}</td><td>${esc(r.label)}<br><small>${r.checked_on||'검토일 미기록'}</small></td><td><small>${esc(r.note)} ${r.sources.map(link).join(' · ')}</small></td></tr>`;}).join('')}</tbody></table></details>`;
}


// Query results describe only the named official search, not universal legal absence.
const ktcQuery = term => ({title:`KTC 공식 품목 검색 · ${term}`,url:`https://www.ktc.go.kr/proInvestList.do?invstg_prd_name=${encodeURIComponent(term)}&sel_invstg_type_code=10100001`});
const KTC_SEARCH_HASHES = {"DMF": "df3891f516e7470ba34f4ec6831990ff33f64f0a7c1af950faa7e542674d4048", "MEK": "6be51d8b557d7313b22eaa0ac623cdbe7c9a1d9769f514aebafcfd5b3301907c", "부탄온": "022708da03ebef56076101a9088471a05827f104951de8306a1f8148329015ff", "케톤": "207524bb0b29b72e054b5d83b92dffd74120afa3d2e0bb42c70c306c7abffe24", "포름": "52ed6424b6b36b97263ea37054273b614974b0d626502610d9b41804bd9e1db1", "디메틸포름아미드": "b257c2cb22bf324f60f82cf0e88a6504ca076a0adb1d2971a6a4951ada7c6f40", "메틸에틸케톤": "160ddb913b22f64d45615e67393b426256dac0ff0a2415e26ea08d5e51bc1ebd"};
export const INDUSTRIAL_COMPARISON_EVIDENCE = [
 ...[['methyl-ethyl-ketone',['메틸에틸케톤','MEK','케톤','부탄온']],['dimethylformamide',['디메틸포름아미드','DMF','포름']]].flatMap(([product,terms])=>terms.map(term=>({product,import_country:'KOR',source:ktcQuery(term),checked_on:INDUSTRIAL_COMPARISON_CHECKED_ON,query:term,query_echo_verified:true,http_status:200,expected_table_present:true,empty_result_message:true,result_count:0,positive_control:{query:'초산에틸',observed_first_page_rows:5},status:'official_search_no_match',sha256:KTC_SEARCH_HASHES[term],absence_confirmed:false}))),
];
export function industrialComparisonEvidence(product,importCountry='KOR') {
 return [...INDUSTRIAL_COMPARISON_EVIDENCE,...USITC_COMPARISON_EVIDENCE].filter(r=>r.product===product&&r.import_country===importCountry).map(r=>structuredClone(r));
}
export const INDUSTRIAL_SOURCE_EXCLUSIONS = [{
 source:source('USITC · AD/CVD Orders (XLS) / 기준일 확인 후 현행 대조 제외','https://www.usitc.gov/sites/default/files/import_injury/documents/orders_2.xls'),
 checked_on:INDUSTRIAL_COMPARISON_CHECKED_ON,data_as_of:'2014-11-03',status:'excluded_stale',reason:'Orders·Revocations 시트의 실제 기준일이 2014년입니다. 현재 사건 부재나 현행 세율 판정에 사용하지 않습니다.'
}];

export function verifiedEmptyComparison(r) {
 return r?.status==='official_search_no_match'&&r.http_status===200&&r.query_echo_verified===true&&(r.expected_table_present===true&&r.empty_result_message===true||r.expected_result_structure===true&&r.empty_cases_array===true)&&r.result_count===0&&r.positive_control?.observed_first_page_rows>0;
}

const USITC_QUERY_RECEIPTS = [{"product": "methyl-ethyl-ketone", "query": "methyl ethyl ketone", "sha256": "46e3fc83715860c78283a5fef6e82d89a01837e555d47076802bf5f8785680ce"}, {"product": "dimethylformamide", "query": "dimethyl formamide", "sha256": "e8c72dca7f8c0e78400e485ff01c867306c75b8355dd50dcff1e3f5f46ff7efe"}, {"product": "methyl-ethyl-ketone", "query": "78-93-3", "sha256": "943b74258f0fb760d1ff51be10e4259d11b050c77a3ddc6eebe2bf9d52089a33"}, {"product": "dimethylformamide", "query": "dimethylformamide", "sha256": "abcb45354ec197d6f85cc3293db8467ed609a8a9667dd0a309b6431a2a1e825d"}, {"product": "dimethylformamide", "query": "68-12-2", "sha256": "a606168589dab273f34bf56cdcedaa9cb1de2cdcc015bc5e1c890b4e4525a048"}, {"product": "methyl-ethyl-ketone", "query": "2-butanone", "sha256": "59708603c4187564e1bb04e3bf3ebdfbadd70249d9d0aad5cc5c90d64e5b6651"}];
export const USITC_COMPARISON_EVIDENCE = USITC_QUERY_RECEIPTS.map(r=>({...r,import_country:'USA',checked_on:INDUSTRIAL_COMPARISON_CHECKED_ON,source:{title:`USITC IDS 공식 사건검색 · ${r.query}`,url:`https://ids.usitc.gov/case?type=basic&query=${encodeURIComponent(r.query)}`},query_echo_verified:true,http_status:200,expected_result_structure:true,empty_cases_array:true,result_count:0,positive_control:{query:'magnesia carbon bricks',observed_first_page_rows:5},status:'official_search_no_match',absence_confirmed:false}));
export const INDUSTRIAL_IDENTITIES = {
 'methyl-ethyl-ketone':{cas:'78-93-3',aliases:['2-Butanone','Methyl ethyl ketone','Ethyl methyl ketone','MEK','Methyl acetone'],source:source('CDC/NIOSH · 2-Butanone 물질 식별','https://www.cdc.gov/niosh/npg/npgd0069.html')},
 'dimethylformamide':{cas:'68-12-2',aliases:['Dimethylformamide','Dimethyl formamide','N,N-Dimethylformamide','DMF'],source:source('CDC/NIOSH · Dimethylformamide 물질 식별','https://www.cdc.gov/niosh/npg/npgd0226.html')},
};
