const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hosts=new Set(['www.govinfo.gov','www.whitehouse.gov','www.cbo.gov','www.crfb.org','www.steptoe.com','rollcall.com','appropriations.house.gov','democrats-appropriations.house.gov']);
const date=s=>typeof s==='string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0,10)===s;
const calendar=d=>Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
export function usableContext(d) {
  try {
    if(d?.schema_version!==1 || !Number.isInteger(d.fiscal_year) || !date(d.reviewed_on) || !date(d.review_valid_until)
       || d.review_valid_until<d.reviewed_on || !Array.isArray(d.sources) || !Array.isArray(d.issues)) return null;
    const source=new Map(d.sources.map(s=>[s.id,s]));
    if(source.size!==d.sources.length) return null;
    for(const s of source.values()) {
      const u=new URL(s.url);
      if(u.protocol!=='https:' || !hosts.has(u.hostname) || u.username || !date(s.published_on) || s.published_on>d.reviewed_on) return null;
    }
    const f=d.funding,p=d.procedure;
    if(f.kind!=='continuing_resolution' || !/^\d{3}-\d+$/.test(f.public_law_number) || !/^\d{3}-(hr|s|hjres|sjres)-\d+$/.test(f.bill_id)
       || !date(f.starts_on) || !date(f.general_deadline) || f.starts_on>f.general_deadline || !date(f.law_verified_on)
       || f.law_verified_on>d.reviewed_on || !/^[a-f0-9]{64}$/.test(f.law_sha256) || !date(p.as_of) || p.as_of>d.reviewed_on
       || !Number.isInteger(p.total_bills) || p.total_bills<=0) return null;
    if(['house_passed','senate_passed'].some(k=>!Number.isInteger(p[k]) || p[k]<0 || p[k]>p.total_bills)) return null;
    for(const record of [f,p,...d.issues]) {
      if(!Array.isArray(record.sources) || !record.sources.length || record.sources.some(id=>!source.has(id))) return null;
    }
    for(const r of d.issues) if(!date(r.as_of) || r.as_of>d.reviewed_on || !['unresolved_at_source','addressed_in_cr'].includes(r.state)
      || r.sources.some(id=>source.get(id).published_on>r.as_of)) return null;
    return d;
  } catch {return null;}
}

export function contextState(d,now=new Date()) {
  if(!usableContext(d))return 'unavailable';
  const p=calendar(now),today=`${p.year}-${p.month}-${p.day}`;
  if(today<d.reviewed_on || today<d.funding.starts_on || today>d.funding.general_deadline || today>d.review_valid_until)return 'needs_review';
  return 'reviewed';
}

export function renderContext(value,now=new Date()) {
  const d=usableContext(value);
  if(!d)return '<h3>현재 운영 예산</h3><p>임시예산·협상 현황을 확인하지 못했습니다. 아래 정부안 숫자로 현재 운영 예산을 판단하지 않습니다.</p>';
  const state=contextState(d,now),f=d.funding,p=d.procedure;
  const sources=new Map(d.sources.map(s=>[s.id,s]));
  const links=ids=>ids.map(id=>{const s=sources.get(id);return `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`;}).join(' · ');
  const issue=r=>`<article class="bf-context-issue"><strong>${esc(r.title)}</strong><p>${esc(r.summary)}</p><p class="bf-muted">근거 기준일 ${esc(r.as_of)} · ${links(r.sources)}</p></article>`;
  return `<h3>FY${d.fiscal_year} 운영 근거 · 임시예산(CR)</h3>
    <p><strong>${state==='reviewed'?'최근 검토에서 확인한 임시 운영 근거':'현황 재확인 필요 · 아래는 검토 기록'}</strong> · 검토 ${esc(d.reviewed_on)} · 재검토 기한 ${esc(d.review_valid_until)}</p>
    <div class="bf-context-grid"><div><span class="bf-muted">일반 적용 기간 · 미국 날짜</span><strong>${esc(f.starts_on)} ~ ${esc(f.general_deadline)}</strong></div><div><span class="bf-muted">법률 · 기한 조항</span><strong>P.L. ${esc(f.public_law_number)}</strong><span>${esc(f.deadline_locator)}</span></div></div>
    <p>${esc(f.scope)}</p><p><strong>왜 임시예산인가?</strong> ${esc(f.why)}</p>
    <p class="bf-muted">${esc(p.as_of)} 집계: 정규 세출법 ${p.total_bills}개 중 하원 통과 ${p.house_passed}개 · 상원 통과 ${p.senate_passed}개. ${esc(p.note)} ${links(p.sources)}</p>
    <p class="bf-muted">정규 세출법은 주로 재량지출의 예산권한을 정합니다. 아래 전체 세출에는 의무지출과 이자도 포함되므로 동일한 총액으로 비교하지 않습니다.</p>
    <p class="bf-message">${state==='reviewed'?'검토 시 확인한 운영 근거입니다.':'검토 당시의 운영 근거입니다. 현재 효력·후속 법률은 재확인이 필요합니다.'} 아래에서 선택하는 연간 정부안·과거 집행 실적과 금액을 합산하지 않습니다. 임시예산 기간 전체 금액은 미집계입니다.</p>
    <details><summary>본예산 협상 쟁점과 CR 합의 내용</summary>
      <h4>출처에서 미해결로 확인된 쟁점</h4>${d.issues.filter(r=>r.state==='unresolved_at_source').map(issue).join('')}
      <h4>CR에서 일단 조치한 사항</h4>${d.issues.filter(r=>r.state==='addressed_in_cr').map(issue).join('')}
      <p class="bf-muted">정치적 입장·보도·분석과 법률 사실을 구분했습니다. 각 근거 날짜 이후의 협상 변화는 별도 확인이 필요합니다.</p>
      <p>${links(f.sources)}</p>
    </details>`;
}

export function initialYear(annual) {
  const proposal=(annual.proposal || annual.fy2027).year.fy;
  return Math.max(...Object.entries(annual.budget.years).filter(([y,r])=>Number(y)<proposal && (!r.status || r.status==='actual') && !r.estimate).map(([y])=>Number(y)));
}

export function renderBasis(annual,fy) {
  const p=annual.proposal || annual.fy2027,isProposal=fy===p.year.fy;
  const y=isProposal?p.year:annual.budget.years[fy];
  const gap=Object.keys(annual.budget.years).map(Number).filter(y=>y<p.year.fy && !annual.budget.types[y]).sort((a,b)=>b-a)[0];
  const description=isProposal
    ? `OMB ${annual.publication || '2026/04'} 정부안 자료의 연간 추정입니다. 세출은 계정표를 합산하고, 세입은 세입표를 사용하며, 적자는 세출−세입으로 계산했습니다. 의회 확정액·임시예산 허용액·집행 실적을 뜻하지 않습니다.`
    : `이 회계연도에 실제 들어오고 나간 돈입니다. ${y.source}. 총액 실적과 의무·재량/계정별 분류의 확보 여부는 다를 수 있습니다.`;
  return `<h3>선택한 금액 자료: FY${fy} ${isProposal?'정부안 · 연간 추정':'결산 실적'}</h3>
    <p>회계기간 ${fy-1}-10-01 ~ ${fy}-09-30</p><p>${esc(description)}</p>
    ${gap ? `<details><summary>FY${gap} 상세는 비어 있는데 FY${p.year.fy} 숫자는 있는 이유</summary><p>실적과 계획은 발표 시점이 다릅니다. FY${gap} 총세입·총세출·적자 실적은 확보됐지만 의무·재량 및 계정별 실제 분류는 미연결입니다. FY${p.year.fy}은 미리 발표한 정부안의 추정 자료이므로 존재할 수 있습니다. 추정치를 FY${gap} 실적 대신 넣지 않습니다.</p></details>` : ''}`;
}
