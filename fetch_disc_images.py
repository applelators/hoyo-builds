#!/usr/bin/env python3
"""
Identify ZZZ disc set images from the Google Sheets spreadsheet via Claude vision.

For each unique image token found in the disc columns, the image is sent to
Claude alongside reference icons from disc_icons/ for visual identification.
Results are cached in vision_cache.json so re-runs pay no API cost.

Output: disc_map.json  { "Character Name": {"4pc": [...], "2pc": [...]} }

Usage:
    python3 fetch_disc_images.py [--debug] [--tab GID]
"""

import argparse
import asyncio
import base64
import io
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple, Set

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


_KNOWN_DISC_SETS = list(json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "disc_icons.json"))
).keys())

# User-verified overrides written directly to disc_map after vision resolution.
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
    "Promeia": {
        "4pc": ["Notes From the Chained"],
        "2pc": ["Phaethon's Melody"],
    },
}


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

    return result


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
    print("=== Step 1: Collect disc images from spreadsheet ===")
    gids = [args.tab] if args.tab else SHEET_GIDS
    all_char_tokens, token_to_bytes = await collect_all_images(gids, args.debug)
    print(f"  {len(all_char_tokens)} characters found across tabs")

    print("\n=== Step 2: Identify disc sets via Claude vision ===")
    all_4pc_tokens: Set[str] = set()
    all_2pc_tokens: Set[str] = set()
    for char_data in all_char_tokens.values():
        all_4pc_tokens.update(char_data["4pc"])
        all_2pc_tokens.update(char_data["2pc"])

    vision_map = resolve_via_vision(
        token_to_bytes, all_4pc_tokens | all_2pc_tokens, _KNOWN_DISC_SETS, args.debug
    )
    token_to_4pc = {t: v for t, v in vision_map.items() if t in all_4pc_tokens}
    token_to_2pc = {t: v for t, v in vision_map.items() if t in all_2pc_tokens}
    print(f"  Identified {len(token_to_4pc)} 4pc tokens, {len(token_to_2pc)} 2pc tokens")

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
