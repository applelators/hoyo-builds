#!/usr/bin/env python3
"""
Scrape tier list data for GI (Game8), HSR, and ZZZ (prydwen.gg).
Output: tiers.json  { "gi": {charName: tier}, "hsr": {...}, "zzz": {...} }

GI:  game8.co — SS/S/A/B/C/D tiers, names in Game8 title-case
HSR/ZZZ: prydwen.gg — T0/T0.5/T1/T1.5/T2/T3/T4 tiers

Names are stored exactly as the source displays them.

Usage:
    python3 fetch_tiers.py              # all games
    python3 fetch_tiers.py --game gi    # one game
"""

import argparse
import asyncio
import json
import os
from typing import Dict

OUTPUT = "/Users/hokori/genshin-builds/tiers.json"

# GI uses Game8 (prydwen doesn't cover GI)
# Update GAME8_GI_URL each major GI patch when Game8 publishes a new tier list article
GAME8_GI_URL = "https://game8.co/games/Genshin-Impact/archives/297465"

GAME_URLS = {
    "hsr": "https://www.prydwen.gg/star-rail/tier-list",
    "zzz": "https://www.prydwen.gg/zenless/tier-list",
}

GAME_PATH_FRAGMENTS = {
    "hsr": "/star-rail/characters/",
    "zzz": "/zenless/characters/",
}

# Walks up from each character link to find the tier label sibling.
_EXTRACT_JS = """
(pathFragment) => {
    const result = {};
    const TIER_RE = /^T(0\\+?|0\\.5|1\\+?|1\\.5|2|3|4)$/;

    const charLinks = Array.from(document.querySelectorAll(
        `a[href*="${pathFragment}"]`
    ));

    charLinks.forEach(link => {
        let el = link;
        let tier = null;

        for (let depth = 0; depth < 20 && !tier; depth++) {
            if (!el.parentElement) break;
            el = el.parentElement;
            for (const sibling of (el.parentElement?.children || [])) {
                if (sibling === el) continue;
                const text = (sibling.textContent || '').trim();
                if (TIER_RE.test(text)) { tier = text; break; }
            }
        }

        if (!tier) return;

        const nameImg = link.querySelector('img[data-main-image]');
        const raw = (
            (nameImg ? nameImg.getAttribute('alt') : null) ||
            link.getAttribute('aria-label') ||
            ''
        ).trim().replace(/\\s+/g, ' ');

        if (raw && raw.length > 0 && raw.length < 50 && !TIER_RE.test(raw)) {
            result[raw] = tier;
        }
    });

    return result;
}
"""


# Game8 GI extraction: finds the active tab's tier table, iterates rows top-to-bottom,
# extracts character names from img alt "Genshin - {Name} {Role} Rank".
# First occurrence wins → best tier for characters listed under multiple roles.
# Tier label is detected from the first cell's img alt (e.g. "SS Tier", "S Tier").
_EXTRACT_GAME8_JS = """
() => {
    const result = {};
    const NAME_RE = /^Genshin\\s*-\\s*(.+?)\\s+(?:Main\\s+DPS|DPS|Sub-DPS|Support)\\s+Rank\\s*$/i;
    const TIER_IMG_RE = /^(SS|S|A|B|C|D)\\s+Tier$/;

    const activePanel = document.querySelector('.a-tabPanel.is-active');
    const tables = Array.from((activePanel || document).querySelectorAll('table.a-table.a-table.a-table'));
    const table = tables[0];
    if (!table) return {};

    let currentTier = null;
    Array.from(table.querySelectorAll('tr')).forEach(row => {
        const firstCell = row.querySelector('td, th');
        if (firstCell) {
            const tierImg = firstCell.querySelector('img');
            if (tierImg) {
                const m = tierImg.alt.match(TIER_IMG_RE);
                if (m) currentTier = m[1];
            }
        }
        if (!currentTier) return;
        row.querySelectorAll('img[alt*="Genshin - "]').forEach(img => {
            const m = img.alt.match(NAME_RE);
            if (!m) return;
            const name = m[1].trim();
            if (name && !result[name]) result[name] = currentTier;
        });
    });
    return result;
}
"""


async def scrape_game_game8(page) -> Dict[str, str]:
    print(f"  Loading {GAME8_GI_URL}...")
    try:
        await page.goto(GAME8_GI_URL, wait_until="load", timeout=90000)
        await page.wait_for_timeout(5000)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {}

    tier_map: Dict[str, str] = await page.evaluate(_EXTRACT_GAME8_JS)

    if not tier_map:
        print("  WARNING: no tier data extracted — page structure may have changed")
        return {}

    print(f"  {len(tier_map)} characters extracted")
    sample = list(tier_map.items())[:6]
    for name, tier in sample:
        print(f"    {tier:4s}  {name}")
    if len(tier_map) > 6:
        print(f"    ... ({len(tier_map) - 6} more)")
    return tier_map


async def scrape_game(page, game: str) -> Dict[str, str]:
    url = GAME_URLS[game]
    path_fragment = GAME_PATH_FRAGMENTS[game]

    print(f"  Loading {url}...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {}

    tier_map: Dict[str, str] = await page.evaluate(_EXTRACT_JS, path_fragment)

    if not tier_map:
        print(f"  WARNING: no tier data extracted — page structure may have changed")
        return {}

    print(f"  {len(tier_map)} characters extracted")
    sample = list(tier_map.items())[:6]
    for name, tier in sample:
        print(f"    {tier:4s}  {name}")
    if len(tier_map) > 6:
        print(f"    ... ({len(tier_map) - 6} more)")
    return tier_map


async def main_async(games: list) -> None:
    from playwright.async_api import async_playwright

    existing: Dict = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            existing = json.load(f)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx  = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()

        result = dict(existing)

        for game in games:
            print(f"\n=== {game.upper()} ===")
            if game == 'gi':
                tier_map = await scrape_game_game8(page)
            else:
                tier_map = await scrape_game(page, game)
            if tier_map:
                result[game] = tier_map
            else:
                print(f"  Keeping existing data for {game}")

        await browser.close()

    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {OUTPUT}")
    for game in games:
        print(f"  {game}: {len(result.get(game, {}))} characters")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", choices=["gi", "hsr", "zzz"])
    args = parser.parse_args()
    games = [args.game] if args.game else ["gi", "hsr", "zzz"]
    asyncio.run(main_async(games))


if __name__ == "__main__":
    main()
