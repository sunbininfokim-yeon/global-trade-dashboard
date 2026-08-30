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
  },

  // Panel references
  hubPanel: document.getElementById('us-policy-hub-panel'),
  congressPanel: document.getElementById('us-congress-overview-panel'),
  executivePanel: document.getElementById('us-executive-panel'),
  committeeDetailPanel: document.getElementById('us-committee-detail-panel'),
  crsPanel: document.getElementById('us-crs-policy-area-panel'),
  billDetailPanel: document.getElementById('us-bill-detail-panel'),

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
    
    // Load default all-bills view
    this.loadBillsByCommittee(committeeId, '');
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

    const bills = POLICY_MOCK_DATA.committee_detail.items;
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
    this.renderBillsList(bills, container);
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
   * Show EO detail (placeholder for now)
   */
  showEODetail(eoNumber) {
    this.hideAllPanels();
    // TODO: Add EO detail panel when structure is added to HTML
    const eo = POLICY_MOCK_DATA?.executive_order_detail;
    if (eo) {
      console.log('EO Detail:', eo);
    }
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
     this.committeeDetailPanel, this.crsPanel, this.billDetailPanel]
      .forEach(panel => this.panelHide(panel));
  },
};

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => USPolicy.init());
} else {
  USPolicy.init();
}
