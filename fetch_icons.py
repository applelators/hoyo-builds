#!/usr/bin/env python3
"""Fetch character icon/thumbnail URLs and write icons.json."""

import json
import re
import time
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).parent / 'icons.json'

WIKIS = {
    'gi':  'genshin-impact.fandom.com',
    'hsr': 'honkai-star-rail.fandom.com',
    'zzz': 'zenless-zone-zero.fandom.com',
}

# GI: Character_NAME_Thumb.png (256×256)
# HSR: Character_NAME_Icon.png (160×160)
# ZZZ: Agent_NAME_Icon.png (283×307)
ICON_OVERRIDES = {
    'gi': {
        'TRAVELER': 'Character_Lumine_Thumb.png',
    },
    'hsr': {
        'Trailblazer':      'Character_Trailblazer_Icon.png',
        'March 7th':        'Character_March_7th_Icon.png',
        'Imbibitor Lunae':  'Character_Dan_Heng_%E2%80%A2_Imbibitor_Lunae_Icon.png',
        'Permansor Terrae': 'Character_Dan_Heng_%E2%80%A2_Permansor_Terrae_Icon.png',
        'Topaz & Numby':    'Character_Topaz_%26_Numby_Icon.png',
    },
    'zzz': {
        'Flora (Seed)':              'Agent_Seed_Icon.png',
        'Orphie Magnusson & Magus':  'Agent_Orphie_Magnusson_%26_Magus_Icon.png',
    },
}


def to_wiki_name(name, game):
    if game == 'gi':
        name = name.title()
    name = re.sub(r'\s*\([^)]+\)$', '', name).strip()
    return name.replace(' ', '_')


def make_icon_filename(name, game):
    wiki_name = to_wiki_name(name, game)
    if game == 'gi':
        return f'Character_{wiki_name}_Thumb.png'
    elif game == 'hsr':
        return f'Character_{wiki_name}_Icon.png'
    else:
        return f'Agent_{wiki_name}_Icon.png'


def fetch_url(wiki, filename):
    api_url = (
        f'https://{wiki}/api.php?action=query'
        f'&titles=File:{filename}&prop=imageinfo&iiprop=url&format=json'
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
        print(f'    error fetching {filename}: {e}')
    return None


def fetch_game_icons(game, chars):
    wiki = WIKIS[game]
    overrides = ICON_OVERRIDES[game]
    results = {}
    seen = set()

    for char in chars:
        name = char['name']
        if name in seen:
            continue
        seen.add(name)

        fname = overrides[name] if name in overrides else make_icon_filename(name, game)
        url = fetch_url(wiki, fname)
        time.sleep(0.25)

        if url:
            results[name] = url
            print(f'  ✓  {name}')
        else:
            print(f'  ✗  {name} (tried: {fname})')

    return results


def main():
    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        print(f'Loaded existing icons.json ({sum(len(v) for v in existing.values())} entries)')

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
            print(f'{game.upper()}: all {len(result[game])} icons cached')
            continue
        print(f'\n{game.upper()}: fetching {len(missing)} icons '
              f'(have {len(result[game])} cached)...')
        new = fetch_game_icons(game, missing)
        result[game].update(new)
        print(f'  → {len(new)}/{len(missing)} found')

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    totals = {g: len(v) for g, v in result.items()}
    print(f'\nWrote icons.json — GI: {totals["gi"]}, HSR: {totals["hsr"]}, ZZZ: {totals["zzz"]}')


if __name__ == '__main__':
    main()
