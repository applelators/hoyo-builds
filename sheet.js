/* ══════════════════════════════════════════════════════════════
   Archon — data-driven Nightdesk character sheet.
   Renders the real build JSON (builds.json / hsr_builds.json /
   zzz_builds.json) into the triptych defined in build-sheet.css.
   Shares globals from app.js: S, GAMES, RARITY, elColor, isNew, esc.
   Exposes: buildSheetHTML(c), wireSheet(tk, c).
   ══════════════════════════════════════════════════════════════ */
(function () {
  const GAME_LABELS = {
    gi:  { w: 'Weapons',    a: 'Artifacts',        scheme: 'Cool Blue' },
    hsr: { w: 'Light Cones', a: 'Relic Sets',      scheme: 'Astral Indigo' },
    zzz: { w: 'W-Engines',   a: 'Drive Discs',     scheme: 'New Eridu Amber' },
  };
  const SVG = {
    cone:   '<svg viewBox="0 0 16 16"><path d="M8 2l1.7 3.9 4.3.4-3.2 2.8 1 4.2L8 11.2 4.2 13.5l1-4.2L2 6.3l4.3-.4z"/></svg>',
    disc:   '<svg viewBox="0 0 16 16"><rect x="3" y="3" width="10" height="10" rx="2"/><path d="M3 8h10M8 3v10"/></svg>',
    planar: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="1.6"/></svg>',
    main:   '<svg viewBox="0 0 16 16"><path d="M2 12l3-3 2.5 2L11 6l3 3"/><path d="M2 4h12"/></svg>',
    sub:    '<svg viewBox="0 0 16 16"><path d="M8 2v12M2 8h12"/></svg>',
    stat:   '<svg viewBox="0 0 16 16"><path d="M2 12l3.5-3.5L8 10.5 13.5 5"/><path d="M10 5h3.5v3.5"/></svg>',
    role:   '<svg viewBox="0 0 16 16"><circle cx="8" cy="5" r="2.6"/><path d="M3 13.5c.6-2.6 2.6-4 5-4s4.4 1.4 5 4"/></svg>',
    upd:    '<svg viewBox="0 0 16 16"><path d="M4 2h6l3 3v9H4z"/><path d="M9 2v4h4"/></svg>',
    team:   '<svg viewBox="0 0 16 16"><circle cx="5" cy="6" r="2.3"/><circle cx="11" cy="6" r="2.3"/><path d="M2 13c.4-2 1.6-3 3-3s2.6 1 3 3M8 13c.4-2 1.6-3 3-3s2.6 1 3 3"/></svg>',
    abil:   '<svg viewBox="0 0 16 16"><path d="M2 13V3l4 3 2-3 2 3 4-3v10z"/></svg>',
    note:   '<svg viewBox="0 0 16 16"><path d="M4 2h6l3 3v9H4z"/><path d="M9 2v4h4"/></svg>',
  };

  // ── tiny parsers ─────────────────────────────────────────────
  const lines = t => String(t || '').split('\n').map(s => s.trim()).filter(s => s && s !== '-' && s !== '–');
  // sanitize free-text descriptions: drop a redundant "X Overview:" label prefix and
  // collapse pathological repeated-character runs (placeholder junk like "AAAA…").
  function cleanDesc(t) {
    return String(t || '')
      .replace(/^\s*[\w ]{0,24}overview\s*:\s*/i, '')
      .replace(/(\w)\1{4,}/g, '$1$1')
      .replace(/\s{2,}/g, ' ')
      .trim();
  }
  const STAR_RE = /\(?\s*([3-5])\s*[★✩☆\*]+\s*\)?/;          // 5★ / (4✩) / 5☆
  const TAG_RE = /\[([^\]]+)\]/;
  const FN_RE = /[¹²³⁴⁵⁶⁰⁷⁸⁹]/g;
  function stripRank(s) { return s.replace(/^\s*(?:~~|≈|[\u2022*]|\d+[.)\-]+)\s*/, '').trim(); }
  function detectStar(s) { const m = s.match(STAR_RE); return m ? +m[1] : 0; }
  function detectTag(s) { const m = s.match(TAG_RE); return m ? m[1] : ''; }
  function cleanName(s) {
    return s.replace(STAR_RE, ' ').replace(TAG_RE, ' ').replace(/\(\d[★✩☆]\)/g, ' ')
      .replace(FN_RE, '').replace(/\s*\*+\s*$/, '').replace(/^\s*\d+\s*[-.)]+\s*/, '')
      .replace(/\s{2,}/g, ' ').replace(/[:：]\s*$/, '').trim();
  }
  // parse a ranked item field -> [{name, star, tag, pc, alt}]
  function parseItems(text) {
    const out = []; let n = 0;
    for (const raw of lines(text)) {
      if (/^[*¹²³⁴⁵⁶].*/.test(raw) && !/[★✩☆]/.test(raw)) continue;   // footnote-only line
      const alt = /^\s*(~~|≈)/.test(raw);
      const star = detectStar(raw), tag = detectTag(raw);
      let body = stripRank(raw);
      const pcm = body.match(/(\d)\s*-?\s*pc\b\s*:?/i);             // "4-PC:" piece count
      const pc = pcm ? pcm[1] + '-pc' : '';
      if (pcm) body = body.replace(pcm[0], ' ');
      const name = cleanName(body);
      if (!name || /^(see notes|conditional|choose)/i.test(name)) continue;
      if (!alt) n++;
      out.push({ name, star, tag, pc, alt, rank: alt ? '≈' : n });
    }
    return out;
  }
  // ZZZ w_engines are free-form: engine names are lines ending in ':' with
  // effect lines between them. Pull just the named engines.
  function parseEngines(text) {
    const out = []; let n = 0;
    for (const raw of lines(text)) {
      if (!/:\s*$/.test(raw) || raw.length > 56) continue;     // only "Engine Name:" lines
      let name = raw.replace(/:\s*$/, '').trim();
      const tag = (name.match(/\(([^)]+)\)/) || [])[1] || '';
      name = name.replace(/\([^)]*\)/, '').replace(FN_RE, '').trim();
      if (!name) continue;
      n++; out.push({ name, tag, star: 0, rank: n, alt: false });
    }
    return out;
  }

  function tagPill(tag) {
    if (!tag) return '';
    const t = tag.toLowerCase();
    if (/free/.test(t)) return `<span class="freetag">${esc(tag)}</span>`;
    if (/battle pass|bp/.test(t)) return `<span class="bptag">${esc(tag)}</span>`;
    return `<span class="bptag">${esc(tag)}</span>`;
  }
  function itemRow(it, sig) {
    const pc = it.star === 5 ? 'p5' : it.star === 4 ? 'p4' : 'p4';
    const sc = it.star === 5 ? 'st5' : 'st4';
    const right = sig && it.rank === 1 ? '<span class="sigtag">Signature</span>' : tagPill(it.tag);
    const starCell = it.star ? `<span class="star ${sc}">${it.star}★</span>` : '';
    return `<tr><td class="rn">${it.rank}</td><td><div class="itm"><span class="thumb ph">${esc(it.name[0] || '?')}</span><span class="pill ${pc}">${esc(it.name)}</span></div></td><td class="r">${right}</td><td class="r">${starCell}</td></tr>`;
  }
  function setRow(it) {
    const badge = it.pc || it.tag;
    return `<tr><td class="rn">${it.rank}</td><td><div class="itm"><span class="thumb ph">${esc(it.name[0] || '?')}</span><span class="nm2">${esc(it.name)}</span>${badge ? `<span class="free">${esc(badge)}</span>` : ''}</div></td></tr>`;
  }
  function card(label, meta, body) {
    return `<div class="card pad reveal" style="--i:${ri++}"><div class="clab">${label}${meta ? `<span class="m">${esc(meta)}</span>` : ''}</div>${body}</div>`;
  }
  let ri = 0;

  // ── member avatar (team) ─────────────────────────────────────
  function memberAvatar(game, name, lead) {
    const icons = (S.icons && S.icons[game]) || {};
    let key = name, src = icons[name];
    if (!src) {                                  // try a looser match (ZZZ alt names "Long (Rina)")
      const base = name.replace(/\s*\(.*\)\s*/, '').trim();
      src = icons[base] || icons[(name.match(/\(([^)]+)\)/) || [])[1]];
    }
    const disp = name.replace(/\s*\(.*\)\s*/, '').trim();
    const short = disp.length > 9 ? disp.slice(0, 8) + '…' : disp;
    const inner = src ? `<img src="${src}" referrerpolicy="no-referrer" alt="">` : `<span class="ph">${esc(disp[0] || '?')}</span>`;
    return `<div class="av${lead ? ' lead' : ''}">${inner}<span>${esc(short)}</span></div>`;
  }
  function teamCard(game, teams) {
    if (!teams || !teams.length) return '';
    const body = `<div class="teams">${teams.slice(0, 5).map(t => {
      const note = t.note || '';
      return `<div class="team"><div class="tn"><b>${esc(t.label || 'Team')}</b>${note ? `<span>${esc(note)}</span>` : ''}</div><div class="mem">${(t.members || []).slice(0, 4).map((m, i) => memberAvatar(game, m, i === 0)).join('')}</div></div>`;
    }).join('')}</div>`;
    return card('Recommended Teams', '', body);
  }

  // ── ability priority -> trace column ─────────────────────────
  const ABIL_ICONS = ['<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2"/></svg>',
    '<svg viewBox="0 0 16 16"><path d="M8 1l2 5 5 .5-3.7 3.3 1.2 5L8 12.4 3.5 14.8l1.2-5L1 6.5 6 6z"/></svg>',
    '<svg viewBox="0 0 16 16"><path d="M8 2l1.6 3.7 3.9.4-3 2.6.9 3.9L8 11.6 4.6 13.2l.9-3.9-3-2.6 3.9-.4z"/></svg>',
    '<svg viewBox="0 0 16 16"><path d="M3 13L11 3M8 3h3v3"/><path d="M3 9l4 4"/></svg>',
    '<svg viewBox="0 0 16 16"><path d="M2 8h12M9 4l4 4-4 4"/></svg>'];
  const ORD = ['1st', '2nd', '3rd', '4th', '5th', '6th'];
  function abilityCard(text, notes) {
    const items = lines(text).map(stripRank).map(s => s.replace(FN_RE, '').trim()).filter(Boolean);
    if (!items.length) return '';
    const skipLast = /ignored|can be ignored|skip/i.test(notes || '') || /ignored|skip/i.test(text || '');
    const rows = items.slice(0, 6).map((label, idx) => {
      const lead = idx < 2;
      const skip = skipLast && idx === items.length - 1;
      return `<div class="trow${lead ? ' lead' : ''}${skip ? ' skip' : ''}"><div class="ic">${ABIL_ICONS[Math.min(idx, 4)]}</div><div class="lbl">${esc(label)}</div><div class="pr">${ORD[idx] || ''}</div></div>`;
    }).join('');
    const note = (notes && notes !== '-') ? `<div class="tnote">${esc(notes)}</div>` : '';
    return card('Ability Priority', 'level order', `<div class="tcol">${rows}</div>${note}`);
  }

  // ── stat helpers ─────────────────────────────────────────────
  function statListCard(label, meta, text, hlKeys) {
    const rows = lines(text).map(l => {
      const m = l.split(/[:：]/);
      if (m.length >= 2) { const k = m[0].trim(), v = m.slice(1).join(':').trim(); return { k, v }; }
      return { k: l.trim(), v: '' };
    }).filter(r => r.k);
    if (!rows.length) return '';
    const body = `<div class="statlist">${rows.map(r => {
      const hl = hlKeys && hlKeys.test(r.k);
      return `<div class="r${hl ? ' hl' : ''}"><span class="k">${esc(r.k)}</span><span class="ld"></span><span class="v">${esc(r.v || '·')}</span></div>`;
    }).join('')}</div>`;
    return card(label, meta, body);
  }
  function mainStatsCard(game, text) {
    const ls = lines(text);
    if (!ls.length) return '';
    const HSR_SLOTS = ['Body', 'Feet', 'Sphere', 'Rope'];
    const rows = ls.map((l, i) => {
      let slot = '', val = l;
      if (/\s-\s/.test(l)) { const p = l.split(/\s-\s/); slot = p[0]; val = p.slice(1).join(' - '); }
      else if (/\bDisc\s*\d/i.test(l)) { const m = l.match(/(.*?)(Disc\s*\d)/i); slot = m ? m[2] : ''; val = m ? m[1].trim() : l; }
      else if (game === 'hsr' && i < 4) { slot = HSR_SLOTS[i]; val = l; }
      return { slot, val: val.replace(FN_RE, '').trim() };
    });
    const body = `<table>${rows.map(r => `<tr class="slot-row"><td>${esc(r.slot || '·')}</td><td>${r.val.includes('/') ? esc(r.val) : `<span class="em">${esc(r.val)}</span>`}</td></tr>`).join('')}</table>`;
    return card('Main Stats', 'by slot', body);
  }
  function subStatCard(text) {
    const parts = lines(text).map(stripRank).map(s => s.replace(FN_RE, '').replace(/\*+/g, '').trim()).filter(Boolean);
    if (!parts.length) return '';
    const flow = parts.map(esc).join('<span class="gt">›</span>');
    return card('Substat Priority', '', `<div class="flow">${flow}</div>`);
  }
  function notesCard(noteFields) {
    const blocks = [];
    const marks = ['¹', '²', '³', '✦'];
    noteFields.filter(Boolean).forEach(t => {
      lines(t).forEach(l => { if (l.length > 4) blocks.push(l); });
    });
    if (!blocks.length) return '';
    const body = blocks.slice(0, 6).map((b, i) => `<div class="note"><span class="fn">${marks[i] || '✦'}</span>${esc(b)}</div>`).join('');
    return card('Notes &amp; Insights', '', body);
  }

  // ── per-game normalizer ──────────────────────────────────────
  function normalize(game, c) {
    const root = (S.builds && S.builds[game] && S.builds[game][c.name]) || {};
    const b = (root.builds && root.builds[0]) || {};
    if (game === 'hsr') return {
      role: b.role, wText: b.light_cones, setsText: b.relic_4pc, planarText: b.planar_ornament,
      mainStats: b.main_stats, subStats: b.sub_stats, baseline: b.baseline_stats,
      ability: b.ability_priority, abilityNotes: b.ability_notes,
      notes: [b.relic_notes, b.other_notes], desc: root.kit_overview,
      teams: (root.example_teams || []).map(t => ({ label: t.label, members: t.members })),
      pull: root.recommended_baseline, eidolons: b.eidolons, sub: root.path, lastUpdated: c.version ? ('Version ' + c.version) : '',
    };
    if (game === 'zzz') return {
      role: b.role, wText: b.w_engines, setsLabels: (b.disc_4pc_labels || []).concat(b.disc_2pc_labels || []),
      mainStats: b.main_stats, subStats: b.sub_stats, baseline: b.baseline,
      ability: b.ability, abilityNotes: '',
      notes: [b.w_engine_notes, b.disc_notes, b.other_notes], desc: b.team_general || root.notes,
      teams: (b.team_comps || []).map(t => ({ label: t.label, members: t.chars })),
      pull: b.mindscapes, sub: root.specialty || c.element, lastUpdated: root.last_updated ? ('Version ' + root.last_updated) : '',
    };
    // gi
    return {
      role: b.role, wText: b.weapons, setsText: b.artifacts,
      mainStats: b.main_stats, subStats: b.substats, baseline: '',
      ability: b.talent_priority, abilityNotes: '',
      notes: [b.tips, root.notes], desc: root.notes,
      teams: [], pull: '', sub: c.element, lastUpdated: root.last_updated || (c.version ? ('Version ' + c.version) : ''),
    };
  }

  // ── main entry ───────────────────────────────────────────────
  window.buildSheetHTML = function (c) {
    ri = 0;
    const game = S.game, L = GAME_LABELS[game] || GAME_LABELS.hsr;
    const ec = elColor(c.element), rc = RARITY[c.rarity] || RARITY[4];
    const splash = c.splash || c.icon;
    const d = normalize(game, c);
    const hasBuild = !!(d.role || d.wText || d.mainStats);
    const sub = d.sub || c.element || '';

    // LEFT — identity rail
    const stars = '<i></i>'.repeat(c.rarity || 4);
    const role0 = d.role ? d.role.split('\n')[0].trim() : '';
    const showSub = sub && !(role0 && role0.toLowerCase().includes(sub.toLowerCase()));
    const roleLabel = [showSub ? sub : '', role0].filter(Boolean).join(' · ');
    const idBadges = `<div class="ids">${c.element ? `<span class="badge b-el"><span class="d"></span>${esc(c.element)}</span>` : ''}${roleLabel ? `<span class="badge b-role">${esc(roleLabel)}</span>` : ''}</div>`;
    const portrait = `<div class="card reveal" style="--i:${ri++}">
      <div class="art sheet-portrait">${splash ? `<img src="${splash}" alt="${esc(c.name)}" referrerpolicy="no-referrer">` : ''}<span class="tag">v${esc(c.version || '—')} · ${esc(L.scheme)}</span></div>
      <div class="plate"><h1>${esc(c.name)}</h1><div class="stars">${stars}</div>${idBadges}</div>
    </div>`;
    const statCard = d.baseline
      ? statListCard('Recommended Stats', 'targets', d.baseline, /CRIT|CR|CD/i)
      : (d.subStats ? card('Recommended Stats', 'targets', `<div class="statlist">${lines(d.subStats).slice(0, 4).map((l, i) => `<div class="r${i === 0 ? ' hl' : ''}"><span class="k">Priority ${i + 1}</span><span class="ld"></span><span class="v">${esc(cleanName(stripRank(l)))}</span></div>`).join('')}</div>`) : '');
    const descClean = cleanDesc((d.desc || '').split('\n').filter(Boolean)[0] || '');
    const roleCard = d.role ? card('Role', '', `<div class="role-big">${esc(d.role.split('\n').join(' · '))}</div>${descClean ? `<div class="role-desc">${esc(descClean.slice(0, 300))}</div>` : ''}`) : '';
    const updCard = card('Last Updated', '', `<div class="updrow"><b>${esc(d.lastUpdated || '—')}</b><span class="chip-sync">Patch sync</span></div>`);
    const left = `<div class="col l">${portrait}${statCard}${roleCard}${updCard}</div>`;

    // MIDDLE — build
    const cones = game === 'zzz' ? parseEngines(d.wText) : parseItems(d.wText);
    const conesCard = cones.length ? card(L.w, 'best → budget', `<table>${cones.map(it => itemRow(it, game === 'hsr')).join('')}</table>`) : '';
    const sets = parseItems(d.setsText);
    let setsCard = '';
    if (sets.length) setsCard = card(L.a, '4-pc', `<table>${sets.map(setRow).join('')}</table>`);
    else if (d.setsLabels && d.setsLabels.length) setsCard = card(L.a, 'sets', `<table>${d.setsLabels.map((s, i) => setRow({ rank: i + 1, name: s, tag: '' })).join('')}</table>`);
    const planar = d.planarText ? parseItems(d.planarText) : [];
    const planarCard = planar.length ? card('Planar Ornament', '', `<table>${planar.map(setRow).join('')}</table>`) : '';
    const setsPair = (setsCard && planarCard) ? `<div class="pair">${setsCard}${planarCard}</div>` : (setsCard + planarCard);
    const mid = `<div class="col">${conesCard}${setsPair}${mainStatsCard(game, d.mainStats)}${subStatCard(d.subStats)}${notesCard(d.notes)}</div>`;

    // RIGHT — teams + pull + abilities
    const teams = teamCard(game, d.teams);
    let pullCard = '';
    if (d.pull || d.eidolons) {
      const eid = d.eidolons ? lines(d.eidolons).map(esc).join('<span class="gt">›</span>') : '';
      pullCard = `<div class="pull reveal" style="--i:${ri++}"><div class="pl">Pull Priority</div><div class="pv">${esc(d.pull || c.name)}${eid ? `<div style="margin-top:7px;font-size:12.5px;color:var(--dim)">Eidolons: ${eid}</div>` : ''}</div></div>`;
    }
    const abil = abilityCard(d.ability, d.abilityNotes);
    const right = `<div class="col">${teams}${pullCard}${abil}</div>`;

    const fallback = !hasBuild ? `<div class="sheet-note" style="grid-column:1/-1">No structured build data found for <b>${esc(c.name)}</b> yet — released v${esc(c.version || '—')}.</div>` : '';

    return `<div class="sheet">
      <header class="sheet-bar">
        <button class="back" data-back><svg viewBox="0 0 16 16" width="13" height="13" fill="none"><path d="M9.5 3L5 8l4.5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>Back</button>
        <div class="crumbs"><span class="crumb-dot" style="background:${ec};color:${ec}"></span><span class="crumb-pre">${esc(GAMES[game])}${c.element ? ' · ' + esc(c.element) : ''} ·</span><b>${esc(c.name)}</b></div>
        <button class="sheet-edit">edit</button>
      </header>
      <div class="sheet-body fullsheet" style="--ec:${ec};--ec2:${rc[1]}">
        <div class="grid">${left}${mid}${right}${fallback}</div>
      </div>
    </div>`;
  };

  // hover footnote popups reuse the conepop styling; lightweight version
  window.wireSheet = function (tk, c) {
    const sheet = tk.querySelector('.fullsheet');
    if (sheet) sheet.addEventListener('scroll', () => { if (tk._pop) tk._pop.classList.remove('show'); }, { passive: true });
  };
})();
