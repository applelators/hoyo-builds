"""Fetch character banner schedules from each game's wiki.

Outputs to banners.json in the project root, preserving the $schema block.
Run once per patch.

Notes:
- Fandom MediaWiki sites expose /api.php which is more reliable than scraping.
- We attempt to use the API where possible; HTML scraping is the fallback.
- Manual `verdict` text is preserved across runs (matched by character + start date).
"""
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing deps. Run: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

OUTPUT = Path(__file__).parent / "banners.json"

SOURCES = {
    "gi":  {
        "url": "https://genshin-impact.fandom.com/wiki/Character_Event_Wish",
        "api": "https://genshin-impact.fandom.com/api.php",
    },
    "hsr": {
        "url": "https://honkai-star-rail.fandom.com/wiki/Warp/Event_Warp",
        "api": "https://honkai-star-rail.fandom.com/api.php",
    },
    "zzz": {
        "url": "https://zenless-zone-zero.fandom.com/wiki/Exclusive_Channel",
        "api": "https://zenless-zone-zero.fandom.com/api.php",
    },
}

UA = {"User-Agent": "hoyo-builds-scraper/1.0 (https://github.com/applelators/hoyo-builds)"}


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def fetch_wiki_html(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def parse_date(s: str) -> str | None:
    """Parse a wiki date string into ISO YYYY-MM-DD. Returns None on failure."""
    s = re.sub(r"\s+", " ", s).strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%b %d, %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # try "Month YYYY" without day
    m = re.match(r"^([A-Z][a-z]+) (\d{4})$", s)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} 1 {m.group(2)}", "%B %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_banners_from_wikitable(soup: BeautifulSoup) -> list[dict]:
    """Generic wikitable extractor. Each game's wiki has slightly different columns;
    this hits the common case (Character | Phase | Start | End) and skips the rest."""
    out = []
    for table in soup.select("table.wikitable, table.article-table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        char_idx = next((i for i, h in enumerate(headers) if "character" in h or "agent" in h), None)
        start_idx = next((i for i, h in enumerate(headers) if "start" in h or "release" in h), None)
        end_idx = next((i for i, h in enumerate(headers) if "end" in h or "expire" in h), None)
        if char_idx is None or start_idx is None:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(char_idx, start_idx, end_idx or 0):
                continue
            char = cells[char_idx].get_text(" ", strip=True)
            # strip parenthetical phase/region tags from name
            char = re.sub(r"\s*\(.*?\)\s*$", "", char).strip()
            start = parse_date(cells[start_idx].get_text(strip=True))
            end = parse_date(cells[end_idx].get_text(strip=True)) if end_idx is not None else None
            if char and start and end:
                out.append({
                    "character": char,
                    "phase": 1,  # TODO: infer phase from version pages
                    "start": start,
                    "end": end,
                    "rerun": False,  # TODO: cross-reference to detect rerun
                    "verdict": "",
                })
    return out


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    """Preserve verdicts + reruns from existing entries when scraping replaces them.
    Match by (character, start)."""
    lookup = {(e["character"], e.get("start")): e for e in (existing or [])}
    merged = []
    for s in scraped:
        key = (s["character"], s.get("start"))
        prev = lookup.get(key)
        if prev:
            s["verdict"] = prev.get("verdict") or s.get("verdict", "")
            s["rerun"] = prev.get("rerun", s.get("rerun", False))
            if prev.get("patch"):
                s["patch"] = prev["patch"]
            if prev.get("phase"):
                s["phase"] = prev["phase"]
        merged.append(s)
    return merged


def main():
    data = load_existing()
    for game, src in SOURCES.items():
        print(f"[{game}] fetching {src['url']}")
        try:
            soup = fetch_wiki_html(src["url"])
            scraped = parse_banners_from_wikitable(soup)
            print(f"[{game}] parsed {len(scraped)} banners")
            data[game] = merge(data.get(game, []), scraped)
        except Exception as e:
            print(f"[{game}] FAILED: {e}", file=sys.stderr)
    OUTPUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
