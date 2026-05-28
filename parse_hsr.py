#!/usr/bin/env python3
"""Parse HSR Helper Team sheet 1 CSVs into hsr_builds.json."""

import csv
import glob
import json
import re

CACHE_DIR     = "/Users/hokori/.cache/hsr_builds"
_BASE_DIR     = "/Users/hokori/genshin-builds"
SCRAPE_OUTPUT = f"{_BASE_DIR}/hsr_builds_scrape.json"
CANONICAL     = f"{_BASE_DIR}/hsr_builds.json"  # user-editable; never written by parser

HSR_NAME_NORMALIZE = {
    'Imbibitor Lunae':  'Dan Heng • Imbibitor Lunae',
    'Permansor Terrae': 'Dan Heng • Permansor Terrae',
    'Evernight':        'March 7th • Evernight',
    'March 7th':        'March 7th • The Hunt',
    'Fugue':            'Tingyun • Fugue',
    'Silver Wolf LV.999': 'Silver Wolf • Lv. 999',
}

PATH_KEYWORDS = {
    'Erudition', 'Harmony', 'Nihility', 'Destruction', 'Hunt',
    'Remembrance', 'Abundance', 'Preservation', 'Elation',
    'Propagation', 'Equanimity',
}
HEADER_SKIP = {'Equipment', 'Relic Stats', 'Ability Priority', '2 Piece Set (Planar Ornament)',
               'Baseline Stats', 'Ability Notes', 'Main Stats', 'Sub Stats',
               '4 Piece Set (Relic Set)', 'Light Cone', 'Notable\r\nEidolons', 'Notable\nEidolons'}


def is_char_header(row):
    while len(row) < 4:
        row.append('')
    return (row[0].strip() == '' and
            row[1].strip() and row[2].strip() in PATH_KEYWORDS and
            row[3].strip() in ('Equipment', '') and
            row[1].strip() not in ('5★ Characters', '4★ Characters'))


def pad(row, n=10):
    while len(row) < n:
        row.append('')
    return row


def parse_file(filepath):
    with open(filepath, newline='', encoding='utf-8') as fh:
        all_rows = list(csv.reader(fh))

    # Find character block boundaries
    char_starts = [i for i, r in enumerate(all_rows) if is_char_header(r)]
    results = []

    for ci, start in enumerate(char_starts):
        end = char_starts[ci + 1] if ci + 1 < len(char_starts) else len(all_rows)
        block = all_rows[start:end]
        char = parse_block(block)
        if char:
            results.append(char)

    return results


def parse_block(rows):
    if len(rows) < 3:
        return None

    header = pad(rows[0])
    name = HSR_NAME_NORMALIZE.get(header[1].strip(), header[1].strip())
    path = header[2].strip()

    # rows[1] = column sub-header, rows[2] = first data row
    first = pad(rows[2]) if len(rows) > 2 else [''] * 10

    # Primary build data lives in the first data row
    base_lc   = first[3].strip()
    base_4pc  = first[4].strip()
    base_sub  = first[6].strip()
    base_eid  = first[9].strip()

    builds = []
    # State per build section
    cur = None

    def flush_build():
        if cur is None:
            return
        # trim collected lists
        cur['main_stats']      = '\n'.join(x for x in cur['_main'] if x)
        cur['ability_priority']= '\n'.join(x for x in cur['_ab']   if x)
        del cur['_main'], cur['_ab']
        builds.append(cur)

    def new_build(role_name, lc, pc4, sub, eid):
        return {
            'role': role_name,
            'light_cones': lc,
            'relic_4pc': pc4,
            'sub_stats': sub,
            'eidolons': eid,
            'planar_ornament': '',
            'baseline_stats': '',
            'ability_notes': '',
            'relic_notes': '',
            'other_notes': '',
            '_main': [],
            '_ab':   [],
        }

    after_role = False  # True once we've passed the Role: row in current build
    pre_role_main = []  # main stats collected before the first Role: row
    pre_role_ab   = []  # ability priority collected before the first Role: row

    for row in rows[2:]:
        row = pad(row)
        c2, c3, c4, c5, c6, c7, c8, c9 = (row[2].strip(), row[3].strip(), row[4].strip(),
                                           row[5].strip(), row[6].strip(), row[7].strip(),
                                           row[8].strip(), row[9].strip())

        # Skip sub-header row
        if c4 in ('Light Cone', '4 Piece Set (Relic Set)'):
            continue

        # Role: row — starts a new build
        if c2.startswith('Role:') or (c2.startswith('Role') and '\n' in c2):
            flush_build()
            role_name = re.sub(r'^Role\s*:\s*', '', c2).strip()
            if builds:
                # Subsequent builds: LC/4PC/etc live in this same row
                cur = new_build(role_name, c3 or base_lc, c4 or base_4pc,
                                c6 or base_sub, c9 or base_eid)
            else:
                # First build: use data from first data row + pre-role collected stats
                cur = new_build(role_name, base_lc, base_4pc, base_sub, base_eid)
                cur['_main'] = pre_role_main
                cur['_ab']   = pre_role_ab
            # Ability priority items can share the Role: row
            if c7 and c7 not in HEADER_SKIP:
                cur['_ab'].append(c7)
            if c8 and c8 not in HEADER_SKIP:
                cur['_ab'].append(c8)
            after_role = True
            continue

        if cur is None:
            # Before any Role: row — collect main stats and ability priority
            if c5 and c5 not in HEADER_SKIP:
                pre_role_main.append(c5)
            if c7 and c7 not in HEADER_SKIP:
                pre_role_ab.append(c7)
            if c8 and c8 not in HEADER_SKIP:
                pre_role_ab.append(c8)
            continue

        # Notes rows
        if c2 in ('Relic Notes', 'Notes') or re.match(r'^Relic Notes', c2):
            cur['relic_notes'] = c3 or cur['relic_notes']
            continue
        if c2.startswith('Other Notes') or c2.startswith('Notes\n'):
            cur['other_notes'] = c3 or cur['other_notes']
            continue
        # Skip section label rows like "Pre 4.0 Buffs"
        if c2 and not c5 and not c7 and not c4 and not c6:
            continue

        # After role row: look for planar ornament / baseline stats row
        if after_role and not cur['planar_ornament']:
            if c4 and c4 not in HEADER_SKIP:
                cur['planar_ornament'] = c4
                cur['baseline_stats']  = c6
                cur['ability_notes']   = c9
                after_role = False

        # Main stats (col 5) — collected across many rows
        if c5 and c5 not in HEADER_SKIP:
            cur['_main'].append(c5)

        # Ability priority (col 7 + col 8)
        if c7 and c7 not in HEADER_SKIP:
            cur['_ab'].append(c7)
        if c8 and c8 not in HEADER_SKIP:
            cur['_ab'].append(c8)

    flush_build()

    if not builds:
        return None

    return {
        'name':  name,
        'path':  path,
        'builds': builds,
    }


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
        if json.dumps(new_c, sort_keys=True) != json.dumps(old_c, sort_keys=True):
            updated.append((name, 'build content changed'))
    return added, removed, updated


def main():
    # Load release dates
    dates_path = f"{_BASE_DIR}/hsr_release_dates.json"
    try:
        with open(dates_path, encoding='utf-8') as fh:
            release_dates = json.load(fh)
    except FileNotFoundError:
        release_dates = {}

    # Load Sheet 2 data (kit overview + example teams)
    s2_path = f"{_BASE_DIR}/hsr_s2.json"
    try:
        with open(s2_path, encoding='utf-8') as fh:
            s2_data = json.load(fh)
    except FileNotFoundError:
        s2_data = {}

    all_chars = {}
    files = sorted(glob.glob(f"{CACHE_DIR}/s1_*.csv"))

    for f in files:
        for char in parse_file(f):
            key = f"{char['name']}|{char['path']}"
            if key not in all_chars:
                char['release_date'] = release_dates.get(char['name'], '')
                s2 = s2_data.get(char['name'], {})
                char['kit_overview']         = s2.get('kit_overview', '')
                char['worth_pulling']        = s2.get('worth_pulling', '')
                char['recommended_baseline'] = s2.get('recommended_baseline', '')
                char['example_teams']        = s2.get('example_teams', [])
                all_chars[key] = char

    result = sorted(all_chars.values(), key=lambda c: c['name'])
    result = [c for c in result if c['builds']]

    # Load previous scrape for diffing
    try:
        with open(SCRAPE_OUTPUT, encoding='utf-8') as fh:
            old_scrape = json.load(fh)
    except FileNotFoundError:
        old_scrape = []

    with open(SCRAPE_OUTPUT, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    added, removed, updated = diff_builds(result, old_scrape)
    print(f"─── HSR scrape diff {'─'*40}")
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
        roles  = ', '.join(b['role'][:30] for b in c['builds'])
        s2_tag = f"  s2={len(c['example_teams'])}teams" if c['example_teams'] else ''
        print(f"  {c['name']:30s}  [{c['path']}]  {c['release_date']}  builds: {roles}{s2_tag}")


if __name__ == '__main__':
    main()
