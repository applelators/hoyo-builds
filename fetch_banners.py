"""Fetch character banner schedules from each game's wiki using Playwright.

Outputs to banners.json in the project root.
Run once per patch; manual `verdict`, `rerun`, and `phase` fields are preserved.

Notes:
- The banner history wiki pages list all-time banners without dated current tables,
  so automated extraction of start/end for the *current* patch isn't reliable.
  The scraper tries its best; if nothing is found the existing data is kept intact.
- Add new banners manually (or update this scraper) when a new patch begins.
  The merge key is (character, start) so safe to re-run after manual edits.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

OUTPUT = Path(__file__).parent / "banners.json"

SOURCES = {
    "gi":  "https://genshin-impact.fandom.com/wiki/Character_Event_Wish",
    "hsr": "https://honkai-star-rail.fandom.com/wiki/Event_Warp",
    "zzz": "https://zenless-zone-zero.fandom.com/wiki/Exclusive_Channel",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Extract rows from tables that have a date range and a character name
_EXTRACT_JS = """
() => {
    const DATE_RE = /\\d{4}-\\d{2}-\\d{2}|[A-Z][a-z]+ \\d{1,2}, \\d{4}/;
    const rows = [];
    for (const table of document.querySelectorAll('table.wikitable, table.article-table')) {
        const headers = Array.from(table.querySelectorAll('tr:first-child th')).map(c => c.innerText.trim().toLowerCase());
        const charIdx  = headers.findIndex(h => h.includes('character') || h.includes('agent') || h.includes('wish'));
        const startIdx = headers.findIndex(h => h.includes('start') || h.includes('from') || h.includes('release'));
        const endIdx   = headers.findIndex(h => h.includes('end') || h.includes('to'));
        if (charIdx < 0 || startIdx < 0) continue;
        for (const row of Array.from(table.querySelectorAll('tr')).slice(1)) {
            const cells = Array.from(row.querySelectorAll('td'));
            if (!cells.length) continue;
            const charText  = cells[charIdx]?.innerText.trim();
            const startText = cells[startIdx]?.innerText.trim();
            const endText   = endIdx >= 0 ? cells[endIdx]?.innerText.trim() : '';
            if (charText && startText && DATE_RE.test(startText))
                rows.push({ character: charText, start: startText, end: endText });
        }
    }
    return rows;
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
    """Preserve verdicts + reruns from existing entries. Match by (character, start)."""
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
    # Preserve existing entries not found in the scrape (manually-added banners)
    seen = {(s["character"], s.get("start")) for s in scraped}
    today = date.today().isoformat()
    for key, prev in lookup.items():
        if key not in seen and prev.get("end", "9999") >= today:
            merged.append(prev)
    return merged


async def scrape_game(page, game: str, url: str) -> list[dict]:
    print(f"  [{game}] loading {url}")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        title = await page.title()
        if "moment" in title.lower():
            await page.wait_for_timeout(7000)

        raw = await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        print(f"  [{game}] ERROR: {e}")
        return []

    out = []
    today = date.today().isoformat()
    for r in raw:
        char  = re.sub(r"\s*\(.*?\)\s*$", "", r["character"]).strip()
        start = parse_date(r["start"])
        end   = parse_date(r["end"]) if r["end"] else None
        if not char or not start or not end:
            continue
        if end < today:
            continue
        out.append({
            "character": char,
            "phase":     1,
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

    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for g, entries in data.items():
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
