"""Apply ZZZ rarity to release_data.json using confirmed A-rank list from img_alt probe."""
import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "release_data.json"

# Confirmed A-rank chars from _probe_zzz_ranks.py (img_alt method only, archives/458129)
A_RANK_SHORT = {
    'manato', 'pan yinhu', 'pulchra', 'seth', 'anby', 'billy',
    'nicole', 'anton', 'corin', 'ben', 'soukaku', 'lucy', 'piper',
}

rd = json.loads(OUTPUT.read_text())
zzz = rd['zzz']

# Build lowercase first-token + full-name lookup
rd_lower_first = {}
for name in zzz:
    first = name.split()[0].lower()
    if first not in rd_lower_first:
        rd_lower_first[first] = name
    # Also index by full lowercase
    rd_lower_first[name.lower()] = name

# Manual overrides for names that don't match by first token
MANUAL_MAP = {
    'manato': 'Komano Manato',
    'lucy':   'Luciana Auxesis Theodoro de Montefio (Lucy)',
    'piper':  'Piper Wheel',
    'pulchra':'Pulchra Fellini',
    'seth':   'Seth Lowell',
    'anby':   'Anby Demara',  # short "Anby" = original A-rank, not "Soldier 0 - Anby"
    'billy':  'Billy Kid',
    'nicole': 'Nicole Demara',
    'anton':  'Anton Ivanov',
    'corin':  'Corin Wickes',
    'ben':    'Ben Bigger',
    'pan yinhu': 'Pan Yinhu',
    'soukaku': 'Soukaku',
}

a_rank_full = set()
for short in A_RANK_SHORT:
    full = MANUAL_MAP.get(short) or rd_lower_first.get(short)
    if full:
        a_rank_full.add(full)
    else:
        print(f"WARNING: could not map A-rank short name {short!r}")

print(f"A-rank chars ({len(a_rank_full)}):")
for n in sorted(a_rank_full):
    print(f"  {n}")

changed = 0
for name in zzz:
    if name in a_rank_full:
        old = zzz[name].get('rarity')
        zzz[name]['rarity'] = 4
        if old != 4:
            print(f"  SET {name}: rarity=4 (was {old})")
            changed += 1
    else:
        old = zzz[name].get('rarity')
        zzz[name]['rarity'] = 5
        if old != 5:
            changed += 1

OUTPUT.write_text(json.dumps(rd, indent=2, ensure_ascii=False))
print(f"\nUpdated {changed} chars, wrote {OUTPUT}")

# Verify
zzz2 = json.loads(OUTPUT.read_text())['zzz']
r4 = [k for k, v in zzz2.items() if v.get('rarity') == 4]
r5 = [k for k, v in zzz2.items() if v.get('rarity') == 5]
missing = [k for k, v in zzz2.items() if not v.get('rarity')]
print(f"rarity=4 ({len(r4)}): {sorted(r4)}")
print(f"rarity=5 ({len(r5)}): count={len(r5)}")
print(f"missing ({len(missing)}): {missing}")
