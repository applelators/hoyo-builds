"""Fetch character banner schedules from Game8 using Playwright.

Outputs to banners.json in the project root.
Run once per patch; manual `verdict`, `rerun`, and `phase` fields are preserved.

Sources:
- GI:  https://game8.co/games/Genshin-Impact/archives/305012  (Current and Next Banner Schedule)
- HSR: See CURRENT_VERSION_URLS — update each patch to the new version page
- ZZZ: See CURRENT_VERSION_URLS — update each patch to the new version page

Notes:
- Game8 banner schedule pages have clean Phase 1 / Phase 2 tables with explicit dates.
- GI: the single banner schedule page covers current and next banners.
- HSR/ZZZ: use the version release date page which lists both phases.
- The merge key is (character, start) so safe to re-run after manual edits.
- Update CURRENT_VERSION_URLS at the start of each patch cycle.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

OUTPUT = Path(__file__).parent / "banners.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

SOURCES = {
    "gi":  "https://game8.co/games/Genshin-Impact/archives/305012",
    "hsr": "https://game8.co/games/Honkai-Star-Rail/archives/585934",
    "zzz": "https://game8.co/games/Zenless-Zone-Zero/archives/590340",
}

# JS to extract banner phase tables from Game8 pages.
# Game8 uses tables with "Phase N Banners | Banner Dates | Rate-Ups" header rows.
_EXTRACT_GI_JS = """
() => {
    var results = [];
    var DATE_RE = /([A-Z][a-z]+ \\d{1,2}, \\d{4})/g;
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var rows = tables[i].querySelectorAll('tr');
        for (var j = 0; j < rows.length; j++) {
            var cells = rows[j].querySelectorAll('td');
            if (cells.length < 2) continue;
            var nameText = cells[0].innerText.trim();
            var dateText = cells[1] ? cells[1].innerText.trim() : '';
            // Look for rows that have a banner name and a date range
            var dates = dateText.match(DATE_RE);
            if (!dates || dates.length < 2) continue;
            // Character name: strip phase suffix, grab 5★ from rate-up cell
            var rateCell = cells[2] ? cells[2].innerText.trim() : '';
            var charMatch = rateCell.match(/5 Star Rate-Up:\\s*([^\\n4]+)/);
            var charName = charMatch ? charMatch[1].trim() : nameText.replace(/\\n.*/,'').trim();
            // Phase: look for "Phase 1" or "Phase 2" in nameText
            var phaseMatch = nameText.match(/Phase (\\d)/);
            var phase = phaseMatch ? parseInt(phaseMatch[1]) : 1;
            results.push({
                character: charName,
                phase: phase,
                startText: dates[0],
                endText: dates[1],
            });
        }
    }
    return results;
}
"""

_EXTRACT_VERSION_JS = """
() => {
    var results = [];
    var DATE_RE = /([A-Z][a-z]+ \\d{1,2}, \\d{4})/g;
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var headers = tables[i].querySelectorAll('tr:first-child th, tr:first-child td');
        var headerText = '';
        for (var h = 0; h < headers.length; h++) headerText += headers[h].innerText;
        if (headerText.toLowerCase().indexOf('phase') < 0 && headerText.toLowerCase().indexOf('banner') < 0) continue;
        var rows = tables[i].querySelectorAll('tr');
        for (var j = 1; j < rows.length; j++) {
            var cells = rows[j].querySelectorAll('td');
            if (cells.length < 2) continue;
            var nameText = cells[0].innerText.trim();
            var dateText = cells[1] ? cells[1].innerText.trim() : '';
            var dates = dateText.match(DATE_RE);
            if (!dates || dates.length < 2) continue;
            var charName = nameText.replace(/Banner.*$/, '').trim();
            var phaseMatch = (nameText + (cells[2] ? cells[2].innerText : '')).match(/Phase (\\d)/);
            var phase = phaseMatch ? parseInt(phaseMatch[1]) : 1;
            results.push({
                character: charName,
                phase: phase,
                startText: dates[0],
                endText: dates[1],
            });
        }
    }
    return results;
}
"""


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def parse_date(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%b %d, %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    lookup = {(e["character"], e.get("start")): e for e in (existing or [])}
    merged = []
    for s in scraped:
        key = (s["character"], s.get("start"))
        prev = lookup.get(key)
        if prev:
            s["verdict"] = prev.get("verdict") or s.get("verdict", "")
            s["rerun"]   = prev.get("rerun", s.get("rerun", False))
            if prev.get("patch"):
                s["patch"] = prev["patch"]
            if prev.get("phase"):
                s["phase"] = prev["phase"]
        merged.append(s)
    seen = {(s["character"], s.get("start")) for s in scraped}
    today = date.today().isoformat()
    for key, prev in lookup.items():
        if key not in seen and prev.get("end", "9999") >= today:
            merged.append(prev)
    return merged


async def scrape_game(page, game: str, url: str) -> list[dict]:
    print(f"  [{game}] loading {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        title = await page.title()
        print(f"  [{game}] title: {title}")

        js = _EXTRACT_GI_JS if game == "gi" else _EXTRACT_VERSION_JS
        raw = await page.evaluate(js)
    except Exception as e:
        print(f"  [{game}] ERROR: {e}")
        return []

    out = []
    today = date.today().isoformat()
    seen = set()
    for r in raw:
        char  = r.get("character", "").strip()
        start = parse_date(r.get("startText", ""))
        end   = parse_date(r.get("endText", ""))
        if not char or not start or not end:
            continue
        if end < today:
            continue
        key = (char, start)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "character": char,
            "phase":     r.get("phase", 1),
            "start":     start,
            "end":       end,
            "rerun":     False,
            "verdict":   "",
        })

    print(f"  [{game}] {len(out)} current/upcoming banners found")
    return out


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

        for game, url in SOURCES.items():
            scraped = await scrape_game(page, game, url)
            existing = data.get(game, [])
            if scraped:
                data[game] = merge(existing, scraped)
                print(f"  [{game}] merged → {len(data[game])} banners")
            else:
                print(f"  [{game}] no new data — keeping {len(existing)} existing")

        await browser.close()

    # Preserve $schema and non-list keys
    result = {k: v for k, v in data.items() if not isinstance(v, list)}
    for game in SOURCES:
        if game in data:
            result[game] = data[game]

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for g, entries in result.items():
        if isinstance(entries, list):
            print(f"  {g}: {len(entries)} banners")


def main() -> None:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        print("Missing playwright. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
