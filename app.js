/* ══════════════════════════════════════════════════════════════
   Archon — production app engine (Nightdesk).
   Ported from the approved redesign/db-app.js: dashboard feed,
   roster, countdown, event popups, tweaks. Real data paths.
   Character sheet is delegated to sheet.js (renders real builds).
   ══════════════════════════════════════════════════════════════ */
/* ══════════════════════════════════════════════════════════════
   Archon · What's New  — standalone landing
   A "what's happening now" dashboard: livestream countdown, just-
   released hero band, banner + ending-soon dashboard, event gantt,
   and the full by-region roster. Vanilla JS, single data load.
   ══════════════════════════════════════════════════════════════ */

const GAMES = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
const GAME_ORDER = ['gi', 'hsr', 'zzz'];
const GAME_DOT = { gi: '#5b9eff', hsr: '#a78bfa', zzz: '#f0a042' };

// ── clock source ──────────────────────────────────────────────
//   LIVE_CLOCK = true  → NOW() is the real wall clock (production default).
//   LIVE_CLOCK = false → pin "now" to SIM0 below, so the demo dashboard tells
//     one coherent story (live banner + just-released hero + livestream soon)
//     regardless of the real date. Real seconds still tick, so countdowns animate.
//   Flip to false only for screenshots/demos against a frozen patch window.
const LIVE_CLOCK = true;
const _REAL0 = Date.now();
const SIM0 = Date.parse('2026-05-20T15:30:00Z');
const NOW = LIVE_CLOCK ? () => Date.now() : () => SIM0 + (Date.now() - _REAL0);

// Evanescia is Physical element / Elation path — her signature accent is Elation rose.
const EVA_ROSE = '#f472b6', EVA_ROSE2 = '#db2777';
const accentFor = c => (c && c.name === 'Evanescia') ? EVA_ROSE : elColor(c && c.element);

const ELEMENT_ORDERS = {
  gi:  ['Pyro', 'Hydro', 'Cryo', 'Electro', 'Anemo', 'Geo', 'Dendro'],
  hsr: ['Fire', 'Ice', 'Wind', 'Lightning', 'Physical', 'Quantum', 'Imaginary', 'Elation'],
  zzz: ['Physical', 'Fire', 'Electric', 'Ice', 'Ether'],
};
const ELEMENT_COLORS = {
  Pyro:['#f87171','#ef4444'], Hydro:['#60a5fa','#3b82f6'], Cryo:['#67e8f9','#22d3ee'],
  Electro:['#a78bfa','#7c3aed'], Anemo:['#34d399','#10b981'], Geo:['#fbbf24','#d97706'],
  Dendro:['#86efac','#16a34a'], Fire:['#f87171','#ef4444'], Ice:['#67e8f9','#22d3ee'],
  Wind:['#34d399','#10b981'], Lightning:['#a78bfa','#7c3aed'], Physical:['#94a3b8','#64748b'],
  Quantum:['#818cf8','#6366f1'], Imaginary:['#fde68a','#ca8a04'], Elation:['#f472b6','#db2777'],
  Electric:['#facc15','#ca8a04'], Ether:['#c084fc','#9333ea'],
};
const RARITY = { 5:['#fcd66e','#f0b400'], 4:['#d4bbff','#b78bff'], 3:['#a8c8ff','#5b9eff'] };
const EVENT_TYPES = {
  main:['#f0b400','Event'], story:['#b78bff','Story'], combat:['#ef6b6b','Combat'],
  web:['#5b9eff','Web'], login:['#34d399','Login'], exploration:['#22d3ee','Explore'],
};
const evtType = t => EVENT_TYPES[t] || ['#8b949e','Event'];

// Rewards considered significant enough to surface prominently on the ending-soon card.
const SIG_RX = /polychrome|stellar jade|primogem|bangboo|light cone\b|(?<!\w)w-engine\b(?!\s*(material|energy|power|supply))|weapon skin|crown of insight|tracks of destiny|self-modeling resin|stella fortuna|namecard|tuning calibrator|master tape|special pass|hamster cage|interference key|speech bubble/i;
function sigRewards(str) {
  if (!str) return [];
  return str.replace(/^\+\s*/, '').split(/\s*·\s*/).filter(p => SIG_RX.test(p));
}

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
// Date-only strings (YYYY-MM-DD) in banners/events JSON are UTC calendar dates.
// Append game-specific maintenance-end time (UTC) confirmed from Game8 maintenance pages:
//   GI:  7-hour window → ends 05:00 UTC (midnight UTC-5)   confirmed Game8 GI maintenance
//   HSR: 5-hour window → ends 03:00 UTC (10 PM UTC-5)      confirmed Game8 HSR 4.3 maintenance
//   ZZZ: 5-hour window → ends 03:00 UTC (10 PM UTC-5)      confirmed Game8 ZZZ 2.8 maintenance
// Mid-version events end at daily reset (04:00 UTC-5 = 09:00 UTC); using maintenance-end
// time as a proxy is within ~4-6h and correct for all version-transition boundaries.
const SERVER_END = { gi: 'T05:00:00Z', hsr: 'T03:00:00Z', zzz: 'T03:00:00Z' };
const parseISO = (d, game) => {
  if (!d) return 0;
  if (/\dT|\dZ|:/.test(d)) return Date.parse(d) || 0;
  return Date.parse(d + (SERVER_END[game] || 'T03:00:00Z')) || 0;
};
const fmtDay = ms => { const d = new Date(ms); return MON[d.getUTCMonth()] + ' ' + d.getUTCDate(); };
const fmtDateLong = ms => { const d = new Date(ms); return MON[d.getUTCMonth()] + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear(); };

const elColor = e => (ELEMENT_COLORS[e] || ['#8b949e','#8b949e'])[1];
const elSoft  = e => (ELEMENT_COLORS[e] || ['#8b949e','#8b949e'])[0];
const NEW_DAYS = 70;
const SORTS = { newest:'Newest', oldest:'Oldest', rarity:'Rarity', az:'A–Z' };

const ERA_MAP = {
  gi:  { 1:'Mondstadt & Liyue', 2:'Inazuma', 3:'Sumeru', 4:'Fontaine', 5:'Natlan', 6:'Nod-Krai' },
  hsr: { 1:'Xianzhou Luofu', 2:'Penacony', 3:'Amphoreus', 4:'Planarcadia' },
  zzz: { 1:'New Eridu', 2:'Waifei Peninsula' },
};

// ── icon glyphs (16-view, stroke=currentColor) ──
const ICONS = {
  spark:'<svg viewBox="0 0 16 16"><path d="M8 1.6l1.7 4.1 4.4.3-3.4 2.8 1.1 4.3L8 11l-3.8 2.4 1.1-4.3-3.4-2.8 4.4-.3z"/></svg>',
  broadcast:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="2"/><path d="M4.6 4.6a4.8 4.8 0 000 6.8M11.4 4.6a4.8 4.8 0 010 6.8M2.6 2.6a7.6 7.6 0 000 10.8M13.4 2.6a7.6 7.6 0 010 10.8"/></svg>',
  wish:'<svg viewBox="0 0 16 16"><path d="M8 13.5S2 9.8 2 5.9A3 3 0 018 4a3 3 0 016 1.9c0 3.9-6 7.6-6 7.6z"/></svg>',
  clock:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/><path d="M8 4.6V8l2.4 1.6"/></svg>',
  calendar:'<svg viewBox="0 0 16 16"><rect x="2.5" y="3.2" width="11" height="10.3" rx="2"/><path d="M2.5 6.3h11M5.4 1.8v2.6M10.6 1.8v2.6"/></svg>',
  grid:'<svg viewBox="0 0 16 16"><rect x="2.4" y="2.4" width="4.6" height="4.6" rx="1.2"/><rect x="9" y="2.4" width="4.6" height="4.6" rx="1.2"/><rect x="2.4" y="9" width="4.6" height="4.6" rx="1.2"/><rect x="9" y="9" width="4.6" height="4.6" rx="1.2"/></svg>',
  dollar:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 2v12"/><path d="M11 5.5C11 4 9.7 3 8 3S5 4 5 5.5C5 7 6.3 7.5 8 8s3 1 3 2.5C11 12 9.7 13 8 13s-3-1-3-2.5"/></svg>',
};

// ── state ──
const S = {
  game: 'all', device: 'desktop', search: '', filterEl: null, sort: 'newest',
  selected: null, animate: true,
  data: {}, icons: {}, portraits: {}, maxDate: {}, banners: {}, events: {}, streams: {},
  tw: { layout: 'composed', font: 'schibsted', accent: 'room', motion: true },
};

const TW_KEY = 'archon:whatsnew:tweaks';
const FONTS = { schibsted: "'Schibsted Grotesk',ui-sans-serif,system-ui,sans-serif", bricolage: "'Bricolage Grotesque',ui-sans-serif,system-ui,sans-serif" };

const EVT_DONE_KEY = 'archon:evt-done';
const evtDoneSet = () => { try { return new Set(JSON.parse(localStorage.getItem(EVT_DONE_KEY) || '[]')); } catch { return new Set(); } };
const evtDoneKey = (game, name) => game + '|' + name;
function toggleEvtDone(game, name) {
  const s = evtDoneSet(), k = evtDoneKey(game, name);
  s.has(k) ? s.delete(k) : s.add(k);
  try { localStorage.setItem(EVT_DONE_KEY, JSON.stringify([...s])); } catch {}
  return s.has(k);
}
const CHK_OFF = '<svg viewBox="0 0 16 16" width="16" height="16"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
const CHK_ON  = '<svg viewBox="0 0 16 16" width="16" height="16"><circle cx="8" cy="8" r="6" fill="currentColor"/><path d="M5.2 8.2l1.9 1.9 3.7-3.7" fill="none" stroke="var(--bg)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';

// ── spending tracker ──
const SPD_KEY = 'archon:spending';
const SPD_CATS = { welkin: 'Welkin Moon', battlepass: 'Battle Pass', topup: 'Top-up', bundle: 'Bundle', other: 'Other' };
// Premium-currency name per game (all share the same USD top-up tiers).
const SPD_CUR = { gi: 'Genesis Crystals', hsr: 'Oneiric Shards', zzz: 'Monochrome' };
// Standard America-region USD top-up tiers (uniform across GI/HSR/ZZZ).
// repeat crystals = base + bonus; first-time = base × 2 (double-bonus until that tier is used).
const SPD_TOPUP = [
  { price: 0.99,  base: 60,   bonus: 0 },
  { price: 4.99,  base: 300,  bonus: 30 },
  { price: 14.99, base: 980,  bonus: 110 },
  { price: 29.99, base: 1980, bonus: 260 },
  { price: 49.99, base: 3280, bonus: 600 },
  { price: 99.99, base: 6480, bonus: 1600 },
];
// Fixed-price recurring presets (membership + battle pass) per game.
const SPD_PRESETS = {
  gi: [
    { id: 'welkin', cat: 'welkin',     label: 'Welkin Moon',        price: 4.99 },
    { id: 'bp',     cat: 'battlepass', label: 'Gnostic Hymn',       price: 9.99 },
    { id: 'bpd',    cat: 'battlepass', label: 'Gnostic Chorus',     price: 19.99 },
  ],
  hsr: [
    { id: 'welkin', cat: 'welkin',     label: 'Express Supply Pass', price: 4.99 },
    { id: 'bp',     cat: 'battlepass', label: 'Nameless Glory',      price: 9.99 },
    { id: 'bpd',    cat: 'battlepass', label: 'Nameless Medal',      price: 19.99 },
  ],
  zzz: [
    { id: 'welkin', cat: 'welkin',     label: 'Inter-Knot Membership', price: 4.99 },
    { id: 'bp',     cat: 'battlepass', label: 'New Eridu City Fund',   price: 9.99 },
    { id: 'bpd',    cat: 'battlepass', label: 'City Fund Deluxe',      price: 19.99 },
  ],
};
// Most recent server-side first-time-bonus reset per game (ISO date). When a reset
// passes, every tier's ×2 becomes available again; update these when HoYoverse resets.
// GI: v6.0 (2025-09-10) · HSR: anniversary (2026-04-22) · ZZZ: v2.0 (2025-06-06).
const SPD_RESETS = { gi: '2025-09-10', hsr: '2026-04-22', zzz: '2025-06-06' };
let spdGame = null; // selected game for the quick-add section
const fmtUSD = n => '$' + (n || 0).toFixed(2);
const fmtCr = n => (n || 0).toLocaleString('en-US');
const monthKeyToday = () => new Date().toISOString().slice(0, 7);
const monthLabel = mk => { const [y, m] = mk.split('-'); return MON[+m - 1] + ' ' + y; };
const fmtIsoDate = d => { const dt = new Date(d + 'T12:00:00Z'); return MON[dt.getUTCMonth()] + ' ' + dt.getUTCDate() + ', ' + dt.getUTCFullYear(); };
function loadSpending() { try { return JSON.parse(localStorage.getItem(SPD_KEY) || '[]'); } catch { return []; } }
function saveSpending(entries) { try { localStorage.setItem(SPD_KEY, JSON.stringify(entries)); } catch {} }
function addSpending(entry) {
  const all = loadSpending();
  all.push({ id: Date.now() + Math.floor(Math.random() * 1000), date: new Date().toISOString().slice(0, 10), ...entry });
  saveSpending(all);
  renderSpending();
}
// A top-up tier's double-bonus is available until that exact game+price tier has been
// logged once SINCE the game's most recent reset. Purchases before the reset no longer count.
function topupUsed(game, price) {
  const reset = SPD_RESETS[game] || '0000-00-00';
  return loadSpending().some(e => e.category === 'topup' && e.game === game
    && Math.abs((e.amount || 0) - price) < 0.001 && e.date >= reset);
}
function renderSpending() {
  const panel = document.getElementById('spending');
  const entries = loadSpending().sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
  const total = entries.reduce((s, e) => s + (e.amount || 0), 0);
  const byGame = Object.fromEntries(GAME_ORDER.map(g => [g, 0]));
  for (const e of entries) if (byGame[e.game] !== undefined) byGame[e.game] += e.amount || 0;
  if (!GAME_ORDER.includes(spdGame)) spdGame = GAME_ORDER.includes(S.game) ? S.game : 'gi';
  const qg = spdGame;

  // group log by month, newest first; current month always shown even if empty
  const groups = {};
  for (const e of entries) (groups[e.date.slice(0, 7)] ||= []).push(e);
  const curMonth = monthKeyToday();
  if (!groups[curMonth]) groups[curMonth] = [];
  const monthKeys = Object.keys(groups).sort().reverse();

  panel.innerHTML = `
    <div class="spd-hd" id="spd-drag"><b>Spending</b><button class="spd-x" id="spd-close">✕</button></div>
    <div class="spd-body">
      <div class="spd-totals">
        <div class="spd-grand">${fmtUSD(total)}</div>
        <div class="spd-bygame">
          ${GAME_ORDER.map(g => `<span class="spd-gtot">
            <span class="spd-gdot" style="background:${GAME_DOT[g]}"></span>
            ${g.toUpperCase()} <b>${fmtUSD(byGame[g])}</b>
          </span>`).join('')}
        </div>
      </div>

      <div class="spd-sec">Quick add</div>
      <div class="spd-gtabs">
        ${GAME_ORDER.map(g => `<button class="spd-gtab${g === qg ? ' on' : ''}" data-qgame="${g}">
          <span class="spd-gdot" style="background:${GAME_DOT[g]}"></span>${g.toUpperCase()}
        </button>`).join('')}
      </div>
      <div class="spd-presets">
        ${SPD_PRESETS[qg].map(p => `<button class="spd-pbtn" data-preset="${p.id}">
          <span class="spd-pname">${p.label}</span><span class="spd-pprice">${fmtUSD(p.price)}</span>
        </button>`).join('')}
      </div>
      <div class="spd-tup-lab">${SPD_CUR[qg]} top-up
        ${SPD_RESETS[qg] ? `<span class="spd-reset" title="First-time ×2 bonus last reset on this date. After a reset, every tier grants double again until repurchased.">×2 reset ${fmtIsoDate(SPD_RESETS[qg])}</span>` : ''}
      </div>
      <div class="spd-tup">
        ${SPD_TOPUP.map((t, i) => {
          const first = !topupUsed(qg, t.price);
          const cr = first ? t.base * 2 : t.base + t.bonus;
          return `<button class="spd-tbtn${first ? ' first' : ''}" data-tier="${i}" title="${fmtCr(cr)} ${SPD_CUR[qg]}${first ? ' (first-time ×2)' : ''}">
            <span class="spd-tprice">${fmtUSD(t.price)}</span>
            <span class="spd-tcr">${fmtCr(cr)}${first ? ' <b>×2</b>' : ''}</span>
          </button>`;
        }).join('')}
      </div>

      <details class="spd-custom">
        <summary>Custom entry</summary>
        <form class="spd-form" id="spd-form">
          <div class="spd-row2">
            <select class="spd-sel" id="spd-game">
              ${GAME_ORDER.map(g => `<option value="${g}"${g === qg ? ' selected' : ''}>${GAMES[g]}</option>`).join('')}
            </select>
            <select class="spd-sel" id="spd-cat">
              ${Object.entries(SPD_CATS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}
            </select>
          </div>
          <div class="spd-row2">
            <input class="spd-inp" id="spd-amt" type="number" min="0.01" step="0.01" placeholder="Amount (USD)" required>
            <input class="spd-inp" id="spd-note" type="text" placeholder="Note (optional)" maxlength="60">
          </div>
          <button class="spd-add" type="submit">Add entry</button>
        </form>
      </details>

      <div class="spd-months">
        ${monthKeys.map(mk => {
          const list = groups[mk];
          const mtot = list.reduce((s, e) => s + (e.amount || 0), 0);
          return `<div class="spd-month">
            <div class="spd-mhd"><span>${monthLabel(mk)}</span><b>${fmtUSD(mtot)}</b></div>
            ${list.length ? list.map(e => `<div class="spd-entry">
              <span class="spd-edate">${(+e.date.slice(8, 10))}</span>
              <span class="spd-edot" style="background:${GAME_DOT[e.game] || '#8b949e'}"></span>
              <span class="spd-emid">
                <span class="spd-ecat">${e.note ? esc(e.note) : (SPD_CATS[e.category] || e.category)}</span>
                ${e.crystals ? `<span class="spd-ecr">+${fmtCr(e.crystals)}${e.first ? ' ×2' : ''}</span>` : ''}
              </span>
              <span class="spd-eamt">${fmtUSD(e.amount)}</span>
              <button class="spd-del" data-id="${e.id}" aria-label="Delete entry">✕</button>
            </div>`).join('') : `<p class="spd-mempty">No purchases this month.</p>`}
          </div>`;
        }).join('')}
      </div>
    </div>`;

  panel.querySelector('#spd-close').addEventListener('click', () => panel.classList.remove('on'));
  panel.querySelectorAll('.spd-gtab').forEach(b => b.addEventListener('click', () => { spdGame = b.dataset.qgame; renderSpending(); }));
  panel.querySelectorAll('.spd-pbtn').forEach(b => b.addEventListener('click', () => {
    const p = SPD_PRESETS[qg].find(x => x.id === b.dataset.preset);
    if (p) addSpending({ game: qg, category: p.cat, amount: p.price, note: p.label });
  }));
  panel.querySelectorAll('.spd-tbtn').forEach(b => b.addEventListener('click', () => {
    const t = SPD_TOPUP[+b.dataset.tier];
    const first = !topupUsed(qg, t.price);
    const crystals = first ? t.base * 2 : t.base + t.bonus;
    addSpending({ game: qg, category: 'topup', amount: t.price, note: SPD_CUR[qg], crystals, first });
  }));
  panel.querySelector('#spd-form').addEventListener('submit', ev => {
    ev.preventDefault();
    const game = panel.querySelector('#spd-game').value;
    const category = panel.querySelector('#spd-cat').value;
    const amount = parseFloat(panel.querySelector('#spd-amt').value);
    const note = panel.querySelector('#spd-note').value.trim();
    if (!amount || amount <= 0) return;
    addSpending({ game, category, amount, note });
  });
  panel.querySelectorAll('.spd-del').forEach(btn => btn.addEventListener('click', () => {
    const id = +btn.dataset.id;
    saveSpending(loadSpending().filter(e => e.id !== id));
    renderSpending();
  }));
  makeDraggable(panel, panel.querySelector('#spd-drag'));
}

// ── boot ──
async function boot() {
  loadTweaks();
  const grab = (p) => fetch(p).then(r => r.json()).catch(() => ({}));
  const [icons, portraits, release, banners, events, streams, giB, hsrB, zzzB, itemIcons, discIcons] = await Promise.all([
    grab('icons.json'), grab('portraits.json'), grab('release_data.json'),
    grab('banners.json'), grab('events.json'), grab('livestreams.json'),
    grab('builds.json'), grab('hsr_builds.json'), grab('zzz_builds.json'),
    grab('item_icons.json'), grab('disc_icons.json'),
  ]);
  S.icons = icons; S.portraits = portraits; S.banners = banners; S.events = events; S.streams = streams;
  S.itemIcons = itemIcons || {}; S.discIcons = discIcons || {};
  const _raw = { gi: giB, hsr: hsrB, zzz: zzzB };
  S.builds = {};
  for (const g of GAME_ORDER) { const idx = {}; (Array.isArray(_raw[g]) ? _raw[g] : []).forEach(o => { if (o && o.name) idx[o.name] = o; }); S.builds[g] = idx; }
  for (const g of GAME_ORDER) {
    const rel = release[g] || {};
    const list = Object.keys(rel).map(name => ({
      name, ...rel[name], icon: (icons[g] || {})[name], splash: (portraits[g] || {})[name],
      t: Date.parse(rel[name].date || '') || 0,
    })).filter(c => c.date);
    S.data[g] = list;
    S.maxDate[g] = list.reduce((m, c) => Math.max(m, c.t), 0);
  }
  wireChrome();
  applyTweaks();
  _booted = true;
  setDevice();
  render('boot');
  window.addEventListener('resize', setDevice);
  setInterval(tick, 1000);
}
let _booted = false;
function setDevice() {
  const dev = window.innerWidth <= 640 ? 'mobile' : 'desktop';
  if (dev === S.device) return;
  S.device = dev;
  const f = document.getElementById('frame'); if (f) f.dataset.device = dev;
  if (_booted) render('resize');
}

const isNew = c => S.maxDate[S.game] && (S.maxDate[S.game] - c.t) <= NEW_DAYS * 864e5;
const charByName = name => (S.data[S.game] || []).find(c => c.name === name);
const charInGame = (g, name) => (S.data[g] || []).find(c => c.name === name);
const totalCount = () => (S.data[S.game] || []).length;

function roster() {
  let list = (S.data[S.game] || []).slice();
  if (S.search) { const q = S.search.toLowerCase(); list = list.filter(c => c.name.toLowerCase().includes(q)); }
  if (S.filterEl) list = list.filter(c => c.element === S.filterEl);
  const byDateDesc = (a, b) => b.t - a.t || a.name.localeCompare(b.name);
  if (S.sort === 'newest') list.sort(byDateDesc);
  else if (S.sort === 'oldest') list.sort((a, b) => a.t - b.t || a.name.localeCompare(b.name));
  else if (S.sort === 'rarity') list.sort((a, b) => (b.rarity || 0) - (a.rarity || 0) || byDateDesc(a, b));
  else if (S.sort === 'az') list.sort((a, b) => a.name.localeCompare(b.name));
  return list;
}
function eraOf(c) {
  const major = parseInt(c.version, 10);
  if (!major) return { key: 'other', label: 'Unknown era', tag: '', major: -1 };
  const label = (ERA_MAP[S.game] || {})[major] || ('Version ' + major);
  return { key: 'era' + major, label, tag: 'v' + major + '.x', major };
}
function byEra(list) {
  const map = new Map();
  for (const c of list) {
    const e = eraOf(c);
    if (!map.has(e.key)) map.set(e.key, { era: e, items: [] });
    map.get(e.key).items.push(c);
  }
  return [...map.values()];
}

// ════════════════════════════════════════════════════════════════  CHROME
function gameSwitch() {
  const allBtn = `<button class="gs-btn gs-all${S.game === 'all' ? ' on' : ''}" data-game="all" role="tab">
    <span class="gs-ab">All</span><span class="gs-full">All games</span>
  </button>`;
  return `<div class="gswitch" role="tablist">${allBtn}` + GAME_ORDER.map(g =>
    `<button class="gs-btn${g === S.game ? ' on' : ''}" data-game="${g}" role="tab">
      <span class="gs-dot" style="background:${GAME_DOT[g]};color:${GAME_DOT[g]}"></span>
      <span class="gs-ab">${g.toUpperCase()}</span><span class="gs-full">${GAMES[g]}</span>
    </button>`).join('') + `</div>`;
}
function topbar() {
  return `<header class="bar">
    <div class="bar-l">
      <div class="wordmark"><span class="wm-a">A</span><span class="wm-t">archon</span></div>
      ${gameSwitch()}
    </div>
    <div class="bar-r">
      <label class="search">
        <svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
        <input id="q" type="text" placeholder="Find a character…" value="${S.search.replace(/"/g,'&quot;')}" autocomplete="off" spellcheck="false">
        ${S.search ? '<button id="q-clear" aria-label="clear">✕</button>' : ''}
      </label>
      <button class="gear" id="open-spending" aria-label="Spending tracker">${ICONS.dollar}</button>
      <button class="gear" aria-label="Settings">
        <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="2.3"/><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8L3.4 3.4"/></svg>
      </button>
    </div>
  </header>`;
}
function sec(icon, title, meta, mod, right) {
  return `<div class="sec${mod ? ' ' + mod : ''}">
    <span class="sec-ico">${ICONS[icon] || ''}</span>
    <span class="sec-t">${title}</span>
    ${meta ? `<span class="sec-m">${meta}</span>` : ''}
    <span class="sec-line"></span>
    ${right ? `<span class="sec-right">${right}</span>` : ''}
  </div>`;
}

// ════════════════════════════════════════════════════════════════  RENDER FEED
let _ri = 0;
const reveal = () => `reveal" style="--i:${_ri++}`;
function render(reason) {
  S.animate = (reason === 'boot' || reason === 'game' || reason === 'tweak');
  document.body.dataset.game = S.game;
  document.getElementById('frame').dataset.device = S.device;
  document.querySelectorAll('#games-meta .gm').forEach(b => b.classList.toggle('on', b.dataset.game === S.game));
  document.querySelectorAll('#devices .dc').forEach(b => b.classList.toggle('on', b.dataset.device === S.device));
  const host = document.getElementById('screen');
  _ri = 0;
  host.innerHTML = `${topbar()}
    <div class="scroll${S.animate ? ' anim' : ''}" id="feed-scroll">
      <div class="feed">
        ${S.game === 'all'
          ? `<div class="all-cols">${allBannersSection()}${allEventsSection()}</div>`
          : livestreamSection() + heroSection() + dashboardSection() + eventSection() + rosterSection()
        }
      </div>
    </div>`;
  tick();
  wireScreen();
  wireEventPops();
}

// ── 1 · LIVESTREAM ─────────────────────────────────────────────
function livestreamSection() {
  const ls = (S.streams || {})[S.game];
  if (!ls || !ls.date || !ls.announced) return '';  // hide until officially announced
  const when = parseISO(ls.date);
  const now = NOW();
  if (when < now - 1.5 * 864e5) return '';           // hide once well past
  const aired = when <= now;
  const hl = (ls.highlights || []).slice(0, 4);
  const codes = aired ? (ls.codes || []) : [];
  const right = aired
    ? `<span class="ls-rl">Aired</span><span class="ls-when">${fmtDateLong(when)}</span>`
    : `<span class="ls-rl">Goes live in</span><span class="cd" data-deadline="${when}" data-cd="seg"></span><span class="ls-when">${fmtDateLong(when)}</span>`;
  return `<section class="block">
    ${sec('broadcast', aired ? 'Latest livestream' : 'Next livestream', GAMES[S.game], '', '')}
    <div class="ls ${aired ? 'aired ' : ''}${reveal()}">
      <div class="ls-badge">
        <span class="ls-ico">${ICONS.broadcast}</span>
      </div>
      <div class="ls-mid">
        <div class="ls-kicker">${aired ? 'Revealed · Special Program' : 'Special Program'}</div>
        <div class="ls-ver" style="margin-top:6px">Version ${ls.version}${ls.title ? ` <small>· ${ls.title}</small>` : ''}</div>
        ${hl.length ? `<div class="ls-hl">${hl.map(h => `<span class="ls-chip">${h}</span>`).join('')}</div>` : ''}
        ${codes.length ? `<div class="ls-codes">
          <span class="ls-codes-lab">Codes${ls.codes_note ? ` · ${ls.codes_note}` : ''}</span>
          <span class="ls-codes-row">${codes.map(c => `<button class="ls-code" data-code="${esc(c)}" title="Copy code">${esc(c)}</button>`).join('')}</span>
        </div>` : ''}
      </div>
      <div class="ls-right">${right}</div>
    </div>
  </section>`;
}

// ── 2 · JUST RELEASED HERO BAND ────────────────────────────────
function currentVersion() {
  const list = (S.data[S.game] || []).filter(c => c.t <= NOW());
  if (!list.length) return null;
  const newest = list.reduce((m, c) => c.t > m.t ? c : m, list[0]);
  return newest.version || null;
}
function heroCard(c) {
  const rc = RARITY[c.rarity] || RARITY[4];
  const bg = c.splash || c.icon;
  const sub = [c.weapon_type, c.element].filter(Boolean).join(' · ');
  return `<button class="fcard ${reveal()}" data-char="${c.name}" style="--ec:${accentFor(c)};--rc:${rc[1]}">
    <span class="fcard-art">${bg ? `<img loading="lazy" src="${bg}" alt="" referrerpolicy="no-referrer">` : `<span class="ph">${c.name[0]}</span>`}</span>
    <span class="fcard-grad"></span><span class="fcard-glow"></span>
    <span class="fcard-top">
      ${c.element ? `<span class="fcard-el" style="--ec:${elColor(c.element)}"><span class="eldot" style="background:${elColor(c.element)}"></span>${c.element}</span>` : '<span></span>'}
      ${isNew(c) ? '<span class="fcard-new">NEW</span>' : ''}
    </span>
    <span class="fcard-info">
      <span class="fcard-rarrow"><span class="fcard-rar" style="color:${rc[1]}">${c.rarity||4}★</span><span class="fcard-sub">${sub || ('v' + (c.version||'—'))}</span></span>
      <span class="fcard-name">${c.name}</span>
    </span>
  </button>`;
}
function heroSection() {
  const cv = currentVersion();
  const list = S.data[S.game] || [];
  const featured = cv ? list.filter(c => c.version === cv && c.t <= NOW())
    .sort((a,b) => b.t - a.t || (b.rarity||0) - (a.rarity||0) || a.name.localeCompare(b.name)) : [];
  if (!featured.length) return '';
  const cols = Math.min(featured.length, 3) || 1;
  const colDef = S.device === 'mobile' ? `repeat(${Math.min(cols,2)},1fr)` : `repeat(${cols},1fr)`;
  return `<section class="block">
    ${sec('spark', 'Just released', `Version ${cv} · ${featured.length} new`, '', '')}
    <div class="hero-wrap">
      <div class="hero" style="grid-template-columns:${colDef};">${featured.map(heroCard).join('')}</div>
    </div>
  </section>`;
}

// ── ALL-GAMES VIEW ─────────────────────────────────────────────
function allBannersSection() {
  const now = NOW();
  let hasAny = false;
  const sections = GAME_ORDER.map(g => {
    const all = (S.banners[g] || []).map(b => ({ ...b, s: parseISO(b.start, g), e: parseISO(b.end, g) })).filter(b => b.s && b.e);
    const active = all.filter(b => b.s <= now && now < b.e).sort((a, b) => a.phase - b.phase);
    if (!active.length) return '';
    hasAny = true;
    const deadline = Math.min(...active.map(b => b.e));
    const dot = GAME_DOT[g];
    return `<div class="all-bn-section" style="--gc:${dot}">
      <div class="all-bn-ghead">
        <span class="all-bn-gdot" style="background:${dot};box-shadow:0 0 6px ${dot}"></span>
        <span class="all-bn-gname">${GAMES[g]}</span>
        <span class="all-bn-close">closes <span class="cd" data-deadline="${deadline}" data-cd="short"></span></span>
      </div>
      <div class="bn-list">${active.map(b => bannerCard(b, g)).join('')}</div>
    </div>`;
  }).join('');
  if (!hasAny) return '';
  return `<section class="block">
    <div class="panel live ${reveal()}">
      <div class="panel-h">
        <span class="panel-ico">${ICONS.wish}</span>
        <span class="panel-t">On the banner now</span>
        <span class="panel-m"><span class="pulse"></span>all games</span>
      </div>
      ${sections}
    </div>
  </section>`;
}
function allEventsSection() {
  const now = NOW();
  const all = [];
  for (const g of GAME_ORDER) {
    const raw = (S.events[g] || []).map(e => ({ ...e, s: parseISO(e.start, g), e2: parseISO(e.end, g), game: g })).filter(e => e.s && e.e2);
    const seen = new Set();
    for (const e of raw) {
      const k = e.start + '|' + e.end + '|' + e.name.toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!seen.has(k)) { seen.add(k); all.push(e); }
    }
  }
  const live = all.filter(e => e.s <= now && e.e2 >= now).sort((a, b) => a.e2 - b.e2);
  if (!live.length) return '';
  const done = evtDoneSet();
  const rows = live.map(e => {
    const g = e.game, gdot = GAME_DOT[g];
    const col = evtType(e.type)[0];
    const rem = e.e2 - now, urgent = rem <= 60 * 36e5;
    const sig = sigRewards(e.rewards);
    const isDone = done.has(evtDoneKey(g, e.name));
    return `<div class="es-row${urgent ? ' urgent' : ''}${isDone ? ' done' : ''}" data-name="${esc(e.name)}" data-game="${g}" data-type="${e.type}" data-s="${e.s}" data-e="${e.e2}" data-rew="${esc(e.rewards||'')}" data-tagline="${esc(e.tagline||'')}">
      <span class="es-dot" style="background:${gdot};color:${gdot}"></span>
      <span class="es-mid">
        <span class="es-name">${e.name}</span>
        ${sig.length ? `<span class="es-sig">${sig.map(s => `<span class="es-sig-chip">${esc(s)}</span>`).join('')}</span>` : ''}
        <span class="es-type" style="color:${urgent ? 'var(--amber)' : col}"><span class="es-gab" style="color:${gdot}">${g.toUpperCase()}</span>${urgent ? ' · Ends soon' : ' · ' + evtType(e.type)[1]}</span>
      </span>
      <span class="es-right"><span class="es-cd${urgent ? ' warn' : ''}" data-deadline="${e.e2}" data-cd="short"></span><span class="es-rl">left</span></span>
      <button class="es-chk" aria-label="${isDone ? 'Mark undone' : 'Mark done'}">${isDone ? CHK_ON : CHK_OFF}</button>
    </div>`;
  }).join('');
  return `<section class="block">
    <div class="panel warn ${reveal()}">
      <div class="panel-h">
        <span class="panel-ico">${ICONS.clock}</span>
        <span class="panel-t">Active events</span>
        <span class="panel-m">all games · soonest ending</span>
      </div>
      <div class="es-list">${rows}</div>
    </div>
  </section>`;
}

// ── 3 · DASHBOARD (banner + ending soon) ───────────────────────
function bannerData() {
  const now = NOW();
  const all = (S.banners[S.game] || []).map(b => ({ ...b, s: parseISO(b.start, S.game), e: parseISO(b.end, S.game) })).filter(b => b.s && b.e);
  const active = all.filter(b => b.s <= now && now < b.e).sort((a,b) => a.phase - b.phase);
  const future = all.filter(b => b.s > now).sort((a,b) => a.s - b.s);
  const nextStart = future.length ? future[0].s : null;
  const next = nextStart != null ? future.filter(b => b.s === nextStart) : [];
  return { active, next };
}
function bannerCard(b, game) {
  const g = game || S.game;
  const c = charInGame(g, b.character);
  const rarity = c?.rarity || 5;
  const rc = RARITY[rarity] || RARITY[5];
  const el = c?.element, ec = accentFor(c) || elColor(el);
  const img = c?.icon || c?.splash;
  const click = !!c, tag = click ? 'button' : 'div';
  return `<${tag} class="bn-card${click ? '' : ' static'}" ${click ? `data-char="${b.character}" data-char-game="${g}"` : ''} style="--ec:${ec};--rc:${rc[1]}">
    <span class="bn-thumb">${img ? `<img src="${img}" loading="lazy" referrerpolicy="no-referrer">` : `<span class="ph">${b.character[0]}</span>`}</span>
    <span class="bn-body">
      <span class="bn-top"><span class="bn-name">${b.character}</span><span class="bn-rar" style="color:${rc[1]}">${rarity}★</span></span>
      <span class="bn-tags">
        ${el ? `<span class="bn-el" style="--ec:${ec}"><span class="eldot" style="background:${ec}"></span>${el}</span>` : ''}
        <span class="bn-pill">Phase ${b.phase}</span>
        <span class="bn-pill ${b.rerun ? 'bn-rerun' : 'bn-debut'}">${b.rerun ? 'Rerun' : 'Debut'}</span>
      </span>
      ${b.verdict ? `<span class="bn-verdict">${b.verdict}</span>` : ''}
    </span>
  </${tag}>`;
}
function bannerPanel() {
  const { active, next } = bannerData();
  if (!active.length && !next.length) return '';
  const deadline = active.length ? Math.min(...active.map(b => b.e)) : null;
  const patch = (active[0] || next[0] || {}).patch;
  return `<div class="panel live ${reveal()}">
    <div class="panel-h">
      <span class="panel-ico">${ICONS.wish}</span>
      <span class="panel-t">On the banner now</span>
      <span class="panel-m"><span class="pulse"></span>${patch ? 'v' + patch : 'live'}</span>
    </div>
    ${active.length ? `
      <div class="bn-cdwrap"><span class="cdl">Wishes close in</span><span class="cd" data-deadline="${deadline}" data-cd="seg"></span></div>
      <div class="bn-list">${active.map(bannerCard).join('')}</div>` : ''}
    ${next.length ? `
      <div class="bn-next">
        <span class="bn-next-l">Up next</span>
        <span class="bn-next-n">${next.map(b => b.character).join(' · ')}</span>
        <span class="bn-next-d">${fmtDay(next[0].s)}<span class="bn-next-cd" data-deadline="${next[0].s}" data-cd="inline"></span></span>
      </div>` : ''}
  </div>`;
}
// events list — used both for the "ending soon" panel and to feed the gantt
function eventData() {
  const now = NOW();
  const raw = (S.events[S.game] || []).map(e => ({ ...e, s: parseISO(e.start, S.game), e2: parseISO(e.end, S.game) })).filter(e => e.s && e.e2);
  const seen = new Set(), list = [];
  for (const e of raw) {
    const k = e.start + '|' + e.end + '|' + e.name.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (seen.has(k)) continue; seen.add(k); list.push(e);
  }
  return list.filter(e => e.e2 >= now).sort((a,b) => a.s - b.s || a.e2 - b.e2);
}
function endingSoonPanel() {
  const now = NOW();
  const live = eventData().filter(e => e.s <= now).sort((a,b) => a.e2 - b.e2).slice(0, 5);
  if (!live.length) return '';
  const rows = live.map(e => {
    const col = evtType(e.type)[0];
    const rem = e.e2 - now;
    const urgent = rem <= 60 * 36e5;                 // within ~2.5 days
    const sig = sigRewards(e.rewards);
    const done = evtDoneSet().has(evtDoneKey(S.game, e.name));
    return `<div class="es-row${urgent ? ' urgent' : ''}${done ? ' done' : ''}" data-name="${esc(e.name)}" data-type="${e.type}" data-s="${e.s}" data-e="${e.e2}" data-rew="${esc(e.rewards||'')}" data-tagline="${esc(e.tagline||'')}">
      <span class="es-dot" style="background:${col};color:${col}"></span>
      <span class="es-mid">
        <span class="es-name">${e.name}</span>
        ${sig.length ? `<span class="es-sig">${sig.map(s => `<span class="es-sig-chip">${esc(s)}</span>`).join('')}</span>` : ''}
        <span class="es-type" style="color:${urgent ? 'var(--amber)' : col}">${urgent ? 'Ends soon · ' : ''}${evtType(e.type)[1]}</span>
      </span>
      <span class="es-right"><span class="es-cd${urgent ? ' warn' : ''}" data-deadline="${e.e2}" data-cd="short"></span><span class="es-rl">left</span></span>
      <button class="es-chk" aria-label="${done ? 'Mark undone' : 'Mark done'}">${done ? CHK_ON : CHK_OFF}</button>
    </div>`;
  }).join('');
  return `<div class="panel warn ${reveal()}">
    <div class="panel-h">
      <span class="panel-ico">${ICONS.clock}</span>
      <span class="panel-t">Active events</span>
      <span class="panel-m">soonest ending</span>
    </div>
    <div class="es-list">${rows}</div>
  </div>`;
}
function dashboardSection() {
  const bp = bannerPanel(), ep = endingSoonPanel();
  if (!bp && !ep) return '';
  const cols = (bp && ep && S.tw.layout === 'composed') ? ' cols' : '';
  return `<section class="block"><div class="dash${cols}">${bp}${ep}</div></section>`;
}

// ── 4 · EVENT TIMELINE (gantt) ─────────────────────────────────
function eventSection() {
  const rel = eventData();
  if (!rel.length) return '';
  const now = NOW();
  const winS = now - 3 * 864e5, winE = now + 38 * 864e5, span = winE - winS;
  const pct = ms => Math.max(0, Math.min(100, (ms - winS) / span * 100));
  const ticks = [];
  for (let d = 0; d <= 41; d += 10) { const ms = winS + d * 864e5; ticks.push(`<span class="evt-tick" style="left:${(ms - winS) / span * 100}%">${fmtDay(ms)}</span>`); }
  const rows = rel.slice(0, 9).map(e => {
    const col = evtType(e.type)[0];
    let L = pct(e.s), R = pct(e.e2);
    if (R - L < 2.5) R = Math.min(100, L + 2.5);
    const liveNow = e.s <= now, remMs = e.e2 - now;
    const soon = liveNow && remMs <= 48 * 36e5;
    let barlab;
    if (!liveNow) barlab = 'in ' + Math.max(1, Math.round((e.s - now) / 864e5)) + 'd';
    else if (soon) barlab = Math.max(1, Math.round(remMs / 36e5)) + 'h left';
    else barlab = Math.round(remMs / 864e5) + 'd left';
    return `<div class="evt-row${soon ? ' soon' : ''}" data-name="${esc(e.name)}" data-type="${e.type}" data-s="${e.s}" data-e="${e.e2}" data-rew="${esc(e.rewards || '')}">
      <span class="evt-label"><span class="evt-tdot" style="background:${col}"></span><span class="evt-name">${e.name}</span>${soon ? `<span class="evt-warn">${WARN_SVG}Ends soon</span>` : `<span class="evt-type" style="color:${col}">${evtType(e.type)[1]}</span>`}</span>
      <span class="evt-track">
        <span class="evt-bar${e.s < winS ? ' clipL' : ''}${e.e2 > winE ? ' clipR' : ''}${soon ? ' soon' : ''}" style="left:${L}%;width:${R - L}%;--c:${soon ? 'var(--amber)' : col}">
          <span class="evt-barlab">${barlab}</span>
        </span>
      </span>
    </div>`;
  }).join('');
  const nowPct = (now - winS) / span * 100;
  return `<section class="block">
    ${sec('calendar', 'Event schedule', GAMES[S.game] + ' · next 6 weeks', '', '')}
    <div class="evt-wrap">
      <div class="evt-tl ${reveal()}" data-wins="${winS}" data-wine="${winE}">
        <div class="evt-axis"><span class="evt-tickrow">${ticks.join('')}</span></div>
        <div class="evt-layer"><span class="evt-now" data-nowline style="left:${nowPct}%"><span class="evt-now-lab">Now</span></span></div>
        <div class="evt-rows">${rows}</div>
      </div>
    </div>
  </section>`;
}

// ── 5 · ROSTER (all chars by region) ───────────────────────────
function controls() {
  const order = (ELEMENT_ORDERS[S.game] || []).filter(e => (S.data[S.game] || []).some(c => c.element === e));
  return `<div class="controls">
    <div class="sortrow">
      <span class="ctl-lab">Sort</span>
      <div class="sortseg">${Object.keys(SORTS).map(k =>
        `<button class="sortbtn${S.sort === k ? ' on' : ''}" data-sort="${k}">${SORTS[k]}</button>`).join('')}</div>
    </div>
    ${order.length > 1 ? `<div class="elrow">
      <button class="elchip${S.filterEl === null ? ' on' : ''}" data-el="">All <span class="elc-n">${totalCount()}</span></button>
      ${order.map(e => `<button class="elchip${S.filterEl === e ? ' on' : ''}" data-el="${e}" style="--ec:${elColor(e)};--ecs:${elSoft(e)}">
        <span class="eldot" style="background:${elColor(e)}"></span>${e}</button>`).join('')}
    </div>` : ''}
  </div>`;
}
function tile(c) {
  const rc = RARITY[c.rarity] || RARITY[4];
  const img = c.icon ? `<img loading="lazy" src="${c.icon}" alt="" referrerpolicy="no-referrer">` : `<span class="ph">${c.name[0]}</span>`;
  return `<button class="tile r${c.rarity||4}" data-char="${c.name}" style="--rc:${rc[1]};--rcs:${rc[0]};--ec:${accentFor(c)}">
    <span class="tile-art">${img}
      ${c.element ? `<span class="tile-el" style="background:${elColor(c.element)}"></span>` : ''}
      ${isNew(c) ? '<span class="tile-new">NEW</span>' : ''}
    </span>
    <span class="tile-name">${c.name}</span>
    <span class="tile-meta"><span class="tile-ver">v${c.version||'—'}</span><span class="tile-rar" style="color:${rc[1]}">${c.rarity||4}★</span></span>
  </button>`;
}
function rosterSection() {
  const list = roster();
  const head = sec('grid', 'All characters', `by region · ${list.length}`, 'muted', '');
  if (!list.length) return `<section class="block">${head}${controls()}${emptyState()}</section>`;
  const sorted = S.sort === 'oldest' ? list : list.slice().sort((a,b) => b.t - a.t || a.name.localeCompare(b.name));
  const eras = byEra(sorted);
  return `<section class="block">
    ${head}
    ${controls()}
    ${eras.map(({ era, items }) => `
      <section class="rsec">
        <div class="rsec-h">
          <span class="rsec-y">${era.label}</span>
          ${era.tag ? `<span class="rsec-tag">${era.tag}</span>` : ''}
          <span class="rsec-line"></span><span class="rsec-n">${items.length}</span>
        </div>
        <div class="grid">${items.map(tile).join('')}</div>
      </section>`).join('')}
  </section>`;
}
function emptyState() {
  return `<div class="empty">No characters match <b>${S.search || S.filterEl || ''}</b>.</div>`;
}

// ════════════════════════════════════════════════════════════════  COUNTDOWN + POPUP
const WARN_SVG = '<svg viewBox="0 0 16 16" width="11" height="11"><path d="M8 2L1.5 13.5h13z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.2v3.3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11.5" r=".55" fill="currentColor"/></svg>';
function fmtSeg(ms) {
  const d = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60, s = Math.floor(ms / 1e3) % 60;
  return [['d', d], ['h', h], ['m', m], ['s', s]];
}
function fmtInline(ms) {
  const d = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60;
  return d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`;
}
function fmtShort(ms) {
  const d = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60;
  return d > 0 ? `${d}d ${h}h` : (h > 0 ? `${h}h ${m}m` : `${m}m`);
}
function fmtFull(ms) {
  const d = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60, s = Math.floor(ms / 1e3) % 60;
  return (d ? d + 'd ' : '') + h + 'h ' + String(m).padStart(2, '0') + 'm ' + String(s).padStart(2, '0') + 's';
}
let _lastSec = -1;
// update a text timer in place; fade it gently only when its value actually changes
function setTimerText(el, txt) {
  if (el.textContent === txt) return;
  el.textContent = txt;
  if (S.tw.motion) { el.classList.remove('cd-fade'); void el.offsetWidth; el.classList.add('cd-fade'); }
}
function tick() {
  const nowSec = Math.floor(NOW() / 1000);
  const flip = nowSec !== _lastSec; _lastSec = nowSec;
  document.querySelectorAll('[data-deadline]').forEach(el => {
    const ms = +el.dataset.deadline - NOW();
    const mode = el.dataset.cd;
    if (mode === 'seg') {
      if (ms <= 0) {
        if (el.dataset.live !== '1') { el.innerHTML = '<span class="cd-end">Live now</span>'; el.dataset.live = '1'; }
        return;
      }
      const segs = fmtSeg(ms);
      let bs = el.querySelectorAll('.cd-seg > b');
      // (re)build structure only when the segment count changes or coming back from "Live now"
      if (el.dataset.live === '1' || bs.length !== segs.length) {
        el.dataset.live = '0';
        el.innerHTML = segs.map(([u, v]) => `<span class="cd-seg"><b>${String(v).padStart(2, '0')}</b><i>${u}</i></span>`).join('<span class="cd-colon">:</span>');
        bs = el.querySelectorAll('.cd-seg > b');
      } else {
        // update digits in place; animate only the ones that actually changed
        segs.forEach(([, v], i) => {
          const b = bs[i]; if (!b) return;
          const nv = String(v).padStart(2, '0');
          if (b.textContent !== nv) {
            b.textContent = nv;
            if (S.tw.motion) { b.classList.remove('dchg'); void b.offsetWidth; b.classList.add('dchg'); }
          }
        });
      }
    } else if (mode === 'full') {
      setTimerText(el, ms <= 0 ? 'Ended' : fmtFull(ms));
    } else if (mode === 'short') {
      setTimerText(el, ms <= 0 ? 'Ended' : fmtShort(ms));
    } else {
      setTimerText(el, ms <= 0 ? '' : ' · in ' + fmtInline(ms));
    }
  });
  document.querySelectorAll('[data-nowline]').forEach(el => {
    const tl = el.closest('.evt-tl'); if (!tl) return;
    const winS = +tl.dataset.wins, winE = +tl.dataset.wine;
    el.style.left = Math.max(0, Math.min(100, (NOW() - winS) / (winE - winS) * 100)) + '%';
  });
}
function wireEventPops() {
  const host = document.getElementById('screen');
  // gantt bars — hover as before
  host.querySelectorAll('.evt-row').forEach(row => {
    row.addEventListener('mouseenter', () => { showEvtPop(row); positionEvtPop(row); });
    row.addEventListener('mouseleave', hideEvtPop);
  });
  // event list rows — click to open, click same row again to close
  host.querySelectorAll('.es-row').forEach(row => {
    row.addEventListener('click', ev => {
      if (ev.target.closest('.es-chk')) return;
      const pop = evtPopEl();
      if (pop.dataset.src === row.dataset.name + '|' + row.dataset.s && pop.classList.contains('on')) {
        hideEvtPop(); return;
      }
      showEvtPop(row); positionEvtPop(row);
    });
  });
  // click outside any row or popup to dismiss
  host.addEventListener('click', ev => {
    if (!ev.target.closest('.es-row') && !ev.target.closest('#evt-pop')) hideEvtPop();
  });
}
function evtPopEl() {
  const host = document.getElementById('screen');
  let pop = host.querySelector('#evt-pop');
  if (!pop) { pop = document.createElement('div'); pop.id = 'evt-pop'; pop.className = 'evt-pop'; host.appendChild(pop); }
  return pop;
}
const fmtLocal = ms => new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
function showEvtPop(row) {
  const pop = evtPopEl();
  const s = +row.dataset.s, e = +row.dataset.e, now = NOW();
  const type = row.dataset.type, col = evtType(type)[0], tlabel = evtType(type)[1];
  const future = s > now;
  const soon = !future && (e - now) <= 48 * 36e5;
  const dl = future ? s : e;
  const total = Math.max(1, Math.round((e - s) / 864e5));
  pop.dataset.src = row.dataset.name + '|' + row.dataset.s;
  pop.innerHTML = `
    <div class="evt-pop-h"><span class="evt-pop-dot" style="background:${col}"></span><span class="evt-pop-type" style="color:${col}">${tlabel}</span>${soon ? `<span class="evt-pop-warn">${WARN_SVG}Ends within 48h</span>` : ''}<button class="evt-pop-close" aria-label="Close">✕</button></div>
    <div class="evt-pop-name">${row.dataset.name}</div>
    ${row.dataset.tagline ? `<div class="evt-pop-tagline">${row.dataset.tagline}</div>` : ''}
    <div class="evt-pop-dates"><span class="evt-pop-rng">${fmtDay(s)} → ${fmtDay(e)}</span><span class="evt-pop-len">${total}d run</span></div>
    <div class="evt-pop-cdrow"><span class="evt-pop-cdl">${future ? 'Starts in' : 'Time remaining'}</span><span class="evt-pop-cd${soon ? ' warn' : ''}" data-deadline="${dl}" data-cd="full"></span></div>
    <div class="evt-pop-local">Ends ${fmtLocal(e)}</div>
    ${row.dataset.rew ? `<div class="evt-pop-rew">${row.dataset.rew}</div>` : ''}`;
  pop.querySelector('.evt-pop-close').addEventListener('click', ev => { ev.stopPropagation(); hideEvtPop(); });
  tick();
}
function positionEvtPop(row) {
  const pop = document.getElementById('evt-pop');
  if (!pop) return;
  const r = row.getBoundingClientRect();
  const pw = pop.offsetWidth || 260, ph = pop.offsetHeight || 200;
  const pad = 10;
  let x, y;
  if (S.device === 'mobile') {
    x = Math.max(pad, Math.min(window.innerWidth - pw - pad, r.left + r.width / 2 - pw / 2));
    y = r.bottom + 8;
    if (y + ph > window.innerHeight - pad) y = r.top - ph - 8;
  } else {
    x = r.right + 12;
    if (x + pw + pad > window.innerWidth) x = r.left - pw - 12;
    y = r.top;
    if (y + ph + pad > window.innerHeight) y = window.innerHeight - ph - pad;
  }
  pop.style.left = Math.max(pad, x) + 'px';
  pop.style.top = Math.max(pad, y) + 'px';
  pop.classList.add('on');
}
function hideEvtPop() {
  const pop = document.getElementById('evt-pop');
  if (pop) pop.classList.remove('on');
}

// ════════════════════════════════════════════════════════════════  CHARACTER TAKEOVER (data-driven Nightdesk sheet — sheet.js)
function openChar(name, tileEl, game) {
  const g = game || S.game;
  const c = (S.data[g] || []).find(x => x.name === name);
  if (!c) return;
  if (g !== S.game) { S._prevGame = S.game; S.game = g; }
  S.selected = c;
  const tk = document.getElementById('takeover');
  tk.className = 'mode-full zoom';
  tk.innerHTML = buildSheetHTML(c);
  tk.classList.add('on');
  const art = tileEl && tileEl.querySelector('.tile-art, .fcard-art, .bn-thumb');
  const dRect = tk.getBoundingClientRect();
  if (art) {
    const r0 = art.getBoundingClientRect();
    const ox = (r0.left + r0.width / 2 - dRect.left).toFixed(1);
    const oy = (r0.top + r0.height / 2 - dRect.top).toFixed(1);
    tk.style.transformOrigin = `${ox}px ${oy}px`;
  } else { tk.style.transformOrigin = '50% 42%'; }
  tk.querySelectorAll('[data-back]').forEach(b => b.addEventListener('click', closeChar));
  if (typeof wireSheet === 'function') wireSheet(tk, c);
  void tk.offsetWidth;
  requestAnimationFrame(() => tk.classList.add('in'));
  setTimeout(() => tk.classList.add('in'), 60);
}
function closeChar() {
  const tk = document.getElementById('takeover');
  if (!tk.classList.contains('on')) return;
  if (tk._pop) { tk._pop.remove(); tk._pop = null; }
  tk.classList.remove('in');
  setTimeout(() => {
    tk.classList.remove('on', 'zoom', 'mode-hero', 'mode-full');
    tk.innerHTML = '';
    tk.style.transformOrigin = '';
    tk._r0 = null; S.selected = null;
    if (S._prevGame) { S.game = S._prevGame; S._prevGame = null; }
  }, 420);
}

// ════════════════════════════════════════════════════════════════  WIRING
function wireScreen() {
  const host = document.getElementById('screen');
  host.querySelectorAll('.gs-btn[data-game]').forEach(b => b.addEventListener('click', () => { S.game = b.dataset.game; S.filterEl = null; S.search = ''; render('game'); }));
  const q = host.querySelector('#q');
  if (q) q.addEventListener('input', () => {
    S.search = q.value; const start = q.selectionStart; render('search');
    const q2 = document.getElementById('q'); if (q2) { q2.focus(); q2.setSelectionRange(start, start); }
  });
  host.querySelector('#q-clear')?.addEventListener('click', () => { S.search = ''; render('search'); document.getElementById('q')?.focus(); });
  host.querySelector('#open-spending')?.addEventListener('click', () => {
    const panel = document.getElementById('spending');
    if (panel.classList.contains('on')) { panel.classList.remove('on'); return; }
    renderSpending();
    panel.classList.add('on');
  });
  host.querySelectorAll('.ls-code').forEach(b => b.addEventListener('click', () => {
    const code = b.dataset.code;
    navigator.clipboard?.writeText(code).catch(() => {});
    const prev = b.textContent;
    b.classList.add('copied'); b.textContent = 'Copied';
    setTimeout(() => { b.classList.remove('copied'); b.textContent = prev; }, 1100);
  }));
  host.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => { S.sort = b.dataset.sort; render('sort'); }));
  host.querySelectorAll('[data-el]').forEach(b => b.addEventListener('click', () => { S.filterEl = b.dataset.el || null; render('filter'); }));
  host.querySelectorAll('[data-char]').forEach(b => b.addEventListener('click', () => openChar(b.dataset.char, b, b.dataset.charGame)));
  host.querySelectorAll('.es-chk').forEach(btn => btn.addEventListener('click', ev => {
    ev.stopPropagation();
    const row = btn.closest('.es-row');
    const isDone = toggleEvtDone(row.dataset.game || S.game, row.dataset.name);
    row.classList.toggle('done', isDone);
    btn.innerHTML = isDone ? CHK_ON : CHK_OFF;
    btn.setAttribute('aria-label', isDone ? 'Mark undone' : 'Mark done');
  }));
}
function wireChrome() {
  document.querySelectorAll('#games-meta .gm').forEach(b => b.addEventListener('click', () => { S.game = b.dataset.game; S.filterEl = null; S.search = ''; render('game'); }));
  document.querySelectorAll('#devices .dc').forEach(b => b.addEventListener('click', () => { S.device = b.dataset.device; render('tweak'); }));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.getElementById('spending')?.classList.remove('on');
      hideEvtPop();
      closeChar();
    }
  });
}

// ════════════════════════════════════════════════════════════════  TWEAKS (host protocol + vanilla panel)
function loadTweaks() {
  try { const v = JSON.parse(localStorage.getItem(TW_KEY) || '{}'); Object.assign(S.tw, v); } catch (e) {}
  document.body.classList.toggle('layout-stacked', S.tw.layout === 'stacked');
  document.body.classList.toggle('layout-composed', S.tw.layout !== 'stacked');
}
function saveTweaks() {
  try { localStorage.setItem(TW_KEY, JSON.stringify(S.tw)); } catch (e) {}
  window.parent.postMessage({ type: '__edit_mode_set_keys', edits: S.tw }, '*');
}
function applyTweaks() {
  document.documentElement.style.setProperty('--fd', FONTS[S.tw.font] || FONTS.schibsted);
  document.body.classList.toggle('layout-stacked', S.tw.layout === 'stacked');
  document.body.classList.toggle('layout-composed', S.tw.layout !== 'stacked');
  // accent override (room = use per-game default; otherwise force a hue)
  const acc = S.tw.accent;
  const map = { blue:['#5b9eff','#3b82f6'], violet:['#a78bfa','#7c3aed'], amber:['#f0a042','#e07a18'], mint:['#34d3a6','#10b981'] };
  if (acc !== 'room' && map[acc]) {
    document.documentElement.style.setProperty('--accent', map[acc][0]);
    document.documentElement.style.setProperty('--accent2', map[acc][1]);
    document.documentElement.style.setProperty('--accent-soft', map[acc][0] + '26');
    document.documentElement.style.setProperty('--accent-line', map[acc][0] + '66');
  } else {
    document.documentElement.style.removeProperty('--accent');
    document.documentElement.style.removeProperty('--accent2');
    document.documentElement.style.removeProperty('--accent-soft');
    document.documentElement.style.removeProperty('--accent-line');
  }
}
function renderTweaks() {
  const radio = (key, opts) => `<div class="twk-radio" data-twk="${key}">${opts.map(o =>
    `<button data-v="${o}" class="${S.tw[key] === o ? 'on' : ''}">${o}</button>`).join('')}</div>`;
  const accents = [['room','linear-gradient(135deg,var(--accent),var(--accent2))'],['blue','#5b9eff'],['violet','#a78bfa'],['amber','#f0a042'],['mint','#34d3a6']];
  const panel = document.getElementById('tweaks');
  panel.innerHTML = `
    <div class="twk-hd" id="twk-drag"><b>Tweaks</b><button class="twk-x" id="twk-close">✕</button></div>
    <div class="twk-body">
      <div class="twk-sec">Layout</div>
      <div class="twk-row"><span class="twk-lbl">Dashboard arrangement</span>${radio('layout', ['composed','stacked'])}</div>
      <div class="twk-sec">Type</div>
      <div class="twk-row"><span class="twk-lbl">Display typeface</span>${radio('font', ['schibsted','bricolage'])}</div>
      <div class="twk-sec">Color</div>
      <div class="twk-row"><span class="twk-lbl">Accent</span>
        <div class="twk-swatches" data-twk="accent">${accents.map(([v, bg]) =>
          `<span class="twk-sw ${S.tw.accent === v ? 'on' : ''}" data-v="${v}" style="background:${bg}" title="${v}"></span>`).join('')}</div>
      </div>
      <div class="twk-sec">Motion</div>
      <div class="twk-row twk-toggle"><span class="twk-lbl">Live animations</span>
        <button class="twk-sw-btn ${S.tw.motion ? 'on' : ''}" id="twk-motion" role="switch" aria-checked="${S.tw.motion}"></button>
      </div>
    </div>`;
  panel.querySelectorAll('.twk-radio').forEach(g => g.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    S.tw[g.dataset.twk] = b.dataset.v; commitTweak();
  })));
  panel.querySelector('[data-twk="accent"]').querySelectorAll('.twk-sw').forEach(sw => sw.addEventListener('click', () => {
    S.tw.accent = sw.dataset.v; commitTweak();
  }));
  panel.querySelector('#twk-motion').addEventListener('click', () => { S.tw.motion = !S.tw.motion; commitTweak(); });
  panel.querySelector('#twk-close').addEventListener('click', () => {
    panel.classList.remove('on'); window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*');
  });
  makeDraggable(panel, panel.querySelector('#twk-drag'));
}
function commitTweak() {
  saveTweaks(); applyTweaks(); renderTweaks(); render('tweak');
}
function makeDraggable(panel, handle) {
  let sx, sy, ox, oy, drag = false;
  handle.addEventListener('mousedown', e => {
    if (e.target.closest('.twk-x')) return;
    drag = true; sx = e.clientX; sy = e.clientY;
    const r = panel.getBoundingClientRect(); ox = r.left; oy = r.top;
    panel.style.right = 'auto'; panel.style.bottom = 'auto'; panel.style.left = ox + 'px'; panel.style.top = oy + 'px';
    e.preventDefault();
  });
  window.addEventListener('mousemove', e => { if (!drag) return; panel.style.left = (ox + e.clientX - sx) + 'px'; panel.style.top = (oy + e.clientY - sy) + 'px'; });
  window.addEventListener('mouseup', () => drag = false);
}
// host protocol
window.addEventListener('message', e => {
  const t = e?.data?.type;
  if (t === '__activate_edit_mode') { renderTweaks(); document.getElementById('tweaks').classList.add('on'); }
  else if (t === '__deactivate_edit_mode') document.getElementById('tweaks').classList.remove('on');
});
window.parent.postMessage({ type: '__edit_mode_available' }, '*');

function esc(s) { return String(s).replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

boot();
