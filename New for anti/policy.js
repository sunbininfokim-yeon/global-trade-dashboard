// US Policy Dashboard
//
// Unlike the commodity/climate views, policy has no map to show -- it is a
// document-style screen, so it takes the full centre surface (#chart-view) the
// same way shipping and finance do, instead of the narrow right pane.
//
// Data comes from the Worker's /api/us/* routes (see _worker.js and
// docs/api-spec.md section 5), which read Supabase under the service role.
// Unlike the UI fixture this replaced, there is no single upfront blob: each
// drill-down level fetches only what it needs and caches it for the session,
// because a live 119th-Congress bill list is too large to preload.

(() => {
  const API_BASE = '/api/us';

  const STAGE_LABELS = {
    introduced: '발의',
    referred: '회부',
    subcommittee: '소위',
    committee_consideration: '위원회 심사',
    reported: '상임위 통과',
    passed_origin_chamber: '본회의 통과',
    second_chamber: '상대원 심사',
    resolving_differences: '양원 조정',
    passed_both_chambers: '양원 통과',
    presented_to_president: '정부 이송',
    enacted: '법률 제정',
    vetoed: '거부',
    failed: '부결',
  };

  const CHAMBER_LABELS = { house: '하원', senate: '상원', joint: '합동' };

  const esc = (value) => {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };

  const stageLabel = (stage) => STAGE_LABELS[stage] || stage || '-';

  // Stage tabs group several raw stages under one label (e.g. "발의·회부" spans
  // four of the fourteen schema.sql stages) -- a presentation choice, not
  // something the API returns, so it is defined once here and the per-stage
  // counts the API does return are summed into it.
  const STAGE_TAB_DEFS = [
    { label: '전체 보기', stages: [] },
    { label: '발의·회부', stages: ['introduced', 'referred', 'subcommittee', 'committee_consideration'] },
    { label: '상임위 통과/보고', stages: ['reported'] },
    { label: '발의원 본회의 통과', stages: ['passed_origin_chamber'] },
    { label: '상대원 심사', stages: ['second_chamber'] },
    { label: '양원 조정', stages: ['resolving_differences'] },
    { label: '양원 통과', stages: ['passed_both_chambers', 'presented_to_president'] },
    { label: '대통령 서명·법률 제정', stages: ['enacted'] },
    { label: '종료·거부/부결', stages: ['vetoed', 'failed'] },
  ];

  function buildStageTabs(stageCounts) {
    const hasCounts = !!stageCounts && typeof stageCounts === 'object';
    const sc = stageCounts || {};
    const total = Object.values(sc).reduce((a, b) => a + b, 0);
    return STAGE_TAB_DEFS.map((def) => ({
      label: def.label,
      stage: def.stages.join(','),
      // Do not render 0 when the aggregate RPC is unavailable. A missing
      // number must remain visibly unknown rather than claim no bills exist.
      count: hasCounts ? (def.stages.length ? def.stages.reduce((s, k) => s + (sc[k] || 0), 0) : total) : null,
    }));
  }

  /* ----------------------------------------------------------------- data */

  // GET wrapper: throws with the server's own message on a non-2xx response,
  // so a fetch failure and an API-level error (e.g. missing Supabase secrets)
  // both surface the same way to a caller's try/catch.
  async function api(path) {
    const res = await fetch(`${API_BASE}${path}`);
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON error page */ }
    if (!res.ok) throw new Error(body?.error || `HTTP ${res.status}`);
    return body;
  }

  const qs = (params) => {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') usp.set(k, v);
    const s = usp.toString();
    return s ? `?${s}` : '';
  };

  // Session-scoped caches, unbounded. Unlike the fixture this replaced (one
  // slot per kind: DATA.bill_detail, DATA.committee_detail...), a live session
  // can open more than one bill/committee/agency/EO/CFR title, so each is
  // keyed by id. Counts stay in the low hundreds even in a long session.
  let overviewPromise = null;
  const billListCache = new Map();   // `${committeeId}|${policyAreaId}|${stage}` -> list response
  const billCache = new Map();       // bill_id -> detail
  const committeeCache = new Map();  // committee_id -> { subcommittees }
  const eoListCache = new Map();     // agency_id -> list response
  const eoCache = new Map();         // eo_number -> detail
  const cfrCache = new Map();        // title_number -> detail

  const cached = (map, key, load) => {
    if (map.has(key)) return map.get(key);
    const p = load().catch((err) => { map.delete(key); throw err; });
    map.set(key, p);
    return p;
  };

  const loadOverview = () => (overviewPromise ||= api('/overview'));

  const loadBillList = (params) => cached(
    billListCache, `${params.committee_id || ''}|${params.policy_area_id || ''}|${params.stage || ''}`,
    () => api(`/congress/bills${qs(params)}`),
  );
  const loadBill = (billId) => cached(billCache, billId, () => api(`/congress/bills/${encodeURIComponent(billId)}`));
  const loadCommittee = (id) => cached(committeeCache, id, () => api(`/congress/committees${qs({ committee_id: id })}`));
  const loadEoList = (agencyId) => cached(eoListCache, agencyId || '', () => api(`/executive/orders${qs({ agency_id: agencyId, limit: 100 })}`));
  const loadEo = (eoNumber) => cached(eoCache, String(eoNumber), () => api(`/executive/orders/${eoNumber}`));
  const loadCfrTitle = (n) => cached(cfrCache, String(n), () => api(`/executive/cfr-titles/${n}`));

  /* ---------------------------------------------------------------- shell */

  // Navigation is a drill-down trail, four levels deep:
  //   미국 › 의회 › 상임위 › 법률
  //   미국 › 행정부 › 부처 › 행정명령
  // The trail doubles as the breadcrumb, so every ancestor stays reachable and
  // a screen never has to guess where it was opened from.
  const state = { trail: [], stage: '', open: {}, search: { query: '' } };

  const current = () => state.trail[state.trail.length - 1] || { view: 'congress' };
  const trailHas = (view) => state.trail.some((t) => t.view === view);

  const empty = (message) => `<div class="policy-empty">${esc(message)}</div>`;

  const card = (title, bodyHtml, extraClass = '') =>
    `<section class="policy-block ${extraClass}">
       <h3 class="policy-block-title">${esc(title)}</h3>
       ${bodyHtml}
     </section>`;

  const collapsibleCard = (key, title, bodyHtml, count) => {
    const open = !!state.open[key];
    return `<section class="policy-block is-collapsible${open ? ' is-open' : ''}">
      <button type="button" class="policy-collapse-toggle" data-collapse="${esc(key)}" aria-expanded="${open}">
        <span class="policy-block-title">${esc(title)}${typeof count === 'number' ? ` (${count})` : ''}</span>
        <span class="policy-collapse-chevron" aria-hidden="true">${open ? '▾' : '▸'}</span>
      </button>
      ${open ? bodyHtml : ''}
    </section>`;
  };

  // Every entry but the last is a step back up the trail, addressed by depth so
  // a click truncates rather than re-navigating.
  const crumb = () =>
    `<nav class="policy-crumb">
      <span class="policy-crumb-root">미국</span>
      ${state.trail.map((p, i) => {
        const last = i === state.trail.length - 1;
        const step = last
          ? `<span class="policy-crumb-current">${esc(p.label)}</span>`
          : `<button type="button" class="policy-crumb-link" data-depth="${i}">${esc(p.label)}</button>`;
        return '<span class="policy-crumb-sep">›</span>' + step;
      }).join('')}
    </nav>`;

  // Backed by /api/us/search: a Gemini query embedding fanned out across
  // bills/executive_orders/regulations (search_policy_corpus RPC). A result
  // row carries the same data-view/data-id pair every other nav element uses,
  // so the existing delegated click handler navigates it without new code.
  const searchBox = () =>
    `<div class="policy-search" data-search>
       <input type="search" class="policy-search-input" data-search-input autocomplete="off"
              placeholder="${esc('법안·행정명령 검색 (예: 니켈, 수출통제)')}" value="${esc(state.search.query)}">
       <div class="policy-search-results" data-search-results hidden></div>
     </div>`;

  const SEARCH_TYPE_LABELS = { bill: '법안', executive_order: 'EO', regulation: '규정' };
  const SEARCH_TYPE_VIEWS = { bill: 'bill', executive_order: 'eo' };

  const searchResultRow = (item) => {
    const view = SEARCH_TYPE_VIEWS[item.type];
    const typeLabel = SEARCH_TYPE_LABELS[item.type] || item.type;
    const tag = view ? 'button' : 'div';
    const navAttrs = view ? ` type="button" data-view="${esc(view)}" data-id="${esc(item.id)}"` : '';
    return `<${tag} class="policy-search-result${view ? '' : ' is-inert'}"${navAttrs}>
        <span class="policy-search-result-type">${esc(typeLabel)}</span>
        <span class="policy-search-result-title">${esc(item.title || item.id)}</span>
      </${tag}>`;
  };

  function renderSearchMessage(message) {
    const box = host?.querySelector('[data-search-results]');
    if (!box) return;
    box.innerHTML = `<div class="policy-search-empty">${esc(message)}</div>`;
    box.hidden = false;
  }

  function renderSearchResults(body) {
    const box = host?.querySelector('[data-search-results]');
    if (!box) return;
    if (body.unavailable) return renderSearchMessage('검색 기능 준비 중입니다');
    if (!body.items?.length) return renderSearchMessage('검색 결과가 없습니다');
    box.innerHTML = body.items.map(searchResultRow).join('');
    box.hidden = false;
  }

  let searchToken = 0;
  let searchTimer = null;

  async function runSearch(value) {
    const token = ++searchToken;
    try {
      const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(value)}`);
      const body = await res.json().catch(() => null);
      if (token !== searchToken || !host) return;
      if (!res.ok || !body) return renderSearchMessage('검색 중 오류가 발생했습니다');
      renderSearchResults(body);
    } catch {
      if (token !== searchToken || !host) return;
      renderSearchMessage('검색 중 오류가 발생했습니다');
    }
  }

  // Delegated on `host` (not the input itself) because paint() replaces the
  // whole header -- including the input -- on every navigation.
  function onSearchInput(event) {
    const input = event.target.closest('[data-search-input]');
    if (!input || !host.contains(input)) return;
    state.search.query = input.value;
    clearTimeout(searchTimer);
    const box = host.querySelector('[data-search-results]');
    if (!input.value.trim()) {
      searchToken += 1; // drop any in-flight response for the old query
      if (box) box.hidden = true;
      return;
    }
    searchTimer = setTimeout(() => runSearch(input.value.trim()), 300);
  }

  function onSearchKeydown(event) {
    const input = event.target.closest('[data-search-input]');
    if (!input || !host.contains(input)) return;
    if (event.key !== 'Escape') return;
    input.value = '';
    state.search.query = '';
    clearTimeout(searchTimer);
    searchToken += 1;
    const box = host.querySelector('[data-search-results]');
    if (box) box.hidden = true;
  }

  // 미국 is the country the screen is scoped to -- one of several eventually,
  // picked in the nav rather than here, so it labels the surface instead of
  // being a tab. The toggle is only the branch split, and it stays meaningful
  // three levels down because it reads the trail.
  const modeTabs = () => `
    <div class="policy-modes">
      <span class="policy-country">미국</span>
      ${[['congress', '의회'], ['executive', '행정부']].map(([id, label]) => `
        <button type="button" class="policy-mode-btn${trailHas(id) ? ' active' : ''}" data-view="${id}">${label}</button>
      `).join('')}
      ${searchBox()}
    </div>`;

  const shell = (bodyHtml) => `
    <div class="policy-surface-inner">
      <header class="policy-head">
        ${modeTabs()}
        ${crumb()}
      </header>
      ${bodyHtml}
    </div>`;

  /* --------------------------------------------------------------- pieces */

  const stageBadge = (stage) => `<span class="policy-stage-badge">${esc(stageLabel(stage))}</span>`;

  const billRow = (bill) => `
    <button type="button" class="policy-bill-row" data-view="bill" data-id="${esc(bill.bill_id)}">
      <span class="policy-bill-row-id">${esc(bill.bill_id)}</span>
      <span class="policy-bill-row-title">${esc(bill.title)}</span>
      <span class="policy-bill-row-meta">
        ${stageBadge(bill.current_stage)}
        <span class="policy-bill-row-date">${esc(bill.latest_action_date || '')}</span>
      </span>
    </button>`;

  const stageTabs = (tabs, activeStage) => {
    if (!tabs?.length) return '';
    return `<div class="policy-stage-tabs">${tabs.map((t) => {
      const value = t.stage || '';
      const on = value === (activeStage || '');
      return `<button type="button" class="policy-stage-tab${on ? ' active' : ''}" data-stage="${esc(value)}">
                ${esc(t.label)}${typeof t.count === 'number' ? `<span class="policy-stage-count">${t.count}</span>` : ''}
              </button>`;
    }).join('')}</div>`;
  };

  const billListBody = (page, prefix = '') => {
    if (!page) return empty('법안 목록을 불러오지 못했습니다');
    return `${prefix}${stageTabs(buildStageTabs(page.stage_counts), state.stage)}
            ${page.items?.length ? `<div class="policy-bill-list">${page.items.map(billRow).join('')}</div>` : empty('해당 단계의 법안이 없습니다')}`;
  };

  // Blocks carry the full name. The chamber prefix goes, since the blocks are
  // already grouped by chamber, and anything still too long for a tile falls
  // back to its abbreviation (Department of Defense -> DOD).
  const TILE_MAX = 30;

  const committeeLabel = (name) => String(name || '')
    .replace(/^(House|Senate)\s+(Select\s+)?/i, '');

  const fit = (full, short) => (full.length > TILE_MAX && short ? short : full);

  // A flat grid of name-only rectangles -- the layout the sketch uses for
  // "pick one of these" screens, six or so to a row.
  const tileGrid = (items) => (items.length
    ? `<div class="policy-tile-grid">${items.map((t) => `
        <button type="button" class="policy-tile" data-view="${esc(t.view)}" data-id="${esc(t.id)}" title="${esc(t.full || t.label)}">
          <span class="policy-tile-label">${esc(t.label)}</span>
        </button>`).join('')}</div>`
    : empty('목록 준비 중'));

  const committeeTiles = (overview, chamber) => tileGrid(
    (overview?.congress_overview?.committees || [])
      .filter((c) => c.chamber === chamber)
      .map((c) => ({
        view: 'committee', id: c.committee_id, full: c.name,
        label: fit(committeeLabel(c.name), c.short_name),
      })),
  );

  const agencyTiles = (overview, kind) => tileGrid(
    (overview?.executive_overview?.agencies || [])
      .filter((a) => a.agency_type === kind)
      .map((a) => ({ view: 'agency', id: a.agency_id, full: a.name, label: fit(a.name, a.short_name) })),
  );

  const policyAreaTiles = (overview) => tileGrid(
    (overview?.policy_areas || [])
      .map((a) => ({ view: 'area', id: a.policy_area_id, full: a.name, label: a.name })),
  );

  const cfrTiles = (overview) => tileGrid(
    (overview?.cfr_titles || [])
      .map((t) => ({
        view: 'cfr', id: t.title_number,
        full: `Title ${t.title_number} — ${t.name}`,
        label: `${t.title_number}. ${t.name}`,
      })),
  );

  // Regulations are external-link-only by design: no internal detail page and
  // no abstract in the list -- title, type and effective date only.
  const renderRegulations = (regs) => `
    <ul class="policy-reg-list">${regs.map((r) => `
      <li>
        <a class="policy-reg-row" href="${esc(r.federal_register_url)}" target="_blank" rel="noopener noreferrer">
          <span class="policy-reg-title">${esc(r.title)}</span>
          <span class="policy-reg-meta">
            <span class="policy-tag">${esc(r.document_type || '규제')}</span>
            <span>시행 ${esc(r.effective_on || '-')}</span>
          </span>
        </a>
      </li>`).join('')}</ul>`;

  const leaderRow = (label, person, placeholder) => `
    <div class="policy-leader">
      <span class="policy-leader-label">${esc(label)}</span>
      <span class="policy-leader-value${person ? '' : ' is-placeholder'}">${esc(person?.name || placeholder)}</span>
    </div>`;

  /* ---------------------------------------------------------------- views */

  // Branch level -- the committees and the CRS policy areas, each a way in.
  function viewCongress(_id, overview) {
    const hasJoint = (overview?.congress_overview?.committees || []).some((c) => c.chamber === 'joint');
    return shell(`
      ${card(`상임위 (${CHAMBER_LABELS.house})`, committeeTiles(overview, 'house'))}
      ${card(`상임위 (${CHAMBER_LABELS.senate})`, committeeTiles(overview, 'senate'))}
      ${hasJoint ? card(`상임위 (${CHAMBER_LABELS.joint})`, committeeTiles(overview, 'joint')) : ''}
      ${collapsibleCard('crs', 'CRS 정책분야', policyAreaTiles(overview), (overview?.policy_areas || []).length)}
    `);
  }

  function viewCommittee(committeeId, overview, extra) {
    const listed = overview?.congress_overview?.committees?.find((c) => c.committee_id === committeeId);
    if (!listed) return shell(empty('위원회를 찾을 수 없습니다'));

    const { detail, billPage } = extra;

    const leadership = `
      ${leaderRow('위원장', null, '위원장 정보 준비 중')}
      ${leaderRow('간사', null, '간사 정보 준비 중')}`;

    const agencies = listed.agencies || [];
    const agencyList = agencies.length
      ? `<div class="policy-tag-row">${agencies.map((a) => `<span class="policy-tag">${esc(a)}</span>`).join('')}</div>`
      : empty('검증된 담당기관 매핑 준비 중');

    const subs = detail?.subcommittees || [];
    const subList = subs.length
      ? `<ul class="policy-sub-list">${subs.map((s) => `
          <li><span class="policy-sub-name">${esc(s.name)}</span>
            <span class="policy-sub-meta is-placeholder">${esc('회의 일정 준비 중')}</span>
          </li>`).join('')}</ul>`
      : empty('소위원회 정보 없음');

    // Bills lead: they are what the screen is for. Membership and
    // subcommittees are reference material, so they sit alongside on the right.
    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card('소관 법안', billListBody(billPage))}
        </div>
        <div class="policy-col">
          ${card(listed.name, `
            ${listed.jurisdiction_summary ? `<p class="policy-prose">${esc(listed.jurisdiction_summary)}</p>` : ''}
            <div class="policy-leaders">${leadership}</div>
            ${listed.official_url ? `<a class="policy-external" href="${esc(listed.official_url)}" target="_blank" rel="noopener noreferrer">공식 사이트</a>` : ''}
          `)}
          ${card('담당 기관', agencyList)}
          ${card('소위원회', subList)}
        </div>
      </div>`);
  }

  // A CRS policy area: every bill filed under it.
  function viewPolicyArea(areaId, overview, extra) {
    const listed = (overview?.policy_areas || []).find((a) => a.policy_area_id === areaId);
    if (!listed) return shell(empty('분류를 찾을 수 없습니다'));
    return shell(card(`${listed.name} · 관련 법안`, billListBody(extra.billPage)));
  }

  // A CFR title lists the regulations filed under it. Executive orders are
  // deliberately NOT classified against a title directly -- the contract
  // (docs/api-spec.md, "분류 개수") says an EO surfaces here only through a
  // regulation of its own that carries the CFR reference, so the orders shown
  // are the ones reached that way.
  function viewCfrTitle(titleNumber, overview, extra) {
    const title = extra.cfrTitle;
    if (!title) return shell(empty('분류를 찾을 수 없습니다'));

    const heading = `Title ${title.title_number} · ${title.name}`;
    if (title.reserved) return shell(card(heading, empty('유보된 분류입니다')));

    const regs = title.regulations || [];
    const viaRegulations = title.executive_orders || [];

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card('관련 규제', regs.length
            ? renderRegulations(regs)
            : empty('이 분류의 규제·행정명령 준비 중'))}
        </div>
        <div class="policy-col">
          ${card('관련 행정명령', viaRegulations.length
            ? `<div class="policy-eo-list">${viaRegulations.map(eoRibbon).join('')}</div>`
            : empty('이 분류의 규제를 통해 연결된 행정명령 없음'))}
        </div>
      </div>`);
  }

  function billPanel(bill) {
    const votes = bill.votes || [];

    const voteBody = votes.length
      ? votes.map((v) => `
          <div class="policy-vote">
            <div class="policy-vote-head">
              <span>${esc(CHAMBER_LABELS[v.chamber] || v.chamber)} · ${esc(v.question)}</span>
              <span class="policy-vote-result">${esc(v.result)}</span>
            </div>
            <div class="policy-vote-counts">
              <span class="yea">찬성 ${esc(v.yea_count)}</span>
              <span class="nay">반대 ${esc(v.nay_count)}</span>
              <span>기권 ${esc(v.present_count)}</span>
              <span>불참 ${esc(v.not_voting_count)}</span>
            </div>
            <div class="policy-vote-foot">
              <span>${esc(v.vote_date)}</span>
              ${v.source_url ? `<a class="policy-external" href="${esc(v.source_url)}" target="_blank" rel="noopener noreferrer">원문</a>` : ''}
            </div>
          </div>`).join('')
      : empty('기록 표결 없음');

    // Official relations come before AI-detected ones, per bill_detail.ui_rules.
    const related = (bill.official_related_bills || []).map((r) => `
      <li>${r.title
        ? `<button type="button" class="policy-link" data-view="bill" data-id="${esc(r.bill_id)}">${esc(r.title)}</button>`
        : `<span>${esc(r.bill_id)}</span>`}
        <span class="policy-tag">공식 · ${esc(r.relation_type)}</span></li>`).join('');

    const similar = (bill.similar_bills || []).map((r) => `
      <li>${r.title
        ? `<button type="button" class="policy-link" data-view="bill" data-id="${esc(r.bill_id)}">${esc(r.title)}</button>`
        : `<span>${esc(r.bill_id)}</span>`}
        <span class="policy-tag is-ai">AI 유사 ${typeof r.similarity_score === 'number' ? r.similarity_score.toFixed(2) : ''}</span></li>`).join('');

    const relatedBody = (related || similar)
      ? `<ul class="policy-related">${related}${similar}</ul>`
      : empty('관련 법안 없음');

    return `<section class="policy-block policy-bill-panel">
      <h3 class="policy-block-title">${esc(bill.title)}</h3>
      <div class="policy-bill-meta">
        ${stageBadge(bill.current_stage)}
        ${bill.sponsor ? `<span>발의자 ${esc(bill.sponsor)}</span>` : ''}
        ${bill.introduced_date ? `<span>발의일 ${esc(bill.introduced_date)}</span>` : ''}
      </div>
      ${bill.current_status ? `<p class="policy-prose">${esc(bill.current_status)}</p>` : ''}
      ${bill.summary ? `<p class="policy-prose">${esc(bill.summary)}</p>` : ''}
      <div class="policy-subblock"><h4>표결</h4>${voteBody}</div>
      <div class="policy-subblock"><h4>관련 법안</h4>${relatedBody}</div>
      ${bill.congress_url ? `<a class="policy-external" href="${esc(bill.congress_url)}" target="_blank" rel="noopener noreferrer">congress.gov</a>` : ''}
    </section>`;
  }

  function viewBill(billId, overview, extra) {
    const bill = extra.bill;
    if (!bill) return shell(empty('법안을 찾을 수 없습니다'));

    const committees = (bill.committees || []).map((c) => `
      <button type="button" class="policy-chip is-compact" data-view="committee" data-id="${esc(c.committee_id)}">
        <span class="policy-chip-name">${esc(c.name)}</span>
      </button>`).join('');

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">${billPanel(bill)}</div>
        <div class="policy-col">
          ${card('회부 위원회', committees ? `<div class="policy-chip-row">${committees}</div>` : empty('위원회 정보 없음'))}
        </div>
      </div>`);
  }

  const eoRibbon = (o) => `
    <button type="button" class="policy-eo-ribbon" data-view="eo" data-id="${esc(o.eo_number)}">
      <span class="policy-eo-num">EO ${esc(o.eo_number)}</span>
      <span class="policy-eo-title">${esc(o.title)}</span>
      <span class="policy-eo-date">${esc(o.signed_date || '')}</span>
    </button>`;

  // Level 2 -- the agencies, each a way into its own orders.
  // Branch level -- departments and independent agencies kept apart, plus the
  // Federal Register's CFR titles as the other way in.
  function viewExecutive(_id, overview) {
    const agencies = overview?.executive_overview?.agencies || [];
    const hasKind = (kind) => agencies.some((a) => a.agency_type === kind);

    return shell(`
      ${hasKind('eop') ? card('대통령실', agencyTiles(overview, 'eop')) : ''}
      ${hasKind('department') ? card('부처 (내청)', agencyTiles(overview, 'department')) : ''}
      ${hasKind('independent') ? card('독립기관 (외청)', agencyTiles(overview, 'independent')) : ''}
      ${collapsibleCard('cfr', '연방관보 분류 · CFR Title', cfrTiles(overview), (overview?.cfr_titles || []).length)}
    `);
  }

  // Level 3 -- one agency: its leadership slot and its orders, the box the
  // wireframe draws with 재무부 over EO1/EO2. Bottom-right stays blank -- no
  // sub-agency directory here; a sub-agency's own screen is where it belongs.
  function viewAgency(agencyId, overview, extra) {
    const agency = overview?.executive_overview?.agencies?.find((a) => a.agency_id === agencyId);
    if (!agency) return shell(empty('기관을 찾을 수 없습니다'));

    const orders = extra.eoPage?.items || [];
    const lead = (label, value) => `
      <div class="policy-leader">
        <span class="policy-leader-label">${esc(label)}</span>
        <span class="policy-leader-value is-placeholder">${esc(value)}</span>
      </div>`;
    const placeholder = '장관 정보 준비 중';

    // Orders lead, the same way bills do on a committee: they are what the
    // screen is for, and the leadership block is reference beside them.
    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card('행정명령', orders.length
            ? `<div class="policy-eo-list">${orders.map(eoRibbon).join('')}</div>`
            : empty('등록된 행정명령 없음'))}
        </div>
        <div class="policy-col">
          ${card(agency.name, `
            ${agency.short_name ? `<p class="policy-prose">${esc(agency.short_name)}</p>` : ''}
            <div class="policy-leaders">
              ${lead('장관', placeholder)}
              ${lead('부장관', placeholder)}
            </div>
          `)}
        </div>
      </div>`);
  }

  function viewEO(eoNumber, overview, extra) {
    const eo = extra.eo;
    if (!eo) return shell(empty('행정명령을 찾을 수 없습니다'));

    // An EO cites statutes, not bill numbers. Only link inward when the
    // citation actually resolves to a bill (bill_id present); otherwise fall
    // back to the official external source.
    const authorities = (eo.legal_authorities || []).length
      ? `<ul class="policy-authority-list">${eo.legal_authorities.map((a) => {
          const badge = a.verification_status ? `<span class="policy-tag">${esc(a.verification_status)}</span>` : '';
          return a.bill_id
            ? `<li class="is-internal">
                 <button type="button" class="policy-link" data-view="bill" data-id="${esc(a.bill_id)}">${esc(a.citation)}</button>
                 <span class="policy-authority-hint">연계 법안 ${esc(a.bill_id)}</span>${badge}
               </li>`
            : `<li><a class="policy-external" href="${esc(a.official_url)}" target="_blank" rel="noopener noreferrer">${esc(a.citation)}</a>${badge}</li>`;
        }).join('')}</ul>`
      : empty('근거 법령 정보 없음');

    const regulations = (eo.related_regulations || []).length
      ? renderRegulations(eo.related_regulations)
      : empty('관련 규제 없음');

    const agencies = (eo.agencies || []).map((a) => `<span class="policy-tag">${esc(a.name)}</span>`).join('');

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card(`EO ${eo.eo_number}`, `
            <p class="policy-eo-headline">${esc(eo.title)}</p>
            <div class="policy-bill-meta">
              <span>서명 ${esc(eo.signed_date || '-')}</span>
              <span>공포 ${esc(eo.publication_date || '-')}</span>
            </div>
            ${agencies ? `<div class="policy-tag-row">${agencies}</div>` : ''}
            ${eo.summary ? `<p class="policy-prose">${esc(eo.summary)}</p>` : `<p class="policy-empty">${esc('상세 정보 준비 중')}</p>`}
            <div class="policy-link-row">
              ${eo.federal_register_url ? `<a class="policy-external" href="${esc(eo.federal_register_url)}" target="_blank" rel="noopener noreferrer">Federal Register</a>` : ''}
              ${eo.executive_order_url ? `<a class="policy-external" href="${esc(eo.executive_order_url)}" target="_blank" rel="noopener noreferrer">White House</a>` : ''}
            </div>
          `)}
        </div>
        <div class="policy-col">
          ${card('근거 법령', authorities)}
          ${card('하위 규제', regulations)}
        </div>
      </div>`);
  }

  /* -------------------------------------------------------------- routing */

  // Where each level sits, so a destination reached from anywhere still lands
  // under the right ancestors: picking a bill off the level-1 hub rebuilds the
  // 미국 › 의회 path rather than leaving a one-entry breadcrumb.
  //
  // A leaf's parent depends on the route taken -- a bill opened from a
  // committee belongs under that committee (미국 › 의회 › 상임위 › 법률),
  // while one opened straight off the hub has no committee to sit under. So
  // those two resolve against the trail as it stands at click time.
  const PARENT = {
    congress: null,
    executive: null,
    committee: 'congress',
    area: 'congress',
    agency: 'executive',
    cfr: 'executive',
    bill: () => (trailHas('committee') ? 'committee' : trailHas('area') ? 'area' : 'congress'),
    eo: () => (trailHas('agency') ? 'agency' : trailHas('cfr') ? 'cfr' : 'executive'),
  };

  const parentOf = (view) => {
    const p = PARENT[view];
    return typeof p === 'function' ? p() : p;
  };

  function labelFor(view, id, overview, extra) {
    switch (view) {
      case 'congress': return '의회';
      case 'executive': return '행정부';
      case 'committee':
        return overview?.congress_overview?.committees?.find((c) => c.committee_id === id)?.name || '상임위';
      case 'agency':
        return overview?.executive_overview?.agencies?.find((a) => a.agency_id === id)?.name || '기관';
      case 'area':
        return (overview?.policy_areas || []).find((a) => a.policy_area_id === id)?.name || '정책분야';
      case 'cfr': {
        const t = (overview?.cfr_titles || []).find((x) => String(x.title_number) === String(id));
        return t ? `Title ${t.title_number} · ${t.name}` : `Title ${id}`;
      }
      case 'bill':
        return extra?.bill?.title || '법률';
      case 'eo':
        return `EO ${id}`;
      default: return view;
    }
  }

  // Fetch whatever the destination view needs beyond the overview blob, which
  // is always already loaded by the time this runs. Returned as a plain
  // object so each view function stays a pure render step over its own data,
  // the same shape the mock-fixture version had.
  async function fetchViewData(view, id) {
    switch (view) {
      case 'committee': {
        const [detail, billPage] = await Promise.all([
          loadCommittee(id),
          loadBillList({ committee_id: id, stage: state.stage }),
        ]);
        return { detail, billPage };
      }
      case 'area': {
        const billPage = await loadBillList({ policy_area_id: id, stage: state.stage });
        return { billPage };
      }
      case 'cfr':
        return { cfrTitle: await loadCfrTitle(id) };
      case 'bill':
        return { bill: await loadBill(id) };
      case 'agency':
        return { eoPage: await loadEoList(id) };
      case 'eo':
        return { eo: await loadEo(id) };
      default:
        return {};
    }
  }

  const VIEWS = {
    congress: viewCongress,
    executive: viewExecutive,
    committee: viewCommittee,
    agency: viewAgency,
    area: viewPolicyArea,
    cfr: viewCfrTitle,
    bill: viewBill,
    eo: viewEO,
  };

  let host = null;
  let overview = null;
  // Data for the current leaf view, populated by go()/refresh() before paint().
  let viewData = {};
  // Guards a render() call whose async work resolves after a newer one started.
  let renderToken = 0;

  function paint() {
    if (!host) return;
    const { view, id } = current();
    host.innerHTML = (VIEWS[view] || viewCongress)(id, overview, viewData);
    host.scrollTop = 0;
  }

  // Build the ancestor chain for a destination, keeping whatever the current
  // trail already holds for those levels (so a bill opened from a committee
  // keeps that committee, not just a bare 의회).
  function trailTo(view, id, extraForLabel) {
    const chain = [];
    for (let v = view; v; v = parentOf(v)) chain.unshift(v);
    return chain.map((v) => {
      if (v === view) return { view: v, id, label: labelFor(v, id, overview, extraForLabel) };
      const existing = state.trail.find((t) => t.view === v);
      return existing || { view: v, id: undefined, label: labelFor(v, undefined, overview) };
    });
  }

  async function go(view, id) {
    const token = renderToken;
    state.stage = '';
    let extra = {};
    try {
      extra = await fetchViewData(view, id);
    } catch (err) {
      console.error(`Failed to load policy view "${view}":`, err);
      if (token !== renderToken || !host) return;
      state.trail = trailTo(view, id, extra);
      viewData = {};
      host.innerHTML = shell(empty('데이터를 불러오지 못했습니다'));
      return;
    }
    if (token !== renderToken || !host) return; // a later navigation won the race
    state.trail = trailTo(view, id, extra);
    viewData = extra;
    paint();
  }

  // Re-fetches the current leaf (used when the stage filter changes) without
  // touching the trail.
  async function refresh() {
    const token = renderToken;
    const { view, id } = current();
    try {
      const extra = await fetchViewData(view, id);
      if (token !== renderToken || !host) return;
      viewData = extra;
      paint();
    } catch (err) {
      console.error('Failed to refresh policy view:', err);
    }
  }

  function onClick(event) {
    const searchWrap = host.querySelector('[data-search]');
    if (searchWrap && !searchWrap.contains(event.target)) {
      const box = searchWrap.querySelector('[data-search-results]');
      if (box) box.hidden = true;
    }
    const searchResult = event.target.closest('.policy-search-result');
    if (searchResult && host.contains(searchResult)) {
      const box = host.querySelector('[data-search-results]');
      const input = host.querySelector('[data-search-input]');
      if (box) box.hidden = true;
      if (input) input.value = '';
      state.search.query = '';
      // no early return: a clickable result still has [data-view]/[data-id]
      // and falls through to the generic nav handling below.
    }
    const collapse = event.target.closest('[data-collapse]');
    if (collapse && host.contains(collapse)) {
      const key = collapse.dataset.collapse;
      state.open[key] = !state.open[key];
      paint();
      return;
    }
    const stageTab = event.target.closest('.policy-stage-tab');
    if (stageTab && host.contains(stageTab)) {
      state.stage = stageTab.dataset.stage || '';
      refresh();
      return;
    }
    const up = event.target.closest('.policy-crumb-link');
    if (up && host.contains(up)) {
      state.trail = state.trail.slice(0, Number(up.dataset.depth) + 1);
      state.stage = '';
      go(current().view, current().id);
      return;
    }
    const nav = event.target.closest('[data-view]');
    if (!nav || !host.contains(nav)) return;
    go(nav.dataset.view, nav.dataset.id);
  }

  // 정책 › 미국 lands on the legislative side; the branch toggle switches it.
  const TARGET_VIEWS = {
    'us-policy-hub': 'congress',
    'us-congress-overview': 'congress',
    'us-executive': 'executive',
  };

  async function render(target, surface) {
    host = surface;
    const token = ++renderToken;
    host.classList.add('policy-surface');
    host.dataset.policyTarget = target;
    host.innerHTML = `<div class="policy-loading">${esc('정책 데이터를 불러오는 중')}</div>`;

    try {
      overview = await loadOverview();
    } catch (err) {
      console.error('Failed to load policy overview:', err);
      if (host.dataset.policyTarget !== target || token !== renderToken) return;
      host.innerHTML = `<div class="policy-surface-inner">${empty('정책 데이터를 불러오지 못했습니다')}</div>`;
      return;
    }
    if (host.dataset.policyTarget !== target || token !== renderToken) return; // a later view won the race

    // Entering from the top menu starts a fresh trail at that level.
    state.trail = [];
    await go(TARGET_VIEWS[target] || 'congress');

    host.removeEventListener('click', onClick);
    host.addEventListener('click', onClick);
    host.removeEventListener('input', onSearchInput);
    host.addEventListener('input', onSearchInput);
    host.removeEventListener('keydown', onSearchKeydown);
    host.addEventListener('keydown', onSearchKeydown);
  }

  function unmount(surface) {
    if (!surface) return;
    renderToken += 1; // invalidate any in-flight fetch from this render
    searchToken += 1;
    clearTimeout(searchTimer);
    surface.removeEventListener('click', onClick);
    surface.removeEventListener('input', onSearchInput);
    surface.removeEventListener('keydown', onSearchKeydown);
    surface.classList.remove('policy-surface');
    delete surface.dataset.policyTarget;
    surface.innerHTML = '';
    host = null;
  }

  // app.js routes the 미국 정책 nav targets through `window.USPolicy`; a bare
  // `const` in a classic script never reaches window on its own.
  window.USPolicy = { render, unmount };
})();
