#!/usr/bin/env python3
"""Fetch release version and date for every character from fandom wikis.

Output: release_data.json
  { "gi":  { "AINO": {"version": "5.5", "date": "2025-09-10"}, … },
    "hsr": { "Acheron": {"version": "1.5", "date": "2024-03-27"}, … },
    "zzz": { "Astra Yao": {"version": "1.4", "date": "2025-01-14"}, … } }
"""

import json
import re
import time
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).parent / 'release_data.json'

WIKIS = {
    'gi':  'genshin-impact.fandom.com',
    'hsr': 'honkai-star-rail.fandom.com',
    'zzz': 'zenless-zone-zero.fandom.com',
}

# Characters whose wiki page name differs from the normalised name
WIKI_PAGE = {
    'gi': {
        'TRAVELER':         'Traveler',
        'ARATAKI ITTO':     'Arataki_Itto',
        'HU TAO':           'Hu_Tao',
        'KAEDEHARA KAZUHA': 'Kaedehara_Kazuha',
        'KAMISATO AYAKA':   'Kamisato_Ayaka',
        'KAMISATO AYATO':   'Kamisato_Ayato',
        'KUJOU SARA':       'Kujou_Sara',
        'KUKI SHINOBU':     'Kuki_Shinobu',
        'LAN YAN':          'Lan_Yan',
        'RAIDEN SHOGUN':    'Raiden_Shogun',
        'SANGONOMIYA KOKOMI': 'Sangonomiya_Kokomi',
        'SHIKANOIN HEIZOU': 'Shikanoin_Heizou',
        'YAE MIKO':         'Yae_Miko',
        'YUMEMIZUKI MIZUKI':'Yumemizuki_Mizuki',
        'YUN JIN':          'Yun_Jin',
    },
    'hsr': {
        'Imbibitor Lunae':  'Dan_Heng_%E2%80%A2_Imbibitor_Lunae',
        'Permansor Terrae': 'Dan_Heng_%E2%80%A2_Permansor_Terrae',
        'Topaz & Numby':    'Topaz_%26_Numby',
        'Trailblazer':      'Trailblazer',
        'March 7th':        'March_7th',
        'Dr. Ratio':        'Dr._Ratio',
        'Silver Wolf LV.999': 'Silver_Wolf_LV.999',
    },
    'zzz': {
        'Flora (Seed)':              'Seed',
        'Soldier 11 (Harin)':        'Soldier_11',
        'Alexandrina Sebastiane (Rina)': 'Alexandrina_Sebastiane',
        'Orphie Magnusson & Magus':  'Orphie_Magnusson_%26_Magus',
        'Soldier 0 - Anby':          'Soldier_0_-_Anby',
    },
}

# GI: patch release dates → version string (for launch-era chars without Change History)
GI_DATE_TO_VERSION = {
    '2020-09-28': '1.0', '2020-11-11': '1.1', '2020-12-23': '1.2',
    '2021-02-03': '1.3', '2021-03-17': '1.4', '2021-04-28': '1.5',
    '2021-06-09': '1.6', '2021-07-21': '2.0', '2021-09-01': '2.1',
    '2021-10-13': '2.2', '2021-11-24': '2.3', '2022-01-05': '2.4',
    '2022-02-16': '2.5', '2022-03-30': '2.6', '2022-05-31': '2.7',
    '2022-07-13': '2.8', '2022-08-24': '3.0', '2022-09-28': '3.1',
    '2022-11-02': '3.2', '2022-12-07': '3.3', '2023-01-18': '3.4',
    '2023-03-01': '3.5', '2023-04-12': '3.6', '2023-05-24': '3.7',
    '2023-07-05': '3.8', '2023-08-16': '4.0', '2023-09-27': '4.1',
    '2023-11-08': '4.2', '2023-12-20': '4.3', '2024-01-31': '4.4',
    '2024-03-13': '4.5', '2024-04-24': '4.6', '2024-06-05': '4.7',
    '2024-07-17': '4.8', '2024-08-28': '5.0', '2024-10-09': '5.1',
    '2024-11-20': '5.2', '2025-01-01': '5.3', '2025-02-12': '5.4',
    '2025-03-26': '5.5', '2025-05-07': '5.6', '2025-06-18': '5.7',
    '2025-07-30': '5.8', '2025-09-10': '5.9',
}

# HSR: patch release dates → version string
HSR_DATE_TO_VERSION = {
    '2023-04-26': '1.0', '2023-06-07': '1.1', '2023-07-19': '1.2',
    '2023-08-30': '1.3', '2023-10-11': '1.4', '2023-11-15': '1.5',
    '2023-12-27': '1.6', '2024-01-31': '2.0', '2024-03-13': '2.1',
    '2024-04-24': '2.2', '2024-06-05': '2.3', '2024-07-17': '2.4',
    '2024-08-28': '2.5', '2024-10-09': '2.6', '2024-11-20': '2.7',
    '2025-01-01': '3.0', '2025-02-12': '3.1', '2025-03-26': '3.2',
    '2025-05-07': '3.3', '2025-06-18': '3.4', '2025-07-30': '3.5',
    '2025-09-10': '3.6', '2025-10-22': '3.7', '2025-12-03': '3.8',
}

# ZZZ: patch release dates → version string
ZZZ_DATE_TO_VERSION = {
    '2024-07-04': '1.0', '2024-08-14': '1.1', '2024-09-25': '1.2',
    '2024-11-06': '1.3', '2024-12-18': '1.4', '2025-01-29': '1.5',
    '2025-03-05': '2.0', '2025-04-16': '2.1', '2025-05-28': '2.2',
    '2025-07-09': '2.3', '2025-08-20': '2.4', '2025-10-01': '2.5',
    '2025-11-12': '2.6', '2025-12-24': '2.7', '2026-02-04': '2.8',
    '2026-03-18': '3.0', '2026-04-29': '3.1', '2026-06-10': '3.2',
}


def to_wiki_name(name, game):
    if game == 'gi':
        name = name.title()
    name = re.sub(r'\s*\([^)]+\)$', '', name).strip()
    return name.replace(' ', '_')


def fetch_release(wiki, page):
    url = (f'https://{wiki}/api.php?action=parse&page={page}'
           f'&prop=wikitext&format=json')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        wt = d.get('parse', {}).get('wikitext', {}).get('*', '')
        if not wt:
            return None, None
        ver = None
        date = None
        m = re.search(r'introduced\s*=\s*([0-9]+\.[0-9]+)', wt)
        if m:
            ver = m.group(1)
        for pat in [r'releaseDate\s*=\s*([\d]{4}-[\d]{2}-[\d]{2})',
                    r'release_date\s*=\s*([\d]{4}-[\d]{2}-[\d]{2})']:
            m = re.search(pat, wt)
            if m:
                date = m.group(1)
                break
        return ver, date
    except Exception as e:
        print(f'    error {page}: {e}')
        return None, None


def resolve(name, game, ver, date):
    """Ensure we have both a version string and a date string."""
    if ver and date:
        return ver, date
    if ver and not date:
        # version known but no date — leave date as None (still useful for display)
        return ver, None
    if date and not ver:
        # map date → version
        lookup = (GI_DATE_TO_VERSION if game == 'gi'
                  else HSR_DATE_TO_VERSION if game == 'hsr'
                  else ZZZ_DATE_TO_VERSION)
        # find closest date key on or before this date
        ver = lookup.get(date)
        if not ver:
            # find nearest key
            candidates = [k for k in lookup if k <= date]
            if candidates:
                ver = lookup[max(candidates)]
        return ver, date
    return None, None


def fetch_game(game, chars):
    wiki = WIKIS[game]
    page_overrides = WIKI_PAGE.get(game, {})
    results = {}
    seen = set()

    for char in chars:
        name = char['name']
        if name in seen:
            continue
        seen.add(name)

        if name in page_overrides:
            page = page_overrides[name]
        else:
            page = to_wiki_name(name, game)

        ver, date = fetch_release(wiki, page)
        ver, date = resolve(name, game, ver, date)

        if ver:
            results[name] = {'version': ver, 'date': date or ''}
            print(f'  ✓  {name}: v{ver} ({date or "?"})')
        else:
            results[name] = {'version': '', 'date': date or ''}
            print(f'  ✗  {name}: no version found (date={date})')

        time.sleep(0.3)

    return results


def main():
    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        total = sum(len(v) for v in existing.values())
        print(f'Loaded existing release_data.json ({total} entries)')

    gi_chars  = json.loads((Path(__file__).parent / 'builds.json').read_text())
    hsr_chars = json.loads((Path(__file__).parent / 'hsr_builds.json').read_text())
    zzz_chars = json.loads((Path(__file__).parent / 'zzz_builds.json').read_text())

    result = {
        'gi':  existing.get('gi', {}),
        'hsr': existing.get('hsr', {}),
        'zzz': existing.get('zzz', {}),
    }

    for game, chars in [('gi', gi_chars), ('hsr', hsr_chars), ('zzz', zzz_chars)]:
        missing = [c for c in chars if c['name'] not in result[game]]
        if not missing:
            print(f'{game.upper()}: all {len(result[game])} entries cached')
            continue
        print(f'\n{game.upper()}: fetching {len(missing)} release versions...')
        new = fetch_game(game, missing)
        result[game].update(new)
        found = sum(1 for v in new.values() if v['version'])
        print(f'  → {found}/{len(missing)} versions found')

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    totals = {g: len(v) for g, v in result.items()}
    print(f'\nWrote release_data.json — GI: {totals["gi"]}, '
          f'HSR: {totals["hsr"]}, ZZZ: {totals["zzz"]}')


if __name__ == '__main__':
    main()
