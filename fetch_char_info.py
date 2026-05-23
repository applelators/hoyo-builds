"""Fetch character rarity, weapon type, and element from Game8.

Updates release_data.json with:
  rarity       — 4 or 5 (integer)
  weapon_type  — Sword / Claymore / Bow / Catalyst / Polearm (GI only)
  element      — confirms / fills in missing values

Sources:
  GI  — all-builds page (archives/530535) lists all chars with page URLs;
         individual pages have Rarity/Element/Weapon infobox rows.
  HSR — rarity-filter pages (archives/406579 = 5★, archives/406580 = 4★);
         individual pages for element confirmation where needed.
  ZZZ — rank-filter pages (archives/458128 = S-rank, archives/458129 = A-rank);
         element already in zzz_builds.json so no individual visits needed.

Run when a new character is added or to populate rarity/weapon_type fields.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from pathlib import Path

OUTPUT     = Path(__file__).parent / "release_data.json"
BUILDS_GI  = Path(__file__).parent / "builds.json"
BUILDS_HSR = Path(__file__).parent / "hsr_builds.json"
BUILDS_ZZZ = Path(__file__).parent / "zzz_builds.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ── URL sources ──────────────────────────────────────────────────────────────
GI_ALL_BUILDS_URL = "https://game8.co/games/Genshin-Impact/archives/530535"
HSR_5STAR_URL     = "https://game8.co/games/Honkai-Star-Rail/archives/406579"
HSR_4STAR_URL     = "https://game8.co/games/Honkai-Star-Rail/archives/406580"
ZZZ_SRANK_URL     = "https://game8.co/games/Zenless-Zone-Zero/archives/458128"
ZZZ_ARANK_URL     = "https://game8.co/games/Zenless-Zone-Zero/archives/458129"

# HSR element pages for char URL discovery
HSR_ELEMENT_URLS = {
    "Fire":      "https://game8.co/games/Honkai-Star-Rail/archives/405734",
    "Ice":       "https://game8.co/games/Honkai-Star-Rail/archives/405735",
    "Wind":      "https://game8.co/games/Honkai-Star-Rail/archives/405736",
    "Lightning": "https://game8.co/games/Honkai-Star-Rail/archives/405737",
    "Quantum":   "https://game8.co/games/Honkai-Star-Rail/archives/405738",
    "Imaginary": "https://game8.co/games/Honkai-Star-Rail/archives/405739",
    "Physical":  "https://game8.co/games/Honkai-Star-Rail/archives/414491",
}

# ZZZ agent-builds page for char URL discovery (image alt = short char name)
ZZZ_AGENT_BUILDS_URL = "https://game8.co/games/Zenless-Zone-Zero/archives/522597"

# ── JS: extract all GI chars from the all-builds table ────────────────────────
_GI_CHAR_LIST_JS = """
() => {
    const result = [];
    const tables = document.querySelectorAll('table');
    // Table index 2 is the character list on archives/530535
    for (let i = 0; i < tables.length; i++) {
        const rows = tables[i].querySelectorAll('tr');
        if (rows.length < 50) continue;
        const header = rows[0].innerText.toLowerCase();
        if (!header.includes('character')) continue;
        for (let j = 1; j < rows.length; j++) {
            const cells = rows[j].querySelectorAll('td');
            if (cells.length < 1) continue;
            const link = cells[0].querySelector('a');
            const name = cells[0].innerText.trim().split('\\n')[0];
            if (!name || name.length < 2) continue;
            result.push({ name, url: link ? link.href : null });
        }
        break;
    }
    return result;
}
"""

# ── JS: extract chars from HSR/ZZZ rarity-filter pages ────────────────────────
_RARITY_LIST_JS = """
(game) => {
    const result = [];
    const seen = new Set();
    // HSR pages: images with alt "Honkai Star Rail {Name} Icon"
    // ZZZ pages: images with alt "{Name}" or "{Name} Icon"
    document.querySelectorAll('img').forEach(img => {
        const alt = (img.alt || '').trim();
        if (!alt || alt.length < 2 || alt.length > 60) return;
        let name = null;
        if (game === 'hsr') {
            const m = alt.match(/^(?:Honkai\\s+Star\\s+Rail\\s+)?(.+?)(?:\\s+Icon)?$/i);
            if (!m) return;
            name = m[1].trim();
            // Exclude paths, elements, items
            if (/^(?:the |fire|ice|wind|lightning|quantum|imaginary|physical|all|free|s rank|a rank|tier|reroll|★)/i.test(name)) return;
            if (/path|element|rank|rarity|light cone|item|icon/i.test(name)) return;
        } else {
            // ZZZ: alt text is just the character name
            name = alt;
            // Skip known non-character alts
            if (/icon|lullaby|serenade|sickle|seeker|bunny|ballad|radiance|vajra|fantasies|bloom|jazz|blues|bop|talon|notes|arc|shell|song|branch|blade|ballad|water|wavy|calls|yesterday|cloudcleave|yunkui|astral|voice|shimmer|stellar|phaethon|dawn|half-sugar|wrathful|thunder|spring|chain|shining|penta|fanfare|overture|startle|twinkle|swing|rank rarity|rarity|element|specialty|faction|industry|compliance|department|association|cunning|hares|sons|family|victoria|sons|obol|6th street|hollow special ops|gentle house|criminal|belobog|deadbeats|victoria|star|gentle/i.test(name)) return;
            if (name.length > 30) return;
        }
        if (!name || name.length < 2) return;
        const a = img.closest('a');
        if (!a) return;
        const href = a.href || '';
        if (!href.includes('/archives/')) return;
        if (seen.has(name)) return;
        seen.add(name);
        result.push({ name, url: href });
    });
    return result;
}
"""

# ── JS: extract infobox data from individual character pages ──────────────────
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

            // ── Rarity ──────────────────────────────────────────────
            // GI 2-cell: [Rarity | ★★★★★]
            if (/^rarity$/i.test(c0) && cells.length === 2) {
                if (/★{2,}/.test(c1))
                    result.rarity = c1.replace(/[^★]/g, '').length;
                else if (/★(\\d)/.test(c1))
                    result.rarity = parseInt(c1.match(/★(\\d)/)[1]);
                else if (/(\\d)-star/i.test(c1))
                    result.rarity = parseInt(c1.match(/(\\d)-star/i)[1]);
                result.rarity_raw = c1.slice(0, 30);
            }
            // HSR 3-cell: [CharName | Rarity | 5-star]
            if (cells.length === 3) {
                const c2 = cells[2].innerText.trim();
                if (/^rarity$/i.test(c1)) {
                    if (/★{2,}/.test(c2))
                        result.rarity = c2.replace(/[^★]/g, '').length;
                    else if (/★(\\d)/.test(c2))
                        result.rarity = parseInt(c2.match(/★(\\d)/)[1]);
                    else if (/(\\d)-star/i.test(c2))
                        result.rarity = parseInt(c2.match(/(\\d)-star/i)[1]);
                    result.rarity_raw = c2.slice(0, 30);
                }
            }
            // ZZZ 4-cell: [Rarity | {img+text} | Attribute | Ice]
            if (cells.length >= 4 && /^rarity$/i.test(c0)) {
                const rankCell = cells[1];
                const img = rankCell.querySelector('img');
                const imgAlt = (img ? img.alt : '').trim();
                const rankText = rankCell.innerText.trim();
                if (/S\\s*Rank/i.test(imgAlt) || /^S$/i.test(rankText))
                    result.rarity = 5;
                else if (/A\\s*Rank/i.test(imgAlt) || /^A$/i.test(rankText))
                    result.rarity = 4;
                result.rarity_raw = imgAlt || rankText;
                // ZZZ attribute (element) is in cells[3]
                const attrLabel = cells[2].innerText.trim();
                const attrVal   = cells[3].innerText.trim();
                if (/attribute/i.test(attrLabel) && attrVal.length < 30 && !result.element)
                    result.element = attrVal.split(/[\\n,]/)[0].trim();
            }

            // ── Element / Vision / Attribute ────────────────────────
            if (/^element(s)?$|^vision$/i.test(c0)) {
                const el = c1.split(/[\\n,]/)[0].trim();
                if (el.length < 30) result.element = el;
            }

            // ── GI Weapon Type ───────────────────────────────────────
            if (/^weapon\\s*type$|^weapon$/i.test(c0)) {
                const wp = c1.split(/[\\n,]/)[0].trim();
                if (/sword|claymore|bow|catalyst|polearm/i.test(wp)) result.weapon = wp;
            }

            // ── HSR Path ──────────────────────────────────────────────
            if (/^path$/i.test(c0) && c1.length < 60) {
                result.path = c1.split(/[\\n,]/)[0].trim();
            }

            // ── ZZZ Specialty ─────────────────────────────────────────
            if (/^specialty$/i.test(c0) && c1.length < 60) {
                result.specialty = c1.split(/[\\n,]/)[0].trim();
            }
        }
    }
    return result;
}
"""

# ── JS: extract chars from HSR individual element pages ────────────────────────
_HSR_ELEM_PAGE_CHARS_JS = """
(element) => {
    const result = [];
    const seen = new Set();
    document.querySelectorAll('img').forEach(img => {
        const alt = (img.alt || '').trim();
        let name = null;
        // "Honkai Star Rail {Name} Icon" format
        const m1 = alt.match(/^Honkai\\s+Star\\s+Rail\\s+(.+?)(?:\\s+Icon)?$/i);
        // "HSR - {Name} Icon" format
        const m2 = alt.match(/^HSR\\s*-\\s*(.+?)(?:\\s+Icon)?$/i);
        if (m1) name = m1[1].trim();
        else if (m2) name = m2[1].trim();
        if (!name || name.length < 2 || name.length > 50) return;
        // Skip paths/elements/categories
        if (/^(?:the |fire|ice|wind|lightning|quantum|imaginary|physical|all|free|★|rarity|rank)/i.test(name)) return;
        if (/path|element|cone|item|plaque|set|relic|ornament|material|credit|trace/i.test(name)) return;
        const a = img.closest('a');
        if (!a || !a.href.includes('/archives/')) return;
        if (seen.has(name)) return;
        seen.add(name);
        result.push({ name, url: a.href, element });
    });
    return result;
}
"""


def load_existing() -> dict:
    if not OUTPUT.exists():
        return {"gi": {}, "hsr": {}, "zzz": {}}
    try:
        return json.loads(OUTPUT.read_text())
    except json.JSONDecodeError:
        return {"gi": {}, "hsr": {}, "zzz": {}}


async def scrape_gi_chars(page) -> dict[str, dict]:
    """Visit GI all-builds page, get all char URLs, then visit each for infobox data."""
    print("  [gi] loading all-builds page...")
    await page.goto(GI_ALL_BUILDS_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(8000)

    char_list = await page.evaluate(_GI_CHAR_LIST_JS)
    print(f"  [gi] found {len(char_list)} characters on all-builds page")

    results: dict[str, dict] = {}
    for i, char in enumerate(char_list):
        name = char["name"]
        url  = char.get("url")
        if not url:
            print(f"  [gi] ({i+1}/{len(char_list)}) {name}: no URL, skipping")
            continue

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            info = await page.evaluate(_INFOBOX_JS)
        except Exception as e:
            print(f"  [gi] ({i+1}/{len(char_list)}) {name}: ERROR {e}")
            continue

        entry: dict = {}
        if info.get("rarity"):
            entry["rarity"] = info["rarity"]
        if info.get("element"):
            entry["element"] = info["element"]
        if info.get("weapon"):
            entry["weapon_type"] = info["weapon"]

        if entry:
            results[name] = entry
            print(f"  [gi] ({i+1}/{len(char_list)}) {name}: rarity={entry.get('rarity')}, element={entry.get('element')}, weapon={entry.get('weapon_type')}")
        else:
            print(f"  [gi] ({i+1}/{len(char_list)}) {name}: no infobox data found (raw={info})")

    return results


async def scrape_hsr_rarity(page) -> dict[str, int]:
    """Get HSR char names from 5★ and 4★ filter pages."""
    rarity_map: dict[str, int] = {}

    for rarity, url in [(5, HSR_5STAR_URL), (4, HSR_4STAR_URL)]:
        print(f"  [hsr] loading {rarity}★ filter page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        chars = await page.evaluate(_RARITY_LIST_JS, "hsr")
        print(f"  [hsr] {rarity}★: found {len(chars)} chars")
        for c in chars:
            name = c["name"]
            if name not in rarity_map:
                rarity_map[name] = rarity
                print(f"    {name} (★{rarity})")

    return rarity_map


async def scrape_hsr_char_urls(page) -> dict[str, str]:
    """Discover HSR char URLs from element-filtered pages."""
    url_map: dict[str, str] = {}

    for element, url in HSR_ELEMENT_URLS.items():
        print(f"  [hsr] loading {element} element page...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
            chars = await page.evaluate(_HSR_ELEM_PAGE_CHARS_JS, element)
            print(f"  [hsr] {element}: found {len(chars)} chars")
            for c in chars:
                if c["name"] not in url_map:
                    url_map[c["name"]] = c["url"]
        except Exception as e:
            print(f"  [hsr] {element} page ERROR: {e}")

    return url_map


async def scrape_hsr_elements(page, url_map: dict[str, str], existing_rd: dict) -> dict[str, dict]:
    """Visit individual HSR pages where element is missing."""
    results: dict[str, dict] = {}
    missing_elem = [n for n, url in url_map.items()
                    if not (existing_rd.get(n) or {}).get("element")]
    print(f"  [hsr] visiting {len(missing_elem)} pages for missing element data")
    for i, name in enumerate(missing_elem):
        url = url_map[name]
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            info = await page.evaluate(_INFOBOX_JS)
            entry: dict = {}
            if info.get("element"):
                entry["element"] = info["element"]
            if info.get("path"):
                entry["path"] = info["path"]
            if info.get("rarity"):
                entry["rarity"] = info["rarity"]
            if entry:
                results[name] = entry
                print(f"  [hsr] ({i+1}/{len(missing_elem)}) {name}: {entry}")
        except Exception as e:
            print(f"  [hsr] ({i+1}/{len(missing_elem)}) {name}: ERROR {e}")
    return results


async def scrape_zzz_rarity(page) -> dict[str, int]:
    """Get ZZZ char names from S-rank and A-rank filter pages."""
    rarity_map: dict[str, int] = {}

    for rarity, url in [(5, ZZZ_SRANK_URL), (4, ZZZ_ARANK_URL)]:
        rank_label = "S" if rarity == 5 else "A"
        print(f"  [zzz] loading {rank_label}-rank filter page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        chars = await page.evaluate(_RARITY_LIST_JS, "zzz")
        print(f"  [zzz] {rank_label}-rank: found {len(chars)} chars")
        for c in chars:
            name = c["name"]
            if name not in rarity_map:
                rarity_map[name] = rarity
                print(f"    {name} ({rank_label}-rank)")

    return rarity_map


def merge_gi(existing_gi: dict, gi_info: dict[str, dict]) -> dict:
    """Merge scraped GI char info into release_data."""
    result = dict(existing_gi)
    for name, info in gi_info.items():
        if name not in result:
            result[name] = {}
        if info.get("rarity"):
            result[name]["rarity"] = info["rarity"]
        if info.get("weapon_type"):
            result[name]["weapon_type"] = info["weapon_type"]
        if info.get("element") and not result[name].get("element"):
            result[name]["element"] = info["element"]
    return result


def merge_hsr(existing_hsr: dict, rarity_map: dict[str, int],
              hsr_builds: list) -> dict:
    """Merge scraped HSR rarity into release_data, matching by name."""
    result = dict(existing_hsr)
    build_names = {c["name"].lower(): c["name"] for c in hsr_builds}

    # Direct match + case-insensitive match
    for scraped_name, rarity in rarity_map.items():
        # Direct
        if scraped_name in result:
            result[scraped_name]["rarity"] = rarity
            continue
        # Case-insensitive
        key = scraped_name.lower()
        if key in build_names:
            canonical = build_names[key]
            if canonical in result:
                result[canonical]["rarity"] = rarity
                continue
        # Partial: scraped name may be missing "Dan Heng •" prefix etc.
        for rd_name in result:
            if scraped_name.lower() in rd_name.lower() or rd_name.lower() in scraped_name.lower():
                result[rd_name]["rarity"] = rarity
                break

    return result


def merge_zzz(existing_zzz: dict, rarity_map: dict[str, int],
              zzz_builds: list) -> dict:
    """Merge scraped ZZZ rarity into release_data, matching builds names → release_data names."""
    result = dict(existing_zzz)

    # ZZZ release_data uses full names, builds uses short names
    # Build a lookup: normalized short name → full release_data name
    rd_lower: dict[str, str] = {}
    for rd_name in result:
        # Use last word and first word for matching short names
        rd_lower[rd_name.lower()] = rd_name
        # Also try just first name
        first = rd_name.split()[0].lower()
        if first not in rd_lower:
            rd_lower[first] = rd_name

    for scraped_name, rarity in rarity_map.items():
        # Direct match
        if scraped_name in result:
            result[scraped_name]["rarity"] = rarity
            continue
        # Lowercase match
        key = scraped_name.lower()
        if key in rd_lower:
            result[rd_lower[key]]["rarity"] = rarity
            continue
        # Also check builds.json names (short names match scraped names)
        # builds short name → find release_data entry
        for build in zzz_builds:
            bn = build["name"]
            if bn.lower() == key or bn.lower().split(":")[0].strip() == key:
                # find rd entry that might correspond
                for rd_name in result:
                    rd_n = rd_name.lower()
                    if bn.lower().split()[0] in rd_n:
                        result[rd_name]["rarity"] = rarity
                        break
                break
        else:
            # Last resort: add directly using scraped name
            if scraped_name not in result:
                result[scraped_name] = {"rarity": rarity}
            else:
                result[scraped_name]["rarity"] = rarity

    return result


async def main_async() -> None:
    existing = load_existing()

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=UA,
        )
        page = await ctx.new_page()

        # ── GI ────────────────────────────────────────────────────────────────
        print("\n[GI] Scraping character info...")
        gi_info = await scrape_gi_chars(page)
        print(f"[GI] Got info for {len(gi_info)} characters")

        # ── HSR ───────────────────────────────────────────────────────────────
        print("\n[HSR] Getting rarity from filter pages...")
        hsr_rarity = await scrape_hsr_rarity(page)
        print(f"[HSR] Got rarity for {len(hsr_rarity)} characters")

        print("\n[HSR] Discovering char URLs from element pages...")
        hsr_urls = await scrape_hsr_char_urls(page)
        print(f"[HSR] Found URLs for {len(hsr_urls)} characters")

        hsr_builds = json.loads(BUILDS_HSR.read_text())
        hsr_elem_data = await scrape_hsr_elements(page, hsr_urls, existing.get("hsr", {}))

        # ── ZZZ ───────────────────────────────────────────────────────────────
        print("\n[ZZZ] Getting rarity from rank filter pages...")
        zzz_rarity = await scrape_zzz_rarity(page)
        print(f"[ZZZ] Got rarity for {len(zzz_rarity)} characters")

        await browser.close()

    # ── Merge into release_data ───────────────────────────────────────────────
    gi_builds  = json.loads(BUILDS_GI.read_text())
    zzz_builds = json.loads(BUILDS_ZZZ.read_text())

    result = {
        "gi":  merge_gi(existing.get("gi", {}), gi_info),
        "hsr": merge_hsr(existing.get("hsr", {}), hsr_rarity, hsr_builds),
        "zzz": merge_zzz(existing.get("zzz", {}), zzz_rarity, zzz_builds),
    }

    # Merge HSR element data
    for name, info in hsr_elem_data.items():
        if name in result["hsr"]:
            for k, v in info.items():
                if not result["hsr"][name].get(k):
                    result["hsr"][name][k] = v

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")

    # Summary
    for game in ("gi", "hsr", "zzz"):
        total = len(result[game])
        with_rarity  = sum(1 for v in result[game].values() if v.get("rarity"))
        with_weapon  = sum(1 for v in result[game].values() if v.get("weapon_type"))
        with_element = sum(1 for v in result[game].values() if v.get("element"))
        print(f"  {game}: {total} chars | rarity={with_rarity} | weapon_type={with_weapon} | element={with_element}")


def main() -> None:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        print("Missing playwright. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
