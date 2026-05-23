"""Fetch upcoming version livestream dates from each game's Game8 wiki.

Outputs to livestreams.json. Run when a new patch livestream is announced.

Strategy:
- Load each game's wiki home page with Playwright.
- Find the "X.Y Livestream" link in the top navigation.
- Load that page and extract the release date + per-server times table.
- Manual `highlights` and `title` fields are preserved across runs.

Update NEXT_VERSION each patch cycle.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

OUTPUT = Path(__file__).parent / "livestreams.json"

GAME_HOMES = {
    "gi":  "https://game8.co/games/Genshin-Impact",
    "hsr": "https://game8.co/games/Honkai-Star-Rail",
    "zzz": "https://game8.co/games/Zenless-Zone-Zero",
}

# Bump these when a new version cycle begins.
NEXT_VERSION = {
    "gi":  "6.7",
    "hsr": "4.3",
    "zzz": "3.0",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# JS: find the X.Y Livestream link on the game home page
_FIND_LS_LINK_JS = """
(ver) => {
    var anchors = document.querySelectorAll('a');
    for (var i = 0; i < anchors.length; i++) {
        var t = (anchors[i].innerText || '').trim();
        var h = anchors[i].href || '';
        if (h.includes('game8.co') && t.indexOf(ver) >= 0 && t.toLowerCase().indexOf('livestream') >= 0) {
            return h;
        }
    }
    return null;
}
"""

# JS: extract release date from Game8 livestream page table
_EXTRACT_DATE_JS = """
() => {
    var DATE_LABELS = /Release\\s*Date|Livestream\\s*Date/i;
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var rows = tables[i].querySelectorAll('tr');
        for (var j = 0; j < rows.length; j++) {
            var cells = rows[j].querySelectorAll('td, th');
            if (cells.length < 2) continue;
            if (DATE_LABELS.test(cells[0].innerText)) {
                return cells[1].innerText.trim();
            }
        }
    }
    // Fallback: look for "North America | <date>" row
    var tables2 = document.querySelectorAll('table');
    for (var i = 0; i < tables2.length; i++) {
        var rows2 = tables2[i].querySelectorAll('tr');
        for (var j = 0; j < rows2.length; j++) {
            var cells2 = rows2[j].querySelectorAll('td, th');
            if (cells2.length >= 2 && /North America/i.test(cells2[0].innerText)) {
                return cells2[1].innerText.trim();
            }
        }
    }
    return null;
}
"""


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def parse_datetime(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip()
    # Strip trailing countdown text
    s = re.split(r"\s+(?:UTC|GMT)", s)[0].strip()
    fmts = [
        "%B %d, %Y at %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y, %H:%M",
        "%B %d, %Y %H:%M",
        "%B %d, %Y",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


async def scrape_game(page, game: str, ver: str) -> str | None:
    home = GAME_HOMES[game]
    print(f"  [{game}] looking for v{ver} livestream link on {home}")
    try:
        await page.goto(home, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        ls_url = await page.evaluate(_FIND_LS_LINK_JS, ver)
        if not ls_url:
            print(f"  [{game}] no v{ver} livestream link found on home page")
            return None

        print(f"  [{game}] found livestream page: {ls_url}")
        await page.goto(ls_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        date_text = await page.evaluate(_EXTRACT_DATE_JS)
        if not date_text:
            print(f"  [{game}] no date found on livestream page")
            return None

        iso = parse_datetime(date_text)
        if not iso:
            print(f"  [{game}] could not parse date: {date_text!r}")
            return None

        print(f"  [{game}] v{ver} livestream: {iso}")
        return iso

    except Exception as e:
        print(f"  [{game}] ERROR: {e}")
        return None


async def main_async() -> None:
    data = load_existing()

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=UA,
        )
        page = await ctx.new_page()

        for game, ver in NEXT_VERSION.items():
            date_iso = await scrape_game(page, game, ver)
            prev = data.get(game) or {}
            if date_iso:
                data[game] = {
                    "version":    ver,
                    "title":      prev.get("title") if prev.get("version") == ver else None,
                    "date":       date_iso,
                    "url":        None,
                    "highlights": prev.get("highlights", []) if prev.get("version") == ver else [],
                }
            else:
                print(f"  [{game}] keeping existing data")

        await browser.close()

    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for g, v in data.items():
        if isinstance(v, dict) and "version" in v:
            print(f"  {g}: v{v.get('version')} @ {v.get('date')}")


def main() -> None:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        print("Missing playwright. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
