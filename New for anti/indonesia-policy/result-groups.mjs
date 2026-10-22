export const resultGroups=[
 {key:'law',label:'국가 법률'},
 {key:'executive',label:'대통령 명령·중앙 결정'},
 {key:'regulation',label:'중앙 행정규정·기타'},
 {key:'local',label:'지방 조례·규정'},
];
export function resultGroup(d){
 if(['provincial','regency','city'].includes(d.issuer_level))return 'local';
 if(d.issuer_level!=='national')return 'unknown';
 if(['UU','Perppu'].includes(d.document_type))return 'law';
 if(['Perpres','Inpres','Kepmen','Keputusan'].includes(d.document_type))return 'executive';
 return 'regulation';
}
export function groupedResults(items){
 const groups=[...resultGroups,{key:'unknown',label:'분류 확인 필요'}];
 return groups.map(g=>({...g,items:items.filter(d=>resultGroup(d)===g.key)})).filter(g=>g.key!=='unknown'||g.items.length);
}
