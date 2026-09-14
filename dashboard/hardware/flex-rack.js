/**
 * Physical Allen-Bradley 1794 FLEX I/O SVG rack renderer.
 * Center-pane only — does not own tree, channel table, or HardwareIOModel.
 */
(function (global) {
  'use strict';

  const IO_W = 100;
  const ADAPTER_W = 172;
  const MOD_H = 260;
  const GAP = 3;

  const flexVisualMap = {
    '1794-AENT': 'Flex1794Adapter',
    '1794-AENTR': 'Flex1794Adapter',
    '1794-IA16': 'Flex1794Input16',
    '1794-IB16': 'Flex1794Input16',
    '1794-OA8I': 'Flex1794Output8',
    '1794-OB16P': 'Flex1794Output16',
    '1794-IA8': 'Flex1794Input8',
    '1794-IB8': 'Flex1794Input8',
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** Strip revision / suffix: /A /B -A -B _A _B and trailing letters after slash. */
  function normalizeCatalog(raw) {
    let cat = String(raw || '').trim().toUpperCase();
    cat = cat.replace(/[/_\-][A-Z]\d*$/i, '');
    cat = cat.replace(/\s+/g, '');
    return cat;
  }

  function resolveVisual(mod) {
    if (!mod) return 'Flex1794Unknown';
    if (mod.is_adapter_card) return 'Flex1794Adapter';
    const cat = normalizeCatalog(mod.catalog || mod.type || '');
    if (flexVisualMap[cat]) return flexVisualMap[cat];
    if (/AENTR?$/.test(cat)) return 'Flex1794Adapter';
    if (/I[AB]16|IW16/.test(cat)) return 'Flex1794Input16';
    if (/OB16P?|OW16|OA16/.test(cat)) return 'Flex1794Output16';
    if (/OA8I?|OB8|OW8/.test(cat)) return 'Flex1794Output8';
    if (/I[AB]8/.test(cat)) return 'Flex1794Input8';
    return 'Flex1794Unknown';
  }

  function isAdapterVisual(visual) {
    return visual === 'Flex1794Adapter';
  }

  function channelCapacity(mod, visual) {
    const cap = Number(mod.channel_capacity);
    if (cap > 0) return cap;
    if (visual === 'Flex1794Input16' || visual === 'Flex1794Output16') return 16;
    if (visual === 'Flex1794Input8' || visual === 'Flex1794Output8') return 8;
    return (mod.channels || []).length;
  }

  /** LED states from model channels only — never invent endpoints. */
  function ledStates(mod, visual) {
    if (isAdapterVisual(visual)) return [];
    const cap = channelCapacity(mod, visual);
    const channels = mod.channels || [];
    const byBit = new Map();
    for (const ch of channels) {
      const bit = ch.fortna_bit;
      if (bit == null || bit === '') continue;
      byBit.set(Number(bit), ch);
    }
    const n = cap > 0 ? cap : channels.length;
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const ch = byBit.get(i);
      if (!ch) out.push('spare');
      else if (ch.logical_endpoint && ch.logical_endpoint.name) out.push('ok');
      else out.push('warn');
    }
    return out;
  }

  function ledFill(st) {
    if (st === 'ok') return '#22c55e';
    if (st === 'warn') return '#f59e0b';
    return '#6b7280';
  }

  function ledGlow(st) {
    if (st === 'ok') return 'rgba(34,197,94,0.65)';
    if (st === 'warn') return 'rgba(245,158,11,0.55)';
    return 'none';
  }

  function svgDefs(uid) {
    return `
      <defs>
        <linearGradient id="${uid}-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#e8e4d8"/>
          <stop offset="18%" stop-color="#d5d0c4"/>
          <stop offset="55%" stop-color="#c9c3b5"/>
          <stop offset="100%" stop-color="#b5afa0"/>
        </linearGradient>
        <linearGradient id="${uid}-label" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3a3a3a"/>
          <stop offset="100%" stop-color="#1a1a1a"/>
        </linearGradient>
        <linearGradient id="${uid}-term" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#9a9588"/>
          <stop offset="40%" stop-color="#7a7568"/>
          <stop offset="100%" stop-color="#5c574c"/>
        </linearGradient>
        <linearGradient id="${uid}-face" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="rgba(255,255,255,0.22)"/>
          <stop offset="35%" stop-color="rgba(255,255,255,0)"/>
          <stop offset="100%" stop-color="rgba(0,0,0,0.08)"/>
        </linearGradient>
        <linearGradient id="${uid}-port" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#1e293b"/>
          <stop offset="100%" stop-color="#0f172a"/>
        </linearGradient>
        <filter id="${uid}-inset" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1" stdDeviation="0.6" flood-color="#000" flood-opacity="0.35"/>
        </filter>
      </defs>`;
  }

  function screw(cx, cy, r) {
    return `
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="#4a453c" stroke="#2a2620" stroke-width="0.6"/>
      <circle cx="${cx}" cy="${cy}" r="${r * 0.55}" fill="#6b6558" stroke="#3a3530" stroke-width="0.4"/>
      <line x1="${cx - r * 0.35}" y1="${cy}" x2="${cx + r * 0.35}" y2="${cy}" stroke="#2a2620" stroke-width="0.7"/>
      <line x1="${cx}" y1="${cy - r * 0.35}" x2="${cx}" y2="${cy + r * 0.35}" stroke="#2a2620" stroke-width="0.7"/>`;
  }

  function terminalBase(w, y0, rows, cols, uid) {
    const h = 52;
    const padX = 8;
    const padY = 7;
    const fill = uid ? `url(#${uid}-term)` : '#7a7568';
    let html = `
      <rect x="4" y="${y0}" width="${w - 8}" height="${h}" rx="2" fill="${fill}" stroke="#5a5548" stroke-width="0.7"/>
      <rect x="6" y="${y0 + 2}" width="${w - 12}" height="${h - 4}" rx="1.5" fill="#6e695c" opacity="0.55"/>`;
    const usableW = w - padX * 2;
    const usableH = h - padY * 2;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const cx = padX + (usableW * (c + 0.5)) / cols;
        const cy = y0 + padY + (usableH * (r + 0.5)) / rows;
        html += screw(cx, cy, 3.1);
      }
    }
    return html;
  }

  function ledGrid(leds, x, y, cols, cellW, cellH) {
    if (!leds.length) return '';
    let html = '';
    leds.forEach((st, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const cx = x + col * cellW + cellW / 2;
      const cy = y + row * cellH + cellH / 2;
      const fill = ledFill(st);
      const glow = ledGlow(st);
      html += `
        <rect x="${cx - 3.2}" y="${cy - 3.2}" width="6.4" height="6.4" rx="0.8"
          fill="#2a2a2a" stroke="#1a1a1a" stroke-width="0.4"/>
        <circle cx="${cx}" cy="${cy}" r="2.1" fill="${fill}"
          ${glow !== 'none' ? `style="filter:drop-shadow(0 0 1.6px ${glow})"` : ''}/>`;
    });
    return html;
  }

  function statusStrip(leds, w, y) {
    const cols = leds.length > 8 ? 8 : Math.max(leds.length, 1);
    const rows = Math.ceil(leds.length / cols) || 1;
    const cellW = (w - 16) / cols;
    const cellH = 11;
    const boxH = rows * cellH + 8;
    return `
      <rect x="8" y="${y}" width="${w - 16}" height="${boxH}" rx="2"
        fill="#2f2f2f" stroke="#1a1a1a" stroke-width="0.6"/>
      <rect x="9" y="${y + 1}" width="${w - 18}" height="3" fill="rgba(255,255,255,0.06)"/>
      ${ledGrid(leds, 8, y + 4, cols, cellW, cellH)}`;
  }

  function labelBand(w, catalog, slot, uid) {
    const fill = uid ? `url(#${uid}-label)` : '#1a1a1a';
    return `
      <rect x="3" y="3" width="${w - 6}" height="36" rx="1.5" fill="${fill}"/>
      <rect x="4" y="4" width="${w - 8}" height="8" fill="rgba(255,255,255,0.06)"/>
      <text x="${w / 2}" y="17" text-anchor="middle" fill="#f5f0e6"
        font-family="ui-monospace, Consolas, monospace" font-size="9" font-weight="700">${escapeHtml(catalog)}</text>
      <text x="${w / 2}" y="30" text-anchor="middle" fill="#a8a29a"
        font-family="ui-sans-serif, system-ui, sans-serif" font-size="7.5">SLOT ${escapeHtml(String(slot ?? '—'))}</text>`;
  }

  function bodyShell(w, h, uid) {
    return `
      <rect x="1.5" y="1.5" width="${w - 3}" height="${h - 3}" rx="3.5"
        fill="url(#${uid}-body)" stroke="#8a8478" stroke-width="1.1"/>
      <rect x="1.5" y="1.5" width="${w - 3}" height="${h - 3}" rx="3.5" fill="url(#${uid}-face)"/>
      <rect x="4" y="40" width="${w - 8}" height="${h - 98}" rx="2"
        fill="#d2cdc0" stroke="#b0aa9c" stroke-width="0.5" opacity="0.55"/>`;
  }

  function kindBadge(w, y, label) {
    return `
      <text x="${w / 2}" y="${y}" text-anchor="middle" fill="#5c574c"
        font-family="ui-sans-serif, system-ui, sans-serif" font-size="7.5"
        letter-spacing="0.06em">${escapeHtml(label)}</text>`;
  }

  function renderAdapterSvg(mod, uid) {
    const w = ADAPTER_W;
    const h = MOD_H;
    const cat = mod.catalog || mod.type || '1794-AENT';
    return `
      <svg class="flex-phys-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
        xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        ${svgDefs(uid)}
        ${bodyShell(w, h, uid)}
        ${labelBand(w, cat, mod.slot ?? 0, uid)}
        ${kindBadge(w, 52, 'ETHERNET ADAPTER')}
        <rect x="14" y="62" width="${w - 28}" height="78" rx="3" fill="#c0baac" stroke="#9a9486" stroke-width="0.7"/>
        <text x="${w / 2}" y="78" text-anchor="middle" fill="#4a453c"
          font-family="ui-sans-serif, system-ui, sans-serif" font-size="8">Allen-Bradley</text>
        <text x="${w / 2}" y="92" text-anchor="middle" fill="#6b6558"
          font-family="ui-sans-serif, system-ui, sans-serif" font-size="7">FLEX I/O</text>
        <!-- RJ45 ports -->
        <g transform="translate(0,0)">
          <rect x="28" y="102" width="42" height="28" rx="2" fill="url(#${uid}-port)" stroke="#334155" stroke-width="0.8"/>
          <rect x="33" y="107" width="32" height="14" rx="1" fill="#020617" stroke="#475569" stroke-width="0.5"/>
          <rect x="38" y="121" width="22" height="5" rx="0.5" fill="#1e293b"/>
          <circle cx="36" cy="110" r="1.4" fill="#22c55e"/>
          <circle cx="62" cy="110" r="1.4" fill="#3b82f6"/>
          <rect x="${w - 70}" y="102" width="42" height="28" rx="2" fill="url(#${uid}-port)" stroke="#334155" stroke-width="0.8"/>
          <rect x="${w - 65}" y="107" width="32" height="14" rx="1" fill="#020617" stroke="#475569" stroke-width="0.5"/>
          <rect x="${w - 60}" y="121" width="22" height="5" rx="0.5" fill="#1e293b"/>
          <circle cx="${w - 62}" cy="110" r="1.4" fill="#22c55e"/>
          <circle cx="${w - 36}" cy="110" r="1.4" fill="#94a3b8"/>
        </g>
        <!-- net / status LEDs -->
        <g>
          <circle cx="24" cy="156" r="3" fill="#22c55e" style="filter:drop-shadow(0 0 1.8px rgba(34,197,94,0.7))"/>
          <text x="34" y="159" fill="#5c574c" font-size="7" font-family="ui-sans-serif, system-ui, sans-serif">OK</text>
          <circle cx="58" cy="156" r="3" fill="#3b82f6" style="filter:drop-shadow(0 0 1.8px rgba(59,130,246,0.55))"/>
          <text x="68" y="159" fill="#5c574c" font-size="7" font-family="ui-sans-serif, system-ui, sans-serif">NET</text>
          <circle cx="98" cy="156" r="3" fill="#6b7280"/>
          <text x="108" y="159" fill="#5c574c" font-size="7" font-family="ui-sans-serif, system-ui, sans-serif">LINK</text>
        </g>
        <!-- rotary / node address window -->
        <rect x="${w / 2 - 22}" y="170" width="44" height="22" rx="2" fill="#2a2a2a" stroke="#1a1a1a" stroke-width="0.6"/>
        <circle cx="${w / 2}" cy="181" r="7" fill="#3f3f46" stroke="#27272a" stroke-width="0.8"/>
        <line x1="${w / 2}" y1="176" x2="${w / 2}" y2="181" stroke="#e5e5e5" stroke-width="1.2"/>
        ${terminalBase(w, h - 56, 2, 8, uid)}
      </svg>`;
  }

  function renderIoSvg(mod, visual, leds, uid) {
    const w = IO_W;
    const h = MOD_H;
    const cat = mod.catalog || mod.type || '—';
    const dir = visual.indexOf('Input') >= 0 ? 'DIGITAL INPUT' : visual.indexOf('Output') >= 0 ? 'DIGITAL OUTPUT' : 'MODULE';
    const pts = leds.length || channelCapacity(mod, visual) || '?';
    const screwCols = leds.length > 8 ? 8 : Math.max(4, Math.min(leds.length || 4, 8));
    const screwRows = leds.length > 8 ? 2 : 2;

    return `
      <svg class="flex-phys-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
        xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        ${svgDefs(uid)}
        ${bodyShell(w, h, uid)}
        ${labelBand(w, cat, mod.slot ?? '—', uid)}
        ${kindBadge(w, 52, dir)}
        <text x="${w / 2}" y="64" text-anchor="middle" fill="#7a7568"
          font-family="ui-monospace, Consolas, monospace" font-size="8">${pts} PT</text>
        ${statusStrip(leds, w, 74)}
        <!-- side keying / rail hooks -->
        <rect x="0.5" y="110" width="3" height="36" rx="0.5" fill="#8a8478"/>
        <rect x="${w - 3.5}" y="110" width="3" height="36" rx="0.5" fill="#8a8478"/>
        <!-- mid face plate -->
        <rect x="10" y="160" width="${w - 20}" height="36" rx="2" fill="#cfc9bb" stroke="#a8a294" stroke-width="0.5"/>
        <text x="${w / 2}" y="176" text-anchor="middle" fill="#5c574c"
          font-family="ui-sans-serif, system-ui, sans-serif" font-size="7">FLEX I/O</text>
        <text x="${w / 2}" y="188" text-anchor="middle" fill="#7a7568"
          font-family="ui-sans-serif, system-ui, sans-serif" font-size="6.5">1794</text>
        ${terminalBase(w, h - 56, screwRows, screwCols, uid)}
      </svg>`;
  }

  function renderUnknownSvg(mod, uid) {
    const w = IO_W;
    const h = MOD_H;
    const cat = mod.catalog || mod.type || 'UNKNOWN';
    return `
      <svg class="flex-phys-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
        xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        ${svgDefs(uid)}
        ${bodyShell(w, h, uid)}
        ${labelBand(w, cat, mod.slot ?? '—', uid)}
        ${kindBadge(w, 72, 'UNSUPPORTED')}
        <text x="${w / 2}" y="120" text-anchor="middle" fill="#7a7568"
          font-family="ui-sans-serif, system-ui, sans-serif" font-size="8">no faceplate</text>
        ${terminalBase(w, h - 56, 2, 4, uid)}
      </svg>`;
  }

  let _uidSeq = 0;
  function nextUid() {
    _uidSeq += 1;
    return `fx${_uidSeq}`;
  }

  /**
   * @param {object} ad adapter
   * @param {object} mod module from HardwareIOModel
   * @param {{ selected?: boolean, moduleKey?: string }} opts
   */
  function renderModule(ad, mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const key = opts.moduleKey || `${ad?.rio_name || ''}::${mod.slot}`;
    const selected = !!opts.selected;
    const used = mod.channels_used ?? (mod.channels || []).length;
    const unres = mod.channels_unresolved ?? 0;
    const total = mod.channel_capacity || channelCapacity(mod, visual);
    const cat = mod.catalog || mod.type || '—';
    const title = isAdapterVisual(visual)
      ? `Slot ${mod.slot ?? 0}\n${cat}\nEthernet adapter`
      : `Slot ${mod.slot ?? '—'}\n${cat}\n${used} resolved · ${unres} unresolved · ${total} ch`;
    const uid = nextUid();
    const leds = ledStates(mod, visual);
    let svg;
    if (visual === 'Flex1794Adapter') svg = renderAdapterSvg(mod, uid);
    else if (visual === 'Flex1794Unknown') svg = renderUnknownSvg(mod, uid);
    else svg = renderIoSvg(mod, visual, leds, uid);

    const widthCls = isAdapterVisual(visual) ? 'flex-phys-mod--adapter' : 'flex-phys-mod--io';
    const selCls = selected ? ' selected' : '';
    return `<button type="button" data-hw-mod="${escapeHtml(key)}"
      class="flex-phys-mod ${widthCls}${selCls}" title="${escapeHtml(title)}"
      data-flex-visual="${escapeHtml(visual)}">${svg}</button>`;
  }

  function dinRailSvg(totalW) {
    const w = Math.max(totalW, 200);
    const id = nextUid();
    return `
      <svg class="flex-phys-din" viewBox="0 0 ${w} 14" width="${w}" height="14"
        xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="none">
        <defs>
          <linearGradient id="${id}-din" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#4b5563"/>
            <stop offset="45%" stop-color="#1f2937"/>
            <stop offset="100%" stop-color="#111827"/>
          </linearGradient>
          <linearGradient id="${id}-bus" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#a16207"/>
            <stop offset="50%" stop-color="#eab308"/>
            <stop offset="100%" stop-color="#a16207"/>
          </linearGradient>
        </defs>
        <rect x="0" y="2" width="${w}" height="10" rx="1.5" fill="url(#${id}-din)" stroke="#0f172a" stroke-width="0.6"/>
        <rect x="0" y="5" width="${w}" height="2.2" fill="url(#${id}-bus)" opacity="0.85"/>
        <rect x="0" y="3" width="${w}" height="1.2" fill="rgba(255,255,255,0.12)"/>
      </svg>`;
  }

  /**
   * Render continuous FLEX assemblies for adapters.
   * @param {object[]} adapters
   * @param {{ selectedKey?: string, moduleKeyFn?: Function, escapeHtml?: Function }} opts
   */
  function renderRacks(adapters, opts) {
    opts = opts || {};
    const selectedKey = opts.selectedKey || '';
    const keyFn = opts.moduleKeyFn || ((rio, slot) => `${rio || ''}::${slot}`);

    const racks = (adapters || []).map((ad) => {
      const aent = (ad.modules || []).find((m) => m.is_adapter_card);
      const aentLabel = aent ? (aent.catalog || aent.type || 'AENT') : '—';
      const mods = [...(ad.modules || [])].sort((a, b) => (Number(a.slot) || 0) - (Number(b.slot) || 0));
      const cards = mods.map((mod) => {
        const key = keyFn(ad.rio_name, mod.slot);
        return renderModule(ad, mod, { selected: key === selectedKey, moduleKey: key });
      }).join('');

      let railW = 24;
      mods.forEach((mod) => {
        railW += (isAdapterVisual(resolveVisual(mod)) ? ADAPTER_W : IO_W) + GAP;
      });

      return `
        <div class="flex-rack-card flex-phys-rack-card">
          <div class="flex-rack-meta">
            <span class="rio">${escapeHtml(ad.rio_name || '—')}</span>
            <span class="mono">${escapeHtml(ad.eipcfg_name || ad.name || '')}</span>
            <span>AENT ${escapeHtml(aentLabel)}</span>
            <span class="ml-auto mono">${escapeHtml(ad.targetip || '')} · ${escapeHtml(ad.panel || '—')}</span>
          </div>
          <div class="flex-phys-rack">
            <div class="flex-phys-row">${cards}</div>
            <div class="flex-phys-rail">${dinRailSvg(railW)}</div>
          </div>
        </div>`;
    }).join('');

    return `<div class="flex-rack-wrap flex-phys-wrap">${racks}</div>`;
  }

  global.FlexRack = {
    flexVisualMap,
    normalizeCatalog,
    resolveVisual,
    ledStates,
    renderModule,
    renderRacks,
    IO_W,
    ADAPTER_W,
    MOD_H,
  };
})(typeof window !== 'undefined' ? window : globalThis);
