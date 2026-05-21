#!/usr/bin/env python3
"""
Identify ZZZ disc set images from the Google Sheets spreadsheet.

Core algorithm:
  For each unique image token T that appears in the 4pc disc column:
    chars_with_T = all characters on the spreadsheet that have image T
    for each char in chars_with_T, get their TEXT-EXTRACTED disc sets (no overrides)
    intersection = set.intersection of all non-empty text-disc sets
    if |intersection| == 1  →  T maps to that one disc set name

Output: disc_map.json  { "Character Name": {"4pc": [...], "2pc": [...]} }

Usage:
    python3 fetch_disc_images.py [--debug] [--tab GID]
"""

import argparse
import asyncio
import base64
import glob
import csv
import io
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple, Set

sys.path.insert(0, os.path.dirname(__file__))
from parse_zzz import (
    parse_block, pad,
    CACHE_DIR as ZZZ_CSV_DIR,
    SKIP_NAMES, HEADER_VALS,
)

OUTPUT             = "/Users/hokori/genshin-builds/disc_map.json"
VISION_CACHE_PATH  = "/Users/hokori/genshin-builds/vision_cache.json"

SHEET_BASE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTj2PaPq6Py_1B5fsOPj_Moc-tN_7mut7fICczI6lz1njyEIAInTnfB7lAraX4pYCRGNbaHGlIbFZ90"
SHEET_GIDS = [
    "571511473",
    "1270581085",
    "897804407",
    "622827842",
    "1395442363",
]

# X ranges for disc-set columns (1600px wide viewport)
DISC_4PC_X_MIN = 680
DISC_4PC_X_MAX = 1150
DISC_2PC_X_MIN = 1150
DISC_2PC_X_MAX = 1500

# Max gap between a team-comp label and the following real character name
TEAMCOMP_GAP_MAX = 60


# ─── Text bootstrap ─────────────────────────────────────────────────────────────
# Disc set names mentioned in disc_notes/w_engine_notes/other_notes are used as
# noisy seeds for the intersection algorithm.  The intersection naturally filters
# out irrelevant mentions (only a name present in ALL characters that share a
# token survives).  Known-correct characters override the noisy text seeds.

_KNOWN_DISC_SETS = list(json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "disc_icons.json"))
).keys())

# Confirmed correct disc sets (user-verified) — flat lists for intersection input.
_EXACT_SEEDS: Dict[str, Dict[str, List[str]]] = {
    "Sunna": {
        "4pc": ["Moonlight Lullaby"],
        "2pc": ["Swing Jazz", "King of the Summit", "Shockstar Disco"],
    },
    "Aria": {
        "4pc": ["Phaethon's Melody", "Shining Aria"],
        "2pc": ["Phaethon's Melody", "Chaos Jazz", "Freedom Blues",
                "Shining Aria", "Chaotic Metal", "Puffer Electro"],
    },
}

# Final output overrides (with correct nested pair structure for 2pc).
# These are written directly to disc_map after token resolution.
_EXACT_OUTPUT: Dict[str, Dict] = {
    "Sunna": {
        "4pc": ["Moonlight Lullaby"],
        "2pc": ["Swing Jazz", ["King of the Summit", "Shockstar Disco"]],
    },
    "Aria": {
        "4pc": ["Phaethon's Melody", "Shining Aria"],
        "2pc": ["Phaethon's Melody", ["Chaos Jazz", "Freedom Blues"],
                ["Shining Aria", "Chaotic Metal"], "Puffer Electro"],
    },
}


def raw_disc_sets_from_csvs() -> Dict[str, Dict[str, List[str]]]:
    """Return rough per-character disc set candidates from CSV text notes."""
    result: Dict[str, Dict[str, List[str]]] = {}
    for f in sorted(glob.glob(f"{ZZZ_CSV_DIR}/agents_*.csv")):
        try:
            for agent in parse_block_from_file(f):
                name = agent["name"]
                text = " ".join([
                    agent.get("disc_notes", ""),
                    agent.get("w_engine_notes", ""),
                    agent.get("other_notes", ""),
                ])
                mentioned = [ds for ds in _KNOWN_DISC_SETS if ds in text]
                if mentioned:
                    result[name] = {"4pc": mentioned, "2pc": mentioned}
        except Exception:
            pass

    # Override with confirmed exact seeds.
    result.update(_EXACT_SEEDS)
    return result


def parse_block_from_file(filepath: str):
    """Yield parsed character dicts from a single CSV (builds[0] fields)."""
    with open(filepath, newline="", encoding="utf-8") as fh:
        all_rows = list(csv.reader(fh))
    char_starts = [i for i in range(len(all_rows)) if _is_char_header(all_rows, i)]
    for ci, start in enumerate(char_starts):
        end = char_starts[ci + 1] if ci + 1 < len(char_starts) else len(all_rows)
        block = parse_block(all_rows[start:end])
        if block:
            yield {
                "name":           block["name"],
                "disc_notes":     block["builds"][0]["disc_notes"],
                "w_engine_notes": block["builds"][0]["w_engine_notes"],
                "other_notes":    block["builds"][0]["other_notes"],
            }


def _is_char_header(rows, i):
    row = rows[i]
    non_empty = [(j, c.strip()) for j, c in enumerate(row) if c.strip()]
    if len(non_empty) != 1 or non_empty[0][0] != 1:
        return False
    name = non_empty[0][1]
    if name in SKIP_NAMES or name.lower().startswith("last updated"):
        return False
    if len(name) < 2:
        return False
    if i + 1 < len(rows):
        nxt = rows[i + 1]
        nxt_val = nxt[1].strip() if len(nxt) > 1 else ""
        if nxt_val.lower().startswith("last updated"):
            return True
    return False


# ─── Playwright helpers ──────────────────────────────────────────────────────────

def url_token(url: str) -> str:
    m = re.search(r"sheets-images-rt/([A-Za-z0-9_\-]+)", url)
    return m.group(1) if m else url


async def load_sheet(page, gid: str, debug: bool = False) -> Tuple[List[dict], List[dict]]:
    """
    Returns:
      char_rows  — [{name, y, next_y}, ...]
      disc_imgs  — [{url, token, col ("4pc"|"2pc"), y, x, w, h}, ...]

    The 4pc/2pc column is determined by each image's y-position relative to the
    per-character "4 Piece Drive Disc Set" / "2 Piece Drive Disc Set" header rows,
    NOT by x-position (both columns share the same x area).
    """
    url = f"{SHEET_BASE}/pubhtml/sheet?headers=false&gid={gid}"
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)

    # ── TR/TD scan ───────────────────────────────────────────────────────────────
    rows = await page.evaluate(r"""
    () => {
        const result = [];
        for (const tr of document.querySelectorAll('tr')) {
            const trRect = tr.getBoundingClientRect();
            const cells = [];
            for (const td of tr.querySelectorAll('td')) {
                const text = td.innerText.trim();
                const rect = td.getBoundingClientRect();
                cells.push({text, x: Math.round(rect.left), w: Math.round(rect.width)});
            }
            result.push({y: Math.round(trRect.top), h: Math.round(trRect.height), cells});
        }
        return result;
    }
    """)

    # ── Character detection ───────────────────────────────────────────────────────
    lu_ys = {r["y"] for r in rows
             if any("last updated" in c["text"].lower() for c in r["cells"])}

    SKIP_NAMES_HTML = {"S Rank Agents", "A Rank Agents", "S Rank", "A Rank",
                       "Equipment", "Role", "Ability Priority", "W-Engines",
                       "Drive Disc Stats", "Team Comps"}

    candidates = []
    for row in rows:
        left_cells = [c for c in row["cells"] if c["text"] and c["x"] < 250]
        if len(left_cells) != 1:
            continue
        name = left_cells[0]["text"]
        if name.lower().startswith("last updated") or len(name) < 2:
            continue
        if name in SKIP_NAMES_HTML:
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
        print(f"  Characters ({len(char_rows)}): {[c['name'] for c in char_rows]}")

    # ── Collect "4 Piece" and "2 Piece" header y-positions for each character ────
    # These appear as text cells at x≈719 within the character's y-range.
    # Each character has exactly one pair; use them to classify disc images.
    header_4pc_ys: List[int] = []  # sorted list of all "4 Piece" header y values
    header_2pc_ys: List[int] = []

    for row in rows:
        for cell in row["cells"]:
            t = cell["text"].lower()
            if "4 piece drive disc" in t or "4 piece disc" in t:
                header_4pc_ys.append(row["y"])
            elif "2 piece drive disc" in t or "2 piece disc" in t:
                header_2pc_ys.append(row["y"])

    # For each character, find their 4pc and 2pc header y values
    for cr in char_rows:
        y0, y1 = cr["y"], cr["next_y"]
        h4 = [h for h in header_4pc_ys if y0 <= h < y1]
        h2 = [h for h in header_2pc_ys if y0 <= h < y1]
        cr["h4pc_y"] = min(h4) if h4 else None
        cr["h2pc_y"] = min(h2) if h2 else None

    # ── Image scan ───────────────────────────────────────────────────────────────
    raw_imgs = await page.evaluate(r"""
    () => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const rect = img.getBoundingClientRect();
            if (rect.width < 50 || rect.height < 50) continue;
            if (rect.width > 500 || rect.height > 500) continue;
            results.push({
                url: img.src,
                x:   Math.round(rect.left),
                y:   Math.round(rect.top),
                w:   Math.round(rect.width),
                h:   Math.round(rect.height),
            });
        }
        return results;
    }
    """)

    # Disc-column x-range: the main disc set area (ignore portraits, ability icons, etc.)
    DISC_X_MIN = 650
    DISC_X_MAX = 1200

    # Classify each image as 4pc, 2pc, or skip
    disc_imgs = []
    for img in raw_imgs:
        img_cx = img["x"] + img["w"] / 2
        if not (DISC_X_MIN <= img_cx <= DISC_X_MAX):
            continue
        img_yc = img["y"] + img["h"] / 2

        # Find which character this image belongs to
        for cr in char_rows:
            y0, y1 = cr["y"], cr["next_y"]
            if not (y0 <= img_yc < y1):
                continue
            h4 = cr["h4pc_y"]
            h2 = cr["h2pc_y"]
            if h4 is None:
                break

            # 4pc: image y is between h4pc header and h2pc header
            if h2 is not None and h4 < img["y"] < h2:
                disc_imgs.append({**img, "col": "4pc", "token": url_token(img["url"])})
            elif h2 is not None and img["y"] >= h2:
                # 2pc: image y is after h2pc header but before next character
                disc_imgs.append({**img, "col": "2pc", "token": url_token(img["url"])})
            break  # each image belongs to at most one character

    if debug:
        print(f"  Section headers: {len(header_4pc_ys)} 4pc, {len(header_2pc_ys)} 2pc")
        print(f"  Disc images (classified): {len(disc_imgs)}")

    return char_rows, disc_imgs


async def collect_all_images(
    gids: List[str], debug: bool = False
) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, bytes]]:
    """
    Returns:
      all_char_tokens  — {char_name: {"4pc": [token,...], "2pc": [token,...]}}
      token_to_bytes   — {token: image_bytes} for every unique disc image token
    """
    from playwright.async_api import async_playwright

    all_char_tokens: Dict[str, Dict[str, List[str]]] = {}
    token_to_url:   Dict[str, str] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx    = await browser.new_context(viewport={"width": 1600, "height": 900})
        page   = await ctx.new_page()

        for gid in gids:
            print(f"  Loading gid={gid}...")
            char_rows, disc_imgs = await load_sheet(page, gid, debug)
            print(f"  → {len(char_rows)} characters, {len(disc_imgs)} disc-column images")

            for img in disc_imgs:
                token_to_url[img["token"]] = img["url"]

            for cr in char_rows:
                name = cr["name"]
                y0, y1 = cr["y"], cr["next_y"]
                tokens_4pc: List[str] = []
                tokens_2pc: List[str] = []

                for img in disc_imgs:
                    yc = img["y"] + img["h"] / 2
                    if y0 <= yc < y1:
                        col_list = tokens_4pc if img["col"] == "4pc" else tokens_2pc
                        if img["token"] not in col_list:
                            col_list.append(img["token"])

                all_char_tokens[name] = {"4pc": tokens_4pc, "2pc": tokens_2pc}

        # Download all unique images while we still have a session
        print(f"  Downloading {len(token_to_url)} unique disc images...")
        token_to_bytes: Dict[str, bytes] = {}
        for tok, url in token_to_url.items():
            try:
                resp = await page.request.get(url)
                if resp.ok:
                    token_to_bytes[tok] = await resp.body()
            except Exception:
                pass
        print(f"  Downloaded {len(token_to_bytes)} images")

        await browser.close()

    return all_char_tokens, token_to_bytes


# ─── Intersection algorithm ───────────────────────────────────────────────────────

def build_token_map(
    all_char_tokens: Dict[str, Dict[str, List[str]]],
    raw_text_disc:   Dict[str, Dict[str, List[str]]],
    debug:           bool = False,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    For each image token, compute intersection of text-disc sets across all characters
    that have that token. If intersection is exactly 1 disc set → that's the mapping.

    Returns (token_to_4pc, token_to_2pc).
    """
    # Collect all tokens
    all_4pc_tokens: Set[str] = set()
    all_2pc_tokens: Set[str] = set()
    for char_data in all_char_tokens.values():
        all_4pc_tokens.update(char_data["4pc"])
        all_2pc_tokens.update(char_data["2pc"])

    token_to_4pc: Dict[str, str] = {}
    token_to_2pc: Dict[str, str] = {}

    for col, all_tokens, bucket in [
        ("4pc", all_4pc_tokens, token_to_4pc),
        ("2pc", all_2pc_tokens, token_to_2pc),
    ]:
        for tok in all_tokens:
            # Find all chars with this token
            chars_with_tok = [
                name for name, data in all_char_tokens.items()
                if tok in data[col]
            ]
            # Get text disc sets for those chars (non-empty only)
            text_sets = [
                set(raw_text_disc[name][col])
                for name in chars_with_tok
                if name in raw_text_disc and raw_text_disc[name][col]
            ]
            if not text_sets:
                continue

            intersection = set.intersection(*text_sets)
            if len(intersection) == 1:
                disc_name = next(iter(intersection))
                bucket[tok] = disc_name
                if debug:
                    print(f"  [{col}] {tok[:22]}... → {disc_name!r}  ({len(chars_with_tok)} chars)")
            elif debug and len(intersection) > 1:
                print(f"  [{col}] {tok[:22]}... → ambiguous: {intersection}  ({len(chars_with_tok)} chars)")

    return token_to_4pc, token_to_2pc


def _load_vision_cache() -> Dict[str, str]:
    if os.path.exists(VISION_CACHE_PATH):
        with open(VISION_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_vision_cache(cache: Dict[str, str]) -> None:
    with open(VISION_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def resolve_via_vision(
    token_to_bytes: Dict[str, bytes],
    unresolved:     Set[str],
    known_disc_sets: List[str],
    debug: bool = False,
) -> Dict[str, str]:
    """
    Identify disc sets for unresolved tokens using Claude vision.

    Sends each unknown spreadsheet icon alongside all reference icons from
    disc_icons/ and asks Claude to match by visual design.  Results are cached
    in vision_cache.json so repeated runs pay no API cost for already-seen tokens.

    Returns {token: disc_set_name} for every token that was successfully identified.
    Tokens whose images are not disc icons (e.g. character portraits that leaked
    into the disc column) will return no entry — Claude's response won't match any
    known disc set name and is silently dropped.
    """
    try:
        import anthropic
    except ImportError:
        print("  [vision] anthropic package not available — skipping")
        return {}

    cache = _load_vision_cache()

    result: Dict[str, str] = {}
    uncached: List[str] = []
    for tok in unresolved:
        if tok in cache:
            result[tok] = cache[tok]
            if debug:
                print(f"  [vision-cache] {tok[:22]}... → {cache[tok]!r}")
        elif tok in token_to_bytes:
            uncached.append(tok)

    if not uncached:
        return result

    # Load reference icons once
    ref_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disc_icons")
    ref_content: List[dict] = []
    valid_names: List[str] = []
    for disc_name in sorted(known_disc_sets):
        path = os.path.join(ref_dir, f"{disc_name}.png")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            b64 = base64.standard_b64encode(fh.read()).decode()
        ref_content.append({"type": "text", "text": f"• {disc_name}"})
        ref_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
        valid_names.append(disc_name)

    client = anthropic.Anthropic()
    print(f"  [vision] identifying {len(uncached)} tokens via Claude vision "
          f"({len(cache)} already cached)...")

    for tok in uncached:
        content: List[dict] = [
            {
                "type": "text",
                "text": (
                    "Below is a ZZZ (Zenless Zone Zero) drive disc set icon taken from a "
                    "Google Sheets spreadsheet. It may look slightly different from the "
                    "reference icons (different render style, smaller size) but the colour "
                    "scheme and overall design pattern should match one of them.\n\n"
                    "Unknown icon:"
                ),
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(token_to_bytes[tok]).decode(),
                },
            },
            {"type": "text", "text": "\nReference disc set icons (name then icon):\n"},
        ] + ref_content + [
            {
                "type": "text",
                "text": (
                    "\nReply with ONLY the exact name of the matching disc set from the "
                    "reference list. No other text."
                ),
            },
        ]

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=32,
                messages=[{"role": "user", "content": content}],
            )
            name = response.content[0].text.strip().rstrip(".")
            if name in valid_names:
                result[tok] = name
                cache[tok] = name
                _save_vision_cache(cache)
                if debug:
                    print(f"  [vision] {tok[:22]}... → {name!r}")
            elif debug:
                print(f"  [vision] {tok[:22]}... → not a disc icon ({name!r} — skipped)")
        except Exception as exc:
            print(f"  [vision] error for {tok[:22]}: {exc}")


def apply_token_map(
    char_name:    str,
    tokens:       Dict[str, List[str]],
    token_to_4pc: Dict[str, str],
    token_to_2pc: Dict[str, str],
) -> Dict[str, List[str]]:
    resolved_4pc = []
    resolved_2pc = []
    unresolved_4pc = []
    unresolved_2pc = []

    for col, resolved, unresolved, bucket in [
        ("4pc", resolved_4pc, unresolved_4pc, token_to_4pc),
        ("2pc", resolved_2pc, unresolved_2pc, token_to_2pc),
    ]:
        for tok in tokens[col]:
            if tok in bucket:
                name = bucket[tok]
                if name not in resolved:
                    resolved.append(name)
            else:
                unresolved.append(tok[:20])

    return {"4pc": resolved_4pc, "2pc": resolved_2pc,
            "_unresolved_4pc": unresolved_4pc, "_unresolved_2pc": unresolved_2pc}


# ─── Main ────────────────────────────────────────────────────────────────────────

async def main_async(args):
    print("=== Step 1: Parse raw text disc sets from CSVs (no overrides) ===")
    raw_text_disc = raw_disc_sets_from_csvs()
    # Summary
    non_empty_4pc = sum(1 for v in raw_text_disc.values() if v["4pc"])
    print(f"  {len(raw_text_disc)} characters, {non_empty_4pc} with non-empty 4pc text sets")

    if args.debug:
        for name, d in sorted(raw_text_disc.items()):
            if d["4pc"]:
                print(f"  {name}: 4pc={d['4pc']}")

    print("\n=== Step 2: Collect disc images from spreadsheet ===")
    gids = [args.tab] if args.tab else SHEET_GIDS
    all_char_tokens, token_to_bytes = await collect_all_images(gids, args.debug)
    print(f"  {len(all_char_tokens)} characters found across tabs")

    print("\n=== Step 3: Build token→disc_set map via intersection ===")
    token_to_4pc, token_to_2pc = build_token_map(
        all_char_tokens, raw_text_disc, args.debug
    )
    print(f"  Mapped: {len(token_to_4pc)} 4pc tokens, {len(token_to_2pc)} 2pc tokens")

    print("\n=== Step 3b: Resolve remaining tokens via Claude vision ===")
    all_4pc_tokens: Set[str] = set()
    all_2pc_tokens: Set[str] = set()
    for char_data in all_char_tokens.values():
        all_4pc_tokens.update(char_data["4pc"])
        all_2pc_tokens.update(char_data["2pc"])

    unresolved = (all_4pc_tokens | all_2pc_tokens) - set(token_to_4pc) - set(token_to_2pc)
    vision_map = resolve_via_vision(token_to_bytes, unresolved, _KNOWN_DISC_SETS, args.debug)

    new_4pc = {t: v for t, v in vision_map.items() if t in all_4pc_tokens and t not in token_to_4pc}
    new_2pc = {t: v for t, v in vision_map.items() if t in all_2pc_tokens and t not in token_to_2pc}
    token_to_4pc.update(new_4pc)
    token_to_2pc.update(new_2pc)
    print(f"  Added {len(new_4pc)} 4pc, {len(new_2pc)} 2pc via vision → "
          f"total {len(token_to_4pc)} 4pc, {len(token_to_2pc)} 2pc")

    # Save images for inspection if requested
    if getattr(args, "save_images", None):
        save_dir = args.save_images
        os.makedirs(save_dir, exist_ok=True)
        # Build reverse map: token → disc set name (from both intersection + vision)
        tok_label = {}
        for tok, name in token_to_4pc.items():
            tok_label[tok] = f"4pc_{name}"
        for tok, name in token_to_2pc.items():
            tok_label.setdefault(tok, f"2pc_{name}")
        for tok, data in token_to_bytes.items():
            label = tok_label.get(tok, "unknown")
            fname = os.path.join(save_dir, f"{label[:40]}_{tok[:16]}.png")
            with open(fname, "wb") as fh:
                fh.write(data)
        print(f"  Saved {len(token_to_bytes)} images to {save_dir}")

    print("\n=== Step 4: Apply map to all characters ===")

    disc_map: Dict[str, Dict[str, List[str]]] = {}
    unresolved_chars = []

    for char_name, tokens in all_char_tokens.items():
        result = apply_token_map(char_name, tokens, token_to_4pc, token_to_2pc)
        disc_map[char_name] = {"4pc": result["4pc"], "2pc": result["2pc"]}

        if result["_unresolved_4pc"] or result["_unresolved_2pc"]:
            unresolved_chars.append({
                "name": char_name,
                "unresolved_4pc": result["_unresolved_4pc"],
                "unresolved_2pc": result["_unresolved_2pc"],
            })

    # Apply exact overrides last — guaranteed correct regardless of resolution results.
    for char_name, exact in _EXACT_OUTPUT.items():
        if char_name in disc_map:
            disc_map[char_name] = {"4pc": exact["4pc"], "2pc": exact["2pc"]}

    with open(OUTPUT, "w") as f:
        json.dump(disc_map, f, indent=2, ensure_ascii=False)
    print(f"  Wrote disc_map.json with {len(disc_map)} characters.")

    if unresolved_chars:
        print("\n=== Characters with unresolved tokens ===")
        for c in unresolved_chars:
            print(f"  {c['name']}: unr4={c['unresolved_4pc']}  unr2={c['unresolved_2pc']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--tab", help="Only process this GID")
    parser.add_argument("--save-images", metavar="DIR",
                        help="Save all downloaded token images to DIR for inspection")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
