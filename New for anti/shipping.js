// Shipping capacity UI foundation.
// The Python engine owns every calculation. This layer only normalizes and
// labels the static shipping_capacity_v1 snapshot for four dashboard views.
(() => {
  const DATA_URL = '/public/data/shipping_capacity_v1.json';
  const SHIP_TYPE_LABELS = {
    dry_bulk: '벌크선',
    tanker: '유조선',
    container: '컨테이너선',
    general_cargo: '일반화물선',
    other: '기타 선박'
  };
  const INPUT_STATUS = {
    observed_bilateral_sea_weight: ['해상 중량 관측', 'observed', '양자 해상운송 중량 관측값'],
    observed_bilateral_weight_with_route_allocation_proxy: ['관측·항로 배분 추정', 'estimated', '양자 중량 관측값을 대표 항로에 배분한 추정값'],
    comtrade_manufactured_weight_extrapolation_proxy: ['Comtrade 확장 추정', 'estimated', '제조업 표본 중량을 확장한 항로 화물량 추정값']
  };

  let shippingDataPromise = null;

  const escapeHtml = value => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
  const finite = value => value !== null && value !== '' && Number.isFinite(Number(value));
  const asArray = value => Array.isArray(value) ? value : [];
  const formatNumber = (value, digits = 0) => finite(value) ? Number(value).toLocaleString('ko-KR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }) : '—';
  const formatPct = (value, digits = 0) => finite(value) ? `${Number(value).toFixed(digits)}%` : '—';
  const formatDWT = value => {
    if (!finite(value)) return '—';
    const number = Number(value);
    if (number >= 1e9) return `${(number / 1e9).toFixed(2)}B DWT`;
    if (number >= 1e6) return `${(number / 1e6).toFixed(2)}M DWT`;
    if (number >= 1e3) return `${(number / 1e3).toFixed(0)}K DWT`;
    return `${formatNumber(number)} DWT`;
  };
  const formatTonnes = value => {
    if (!finite(value)) return '—';
    const number = Number(value);
    if (number >= 1e9) return `${(number / 1e9).toFixed(2)}B t`;
    if (number >= 1e6) return `${(number / 1e6).toFixed(2)}M t`;
    if (number >= 1e3) return `${(number / 1e3).toFixed(0)}K t`;
    return `${formatNumber(number)} t`;
  };
  const formatDate = value => {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? escapeHtml(value) : parsed.toLocaleDateString('ko-KR');
  };

  const statusMeta = status => INPUT_STATUS[status]
    || (String(status || '').startsWith('scenario_seed')
      ? ['시나리오 시드', 'scenario', '공공 화물량 연결 전의 초기 가정']
      : ['입력 상태 확인', 'neutral', '출처 상태가 정의되지 않은 입력값']);

  const badge = (label, tier = 'neutral', title = '') => {
    const palette = {
      observed: ['#0369a1', '#e0f2fe'],
      estimated: ['#92400e', '#fef3c7'],
      scenario: ['#475569', '#e2e8f0'],
      neutral: ['#475569', '#f1f5f9']
    };
    const [text, background] = palette[tier] || palette.neutral;
    return `<span title="${escapeHtml(title)}" style="display:inline-flex;align-items:center;width:max-content;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:600;color:${text};background:${background};">${escapeHtml(label)}</span>`;
  };

  const section = (title, body, eyebrow = '') => `
    <section style="background:var(--surface-1);border:0.5px solid var(--border);border-radius:12px;padding:1.25rem;margin-bottom:1rem;">
      ${title ? `<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin-bottom:1rem;"><div>${eyebrow ? `<p style="margin:0 0 .35rem;color:var(--text-muted);font-size:10px;letter-spacing:.08em;font-weight:700;">${escapeHtml(eyebrow)}</p>` : ''}<h2 style="font-size:16px;font-weight:600;margin:0;color:var(--text-primary);">${escapeHtml(title)}</h2></div></div>` : ''}
      ${body}
    </section>`;

  const kpi = (label, value, note = '') => `
    <div style="min-width:0;padding:1rem;border:0.5px solid var(--border);border-radius:10px;background:var(--surface-0);">
      <p style="margin:0 0 .4rem;color:var(--text-secondary);font-size:12px;">${escapeHtml(label)}</p>
      <p style="margin:0;color:var(--text-primary);font-size:21px;font-weight:600;letter-spacing:-.02em;">${value}</p>
      ${note ? `<p style="margin:.45rem 0 0;color:var(--text-muted);font-size:11px;line-height:1.45;">${escapeHtml(note)}</p>` : ''}
    </div>`;

  const definitionRows = rows => `<div style="display:grid;gap:0;">${rows.map(([label, value]) => `
    <div style="display:flex;justify-content:space-between;gap:1rem;padding:.7rem 0;border-bottom:0.5px solid var(--border);font-size:12px;">
      <span style="color:var(--text-secondary);">${escapeHtml(label)}</span><strong style="color:var(--text-primary);text-align:right;">${value}</strong>
    </div>`).join('')}</div>`;

  const pageShell = (title, description, body, data) => `
    <div class="shipping-foundation" style="padding:2rem;max-width:1280px;margin:0 auto;">
      <header style="display:flex;justify-content:space-between;align-items:flex-end;gap:1.5rem;flex-wrap:wrap;margin:0 0 1.5rem;">
        <div>
          <p style="margin:0 0 .45rem;color:var(--text-muted);font-size:11px;letter-spacing:.1em;font-weight:700;">SHIPPING CAPACITY</p>
          <h1 style="font-size:26px;font-weight:600;letter-spacing:-.025em;margin:0 0 .55rem;color:var(--text-primary);">${escapeHtml(title)}</h1>
          <p style="max-width:760px;color:var(--text-secondary);font-size:13px;line-height:1.6;margin:0;">${escapeHtml(description)}</p>
        </div>
        <div style="display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;">
          ${badge('세계 선대 · 관측', 'observed')}
          ${badge('항로 필요량 · 추정', 'estimated')}
          ${badge('봉쇄 영향 · 시나리오', 'scenario')}
        </div>
      </header>
      ${body}
      <p style="color:var(--text-muted);font-size:11px;margin:1.25rem 0 0;">스냅샷 생성 ${formatDate(data.generated_at)}</p>
    </div>`;

  // This adapter is the only snapshot-to-UI boundary. It prevents a Python
  // field rename from silently rendering `undefined` or a false zero.
  const normalizeSnapshot = payload => {
    const fleetRows = asArray(payload.fleet?.fleet_by_type);
    const routes = asArray(payload.routes);
    if (!fleetRows.length || !routes.length) throw new Error('선대 또는 항로 UI 계약 데이터가 비어 있습니다.');

    const displayById = new Map(asArray(payload.live_display)
      .filter(row => row?.chokepoint_id)
      .map(row => [row.chokepoint_id, row]));
    const chokepoints = asArray(payload.chokepoints).map(point => {
      const live = payload.chokepoints_live?.[point.id] || {};
      const display = displayById.get(point.id) || {};
      const metricKey = display.metric_key || point.primary_live_metric || 'all';
      const metric = live.metrics?.[metricKey] || live.metrics?.all || {};
      const shortfall = finite(display.trade_volume_shortfall_fraction)
        ? Number(display.trade_volume_shortfall_fraction)
        : finite(metric.observed_trade_volume_shortfall_fraction)
          ? Number(metric.observed_trade_volume_shortfall_fraction) : null;
      const remaining = finite(display.remaining_trade_volume_ratio)
        ? Number(display.remaining_trade_volume_ratio)
        : finite(metric.remaining_trade_volume_ratio)
          ? Number(metric.remaining_trade_volume_ratio)
          : shortfall === null ? null : 1 - shortfall;
      return { ...point, live, display, metricKey, metric, shortfall, remaining };
    });

    return {
      ...payload,
      ui: {
        fleetRows,
        routes,
        chokepoints,
        baseScenarios: asArray(payload.scenario_summary).length ? payload.scenario_summary : asArray(payload.scenarios)
      }
    };
  };

  const loadShippingData = async () => {
    if (!shippingDataPromise) {
      shippingDataPromise = fetch(DATA_URL, { cache: 'no-cache' })
        .then(async response => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const payload = await response.json();
          if (payload.schema_version !== 'shipping-capacity-v1') throw new Error('지원하지 않는 선복량 데이터 버전입니다.');
          return normalizeSnapshot(payload);
        })
        .catch(error => {
          shippingDataPromise = null;
          throw error;
        });
    }
    return shippingDataPromise;
  };

  const renderShippingFleet = data => {
    const fleet = data.fleet || {};
    const rows = [...data.ui.fleetRows].sort((a, b) => b.dwt - a.dwt);
    const body = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.75rem;margin-bottom:1rem;">
        ${kpi('세계 선대 총 선복량', formatDWT(fleet.world_total_dwt), 'UNCTAD 연간 관측 DWT')}
        ${kpi('기준일', escapeHtml(fleet.as_of || '—'), escapeHtml(fleet.scope || ''))}
        ${kpi('벌크선 + 유조선', formatPct(rows.filter(row => ['dry_bulk', 'tanker'].includes(row.ship_type)).reduce((sum, row) => sum + Number(row.share_pct || 0), 0), 1), '세계 DWT 중 비중')}
      </div>
      ${section('선종별 세계 선복량', `
        <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:13px;min-width:520px;">
          <thead><tr style="border-bottom:0.5px solid var(--border);color:var(--text-secondary);font-size:11px;"><th style="text-align:left;padding:.65rem;">선종</th><th style="text-align:right;padding:.65rem;">선복량</th><th style="text-align:right;padding:.65rem;">세계 비중</th><th style="text-align:left;padding:.65rem;">데이터 성격</th></tr></thead>
          <tbody>${rows.map(row => `<tr style="border-bottom:0.5px solid var(--border);"><td style="padding:.75rem .65rem;color:var(--text-primary);">${escapeHtml(SHIP_TYPE_LABELS[row.ship_type] || row.ship_type)}</td><td style="padding:.75rem .65rem;text-align:right;">${formatDWT(row.dwt)}</td><td style="padding:.75rem .65rem;text-align:right;">${formatPct(row.share_pct, 1)}</td><td style="padding:.75rem .65rem;">${badge('연간 관측', 'observed')}</td></tr>`).join('')}</tbody>
        </table></div>
        <p style="margin:1rem 0 0;color:var(--text-muted);font-size:12px;line-height:1.55;">${escapeHtml(fleet.rounding_note || '세계 선대는 관측 DWT이며 항로 필요 선복량과 직접 합산하지 않습니다.')}</p>`, 'OBSERVED FLEET')}`;
    return pageShell('글로벌 선대', '세계 상선 선대의 관측 DWT와 선종별 구성을 표시합니다.', body, data);
  };

  const renderShippingRoutes = data => {
    const routes = [...data.ui.routes].sort((a, b) => (b.baseline?.baseline_required_dwt || 0) - (a.baseline?.baseline_required_dwt || 0));
    const body = `
      <div style="padding:1rem 1.1rem;margin-bottom:1rem;border-radius:10px;background:#fffbeb;border:0.5px solid #fde68a;color:#78350f;font-size:12px;line-height:1.6;"><strong>항로 필요 선복량은 모델 추정치입니다.</strong> 연간 화물톤·왕복주기·적재율로 계산한 DWT-equivalent이며, 세계 선대 관측 DWT와 같은 종류의 수치가 아닙니다.</div>
      ${section('대표 항로별 필요 선복량', `
        <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;min-width:860px;">
          <thead><tr style="border-bottom:0.5px solid var(--border);color:var(--text-secondary);font-size:11px;"><th style="text-align:left;padding:.65rem;">항로</th><th style="text-align:left;padding:.65rem;">선종·선형</th><th style="text-align:right;padding:.65rem;">연간 화물량</th><th style="text-align:right;padding:.65rem;">필요 DWT</th><th style="text-align:right;padding:.65rem;">P10–P90</th><th style="text-align:left;padding:.65rem;">입력 성격</th></tr></thead>
          <tbody>${routes.map(route => {
            const baseline = route.baseline || {};
            const interval = baseline.interval?.baseline_required_dwt || {};
            const [label, tier, note] = statusMeta(route.input_status);
            return `<tr style="border-bottom:0.5px solid var(--border);"><td style="padding:.75rem .65rem;color:var(--text-primary);font-weight:500;">${escapeHtml(route.name_ko || route.id)}</td><td style="padding:.75rem .65rem;">${escapeHtml(SHIP_TYPE_LABELS[route.ship_type] || route.ship_type)}<br><span style="color:var(--text-muted);font-size:11px;">${escapeHtml(route.vessel_class_ko || '—')}</span></td><td style="padding:.75rem .65rem;text-align:right;">${formatTonnes(route.annual_cargo_tonnes)}</td><td style="padding:.75rem .65rem;text-align:right;font-weight:600;">${formatDWT(baseline.baseline_required_dwt)}</td><td style="padding:.75rem .65rem;text-align:right;color:var(--text-secondary);">${formatDWT(interval.p10)} – ${formatDWT(interval.p90)}</td><td style="padding:.75rem .65rem;">${badge(label, tier, note)}</td></tr>`;
          }).join('')}</tbody>
        </table></div>
        <p style="margin:1rem 0 0;color:var(--text-muted);font-size:12px;">P10–P90은 화물량·속도·적재율 입력 범위에서 계산된 불확실성 구간입니다.</p>`, 'ROUTE CAPACITY')}`;
    return pageShell('항로별 선복량', '대형선 중심 항로에 필요한 배치 선복량을 투명한 입력 상태와 함께 비교합니다.', body, data);
  };

  const renderShippingChokepoints = data => {
    const cards = data.ui.chokepoints.map(point => {
      const display = point.display || {};
      const shortfallPct = point.shortfall === null ? null : point.shortfall * 100;
      const remainingPct = point.remaining === null ? null : point.remaining * 100;
      const isStale = Boolean(display.is_stale);
      return `<article style="padding:1rem;border:0.5px solid var(--border);border-radius:10px;background:var(--surface-0);">
        <div style="display:flex;justify-content:space-between;gap:.75rem;align-items:flex-start;"><div><p style="margin:0;color:var(--text-muted);font-size:10px;letter-spacing:.06em;">${escapeHtml(point.name_en)}</p><h3 style="margin:.25rem 0 0;font-size:15px;color:var(--text-primary);">${escapeHtml(point.name_ko)}</h3></div>${badge(isStale ? '기준일 경과' : '최근 신호', isStale ? 'scenario' : 'observed')}</div>
        <p style="margin:1rem 0 .35rem;font-size:27px;font-weight:600;color:${shortfallPct >= 25 ? 'var(--text-danger)' : 'var(--text-primary)'};">${formatPct(shortfallPct, 0)}</p>
        <p style="margin:0;color:var(--text-secondary);font-size:11px;line-height:1.55;">${escapeHtml(display.headline_label_ko || '추정 교역량 감소율')} · ${escapeHtml(display.basis_label_ko || '최근 7일 기준')}</p>
        <div style="display:grid;gap:.45rem;margin-top:.8rem;font-size:11px;">${definitionRows([
          [display.residual_label_ko || '잔존 추정 교역량', formatPct(remainingPct, 0)],
          ['최근 7일 추정 교역량', `${formatTonnes(point.metric.current_7d_mean_estimated_trade_tonnes)}/일`],
          ['직전 28일 기준선', `${formatTonnes(point.metric.prior_28d_mean_estimated_trade_tonnes)}/일`]
        ])}</div>
        <p style="margin:.8rem 0 0;color:var(--text-muted);font-size:10px;">기준일 ${formatDate(display.latest_date || point.live.latest_date)}${isStale ? ` · ${formatNumber(display.stale_days, 0)}일 경과` : ''}</p>
      </article>`;
    }).join('');
    const body = `
      <div style="padding:1rem 1.1rem;margin-bottom:1rem;border-radius:10px;background:#eff6ff;border:0.5px solid #bfdbfe;color:#1e3a8a;font-size:12px;line-height:1.6;"><strong>관측 이상 신호:</strong> PortWatch의 최근 7일 <em>추정 교역량</em>을 직전 28일 평균과 비교합니다. 실제 통항 DWT·물리적 봉쇄율·보험 미확보율 관측값이 아닙니다.</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.75rem;">${cards}</div>
      <p style="margin:1rem 0 0;color:var(--text-muted);font-size:12px;line-height:1.55;">호르무즈는 탱커, 나머지 초크포인트는 전체 추정 교역량을 대표 지표로 사용합니다. 따라서 호르무즈의 81%는 “최근 7일 탱커 추정 교역량 감소율”이며 시나리오 봉쇄율과 동일한 숫자가 아닙니다.</p>`;
    return pageShell('초크포인트 모니터', 'PortWatch 공개 신호로 주요 통로의 단기 교역량 위축을 분리해 보여줍니다.', body, data);
  };

  const scenarioKpis = summary => `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:.6rem;">
    ${kpi('추가 흡수 선복량', formatDWT(summary.operational_capacity_absorbed_dwt), '우회 + 대기')}
    ${kpi('상업적 선복 갭', formatDWT(summary.commercial_capacity_gap_dwt), '예비분 초과 부족')}
    ${kpi('기간 말 백로그', formatTonnes(summary.backlog_cargo_tonnes_horizon), '미운송 화물')}
    ${kpi('선적 후 억류 DWT', formatDWT(summary.trapped_loaded_dwt), 'AIS 실제 척수 아님')}
    ${kpi('보험 제외 DWT', formatDWT(summary.insurance_excluded_dwt), '보험·안전 제약 가정')}
    ${kpi('트래픽 변화', formatPct(summary.weighted_traffic_change_pct), '배송가능 흐름')}
  </div>`;

  const renderScenarioGridResult = (root, data, baseId, closurePct, durationDays) => {
    const row = asArray(data.ui_scenario_grid?.rows).find(item => item.base_scenario_id === baseId
      && Number(item.closure_pct) === Number(closurePct)
      && Number(item.duration_days) === Number(durationDays));
    const result = root.querySelector('#shipping-scenario-result');
    if (!result) return;
    if (!row) {
      result.innerHTML = '<p style="color:var(--text-secondary);font-size:12px;">선택 조합의 사전 계산 결과가 없습니다.</p>';
      return;
    }
    result.innerHTML = `${scenarioKpis(row.summary || {})}
      <p style="margin:1rem 0 0;color:var(--text-muted);font-size:11px;line-height:1.55;">이 값은 브라우저에서 새로 계산하지 않습니다. Python 엔진이 사전 계산한 ${formatNumber(row.horizon_days, 0)}일 분석 지평의 격자 결과입니다.</p>`;
  };

  const renderShippingScenarios = data => {
    const grid = data.ui_scenario_grid || {};
    const baseScenarios = data.ui.baseScenarios;
    const closureOptions = asArray(grid.closure_pct_options);
    const durationOptions = asArray(grid.duration_day_options);
    const initial = baseScenarios.find(item => item.id === 'hormuz_effective_80pct_28d') || baseScenarios[0] || {};
    const initialClosure = closureOptions.includes(80) ? 80 : Math.round(Number(initial.closure_fraction || 0) * 100);
    const initialDuration = durationOptions.includes(Number(initial.duration_days)) ? Number(initial.duration_days) : durationOptions.at(-1);
    const summaryCards = baseScenarios.map(summary => `
      <article style="padding:1rem;border:0.5px solid var(--border);border-radius:10px;background:var(--surface-0);">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;"><h3 style="margin:0;font-size:14px;color:var(--text-primary);">${escapeHtml(summary.name_ko || summary.id)}</h3>${badge('가정 기반', 'scenario')}</div>
        ${definitionRows([
          ['실효 봉쇄율', formatPct(Number(summary.closure_fraction) * 100, 0)],
          ['잔존 통항률', formatPct(Number(summary.residual_throughput_rate) * 100, 0)],
          ['지속기간', `${formatNumber(summary.duration_days, 0)}일`],
          ['기간 말 백로그', formatTonnes(summary.backlog_cargo_tonnes_horizon)],
          ['보험 제외 DWT', formatDWT(summary.insurance_excluded_dwt)]
        ])}
      </article>`).join('');
    const body = `
      <div style="padding:1rem 1.1rem;margin-bottom:1rem;border-radius:10px;background:#fffbeb;border:0.5px solid #fde68a;color:#78350f;font-size:12px;line-height:1.6;"><strong>봉쇄 충격은 가정 기반 시나리오입니다.</strong> PortWatch 관측 신호와 물리 봉쇄율을 동일시하지 않으며, 보험 제외·억류·우회는 공개 AIS 원장이 아닌 명시된 모델 가정입니다.</div>
      ${section('사전 계산 시나리오 조회', `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem;margin-bottom:1rem;">
          <label style="display:grid;gap:.35rem;color:var(--text-secondary);font-size:12px;">기준 시나리오<select id="shipping-scenario-preset" style="padding:.6rem;border:0.5px solid var(--border);border-radius:7px;background:var(--surface-0);color:var(--text-primary);font:inherit;">${baseScenarios.map(item => `<option value="${escapeHtml(item.id)}" ${item.id === initial.id ? 'selected' : ''}>${escapeHtml(item.name_ko || item.id)}</option>`).join('')}</select></label>
          <label style="display:grid;gap:.35rem;color:var(--text-secondary);font-size:12px;">봉쇄율<select id="shipping-closure-select" style="padding:.6rem;border:0.5px solid var(--border);border-radius:7px;background:var(--surface-0);color:var(--text-primary);font:inherit;">${closureOptions.map(value => `<option value="${value}" ${value === initialClosure ? 'selected' : ''}>${value}%</option>`).join('')}</select></label>
          <label style="display:grid;gap:.35rem;color:var(--text-secondary);font-size:12px;">지속기간<select id="shipping-duration-select" style="padding:.6rem;border:0.5px solid var(--border);border-radius:7px;background:var(--surface-0);color:var(--text-primary);font:inherit;">${durationOptions.map(value => `<option value="${value}" ${value === initialDuration ? 'selected' : ''}>${value}일</option>`).join('')}</select></label>
        </div><div id="shipping-scenario-result"></div>`, 'SHOCK SIMULATOR')}
      ${section('기준 시나리오 전체 영향', `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:.75rem;">${summaryCards}</div>`, 'SCENARIO SUMMARY')}`;
    return pageShell('봉쇄 충격 시뮬레이터', '실효 봉쇄율과 지속일을 바꿔, 선복량·백로그·억류·보험 제약의 사전 계산 결과를 확인합니다.', body, data);
  };

  const renderShippingView = async (target, host) => {
    host.innerHTML = '<p style="padding:2rem;color:var(--text-secondary);">선복량 데이터를 불러오는 중입니다.</p>';
    try {
      const data = await loadShippingData();
      let html;
      if (target === 'shipping_fleet') html = renderShippingFleet(data);
      else if (target === 'shipping_routes') html = renderShippingRoutes(data);
      else if (target === 'shipping_chokepoints') html = renderShippingChokepoints(data);
      else html = renderShippingScenarios(data);
      host.innerHTML = html;

      if (target === 'shipping_scenarios') {
        const preset = host.querySelector('#shipping-scenario-preset');
        const closure = host.querySelector('#shipping-closure-select');
        const duration = host.querySelector('#shipping-duration-select');
        const update = () => renderScenarioGridResult(host, data, preset.value, closure.value, duration.value);
        [preset, closure, duration].forEach(control => control?.addEventListener('change', update));
        update();
      }
    } catch (error) {
      console.error('Shipping data load failed:', error);
      host.innerHTML = `<p style="padding:2rem;color:var(--text-danger);">해운 데이터를 표시하지 못했습니다: ${escapeHtml(error.message)}</p>`;
    }
  };

  const unmountShipping = host => { if (host) host.innerHTML = ''; };
  window.ShippingDashboard = { render: renderShippingView, unmount: unmountShipping };
})();
