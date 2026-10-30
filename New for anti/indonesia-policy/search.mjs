import {officialUrl,documentLinks} from './source-links.mjs';
import {effectLabel,findingLabels} from './legal-effect.mjs';
import {groupedResults,resultGroup} from './result-groups.mjs';
const form=document.querySelector('#search-form'),results=document.querySelector('#results');
const status=document.querySelector('#status'),coverage=document.querySelector('#coverage'),pages=document.querySelector('#pagination');
const dialog=document.querySelector('#detail'),detail=document.querySelector('#detail-content');
const topics={coal:'석탄',nickel_mining:'니켈',palm_oil:'팜유',biofuel:'바이오연료',bauxite:'보크사이트·알루미늄',copper:'구리',tin:'주석',cobalt:'코발트',manganese:'망간',iron_steel:'철광석·철강',silica:'실리카·석영',gold_silver:'금·은',rare_earths:'희토류'};
const streams={upstream:'상류',midstream:'중류',downstream:'하류',trading:'거래'};
const levels={national:'중앙',provincial:'주',regency:'군',city:'시'};
const fields={title:'제목·문서번호',source_text:'출처 본문',catalogue:'분류·기관·지역'};
const regionNames={Banten:'반텐','Jawa Tengah':'중앙자바','Kalimantan Timur':'동칼리만탄',Maluku:'말루쿠','Sulawesi Tengah':'중앙술라웨시','Kabupaten Paser':'파세르군'};
const regionSelect=document.querySelector('#jurisdictions'),levelSelect=form.elements.namedItem('level');
let controller,detailController,serial=0;
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const spinner=()=>node('span',undefined,'spinner');
function sourceLink(url,label){const href=officialUrl(url);if(!href)return node('span','원문 링크 확인 필요');const a=node('a',label);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;}
function appendSources(target,item){
 const links=documentLinks(item);for(const link of links){const a=sourceLink(link.url,link.label);a.dataset.sourceType=link.type;target.append(a);}
 if(!links.some(x=>x.type==='pdf'))target.append(node('span',item.content_kind==='official_text'?'PDF 미확보 · 원문 링크 확인':'원문·PDF 미확보 · 메타데이터만 저장','meta'));
}
function updateGovernmentFilters(resetRegion=false){
 if(resetRegion||levelSelect.value==='national')regionSelect.value='';
 const national=levelSelect.value==='national';regionSelect.disabled=national;document.querySelector('#jurisdiction-filter').hidden=national;
 const descriptions={national:'중앙정부가 발행한 문서만 표시합니다. 지방정부 문서는 포함하지 않습니다.',local:'지방정부(주·군·시)가 발행한 문서만 표시합니다. 중앙정부 문서는 포함하지 않습니다.',provincial:'주정부 발행 문서만 표시합니다.',regency:'군정부 발행 문서만 표시합니다.',city:'시정부 발행 문서만 표시합니다.'};
 document.querySelector('#filter-help').textContent=(descriptions[levelSelect.value]||'중앙·지방정부 발행 문서를 함께 표시합니다.')+(national?'':' 지방 발행지역을 고르면 해당 지역의 지방 문서만 남습니다. 발행지역은 중앙법의 적용지역 판정과 다릅니다.');
}
function badges(item){
 const row=node('div',undefined,'badges');
 const common=item.topics?.includes('cross_sector_business');
 row.append(node('span',common?'공통 사업법규':item.topics?.includes('cross_sector')?'업종 공통 제도':topics[item.primary_stage]||'광물·산업','badge'));
 if(!common&&!item.topics?.includes('cross_sector')){const labels=Object.entries(topics).filter(([key])=>item.topics?.includes(key)).map(([,label])=>label);row.append(node('span',labels.slice(0,3).join(' · ')+(labels.length>3?` 외 ${labels.length-3}개`:''),'badge'));}
 const chain=Object.entries(streams).filter(([key])=>item.topics?.includes('stream_'+key)).map(([,label])=>label);
 row.append(node('span',chain.length?chain.join(' · '):'사업단계 미분류','badge'));
 for(const text of [levels[item.issuer_level]||item.issuer_level,regionNames[item.jurisdiction]||item.jurisdiction,item.content_kind==='official_text'?'원문 확보':'본문 미확보 · 메타데이터'])row.append(node('span',text,'badge'));
 if(item.text_truncated)row.append(node('span','본문 일부 수집 · 원문 링크 확인','badge unverified'));
 if(item.topics?.includes('cross_sector'))row.append(node('span','공통 제도 · 적용대상 별도 확인','badge'));
 row.append(node('span',effectLabel(item.legal_effect),'badge unverified'));return row;
}
function effectDetails(effect){
 const section=node('section');section.append(node('h3','시행·개정·폐지 검토'),node('p',effectLabel(effect),'scope'));
 section.append(node('p','확보한 공식 원문의 검토 범위입니다. 시행일 확인만으로 현재 유효하다고 확정하지 않습니다. 후속 개폐와 개별 사업 적용성은 별도 확인이 필요합니다.','meta'));
 if(effect?.reviewed_at)section.append(node('p',`근거 검토 ${new Date(effect.reviewed_at).toLocaleDateString('ko-KR')}`,'meta'));
 if(effect?.stale_evidence_count)section.append(node('p',`본문 변경으로 이전 효력 근거 ${effect.stale_evidence_count}건을 제외했습니다.`,'meta'));
 if(effect?.transition_review_required)section.append(node('p','경과조치 확인 · 기존 인증·허가·시행규칙 유지 조건을 함께 검토하세요.','scope'));
 for(const f of effect?.findings||[]){const entry=node('details');entry.append(node('summary',`${findingLabels[f.finding_type]||f.finding_type} · ${f.article} · ${f.effective_on||'적용일 미확인'}`),node('p',f.scope_note_ko,'scope'),node('blockquote',f.quote));
  if(f.date_quote)entry.append(node('p',`날짜 근거: ${f.date_quote}`,'meta'));entry.append(sourceLink(f.source_url,'효력 근거 원문'));section.append(entry);
 }
 return section;
}
function ref(item){return `${item.document_type} ${item.document_number}/${item.document_year}`;}
function matchEvidence(item){
 const box=node('details');box.append(node('summary','일치 근거 보기'));for(const m of item.matched_terms||[])box.append(node('p',`${m.term} → ${m.alias} · ${fields[m.field]||m.field}`,'meta'));
 for(const p of item.matched_passages||[]){const section=node('details',undefined,'passage');
  section.append(node('summary',`${p.article} · ${p.total_condition_count}개 조건 중 ${p.matched_condition_count}개 원문 일치`),node('p',p.interpretation_ko,'scope'),node('blockquote',p.quote),sourceLink(p.source_url,'근거 원문'));
  if(p.semantic_similarity>=0.60)section.append(node('p','선택 발췌 의미 연관 후보 · 적용성 판단 아님','meta'));
  box.append(section);
 }
 return box;
}
const roleNames={miner:'광산',smelter:'제련·정련',trader:'무역',plantation:'농장',bioenergy:'바이오에너지',manufacturer:'제조',investor:'투자',transporter:'운송'};
const permitNames={IUP:'IUP',IUPK:'IUPK',IUPK_continuation:'계약·협정 연장 IUPK',industrial_license:'산업 허가',governor_transport_permission:'주지사 운송 허가'};
function citation(id){const m=/^idn-(pp|perpres|uu)-(\d+)-(\d+)$/.exec(id);return m?`${m[1].toUpperCase()} ${m[2]}/${m[3]}`:id;}
async function appendContext(id,signal,target){
 try{
  const r=await fetch(`/api/idn/context/${encodeURIComponent(id)}`,{signal}),context=await r.json();
  if(!r.ok||context.country!=='IDN')throw Error('Unavailable context');
  if(signal.aborted)return;
  const section=node('section',undefined,'review-context');section.append(node('h3','관계·사업 검토 근거'),node('p','저장된 원문 발췌를 검토한 범위입니다. 현행 효력·개별 사업 적용성과 지원 자격은 미확인입니다.','meta'));
  if(context.stale_evidence_count)section.append(node('p',`본문 버전 변경으로 이전 근거 ${context.stale_evidence_count}건을 제외했습니다.`,'meta'));
  for(const rel of context.relations||[]){const outgoing=rel.document_id===id,other=outgoing?rel.target_id:rel.document_id;
   const relationName={amends:'일부 개정 문구 확인',repeals:'폐지 문구 확인',implements:'시행 근거 문구 확인'}[rel.relation_type]||'관계 문구 확인';
   const entry=node('details');entry.append(node('summary',`${outgoing?citation(other):rel.source_title_ko} · ${relationName} · ${rel.article}`),node('p',rel.interpretation_ko,'scope'),node('blockquote',rel.quote),sourceLink(rel.source_url,'관계 근거 원문'));
   if(!outgoing||rel.target_stored){const b=node('button','관련 문서 보기');b.type='button';b.addEventListener('click',()=>showDetail(other));entry.append(b);}else entry.append(node('p','대상 법령 본문 미확보 · 관계 인용만 확인','meta'));
   section.append(entry);
  }
  for(const scope of context.applicability||[]){const entry=node('details');entry.append(node('summary',`${scope.article} · 사업 검토범위`),node('p',scope.interpretation_ko,'scope'));
   entry.append(node('p',`사업자: ${scope.operator_roles.map(x=>roleNames[x]||x).join(' · ')||'미분류'} · 허가: ${scope.permit_types.map(x=>permitNames[x]||x).join(' · ')||'별도 확인'}`,'meta'));
   entry.append(node('p',scope.geographic_scope==='national_framework'?'지역: 중앙 공통 제도 검토 · 개별 적용성 미확인':`지역: ${scope.applicable_regions.map(x=>regionNames[x]||x).join(' · ')||'미확인'}`,'meta'),node('blockquote',scope.quote),sourceLink(scope.source_url,'검토 근거 원문'));section.append(entry);
  }
  if(!context.relations?.length&&!context.applicability?.length)section.append(node('p','이 문서의 관계·사업범위는 아직 검토되지 않았습니다. 규정이 없거나 적용되지 않는다는 뜻은 아닙니다.','meta'));
  target.replaceChildren(section);
 }catch(e){if(e.name!=='AbortError'&&!signal.aborted)target.replaceChildren(node('p','관계·사업 검토 근거를 불러오지 못했습니다. 원문 자료는 아래에서 확인하세요.','meta'));}
}
function card(item){
 const e=node('article');e.dataset.documentId=item.document_id;e.append(badges(item),node('h2',item.title_ko),node('p',item.title,'original'),node('p',`${ref(item)} · ${item.issuer_name}`,'meta'));
 if(item.semantic_similarity>=0.60)e.append(node('p','문서개요 의미 연관 후보 · 적용성 판단 아님','matches'));
 if(item.total_condition_count){e.append(node('p',`${item.total_condition_count}개 조건 중 ${item.matched_condition_count}개 일치${item.matched_condition_count<item.total_condition_count?' · 일부 조건만 일치':''}`,'matches'),matchEvidence(item));}
 e.append(node('p',item.content_kind==='official_metadata'?'공식 카탈로그를 확보했습니다. 원문 본문·부속서는 별도 확인이 필요합니다.':item.excerpt,'excerpt'));
 if(item.content_observed_at)e.append(node('p',`자료 확인 ${new Date(item.content_observed_at).toLocaleDateString('ko-KR')} · 문서 연도 ${item.document_year}`,'meta'));
 const actions=node('div',undefined,'actions'),button=node('button','세부사항');button.type='button';button.addEventListener('click',()=>showDetail(item.document_id));
 actions.append(button);appendSources(actions,item);e.append(actions);return e;
}
async function showDetail(id){
 detailController?.abort();detailController=new AbortController();const signal=detailController.signal;
 detail.replaceChildren(node('p','문서를 불러오는 중입니다.'));detail.firstChild.append(spinner());if(!dialog.open)dialog.showModal();
 try{
  const r=await fetch(`/api/idn/documents/${encodeURIComponent(id)}`,{signal}),d=await r.json();
  if(!r.ok)throw Error(d.error||'문서를 불러오지 못했습니다.');
  if(d.country!=='IDN')throw Error('국가별 데이터 검증에 실패했습니다.');
  const v=d.version;detail.replaceChildren(node('h2',d.title_ko),node('p',d.title,'original'),badges({...d,content_kind:v.content_kind,text_truncated:v.text_truncated}),node('p',`${ref(d)} · ${d.issuer_name}`,'meta'),node('p','수집 범위·검토 사항','meta'),node('p',d.scope_note,'scope'));
  detail.append(node('p',`자료 확인: ${new Date(v.observed_at).toLocaleString('ko-KR')} · 한국어 제목은 번역·정리 제목입니다.`,'meta'));
  detail.append(effectDetails(d.legal_effect));
  const links=node('div',undefined,'actions');appendSources(links,{...d,content_kind:v.content_kind,text_source_url:v.text_source_url});detail.append(links);
  const context=node('div');detail.append(context);void appendContext(id,signal,context);
  detail.append(node('h3',v.content_kind==='official_metadata'?'공식 메타데이터':'수집한 원문 자료'));
  if(v.text_truncated)detail.append(node('p','저장 길이 제한으로 일부만 확보한 본문입니다.','badge unverified'));
  detail.append(node('pre',v.text_content));
 }catch(e){if(e.name!=='AbortError')detail.replaceChildren(node('p',e.message));}
}
document.querySelector('#close-detail').addEventListener('click',()=>{detailController?.abort();dialog.close();});
dialog.addEventListener('close',()=>detailController?.abort());
function parameters(offset=0){const p=new URLSearchParams();for(const [key,value] of new FormData(form))if(String(value).trim())p.set(key,String(value).trim());p.set('offset',String(offset));return p;}
async function search(offset=0,writeHistory=true){
 controller?.abort();controller=new AbortController();const token=++serial;
 const p=parameters(offset);if(writeHistory)history.replaceState(null,'',`${location.pathname}?${p}`);
 status.replaceChildren('검색 중입니다.',spinner());results.replaceChildren();pages.replaceChildren();
 try{
  const r=await fetch(`/api/idn/search?${p}`,{signal:controller.signal}),data=await r.json();
  if(!r.ok)throw Error(data.error||'검색하지 못했습니다.');if(data.country!=='IDN')throw Error('국가별 데이터 검증에 실패했습니다.');if(token!==serial)return;
  const semanticControl=form.elements.namedItem('mode');semanticControl.disabled=data.semantic_enabled!==true;
  semanticControl.title=semanticControl.disabled?'이 서버는 문서개요 의미검색을 활성화하지 않았습니다.':'문서 개요 기반 검색이며 전체 조문 검색이 아닙니다.';
  coverage.textContent=`저장 문서 ${data.coverage.documents}건 · 수집 실패 이력이 있는 출처 ${data.coverage.held_sources}건 · 문서개요 임베딩 ${data.coverage.embedded_documents||0}건 · 시범 수집 중`;
  const chosen=regionSelect.value||p.get('jurisdiction')||'';
  regionSelect.replaceChildren(new Option('전체',''),...data.jurisdictions.map(j=>new Option(regionNames[j]?`${regionNames[j]} (${j})`:j,j)));
  if(chosen&&!data.jurisdictions.includes(chosen))regionSelect.append(new Option(`${chosen} · 현재 자료 없음`,chosen));regionSelect.value=chosen;
  status.textContent=data.total?`${data.total}건 검색됨 · ${data.search_mode==='hybrid_overview'?'키워드 + 문서개요 의미검색':'키워드·동의어 검색'}`:'저장된 자료에서 일치하는 문서를 찾지 못했습니다. 조건을 줄이거나 품목을 선택해 보세요.';
  // Compact list keeps the server order; desktop sections reuse the same cards.
  const desktop=node('div',undefined,'grouped-results');
  for(const group of groupedResults(data.items)){
   const section=node('section',undefined,'result-group');section.dataset.group=group.key;
   section.append(node('h2',`${group.label} · 현재 페이지 ${group.items.length}건`,'group-heading'));
   section.append(...group.items.map(card));
   if(!group.items.length)section.append(node('p','현재 페이지에 해당 유형이 없습니다.','meta'));
   desktop.append(section);
  }
  const compact=node('div',undefined,'compact-results');
  compact.append(...data.items.map(item=>{const e=card(item);e.dataset.group=resultGroup(item);return e;}));
  results.replaceChildren(desktop,compact);
  for(const [label,next,enabled] of [['이전',offset-20,offset>0],['다음',offset+20,offset+20<data.total]])if(enabled){const b=node('button',label);b.type='button';b.addEventListener('click',()=>search(next));pages.append(b);}
 }catch(e){if(e.name!=='AbortError'&&token===serial){status.textContent=e.message;coverage.textContent='연결 오류로 결과를 확인하지 못했습니다.';}}
}
const initial=new URLSearchParams(location.search);for(const [key,value] of initial){const control=form.elements.namedItem(key);if(!control)continue;if(control.type==='checkbox')control.checked=key==='mode'?value==='hybrid':value==='all';else if(key==='jurisdiction'){control.append(new Option(value,value));control.value=value;}else control.value=value;}
document.querySelector('#reset-filters').addEventListener('click',()=>{form.reset();updateGovernmentFilters(true);search();});
for(const button of document.querySelectorAll('[data-query]'))button.addEventListener('click',()=>{form.reset();form.elements.q.value=button.dataset.query;updateGovernmentFilters(true);search();});
form.addEventListener('submit',e=>{e.preventDefault();search();});form.addEventListener('change',e=>{if(e.target.name!=='q'){updateGovernmentFilters(['level','topic'].includes(e.target.name));search();}});
updateGovernmentFilters();search(Number(initial.get('offset'))||0);
