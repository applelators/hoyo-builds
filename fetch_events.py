"""Fetch event calendar from each game's wiki using Playwright.

Outputs to events.json. Run once per patch.

Notes:
- Preserves manual `tagline` and `type` fields across runs.
- Drops events that ended more than 7 days ago.
- Event pages use "Event | Duration | Type(s)" table format where Duration is
  "Month DD, YYYY – Month DD, YYYY" (or a single date for permanent events).
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).parent / "events.json"

SOURCES = {
    "gi":  "https://genshin-impact.fandom.com/wiki/Event",
    "hsr": "https://honkai-star-rail.fandom.com/wiki/Event",
    "zzz": "https://zenless-zone-zero.fandom.com/wiki/Event",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

TYPE_HINTS = [
    (re.compile(r"\b(combat|spiral|abyss|tower|shiyu|trailblaze|memory|defense)\b", re.I), "combat"),
    (re.compile(r"\b(web|browser|browser-only)\b", re.I), "web"),
    (re.compile(r"\b(login|sign-in|check-in|daily|festive gifts|gift of odyssey)\b", re.I), "login"),
    (re.compile(r"\b(story|chapter|tale|saga)\b", re.I), "story"),
    (re.compile(r"\b(explor|hunt|delve|investigation)\b", re.I), "exploration"),
]

# Fandom appends start dates to recurring event names to disambiguate — strip them.
_DATE_SUFFIX = re.compile(r"\s+\d{4}-\d{2}-\d{2}$")


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def parse_date(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_duration(s: str) -> tuple[str | None, str | None]:
    """Parse 'Month DD, YYYY – Month DD, YYYY' into (start, end). Returns (None,None) on failure."""
    s = s.replace("–", "-").replace("—", "-")
    parts = re.split(r"\s*-\s*(?=[A-Z]|\d{4})", s, maxsplit=1)
    if len(parts) == 2:
        return parse_date(parts[0].strip()), parse_date(parts[1].strip())
    # Single date (permanent event) - no end
    d = parse_date(s.strip())
    return d, None


def infer_type(name: str, types_text: str = "") -> str:
    text = f"{name} {types_text}"
    for pattern, t in TYPE_HINTS:
        if pattern.search(text):
            return t
    return "main"


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    lookup = {(e["name"], e.get("start")): e for e in (existing or []) if e.get("end", "9999") > cutoff}
    merged = []
    seen = set()
    for s in scraped:
        if s.get("end") and s["end"] <= cutoff:
            continue
        # Preserve manual fields
        key = (s["name"], s.get("start"))
        seen.add(key)
        prev = lookup.get(key)
        if prev:
            s["tagline"] = prev.get("tagline") or s.get("tagline", "")
            s["rewards"] = prev.get("rewards") or s.get("rewards", "")
            if prev.get("type") and prev["type"] != "main":
                s["type"] = prev["type"]
            if prev.get("patch"):
                s["patch"] = prev["patch"]
        merged.append(s)
    # Keep any manual entries the scraper missed
    for key, prev in lookup.items():
        if key not in seen:
            merged.append(prev)
    merged.sort(key=lambda e: e.get("start") or "")
    return merged


_EXTRACT_JS = """
() => {
    const rows = [];
    for (const table of document.querySelectorAll('table.wikitable, table.article-table')) {
        const headerCells = Array.from(table.querySelectorAll('tr:first-child th'));
        if (!headerCells.length) continue;
        const headers = headerCells.map(c => c.innerText.trim().toLowerCase());
        const nameIdx     = headers.findIndex(h => h.includes('event') || h.includes('name'));
        const durationIdx = headers.findIndex(h => h.includes('duration') || h.includes('date'));
        const typeIdx     = headers.findIndex(h => h.includes('type'));
        if (nameIdx < 0 || durationIdx < 0) continue;
        for (const row of Array.from(table.querySelectorAll('tr')).slice(1)) {
            const cells = Array.from(row.querySelectorAll('td'));
            if (cells.length <= Math.max(nameIdx, durationIdx)) continue;
            const nameCell = cells[nameIdx];
            const link = nameCell.querySelector('a');
            rows.push({
                name:     nameCell.innerText.trim(),
                duration: cells[durationIdx].innerText.trim(),
                types:    typeIdx >= 0 ? cells[typeIdx].innerText.trim() : '',
                url:      link ? link.href : null,
            });
        }
    }
    return rows;
}
"""


async def scrape_game(page, game: str, url: str) -> list[dict]:
    print(f"  [{game}] loading {url}")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        # Wait longer for Cloudflare challenge pages
        await page.wait_for_timeout(8000)
        title = await page.title()
        if "moment" in title.lower():
            print(f"  [{game}] still on Cloudflare challenge, waiting more...")
            await page.wait_for_timeout(7000)

        raw = await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        print(f"  [{game}] ERROR: {e}")
        return []

    today = date.today().isoformat()
    out = []
    seen_names = set()
    for r in raw:
        # Strip wiki date-suffix disambiguation from name
        name = _DATE_SUFFIX.sub("", r["name"]).strip()
        if not name or name in seen_names:
            continue
        start, end = parse_duration(r["duration"])
        if not start:
            continue
        # Skip permanent events (no end date) and far-future events
        if not end:
            continue
        seen_names.add(name)
        out.append({
            "name":    name,
            "type":    infer_type(name, r["types"]),
            "start":   start,
            "end":     end,
            "tagline": "",
            "rewards": "",
            "url":     r["url"],
        })

    print(f"  [{game}] found {len(out)} events")
    return out


async def main_async() -> None:
    existing = load_existing()

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=UA,
        )
        page = await ctx.new_page()

        # Start with existing to preserve $schema and any extra keys
        result = {k: v for k, v in existing.items() if not isinstance(v, list)}
        for game, url in SOURCES.items():
            scraped = await scrape_game(page, game, url)
            result[game] = merge(existing.get(game, []), scraped)

        await browser.close()

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for g, entries in result.items():
        print(f"  {g}: {len(entries)} events")


def main() -> None:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        print("Missing playwright. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
