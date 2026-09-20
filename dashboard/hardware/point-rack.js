/**
 * Allen-Bradley 1734 POINT I/O rack — engineering schematic presentation.
 *
 * Same visual language as FLEX (clean cards), POINT proportions (narrow modules).
 * Wired ONLY to HardwareIOModel / RUN evidence.
 * Do NOT invent modules. Unknown catalog → generic POINT card with exact catalog.
 * Channel LEDs = engineering resolution (assigned / review / spare), NOT live PLC state.
 */
(function (global) {
  'use strict';

  const pointVisualMap = {
    '1734-AENT': 'adapter',
    '1734-AENTR': 'adapter',
    '1734-IB8': 'in8',
    '1734-OB8': 'out8',
    '1734-OB8E': 'out8',
    '1734-IA4': 'in4',
    '1734-OA4': 'out4',
    '1734-IB4': 'in4',
    '1734-OB4': 'out4',
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
    if (pointVisualMap[cat]) return pointVisualMap[cat];
    if (/AENTR?$/.test(cat)) return 'adapter';
    if (/I[AB]8/.test(cat)) return 'in8';
    if (/O[ABW]8/.test(cat)) return 'out8';
    if (/I[AB]4/.test(cat)) return 'in4';
    if (/O[ABW]4/.test(cat)) return 'out4';
    return 'unknown';
  }

  function shortName(mod, visual) {
    const cat = String(mod.catalog || mod.type || '');
    const m = cat.match(/1734-([A-Z0-9]+)/i);
    if (m) return m[1].replace(/\/.*$/, '');
    if (visual === 'adapter') return 'AENTR';
    if (visual === 'in8') return 'DI8';
    if (visual === 'out8') return 'DO8';
    if (visual === 'in4') return 'DI4';
    if (visual === 'out4') return 'DO4';
    return 'MOD';
  }

  function descLabel(visual, ch) {
    if (visual === 'adapter') return 'Adapter';
    if (visual === 'in8') return '8 In';
    if (visual === 'out8') return '8 Out';
    if (visual === 'in4') return '4 In';
    if (visual === 'out4') return '4 Out';
    if (visual === 'unknown') return 'POINT';
    return ch ? `${ch} ch` : 'Module';
  }

  function brandDirection(visual) {
    if (visual === 'adapter') return 'POINT I/O';
    if (visual === 'in8' || visual === 'in4') return 'INPUT';
    if (visual === 'out8' || visual === 'out4') return 'OUTPUT';
    return 'POINT I/O';
  }

  function directionClass(visual) {
    if (visual === 'adapter') return 'adapter';
    if (visual === 'in8' || visual === 'in4') return 'input';
    if (visual === 'out8' || visual === 'out4') return 'output';
    return 'adapter';
  }

  function channelCapacity(mod, visual) {
    const cap = Number(mod.channel_capacity);
    if (cap > 0) return cap;
    if (visual === 'in8' || visual === 'out8') return 8;
    if (visual === 'in4' || visual === 'out4') return 4;
    return (mod.channels || []).length;
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

  /**
   * Engineering-resolution indicators (not live PLC ON/OFF):
   *   ok/assigned = green, amber/review = amber, off/spare = gray
   */
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
    const n = Math.min(cap > 0 ? cap : channels.length, 8);
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const ch = byBit.get(i);
      if (!ch) out.push('off');
      else if (ch.logical_endpoint && ch.logical_endpoint.name) out.push('ok');
      else if (ch.engineering_owner) out.push('ok');
      else if (isTrulyUnresolved(ch)) out.push('amber');
      else out.push('off');
    }
    return out;
  }

  function channelRowsHtml(mod, visual) {
    const states = ledStates(mod, visual);
    if (!states.length) {
      // Unknown catalog with no capacity — still show a compact placeholder
      return '<div class="point-adapter-meta">Exact catalog · no channel map</div>';
    }
    return `<div class="point-channels">${states.map((st, i) => {
      const cls = st === 'ok' ? 'point-led on'
        : st === 'amber' ? 'point-led amber'
        : 'point-led off';
      return `<div class="point-ch"><span class="${cls}" title="ch ${i} resolution"></span><span>${i}</span></div>`;
    }).join('')}</div>`;
  }

  function renderAdapterFace(mod, opts) {
    opts = opts || {};
    const cat = mod.catalog || mod.type || '1734-AENTR';
    const key = opts.moduleKey || '';
    const sel = opts.selected ? ' selected' : '';
    const rio = opts.rioName || '';
    return `<button type="button" data-hw-mod="${escapeHtml(key)}" class="point-adapter point-adapter-clean${sel}" title="${escapeHtml(cat)}">
      <div class="point-face-head">
        <div class="point-rio-name">${escapeHtml(rio || shortName(mod, 'adapter'))}</div>
        <div class="point-cat">${escapeHtml(cat)}</div>
        <div class="point-dir adapter">POINT I/O</div>
      </div>
      <div class="point-face-body">
        <div class="point-adapter-meta">ADAPTER</div>
        <div class="point-status-row"><span class="point-led on" title="NET status cue"></span>NET</div>
        <div class="point-status-row"><span class="point-led on" title="MOD status cue"></span>MOD</div>
      </div>
    </button>`;
  }

  function renderIoFace(mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const cat = mod.catalog || mod.type || '—';
    const key = opts.moduleKey || '';
    const sel = opts.selected ? ' selected' : '';
    const unknown = visual === 'unknown' ? ' point-unknown' : '';
    const dir = brandDirection(visual);
    const dcls = directionClass(visual);
    const slot = mod.slot ?? '—';
    return `<button type="button" data-hw-mod="${escapeHtml(key)}" class="point-module${sel}${unknown}"
      title="${escapeHtml(`Slot ${slot} · ${cat}`)}">
      <div class="point-face-head">
        <div class="point-slot-num">SLOT ${escapeHtml(String(slot))}</div>
        <div class="point-cat" title="${escapeHtml(cat)}">${escapeHtml(cat)}</div>
        <div class="point-dir ${dcls}">${escapeHtml(dir)}</div>
      </div>
      <div class="point-face-body">
        ${channelRowsHtml(mod, visual)}
      </div>
    </button>`;
  }

  function renderModule(ad, mod, opts) {
    opts = opts || {};
    const visual = resolveVisual(mod);
    const key = opts.moduleKey || `${ad?.rio_name || ''}::${mod.slot}`;
    if (visual === 'adapter') {
      return renderAdapterFace(mod, {
        selected: !!opts.selected,
        moduleKey: key,
        rioName: ad?.rio_name || '',
      });
    }
    return renderIoFace(mod, { selected: !!opts.selected, moduleKey: key });
  }

  function physicalRackHtml(ad, mods, selectedKey, keyFn) {
    const faces = mods.map((mod) => {
      const key = keyFn(ad.rio_name, mod.slot);
      return renderModule(ad, mod, { selected: key === selectedKey, moduleKey: key });
    }).join('');

    return `
      <div class="point-rack-viewport">
        <div class="point-rack-wrap-inner">
          <div class="point-din-rail" aria-hidden="true"></div>
          <div class="point-rack-row">${faces}</div>
        </div>
      </div>`;
  }

  function renderRacks(adapters, opts) {
    opts = opts || {};
    const selectedKey = opts.selectedKey || '';
    const keyFn = opts.moduleKeyFn || ((rio, slot) => `${rio || ''}::${slot}`);

    if (!(adapters || []).length) {
      return `<div class="sf-empty-state text-sm py-8 text-center">
        <div class="sf-empty-title">NO POINT ADAPTERS</div>
        <div class="sf-empty-detail">HardwareIOModel has no 1734 adapters for this filter.</div>
      </div>`;
    }

    const cards = adapters.map((ad) => {
      const aent = (ad.modules || []).find((m) => m.is_adapter_card);
      const mods = [...(ad.modules || [])].sort((a, b) => (Number(a.slot) || 0) - (Number(b.slot) || 0));
      const aentCat = aent ? (aent.catalog || aent.type || '1734-AENTR') : '1734-AENTR';
      const rio = ad.rio_name || '';
      const rack = physicalRackHtml(ad, mods, selectedKey, keyFn);

      return `
        <div class="point-phys-rack-card expanded" data-hw-rio="${escapeHtml(rio)}" data-hw-family="1734">
          <div class="point-phys-rack-meta">
            <span class="rio">${escapeHtml(rio || '—')}</span>
            <span class="mono">${escapeHtml(ad.eipcfg_name || ad.name || '')}</span>
            <span class="point-family-badge">POINT I/O</span>
            <span>${escapeHtml(aentCat)}</span>
            <span class="ml-auto mono">${escapeHtml(ad.targetip || '')} · ${escapeHtml(ad.panel || '—')}</span>
          </div>
          ${mods.length
            ? rack
            : `<div class="point-aent-hint">No modules on this adapter in HardwareIOModel.</div>`}
        </div>`;
    }).join('');

    return `<div class="point-rack-wrap point-phys-wrap">${cards}</div>`;
  }

  global.PointRack = {
    pointVisualMap,
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
