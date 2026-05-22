"""Fetch upcoming version livestream dates from each game's wiki.

Outputs to livestreams.json. Run when a new patch livestream is announced.

Strategy:
- Load each game's version page with Playwright (handles Cloudflare).
- Look for "Special Program" / "Livestream" text and the adjacent date.
- Manual `highlights` are preserved across runs.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

OUTPUT = Path(__file__).parent / "livestreams.json"

SOURCES = {
    "gi":  "https://genshin-impact.fandom.com/wiki/Version/{ver}",
    "hsr": "https://honkai-star-rail.fandom.com/wiki/Version/{ver}",
    "zzz": "https://zenless-zone-zero.fandom.com/wiki/Version/{ver}",
}

# Bump these when a new version cycle begins.
NEXT_VERSION = {
    "gi":  "5.8",
    "hsr": "3.8",
    "zzz": "2.6",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def parse_datetime(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip()
    fmts = [
        "%Y-%m-%d %H:%M:%S",
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


_FIND_DATE_JS = """
() => {
    const LABELS = /Special\\s+Program|Livestream|Preview\\s+Stream/i;
    for (const el of document.querySelectorAll('[data-source], .pi-data, tr, div')) {
        const label = el.querySelector('.pi-data-label, th, [class*="label"]');
        if (!label || !LABELS.test(label.innerText)) continue;
        const val = el.querySelector('.pi-data-value, td, [class*="value"]');
        if (val) {
            const text = val.innerText.trim();
            if (text && text.length > 4) return text;
        }
    }
    // fallback: scan page text for date near the label
    const body = document.body.innerText;
    const m = body.match(/Special\\s+Program[^\\n]*\\n([^\\n]+)/i);
    return m ? m[1].trim() : null;
}
"""


async def scrape_game(page, game: str, ver: str) -> str | None:
    url = SOURCES[game].format(ver=ver)
    print(f"  [{game}] loading {url}")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        title = await page.title()
        if "moment" in title.lower() or "404" in title:
            print(f"  [{game}] Cloudflare/404, waiting extra...")
            await page.wait_for_timeout(10000)
            title = await page.title()
        else:
            await page.wait_for_timeout(5000)

        if "moment" in title.lower():
            print(f"  [{game}] still blocked — skipping")
            return None
        if "404" in title or "not found" in title.lower():
            print(f"  [{game}] page not found yet")
            return None

        date_text = await page.evaluate(_FIND_DATE_JS)
        if not date_text:
            print(f"  [{game}] no livestream date found on page")
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
            url = SOURCES[game].format(ver=ver)
            prev = data.get(game) or {}
            if date_iso:
                data[game] = {
                    "version":    ver,
                    "title":      prev.get("title") if prev.get("version") == ver else None,
                    "date":       date_iso,
                    "url":        url,
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
