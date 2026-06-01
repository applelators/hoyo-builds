#!/usr/bin/env python3
"""Fetch character portrait URLs from fandom wikis and write portraits.json.

Sources:
  GI  — HoYoverse Website Character Profile  ({Name}_Profile.png)
  HSR — Splash Art                            (Character_{Name}_Splash_Art.png)
  ZZZ — Agent Full Mindscape                  (Mindscape_{Name}_Full.png)

Pass --force to ignore the cached portraits.json and re-fetch everything.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).parent / 'portraits.json'

WIKIS = {
    'gi':  'genshin-impact.fandom.com',
    'hsr': 'honkai-star-rail.fandom.com',
    'zzz': 'zenless-zone-zero.fandom.com',
}

# Characters whose wiki image filename differs from the normalised pattern.
# Set a name to None to explicitly skip (no portrait available).
OVERRIDES = {
    'gi': {
        'Traveler': None,
        # Short builds name → full GI wiki portrait filename
        'Itto':    'Arataki_Itto_Profile.png',
        'Kazuha':  'Kaedehara_Kazuha_Profile.png',
        'Ayaka':   'Kamisato_Ayaka_Profile.png',
        'Ayato':   'Kamisato_Ayato_Profile.png',
        'Sara':    'Kujou_Sara_Profile.png',
        'Shinobu': 'Kuki_Shinobu_Profile.png',
        'Raiden':  'Raiden_Shogun_Profile.png',
        'Kokomi':  'Sangonomiya_Kokomi_Profile.png',
        'Heizou':  'Shikanoin_Heizou_Profile.png',
        'Mizuki':  'Yumemizuki_Mizuki_Profile.png',
        'Nicole':  'Character_Nicole_Full_Wish.png',
        'Lohen':   'Lohen_Card.png',
    },
    'hsr': {
        'Dan Heng • Imbibitor Lunae':  'Character_Dan_Heng_%E2%80%A2_Imbibitor_Lunae_Splash_Art.png',
        'Dan Heng • Permansor Terrae': 'Character_Dan_Heng_%E2%80%A2_Permansor_Terrae_Splash_Art.png',
        'Topaz & Numby':               'Character_Topaz_%26_Numby_Splash_Art.png',
        'Tingyun • Fugue':             'Character_Fugue_Splash_Art.png',
        'March 7th • The Hunt':        'Character_March_7th_Splash_Art.png',
        'March 7th • Evernight':       'Character_Evernight_Splash_Art.png',
        'Silver Wolf • Lv. 999':       'Character_Silver_Wolf_LV.999_Splash_Art.png',
        'Trailblazer': None,
    },
    'zzz': {
        # Short builds name → full ZZZ wiki Mindscape filename
        'Anby':            'Mindscape_Anby_Demara_Full.png',
        'Alice':           'Mindscape_Alice_Thymefield_Full.png',
        'Anton':           'Mindscape_Anton_Ivanov_Full.png',
        'Ben':             'Mindscape_Ben_Bigger_Full.png',
        'Billy':           'Mindscape_Billy_Kid_Full.png',
        'Burnice':         'Mindscape_Burnice_White_Full.png',
        'Caesar':          'Mindscape_Caesar_King_Full.png',
        'Corin':           'Mindscape_Corin_Wickes_Full.png',
        'Ellen':           'Mindscape_Ellen_Joe_Full.png',
        'Evelyn':          'Mindscape_Evelyn_Chevalier_Full.png',
        'Grace':           'Mindscape_Grace_Howard_Full.png',
        'Harumasa':        'Mindscape_Asaba_Harumasa_Full.png',
        'Hugo':            'Mindscape_Hugo_Vlad_Full.png',
        'Koleda':          'Mindscape_Koleda_Belobog_Full.png',
        'Lucia':           'Mindscape_Lucia_Elowen_Full.png',
        'Lucy':            'Mindscape_Luciana_de_Montefio_Full.png',
        'Lycaon':          'Mindscape_Von_Lycaon_Full.png',
        'Manato':          'Mindscape_Komano_Manato_Full.png',
        'Miyabi':          'Mindscape_Hoshimi_Miyabi_Full.png',
        'Nekomata':        'Mindscape_Nekomiya_Mana_Full.png',
        'Nicole':          'Mindscape_Nicole_Demara_Full.png',
        'Orphie & Magus':  'Mindscape_Orphie_Magnusson_%26_Magus_Full.png',
        'Piper':           'Mindscape_Piper_Wheel_Full.png',
        'Pulchra':         'Mindscape_Pulchra_Fellini_Full.png',
        'Rina':            'Mindscape_Alexandrina_Sebastiane_Full.png',
        'Seed':            'Mindscape_Seed_Full.png',
        'Seth':            'Mindscape_Seth_Lowell_Full.png',
        'Anby: Soldier 0':  'Mindscape_Soldier_0_-_Anby_Full.png',
        'Starlight Billy':  'Mindscape_Starlight_-_Billy_Kid_Full.png',
        'Vivian':           'Mindscape_Vivian_Banshee_Full.png',
        'Yanagi':          'Mindscape_Tsukishiro_Yanagi_Full.png',
        'Yidhari':         'Mindscape_Yidhari_Murphy_Full.png',
        'Yuzuha':          'Mindscape_Ukinami_Yuzuha_Full.png',
    },
}


def to_wiki_name(name: str, game: str) -> str:
    """Convert a character name to a wiki filename base."""
    if game == 'gi':
        name = name.title()
    name = re.sub(r'\s*\([^)]+\)$', '', name).strip()
    return name.replace(' ', '_')


def make_filename(name: str, game: str) -> str:
    wiki_name = to_wiki_name(name, game)
    if game == 'gi':
        return f'{wiki_name}_Profile.png'
    elif game == 'hsr':
        return f'Character_{wiki_name}_Splash_Art.png'
    else:  # zzz
        return f'Mindscape_{wiki_name}_Full.png'


def fetch_url(wiki: str, filename: str):
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


def fetch_game_portraits(game, chars, existing):
    wiki = WIKIS[game]
    overrides = OVERRIDES[game]
    results = dict(existing)
    seen_names = set()

    for char in chars:
        name = char['name']
        if name in seen_names:
            continue
        seen_names.add(name)

        override = overrides.get(name, ...)  # ... = not overridden
        if override is None:
            print(f'  –  {name} (skipped — no portrait source)')
            results.pop(name, None)
            continue

        if name in results:
            print(f'  ·  {name} (cached)')
            continue

        filename = override if override is not ... else make_filename(name, game)
        url = fetch_url(wiki, filename)

        if url:
            results[name] = url
            print(f'  ✓  {name}')
        else:
            print(f'  ✗  {name} (tried: {filename})')

        time.sleep(0.25)

    return results


def main():
    force = '--force' in sys.argv

    existing = {'gi': {}, 'hsr': {}, 'zzz': {}}
    if not force and OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        print(f'Loaded existing portraits.json ({sum(len(v) for v in existing.values())} entries)')
    elif force:
        print('--force: ignoring cache, re-fetching all portraits')

    gi_chars  = json.loads((Path(__file__).parent / 'builds.json').read_text())
    hsr_chars = json.loads((Path(__file__).parent / 'hsr_builds.json').read_text())
    zzz_chars = json.loads((Path(__file__).parent / 'zzz_builds.json').read_text())

    result = {}
    for game, chars in [('gi', gi_chars), ('hsr', hsr_chars), ('zzz', zzz_chars)]:
        print(f'\n{game.upper()}:')
        result[game] = fetch_game_portraits(game, chars, existing.get(game, {}))

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    totals = {g: len(v) for g, v in result.items()}
    print(f'\nWrote portraits.json — GI: {totals["gi"]}, HSR: {totals["hsr"]}, ZZZ: {totals["zzz"]}')


if __name__ == '__main__':
    main()
