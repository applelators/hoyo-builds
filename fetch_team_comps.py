#!/usr/bin/env python3
"""
Extract ZZZ team comp member characters from Google Sheets portrait images.
Matches 100×119px portrait images against wiki Agent portrait art via phash.
Output: team_map.json  { "CharName": {"teams": [{"label":"...", "members":[...]}]} }

Usage:
    python3 fetch_team_comps.py [--debug] [--tab GID] [--threshold N]
"""

import argparse
import asyncio
from collections import Counter
import io
import json
import os
import re
import requests
import sys
from typing import Dict, List, Optional, Set, Tuple

SHEET_BASE = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTj2PaPq6Py_1B5fsOPj_Moc-tN_7mut7fICczI6lz1njyEIAInTnfB7lAraX4pYCRGNbaHGlIbFZ90"
)
SHEET_GIDS = [
    "571511473",
    "1270581085",
    "897804407",
    "622827842",
    "1395442363",
]

ICONS_JSON      = "/Users/hokori/genshin-builds/icons.json"
ICON_CACHE      = "/Users/hokori/.cache/zzz_icons"
PORTRAIT_CACHE  = "/Users/hokori/.cache/zzz_portraits"
ZZZ_WIKI        = "zenless-zone-zero.fandom.com"
OUTPUT          = "/Users/hokori/genshin-builds/team_map.json"

# Portrait image size filter (pixels, at 1600px viewport)
IMG_W_MIN, IMG_W_MAX = 80,  125
IMG_H_MIN, IMG_H_MAX = 90,  145

# x-range of team comp portrait columns
TEAM_X_MIN = 200
TEAM_X_MAX = 1950

# x-range of team general / misc text (right side, not team comps)
TEAM_MISC_X = 1500

TEAMCOMP_GAP_MAX = 60

# Characters whose portrait filename differs from the normalised pattern.
PORTRAIT_OVERRIDES = {
    "Seed":             "Agent_Seed_Portrait.png",
    "Orphie & Magus":   "Agent_Orphie_Magnusson_%26_Magus_Portrait.png",
    "Rina":             "Agent_Rina_Portrait.png",
    "Soldier 11":       "Agent_Soldier_11_Portrait.png",
    "Anby: Soldier 0":  "Agent_Soldier_0_Portrait.png",
    "Lucy":             "Agent_Lucy_Portrait.png",
}

# Manually verified team comps — override automated detection on every run.
_EXACT_OUTPUT: Dict[str, dict] = {
    "Cissia": {"teams": [
        {"label": "Ssseed",              "members": ["Cissia", "Seed", "Dialyn"]},
        {"label": "King Cobra",          "members": ["Cissia", "Dialyn", "Sunna"]},
        {"label": "Food Chain",          "members": ["Cissia", "Trigger", "Nicole"]},
        {"label": "Brokie Hypercarry",   "members": ["Cissia", "Lycaon", "Nicole"]},
        {"label": "Generic Team Example","members": ["Cissia", "Seth", "Astra Yao"]},
    ]},
    "Nangong Yu": {"teams": [
        {"label": "AoD: Lead(er) Dancer",               "members": ["Nangong Yu", "Aria", "Astra Yao"]},
        {"label": "Brand-new Anomaly Wheelchair",       "members": ["Nangong Yu", "Burnice", "Lucy"]},
        {"label": "Poppin' Ice",                        "members": ["Nangong Yu", "Yuzuha", "Miyabi"]},
        {"label": "Anything to fund the show (F2P)",    "members": ["Nangong Yu", "Piper", "Nicole"]},
        {"label": "Generic Team Example",               "members": ["Nangong Yu", "Lighter", "Astra Yao"]},
    ]},
    "Promeia": {"teams": [
        {"label": "Ice Cold Treats",        "members": ["Promeia", "Nangong Yu", "Yuzuha"]},
        {"label": "Purple Aesthetic",       "members": ["Promeia", "Vivian", "Yuzuha"]},
        {"label": "Chains and Blossoms",    "members": ["Promeia", "Vivian", "Zhao"]},
        {"label": "Beauties and the Beast", "members": ["Promeia", "Lycaon", "Nicole"]},
        {"label": "Generic Team Example",   "members": ["Promeia", "Astra Yao", "Yuzuha"]},
    ]},
}


def _wiki_portrait_filename(char_name: str) -> str:
    override = PORTRAIT_OVERRIDES.get(char_name)
    if override:
        return override
    base = re.sub(r"\s*\([^)]+\)$", "", char_name).strip()
    base = base.replace(" ", "_")
    return f"Agent_{base}_Portrait.png"


def _fetch_wiki_url(filename: str) -> Optional[str]:
    api = (
        f"https://{ZZZ_WIKI}/api.php?action=query"
        f"&titles=File:{filename}&prop=imageinfo&iiprop=url&format=json"
    )
    try:
        resp = requests.get(api, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not resp.ok:
            return None
        for page in resp.json().get("query", {}).get("pages", {}).values():
            if "missing" in page:
                return None
            imgs = page.get("imageinfo", [])
            if imgs:
                return imgs[0]["url"]
    except Exception:
        pass
    return None


# ─── Reference portraits ──────────────────────────────────────────────────────

def download_reference_icons() -> Dict[str, bytes]:
    """Download and cache Agent icon thumbnails for all ZZZ characters.

    Uses icons.json icon URLs (small square thumbnails matching spreadsheet style).
    """
    with open(ICONS_JSON) as f:
        all_icons = json.load(f)
    zzz_icons: Dict[str, str] = all_icons.get("zzz", {})

    os.makedirs(ICON_CACHE, exist_ok=True)

    result: Dict[str, bytes] = {}
    hits, misses = 0, 0

    for char_name, icon_url in zzz_icons.items():
        safe = re.sub(r"[^\w]", "_", char_name)
        icon_path = os.path.join(ICON_CACHE, f"{safe}.png")

        if os.path.exists(icon_path):
            with open(icon_path, "rb") as fh:
                result[char_name] = fh.read()
            hits += 1
            continue

        try:
            resp = requests.get(icon_url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                result[char_name] = resp.content
                with open(icon_path, "wb") as fh:
                    fh.write(resp.content)
                hits += 1
            else:
                print(f"  WARN: {char_name}: HTTP {resp.status_code}")
                misses += 1
        except Exception as exc:
            print(f"  WARN: {char_name}: {exc}")
            misses += 1

    print(f"  {hits} icons loaded, {misses} failed "
          f"({len(result)} total, cache: {ICON_CACHE})")
    return result


def build_phash_db(char_icons: Dict[str, bytes]) -> Dict[str, object]:
    """Return {char_name: phash} for all downloadable icons."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        print("  ERROR: pip install imagehash Pillow")
        return {}

    db: Dict[str, object] = {}
    for name, data in char_icons.items():
        try:
            h = imagehash.phash(Image.open(io.BytesIO(data)))
            db[name] = h
        except Exception:
            pass
    print(f"  {len(db)} reference phashes built")
    return db


def best_match(img_bytes: bytes,
               phash_db: Dict[str, object],
               threshold: int) -> Tuple[Optional[str], int]:
    """Return (char_name, dist) or (None, 999) if no match within threshold."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None, 999
    try:
        h = imagehash.phash(Image.open(io.BytesIO(img_bytes)))
    except Exception:
        return None, 999

    best_d, best_n = 999, None
    for name, rh in phash_db.items():
        d = abs(h - rh)
        if d < best_d:
            best_d, best_n = d, name
    if best_d <= threshold:
        return best_n, best_d
    return None, best_d


# ─── DOM helpers (shared by token extraction and team loading) ────────────────

def _base_token(url: str) -> str:
    """Strip Google Serving URL size suffix to get the stable base image token."""
    tail = url.split("/")[-1]
    return re.sub(r"=w\d+-h\d+.*$", "", tail)


_DOM_ROWS_JS = r"""() => {
    const result = [];
    for (const tr of document.querySelectorAll('tr')) {
        const trRect = tr.getBoundingClientRect();
        const cells = [];
        for (const td of tr.querySelectorAll('td')) {
            const text = td.innerText.trim();
            const rect = td.getBoundingClientRect();
            cells.push({text, x: Math.round(rect.left),
                        w: Math.round(rect.width), y: Math.round(rect.top)});
        }
        result.push({y: Math.round(trRect.top), h: Math.round(trRect.height), cells});
    }
    return result;
}"""

_DOM_IMGS_JS = r"""() => {
    const results = [];
    for (const img of document.querySelectorAll('img')) {
        const rect = img.getBoundingClientRect();
        results.push({
            src: img.src, alt: img.alt || '',
            x: Math.round(rect.left), y: Math.round(rect.top),
            w: Math.round(rect.width), h: Math.round(rect.height),
        });
    }
    return results;
}"""


async def _load_tab(page, gid: str):
    """Load a sheet tab and return (rows, portrait_imgs, char_rows, tc_ys)."""
    url = f"{SHEET_BASE}/pubhtml/sheet?headers=false&gid={gid}"
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)

    rows     = await page.evaluate(_DOM_ROWS_JS)
    raw_imgs = await page.evaluate(_DOM_IMGS_JS)

    # Character row detection
    lu_ys = {r["y"] for r in rows
             if any("last updated" in c["text"].lower() for c in r["cells"])}
    SKIP = {"S Rank Agents", "A Rank Agents", "S Rank", "A Rank",
            "Equipment", "Role", "Ability Priority", "W-Engines",
            "Drive Disc Stats", "Team Comps"}
    candidates = []
    for row in rows:
        left = [c for c in row["cells"] if c["x"] < 250 and c["text"] and len(c["text"]) > 2]
        if len(left) != 1:
            continue
        name = left[0]["text"]
        if name.lower().startswith("last updated") or name in SKIP:
            continue
        if any(0 < lu_y - row["y"] <= 120 for lu_y in lu_ys):
            candidates.append({"name": name, "y": row["y"]})

    char_rows: list = []
    i = 0
    while i < len(candidates):
        if (i + 1 < len(candidates) and
                candidates[i + 1]["y"] - candidates[i]["y"] <= TEAMCOMP_GAP_MAX):
            char_rows.append(candidates[i + 1])
            i += 2
        else:
            char_rows.append(candidates[i])
            i += 1
    for j in range(len(char_rows) - 1):
        char_rows[j]["next_y"] = char_rows[j + 1]["y"]
    if char_rows:
        char_rows[-1]["next_y"] = 999999

    tc_ys: List[int] = [
        row["y"] for row in rows
        if any(c["text"].lower() == "team comps" for c in row["cells"])
    ]

    portrait_imgs = [
        img for img in raw_imgs
        if (IMG_W_MIN <= img["w"] <= IMG_W_MAX
            and IMG_H_MIN <= img["h"] <= IMG_H_MAX
            and TEAM_X_MIN <= img["x"] <= TEAM_X_MAX)
    ]

    return rows, portrait_imgs, char_rows, tc_ys


def _section_data(char_row: dict, rows: list, portrait_imgs: list,
                  tc_ys: List[int]) -> tuple:
    """Return (tc_y, label_cells, portraits) for a single character section."""
    y0, y1 = char_row["y"], char_row["next_y"]
    tc_y = next((y for y in tc_ys if y0 <= y < y1), None)
    if tc_y is None:
        return None, None, None
    label_cells: List[Tuple[int, str]] = []
    for row in rows:
        if not (tc_y < row["y"] < y1):
            continue
        for cell in row["cells"]:
            if (TEAM_X_MIN <= cell["x"] <= TEAM_X_MAX
                    and cell["w"] >= 250
                    and cell["text"]
                    and cell["text"].lower() not in ("team comps",)):
                label_cells.append((cell["x"], cell["text"]))
    label_cells.sort(key=lambda t: t[0])
    portraits = sorted(
        [img for img in portrait_imgs if tc_y < img["y"] < y1],
        key=lambda i: i["x"],
    )
    return tc_y, label_cells, portraits


# ─── Pass 1: Token extraction ─────────────────────────────────────────────────

async def extract_tab_tokens(page, gid: str) -> Dict[str, str]:
    """Return {char_name: base_token} using dominant-token heuristic (no downloads)."""
    rows, portrait_imgs, char_rows, tc_ys = await _load_tab(page, gid)
    char_token: Dict[str, str] = {}
    for cr in char_rows:
        _, label_cells, portraits = _section_data(cr, rows, portrait_imgs, tc_ys)
        if not label_cells:
            continue
        team_token_sets: List[Set[str]] = []
        for ti, (lx, _) in enumerate(label_cells):
            next_lx = label_cells[ti + 1][0] if ti + 1 < len(label_cells) else TEAM_X_MAX + 1
            tokens: Set[str] = {_base_token(p["src"])
                                for p in portraits if lx <= p["x"] < next_lx}
            if tokens:
                team_token_sets.append(tokens)
        if not team_token_sets:
            continue
        freq = Counter(tok for tset in team_token_sets for tok in tset)
        dominant, count = freq.most_common(1)[0]
        if count >= (len(team_token_sets) + 1) // 2:
            char_token[cr["name"]] = dominant
    return char_token


# ─── Pass 2: Team loading ─────────────────────────────────────────────────────

async def load_sheet_teams(page, gid: str,
                           phash_db: Dict[str, object],
                           threshold: int,
                           global_token_to_char: Dict[str, str],
                           debug: bool = False) -> Dict[str, dict]:
    """
    Returns {char_name: {"teams": [{"label": str, "members": [str, ...]}]}}
    for all characters on this sheet tab.
    Uses global_token_to_char for direct lookup; phash as fallback.
    """
    rows, portrait_imgs, char_rows, tc_ys = await _load_tab(page, gid)

    if debug:
        print(f"  {len(char_rows)} characters: {[c['name'] for c in char_rows]}")

    # ── Download all unique portrait images ───────────────────────────────────
    seen_srcs: Dict[str, Optional[bytes]] = {}
    for img in portrait_imgs:
        if img["src"] not in seen_srcs:
            seen_srcs[img["src"]] = None
    print(f"  Downloading {len(seen_srcs)} unique portrait images...")
    for src in list(seen_srcs):
        try:
            resp = await page.request.get(src)
            if resp.ok:
                seen_srcs[src] = await resp.body()
        except Exception:
            pass
    downloaded = sum(1 for v in seen_srcs.values() if v)
    print(f"  Downloaded {downloaded}/{len(seen_srcs)}")

    # ── Match portraits: global token lookup first, phash fallback ────────────
    src_to_char: Dict[str, Optional[str]] = {}
    for src, data in seen_srcs.items():
        tok = _base_token(src)
        if tok in global_token_to_char:
            src_to_char[src] = global_token_to_char[tok]
            if debug:
                tail = src.split("/")[-1][:30]
                print(f"    {tail} → {global_token_to_char[tok]!r} (token)")
        elif data is None:
            src_to_char[src] = None
        else:
            name, dist = best_match(data, phash_db, threshold)
            src_to_char[src] = name
            if debug:
                tail = src.split("/")[-1][:30]
                print(f"    {tail} → {name!r} (phash dist={dist})")

    # ── Per-character: collect teams ──────────────────────────────────────────
    result: Dict[str, dict] = {}

    for cr in char_rows:
        _, label_cells, char_portraits = _section_data(cr, rows, portrait_imgs, tc_ys)
        if not label_cells:
            continue

        char_name = cr["name"]

        if debug:
            print(f"  {char_name}: {len(char_portraits)} portrait imgs, "
                  f"{len(label_cells)} labels: "
                  f"{[lbl[:25] for _, lbl in label_cells]}")

        teams: List[dict] = []
        for ti, (lx, lbl) in enumerate(label_cells):
            next_lx = label_cells[ti + 1][0] if ti + 1 < len(label_cells) else TEAM_X_MAX + 1
            team_imgs = [p for p in char_portraits if lx <= p["x"] < next_lx]
            members: List[str] = []
            for p in team_imgs:
                char = src_to_char.get(p["src"])
                if char and char not in members:
                    members.append(char)
            teams.append({"label": lbl, "members": members,
                          "_imgs": [{"x": p["x"], "y": p["y"], "src": p["src"]}
                                    for p in team_imgs]})

        if teams:
            result[char_name] = {"teams": teams}

    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main_async(args):
    threshold = args.threshold

    print("=== Step 1: Download reference icons ===")
    char_icons = download_reference_icons()
    phash_db   = build_phash_db(char_icons)
    if not phash_db:
        sys.exit("No phash database — install imagehash and Pillow")

    from playwright.async_api import async_playwright
    gids = [args.tab] if args.tab else SHEET_GIDS

    # ── Pass 1: Build global token map (no image downloads) ───────────────────
    print("\n=== Step 2: Build global character token map ===")
    global_char_token: Dict[str, str] = {}  # char_name → base_token
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx  = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        for gid in gids:
            print(f"  Scanning gid={gid}...")
            tokens = await extract_tab_tokens(page, gid)
            print(f"    {len(tokens)} tokens extracted")
            global_char_token.update(tokens)
        await browser.close()

    global_token_to_char: Dict[str, str] = {tok: name
                                             for name, tok in global_char_token.items()}
    print(f"  Global token map: {len(global_token_to_char)} entries "
          f"({len(global_char_token)} characters)")

    # ── Pass 2: Scrape team comps with global token map ───────────────────────
    print("\n=== Step 3: Scrape team comp images ===")
    team_map: Dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx  = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        for gid in gids:
            print(f"\n  Loading gid={gid}...")
            tab_result = await load_sheet_teams(
                page, gid, phash_db, threshold, global_token_to_char, args.debug
            )
            print(f"  → {len(tab_result)} characters with team data")
            team_map.update(tab_result)

        await browser.close()

    if args.save_portraits:
        save_name = args.save_portraits
        save_dir  = f"/tmp/portraits_{save_name.replace(' ', '_')}"
        os.makedirs(save_dir, exist_ok=True)
        entry = team_map.get(save_name)
        if not entry:
            print(f"  '{save_name}' not found in team_map")
        else:
            async with async_playwright() as pw2:
                browser2 = await pw2.chromium.launch(headless=True)
                ctx2  = await browser2.new_context(viewport={"width": 1600, "height": 900})
                page2 = await ctx2.new_page()
                gid = args.tab or SHEET_GIDS[0]
                url = f"{SHEET_BASE}/pubhtml/sheet?headers=false&gid={gid}"
                await page2.goto(url, wait_until="networkidle", timeout=60000)
                await page2.wait_for_timeout(2000)
                for ti, team in enumerate(entry["teams"]):
                    for pi, img_info in enumerate(team.get("_imgs", [])):
                        resp = await page2.request.get(img_info["src"])
                        if resp.ok:
                            body = await resp.body()
                            fname = os.path.join(save_dir,
                                f"t{ti+1}_{pi+1}_x{img_info['x']}.png")
                            with open(fname, "wb") as fh2:
                                fh2.write(body)
                await browser2.close()
            print(f"  Saved portraits to {save_dir}/")
            for ti, team in enumerate(entry["teams"]):
                imgs = team.get("_imgs", [])
                print(f"  Team {ti+1} '{team['label']}': {len(imgs)} imgs → {team['members']}")
                for img_info in imgs:
                    print(f"    x={img_info['x']}  ...{img_info['src'][-30:]}")
        return

    print(f"\n=== Step 4: Write {OUTPUT} ===")
    # Strip _imgs before writing
    clean_map = {}
    for name, data in team_map.items():
        clean_map[name] = {"teams": [{"label": t["label"], "members": t["members"]}
                                      for t in data["teams"]]}
    # Apply manually verified overrides last
    for name, exact in _EXACT_OUTPUT.items():
        if name in clean_map:
            clean_map[name] = exact
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(clean_map, fh, indent=2, ensure_ascii=False)
    print(f"  Wrote {len(clean_map)} characters")

    print("\n=== Summary ===")
    for name, data in sorted(team_map.items()):
        for t in data["teams"]:
            members_str = ", ".join(t["members"]) or "(none matched)"
            print(f"  {name:42s}  [{t['label'][:30]:30s}]  {members_str}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--debug",          action="store_true")
    p.add_argument("--tab",            help="Only process this GID")
    p.add_argument("--threshold",      type=int, default=20,
                   help="phash match threshold (default 20)")
    p.add_argument("--save-portraits", metavar="CHARNAME",
                   help="Save portrait images for CHARNAME to /tmp/portraits_<name>/")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
