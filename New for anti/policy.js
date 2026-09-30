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
    reported: '상임위 보고',
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

  // Use the same evidence contract as ingestion and the API.
  const TERMINAL_LABELS = { vetoed: '거부권 행사', failed: '부결' };
  function resolveBillStage(bill) {
    const lifecycle = bill.lifecycle || window.PolicyEvidence.buildLifecycle(bill);
    const stageFlow = lifecycle.steps;
    return { lifecycle, stageFlow, currentIndex: stageFlow.findIndex(s => s.id === lifecycle.current.step_id) };
  }

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
    { label: '상임위 보고', stages: ['reported'] },
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
  const searchCache = new Map();     // query -> search response

  const cached = (map, key, load) => {
    if (map.has(key)) return map.get(key);
    const p = load().catch((err) => { map.delete(key); throw err; });
    map.set(key, p);
    return p;
  };

  const loadOverview = () => (overviewPromise ||= api('/overview'));

  // Chair/ranking-member/agency-jurisdiction/official-URL for the USA
  // standing committees don't come from the /congress API at all -- they're
  // pre-joined onto the election board by the election_watch pipeline
  // (Clerk XML + Senate CVC + House Rule X/Senate Rule XXV agency rows,
  // never a client-side guess) and read from there once, the same static
  // fetch js/elections/data/core-service.js already uses for the board.
  // See scripts/election_watch/HANDOFF_CLAUDE_POLICY_USA_COMMITTEES.md.
  let committeeCardsPromise = null;
  const loadCommitteeCards = () => {
    if (!committeeCardsPromise) {
      committeeCardsPromise = fetch('/public/data/elections_board_v1.json', { cache: 'no-store' })
        .then((res) => {
          if (!res.ok) throw new Error(`elections_board_v1.json (${res.status})`);
          return res.json();
        })
        .then((board) => {
          const usa = (board.countries || []).find((c) => c.iso3 === 'USA');
          const cards = usa?.ui_ready?.congress?.standing_committee_cards || null;
          const list = cards?.standing || [...(cards?.house || []), ...(cards?.senate || [])];
          return { urlTemplates: cards?.url_templates || null, byId: new Map(list.map((c) => [c.committee_id, c])) };
        })
        .catch(() => ({ urlTemplates: null, byId: new Map() }));
    }
    return committeeCardsPromise;
  };

  const loadBillList = (params) => cached(
    billListCache, `${params.committee_id || ''}|${params.policy_area_id || ''}|${params.stage || ''}`,
    () => api(`/congress/bills${qs(params)}`),
  );
  const loadBill = (billId) => cached(billCache, billId, () => api(`/congress/bills/${encodeURIComponent(billId)}`));
  const loadCommittee = (id) => cached(committeeCache, id, () => api(`/congress/committees${qs({ committee_id: id })}`));
  const loadEoList = (agencyId) => cached(eoListCache, agencyId || '', () => api(`/executive/orders${qs({ agency_id: agencyId, limit: 100 })}`));
  const loadEo = (eoNumber) => cached(eoCache, String(eoNumber), () => api(`/executive/orders/${eoNumber}`));
  const loadCfrTitle = (n) => cached(cfrCache, String(n), () => api(`/executive/cfr-titles/${n}`));
  const loadSearch = (query) => cached(searchCache, query, () => api(`/search${qs({ q: query })}`));

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
       <span class="policy-search-spinner" data-search-spinner hidden aria-hidden="true"></span>
       <div class="policy-search-results" data-search-results hidden></div>
     </div>`;

  const SEARCH_TYPE_VIEWS = { bill: 'bill', executive_order: 'eo' };

  // search_policy_corpus's source_type ('bill'/'executive_order'/'regulation')
  // doesn't say whether a bill is already law -- that split is invisible in
  // the raw type, so a mixed result list used to read as one undifferentiated
  // pile: no way to tell an enacted law from a bill still in committee from
  // an EO at a glance. usSearch (_worker.js) enriches bill hits with
  // law_number/current_stage; searchGroupKey turns that into the four
  // buckets a reader actually asks about.
  const SEARCH_GROUPS = [
    { key: 'enacted', cls: 'is-enacted', label: '제정법안', badgeLabel: '법률' },
    { key: 'pending', cls: 'is-pending', label: '발의법안', badgeLabel: '법안' },
    { key: 'executive_order', cls: 'is-eo', label: '행정명령', badgeLabel: 'EO' },
    { key: 'regulation', cls: 'is-regulation', label: '규정', badgeLabel: '규정' },
  ];
  const SEARCH_GROUP_BY_KEY = new Map(SEARCH_GROUPS.map((g) => [g.key, g]));

  const searchGroupKey = (item) => (item.type === 'bill' ? ((item.law_number || item.current_stage === 'enacted') ? 'enacted' : 'pending') : item.type);

  // Groups in a fixed order, and drops any group with no hits for this query
  // -- three blocks most of the time, a fourth only when a regulation result
  // actually turned up, rather than an empty "규정" column every search.
  function groupSearchItems(items) {
    const buckets = new Map();
    for (const item of items) {
      const key = searchGroupKey(item);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(item);
    }
    return SEARCH_GROUPS
      .map((def) => ({ ...def, items: buckets.get(def.key) || [] }))
      .filter((g) => g.items.length);
  }

  // Only a bill has anything worth a second line here: an enacted one cites
  // its public/private law number, a pending one its own bill number and
  // current stage. EO/regulation rows stay title-only, same as before.
  const searchResultMeta = (item) => {
    if (item.type !== 'bill') return '';
    const cite = billNumberLabel({ ...item, bill_id: item.id });
    if (item.law_number) {
      const lawLabel = `${item.law_type === 'private' ? '사법' : '공법'} ${item.law_number}`;
      return item.latest_action_date ? `${lawLabel} · ${item.latest_action_date}` : lawLabel;
    }
    return `${cite} · ${stageLabel(item.current_stage)}`;
  };

  // opts.compact drops the meta line for the header dropdown, which has no
  // room for it -- the full search page (viewSearch below) keeps it.
  const searchResultRow = (item, opts = {}) => {
    const group = SEARCH_GROUP_BY_KEY.get(searchGroupKey(item));
    const view = SEARCH_TYPE_VIEWS[item.type];
    const meta = !opts.compact ? searchResultMeta(item) : '';
    const body = `<span class="policy-search-result-type${group ? ` ${group.cls}` : ''}">${esc(group?.badgeLabel || item.type)}</span>
        <span class="policy-search-result-body">
          <span class="policy-search-result-title">${esc(item.title || item.id)}${item.match_type === 'exact_bill_number' ? ` · ${esc(item.bill_type.toUpperCase())} ${esc(item.bill_number)} (${esc(item.congress_number)}대)` : ''}</span>
          ${meta ? `<span class="policy-search-result-meta">${esc(meta)}</span>` : ''}
        </span>`;
    // Regulations have no internal drill-down screen of their own -- they
    // only ever appear nested under an EO or a CFR title -- so a search hit
    // links straight to its official Federal Register page instead.
    if (item.type === 'regulation') {
      return item.source_url
        ? `<a class="policy-search-result" href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">${body}</a>`
        : `<div class="policy-search-result is-inert">${body}</div>`;
    }
    const tag = view ? 'button' : 'div';
    const navAttrs = view ? ` type="button" data-view="${esc(view)}" data-id="${esc(item.id)}"` : '';
    return `<${tag} class="policy-search-result${view ? '' : ' is-inert'}"${navAttrs}>${body}</${tag}>`;
  };

  const searchGroupBlock = (group, opts = {}) => `
    <section class="policy-search-group">
      <div class="policy-search-group-head ${group.cls}">
        <span class="policy-search-group-dot ${group.cls}" aria-hidden="true"></span>
        <span class="policy-search-group-label">${esc(group.label)}</span>
        <span class="policy-search-group-count">${group.items.length}건</span>
      </div>
      <div class="policy-search-group-rows">${group.items.map((item) => searchResultRow(item, opts)).join('')}</div>
    </section>`;

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
    box.innerHTML = groupSearchItems(body.items).map((g) => searchGroupBlock(g, { compact: true })).join('');
    box.hidden = false;
  }

  let searchToken = 0;
  let searchTimer = null;

  function setSearchSpinner(visible) {
    const spinner = host?.querySelector('[data-search-spinner]');
    if (spinner) spinner.hidden = !visible;
  }

  async function runSearch(value) {
    const token = ++searchToken;
    setSearchSpinner(true);
    try {
      const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(value)}`);
      const body = await res.json().catch(() => null);
      if (token !== searchToken || !host) return;
      setSearchSpinner(false);
      if (!res.ok || !body) return renderSearchMessage('검색 중 오류가 발생했습니다');
      renderSearchResults(body);
    } catch {
      if (token !== searchToken || !host) return;
      setSearchSpinner(false);
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
      setSearchSpinner(false);
      if (box) box.hidden = true;
      return;
    }
    searchTimer = setTimeout(() => runSearch(input.value.trim()), 300);
  }

  function onSearchKeydown(event) {
    const input = event.target.closest('[data-search-input]');
    if (!input || !host.contains(input)) return;
    if (event.key === 'Enter') {
      const query = input.value.trim();
      if (!query) return;
      clearTimeout(searchTimer);
      searchToken += 1; // drop any in-flight dropdown fetch, the full page is taking over
      setSearchSpinner(false);
      const box = host.querySelector('[data-search-results]');
      if (box) box.hidden = true;
      go('search', query);
      return;
    }
    if (event.key !== 'Escape') return;
    input.value = '';
    state.search.query = '';
    clearTimeout(searchTimer);
    searchToken += 1;
    setSearchSpinner(false);
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

  // "어디까지 갔나"를 한눈에. How far a bill got is not the same question as
  // what stage it is in now -- a vetoed bill's current_stage is off the rail
  // entirely -- so this is driven by resolveBillStage's furthest-reached
  // computation (action history + a chamber's own recorded floor votes),
  // not by current_stage alone.
  const stageRail = (bill) => {
    const { lifecycle, stageFlow, currentIndex } = resolveBillStage(bill);
    const steps = stageFlow.map((step, i) => {
      const observed = step.state === 'observed';
      const evidence = step.evidence.at(-1);
      const title = evidence ? `${step.label} · ${String(evidence.date || '').slice(0, 10)} · ${evidence.text}` : `${step.label}: 근거 미확인`;
      return `<li class="policy-stage-step${i === currentIndex ? ' is-current' : ''}${observed && i !== currentIndex ? ' is-done' : ''}" title="${esc(title)}"><span class="policy-stage-step-dot" aria-hidden="true"></span><span class="policy-stage-step-label">${esc(step.label)}</span><small class="policy-stage-step-date">${observed ? esc(String(evidence.date || '날짜 미확인').slice(0, 10)) : '근거 미확인'}</small></li>`;
    }).join('');
    const alert = lifecycle.procedural_alert;
    return `<ol class="policy-stage-rail" aria-label="입법 단계">${steps}</ol>
      ${alert ? `<p class="policy-notice policy-procedural-alert">${esc(alert.label)} — 법안 통과 여부와 별도입니다.</p>` : ''}
      <p class="policy-notice">${esc(lifecycle.note)}</p>
      ${lifecycle.next ? `<p class="policy-notice">다음 확인 항목: ${esc(lifecycle.next.label)}</p>` : ''}`;
  };

  /* ------------------------------------------------------------ favorites */

  // The star is the one control on these screens that needs an account.
  // Logged out, it opens the signup tab rather than silently failing; logged
  // in, it writes straight through (auth.js owns the Supabase client, so the
  // row still lands under the caller's own auth.uid()).
  const favState = { keys: new Set() };
  const favKey = (kind, id) => `${kind}:${id}`;
  const signedIn = () => !!window.Auth?.currentUser?.();

  async function loadFavorites() {
    if (!signedIn()) {
      favState.keys = new Set();
      return;
    }
    try {
      const rows = await window.Auth.listFavorites();
      favState.keys = new Set(rows.map((r) => favKey(r.item_kind, r.item_id)));
    } catch (err) {
      // A missing table or a rejected policy must not take the screen down --
      // the star just renders unset.
      console.error('Failed to load favorites:', err);
    }
  }

  const favButton = (kind, id, title) => {
    const on = favState.keys.has(favKey(kind, id));
    return `<button type="button" class="policy-fav${on ? ' is-on' : ''}"
              data-fav-kind="${esc(kind)}" data-fav-id="${esc(id)}" data-fav-title="${esc(title || '')}"
              aria-pressed="${on}" title="${esc(on ? '즐겨찾기 해제' : '즐겨찾기')}">
              <span class="policy-fav-icon" aria-hidden="true">${on ? '★' : '☆'}</span>
            </button>`;
  };

  function paintFavButton(button, on) {
    button.classList.toggle('is-on', on);
    button.setAttribute('aria-pressed', String(on));
    button.title = on ? '즐겨찾기 해제' : '즐겨찾기';
    const icon = button.querySelector('.policy-fav-icon');
    if (icon) icon.textContent = on ? '★' : '☆';
  }

  async function toggleFavorite(button) {
    // Not signed in -> straight to 회원가입, and nothing is written.
    if (!signedIn()) {
      window.Auth?.openModal?.('signup');
      return;
    }
    const kind = button.dataset.favKind;
    const id = button.dataset.favId;
    const key = favKey(kind, id);
    const on = favState.keys.has(key);

    button.disabled = true;
    try {
      if (on) {
        await window.Auth.removeFavorite(kind, id);
        favState.keys.delete(key);
      } else {
        await window.Auth.addFavorite(kind, id, button.dataset.favTitle);
        favState.keys.add(key);
      }
      // Repaint this one control rather than the screen: a full paint() would
      // wipe whatever the visitor has typed into the search box.
      paintFavButton(button, !on);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    } finally {
      button.disabled = false;
    }
  }

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

  // usOverview only ever returns top-level bodies (parent_committee_id is
  // null server-side), so committee_type alone says which bucket a row
  // belongs in -- reliable as of the 2026-09-21 committee hierarchy repair
  // (docs/policy-committee-repair-20260921.md, PR #342), which corrected the
  // 53 rows this screen reads and put a DB trigger in front of them so
  // future syncs can't quietly re-break it. An earlier version of this
  // classified by matching committee names against a hand-written regex
  // list; Codex's review of that PR found the regexes didn't match the
  // DB's actual names at all (e.g. "Aging (Special) Committee" never matched
  // /special committee on aging/i), so this uses the type field instead.
  const COMMITTEE_KIND_BY_TYPE = {
    standing: 'standing',
    select: 'select',
    special: 'select',
    joint: 'joint',
    commission_or_caucus: 'other',
    caucus: 'other',
    other: 'other',
  };

  // A type this map doesn't recognize (a new one the repair didn't
  // anticipate, or a row the repair hasn't reached yet) must not silently
  // read as "standing" -- that was the original bug. It gets its own bucket
  // instead, so a real gap stays visible rather than being miscounted.
  const committeeKind = (c) => COMMITTEE_KIND_BY_TYPE[c.committee_type] || 'unknown';

  const committeeTiles = (overview, chamber, kind) => tileGrid(
    (overview?.congress_overview?.committees || [])
      .filter((c) => (chamber == null || c.chamber === chamber) && committeeKind(c) === kind)
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

  // `person` is a standing_committee_cards chair/ranking_member row when
  // present ({ name, member_office_url, ... }) -- linked straight to the
  // Clerk/bioguide URL the pipeline already resolved, never assembled from a
  // lastname guess client-side.
  const leaderRow = (label, person, placeholder) => {
    const url = person?.member_office_url || person?.bioguide_url || null;
    const value = person?.name
      ? (url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(person.name)}</a>` : esc(person.name))
      : esc(placeholder);
    return `
    <div class="policy-leader">
      <span class="policy-leader-label">${esc(label)}</span>
      <span class="policy-leader-value${person?.name ? '' : ' is-placeholder'}">${value}</span>
    </div>`;
  };

  /* ---------------------------------------------------------------- views */

  // Branch level -- the committees and the CRS policy areas, each a way in.
  // House/Senate standing committees get their own cards, separate from
  // each chamber's select/special committees; a card only appears when that
  // bucket actually has something in it, so a chamber with none in the data
  // doesn't show an empty box.
  function viewCongress(_id, overview) {
    const committees = overview?.congress_overview?.committees || [];
    const has = (chamber, kind) => committees.some((c) => (chamber == null || c.chamber === chamber) && committeeKind(c) === kind);
    return shell(`
      ${card(`상임위 (${CHAMBER_LABELS.house})`, committeeTiles(overview, 'house', 'standing'))}
      ${has('house', 'select') ? card(`특별·선정위원회 (${CHAMBER_LABELS.house})`, committeeTiles(overview, 'house', 'select')) : ''}
      ${card(`상임위 (${CHAMBER_LABELS.senate})`, committeeTiles(overview, 'senate', 'standing'))}
      ${has('senate', 'select') ? card(`특별·선정위원회 (${CHAMBER_LABELS.senate})`, committeeTiles(overview, 'senate', 'select')) : ''}
      ${has(null, 'joint') ? card(`합동위원회`, committeeTiles(overview, null, 'joint')) : ''}
      ${has(null, 'other') ? card(`기타 기구`, committeeTiles(overview, null, 'other')) : ''}
      ${has(null, 'unknown') ? card(`미확인 유형`, committeeTiles(overview, null, 'unknown')) : ''}
      ${collapsibleCard('crs', 'CRS 정책분야', policyAreaTiles(overview), (overview?.policy_areas || []).length)}
    `);
  }

  function viewCommittee(committeeId, overview, extra) {
    // extra.detail.committee_id is the canonical id _worker.js resolved
    // committeeId to (identical to committeeId unless committeeId is an old
    // alias, e.g. one of JEC's three source codes) -- the overview list only
    // ever carries the canonical row, so an alias must resolve through this
    // or every old bookmarked/shared committee link "disappears".
    const resolvedId = extra?.detail?.committee_id || committeeId;
    const listed = overview?.congress_overview?.committees?.find((c) => c.committee_id === resolvedId);
    if (!listed) return shell(empty('위원회를 찾을 수 없습니다'));

    const { detail, billPage, card: committeeCard } = extra;

    // committeeCard is the pre-joined standing_committee_cards row (chair/
    // ranking_member/agencies/committee_url straight from Clerk XML + Senate
    // CVC + Rule X/XXV) when this committee is one of the 20 House + 16
    // Senate standing committees it covers. Select/joint committees outside
    // that set have no card -- placeholders stay placeholders rather than
    // guessing, exactly as before this pipeline existed.
    const leadership = committeeCard
      ? `${leaderRow('위원장', committeeCard.chair, '위원장 정보 준비 중')}${leaderRow('간사', committeeCard.ranking_member, '간사 정보 준비 중')}`
      : `${leaderRow('위원장', null, '위원장 정보 준비 중')}${leaderRow('간사', null, '간사 정보 준비 중')}`;

    // agency_id resolves against the same Federal Register agency list the
    // executive-branch tiles already use, so a committee's agency chip
    // reuses that name and its data-view="agency" click-through instead of
    // showing a bare fr-* slug. A card with agencies:[] (jurisdiction
    // researched, no Rule X/XXV row names an agency) stays empty rather than
    // falling back to any guessed mapping -- only a missing card at all
    // falls back to the old listed.agencies.
    const agencyName = (agencyId) => overview?.executive_overview?.agencies
      ?.find((a) => a.agency_id === agencyId);
    const agencyChip = (agencyId) => {
      const found = agencyName(agencyId);
      return found
        ? `<button type="button" class="policy-tag policy-chip is-compact" data-view="agency" data-id="${esc(agencyId)}">${esc(found.short_name || found.name)}</button>`
        : `<span class="policy-tag">${esc(agencyId)}</span>`;
    };
    const agencyList = committeeCard
      ? (committeeCard.agencies?.length
        ? `<div class="policy-tag-row">${committeeCard.agencies.map((a) => agencyChip(a.agency_id)).join('')}</div>`
        : empty('공식 규칙 조항에 부처명을 적은 소관 없음'))
      : ((listed.agencies || []).length
        ? `<div class="policy-tag-row">${listed.agencies.map((a) => `<span class="policy-tag">${esc(a)}</span>`).join('')}</div>`
        : empty('검증된 담당기관 매핑 준비 중'));
    const officialUrl = committeeCard?.committee_url || listed.official_url;

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
            ${officialUrl ? `<a class="policy-external" href="${esc(officialUrl)}" target="_blank" rel="noopener noreferrer">공식 사이트</a>` : ''}
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

  const BILL_TYPE_LABELS = {
    hr: 'H.R.', s: 'S.',
    hres: 'H.Res.', sres: 'S.Res.',
    hjres: 'H.J.Res.', sjres: 'S.J.Res.',
    hconres: 'H.Con.Res.', sconres: 'S.Con.Res.',
  };

  // "119대 · H.R. 3633" -- the citation a reader recognises, rather than the
  // raw bill_id ("119-hr-3633") the API keys on. An unknown type falls back to
  // its own code rather than dropping the number.
  const billNumberLabel = (bill) => {
    const type = BILL_TYPE_LABELS[String(bill.bill_type || '').toLowerCase()]
      || String(bill.bill_type || '').toUpperCase();
    const cite = type && bill.bill_number ? `${type} ${bill.bill_number}` : bill.bill_id;
    return bill.congress_number ? `${bill.congress_number}대 · ${cite}` : cite;
  };

  // Compact card for a favorited bill (My Page favorites/mailing lists),
  // reusing the same stage rail and vote data as the full bill detail panel
  // below so the two views can never disagree about what "next stage" means.
  // There is no curated short/abbreviated title anywhere in the schema --
  // bill.title is the official long title -- so this shows that title as-is
  // rather than fabricate an abbreviation.
  //
  // notifyEnabled reflects user_favorites.notify_enabled for this bill (not
  // part of the `bills` row loadBillById returns), defaulting to true when
  // omitted so a caller that doesn't track it yet still gets a checked box.
  // bill.bill_id doubles as the favorite's item_id -- callers only ever load
  // this card for item_kind 'bill', and loadBillById(item_id) returns the
  // row keyed by that same id.
  function favoriteBillCardHtml(bill, notifyEnabled) {
    const { lifecycle, stageFlow, currentIndex } = resolveBillStage(bill);
    const terminalLabel = TERMINAL_LABELS[bill.current_stage];
    const currentLabel = lifecycle.current.label;
    const nextLabel = !terminalLabel && currentIndex >= 0 && currentIndex < stageFlow.length - 1
      ? stageFlow[currentIndex + 1].label
      : null;

    const votes = (bill.bill_votes || []).map(v => ({ ...v, ...window.PolicyEvidence.voteEvidence(v) }));
    const lastVote = [...votes].sort((a, b) => String(b.vote_date).localeCompare(String(a.vote_date)))[0];
    const voteInfo = lastVote ? window.PolicyEvidence.voteEvidence(lastVote) : null;
    const voteText = voteInfo ? `${voteInfo.kind === 'cloture' ? '토론 종결' : '표결'} 찬 ${esc(voteInfo.yea_count ?? '미확인')} · 반 ${esc(voteInfo.nay_count ?? '미확인')}` : null;
    const itemId = esc(bill.bill_id);

    return `<div class="policy-fav-bill-card">
      <div class="policy-fav-bill-title">${esc(bill.title)}</div>
      <div class="policy-fav-bill-meta">
        <span class="policy-fav-bill-code">${esc(billNumberLabel(bill))}</span>
        <span class="policy-fav-bill-stage">${esc(currentLabel)}${nextLabel ? ` → ${esc(nextLabel)}` : ''}</span>
        ${voteText ? `<span class="policy-fav-bill-votes">${voteText}</span>` : ''}
      </div>
      <div class="policy-fav-bill-actions">
        <label class="policy-fav-bill-notify">
          <input type="checkbox" class="policy-fav-bill-notify-checkbox" data-item-id="${itemId}" ${notifyEnabled === false ? '' : 'checked'}>
          메일 알림
        </label>
        <button type="button" class="policy-fav-star" data-remove-item-id="${itemId}" title="즐겨찾기 해제" aria-label="즐겨찾기 해제">★</button>
      </div>
    </div>`;
  }

  const actionRow = (row) => {
    const evidence = window.PolicyEvidence.classifyAction(row);
    const a = { ...row, chamber: evidence.chamber };
    const label = ({ passage: '본회의 통과', passage_failed: '본회의 통과 표결 부결', procedural_vote: '절차 표결', other: '기타' })[evidence.kind] || stageLabel(evidence.kind);
    return `
    <li class="policy-action">
      <span class="policy-action-date">${esc(a.action_date || '')}</span>
      <span class="policy-action-body">
        ${a.chamber ? `<span class="policy-action-chamber">${esc(CHAMBER_LABELS[a.chamber] || a.chamber)}</span>` : ''}
        <span>${esc(a.action_text || '')}</span>
      </span>
      <span class="policy-tag">${esc(label)}</span>
    </li>`;
  };

  // Version rows link out only. docs/api-spec.md forbids storing or
  // re-serving the document text itself, so the official copy is the copy.
  const textVersionRow = (v) => {
    const links = [
      v.html_url ? `<a class="policy-external" href="${esc(v.html_url)}" target="_blank" rel="noopener noreferrer">HTML</a>` : '',
      v.pdf_url ? `<a class="policy-external" href="${esc(v.pdf_url)}" target="_blank" rel="noopener noreferrer">PDF</a>` : '',
    ].filter(Boolean).join('');
    return `<li class="policy-textver">
        <span class="policy-textver-name">${esc(v.version_name || v.version_code || '원문')}</span>
        <span class="policy-textver-meta">${esc(v.issued_on || '')}${links}</span>
      </li>`;
  };

  function billPanel(bill) {
    const votes = (bill.bill_votes || []).map(v => ({ ...v, ...window.PolicyEvidence.voteEvidence(v) }));
    // Same resolution stageRail uses below, so the badge and the rail's
    // highlighted step can never name two different stages for one bill.
    const { lifecycle: badgeLifecycle, stageFlow: badgeStageFlow, currentIndex: badgeCurrentIndex } = resolveBillStage(bill);
    const currentStageLabel = badgeLifecycle.current.label;

    const voteBody = votes.length
      ? votes.map((v) => `
          <div class="policy-vote">
            <div class="policy-vote-head">
              <span>${esc(CHAMBER_LABELS[v.chamber] || v.chamber)} · ${esc(v.question)}</span>
              <span class="policy-vote-result">${esc(({ passed: '가결', failed: '부결', unknown: '결과 미확인' })[v.result] || v.result)}</span>
            </div>
            <div class="policy-vote-counts">
              <span class="yea">찬성 ${esc(v.yea_count ?? '미확인')}</span>
              <span class="nay">반대 ${esc(v.nay_count ?? '미확인')}</span>
              <span>기권 ${esc(v.present_count ?? '미확인')}</span>
              <span>불참 ${esc(v.not_voting_count ?? '미확인')}</span>
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

    const lawLabel = bill.law_number
      ? `${bill.law_type === 'private' ? '사법' : '공법'} ${esc(bill.law_number)}`
      : '';

    return `<section class="policy-block policy-bill-panel">
      <div class="policy-bill-head">
        <h3 class="policy-block-title">${esc(bill.title)}</h3>
        ${favButton('bill', bill.bill_id, bill.title)}
      </div>
      <div class="policy-bill-meta">
        <span class="policy-stage-badge">${esc(currentStageLabel)}</span>
        <span class="policy-bill-cite">${esc(billNumberLabel(bill))}</span>
        ${bill.sponsor ? `<span>발의자 ${esc(bill.sponsor)}</span>` : ''}
        ${bill.introduced_date ? `<span>발의일 ${esc(bill.introduced_date)}</span>` : ''}
        ${bill.latest_action_date ? `<span>최근 조치 ${esc(bill.latest_action_date)}</span>` : ''}
        ${lawLabel ? `<span class="policy-tag is-law">${lawLabel}</span>` : ''}
      </div>
      ${stageRail(bill)}
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

    // CRS policy area is the one classification with its own screen; the
    // legislative subjects beside it are labels, not destinations.
    const areaChip = bill.policy_areas?.policy_area_id
      ? `<button type="button" class="policy-chip is-compact" data-view="area" data-id="${esc(bill.policy_areas.policy_area_id)}">
           <span class="policy-chip-name">${esc(bill.policy_areas.name)}</span>
         </button>`
      : '';
    const subjects = (bill.bill_subjects || [])
      .map((s) => s.legislative_subjects?.name)
      .filter(Boolean)
      .map((name) => `<span class="policy-tag">${esc(name)}</span>`)
      .join('');
    const classification = areaChip || subjects
      ? `${areaChip ? `<div class="policy-chip-row">${areaChip}</div>` : ''}
         ${subjects ? `<div class="policy-tag-row">${subjects}</div>` : ''}`
      : empty('분류 정보 없음');

    const versions = (bill.bill_text_versions || []).length
      ? `<ul class="policy-textver-list">${bill.bill_text_versions.map(textVersionRow).join('')}</ul>`
      : empty('공개된 법안 원문 없음');

    // The action list is the longest thing on the screen and the least often
    // read, so it stays folded until asked for -- same treatment the long
    // taxonomies get on the directory screens.
    const actions = bill.bill_actions || [];
    const actionsBody = actions.length
      ? `<ul class="policy-action-list">${actions.map(actionRow).join('')}</ul>`
      : empty('기록된 조치 없음');

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${billPanel(bill)}
          ${collapsibleCard('bill-actions', '진행 이력', actionsBody, actions.length)}
        </div>
        <div class="policy-col">
          ${card('회부 위원회', committees ? `<div class="policy-chip-row">${committees}</div>` : empty('위원회 정보 없음'))}
          ${card('분류', classification)}
          ${card('법안 원문', versions)}
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

    const agencyGroups = eoAgencyGroups(eo.agency_relations);

    return shell(`
      <div class="policy-grid-2">
        <div class="policy-col">
          ${card(`EO ${eo.eo_number}`, `
            <div class="policy-bill-head">
              <p class="policy-eo-headline">${esc(eo.title)}</p>
              ${favButton('executive_order', String(eo.eo_number), eo.title)}
            </div>
            <div class="policy-bill-meta">
              <span>서명 ${esc(eo.signed_date || '-')}</span>
              <span>공포 ${esc(eo.publication_date || '-')}</span>
            </div>
            ${agencyGroups.issuing.length ? `<div class="policy-tag-row">${agencyGroups.issuing.map(agencyTag).join('')}</div>` : ''}
            ${eo.summary ? `<p class="policy-prose">${esc(eo.summary)}</p>` : `<p class="policy-empty">${esc('상세 정보 준비 중')}</p>`}
            <div class="policy-link-row">
              ${eo.federal_register_url ? `<a class="policy-external" href="${esc(eo.federal_register_url)}" target="_blank" rel="noopener noreferrer">Federal Register</a>` : ''}
              ${eo.executive_order_url ? `<a class="policy-external" href="${esc(eo.executive_order_url)}" target="_blank" rel="noopener noreferrer">White House</a>` : ''}
            </div>
            ${agencyRelationBlock('지시 대상 기관', agencyGroups.directed)}
            ${agencyRelationBlock('협의 기관', agencyGroups.consulted)}
            ${agencyRelationBlock('협업 기관', agencyGroups.coordinating)}
          `)}
        </div>
        <div class="policy-col">
          ${card('근거 법령', authorities)}
          ${card('하위 규제', regulations)}
        </div>
      </div>`);
  }

  // issuing_document/implementing_regulation come from official document
  // metadata and carry no quotable text -- shown as plain tags, same as
  // before. The three official_text_citation roles (a specific "shall",
  // "in consultation with", "in coordination with" sentence in the EO's own
  // text) are shown with that sentence attached, so the reader sees why the
  // agency is here instead of taking the tag on faith.
  function eoAgencyGroups(relations) {
    const groups = { issuing: [], directed: [], consulted: [], coordinating: [] };
    for (const r of relations || []) {
      if (!r.agency) continue;
      if (r.relationship_type === 'directed_agency') groups.directed.push(r);
      else if (r.relationship_type === 'consulted_agency') groups.consulted.push(r);
      else if (r.relationship_type === 'coordinating_agency') groups.coordinating.push(r);
      else groups.issuing.push(r);
    }
    return groups;
  }

  const agencyTag = (r) => `<span class="policy-tag">${esc(r.agency.name)}</span>`;

  const agencyRelationBlock = (label, relations) => (relations.length
    ? `<div class="policy-subblock"><h4>${esc(label)}</h4>
         <ul class="policy-authority-list">${relations.map((r) => `
           <li>
             <span class="policy-tag">${esc(r.agency.name)}</span>
             ${r.evidence_excerpt ? `<p class="policy-authority-hint">"${esc(r.evidence_excerpt)}"</p>` : ''}
           </li>`).join('')}</ul>
       </div>`
    : '');

  // Reached by pressing Enter in the header search box (onSearchKeydown) --
  // the dropdown is for a quick glance while typing; this is its own screen
  // with its own URL, so a search is shareable and survives a refresh the
  // same way every other drill-down level does.
  function viewSearch(query, overview, extra) {
    const body = extra?.results;
    const heading = `"${query}" 검색`;
    if (!body) return shell(card(heading, empty('검색 결과를 불러오지 못했습니다')));
    if (body.unavailable) return shell(card(heading, empty('검색 기능 준비 중입니다')));
    if (!body.items?.length) return shell(card(heading, empty('검색 결과가 없습니다')));
    const groups = groupSearchItems(body.items);
    return shell(card(`${heading} (${body.items.length}건)`,
      `<div class="policy-search-page-results">${groups.map((g) => searchGroupBlock(g, { compact: false })).join('')}</div>`));
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
    search: null,
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
      case 'committee': {
        // usCommitteeDetail resolves an old alias id (e.g. a bookmarked JEC
        // code) to its canonical committee_id -- the overview list only ever
        // carries the canonical row, so look that up instead of the raw id
        // or an old link falls back to the generic label below.
        const resolvedId = extra?.detail?.committee_id || id;
        return overview?.congress_overview?.committees?.find((c) => c.committee_id === resolvedId)?.name || '상임위';
      }
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
      case 'search':
        return `검색: "${id}"`;
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
        const [detail, billPage, committeeCards] = await Promise.all([
          loadCommittee(id),
          loadBillList({ committee_id: id, stage: state.stage }),
          loadCommitteeCards(),
        ]);
        return { detail, billPage, card: committeeCards.byId.get(id) || null };
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
      case 'search':
        return { results: await loadSearch(id) };
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
    search: viewSearch,
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

  // Committees and agencies get a human-readable slug (from their official
  // name) instead of their opaque id everywhere a URL is built or parsed.
  // Built once per render() from the already-loaded overview -- nothing
  // extra to fetch. Two committees/agencies landing on the same slug (a
  // generic subcommittee name reused across parents, say) get a numeric
  // suffix so neither silently overwrites the other in the lookup.
  let committeeSlugById = new Map();
  let committeeIdBySlug = new Map();
  let agencySlugById = new Map();
  let agencyIdBySlug = new Map();

  function slugify(text) {
    return String(text || '')
      .toLowerCase()
      .normalize('NFKD').replace(new RegExp('[\\u0300-\\u036f]', 'g'), '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function buildSlugMaps(list, idKey, nameOf = (item) => item.name) {
    const slugById = new Map();
    const idBySlug = new Map();
    for (const item of list || []) {
      const id = item?.[idKey];
      if (!id) continue;
      const base = slugify(nameOf(item)) || slugify(id);
      let slugValue = base;
      let n = 2;
      while (idBySlug.has(slugValue)) slugValue = `${base}-${n++}`;
      slugById.set(id, slugValue);
      idBySlug.set(slugValue, id);
    }
    return { slugById, idBySlug };
  }

  // Congress.gov's committee.name carries no chamber ("Committee on
  // Appropriations", "Committee on Armed Services", "Committee on the
  // Budget", "Committee on the Judiciary", "Committee on Veterans' Affairs"
  // are each the literal, identical name in both chambers), so slugifying
  // the bare name alone would hand one chamber's committee an arbitrary
  // "-2" suffix instead of a name that says which chamber it is -- and
  // which one loses the tie isn't guaranteed stable if the API's row order
  // ever shifts. Joint committees keep their bare name: their names already
  // read as "Joint Committee on Taxation" etc., so prefixing would repeat
  // "joint" and they don't collide with the house/senate pattern anyway.
  function committeeSlugName(c) {
    return c.chamber === 'house' || c.chamber === 'senate' ? `${c.chamber} ${c.name}` : c.name;
  }

  // Exposed for the 정치 › 미국 하원/상원 committee chips (usa-legislature.js):
  // that panel's committee list comes from a different pipeline
  // (election_watch's usa_committees.json) whose `code` field uses its own
  // scheme (House: bare "AG00"; Senate already "SS"-prefixed) that does not
  // match Congress.gov's systemCode this module's committee_id is built
  // from -- guessing a translation between the two id schemes risked
  // silently landing on the wrong committee. Building the slug the exact
  // same way from the shared official name instead means it either matches
  // a real committee_id (via committeeIdBySlug in parseLeafFromPath) or
  // visibly fails to, never silently wrong.
  const committeeSlug = (chamber, name) => (name ? slugify(committeeSlugName({ chamber, name })) : undefined);

  const POLICY_BASE_PATH = '/policy/us';

  // Mirrors the current leaf into the URL's path so a bill, EO, committee, or
  // agency is a real link -- reload, share, browser back/forward -- instead
  // of living only in `state.trail`. app.js's top-level router only cares
  // whether the path starts with /policy/us and whether the next segment is
  // "executive"; everything past that is ours to shape.
  function pathForLeaf(view, id) {
    if (view === 'congress') return POLICY_BASE_PATH;
    if (view === 'executive' && id === undefined) return `${POLICY_BASE_PATH}/executive`;
    const segment = view === 'committee' ? (committeeSlugById.get(id) || id)
      : view === 'agency' ? (agencySlugById.get(id) || id)
      : id;
    return `${POLICY_BASE_PATH}/${view}${segment !== undefined && segment !== null ? `/${encodeURIComponent(segment)}` : ''}`;
  }

  function syncUrl(view, id, opts = {}) {
    const url = pathForLeaf(view, id);
    if (url === window.location.pathname) return; // no-op, skip a duplicate history entry
    window.history[opts.replace ? 'replaceState' : 'pushState']({ policyView: view, policyId: id }, '', url);
  }

  // Reverses pathForLeaf(): whatever follows /policy/us in the URL, resolved
  // back to a {view, id} go() can navigate to. A committee/agency segment is
  // tried as a slug first and falls back to treating it as the raw id
  // directly -- a link built before overview loaded, or built by another
  // module (the elections handoff uses the raw committee_id), still resolves.
  function parseLeafFromPath(pathname) {
    const trimmed = pathname.replace(/^\/+|\/+$/g, '');
    if (trimmed !== 'policy/us' && !trimmed.startsWith('policy/us/')) return null;
    const rest = trimmed === 'policy/us' ? '' : trimmed.slice('policy/us/'.length);
    if (!rest || rest === 'congress') return null; // default congress leaf, nothing to restore
    if (rest === 'executive') return { view: 'executive', id: undefined };
    const slashIdx = rest.indexOf('/');
    const view = slashIdx < 0 ? rest : rest.slice(0, slashIdx);
    if (!VIEWS[view]) return null;
    let idRaw = slashIdx < 0 ? '' : rest.slice(slashIdx + 1);
    if (!idRaw) return null;
    try { idRaw = decodeURIComponent(idRaw); } catch { /* keep as-is */ }
    const id = view === 'committee' ? (committeeIdBySlug.get(idRaw) || idRaw)
      : view === 'agency' ? (agencyIdBySlug.get(idRaw) || idRaw)
      : idRaw;
    return { view, id };
  }

  async function go(view, id, opts = {}) {
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
    syncUrl(view, id, opts);
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
      searchToken += 1; // drop any in-flight dropdown fetch now that it's dismissed
      setSearchSpinner(false);
      const box = searchWrap.querySelector('[data-search-results]');
      if (box) box.hidden = true;
    }
    const fav = event.target.closest('.policy-fav');
    if (fav && host.contains(fav)) {
      toggleFavorite(fav);
      return;
    }
    const searchResult = event.target.closest('.policy-search-result');
    if (searchResult && host.contains(searchResult)) {
      searchToken += 1;
      setSearchSpinner(false);
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

  // Auth.onChange has no unsubscribe, so this registers once for the life of
  // the page rather than per render. Signing in or out reloads the set and
  // repaints, so the stars match the account that is actually signed in.
  let authSubscribed = false;

  function subscribeToAuth() {
    if (authSubscribed || !window.Auth?.onChange) return;
    authSubscribed = true;
    window.Auth.onChange(() => {
      loadFavorites().then(() => { if (host) paint(); });
    });
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

    subscribeToAuth();

    try {
      // Favorites ride along rather than gating the screen: signed out it is a
      // no-op, and a failure only leaves the stars unset.
      [overview] = await Promise.all([loadOverview(), loadFavorites()]);
    } catch (err) {
      console.error('Failed to load policy overview:', err);
      if (host.dataset.policyTarget !== target || token !== renderToken) return;
      host.innerHTML = `<div class="policy-surface-inner">${empty('정책 데이터를 불러오지 못했습니다')}</div>`;
      return;
    }
    if (host.dataset.policyTarget !== target || token !== renderToken) return; // a later view won the race

    ({ slugById: committeeSlugById, idBySlug: committeeIdBySlug } =
      buildSlugMaps(overview?.congress_overview?.committees, 'committee_id', committeeSlugName));
    ({ slugById: agencySlugById, idBySlug: agencyIdBySlug } =
      buildSlugMaps(overview?.executive_overview?.agencies, 'agency_id'));

    // Entering from the top menu starts a fresh trail at that level -- unless
    // the URL already names a deeper view (a shared link, a reload, or the
    // browser back/forward button landing back on this same path).
    state.trail = [];
    const leaf = parseLeafFromPath(window.location.pathname);
    const restored = leaf && VIEWS[leaf.view] && (leaf.view === 'executive' ? true : leaf.id);
    await go(restored ? leaf.view : (TARGET_VIEWS[target] || 'congress'), restored ? leaf.id : undefined, { replace: true });

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
  //
  // loadBillById/favoriteBillCardHtml are for My Page's favorites list: a
  // favorited bill's detail lives behind /api/us (bills carry no browser RLS
  // policy -- see supabase/migrations, service_role only), so My Page cannot
  // query Supabase directly for it the way it does for the user_favorites
  // row itself. This reuses the exact same API path and stage/vote
  // formatting as the bill detail panel above instead of a second copy.
  window.USPolicy = {
    render,
    unmount,
    loadBillById: (billId) => api(`/congress/bills/${encodeURIComponent(billId)}`),
    favoriteBillCardHtml,
    committeeSlug,
  };
})();
