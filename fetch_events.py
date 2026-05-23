"""Fetch event calendar from each game's Game8 wiki using Playwright.

Outputs to events.json. Run once per patch.

Notes:
- Preserves manual `tagline` and `type` fields across runs.
- Drops events that ended more than 7 days ago.
- Strategy:
  - GI: Visit one current event page — it contains a full "Event Guide | Date and Rewards"
    table listing all v6.x events with MM/DD/YYYY dates.
  - HSR: Visit the All Events and Schedule page — has "Dates | Ongoing Events" table.
  - ZZZ: Visit one current event page — it contains the same cross-event summary table.
- Update EVENT_ENTRY_URLS each patch to point to an event page from the current version.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).parent / "events.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Entry-point pages that contain the comprehensive events-with-dates table.
# Update these each patch to a current-version event or schedule page.
EVENT_ENTRY_URLS = {
    "gi":  "https://game8.co/games/Genshin-Impact/archives/598978",      # Phantasmal Pals (v6.6)
    "hsr": "https://game8.co/games/Honkai-Star-Rail/archives/408749",     # All Events and Schedule
    "zzz": "https://game8.co/games/Zenless-Zone-Zero/archives/596538",    # Operation Save Bootopia (v2.8)
}

TYPE_HINTS = [
    (re.compile(r"\b(combat|spiral|abyss|tower|shiyu|trailblaze|memory|defense|bounty|trial|verdict|fissure|realm|novaflare|onslaught|simulation)\b", re.I), "combat"),
    (re.compile(r"\b(web|browser|browser-only|tea party|workshop)\b", re.I), "web"),
    (re.compile(r"\b(login|sign-in|check-in|daily|festive gifts|gift of odyssey|program|en-nah|boopons?)\b", re.I), "login"),
    (re.compile(r"\b(story|chapter|tale|saga|callback|notebook)\b", re.I), "story"),
    (re.compile(r"\b(explor|hunt|delve|investigation|ridu|legends|roaming|data)\b", re.I), "exploration"),
]

# Game8 event tables use either "Event Guide | Date and Rewards" (GI/ZZZ)
# or "Dates | Ongoing Events" (HSR).
_EXTRACT_JS = """
() => {
    var results = [];
    var DATE_RE = /(\\d{2}\\/\\d{2}\\/\\d{4})/g;
    var DATE_RE2 = /([A-Z][a-z]+\\.?\\s+\\d{1,2},?\\s+\\d{4})/g;
    function parseDates(txt) {
        var m1 = txt.match(DATE_RE);
        if (m1 && m1.length >= 2) return [m1[0], m1[m1.length-1]];
        var m2 = txt.match(DATE_RE2);
        if (m2 && m2.length >= 2) return [m2[0], m2[m2.length-1]];
        // HSR format "MM/DD - MM/DD" within a year context
        var range = txt.match(/(\\d{2}\\/\\d{2})\\s*[-–]\\s*(\\d{2}\\/\\d{2})(?:,\\s*(\\d{4}))?/);
        if (range) {
            var yr = range[3] || new Date().getFullYear();
            return [range[1] + '/' + yr, range[2] + '/' + yr];
        }
        return null;
    }
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var rows = tables[i].querySelectorAll('tr');
        for (var j = 0; j < rows.length; j++) {
            var cells = rows[j].querySelectorAll('td');
            if (cells.length < 2) continue;
            var col0 = cells[0].innerText.trim();
            var col1 = cells[1].innerText.trim();
            // GI/ZZZ format: col0=name, col1=date range
            // HSR format: col0=date range, col1=name
            var nameText, dateText;
            if (DATE_RE.test(col0) || /\\d{2}\\/\\d{2}/.test(col0)) {
                DATE_RE.lastIndex = 0;
                dateText = col0;
                nameText = col1.replace(/^◆\\s*/, '').split('\\n')[0].trim();
            } else {
                nameText = col0.replace(/^◆\\s*/, '').split('\\n')[0].trim();
                dateText = col1;
            }
            DATE_RE.lastIndex = 0;
            if (!nameText || nameText.length < 3) continue;
            // Skip header rows and reward-only rows
            if (/^(Event|Date|Duration|Guide|Reward|Ongoing)/i.test(nameText)) continue;
            var dates = parseDates(dateText);
            if (!dates) continue;
            // Extract URL from name cell anchor
            var anchor = cells[0].querySelector('a') || cells[1].querySelector('a');
            var url = anchor ? anchor.href : null;
            results.push({
                name: nameText.replace(/\\s+/g, ' '),
                dateStart: dates[0],
                dateEnd: dates[1],
                url: url,
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
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b. %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def infer_type(name: str) -> str:
    for pattern, t in TYPE_HINTS:
        if pattern.search(name):
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
        key = (s["name"], s.get("start"))
        seen.add(key)
        prev = lookup.get(key)
        if prev:
            s["tagline"] = prev.get("tagline") or s.get("tagline", "")
            s["rewards"] = prev.get("rewards") or s.get("rewards", "")
            if prev.get("type") and prev["type"] != "main":
                s["type"] = prev["type"]
        merged.append(s)
    for key, prev in lookup.items():
        if key not in seen:
            merged.append(prev)
    merged.sort(key=lambda e: e.get("start") or "")
    return merged


async def scrape_game(page, game: str, url: str) -> list[dict]:
    print(f"  [{game}] loading {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        title = await page.title()
        print(f"  [{game}] title: {title}")
        raw = await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        print(f"  [{game}] ERROR: {e}")
        return []

    today = date.today().isoformat()
    out = []
    seen_names = set()
    for r in raw:
        name = r.get("name", "").strip()
        if not name or name in seen_names:
            continue
        start = parse_date(r.get("dateStart", ""))
        end   = parse_date(r.get("dateEnd", ""))
        if not start or not end:
            continue
        if end < today:
            continue
        # Skip permanent / no-end events surfaced by the table scraper
        if end > "2030-01-01":
            continue
        seen_names.add(name)
        out.append({
            "name":    name,
            "type":    infer_type(name),
            "start":   start,
            "end":     end,
            "tagline": "",
            "rewards": "",
            "url":     r.get("url"),
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

        result = {k: v for k, v in existing.items() if not isinstance(v, list)}
        for game, url in EVENT_ENTRY_URLS.items():
            scraped = await scrape_game(page, game, url)
            result[game] = merge(existing.get(game, []), scraped)

        await browser.close()

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for g, entries in result.items():
        if isinstance(entries, list):
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
