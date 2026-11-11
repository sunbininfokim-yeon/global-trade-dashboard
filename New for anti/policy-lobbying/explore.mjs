const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const kinds = {government:'정부·관청', political_party:'정당', public_body:'공공기관', state_owned_company:'국영기업', private_company:'민간기업', nonprofit:'협회·비영리', individual:'개인', unknown:'미확인'};
const branches = {legislative:'의회', executive:'행정부', judicial:'사법부', state_local:'주·지방정부', media:'언론', other:'기타', unknown:'미확인'};
const grains = {contact:'접촉 활동', narrative:'활동 서술', filing_issue_block:'LDA 이슈 묶음'};
const options = labels => Object.entries(labels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('');

export function mountExplorer(root, navigate) {
  let active = true;
  let controller;
  let offset = 0;
  root.innerHTML = `<button type="button" data-documents>← 문서 검색</button><h2>로비 관계 탐색</h2>
    <form data-explore-form>
      <input name="q" type="search" placeholder="한국 기업의 관세 관련 활동" aria-label="활동·정책 사안 검색" maxlength="300">
      <select name="source" aria-label="공시 제도"><option value="">FARA + LDA</option><option value="fara">FARA</option><option value="lda">LDA</option></select>
      <select name="country" aria-label="의뢰인 국가"><option value="">모든 국가</option><option value="KR">한국</option><option value="JP">일본</option><option value="CN">중국</option><option value="US">미국</option></select>
      <select name="principal_kind" aria-label="의뢰인 유형"><option value="">모든 의뢰인 유형</option>${options(kinds)}</select>
      <select name="branch" aria-label="접촉 대상 소속"><option value="">모든 접촉 대상</option>${options(branches)}</select>
      <select name="recipient" aria-label="접촉 기관·인물"><option value="">모든 기관·인물</option></select>
      <select name="mode" aria-label="검색 방식"><option value="semantic">의미 검색</option><option value="keyword">단어 검색</option></select><button>조회</button>
    </form>
    <div data-structure-coverage></div><div data-structure-facets></div><div data-structure-results role="status"></div>
    <div class="lobby-pages"><button type="button" data-previous disabled>이전</button><span data-page-label></span><button type="button" data-next disabled>다음</button></div>`;

  const load = async () => {
    controller?.abort(); controller = new AbortController();
    const query = new URLSearchParams(new FormData(root.querySelector('form')));
    for (const [key, value] of [...query]) if (!value) query.delete(key);
    query.set('offset', String(offset));
    root.querySelector('[data-previous]').disabled = true;
    root.querySelector('[data-next]').disabled = true;
    root.querySelector('[data-structure-results]').textContent = '근거를 조회하는 중입니다.';
    try {
      const response = await fetch('/api/us/lobbying/explore?' + query, {signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || '조회 실패');
      if (!active) return;
      const coverage = data.coverage;
      root.querySelector('[data-structure-coverage]').innerHTML = `<p>본문 확보 ${Number(coverage.eligible_documents).toLocaleString()}건 중 구조화 처리 완료 ${Number(coverage.fully_processed_documents).toLocaleString()}건</p>
        <p class="lobby-note">FARA 관계는 원문 근거가 있는 자동 추출 후보입니다. LDA는 신고된 이슈 묶음이며, 각 항목에서 근거와 검토 상태를 확인할 수 있습니다.</p>`;
      root.querySelector('[data-structure-facets]').innerHTML = `<p>필터에 해당하는 활동 묶음 ${Number(data.total_groups).toLocaleString()}개${data.semantic?' · 아래 결과는 의미 유사도순':''}</p>` +
        [['countries','country','의뢰인 국가',{}], ['principal_kinds','principal_kind','의뢰인 유형',kinds], ['branches','branch','접촉 대상 소속',branches], ['recipients','recipient','접촉 기관·인물',{}]].map(([field, filter, title, labels]) =>
          `<details ${filter==='recipient'?'':'open'}><summary>${title}</summary><div class="lobby-cases">${data[field].map(item =>
            `<button type="button" data-facet="${filter}" data-value="${escape(item.value)}" ${filter==='country'&&item.value==='unknown'?'disabled':''}>${escape(labels[item.value] || (item.value==='unknown'?'미확인':item.value))} ${Number(item.count).toLocaleString()}</button>`).join('') || '확보된 분류 없음'}</div></details>`).join('');
      root.querySelector('[data-structure-results]').innerHTML = data.items.map(item => {
        const detail = item.detail;
        const recipients = detail.recipients.map(actor => [...new Set([actor.name, actor.role, actor.organization, actor.department].filter(Boolean))].join(' · ')).join(' / ');
        return `<article class="lobby-activity"><small>${escape(item.source.toUpperCase())} · ${escape(grains[item.grain])} · ${item.review_status==='source_structured'?'신고 원문 구조':'자동 추출·검토 대기'}</small>
          <h3>${escape(detail.summary_ko || detail.issue)}</h3>
          <p>${escape(detail.principal?.name || '의뢰인 미확인')} → ${escape(recipients || '접촉 대상 미확인')}</p>
          <p>${escape(item.occurred_on || '활동일 미확인')} · ${escape(detail.method || '방식 미기재')}</p>
          <details><summary>원문 근거 ${item.locator.page?'· PDF '+Number(item.locator.page)+'쪽':''}</summary><blockquote class="lobby-text">${escape(detail.quote)}</blockquote></details>
          <button type="button" data-open-record="${escape(item.record_id)}">신고 문서 열기</button></article>`;
      }).join('') || '<p>조건에 맞는 구조화 활동이 아직 없습니다. 본문 처리 범위를 위에서 확인할 수 있습니다.</p>';
      root.querySelector('[data-previous]').disabled = offset === 0;
      root.querySelector('[data-next]').disabled = offset + data.items.length >= data.total_results;
      root.querySelector('[data-page-label]').textContent = `${Math.floor(offset/25)+1}쪽 · 결과 ${Number(data.total_results).toLocaleString()}개`;
    } catch (error) {
      if (active && error.name !== 'AbortError') root.querySelector('[data-structure-results]').textContent = error.message;
    }
  };
  const submit = event => { event.preventDefault(); offset=0; void load(); };
  const click = event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-documents')) navigate('lobbying');
    if (button.dataset.openRecord) navigate('lobbying', button.dataset.openRecord);
    if (button.hasAttribute('data-previous')) { offset=Math.max(0,offset-25); void load(); }
    if (button.hasAttribute('data-next')) { offset+=25; void load(); }
    if (button.dataset.facet) {
      const select = root.querySelector(`[name="${button.dataset.facet}"]`);
      if (![...select.options].some(option => option.value === button.dataset.value)) select.add(new Option(button.dataset.value, button.dataset.value));
      select.value = button.dataset.value;
      offset=0;
      void load();
    }
  };
  root.addEventListener('submit', submit); root.addEventListener('click', click);
  void load();
  return () => { active=false; controller?.abort(); root.removeEventListener('submit',submit); root.removeEventListener('click',click); };
}
