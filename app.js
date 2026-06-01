'use strict';

// ── spreadsheet sources ──────────────────────────────────────
const SOURCES = {
  gi: [
    { label: 'Spreadsheet', url: 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRq-sQxkvdbvaJtQAGG6iVz2q2UN9FCKZ8Mkyis87QHFptcOU3ViLh0_PJyMxFSgwJZrd10kbYpQFl1/pubhtml' },
  ],
  hsr: [
    { label: 'Sheet 1', url: 'https://docs.google.com/spreadsheets/u/2/d/e/2PACX-1vRsm60jYo8MdHWimjvY42wE8-j-0NBwG9-KutpNcQbylhhBiKBpGmUm1x3CXExthl2EB438RdMWdeT3/pubhtml' },
    { label: 'Sheet 2', url: 'https://docs.google.com/spreadsheets/u/2/d/e/2PACX-1vTFKy8epBat8dV-VFkGNnLj4HROtkFvNUgZWQgnUXgacjR8kgvSeuYLn_tatc7z5AEfM3pPZvpwP--o/pubhtml' },
  ],
  zzz: [
    { label: 'Spreadsheet', url: 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTj2PaPq6Py_1B5fsOPj_Moc-tN_7mut7fICczI6lz1njyEIAInTnfB7lAraX4pYCRGNbaHGlIbFZ90/pubhtml' },
  ],
};

function updateSourceCredit(game) {
  const links = SOURCES[game] || [];
  $('source-credit').innerHTML = links.map(s =>
    `<a href="${s.url}" target="_blank" rel="noopener" class="source-link">${s.label}</a>`
  ).join('<span class="source-sep">·</span>');
}

// ── state ────────────────────────────────────────────────────
let giChars  = [];
let hsrChars = [];
let zzzChars = [];
let allChars = [];      // active game's character list
let portraits    = {};  // {gi: {name: url}, hsr: {…}, zzz: {…}}
let icons        = {};  // {gi: {name: url}, hsr: {…}, zzz: {…}} — sidebar thumbnails
let releaseData  = {};  // {gi: {name: {version, date}}, …} — wiki release versions
let activeChar    = null;
let activeBuildIdx = 0;
let currentGame   = 'gi';   // 'gi' | 'hsr' | 'zzz'
let filterElement = null;   // currently selected element filter, or null
let tiersData     = {};     // {gi: {name: tier}, hsr: {…}, zzz: {…}}
let bannerData    = {};     // {gi: [{character, phase, start, end, verdict}], …}
let eventData     = {};     // {gi: [{name, type, start, end, rewards, tagline}], …}
let livestreamData = {};    // {gi: {version, title, date, highlights}, …}
let itemIcons     = {};     // {gi: {itemName: url}, hsr: {…}, zzz: {…}}

// ── favorites + density (localStorage) ───────────────────────
const FAV_KEY = 'archon:favorites';
const DENSITY_KEY = 'archon:density';
function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    return raw ? JSON.parse(raw) : { gi: [], hsr: [], zzz: [] };
  } catch { return { gi: [], hsr: [], zzz: [] }; }
}
function saveFavorites(f) {
  try { localStorage.setItem(FAV_KEY, JSON.stringify(f)); } catch {}
}
function loadDensity() {
  try { return localStorage.getItem(DENSITY_KEY) === 'compact'; } catch { return false; }
}
function saveDensity(compact) {
  try { localStorage.setItem(DENSITY_KEY, compact ? 'compact' : 'normal'); } catch {}
}
let favorites = { gi: [], hsr: [], zzz: [] };
function isFavorite(char) {
  const list = favorites[currentGame] || [];
  return list.includes(char.name);
}
function toggleFavorite(char) {
  if (!favorites[currentGame]) favorites[currentGame] = [];
  const idx = favorites[currentGame].indexOf(char.name);
  if (idx >= 0) favorites[currentGame].splice(idx, 1);
  else favorites[currentGame].push(char.name);
  saveFavorites(favorites);
  refreshList();
}
let compactMode = false;

// ── compare mode state ───────────────────────────────────────
let compareChar = null;

// ── build overrides (user-edited builds, persisted) ──────────
let baseCharsMap  = { gi: {}, hsr: {}, zzz: {} };
let buildOverrides = { gi: {}, hsr: {}, zzz: {} };

// ── palette + element grouping state ───────────────────────
let paletteOpen = false;
let paletteQuery = '';
let paletteIndex = 0;
let paletteItems = []; // [{type, char?, label, action}]

const COLLAPSE_KEY = 'archon:collapsed-groups';
let collapsedGroups = {};
function loadCollapsed() {
  try { return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '{}'); }
  catch { return {}; }
}
function saveCollapsed() {
  try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify(collapsedGroups)); } catch {}
}
function isGroupCollapsed(el) {
  return !!(collapsedGroups[currentGame] && collapsedGroups[currentGame][el]);
}
function toggleGroup(el) {
  if (!collapsedGroups[currentGame]) collapsedGroups[currentGame] = {};
  collapsedGroups[currentGame][el] = !collapsedGroups[currentGame][el];
  saveCollapsed();
  refreshList();
}

// ── Cloudflare Worker sync ────────────────────────────────────
const WORKER_URL_KEY    = 'archon:worker-url';
const WORKER_SECRET_KEY = 'archon:worker-secret';

function loadWorkerConfig() {
  try {
    return {
      url:    localStorage.getItem(WORKER_URL_KEY)    || '',
      secret: localStorage.getItem(WORKER_SECRET_KEY) || '',
    };
  } catch { return { url: '', secret: '' }; }
}
function saveWorkerConfig(url, secret) {
  try {
    localStorage.setItem(WORKER_URL_KEY,    url);
    localStorage.setItem(WORKER_SECRET_KEY, secret);
  } catch {}
}
function clearWorkerConfig() {
  try {
    localStorage.removeItem(WORKER_URL_KEY);
    localStorage.removeItem(WORKER_SECRET_KEY);
  } catch {}
}
function workerConfigured() {
  const { url, secret } = loadWorkerConfig();
  return !!(url && secret);
}
async function fetchWorkerOverrides() {
  const { url, secret } = loadWorkerConfig();
  if (!url || !secret) return null;
  try {
    const resp = await fetch(`${url.replace(/\/$/, '')}/overrides`, {
      headers: { 'Authorization': `Bearer ${secret}` },
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch { return null; }
}
async function pushWorkerOverrides() {
  const { url, secret } = loadWorkerConfig();
  if (!url || !secret) return { ok: false, reason: 'not-configured' };
  try {
    const resp = await fetch(`${url.replace(/\/$/, '')}/overrides`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${secret}`,
        'Content-Type':  'application/json',
      },
      body: JSON.stringify(buildOverrides),
    });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}));
      return { ok: false, reason: `${resp.status}: ${e.error || resp.statusText}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// ── sync modal ────────────────────────────────────────────────
function openSyncModal() {
  const cfg = loadWorkerConfig();
  const urlInput    = $('sync-url-input');
  const secretInput = $('sync-token-input');
  if (urlInput)    urlInput.value    = cfg.url;
  if (secretInput) secretInput.value = cfg.secret;
  $('sync-test-result').textContent = '';
  $('sync-modal').classList.remove('hidden');
  if (urlInput) urlInput.focus();
}
function closeSyncModal() {
  $('sync-modal').classList.add('hidden');
}
function saveSyncToken() {
  const url    = ($('sync-url-input').value    || '').trim();
  const secret = ($('sync-token-input').value  || '').trim();
  saveWorkerConfig(url, secret);
  closeSyncModal();
}
function clearSyncToken() {
  clearWorkerConfig();
  const urlInput = $('sync-url-input');
  if (urlInput) urlInput.value = '';
  const secretInput = $('sync-token-input');
  if (secretInput) secretInput.value = '';
  const r = $('sync-test-result');
  r.className = 'sync-test-result';
  r.textContent = 'Config cleared.';
}
async function testSyncToken() {
  const url    = ($('sync-url-input').value    || '').trim();
  const secret = ($('sync-token-input').value  || '').trim();
  const r = $('sync-test-result');
  r.className = 'sync-test-result';
  r.textContent = 'Testing…';
  if (!url || !secret) {
    r.className = 'sync-test-result error';
    r.textContent = '✗ Enter a Worker URL and secret first.';
    return;
  }
  try {
    const resp = await fetch(`${url.replace(/\/$/, '')}/overrides`, {
      headers: { 'Authorization': `Bearer ${secret}` },
    });
    if (resp.ok) {
      r.className = 'sync-test-result ok';
      r.textContent = '✓ Connected — worker is reachable.';
    } else {
      const e = await resp.json().catch(() => ({}));
      r.className = 'sync-test-result error';
      r.textContent = `✗ ${resp.status}: ${e.error || 'Request failed'}`;
    }
  } catch (e) {
    r.className = 'sync-test-result error';
    r.textContent = `✗ Network error: ${e.message}`;
  }
}

const OVERRIDES_KEY = 'archon:overrides';
function loadOverrides() {
  try {
    const raw = localStorage.getItem(OVERRIDES_KEY);
    return raw ? JSON.parse(raw) : { gi: {}, hsr: {}, zzz: {} };
  } catch { return { gi: {}, hsr: {}, zzz: {} }; }
}
function saveOverride(game, name, charData) {
  if (!buildOverrides[game]) buildOverrides[game] = {};
  buildOverrides[game][name] = charData;
  try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(buildOverrides)); } catch {}
}
function clearOverride(game, name) {
  if (buildOverrides[game]) delete buildOverrides[game][name];
  try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(buildOverrides)); } catch {}
}
function applyAllOverrides() {
  [['gi', giChars], ['hsr', hsrChars], ['zzz', zzzChars]].forEach(([g, arr]) => {
    const ovs = buildOverrides[g] || {};
    for (let i = 0; i < arr.length; i++) {
      if (ovs[arr[i].name]) arr[i] = { ...arr[i], ...ovs[arr[i].name] };
    }
  });
}

const $ = id => document.getElementById(id);

const ELEMENT_ORDER = ['Physical', 'Fire', 'Electric', 'Ice', 'Ether'];

const ELEMENT_ORDERS = {
  gi:  ['Pyro', 'Hydro', 'Cryo', 'Electro', 'Anemo', 'Geo', 'Dendro'],
  hsr: ['Fire', 'Ice', 'Wind', 'Lightning', 'Physical', 'Quantum', 'Imaginary', 'Elation'],
  zzz: ['Physical', 'Fire', 'Electric', 'Ice', 'Ether'],
};

const ELEMENT_COLORS = {
  Pyro:      ['#f87171', '#ef4444', false],
  Hydro:     ['#60a5fa', '#3b82f6', false],
  Cryo:      ['#67e8f9', '#22d3ee', true],
  Electro:   ['#a78bfa', '#7c3aed', false],
  Anemo:     ['#34d399', '#10b981', true],
  Geo:       ['#fbbf24', '#d97706', true],
  Dendro:    ['#86efac', '#16a34a', true],
  Fire:      ['#f87171', '#ef4444', false],
  Ice:       ['#67e8f9', '#22d3ee', true],
  Wind:      ['#34d399', '#10b981', true],
  Lightning: ['#a78bfa', '#7c3aed', false],
  Physical:  ['#94a3b8', '#64748b', false],
  Quantum:   ['#818cf8', '#6366f1', false],
  Imaginary: ['#fde68a', '#ca8a04', true],
  Elation:   ['#f472b6', '#db2777', false],
  Electric:  ['#facc15', '#ca8a04', true],
  Ether:     ['#c084fc', '#9333ea', false],
};

function zzzElementKey(char) {
  const i = ELEMENT_ORDER.indexOf(char.element || '');
  return i === -1 ? 999 : i;
}

// ── element accent setting (per-character page tint) ─────────
function applyCharAccent(char) {
  const el = charElement(char);
  const col = ELEMENT_COLORS[el];
  const root = document.documentElement;
  if (col) {
    const [idle, active, dark] = col;
    root.style.setProperty('--char-accent', active);
    root.style.setProperty('--char-accent-soft', idle);
    root.style.setProperty('--char-accent-fg', dark ? '#111' : '#fff');
  } else {
    root.style.removeProperty('--char-accent');
    root.style.removeProperty('--char-accent-soft');
    root.style.removeProperty('--char-accent-fg');
  }
}

// ── rarity detection for items (5✩ / 4✩ / 3✩ / 5★ / 4★ / 3★) ─
function detectRarity(text) {
  const m = text.match(/\(?\s*(\d)\s*[✩★⭐]/);
  if (m) return parseInt(m[1]);
  return null;
}

// ── section header glyph map ─────────────────────────────────
const SECTION_ICONS = {
  'role':           '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="8" cy="5.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3 14c.5-2.8 2.6-4.5 5-4.5s4.5 1.7 5 4.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  'weapons':        '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M2.5 13.5l8-8 1.5 1.5-8 8zM10.5 5.5l3-3M2 14l1.5-1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  'light cones':    '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M8 1.5l1.5 5h5l-4 3 1.5 5L8 11.5 4 14.5l1.5-5-4-3h5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  'w-engines':      '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><path d="M8 3v-2M8 15v-2M13 8h2M1 8h2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  'w-engine notes': '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/></svg>',
  'artifacts':      '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 6l5-3 5 3v4l-5 3-5-3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'relics':         '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 6l5-3 5 3v4l-5 3-5-3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'drive discs':    '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>',
  'main stats':     '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M2 13l3-5 3 3 4-7 2 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'sub stats':      '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M2 13l3-5 3 3 4-7 2 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'substats':       '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M2 13l3-5 3 3 4-7 2 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'talent priority':'<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 4h10M3 8h7M3 12h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  'ability priority':'<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 4h10M3 8h7M3 12h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  'tips':           '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M5.5 11h5M6.5 13h3M8 1.5c-2.8 0-4.5 2-4.5 4.5 0 2 1 3 1.5 4h6c.5-1 1.5-2 1.5-4 0-2.5-1.7-4.5-4.5-4.5z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'notes':          '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 2.5h7l3 3V14H3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M10 2.5v3h3M5.5 8h5M5.5 11h4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'other notes':    '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 2.5h7l3 3V14H3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M10 2.5v3h3M5.5 8h5M5.5 11h4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'team comps':     '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="4.5" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="11.5" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M1.5 13c.4-1.8 1.6-2.8 3-2.8s2.6 1 3 2.8M8.5 13c.4-1.8 1.6-2.8 3-2.8s2.6 1 3 2.8" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'example teams':  '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="4.5" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="11.5" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M1.5 13c.4-1.8 1.6-2.8 3-2.8s2.6 1 3 2.8M8.5 13c.4-1.8 1.6-2.8 3-2.8s2.6 1 3 2.8" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'mindscapes':     '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M8 1.5c-1.5 2-4 2.5-4 5.5 0 2.5 1.8 4.5 4 4.5s4-2 4-4.5c0-3-2.5-3.5-4-5.5z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'eidolons':       '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M8 1.5c-1.5 2-4 2.5-4 5.5 0 2.5 1.8 4.5 4 4.5s4-2 4-4.5c0-3-2.5-3.5-4-5.5z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'notable eidolons':'<svg viewBox="0 0 16 16" class="sec-ico"><path d="M8 1.5c-1.5 2-4 2.5-4 5.5 0 2.5 1.8 4.5 4 4.5s4-2 4-4.5c0-3-2.5-3.5-4-5.5z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  'stat targets':   '<svg viewBox="0 0 16 16" class="sec-ico"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="0.8" fill="currentColor"/></svg>',
  'disc notes':     '<svg viewBox="0 0 16 16" class="sec-ico"><path d="M3 2.5h7l3 3V14H3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
};
function sectionIcon(label) {
  return SECTION_ICONS[label.toLowerCase()] || '';
}

// ── stat-target table parser ────────────────────────────
function parseStatTargets(text) {
  if (!text || !text.trim()) return null;
  const sections = [];
  let cur = { title: null, rows: [] };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) {
      if (cur.rows.length || cur.title) { sections.push(cur); cur = { title: null, rows: [] }; }
      continue;
    }
    // "LABEL:" alone (no value) → section heading
    const headMatch = line.match(/^([^:]+):\s*$/);
    if (headMatch) {
      if (cur.rows.length || cur.title) { sections.push(cur); cur = { title: null, rows: [] }; }
      cur.title = headMatch[1].trim();
      continue;
    }
    // "LABEL: VALUE"
    const kvMatch = line.match(/^([^:]+):\s*(.+)$/);
    if (kvMatch) {
      cur.rows.push({ label: kvMatch[1].trim(), value: kvMatch[2].trim() });
      continue;
    }
    // bare value
    cur.rows.push({ label: '', value: line });
  }
  if (cur.rows.length || cur.title) sections.push(cur);
  return sections.length ? sections : null;
}

function statTargetCard(text) {
  const sections = parseStatTargets(text);
  if (!sections) return '';
  let body = '';
  for (const sec of sections) {
    if (sec.title) body += `<div class="stat-section-title">${escHtml(sec.title)}</div>`;
    body += '<div class="stat-target-grid">';
    for (const r of sec.rows) {
      if (r.label) {
        body += `<span class="st-label">${escHtml(r.label)}</span><span class="st-value">${escHtml(r.value)}</span>`;
      } else {
        body += `<span class="st-full">${escHtml(r.value)}</span>`;
      }
    }
    body += '</div>';
  }
  return `<div class="build-card left-card"><div class="card-label">${sectionIcon('stat targets')}<span>stat targets</span></div>${body}</div>`;
}

function pullPriorityCard(text) {
  if (!text || !text.trim()) return '';
  return `<div class="build-card left-card pull-priority">
    <div class="card-label">${sectionIcon('pull priority')}<span>pull priority</span></div>
    <div class="pp-body">${escHtml(text.trim())}</div>
  </div>`;
}

// ── character icon lookup with name normalization ──────────
function lookupIcon(game, name) {
  if (!name) return null;
  const map = icons[game] || {};
  if (map[name]) return map[name];
  // strip parens → try inside-parens or outside-parens
  const parenMatch = name.match(/\(([^)]+)\)/);
  if (parenMatch && map[parenMatch[1].trim()]) return map[parenMatch[1].trim()];
  const stripped = name.replace(/\s*\(.*?\)\s*/g, '').trim();
  if (map[stripped]) return map[stripped];
  // last word fallback ("Tsukishiro Yanagi" → "Yanagi")
  const last = stripped.split(' ').pop();
  if (last && map[last]) return map[last];
  // first word
  const first = stripped.split(' ')[0];
  if (first && map[first]) return map[first];
  // try matching against keys case-insensitive
  const lower = name.toLowerCase();
  for (const k of Object.keys(map)) {
    if (k.toLowerCase() === lower || k.toLowerCase().includes(lower) || lower.includes(k.toLowerCase())) {
      return map[k];
    }
  }
  return null;
}

function teamMemberThumb(game, name) {
  const display = game === 'zzz' ? zzzShortName(name) : name;
  const url = lookupIcon(game, name);
  const imgHtml = url
    ? `<img class="tm-icon" src="${escHtml(url)}" alt="" referrerpolicy="no-referrer" loading="lazy">`
    : '<span class="tm-icon tm-icon-blank"></span>';
  return `<span class="team-thumb">${imgHtml}<span class="tm-name">${escHtml(display)}</span></span>`;
}

// ── status pill (NEW / BUFFED) ────────────────────────────────
const TODAY = new Date('2026-05-21'); // matches "today" per project; falls back gracefully
function statusPill(char) {
  let dateStr = null;
  if (currentGame === 'hsr' && char.release_date) dateStr = char.release_date;
  else {
    const rd = (releaseData[currentGame] || {})[char.name];
    if (rd && rd.date) dateStr = rd.date;
  }
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '';
  const diff = (TODAY - d) / (1000 * 60 * 60 * 24);
  if (diff < 0) return '<span class="pill pill-upcoming">UPCOMING</span>';
  if (diff <= 45) return '<span class="pill pill-new">NEW</span>';
  if (diff <= 90) return '<span class="pill pill-recent">RECENT</span>';
  return '';
}

// ── boot ─────────────────────────────────────────────────────
async function init() {
  const [gi, hsr, zzz, pts, ico, rel, tiers, bnrs, evts, livs, itmIco] = await Promise.all([
    fetch('builds.json').then(r => r.json()),
    fetch('hsr_builds.json').then(r => r.json()),
    fetch('zzz_builds.json').then(r => r.json()),
    fetch('portraits.json').then(r => r.json()).catch(() => ({})),
    fetch('icons.json').then(r => r.json()).catch(() => ({})),
    fetch('release_data.json').then(r => r.json()).catch(() => ({})),
    fetch('tiers.json').then(r => r.json()).catch(() => ({})),
    fetch('banners.json').then(r => r.json()).catch(() => ({})),
    fetch('events.json').then(r => r.json()).catch(() => ({})),
    fetch('livestreams.json').then(r => r.json()).catch(() => ({})),
    fetch('item_icons.json').then(r => r.json()).catch(() => ({})),
  ]);
  giChars  = gi;
  hsrChars = hsr;
  zzzChars = zzz;
  portraits = pts;
  icons = ico;
  releaseData = rel;
  tiersData = tiers;
  bannerData = bnrs;
  eventData = evts;
  livestreamData = livs;
  itemIcons = itmIco;

  // snapshot unmodified data so Reset can restore it
  baseCharsMap.gi  = Object.fromEntries(gi.map(c => [c.name, JSON.parse(JSON.stringify(c))]));
  baseCharsMap.hsr = Object.fromEntries(hsr.map(c => [c.name, JSON.parse(JSON.stringify(c))]));
  baseCharsMap.zzz = Object.fromEntries(zzz.map(c => [c.name, JSON.parse(JSON.stringify(c))]));
  buildOverrides = loadOverrides();
  if (workerConfigured()) {
    try {
      const workerOvs = await Promise.race([
        fetchWorkerOverrides(),
        new Promise(r => setTimeout(() => r(null), 2000)),
      ]);
      if (workerOvs) {
        buildOverrides = workerOvs;
        try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(buildOverrides)); } catch {}
      }
    } catch {}
  }
  applyAllOverrides();

  allChars = giChars;

  // load persisted state
  collapsedGroups = loadCollapsed();

  // rail — game buttons
  document.querySelectorAll('.rail-game').forEach(btn => {
    btn.addEventListener('click', () => switchGame(btn.dataset.game));
  });

  // rail — lens buttons (tiers/favorites/compare hooked separately)
  document.querySelectorAll('.rail-lens').forEach(btn => {
    const lens = btn.dataset.lens;
    if (lens === 'tiers') {
      btn.addEventListener('click', showTierView);
    } else if (lens === 'favorites') {
      btn.addEventListener('click', () => toggleFavoritesLens());
    } else if (lens === 'compare') {
      btn.addEventListener('click', () => {
        if (compareChar) clearCompare();
      });
    } else if (lens === 'characters') {
      btn.addEventListener('click', () => clearLensViews());
    }
  });

  $('back-btn').addEventListener('click', () => {
    document.body.classList.remove('viewing-char');
    $('back-btn').classList.add('hidden');
    $('tier-view').classList.add('hidden');
    $('tier-btn').classList.remove('active');
    $('placeholder').classList.remove('hidden');
    $('char-view').classList.add('hidden');
    activeChar = null;
    clearCompare();
    updateLensState();
    updateUrl();
  });

  $('tier-btn').addEventListener('click', showTierView);

  // ── palette wire-up ──
  const paletteTrigger = $('palette-trigger');
  if (paletteTrigger) paletteTrigger.addEventListener('click', openPalette);
  const paletteInput = $('palette-input');
  if (paletteInput) {
    paletteInput.addEventListener('input', () => {
      paletteQuery = paletteInput.value;
      paletteIndex = 0;
      renderPalette();
    });
    paletteInput.addEventListener('keydown', handlePaletteKeydown);
  }
  const backdrop = document.querySelector('#palette .palette-backdrop');
  if (backdrop) backdrop.addEventListener('click', closePalette);

  updateSourceCredit(currentGame);
  renderElementFilters();

  // ── favorites + density load ──
  favorites = loadFavorites();
  compactMode = loadDensity();
  document.body.classList.toggle('density-compact', compactMode);

  // ── wire density toggle ──
  const dToggle = $('density-toggle');
  if (dToggle) {
    dToggle.addEventListener('click', () => {
      compactMode = !compactMode;
      saveDensity(compactMode);
      document.body.classList.toggle('density-compact', compactMode);
      dToggle.classList.toggle('active', compactMode);
    });
    dToggle.classList.toggle('active', compactMode);
  }

  // ── wire compare close ──
  const cClose = $('compare-close');
  if (cClose) cClose.addEventListener('click', clearCompare);

  // ── edit button ──
  const editBtn = $('crumb-edit-btn');
  if (editBtn) editBtn.addEventListener('click', () => { if (activeChar) renderEditView(activeChar); });

  // ── sync modal ──
  const syncBtn = $('github-sync-btn');
  if (syncBtn) syncBtn.addEventListener('click', openSyncModal);
  const syncClose = $('sync-modal-close');
  if (syncClose) syncClose.addEventListener('click', closeSyncModal);
  const syncBackdrop = document.querySelector('#sync-modal .sync-backdrop');
  if (syncBackdrop) syncBackdrop.addEventListener('click', closeSyncModal);
  const syncSave = $('sync-save-btn');
  if (syncSave) syncSave.addEventListener('click', saveSyncToken);
  const syncClear = $('sync-clear-btn');
  if (syncClear) syncClear.addEventListener('click', clearSyncToken);
  const syncTest = $('sync-test-btn');
  if (syncTest) syncTest.addEventListener('click', testSyncToken);

  // ── keyboard navigation ──
  document.addEventListener('keydown', handleKeydown);

  // ── URL state on load ──
  window.addEventListener('popstate', applyUrlState);

  refreshList();
  renderHighlights();
  updateGameLabel();
  applyUrlState();
}

// ── URL state ─────────────────────────────────────────────
function applyUrlState() {
  const params = new URLSearchParams(location.hash.slice(1) || location.search.slice(1));
  const g = params.get('game');
  const c = params.get('char');
  const cmp = params.get('compare');
  const view = params.get('view'); // 'tier'
  if (g && g !== currentGame && ['gi','hsr','zzz'].includes(g)) {
    _switchGameNoUrl(g);
  }
  if (view === 'tier') {
    showTierView();
    return;
  }
  if (c) {
    const char = allChars.find(x => x.name.toLowerCase() === c.toLowerCase());
    if (char) {
      _selectCharNoUrl(char);
      if (cmp) {
        const cmpChar = allChars.find(x => x.name.toLowerCase() === cmp.toLowerCase());
        if (cmpChar) setCompareChar(cmpChar);
        else clearCompare();
      } else clearCompare();
    }
  }
}

function updateUrl() {
  const params = new URLSearchParams();
  params.set('game', currentGame);
  if (activeChar) params.set('char', activeChar.name);
  if (compareChar) params.set('compare', compareChar.name);
  const target = '#' + params.toString();
  if (location.hash !== target) {
    history.replaceState(null, '', target);
  }
}

// ── keyboard navigation ───────────────────────────────
function handleKeydown(e) {
  const t = e.target;
  const inField = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
  // ⌘K / Ctrl+K always opens palette
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    openPalette();
    return;
  }
  if (e.key === '/' && !inField) {
    e.preventDefault();
    openPalette();
    return;
  }
  if (e.key === 'Escape') {
    if (!$('sync-modal').classList.contains('hidden')) { closeSyncModal(); return; }
    if (paletteOpen) { closePalette(); return; }
    if (inField) { t.blur(); return; }
    if (compareChar) { clearCompare(); return; }
    $('back-btn').click();
    return;
  }
  if (inField) return;
  const items = [...document.querySelectorAll('#char-list li:not(.list-section-header)')];
  if (!items.length) return;
  const activeIdx = items.findIndex(li => li.classList.contains('active'));
  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault();
    const next = items[Math.min(items.length - 1, (activeIdx < 0 ? 0 : activeIdx + 1))];
    if (next) next.click();
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault();
    const prev = items[Math.max(0, (activeIdx < 0 ? 0 : activeIdx - 1))];
    if (prev) prev.click();
  } else if (e.key === '1') { switchGame('gi'); }
  else if (e.key === '2') { switchGame('hsr'); }
  else if (e.key === '3') { switchGame('zzz'); }
}

// ── compare mode ───────────────────────────────────────────
// ── command palette ───────────────────────────────────────────
function openPalette() {
  if (paletteOpen) return;
  paletteOpen = true;
  paletteQuery = '';
  paletteIndex = 0;
  const root = $('palette');
  if (!root) return;
  root.classList.remove('hidden');
  const input = $('palette-input');
  if (input) { input.value = ''; setTimeout(() => input.focus(), 10); }
  renderPalette();
}
function closePalette() {
  if (!paletteOpen) return;
  paletteOpen = false;
  $('palette').classList.add('hidden');
}

function fuzzyScore(query, text) {
  if (!query) return 0;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (t.startsWith(q)) return 1000 - t.length;
  if (t.includes(q)) return 500 - t.length;
  // subsequence match
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length ? 100 - t.length : -1;
}

function buildPaletteItems() {
  const q = paletteQuery.trim();
  const items = [];

  // Characters (active game first, then others)
  const allGameChars = [
    ...allChars.map(c => ({ char: c, game: currentGame })),
    ...(currentGame !== 'gi' ? giChars.map(c => ({ char: c, game: 'gi' })) : []),
    ...(currentGame !== 'hsr' ? hsrChars.map(c => ({ char: c, game: 'hsr' })) : []),
    ...(currentGame !== 'zzz' ? zzzChars.map(c => ({ char: c, game: 'zzz' })) : []),
  ];
  let charMatches = allGameChars
    .map(({ char, game }) => ({ char, game, score: fuzzyScore(q, char.name) }))
    .filter(x => !q || x.score > 0)
    .sort((a, b) => b.score - a.score);
  // cap to 12 results when querying, otherwise show top 30
  charMatches = q ? charMatches.slice(0, 12) : charMatches.slice(0, 30);
  if (charMatches.length) {
    items.push({ kind: 'section', label: 'Characters' });
    for (const { char, game } of charMatches) {
      items.push({
        kind: 'char',
        char, game,
        label: char.name,
        sublabel: gamePaletteLabel(game, char),
        action: () => {
          if (game !== currentGame) _switchGameNoUrl(game);
          allChars = game === 'gi' ? giChars : game === 'hsr' ? hsrChars : zzzChars;
          selectChar(char);
        },
      });
    }
  }

  // Actions / Lenses
  const actionFilters = [
    { label: 'Open Tier List', score: fuzzyScore(q, 'open tier list'), icon: 'tier', action: showTierView },
    { label: 'Show Pinned Characters', score: fuzzyScore(q, 'show pinned characters'), icon: 'star', action: () => { favoritesOnly = true; updateLensState(); refreshList(); } },
    { label: 'Switch to Genshin Impact', score: fuzzyScore(q, 'switch to genshin impact'), icon: 'game', action: () => switchGame('gi') },
    { label: 'Switch to Honkai: Star Rail', score: fuzzyScore(q, 'switch to honkai star rail'), icon: 'game', action: () => switchGame('hsr') },
    { label: 'Switch to Zenless Zone Zero', score: fuzzyScore(q, 'switch to zenless zone zero'), icon: 'game', action: () => switchGame('zzz') },
    { label: 'Toggle Compact List', score: fuzzyScore(q, 'toggle compact list'), icon: 'density', action: () => $('density-toggle').click() },
  ];
  const actionMatches = actionFilters.filter(a => !q || a.score > 0).sort((a, b) => b.score - a.score);
  if (actionMatches.length) {
    items.push({ kind: 'section', label: 'Actions' });
    for (const a of actionMatches) {
      items.push({ kind: 'action', label: a.label, icon: a.icon, action: a.action });
    }
  }

  return items;
}

function gamePaletteLabel(game, char) {
  const parts = [];
  parts.push(game.toUpperCase());
  if (game === 'hsr' && char.path) parts.push(char.path);
  else if (game === 'zzz' && char.specialty) parts.push(char.specialty);
  else {
    const el = ((releaseData[game] || {})[char.name] || {}).element || char.element;
    if (el) parts.push(el);
  }
  return parts.join(' · ');
}

const PALETTE_ICONS = {
  tier:    '<svg viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="2.5" rx="0.5" fill="#f5a623"/><rect x="2" y="7" width="9" height="2.5" rx="0.5" fill="#9b59b6"/><rect x="2" y="11" width="6" height="2.5" rx="0.5" fill="#3498db"/></svg>',
  star:    '<svg viewBox="0 0 16 16" fill="none"><path d="M8 2l1.8 4 4.2.4-3.2 2.8 1 4.4L8 11.3 4.2 13.6l1-4.4L2 6.4l4.2-.4z" stroke="currentColor" stroke-width="1.4" fill="rgba(240,192,64,0.3)"/></svg>',
  game:    '<svg viewBox="0 0 16 16" fill="none"><rect x="1" y="5" width="14" height="7" rx="2" stroke="currentColor" stroke-width="1.4"/><circle cx="11" cy="8.5" r="1" fill="currentColor"/><path d="M4 7v3M3 8.5h2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  density: '<svg viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

function renderPalette() {
  paletteItems = buildPaletteItems();
  const wrap = $('palette-results');
  if (!wrap) return;
  if (!paletteItems.length || paletteItems.every(i => i.kind === 'section')) {
    wrap.innerHTML = '<div class="palette-empty">No matches</div>';
    return;
  }
  // clamp index to a selectable (non-section) item
  const selectable = paletteItems.filter(i => i.kind !== 'section');
  if (paletteIndex >= selectable.length) paletteIndex = 0;

  let html = '';
  let selIdx = -1;
  for (let i = 0; i < paletteItems.length; i++) {
    const it = paletteItems[i];
    if (it.kind === 'section') {
      html += `<div class="palette-section-title">${escHtml(it.label)}</div>`;
    } else {
      selIdx++;
      const isActive = selIdx === paletteIndex;
      const cls = `palette-item${isActive ? ' active' : ''}`;
      let iconHtml = '';
      if (it.kind === 'char') {
        const url = (icons[it.game] || {})[it.char.name];
        iconHtml = url
          ? `<img class="palette-item-icon" src="${escHtml(url)}" alt="" referrerpolicy="no-referrer">`
          : '<span class="palette-item-iconwrap"></span>';
      } else {
        iconHtml = `<span class="palette-item-iconwrap">${PALETTE_ICONS[it.icon] || ''}</span>`;
      }
      let tierBadge = '';
      if (it.kind === 'char') {
        const tier = (tiersData[it.game] || {})[it.char.name];
        if (tier) tierBadge = `<span class="palette-item-tier tier-${tier.replace('.', '_')}">${tier}</span>`;
      }
      html += `<div class="${cls}" data-selidx="${selIdx}">
        ${iconHtml}
        <span class="palette-item-name">${escHtml(it.label)}</span>
        ${tierBadge}
        ${it.sublabel ? `<span class="palette-item-meta">${escHtml(it.sublabel)}</span>` : ''}
      </div>`;
    }
  }
  wrap.innerHTML = html;
  wrap.querySelectorAll('.palette-item').forEach(el => {
    el.addEventListener('click', (e) => {
      const idx = parseInt(el.dataset.selidx, 10);
      runPaletteIndex(idx, e.shiftKey);
    });
  });
  // scroll active into view
  const activeEl = wrap.querySelector('.palette-item.active');
  if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
}

function runPaletteIndex(idx, withShift) {
  const selectable = paletteItems.filter(i => i.kind !== 'section');
  const target = selectable[idx];
  if (!target) return;
  closePalette();
  if (target.kind === 'char' && withShift) {
    // shift-enter on a char => compare
    if (target.game !== currentGame) _switchGameNoUrl(target.game);
    allChars = target.game === 'gi' ? giChars : target.game === 'hsr' ? hsrChars : zzzChars;
    setCompareChar(target.char);
  } else if (target.action) {
    target.action();
  }
}

function handlePaletteKeydown(e) {
  if (e.key === 'Escape') { e.preventDefault(); closePalette(); return; }
  const selectable = paletteItems.filter(i => i.kind !== 'section');
  if (!selectable.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    paletteIndex = Math.min(selectable.length - 1, paletteIndex + 1);
    renderPalette();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    paletteIndex = Math.max(0, paletteIndex - 1);
    renderPalette();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    runPaletteIndex(paletteIndex, e.shiftKey);
  }
}

function setCompareChar(char) {
  if (!activeChar) { selectChar(char); return; }
  if (activeChar.name === char.name) return;
  compareChar = char;
  document.body.classList.add('compare-on');
  applyCharAccent(activeChar); // keep primary accent on root
  renderCompareView();
  highlightCompare(char);
  updateLensState();
  updateUrl();
}
function clearCompare() {
  compareChar = null;
  document.body.classList.remove('compare-on');
  document.querySelectorAll('#char-list li.compare').forEach(li => li.classList.remove('compare'));
  updateLensState();
  updateUrl();
}
function highlightCompare(char) {
  const key = char.name + '|' + (char.path || '');
  document.querySelectorAll('#char-list li').forEach(li =>
    li.classList.toggle('compare', li.dataset.name === key));
}
function renderCompareView() {
  if (!compareChar) return;
  const wrap = $('compare-panel');
  if (!wrap) return;
  const build = compareChar.builds[0];
  const portraitUrl = (portraits[currentGame] || {})[compareChar.name];
  const cmpEl = charElement(compareChar);
  const cmpCol = ELEMENT_COLORS[cmpEl];
  const cmpAccent = cmpCol ? cmpCol[1] : '#818cf8';
  const cmpAccentSoft = cmpCol ? cmpCol[0] : '#a5b4fc';

  let cards = '';
  if (currentGame === 'gi') {
    cards = itemCard('weapons', build.weapons, 'gi')
          + abilityCard('talent priority', build.talent_priority)
          + itemCard('artifacts', build.artifacts, 'gi')
          + card('main stats', build.main_stats);
  } else if (currentGame === 'hsr') {
    cards = itemCard('light cones', build.light_cones, 'hsr')
          + abilityCard('ability priority', build.ability_priority, build.ability_notes)
          + hsrRelicCard(build)
          + card('main stats', build.main_stats);
  } else {
    cards = itemCard('w-engines', build.w_engines, 'zzz')
          + abilityCard('ability priority', build.ability)
          + zzzDiscCard(build);
  }

  const portraitHtml = portraitUrl
    ? `<img class="cmp-portrait" src="${escHtml(portraitUrl)}" alt="" referrerpolicy="no-referrer">`
    : '<div class="cmp-portrait cmp-portrait-blank"></div>';

  wrap.innerHTML = `
    <div class="cmp-head">
      <div class="cmp-portrait-wrap">${portraitHtml}
        <div class="cmp-nameplate">
          <span class="cmp-name">${escHtml(toTitle(compareChar.name))}</span>
        </div>
      </div>
      <button id="compare-close" class="cmp-close" title="Close compare" aria-label="Close compare">×</button>
      <div class="cmp-role">
        <div class="role-label">vs — ${escHtml(build.role || '')}</div>
      </div>
    </div>
    <div class="cmp-cards">${cards}</div>
  `;
  wrap.style.setProperty('--cmp-accent', cmpAccent);
  wrap.style.setProperty('--cmp-accent-soft', cmpAccentSoft);
  $('compare-close').addEventListener('click', clearCompare);
}

// ── highlights row on landing ────────────────────────────────
function renderHighlights() {
  const wrap = $('highlights');
  if (!wrap) return;
  const banners = (bannerData[currentGame] || []).filter(b => b && b.character);
  if (banners.length || livestreamData[currentGame] || (eventData[currentGame] || []).length) {
    renderPullGuide(wrap, banners);
    return;
  }
  // Fallback when no banner data: simple latest-3 row
  const sorted = [...allChars].sort((a, b) => releaseKey(b) - releaseKey(a));
  const top = sorted.slice(0, 3);
  if (!top.length) { wrap.innerHTML = ''; return; }

  const gameLabel = currentGame === 'gi' ? 'Genshin Impact' : currentGame === 'hsr' ? 'Honkai: Star Rail' : 'Zenless Zone Zero';
  let html = `<div class="hl-eyebrow">latest in ${escHtml(gameLabel)}</div><div class="hl-grid">`;
  for (const c of top) {
    const portraitUrl = (portraits[currentGame] || {})[c.name];
    const el = charElement(c);
    const col = ELEMENT_COLORS[el];
    const accent = col ? col[1] : '#818cf8';
    const tier = charTier(c);
    html += `<button class="hl-card" data-name="${escHtml(c.name)}" style="--hl-accent:${accent}">
      <div class="hl-art">${portraitUrl ? `<img src="${escHtml(portraitUrl)}" alt="" referrerpolicy="no-referrer">` : ''}</div>
      <div class="hl-info">
        <div class="hl-name">${escHtml(toTitle(c.name))}</div>
        <div class="hl-meta">${el ? escHtml(el) : ''}${tier ? ` <span class="tier-badge tier-${tier.replace('.', '_')}">${tier}</span>` : ''}</div>
      </div>
    </button>`;
  }
  html += '</div>';
  wrap.innerHTML = html;
  wrap.querySelectorAll('.hl-card').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const char = allChars.find(x => x.name === name);
      if (char) selectChar(char);
    });
  });
}

// ── Pull Guide (variation 4) ─────────────────────────────────
function tierColor(tier) {
  const map = { 'T0':'#f5a623','T0.5':'#e8832a','T1':'#9b59b6','T1.5':'#5b7fd4','T2':'#3498db','T3':'#27ae60','T4':'#8b949e',
                'SS':'#f5a623','S':'#9b59b6','A':'#3498db','B':'#27ae60','C':'#8b949e','D':'#555' };
  return map[tier] || '#9b59b6';
}
function tierFg(tier) {
  return (tier === 'T0' || tier === 'SS') ? '#000' : '#fff';
}
function tierRank(tier) {
  const map = { 'T0':1,'SS':1,'T0.5':2,'S':2,'T1':3,'A':3,'T1.5':4,'T2':5,'B':5,'T3':6,'C':6,'T4':7,'D':7 };
  return map[tier] || 9;
}

function renderPullGuide(wrap, banners) {
  const games = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
  const now = Date.now();
  const findChar = (name) => allChars.find(c => c.name === name);
  const computeDelta = (b) => {
    const start = new Date(b.start).getTime();
    const end = new Date(b.end).getTime();
    return { start, end, isActive: now >= start && now < end, isPast: now >= end, isFuture: now < start };
  };
  const decorated = banners.map(b => ({ b, ...computeDelta(b) }));
  const featured =
    decorated.find(d => d.isActive && d.b.phase === 1)
    || decorated.find(d => d.isActive)
    || decorated.find(d => d.isFuture)
    || decorated[0];
  const upcoming = decorated.filter(d => d !== featured && (d.isFuture || (d.isActive && d.b.phase !== featured.b.phase)))
    .sort((a, b) => a.start - b.start).slice(0, 2);

  const featuredChar = findChar(featured.b.character);
  const featuredTier = featuredChar ? (tiersData[currentGame] || {})[featuredChar.name] : null;
  const featuredTierCol = featuredTier ? tierColor(featuredTier) : '#9b59b6';
  const featuredTierFg  = featuredTier ? tierFg(featuredTier) : '#fff';
  const featuredElement = featuredChar ? charElement(featuredChar) : null;
  const splash = featuredChar ? (portraits[currentGame] || {})[featuredChar.name] : null;
  const remainingMs = featured.end - now;
  const days = Math.max(0, Math.floor(remainingMs / 86400000));
  const hours = Math.max(0, Math.floor((remainingMs % 86400000) / 3600000));
  const mins = Math.max(0, Math.floor((remainingMs % 3600000) / 60000));
  const role = featuredChar ? (featuredChar.builds?.[0]?.role || '').split('\n')[0] : '';
  const groupVal = featuredChar ? (currentGame === 'hsr' ? featuredChar.path : currentGame === 'zzz' ? featuredChar.specialty : null) : null;
  const bannerLabel = featured.b.rerun ? `Phase ${featured.b.phase} Rerun` : `Phase ${featured.b.phase}`;

  const inList = new Set([featured.b.character, ...upcoming.map(d => d.b.character)]);
  const tierMap = tiersData[currentGame] || {};
  const worthCands = allChars
    .filter(c => !inList.has(c.name))
    .map(c => ({ char: c, tier: tierMap[c.name] }))
    .filter(x => x.tier === 'T0' || x.tier === 'SS' || x.tier === 'T0.5')
    .sort((a, b) => (tierRank(a.tier) - tierRank(b.tier)))
    .slice(0, 2);
  const worthList = [
    { char: featuredChar, tier: featuredTier, verdict: featured.b.verdict, when: 'On banner now' },
    ...worthCands.map(x => ({ char: x.char, tier: x.tier, verdict: null, when: 'Likely future rerun' })),
  ].filter(x => x.char);

  let html = `
    <div class="pg-body">
      ${renderLivestreamStrip()}
      <div class="pg-pre">Featured banner · ${escHtml(games[currentGame])} · ${escHtml(bannerLabel)}</div>
      <div class="pg-banner">
        <div class="pg-banner-left">
          <h1 class="pg-banner-title">
            ${escHtml(toTitle(featured.b.character))}
            ${featuredTier ? `<span class="pg-banner-tier" style="background:${featuredTierCol};color:${featuredTierFg}">${escHtml(featuredTier)}</span>` : ''}
          </h1>
          <div class="pg-banner-meta">
            ${groupVal ? `<span>${escHtml(groupVal)}</span><span class="sep">·</span>` : ''}
            ${featuredElement ? `<span>${escHtml(featuredElement)}</span>` : ''}
            ${role ? `<span class="sep">·</span><span>${escHtml(role)}</span>` : ''}
          </div>
          ${featured.b.verdict ? `
            <div class="pg-verdict">
              <div class="pg-verdict-label">Pull verdict</div>
              <div class="pg-verdict-text">${escHtml(featured.b.verdict)}</div>
            </div>
          ` : ''}
          ${remainingMs > 0 ? `
            <div class="pg-timer">
              <span class="pg-timer-label">Banner ends in</span>
              <div class="pg-timer-vals">
                <div class="pg-timer-val"><span class="pg-timer-num">${days}</span><span class="pg-timer-unit">days</span></div>
                <div class="pg-timer-val"><span class="pg-timer-num">${String(hours).padStart(2,'0')}</span><span class="pg-timer-unit">hrs</span></div>
                <div class="pg-timer-val"><span class="pg-timer-num">${String(mins).padStart(2,'0')}</span><span class="pg-timer-unit">min</span></div>
              </div>
            </div>
          ` : ''}
          <div class="pg-banner-cta">
            <button class="pg-cta primary" data-pg-open="${escHtml(featured.b.character)}">View build →</button>
            <button class="pg-cta secondary" data-pg-tiers>Tier list</button>
          </div>
        </div>
        <div class="pg-banner-art">
          ${splash ? `<img src="${escHtml(splash)}" alt="" referrerpolicy="no-referrer">` : ''}
        </div>
      </div>
      <div class="pg-twocol">
  `;

  if (upcoming.length) {
    html += `<div class="pg-mini" style="--m-color:#22d3ee"><div class="pg-mini-title">Coming next</div><div class="pg-upcoming">`;
    for (const u of upcoming) {
      const c = findChar(u.b.character);
      const cEl = c ? charElement(c) : null;
      const cElCol = cEl ? (ELEMENT_COLORS[cEl] || ['#8b949e'])[1] : '#8b949e';
      const cSplash = c ? (portraits[currentGame] || {})[c.name] : null;
      const cIcon = c ? (icons[currentGame] || {})[c.name] : null;
      const cTier = c ? (tiersData[currentGame] || {})[c.name] : null;
      const cRole = c ? ((c.builds?.[0]?.role || '').split('\n')[0]) : '';
      const cGroup = c ? (currentGame === 'hsr' ? c.path : currentGame === 'zzz' ? c.specialty : cEl) : null;
      const phaseLabel = u.b.rerun ? `Phase ${u.b.phase} rerun` : `Phase ${u.b.phase}`;
      html += `<div class="pg-up-row" style="--c-color:${cElCol}" data-pg-open="${escHtml(u.b.character)}">
        <div class="pg-up-art">${cSplash ? `<img src="${escHtml(cSplash)}" alt="" referrerpolicy="no-referrer">` : (cIcon ? `<img src="${escHtml(cIcon)}" alt="" referrerpolicy="no-referrer">` : '')}</div>
        <div class="pg-up-info">
          <div class="pg-up-tag">${escHtml(phaseLabel)}</div>
          <div class="pg-up-name">${escHtml(toTitle(u.b.character))}</div>
          <div class="pg-up-sub">${escHtml([cEl, cGroup, cTier && (cTier + (cRole ? ' ' + cRole : ''))].filter(Boolean).join(' · '))}</div>
        </div>
      </div>`;
    }
    html += `</div></div>`;
  }

  if (worthList.length) {
    html += `<div class="pg-mini" style="--m-color:#f5a623"><div class="pg-mini-title">Worth pulling</div><div class="pg-worth">`;
    for (const w of worthList) {
      const cIcon = (icons[currentGame] || {})[w.char.name];
      const cEl = charElement(w.char);
      const cElCol = cEl ? (ELEMENT_COLORS[cEl] || ['#8b949e'])[1] : '#8b949e';
      const cRole = (w.char.builds?.[0]?.role || '').split('\n')[0];
      const rank = tierRank(w.tier);
      const badge = rank <= 1 ? { cls: 'high', text: 'High' } : rank <= 2 ? { cls: 'mid', text: 'Strong' } : { cls: 'skip', text: 'Skip' };
      const meta = [w.tier && (w.tier + (cRole ? ' ' + cRole : '')), w.when].filter(Boolean).join(' · ');
      html += `<div class="pg-worth-row" style="--c-color:${cElCol}" data-pg-open="${escHtml(w.char.name)}">
        ${cIcon ? `<img src="${escHtml(cIcon)}" alt="" referrerpolicy="no-referrer">` : '<span></span>'}
        <div class="pg-worth-info">
          <div class="pg-worth-name">${escHtml(toTitle(w.char.name))}</div>
          <div class="pg-worth-meta">${escHtml(meta)}</div>
        </div>
        <span class="pg-worth-badge ${badge.cls}"><span class="pg-worth-dot"></span>${badge.text}</span>
      </div>`;
    }
    html += `</div></div>`;
  }
  html += `</div>${renderEventsBlock()}</div>`;

  wrap.innerHTML = html;
  wrap.querySelectorAll('[data-pg-open]').forEach(el => {
    el.addEventListener('click', () => {
      const name = el.dataset.pgOpen;
      const char = allChars.find(c => c.name === name);
      if (char) selectChar(char);
    });
  });
  const tiersBtn = wrap.querySelector('[data-pg-tiers]');
  if (tiersBtn) tiersBtn.addEventListener('click', showTierView);
}

// ── Livestream countdown strip ────────────────────────────
function renderLivestreamStrip() {
  const ls = livestreamData[currentGame];
  if (!ls || !ls.date) return '';
  const date = new Date(ls.date);
  if (isNaN(date.getTime())) return '';
  const now = Date.now();
  const ms = date.getTime() - now;
  if (ms < -1000 * 60 * 60 * 24) return ''; // hide if more than a day past

  let timerHtml = '';
  if (ms > 0) {
    const days = Math.floor(ms / 86400000);
    const hours = Math.floor((ms % 86400000) / 3600000);
    const mins = Math.floor((ms % 3600000) / 60000);
    timerHtml = `<div class="pg-livestream-timer">
      <div class="pg-timer-val"><span class="pg-timer-num">${days}</span><span class="pg-timer-unit">d</span></div>
      <div class="pg-timer-val"><span class="pg-timer-num">${String(hours).padStart(2,'0')}</span><span class="pg-timer-unit">h</span></div>
      <div class="pg-timer-val"><span class="pg-timer-num">${String(mins).padStart(2,'0')}</span><span class="pg-timer-unit">m</span></div>
    </div>`;
  } else {
    timerHtml = `<div class="pg-livestream-timer"><div class="pg-timer-val" style="background:rgba(63,185,80,0.15);border-color:#3fb950"><span class="pg-timer-num" style="color:#3fb950">LIVE</span></div></div>`;
  }

  const dateLabel = date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  const games = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
  const hlPills = (ls.highlights || []).slice(0, 3).map(h => `<span class="pg-livestream-hl-pill">${escHtml(h)}</span>`).join('');
  const link = ls.url ? `<a class="pg-livestream-link" href="${escHtml(ls.url)}" target="_blank" rel="noopener">Watch ↗</a>` : '';

  return `
    <div class="pg-livestream">
      <span class="pg-livestream-icon">
        <svg viewBox="0 0 16 16" fill="none"><rect x="1.5" y="3" width="13" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 6L10 8L6.5 10z" fill="currentColor"/></svg>
      </span>
      <div class="pg-livestream-info">
        <div class="pg-livestream-pre">Upcoming v${escHtml(ls.version)} Livestream</div>
        <div class="pg-livestream-name"><b>${escHtml(games[currentGame] || '')}</b>${ls.title ? ' · ' + escHtml(ls.title) : ''}</div>
        ${hlPills ? `<div class="pg-livestream-highlights">${hlPills}</div>` : `<div class="pg-livestream-time">${escHtml(dateLabel)}</div>`}
      </div>
      ${timerHtml}
      ${link}
    </div>
  `;
}

// ── Event calendar block ────────────────────────────────────
const EVENT_COLORS = {
  main:        '#22d3ee',
  combat:      '#f87171',
  exploration: '#3fb950',
  web:         '#a78bfa',
  login:       '#fbbf24',
  story:       '#67e8f9',
};
const EVENT_ICONS = {
  main:        '<svg viewBox="0 0 16 16" fill="none"><path d="M8 1.5l1.8 4 4.2.4-3.2 2.8 1 4.4L8 11.3 4.2 13.6l1-4.4L2 6.4l4.2-.4z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  combat:      '<svg viewBox="0 0 16 16" fill="none"><path d="M2.5 13.5l8-8 1.5 1.5-8 8zM10.5 5.5l3-3M2 14l1.5-1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  exploration: '<svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><path d="M5 8l2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  web:         '<svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12" stroke="currentColor" stroke-width="1.2"/></svg>',
  login:       '<svg viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3" width="11" height="10" rx="1.4" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 6h11M6 2v2M10 2v2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  story:       '<svg viewBox="0 0 16 16" fill="none"><path d="M3 2.5h7l3 3V14H3z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M10 2.5v3h3M5.5 8h5M5.5 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
};

function renderEventsBlock() {
  const events = (eventData[currentGame] || []).slice();
  if (!events.length) return '';
  const now = Date.now();
  const decorated = events.map(e => {
    const start = new Date(e.start).getTime();
    const end = new Date(e.end).getTime();
    return { ev: e, start, end,
      isLive: now >= start && now < end,
      isSoon: now < start,
      isEnded: now >= end,
    };
  }).filter(d => !d.isEnded);
  // Sort: live first (by end soonest), then upcoming (by start)
  decorated.sort((a, b) => {
    if (a.isLive && !b.isLive) return -1;
    if (!a.isLive && b.isLive) return 1;
    if (a.isLive) return a.end - b.end;
    return a.start - b.start;
  });

  let html = `<div class="pg-events">
    <div class="pg-events-head">
      <div class="pg-events-title">Event calendar</div>
      <span class="pg-events-count"><b>${decorated.length}</b> active</span>
    </div>`;
  if (!decorated.length) {
    html += `<div class="pg-event-empty">No events scheduled.</div>`;
  } else {
    html += '<div class="pg-events-list">';
    for (const d of decorated) {
      const e = d.ev;
      const type = (e.type || 'main').toLowerCase();
      const color = EVENT_COLORS[type] || '#8b949e';
      const icon = EVENT_ICONS[type] || EVENT_ICONS.main;
      let pillCls, pillText, whenText;
      if (d.isLive) {
        pillCls = 'live'; pillText = 'Live';
        const msLeft = d.end - now;
        if (msLeft < 86400000) {
          const h = Math.max(1, Math.ceil(msLeft / 3600000));
          whenText = `Ends in ${h}h`;
        } else {
          const daysLeft = Math.max(0, Math.ceil(msLeft / 86400000));
          whenText = `Ends in ${daysLeft}d`;
        }
      } else {
        pillCls = 'soon'; pillText = 'Upcoming';
        const daysUntil = Math.max(0, Math.ceil((d.start - now) / 86400000));
        whenText = `In ${daysUntil}d`;
      }
      const progress = d.isLive
        ? Math.max(0, Math.min(1, (now - d.start) / (d.end - d.start)))
        : 0;
      const barPct = (progress * 100).toFixed(1);
      const hasUrl = !!e.url;
      const tag = hasUrl ? 'a' : 'div';
      const attrs = hasUrl ? ` href="${escHtml(e.url)}" target="_blank" rel="noopener" style="text-decoration:none"` : '';
      html += `<${tag} class="pg-event" style="--e-color:${color}"${attrs}>
        <div class="pg-event-top">
          <span class="pg-event-icon">${icon}</span>
          <div class="pg-event-info">
            <div class="pg-event-name">${escHtml(e.name || '')}</div>
            ${e.tagline ? `<div class="pg-event-tagline">${escHtml(e.tagline)}</div>` : ''}
            ${e.rewards ? `<div class="pg-event-rewards">${escHtml(e.rewards)}</div>` : ''}
          </div>
          <div class="pg-event-status">
            <span class="pg-event-pill ${pillCls}">${pillText}</span>
            <span class="pg-event-when">${escHtml(whenText)}</span>
          </div>
        </div>
        <div class="pg-event-bar"><div class="pg-event-bar-fill" style="width:${barPct}%"></div></div>
      </${tag}>`;
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function switchGame(game) { _switchGameNoUrl(game); updateUrl(); }
function _switchGameNoUrl(game) {
  currentGame = game;
  allChars    = game === 'gi' ? giChars : game === 'hsr' ? hsrChars : zzzChars;
  activeChar  = null;

  document.querySelectorAll('.rail-game').forEach(t =>
    t.classList.toggle('active', t.dataset.game === game));
  document.body.classList.toggle('game-hsr', game === 'hsr');
  document.body.classList.toggle('game-zzz', game === 'zzz');
  document.body.classList.remove('viewing-char');
  $('back-btn').classList.add('hidden');

  $('char-view').classList.add('hidden');
  $('tier-view').classList.add('hidden');
  $('tier-btn').classList.remove('active');
  $('placeholder').classList.remove('hidden');
  filterElement = null;
  clearCompare();
  updateSourceCredit(game);
  renderElementFilters();
  updateGameLabel();
  refreshList();
  renderHighlights();
  updateLensState();
}

function updateGameLabel() {
  const names = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
  const nameEl = document.getElementById('game-name');
  const countEl = document.getElementById('game-count');
  if (nameEl) nameEl.textContent = names[currentGame] || '';
  if (countEl) countEl.textContent = allChars.length;
}

// ── list rendering ────────────────────────────────────────────
function releaseKey(char) {
  const entry = (releaseData[currentGame] || {})[char.name];
  if (!entry) return 0;
  if (entry.date) return new Date(entry.date).getTime();
  // fall back to numeric version comparison
  const v = parseFloat(entry.version || 0);
  return v * 1e10; // arbitrary large scale so it sorts after any real date
}

function releaseVersionLabel(char) {
  const entry = (releaseData[currentGame] || {})[char.name];
  return entry && entry.version ? entry.version : '';
}

function charElement(char) {
  if (currentGame === 'zzz') return char.element || '';
  return ((releaseData[currentGame] || {})[char.name] || {}).element || '';
}

function renderElementFilters() {
  const wrap = $('element-filter');
  wrap.innerHTML = '';

  const seen = new Set();
  allChars.forEach(c => { const e = charElement(c); if (e) seen.add(e); });
  if (seen.size === 0) return;

  const order = ELEMENT_ORDERS[currentGame] || [];
  const elems = order.filter(e => seen.has(e));

  const allBtn = document.createElement('button');
  allBtn.className = 'elem-btn' + (filterElement === null ? ' elem-btn-all' : '');
  allBtn.textContent = 'All';
  allBtn.addEventListener('click', () => { filterElement = null; renderElementFilters(); refreshList(); });
  wrap.appendChild(allBtn);

  elems.forEach(el => {
    const col = ELEMENT_COLORS[el];
    const isActive = filterElement === el;
    const btn = document.createElement('button');
    btn.className = 'elem-btn';
    btn.textContent = el;
    if (col) {
      const [idle, active, dark] = col;
      if (isActive) {
        btn.style.background = active;
        btn.style.borderColor = active;
        btn.style.color = dark ? '#111' : '#fff';
      } else {
        btn.style.borderColor = idle + '60';
        btn.style.color = idle;
      }
    }
    btn.addEventListener('click', () => {
      filterElement = filterElement === el ? null : el;
      renderElementFilters();
      refreshList();
    });
    wrap.appendChild(btn);
  });
}

// ── lens state (which sidebar mode is active) ─────────────────────
let favoritesOnly = false;
function toggleFavoritesLens() {
  favoritesOnly = !favoritesOnly;
  updateLensState();
  refreshList();
}
function clearLensViews() {
  // "Characters" lens click: close tier view if open, otherwise no-op
  if (!$('tier-view').classList.contains('hidden')) {
    $('tier-view').classList.add('hidden');
    $('tier-btn').classList.remove('active');
    document.body.classList.remove('viewing-char');
    $('back-btn').classList.add('hidden');
    $('placeholder').classList.remove('hidden');
  }
  updateLensState();
}
function updateLensState() {
  const tierActive = !$('tier-view').classList.contains('hidden');
  const charView = !$('char-view').classList.contains('hidden');
  document.querySelectorAll('.rail-lens').forEach(btn => {
    const lens = btn.dataset.lens;
    if (lens === 'tiers') btn.classList.toggle('active', tierActive);
    else if (lens === 'favorites') btn.classList.toggle('active', favoritesOnly);
    else if (lens === 'compare') btn.classList.toggle('active', !!compareChar);
    else if (lens === 'characters') btn.classList.toggle('active', !tierActive);
  });
}

function refreshList() {
  let list = [...allChars];
  if (filterElement) list = list.filter(c => charElement(c) === filterElement);
  const favSet = new Set(favorites[currentGame] || []);
  if (favoritesOnly) list = list.filter(c => favSet.has(c.name));
  list.sort((a, b) => releaseKey(b) - releaseKey(a));
  const pinned = favoritesOnly ? [] : list.filter(c => favSet.has(c.name));
  const rest = list.filter(c => !favSet.has(c.name));
  renderList(pinned, rest);
}

function renderList(pinned, rest) {
  const ul = $('char-list');
  ul.innerHTML = '';

  if (pinned && pinned.length) {
    const hdr = document.createElement('li');
    hdr.className = 'list-section-header';
    hdr.innerHTML = '<svg viewBox="0 0 16 16" fill="none" style="width:11px;height:11px"><path d="M8 2l1.8 4 4.2.4-3.2 2.8 1 4.4L8 11.3 4.2 13.6l1-4.4L2 6.4l4.2-.4z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg><span>Pinned</span><span class="group-count">' + pinned.length + '</span>';
    hdr.style.cursor = 'default';
    ul.appendChild(hdr);
    pinned.forEach(c => ul.appendChild(buildListItem(c, true)));
  }

  if (favoritesOnly || !filterElement) {
    // flat list sorted by release date (no filter = chronological; favorites = flat)
    rest.forEach(c => ul.appendChild(buildListItem(c, false)));
  } else {
    // element filter active — group by element
    const order = ELEMENT_ORDERS[currentGame] || [];
    const groups = new Map();
    for (const c of rest) {
      const el = charElement(c) || 'Other';
      if (!groups.has(el)) groups.set(el, []);
      groups.get(el).push(c);
    }
    // Sort group keys per game-defined order, unknown at end
    const groupKeys = [...groups.keys()].sort((a, b) => {
      const ia = order.indexOf(a), ib = order.indexOf(b);
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
    });
    for (const el of groupKeys) {
      const collapsed = isGroupCollapsed(el);
      const items = groups.get(el);
      const hdr = document.createElement('li');
      hdr.className = 'list-section-header' + (collapsed ? ' collapsed' : '');
      const col = ELEMENT_COLORS[el];
      const dotColor = col ? col[1] : 'var(--muted)';
      hdr.innerHTML =
        '<span class="group-dot" style="background:' + dotColor + ';color:' + dotColor + '"></span>' +
        '<span>' + escHtml(el) + '</span>' +
        '<span class="group-count">' + items.length + '</span>' +
        '<span class="group-chev">▾</span>';
      hdr.addEventListener('click', () => toggleGroup(el));
      ul.appendChild(hdr);
      if (!collapsed) {
        items.forEach(c => ul.appendChild(buildListItem(c, false)));
      }
    }
  }

  if (activeChar) highlightActive(activeChar);
  if (compareChar) highlightCompare(compareChar);
}

function buildListItem(char, isPinned) {
  const li = document.createElement('li');
  li.dataset.name = char.name + '|' + (char.path || '');
  li.addEventListener('click', (e) => {
    if (e.shiftKey && activeChar && activeChar.name !== char.name) {
      setCompareChar(char);
    } else {
      selectChar(char);
    }
  });

  const iconUrl = (icons[currentGame] || {})[char.name];
  if (iconUrl) {
    const img = document.createElement('img');
    img.className = 'li-icon';
    img.referrerPolicy = 'no-referrer';
    img.src = iconUrl;
    img.alt = '';
    li.appendChild(img);
  }

  const nameSpan = document.createElement('span');
  nameSpan.className = 'li-name';
  nameSpan.textContent = toTitle(char.name);

  const metaSpan = document.createElement('span');
  metaSpan.className = 'li-ver';
  const rdMeta = (releaseData[currentGame] || {})[char.name] || {};
  if (currentGame === 'gi') {
    const relVer = releaseVersionLabel(char);
    const parts = [rdMeta.element, relVer].filter(Boolean);
    metaSpan.textContent = parts.join(' · ');
  } else if (currentGame === 'hsr') {
    const relVer = releaseVersionLabel(char);
    const parts = [rdMeta.element, char.path, relVer].filter(Boolean);
    metaSpan.textContent = parts.join(' · ');
  } else {
    const relVer = releaseVersionLabel(char);
    const parts = [char.element, relVer].filter(Boolean);
    metaSpan.textContent = parts.join(' · ');
  }

  li.appendChild(nameSpan);

  // NEW dot for recent characters
  if (isRecentlyReleased(char)) {
    const dot = document.createElement('span');
    dot.className = 'li-status';
    dot.title = 'Released recently';
    li.appendChild(dot);
  }

  li.appendChild(metaSpan);

  const tier = charTier(char);
  if (tier) {
    const badge = document.createElement('span');
    badge.className = `tier-badge tier-${tier.replace('.', '_')}`;
    badge.textContent = tier;
    li.appendChild(badge);
  }

  // favorite star (hover/visible if pinned)
  const fav = document.createElement('button');
  fav.className = 'li-fav' + (isPinned ? ' active' : '');
  fav.innerHTML = '★';
  fav.title = isPinned ? 'Unpin' : 'Pin to top';
  fav.addEventListener('click', (e) => { e.stopPropagation(); toggleFavorite(char); });
  li.appendChild(fav);

  return li;
}

function isRecentlyReleased(char) {
  let dateStr = null;
  if (currentGame === 'hsr' && char.release_date) dateStr = char.release_date;
  else {
    const rd = (releaseData[currentGame] || {})[char.name];
    if (rd && rd.date) dateStr = rd.date;
  }
  if (!dateStr) return false;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return false;
  const diff = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 45;
}

function highlightActive(char) {
  const key = char.name + '|' + (char.path || '');
  document.querySelectorAll('#char-list li').forEach(li =>
    li.classList.toggle('active', li.dataset.name === key));
}

function renderCrumbs(char) {
  const games = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
  const gameEl = document.querySelector('#crumbs .crumb-game');
  const sectEl = document.querySelector('#crumbs .crumb-section');
  const curEl  = document.querySelector('#crumbs .crumb-current');
  if (!gameEl) return;
  const el = charElement(char);
  const col = ELEMENT_COLORS[el];
  const dotColor = col ? col[1] : 'var(--char-accent)';
  gameEl.innerHTML = '<span class="crumb-game-dot" style="background:' + dotColor + ';color:' + dotColor + '"></span>' + escHtml(games[currentGame] || '');
  let section = '';
  if (currentGame === 'hsr' && char.path) section = char.path;
  else if (currentGame === 'zzz' && char.specialty) section = char.specialty;
  else if (el) section = el;
  sectEl.textContent = section;
  curEl.textContent = toTitle(char.name);
}

// ── character view ────────────────────────────────────────────
function selectChar(char) { _selectCharNoUrl(char); updateUrl(); }
function _selectCharNoUrl(char) {
  // clear compare when selecting new primary
  if (compareChar && char.name !== compareChar.name) {
    // keep compare if explicit; otherwise clear
  }
  activeChar    = char;
  activeBuildIdx = 0;
  highlightActive(char);
  applyCharAccent(char);
  renderCrumbs(char);

  $('placeholder').classList.add('hidden');
  $('tier-view').classList.add('hidden');
  $('tier-btn').classList.remove('active');
  $('char-view').classList.remove('hidden');

  const nameEl = $('char-name');
  nameEl.textContent = toTitle(char.name);
  const detailTier = charTier(char);
  if (detailTier) {
    const badge = document.createElement('span');
    badge.className = `tier-badge tier-${detailTier.replace('.', '_')} char-tier-badge`;
    badge.textContent = detailTier;
    nameEl.appendChild(badge);
  }

  const portraitWrap = $('char-portrait-wrap');
  const portraitEl   = $('char-portrait');
  const portraitUrl  = (portraits[currentGame] || {})[char.name];
  if (portraitUrl) {
    portraitEl.src = portraitUrl;
    portraitWrap.classList.remove('hidden');
  } else {
    portraitEl.src = '';
    portraitWrap.classList.add('hidden');
  }

  // meta line: version for GI, path badge for HSR, specialty badge for ZZZ
  const meta = $('char-meta');
  if (currentGame === 'gi') {
    meta.textContent = char.last_updated || '';
  } else if (currentGame === 'hsr') {
    const pathHtml = char.path ? `<span class="path-badge">${char.path}</span>` : '';
    const dateHtml = char.release_date
      ? `<span class="release-date">${formatReleaseDate(char.release_date)}</span>`
      : '';
    meta.innerHTML = pathHtml + dateHtml;
  } else {
    const specHtml = char.specialty ? `<span class="path-badge">${char.specialty}</span>` : '';
    const verHtml  = char.last_updated ? `<span class="release-date">v${char.last_updated}</span>` : '';
    meta.innerHTML = specHtml + verHtml;
  }

  renderTabs(char);
  renderBuild(char, 0);
  renderRoleCallout(char, 0);
  renderNotes(char);

  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  $('content').scrollTop = 0;
  updateLensState();
}
function renderTabs(char) {
  const container = $('build-tabs');
  container.innerHTML = '';
  if (char.builds.length <= 1) return;

  char.builds.forEach((build, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    const label = build.role || build.role_name || '';
    btn.innerHTML = escHtml(label)
      + (build.recommended ? ' <span class="tab-star">✩</span>' : '');
    btn.addEventListener('click', () => {
      activeBuildIdx = i;
      container.querySelectorAll('.tab-btn').forEach((b, j) =>
        b.classList.toggle('active', j === i));
      renderBuild(char, i);
      renderRoleCallout(char, i);
      $('content').scrollTop = 0;
    });
    container.appendChild(btn);
  });
}

function renderBuild(char, idx) {
  const build = char.builds[idx];
  const panel = $('build-panel');
  if (!build) { panel.innerHTML = ''; return; }

  if (currentGame === 'gi') {
    renderGiBuild(build, panel);
  } else if (currentGame === 'hsr') {
    renderHsrBuild(char, build, panel);
  } else {
    renderZzzBuild(build, panel);
  }
}

function renderRoleCallout(char, idx) {
  const build = char.builds[idx];
  const callout = $('role-callout');
  const leftCards = $('left-cards');
  leftCards.innerHTML = '';
  if (!build || !build.role) {
    callout.classList.add('hidden');
    return;
  }
  callout.classList.remove('hidden');
  $('role-text').innerHTML = escHtml(build.role) +
    (build.recommended ? ' <span class="role-star">✩</span>' : '');
  const verEl = $('role-version');
  let verText = '';
  if (currentGame === 'gi') verText = char.last_updated || '';
  else if (currentGame === 'hsr') {
    const parts = [char.path, char.release_date ? formatReleaseDate(char.release_date) : ''].filter(Boolean);
    verText = parts.join(' · ');
  } else {
    const parts = [char.specialty, char.last_updated ? 'v' + char.last_updated : ''].filter(Boolean);
    verText = parts.join(' · ');
  }
  verEl.textContent = verText;
  $('role-status').innerHTML = statusPill(char);
  // left column extra cards: stat targets + pull priority
  let leftHtml = '';
  const targetText = build.baseline_stats || build.baseline || '';
  if (targetText) leftHtml += statTargetCard(targetText);
  if (currentGame === 'hsr' && char.recommended_baseline) {
    leftHtml += pullPriorityCard(char.recommended_baseline);
  }
  leftCards.innerHTML = leftHtml;
}

function renderGiBuild(build, panel) {
  panel.innerHTML = [
    itemCard('weapons', build.weapons, 'gi'),
    abilityCard('talent priority', build.talent_priority),
    itemCard('artifacts', build.artifacts, 'gi', true),
    card('main stats', build.main_stats),
    card('substats', build.substats, false, true),
    build.tips ? card('tips', build.tips, true) : '',
  ].join('');
}

function renderHsrBuild(char, build, panel) {
  const notesText = [build.relic_notes, build.other_notes].filter(Boolean).join('\n\n');
  panel.innerHTML = [
    itemCard('light cones', build.light_cones, 'hsr'),
    abilityCard('ability priority', build.ability_priority, build.ability_notes),
    hsrRelicCard(build),
    card('main stats', build.main_stats),
    card('sub stats', build.sub_stats, false, true),
    build.baseline_stats ? '' : '', // stat targets moved to left column
    build.eidolons ? card('notable eidolons', build.eidolons) : '',
    notesText ? card('notes', notesText, true) : '',
    hsrTeamCard(char),
  ].join('');
}

function hsrTeamCard(char) {
  const teams = char.example_teams;
  if (!teams || !teams.length) return '';
  let html = '<div class="build-card wide"><div class="card-label">' + sectionIcon('example teams') + '<span>example teams</span></div><div class="hsr-teams">';
  for (const team of teams) {
    html += '<div class="hsr-team-group">';
    if (team.label) {
      html += `<div class="hsr-team-label">${escHtml(team.label)}</div>`;
    }
    if (team.members && team.members.length) {
      html += '<div class="hsr-team-members team-thumbs">';
      for (const m of team.members) {
        html += teamMemberThumb('hsr', m);
      }
      html += '</div>';
    }
    html += '</div>';
  }
  html += '</div></div>';
  return html;
}

function renderZzzBuild(build, panel) {
  const discCard = zzzDiscCard(build);
  const teamCard = zzzTeamCard(build);
  const mainStatRows = parseStatGrid(build.main_stats || '', 'zzz');
  const mainStatContent = mainStatRows.length
    ? cardRaw('main stats', `<div class="stat-grid">${statGridRows(mainStatRows)}</div>`)
    : card('main stats', build.main_stats);
  panel.innerHTML = [
    itemCard('w-engines', build.w_engines, 'zzz'),
    build.w_engine_notes ? card('w-engine notes', build.w_engine_notes, true) : '',
    abilityCard('ability priority', build.ability),
    discCard,
    mainStatContent,
    card('sub stats', build.sub_stats),
    build.baseline ? '' : '', // stat targets moved to left column
    build.mindscapes ? card('mindscapes', build.mindscapes, true) : '',
    build.other_notes ? card('other notes', build.other_notes, true) : '',
    teamCard,
  ].join('');
}

// ── new render helpers ────────────────────────────────────────

function cardRaw(label, bodyHtml, wide = false) {
  if (!bodyHtml) return '';
  return `<div class="build-card${wide ? ' wide' : ''}"><div class="card-label">${sectionIcon(label)}<span>${label}</span></div>${bodyHtml}</div>`;
}

function parseItemList(text, game) {
  if (!text || !text.trim()) return [];
  const lines = text.trim().split('\n');
  const items = [];
  if (game === 'zzz') {
    let cur = null;
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      if (t.endsWith(':')) {
        if (cur) items.push(cur);
        cur = { rank: items.length + 1, name: t.slice(0, -1).trim(), desc: '', rarity: null };
      } else if (cur) {
        cur.desc += (cur.desc ? '\n' : '') + t;
        if (!cur.rarity) { const r = detectRarity(t); if (r) cur.rarity = r; }
      }
    }
    if (cur) items.push(cur);
  } else {
    let cur = null;
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      const nm = t.match(/^(\d+)\s*[.)\-]+\s*(.+)/);
      const em = !nm && t.match(/^[≈~]{1,2}\s*(.+)/);
      if (nm) {
        if (cur) items.push(cur);
        const name = nm[2].trim();
        cur = { rank: parseInt(nm[1]), name, desc: '', rarity: detectRarity(name) };
      } else if (em) {
        if (cur) items.push(cur);
        const name = em[1].trim();
        cur = { rank: 0, name, desc: '', rarity: detectRarity(name) };
      } else if (cur) {
        cur.desc += (cur.desc ? '\n' : '') + t;
      }
    }
    if (cur) items.push(cur);
  }
  for (const it of items) {
    it.displayName = it.name
      .replace(/\s*\(\d\s*[✩★⭐]\)\s*/g, '')
      .replace(/\s*\[R\d\]\s*/gi, '')
      .replace(/\s*\*+$/, '')
      .trim();
    it.trailingStar = /\*$/.test(it.name);
  }
  return items;
}

function normalizeItemName(name) {
  return name
    .replace(/\s*\d+[★✩⭐]\s*$/, '')
    .replace(/\s*\[[^\]]*\]\s*$/, '')
    .replace(/\s*[¹²³⁴⁵⁶⁷⁸⁹]+\s*$/, '')
    .replace(/\s+\d+\s*$/, '')
    .replace(/^\d+-?PC:\s*/i, '')
    .replace(/\s*\(\d+\).*$/, '')
    .trim();
}

function lookupItemIcon(game, name) {
  const cleaned = normalizeItemName(name);
  return (itemIcons[game] || {})[cleaned] || null;
}

function itemImgHtml(url, cls = 'item-icon') {
  if (!url) return '';
  return `<img class="${cls}" src="${escHtml(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
}

function itemListHtml(items, game) {
  if (!items.length) return '';
  return '<div class="item-list">' + items.map(item => {
    const cls = item.rank === 1 ? ' tier-1' : item.rank === 2 ? ' tier-2' : item.rank === 0 ? ' tier-eq' : '';
    const rarityCls = item.rarity ? ` rarity-${item.rarity}` : '';
    const label = item.rank === 0 ? '≈' : item.rank;
    const star = item.trailingStar ? '<sup class="item-foot">*</sup>' : '';
    const display = item.displayName || item.name;
    const iconUrl = game ? lookupItemIcon(game, display) : null;
    const nameHtml = `<span class="item-name-wrap">${itemImgHtml(iconUrl)}<span class="item-pill${rarityCls}${cls}">${escHtml(display)}</span>${star}</span>`;
    const descHtml = item.desc ? `<div class="item-desc">${escHtml(item.desc)}</div>` : '';
    return `<div class="item-row"><span class="item-rank">${label}</span><div class="item-body">${nameHtml}${descHtml}</div></div>`;
  }).join('') + '</div>';
}

function itemCard(label, text, game, wide = false) {
  if (!text || !text.trim()) return '';
  const items = parseItemList(text, game);
  if (!items.length) return card(label, text, wide, true);
  return cardRaw(label, `<div class="card-body">${itemListHtml(items, game)}</div>`, wide);
}

function parseAbilityPriority(text) {
  if (!text || !text.trim()) return [];
  const nodes = [];
  const seen = new Set();
  let currentRank = 0;
  let seenHighRank = false;

  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t) continue;
    const numM = t.match(/^(\d+)\s*[.)]+\s*(.+)/);
    const eqM  = !numM && t.match(/^[≈~>=]+\s*(.+)/);
    let name = null, rank = 0, isEquiv = false;
    if (numM) {
      rank = parseInt(numM[1]);
      name = numM[2].trim();
      // Stop when the rank resets to 1 after a full sequence (duplicate block or mixed stats)
      if (rank === 1 && seenHighRank) break;
      if (rank > 1) seenHighRank = true;
      currentRank = rank;
    } else if (eqM) {
      name = eqM[1].trim();
      isEquiv = true;
      rank = currentRank;
    }
    if (name && name.length <= 35 && !seen.has(name)) {
      seen.add(name);
      nodes.push({ name, rank, isEquiv });
    }
  }
  return nodes;
}

function abilityChainHtml(nodes) {
  if (!nodes.length) return '';
  return '<div class="ability-chain">' + nodes.map((n, i) => {
    const cls = n.rank === 1 ? ' tier-1' : n.rank === 2 ? ' tier-2' : '';
    const next = nodes[i + 1];
    const sep = next
      ? (next.isEquiv ? '<span class="ability-arrow">≈</span>' : '<span class="ability-arrow">→</span>')
      : '';
    return `<span class="ability-node${cls}">${escHtml(n.name)}</span>${sep}`;
  }).join('') + '</div>';
}

function abilityCard(label, text, notes) {
  if (!text || !text.trim()) return '';
  const nodes = parseAbilityPriority(text);
  let effectiveNotes = notes;
  if (!effectiveNotes) {
    const prose = text.split('\n')
      .map(l => l.trim())
      .filter(t => t && !/^(\d+)\s*[.)]+\s*/.test(t) && !/^[≈~>=]+\s*/.test(t));
    if (prose.length) effectiveNotes = prose.join('\n');
  }
  const noteHtml = effectiveNotes ? `<p class="ability-note">${escHtml(effectiveNotes)}</p>` : '';
  if (!nodes.length) return cardRaw(label, `<div class="card-body">${escHtml(text)}</div>`);
  return cardRaw(label, abilityChainHtml(nodes) + noteHtml);
}

function parseHsrSets(text) {
  if (!text || !text.trim()) return [];
  const sets = [];
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t) continue;
    const nm = t.match(/^(\d+)\s*[.)\-]+\s*(.+)/);
    const em = !nm && t.match(/^[≈~]{1,2}\s*(.+)/);
    let name = nm ? nm[2].trim() : em ? em[1].trim() : null;
    if (!name) continue;
    name = name.replace(/^\d-PC:\s*/i, '');
    name = name.replace(/\s*[¹²³⁴-⁹]+\s*$/, '').trim();
    if (name) sets.push(name);
  }
  return sets;
}

function hsrRelicCard(build) {
  const sets4 = parseHsrSets(build.relic_4pc || '');
  const sets2 = parseHsrSets(build.planar_ornament || '');
  if (!sets4.length && !sets2.length) return '';
  let html = '<div class="build-card wide"><div class="card-label">' + sectionIcon('relics') + '<span>relics</span></div><div class="disc-sets">';
  if (sets4.length) {
    html += '<div class="disc-row"><span class="disc-pc-label">4PC</span>'
      + sets4.map((s, i) => {
          const icon = itemImgHtml(lookupItemIcon('hsr', s), 'disc-icon');
          return `<span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${icon}${escHtml(s)}</span>`;
        }).join('')
      + '</div>';
  }
  if (sets2.length) {
    html += '<div class="disc-row"><span class="disc-pc-label">2PC</span>'
      + sets2.map((s, i) => {
          const icon = itemImgHtml(lookupItemIcon('hsr', s), 'disc-icon');
          return `<span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${icon}${escHtml(s)}</span>`;
        }).join('')
      + '</div>';
  }
  html += '</div></div>';
  return html;
}

function parseStatGrid(text, game) {
  if (!text || !text.trim()) return [];
  const rows = [];
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t) continue;
    if (game === 'zzz') {
      const m = t.match(/^(.+?)\s+((?:disc)\s*\d+)\s*$/i);
      rows.push(m ? { slot: m[2].trim(), stat: m[1].trim() } : { slot: '', stat: t });
    } else {
      rows.push({ slot: '', stat: t });
    }
  }
  return rows;
}

function statGridRows(rows) {
  return rows.map(r =>
    r.slot
      ? `<span class="stat-slot">${escHtml(r.slot)}</span><span class="stat-val">${escHtml(r.stat)}</span>`
      : `<span class="stat-full">${escHtml(r.stat)}</span>`
  ).join('');
}

// ── ZZZ disc drive sets ──────────────────────────────────────

function zzzDiscCard(build) {
  const has4 = build.disc_4pc && build.disc_4pc.length;
  const has2 = build.disc_2pc && build.disc_2pc.length;
  const hasNotes = build.disc_notes && build.disc_notes.trim();
  if (!has4 && !has2 && !hasNotes) return '';

  let html = '<div class="build-card wide"><div class="card-label">' + sectionIcon('drive discs') + '<span>drive discs</span></div>';

  if (has4 || has2) {
    html += '<div class="disc-sets">';
    if (has4) {
      const labels4 = build.disc_4pc_labels || [];
      html += '<div class="disc-row">'
        + '<span class="disc-pc-label">4PC</span>'
        + build.disc_4pc.map((s, i) => {
            const icon = itemImgHtml(lookupItemIcon('zzz', s), 'disc-icon');
            const lbl = labels4[i] ? `<span class="disc-chip-label">${escHtml(labels4[i])}</span>` : '';
            return `<span class="disc-chip-wrap"><span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${icon}${escHtml(s)}</span>${lbl}</span>`;
          }).join('')
        + '</div>';
    }
    if (has2) {
      const labels2 = build.disc_2pc_labels || [];
      html += '<div class="disc-row">'
        + '<span class="disc-pc-label">2PC</span>'
        + build.disc_2pc.map((s, i) => {
            const lbl = labels2[i] ? `<span class="disc-chip-label">${escHtml(labels2[i])}</span>` : '';
            if (Array.isArray(s)) {
              return '<span class="disc-chip-wrap"><span class="disc-pair-group">'
                + s.map(name => {
                    const icon = itemImgHtml(lookupItemIcon('zzz', name), 'disc-icon');
                    return `<span class="disc-chip">${icon}${escHtml(name)}</span>`;
                  }).join('<span class="disc-pair-sep">/</span>')
                + `</span>${lbl}</span>`;
            }
            const icon2pc = itemImgHtml(lookupItemIcon('zzz', s), 'disc-icon');
            return `<span class="disc-chip-wrap"><span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${icon2pc}${escHtml(s)}</span>${lbl}</span>`;
          }).join('')
        + '</div>';
    }
    html += '</div>';
  }

  if (hasNotes) {
    html += `<div class="disc-notes-body">${escHtml(build.disc_notes)}</div>`;
  }

  html += '</div>';
  return html;
}

const ZZZ_SHORT = {
  'Soldier 11':      'S11',
  'Anby: Soldier 0': 'S0-Anby',
  'Jane Doe':        'Jane',
  'Orphie & Magus':  'Orphie',
  'Astra Yao':       'Astra',
  'Nangong Yu':      'Nangong',
  'Zhu Yuan':        'Zhu Yuan',
};

function zzzShortName(n) {
  return ZZZ_SHORT[n] || n.replace(/\s*\(.*?\)\s*/g, '').trim().split(' ').pop();
}

function zzzTeamCard(build) {
  const hasComps = build.team_comps && build.team_comps.length;
  const hasGeneral = build.team_general && build.team_general.trim();
  if (!hasComps && !hasGeneral) return '';

  let html = '<div class="build-card wide"><div class="card-label">' + sectionIcon('team comps') + '<span>team comps</span></div>';

  if (hasGeneral) {
    html += `<div class="card-body" style="margin-bottom:${hasComps ? '12px' : '0'}">${escHtml(build.team_general)}</div>`;
  }

  if (hasComps) {
    const isStructured = typeof build.team_comps[0] === 'object';
    if (isStructured) {
      html += '<div class="team-rows">';
      for (const team of build.team_comps) {
        html += '<div class="team-row">';
        html += `<span class="team-chip">${escHtml(team.label)}</span>`;
        if (team.chars && team.chars.length) {
          html += '<span class="team-thumbs">';
          for (const c of team.chars) {
            html += teamMemberThumb('zzz', c);
          }
          html += '</span>';
        }
        html += '</div>';
      }
      html += '</div>';
    } else {
      html += '<div class="team-chips">'
        + build.team_comps.map(t => `<span class="team-chip">${escHtml(t)}</span>`).join('')
        + '</div>';
    }
  }

  html += '</div>';
  return html;
}

function renderNotes(char) {
  const details  = $('notes-details');
  const body     = $('notes-body');
  const summary  = details.querySelector('summary');

  if (currentGame === 'gi' && char.notes && char.notes.trim()) {
    if (summary) summary.textContent = 'notes';
    details.classList.remove('hidden');
    body.textContent = char.notes;
    details.removeAttribute('open');
  } else if (currentGame === 'hsr' && char.kit_overview && char.kit_overview.trim()) {
    if (summary) summary.textContent = 'kit overview';
    details.classList.remove('hidden');
    body.textContent = char.kit_overview;
    details.removeAttribute('open');
  } else {
    details.classList.add('hidden');
  }
}

// ── in-browser build editing ──────────────────────────────────
let _pickerDragSrc = null;  // {listEl, idx} during a drag
const _pickerPoolCache = {}; // poolKey → [{name, url}]

const EDIT_FIELDS = {
  gi: {
    buildFields: [
      { key: 'role',            label: 'Role',            multi: false },
      { key: 'weapons',         label: 'Weapons',         multi: true,  picker: 'gi-weapons'   },
      { key: 'artifacts',       label: 'Artifacts',       multi: true,  picker: 'gi-artifacts' },
      { key: 'main_stats',      label: 'Main Stats',      multi: true  },
      { key: 'substats',        label: 'Substats',        multi: true  },
      { key: 'talent_priority', label: 'Talent Priority', multi: true  },
      { key: 'tips',            label: 'Tips',            multi: true  },
    ],
    charFields: [
      { key: 'notes',        label: 'Notes',        multi: true  },
      { key: 'last_updated', label: 'Last Updated', multi: false },
    ],
  },
  hsr: {
    buildFields: [
      { key: 'role',             label: 'Role',             multi: false },
      { key: 'light_cones',      label: 'Light Cones',      multi: true,  picker: 'hsr-lc'      },
      { key: 'relic_4pc',        label: 'Relic 4pc',        multi: false, picker: 'hsr-relics'  },
      { key: 'planar_ornament',  label: 'Planar Ornament',  multi: false, picker: 'hsr-planars' },
      { key: 'main_stats',       label: 'Main Stats',       multi: true  },
      { key: 'sub_stats',        label: 'Sub Stats',        multi: true  },
      { key: 'ability_priority', label: 'Ability Priority', multi: true  },
      { key: 'ability_notes',    label: 'Ability Notes',    multi: false },
      { key: 'eidolons',         label: 'Eidolons',         multi: true  },
      { key: 'relic_notes',      label: 'Relic Notes',      multi: true  },
      { key: 'other_notes',      label: 'Other Notes',      multi: true  },
      { key: 'baseline_stats',   label: 'Baseline Stats',   multi: false },
    ],
    charFields: [
      { key: 'kit_overview',         label: 'Kit Overview',         multi: true  },
      { key: 'worth_pulling',        label: 'Worth Pulling',        multi: true  },
      { key: 'recommended_baseline', label: 'Recommended Baseline', multi: false },
    ],
  },
  zzz: {
    buildFields: [
      { key: 'role',           label: 'Role',           multi: false },
      { key: 'w_engines',      label: 'W-Engines',      multi: true,  picker: 'zzz-engines' },
      { key: 'disc_sets',      label: 'Drive Discs',    multi: false, picker: 'zzz-discs'   },
      { key: 'main_stats',     label: 'Main Stats',     multi: true  },
      { key: 'sub_stats',      label: 'Sub Stats',      multi: false },
      { key: 'ability',        label: 'Ability',        multi: true  },
      { key: 'disc_notes',     label: 'Disc Notes',     multi: true  },
      { key: 'w_engine_notes', label: 'W-Engine Notes', multi: true  },
      { key: 'mindscapes',     label: 'Mindscapes',     multi: true  },
      { key: 'other_notes',    label: 'Other Notes',    multi: true  },
      { key: 'baseline',       label: 'Baseline',       multi: false },
    ],
    charFields: [
      { key: 'last_updated', label: 'Last Updated', multi: false },
    ],
  },
};

// ── item picker helpers ───────────────────────────────────────

function getPickerPool(poolKey) {
  if (_pickerPoolCache[poolKey]) return _pickerPoolCache[poolKey];
  let entries = [];
  const gi  = itemIcons.gi  || {};
  const hsr = itemIcons.hsr || {};
  const zzz = itemIcons.zzz || {};
  if (poolKey === 'gi-weapons')   entries = Object.entries(gi).filter(([,u]) =>  u.includes('/Weapon_'));
  if (poolKey === 'gi-artifacts') entries = Object.entries(gi).filter(([,u]) =>  u.includes('/Item_'));
  if (poolKey === 'hsr-lc')       entries = Object.entries(hsr).filter(([,u]) => u.includes('/Light_Cone_'));
  if (poolKey === 'hsr-relics')   entries = Object.entries(hsr).filter(([,u]) => u.includes('/Item_'));
  if (poolKey === 'hsr-planars')  entries = Object.entries(hsr).filter(([,u]) => u.includes('/Item_'));
  if (poolKey === 'zzz-engines')  entries = Object.entries(zzz).filter(([,u]) => u.includes('/W-Engine_') || u.includes('/W-engine_'));
  if (poolKey === 'zzz-discs')    entries = Object.entries(zzz).filter(([,u]) => !u.includes('/W-Engine_') && !u.includes('/W-engine_'));
  const pool = entries.map(([name, url]) => ({ name, url })).sort((a, b) => a.name.localeCompare(b.name));
  _pickerPoolCache[poolKey] = pool;
  return pool;
}

function deserializePickerItems(text, poolKey, fieldKey) {
  if (!text || !text.trim()) return [];
  const pool = getPickerPool(poolKey);
  const poolNames = new Set(pool.map(p => p.name));
  const items = parseItemList(text, fieldKey === 'w_engines' ? 'zzz' : 'gi');
  return items.map(it => {
    const clean = normalizeItemName(it.displayName || it.name);
    if (poolNames.has(clean)) {
      return { name: clean, equiv: it.rank === 0, note: (it.desc || '').trim() };
    }
    return { name: null, raw: it.displayName || it.name, equiv: it.rank === 0, note: '' };
  });
}

function serializePickerItems(items, fieldKey) {
  let rank = 0;
  return items.map(item => {
    const n = item.name || item.raw || '';
    if (fieldKey === 'w_engines') {
      const noteLines = item.note ? '\n' + item.note : '';
      return `${n}:${noteLines}`;
    }
    if (item.equiv) return `≈ ${n}`;
    rank++;
    if (fieldKey === 'artifacts') return `${rank}. ${n} (4)`;
    return `${rank}. ${n}`;
  }).join('\n');
}

function pickerItemsFromDiscBuild(build) {
  const items4 = (build.disc_4pc || []).map((n, i) => ({
    name: n, label: (build.disc_4pc_labels || [])[i] || ''
  }));
  const items2 = (build.disc_2pc || []).map((n, i) => {
    if (Array.isArray(n)) return { name: n.join(' / '), label: (build.disc_2pc_labels || [])[i] || '', paired: true };
    return { name: n, label: (build.disc_2pc_labels || [])[i] || '' };
  });
  return { items4, items2 };
}

function syncDiscHiddenInputs(editorEl) {
  const items4 = [], labels4 = [], items2 = [], labels2 = [];
  editorEl.querySelectorAll('.disc-picker-row[data-section="4pc"]').forEach(row => {
    items4.push(row.dataset.name);
    labels4.push(row.querySelector('.disc-picker-label-input')?.value || '');
  });
  editorEl.querySelectorAll('.disc-picker-row[data-section="2pc"]').forEach(row => {
    items2.push(row.dataset.name);
    labels2.push(row.querySelector('.disc-picker-label-input')?.value || '');
  });
  const set = (field, val) => {
    const el = editorEl.querySelector(`[data-field="${field}"]`);
    if (el) el.value = JSON.stringify(val);
  };
  set('disc_4pc', items4); set('disc_4pc_labels', labels4);
  set('disc_2pc', items2); set('disc_2pc_labels', labels2);
}

function renderPickerRowHtml(item, idx, fieldKey) {
  const isEngine = fieldKey === 'w_engines';
  const isRaw = item.name === null;
  const displayName = isRaw ? (item.raw || '') : item.name;
  const poolGame = (fieldKey === 'w_engines') ? 'zzz'
    : (fieldKey === 'light_cones' || fieldKey === 'relic_4pc' || fieldKey === 'planar_ornament') ? 'hsr'
    : 'gi';
  const iconHtml = (!isRaw && item.name && lookupItemIcon(poolGame, item.name))
    ? itemImgHtml(lookupItemIcon(poolGame, item.name), 'picker-row-icon')
    : '<span class="picker-row-icon picker-no-icon"></span>';
  const rankLabel = item.equiv ? '≈' : '';
  const equivActive = item.equiv ? ' active' : '';
  let noteHtml = '';
  if (isEngine) {
    const noteVal = escHtml(item.note || '');
    noteHtml = `<textarea class="picker-item-note" placeholder="Notes (optional)">${noteVal}</textarea>`;
  }
  const rawClass = isRaw ? ' picker-row-raw' : '';
  return `<div class="picker-row${rawClass}${item.equiv ? ' equiv' : ''}" draggable="true" data-idx="${idx}" data-equiv="${item.equiv}" data-raw="${isRaw}">
  <span class="picker-drag-handle" title="Drag to reorder">⠿</span>
  <span class="picker-rank">${rankLabel || (item.equiv ? '≈' : '')}</span>
  ${iconHtml}
  <span class="picker-row-name">${escHtml(displayName)}</span>
  ${!isRaw ? `<button class="picker-equiv-btn${equivActive}" title="Mark as equivalent (≈)">≈</button>` : ''}
  <button class="picker-remove-btn" title="Remove">✕</button>
  ${noteHtml}
</div>`;
}

function renderPickerField(f, val, bi, game) {
  const pool = getPickerPool(f.picker);
  const items = deserializePickerItems(val, f.picker, f.key);

  const pickerGame = f.picker === 'zzz-engines' ? 'zzz' : f.picker.startsWith('hsr') ? 'hsr' : 'gi';

  const selectedHtml = items.length
    ? items.map((it, i) => renderPickerRowHtml(it, i, f.key)).join('')
    : '<div class="picker-empty-hint">No items selected — add from the list below.</div>';

  const tilesHtml = pool.map(p => {
    const inUse = items.some(it => it.name === p.name);
    return `<button class="picker-tile${inUse ? ' in-use' : ''}" data-name="${escHtml(p.name)}" title="${escHtml(p.name)}">
      <img class="picker-tile-icon" src="${escHtml(p.url)}" alt="" loading="lazy" referrerpolicy="no-referrer">
      <span class="picker-tile-name">${escHtml(p.name)}</span>
    </button>`;
  }).join('');

  const hiddenVal = escHtml(val);
  const pid = `picker-${bi}-${f.key}`;

  return `<div class="picker-editor" id="${pid}" data-pool="${f.picker}" data-field-key="${f.key}" data-game="${pickerGame}">
  <div class="picker-selected">
    <div class="picker-selected-header">Selected</div>
    <div class="picker-list">${selectedHtml}</div>
  </div>
  <div class="picker-pool">
    <input class="picker-search" placeholder="Search ${escHtml(f.label.toLowerCase())}…" autocomplete="off">
    <div class="picker-grid">${tilesHtml}</div>
  </div>
  <button class="picker-manual-link">Edit manually</button>
</div>
<textarea class="edit-textarea picker-hidden-ta" data-build="${bi}" data-field="${escHtml(f.key)}" rows="1">${hiddenVal}</textarea>`;
}

function renderDiscPickerField(build, bi) {
  const pool = getPickerPool('zzz-discs');
  const { items4, items2 } = pickerItemsFromDiscBuild(build);

  function discRowHtml(item, section) {
    const icon = itemImgHtml(lookupItemIcon('zzz', item.name), 'picker-row-icon');
    return `<div class="disc-picker-row picker-row" draggable="true" data-name="${escHtml(item.name)}" data-section="${section}">
  <span class="picker-drag-handle">⠿</span>
  ${icon}
  <span class="picker-row-name">${escHtml(item.name)}</span>
  <input class="disc-picker-label-input" type="text" placeholder="Label (e.g. BIS)" value="${escHtml(item.label)}">
  <button class="picker-remove-btn" title="Remove">✕</button>
</div>`;
  }

  function tilesHtml(usedNames) {
    return pool.map(p => {
      const inUse = usedNames.includes(p.name);
      return `<button class="picker-tile${inUse ? ' in-use' : ''}" data-name="${escHtml(p.name)}" title="${escHtml(p.name)}">
        <img class="picker-tile-icon" src="${escHtml(p.url)}" alt="" loading="lazy" referrerpolicy="no-referrer">
        <span class="picker-tile-name">${escHtml(p.name)}</span>
      </button>`;
    }).join('');
  }

  const used4 = items4.map(i => i.name);
  const used2 = items2.filter(i => !i.paired).map(i => i.name);

  return `<div class="picker-editor disc-picker-editor" data-pool="zzz-discs" data-field-key="disc_sets">
  <div class="disc-picker-section">
    <div class="disc-picker-section-head">4PC Sets</div>
    <div class="picker-list picker-list-4pc">${items4.map(i => discRowHtml(i, '4pc')).join('') || '<div class="picker-empty-hint">No 4pc sets selected.</div>'}</div>
    <div class="picker-pool">
      <input class="picker-search" placeholder="Search disc sets…" autocomplete="off">
      <div class="picker-grid">${tilesHtml(used4)}</div>
    </div>
  </div>
  <div class="disc-picker-section">
    <div class="disc-picker-section-head">2PC Sets</div>
    <div class="picker-list picker-list-2pc">${items2.filter(i => !i.paired).map(i => discRowHtml(i, '2pc')).join('') || '<div class="picker-empty-hint">No 2pc sets selected.</div>'}</div>
    <div class="picker-pool">
      <input class="picker-search" placeholder="Search disc sets…" autocomplete="off">
      <div class="picker-grid">${tilesHtml(used2)}</div>
    </div>
  </div>
  <input type="hidden" data-build="${bi}" data-field="disc_4pc"        value="${escHtml(JSON.stringify(used4))}">
  <input type="hidden" data-build="${bi}" data-field="disc_4pc_labels" value="${escHtml(JSON.stringify(items4.map(i => i.label)))}">
  <input type="hidden" data-build="${bi}" data-field="disc_2pc"        value="${escHtml(JSON.stringify(used2))}">
  <input type="hidden" data-build="${bi}" data-field="disc_2pc_labels" value="${escHtml(JSON.stringify(items2.filter(i => !i.paired).map(i => i.label)))}">
</div>`;
}

function renderEditView(char) {
  const schema = EDIT_FIELDS[currentGame];
  if (!schema) return;
  const panel = $('char-right');
  const isOverridden = !!(buildOverrides[currentGame] || {})[char.name];
  const PENCIL = `<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M11 2.5L13.5 5L5.5 13H3V10.5L11 2.5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9.5 4L12 6.5" stroke="currentColor" stroke-width="1.4"/></svg>`;

  let html = `<div class="edit-view">`;
  html += `<div class="edit-header">`;
  html += `<span class="edit-title">${PENCIL} editing ${escHtml(toTitle(char.name))}</span>`;
  html += `<div class="edit-actions">`;
  if (isOverridden) {
    html += `<button class="edit-btn edit-btn-reset" id="edit-reset-btn">Reset to default</button>`;
  }
  html += `<button class="edit-btn edit-btn-export" id="edit-export-btn">Export JSON</button>`;
  html += `<button class="edit-btn edit-btn-cancel" id="edit-cancel-btn">Cancel</button>`;
  html += `<button class="edit-btn edit-btn-save" id="edit-save-btn">Save</button>`;
  html += `</div></div>`;

  if (workerConfigured()) {
    html += `<div id="edit-sync-status" class="edit-sync-status"></div>`;
  } else {
    html += `<div class="edit-sync-no-token">No sync configured — edits save locally only. <button class="edit-sync-config-btn" id="edit-open-sync">Configure sync →</button></div>`;
  }

  char.builds.forEach((build, bi) => {
    const roleLabel = build.role || `Build ${bi + 1}`;
    html += `<div class="edit-section">`;
    html += `<div class="edit-section-head">Build: ${escHtml(roleLabel)}</div>`;
    for (const f of schema.buildFields) {
      if (f.picker === 'zzz-discs') {
        html += `<div class="edit-field"><label class="edit-label">${escHtml(f.label)}</label>`;
        html += renderDiscPickerField(build, bi);
        html += `</div>`;
        continue;
      }
      if (f.picker) {
        const val = build[f.key] ?? '';
        html += `<div class="edit-field"><label class="edit-label">${escHtml(f.label)}</label>`;
        html += renderPickerField(f, val, bi, currentGame);
        html += `</div>`;
        continue;
      }
      const val = build[f.key] ?? '';
      html += `<div class="edit-field"><label class="edit-label">${escHtml(f.label)}</label>`;
      if (f.multi) {
        const rows = Math.max(2, val.split('\n').length + 1);
        html += `<textarea class="edit-textarea" data-build="${bi}" data-field="${escHtml(f.key)}" rows="${rows}">${escHtml(val)}</textarea>`;
      } else {
        html += `<input class="edit-input" type="text" data-build="${bi}" data-field="${escHtml(f.key)}" value="${escHtml(val)}">`;
      }
      html += `</div>`;
    }
    html += `</div>`;
  });

  if (schema.charFields.length) {
    html += `<div class="edit-section">`;
    html += `<div class="edit-section-head">Character</div>`;
    for (const f of schema.charFields) {
      const val = char[f.key] ?? '';
      html += `<div class="edit-field"><label class="edit-label">${escHtml(f.label)}</label>`;
      if (f.multi) {
        const rows = Math.max(2, val.split('\n').length + 1);
        html += `<textarea class="edit-textarea" data-build="" data-field="${escHtml(f.key)}" rows="${rows}">${escHtml(val)}</textarea>`;
      } else {
        html += `<input class="edit-input" type="text" data-build="" data-field="${escHtml(f.key)}" value="${escHtml(val)}">`;
      }
      html += `</div>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  panel.innerHTML = html;

  $('edit-cancel-btn').addEventListener('click', () => _selectCharNoUrl(activeChar));
  $('edit-save-btn').addEventListener('click', () => saveEditView(char));
  $('edit-export-btn').addEventListener('click', exportBuilds);
  const resetBtn = $('edit-reset-btn');
  if (resetBtn) resetBtn.addEventListener('click', () => resetCharEdit(char));
  const openSyncBtn = $('edit-open-sync');
  if (openSyncBtn) openSyncBtn.addEventListener('click', openSyncModal);

  panel.querySelectorAll('.picker-editor:not(.disc-picker-editor)').forEach(el => initPickerField(el));
  panel.querySelectorAll('.picker-editor.disc-picker-editor').forEach(el => initDiscPickerField(el));
}

// ── picker interaction logic ──────────────────────────────────

function getPickerItems(editorEl) {
  const fieldKey  = editorEl.dataset.fieldKey;
  const poolKey   = editorEl.dataset.pool;
  const listEl    = editorEl.querySelector('.picker-list');
  const items     = [];
  listEl.querySelectorAll('.picker-row').forEach(row => {
    const isRaw  = row.dataset.raw === 'true';
    const equiv  = row.dataset.equiv === 'true';
    const name   = isRaw ? null : row.querySelector('.picker-row-name').textContent;
    const raw    = isRaw ? row.querySelector('.picker-row-name').textContent : null;
    const noteEl = row.querySelector('.picker-item-note');
    const note   = noteEl ? noteEl.value : '';
    items.push(isRaw ? { name: null, raw, equiv, note } : { name, equiv, note });
  });
  return items;
}

function syncPickerHiddenTextarea(editorEl) {
  const fieldKey = editorEl.dataset.fieldKey;
  const items    = getPickerItems(editorEl);
  const ta       = editorEl.parentElement.querySelector('.picker-hidden-ta');
  if (ta) ta.value = serializePickerItems(items, fieldKey);
}

function reRenderPickerList(editorEl, items) {
  const fieldKey = editorEl.dataset.fieldKey;
  const poolKey  = editorEl.dataset.pool;
  const listEl   = editorEl.querySelector('.picker-list');

  // Compute sequential ranks for rank labels
  let rank = 0;
  listEl.innerHTML = items.length
    ? items.map((item, i) => {
        const html = renderPickerRowHtml(item, i, fieldKey);
        if (!item.equiv) rank++;
        return html;
      }).join('')
    : '<div class="picker-empty-hint">No items selected — add from the list below.</div>';

  // Update rank labels after render (numbers need sequential counting)
  let r = 0;
  listEl.querySelectorAll('.picker-row').forEach(row => {
    const equiv = row.dataset.equiv === 'true';
    const rankEl = row.querySelector('.picker-rank');
    if (rankEl) rankEl.textContent = equiv ? '≈' : ++r;
  });

  // Update in-use state on tiles
  const usedNames = new Set(items.filter(i => i.name).map(i => i.name));
  editorEl.querySelectorAll('.picker-tile').forEach(tile => {
    tile.classList.toggle('in-use', usedNames.has(tile.dataset.name));
  });

  rewirePickerRowEvents(editorEl);
  syncPickerHiddenTextarea(editorEl);
}

function rewirePickerRowEvents(editorEl) {
  const listEl   = editorEl.querySelector('.picker-list');
  const fieldKey = editorEl.dataset.fieldKey;

  listEl.querySelectorAll('.picker-row').forEach((row, idx) => {
    // Remove button
    row.querySelector('.picker-remove-btn')?.addEventListener('click', () => {
      const items = getPickerItems(editorEl);
      items.splice(idx, 1);
      reRenderPickerList(editorEl, items);
    });

    // Equiv toggle
    row.querySelector('.picker-equiv-btn')?.addEventListener('click', () => {
      const items = getPickerItems(editorEl);
      items[idx].equiv = !items[idx].equiv;
      row.dataset.equiv = items[idx].equiv;
      reRenderPickerList(editorEl, items);
    });

    // Note textarea sync (w_engines)
    row.querySelector('.picker-item-note')?.addEventListener('input', () => {
      syncPickerHiddenTextarea(editorEl);
    });

    // DnD
    row.addEventListener('dragstart', e => {
      _pickerDragSrc = { listEl, idx };
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      listEl.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });
    row.addEventListener('dragover', e => {
      e.preventDefault();
      if (_pickerDragSrc && _pickerDragSrc.listEl === listEl) {
        listEl.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        row.classList.add('drag-over');
      }
    });
    row.addEventListener('drop', e => {
      e.preventDefault();
      if (!_pickerDragSrc || _pickerDragSrc.listEl !== listEl) return;
      const from = _pickerDragSrc.idx;
      const to   = idx;
      if (from === to) return;
      const items = getPickerItems(editorEl);
      const [moved] = items.splice(from, 1);
      items.splice(to, 0, moved);
      _pickerDragSrc = null;
      reRenderPickerList(editorEl, items);
    });
  });
}

function initPickerField(editorEl) {
  const fieldKey = editorEl.dataset.fieldKey;
  const poolKey  = editorEl.dataset.pool;
  const pool     = getPickerPool(poolKey);

  // Initial rank label update
  let r = 0;
  editorEl.querySelectorAll('.picker-list .picker-row').forEach(row => {
    const equiv = row.dataset.equiv === 'true';
    const rankEl = row.querySelector('.picker-rank');
    if (rankEl) rankEl.textContent = equiv ? '≈' : ++r;
  });

  rewirePickerRowEvents(editorEl);

  // Tile click → add item
  editorEl.querySelectorAll('.picker-tile').forEach(tile => {
    tile.addEventListener('click', () => {
      const name = tile.dataset.name;
      const items = getPickerItems(editorEl);
      if (items.some(i => i.name === name)) return;
      items.push({ name, equiv: false, note: '' });
      reRenderPickerList(editorEl, items);
    });
  });

  // Search
  editorEl.querySelectorAll('.picker-search').forEach(input => {
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const grid = input.closest('.picker-pool').querySelector('.picker-grid');
      grid.querySelectorAll('.picker-tile').forEach(tile => {
        tile.hidden = q && !tile.dataset.name.toLowerCase().includes(q);
      });
    });
  });

  // Manual toggle
  const manualBtn = editorEl.querySelector('.picker-manual-link');
  const hiddenTa  = editorEl.parentElement.querySelector('.picker-hidden-ta');
  if (manualBtn && hiddenTa) {
    manualBtn.addEventListener('click', () => {
      syncPickerHiddenTextarea(editorEl);
      hiddenTa.rows = Math.max(4, (hiddenTa.value || '').split('\n').length + 1);
      hiddenTa.classList.remove('picker-manual-hidden');
      hiddenTa.classList.add('picker-manual-visible');
      editorEl.classList.add('picker-editor-hidden');

      if (!hiddenTa._visualBtn) {
        const btn = document.createElement('button');
        btn.className = 'picker-manual-link picker-visual-btn';
        btn.textContent = 'Use visual editor';
        hiddenTa.insertAdjacentElement('afterend', btn);
        hiddenTa._visualBtn = btn;
        btn.addEventListener('click', () => {
          const items2 = deserializePickerItems(hiddenTa.value, poolKey, fieldKey);
          reRenderPickerList(editorEl, items2);
          hiddenTa.classList.remove('picker-manual-visible');
          editorEl.classList.remove('picker-editor-hidden');
        });
      }
    });
  }
}

function initDiscPickerField(editorEl) {
  function rewireSection(section) {
    const listEl = editorEl.querySelector(`.picker-list-${section}`);
    if (!listEl) return;

    listEl.querySelectorAll('.disc-picker-row').forEach((row, idx) => {
      row.querySelector('.picker-remove-btn')?.addEventListener('click', () => {
        row.remove();
        syncDiscTiles(editorEl);
        syncDiscHiddenInputs(editorEl);
      });
      row.querySelector('.disc-picker-label-input')?.addEventListener('input', () => {
        syncDiscHiddenInputs(editorEl);
      });

      // DnD
      row.addEventListener('dragstart', e => {
        _pickerDragSrc = { listEl, idx };
        row.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });
      row.addEventListener('dragend', () => {
        row.classList.remove('dragging');
        listEl.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      });
      row.addEventListener('dragover', e => {
        e.preventDefault();
        if (_pickerDragSrc?.listEl === listEl) {
          listEl.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
          row.classList.add('drag-over');
        }
      });
      row.addEventListener('drop', e => {
        e.preventDefault();
        if (!_pickerDragSrc || _pickerDragSrc.listEl !== listEl) return;
        const from = _pickerDragSrc.idx;
        const to   = [...listEl.querySelectorAll('.disc-picker-row')].indexOf(row);
        if (from === to) { _pickerDragSrc = null; return; }
        const rows = [...listEl.querySelectorAll('.disc-picker-row')];
        const moved = rows.splice(from, 1)[0];
        rows.splice(to, 0, moved);
        rows.forEach(r => listEl.appendChild(r));
        _pickerDragSrc = null;
        syncDiscHiddenInputs(editorEl);
      });
    });
  }

  rewireSection('4pc');
  rewireSection('2pc');

  // Tile clicks — find which section the tile's picker-pool belongs to
  editorEl.querySelectorAll('.disc-picker-section').forEach(sectionEl => {
    const isFour = sectionEl.querySelector('.disc-picker-section-head').textContent.includes('4PC');
    const section = isFour ? '4pc' : '2pc';
    const listEl  = editorEl.querySelector(`.picker-list-${section}`);

    sectionEl.querySelectorAll('.picker-tile').forEach(tile => {
      tile.addEventListener('click', () => {
        const name = tile.dataset.name;
        if (listEl.querySelector(`.disc-picker-row[data-name="${CSS.escape(name)}"]`)) return;

        const icon = itemImgHtml(lookupItemIcon('zzz', name), 'picker-row-icon');
        const rowHtml = `<div class="disc-picker-row picker-row" draggable="true" data-name="${escHtml(name)}" data-section="${section}">
  <span class="picker-drag-handle">⠿</span>
  ${icon}
  <span class="picker-row-name">${escHtml(name)}</span>
  <input class="disc-picker-label-input" type="text" placeholder="Label (e.g. BIS)" value="">
  <button class="picker-remove-btn" title="Remove">✕</button>
</div>`;
        const emptyHint = listEl.querySelector('.picker-empty-hint');
        if (emptyHint) emptyHint.remove();
        listEl.insertAdjacentHTML('beforeend', rowHtml);
        rewireSection(section);
        syncDiscTiles(editorEl);
        syncDiscHiddenInputs(editorEl);
      });
    });

    sectionEl.querySelectorAll('.picker-search').forEach(input => {
      input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        const grid = input.closest('.picker-pool').querySelector('.picker-grid');
        grid.querySelectorAll('.picker-tile').forEach(tile => {
          tile.hidden = q && !tile.dataset.name.toLowerCase().includes(q);
        });
      });
    });
  });

  syncDiscHiddenInputs(editorEl);
}

function syncDiscTiles(editorEl) {
  const used4 = [...editorEl.querySelectorAll('.disc-picker-row[data-section="4pc"]')].map(r => r.dataset.name);
  const used2 = [...editorEl.querySelectorAll('.disc-picker-row[data-section="2pc"]')].map(r => r.dataset.name);
  editorEl.querySelectorAll('.disc-picker-section').forEach(sectionEl => {
    const isFour = sectionEl.querySelector('.disc-picker-section-head').textContent.includes('4PC');
    const used   = isFour ? used4 : used2;
    sectionEl.querySelectorAll('.picker-tile').forEach(tile => {
      tile.classList.toggle('in-use', used.includes(tile.dataset.name));
    });
  });
}

async function saveEditView(char) {
  // Sync picker states into hidden textareas before reading (skip if user is in manual mode)
  document.querySelectorAll('#char-right .picker-editor:not(.disc-picker-editor)').forEach(ed => {
    if (!ed.classList.contains('picker-editor-hidden')) syncPickerHiddenTextarea(ed);
  });

  const newChar = JSON.parse(JSON.stringify(char));
  document.querySelectorAll('#char-right [data-field]').forEach(el => {
    const buildIdx = el.dataset.build;
    const field    = el.dataset.field;
    const rawVal   = el.value;
    const val      = (rawVal.startsWith('[') || rawVal.startsWith('{')) ? (() => { try { return JSON.parse(rawVal); } catch { return rawVal; } })() : rawVal;
    if (buildIdx !== undefined && buildIdx !== '') {
      const bi = parseInt(buildIdx, 10);
      if (newChar.builds[bi]) newChar.builds[bi][field] = val;
    } else if (buildIdx === '') {
      newChar[field] = val;
    }
  });

  const arr = currentGame === 'gi' ? giChars : currentGame === 'hsr' ? hsrChars : zzzChars;
  const idx = arr.findIndex(c => c.name === char.name);
  if (idx >= 0) arr[idx] = newChar;
  const ai = allChars.findIndex(c => c.name === char.name);
  if (ai >= 0) allChars[ai] = newChar;
  activeChar = newChar;

  buildOverrides[currentGame] = buildOverrides[currentGame] || {};
  buildOverrides[currentGame][char.name] = newChar;
  try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(buildOverrides)); } catch {}

  if (!workerConfigured()) {
    _selectCharNoUrl(newChar);
    return;
  }

  const saveBtn = $('edit-save-btn');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  const result = await pushWorkerOverrides();
  if (result.ok) {
    _selectCharNoUrl(newChar);
  } else {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
    const statusEl = $('edit-sync-status');
    if (statusEl) {
      statusEl.className = 'edit-sync-status error';
      statusEl.textContent = `Sync failed: ${result.reason}. Saved locally as fallback.`;
    }
  }
}

async function resetCharEdit(char) {
  if (buildOverrides[currentGame]) delete buildOverrides[currentGame][char.name];
  try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(buildOverrides)); } catch {}

  const baseChar = (baseCharsMap[currentGame] || {})[char.name];
  const restored = baseChar ? JSON.parse(JSON.stringify(baseChar)) : char;
  const arr = currentGame === 'gi' ? giChars : currentGame === 'hsr' ? hsrChars : zzzChars;
  const idx = arr.findIndex(c => c.name === char.name);
  if (idx >= 0) arr[idx] = restored;
  const ai = allChars.findIndex(c => c.name === char.name);
  if (ai >= 0) allChars[ai] = restored;
  activeChar = restored;

  if (workerConfigured()) {
    await pushWorkerOverrides();
  }
  _selectCharNoUrl(restored);
}

function exportBuilds() {
  const arr = currentGame === 'gi' ? giChars : currentGame === 'hsr' ? hsrChars : zzzChars;
  const filename = currentGame === 'gi' ? 'builds.json' : currentGame === 'hsr' ? 'hsr_builds.json' : 'zzz_builds.json';
  const blob = new Blob([JSON.stringify(arr, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── card helpers ──────────────────────────────────────────────
function card(label, content, wide = false, colorTiers = false) {
  if (!content || !content.trim()) return '';
  const body = colorTiers ? colorize(escHtml(content)) : escHtml(content);
  return `
    <div class="build-card${wide ? ' wide' : ''}">
      <div class="card-label">${sectionIcon(label)}<span>${label}</span></div>
      <div class="card-body">${body}</div>
    </div>`;
}

function colorize(html) {
  return html.split('\n').map(line => {
    if (/^≈|^~~/.test(line.trim())) return `<span class="tier-eq">${line}</span>`;
    const m = line.trim().match(/^(\d+)[.)-]/);
    if (m) {
      const n = parseInt(m[1]);
      if (n === 1) return `<span class="tier-1">${line}</span>`;
      if (n === 2) return `<span class="tier-2">${line}</span>`;
    }
    return line;
  }).join('\n');
}

// ── tier list ────────────────────────────────────────────────
function charTier(char) {
  return (tiersData[currentGame] || {})[char.name] || null;
}

const TIER_ORDERS = {
  gi:  ['SS', 'S', 'A', 'B', 'C', 'D'],
  hsr: ['T0', 'T0.5', 'T1', 'T1.5', 'T2', 'T3', 'T4'],
  zzz: ['T0', 'T0.5', 'T1', 'T1.5', 'T2', 'T3', 'T4'],
};

function showTierView() {
  $('placeholder').classList.add('hidden');
  $('char-view').classList.add('hidden');
  $('tier-btn').classList.add('active');
  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  activeChar = null;
  $('tier-view').classList.remove('hidden');
  renderTierView();
  $('content').scrollTop = 0;
  updateLensState();
  // update url
  const params = new URLSearchParams();
  params.set('game', currentGame);
  params.set('view', 'tier');
  history.replaceState(null, '', '#' + params.toString());
}

// ── tier list state ───────────────────────────────────────────
let tierFilters = { element: null, group: null, newOnly: false, q: '' };
let tierCompact = false;

const TIER_BLURBS = {
  // HSR/ZZZ shape
  'T0':   { name: 'Era-defining', blurb: 'Top of meta. Pulls revolve around these.', color: '#f5a623', fg: '#000' },
  'T0.5': { name: 'Strong',       blurb: 'Build-around, very competitive.',         color: '#e8832a', fg: '#fff' },
  'T1':   { name: 'Solid',        blurb: 'Reliable picks, no team wasted.',         color: '#9b59b6', fg: '#fff' },
  'T1.5': { name: 'Niche',        blurb: 'Strong in their lane, narrow use.',       color: '#5b7fd4', fg: '#fff' },
  'T2':   { name: 'Aging',        blurb: 'Powercrept but still playable.',          color: '#3498db', fg: '#fff' },
  'T3':   { name: 'Filler',       blurb: 'Use only if you have no alternative.',    color: '#27ae60', fg: '#fff' },
  'T4':   { name: 'Outdated',     blurb: 'Outclassed; skip unless meme.',           color: '#8b949e', fg: '#0d1117' },
  // GI shape
  'SS':   { name: 'Top tier',     blurb: 'Strongest picks; pull priority.',         color: '#f5a623', fg: '#000' },
  'S':    { name: 'Strong',       blurb: 'Excellent in their role.',                color: '#9b59b6', fg: '#fff' },
  'A':    { name: 'Solid',        blurb: 'Good picks, reliable.',                   color: '#3498db', fg: '#fff' },
  'B':    { name: 'Decent',       blurb: 'Usable, niche or budget option.',         color: '#27ae60', fg: '#fff' },
  'C':    { name: 'Weak',         blurb: 'Outclassed in most teams.',               color: '#8b949e', fg: '#0d1117' },
  'D':    { name: 'Outdated',     blurb: 'Skip unless you must.',                   color: '#555',    fg: '#aaa' },
  'Unranked': { name: 'Unranked', blurb: 'No tier assigned.',                       color: '#3a414b', fg: '#fff' },
};

function renderTierView() {
  const gameTiers = tiersData[currentGame] || {};
  const gameIcons = icons[currentGame] || {};
  const tierOrder = TIER_ORDERS[currentGame] || TIER_ORDERS.zzz;

  // Build filtered list
  const q = (tierFilters.q || '').trim().toLowerCase();
  let chars = [...allChars];
  if (q) chars = chars.filter(c => c.name.toLowerCase().includes(q));
  if (tierFilters.element) chars = chars.filter(c => charElement(c) === tierFilters.element);
  if (tierFilters.group) {
    chars = chars.filter(c => {
      if (currentGame === 'hsr') return c.path === tierFilters.group;
      if (currentGame === 'zzz') return c.specialty === tierFilters.group;
      return true;
    });
  }
  if (tierFilters.newOnly) chars = chars.filter(c => isRecentlyReleased(c));

  const filteredCount = chars.length;
  const totalCount = allChars.length;

  // Group by tier
  const byTier = {};
  for (const c of chars) {
    const t = gameTiers[c.name] || 'Unranked';
    (byTier[t] = byTier[t] || []).push(c);
  }
  const orderedTiers = [...tierOrder.filter(t => byTier[t]), ...(byTier['Unranked'] ? ['Unranked'] : [])];

  // Determine collection axes
  const games = { gi: 'Genshin Impact', hsr: 'Honkai: Star Rail', zzz: 'Zenless Zone Zero' };
  const gameLabel = games[currentGame] || '';
  const gameShort = currentGame.toUpperCase();
  const groupAxisLabel = currentGame === 'hsr' ? 'Path' : currentGame === 'zzz' ? 'Specialty' : null;
  const groupValues = currentGame === 'hsr'
    ? ['Destruction', 'Hunt', 'Erudition', 'Harmony', 'Nihility', 'Preservation', 'Abundance', 'Remembrance']
    : currentGame === 'zzz'
      ? ['Attack', 'Anomaly', 'Stun', 'Support', 'Defense', 'Rupture']
      : null;

  // Element filter (use existing ELEMENT_ORDERS data)
  const elemSet = new Set();
  for (const c of allChars) {
    const el = charElement(c);
    if (el) elemSet.add(el);
  }
  const elemOrder = (ELEMENT_ORDERS[currentGame] || []).filter(e => elemSet.has(e));

  // Build header
  let html = `
    <div class="tv-head">
      <div>
        <div class="tv-eyebrow">${escHtml(gameShort)} · Tier List</div>
        <div class="tv-title">${escHtml(gameLabel)}</div>
      </div>
      <div class="tv-search">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.5"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="tv-search-input" type="text" placeholder="Filter characters…" value="${escHtml(tierFilters.q)}" autocomplete="off" spellcheck="false" />
      </div>
    </div>
    <div class="tv-filterbar">
  `;

  if (elemOrder.length) {
    html += '<div class="tv-fgroup"><span class="tv-flabel">Element</span>';
    html += `<button class="tv-fpill${tierFilters.element === null ? ' active' : ''}" data-tv-elem="">All</button>`;
    for (const el of elemOrder) {
      const col = ELEMENT_COLORS[el];
      const dot = col ? col[1] : 'var(--muted)';
      html += `<button class="tv-fpill${tierFilters.element === el ? ' active' : ''}" data-tv-elem="${escHtml(el)}"><span class="tv-fdot" style="background:${dot}"></span>${escHtml(el)}</button>`;
    }
    html += '</div>';
  }

  if (groupAxisLabel && groupValues) {
    html += `<div class="tv-fgroup"><span class="tv-flabel">${groupAxisLabel}</span>`;
    html += `<button class="tv-fpill${tierFilters.group === null ? ' active' : ''}" data-tv-group="">All</button>`;
    // detect which group values are actually present
    const presentGroups = new Set();
    for (const c of allChars) {
      const g = currentGame === 'hsr' ? c.path : c.specialty;
      if (g) presentGroups.add(g);
    }
    for (const g of groupValues) {
      if (!presentGroups.has(g)) continue;
      html += `<button class="tv-fpill${tierFilters.group === g ? ' active' : ''}" data-tv-group="${escHtml(g)}">${escHtml(g)}</button>`;
    }
    html += '</div>';
  }

  html += `
    <div class="tv-fgroup">
      <span class="tv-flabel">Show</span>
      <button class="tv-fpill${tierFilters.newOnly ? ' active' : ''}" id="tv-new-only">New only</button>
    </div>
    <span class="tv-resultcount"><b>${filteredCount}</b> of ${totalCount}</span>
    <div class="tv-density">
      <button class="${!tierCompact ? 'active' : ''}" data-tv-density="cards">Cards</button>
      <button class="${tierCompact ? 'active' : ''}" data-tv-density="compact">Compact</button>
    </div>
  </div>
  `;

  // Tier sections
  if (!orderedTiers.length) {
    html += `<div class="tv-empty"><b>No characters match.</b><br>Try clearing some filters.</div>`;
  } else {
    for (const tier of orderedTiers) {
      const meta = TIER_BLURBS[tier] || TIER_BLURBS['Unranked'];
      const tierChars = byTier[tier].sort((a, b) => releaseKey(b) - releaseKey(a));
      html += `<div class="tv-section" style="--t-color:${meta.color};--t-fg:${meta.fg}">`;
      html += `<div class="tv-banner">
        <span class="tv-letter">${escHtml(tier)}</span>
        <span class="tv-tier-name">${escHtml(meta.name)}</span>
        <span class="tv-tier-blurb">${escHtml(meta.blurb)}</span>
        <span class="tv-tier-count">${tierChars.length} character${tierChars.length === 1 ? '' : 's'}</span>
      </div>`;
      html += '<div class="tv-grid">';
      for (const c of tierChars) {
        const iconUrl = gameIcons[c.name];
        const el = charElement(c);
        const col = ELEMENT_COLORS[el];
        const dot = col ? col[1] : 'var(--muted)';
        const groupVal = currentGame === 'hsr' ? c.path : currentGame === 'zzz' ? c.specialty : el;
        const isNew = isRecentlyReleased(c);
        const cKey = c.name + '|' + (c.path || '');
        html += `<div class="tv-chip" data-tv-char="${escHtml(cKey)}" style="--c-color:${dot}">`;
        if (iconUrl) html += `<img class="tv-chip-icon" src="${escHtml(iconUrl)}" alt="" referrerpolicy="no-referrer">`;
        else html += '<span class="tv-chip-icon" style="background:rgba(255,255,255,0.05)"></span>';
        html += `<div class="tv-chip-info">`;
        html += `<span class="tv-chip-name">${escHtml(toTitle(c.name))}</span>`;
        html += `<span class="tv-chip-meta">`;
        if (el) html += `<span class="tv-eldot" style="background:${dot}"></span>`;
        if (groupVal) html += escHtml(groupVal);
        html += `</span>`;
        html += `</div>`;
        if (isNew) html += `<span class="tv-chip-new">NEW</span>`;
        html += `</div>`;
      }
      html += `</div></div>`;
    }
  }

  const view = $('tier-view');
  view.innerHTML = html;
  view.classList.toggle('compact', tierCompact);

  // Wire interactions
  view.querySelectorAll('[data-tv-elem]').forEach(btn => {
    btn.addEventListener('click', () => {
      const v = btn.dataset.tvElem;
      tierFilters.element = v || null;
      renderTierView();
    });
  });
  view.querySelectorAll('[data-tv-group]').forEach(btn => {
    btn.addEventListener('click', () => {
      const v = btn.dataset.tvGroup;
      tierFilters.group = v || null;
      renderTierView();
    });
  });
  const newBtn = view.querySelector('#tv-new-only');
  if (newBtn) newBtn.addEventListener('click', () => {
    tierFilters.newOnly = !tierFilters.newOnly;
    renderTierView();
  });
  view.querySelectorAll('[data-tv-density]').forEach(btn => {
    btn.addEventListener('click', () => {
      tierCompact = btn.dataset.tvDensity === 'compact';
      renderTierView();
    });
  });
  view.querySelectorAll('[data-tv-char]').forEach(chip => {
    chip.addEventListener('click', () => {
      const key = chip.dataset.tvChar;
      const char = allChars.find(c => (c.name + '|' + (c.path || '')) === key);
      if (char) selectChar(char);
    });
  });
  const searchInput = view.querySelector('#tv-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      tierFilters.q = searchInput.value;
      // Re-render without losing focus by saving cursor pos
      const start = searchInput.selectionStart;
      renderTierView();
      const newInput = $('tier-view').querySelector('#tv-search-input');
      if (newInput) { newInput.focus(); newInput.setSelectionRange(start, start); }
    });
  }
}

// ── utilities ─────────────────────────────────────────────────
function formatReleaseDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[parseInt(m,10)-1]} ${d}, ${y}`;
}

function formatVer(str) {
  if (!str) return '';
  const luna = str.match(/Luna\s+(\w+)/i);
  if (luna) return `Luna ${luna[1]}`;
  const num = str.match(/(\d+\.\d+)/);
  return num ? num[1] : '';
}

function toTitle(name) {
  return name.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

init();
