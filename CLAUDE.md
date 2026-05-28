# CLAUDE.md — Archon

A guide for Claude Code working on the Archon app. Read this first.

## What this is

A character field guide / reference tool for three HoYoverse games: **Genshin Impact (GI)**, **Honkai: Star Rail (HSR)**, and **Zenless Zone Zero (ZZZ)**. The front-end is plain HTML + CSS + JS — no framework, no build step. Open `index.html` directly or serve the folder with any static server.

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## File map

### Front-end (the live app — three files)
- `index.html` — DOM shell. Three regions: icon rail, sidebar, content. ⌘K palette modal at the bottom.
- `style.css` — all styling. Per-game tints, mobile breakpoints, all components.
- `app.js` — single ~2200-line vanilla JS file. Section banners (`// ── X ──`) mark the major chunks.

### Data files (read at boot by `init()`)
- `builds.json` / `hsr_builds.json` / `zzz_builds.json` — per-game character builds (parser output)
- `tiers.json` — `{ gi|hsr|zzz: { charName: tierLabel } }`
- `icons.json`, `portraits.json` — character avatars and splash art per game
- `release_data.json` — `{ gi|hsr|zzz: { charName: { version, date, element } } }`
- `banners.json` — current/upcoming gacha banners. Drives the Pull Guide landing.
- `events.json` — event calendar. Drives landing-page event list.
- `livestreams.json` — next-version livestream date. Drives countdown strip.
- `team_map.json`, `disc_map.json`, `disc_icons.json` — ZZZ-specific lookups.

The latter three banner/event/livestream files start with a `$schema` block documenting their fields, source-wiki URLs, and scrape hints.

### Scrapers (Python, manual run per patch)
- `fetch_banners.py` / `fetch_events.py` / `fetch_livestreams.py` — pull from Fandom wikis. **Preserve manual fields** (verdicts, taglines, highlights) across runs.
- `fetch_portraits.py` / `fetch_icons.py` / `fetch_release_data.py` / etc. — asset/metadata refresh.
- `parse.py` / `parse_hsr.py` / `parse_zzz.py` — turn published Google Sheets into `*_builds.json`.

### Mockup-only files (not loaded by the live app)
- `Cyrene Variations.html`, `Nav Variations.html`, `Tier Variations.html`, `Landing Variations.html`, `Polish Font Pairings.html`, `cyrene-*.jsx`, `nav-*.jsx`, `tier-*.jsx`, `lp-*.jsx`, `design-canvas.jsx`, `tweaks-panel.jsx` — reference mockups from the redesign process. Safe to delete or ignore. Class prefixes from these (`v1-*`, `nA-*`, `t1-*`, `lp1-*`, etc.) must **never** appear in the live app.

## Design language

### Type
- **Display** (names, titles, large numbers): `Bricolage Grotesque` variable, 400–700 weight. CSS var: `--font-display`.
- **Mono** (everything else): `DM Mono`, 400/500 only — never bold. CSS var: `--font-mono`.
- Loaded from Google Fonts in `index.html`. Don't introduce a third family.

### Color
Per-game tint, applied via body class:
- **GI** (no class) — cool blue (`#0a0d14`, blue + sky ambient)
- **HSR** (`body.game-hsr`) — purple (`#0d0a14`, violet ambient)
- **ZZZ** (`body.game-zzz`) — warm orange (`#100c08`, orange + amber ambient)

Each game sets `--bg`, `--surface`, `--card`, `--card-hi`, `--border`, `--border-hi`, `--ambient-a`, `--ambient-b`. The ambient gradient pair renders via `body::before` — intentionally subtle flavoring.

**Per-character accent**: `applyCharAccent(char)` sets `--char-accent` / `--char-accent-soft` / `--char-accent-fg` on `:root`. Use these for card label underlines, role callout left-bar, primary CTAs, sidebar active border, breadcrumb current item.

**Element colors** live in `ELEMENT_COLORS` in `app.js` — `[idle, active, dark]` triplet per element. `[1]` is the active tint.

**Rarity tints**: 5★ gold (`#fcd66e` / `#f0b400`), 4★ purple (`#d4bbff` / `#b78bff`), 3★ blue (`#a8c8ff` / `#5b9eff`). Auto-detected from `(5✩)` / `5★` patterns via `detectRarity()`.

**Tier colors** must stay coordinated between `.tier-*` CSS rules (sidebar badges) and `tierColor()` / `tierFg()` / `tierRank()` in `app.js`. T0/SS = gold, T0.5 = darker orange, T1/S = purple, T1.5 = blue-purple, T2/A = blue, T3/B = green, T4/C = muted, D = dark. Tier name + blurb data lives in `TIER_BLURBS` in `app.js`.

### Geometry
- Border radius: 4–6px chips/pills, 7–8px buttons, 10–12px cards/portrait/banner/palette.
- Card padding: `12–14px 14–18px`. Tight over generous.
- Animation: 0.12s for hover color changes, 0.15–0.22s for entry fade / scale-in, 0.4s for full-room game-switch transitions only.
- Hover lift: `transform: translateY(-1px to -3px)` — don't animate `box-shadow` heavily.

### Iconography
All icons are inline SVG, 16×16 viewBox, `stroke="currentColor"`, `stroke-width: 1.3–1.6`. **The catalog is `SECTION_ICONS` in `app.js`** — add new glyphs there, don't inline at the call site. Element/status dots are flat circles with `box-shadow: 0 0 6px currentColor` for the soft glow.

### Component voice
- **Card labels** — mono, 10px, uppercase, 0.1em tracking, `var(--char-accent)`, thin tinted bottom border, prefixed with a `SECTION_ICONS` glyph.
- **Section eyebrows** — mono, 10px, 0.22em tracking, uppercase, accent color.
- **Buttons** — mono, uppercase, 0.04–0.08em tracking. Primary = colored fill; secondary = transparent + border.
- **Rarity pills** — colored border + 14% bg tint + bright foreground text.
- **Element pills** — small colored dot + neutral text.

## Layout (the Codex IA)

```
┌──────┬──────────┬─────────────────────────────────┐
│ Rail │ Sidebar  │  Content                        │
│ 56px │ 300px    │  (placeholder / char-view /     │
│      │          │   tier-view)                    │
└──────┴──────────┴─────────────────────────────────┘
```

**Rail** (`#rail`) — icon-only vertical nav. Three game switchers on top, four lenses (Characters / Tiers / Pinned / Compare) below, density toggle at the bottom. Tooltips via `data-tip`. Goes to a horizontal scrolling bottom bar at `≤ 640px`.

**Sidebar** (`#sidebar`) — game name + count, palette trigger, element filter chips, then character list grouped by element with collapsible headers. "Pinned" group appears above when favorites exist.

**Content** — three mutually-exclusive views:
- `#placeholder` — landing (Pull Guide)
- `#char-view` — character detail
- `#tier-view` — tier list

### Character detail layout
- `#char-left` (sticky on desktop) — portrait + role callout + stat targets + pull priority cards.
- `#char-right` — tabs + build cards (1 col, 2-col at ≥1280px) + notes.
- `#compare-panel` — third column when `body.compare-on`.
- `#crumbs` above — `GAME · path/element · Name`.

### Landing (Pull Guide)
- `.pg-livestream` — countdown strip at top (auto-hides if >1 day past).
- `.pg-banner` — featured character with verdict + timer + CTAs.
- `.pg-twocol` — "Coming next" + "Worth pulling" side-by-side.
- `.pg-events` — event calendar grid below.
- Falls back to a "latest 3" highlights row when `banners.json` is empty.

### Tier list (Filtered Grid)
- `.tv-head` (search) + `.tv-filterbar` (Element / Path / "New only" + density toggle).
- One `.tv-section` per tier with banner (letter + name + blurb + count), then `.tv-grid` of `.tv-chip` items.

## State

All state in module-scoped variables at the top of `app.js`. **No store, no reducer, no event bus.** Render functions read state and write innerHTML.

**localStorage keys** (all prefixed `archon:`):
- `archon:favorites` — pinned characters per game
- `archon:density` — compact-list mode
- `archon:collapsed-groups` — element groups collapsed in sidebar, per game

**URL hash** is the source of truth for navigation:
- `#game=hsr&char=Acheron&compare=Cyrene` — game, character, optional compare
- `#game=hsr&view=tier` — tier view open

`applyUrlState()` restores from hash on boot + `popstate`. `updateUrl()` writes to it whenever the user changes selection.

## Keyboard shortcuts (in `handleKeydown`)

- `⌘K` / `Ctrl+K` or `/` — open palette
- `Esc` — close palette → exit compare → go back
- `j` / `↓` — next character; `k` / `↑` — previous
- `1` / `2` / `3` — switch GI / HSR / ZZZ
- `↵` in palette — open; `⇧↵` in palette — set as compare target

## Code map (`app.js`)

```
state, localStorage helpers       lines 25–110
ELEMENT_ORDER + ELEMENT_COLORS    ~115–130
applyCharAccent                   140
detectRarity                      155
SECTION_ICONS + sectionIcon       ~160–190
parseStatTargets + statTargetCard ~192–240
pullPriorityCard                  ~241
lookupIcon, teamMemberThumb       ~250–280
statusPill                        ~286
init                              304   ← loads all JSON, wires events
applyUrlState / updateUrl         420 / 446
handleKeydown                     458
openPalette + buildPaletteItems + renderPalette + handlePaletteKeydown
                                  498–690
setCompareChar / clearCompare / renderCompareView
                                  692–765
renderHighlights / renderPullGuide / renderLivestreamStrip / renderEventsBlock
                                  767–1095   ← landing page
switchGame / _switchGameNoUrl     1098
updateGameLabel                   1125
releaseKey / charElement          1134–1150
renderElementFilters              1153
updateLensState                   1214
refreshList / renderList / buildListItem
                                  1226–1360   ← sidebar list
renderCrumbs                      1384
selectChar / _selectCharNoUrl     1403
renderTabs / renderBuild          1467 / 1490
renderRoleCallout                 1504
renderGiBuild / renderHsrBuild / renderZzzBuild
                                  1538 / 1549 / 1586
parseItemList / itemListHtml / itemCard
                                  1614–1683
parseAbilityPriority / abilityChainHtml / abilityCard
                                  1685–1745
parseHsrSets / hsrRelicCard       1745–1780
parseStatGrid / statGridRows      1781–1805
zzzDiscCard / zzzTeamCard         1807–1900
renderNotes                       1907
card / cardRaw / colorize         1928–1950
charTier / showTierView / renderTierView
                                  1952–2195   ← tier list view
formatReleaseDate / toTitle / escHtml   2197–2225
```

DOM updates always re-render their region from `innerHTML`. Cheap because the page is small. **Don't introduce a virtual DOM or framework.**

## How to add things

### A new character to an existing game

The parsers use a **two-file workflow**:
- `*_builds.json` — **canonical** (what the app reads). User-editable. **Never overwritten by the parser.**
- `*_builds_scrape.json` — raw parser output. Overwritten on every run. Used as the diff baseline.

Run the parser to see what changed in the spreadsheet:
```bash
python parse.py        # GI  → writes builds_scrape.json, diffs vs previous scrape
python parse_hsr.py    # HSR → writes hsr_builds_scrape.json
python parse_zzz.py    # ZZZ → writes zzz_builds_scrape.json
```
The parser prints a diff report (NEW / UPDATED / REMOVED characters). Apply changes you want to `*_builds.json` manually — either copy individual entries from the scrape file or copy the whole file if no manual edits exist yet.

Then refresh icons/portraits if new characters appeared:
```bash
python fetch_portraits.py && python fetch_icons.py
```

### Update banner/event/livestream for a new patch
```bash
python fetch_banners.py
python fetch_events.py
python fetch_livestreams.py
```
Then hand-edit the verdict / tagline / highlights in the resulting JSON. The scrapers preserve manual fields by matching on stable keys.

### Add a card to the character detail
1. Write a renderer that returns an HTML string. Shortest example: `pullPriorityCard`.
2. Either return it from `renderRoleCallout` (appends to `#left-cards`) for the left column, or include it in the `panel.innerHTML = [...].join('')` array inside `renderGiBuild` / `renderHsrBuild` / `renderZzzBuild`.
3. If it has a label, add a glyph to `SECTION_ICONS` and use `sectionIcon(label)` inside the label `<div>`.

### Add a new lens to the rail
1. In `index.html`, add `<button class="rail-btn rail-lens" data-lens="X" data-tip="Y">…</button>` inside `#lens-nav`.
2. In `app.js` `init()`, register a click handler in the `.rail-lens` loop.
3. In `updateLensState()`, set `.active` based on your lens's state.

### Add a 4th game
Touchpoints:
- Add element names to `ELEMENT_ORDERS` and `ELEMENT_COLORS`.
- Add keys to `tiersData`, `releaseData`, `icons`, `portraits`.
- Update `_switchGameNoUrl` body-class toggling.
- Write a new `renderXxxBuild` for the game's build shape.
- Add a new `body.game-xxx { ... }` block in `style.css` with the per-game tint.
- Add a new game button to the rail in `index.html`.
- Write `fetch_*.py` and `parse_*.py` for the source data.

### Add a Tweaks panel
The starter `tweaks-panel.jsx` is **not used by the live app** — the live app has no React. If you want tweakable controls, prefer:
1. Vanilla equivalents wired to localStorage that apply via CSS custom properties on `:root`.

Don't introduce React without strong justification.

## Hard rules

- **No build step.** No bundlers, transpilers, or `node_modules` for the front-end.
- **No framework.** Vanilla JS, vanilla CSS. The mockup `.jsx` files are references, never dependencies.
- **All data is fetched lazily on boot.** New data files go into `init()`'s `Promise.all`. Always `.catch(() => ({}))` so a missing file doesn't crash.
- **URL hash is the source of truth** for game/character/compare/tier-view. Update via `updateUrl()`. Parse on load via `applyUrlState()`.
- **CSS custom properties for accent, ambient, type.** Never hardcode font stack or per-character color in component CSS.
- **Section glyphs in one map.** Add to `SECTION_ICONS`, don't inline.
- **Mobile is the bottom rail.** The rail must stay accessible at `≤ 640px` as a horizontal bottom bar.
- **Element + tier colors are coordinated globally.** Adding a new element requires updating `ELEMENT_COLORS` and possibly per-game tints in CSS.

## Conventions

- Two-letter game IDs everywhere: `'gi'`, `'hsr'`, `'zzz'`. Never spelled out.
- Character keys are exact `name` strings from the build JSON (case-sensitive). Cross-reference by name, never slug.
- ISO dates everywhere; ISO datetime for livestreams (`YYYY-MM-DDTHH:mm:ssZ`).
- Class-name prefixes:
  - `rail-*` — left rail
  - `pg-*` — pull guide / landing
  - `tv-*` — tier view
  - `cmp-*` — compare panel
  - `palette-*` — ⌘K modal
  - `hl-*` — fallback highlights row
  - `pg-event*`, `pg-livestream*` — landing subsections
  - `nA-*`, `nB-*`, `t1-*`–`t4-*`, `lp1-*`–`lp5-*`, `v1-*` are **mockup-only**, never used by live app.

## Don't do this

- **No per-character special cases** in the build renderers. Every character must flow through the same parsers; if a character's data breaks the parser, fix the parser, not the renderer.
- **No hard-coded tier names** outside `TIER_BLURBS` and `tierColor()`.
- **No emoji as functional UI.** SVG glyphs only.
- **No forked design language** for one screen. If a new treatment is needed, flow it back into the design system (new card type, new pill variant, new section glyph).
- **No build step or framework** without asking the user.

## Smoke test (manual)

After any non-trivial change, verify:
1. All three games load (toggle the rail).
2. A character per game opens and renders cards.
3. ⌘K palette opens, finds a character, opens it.
4. Tier list opens via the rail bar-chart icon and filters work.
5. Landing shows the Pull Guide if `banners.json` has entries; latest-3 row otherwise.
6. URL hash updates on every selection and reloads correctly.
7. Resize to ~375px: rail moves to bottom, sidebar / content swap on character select, back button appears.
