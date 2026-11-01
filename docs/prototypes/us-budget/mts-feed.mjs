// The actual MTS feed never changes the annual OMB proposal snapshot.
export function validateFeed(feed) {
  const fail = () => { throw new Error('MTS 피드 형식·기간 검증 실패'); };
  const money = n => typeof n === 'number' && Number.isFinite(n);
  const near = (a, b) => Math.abs(a - b) <= 0.05;
  const monthIndex = s => { const [y, m] = s.split('-').map(Number); return y * 12 + m - 1; };
  if (feed?.schema_version !== 1 || feed.unit !== 'USD' || feed.status !== 'actual'
      || !/^\d{4}-\d{2}-\d{2}$/.test(feed.publication_date)
      || !Array.isArray(feed.monthly) || feed.monthly.length !== 36) fail();
  for (const [i, row] of feed.monthly.entries()) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(row.month) || row.status !== 'actual'
        || !['receipts', 'outlays', 'deficit'].every(k => money(row[k]))
        || !near(row.outlays - row.receipts, row.deficit)
        || (i > 0 && monthIndex(row.month) !== monthIndex(feed.monthly[i - 1].month) + 1)) fail();
  }
  if (feed.monthly.at(-1).month !== feed.publication_date.slice(0, 7)) fail();
  if (feed.coverage?.start !== feed.monthly[0].month || feed.coverage?.end !== feed.monthly.at(-1).month
      || feed.coverage?.months !== 36) fail();
  const y = feed.fiscal_ytd;
  if (!y || !['receipts', 'outlays', 'deficit'].every(k => money(y[k]))
      || y.through !== feed.publication_date.slice(0, 7)
      || !near(y.outlays - y.receipts, y.deficit)) fail();
  const publicationMonth = Number(feed.publication_date.slice(5, 7));
  const fiscalYear = Number(feed.publication_date.slice(0, 4)) + (publicationMonth >= 10 ? 1 : 0);
  if (y.fy !== fiscalYear || y.complete_fy !== feed.publication_date.endsWith('09-30')) fail();
  for (const [key, total] of [['receipts_by_category', y.receipts], ['agencies', y.outlays]]) {
    if (!Array.isArray(y[key]) || !y[key].length) fail();
    let sum = 0;
    for (const r of y[key]) {
      if (typeof r.name !== 'string' || !(r.value === null || money(r.value))
          || !(r.prior === null || money(r.prior))) fail();
      if (r.value !== null) sum += r.value;
    }
    if (!near(sum, total)) fail();
  }
  const f = y.finance;
  if (!f || !['borrowing', 'cashIncrease', 'other', 'deficit'].every(k => money(f[k]))
      || !near(f.borrowing - f.cashIncrease + f.other, y.deficit)
      || !near(f.deficit, y.deficit)) fail();
  if (!Array.isArray(feed.sources) || !feed.sources.length) fail();
  for (const s of feed.sources) {
    const url = new URL(s.url);
    if (url.protocol !== 'https:' || url.hostname !== 'api.fiscaldata.treasury.gov') fail();
  }
  return feed;
}

export function sortedGroups(rows, sort) {
  const metric = r => r.value === null ? null : sort === 'delta'
    ? (r.prior === null ? null : r.value - r.prior)
    : sort === 'rate' ? (r.prior > 0 && r.value >= 0 ? r.value / r.prior - 1 : null) : r.value;
  return [...rows].sort((a, b) => {
    const x = metric(a), y = metric(b);
    return x === null ? (y === null ? a.name.localeCompare(b.name) : 1) : y === null ? -1 : y - x;
  });
}

export function renderLatest(feed, mount, agencyLabels = {}) {
  const y = feed.fiscal_ytd;
  const format = n => n === null ? '미확인' : (n / 1e9).toLocaleString('ko-KR', { maximumFractionDigits: 3 }) + ' B$';
  const element = (tag, text, parent = mount) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    parent.append(el);
    return el;
  };
  mount.replaceChildren();
  const box = element('details');
  element('summary', `최신 집행 실적 · FY${y.fy} ${y.through}까지${y.complete_fy ? ' 결산' : ' 누계'}`, box);
  element('p', `세출 ${format(y.outlays)} · 세입 ${format(y.receipts)} · ${y.deficit < 0 ? '흑자' : '적자'} ${format(Math.abs(y.deficit))}`, box);
  element('p', `MTS 발표 기준 ${feed.publication_date} · 비교: 전년 같은 기간 · 연간 정부안과 별도`, box).className = 'bf-muted';
  const labels = {
    'Individual Income Taxes': '개인소득세', 'Corporation Income Taxes': '법인세',
    'Social Insurance and Retirement Receipts:': '사회보험·퇴직 부담금', 'Excise Taxes': '소비세',
    'Estate and Gift Taxes': '상속·증여세', 'Customs Duties': '관세', 'Miscellaneous Receipts': '기타 세입'
  };
  for (const [key, name] of [['agencies', '부처별 순지출'], ['receipts_by_category', '세입 구조']]) {
    const section = element('details', undefined, box);
    element('summary', name, section);
    const select = element('select', undefined, section);
    select.setAttribute('aria-label', `${name} 정렬`);
    for (const [value, label] of [['value', '금액순'], ['rate', '증가율순'], ['delta', '증가액순']]) {
      element('option', label, select).value = value;
    }
    const list = element('div', undefined, section);
    const update = () => {
      list.replaceChildren();
      for (const r of sortedGroups(y[key], select.value)) {
        const row = element('div', undefined, list);
        row.className = 'bf-line';
        element('span', labels[r.name] || agencyLabels[r.name] || r.name, row);
        const delta = r.value === null || r.prior === null ? '증감 미확인' : `증감 ${format(r.value - r.prior)}`;
        const rate = r.value !== null && r.prior > 0 && r.value >= 0 ? ` · ${(100 * (r.value / r.prior - 1)).toFixed(1)}%` : ' · 증감률 제외';
        element('span', `${format(r.value)} · ${delta}${rate}`, row).className = 'bf-num';
      }
    };
    select.onchange = update;
    update();
  }
  element('p', '부처별 금액은 차감 수입을 포함한 순지출입니다. 음수는 일괄 삭감을 뜻하지 않으며 의무·재량 분류와 합산하지 않습니다.', box).className = 'bf-muted';
  const f = y.finance;
  element('p', `적자 조달: 순차입 ${format(f.borrowing)} − 현금 증가 ${format(f.cashIncrease)} + 기타 조달·조정 ${format(f.other)}`, box);
  element('p', '순차입은 세입·국채 총발행액과 다릅니다. 기타는 잔차이며 단일 공식 계정이 아닙니다.', box).className = 'bf-muted';
  const seen = new Set();
  for (const s of feed.sources.filter(s => s.publication_date === feed.publication_date)) {
    if (seen.has(s.table)) continue;
    seen.add(s.table);
    const link = element('a', `Treasury MTS 표 ${s.table} 원자료 `, box);
    link.href = s.url;
    link.target = '_blank';
    link.rel = 'noopener';
  }
}
