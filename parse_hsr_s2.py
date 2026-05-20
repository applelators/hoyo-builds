#!/usr/bin/env python3
"""
Parse HSR Sheet 2 CSVs into hsr_s2.json.
Output: { "Character Name": { kit_overview, worth_pulling, recommended_baseline,
                               example_teams: [{label, members:[str,...]}] } }
"""

import csv
import glob
import json
import re

CACHE_DIR = "/Users/hokori/.cache/hsr_builds"
OUTPUT    = "/Users/hokori/genshin-builds/hsr_s2.json"

# Blocks whose col[1] on the Main Role row marks them as template / not a character
SKIP_COL1 = {
    'Portrait of Character taken from their Signature Light Cone',
}


def g(row, j):
    return row[j].strip() if len(row) > j else ''


def normalize_name(raw: str):
    """Convert Sheet 2 ALL_CAPS name to display form. Returns None for non-names."""
    name = raw.strip()
    if not name or re.match(r'^[✦★*]+$', name):
        return None
    # Normalize & spacing ("TOPAZ&NUMBY" → "Topaz & Numby")
    name = re.sub(r'(?<!\s)&(?!\s)', ' & ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.title()


def parse_block(rows):
    if len(rows) < 2:
        return None

    # Skip template blocks identified by col[1] of the Main Role row
    if g(rows[0], 1) in SKIP_COL1:
        return None

    # Find actual data row: first row in block where col[16] is non-empty and
    # not a ✦ section header.  Some blocks put kit data on the Main Role row
    # itself (idx=0); others have it on rows[1] or rows[2].
    data_row = None
    data_row_idx = None
    for idx in range(len(rows)):
        c16 = g(rows[idx], 16)
        if c16 and not c16.startswith('✦'):
            data_row = rows[idx]
            data_row_idx = idx
            break

    if data_row is None:
        return None

    kit_overview         = g(data_row, 16)
    worth_pulling        = g(data_row, 44)
    recommended_baseline = g(data_row, 58)

    # Drop values that are actually ✦ section headers that bled into data col
    if recommended_baseline.startswith('✦'):
        recommended_baseline = ''
    if worth_pulling.startswith('✦'):
        worth_pulling = ''

    # Character name: collect consecutive non-empty non-star col[1] values,
    # then normalize.  Some names span two rows (e.g. "SILVER WOLF" / "LVL 999").
    raw_parts: list = []
    for r in rows:
        c1 = g(r, 1)
        if not c1:
            if raw_parts:
                break          # stop at first gap after name started
            continue
        if re.match(r'^[✦★*]+$', c1):
            if raw_parts:
                break          # star rating row ends the name
            continue
        raw_parts.append(c1)

    if not raw_parts:
        return None
    raw_name = ' '.join(raw_parts)
    name = normalize_name(raw_name)
    if not name:
        return None

    # Normalize multi-row / variant names to match hsr_builds.json names
    _NAME_FIXES = {
        'Silver Wolf Lvl 999':       'Silver Wolf LV.999',
        'Dan Heng Imbibitor Lunae':  'Imbibitor Lunae',
        'Dan Heng Permansor Terrae': 'Permansor Terrae',
    }
    name = _NAME_FIXES.get(name, name)

    # Teams: scan rows AFTER the data row (skip the teams-general-note in data_row col[70])
    example_teams = []
    pending_label = None
    for r in rows[data_row_idx + 1:]:
        t70, t75, t80, t85 = [g(r, j) for j in [70, 75, 80, 85]]

        if t70 and not t75:
            # Label row — skip ✦ section headers
            if not t70.startswith('✦'):
                pending_label = t70
        elif t70 and t75:
            # Member row
            members = [m for m in [t70, t75, t80, t85] if m]
            example_teams.append({
                'label':   pending_label or '',
                'members': members,
            })
            pending_label = None

    return {
        'name':                 name,
        'kit_overview':         kit_overview,
        'worth_pulling':        worth_pulling,
        'recommended_baseline': recommended_baseline,
        'example_teams':        example_teams,
    }


def parse_file(path: str) -> list:
    with open(path, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    mr_idxs = [i for i, r in enumerate(rows) if g(r, 8) == 'Main Role']
    if not mr_idxs:
        return []

    results = []
    for bi, start in enumerate(mr_idxs):
        end = mr_idxs[bi + 1] if bi + 1 < len(mr_idxs) else len(rows)
        parsed = parse_block(rows[start:end])
        if parsed:
            results.append(parsed)
    return results


def main():
    all_blocks: list = []
    for path in sorted(glob.glob(f"{CACHE_DIR}/s2_*.csv")):
        blocks = parse_file(path)
        all_blocks.extend(blocks)
        print(f"  {path.split('/')[-1]}: {len(blocks)} chars")

    # Build lookup: name → data  (first-wins for duplicates like Trailblazer)
    lookup: dict = {}
    seen_names: dict = {}
    for b in all_blocks:
        n = b['name']
        seen_names[n] = seen_names.get(n, 0) + 1
        if n not in lookup:
            lookup[n] = {k: v for k, v in b.items() if k != 'name'}

    with open(OUTPUT, 'w', encoding='utf-8') as fh:
        json.dump(lookup, fh, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(lookup)} entries to {OUTPUT}")
    for n, cnt in sorted(seen_names.items()):
        ov = lookup[n]
        teams = len(ov['example_teams'])
        dup   = f" ({cnt}×)" if cnt > 1 else ''
        print(f"  {n:40s}{dup}  {teams} teams  base={ov['recommended_baseline'][:25]}")


if __name__ == '__main__':
    main()
