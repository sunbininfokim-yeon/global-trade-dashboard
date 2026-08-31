// US Policy Dashboard
//
// Unlike the commodity/climate views, policy has no map to show -- it is a
// document-style screen, so it takes the full centre surface (#chart-view) the
// same way shipping and finance do, instead of the narrow right pane.
//
// Data currently comes from the UI fixture at
// New for anti/public/data/ui-policy-mock-data.json. Everything in it is
// marked is_mock: true and must never be presented as live U.S. government
// data. TODO(real-api): swap loadData() for the /api/us/* endpoints described
// in docs/api-spec.md -- the response schema is identical, so the render code
// below does not change.

(() => {
  const DATA_URL = '/public/data/ui-policy-mock-data.json';

  let DATA = null;
  let loadPromise = null;

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

  // A stage tab's value is either empty (= every stage) or a comma-separated
  // OR list, e.g. "vetoed,failed".
  const filterByStage = (bills, stage) => {
    if (!bills) return [];
    if (!stage) return bills;
    const wanted = String(stage).split(',').map((s) => s.trim()).filter(Boolean);
    return wanted.length ? bills.filter((b) => wanted.includes(b.current_stage)) : bills;
  };

  // Only bills the dashboard can actually open a detail view for are linkable.
  const resolveBill = (billId) => {
    if (!billId) return null;
    if (DATA?.bill_detail && String(DATA.bill_detail.bill_id) === String(billId)) return DATA.bill_detail;
    return null;
  };

  const findBillSummary = (billId) =>
    DATA?.policy_hub?.summary_cards?.find((b) => b.bill_id === billId)
    || DATA?.committee_detail?.items?.find((b) => b.bill_id === billId)
    || null;

  const uiState = (key, fallback) => DATA?.ui_states?.[key]?.title || fallback;

  async function loadData() {
    if (DATA) return DATA;
    if (loadPromise) return loadPromise;
    // The Worker serves `New for anti` with not_found_handling=single-page-application,
    // so a missing asset comes back as index.html with HTTP 200, not a 404 --
    // fetch neither rejects nor reports !ok and only the parse fails. Validate
    // the body as JSON so a missing asset reports what actually went wrong.
    loadPromise = (async () => {
      try {
        const res = await fetch(DATA_URL);
        const body = res.ok ? await res.text() : null;
        if (!body) return null;
        try {
          DATA = JSON.parse(body);
        } catch {
          console.error(
            `Policy data at ${DATA_URL} is not JSON (HTTP ${res.status}, ${res.headers.get('content-type')}) --`,
            'the asset is most likely missing and the SPA fallback returned index.html.',
          );
        }
      } catch (err) {
        console.error('Failed to load policy data:', err);
      }
      return DATA;
    })();
    return loadPromise;
  }

  /* ---------------------------------------------------------------- shell */

  // Navigation is a drill-down trail, four levels deep:
  //   미국 › 의회 › 상임위 › 법률
  //   미국 › 행정부 › 부처 › 행정명령
  // The trail doubles as the breadcrumb, so every ancestor stays reachable and
  // a screen never has to guess where it was opened from.
  const state = { trail: [], stage: '', open: {} };

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

  // The mock fixture keeps search switched off (meta.search.visible=false);
  // the control is rendered disabled so the layout matches the final screen.
  const searchBox = () => {
    if (DATA?.meta?.search?.visible) return '';
    return `<div class="policy-search is-disabled" title="${esc(uiState('no_search', '검색 기능은 준비 중'))}">
              <input type="search" placeholder="${esc(uiState('no_search', '검색 기능은 준비 중'))}" disabled>
            </div>`;
  };

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

  const mockNotice = () => (DATA?.meta?.is_mock
    ? `<p class="policy-mock-notice">표시된 내용은 UI 확인용 예시 데이터입니다. 실제 미국 정부 자료가 아닙니다.</p>`
    : '');

  const shell = (bodyHtml) => `
    <div class="policy-surface-inner">
      <header class="policy-head">
        ${modeTabs()}
        ${crumb()}
      </header>
      ${mockNotice()}
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

  const committeeTiles = (chamber) => tileGrid(
    (DATA?.congress_overview?.committees || [])
      .filter((c) => c.chamber === chamber)
      .map((c) => ({
        view: 'committee', id: c.committee_id, full: c.name,
        label: fit(committeeLabel(c.name), c.short_name),
      })),
  );

  // The Federal Register API does not classify agencies -- it exposes parent_id,
  // but Cabinet departments and independent agencies are both top-level, so
  // that cannot separate them. The backend is meant to send agency_type
  // (docs/api-spec.md); until it does, derive it, or the 부처/외청 blocks come
  // back empty against live data. The Cabinet is a closed, stable set of 15,
  // and EOP components are named, so only the residue is a guess.
  const EOP_AGENCIES = new Set([
    'executive office of the president',
    'office of management and budget',
    'office of the united states trade representative',
    'office of the u.s. trade representative',
    'office of science and technology policy',
    'council of economic advisers',
    'national security council',
    'office of national drug control policy',
  ]);

  const agencyType = (a) => {
    if (a.agency_type) return a.agency_type;
    const name = String(a.name || '').trim().toLowerCase();
    if (EOP_AGENCIES.has(name)) return 'eop';
    if (/^(u\.s\.\s+)?department of\b/.test(name)) return 'department';
    return 'independent';
  };

  const agencyTiles = (kind) => tileGrid(
    (DATA?.executive_overview?.agencies || [])
      .filter((a) => (kind ? agencyType(a) === kind : true))
      .map((a) => ({ view: 'agency', id: a.agency_id, full: a.name, label: fit(a.name, a.short_name) })),
  );

  const policyAreaTiles = () => tileGrid(
    (DATA?.policy_areas || [])
      .map((a) => ({ view: 'area', id: a.policy_area_id, full: a.name, label: a.name })),
  );

  const cfrTiles = () => tileGrid(
    (DATA?.cfr_titles || [])
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
  function viewCongress() {
    const co = DATA?.congress_overview;
    if (!co) return shell(empty('의회 데이터를 불러올 수 없습니다'));

    const hasJoint = (co.committees || []).some((c) => c.chamber === 'joint');

    return shell(`
      ${card(`상임위 (${CHAMBER_LABELS.house})`, committeeTiles('house'))}
      ${card(`상임위 (${CHAMBER_LABELS.senate})`, committeeTiles('senate'))}
      ${hasJoint ? card(`상임위 (${CHAMBER_LABELS.joint})`, committeeTiles('joint')) : ''}
      ${collapsibleCard('crs', 'CRS 정책분야', policyAreaTiles(), (DATA?.policy_areas || []).length)}
    `);
  }

  function viewCommittee(committeeId) {
    const detail = DATA?.committee_detail;
    const listed = DATA?.congress_overview?.committees?.find((c) => c.committee_id === committeeId);
    // The fixture carries one fully detailed committee; others fall back to
    // their overview record so the screen still opens.
    const comm = (detail?.committee?.committee_id === committeeId ? detail.committee : null) || listed;
    if (!comm) return shell(empty('위원회를 찾을 수 없습니다'));

    const hasDetail = detail?.committee?.committee_id === committeeId;
    const items = hasDetail ? filterByStage(detail.items, state.stage) : [];
    const subs = comm.subcommittees || [];

    const leadership = `
      ${leaderRow('위원장', comm.chair, comm.chair_placeholder || uiState('empty_chair', '위원장 정보 준비 중'))}
      ${leaderRow('간사', comm.ranking_member, comm.ranking_member_placeholder || uiState('empty_ranking_member', '간사 정보 준비 중'))}`;

    // The overview record carries the verified agency mapping; the detail
    // record does not, so fall back to it when the two differ.
    const agencies = comm.agencies || listed?.agencies || [];
    const agencyList = agencies.length
      ? `<div class="policy-tag-row">${agencies.map((a) => `<span class="policy-tag">${esc(a)}</span>`).join('')}</div>`
      : empty(uiState('empty_committee_agencies', '검증된 담당기관 매핑 준비 중'));

    const subList = subs.length
      ? `<ul class="policy-sub-list">${subs.map((s) => `
          <li><span class="policy-sub-name">${esc(s.name)}</span>
            <span class="policy-sub-meta is-placeholder">${esc(s.meetings_placeholder || uiState('empty_subcommittee_meetings', '회의 일정 준비 중'))}</span>
          </li>`).join('')}</ul>`
      : empty('소위원회 정보 준비 중');

    const billsBody = hasDetail
      ? `${stageTabs(detail.stage_tabs, state.stage)}
         ${items.length ? `<div class="policy-bill-list">${items.map(billRow).join('')}</div>` : empty('해당 단계의 법안이 없습니다')}`
      : empty('이 위원회의 법안 목록 준비 중');

    // Bills lead: they are what the screen is for. Membership and
    // subcommittees are reference material, so they sit alongside on the right.
    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card('소관 법안', billsBody)}
        </div>
        <div class="policy-col">
          ${card(comm.name, `
            ${comm.jurisdiction_summary ? `<p class="policy-prose">${esc(comm.jurisdiction_summary)}</p>` : ''}
            <div class="policy-leaders">${leadership}</div>
            ${comm.official_url ? `<a class="policy-external" href="${esc(comm.official_url)}" target="_blank" rel="noopener noreferrer">공식 사이트</a>` : ''}
          `)}
          ${card('담당 기관', agencyList)}
          ${card('소위원회', subList)}
        </div>
      </div>`);
  }

  // A CRS policy area: every bill filed under it. The fixture only carries a
  // handful, so most areas legitimately come back empty.
  function viewPolicyArea(areaId) {
    const listed = (DATA?.policy_areas || []).find((a) => a.policy_area_id === areaId);
    const detail = DATA?.policy_area_detail;
    const name = listed?.name
      || (detail?.policy_area?.policy_area_id === areaId ? detail.policy_area.name : null)
      || areaId;

    // Bills reach an area either through the curated detail list or through
    // their own policy_area field.
    const curated = detail?.policy_area?.policy_area_id === areaId ? (detail.items || []) : [];
    const pool = DATA?.policy_hub?.summary_cards || [];
    const matched = pool.filter((b) =>
      curated.includes(b.bill_id) || b.policy_area?.policy_area_id === areaId);
    const bills = filterByStage(matched, state.stage);

    const body = matched.length
      ? `${stageTabs(DATA?.committee_detail?.stage_tabs, state.stage)}
         ${bills.length ? `<div class="policy-bill-list">${bills.map(billRow).join('')}</div>` : empty('해당 단계의 법안이 없습니다')}`
      : empty(uiState('empty_policy_area', '이 분류의 법안 준비 중'));

    return shell(card(`${name} · 관련 법안`, body));
  }

  // A CFR title: the regulations filed under it, and the orders that reach
  // them. Regulations stay external-link-only here too.
  function viewCfrTitle(titleNumber) {
    const title = (DATA?.cfr_titles || []).find((t) => String(t.title_number) === String(titleNumber));
    if (!title) return shell(empty('분류를 찾을 수 없습니다'));

    const heading = `Title ${title.title_number} · ${title.name}`;
    if (title.reserved) return shell(card(heading, empty('유보된 분류입니다')));

    // The fixture has no title↔regulation mapping yet, so anything the EO
    // detail carries is all there is to show.
    // TODO(real-api): GET /api/us/regulations?cfr_title= supplies this.
    const regs = DATA?.executive_order_detail?.related_regulations || [];
    const orders = DATA?.executive_overview?.executive_orders || [];

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card(`${heading} · 관련 규제`, title.regulation_count && regs.length
            ? renderRegulations(regs)
            : empty(uiState('empty_cfr_title', '이 분류의 규제·행정명령 준비 중')))}
        </div>
        <div class="policy-col">
          ${card('관련 행정명령', title.regulation_count && orders.length
            ? `<div class="policy-eo-list">${orders.map(eoRibbon).join('')}</div>`
            : empty(uiState('empty_cfr_title', '이 분류의 규제·행정명령 준비 중')))}
        </div>
      </div>`);
  }

  function billPanel(bill, { compact = false } = {}) {
    const full = resolveBill(bill.bill_id);
    const votes = full?.votes || [];

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
      : empty(uiState('empty_vote', '기록 표결 없음'));

    // Official relations come before AI-detected ones, per bill_detail.ui_rules.
    const related = (full?.official_related_bills || []).map((r) => `
      <li>${resolveBill(r.bill_id)
        ? `<button type="button" class="policy-link" data-view="bill" data-id="${esc(r.bill_id)}">${esc(r.title)}</button>`
        : `<span>${esc(r.title)}</span>`}
        <span class="policy-tag">공식 · ${esc(r.relation_type)}</span></li>`).join('');

    const similar = (full?.similar_bills || []).map((r) => `
      <li>${resolveBill(r.bill_id)
        ? `<button type="button" class="policy-link" data-view="bill" data-id="${esc(r.bill_id)}">${esc(r.title)}</button>`
        : `<span>${esc(r.title)}</span>`}
        <span class="policy-tag is-ai">AI 유사 ${typeof r.similarity_score === 'number' ? r.similarity_score.toFixed(2) : ''}</span></li>`).join('');

    const relatedBody = (related || similar)
      ? `<ul class="policy-related">${related}${similar}</ul>`
      : empty('관련 법안 없음');

    const meta = full || bill;

    return `<section class="policy-block policy-bill-panel${compact ? ' is-compact' : ''}">
      <h3 class="policy-block-title">${esc(meta.title)}</h3>
      <div class="policy-bill-meta">
        ${stageBadge(meta.current_stage)}
        ${meta.sponsor ? `<span>발의자 ${esc(meta.sponsor)}</span>` : ''}
        ${meta.introduced_date ? `<span>발의일 ${esc(meta.introduced_date)}</span>` : ''}
      </div>
      ${meta.current_status ? `<p class="policy-prose">${esc(meta.current_status)}</p>` : ''}
      ${meta.summary ? `<p class="policy-prose">${esc(meta.summary)}</p>` : ''}
      ${full ? `<div class="policy-subblock"><h4>표결</h4>${voteBody}</div>` : ''}
      ${full ? `<div class="policy-subblock"><h4>관련 법안</h4>${relatedBody}</div>` : ''}
      ${meta.congress_url ? `<a class="policy-external" href="${esc(meta.congress_url)}" target="_blank" rel="noopener noreferrer">congress.gov</a>` : ''}
      ${full ? '' : `<p class="policy-empty">상세 정보 준비 중</p>`}
    </section>`;
  }

  function viewBill(billId) {
    const bill = resolveBill(billId) || findBillSummary(billId);
    if (!bill) return shell(empty('법안을 찾을 수 없습니다'));

    const committees = (resolveBill(billId)?.committees || []).map((c) => `
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

  const ordersOf = (agencyId) =>
    (DATA?.executive_overview?.executive_orders || []).filter((o) => o.agency_id === agencyId);

  const eoRibbon = (o) => `
    <button type="button" class="policy-eo-ribbon" data-view="eo" data-id="${esc(o.eo_number)}">
      <span class="policy-eo-num">EO ${esc(o.eo_number)}</span>
      <span class="policy-eo-title">${esc(o.title)}</span>
      <span class="policy-eo-date">${esc(o.signed_date || '')}</span>
    </button>`;

  // Level 2 -- the agencies, each a way into its own orders.
  // Branch level -- departments and independent agencies kept apart, plus the
  // Federal Register's CFR titles as the other way in.
  function viewExecutive() {
    const eo = DATA?.executive_overview;
    if (!eo) return shell(empty('행정부 데이터를 불러올 수 없습니다'));

    const hasKind = (kind) => (eo.agencies || []).some((a) => agencyType(a) === kind);

    return shell(`
      ${hasKind('eop') ? card('대통령실', agencyTiles('eop')) : ''}
      ${hasKind('department') ? card('부처 (내청)', agencyTiles('department')) : ''}
      ${hasKind('independent') ? card('독립기관 (외청)', agencyTiles('independent')) : ''}
      ${collapsibleCard('cfr', '연방관보 분류 · CFR Title', cfrTiles(), (DATA?.cfr_titles || []).length)}
    `);
  }

  // Level 3 -- one agency: its leadership slot and its orders, the box the
  // wireframe draws with 재무부 over EO1/EO2.
  function viewAgency(agencyId) {
    const agency = DATA?.executive_overview?.agencies?.find((a) => a.agency_id === agencyId);
    if (!agency) return shell(empty('기관을 찾을 수 없습니다'));

    const orders = ordersOf(agencyId);
    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card(agency.name, `
            ${agency.short_name ? `<p class="policy-prose">${esc(agency.short_name)}</p>` : ''}
            <div class="policy-leaders">
              <div class="policy-leader">
                <span class="policy-leader-label">장관</span>
                <span class="policy-leader-value is-placeholder">${esc(agency.secretary_placeholder || uiState('empty_agency_secretary', '장관 정보 준비 중'))}</span>
              </div>
            </div>
          `)}
        </div>
        <div class="policy-col">
          ${card('행정명령', orders.length
            ? `<div class="policy-eo-list">${orders.map(eoRibbon).join('')}</div>`
            : empty('등록된 행정명령 없음'))}
        </div>
      </div>`);
  }

  function viewEO(eoNumber) {
    const detail = DATA?.executive_order_detail;
    const listed = DATA?.executive_overview?.executive_orders?.find((o) => String(o.eo_number) === String(eoNumber));
    const hasDetail = detail && String(detail.eo_number) === String(eoNumber);
    const eo = hasDetail ? detail : listed;
    if (!eo) return shell(empty('행정명령을 찾을 수 없습니다'));

    // An EO cites statutes, not bill numbers. Only link inward when the
    // citation actually resolves to a bill the dashboard can open;
    // otherwise fall back to the official external source.
    // TODO(real-api): bill_id becomes a live citation↔bill relationship.
    const authorities = (eo.legal_authorities || []).length
      ? `<ul class="policy-authority-list">${eo.legal_authorities.map((a) => {
          const linked = a.bill_id && resolveBill(a.bill_id);
          const badge = a.verification_status ? `<span class="policy-tag">${esc(a.verification_status)}</span>` : '';
          return linked
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
    const links = eo.official_links || (eo.federal_register_url ? { federal_register_url: eo.federal_register_url } : {});

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
            ${eo.summary ? `<p class="policy-prose">${esc(eo.summary)}</p>` : `<p class="policy-empty">${esc(uiState('empty_eo_detail', '상세 정보 준비 중'))}</p>`}
            <div class="policy-link-row">
              ${links.federal_register_url ? `<a class="policy-external" href="${esc(links.federal_register_url)}" target="_blank" rel="noopener noreferrer">Federal Register</a>` : ''}
              ${links.executive_order_url ? `<a class="policy-external" href="${esc(links.executive_order_url)}" target="_blank" rel="noopener noreferrer">White House</a>` : ''}
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

  const VIEWS = {
    congress: viewCongress,
    executive: viewExecutive,
    committee: (id) => viewCommittee(id),
    agency: (id) => viewAgency(id),
    area: (id) => viewPolicyArea(id),
    cfr: (id) => viewCfrTitle(id),
    bill: (id) => viewBill(id),
    eo: (id) => viewEO(id),
  };

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

  function labelFor(view, id) {
    switch (view) {
      case 'congress': return '의회';
      case 'executive': return '행정부';
      case 'committee':
        return DATA?.congress_overview?.committees?.find((c) => c.committee_id === id)?.name
          || (DATA?.committee_detail?.committee?.committee_id === id ? DATA.committee_detail.committee.name : null)
          || '상임위';
      case 'agency':
        return DATA?.executive_overview?.agencies?.find((a) => a.agency_id === id)?.name || '기관';
      case 'area':
        return (DATA?.policy_areas || []).find((a) => a.policy_area_id === id)?.name || '정책분야';
      case 'cfr': {
        const t = (DATA?.cfr_titles || []).find((x) => String(x.title_number) === String(id));
        return t ? `Title ${t.title_number} · ${t.name}` : `Title ${id}`;
      }
      case 'bill':
        return (resolveBill(id) || findBillSummary(id))?.title || '법률';
      case 'eo':
        return `EO ${id}`;
      default: return view;
    }
  }

  let host = null;

  function paint() {
    if (!host) return;
    const { view, id } = current();
    host.innerHTML = (VIEWS[view] || viewCongress)(id);
    host.scrollTop = 0;
  }

  // Build the ancestor chain for a destination, keeping whatever the current
  // trail already holds for those levels (so a bill opened from a committee
  // keeps that committee, not just a bare 의회).
  function trailTo(view, id) {
    const chain = [];
    for (let v = view; v; v = parentOf(v)) chain.unshift(v);
    return chain.map((v) => {
      if (v === view) return { view: v, id, label: labelFor(v, id) };
      const existing = state.trail.find((t) => t.view === v);
      return existing || { view: v, id: undefined, label: labelFor(v) };
    });
  }

  function go(view, id) {
    // The stage filter belongs to the list that set it, so it resets on every
    // move rather than silently carrying into the next screen.
    state.trail = trailTo(view, id);
    state.stage = '';
    paint();
  }

  function onClick(event) {
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
      paint();
      return;
    }
    const up = event.target.closest('.policy-crumb-link');
    if (up && host.contains(up)) {
      state.trail = state.trail.slice(0, Number(up.dataset.depth) + 1);
      state.stage = '';
      paint();
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
    host.classList.add('policy-surface');
    host.dataset.policyTarget = target;
    host.innerHTML = `<div class="policy-loading">${esc(uiState('loading', '정책 데이터를 불러오는 중'))}</div>`;

    await loadData();
    if (host.dataset.policyTarget !== target) return;  // a later view won the race

    if (!DATA) {
      host.innerHTML = `<div class="policy-surface-inner">${empty('정책 데이터를 불러오지 못했습니다')}</div>`;
      return;
    }

    // Entering from the top menu starts a fresh trail at that level.
    state.trail = [];
    go(TARGET_VIEWS[target] || 'congress');

    host.removeEventListener('click', onClick);
    host.addEventListener('click', onClick);
  }

  function unmount(surface) {
    if (!surface) return;
    surface.removeEventListener('click', onClick);
    surface.classList.remove('policy-surface');
    delete surface.dataset.policyTarget;
    surface.innerHTML = '';
    host = null;
  }

  // app.js routes the 미국 정책 nav targets through `window.USPolicy`; a bare
  // `const` in a classic script never reaches window on its own.
  window.USPolicy = { render, unmount, loadData };
})();
