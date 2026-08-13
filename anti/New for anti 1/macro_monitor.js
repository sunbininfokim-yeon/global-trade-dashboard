/* Macro Monitor prototype — map → country overlay → category chips → history chart.
   Standalone: does not touch app.js / style.css / index.html. */

(() => {
  const DATA_URL = "public/data/macro_monitor_v1.json";
  const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
  // Minimal topo→geo without d3-geo dependency for projection math we implement ourselves.

  const state = {
    data: null,
    geo: null,
    features: [],
    selected: null,
    category: null,
    chartSeries: null,
    window: "5y",
    map: {
      scale: 1,
      tx: 0,
      ty: 0,
      dragging: false,
      lastX: 0,
      lastY: 0,
      hoverIso3: null,
    },
  };

  const el = {
    canvas: document.getElementById("map"),
    stageHint: document.getElementById("stageHint"),
    countryStage: document.getElementById("countryStage"),
    backBtn: document.getElementById("backBtn"),
    countryName: document.getElementById("countryName"),
    kitBadge: document.getElementById("kitBadge"),
    countryAsof: document.getElementById("countryAsof"),
    catTabs: document.getElementById("catTabs"),
    chipCloud: document.getElementById("chipCloud"),
    limitsBox: document.getElementById("limitsBox"),
    limitsBody: document.getElementById("limitsBody"),
    chartDrawer: document.getElementById("chartDrawer"),
    chartTitle: document.getElementById("chartTitle"),
    chartMeta: document.getElementById("chartMeta"),
    chartNote: document.getElementById("chartNote"),
    chartCanvas: document.getElementById("chartCanvas"),
    closeChart: document.getElementById("closeChart"),
    windowToggle: document.getElementById("windowToggle"),
    footSource: document.getElementById("footSource"),
  };

  const ctx = el.canvas.getContext("2d");

  // --- tiny topojson decode (countries-110m arcs) ---
  function decodeArcs(topology) {
    const { arcs, transform } = topology;
    const scale = transform?.scale || [1, 1];
    const translate = transform?.translate || [0, 0];
    return arcs.map((arc) => {
      const out = [];
      let x = 0, y = 0;
      for (const p of arc) {
        x += p[0];
        y += p[1];
        out.push([x * scale[0] + translate[0], y * scale[1] + translate[1]]);
      }
      return out;
    });
  }

  function mergeArc(decoded, i) {
    return i < 0 ? decoded[~i].slice().reverse() : decoded[i];
  }

  function geometryToPolygons(geom, decoded) {
    const polys = [];
    function ring(indexes) {
      const coords = [];
      for (const i of indexes) {
        const part = mergeArc(decoded, i);
        // skip first of subsequent to avoid dup vertex
        for (let k = coords.length ? 1 : 0; k < part.length; k++) coords.push(part[k]);
      }
      return coords;
    }
    if (geom.type === "Polygon") {
      polys.push(geom.arcs.map(ring));
    } else if (geom.type === "MultiPolygon") {
      for (const poly of geom.arcs) polys.push(poly.map(ring));
    }
    return polys;
  }

  function project(lon, lat, w, h, scale, tx, ty) {
    // equirectangular centered
    const x = ((lon + 180) / 360) * w;
    const y = ((90 - lat) / 180) * h;
    const cx = w / 2, cy = h / 2;
    return [(x - cx) * scale + cx + tx, (y - cy) * scale + cy + ty];
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = window.innerWidth;
    const h = window.innerHeight;
    el.canvas.width = Math.floor(w * dpr);
    el.canvas.height = Math.floor(h * dpr);
    el.canvas.style.width = w + "px";
    el.canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawMap();
  }

  function iso3FromFeature(f) {
    // world-atlas countries use numeric id; map via properties if present, else name match
    const name = f.properties?.name;
    if (!name || !state.data) return null;
    const hit = state.data.countries_index.find((c) => {
      if (c.name_en === name) return true;
      return (c.aliases || []).includes(name);
    });
    return hit?.iso3 || null;
  }

  function drawMap() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const { scale, tx, ty, hoverIso3 } = state.map;
    const selectedIso = state.selected?.iso3;

    ctx.clearRect(0, 0, w, h);
    // sea
    const g = ctx.createRadialGradient(w * 0.5, h * 0.45, 40, w * 0.5, h * 0.5, Math.max(w, h) * 0.7);
    g.addColorStop(0, "#0c1c28");
    g.addColorStop(1, "#071018");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    if (!state.features.length) return;

    for (const f of state.features) {
      const iso3 = f._iso3;
      const active = iso3 && iso3 === selectedIso;
      const hover = iso3 && iso3 === hoverIso3;
      const tracked = !!iso3;

      ctx.beginPath();
      for (const poly of f._polys) {
        for (let r = 0; r < poly.length; r++) {
          const ring = poly[r];
          for (let i = 0; i < ring.length; i++) {
            const [lon, lat] = ring[i];
            const [x, y] = project(lon, lat, w, h, scale, tx, ty);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.closePath();
        }
      }
      if (active) {
        ctx.fillStyle = "rgba(62, 207, 191, 0.55)";
        ctx.strokeStyle = "rgba(62, 207, 191, 0.95)";
        ctx.lineWidth = 1.4;
      } else if (hover && tracked) {
        ctx.fillStyle = "rgba(42, 74, 88, 0.95)";
        ctx.strokeStyle = "rgba(62, 207, 191, 0.55)";
        ctx.lineWidth = 1;
      } else if (tracked) {
        ctx.fillStyle = "rgba(32, 58, 70, 0.92)";
        ctx.strokeStyle = "rgba(232, 238, 242, 0.18)";
        ctx.lineWidth = 0.6;
      } else {
        ctx.fillStyle = "rgba(20, 36, 44, 0.75)";
        ctx.strokeStyle = "rgba(232, 238, 242, 0.08)";
        ctx.lineWidth = 0.4;
      }
      ctx.fill("evenodd");
      ctx.stroke();
    }
  }

  function hitTest(mx, my) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const { scale, tx, ty } = state.map;
    // reverse project approx → lon/lat then point-in-polygon would be better;
    // for demo: scan tracked countries with bbox + winding on projected rings
    for (let i = state.features.length - 1; i >= 0; i--) {
      const f = state.features[i];
      if (!f._iso3) continue;
      for (const poly of f._polys) {
        const outer = poly[0];
        if (!outer || outer.length < 3) continue;
        let inside = false;
        for (let j = 0, k = outer.length - 1; j < outer.length; k = j++) {
          const [x1, y1] = project(outer[j][0], outer[j][1], w, h, scale, tx, ty);
          const [x2, y2] = project(outer[k][0], outer[k][1], w, h, scale, tx, ty);
          if (((y1 > my) !== (y2 > my)) && (mx < (x2 - x1) * (my - y1) / (y2 - y1 + 1e-12) + x1)) {
            inside = !inside;
          }
        }
        if (inside) return f._iso3;
      }
    }
    return null;
  }

  function openCountry(iso3) {
    const pack = state.data.countries.find((c) => c.iso3 === iso3);
    if (!pack) return;
    state.selected = pack;
    state.category = pack.active_categories[0];
    state.chartSeries = null;
    el.chartDrawer.hidden = true;
    el.countryStage.hidden = false;
    el.countryName.textContent = pack.name_ko;
    el.kitBadge.textContent = pack.benchmark
      ? "BENCHMARK"
      : pack.featured
        ? "FEATURED"
        : pack.kit.toUpperCase();
    el.countryAsof.textContent = `asof ${pack.asof} · ${pack.indicators.length} indicators`;
    el.stageHint.textContent =
      pack.purpose_ko ||
      (pack.benchmark
        ? "미국 = 글로벌 매크로 벤치마크 · 칩을 눌러 5·10년 차트"
        : pack.featured
          ? "일본 = BOJ/YCC 특화 키트 · 칩을 눌러 5·10년 차트"
          : "얇은 국가 키트 · 미국·일본을 열면 풀 키트");
    renderTabs();
    renderChips();
    renderLimits(pack);
    drawMap();
  }

  function closeCountry() {
    state.selected = null;
    state.category = null;
    state.chartSeries = null;
    el.countryStage.hidden = true;
    el.chartDrawer.hidden = true;
    el.stageHint.textContent = "국가를 클릭하세요 · US·JP·UK·CN·EU·RU·HK·SG·ZA·IN·KR·CA·AU·CH·BR·VN·KZ·TW = 풀 키트";
    drawMap();
  }

  function renderTabs() {
    const pack = state.selected;
    const labels = Object.fromEntries(
      (state.data.ui.category_tabs || []).map((c) => [c.id, c.label_ko])
    );
    el.catTabs.innerHTML = "";
    for (const id of pack.active_categories) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = labels[id] || id;
      btn.className = id === state.category ? "active" : "";
      btn.addEventListener("click", () => {
        state.category = id;
        renderTabs();
        renderChips();
      });
      el.catTabs.appendChild(btn);
    }
  }

  function renderChips() {
    const pack = state.selected;
    const chips = pack.categories[state.category] || [];
    el.chipCloud.innerHTML = "";
    for (const c of chips) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip";
      const d1 = c.change_1m_pct;
      const deltaCls = d1 == null ? "" : d1 >= 0 ? "up" : "down";
      const deltaTxt = d1 == null ? "" : `1M ${d1 >= 0 ? "+" : ""}${d1.toFixed(1)}%`;
      btn.innerHTML = `<span class="lbl">${c.label_ko}</span><span class="val">${c.display}</span><span class="delta ${deltaCls}">${deltaTxt}</span>`;
      btn.addEventListener("click", () => openChart(c.id));
      el.chipCloud.appendChild(btn);
    }
  }

  function renderLimits(pack) {
    const lim = pack?.limitations;
    if (!lim?.items?.length) {
      el.limitsBox.hidden = true;
      return;
    }
    el.limitsBox.hidden = false;
    const summary = el.limitsBox.querySelector("summary");
    if (summary) summary.textContent = lim.title_ko || "지표 추론의 한계";
    el.limitsBody.innerHTML = lim.items
      .map(
        (it) =>
          `<div class="lim-item"><strong>${it.title_ko}</strong>${it.body_ko}</div>`
      )
      .join("");
  }

  function openChart(seriesId) {
    const ind = state.selected.indicators.find((i) => i.id === seriesId);
    if (!ind) return;
    state.chartSeries = ind;
    // prefer available window
    if (!ind.history[state.window]) {
      state.window = Object.keys(ind.history)[0];
    }
    el.chartDrawer.hidden = false;
    el.chartTitle.textContent = `${ind.label_ko}  ${ind.display}`;
    el.chartMeta.textContent = `${state.selected.name_ko} · ${ind.asof} · ${ind.source}`;
    el.chartNote.textContent = ind.note_ko || "";
    [...el.windowToggle.querySelectorAll("button")].forEach((b) => {
      const win = b.dataset.window;
      b.disabled = !ind.history[win];
      b.classList.toggle("active", win === state.window);
    });
    drawChart();
  }

  function drawChart() {
    const ind = state.chartSeries;
    if (!ind) return;
    const hist = ind.history[state.window];
    if (!hist) return;
    const canvas = el.chartCanvas;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssW = canvas.clientWidth || 480;
    const cssH = 220;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    const c = canvas.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, cssW, cssH);

    const pad = { t: 12, r: 12, b: 28, l: 44 };
    const vals = hist.values;
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;
    const n = vals.length;

    // grid
    c.strokeStyle = "rgba(232,238,242,0.08)";
    c.lineWidth = 1;
    for (let i = 0; i < 4; i++) {
      const y = pad.t + ((cssH - pad.t - pad.b) * i) / 3;
      c.beginPath();
      c.moveTo(pad.l, y);
      c.lineTo(cssW - pad.r, y);
      c.stroke();
    }

    // line
    c.beginPath();
    for (let i = 0; i < n; i++) {
      const x = pad.l + ((cssW - pad.l - pad.r) * i) / Math.max(n - 1, 1);
      const y = pad.t + (cssH - pad.t - pad.b) * (1 - (vals[i] - min) / span);
      if (i === 0) c.moveTo(x, y);
      else c.lineTo(x, y);
    }
    c.strokeStyle = "#3ecfbf";
    c.lineWidth = 2;
    c.stroke();

    // end dot
    const xN = pad.l + (cssW - pad.l - pad.r);
    const yN = pad.t + (cssH - pad.t - pad.b) * (1 - (vals[n - 1] - min) / span);
    c.fillStyle = "#3ecfbf";
    c.beginPath();
    c.arc(xN, yN, 3.2, 0, Math.PI * 2);
    c.fill();

    // labels
    c.fillStyle = "#8fa3b0";
    c.font = "11px IBM Plex Mono, monospace";
    c.fillText(String(max.toFixed(2)), 4, pad.t + 8);
    c.fillText(String(min.toFixed(2)), 4, cssH - pad.b);
    c.fillText(hist.dates[0]?.slice(0, 7) || "", pad.l, cssH - 8);
    c.fillText(hist.dates[n - 1]?.slice(0, 7) || "", cssW - pad.r - 52, cssH - 8);
  }

  // events
  el.backBtn.addEventListener("click", closeCountry);
  el.closeChart.addEventListener("click", () => {
    el.chartDrawer.hidden = true;
    state.chartSeries = null;
  });
  el.windowToggle.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-window]");
    if (!b || b.disabled) return;
    state.window = b.dataset.window;
    [...el.windowToggle.querySelectorAll("button")].forEach((x) =>
      x.classList.toggle("active", x === b)
    );
    if (state.chartSeries) {
      openChart(state.chartSeries.id);
    }
  });

  el.canvas.addEventListener("pointerdown", (e) => {
    state.map.dragging = true;
    state.map.moved = false;
    state.map.downX = e.clientX;
    state.map.downY = e.clientY;
    state.map.lastX = e.clientX;
    state.map.lastY = e.clientY;
    el.canvas.setPointerCapture(e.pointerId);
  });
  el.canvas.addEventListener("pointermove", (e) => {
    if (state.map.dragging) {
      const dx = e.clientX - state.map.lastX;
      const dy = e.clientY - state.map.lastY;
      if (Math.hypot(e.clientX - state.map.downX, e.clientY - state.map.downY) > 4) {
        state.map.moved = true;
      }
      state.map.tx += dx;
      state.map.ty += dy;
      state.map.lastX = e.clientX;
      state.map.lastY = e.clientY;
      drawMap();
      return;
    }
    const iso = hitTest(e.clientX, e.clientY);
    if (iso !== state.map.hoverIso3) {
      state.map.hoverIso3 = iso;
      drawMap();
    }
  });
  el.canvas.addEventListener("pointerup", (e) => {
    const wasMoved = state.map.moved;
    state.map.dragging = false;
    if (wasMoved) return;
    const iso = hitTest(e.clientX, e.clientY);
    if (iso) openCountry(iso);
  });
  el.canvas.addEventListener("pointerleave", () => {
    state.map.dragging = false;
    state.map.hoverIso3 = null;
    drawMap();
  });
  el.canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      state.map.scale = Math.min(4, Math.max(0.7, state.map.scale * factor));
      drawMap();
    },
    { passive: false }
  );

  window.addEventListener("resize", resize);

  async function boot() {
    const [data, topo] = await Promise.all([
      fetch(DATA_URL).then((r) => {
        if (!r.ok) throw new Error("macro_monitor_v1.json missing — run build_macro_monitor.py");
        return r.json();
      }),
      fetch(GEO_URL).then((r) => r.json()),
    ]);
    state.data = data;
    el.footSource.textContent = `${data.source.kind} · ${data.generated_at}`;

    const decoded = decodeArcs(topo);
    const obj = topo.objects.countries;
    state.features = obj.geometries.map((geom) => {
      const props = geom.properties || {};
      const f = { properties: props, _polys: geometryToPolygons(geom, decoded) };
      f._iso3 = iso3FromFeature(f);
      return f;
    });

    // render limitations default text in data for USA path
    resize();
  }

  boot().catch((err) => {
    el.stageHint.textContent = String(err.message || err);
    console.error(err);
  });
})();
