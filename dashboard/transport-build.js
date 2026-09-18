/* Transport Build POC — Node-RED style conveyor graph (visual only).
 * Persists to localStorage. Future: feed graph JSON to fortna_autogen.
 */
(function () {
  // v2 invalidates plant-wide canvases saved before ControllerScope filtering.
  const STORE_KEY = 'siteforge.transportBuild.v2';

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
    laneSeparate: true, // presentation-only offsets for stacked bodies
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

  function ensureArea() {
    // Clear Current Project may leave canvas empty until Auto Build / Add area
    if (tb.suppressDefaultArea) return;
    if (!tb.areas.length) {
      const a = { id: uid('area'), name: 'Transport_1', nodes: [], wires: [] };
      tb.areas.push(a);
      tb.activeAreaId = a.id;
    }
    if (!activeArea()) tb.activeAreaId = tb.areas[0].id;
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
      return { ...area, nodes, wires };
    }).filter((a) => (a.nodes || []).length > 0);
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
        tb.safetyZones = data.safetyZones
          .filter((z) => z && (z.name || z.id))
          .map((z) => ({ id: z.id || uid('szone'), name: String(z.name || '').trim() }))
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
        (area.nodes || []).forEach((n) => {
          if (n.controlPanel == null) n.controlPanel = '';
          if (n.safetyZone == null) n.safetyZone = '';
        });
      });
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

  function renderValidationPanel() {
    const el = $('tb-validation');
    if (!el) return;
    const { errors, warnings, ready } = collectValidation();
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

  /** All known Safety Zone names (first-class list + any conveyor values). */
  function listSafetyZoneNames() {
    const names = new Set();
    (tb.safetyZones || []).forEach((z) => {
      const n = String(z?.name || '').trim();
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

  /** Ensure a Safety Zone exists by name; returns the zone record. */
  function ensureSafetyZone(name) {
    const nm = String(name || '').trim();
    if (!nm) return null;
    tb.safetyZones = tb.safetyZones || [];
    let z = tb.safetyZones.find((x) => String(x.name || '').trim().toLowerCase() === nm.toLowerCase());
    if (!z) {
      z = { id: uid('szone'), name: nm };
      tb.safetyZones.push(z);
    }
    return z;
  }

  /**
   * Delete a Safety Zone from Transportation: drop registry entry and clear
   * conveyor.safetyZone assignments that pointed at it. Display-only membership.
   */
  function deleteSafetyZone(name) {
    const nm = String(name || '').trim();
    if (!nm) return false;
    const lower = nm.toLowerCase();
    tb.safetyZones = (tb.safetyZones || []).filter(
      (z) => String(z.name || '').trim().toLowerCase() !== lower,
    );
    (tb.areas || []).forEach((area) => {
      (area.nodes || []).forEach((n) => {
        if (String(n.safetyZone || '').trim().toLowerCase() === lower) n.safetyZone = '';
      });
    });
    if (tb.activeSafetyZoneId && !(tb.safetyZones || []).some((z) => z.id === tb.activeSafetyZoneId)) {
      tb.activeSafetyZoneId = (tb.safetyZones[0] && tb.safetyZones[0].id) || null;
    }
    if (String(tb.buildContext?.safetyZone || '').trim().toLowerCase() === lower) {
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
      const prev = (tb.safetyZones || []).find(
        (z) => String(z.name || '').trim().toLowerCase() === name.toLowerCase()
      );
      return prev || { id: uid('szone'), name };
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
    tb.view.zoom = next;
    applyViewportZoom();
    if (canvas) {
      canvas.scrollLeft = wx * next - canvas.clientWidth / 2;
      canvas.scrollTop = wy * next - canvas.clientHeight / 2;
    }
    render();
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
        const areaOpts = tb.areas
          .map((a) => `<option value="${escapeHtml(a.id)}" ${a.id === area.id ? 'selected' : ''}>${escapeHtml(a.name)}</option>`)
          .join('');
        const dsOpts = [`<option value="">—</option>`]
          .concat(
            (area.nodes || [])
              .filter((x) => isConv(x.kind) && x.id !== n.id && (x.conveyorTag || '').trim())
              .map((x) => {
                const t = x.conveyorTag.trim();
                return `<option value="${escapeHtml(t)}" ${t === ds ? 'selected' : ''}>${escapeHtml(t)}</option>`;
              })
          )
          .join('');
        // Conveyor-level Safety Zone is authoritative (not Area-derived).
        const curZone = String(n.safetyZone || '').trim();
        const zoneNames = listSafetyZoneNames();
        if (curZone && !zoneNames.includes(curZone)) zoneNames.push(curZone);
        const zoneOpts = [`<option value="">—</option>`]
          .concat(zoneNames.map((z) =>
            `<option value="${escapeHtml(z)}" ${z === curZone ? 'selected' : ''}>${escapeHtml(z)}</option>`
          ))
          .join('');
        rows.push(`<tr class="${sel}" data-topo-id="${escapeHtml(n.id)}" data-topo-area="${escapeHtml(area.id)}">
          <td class="mono text-cyan-300">${escapeHtml(tag || n.label || n.id)}</td>
          <td><select data-topo-area-sel="${escapeHtml(n.id)}">${areaOpts}</select></td>
          <td class="text-slate-400">${escapeHtml(up)}</td>
          <td><select data-topo-ds="${escapeHtml(n.id)}">${dsOpts}</select></td>
          <td>${escapeHtml(typ)}</td>
          <td class="mono">${escapeHtml(exitPe || '—')}</td>
          <td class="mono">${escapeHtml(addPe || '—')}</td>
          <td class="mono">${escapeHtml(jamPe || '—')}</td>
          <td class="mono">${escapeHtml(fullPe || '—')}</td>
          <td><select data-topo-szone="${escapeHtml(n.id)}" class="mono text-amber-200 max-w-[9rem]" title="Conveyor Safety Zone (independent of Area)">${zoneOpts}</select></td>
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
        moveNodeToArea(nodeId, destAreaId);
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

  /**
   * Reassign a conveyor's Area (organization/metadata).
   *
   * Architecture note:
   * - Visual wires[] are area-scoped (drawn only when both ends share an area).
   * - Canonical topology is tag-based node.downstream (area-independent).
   * - Apply already prefers wires then falls back to node.downstream across the whole graph.
   * Therefore changing Area must NEVER clear downstream relationships.
   */
  function moveNodeToArea(nodeId, destAreaId) {
    const dest = tb.areas.find((a) => a.id === destAreaId);
    if (!dest) return;
    let node = null;
    let srcArea = null;
    for (const a of tb.areas) {
      const idx = (a.nodes || []).findIndex((n) => n.id === nodeId);
      if (idx >= 0) {
        node = a.nodes[idx];
        srcArea = a;
        if (a.id === destAreaId) return;
        break;
      }
    }
    if (!node || !srcArea) return;

    // Snapshot tag topology from wires before removing area-local visuals
    syncDownstreamFromWires(srcArea);
    const keptDownstream = String(node.downstream || '').trim();
    const myTag = String(node.conveyorTag || '').trim();
    inboundWires(srcArea, node.id).forEach((w) => {
      const src = (srcArea.nodes || []).find((n) => n.id === w.from);
      if (!src) return;
      // Keep upstream → this tag even after the visual wire is dropped
      if (myTag) src.downstream = myTag;
      else if (!src.downstream) {
        /* leave as-is */
      }
    });

    const idx = (srcArea.nodes || []).findIndex((n) => n.id === nodeId);
    if (idx < 0) return;
    srcArea.nodes.splice(idx, 1);
    // Drop area-local wire visuals involving this node (cannot draw cross-area yet)
    srcArea.wires = (srcArea.wires || []).filter((w) => w.from !== nodeId && w.to !== nodeId);
    // CRITICAL: Area is metadata — do not destroy physical topology
    node.downstream = keptDownstream;

    dest.nodes = dest.nodes || [];
    dest.nodes.push(node);

    // Rebuild same-area visuals wherever both ends co-reside; cross-area stays tag-only
    (tb.areas || []).forEach((a) => {
      syncDownstreamFromWires(a);
      syncWiresFromDownstream(a);
    });

    // Area assignment must NOT switch the displayed Area / viewport.
    // Engineer navigates Areas explicitly via the Area dropdown.
    // Apply Area default Safety Zone only when conveyor has none yet.
    if (!String(node.safetyZone || '').trim()) {
      const defZ = String(dest.defaultSafetyZone || '').trim();
      if (defZ) {
        node.safetyZone = defZ;
        if (!node.provenance) node.provenance = {};
        node.provenance.safetyZone = 'AREA_DEFAULT';
      }
    }
    tb.selectedId = node.id;
    if (Array.isArray(tb.selectedIds)) {
      tb.selectedIds = tb.selectedIds.includes(node.id) ? tb.selectedIds : [node.id];
    }
    invalidateSchematicHitGeometry();
    save();
    render();
    // Re-draw schematic with fresh offsets so hit == visible after lane re-separation
    try {
      drawSchematic(activeArea());
      drawWires();
      applyViewportZoom();
    } catch (_) { /* ignore */ }
    status(
      `Moved ${nodeLabel(node)} → area ${dest.name} (view unchanged · topology preserved` +
        (keptDownstream ? `; downstream ${keptDownstream}` : '') +
        ')'
    );
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
    sel.innerHTML = tb.areas
      .map(
        (a) =>
          `<option value="${a.id}" ${a.id === tb.activeAreaId ? 'selected' : ''}>${escapeHtml(a.name)}</option>`
      )
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
   * Display elbow radius must be >> belt stroke or a quarter-turn collapses into a
   * fat diagonal (sagitta ≈ 0.29·r; stroke 12–22px swallows r≈28). Prefer a clear L.
   */
  function curveDisplayMinRadius(n) {
    const sw = schematicStrokeWidth(n);
    // Sagitta ≈ 0.29·r must exceed ~stroke so the elbow reads as a turn, not a diagonal.
    return Math.max(72, sw * 4);
  }

  /** Inflate a RUN-derived arc radius for readability without changing sweep direction. */
  function inflateCurvePathForDisplay(pathCanvas, n) {
    if (!pathCanvas || !pathCanvas.length) return pathCanvas;
    const arcIdx = pathCanvas.findIndex((c) => String(c.cmd || '').toLowerCase() === 'arc');
    if (arcIdx < 0) return pathCanvas;
    const arc = pathCanvas[arcIdx];
    const r = Number(arc.radius);
    const minR = curveDisplayMinRadius(n);
    if (!(r > 0) || r >= minR) return pathCanvas;
    const grow = minR / r;
    const move = pathCanvas.find((c) => String(c.cmd || '').toLowerCase() === 'move');
    const cx = arc.center && arc.center.x != null ? Number(arc.center.x) : null;
    const cy = arc.center && arc.center.y != null ? Number(arc.center.y) : null;
    const out = pathCanvas.map((c) => ({ ...c }));
    const a = out[arcIdx];
    a.radius = minR;
    // Scale endpoints/center about chord midpoint so sweep_flag is unchanged
    const x0 = move ? Number(move.x) : Number(a.x);
    const y0 = move ? Number(move.y) : Number(a.y);
    const x1 = Number(a.x);
    const y1 = Number(a.y);
    const mx = (x0 + x1) / 2;
    const my = (y0 + y1) / 2;
    if (move) {
      const m = out.find((c) => String(c.cmd || '').toLowerCase() === 'move');
      if (m) {
        m.x = mx + (x0 - mx) * grow;
        m.y = my + (y0 - my) * grow;
      }
    }
    a.x = mx + (x1 - mx) * grow;
    a.y = my + (y1 - my) * grow;
    if (cx != null && cy != null) {
      a.center = { x: mx + (cx - mx) * grow, y: my + (cy - my) * grow };
    }
    // Preserve RUN sweep_deg / sweep_flag exactly — orientation comes from RUN b/Angle
    void n;
    return out;
  }

  /**
   * DISPLAY-ONLY quarter-circle for proven CURVE / 90° conveyors.
   * Always builds center from chord midpoint ± perpendicular; radius = chord/√2.
   * Uses existingArc.sweep_deg / node sweep for signed direction only — never
   * reuses RUN arc center (that preserves tangent stubs as hooks).
   * Does not mutate topology / canonical sourceX/Y / pathCanvas on the node.
   */
  function synthesizeCurveDisplayPath(n, opts) {
    const loose = !!(opts && opts.loose);
    let entry = n?.entryCanvas ? { x: Number(n.entryCanvas.x), y: Number(n.entryCanvas.y) } : null;
    let exit = n?.exitCanvas ? { x: Number(n.exitCanvas.x), y: Number(n.exitCanvas.y) } : null;
    // Loose fallback: derive anchors from pathCanvas endpoints when topology anchors missing
    if ((!entry || !exit) && loose && Array.isArray(n?.pathCanvas) && n.pathCanvas.length) {
      const mv = n.pathCanvas.find((c) => String(c.cmd || '').toLowerCase() === 'move');
      const last = n.pathCanvas[n.pathCanvas.length - 1];
      if (!entry && mv && mv.x != null) entry = { x: Number(mv.x), y: Number(mv.y) };
      if (!exit && last && last.x != null) exit = { x: Number(last.x), y: Number(last.y) };
    }
    if (!entry || !exit) return null;
    let dx = exit.x - entry.x;
    let dy = exit.y - entry.y;
    let chord = Math.hypot(dx, dy);
    if (!(chord > (loose ? 0.5 : 2))) return null;

    const existingArc = (n.pathCanvas || []).find((c) => String(c.cmd || '').toLowerCase() === 'arc');
    // Radius ALWAYS from chord: 90° → r = chord/√2
    let rCl = chord / Math.SQRT2;
    // Inflate tiny site-scale chords so the DISPLAY quarter-turn is a clear elbow.
    // Canonical entryCanvas/exitCanvas (PE/wires) stay untouched — only this path.
    // minR must beat belt stroke or the arc sagitta disappears into the stroke.
    const minR = curveDisplayMinRadius(n);
    if (rCl < minR) {
      const needChord = minR * Math.SQRT2;
      const grow = needChord / chord;
      const mx0 = (entry.x + exit.x) / 2;
      const my0 = (entry.y + exit.y) / 2;
      entry = { x: mx0 + (entry.x - mx0) * grow, y: my0 + (entry.y - my0) * grow };
      exit = { x: mx0 + (exit.x - mx0) * grow, y: my0 + (exit.y - my0) * grow };
      dx = exit.x - entry.x;
      dy = exit.y - entry.y;
      chord = Math.hypot(dx, dy);
      rCl = chord / Math.SQRT2;
    }

    let signedSweep = null;
    // Prefer RUN-derived signed sweep already projected into pathCanvas (Y-flip applied).
    if (existingArc && existingArc.sweep_deg != null && Number.isFinite(Number(existingArc.sweep_deg))) {
      signedSweep = Number(existingArc.sweep_deg);
    } else if (n.sweepDeg != null || n.sweep_deg != null) {
      signedSweep = Number(n.sweepDeg ?? n.sweep_deg);
    } else if (n.sourceAngle != null && (n.angleOut != null && n.angleOut !== '' || n.runB != null || n.b != null)) {
      const exitBearing = n.angleOut != null && n.angleOut !== ''
        ? Number(n.angleOut)
        : Number(n.runB ?? n.b);
      let d = exitBearing - Number(n.sourceAngle);
      while (d > 180) d -= 360;
      while (d < -180) d += 360;
      // Canvas Y-flip reverses sweep relative to RUN world
      signedSweep = -d;
    } else if (n.kind === 'conv_left') {
      signedSweep = 90;
    } else {
      signedSweep = -90;
    }
    if (!Number.isFinite(signedSweep) || Math.abs(signedSweep) < 1) {
      signedSweep = n.kind === 'conv_left' ? 90 : -90;
    }
    // Snap near-90 sweeps to a true quarter-turn
    if (Math.abs(Math.abs(signedSweep) - 90) <= 45) {
      signedSweep = signedSweep >= 0 ? 90 : -90;
    } else if (Math.abs(signedSweep) > 170) {
      signedSweep = signedSweep >= 0 ? 90 : -90;
    }

    // Quarter-circle center from chord midpoint ± perpendicular (display only)
    const mx = (Number(entry.x) + Number(exit.x)) / 2;
    const my = (Number(entry.y) + Number(exit.y)) / 2;
    const hx = dx / 2;
    const hy = dy / 2;
    const c1 = { x: mx - hy, y: my + hx };
    const c2 = { x: mx + hy, y: my - hx };
    const crossOf = (c) => (entry.x - c.x) * (exit.y - c.y) - (entry.y - c.y) * (exit.x - c.x);
    // Samples: sweep_deg -90 → flag 0; +90 → flag 1. flag 1 = CW in SVG Y-down.
    // signedSweep > 0 → flag 1 (CW); want positive cross for CW.
    const wantPositiveCross = signedSweep > 0;
    const center = (crossOf(c1) > 0) === wantPositiveCross ? c1 : c2;
    rCl = Math.hypot(entry.x - center.x, entry.y - center.y) || rCl;

    const sweep_flag = signedSweep > 0 ? 1 : 0;
    return [
      { cmd: 'move', x: Number(entry.x), y: Number(entry.y) },
      {
        cmd: 'arc',
        x: Number(exit.x),
        y: Number(exit.y),
        radius: Math.max(1, rCl),
        sweep_deg: signedSweep > 0 ? 90 : -90,
        sweep_flag,
        large_arc: 0,
        center: { x: center.x, y: center.y },
      },
    ];
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
    void n;
    return 'UNKNOWN';
  }

  /**
   * PL-2 — centralized UNKNOWN-orientation CURVE symbol constants (UI-only).
   * Diagonal angle is a SYMBOL meaning "curve; physical turn unresolved".
   * It MUST NOT be written into model provenance as physical orientation.
   */
  const CURVE_SYMBOL = Object.freeze({
    // Oblong body ≈ normal conveyor weight; length ~50% of prior symbolic glyph
    MIN_LENGTH_PX: 80,
    LENGTH_STROKE_MULT: 4.5,
    BODY_WIDTH_MIN: 18,
    BODY_WIDTH_MAX: 28,
    STROKE_MIN: 18,
    STROKE_MAX: 28,
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
  function curveDisplayDirectionRad(n) {
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

  function displayPathCanvasForNode(n) {
    // Curves: UNKNOWN physical turn → standardized diagonal CURVE symbol (never guessed elbow).
    if (isCurveNode(n)) {
      return curveUnknownOrientationSymbolPath(n);
    }
    return n?.pathCanvas || null;
  }

  /** Effective schematic pick stroke width (px). Visible belt stroke `sw` is unchanged. */
  /** Invisible selection target around belt centerline (~40–50px effective). */
  const SCHEMATIC_HIT_WIDTH = 50;

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
      const off = offsets[n.id] || { dx: 0, dy: 0 };
      let d = distanceToDisplayPath(pt, n, offsets);
      // Universal contract: identity label / body midpoint is always a hit target
      const mid0 = n.entryCanvas && n.exitCanvas
        ? { x: (n.entryCanvas.x + n.exitCanvas.x) / 2, y: (n.entryCanvas.y + n.exitCanvas.y) / 2 }
        : { x: Number(n.x) || 0, y: Number(n.y) || 0 };
      const mid = applyPresOffset(mid0, off);
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
    const collides = (box) => placed.some((p) => !(
      box.x2 < p.x1 || box.x1 > p.x2 || box.y2 < p.y1 || box.y1 > p.y2
    ));
    const results = [];
    // Selected first, then longer runs (prefer keeping primary labels)
    const ordered = labelCandidates.slice().sort((a, b) => {
      if (a.selected !== b.selected) return a.selected ? -1 : 1;
      return (b.priority || 0) - (a.priority || 0);
    });
    ordered.forEach((c) => {
      const w = approxW(c.tag);
      const offsets = [
        { dx: 0, dy: 0 }, // preferred — on body midpoint
        { dx: 0, dy: -(H + 4) }, // above
        { dx: 0, dy: (H + 4) }, // below
        { dx: w * 0.35, dy: -(H + 2) },
        { dx: -w * 0.35, dy: (H + 2) },
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
        // Collision remains — hide secondary labels; keep selected visible
        if (c.selected) {
          chosen = {
            x: c.x,
            y: c.y - (H + 6),
            box: { x1: c.x - w / 2, x2: c.x + w / 2, y1: c.y - H * 1.5, y2: c.y - H * 0.5 },
            hidden: false,
            offsetIndex: -1,
            forced: true,
          };
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
    if (!tb.laneSeparate) {
      listIn.forEach((n) => { if (n) n._layoutInitialized = true; });
      tb._presentationOffsets = offsets;
      tb.presentationLayoutFrozen = true;
      tb.forcePresentationRelayout = false;
      return offsets;
    }
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
      if (physicallyLinked(a, b) || endpointNear(a, b)) {
        const ra = String(a.renderKind || a.equipmentType || '').toUpperCase();
        const rb = String(b.renderKind || b.equipmentType || '').toUpperCase();
        if (ra.includes('CURVE') || rb.includes('CURVE')) return 'CURVE_ASSEMBLY';
        return 'CONNECTED_SERIAL';
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
    // Wider gap — reduce body/label collisions without inventing topology.
    const laneGap = 88;
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

  function drawSchematic(area) {
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
    const debug = tb.viewMode === 'geom-debug' || !!tb.layers?.physical;
    let html = '';
    const labelCandidates = [];
    nodes.forEach((n) => {
      const off = offsets[n.id] || { dx: 0, dy: 0 };
      // Prefer proven pathCanvas arc; synthesize quarter-turn for CURVE when degenerate
      const displayPath = displayPathCanvasForNode(n);
      let d = offsetPathD(displayPath, off);
      if (!d && n.entryCanvas && n.exitCanvas && !isCurveNode(n)) {
        const a = applyPresOffset(n.entryCanvas, off);
        const b = applyPresOffset(n.exitCanvas, off);
        d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
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
      const sw = isCurveNode(n) ? curveSymbolStrokeWidth(n) : schematicStrokeWidth(n);
      const sel = n.id === tb.selectedId || (tb.selectedIds || []).includes(n.id);
      const amb = (n.ambiguousInbound || []).length > 0;
      const cp = normalizeControlPanel(n.controlPanel);
      const cpMatch = nodeMatchesCpFilter(n);
      let cls = `tb-schematic-body tb-rk-${rk}`;
      if (isCurveNode(n)) cls += ' tb-rk-curve';
      if (sel) cls += ' selected';
      if (amb) cls += ' tb-ambiguous';
      if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') cls += ' tb-display-context tb-external-ref';
      if (cp === 'CP1' || cp === 'CP2' || cp === 'CP3') cls += ` tb-cp-${cp}`;
      else if (cp === 'Other') cls += ' tb-cp-Other';
      if (cpFilterActive()) cls += cpMatch ? ' tb-cp-match' : ' tb-cp-dim';
      const tag = (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE')
        ? (`→ External ${(n.conveyorTag || n.label || '').trim()}`.trim() || '→ External')
        : ((n.conveyorTag || n.label || '').trim() || 'P???');
      const mid0 = n.entryCanvas && n.exitCanvas
        ? { x: (n.entryCanvas.x + n.exitCanvas.x) / 2, y: (n.entryCanvas.y + n.exitCanvas.y) / 2 }
        : { x: Number(n.x) || 0, y: Number(n.y) || 0 };
      const mid = applyPresOffset(mid0, off);
      const tip = isCurveNode(n)
        ? `${tag} · ${CURVE_SYMBOL.TOOLTIP_SUFFIX}`
        : (cp ? `${tag} · ${cp}` : tag);
      html += `<path class="${cls}" data-id="${escapeHtml(n.id)}" d="${d}" stroke-width="${sw}"><title>${escapeHtml(tip)}</title></path>`;
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
        if (isCurveNode(n) && curveOrientationStatus(n) === 'UNKNOWN') {
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
        });
      }
    });
    tb._schematicLabelPos = {};
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
      // Identity label is a FIRST-CLASS selection target (universal contract)
      html += `<text class="tb-schematic-label tb-schematic-label-hit" data-id="${escapeHtml(lab.id)}" x="${lab.x}" y="${lab.y}">${tipAttr}${escapeHtml(lab.tag)}</text>`;
      // Invisible hit disc behind the number so short tags remain easy to click
      html += `<circle class="tb-schematic-label-disc" data-id="${escapeHtml(lab.id)}" cx="${lab.x}" cy="${lab.y}" r="16" />`;
      if (lab.secondary) {
        const secCls = lab.secondary === 'CURVE'
          ? 'tb-schematic-label-sec tb-curve-badge'
          : 'tb-schematic-label-sec';
        html += `<text class="${secCls}" data-id="${escapeHtml(lab.id)}" x="${lab.x}" y="${lab.y + 12}">${escapeHtml(lab.secondary)}</text>`;
      }
    });
    // Mate marks (EXIT▶◀ENTRY): informational only; hide when relationships layer off
    if (tb.layers?.relationships) {
      (area?.wires || []).forEach((w) => {
        if (!w.physical) return;
        const conf = String(w.confidence || '').toUpperCase();
        if (!(conf === 'CONFIRMED' || conf.includes('HIGH'))) return;
        const a = (area.nodes || []).find((n) => n.id === w.from);
        const b = (area.nodes || []).find((n) => n.id === w.to);
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
    const info = fitViewToNodes(useNodes, {
      mode: 'visible',
      paddingFrac: 0.1,
      minZoom: tb.physicalLayout ? 0.05 : 0.35,
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

  function render() {
    ensureArea();
    refreshAreaSelect();
    const area = activeArea();
    const empty = $('tb-canvas-empty');
    const host = $('tb-nodes');
    const wires = $('tb-wires');
    if (!host || !wires) return;

    if (!area || (!area.nodes.length && !tb.areas.length)) {
      if (empty) empty.classList.remove('hidden');
    } else if (empty) {
      empty.classList.toggle('hidden', !!(area && area.nodes.length));
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
    drawSchematic(area);
    drawWires();
    renderInspector();
    setWorkflowStep(tb.workflow?.apply ? 'build' : (tb.workflow?.autobuild ? 'review' : 'review'));
    renderTopologyTable();
    renderInventoryPanel();
    renderValidationPanel();
    const autoEl = $('tb-auto-connect');
    if (autoEl) autoEl.checked = !!tb.autoConnectNew;
    // Explicit Pass 2 (and future) update hook — prefer this over DOM MutationObserver
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

  function drawWires(temp) {
    const svg = $('tb-wires');
    const host = $('tb-nodes');
    const canvas = $('tb-canvas');
    if (!svg || !host) return;
    const area = activeArea();
    ensureCanvasExtents(area);
    const showRel = !!tb.layers?.relationships;
    canvas?.classList.toggle('tb-hide-relationships', !showRel);
    const w = Math.max(host.scrollWidth || 0, host.offsetWidth || 0, parseInt(host.style.minWidth || '0', 10) || 0);
    const h = Math.max(host.scrollHeight || 0, host.offsetHeight || 0, parseInt(host.style.minHeight || '0', 10) || 0);
    svg.setAttribute('width', String(w));
    svg.setAttribute('height', String(h));
    svg.style.width = `${w}px`;
    svg.style.height = `${h}px`;
    svg.style.pointerEvents = 'none';
    let html = '';
    // Visualization-only: when relationships are hidden, skip all wires except temp connect rubber-band.
    // Wire data on the model is never deleted.
    if (!showRel && !(temp && temp.from && temp.to)) {
      svg.innerHTML = '';
      return;
    }
    (area?.wires || []).forEach((wire) => {
      if (!showRel) return;
      const a = portCenter(wire.from, 'out');
      const b = portCenter(wire.to, wire.toPort || 'in');
      if (!a || !b) return;
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      const conf = String(wire.confidence || '').toUpperCase();
      // Confirmed physical mates: endpoints coincide — mate mark drawn in schematic layer; no Bezier wire
      if (wire.physical && (conf === 'CONFIRMED' || conf.includes('HIGH')) && dist < 12) {
        return;
      }
      let d;
      if (wire.physical && dist < 80) {
        // Short mating stub — reads as physically joined EXIT▶◀ENTRY
        d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
      } else if (wire.physical) {
        // Still-disconnected physical candidate — thin dashed cue only (not topology invention)
        d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
      } else {
        const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
        d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
      }
      let cls = 'tb-wire';
      if (wire.physical) cls += ' tb-physical';
      if (conf === 'CONFIRMED') cls += ' tb-conf-confirmed';
      else if (conf.includes('HIGH')) cls += ' tb-conf-high';
      else if (conf.includes('AMBIG')) cls += ' tb-conf-ambiguous';
      const tip = wire.physical
        ? `EXIT ▶◀ ENTRY · ${wire.confidence || 'physical'}${wire.distance != null ? ` · d=${wire.distance}` : ''}`
        : 'topology wire';
      html += `<path class="${cls}" d="${d}"><title>${escapeHtml(tip)}</title></path>`;
    });
    if (temp && temp.from && temp.to) {
      const dx = Math.max(40, Math.abs(temp.to.x - temp.from.x) * 0.45);
      const d = `M ${temp.from.x} ${temp.from.y} C ${temp.from.x + dx} ${temp.from.y}, ${temp.to.x - dx} ${temp.to.y}, ${temp.to.x} ${temp.to.y}`;
      html += `<path class="tb-wire tb-wire-temp" d="${d}" />`;
    }
    svg.innerHTML = html;
  }

  /** Select a node. Pass { additive: true } for Ctrl/Meta toggle-select (Shift is connect, not select). */
  function selectNode(id, { additive } = {}) {
    if (!id) {
      tb.selectedId = null;
      tb.selectedIds = [];
      tb.selectedDeviceId = null;
      render();
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
    render();
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
    save();
    render();
    status(`Connected ${from.label || fromId} → ${to.label || toId} (${port})`);
    maybeConfirmMerge(to);
  }

  function bindToolbar() {
    // Toolbar first — never gated on canvas existing (fixes silent New Area / Build POC)
    $('tb-area-select')?.addEventListener('change', (e) => {
      tb.activeAreaId = e.target.value;
      tb.selectedId = null;
      // Drop prior Area pan — do not retain another Area's scroll offset
      save();
      render();
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
        const def = `Transport_${tb.areas.length + 1}`;
        const name = await askText(
          'Create Area',
          'Area Name (operational conveyor grouping — not a Safety Zone):',
          def
        );
        if (name === null || !(String(name).trim())) return;
        const areaName = String(name).trim();
        const existing = listSafetyZoneNames();
        // Seed from current Area/layout name (ORNCCP2_Area → ORNCCP2_ESZoneN). Suggestion only.
        const zoneHint = nextSafetyZoneName(areaName);
        const zonePrompt = existing.length
          ? `Default Safety Zone for “${areaName}”.\n`
            + `Suggested: ${zoneHint}\n`
            + `Existing: ${existing.slice(0, 8).join(', ')}${existing.length > 8 ? '…' : ''}\n`
            + 'Pick an existing name, or type a new Safety Zone name to create it.\n'
            + 'Area ≠ Safety Zone — engineer may edit; not permanently derived from Area.'
          : `Default Safety Zone for “${areaName}” (suggested from Area name).\n`
            + 'Area ≠ Safety Zone — conveyor-level value remains authoritative and editable.';
        const zoneIn = await askText('Safety Zone', zonePrompt, zoneHint);
        if (zoneIn === null) return; // cancelled
        const defaultZone = String(zoneIn || '').trim();
        if (defaultZone) ensureSafetyZone(defaultZone);
        const a = {
          id: uid('area'),
          name: areaName,
          nodes: [],
          wires: [],
          defaultSafetyZone: defaultZone,
        };
        tb.areas.push(a);
        tb.activeAreaId = a.id;
        tb.selectedId = null;
        tb.selectedDeviceId = null;
        if (defaultZone) {
          tb.buildContext = tb.buildContext || {};
          tb.buildContext.areaId = a.id;
          tb.buildContext.areaName = a.name;
          tb.buildContext.safetyZone = defaultZone;
        }
        save();
        render();
        status(
          `Area “${a.name}” ready`
          + (defaultZone ? ` · default Safety Zone “${defaultZone}”` : '')
          + ' — topology Safety Zone dropdown remains authoritative'
        );
      } catch (err) {
        status(`New area error: ${err?.message || err}`);
        try { await showInfo('New area failed', String(err?.message || err)); } catch (_) { /* ignore */ }
      }
    });

    $('tb-area-rename')?.addEventListener('click', async () => {
      const a = activeArea();
      if (!a) return;
      const name = await askText('Rename area', 'New area name:', a.name);
      if (name === null || !(name || '').trim()) return;
      a.name = name.trim();
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
      const ok = await askYesNo('Delete area', `Delete area “${a.name}” and its canvas?`);
      if (!ok) return;
      tb.areas = tb.areas.filter((x) => x.id !== a.id);
      tb.activeAreaId = tb.areas[0]?.id || null;
      tb.selectedId = null;
      tb.selectedDeviceId = null;
      resetPeRoleCheckboxes();
      ensureArea();
      save();
      render();
      status(`Deleted area “${a.name}”`);
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
          areaRequired: !!n.areaRequired,
          esZoneRequired: !!n.esZoneRequired,
          pe_a: n.pe_a || '',
          pe_b: n.pe_b || '',
          pe_c: n.pe_c || '',
          jam_pe: n.jam_pe || '',
          allow_undefined_pe: !!n.allow_undefined_pe,
          devices,
          placeholderTag: !!n.placeholderTag,
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
      let res;
      if (typeof window.applyTransportMergesToAutogen === 'function') {
        res = await window.applyTransportMergesToAutogen({ graph });
      } else {
        const api = window.fortnaAPI || window.api;
        if (!api?.transportApplyAutogen) {
          await showInfo('Apply to Autogen', 'Desktop IPC missing — restart Site Forge.');
          return;
        }
        res = await api.transportApplyAutogen({ graph });
      }
      if (!res?.ok) {
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
      $('tb-goto-build-plc')?.classList.remove('hidden');
      save(); // persist workflow.apply without dirtying hub
      const areas = (res.areas_applied || []).join(', ') || '(none)';
      const go = await askYesNo(
        'Applied to Autogen',
        `${res.summary || 'Transport applied to workbook.'}\n\n`
          + `Areas: ${areas}\n`
          + `Workbook: ${res.workbook_path || 'workspace/autogen_workbook.json'}\n\n`
          + 'Next step: Build PLC (Export L5X Package) on the PLC Autogen tab.\n\n'
          + 'Open PLC Autogen now?'
      );
      status(`Applied → Autogen — ${go ? 'opening Build PLC' : 'ready for Build PLC'} · hash ${hashAfter}`);
      if (go) {
        try {
          if (typeof window.activateTab === 'function') window.activateTab('autogen');
          else {
            document.querySelector('[data-tab="autogen"]')?.click();
          }
          setTimeout(() => {
            const btn = $('btn-autogen-from-run');
            if (btn) {
              btn.classList.add('ring-2', 'ring-amber-400');
              btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }, 200);
        } catch (_) { /* ignore */ }
      }
    } catch (err) {
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
        const area = activeArea();
        if (!area) return;
        const pt = canvasPointFromEvent(ev);
        const primary = area.nodes.find((x) => x.id === tb.moving.id);
        if (!primary) return;
        const origins = tb.moving.origins;
        if (origins && origins.length) {
          // ox/oy captured as pt - n.x at drag start → nx/ny is primary target
          const nx = pt.x - tb.moving.ox;
          const ny = pt.y - tb.moving.oy;
          const ddx = nx - (tb.moving.startX || 0);
          const ddy = ny - (tb.moving.startY || 0);
          origins.forEach((o) => {
            const n = area.nodes.find((x) => x.id === o.id);
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
          ensureCanvasExtents(area);
          drawSchematic(area);
          drawWires();
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
          ensureCanvasExtents(area);
          drawWires();
        }
      }
      if (tb.linkFrom) {
        const a = portCenter(tb.linkFrom.nodeId, 'out');
        if (a) {
          const pt = canvasPointFromEvent(ev);
          drawWires({
            from: a,
            to: { x: pt.x, y: pt.y },
          });
        }
      }
    });

    window.addEventListener('mouseup', (ev) => {
      if (tb.moving) {
        tb.moving = null;
        tb._moveHistoryPushed = false;
        save();
        // Refresh schematic after group move settles
        try { drawSchematic(activeArea()); drawWires(); } catch (_) { /* ignore */ }
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
    load();
    ensureArea();
    migrateGraphTopology();
    bindUi();
    paintPaletteIcons();
    render();
    status('Transport Build ready — Build Chain / Continue Run for rapid topology.');
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
    ensureCanvasExtents,
    portCenter,
    collectValidation,
    renderValidationPanel,
    renderInventoryPanel,
    renderTopologyTable,
    renderInspector,
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
    drawSchematic,
    invalidateSchematicHitGeometry,
    requestPresentationRelayout,
    schematicPathD,
    pickSchematicNodeAt,
    distanceToDisplayPath,
    SCHEMATIC_HIT_WIDTH,
    CURVE_SYMBOL,
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
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
