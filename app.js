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
let discIconNames = []; // disc set names from disc_icons.json (ZZZ only)
let zzzIconEntries = []; // [{name, url}] sorted by name from icons.json ZZZ section
let activeChar    = null;
let activeBuildIdx = 0;
let currentGame   = 'gi';   // 'gi' | 'hsr' | 'zzz'

const $ = id => document.getElementById(id);

const ELEMENT_ORDER = ['Physical', 'Fire', 'Electric', 'Ice', 'Ether'];

function zzzElementKey(char) {
  const i = ELEMENT_ORDER.indexOf(char.element || '');
  return i === -1 ? 999 : i;
}

function zzzSortedChars() {
  return [...zzzChars].sort((a, b) => {
    const ek = zzzElementKey(a) - zzzElementKey(b);
    if (ek !== 0) return ek;
    return releaseKey(b) - releaseKey(a);
  });
}

// ── boot ─────────────────────────────────────────────────────
async function init() {
  const [gi, hsr, zzz, pts, ico, rel, di] = await Promise.all([
    fetch('builds.json').then(r => r.json()),
    fetch('hsr_builds.json').then(r => r.json()),
    fetch('zzz_builds.json').then(r => r.json()),
    fetch('portraits.json').then(r => r.json()).catch(() => ({})),
    fetch('icons.json').then(r => r.json()).catch(() => ({})),
    fetch('release_data.json').then(r => r.json()).catch(() => ({})),
    fetch('disc_icons.json').then(r => r.json()).catch(() => ({})),
  ]);
  giChars  = gi;
  hsrChars = hsr;
  zzzChars = zzz;
  portraits = pts;
  icons = ico;
  releaseData = rel;
  discIconNames = Object.keys(di).sort();
  zzzIconEntries = Object.entries(ico.zzz || {}).sort((a, b) => a[0].localeCompare(b[0]));
  allChars = giChars;

  $('search').addEventListener('input', () => refreshList());

  document.querySelectorAll('.game-tab').forEach(tab => {
    tab.addEventListener('click', () => switchGame(tab.dataset.game));
  });

  $('back-btn').addEventListener('click', () => {
    document.body.classList.remove('viewing-char');
    $('back-btn').classList.add('hidden');
    $('disc-ref-view').classList.add('hidden');
    $('char-ref-view').classList.add('hidden');
    $('audit-view').classList.add('hidden');
    $('disc-ref-btn').classList.remove('active');
    $('char-ref-btn').classList.remove('active');
    $('audit-btn').classList.remove('active');
    $('placeholder').classList.remove('hidden');
  });

  $('disc-ref-btn').addEventListener('click', showDiscReference);
  $('char-ref-btn').addEventListener('click', showCharReference);
  $('audit-btn').addEventListener('click', showAuditView);

  $('audit-view').addEventListener('click', e => {
    if (e.target.id === 'audit-export-btn') { copyFlagged(e.target); return; }
    const btn = e.target.closest('[data-audit-char]');
    if (!btn) return;
    const charName = btn.dataset.auditChar;
    const status   = btn.dataset.auditStatus;
    const state    = getAuditState();
    if (state[charName] === status) {
      delete state[charName];
    } else {
      state[charName] = status;
    }
    saveAuditState(state);
    const scrollTop = $('content').scrollTop;
    renderAuditView();
    requestAnimationFrame(() => { $('content').scrollTop = scrollTop; });
  });

  updateSourceCredit(currentGame);
  refreshList();
}

function switchGame(game) {
  currentGame = game;
  allChars    = game === 'gi' ? giChars : game === 'hsr' ? hsrChars : zzzChars;
  activeChar  = null;

  document.querySelectorAll('.game-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.game === game));
  document.body.classList.toggle('game-hsr', game === 'hsr');
  document.body.classList.toggle('game-zzz', game === 'zzz');
  document.body.classList.remove('viewing-char');
  $('back-btn').classList.add('hidden');

  $('char-view').classList.add('hidden');
  $('disc-ref-view').classList.add('hidden');
  $('char-ref-view').classList.add('hidden');
  $('audit-view').classList.add('hidden');
  $('disc-ref-btn').classList.remove('active');
  $('char-ref-btn').classList.remove('active');
  $('audit-btn').classList.remove('active');
  $('disc-ref-wrap').classList.toggle('hidden', game !== 'zzz');
  $('placeholder').classList.remove('hidden');
  $('search').value = '';
  updateSourceCredit(game);
  refreshList();
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
  return entry && entry.version ? `v${entry.version}` : '';
}

function refreshList() {
  const q = $('search').value.trim().toLowerCase();
  let list = q ? allChars.filter(c => c.name.toLowerCase().includes(q)) : [...allChars];
  if (currentGame === 'zzz') {
    list.sort((a, b) => {
      const ek = zzzElementKey(a) - zzzElementKey(b);
      if (ek !== 0) return ek;
      return releaseKey(b) - releaseKey(a);
    });
  } else {
    list.sort((a, b) => releaseKey(b) - releaseKey(a));
  }
  renderList(list);
}

function renderList(chars) {
  const ul = $('char-list');
  ul.innerHTML = '';
  chars.forEach(char => {
    const li = document.createElement('li');
    li.dataset.name = char.name + '|' + (char.path || '');
    li.addEventListener('click', () => selectChar(char));

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
    const relVer = releaseVersionLabel(char);
    if (currentGame === 'gi') {
      metaSpan.textContent = relVer;
    } else if (currentGame === 'hsr') {
      metaSpan.textContent = char.path ? `${char.path} · ${relVer}` : relVer;
    } else {
      metaSpan.textContent = char.specialty ? `${char.specialty} · ${relVer}` : relVer;
    }

    li.appendChild(nameSpan);
    li.appendChild(metaSpan);
    ul.appendChild(li);
  });
  if (activeChar) highlightActive(activeChar);
}

function highlightActive(char) {
  const key = char.name + '|' + (char.path || '');
  document.querySelectorAll('#char-list li').forEach(li =>
    li.classList.toggle('active', li.dataset.name === key));
}

// ── character view ────────────────────────────────────────────
function selectChar(char) {
  activeChar    = char;
  activeBuildIdx = 0;
  highlightActive(char);

  $('placeholder').classList.add('hidden');
  $('disc-ref-view').classList.add('hidden');
  $('char-ref-view').classList.add('hidden');
  $('audit-view').classList.add('hidden');
  $('disc-ref-btn').classList.remove('active');
  $('char-ref-btn').classList.remove('active');
  $('audit-btn').classList.remove('active');
  $('char-view').classList.remove('hidden');

  $('char-name').textContent = toTitle(char.name);

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
  renderNotes(char);

  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  $('content').scrollTop = 0;
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

function renderGiBuild(build, panel) {
  const roleLabel = build.role + (build.recommended ? ' ✩' : '');
  panel.innerHTML = [
    card('role', roleLabel),
    itemCard('weapons', build.weapons, 'gi'),
    abilityCard('talent priority', build.talent_priority),
    itemCard('artifacts', build.artifacts, 'gi', true),
    card('main stats', build.main_stats),
    card('substats', build.substats, false, true),
    build.tips ? card('tips', build.tips, true) : '',
  ].join('');
}

function renderHsrBuild(char, build, panel) {
  const roleLabel = build.role || '';
  const notesText = [build.relic_notes, build.other_notes].filter(Boolean).join('\n\n');
  panel.innerHTML = [
    card('role', roleLabel),
    itemCard('light cones', build.light_cones, 'hsr'),
    abilityCard('ability priority', build.ability_priority, build.ability_notes),
    hsrRelicCard(build),
    card('main stats', build.main_stats),
    card('sub stats', build.sub_stats, false, true),
    build.baseline_stats ? card('stat targets', build.baseline_stats) : '',
    build.eidolons ? card('notable eidolons', build.eidolons) : '',
    notesText ? card('notes', notesText, true) : '',
    hsrTeamCard(char),
  ].join('');
}

function hsrTeamCard(char) {
  const teams = char.example_teams;
  if (!teams || !teams.length) return '';
  let html = '<div class="build-card wide"><div class="card-label">example teams</div><div class="hsr-teams">';
  for (const team of teams) {
    html += '<div class="hsr-team-group">';
    if (team.label) {
      html += `<div class="hsr-team-label">${escHtml(team.label)}</div>`;
    }
    if (team.members && team.members.length) {
      html += '<div class="hsr-team-members">';
      for (const m of team.members) {
        html += `<span class="hsr-team-chip">${escHtml(m)}</span>`;
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
    card('role', build.role),
    itemCard('w-engines', build.w_engines, 'zzz'),
    build.w_engine_notes ? card('w-engine notes', build.w_engine_notes, true) : '',
    abilityCard('ability priority', build.ability),
    discCard,
    mainStatContent,
    card('sub stats', build.sub_stats),
    build.baseline ? card('stat targets', build.baseline) : '',
    build.mindscapes ? card('mindscapes', build.mindscapes, true) : '',
    build.other_notes ? card('other notes', build.other_notes, true) : '',
    teamCard,
  ].join('');
}

// ── new render helpers ────────────────────────────────────────

function cardRaw(label, bodyHtml, wide = false) {
  if (!bodyHtml) return '';
  return `<div class="build-card${wide ? ' wide' : ''}"><div class="card-label">${label}</div>${bodyHtml}</div>`;
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
        cur = { rank: items.length + 1, name: t.slice(0, -1).trim(), desc: '' };
      } else if (cur) {
        cur.desc += (cur.desc ? '\n' : '') + t;
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
        cur = { rank: parseInt(nm[1]), name: nm[2].trim(), desc: '' };
      } else if (em) {
        if (cur) items.push(cur);
        cur = { rank: 0, name: em[1].trim(), desc: '' };
      } else if (cur) {
        cur.desc += (cur.desc ? '\n' : '') + t;
      }
    }
    if (cur) items.push(cur);
  }
  return items;
}

function itemListHtml(items) {
  if (!items.length) return '';
  return '<div class="item-list">' + items.map(item => {
    const cls = item.rank === 1 ? ' tier-1' : item.rank === 2 ? ' tier-2' : item.rank === 0 ? ' tier-eq' : '';
    const label = item.rank === 0 ? '≈' : item.rank;
    const nameHtml = `<span class="item-name${cls}">${escHtml(item.name)}</span>`;
    const descHtml = item.desc ? `<div class="item-desc">${escHtml(item.desc)}</div>` : '';
    return `<div class="item-row"><span class="item-rank">${label}</span><div class="item-body">${nameHtml}${descHtml}</div></div>`;
  }).join('') + '</div>';
}

function itemCard(label, text, game, wide = false) {
  if (!text || !text.trim()) return '';
  const items = parseItemList(text, game);
  if (!items.length) return card(label, text, wide, true);
  return cardRaw(label, `<div class="card-body">${itemListHtml(items)}</div>`, wide);
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
  let html = '<div class="build-card wide"><div class="card-label">relics</div><div class="disc-sets">';
  if (sets4.length) {
    html += '<div class="disc-row"><span class="disc-pc-label">4PC</span>'
      + sets4.map((s, i) => `<span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${escHtml(s)}</span>`).join('')
      + '</div>';
  }
  if (sets2.length) {
    html += '<div class="disc-row"><span class="disc-pc-label">2PC</span>'
      + sets2.map((s, i) => `<span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${escHtml(s)}</span>`).join('')
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

  let html = '<div class="build-card wide"><div class="card-label">drive discs</div>';

  if (has4 || has2) {
    html += '<div class="disc-sets">';
    if (has4) {
      const labels4 = build.disc_4pc_labels || [];
      html += '<div class="disc-row">'
        + '<span class="disc-pc-label">4PC</span>'
        + build.disc_4pc.map((s, i) => {
            const lbl = labels4[i] ? `<span class="disc-chip-label">${escHtml(labels4[i])}</span>` : '';
            return `<span class="disc-chip-wrap"><span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${escHtml(s)}</span>${lbl}</span>`;
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
                + s.map(name => `<span class="disc-chip">${escHtml(name)}</span>`)
                    .join('<span class="disc-pair-sep">/</span>')
                + `</span>${lbl}</span>`;
            }
            return `<span class="disc-chip-wrap"><span class="disc-chip${i === 0 ? ' disc-bis' : ''}">${escHtml(s)}</span>${lbl}</span>`;
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
  'Alexandrina Sebastiane (Rina)': 'Rina',
  'Asaba Harumasa': 'Harumasa',
  'Tsukishiro Yanagi': 'Yanagi',
  'Ukinami Yuzuha': 'Yuzuha',
  'Hoshimi Miyabi': 'Miyabi',
  'Luciana Auxesis Theodoro de Montefio (Lucy)': 'Lucy',
  'Komano Manato': 'Manato',
  'Koleda Belobog': 'Koleda',
  'Nekomiya Mana': 'Mana',
  'Alice Thymefield': 'Alice',
  'Von Lycaon': 'Lycaon',
  'Evelyn Chevalier': 'Evelyn',
  'Soldier 11 (Harin)': 'S11',
  'Soldier 0 - Anby': 'S0-Anby',
  'Flora (Seed)': 'Seed',
  'Grace Howard': 'Grace',
  'Jane Doe': 'Jane',
  'Ellen Joe': 'Ellen',
  'Piper Wheel': 'Piper',
  'Corin Wickes': 'Corin',
  'Nicole Demara': 'Nicole',
  'Anby Demara': 'Anby',
  'Billy Kid': 'Billy',
  'Seth Lowell': 'Seth',
  'Ju Fufu': 'Fufu',
  'Orphie Magnusson & Magus': 'Orphie',
  'Burnice White': 'Burnice',
  'Caesar King': 'Caesar',
  'Pulchra Fellini': 'Pulchra',
  'Vivian Banshee': 'Vivian',
  'Yidhari Murphy': 'Yidhari',
  'Hugo Vlad': 'Hugo',
  'Lucia Elowen': 'Lucia',
  'Astra Yao': 'Astra',
  'Anton Ivanov': 'Anton',
  'Ben Bigger': 'Ben',
  'Zhu Yuan': 'Zhu Yuan',
  'Nangong Yu': 'Nangong',
  'Ye Shunguang': 'Shunguang',
  'Pan Yinhu': 'Pan Yinhu',
};

function zzzShortName(n) {
  return ZZZ_SHORT[n] || n.replace(/\s*\(.*?\)\s*/g, '').trim().split(' ').pop();
}

function zzzTeamCard(build) {
  const hasComps = build.team_comps && build.team_comps.length;
  const hasGeneral = build.team_general && build.team_general.trim();
  if (!hasComps && !hasGeneral) return '';

  let html = '<div class="build-card wide"><div class="card-label">team comps</div>';

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
          for (const c of team.chars) {
            html += `<span class="team-member-chip">${escHtml(zzzShortName(c))}</span>`;
          }
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

function showDiscReference() {
  $('placeholder').classList.add('hidden');
  $('char-view').classList.add('hidden');
  $('char-ref-view').classList.add('hidden');
  $('audit-view').classList.add('hidden');
  $('char-ref-btn').classList.remove('active');
  $('audit-btn').classList.remove('active');
  $('disc-ref-btn').classList.add('active');
  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  activeChar = null;

  const view = $('disc-ref-view');
  view.classList.remove('hidden');
  view.innerHTML =
    '<div class="disc-ref-header">drive disc icons</div>'
    + '<div class="disc-ref-grid">'
    + discIconNames.map(name =>
        `<div class="disc-ref-item">`
        + `<img class="disc-ref-img" src="disc_icons/${encodeURIComponent(name)}.png" alt="${escHtml(name)}">`
        + `<span class="disc-ref-name">${escHtml(name)}</span>`
        + `</div>`
      ).join('')
    + '</div>';

  $('content').scrollTop = 0;
}

function showCharReference() {
  $('placeholder').classList.add('hidden');
  $('char-view').classList.add('hidden');
  $('disc-ref-view').classList.add('hidden');
  $('audit-view').classList.add('hidden');
  $('disc-ref-btn').classList.remove('active');
  $('audit-btn').classList.remove('active');
  $('char-ref-btn').classList.add('active');
  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  activeChar = null;

  const view = $('char-ref-view');
  view.classList.remove('hidden');
  view.innerHTML =
    '<div class="disc-ref-header">character icons (ZZZ)</div>'
    + '<div class="disc-ref-grid">'
    + zzzIconEntries.map(([name, url]) =>
        `<div class="disc-ref-item">`
        + `<img class="disc-ref-img" src="${escHtml(url)}" alt="${escHtml(name)}" referrerpolicy="no-referrer">`
        + `<span class="disc-ref-name">${escHtml(name)}</span>`
        + `</div>`
      ).join('')
    + '</div>';

  $('content').scrollTop = 0;
}

function getAuditState() {
  try { return JSON.parse(localStorage.getItem('zzz_audit') || '{}'); }
  catch { return {}; }
}
function saveAuditState(s) { localStorage.setItem('zzz_audit', JSON.stringify(s)); }

function copyFlagged(btn) {
  const state = getAuditState();
  const flagged = zzzChars
    .filter(c => state[c.name] && state[c.name] !== 'correct')
    .map(c => `- ${c.name}: ${state[c.name]}`);
  if (!flagged.length) return;
  const text = `Needs revision (${flagged.length}):\n${flagged.join('\n')}`;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

function showAuditView() {
  $('placeholder').classList.add('hidden');
  $('char-view').classList.add('hidden');
  $('disc-ref-view').classList.add('hidden');
  $('char-ref-view').classList.add('hidden');
  $('disc-ref-btn').classList.remove('active');
  $('char-ref-btn').classList.remove('active');
  $('audit-btn').classList.add('active');
  document.body.classList.add('viewing-char');
  $('back-btn').classList.remove('hidden');
  activeChar = null;
  $('audit-view').classList.remove('hidden');
  renderAuditView();
  $('content').scrollTop = 0;
}

function renderAuditView() {
  const state    = getAuditState();
  const sorted   = zzzSortedChars();
  const pending  = sorted.filter(c => !state[c.name]);
  const revision = sorted.filter(c => state[c.name] && state[c.name] !== 'correct');
  const verified = sorted.filter(c => state[c.name] === 'correct');
  const reviewed = revision.length + verified.length;

  const exportLabel = revision.length ? `export flagged (${revision.length})` : 'nothing flagged';
  const exportDis   = revision.length ? '' : ' disabled';
  let html = '<div class="audit-top-bar">'
    + '<span class="disc-ref-header" style="margin-bottom:0">audit — disc drives &amp; team comps</span>'
    + '<div class="audit-top-right">'
    + `<span class="audit-progress">${reviewed} / ${zzzChars.length} reviewed</span>`
    + `<button class="audit-export-btn" id="audit-export-btn"${exportDis}>${exportLabel}</button>`
    + '</div>'
    + '</div>';

  if (revision.length) {
    html += `<div class="audit-section-hdr audit-hdr-revision">needs revision <span class="audit-count">${revision.length}</span></div>`;
    html += '<div class="audit-grid">';
    for (const c of revision) html += auditCharCard(c, state[c.name]);
    html += '</div>';
  }

  if (pending.length) {
    html += `<div class="audit-section-hdr audit-hdr-pending">pending review <span class="audit-count">${pending.length}</span></div>`;
    html += '<div class="audit-grid">';
    for (const c of pending) html += auditCharCard(c, null);
    html += '</div>';
  }

  if (verified.length) {
    html += '<details class="audit-verified-wrap">'
      + `<summary class="audit-section-hdr audit-hdr-verified">verified <span class="audit-count">${verified.length}</span></summary>`
      + '<div class="audit-grid">';
    for (const c of verified) html += auditCharCard(c, 'correct');
    html += '</div></details>';
  }

  $('audit-view').innerHTML = html;
}

function discIconItem(name) {
  const src = 'disc_icons/' + encodeURIComponent(name) + '.png';
  return `<div class="disc-icon-item">`
    + `<img class="disc-icon-img" src="${src}" alt="${escHtml(name)}">`
    + `<span class="disc-icon-name">${escHtml(name)}</span>`
    + `</div>`;
}

function auditCharCard(char, status) {
  const build = char.builds && char.builds[0];
  if (!build) return '';
  const zzzIcons = icons.zzz || {};
  const iconUrl  = zzzIcons[char.name];
  const disc4    = build.disc_4pc || [];
  const disc2    = build.disc_2pc || [];
  const teams    = build.team_comps || [];
  const statusCls = status ? ` audit-status-${status}` : '';

  let html = `<div class="audit-char${statusCls}">`;

  // Header
  html += '<div class="audit-char-header">';
  if (iconUrl) html += `<img class="audit-char-icon" src="${escHtml(iconUrl)}" alt="" referrerpolicy="no-referrer">`;
  html += `<span class="audit-char-name">${escHtml(char.name)}</span>`;
  if (char.specialty) html += `<span class="path-badge">${escHtml(char.specialty)}</span>`;
  html += '</div>';

  // Disc drives
  if (disc4.length || disc2.length) {
    html += '<div class="audit-section">';
    if (disc4.length) {
      html += '<div class="audit-row"><span class="audit-pc">4PC</span><div class="disc-icon-row">';
      for (const s of disc4) html += discIconItem(s);
      html += '</div></div>';
    }
    if (disc2.length) {
      html += '<div class="audit-row"><span class="audit-pc">2PC</span><div class="disc-icon-row">';
      for (const s of disc2) {
        if (Array.isArray(s)) {
          html += '<div class="disc-pair">';
          for (const n of s) html += discIconItem(n);
          html += '</div>';
        } else {
          html += discIconItem(s);
        }
      }
      html += '</div></div>';
    }
    html += '</div>';
  } else {
    html += '<div class="audit-empty">no disc data</div>';
  }

  // Team comps
  if (teams.length) {
    html += '<div class="audit-teams">';
    for (const team of teams) {
      html += '<div class="audit-team-row">';
      html += `<span class="audit-team-label">${escHtml(team.label)}</span>`;
      html += '<div class="audit-team-members">';
      for (const m of team.chars) {
        const mUrl = zzzIcons[m];
        html += '<div class="audit-member">';
        if (mUrl) html += `<img class="audit-member-icon" src="${escHtml(mUrl)}" alt="" referrerpolicy="no-referrer">`;
        html += `<span class="audit-member-name">${escHtml(zzzShortName(m))}</span>`;
        html += '</div>';
      }
      html += '</div></div>';
    }
    html += '</div>';
  } else {
    html += '<div class="audit-empty">no team data</div>';
  }

  // Action buttons
  const enc = escHtml(char.name);
  html += '<div class="audit-actions">'
    + `<button class="audit-action-btn audit-correct${status === 'correct' ? ' active' : ''}" data-audit-char="${enc}" data-audit-status="correct">✓ correct</button>`
    + `<button class="audit-action-btn audit-wrong${status === 'discs' ? ' active' : ''}" data-audit-char="${enc}" data-audit-status="discs">✗ discs</button>`
    + `<button class="audit-action-btn audit-wrong${status === 'teams' ? ' active' : ''}" data-audit-char="${enc}" data-audit-status="teams">✗ teams</button>`
    + `<button class="audit-action-btn audit-wrong${status === 'both' ? ' active' : ''}" data-audit-char="${enc}" data-audit-status="both">✗ both</button>`
    + '</div>';

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

// ── card helpers ──────────────────────────────────────────────
function card(label, content, wide = false, colorTiers = false) {
  if (!content || !content.trim()) return '';
  const body = colorTiers ? colorize(escHtml(content)) : escHtml(content);
  return `
    <div class="build-card${wide ? ' wide' : ''}">
      <div class="card-label">${label}</div>
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
