#!/usr/bin/env python3
"""Fetch release dates for HSR characters from the fandom wiki API."""

import json
import time
import urllib.request
import urllib.parse

OUTPUT = "/Users/hokori/genshin-builds/hsr_release_dates.json"

API = "https://honkai-star-rail.fandom.com/api.php"

# Map character names that don't match wiki page titles directly
WIKI_TITLE = {
    "Imbibitor Lunae":    "Dan Heng • Imbibitor Lunae",
    "Topaz & Numby":      "Topaz & Numby",
    "The Herta":          "The Herta",
    "The Dahlia":         "Dahlia",
    "Silver Wolf LV.999": "Anicka",        # Elation version — try wiki name
    "Dr. Ratio":          "Dr. Ratio",
    "Black Swan":         "Black Swan",
    "Jing Yuan":          "Jing Yuan",
    "Fu Xuan":            "Fu Xuan",
    "Dan Heng":           "Dan Heng",
    "Ruan Mei":           "Ruan Mei",
    "Yao Guang":          "Yao Guang",
}

# Characters that share a wiki page (same person, different paths)
SHARED_PAGE = {
    "March 7th":   "March 7th",
    "Trailblazer": "Trailblazer",
}


def fetch_release_date(title: str):
    params = urllib.parse.urlencode({
        "action": "parse",
        "page":   title,
        "prop":   "wikitext",
        "format": "json",
    })
    url = f"{API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"  ERROR fetching {title!r}: {e}")
        return None

    if "error" in data:
        print(f"  WIKI ERROR for {title!r}: {data['error'].get('info','')}")
        return None

    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    # Look for |release_date = YYYY-MM-DD
    import re
    m = re.search(r"\|\s*release_date\s*=\s*(\d{4}-\d{2}-\d{2})", wikitext)
    if m:
        return m.group(1)
    # Some pages use a different field
    m = re.search(r"release[_\s]date[^=]*=\s*(\d{4}-\d{2}-\d{2})", wikitext, re.IGNORECASE)
    return m.group(1) if m else None


def main():
    with open("/Users/hokori/genshin-builds/hsr_builds.json") as f:
        chars = json.load(f)

    # Collect unique wiki titles to fetch (avoid duplicate requests)
    seen_titles: dict[str, str] = {}   # wiki_title -> release_date
    name_to_date: dict[str, str] = {}  # char_name -> release_date

    for char in chars:
        name = char["name"]
        if name in SHARED_PAGE:
            title = SHARED_PAGE[name]
        elif name in WIKI_TITLE:
            title = WIKI_TITLE[name]
        else:
            title = name

        if title not in seen_titles:
            print(f"Fetching: {title!r} (for {name!r})")
            date = fetch_release_date(title)
            seen_titles[title] = date or ""
            print(f"  → {date}")
            time.sleep(0.4)   # be polite

        date = seen_titles[title]
        name_to_date[name] = date

    with open(OUTPUT, "w") as f:
        json.dump(name_to_date, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(name_to_date)} entries to {OUTPUT}")
    missing = [n for n, d in name_to_date.items() if not d]
    if missing:
        print(f"Missing dates: {missing}")


if __name__ == "__main__":
    main()
