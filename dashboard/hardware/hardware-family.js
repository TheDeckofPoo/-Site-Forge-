/**
 * Hardware family registry (UI) — mirrors tools/scripts/fortna_hardware_family.py.
 *
 * HardwareIOModel → Hardware Family → correct renderer.
 * Never treat 1734 POINT as 1794 FLEX.
 */
(function (global) {
  'use strict';

  const FAMILY_FLEX = '1794';
  const FAMILY_POINT = '1734';
  const FAMILY_ETHERNET_DRIVE = 'ETHERNET_DRIVE';
  const FAMILY_UNKNOWN = 'UNKNOWN';

  const FAMILIES = {
    [FAMILY_FLEX]: {
      family: FAMILY_FLEX,
      label: 'FLEX I/O',
      rendererId: 'flex',
      adapterDefault: '1794-AENT',
    },
    [FAMILY_POINT]: {
      family: FAMILY_POINT,
      label: 'POINT I/O',
      rendererId: 'point',
      adapterDefault: '1734-AENTR',
    },
    [FAMILY_ETHERNET_DRIVE]: {
      family: FAMILY_ETHERNET_DRIVE,
      label: 'Ethernet Drive',
      rendererId: 'ethernet_drive',
      adapterDefault: '',
    },
  };

  function normalizeCatalog(raw) {
    let cat = String(raw || '').trim().toUpperCase();
    cat = cat.replace(/[/_\-][A-Z]\d*$/i, '');
    cat = cat.replace(/\s+/g, '');
    return cat;
  }

  function isEthernetDriveCatalog(catalog) {
    const raw = String(catalog || '').trim();
    if (!raw) return false;
    const u = raw.toUpperCase();
    const cat = normalizeCatalog(raw);
    if (cat.includes('1794') || cat.includes('1734') || cat.includes('1738') || cat.includes('AENT')) {
      return false;
    }
    if (/POWERFLEX|PF70|PF525|PF755|\bPF4\b|20-COMM|20COMM/.test(u)) return true;
    if (/^20[ABCD]|^22[ABC]|^25[ABC]/.test(cat)) return true;
    if (/\bDRIVE\b/.test(u) && !/^\d{4}/.test(cat)) return true;
    return false;
  }

  function detectFamilyFromCatalog(catalog) {
    const cat = normalizeCatalog(catalog);
    if (!cat) return FAMILY_UNKNOWN;
    if (isEthernetDriveCatalog(catalog)) return FAMILY_ETHERNET_DRIVE;
    if (cat.startsWith('1734') || cat.startsWith('1738') || cat.includes('1734') || cat.includes('1738')) {
      return FAMILY_POINT;
    }
    if (cat.startsWith('1794') || cat.includes('1794')) {
      return FAMILY_FLEX;
    }
    return FAMILY_UNKNOWN;
  }

  function detectFamilyFromModules(modules) {
    let sawPoint = false;
    let sawFlex = false;
    let sawDrive = false;
    (modules || []).forEach((m) => {
      const explicit = String(m?.family || '').trim();
      if (explicit === FAMILY_POINT) sawPoint = true;
      if (explicit === FAMILY_FLEX) sawFlex = true;
      if (explicit === FAMILY_ETHERNET_DRIVE) sawDrive = true;
      const fam = detectFamilyFromCatalog(m?.catalog || m?.type || '');
      if (fam === FAMILY_POINT) sawPoint = true;
      if (fam === FAMILY_FLEX) sawFlex = true;
      if (fam === FAMILY_ETHERNET_DRIVE) sawDrive = true;
    });
    if (sawPoint) return FAMILY_POINT;
    if (sawFlex) return FAMILY_FLEX;
    if (sawDrive) return FAMILY_ETHERNET_DRIVE;
    return FAMILY_UNKNOWN;
  }

  function adapterFamily(ad) {
    if (!ad) return FAMILY_UNKNOWN;
    const explicit = String(ad.family || '').trim();
    if (explicit === FAMILY_POINT || explicit === FAMILY_FLEX || explicit === FAMILY_ETHERNET_DRIVE) {
      return explicit;
    }
    return detectFamilyFromModules(ad.modules || []);
  }

  function rendererIdForAdapter(ad) {
    const fam = adapterFamily(ad);
    if (fam === FAMILY_POINT) return 'point';
    if (fam === FAMILY_FLEX) return 'flex';
    if (fam === FAMILY_ETHERNET_DRIVE) return 'ethernet_drive';
    // Unknown: prefer Flex visual only when no POINT catalog present
    return 'flex';
  }

  /**
   * Dispatch rack rendering by family. 1794 FLEX renderer stays frozen;
   * 1734 POINT uses PointRack when available.
   */
  /** Generic industrial VFD / Ethernet drive card (not Flex AENT chrome). */
  function renderEthernetDriveCard(ad) {
    const esc = (s) => String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    const mods = ad?.modules || [];
    const head = mods.find((m) => String(m.connection || '').toUpperCase() === 'HEADNODE') || mods[0] || {};
    const catalog = String(head.type || head.catalog || ad?.catalog || 'PowerFlex').trim();
    const brand = /powerflex|allen|ab\b/i.test(catalog) || /powerflex/i.test(String(ad?.name || ''))
      ? 'Allen-Bradley'
      : 'Ethernet Drive';
    const product = /powerflex/i.test(catalog) ? 'PowerFlex' : (catalog.split('-')[0] || 'Drive');
    const engName = String(ad?.rio_name || ad?.name || head.name || 'Drive').trim();
    const ip = String(ad?.targetip || ad?.ip || '').trim();
    const part = String(head.name || catalog || '').trim();
    return `
      <div class="hw-vfd-card rounded-xl border border-slate-700 bg-gradient-to-b from-[#121a24] to-[#0a1018] p-3 min-w-[11rem] max-w-[14rem] shadow-lg" data-rio="${esc(engName)}">
        <div class="rounded-lg border border-slate-600 bg-[#0c1219] px-3 py-4 text-center space-y-1">
          <div class="text-[10px] uppercase tracking-widest text-slate-500">${esc(brand)}</div>
          <div class="text-base font-semibold text-slate-100">${esc(product)}</div>
          <div class="text-[10px] mono text-sky-300/90 break-all">${esc(part)}</div>
          <div class="flex justify-center gap-4 pt-2 text-[9px] text-slate-500">
            <span><span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500/80 mr-1"></span>STS</span>
            <span><span class="inline-block w-1.5 h-1.5 rounded-full bg-sky-500/80 mr-1"></span>NET</span>
          </div>
        </div>
        <div class="mt-2 text-center space-y-0.5">
          <div class="text-xs font-medium text-slate-200 mono">${esc(engName)}</div>
          ${ip ? `<div class="text-[10px] mono text-slate-400">${esc(ip)}</div>` : ''}
        </div>
      </div>`;
  }

  function renderRacks(adapters, opts) {
    opts = opts || {};
    const list = adapters || [];
    if (!list.length) {
      return '<div class="text-sm text-slate-500 py-10 text-center">No adapters for this filter (HardwareIOModel).</div>';
    }

    // Group consecutive adapters by renderer so mixed sites keep both visuals
    const cards = list.map((ad) => {
      const rid = rendererIdForAdapter(ad);
      if (rid === 'ethernet_drive') {
        return renderEthernetDriveCard(ad);
      }
      if (rid === 'point' && global.PointRack && typeof global.PointRack.renderRacks === 'function') {
        return global.PointRack.renderRacks([ad], opts);
      }
      if (rid !== 'ethernet_drive' && global.FlexRack && typeof global.FlexRack.renderRacks === 'function') {
        return global.FlexRack.renderRacks([ad], opts);
      }
      return `<div class="text-sm text-slate-500 py-4 text-center">No renderer for family ${rid}</div>`;
    });

    return `<div class="flex-rack-wrap flex-phys-wrap hw-family-wrap">${cards.join('')}</div>`;
  }

  function renderModule(ad, mod, opts) {
    const rid = rendererIdForAdapter(ad);
    if (rid === 'point' && global.PointRack && typeof global.PointRack.renderModule === 'function') {
      return global.PointRack.renderModule(ad, mod, opts);
    }
    if (global.FlexRack && typeof global.FlexRack.renderModule === 'function') {
      return global.FlexRack.renderModule(ad, mod, opts);
    }
    return '';
  }

  global.HardwareFamily = {
    FAMILY_FLEX,
    FAMILY_POINT,
    FAMILY_ETHERNET_DRIVE,
    FAMILY_UNKNOWN,
    FAMILIES,
    normalizeCatalog,
    isEthernetDriveCatalog,
    detectFamilyFromCatalog,
    detectFamilyFromModules,
    adapterFamily,
    rendererIdForAdapter,
    renderRacks,
    renderModule,
  };
})(typeof window !== 'undefined' ? window : globalThis);
