const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const officialHosts = new Set(['www.govinfo.gov', 'www.congress.gov', 'www.cbo.gov', 'www.whitehouse.gov', 'www.archives.gov']);
const money = n => `${(n / 1e9).toLocaleString('ko-KR', {maximumFractionDigits: 3})} B$`;
export function usableFunding(value) {
  try {
    if (value?.schema_version !== 1 || value.coverage !== 'reviewed_subset'
        || !Array.isArray(value.measures) || !Array.isArray(value.cost_estimates)) return null;
    const identity = id => /^\d{3}-(hr|s|hjres|sjres)-[1-9]\d*$/.test(id || '');
    for (const law of value.measures) {
      if (!identity(law.bill_id) || !/^\d{3}-[1-9]\d*$/.test(law.public_law_number)
          || !/^\d{4}-\d{2}-\d{2}$/.test(law.general_deadline) || !Array.isArray(law.areas)
          || !['verified','needs_review','source_unavailable'].includes(law.verification_status)) return null;
    }
    for (const e of value.cost_estimates) {
      const f=e.budget_effects, a=e.annualized;
      if (!identity(e.bill_id) || e.version_match !== 'related_draft_not_verified_as_enacted'
          || !value.measures.some(m=>m.bill_id===e.bill_id && m.public_law_number===e.public_law_number)
          || ![a.budget_authority_usd,a.outlays_usd,a.fiscal_year].every(Number.isFinite)
          || !Array.isArray(f.years) || !f.years.length) return null;
      if (f.years.some((y,i)=>!Number.isInteger(y)||(i && y!==f.years[i-1]+1))) return null;
      for (const key of ['outlays_million','revenues_million','deficit_million']) {
        if (!Array.isArray(f[key]) || f[key].length!==f.years.length || !f[key].every(Number.isFinite)) return null;
      }
      if (f.years.some((_,i)=>Math.abs(f.outlays_million[i]-f.revenues_million[i]-f.deficit_million[i])>0.001)) return null;
      if (!Array.isArray(f.cumulative) || !f.cumulative.length) return null;
      for (const r of f.cumulative) {
        if (![r.start,r.end].every(Number.isInteger) || r.start>r.end || r.start<f.years[0] || r.end>f.years.at(-1)) return null;
        for (const key of ['outlays_million','revenues_million','deficit_million']) {
          const sum=f.years.reduce((n,y,i)=>n+(y>=r.start&&y<=r.end?f[key][i]:0),0);
          if (!Number.isFinite(r[key]) || Math.abs(sum-r[key])>0.001) return null;
        }
      }
    }
    return value;
  } catch { return null; }
}
function link(url, text) {
  try {
    const u = new URL(url);
    if (u.protocol !== 'https:' || !officialHosts.has(u.hostname)) return esc(text);
    return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`;
  } catch { return esc(text); }
}

export function financeForBill(funding, billId) {
  if (!usableFunding(funding) || !/^\d{3}-(hr|s|hjres|sjres)-[1-9]\d*$/.test(billId || '')) return null;
  const measures = (funding?.measures || []).filter(m => m.bill_id === billId);
  const estimates = (funding?.cost_estimates || []).filter(m => m.bill_id === billId);
  return measures.length || estimates.length ? {measures, estimates} : null;
}

function lawMarkup(m) {
  const status = m.verification_status === 'verified' ? '법률 원문 확인' : m.verification_status === 'needs_review' ? '원문 변경: 재검토 필요' : '원문 재확인 불가';
  return `<details><summary>${esc(m.title)} · P.L. ${esc(m.public_law_number)}</summary>
    <p>${status} · 제정일 ${esc(m.enacted_on)} · FY${esc(m.fiscal_year)}</p>
    <p>임시예산 일반 기한: <strong>${esc(m.general_deadline)}</strong> (미국 날짜) · ${esc(m.deadline_section)}</p>
    <p>후속 세출법의 제정·사업 제외에 따른 조기 종료와 조항별 예외가 있습니다. 현재 모든 사업의 자금 효력을 확정한 표시는 아닙니다.</p>
    <p>${link(m.govinfo_url, '법률 원문')} · ${link(m.corroborating_url, '대통령 서명 확인')}</p>
    <details><summary>기존 세출법을 참조하는 ${m.areas.length}개 분야</summary>${m.areas.map(a => `<div class="bf-line"><span>${esc(a.name)}</span><span>P.L. ${esc(a.base_law)}${a.base_division ? ` · Division ${esc(a.base_division)}` : ''} · §101(${a.item})</span></div>`).join('')}</details>
  </details>`;
}

function estimateMarkup(e) {
  const a = e.annualized, f = e.budget_effects;
  const unavailable = ['http_403', 'source_unavailable'].includes(e.direct_fetch_status);
  return `<details><summary>CBO 재정효과 · ${esc(e.published_on)} 초안 추정</summary>
    <p>${esc(e.version)} · 확정법과의 버전 일치 미검증</p>
    <p>${unavailable ? '직접 다운로드 재확인 불가. ' : '새 다운로드의 수치 재검토 필요. '}검토일 ${esc(e.reviewed_on)}의 확인된 표를 보관해 표시합니다.</p>
    <h4>재량지출 연간 환산 추정 · FY${a.fiscal_year}</h4>
    <p>예산권한 ${money(a.budget_authority_usd)} · 지출 추정 ${money(a.outlays_usd)}</p>
    <p>이전 세출법의 영향과 법정 제외 항목을 포함한 원문의 범위를 따릅니다. 임시예산 기간의 확정액·실제 지급액과 구분합니다.</p>
    <h4>별도 의무지출·세입 변경 추정</h4><p>${esc(f.baseline)} 대비 · ${esc(f.scope)}</p>
    ${f.cumulative.map(r => `<p>FY${r.start}–${r.end}: 지출 ${money(r.outlays_million*1e6)} · 세입 ${money(r.revenues_million*1e6)} · 적자 영향 ${money(r.deficit_million*1e6)}</p>`).join('')}
    <details><summary>연도별 영향 · 원표 단위: 백만 달러</summary>${f.years.map((year,i) => `<div class="bf-line"><span>FY${year}</span><span>지출 ${f.outlays_million[i]} · 세입 ${f.revenues_million[i]} · 적자 ${f.deficit_million[i]}</span></div>`).join('')}</details>
    <p>${link(e.source_url, 'CBO 원문 표 1·2')} · 원문 표의 버전·기준선·범위를 유지하며 다른 예산 총액과 합산하지 않습니다.</p>
  </details>`;
}

export function renderBillFinance(funding, billId) {
  const found = financeForBill(funding, billId);
  if (!found) return '<p>확인된 예산·재정효과 자료가 없습니다. 미조사 항목도 포함됩니다.</p>';
  return found.measures.map(lawMarkup).join('') + found.estimates.map(estimateMarkup).join('');
}

export function renderFunding(funding, fiscalYear) {
  if (!usableFunding(funding)) return '<p>세출법·임시예산 연결 자료는 미수집 또는 검증 미완료 상태입니다.</p>';
  const laws = funding.measures.filter(m => m.fiscal_year === fiscalYear);
  const bills = new Set(laws.map(m => m.bill_id));
  const status = funding.discovery.status === 'checked' ? '공식 법률 목록 확인' : '공식 법률 목록 재확인 불가';
  return `<details><summary>확인된 세출법·임시예산 · FY${fiscalYear}</summary>
    <p>${status} · 검토된 일부 법률만 표시합니다. 표시된 법률이 없다고 관련 법률이 없는 것은 아닙니다.</p>
    ${laws.length ? laws.map(lawMarkup).join('') : '<p>선택 연도의 검토된 법률이 없습니다.</p>'}
    ${funding.cost_estimates.filter(e => bills.has(e.bill_id)).map(estimateMarkup).join('')}
    <p>새 공고 검토 후보: ${funding.discovery.status==='checked' ? `${(funding.discovery.candidates || []).length}건` : '확인 불가'} · 목록 조회가 실패하면 기존 후보를 보존합니다.</p>
  </details>`;
}

let pending = null, loaded = 0;
export function mountBillFinance(root, billId) {
  let alive = true;
  const button = root.querySelector('[data-budget-finance-load]');
  const result = root.querySelector('[data-budget-finance-result]');
  button.onclick = async () => {
    button.disabled = true;
    result.textContent = '예산·재정 근거를 확인하고 있습니다.';
    try {
      if (!pending || Date.now()-loaded > 5*60*1000) {
        loaded = Date.now();
        pending = fetch('/public/data/us_budget/budget_live_v1.json', {cache:'no-cache'})
          .then(r => { if (!r.ok) throw new Error('Budget data unavailable'); return r.json(); })
          .catch(error => { pending = null; throw error; });
      }
      const bundle = await pending;
      if (alive) result.innerHTML = renderBillFinance(bundle.funding, billId);
    } catch {
      if (alive) result.textContent = '예산 연결 자료를 불러오지 못했습니다. 재정효과는 미확인 상태입니다.';
    } finally { if (alive) button.disabled = false; }
  };
  return () => { alive = false; button.onclick = null; };
}
