const form=document.querySelector('#search-form'),results=document.querySelector('#results');
const status=document.querySelector('#status'),coverage=document.querySelector('#coverage'),pages=document.querySelector('#pagination');
const dialog=document.querySelector('#detail'),detail=document.querySelector('#detail-content');
const topics={coal:'석탄',nickel_mining:'니켈·광산',palm_oil:'팜유',biofuel:'바이오연료'};
const levels={national:'중앙',provincial:'주',regency:'군',city:'시'};
const fields={title:'제목·문서번호',source_text:'출처 본문',catalogue:'분류·기관·지역'};
let controller,detailController,serial=0;
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const official=url=>{try{const u=new URL(url);return u.protocol==='https:'&&u.hostname.endsWith('.go.id')?u.href:null;}catch{return null;}};
function sourceLink(url,label){const href=official(url);if(!href)return node('span','원문 링크 확인 필요');const a=node('a',label);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;}
function badges(item){const row=node('div',undefined,'badges');for(const text of [topics[item.primary_stage],levels[item.issuer_level],item.jurisdiction,item.content_kind==='official_text'?'원문 자료':'메타데이터'])row.append(node('span',text,'badge'));row.append(node('span','현행 효력 미확인','badge unverified'));return row;}
function ref(item){return `${item.document_type} ${item.document_number}/${item.document_year}`;}
function matchEvidence(item){const box=node('details');box.append(node('summary','일치 근거 보기'));for(const m of item.matched_terms||[])box.append(node('p',`${m.term} → ${m.alias} · ${fields[m.field]||m.field}`,'meta'));return box;}
function card(item){
 const e=node('article');e.append(badges(item),node('h2',item.title_ko),node('p',item.title,'original'),node('p',`${ref(item)} · ${item.issuer_name}`,'meta'));
 if(item.total_condition_count){e.append(node('p',`${item.total_condition_count}개 조건 중 ${item.matched_condition_count}개 일치${item.matched_condition_count<item.total_condition_count?' · 일부 조건만 일치':''}`,'matches'),matchEvidence(item));}
 e.append(node('p',item.excerpt,'excerpt'));
 const actions=node('div',undefined,'actions'),button=node('button','세부사항');button.type='button';button.addEventListener('click',()=>showDetail(item.document_id));
 actions.append(button,sourceLink(item.source_url,'공식 출처 ↗'));e.append(actions);return e;
}
async function showDetail(id){
 detailController?.abort();detailController=new AbortController();const signal=detailController.signal;
 detail.replaceChildren(node('p','문서를 불러오는 중입니다.'));if(!dialog.open)dialog.showModal();
 try{
  const r=await fetch(`/api/idn/documents/${encodeURIComponent(id)}`,{signal}),d=await r.json();
  if(!r.ok)throw Error(d.error||'문서를 불러오지 못했습니다.');
  if(d.country!=='IDN')throw Error('국가별 데이터 검증에 실패했습니다.');
  const v=d.version;detail.replaceChildren(node('h2',d.title_ko),node('p',d.title,'original'),badges({...d,content_kind:v.content_kind}),node('p',`${ref(d)} · ${d.issuer_name}`,'meta'),node('p','수집 범위·검토 사항','meta'),node('p',d.scope_note,'scope'));
  detail.append(node('p',`자료 확인: ${new Date(v.observed_at).toLocaleString('ko-KR')} · 한국어 제목은 번역·정리 제목입니다.`,'meta'));
  const links=node('div',undefined,'actions');links.append(sourceLink(d.source_url,'공식 문서 페이지 ↗'));if(v.text_source_url&&v.text_source_url!==d.source_url)links.append(sourceLink(v.text_source_url,'원문 자료 ↗'));detail.append(links);
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
  coverage.textContent=`저장 문서 ${data.coverage.documents}건 · 원문 확인 보류 출처 ${data.coverage.held_sources}건 · 시범 수집 중`;
  const select=document.querySelector('#jurisdictions'),chosen=select.value||p.get('jurisdiction')||'';
  select.replaceChildren(new Option('전체',''),...data.jurisdictions.map(j=>new Option(j,j)));select.value=chosen;
  status.textContent=data.total?`${data.total}건 검색됨 · 키워드·동의어 검색`:'저장된 자료에서 일치하는 문서를 찾지 못했습니다. 조건을 줄이거나 품목을 선택해 보세요.';
  results.replaceChildren(...data.items.map(card));
  for(const [label,next,enabled] of [['이전',offset-20,offset>0],['다음',offset+20,offset+20<data.total]])if(enabled){const b=node('button',label);b.type='button';b.addEventListener('click',()=>search(next));pages.append(b);}
 }catch(e){if(e.name!=='AbortError'&&token===serial){status.textContent=e.message;coverage.textContent='연결 오류로 결과를 확인하지 못했습니다.';}}
}
const initial=new URLSearchParams(location.search);for(const [key,value] of initial){const control=form.elements.namedItem(key);if(!control)continue;if(control.type==='checkbox')control.checked=value==='all';else if(key==='jurisdiction'){control.append(new Option(value,value));control.value=value;}else control.value=value;}
form.addEventListener('submit',e=>{e.preventDefault();search();});form.addEventListener('change',e=>{if(e.target.name!=='q')search();});
search(Number(initial.get('offset'))||0,false);
