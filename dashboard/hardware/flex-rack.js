/**
 * Physical Allen-Bradley 1794 FLEX I/O rack — visual language from
 * site_forge_flexio_reference.html. Wired only to HardwareIOModel data.
 * AENT is the primary card; click expands associated I/O modules.
 */
(function (global) {
  'use strict';

  const flexVisualMap = {
    '1794-AENT': 'adapter',
    '1794-AENTR': 'adapter',
    '1794-IA16': 'in16',
    '1794-IB16': 'in16',
    '1794-OA8I': 'out8',
    '1794-OB16P': 'out16',
    '1794-OA16': 'out16',
    '1794-IA8': 'in8',
    '1794-IB8': 'in8',
    '1794-OA8': 'out8',
    '1794-OB8': 'out8',
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function normalizeCatalog(raw) {
    let cat = String(raw || '').trim().toUpperCase();
    cat = cat.replace(/[/_\-][A-Z]\d*$/i, '');
    cat = cat.replace(/\s+/g, '');
    return cat;
  }

  function resolveVisual(mod) {
    if (!mod) return 'unknown';
    if (mod.is_adapter_card) return 'adapter';
    const cat = normalizeCatalog(mod.catalog || mod.type || '');
    if (flexVisualMap[cat]) return flexVisualMap[cat];
    if (/AENTR?$/.test(cat)) return 'adapter';
    if (/I[AB]16|IW16/.test(cat)) return 'in16';
    if (/OB16P?|OW16|OA16/.test(cat)) return 'out16';
    if (/OA8I?|OB8|OW8/.test(cat)) return 'out8';
    if (/I[AB]8/.test(cat)) return 'in8';
    return 'unknown';
  }

  function shortName(mod, visual) {
    const cat = String(mod.catalog || mod.type || '');
    const m = cat.match(/1794-([A-Z0-9]+)/i);
    if (m) return m[1].replace(/\/.*$/, '');
    if (visual === 'adapter') return 'AENT';
    if (visual === 'in16') return 'DI16';
    if (visual === 'out8') return 'DO8';
    if (visual === 'out16') return 'DO16';
    if (visual === 'in8') return 'DI8';
    return 'MOD';
  }

  function descLabel(visual, ch) {
    if (visual === 'adapter') return 'Adapter';
    if (visual === 'in16') return '16 In';
    if (visual === 'in8') return '8 In';
    if (visual === 'out8') return '8 Out';
    if (visual === 'out16') return '16 Out';
    return ch ? `${ch} ch` : 'Module';
  }

  function channelCapacity(mod, visual) {
    const cap = Number(mod.channel_capacity);
    if (cap > 0) return cap;
    if (visual === 'in16' || visual === 'out16') return 16;
    if (visual === 'in8' || visual === 'out8') return 8;
    return (mod.channels || []).length;
  }

  /** LED states from model channels only. */
  function ledStates(mod, visual) {
    if (visual === 'adapter') return [];
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
      if (!ch) out.push('off');
      else if (ch.logical_endpoint && ch.logical_endpoint.name) out.push('ok');
      else out.push('amber');
    }
    return out;
  }

  function screwGrid(count) {
    const n = count || 16;
    let row = '';
    for (let i = 0; i < n; i += 1) row += '<span class="flex-screw"></span>';
    return `<div class="flex-screws">${row}</div><div class="flex-screws screw2">${row}</div>`;
  }

  function sideKeys() {
    return '<span class="flex-side-key left" aria-hidden="true"></span>'
      + '<span class="flex-side-key right" aria-hidden="true"></span>';
  }

  function renderAdapterFace(mod, opts) {
    opts = opts || {};
    const cat = mod.catalog || mod.type || '1794-AENT';
    const key = opts.moduleKey || '';
    const sel = opts.selected ? ' selected' : '';
    const tag = opts.asButton === false ? 'div' : 'button';
    const typeAttr = opts.asButton === false ? '' : 'type="button"';
    const dataAttr = key ? `data-hw-mod="${escapeHtml(key)}"` : '';
    const aentAttr = opts.rioName ? `data-hw-aent="${escapeHtml(opts.rioName)}"` : '';
    return `<${tag} ${typeAttr} ${dataAttr} ${aentAttr} class="flex-adapter${sel}" title="${escapeHtml(cat)}">
      ${sideKeys()}
      <div class="flex-module-top">
        <div class="flex-brand-tiny">Allen-Bradley</div>
        <div class="flex-label-italic">FLEX I/O</div>
        <div class="flex-cat">${escapeHtml(cat)}</div>
      </div>
      <div class="flex-status-leds">
        <div><span></span>LINK 1</div>
        <div><span></span>LINK 2</div>
        <div><span></span>NET</div>
        <div><span></span>OK</div>
      </div>
      <div class="flex-eth">EtherNet/IP</div>
      <div class="flex-port p1"></div>
      <div class="flex-port p2"></div>
      <div class="flex-base-foot"></div>
    </${tag}>`;
  }

  function renderIoFace(mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const cat = mod.catalog || mod.type || '—';
    const key = opts.moduleKey || '';
    const sel = opts.selected ? ' selected' : '';
    const leds = ledStates(mod, visual);
    const show = leds.length > 8 ? leds.slice(0, 8) : leds;
    const inds = show.map((st) => {
      const cls = st === 'ok' ? 'flex-indicator'
        : st === 'amber' ? 'flex-indicator amber'
        : 'flex-indicator off';
      return `<span class="${cls}"></span>`;
    }).join('');
    const screwCount = leds.length > 8 ? 16 : 8;
    return `<button type="button" data-hw-mod="${escapeHtml(key)}" class="flex-io${sel}"
      title="${escapeHtml(`Slot ${mod.slot ?? '—'} · ${cat}`)}">
      ${sideKeys()}
      <div class="flex-module-top">
        <div class="flex-brand-tiny">Allen-Bradley</div>
        <div class="flex-label-italic">FLEX I/O</div>
        <div class="flex-cat">${escapeHtml(cat)}</div>
      </div>
      <div class="flex-term-base">
        <div class="flex-channel-strip">${inds}</div>
        ${screwGrid(screwCount)}
        <div class="flex-base-foot"></div>
      </div>
    </button>`;
  }

  /**
   * Single module face (used by fortna-plus renderFlexModuleCard).
   */
  function renderModule(ad, mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const key = opts.moduleKey || `${ad?.rio_name || ''}::${mod.slot}`;
    if (visual === 'adapter') {
      return renderAdapterFace(mod, {
        selected: !!opts.selected,
        moduleKey: key,
        rioName: ad?.rio_name,
      });
    }
    return renderIoFace(mod, { selected: !!opts.selected, moduleKey: key });
  }

  function moduleMenuItem(ad, mod, selectedKey, keyFn) {
    const key = keyFn(ad.rio_name, mod.slot);
    const visual = resolveVisual(mod);
    const short = shortName(mod, visual);
    const cat = mod.catalog || mod.type || short;
    const sel = key === selectedKey ? ' selected' : '';
    return `<button type="button" class="flex-mod-menu-btn${sel}" data-hw-mod="${escapeHtml(key)}"
      title="${escapeHtml(cat)}">
      <span class="slot">[${mod.slot ?? '—'}]</span>${escapeHtml(short)}
    </button>`;
  }

  function physicalRackHtml(ad, mods, selectedKey, keyFn) {
    const labels = mods.map((mod) => {
      const visual = resolveVisual(mod);
      const key = keyFn(ad.rio_name, mod.slot);
      const short = shortName(mod, visual);
      const desc = descLabel(visual, channelCapacity(mod, visual));
      const sel = key === selectedKey ? ' selected' : '';
      const wcls = visual === 'adapter' ? ' adapter-slot' : '';
      return `<div class="flex-slot-label${wcls}${sel}">${mod.slot ?? '—'}<br><b>${escapeHtml(short)}</b><br>${escapeHtml(desc)}</div>`;
    }).join('');

    const faces = mods.map((mod) => {
      const key = keyFn(ad.rio_name, mod.slot);
      return renderModule(ad, mod, { selected: key === selectedKey, moduleKey: key });
    }).join('');

    return `
      <div class="flex-rack-viewport">
        <div class="flex-rack-wrap-inner">
          <div class="flex-slot-labels">${labels}</div>
          <div class="flex-din-rail" aria-hidden="true"></div>
          <div class="flex-rack-row">${faces}</div>
        </div>
      </div>`;
  }

  /**
   * AENT-first rack list: each adapter is a primary card.
   * Click AENT expands dropdown of associated I/O modules + physical rack.
   *
   * opts:
   *   selectedKey, expandedRio, moduleKeyFn
   */
  function renderRacks(adapters, opts) {
    opts = opts || {};
    const selectedKey = opts.selectedKey || '';
    const expandedRio = opts.expandedRio || '';
    const keyFn = opts.moduleKeyFn || ((rio, slot) => `${rio || ''}::${slot}`);

    if (!(adapters || []).length) {
      return `<div class="text-sm text-slate-500 py-10 text-center">No adapters for this filter (HardwareIOModel).</div>`;
    }

    const cards = adapters.map((ad) => {
      const aent = (ad.modules || []).find((m) => m.is_adapter_card);
      const mods = [...(ad.modules || [])].sort((a, b) => (Number(a.slot) || 0) - (Number(b.slot) || 0));
      const ioMods = mods.filter((m) => !m.is_adapter_card);
      const aentCat = aent ? (aent.catalog || aent.type || '1794-AENT') : '1794-AENT';
      const aentKey = aent ? keyFn(ad.rio_name, aent.slot) : '';
      const rio = ad.rio_name || '';
      const expanded = expandedRio === rio || (!expandedRio && adapters.length === 1);
      const aentSelected = aentKey && aentKey === selectedKey;
      const used = ioMods.reduce((s, m) => s + (m.channels_used ?? (m.channels || []).length), 0);
      const unres = ioMods.reduce((s, m) => s + (m.channels_unresolved ?? 0), 0);

      const aentFace = aent
        ? renderAdapterFace(aent, {
          selected: aentSelected || expanded,
          moduleKey: aentKey,
          rioName: rio,
          asButton: false,
        })
        : `<div class="flex-adapter"><div class="flex-module-top"><div class="flex-cat">AENT</div></div></div>`;

      const menu = mods.map((m) => moduleMenuItem(ad, m, selectedKey, keyFn)).join('');
      const rack = physicalRackHtml(ad, mods, selectedKey, keyFn);

      return `
        <div class="flex-phys-rack-card${expanded ? ' expanded' : ''}" data-hw-rio="${escapeHtml(rio)}">
          <div class="flex-phys-rack-meta">
            <span class="rio">${escapeHtml(rio || '—')}</span>
            <span class="mono">${escapeHtml(ad.eipcfg_name || ad.name || '')}</span>
            <span>${escapeHtml(aentCat)}</span>
            <span class="ml-auto mono">${escapeHtml(ad.targetip || '')} · ${escapeHtml(ad.panel || '—')}</span>
          </div>
          <button type="button" class="flex-aent-card${expanded ? ' expanded' : ''}${aentSelected ? ' selected' : ''}"
            data-hw-aent-toggle="${escapeHtml(rio)}"
            ${aentKey ? `data-hw-mod="${escapeHtml(aentKey)}"` : ''}
            title="Click to show I/O modules on ${escapeHtml(rio)}">
            <div class="flex-aent-face">${aentFace}</div>
            <div class="flex-aent-body">
              <div class="flex-aent-title">${escapeHtml(rio || 'Remote I/O')}</div>
              <div class="flex-aent-sub">${escapeHtml(aentCat)} · EtherNet/IP adapter</div>
              <div class="flex-aent-stats">
                ${ioMods.length} I/O module${ioMods.length === 1 ? '' : 's'}
                · ${used} channel${used === 1 ? '' : 's'} mapped
                ${unres ? ` · <span style="color:#e2a93b">${unres} unresolved</span>` : ''}
              </div>
              <div class="flex-aent-stats" style="color:#27cfff">
                ${expanded ? '▼ Modules on this adapter' : '▶ Click AENT to show modules'}
              </div>
            </div>
            <div class="flex-aent-chevron"><i class="fa-solid fa-chevron-down"></i></div>
          </button>
          <div class="flex-aent-dropdown">
            ${mods.length
              ? `<div class="flex-mod-menu">${menu}</div>${rack}`
              : `<div class="flex-aent-hint">No I/O modules on this adapter in HardwareIOModel.</div>`}
          </div>
        </div>`;
    }).join('');

    return `<div class="flex-rack-wrap flex-phys-wrap">${cards}</div>`;
  }

  global.FlexRack = {
    flexVisualMap,
    normalizeCatalog,
    resolveVisual,
    ledStates,
    renderModule,
    renderRacks,
    shortName,
    descLabel,
  };
})(typeof window !== 'undefined' ? window : globalThis);
