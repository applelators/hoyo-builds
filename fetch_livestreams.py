"""Fetch upcoming version livestream dates from each game's wiki.

Outputs to livestreams.json. Run when a new patch livestream is announced.

Strategy:
- Each game's wiki has /wiki/Version/<N.M> pages with a "Special Program" /
  "Livestream" infobox row.
- We try the *next* version page (latest known + 0.1, plus a couple offsets).
- Manual `highlights` are preserved across runs.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing deps. Run: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

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

UA = {"User-Agent": "hoyo-builds-scraper/1.0"}


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {}


def parse_datetime(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip()
    # Try common Fandom datetime formats
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


def find_livestream(soup: BeautifulSoup) -> str | None:
    """Scan the page for a 'Special Program' or 'Livestream' label and grab the
    adjacent date cell."""
    for label in soup.find_all(string=re.compile(r"Special Program|Livestream", re.I)):
        # Walk up to the row, then look at the next cell
        parent = label.parent
        for _ in range(4):
            if parent is None:
                break
            if parent.name in ("tr", "div"):
                break
            parent = parent.parent
        if parent is None:
            continue
        # Try sibling text
        sib = parent.find_next("td") or parent.find_next("div", class_="pi-data-value")
        if sib:
            text = sib.get_text(" ", strip=True)
            iso = parse_datetime(text)
            if iso:
                return iso
    return None


def main():
    data = load_existing()
    for game, url_template in SOURCES.items():
        ver = NEXT_VERSION[game]
        url = url_template.format(ver=ver)
        print(f"[{game}] fetching {url}")
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 404:
                print(f"[{game}] {url} not found — version page may not exist yet")
                continue
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            date_iso = find_livestream(soup)
            if not date_iso:
                print(f"[{game}] no livestream date found on {url}")
                continue
            prev = data.get(game) or {}
            data[game] = {
                "version": ver,
                "title": prev.get("title") if prev.get("version") == ver else None,
                "date": date_iso,
                "url": url,
                "highlights": prev.get("highlights", []) if prev.get("version") == ver else [],
            }
            print(f"[{game}] v{ver} livestream at {date_iso}")
        except Exception as e:
            print(f"[{game}] FAILED: {e}", file=sys.stderr)
    OUTPUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
