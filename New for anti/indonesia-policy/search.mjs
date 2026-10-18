import {officialUrl,documentLinks} from './source-links.mjs';
const form=document.querySelector('#search-form'),results=document.querySelector('#results');
const status=document.querySelector('#status'),coverage=document.querySelector('#coverage'),pages=document.querySelector('#pagination');
const dialog=document.querySelector('#detail'),detail=document.querySelector('#detail-content');
const topics={coal:'석탄',nickel_mining:'니켈·광산',palm_oil:'팜유',biofuel:'바이오연료'};
const levels={national:'중앙',provincial:'주',regency:'군',city:'시'};
const fields={title:'제목·문서번호',source_text:'출처 본문',catalogue:'분류·기관·지역'};
const regionNames={Banten:'반텐','Jawa Tengah':'중앙자바','Kalimantan Timur':'동칼리만탄',Maluku:'말루쿠','Sulawesi Tengah':'중앙술라웨시','Kabupaten Paser':'파세르군'};
const regionSelect=document.querySelector('#jurisdictions'),levelSelect=form.elements.namedItem('level');
let controller,detailController,serial=0;
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
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
 const row=node('div',undefined,'badges');for(const text of [topics[item.primary_stage],levels[item.issuer_level],item.jurisdiction,item.content_kind==='official_text'?'원문 자료':'메타데이터'])row.append(node('span',text,'badge'));
 if(item.text_truncated)row.append(node('span','본문 일부 수집 · 원문 링크 확인','badge unverified'));
 if(item.topics?.includes('cross_sector'))row.append(node('span','공통 제도 · 적용대상 별도 확인','badge'));
 row.append(node('span','현행 효력 미확인','badge unverified'));return row;
}
function ref(item){return `${item.document_type} ${item.document_number}/${item.document_year}`;}
function matchEvidence(item){const box=node('details');box.append(node('summary','일치 근거 보기'));for(const m of item.matched_terms||[])box.append(node('p',`${m.term} → ${m.alias} · ${fields[m.field]||m.field}`,'meta'));return box;}
function card(item){
 const e=node('article');e.append(badges(item),node('h2',item.title_ko),node('p',item.title,'original'),node('p',`${ref(item)} · ${item.issuer_name}`,'meta'));
 if(item.total_condition_count){e.append(node('p',`${item.total_condition_count}개 조건 중 ${item.matched_condition_count}개 일치${item.matched_condition_count<item.total_condition_count?' · 일부 조건만 일치':''}`,'matches'),matchEvidence(item));}
 e.append(node('p',item.excerpt,'excerpt'));
 const actions=node('div',undefined,'actions'),button=node('button','세부사항');button.type='button';button.addEventListener('click',()=>showDetail(item.document_id));
 actions.append(button);appendSources(actions,item);e.append(actions);return e;
}
async function showDetail(id){
 detailController?.abort();detailController=new AbortController();const signal=detailController.signal;
 detail.replaceChildren(node('p','문서를 불러오는 중입니다.'));if(!dialog.open)dialog.showModal();
 try{
  const r=await fetch(`/api/idn/documents/${encodeURIComponent(id)}`,{signal}),d=await r.json();
  if(!r.ok)throw Error(d.error||'문서를 불러오지 못했습니다.');
  if(d.country!=='IDN')throw Error('국가별 데이터 검증에 실패했습니다.');
  const v=d.version;detail.replaceChildren(node('h2',d.title_ko),node('p',d.title,'original'),badges({...d,content_kind:v.content_kind,text_truncated:v.text_truncated}),node('p',`${ref(d)} · ${d.issuer_name}`,'meta'),node('p','수집 범위·검토 사항','meta'),node('p',d.scope_note,'scope'));
  detail.append(node('p',`자료 확인: ${new Date(v.observed_at).toLocaleString('ko-KR')} · 한국어 제목은 번역·정리 제목입니다.`,'meta'));
  const links=node('div',undefined,'actions');appendSources(links,{...d,content_kind:v.content_kind,text_source_url:v.text_source_url});detail.append(links);
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
 status.textContent='검색 중입니다.';results.replaceChildren();pages.replaceChildren();
 try{
  const r=await fetch(`/api/idn/search?${p}`,{signal:controller.signal}),data=await r.json();
  if(!r.ok)throw Error(data.error||'검색하지 못했습니다.');if(data.country!=='IDN')throw Error('국가별 데이터 검증에 실패했습니다.');if(token!==serial)return;
  coverage.textContent=`저장 문서 ${data.coverage.documents}건 · 수집 실패 이력이 있는 출처 ${data.coverage.held_sources}건 · 시범 수집 중`;
  const chosen=regionSelect.value||p.get('jurisdiction')||'';
  regionSelect.replaceChildren(new Option('전체',''),...data.jurisdictions.map(j=>new Option(regionNames[j]?`${regionNames[j]} (${j})`:j,j)));
  if(chosen&&!data.jurisdictions.includes(chosen))regionSelect.append(new Option(`${chosen} · 현재 자료 없음`,chosen));regionSelect.value=chosen;
  status.textContent=data.total?`${data.total}건 검색됨 · 키워드·동의어 검색`:'저장된 자료에서 일치하는 문서를 찾지 못했습니다. 조건을 줄이거나 품목을 선택해 보세요.';
  results.replaceChildren(...data.items.map(card));
  for(const [label,next,enabled] of [['이전',offset-20,offset>0],['다음',offset+20,offset+20<data.total]])if(enabled){const b=node('button',label);b.type='button';b.addEventListener('click',()=>search(next));pages.append(b);}
 }catch(e){if(e.name!=='AbortError'&&token===serial){status.textContent=e.message;coverage.textContent='연결 오류로 결과를 확인하지 못했습니다.';}}
}
const initial=new URLSearchParams(location.search);for(const [key,value] of initial){const control=form.elements.namedItem(key);if(!control)continue;if(control.type==='checkbox')control.checked=value==='all';else if(key==='jurisdiction'){control.append(new Option(value,value));control.value=value;}else control.value=value;}
form.addEventListener('submit',e=>{e.preventDefault();search();});form.addEventListener('change',e=>{if(e.target.name!=='q'){updateGovernmentFilters(['level','topic'].includes(e.target.name));search();}});
updateGovernmentFilters();search(Number(initial.get('offset'))||0);
