#!/usr/bin/env python3
"""Fetch item icon URLs (weapons, artifacts, light cones, relics, W-engines, drive discs).

Outputs to item_icons.json. Re-running only fetches missing entries.

Patterns confirmed via wiki API:
  GI  weapons:   Weapon_{Name}.png
  GI  artifacts: Item_{Name}.png
  HSR light cones: Light_Cone_{Name}.png
  HSR relics/planars: Item_{Name}.png
  ZZZ W-engines: W-Engine_{Name}.png
  ZZZ disc sets: Drive Disc {Name} Icon.png  (spaces, not underscores)
"""

import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT = ROOT / 'item_icons.json'

WIKIS = {
    'gi':  'genshin-impact.fandom.com',
    'hsr': 'honkai-star-rail.fandom.com',
    'zzz': 'zenless-zone-zero.fandom.com',
}


def fetch_url(wiki, filename):
    api_url = (
        f'https://{wiki}/api.php?action=query'
        f'&titles=File:{urllib.parse.quote(filename)}'
        f'&prop=imageinfo&iiprop=url&format=json'
    )
    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for page in data.get('query', {}).get('pages', {}).values():
            if page.get('missing') is not None:
                return None
            imgs = page.get('imageinfo', [])
            if imgs:
                return imgs[0]['url']
    except Exception as e:
        print(f'    error: {e}')
    return None


def to_wiki_name(name):
    return name.replace(' ', '_')


def normalize_name(name):
    """Strip build-text noise to get a clean item name for wiki lookup."""
    name = re.sub(r'\s*\d+[★✩⭐]\s*$', '', name)      # "5★" suffix
    name = re.sub(r'\s*\[[^\]]*\]\s*$', '', name)      # "[Battle Pass]" etc.
    name = re.sub(r'\s*[¹²³⁴⁵⁶⁷⁸⁹]+\s*$', '', name)  # footnote superscripts
    name = re.sub(r'\s+\d+\s*$', '', name)             # bare trailing number
    name = re.sub(r'^\d+-?PC:\s*', '', name, flags=re.I)
    return name.strip()


def is_generic(name):
    """Return True if name is a descriptor, not a real item."""
    if '%' in name: return True
    if re.search(r'^[\+\-]', name.strip()): return True
    if re.search(r'\bstat\s*stick\b', name, re.I): return True
    if re.search(r'\b(any|rank)\b', name, re.I): return True
    if re.search(r'\b(craftable|event)\b', name, re.I): return True
    if re.search(r'engine|disc', name, re.I) and len(name.split()) <= 3: return True
    if name.startswith('/') or name.startswith('('): return True
    if len(name) < 4: return True
    return False


def parse_ranked_lines(text):
    """Yield clean item names from ranked/tiered build text lines."""
    for line in (text or '').split('\n'):
        t = line.strip()
        if not t:
            continue
        m = re.match(r'^(?:\d+\s*[-.)]+|[≈~]{1,2})\s*(.+)', t)
        if not m:
            continue
        name = m.group(1)
        name = re.sub(r'\s*\(\d\s*[✩★⭐]\)\s*', '', name)  # (5✩)
        name = re.sub(r'\s*\[R\d\]\s*', '', name, flags=re.I)
        name = re.sub(r'\s*\*+\s*$', '', name)
        name = normalize_name(name).strip()
        if name and not is_generic(name):
            yield name


def parse_gi_items(builds):
    weapons, artifacts = set(), set()
    for char in builds:
        for build in char.get('builds', []):
            for name in parse_ranked_lines(build.get('weapons', '')):
                weapons.add(name)
            for line in (build.get('artifacts', '') or '').split('\n'):
                t = line.strip()
                if not t:
                    continue
                m = re.match(r'^(?:\d+\s*[-.)]+|[≈~]{1,2})\s*(.+)', t)
                if not m:
                    continue
                name = m.group(1)
                # Strip piece count, combo syntax, qualifiers
                name = re.sub(r'\s*\(\d\)\s*.*$', '', name)
                name = re.sub(r'\s*/.*$', '', name)
                name = re.sub(r'\s*\[.*$', '', name)
                name = re.sub(r'\bChoose.*$', '', name, flags=re.I)
                name = re.sub(r'\(\d\s*[✩★⭐]\)', '', name)
                name = normalize_name(name).strip()
                if name and not is_generic(name):
                    artifacts.add(name)
    return weapons, artifacts


def parse_hsr_sets(text):
    sets = []
    for line in (text or '').split('\n'):
        t = line.strip()
        if not t:
            continue
        m = re.match(r'^(?:\d+\s*[-.)]+|[≈~]{1,2})\s*(.+)', t)
        if not m:
            continue
        name = m.group(1)
        name = re.sub(r'^\d+-?PC:\s*', '', name, flags=re.I)
        name = re.sub(r'\s*[¹²³⁴⁵⁶⁷⁸⁹]+\s*$', '', name)
        name = name.strip()
        if name and not is_generic(name):
            sets.append(name)
    return sets


def parse_hsr_items(builds):
    lcs, relics, planars = set(), set(), set()
    for char in builds:
        for build in char.get('builds', []):
            for name in parse_ranked_lines(build.get('light_cones', '')):
                lcs.add(name)
            for name in parse_hsr_sets(build.get('relic_4pc', '')):
                relics.add(name)
            for name in parse_hsr_sets(build.get('planar_ornament', '')):
                planars.add(name)
    return lcs, relics, planars


def parse_zzz_wengines(builds):
    engines = set()
    for char in builds:
        for build in char.get('builds', []):
            for line in (build.get('w_engines', '') or '').split('\n'):
                t = line.strip()
                if t.endswith(':'):
                    name = t[:-1].strip()
                    if name and not is_generic(name):
                        engines.add(name)
    return engines


def fetch_batch(wiki, names, make_filename, label, existing, delay=0.25):
    """Fetch icons for names not already in existing. Returns updated dict."""
    result = dict(existing)
    missing = sorted(n for n in names if n not in result)
    if not missing:
        print(f'{label}: all {len(result)} cached')
        return result
    print(f'\n{label}: fetching {len(missing)} (have {len(result)} cached)...')
    ok = fail = 0
    for name in missing:
        fname = make_filename(name)
        url = fetch_url(wiki, fname)
        time.sleep(delay)
        if url:
            result[name] = url
            ok += 1
            print(f'  ✓ {name}')
        else:
            fail += 1
            print(f'  ✗ {name}')
    print(f'  → {ok}/{len(missing)} found')
    return result


def main():
    existing = {'gi': {}, 'hsr': {}, 'zzz': {}}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        print(f'Loaded existing item_icons.json ({sum(len(v) for v in existing.values())} entries)')

    gi_builds  = json.loads((ROOT / 'builds.json').read_text())
    hsr_builds = json.loads((ROOT / 'hsr_builds.json').read_text())
    zzz_builds = json.loads((ROOT / 'zzz_builds.json').read_text())
    disc_names = set(json.loads((ROOT / 'disc_icons.json').read_text()).keys())

    gi_weapons, gi_artifacts = parse_gi_items(gi_builds)
    hsr_lcs, hsr_relics, hsr_planars = parse_hsr_items(hsr_builds)
    zzz_engines = parse_zzz_wengines(zzz_builds)

    GI  = WIKIS['gi']
    HSR = WIKIS['hsr']
    ZZZ = WIKIS['zzz']

    result_gi = dict(existing.get('gi', {}))
    result_hsr = dict(existing.get('hsr', {}))
    result_zzz = dict(existing.get('zzz', {}))

    result_gi = fetch_batch(GI,  gi_weapons,
        lambda n: f'Weapon_{to_wiki_name(n)}.png',
        'GI weapons', result_gi)

    result_gi = fetch_batch(GI, gi_artifacts,
        lambda n: f'Item_{to_wiki_name(n)}.png',
        'GI artifacts', result_gi)

    result_hsr = fetch_batch(HSR, hsr_lcs,
        lambda n: f'Light_Cone_{to_wiki_name(n)}.png',
        'HSR light cones', result_hsr)

    result_hsr = fetch_batch(HSR, hsr_relics | hsr_planars,
        lambda n: f'Item_{to_wiki_name(n)}.png',
        'HSR relics + planars', result_hsr)

    result_zzz = fetch_batch(ZZZ, zzz_engines,
        lambda n: f'W-Engine_{to_wiki_name(n)}.png',
        'ZZZ W-engines', result_zzz)

    result_zzz = fetch_batch(ZZZ, disc_names,
        lambda n: f'Drive Disc {n} Icon.png',
        'ZZZ disc sets', result_zzz)

    output = {'gi': result_gi, 'hsr': result_hsr, 'zzz': result_zzz}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f'\nWrote item_icons.json')
    for g, d in output.items():
        print(f'  {g}: {len(d)} entries')


if __name__ == '__main__':
    main()
