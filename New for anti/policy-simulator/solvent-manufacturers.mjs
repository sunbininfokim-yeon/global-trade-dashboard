// Product/manufacturer evidence is not a shipment origin or an executable duty.
export const SOLVENT_MANUFACTURER_CHECKED_ON = '2026-11-05';
const source=(title,url)=>({title,url,checked_on:SOLVENT_MANUFACTURER_CHECKED_ON});
export const KUMHO_ACETONE = source('금호피앤비화학 · 아세톤 제조·제품 규격','https://www.kpb.co.kr/kor/product/acetone');
export const KUMHO_MIBK = source('금호피앤비화학 · MIBK 제조·제품 규격','https://www.kpb.co.kr/kor/product/mibk');
export const ISU_IPA = source('이수스페셜티케미컬 · IPA 제조·CAS·제품 규격','https://www.isuspecialtychemical.com/kor/business/getBiz1005Html.do');
export const SHENGHUA_DMC = source('시다승화 · DMC 제품·CAS','https://www.sinodmc.com/solvent/229.html');
export const LUXI_DISCLOSURE = source('루시화학 · 2025 연차보고서 pp.12~13 / DMF 생산법인','https://static.cninfo.com.cn/finalpage/2026-04-29/1225240339.PDF');
export const SOLVENT_MANUFACTURERS = [
 {id:'kumho-pnb',name:'금호피앤비화학',official_name:'KUMHO P&B CHEMICALS, INC.',headquarters_country:'KOR',role:'manufacturer',role_label:'제조기업',products:[{product:'acetone',source:KUMHO_ACETONE},{product:'methyl-isobutyl-ketone',source:KUMHO_MIBK}],
  note:'공식 제품 페이지에서 아세톤·MIBK 제조와 규격을 확인했습니다. MEK는 다른 물질입니다. 중국 MIBK 공고의 법인명과 제품을 연결하되 한국산→중국 수입 공고값을 미국 예치율·아세톤·그룹 다른 법인에 이식하지 않습니다. 실제 거래·최신 변경은 별도 확인 대상입니다.'},
 {id:'isu-specialty-chemical',name:'이수스페셜티케미컬',official_name:'주식회사 이수스페셜티케미컬',headquarters_country:'KOR',role:'manufacturer',role_label:'제조기업',products:[{product:'isopropyl-alcohol',source:ISU_IPA}],
  note:'공식 자료의 IPA 제조공정·온산 공장·CAS를 확인했습니다. 원료 아세톤을 이 회사의 제조 제품으로 등록하지 않습니다. 과거 이수화학 명의와 현 법인을 구분하며 인도 2026 개시 공고만으로 이 회사의 개별 조사·덤핑률을 확정하지 않습니다.'},
 {id:'shida-shenghua',name:'시다승화 신소재 그룹',official_name:'石大胜华新材料集团股份有限公司 · 공식 사이트 표기',headquarters_country:'CHN',role:'manufacturer_group',role_label:'제조기업 그룹',products:[{product:'dimethyl-carbonate',source:SHENGHUA_DMC}],
  note:'공식 사이트의 DMC 제품·CAS를 확인한 그룹 프로필입니다. 특정 생산 자회사·실제 수출 법인·거래 원산지와의 동일성은 미확인입니다. 공장·품질등급·명령 범위 없이 그룹 전체에 세율을 부여하지 않습니다.'},
 {id:'liaocheng-luxi-methylamine',name:'랴오청 루시 메틸아민',official_name:'聊城鲁西甲胺化工有限公司',headquarters_country:'CHN',role:'manufacturer',role_label:'공시상 제조법인',products:[{product:'dimethylformamide',source:LUXI_DISCLOSURE}],
  note:'루시화학 2025 연차보고서 pp.12~13에서 이 법인의 DMF 생산 허가·제품을 확인했습니다. 그룹의 판매법인·다른 생산 자회사와 구분합니다. 과거 인도 권고의 영문 법인명과 현재 거래법인의 법적 동일성·현행 부과는 별도 확인 대상입니다. 과거 권고값을 현행 세율로 채우지 않습니다.'},
];
export function solventManufacturers(product){
 return SOLVENT_MANUFACTURERS.filter(m=>m.products.some(p=>p.product===product)).map(m=>structuredClone(m));
}
