#!/usr/bin/env python3
"""
Scrape tier list data from prydwen.gg for GI, HSR, and ZZZ.
Output: tiers.json  { "gi": {charName: tier}, "hsr": {...}, "zzz": {...} }

Names are stored exactly as prydwen.gg displays them.
Mapping from internal names is handled in app.js (PRYDWEN_NAME_MAP).

Usage:
    python3 fetch_tiers.py              # all games
    python3 fetch_tiers.py --game zzz   # one game
"""

import argparse
import asyncio
import json
import os
from typing import Dict

OUTPUT = "/Users/hokori/genshin-builds/tiers.json"

GAME_URLS = {
    "gi":  "https://www.prydwen.gg/genshin/tier-list",
    "hsr": "https://www.prydwen.gg/star-rail/tier-list",
    "zzz": "https://www.prydwen.gg/zenless/tier-list",
}

GAME_PATH_FRAGMENTS = {
    "gi":  "/genshin/characters/",
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
        ctx  = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        result = dict(existing)

        for game in games:
            print(f"\n=== {game.upper()} ===")
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
