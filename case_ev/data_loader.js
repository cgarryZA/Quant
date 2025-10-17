// data_loader.js
// Minimal data-only loader.
// - Expands a case JSON into a flat list of items (skins/knives/gloves)
// - Enumerates per-wear × ST variants
// - Generates a deterministic USD random-walk price series for each variant
// - Generates a deterministic USD random-walk case price series
// No probability logic here. Pure data fetch + expansion + series.

//
// ------- Public API -------
//
// configureCatalogPaths({ root, casesDir, collectionsDir, knivesDir, glovesDir })
// loadCaseData(caseName, { n, settings }) -> { items, variants, seriesByKey, errors, caseUrl }
// getVariantSeries({ skin, wear, st }) -> [{x,y}, ...]  (after loadCaseData)
// listVariants() -> [{ key, skin, wear, st }]           (after loadCaseData)
// getCasePriceSeries({ n, settings, caseName }) -> [{x,y}, ...]
// listCases() -> ["Chroma 2", "Spectrum 2", ...]
// WEARS, ST_FLAGS for convenience
//

// ==============================
// Configurable catalogue paths
// ==============================
const _paths = {
  root: "/data/catalogues",
  casesDir: "cases",
  collectionsDir: "collections",
  knivesDir: "knives",
  glovesDir: "gloves",
};

export function configureCatalogPaths({ root, casesDir, collectionsDir, knivesDir, glovesDir } = {}) {
  if (root) _paths.root = root;
  if (casesDir) _paths.casesDir = casesDir;
  if (collectionsDir) _paths.collectionsDir = collectionsDir;
  if (knivesDir) _paths.knivesDir = knivesDir;
  if (glovesDir) _paths.glovesDir = glovesDir;
}

function joinUrl(...parts) {
  return parts
    .filter(Boolean)
    .map((p, i) => (i === 0 ? String(p).replace(/\/+$/,"") : String(p).replace(/^\/+|\/+$/g,"")))
    .join("/");
}

function slugifyFilename(name) {
  const s = (name || "")
    .trim()
    .replace(/[^\w\s&-]/g, "")
    .replace(/\s+/g, "_");
  return `${s}.json`;
}

async function fetchJSON(url) {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
async function fetchText(url) {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

// ==============================
// Skin lists (collections)
// ==============================
function genCollectionFilenameCandidates(collectionName) {
  const raw = (collectionName || "").trim();

  const stem = raw.replace(/\s*Collection\s*$/i, "").trim();

  const forms = new Set();
  if (stem) {
    forms.add(stem);
    forms.add(stem.replace(/^the\s+/i, "").trim());
    if (!/^the\s/i.test(stem)) forms.add(`The ${stem}`);
  }

  const ampVariants = (s) => [s, s.replace(/&/g, "and"), s.replace(/&/g, "")];

  const candidates = [];
  for (const f of forms) {
    for (const v of ampVariants(f)) {
      candidates.push(
        joinUrl(_paths.root, _paths.collectionsDir, slugifyFilename(v))
      );
    }
  }

  return [...new Set(candidates)];
}


async function loadSkins(collectionName, errs) {
  if (!collectionName) return [];
  const tried = [];
  for (const url of genCollectionFilenameCandidates(collectionName)) {
    tried.push(url);
    const data = await fetchJSON(url);
    if (data) {
      const out = [];
      for (const s of (data.Skins || [])) {
        const weapon = (s.Weapon || "").trim();
        const name   = (s.Name   || "").trim();
        if (weapon && name) out.push(`${weapon} ${name}`);
      }
      return out;
    }
  }
  errs.push(`[WARN] Couldn't find collection file for '${collectionName}'. Tried: ${tried.join(", ")}`);
  return [];
}

// ==============================
// Knives
// ==============================
const _KNIFE_PACK_HINTS = {
  "original": "Original",
  "chroma": "Chroma",
  "gamma": "Gamma",
  "spectrum": "Spectrum",
  "fracture": "Fracture",
  "horizon": "Horizon",
  "prisma": "Prisma",
  "prisma 2": "Prisma_2",
  "gamma 2": "Gamma_2",
  "chroma 2": "Chroma_2",
  "chroma 3": "Chroma_3",
  "spectrum 2": "Spectrum_2",
};

function normalizeKnifePack(extraordinaryItems) {
  if (!extraordinaryItems) return null;
  let s = extraordinaryItems.trim().toLowerCase();
  s = s.replace(/\s+knives?$/, "");
  s = s.replace(/&/g, "and").trim();

  const keys = Object.keys(_KNIFE_PACK_HINTS).sort((a, b) => b.length - a.length);
  for (const k of keys) {
    if (s === k) return `${_KNIFE_PACK_HINTS[k]}.json`;
  }

  const base = s.replace(/\s+/g, "_").replace(/^_+|_+$/g, "");
  if (!base) return null;
  const titled = base.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join("_");
  return `${titled}.json`;
}

async function loadKnifeFinishes(extraordinaryItems, errs) {
  const file = normalizeKnifePack(extraordinaryItems);
  if (!file) {
    errs.push(`[WARN] Could not determine knife pack from ExtraordinaryItems='${extraordinaryItems}'`);
    return [];
  }
  const url = joinUrl(_paths.root, _paths.knivesDir, file);
  const data = await fetchJSON(url);
  if (!data) {
    errs.push(`[WARN] Knife pack file missing: ${url}`);
    return [];
  }
  const finishes = [];
  const fin = data.Finishes || {};
  for (const lst of Object.values(fin)) finishes.push(...(lst || []));
  if (finishes.length === 0) {
    errs.push(`[WARN] Knife pack '${file}' has no finishes listed.`);
  }
  return finishes;
}

// ==============================
// Gloves
// ==============================
function isGlovePackLabel(label) {
  if (!label) return false;
  const s = label.toLowerCase();
  return ["glove", "gloves", "broken fang", "clutch"].some(k => s.includes(k));
}

function normalizeGlovePack(extraordinaryItems) {
  if (!isGlovePackLabel(extraordinaryItems)) return null;
  const s = extraordinaryItems.toLowerCase();
  if (s.includes("broken") && s.includes("fang")) return "Broken_Fang.json";
  if (s.includes("clutch")) return "Clutch.json";
  if (s.includes("glove"))  return "Glove.json";
  return null;
}

async function loadGlovePackMap(extraordinaryItems, errs) {
  const file = normalizeGlovePack(extraordinaryItems);
  if (!file) {
    errs.push(`[WARN] Could not determine glove pack from ExtraordinaryItems='${extraordinaryItems}'`);
    return {};
  }
  const url = joinUrl(_paths.root, _paths.glovesDir, file);
  const data = await fetchJSON(url);
  if (!data) {
    errs.push(`[WARN] Glove pack file missing: ${url}`);
    return {};
  }
  const finishes = data.Finishes || {};
  if (typeof finishes !== "object" || !Object.keys(finishes).length) {
    errs.push(`[WARN] Glove pack '${file}' has no finishes map.`);
    return {};
  }
  return finishes;
}

// ==============================
// Per-case expansion (flat items)
// ==============================
async function expandCaseItems(caseName) {
  const caseUrl = joinUrl(_paths.root, _paths.casesDir, slugifyFilename(caseName));
  const caseData = await fetchJSON(caseUrl);
  if (!caseData) {
    return { items: null, errors: [`[ERR ] Could not read case file: ${caseUrl}`], caseUrl };
  }

  const errs = [];
  const items = [];
  const collectionName = (caseData.Collection || "").trim();
  const extraordinary  = (caseData.ExtraordinaryItems || "").trim();

  // Knives
  if (Array.isArray(caseData.Knives) && caseData.Knives.length && extraordinary) {
    const kfinishes = await loadKnifeFinishes(extraordinary, errs);
    if (kfinishes.length) {
      for (let k of caseData.Knives) {
        k = (k || "").trim();
        if (!k) continue;
        for (const f of kfinishes) items.push(`${k} ${f}`);
      }
    }
  }

  // Gloves
  if (isGlovePackLabel(extraordinary)) {
    const gmap = await loadGlovePackMap(extraordinary, errs);
    let gloveTypes = caseData.Gloves;
    if (gloveTypes == null) gloveTypes = Object.keys(gmap).sort();
    for (let g of (gloveTypes || [])) {
      g = (g || "").trim();
      if (!g) continue;
      if (g in gmap) {
        for (const f of gmap[g] || []) items.push(`${g} ${f}`);
      } else {
        if (Object.keys(gmap).some(t => g.startsWith(t + " "))) {
          items.push(g);
        } else {
          errs.push(`[WARN] Glove type '${g}' has no finishes in pack '${extraordinary}'`);
        }
      }
    }
  }

  // Collection skins
  items.push(...(await loadSkins(collectionName, errs)));

  if (!items.length) {
    errs.push(`[WARN] No items produced for case '${caseName}'`);
  }

  return { items, errors: errs, caseUrl };
}

// ==============================
// Variant enumeration & pricing
// ==============================
export const WEARS    = ["FN", "MW", "FT", "WW", "BS"];
export const ST_FLAGS = [true, false];

function variantKey(skin, wear, st) {
  return `${skin} | ${wear} | ${st ? "ST" : "N"}`;
}

function enumerateVariants(skins) {
  const out = [];
  for (const skin of skins) {
    for (const wear of WEARS) {
      for (const st of ST_FLAGS) {
        out.push({ key: variantKey(skin, wear, st), skin, wear, st });
      }
    }
  }
  return out;
}

function seededSeriesUSD({ skin, wear, st, n, settings }) {
  const seed = hash32(`[SKIN$]${skin}|${wear}|${st ? "ST" : "N"}|${settings.timescale}|${settings.interval}`);
  const rand = mulberry32(seed);

  const base =
    0.8 + (st ? 0.6 : 0) +
    ({ FN: 1.2, MW: 1.0, FT: 0.8, WW: 0.6, BS: 0.5 }[wear] || 0.7) +
    rand() * 0.6;

  const out = [];
  let y = base;
  for (let i = 0; i < n; i++) {
    const x = i / (n - 1);
    y *= 1 + (rand() - 0.5) * 0.05;
    y = Math.max(0.20, Math.min(500.0, y));
    out.push({ x, y });
  }
  return smooth(out, 2);
}

// ==============================
// Public store + loader
// ==============================
const _store = {
  variants: [],            // [{ key, skin, wear, st }, ...]
  seriesByKey: new Map(),  // key -> [{x,y},...]
  items: [],               // flat list of skins/items (strings)
  errors: [],
  caseUrl: "",
};

export function listVariants() {
  return _store.variants.slice();
}

export function getVariantSeries({ skin, wear, st }) {
  return _store.seriesByKey.get(variantKey(skin, wear, st)) || null;
}

export async function loadCaseData(caseName, opts = {}) {
  const n = Math.max(8, Math.floor(opts.n ?? 48));
  const settings = opts.settings || { timescale: "3M", interval: "1d" };

  const { items, errors, caseUrl } = await expandCaseItems(caseName);

  _store.items   = items || [];
  _store.errors  = errors || [];
  _store.caseUrl = caseUrl || "";

  _store.variants = enumerateVariants(_store.items);
  _store.seriesByKey = new Map();

  for (const v of _store.variants) {
    const series = seededSeriesUSD({ ...v, n, settings });
    _store.seriesByKey.set(v.key, series);
  }

  return {
    items: _store.items.slice(),
    variants: _store.variants.slice(),
    seriesByKey: _store.seriesByKey,
    errors: _store.errors.slice(),
    caseUrl: _store.caseUrl,
  };
}

// ==============================
// Case price series
// ==============================
export function getCasePriceSeries({ n = 48, settings = { timescale: "3M", interval: "1d" }, caseName = "" } = {}) {
  const seed = hash32(`[CASE|PRICE]${caseName}|${settings.timescale}|${settings.interval}`);
  const rand = mulberry32(seed);
  const out = [];
  let y = 3.2 + rand() * 1.2;
  for (let i = 0; i < n; i++) {
    const x = i / Math.max(1, (n - 1));
    y *= 1 + (rand() - 0.5) * 0.08;
    y = Math.max(0.5, Math.min(12.0, y));
    out.push({ x, y });
  }
  return smooth(out, 2);
}

// ==============================
// Case list (for dropdown)
// ==============================
export async function listCases() {
  const dirUrl = joinUrl(_paths.root, _paths.casesDir, "/");

  // 1) Try JSON index
  const idx = await fetchJSON(joinUrl(_paths.root, _paths.casesDir, "index.json"));
  if (idx) {
    const files = Array.isArray(idx)
      ? idx.map(v => (typeof v === "string" ? v : (v.file || v.name || "")))
      : [];
    return normalizeCaseNames(files.filter(f => f && /\.json$/i.test(f)));
  }

  const html = await fetchText(dirUrl);
  if (html) {
    const files = [];
    const re = /href="([^"]+\.json)"/gi;
    let m; while ((m = re.exec(html))) {
      const f = m[1].split("/").pop();
      if (f) files.push(f);
    }
    if (files.length) return normalizeCaseNames([...new Set(files)]);
  }
  
  return [];
}

function normalizeCaseNames(files) {
  return files
    .map(f => String(f).replace(/\.json$/i, ""))
    .map(base => base.replace(/_/g, " ").trim())
    .map(s => s.replace(/\s+/g, " "));
}

// ==============================
// Small utilities
// ==============================
function smooth(points, win = 2) {
  if (win <= 1) return points;
  const out = points.map(p => ({ ...p }));
  for (let i = 0; i < points.length; i++) {
    let sum = 0, cnt = 0;
    for (let k = -win; k <= win; k++) {
      const j = i + k;
      if (j >= 0 && j < points.length) {
        sum += points[j].y;
        cnt++;
      }
    }
    out[i].y = sum / cnt;
  }
  return out;
}

function hash32(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h += h << 13; h ^= h >>> 7;
  h += h << 3;  h ^= h >>> 17;
  h += h << 5;
  return h >>> 0;
}

function mulberry32(a) {
  return function () {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
