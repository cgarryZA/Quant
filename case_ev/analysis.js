// analysis.js
import {
  configureCatalogPaths,
  loadCaseData,
  getVariantSeries,
  WEARS as LOADER_WEARS,
  ST_FLAGS as LOADER_ST_FLAGS,
  getCasePriceSeries as loaderCasePriceSeries,
} from "./data_loader.js";

// Modules (each exposes: compute(providers, SETTINGS) -> { title, metrics?, series?, notes? })
import { compute as coreStatsCompute } from "./analysis/core_stats.js";
import { compute as efficiencyCompute } from "./analysis/efficiency.js";
import { compute as volatilityCompute } from "./analysis/volatility.js";
import { compute as crossSectionCompute } from "./analysis/cross_section.js";
import { compute as liquidityCompute } from "./analysis/liquidity.js";
import { compute as signalsCompute } from "./analysis/signals.js";

document.addEventListener("DOMContentLoaded", () => {
  const SETTINGS = { timescale: "3M", interval: "1d" };
  let CASE_NAME = window.currentCaseName || "Chroma 2";
  configureCatalogPaths({ root: "./../data/catalogues" });

  const ST_PROB = 0.1;
  const DEFAULT_FLOAT_RANGE = { fmin: 0.06, fmax: 0.8 };
  const WEAR_BUCKETS = [
    { wear: "FN", range: [0.0, 0.07] },
    { wear: "MW", range: [0.07, 0.15] },
    { wear: "FT", range: [0.15, 0.38] },
    { wear: "WW", range: [0.38, 0.45] },
    { wear: "BS", range: [0.45, 1.0] },
  ];
  const WEARS = LOADER_WEARS;       // ["FN","MW","FT","WW","BS"]
  const ST_FLAGS = LOADER_ST_FLAGS; // [true,false]

  // ---- Container ----
  const card = document.getElementById("analysis-card");
  if (!card) return;
  card.innerHTML = `<h3 style="margin-bottom:12px;">Quant Analysis</h3>`;

  // ---- Tabs ----
  const tabs = [
    { id: "core",        title: "Core Stats",      compute: coreStatsCompute },
    { id: "efficiency",  title: "Efficiency",      compute: efficiencyCompute },
    { id: "vol",         title: "Volatility",      compute: volatilityCompute },
    { id: "xsec",        title: "Cross-Section",   compute: crossSectionCompute },
    { id: "liquidity",   title: "Liquidity",       compute: liquidityCompute },
    { id: "signals",     title: "Signals",         compute: signalsCompute },
  ];

  const nav = document.createElement("div");
  nav.style.display = "flex";
  nav.style.gap = "6px";
  nav.style.marginBottom = "12px";

  const panels = document.createElement("div");
  panels.style.display = "block";

  const state = { active: tabs[0].id, cache: {} };

  tabs.forEach(t => {
    const btn = document.createElement("button");
    btn.textContent = t.title;
    styleTab(btn, t.id === state.active);
    btn.addEventListener("click", () => {
      state.active = t.id;
      [...nav.children].forEach(b => styleTab(b, b.textContent === t.title));
      render();
    });
    nav.appendChild(btn);
  });

  card.appendChild(nav);
  card.appendChild(panels);

  // ---- React to global changes sent by case_ev.js ----
  window.addEventListener("case-settings-changed", (e) => {
    const d = e?.detail || {};
    if (d.timescale) SETTINGS.timescale = d.timescale;
    if (d.interval)  SETTINGS.interval  = d.interval;
    state.cache = {};
    render();
  });
  window.addEventListener("case-selected", (e) => {
    CASE_NAME = (e?.detail?.caseName) || CASE_NAME;
    state.cache = {};
    render();
  });

  render();

  // =========================
  // Orchestration / Renderer
  // =========================
  async function render() {
    panels.innerHTML = `<div style="opacity:.8;">Computing…</div>`;

    const n = choosePointCount(SETTINGS) * 2;
    const { items } = await loadCaseData(CASE_NAME, { n, settings: SETTINGS });

    const ev = buildEV(items, n, SETTINGS);
    const price = loaderCasePriceSeries({ n, settings: SETTINGS, caseName: CASE_NAME });

    const providers = {
      getEV: () => ev,
      getPrice: () => price,
      getAligned: () => alignXY(ev, price),
      getSettings: () => ({ ...SETTINGS }),
      getTimes: () => ev.map(p => p.x),
      getCaseName: () => CASE_NAME,
    };

    const mod = tabs.find(t => t.id === state.active);
    let result = state.cache[mod.id];
    if (!result) {
      result = await mod.compute(providers, SETTINGS);
      state.cache[mod.id] = result;
    }

    panels.innerHTML = "";
    const { title, metrics, series, notes } = result || {};
    const top = document.createElement("div");
    if (title) {
      const h = document.createElement("h4");
      h.textContent = `${title} — ${CASE_NAME}`;
      h.style.margin = "0 0 10px 0";
      top.appendChild(h);
    }
    if (metrics) top.appendChild(renderMetrics(metrics));
    panels.appendChild(top);

    if (Array.isArray(series)) {
      series.forEach(s => panels.appendChild(renderChart(s)));
    }
    if (notes) {
      const p = document.createElement("p");
      p.style.opacity = "0.85";
      p.style.marginTop = "8px";
      p.textContent = notes;
      panels.appendChild(p);
    }
  }

  // =========================
  // EV Builder
  // =========================
  function buildEV(items, n, settings) {
    const RARITY_TO_PROB = {
      "Mil-Spec Grade": 0.7992,
      Restricted: 0.1598,
      Classified: 0.032,
      Covert: 0.0064,
      "Exceedingly Rare": 0.0026,
    };
    const skinsWithRarity = items.map(name => ({ Name: name, Rarity: "Restricted" }));

    function computeWearProbabilities(fmin, fmax) {
      const len = Math.max(0, fmax - fmin);
      const PRIORS = { FN: 0.0135, MW: 0.108, FT: 0.311, WW: 0.095, BS: 0.473 };
      if (len <= 0) return PRIORS;

      const overlap = (a0, a1, b0, b1) => Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));
      let sum = 0;
      const raw = {};
      for (const b of WEAR_BUCKETS) {
        const [r0, r1] = b.range;
        const v = overlap(fmin, fmax, r0, r1);
        raw[b.wear] = v;
        sum += v;
      }
      if (sum <= 0) return PRIORS;
      const probs = {};
      for (const w of WEARS) probs[w] = raw[w] / sum;
      return probs;
    }

    const ev = new Array(n).fill(0).map((_, i) => ({ x: i / (n - 1), y: 0 }));
    const fr = DEFAULT_FLOAT_RANGE;
    const wearProbs = computeWearProbabilities(fr.fmin, fr.fmax);

    for (const skin of skinsWithRarity) {
      const name = skin.Name;
      const pSkin = RARITY_TO_PROB[skin.Rarity] ?? 0;
      if (pSkin <= 0) continue;

      const avg = new Array(n).fill(0).map((_, i) => ({ x: i / (n - 1), y: 0 }));
      let gridFrom = null;

      for (const wear of WEARS) {
        const pw = wearProbs[wear] ?? 0;
        for (const st of ST_FLAGS) {
          const pst = st ? ST_PROB : 1 - ST_PROB;
          const weight = pw * pst;
          const s = getVariantSeries({ skin: name, wear, st }) || avg;
          if (!gridFrom) gridFrom = s;
          for (let i = 0; i < Math.min(n, s.length); i++) {
            avg[i].x = gridFrom[i].x;
            avg[i].y += weight * s[i].y;
          }
        }
      }
      for (let i = 0; i < n; i++) ev[i].y += pSkin * avg[i].y;
    }
    return smooth(ev, 2);
  }

  // =========================
  // Render helpers
  // =========================
  function renderMetrics(metrics) {
    const wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gridTemplateColumns = "repeat(auto-fit,minmax(160px,1fr))";
    wrap.style.gap = "8px";
    Object.entries(metrics).forEach(([k, v]) => {
      const b = document.createElement("div");
      b.style.padding = "8px";
      b.style.border = "1px solid rgba(255,255,255,0.12)";
      b.style.borderRadius = "8px";
      b.style.background = "rgba(255,255,255,0.03)";
      b.innerHTML = `<div style="opacity:.7;font-size:12px;margin-bottom:4px;">${k}</div>
                     <div style="font-weight:600;">${Number.isFinite(v) ? num(v) : v}</div>`;
      wrap.appendChild(b);
    });
    return wrap;
  }

  function renderChart({ name, lines, ymin, ymax }) {
    const box = document.createElement("div");
    box.style.marginTop = "10px";
    const label = document.createElement("div");
    label.textContent = name || "Chart";
    label.style.opacity = "0.9";
    label.style.margin = "4px 0 6px";
    box.appendChild(label);

    const canvas = document.createElement("canvas");
    canvas.width = 960;
    canvas.height = 260;
    canvas.style.width = "100%";
    canvas.style.height = "260px";
    box.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;

    function yToPx(y, lo, hi) {
      const t = (y - lo) / Math.max(1e-9, (hi - lo));
      return 16 + (1 - t) * (H - 40);
    }

    let lo = +Infinity, hi = -Infinity;
    lines.forEach(L => L.points.forEach(p => { lo = Math.min(lo, p.y); hi = Math.max(hi, p.y); }));
    if (!isFinite(lo) || !isFinite(hi) || lo === hi) { lo = 0; hi = 1; }
    if (typeof ymin === "number") lo = Math.min(lo, ymin);
    if (typeof ymax === "number") hi = Math.max(hi, ymax);
    const pad = 0.08 * (hi - lo); lo -= pad; hi += pad;

    ctx.fillStyle = "#0b0f14"; ctx.fillRect(0,0,W,H);
    ctx.strokeStyle = "rgba(255,255,255,.12)";
    ctx.beginPath(); ctx.moveTo(56, 16); ctx.lineTo(56, H-24); ctx.lineTo(W-12, H-24); ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,.7)";
    ctx.font = "12px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (let i=0;i<=4;i++){
      const v = lo + (i*(hi-lo))/4;
      const py = yToPx(v, lo, hi);
      ctx.strokeStyle = "rgba(255,255,255,.06)";
      ctx.beginPath(); ctx.moveTo(56, py); ctx.lineTo(W-12, py); ctx.stroke();
      ctx.fillText(num(v), 52, py);
    }


    lines.forEach((L, idx) => {
      ctx.strokeStyle = L.color || ["#38bdf8","#ef4444","#a78bfa","#22c55e"][idx%4];
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      L.points.forEach((p, i) => {
        const px = 56 + p.x * (W - 68);
        const py = yToPx(p.y, lo, hi);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.stroke();
    });

    return box;
  }

  // =========================
  // Utils
  // =========================
  function smooth(points, win = 2) {
    if (win <= 1) return points;
    const out = points.map(p => ({ ...p }));
    for (let i = 0; i < points.length; i++) {
      let s=0,c=0;
      for (let k=-win;k<=win;k++){
        const j=i+k; if (j>=0 && j<points.length) { s+=points[j].y; c++; }
      }
      out[i].y = s/c;
    }
    return out;
  }

  function choosePointCount(settings) {
    const base = { "1h":72, "4h":48, "1d":32, "1w":24 }[settings.interval] || 32;
    const mult = { "1W":0.5, "1M":1, "3M":1.5, "6M":2, "1Y":2.5, ALL:3 }[settings.timescale] || 1;
    return Math.max(12, Math.floor(base * mult));
  }

  function alignXY(a, b) {
    const n = Math.min(a.length, b.length);
    return {
      ev: a.slice(0,n),
      price: b.slice(0,n),
      spread: a.slice(0,n).map((_,i)=>({ x: a[i].x, y: a[i].y - b[i].y })),
    };
  }

  function num(v) { return Number.isFinite(v) ? (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(3)) : String(v); }

  function styleTab(btn, active) {
    btn.style.padding = "6px 10px";
    btn.style.fontSize = "12px";
    btn.style.borderRadius = "8px";
    btn.style.border = "1px solid rgba(255,255,255,0.15)";
    btn.style.cursor = "pointer";
    btn.style.background = active ? "rgba(56,189,248,0.18)" : "transparent";
    btn.style.color = "white";
  }
});
