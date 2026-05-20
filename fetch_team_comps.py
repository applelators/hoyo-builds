#!/usr/bin/env python3
"""
Extract ZZZ team comp member characters from Google Sheets portrait images.
Matches 100×119px portrait images against wiki character icons via phash.
Output: team_map.json  { "CharName": {"teams": [{"label":"...", "members":[...]}]} }

Usage:
    python3 fetch_team_comps.py [--debug] [--tab GID] [--threshold N]
"""

import argparse
import asyncio
import io
import json
import os
import re
import requests
import sys
from typing import Dict, List, Optional, Tuple

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

ICONS_JSON   = "/Users/hokori/genshin-builds/icons.json"
ICON_CACHE   = "/Users/hokori/.cache/zzz_icons"
OUTPUT       = "/Users/hokori/genshin-builds/team_map.json"

# Portrait image size filter (pixels, at 1600px viewport)
IMG_W_MIN, IMG_W_MAX = 80,  125
IMG_H_MIN, IMG_H_MAX = 90,  145

# x-range of team comp portrait columns
TEAM_X_MIN = 200
TEAM_X_MAX = 1550

# x-range of team general / misc text (right side, not team comps)
TEAM_MISC_X = 1500

TEAMCOMP_GAP_MAX = 60


# ─── Reference icons ─────────────────────────────────────────────────────────

def download_reference_icons() -> Dict[str, bytes]:
    """Download and cache all ZZZ character icons from icons.json."""
    with open(ICONS_JSON) as f:
        all_icons = json.load(f)
    zzz_icons: Dict[str, str] = all_icons.get("zzz", {})

    os.makedirs(ICON_CACHE, exist_ok=True)
    result: Dict[str, bytes] = {}
    for char_name, url in zzz_icons.items():
        safe = re.sub(r"[^\w]", "_", char_name)
        cache_path = os.path.join(ICON_CACHE, f"{safe}.png")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as fh:
                result[char_name] = fh.read()
            continue
        try:
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                result[char_name] = resp.content
                with open(cache_path, "wb") as fh:
                    fh.write(resp.content)
            else:
                print(f"  WARN: {char_name}: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"  WARN: {char_name}: {exc}")
    print(f"  {len(result)} icons ready (cache: {ICON_CACHE})")
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


# ─── Playwright ───────────────────────────────────────────────────────────────

async def load_sheet_teams(page, gid: str,
                           phash_db: Dict[str, object],
                           threshold: int,
                           debug: bool = False) -> Dict[str, dict]:
    """
    Returns {char_name: {"teams": [{"label": str, "members": [str, ...]}]}}
    for all characters on this sheet tab.
    """
    url = f"{SHEET_BASE}/pubhtml/sheet?headers=false&gid={gid}"
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)

    # ── Scan all TR rows ──────────────────────────────────────────────────────
    rows = await page.evaluate(r"""() => {
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
    }""")

    # ── Scan all images ───────────────────────────────────────────────────────
    raw_imgs = await page.evaluate(r"""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const rect = img.getBoundingClientRect();
            results.push({
                src: img.src,
                alt: img.alt || '',
                x:   Math.round(rect.left),
                y:   Math.round(rect.top),
                w:   Math.round(rect.width),
                h:   Math.round(rect.height),
            });
        }
        return results;
    }""")

    # ── Identify character rows ───────────────────────────────────────────────
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

    char_rows = []
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

    if debug:
        print(f"  {len(char_rows)} characters: {[c['name'] for c in char_rows]}")

    # ── Find Team Comps sections ──────────────────────────────────────────────
    team_comp_label_ys: List[int] = [
        row["y"]
        for row in rows
        if any(c["text"].lower() == "team comps" for c in row["cells"])
    ]

    # ── Filter portrait-sized images in team comp x-range ────────────────────
    portrait_imgs = [
        img for img in raw_imgs
        if (IMG_W_MIN <= img["w"] <= IMG_W_MAX
            and IMG_H_MIN <= img["h"] <= IMG_H_MAX
            and TEAM_X_MIN <= img["x"] <= TEAM_X_MAX)
    ]

    # ── Download all unique portrait images via session ───────────────────────
    seen_srcs = {}
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

    # ── Match portraits to character names ────────────────────────────────────
    src_to_char: Dict[str, Optional[str]] = {}
    for src, data in seen_srcs.items():
        if data is None:
            src_to_char[src] = None
            continue
        name, dist = best_match(data, phash_db, threshold)
        src_to_char[src] = name
        if debug:
            tail = src.split("/")[-1][:30]
            print(f"    {tail} → {name!r} (dist={dist})")

    # ── Per-character: collect teams ──────────────────────────────────────────
    result: Dict[str, dict] = {}

    for cr in char_rows:
        char_name = cr["name"]
        y0, y1 = cr["y"], cr["next_y"]

        # Find this character's Team Comps label y
        tc_y = next((y for y in team_comp_label_ys if y0 <= y < y1), None)
        if tc_y is None:
            continue

        # Team label text cells (in row ≈ tc_y + 100..200)
        # They appear ~2 rows after the portrait image row
        team_label_cells: List[Tuple[int, str]] = []  # (x, label)
        for row in rows:
            if not (tc_y < row["y"] < y1):
                continue
            for cell in row["cells"]:
                if (TEAM_X_MIN <= cell["x"] <= TEAM_X_MAX
                        and cell["w"] >= 250
                        and cell["text"]
                        and cell["text"].lower() not in ("team comps",)):
                    team_label_cells.append((cell["x"], cell["text"]))
        team_label_cells.sort(key=lambda t: t[0])

        if not team_label_cells:
            continue

        # Portrait images belonging to this character's team comp section
        char_portraits = sorted(
            [img for img in portrait_imgs if tc_y < img["y"] < y1],
            key=lambda i: i["x"],
        )

        if debug:
            print(f"  {char_name}: {len(char_portraits)} portrait imgs, "
                  f"{len(team_label_cells)} labels: "
                  f"{[lbl[:25] for _, lbl in team_label_cells]}")

        # Group portraits into teams by label x boundaries
        # Each team's x range: [label_x, next_label_x)
        teams: List[dict] = []
        for ti, (lx, lbl) in enumerate(team_label_cells):
            next_lx = team_label_cells[ti + 1][0] if ti + 1 < len(team_label_cells) else TEAM_X_MAX + 1
            team_imgs = [p for p in char_portraits if lx <= p["x"] < next_lx]
            members: List[str] = []
            for p in team_imgs:
                char = src_to_char.get(p["src"])
                if char and char not in members:
                    members.append(char)
            teams.append({"label": lbl, "members": members})

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

    print("\n=== Step 2: Scrape team comp images ===")
    from playwright.async_api import async_playwright

    team_map: Dict[str, dict] = {}
    gids = [args.tab] if args.tab else SHEET_GIDS

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx  = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        for gid in gids:
            print(f"\n  Loading gid={gid}...")
            tab_result = await load_sheet_teams(
                page, gid, phash_db, threshold, args.debug
            )
            print(f"  → {len(tab_result)} characters with team data")
            team_map.update(tab_result)

        await browser.close()

    print(f"\n=== Step 3: Write {OUTPUT} ===")
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(team_map, fh, indent=2, ensure_ascii=False)
    print(f"  Wrote {len(team_map)} characters")

    print("\n=== Summary ===")
    for name, data in sorted(team_map.items()):
        for t in data["teams"]:
            members_str = ", ".join(t["members"]) or "(none matched)"
            print(f"  {name:42s}  [{t['label'][:30]:30s}]  {members_str}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--debug",     action="store_true")
    p.add_argument("--tab",       help="Only process this GID")
    p.add_argument("--threshold", type=int, default=12,
                   help="phash match threshold (default 12)")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
