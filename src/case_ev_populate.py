# -*- coding: utf-8 -*-
# C:\Users\z00503ku\Documents\Quant\src\case_ev_populate.py
r"""
One-shot population script for PriceEmpire item price histories.

- Expands every case in /data/catalogues/cases into concrete Steam market_hash_names
- Minimizes paid calls by batching and using max (<=180d) windows per request
- Iterates backward from today to as-early-as (default 2013-01-01), with early-stop on consecutive empty windows
- Saves merged per-item raw history JSONs under data/raw/<provider>/items/

USAGE (PowerShell/CMD):
  set PRICEMPIRE_API_KEY=...   # or $env:PRICEMPIRE_API_KEY in PowerShell
  python C:\Users\z00503ku\Documents\Quant\src\case_ev_populate.py

Defaults:
  providers = buff163
  from      = 2013-01-01
  to        = today
  batch-size= 50


  python C:\Users\z00503ku\Documents\Quant\src\case_ev_populate.py --debug
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import argparse
import datetime as dt
from typing import Dict, List, Tuple, Iterable, Optional

try:
    import requests  # type: ignore
except ImportError:
    print("Please `pip install requests` before running.", file=sys.stderr)
    sys.exit(1)

# ---------- CONFIG DEFAULTS ----------
DATA_ROOT = r"C:\Users\z00503ku\Documents\Quant\data"
CATALOG_ROOT = os.path.join(DATA_ROOT, "catalogues")
CASES_DIR = os.path.join(CATALOG_ROOT, "cases")
COLLECTIONS_DIR = os.path.join(CATALOG_ROOT, "collections")
KNIVES_DIR = os.path.join(CATALOG_ROOT, "knives")
GLOVES_DIR = os.path.join(CATALOG_ROOT, "gloves")

RAW_OUT_DIR = os.path.join(DATA_ROOT, "raw")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG = os.path.join(SCRIPT_DIR, "case_ev_populate.debug_requests.txt")

API_BASE = "https://api.pricempire.com/v4/paid/items/prices/history"
DEFAULT_PROVIDERS = ["buff163"]  # default provider
DEFAULT_CURRENCY = "USD"
WINDOW_DAYS_MAX = 180
DEFAULT_FROM = "2013-01-01"
DEFAULT_MAX_EMPTY_WINDOWS = 2
DEFAULT_BATCH_SIZE = 50
DEFAULT_SLEEP_SEC = 0.15

# Exteriors mapping
EXTERIORS = [
    ("FN", "Factory New"),
    ("MW", "Minimal Wear"),
    ("FT", "Field-Tested"),
    ("WW", "Well-Worn"),
    ("BS", "Battle-Scarred"),
]
EXTERIOR_NAME = dict(EXTERIORS)

# ---------- UTILITIES ----------
def slugify_filename(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[^\w\s&-]", "", s)
    s = re.sub(r"\s+", "_", s)
    return f"{s}.json"

def join_path(*parts: str) -> str:
    return os.path.normpath(os.path.join(*[p for p in parts if p]))

def list_json_files(directory: str) -> List[str]:
    if not os.path.isdir(directory):
        return []
    return [f for f in os.listdir(directory) if f.lower().endswith(".json")]

def read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def today_str() -> str:
    return dt.date.today().isoformat()

def date_chunks_backward(from_date: str, to_date: str, days: int) -> Iterable[Tuple[str, str]]:
    end = dt.date.fromisoformat(to_date)
    start_min = dt.date.fromisoformat(from_date)
    one = dt.timedelta(days=1)
    span = dt.timedelta(days=days - 1)
    while end >= start_min:
        start = max(start_min, end - span)
        yield (start.isoformat(), end.isoformat())
        end = start - one

def sanitize_filename(s: str) -> str:
    s = s.replace("™", "TM").replace("★", "STAR")
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", s)

def dedup_merge_dict(dst: Dict[str, int], src: Dict[str, int]) -> None:
    dst.update(src or {})

def chunked(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

# ---------- NAME BUILDERS ----------
def build_skin_names(base: str) -> List[str]:
    names = []
    for _, ext in EXTERIORS:
        names.append(f"{base} ({ext})")
        names.append(f"StatTrak™ {base} ({ext})")
    return names

def build_knife_names(knife_finish: str) -> List[str]:
    return [f"★ {knife_finish}", f"★ StatTrak™ {knife_finish}"]

def build_glove_names(glove_finish: str) -> List[str]:
    names = []
    for _, ext in EXTERIORS:
        names.append(f"★ {glove_finish} ({ext})")
    return names

# ---------- CATALOG EXPANSION (mirror your JS) ----------
KNIFE_PACK_HINTS = {
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
}

def normalize_knife_pack(label: str) -> Optional[str]:
    if not label:
        return None
    s = label.strip().lower()
    s = re.sub(r"\s+knives?$", "", s)
    s = s.replace("&", "and").strip()
    for k in sorted(KNIFE_PACK_HINTS.keys(), key=len, reverse=True):
        if s == k:
            return f"{KNIFE_PACK_HINTS[k]}.json"
    base = re.sub(r"\s+", "_", s).strip("_")
    if not base:
        return None
    titled = "_".join(w[:1].upper() + w[1:] for w in base.split("_"))
    return f"{titled}.json"

def is_glove_pack_label(label: str) -> bool:
    if not label: return False
    t = label.lower()
    return any(k in t for k in ["glove", "gloves", "broken fang", "clutch"])

def normalize_glove_pack(label: str) -> Optional[str]:
    if not is_glove_pack_label(label):
        return None
    s = label.lower()
    if "broken" in s and "fang" in s: return "Broken_Fang.json"
    if "clutch" in s: return "Clutch.json"
    if "glove" in s: return "Glove.json"
    return None

def gen_collection_filename_candidates(collection_name: str) -> List[str]:
    raw = (collection_name or "").strip()
    stem = re.sub(r"\s*Collection\s*$", "", raw, flags=re.I).strip()
    forms = set()
    if stem:
        forms.add(stem)
        forms.add(re.sub(r"^the\s+", "", stem, flags=re.I).strip())
        if not re.match(r"^the\s", stem, flags=re.I):
            forms.add(f"The {stem}")
    def amp_variants(s: str) -> List[str]:
        return [s, s.replace("&", "and"), s.replace("&", "")]
    candidates = []
    for f in forms:
        for v in amp_variants(f):
            candidates.append(os.path.join(COLLECTIONS_DIR, slugify_filename(v)))
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            out.append(c); seen.add(c)
    return out

def load_skins_from_collection(collection_name: str, errs: List[str]) -> List[str]:
    if not collection_name:
        return []
    tried = []
    for path in gen_collection_filename_candidates(collection_name):
        tried.append(path)
        data = read_json(path)
        if data:
            out = []
            for s in data.get("Skins", []):
                weapon = (s.get("Weapon") or "").strip()
                name   = (s.get("Name")   or "").strip()
                if weapon and name:
                    out.append(f"{weapon} | {name}")
            return out
    errs.append(f"[WARN] Couldn't find collection file for '{collection_name}'. Tried: " + ", ".join(tried))
    return []

def load_knife_finishes(extraordinary_items: str, errs: List[str]) -> List[str]:
    file = normalize_knife_pack(extraordinary_items)
    if not file:
        errs.append(f"[WARN] Could not determine knife pack from ExtraordinaryItems='{extraordinary_items}'")
        return []
    path = os.path.join(KNIVES_DIR, file)
    data = read_json(path)
    if not data:
        errs.append(f"[WARN] Knife pack file missing: {path}")
        return []
    finishes = []
    fin = data.get("Finishes") or {}
    for lst in fin.values():
        finishes.extend(lst or [])
    if not finishes:
        errs.append(f"[WARN] Knife pack '{file}' has no finishes listed.")
    return finishes

def load_glove_pack_map(extraordinary_items: str, errs: List[str]) -> Dict[str, List[str]]:
    file = normalize_glove_pack(extraordinary_items)
    if not file:
        errs.append(f"[WARN] Could not determine glove pack from ExtraordinaryItems='{extraordinary_items}'")
        return {}
    path = os.path.join(GLOVES_DIR, file)
    data = read_json(path)
    if not data:
        errs.append(f"[WARN] Glove pack file missing: {path}")
        return {}
    finishes = data.get("Finishes") or {}
    if not isinstance(finishes, dict) or not finishes:
        errs.append(f"[WARN] Glove pack '{file}' has no finishes map.")
        return {}
    return finishes

def expand_case_items(case_path: str) -> Tuple[List[str], List[str], List[str]]:
    data = read_json(case_path)
    errs: List[str] = []
    if not data:
        return [], [], [f"[ERR ] Could not read case file: {case_path}"]
    skins_bases: List[str] = []
    knife_bases: List[str] = []
    collection_name = (data.get("Collection") or "").strip()
    extraordinary = (data.get("ExtraordinaryItems") or "").strip()

    if isinstance(data.get("Knives"), list) and data["Knives"] and extraordinary:
        finishes = load_knife_finishes(extraordinary, errs)
        if finishes:
            for k in data["Knives"]:
                k = (k or "").strip()
                if not k:
                    continue
                for f in finishes:
                    knife_bases.append(f"{k} | {f}")

    if is_glove_pack_label(extraordinary):
        gmap = load_glove_pack_map(extraordinary, errs)
        glove_types = data.get("Gloves")
        if glove_types is None:
            glove_types = sorted(gmap.keys())
        for g in (glove_types or []):
            g = (g or "").strip()
            if not g:
                continue
            if g in gmap:
                for f in (gmap.get(g) or []):
                    skins_bases.append(f"{g} | {f}")  # treat like base; expand as gloves later
            else:
                if any(g.startswith(t + " ") for t in gmap.keys()):
                    skins_bases.append(g)
                else:
                    errs.append(f"[WARN] Glove type '{g}' has no finishes in pack '{extraordinary}'")

    skins_bases.extend(load_skins_from_collection(collection_name, errs))
    return skins_bases, knife_bases, errs

def build_all_market_hash_names_for_case(case_path: str) -> Tuple[List[str], List[str]]:
    skins_bases, knife_bases, errs = expand_case_items(case_path)
    names: List[str] = []
    for base in skins_bases:
        if " | " in base and base.split(" | ")[0] in {
            "Hand Wraps", "Driver Gloves", "Specialist Gloves", "Sport Gloves",
            "Moto Gloves", "Hydra Gloves", "Broken Fang Gloves"
        }:
            for _, ext in EXTERIORS:
                names.append(f"★ {base} ({ext})")
        else:
            names.extend(build_skin_names(base))
    for base in knife_bases:
        names.extend(build_knife_names(base))
    seen, ordered = set(), []
    for n in names:
        if n not in seen:
            ordered.append(n); seen.add(n)
    return ordered, errs

# ---------- API ----------
def build_request_url(provider_key: str, currency: str, start_date: str, end_date: str, market_hash_names: List[str]) -> str:
    q = [
        ("app_id", "730"),
        ("provider_key", provider_key),
        ("currency", currency),
        ("from_date", start_date),
        ("to_date", end_date),
        ("market_hash_names", ",".join(market_hash_names)),
    ]
    return API_BASE + "?" + "&".join(f"{k}={v}" for k, v in q)

def hit_api(session: requests.Session, api_key: str, provider_key: str, currency: str,
            start_date: str, end_date: str, market_hash_names: List[str],
            debug: bool, debug_lines: List[str]) -> Optional[dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "app_id": 730,
        "provider_key": provider_key,
        "currency": currency,
        "from_date": start_date,
        "to_date": end_date,
        "market_hash_names": ",".join(market_hash_names),
    }
    if debug:
        debug_lines.append(build_request_url(provider_key, currency, start_date, end_date, market_hash_names))
        return None
    resp = session.get(API_BASE, headers=headers, params=params, timeout=60)
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            return None
    try:
        errj = resp.json()
    except Exception:
        errj = {"text": resp.text[:500]}
    print(f"[WARN] HTTP {resp.status_code} for {provider_key} {start_date}->{end_date}: {errj}", file=sys.stderr)
    return None

# ---------- SAVE ----------
def save_item_history(out_root: str, provider_key: str, market_hash_name: str, merged: Dict[str, int], meta: dict) -> None:
    out_dir = os.path.join(out_root, provider_key, "items")
    ensure_dir(out_dir)
    fname = sanitize_filename(market_hash_name) + ".json"
    out_path = os.path.join(out_dir, fname)
    payload = {"metadata": meta, "data": merged}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

# ---------- MAIN ----------
def main():
    # <-- move globals to top of function to avoid SyntaxError
    global CATALOG_ROOT, CASES_DIR, COLLECTIONS_DIR, KNIVES_DIR, GLOVES_DIR

    parser = argparse.ArgumentParser(description="Populate PriceEmpire histories for all items in all cases.")
    parser.add_argument("--catalog-root", default=CATALOG_ROOT)
    parser.add_argument("--cases-dir", default=CASES_DIR)
    parser.add_argument("--collections-dir", default=COLLECTIONS_DIR)
    parser.add_argument("--knives-dir", default=KNIVES_DIR)
    parser.add_argument("--gloves-dir", default=GLOVES_DIR)
    parser.add_argument("--out-dir", default=RAW_OUT_DIR)
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS), help="Comma-separated provider keys (e.g., buff163,steam)")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY)
    parser.add_argument("--from", dest="from_date", default=DEFAULT_FROM)
    parser.add_argument("--to", dest="to_date", default=today_str())
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SEC)
    parser.add_argument("--max-empty-windows", type=int, default=DEFAULT_MAX_EMPTY_WINDOWS)
    parser.add_argument("--case-filter", default="", help="Regex to filter case filenames (without .json)")
    parser.add_argument("--debug", action="store_true", help="Do not hit API; write intended URLs to a .debug_requests.txt file")
    args = parser.parse_args()

    # update module-level paths so helper functions use overrides
    CATALOG_ROOT = args.catalog_root
    CASES_DIR = args.cases_dir
    COLLECTIONS_DIR = args.collections_dir
    KNIVES_DIR = args.knives_dir
    GLOVES_DIR = args.gloves_dir

    api_key = os.getenv("PRICEMPIRE_API_KEY", "").strip()
    if not api_key and not args.debug:
        print("ERROR: PRICEMPIRE_API_KEY env var not set. Use --debug to avoid calling the API.", file=sys.stderr)
        sys.exit(2)

    case_files = [os.path.join(CASES_DIR, f) for f in list_json_files(CASES_DIR)]
    if args.case_filter:
        pat = re.compile(args.case_filter, re.I)
        case_files = [p for p in case_files if pat.search(os.path.splitext(os.path.basename(p))[0])]

    if not case_files:
        print(f"No case JSONs found under: {CASES_DIR}", file=sys.stderr)
        sys.exit(0)

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    currency = args.currency
    from_date = args.from_date
    to_date = args.to_date
    batch_size = max(1, args.batch_size)
    max_empty_windows = max(0, args.max_empty_windows)
    sleep_sec = max(0.0, args.sleep)

    all_names: List[str] = []
    all_warns: List[str] = []

    print(f"[INFO] Scanning cases under: {CASES_DIR}")
    for case_path in case_files:
        case_base = os.path.splitext(os.path.basename(case_path))[0]
        names, warns = build_all_market_hash_names_for_case(case_path)
        all_warns.extend(warns)
        print(f"  - {case_base}: {len(names)} market_hash_names")
        all_names.extend(names)

    seen, mhns = set(), []
    for n in all_names:
        if n not in seen:
            mhns.append(n); seen.add(n)

    print(f"[INFO] Total unique market_hash_names: {len(mhns)}")

    per_item_data: Dict[str, Dict[str, int]] = {n: {} for n in mhns}

    debug_lines: List[str] = []
    session = requests.Session()

    for provider in providers:
        print(f"[INFO] Provider: {provider}")
        empty_streak = 0
        windows = list(date_chunks_backward(from_date, to_date, WINDOW_DAYS_MAX))
        for (start, end) in windows:
            window_had_data = False
            for batch in chunked(mhns, batch_size):
                resp_json = hit_api(session, api_key, provider, currency, start, end, batch, args.debug, debug_lines)
                if resp_json is None:
                    continue
                data = resp_json.get("data") or {}
                for name in batch:
                    series = data.get(name)
                    if isinstance(series, dict) and series:
                        window_had_data = True
                        dedup_merge_dict(per_item_data[name], series)
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
            if not args.debug:
                print(f"    window {start} → {end}: {'data' if window_had_data else 'empty'}")
            empty_streak = (empty_streak + 1) if not window_had_data else 0
            if empty_streak >= max_empty_windows:
                print(f"[INFO] Early stop after {empty_streak} empty windows for provider={provider}.")
                break

        if args.debug:
            with open(DEBUG_LOG, "w", encoding="utf-8") as fh:
                fh.write("\n".join(debug_lines))
            print(f"[DEBUG] Wrote intended requests to: {DEBUG_LOG}")
        else:
            meta_common = {
                "app_id": 730,
                "provider_key": provider,
                "currency": currency,
                "requested_from_date": from_date,
                "requested_to_date": to_date,
                "max_window_days": WINDOW_DAYS_MAX,
                "batch_size": batch_size,
                "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            }
            saved = 0
            for name, series in per_item_data.items():
                if not series:
                    continue
                meta = dict(meta_common)
                ts_list = sorted(int(k) for k in series.keys())
                if ts_list:
                    meta["observations"] = len(ts_list)
                    meta["first_epoch"] = ts_list[0]
                    meta["last_epoch"] = ts_list[-1]
                save_item_history(RAW_OUT_DIR, provider, name, series, meta)
                saved += 1
            print(f"[INFO] Saved {saved} items for provider={provider} to {RAW_OUT_DIR}")

    if all_warns:
        print("\n".join(all_warns))

if __name__ == "__main__":
    main()
