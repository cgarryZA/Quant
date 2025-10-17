import json
import sys
from pathlib import Path
import re

def log(msg: str): print(msg)

# ----- argv -----
def parse_args():
    if len(sys.argv) >= 3:
        return Path(sys.argv[1]), Path(sys.argv[2])
    root = Path(r"C:\Users\z00503ku\Documents\Quant\data\catalogues")
    return root / "cases", root / "outputs" / "cases"

# ----- catalogue roots -----
CAT_ROOT = Path(r"C:\Users\z00503ku\Documents\Quant\data\catalogues")
COLLECTIONS_DIR = CAT_ROOT / "collections"
KNIVES_DIR = CAT_ROOT / "knives"
GLOVES_DIR = CAT_ROOT / "gloves"

# ----- utils -----
def slugify_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s&-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return f"{name}.json"

def try_open_json(path: Path):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None

# =========================
#   COLLECTION (SKINS)
# =========================
def gen_collection_filename_candidates(collection_name: str):
    base = (collection_name or "").strip()
    no_suffix = re.sub(r"\s*Collection\s*$", "", base, flags=re.IGNORECASE).strip()
    labels = set()

    def add(label: str):
        if not label: return
        labels.add(label)
        if label.lower().startswith("the "):
            labels.add(label[4:])  # drop "The "
        if "&" in label:
            labels.add(label.replace("&", "and"))
            labels.add(label.replace("&", ""))

    add(base)
    add(no_suffix)

    return [COLLECTIONS_DIR / slugify_filename(lbl) for lbl in labels]

def load_skins(collection_name: str, errs: list[str]):
    if not collection_name:
        return []
    tried_paths = []
    for candidate in gen_collection_filename_candidates(collection_name):
        tried_paths.append(str(candidate))
        data = try_open_json(candidate)
        if data:
            out = []
            for s in data.get("Skins", []):
                weapon = (s.get("Weapon") or "").strip()
                name = (s.get("Name") or "").strip()
                if weapon and name:
                    out.append(f"{weapon} {name}")
            return out
    errs.append(f"[WARN] Couldn't find collection file for '{collection_name}'. Tried: {', '.join(tried_paths)}")
    return []

# =========================
#        KNIVES
# =========================
# Map common aliases to a file base name in /knives
_KNIFE_PACK_HINTS = {
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
    # add more if you have corresponding knife packs in /knives
}

def normalize_knife_pack(extraordinary_items: str) -> str | None:
    """
    Turn ExtraordinaryItems into a knife pack filename in /knives.
    Accepts values with or without 'Knives' suffix (e.g., 'Original', 'Original Knives').
    """
    if not extraordinary_items:
        return None
    s = extraordinary_items.strip().lower()
    s = re.sub(r"\s+knives?$", "", s)  # drop trailing 'knife/knives'
    s = s.replace("&", "and").strip()

    # direct hint match first (longer keys first to catch 'prisma 2' etc.)
    for k in sorted(_KNIFE_PACK_HINTS.keys(), key=len, reverse=True):
        if s == k:
            return f"{_KNIFE_PACK_HINTS[k]}.json"

    # fallback: TitleCase the residue → file.json
    base = re.sub(r"\s+", "_", s).strip("_")
    if not base:
        return None
    # capitalize each token roughly
    base = "_".join(w.capitalize() for w in base.split("_"))
    return f"{base}.json"

def load_knife_finishes(extraordinary_items: str, errs: list[str]):
    pack_file = normalize_knife_pack(extraordinary_items)
    if not pack_file:
        errs.append(f"[WARN] Could not determine knife pack from ExtraordinaryItems='{extraordinary_items}'")
        return []
    data = try_open_json(KNIVES_DIR / pack_file)
    if not data:
        errs.append(f"[WARN] Knife pack file missing: {KNIVES_DIR / pack_file}")
        return []
    finishes = []
    for lst in (data.get("Finishes") or {}).values():
        finishes.extend(lst)
    if not finishes:
        errs.append(f"[WARN] Knife pack '{pack_file}' has no finishes listed.")
    return finishes

# =========================
#        GLOVES
# =========================
def is_glove_pack_label(label: str) -> bool:
    if not label: return False
    s = label.lower()
    return any(k in s for k in ("glove", "gloves", "broken fang", "clutch"))

def normalize_glove_pack(extraordinary_items: str) -> str | None:
    if not is_glove_pack_label(extraordinary_items):
        return None
    s = extraordinary_items.lower()
    if "broken" in s and "fang" in s: return "Broken_Fang.json"
    if "clutch" in s:                 return "Clutch.json"
    if "glove" in s:                  return "Glove.json"
    return None

def load_glove_pack_map(extraordinary_items: str, errs: list[str]):
    fname = normalize_glove_pack(extraordinary_items)
    if not fname:
        errs.append(f"[WARN] Could not determine glove pack from ExtraordinaryItems='{extraordinary_items}'")
        return {}
    data = try_open_json(GLOVES_DIR / fname)
    if not data:
        errs.append(f"[WARN] Glove pack file missing: {GLOVES_DIR / fname}")
        return {}
    finishes = data.get("Finishes") or {}
    if not isinstance(finishes, dict) or not finishes:
        errs.append(f"[WARN] Glove pack '{fname}' has no finishes map.")
        return {}
    return finishes

# =========================
#   PER-CASE EXPANSION
# =========================
def expand_case_items(case_json_path: Path):
    case = try_open_json(case_json_path)
    if not case:
        return None, [f"[ERR ] Could not read case file: {case_json_path}"]

    errs, items = [], []
    collection_name = (case.get("Collection") or "").strip()
    extraordinary = (case.get("ExtraordinaryItems") or "").strip()

    # Knives (accept packs like 'Original' or 'Original Knives')
    if (case.get("Knives") or []) and extraordinary:
        kfinishes = load_knife_finishes(extraordinary, errs)
        if kfinishes:
            for k in case.get("Knives", []):
                k = (k or "").strip()
                if not k: continue
                for f in kfinishes:
                    items.append(f"{k} {f}")

    # Gloves (pack-based expansion)
    if is_glove_pack_label(extraordinary):
        gmap = load_glove_pack_map(extraordinary, errs)
        glove_types = case.get("Gloves")
        if glove_types is None:  # expand all in pack if not constrained
            glove_types = sorted(gmap.keys())
        for g in glove_types or []:
            g = (g or "").strip()
            if not g: continue
            if g in gmap:
                for f in gmap[g]:
                    items.append(f"{g} {f}")
            else:
                # allow legacy "Type Finish" entries to pass through
                if any(g.startswith(t + " ") for t in gmap.keys()):
                    items.append(g)
                else:
                    errs.append(f"[WARN] Glove type '{g}' has no finishes in pack '{extraordinary}'")

    # Weapon skins (always try)
    items.extend(load_skins(collection_name, errs))

    if not items:
        errs.append(f"[WARN] No items produced for case '{case_json_path.name}'")

    return items, errs

# =========================
#          MAIN
# =========================
def main():
    cases_dir, out_dir = parse_args()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building case item lists (knives + gloves + skins)...")
    all_errs = []
    n_ok = 0

    for p in sorted(cases_dir.glob("*.json")):
        items, errs = expand_case_items(p)
        if items is None:
            all_errs.append(f"[ERR ] Skipped {p.name}")
            continue
        out_path = out_dir / p.name
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        print(f"[OK  ] {p.name} -> {out_path}")
        n_ok += 1
        all_errs.extend(errs)

    print(f"\nDone. Wrote {n_ok} case files to: {out_dir}\n")
    if all_errs:
        print("Issues encountered:")
        for e in all_errs:
            print("  " + e)

if __name__ == "__main__":
    main()
