#!/usr/bin/env python3
"""Parse ZZZ agent build CSVs into zzz_builds.json."""

import csv
import glob
import json
import os
import re

CACHE_DIR = "/Users/hokori/.cache/zzz_builds"
OUTPUT    = "/Users/hokori/genshin-builds/zzz_builds.json"

SKIP_NAMES = {'S Rank Agents', 'A Rank Agents', 'S Rank', 'A Rank'}

# Disc sets whose names appear only as spreadsheet images (not in any text column).
# prepend_4pc / prepend_2pc: insert before text-extracted sets.
# exclude_4pc / exclude_2pc: remove sets falsely detected from partner-disc text.
DISC_OVERRIDES = {
    # ── image-only sets: sourced from Prydwen ──────────────────────────────
    'Banyue':         {'prepend_4pc': ['Yunkui Tales']},
    'Burnice White':  {'prepend_4pc': ['Chaos Jazz']},
    'Cissia':         {'prepend_4pc': ['Astral Voice', "Dawn's Bloom", 'Thunder Metal']},
    'Ellen Joe':      {'prepend_4pc': ['Puffer Electro', 'Woodpecker Electro', 'Shadow Harmony']},
    'Komano Manato':  {'prepend_4pc': ['Yunkui Tales']},
    'Lucia Elowen':   {'prepend_4pc': ['Moonlight Lullaby']},
    'Promeia':        {'prepend_4pc': ['Notes From the Chained']},
    'Seth Lowell':    {'prepend_4pc': ['Astral Voice', 'Swing Jazz', 'Proto Punk', 'Freedom Blues']},
    'Vivian Banshee': {'prepend_4pc': ["Phaethon's Melody"]},
    'Yidhari Murphy': {'prepend_4pc': ['Yunkui Tales'], 'prepend_2pc': ['Polar Metal']},
    'Yixuan':         {'prepend_4pc': ['Yunkui Tales']},
    # ── spreadsheet image confirmed ─────────────────────────────────────────
    'Dialyn':         {'prepend_4pc': ['King of the Summit']},
    # ── text-extraction fixes ───────────────────────────────────────────────
    # "Astra must run 4PC Moonlight Lullaby" → Moonlight is Astra's, not Anton's.
    # "4PC Thunder" short form can't be safely auto-extracted.
    'Anton Ivanov':   {'exclude_4pc': ['Moonlight Lullaby'],
                       'prepend_4pc': ['Thunder Metal']},
    # "PLEASE DON'T USE 4PC FANGED" — negation context; "fanged 2pc" is correct.
    'Nekomiya Mana':  {'exclude_4pc': ['Fanged Metal']},
    # "Shockstar/King of the Summit are only to be used outside of Ye Shunguang teams"
    # — no 4pc/2pc qualifier in text so extractor defaults to 4pc; they are 2pc options.
    # 'astral' short alias catches "Astral/Hormone 2pc" putting Astral Voice in 2pc,
    # but disc_map adds it as the 4pc — can't be both simultaneously.
    'Sunna':          {'exclude_4pc': ['King of the Summit', 'Shockstar Disco'],
                       'exclude_2pc': ['Astral Voice']},
}
NOTE_LABELS = {'Disc Drive Notes', 'Mindscapes', 'Other Notes', 'Team Comps'}
HEADER_VALS = {'Equipment', 'Drive Disc Stats', 'Ability Priority',
               'W-Engines', '4 Piece Drive Disc Set', 'Main Stats', 'Sub stats',
               '2 Piece Drive Disc Set', 'Baseline Stats'}

# Canonical disc set names from the ZZZ fandom wiki (Category:Drive_Discs)
DISC_SETS = [
    "Assassin's Ballad", 'Astral Voice', 'Branch & Blade Song', 'Bunny in Wonderland',
    'Chaos Jazz', 'Chaotic Metal', "Dawn's Bloom", 'Doom Grindcore', 'Ecstatic Punk',
    'Fanged Metal', 'Freedom Blues', 'Hormone Punk', 'Inferno Metal', 'King of the Summit',
    'Mammoth Electro', 'Monsoon Funk', 'Moonlight Lullaby', 'Noisy Pop',
    'Notes From the Chained', "Phaethon's Melody", 'Polar Metal', 'Proto Punk',
    'Puffer Electro', 'Shadow Harmony', 'Shining Aria', 'Shockstar Disco', 'Soul Rock',
    'Swing Jazz', 'Thunder Metal', 'Twisted Grindcore', 'Unicorn Electro',
    'Vagabond Folk', 'White Water Ballad', 'Woodpecker Electro', 'Yunkui Tales',
]

# Abbreviations / partial names that reliably identify a specific set
# Ordered longest-first so longer matches take priority
DISC_ALIASES = [
    ('branch & blade song',  'Branch & Blade Song'),
    ('branch & blade',       'Branch & Blade Song'),
    ("assassin's ballad",    "Assassin's Ballad"),
    ('astral voice',         'Astral Voice'),
    ('bunny in wonderland',  'Bunny in Wonderland'),
    ("dawn's bloom",         "Dawn's Bloom"),
    ('doom grindcore',       'Doom Grindcore'),
    ('ecstatic punk',        'Ecstatic Punk'),
    ('chaos jazz',           'Chaos Jazz'),
    ('chaotic metal',        'Chaotic Metal'),
    ('fanged metal',         'Fanged Metal'),
    ('freedom blues',        'Freedom Blues'),
    ('hormone punk',         'Hormone Punk'),
    ('inferno metal',        'Inferno Metal'),
    ('king of the summit',   'King of the Summit'),
    ('mammoth electro',      'Mammoth Electro'),
    ('monsoon funk',         'Monsoon Funk'),
    ('moonlight lullaby',    'Moonlight Lullaby'),
    ('noisy pop',            'Noisy Pop'),
    ('notes from the chained', 'Notes From the Chained'),
    ("phaethon's melody",    "Phaethon's Melody"),
    ('polar metal',          'Polar Metal'),
    ('proto punk',           'Proto Punk'),
    ('puffer electro',       'Puffer Electro'),
    ('shadow harmony',       'Shadow Harmony'),
    ('shining aria',         'Shining Aria'),
    ('shockstar disco',      'Shockstar Disco'),
    ('soul rock',            'Soul Rock'),
    ('swing jazz',           'Swing Jazz'),
    ('thunder metal',        'Thunder Metal'),
    ('twisted grindcore',    'Twisted Grindcore'),
    ('unicorn electro',      'Unicorn Electro'),
    ('vagabond folk',        'Vagabond Folk'),
    ('white water ballad',   'White Water Ballad'),
    ('woodpecker electro',   'Woodpecker Electro'),
    ('woodpecker',           'Woodpecker Electro'),
    ('yunkui tales',         'Yunkui Tales'),
    ('yunkui',               'Yunkui Tales'),
    # Phaethon without apostrophe-s (common in notes)
    ('phaethon melody',      "Phaethon's Melody"),
    ('phaethon',             "Phaethon's Melody"),
    # Short single-word forms that reliably name one set
    ('freedom blues',        'Freedom Blues'),   # already above, but also catch bare:
    ('freedom',              'Freedom Blues'),
    ('chaos jazz',           'Chaos Jazz'),      # already above, also catch bare:
    ('chaos',                'Chaos Jazz'),
    # Alternate conjunctions in multi-word names
    ('branch and blade song', 'Branch & Blade Song'),
    ('branch and blade',     'Branch & Blade Song'),
    # Short but reliable abbreviations
    ('astral',               'Astral Voice'),
    ('fanged',               'Fanged Metal'),  # "using fanged 2pc"
    ('fang',                 'Fanged Metal'),  # "4PC Fang"
    ('hormone',              'Hormone Punk'),
    ('moonlight',            'Moonlight Lullaby'),
    ('puffer',               'Puffer Electro'),
    ('shockstar',            'Shockstar Disco'),
    # NOTE: 'polar' excluded — false-positive on "polarity" in descriptions
    # NOTE: 'thunder' excluded — false-positive on "chasing thunder" mechanic text
]


# ZZZ character name/nickname aliases for team comp text mining.
# Longest entries first so longer aliases take priority over shorter substrings.
_ZZZ_CHAR_ALIASES = [
    ('ye shunguang', 'Ye Shunguang'),
    ('nangong yu',   'Nangong Yu'),
    ('pan yinhu',    'Pan Yinhu'),
    ('zhu yuan',     'Zhu Yuan'),
    ('von lycaon',   'Von Lycaon'),
    ('soldier 11',   'Soldier 11 (Harin)'),
    ('soldier 0',    'Soldier 0 - Anby'),
    ('alexandrina',  'Alexandrina Sebastiane (Rina)'),
    ('harumasa',     'Asaba Harumasa'),
    ('tsukishiro',   'Tsukishiro Yanagi'),
    ('shunguang',    'Ye Shunguang'),
    ('nekomiya',     'Nekomiya Mana'),
    ('ukinami',      'Ukinami Yuzuha'),
    ('yuzuha',       'Ukinami Yuzuha'),
    ('miyabi',       'Hoshimi Miyabi'),
    ('manato',       'Komano Manato'),
    ('yidhari',      'Yidhari Murphy'),
    ('lycaon',       'Von Lycaon'),
    ('yanagi',       'Tsukishiro Yanagi'),
    ('evelyn',       'Evelyn Chevalier'),
    ('dialyn',       'Dialyn'),
    ('lighter',      'Lighter'),
    ('orphie',       'Orphie Magnusson & Magus'),
    ('pulchra',      'Pulchra Fellini'),
    ('burnice',      'Burnice White'),
    ('koleda',       'Koleda Belobog'),
    ('vivian',       'Vivian Banshee'),
    ('promeia',      'Promeia'),
    ('trigger',      'Trigger'),
    ('soukaku',      'Soukaku'),
    ('nangong',      'Nangong Yu'),
    ('sunna',        'Sunna'),
    ('yixuan',       'Yixuan'),
    ('banyue',       'Banyue'),
    ('qingyi',       'Qingyi'),
    ('cissia',       'Cissia'),
    ('yuzu',         'Ukinami Yuzuha'),
    ('harin',        'Soldier 11 (Harin)'),
    ('astra',        'Astra Yao'),
    ('nicole',       'Nicole Demara'),
    ('grace',        'Grace Howard'),
    ('ellen',        'Ellen Joe'),
    ('piper',        'Piper Wheel'),
    ('corin',        'Corin Wickes'),
    ('alice',        'Alice Thymefield'),
    ('hugo',         'Hugo Vlad'),
    ('billy',        'Billy Kid'),
    ('fufu',         'Ju Fufu'),
    ('aria',         'Aria'),
    ('zhao',         'Zhao'),
    ('seed',         'Flora (Seed)'),
    ('flora',        'Flora (Seed)'),
    ('lucia',        'Lucia Elowen'),
    ('lucy',         'Luciana Auxesis Theodoro de Montefio (Lucy)'),
    ('anby',         'Anby Demara'),
    ('jane',         'Jane Doe'),
    ('seth',         'Seth Lowell'),
    ('mana',         'Nekomiya Mana'),
    ('rina',         'Alexandrina Sebastiane (Rina)'),
    ('s11',          'Soldier 11 (Harin)'),
    ('ben',          'Ben Bigger'),
    ('anton',        'Anton Ivanov'),
]

_ZZZ_ALIAS_RES = [
    (re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE), canon)
    for alias, canon in _ZZZ_CHAR_ALIASES
]


def mine_chars(text: str) -> list:
    """Return canonical ZZZ character names found in text via word-boundary alias search."""
    found: list = []
    seen: set = set()
    for pat, canon in _ZZZ_ALIAS_RES:
        if canon not in seen and pat.search(text):
            found.append(canon)
            seen.add(canon)
    return found


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


def normalize(text):
    """Normalize smart quotes and whitespace for disc name matching."""
    return (text
            .replace('’', "'").replace('‘', "'")
            .replace('“', '"').replace('”', '"')
            .lower())


_PC4 = re.compile(r'\b4[\s\-]?p(?:c|iece)\b')
_PC2 = re.compile(r'\b2[\s\-]?p(?:c|iece)\b')


def _nearest_pc(norm, idx, alias_len, window=40):
    """Return '4', '2', or None for the pc-marker closest to position idx."""
    before = norm[max(0, idx - window):idx]
    after  = norm[idx + alias_len:idx + alias_len + window]

    # Find the rightmost marker in before and leftmost in after
    m4b = list(_PC4.finditer(before))
    m2b = list(_PC2.finditer(before))
    m4a = list(_PC4.finditer(after))
    m2a = list(_PC2.finditer(after))

    candidates = []
    if m4b:
        candidates.append(('4', -(len(before) - m4b[-1].end())))  # negative = behind
    if m2b:
        candidates.append(('2', -(len(before) - m2b[-1].end())))
    if m4a:
        candidates.append(('4', m4a[0].start()))
    if m2a:
        candidates.append(('2', m2a[0].start()))

    if not candidates:
        return None
    # Pick the marker with the smallest absolute distance to the alias
    candidates.sort(key=lambda x: abs(x[1]))
    return candidates[0][0]


_PARTNER_DISC_RE = re.compile(
    r'(?:'
    r'teammate\s+\S+\s+holding'            # "teammate X holding"
    r'|a\s+teammate\s+holds'
    r'|certain\s+\w[\w\s,]+\brun\b'        # "certain DPS agents ... run"
    r'|dps\s+agents?\s+\w[\w\s,]+\brun\b'
    r'|it\s+is\s+recommended\s+that\s+\w[\w\s,]+\brun\b'
    r'|\w+\s+must\s+(?:run|use|carry)\b'   # "[Name] must run/use/carry"
    r'|\w+\s+needs?\s+to\s+(?:run|use|carry)\b'
    r')',
    re.IGNORECASE,
)

def _strip_partner_disc_sentences(text):
    """Remove sentences that describe disc recommendations for *partner* characters."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    kept = [s for s in sentences if not _PARTNER_DISC_RE.search(s)]
    return ' '.join(kept)


def extract_disc_sets(text):
    """Return {'4pc': [names], '2pc': [names]} extracted from free text."""
    text = _strip_partner_disc_sentences(text)
    norm = normalize(text)
    found_4 = []
    found_2 = []
    consumed = set()

    for alias, canonical in DISC_ALIASES:
        pos = 0
        while True:
            idx = norm.find(alias, pos)
            if idx == -1:
                break
            # Skip if this start position was already claimed by a longer alias
            if idx in consumed:
                pos = idx + 1
                continue

            for k in range(idx, idx + len(alias)):
                consumed.add(k)

            pc = _nearest_pc(norm, idx, len(alias))
            if pc == '4':
                if canonical not in found_4:
                    found_4.append(canonical)
            elif pc == '2':
                if canonical not in found_2:
                    found_2.append(canonical)
            else:
                # No explicit qualifier: default to 4PC
                if canonical not in found_4 and canonical not in found_2:
                    found_4.append(canonical)
            pos = idx + len(alias)

    return {'4pc': found_4, '2pc': found_2}


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

    name = rows[0][1].strip()
    last_updated = rows[1][1].strip().replace('Last Updated:', '').replace('Last updated:', '').strip()

    # Header row (rows[2]): col[3] = specialty
    hdr = pad(rows[2])
    specialty = hdr[3].strip()

    w_engines     = []
    main_stats    = []
    ability_left  = []   # col 30
    ability_right = []   # col 31
    sub_stats     = ''
    baseline      = ''
    role          = ''
    disc_notes    = ''
    w_engine_notes = ''
    mindscapes    = ''
    other_notes   = ''
    team_general  = ''
    team_comps    = []

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
                if tm_entry:
                    team_comps = [
                        {"label": t["label"], "chars": t["members"]}
                        for t in tm_entry
                        if len(t["members"]) >= 3
                    ]
                else:
                    team_comps = [{"label": lbl, "chars": mine_chars(lbl)} for lbl in named]
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
        if c24 and c24 not in HEADER_VALS:
            main_stats.append(c24)

        # Sub stats: col 27 (first non-header, non-baseline occurrence)
        if c27 and c27 not in HEADER_VALS and not sub_stats and not baseline:
            sub_stats = c27

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
        'last_updated': last_updated,
        'builds': [{
            'role':         role or specialty,
            'w_engines':    '\n'.join(w_engines),
            'main_stats':   '\n'.join(main_stats),
            'sub_stats':    sub_stats,
            'baseline':     baseline,
            'ability':      '\n'.join(ability_clean),
            'disc_4pc':     disc_sets['4pc'],
            'disc_2pc':     disc_sets['2pc'],
            'w_engine_notes': w_engine_notes,
            'disc_notes':   disc_notes,
            'mindscapes':   mindscapes,
            'other_notes':  other_notes,
            'team_general': team_general,
            'team_comps':   team_comps,
        }],
    }


def main():
    all_agents = {}
    for f in sorted(glob.glob(f"{CACHE_DIR}/agents_*.csv")):
        for agent in parse_file(f):
            if agent['name'] not in all_agents:
                all_agents[agent['name']] = agent

    result = sorted(all_agents.values(), key=lambda a: a['name'])

    with open(OUTPUT, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(f"Wrote {len(result)} agents to {OUTPUT}")
    for a in result:
        b = a['builds'][0]
        d4 = ', '.join(b['disc_4pc']) or '—'
        d2 = ', '.join(s if isinstance(s, str) else '/'.join(s) for s in b['disc_2pc']) or '—'
        print(f"  {a['name']:40s}  4pc: {d4[:35]:35s}  2pc: {d2[:30]}")


if __name__ == '__main__':
    main()
