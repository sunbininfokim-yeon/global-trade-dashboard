// Product evidence and proceeding evidence are independent. A trader is not
// automatically the investigated producer/exporter. No executable duty rates.
export const INDUSTRIAL_CHECKED_ON = '2026-11-04';
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
const brickAD = fr('2026-22523','2026-11-04','Commerce · 마그카본 벽돌 AD 제3차 일몰 최종결과');
const brickCVD = fr('2026-22529','2026-11-04','Commerce · 중국산 마그카본 벽돌 CVD 제3차 일몰 최종결과');
const rescission = fr('2026-16051','2026-08-06','Commerce · 중국산 마그카본 벽돌 2024~2025 재심 철회');
const acetone = fr('2026-11549','2026-06-09','Commerce · 한국산 아세톤 2024~2025 최종결과');
const ktc = source('한국 무역위원회 · 진행 중 반덤핑 조사 목록','https://www.ktc.go.kr/proInvestList.do');
export const INDUSTRIAL_CASES = [
  {id:'us-cn-mcb-ad', product:'magnesia-carbon-bricks', import_country:'USA', origin:'CHN', duty:'AD', case_id:'A-570-954', stage:'commerce_sunset_final', procedure_label:'상무부 제3차 일몰재심 최종결과 공표', date:'2026-11-04', source:brickAD, related_sources:[rescission], rate_pct:null,
    steps:[['상무부 일몰 최종결과','confirmed','2026-11-04'],['동일 차수 ITC 결과','unknown',null],['동일 차수 명령 유지·철회','unknown',null]],
    note:'일몰재심의 재발 가능성 판단입니다. 현재 예치율·최종 확정 관세·기업별 미래 세율이 아닙니다. 8/6의 연례재심 철회는 명령 철회가 아니며 공고는 예치율 변경 없음으로 명시합니다. 조선내화 또는 중국 관계사와 공고 법인의 동일성은 미확인입니다.'},
  {id:'us-cn-mcb-cvd', product:'magnesia-carbon-bricks', import_country:'USA', origin:'CHN', duty:'CVD', case_id:'C-570-955', stage:'commerce_sunset_final', procedure_label:'상무부 제3차 CVD 일몰재심 최종결과 공표', date:'2026-11-04', source:brickCVD, related_sources:[], rate_pct:null,
    steps:[['상무부 CVD 일몰 최종결과','confirmed','2026-11-04'],['동일 차수 ITC 결과','unknown',null],['동일 차수 명령 유지·철회','unknown',null]],
    note:'AD와 별도 CVD 사건입니다. 공고의 일몰 보조금률은 계산 예치율로 연결하지 않습니다. 조선내화의 한국산·모든 내화재 또는 다른 법인에 이식하지 않습니다.'},
  {id:'kr-cn-ethyl-acetate', product:'ethyl-acetate', import_country:'KOR', origin:'CHN', duty:'AD', case_id:'구제23-2026-6호', stage:'investigation_in_progress', procedure_label:'한국 무역위원회 목록상 조사실행', date:'2026-08-18', date_kind:'investigation_initiated', source:ktc, related_sources:[], rate_pct:null,
    steps:[['조사 개시','confirmed','2026-08-18'],['예비판정·잠정조치','unknown',null],['최종판정','unknown',null],['부과·가격약속','unknown',null]],
    note:'2026-11-04 확인한 진행 목록에 개시일과 조사실행이 기재되어 있습니다. 상세 개시공고·대상 순도/HS·생산자·공급자·최신 잠정/최종 세율은 미확보입니다. 후성은 제품 취급만 확인했으며 제소인·피소 수출자·개별 세율 보유 법인으로 확인한 것이 아닙니다. 이 한국 수입 사건을 미국 예치 계산에 사용하지 않습니다.'},
  {id:'us-kr-acetone', product:'acetone', import_country:'USA', origin:'KOR', duty:'AD', case_id:'A-580-899', stage:'administrative_review_final', procedure_label:'2024~2025 POR 상무부 최종결과 공표', date:'2026-06-09', por_start:'2024-03-01', por_end:'2025-02-28', source:acetone, related_sources:[], rate_pct:null,
    steps:[['해당 POR 최종결과','confirmed','2026-06-09'],['거래별 현행 예치 지침','unknown',null],['소송·관세 정산','unknown',null]],
    note:'이 공고의 개별조사 법인은 Kumho P&B Chemicals, Inc.입니다. 최종 마진표·예치 조항이 있어도 후성의 제조사·수출자 조합을 확인하지 않고 적용하지 않습니다. 중국산 아세톤이나 초산에틸로 이식하지 않습니다. 최신 세그먼트 전수 검토·후성별 적용은 미확인입니다.'},
].map(r=>({...r,checked_on:INDUSTRIAL_CHECKED_ON,calculation_ready:false,company_application:'unconfirmed'}));
export function industrialCases(product, origin=null, importCountry=null) {
  return INDUSTRIAL_CASES.filter(c=>c.product===product&&(!origin||c.origin===origin)&&(!importCountry||c.import_country===importCountry)).map(c=>structuredClone(c));
}
export function industrialUSVerification(product,origin) {
  const p=INDUSTRIAL_PRODUCTS.find(p=>p.id===product); if(!p)return null;
  const records=industrialCases(product,origin,'USA');
  return {checked_on:INDUSTRIAL_CHECKED_ON,ad:{country:origin,import_country:'USA',status:records.length?'industrial_us_case_reviewed':'industrial_case_not_reviewed',label:records.length?'미국 수입 공식 사건 확인 · 기업별 적용 미확정':'기업 취급 제품 확인 · 미국 해당 원산지 사건 미확인',rate_pct:null,case_ids:records.map(r=>r.case_id),sources:[p.source,...records.flatMap(r=>[r.source,...r.related_sources])],note:records.length?records.map(r=>r.note).join(' '):'기업 제품 자료만 확인했습니다. 미국의 해당 원산지 AD/CVD 사건 조사·최신 적용은 미완료이며 정부 판정 대기·면제·0%를 뜻하지 않습니다.',records}};
}
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const country=c=>({USA:'미국',KOR:'한국',CHN:'중국',JPN:'일본',VNM:'베트남'})[c]||c;
const link=s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`;
export function industrialEvidenceMarkup(product,origin=null,{originControls=true}={}) {
  const p=INDUSTRIAL_PRODUCTS.find(p=>p.id===product); if(!p)return '';
  const records=industrialCases(product),matched=records.filter(r=>r.origin===origin);
  return `<section class="ts-ad-notices" data-industrial-evidence><h2>수입국별 관련 사건</h2><p class="ts-help">기업의 취급·생산 품목과 실제 반덤핑 적용은 별개입니다. 현재 원산지 ${esc(country(origin)||'미선택')} · 자료 확인 ${INDUSTRIAL_CHECKED_ON}. 미국과 한국의 조사·부과 절차를 합치지 않습니다.</p>${link(p.source)}
    ${records.length?records.map(r=>{const same=r.origin===origin;return `<article data-industrial-case="${r.id}" data-import-country="${r.import_country}"><h3>${country(r.origin)}산 → ${country(r.import_country)} 수입 · ${r.duty}</h3><p><b>${esc(r.case_id)} · ${esc(r.procedure_label)}</b></p>${same?'':`<p class="ts-unverified">현재 선택 원산지와 다름 · 관련 사건 참고만</p>${originControls?`<button type="button" data-ad-related-origin="${r.origin}">${country(r.origin)}산 자료 선택</button>`:`<small>위 제품 원산지 입력에서 ${country(r.origin)}을 선택하면 일치 여부를 확인할 수 있습니다.</small>`}`}<p class="ts-help">${esc(r.note)}</p>${r.por_start?`<small>POR ${r.por_start} ~ ${r.por_end}</small>`:''}${same?`<div class="ts-ad-stages" aria-label="${country(r.import_country)} 사건 확인 단계">${r.steps.map(([label,state,date])=>`<p data-evidence-stage="${state}">${state==='confirmed'?'●':'○'} ${esc(label)} · ${date||'근거 미확인'}</p>`).join('')}</div>`:''}<p>${link(r.source)}${r.related_sources.map(s=>' · '+link(s)).join('')}</p><small>기업별 적용 미확인 · 자동 세율·단계 계산 미반영</small></article>`;}).join(''):'<p class="ts-unverified">제품 취급 확인 · 해당 제품의 공식 반덤핑 사건 조사 미완료. 판정 대기나 0%가 아닙니다.</p>'}
    ${records.length&&!matched.length?'<p class="ts-help">현재 선택 원산지에 일치하는 확인 사건 없음 · 다른 원산지의 세율을 적용하지 않습니다.</p>':''}</section>`;
}
