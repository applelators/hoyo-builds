"""Fix remaining missing character info: ZZZ rarity, GI missing chars, HSR gaps."""
import asyncio
import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "release_data.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Known GI chars missing from Game8 all-builds (rarity + weapon_type)
GI_MANUAL = {
    "Illuga": {"rarity": 5, "weapon_type": "Claymore"},  # v6.3 Geo
    "Linnea": {"rarity": 4, "weapon_type": "Sword"},     # v6.5 Geo
    "Nefer":  {"rarity": 5, "weapon_type": "Catalyst"},  # v6.1 Dendro
    "Varka":  {"rarity": 5, "weapon_type": "Claymore"},  # v6.4 Pyro
    "Zibai":  {"rarity": 5, "weapon_type": "Sword"},     # v6.3 Geo
}

# Known HSR chars missing rarity (all 5★)
HSR_MANUAL_RARITY = {
    "Firefly":          5,
    "Silver Wolf LV.999": 5,
    "The Dahlia":       5,
    "The Herta":        5,
    "March 7th • Evernight": 4,
    "March 7th • The Hunt": 5,
    "Tingyun • Fugue":  5,
    "Dan Heng • Imbibitor Lunae": 5,
    "Dan Heng • Permansor Terrae": 5,
}

_INFOBOX_JS = """
() => {
    const result = {};
    const tables = document.querySelectorAll('table');
    for (const table of tables) {
        const rows = table.querySelectorAll('tr');
        for (const row of rows) {
            const cells = row.querySelectorAll('td, th');
            if (cells.length < 2) continue;
            const c0 = cells[0].innerText.trim();
            const c1 = cells[1].innerText.trim();
            // GI 2-cell rarity
            if (/^rarity$/i.test(c0) && cells.length === 2) {
                if (/★{2,}/.test(c1)) result.rarity = c1.replace(/[^★]/g, '').length;
                else if (/★(\\d)/.test(c1)) result.rarity = parseInt(c1.match(/★(\\d)/)[1]);
                else if (/(\\d)-star/i.test(c1)) result.rarity = parseInt(c1.match(/(\\d)-star/i)[1]);
                result.rarity_raw = c1.slice(0, 30);
            }
            // HSR 3-cell rarity
            if (cells.length === 3) {
                const c2 = cells[2].innerText.trim();
                if (/^rarity$/i.test(c1)) {
                    if (/★{2,}/.test(c2)) result.rarity = c2.replace(/[^★]/g, '').length;
                    else if (/★(\\d)/.test(c2)) result.rarity = parseInt(c2.match(/★(\\d)/)[1]);
                    else if (/(\\d)-star/i.test(c2)) result.rarity = parseInt(c2.match(/(\\d)-star/i)[1]);
                    result.rarity_raw = c2.slice(0, 30);
                }
            }
            // ZZZ 4-cell: [Rarity | rank_img | Attribute | element]
            if (cells.length >= 4 && /^rarity$/i.test(c0)) {
                const rankCell = cells[1];
                const imgs = rankCell.querySelectorAll('img');
                let found = false;
                for (const img of imgs) {
                    const alt = (img.alt || '').trim();
                    if (/S\\s*Rank/i.test(alt)) { result.rarity = 5; found = true; break; }
                    if (/A\\s*Rank/i.test(alt)) { result.rarity = 4; found = true; break; }
                }
                if (!found) {
                    // Fallback: check src URL (S-rank icons often have "s-rank" in URL)
                    for (const img of imgs) {
                        const src = (img.src || '').toLowerCase();
                        if (/s.rank|srank/.test(src)) { result.rarity = 5; found = true; break; }
                        if (/a.rank|arank/.test(src)) { result.rarity = 4; found = true; break; }
                    }
                }
                result.rarity_raw = rankCell.innerHTML.slice(0, 100);
                // Also get element
                const attrLabel = cells[2].innerText.trim();
                const attrVal   = cells[3].innerText.trim();
                if (/attribute/i.test(attrLabel) && attrVal.length < 30)
                    result.element = attrVal.split(/[\\n,]/)[0].trim();
            }
            // Standard element
            if (/^element(s)?$|^vision$/i.test(c0)) {
                const el = c1.split(/[\\n,]/)[0].trim();
                if (el.length < 30) result.element = el;
            }
            // GI weapon
            if (/^weapon\\s*type$|^weapon$/i.test(c0)) {
                const wp = c1.split(/[\\n,]/)[0].trim();
                if (/sword|claymore|bow|catalyst|polearm/i.test(wp)) result.weapon = wp;
            }
        }
    }
    return result;
}
"""

# ZZZ Agent Builds page → get char name + URL mapping
_ZZZ_URL_MAP_JS = """
(knownNames) => {
    const known = new Set(knownNames.map(n => n.toLowerCase()));
    const result = [];
    const seen = new Set();
    document.querySelectorAll('img').forEach(img => {
        const alt = (img.alt || '').trim();
        if (!alt || alt.length < 2) return;
        if (!known.has(alt.toLowerCase())) return;
        const a = img.closest('a');
        if (!a || !a.href.includes('/archives/')) return;
        if (seen.has(alt.toLowerCase())) return;
        seen.add(alt.toLowerCase());
        result.push({ name: alt, url: a.href });
    });
    return result;
}
"""

# GI: search for char on Game8 via title search
_GI_FIND_URL_JS = """
(charName) => {
    const links = document.querySelectorAll('a[href*="/archives/"]');
    for (const a of links) {
        const text = (a.innerText || '').trim();
        if (text.toLowerCase().includes(charName.toLowerCase())) return a.href;
    }
    return null;
}
"""


async def main():
    existing = json.loads(OUTPUT.read_text())
    zzz_builds = json.loads((Path(__file__).parent / "zzz_builds.json").read_text())
    zzz_short_names = [c["name"] for c in zzz_builds]
    # Also try without colon suffixes (Anby: Soldier 0 → Anby)
    zzz_names_normalized = list(set([n.split(":")[0].strip() for n in zzz_short_names] + zzz_short_names))

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=UA)
        page = await ctx.new_page()

        # ── ZZZ: Get char URL mapping from Agent Builds page ─────────────────
        print("[ZZZ] Loading Agent Builds page for char URL mapping...")
        await page.goto("https://game8.co/games/Zenless-Zone-Zero/archives/522597", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        zzz_url_map_raw = await page.evaluate(_ZZZ_URL_MAP_JS, zzz_names_normalized)
        zzz_url_map = {item["name"]: item["url"] for item in zzz_url_map_raw}
        print(f"[ZZZ] Found URLs for {len(zzz_url_map)} chars: {sorted(zzz_url_map.keys())}")

        # ── ZZZ: Visit each char page for rarity ─────────────────────────────
        zzz_rarity: dict[str, int] = {}
        for i, name in enumerate(sorted(zzz_url_map.keys())):
            url = zzz_url_map[name]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                info = await page.evaluate(_INFOBOX_JS)
                rarity = info.get("rarity")
                if rarity:
                    zzz_rarity[name] = rarity
                    print(f"  [zzz] ({i+1}/{len(zzz_url_map)}) {name}: rarity={rarity} (raw: {info.get('rarity_raw','?')[:50]})")
                else:
                    print(f"  [zzz] ({i+1}/{len(zzz_url_map)}) {name}: rarity=None (raw: {info.get('rarity_raw','?')[:50]})")
            except Exception as e:
                print(f"  [zzz] ({i+1}/{len(zzz_url_map)}) {name}: ERROR {e}")

        # ── GI: Search for missing chars on Game8 ────────────────────────────
        gi_missing = [k for k in GI_MANUAL if not existing["gi"].get(k, {}).get("rarity")]
        if gi_missing:
            print(f"\n[GI] Searching for {len(gi_missing)} missing chars on Game8...")
            await page.goto("https://game8.co/games/Genshin-Impact/archives/530535", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(8000)
            for name in gi_missing:
                url = await page.evaluate(_GI_FIND_URL_JS, name)
                if url:
                    print(f"  [gi] {name}: found at {url}")
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(3000)
                        info = await page.evaluate(_INFOBOX_JS)
                        if info.get("rarity"):
                            GI_MANUAL[name]["rarity"] = info["rarity"]
                        if info.get("weapon"):
                            GI_MANUAL[name]["weapon_type"] = info["weapon"]
                        print(f"    scraped: rarity={info.get('rarity')}, weapon={info.get('weapon')}")
                    except Exception as e:
                        print(f"    ERROR: {e}")
                else:
                    print(f"  [gi] {name}: not found on Game8, using manual data")

        await browser.close()

    # ── Apply fixes ────────────────────────────────────────────────────────────
    rd = existing.copy()

    # GI manual fixes
    for name, info in GI_MANUAL.items():
        if name in rd["gi"]:
            if info.get("rarity"):
                rd["gi"][name]["rarity"] = info["rarity"]
            if info.get("weapon_type"):
                rd["gi"][name]["weapon_type"] = info["weapon_type"]

    # HSR manual rarity fixes
    for name, rarity in HSR_MANUAL_RARITY.items():
        if name in rd["hsr"]:
            rd["hsr"][name]["rarity"] = rarity

    # ZZZ rarity from individual pages
    # Map short names (from builds) to release_data full names
    rd_zzz = rd["zzz"]
    rd_lower = {k.lower(): k for k in rd_zzz}
    # First-name mapping
    for rd_name in rd_zzz:
        first = rd_name.split()[0].lower()
        if first not in rd_lower:
            rd_lower[first] = rd_name

    for short_name, rarity in zzz_rarity.items():
        # Try exact match
        if short_name in rd_zzz:
            rd_zzz[short_name]["rarity"] = rarity
            continue
        # Try lowercase match
        key = short_name.lower()
        if key in rd_lower:
            rd_zzz[rd_lower[key]]["rarity"] = rarity
            continue
        # Try matching by removing "Anby: Soldier 0" → "Anby"
        base = short_name.split(":")[0].strip().lower()
        if base in rd_lower:
            rd_zzz[rd_lower[base]]["rarity"] = rarity
            continue
        print(f"  [zzz] WARNING: could not match '{short_name}' to a release_data entry")

    # Write output
    OUTPUT.write_text(json.dumps(rd, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for game in ("gi", "hsr", "zzz"):
        g = rd[game]
        total = len(g)
        with_r = sum(1 for v in g.values() if v.get("rarity"))
        with_w = sum(1 for v in g.values() if v.get("weapon_type"))
        print(f"  {game}: {total} chars | rarity={with_r} | weapon_type={with_w}")


asyncio.run(main())
