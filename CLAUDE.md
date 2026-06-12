# CLAUDE.md — Archon

A guide for Claude Code working on the Archon app. Read this first.

## What this is

A character field guide / reference tool for three HoYoverse games: **Genshin Impact (GI)**, **Honkai: Star Rail (HSR)**, and **Zenless Zone Zero (ZZZ)**. The front-end is plain HTML + CSS + JS — no framework, no build step. Open `index.html` directly or serve the folder with any static server.

> **⚠️ Production rebuild (Nightdesk) — read before editing the front-end.**
> The live front-end is now the **Nightdesk** redesign (ported from `redesign/Dashboard & Build.html`):
> a recency-first **dashboard feed** (livestream → just-released hero band → banners + active events → event timeline → roster) with a **hero-expand character takeover**.
> - `index.html` — full-viewport shell: top app bar (`.bar`) + `#screen` / `#takeover` / `#tweaks`. `body[data-game]` drives the room tint.
> - `style.css` — the Nightdesk design system (per-game room tints on `body[data-game]`, signature accent on `--ec`).
> - `build-sheet.css` — the character build-sheet triptych (scoped to `#takeover .fullsheet`).
> - `app.js` — dashboard/roster engine (ported from `redesign/db-app.js`): feed sections, roster by era, countdowns, event popups, vanilla Tweaks panel. Loads real data. **Clock is live** (`LIVE_CLOCK = true` in `app.js`, `NOW = Date.now`). Set `LIVE_CLOCK = false` to pin to `SIM0` (the 4.2/4.3 window) for frozen-date demos/screenshots.
> - `sheet.js` — **data-driven** Nightdesk character sheet. Parses the real build JSON for all 3 games into the triptych (`buildSheetHTML(c)` / `wireSheet`).
> - The **old codebase** (rail + sidebar IA, ⌘K palette, tier-list view, compare panel, favorites/density, edit-mode/GitHub-sync, per-game build renderers) is preserved verbatim in **`legacy/`** (`index-legacy.html`, `app-legacy.js`, `style-legacy.css`). Those features were **not** part of the approved redesign and are the obvious next port — lift them from `legacy/` into the Nightdesk shell when needed.
> A full **Nightdesk architecture & design language** reference follows immediately below. Everything after it, under the **"Legacy reference"** divider, describes the old rail/sidebar codebase and applies to `legacy/` only — not the live app.

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## Backlog — deferred Nightdesk ports (not yet wired into production)

These legacy power-features exist **only** in `legacy/` and were intentionally deferred (user decision, June 2026). Revisit when wanted; each is a self-contained port from `legacy/app-legacy.js` into the Nightdesk shell:

- **⌘K command palette** — fuzzy character search + quick-jump (and shift-↵ set-compare). Highest-utility, lowest-risk; do this first if resuming. Lives in `legacy/app-legacy.js` (`openPalette` / `buildPaletteItems` / `renderPalette` / `handlePaletteKeydown`).
- **Tier-list view** — filtered grid grouped by tier (T0/SS…D), with element/path/"new only" filters. `showTierView` / `renderTierView`; tier colors in `tierColor()`/`TIER_BLURBS`.
- **Compare panel** — two characters side-by-side as a third column. `setCompareChar` / `clearCompare` / `renderCompareView`; gated on `body.compare-on`.
- **Favorites / pinning + density toggle** — pin chars (per-game) to a "Pinned" group; compact list mode. localStorage `archon:favorites`, `archon:density`, `archon:collapsed-groups`.
- **Edit-mode + GitHub sync** — in-app build editing + push/pull overrides via a worker. `legacy/app-legacy.js` sync modal + `worker/`.

If/when porting: lift the renderer from `legacy/`, reskin to the Nightdesk design language (room tints on `body[data-game]`, `--ec` accent, `build-sheet.css` vocabulary), and surface entry points in the top app bar (`.bar`), not a left rail.

---

# Nightdesk reference (THE LIVE APP — read this for all new work)

## Files (the live app)
- `index.html` — full-viewport shell. `body[data-game]` (gi/hsr/zzz) drives the room tint. Structure: `.stage > #frame[data-device] > .device > #screen + #takeover + #tweaks`. Loads `sheet.js` **before** `app.js` (both are plain global scripts — no modules).
- `style.css` — the Nightdesk design system: `:root` tokens, per-game room tints, the device frame, and every feed/dashboard component.
- `build-sheet.css` — the character build-sheet triptych, scoped to `#takeover .fullsheet`. Self-contained; owns `--ec` (per-character signature accent) consumers.
- `app.js` — the engine (~735 lines). Loads all data in `init()`, holds state in `S`, renders the feed into `#screen`, runs the 1s `tick()`, opens the character takeover, and drives the vanilla Tweaks panel.
- `sheet.js` — the **data-driven** character sheet. An IIFE exposing `window.buildSheetHTML(c)` and `window.wireSheet(tk, c)`. Reads the real build JSON and lays it into the triptych. Borrows globals from `app.js` (`S`, `GAMES`, `RARITY`, `elColor`, `esc`, …) at call time.

Data files are unchanged from the legacy app (see the Legacy reference's "Data files"), plus `item_icons.json` / `disc_icons.json` are now loaded in `init()`'s `Promise.all`.

## Shell & layout (the IA)
```
body[data-game]                      ← room tint
 └ .stage                            ← letterbox backdrop
    └ #frame[data-device]            ← desktop | mobile (402×820 device frame)
       └ .device
          ├ #screen                  ← the dashboard FEED (always present)
          ├ #takeover                ← character build sheet (overlay; hero-expand zoom)
          └ #tweaks                  ← Tweaks panel
```
**Feed order** (each section is a function returning an HTML string, or `''` to omit itself):
`topbar()` → `livestreamSection()` → `heroSection()` → `dashboardSection()` (banner + ending-soon) → `eventSection()` (gantt) → `rosterSection()` (by region/era).

**Responsive**: `setDevice()` flips `#frame[data-device]` between `desktop` and `mobile` at the 640px breakpoint and re-renders. Mobile is a centered 402×820 phone frame; the feed and the sheet triptych both collapse to one column (`#frame[data-device="mobile"]` rules in `style.css` + `build-sheet.css`).

**No URL-hash routing** in the live app (the legacy app had it). Navigation is just `S` + `render()`. The only persistence is the Tweaks blob in `localStorage['archon:whatsnew:tweaks']`.

## Render model
`render(reason)` is the whole loop: it sets `body.dataset.game`, rebuilds `#screen.innerHTML` from the section functions, then calls `tick()`, `wireScreen()`, `wireEventPops()`. `reason ∈ {boot, game, tweak, resize}` — the first three set `S.animate = true` so the entrance reveal plays; `resize` does not. **Always re-render a whole region from a string; never diff.** It's cheap because the feed is small.

`tick()` runs every 1s and updates every `[data-deadline]` element in place (see Motion). `openChar(name, tileEl)` fills `#takeover` with `buildSheetHTML(c)` and runs the hero-expand zoom from the clicked tile; `closeChar()` reverses it.

## Design tokens (in `style.css` — USE THESE, never hardcode)
**Type** — three families, on short var names (NOT the legacy `--font-*`):
- `--fd` Schibsted Grotesk — display: names, titles, version numbers, eyebrows.
- `--fm` IBM Plex Sans — body: labels, pills, copy, controls. (`body` defaults to this.)
- `--fnum` IBM Plex Mono, tabular figures — numerals ONLY where the instrument-panel quality earns it (countdown digits `.cd-seg b`, tier letters). Don't blanket the UI in mono.

**Room palette** — set per game on `body[data-game="…"]`; components read the role tokens, never the raw hex:
`--bg --surface --card --card2 --card-hi --border --border-hi` (surfaces), `--ink --dim --faint` (text), `--amb-a --amb-b` (ambient gradient pair), and the signature `--accent --accent2 --accent-soft --accent-line`. GI = blue, HSR = violet, ZZZ = amber.

**Semantic (game-independent)**: `--mint`/`--mint-soft`/`--mint-line` (live/positive), `--amber`/`--amber-soft`/`--amber-line` (warn/ending-soon).

**Per-character signature**: `accentFor(c)` returns a character's hue (element color, or a hand-set signature like Evanescia's rose). The build sheet sets `--ec`/`--ec2` from it; use `--ec` for the sheet's accents.

**Geometry & motion**: radii `--r-card:14 / --r-sm:9 / --r-chip:6`; `--shadow`, `--shadow-lift`; rhythm `--pad-x:28 / --gap-sec:30`; easing `--ease`. Hover lift is a small `translateY(-1…-3px)` — don't animate big shadows.

## Motion language (keep it calm)
- **Entrance**: `.reveal` elements rise/fade once, staggered by `--i` (set via the `reveal()` helper), only when `S.animate` and `.anim` is on the screen.
- **Timers**: never rebuild a countdown's `innerHTML` each second. The segmented countdown (`.cd[data-cd="seg"]`) updates each `.cd-seg > b` in place and fades **only the digit that changed** (`.dchg`). Text timers (`short`/`full`/`inline`) go through `setTimerText()`, which writes only on change and fades with `.cd-fade`. Both keyframes are a soft opacity-only dip (`cddigit`).
- All motion is gated on `S.tw.motion` (the Tweaks "Live animations" toggle) **and** `@media (prefers-reduced-motion)`. Honor both for anything new.

## Iconography
Inline SVG, 16-viewBox, `stroke="currentColor"`, width 1.3–1.6. **The catalog is `ICONS` in `app.js`** — add a glyph there and reference it (e.g. via `sec(iconKey, …)`); don't inline at the call site. Element/status dots are flat circles with `box-shadow: 0 0 6px currentColor`.

## Component vocabulary (class → what it is)
- `.bar` topbar; `.gswitch`/`.gs-btn`/`.gs-dot` game switcher.
- `.block` is a feed section wrapper; `.sec` + `.sec-ico` is its header (built by `sec(icon,title,meta,mod,right)`).
- `.card` generic surface; `.panel` (`.live` / `.warn`) the dashboard panels; `.dash`(`.cols`) the banner+ending-soon row.
- `.ls`/`.ls-*` livestream strip; `.cd`/`.cd-seg` the shared countdown display.
- `.fcard`/`.fcard-*` the "just released" hero card(s).
- `.bn-*` banner items, `.es-*` ending-soon rows, `.evt-*` the event gantt (axis, rows, now-line, hover `.evt-pop`).
- `.tile` roster cards (grouped by era).
- Sheet (in `build-sheet.css`): `.sheet`/`.fullsheet` triptych; columns `.col.l` (identity), `.col` mid (build), `.col` right (teams/pull/abilities); `.card`+`.clab` cards, `.pill`/`.nm2` item names, `.flow` substat flow, `.trow` ability rows, `.av` team avatars, `.pull` pull-priority.

## How to add things (Nightdesk)
**A feed section** — write `mySection()` returning an HTML string (return `''` when it has no data so it self-hides); add it to the screen template array inside `render()`; wire any clicks in `wireScreen()`; if it has a header, add a glyph to `ICONS` and use `sec()`.

**A build-sheet card** — in `sheet.js`, build markup with the `card(label, meta, body)` helper and push it into the relevant column array in `buildSheetHTML`. Pull data through `normalize(game, c)` (which maps each game's build JSON to a common shape) — don't special-case a character; extend the parser/normalizer.

**A Tweak** — add a key+default to `S.tw`, a control in `renderTweaks()`, and apply it in `applyTweaks()` (CSS var on `:root` or a `body` class). Persisted automatically via `commitTweak()`/`TW_KEY`.

**A 4th game / new character / patch data** — data workflow (parsers + JSON) is unchanged (see Legacy reference). New touchpoints for a game: `GAMES`, `GAME_ORDER`, `GAME_DOT`, `ELEMENT_ORDERS`, `ELEMENT_COLORS`, `ERA_MAP`, a `body[data-game="xxx"]{…}` tint block in `style.css`, and (if its build shape differs) a branch in `sheet.js`'s `normalize()`.

## Code map (`app.js`)
```
constants: GAMES/GAME_ORDER/GAME_DOT, LIVE_CLOCK+NOW, ELEMENT_*,    ~14–88
  RARITY, EVENT_TYPES, ERA_MAP, ICONS, S (state), TW_KEY
boot: init() (loads JSON, builds S.data/S.builds), setDevice()       ~90–130
roster helpers: roster() / eraOf() / byEra()                        ~135–160
chrome: gameSwitch() / topbar() / sec()                             ~162–197
render(): the loop + reveal() helper                                ~198–223
feed §1 livestreamSection                                           ~225
feed §2 heroSection (currentVersion / heroCard)                     ~253
feed §3 dashboardSection (bannerPanel / endingSoonPanel)            ~292
feed §4 eventSection (the gantt)                                    ~385
feed §5 rosterSection                                               ~453
countdown: fmtSeg/fmtFull/fmtShort/fmtInline, setTimerText, tick()  ~477–589
character takeover: openChar / closeChar  (delegates to sheet.js)   ~590–625
wiring: wireScreen / wireChrome                                     ~626–645
tweaks: loadTweaks / saveTweaks / applyTweaks / renderTweaks        ~646–end
```
`sheet.js`: `buildSheetHTML(c)` (triptych) · `normalize(game,c)` (per-game build→common shape) · parsers `parseItems`/`parseEngines`/`cleanDesc` · `wireSheet`.

## Hard rules (Nightdesk)
- **No build step, no framework, no URL-hash routing.** Vanilla JS/CSS; state is `S` + the Tweaks localStorage blob.
- **Tokens, never hex.** Type is `--fd`/`--fm`/`--fnum`; color via the room tokens on `body[data-game]` and `--ec` on the sheet.
- **Sections self-hide** by returning `''`; **all data is optional** — guard every field (a thin patch JSON must not crash the feed).
- **Timers update in place** and respect `S.tw.motion` + reduced-motion; never re-`innerHTML` a ticking element.
- **One design language.** New treatments become a new `.card`/`.panel`/pill variant or `ICONS` glyph — don't fork a one-off style for a single screen.
- **Per-game and element/rarity colors stay coordinated** between `style.css` tints and the `ELEMENT_COLORS`/`RARITY` maps in `app.js`.

## Smoke test (Nightdesk, manual)
After any non-trivial change:
1. All three games load and the room tint changes when you switch (`body[data-game]`).
2. The feed shows livestream → hero → banner/ending-soon → event gantt → roster (sections with no data quietly disappear).
3. Clicking a roster tile / hero card / banner opens the takeover with a real build sheet (named cones/weapons + rarity, sets, teams) — try one character per game. Back / Esc closes it.
4. Countdowns tick calmly — only the changing digit fades; no full-strip flash.
5. Resize below 640px: the phone frame appears, feed and sheet collapse to one column, no horizontal overflow.
6. Toggle Tweaks → "Live animations" off kills all motion; font/accent/layout tweaks apply and survive reload.

---

# Legacy reference — `legacy/` only (old rail/sidebar app)

> Everything from here down documents the **previous** codebase, now preserved in `legacy/` (`index-legacy.html`, `app-legacy.js`, `style-legacy.css`). It is accurate for those files and is the guide for porting a deferred feature, but it does **not** describe the live app — note especially that the legacy app uses `--font-display`/`--font-body`/`--font-num`, a left rail + sidebar, and URL-hash routing, none of which exist in the Nightdesk app above.

## File map

### Front-end (the old app — three files, now in `legacy/`)
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
- **Display** (names, titles, version numbers, eyebrows): `Schibsted Grotesk`, 400–800 weight. CSS var: `--font-display`.
- **Body** (everything else — labels, pills, copy, controls): `IBM Plex Sans`, 400–600. CSS var: `--font-body`. (Was the old `--font-mono` role; renamed when body moved off mono.)
- **Numerals** (countdown digits, tier letters): `IBM Plex Mono`, tabular figures. CSS var: `--font-num`. Use **only** where the instrument-panel/data-readout quality earns it — don't blanket the UI in mono.
- Loaded from Google Fonts in `index.html`. Three families total — don't introduce a fourth.

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
