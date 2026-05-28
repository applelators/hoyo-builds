#!/usr/bin/env python3
"""Parse Genshin Helper Team CSVs into builds.json."""

import csv
import glob
import json
import re

CACHE_DIR     = "/Users/hokori/.cache/genshin_builds"
SCRAPE_OUTPUT = "/Users/hokori/genshin-builds/builds_scrape.json"
CANONICAL     = "/Users/hokori/genshin-builds/builds.json"  # user-editable; never written by parser

SKIP_NAMES = {
    "ROLE", "EQUIPMENT", "ARTIFACT", "SUBSTATS", "TALENT PRIORITY",
    "ABILITY TIPS", "MAIN STATS", "NOTES", "4 STAR", "5 STAR",
}

GI_NAME_NORMALIZE = {
    'ARATAKI ITTO': 'Itto',
    'KAEDEHARA KAZUHA': 'Kazuha',
    'KAMISATO AYAKA': 'Ayaka',
    'KAMISATO AYATO': 'Ayato',
    'KUJOU SARA': 'Sara',
    'KUKI SHINOBU': 'Shinobu',
    'RAIDEN SHOGUN': 'Raiden',
    'SANGONOMIYA KOKOMI': 'Kokomi',
    'SHIKANOIN HEIZOU': 'Heizou',
    'YUMEMIZUKI MIZUKI': 'Mizuki',
}

HEADER_MARKERS = {"ROLE", "EQUIPMENT", "ARTIFACT STATS", "TALENT PRIORITY", "ABILITY TIPS"}


def is_character_row(row):
    if len(row) < 2:
        return False
    col0 = row[0].strip()
    col1 = row[1].strip()
    col2 = row[2].strip() if len(row) > 2 else ""
    if col0 != "" or col1 == "" or col2 != "":
        return False
    if col1 in SKIP_NAMES:
        return False
    if not re.match(r"^[A-Z][A-Z\s\']+$", col1):
        return False
    if len(col1) < 3:
        return False
    return True


def parse_file(filepath):
    characters = []
    current = None

    with open(filepath, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)

    for row in rows:
        # Pad row to at least 9 columns
        while len(row) < 9:
            row.append("")

        col0 = row[0].strip()
        col1 = row[1].strip()
        col2 = row[2].strip()

        # New character header
        if is_character_row(row):
            if current:
                characters.append(current)
            name = GI_NAME_NORMALIZE.get(col1, col1.title())
            current = {"name": name, "last_updated": "", "builds": [], "notes": ""}
            continue

        if current is None:
            continue

        # Last updated
        if col1.startswith("Last Updated:"):
            current["last_updated"] = col1.replace("Last Updated:", "").strip()
            continue

        # Header rows — skip
        if col2 in HEADER_MARKERS or col1 in HEADER_MARKERS:
            continue
        if col2 == "WEAPON" or col2 == "ARTIFACT":
            continue

        # Notes row
        if col1 == "NOTES":
            current["notes"] = row[2].strip()
            continue

        # Build row: col1 empty, col2 has role name
        if col0 == "" and col1 == "" and col2 != "":
            role_text = col2
            recommended = "✩" in role_text
            role_name = role_text.replace("✩", "").strip()
            build = {
                "role": role_name,
                "recommended": recommended,
                "weapons": row[3].strip(),
                "artifacts": row[4].strip(),
                "main_stats": row[5].strip(),
                "substats": row[6].strip(),
                "talent_priority": row[7].strip(),
                "tips": row[8].strip(),
            }
            current["builds"].append(build)
            continue

        # Footnote continuation row: no role, no notes label, content only in stats columns.
        # Append to the last build's main_stats (col 5 is the main_stats column).
        if col0 == "" and col1 == "" and col2 == "" and current["builds"]:
            note = row[5].strip()
            if note and note not in ("MAIN STATS", "MAIN STAT", "WEAPON", "ARTIFACT", "SUBSTATS"):
                last = current["builds"][-1]
                last["main_stats"] = (last["main_stats"] + "\n" + note).strip()
            continue

    if current:
        characters.append(current)

    return characters


def diff_builds(new_chars, old_chars):
    new_by_name = {c['name']: c for c in new_chars}
    old_by_name = {c['name']: c for c in old_chars}
    added   = sorted(new_by_name.keys() - old_by_name.keys())
    removed = sorted(old_by_name.keys() - new_by_name.keys())
    updated = []
    for name, new_c in new_by_name.items():
        if name not in old_by_name:
            continue
        old_c = old_by_name[name]
        if new_c.get('last_updated') != old_c.get('last_updated'):
            updated.append((name, f"{old_c.get('last_updated')!r} → {new_c.get('last_updated')!r}"))
        elif json.dumps(new_c, sort_keys=True) != json.dumps(old_c, sort_keys=True):
            updated.append((name, 'build content changed'))
    return added, removed, updated


def main():
    all_characters = {}
    files = sorted(glob.glob(f"{CACHE_DIR}/builds_*.csv"))

    for f in files:
        chars = parse_file(f)
        for char in chars:
            name = char["name"]
            if name not in all_characters and name not in SKIP_NAMES:
                all_characters[name] = char

    result = sorted(all_characters.values(), key=lambda c: c["name"])
    result = [c for c in result if c["builds"] or c["notes"]]

    # Load previous scrape for diffing
    try:
        with open(SCRAPE_OUTPUT, encoding="utf-8") as fh:
            old_scrape = json.load(fh)
    except FileNotFoundError:
        old_scrape = []

    with open(SCRAPE_OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    added, removed, updated = diff_builds(result, old_scrape)
    print(f"─── GI scrape diff {'─'*41}")
    print(f"  NEW     ({len(added)}):  {', '.join(added) or '(none)'}")
    if updated:
        for name, reason in updated:
            print(f"  UPDATED:  {name}  [{reason}]")
    else:
        print(f"  UPDATED (0):  (none)")
    print(f"  REMOVED ({len(removed)}):  {', '.join(removed) or '(none)'}")
    print(f"\nWrote {len(result)} characters to {SCRAPE_OUTPUT}")
    print(f"Canonical ({CANONICAL}) NOT modified — apply updates manually.")

    for c in result:
        print(f"  {c['name']}: {len(c['builds'])} build(s)")


if __name__ == "__main__":
    main()
