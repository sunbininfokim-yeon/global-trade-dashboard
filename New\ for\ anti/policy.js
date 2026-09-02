// US Policy Dashboard Logic
// Handles Congress bills, committees, executive orders, and regulations

const USPolicy = {
  state: {
    currentView: null,  // 'hub', 'congress-overview', 'executive'
    selectedCommittee: null,
    selectedPolicyArea: null,
    selectedBill: null,
  },

  // Panel references
  hubPanel: document.getElementById('us-policy-hub-panel'),
  congressPanel: document.getElementById('us-congress-overview-panel'),
  executivePanel: document.getElementById('us-executive-panel'),
  committeeDetailPanel: document.getElementById('us-committee-detail-panel'),
  crsPanel: document.getElementById('us-crs-policy-area-panel'),
  billDetailPanel: document.getElementById('us-bill-detail-panel'),

  /**
   * Initialize policy dashboard
   */
  init() {
    this.setupEventListeners();
    console.log('USPolicy initialized');
  },

  /**
   * Set up all event listeners
   */
  setupEventListeners() {
    // Congress overview tabs
    const congressTabs = document.querySelectorAll('#congress-tabs .tab-btn');
    congressTabs.forEach(btn => {
      btn.addEventListener('click', (e) => this.loadCommittees(e.target.dataset.chamber));
    });

    // Executive tabs
    const executiveTabs = document.querySelectorAll('#executive-tabs .tab-btn');
    executiveTabs.forEach(btn => {
      btn.addEventListener('click', (e) => this.loadExecutiveContent(e.target.dataset.type));
    });

    // Committee bill stage tabs
    const committeeTabBtns = document.querySelectorAll('#committee-bill-tabs .tab-btn');
    committeeTabBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const stage = e.target.dataset.stage;
        this.loadBillsByCommittee(this.state.selectedCommittee, stage);
      });
    });

    // CRS policy area bill stage tabs
    const crsTabBtns = document.querySelectorAll('#crs-bill-tabs .tab-btn');
    crsTabBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const stage = e.target.dataset.stage;
        this.loadBillsByPolicyArea(this.state.selectedPolicyArea, stage);
      });
    });
  },

  /**
   * Show policy hub (top 10 bills)
   */
  async showHub() {
    this.state.currentView = 'hub';
    this.hideAllPanels();
    this.panelShow(this.hubPanel);
    await this.loadPolicySummary();
  },

  /**
   * Show Congress overview
   */
  async showCongressOverview() {
    this.state.currentView = 'congress-overview';
    this.hideAllPanels();
    this.panelShow(this.congressPanel);
    await this.loadCommittees('senate');
  },

  /**
   * Show Executive orders and regulations
   */
  async showExecutive() {
    this.state.currentView = 'executive';
    this.hideAllPanels();
    this.panelShow(this.executivePanel);
    await this.loadExecutiveContent('eo');
  },

  /**
   * Load top 10 policy summary
   * API: GET /api/us/policy/summary?limit=10
   */
  async loadPolicySummary() {
    const container = document.getElementById('policy-summary-cards');
    try {
      container.innerHTML = '<p class="empty-state">데이터 로딩 중…</p>';

      // TODO: Uncomment when API is ready
      // const response = await fetch('/api/us/policy/summary?limit=10');
      // const bills = await response.json();
      // this.renderPolicySummaryCards(bills);

      // Mock data for UI preview
      this.renderPolicySummaryCards([
        {
          bill_id: 'S.119-001',
          title: 'Build America Act (가칭)',
          current_stage: 'passed_origin_chamber',
          latest_action_date: '2024-08-20',
          summary: 'A comprehensive infrastructure investment bill targeting critical modernization of America\'s infrastructure.',
        },
        {
          bill_id: 'H.R.119-234',
          title: 'Foreign Investment Risk Assessment Act',
          current_stage: 'committee_consideration',
          latest_action_date: '2024-08-18',
          summary: 'Strengthens CFIUS review procedures for sensitive tech sector investments.',
        },
      ]);
    } catch (error) {
      console.error('Error loading policy summary:', error);
      container.innerHTML = '<p class="empty-state">데이터를 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Render policy summary cards
   */
  renderPolicySummaryCards(bills) {
    const container = document.getElementById('policy-summary-cards');
    if (!bills || bills.length === 0) {
      container.innerHTML = '<p class="empty-state">표시할 법안이 없습니다.</p>';
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

    // Add click handlers
    container.querySelectorAll('.policy-card').forEach(card => {
      card.addEventListener('click', () => {
        const billId = card.dataset.billId;
        this.loadBillDetail(billId);
      });
    });
  },

  /**
   * Load committees by chamber
   * API: GET /api/us/congress/committees?chamber={chamber}
   */
  async loadCommittees(chamber) {
    const container = document.getElementById('congress-committees-list');
    try {
      container.innerHTML = '<p class="empty-state">위원회 로딩 중…</p>';

      // TODO: Uncomment when API is ready
      // const response = await fetch(`/api/us/congress/committees?chamber=${chamber}`);
      // const committees = await response.json();
      // this.renderCommittees(committees);

      // Mock data
      const mockCommittees = {
        senate: [
          { committee_id: 'SSFS', name: 'Committee on Finance', jurisdiction_summary: 'Taxation and revenue' },
          { committee_id: 'SSFR', name: 'Committee on Foreign Relations', jurisdiction_summary: 'International relations' },
        ],
        house: [
          { committee_id: 'HSWM', name: 'Committee on Ways and Means', jurisdiction_summary: 'Taxation and trade' },
          { committee_id: 'HSPF', name: 'Committee on Foreign Affairs', jurisdiction_summary: 'International affairs' },
        ],
      };

      this.renderCommittees(mockCommittees[chamber] || []);
    } catch (error) {
      console.error('Error loading committees:', error);
      container.innerHTML = '<p class="empty-state">위원회를 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Render committees list
   */
  renderCommittees(committees) {
    const container = document.getElementById('congress-committees-list');
    if (!committees || committees.length === 0) {
      container.innerHTML = '<p class="empty-state">위원회 정보가 없습니다.</p>';
      return;
    }

    container.innerHTML = committees.map(comm => `
      <div class="committee-item" data-committee-id="${comm.committee_id}">
        <div class="committee-name">${comm.name}</div>
        <div class="committee-meta">${comm.jurisdiction_summary}</div>
      </div>
    `).join('');

    // Add click handlers
    container.querySelectorAll('.committee-item').forEach(item => {
      item.addEventListener('click', () => {
        const committeeId = item.dataset.committeeId;
        this.state.selectedCommittee = committeeId;
        this.showCommitteeDetail(committeeId);
      });
    });
  },

  /**
   * Show committee detail view
   */
  async showCommitteeDetail(committeeId) {
    this.hideAllPanels();
    this.panelShow(this.committeeDetailPanel);
    // Set committee title (mock)
    document.getElementById('committee-name-title').textContent = committeeId + ' 상임위';
    document.getElementById('committee-jurisdiction').textContent = '관할: 로딩 중…';
    await this.loadBillsByCommittee(committeeId, '');
  },

  /**
   * Load bills by committee and stage
   */
  async loadBillsByCommittee(committeeId, stage) {
    const container = document.getElementById('committee-bills-list');
    try {
      container.innerHTML = '<p class="empty-state">법안 로딩 중…</p>';

      // TODO: Uncomment when API is ready
      // const stageParam = stage ? `&stage=${stage}` : '';
      // const response = await fetch(`/api/us/congress/bills?committee_id=${committeeId}${stageParam}`);
      // const bills = await response.json();
      // this.renderBillsList(bills);

      // Mock data
      this.renderBillsList([
        { bill_id: 'S.119-456', title: 'Export Control Reform Act', current_stage: 'reported' },
        { bill_id: 'H.R.119-789', title: 'Foreign Investment Scrutiny Act', current_stage: 'passed_origin_chamber' },
      ]);
    } catch (error) {
      console.error('Error loading bills:', error);
      container.innerHTML = '<p class="empty-state">법안을 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Load bills by policy area and stage
   */
  async loadBillsByPolicyArea(policyAreaId, stage) {
    const container = document.getElementById('crs-bills-list');
    try {
      container.innerHTML = '<p class="empty-state">법안 로딩 중…</p>';

      // TODO: Uncomment when API is ready
      // const stageParam = stage ? `&stage=${stage}` : '';
      // const response = await fetch(`/api/us/congress/bills?policy_area_id=${policyAreaId}${stageParam}`);
      // const bills = await response.json();
      // this.renderBillsList(bills, container);

      this.renderBillsList([
        { bill_id: 'S.119-111', title: 'Trade Policy Reform', current_stage: 'committee_consideration' },
      ], container);
    } catch (error) {
      console.error('Error loading policy area bills:', error);
      container.innerHTML = '<p class="empty-state">법안을 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Render bills list
   */
  renderBillsList(bills, container = null) {
    const target = container || document.getElementById('committee-bills-list');
    if (!bills || bills.length === 0) {
      target.innerHTML = '<p class="empty-state">표시할 법안이 없습니다.</p>';
      return;
    }

    target.innerHTML = bills.map(bill => `
      <div class="bill-item" data-bill-id="${bill.bill_id}">
        <div class="bill-number">${bill.bill_id}</div>
        <div class="bill-title">${bill.title}</div>
        <div class="bill-meta">
          <span class="policy-stage-badge">${this.stageLabel(bill.current_stage)}</span>
        </div>
      </div>
    `).join('');

    // Add click handlers
    target.querySelectorAll('.bill-item').forEach(item => {
      item.addEventListener('click', () => {
        const billId = item.dataset.billId;
        this.loadBillDetail(billId);
      });
    });
  },

  /**
   * Load and show bill detail
   */
  async loadBillDetail(billId) {
    this.state.selectedBill = billId;
    this.hideAllPanels();
    this.panelShow(this.billDetailPanel);

    try {
      // TODO: Uncomment when API is ready
      // const response = await fetch(`/api/us/congress/bills/${billId}`);
      // const bill = await response.json();
      // this.renderBillDetail(bill);

      // Mock data
      this.renderBillDetail({
        bill_id: billId,
        title: 'Export Control Reform Act',
        sponsor: 'Sen. Smith (D-CA)',
        introduced_date: '2024-01-15',
        current_stage: 'reported',
        summary: 'Comprehensive reform of US export control systems for advanced technology.',
        committees: [
          { committee_id: 'SSFR', name: 'Committee on Foreign Relations' }
        ],
        related_bills: [
          { bill_id: 'H.R.119-456', title: 'Companion bill in House' }
        ],
      });
    } catch (error) {
      console.error('Error loading bill detail:', error);
      document.getElementById('bill-detail-content').innerHTML =
        '<p class="empty-state">법안 정보를 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Render bill detail
   */
  renderBillDetail(bill) {
    const content = document.getElementById('bill-detail-content');
    document.getElementById('bill-number-title').textContent = bill.bill_id;
    document.getElementById('bill-title-subtitle').textContent = bill.title;

    const sections = [
      {
        title: '스폰서',
        content: `<div class="bill-sponsor">${bill.sponsor}</div>`,
      },
      {
        title: '요약',
        content: `<div class="bill-detail-section-content">${bill.summary}</div>`,
      },
      {
        title: '회부 위원회',
        content: bill.committees ? bill.committees.map(c =>
          `<div class="bill-sponsor">${c.name}</div>`
        ).join('') : '<div class="empty-state">정보 없음</div>',
      },
      {
        title: '관련 법안',
        content: bill.related_bills && bill.related_bills.length > 0 ?
          `<div class="bill-related-list">${bill.related_bills.map(rb =>
            `<div class="bill-related-item">${rb.bill_id}: ${rb.title}</div>`
          ).join('')}</div>` :
          '<div class="empty-state">관련 법안 없음</div>',
      },
    ];

    content.innerHTML = sections.map(sec => `
      <div class="bill-detail-section">
        <div class="bill-detail-section-title">${sec.title}</div>
        <div class="bill-detail-section-content">${sec.content}</div>
      </div>
    `).join('');
  },

  /**
   * Load executive orders and regulations
   */
  async loadExecutiveContent(type) {
    const container = document.getElementById('executive-content');
    try {
      container.innerHTML = '<p class="empty-state">데이터 로딩 중…</p>';

      if (type === 'eo') {
        // TODO: Uncomment when API is ready
        // const response = await fetch('/api/us/executive/orders?limit=20');
        // const orders = await response.json();
        // this.renderExecutiveOrders(orders);

        this.renderExecutiveOrders([
          { eo_number: '14156', title: 'Strengthening American Leadership in Semiconductors', signed_date: '2024-08-01' },
          { eo_number: '14155', title: 'Ensuring Responsible AI Development', signed_date: '2024-07-15' },
        ]);
      } else {
        // TODO: Uncomment when API is ready
        // const response = await fetch('/api/us/executive/cfr-titles');
        // const titles = await response.json();
        // this.renderRegulations(titles);

        this.renderRegulations([
          { title_number: '15', name: 'Commerce and Foreign Trade' },
          { title_number: '50', name: 'War and National Defense' },
        ]);
      }
    } catch (error) {
      console.error('Error loading executive content:', error);
      container.innerHTML = '<p class="empty-state">데이터를 불러올 수 없습니다.</p>';
    }
  },

  /**
   * Render executive orders
   */
  renderExecutiveOrders(orders) {
    const container = document.getElementById('executive-content');
    if (!orders || orders.length === 0) {
      container.innerHTML = '<p class="empty-state">행정명령이 없습니다.</p>';
      return;
    }

    container.innerHTML = orders.map(eo => `
      <div class="eo-item" data-eo-number="${eo.eo_number}">
        <div class="eo-number">EO ${eo.eo_number}</div>
        <div class="eo-title">${eo.title}</div>
        <div class="eo-meta">${eo.signed_date}</div>
      </div>
    `).join('');
  },

  /**
   * Render regulations by CFR title
   */
  renderRegulations(titles) {
    const container = document.getElementById('executive-content');
    if (!titles || titles.length === 0) {
      container.innerHTML = '<p class="empty-state">규제가 없습니다.</p>';
      return;
    }

    container.innerHTML = titles.map(title => `
      <div class="regulation-item" data-title="${title.title_number}">
        <div class="regulation-title">CFR Title ${title.title_number}</div>
        <div class="regulation-desc">${title.name}</div>
      </div>
    `).join('');
  },

  /**
   * Map stage value to Korean label
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
