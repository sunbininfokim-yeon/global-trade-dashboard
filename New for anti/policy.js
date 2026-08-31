// US Policy Dashboard Logic with Mock Data Integration
// Loads UI mock data from docs/ui-policy-mock-data.json

let POLICY_MOCK_DATA = null;

const USPolicy = {
  state: {
    currentView: null,
    selectedCommittee: null,
    selectedPolicyArea: null,
    selectedBill: null,
    selectedChamber: 'senate',
    selectedExecutiveType: 'eo',
    selectedEO: null,
  },

  // Panel references
  hubPanel: document.getElementById('us-policy-hub-panel'),
  congressPanel: document.getElementById('us-congress-overview-panel'),
  executivePanel: document.getElementById('us-executive-panel'),
  committeeDetailPanel: document.getElementById('us-committee-detail-panel'),
  crsPanel: document.getElementById('us-crs-policy-area-panel'),
  billDetailPanel: document.getElementById('us-bill-detail-panel'),
  eoDetailPanel: document.getElementById('us-eo-detail-panel'),

  /**
   * Initialize: load mock data and setup
   */
  async init() {
    try {
      const res = await fetch('/public/data/ui-policy-mock-data.json').catch(() =>
        fetch('/docs/ui-policy-mock-data.json')
      );
      if (res?.ok) {
        POLICY_MOCK_DATA = await res.json();
      }
    } catch (err) {
      console.error('Failed to load policy mock data:', err);
    }
    
    this.setupEventListeners();
    console.log('USPolicy initialized', { hasMockData: !!POLICY_MOCK_DATA });
  },

  /**
   * Setup event listeners for tabs and interactions
   */
  setupEventListeners() {
    // Congress chamber tabs
    document.querySelectorAll('#congress-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.state.selectedChamber = e.target.dataset.chamber;
        this.updateTabState('#congress-tabs', e.target);
        this.loadCommittees(e.target.dataset.chamber);
      });
    });

    // Executive tabs
    document.querySelectorAll('#executive-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.state.selectedExecutiveType = e.target.dataset.type;
        this.updateTabState('#executive-tabs', e.target);
        this.loadExecutiveContent(e.target.dataset.type);
      });
    });

    // Committee bill stage tabs
    document.querySelectorAll('#committee-bill-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.updateTabState('#committee-bill-tabs', e.target);
        const stage = e.target.dataset.stage;
        this.loadBillsByCommittee(this.state.selectedCommittee, stage);
      });
    });

    // CRS bill stage tabs
    document.querySelectorAll('#crs-bill-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.updateTabState('#crs-bill-tabs', e.target);
        const stage = e.target.dataset.stage;
        this.loadBillsByPolicyArea(this.state.selectedPolicyArea, stage);
      });
    });
  },

  updateTabState(tabContainer, activeBtn) {
    document.querySelectorAll(`${tabContainer} .tab-btn`).forEach(btn => {
      btn.classList.remove('active');
    });
    activeBtn.classList.add('active');
  },

  /**
   * Show policy hub (top 10 bills from mock data)
   */
  async showHub() {
    this.state.currentView = 'hub';
    this.hideAllPanels();
    this.panelShow(this.hubPanel);
    this.loadPolicySummary();
  },

  /**
   * Show Congress overview (committees by chamber)
   */
  async showCongressOverview() {
    this.state.currentView = 'congress-overview';
    this.hideAllPanels();
    this.panelShow(this.congressPanel);
    this.loadCommittees('senate');  // Default to Senate
  },

  /**
   * Show Executive orders and regulations
   */
  async showExecutive() {
    this.state.currentView = 'executive';
    this.hideAllPanels();
    this.panelShow(this.executivePanel);
    this.loadExecutiveContent('eo');  // Default to EOs
  },

  /**
   * Load policy hub summary cards
   */
  loadPolicySummary() {
    const container = document.getElementById('policy-summary-cards');
    if (!POLICY_MOCK_DATA?.policy_hub?.summary_cards) {
      container.innerHTML = this.renderEmpty('데이터를 불러올 수 없습니다');
      return;
    }

    const bills = POLICY_MOCK_DATA.policy_hub.summary_cards;
    if (!bills.length) {
      container.innerHTML = this.renderEmpty('표시할 법안이 없습니다');
      return;
    }

    container.innerHTML = bills.map(bill => `
      <div class="policy-card" data-bill-id="${bill.bill_id}">
        <div class="policy-card-title">${bill.title}</div>
        <div class="policy-card-meta">
          <span class="policy-stage-badge">${this.stageLabel(bill.current_stage)}</span>
          <span>${bill.latest_action_date}</span>
        </div>
        <div class="policy-card-summary">${bill.summary || '요약 없음'}</div>
      </div>
    `).join('');

    container.querySelectorAll('.policy-card').forEach(card => {
      card.addEventListener('click', () => {
        this.loadBillDetail(card.dataset.billId);
      });
    });
  },

  /**
   * Load committees by chamber
   */
  loadCommittees(chamber) {
    const container = document.getElementById('congress-committees-list');
    if (!POLICY_MOCK_DATA?.congress_overview?.committees) {
      container.innerHTML = this.renderEmpty('위원회 데이터를 불러올 수 없습니다');
      return;
    }

    const committees = POLICY_MOCK_DATA.congress_overview.committees.filter(c => c.chamber === chamber);
    if (!committees.length) {
      container.innerHTML = this.renderEmpty('위원회가 없습니다');
      return;
    }

    container.innerHTML = committees.map(comm => `
      <div class="committee-item" data-committee-id="${comm.committee_id}">
        <div class="committee-name">${comm.name}</div>
        <div class="committee-meta">${comm.jurisdiction_summary}</div>
        ${comm.agencies?.length ? `<div class="committee-meta" style="margin-top:4px; font-size:9px; color:#64748b;">관할: ${comm.agencies.join(', ')}</div>` : ''}
      </div>
    `).join('');

    container.querySelectorAll('.committee-item').forEach(item => {
      item.addEventListener('click', () => {
        this.state.selectedCommittee = item.dataset.committeeId;
        this.showCommitteeDetail(item.dataset.committeeId);
      });
    });
  },

  /**
   * Show committee detail view
   */
  showCommitteeDetail(committeeId) {
    this.hideAllPanels();
    this.panelShow(this.committeeDetailPanel);
    
    const comm = POLICY_MOCK_DATA?.congress_overview?.committees?.find(c => c.committee_id === committeeId);
    if (!comm) return;

    document.getElementById('committee-name-title').textContent = comm.name;
    document.getElementById('committee-jurisdiction').textContent = `관할: ${comm.jurisdiction_summary}`;

    this.renderCommitteeLeadership(committeeId);
    this.renderSubcommittees(committeeId);

    // Reset the stage tabs to "전체 보기" so a previously selected stage does
    // not silently filter a newly opened committee.
    const tabs = document.querySelectorAll('#committee-bill-tabs .tab-btn');
    if (tabs.length) this.updateTabState('#committee-bill-tabs', tabs[0]);

    // Load default all-bills view
    this.loadBillsByCommittee(committeeId, '');
  },

  /**
   * Render Chair + Ranking Member rows for the committee detail header.
   * Both are placeholder-only until member data lands.
   * TODO(real-api): replace the placeholder strings with the Supabase-backed
   * committee membership rows (chair / ranking member) once available.
   */
  renderCommitteeLeadership(committeeId) {
    const container = document.getElementById('committee-leadership');
    if (!container) return;

    const detail = POLICY_MOCK_DATA?.committee_detail?.committee;
    const states = POLICY_MOCK_DATA?.ui_states || {};

    const chairText = detail?.chair?.name
      || detail?.chair_placeholder
      || states.empty_chair?.title
      || '위원장 정보 준비 중';
    const rankingText = detail?.ranking_member?.name
      || detail?.ranking_member_placeholder
      || states.empty_ranking_member?.title
      || '간사 정보 준비 중';

    const row = (label, value, isPlaceholder) => `
      <div class="committee-leader-row">
        <span class="committee-leader-label">${this.esc(label)}</span>
        <span class="committee-leader-value${isPlaceholder ? ' is-placeholder' : ''}">${this.esc(value)}</span>
      </div>
    `;

    container.innerHTML =
      row('위원장', chairText, !detail?.chair) +
      row('간사', rankingText, !detail?.ranking_member);
  },

  /**
   * Render the subcommittee list (name + meeting-schedule placeholder).
   * TODO(real-api): meeting schedules come from a live committee-meetings feed
   * later; until then every row shows meetings_placeholder.
   */
  renderSubcommittees(committeeId) {
    const container = document.getElementById('committee-subcommittees');
    if (!container) return;

    const subs = POLICY_MOCK_DATA?.committee_detail?.committee?.subcommittees;
    if (!subs || !subs.length) {
      container.innerHTML = '';
      return;
    }

    const fallback = POLICY_MOCK_DATA?.ui_states?.empty_subcommittee_meetings?.title || '회의 일정 준비 중';

    container.innerHTML = `
      <div class="committee-subcommittee-title">소위원회</div>
      ${subs.map(sub => `
        <div class="committee-subcommittee-item" data-subcommittee-id="${this.esc(sub.subcommittee_id)}">
          <div class="committee-subcommittee-name">${this.esc(sub.name)}</div>
          <div class="committee-subcommittee-meta is-placeholder">${this.esc(sub.meetings_placeholder || fallback)}</div>
        </div>
      `).join('')}
    `;
  },

  /**
   * Filter a bill list by a stage tab value.
   * The tab's data-stage is either empty/null (= all stages) or a
   * comma-separated OR list, e.g. "vetoed,failed".
   */
  filterByStage(bills, stage) {
    if (!bills) return [];
    if (!stage) return bills;
    const wanted = String(stage).split(',').map(s => s.trim()).filter(Boolean);
    if (!wanted.length) return bills;
    return bills.filter(b => wanted.includes(b.current_stage));
  },

  /**
   * Load bills by committee and stage
   */
  loadBillsByCommittee(committeeId, stage) {
    const container = document.getElementById('committee-bills-list');
    if (!POLICY_MOCK_DATA?.committee_detail?.items) {
      container.innerHTML = this.renderEmpty('법안을 불러올 수 없습니다');
      return;
    }

    const bills = this.filterByStage(POLICY_MOCK_DATA.committee_detail.items, stage);
    this.renderBillsList(bills, container);
  },

  /**
   * Load bills by policy area and stage
   */
  loadBillsByPolicyArea(policyAreaId, stage) {
    const container = document.getElementById('crs-bills-list');
    if (!POLICY_MOCK_DATA?.policy_area_detail?.items) {
      container.innerHTML = this.renderEmpty('법안을 불러올 수 없습니다');
      return;
    }

    // In mock data, policy_area_detail.items are bill_ids, need to look up actual bills
    const bills = POLICY_MOCK_DATA.policy_hub.summary_cards.filter(b =>
      POLICY_MOCK_DATA.policy_area_detail.items.includes(b.bill_id)
    );
    this.renderBillsList(this.filterByStage(bills, stage), container);
  },

  /**
   * Render bill list
   */
  renderBillsList(bills, container) {
    if (!bills || !bills.length) {
      container.innerHTML = this.renderEmpty('표시할 법안이 없습니다');
      return;
    }

    container.innerHTML = bills.map(bill => `
      <div class="bill-item" data-bill-id="${bill.bill_id}">
        <div class="bill-number">${bill.bill_id}</div>
        <div class="bill-title">${bill.title}</div>
        <div class="bill-meta">
          <span class="policy-stage-badge">${this.stageLabel(bill.current_stage)}</span>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.bill-item').forEach(item => {
      item.addEventListener('click', () => {
        this.loadBillDetail(item.dataset.billId);
      });
    });
  },

  /**
   * Load and display bill detail
   */
  loadBillDetail(billId) {
    this.state.selectedBill = billId;
    this.hideAllPanels();
    this.panelShow(this.billDetailPanel);

    const bill = POLICY_MOCK_DATA?.bill_detail;
    if (!bill) {
      document.getElementById('bill-detail-content').innerHTML = this.renderEmpty('법안 정보를 불러올 수 없습니다');
      return;
    }

    document.getElementById('bill-number-title').textContent = bill.bill_id;
    document.getElementById('bill-title-subtitle').textContent = bill.title;

    const sections = [];

    // Sponsor
    sections.push({
      title: '발의자',
      content: `<div class="bill-sponsor">${bill.sponsor}</div>`,
    });

    // Summary
    sections.push({
      title: '요약',
      content: `<div class="bill-detail-section-content">${bill.summary}</div>`,
    });

    // Committees
    sections.push({
      title: '회부 위원회',
      content: bill.committees?.length ? bill.committees.map(c =>
        `<div class="bill-sponsor">${c.name}</div>`
      ).join('') : this.renderEmpty('정보 없음'),
    });

    // Votes
    if (bill.votes?.length) {
      const vote = bill.votes[0];
      sections.push({
        title: '표결',
        content: `
          <div class="bill-detail-section-content">
            <div style="font-size:10px; line-height:1.5;">
              <strong>${vote.result}</strong> (${vote.vote_date})<br>
              찬성: ${vote.yea_count} | 반대: ${vote.nay_count} | 기권: ${vote.present_count}
            </div>
          </div>
        `,
      });
    } else {
      sections.push({
        title: '표결',
        content: this.renderEmpty(POLICY_MOCK_DATA.ui_states?.empty_vote?.title || '기록 표결 없음'),
      });
    }

    // Related bills
    if (bill.official_related_bills?.length || bill.similar_bills?.length) {
      const relatedHtml = (bill.official_related_bills || []).map(rb =>
        `<div class="bill-related-item">
          <strong>${rb.bill_id}</strong>: ${rb.title}
          <div style="font-size:9px; color:#64748b;">공식 관계</div>
        </div>`
      ).join('');

      const similarHtml = (bill.similar_bills || []).map(sb =>
        `<div class="bill-related-item">
          <strong>${sb.bill_id}</strong>: ${sb.title}
          <div style="font-size:9px; color:#f59e0b;">AI 유사도: ${(sb.similarity_score * 100).toFixed(0)}%</div>
        </div>`
      ).join('');

      sections.push({
        title: '관련 법안',
        content: `<div class="bill-related-list">${relatedHtml}${similarHtml}</div>`,
      });
    }

    document.getElementById('bill-detail-content').innerHTML = sections.map(sec => `
      <div class="bill-detail-section">
        <div class="bill-detail-section-title">${sec.title}</div>
        <div class="bill-detail-section-content">${sec.content}</div>
      </div>
    `).join('');
  },

  /**
   * Load executive content (EO or regulations)
   */
  loadExecutiveContent(type) {
    const container = document.getElementById('executive-content');
    
    if (type === 'eo') {
      const eos = POLICY_MOCK_DATA?.executive_overview?.executive_orders;
      if (!eos || !eos.length) {
        container.innerHTML = this.renderEmpty('행정명령이 없습니다');
        return;
      }

      container.innerHTML = eos.map(eo => `
        <div class="eo-item" data-eo-number="${eo.eo_number}">
          <div class="eo-number">EO ${eo.eo_number}</div>
          <div class="eo-title">${eo.title}</div>
          <div class="bill-meta">${eo.signed_date}</div>
        </div>
      `).join('');

      container.querySelectorAll('.eo-item').forEach(item => {
        item.addEventListener('click', () => {
          this.showEODetail(item.dataset.eoNumber);
        });
      });
    } else if (type === 'agency') {
      this.renderExecutiveHubByAgency(container);
    } else {
      // CFR Titles
      const titles = POLICY_MOCK_DATA?.cfr_titles;
      if (!titles || !titles.length) {
        container.innerHTML = this.renderEmpty('규제 제목이 없습니다');
        return;
      }

      container.innerHTML = titles.map(title => `
        <div class="regulation-item" data-title="${title.title_number}">
          <div class="regulation-title">CFR Title ${title.title_number}</div>
          <div class="regulation-desc">${title.name}</div>
          ${title.reserved ? `<div class="bill-meta" style="color:#f59e0b;">예약됨</div>` : `<div class="bill-meta">${title.regulation_count} 규제</div>`}
        </div>
      `).join('');
    }
  },

  /**
   * Executive hub grouped by issuing agency.
   * Each agency box = agency name + a Secretary/Deputy placeholder + the
   * titles of the EOs it issued, as clickable ribbons into the EO detail.
   * Grouping is driven purely by data: an EO's own `agency_id`, falling back
   * to the agency's `eo_ids` list. No agency name is hardcoded here.
   * TODO(real-api): agency leadership (장관/차관) and the agency↔EO join come
   * from Supabase later; the placeholder row stands in until then.
   */
  renderExecutiveHubByAgency(container) {
    const agencies = POLICY_MOCK_DATA?.executive_overview?.agencies;
    const eos = POLICY_MOCK_DATA?.executive_overview?.executive_orders || [];

    if (!agencies || !agencies.length) {
      container.innerHTML = this.renderEmpty('기관 데이터를 불러올 수 없습니다');
      return;
    }

    const secretaryFallback = POLICY_MOCK_DATA?.ui_states?.empty_agency_secretary?.title || '장관 정보 준비 중';

    const groups = agencies.map(agency => {
      const byAgencyId = eos.filter(eo => eo.agency_id === agency.agency_id);
      const byEoIds = (agency.eo_ids || [])
        .map(id => eos.find(eo => String(eo.eo_number) === String(id)))
        .filter(Boolean);
      // Union of both links, de-duplicated by eo_number.
      const seen = new Set();
      const items = [...byAgencyId, ...byEoIds].filter(eo => {
        const key = String(eo.eo_number);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      return { agency, items };
    });

    container.innerHTML = groups.map(({ agency, items }) => `
      <div class="policy-agency-group" data-agency-id="${this.esc(agency.agency_id)}">
        <div class="policy-agency-header">
          <div class="policy-agency-name">${this.esc(agency.name)}</div>
          ${agency.short_name ? `<span class="policy-agency-short">${this.esc(agency.short_name)}</span>` : ''}
        </div>
        <div class="policy-agency-placeholder is-placeholder">${this.esc(agency.secretary_placeholder || secretaryFallback)}</div>
        ${items.length ? items.map(eo => `
          <div class="policy-eo-ribbon" data-eo-number="${this.esc(eo.eo_number)}">
            <span class="policy-eo-ribbon-number">EO ${this.esc(eo.eo_number)}</span>
            <span class="policy-eo-ribbon-title">${this.esc(eo.title)}</span>
          </div>
        `).join('') : this.renderEmpty('해당 기관의 행정명령이 없습니다')}
      </div>
    `).join('');

    container.querySelectorAll('.policy-eo-ribbon').forEach(row => {
      row.addEventListener('click', () => {
        this.showEODetail(row.dataset.eoNumber);
      });
    });
  },

  /**
   * Show EO detail: summary, official links, cited legal authorities and the
   * related-regulation list.
   */
  showEODetail(eoNumber) {
    this.state.selectedEO = eoNumber;
    this.hideAllPanels();
    this.panelShow(this.eoDetailPanel);

    const content = document.getElementById('eo-detail-content');
    if (!content) return;

    const listed = (POLICY_MOCK_DATA?.executive_overview?.executive_orders || [])
      .find(eo => String(eo.eo_number) === String(eoNumber));
    const detail = POLICY_MOCK_DATA?.executive_order_detail;
    // The mock fixture carries a single fully detailed EO; other list rows fall
    // back to their overview record plus a "detail pending" placeholder.
    const hasDetail = !!detail && String(detail.eo_number) === String(eoNumber);
    const eo = hasDetail ? detail : listed;

    const numberTitle = document.getElementById('eo-number-title');
    const subtitle = document.getElementById('eo-title-subtitle');
    if (numberTitle) numberTitle.textContent = eo ? `EO ${eo.eo_number}` : '행정명령 상세';
    if (subtitle) subtitle.textContent = eo?.title || '';

    if (!eo) {
      content.innerHTML = this.renderEmpty('행정명령 정보를 불러올 수 없습니다');
      return;
    }

    const sections = [];

    sections.push({
      title: '요약',
      content: `<div class="bill-detail-section-content">${this.esc(eo.summary || '요약 없음')}</div>`,
    });

    sections.push({
      title: '서명·공포일',
      content: `<div class="bill-detail-section-content">서명: ${this.esc(eo.signed_date || '-')} · 공포: ${this.esc(eo.publication_date || '-')}</div>`,
    });

    if (!hasDetail) {
      const pending = POLICY_MOCK_DATA?.ui_states?.empty_eo_detail?.title || '행정명령 상세 정보 준비 중';
      sections.push({ title: '상세', content: this.renderEmpty(pending) });
    }

    // Official links (always external)
    const links = hasDetail
      ? Object.values(detail.official_links || {})
      : [eo.federal_register_url].filter(Boolean);
    if (links.length) {
      sections.push({
        title: '공식 링크',
        content: links.map(url =>
          `<a class="policy-external-link" href="${this.esc(url)}" target="_blank" rel="noopener noreferrer">${this.esc(url)}</a>`
        ).join(''),
      });
    }

    if (hasDetail) {
      sections.push({ title: '근거 법령', content: this.renderLegalAuthorities(detail.legal_authorities) });
      sections.push({ title: '관련 규제', content: this.renderRelatedRegulations(detail.related_regulations) });
    }

    content.innerHTML = sections.map(sec => `
      <div class="bill-detail-section">
        <div class="bill-detail-section-title">${this.esc(sec.title)}</div>
        <div class="bill-detail-section-content">${sec.content}</div>
      </div>
    `).join('');

    // Citations resolved to an internal bill open the bill detail view.
    content.querySelectorAll('.policy-legal-authority[data-bill-id]').forEach(item => {
      item.addEventListener('click', () => {
        this.loadBillDetail(item.dataset.billId);
      });
    });
  },

  /**
   * Cited legal authorities on an EO.
   * A citation carrying a `bill_id` that resolves to a bill we track renders as
   * an internal link into that bill's detail view; everything else keeps the
   * external official_url + verification badge it has today.
   * TODO(real-api): `bill_id` is a mock stand-in for a live Supabase-backed
   * citation↔bill relationship — resolve it server-side once that table exists.
   */
  renderLegalAuthorities(authorities) {
    if (!authorities || !authorities.length) return this.renderEmpty('근거 법령 정보 없음');

    return `<div class="policy-legal-list">${authorities.map(auth => {
      const badge = auth.verification_status
        ? `<span class="policy-verify-badge">${this.esc(auth.verification_status)}</span>`
        : '';

      if (auth.bill_id && this.resolveBillId(auth.bill_id)) {
        return `
          <div class="policy-legal-authority is-internal" data-bill-id="${this.esc(auth.bill_id)}">
            <span class="policy-legal-citation">${this.esc(auth.citation)}</span>
            <span class="policy-legal-hint">연계 법안: ${this.esc(auth.bill_id)}</span>
            ${badge}
          </div>
        `;
      }

      return `
        <div class="policy-legal-authority">
          <a class="policy-external-link" href="${this.esc(auth.official_url)}" target="_blank" rel="noopener noreferrer">${this.esc(auth.citation)}</a>
          ${badge}
        </div>
      `;
    }).join('')}</div>`;
  },

  /**
   * Is this bill_id one the dashboard can open a detail view for?
   * The mock fixture only carries one fully detailed bill.
   */
  resolveBillId(billId) {
    if (!billId) return null;
    const detail = POLICY_MOCK_DATA?.bill_detail;
    return detail && String(detail.bill_id) === String(billId) ? detail.bill_id : null;
  },

  /**
   * Regulations under an EO.
   * By design these are external-link-only: a regulation never gets an internal
   * detail page, and no abstract/summary is rendered in this list — the row is
   * title + document type + effective date, opening federal_register_url in a
   * new tab. (`abstract` stays in the data for other consumers.)
   */
  renderRelatedRegulations(regulations) {
    if (!regulations || !regulations.length) return this.renderEmpty('관련 규제 없음');

    return `<div class="policy-regulation-list">${regulations.map(reg => `
      <a class="policy-regulation-row" href="${this.esc(reg.federal_register_url)}" target="_blank" rel="noopener noreferrer">
        <span class="policy-regulation-row-title">${this.esc(reg.title)}</span>
        <span class="policy-regulation-row-meta">
          <span class="policy-stage-badge">${this.esc(reg.document_type || '규제')}</span>
          <span>시행일: ${this.esc(reg.effective_on || '-')}</span>
        </span>
      </a>
    `).join('')}</div>`;
  },

  /**
   * Map stage code to Korean label
   */
  stageLabel(stage) {
    const stages = {
      'introduced': '발의',
      'referred': '회부',
      'subcommittee': '소위',
      'committee_consideration': '위원회',
      'reported': '상임위 통과',
      'passed_origin_chamber': '본회의 통과',
      'second_chamber': '상대원',
      'resolving_differences': '양원 조정',
      'passed_both_chambers': '양원 통과',
      'presented_to_president': '대통령 송부',
      'enacted': '제정',
      'vetoed': '거부',
      'failed': '부결',
    };
    return stages[stage] || '기타';
  },

  /**
   * Render empty state
   */
  renderEmpty(message) {
    return `<p class="empty-state">${message}</p>`;
  },

  /**
   * Escape a value for interpolation into markup / attributes.
   */
  esc(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  /**
   * Utility: Show panel
   */
  panelShow(el) {
    if (el) el.classList.remove('hidden');
  },

  /**
   * Utility: Hide panel
   */
  panelHide(el) {
    if (el) el.classList.add('hidden');
  },

  /**
   * Hide all policy panels
   */
  hideAllPanels() {
    [this.hubPanel, this.congressPanel, this.executivePanel,
     this.committeeDetailPanel, this.crsPanel, this.billDetailPanel,
     this.eoDetailPanel]
      .forEach(panel => this.panelHide(panel));
  },
};

// app.js routes the 미국 정책 nav targets through `window.USPolicy`; a
// top-level `const` in a classic script does not attach to window on its own.
window.USPolicy = USPolicy;

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => USPolicy.init());
} else {
  USPolicy.init();
}
