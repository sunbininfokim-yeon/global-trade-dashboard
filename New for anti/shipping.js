// Shipping capacity UI.
//
// The Python engine owns every calculation. This layer normalizes the static
// shipping_capacity_v1 snapshot, labels each number with how it was produced
// (observed / estimated / scenario), and renders three dashboard views.
//
// The data-contract boundary below (normalizeSnapshot, INPUT_STATUS) comes from
// the Codex foundation and is deliberately the only place snapshot fields are
// read; everything after it works on already-validated values.
(() => {
  const DATA_URL = '/public/data/shipping_capacity_v1.json';
  // The scenario grid is ~90% of the screen payload by size but only needed
  // once a simulator is opened, so it ships as its own file and is fetched
  // lazily instead of bloating every fleet/route/chokepoint list load.
  const GRID_URL = '/public/data/shipping_capacity_scenario_grid_v1.json';

  const VIEW_META = {
    shipping_fleet: {
      eyebrow: 'OBSERVED FLEET',
      title: '글로벌 선대',
      desc: 'UNCTAD가 연간 집계한 세계 상선 선복량과 선종별 구성입니다. 이 화면의 숫자만 관측값이며, 나머지 화면은 이 선대를 기준으로 한 추정·시나리오입니다.'
    },
    shipping_routes: {
      eyebrow: 'ROUTE CAPACITY',
      title: '항로 운항 선복량',
      desc: '현재 선박 위치가 아니라, 대표 화물 흐름을 유지하기 위해 항로에 계속 배치되어야 하는 모델상 서비스 선복량입니다.'
    },
    shipping_chokepoints: {
      eyebrow: 'CHOKEPOINT MONITOR',
      title: '초크포인트 모니터',
      desc: 'IMF PortWatch가 AIS로 포착한 최근 7일 추정 교역량을 52주 전 같은 7일과 비교합니다. 물리적 봉쇄율이 아니며, 공식 추정이 있는 해협은 함께 보여줍니다.'
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
    ['shipping_routes', '항로 운항 선복량'],
    ['shipping_chokepoints', '초크포인트']
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
  let scenarioGridPromise = null;
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

  // Coastline for the detail map. Same source app.js already uses, so the
  // browser cache is usually warm by the time a chokepoint is opened.
  const COUNTRIES_GEOJSON = 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json';
  // Keep the location panel useful at a glance: the pin alone does not tell a
  // reader whether a strait sits between Iran/Oman, Yemen/Djibouti, etc.
  // These are labels on top of the shared country GeoJSON, not a substitute
  // for a geographic boundary source.
  const CHOKEPOINT_COUNTRY_LABELS = {
    suez: [['이집트', 30.7, 29.8], ['이스라엘', 34.9, 31.3], ['사우디아라비아', 38.4, 27.2]],
    bab_el_mandeb: [['예멘', 45.3, 14.4], ['지부티', 43.1, 11.9], ['에리트레아', 39.6, 15.1]],
    hormuz: [['이란', 55.6, 27.6], ['UAE', 55.3, 25.2], ['오만', 58.1, 24.2]],
    panama: [['파나마', -79.8, 9.2], ['코스타리카', -83.1, 9.9], ['콜롬비아', -77.0, 7.1]],
    malacca: [['말레이시아', 101.9, 4.5], ['싱가포르', 103.8, 1.35], ['인도네시아', 103.0, -1.2]]
  };
  let worldGeoPromise = null;
  const loadWorldGeo = () => {
    if (!worldGeoPromise) {
      worldGeoPromise = fetch(COUNTRIES_GEOJSON, { cache: 'force-cache' })
        .then(response => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
        .catch(error => { worldGeoPromise = null; throw error; });
    }
    return worldGeoPromise;
  };

  /**
   * Equirectangular mini map centred on one chokepoint.
   *
   * Built as inline SVG rather than a deck.gl layer: this sits inside a
   * scrolling panel that deck does not own, and the view never pans or zooms,
   * so a full map engine would cost a canvas and a controller for a picture.
   */
  const renderMiniMap = async (host, point, spanDeg = 20) => {
    const [lon, lat] = point.coordinates || [];
    if (!finite(lon) || !finite(lat)) {
      host.innerHTML = '<p class="shipping-empty">좌표 없음</p>';
      return;
    }

    const W = 300;
    const H = 300;
    const lonSpan = spanDeg;
    const latSpan = spanDeg * (H / W) * Math.cos(lat * Math.PI / 180);
    const x = lo => ((lo - (lon - lonSpan / 2)) / lonSpan) * W;
    const y = la => H - ((la - (lat - latSpan / 2)) / latSpan) * H;

    let paths = '';
    try {
      const geo = await loadWorldGeo();
      const ringToPath = ring => {
        // Skip rings entirely outside the frame before projecting them.
        let inside = false;
        for (const [lo, la] of ring) {
          if (Math.abs(lo - lon) < lonSpan && Math.abs(la - lat) < latSpan) { inside = true; break; }
        }
        if (!inside) return '';
        return 'M' + ring.map(([lo, la]) => `${x(lo).toFixed(1)},${y(la).toFixed(1)}`).join('L') + 'Z';
      };
      const d = (geo.features || []).map(feature => {
        const g = feature.geometry || {};
        if (g.type === 'Polygon') return g.coordinates.map(ringToPath).join('');
        if (g.type === 'MultiPolygon') return g.coordinates.map(poly => poly.map(ringToPath).join('')).join('');
        return '';
      }).join('');
      paths = `<path d="${d}" fill="#1e293b" stroke="#334155" stroke-width="0.7" />`;
    } catch (_) {
      paths = '';
    }

    const labels = asArray(CHOKEPOINT_COUNTRY_LABELS[point.id]).map(([name, labelLon, labelLat]) => {
      const labelX = x(labelLon);
      const labelY = y(labelLat);
      if (labelX < 8 || labelX > W - 8 || labelY < 10 || labelY > H - 8) return '';
      return `<text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}" class="shipping-minimap-country">${escapeHtml(name)}</text>`;
    }).join('');

    host.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" class="shipping-minimap-svg" role="img"
           aria-label="${escapeHtml(point.name_ko)} 위치">
        <rect width="${W}" height="${H}" fill="#0b1220" />
        ${paths}
        ${labels}
        <circle cx="${W / 2}" cy="${H / 2}" r="16" fill="none" stroke="#38bdf8" stroke-width="1" opacity="0.35" />
        <circle cx="${W / 2}" cy="${H / 2}" r="7" fill="#38bdf8" fill-opacity="0.25" stroke="#38bdf8" stroke-width="1.5" />
        <circle cx="${W / 2}" cy="${H / 2}" r="2.5" fill="#e0f2fe" />
      </svg>
      <p class="shipping-note">${formatNumber(Math.abs(lat), 2)}°${lat >= 0 ? 'N' : 'S'} · ${formatNumber(Math.abs(lon), 2)}°${lon >= 0 ? 'E' : 'W'}</p>`;
  };

  const CHOKEPOINT_METRIC_TABS = [
    ['all', '전체'],
    ['container', '컨테이너'],
    ['dry_bulk', '벌크'],
    ['tanker', '탱커']
  ];

  // Daily PortWatch series by ship type as lines: all three types together, or
  // one type alone. A dashed line is the same weekday 52 weeks earlier, which
  // the engine aligns (`metric_histories.<type>.year_ago`); the UI only draws.
  const CHOKEPOINT_RANGES = [['90', '3개월'], ['180', '6개월']];

  // Axis and tooltip in tonnes at the scale of the data: a 50K t/day strait
  // must not print every tick as "0.1M".
  const lineChartOptions = (formatValue, { legend = true, formatTick = formatValue } = {}) => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 320 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: legend
        ? { position: 'bottom', labels: { color: INK.secondary, boxWidth: 22, boxHeight: 2, padding: 14, font: { size: 11 } } }
        : { display: false },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        borderColor: 'rgba(148, 163, 184, 0.25)',
        borderWidth: 1,
        padding: 10,
        callbacks: {
          label: ctx => `${ctx.dataset.label}: ${finite(ctx.parsed.y) ? formatValue(ctx.parsed.y) : '자료 없음'}`
        }
      }
    },
    scales: {
      x: { grid: { color: 'transparent' }, ticks: { color: INK.muted, font: { size: 10 }, maxTicksLimit: 8, autoSkip: true, maxRotation: 0 } },
      y: { beginAtZero: true, grid: { color: GRID_LINE }, ticks: { color: INK.muted, font: { size: 11 }, callback: value => formatTick(value) } }
    }
  });

  const solidLine = (label, data, color) => ({
    label, data, borderColor: color, backgroundColor: 'transparent',
    borderWidth: 2, pointRadius: 0, pointHitRadius: 6, tension: 0.2, spanGaps: false
  });
  const dashedLine = (label, data, color) => ({
    label, data, borderColor: `${color}99`, backgroundColor: 'transparent',
    borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, pointHitRadius: 6, tension: 0.2, spanGaps: false
  });

  const typeSeries = (point, key, days) => {
    const metric = point.live?.metric_histories?.[key] || {};
    const history = asArray(metric.history);
    const priorValues = asArray(metric.year_ago?.values);
    const rows = history.map((row, index) => ({
      date: row.date,
      value: finite(row?.value) ? Number(row.value) : null,
      prior: priorValues.length === history.length && finite(priorValues[index]) ? Number(priorValues[index]) : null
    })).slice(-days);
    return { rows, hasPrior: rows.some(row => row.prior !== null) };
  };

  const renderObservedTypeComparison = point => {
    const available = CHOKEPOINT_METRIC_TABS.filter(([key]) => point.live?.metrics?.[key]);
    if (!available.length) return '';
    return `
      <section class="shipping-observed-type-comparison" aria-label="선종별 추정 교역량 비교">
        <div class="shipping-observed-type-head">
          <div>
            <span>SHIP TYPE COMPARISON</span>
            <h3>선종별 추정 교역량</h3>
          </div>
          <small>실선 올해 · 점선 52주 전 같은 요일</small>
        </div>
        <div class="shipping-observed-type-controls" role="tablist" aria-label="선종 선택">
          ${available.map(([key, label]) => `<button type="button" data-chokepoint-metric="${key}" role="tab" aria-selected="${key === 'all'}">${label}</button>`).join('')}
        </div>
        <div class="shipping-observed-window-controls" role="group" aria-label="그래프 기간 선택">
          ${CHOKEPOINT_RANGES.map(([days, label]) => `<button type="button" data-chokepoint-range="${days}" aria-pressed="${days === '90'}">${label}</button>`).join('')}
        </div>
        <div class="shipping-observed-type-result" data-chokepoint-type-result></div>
      </section>`;
  };

  const bindObservedTypeComparison = (scope, point) => {
    const result = scope.querySelector('[data-chokepoint-type-result]');
    const metricButtons = [...scope.querySelectorAll('[data-chokepoint-metric]')];
    const rangeButtons = [...scope.querySelectorAll('[data-chokepoint-range]')];
    if (!result || !metricButtons.length) return;
    let metricKey = 'all';
    let days = 90;
    let observedChart = null;

    const destroyChart = () => {
      if (!observedChart) return;
      observedChart.destroy();
      activeCharts = activeCharts.filter(chart => chart !== observedChart);
      observedChart = null;
    };

    const update = () => {
      metricButtons.forEach(button => button.setAttribute('aria-selected', String(button.dataset.chokepointMetric === metricKey)));
      rangeButtons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.chokepointRange) === days)));
      destroyChart();
      // "전체" draws the three ship types; the all-vessel total stays a summary
      // figure so that one large line does not flatten the others.
      const keys = metricKey === 'all'
        ? CHOKEPOINT_METRIC_TABS.map(([key]) => key).filter(key => key !== 'all' && point.live?.metric_histories?.[key])
        : [metricKey];
      const series = keys.map(key => ({ key, ...typeSeries(point, key, days) })).filter(item => item.rows.length);
      const dates = series[0]?.rows.map(row => row.date) || [];
      const metric = point.live?.metrics?.[metricKey] || {};
      const recent = Number(metric.current_7d_mean_estimated_trade_tonnes);
      const prior = Number(metric.prior_28d_mean_estimated_trade_tonnes);
      const remaining = Number(metric.remaining_trade_volume_ratio);
      const anyPrior = series.some(item => item.hasPrior);
      result.innerHTML = `
        ${series.length
          ? '<div class="shipping-chart-wrap" style="grid-column:1 / -1"><canvas id="shipping-observed-type-chart"></canvas></div>'
          : '<div class="shipping-callout warning" style="grid-column:1 / -1"><strong>선종별 일별 이력이 아직 발행되지 않았습니다.</strong> 아래 7일·28일 평균만 공개되어 있으며, 평균값을 연결해 일별 그래프를 만들지 않습니다.</div>'}
        <p class="shipping-note" style="grid-column:1 / -1;margin-top:4px">PortWatch AIS 기반 선종별 일별 추정 교역량(톤)입니다. 선종 기준이라 원유·LNG 같은 품목으로 나눌 수 없습니다. 품목별 공식 수치는 아래 EIA 그래프를 보세요.${anyPrior ? '' : ' 52주 전 자료가 없어 점선은 그리지 않았습니다.'}</p>
        <div class="shipping-observed-value">
          <span>${metricKey === 'all' ? '전체 선종 최근 7일 일평균' : `${escapeHtml(SHIP_TYPE_LABELS[metricKey] || metricKey)} 최근 7일 일평균`}</span>
          <strong>${formatTonnes(recent)}/일</strong>
          <small>직전 28일 대비 ${formatPct(metric.change_pct, 1)}</small>
          ${finite(point.live?.metric_histories?.[metricKey]?.year_ago?.change_pct)
            ? `<small>52주 전 같은 7일 대비 ${formatPct(point.live.metric_histories[metricKey].year_ago.change_pct, 1)}</small>` : ''}
        </div>
        <div class="shipping-observed-compare">
          <span>직전 28일 기준선</span>
          <b>${formatTonnes(prior)}/일</b>
          ${finite(remaining) ? `<small>잔존 추정 교역량 ${formatPct(remaining * 100, 1)}</small>` : ''}
        </div>`;
      if (!series.length) return;
      const datasets = [];
      series.forEach(item => {
        const color = SHIP_TYPE_COLORS[item.key] || SHIP_TYPE_COLORS.other;
        const label = SHIP_TYPE_LABELS[item.key] || item.key;
        datasets.push(solidLine(label, item.rows.map(row => row.value), color));
        if (item.hasPrior) datasets.push(dashedLine(`${label} 52주 전`, item.rows.map(row => row.prior), color));
      });
      observedChart = createChart(result, 'shipping-observed-type-chart', {
        type: 'line',
        data: { labels: dates.map(date => String(date).slice(5)), datasets },
        options: lineChartOptions(value => `${formatTonnes(value)}/일`, { formatTick: formatTonnes })
      });
    };

    metricButtons.forEach(button => button.addEventListener('click', () => {
      metricKey = button.dataset.chokepointMetric;
      update();
    }));
    rangeButtons.forEach(button => button.addEventListener('click', () => {
      days = Number(button.dataset.chokepointRange);
      update();
    }));
    update();
  };

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
          ? Number(metric.remaining_trade_volume_ratio) : null;
      // Render-only: the official reference block and the reconstruction
      // ledger stay exactly as the engine published them.
      const officialCargo = payload.official_cargo_monitor?.chokepoints?.[point.id] || null;
      const reconstruction = point.id === 'hormuz' ? (payload.hormuz_reconstruction || null) : null;
      // The Red Sea bypass touches Hormuz (origin) and both Red Sea exits.
      const bypass = ['hormuz', 'bab_el_mandeb', 'suez'].includes(point.id) ? (payload.hormuz_bypass_monitor || null) : null;
      return { ...point, live, display, metricKey, metric, shortfall, remaining, officialCargo, reconstruction, bypass };
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
          if (payload.ui_delivery_contract?.contract_version !== 'shipping-ui-delivery-v2') {
            throw new Error('해운 화면 데이터 계약 버전이 일치하지 않습니다.');
          }
          return normalizeSnapshot(payload);
        })
        .catch(error => {
          shippingDataPromise = null;
          throw error;
        });
    }
    return shippingDataPromise;
  };

  const loadScenarioGrid = async data => {
    if (!scenarioGridPromise) {
      scenarioGridPromise = (async () => {
        try {
          const response = await fetch(GRID_URL, { cache: 'no-cache' });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const payload = await response.json();
          if (payload.schema_version !== 'shipping-capacity-scenario-grid-v1') {
            throw new Error('지원하지 않는 시나리오 격자 데이터 버전입니다.');
          }
          if (payload.bundle_id !== data.bundle_id) {
            throw new Error('시나리오 격자 데이터가 화면 데이터와 버전이 일치하지 않습니다.');
          }
          return payload.ui_scenario_grid;
        } catch (error) {
          scenarioGridPromise = null;
          throw error;
        }
      })();
    }
    return scenarioGridPromise;
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
      ))}
      <div id="shipping-fleet-environment" style="margin-top:32px"></div>`;

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
    renderEnvironmentInto(data, root.querySelector('#shipping-fleet-environment'));
  };

  const renderRoutes = (data, root) => {
    const contractTabs = asArray(data.ui_delivery_contract?.views?.route_service?.tabs);
    const tabs = contractTabs.length ? contractTabs : ['all', 'container', 'dry_bulk', 'tanker'];
    const tabLabels = { all: '전체', container: '컨테이너선', dry_bulk: '벌크선', tanker: '유조선' };
    const chokepointNames = new Map(data.ui.chokepoints.map(point => [point.id, point.name_ko]));
    let activeType = 'all';
    let routeChart = null;

    const draw = () => {
      if (routeChart) {
        routeChart.destroy();
        activeCharts = activeCharts.filter(chart => chart !== routeChart);
      }
      const routes = [...data.ui.routes]
        .filter(route => activeType === 'all' || route.ship_type === activeType)
        .sort((a, b) => (b.baseline?.baseline_required_dwt || 0) - (a.baseline?.baseline_required_dwt || 0));
      const top = routes.slice(0, 12);
      const observedCount = routes.filter(route => statusMeta(route.input_status)[1] === 'observed').length;
      const tabMarkup = `<div class="shipping-tabs" role="tablist">${tabs.map(type => `
        <button class="shipping-tab${type === activeType ? ' active' : ''}" data-route-ship-type="${escapeHtml(type)}" role="tab" aria-selected="${type === activeType}">
          ${escapeHtml(tabLabels[type] || type)}
        </button>`).join('')}</div>`;

      const body = `
        <div class="shipping-callout warning"><strong>현재 선박 위치가 아닙니다.</strong> 연간 화물 흐름을 유지하기 위해 항로에 계속 배치되어야 하는 DWT-equivalent 서비스 선복량입니다.</div>
        ${tabMarkup}
        <div class="shipping-kpi-grid">
          ${kpi('선택 항로', `${formatNumber(routes.length)}개`, `${tabLabels[activeType] || activeType} 운항 서비스`)}
          ${kpi('관측 기반 입력', `${formatNumber(observedCount)}개`, '나머지는 배분·확장 추정')}
          ${kpi('최대 필요 선복량', formatDWT(top[0]?.baseline?.baseline_required_dwt), escapeHtml(top[0]?.name_ko || '—'))}
        </div>
        ${panel('ROUTE SERVICE CAPACITY', `${tabLabels[activeType] || activeType} 필요 선복량`, '<div class="shipping-chart-wrap tall"><canvas id="shipping-routes-chart"></canvas></div>', badge('모델 추정', 'estimated'))}
        ${panel('SERVICE DETAIL', '정상·우회 운항 조건', table(
          ['항로', '선종·선형', { label: '정상 편도', align: 'right' }, { label: '우회 시 추가', align: 'right' }, { label: '필요 DWT', align: 'right' }, '입력 성격'],
          routes.map(route => {
            const baseline = route.baseline || {};
            const normal = route.operational_profile?.normal || {};
            const alternatives = asArray(route.operational_profile?.chokepoint_alternatives)
              .filter(item => item.reroute_available && finite(item.reroute_extra_days_one_way));
            const detour = alternatives.length
              ? alternatives.map(item => `${escapeHtml(chokepointNames.get(item.chokepoint_id) || item.chokepoint_id)} +${formatNumber(item.reroute_extra_days_one_way, 1)}일`).join('<br>')
              : '대체항로 없음·비대상';
            const [label, tier, note] = statusMeta(route.input_status);
            return `<tr>
              <td style="font-weight:500;color:#f1f5f9">${escapeHtml(route.name_ko || route.id)}</td>
              <td>${escapeHtml(SHIP_TYPE_LABELS[route.ship_type] || route.ship_type)}<br><small style="color:#64748b">${escapeHtml(route.vessel_class_ko || '—')} · ${formatReferenceSize(route.reference_size)}</small></td>
              <td style="text-align:right">${formatNumber(normal.sea_days_one_way, 1)}일<br><small style="color:#64748b">왕복주기 ${formatNumber(normal.cycle_days_round_trip, 1)}일</small></td>
              <td style="text-align:right">${detour}</td>
              <td style="text-align:right;font-weight:600">${formatDWT(baseline.baseline_required_dwt)}</td>
              <td>${badge(label, tier, note)}</td>
            </tr>`;
          }).join('')
        ))}
        <p class="shipping-note">운항기간은 설정된 거리·서비스 속도로 계산한 항로 수준 가정이며, 선사 스케줄이나 실제 기항 일정이 아닙니다.</p>`;

      root.innerHTML = pageShell('shipping_routes', body, data);
      routeChart = createChart(root, 'shipping-routes-chart', {
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
      root.querySelectorAll('[data-route-ship-type]').forEach(button => {
        button.addEventListener('click', () => {
          activeType = button.dataset.routeShipType;
          draw();
        });
      });
      // Ship-type filtering replaces the page shell, so restore the top-level
      // shipping view listeners on the newly rendered buttons as well.
      bindTabs(root);
    };
    draw();
  };

  // ------------------------------------------- official cargo & reconstruction
  //
  // Render-only. official_cargo.py and hormuz_reconstruction.py own every
  // number: nothing here converts barrels, mixes publishers or periods,
  // computes a transit probability, or fills a missing value.

  const safeUrl = url => (/^https:\/\//i.test(String(url || '')) ? String(url) : '');
  const sourceLink = (url, label = '원문 ↗') => safeUrl(url)
    ? `<a class="shipping-source-link" href="${escapeHtml(safeUrl(url))}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`
    : '';

  const SOURCE_STATUS = {
    fetched: ['최신 수집', 'observed'],
    cached_fallback: ['직전 정상값 유지', 'estimated'],
    cached_offline: ['저장본', 'neutral'],
    unavailable: ['수집 실패', 'neutral'],
    not_fetched: ['미수집', 'neutral'],
    reference_link_only: ['링크만 제공', 'neutral']
  };
  const sourceStatusBadge = status => {
    const [label, tier] = SOURCE_STATUS[status] || ['상태 미상', 'neutral'];
    return badge(label, tier, String(status || ''));
  };

  // SUMED must stay in the title: EIA's Suez oil figure includes the pipeline.
  const GEOGRAPHY_LABELS = {
    strait_of_hormuz: '호르무즈 해협',
    suez_canal_and_sumed_pipeline: '수에즈+SUMED',
    suez_canal: '수에즈 운하 단독',
    strait_of_bab_el_mandeb: '바브엘만데브 해협'
  };

  // Display scaling only (4,900,000 b/d → 490만 배럴/일); LNG keeps its unit.
  const formatOfficialValue = (value, unit) => {
    if (!finite(value)) return '—';
    const number = Number(value);
    if (unit === 'barrels_per_day') {
      return number >= 1e4 ? `${formatNumber(number / 1e4, 0)}만 배럴/일` : `${formatNumber(number)} 배럴/일`;
    }
    if (unit === 'billion_cubic_feet_per_day') return `${formatNumber(number, 1)} 십억 입방피트/일`;
    return `${formatNumber(number, 1)} ${escapeHtml(unit || '')}`;
  };

  const officialCard = card => `
    <article class="shipping-kpi">
      <span class="shipping-kpi-label">${escapeHtml(card.publisher || '기관')} · ${escapeHtml(GEOGRAPHY_LABELS[card.geography_scope] || card.geography_scope || '')}</span>
      <strong>${finite(card.value) ? formatOfficialValue(card.value, card.unit) : '미보고'}</strong>
      <small>${escapeHtml(card.display_label_ko || card.label_ko || '')}</small>
      ${card.year_ago ? `<small>1년 전(${escapeHtml(card.year_ago.period)}) ${formatOfficialValue(card.year_ago.value, card.unit)}${finite(card.year_ago.change_pct) ? ` → ${Number(card.year_ago.change_pct) > 0 ? '+' : ''}${formatPct(card.year_ago.change_pct, 0)}` : ''}</small>` : ''}
      <small>${escapeHtml(card.period_start || '')} ~ ${escapeHtml(card.period_end || '')} · 발표 ${escapeHtml(card.source_published_at || '—')}</small>
      ${card.license ? `<small>라이선스 ${escapeHtml(card.license)}</small>` : ''}
      <small>${sourceStatusBadge(card.source_status)} ${sourceLink(card.source_url)}</small>
    </article>`;

  const cardNotes = cards => {
    const warnings = [...new Set(cards.map(card => card.warning_ko).filter(Boolean))];
    const attributions = [...new Set(cards.map(card => card.attribution).filter(Boolean))];
    return `${warnings.map(text => `<p class="shipping-note">${escapeHtml(text)}</p>`).join('')}
      ${attributions.map(text => `<p class="shipping-note" style="overflow-wrap:anywhere">${escapeHtml(text)}</p>`).join('')}`;
  };

  const OIL_SERIES = [
    ['total_oil', '석유 전체', '#38bdf8'],
    ['crude_condensate', '원유+콘덴세이트', '#818cf8'],
    ['petroleum_products', '석유제품', '#fbbf24']
  ];
  const FREQUENCY_LABELS = { quarterly: '분기', monthly: '월' };

  const LNG_COLOR = '#f472b6';
  const QUARTER_LABELS = ['1분기', '2분기', '3분기', '4분기'];
  const MONTH_LABELS = Array.from({ length: 12 }, (_, index) => `${index + 1}월`);

  // One chart per publisher/frequency/unit. Period means sit on a calendar
  // axis (quarter or month) with the latest year solid and the year before
  // dashed; a period nobody published stays a gap, never a zero. This is a
  // separate chart from the daily AIS lines, so the two are never mixed.
  const eiaQuarterly = rows => {
    const eia = rows.filter(row => row.publisher === 'EIA' && row.frequency === 'quarterly');
    return {
      oil: eia.filter(row => row.unit === 'barrels_per_day' && OIL_SERIES.some(([key]) => key === row.cargo_category)),
      lng: eia.filter(row => row.cargo_category === 'lng' && row.unit === 'billion_cubic_feet_per_day')
    };
  };

  const periodSlot = (start, frequency) => {
    const month = Number(String(start).slice(5, 7));
    return frequency === 'quarterly' ? Math.floor((month - 1) / 3) : month - 1;
  };

  const overlayChartData = (seriesList, frequency, scale = 1) => {
    const labels = frequency === 'quarterly' ? QUARTER_LABELS : MONTH_LABELS;
    const years = [...new Set(seriesList.flatMap(item => item.points)
      .filter(point => finite(point.value)).map(point => String(point.period_start).slice(0, 4)))].sort();
    const current = years[years.length - 1] || null;
    const prior = years.length > 1 ? years[years.length - 2] : null;
    const valuesFor = (points, year) => labels.map((_, index) => {
      const hit = points.find(point => String(point.period_start).slice(0, 4) === year && periodSlot(point.period_start, frequency) === index);
      return hit && finite(hit.value) ? Number(hit.value) / scale : null;
    });
    const datasets = seriesList.flatMap(item => [
      current && { ...solidLine(`${item.label} ${current}`, valuesFor(item.points, current), item.color), borderWidth: item.width || 2, pointRadius: 3 },
      prior && { ...dashedLine(`${item.label} ${prior}`, valuesFor(item.points, prior), item.color), pointRadius: 2 }
    ].filter(Boolean));
    return { labels, datasets, current, prior };
  };

  const overlayChart = (mount, canvasId, seriesList, frequency, { scale = 1, formatValue, formatTick }) => {
    const { labels, datasets } = overlayChartData(seriesList, frequency, scale);
    if (!datasets.some(dataset => dataset.data.some(value => value !== null))) return null;
    return createChart(mount, canvasId, {
      type: 'line',
      data: { labels, datasets },
      options: lineChartOptions(formatValue, { formatTick })
    });
  };

  const formatManBarrels = value => `${formatNumber(value, 0)}만 배럴/일`;
  const formatBcf = value => `${formatNumber(value, 1)} 십억 입방피트/일`;

  const otherSeriesTable = rows => {
    // EIA quarterly oil and LNG are drawn above; the table keeps the rest.
    const others = rows.filter(row => !(row.publisher === 'EIA' && row.frequency === 'quarterly'));
    if (!others.length) return '';
    const body = [...others]
      .sort((a, b) => `${a.publisher}${a.cargo_category}${a.period_start}`.localeCompare(`${b.publisher}${b.cargo_category}${b.period_start}`))
      .map(row => `<tr>
        <td>${escapeHtml(row.publisher)} · ${escapeHtml(FREQUENCY_LABELS[row.frequency] || row.frequency || '')}</td>
        <td>${escapeHtml(GEOGRAPHY_LABELS[row.geography_scope] || row.geography_scope || '')}</td>
        <td>${escapeHtml(row.label_ko || row.cargo_category || '')}</td>
        <td>${escapeHtml(row.period || '')}</td>
        <td style="text-align:right">${formatOfficialValue(row.value, row.unit)}</td>
      </tr>`).join('');
    return table(['기관 · 주기', '범위', '품목', '기간', { label: '기간 일평균', align: 'right' }], body)
      .replace('class="shipping-table"', 'class="shipping-table compact-table"');
  };

  const renderTransitAssessment = assessment => {
    const refs = asArray(assessment?.advisory_references);
    return `
      ${definitionRows([
        ['통항 성공확률', '산출하지 않음'],
        ['보험 인수 가능 여부', '확인 불가'],
        ['경보 출처 상태', sourceStatusBadge(assessment?.advisory_source_status)]
      ])}
      ${refs.length ? definitionRows(refs.map(ref => [ref.title || '공식 경보', sourceLink(ref.source_url)])) : '<p class="shipping-note">연결된 공식 경보 원문이 없습니다.</p>'}
      ${assessment?.warning_ko ? `<p class="shipping-note">${escapeHtml(assessment.warning_ko)}</p>` : ''}`;
  };

  const renderOfficialCargo = (official, point) => {
    if (!official) return '';
    const cards = asArray(official.reference_cards);
    const supplementary = asArray(official.supplementary_reference_cards);
    const rows = asArray(official.reported_series);
    const { oil, lng } = eiaQuarterly(rows);
    const hasLng = lng.some(row => finite(row.value));
    const breakdownNote = official.commodity_breakdown_status === 'latest_sca_commodity_tonnes_not_connected'
      ? '<p class="shipping-note">수에즈운하청(SCA)의 최신 품목별 톤 통계는 아직 연결되지 않았습니다. 위 일별 그래프는 선종별 추정 교역량이며 품목별 실제 통계가 아닙니다.</p>'
      : '';
    const referenceBody = cards.length || supplementary.length ? `
      ${cards.length ? `<div class="shipping-kpi-grid">${cards.map(officialCard).join('')}</div>${cardNotes(cards)}` : ''}
      ${supplementary.length ? `
        <p class="shipping-panel-kicker" style="margin-top:18px">월간 보조 참고 · 분기 구성비와 섞지 않음</p>
        <div class="shipping-kpi-grid">${supplementary.map(officialCard).join('')}</div>
        ${cardNotes(supplementary)}` : ''}
      ${oil.length ? `
        <p class="shipping-panel-kicker" style="margin-top:18px">EIA 분기 일평균 · 석유 전체 = 원유+콘덴세이트 + 석유제품 · 실선 올해, 점선 전년</p>
        <div class="shipping-chart-wrap"><canvas id="shipping-official-series-chart"></canvas></div>` : ''}
      ${hasLng ? `
        <p class="shipping-panel-kicker" style="margin-top:18px">EIA 분기 일평균 · LNG (십억 입방피트/일 · 석유와 단위가 달라 따로 그림)</p>
        <div class="shipping-chart-wrap" style="min-height:220px"><canvas id="shipping-official-lng-chart"></canvas></div>` : ''}
      ${otherSeriesTable(rows)}
      ${definitionRows([
        ['일별 원유 통과량', '산출하지 않음 · 검증된 일별 품목 자료 없음'],
        ['일별 그래프', '위 선종별 AIS 기반 추정 교역량(톤) · 원유·제품 명세 아님']
      ])}
      ${breakdownNote}`
      : `<div class="shipping-callout warning"><strong>공식 화물 참고 자료 미수집.</strong> 위 일별 추정 교역량과 시뮬레이터는 그대로 동작합니다.</div>${breakdownNote}`;
    // Wide column first: the detail grid's narrow left third is sized for the
    // mini map and squeezes four reference cards into ~120px each.
    return `
      <div class="shipping-grid wide-first">
        ${panel('OFFICIAL CARGO REFERENCE', `${point.name_ko} 공식 화물 참고`, referenceBody, badge('기관 기간 평균', 'estimated', '특정 날짜의 실측값이 아님'))}
        ${panel('TRANSIT CONDITIONS', '통항 여건 확인', renderTransitAssessment(official.transit_assessment), badge('경보 원문', 'neutral'))}
      </div>`;
  };

  const TERM_STATUS = {
    qualified: ['자료 충족', 'observed'],
    unqualified_input: ['후보 있음 · 불충족', 'estimated'],
    missing_no_free_source: ['무료 자료 없음', 'neutral']
  };
  const INPUT_STATUS_LABELS = {
    reported: '보고됨', not_reported: '미보고', no_row: '행 없음', available: '수집됨', rejected: '사용 금지'
  };

  const renderLedger = mass => {
    const rows = asArray(mass?.terms).map(term => {
      const [label, tier] = TERM_STATUS[term.status] || ['상태 미상', 'neutral'];
      const sign = term.sign === 1 ? '+' : term.sign === -1 ? '−' : '대조';
      const candidates = asArray(term.candidates);
      return `<tr>
        <td><strong>${escapeHtml(term.label_ko)}</strong><br><small>${escapeHtml(term.required_ko || '')}</small></td>
        <td style="text-align:center">${sign}</td>
        <td>${badge(label, tier)}</td>
        <td>${candidates.length ? candidates.map(candidate => `<div><strong>${escapeHtml(candidate.source)}</strong> · ${escapeHtml(INPUT_STATUS_LABELS[candidate.input_status] || candidate.input_status || '')}<br><small>${escapeHtml(asArray(candidate.reason_labels_ko).join(' · '))}</small></div>`).join('') : '<small>무료 공개 후보 없음</small>'}</td>
        <td><small>${escapeHtml(term.unlock_ko || '')}</small></td>
      </tr>`;
    }).join('');
    return table(['항목', { label: '부호', align: 'center' }, '상태', '무료 후보 · 불충족 사유', '필요한 자료'], rows);
  };

  const ROUTE_TIER = { hormuz_only_seaborne: 'observed', bypass_capable: 'neutral', outside_strait: 'neutral' };

  const renderProducerExports = exports => {
    const months = asArray(exports?.months);
    if (!months.length) return '<div class="shipping-callout warning">JODI 산유국 원유 수출 자료를 아직 수집하지 못했습니다.</div>';
    const cell = point => point?.status === 'reported' ? formatNumber(point.value, 0)
      : point?.status === 'not_reported' ? '<small>미보고</small>' : '—';
    const rows = asArray(exports.producers).map(producer => `<tr>
      <td><strong>${escapeHtml(producer.name_ko)}</strong></td>
      <td>${badge(producer.route_class_label_ko, ROUTE_TIER[producer.route_class] || 'neutral', producer.route_note_ko)}</td>
      ${months.map(month => `<td style="text-align:right">${cell(asArray(producer.series).find(point => point.period === month))}</td>`).join('')}
    </tr>`).join('');
    const group = exports.hormuz_only_group || {};
    const groupRow = `<tr class="selected-row">
      <td colspan="2"><strong>${escapeHtml(group.label_ko || '')}</strong></td>
      ${months.map(month => {
        const entry = asArray(group.by_month).find(item => item.period === month) || {};
        return `<td style="text-align:right">${finite(entry.value) ? formatNumber(entry.value, 0)
          : `<small title="${escapeHtml(asArray(entry.missing_members).join(', '))} 미보고">미산출</small>`}</td>`;
      }).join('')}
    </tr>`;
    return `${table(['산유국', '수출로', ...months.map(month => ({ label: month, align: 'right' }))], rows + groupRow)}
      <p class="shipping-note">단위 천 배럴/일(월평균) · JODI CRUDEOIL 총수출. ${escapeHtml(exports.warning_ko || '')}</p>
      <p class="shipping-note">${escapeHtml(group.warning_ko || '')}</p>`;
  };

  const renderImporterReceipts = receipts => {
    const months = asArray(receipts?.months);
    const importers = asArray(receipts?.importers);
    const withRows = importers.filter(importer => asArray(importer.origins).length);
    const without = importers.filter(importer => !asArray(importer.origins).length);
    if (!withRows.length) return '<div class="shipping-callout warning">수입국 월간 원유 수입 행을 아직 받지 못했습니다.</div>';
    const rows = withRows.map(importer => asArray(importer.origins).map((origin, index) => `<tr>
      <td>${index === 0 ? `<strong>${escapeHtml(importer.name_ko)}</strong>` : ''}</td>
      <td>${escapeHtml(origin.name_ko)}</td>
      <td>${badge(origin.route_class_label_ko, ROUTE_TIER[origin.route_class] || 'neutral')}</td>
      ${months.map(month => {
        const point = asArray(origin.series).find(item => item.period === month);
        return `<td style="text-align:right">${finite(point?.value) ? formatNumber(point.value / 1000, 0) : '—'}</td>`;
      }).join('')}
    </tr>`).join('')).join('');
    return `${table(['수입국', '원산지', '수출로', ...months.map(month => ({ label: month, align: 'right' }))], rows)}
      <p class="shipping-note">단위 천 톤(순중량, 세관 월 기준) · UN Comtrade HS 2709. ${escapeHtml(receipts.warning_ko || '')}</p>
      ${without.length ? `<p class="shipping-note">${escapeHtml(without.map(importer => importer.name_ko).join('·'))}: 이 기간 월간 행 없음(미보고 또는 공개 지연).</p>` : ''}`;
  };

  const renderSarCoverage = sar => {
    if (!sar || !asArray(sar.acquisitions).length) {
      return '<div class="shipping-callout warning">Sentinel-1 촬영 메타데이터를 아직 받지 못했습니다.</div>';
    }
    const byDate = new Map(asArray(sar.acquisitions).map(row => [row.date, row]));
    const start = new Date(`${sar.window_start}T00:00:00Z`);
    const end = new Date(`${sar.window_end}T00:00:00Z`);
    const days = [];
    for (let day = new Date(start); day <= end && days.length < 62; day.setUTCDate(day.getUTCDate() + 1)) {
      days.push(day.toISOString().slice(0, 10));
    }
    const strip = days.map(day => {
      const row = byDate.get(day);
      const coverage = row ? Number(row.bbox_coverage_fraction) : 0;
      const title = row ? `${day} · 해협 상자 ${formatPct(coverage * 100, 0)} 촬영 · ${row.scene_count}장면` : `${day} · 촬영 없음`;
      return `<span title="${escapeHtml(title)}" style="height:18px;border-radius:3px;background:${row ? `rgba(56,189,248,${(0.25 + 0.75 * coverage).toFixed(2)})` : 'rgba(148,163,184,0.10)'}"></span>`;
    }).join('');
    return `
      <div role="img" aria-label="일별 Sentinel-1 촬영 커버리지" style="display:grid;grid-template-columns:repeat(${days.length},minmax(0,1fr));gap:2px;margin-bottom:12px">${strip}</div>
      ${definitionRows([
        ['관측 기간', `${escapeHtml(sar.window_start)} ~ ${escapeHtml(sar.window_end)}`],
        ['촬영일', `${formatNumber(sar.acquisition_dates)}일`],
        [`해협 상자 ${formatPct(Number(sar.full_coverage_threshold) * 100, 0)} 이상 촬영`, `${formatNumber(sar.full_coverage_dates)}일`],
        ['최대 촬영 공백', finite(sar.max_gap_days) ? `${formatNumber(sar.max_gap_days)}일` : '—'],
        ['최근 촬영일', escapeHtml(sar.latest_acquisition_date || '—')],
        ['선박 탐지·AIS 대조', '하지 않음']
      ])}
      <p class="shipping-note">${escapeHtml(sar.warning_ko || '')}</p>`;
  };

  const renderIdentifiability = recon => {
    const ident = recon.identifiability || {};
    return `
      <div class="shipping-formula-block"><span>설명용 식 · 계산하지 않음</span><strong>${escapeHtml(ident.formula || '')}</strong></div>
      ${definitionRows(asArray(ident.terms).map(term => [term.label_ko, `<span title="${escapeHtml(term.note_ko || '')}">${escapeHtml(term.note_ko || term.status || '')}</span>`]))}
      <p class="shipping-panel-kicker" style="margin-top:14px">쓰지 않는 지름길</p>
      ${definitionRows(asArray(recon.rejected_shortcuts).map(item => [item.label_ko, escapeHtml(item.reason_ko || '')]))}`;
  };

  const RECON_SOURCE_LABELS = { jodi: 'JODI-Oil', comtrade: 'UN Comtrade', sentinel1: 'Copernicus Sentinel-1' };

  const renderReconstruction = recon => {
    if (!recon) return '';
    const headline = recon.headline || {};
    const mass = recon.mass_balance || {};
    const computed = headline.status === 'computed_monthly_unexplained_range' && finite(headline.value);
    const blocking = asArray(headline.blocking_terms).length;
    const total = asArray(mass.terms).length;
    const headlineHtml = computed
      ? `<div class="shipping-callout info"><strong>${escapeHtml(headline.display_ko)}</strong> · ${escapeHtml(mass.period?.period || '')} · ${formatNumber(Number(headline.value) / 1e6, 1)}백만 배럴${headline.range ? ` (범위 ${formatNumber(Number(headline.range.low) / 1e6, 1)}–${formatNumber(Number(headline.range.high) / 1e6, 1)})` : ''}. ${escapeHtml(headline.warning_ko || '')}</div>`
      : `<div class="shipping-callout warning"><strong>${escapeHtml(headline.display_ko || '미포착 화물량: 자료 부족으로 미산출')}</strong> · ${escapeHtml(mass.period?.period || '기간 미정')} 월 원장 기준, 질량수지 ${formatNumber(total)}개 항 중 ${formatNumber(blocking)}개가 같은 경계·기간·품목의 배럴 자료로 채워지지 않았습니다. 빈 항을 0이나 추정 배수로 채우지 않습니다.</div>`;
    const sources = Object.entries(recon.sources || {}).map(([id, source]) => `
      <span>${escapeHtml(RECON_SOURCE_LABELS[id] || id)} ${sourceStatusBadge(source.status)} ${sourceLink(source.source_url, '출처')} ${sourceLink(source.terms_url, '이용조건')}</span>`).join(' · ');
    const attributions = Object.values(recon.sources || {}).map(source => source.attribution).filter(Boolean);
    return `
      ${panel('UNOBSERVED FLOW', '미포착 화물 역산 · 오만만 질량수지', `
        ${headlineHtml}
        <div class="shipping-formula-block" style="margin-top:14px"><span>${escapeHtml(mass.boundary?.label_ko || '')} · 기간 누적 배럴</span><strong>${escapeHtml(mass.equation_ko || '')}</strong></div>
        ${renderLedger(mass)}
        ${asArray(mass.rules_ko).map(rule => `<p class="shipping-note">${escapeHtml(rule)}</p>`).join('')}`,
        `<div class="shipping-panel-tools">${popover('recon-why', '왜 숫자가 없나', '식별 조건과 쓰지 않는 지름길', renderIdentifiability(recon))}${badge('식별 원장', 'neutral')}</div>`)}
      <div class="shipping-grid two-columns">
        ${panel('PRODUCER EXPORTS · JODI', '산유국 원유 수출 (월간 외부 검증)', renderProducerExports(recon.producer_exports), badge('국가 보고', 'observed'))}
        ${panel('SAR COVERAGE', 'Sentinel-1 촬영 커버리지', renderSarCoverage(recon.sar_coverage), badge('메타데이터', 'neutral'))}
      </div>
      ${panel('IMPORTER RECEIPTS · COMTRADE', '수입국 원유 수령 (지연 확인)', renderImporterReceipts(recon.importer_receipts), badge('세관 월 기준', 'observed'))}
      <p class="shipping-note">${sources}</p>
      ${attributions.map(text => `<p class="shipping-note" style="overflow-wrap:anywhere">${escapeHtml(text)}</p>`).join('')}`;
  };

  // Red Sea bypass of Hormuz. Threat events are a manual, source-cited log
  // whose status the engine expires; Yanbu figures are AIS estimates.
  const THREAT_STATUS = {
    recent_events_reported: ['최근 위협 보도', 'estimated'],
    no_recent_events_in_log: ['최근 기록 없음', 'neutral'],
    log_review_stale: ['기록 검토 필요', 'neutral']
  };
  const BYPASS_COLORS = { hormuz: '#f87171', bab_el_mandeb: '#fbbf24', suez: '#38bdf8' };

  const threatenedSegments = bypass => {
    if (bypass?.threat?.status !== 'recent_events_reported') return new Set();
    return new Set(asArray(bypass.threat.events).flatMap(event => asArray(event.affects)));
  };

  const bypassThreatensPoint = point => {
    const hit = threatenedSegments(point.bypass);
    return asArray(point.bypass?.route?.segments).some(segment => segment.chokepoint_id === point.id && hit.has(segment.id));
  };

  const renderBypass = (bypass, point) => {
    if (!bypass) return '';
    const route = bypass.route || {};
    const threat = bypass.threat || {};
    const events = asArray(threat.events);
    const hit = threatenedSegments(bypass);
    const segmentBadge = segment => {
      const threatened = hit.has(segment.id);
      const here = segment.chokepoint_id === point.id;
      return `<span class="shipping-badge ${threatened ? 'estimated' : here ? 'observed' : 'neutral'}">${escapeHtml(segment.label_ko)}${threatened ? ' · 위협 보도' : ''}</span>`;
    };
    const segments = asArray(route.segments);
    const arrow = '<span aria-hidden="true" style="color:#64748b">→</span>';
    const chain = `<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:12px">
      ${segments.filter(segment => segment.type !== 'chokepoint').map(segmentBadge).join(arrow)}
      ${arrow}
      ${segments.filter(segment => segment.type === 'chokepoint').map(segmentBadge).join('<span style="color:#64748b">또는</span>')}
    </div>`;
    const facts = asArray(route.context_facts).map(fact => `<p class="shipping-note">${escapeHtml(fact.label_ko)} ${asArray(fact.sources).map(source => sourceLink(source.url, `${source.publisher}${source.published_at ? ` ${source.published_at}` : ''} ↗`)).join(' ')}</p>`).join('');
    const first = events[0];
    const [statusLabel, statusTier] = THREAT_STATUS[threat.status] || ['상태 미상', 'neutral'];
    const statusHtml = threat.status === 'recent_events_reported'
      ? `<div class="shipping-callout warning"><strong>홍해 우회로에 대한 후티 반군의 봉쇄 위협이 보도되고 있습니다.</strong> ${first ? `${escapeHtml(first.date)} ${escapeHtml(first.event_ko)} 이후` : ''} 얀부 앞바다와 바브엘만데브에서 공격이 이어졌습니다(최근 기록 ${escapeHtml(threat.latest_event_date || '—')}, 기록 검토 ${escapeHtml(threat.reviewed_at || '—')}). 아래는 출처가 달린 수기 기록이며 실시간 경보가 아닙니다. 최신 상황은 통항 여건 확인의 공식 경보 원문을 보세요.</div>`
      : threat.status === 'log_review_stale'
        ? `<div class="shipping-callout info"><strong>위협 기록 검토 필요.</strong> 마지막 검토(${escapeHtml(threat.reviewed_at || '—')}) 후 ${formatNumber(threat.days_since_review)}일이 지나 현재 위협 여부를 표시하지 않습니다.</div>`
        : `<div class="shipping-callout info">최근 ${formatNumber(threat.recent_event_window_days)}일 안에 기록된 사건이 없습니다(검토 ${escapeHtml(threat.reviewed_at || '—')}).</div>`;
    const timeline = events.length ? table(['날짜', '사건', '위치', '근거', '출처'], [...events].reverse().map(event => `<tr>
      <td>${escapeHtml(event.date)}${event.date_precision === 'month' ? '<br><small>월 단위</small>' : ''}</td>
      <td>${escapeHtml(event.event_ko)}</td>
      <td>${escapeHtml(event.location_ko || '')}</td>
      <td>${badge(event.evidence_label_ko || event.evidence_class, event.evidence_class === 'official_statement' ? 'observed' : 'neutral')}</td>
      <td>${asArray(event.sources).map(source => sourceLink(source.url, `${source.publisher} ↗`)).join('<br>')}</td>
    </tr>`).join('')) : '';

    const yanbu = bypass.yanbu_port_activity || {};
    const portSource = bypass.sources?.portwatch_ports || {};
    const yanbuBody = asArray(yanbu.monthly).length ? `
      <div class="shipping-chart-wrap"><canvas id="shipping-bypass-yanbu-chart"></canvas></div>
      ${definitionRows([
        ['최근 7일 평균', finite(yanbu.recent_7d_mean_tonnes_per_day) ? `${formatTonnes(yanbu.recent_7d_mean_tonnes_per_day)}/일` : '—'],
        ['직전 28일 평균', finite(yanbu.prior_28d_mean_tonnes_per_day) ? `${formatTonnes(yanbu.prior_28d_mean_tonnes_per_day)}/일` : '—'],
        ['변화', finite(yanbu.change_pct) ? formatPct(yanbu.change_pct, 1) : '—'],
        ['기준일', escapeHtml(yanbu.latest_date || '—')],
        ['수집 상태', sourceStatusBadge(portSource.status)]
      ])}
      <p class="shipping-note">${escapeHtml(yanbu.warning_ko || '')}</p>
      <p class="shipping-note">${escapeHtml(asArray(yanbu.ports).map(port => port.portname).join(' + '))} 합계 · 실선 올해, 점선 전년${asArray(yanbu.monthly).some(row => row.partial_month) ? ` · 관측일이 모자란 달: ${escapeHtml(asArray(yanbu.monthly).filter(row => row.partial_month).map(row => `${row.month}(${row.days_observed}일)`).join(', '))}` : ''} ${sourceLink(portSource.source_url, 'PortWatch ↗')}</p>`
      : '<div class="shipping-callout warning">얀부항 PortWatch 자료를 아직 받지 못했습니다.</div>';

    const comparison = bypass.official_crude_comparison || {};
    const hasComparison = asArray(comparison.series).some(series => asArray(series.points).length);
    const comparisonBody = hasComparison ? `
      <div class="shipping-chart-wrap"><canvas id="shipping-bypass-eia-chart"></canvas></div>
      <p class="shipping-note">EIA 분기 일평균 · 원유+콘덴세이트 · 실선 올해, 점선 전년. ${escapeHtml(comparison.warning_ko || '')}</p>`
      : '<div class="shipping-callout warning">EIA 해협별 원유 자료를 아직 받지 못했습니다.</div>';

    return `
      ${panel('HORMUZ BYPASS · RED SEA', escapeHtml(route.label_ko || '호르무즈 우회로'), `
        ${chain}
        <p class="shipping-note" style="margin-top:0">${escapeHtml(route.note_ko || '')}</p>
        ${facts}
        <div style="margin-top:14px">${statusHtml}</div>
        ${timeline}`, badge(statusLabel, statusTier))}
      <div class="shipping-grid two-columns">
        ${panel('YANBU · PORTWATCH', '얀부항 탱커 선적 (AIS 추정, 월평균)', yanbuBody, badge('AIS 추정', 'estimated'))}
        ${panel('EIA · CRUDE + CONDENSATE', '해협별 원유 분기 일평균', comparisonBody, badge('기관 분기 평균', 'estimated'))}
      </div>`;
  };

  const drawBypassCharts = (mount, bypass) => {
    const monthly = asArray(bypass?.yanbu_port_activity?.monthly);
    const yanbu = overlayChart(mount, 'shipping-bypass-yanbu-chart', [{
      label: '얀부 탱커 수출 추정', color: '#818cf8',
      points: monthly.map(row => ({ period_start: `${row.month}-01`, value: row.tanker_export_tonnes_per_day }))
    }], 'monthly', { formatValue: value => `${formatTonnes(value)}/일`, formatTick: formatTonnes });
    const series = asArray(bypass?.official_crude_comparison?.series).filter(row => asArray(row.points).length);
    const crude = overlayChart(mount, 'shipping-bypass-eia-chart', series.map(row => ({
      label: row.label_ko, color: BYPASS_COLORS[row.chokepoint_id] || SHIP_TYPE_COLORS.other, points: row.points
    })), 'quarterly', { scale: 1e4, formatValue: formatManBarrels, formatTick: value => `${formatNumber(value, 0)}만` });
    return [yanbu, crude].filter(Boolean);
  };

  let officialCharts = [];
  const renderOfficialCargoInto = (mount, point) => {
    if (!mount) return;
    officialCharts.forEach(chart => { try { chart.destroy(); } catch (_) { /* already gone */ } });
    activeCharts = activeCharts.filter(chart => !officialCharts.includes(chart));
    officialCharts = [];
    if (!point.officialCargo && !point.reconstruction && !point.bypass) { mount.innerHTML = ''; return; }
    mount.innerHTML = `<div class="shipping-content" style="margin-top:18px">
      ${renderOfficialCargo(point.officialCargo, point)}
      ${renderBypass(point.bypass, point)}
      ${renderReconstruction(point.reconstruction)}
    </div>`;
    const { oil, lng } = eiaQuarterly(asArray(point.officialCargo?.reported_series));
    officialCharts.push(...[
      overlayChart(mount, 'shipping-official-series-chart', OIL_SERIES.map(([key, label, color]) => ({
        label, color, width: key === 'total_oil' ? 3 : 2,
        points: oil.filter(row => row.cargo_category === key)
      })), 'quarterly', { scale: 1e4, formatValue: formatManBarrels, formatTick: value => `${formatNumber(value, 0)}만` }),
      overlayChart(mount, 'shipping-official-lng-chart', [{ label: 'LNG', color: LNG_COLOR, points: lng }], 'quarterly',
        { formatValue: formatBcf, formatTick: value => formatNumber(value, 1) }),
      ...drawBypassCharts(mount, point.bypass)
    ].filter(Boolean));
    bindPopovers(mount);
  };

  const CORE_CHOKEPOINT_IDS = ['suez', 'bab_el_mandeb', 'hormuz', 'panama', 'malacca'];

  // Year-over-year, not a floored shortfall: each chokepoint against its own
  // same 7 weekdays 52 weeks earlier, so a rise reads as a rise and straits of
  // very different size share one axis. The engine computes every value
  // (`chokepoint_trend`); this only draws.
  const TREND_COLORS = ['#38bdf8', '#f87171', '#fbbf24', '#34d399', '#a78bfa', '#f472b6', '#fb923c', '#94a3b8', '#2dd4bf'];
  const signedPct = (value, digits = 0) => finite(value) ? `${Number(value) > 0 ? '+' : ''}${formatPct(value, digits)}` : '—';
  const trendSeverity = yoy => !finite(yoy) ? 'neutral' : yoy <= -25 ? 'negative' : yoy <= -10 ? 'warn' : yoy >= 5 ? 'rise' : 'positive';
  const TREND_SEVERITY_STYLE = { rise: ' style="color:#38bdf8"' };
  const AIS_GAP_LABELS = {
    ais_undercount_likely: 'AIS 미포착 가능성 큼',
    ais_above_official: 'AIS가 공식 추정보다 큼',
    consistent: '공식 추정과 방향 일치'
  };

  const renderChokepoints = (data, root, showAll = false) => {
    const allPoints = data.ui.chokepoints;
    const points = showAll
      ? allPoints
      : allPoints.filter(point => CORE_CHOKEPOINT_IDS.includes(point.id));
    const trendById = new Map(asArray(data.chokepoint_trend?.points).map(row => [row.chokepoint_id, row]));
    const trendOf = point => trendById.get(point.id) || {};
    const ranked = [...points].filter(point => finite(trendOf(point).latest_yoy_pct))
      .sort((a, b) => trendOf(a).latest_yoy_pct - trendOf(b).latest_yoy_pct);
    const worst = ranked[0];
    const best = ranked[ranked.length - 1];
    const metricLabel = key => key === 'all' ? '전체 선종' : (SHIP_TYPE_LABELS[key] || key);

    const cards = points.map(point => {
      const display = point.display || {};
      const trend = trendOf(point);
      const yoy = trend.latest_yoy_pct;
      const gap = trend.official_vs_ais;
      const latest = trend.official_latest;
      const isStale = Boolean(display.is_stale);
      const severity = trendSeverity(yoy);
      return `<article class="shipping-chokepoint-card" data-chokepoint="${escapeHtml(point.id)}"
                       role="button" tabindex="0" aria-expanded="false">
        <div class="shipping-chokepoint-head">
          <div><span>${escapeHtml(point.name_en)}</span><h3>${escapeHtml(point.name_ko)}</h3></div>
          ${badge(isStale ? '기준일 경과' : '최근 신호', isStale ? 'neutral' : 'observed')}
        </div>
        ${bypassThreatensPoint(point) ? `<div style="margin:8px 0 2px">${badge('호르무즈 우회로 · 후티 봉쇄 위협 보도', 'estimated', '출처가 달린 수기 기록 기준. 상세에서 사건과 공식 경보를 확인')}</div>` : ''}
        ${gap?.status === 'ais_undercount_likely' ? `<div style="margin:8px 0 2px">${badge('AIS 미포착 가능성 큼', 'estimated', `${gap.period} 공식 추정은 전년 대비 ${signedPct(gap.official_yoy_pct, 1)}, AIS 포착은 ${signedPct(gap.ais_yoy_pct, 1)}`)}</div>` : ''}
        <strong class="shipping-change ${severity}"${TREND_SEVERITY_STYLE[severity] || ''}>${signedPct(yoy, 0)}</strong>
        <p>전년 대비 · ${escapeHtml(metricLabel(trend.metric_key || point.metricKey))} AIS 포착 · 최근 7일 vs 52주 전</p>
        ${definitionRows([
          ['최근 7일 vs 직전 28일', signedPct(point.metric.change_pct, 1)],
          ['최근 7일 추정 교역량', `${formatTonnes(point.metric.current_7d_mean_estimated_trade_tonnes)}/일`],
          ...(latest ? [[`공식 최신 · ${latest.publisher} ${latest.period}`, formatOfficialValue(latest.value, latest.unit)]] : []),
          ...(gap && finite(gap.ais_yoy_pct) ? [[`${gap.period} 전년 대비 · 공식 / AIS`, `${signedPct(gap.official_yoy_pct, 0)} / ${signedPct(gap.ais_yoy_pct, 0)}`]] : [])
        ])}
        <p class="shipping-note">기준일 ${formatDate(trend.latest_date || display.latest_date || point.live.latest_date)}${isStale ? ` · ${formatNumber(display.stale_days, 0)}일 경과` : ''}</p>
      </article>`;
    }).join('');

    const body = `
      <div class="shipping-callout info"><strong>관측 이상 신호:</strong> PortWatch가 <em>AIS로 포착한</em> 통항의 최근 7일을 52주 전 같은 7일과 비교합니다. 0% 위는 증가, 아래는 감소입니다. 위협 해역에서는 선박이 AIS를 꺼 실제보다 크게 줄어 보일 수 있어, 공식 추정이 있는 통로는 함께 보여줍니다.</div>
      ${worst ? `<div class="shipping-kpi-grid">
        ${kpi('최대 위축 통로', escapeHtml(worst.name_ko), `전년 대비 ${signedPct(trendOf(worst).latest_yoy_pct, 0)} · AIS 포착`, { featured: true })}
        ${best && trendOf(best).latest_yoy_pct > 0 ? kpi('최대 증가 통로', escapeHtml(best.name_ko), `전년 대비 ${signedPct(trendOf(best).latest_yoy_pct, 0)} · AIS 포착`) : kpi('증가 통로', '없음', '전년 대비 증가한 통로 없음')}
        ${kpi('모니터 대상', `${formatNumber(points.length)}개 통로`, showAll ? '전체 PortWatch 공개 신호' : '차단 시 우회·대기 영향 중심')}
      </div>` : ''}
      ${panel('LIVE SIGNAL', '통로별 전년 대비 추정 교역량 (7일 이동평균)', `
        <div class="shipping-chart-wrap tall"><canvas id="shipping-chokepoint-chart"></canvas></div>
        <p class="shipping-note">선은 AIS 포착 기준 전년 대비(%)입니다. ◆ 표시는 같은 해협의 EIA 공식 분기 추정치의 전년 대비이며, 분기 가운데 날짜에 찍었습니다. 범례를 눌러 통로를 켜고 끌 수 있습니다 — 호르무즈를 끄면 나머지 통로의 움직임이 크게 보입니다.</p>
        <div class="shipping-legend">
          <span><i style="background:#f87171"></i>위험 · 전년 대비 25% 이상 감소</span>
          <span><i style="background:#fbbf24"></i>주의 · 10–25% 감소</span>
          <span><i style="background:#34d399"></i>정상 범위</span>
          <span><i style="background:#38bdf8"></i>증가 · 5% 이상</span>
        </div>`,
        `<div class="shipping-panel-tools">
          ${popover('choke-def', '용어', '초크포인트 지표 읽는 법', `
            ${definitionRows([
              ['전년 대비', '최근 7일 평균 ÷ 52주 전 같은 요일 7일 평균 − 1 (AIS 포착 기준)'],
              ['최근 7일 vs 직전 28일', '단기 변화. 이미 붕괴한 기준선 안의 등락이라 전년 대비와 함께 봐야 함'],
              ['AIS 미포착 가능성 큼', '같은 분기 전년 대비로 AIS가 남긴 비율이 공식 추정이 남긴 비율의 절반 미만'],
              ['색 구간', '25% 이상 감소 위험 · 10–25% 주의 · 5% 이상 증가']
            ])}
            <p class="shipping-note">색 구간은 이 화면이 정한 표시 기준이며 PortWatch 등급이 아닙니다. 모든 값은 엔진이 계산한 스냅샷 값을 그대로 씁니다. 톤과 배럴을 서로 환산하지 않습니다.</p>`)}
          <button type="button" class="shipping-secondary-control" id="shipping-chokepoint-scope-toggle" aria-pressed="${showAll}">
            ${showAll ? '핵심 5개만 보기' : `전체 ${formatNumber(allPoints.length)}개 통로 보기`}
          </button>
          ${badge('PortWatch AIS 추정', 'estimated')}
        </div>`)}
      <div class="shipping-chokepoint-grid">${cards}</div>
      <div id="shipping-chokepoint-detail"></div>
      <p class="shipping-note">호르무즈는 탱커, 나머지 통로는 전체 추정 교역량을 대표 지표로 씁니다. 전년 대비는 AIS에 포착된 통항 기준이며 시나리오 봉쇄율과 같은 숫자가 아닙니다.</p>`;

    root.innerHTML = pageShell('shipping_chokepoints', body, data);

    root.querySelector('#shipping-chokepoint-scope-toggle')?.addEventListener('click', () => {
      renderChokepoints(data, root, !showAll);
    });

    const trended = points.filter(point => asArray(trendOf(point).dates).length);
    const labels = asArray(trendOf(trended[0] || {}).dates);
    const datasets = [];
    trended.forEach((point, index) => {
      const trend = trendOf(point);
      const color = TREND_COLORS[index % TREND_COLORS.length];
      const byDate = new Map(asArray(trend.dates).map((day, i) => [day, trend.yoy_pct[i]]));
      const name = `${point.name_ko}${trend.metric_key && trend.metric_key !== 'all' ? ` (AIS ${SHIP_TYPE_LABELS[trend.metric_key] || trend.metric_key})` : ''}`;
      datasets.push({ ...solidLine(name, labels.map(day => finite(byDate.get(day)) ? Number(byDate.get(day)) : null), color), borderWidth: 2 });
      const gap = trend.official_vs_ais;
      const quarter = gap && /^([1-4])Q(\d{2})$/.exec(gap.period || '');
      if (quarter) {
        const mid = `20${quarter[2]}-${String(Number(quarter[1]) * 3 - 1).padStart(2, '0')}-15`;
        const at = labels.indexOf(mid);
        if (at >= 0) {
          datasets.push({
            label: `${point.name_ko} EIA ${gap.period} 공식`, data: labels.map((_, i) => i === at ? gap.official_yoy_pct : null),
            borderColor: color, backgroundColor: color, showLine: false, pointStyle: 'rectRot', pointRadius: 7, pointHoverRadius: 9
          });
        }
      }
    });
    if (datasets.length) {
      const options = lineChartOptions(value => signedPct(value, 1), { formatTick: value => `${value > 0 ? '+' : ''}${formatNumber(value, 0)}%` });
      options.scales.y.beginAtZero = false;
      options.scales.y.grid = { color: ctx => ctx.tick?.value === 0 ? 'rgba(248, 250, 252, 0.45)' : GRID_LINE, lineWidth: ctx => ctx.tick?.value === 0 ? 1.5 : 1 };
      options.scales.x.ticks.callback = function (value) { return String(this.getLabelForValue(value)).slice(5); };
      // ◆ official points are explained in the note; keep the legend to lines.
      options.plugins.legend.labels.filter = item => !String(item.text).includes('공식');
      createChart(root, 'shipping-chokepoint-chart', { type: 'line', data: { labels, datasets }, options });
    }

    // Detail: location on the left third, daily series on the right two.
    const detail = root.querySelector('#shipping-chokepoint-detail');
    const cardEls = [...root.querySelectorAll('[data-chokepoint]')];
    let openId = null;

    const openDetail = async id => {
      openId = openId === id ? null : id;
      cardEls.forEach(card => {
        const on = card.dataset.chokepoint === openId;
        card.classList.toggle('is-active', on);
        card.setAttribute('aria-expanded', String(on));
      });
      if (!openId) { detail.innerHTML = ''; return; }

      const point = points.find(p => p.id === openId);
      const shortfallPct = point.shortfall === null ? null : point.shortfall * 100;
      const risk = point.risk_context || {};

      detail.innerHTML = `
        <div class="shipping-detail-grid">
          ${panel('LOCATION', point.name_ko, '<div id="shipping-minimap"><p class="shipping-empty">지도를 불러오는 중…</p></div>')}
          ${panel('OBSERVED TRADE BY TYPE', '선종별 추정 교역량', `
            ${definitionRows([
              ['직전 28일 기준선', `${formatTonnes(point.metric.prior_28d_mean_estimated_trade_tonnes)}/일`],
              ['최근 7일 평균', `${formatTonnes(point.metric.current_7d_mean_estimated_trade_tonnes)}/일`],
              // Signed change, not the floored shortfall: a rise inside an
              // already collapsed baseline must not read as "0%, 100% left".
              ['직전 28일 대비', finite(point.metric.change_pct)
                ? `${Number(point.metric.change_pct) > 0 ? '+' : ''}${formatPct(point.metric.change_pct, 1)}${shortfallPct > 0 ? ` (잔존 ${formatPct((point.remaining || 0) * 100, 0)})` : ''}`
                : '—'],
              ['52주 전 같은 7일 대비', (() => {
                const yearAgo = point.live?.metric_histories?.[point.metricKey]?.year_ago;
                return finite(yearAgo?.change_pct)
                  ? `${Number(yearAgo.change_pct) > 0 ? '+' : ''}${formatPct(yearAgo.change_pct, 1)} (${formatTonnes(yearAgo.year_ago_7d_mean)}/일 → ${formatTonnes(yearAgo.recent_7d_mean)}/일)`
                  : '비교 자료 없음';
              })()]
            ])}
            <p class="shipping-note"><strong>${escapeHtml(risk.primary_constraint_label_ko || '주요 제약')}:</strong> ${escapeHtml(risk.mechanism_ko || '제약 설명이 제공되지 않았습니다.')}</p>
            <p class="shipping-note">${escapeHtml(risk.scenario_interpretation_ko || '')}</p>
            ${renderObservedTypeComparison(point)}`,
            badge('PortWatch 추정', 'observed', '일별 값은 공개된 선종별 이력이 있을 때만 표시'))}
        </div>
        <div id="shipping-official-cargo"></div>
        <div id="shipping-inline-simulator"></div>`;

      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      renderMiniMap(detail.querySelector('#shipping-minimap'), point);
      bindObservedTypeComparison(detail, point);
      renderOfficialCargoInto(detail.querySelector('#shipping-official-cargo'), point);
      renderScenarioSimulatorInto(
        data,
        detail.querySelector('#shipping-inline-simulator'),
        point.id
      );
    };

    cardEls.forEach(card => {
      const run = () => openDetail(card.dataset.chokepoint);
      card.addEventListener('click', run);
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); run(); }
      });
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

  const renderRerouteReceivers = (receivers, scenarioId, horizonDays = 28) => {
    const isRerouteRelevantScenario = /^(suez|bab_el_mandeb)_/.test(scenarioId);
    if (!isRerouteRelevantScenario || !asArray(receivers).length) return '';

    return `<details class="shipping-reroute-details">
      <summary>
        <span>
          <small>ROUTE RECEIVER</small>
          <strong>우회 항로 처리 역량</strong>
        </span>
        <span class="shipping-reroute-summary-value">${formatDWT(asArray(receivers).reduce((sum, item) => sum + Number(item.additional_service_capacity_dwt || 0), 0))}</span>
      </summary>
      <div class="shipping-reroute-details-body">
      ${asArray(receivers).map(recv => `
        <div class="shipping-reroute-receiver">
          <div class="shipping-reroute-receiver-title">${escapeHtml(recv.name_ko || recv.id)}</div>
          <div class="shipping-metric-grid shipping-reroute-metrics">
            ${recv.rerouted_cargo_tonnes_horizon ? `
              <div>
                <div>우회 출항 화물 (28일 누계)</div>
                <strong>${formatTonnes(recv.rerouted_cargo_tonnes_horizon)}</strong>
              </div>` : ''}
            ${recv.rerouted_in_transit_cargo_tonnes_horizon ? `
              <div>
                <div>기간 말 우회 항해 중 화물</div>
                <strong>${formatTonnes(recv.rerouted_in_transit_cargo_tonnes_horizon)}</strong>
              </div>` : ''}
            ${recv.additional_service_capacity_dwt ? `
              <div>
                <div>우회로 추가 필요 서비스 선복</div>
                <strong>${formatDWT(recv.additional_service_capacity_dwt)}</strong>
              </div>` : ''}
          </div>
          <p class="shipping-note">우회 출항 화물은 분석기간에 대체 경로로 출발시킨 누계이며, 기간 말 우회 항해 중 화물은 그중 ${formatNumber(horizonDays, 0)}일째 아직 도착하지 않은 재고입니다. 두 값을 더하면 안 됩니다.</p>
          ${asArray(recv.ship_type_breakdown).length ? `
            <div class="shipping-reroute-breakdown">
              <div>선종별 우회 서비스 영향</div>
              ${table(
                [{ label: '선종', align: 'left' }, { label: '우회 출항', align: 'right' }, { label: '기간 말 항해중', align: 'right' }, { label: '추가 서비스 선복', align: 'right' }, { label: '배송가능 흐름', align: 'right' }],
                asArray(recv.ship_type_breakdown).map(st => `<tr>
                  <td><span class="shipping-color-dot" style="background:${SHIP_TYPE_COLORS[st.ship_type] || SHIP_TYPE_COLORS.other}"></span>${escapeHtml(SHIP_TYPE_LABELS[st.ship_type] || st.ship_type)}</td>
                  <td style="text-align:right;font-size:13px">${formatTonnes(st.rerouted_cargo_tonnes_horizon)}</td>
                  <td style="text-align:right;font-size:13px">${formatTonnes(st.rerouted_in_transit_cargo_tonnes_horizon)}</td>
                  <td style="text-align:right;font-size:13px">${formatDWT(st.additional_service_capacity_dwt)}${finite(st.additional_service_capacity_pct_of_baseline) ? `<br><small style="color:#64748b">기준 서비스 대비 +${formatPct(st.additional_service_capacity_pct_of_baseline, 1)}</small>` : ''}</td>
                  <td style="text-align:right;font-size:13px" class="${Number(st.weighted_traffic_change_pct) < 0 ? 'negative-text' : ''}">${finite(st.weighted_traffic_change_pct) ? formatPct(st.weighted_traffic_change_pct, 1) : '—'}</td>
                </tr>`).join('')
              )}
              <p class="shipping-note">컨테이너도 이 엔진에서는 항로 주기 변화에 따른 필요 서비스 선복을 DWT-equivalent로 계산합니다. TEU는 선박 크기·적재 단위라 추가 필요 선복을 단순 TEU로 바꾸지 않습니다. 컨테이너 행의 괄호는 해당 대표 정기선 서비스의 기준 필요 선복 대비 증가율입니다.</p>
            </div>` : ''}
          ${recv.status === 'modelled_reroute_receiver_not_observed_traffic' && recv.warning_ko ? `
            <div class="shipping-reroute-warning">
              <strong>주의:</strong> ${escapeHtml(recv.warning_ko)}<br>
              <small>이 수치는 대표 항로의 시나리오 모델 결과이며, 희망봉의 실제 AIS 통항량·물리적 처리능력·실시간 선복량 관측값이 아닙니다.</small>
            </div>` : ''}
        </div>
      `).join('')}
      </div>
    </details>`;
  };

  const scenarioKpis = summary => `<div class="shipping-kpi-grid scenario-kpis">
    ${kpi('추가 흡수 선복량', formatDWT(summary.operational_capacity_absorbed_dwt), '우회 + 대기', { key: 'absorbed' })}
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

  // Fetches the scenario grid on first use and caches it, then renders. The
  // grid file is the large, simulator-only artifact split out of the main
  // screen data (see GRID_URL above), so list screens never pay for it.
  const renderScenarioSimulatorInto = (data, mount, chokepointId = null) => {
    if (!mount) return;
    mount.innerHTML = '<p class="shipping-empty">시나리오 격자를 불러오는 중…</p>';
    loadScenarioGrid(data)
      .then(grid => renderScenarioSimulatorBody(data, grid, mount, chokepointId))
      .catch(error => {
        mount.innerHTML = `<p class="shipping-empty">시나리오 격자 데이터를 불러오지 못했습니다: ${escapeHtml(error.message)}</p>`;
      });
  };

  const renderScenarioSimulatorBody = (data, grid, mount, chokepointId) => {
    const baseScenarios = data.ui.baseScenarios.filter(item =>
      !chokepointId || item.chokepoint_id === chokepointId);
    const closureOptions = asArray(grid.closure_pct_options);
    const durationOptions = asArray(grid.duration_day_options);
    const labels = data.ui_delivery_contract?.views?.chokepoint_detail?.labels_ko || {};

    if (!baseScenarios.length || !asArray(grid.rows).length) {
      mount.innerHTML = '<p class="shipping-empty">이 통로에 연결된 시나리오 격자 데이터가 없습니다.</p>';
      return;
    }

    const initial = baseScenarios.find(item => item.id === 'hormuz_effective_80pct_28d') || baseScenarios[0];
    const initialClosure = closureOptions.includes(80) ? 80 : Math.round(Number(initial.closure_fraction || 0) * 100);
    const initialDuration = durationOptions.includes(Number(initial.duration_days))
      ? Number(initial.duration_days) : durationOptions.at(-1);

    mount.innerHTML = panel('SHOCK SIMULATOR', '봉쇄·통항제약 시뮬레이터', `
      <div class="shipping-callout warning"><strong>가정 기반 스트레스입니다.</strong> PortWatch 관측 신호와 물리 봉쇄율을 동일시하지 않습니다.</div>
        <div class="shipping-simulator-controls">
          <label>기준 시나리오
            <select id="shipping-scenario-preset" class="shipping-select">
              ${baseScenarios.map(item => `<option value="${escapeHtml(item.id)}"${item.id === initial.id ? ' selected' : ''}>${escapeHtml(item.name_ko || item.id)}</option>`).join('')}
            </select>
          </label>
          <label>${escapeHtml(labels.closure_pct || '실효 통행제약률')}
            <select id="shipping-closure-select" class="shipping-select">
              ${closureOptions.map(v => `<option value="${v}"${v === initialClosure ? ' selected' : ''}>${v}%</option>`).join('')}
            </select>
          </label>
          <label>${escapeHtml(labels.duration_days || '제약 지속일')}
            <select id="shipping-duration-select" class="shipping-select">
              ${durationOptions.map(v => `<option value="${v}"${v === initialDuration ? ' selected' : ''}>${v}일</option>`).join('')}
            </select>
          </label>
        </div>
        <div id="shipping-scenario-result"></div>`);

    const presetEl = mount.querySelector('#shipping-scenario-preset');
    const closureEl = mount.querySelector('#shipping-closure-select');
    const durationEl = mount.querySelector('#shipping-duration-select');
    const resultEl = mount.querySelector('#shipping-scenario-result');
    let scenarioChart = null;

    const update = () => {
      const row = asArray(grid.rows).find(item => item.base_scenario_id === presetEl.value
        && Number(item.closure_pct) === Number(closureEl.value)
        && Number(item.duration_days) === Number(durationEl.value));

      if (!row) {
        resultEl.innerHTML = '<p class="shipping-empty">선택한 조합의 사전 계산 결과가 없습니다.</p>';
        return;
      }
      if (scenarioChart) {
        scenarioChart.destroy();
        activeCharts = activeCharts.filter(chart => chart !== scenarioChart);
      }
      const breakdown = asArray(row.summary?.ship_type_breakdown);
      const lngSegments = asArray(row.summary?.cargo_segment_breakdown)
        .filter(item => item?.cargo_segment === 'lng');

      resultEl.innerHTML = `
        ${scenarioKpis(row.summary || {})}
        ${breakdown.length ? `
          <div class="shipping-chart-wrap" style="margin-top:18px"><canvas id="shipping-scenario-chart"></canvas></div>
          ${table(
            ['선종', { label: '영향 항로 배치 DWT', align: 'right' }, { label: '사용 불가 DWT', align: 'right' }, { label: '추가 흡수 / 세계 선대', align: 'right' }, { label: '28일 말 백로그', align: 'right' }, { label: '트래픽', align: 'right' }],
            breakdown.map(item => `<tr>
              <td><span class="shipping-color-dot" style="background:${SHIP_TYPE_COLORS[item.ship_type] || SHIP_TYPE_COLORS.other}"></span>${escapeHtml(SHIP_TYPE_LABELS[item.ship_type] || item.ship_type)}</td>
              <td style="text-align:right">${formatDWT(item.affected_allocated_dwt_with_reserve)}</td>
              <td style="text-align:right;font-weight:600">${formatDWT(item.commercially_unavailable_dwt)}<br><small style="color:#64748b">${formatPct(item.commercially_unavailable_pct_of_affected_allocated, 1)}</small></td>
              <td style="text-align:right">${formatPct(item.operational_capacity_absorbed_pct_of_relevant_global_type_fleet, 2)}</td>
              <td style="text-align:right">${formatTonnes(item.backlog_cargo_tonnes_horizon)}</td>
              <td style="text-align:right" class="negative-text">${formatPct(item.weighted_traffic_change_pct, 1)}</td>
            </tr>`).join('')
          )}` : '<p class="shipping-empty">이 조합에 영향받는 대표 선종이 없습니다.</p>'}
        ${lngSegments.length ? `<section class="shipping-lng-segment" aria-label="LNG 화물 세그먼트 영향">
          <div class="shipping-lng-segment-head">
            <div><span>CARGO SEGMENT</span><h3>LNG 운반선 서비스 영향</h3></div>
            <small>유조선 합계와 별도 표시</small>
          </div>
          ${lngSegments.map(item => `<div class="shipping-lng-segment-grid">
            <div><span>영향 항로 배치 DWT</span><strong>${formatDWT(item.affected_allocated_dwt_with_reserve)}</strong></div>
            <div><span>추가 흡수 선복량</span><strong>${formatDWT(item.operational_capacity_absorbed_dwt)}</strong></div>
            <div><span>기간 말 백로그</span><strong>${formatTonnes(item.backlog_cargo_tonnes_horizon)}</strong></div>
            <div><span>배송가능 흐름 변화</span><strong class="negative-text">${formatPct(item.weighted_traffic_change_pct, 1)}</strong></div>
          </div>
          <p class="shipping-note">LNG는 화물·서비스 세그먼트입니다. 무료 공개자료에는 LNG 전용 세계 선대 DWT가 없어, 탱커 세계 선대 비중이나 LNG 세계 선대 비율을 표시하지 않습니다.</p>
        </section>`).join('')}` : ''}
        <p class="shipping-note">${escapeHtml(labels.backlog_cargo_tonnes_horizon || '분석기간 말 미운송 화물')}입니다. 모든 값은 Python 엔진이 사전 계산한 ${formatNumber(row.horizon_days, 0)}일 격자 결과입니다.</p>
        ${renderRerouteReceivers(row.summary?.reroute_receivers, row.base_scenario_id, row.horizon_days)}`;

      if (breakdown.length) {
        scenarioChart = createChart(resultEl, 'shipping-scenario-chart', {
          type: 'bar',
          data: {
            labels: breakdown.map(item => SHIP_TYPE_LABELS[item.ship_type] || item.ship_type),
            datasets: [
              {
                label: '상업적 사용 가능 DWT',
                data: breakdown.map(item => (item.commercially_available_dwt || 0) / 1e6),
                backgroundColor: '#38bdf8',
                stack: 'availability'
              },
              {
                label: '상업적 사용 불가 DWT',
                data: breakdown.map(item => (item.commercially_unavailable_dwt || 0) / 1e6),
                backgroundColor: '#f87171',
                stack: 'availability'
              }
            ]
          },
          options: chartOptions({ unit: 'M DWT', stacked: true, legend: true })
        });
      }

      bindScenarioKpis(resultEl);
    };

    [presetEl, closureEl, durationEl].forEach(el => el?.addEventListener('change', update));
    update();
  };

  const renderScenarios = (data, root) => {
    root.innerHTML = pageShell(
      'shipping_scenarios',
      '<div id="shipping-standalone-simulator"></div>',
      data
    );
    renderScenarioSimulatorInto(data, root.querySelector('#shipping-standalone-simulator'));
  };

  const renderEnvironmentInto = (data, mount) => {
    if (!mount) return;
    const env = data.ui.environment;
    const allScenarios = asArray(env?.scenarios);
    const pathways = asArray(env?.pathways);

    if (!allScenarios.length || !pathways.length) {
      mount.innerHTML = '<p class="shipping-empty">환경규제 시나리오 데이터가 없습니다.</p>';
      return;
    }

    let activePathwayId = pathways.find(path => path.id === 'imo_adopted')?.id || pathways[0].id;
    let environmentCharts = [];
    const byPathway = id => allScenarios
      .filter(scenario => scenario.pathway_id === id)
      .sort((a, b) => Number(a.year) - Number(b.year));

    const draw = () => {
      environmentCharts.forEach(chart => chart.destroy());
      activeCharts = activeCharts.filter(chart => !environmentCharts.includes(chart));
      environmentCharts = [];
      const scenarios = byPathway(activePathwayId);
      const first = scenarios[0];
      const last = scenarios.at(-1);
      if (!first || !last) {
        mount.innerHTML = '<p class="shipping-empty">선택한 환경 경로의 산출값이 없습니다.</p>';
        return;
      }
      const latestBreakdown = asArray(last.ship_type_breakdown);
      const pathwayCards = pathways.map(path => {
        const rows = byPathway(path.id);
        const latest = rows.at(-1);
        const adopted = path.policy_status === 'official_adopted_path';
        return `<article class="shipping-pathway${path.id === activePathwayId ? ' is-active' : ''}"
          data-pathway="${escapeHtml(path.id)}" role="button" tabindex="0" aria-pressed="${path.id === activePathwayId}">
          <div class="shipping-pathway-head">
            <strong>${escapeHtml(path.name_ko || path.id)}</strong>
            ${badge(adopted ? '채택 경로' : '반사실 민감도', adopted ? 'observed' : 'neutral')}
          </div>
          <span class="shipping-pathway-sub">${escapeHtml(path.description_ko || '')}</span>
          <p class="shipping-pathway-value">${latest ? formatDWT(latest.effective_dwt_loss) : '—'}</p>
          <small>${latest ? `${latest.year}년 유효 DWT 손실` : '값 없음'}</small>
        </article>`;
      }).join('');

      mount.innerHTML = `
        <div class="shipping-callout warning"><strong>물리적 선대 감소가 아닙니다.</strong> ${escapeHtml(env.methodology_ko || '')}</div>
        ${panel('ENVIRONMENT PATHWAYS', '환경 규제 경로 비교', `<div class="shipping-pathway-grid">${pathwayCards}</div>`)}
        <div class="shipping-kpi-grid">
          ${kpi(`${last.year}년 유효 DWT 손실`, formatDWT(last.effective_dwt_loss), escapeHtml(last.pathway_name_ko || activePathwayId))}
          ${kpi('유효 용량 유지율', formatPct(last.effective_capacity_retention_rate * 100, 1), '대표 항로 모델 기준')}
          ${kpi('같은 서비스 추가 필요', formatDWT(last.additional_required_vs_baseline_dwt), '기준 서비스 유지 가정')}
          ${kpi('CII 감축 경로', formatPct(last.regulatory_inputs?.cii_reduction_vs_2019_pct, 2), `${last.year}년 · 2019년 대비`)}
        </div>
        <div class="shipping-grid two-columns">
          ${panel('CAPACITY OVER TIME', `${escapeHtml(last.pathway_name_ko || activePathwayId)} · 연도별 유효 선복량`, '<div class="shipping-chart-wrap"><canvas id="shipping-environment-chart"></canvas></div><p class="shipping-note">파란색은 서비스 가능한 DWT, 주황색은 감속·개조·퇴출 가정으로 잠식되는 서비스 상당 DWT입니다.</p>')}
          ${panel('SHIP TYPE IMPACT', `${last.year}년 선종별 유효 DWT 손실`, '<div class="shipping-chart-wrap"><canvas id="shipping-env-shiptype-chart"></canvas></div><p class="shipping-note">컨테이너·벌크·탱커 대표 항로의 엔진 합계이며 세계 선대 전체 예측이 아닙니다.</p>')}
        </div>
        ${panel('REGULATORY INPUTS', '연도별 규제 입력과 선복량 영향', table(
          ['연도', { label: 'CII 감축', align: 'right' }, { label: 'FuelEU 감축', align: 'right' }, { label: '유효 DWT 손실', align: 'right' }, { label: '같은 서비스 필요 DWT', align: 'right' }, '정책 상태'],
          scenarios.map(scenario => `<tr>
            <td>${formatNumber(scenario.year)}</td>
            <td style="text-align:right">${formatPct(scenario.regulatory_inputs?.cii_reduction_vs_2019_pct, 3)}</td>
            <td style="text-align:right">${formatPct(scenario.regulatory_inputs?.fueleu_ghg_intensity_reduction_vs_2020_pct, 1)}</td>
            <td style="text-align:right;font-weight:600;color:#fcd34d">${formatDWT(scenario.effective_dwt_loss)}</td>
            <td style="text-align:right">${formatDWT(scenario.same_service_required_dwt)}</td>
            <td>${badge(scenario.pathway_policy_status === 'official_adopted_path' ? '채택' : '반사실', scenario.pathway_policy_status === 'official_adopted_path' ? 'observed' : 'neutral')}</td>
          </tr>`).join('')
        ))}
        <p class="shipping-note">범위: ${escapeHtml(last.scope || '')}</p>
        ${asArray(env.warnings_ko).length ? panel('CAVEATS', '해석 시 주의', `<ul class="shipping-note" style="margin:0;padding-left:1.1rem;line-height:1.9">${env.warnings_ko.map(warning => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>`) : ''}`;

      const capacityChart = createChart(mount, 'shipping-environment-chart', {
        type: 'bar',
        data: {
          labels: scenarios.map(scenario => String(scenario.year)),
          datasets: [
            { label: '유효 서비스 DWT', data: scenarios.map(scenario => scenario.effective_service_capacity_dwt / 1e6), backgroundColor: '#38bdf8', stack: 'dwt' },
            { label: '유효 DWT 손실', data: scenarios.map(scenario => scenario.effective_dwt_loss / 1e6), backgroundColor: '#fbbf24', stack: 'dwt' }
          ]
        },
        options: chartOptions({ unit: 'M DWT', stacked: true, legend: true })
      });
      const shipTypeChart = createChart(mount, 'shipping-env-shiptype-chart', {
        type: 'bar',
        data: {
          labels: latestBreakdown.map(item => SHIP_TYPE_LABELS[item.ship_type] || item.ship_type),
          datasets: [{
            label: '유효 DWT 손실',
            data: latestBreakdown.map(item => item.effective_dwt_loss / 1e6),
            backgroundColor: latestBreakdown.map(item => SHIP_TYPE_COLORS[item.ship_type] || SHIP_TYPE_COLORS.other),
            borderRadius: 5
          }]
        },
        options: chartOptions({ unit: 'M DWT' })
      });
      environmentCharts = [capacityChart, shipTypeChart].filter(Boolean);

      mount.querySelectorAll('[data-pathway]').forEach(card => {
        const run = () => {
          activePathwayId = card.dataset.pathway;
          draw();
        };
        card.addEventListener('click', run);
        card.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); run(); }
        });
      });
    };
    draw();
  };

  const renderEnvironment = (data, root) => {
    root.innerHTML = pageShell('shipping_environment', '<div id="shipping-environment-standalone"></div>', data);
    renderEnvironmentInto(data, root.querySelector('#shipping-environment-standalone'));
  };

  // --------------------------------------------------------------- lifecycle

  const bindTabs = (root) => {
    root.querySelectorAll('[data-shipping-view]').forEach(button => {
      if (button.dataset.shippingViewBound === 'true') return;
      button.dataset.shippingViewBound = 'true';
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

  // loadData is exposed so the home 「오늘 신호」 chokepoint tile can read the
  // same snapshot without fetching 1.1 MB a second time -- the promise is
  // memoised here, so whichever screen asks first warms it for the other.
  window.ShippingDashboard = { render, unmount, loadData: loadShippingData };
})();
