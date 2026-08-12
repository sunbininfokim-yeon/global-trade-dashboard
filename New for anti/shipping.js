// Shipping capacity model UI (PR #44)
// Codex/shipping-capacity-v1-7 + Claude/shipping-ui rendering
// All calc done by Python engine; browser reads shipping_capacity_v1.json only.
// Contracts: https://github.com/sunbininfokim-yeon/global-trade-dashboard/tree/codex/shipping-capacity-v1-7#%EB%8C%80%EC%8B%9C%EB%B3%B4%EB%93%9C-%EA%B3%84%EC%95%BD

let shippingData = null;

const loadShippingData = async () => {
  if (shippingData) return shippingData;
  try {
    const resp = await fetch('data/shipping_capacity_v1.json?v=' + Date.now());
    shippingData = await resp.json();
    return shippingData;
  } catch (e) {
    console.error('Shipping data load failed:', e);
    return null;
  }
};

const formatDWT = (n) => {
  if (!n) return '—';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M DWT';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'k DWT';
  return n.toFixed(0) + ' DWT';
};

const formatTonnes = (n) => {
  if (!n) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B t';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M t';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'k t';
  return n.toFixed(0) + ' t';
};

const renderShippingFleet = async (host) => {
  const data = await loadShippingData();
  if (!data) {
    host.innerHTML = '<p style="color: var(--text-danger);">해운 데이터 로드 실패</p>';
    return;
  }

  const fleet = data.fleet || {};
  const byType = fleet.fleet_by_type || [];
  const totalDwt = fleet.world_total_dwt || 0;

  let html = `<div style="padding: 2rem; max-width: 1200px; margin: 0 auto;">
    <h1 style="font-size: 24px; font-weight: 500; margin: 0 0 1.5rem;">글로벌 선대</h1>
    <div style="background: var(--surface-1); border-radius: 12px; border: 0.5px solid var(--border); padding: 1.5rem; margin-bottom: 2rem;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem;">
        <div>
          <p style="color: var(--text-secondary); font-size: 13px; margin: 0 0 0.5rem;">세계 선대 총 선복량</p>
          <p style="font-size: 28px; font-weight: 500; margin: 0; color: var(--text-primary);">${formatDWT(totalDwt)}</p>
          <p style="color: var(--text-muted); font-size: 12px; margin: 0.5rem 0 0;">기준: UNCTAD 2025 Table II.5</p>
        </div>
        <div>
          <p style="color: var(--text-secondary); font-size: 13px; margin: 0 0 0.5rem;">데이터 시점</p>
          <p style="font-size: 16px; font-weight: 500; margin: 0; color: var(--text-primary);">${fleet.as_of || '—'}</p>
        </div>
      </div>
    </div>`;

  if (byType.length > 0) {
    html += `<h2 style="font-size: 18px; font-weight: 500; margin: 2rem 0 1rem;">선종별 선복량</h2>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
      <thead>
        <tr style="background: var(--surface-1);">
          <th style="text-align: left; padding: 12px; border-bottom: 0.5px solid var(--border);">선종</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">DWT</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">전체 비중</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">척수</th>
        </tr>
      </thead>
      <tbody>`;

    for (const type of byType) {
      const share = totalDwt > 0 ? ((type.dwt / totalDwt) * 100).toFixed(1) : 0;
      html += `<tr style="border-bottom: 0.5px solid var(--border);">
        <td style="padding: 12px; text-align: left;">${type.vessel_type_ko || type.vessel_type || '—'}</td>
        <td style="padding: 12px; text-align: right;">${formatDWT(type.dwt)}</td>
        <td style="padding: 12px; text-align: right;">${share}%</td>
        <td style="padding: 12px; text-align: right;">${type.count || '—'}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  html += `<p style="color: var(--text-muted); font-size: 12px; margin-top: 2rem; line-height: 1.6;">
    <strong>참고:</strong> 세계 선대는 관측값(UNCTAD)입니다. 각 항로의 필요 선복량은 화물톤·왕복주기·적재율로 추정한 값으로, 이 총합과 세계 선대는 다를 수 있습니다.
  </p></div>`;

  host.innerHTML = html;
};

const renderShippingRoutes = async (host) => {
  const data = await loadShippingData();
  if (!data) {
    host.innerHTML = '<p style="color: var(--text-danger);">해운 데이터 로드 실패</p>';
    return;
  }

  const routes = data.routes || [];
  if (routes.length === 0) {
    host.innerHTML = '<p style="color: var(--text-secondary);">항로 데이터 없음</p>';
    return;
  }

  let html = `<div style="padding: 2rem; max-width: 1400px; margin: 0 auto;">
    <h1 style="font-size: 24px; font-weight: 500; margin: 0 0 1.5rem;">항로별 선복량</h1>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
      <thead>
        <tr style="background: var(--surface-1);">
          <th style="text-align: left; padding: 12px; border-bottom: 0.5px solid var(--border);">항로</th>
          <th style="text-align: center; padding: 12px; border-bottom: 0.5px solid var(--border);">선종</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">연간 화물량</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">필요 DWT</th>
          <th style="text-align: right; padding: 12px; border-bottom: 0.5px solid var(--border);">P90</th>
          <th style="text-align: left; padding: 12px; border-bottom: 0.5px solid var(--border);">데이터 상태</th>
        </tr>
      </thead>
      <tbody>`;

    for (const route of routes.slice(0, 25)) {
      const baseline = route.baseline || {};
      const cargoTonnes = route.annual_cargo_tonnes || 0;
      const statusBg = route.input_status === 'comtrade_quality_passed' ? 'var(--bg-success)' : 'var(--bg-warning)';
      const statusText = route.input_status === 'comtrade_quality_passed' ? '검증됨' : '시드';

      html += `<tr style="border-bottom: 0.5px solid var(--border); hover">
        <td style="padding: 12px; text-align: left; font-weight: 500;">${route.name_ko || route.name_en || route.id}</td>
        <td style="padding: 12px; text-align: center; font-size: 12px; color: var(--text-secondary);">${route.vessel_class_ko || route.vessel_class || '—'}</td>
        <td style="padding: 12px; text-align: right;">${formatTonnes(cargoTonnes)}</td>
        <td style="padding: 12px; text-align: right; font-weight: 500;">${formatDWT(baseline.p50)}</td>
        <td style="padding: 12px; text-align: right; color: var(--text-secondary); font-size: 12px;">${formatDWT(baseline.p90)}</td>
        <td style="padding: 12px; text-align: left;">
          <span style="background: ${statusBg}; color: var(--text-primary); padding: 2px 8px; border-radius: var(--radius); font-size: 11px; font-weight: 500;">${statusText}</span>
        </td>
      </tr>`;
    }

    html += `</tbody></table>
    <p style="color: var(--text-muted); font-size: 12px; margin-top: 2rem;">
      <strong>필요 DWT:</strong> 연간 화물량을 왕복주기와 적재율로 역산한 추정값입니다. <strong>P90:</strong> 불확실성 범위의 상한선입니다.
    </p></div>`;

  host.innerHTML = html;
};

const renderShippingChokepoints = async (host) => {
  const data = await loadShippingData();
  if (!data) {
    host.innerHTML = '<p style="color: var(--text-danger);">해운 데이터 로드 실패</p>';
    return;
  }

  const chokepoints = data.chokepoints || [];
  const chokePointsLive = data.chokepoints_live || [];
  const liveDisplay = data.live_display || [];
  const liveQuality = data.live_data_quality || {};

  let html = `<div style="padding: 2rem; max-width: 1200px; margin: 0 auto;">
    <h1 style="font-size: 24px; font-weight: 500; margin: 0 0 0.5rem;">초크포인트 모니터</h1>
    <p style="color: var(--text-secondary); font-size: 13px; margin: 0 0 2rem;">PortWatch 추정 교역량 기반 관측, 최근 7일 평균 vs 28일 기준선</p>`;

  for (const live of liveDisplay) {
    const cp = chokePointsLive[live.chokepoint_id] || {};
    const changeRate = ((cp.latest_7d_rate_of_change || 0) * 100).toFixed(1);
    const direction = cp.latest_7d_rate_of_change > 0 ? '↑' : cp.latest_7d_rate_of_change < 0 ? '↓' : '→';
    const color = cp.latest_7d_rate_of_change > 0 ? 'var(--text-success)' : cp.latest_7d_rate_of_change < 0 ? 'var(--text-danger)' : 'var(--text-muted)';

    html += `<div style="background: var(--surface-1); border-radius: 12px; border: 0.5px solid var(--border); padding: 1.5rem; margin-bottom: 1.5rem;">
      <h3 style="font-size: 16px; font-weight: 500; margin: 0 0 1rem;">${live.label_ko || live.label_en || live.chokepoint_id}</h3>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem;">
        <div>
          <p style="color: var(--text-secondary); font-size: 12px; margin: 0 0 0.5rem;">교역량 변화</p>
          <p style="font-size: 24px; font-weight: 500; margin: 0; color: ${color};">${direction} ${changeRate}%</p>
        </div>
        <div>
          <p style="color: var(--text-secondary); font-size: 12px; margin: 0 0 0.5rem;">최근 7일 기준</p>
          <p style="font-size: 16px; font-weight: 500; margin: 0;">${formatTonnes(cp.latest_7d_capacity_tonnes)}</p>
        </div>
        <div>
          <p style="color: var(--text-secondary); font-size: 12px; margin: 0 0 0.5rem;">28일 기준선</p>
          <p style="font-size: 16px; font-weight: 500; margin: 0;">${formatTonnes(cp.baseline_28d_capacity_tonnes)}</p>
        </div>
      </div>
      ${cp.signal_status_message ? `<p style="color: var(--text-muted); font-size: 12px; margin: 1rem 0 0;">${cp.signal_status_message}</p>` : ''}
    </div>`;
  }

  if (liveQuality.observation_count || liveQuality.last_updated) {
    html += `<p style="color: var(--text-muted); font-size: 12px; margin-top: 2rem;">
      데이터 품질: ${liveQuality.observation_count || 0}개 관측 • 마지막 갱신: ${liveQuality.last_updated || '—'}
    </p>`;
  }

  html += `</div>`;
  host.innerHTML = html;
};

const renderShippingScenarios = async (host) => {
  const data = await loadShippingData();
  if (!data) {
    host.innerHTML = '<p style="color: var(--text-danger);">해운 데이터 로드 실패</p>';
    return;
  }

  const scenarioGrid = data.ui_scenario_grid || {};
  const rows = scenarioGrid.rows || [];
  const summaries = data.scenario_summary || [];

  let html = `<div style="padding: 2rem; max-width: 1200px; margin: 0 auto;">
    <h1 style="font-size: 24px; font-weight: 500; margin: 0 0 1rem;">봉쇄 충격 시뮬레이터</h1>
    <p style="color: var(--text-secondary); font-size: 13px; margin: 0 0 2rem;">초크포인트 봉쇄율 × 지속일 시나리오별 전체 영향</p>`;

  if (rows.length > 0) {
    html += `<div style="overflow-x: auto;">
      <table style="border-collapse: collapse; font-size: 12px; min-width: 100%;">
        <thead>
          <tr style="background: var(--surface-1);">
            <th style="padding: 12px; border: 0.5px solid var(--border); text-align: center;">봉쇄율 × 지속</th>`;

    const scenarios = [...new Set(rows.map(r => r.scenario_label))];
    for (const scenario of scenarios.slice(0, 10)) {
      html += `<th style="padding: 12px; border: 0.5px solid var(--border); text-align: center; font-weight: 500; font-size: 11px;">${scenario}</th>`;
    }
    html += `</tr></thead><tbody>`;

    const closureRates = [...new Set(rows.map(r => r.closure_fraction_pct))];
    for (const rate of closureRates.sort((a, b) => a - b)) {
      html += `<tr><td style="padding: 12px; border: 0.5px solid var(--border); font-weight: 500; white-space: nowrap;">${rate}% 봉쇄</td>`;
      for (const scenario of scenarios.slice(0, 10)) {
        const row = rows.find(r => r.closure_fraction_pct === rate && r.scenario_label === scenario);
        const backlog = row?.backlog_cargo_tonnes || 0;
        const color = backlog > 1e8 ? 'var(--text-danger)' : backlog > 5e7 ? 'var(--text-warning)' : 'var(--text-secondary)';
        html += `<td style="padding: 12px; border: 0.5px solid var(--border); text-align: right; color: ${color}; font-weight: 500;">${formatTonnes(backlog)}</td>`;
      }
      html += `</tr>`;
    }
    html += `</tbody></table></div>`;
  }

  if (summaries.length > 0) {
    html += `<h2 style="font-size: 16px; font-weight: 500; margin: 2rem 0 1rem;">총 영향 (전체 항로 합계)</h2>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem;">`;

    for (const summary of summaries.slice(0, 8)) {
      html += `<div style="background: var(--surface-1); border-radius: 12px; border: 0.5px solid var(--border); padding: 1.5rem;">
        <h3 style="font-size: 14px; font-weight: 500; margin: 0 0 1rem;">${summary.scenario_label || '—'}</h3>
        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div>
            <p style="color: var(--text-secondary); font-size: 11px; margin: 0 0 0.25rem;">Backlog</p>
            <p style="font-size: 16px; font-weight: 500; margin: 0;">${formatTonnes(summary.backlog_cargo_tonnes)}</p>
          </div>
          <div>
            <p style="color: var(--text-secondary); font-size: 11px; margin: 0 0 0.25rem;">억류 DWT</p>
            <p style="font-size: 14px; margin: 0;">${formatDWT(summary.trapped_loaded_dwt)}</p>
          </div>
          <div>
            <p style="color: var(--text-secondary); font-size: 11px; margin: 0 0 0.25rem;">보험 제외 DWT</p>
            <p style="font-size: 14px; margin: 0;">${formatDWT(summary.insurance_excluded_dwt)}</p>
          </div>
        </div>
      </div>`;
    }
    html += `</div>`;
  }

  html += `<p style="color: var(--text-muted); font-size: 12px; margin-top: 2rem; line-height: 1.6;">
    <strong>주의:</strong> 모든 수치는 Python 모델의 시나리오 계산 결과입니다. 보험 제외율·억류일·우회 행동은 모델 가정이며, 실제 보험료·선박별 정책·라우팅 선택은 공개 데이터로 관측할 수 없습니다.
  </p></div>`;

  host.innerHTML = html;
};

const renderShippingView = async (target, host) => {
  if (target === 'shipping_fleet') await renderShippingFleet(host);
  else if (target === 'shipping_routes') await renderShippingRoutes(host);
  else if (target === 'shipping_chokepoints') await renderShippingChokepoints(host);
  else if (target === 'shipping_scenarios') await renderShippingScenarios(host);
};

const unmountShipping = (host) => {
  if (host) host.innerHTML = '';
};

// Expose globally for app.js
window.ShippingDashboard = {
  render: renderShippingView,
  unmount: unmountShipping
};
