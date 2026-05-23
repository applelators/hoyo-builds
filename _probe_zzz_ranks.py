"""Get complete ZZZ A-rank and S-rank character lists."""
import asyncio
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# More thorough extraction - get all char images regardless of alt format
_ALL_CHARS_JS = """
(knownNames) => {
    const known = new Set(knownNames.map(n => n.toLowerCase().split(':')[0].trim()));
    const result = [];
    const seen = new Set();

    // Method 1: img alt text
    document.querySelectorAll('img').forEach(img => {
        const alt = (img.alt || '').trim();
        if (!alt) return;
        const altLow = alt.toLowerCase();
        if (known.has(altLow) || known.has(altLow.split(' ')[0])) {
            const a = img.closest('a');
            const href = a ? a.href : '';
            if (seen.has(altLow)) return;
            seen.add(altLow);
            result.push({ name: alt, method: 'img_alt', href });
        }
    });

    // Method 2: anchor text
    document.querySelectorAll('a').forEach(a => {
        const text = (a.innerText || '').trim().split('\\n')[0];
        const textLow = text.toLowerCase();
        if (!text || text.length > 50) return;
        if (known.has(textLow) || known.has(textLow.split(' ')[0])) {
            if (seen.has(textLow)) return;
            seen.add(textLow);
            result.push({ name: text, method: 'anchor_text', href: a.href });
        }
    });

    return result;
}
"""

_DUMP_ALL_IMGS_JS = """
() => {
    const result = [];
    document.querySelectorAll('img').forEach(img => {
        const alt = (img.alt || '').trim();
        const a = img.closest('a');
        result.push({ alt, href: a ? a.href.slice(-20) : '' });
    });
    return result;
}
"""

async def main():
    import json
    zzz_builds = json.loads(open('/Users/hokori/genshin-builds/zzz_builds.json').read())
    known_names = [c['name'] for c in zzz_builds]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=UA)
        page = await ctx.new_page()

        # A-rank page
        print("=== ZZZ A-rank page ===")
        await page.goto("https://game8.co/games/Zenless-Zone-Zero/archives/458129", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        title = await page.title()
        print(f"Title: {title}")

        # Try all chars extraction
        chars = await page.evaluate(_ALL_CHARS_JS, known_names)
        print(f"Found {len(chars)} A-rank chars:")
        for c in chars:
            print(f"  {c['name']!r} ({c['method']}) -> {c['href'][-15:]}")

        print("\nAll images on A-rank page:")
        imgs = await page.evaluate(_DUMP_ALL_IMGS_JS)
        for img in imgs[:40]:
            print(f"  alt={img['alt']!r}")

        # S-rank page
        print("\n=== ZZZ S-rank page ===")
        await page.goto("https://game8.co/games/Zenless-Zone-Zero/archives/458128", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        title = await page.title()
        print(f"Title: {title}")

        chars_s = await page.evaluate(_ALL_CHARS_JS, known_names)
        print(f"Found {len(chars_s)} S-rank chars:")
        for c in chars_s:
            print(f"  {c['name']!r} ({c['method']}) -> {c['href'][-15:]}")

        await browser.close()

asyncio.run(main())
