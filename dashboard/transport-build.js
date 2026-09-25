/* Transport Build POC — Node-RED style conveyor graph (visual only).
 * Persists to localStorage. Future: feed graph JSON to fortna_autogen.
 */
(function () {
  // v2 invalidates plant-wide canvases saved before ControllerScope filtering.
  const STORE_KEY = 'siteforge.transportBuild.v2';

  // --- Performance instrumentation (hard acceptance gate) ---
  const _perfLog = [];
  const PERF_LOG_MAX = 200;
  let _drawSchematicRaf = 0;
  let _drawWiresRaf = 0;
  let _pendingSchematicArea = null;
  let _pendingWiresOpts = undefined;
  let _nodeIndexByArea = new WeakMap();
  let _areaAssignSaveTimer = 0;
  const AREA_ASSIGN_SAVE_MS = 75;

  function perfRecord(cause, duration_ms, extra) {
    const row = {
      t: Date.now(),
      cause: String(cause || ''),
      duration_ms: Math.round(Number(duration_ms) * 100) / 100,
      ...(extra || {}),
    };
    _perfLog.push(row);
    if (_perfLog.length > PERF_LOG_MAX) _perfLog.shift();
    try {
      if (duration_ms >= 33 && typeof console !== 'undefined' && console.debug) {
        console.debug('[tb-perf]', cause, `${row.duration_ms}ms`, extra || {});
      }
    } catch (_) { /* ignore */ }
    return row;
  }

  function perfSnapshot() {
    return _perfLog.slice(-50);
  }

  function invalidateNodeIndex(area) {
    if (area) _nodeIndexByArea.delete(area);
  }

  function nodeIndex(area) {
    if (!area) return new Map();
    let m = _nodeIndexByArea.get(area);
    if (m) return m;
    m = new Map();
    (area.nodes || []).forEach((n) => {
      if (n && n.id != null) m.set(n.id, n);
    });
    _nodeIndexByArea.set(area, m);
    return m;
  }

  function scheduleDrawSchematic(area) {
    _pendingSchematicArea = area;
    if (_drawSchematicRaf) return;
    _drawSchematicRaf = requestAnimationFrame(() => {
      _drawSchematicRaf = 0;
      const a = _pendingSchematicArea;
      _pendingSchematicArea = null;
      if (a) drawSchematicNow(a);
    });
  }

  function scheduleDrawWires(opts) {
    _pendingWiresOpts = opts;
    if (_drawWiresRaf) return;
    _drawWiresRaf = requestAnimationFrame(() => {
      _drawWiresRaf = 0;
      const o = _pendingWiresOpts;
      _pendingWiresOpts = undefined;
      drawWiresNow(o);
    });
  }

  const KIND_META = {
    conv_straight: { icon: 'fa-minus', color: 'text-sky-300', isConv: true, title: 'Straight' },
    conv_right: { icon: 'fa-arrow-turn-up fa-rotate-90', color: 'text-sky-300', isConv: true, title: '90° Right' },
    conv_left: { icon: 'fa-arrow-turn-down fa-rotate-270', color: 'text-sky-300', isConv: true, title: '90° Left' },
    conv_merge: { icon: 'fa-code-merge', color: 'text-orange-300', isConv: true, isMerge: true, title: 'Merge' },
    conv_spiral: {
      icon: 'fa-dharmachakra',
      color: 'text-teal-300',
      isConv: true,
      isSpiral: true,
      title: 'Spiral',
    },
    motor: { icon: 'fa-gear', color: 'text-amber-300', isConv: false, title: 'Motor', svg: 'motor' },
    estop: { icon: 'fa-hand', color: 'text-red-300', isConv: false, title: 'E-Stop', svg: 'estop' },
    pws: { icon: 'fa-bolt', color: 'text-yellow-300', isConv: false, title: 'Power Supply' },
    encoder: { icon: 'fa-compact-disc', color: 'text-violet-300', isConv: false, title: 'Encoder', svg: 'encoder' },
    photoeye: { icon: 'fa-eye', color: 'text-emerald-300', isConv: false, title: 'Photoeye', svg: 'photoeye' },
  };

  const SPIRAL_MOTOR_MIN = 1;
  const SPIRAL_MOTOR_MAX = 6;
  const SPIRAL_MOTOR_DEFAULT = 3;

  /** Gate 2 — Site Forge canonical ownership bucket (not RUN provenance). */
  const DEFAULT_AREA_NAME = 'Default Area';
  const DEFAULT_AREA_ALIASES = new Set([
    'default area',
    'area_1',
    'unassigned',
    'main_area',
    'run_imported',
  ]);

  function isDefaultAreaName(name) {
    const s = String(name || '').trim().toLowerCase();
    if (!s) return true;
    if (DEFAULT_AREA_ALIASES.has(s)) return true;
    if (/_imported$/i.test(s)) return true;
    return false;
  }

  function isDefaultArea(area) {
    if (!area) return false;
    if (area.isDefault || area.defaultArea) return true;
    return isDefaultAreaName(area.name);
  }

  function ownedTransportNodes(area) {
    return (area?.nodes || []).filter(
      (n) => n && !n.displayContext && n.plcOwned !== false
        && !['OUT_OF_SCOPE', 'UNRESOLVED', 'EXTERNAL_REFERENCE'].includes(String(n.scopeClass || '').toUpperCase()),
    );
  }

  function transportOwnershipCounts() {
    const engineer = {};
    let defaultN = 0;
    let excl = 0;
    const seen = new Set();
    let dupes = 0;
    (tb.areas || []).forEach((area) => {
      (area.nodes || []).forEach((n) => {
        if (!n) return;
        const external = !!(n.displayContext || n.plcOwned === false
          || ['OUT_OF_SCOPE', 'UNRESOLVED', 'EXTERNAL_REFERENCE'].includes(String(n.scopeClass || '').toUpperCase()));
        const tag = String(n.conveyorTag || n.label || n.id || '').trim().toUpperCase();
        if (external) {
          excl += 1;
          return;
        }
        if (!tag) return;
        if (seen.has(tag)) {
          dupes += 1;
          return;
        }
        seen.add(tag);
        if (isDefaultArea(area)) defaultN += 1;
        else {
          const nm = String(area.name || area.id || 'Area');
          engineer[nm] = (engineer[nm] || 0) + 1;
        }
      });
    });
    const engTotal = Object.values(engineer).reduce((s, n) => s + n, 0);
    const discovered = defaultN + engTotal + excl;
    return {
      discovered,
      default: defaultN,
      engineer,
      engineer_total: engTotal,
      proven_exclusions: excl,
      dupes,
      ok: dupes === 0 && discovered === defaultN + engTotal + excl,
    };
  }

  function normalizeSpiralMotors(node) {
    if (!node || !KIND_META[node.kind]?.isSpiral) return [];
    let count = Number(node.motorCount);
    if (!Number.isFinite(count)) count = SPIRAL_MOTOR_DEFAULT;
    count = Math.min(SPIRAL_MOTOR_MAX, Math.max(SPIRAL_MOTOR_MIN, count));
    node.motorCount = count;
    const prev = Array.isArray(node.motors) ? node.motors.map((t) => String(t || '').trim()) : [];
    const next = [];
    for (let i = 0; i < count; i++) next.push(prev[i] || '');
    node.motors = next;
    return next;
  }

  /**
   * PE roles for Autogen — only RUN-supported suffixes or engineer-confirmed.
   * Do NOT silently invent Exit/Jam/Full/Add when evidence is weak.
   */
  const PE_ROLE_ORDER = ['exit', 'add', 'jam', 'full', 'other', 'none'];
  const PE_ROLE_APPLY = ['exit', 'add', 'jam', 'full']; // roles that may drive PLC AOIs
  const PE_ROLE_BADGE = {
    exit: { letter: 'P', cls: 'tb-pe-role-exit', title: 'Exit / product (_P) → Fast_Conv ExitPE' },
    add: { letter: 'A', cls: 'tb-pe-role-add', title: 'Add / entrance → Fast_Conv AddPE' },
    jam: { letter: 'J', cls: 'tb-pe-role-jam', title: 'Jam (_J) → Slow_Jam' },
    full: { letter: 'F', cls: 'tb-pe-role-full', title: 'Full (_F) → Full_PE' },
    other: { letter: '?', cls: 'tb-pe-role-other', title: 'Other (engineer-described; not auto-wired)' },
    none: { letter: '–', cls: 'tb-pe-role-none', title: 'None — intentionally no PLC PE role' },
  };

  /** Returns roles only when tag suffix is RUN-explicit. Empty = PE ROLE REQUIRED. */
  function inferPeRoles(tag) {
    const u = String(tag || '').trim().toUpperCase();
    if (!u) return [];
    // Strict Fortna suffix evidence only — no default 'exit'
    if (/_F\d*$|_FULL/.test(u) && !/_JF|_FDJ/.test(u)) return ['full'];
    if (/_J\d*$|_JAM|_JF|_FDJ/.test(u)) return ['jam'];
    if (/_P\d*$|_P$/.test(u)) return ['exit', 'jam']; // Fortna _P = product/exit (+ jam common)
    if (/_A\d*$|_ADD/.test(u)) return ['add'];
    return [];
  }

  function peEvidenceLevel(tag) {
    const roles = inferPeRoles(tag);
    return roles.length ? 'RUN_EXPLICIT' : 'UNKNOWN';
  }

  function normalizePeRoles(roles) {
    const set = new Set((roles || []).map((r) => String(r || '').toLowerCase()).filter(Boolean));
    if (set.has('none')) return ['none'];
    return PE_ROLE_ORDER.filter((r) => set.has(r));
  }

  function ensurePeRoles(dev, { forceInfer = false } = {}) {
    if (!dev || dev.kind !== 'photoeye') return [];
    // Engineer confirmation always wins
    if (!forceInfer && dev.rolesManual) {
      dev.roles = normalizePeRoles(dev.roles);
      dev.peRoleRequired = false;
      dev.peRoleProvenance = 'ENGINEER_CONFIGURED';
      return dev.roles;
    }
    if (!forceInfer && Array.isArray(dev.roles) && dev.roles.length && !dev.peRoleRequired) {
      // Previously confirmed / RUN-derived — keep unless forceInfer
      dev.roles = normalizePeRoles(dev.roles);
      return dev.roles;
    }
    const inferred = inferPeRoles(dev.tag || dev.name || '');
    if (inferred.length) {
      dev.roles = inferred;
      dev.peRoleRequired = false;
      dev.peRoleProvenance = 'RUN_EXPLICIT';
      return dev.roles;
    }
    // Insufficient evidence — do not invent roles
    dev.roles = [];
    dev.peRoleRequired = true;
    dev.peRoleProvenance = 'UNKNOWN';
    return [];
  }

  function peRoleBadgesHtml(roles, { required } = {}) {
    if (required) {
      return '<span class="tb-pe-role-required" title="PE ROLE REQUIRED — select JAM/FULL/EXIT/ADD/OTHER/NONE">PE ROLE REQUIRED</span>';
    }
    const list = normalizePeRoles(roles);
    if (!list.length) {
      return '<span class="tb-pe-role-required" title="PE ROLE REQUIRED">PE ROLE REQUIRED</span>';
    }
    return list
      .map((r) => {
        const meta = PE_ROLE_BADGE[r];
        if (!meta) return '';
        return `<span class="tb-pe-role ${meta.cls}" title="${escapeHtml(meta.title)}">${meta.letter}</span>`;
      })
      .join('');
  }

  /** Clean SVG icons from engineer sketches (motor / ES / encoder arrows / photoeye). */
  const TB_SVG = {
    motor: `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="4" y="10" width="16" height="12" rx="2" fill="#f59e0b" fill-opacity="0.25" stroke="#fbbf24" stroke-width="1.5"/>
      <circle cx="12" cy="16" r="3.2" stroke="#fde68a" stroke-width="1.3"/>
      <path d="M20 14h6v4h-6" stroke="#fbbf24" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="27" cy="16" r="1.6" fill="#fbbf24"/>
      <path d="M7 10V8.5M12 10V8M17 10V8.5" stroke="#fbbf24" stroke-width="1.2" stroke-linecap="round"/>
    </svg>`,
    estop: `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="16" cy="16" r="11" fill="#7f1d1d" stroke="#f87171" stroke-width="1.6"/>
      <circle cx="16" cy="16" r="8.2" fill="#dc2626"/>
      <text x="16" y="19.5" text-anchor="middle" font-size="9" font-weight="700" font-family="Inter,system-ui,sans-serif" fill="#fff">ES</text>
    </svg>`,
    encoder: `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="16" cy="16" r="7.5" stroke="#c4b5fd" stroke-width="1.6"/>
      <circle cx="16" cy="16" r="2.2" fill="#a78bfa"/>
      <path d="M16 6.5v3M16 22.5v3M6.5 16h3M22.5 16h3" stroke="#a78bfa" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M22.5 9.5a10 10 0 0 1 2.2 3.2" stroke="#ddd6fe" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M24.2 11.2l1.6-.1-.7 1.5" fill="#ddd6fe"/>
      <path d="M9.5 22.5a10 10 0 0 1-2.2-3.2" stroke="#ddd6fe" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M7.8 20.8l-1.6.1.7-1.5" fill="#ddd6fe"/>
    </svg>`,
    photoeye: `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="3" y="10" width="12" height="12" rx="1.5" fill="#064e3b" stroke="#34d399" stroke-width="1.4"/>
      <circle cx="9" cy="16" r="3" stroke="#6ee7b7" stroke-width="1.3"/>
      <circle cx="9" cy="16" r="1.2" fill="#a7f3d0"/>
      <path d="M15 16h12" stroke="#34d399" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="2.5 2"/>
      <path d="M25 13.5l3 2.5-3 2.5" stroke="#6ee7b7" stroke-width="1.2" stroke-linejoin="round"/>
    </svg>`,
  };

  function kindIconHtml(kind, cls) {
    const meta = KIND_META[kind] || {};
    if (meta.svg && TB_SVG[meta.svg]) {
      return `<span class="tb-ico ${cls || meta.color || ''}">${TB_SVG[meta.svg]}</span>`;
    }
    return `<i class="fa-solid ${meta.icon || 'fa-cube'} ${cls || meta.color || ''}"></i>`;
  }

  function paintPaletteIcons() {
    document.querySelectorAll('#tab-transport [data-tb-ico]').forEach((el) => {
      const k = el.getAttribute('data-tb-ico');
      if (TB_SVG[k]) el.innerHTML = `<span class="tb-ico">${TB_SVG[k]}</span>`;
    });
  }

  const tb = {
    areas: [],
    activeAreaId: null,
    // First-class Safety Zones (E-stop grouping) — independent of Areas
    safetyZones: [], // [{ id, name }]
    activeSafetyZoneId: null,
    suppressDefaultArea: false, // Clear Current Project: leave canvas empty until Auto Build / New Area
    selectedId: null, // conveyor node id (primary)
    selectedIds: [], // multi-select (includes selectedId when set)
    selectedDeviceId: null, // device id on that conveyor (inspector device mode)
    dragKind: null,
    linkFrom: null, // { nodeId, port }
    moving: null, // { id, ox, oy }
    connectMode: false,
    connectSourceId: null,
    autoConnectNew: false,
    // Pass 2
    buildContext: { areaId: null, areaName: '', safetyZone: '' },
    history: { past: [], future: [], max: 50 },
    marquee: null,
    showPorts: false,
    continueOpen: false,
    _moveHistoryPushed: false,
    spacePan: false, // Space held → temporary hand cursor / pan
    // Presentation transform (does NOT mutate RUN sourceX/Y/Angle/Length/Width)
    view: {
      zoom: 1,
      canvasScale: null, // from Auto Build metrics; maps RUN length → canvas px
      mode: 'site', // site | area
    },
    metrics: null,
    physicalLayout: false,
    // Clean schematic is the normal view. Geometry debug is Advanced-only.
    viewMode: 'schematic', // schematic | geom-debug
    // Presentation renderer — Lite is the production/default engineering view.
    // detailed | diagnostic restore expensive geometry. Never affects Autogen.
    renderMode: 'lite', // lite | detailed | diagnostic
    // Display-only schematic style (Lite). Never mutates node.x/y / provenance /
    // Autogen geometry. Packed translates whole disconnected components.
    schematicStyle: 'raw', // raw | readable | packed
    // Legacy mirror of schematicStyle === 'readable' (tests / older callers).
    readableSchematic: false,
    showRelationships: false, // relationship-wire layer off by default
    validationDirty: true,
    _validationCache: null,
    _liteGeomCache: Object.create(null), // id → { revision, pathD, midpoint }
    _transportModelCacheKey: null,
    // Gate H — Geometry display authority mode (default looks correct for engineers)
    //   run      = RUN/Physical proven geometry
    //   override = show engineer overrides when present
    //   diagnostic = anchors/entry/exit/provenance/mismatches
    geometryAuthorityMode: 'run', // run | override | diagnostic
    // OFF by default: RUN/Physical mode must preserve proven relative XY
    // (uniform scale + global translation + proven Y invert only).
    // Explicit Advanced toggle may enable presentation lane separation.
    laneSeparate: false,
    // PL-1: after initial layout, freeze presentation offsets so Area moves
    // redraw without musical-chair re-layout of unrelated conveyors.
    // Explicit Rebuild Layout / lane-separate toggle sets forcePresentationRelayout.
    presentationLayoutFrozen: false,
    forcePresentationRelayout: false,
    // Presentation layers — conveyor tags on by default; device text off.
    layers: {
      physical: false,
      // Default OFF — clean engineering layout; toggle is visualization-only
      relationships: false,
      conveyorTags: true,
      motors: false,
      photoeyes: false,
      otherDevices: false,
      deviceLabels: false,
      externalRefs: true,
      area: false,
      safety: false,
      controller: false,
      tracking: false,
    },
    // Control Panel filter toggles — keys discovered from RUN after Auto Build
    cpFilters: {},
    panning: null, // middle-mouse / empty-drag pan: { sx, sy, sl, st }
    workflow: { import: false, autobuild: false, review: true, apply: false, build: false },
  };

  function $(id) {
    return document.getElementById(id);
  }

  function uid(prefix) {
    return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
  }

  function status(msg) {
    const el = $('tb-status');
    if (el) el.textContent = msg;
    try { console.log('[TransportBuild]', msg); } catch (_) { /* ignore */ }
    showToast(msg);
  }

  let _toastTimer = null;
  function showToast(msg) {
    const toast = $('tb-toast');
    if (!toast || !msg) return;
    toast.textContent = msg;
    toast.classList.remove('hidden');
    toast.style.display = 'block';
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => {
      toast.classList.add('hidden');
      toast.style.display = 'none';
    }, 4500);
  }

  function isTransportDialogOpen() {
    const dlg = $('tb-dialog');
    if (!dlg) return false;
    if (dlg.classList.contains('hidden')) return false;
    return dlg.style.display !== 'none';
  }

  /** Electron often disables window.prompt/confirm — use fixed overlay instead. */
  function askDialog({ title, message, defaultValue, showInput, detail, okLabel, cancelLabel, hideCancel }) {
    return new Promise((resolve) => {
      const dlg = $('tb-dialog');
      const titleEl = $('tb-dialog-title');
      const msgEl = $('tb-dialog-msg');
      const input = $('tb-dialog-input');
      const detailEl = $('tb-dialog-detail');
      const ok = $('tb-dialog-ok');
      const cancel = $('tb-dialog-cancel');
      if (!dlg || !ok || !cancel) {
        // Last resort: still resolve so New Area / Build POC never go silent
        resolve(showInput ? (defaultValue || '') : true);
        return;
      }
      if (titleEl) titleEl.textContent = title || 'Transport Build';
      if (msgEl) msgEl.textContent = message || '';
      if (input) {
        const show = !!showInput;
        input.classList.toggle('hidden', !show);
        input.style.display = show ? 'block' : 'none';
        input.readOnly = false;
        input.disabled = false;
        input.value = defaultValue || '';
      }
      if (detailEl) {
        const has = !!(detail && String(detail).trim());
        detailEl.classList.toggle('hidden', !has);
        detailEl.style.display = has ? 'block' : 'none';
        detailEl.textContent = has ? String(detail) : '';
      }
      ok.textContent = okLabel || 'OK';
      cancel.textContent = cancelLabel || 'Cancel';
      cancel.classList.toggle('hidden', !!hideCancel);
      cancel.style.display = hideCancel ? 'none' : '';

      dlg.dataset.open = '1';
      dlg.classList.remove('hidden');
      dlg.style.display = 'flex';
      // Frameless Electron: keep dialog out of titlebar drag region
      dlg.style.webkitAppRegion = 'no-drag';

      const finish = (val) => {
        dlg.dataset.open = '0';
        dlg.classList.add('hidden');
        dlg.style.display = 'none';
        ok.onclick = null;
        cancel.onclick = null;
        if (input) {
          input.onkeydown = null;
          input.onkeyup = null;
        }
        resolve(val);
      };
      cancel.onclick = () => finish(showInput ? null : false);
      ok.onclick = () => finish(showInput ? (input?.value ?? '') : true);
      if (showInput && input) {
        const focusInput = () => {
          try {
            input.focus({ preventScroll: true });
            input.select();
          } catch (_) {
            try { input.focus(); input.select(); } catch (__) { /* ignore */ }
          }
        };
        // Canvas tabindex steals focus — retry a few times
        focusInput();
        setTimeout(focusInput, 0);
        setTimeout(focusInput, 50);
        setTimeout(focusInput, 150);
        input.onkeydown = (e) => {
          e.stopPropagation();
          if (e.key === 'Enter') { e.preventDefault(); finish(input.value); }
          if (e.key === 'Escape') { e.preventDefault(); finish(null); }
        };
        input.onkeyup = (e) => e.stopPropagation();
      } else {
        setTimeout(() => { try { ok.focus(); } catch (_) { /* ignore */ } }, 30);
      }
    });
  }

  async function askText(title, message, defaultValue) {
    return askDialog({ title, message, defaultValue, showInput: true });
  }

  async function askYesNo(title, message) {
    return askDialog({ title, message, showInput: false });
  }

  async function showInfo(title, message, detail) {
    return askDialog({
      title,
      message,
      showInput: false,
      detail,
      hideCancel: true,
      okLabel: 'Got it',
    });
  }

  function activeArea() {
    return tb.areas.find((a) => a.id === tb.activeAreaId) || null;
  }

  function ensureDefaultArea() {
    // Gate 2 — always keep Default Area ownership bucket (unless project cleared)
    if (tb.suppressDefaultArea) return null;
    let d = (tb.areas || []).find((a) => isDefaultArea(a));
    if (!d) {
      d = {
        id: uid('area'),
        name: DEFAULT_AREA_NAME,
        nodes: [],
        wires: [],
        isDefault: true,
        defaultArea: true,
        provenance: 'SITE_FORGE_DEFAULT',
        defaultSafetyZone: '',
      };
      tb.areas.unshift(d);
    } else {
      d.isDefault = true;
      d.defaultArea = true;
      // Normalize legacy Unassigned / Transport_1 / *_Imported → Default Area label
      if (isDefaultAreaName(d.name) && String(d.name).trim() !== DEFAULT_AREA_NAME) {
        if (/^Transport_\d+$/i.test(d.name) || isDefaultAreaName(d.name)) {
          d.name = DEFAULT_AREA_NAME;
        }
      }
    }
    return d;
  }

  function ensureArea() {
    // Clear Current Project may leave canvas empty until Auto Build / Add area
    if (tb.suppressDefaultArea) return;
    ensureDefaultArea();
    if (!tb.areas.length) {
      const a = ensureDefaultArea();
      if (a) tb.activeAreaId = a.id;
    }
    if (!activeArea()) tb.activeAreaId = tb.areas[0].id;
  }

  /** Move all members of an engineer Area into Default Area (Gate 2 conservation). */
  function returnAreaMembersToDefault(area) {
    if (!area || isDefaultArea(area)) return 0;
    const dest = ensureDefaultArea();
    if (!dest || dest.id === area.id) return 0;
    const moving = [...(area.nodes || [])];
    moving.forEach((n) => {
      // Preserve tag topology; drop area-local wire visuals
      if (n && !n.provenance) n.provenance = {};
      // Ownership only — do not rewrite RUN geometry provenance
      if (n) n.provenance.area = 'SITE_FORGE_DEFAULT';
    });
    dest.nodes = dest.nodes || [];
    dest.nodes.push(...moving);
    area.nodes = [];
    area.wires = [];
    return moving.length;
  }

  function canonicalTransportHash() {
    // Stable hash of engineer-authoritative Transport topology (Areas + bound tags + wires).
    // Excludes presentation/geometry so Apply cannot be blamed for viz-only drift.
    try {
      const areas = (tb.areas || []).map((a) => ({
        id: a.id,
        name: a.name || '',
        nodes: (a.nodes || [])
          .filter((n) => n && !n.displayContext && n.plcOwned !== false)
          .map((n) => ({
            id: n.id,
            kind: n.kind,
            tag: (n.conveyorTag || '').trim(),
            downstream: (n.downstream || '').trim(),
            terminal: !!n.terminal,
            safetyZone: n.safetyZone || '',
          }))
          .sort((x, y) => String(x.id).localeCompare(String(y.id))),
        wires: (a.wires || [])
          .map((w) => ({ from: w.from, to: w.to, toPort: w.toPort || 'in' }))
          .sort((x, y) => `${x.from}|${x.to}|${x.toPort}`.localeCompare(`${y.from}|${y.to}|${y.toPort}`)),
      })).sort((x, y) => String(x.id).localeCompare(String(y.id)));
      const raw = JSON.stringify(areas);
      let h = 0;
      for (let i = 0; i < raw.length; i += 1) {
        h = ((h << 5) - h) + raw.charCodeAt(i);
        h |= 0;
      }
      return `h${(h >>> 0).toString(16)}:${areas.length}:${raw.length}`;
    } catch (_) {
      return 'h0';
    }
  }

  function currentProjectIdentity() {
    try {
      const raw = localStorage.getItem('siteforge.projectIdentity');
      return raw ? JSON.parse(raw) : (window.state?.projectIdentity || null);
    } catch (_) {
      return null;
    }
  }

  function identityKey(id) {
    if (!id || typeof id !== 'object') return '';
    return [id.machine || '', id.run_fingerprint || '', id.archive || ''].join('|');
  }

  function save() {
    try {
      localStorage.setItem(
        STORE_KEY,
        JSON.stringify({
          areas: tb.areas,
          activeAreaId: tb.activeAreaId,
          safetyZones: tb.safetyZones || [],
          activeSafetyZoneId: tb.activeSafetyZoneId || null,
          autoConnectNew: !!tb.autoConnectNew,
          // Additive v2 fields — controlPanel lives on nodes; filters/layers are UI prefs
          cpFilters: tb.cpFilters || {},
          layers: tb.layers || null,
          decoderInventoryTags: tb.decoderInventoryTags || null,
          cp5a: tb.cp5a || null,
          // Identity guard — refuse restore into a different site/controller
          projectIdentity: currentProjectIdentity(),
        })
      );
    } catch (_) { /* ignore */ }
    // After a successful Apply, any canvas edit requires re-Apply —
    // but never mark dirty while Apply itself is in progress (persistence guard).
    if (
      tb.workflow?.apply
      && !tb.applyingAutogen
      && typeof window.markAutogenReadinessDirty === 'function'
    ) {
      try { window.markAutogenReadinessDirty('transport'); } catch (_) { /* ignore */ }
    }
  }

  function _nodeInControllerScope(n) {
    if (!n) return false;
    if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') return true;
    if (n.displayContext) return false;
    if (n.plcOwned === false) return false;
    if (n.scopeClass === 'OUT_OF_SCOPE' || n.scopeClass === 'UNRESOLVED') return false;
    return true;
  }

  function _filterAreasToControllerScope(areas) {
    return (areas || []).map((area) => {
      const nodes = (area.nodes || []).filter(_nodeInControllerScope);
      const keep = new Set(nodes.map((n) => n.id));
      const wires = (area.wires || []).filter((w) => keep.has(w.from) && keep.has(w.to));
      const next = { ...area, nodes, wires };
      if (isDefaultArea(next)) {
        next.isDefault = true;
        next.defaultArea = true;
      }
      return next;
    // PD-0040 — keep empty engineer Areas (nodes may be empty by design)
    }).filter((a) => (a.nodes || []).length > 0 || isDefaultArea(a) || isEngineerAreaShell(a));
  }

  /** Empty engineer Area shells must survive reload / project reopen. */
  function isEngineerAreaShell(a) {
    if (!a || isDefaultArea(a)) return false;
    const prov = String(a.provenance || '').toUpperCase();
    if (prov === 'ENGINEER' || prov === 'ENGINEER_CREATED' || prov === 'ENGINEER_ASSIGNED') return true;
    // Named non-default Area with zero nodes is still a first-class shell
    return !!String(a.name || '').trim() && a.defaultArea !== true && a.isDefault !== true;
  }

  function load() {
    try {
      // Drop legacy plant-wide saves (v1 and any stale duplicates).
      try {
        localStorage.removeItem('siteforge.transportBuild.v1');
      } catch (_) { /* ignore */ }
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      // Project identity guard: Site A cache must not restore into Site B
      const savedId = identityKey(data.projectIdentity);
      const liveId = identityKey(currentProjectIdentity());
      if (savedId && liveId && savedId !== liveId) {
        try { localStorage.removeItem(STORE_KEY); } catch (_) { /* ignore */ }
        tb.areas = [];
        tb.safetyZones = [];
        tb.activeAreaId = null;
        tb.activeSafetyZoneId = null;
        status('Discarded prior-site Transport cache (project identity mismatch)');
        return;
      }
      if (Array.isArray(data.areas)) {
        const filtered = _filterAreasToControllerScope(data.areas);
        const before = (data.areas || []).reduce((s, a) => s + ((a.nodes || []).length), 0);
        const after = filtered.reduce((s, a) => s + ((a.nodes || []).length), 0);
        // If a saved canvas is still site-wide after filtering, wipe it.
        if (before > 120 && after > 0 && after < before * 0.5) {
          tb.areas = filtered;
        } else if (before > 200 && after > 150) {
          // Unscoped residual — do not restore.
          tb.areas = [];
          try { localStorage.removeItem(STORE_KEY); } catch (_) { /* ignore */ }
        } else {
          tb.areas = filtered;
        }
      }
      tb.activeAreaId = data.activeAreaId || (tb.areas[0] && tb.areas[0].id) || null;
      if (tb.activeAreaId && !(tb.areas || []).some((a) => a.id === tb.activeAreaId)) {
        tb.activeAreaId = (tb.areas[0] && tb.areas[0].id) || null;
      }
      if (Array.isArray(data.safetyZones)) {
        // Preserve ENGINEER_CREATED provenance / source_id / areaRef / members
        // (stripped metadata previously made engineer zones look like RUN PROVEN).
        tb.safetyZones = data.safetyZones
          .filter((z) => z && (z.name || z.engineering_name || z.id || z.source_id))
          .map((z) => {
            const eng = String(z.engineering_name || z.name || '').trim();
            const sid = String(z.source_id || z.id || '').trim() || uid('szone');
            const provenance = String(z.provenance || z.origin || '').trim()
              || (z.createdBy === 'engineer' ? 'ENGINEER_CREATED' : '');
            return {
              ...z,
              id: sid,
              source_id: sid,
              name: eng || sid,
              engineering_name: eng || sid,
              createdBy: z.createdBy || (provenance === 'ENGINEER_CREATED' ? 'engineer' : z.createdBy),
              provenance: provenance || z.provenance || '',
              origin: z.origin || provenance || '',
              areaRef: z.areaRef || z.area || '',
              members: Array.isArray(z.members) ? z.members : [],
              status: z.status || 'REVIEW_REQUIRED',
              operational: z.operational !== false,
            };
          })
          .filter((z) => z.name);
      } else {
        // Seed from conveyor safetyZone values already on the canvas
        seedSafetyZonesFromNodes({ preserveEngineer: false });
      }
      tb.activeSafetyZoneId = data.activeSafetyZoneId
        || (tb.safetyZones[0] && tb.safetyZones[0].id)
        || null;
      if ((tb.areas || []).length) tb.suppressDefaultArea = false;
      if (typeof data.autoConnectNew === 'boolean') tb.autoConnectNew = data.autoConnectNew;
      if (data.cpFilters && typeof data.cpFilters === 'object') {
        tb.cpFilters = {};
        Object.keys(data.cpFilters).forEach((k) => {
          if (k) tb.cpFilters[k] = !!data.cpFilters[k];
        });
      }
      if (data.decoderInventoryTags && typeof data.decoderInventoryTags === 'object') {
        tb.decoderInventoryTags = data.decoderInventoryTags;
      }
      if (data.cp5a && typeof data.cp5a === 'object') {
        tb.cp5a = data.cp5a;
      }
      if (data.layers && typeof data.layers === 'object') {
        tb.layers = { ...(tb.layers || {}), ...data.layers };
      }
      // Ensure controlPanel exists on restored nodes (presentation metadata only)
      (tb.areas || []).forEach((area) => {
        if (area.defaultSafetyZone == null) area.defaultSafetyZone = '';
        if (isDefaultArea(area)) {
          area.isDefault = true;
          area.defaultArea = true;
          if (isDefaultAreaName(area.name) && String(area.name).trim() !== DEFAULT_AREA_NAME) {
            area.name = DEFAULT_AREA_NAME;
          }
        }
        (area.nodes || []).forEach((n) => {
          if (n.controlPanel == null) n.controlPanel = '';
          if (n.safetyZone == null) n.safetyZone = '';
        });
      });
      // Gate 2 — Default Area must exist after restore when canvas has equipment
      if ((tb.areas || []).length && !tb.suppressDefaultArea) {
        ensureDefaultArea();
      }
    } catch (_) { /* ignore */ }
  }


  /* ===== Transport UX Pass 1 — topology-first helpers ===== */
  function nodeLabel(n) {
    return (n && (n.conveyorTag || n.label || n.id)) || '';
  }

  function findNodeByTag(area, tag) {
    const u = String(tag || '').trim().toUpperCase();
    if (!u || !area) return null;
    return (area.nodes || []).find(
      (n) => isConv(n.kind) && String(n.conveyorTag || '').trim().toUpperCase() === u
    ) || null;
  }

  function outboundWire(area, fromId) {
    return (area?.wires || []).find((w) => w.from === fromId) || null;
  }

  function inboundWires(area, toId) {
    return (area?.wires || []).filter((w) => w.to === toId);
  }

  function syncDownstreamFromWires(area) {
    if (!area) return;
    const byId = Object.fromEntries((area.nodes || []).map((n) => [n.id, n]));
    (area.nodes || []).forEach((n) => {
      if (!isConv(n.kind)) return;
      const w = outboundWire(area, n.id);
      if (!w) {
        if (!n.downstream) n.downstream = '';
        return;
      }
      const dst = byId[w.to];
      n.downstream = dst ? (dst.conveyorTag || '').trim() : (n.downstream || '');
    });
  }

  function syncWiresFromDownstream(area) {
    if (!area) return;
    (area.nodes || []).forEach((n) => {
      if (!isConv(n.kind)) return;
      const ds = String(n.downstream || '').trim();
      if (!ds) return;
      const dst = findNodeByTag(area, ds);
      if (!dst || dst.id === n.id) return;
      if ((area.wires || []).some((w) => w.from === n.id && w.to === dst.id)) return;
      // Migrate: create wire from canonical downstream when missing
      const toPort = pickEntrancePort(area, dst);
      area.wires = area.wires || [];
      area.wires.push({ id: uid('wire'), from: n.id, to: dst.id, toPort });
    });
  }

  function pickEntrancePort(area, dst) {
    if (!dst) return 'in';
    const meta = KIND_META[dst.kind] || {};
    if (!meta.isMerge && !dst.asMerge) return 'in';
    const lanes = Math.max(2, Number(dst.inPorts) || 2);
    const used = new Set(
      inboundWires(area, dst.id).map((w) => w.toPort || 'in0')
    );
    for (let i = 0; i < lanes; i++) {
      const p = `in${i}`;
      if (!used.has(p) && !(i === 0 && used.has('in'))) return p;
    }
    return `in${Math.min(lanes - 1, inboundWires(area, dst.id).length)}`;
  }

  function migrateGraphTopology() {
    (tb.areas || []).forEach((area) => {
      syncWiresFromDownstream(area);
      syncDownstreamFromWires(area);
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        if (typeof n.terminal !== 'boolean') n.terminal = false;
        if (typeof n.asMerge !== 'boolean') n.asMerge = !!n.asMerge;
        // Physical layout fields (Auto Build From RUN) — defaults for legacy graphs
        if (typeof n.physical !== 'boolean') n.physical = false;
        if (n.length == null) n.length = null;
        if (n.width == null) n.width = null;
        if (!n.equipmentType) n.equipmentType = '';
        if (!n.entryAnchor) n.entryAnchor = null;
        if (!n.exitAnchor) n.exitAnchor = null;
        if (!n.provenance || typeof n.provenance !== 'object') {
          n.provenance = { geometry: n.physical ? 'IMPORTED' : 'MANUAL', area: 'MANUAL', safetyZone: 'MANUAL' };
        }
        if (!Array.isArray(n.motorsMeta)) n.motorsMeta = [];
        if (!Array.isArray(n.ambiguousInbound)) n.ambiguousInbound = [];
      });
      (area.wires || []).forEach((w) => {
        if (typeof w.physical !== 'boolean') w.physical = false;
        if (!w.confidence) w.confidence = w.physical ? 'HIGH_CONFIDENCE' : '';
        if (!w.fromAnchor) w.fromAnchor = 'exit';
        if (!w.toAnchor) w.toAnchor = 'entry';
      });
    });
  }

  function getUpstreamNodes(area, nodeId) {
    return inboundWires(area, nodeId)
      .map((w) => (area.nodes || []).find((n) => n.id === w.from))
      .filter(Boolean);
  }

  function getUpstreamTags(area, nodeId) {
    return getUpstreamNodes(area, nodeId)
      .map((n) => (n.conveyorTag || n.label || '').trim())
      .filter(Boolean);
  }

  function clearDownstream(fromId, { silent } = {}) {
    const area = activeArea();
    if (!area) return false;
    const from = area.nodes.find((n) => n.id === fromId);
    if (!from) return false;
    area.wires = (area.wires || []).filter((w) => w.from !== fromId);
    from.downstream = '';
    if (!silent) {
      save();
      render();
      status(`Cleared downstream for ${nodeLabel(from)}`);
    }
    return true;
  }

  async function maybeConfirmMerge(dst) {
    // Pass 2 may replace via window.__tbHooks.maybeConfirmMerge (3:1 unsupported marking)
    if (typeof window.__tbHooks?.maybeConfirmMerge === 'function') {
      return window.__tbHooks.maybeConfirmMerge(dst);
    }
    const area = activeArea();
    if (!area || !dst || !isConv(dst.kind)) return;
    if (KIND_META[dst.kind]?.isMerge || dst.asMerge) return;
    const inbound = inboundWires(area, dst.id);
    if (inbound.length < 2) return;
    const tag = nodeLabel(dst) || 'this conveyor';
    const ok = await askYesNo(
      'Configure 2:1 Merge?',
      `${tag} has two inbound lanes. Configure as 2:1 Merge?\n\n`
        + `This keeps hold_mode=runhold (Greensboro PLC2 pattern) unless you change it later.`
    );
    if (!ok) return;
    dst.asMerge = true;
    dst.inPorts = Math.max(2, Number(dst.inPorts) || inbound.length);
    // Normalize ports onto in0/in1…
    inbound.forEach((w, i) => {
      w.toPort = `in${i}`;
    });
    save();
    render();
    status(`${tag} marked as 2:1 merge discharge (asMerge)`);
  }

  function setDownstream(fromId, toIdOrTag, { silent, skipMergePrompt } = {}) {
    const area = activeArea();
    if (!area) return false;
    const from = area.nodes.find((n) => n.id === fromId);
    if (!from || !isConv(from.kind)) return false;
    let to = null;
    if (toIdOrTag && typeof toIdOrTag === 'object') to = toIdOrTag;
    else if (toIdOrTag) {
      to = area.nodes.find((n) => n.id === toIdOrTag)
        || findNodeByTag(area, toIdOrTag);
    }
    if (!toIdOrTag) {
      return clearDownstream(fromId, { silent });
    }
    if (!to || !isConv(to.kind)) {
      status('Downstream target not found in this area.');
      return false;
    }
    if (to.id === from.id) {
      status('Self-connection rejected.');
      return false;
    }
    // Replace any existing outbound from source (single downstream model)
    area.wires = (area.wires || []).filter((w) => w.from !== from.id);
    const dup = (area.wires || []).some((w) => w.from === from.id && w.to === to.id);
    if (dup) {
      status('Already connected.');
      return false;
    }
    const toPort = pickEntrancePort(area, to);
    if (toPort !== 'in' && String(toPort).startsWith('in')) {
      area.wires = area.wires.filter((w) => !(w.to === to.id && (w.toPort || 'in') === toPort));
    }
    area.wires.push({ id: uid('wire'), from: from.id, to: to.id, toPort });
    from.downstream = (to.conveyorTag || '').trim();
    from.terminal = false;
    markValidationDirty();
    if (!silent) {
      save();
      render();
      status(`Connected ${nodeLabel(from)} → ${nodeLabel(to)}`);
    }
    if (!skipMergePrompt) {
      // Fire-and-forget confirm; caller may await separately
      maybeConfirmMerge(to);
    }
    return true;
  }

  function exitConnectMode() {
    tb.connectMode = false;
    tb.connectSourceId = null;
    $('tb-connect-mode')?.classList.remove('tb-mode-on');
    $('tab-transport')?.classList.remove('tb-connect-active');
  }

  function enterConnectMode() {
    tb.connectMode = true;
    tb.connectSourceId = null;
    tb.linkFrom = null;
    $('tb-connect-mode')?.classList.add('tb-mode-on');
    $('tab-transport')?.classList.add('tb-connect-active');
    status('Connect Mode: click source conveyor, then destination (Esc / right-click to exit)');
    render();
  }

  function toggleConnectMode() {
    if (tb.connectMode) {
      exitConnectMode();
      status('Connect Mode off');
      render();
    } else {
      enterConnectMode();
    }
  }

  async function handleConnectModeClick(node) {
    if (!tb.connectMode || !node || !isConv(node.kind)) return false;
    if (!tb.connectSourceId) {
      tb.connectSourceId = node.id;
      tb.selectedId = node.id;
      tb.selectedDeviceId = null;
      status(`Connect source: ${nodeLabel(node)} — click destination`);
      render();
      return true;
    }
    if (tb.connectSourceId === node.id) {
      status('Self-connection rejected — pick a different destination');
      return true;
    }
    const src = tb.connectSourceId;
    tb.connectSourceId = null;
    const ok = setDownstream(src, node.id, { silent: true, skipMergePrompt: true });
    if (ok) {
      save();
      render();
      status(`Connected — still in Connect Mode (Esc to exit)`);
      await maybeConfirmMerge(node);
    }
    // keep mode active
    render();
    return true;
  }

  function peRolesOnNode(n) {
    const roles = new Set();
    (n.devices || []).forEach((d) => {
      if (d.kind !== 'photoeye') return;
      ensurePeRoles(d).forEach((r) => roles.add(r));
    });
    return [...roles];
  }

  function peTagsByRole(n, role) {
    const out = [];
    (n.devices || []).forEach((d) => {
      if (d.kind !== 'photoeye') return;
      const roles = ensurePeRoles(d);
      if (roles.includes(role)) {
        const t = (d.tag || d.name || '').trim();
        if (t) out.push(t);
      }
    });
    return out;
  }

  function assignedConveyorTags() {
    const used = new Set();
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        const t = (n.conveyorTag || '').trim().toUpperCase();
        if (t) used.add(t);
      });
    });
    return used;
  }

  function assignedDeviceTags() {
    const used = new Set();
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        (n.devices || []).forEach((d) => {
          const t = (d.tag || d.name || '').trim().toUpperCase();
          if (t) used.add(t);
        });
        ['pe_a', 'pe_b', 'pe_c', 'jam_pe'].forEach((k) => {
          const t = String(n[k] || '').trim().toUpperCase();
          if (t) used.add(t);
        });
      });
    });
    return used;
  }

  function runInventory() {
    const convs = conveyorOptions();
    const cat = buildableTagCatalog();
    const usedConv = assignedConveyorTags();
    const usedDev = assignedDeviceTags();
    const pe = [...(cat.photoeye || [])].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const motors = [...(cat.motor || [])].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const enc = [...(cat.encoder || [])].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return {
      conveyors: {
        detected: convs.length,
        assigned: convs.filter((c) => usedConv.has(c.toUpperCase())).length,
        unassigned: convs.filter((c) => !usedConv.has(c.toUpperCase())).length,
        list: convs,
      },
      photoeyes: {
        detected: pe.length,
        assigned: pe.filter((c) => usedDev.has(c.toUpperCase())).length,
        unassigned: pe.filter((c) => !usedDev.has(c.toUpperCase())).length,
        list: pe,
      },
      motors: { list: motors, used: usedDev },
      encoders: { list: enc, used: usedDev },
      usedConv,
      usedDev,
    };
  }

  function renderInventoryPanel() {
    // Pass 2 replaces inventory with an active build palette when hooked
    if (typeof window.__tbHooks?.renderInventoryPanel === 'function') {
      window.__tbHooks.renderInventoryPanel();
      return;
    }
    const sum = $('tb-inv-summary');
    const list = $('tb-inv-list');
    if (!sum || !list) return;
    const inv = runInventory();
    sum.innerHTML = `
      <div>Conveyors <span class="text-cyan-400">${inv.conveyors.detected}</span>
        · assigned <span class="text-emerald-400">${inv.conveyors.assigned}</span>
        · free <span class="text-amber-400">${inv.conveyors.unassigned}</span></div>
      <div>Photoeyes <span class="text-cyan-400">${inv.photoeyes.detected}</span>
        · assigned <span class="text-emerald-400">${inv.photoeyes.assigned}</span>
        · free <span class="text-amber-400">${inv.photoeyes.unassigned}</span></div>`;
    const q = String($('tb-inv-filter')?.value || '').trim().toUpperCase();
    const rows = [];
    const pushGroup = (label, items, usedSet) => {
      items.forEach((t) => {
        if (q && !t.toUpperCase().includes(q)) return;
        const used = usedSet.has(t.toUpperCase());
        rows.push(
          `<div class="tb-inv-item ${used ? 'used' : 'free'}" title="${escapeHtml(label)}">${escapeHtml(t)}${used ? ' · used' : ''}</div>`
        );
      });
    };
    pushGroup('P', inv.conveyors.list, inv.usedConv);
    pushGroup('PE', inv.photoeyes.list, inv.usedDev);
    pushGroup('M/VFD', inv.motors.list, inv.usedDev);
    pushGroup('ENC', inv.encoders.list, inv.usedDev);
    list.innerHTML = rows.slice(0, 120).join('')
      || `<div class="text-slate-600 px-1">No RUN tags match.</div>`;
  }

  function collectValidation() {
    const errors = [];
    const warnings = [];
    const byTag = new Map();
    const peUses = new Map();
    const buildablePe = new Set([...(buildableTagCatalog().photoeye || [])].map((x) => x.toUpperCase()));

    (tb.areas || []).forEach((area) => {
      const aname = area.name || 'Area';
      if (!(area.name || '').trim()) {
        warnings.push(`${aname}: area has no name`);
      }
      const byId = Object.fromEntries((area.nodes || []).map((n) => [n.id, n]));
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        const tag = (n.conveyorTag || '').trim();
        if (!tag) {
          errors.push(`${aname}: unbound conveyor (${n.label || n.id})`);
        } else {
          const key = tag.toUpperCase();
          if (byTag.has(key)) {
            errors.push(`Duplicate P### assignment: ${tag}`);
          } else {
            byTag.set(key, n);
          }
        }
        const ds = String(n.downstream || '').trim();
        const out = outboundWire(area, n.id);
        if (out && !byId[out.to]) {
          errors.push(`${aname}: dangling connection from ${tag || n.id}`);
        }
        if (out && out.to === n.id) {
          errors.push(`${aname}: self connection on ${tag || n.id}`);
        }
        if (ds && !findNodeByTag(area, ds) && !byTag.has(ds.toUpperCase())) {
          // may exist in another area — soft warn
          const elsewhere = (tb.areas || []).some((a2) => findNodeByTag(a2, ds));
          if (!elsewhere) warnings.push(`${tag || n.id}: downstream ${ds} missing`);
        }
        if (!ds && !n.terminal && !KIND_META[n.kind]?.isMerge) {
          warnings.push(`${tag || n.label || n.id}: no downstream (mark terminal if end of run)`);
        }
        if (!aname || aname === 'Transport_1') {
          /* area always exists */
        }
        if (!(area.name || '').trim()) {
          errors.push(`${tag || n.id}: conveyor with no area`);
        }
        if (n.asMerge || KIND_META[n.kind]?.isMerge) {
          const inbound = inboundWires(area, n.id);
          if (inbound.length < 2) {
            warnings.push(`${tag || n.label}: merge with <2 inbound lanes`);
          }
          if (!tag) warnings.push(`${n.label || n.id}: merge with no discharge tag`);
        }
        (n.devices || []).forEach((d) => {
          if (d.kind !== 'photoeye') return;
          const pt = (d.tag || '').trim();
          if (!pt) return;
          const pu = pt.toUpperCase();
          peUses.set(pu, (peUses.get(pu) || 0) + 1);
          if (buildablePe.size && !buildablePe.has(pu)) {
            warnings.push(`PE ${pt} not found in RUN/workbook`);
          }
        });
      });
      (area.wires || []).forEach((w) => {
        if (!byId[w.from] || !byId[w.to]) {
          errors.push(`${aname}: dangling wire ${w.id || ''}`);
        }
        if (w.from === w.to) errors.push(`${aname}: self connection wire`);
      });
    });
    peUses.forEach((count, pe) => {
      if (count > 1) warnings.push(`Suspicious duplicate PE use: ${pe} (${count}×)`);
    });

    return { errors, warnings, ready: !errors.length };
  }

  function markValidationDirty() {
    tb.validationDirty = true;
    tb._validationCache = null;
  }

  function getValidationCached() {
    if (!tb.validationDirty && tb._validationCache) return tb._validationCache;
    tb._validationCache = collectValidation();
    tb.validationDirty = false;
    return tb._validationCache;
  }

  function renderValidationPanel() {
    const el = $('tb-validation');
    if (!el) return;
    // Event-driven: only compute when panel visible / dirty / explicit verify
    const open = !el.classList.contains('hidden') || el.dataset.open === '1';
    if (!open && !tb.validationDirty && tb._validationCache) {
      /* keep last paint */
    }
    const { errors, warnings, ready } = getValidationCached();
    const parts = [];
    if (ready && !warnings.length) {
      parts.push(`<div class="tb-val-ok">Ready · ${errors.length} errors · ${warnings.length} warnings</div>`);
    } else {
      parts.push(
        `<div class="${errors.length ? 'tb-val-err' : 'tb-val-ok'}">Errors: ${errors.length}</div>`
      );
      parts.push(`<div class="tb-val-warn">Warnings: ${warnings.length}</div>`);
      if (ready) parts.push(`<div class="tb-val-ok">Ready for Apply (warnings OK)</div>`);
      else parts.push(`<div class="tb-val-err">Not clean — editing still allowed</div>`);
    }
    errors.slice(0, 12).forEach((e) => {
      parts.push(`<div class="tb-val-err">• ${escapeHtml(e)}</div>`);
    });
    warnings.slice(0, 12).forEach((w) => {
      parts.push(`<div class="tb-val-warn">• ${escapeHtml(w)}</div>`);
    });
    el.innerHTML = parts.join('');
    renderTopologyAccounting();
  }

  /** Account for EVERY conveyor — never hide unresolved islands from the engineer. */
  function renderTopologyAccounting() {
    const el = $('tb-topo-accounting');
    if (!el) return;
    const area = activeArea();
    const nodes = (area?.nodes || []).filter((n) => isConv(n.kind));
    const wires = area?.wires || [];
    const topo = computeConnectedComponents(nodes, wires);
    const ext = nodes.filter(
      (n) => n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE' || n.displayContext
    );
    const local = nodes.filter((n) => !ext.includes(n));
    const wired = new Set();
    wires.forEach((w) => { wired.add(w.from); wired.add(w.to); });
    nodes.forEach((n) => { if (String(n.downstream || '').trim()) wired.add(n.id); });
    const connected = local.filter((n) => wired.has(n.id));
    const unresolved = local.filter((n) => !wired.has(n.id));
    tb.topologyAccounting = {
      total: nodes.length,
      connected: connected.length,
      external: ext.length,
      unresolved: unresolved.length,
      unresolvedTags: unresolved.map((n) => n.conveyorTag || n.id),
      externalTags: ext.map((n) => n.conveyorTag || n.id),
      components: topo?.count || 0,
      primary: topo?.primarySize || 0,
      islands: topo?.islandCount || 0,
    };
    const a = tb.topologyAccounting;
    el.innerHTML = [
      `TOTAL ${a.total}`,
      `CONNECTED ${a.connected}`,
      `EXTERNAL ${a.external}`,
      `UNRESOLVED ${a.unresolved}`,
      `COMPONENTS ${a.components} · PRIMARY ${a.primary} · ISLANDS ${a.islands}`,
    ].map((s) => `<div>${escapeHtml(s)}</div>`).join('');
  }

  /** Highlight conveyors belonging to a Safety Zone (canonical Transport viz). */
  function highlightSafetyZone(zoneName) {
    const zname = String(zoneName || '').trim();
    const area = activeArea();
    if (!area) return;
    (area.nodes || []).forEach((n) => {
      const el = document.querySelector(`[data-id="${CSS.escape(n.id)}"]`);
      if (!el) return;
      const match = zname && String(n.safetyZone || '').trim() === zname;
      el.classList.toggle('tb-safety-zone-hl', !!match);
      if (match) el.classList.add('selected');
    });
    // Also mark schematic hit paths
    document.querySelectorAll('.tb-schematic-hit, .tb-schematic-body').forEach((el) => {
      const id = el.getAttribute('data-id');
      const n = (area.nodes || []).find((x) => x.id === id);
      const match = n && zname && String(n.safetyZone || '').trim() === zname;
      el.classList.toggle('tb-safety-zone-hl', !!match);
    });
    status(zname ? `Safety Zone highlighted: ${zname}` : 'Safety Zone highlight cleared');
  }

  function showUnresolvedTopology() {
    renderTopologyAccounting();
    const tags = tb.topologyAccounting?.unresolvedTags || [];
    const ext = tb.topologyAccounting?.externalTags || [];
    const all = [...tags, ...ext];
    if (!all.length) {
      status('No unresolved/external topology — all local conveyors connected');
      return;
    }
    const area = activeArea();
    const hits = (area?.nodes || []).filter((n) => {
      const t = String(n.conveyorTag || '').trim();
      return all.includes(t) || all.includes(n.id);
    });
    tb.selectedIds = hits.map((n) => n.id);
    tb.selectedId = hits[0]?.id || null;
    fitViewToNodes(hits.length ? hits : area?.nodes || [], {
      mode: 'unresolved',
      paddingFrac: 0.12,
      primaryComponentOnly: false,
      excludeOutliers: false,
    });
    render();
    status(
      `Unresolved topology · ${tags.length} local + ${ext.length} external — `
      + all.slice(0, 12).join(', ')
      + (all.length > 12 ? '…' : '')
    );
  }

  function safetyForAreaName(name) {
    return nextSafetyZoneName(name);
  }

  /**
   * Default Safety Zone suggestion from Area/layout name.
   * ORNCCP2_Area → ORNCCP2_ESZone1 (next free N if taken). Suggestion only.
   */
  function nextSafetyZoneName(areaName) {
    const base = String(areaName || 'Transport').replace(/_Area$/i, '').trim() || 'Transport';
    const existing = new Set(listSafetyZoneNames().map((z) => z.toLowerCase()));
    for (let n = 1; n < 100; n++) {
      const candidate = `${base}_ESZone${n}`;
      if (!existing.has(candidate.toLowerCase())) return candidate;
    }
    return `${base}_ESZone1`;
  }

  /** All known Safety Zone engineering/Logix names (first-class list + conveyor values). */
  function listSafetyZoneNames() {
    const names = new Set();
    (tb.safetyZones || []).forEach((z) => {
      const n = String(z?.engineering_name || z?.name || '').trim();
      if (n) names.add(n);
    });
    (tb.areas || []).forEach((a) => {
      const d = String(a.defaultSafetyZone || '').trim();
      if (d) names.add(d);
      (a.nodes || []).forEach((n) => {
        const z = String(n.safetyZone || '').trim();
        if (z) names.add(z);
      });
    });
    const ctx = String(tb.buildContext?.safetyZone || '').trim();
    if (ctx) names.add(ctx);
    return [...names].sort((a, b) => a.localeCompare(b));
  }

  /**
   * Ensure a Safety Zone exists by engineering/Logix name; returns the zone record.
   * Gate E — engineer-created zones get immutable source_id (szone_*), separate from
   * reusable engineering_name. Empty shells are first-class (REVIEW_REQUIRED).
   * opts: { areaRef, silent, forceHandoff }
   */
  function ensureSafetyZone(name, opts) {
    const nm = String(name || '').trim();
    if (!nm) return null;
    const o = opts && typeof opts === 'object' ? opts : {};
    const areaRef = String(o.areaRef || o.area || '').trim();
    tb.safetyZones = tb.safetyZones || [];
    const engKey = nm.toLowerCase();
    // Match active zones by engineering_name / name — never invent a second active
    // zone with the same Logix name (deleted names may be reused via a new source_id).
    let z = tb.safetyZones.find((x) => {
      const eng = String(x.engineering_name || x.name || '').trim().toLowerCase();
      return eng === engKey;
    });
    const created = !z;
    if (!z) {
      const sid = uid('szone');
      z = {
        id: sid,
        source_id: sid,
        name: nm,
        engineering_name: nm,
        createdBy: 'engineer',
        provenance: 'ENGINEER_CREATED',
        origin: 'ENGINEER_CREATED',
        areaRef: areaRef || '',
        members: [],
        operational: true,
        status: 'REVIEW_REQUIRED',
        createdAt: new Date().toISOString(),
      };
      tb.safetyZones.push(z);
    } else {
      // PD-0040 — never silently move an existing same-name zone to another Area
      const existingArea = String(z.areaRef || z.area || '').trim();
      if (
        areaRef
        && existingArea
        && existingArea.toLowerCase() !== areaRef.toLowerCase()
      ) {
        const msg = `Safety Zone “${nm}” already exists under Area “${existingArea}” — not moved to “${areaRef}”`;
        if (!o.silent) {
          try { status(msg); } catch (_) { /* ignore */ }
          try {
            const notify = (typeof showInfo === 'function') ? showInfo
              : (typeof window.showInfo === 'function' ? window.showInfo : null);
            if (notify) notify('Safety Zone name in use', msg);
          } catch (_) { /* ignore */ }
        }
        return null;
      }
      // Enrich existing shell without wiping immutable source_id
      if (!z.source_id || z.source_id === z.name || z.source_id === z.engineering_name) {
        // Migrate legacy name-as-source_id shells to immutable szone_* ids
        if (!String(z.source_id || '').startsWith('szone_')) {
          z.source_id = z.id && String(z.id).startsWith('szone_') ? z.id : uid('szone');
          z.id = z.source_id;
        }
      }
      if (!z.engineering_name) z.engineering_name = z.name || nm;
      z.name = z.engineering_name || nm;
      // Only fill empty areaRef — never overwrite an existing Area association
      if (areaRef && !existingArea) z.areaRef = areaRef;
      if (!z.createdBy && !z.provenance) {
        z.createdBy = 'engineer';
        z.provenance = 'ENGINEER_CREATED';
        z.origin = 'ENGINEER_CREATED';
      }
      if (!Array.isArray(z.members)) z.members = z.members || [];
      z.operational = z.operational !== false;
      if (!z.status) z.status = 'REVIEW_REQUIRED';
    }
    // Gate E — handoff immediately so Safety Build shows the shell (even 0 members)
    if (created || o.forceHandoff) {
      try { save(); } catch (_) { /* ignore */ }
      try {
        if (typeof window.safetyBuildUpsertZone === 'function') {
          window.safetyBuildUpsertZone(z);
        }
      } catch (_) { /* ignore */ }
      try {
        window.dispatchEvent(new CustomEvent('siteforge:safety-zone-created', {
          detail: {
            source_id: z.source_id,
            id: z.source_id,
            engineering_name: z.engineering_name || z.name,
            name: z.engineering_name || z.name,
            areaRef: z.areaRef || '',
            createdBy: z.createdBy || 'engineer',
            provenance: z.provenance || 'ENGINEER_CREATED',
            origin: z.origin || 'ENGINEER_CREATED',
            members: Array.isArray(z.members) ? z.members : [],
            operational: true,
            status: z.status || 'REVIEW_REQUIRED',
          },
        }));
      } catch (_) { /* ignore */ }
    }
    return z;
  }

  /**
   * Delete a Safety Zone from Transportation: drop registry entry and clear
   * conveyor.safetyZone assignments that pointed at it. Display-only membership.
   * Accepts source_id or engineering_name.
   */
  function deleteSafetyZone(nameOrId) {
    const nm = String(nameOrId || '').trim();
    if (!nm) return false;
    const lower = nm.toLowerCase();
    const match = (z) => {
      const sid = String(z.source_id || z.id || '').trim().toLowerCase();
      const eng = String(z.engineering_name || z.name || '').trim().toLowerCase();
      return sid === lower || eng === lower;
    };
    const doomed = (tb.safetyZones || []).filter(match);
    const engNames = new Set(
      doomed.map((z) => String(z.engineering_name || z.name || '').trim().toLowerCase()).filter(Boolean),
    );
    if (engNames.size === 0) engNames.add(lower);
    tb.safetyZones = (tb.safetyZones || []).filter((z) => !match(z));
    (tb.areas || []).forEach((area) => {
      (area.nodes || []).forEach((n) => {
        const zn = String(n.safetyZone || '').trim().toLowerCase();
        if (engNames.has(zn) || zn === lower) n.safetyZone = '';
      });
    });
    if (tb.activeSafetyZoneId && !(tb.safetyZones || []).some((z) => z.id === tb.activeSafetyZoneId)) {
      tb.activeSafetyZoneId = (tb.safetyZones[0] && tb.safetyZones[0].id) || null;
    }
    const ctxZ = String(tb.buildContext?.safetyZone || '').trim().toLowerCase();
    if (engNames.has(ctxZ) || ctxZ === lower) {
      tb.buildContext.safetyZone = '';
    }
    try { save(); } catch (_) { /* ignore */ }
    try { refreshSafetyZoneSelect(); } catch (_) { /* ignore */ }
    try { render(); } catch (_) { /* ignore */ }
    return true;
  }

  /**
   * Seed Safety Zones from RUN-proven conveyor.safetyZone values.
   * Does NOT invent zones from Area names. Engineer-created zones stay authoritative.
   */
  function seedSafetyZonesFromNodes({ preserveEngineer = true } = {}) {
    const engineerNames = new Set(
      preserveEngineer
        ? (tb.safetyZones || []).map((z) => String(z.name || '').trim()).filter(Boolean)
        : []
    );
    const found = new Set(engineerNames);
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        const z = String(n.safetyZone || '').trim();
        if (z) found.add(z);
      });
    });
    tb.safetyZones = [...found].sort((a, b) => a.localeCompare(b)).map((name) => {
      const prev = (tb.safetyZones || []).find((z) => {
        const eng = String(z.engineering_name || z.name || '').trim().toLowerCase();
        return eng === name.toLowerCase();
      });
      if (prev) {
        if (!prev.source_id || prev.source_id === prev.name) {
          prev.source_id = (prev.id && String(prev.id).startsWith('szone_'))
            ? prev.id
            : uid('szone');
          prev.id = prev.source_id;
        }
        if (!prev.engineering_name) prev.engineering_name = prev.name || name;
        return prev;
      }
      const sid = uid('szone');
      return {
        id: sid,
        source_id: sid,
        name,
        engineering_name: name,
        status: 'REVIEW_REQUIRED',
      };
    });
    if (!tb.activeSafetyZoneId || !(tb.safetyZones || []).some((z) => z.id === tb.activeSafetyZoneId)) {
      tb.activeSafetyZoneId = (tb.safetyZones[0] && tb.safetyZones[0].id) || null;
    }
    return tb.safetyZones;
  }

  function refreshSafetyZoneSelect() {
    const sel = $('tb-szone-select');
    if (!sel) return;
    const zones = tb.safetyZones || [];
    if (!zones.length) {
      sel.innerHTML = '<option value="">— none —</option>';
      return;
    }
    sel.innerHTML = zones
      .map(
        (z) =>
          `<option value="${escapeHtml(z.id)}" ${z.id === tb.activeSafetyZoneId ? 'selected' : ''}>${escapeHtml(z.name)}</option>`
      )
      .join('');
  }

  function resetView100() {
    if (!tb.view) tb.view = { zoom: 1, canvasScale: null, mode: 'site' };
    tb.view.zoom = 1;
    applyViewportZoom();
    // Center current area at 100% — do not jump to top-left (biases right on next zoom).
    const area = activeArea();
    const nodes = area?.nodes || [];
    if (nodes.length) {
      fitViewToNodes(nodes, {
        mode: 'area',
        paddingFrac: 0.08,
        minZoom: 1,
        maxZoom: 1,
        excludeOutliers: !tb.physicalLayout,
      });
    } else {
      const canvas = $('tb-canvas');
      if (canvas) {
        canvas.scrollLeft = 0;
        canvas.scrollTop = 0;
      }
    }
    render();
    status('Reset View · 100% centered (presentation only)');
  }

  /** Zoom +/- around viewport center (presentation only — no model mutation). */
  function zoomByFactor(factor) {
    const canvas = $('tb-canvas');
    if (!tb.view) tb.view = { zoom: 1, canvasScale: null, mode: 'site' };
    const lim = viewportZoomLimits();
    const before = Math.max(lim.min, Number(tb.view.zoom) || 1);
    const next = Math.max(lim.min, Math.min(lim.max, before * (Number(factor) || 1)));
    if (Math.abs(next - before) < 0.001) return;
    const cx = canvas ? canvas.scrollLeft + canvas.clientWidth / 2 : 0;
    const cy = canvas ? canvas.scrollTop + canvas.clientHeight / 2 : 0;
    const wx = cx / before;
    const wy = cy / before;
    const lodBefore = typeof detailLevel === 'function' ? detailLevel() : null;
    tb.view.zoom = next;
    applyViewportZoom();
    if (canvas) {
      canvas.scrollLeft = wx * next - canvas.clientWidth / 2;
      canvas.scrollTop = wy * next - canvas.clientHeight / 2;
    }
    // Transform-only zoom — do NOT reconstruct the graph/DOM on every step.
    // Only schedule a schematic redraw when LOD band changes (badge density).
    const lodAfter = typeof detailLevel === 'function' ? detailLevel() : null;
    if (lodBefore != null && lodAfter != null && lodBefore !== lodAfter) {
      scheduleDrawSchematic(activeArea());
    }
    status(`Zoom ${Math.round(next * 100)}% (presentation only)`);
  }

  function renderTopologyTable() {
    const body = $('tb-topo-body');
    if (!body) return;
    const rows = [];
    (tb.areas || []).forEach((area) => {
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        const tag = (n.conveyorTag || '').trim();
        const up = getUpstreamTags(area, n.id).join(', ') || '—';
        const ds = String(n.downstream || '').trim();
        const exitPe = peTagsByRole(n, 'exit').join(', ');
        const addPe = peTagsByRole(n, 'add').join(', ');
        const jamPe = peTagsByRole(n, 'jam').join(', ');
        const fullPe = peTagsByRole(n, 'full').join(', ');
        const meta = KIND_META[n.kind] || {};
        const typ = n.asMerge ? 'Merge discharge' : (meta.title || n.kind);
        let st = [];
        if (!tag) st.push('unbound');
        if (n.asMerge) st.push('merge');
        if (n.terminal) st.push('terminal');
        if (!ds && !n.terminal) st.push('no-ds');
        const sel = n.id === tb.selectedId ? ' tb-topo-sel' : '';
        // Lazy editors: do NOT build every downstream/zone <option> for every row.
        const curZone = String(n.safetyZone || '').trim();
        rows.push(`<tr class="${sel}" data-topo-id="${escapeHtml(n.id)}" data-topo-area="${escapeHtml(area.id)}">
          <td class="mono text-cyan-300">${escapeHtml(tag || n.label || n.id)}</td>
          <td class="text-slate-400 text-[10px]">${escapeHtml(area.name || '')}</td>
          <td class="text-slate-400">${escapeHtml(up)}</td>
          <td><button type="button" class="tb-topo-ds-btn text-[10px] mono px-1.5 py-0.5 rounded border border-slate-700 text-cyan-300 hover:border-cyan-600" data-topo-ds-edit="${escapeHtml(n.id)}" title="Edit downstream">${escapeHtml(ds || '—')}</button></td>
          <td>${escapeHtml(typ)}</td>
          <td class="mono">${escapeHtml(exitPe || '—')}</td>
          <td class="mono">${escapeHtml(addPe || '—')}</td>
          <td class="mono">${escapeHtml(jamPe || '—')}</td>
          <td class="mono">${escapeHtml(fullPe || '—')}</td>
          <td><button type="button" class="tb-topo-sz-btn text-[10px] mono px-1.5 py-0.5 rounded border border-slate-700 text-amber-200 hover:border-amber-600" data-topo-sz-edit="${escapeHtml(n.id)}" title="Edit Safety Zone">${escapeHtml(curZone || '—')}</button></td>
          <td class="text-slate-500">${escapeHtml(st.join(', ') || 'ok')}</td>
        </tr>`);
      });
    });
    // Always exactly one blank Add Conveyor row (never enters Apply graph)
    const curArea = activeArea();
    const addAreaOpts = (tb.areas || [])
      .map((a) => `<option value="${escapeHtml(a.id)}" ${curArea && a.id === curArea.id ? 'selected' : ''}>${escapeHtml(a.name)}</option>`)
      .join('');
    rows.push(`<tr id="tb-topo-add-row" class="tb-topo-add-row" data-topo-add="1">
      <td>
        <input id="tb-topo-add-tag" type="text" placeholder="Add conveyor…" autocomplete="off" spellcheck="false"
          class="w-full bg-slate-950 border border-fuchsia-900/50 rounded px-1.5 py-1 text-[10px] mono text-cyan-200"
          style="-webkit-app-region:no-drag" />
      </td>
      <td>
        <select id="tb-topo-add-area" class="bg-slate-950 border border-slate-700 rounded px-1 text-[10px] text-slate-200 max-w-[8.5rem]">
          ${addAreaOpts || '<option value="">— create Area first —</option>'}
        </select>
      </td>
      <td class="text-slate-600">—</td>
      <td>
        <input id="tb-topo-add-ds" type="text" placeholder="Downstream (opt)"
          class="w-full bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-slate-300"
          style="-webkit-app-region:no-drag" />
      </td>
      <td class="text-slate-600">Straight</td>
      <td class="text-slate-600" colspan="5">—</td>
      <td>
        <button type="button" id="tb-topo-add-btn" class="btn-ghost text-[10px] px-2 py-0.5 rounded border border-fuchsia-700/60 text-fuchsia-200" title="Add conveyor to Area + canvas">+</button>
      </td>
    </tr>`);
    body.innerHTML = rows.join('');

    // Lazy downstream / Safety editors — build options for ONE row when clicked
    body.querySelectorAll('[data-topo-ds-edit]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        const nid = btn.getAttribute('data-topo-ds-edit');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n || !area) return;
        const ds = String(n.downstream || '').trim();
        const sel = document.createElement('select');
        sel.setAttribute('data-topo-ds', nid);
        sel.className = 'bg-slate-950 border border-cyan-700 rounded px-1 text-[10px] mono text-cyan-200';
        sel.innerHTML = [`<option value="">—</option>`]
          .concat(
            (area.nodes || [])
              .filter((x) => isConv(x.kind) && x.id !== n.id && (x.conveyorTag || '').trim())
              .map((x) => {
                const t = x.conveyorTag.trim();
                return `<option value="${escapeHtml(t)}" ${t === ds ? 'selected' : ''}>${escapeHtml(t)}</option>`;
              }),
          )
          .join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          n.downstream = sel.value || '';
          markValidationDirty();
          save();
          renderScene();
          renderTopologyPanel();
        });
      });
    });
    body.querySelectorAll('[data-topo-sz-edit]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        const nid = btn.getAttribute('data-topo-sz-edit');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n) return;
        const curZone = String(n.safetyZone || '').trim();
        const zoneNames = listSafetyZoneNames();
        if (curZone && !zoneNames.includes(curZone)) zoneNames.push(curZone);
        const sel = document.createElement('select');
        sel.setAttribute('data-topo-szone', nid);
        sel.className = 'mono text-amber-200 max-w-[9rem] bg-slate-950 border border-amber-800 rounded px-1 text-[10px]';
        sel.innerHTML = [`<option value="">—</option>`]
          .concat(zoneNames.map((z) =>
            `<option value="${escapeHtml(z)}" ${z === curZone ? 'selected' : ''}>${escapeHtml(z)}</option>`))
          .join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          n.safetyZone = sel.value || '';
          markValidationDirty();
          save();
          renderScene();
          renderTopologyPanel();
        });
      });
    });

    const commitAddConveyor = () => {
      const tagInput = $('tb-topo-add-tag');
      const areaSel = $('tb-topo-add-area');
      const dsInput = $('tb-topo-add-ds');
      const raw = String(tagInput?.value || '').trim();
      if (!raw) {
        status('Enter a conveyor tag (e.g. P100)');
        return;
      }
      // Validate: P### / sectioned P###_P# or known RUN inventory tag
      const okTag = /^P\d+[A-Z0-9_]*$/i.test(raw)
        || (typeof runInventory === 'function' && (runInventory()?.conveyors || []).some(
          (c) => String(c).trim().toUpperCase() === raw.toUpperCase()
        ));
      if (!okTag) {
        status(`Invalid conveyor tag “${raw}” — use P### (sections like P136_P1 OK)`);
        return;
      }
      ensureArea();
      let area = (tb.areas || []).find((a) => a.id === (areaSel?.value || '')) || activeArea();
      if (!area) {
        status('Create an Area first');
        return;
      }
      // Reject duplicates across all areas
      const want = raw.toUpperCase();
      for (const a of tb.areas || []) {
        if ((a.nodes || []).some((n) => isConv(n.kind) && String(n.conveyorTag || '').trim().toUpperCase() === want)) {
          status(`Conveyor ${raw} already on canvas (area “${a.name}”)`);
          return;
        }
      }
      const ds = String(dsInput?.value || '').trim();
      // Place to the right of existing nodes in this area
      const xs = (area.nodes || []).filter((n) => isConv(n.kind)).map((n) => Number(n.x) || 0);
      const ys = (area.nodes || []).filter((n) => isConv(n.kind)).map((n) => Number(n.y) || 0);
      const x = (xs.length ? Math.max(...xs) + 140 : 80);
      const y = (ys.length ? ys.reduce((s, v) => s + v, 0) / ys.length : 120);
      let node = null;
      if (typeof window.__tbPass2CreateConv === 'function') {
        node = window.__tbPass2CreateConv({ tag: raw, x, y, area });
      } else {
        // Fallback: addNode then bind tag
        tb.activeAreaId = area.id;
        addNode('conv_straight', x, y, null);
        node = (area.nodes || [])[(area.nodes || []).length - 1];
        if (node) {
          node.conveyorTag = raw;
          node.label = raw;
        }
      }
      if (!node) {
        status('Failed to create conveyor node');
        return;
      }
      if (ds) {
        node.downstream = ds;
        try { setDownstream(node.id, ds, { skipMergePrompt: true }); } catch (_) { /* ignore */ }
      }
      tb.activeAreaId = area.id;
      tb.selectedId = node.id;
      tb.selectedIds = [node.id];
      save();
      render();
      status(`Added ${raw} → area “${area.name}”`);
    };
    $('tb-topo-add-btn')?.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      commitAddConveyor();
    });
    $('tb-topo-add-tag')?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        commitAddConveyor();
      }
    });

    body.querySelectorAll('tr[data-topo-id]').forEach((tr) => {
      tr.addEventListener('click', (ev) => {
        if (ev.target.closest('select')) return;
        const id = tr.getAttribute('data-topo-id');
        const areaId = tr.getAttribute('data-topo-area');
        if (areaId && areaId !== tb.activeAreaId) {
          tb.activeAreaId = areaId;
        }
        selectNode(id);
        const el = document.querySelector(`.tb-node[data-id="${id}"]`);
        const canvas = $('tb-canvas');
        if (el && canvas) {
          const n = activeArea()?.nodes.find((x) => x.id === id);
          if (n) {
            canvas.scrollLeft = Math.max(0, n.x - 120);
            canvas.scrollTop = Math.max(0, n.y - 80);
          }
        }
      });
    });
    body.querySelectorAll('select[data-topo-ds]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const id = sel.getAttribute('data-topo-ds');
        // Ensure active area contains node
        for (const a of tb.areas) {
          if (a.nodes.some((n) => n.id === id)) {
            tb.activeAreaId = a.id;
            break;
          }
        }
        setDownstream(id, sel.value || '', { skipMergePrompt: false });
      });
    });
    body.querySelectorAll('select[data-topo-area-sel]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const nodeId = sel.getAttribute('data-topo-area-sel');
        const destAreaId = sel.value;
        moveNodeToArea(nodeId, destAreaId, { debounceSave: true });
      });
    });
    body.querySelectorAll('select[data-topo-szone]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const nodeId = sel.getAttribute('data-topo-szone');
        const zone = String(sel.value || '').trim();
        let node = null;
        for (const a of tb.areas || []) {
          node = (a.nodes || []).find((n) => n.id === nodeId);
          if (node) break;
        }
        if (!node) return;
        node.safetyZone = zone;
        if (!node.provenance) node.provenance = {};
        node.provenance.safetyZone = 'ENGINEER';
        if (zone) ensureSafetyZone(zone);
        save();
        render();
        status(`Safety Zone → ${zone || '(none)'} on ${nodeLabel(node)}`);
      });
    });
  }

  function _nowMs() {
    return (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  }

  /** Coalesce rapid topo-dropdown area saves; flush on Apply / tab leave. */
  function scheduleAreaAssignPersist() {
    if (_areaAssignSaveTimer) clearTimeout(_areaAssignSaveTimer);
    _areaAssignSaveTimer = setTimeout(() => {
      _areaAssignSaveTimer = 0;
      try { save(); } catch (_) { /* ignore */ }
    }, AREA_ASSIGN_SAVE_MS);
  }

  function flushAreaAssignPersist() {
    if (!_areaAssignSaveTimer) return false;
    clearTimeout(_areaAssignSaveTimer);
    _areaAssignSaveTimer = 0;
    try { save(); } catch (_) { /* ignore */ }
    return true;
  }

  /**
   * Batch Area reassignment (organization/metadata).
   *
   * One topology sync over touched areas, one save, one render — bulk must not
   * multiply per-id save/render. Does not unlock presentation layout or rebuild RUN.
   *
   * opts.skipSave / opts.skipRender — caller owns persist/paint (e.g. bulk + post-edits)
   * opts.debounceSave — topo dropdown: render now, persist ~75ms later
   * opts.silent — suppress status line
   */
  function moveNodesToArea(ids, destAreaId, opts) {
    const o = opts || {};
    const dest = (tb.areas || []).find((a) => a.id === destAreaId);
    if (!dest) return { moved: 0, n: 0 };
    const idList = [...new Set((ids || []).filter(Boolean).map(String))];
    if (!idList.length) return { moved: 0, n: 0 };

    const tAll0 = _nowMs();
    const bySrc = new Map();
    for (const nodeId of idList) {
      let found = null;
      for (const a of tb.areas || []) {
        const node = (a.nodes || []).find((n) => n.id === nodeId);
        if (node) {
          found = { node, srcArea: a, nodeId };
          break;
        }
      }
      if (!found) continue;
      if (found.srcArea.id === destAreaId) continue;
      if (!bySrc.has(found.srcArea)) bySrc.set(found.srcArea, []);
      bySrc.get(found.srcArea).push(found);
    }
    if (!bySrc.size) return { moved: 0, n: 0 };

    const movedNodes = [];
    const touched = new Set([dest]);
    bySrc.forEach((items, srcArea) => {
      touched.add(srcArea);
      syncDownstreamFromWires(srcArea);
      const removeIds = new Set(items.map((it) => it.nodeId));
      items.forEach(({ node, nodeId }) => {
        const keptDownstream = String(node.downstream || '').trim();
        const myTag = String(node.conveyorTag || '').trim();
        inboundWires(srcArea, nodeId).forEach((w) => {
          const src = (srcArea.nodes || []).find((n) => n.id === w.from);
          if (!src) return;
          if (myTag) src.downstream = myTag;
        });
        node.downstream = keptDownstream;
        // Logic Area membership change must NOT silently rewrite Safety Zone or PI Area.
        // Only apply Area default Safety Zone when the node has none AND caller opts in
        // via opts.applyAreaDefaultSafety (legacy Auto Build). Engineer Assign never opts in.
        if (o.applyAreaDefaultSafety && !String(node.safetyZone || '').trim()) {
          const defZ = String(dest.defaultSafetyZone || '').trim();
          if (defZ) {
            node.safetyZone = defZ;
            if (!node.provenance) node.provenance = {};
            node.provenance.safetyZone = 'AREA_DEFAULT';
          }
        }
        movedNodes.push(node);
      });
      srcArea.nodes = (srcArea.nodes || []).filter((n) => !removeIds.has(n.id));
      srcArea.wires = (srcArea.wires || []).filter(
        (w) => !removeIds.has(w.from) && !removeIds.has(w.to)
      );
    });

    dest.nodes = dest.nodes || [];
    movedNodes.forEach((node) => {
      dest.nodes.push(node);
    });

    const tSync0 = _nowMs();
    touched.forEach((a) => {
      syncDownstreamFromWires(a);
      syncWiresFromDownstream(a);
      invalidateNodeIndex(a);
    });
    const sync_ms = _nowMs() - tSync0;

    // Area assignment must NOT switch the displayed Area / viewport.
    // Do NOT forcePresentationRelayout / rebuild RUN geometry on membership change.
    if (movedNodes.length) {
      const last = movedNodes[movedNodes.length - 1];
      const movedIds = movedNodes.map((n) => n.id);
      tb.selectedId = last.id;
      if (Array.isArray(tb.selectedIds)) {
        const keep = (tb.selectedIds || []).filter((id) => movedIds.includes(id));
        tb.selectedIds = keep.length ? keep : movedIds.slice();
      }
    }
    invalidateSchematicHitGeometry();

    let save_ms = 0;
    let render_ms = 0;
    if (!o.skipSave) {
      if (o.debounceSave) {
        scheduleAreaAssignPersist();
      } else {
        const tSave0 = _nowMs();
        flushAreaAssignPersist();
        save();
        save_ms = _nowMs() - tSave0;
      }
    }
    if (!o.skipRender) {
      const tRender0 = _nowMs();
      render();
      try {
        drawSchematic(activeArea());
        drawWires();
        applyViewportZoom();
      } catch (_) { /* ignore */ }
      render_ms = _nowMs() - tRender0;
    }

    const n = movedNodes.length;
    perfRecord('transport.areaAssign', _nowMs() - tAll0, {
      sync_ms: Math.round(sync_ms * 100) / 100,
      save_ms: Math.round(save_ms * 100) / 100,
      render_ms: Math.round(render_ms * 100) / 100,
      n,
      debounceSave: !!o.debounceSave,
    });

    if (!o.silent && n) {
      const sample = nodeLabel(movedNodes[0]);
      status(
        n === 1
          ? `Moved ${sample} → area ${dest.name} (view unchanged · topology preserved)`
          : `Moved ${n} conveyor(s) → area ${dest.name} (view unchanged · topology preserved)`
      );
    }
    return { moved: n, n, destId: dest.id };
  }

  /** Single-node Area reassignment — delegates to batch primitive. */
  function moveNodeToArea(nodeId, destAreaId, opts) {
    return moveNodesToArea(nodeId != null ? [nodeId] : [], destAreaId, opts);
  }

  function fillDownstreamSelect(sel, node) {
    if (!sel || !node) return;
    const area = activeArea();
    const cur = String(node.downstream || '').trim();
    const opts = (area?.nodes || [])
      .filter((n) => isConv(n.kind) && n.id !== node.id)
      .map((n) => (n.conveyorTag || '').trim())
      .filter(Boolean);
    let html = `<option value="">— none / terminal —</option>`;
    opts.forEach((t) => {
      html += `<option value="${escapeHtml(t)}" ${t === cur ? 'selected' : ''}>${escapeHtml(t)}</option>`;
    });
    if (cur && !opts.includes(cur)) {
      html += `<option value="${escapeHtml(cur)}" selected>${escapeHtml(cur)} (missing)</option>`;
    }
    sel.innerHTML = html;
  }

  function centerOnNode(id) {
    const n = activeArea()?.nodes.find((x) => x.id === id);
    const canvas = $('tb-canvas');
    if (!n || !canvas) return;
    canvas.scrollLeft = Math.max(0, n.x - 140);
    canvas.scrollTop = Math.max(0, n.y - 100);
  }


  /** True for Fortna belt tags like P100 / P208A — not SS, SSV, ENC, ES, motors. */
  function isConveyorTag(name) {
    const n = String(name || '').trim();
    if (!n) return false;
    if (!/^P\d{2,4}[A-Z0-9_]*$/i.test(n)) return false;
    if (/_(AUX|FLT|OK|RUN)$/i.test(n)) return false;
    return true;
  }

  function conveyorOptions() {
    const opts = new Set();
    try {
      if (typeof autogenState !== 'undefined' && autogenState.workbook?.conveyors) {
        autogenState.workbook.conveyors.forEach((r) => {
          if (r?.conveyor && isConveyorTag(r.conveyor)) opts.add(String(r.conveyor));
        });
      }
    } catch (_) { /* ignore */ }
    try {
      if (typeof state !== 'undefined' && Array.isArray(state.conveyors)) {
        state.conveyors.forEach((c) => {
          if (c && isConveyorTag(c)) opts.add(String(c));
        });
      }
    } catch (_) { /* ignore */ }
    // CP5A: decoder-found conveyor candidates (geometry may be UNKNOWN / unplaced)
    try {
      const inv = tb.decoderInventoryTags || {};
      (inv.conveyorCandidates || inv.unplacedConveyorCandidates || []).forEach((c) => {
        if (c && isConveyorTag(c)) opts.add(String(c));
      });
    } catch (_) { /* ignore */ }
    return [...opts].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  /** Reject HMI / sim / clock / counter clutter (not field IO). */
  function isClutterTag(name) {
    const u = String(name || '').trim().toUpperCase();
    if (!u) return true;
    // Photoeye / motor system tags the engineer called out
    if (
      /^(PE_COUNT|PE_FLT|PE_OVERRIDE|PE_SIM|PE_STATE|PE_TO|PESIM)/.test(u) ||
      /^PE_(COUNT|FLT|OVERRIDE|SIM|STATE|TO|TIMERS)/.test(u) ||
      /_(COUNT|COUNTER|TIMERS?|SIM|MSG|STATE|OVERRIDE|TO)$/.test(u) && /PE/.test(u)
    ) {
      return true;
    }
    if (
      /^(M_DAY|M_HOUR|M_MIN|M_MONTH|M_SEC|M_YEAR|MAINT|MAX|MAX_FLOAT|MAX_REAL|MDR_SYS)/.test(u) ||
      /^M_(DAY|HOUR|MIN|MONTH|SEC|YEAR)$/.test(u)
    ) {
      return true;
    }
    if (/^(SYS_|HMI_|SIM_|STAT_|STATS_)/.test(u)) return true;
    if (/_(OK|RUN|FLT|AUX)$/.test(u) && /^(MDR|MSG|SYS)/.test(u)) return true;
    return false;
  }

  /** Name regex / kind filters — field IO only (keeps dropdowns uncluttered). */
  function deviceTagMatches(kind, name, equipmentKind) {
    const n = String(name || '').trim();
    if (!n || isClutterTag(n)) return false;
    const ek = String(equipmentKind || '').toLowerCase();
    const u = n.toUpperCase();

    if (kind === 'encoder') {
      // ENC208 / ENC100 — not ENC_SYS / ENCSTATUS
      return /^ENC\d+[A-Z0-9_]*$/i.test(n);
    }
    if (kind === 'photoeye') {
      // Real eyes: PE208, PE208_P, EZPE116_F, PES1-9_I, PES1_9_I — not PE_COUNT / PE_SIM
      if (!/PE/i.test(n)) return false;
      if (/^PE_[A-Z]/.test(u)) return false; // PE_COUNT, PE_SIM, …
      if (/SIM|COUNT|TIMER|OVERRIDE|STATE|_TO$|_MSG|_FLT_/.test(u)) return false;
      return (
        /^PE\d+[A-Z0-9_-]*$/i.test(n) ||
        /^EZPE\d+[A-Z0-9_-]*$/i.test(n) ||
        /^PES\d+[A-Z0-9_-]*$/i.test(n) ||
        /^P\d+PE\d*[A-Z0-9_-]*$/i.test(n) ||
        (ek === 'photoeye' && /^[A-Z0-9_-]*PE[A-Z0-9_-]*$/i.test(n) && /\d/.test(n))
      );
    }
    if (kind === 'motor') {
      // M66 / M66A / M66_AUX / VFD208 — not M_Day, MAINT, MAX, MDR_SYS
      if (/^VFD\d+[A-Z0-9_]*$/i.test(n) || ek === 'vfd') return /^VFD\d/i.test(n);
      return /^M\d+[A-Z]?(?:_AUX)?$/i.test(n);
    }
    if (kind === 'estop') {
      return (
        /^ESL?\d+[A-Z0-9_]*$/i.test(n) ||
        /^ESTP\d+[A-Z0-9_]*$/i.test(n) ||
        /^ESPB\d+[A-Z0-9_]*$/i.test(n) ||
        /^\d+ES\d+[A-Z0-9_]*$/i.test(n)
      );
    }
    if (kind === 'pws') {
      // EZPWS27, EZPWS13P6, PWS2, PS12 — field power supplies
      return (
        /^EZPWS[A-Z0-9_]*$/i.test(n) ||
        /^PWS\d+[A-Z0-9_]*$/i.test(n) ||
        /^PS\d+[A-Z0-9_]*$/i.test(n) ||
        ek === 'power_supply'
      );
    }
    return false;
  }

  /** PWS / standalone contact-start units can bind EZPWS* as their "conveyor" tag. */
  function isPwsTag(name) {
    return deviceTagMatches('pws', name, 'power_supply');
  }

  /**
   * Tags that Autogen will actually emit into the L5X (IO map / PE_UDT / motors).
   * Keeps Merge_2to1 PE operands from referencing undefined Studio tags.
   */
  function buildableTagCatalog() {
    const byKind = {
      photoeye: new Set(),
      motor: new Set(),
      encoder: new Set(),
      estop: new Set(),
      pws: new Set(),
      all: new Set(),
    };
    const add = (kind, name) => {
      const n = String(name || '').trim();
      if (!n || n.toUpperCase() === 'NO_PE') return;
      if (!deviceTagMatches(kind, n, kind === 'photoeye' ? 'photoeye' : '')) return;
      byKind[kind]?.add(n);
      byKind.all.add(n);
    };
    try {
      const wb = typeof autogenState !== 'undefined' ? autogenState.workbook : null;
      if (wb) {
        (wb.options?.exit_pe || []).forEach((p) => add('photoeye', p));
        (wb.conveyors || []).forEach((r) => {
          add('photoeye', r.exit_pe_tag);
          (r.exit_pe_choices || []).forEach((p) => add('photoeye', p));
          (r.jam_pe_tags || []).forEach((p) => add('photoeye', p));
          (r.product_pe_tags || []).forEach((p) => add('photoeye', p));
          (r.full_pe_tags || []).forEach((p) => add('photoeye', p));
          (r.all_pe_tags || []).forEach((p) => add('photoeye', p));
        });
        const ioList = wb.io_points || wb.io || [];
        ioList.forEach((r) => {
          const name = r.device || r.device_name || r.fortna_name || r.name;
          const dt = String(r.device_type || r.equipment_kind || '').toLowerCase();
          // Power supplies are often unmapped in workbook — still list EZPWS*
          const isPwsType = dt.includes('power') || dt === 'pws';
          if (r.mapped === false && !isPwsType) return;
          if (dt.includes('photo') || dt === 'pe') add('photoeye', name);
          else if (dt.includes('motor') || dt === 'vfd') add('motor', name);
          else if (dt.includes('encod')) add('encoder', name);
          else if (dt.includes('estop') || dt.includes('e-stop')) add('estop', name);
          else if (isPwsType) add('pws', name);
        });
      }
    } catch (_) { /* ignore */ }
    try {
      if (typeof state !== 'undefined' && Array.isArray(state.devices)) {
        state.devices.forEach((d) => {
          const name = d.name || d.fortna_name || d.tag;
          const ek = d.equipment_kind || d.category || d.device_type;
          const ekL = String(ek || '').toLowerCase();
          if (ekL.includes('photo')) add('photoeye', name);
          else if (ekL.includes('motor') || ekL === 'vfd') add('motor', name);
          else if (ekL.includes('encod')) add('encoder', name);
          else if (ekL.includes('estop')) add('estop', name);
          else if (ekL.includes('power')) add('pws', name);
        });
      }
    } catch (_) { /* ignore */ }
    return byKind;
  }

  function deviceTagOptions(kind) {
    const cat = buildableTagCatalog();
    const set = cat[kind] || new Set();
    // Only buildable tags — do not offer free-form RUN noise that won't exist in L5X
    return [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  function fillTagSelect(sel, kind, selected) {
    if (!sel) return;
    const opts = deviceTagOptions(kind);
    const allowNone = kind === 'photoeye' || kind === 'encoder' || kind === 'pws';
    const emptyLab = allowNone
      ? '— none / NO_PE (build OK) —'
      : `— select ${kind} (buildable) —`;
    const paintSelect = (filter) => {
      const q = String(filter || '').trim().toUpperCase();
      // Type "vfd" → only VFD*; type "m66" → motors matching; empty → full list
      const hits = opts.filter((t) => !q || t.toUpperCase().includes(q));
      let html = `<option value="">${emptyLab}</option>`;
      hits.slice(0, 200).forEach((t) => {
        html += `<option value="${escapeHtml(t)}" ${t === selected ? 'selected' : ''}>${escapeHtml(t)}</option>`;
      });
      if (selected && !hits.includes(selected) && !opts.includes(selected)) {
        html += `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} (⚠)</option>`;
      } else if (selected && opts.includes(selected) && !hits.includes(selected)) {
        html += `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>`;
      }
      sel.innerHTML = html;
      if (selected && hits.includes(selected)) sel.value = selected;
    };
    paintSelect('');

    // Type box + live-filtered dropdown (both visible)
    const host = sel.closest?.('.tb-combo') || sel.parentElement;
    if (host) {
      host.classList.add('tb-combo');
      let input = host.querySelector('input.tb-combo-input');
      if (!input) {
        input = document.createElement('input');
        input.type = 'text';
        input.className = 'tb-combo-input mb-1';
        input.autocomplete = 'off';
        host.insertBefore(input, sel);
      }
      const hint =
        kind === 'motor'
          ? 'Type VFD… or M… to filter'
          : kind === 'photoeye'
            ? 'Type PE… to filter'
            : kind === 'pws'
              ? 'Type EZPWS… to filter'
              : `Type to filter ${kind}…`;
      input.placeholder = hint;
      input.value = '';
      sel.style.display = ''; // keep dropdown visible
      input.oninput = () => {
        paintSelect(input.value);
        // Auto-open feel: if exactly one hit, preview it
      };
      input.onkeydown = (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const q = input.value.trim().toUpperCase();
          const hits = opts.filter((t) => !q || t.toUpperCase().includes(q));
          const pick = hits.find((t) => t.toUpperCase() === q) || hits[0] || '';
          if (pick) {
            sel.value = pick;
            selected = pick;
            paintSelect('');
            input.value = '';
            sel.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      };
      // Selecting from dropdown still works normally
    }
  }

  function refreshAreaSelect() {
    const sel = $('tb-area-select');
    if (!sel) return;
    // Default Area first, visually marked; engineer Areas follow
    const ordered = [...(tb.areas || [])].sort((a, b) => {
      const da = isDefaultArea(a) ? 0 : 1;
      const db = isDefaultArea(b) ? 0 : 1;
      if (da !== db) return da - db;
      return String(a.name || '').localeCompare(String(b.name || ''));
    });
    sel.innerHTML = ordered
      .map((a) => {
        const label = isDefaultArea(a)
          ? `${DEFAULT_AREA_NAME} (${ownedTransportNodes(a).length})`
          : `${a.name} (${ownedTransportNodes(a).length})`;
        return `<option value="${a.id}" ${a.id === tb.activeAreaId ? 'selected' : ''}>${escapeHtml(label)}</option>`;
      })
      .join('');
    refreshSafetyZoneSelect();
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function isConv(kind) {
    return !!(KIND_META[kind] && KIND_META[kind].isConv);
  }

  /**
   * Screen/client pointer → world/model coordinates used by node.x/y and schematic pathCanvas.
   *
   * Pipeline (must stay in sync with applyViewportZoom + marquee):
   *   clientX/Y
   *   → subtract canvas getBoundingClientRect (viewport)
   *   → add scrollLeft/Top (pan via overflow scroll)
   *   → divide by view.zoom (CSS scale on #tb-nodes / #tb-schematic / #tb-marquee)
   *   → world coordinates
   *
   * Do not apply hardcoded offsets. Marquee CSS left/top are world coords on a
   * layer that receives the same scale(z) transform as the conveyors.
   */
  function canvasPointFromEvent(ev) {
    // AUTHORITATIVE: convert client → schematic SVG user space via live CTM.
    // This stays in sync with CSS scale(zoom), scroll, and current SVG size after
    // Area moves / re-layout — never use a stale manual transform cache.
    const schematic = $('tb-schematic');
    if (schematic && typeof schematic.createSVGPoint === 'function') {
      try {
        const pt = schematic.createSVGPoint();
        pt.x = ev.clientX;
        pt.y = ev.clientY;
        const ctm = schematic.getScreenCTM();
        if (ctm) {
          const sp = pt.matrixTransform(ctm.inverse());
          return { x: sp.x, y: sp.y };
        }
      } catch (_) { /* fall through */ }
    }
    const canvas = $('tb-canvas');
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    return {
      x: (ev.clientX - rect.left + canvas.scrollLeft) / z,
      y: (ev.clientY - rect.top + canvas.scrollTop) / z,
    };
  }

  /**
   * Invalidate HIT caches only (labels / ephemeral pick map).
   * Does NOT unlock presentation layout — Area membership changes must redraw
   * with frozen display_dx/dy so unrelated conveyors keep their editor positions.
   */
  function invalidateSchematicHitGeometry() {
    tb._schematicLabelPos = null;
    // Keep tb._presentationOffsets when frozen; clear only if unlocked so next
    // draw rebuilds from persistent per-node display_dx/dy.
    if (!tb.presentationLayoutFrozen) {
      tb._presentationOffsets = null;
    }
  }

  /** Engineer-requested Auto Layout / Rebuild Layout — permission to recompute offsets. */
  function requestPresentationRelayout() {
    tb.forcePresentationRelayout = true;
    tb.presentationLayoutFrozen = false;
    tb._presentationOffsets = null;
    tb._schematicLabelPos = null;
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        if (!n) return;
        n._layoutInitialized = false;
      });
    });
  }

  /** World → scroll-content CSS pixels (inverse of canvasPointFromEvent zoom step). */
  function worldToContentCss(pt) {
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    return { x: (Number(pt?.x) || 0) * z, y: (Number(pt?.y) || 0) * z };
  }

  function presentationScale() {
    const cs = Number(tb.view?.canvasScale);
    if (cs && cs > 0) return cs;
    const m = Number(tb.metrics?.canvas_scale);
    if (m && m > 0) return m;
    return 0.01;
  }

  function isPhysicalSeg(n) {
    return !!(n && n.physical && isConv(n.kind) && (n.length != null || n.sourceX != null));
  }

  function isSchematicNode(n) {
    return !!(n && n.physical && (n.schematic || (n.pathCanvas && n.pathCanvas.length) || n.entryCanvas));
  }

  /** Normalize controlPanel to CP1/CP2/CP3/Other or "". Presentation metadata only. */
  function normalizeControlPanel(v) {
    const s = String(v || '').trim();
    if (!s) return '';
    const u = s.toUpperCase();
    if (u === 'OTHER') return 'Other';
    const m = u.match(/^CP\s*(\d{1,2})$/);
    if (m) return `CP${Number(m[1])}`;
    return s;
  }

  /**
   * Infer controlPanel ONLY from strong RUN evidence.
   * Machine_Name embedding CP# (ORNCCP2 → CP2) or explicit CP token.
   * If unsure, return "" — engineer assigns manually.
   */
  function inferControlPanelFromEvidence(n) {
    if (!n) return '';
    const existing = normalizeControlPanel(n.controlPanel);
    if (existing) return existing;
    const mn = String(n.machineName || n.machine_name || '').trim().toUpperCase();
    if (!mn || ['N/A', 'INVALID', 'NONE', 'ALL', '0'].includes(mn)) return '';
    // Explicit CP token bounded by non-alnum (or string edges)
    let m = mn.match(/(?:^|[^A-Z0-9])(CP\d{1,2})(?=[^A-Z0-9]|$)/);
    if (m) return normalizeControlPanel(m[1]);
    // Trailing embedded form common in Fortna controllers: ORNCCP2, MSCRENOCP3
    m = mn.match(/CP(\d{1,2})$/);
    if (m) return `CP${Number(m[1])}`;
    return '';
  }

  function ensureControlPanel(n, { forceInfer = false } = {}) {
    if (!n) return '';
    if (!forceInfer && n.controlPanel != null && String(n.controlPanel).trim() !== '') {
      n.controlPanel = normalizeControlPanel(n.controlPanel);
      return n.controlPanel;
    }
    if (n.controlPanel == null) n.controlPanel = '';
    const inferred = inferControlPanelFromEvidence({ ...n, controlPanel: '' });
    if (inferred) {
      n.controlPanel = inferred;
      n.controlPanelProvenance = 'RUN_EXPLICIT';
    } else if (forceInfer) {
      n.controlPanel = '';
      n.controlPanelProvenance = 'UNKNOWN';
    }
    return n.controlPanel || '';
  }

  /** Unique Control Panel tags present on the current Transport graph (RUN-derived). */
  function discoveredControlPanels() {
    const set = new Set();
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        const cp = normalizeControlPanel(n?.controlPanel);
        if (cp) set.add(cp);
      });
    });
    return [...set].sort((a, b) => {
      const na = a.match(/^CP(\d+)$/i);
      const nb = b.match(/^CP(\d+)$/i);
      if (na && nb) return Number(na[1]) - Number(nb[1]);
      if (na) return -1;
      if (nb) return 1;
      return a.localeCompare(b);
    });
  }

  function cpFilterActive() {
    const f = tb.cpFilters || {};
    return Object.keys(f).some((k) => !!f[k]);
  }

  function nodeMatchesCpFilter(n) {
    if (!cpFilterActive()) return true;
    const cp = normalizeControlPanel(n?.controlPanel);
    const f = tb.cpFilters || {};
    return !!(cp && f[cp]);
  }

  /** Snapshot canvas geometry for undo-safe group moves (does not touch sourceX/Y). */
  function captureNodeGeom(n) {
    if (!n) return null;
    return {
      id: n.id,
      x: Number(n.x) || 0,
      y: Number(n.y) || 0,
      entryCanvas: n.entryCanvas ? { ...n.entryCanvas } : null,
      exitCanvas: n.exitCanvas ? { ...n.exitCanvas } : null,
      pathCanvas: Array.isArray(n.pathCanvas) ? JSON.parse(JSON.stringify(n.pathCanvas)) : null,
      arcSamplesCanvas: Array.isArray(n.arcSamplesCanvas)
        ? JSON.parse(JSON.stringify(n.arcSamplesCanvas))
        : null,
    };
  }

  /** Apply dx/dy from a captureNodeGeom origin. Preserves relative geometry. */
  function applyNodeGeomDelta(n, origin, dx, dy) {
    if (!n || !origin) return;
    const nx = (origin.x || 0) + dx;
    const ny = (origin.y || 0) + dy;
    // Avoid negative proxy positions for palette cards; physical schematic may go slightly negative
    const clamp = !(n.physical || isSchematicNode(n));
    n.x = clamp ? Math.max(0, nx) : nx;
    n.y = clamp ? Math.max(0, ny) : ny;
    const adx = n.x - (origin.x || 0);
    const ady = n.y - (origin.y || 0);
    if (origin.entryCanvas) {
      n.entryCanvas = {
        ...origin.entryCanvas,
        x: origin.entryCanvas.x + adx,
        y: origin.entryCanvas.y + ady,
      };
    }
    if (origin.exitCanvas) {
      n.exitCanvas = {
        ...origin.exitCanvas,
        x: origin.exitCanvas.x + adx,
        y: origin.exitCanvas.y + ady,
      };
    }
    if (origin.pathCanvas) {
      n.pathCanvas = origin.pathCanvas.map((cmd) => {
        const c = { ...cmd };
        if (c.x != null) c.x = Number(c.x) + adx;
        if (c.y != null) c.y = Number(c.y) + ady;
        if (c.center && c.center.x != null) {
          c.center = { ...c.center, x: c.center.x + adx, y: c.center.y + ady };
        }
        return c;
      });
    }
    if (origin.arcSamplesCanvas) {
      n.arcSamplesCanvas = origin.arcSamplesCanvas.map((p) => ({
        ...p,
        x: p.x + adx,
        y: p.y + ady,
      }));
    }
  }

  /** Build SVG path `d` from projected pathCanvas commands (Y already flipped). */
  function schematicPathD(pathCanvas) {
    if (!pathCanvas || !pathCanvas.length) return '';
    const parts = [];
    let x0 = null;
    let y0 = null;
    pathCanvas.forEach((cmd) => {
      const c = String(cmd.cmd || '').toLowerCase();
      if (c === 'move') {
        parts.push(`M ${cmd.x} ${cmd.y}`);
        x0 = cmd.x;
        y0 = cmd.y;
      } else if (c === 'line') {
        parts.push(`L ${cmd.x} ${cmd.y}`);
        x0 = cmd.x;
        y0 = cmd.y;
      } else if (c === 'arc') {
        const r = Math.max(1, Number(cmd.radius) || 1);
        const sweep = cmd.sweep_flag != null ? Number(cmd.sweep_flag) : 1;
        const large = Number(cmd.large_arc) || 0;
        parts.push(`A ${r} ${r} 0 ${large} ${sweep} ${cmd.x} ${cmd.y}`);
        x0 = cmd.x;
        y0 = cmd.y;
      }
    });
    return parts.join(' ');
  }

  function isCurveNode(n) {
    if (!n) return false;
    const rk = String(n.renderKind || n.equipmentType || '').toLowerCase();
    if (rk.includes('curve')) return true;
    if (n.kind === 'conv_right' || n.kind === 'conv_left') return true;
    const sweep = Number(n.sweepDeg ?? n.sweep_deg);
    if (Number.isFinite(sweep) && Math.abs(Math.abs(sweep) - 90) < 20) return true;
    return false;
  }

  /** True when pathCanvas has a usable SVG arc (not a near-straight / unreadable chord). */
  function pathHasValidArc(pathCanvas) {
    if (!pathCanvas || !pathCanvas.length) return false;
    const arc = pathCanvas.find((c) => String(c.cmd || '').toLowerCase() === 'arc');
    if (!arc) return false;
    const r = Number(arc.radius);
    const sweep = Math.abs(Number(arc.sweep_deg));
    // Tiny site-scale radii are OK when RUN sweep is present — inflate for display
    // instead of re-synthesizing (re-synthesis was flipping orientation).
    if (Number.isFinite(sweep) && sweep >= 25 && r > 2) return true;
    if (!(r > 18)) return false;
    if (Number.isFinite(sweep) && sweep > 0 && sweep < 25) return false;
    return true;
  }

  /**
   * Legacy helper kept for callers; physical solver never stretches anchors.
   * Min radius is advisory only — endpoints stay immutable.
   */
  function curveDisplayMinRadius(n) {
    const sw = schematicStrokeWidth(n);
    return Math.max(72, sw * 4);
  }

  /** No-op preserve: never inflate by moving endpoints (anchors IMMUTABLE). */
  function inflateCurvePathForDisplay(pathCanvas, n) {
    void n;
    return pathCanvas;
  }

  function _curveUnitFromDeg(deg) {
    const r = (Number(deg) * Math.PI) / 180;
    return { x: Math.cos(r), y: Math.sin(r) };
  }

  function _curvePerp(u, ccw) {
    return ccw ? { x: -u.y, y: u.x } : { x: u.y, y: -u.x };
  }

  function _curveLineIntersect(p1, d1, p2, d2) {
    const det = d1.x * d2.y - d1.y * d2.x;
    if (Math.abs(det) < 1e-9) return null;
    const t = ((p2.x - p1.x) * d2.y - (p2.y - p1.y) * d2.x) / det;
    return { x: p1.x + t * d1.x, y: p1.y + t * d1.y };
  }

  function _curveSnapSignedSweep(signedSweep, fallback) {
    let sweep = Number(signedSweep);
    if (!Number.isFinite(sweep) || Math.abs(sweep) < 1) sweep = fallback;
    if (Math.abs(Math.abs(sweep) - 90) <= 45) sweep = sweep >= 0 ? 90 : -90;
    else if (Math.abs(sweep) > 170) sweep = sweep >= 0 ? 90 : -90;
    return sweep;
  }

  /**
   * Tangent-constrained centerline arc. Entry/exit anchors IMMUTABLE.
   * te/tx = unit flow tangents at entry/exit (canvas space).
   */
  function _curveFromTangents(entry, exit, te, tx) {
    if (!entry || !exit || !te || !tx) return null;
    const teL = Math.hypot(te.x, te.y);
    const txL = Math.hypot(tx.x, tx.y);
    if (!(teL > 1e-9) || !(txL > 1e-9)) return null;
    const teU = { x: te.x / teL, y: te.y / teL };
    const txU = { x: tx.x / txL, y: tx.y / txL };
    const candidates = [];
    for (const entryCcw of [true, false]) {
      for (const exitCcw of [true, false]) {
        const ne = _curvePerp(teU, entryCcw);
        const nx = _curvePerp(txU, exitCcw);
        const c = _curveLineIntersect(entry, ne, exit, nx);
        if (!c) continue;
        const r1 = Math.hypot(c.x - entry.x, c.y - entry.y);
        const r2 = Math.hypot(c.x - exit.x, c.y - exit.y);
        if (!(r1 > 0.5) || Math.abs(r1 - r2) > Math.max(2, 0.08 * r1)) continue;
        const rx = entry.x - c.x;
        const ry = entry.y - c.y;
        if (Math.abs(teU.x * rx + teU.y * ry) > 0.2 * r1) continue;
        let a0 = Math.atan2(entry.y - c.y, entry.x - c.x);
        let a1 = Math.atan2(exit.y - c.y, exit.x - c.x);
        let delta = a1 - a0;
        while (delta > Math.PI) delta -= 2 * Math.PI;
        while (delta < -Math.PI) delta += 2 * Math.PI;
        // SVG Y-down: CW tangent from radius = (ry, -rx)
        const cwDot = teU.x * ry + teU.y * (-rx);
        const ccwDot = teU.x * (-ry) + teU.y * rx;
        let sweepDeg;
        let sweepFlag;
        if (cwDot >= ccwDot) {
          if (delta < 0) delta += 2 * Math.PI;
          sweepDeg = (delta * 180) / Math.PI;
          sweepFlag = 1;
        } else {
          if (delta > 0) delta -= 2 * Math.PI;
          sweepDeg = (delta * 180) / Math.PI;
          sweepFlag = 0;
        }
        if (Math.abs(sweepDeg) < 5 || Math.abs(sweepDeg) > 270) continue;
        candidates.push({
          entry: { x: entry.x, y: entry.y },
          exit: { x: exit.x, y: exit.y },
          center: c,
          radius: r1,
          sweep_deg: sweepDeg,
          sweep_flag: sweepFlag,
          method: 'tangents',
          score: Math.abs(Math.abs(sweepDeg) - 90) + Math.abs(r1 - r2),
        });
      }
    }
    if (!candidates.length) return null;
    candidates.sort((a, b) => a.score - b.score);
    return candidates[0];
  }

  /**
   * Chord + signed sweep → centerline arc. Entry/exit anchors IMMUTABLE.
   * Never grows endpoints for min radius.
   */
  function _curveFromChordAndSweep(entry, exit, signedSweep) {
    if (!entry || !exit) return null;
    const dx = exit.x - entry.x;
    const dy = exit.y - entry.y;
    const chord = Math.hypot(dx, dy);
    if (!(chord > 0.5)) return null;
    const sweep = _curveSnapSignedSweep(signedSweep, -90);
    const half = (Math.abs(sweep) * Math.PI) / 360;
    const sinHalf = Math.sin(half);
    if (!(sinHalf > 1e-9)) return null;
    const r = chord / (2 * sinHalf);
    const mx = (entry.x + exit.x) / 2;
    const my = (entry.y + exit.y) / 2;
    const d = r * Math.cos(half);
    const hx = dx / chord;
    const hy = dy / chord;
    const nx = -hy;
    const ny = hx;
    const c1 = { x: mx + nx * d, y: my + ny * d };
    const c2 = { x: mx - nx * d, y: my - ny * d };
    const crossOf = (c) => (entry.x - c.x) * (exit.y - c.y) - (entry.y - c.y) * (exit.x - c.x);
    // sweep > 0 → flag 1 (CW Y-down); want positive cross for CW
    const wantPositiveCross = sweep > 0;
    const center = (crossOf(c1) > 0) === wantPositiveCross ? c1 : c2;
    const rCl = Math.hypot(entry.x - center.x, entry.y - center.y) || r;
    return {
      entry: { x: entry.x, y: entry.y },
      exit: { x: exit.x, y: exit.y },
      center,
      radius: rCl,
      sweep_deg: sweep,
      sweep_flag: sweep > 0 ? 1 : 0,
      method: 'chord_sweep',
    };
  }

  function _curveSolveToPath(solved) {
    if (!solved) return null;
    return [
      { cmd: 'move', x: Number(solved.entry.x), y: Number(solved.entry.y) },
      {
        cmd: 'arc',
        x: Number(solved.exit.x),
        y: Number(solved.exit.y),
        radius: Math.max(1e-3, Number(solved.radius) || 1),
        sweep_deg: Number(solved.sweep_deg),
        sweep_flag: solved.sweep_flag != null ? Number(solved.sweep_flag) : (solved.sweep_deg > 0 ? 1 : 0),
        large_arc: Math.abs(Number(solved.sweep_deg)) > 180 ? 1 : 0,
        center: { x: solved.center.x, y: solved.center.y },
        method: solved.method || 'physical',
      },
    ];
  }

  function _curveResolveAnchors(n, opts) {
    const loose = !!(opts && opts.loose);
    const ov = (opts && opts.anchors) || {};
    let entry = ov.entry
      ? { x: Number(ov.entry.x), y: Number(ov.entry.y) }
      : (n?.entryCanvas ? { x: Number(n.entryCanvas.x), y: Number(n.entryCanvas.y) } : null);
    let exit = ov.exit
      ? { x: Number(ov.exit.x), y: Number(ov.exit.y) }
      : (n?.exitCanvas ? { x: Number(n.exitCanvas.x), y: Number(n.exitCanvas.y) } : null);
    if ((!entry || !exit) && loose && Array.isArray(n?.pathCanvas) && n.pathCanvas.length) {
      const mv = n.pathCanvas.find((c) => String(c.cmd || '').toLowerCase() === 'move');
      const last = n.pathCanvas[n.pathCanvas.length - 1];
      if (!entry && mv && mv.x != null) entry = { x: Number(mv.x), y: Number(mv.y) };
      if (!exit && last && last.x != null) exit = { x: Number(last.x), y: Number(last.y) };
    }
    return { entry, exit };
  }

  function _curveResolveSignedSweep(n) {
    const existingArc = (n?.pathCanvas || []).find((c) => String(c.cmd || '').toLowerCase() === 'arc');
    let signedSweep = null;
    if (existingArc && existingArc.sweep_deg != null && Number.isFinite(Number(existingArc.sweep_deg))) {
      signedSweep = Number(existingArc.sweep_deg);
    } else if (n?.sweepDeg != null || n?.sweep_deg != null) {
      signedSweep = Number(n.sweepDeg ?? n.sweep_deg);
    } else if (
      n?.sourceAngle != null
      && (n.angleOut != null && n.angleOut !== '' || n.runB != null || n.b != null)
    ) {
      const exitBearing = n.angleOut != null && n.angleOut !== ''
        ? Number(n.angleOut)
        : Number(n.runB ?? n.b);
      let d = exitBearing - Number(n.sourceAngle);
      while (d > 180) d -= 360;
      while (d < -180) d += 360;
      signedSweep = -d; // canvas Y-flip
    } else if (n?.kind === 'conv_left') {
      signedSweep = 90;
    } else {
      signedSweep = -90;
    }
    return _curveSnapSignedSweep(signedSweep, n?.kind === 'conv_left' ? 90 : -90);
  }

  /**
   * Prefer shared topology joints: if A.downstream=B, average A.exit≈B.entry
   * for DISPLAY only (does not mutate canonical entryCanvas/exitCanvas).
   */
  function projectSharedTopologyJoints(nodes) {
    const list = nodes || [];
    const byTag = new Map();
    list.forEach((n) => {
      const t = String(n.conveyorTag || n.label || '').trim().toUpperCase();
      if (t) byTag.set(t, n);
    });
    const overlay = {};
    const ensure = (id) => {
      if (!overlay[id]) overlay[id] = {};
      return overlay[id];
    };
    list.forEach((a) => {
      const ds = String(a.downstream || '').trim().toUpperCase();
      if (!ds || !a.exitCanvas) return;
      const b = byTag.get(ds);
      if (!b || !b.entryCanvas || b.id === a.id) return;
      const ax = Number(a.exitCanvas.x);
      const ay = Number(a.exitCanvas.y);
      const bx = Number(b.entryCanvas.x);
      const by = Number(b.entryCanvas.y);
      const gap = Math.hypot(ax - bx, ay - by);
      if (!(gap < 40)) return; // only project near mates
      const mid = { x: (ax + bx) / 2, y: (ay + by) / 2 };
      ensure(a.id).exit = mid;
      ensure(b.id).entry = mid;
    });
    return overlay;
  }

  /**
   * Physical centerline arc for CURVE display.
   * Entry/exit anchors are IMMUTABLE — never grown for min radius.
   */
  function buildPhysicalCurveDisplayPath(n, opts) {
    const { entry, exit } = _curveResolveAnchors(n, opts);
    if (!entry || !exit) return null;
    const chord = Math.hypot(exit.x - entry.x, exit.y - entry.y);
    if (!(chord > ((opts && opts.loose) ? 0.5 : 2))) return null;

    // Try tangent-constrained solve when entry/exit bearings exist
    let te = null;
    let tx = null;
    if (n?.sourceAngle != null && Number.isFinite(Number(n.sourceAngle))) {
      // Canvas heading: RUN Angle is CCW from +X with Y-up; canvas flips Y → negate
      te = _curveUnitFromDeg(-Number(n.sourceAngle));
    }
    const exitBearing = (n?.angleOut != null && n.angleOut !== '')
      ? Number(n.angleOut)
      : (n?.runB != null || n?.b != null ? Number(n.runB ?? n.b) : null);
    if (exitBearing != null && Number.isFinite(exitBearing)) {
      tx = _curveUnitFromDeg(-exitBearing);
    }
    let solved = null;
    if (te && tx) {
      solved = _curveFromTangents(entry, exit, te, tx);
    }
    if (!solved) {
      solved = _curveFromChordAndSweep(entry, exit, _curveResolveSignedSweep(n));
    }
    return _curveSolveToPath(solved);
  }

  /**
   * DISPLAY-ONLY centerline arc. Delegates to physical solver.
   * Anchors never stretch for min radius (no endpoint inflation).
   */
  function synthesizeCurveDisplayPath(n, opts) {
    return buildPhysicalCurveDisplayPath(n, opts || { loose: true });
  }

  /**
   * Closed annular belt polygon from a centerline arc path.
   * Flat entry/discharge faces — not a round-capped thick stroke (no kidney bean).
   */
  function annularBeltPathDFromCenterline(pathCmds, beltWidthPx) {
    if (!Array.isArray(pathCmds) || !pathCmds.length) return '';
    const arc = pathCmds.find((c) => String(c.cmd || '').toLowerCase() === 'arc');
    const move = pathCmds.find((c) => String(c.cmd || '').toLowerCase() === 'move');
    if (!arc || !move) return '';
    const cx = Number(arc.center?.x);
    const cy = Number(arc.center?.y);
    const r = Number(arc.radius);
    const sweep = Number(arc.sweep_deg);
    const x0 = Number(move.x);
    const y0 = Number(move.y);
    const x1 = Number(arc.x);
    const y1 = Number(arc.y);
    const w = Math.max(4, Number(beltWidthPx) || 12);
    if (![cx, cy, r, sweep, x0, y0, x1, y1].every(Number.isFinite) || !(r > 1)) {
      return '';
    }
    const rOuter = r + w / 2;
    const rInner = Math.max(1, r - w / 2);
    const a0 = Math.atan2(y0 - cy, x0 - cx);
    const a1 = Math.atan2(y1 - cy, x1 - cx);
    const sweepRad = (sweep * Math.PI) / 180;
    // Outer arc follows centerline sweep; inner arc reverses.
    const large = Math.abs(sweep) > 180 ? 1 : 0;
    const sweepFlag = sweep > 0 ? 1 : 0;
    const outerStart = { x: cx + rOuter * Math.cos(a0), y: cy + rOuter * Math.sin(a0) };
    const outerEnd = { x: cx + rOuter * Math.cos(a1), y: cy + rOuter * Math.sin(a1) };
    const innerEnd = { x: cx + rInner * Math.cos(a1), y: cy + rInner * Math.sin(a1) };
    const innerStart = { x: cx + rInner * Math.cos(a0), y: cy + rInner * Math.sin(a0) };
    // M outerStart → A outer → L innerEnd → A reverse inner → Z
    return [
      `M ${outerStart.x} ${outerStart.y}`,
      `A ${rOuter} ${rOuter} 0 ${large} ${sweepFlag} ${outerEnd.x} ${outerEnd.y}`,
      `L ${innerEnd.x} ${innerEnd.y}`,
      `A ${rInner} ${rInner} 0 ${large} ${sweepFlag ? 0 : 1} ${innerStart.x} ${innerStart.y}`,
      'Z',
    ].join(' ');
  }

  /** Resolve display path for a node — prefers valid pathCanvas arc; synthesizes curves. */
  /**
   * Gate B — RUN geometry evidence classification (initial placement):
   *   entryCanvas / exitCanvas / pathCanvas / sourceAngle / b / runB /
   *   sweepDeg / insideRadius → PROVEN (decoder fields exist and are used for
   *   initial X/Y placement when present).
   *   presentation_offsets (display_dx/dy) → DERIVED (Site Forge layout only).
   *   curve_display_orientation (elbow paint L/R) → UNKNOWN — do not synthesize.
   *   topology from equipment numbering → UNKNOWN — never guess.
   * Engineer edits remain authoritative over any RUN-derived placement.
   *
   * Curve orientation for DISPLAY.
   * RUN carries Angle/B/sweep/entry/exit (PROVEN as raw fields),
   * but synthesized elbows have failed visual acceptance (wrong way / stringy arcs).
   * Until orientation is contractually validated for elbow paint, status = UNKNOWN.
   */
  function curveOrientationStatus(n) {
    if (!isCurveNode(n)) return 'N/A';
    const prov = (n && n.provenance) || {};
    const candidates = [
      n.physicalTurnOrientation,
      n.displayOrientation,
      n.turnOrientation,
      prov.physicalTurnOrientation,
      prov.curveOrientation,
      prov.b,
      prov.Angle,
    ];
    for (const c of candidates) {
      const s = String(c || '').trim().toUpperCase();
      if (!s || s === 'UNKNOWN' || s === 'N/A') continue;
      if (s === 'PROVEN' || s === 'RUN_EXPLICIT' || s === 'RUN_DERIVED' || s === 'DERIVED') {
        return s.startsWith('RUN') || s === 'PROVEN' ? 'PROVEN' : 'DERIVED';
      }
      if (s === 'ENGINEER_ASSIGNED' || s === 'LEFT' || s === 'RIGHT' || s === 'CW' || s === 'CCW') {
        return s === 'ENGINEER_ASSIGNED' ? 'ENGINEER_ASSIGNED' : 'PROVEN';
      }
    }
    // Sweep sign on pathCanvas arc is enough to draw a centerline turn
    const arc = (n.pathCanvas || []).find((c) => String(c.cmd || '').toLowerCase() === 'arc');
    if (arc && Number.isFinite(Number(arc.sweep_deg)) && Math.abs(Number(arc.sweep_deg)) >= 25) {
      return 'DERIVED';
    }
    if (n.entryCanvas && n.exitCanvas) return 'DERIVED';
    return 'UNKNOWN';
  }

  /**
   * PL-2 — centralized UNKNOWN-orientation CURVE symbol constants (UI-only).
   * Diagonal angle is a SYMBOL meaning "curve; physical turn unresolved".
   * It MUST NOT be written into model provenance as physical orientation.
   */
  const CURVE_SYMBOL = Object.freeze({
    // Gate 5: oblong body ≈ normal conveyor weight; keep purple curve language
    MIN_LENGTH_PX: 84,
    LENGTH_STROKE_MULT: 4.6,
    BODY_WIDTH_MIN: 19,
    BODY_WIDTH_MAX: 30,
    STROKE_MIN: 19,
    STROKE_MAX: 30,
    // Standardized diagonal for the unknown-orientation glyph (UI-only degrees)
    SYMBOL_ANGLE_DEG: -35,
    BADGE: 'CURVE',
    TOOLTIP_SUFFIX: 'CURVE — orientation UNKNOWN (symbolic diagonal; not physical turn)',
    // Gate F — RUN geometry evidence classification (display only; not PLC semantics)
    EVIDENCE: Object.freeze({
      entryCanvas: 'PROVEN',
      exitCanvas: 'PROVEN',
      pathCanvas: 'PROVEN',
      sourceAngle: 'PROVEN',
      b: 'PROVEN',
      runB: 'PROVEN',
      sweepDeg: 'PROVEN',
      insideRadius: 'PROVEN',
      displayOrientation: 'UNKNOWN',
      physicalTurnLeftRight: 'UNKNOWN',
      presentation_offsets: 'DERIVED',
    }),
  });

  function curveSymbolStrokeWidth(n) {
    const { W } = segSize(n);
    return Math.max(CURVE_SYMBOL.STROKE_MIN, Math.min(CURVE_SYMBOL.STROKE_MAX, W || 20));
  }

  function curveSymbolBodyWidth(n) {
    const sw = curveSymbolStrokeWidth(n);
    return Math.max(CURVE_SYMBOL.BODY_WIDTH_MIN, Math.min(CURVE_SYMBOL.BODY_WIDTH_MAX, sw));
  }

  /**
   * Standardized UNKNOWN-orientation CURVE symbol — oblong/rounded conveyor-like
   * body on a diagonal. UI-ONLY symbol; does NOT set engineering orientation.
   * curveType remains PROVEN; physicalTurnOrientation / displayOrientation = UNKNOWN.
   */
  /**
   * DISPLAY direction vector for CURVE placeholder (Gate B).
   * Uses PROVEN entry/exit (or pathCanvas chord) when available.
   * Returns radians for UI paint only — does NOT set physical LEFT/RIGHT elbow.
   */
  /** Allowed CURVE presentation angles (degrees). DISPLAY only — not physical L/R. */
  const CURVE_DISPLAY_ANGLE_CHOICES = Object.freeze([
    'Auto', 0, 45, 90, 135, 180, -45, -90, -135,
  ]);

  function curveDisplayDirectionRad(n) {
    // Engineer presentation override (persisted on node) — DISPLAY only
    const ov = n?.curveDisplayAngle;
    if (ov != null && ov !== '' && String(ov).toUpperCase() !== 'AUTO') {
      const deg = Number(ov);
      if (Number.isFinite(deg)) return (deg * Math.PI) / 180;
    }
    if (n?.entryCanvas && n?.exitCanvas) {
      const dx = Number(n.exitCanvas.x) - Number(n.entryCanvas.x);
      const dy = Number(n.exitCanvas.y) - Number(n.entryCanvas.y);
      if (Math.hypot(dx, dy) > 0.5) return Math.atan2(dy, dx);
    }
    const path = n?.pathCanvas;
    if (Array.isArray(path) && path.length >= 2) {
      const a = path.find((c) => String(c.cmd || '').toLowerCase() === 'move') || path[0];
      const b = path[path.length - 1];
      const dx = Number(b.x) - Number(a.x);
      const dy = Number(b.y) - Number(a.y);
      if (Math.hypot(dx, dy) > 0.5) return Math.atan2(dy, dx);
    }
    if (n?.sourceAngle != null && Number.isFinite(Number(n.sourceAngle))) {
      // PROVEN field used as DISPLAY heading only (degrees → radians); not elbow chirality
      return (-Number(n.sourceAngle) * Math.PI) / 180;
    }
    // Fallback symbolic angle — still UNKNOWN physical orientation
    return (CURVE_SYMBOL.SYMBOL_ANGLE_DEG * Math.PI) / 180;
  }

  /** Set CURVE presentation angle override. DISPLAY metadata only. */
  function setCurveDisplayAngle(nodeId, angleChoice) {
    let n = null;
    let area = null;
    for (const a of tb.areas || []) {
      const hit = (a.nodes || []).find((x) => x.id === nodeId);
      if (hit) {
        n = hit;
        area = a;
        break;
      }
    }
    if (!n || !isCurveNode(n)) return false;
    if (angleChoice == null || String(angleChoice).toUpperCase() === 'AUTO') {
      delete n.curveDisplayAngle;
      if (n.provenance) delete n.provenance.curveDisplayAngle;
    } else {
      const deg = Number(angleChoice);
      if (!Number.isFinite(deg)) return false;
      n.curveDisplayAngle = deg;
      if (!n.provenance) n.provenance = {};
      n.provenance.curveDisplayAngle = 'ENGINEER_ASSIGNED';
    }
    // Force redraw from mutated display angle — same geometry for body/label/hit
    invalidateSchematicHitGeometry();
    tb._presentationOffsets = null;
    save();
    try {
      if (area) drawSchematic(area);
      else drawSchematic(activeArea());
      drawWires();
      applyViewportZoom();
      render(); // refresh proxy/labels that share transform
    } catch (_) { /* ignore */ }
    status(
      `${nodeLabel(n)} CURVE display angle → ${
        angleChoice == null || String(angleChoice).toUpperCase() === 'AUTO'
          ? 'Auto / RUN'
          : `${angleChoice}°`
      } (presentation only)`,
    );
    return true;
  }

  /** Test helper: sample display path angle (deg) for regression. */
  function curveRenderedDisplayAngleDeg(n) {
    return (curveDisplayDirectionRad(n) * 180) / Math.PI;
  }

  function curveUnknownOrientationSymbolPath(n) {
    const bodyW = curveSymbolBodyWidth(n);
    const minLen = Math.max(CURVE_SYMBOL.MIN_LENGTH_PX, bodyW * CURVE_SYMBOL.LENGTH_STROKE_MULT);
    let mx;
    let my;
    if (n?.entryCanvas && n?.exitCanvas) {
      mx = (Number(n.entryCanvas.x) + Number(n.exitCanvas.x)) / 2;
      my = (Number(n.entryCanvas.y) + Number(n.exitCanvas.y)) / 2;
    } else {
      mx = Number(n.x) || 0;
      my = Number(n.y) || 0;
    }
    // Align oblong with proven display vector when available; NEVER claim LEFT/RIGHT elbow
    const ang = curveDisplayDirectionRad(n);
    const halfL = minLen / 2;
    const halfW = bodyW / 2;
    const ux = Math.cos(ang);
    const uy = Math.sin(ang);
    const nx = -uy;
    const ny = ux;
    // Closed oblong (parallelogram) — same visual weight as a straight section
    const p1 = { x: mx - ux * halfL + nx * halfW, y: my - uy * halfL + ny * halfW };
    const p2 = { x: mx + ux * halfL + nx * halfW, y: my + uy * halfL + ny * halfW };
    const p3 = { x: mx + ux * halfL - nx * halfW, y: my + uy * halfL - ny * halfW };
    const p4 = { x: mx - ux * halfL - nx * halfW, y: my - uy * halfL - ny * halfW };
    return [
      { cmd: 'move', x: p1.x, y: p1.y },
      { cmd: 'line', x: p2.x, y: p2.y },
      { cmd: 'line', x: p3.x, y: p3.y },
      { cmd: 'line', x: p4.x, y: p4.y },
      { cmd: 'line', x: p1.x, y: p1.y },
    ];
  }

  function pathIsPhysicalCenterlineArc(pathCanvas) {
    if (!pathCanvas || !pathCanvas.length) return false;
    return pathCanvas.some((c) => String(c.cmd || '').toLowerCase() === 'arc');
  }

  function displayPathCanvasForNode(n, opts) {
    // Curves: prefer physical tangent/chord centerline arc (immutable anchors).
    // Symbolic UNKNOWN oblong only when anchors cannot resolve an arc.
    if (isCurveNode(n)) {
      const physical = buildPhysicalCurveDisplayPath(n, { loose: true, ...(opts || {}) });
      if (physical && pathIsPhysicalCenterlineArc(physical)) return physical;
      // Preserve a valid RUN pathCanvas arc only if anchors missing (no stretch)
      if (pathHasValidArc(n?.pathCanvas) && !(n?.entryCanvas && n?.exitCanvas)) {
        return n.pathCanvas;
      }
      return curveUnknownOrientationSymbolPath(n);
    }
    return n?.pathCanvas || null;
  }

  /** Effective schematic pick stroke width (px). Visible belt stroke `sw` is unchanged. */
  /** Invisible selection target around belt centerline (~40–50px effective). */
  const SCHEMATIC_HIT_WIDTH = 50;

  /**
   * Gate K — transport geometry diagnostic for a selected node.
   * Report / inspector artifact only — does NOT mutate production layout.
   */
  function buildGeometryDiagnostic(node, area) {
    const n = node || {};
    const a = area || activeArea();
    const tag = String(n.conveyorTag || n.label || n.id || '').trim();
    const offs = a ? (computePresentationOffsets(a.nodes || [], a) || {}) : {};
    const xf = getDisplayTransform(n, offs);
    const entry = n.entryCanvas ? { ...n.entryCanvas } : null;
    const exit = n.exitCanvas ? { ...n.exitCanvas } : null;
    const rendered = {
      anchors: {
        entry: xf.body.entry,
        exit: xf.body.exit,
      },
      centers: xf.body.center,
      entry: xf.body.entry,
      exit: xf.body.exit,
      source_anchor: n.source_anchor || null,
      render_anchor: xf.body.anchor,
      body_center: xf.body.center,
      entry_endpoint: xf.body.entry,
      exit_endpoint: xf.body.exit,
      presentation_offset: xf.offset,
      hit_target: xf.hit_target,
      context_menu_target: xf.context_menu_target,
      same_transform: true,
    };
    const ups = a ? getUpstreamTags(a, n.id) : [];
    const path = displayPathCanvasForNode(n);
    const evid = (CURVE_SYMBOL && CURVE_SYMBOL.EVIDENCE) || {};
    const srcFields = (n.source_geometry && n.source_geometry.fields) || {};
    return {
      kind: 'TransportGeometryDiagnostic',
      version: 2,
      node_id: n.id || '',
      conveyor_tag: tag,
      run: {
        X: n.sourceX != null ? n.sourceX : (n.x ?? null),
        Y: n.sourceY != null ? n.sourceY : (n.y ?? null),
        X_cord: srcFields.X_cord ?? n.sourceX ?? n.x ?? null,
        Y_cord: srcFields.Y_cord ?? n.sourceY ?? n.y ?? null,
        Length: srcFields.Length ?? n.length ?? n.sourceLength ?? null,
        Width: srcFields.Width ?? n.width ?? n.sourceWidth ?? null,
        Angle: srcFields.Angle ?? n.sourceAngle ?? n.rotation ?? n.angle ?? null,
        Type: srcFields.Type || n.equipmentType || n.renderKind || n.kind || null,
        Inside_Radius: srcFields.Inside_Radius ?? n.insideRadius ?? n.Inside_Radius ?? null,
      },
      rendered,
      hitbox: {
        schematic_hit_width_px: SCHEMATIC_HIT_WIDTH,
        visible_stroke_note: 'hit stroke is invisible; belt stroke unchanged',
        hit_equals_body: true,
      },
      upstream: ups,
      downstream: n.terminal ? 'END' : (String(n.downstream || '').trim() || null),
      provenance: {
        geometry: (n.provenance && n.provenance.geometry) || (n.physical ? 'IMPORTED' : 'MANUAL'),
        geometry_authority: n.geometry_provenance
          || (n.provenance && n.provenance.geometry_authority)
          || (n.physical ? 'PROVEN_RUN' : 'UNKNOWN'),
        override_provenance: n.override_provenance || null,
        source_geometry_mutated: !!(n.override_provenance && n.override_provenance.source_geometry_mutated),
        area: (n.provenance && n.provenance.area) || null,
        safetyZone: (n.provenance && n.provenance.safetyZone) || null,
        evidence: evid,
        pathCanvas_cmds: Array.isArray(path) ? path.length : 0,
        physical: !!n.physical,
      },
      geometry_flags: n.geometryFlags || [],
      // Diagnostic-only notes (never drive layout)
      notes: [
        'Gate K diagnostic — report/inspector only; production geometry layout unchanged',
        'Authority: ENGINEER_ASSIGNED > PROVEN_RUN > DERIVED_TOPOLOGY > FALLBACK_LAYOUT > UNKNOWN',
      ],
    };
  }

  /**
   * Gate K — optional site-specific diagnostic notes for known hard cases.
   * Report artifact ONLY — never used as production layout branching.
   */
  function geometryDiagnosticSiteNotes(diag) {
    const tag = String(diag?.conveyor_tag || '').toUpperCase();
    const notes = [];
    // Example hard cases for engineer report review (not production ifs)
    if (tag === 'P500' || tag === 'P536') {
      notes.push({
        tag,
        severity: 'diagnostic',
        message: `${tag} flagged for geometry report review (anchors/angle/hitbox) — layout not altered`,
      });
    }
    return notes;
  }

  async function exportGeometryDiagnostic(node, area) {
    const diag = buildGeometryDiagnostic(node, area);
    diag.site_notes = geometryDiagnosticSiteNotes(diag);
    const payload = {
      generated_at: new Date().toISOString(),
      diagnostic: diag,
      policy: {
        production_layout_unchanged: true,
        site_specific_notes_are_report_only: true,
      },
    };
    const A = window.fortnaAPI || window.api || {};
    const tag = diag.conveyor_tag || diag.node_id || 'node';
    const safe = String(tag).replace(/[^\w.-]+/g, '_');
    // Prefer Electron write when available; else download blob
    try {
      if (typeof A.writeTextFile === 'function') {
        const pathHint = `exports/run-geometry/geom_diag_${safe}.json`;
        await A.writeTextFile(pathHint, JSON.stringify(payload, null, 2));
        status(`Geometry diagnostic → ${pathHint}`);
        return payload;
      }
      if (typeof A.saveTextFile === 'function') {
        await A.saveTextFile({
          defaultPath: `geom_diag_${safe}.json`,
          content: JSON.stringify(payload, null, 2),
        });
        status('Geometry diagnostic exported');
        return payload;
      }
    } catch (err) {
      status(`Geometry diagnostic export warn: ${err?.message || err}`);
    }
    try {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const aEl = document.createElement('a');
      aEl.href = url;
      aEl.download = `geom_diag_${safe}.json`;
      aEl.click();
      URL.revokeObjectURL(url);
      status(`Geometry diagnostic downloaded (${aEl.download})`);
    } catch (err) {
      status(`Geometry diagnostic failed: ${err?.message || err}`);
    }
    return payload;
  }

  function distPointToSeg(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len2 = dx * dx + dy * dy;
    if (!(len2 > 1e-9)) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * dx + (py - y1) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  /** Sample display path to a polyline (arcs ≈ 10 points). Applies presentation offsets. */
  function sampleDisplayPathPoints(n, offsets) {
    const off = (offsets && offsets[n.id]) || { dx: 0, dy: 0 };
    const path = displayPathCanvasForNode(n);
    const pts = [];
    const push = (x, y) => {
      pts.push({ x: Number(x) + (off.dx || 0), y: Number(y) + (off.dy || 0) });
    };
    if (path && path.length) {
      let x0 = null;
      let y0 = null;
      path.forEach((cmd) => {
        const c = String(cmd.cmd || '').toLowerCase();
        if (c === 'move') {
          push(cmd.x, cmd.y);
          x0 = Number(cmd.x);
          y0 = Number(cmd.y);
        } else if (c === 'line') {
          push(cmd.x, cmd.y);
          x0 = Number(cmd.x);
          y0 = Number(cmd.y);
        } else if (c === 'arc') {
          const x1 = Number(cmd.x);
          const y1 = Number(cmd.y);
          const cx = cmd.center && cmd.center.x != null ? Number(cmd.center.x) : null;
          const cy = cmd.center && cmd.center.y != null ? Number(cmd.center.y) : null;
          if (x0 != null && y0 != null && cx != null && cy != null) {
            let a0 = Math.atan2(y0 - cy, x0 - cx);
            let a1 = Math.atan2(y1 - cy, x1 - cx);
            let delta = a1 - a0;
            const sweepFlag = cmd.sweep_flag != null ? Number(cmd.sweep_flag) : 1;
            // SVG Y-down: sweep_flag 1 = CW = positive atan2 delta
            if (sweepFlag === 1) {
              if (delta < 0) delta += 2 * Math.PI;
            } else if (delta > 0) {
              delta -= 2 * Math.PI;
            }
            const r = Math.hypot(x0 - cx, y0 - cy) || Math.max(1, Number(cmd.radius) || 1);
            const samples = 10;
            for (let i = 1; i <= samples; i++) {
              const a = a0 + (delta * i) / samples;
              push(cx + r * Math.cos(a), cy + r * Math.sin(a));
            }
          } else {
            push(x1, y1);
          }
          x0 = x1;
          y0 = y1;
        }
      });
    }
    if (pts.length < 2 && n.entryCanvas && n.exitCanvas) {
      push(n.entryCanvas.x, n.entryCanvas.y);
      push(n.exitCanvas.x, n.exitCanvas.y);
    }
    return pts;
  }

  /** Approximate distance from canvas point to node display centerline. */
  function distanceToDisplayPath(pt, n, offsets) {
    const pts = sampleDisplayPathPoints(n, offsets);
    if (pts.length < 2) return Infinity;
    let best = Infinity;
    for (let i = 1; i < pts.length; i++) {
      const d = distPointToSeg(pt.x, pt.y, pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y);
      if (d < best) best = d;
    }
    return best;
  }

  function schematicLocalNodes(area) {
    return (area?.nodes || []).filter((n) => {
      if (!isSchematicNode(n)) return false;
      if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') return true;
      if (n.displayContext) return false;
      if (n.plcOwned === false) return false;
      if (n.scopeClass === 'OUT_OF_SCOPE' || n.scopeClass === 'UNRESOLVED') return false;
      return true;
    });
  }

  /**
   * Closest-centerline schematic pick. Considers all local schematic nodes within
   * SCHEMATIC_HIT_WIDTH/2 of the display path; tie-break by id.
   */
  function pickSchematicNodeAt(clientX, clientY, area) {
    if (!area) return null;
    const pt = canvasPointFromEvent({ clientX, clientY });
    const nodes = schematicLocalNodes(area);
    // ALWAYS recompute offsets from CURRENT area nodes — never trust a cache that
    // may predate Area reassignment / lane re-separation (stale hitbox bug).
    // Store as the single authoritative presentation geometry for draw + hit.
    const offsets = computePresentationOffsets(nodes, area);
    tb._presentationOffsets = offsets;
    const half = SCHEMATIC_HIT_WIDTH / 2;
    const labelHitR = 24; // guaranteed click target around P-tag / identity
    let best = null;
    let bestDist = Infinity;
    nodes.forEach((n) => {
      // Gate G — hit target uses the SAME authoritative display transform as draw/context
      const xf = getDisplayTransform(n, offsets);
      let d = distanceToDisplayPath(pt, n, offsets);
      const mid = xf.hit_target.center || xf.label;
      const dMid = Math.hypot(pt.x - mid.x, pt.y - mid.y);
      if (dMid <= labelHitR) d = Math.min(d, dMid);
      // Label positions from the same offsets (recompute, don't require prior draw)
      const lab = (tb._schematicLabelPos && tb._schematicLabelPos[n.id]) || null;
      if (lab) {
        const dLab = Math.hypot(pt.x - lab.x, pt.y - lab.y);
        if (dLab <= labelHitR) d = Math.min(d, dLab);
      }
      if (d > half && d > labelHitR) return;
      if (d < bestDist || (d === bestDist && best && String(n.id) < String(best.id))) {
        bestDist = d;
        best = n;
      }
    });
    return best;
  }

  function schematicStrokeWidth(n) {
    // Match physical segment belt thickness (segSize.W) so curves ≠ thin crescents
    const { W } = segSize(n);
    return Math.max(12, Math.min(22, W || 14));
  }

  /**
   * Place P-tag labels with basic collision avoidance.
   * Never moves physical conveyor geometry — only label (x,y) candidates.
   * Preferred: body midpoint; alternate above/below; hide if still colliding
   * (unless selected).
   */
  function placeSchematicLabels(labelCandidates) {
    const placed = [];
    const approxW = (tag) => Math.max(28, String(tag).length * 7.2);
    const H = 14;
    const pad = 3;
    const collides = (box) => placed.some((p) => !(
      box.x2 + pad < p.x1 || box.x1 - pad > p.x2 || box.y2 + pad < p.y1 || box.y1 - pad > p.y2
    ));
    const results = [];
    // Gate 5: selected > local > external; then longer runs keep primary labels
    const ordered = labelCandidates.slice().sort((a, b) => {
      if (a.selected !== b.selected) return a.selected ? -1 : 1;
      if (!!a.external !== !!b.external) return a.external ? 1 : -1;
      return (b.priority || 0) - (a.priority || 0);
    });
    ordered.forEach((c) => {
      const w = approxW(c.tag);
      const ext = !!c.external;
      // External labels prefer offset slots to avoid colliding with local P-tags
      const offsets = ext
        ? [
          { dx: 0, dy: -(H + 8) },
          { dx: w * 0.45, dy: -(H + 6) },
          { dx: -w * 0.45, dy: -(H + 6) },
          { dx: w * 0.55, dy: (H + 4) },
          { dx: -w * 0.55, dy: (H + 4) },
          { dx: 0, dy: (H + 10) },
          { dx: 0, dy: 0 },
        ]
        : [
          { dx: 0, dy: 0 },
          { dx: 0, dy: -(H + 5) },
          { dx: 0, dy: (H + 5) },
          { dx: w * 0.4, dy: -(H + 3) },
          { dx: -w * 0.4, dy: (H + 3) },
          { dx: w * 0.55, dy: 0 },
          { dx: -w * 0.55, dy: 0 },
          { dx: w * 0.35, dy: (H + 8) },
          { dx: -w * 0.35, dy: -(H + 8) },
        ];
      let chosen = null;
      for (let i = 0; i < offsets.length; i++) {
        const o = offsets[i];
        const x = c.x + o.dx;
        const y = c.y + o.dy;
        const box = { x1: x - w / 2, x2: x + w / 2, y1: y - H / 2, y2: y + H / 2 };
        if (!collides(box)) {
          chosen = { x, y, box, hidden: false, offsetIndex: i };
          break;
        }
      }
      if (!chosen) {
        if (c.selected) {
          chosen = {
            x: c.x,
            y: c.y - (H + 10),
            box: { x1: c.x - w / 2, x2: c.x + w / 2, y1: c.y - H * 1.8, y2: c.y - H * 0.4 },
            hidden: false,
            offsetIndex: -1,
            forced: true,
          };
        } else if (ext) {
          // Prefer hiding colliding External text over covering local tags
          chosen = { x: c.x, y: c.y, box: null, hidden: true, offsetIndex: -1 };
        } else {
          chosen = { x: c.x, y: c.y, box: null, hidden: true, offsetIndex: -1 };
        }
      }
      if (!chosen.hidden && chosen.box) placed.push(chosen.box);
      results.push({ ...c, ...chosen });
    });
    return results;
  }

  /**
   * LAYOUT INTERPRETER — presentation-only geometry.
   *
   * RAW ENGINEERING GEOMETRY (sourceX/Y/Angle/Length/Width/pathCanvas/entry/exit)
   * stays authoritative for workbook, PLC downstream, and L5X.
   *
   * DISPLAY = projected canvas + (display_dx, display_dy).
   * Never mutates topology / RUN coordinates / engineering geometry.
   *
   * Passes:
   *   1) stack / parallel lane separation for overlapping bodies
   *   2) merge feed-lane fan (2:1 / 3:1 / sawtooth) when asMerge + inbound wires
   *   3) connectivity-assisted mating nudge for trustworthy physical wires
   */
  function computePresentationOffsets(nodes, area) {
    const offsets = {};
    const listIn = nodes || [];
    // Gate 2 — RUN/Physical default: ZERO per-object presentation offsets.
    // Proven relative XY survives as uniform scale + global translation
    // (+ Y invert already applied when projecting RUN→canvas). Lane separation,
    // cluster spread, merge fans, and mate nudges are opt-in via laneSeparate.
    if (!tb.laneSeparate) {
      listIn.forEach((n) => {
        if (!n) return;
        const reason = tb.geometryAuthorityMode === 'run' ? 'RUN_PHYSICAL_FIDELITY' : '';
        offsets[n.id] = { dx: 0, dy: 0, lane: 0, reason };
        n.display_dx = 0;
        n.display_dy = 0;
        n.display_lane = 0;
        n.display_reason = reason;
        n._layoutInitialized = true;
      });
      tb._presentationOffsets = offsets;
      tb.presentationLayoutFrozen = true;
      tb.forcePresentationRelayout = false;
      return offsets;
    }
    // PL-1: MODEL/REDRAW must not musical-chair frozen editor positions.
    // Reuse persistent display_dx/dy unless engineer requested Rebuild Layout.
    const force = !!tb.forcePresentationRelayout;
    const canReuseFrozen = tb.presentationLayoutFrozen && !force;
    if (canReuseFrozen || (!force && listIn.every((n) => n && n._layoutInitialized))) {
      listIn.forEach((n) => {
        if (!n) return;
        const dx = Number(n.display_dx) || 0;
        const dy = Number(n.display_dy) || 0;
        offsets[n.id] = {
          dx,
          dy,
          lane: Number(n.display_lane) || 0,
          reason: n.display_reason || 'FROZEN_EDITOR_POSITION',
        };
      });
      tb._presentationOffsets = offsets;
      tb.presentationLayoutFrozen = true;
      tb.forcePresentationRelayout = false;
      return offsets;
    }
    listIn.forEach((n) => {
      offsets[n.id] = { dx: 0, dy: 0, lane: 0, reason: '' };
      n.display_dx = 0;
      n.display_dy = 0;
      n.display_lane = 0;
      n.display_reason = '';
    });
    const list = (nodes || []).filter(isSchematicNode);
    const byId = {};
    list.forEach((n) => { byId[n.id] = n; });
    const midOf = (n) => {
      if (n.entryCanvas && n.exitCanvas) {
        return { x: (n.entryCanvas.x + n.exitCanvas.x) / 2, y: (n.entryCanvas.y + n.exitCanvas.y) / 2 };
      }
      return { x: Number(n.x) || 0, y: Number(n.y) || 0 };
    };
    const angOf = (n) => Number(n.sourceAngle != null ? n.sourceAngle : n.rotation) || 0;
    const angDelta = (a, b) => {
      const d = Math.abs(a - b) % 360;
      return Math.min(d, 360 - d);
    };
    const setOff = (n, dx, dy, lane, reason, extra) => {
      const prev = offsets[n.id] || { dx: 0, dy: 0 };
      // Accumulate only when stacking on empty; later passes may refine.
      const out = {
        dx, dy, lane: lane || 0, reason: reason || '',
        ...(extra || {}),
      };
      // Prefer explicit later reason over empty earlier.
      if (prev.reason && !reason) {
        out.dx = prev.dx; out.dy = prev.dy; out.lane = prev.lane; out.reason = prev.reason;
      }
      offsets[n.id] = out;
      n.display_dx = out.dx;
      n.display_dy = out.dy;
      n.display_lane = out.lane;
      n.display_reason = out.reason;
    };

    // --- Pass 1: classify overlaps; separate PARALLEL only ---
    // CONNECTED_SERIAL / CURVE_ASSEMBLY must stay visually joined — do not shove them apart.
    const wiresEarly = (area && area.wires) || [];
    const physicallyLinked = (a, b) => {
      return wiresEarly.some((w) => {
        if (!w.physical) return false;
        const conf = String(w.confidence || '').toUpperCase();
        if (!(conf === 'CONFIRMED' || conf.includes('HIGH'))) return false;
        return (w.from === a.id && w.to === b.id) || (w.from === b.id && w.to === a.id);
      });
    };
    const endpointNear = (a, b) => {
      if (!a?.exitCanvas || !a?.entryCanvas || !b?.exitCanvas || !b?.entryCanvas) return false;
      const pairs = [
        [a.exitCanvas, b.entryCanvas],
        [b.exitCanvas, a.entryCanvas],
        [a.entryCanvas, b.entryCanvas],
        [a.exitCanvas, b.exitCanvas],
      ];
      return pairs.some(([p, q]) => Math.hypot(p.x - q.x, p.y - q.y) < 14);
    };
    const sameEntryOrExit = (a, b) => {
      if (!a?.entryCanvas || !b?.entryCanvas) return false;
      const ee = Math.hypot(a.entryCanvas.x - b.entryCanvas.x, a.entryCanvas.y - b.entryCanvas.y) < 8;
      const xx = a.exitCanvas && b.exitCanvas
        && Math.hypot(a.exitCanvas.x - b.exitCanvas.x, a.exitCanvas.y - b.exitCanvas.y) < 8;
      return ee || xx;
    };
    const classifyPair = (a, b) => {
      // Nested / split ZP segments that share an endpoint (P136 vs P136A) — do not shove apart.
      if (sameEntryOrExit(a, b)) {
        const la = Number(a.length) || 0;
        const lb = Number(b.length) || 0;
        if (angDelta(angOf(a), angOf(b)) < 12 && Math.abs(la - lb) > Math.min(la, lb) * 0.5) {
          return 'SAME_PHYSICAL_ASSEMBLY';
        }
      }
      // Gate 4: RUN XY proximity alone is NOT a physical connection.
      // Only proven physical wires keep bodies visually joined as CONNECTED_SERIAL.
      if (physicallyLinked(a, b)) {
        const ra = String(a.renderKind || a.equipmentType || '').toUpperCase();
        const rb = String(b.renderKind || b.equipmentType || '').toUpperCase();
        if (ra.includes('CURVE') || rb.includes('CURVE')) return 'CURVE_ASSEMBLY';
        return 'CONNECTED_SERIAL';
      }
      if (endpointNear(a, b)) {
        return 'NEAR_MISS_UNCONNECTED';
      }
      const da = angDelta(angOf(a), angOf(b));
      const ma = midOf(a);
      const mb = midOf(b);
      const midDist = Math.hypot(ma.x - mb.x, ma.y - mb.y);
      const layerA = String(a.layer || '');
      const layerB = String(b.layer || '');
      if (layerA && layerB && layerA !== layerB && midDist < 72) return 'DIFFERENT_LAYER';
      // Plenty of canvas room — treat near midpoints as stacks even when angles differ
      // (curve elbows often differ ~90° but still paint on top of each other).
      if (da < 25 && midDist < 72) return 'PARALLEL_CONVEYOR';
      if (midDist < 52) return 'OVERLAPPING_BODY';
      if (da > 50 && midDist < 72) return 'VALID_PHYSICAL_OVERLAP';
      return 'UNKNOWN';
    };
    const groups = [];
    const used = new Set();
    const sorted = list.slice().sort((a, b) => String(a.conveyorTag || a.id).localeCompare(String(b.conveyorTag || b.id)));
    sorted.forEach((n) => {
      if (used.has(n.id)) return;
      const mn = midOf(n);
      const group = [n];
      used.add(n.id);
      sorted.forEach((o) => {
        if (used.has(o.id)) return;
        const mo = midOf(o);
        if (Math.hypot(mn.x - mo.x, mn.y - mo.y) >= 72) return;
        const cls = classifyPair(n, o);
        // Separate parallel stacks AND near-coincident overlapping bodies (incl. curves).
        if (
          cls === 'PARALLEL_CONVEYOR'
          || cls === 'PARALLEL'
          || cls === 'OVERLAPPING_BODY'
          || cls === 'VALID_PHYSICAL_OVERLAP'
        ) {
          group.push(o);
          used.add(o.id);
        } else if (
          cls === 'CONNECTED_SERIAL'
          || cls === 'CURVE_ASSEMBLY'
          || cls === 'SAME_PHYSICAL_ASSEMBLY'
        ) {
          // Mark reason but do not separate — leave display_dx=0 for coherent runs.
          if (!offsets[n.id]?.reason) setOff(n, 0, 0, 0, cls, {});
          if (!offsets[o.id]?.reason) setOff(o, 0, 0, 0, cls, {});
        }
      });
      if (group.length > 1) groups.push(group);
    });
    // Gate 5: wider gap for dense parallel / branch stacks (presentation only).
    const laneGap = 96;
    groups.forEach((group) => {
      group.sort((a, b) => String(a.conveyorTag || '').localeCompare(String(b.conveyorTag || '')));
      // Re-check: if any pair in the group is actually serial-connected, skip separation.
      let serialish = false;
      for (let i = 0; i < group.length && !serialish; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const cls = classifyPair(group[i], group[j]);
          if (
            cls === 'CONNECTED_SERIAL'
            || cls === 'CURVE_ASSEMBLY'
            || cls === 'SAME_PHYSICAL_ASSEMBLY'
          ) { serialish = true; break; }
        }
      }
      if (serialish) {
        group.forEach((n) => setOff(n, 0, 0, 0, 'CONNECTED_SERIAL', { stackSize: group.length }));
        return;
      }
      const reason = group.some((g) => g.asMerge || String(g.equipmentType || '').toUpperCase() === 'MERGE')
        ? 'MERGE_LANE_SEPARATION'
        : 'PARALLEL_LANE_SEPARATION';
      group.forEach((n, i) => {
        const ang = (angOf(n) * Math.PI) / 180;
        const nx = -Math.sin(ang);
        const ny = Math.cos(ang);
        const shift = (i - (group.length - 1) / 2) * laneGap;
        setOff(n, nx * shift, -ny * shift, i, reason, {
          stackIndex: i,
          stackSize: group.length,
          overlapClass: 'PARALLEL',
        });
      });
    });

    // --- Pass 1b: nudge near-coincident LOCAL bodies farther apart ---
    // Canvas has room — prefer readable spacing over exact RUN midpoint coincidence.
    {
      const locals = list.filter((n) => !n.externalReference && n.plcOwned !== false);
      const minSep = 56;
      for (let iter = 0; iter < 2; iter++) {
        for (let i = 0; i < locals.length; i++) {
          for (let j = i + 1; j < locals.length; j++) {
            const a = locals[i];
            const b = locals[j];
            if (physicallyLinked(a, b) || endpointNear(a, b)) continue;
            const oa = offsets[a.id] || { dx: 0, dy: 0 };
            const ob = offsets[b.id] || { dx: 0, dy: 0 };
            const ma = midOf(a);
            const mb = midOf(b);
            const ax = ma.x + (oa.dx || 0);
            const ay = ma.y + (oa.dy || 0);
            const bx = mb.x + (ob.dx || 0);
            const by = mb.y + (ob.dy || 0);
            const d = Math.hypot(ax - bx, ay - by);
            if (d >= minSep) continue;
            const ang = ((angOf(a) + angOf(b)) / 2) * Math.PI / 180;
            const nx = -Math.sin(ang) || 0;
            const ny = Math.cos(ang) || 1;
            const push = (minSep - Math.max(d, 0.1)) / 2;
            setOff(
              a,
              (oa.dx || 0) - nx * push,
              (oa.dy || 0) + ny * push,
              oa.lane || 0,
              oa.reason ? `${oa.reason}+CLUSTER_SPREAD` : 'CLUSTER_SPREAD',
            );
            setOff(
              b,
              (ob.dx || 0) + nx * push,
              (ob.dy || 0) - ny * push,
              ob.lane || 0,
              ob.reason ? `${ob.reason}+CLUSTER_SPREAD` : 'CLUSTER_SPREAD',
            );
          }
        }
      }
    }

    // --- Pass 2: merge feed-lane fan (presentation only) ---
    // When a discharge is marked asMerge (or equipmentType MERGE) with ≥2 inbound
    // wires, spread upstream bodies along the discharge normal so a 2:1 / 3:1 /
    // sawtooth reads as conveyor geometry rather than a node graph.
    const wires = (area && area.wires) || [];
    const mergeNodes = list.filter((n) => n.asMerge || String(n.equipmentType || '').toUpperCase() === 'MERGE'
      || String(n.renderKind || '').toLowerCase() === 'merge');
    mergeNodes.forEach((dst) => {
      const inbound = wires.filter((w) => w.to === dst.id).map((w) => byId[w.from]).filter(Boolean);
      if (inbound.length < 2) return;
      inbound.sort((a, b) => String(a.conveyorTag || a.id).localeCompare(String(b.conveyorTag || b.id)));
      const dang = (angOf(dst) * Math.PI) / 180;
      const nx = -Math.sin(dang);
      const ny = Math.cos(dang);
      const gap = Math.max(28, Math.min(48, (Number(dst.width) || 200) * 0.07));
      inbound.forEach((up, i) => {
        // Do not overwrite a larger stack separation already applied to the upstream.
        const prev = offsets[up.id];
        if (prev && prev.reason === 'PARALLEL_LANE_SEPARATION' && (prev.stackSize || 0) > inbound.length) return;
        const shift = (i - (inbound.length - 1) / 2) * gap;
        const reason = inbound.length >= 3 ? 'SAWTOOTH_OR_MULTI_MERGE_FAN' : 'MERGE_2TO1_FAN';
        setOff(up, nx * shift, -ny * shift, i, reason, {
          mergeDischarge: dst.conveyorTag || dst.id,
          mergeLaneCount: inbound.length,
        });
      });
      // Keep discharge centered (lane 0) with a merge reason marker if unset.
      if (!offsets[dst.id]?.reason) {
        setOff(dst, 0, 0, 0, 'MERGE_DISCHARGE_ANCHOR', { mergeLaneCount: inbound.length });
      }
    });

    // --- Pass 3: connectivity-assisted mating nudge ---
    // For trustworthy physical wires, if display offsets left a gap between
    // upstream EXIT and downstream ENTRY, nudge the *downstream* display origin
    // so endpoints visually mate. Caps small noise only — never invents PLC links.
    wires.forEach((w) => {
      if (!w.physical) return;
      const conf = String(w.confidence || '').toUpperCase();
      if (!(conf === 'CONFIRMED' || conf.includes('HIGH'))) return;
      const a = byId[w.from];
      const b = byId[w.to];
      if (!a?.exitCanvas || !b?.entryCanvas) return;
      const oa = offsets[a.id] || { dx: 0, dy: 0 };
      const ob = offsets[b.id] || { dx: 0, dy: 0 };
      const ax = a.exitCanvas.x + (oa.dx || 0);
      const ay = a.exitCanvas.y + (oa.dy || 0);
      const bx = b.entryCanvas.x + (ob.dx || 0);
      const by = b.entryCanvas.y + (ob.dy || 0);
      const gap = Math.hypot(ax - bx, ay - by);
      // Connected-run display assembly: allow a slightly larger presentation gap
      // so STRAIGHT→CURVE→STRAIGHT reads as one coherent run. Never invents topology.
      if (gap < 0.5 || gap > 28) return;
      // If downstream already has a strong parallel-lane offset, skip (keep lanes apart).
      if (ob.reason && String(ob.reason).includes('PARALLEL') && Math.hypot(ob.dx || 0, ob.dy || 0) > 8) return;
      const ndx = (ob.dx || 0) + (ax - bx);
      const ndy = (ob.dy || 0) + (ay - by);
      setOff(b, ndx, ndy, ob.lane || 0, ob.reason ? `${ob.reason}+MATE_NUDGE` : 'CONNECTED_RUN_MATE', {
        matedFrom: a.conveyorTag || a.id,
        mateGapBefore: gap,
        overlapClass: 'CONNECTED_SERIAL',
      });
    });

    // Lock editor positions after this initial / requested layout pass.
    list.forEach((n) => { if (n) n._layoutInitialized = true; });
    (nodes || []).forEach((n) => {
      if (n && offsets[n.id] && !n._layoutInitialized) n._layoutInitialized = true;
    });
    tb._presentationOffsets = offsets;
    tb.presentationLayoutFrozen = true;
    tb.forcePresentationRelayout = false;
    return offsets;
  }

  function applyPresOffset(pt, off) {
    if (!pt) return pt;
    const o = off || { dx: 0, dy: 0 };
    return { x: pt.x + (o.dx || 0), y: pt.y + (o.dy || 0) };
  }

  /**
   * Gate B/G — ONE authoritative display transform for body, label, selection,
   * hover, right-click, hit testing, context menu, and debug endpoints.
   * Presentation offsets only; never mutates source_geometry / sourceX/Y.
   */
  function getDisplayTransform(n, offsets) {
    // RUN/Physical with laneSeparate OFF: ignore stale presentation offsets so
    // proven relative coordinates are never silently distorted.
    let off = (offsets && n && offsets[n.id]) || {
      dx: Number(n?.display_dx) || 0,
      dy: Number(n?.display_dy) || 0,
    };
    if (!tb.laneSeparate) {
      off = { dx: 0, dy: 0 };
    }
    const useOverride = tb.geometryAuthorityMode === 'override'
      && n?.engineerGeometry
      && (n.engineerGeometry.entry_endpoint || n.engineerGeometry.entryCanvas);
    const eng = useOverride ? n.engineerGeometry : null;
    const entry0 = eng?.entry_endpoint || eng?.entryCanvas || n?.entryCanvas || null;
    const exit0 = eng?.exit_endpoint || eng?.exitCanvas || n?.exitCanvas || null;
    const mid0 = entry0 && exit0
      ? { x: (entry0.x + exit0.x) / 2, y: (entry0.y + exit0.y) / 2 }
      : (n?.body_center || { x: Number(n?.x) || 0, y: Number(n?.y) || 0 });
    const entry = entry0 ? applyPresOffset(entry0, off) : null;
    const exit = exit0 ? applyPresOffset(exit0, off) : null;
    const center = applyPresOffset(mid0, off);
    const anchor0 = n?.render_anchor || n?.source_anchor || entry0 || mid0;
    const anchor = anchor0 ? applyPresOffset(anchor0, off) : center;
    const angle = eng?.angle != null
      ? eng.angle
      : (n?.sourceAngle ?? n?.rotation ?? n?.angle ?? null);
    return {
      body: { entry, exit, center, anchor, angle, length: n?.length, width: n?.width },
      label: { x: center.x, y: center.y },
      hit_target: { center, entry, exit, angle },
      context_menu_target: { center, entry, exit },
      selection: { center },
      hover: { center },
      debug_endpoints: { entry, exit, anchor, center },
      offset: { dx: Number(off.dx) || 0, dy: Number(off.dy) || 0 },
      geometry_provenance: n?.geometry_provenance
        || (n?.provenance && n.provenance.geometry_authority)
        || (n?.physical ? 'PROVEN_RUN' : 'UNKNOWN'),
      same_transform: true,
    };
  }

  /**
   * Gate B — apply engineer geometry override without mutating source geometry.
   * Persists on n.engineerGeometry; sourceX/Y/source_geometry stay intact.
   */
  function applyEngineerGeometryOverride(n, override) {
    if (!n || !override) return n;
    if (!n.source_geometry) {
      n.source_geometry = {
        fields: {
          X_cord: n.sourceX ?? null,
          Y_cord: n.sourceY ?? null,
          Length: n.length ?? null,
          Width: n.width ?? null,
          Angle: n.sourceAngle ?? null,
          Type: n.equipmentType || null,
          Inside_Radius: n.insideRadius ?? null,
        },
        provenance: n.physical ? 'PROVEN_RUN' : 'UNKNOWN',
      };
    }
    n.engineerGeometry = {
      ...(n.engineerGeometry || {}),
      ...override,
      applied_at: new Date().toISOString(),
    };
    n.override_provenance = {
      authority: 'ENGINEER_ASSIGNED',
      source_geometry_mutated: false,
      fields: Object.keys(override || {}),
    };
    n.geometry_provenance = 'ENGINEER_ASSIGNED';
    if (!n.provenance) n.provenance = {};
    n.provenance.geometry_authority = 'ENGINEER_ASSIGNED';
    // Effective canvas fields for display — sourceX/Y untouched
    if (override.entry_endpoint || override.entryCanvas) {
      n.entryCanvas = { ...(override.entry_endpoint || override.entryCanvas) };
    }
    if (override.exit_endpoint || override.exitCanvas) {
      n.exitCanvas = { ...(override.exit_endpoint || override.exitCanvas) };
    }
    if (override.angle != null) n.rotation = Number(override.angle);
    if (override.x != null) n.x = Number(override.x);
    if (override.y != null) n.y = Number(override.y);
    return n;
  }

  /** Guard: never let deterministic/topology fallback overwrite PROVEN geometry. */
  function mayApplyFallbackLayout(n) {
    const p = String(n?.geometry_provenance || n?.provenance?.geometry_authority || '').toUpperCase();
    if (p === 'PROVEN_RUN' || p === 'ENGINEER_ASSIGNED' || p === 'IMPORTED') return false;
    if (n?.physical && (n.sourceX != null && n.sourceY != null)) return false;
    return true;
  }

  function offsetPathD(pathCanvas, off) {
    if (!pathCanvas || !pathCanvas.length) return '';
    const shifted = pathCanvas.map((cmd) => {
      const c = { ...cmd };
      if (c.x != null) c.x = Number(c.x) + (off.dx || 0);
      if (c.y != null) c.y = Number(c.y) + (off.dy || 0);
      if (c.center) {
        c.center = {
          x: Number(c.center.x) + (off.dx || 0),
          y: Number(c.center.y) + (off.dy || 0),
        };
      }
      return c;
    });
    return schematicPathD(shifted);
  }

  function isLiteRenderMode() {
    const m = String(tb.renderMode || 'lite').toLowerCase();
    return m === 'lite' || m === '';
  }

  /** Lite arrowhead linear size vs historical markerWidth/Height=7 (~2/3 smaller). */
  const LITE_ARROW_SCALE = 0.375;
  const LITE_ARROW_MARKER_SIZE = 7 * LITE_ARROW_SCALE;

  function getSchematicStyle() {
    const s = String(tb.schematicStyle || '').toLowerCase();
    if (s === 'readable' || s === 'packed') return s;
    if (tb.readableSchematic) return 'readable';
    return 'raw';
  }

  function isReadableSchematic() {
    return getSchematicStyle() === 'readable' && isLiteRenderMode();
  }

  function isPackedSchematic() {
    return getSchematicStyle() === 'packed' && isLiteRenderMode();
  }

  /**
   * Deterministic VFD-driven evidence for cyan accent.
   * Uses drive/motor semantics from physical layout (driveType / motorsMeta / vfdTag
   * / VFD### motor tags). Does NOT fabricate from conveyor name containing "VFD".
   */
  function nodeHasVfdDriveEvidence(n) {
    if (!n || typeof n !== 'object') return false;
    if (String(n.vfdTag || '').trim()) return true;
    const devices = Array.isArray(n.devices) ? n.devices : [];
    for (let i = 0; i < devices.length; i++) {
      const d = devices[i] || {};
      const kind = String(d.kind || '').toLowerCase();
      if (kind && kind !== 'motor' && kind !== 'vfd') continue;
      const dt = String(d.driveType || d.drive_type || '').toUpperCase();
      if (dt.includes('VFD')) return true;
      const tag = String(d.tag || d.name || d.motor || '').trim();
      if (/^VFD\d/i.test(tag)) return true;
    }
    const meta = Array.isArray(n.motorsMeta) ? n.motorsMeta : [];
    for (let i = 0; i < meta.length; i++) {
      const m = meta[i] || {};
      const dt = String(m.driveType || m.drive_type || '').toUpperCase();
      if (dt.includes('VFD')) return true;
      const tag = String(m.motor || m.tag || m.name || '').trim();
      if (/^VFD\d/i.test(tag)) return true;
    }
    return false;
  }

  function syncTransportLegendVisibility() {
    const leg = $('tb-lite-legend');
    if (!leg) return;
    // Persistent for Raw / Readable / Packed (all Lite schematic styles).
    const show = isLiteRenderMode();
    leg.classList.toggle('tb-legend-visible', show);
    leg.setAttribute('aria-hidden', show ? 'false' : 'true');
  }

  function syncRenderModeButtons() {
    const liteBtn = $('tb-mode-lite');
    const detBtn = $('tb-mode-detailed');
    liteBtn?.classList.toggle('active', isLiteRenderMode());
    detBtn?.classList.toggle('active', !isLiteRenderMode());
    const style = getSchematicStyle();
    $('tb-canvas')?.classList.toggle('tb-canvas-lite', isLiteRenderMode());
    $('tb-canvas')?.classList.toggle('tb-readable-schematic', style === 'readable');
    $('tb-canvas')?.classList.toggle('tb-packed-schematic', style === 'packed');
    const rawBtn = $('tb-style-raw');
    const readBtn = $('tb-style-readable');
    const packBtn = $('tb-style-packed');
    rawBtn?.classList.toggle('active', style === 'raw');
    readBtn?.classList.toggle('active', style === 'readable');
    packBtn?.classList.toggle('active', style === 'packed');
    rawBtn?.setAttribute('aria-pressed', style === 'raw' ? 'true' : 'false');
    readBtn?.setAttribute('aria-pressed', style === 'readable' ? 'true' : 'false');
    packBtn?.setAttribute('aria-pressed', style === 'packed' ? 'true' : 'false');
    syncTransportLegendVisibility();
  }

  function schematicStyleStatus(style) {
    if (style === 'readable') return 'Lite · Readable Schematic (display-only spread)';
    if (style === 'packed') return 'Lite · Packed Components (display-only tile)';
    return 'Lite Schematic · Raw Geometry';
  }

  function setRenderMode(mode) {
    const next = String(mode || 'lite').toLowerCase();
    tb.renderMode = (next === 'detailed' || next === 'diagnostic') ? next : 'lite';
    try {
      localStorage.setItem('siteforge.transportRenderMode', tb.renderMode);
    } catch (_) { /* ignore */ }
    syncRenderModeButtons();
    // Presentation-only — rebuild scene visuals, not Autogen model
    renderScene();
    status(isLiteRenderMode()
      ? schematicStyleStatus(getSchematicStyle())
      : 'Detailed geometry (Advanced presentation)');
  }

  function setSchematicStyle(style) {
    const next = String(style || 'raw').toLowerCase();
    tb.schematicStyle = (next === 'readable' || next === 'packed') ? next : 'raw';
    tb.readableSchematic = tb.schematicStyle === 'readable';
    try {
      localStorage.setItem('siteforge.transportSchematicStyle', tb.schematicStyle);
      localStorage.setItem('siteforge.transportReadableSchematic', tb.readableSchematic ? '1' : '0');
    } catch (_) { /* ignore */ }
    syncRenderModeButtons();
    if (isLiteRenderMode()) renderScene();
    if (tb.schematicStyle === 'readable') {
      status('Readable Schematic — display offsets only (canonical XY preserved)');
    } else if (tb.schematicStyle === 'packed') {
      status('Packed Components — rigid component translates only (canonical XY preserved)');
    } else {
      status('Raw Geometry — canonical RUN/Physical XY');
    }
  }

  function setReadableSchematic(on) {
    setSchematicStyle(on ? 'readable' : 'raw');
  }

  function restoreRenderModePreference() {
    let pref = 'lite';
    let style = 'raw';
    try {
      pref = localStorage.getItem('siteforge.transportRenderMode') || 'lite';
      style = localStorage.getItem('siteforge.transportSchematicStyle') || '';
      if (!style) {
        style = localStorage.getItem('siteforge.transportReadableSchematic') === '1'
          ? 'readable'
          : 'raw';
      }
    } catch (_) { /* ignore */ }
    const next = String(pref || 'lite').toLowerCase();
    tb.renderMode = (next === 'detailed' || next === 'diagnostic') ? next : 'lite';
    const s = String(style || 'raw').toLowerCase();
    tb.schematicStyle = (s === 'readable' || s === 'packed') ? s : 'raw';
    tb.readableSchematic = tb.schematicStyle === 'readable';
    syncRenderModeButtons();
  }

  /** Stable 32-bit hash for display-lane assignment (id → lane side). */
  function liteStableHash(id) {
    let h = 2166136261;
    const s = String(id || '');
    for (let i = 0; i < s.length; i += 1) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  /**
   * Readable Schematic — display-only lateral offsets for near-parallel
   * overlapping Lite belts. Returns Map<id,{dx,dy}>. Never writes node.x/y.
   */
  function computeLiteReadableOffsets(nodes) {
    const MIN_SEP = 14;
    const out = new Map();
    const items = [];
    (nodes || []).forEach((n) => {
      if (!n?.id) return;
      out.set(n.id, { dx: 0, dy: 0 });
      const cache = liteCachedPath(n);
      if (!cache?.pathD) return;
      const a = n.entryCanvas;
      const b = n.exitCanvas;
      let ang = 0;
      if (a && b) {
        ang = Math.atan2(Number(b.y) - Number(a.y), Number(b.x) - Number(a.x));
      } else {
        ang = ((Number(n.sourceAngle != null ? n.sourceAngle : n.rotation) || 0) * Math.PI) / 180;
      }
      const mid = cache.midpoint || { x: Number(n.x) || 0, y: Number(n.y) || 0 };
      items.push({
        id: n.id,
        mid,
        ang,
        nx: -Math.sin(ang),
        ny: Math.cos(ang),
        hash: liteStableHash(n.id),
        merge: !!(n.asMerge || KIND_META[n.kind]?.isMerge),
      });
    });
    if (items.length < 2) return out;

    const parent = items.map((_, i) => i);
    const find = (i) => {
      let r = i;
      while (parent[r] !== r) r = parent[r];
      let c = i;
      while (parent[c] !== r) {
        const n = parent[c];
        parent[c] = r;
        c = n;
      }
      return r;
    };
    const uni = (i, j) => {
      const a = find(i);
      const b = find(j);
      if (a !== b) parent[a] = b;
    };

    for (let i = 0; i < items.length; i += 1) {
      for (let j = i + 1; j < items.length; j += 1) {
        const A = items[i];
        const B = items[j];
        let dAng = Math.abs(A.ang - B.ang) % Math.PI;
        dAng = Math.min(dAng, Math.PI - dAng);
        if (dAng > 0.40) continue; // ~23° — not near-parallel
        const dist = Math.hypot(A.mid.x - B.mid.x, A.mid.y - B.mid.y);
        if (dist > Math.max(MIN_SEP * 2.8, 36)) continue;
        uni(i, j);
      }
    }

    const groups = new Map();
    items.forEach((it, i) => {
      const r = find(i);
      if (!groups.has(r)) groups.set(r, []);
      groups.get(r).push(it);
    });

    groups.forEach((members) => {
      if (members.length < 2) return;
      members.sort((a, b) => (a.hash - b.hash) || String(a.id).localeCompare(String(b.id)));
      // Average normal of the cluster
      let nx = 0;
      let ny = 0;
      members.forEach((m) => { nx += m.nx; ny += m.ny; });
      const nlen = Math.hypot(nx, ny) || 1;
      nx /= nlen;
      ny /= nlen;
      const mid = (members.length - 1) / 2;
      members.forEach((m, idx) => {
        const lane = idx - mid;
        if (lane === 0) return;
        out.set(m.id, { dx: nx * lane * MIN_SEP, dy: ny * lane * MIN_SEP });
      });
    });
    return out;
  }

  /** Lite extent points for packing bbox — read-only, never writes node.x/y. */
  function liteNodeExtentPoints(n) {
    const pts = [];
    if (n?.entryCanvas) pts.push({ x: Number(n.entryCanvas.x), y: Number(n.entryCanvas.y) });
    if (n?.exitCanvas) pts.push({ x: Number(n.exitCanvas.x), y: Number(n.exitCanvas.y) });
    const cache = n?.id ? liteCachedPath(n) : null;
    if (cache?.midpoint) pts.push({ x: Number(cache.midpoint.x), y: Number(cache.midpoint.y) });
    if (!pts.length) pts.push({ x: Number(n?.x) || 0, y: Number(n?.y) || 0 });
    return pts;
  }

  /**
   * Disconnected Transportation graph components (wires + downstream tags).
   * Returns full member lists for display packing — does not mutate topologyAccounting.
   */
  function listLiteTransportComponents(nodes, wires) {
    const list = (nodes || []).filter((n) => n?.id);
    const byId = new Map(list.map((n) => [n.id, n]));
    const byTag = new Map();
    list.forEach((n) => {
      const t = String(n.conveyorTag || '').trim().toUpperCase();
      if (t) byTag.set(t, n);
    });
    const adj = new Map(list.map((n) => [n.id, new Set()]));
    const link = (a, b) => {
      if (!a || !b || a === b || !adj.has(a) || !adj.has(b)) return;
      adj.get(a).add(b);
      adj.get(b).add(a);
    };
    (wires || []).forEach((w) => link(w.from, w.to));
    list.forEach((n) => {
      const ds = String(n.downstream || '').trim().toUpperCase();
      if (!ds) return;
      const dst = byTag.get(ds);
      if (dst) link(n.id, dst.id);
    });
    const seen = new Set();
    const components = [];
    list.forEach((n) => {
      if (seen.has(n.id)) return;
      const stack = [n.id];
      const members = [];
      seen.add(n.id);
      while (stack.length) {
        const id = stack.pop();
        const node = byId.get(id);
        if (node) members.push(node);
        (adj.get(id) || []).forEach((nb) => {
          if (!seen.has(nb)) {
            seen.add(nb);
            stack.push(nb);
          }
        });
      }
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      members.forEach((m) => {
        liteNodeExtentPoints(m).forEach((p) => {
          minX = Math.min(minX, p.x);
          minY = Math.min(minY, p.y);
          maxX = Math.max(maxX, p.x);
          maxY = Math.max(maxY, p.y);
        });
      });
      if (!Number.isFinite(minX)) {
        minX = 0; minY = 0; maxX = 0; maxY = 0;
      }
      const pad = 8;
      components.push({
        nodes: members,
        size: members.length,
        minX: minX - pad,
        minY: minY - pad,
        maxX: maxX + pad,
        maxY: maxY + pad,
        w: (maxX - minX) + pad * 2,
        h: (maxY - minY) + pad * 2,
        key: members.map((m) => m.id).sort().join('|'),
      });
    });
    components.sort((a, b) => (
      (b.size - a.size)
      || String(a.key).localeCompare(String(b.key))
    ));
    return components;
  }

  /**
   * Packed Components — display-only rigid translates of disconnected graph
   * components into a compact tile. Never writes node.x/y / provenance / Autogen.
   */
  function computeLitePackedOffsets(nodes, wires) {
    const out = new Map();
    (nodes || []).forEach((n) => {
      if (n?.id) out.set(n.id, { dx: 0, dy: 0 });
    });
    const comps = listLiteTransportComponents(nodes, wires);
    if (comps.length <= 1) return out;

    const GAP = 56;
    let areaSum = 0;
    comps.forEach((c) => { areaSum += Math.max(1, c.w) * Math.max(1, c.h); });
    const targetW = Math.max(comps[0].w, Math.sqrt(areaSum) * 1.35);

    let cursorX = 0;
    let cursorY = 0;
    let rowH = 0;
    comps.forEach((c) => {
      if (cursorX > 0 && cursorX + c.w > targetW) {
        cursorX = 0;
        cursorY += rowH + GAP;
        rowH = 0;
      }
      const dx = cursorX - c.minX;
      const dy = cursorY - c.minY;
      c.nodes.forEach((n) => {
        if (n?.id) out.set(n.id, { dx, dy });
      });
      cursorX += c.w + GAP;
      rowH = Math.max(rowH, c.h);
    });
    return out;
  }

  /** Light label de-confliction — nudge or hide overlapping P-tags (display only). */
  function liteLabelCollisionPlan(placements) {
    // placements: [{id, x, y, merge, sel, keep}]
    const plan = new Map();
    const kept = [];
    const sorted = [...(placements || [])].sort((a, b) => {
      const wa = (a.sel ? 4 : 0) + (a.merge ? 2 : 0);
      const wb = (b.sel ? 4 : 0) + (b.merge ? 2 : 0);
      return wb - wa;
    });
    sorted.forEach((p) => {
      let x = p.x;
      let y = p.y;
      let hide = false;
      for (const k of kept) {
        const d = Math.hypot(x - k.x, y - k.y);
        if (d >= 16) continue;
        if (p.sel || p.merge) {
          // Nudge lower-priority kept label later; keep this one
          y -= 10;
        } else if (k.sel || k.merge) {
          hide = true;
          break;
        } else {
          // Stable: lower hash hides
          if (liteStableHash(p.id) > liteStableHash(k.id)) {
            hide = true;
            break;
          }
          y -= 9;
        }
      }
      plan.set(p.id, { x, y, hide });
      if (!hide) kept.push({ id: p.id, x, y, merge: p.merge, sel: p.sel });
    });
    return plan;
  }

  function setShowRelationships(on) {
    const v = !!on;
    tb.showRelationships = v;
    if (!tb.layers) tb.layers = {};
    tb.layers.relationships = v;
    const el = $('tb-show-relationships');
    if (el) el.checked = v;
    // Presentation-only: wire layer toggle must not rebuild topology/validation
    if (v) drawWiresNow();
    else {
      const svg = $('tb-wires');
      if (svg) svg.innerHTML = '';
      $('tb-canvas')?.classList.add('tb-hide-relationships');
    }
    try { save(); } catch (_) { /* ignore */ }
    status(v ? 'Relationships: ON (visualization)' : 'Relationships: OFF (clean layout)');
  }

  /** Project-scoped Transport model cache key. Erased Means Erased across projects. */
  function transportModelCacheKey() {
    const id = currentProjectIdentity() || {};
    const machine = String(id.machine || window.state?.machine || '').trim();
    const runFp = String(id.run_fingerprint || id.runFingerprint || '').trim();
    const projectKey = identityKey(id) || [
      id.project_key || id.projectKey || '',
      machine,
      id.archive || '',
    ].join('|');
    const ver = String(tb.transportModelVersion || '1');
    return {
      project_key: projectKey,
      machine,
      run_fingerprint: runFp,
      transport_model_version: ver,
      key: `${projectKey}::${machine}::${runFp}::${ver}`,
    };
  }

  function getCachedTransportModel() {
    const meta = transportModelCacheKey();
    if (!meta.key || meta.key.startsWith('::::')) return null;
    if (tb._transportModelCacheKey !== meta.key) return null;
    return tb._transportModelCache || null;
  }

  function setCachedTransportModel(model) {
    const meta = transportModelCacheKey();
    // Never cache under an empty / foreign identity
    if (!meta.key || (!meta.machine && !meta.project_key)) {
      clearTransportModelCache('no_identity');
      return null;
    }
    tb._transportModelCacheKey = meta.key;
    tb._transportModelCache = model || null;
    tb._transportModelCacheMeta = meta;
    return meta;
  }

  function clearTransportModelCache(reason) {
    tb._transportModelCacheKey = null;
    tb._transportModelCache = null;
    tb._transportModelCacheMeta = null;
    tb._liteGeomCache = Object.create(null);
    return reason || 'cleared';
  }

  function assertTransportModelCacheIdentity() {
    const live = transportModelCacheKey();
    if (!tb._transportModelCacheKey) return true;
    if (tb._transportModelCacheKey !== live.key) {
      clearTransportModelCache('identity_mismatch');
      status('Discarded foreign Transport model cache (Erased Means Erased)');
      return false;
    }
    return true;
  }

  function buildPerfReport() {
    const snap = perfSnapshot();
    const byCause = {};
    snap.forEach((row) => {
      const c = row.cause || 'unknown';
      if (!byCause[c]) byCause[c] = { count: 0, total_ms: 0, max_ms: 0, samples: [] };
      byCause[c].count += 1;
      byCause[c].total_ms += Number(row.duration_ms) || 0;
      byCause[c].max_ms = Math.max(byCause[c].max_ms, Number(row.duration_ms) || 0);
      if (byCause[c].samples.length < 8) byCause[c].samples.push(row.duration_ms);
    });
    Object.keys(byCause).forEach((k) => {
      const b = byCause[k];
      b.avg_ms = b.count ? Math.round((b.total_ms / b.count) * 100) / 100 : 0;
    });
    const area = activeArea();
    return {
      kind: 'transport_gui_perf',
      version: 1,
      generated_at: new Date().toISOString(),
      renderMode: tb.renderMode || 'lite',
      showRelationships: !!(tb.showRelationships || tb.layers?.relationships),
      node_count: (area?.nodes || []).length,
      area: area?.name || area?.id || '',
      project: transportModelCacheKey(),
      targets_ms: {
        hover: 5,
        select: 20,
        drag_frame: 30,
        drag_commit: 100,
        area_switch: 150,
        open_topology: 250,
        initial_ui: 2000,
      },
      by_cause: byCause,
      recent: snap,
      note: 'Instrument from Electron browser via perfRecord — proxy Python benches are not acceptance.',
    };
  }

  async function writeTransportGuiPerf(report) {
    const payload = report || buildPerfReport();
    const rel = 'exports/qualification/perf/transport_gui_perf.json';
    if (window.fortnaAPI && typeof window.fortnaAPI.writeExportJson === 'function') {
      const r = await window.fortnaAPI.writeExportJson({ path: rel, data: payload });
      return { ok: !!r?.success, path: rel, result: r };
    }
    // Fallback: expose for harness / copy
    try {
      window.__tbLastPerfReport = payload;
    } catch (_) { /* ignore */ }
    return { ok: false, path: rel, fallback: true, data: payload };
  }

  function liteStraightPath(n) {
    const a = n?.entryCanvas;
    const b = n?.exitCanvas;
    if (!a || !b) return '';
    return `M ${Number(a.x)} ${Number(a.y)} L ${Number(b.x)} ${Number(b.y)}`;
  }

  function liteCurvePath(n) {
    const a = n?.entryCanvas;
    const b = n?.exitCanvas;
    if (!a || !b) return '';
    // Prefer proven centerline when present (presentation read-only)
    if (pathIsPhysicalCenterlineArc(n.pathCanvas)) {
      return schematicPathD(n.pathCanvas) || '';
    }
    const ax = Number(a.x);
    const ay = Number(a.y);
    const bx = Number(b.x);
    const by = Number(b.y);
    const mx = (ax + bx) / 2;
    const my = (ay + by) / 2;
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const bend = Math.min(40, len * 0.30);
    const sign = Number(n.sweepDeg ?? n.sweep_deg ?? 90) >= 0 ? 1 : -1;
    const cx = mx + (-dy / len) * bend * sign;
    const cy = my + (dx / len) * bend * sign;
    return `M ${ax} ${ay} Q ${cx} ${cy} ${bx} ${by}`;
  }

  function liteNodeRevision(n) {
    return [
      n.id,
      n.entryCanvas?.x, n.entryCanvas?.y,
      n.exitCanvas?.x, n.exitCanvas?.y,
      n.sweepDeg ?? n.sweep_deg,
      n.conveyorTag || n.label,
      (n.pathCanvas || []).length,
    ].join('|');
  }

  function liteCachedPath(n) {
    const rev = liteNodeRevision(n);
    const hit = tb._liteGeomCache?.[n.id];
    if (hit && hit.geometryRevision === rev && hit.pathD) return hit;
    const isCurve = isCurveNode(n);
    const pathD = isCurve ? liteCurvePath(n) : liteStraightPath(n);
    const a = n.entryCanvas;
    const b = n.exitCanvas;
    const midpoint = (a && b)
      ? { x: (Number(a.x) + Number(b.x)) / 2, y: (Number(a.y) + Number(b.y)) / 2 }
      : { x: Number(n.x) || 0, y: Number(n.y) || 0 };
    const row = { geometryRevision: rev, pathD, midpoint };
    if (!tb._liteGeomCache) tb._liteGeomCache = Object.create(null);
    tb._liteGeomCache[n.id] = row;
    return row;
  }

  function invalidateLiteGeom(id) {
    if (!id || !tb._liteGeomCache) return;
    delete tb._liteGeomCache[id];
  }

  function nodeIdFromLiteEvent(ev) {
    const el = ev?.target?.closest?.(
      '.tb-lite-hit, .tb-lite-belt, .tb-lite-label, .tb-lite-node',
    );
    return el?.getAttribute?.('data-id') || el?.dataset?.id || null;
  }

  function toggleLiteSelectedClass(id, on) {
    if (!id) return;
    const svg = $('tb-schematic');
    if (!svg) return;
    const esc = (typeof CSS !== 'undefined' && CSS.escape)
      ? CSS.escape(id)
      : String(id).replace(/"/g, '\\"');
    svg.querySelectorAll(`[data-id="${esc}"]`).forEach((el) => {
      el.classList.toggle('selected', !!on);
    });
  }

  function updateLiteHover(id) {
    const svg = $('tb-schematic');
    if (!svg) return;
    svg.querySelectorAll('.tb-hover').forEach((el) => el.classList.remove('tb-hover'));
    if (!id) return;
    const esc = (typeof CSS !== 'undefined' && CSS.escape)
      ? CSS.escape(id)
      : String(id).replace(/"/g, '\\"');
    svg.querySelectorAll(`[data-id="${esc}"]`).forEach((el) => el.classList.add('tb-hover'));
  }

  function selectLiteNode(id, { additive } = {}) {
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const prev = tb.selectedId;
    if (!id) {
      toggleLiteSelectedClass(prev, false);
      tb.selectedId = null;
      tb.selectedIds = [];
      tb.selectedDeviceId = null;
      renderInspector();
      perfRecord('transport.selectLite', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {});
      return;
    }
    if (additive) {
      const set = new Set(tb.selectedIds || []);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      tb.selectedIds = [...set];
      tb.selectedId = tb.selectedIds.includes(id) ? id : (tb.selectedIds[0] || null);
    } else {
      tb.selectedId = id;
      tb.selectedIds = [id];
    }
    tb.selectedDeviceId = null;
    if (prev && prev !== tb.selectedId) toggleLiteSelectedClass(prev, false);
    (tb.selectedIds || []).forEach((sid) => toggleLiteSelectedClass(sid, true));
    renderInspector();
    perfRecord('transport.selectLite', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, { id });
  }

  function drawLiteSchematicNow(area) {
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const svg = $('tb-schematic');
    if (!svg) return;
    const nodes = (area?.nodes || []).filter((n) => {
      if (!isSchematicNode(n)) return false;
      if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') return true;
      if (n.displayContext) return false;
      if (n.plcOwned === false) return false;
      if (n.scopeClass === 'OUT_OF_SCOPE' || n.scopeClass === 'UNRESOLVED') return false;
      return true;
    });
    const lod = detailLevel();
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    // Gate F: always show ordinary P-tag identity labels at every zoom.
    // Far zoom shrinks font; never gate identity on 0.35 / overview LOD.
    const showAllLabels = true;
    const labelPx = z < 0.25 ? 8 : (z < 0.55 ? 9 : 11);
    const style = getSchematicStyle();
    const readable = style === 'readable';
    const packed = style === 'packed';
    // Display-only offsets — never written into node.x/y or provenance.
    let dispOff = null;
    if (readable) dispOff = computeLiteReadableOffsets(nodes);
    else if (packed) dispOff = computeLitePackedOffsets(nodes, area?.wires || []);
    const labelCandidates = [];
    nodes.forEach((n) => {
      const cache = liteCachedPath(n);
      if (!cache?.pathD) return;
      const off = dispOff?.get(n.id) || { dx: 0, dy: 0 };
      const mid = cache.midpoint || { x: 0, y: 0 };
      const sel = n.id === tb.selectedId || (tb.selectedIds || []).includes(n.id);
      const merge = !!(n.asMerge || KIND_META[n.kind]?.isMerge);
      // Identity labels always on — merge/sel flags still drive collision priority.
      labelCandidates.push({
        id: n.id,
        x: mid.x + (Number(off.dx) || 0),
        y: mid.y - 6 + (Number(off.dy) || 0),
        merge,
        sel,
      });
    });
    // Readable: light label-vs-label cleanup (no expensive physics).
    const labelPlan = readable
      ? liteLabelCollisionPlan(labelCandidates)
      : null;
    const arrowSz = LITE_ARROW_MARKER_SIZE;
    let html = `<defs><marker id="tbArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="${arrowSz}" markerHeight="${arrowSz}" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker></defs>`;
    nodes.forEach((n) => {
      const cache = liteCachedPath(n);
      const d = cache.pathD;
      if (!d) return;
      const tag = ((n.conveyorTag || n.label || '').trim()) || 'P???';
      const kindTitle = KIND_META[n.kind]?.title || n.kind || 'conveyor';
      const sel = n.id === tb.selectedId || (tb.selectedIds || []).includes(n.id);
      const merge = !!(n.asMerge || KIND_META[n.kind]?.isMerge);
      const review = Array.isArray(n.ambiguousInbound) && n.ambiguousInbound.length > 0;
      const vfd = nodeHasVfdDriveEvidence(n);
      let cls = 'tb-lite-belt';
      if (sel) cls += ' selected';
      if (merge) cls += ' tb-merge';
      if (review && !sel) cls += ' tb-review';
      if (vfd) cls += ' tb-vfd';
      const mid = cache.midpoint || { x: 0, y: 0 };
      const off = dispOff?.get(n.id) || { dx: 0, dy: 0 };
      const ox = Number(off.dx) || 0;
      const oy = Number(off.dy) || 0;
      // Group translate = display-only spread/pack; path D stays canonical.
      const xf = (ox || oy) ? ` transform="translate(${ox} ${oy})"` : '';
      html += `<g class="tb-lite-node" data-id="${escapeHtml(n.id)}"${xf}>`;
      html += `<path class="tb-lite-hit" data-id="${escapeHtml(n.id)}" d="${d}" />`;
      // Merge/divert ≥2× ordinary stroke (4 → 10). Style modes keep hierarchy.
      const stroke = merge ? (sel ? 11 : 10) : (sel ? 5 : 4);
      const tipParts = [tag, kindTitle];
      if (merge) tipParts.push('merge');
      if (vfd) tipParts.push('VFD');
      if (review) tipParts.push('review');
      if (n.downstream) tipParts.push(`→ ${n.downstream}`);
      html += `<path class="${cls}" data-id="${escapeHtml(n.id)}" d="${d}" `
        + `stroke-width="${stroke}" marker-end="url(#tbArrow)">`
        + `<title>${escapeHtml(tipParts.join(' · '))}</title></path>`;
      // Cyan accent stripe — keeps gray/orange/purple/amber base meanings intact.
      if (vfd) {
        const accentSw = merge ? 3 : 1.75;
        html += `<path class="tb-lite-vfd-accent" data-id="${escapeHtml(n.id)}" d="${d}" `
          + `stroke-width="${accentSw}" />`;
      }
      // Always emit P-tag identity (Gate F — not gated on zoom/LOD).
      if (showAllLabels) {
        const plan = labelPlan?.get(n.id);
        if (!(plan && plan.hide)) {
          // Label lives inside offset group — use canonical mid + collision nudge.
          const naturalSx = mid.x + ox;
          const naturalSy = mid.y - 6 + oy;
          const ndx = plan ? ((Number(plan.x) || naturalSx) - naturalSx) : 0;
          const ndy = plan ? ((Number(plan.y) || naturalSy) - naturalSy) : 0;
          const lx = mid.x + ndx;
          const ly = mid.y - 6 + ndy;
          const inv = Math.min(2.5, Math.max(1, 0.55 / z));
          html += `<text class="tb-lite-label${sel ? ' selected' : ''}${lod === 'overview' || z < 0.35 ? ' tb-lite-label-far' : ''}" `
            + `data-id="${escapeHtml(n.id)}" x="${lx}" y="${ly}" `
            + `font-size="${labelPx}" `
            + `transform="translate(${lx} ${ly}) scale(${inv}) translate(${-lx} ${-ly})">`
            + `${escapeHtml(tag)}</text>`;
        }
      }
      html += '</g>';
    });
    svg.innerHTML = html;
    // Event delegation — no per-node listeners, no mathematical pick scan
    svg.onpointermove = (ev) => {
      const id = nodeIdFromLiteEvent(ev);
      updateLiteHover(id);
    };
    svg.onpointerleave = () => updateLiteHover(null);
    svg.onpointerdown = (ev) => {
      if (ev.button !== 0) return;
      const id = nodeIdFromLiteEvent(ev);
      if (!id) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (tb.connectMode) {
        const n = (area?.nodes || []).find((x) => x.id === id);
        if (n && isConv(n.kind)) handleConnectModeClick(n);
        return;
      }
      selectLiteNode(id, { additive: !!(ev.ctrlKey || ev.metaKey) });
      const n = (area?.nodes || []).find((x) => x.id === id);
      if (n) {
        const pt = canvasPointFromEvent(ev);
        // Lite drag: transform presentation only during pointermove; commit on mouseup.
        tb.moving = {
          id: n.id,
          ox: pt.x - (Number(n.x) || 0),
          oy: pt.y - (Number(n.y) || 0),
          startX: Number(n.x) || 0,
          startY: Number(n.y) || 0,
          origins: [captureNodeGeom(n)],
          lite: true,
          presentationOnly: true,
        };
      }
    };
    const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    perfRecord('transport.drawLiteSchematic', t1 - t0, {
      node_count: nodes.length,
      area: area?.name || area?.id || '',
      mode: 'lite',
      schematicStyle: style,
      readable: !!readable,
      packed: !!packed,
    });
  }

  function drawSchematic(area) {
    // Public entry — coalesce high-frequency redraws (drag/pan) into one frame.
    scheduleDrawSchematic(area);
  }

  function drawSchematicNow(area) {
    if (isLiteRenderMode()) {
      drawLiteSchematicNow(area);
      return;
    }
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const svg = $('tb-schematic');
    if (!svg) return;
    // Clean schematic is always drawn in normal mode. Advanced "Physical debug"
    // only adds extra cues — it does not replace the schematic.
    const nodes = (area?.nodes || []).filter((n) => {
      if (!isSchematicNode(n)) return false;
      // Controller-scoped canvas: LOCAL + EXTERNAL_REFERENCE only
      if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') return true;
      if (n.displayContext) return false;
      if (n.plcOwned === false) return false;
      if (n.scopeClass === 'OUT_OF_SCOPE' || n.scopeClass === 'UNRESOLVED') return false;
      return true;
    });
    const lod = detailLevel();
    const offsets = computePresentationOffsets(nodes, area);
    const jointOverlay = projectSharedTopologyJoints(nodes);
    const debug = tb.viewMode === 'geom-debug' || !!tb.layers?.physical;
    let html = '';
    const labelCandidates = [];
    nodes.forEach((n) => {
      const off = offsets[n.id] || { dx: 0, dy: 0 };
      const isExt = !!(n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE');
      // Gate 4: inset tips that RUN-XY-abut unconnected neighbors (no fake join paint)
      const insets = isCurveNode(n) ? { entryInset: 0, exitInset: 0 }
        : falseAbutmentInsets(n, nodes, area, offsets);
      // Physical centerline arc; shared topology joints projected for display only
      const displayPath = displayPathCanvasForNode(n, { anchors: jointOverlay[n.id] });
      const physicalArc = isCurveNode(n) && pathIsPhysicalCenterlineArc(displayPath);
      let d = '';
      if (!isCurveNode(n) && n.entryCanvas && n.exitCanvas) {
        const rawA = applyPresOffset(n.entryCanvas, off);
        const rawB = applyPresOffset(n.exitCanvas, off);
        const inset = insetDisplayEndpoints(rawA, rawB, insets);
        d = `M ${inset.entry.x} ${inset.entry.y} L ${inset.exit.x} ${inset.exit.y}`;
      } else {
        d = offsetPathD(displayPath, off);
      }
      // Curves: never paint RUN arcSamples (tangent hooks). Non-curves may use samples.
      if (!d && !isCurveNode(n) && n.arcSamplesCanvas?.length) {
        d = n.arcSamplesCanvas.map((p, i) => {
          const q = applyPresOffset(p, off);
          return `${i ? 'L' : 'M'} ${q.x} ${q.y}`;
        }).join(' ');
      }
      if (!d) return;
      const rk = String(n.renderKind || n.equipmentType || 'unknown').toLowerCase();
      const sw = physicalArc
        ? schematicStrokeWidth(n)
        : (isCurveNode(n) ? curveSymbolStrokeWidth(n) : schematicStrokeWidth(n));
      const sel = n.id === tb.selectedId || (tb.selectedIds || []).includes(n.id);
      const amb = (n.ambiguousInbound || []).length > 0;
      const cp = normalizeControlPanel(n.controlPanel);
      const cpMatch = nodeMatchesCpFilter(n);
      let cls = `tb-schematic-body tb-rk-${rk}`;
      if (isCurveNode(n)) cls += ' tb-rk-curve';
      if (physicalArc) cls += ' tb-curve-physical';
      if (sel) cls += ' selected';
      if (amb) cls += ' tb-ambiguous';
      if (isExt) cls += ' tb-display-context tb-external-ref';
      if (cp === 'CP1' || cp === 'CP2' || cp === 'CP3') cls += ` tb-cp-${cp}`;
      else if (cp === 'Other') cls += ' tb-cp-Other';
      if (cpFilterActive()) cls += cpMatch ? ' tb-cp-match' : ' tb-cp-dim';
      const tag = isExt
        ? (`→ External ${(n.conveyorTag || n.label || '').trim()}`.trim() || '→ External')
        : ((n.conveyorTag || n.label || '').trim() || 'P???');
      const mid0 = n.entryCanvas && n.exitCanvas
        ? { x: (n.entryCanvas.x + n.exitCanvas.x) / 2, y: (n.entryCanvas.y + n.exitCanvas.y) / 2 }
        : { x: Number(n.x) || 0, y: Number(n.y) || 0 };
      const mid = applyPresOffset(mid0, off);
      const tip = isCurveNode(n)
        ? (physicalArc
          ? `${tag} · CURVE centerline arc (immutable anchors)`
          : `${tag} · ${CURVE_SYMBOL.TOOLTIP_SUFFIX}`)
        : (cp ? `${tag} · ${cp}` : tag);
      // Physical curve: closed annular belt (flat faces), not a round-capped stroke.
      if (physicalArc) {
        const beltW = Math.max(sw, curveSymbolBodyWidth(n) || sw);
        const beltD = annularBeltPathDFromCenterline(displayPath, beltW);
        if (beltD) {
          html += `<path class="tb-belt-annulus ${sel ? 'selected' : ''}" data-id="${escapeHtml(n.id)}" d="${beltD}"><title>${escapeHtml(tip)}</title></path>`;
          html += `<path class="tb-belt-center" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="1.25" />`;
        } else {
          html += `<path class="tb-belt-frame" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="${sw + 5}" />`;
          html += `<path class="${cls}" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="${sw}"><title>${escapeHtml(tip)}</title></path>`;
          html += `<path class="tb-belt-center" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="1.25" />`;
        }
      } else {
        html += `<path class="${cls}" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="${sw}"><title>${escapeHtml(tip)}</title></path>`;
      }
      // Invisible hit stroke — visual belt stays `sw`; pick uses SCHEMATIC_HIT_WIDTH (~50).
      const hitSw = SCHEMATIC_HIT_WIDTH;
      html += `<path class="tb-schematic-hit" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="${hitSw}" />`;
      // Orange warn dot: missing Area/ES (informational only; not a selection handle)
      const needsCfg = !!(n.areaRequired || n.esZoneRequired);
      if (needsCfg && (sel || tb.viewMode === 'geom-debug')) {
        html += `<circle class="tb-schematic-warn" data-id="${escapeHtml(n.id)}" cx="${mid.x}" cy="${mid.y - sw / 2 - 4}" r="2.5"><title>Missing Area/ES — edit in inspector (not a click handle)</title></circle>`;
      }
      // Small CP badge (does not alter connectivity geometry)
      if (cp && (sel || cpFilterActive() || lod === 'close' || lod === 'mid')) {
        const badge = cp === 'Other' ? 'CP?' : cp;
        html += `<text class="tb-cp-badge tb-cp-badge-${escapeHtml(cp)}" data-id="${escapeHtml(n.id)}" x="${mid.x}" y="${mid.y + sw / 2 + 10}" text-anchor="middle">${escapeHtml(badge)}</text>`;
      }
      // Flow tick at exit (overview+) so direction is readable without device clutter
      if (n.exitCanvas && n.entryCanvas) {
        const ex = applyPresOffset(n.exitCanvas, off);
        const en = applyPresOffset(n.entryCanvas, off);
        const ang = Math.atan2(ex.y - en.y, ex.x - en.x);
        const fx = ex.x - Math.cos(ang) * 4;
        const fy = ex.y - Math.sin(ang) * 4;
        const ax = fx - Math.cos(ang - 0.45) * 7;
        const ay = fy - Math.sin(ang - 0.45) * 7;
        const bx = fx - Math.cos(ang + 0.45) * 7;
        const by = fy - Math.sin(ang + 0.45) * 7;
        html += `<path class="tb-schematic-flow" data-id="${escapeHtml(n.id)}" d="M ${ax} ${ay} L ${fx} ${fy} L ${bx} ${by}" />`;
      }
      // Conveyor-first: P-tag only unless Motors/PE/Device Labels layers are on.
      // CURVE type with UNKNOWN orientation always shows a CURVE secondary badge.
      const showConvTags = tb.layers?.conveyorTags !== false;
      if (showConvTags && (lod === 'overview' || lod === 'mid' || lod === 'close' || sel || isCurveNode(n))) {
        const len = Number(n.length) || (n.entryCanvas && n.exitCanvas
          ? Math.hypot(n.exitCanvas.x - n.entryCanvas.x, n.exitCanvas.y - n.entryCanvas.y)
          : 0);
        let secondary = '';
        if (isCurveNode(n) && !physicalArc && curveOrientationStatus(n) === 'UNKNOWN') {
          secondary = CURVE_SYMBOL.BADGE;
        } else if (tb.layers?.motors || tb.layers?.deviceLabels) {
          if (Array.isArray(n.motorsMeta) && n.motorsMeta[0]) {
            const m = n.motorsMeta[0].motor || n.motorsMeta[0].tag;
            if (m) secondary = String(m);
          } else if (n.vfdTag) {
            secondary = String(n.vfdTag);
          }
        }
        // Rich hover tooltip — not painted permanently
        const tipParts = [tag];
        const m0 = (Array.isArray(n.motorsMeta) && n.motorsMeta[0])
          ? (n.motorsMeta[0].motor || n.motorsMeta[0].tag)
          : (n.devices || []).find((d) => d.kind === 'motor')?.tag;
        if (m0) tipParts.push(`Motor: ${m0}`);
        const pes = (n.devices || []).filter((d) => d.kind === 'photoeye' && (d.tag || '').trim()).map((d) => d.tag);
        if (pes.length) tipParts.push(`PE: ${pes.slice(0, 3).join(', ')}`);
        const ups = getUpstreamTags(area, n.id);
        if (ups.length) tipParts.push(`Upstream: ${ups.join(', ')}`);
        if (n.downstream) tipParts.push(`Downstream: ${n.downstream}`);
        if ((n.ambiguousInbound || []).length) tipParts.push(`Ambiguous mates: ${n.ambiguousInbound.length}`);
        labelCandidates.push({
          id: n.id,
          tag,
          secondary,
          tip: tipParts.join('\n'),
          x: mid.x,
          y: mid.y,
          anchorX: mid.x,
          anchorY: mid.y,
          selected: sel,
          priority: len,
          external: isExt,
        });
      }
    });
    tb._schematicLabelPos = {};
    // Gate 5: paint labels after bodies so z-order keeps identity readable
    placeSchematicLabels(labelCandidates).forEach((lab) => {
      if (lab.hidden) return;
      tb._schematicLabelPos[lab.id] = { x: lab.x, y: lab.y };
      // Leader line only when label was moved off the body midpoint.
      if (lab.offsetIndex > 0 || lab.forced) {
        const ax = lab.anchorX != null ? lab.anchorX : lab.x;
        const ay = lab.anchorY != null ? lab.anchorY : lab.y;
        html += `<line class="tb-schematic-leader" data-id="${escapeHtml(lab.id)}" x1="${ax}" y1="${ay}" x2="${lab.x}" y2="${lab.y}" />`;
      }
      const tipAttr = lab.tip ? `<title>${escapeHtml(lab.tip)}</title>` : '';
      const labCls = lab.external
        ? 'tb-schematic-label tb-schematic-label-hit tb-schematic-label-external'
        : 'tb-schematic-label tb-schematic-label-hit';
      const selCls = lab.selected ? ' tb-label-selected' : '';
      // Identity label is a FIRST-CLASS selection target (universal contract)
      html += `<text class="${labCls}${selCls}" data-id="${escapeHtml(lab.id)}" x="${lab.x}" y="${lab.y}">${tipAttr}${escapeHtml(lab.tag)}</text>`;
      // Invisible hit disc behind the number so short tags remain easy to click
      html += `<circle class="tb-schematic-label-disc" data-id="${escapeHtml(lab.id)}" cx="${lab.x}" cy="${lab.y}" r="16" />`;
      if (lab.secondary) {
        const secCls = lab.secondary === 'CURVE'
          ? 'tb-schematic-label-sec tb-curve-badge'
          : 'tb-schematic-label-sec';
        html += `<text class="${secCls}" data-id="${escapeHtml(lab.id)}" x="${lab.x}" y="${lab.y + 12}">${escapeHtml(lab.secondary)}</text>`;
      }
    });
    // Mate marks (EXIT▶◀ENTRY): only PHYSICAL_GEOMETRY / engineer override — never logical topology
    if (tb.layers?.relationships) {
      (area?.wires || []).forEach((w) => {
        const a = (area.nodes || []).find((n) => n.id === w.from);
        const b = (area.nodes || []).find((n) => n.id === w.to);
        const clsKind = classifyRenderedConnection(w, a, b);
        if (!mayDrawPhysicalJoin(w, clsKind)) return;
        if (!a?.exitCanvas || !b?.entryCanvas) return;
        const oa = offsets[a.id] || { dx: 0, dy: 0 };
        const ob = offsets[b.id] || { dx: 0, dy: 0 };
        const ax = applyPresOffset(a.exitCanvas, oa);
        const bx = applyPresOffset(b.entryCanvas, ob);
        const mx = (ax.x + bx.x) / 2;
        const my = (ax.y + bx.y) / 2;
        html += `<text class="tb-mate-mark" x="${mx}" y="${my}"><title>Physical mate EXIT ▶◀ ENTRY (not a click handle)</title>▶◀</text>`;
      });
    }
    svg.innerHTML = html;
    // Hit paths + identity discs are the interactive targets; body stroke is visual only.
    svg.querySelectorAll('.tb-schematic-hit').forEach((el) => {
      el.style.pointerEvents = 'stroke';
    });
    svg.querySelectorAll('.tb-schematic-label-disc, .tb-schematic-label-hit').forEach((el) => {
      el.style.pointerEvents = 'all';
    });
    svg.querySelectorAll('.tb-schematic-body').forEach((el) => {
      el.style.pointerEvents = 'none';
    });
    const clearHover = () => {
      svg.querySelectorAll('.tb-hover').forEach((el) => el.classList.remove('tb-hover'));
    };
    const setHover = (id) => {
      clearHover();
      if (!id) return;
      const esc = (typeof CSS !== 'undefined' && CSS.escape)
        ? CSS.escape(id)
        : String(id).replace(/"/g, '\\"');
      svg.querySelectorAll(`[data-id="${esc}"]`).forEach((el) => {
        if (
          el.classList.contains('tb-schematic-body')
          || el.classList.contains('tb-schematic-hit')
          || el.classList.contains('tb-schematic-label-hit')
          || el.classList.contains('tb-schematic-label-disc')
        ) {
          el.classList.add('tb-hover');
        }
      });
    };
    const onSchematicPointer = (ev) => {
      if (ev.type === 'mousedown' && ev.button === 1) return;
      const n = pickSchematicNodeAt(ev.clientX, ev.clientY, area);
      if (ev.type === 'mousemove') {
        setHover(n?.id || null);
        return;
      }
      if (!n) return;
      if (ev.type === 'mousedown') {
        ev.preventDefault();
        ev.stopPropagation();
        if (tb.connectMode && isConv(n.kind)) {
          handleConnectModeClick(n);
          return;
        }
        selectNode(n.id);
        const pt = canvasPointFromEvent(ev);
        tb.moving = { id: n.id, ox: pt.x - n.x, oy: pt.y - n.y };
      } else if (ev.type === 'contextmenu') {
        selectNode(n.id);
        // Do not stopPropagation — pass2 handles showCtxMenu
      }
    };
    // Property assignment avoids stacking listeners across redraws
    svg.onmousedown = onSchematicPointer;
    svg.oncontextmenu = onSchematicPointer;
    svg.onmousemove = onSchematicPointer;
    svg.onmouseleave = () => clearHover();
    const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    perfRecord('transport.drawSchematic', t1 - t0, {
      node_count: nodes.length,
      area: area?.name || area?.id || '',
    });
  }

  /** Screen flow angle (deg). RUN Y is flipped to canvas → negate sourceAngle (matches layout SVG). */
  function flowAngleDeg(n) {
    if (n.sourceAngle != null && n.sourceAngle !== '') return -Number(n.sourceAngle);
    return -(Number(n.rotation) || 0);
  }

  function segSize(n) {
    const s = presentationScale();
    const Lraw = Number(n.length);
    const Wraw = Number(n.width);
    const L = Math.max(32, (Number.isFinite(Lraw) && Lraw > 0 ? Lraw : 2400) * s);
    // Keep belt readable but compact — not Node-RED card sized
    const W = Math.max(12, Math.min(22, (Number.isFinite(Wraw) && Wraw > 0 ? Wraw : 200) * s * 2.2));
    return { L, W };
  }

  /** ENTRY / EXIT anchors in canvas space. Prefer projected entryCanvas/exitCanvas (infeed model). */
  function physicalAnchors(n) {
    if (n.entryCanvas && n.exitCanvas) {
      return {
        center: {
          x: (n.entryCanvas.x + n.exitCanvas.x) / 2,
          y: (n.entryCanvas.y + n.exitCanvas.y) / 2,
        },
        entry: { x: n.entryCanvas.x, y: n.entryCanvas.y },
        exit: { x: n.exitCanvas.x, y: n.exitCanvas.y },
      };
    }
    // Fallback: treat n.x/n.y as body center with length along flow (legacy)
    const { L } = segSize(n);
    const ang = (flowAngleDeg(n) * Math.PI) / 180;
    const hl = L / 2;
    const cx = Number(n.x) || 0;
    const cy = Number(n.y) || 0;
    return {
      center: { x: cx, y: cy },
      entry: { x: cx - Math.cos(ang) * hl, y: cy - Math.sin(ang) * hl },
      exit: { x: cx + Math.cos(ang) * hl, y: cy + Math.sin(ang) * hl },
    };
  }

  function detailLevel() {
    // Progressive disclosure: far = P-tag only; closer = Area/ES/VFD/PE
    const z = Number(tb.view?.zoom) || 1;
    if (z < 0.9) return 'overview';
    if (z < 1.35) return 'mid';
    return 'close';
  }

  function nodeAtPoint(x, y, area) {
    // Hit-test in canvas content coords (same space as node.x / node.y)
    const pad = 36;
    const canvas = $('tb-canvas');
    if (!canvas) return null;
    const cr = canvas.getBoundingClientRect();
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    for (let i = area.nodes.length - 1; i >= 0; i--) {
      const n = area.nodes[i];
      if (!isConv(n.kind)) continue;
      if (isPhysicalSeg(n)) {
        // Axis-aligned bbox around oriented segment (generous for pick)
        const { L, W } = segSize(n);
        const rad = Math.max(L, W) / 2 + pad;
        if (Math.abs(x - n.x) <= rad && Math.abs(y - n.y) <= rad) return n;
        continue;
      }
      const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
      if (!el) {
        if (x >= n.x - pad && x <= n.x + 160 + pad && y >= n.y - pad && y <= n.y + 72 + pad) {
          return n;
        }
        continue;
      }
      const r = el.getBoundingClientRect();
      const left = (r.left - cr.left + canvas.scrollLeft) / z - pad;
      const top = (r.top - cr.top + canvas.scrollTop) / z - pad;
      const w = r.width / z + pad * 2;
      const h = r.height / z + pad * 2;
      if (x >= left && x <= left + w && y >= top && y <= top + h) return n;
    }
    return null;
  }

  /** Port side classes from rotation — card stays upright; only ports move. */
  function portSides(rot) {
    const r = ((Number(rot) || 0) % 360 + 360) % 360;
    if (r === 90) return { inn: 'side-top', out: 'side-bottom' };
    if (r === 180) return { inn: 'side-right', out: 'side-left' };
    if (r === 270) return { inn: 'side-bottom', out: 'side-top' };
    return { inn: 'side-left', out: 'side-right' };
  }

  function viewportZoomLimits() {
    // Physical RUN layouts must allow deep zoom-out (fitView minZoom 0.05).
    return {
      min: tb.physicalLayout ? 0.05 : 0.25,
      max: 3,
    };
  }

  function applyViewportZoom() {
    const lim = viewportZoomLimits();
    const z = Math.max(lim.min, Math.min(lim.max, Number(tb.view?.zoom) || 1));
    tb.view.zoom = z;
    const host = $('tb-nodes');
    const wires = $('tb-wires');
    const schematic = $('tb-schematic');
    const bg = $('tb-canvas-bg');
    // Marquee must share the same scale transform as nodes/schematic so
    // world-coordinate left/top match conveyor rendering after pan/zoom.
    const marquee = $('tb-marquee');
    const origin = '0 0';
    const t = `scale(${z})`;
    [host, wires, schematic, bg, marquee].forEach((el) => {
      if (!el) return;
      el.style.transform = t;
      el.style.transformOrigin = origin;
    });
    const canvas = $('tb-canvas');
    if (canvas) canvas.dataset.zoom = String(z);
  }

  function nodeExtentPoints(n) {
    const pts = [];
    if (isSchematicNode(n) && n.entryCanvas && n.exitCanvas) {
      pts.push(n.entryCanvas, n.exitCanvas);
      (n.pathCanvas || []).forEach((p) => {
        if (p && p.x != null && p.y != null) pts.push({ x: p.x, y: p.y });
      });
      (n.arcSamplesCanvas || []).forEach((p) => pts.push(p));
    } else if (isPhysicalSeg(n) || isSchematicNode(n)) {
      const a = physicalAnchors(n);
      pts.push(a.entry, a.exit, a.center);
    } else if (isConv(n.kind)) {
      pts.push({ x: Number(n.x) || 0, y: Number(n.y) || 0 });
      pts.push({ x: (Number(n.x) || 0) + 130, y: (Number(n.y) || 0) + 70 });
    }
    return pts;
  }

  function nodesBBox(nodes, { physicalOnly } = {}) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    let count = 0;
    (nodes || []).forEach((n) => {
      if (!isConv(n.kind)) return;
      if (physicalOnly && !(isPhysicalSeg(n) || isSchematicNode(n))) return;
      const pts = nodeExtentPoints(n);
      if (!pts.length) return;
      const pad = isSchematicNode(n) || isPhysicalSeg(n) ? schematicStrokeWidth(n) : 8;
      pts.forEach((p) => {
        minX = Math.min(minX, p.x - pad);
        minY = Math.min(minY, p.y - pad);
        maxX = Math.max(maxX, p.x + pad);
        maxY = Math.max(maxY, p.y + pad);
      });
      count += 1;
    });
    if (!count || !Number.isFinite(minX)) return null;
    return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY, count };
  }

  /** Median of numbers (for robust cluster bounds). */
  function _median(vals) {
    if (!vals.length) return 0;
    const a = vals.slice().sort((x, y) => x - y);
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  /**
   * Classify visible equipment into MAIN CLUSTER vs OUTLIER EQUIPMENT.
   * Does NOT move equipment — report only. Outliers are distant from the
   * robust center of the currently displayed set.
   */
  function classifySpatialOutliers(nodes) {
    const list = (nodes || []).filter((n) => isConv(n.kind));
    const centers = list.map((n) => {
      const pts = nodeExtentPoints(n);
      if (!pts.length) return { n, x: Number(n.x) || 0, y: Number(n.y) || 0 };
      const sx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
      const sy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
      return { n, x: sx, y: sy };
    });
    if (centers.length < 3) {
      return {
        mainCluster: list,
        outliers: [],
        report: centers.map((c) => ({
          tag: c.n.conveyorTag || c.n.label || c.n.id,
          class: 'MAIN CLUSTER',
        })),
      };
    }
    const mx = _median(centers.map((c) => c.x));
    const my = _median(centers.map((c) => c.y));
    const dists = centers.map((c) => Math.hypot(c.x - mx, c.y - my));
    const medDist = _median(dists);
    // Robust threshold: max(3× median distance, 15% of full span, 80px)
    const bb = nodesBBox(list);
    const span = bb ? Math.hypot(bb.w, bb.h) : 0;
    const thresh = Math.max(medDist * 3.5, span * 0.18, 120);
    const mainCluster = [];
    const outliers = [];
    const report = [];
    centers.forEach((c, i) => {
      const tag = c.n.conveyorTag || c.n.label || c.n.id;
      if (dists[i] > thresh) {
        outliers.push(c.n);
        report.push({ tag, class: 'OUTLIER EQUIPMENT', distance_from_cluster: Math.round(dists[i]) });
      } else {
        mainCluster.push(c.n);
        report.push({ tag, class: 'MAIN CLUSTER', distance_from_cluster: Math.round(dists[i]) });
      }
    });
    tb.spatialOutliers = { mainCluster, outliers, report, threshold: thresh, medianDistance: medDist };
    return tb.spatialOutliers;
  }

  /**
   * Connected components from wires + downstream tags (engineering topology).
   * Does not invent edges — only proven wires / downstream relationships.
   */
  function computeConnectedComponents(nodes, wires) {
    const list = (nodes || []).filter((n) => isConv(n.kind));
    const byId = new Map(list.map((n) => [n.id, n]));
    const byTag = new Map();
    list.forEach((n) => {
      const t = String(n.conveyorTag || '').trim().toUpperCase();
      if (t) byTag.set(t, n);
    });
    const adj = new Map(list.map((n) => [n.id, new Set()]));
    const link = (a, b) => {
      if (!a || !b || a === b || !adj.has(a) || !adj.has(b)) return;
      adj.get(a).add(b);
      adj.get(b).add(a);
    };
    (wires || []).forEach((w) => link(w.from, w.to));
    list.forEach((n) => {
      const ds = String(n.downstream || '').trim().toUpperCase();
      if (!ds) return;
      const dst = byTag.get(ds);
      if (dst) link(n.id, dst.id);
    });
    const seen = new Set();
    const components = [];
    list.forEach((n) => {
      if (seen.has(n.id)) return;
      const stack = [n.id];
      const members = [];
      seen.add(n.id);
      while (stack.length) {
        const id = stack.pop();
        members.push(byId.get(id));
        (adj.get(id) || []).forEach((nb) => {
          if (!seen.has(nb)) {
            seen.add(nb);
            stack.push(nb);
          }
        });
      }
      const tags = members.map((m) => m.conveyorTag || m.id).filter(Boolean);
      components.push({
        size: members.length,
        nodes: members,
        tags,
        isIsland: members.length <= 2,
      });
    });
    components.sort((a, b) => b.size - a.size);
    const primary = components[0] || null;
    const islandCount = components.filter((c) => c !== primary).length;
    tb.topologyComponents = {
      count: components.length,
      primarySize: primary ? primary.size : 0,
      islandCount,
      components: components.map((c, i) => ({
        id: i + 1,
        size: c.size,
        tags: c.tags.slice(0, 40),
        isPrimary: i === 0,
        isIsland: i > 0,
      })),
    };
    return tb.topologyComponents;
  }

  function fitViewToNodes(nodes, { mode, paddingFrac, minZoom, maxZoom, excludeOutliers, primaryComponentOnly } = {}) {
    const canvas = $('tb-canvas');
    if (!canvas) return null;
    let useNodes = nodes || [];
    let outlierInfo = null;
    // Prefer PRIMARY connected component for centering so islands don't shove
    // the main system off to one side (still accessible via Fit All / pan).
    const preferPrimary = primaryComponentOnly !== false;
    if (preferPrimary && useNodes.length >= 3) {
      const area = activeArea();
      const topo = computeConnectedComponents(useNodes, area?.wires || []);
      // Map tag → component size
      const tagSize = new Map();
      (topo.components || []).forEach((c) => {
        (c.tags || []).forEach((t) => tagSize.set(String(t).toUpperCase(), c.size));
      });
      // Fit bbox: LOCAL engineering topology — exclude EXTERNAL_REFERENCE display
      // context and singleton islands so they cannot shove the main system aside.
      // Islands remain on the canvas (Fit All / pan). No invented edges.
      const fitCandidates = useNodes.filter((n) => {
        if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE' || n.displayContext) {
          return false;
        }
        const t = String(n.conveyorTag || '').trim().toUpperCase();
        const sz = tagSize.get(t) || tagSize.get(String(n.id).toUpperCase()) || 1;
        return sz >= 3; // keep chains of 3+; drop true singletons/pairs from fit frame
      });
      if (fitCandidates.length >= 4) {
        useNodes = fitCandidates;
      } else if ((topo.components || [])[0]?.size >= 2) {
        const pTags = new Set(((topo.components || [])[0].tags || []).map((t) => String(t).toUpperCase()));
        const primaryNodes = useNodes.filter((n) => {
          const t = String(n.conveyorTag || '').trim().toUpperCase();
          return (t && pTags.has(t)) || pTags.has(String(n.id).toUpperCase());
        });
        if (primaryNodes.length >= 2) useNodes = primaryNodes;
      }
      try {
        if (typeof status === 'function') {
          status(
            `CONNECTED COMPONENTS: ${topo.count} · PRIMARY: ${topo.primarySize} · ISLANDS: ${topo.islandCount}`
          );
        }
      } catch (_) { /* ignore */ }
    }
    if (excludeOutliers) {
      outlierInfo = classifySpatialOutliers(useNodes);
      if ((outlierInfo.mainCluster || []).length >= 2) {
        useNodes = outlierInfo.mainCluster;
      }
    }
    const bb = nodesBBox(useNodes, {
      physicalOnly: !!(tb.physicalLayout || useNodes.some((n) => isPhysicalSeg(n) || isSchematicNode(n))),
    });
    if (!bb || bb.w < 1 || bb.h < 1) return outlierInfo;
    // 5–10% viewport padding around visible equipment (default 8%)
    const pf = paddingFrac != null ? paddingFrac : 0.08;
    const padX = Math.max(24, bb.w * pf);
    const padY = Math.max(24, bb.h * pf);
    const frameW = bb.w + padX * 2;
    const frameH = bb.h + padY * 2;
    const cw = Math.max(200, canvas.clientWidth);
    const ch = Math.max(160, canvas.clientHeight);
    // Physical RUN layouts use fixed world scale — allow deep zoom-out so fitView
    // frames the plant without compressing geometry into the viewport box.
    const defaultMin = tb.physicalLayout ? 0.05 : 0.55;
    const zMin = minZoom != null ? minZoom : defaultMin;
    const zMax = maxZoom != null ? maxZoom : 2.4;
    const zoom = Math.max(zMin, Math.min(zMax, Math.min(cw / frameW, ch / frameH)));
    tb.view.zoom = zoom;
    tb.view.mode = mode || tb.view.mode || 'visible';
    applyViewportZoom();
    // TOP-CENTER (not center-center):
    //   boundsCenterX → viewportCenterX  (balanced left/right padding)
    //   minY → viewportTop + topPadding  (system near top; unused space below)
    const boundsCenterX = ((bb.minX + bb.maxX) / 2) * zoom;
    const topPadPx = Math.max(28, (pf != null ? pf : 0.08) * Math.max(160, canvas.clientHeight));
    canvas.scrollLeft = Math.max(0, boundsCenterX - canvas.clientWidth / 2);
    canvas.scrollTop = Math.max(0, bb.minY * zoom - topPadPx);
    return outlierInfo;
  }

  /** Fit currently displayed equipment — center active Area conveyance X+Y. */
  function fitVisible() {
    const area = activeArea();
    // Prefer CURRENTLY VISIBLE Area conveyance so Fit View balances padding
    // on both axes for the selected Area (Fit Site / Fit All for full plant).
    const areaNodes = area?.nodes || [];
    const nodes = [];
    if (areaNodes.length) {
      areaNodes.forEach((n) => nodes.push(n));
    } else {
      (tb.areas || []).forEach((a) => (a.nodes || []).forEach((n) => nodes.push(n)));
    }
    const useNodes = nodes.length ? nodes : areaNodes;
    // Lite: keep a readable zoom floor so P-tags remain usable after Fit System.
    const liteFloor = (typeof isLiteRenderMode === 'function' && isLiteRenderMode()) ? 0.18 : 0.05;
    const info = fitViewToNodes(useNodes, {
      mode: 'visible',
      paddingFrac: 0.1,
      minZoom: tb.physicalLayout ? Math.max(0.05, liteFloor) : 0.35,
      maxZoom: 2.4,
      // Physical layouts already have real XY — do not drop "outlier" chains.
      excludeOutliers: !tb.physicalLayout,
    });
    drawSchematic(area);
    drawWires();
    const nOut = info?.outliers?.length || 0;
    status(
      nOut
        ? `Fit View · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}% · Top-Centered · ${nOut} OUTLIER (use Fit All)`
        : `Fit View · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}% · Top-Centered (X center, Y top)`
    );
    return info;
  }

  /** Fit all displayed equipment including spatial outliers. */
  function fitAll() {
    const area = activeArea();
    const nodes = area?.nodes || [];
    classifySpatialOutliers(nodes);
    fitViewToNodes(nodes, {
      mode: 'all',
      paddingFrac: 0.08,
      minZoom: tb.physicalLayout ? 0.05 : 0.25,
      maxZoom: 2.4,
      excludeOutliers: false,
    });
    drawSchematic(area);
    drawWires();
    const nOut = (tb.spatialOutliers?.outliers || []).length;
    status(
      `Fit All · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}%`
        + (nOut ? ` · includes ${nOut} OUTLIER EQUIPMENT` : '')
    );
  }

  function fitSite() {
    // Alias: Fit All across areas currently loaded (controller-filtered canvas)
    const nodes = [];
    (tb.areas || []).forEach((a) => (a.nodes || []).forEach((n) => nodes.push(n)));
    // Prefer Fit Visible semantics when a single area is active with physical layout
    if (tb.physicalLayout && activeArea()?.nodes?.length) {
      return fitVisible();
    }
    fitViewToNodes(nodes, {
      mode: 'site',
      paddingFrac: 0.08,
      minZoom: tb.physicalLayout ? 0.05 : 0.55,
      excludeOutliers: !tb.physicalLayout,
    });
    drawSchematic(activeArea());
    drawWires();
    status(`Fit Site · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}%`);
  }

  function fitArea() {
    const area = activeArea();
    fitViewToNodes(area?.nodes || [], {
      mode: 'area',
      paddingFrac: 0.08,
      minZoom: tb.physicalLayout ? 0.05 : 0.55,
      excludeOutliers: !tb.physicalLayout,
    });
    drawSchematic(area);
    drawWires();
    status(`Fit Area · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}%`);
  }

  /** Frame current selection (or Fit Visible when nothing selected). */
  function fitSelection() {
    const area = activeArea();
    const ids = new Set(
      (tb.selectedIds || []).length
        ? tb.selectedIds
        : tb.selectedId
          ? [tb.selectedId]
          : []
    );
    const nodes = (area?.nodes || []).filter((n) => ids.has(n.id));
    if (nodes.length < 1) {
      return fitVisible();
    }
    fitViewToNodes(nodes, {
      mode: 'selection',
      paddingFrac: 0.12,
      minZoom: tb.physicalLayout ? 0.05 : 0.35,
      excludeOutliers: false,
    });
    drawSchematic(area);
    drawWires();
    status(`Frame Selection · ${nodes.length} · zoom ${((tb.view.zoom || 1) * 100).toFixed(0)}%`);
  }

  /** Gate H — Fit System (primary connected plant). */
  function fitSystem() {
    return fitVisible();
  }

  /** Gate H — Center Selected (alias of Frame Selection). */
  function centerSelected() {
    return fitSelection();
  }

  /** Gate H — Home: reset zoom/pan to a stable origin view. */
  function homeView() {
    return resetView100();
  }

  /** Gate H — set geometry authority display mode. */
  function setGeometryAuthorityMode(mode) {
    const m = String(mode || 'run').toLowerCase();
    tb.geometryAuthorityMode = (m === 'override' || m === 'diagnostic' || m === 'run') ? m : 'run';
    if (tb.geometryAuthorityMode === 'diagnostic') {
      tb.viewMode = 'geom-debug';
      if (!tb.layers) tb.layers = {};
      tb.layers.physical = true;
    } else if (tb.viewMode === 'geom-debug' && m === 'run') {
      tb.viewMode = 'schematic';
      if (tb.layers) tb.layers.physical = false;
    }
    // Returning to RUN/Physical with laneSeparate OFF clears any presentation scatter.
    if (tb.geometryAuthorityMode === 'run' && !tb.laneSeparate) {
      try { requestPresentationRelayout(); } catch (_) { /* ignore */ }
    }
    try { render(); } catch (_) { /* ignore */ }
    status(`Geometry mode: ${tb.geometryAuthorityMode === 'run' ? 'RUN/Physical'
      : (tb.geometryAuthorityMode === 'override' ? 'Engineering Override' : 'Diagnostic')}`);
    return tb.geometryAuthorityMode;
  }

  function renderTopologyPanel() {
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    try { renderTopologyTable(); } catch (_) { /* ignore */ }
    perfRecord('transport.openTopology', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {
      node_count: (tb.areas || []).reduce((s, a) => s + ((a.nodes || []).filter((n) => isConv(n.kind)).length), 0),
    });
  }

  function renderInventoryPanel() {
    try {
      if (typeof renderInventory === 'function') renderInventory();
    } catch (_) { /* ignore */ }
  }

  function renderScene() {
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    ensureArea();
    const area = activeArea();
    const empty = $('tb-canvas-empty');
    const host = $('tb-nodes');
    const wires = $('tb-wires');
    if (!host || !wires) return;
    syncRenderModeButtons();

    const hasNodes = !!(area && (area.nodes || []).length);
    if (empty) {
      empty.classList.toggle('hidden', hasNodes);
      if (!hasNodes && typeof window.updateTransportEmptyState === 'function') {
        const id = currentProjectIdentity();
        const machine = id?.machine || window.state?.workspace?.machine || '';
        if (!machine) window.updateTransportEmptyState({ status: 'no_project' });
        else window.updateTransportEmptyState({ status: 'active_empty', machine, site: id?.site });
      }
    }
    try {
      if (typeof window.updateTransportActiveProjectUi === 'function') {
        window.updateTransportActiveProjectUi({ ok: true });
      }
    } catch (_) { /* ignore */ }

    // Lite: SVG schematic only — no HTML conveyor proxy DIVs
    if (isLiteRenderMode()) {
      host.innerHTML = '';
      ensureCanvasExtents(area);
      applyViewportZoom();
      drawSchematicNow(area);
      if (tb.showRelationships || tb.layers?.relationships) drawWiresNow();
      else {
        const svg = $('tb-wires');
        if (svg) svg.innerHTML = '';
      }
      perfRecord('transport.renderScene', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {
        mode: 'lite',
        node_count: (area?.nodes || []).length,
      });
      return;
    }

    const lod = detailLevel();
    host.innerHTML = '';
    (area?.nodes || []).forEach((n) => {
      // Conveyor-first: hide attached device nodes unless their layer is on.
      if (!isConv(n.kind) && !n.externalReference) {
        const k = String(n.kind || '').toLowerCase();
        const showMotor = !!(tb.layers?.motors || tb.layers?.deviceLabels) && (k === 'motor' || k === 'vfd');
        const showPe = !!(tb.layers?.photoeyes || tb.layers?.deviceLabels) && k === 'photoeye';
        const showOther = !!(tb.layers?.otherDevices || tb.layers?.deviceLabels)
          && !showMotor && !showPe;
        if (!(showMotor || showPe || showOther)) return;
      }
      if (n.externalReference && tb.layers?.externalRefs === false) return;
      const meta = KIND_META[n.kind] || { icon: 'fa-cube', color: 'text-slate-300', title: n.kind };
      const el = document.createElement('div');
      el.dataset.id = n.id;
      // Clean schematic is NORMAL: draw pathCanvas/curve bodies in #tb-schematic.
      // Physical-debug layer (tb.layers.physical === true) may still use segment cards
      // for non-schematic nodes. Never require physical=true to show curves — that
      // inverted gate made CURVE nodes render as horizontal .tb-seg.tb-curve pills
      // (P226 acceptance failure).
      const useSchematic = isSchematicNode(n);
      const useSeg = !useSchematic && isPhysicalSeg(n);
      const rot = Number(n.rotation || 0) % 360;
      const sides = portSides(useSeg ? 0 : rot); // segment ports sit on length ends

      const areaName = activeArea()?.name || '';
      const roleLetters = peRolesOnNode(n);
      const roleBadges = peRoleBadgesHtml(roleLetters);
      const tagShow = (n.conveyorTag || '').trim() || (isConv(n.kind) ? 'P???' : (n.label || meta.title));
      const mergeNote = (meta.isMerge || n.asMerge)
        ? `<span class="text-orange-400/90 text-[8px]">${n.inPorts || 2}:1</span>`
        : '';
      const spiralNote = meta.isSpiral
        ? `<span class="text-teal-400/80 text-[8px]">${normalizeSpiralMotors(n).filter(Boolean).length}M</span>`
        : '';
      const orientNote = rot ? `<span class="tb-orient">${rot}°</span>` : '';

      let portsHtml = '';
      if (isConv(n.kind)) {
        const inCount = (meta.isMerge || n.asMerge) ? Math.max(2, Number(n.inPorts) || 2) : 1;
        if (useSeg) {
          // Mating anchors: ENTRY ◀ left · EXIT ▶ right in local segment space
          if (inCount === 1) {
            portsHtml += `<div class="tb-port in side-left tb-anchor-entry" data-port="in" title="ENTRY ◀"></div>`;
          } else {
            for (let i = 0; i < inCount; i++) {
              const pct = ((i + 1) / (inCount + 1)) * 100;
              portsHtml += `<div class="tb-port in side-left tb-anchor-entry" data-port="in${i}" style="top:${pct}%;transform:translateY(-50%)" title="ENTRY ◀ ${i + 1}"></div>`;
            }
          }
          portsHtml += `<div class="tb-port out side-right tb-anchor-exit" data-port="out" title="EXIT ▶"></div>`;
        } else {
          if (inCount === 1) {
            portsHtml += `<div class="tb-port in ${sides.inn}" data-port="in" title="Entrance"></div>`;
          } else {
            for (let i = 0; i < inCount; i++) {
              const pct = ((i + 1) / (inCount + 1)) * 100;
              const along = sides.inn.includes('top') || sides.inn.includes('bottom')
                ? `left:${pct}%;transform:translateX(-50%)`
                : `top:${pct}%;transform:translateY(-50%)`;
              portsHtml += `<div class="tb-port in ${sides.inn}" data-port="in${i}" style="${along}" title="Entrance ${i + 1}"></div>`;
            }
          }
          portsHtml += `<div class="tb-port out ${sides.out}" data-port="out" title="Exit"></div>`;
        }
      }

      const connectCls = tb.connectMode && tb.connectSourceId === n.id
        ? ' tb-connect-src'
        : (tb.connectMode && tb.connectSourceId && n.id !== tb.connectSourceId ? ' tb-connect-dst' : '');
      if (n.asMerge) el.classList.add('tb-as-merge');

      const cp = normalizeControlPanel(n.controlPanel);
      const cpMatch = nodeMatchesCpFilter(n);
      const cpCls = cp === 'CP1' || cp === 'CP2' || cp === 'CP3'
        ? ` tb-cp-${cp}`
        : (cp === 'Other' ? ' tb-cp-Other' : '');
      const cpFilterCls = cpFilterActive() ? (cpMatch ? ' tb-cp-match' : ' tb-cp-dim') : '';
      const multiSel = n.id === tb.selectedId || (tb.selectedIds || []).includes(n.id);

      if (useSchematic) {
        // Invisible proxy at body center — selection/drag/connect; body drawn in #tb-schematic
        el.className = `tb-node tb-schematic-proxy tb-physical${multiSel ? ' selected' : ''}${meta.isMerge || n.asMerge ? ' tb-merge' : ''}${connectCls}${cpCls}${cpFilterCls}`;
        if ((n.ambiguousInbound || []).length) el.classList.add('tb-ambiguous');
        el.style.left = `${(Number(n.x) || 0) - 9}px`;
        el.style.top = `${(Number(n.y) || 0) - 9}px`;
        el.style.width = '18px';
        el.style.height = '18px';
        el.style.transform = '';
        el.innerHTML = `${portsHtml}`;
        el.title = cp ? `${(n.conveyorTag || n.label || '').trim()} · ${cp}` : (n.conveyorTag || n.label || '').trim();
      } else if (useSeg) {
        const { L, W } = segSize(n);
        const ang = flowAngleDeg(n);
        const eq = String(n.equipmentType || '').toUpperCase();
        el.className = `tb-node tb-seg${multiSel ? ' selected' : ''}${meta.isMerge || n.asMerge ? ' tb-merge' : ''}${connectCls}${cpCls}${cpFilterCls}`;
        if (eq === 'CURVE' || n.kind === 'conv_right' || n.kind === 'conv_left') el.classList.add('tb-curve');
        if (eq === 'MERGE' || n.asMerge) el.classList.add('tb-seg-merge');
        if (eq === 'BELT') el.classList.add('tb-seg-belt');
        if ((n.ambiguousInbound || []).length) el.classList.add('tb-ambiguous');
        el.classList.add('tb-physical');
        el.style.left = `${(Number(n.x) || 0) - L / 2}px`;
        el.style.top = `${(Number(n.y) || 0) - W / 2}px`;
        el.style.width = `${L}px`;
        el.style.height = `${W}px`;
        el.style.transform = `rotate(${ang}deg)`;
        const counter = -ang;
        // Conveyor-first: P-tag only on body; no AMB / equipmentType / PE badges on canvas.
        el.innerHTML = `
          <div class="tb-seg-body" title="${escapeHtml(cp ? `${tagShow} · ${cp}` : tagShow)}">
            <span class="tb-seg-entry" aria-hidden="true">◀</span>
            <span class="tb-seg-label" style="transform:rotate(${counter}deg)">${escapeHtml(tagShow)}</span>
            <span class="tb-seg-exit" aria-hidden="true">▶</span>
          </div>
          ${portsHtml}
        `;
      } else {
        el.className = `tb-node${multiSel ? ' selected' : ''}${meta.isMerge || n.asMerge ? ' tb-merge' : ''}${connectCls}${cpCls}${cpFilterCls}`;
        el.style.left = `${n.x}px`;
        el.style.top = `${n.y}px`;
        el.style.transform = ''; // card stays upright — labels always readable
        // Conveyor-first card: tag only; details live in inspector / hover.
        el.innerHTML = `
          <div class="tb-content" title="${escapeHtml(cp ? `${tagShow} · ${cp}` : tagShow)}">
            <div class="tb-head">
              ${isConv(n.kind) ? '' : kindIconHtml(n.kind, meta.color)}
              <span class="tb-tag truncate">${escapeHtml(tagShow)}</span>
              ${cp ? `<span class="tb-cp-chip">${escapeHtml(cp)}</span>` : ''}
            </div>
          </div>
          ${portsHtml}
        `;
      }

      el.addEventListener('mousedown', (ev) => {
        if (ev.target.classList.contains('tb-port')) return;
        if (ev.button === 1) return; // middle-mouse reserved for pan (Pass2)
        if (tb.connectMode && isConv(n.kind)) {
          ev.preventDefault();
          ev.stopPropagation();
          handleConnectModeClick(n);
          return;
        }
        // Pass2 capture handler owns multi-select / group-move setup when present
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
        if ((tb.selectedIds || []).length > 1 && (tb.selectedIds || []).includes(n.id)) return;
        selectNode(n.id);
        const pt = canvasPointFromEvent(ev);
        tb.moving = {
          id: n.id,
          ox: pt.x - n.x,
          oy: pt.y - n.y,
          origins: [captureNodeGeom(n)],
          startX: n.x,
          startY: n.y,
        };
        ev.preventDefault();
      });

      el.querySelectorAll('.tb-port').forEach((port) => {
        port.addEventListener('mousedown', (ev) => {
          ev.stopPropagation();
          if (port.dataset.port !== 'out') return;
          tb.linkFrom = { nodeId: n.id, port: 'out' };
          port.classList.add('linking');
          status(`Linking from ${n.label || n.id} EXIT ▶ → drop on ENTRY ◀`);
        });
      });

      host.appendChild(el);
    });

    ensureCanvasExtents(area);
    applyViewportZoom();
    const canvas = $('tb-canvas');
    if (canvas) {
      canvas.classList.add('tb-clean-schematic');
      canvas.classList.toggle('tb-geom-debug', tb.viewMode === 'geom-debug' || !!tb.layers?.physical);
      canvas.classList.toggle('tb-cp-filter-active', cpFilterActive());
    }
    ensureCanvasExtents(area);
    applyViewportZoom();
    drawSchematicNow(area);
    if (tb.showRelationships || tb.layers?.relationships) drawWiresNow();
    else {
      const wsvg = $('tb-wires');
      if (wsvg) wsvg.innerHTML = '';
    }
    perfRecord('transport.renderScene', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {
      mode: 'detailed',
      node_count: (area?.nodes || []).length,
    });
  }

  /** Full page refresh — panels are opt-in; scene is always updated. */
  function render() {
    ensureArea();
    refreshAreaSelect();
    renderScene();
    renderInspector();
    setWorkflowStep(tb.workflow?.apply ? 'build' : (tb.workflow?.autobuild ? 'review' : 'review'));
    // Topology table + inventory must refresh in ALL modes (including Lite).
    // Skipping them in Lite left Area membership invisible despite placed conveyors.
    try { renderTopologyPanel(); } catch (_) { /* ignore */ }
    try { renderInventoryPanel(); } catch (_) { /* ignore */ }
    try { renderAreaResolutionPanels(); } catch (_) { /* ignore */ }
    const valEl = $('tb-validation');
    if (valEl && (!valEl.classList.contains('hidden') || valEl.offsetParent)) {
      renderValidationPanel();
    }
    const autoEl = $('tb-auto-connect');
    if (autoEl) autoEl.checked = !!tb.autoConnectNew;
    if (typeof window.__tbOnTransportRender === 'function') {
      try {
        window.__tbOnTransportRender();
      } catch (err) {
        try {
          console.warn('[TransportBuild] __tbOnTransportRender', err);
        } catch (_) { /* ignore */ }
      }
    }
  }

  function portCenter(nodeId, port) {
    const area = activeArea();
    const node = (area?.nodes || []).find((n) => n.id === nodeId);
    if (node && isSchematicNode(node) && node.entryCanvas && node.exitCanvas) {
      const key = port || 'in';
      if (key === 'out') return { x: node.exitCanvas.x, y: node.exitCanvas.y };
      return { x: node.entryCanvas.x, y: node.entryCanvas.y };
    }
    if (node && isPhysicalSeg(node)) {
      const a = physicalAnchors(node);
      const key = port || 'in';
      if (key === 'out') return a.exit;
      return a.entry;
    }
    const el = document.querySelector(`.tb-node[data-id="${nodeId}"]`);
    if (!el) return null;
    const key = port || 'in';
    let p = el.querySelector(`.tb-port[data-port="${key}"]`);
    if (!p && key === 'in') p = el.querySelector('.tb-port.in');
    if (!p && String(key).startsWith('in')) p = el.querySelector(`.tb-port[data-port="${key}"]`);
    const canvas = $('tb-canvas');
    if (!p || !canvas) return null;
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    const pr = p.getBoundingClientRect();
    const cr = canvas.getBoundingClientRect();
    return {
      x: (pr.left + pr.width / 2 - cr.left + canvas.scrollLeft) / z,
      y: (pr.top + pr.height / 2 - cr.top + canvas.scrollTop) / z,
    };
  }

  /** Grow the drawable grid when nodes sit near the edge (fixes deep-scroll drop/wire).
   *  Also pad by ~½ viewport (world units) so Fit/Area-switch can center X+Y without
   *  clamping scroll to the origin (which biases topology left/right). */
  function ensureCanvasExtents(area) {
    const host = $('tb-nodes');
    const wires = $('tb-wires');
    const schematic = $('tb-schematic');
    const canvas = $('tb-canvas');
    if (!host) return;
    let maxX = 1600;
    let maxY = 1000;
    // Include presentation offsets so lane-separated bodies stay inside SVG extents
    const offsets = tb._presentationOffsets || {};
    (area?.nodes || []).forEach((n) => {
      const odx = Number(offsets[n.id]?.dx) || Number(n.display_dx) || 0;
      const ody = Number(offsets[n.id]?.dy) || Number(n.display_dy) || 0;
      if (isSchematicNode(n) && n.entryCanvas && n.exitCanvas) {
        const pad = 80;
        maxX = Math.max(
          maxX,
          n.entryCanvas.x + odx + pad,
          n.exitCanvas.x + odx + pad,
          (Number(n.x) || 0) + odx + pad,
        );
        maxY = Math.max(
          maxY,
          n.entryCanvas.y + ody + pad,
          n.exitCanvas.y + ody + pad,
          (Number(n.y) || 0) + ody + pad,
        );
        (n.pathCanvas || []).forEach((p) => {
          if (p.x != null) maxX = Math.max(maxX, p.x + odx + pad);
          if (p.y != null) maxY = Math.max(maxY, p.y + ody + pad);
        });
      } else if (isPhysicalSeg(n)) {
        const a = physicalAnchors(n);
        const { W } = segSize(n);
        const pad = Math.max(40, W * 2);
        maxX = Math.max(maxX, a.entry.x + pad, a.exit.x + pad, a.center.x + pad);
        maxY = Math.max(maxY, a.entry.y + pad, a.exit.y + pad, a.center.y + pad);
      } else {
        maxX = Math.max(maxX, (Number(n.x) || 0) + 280);
        maxY = Math.max(maxY, (Number(n.y) || 0) + 180);
      }
    });
    // Room to scroll so visibleCenter maps to viewportCenter (balanced padding)
    const z = Math.max(0.05, Number(tb.view?.zoom) || 1);
    if (canvas) {
      maxX = Math.max(maxX, (canvas.clientWidth / z) + 200);
      maxY = Math.max(maxY, (canvas.clientHeight / z) + 200);
    }
    host.style.minWidth = `${maxX}px`;
    host.style.minHeight = `${maxY}px`;
    [wires, schematic].forEach((el) => {
      if (!el) return;
      el.setAttribute('width', String(maxX));
      el.setAttribute('height', String(maxY));
      el.style.width = `${maxX}px`;
      el.style.height = `${maxY}px`;
    });
  }

  /**
   * Gate 4 — classify a rendered connection for viz (does not mutate topology).
   * Classes: PHYSICAL_GEOMETRY | PROVEN_TOPOLOGY | DERIVED_TOPOLOGY | VISUAL_HELPER | UNKNOWN
   * Draw priority for physical-looking joins:
   *   ENGINEER_OVERRIDE > PROVEN_RUN_GEOMETRY > PROVEN_PHYSICAL_RELATIONSHIP > DERIVED_TOPOLOGY > FALLBACK
   * Logical/control relationships must NEVER paint as physical belt joins.
   * RUN XY proximity alone must NEVER invent connecting segments.
   */
  function classifyRenderedConnection(wire, fromNode, toNode) {
    if (!wire) return 'UNKNOWN';
    if (wire._temp || wire.visualHelper === true) return 'VISUAL_HELPER';
    const conf = String(wire.confidence || '').toUpperCase();
    const prov = String(wire.provenance || '').toUpperCase();
    const auth = String(wire.authority || wire.overrideAuthority || '').toUpperCase();
    const topo = String(
      (fromNode && fromNode.topologyProvenance && fromNode.topologyProvenance.confidence)
      || (fromNode && fromNode.topologyProvenance && fromNode.topologyProvenance.rule)
      || ''
    ).toUpperCase();
    if (auth === 'ENGINEER_OVERRIDE' || wire.engineerOverride === true) {
      return wire.physical ? 'PHYSICAL_GEOMETRY' : 'PROVEN_TOPOLOGY';
    }
    if (wire.physical && (conf === 'CONFIRMED' || conf.includes('HIGH'))) {
      return 'PHYSICAL_GEOMETRY';
    }
    if (
      conf.includes('PROVEN')
      || prov.includes('MTRCHAIN')
      || prov.includes('MERGE')
      || topo.includes('PROVEN')
      || topo.includes('MTRCHAIN')
    ) {
      return 'PROVEN_TOPOLOGY';
    }
    if (wire.physical === false || prov || conf.includes('DERIVED') || conf.includes('AUTO')) {
      return 'DERIVED_TOPOLOGY';
    }
    if (!wire.physical) return 'DERIVED_TOPOLOGY';
    if (wire.physical) return 'UNKNOWN';
    return 'UNKNOWN';
  }

  /** True when a wire may paint a physical-looking EXIT▶◀ENTRY join / stub. */
  function mayDrawPhysicalJoin(wire, cls) {
    const auth = String(wire?.authority || wire?.overrideAuthority || '').toUpperCase();
    if (auth === 'ENGINEER_OVERRIDE' || wire?.engineerOverride === true) return true;
    return cls === 'PHYSICAL_GEOMETRY';
  }

  /** Proven physical mate between two node ids (CONFIRMED / HIGH only). */
  function hasProvenPhysicalWire(area, aId, bId) {
    return (area?.wires || []).some((w) => {
      if (!w.physical) return false;
      const conf = String(w.confidence || '').toUpperCase();
      if (!(conf === 'CONFIRMED' || conf.includes('HIGH'))) return false;
      return (w.from === aId && w.to === bId) || (w.from === bId && w.to === aId);
    });
  }

  /**
   * Gate 4 — presentation tip inset when RUN XY places bodies near each other
   * without a proven physical wire. Prevents thick schematic strokes from
   * paint-merging into a false discharge→horizontal join. Never invents wires.
   */
  function falseAbutmentInsets(n, nodes, area, offsets) {
    const out = { entryInset: 0, exitInset: 0 };
    if (!n?.entryCanvas || !n?.exitCanvas || isCurveNode(n)) return out;
    const off = (offsets && offsets[n.id]) || { dx: 0, dy: 0 };
    const en = applyPresOffset(n.entryCanvas, off);
    const ex = applyPresOffset(n.exitCanvas, off);
    const len = Math.hypot(ex.x - en.x, ex.y - en.y);
    if (!(len > 4)) return out;
    const swN = schematicStrokeWidth(n);
    const minGap = 6;
    (nodes || []).forEach((o) => {
      if (!o || o.id === n.id || !o.entryCanvas || !o.exitCanvas) return;
      if (hasProvenPhysicalWire(area, n.id, o.id)) return;
      const oo = (offsets && offsets[o.id]) || { dx: 0, dy: 0 };
      const oe = applyPresOffset(o.entryCanvas, oo);
      const ox = applyPresOffset(o.exitCanvas, oo);
      const olx = ox.x - oe.x;
      const oly = ox.y - oe.y;
      const olen = Math.hypot(olx, oly) || 1;
      const swO = schematicStrokeWidth(o);
      const need = (swN + swO) / 2 + minGap;
      // Distance from our EXIT/ENTRY to other centerline segment
      const distPtSeg = (px, py) => {
        const t = Math.max(0, Math.min(1, ((px - oe.x) * olx + (py - oe.y) * oly) / (olen * olen)));
        const qx = oe.x + t * olx;
        const qy = oe.y + t * oly;
        return Math.hypot(px - qx, py - qy);
      };
      const dExit = distPtSeg(ex.x, ex.y);
      if (dExit < need) {
        out.exitInset = Math.max(out.exitInset, Math.min(len * 0.35, need - dExit + 2));
      }
      const dEntry = distPtSeg(en.x, en.y);
      if (dEntry < need) {
        out.entryInset = Math.max(out.entryInset, Math.min(len * 0.35, need - dEntry + 2));
      }
      // Other tip lands near our body — inset our near side so paint doesn't merge
      const distToOur = (px, py) => {
        const t = Math.max(0, Math.min(1, ((px - en.x) * (ex.x - en.x) + (py - en.y) * (ex.y - en.y)) / (len * len)));
        const qx = en.x + t * (ex.x - en.x);
        const qy = en.y + t * (ex.y - en.y);
        return { d: Math.hypot(px - qx, py - qy), t };
      };
      [oe, ox].forEach((pt) => {
        const r = distToOur(pt.x, pt.y);
        if (r.d >= need) return;
        if (r.t > 0.55) out.exitInset = Math.max(out.exitInset, Math.min(len * 0.35, need - r.d + 2));
        else if (r.t < 0.45) out.entryInset = Math.max(out.entryInset, Math.min(len * 0.35, need - r.d + 2));
      });
    });
    return out;
  }

  function insetDisplayEndpoints(entry, exit, insets) {
    if (!entry || !exit) return { entry, exit };
    const len = Math.hypot(exit.x - entry.x, exit.y - entry.y);
    if (!(len > 4)) return { entry, exit };
    const ux = (exit.x - entry.x) / len;
    const uy = (exit.y - entry.y) / len;
    const ei = Math.max(0, Number(insets?.entryInset) || 0);
    const xi = Math.max(0, Number(insets?.exitInset) || 0);
    if (ei + xi >= len - 2) return { entry, exit };
    return {
      entry: { x: entry.x + ux * ei, y: entry.y + uy * ei },
      exit: { x: exit.x - ux * xi, y: exit.y - uy * xi },
    };
  }

  function drawWires(temp) {
    // Coalesce pointer-driven wire redraws; force immediate when linking temp path.
    if (temp) {
      drawWiresNow(temp);
      return;
    }
    scheduleDrawWires(temp);
  }

  function drawWiresNow(temp) {
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const svg = $('tb-wires');
    const host = $('tb-nodes');
    const canvas = $('tb-canvas');
    if (!svg || !host) return;
    const area = activeArea();
    ensureCanvasExtents(area);
    const showRel = !!(tb.showRelationships || tb.layers?.relationships);
    canvas?.classList.toggle('tb-hide-relationships', !showRel);
    if (!showRel && !temp) {
      svg.innerHTML = '';
      const tSkip = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      perfRecord('transport.drawWires', tSkip - t0, { skipped: true, reason: 'relationships_off' });
      return;
    }
    const w = Math.max(host.scrollWidth || 0, host.offsetWidth || 0, parseInt(host.style.minWidth || '0', 10) || 0);
    const h = Math.max(host.scrollHeight || 0, host.offsetHeight || 0, parseInt(host.style.minHeight || '0', 10) || 0);
    svg.setAttribute('width', String(w));
    svg.setAttribute('height', String(h));
    svg.style.width = `${w}px`;
    svg.style.height = `${h}px`;
    svg.style.pointerEvents = 'none';
    let html = '';
    const byId = {};
    (area?.nodes || []).forEach((n) => { byId[n.id] = n; });
    // Visualization-only: when relationships are hidden, skip all wires except temp connect rubber-band.
    // Wire data on the model is never deleted.
    if (!showRel && !(temp && temp.from && temp.to)) {
      svg.innerHTML = '';
      return;
    }
    (area?.wires || []).forEach((wire) => {
      if (!showRel) return;
      const fromN = byId[wire.from];
      const toN = byId[wire.to];
      const clsKind = classifyRenderedConnection(wire, fromN, toN);
      const a = portCenter(wire.from, 'out');
      const b = portCenter(wire.to, wire.toPort || 'in');
      if (!a || !b) return;
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      const conf = String(wire.confidence || '').toUpperCase();
      const physicalJoin = mayDrawPhysicalJoin(wire, clsKind);
      // Confirmed physical mates: endpoints coincide — mate mark drawn in schematic layer; no Bezier wire
      if (physicalJoin && dist < 12) {
        return;
      }
      // Gate 4: logical/control topology must not paint as a physical belt join.
      // Proximity without PHYSICAL_GEOMETRY never invents a connecting segment.
      let d;
      let cls = `tb-wire tb-conn-${clsKind.toLowerCase()}`;
      if (physicalJoin && dist < 80) {
        d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
        cls += ' tb-physical';
      } else if (physicalJoin) {
        d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
        cls += ' tb-physical';
      } else if (clsKind === 'PROVEN_TOPOLOGY' || clsKind === 'DERIVED_TOPOLOGY') {
        // Topology helper only — never a fake physical discharge segment
        const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
        d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
        cls += ' tb-wire-topology';
      } else if (clsKind === 'VISUAL_HELPER') {
        const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
        d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
        cls += ' tb-wire-helper';
      } else {
        // UNKNOWN — dim topology cue only; do not imply physical join
        const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
        d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
        cls += ' tb-wire-topology';
      }
      if (physicalJoin && conf === 'CONFIRMED') cls += ' tb-conf-confirmed';
      else if (physicalJoin && conf.includes('HIGH')) cls += ' tb-conf-high';
      else if (conf.includes('AMBIG')) cls += ' tb-conf-ambiguous';
      const tip = physicalJoin
        ? `PHYSICAL_GEOMETRY · EXIT ▶◀ ENTRY · ${wire.confidence || 'physical'}${wire.distance != null ? ` · d=${wire.distance}` : ''}`
        : `${clsKind} · logical/control (not a physical belt join)`;
      html += `<path class="${cls}" d="${d}" data-conn-class="${clsKind}"><title>${escapeHtml(tip)}</title></path>`;
    });
    if (temp && temp.from && temp.to) {
      const dx = Math.max(40, Math.abs(temp.to.x - temp.from.x) * 0.45);
      const d = `M ${temp.from.x} ${temp.from.y} C ${temp.from.x + dx} ${temp.from.y}, ${temp.to.x - dx} ${temp.to.y}, ${temp.to.x} ${temp.to.y}`;
      html += `<path class="tb-wire tb-wire-temp tb-conn-visual_helper" d="${d}" data-conn-class="VISUAL_HELPER" />`;
    }
    svg.innerHTML = html;
    const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const areaNow = activeArea();
    perfRecord('transport.drawWires', t1 - t0, {
      wire_count: (areaNow?.wires || areaNow?.links || []).length || 0,
      node_count: (areaNow?.nodes || []).length || 0,
      temp: !!temp,
    });
  }

  /** Select a node. Pass { additive: true } for Ctrl/Meta toggle-select (Shift is connect, not select). */
  function selectNode(id, { additive } = {}) {
    if (isLiteRenderMode()) {
      selectLiteNode(id, { additive });
      return;
    }
    if (!id) {
      tb.selectedId = null;
      tb.selectedIds = [];
      tb.selectedDeviceId = null;
      renderInspector();
      renderScene();
      return;
    }
    if (additive) {
      const set = new Set(tb.selectedIds || []);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      tb.selectedIds = [...set];
      tb.selectedId = tb.selectedIds.includes(id) ? id : (tb.selectedIds[0] || null);
    } else {
      tb.selectedId = id;
      tb.selectedIds = [id];
    }
    tb.selectedDeviceId = null;
    renderInspector();
    renderScene();
  }

  function resetPeRoleUi() {
    PE_ROLE_ORDER.forEach((r) => {
      const el = $(`tb-insp-pe-role-${r}`);
      if (el) el.checked = false;
    });
    $('tb-insp-pe-roles-wrap')?.classList.add('hidden');
    $('tb-insp-dev-panel')?.classList.add('hidden');
    $('tb-insp-conv-panel')?.classList.remove('hidden');
  }

  function renderInspector() {
    const empty = $('tb-inspector-empty');
    const panel = $('tb-inspector');
    const area = activeArea();
    const n = area?.nodes.find((x) => x.id === tb.selectedId);
    if (!n) {
      empty?.classList.remove('hidden');
      panel?.classList.add('hidden');
      resetPeRoleUi();
      return;
    }
    empty?.classList.add('hidden');
    panel?.classList.remove('hidden');

    const meta = KIND_META[n.kind] || {};
    const dev = (n.devices || []).find((d) => d.id === tb.selectedDeviceId);
    const convPanel = $('tb-insp-conv-panel');
    const devPanel = $('tb-insp-dev-panel');

    if (dev) {
      // Device tag mode
      convPanel?.classList.add('hidden');
      devPanel?.classList.remove('hidden');
      const dm = KIND_META[dev.kind] || {};
      $('tb-insp-kind').textContent = `${dm.title || dev.kind} on ${n.label || n.conveyorTag || n.id}`;
      const hint = $('tb-insp-dev-hint');
      if (hint) {
        const hints = {
          photoeye: 'Buildable PE tags only (from Autogen IO / exit_pe). Blank = NO_PE. Set roles below (_P/_J/_F).',
          motor: 'Buildable M### / VFD### from IO map',
          estop: 'Buildable ES* from IO map',
          pws: 'Buildable EZPWS* / PWS* from IO map',
          encoder: 'Buildable ENC* from IO map',
        };
        hint.textContent = hints[dev.kind] || 'Only tags that Autogen will emit into the L5X.';
      }
      fillTagSelect($('tb-insp-dev-tag'), dev.kind, dev.tag || dev.name || '');
      const rolesWrap = $('tb-insp-pe-roles-wrap');
      if (rolesWrap) {
        const isPe = dev.kind === 'photoeye';
        rolesWrap.classList.toggle('hidden', !isPe);
        if (isPe) {
          const roles = new Set(ensurePeRoles(dev));
          PE_ROLE_ORDER.forEach((role) => {
            const el = $(`tb-insp-pe-role-${role}`);
            if (el) el.checked = roles.has(role);
          });
          const req = $('tb-insp-pe-role-required');
          if (req) req.classList.toggle('hidden', !dev.peRoleRequired);
        }
      }
      return;
    }

    // Conveyor mode
    convPanel?.classList.remove('hidden');
    devPanel?.classList.add('hidden');
    const convTag = (n.conveyorTag || n.label || '').trim() || 'P???';
    $('tb-insp-kind').textContent = `Conveyor ${convTag}`;
    if ($('tb-insp-label')) $('tb-insp-label').value = n.label || '';
    if ($('tb-insp-rotation')) $('tb-insp-rotation').textContent = `${Number(n.rotation || 0) % 360}°`;
    // Attached devices / relationships (presentation of canonical model)
    const attached = $('tb-insp-attached');
    if (attached) {
      const motors = (n.devices || []).filter((d) => d.kind === 'motor' && (d.tag || '').trim());
      const pes = (n.devices || []).filter((d) => d.kind === 'photoeye' && (d.tag || '').trim());
      const others = (n.devices || []).filter((d) => d.kind !== 'motor' && d.kind !== 'photoeye' && (d.tag || d.name || '').trim());
      const m0 = motors[0]?.tag || (n.motorsMeta && n.motorsMeta[0] && (n.motorsMeta[0].motor || n.motorsMeta[0].tag)) || '';
      const msTag = m0 ? `${String(convTag).replace(/_Conv$/i, '')}_MS` : '—';
      const vfd = n.vfdTag || motors.find((d) => /vfd/i.test(d.tag || '') || d.driveType === 'VFD')?.tag || 'none';
      const ups = getUpstreamTags(area, n.id);
      const lines = [
        `<div><span class="text-slate-500">Conveyor</span> <span class="mono text-cyan-300">${escapeHtml(convTag)}</span></div>`,
        `<div><span class="text-slate-500">Drive</span> <span class="mono text-amber-300">${escapeHtml(m0 || '—')}</span></div>`,
        `<div class="pl-2 text-[10px] text-slate-500">Motor Starter: <span class="mono text-slate-300">${escapeHtml(msTag)}</span> · VFD: <span class="mono text-slate-300">${escapeHtml(vfd || 'none')}</span></div>`,
        `<div><span class="text-slate-500">Photoeyes</span> <span class="mono text-emerald-300">${pes.length ? pes.map((p) => escapeHtml(p.tag)).join(', ') : '—'}</span></div>`,
        `<div><span class="text-slate-500">Upstream</span> <span class="mono text-slate-300">${ups.length ? ups.map(escapeHtml).join(', ') : '—'}</span></div>`,
        `<div><span class="text-slate-500">Downstream</span> <span class="mono text-slate-300">${escapeHtml(n.terminal ? 'END' : (n.downstream || '—'))}</span></div>`,
      ];
      if (others.length) {
        lines.push(`<div><span class="text-slate-500">Other</span> <span class="mono text-slate-400">${others.map((d) => escapeHtml(d.tag || d.name)).join(', ')}</span></div>`);
      }
      if ((n.ambiguousInbound || []).length) {
        lines.push(`<div class="text-amber-400/90 text-[10px]">Ambiguous inbound mates: ${n.ambiguousInbound.length} (review connections)</div>`);
      }
      attached.innerHTML = lines.join('');
    }
    const upEl = $('tb-insp-upstream');
    if (upEl) {
      const ups = getUpstreamTags(area, n.id);
      upEl.textContent = ups.length ? ups.join(', ') : '—';
    }
    fillDownstreamSelect($('tb-insp-downstream'), n);
    const term = $('tb-insp-terminal');
    if (term) term.checked = !!n.terminal;
    const mergeWrap = $('tb-insp-merge-wrap');
    if (mergeWrap) {
      const showMerge = !!(meta.isMerge || n.asMerge);
      mergeWrap.classList.toggle('hidden', !showMerge);
      const laneSel = $('tb-insp-merge-lanes');
      const lanes = Math.max(2, Number(n.inPorts) || 2);
      if (laneSel && showMerge) laneSel.value = String(lanes);
      if (showMerge) {
        fillTagSelect($('tb-insp-merge-pe-a'), 'photoeye', n.pe_a || '');
        fillTagSelect($('tb-insp-merge-pe-b'), 'photoeye', n.pe_b || '');
        fillTagSelect($('tb-insp-merge-jam-pe'), 'photoeye', n.jam_pe || '');
        const peCWrap = $('tb-insp-merge-pe-c-wrap');
        if (peCWrap) {
          peCWrap.classList.toggle('hidden', lanes < 3);
          if (lanes >= 3) fillTagSelect($('tb-insp-merge-pe-c'), 'photoeye', n.pe_c || '');
        }
        const allow = $('tb-insp-merge-allow-pe');
        if (allow) allow.checked = !!n.allow_undefined_pe;
      }
    }

    const spiralWrap = $('tb-insp-spiral-wrap');
    if (spiralWrap) {
      spiralWrap.classList.toggle('hidden', !meta.isSpiral);
      if (meta.isSpiral) {
        const motors = normalizeSpiralMotors(n);
        const countSel = $('tb-insp-spiral-motors');
        if (countSel) countSel.value = String(n.motorCount || SPIRAL_MOTOR_DEFAULT);
        const list = $('tb-insp-spiral-motor-list');
        if (list) {
          list.innerHTML = motors
            .map((tag, idx) => {
              const id = `tb-insp-spiral-motor-${idx}`;
              return `<div>
                <label class="text-[10px] text-slate-500" for="${id}">Motor ${idx + 1}</label>
                <div class="tb-combo mt-0.5">
                  <select id="${id}" data-tb-combo="1" data-spiral-motor="${idx}"
                    class="w-full bg-slate-900 border border-slate-700 rounded-lg text-[10px] px-1.5 py-1 text-amber-300"></select>
                </div>
              </div>`;
            })
            .join('');
          motors.forEach((tag, idx) => {
            const sel = $(`tb-insp-spiral-motor-${idx}`);
            if (!sel) return;
            fillTagSelect(sel, 'motor', tag || '');
            sel.onchange = () => {
              const a2 = activeArea();
              const n2 = a2?.nodes.find((x) => x.id === tb.selectedId);
              if (!n2 || !KIND_META[n2.kind]?.isSpiral) return;
              normalizeSpiralMotors(n2);
              n2.motors[idx] = sel.value || '';
              save();
              render();
              status(`Spiral motor ${idx + 1} → ${sel.value || '(none)'}`);
            };
          });
        }
      }
    }

    const convWrap = $('tb-insp-conv-wrap');
    if (convWrap) convWrap.classList.toggle('hidden', !isConv(n.kind));

    const sel = $('tb-insp-conveyor');
    if (sel && isConv(n.kind)) {
      const opts = conveyorOptions();
      const paintConv = (filter) => {
        const q = String(filter || '').trim().toUpperCase();
        const hits = opts.filter((t) => !q || t.toUpperCase().includes(q));
        let html = `<option value="">— select P### from RUN —</option>`;
        hits.slice(0, 200).forEach((c) => {
          html += `<option value="${escapeHtml(c)}" ${c === n.conveyorTag ? 'selected' : ''}>${escapeHtml(c)}</option>`;
        });
        if (n.conveyorTag && !hits.includes(n.conveyorTag)) {
          html += `<option value="${escapeHtml(n.conveyorTag)}" selected>${escapeHtml(n.conveyorTag)} (custom)</option>`;
        }
        sel.innerHTML = html;
      };
      paintConv('');
      const host = sel.closest('.tb-combo');
      if (host) {
        host.classList.add('tb-combo');
        let input = host.querySelector('input.tb-combo-input');
        if (!input) {
          input = document.createElement('input');
          input.type = 'text';
          input.className = 'tb-combo-input mb-1';
          input.autocomplete = 'off';
          host.insertBefore(input, sel);
        }
        input.placeholder = 'Type P### to filter…';
        input.value = '';
        sel.style.display = '';
        input.oninput = () => paintConv(input.value);
        input.onkeydown = (e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          const q = input.value.trim().toUpperCase();
          const hits = opts.filter((t) => !q || t.toUpperCase().includes(q));
          const pick = hits.find((t) => t.toUpperCase() === q) || hits[0] || '';
          if (!pick) return;
          n.conveyorTag = pick;
          if (!n.label || KIND_META[n.kind]?.title === n.label) n.label = pick;
          input.value = '';
          paintConv('');
          sel.value = pick;
          save();
          render();
        };
      }
    }

    const list = $('tb-insp-devices');
    if (list) {
      const devices = n.devices || [];
      if (!devices.length) {
        list.innerHTML = `<div class="text-[10px] text-slate-600">None yet — drop a device on this conveyor or click Attach.</div>`;
      } else {
        list.innerHTML = devices
          .map((d, i) => {
            const label = d.tag || d.name || d.kind;
            const badges = d.kind === 'photoeye'
              ? peRoleBadgesHtml(ensurePeRoles(d), { required: !!d.peRoleRequired })
              : '';
            return `<div class="flex items-center gap-2 text-[10px] bg-slate-900/80 border border-slate-800 rounded-lg px-2 py-1 cursor-pointer hover:border-fuchsia-700/50" data-sel-dev="${escapeHtml(d.id)}">
              ${kindIconHtml(d.kind)}
              <span class="flex-1 truncate">${escapeHtml(label)}</span>
              ${badges}
              <button type="button" data-rm-dev="${i}" class="text-slate-600 hover:text-red-400"><i class="fa-solid fa-xmark"></i></button>
            </div>`;
          })
          .join('');
        list.querySelectorAll('[data-sel-dev]').forEach((row) => {
          row.addEventListener('click', (ev) => {
            if (ev.target.closest('[data-rm-dev]')) return;
            tb.selectedDeviceId = row.dataset.selDev;
            render();
          });
        });
        list.querySelectorAll('[data-rm-dev]').forEach((btn) => {
          btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            const i = Number(btn.dataset.rmDev);
            const removed = n.devices[i];
            n.devices.splice(i, 1);
            if (removed && tb.selectedDeviceId === removed.id) tb.selectedDeviceId = null;
            save();
            render();
          });
        });
      }
    }

    $('tb-insp-add-row')?.classList.add('hidden');
    refreshAttachKindOptions();
    // Prefill attach-row tag list for default kind
    const addKind = $('tb-insp-device-kind')?.value || 'motor';
    fillTagSelect($('tb-insp-device-tag-new'), addKind, '');

    // Gate K — geometry diagnostic panel when Advanced geometry debug is on
    const geomHost = $('tb-insp-geom-diag');
    const geomBody = $('tb-insp-geom-diag-body');
    const debugOn = tb.viewMode === 'geom-debug' || !!tb.layers?.physical;
    if (geomHost) {
      geomHost.classList.toggle('hidden', !debugOn);
      if (debugOn && geomBody) {
        try {
          const diag = buildGeometryDiagnostic(n, area);
          geomBody.textContent = JSON.stringify({
            run: diag.run,
            rendered: diag.rendered,
            hitbox: diag.hitbox,
            upstream: diag.upstream,
            downstream: diag.downstream,
            provenance: diag.provenance,
          }, null, 2);
        } catch (err) {
          geomBody.textContent = `diagnostic error: ${err?.message || err}`;
        }
      }
    }
    $('tb-insp-geom-export')?.addEventListener('click', () => {
      exportGeometryDiagnostic(n, area);
    });
  }

  /** Merge nodes: Attach motor/ES/PWS/ENC only — PEs use AOI fields above. */
  function refreshAttachKindOptions() {
    const sel = $('tb-insp-device-kind');
    const a = activeArea();
    const n = a?.nodes.find((x) => x.id === tb.selectedId);
    if (!sel) return;
    const isMerge = !!(n && KIND_META[n.kind]?.isMerge);
    const kinds = isMerge
      ? [
          ['motor', 'Motor'],
          ['estop', 'E-Stop'],
          ['pws', 'Power Supply'],
          ['encoder', 'Encoder'],
        ]
      : [
          ['motor', 'Motor'],
          ['estop', 'E-Stop'],
          ['pws', 'Power Supply'],
          ['encoder', 'Encoder'],
          ['photoeye', 'Photoeye'],
        ];
    const cur = sel.value;
    sel.innerHTML = kinds
      .map(([v, lab]) => `<option value="${v}">${lab}</option>`)
      .join('');
    if (kinds.some(([v]) => v === cur)) sel.value = cur;
    else sel.value = kinds[0][0];
  }

  function addNode(kind, x, y, ontoConv) {
    const area = activeArea();
    if (!area) return;
    const meta = KIND_META[kind];
    if (!meta) return;

    if (!isConv(kind)) {
      // Device: must attach to a conveyor
      const target = ontoConv || null;
      if (!target || !isConv(target.kind)) {
        status('Drop devices onto a conveyor piece (or select one and use Attach).');
        return;
      }
      // Merge AOI PEs are inspector-only — avoid duplicate PE chips on the merge node
      if (KIND_META[target.kind]?.isMerge && kind === 'photoeye') {
        tb.selectedId = target.id;
        tb.selectedDeviceId = null;
        save();
        render();
        status('Merge PEs: use Lane A / Lane B / Jam PE in the inspector (not a Photoeye chip).');
        return;
      }
      if (!target.devices) target.devices = [];
      const newDev = {
        id: uid('dev'),
        kind,
        name: `${meta.title}_${target.devices.length + 1}`,
        tag: '',
      };
      if (kind === 'photoeye') {
        newDev.roles = inferPeRoles('');
        newDev.rolesManual = false;
      }
      target.devices.push(newDev);
      tb.selectedId = target.id;
      tb.selectedDeviceId = newDev.id; // open tag picker for this device
      save();
      render();
      status(`Attached ${meta.title} — pick a buildable ${kind} tag`);
      return;
    }

    // Don't call prompt() inside drop handlers — Electron/Chromium often cancels the drop.
    // Merges default to 2:1; spirals default to 3 motors (change in inspector).
    let inPorts = 1;
    let label = meta.title;
    if (meta.isMerge) {
      inPorts = 2;
      label = 'Merge 2:1';
    }

    const node = {
      id: uid('node'),
      kind,
      label,
      conveyorTag: '',
      x: Math.max(20, x),
      y: Math.max(20, y),
      devices: [],
      rotation: 0,
      inPorts,
      downstream: '',
      terminal: false,
      asMerge: false,
      safetyZone: (tb.buildContext && tb.buildContext.safetyZone) || '',
      controlPanel: '', // presentation / organizational only — not PLC ownership
    };
    if (meta.isSpiral) {
      node.motorCount = SPIRAL_MOTOR_DEFAULT;
      node.motors = Array(SPIRAL_MOTOR_DEFAULT).fill('');
      label = `Spiral (${SPIRAL_MOTOR_DEFAULT} motors)`;
      node.label = label;
    }
    // Straight / 90° belts: auto-attach one motor chip (user still picks M### / VFD###).
    // Merge / Spiral use their own motor / PE inspectors — do not auto-add here.
    let autoMotorId = null;
    if (meta.isConv && !meta.isMerge && !meta.isSpiral) {
      autoMotorId = uid('dev');
      node.devices.push({
        id: autoMotorId,
        kind: 'motor',
        tag: '',
        name: '',
      });
    }
    const prevSelectedId = tb.selectedId;
    area.nodes.push(node);
    invalidateNodeIndex(area);
    // Sequential Build: auto-connect previously selected conveyor → new one
    if (
      tb.autoConnectNew &&
      meta.isConv &&
      !meta.isMerge &&
      prevSelectedId &&
      prevSelectedId !== node.id
    ) {
      const prev = area.nodes.find((x) => x.id === prevSelectedId);
      if (prev && isConv(prev.kind) && !KIND_META[prev.kind]?.isMerge) {
        const toPort = pickEntrancePort(area, node);
        area.wires = (area.wires || []).filter((w) => w.from !== prev.id);
        area.wires.push({ id: uid('wire'), from: prev.id, to: node.id, toPort });
        prev.downstream = (node.conveyorTag || '').trim();
        prev.terminal = false;
      }
    }
    tb.selectedId = node.id;
    tb.selectedDeviceId = autoMotorId;
    syncDownstreamFromWires(area);
    save();
    render();

    if (meta.isMerge) {
      status('Added Merge 2:1 — choose lane count…');
      setTimeout(async () => {
        const raw = await askText(
          'Merge lanes',
          'How many inbound lanes? (2, 3, or 4)',
          '2'
        );
        if (raw === null) return;
        const lanes = Math.min(4, Math.max(2, parseInt(raw, 10) || 2));
        const a2 = activeArea();
        const n2 = a2?.nodes.find((x) => x.id === node.id);
        if (!n2) return;
        n2.inPorts = lanes;
        n2.label = `Merge ${lanes}:1`;
        save();
        render();
        status(`Merge set to ${lanes}:1 — wire each green entrance`);
      }, 50);
    } else if (meta.isSpiral) {
      status(`Added Spiral — set ${SPIRAL_MOTOR_DEFAULT} motors (M### / VFD###) in the inspector`);
    } else if (autoMotorId) {
      status(`Added ${meta.title} + motor — bind P### and pick motor tag (M### / VFD###)`);
    } else {
      status(`Added ${meta.title} — bind a controller conveyor in the inspector`);
    }
  }

  function connect(fromId, toId, toPort) {
    const area = activeArea();
    if (!area || fromId === toId) {
      if (fromId === toId) status('Self-connection rejected.');
      return;
    }
    const from = area.nodes.find((n) => n.id === fromId);
    const to = area.nodes.find((n) => n.id === toId);
    if (!from || !to || !isConv(from.kind) || !isConv(to.kind)) {
      status('Only conveyor exit → conveyor entrance links are allowed.');
      return;
    }
    const port = toPort || pickEntrancePort(area, to);
    if (area.wires.some((w) => w.from === fromId && w.to === toId && (w.toPort || 'in') === port)) {
      status('Already connected.');
      return;
    }
    // Single outbound downstream per source (canonical model)
    area.wires = area.wires.filter((w) => w.from !== fromId);
    // One wire per merge entrance
    if (port !== 'in') {
      area.wires = area.wires.filter((w) => !(w.to === toId && (w.toPort || 'in') === port));
    }
    area.wires.push({ id: uid('wire'), from: fromId, to: toId, toPort: port });
    from.downstream = (to.conveyorTag || '').trim();
    from.terminal = false;
    markValidationDirty();
    save();
    render();
    status(`Connected ${from.label || fromId} → ${to.label || toId} (${port})`);
    maybeConfirmMerge(to);
  }

  function bindToolbar() {
    // Toolbar first — never gated on canvas existing (fixes silent New Area / Build POC)
    $('tb-mode-lite')?.addEventListener('click', () => setRenderMode('lite'));
    $('tb-mode-detailed')?.addEventListener('click', () => setRenderMode('detailed'));
    $('tb-adv-mode-lite')?.addEventListener('click', () => setRenderMode('lite'));
    $('tb-adv-mode-detailed')?.addEventListener('click', () => setRenderMode('detailed'));
    $('tb-style-raw')?.addEventListener('click', () => setSchematicStyle('raw'));
    $('tb-style-readable')?.addEventListener('click', () => setSchematicStyle('readable'));
    $('tb-style-packed')?.addEventListener('click', () => setSchematicStyle('packed'));
    $('tb-show-relationships')?.addEventListener('change', (e) => {
      setShowRelationships(!!e.target.checked);
    });
    const rebuildActive = async () => {
      status('Rebuilding Transportation from Active RUN…');
      if (typeof window.ensureTransportHydrated === 'function') {
        const r = await window.ensureTransportHydrated({
          force: true,
          reason: 'engineer rebuild',
        });
        if (r?.ok) status(r.summary || 'Transportation rebuilt from Active RUN');
        else status(`Rebuild failed: ${r?.error || r?.reason || 'unknown'}`);
        try { if (typeof window.updateTransportActiveProjectUi === 'function') window.updateTransportActiveProjectUi(r); } catch (_) { /* ignore */ }
        renderScene();
        return;
      }
      if (typeof window.transportAutoBuildFromRun === 'function') {
        await window.transportAutoBuildFromRun({ silent: false, rebuild: true });
      } else {
        status('Active Project hydrate unavailable — relaunch Site Forge');
      }
    };
    $('tb-rebuild-active-run')?.addEventListener('click', () => {
      rebuildActive().catch((err) => status(`Rebuild error: ${err?.message || err}`));
    });
    $('tb-empty-retry')?.addEventListener('click', () => {
      rebuildActive().catch((err) => status(`Retry error: ${err?.message || err}`));
    });

    $('tb-area-select')?.addEventListener('change', (e) => {
      const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      tb.activeAreaId = e.target.value;
      tb.selectedId = null;
      // Drop prior Area pan — do not retain another Area's scroll offset
      save();
      // Area switch: scene + inspector only; topology/validation stay lazy
      refreshAreaSelect();
      renderScene();
      renderInspector();
      perfRecord('transport.areaSwitch', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {
        area: activeArea()?.name || '',
        node_count: (activeArea()?.nodes || []).length,
      });
      // SELECT AREA → FIT/CENTER visible conveyance on X and Y
      requestAnimationFrame(() => {
        try {
          fitArea();
          status(`Area Top-Centered · ${(activeArea()?.name || '').trim() || '—'}`);
        } catch (_) { /* ignore */ }
      });
    });

    $('tb-area-new')?.addEventListener('click', async () => {
      try {
        tb.suppressDefaultArea = false;
        ensureDefaultArea();
        const engN = (tb.areas || []).filter((a) => !isDefaultArea(a)).length;
        const def = `Area_${engN + 1}`;
        const name = await askText(
          'Create Area',
          'Engineer Area name (operational conveyor grouping — not Default Area, not a Safety Zone):',
          def
        );
        if (name === null || !(String(name).trim())) return;
        const areaName = String(name).trim();
        if (isDefaultAreaName(areaName)) {
          status(`“${areaName}” is reserved for the Default Area ownership bucket`);
          return;
        }
        if ((tb.areas || []).some((a) => String(a.name || '').trim().toLowerCase() === areaName.toLowerCase())) {
          status(`Area “${areaName}” already exists`);
          return;
        }
        const existing = listSafetyZoneNames();
        // Seed from current Area/layout name (ORNCCP2_Area → ORNCCP2_ESZoneN). Suggestion only.
        const zoneHint = nextSafetyZoneName(areaName);
        const zonePrompt = existing.length
          ? `Optional Safety Zone default for conveyors in “${areaName}”.\n`
            + `Suggested: ${zoneHint}\n`
            + `Existing: ${existing.slice(0, 8).join(', ')}${existing.length > 8 ? '…' : ''}\n`
            + 'Pick an existing name, or type a new Safety Zone name to create it.\n'
            + 'Area ≠ Safety Zone — engineer may edit; not permanently derived from Area.'
          : `Optional Safety Zone default for conveyors in “${areaName}” (suggested from Area name).\n`
            + 'Area ≠ Safety Zone — conveyor-level value remains authoritative and editable.';
        const zoneIn = await askText('Safety Zone', zonePrompt, zoneHint);
        if (zoneIn === null) return; // cancelled
        const defaultZone = String(zoneIn || '').trim();
        let zoneOk = '';
        if (defaultZone) {
          // Gate E — immediate Safety Build handoff with immutable szone_* source_id
          // PD-0040 — reject duplicate name that would move an existing zone
          const ensured = ensureSafetyZone(defaultZone, { areaRef: areaName, forceHandoff: true });
          if (!ensured) {
            await showInfo(
              'Safety Zone name in use',
              `“${defaultZone}” already belongs to another Area — Area will be created without that Safety Zone default.`,
            );
          } else {
            zoneOk = defaultZone;
          }
        }
        const a = {
          id: uid('area'),
          name: areaName,
          nodes: [],
          wires: [],
          isDefault: false,
          defaultArea: false,
          provenance: 'ENGINEER',
          defaultSafetyZone: zoneOk,
        };
        tb.areas.push(a);
        tb.activeAreaId = a.id;
        tb.selectedId = null;
        tb.selectedDeviceId = null;
        if (zoneOk) {
          tb.buildContext = tb.buildContext || {};
          tb.buildContext.areaId = a.id;
          tb.buildContext.areaName = a.name;
          tb.buildContext.safetyZone = zoneOk;
        }
        save();
        render();
        const counts = transportOwnershipCounts();
        status(
          `Engineer Area “${a.name}” ready`
          + (zoneOk ? ` · Safety Zone “${zoneOk}”` : '')
          + ` · Default Area ${counts.default} · engineer ${counts.engineer_total}`
        );
      } catch (err) {
        status(`New area error: ${err?.message || err}`);
        try { await showInfo('New area failed', String(err?.message || err)); } catch (_) { /* ignore */ }
      }
    });

    $('tb-area-rename')?.addEventListener('click', async () => {
      const a = activeArea();
      if (!a) return;
      if (isDefaultArea(a)) {
        status('Default Area cannot be renamed — it is the Site Forge ownership bucket');
        return;
      }
      const name = await askText('Rename area', 'New area name:', a.name);
      if (name === null || !(name || '').trim()) return;
      const next = name.trim();
      if (isDefaultAreaName(next)) {
        status(`“${next}” is reserved for Default Area`);
        return;
      }
      a.name = next;
      a.provenance = 'ENGINEER';
      save();
      render();
      status(`Renamed area to “${a.name}”`);
    });

    function resetPeRoleCheckboxes() {
      PE_ROLE_ORDER.forEach((r) => {
        const el = $(`tb-insp-pe-role-${r}`);
        if (el) el.checked = false;
      });
    }

    async function deleteActiveArea() {
      const a = activeArea();
      if (!a) return;
      if (isDefaultArea(a)) {
        status('Default Area cannot be deleted — it is the Site Forge ownership bucket');
        return;
      }
      const n = ownedTransportNodes(a).length;
      const ok = await askYesNo(
        'Delete area',
        n
          ? `Delete engineer Area “${a.name}”?\n\n${n} conveyor(s) return to Default Area (nothing disappears).`
          : `Delete empty engineer Area “${a.name}”?`,
      );
      if (!ok) return;
      const returned = returnAreaMembersToDefault(a);
      tb.areas = tb.areas.filter((x) => x.id !== a.id);
      const def = ensureDefaultArea();
      tb.activeAreaId = def?.id || tb.areas[0]?.id || null;
      tb.selectedId = null;
      tb.selectedDeviceId = null;
      resetPeRoleCheckboxes();
      ensureArea();
      save();
      render();
      const counts = transportOwnershipCounts();
      status(
        `Deleted area “${a.name}”`
        + (returned ? ` · ${returned} returned to Default Area` : '')
        + ` · Default ${counts.default} · engineer ${counts.engineer_total}`
      );
    }
    $('tb-area-delete')?.addEventListener('click', () => {
      deleteActiveArea().catch((err) => status(`Delete area error: ${err?.message || err}`));
    });
    $('tb-area-delete-btn')?.addEventListener('click', () => {
      deleteActiveArea().catch((err) => status(`Delete area error: ${err?.message || err}`));
    });

    $('tb-clear-canvas')?.addEventListener('click', async () => {
      const a = activeArea();
      if (!a) return;
      const ok = await askYesNo('Clear canvas', 'Clear all nodes and wires in this area?');
      if (!ok) return;
      a.nodes = [];
      a.wires = [];
      tb.selectedId = null;
      tb.selectedDeviceId = null;
      resetPeRoleCheckboxes();
      save();
      render();
      status('Canvas cleared — PE roles reset');
    });

    // Build POC kept as internal helper (toolbar button removed) — Apply is the main path
    $('tb-build-poc')?.addEventListener('click', async () => {
      const payload = {
        version: 1,
        exportedAt: new Date().toISOString(),
        areas: tb.areas,
      };
      status('Running Transport Build POC…');
      try {
        const api = window.fortnaAPI || window.api;
        if (!api?.transportBuildPoc) {
          await showInfo(
            'Build POC',
            'Needs the desktop Site Forge app (Electron IPC).\n\nGraph is still available via Export JSON.'
          );
          status('Build POC needs the desktop app (IPC). Use Export JSON.');
          return;
        }
        const res = await api.transportBuildPoc({ graph: payload });
        if (!res?.ok && !res?.success) {
          await showInfo('Build POC failed', res?.error || res?.message || 'unknown error');
          status(`POC failed: ${res?.error || res?.message || 'unknown'}`);
          return;
        }
        tb.lastPoc = res;
        const totals = res.totals || {};
        const exportsDir = res.exports_dir || 'C:\\dev\\worktree\\FortnaPlus\\exports\\transport-poc';
        const detail = [
          res.summary || '',
          '',
          `Areas: ${totals.areas ?? '—'}`,
          `Conveyors: ${totals.nodes ?? '—'}`,
          `Merges: ${totals.merges ?? '—'} → Autogen rows: ${res.merges_2to1_count ?? '—'}`,
          `Wires: ${totals.wires ?? '—'}`,
          `Devices: ${totals.devices ?? '—'}`,
          '',
          `Exports folder:\n${exportsDir}`,
          res.report_path ? `Report: ${res.report_path}` : '',
          res.autogen_merges_path ? `Merges fragment: ${res.autogen_merges_path}` : '',
          '',
          'Next: Apply to Autogen → area names become Autogen areas,',
          'bound P### get that main_area (simple transport + merges).',
        ].filter((l) => l !== undefined).join('\n');
        await showInfo(
          'Transport Build POC OK',
          'Wrote report under exports/transport-poc.\nDoes NOT change Autogen until you Apply.\n\nAreas + simple transport + merges all Apply together.',
          detail
        );
        status(`POC OK — files in exports/transport-poc — click Apply to Autogen`);
        if (exportsDir && api.openPath) {
          try { await api.openPath(exportsDir); } catch (_) { /* ignore */ }
        }
        const doApply = await askYesNo(
          'Apply to Autogen workbook?',
          `Push Transport areas + bound conveyors`
            + ((res.merges_2to1_count || 0) > 0 ? ` + ${res.merges_2to1_count} merge(s)` : '')
            + ` into PLC Autogen now?\n\n`
            + `Rename areas first if you want Autogen program names to match (e.g. Induct / Shipping).`
        );
        if (doApply) {
          await applyMergesToAutogenUi();
        }
      } catch (err) {
        await showInfo('Build POC error', String(err?.message || err));
        status(`POC error: ${err?.message || err}`);
      }
    });

    $('tb-connect-mode')?.addEventListener('click', () => toggleConnectMode());
    $('tb-auto-connect')?.addEventListener('change', (e) => {
      tb.autoConnectNew = !!e.target.checked;
      save();
      status(tb.autoConnectNew
        ? 'Auto Connect New ON — each new conveyor links from the selected one'
        : 'Auto Connect New OFF');
    });
    $('tb-inv-filter')?.addEventListener('input', () => renderInventoryPanel());

    $('tb-apply-autogen')?.addEventListener('click', async () => {
      await applyMergesToAutogenUi();
    });

    $('tb-wizard')?.addEventListener('click', () => openTransportWizard());
    $('tb-wiz-close')?.addEventListener('click', () => closeTransportWizard());
    $('tb-wiz-back')?.addEventListener('click', () => wizardNav(-1));
    $('tb-wiz-next')?.addEventListener('click', () => wizardNav(1));

    $('tb-open-exports')?.addEventListener('click', async () => {
      const api = window.fortnaAPI || window.api;
      const dir =
        tb.lastPoc?.exports_dir ||
        'C:\\dev\\worktree\\FortnaPlus\\exports\\transport-poc';
      status(`Opening ${dir}`);
      if (api?.openPath) {
        try { await api.openPath(dir); } catch (err) {
          await showInfo('Open exports', String(err?.message || err));
        }
      } else {
        await showInfo('Exports folder', dir);
      }
    });
  }

  /** Wires connect flow only — each node still needs a P### (or placeholder) tag. */
  function ensurePlaceholderConveyorTags() {
    let made = 0;
    tb.areas.forEach((area) => {
      let i = 1;
      // Placeholder conveyor tags only — do NOT sanitize/purge engineer area names
      // (Area_1lksadfj and similar intentional names must survive Apply).
      const base = String(area.name || 'TB').replace(/[^\w]+/g, '_') || 'TB';
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        if ((n.conveyorTag || '').trim()) return;
        // Placeholder until engineer binds a real RUN tag — still emits area programs
        while ((area.nodes || []).some((x) => (x.conveyorTag || '').toUpperCase() === `${base}_C${i}`.toUpperCase())) {
          i += 1;
        }
        n.conveyorTag = `${base}_C${i}`;
        n.placeholderTag = true;
        if (!n.label || KIND_META[n.kind]?.title === n.label || /^Merge /i.test(n.label || '')) {
          if (!KIND_META[n.kind]?.isMerge) n.label = n.conveyorTag;
        }
        // Missing AOI PE placeholders on merges
        if (KIND_META[n.kind]?.isMerge) {
          if (!n.pe_a) n.pe_a = '';
          if (!n.pe_b) n.pe_b = '';
          n.allow_undefined_pe = n.allow_undefined_pe || false;
        }
        i += 1;
        made += 1;
      });
    });
    if (made) {
      save();
      render();
      status(`Assigned ${made} placeholder tag(s) (e.g. Area_C1) — replace with real P### when known`);
    }
    return made;
  }

  /**
   * Canonical Apply payload — topology + Area/ES/PE/relationships only.
   * Physical/debug presentation fields (pathCanvas, view, layers, presentationOffset)
   * are intentionally excluded so render state cannot affect Autogen.
   */
  function buildCanonicalApplyGraph() {
    (tb.areas || []).forEach((area) => {
      syncWiresFromDownstream(area);
      syncDownstreamFromWires(area);
    });
    const areas = (tb.areas || []).map((area) => ({
      id: area.id,
      name: area.name || '',
      isDefault: !!isDefaultArea(area),
      defaultArea: !!isDefaultArea(area),
      defaultSafetyZone: area.defaultSafetyZone || '',
      nodes: (area.nodes || [])
        // Presentation-only displayContext neighbors never enter Autogen/workbook.
        .filter((n) => !n.displayContext && n.plcOwned !== false)
        .map((n) => {
        const devices = (n.devices || []).map((d) => {
          // Only RUN-explicit or engineer-confirmed PE roles go to Autogen
          let roles = [];
          if (d.kind === 'photoeye') {
            if (d.rolesManual && Array.isArray(d.roles)) {
              roles = d.roles.filter((r) => PE_ROLE_APPLY.includes(r));
            } else if (!d.peRoleRequired) {
              roles = (inferPeRoles(d.tag || d.name || '')).filter((r) => PE_ROLE_APPLY.includes(r));
            }
            // peRoleRequired / none / other → no AOI roles emitted
          }
          return {
            id: d.id,
            kind: d.kind,
            tag: d.tag || d.name || '',
            name: d.name || d.tag || '',
            roles,
            rolesManual: !!d.rolesManual,
            peRoleRequired: !!d.peRoleRequired,
            peRoleProvenance: d.peRoleProvenance || undefined,
            driveType: d.driveType || undefined,
          };
        });
        return {
          id: n.id,
          kind: n.kind,
          label: n.label || '',
          conveyorTag: n.conveyorTag || '',
          downstream: n.downstream || '',
          terminal: !!n.terminal,
          asMerge: !!n.asMerge,
          mergeConfirmed: !!n.mergeConfirmed,
          mergeDetected: !!n.mergeDetected,
          mergeGenSupported: n.mergeGenSupported,
          inPorts: n.inPorts,
          safetyZone: n.safetyZone || '',
          piArea: n.piArea || '',
          provenance: n.provenance || undefined,
          areaRequired: !!n.areaRequired,
          esZoneRequired: !!n.esZoneRequired,
          pe_a: n.pe_a || '',
          pe_b: n.pe_b || '',
          pe_c: n.pe_c || '',
          jam_pe: n.jam_pe || '',
          allow_undefined_pe: !!n.allow_undefined_pe,
          devices,
          placeholderTag: !!n.placeholderTag,
          // Presentation-only CURVE angle override (not PLC topology)
          curveDisplayAngle: n.curveDisplayAngle != null ? n.curveDisplayAngle : undefined,
        };
      }),
      wires: (area.wires || []).map((w) => ({
        id: w.id,
        from: w.from,
        to: w.to,
        toPort: w.toPort || 'in',
      })),
    }));
    // Engineer Transportation Safety Zone assignments are authoritative.
    // Build SafetyZone IR: zone → area + conveyors[] (device membership resolved later from RUN).
    const zoneMap = new Map(); // name → { name, area, conveyors: [] }
    (areas || []).forEach((area) => {
      const aname = area.name || '';
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        const tag = String(n.conveyorTag || '').trim();
        const zname = String(n.safetyZone || '').trim();
        if (!zname || !tag) return;
        if (!zoneMap.has(zname)) {
          zoneMap.set(zname, { name: zname, area: aname, conveyors: [], members: [] });
        }
        const z = zoneMap.get(zname);
        if (!z.area && aname) z.area = aname;
        if (!z.conveyors.includes(tag)) z.conveyors.push(tag);
      });
    });
    // Also include named zones with no conveyors yet (engineer-created)
    (tb.safetyZones || []).forEach((z) => {
      const nm = String(z.name || '').trim();
      if (!nm) return;
      if (!zoneMap.has(nm)) {
        zoneMap.set(nm, { name: nm, area: '', conveyors: [], members: [] });
      }
    });
    const safetyBuildZones = [...zoneMap.values()];

    return {
      version: 1,
      exportedAt: new Date().toISOString(),
      applyMode: 'canonical',
      areas,
      safetyZones: (tb.safetyZones || []).map((z) => ({
        id: z.id,
        name: z.name || '',
      })).concat(
        safetyBuildZones
          .filter((z) => !(tb.safetyZones || []).some((t) => t.name === z.name))
          .map((z) => ({ id: z.name, name: z.name }))
      ),
      safetyBuild: {
        zones: safetyBuildZones,
        source: 'transport_engineer',
      },
      activeAreaId: tb.activeAreaId,
    };
  }

  function setWorkflowStep(step, { done } = {}) {
    if (!tb.workflow) tb.workflow = {};
    if (done) tb.workflow[step] = true;
    document.querySelectorAll('#tb-workflow-strip .tb-wf-step').forEach((el) => {
      const k = el.getAttribute('data-wf');
      el.classList.toggle('tb-wf-done', !!tb.workflow[k] && k !== step);
      el.classList.toggle('tb-wf-active', k === step);
    });
  }

  async function applyMergesToAutogenUi() {
    // Persistence guard: engineer canvas is authoritative. Apply serializes only —
    // never clear localStorage, never rebuild from RUN, never replace tb.areas.
    const areasBefore = (tb.areas || []).map((a) => ({
      id: a.id,
      name: a.name,
      n: (a.nodes || []).length,
    }));
    const hashBefore = canonicalTransportHash();
    tb.applyingAutogen = true;
    try {
      flushAreaAssignPersist();
      save(); // persist engineer edits before serialization
      ensurePlaceholderConveyorTags();
      const graph = buildCanonicalApplyGraph();
      // Empty engineer Areas must still travel in the graph (even with 0 bound tags)
      const graphAreaNames = (graph.areas || []).map((a) => (a.name || '').trim()).filter(Boolean);
      if (areasBefore.length && graphAreaNames.length < areasBefore.filter((a) => a.name).length) {
        status('Apply warning: canonical graph dropped an Area name — check unbound filters');
      }
      status('Applying Transport → Autogen workbook (canonical topology only)…');
      setWorkflowStep('apply');
      const applyBtn = document.querySelector('#tb-apply-autogen, [data-tb-apply]');
      const fb = window.sfActionFeedback;
      fb?.begin(applyBtn, 'APPLYING…');
      let res;
      if (typeof window.applyTransportMergesToAutogen === 'function') {
        res = await window.applyTransportMergesToAutogen({ graph });
      } else {
        const api = window.fortnaAPI || window.api;
        if (!api?.transportApplyAutogen) {
          fb?.fail(applyBtn, 'Desktop IPC missing');
          await showInfo('Apply to Autogen', 'Desktop IPC missing — restart Site Forge.');
          return;
        }
        res = await api.transportApplyAutogen({ graph });
      }
      if (!res?.ok) {
        fb?.fail(applyBtn, res?.error || 'unknown');
        await showInfo('Apply failed', res?.error || 'unknown');
        status(`Apply failed: ${res?.error || 'unknown'}`);
        return;
      }
      // Assert canvas was not mutated by Apply
      const areasAfter = (tb.areas || []).map((a) => ({
        id: a.id,
        name: a.name,
        n: (a.nodes || []).length,
      }));
      const hashAfter = canonicalTransportHash();
      if (hashBefore !== hashAfter) {
        status(`Apply persistence ERROR: Transport hash changed ${hashBefore} → ${hashAfter}`);
        await showInfo(
          'Apply persistence error',
          `Transport canvas changed during Apply (should be impossible).\n`
          + `Before: ${JSON.stringify(areasBefore)}\nAfter: ${JSON.stringify(areasAfter)}`
        );
      }
      tb.workflow.apply = true;
      if (typeof window.setAutogenReadinessApplied === 'function') {
        try {
          window.setAutogenReadinessApplied(
            'transport',
            res.summary || 'Transport applied',
          );
        } catch (_) { /* ignore */ }
      }
      setWorkflowStep('build', { done: true });
      save(); // persist workflow.apply without dirtying hub
      const areas = (res.areas_applied || []).join(', ') || '(none)';
      const nConv = (res.conveyors_updated || []).length + (res.conveyors_created || []).length;
      const nMerge = Number(res.applied_count || res.total_count || 0);
      // Stay on Transportation — success only; PLC Autogen is the compile destination.
      status(
        `APPLIED ✓ Transportation · ${nConv} conveyor(s) · ${nMerge || '—'} merge(s) · areas: ${areas} · hash ${hashAfter}.`,
      );
      fb?.success(
        applyBtn,
        'APPLIED ✓ Transportation',
        `${nConv} conveyor(s) · areas: ${areas}`,
      );
      await showInfo(
        'Transportation APPLIED ✓',
        `${res.summary || 'Transport applied to workbook.'}\n\n`
          + `Areas: ${areas}\n`
          + `Conveyors touched: ${nConv}\n`
          + `Workbook: ${res.workbook_path || 'workspace/autogen_workbook.json'}\n\n`
          + 'Staying on Transportation. PLC Autogen remains available when you are ready to compile.',
      );
    } catch (err) {
      try {
        window.sfActionFeedback?.fail(
          document.querySelector('#tb-apply-autogen, [data-tb-apply]'),
          err?.message || String(err),
        );
      } catch (_) { /* ignore */ }
      await showInfo('Apply error', String(err?.message || err));
      status(`Apply error: ${err?.message || err}`);
    } finally {
      tb.applyingAutogen = false;
    }
  }

  function bindUi() {
    bindToolbar();

    // Event delegation so palette items (including Merge) always drag after HTML edits
    document.querySelector('#tab-transport')?.addEventListener('dragstart', (ev) => {
      const el = ev.target.closest?.('.tb-palette-item');
      if (!el || !el.dataset.tbKind) return;
      tb.dragKind = el.dataset.tbKind;
      try {
        ev.dataTransfer.setData('text/tb-kind', tb.dragKind);
        ev.dataTransfer.setData('text/plain', tb.dragKind);
        ev.dataTransfer.effectAllowed = 'copy';
      } catch (_) { /* ignore */ }
    });

    const canvas = $('tb-canvas');
    const nodesHost = $('tb-nodes');
    if (!canvas || !nodesHost) {
      status('Transport canvas missing — toolbar still works; reload if drop fails.');
      return;
    }
    // Allow keyboard focus for arrows / Delete after clicking the grid
    if (!canvas.hasAttribute('tabindex')) canvas.setAttribute('tabindex', '0');
    canvas.addEventListener('mousedown', (ev) => {
      try { canvas.focus(); } catch (_) { /* ignore */ }
      if (ev.button === 2 && tb.connectMode) {
        exitConnectMode();
        status('Connect Mode cancelled');
        render();
      }
    });
    canvas.addEventListener('contextmenu', (ev) => {
      if (tb.connectMode) {
        ev.preventDefault();
        exitConnectMode();
        status('Connect Mode cancelled');
        render();
      }
    });

    canvas.addEventListener('dragover', (ev) => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'copy';
    });

    canvas.addEventListener('drop', (ev) => {
      ev.preventDefault();
      const kind =
        ev.dataTransfer.getData('text/tb-kind') ||
        ev.dataTransfer.getData('text/plain') ||
        tb.dragKind;
      if (!kind || !KIND_META[kind]) {
        status('Drop failed — unknown palette item');
        return;
      }
      const pt = canvasPointFromEvent(ev);
      const x = pt.x;
      const y = pt.y;
      const area = activeArea();
      let onto = null;
      if (!isConv(kind) && area) {
        onto = nodeAtPoint(x, y, area);
      }
      addNode(kind, Math.max(0, x - 70), Math.max(0, y - 24), onto);
      tb.dragKind = null;
    });

    window.addEventListener('mousemove', (ev) => {
      // Middle-mouse pan is owned by Pass2 (tb.panning)
      if (tb.panning) return;
      if (tb.moving) {
        const tMove0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        const area = activeArea();
        if (!area) return;
        const pt = canvasPointFromEvent(ev);
        const byId = nodeIndex(area);
        const primary = byId.get(tb.moving.id);
        if (!primary) return;

        // Lite: CSS/SVG transform only — no path recalc, no model mutation per frame.
        if (tb.moving.lite || (isLiteRenderMode() && tb.moving.presentationOnly)) {
          const nx = pt.x - tb.moving.ox;
          const ny = pt.y - tb.moving.oy;
          const ddx = nx - (tb.moving.startX || 0);
          const ddy = ny - (tb.moving.startY || 0);
          tb.moving._dx = ddx;
          tb.moving._dy = ddy;
          const svg = $('tb-schematic');
          const esc = (typeof CSS !== 'undefined' && CSS.escape)
            ? CSS.escape(tb.moving.id)
            : String(tb.moving.id).replace(/"/g, '\\"');
          const g = svg?.querySelector?.(`.tb-lite-node[data-id="${esc}"]`);
          if (g) g.setAttribute('transform', `translate(${ddx} ${ddy})`);
          perfRecord('transport.dragFrameLite', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - tMove0, {
            id: tb.moving.id,
          });
          return;
        }

        const origins = tb.moving.origins;
        if (origins && origins.length) {
          // ox/oy captured as pt - n.x at drag start → nx/ny is primary target
          const nx = pt.x - tb.moving.ox;
          const ny = pt.y - tb.moving.oy;
          const ddx = nx - (tb.moving.startX || 0);
          const ddy = ny - (tb.moving.startY || 0);
          origins.forEach((o) => {
            const n = byId.get(o.id);
            if (!n) return;
            applyNodeGeomDelta(n, o, ddx, ddy);
            const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
            if (el) {
              if (isSchematicNode(n) || el.classList.contains('tb-schematic-proxy')) {
                el.style.left = `${(Number(n.x) || 0) - 9}px`;
                el.style.top = `${(Number(n.y) || 0) - 9}px`;
              } else if (isPhysicalSeg(n) || el.classList.contains('tb-seg')) {
                const { L, W } = segSize(n);
                el.style.left = `${n.x - L / 2}px`;
                el.style.top = `${n.y - W / 2}px`;
              } else {
                el.style.left = `${n.x}px`;
                el.style.top = `${n.y}px`;
              }
            }
          });
          // Drag: update proxy/node DOM positions only. Full schematic rebuild
          // happens once on mouseup — never per pointer sample.
          // Never persist localStorage during drag.
        } else {
          primary.x = Math.max(0, pt.x - tb.moving.ox);
          primary.y = Math.max(0, pt.y - tb.moving.oy);
          const el = document.querySelector(`.tb-node[data-id="${primary.id}"]`);
          if (el) {
            if (isPhysicalSeg(primary) || el.classList.contains('tb-seg')) {
              const { L, W } = segSize(primary);
              el.style.left = `${primary.x - L / 2}px`;
              el.style.top = `${primary.y - W / 2}px`;
            } else {
              el.style.left = `${primary.x}px`;
              el.style.top = `${primary.y}px`;
            }
          }
        }
        perfRecord('transport.dragFrame', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - tMove0, {
          id: tb.moving.id,
        });
      }
      if (tb.linkFrom) {
        const a = portCenter(tb.linkFrom.nodeId, 'out');
        if (a) {
          const pt = canvasPointFromEvent(ev);
          // Rubber-band: coalesce to one wire redraw per frame (not sync full rebuild)
          scheduleDrawWires({
            from: a,
            to: { x: pt.x, y: pt.y },
          });
        }
      }
    });

    window.addEventListener('mouseup', (ev) => {
      if (tb.moving) {
        const tUp0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        const move = tb.moving;
        const area = activeArea();
        if (move.lite || (isLiteRenderMode() && move.presentationOnly)) {
          // Commit presentation geometry once — not true RUN engineering edit.
          const byId = nodeIndex(area);
          const primary = byId.get(move.id);
          const origin = (move.origins && move.origins[0]) || null;
          const ddx = Number(move._dx) || 0;
          const ddy = Number(move._dy) || 0;
          if (primary && origin && (Math.abs(ddx) > 0.01 || Math.abs(ddy) > 0.01)) {
            applyNodeGeomDelta(primary, origin, ddx, ddy);
            if (!primary.provenance) primary.provenance = {};
            primary.provenance.presentationMove = 'ENGINEER_PRESENTATION';
            invalidateLiteGeom(primary.id);
          }
          tb.moving = null;
          tb._moveHistoryPushed = false;
          save();
          try { drawLiteSchematicNow(area); } catch (_) { /* ignore */ }
          perfRecord('transport.dragCommitLite', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - tUp0, {
            id: move.id,
            dx: ddx,
            dy: ddy,
          });
        } else {
          tb.moving = null;
          tb._moveHistoryPushed = false;
          save();
          // Refresh schematic after group move settles
          try { drawSchematic(activeArea()); drawWires(); } catch (_) { /* ignore */ }
          perfRecord('transport.dragCommit', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - tUp0, {
            id: move.id,
          });
        }
      }
      if (tb.linkFrom) {
        const target = ev.target.closest?.('.tb-port.in');
        const nodeEl = ev.target.closest?.('.tb-node');
        document.querySelectorAll('.tb-port.linking').forEach((p) => p.classList.remove('linking'));
        if (target && nodeEl) {
          connect(tb.linkFrom.nodeId, nodeEl.dataset.id, target.dataset.port || 'in');
        } else {
          status('Link cancelled');
          drawWires();
        }
        tb.linkFrom = null;
      }
    });

    $('tb-insp-label')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;
      n.label = e.target.value.trim();
      save();
      render();
    });

    $('tb-insp-conveyor')?.addEventListener('change', async (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;
      const prev = (n.conveyorTag || '').trim();
      const next = (e.target.value || '').trim();
      if (next) {
        const dup = (tb.areas || []).some((area) =>
          (area.nodes || []).some(
            (x) => x.id !== n.id && String(x.conveyorTag || '').trim().toUpperCase() === next.toUpperCase()
          )
        );
        if (dup) {
          const ok = await askYesNo(
            'Duplicate P###',
            `${next} is already assigned to another graph node. Assign anyway?`
          );
          if (!ok) {
            e.target.value = prev;
            return;
          }
        }
      }
      n.conveyorTag = next;
      n.placeholderTag = false;
      if (n.conveyorTag && (!n.label || KIND_META[n.kind]?.title === n.label || /^Merge /i.test(n.label || ''))) {
        if (!KIND_META[n.kind]?.isMerge) n.label = n.conveyorTag;
      }
      // Refresh downstream tags on inbound sources pointing here
      syncDownstreamFromWires(a);
      (a.wires || []).filter((w) => w.to === n.id).forEach((w) => {
        const src = a.nodes.find((x) => x.id === w.from);
        if (src) src.downstream = (n.conveyorTag || '').trim();
      });
      save();
      render();
      if (!n.conveyorTag && prev) {
        status(`Cleared ${prev} — Apply to remove it from the Transport area L5X`);
        showToast(`Cleared ${prev}. Click Apply so the next Generate drops it from MERGE/area routines.`);
      }
    });

    $('tb-insp-downstream')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;
      setDownstream(n.id, e.target.value || '');
    });

    $('tb-insp-terminal')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;
      n.terminal = !!e.target.checked;
      if (n.terminal) {
        // Clearing relationship is explicit via downstream dropdown; terminal only suppresses warning
      }
      save();
      render();
    });

    $('tb-insp-rotate')?.addEventListener('click', () => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n || !isConv(n.kind)) return;
      n.rotation = (Number(n.rotation || 0) + 90) % 360;
      save();
      render();
      status(`Rotated ${n.label || n.id} to ${n.rotation}°`);
    });

    $('tb-insp-spiral-motors')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n || !KIND_META[n.kind]?.isSpiral) return;
      n.motorCount = Math.min(
        SPIRAL_MOTOR_MAX,
        Math.max(SPIRAL_MOTOR_MIN, parseInt(e.target.value, 10) || SPIRAL_MOTOR_DEFAULT),
      );
      normalizeSpiralMotors(n);
      if (!n.label || /^Spiral/i.test(n.label)) {
        n.label = `Spiral (${n.motorCount} motors)`;
      }
      save();
      render();
      status(`Spiral set to ${n.motorCount} motor(s) — pick M### / VFD### tags`);
    });

    $('tb-insp-spiral-motors')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n || !KIND_META[n.kind]?.isSpiral) return;
      n.motorCount = Math.min(
        SPIRAL_MOTOR_MAX,
        Math.max(SPIRAL_MOTOR_MIN, parseInt(e.target.value, 10) || SPIRAL_MOTOR_DEFAULT),
      );
      normalizeSpiralMotors(n);
      if (!n.label || /^Spiral/i.test(n.label)) {
        n.label = `Spiral (${n.motorCount} motors)`;
      }
      save();
      render();
      status(`Spiral set to ${n.motorCount} motor(s) — pick M### / VFD### tags`);
    });

    function isMergeLike(n) {
      return !!(n && (KIND_META[n.kind]?.isMerge || n.asMerge));
    }

    $('tb-insp-merge-lanes')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!isMergeLike(n)) return;
      const lanes = Math.min(4, Math.max(2, parseInt(e.target.value, 10) || 2));
      n.inPorts = lanes;
      if (KIND_META[n.kind]?.isMerge) n.label = `Merge ${lanes}:1`;
      if (lanes < 3) n.pe_c = '';
      // Drop wires to removed entrances
      const valid = new Set([...Array(lanes)].map((_, i) => `in${i}`));
      a.wires = a.wires.filter((w) => {
        if (w.to !== n.id) return true;
        return valid.has(w.toPort || 'in0') || valid.has(w.toPort);
      });
      save();
      render();
      status(`Merge set to ${lanes}:1${lanes >= 3 ? ' — Lane C PE available' : ''}`);
    });

    const bindMergePe = (id, key) => {
      $(id)?.addEventListener('change', (e) => {
        const a = activeArea();
        const n = a?.nodes.find((x) => x.id === tb.selectedId);
        if (!isMergeLike(n)) return;
        n[key] = e.target.value || '';
        save();
        status(`Merge ${key} → ${n[key] || 'NO_PE'}`);
      });
    };
    bindMergePe('tb-insp-merge-pe-a', 'pe_a');
    bindMergePe('tb-insp-merge-pe-b', 'pe_b');
    bindMergePe('tb-insp-merge-pe-c', 'pe_c');
    bindMergePe('tb-insp-merge-jam-pe', 'jam_pe');
    $('tb-insp-merge-allow-pe')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!isMergeLike(n)) return;
      n.allow_undefined_pe = !!e.target.checked;
      save();
      status(n.allow_undefined_pe ? 'Will create missing PE tags in L5X' : 'Unknown PEs → NO_PE');
    });

    // Keyboard: Delete / Backspace remove selection; arrows nudge conveyors
    window.addEventListener('keydown', (ev) => {
      const tab = $('tab-transport');
      if (!tab || tab.classList.contains('hidden')) return;
      // Never steal keys while New/Rename area (or any Transport dialog) is open
      if (isTransportDialogOpen()) return;
      const tag = (ev.target && ev.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || ev.target?.isContentEditable) return;
      // Also ignore when focus is inside the dialog overlay
      if (ev.target?.closest?.('#tb-dialog')) return;

      if (ev.key === 'Escape' && tb.connectMode) {
        ev.preventDefault();
        exitConnectMode();
        status('Connect Mode cancelled');
        render();
        return;
      }

      const a = activeArea();
      if (!a || !tb.selectedId) return;
      const n = a.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;

      if (ev.key === 'Delete' || ev.key === 'Backspace') {
        ev.preventDefault();
        if (tb.selectedDeviceId && n.devices) {
          n.devices = n.devices.filter((d) => d.id !== tb.selectedDeviceId);
          tb.selectedDeviceId = null;
          save();
          render();
          status('Device removed');
          return;
        }
        a.nodes = a.nodes.filter((x) => x.id !== tb.selectedId);
        a.wires = a.wires.filter((w) => w.from !== tb.selectedId && w.to !== tb.selectedId);
        if (tb.connectSourceId === tb.selectedId) tb.connectSourceId = null;
        tb.selectedId = null;
        tb.selectedDeviceId = null;
        syncDownstreamFromWires(a);
        save();
        render();
        status('Node deleted');
        return;
      }

      const step = ev.shiftKey ? 20 : 5;
      let moved = false;
      if (ev.key === 'ArrowLeft') { n.x = Math.max(0, n.x - step); moved = true; }
      if (ev.key === 'ArrowRight') { n.x += step; moved = true; }
      if (ev.key === 'ArrowUp') { n.y = Math.max(0, n.y - step); moved = true; }
      if (ev.key === 'ArrowDown') { n.y += step; moved = true; }
      if (moved) {
        ev.preventDefault();
        const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
        if (el) {
          el.style.left = `${n.x}px`;
          el.style.top = `${n.y}px`;
        }
        drawWires();
        save();
      }
      if (ev.key === 'r' || ev.key === 'R') {
        if (!isConv(n.kind)) return;
        ev.preventDefault();
        n.rotation = (Number(n.rotation || 0) + 90) % 360;
        save();
        render();
      }
    });

    $('tb-insp-add-device')?.addEventListener('click', () => {
      const row = $('tb-insp-add-row');
      row?.classList.toggle('hidden');
      refreshAttachKindOptions();
      const kind = $('tb-insp-device-kind')?.value || 'motor';
      fillTagSelect($('tb-insp-device-tag-new'), kind, '');
    });

    $('tb-insp-device-kind')?.addEventListener('change', (e) => {
      fillTagSelect($('tb-insp-device-tag-new'), e.target.value || 'motor', '');
    });

    $('tb-insp-device-ok')?.addEventListener('click', () => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n || !isConv(n.kind)) return;
      const kind = $('tb-insp-device-kind')?.value || 'motor';
      if (KIND_META[n.kind]?.isMerge && kind === 'photoeye') {
        status('Merge PEs: use Lane A / B / Jam in the inspector — not Attach Photoeye.');
        return;
      }
      const tag = ($('tb-insp-device-tag-new')?.value || '').trim();
      if (!tag) {
        status('Pick a buildable tag for this device type.');
        return;
      }
      if (!deviceTagMatches(kind, tag, kind)) {
        status(`“${tag}” is not a field ${kind} tag (clutter filtered).`);
        return;
      }
      if (!n.devices) n.devices = [];
      const newDev = { id: uid('dev'), kind, name: tag, tag };
      if (kind === 'photoeye') {
        newDev.roles = inferPeRoles(tag);
        newDev.rolesManual = false;
      }
      n.devices.push(newDev);
      $('tb-insp-add-row')?.classList.add('hidden');
      tb.selectedDeviceId = null;
      save();
      render();
      status(
        kind === 'photoeye'
          ? `Added PE ${tag} · roles ${newDev.roles.join('+') || 'none'}`
          : `Added ${kind} ${tag}`,
      );
    });

    $('tb-insp-dev-tag')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      const d = n?.devices?.find((x) => x.id === tb.selectedDeviceId);
      if (!d) return;
      d.tag = e.target.value;
      d.name = d.tag || d.name;
      if (d.kind === 'photoeye') {
        // Re-infer from new suffix unless engineer already customized roles
        ensurePeRoles(d, { forceInfer: !d.rolesManual });
      }
      save();
      render();
      status(
        d.kind === 'photoeye'
          ? `Set PE → ${d.tag || '(none)'} · ${(d.roles || []).join('+') || 'no roles'}`
          : `Set ${d.kind} tag → ${d.tag || '(none)'}`,
      );
    });

    PE_ROLE_ORDER.forEach((role) => {
      $(`tb-insp-pe-role-${role}`)?.addEventListener('change', (ev) => {
        const a = activeArea();
        const n = a?.nodes.find((x) => x.id === tb.selectedId);
        const d = n?.devices?.find((x) => x.id === tb.selectedDeviceId);
        if (!d || d.kind !== 'photoeye') return;
        // NONE is exclusive
        if (role === 'none' && ev.target.checked) {
          PE_ROLE_ORDER.forEach((r) => {
            const el = $(`tb-insp-pe-role-${r}`);
            if (el) el.checked = r === 'none';
          });
        } else if (role !== 'none' && ev.target.checked) {
          const noneEl = $('tb-insp-pe-role-none');
          if (noneEl) noneEl.checked = false;
        }
        const next = PE_ROLE_ORDER.filter((r) => !!$(`tb-insp-pe-role-${r}`)?.checked);
        if (!next.length) {
          // Cleared → PE ROLE REQUIRED (do not invent defaults)
          d.rolesManual = false;
          d.roles = inferPeRoles(d.tag || d.name || '');
          d.peRoleRequired = !(d.roles && d.roles.length);
          d.peRoleProvenance = d.peRoleRequired ? 'UNKNOWN' : 'RUN_EXPLICIT';
          status(d.peRoleRequired
            ? 'PE ROLE REQUIRED — select JAM / FULL / EXIT / ADD / OTHER / NONE'
            : `PE roles from RUN suffix → ${d.roles.join('+')}`);
        } else {
          d.roles = next;
          d.rolesManual = true;
          d.peRoleRequired = false;
          d.peRoleProvenance = 'ENGINEER_CONFIGURED';
          status(`PE roles (engineer) → ${d.roles.join('+')}`);
        }
        PE_ROLE_ORDER.forEach((r) => {
          const el = $(`tb-insp-pe-role-${r}`);
          if (el) el.checked = (d.roles || []).includes(r);
        });
        const req = $('tb-insp-pe-role-required');
        if (req) req.classList.toggle('hidden', !d.peRoleRequired);
        save();
        render();
      });
    });

    $('tb-insp-dev-back')?.addEventListener('click', () => {
      tb.selectedDeviceId = null;
      render();
    });

    $('tb-insp-delete')?.addEventListener('click', () => {
      const a = activeArea();
      if (!a || !tb.selectedId) return;
      const n = a.nodes.find((x) => x.id === tb.selectedId);
      if (tb.selectedDeviceId && n?.devices) {
        n.devices = n.devices.filter((d) => d.id !== tb.selectedDeviceId);
        tb.selectedDeviceId = null;
        save();
        render();
        return;
      }
      a.nodes = a.nodes.filter((x) => x.id !== tb.selectedId);
      a.wires = a.wires.filter((w) => w.from !== tb.selectedId && w.to !== tb.selectedId);
      tb.selectedId = null;
      tb.selectedDeviceId = null;
      save();
      render();
    });
  }

  /* —— Transport wizard (areas → conveyors → devices → merge PEs → apply) —— */
  const wiz = { step: 0, mergeId: null };

  function closeTransportWizard() {
    const p = $('tb-wizard-panel');
    if (p) { p.classList.add('hidden'); p.style.display = 'none'; }
  }

  function openTransportWizard() {
    wiz.step = 0;
    wiz.mergeId = null;
    const p = $('tb-wizard-panel');
    if (p) { p.classList.remove('hidden'); p.style.display = 'flex'; }
    renderWizardStep();
  }

  function wizardNav(delta) {
    const next = wiz.step + delta;
    if (next < 0) return;
    if (delta > 0 && !wizardCommitStep()) return;
    if (next > 4) {
      closeTransportWizard();
      applyMergesToAutogenUi();
      return;
    }
    wiz.step = next;
    renderWizardStep();
  }

  function wizardCommitStep() {
    const a = activeArea();
    if (wiz.step === 0) {
      const name = ($('tb-wiz-area-name')?.value || '').trim();
      if (name && a) { a.name = name; save(); render(); }
    }
    if (wiz.step === 3 && wiz.mergeId && a) {
      const n = a.nodes.find((x) => x.id === wiz.mergeId);
      if (n) {
        n.pe_a = $('tb-wiz-pe-a')?.value || '';
        n.pe_b = $('tb-wiz-pe-b')?.value || '';
        n.jam_pe = $('tb-wiz-jam-pe')?.value || '';
        n.allow_undefined_pe = !!$('tb-wiz-allow-pe')?.checked;
        save();
      }
    }
    return true;
  }

  function renderWizardStep() {
    const titles = [
      '1 · Name the area',
      '2 · Bind conveyors',
      '3 · Devices (buildable tags)',
      '4 · Merge AOI PEs (optional)',
      '5 · Apply to Autogen',
    ];
    const msgs = [
      'Rename this Transport area — Apply maps it to Autogen main_area / Fast·Slow programs.',
      'Select each conveyor on the canvas and bind a P### from the RUN list in the inspector.',
      'Attach motors / PEs / etc. Dropdowns only list tags Autogen will put in the L5X.',
      'Merge needs lane PEs and optional jam PE. Leave blank = NO_PE — build still succeeds. Check override only if you must force a PE tag into the L5X.',
      'Push areas + transport + merges into the Autogen workbook, then Generate on PLC Autogen.',
    ];
    if ($('tb-wiz-title')) $('tb-wiz-title').textContent = titles[wiz.step] || 'Wizard';
    if ($('tb-wiz-msg')) $('tb-wiz-msg').textContent = msgs[wiz.step] || '';
    if ($('tb-wiz-steps')) {
      $('tb-wiz-steps').innerHTML = titles
        .map((t, i) => `<span class="${i === wiz.step ? 'text-sky-400' : ''}">${i + 1}</span>`)
        .join('<span class="text-slate-700">·</span>');
    }
    const body = $('tb-wiz-body');
    const back = $('tb-wiz-back');
    const next = $('tb-wiz-next');
    if (back) back.disabled = wiz.step === 0;
    if (next) next.textContent = wiz.step === 4 ? 'Apply to Autogen' : 'Next';
    if (!body) return;

    const a = activeArea();
    if (wiz.step === 0) {
      body.innerHTML = `
        <label class="text-[10px] text-slate-500">Area name
          <input id="tb-wiz-area-name" type="text" class="mt-1 w-full bg-slate-900 border border-slate-700 rounded-lg text-xs px-2 py-1.5 text-slate-200"
            value="${escapeHtml(a?.name || 'Transport_1')}" />
        </label>
        <p class="text-[9px] text-slate-600">Tip: use New area for Induct / Shipping / etc., then run the wizard per area.</p>`;
    } else if (wiz.step === 1) {
      const rows = (a?.nodes || []).filter((n) => isConv(n.kind));
      body.innerHTML = rows.length
        ? `<div class="space-y-1 max-h-48 overflow-y-auto">${rows
            .map(
              (n) =>
                `<div class="text-[10px] mono flex gap-2"><span class="text-slate-500 w-28 truncate">${escapeHtml(
                  n.label || n.kind
                )}</span><span class="${n.conveyorTag ? 'text-cyan-400' : 'text-amber-400'}">${escapeHtml(
                  n.conveyorTag || '⚠ unbound'
                )}</span></div>`
            )
            .join('')}</div>
          <p class="text-[9px] text-slate-600">Unbound conveyors still Apply as stubs; bind before Generate for real IO.</p>`
        : `<p class="text-[11px] text-amber-400">No conveyors yet — drag Straight / Merge onto the grid, then continue.</p>`;
    } else if (wiz.step === 2) {
      const cat = buildableTagCatalog();
      body.innerHTML = `
        <div class="text-[10px] text-slate-400 space-y-1">
          <div>Buildable photoeyes: <span class="mono text-sky-400">${cat.photoeye.size}</span></div>
          <div>Buildable motors: <span class="mono text-amber-400">${cat.motor.size}</span></div>
          <div>Buildable encoders: <span class="mono text-violet-400">${cat.encoder.size}</span></div>
        </div>
        <p class="text-[9px] text-slate-600 mt-2">If counts are 0, open PLC Autogen and build the workbook from RUN first — then device dropdowns fill.</p>`;
    } else if (wiz.step === 3) {
      const merges = (a?.nodes || []).filter((n) => KIND_META[n.kind]?.isMerge);
      if (!merges.length) {
        body.innerHTML = `<p class="text-[11px] text-slate-400">No merge on this area — skip ahead. Simple transport does not need jam PE.</p>`;
        wiz.mergeId = null;
      } else {
        wiz.mergeId = merges[0].id;
        const n = merges[0];
        body.innerHTML = `
          <div class="text-[10px] text-orange-300 mb-1">Merge ${escapeHtml(n.conveyorTag || n.label || '')}</div>
          <label class="block text-[10px] text-slate-500">Lane A PE<select id="tb-wiz-pe-a" class="mt-0.5 w-full bg-slate-900 border border-slate-700 rounded text-[10px] px-1.5 py-1 text-sky-300"></select></label>
          <label class="block text-[10px] text-slate-500">Lane B PE<select id="tb-wiz-pe-b" class="mt-0.5 w-full bg-slate-900 border border-slate-700 rounded text-[10px] px-1.5 py-1 text-sky-300"></select></label>
          <label class="block text-[10px] text-slate-500">Jam PE (optional)<select id="tb-wiz-jam-pe" class="mt-0.5 w-full bg-slate-900 border border-slate-700 rounded text-[10px] px-1.5 py-1 text-sky-300"></select></label>
          <label class="flex items-center gap-2 text-[10px] text-slate-400 mt-1"><input id="tb-wiz-allow-pe" type="checkbox" ${
            n.allow_undefined_pe ? 'checked' : ''
          }/> Create missing PE tags (override)</label>`;
        fillTagSelect($('tb-wiz-pe-a'), 'photoeye', n.pe_a || '');
        fillTagSelect($('tb-wiz-pe-b'), 'photoeye', n.pe_b || '');
        fillTagSelect($('tb-wiz-jam-pe'), 'photoeye', n.jam_pe || '');
      }
    } else {
      body.innerHTML = `
        <ul class="text-[11px] text-slate-400 space-y-1 list-disc pl-4">
          <li>Areas → Autogen <span class="mono">main_area</span></li>
          <li>Simple belts → Fast/Slow (no merge required)</li>
          <li>Merges → Merge pack + <span class="mono">NO_PE</span> if PE left blank</li>
        </ul>
        <p class="text-[9px] text-slate-600 mt-2">Next runs Apply. Then PLC Autogen → Generate.</p>`;
    }
  }

  function init() {
    if (!$('tab-transport')) return;
    const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    load();
    restoreRenderModePreference();
    // Relationships stay OFF by default for Lite Schematic (clean one-line)
    if (typeof tb.layers?.relationships !== 'boolean') {
      if (!tb.layers) tb.layers = {};
      tb.layers.relationships = false;
    }
    tb.showRelationships = !!tb.layers.relationships;
    const relEl = $('tb-show-relationships');
    if (relEl) relEl.checked = !!tb.showRelationships;
    assertTransportModelCacheIdentity();
    ensureArea();
    migrateGraphTopology();
    bindUi();
    paintPaletteIcons();
    render();
    syncRenderModeButtons();
    perfRecord('transport.initialUi', ((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()) - t0, {
      mode: tb.renderMode || 'lite',
      node_count: (activeArea()?.nodes || []).length,
    });
    status(isLiteRenderMode()
      ? 'Transport Lite Schematic ready — Build Chain / Continue Run for rapid topology.'
      : 'Transport Build ready — Build Chain / Continue Run for rapid topology.');
    try {
      if (typeof window.__tbPass2Init === 'function') window.__tbPass2Init();
    } catch (err) {
      try { console.warn('[TransportBuild] Pass2 init', err); } catch (_) { /* ignore */ }
    }
  }

  // Expose refresh when tab opens (conveyor dropdown)
  window.transportHighlightSafetyZone = function (zoneName) {
    try { highlightSafetyZone(zoneName); } catch (_) { /* ignore */ }
  };

  window.transportDeleteSafetyZone = function (zoneName) {
    try { return deleteSafetyZone(zoneName); } catch (_) { return false; }
  };

  window.transportBuildRefresh = function () {
    render();
    try {
      if (typeof window.__tbPass2OnRefresh === 'function') window.__tbPass2OnRefresh();
    } catch (_) { /* ignore */ }
  };

  /**
   * Wipe all Transport Build areas (Transport1, Merge5, …) and reset PE role UI.
   * opts.leaveEmpty — skip recreating Transport_1 / save (Clear Current Project).
   */
  window.transportBuildClearAll = function (opts) {
    const leaveEmpty = !!(opts && opts.leaveEmpty);
    tb.suppressDefaultArea = leaveEmpty;
    tb.areas = [];
    tb.activeAreaId = null;
    tb.safetyZones = [];
    tb.activeSafetyZoneId = null;
    tb.selectedId = null;
    tb.selectedIds = [];
    tb.selectedDeviceId = null;
    tb.buildContext = { areaId: null, areaName: '', safetyZone: '' };
    tb.history = { past: [], future: [], max: 50 };
    // Erased Means Erased — drop project-scoped model + geometry caches
    clearTransportModelCache('project_cleared');
    markValidationDirty();
    if (tb.view) tb.view.zoom = 1;
    try { localStorage.removeItem(STORE_KEY); } catch (_) { /* ignore */ }
    try { localStorage.removeItem('siteforge.transportBuild.v1'); } catch (_) { /* ignore */ }
    if (!leaveEmpty) {
      ensureArea();
    }
    resetPeRoleUi();
    if (!leaveEmpty) {
      save();
    }
    render();
    // Force inspector empty state (PE roles must not linger after Clear Current Project)
    $('tb-inspector-empty')?.classList.remove('hidden');
    $('tb-inspector')?.classList.add('hidden');
    status(leaveEmpty
      ? 'Transport canvas empty — load RUN (auto layout) or Rebuild Layout'
      : 'All transport areas cleared — PE roles reset');
    return true;
  };

  // Electron has no window.prompt — expose Site Forge dialogs globally for I/O / Safety
  window.askText = askText;
  window.askYesNo = askYesNo;
  window.showInfo = showInfo;
  window.askDialog = askDialog;

  /** Pass 2 bridge — companion script uses these without rewriting Pass 1 core. */
  window.__tbApi = {
    get tb() { return tb; },
    $,
    uid,
    save,
    load,
    render,
    status,
    showToast,
    activeArea,
    ensureArea,
    ensureDefaultArea,
    isDefaultArea,
    isDefaultAreaName,
    isEngineerAreaShell,
    DEFAULT_AREA_NAME,
    transportOwnershipCounts,
    ownedTransportNodes,
    returnAreaMembersToDefault,
    isConv,
    KIND_META,
    escapeHtml,
    canvasPointFromEvent,
    nodeAtPoint,
    selectNode,
    setDownstream,
    clearDownstream,
    connect,
    maybeConfirmMerge,
    findNodeByTag,
    getUpstreamTags,
    getUpstreamNodes,
    syncDownstreamFromWires,
    syncWiresFromDownstream,
    migrateGraphTopology,
    outboundWire,
    inboundWires,
    pickEntrancePort,
    nodeLabel,
    conveyorOptions,
    deviceTagOptions,
    buildableTagCatalog,
    runInventory,
    assignedConveyorTags,
    assignedDeviceTags,
    moveNodeToArea,
    moveNodesToArea,
    scheduleAreaAssignPersist,
    flushAreaAssignPersist,
    peRolesOnNode,
    peRoleBadgesHtml,
    peTagsByRole,
    inferPeRoles,
    ensurePeRoles,
    fillTagSelect,
    askYesNo,
    askText,
    showInfo,
    askDialog,
    enterConnectMode,
    exitConnectMode,
    toggleConnectMode,
    handleConnectModeClick,
    drawWires,
    classifyRenderedConnection,
    mayDrawPhysicalJoin,
    hasProvenPhysicalWire,
    falseAbutmentInsets,
    insetDisplayEndpoints,
    ensureCanvasExtents,
    portCenter,
    collectValidation,
    renderValidationPanel,
    renderInventoryPanel,
    renderTopologyTable,
    renderInspector,
    buildGeometryDiagnostic,
    exportGeometryDiagnostic,
    geometryDiagnosticSiteNotes,
    safetyForAreaName,
    listSafetyZoneNames,
    ensureSafetyZone,
    deleteSafetyZone,
    seedSafetyZonesFromNodes,
    refreshSafetyZoneSelect,
    resetView100,
    zoomByFactor,
    STORE_KEY,
    isPhysicalSeg,
    isSchematicNode,
    physicalAnchors,
    segSize,
    presentationScale,
    flowAngleDeg,
    detailLevel,
    fitSite,
    fitArea,
    fitVisible,
    fitAll,
    fitSelection,
    fitSystem,
    centerSelected,
    homeView,
    setGeometryAuthorityMode,
    getDisplayTransform,
    applyEngineerGeometryOverride,
    mayApplyFallbackLayout,
    fitViewToNodes,
    applyViewportZoom,
    viewportZoomLimits,
    nodesBBox,
    classifySpatialOutliers,
    computeConnectedComponents,
    renderTopologyAccounting,
    showUnresolvedTopology,
    highlightSafetyZone,
    placeSchematicLabels,
    buildPhysicalCurveDisplayPath,
    synthesizeCurveDisplayPath,
    displayPathCanvasForNode,
    projectSharedTopologyJoints,
    _curveFromTangents,
    _curveFromChordAndSweep,
    pathIsPhysicalCenterlineArc,
    drawSchematic,
    drawSchematicNow,
    drawLiteSchematicNow,
    drawWiresNow,
    perfSnapshot,
    perfRecord,
    buildPerfReport,
    writeTransportGuiPerf,
    invalidateNodeIndex,
    invalidateSchematicHitGeometry,
    invalidateLiteGeom,
    requestPresentationRelayout,
    schematicPathD,
    pickSchematicNodeAt,
    nodeIdFromLiteEvent,
    selectLiteNode,
    updateLiteHover,
    distanceToDisplayPath,
    SCHEMATIC_HIT_WIDTH,
    CURVE_SYMBOL,
    CURVE_DISPLAY_ANGLE_CHOICES,
    setCurveDisplayAngle,
    curveDisplayDirectionRad,
    curveRenderedDisplayAngleDeg,
    buildCanonicalApplyGraph,
    applyMergesToAutogenUi,
    canonicalTransportHash,
    setWorkflowStep,
    computePresentationOffsets,
    normalizeControlPanel,
    inferControlPanelFromEvidence,
    ensureControlPanel,
    discoveredControlPanels,
    cpFilterActive,
    nodeMatchesCpFilter,
    captureNodeGeom,
    applyNodeGeomDelta,
    isLiteRenderMode,
    isReadableSchematic,
    isPackedSchematic,
    getSchematicStyle,
    setSchematicStyle,
    setRenderMode,
    setReadableSchematic,
    restoreRenderModePreference,
    nodeHasVfdDriveEvidence,
    syncTransportLegendVisibility,
    LITE_ARROW_SCALE,
    LITE_ARROW_MARKER_SIZE,
    computeLiteReadableOffsets,
    computeLitePackedOffsets,
    listLiteTransportComponents,
    liteLabelCollisionPlan,
    setShowRelationships,
    renderScene,
    renderTopologyPanel,
    markValidationDirty,
    getValidationCached,
    transportModelCacheKey,
    getCachedTransportModel,
    setCachedTransportModel,
    clearTransportModelCache,
    assertTransportModelCacheIdentity,
    liteStraightPath,
    liteCurvePath,
    liteCachedPath,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
