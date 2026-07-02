#!/usr/bin/env python3
"""
Convert the Genshin-Impact-Helper-Team/genshin-builds repo (the new website
source of truth, replacing the sunset Google Sheet) into our flat builds.json
GI schema.

Pipeline:
  1. git clone/pull the repo into ~/.cache/gi_website_repo
  2. load i18n en maps + weapon rarity data + translation aliases
  3. walk src/content/<element>/<rarity>/<char>/<build>/*.json
  4. emit our schema to builds_scrape.json, diff vs previous scrape

Then MANUALLY merge desired changes into builds.json (never auto-overwritten).
"""
import json, os, re, glob, subprocess, sys

REPO = os.path.expanduser("~/.cache/gi_website_repo")
REPO_URL = "https://github.com/Genshin-Impact-Helper-Team/genshin-builds"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "builds_website_scrape.json")
CANON = os.path.join(HERE, "builds.json")

# Stat display overrides to match our existing house style (repo uses e.g.
# "CRIT Rate / CRIT DMG"; we keep the shorter "Crit Rate / DMG").
# Website uses full character names; our roster (release_data.json / icons /
# portraits) keys on these short names. Map by stable directory slug.
NAME_MAP = {
    "arataki-itto": "Itto",
    "kaedehara-kazuha": "Kazuha",
    "kamisato-ayaka": "Ayaka",
    "kamisato-ayato": "Ayato",
    "kujou-sara": "Sara",
    "kuki-shinobu": "Shinobu",
    "shogun-raiden": "Raiden",
    "sangonomiya-kokomi": "Kokomi",
    "shikanoin-heizou": "Heizou",
    "yumemizuki-mizuki": "Mizuki",
}

STAT_OVERRIDES = {
    "cr": "Crit Rate", "cd": "Crit DMG", "cr/cd": "Crit Rate / DMG",
    "em": "Elemental Mastery", "er": "Energy Recharge",
    "hp": "Flat HP", "hp%": "HP%", "atk": "Flat ATK", "atk%": "ATK%",
    "def": "Flat DEF", "def%": "DEF%", "healing-bonus": "Healing Bonus",
}


def sh(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def ensure_repo():
    if os.path.isdir(os.path.join(REPO, ".git")):
        r = sh(["git", "pull", "--ff-only"], cwd=REPO)
        print("git pull:", (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr).strip() else "ok")
    else:
        print("cloning", REPO_URL)
        sh(["git", "clone", "--depth", "1", REPO_URL, REPO])


def load(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as f:
        return json.load(f)


class Resolver:
    def __init__(self):
        self.weapons = load("src/i18n/en/weapons.json")
        self.sets = load("src/i18n/en/artifact-sets.json")
        self.stats = load("src/i18n/en/stats.json")
        self.abilities = load("src/i18n/en/abilities.json")
        self.characters = load("src/i18n/en/characters.json")
        self.elements = load("src/i18n/en/elements.json")
        al = load("src/data/translation-aliases.json")
        self.walias = al.get("weapon", {})
        self.salias = al.get("set", {})
        # weapon rarity, keyed by real slug, across all weapon-type files
        self.wrarity = {}
        for wt in ("bow", "catalyst", "claymore", "polearm", "sword"):
            for slug, d in load(f"src/data/weapons/{wt}.json").items():
                self.wrarity[slug] = d.get("rarity")

    def weapon(self, slug):
        real = self.walias.get(slug, slug)
        return self.weapons.get(real) or self.weapons.get(slug) or _title(slug)

    def weapon_rarity(self, slug):
        real = self.walias.get(slug, slug)
        return self.wrarity.get(real) or self.wrarity.get(slug)

    def aset(self, slug):
        real = self.salias.get(slug, slug)
        return (self.sets.get(real) or self.sets.get(slug)
                or self.stats.get(slug) or _title(slug))

    def stat(self, slug):
        if slug in STAT_OVERRIDES:
            return STAT_OVERRIDES[slug]
        # custom names may embed markup like "[[stat:atk%]] / [[stat:hp]]"
        if "[[" in slug:
            return self.markup(slug)
        return self.stats.get(slug) or _title(slug)

    def ability(self, slug):
        return self.abilities.get(slug) or _title(slug)

    def character(self, slug):
        return self.characters.get(slug) or _title(slug)

    def element(self, slug):
        return self.elements.get(slug) or _title(slug)

    # ---- markup resolution for note text ----
    _TAG = re.compile(r"\[\[([a-z]+):([^\]|]+)(?:\|([^\]]+))?\]\]")

    def markup(self, text):
        if not text:
            return ""

        def repl(m):
            kind, slug, override = m.group(1), m.group(2), m.group(3)
            if override:
                return override
            slug = slug.strip()
            if kind == "weapon":
                return self.weapon(slug)
            if kind == "set":
                return self.aset(slug)
            if kind == "stat":
                return self.stat(slug)
            if kind == "ability":
                return self.ability(slug)
            if kind == "character":
                return self.character(slug)
            if kind == "element":
                return self.element(slug)
            return slug

        s = self._TAG.sub(repl, text)
        s = re.sub(r"\{rot:([^}]*)\}", r"\1", s)   # {rot:N2C} -> N2C
        # best-effort cleanup of malformed/prefix-less tags in source data
        # e.g. [[atk%]] or [[primordial-jade-winged-spear]] (missing kind:)
        s = re.sub(r"\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]", self._loose, s)
        s = s.replace("[[", "").replace("]]", "")   # any stray brackets
        s = s.replace("**", "")                      # strip bold
        return s

    def _loose(self, m):
        if m.group(2):
            return m.group(2)
        slug = m.group(1).strip()
        return (self.stats.get(slug) or self.weapons.get(self.walias.get(slug, slug))
                or self.sets.get(self.salias.get(slug, slug))
                or self.characters.get(slug) or self.elements.get(slug)
                or STAT_OVERRIDES.get(slug) or _title(slug))


def _title(slug):
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


def _en(note):
    """A note field is {en:..,fr:..} or a plain string."""
    if isinstance(note, dict):
        return note.get("en", "")
    return note or ""


# ────────────────────────── field converters ──────────────────────────

def conv_weapons(R, data):
    """weapons.json -> ranked text string + list of (name, note) for notes."""
    lines, notes = [], []
    rank = 0
    for grp in data.get("weapons", []):
        items = grp.get("items", [])
        for i, it in enumerate(items):
            if isinstance(it, str):
                slug, note, refine = it, "", None
            else:
                slug = it.get("name")
                note = _en(it.get("note"))
                refine = it.get("refinement")
            name = R.weapon(slug)
            rar = R.weapon_rarity(slug)
            star = f" ({rar}✩)" if rar else ""
            ref = f" [{refine}]" if refine else ""
            star_note = "*" if note else ""
            if i == 0:
                rank += 1
                lines.append(f"{rank}. {name}{ref}{star}{star_note}")
            else:
                lines.append(f"≈ {name}{ref}{star}{star_note}")
            if note:
                notes.append((name, R.markup(note)))
    return "\n".join(lines), notes


def _set_item(R, it):
    """One set item dict {name,pieces,note} -> ('Name (P)', note_or_'')."""
    name = R.aset(it["name"])
    p = it.get("pieces")
    piece = f" ({p})" if p else ""
    note = _en(it.get("note"))
    return f"{name}{piece}", (R.markup(note) if note else ""), name


def conv_artifacts(R, data):
    lines, notes = [], []
    rank = 0

    def render_group(grp, is_alt):
        """Return the display fragment for one group object."""
        items = grp.get("items", [])
        rendered = []
        for it in items:
            frag, note, name = _set_item(R, it)
            rendered.append(frag)
            if note:
                notes.append((name, note))
        if grp.get("choose"):
            return " / ".join(rendered) + " [Choose Two]"
        return " / ".join(rendered)

    for entry in data.get("artifact_sets", []):
        # entry is a rank slot; may be a bare group-with-items, a
        # {groups:[...]} (first numbered, rest ≈), or {choices:[...]}
        if "choices" in entry:
            pools = [render_group(g, False) for g in entry["choices"]]
            rank += 1
            lines.append(f"{rank}. " + " and ".join(pools) + " [Choose One]")
            continue
        groups = entry.get("groups", [entry])
        for gi, g in enumerate(groups):
            frag = render_group(g, gi > 0)
            star = "*" if _group_has_note(g) else ""
            if gi == 0:
                rank += 1
                lines.append(f"{rank}. {frag}{star}")
            else:
                lines.append(f"≈ {frag}{star}")

    cond = data.get("conditional", [])
    if cond:
        lines.append("")
        lines.append("Conditional (See Notes)")
        for g in cond:
            frag = render_group(g, False)
            star = "*" if _group_has_note(g) else ""
            lines.append(f"{frag}{star}")

    return "\n".join(lines), notes


def _group_has_note(g):
    return any(isinstance(it, dict) and it.get("note") for it in g.get("items", []))


def conv_mainstats(R, data):
    ms = data.get("main_stats", {})

    def slot(key):
        vals = []
        for x in ms.get(key, []):
            if isinstance(x, str):
                vals.append(R.stat(x))
            else:
                vals.append(R.stat(x.get("name")))
        return " / ".join(vals)

    return "\n".join([
        f"Sands - {slot('sands')}",
        f"Goblet - {slot('goblet')}",
        f"Circlet - {slot('circlet')}",
    ])


def conv_substats(R, data):
    lines, notes = [], []
    rank = 0
    for x in data.get("substats_priority", []):
        if isinstance(x, str):
            rank += 1
            lines.append(f"{rank}. {R.stat(x)}")
        elif "items" in x:  # alt group
            for i, it in enumerate(x["items"]):
                nm = R.stat(it) if isinstance(it, str) else R.stat(it.get("name"))
                if i == 0:
                    rank += 1
                    lines.append(f"{rank}. {nm}")
                else:
                    lines.append(f"≈ {nm}")
        else:  # {name, note}
            rank += 1
            note = _en(x.get("note"))
            star = "*" if note else ""
            nm = R.stat(x.get("name"))
            lines.append(f"{rank}. {nm}{star}")
            if note:
                notes.append((nm, R.markup(note)))
    return "\n".join(lines), notes


ABILITY_ORDER_NAME = {"na": "Normal Attack", "ca": "Charged Attack",
                      "skill": "Skill", "burst": "Burst"}


def conv_talents(R, data):
    lines = []
    rank = 0
    for grp in data.get("talents", []):
        items = grp.get("items", [])
        parts = []
        approx = False
        for it in items:
            if isinstance(it, str):
                parts.append(R.ability(it))
            else:
                parts.append(R.ability(it.get("name")))
                if it.get("approx"):
                    approx = True
        rank += 1
        pre = "≈ " if approx else f"{rank}. "
        lines.append(pre + " = ".join(parts))
    return "\n".join(lines)


def conv_notes(R, bn, wnotes, anotes, snotes):
    parts = []
    for n in bn.get("notes", []):
        parts.append(R.markup(_en(n)))
    body = "\n\n".join(p for p in parts if p)

    def section(title, pairs):
        if not pairs:
            return ""
        out = [title]
        for name, txt in pairs:
            out.append(f"{name}: {txt}")
        return "\n".join(out)

    blocks = [body]
    wsec = section("Regarding Weapon Choices:", wnotes)
    asec = section("Regarding Artifact Sets:", anotes)
    ssec = section("Regarding Artifact Substats Priority:", snotes)
    for b in (wsec, asec, ssec):
        if b:
            blocks.append(b)
    return "\n\n".join(b for b in blocks if b)


# ────────────────────────── main walk ──────────────────────────

def build_char(R, char_dir):
    meta = json.load(open(os.path.join(char_dir, "metadata.json")))
    slug = os.path.basename(char_dir)
    name = NAME_MAP.get(slug) or R.character(slug)
    lu = meta.get("last_updated", "")
    last_updated = f"Version {lu}" if lu else ""
    # content path is src/content/<element>/<rarity>/<slug>/
    element = os.path.basename(os.path.dirname(os.path.dirname(char_dir))).capitalize()
    is_traveler = slug == "traveler"

    builds = []
    for bd in sorted(glob.glob(os.path.join(char_dir, "*/"))):
        bn_path = os.path.join(bd, "build-notes.json")
        if not os.path.exists(bn_path):
            continue
        bn = json.load(open(bn_path))

        def g(fn):
            # mirror the site's loadJSON: build dir first, then char dir
            p = os.path.join(bd, fn)
            if not os.path.exists(p):
                p = os.path.join(char_dir, fn)
            return json.load(open(p)) if os.path.exists(p) else {}

        wtext, wnotes = conv_weapons(R, g("weapons.json"))
        atext, anotes = conv_artifacts(R, g("artifacts-sets.json"))
        stext, snotes = conv_substats(R, g("artifacts-substats.json"))
        role = R.markup(_en(bn.get("name"))) or _title(os.path.basename(bd.rstrip("/")))
        if is_traveler:
            role = f"{element} — {role}"
        build = {
            "role": role,
            "recommended": bool(bn.get("best")),
            "weapons": wtext,
            "artifacts": atext,
            "main_stats": conv_mainstats(R, g("artifacts-mainstats.json")),
            "substats": stext,
            "talent_priority": conv_talents(R, g("talents.json")),
            "tips": conv_notes(R, bn, wnotes, anotes, snotes),
        }
        builds.append(build)

    # sort recommended build first
    builds.sort(key=lambda b: not b["recommended"])
    return {"name": name, "last_updated": last_updated, "builds": builds,
            "notes": builds[0]["tips"] if builds else ""}


def main():
    ensure_repo()
    R = Resolver()
    by_name = {}
    for md in sorted(glob.glob(os.path.join(REPO, "src/content/*/*/*/metadata.json"))):
        c = build_char(R, os.path.dirname(md))
        if c["name"] in by_name:  # e.g. Traveler across 6 element dirs
            by_name[c["name"]]["builds"].extend(c["builds"])
        else:
            by_name[c["name"]] = c
    chars = sorted(by_name.values(), key=lambda c: c["name"])
    for c in chars:  # keep recommended builds first, refresh top-level notes
        c["builds"].sort(key=lambda b: not b["recommended"])
        c["notes"] = c["builds"][0]["tips"] if c["builds"] else ""

    prev = {}
    baseline = OUT if os.path.exists(OUT) else CANON
    if os.path.exists(baseline):
        old = json.load(open(baseline))
        old = old if isinstance(old, list) else old.get("gi", [])
        prev = {c["name"]: c for c in old}

    new = {c["name"]: c for c in chars}
    added = sorted(set(new) - set(prev))
    removed = sorted(set(prev) - set(new))
    changed = sorted(n for n in new if n in prev and new[n] != prev[n])
    print(f"\n=== DIFF ===\n  {len(chars)} characters")
    print(f"  NEW ({len(added)}): {', '.join(added) or '-'}")
    print(f"  REMOVED ({len(removed)}): {', '.join(removed) or '-'}")
    print(f"  UPDATED ({len(changed)}): {', '.join(changed) or '-'}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(chars, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
