#!/usr/bin/env python3
"""Parse ZZZ agent build CSVs into zzz_builds.json."""

import csv
import glob
import json
import os
import re

CACHE_DIR     = "/Users/hokori/.cache/zzz_builds"
SCRAPE_OUTPUT = "/Users/hokori/genshin-builds/zzz_builds_scrape.json"
CANONICAL     = "/Users/hokori/genshin-builds/zzz_builds.json"  # user-editable; never written by parser

SKIP_NAMES = {'S Rank Agents', 'A Rank Agents', 'S Rank', 'A Rank'}

ZZZ_NAME_NORMALIZE = {
    "Alice Thymefield":                            "Alice",
    "Anby Demara":                                 "Anby",
    "Anton Ivanov":                                "Anton",
    "Asaba Harumasa":                              "Harumasa",
    "Ben Bigger":                                  "Ben",
    "Billy Kid":                                   "Billy",
    "Burnice White":                               "Burnice",
    "Caesar King":                                 "Caesar",
    "Corin Wickes":                                "Corin",
    "Ellen Joe":                                   "Ellen",
    "Evelyn Chevalier":                            "Evelyn",
    "Flora (Seed)":                                "Seed",
    "Grace Howard":                                "Grace",
    "Hoshimi Miyabi":                              "Miyabi",
    "Hugo Vlad":                                   "Hugo",
    "Koleda Belobog":                              "Koleda",
    "Komano Manato":                               "Manato",
    "Lucia Elowen":                                "Lucia",
    "Luciana Auxesis Theodoro de Montefio (Lucy)": "Lucy",
    "Nekomiya Mana":                               "Nekomata",
    "Nicole Demara":                               "Nicole",
    "Orphie Magnusson & Magus":                    "Orphie & Magus",
    "Piper Wheel":                                 "Piper",
    "Pulchra Fellini":                             "Pulchra",
    "Seth Lowell":                                 "Seth",
    "Soldier 0 - Anby":                            "Anby: Soldier 0",
    "Soldier 11 (Harin)":                          "Soldier 11",
    "Tsukishiro Yanagi":                           "Yanagi",
    "Ukinami Yuzuha":                              "Yuzuha",
    "Vivian Banshee":                              "Vivian",
    "Von Lycaon":                                  "Lycaon",
    "Yidhari Murphy":                              "Yidhari",
    "Alexandrina Sebastiane (Rina)":               "Rina",
}

ZZZ_ELEMENT = {
    # Physical
    "Alice":      "Physical",
    "Banyue":     "Physical",
    "Billy":      "Physical",
    "Caesar":     "Physical",
    "Corin":      "Physical",
    "Dialyn":     "Physical",
    "Seed":       "Physical",
    "Jane Doe":   "Physical",
    "Nekomata":   "Physical",
    "Pan Yinhu":  "Physical",
    "Piper":      "Physical",
    "Pulchra":    "Physical",
    "Sunna":      "Physical",
    # Fire
    "Ben":           "Fire",
    "Burnice":       "Fire",
    "Evelyn":        "Fire",
    "Ju Fufu":       "Fire",
    "Koleda":        "Fire",
    "Manato":        "Fire",
    "Lighter":       "Fire",
    "Lucy":          "Fire",
    "Nangong Yu":    "Fire",
    "Soldier 11":    "Fire",
    # Electric
    "Rina":              "Electric",
    "Anby":              "Electric",
    "Anton":             "Electric",
    "Harumasa":          "Electric",
    "Cissia":            "Electric",
    "Grace":             "Electric",
    "Hugo":              "Electric",
    "Qingyi":            "Electric",
    "Seth":              "Electric",
    "Anby: Soldier 0":   "Electric",
    "Trigger":           "Electric",
    "Yanagi":            "Electric",
    "Yuzuha":            "Electric",
    # Ice
    "Ellen":           "Ice",
    "Miyabi":          "Ice",
    "Lucia":           "Ice",
    "Orphie & Magus":  "Ice",
    "Soukaku":         "Ice",
    "Lycaon":          "Ice",
    "Ye Shunguang":    "Ice",
    "Yidhari":         "Ice",
    "Zhao":            "Ice",
    # Ether
    "Aria":     "Ether",
    "Astra Yao": "Ether",
    "Nicole":   "Ether",
    "Promeia":  "Ether",
    "Vivian":   "Ether",
    "Yixuan":   "Ether",
    "Zhu Yuan": "Ether",
}
HEADER_VALS = {'Equipment', 'Drive Disc Stats', 'Ability Priority',
               'W-Engines', '4 Piece Drive Disc Set', 'Main Stats', 'Sub stats',
               '2 Piece Drive Disc Set', 'Baseline Stats'}

_DISC_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disc_map.json")
_disc_map: dict = {}
if os.path.exists(_DISC_MAP_PATH):
    with open(_DISC_MAP_PATH, encoding="utf-8") as _f:
        _disc_map = json.load(_f)

_TEAM_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_map.json")
_team_map: dict = {}
if os.path.exists(_TEAM_MAP_PATH):
    with open(_TEAM_MAP_PATH, encoding="utf-8") as _f:
        _team_map = json.load(_f)


def pad(row, n=35):
    while len(row) < n:
        row.append('')
    return row


def is_char_header(rows, i):
    row = rows[i]
    non_empty = [(j, c.strip()) for j, c in enumerate(row) if c.strip()]
    if len(non_empty) != 1 or non_empty[0][0] != 1:
        return False
    name = non_empty[0][1]
    if name in SKIP_NAMES or name.lower().startswith('last updated'):
        return False
    if len(name) < 2:
        return False
    # Confirm next row has "Last Updated:" (case-insensitive)
    if i + 1 < len(rows):
        nxt = rows[i + 1]
        nxt_val = nxt[1].strip() if len(nxt) > 1 else ''
        if nxt_val.lower().startswith('last updated'):
            return True
    return False


def parse_file(filepath):
    with open(filepath, newline='', encoding='utf-8') as fh:
        all_rows = list(csv.reader(fh))

    char_starts = [i for i in range(len(all_rows)) if is_char_header(all_rows, i)]
    results = []
    for ci, start in enumerate(char_starts):
        end = char_starts[ci + 1] if ci + 1 < len(char_starts) else len(all_rows)
        char = parse_block(all_rows[start:end])
        if char:
            results.append(char)
    return results


def parse_block(rows):
    if len(rows) < 3:
        return None

    name = ZZZ_NAME_NORMALIZE.get(rows[0][1].strip(), rows[0][1].strip())
    last_updated = rows[1][1].strip().replace('Last Updated:', '').replace('Last updated:', '').strip()

    # Header row (rows[2]): col[3] = specialty
    hdr = pad(rows[2])
    specialty = hdr[3].strip()

    w_engines     = []
    main_stats    = []
    ability_left  = []   # col 30
    ability_right = []   # col 31
    sub_stats      = ''
    baseline       = ''
    role           = ''
    disc_notes     = ''
    w_engine_notes = ''
    mindscapes     = ''
    other_notes    = ''
    team_general   = ''
    team_comps     = []
    disc_4pc_labels = []
    disc_2pc_labels = []

    in_team = False

    for row in rows[2:]:
        row = pad(row)
        c3  = row[3].strip()
        c5  = row[5].strip()
        c6  = row[6].strip()
        c24 = row[24].strip()
        c27 = row[27].strip()
        c28 = row[28].strip()
        c30 = row[30].strip()
        c31 = row[31].strip()

        # Skip header / sub-header rows
        if c5 in HEADER_VALS or c24 in HEADER_VALS or c3 in ('S Rank Agents', 'A Rank Agents'):
            continue

        # Labeled rows
        if c3 == 'W-Engine Notes':
            w_engine_notes = c5
            continue
        if c3 == 'Disc Drive Notes':
            disc_notes = c5
            in_team = False
            continue
        if c3 == 'Mindscapes':
            mindscapes = c5
            continue
        if c3 == 'Other Notes':
            other_notes = c5
            continue
        if c3 == 'Team Comps':
            in_team = True
            continue

        if in_team:
            if c28 and not team_general:
                team_general = c28
            named = [row[j].strip() for j in (3, 6, 12, 24, 27) if row[j].strip()]
            if named and not c28:
                tm_entry = _team_map.get(name, {}).get("teams", [])
                team_comps = []
                for t in tm_entry:
                    members = t["members"]
                    if name not in members:
                        members = [name] + members
                    if len(members) >= 2:
                        team_comps.append({"label": t["label"], "chars": members})
            continue

        # Role row
        if c3.startswith('Role'):
            role = re.sub(r'^Role\s*:?\s*', '', c3).strip()
            if c27 and c27 not in HEADER_VALS:
                baseline = c27
            in_team = False

        # W-Engine: col 6
        if c6 and c6 not in HEADER_VALS:
            w_engines.append(c6)

        # Main stats: col 24
        # 2pc disc labels appear at cols 8/12/16/20 on the last main-stat row
        if c24 and c24 not in HEADER_VALS:
            main_stats.append(c24)
            for _col in (8, 12, 16, 20):
                _v = row[_col].strip()
                if _v and _v not in HEADER_VALS:
                    disc_2pc_labels.append(_v)

        # Sub stats: col 27 (first non-header, non-baseline occurrence)
        # 4pc disc labels appear at cols 8/12/16/20 on this same row
        if c27 and c27 not in HEADER_VALS and not sub_stats and not baseline:
            sub_stats = c27
            for _col in (8, 12, 16, 20):
                _v = row[_col].strip()
                if _v and _v not in HEADER_VALS:
                    disc_4pc_labels.append(_v)

        # Ability priority: cols 30 & 31
        if c30 and c30 not in HEADER_VALS:
            ability_left.append(c30)
        if c31 and c31 not in HEADER_VALS:
            ability_right.append(c31)

    # Merge ability priority
    ability = []
    for a, b in zip(ability_left, ability_right):
        if a: ability.append(a)
        if b: ability.append(b)
    for extra in ability_left[len(ability_right):]:
        if extra: ability.append(extra)
    for extra in ability_right[len(ability_left):]:
        if extra: ability.append(extra)
    ability_clean = []
    for line in ability:
        if not ability_clean or line != ability_clean[-1]:
            ability_clean.append(line)

    # Disc sets come exclusively from disc_map.json (image recognition).
    dm = _disc_map.get(name, {})
    disc_sets = {
        '4pc': list(dm.get('4pc', [])),
        '2pc': list(dm.get('2pc', [])),
    }

    return {
        'name':         name,
        'specialty':    specialty,
        'element':      '',          # filled in by main()
        'last_updated': last_updated,
        'builds': [{
            'role':         role or specialty,
            'w_engines':    '\n'.join(w_engines),
            'main_stats':   '\n'.join(main_stats),
            'sub_stats':    sub_stats,
            'baseline':     baseline,
            'ability':      '\n'.join(ability_clean),
            'disc_4pc':        disc_sets['4pc'],
            'disc_2pc':        disc_sets['2pc'],
            'disc_4pc_labels': disc_4pc_labels,
            'disc_2pc_labels': disc_2pc_labels,
            'w_engine_notes': w_engine_notes,
            'disc_notes':   disc_notes,
            'mindscapes':   mindscapes,
            'other_notes':  other_notes,
            'team_general': team_general,
            'team_comps':   team_comps,
        }],
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
        if new_c.get('last_updated') != old_c.get('last_updated'):
            updated.append((name, f"{old_c.get('last_updated')!r} → {new_c.get('last_updated')!r}"))
        elif json.dumps(new_c, sort_keys=True) != json.dumps(old_c, sort_keys=True):
            updated.append((name, 'build content changed'))
    return added, removed, updated


def main():
    all_agents = {}
    for f in sorted(glob.glob(f"{CACHE_DIR}/agents_*.csv")):
        for agent in parse_file(f):
            if agent['name'] not in all_agents:
                agent['element'] = ZZZ_ELEMENT.get(agent['name'], '')
                all_agents[agent['name']] = agent

    result = sorted(all_agents.values(), key=lambda a: a['name'])

    # Load previous scrape for diffing
    try:
        with open(SCRAPE_OUTPUT, encoding='utf-8') as fh:
            old_scrape = json.load(fh)
    except FileNotFoundError:
        old_scrape = []

    with open(SCRAPE_OUTPUT, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    added, removed, updated = diff_builds(result, old_scrape)
    print(f"─── ZZZ scrape diff {'─'*40}")
    print(f"  NEW     ({len(added)}):  {', '.join(added) or '(none)'}")
    if updated:
        for name, reason in updated:
            print(f"  UPDATED:  {name}  [{reason}]")
    else:
        print(f"  UPDATED (0):  (none)")
    print(f"  REMOVED ({len(removed)}):  {', '.join(removed) or '(none)'}")
    print(f"\nWrote {len(result)} agents to {SCRAPE_OUTPUT}")
    print(f"Canonical ({CANONICAL}) NOT modified — apply updates manually.")

    for a in result:
        b = a['builds'][0]
        d4 = ', '.join(b['disc_4pc']) or '—'
        d2 = ', '.join(s if isinstance(s, str) else '/'.join(s) for s in b['disc_2pc']) or '—'
        print(f"  {a['name']:40s}  4pc: {d4[:35]:35s}  2pc: {d2[:30]}")


if __name__ == '__main__':
    main()
