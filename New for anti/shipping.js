// Shipping capacity UI.
//
// The Python engine owns every calculation. This layer normalizes the static
// shipping_capacity_v1 snapshot, labels each number with how it was produced
// (observed / estimated / scenario), and renders five dashboard views.
//
// The data-contract boundary below (normalizeSnapshot, INPUT_STATUS) comes from
// the Codex foundation and is deliberately the only place snapshot fields are
// read; everything after it works on already-validated values.
(() => {
  const DATA_URL = '/public/data/shipping_capacity_v1.json';

  const VIEW_META = {
    shipping_fleet: {
      eyebrow: 'OBSERVED FLEET',
      title: '글로벌 선대',
      desc: 'UNCTAD가 연간 집계한 세계 상선 선복량과 선종별 구성입니다. 이 화면의 숫자만 관측값이며, 나머지 화면은 이 선대를 기준으로 한 추정·시나리오입니다.'
    },
    shipping_routes: {
      eyebrow: 'ROUTE CAPACITY',
      title: '항로별 선복량',
      desc: '대표 항로가 묶어두는 선복량을 연간 화물톤·왕복주기·적재율로 역산한 추정치입니다. 세계 선대 관측 DWT와 직접 합산할 수 없습니다.'
    },
    shipping_chokepoints: {
      eyebrow: 'CHOKEPOINT MONITOR',
      title: '초크포인트 모니터',
      desc: 'IMF PortWatch의 최근 7일 추정 교역량을 직전 28일 평균과 비교한 단기 이상 신호입니다. 물리적 봉쇄율이 아닙니다.'
    },
    shipping_scenarios: {
      eyebrow: 'SHOCK SIMULATOR',
      title: '봉쇄 충격 시뮬레이터',
      desc: '실효 봉쇄율과 지속일 조합별로 엔진이 사전 계산해 둔 선복량·백로그·억류 결과를 조회합니다. 브라우저에서 다시 계산하지 않습니다.'
    },
    shipping_environment: {
      eyebrow: 'NET ZERO PATHWAY',
      title: 'Net Zero 시나리오',
      desc: 'IMO 2050 넷제로 전략의 중간 관문인 CII 감축 일정(2026–2030)에 대응해 감속·개조가 유효 선복량을 얼마나 잠식하는지 봅니다. 2050년까지의 전체 경로가 아니라 현재 확정된 감축 계수 구간만 다룹니다.'
    }
  };

  const VIEW_ORDER = [
    ['shipping_fleet', '글로벌 선대'],
    ['shipping_routes', '항로별 선복량'],
    ['shipping_chokepoints', '초크포인트'],
    ['shipping_scenarios', '봉쇄 시뮬레이터'],
    ['shipping_environment', 'Net Zero']
  ];

  const SHIP_TYPE_LABELS = {
    dry_bulk: '벌크선',
    tanker: '유조선',
    container: '컨테이너선',
    general_cargo: '일반화물선',
    lng: 'LNG선',
    other: '기타 선박'
  };

  // Chart colours are deliberately fixed hex, not CSS variables: canvas cannot
  // resolve var() and silently draws nothing when handed one.
  const SHIP_TYPE_COLORS = {
    dry_bulk: '#38bdf8',
    tanker: '#818cf8',
    container: '#34d399',
    general_cargo: '#fbbf24',
    lng: '#f472b6',
    other: '#64748b'
  };

  const INK = { primary: '#f8fafc', secondary: '#94a3b8', muted: '#64748b' };
  const GRID_LINE = 'rgba(148, 163, 184, 0.10)';

  const INPUT_STATUS = {
    observed_bilateral_sea_weight: ['해상 중량 관측', 'observed', '양자 해상운송 중량 관측값'],
    observed_bilateral_weight_with_route_allocation_proxy: ['관측·항로 배분 추정', 'estimated', '양자 중량 관측값을 대표 항로에 배분한 추정값'],
    comtrade_manufactured_weight_extrapolation_proxy: ['Comtrade 확장 추정', 'estimated', '제조업 표본 중량을 확장한 항로 화물량 추정값']
  };

  let shippingDataPromise = null;
  let activeCharts = [];

  // ---------------------------------------------------------------- helpers

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

  // Container routes carry teu_min/teu_max and leave dwt_* null; every other
  // segment is the reverse. Sizing a box ship in DWT is how the industry does
  // not talk about it, so the unit follows the vessel rather than the table.
  const formatReferenceSize = size => {
    if (!size) return '—';
    if (finite(size.teu_min) && finite(size.teu_max)) {
      return `${formatNumber(size.teu_min / 1000, 0)}K–${formatNumber(size.teu_max / 1000, 0)}K TEU`;
    }
    if (finite(size.dwt_min) && finite(size.dwt_max)) {
      return `${formatNumber(size.dwt_min / 1000, 0)}K–${formatNumber(size.dwt_max / 1000, 0)}K DWT`;
    }
    return '—';
  };

  // ------------------------------------------------------------- components

  const badge = (label, tier = 'neutral', title = '') =>
    `<span class="shipping-badge ${tier}"${title ? ` title="${escapeHtml(title)}"` : ''}>${escapeHtml(label)}</span>`;

  const kpi = (label, value, note = '', { featured = false, key = '', active = false } = {}) => {
    const clickable = key
      ? ` is-clickable${active ? ' is-active' : ''}" data-shipping-kpi="${escapeHtml(key)}" role="button" tabindex="0`
      : '';
    return `
    <article class="shipping-kpi${featured ? ' featured' : ''}${clickable}">
      <span class="shipping-kpi-label">${escapeHtml(label)}</span>
      <strong>${value}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ''}
    </article>`;
  };

  const panel = (kicker, title, body, aside = '') => `
    <section class="shipping-panel">
      ${title ? `<div class="shipping-panel-heading">
        <div>${kicker ? `<p class="shipping-panel-kicker">${escapeHtml(kicker)}</p>` : ''}<h2>${escapeHtml(title)}</h2></div>
        ${aside}
      </div>` : ''}
      ${body}
    </section>`;

  const definitionRows = rows => `<div class="shipping-definition-list">${rows.map(([label, value]) => `
    <div><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`).join('')}</div>`;

  // A note that would otherwise take a full panel for something the reader
  // consults once. Anchored to its trigger, so it cannot use position:fixed.
  const popover = (id, triggerLabel, title, body) => `
    <span class="shipping-pop" data-shipping-pop="${escapeHtml(id)}">
      <button type="button" class="shipping-pop-trigger" aria-expanded="false" aria-controls="pop-${escapeHtml(id)}">
        <span aria-hidden="true">ⓘ</span> ${escapeHtml(triggerLabel)}
      </button>
      <div class="shipping-pop-body" id="pop-${escapeHtml(id)}" role="dialog" aria-label="${escapeHtml(title)}" hidden>
        <div class="shipping-pop-head">
          <strong>${escapeHtml(title)}</strong>
          <button type="button" class="shipping-pop-close" aria-label="닫기">✕</button>
        </div>
        ${body}
      </div>
    </span>`;

  const bindPopovers = root => {
    const close = pop => {
      pop.querySelector('.shipping-pop-body').hidden = true;
      pop.querySelector('.shipping-pop-trigger').setAttribute('aria-expanded', 'false');
    };
    const all = [...root.querySelectorAll('[data-shipping-pop]')];
    all.forEach(pop => {
      const trigger = pop.querySelector('.shipping-pop-trigger');
      const body = pop.querySelector('.shipping-pop-body');
      trigger.addEventListener('click', event => {
        event.stopPropagation();
        const willOpen = body.hidden;
        all.forEach(close);
        body.hidden = !willOpen;
        trigger.setAttribute('aria-expanded', String(willOpen));
      });
      pop.querySelector('.shipping-pop-close').addEventListener('click', () => close(pop));
      body.addEventListener('click', event => event.stopPropagation());
    });
    if (all.length) {
      root.addEventListener('click', () => all.forEach(close));
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') all.forEach(close);
      });
    }
  };

  const table = (headers, rows) => `
    <div class="shipping-table-wrap">
      <table class="shipping-table">
        <thead><tr>${headers.map(h => `<th${h.align ? ` style="text-align:${h.align}"` : ''}>${escapeHtml(h.label ?? h)}</th>`).join('')}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

  const pageShell = (target, body, data) => {
    const meta = VIEW_META[target];
    const tabs = VIEW_ORDER.map(([id, label]) =>
      `<button type="button" class="shipping-tab${id === target ? ' active' : ''}" data-shipping-view="${id}">${escapeHtml(label)}</button>`
    ).join('');
    const source = asArray(data.sources)[0];
    return `
      <div class="shipping-shell">
        <header class="shipping-hero">
          <div>
            <p class="shipping-eyebrow">${escapeHtml(meta.eyebrow)}</p>
            <h1>${escapeHtml(meta.title)}</h1>
            <p class="shipping-hero-desc">${escapeHtml(meta.desc)}</p>
          </div>
          <div class="shipping-hero-meta">
            <span>스냅샷 ${formatDate(data.generated_at)}</span>
            ${source ? `<a class="shipping-source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noopener">UNCTAD 원문 ↗</a>` : ''}
          </div>
        </header>
        <nav class="shipping-tabs" aria-label="해운 데이터 화면">${tabs}</nav>
        <div class="shipping-content">${body}</div>
      </div>`;
  };

  // ------------------------------------------------------------------ chart

  const destroyCharts = () => {
    activeCharts.forEach(chart => { try { chart.destroy(); } catch (_) { /* already gone */ } });
    activeCharts = [];
  };

  const createChart = (root, canvasId, config) => {
    const canvas = root.querySelector(`#${canvasId}`);
    if (!canvas || typeof Chart === 'undefined') return null;
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    const chart = new Chart(canvas, config);
    activeCharts.push(chart);
    return chart;
  };

  const chartOptions = ({ horizontal = false, unit = '', stacked = false, rotate = 0, legend = false } = {}) => ({
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? 'y' : 'x',
    animation: { duration: 320 },
    plugins: {
      legend: legend
        ? { position: 'bottom', labels: { color: INK.secondary, boxWidth: 10, usePointStyle: true, padding: 16, font: { size: 11 } } }
        : { display: false },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: 'rgba(148, 163, 184, 0.25)',
        borderWidth: 1,
        padding: 10,
        titleFont: { size: 12 },
        bodyFont: { size: 12 },
        callbacks: {
          label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.parsed[horizontal ? 'x' : 'y'], 1)} ${unit}`.trim()
        }
      }
    },
    scales: {
      x: {
        stacked,
        grid: { color: horizontal ? GRID_LINE : 'transparent', drawBorder: false },
        ticks: { color: INK.muted, font: { size: 11 }, maxRotation: rotate, minRotation: 0, autoSkip: false }
      },
      y: {
        stacked,
        grid: { color: horizontal ? 'transparent' : GRID_LINE, drawBorder: false },
        ticks: { color: INK.muted, font: { size: 11 } }
      }
    }
  });

  // ----------------------------------------------------------- data contract

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
        baseScenarios: asArray(payload.scenario_summary).length ? payload.scenario_summary : asArray(payload.scenarios),
        environment: payload.environment || null
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

  // ------------------------------------------------------------------ views

  // Per-segment detail shown when a fleet KPI is selected. Container ships get
  // a TEU-denominated panel because that is the unit their routes are sized in
  // -- the snapshot leaves dwt_min/max null for every box-ship route.
  const fleetSegmentDetail = (data, shipType) => {
    const routes = data.ui.routes.filter(route => route.ship_type === shipType);
    const label = SHIP_TYPE_LABELS[shipType] || shipType;
    if (!routes.length) {
      return `<p class="shipping-empty">${escapeHtml(label)}으로 분류된 대표 항로가 아직 없습니다.</p>`;
    }

    const isContainer = shipType === 'container';
    const sorted = [...routes].sort((a, b) =>
      (b.baseline?.baseline_required_dwt || 0) - (a.baseline?.baseline_required_dwt || 0));
    const teuRoutes = sorted.filter(r => finite(r.reference_size?.teu_max));
    const teuCeiling = teuRoutes.length ? Math.max(...teuRoutes.map(r => r.reference_size.teu_max)) : null;

    const summary = isContainer && teuCeiling
      ? definitionRows([
          ['대표 항로', `${formatNumber(routes.length)}개`],
          ['최대 선형', `${formatNumber(teuCeiling / 1000, 0)}K TEU`],
          ['선형 구분', [...new Set(sorted.map(r => r.vessel_class_ko).filter(Boolean))].join(' · ') || '—'],
          ['배치 선복량 합', formatDWT(sorted.reduce((s, r) => s + (r.baseline?.baseline_required_dwt || 0), 0))]
        ])
      : definitionRows([
          ['대표 항로', `${formatNumber(routes.length)}개`],
          ['선형 구분', [...new Set(sorted.map(r => r.vessel_class_ko).filter(Boolean))].join(' · ') || '—'],
          ['배치 선복량 합', formatDWT(sorted.reduce((s, r) => s + (r.baseline?.baseline_required_dwt || 0), 0))]
        ]);

    return `
      ${isContainer ? '<div class="shipping-callout info"><strong>컨테이너선은 TEU로 셉니다.</strong> 박스 적재 능력이 곧 서비스 용량이라 스냅샷도 컨테이너 항로에는 DWT 대신 TEU 선형만 기록합니다. 아래 필요 선복량은 비교를 위해 DWT-equivalent로 환산한 값입니다.</div>' : ''}
      <div class="shipping-grid two-columns" style="margin-top:16px">
        ${panel(isContainer ? 'CONTAINER ROUTES' : 'SEGMENT ROUTES', `${label} 대표 항로`, table(
          [
            '항로',
            isContainer ? '선형 (TEU)' : '선형',
            { label: '연간 화물량', align: 'right' },
            { label: '필요 선복량', align: 'right' }
          ],
          sorted.map(route => `<tr>
            <td style="font-weight:500;color:#f1f5f9">${escapeHtml(route.name_ko || route.id)}</td>
            <td>${escapeHtml(route.vessel_class_ko || '—')}<br><small style="color:#64748b">${formatReferenceSize(route.reference_size)}</small></td>
            <td style="text-align:right">${formatTonnes(route.annual_cargo_tonnes)}</td>
            <td style="text-align:right;font-weight:600">${formatDWT(route.baseline?.baseline_required_dwt)}</td>
          </tr>`).join('')
        ), badge(isContainer ? 'TEU 기준 선형' : '모델 추정', isContainer ? 'observed' : 'estimated'))}
        ${panel('SEGMENT PROFILE', `${label} 요약`, summary)}
      </div>`;
  };

  const renderFleet = (data, root) => {
    const fleet = data.fleet || {};
    const rows = [...data.ui.fleetRows].sort((a, b) => b.dwt - a.dwt);
    const byType = type => rows.find(r => r.ship_type === type);
    const SEGMENTS = ['dry_bulk', 'tanker', 'container'];

    const body = `
      <div class="shipping-kpi-grid" id="shipping-fleet-kpis">
        ${kpi('세계 선대 총 선복량', formatDWT(fleet.world_total_dwt), 'UNCTAD 연간 관측 DWT', { featured: true })}
        ${SEGMENTS.map(type => kpi(
          SHIP_TYPE_LABELS[type],
          formatDWT(byType(type)?.dwt),
          `세계 선대 ${formatPct(byType(type)?.share_pct, 1)} · 클릭 시 상세`,
          { key: type }
        )).join('')}
      </div>
      ${panel('FLEET MIX', '선종별 세계 선복량',
        '<div class="shipping-chart-wrap"><canvas id="shipping-fleet-chart"></canvas></div>',
        `<div class="shipping-panel-tools">
          ${popover('fleet-def', '숫자 읽는 법', '선대 수치를 읽는 법', `
            ${definitionRows([
              ['기준일', escapeHtml(fleet.as_of || '—')],
              ['측정 단위', 'DWT · 재화중량톤'],
              ['컨테이너선', 'TEU 선형으로 별도 표기'],
              ['항로 수치와의 차이', '선대는 관측, 항로는 모델 추정']
            ])}
            <p class="shipping-note">${escapeHtml(fleet.rounding_note || '세계 선대는 관측 DWT이며 항로 필요 선복량과 직접 합산하지 않습니다.')}</p>`)}
          ${badge('연간 관측', 'observed', 'UNCTAD Review of Maritime Transport')}
        </div>`)}
      <div id="shipping-fleet-detail"></div>
      ${panel('WORLD FLEET TABLE', '선종별 상세', table(
        ['선종', { label: '선복량', align: 'right' }, { label: '세계 비중', align: 'right' }, '데이터 성격'],
        rows.map(row => `<tr data-ship-type="${escapeHtml(row.ship_type)}">
          <td><span class="shipping-color-dot" style="background:${SHIP_TYPE_COLORS[row.ship_type] || SHIP_TYPE_COLORS.other}"></span>${escapeHtml(SHIP_TYPE_LABELS[row.ship_type] || row.ship_type)}</td>
          <td style="text-align:right">${formatDWT(row.dwt)}</td>
          <td style="text-align:right">${formatPct(row.share_pct, 1)}</td>
          <td>${badge('연간 관측', 'observed')}</td>
        </tr>`).join('')
      ))}`;

    root.innerHTML = pageShell('shipping_fleet', body, data);

    const chart = createChart(root, 'shipping-fleet-chart', {
      type: 'bar',
      data: {
        labels: rows.map(row => SHIP_TYPE_LABELS[row.ship_type] || row.ship_type),
        datasets: [{
          label: '선복량',
          data: rows.map(row => Number(row.dwt) / 1e6),
          backgroundColor: rows.map(row => SHIP_TYPE_COLORS[row.ship_type] || SHIP_TYPE_COLORS.other),
          borderRadius: 5,
          borderSkipped: false,
          barThickness: 22
        }]
      },
      options: chartOptions({ horizontal: true, unit: 'M DWT' })
    });

    // Selecting a segment dims the other bars and opens its route detail, so
    // the chart and the panel below always describe the same thing.
    const detail = root.querySelector('#shipping-fleet-detail');
    const cards = [...root.querySelectorAll('[data-shipping-kpi]')];
    let selected = null;

    const select = shipType => {
      selected = selected === shipType ? null : shipType;
      cards.forEach(card => card.classList.toggle('is-active', card.dataset.shippingKpi === selected));
      detail.innerHTML = selected ? fleetSegmentDetail(data, selected) : '';

      if (chart) {
        chart.data.datasets[0].backgroundColor = rows.map(row => {
          const base = SHIP_TYPE_COLORS[row.ship_type] || SHIP_TYPE_COLORS.other;
          return !selected || row.ship_type === selected ? base : 'rgba(100, 116, 139, 0.28)';
        });
        chart.update('none');
      }
      root.querySelectorAll('tr[data-ship-type]').forEach(tr => {
        tr.style.background = selected && tr.dataset.shipType === selected ? 'rgba(56,189,248,0.10)' : '';
      });
      if (selected) detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };

    cards.forEach(card => {
      const run = () => select(card.dataset.shippingKpi);
      card.addEventListener('click', run);
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); run(); }
      });
    });

    bindPopovers(root);
  };

  const renderRoutes = (data, root) => {
    const routes = [...data.ui.routes]
      .sort((a, b) => (b.baseline?.baseline_required_dwt || 0) - (a.baseline?.baseline_required_dwt || 0));
    const top = routes.slice(0, 12);
    const observedCount = routes.filter(r => statusMeta(r.input_status)[1] === 'observed').length;

    const body = `
      <div class="shipping-callout warning"><strong>항로 필요 선복량은 모델 추정치입니다.</strong> 연간 화물톤·왕복주기·적재율로 계산한 DWT-equivalent이며, 세계 선대 관측 DWT와 같은 종류의 수치가 아닙니다.</div>
      <div class="shipping-kpi-grid">
        ${kpi('대표 항로', `${formatNumber(routes.length)}개`, '용량 계산이 연결된 항로', { featured: true })}
        ${kpi('관측 기반 입력', `${formatNumber(observedCount)}개`, '나머지는 배분·확장 추정')}
        ${kpi('최대 필요 선복량', formatDWT(top[0]?.baseline?.baseline_required_dwt), escapeHtml(top[0]?.name_ko || ''))}
      </div>
      ${panel('ROUTE CAPACITY', '상위 항로 필요 선복량', '<div class="shipping-chart-wrap tall"><canvas id="shipping-routes-chart"></canvas></div>', badge('모델 추정', 'estimated', '화물톤 ÷ 왕복주기 ÷ 적재율'))}
      ${panel('ALL ROUTES', '항로별 상세', table(
        ['항로', '선종·선형', { label: '연간 화물량', align: 'right' }, { label: '필요 DWT', align: 'right' }, { label: 'P10–P90', align: 'right' }, '입력 성격'],
        routes.map(route => {
          const baseline = route.baseline || {};
          const interval = baseline.interval?.baseline_required_dwt || {};
          const [label, tier, note] = statusMeta(route.input_status);
          return `<tr>
            <td style="font-weight:500;color:#f1f5f9">${escapeHtml(route.name_ko || route.id)}</td>
            <td>${escapeHtml(SHIP_TYPE_LABELS[route.ship_type] || route.ship_type)}<br><small style="color:#64748b">${escapeHtml(route.vessel_class_ko || '—')} · ${formatReferenceSize(route.reference_size)}</small></td>
            <td style="text-align:right">${formatTonnes(route.annual_cargo_tonnes)}</td>
            <td style="text-align:right;font-weight:600">${formatDWT(baseline.baseline_required_dwt)}</td>
            <td style="text-align:right;color:#94a3b8">${formatDWT(interval.p10)} – ${formatDWT(interval.p90)}</td>
            <td>${badge(label, tier, note)}</td>
          </tr>`;
        }).join('')
      ))}
      <p class="shipping-note">P10–P90은 화물량·속도·적재율 입력 범위에서 계산된 불확실성 구간입니다.</p>`;

    root.innerHTML = pageShell('shipping_routes', body, data);

    createChart(root, 'shipping-routes-chart', {
      type: 'bar',
      data: {
        labels: top.map(route => (route.name_ko || route.id).replace(' → ', '→')),
        datasets: [{
          label: '필요 선복량',
          data: top.map(route => (route.baseline?.baseline_required_dwt || 0) / 1e6),
          backgroundColor: top.map(route => SHIP_TYPE_COLORS[route.ship_type] || SHIP_TYPE_COLORS.other),
          borderRadius: 5,
          borderSkipped: false,
          barThickness: 16
        }]
      },
      options: chartOptions({ horizontal: true, unit: 'M DWT' })
    });
  };

  const renderChokepoints = (data, root) => {
    const points = data.ui.chokepoints;
    const worst = [...points].filter(p => p.shortfall !== null)
      .sort((a, b) => (b.shortfall || 0) - (a.shortfall || 0))[0];

    const cards = points.map(point => {
      const display = point.display || {};
      const shortfallPct = point.shortfall === null ? null : point.shortfall * 100;
      const remainingPct = point.remaining === null ? null : point.remaining * 100;
      const isStale = Boolean(display.is_stale);
      const severity = shortfallPct === null ? 'neutral' : shortfallPct >= 25 ? 'negative' : shortfallPct >= 10 ? 'warn' : 'positive';
      return `<article class="shipping-chokepoint-card">
        <div class="shipping-chokepoint-head">
          <div><span>${escapeHtml(point.name_en)}</span><h3>${escapeHtml(point.name_ko)}</h3></div>
          ${badge(isStale ? '기준일 경과' : '최근 신호', isStale ? 'neutral' : 'observed')}
        </div>
        <strong class="shipping-change ${severity}">${formatPct(shortfallPct, 0)}</strong>
        <p>${escapeHtml(display.headline_label_ko || '추정 교역량 감소율')} · ${escapeHtml(display.basis_label_ko || '최근 7일 기준')}</p>
        ${definitionRows([
          [display.residual_label_ko || '잔존 추정 교역량', formatPct(remainingPct, 0)],
          ['최근 7일 추정 교역량', `${formatTonnes(point.metric.current_7d_mean_estimated_trade_tonnes)}/일`],
          ['직전 28일 기준선', `${formatTonnes(point.metric.prior_28d_mean_estimated_trade_tonnes)}/일`]
        ])}
        <p class="shipping-note">기준일 ${formatDate(display.latest_date || point.live.latest_date)}${isStale ? ` · ${formatNumber(display.stale_days, 0)}일 경과` : ''}</p>
      </article>`;
    }).join('');

    const body = `
      <div class="shipping-callout info"><strong>관측 이상 신호:</strong> PortWatch의 최근 7일 <em>추정 교역량</em>을 직전 28일 평균과 비교합니다. 실제 통항 DWT·물리적 봉쇄율·보험 미확보율 관측값이 아닙니다.</div>
      ${worst ? `<div class="shipping-kpi-grid">
        ${kpi('최대 위축 통로', escapeHtml(worst.name_ko), `${formatPct((worst.shortfall || 0) * 100, 0)} 감소`, { featured: true })}
        ${kpi('잔존 교역량', formatPct((worst.remaining || 0) * 100, 0), escapeHtml(worst.display?.residual_label_ko || '최근 7일 기준'))}
        ${kpi('모니터 대상', `${formatNumber(points.length)}개 통로`, 'PortWatch 공개 신호')}
      </div>` : ''}
      ${panel('LIVE SIGNAL', '통로별 추정 교역량 변화', `
        <div class="shipping-chart-wrap"><canvas id="shipping-chokepoint-chart"></canvas></div>
        <div class="shipping-legend">
          <span><i style="background:#34d399"></i>정상 범위 · 10% 미만 감소</span>
          <span><i style="background:#fbbf24"></i>주의 · 10–25% 감소</span>
          <span><i style="background:#f87171"></i>위험 · 25% 이상 감소</span>
        </div>`,
        `<div class="shipping-panel-tools">
          ${popover('choke-def', '용어', '초크포인트 지표 읽는 법', `
            ${definitionRows([
              ['감소율', '최근 7일 추정 교역량 ÷ 직전 28일 평균 − 1'],
              ['잔존 추정 교역량', '평소 대비 아직 통과 중인 비율 (감소율 + 잔존 = 100%)'],
              ['색 구간', '10% 미만 정상 · 10–25% 주의 · 25% 이상 위험']
            ])}
            <p class="shipping-note">색 구간은 이 화면이 정한 표시 기준이며, PortWatch가 제공하는 등급이 아닙니다. 감소율 자체는 계산이 아니라 스냅샷에 기록된 값을 그대로 씁니다.</p>`)}
          ${badge('PortWatch 추정', 'estimated')}
        </div>`)}
      <div class="shipping-chokepoint-grid">${cards}</div>
      <p class="shipping-note">호르무즈는 탱커, 나머지 통로는 전체 추정 교역량을 대표 지표로 씁니다. 따라서 호르무즈 수치는 “최근 7일 탱커 추정 교역량 감소율”이며 시나리오 봉쇄율과 같은 숫자가 아닙니다.</p>`;

    root.innerHTML = pageShell('shipping_chokepoints', body, data);

    const charted = points.filter(p => p.shortfall !== null);
    createChart(root, 'shipping-chokepoint-chart', {
      type: 'bar',
      data: {
        labels: charted.map(p => p.name_ko),
        datasets: [{
          label: '추정 교역량 감소율',
          data: charted.map(p => -(p.shortfall * 100)),
          backgroundColor: charted.map(p => {
            const pct = p.shortfall * 100;
            return pct >= 25 ? '#f87171' : pct >= 10 ? '#fbbf24' : '#34d399';
          }),
          borderRadius: 5,
          borderSkipped: false,
          barThickness: 30
        }]
      },
      options: chartOptions({ unit: '%' })
    });

    bindPopovers(root);
  };

  // What each scenario KPI actually counts. Shown on click, because the labels
  // alone ("상업적 선복 갭") do not say which of several plausible things they
  // mean, and a permanent block of definitions would bury the numbers.
  const SCENARIO_METRIC_NOTES = {
    absorbed: ['추가 흡수 선복량', '봉쇄로 우회하거나 대기하면서 <strong>추가로 묶이는 선복량</strong>입니다. 같은 화물을 나르는 데 배가 더 오래 매여 있으니, 그만큼 시장에서 빠집니다. 선박이 사라지는 것이 아니라 회전이 느려지는 몫입니다.'],
    gap: ['상업적 선복 갭', '위 흡수량 중 <strong>예비 선복으로 흡수되지 못하고 남는 부족분</strong>입니다. 선사가 통상 유지하는 여유분을 넘어선 순간부터 운임에 압력이 생깁니다.'],
    backlog: ['기간 말 백로그', '분석 지평이 끝나는 시점에 <strong>아직 실려나가지 못한 화물</strong>입니다. 봉쇄가 풀려도 이 물량이 해소되기까지 시간이 더 걸립니다.'],
    trapped: ['선적 후 억류 DWT', '화물을 실은 채 통로 안쪽에 <strong>묶인 선복량</strong>입니다. 대표 선형 DWT로 환산한 값이며, AIS로 센 실제 척수가 아닙니다.'],
    insurance: ['보험 제외 DWT', '전쟁위험 보험·안전 정책 때문에 <strong>해당 구간에 투입할 수 없다고 가정한 선복량</strong>입니다. 관측이 아니라 시나리오 가정입니다.'],
    traffic: ['트래픽 변화', '영향 항로 전체에서 <strong>실제로 배송 가능한 화물 흐름의 변화율</strong>입니다. 필요 선복량 대비 실제 공급 가능량을 화물 기준으로 가중평균한 값입니다.']
  };

  const scenarioKpis = summary => `<div class="shipping-kpi-grid scenario-kpis">
    ${kpi('추가 흡수 선복량', formatDWT(summary.operational_capacity_absorbed_dwt), '우회 + 대기', { featured: true, key: 'absorbed' })}
    ${kpi('상업적 선복 갭', formatDWT(summary.commercial_capacity_gap_dwt), '예비분 초과 부족', { key: 'gap' })}
    ${kpi('기간 말 백로그', formatTonnes(summary.backlog_cargo_tonnes_horizon), '미운송 화물', { key: 'backlog' })}
    ${kpi('선적 후 억류 DWT', formatDWT(summary.trapped_loaded_dwt), 'AIS 실제 척수 아님', { key: 'trapped' })}
    ${kpi('보험 제외 DWT', formatDWT(summary.insurance_excluded_dwt), '보험·안전 제약 가정', { key: 'insurance' })}
    ${kpi('트래픽 변화', formatPct(summary.weighted_traffic_change_pct, 1), '배송가능 흐름', { key: 'traffic' })}
  </div>
  <div class="shipping-metric-note" id="shipping-metric-note" hidden></div>`;

  const bindScenarioKpis = scope => {
    const note = scope.querySelector('#shipping-metric-note');
    if (!note) return;
    const cards = [...scope.querySelectorAll('.scenario-kpis [data-shipping-kpi]')];
    let open = null;
    cards.forEach(card => {
      const run = () => {
        const key = card.dataset.shippingKpi;
        open = open === key ? null : key;
        cards.forEach(c => c.classList.toggle('is-active', c.dataset.shippingKpi === open));
        if (!open) { note.hidden = true; return; }
        const [title, text] = SCENARIO_METRIC_NOTES[key] || [key, ''];
        note.innerHTML = `<strong>${escapeHtml(title)}</strong><p>${text}</p>`;
        note.hidden = false;
      };
      card.addEventListener('click', run);
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); run(); }
      });
    });
  };

  const renderScenarios = (data, root) => {
    const grid = data.ui_scenario_grid || {};
    const baseScenarios = data.ui.baseScenarios;
    const closureOptions = asArray(grid.closure_pct_options);
    const durationOptions = asArray(grid.duration_day_options);

    if (!baseScenarios.length || !asArray(grid.rows).length) {
      root.innerHTML = pageShell('shipping_scenarios', '<p class="shipping-empty">시나리오 격자 데이터가 없습니다.</p>', data);
      return;
    }

    const initial = baseScenarios.find(item => item.id === 'hormuz_effective_80pct_28d') || baseScenarios[0];
    const initialClosure = closureOptions.includes(80) ? 80 : Math.round(Number(initial.closure_fraction || 0) * 100);
    const initialDuration = durationOptions.includes(Number(initial.duration_days))
      ? Number(initial.duration_days) : durationOptions.at(-1);

    const summaryCards = baseScenarios.map(summary => `
      <article class="shipping-panel">
        <div class="shipping-panel-heading">
          <div><h2 style="font-size:14px">${escapeHtml(summary.name_ko || summary.id)}</h2></div>
          ${badge('가정 기반', 'neutral', '관측이 아니라 명시된 모델 가정입니다')}
        </div>
        ${definitionRows([
          ['실효 봉쇄율', formatPct(Number(summary.closure_fraction) * 100, 0)],
          ['잔존 통항률', formatPct(Number(summary.residual_throughput_rate) * 100, 0)],
          ['지속기간', `${formatNumber(summary.duration_days, 0)}일`],
          ['기간 말 백로그', formatTonnes(summary.backlog_cargo_tonnes_horizon)],
          ['보험 제외 DWT', formatDWT(summary.insurance_excluded_dwt)]
        ])}
      </article>`).join('');

    const body = `
      <div class="shipping-callout warning"><strong>봉쇄 충격은 가정 기반 시나리오입니다.</strong> PortWatch 관측 신호와 물리 봉쇄율을 동일시하지 않으며, 보험 제외·억류·우회는 공개 AIS 원장이 아닌 명시된 모델 가정입니다.</div>
      ${panel('SHOCK SIMULATOR', '사전 계산 시나리오 조회', `
        <div class="shipping-simulator-controls">
          <label>기준 시나리오
            <select id="shipping-scenario-preset" class="shipping-select">
              ${baseScenarios.map(item => `<option value="${escapeHtml(item.id)}"${item.id === initial.id ? ' selected' : ''}>${escapeHtml(item.name_ko || item.id)}</option>`).join('')}
            </select>
          </label>
          <label>봉쇄율
            <select id="shipping-closure-select" class="shipping-select">
              ${closureOptions.map(v => `<option value="${v}"${v === initialClosure ? ' selected' : ''}>${v}%</option>`).join('')}
            </select>
          </label>
          <label>지속기간
            <select id="shipping-duration-select" class="shipping-select">
              ${durationOptions.map(v => `<option value="${v}"${v === initialDuration ? ' selected' : ''}>${v}일</option>`).join('')}
            </select>
          </label>
        </div>
        <div id="shipping-scenario-result"></div>`)}
      ${panel('SCENARIO SUMMARY', '기준 시나리오 전체 영향', `<div class="shipping-grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">${summaryCards}</div>`)}`;

    root.innerHTML = pageShell('shipping_scenarios', body, data);

    const presetEl = root.querySelector('#shipping-scenario-preset');
    const closureEl = root.querySelector('#shipping-closure-select');
    const durationEl = root.querySelector('#shipping-duration-select');
    const resultEl = root.querySelector('#shipping-scenario-result');

    const update = () => {
      const row = asArray(grid.rows).find(item => item.base_scenario_id === presetEl.value
        && Number(item.closure_pct) === Number(closureEl.value)
        && Number(item.duration_days) === Number(durationEl.value));

      if (!row) {
        resultEl.innerHTML = '<p class="shipping-empty">선택한 조합의 사전 계산 결과가 없습니다.</p>';
        return;
      }
      // Cards are rebuilt on every lookup, so their handlers are rebound below.

      const routes = asArray(row.routes).slice()
        .sort((a, b) => (b.operational_capacity_absorbed_dwt || 0) - (a.operational_capacity_absorbed_dwt || 0));
      const nameById = new Map(data.ui.routes.map(r => [r.id, r.name_ko || r.id]));

      resultEl.innerHTML = `
        ${scenarioKpis(row.summary || {})}
        ${routes.length ? `
          <div class="shipping-chart-wrap" style="margin-top:18px"><canvas id="shipping-scenario-chart"></canvas></div>
          ${table(
            ['영향 항로', { label: '정상 필요 DWT', align: 'right' }, { label: '충격 후 필요 DWT', align: 'right' }, { label: '트래픽', align: 'right' }],
            routes.map(r => `<tr>
              <td>${escapeHtml(nameById.get(r.route_id) || r.route_id)}</td>
              <td style="text-align:right;color:#94a3b8">${formatDWT(r.baseline_required_dwt)}</td>
              <td style="text-align:right;font-weight:600">${formatDWT(r.continuity_required_dwt)}</td>
              <td style="text-align:right" class="negative-text">${formatPct(r.traffic_change_pct, 1)}</td>
            </tr>`).join('')
          )}` : '<p class="shipping-empty">이 조합에 영향받는 대표 항로가 없습니다.</p>'}
        <p class="shipping-note">이 값은 브라우저에서 새로 계산하지 않습니다. Python 엔진이 사전 계산한 ${formatNumber(row.horizon_days, 0)}일 분석 지평의 격자 결과입니다.</p>`;

      if (routes.length) {
        createChart(root, 'shipping-scenario-chart', {
          type: 'bar',
          data: {
            labels: routes.map(r => (nameById.get(r.route_id) || r.route_id).replace(' → ', '→')),
            datasets: [
              {
                label: '정상 필요 DWT',
                data: routes.map(r => (r.baseline_required_dwt || 0) / 1e6),
                backgroundColor: 'rgba(100, 116, 139, 0.65)',
                borderRadius: 4,
                barThickness: 14
              },
              {
                label: '충격 후 필요 DWT',
                data: routes.map(r => (r.continuity_required_dwt || 0) / 1e6),
                backgroundColor: '#38bdf8',
                borderRadius: 4,
                barThickness: 14
              }
            ]
          },
          options: chartOptions({ horizontal: true, unit: 'M DWT', legend: true })
        });
      }

      bindScenarioKpis(resultEl);
    };

    [presetEl, closureEl, durationEl].forEach(el => el?.addEventListener('change', update));
    update();
  };

  const renderEnvironment = (data, root) => {
    const env = data.ui.environment;
    const scenarios = asArray(env?.scenarios);

    if (!scenarios.length) {
      root.innerHTML = pageShell('shipping_environment', '<p class="shipping-empty">환경규제 시나리오 데이터가 없습니다.</p>', data);
      return;
    }

    const last = scenarios[scenarios.length - 1];
    const first = scenarios[0];

    const body = `
      <div class="shipping-callout warning"><strong>선박별 예측이 아닙니다.</strong> ${escapeHtml(env.methodology_ko || '')}</div>
      <div class="shipping-kpi-grid">
        ${kpi(`${first.year}년 손실`, formatDWT(first.effective_dwt_loss), `유효 용량 ${formatPct((first.effective_capacity_retention_rate || 0) * 100, 1)} 유지`)}
        ${kpi(`${last.year}년 손실`, formatDWT(last.effective_dwt_loss), `유효 용량 ${formatPct((last.effective_capacity_retention_rate || 0) * 100, 1)} 유지`, { featured: true })}
        ${kpi('CII 감축 목표', formatPct(last.cii_reduction_vs_2019_pct, 1), `${last.year}년 · 2019년 대비`)}
        ${kpi('대상 항로', `${formatNumber(last.representative_route_count)}개`, '대표 항로 기준')}
      </div>
      ${panel('CAPACITY OVER TIME', '연도별 유효 선복량 잠식', `
        <div class="shipping-chart-wrap"><canvas id="shipping-environment-chart"></canvas></div>
        <p class="shipping-note">막대 전체가 정상 배치 선복량이고, 파란 구간이 규제 대응 후에도 남는 유효 용량, 주황 구간이 그해 잠식되는 몫입니다.</p>`,
        `<div class="shipping-panel-tools">
          ${popover('env-def', '숫자 읽는 법', 'Net Zero 지표 읽는 법', `
            ${definitionRows([
              ['CII 감축', 'IMO가 정한 2019년 대비 탄소집약도 감축률'],
              ['유효 선복량 손실', '감속·개조로 같은 기간에 실어나를 수 없게 되는 몫'],
              ['용량 유지율', '정상 대비 남는 서비스 용량 (저·중·고 행동 가정)']
            ])}
            <p class="shipping-note">물리적 선대가 줄어드는 것이 아니라, 같은 배가 더 느리게 돌아 실질 공급이 줄어드는 구조입니다.</p>`)}
          ${badge('모델 시나리오', 'neutral', '관측이 아니라 명시된 행동 가정 범위')}
        </div>`)}
      <div class="shipping-grid two-columns">
        ${panel('PATHWAY', 'CII 감축 일정 대비 잠식', `
          <div class="shipping-chart-wrap"><canvas id="shipping-env-pathway-chart"></canvas></div>
          <p class="shipping-note">감축 계수가 올라갈수록 잠식폭이 비선형으로 커집니다. 2030년 21.5% 감축 지점에서 손실이 2026년의 2.6배입니다.</p>`)}
        ${panel('UNCERTAINTY BAND', '같은 서비스 유지에 필요한 선복량', `
          <div class="shipping-chart-wrap"><canvas id="shipping-env-band-chart"></canvas></div>
          <p class="shipping-note">선사가 감속에 얼마나 공격적으로 대응하는지에 따른 범위입니다. 위쪽 선일수록 대응이 크고 필요 선복량도 커집니다.</p>`)}
      </div>
      ${panel('SCENARIO TABLE', '시나리오별 상세', table(
        ['시나리오', { label: 'CII 감축', align: 'right' }, { label: '유효 선복량 손실', align: 'right' }, { label: '용량 유지율 (저·중·고)', align: 'right' }, { label: '대상 항로', align: 'right' }],
        scenarios.map(sc => {
          const range = sc.effective_capacity_retention_rate_range || {};
          return `<tr>
            <td style="font-weight:500;color:#f1f5f9">${escapeHtml(sc.name_ko || sc.id)}<br><small style="color:#64748b">${sc.year || ''} · ${sc.status === 'scenario_provisional' ? '잠정' : escapeHtml(sc.status || '')}</small></td>
            <td style="text-align:right">${formatPct(sc.cii_reduction_vs_2019_pct, 2)}</td>
            <td style="text-align:right;font-weight:600;color:#fcd34d">${formatDWT(sc.effective_dwt_loss)}</td>
            <td style="text-align:right;color:#94a3b8">${formatPct((range.low || 0) * 100, 1)} · <strong style="color:#f1f5f9">${formatPct((range.central || 0) * 100, 1)}</strong> · ${formatPct((range.high || 0) * 100, 1)}</td>
            <td style="text-align:right">${formatNumber(sc.representative_route_count)}개</td>
          </tr>`;
        }).join('')
      ))}
      ${asArray(env.warnings_ko).length ? panel('CAVEATS', '해석 시 주의', `
        <ul class="shipping-note" style="margin:0;padding-left:1.1rem;line-height:1.9">
          ${env.warnings_ko.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
        </ul>`) : ''}
      ${asArray(env.sources).length ? `<p class="shipping-note">출처: ${env.sources.map(s => `<a class="shipping-source-link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.name)}</a>`).join(' · ')}</p>` : ''}`;

    root.innerHTML = pageShell('shipping_environment', body, data);

    createChart(root, 'shipping-environment-chart', {
      type: 'bar',
      data: {
        labels: scenarios.map(sc => String(sc.year || sc.id)),
        datasets: [
          {
            label: '유효 용량 (규제 대응 후)',
            data: scenarios.map(sc => (sc.effective_service_capacity_dwt || 0) / 1e6),
            backgroundColor: '#38bdf8',
            stack: 'dwt',
            barThickness: 46
          },
          {
            label: '잠식된 선복량',
            data: scenarios.map(sc => (sc.effective_dwt_loss || 0) / 1e6),
            backgroundColor: '#fbbf24',
            stack: 'dwt',
            borderRadius: 4,
            barThickness: 46
          }
        ]
      },
      options: chartOptions({ unit: 'M DWT', stacked: true, legend: true })
    });

    const years = scenarios.map(sc => String(sc.year || sc.id));

    // Loss against the regulatory schedule that drives it. Two units, so the
    // reduction schedule rides a second axis -- the only place in this file
    // that is justified, since the pairing is the whole point of the panel.
    createChart(root, 'shipping-env-pathway-chart', {
      type: 'bar',
      data: {
        labels: years,
        datasets: [
          {
            label: '유효 선복량 손실 (M DWT)',
            data: scenarios.map(sc => (sc.effective_dwt_loss || 0) / 1e6),
            backgroundColor: '#fbbf24',
            borderRadius: 4,
            barThickness: 28,
            yAxisID: 'y'
          },
          {
            label: 'CII 감축률 (%)',
            type: 'line',
            data: scenarios.map(sc => Number(sc.cii_reduction_vs_2019_pct || 0)),
            borderColor: '#38bdf8',
            backgroundColor: '#38bdf8',
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#0f172a',
            pointBorderWidth: 2,
            tension: 0.25,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        ...chartOptions({ legend: true }),
        scales: {
          x: { grid: { color: 'transparent' }, ticks: { color: INK.muted, font: { size: 11 } } },
          y: {
            position: 'left',
            grid: { color: GRID_LINE },
            ticks: { color: '#fbbf24', font: { size: 11 }, callback: v => `${v}M` }
          },
          y1: {
            position: 'right',
            grid: { display: false },
            ticks: { color: '#38bdf8', font: { size: 11 }, callback: v => `${v}%` }
          }
        }
      }
    });

    // The low/central/high band, drawn as three lines rather than a shaded
    // area: the engine publishes three named behaviour paths, not a
    // distribution, and a filled band would imply a confidence interval.
    const band = key => scenarios.map(sc => (sc.same_service_required_dwt_range?.[key] || 0) / 1e6);
    createChart(root, 'shipping-env-band-chart', {
      type: 'line',
      data: {
        labels: years,
        datasets: [
          { label: '고대응', data: band('high'), borderColor: '#f472b6', borderDash: [5, 4], borderWidth: 2, pointRadius: 3, tension: 0.25 },
          { label: '중앙', data: band('central'), borderColor: '#38bdf8', borderWidth: 2.5, pointRadius: 4, tension: 0.25 },
          { label: '저대응', data: band('low'), borderColor: '#34d399', borderDash: [5, 4], borderWidth: 2, pointRadius: 3, tension: 0.25 }
        ]
      },
      options: {
        ...chartOptions({ unit: 'M DWT', legend: true }),
        scales: {
          x: { grid: { color: 'transparent' }, ticks: { color: INK.muted, font: { size: 11 } } },
          y: {
            grid: { color: GRID_LINE },
            ticks: { color: INK.muted, font: { size: 11 }, callback: v => `${v}M` }
          }
        }
      }
    });

    bindPopovers(root);
  };

  // --------------------------------------------------------------- lifecycle

  const bindTabs = (root) => {
    root.querySelectorAll('[data-shipping-view]').forEach(button => {
      button.addEventListener('click', () => {
        const link = document.querySelector(`.dropdown a[data-target="${button.dataset.shippingView}"]`);
        if (link) link.click();
      });
    });
  };

  const RENDERERS = {
    shipping_fleet: renderFleet,
    shipping_routes: renderRoutes,
    shipping_chokepoints: renderChokepoints,
    shipping_scenarios: renderScenarios,
    shipping_environment: renderEnvironment
  };

  const render = async (target, host) => {
    destroyCharts();
    host.scrollTop = 0;
    host.classList.add('shipping-surface');
    host.dataset.shippingTarget = target;
    host.innerHTML = '<div class="shipping-loading"><span></span><p>선복량 데이터를 불러오는 중입니다.</p></div>';

    try {
      const data = await loadShippingData();
      if (host.dataset.shippingTarget !== target) return;
      (RENDERERS[target] || renderFleet)(data, host);
      bindTabs(host);
    } catch (error) {
      console.error('Shipping data load failed:', error);
      host.innerHTML = `
        <div class="shipping-error">
          <strong>해운 데이터를 표시하지 못했습니다.</strong>
          <p>${escapeHtml(error.message)}</p>
          <button type="button" id="shipping-retry">다시 시도</button>
        </div>`;
      host.querySelector('#shipping-retry')?.addEventListener('click', () => render(target, host));
    }
  };

  const unmount = host => {
    destroyCharts();
    if (!host) return;
    host.classList.remove('shipping-surface');
    delete host.dataset.shippingTarget;
    host.innerHTML = '';
  };

  window.ShippingDashboard = { render, unmount };
})();
