#!/usr/bin/env python3
"""Download ZZZ drive disc set icons from the fandom wiki and compute phash references.

Output:
    disc_icons/         directory with one PNG per disc set
    disc_icons.json     { "Set Name": "phash_hex_string" }

Usage:
    python3 fetch_disc_icons.py
    python3 fetch_disc_icons.py --force   # re-download even if cached
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

try:
    import imagehash
    from PIL import Image
except ImportError:
    print("pip install imagehash Pillow")
    sys.exit(1)

DIR      = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(DIR, 'disc_icons.json')
OUT_DIR  = os.path.join(DIR, 'disc_icons')
WIKI_API = 'https://zenless-zone-zero.fandom.com/api.php'

DISC_SETS = [
    "Assassin's Ballad", "Astral Voice", "Branch & Blade Song",
    "Bunny in Wonderland", "Chaos Jazz", "Chaotic Metal", "Dawn's Bloom",
    "Doom Grindcore", "Ecstatic Punk", "Fanged Metal", "Freedom Blues",
    "Hormone Punk", "Inferno Metal", "King of the Summit", "Mammoth Electro",
    "Monsoon Funk", "Moonlight Lullaby", "Noisy Pop", "Notes From the Chained",
    "Phaethon's Melody", "Polar Metal", "Proto Punk", "Puffer Electro",
    "Shadow Harmony", "Shining Aria", "Shockstar Disco", "Soul Rock",
    "Swing Jazz", "Thunder Metal", "Twisted Grindcore", "Unicorn Electro",
    "Vagabond Folk", "White Water Ballad", "Woodpecker Electro", "Yunkui Tales",
]


def fetch_cdn_url(name: str):
    """Try _S, _A, _B suffixes; return first URL that resolves (prefer 256x256 square)."""
    safe = name.replace(' ', '_')
    for suffix in ('S', 'A', 'B'):
        filename = f"Drive_Disc_{safe}_{suffix}.png"
        params = urllib.parse.urlencode({
            'action': 'query',
            'titles': f'File:{filename}',
            'prop':   'imageinfo',
            'iiprop': 'url',
            'format': 'json',
        })
        req = urllib.request.Request(
            f"{WIKI_API}?{params}",
            headers={'User-Agent': 'Mozilla/5.0 (compatible; hoyo-builds/1.0)'},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            for page in data['query']['pages'].values():
                if 'imageinfo' in page:
                    return page['imageinfo'][0]['url']
        except Exception as e:
            print(f"  API error ({filename}): {e}")
        time.sleep(0.1)
    return None


def download_bytes(url: str):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; hoyo-builds/1.0)'},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except Exception as e:
        print(f"  Download error: {e}")
    return None


def compute_phash(data: bytes):
    img = Image.open(io.BytesIO(data))
    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode in ('RGBA', 'LA'):
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    else:
        img = img.convert('RGB')
    return str(imagehash.phash(img))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='Re-download even if cached')
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    missing = []

    for name in DISC_SETS:
        icon_path = os.path.join(OUT_DIR, f"{name}.png")
        print(f"  {name:35s}", end=' ', flush=True)

        if os.path.exists(icon_path) and not args.force:
            with open(icon_path, 'rb') as f:
                data = f.read()
            print("cached", end=' ', flush=True)
        else:
            cdn_url = fetch_cdn_url(name)
            if not cdn_url:
                print("MISSING ON WIKI")
                missing.append(name)
                continue
            data = download_bytes(cdn_url)
            if not data:
                print("DOWNLOAD FAILED")
                missing.append(name)
                continue
            with open(icon_path, 'wb') as f:
                f.write(data)
            time.sleep(0.3)

        try:
            h = compute_phash(data)
            results[name] = h
            print(f"phash={h}")
        except Exception as e:
            print(f"PHASH ERROR: {e}")
            missing.append(name)

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(results)}/{len(DISC_SETS)} entries to {OUT_JSON}")
    if missing:
        print(f"Missing/failed: {missing}")


if __name__ == '__main__':
    main()
