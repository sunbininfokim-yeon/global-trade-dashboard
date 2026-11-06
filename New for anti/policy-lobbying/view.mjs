const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TOPICS={supply_chain:'공급망',mining:'광산·핵심광물',agriculture:'농산물',semiconductors:'반도체',data_centers:'데이터센터',steel:'철강'};
const TEXT={pending:'본문 수집 대기',extracted:'본문 확보',ocr_required:'OCR 필요',source_unavailable:'본문 접근 실패',not_applicable:'등록 정보'};
const STATUS={pending:'대기',running:'실행 중',partial:'수집 진행 중',complete_pass:'목록 한 차례 순회 완료',source_unavailable:'원천 접근 실패'};
export async function prepare(){
  if(!document.querySelector('link[data-lobbying-css]')){
    const link=document.createElement('link'); link.rel='stylesheet';link.href='/policy-lobbying/style.css?v=1';link.dataset.lobbyingCss='';document.head.append(link);
  }
}
export function markup(){return '<section class="lobbying" data-lobbying><p role="status">로비·사안 자료를 불러오는 중입니다.</p></section>';}
const safeUrl = value => {try{const u=new URL(value);return u.protocol==='https:'?u.href:'';}catch{return '';}};
const sourceLink=(url,label='공식 원문')=>safeUrl(url)?`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`:'';
const recordLink=r=>`<button type="button" data-record="${esc(r.record_id)}">${esc(r.client_name || r.registrant_name || r.title)}</button>`;
function rowsMarkup(items){return items.length?`<div class="lobby-table-wrap"><table><thead><tr><th>출처·일자</th><th>의뢰인·등록기관</th><th>문서</th><th>국가·본문 상태</th></tr></thead><tbody>${items.map(r=>`<tr><td>${esc(r.source.toUpperCase())}<br>${esc(r.source_date || '원천 날짜 미확인')}</td><td>${recordLink(r)}<small>${esc(r.registrant_name)}</small></td><td>${esc(r.title)}<small>${(r.topics||[]).map(t=>esc(TOPICS[t]||t)).join(' · ')}</small></td><td>${esc(r.country_raw || ((r.related_countries||[]).length?'등록기관 관계 국가: '+r.related_countries.join(', ')+' · 문서 귀속 미확인':'국가 미기재'))}<small>${esc(TEXT[r.text_state]||r.text_state)}</small></td></tr>`).join('')}</tbody></table></div>`:'<p>이 조건으로 수집된 문서가 없습니다. 미수집·미추출 자료가 있을 수 있습니다.</p>';}
function detailMarkup(data){
  const r=data.record;
  return `<button type="button" data-home>← 신고 검색</button><h2>${esc(r.client_name || r.registrant_name)}</h2>
    <p>${esc(r.title)} · ${esc(r.source_date || '날짜 미확인')} · ${esc(TEXT[r.text_state])}</p>
    <p>${sourceLink(r.source_url)} · ${esc(r.registrant_name)}</p>
    ${r.source==='lda'?'<p class="lobby-note">분기별 이슈 묶음입니다. 신고서 전체 금액을 개별 법안·기관·사안 비용으로 배분하지 않습니다.</p>':''}
    <h3>정책 연결</h3>${data.links.length?`<ul>${data.links.map(l=>`<li>${esc(l.raw_reference)} · ${esc(l.resolution_status==='confirmed'?'정본 ID 확인':l.resolution_status==='ambiguous'?'회기·식별자 검토 필요':'정책 DB 미수록')}${l.resolution_status==='confirmed'&&l.target_type==='bill'?` <button type="button" data-policy="${esc(l.target_id)}">법안 열기</button>`:''}</li>`).join('')}</ul>`:'<p>확인된 정책 식별자가 없습니다. 주제만으로 법안을 연결하지 않습니다.</p>'}
    ${data.activities.map(a=>`<article><h3>${esc(a.issue_code || '신고 이슈')}</h3><p class="lobby-text">${esc(a.description)}</p><p>신고된 기관: ${(a.government_entities||[]).map(x=>esc(x.name)).join(' · ') || '미기재'}</p></article>`).join('')}
    ${r.pages?.length?`<h3>원문 본문</h3>${r.pages.map(p=>`<details><summary>PDF ${esc(p.page)}쪽</summary><pre>${esc(p.text)}</pre></details>`).join('')}`:r.body_text?`<pre>${esc(r.body_text)}</pre>`:'<p>본문 수집 대기 또는 접근 실패입니다. 공식 원문 링크로 확인할 수 있습니다.</p>'}`;
}
function caseMarkup(c){return `<button type="button" data-home>← 신고 검색</button><h2>${esc(c.title)}</h2><p class="lobby-note">${esc(c.note)} 검토일 ${esc(c.reviewed_at)}</p><h3>사안 연표</h3>${c.events.map(e=>`<article><small>${esc(e.date)} · ${esc(e.actor)}</small><h3>${esc(e.title)}</h3><p>${esc(e.description)}</p>${sourceLink(e.url)} · ${esc(e.evidence)}</article>`).join('')}<h3>문맥상 관련 신고</h3>${c.contextual_records.map(r=>`<article>${sourceLink(r.url,r.title)}<p>${esc(r.note)}</p></article>`).join('')}`;}

export function mount(root,{id,navigate}={}){
  let active=true,controller=null,offset=0;
  const get=async path=>{const res=await fetch('/api/us/lobbying/'+path,{signal:controller.signal});const body=await res.json();if(!res.ok)throw new Error(body.error||'조회 실패');return body;};
  const show=async()=>{
    controller?.abort();controller=new AbortController();
    try{
      if(id){const body=await get(id.startsWith('case:')?'cases/'+encodeURIComponent(id.slice(5)):'records/'+encodeURIComponent(id));if(active)root.innerHTML=id.startsWith('case:')?caseMarkup(body):detailMarkup(body);return;}
      root.innerHTML=`<h2>로비·사안</h2><p class="lobby-note">전 국가·전 산업을 수집합니다. 아래 조건은 조회 필터이며 주제 태그는 자동 분류입니다. 등록기관 관계 국가가 문서별 활동 국가를 뜻하지는 않습니다.</p>
        <details><summary>전체 수집 진행 상황</summary><div data-coverage></div></details>
        <div class="lobby-cases" data-cases></div>
        <form data-filters><input name="q" type="search" placeholder="기업·정책 원문 검색" aria-label="기업·정책 검색">
        <select name="source" aria-label="출처"><option value="">모든 출처</option><option value="fara">FARA</option><option value="lda">LDA</option></select>
        <select name="country" aria-label="국가"><option value="">모든 국가</option><option value="KR">한국</option><option value="JP">일본</option><option value="CN">중국 본토</option><option value="TW">대만</option><option value="HK">홍콩</option><option value="US">미국</option></select>
        <select name="topic" aria-label="산업"><option value="">모든 산업·주제</option>${Object.entries(TOPICS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><button>검색</button></form>
        <div data-results role="status">신고 목록을 불러오는 중입니다.</div><div class="lobby-pages"><button type="button" data-page="prev">이전</button><span data-page-label></span><button type="button" data-page="next">다음</button></div>`;
      const loadAux=async()=>{const results=await Promise.allSettled([get('coverage'),get('cases')]);if(!active)return;
        root.querySelector('[data-coverage]').innerHTML=results[0].status==='fulfilled'?`<p>저장된 목록 ${(results[0].value.counts||[]).reduce((s,x)=>s+Number(x.count),0).toLocaleString()}건 · 본문·검수 완료와는 별도입니다.</p><ul>${(results[0].value.streams||[]).map(s=>`<li>${esc(s.stream)}: ${esc(STATUS[s.status]||s.status)}${s.expected_count!=null?' · 원천 목록 '+Number(s.expected_count).toLocaleString()+'건':''} · 최근 성공 ${esc(s.last_success_at||'없음')}${s.last_error?' · 접근 오류':''}</li>`).join('')}</ul>`:'수집 상태를 불러오지 못했습니다.';
        root.querySelector('[data-cases]').innerHTML=results[1].status==='fulfilled'?results[1].value.items.map(c=>`<button type="button" data-case="${esc(c.case_id)}">사안: ${esc(c.title)}</button>`).join(''):'';
      };
      await Promise.all([loadList(),loadAux()]);
    }catch(error){if(active&&error.name!=='AbortError')root.innerHTML=`<p role="alert">${esc(error.message)}</p><button type="button" data-home>신고 검색으로</button>`;}
  };
  let listController=null;
  const loadList=async()=>{
    listController?.abort();listController=new AbortController();
    const query=new URLSearchParams(new FormData(root.querySelector('[data-filters]')));
    for(const [k,v] of [...query])if(!v)query.delete(k);
    query.set('offset',offset);const target=root.querySelector('[data-results]');target.textContent='조회 중입니다.';
    try{const res=await fetch('/api/us/lobbying/records?'+query,{signal:listController.signal});const data=await res.json();if(!res.ok)throw new Error(data.error);if(!active)return;
      target.innerHTML=rowsMarkup(data.items);root.querySelector('[data-page="prev"]').disabled=offset===0;root.querySelector('[data-page="next"]').disabled=!data.has_more;root.querySelector('[data-page-label]').textContent=String(Math.floor(offset/25)+1);
    }catch(error){if(active&&error.name!=='AbortError')target.textContent=error.message;}
  };
  const click=e=>{const b=e.target.closest('button');if(!b)return;
    if(b.hasAttribute('data-home'))navigate('lobbying');
    if(b.dataset.record)navigate('lobbying',b.dataset.record);
    if(b.dataset.case)navigate('lobbying','case:'+b.dataset.case);
    if(b.dataset.policy)navigate('bill',b.dataset.policy);
    if(b.dataset.page){offset=Math.max(0,offset+(b.dataset.page==='next'?25:-25));void loadList();}
  };
  const submit=e=>{if(e.target.matches('[data-filters]')){e.preventDefault();offset=0;void loadList();}};
  root.addEventListener('click',click);root.addEventListener('submit',submit);void show();
  return()=>{active=false;controller?.abort();listController?.abort();root.removeEventListener('click',click);root.removeEventListener('submit',submit);};
}

export function mountPolicyLinks(root,type,id,navigate){
  const controller=new AbortController();
  root.innerHTML='<h3>관련 로비 공시</h3><p role="status">연결 자료 조회 중입니다.</p>';
  fetch('/api/us/lobbying/records?'+new URLSearchParams({policy_type:type,policy_id:id}),{signal:controller.signal})
    .then(async r=>{const data=await r.json();if(!r.ok)throw new Error();return data;})
    .then(data=>{root.innerHTML='<h3>관련 로비 공시</h3>'+rowsMarkup(data.items);})
    .catch(e=>{if(e.name!=='AbortError')root.innerHTML='<h3>관련 로비 공시</h3><p>연결 자료를 불러오지 못했습니다.</p>';});
  const click=e=>{const b=e.target.closest('[data-record]');if(b)navigate('lobbying',b.dataset.record);};root.addEventListener('click',click);
  return()=>{controller.abort();root.removeEventListener('click',click);};
}
