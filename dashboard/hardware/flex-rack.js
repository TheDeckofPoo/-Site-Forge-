/**
 * Physical Allen-Bradley 1794 FLEX I/O rack — visual language from
 * site_forge_flexio_reference.html. Wired only to HardwareIOModel data.
 * Full rack always visible (AENT + all I/O modules). Tree expand is separate.
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
      else if (isTrulyUnresolved(ch)) out.push('amber');
      else out.push('off');
    }
    return out;
  }

  /** True only when owner resolution failed — never ordinary SPARE capacity (Gate D/K). */
  function isTrulyUnresolved(ch) {
    if (!ch) return false;
    const ownerState = String(ch.owner_state || ch.resolution_status || '').toUpperCase();
    if (ownerState === 'UNRESOLVED_OWNER') return true;
    if (ownerState === 'PROVEN_SPARE' || ownerState === 'ENGINEER_SPARE' || ownerState === 'ASSIGNED') {
      return false;
    }
    if (ch.engineering_owner || (ch.logical_endpoint && ch.logical_endpoint.name)) return false;
    const st = String(ch.status || ch.resolve_status || ch.endpoint_status || '').toLowerCase();
    if (/unresolv|error|fail|missing|conflict/.test(st)) return true;
    const how = String(ch.provenance?.assign_how || ch.assign_how || '').toLowerCase();
    if (/unresolv|error|fail|conflict/.test(how)) return true;
    if (ch.unresolved === true || ch.is_unresolved === true) return true;
    return false;
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
    // Gate A: no black RJ45 jack rectangles — they obscured catalog/face text.
    // Child FLEX I/O module width (×1.20) and rack architecture unchanged.
    return `<button type="button" data-hw-mod="${escapeHtml(key)}" class="flex-adapter flex-adapter-clean${sel}" title="${escapeHtml(cat)}">
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
      <div class="flex-base-foot"></div>
    </button>`;
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

  function renderModule(ad, mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const key = opts.moduleKey || `${ad?.rio_name || ''}::${mod.slot}`;
    if (visual === 'adapter') {
      return renderAdapterFace(mod, { selected: !!opts.selected, moduleKey: key });
    }
    return renderIoFace(mod, { selected: !!opts.selected, moduleKey: key });
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
   * Always show full physical rack(s) — AENT + all I/O modules visible.
   * Expand/collapse of AENT children lives in the Hardware tree, not here.
   */
  function renderRacks(adapters, opts) {
    opts = opts || {};
    const selectedKey = opts.selectedKey || '';
    const keyFn = opts.moduleKeyFn || ((rio, slot) => `${rio || ''}::${slot}`);

    if (!(adapters || []).length) {
      return `<div class="text-sm text-slate-500 py-10 text-center">No adapters for this filter (HardwareIOModel).</div>`;
    }

    const cards = adapters.map((ad) => {
      const aent = (ad.modules || []).find((m) => m.is_adapter_card);
      const mods = [...(ad.modules || [])].sort((a, b) => (Number(a.slot) || 0) - (Number(b.slot) || 0));
      const aentCat = aent ? (aent.catalog || aent.type || '1794-AENT') : '1794-AENT';
      const rio = ad.rio_name || '';
      const rack = physicalRackHtml(ad, mods, selectedKey, keyFn);

      return `
        <div class="flex-phys-rack-card expanded" data-hw-rio="${escapeHtml(rio)}">
          <div class="flex-phys-rack-meta">
            <span class="rio">${escapeHtml(rio || '—')}</span>
            <span class="mono">${escapeHtml(ad.eipcfg_name || ad.name || '')}</span>
            <span>${escapeHtml(aentCat)}</span>
            <span class="ml-auto mono">${escapeHtml(ad.targetip || '')} · ${escapeHtml(ad.panel || '—')}</span>
          </div>
          ${mods.length
            ? rack
            : `<div class="flex-aent-hint">No modules on this adapter in HardwareIOModel.</div>`}
        </div>`;
    }).join('');

    return `<div class="flex-rack-wrap flex-phys-wrap">${cards}</div>`;
  }

  global.FlexRack = {
    flexVisualMap,
    normalizeCatalog,
    resolveVisual,
    ledStates,
    isTrulyUnresolved,
    renderModule,
    renderRacks,
    shortName,
    descLabel,
    channelCapacity,
  };
})(typeof window !== 'undefined' ? window : globalThis);
