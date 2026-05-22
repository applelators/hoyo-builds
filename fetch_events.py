"""Fetch event calendar from each game's wiki.

Outputs to events.json. Run once per patch.

Notes:
- Preserves manual `tagline` and `type` fields across runs.
- Drops past events (end < today - 7d) on each run.
"""
import json
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing deps. Run: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

OUTPUT = Path(__file__).parent / "events.json"

SOURCES = {
    "gi":  "https://genshin-impact.fandom.com/wiki/Event",
    "hsr": "https://honkai-star-rail.fandom.com/wiki/Event",
    "zzz": "https://zenless-zone-zero.fandom.com/wiki/Event",
}

UA = {"User-Agent": "hoyo-builds-scraper/1.0"}


TYPE_HINTS = [
    (re.compile(r"\b(combat|spiral|abyss|tower|shiyu|trailblaze|memory)\b", re.I), "combat"),
    (re.compile(r"\b(web|browser|browser-only)\b", re.I), "web"),
    (re.compile(r"\b(login|sign-in|check-in|daily)\b", re.I), "login"),
    (re.compile(r"\b(story|chapter|tale|saga)\b", re.I), "story"),
    (re.compile(r"\b(explor|hunt|delve|investigation)\b", re.I), "exploration"),
]


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


def infer_type(name: str, tagline: str = "") -> str:
    text = f"{name} {tagline}"
    for pattern, t in TYPE_HINTS:
        if pattern.search(text):
            return t
    return "main"


def parse_events(soup: BeautifulSoup) -> list[dict]:
    out = []
    for table in soup.select("table.wikitable, table.article-table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        name_idx = next((i for i, h in enumerate(headers) if "name" in h or "event" in h), None)
        start_idx = next((i for i, h in enumerate(headers) if "start" in h or "from" in h), None)
        end_idx = next((i for i, h in enumerate(headers) if "end" in h or "to" in h), None)
        if name_idx is None or start_idx is None or end_idx is None:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(name_idx, start_idx, end_idx):
                continue
            name = cells[name_idx].get_text(" ", strip=True)
            link_el = cells[name_idx].find("a")
            url = "https://" + link_el["href"].lstrip("/") if link_el and link_el.get("href", "").startswith("/wiki") else None
            start = parse_date(cells[start_idx].get_text(strip=True))
            end = parse_date(cells[end_idx].get_text(strip=True))
            if name and start and end:
                out.append({
                    "name": name,
                    "type": infer_type(name),
                    "start": start,
                    "end": end,
                    "tagline": "",
                    "rewards": "",
                    "url": url,
                })
    return out


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    """Drop past events; preserve manual taglines/rewards by (name, start)."""
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    lookup = {(e["name"], e.get("start")): e for e in (existing or []) if e.get("end", "") > cutoff}
    merged = []
    seen = set()
    for s in scraped:
        if s.get("end", "") <= cutoff:
            continue
        key = (s["name"], s.get("start"))
        seen.add(key)
        prev = lookup.get(key)
        if prev:
            s["tagline"] = prev.get("tagline") or s.get("tagline", "")
            s["rewards"] = prev.get("rewards") or s.get("rewards", "")
            if prev.get("type"):
                s["type"] = prev["type"]
            if prev.get("patch"):
                s["patch"] = prev["patch"]
        merged.append(s)
    # keep any manual entries the scraper missed
    for key, prev in lookup.items():
        if key not in seen:
            merged.append(prev)
    merged.sort(key=lambda e: e.get("start", ""))
    return merged


def main():
    data = load_existing()
    for game, url in SOURCES.items():
        print(f"[{game}] fetching {url}")
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            scraped = parse_events(soup)
            print(f"[{game}] parsed {len(scraped)} events")
            data[game] = merge(data.get(game, []), scraped)
        except Exception as e:
            print(f"[{game}] FAILED: {e}", file=sys.stderr)
    OUTPUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
