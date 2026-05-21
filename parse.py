#!/usr/bin/env python3
"""Parse Genshin Helper Team CSVs into builds.json."""

import csv
import glob
import json
import re

CACHE_DIR = "/Users/hokori/.cache/genshin_builds"
OUTPUT = "/Users/hokori/genshin-builds/builds.json"

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
    # Filter out non-character entries
    result = [c for c in result if c["builds"] or c["notes"]]

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(f"Wrote {len(result)} characters to {OUTPUT}")
    for c in result:
        print(f"  {c['name']}: {len(c['builds'])} build(s)")


if __name__ == "__main__":
    main()
