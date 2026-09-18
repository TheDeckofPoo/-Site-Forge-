/**
 * Safety Build — first-class Site Forge subsystem.
 *
 * Canonical SafetyModel (refs to Areas / Conveyors / HardwareIO — no duplicates).
 * AUTO DISCOVER → ENGINEER REVIEW → APPLY → GENERATE PLC
 */
(function () {
  const ORIGIN_LABEL = {
    AUTO_RUN_PROVEN: 'AUTO — RUN PROVEN',
    ENGINEER_ASSIGNED: 'ENGINEER ASSIGNED',
    SUGGESTED_DIGIT_MATCH: 'SUGGESTED',
    UNRESOLVED: 'UNRESOLVED',
  };

  const KIND_ORDER = ['ESTOP', 'ESR', 'MCR', 'CS', 'ESLS', 'OTHER'];
  const KIND_LABEL = {
    ESTOP: 'ESTOPS',
    ESR: 'ESR',
    MCR: 'MCR',
    CS: 'CONTROL STATIONS',
    ESLS: 'ESLS',
    OTHER: 'OTHER',
  };

  const DEVICE_PROVENANCE_KEYS = [
    'safetyZoneRef', 'status', 'source', 'sourceTable', 'originalName',
    'engineerName', 'physicalEndpoint', 'classification', 'confidence',
    'evidence', 'physicalIoRef', 'origin', 'kind',
  ];

  const state = {
    model: null,
    selectedZoneId: null,
    filter: '',
    inventoryFilter: '',
    dirty: false,
    /** Zone names engineer deleted — must not reappear from Transport canvas seeds. */
    deletedZones: new Set(),
  };

  function $(id) {
    return document.getElementById(id);
  }

  function api() {
    return window.fortnaAPI || window.api || {};
  }

  function status(msg) {
    const el = $('sb-status');
    if (el) el.textContent = msg || '';
  }

  function ensureAutogenState() {
    if (!window.autogenState) window.autogenState = {};
    return window.autogenState;
  }

  function transportZonesFromCanvas() {
    try {
      const raw = localStorage.getItem('siteforge.transportBuild.v2')
        || localStorage.getItem('siteforge.transportBuild.v1');
      if (!raw) return [];
      const data = JSON.parse(raw);
      const zoneMap = new Map();
      (data.areas || []).forEach((area) => {
        const aname = area.name || '';
        (area.nodes || []).forEach((n) => {
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
      (data.safetyZones || []).forEach((z) => {
        const nm = String(z.name || '').trim();
        if (!nm) return;
        if (!zoneMap.has(nm)) zoneMap.set(nm, { name: nm, area: '', conveyors: [], members: [] });
      });
      return [...zoneMap.values()];
    } catch (_) {
      return [];
    }
  }

  function areaConveyorsFromWorkbook() {
    const wb = ensureAutogenState().workbook || {};
    const map = {};
    (wb.conveyors || []).forEach((c) => {
      const an = String(c.main_area || c.area || '').trim();
      const cn = String(c.clean_name || c.name || c.conveyor || '').trim();
      if (an && cn) {
        if (!map[an]) map[an] = [];
        if (!map[an].includes(cn)) map[an].push(cn);
      }
    });
    return map;
  }

  function buildClientModel() {
    /** Client-side SafetyModel assembly (mirrors Python fortna_safety_model). */
    const AS = ensureAutogenState();
    const wb = AS.workbook || {};
    const eng = AS.safety_build || wb.safety_build || { zones: [] };
    const transportZones = transportZonesFromCanvas();
    const areaConvs = areaConveyorsFromWorkbook();
    const areas = Array.isArray(wb.areas) ? wb.areas.slice() : [];
    // Prefer live discovered devices; workbook cache is fallback only
    const live = normalizeDeviceList(AS.safetyDevices || []);
    const cached = normalizeDeviceList(eng.devices || []);
    const devices = live.length ? live : cached;

    // Merge transport + engineer zones (skip engineer-deleted names)
    const deleted = state.deletedZones;
    const byName = new Map();
    transportZones.forEach((z) => {
      if (deleted.has(String(z.name || '').trim())) return;
      byName.set(z.name, {
        id: z.name,
        name: z.name,
        areaRef: z.area || '',
        areaOrigin: 'AUTO_RUN_PROVEN',
        conveyorRefs: [...(z.conveyors || [])],
        conveyorsOrigin: (z.conveyors || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        members: [...(z.members || [])],
        membersOrigin: (z.members || []).length ? 'ENGINEER_ASSIGNED' : 'UNRESOLVED',
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        resetSource: z.area ? `${z.area}.Reset` : '',
        silenceSource: z.area ? `${z.area}.Silence` : '',
        resetOrigin: z.area ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        silenceOrigin: z.area ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        suggestions: [],
        engineerEdited: false,
        status: 'REVIEW_REQUIRED',
        fields: {},
      });
    });
    (eng.zones || []).forEach((ez) => {
      const name = String(ez.name || ez.id || '').trim();
      if (!name || deleted.has(name)) return;
      const cur = byName.get(name) || {
        id: name,
        name,
        areaRef: '',
        conveyorRefs: [],
        members: [],
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        resetSource: '',
        silenceSource: '',
        suggestions: [],
        status: 'REVIEW_REQUIRED',
        fields: {},
      };
      if (ez.area || ez.areaRef) {
        cur.areaRef = ez.area || ez.areaRef;
        cur.areaOrigin = ez.engineerEdited ? 'ENGINEER_ASSIGNED' : (cur.areaOrigin || 'AUTO_RUN_PROVEN');
      }
      const convs = ez.conveyorRefs || ez.conveyors;
      if (Array.isArray(convs) && convs.length) {
        cur.conveyorRefs = [...convs];
        cur.conveyorsOrigin = ez.conveyorsOrigin || 'ENGINEER_ASSIGNED';
      }
      if (Array.isArray(ez.members)) {
        cur.members = [...ez.members];
        cur.membersOrigin = ez.membersOrigin || 'ENGINEER_ASSIGNED';
        cur.engineerEdited = true;
      }
      if (ez.resetSource || ez.reset_source) {
        cur.resetSource = ez.resetSource || ez.reset_source;
        cur.resetOrigin = 'ENGINEER_ASSIGNED';
      }
      if (ez.silenceSource || ez.silence_source) {
        cur.silenceSource = ez.silenceSource || ez.silence_source;
        cur.silenceOrigin = 'ENGINEER_ASSIGNED';
      }
      if (!cur.resetSource && cur.areaRef) cur.resetSource = `${cur.areaRef}.Reset`;
      if (!cur.silenceSource && cur.areaRef) cur.silenceSource = `${cur.areaRef}.Silence`;
      // Fill conveyors from area map when empty
      if (!cur.conveyorRefs.length && cur.areaRef && areaConvs[cur.areaRef]) {
        cur.conveyorRefs = [...areaConvs[cur.areaRef]];
        cur.conveyorsOrigin = 'AUTO_RUN_PROVEN';
      }
      byName.set(name, cur);
    });

    // Ensure area-named default zones exist for each *current* workbook area only
    const areaSet = new Set(areas.map((a) => String(a || '').trim()).filter(Boolean));
    areas.forEach((a) => {
      const an = String(a || '').trim();
      if (!an) return;
      const stem = an.replace(/_Area$/i, '');
      const preferred = `${stem}_ESZone1`;
      if (deleted.has(preferred)) return;
      const existing = [...byName.keys()].find((k) => {
        const kl = k.toLowerCase();
        return kl === preferred.toLowerCase()
          || kl.startsWith(`${stem.toLowerCase()}_eszone`);
      });
      if (existing) return;
      if (!byName.has(preferred)) {
        byName.set(preferred, {
          id: preferred,
          name: preferred,
          areaRef: an,
          areaOrigin: 'AUTO_RUN_PROVEN',
          conveyorRefs: [...(areaConvs[an] || [])],
          conveyorsOrigin: (areaConvs[an] || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
          members: [],
          membersOrigin: 'UNRESOLVED',
          eStops: [],
          esrDevices: [],
          mcrDevices: [],
          resetSource: `${an}.Reset`,
          silenceSource: `${an}.Silence`,
          resetOrigin: 'AUTO_RUN_PROVEN',
          silenceOrigin: 'AUTO_RUN_PROVEN',
          suggestions: [],
          engineerEdited: false,
          status: 'REVIEW_REQUIRED',
          fields: {},
        });
      }
    });

    // Drop stale zones from prior projects (saved localStorage) unless their Area
    // still exists on this project OR they appear on the Transport canvas.
    const transportNames = new Set(transportZones.map((z) => String(z.name || '').trim()));
    for (const [name, z] of [...byName.entries()]) {
      const area = String(z.areaRef || '').trim();
      const keep = transportNames.has(name)
        || (area && areaSet.has(area))
        || (areaSet.size === 0 && transportNames.size === 0 && z.engineerEdited);
      // If we have current areas and this zone's area is gone → drop
      if (areaSet.size > 0 && area && !areaSet.has(area) && !transportNames.has(name)) {
        byName.delete(name);
        continue;
      }
      // Orphan zone with no area and not on canvas → drop
      if (!keep && areaSet.size > 0 && !transportNames.has(name)) {
        byName.delete(name);
      }
    }

    const zones = [...byName.values()].map((z) => {
      splitZoneMembers(z);
      const fields = {
        Area: z.areaRef ? 'READY' : 'UNRESOLVED',
        Conveyors: (z.conveyorRefs || []).length ? 'READY' : 'NONE',
        SafetyDevices: (z.members || []).length ? 'READY' : ((z.conveyorRefs || []).length ? 'UNRESOLVED' : 'NONE'),
        'E-Stops': z.eStops.length ? 'READY' : ((z.conveyorRefs || []).length ? 'UNRESOLVED' : 'NONE'),
        ESR: z.esrDevices.length ? 'READY' : 'N/A',
        MCR: z.mcrDevices.length ? 'READY' : 'N/A',
        CS: (z.csDevices || []).length ? 'READY' : 'N/A',
        ESLS: (z.eslsDevices || []).length ? 'READY' : 'N/A',
        Reset: z.resetSource ? 'READY' : 'UNRESOLVED',
        Silence: z.silenceSource ? 'READY' : 'UNRESOLVED',
        'Physical I/O': 'READY',
        'AOI dependencies': 'READY',
        'Datatype dependencies': 'READY',
      };
      z.fields = fields;
      const hard = [];
      if (fields.Area === 'UNRESOLVED') hard.push('Area');
      if (fields.SafetyDevices === 'UNRESOLVED') hard.push('SafetyDevices');
      if (fields.Reset === 'UNRESOLVED') hard.push('Reset');
      if (fields.Silence === 'UNRESOLVED') hard.push('Silence');
      z.hard_missing = hard;
      // READY only when members are persisted on the zone model (not empty DOM).
      // Global hub still REVIEW if other devices remain unassigned / draft dirty.
      z.status = hard.length || !(z.members || []).length ? 'REVIEW_REQUIRED' : 'READY';
      if (!(z.conveyorRefs || []).length && !(z.members || []).length) z.status = 'REVIEW_REQUIRED';
      // Draft edits not yet Applied → conspicuous REVIEW on the zone chip
      if (z.status === 'READY' && state.dirty) {
        z.status = 'REVIEW_REQUIRED';
        z._draftReady = true; // members present but Apply Safety required
      }
      // Digit-match suggestions
      const digs = new Set();
      (z.conveyorRefs || []).forEach((c) => (String(c).match(/\d{2,4}/g) || []).forEach((d) => digs.add(d)));
      (String(z.areaRef).match(/\d{2,4}/g) || []).forEach((d) => digs.add(d));
      const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
      z.suggestions = (devices || [])
        .map((d) => (typeof d === 'string' ? { name: d } : d))
        .filter((d) => d && d.name && !assigned.has(String(d.name).toUpperCase()))
        .filter((d) => (String(d.name).match(/\d{2,4}/g) || []).some((x) => digs.has(x)))
        .map((d) => ({
          name: d.name,
          kind: d.kind || classifyDevName(d.name) || 'OTHER',
          origin: 'SUGGESTED_DIGIT_MATCH',
        }));
      return z;
    });

    // Zone membership → device.safetyZoneRef / status / assignment origin
    const memberToZone = new Map();
    const memberOrigin = new Map();
    zones.forEach((z) => {
      const zOrigin = z.membersOrigin || (z.engineerEdited ? 'ENGINEER_ASSIGNED' : 'AUTO_RUN_PROVEN');
      (z.members || []).forEach((m) => {
        const key = String(m).toUpperCase();
        if (!memberToZone.has(key)) {
          memberToZone.set(key, z.name);
          memberOrigin.set(key, zOrigin);
        }
      });
    });

    const deviceList = (devices || []).map((d) => {
      const base = typeof d === 'string'
        ? { name: d, kind: classifyDevName(d) || 'OTHER' }
        : { ...d };
      const key = String(base.name || '').toUpperCase();
      const zoneRef = memberToZone.get(key) || base.safetyZoneRef || '';
      const assignOrigin = zoneRef
        ? (memberOrigin.get(key) || base.origin || 'AUTO_RUN_PROVEN')
        : (base.origin || 'UNRESOLVED');
      base.kind = base.kind || classifyDevName(base.name) || 'OTHER';
      base.classification = base.classification || base.kind;
      base.safetyZoneRef = zoneRef || null;
      if (zoneRef) {
        if (assignOrigin === 'ENGINEER_ASSIGNED') {
          base.status = 'ENGINEER_ASSIGNED';
          base.origin = 'ENGINEER_ASSIGNED';
        } else {
          base.status = 'AUTO_RESOLVED';
          if (!base.origin || base.origin === 'UNRESOLVED') base.origin = assignOrigin || 'AUTO_RUN_PROVEN';
        }
      } else {
        base.status = 'UNASSIGNED';
        base.safetyZoneRef = null;
      }
      return base;
    });

    const unassigned = deviceList.filter((d) => d && d.name && d.status === 'UNASSIGNED');
    const autoResolved = deviceList.filter((d) => d.status === 'AUTO_RESOLVED');
    const engAssigned = deviceList.filter((d) => d.status === 'ENGINEER_ASSIGNED');
    const kindOf = (d) => d.kind || classifyDevName(d.name) || 'OTHER';
    const devicesFound = deviceList.length;
    const assignedN = devicesFound - unassigned.length;
    const completionPct = devicesFound
      ? Math.round((1000 * assignedN) / devicesFound) / 10
      : 0;

    const inventory = {};
    KIND_ORDER.forEach((k) => { inventory[k] = []; });
    deviceList.forEach((d) => {
      const k = KIND_ORDER.includes(kindOf(d)) ? kindOf(d) : 'OTHER';
      inventory[k].push({
        name: d.name,
        kind: k,
        status: d.status,
        safetyZoneRef: d.safetyZoneRef || '',
        origin: d.origin || '',
      });
    });

    return {
      kind: 'SafetyModel',
      version: 1,
      devices: deviceList,
      zones,
      unassignedDevices: unassigned.map((d) => d.name),
      inventory,
      counts: {
        zones: zones.length,
        ready: zones.filter((z) => z.status === 'READY').length,
        review_required: zones.filter((z) => z.status === 'REVIEW_REQUIRED').length,
        devices: devicesFound,
        devices_found: devicesFound,
        estops: deviceList.filter((d) => kindOf(d) === 'ESTOP').length,
        esr: deviceList.filter((d) => kindOf(d) === 'ESR').length,
        mcr: deviceList.filter((d) => kindOf(d) === 'MCR').length,
        cs: deviceList.filter((d) => kindOf(d) === 'CS').length,
        esls: deviceList.filter((d) => kindOf(d) === 'ESLS').length,
        unassigned_estops: unassigned.filter((d) => kindOf(d) === 'ESTOP').length,
        unassigned: unassigned.length,
        automatically_resolved: autoResolved.length,
        engineer_assigned: engAssigned.length,
        completion_pct: completionPct,
        unresolved_io: zones.filter((z) => (z.hard_missing || []).includes('SafetyDevices')).length,
      },
    };
  }

  function splitZoneMembers(z) {
    const members = z.members || [];
    z.eStops = members.filter((m) => classifyDevName(m) === 'ESTOP');
    z.esrDevices = members.filter((m) => classifyDevName(m) === 'ESR');
    z.mcrDevices = members.filter((m) => classifyDevName(m) === 'MCR');
    z.csDevices = members.filter((m) => classifyDevName(m) === 'CS');
    z.eslsDevices = members.filter((m) => classifyDevName(m) === 'ESLS');
    return z;
  }

  function classifyDevName(name) {
    const u = String(name || '').trim().toUpperCase().replace(/-/g, '_');
    if (!u) return '';
    if (u.includes('ESLS')) return 'ESLS';
    if (/ESR\d*|ESR_/.test(u) || u.includes('_ESR') || u.startsWith('ESR')) return 'ESR';
    if (/MCR\d*/.test(u) || u.includes('_MCR') || u.startsWith('MCR')) return 'MCR';
    if (/^CP\d+_CS\d*$/.test(u) || /_CS\d*$/.test(u)) return 'CS';
    // T_2ES, CP2_ES…, 2ES, ES400, ES406
    if (
      /^T_\d+ES\d*\w*$/.test(u)
      || /^CP\d+_ES\d*\w*$/.test(u)
      || /^ES\d[\w]*$/.test(u)
      || /^\d+ES\d*\w*$/.test(u)
      || /(^|_)ES\d/.test(u)
    ) return 'ESTOP';
    return '';
  }

  function normalizeDeviceList(list) {
    const out = [];
    const seen = new Set();
    (list || []).forEach((d) => {
      const name = typeof d === 'string'
        ? d
        : (d?.name || d?.Desc || d?.Part || d?.tag || '');
      const nm = String(name || '').trim();
      if (!nm || seen.has(nm.toUpperCase())) return;
      const kind = (typeof d === 'object' && (d?.kind || d?.classification))
        || classifyDevName(nm);
      if (!kind) return; // only Safety-looking names
      seen.add(nm.toUpperCase());
      const row = {
        name: nm,
        kind,
        origin: (d && typeof d === 'object' && d.origin) || 'AUTO_RUN_PROVEN',
      };
      if (d && typeof d === 'object') {
        DEVICE_PROVENANCE_KEYS.forEach((k) => {
          if (d[k] !== undefined && d[k] !== null && d[k] !== '') {
            if (k === 'kind' || k === 'origin') return; // already set
            row[k] = d[k];
          }
        });
        if (d.classification && !row.classification) row.classification = d.classification;
      }
      out.push(row);
    });
    return out;
  }

  async function loadDevicesFromRun() {
    const A = api();
    const AS = ensureAutogenState();
    let lastErr = '';

    // 1) Canonical SafetyModel (EStop.asc via fortna_safety_model.py)
    if (typeof A.buildSafetyModel === 'function') {
      try {
        const res = await A.buildSafetyModel({});
        if ((res?.ok || res?.success) && res.model) {
          const mapped = normalizeDeviceList(res.model.devices || []);
          if (mapped.length) {
            AS.safetyDevices = mapped;
            // Keep devices on safety_build so rebuilds don't drop them
            if (!AS.safety_build) AS.safety_build = { zones: [] };
            AS.safety_build.devices = mapped;
            return mapped;
          }
          lastErr = 'SafetyModel returned 0 devices';
        } else {
          lastErr = res?.error || res?.message || 'buildSafetyModel failed';
        }
      } catch (err) {
        lastErr = err?.message || String(err);
      }
    } else {
      lastErr = 'buildSafetyModel API missing — restart Site Forge after update';
    }

    // 2) listDevices — scan ALL categories for ES*/ESR*/MCR*/T_*/CP*_ names
    if (typeof A.listDevices === 'function') {
      try {
        const res = await A.listDevices({});
        const list = res?.devices || res?.rows || res?.items || [];
        const mapped = normalizeDeviceList(list);
        if (mapped.length) {
          AS.safetyDevices = mapped;
          if (!AS.safety_build) AS.safety_build = { zones: [] };
          AS.safety_build.devices = mapped;
          return mapped;
        }
      } catch (_) { /* ignore */ }
    }

    // 2b) Hardware I/O engineer Names (T_2ES, CP2_ESR1, T_2MCR1, CP2_CS, …)
    if (typeof A.getHardwareIo === 'function') {
      try {
        const res = await A.getHardwareIo();
        const names = [];
        const walk = (obj) => {
          if (!obj || typeof obj !== 'object') return;
          if (Array.isArray(obj)) {
            obj.forEach(walk);
            return;
          }
          const nm = obj.engineer_name || obj.engineerName || obj.Name || obj.name || obj.tag;
          if (nm && classifyDevName(String(nm))) names.push(String(nm));
          Object.values(obj).forEach((v) => {
            if (v && typeof v === 'object') walk(v);
          });
        };
        walk(res);
        const mapped = normalizeDeviceList(names);
        if (mapped.length) {
          // Merge with any prior list
          const prev = normalizeDeviceList(AS.safetyDevices || []);
          const by = new Map(prev.map((d) => [d.name.toUpperCase(), d]));
          mapped.forEach((d) => { if (!by.has(d.name.toUpperCase())) by.set(d.name.toUpperCase(), d); });
          const merged = [...by.values()];
          AS.safetyDevices = merged;
          if (!AS.safety_build) AS.safety_build = { zones: [] };
          AS.safety_build.devices = merged;
          if (merged.length) return merged;
        }
      } catch (_) { /* ignore */ }
    }

    // 3) Cached workbook / prior session
    const wb = AS.workbook || {};
    const cached = normalizeDeviceList(
      (wb.safety_build || {}).devices || AS.safetyDevices || [],
    );
    if (cached.length) {
      AS.safetyDevices = cached;
      return cached;
    }

    status(`No Safety devices loaded — ${lastErr || 'unknown'}. Click Refresh discovery.`);
    return [];
  }

  async function refreshModel() {
    status('Discovering Safety devices…');
    const devices = await loadDevicesFromRun();
    state.model = buildClientModel();
    // If model still has 0 devices but we loaded some, force them in
    if (devices.length && !(state.model.devices || []).length) {
      state.model.devices = devices;
    }
    render();
    syncReadiness();
    const n = (state.model?.devices || []).length;
    if (n) status(`Loaded ${n} Safety device(s). Assign E-Stops to the zone, then Apply Safety.`);
    else status('Still no devices — check RUN is loaded, then Refresh discovery.');
  }

  function selectedZone() {
    if (!state.model) return null;
    return (state.model.zones || []).find((z) => z.id === state.selectedZoneId || z.name === state.selectedZoneId) || null;
  }

  function badge(status) {
    const s = String(status || '').toUpperCase();
    if (s === 'READY') return '<span class="text-emerald-400 font-semibold">READY</span>';
    if (s === 'N/A' || s === 'NONE') return '<span class="text-slate-500">N/A</span>';
    return '<span class="text-amber-300 font-semibold">REVIEW</span>';
  }

  function originChip(origin) {
    const label = ORIGIN_LABEL[origin] || origin || '—';
    const cls = origin === 'ENGINEER_ASSIGNED'
      ? 'text-fuchsia-300'
      : origin === 'AUTO_RUN_PROVEN'
        ? 'text-emerald-400/90'
        : origin === 'SUGGESTED_DIGIT_MATCH'
          ? 'text-sky-400/90'
          : 'text-amber-300/90';
    return `<span class="text-[9px] ${cls}">${label}</span>`;
  }

  function statusChip(status, zoneRef) {
    const st = String(status || '').toUpperCase();
    if (st === 'ENGINEER_ASSIGNED' || st === 'AUTO_RESOLVED' || st === 'ASSIGNED') {
      const z = zoneRef ? ` → ${escapeHtml(zoneRef)}` : '';
      const label = st === 'ENGINEER_ASSIGNED' ? 'ENGINEER' : (st === 'AUTO_RESOLVED' ? 'AUTO' : 'ASSIGNED');
      return `<span class="text-[8px] text-emerald-400/90">${label}${z}</span>`;
    }
    return '<span class="text-[8px] text-amber-300/90">UNASSIGNED</span>';
  }

  function renderInventory() {
    const host = $('sb-inventory');
    if (!host) return;
    if (!state.model) {
      host.innerHTML = '<div class="text-[10px] text-slate-600 p-2">No devices yet — Refresh discovery.</div>';
      return;
    }
    const filt = String(state.inventoryFilter || state.filter || '').trim().toUpperCase();
    const devices = state.model.devices || [];
    const byKind = {};
    KIND_ORDER.forEach((k) => { byKind[k] = []; });
    devices.forEach((d) => {
      if (!d || !d.name) return;
      if (filt && !String(d.name).toUpperCase().includes(filt)
        && !String(d.safetyZoneRef || '').toUpperCase().includes(filt)
        && !String(d.kind || '').toUpperCase().includes(filt)) return;
      const k = KIND_ORDER.includes(d.kind) ? d.kind : 'OTHER';
      byKind[k].push(d);
    });
    const c = state.model.counts || {};
    const left = (c.unassigned != null ? c.unassigned : (state.model.unassignedDevices || []).length);
    let body = '';
    KIND_ORDER.forEach((k) => {
      const rows = byKind[k] || [];
      if (!rows.length) return;
      body += `<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold mt-2 mb-0.5 first:mt-0">${KIND_LABEL[k] || k}</div>`;
      body += rows.map((d) => `
        <label class="flex items-center gap-1.5 px-1 py-0.5 rounded hover:bg-slate-900/80 cursor-pointer" data-sb-inv-row="${escapeHtml(d.name)}">
          <input type="checkbox" data-sb-inv="${escapeHtml(d.name)}" class="rounded border-slate-600">
          <button type="button" data-sb-inv-pick="${escapeHtml(d.name)}" class="flex-1 text-left mono text-[11px] text-slate-300 hover:text-rose-200 truncate">${escapeHtml(d.name)}</button>
          ${statusChip(d.status, d.safetyZoneRef)}
        </label>`).join('');
    });
    host.innerHTML = `
      <div class="flex items-center gap-2 mb-1.5 flex-wrap">
        <span class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold" title="Complete discovered Safety-device ledger (assigned + unassigned)">Device Inventory</span>
        <span class="text-[9px] text-slate-600 mono">${devices.length} found · ${left} unassigned</span>
        <input id="sb-inv-filter" type="search" placeholder="Filter…" class="ml-auto bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-[10px] w-28" value="${escapeHtml(state.inventoryFilter || '')}">
      </div>
      <div class="text-[9px] text-slate-600 mb-1 leading-snug">Full site ledger — shows assignment state. Not the same as Available (zone picker).</div>
      <div class="space-y-0.5">${body || '<div class="text-slate-600 p-2 text-[10px]">No devices match</div>'}</div>
      <div class="mt-2 flex flex-col gap-1.5">
        <button type="button" id="sb-inv-assign-selected" class="btn-primary w-full text-[10px] py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 border border-emerald-500/40 text-white font-semibold" title="Assign checked devices into the currently selected Safety Zone">
          Assign Selected → Zone
        </button>
        <button type="button" id="sb-inv-assign" class="btn-ghost w-full text-[10px] py-1 rounded-lg border border-emerald-900/50 text-emerald-300" title="Pick zone + confirm list">
          Assign Devices…
        </button>
      </div>`;
    const refreshAssignLabel = () => {
      const n = host.querySelectorAll('[data-sb-inv]:checked').length;
      const z = selectedZone();
      const btn = $('sb-inv-assign-selected');
      const btn2 = $('sb-inv-assign');
      if (btn) {
        btn.textContent = n
          ? `Assign ${n} Selected → ${z?.name || 'Zone'}`
          : 'Assign Selected → Zone';
        btn.disabled = !n || !z;
        btn.classList.toggle('opacity-50', !n || !z);
      }
      if (btn2) btn2.textContent = n ? `Assign ${n} Devices…` : 'Assign Devices…';
    };
    host.querySelectorAll('[data-sb-inv]').forEach((cb) => {
      cb.addEventListener('change', refreshAssignLabel);
      cb.addEventListener('click', (ev) => ev.stopPropagation());
    });
    refreshAssignLabel();
    $('sb-inv-filter')?.addEventListener('input', (ev) => {
      // Preserve checked names across filter re-render
      const kept = [...host.querySelectorAll('[data-sb-inv]:checked')]
        .map((el) => el.getAttribute('data-sb-inv'))
        .filter(Boolean);
      state.inventoryFilter = ev.target.value || '';
      state.filter = state.inventoryFilter;
      renderInventory();
      const z = selectedZone();
      if (z) renderDeviceLists(z);
      // restore checks that remain visible
      kept.forEach((name) => {
        host.querySelectorAll('[data-sb-inv]').forEach((cb) => {
          if (cb.getAttribute('data-sb-inv') === name) cb.checked = true;
        });
      });
      refreshAssignLabel();
    });
    host.querySelectorAll('[data-sb-inv-pick]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const name = btn.getAttribute('data-sb-inv-pick') || '';
        // Toggle check only — do NOT re-render (that wiped selections)
        host.querySelectorAll('[data-sb-inv]').forEach((cb) => {
          if (cb.getAttribute('data-sb-inv') === name) cb.checked = !cb.checked;
        });
        refreshAssignLabel();
      });
    });
    $('sb-inv-assign')?.addEventListener('click', () => {
      openAssignDevicesWizard();
    });
    $('sb-inv-assign-selected')?.addEventListener('click', () => {
      assignCheckedToSelectedZone();
    });
  }

  /** Primary action: assign checked inventory devices to the currently selected zone. */
  function assignCheckedToSelectedZone() {
    const host = $('sb-inventory');
    const z = selectedZone();
    if (!z) {
      status('Select a Safety Zone card first, then Assign Selected');
      return;
    }
    const names = [...(host?.querySelectorAll('[data-sb-inv]:checked') || [])]
      .map((el) => el.getAttribute('data-sb-inv'))
      .filter(Boolean);
    if (!names.length) {
      status('Check devices in Device Inventory first');
      return;
    }
    const live = (state.model.zones || []).find((x) => x.name === z.name);
    if (!live) return;
    // Reassign: remove from other zones first (no duplicate membership)
    (state.model.zones || []).forEach((oz) => {
      if (oz.name === z.name) return;
      const before = (oz.members || []).length;
      oz.members = (oz.members || []).filter(
        (m) => !names.some((n) => String(n).toUpperCase() === String(m).toUpperCase()),
      );
      if (oz.members.length !== before) {
        oz.membersOrigin = 'ENGINEER_ASSIGNED';
        oz.engineerEdited = true;
        splitZoneMembers(oz);
      }
    });
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
    });
    status(`Assigned ${names.length} device(s) → ${z.name} (Apply Safety to persist)`);
  }

  /** Gate E — guided bulk assign: select → choose zone → confirm list → Apply later */
  function openAssignDevicesWizard() {
    const host = $('sb-inventory');
    const names = [...(host?.querySelectorAll('[data-sb-inv]:checked') || [])]
      .map((el) => el.getAttribute('data-sb-inv'))
      .filter(Boolean);
    if (!names.length) {
      status('Check inventory devices first, then Assign Devices…');
      return;
    }
    const zones = (state.model?.zones || []).map((z) => z.name).filter(Boolean);
    if (!zones.length) {
      status('Create a Safety Zone on Transportation / Safety Build first');
      return;
    }
    const selected = selectedZone();
    const defaultZone = selected?.name || zones[0];
    const zonePick = prompt(
      `Assign ${names.length} device(s) to which Safety Zone?\n\n`
      + `Zones:\n${zones.map((z) => `  • ${z}`).join('\n')}\n\n`
      + 'Type the destination zone name exactly:',
      defaultZone,
    );
    if (zonePick == null) return;
    const dest = String(zonePick || '').trim();
    if (!zones.includes(dest)) {
      status(`Unknown zone “${dest}” — cancelled`);
      return;
    }
    const ok = confirm(
      `Confirm assignment\n\n`
      + `Destination: ${dest}\n`
      + `Devices (${names.length}):\n`
      + names.map((n) => `  • ${n}`).join('\n')
      + `\n\nNothing is persisted until you click Apply Safety.`,
    );
    if (!ok) {
      status('Assignment cancelled');
      return;
    }
    const live = (state.model.zones || []).find((x) => x.name === dest);
    if (!live) {
      status(`Zone ${dest} not in model`);
      return;
    }
    state.selectedZoneId = dest;
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
    });
    status(`Assigned ${names.length} device(s) → ${dest} (Apply Safety to persist)`);
  }

  function renderZoneList() {
    const host = $('sb-zone-list');
    if (!host || !state.model) return;
    const zones = state.model.zones || [];
    if (!zones.length) {
      host.innerHTML = '<div class="text-sm text-slate-500 p-4">No Safety Zones yet. Create an Area on Transportation (default zone offered), or Apply Transport so zones seed here.</div>';
      return;
    }
    host.innerHTML = zones.map((z) => {
      const sel = (z.id === state.selectedZoneId || z.name === state.selectedZoneId)
        ? 'border-rose-500/60 bg-rose-950/20'
        : 'border-slate-800 hover:border-slate-600';
      const st = z.status === 'READY'
        ? '<span class="text-emerald-400">READY</span>'
        : '<span class="text-amber-300">REVIEW REQUIRED</span>';
      return `<div class="rounded-xl border ${sel} px-3 py-2.5 mb-2 transition flex items-start gap-2">
        <button type="button" data-sb-zone="${escapeHtml(z.name)}" class="flex-1 text-left min-w-0">
          <div class="flex items-center gap-2">
            <span class="mono text-sm text-rose-200 font-semibold truncate">${escapeHtml(z.name)}</span>
            <span class="ml-auto text-[10px] shrink-0">${st}</span>
          </div>
          <div class="text-[10px] text-slate-500 mt-1">Area ${escapeHtml(z.areaRef || '—')} · Conv ${(z.conveyorRefs || []).length} · Devices ${(z.members || []).length}</div>
        </button>
        <button type="button" data-sb-zone-del="${escapeHtml(z.name)}" title="Delete Safety Zone"
          class="shrink-0 mt-0.5 btn-ghost text-[10px] px-2 py-1 rounded-lg border border-rose-900/50 text-rose-300 hover:bg-rose-950/40">
          <i class="fa-solid fa-trash"></i>
        </button>
      </div>`;
    }).join('');
    host.querySelectorAll('[data-sb-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.selectedZoneId = btn.getAttribute('data-sb-zone');
        render();
        highlightTransportZone(state.selectedZoneId);
      });
    });
    host.querySelectorAll('[data-sb-zone-del]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        deleteSafetyZone(btn.getAttribute('data-sb-zone-del'));
      });
    });
  }

  function renderZoneDetail() {
    const host = $('sb-zone-detail');
    if (!host) return;
    const z = selectedZone();
    if (!z) {
      host.innerHTML = '<div class="text-sm text-slate-500 p-4">Select a Safety Zone.</div>';
      return;
    }
    const f = z.fields || {};
    const row = (label, value, status, origin) => `
      <div class="flex items-start gap-2 py-1.5 border-b border-slate-800/60">
        <div class="w-36 shrink-0 text-[10px] uppercase tracking-wider text-slate-500 pt-0.5">${label}</div>
        <div class="flex-1 mono text-[11px] text-slate-200 break-all">${value}</div>
        <div class="w-24 text-right text-[10px]">${badge(status)}</div>
        <div class="w-28 text-right">${originChip(origin)}</div>
      </div>`;

    host.innerHTML = `
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <h3 class="text-base font-semibold text-rose-200 mono">${escapeHtml(z.name)}</h3>
        <span class="text-[11px]">${
          z.status === 'READY' ? badge('READY')
            : (z._draftReady ? badge('APPLY TO PERSIST') : badge('REVIEW'))
        }</span>
        <button type="button" id="sb-show-on-transport" class="ml-auto btn-ghost text-[10px] px-2 py-1 rounded-lg border border-slate-700">
          <i class="fa-solid fa-route mr-1"></i>Show on Transportation
        </button>
        <button type="button" id="sb-delete-zone" class="btn-ghost text-[10px] px-2 py-1 rounded-lg border border-rose-900/50 text-rose-300" title="Delete this Safety Zone">
          <i class="fa-solid fa-trash mr-1"></i>Delete zone
        </button>
      </div>
      <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 mb-3">
        ${row('Area', escapeHtml(z.areaRef || '—'), f.Area, z.areaOrigin)}
        ${row('Conveyors', `${(z.conveyorRefs || []).length}`, f.Conveyors, z.conveyorsOrigin)}
        ${row('E-Stops', z.eStops.length ? escapeHtml(z.eStops.join(', ')) : 'none assigned', f['E-Stops'], z.membersOrigin)}
        ${row('ESR', z.esrDevices.length ? escapeHtml(z.esrDevices.join(', ')) : '—', f.ESR, z.membersOrigin)}
        ${row('MCR', z.mcrDevices.length ? escapeHtml(z.mcrDevices.join(', ')) : '—', f.MCR, z.membersOrigin)}
        ${row('CS', (z.csDevices || []).length ? escapeHtml(z.csDevices.join(', ')) : '—', f.CS || 'N/A', z.membersOrigin)}
        ${row('ESLS', (z.eslsDevices || []).length ? escapeHtml(z.eslsDevices.join(', ')) : '—', f.ESLS || 'N/A', z.membersOrigin)}
        ${row('Reset', escapeHtml(z.resetSource || '—'), f.Reset, z.resetOrigin)}
        ${row('Silence', escapeHtml(z.silenceSource || '—'), f.Silence, z.silenceOrigin)}
      </div>
      ${(z.hard_missing || []).length ? `<div class="mb-3 text-[11px] text-amber-200/90 border border-amber-900/40 bg-amber-950/20 rounded-lg px-3 py-2">Missing: <span class="mono">${escapeHtml((z.hard_missing || []).join(', '))}</span></div>` : ''}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 flex flex-col min-h-[18rem]">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold" title="Unassigned devices eligible for this zone">Available Devices</span>
            <input id="sb-device-filter" type="search" placeholder="Filter…" class="ml-auto bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-[10px] w-36" value="${escapeHtml(state.filter)}">
          </div>
          <div class="text-[9px] text-slate-600 mb-1">Unassigned devices eligible for the selected zone (not the full inventory).</div>
          <div id="sb-available" class="flex-1 overflow-y-auto space-y-0.5 text-[11px] mono"></div>
          <div class="mt-2 flex gap-2">
            <button type="button" id="sb-add-selected" class="btn-ghost flex-1 text-[10px] py-1.5 rounded-lg border border-emerald-900/50 text-emerald-300">Add →</button>
            <button type="button" id="sb-accept-suggestions" class="btn-ghost text-[10px] py-1.5 px-2 rounded-lg border border-sky-900/50 text-sky-300" title="Accept digit-match suggestions (engineer action)">Accept suggestions</button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 flex flex-col min-h-[18rem]">
          <div class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Assigned to Zone</div>
          <div id="sb-assigned" class="flex-1 overflow-y-auto space-y-0.5 text-[11px] mono"></div>
          <button type="button" id="sb-remove-selected" class="mt-2 btn-ghost w-full text-[10px] py-1.5 rounded-lg border border-rose-900/50 text-rose-300">← Remove</button>
        </div>
      </div>
      <details class="mt-3 text-[10px] text-slate-500">
        <summary class="cursor-pointer text-slate-400 hover:text-slate-300">Evidence / diagnostics</summary>
        <pre class="mt-2 p-2 rounded bg-slate-950 border border-slate-800 overflow-x-auto text-[9px] text-slate-500">${escapeHtml(JSON.stringify({
          conveyors: z.conveyorRefs,
          members: z.members,
          suggestions: z.suggestions,
          fields: z.fields,
          origins: {
            area: z.areaOrigin,
            conveyors: z.conveyorsOrigin,
            members: z.membersOrigin,
            reset: z.resetOrigin,
            silence: z.silenceOrigin,
          },
        }, null, 2))}</pre>
      </details>
    `;

    renderDeviceLists(z);
    $('sb-show-on-transport')?.addEventListener('click', () => {
      highlightTransportZone(z.name);
      if (typeof window.activateTab === 'function') window.activateTab('transport');
    });
    $('sb-device-filter')?.addEventListener('input', (ev) => {
      state.filter = ev.target.value || '';
      state.inventoryFilter = state.filter;
      renderDeviceLists(z);
      renderInventory();
    });
    $('sb-add-selected')?.addEventListener('click', () => addSelectedDevices(z));
    $('sb-remove-selected')?.addEventListener('click', () => removeSelectedDevices(z));
    $('sb-accept-suggestions')?.addEventListener('click', () => acceptSuggestions(z));
    $('sb-delete-zone')?.addEventListener('click', () => deleteSafetyZone(z.name));
  }

  function serializeDevice(d) {
    if (!d || !d.name) return null;
    const row = { name: d.name, kind: d.kind || classifyDevName(d.name) || 'OTHER' };
    DEVICE_PROVENANCE_KEYS.forEach((k) => {
      if (d[k] !== undefined && d[k] !== null && d[k] !== '') row[k] = d[k];
    });
    row.kind = d.kind || row.kind;
    row.origin = d.origin || row.origin || 'AUTO_RUN_PROVEN';
    if (d.safetyZoneRef) row.safetyZoneRef = d.safetyZoneRef;
    if (d.status) row.status = d.status;
    return row;
  }

  function groupedDeviceHtml(devices, { suggested, checkboxAttr }) {
    const byKind = {};
    KIND_ORDER.forEach((k) => { byKind[k] = []; });
    (devices || []).forEach((d) => {
      const k = KIND_ORDER.includes(d.kind) ? d.kind : 'OTHER';
      byKind[k].push(d);
    });
    let html = '';
    KIND_ORDER.forEach((k) => {
      const rows = byKind[k] || [];
      if (!rows.length) return;
      html += `<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold mt-1.5 mb-0.5">${KIND_LABEL[k] || k}</div>`;
      html += rows.map((d) => {
        const sug = suggested && suggested.has(String(d.name).toUpperCase());
        const chip = statusChip(d.status, d.safetyZoneRef);
        return `<label class="flex items-center gap-2 px-1.5 py-0.5 rounded hover:bg-slate-900/80 cursor-pointer ${sug ? 'bg-sky-950/30' : ''}">
          <input type="checkbox" ${checkboxAttr}="${escapeHtml(d.name)}" class="rounded border-slate-600">
          <span class="${sug ? 'text-sky-300' : 'text-slate-300'}">${escapeHtml(d.name)}</span>
          <span class="ml-auto flex items-center gap-1">${chip}${sug ? '<span class="text-[8px] text-sky-400">SUGGESTED</span>' : ''}</span>
        </label>`;
      }).join('');
    });
    return html;
  }

  function renderDeviceLists(z) {
    const availHost = $('sb-available');
    const asgnHost = $('sb-assigned');
    if (!availHost || !asgnHost || !state.model) return;
    const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
    const filt = String(state.filter || '').trim().toUpperCase();
    // AVAILABLE = unassigned (or not on another zone) eligible for THIS zone.
    // DEVICE INVENTORY (left rail) remains the full ledger including assigned.
    const avail = (state.model.devices || [])
      .filter((d) => d && d.name && !assigned.has(String(d.name).toUpperCase()))
      .filter((d) => {
        const st = String(d.status || '').toUpperCase();
        const ref = String(d.safetyZoneRef || '').trim();
        if (ref && ref.toUpperCase() !== String(z.name || '').toUpperCase()) return false;
        return !ref || st === 'UNASSIGNED' || st === '';
      })
      .filter((d) => !filt || String(d.name).toUpperCase().includes(filt)
        || String(d.kind || '').toUpperCase().includes(filt)
        || String(d.safetyZoneRef || '').toUpperCase().includes(filt));
    const suggested = new Set((z.suggestions || []).map((s) => String(s.name).toUpperCase()));
    availHost.innerHTML = groupedDeviceHtml(avail, { suggested, checkboxAttr: 'data-sb-avail' })
      || '<div class="text-slate-600 p-2">No available devices</div>';

    const asgnDevices = (z.members || []).map((m) => {
      const found = (state.model.devices || []).find((d) => String(d.name).toUpperCase() === String(m).toUpperCase());
      return found || {
        name: m,
        kind: classifyDevName(m) || 'OTHER',
        status: 'ENGINEER_ASSIGNED',
        safetyZoneRef: z.name,
      };
    });
    asgnHost.innerHTML = groupedDeviceHtml(asgnDevices, { suggested: null, checkboxAttr: 'data-sb-asgn' })
      || '<div class="text-slate-600 p-2">No devices assigned — zone cannot become READY</div>';
  }

  function mutateZone(z, mutator) {
    mutator(z);
    z.membersOrigin = 'ENGINEER_ASSIGNED';
    z.engineerEdited = true;
    splitZoneMembers(z);
    state.dirty = true;
    // Persist engineer draft FIRST so rebuild keeps membership
    persistLocalDraft();
    state.model = buildClientModel();
    persistLocalDraft(); // refresh stamped safetyZoneRef/status on devices
    if (z.name) state.selectedZoneId = z.name;
    render();
    syncReadiness();
    status(`${z.name}: membership updated (not yet Applied)`);
  }

  function persistLocalDraft() {
    const AS = ensureAutogenState();
    const zones = (state.model?.zones || []).map((z) => ({
      id: z.id || z.name,
      name: z.name,
      area: z.areaRef,
      areaRef: z.areaRef,
      conveyors: z.conveyorRefs || [],
      conveyorRefs: z.conveyorRefs || [],
      members: z.members || [],
      membersOrigin: z.membersOrigin,
      resetSource: z.resetSource,
      silenceSource: z.silenceSource,
      engineerEdited: !!z.engineerEdited,
      status: z.status,
    }));
    const devices = (state.model?.devices || []).map(serializeDevice).filter(Boolean);
    AS.safety_build = {
      version: 1,
      source: 'safety_build',
      zones,
      devices,
      unassignedDevices: state.model?.unassignedDevices || [],
      inventory: state.model?.inventory || {},
      counts: state.model?.counts || {},
      deletedZones: [...state.deletedZones],
      draft: true,
      dirty: state.dirty,
    };
    try {
      localStorage.setItem('siteforge.safetyBuild.v1', JSON.stringify(AS.safety_build));
    } catch (_) { /* ignore */ }
  }

  /** Clear zone name off Transportation conveyors + tb.safetyZones registry. */
  function clearZoneFromTransport(zoneName) {
    const zname = String(zoneName || '').trim();
    if (!zname) return;
    try {
      if (typeof window.transportDeleteSafetyZone === 'function') {
        window.transportDeleteSafetyZone(zname);
        return;
      }
    } catch (_) { /* fall through */ }
    try {
      const key = localStorage.getItem('siteforge.transportBuild.v2')
        ? 'siteforge.transportBuild.v2'
        : 'siteforge.transportBuild.v1';
      const raw = localStorage.getItem(key);
      if (!raw) return;
      const data = JSON.parse(raw);
      (data.areas || []).forEach((area) => {
        (area.nodes || []).forEach((n) => {
          if (String(n.safetyZone || '').trim() === zname) n.safetyZone = '';
        });
      });
      data.safetyZones = (data.safetyZones || []).filter(
        (z) => String(z.name || z.id || '').trim() !== zname,
      );
      localStorage.setItem(key, JSON.stringify(data));
    } catch (_) { /* ignore */ }
  }

  function deleteSafetyZone(zoneName) {
    const zname = String(zoneName || '').trim();
    if (!zname) return;
    const ok = confirm(
      `Delete Safety Zone "${zname}"?\n\n`
      + '• Removes it from Safety Build\n'
      + '• Clears this zone off conveyors on Transportation\n'
      + '• Assigned devices become UNASSIGNED\n\n'
      + 'This does not delete physical devices — only the zone membership.',
    );
    if (!ok) return;
    state.deletedZones.add(zname);
    clearZoneFromTransport(zname);
    const AS = ensureAutogenState();
    if (AS.safety_build && Array.isArray(AS.safety_build.zones)) {
      AS.safety_build.zones = AS.safety_build.zones.filter(
        (z) => String(z.name || z.id || '').trim() !== zname,
      );
      AS.safety_build.deletedZones = [...state.deletedZones];
    }
    if (AS.workbook?.safety_build && Array.isArray(AS.workbook.safety_build.zones)) {
      AS.workbook.safety_build.zones = AS.workbook.safety_build.zones.filter(
        (z) => String(z.name || z.id || '').trim() !== zname,
      );
      AS.workbook.safety_build.deletedZones = [...state.deletedZones];
    }
    if (state.selectedZoneId === zname) state.selectedZoneId = null;
    state.dirty = true;
    state.model = buildClientModel();
    if (!state.selectedZoneId && (state.model.zones || []).length) {
      state.selectedZoneId = state.model.zones[0].name;
    }
    persistLocalDraft();
    render();
    syncReadiness();
    status(`Deleted Safety Zone ${zname}`);
  }

  function addSelectedDevices(z) {
    const names = [...document.querySelectorAll('#sb-available [data-sb-avail]:checked')]
      .map((el) => el.getAttribute('data-sb-avail'));
    if (!names.length) return;
    // Find zone in live model
    const live = (state.model.zones || []).find((x) => x.name === z.name);
    if (!live) return;
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
    });
  }

  function removeSelectedDevices(z) {
    const names = new Set([...document.querySelectorAll('#sb-assigned [data-sb-asgn]:checked')]
      .map((el) => el.getAttribute('data-sb-asgn')));
    if (!names.size) return;
    const live = (state.model.zones || []).find((x) => x.name === z.name);
    if (!live) return;
    mutateZone(live, (zz) => {
      zz.members = (zz.members || []).filter((m) => !names.has(m));
    });
  }

  function acceptSuggestions(z) {
    const live = (state.model.zones || []).find((x) => x.name === z.name);
    if (!live) return;
    const sug = (live.suggestions || []).map((s) => s.name);
    if (!sug.length) {
      status('No suggestions for this zone');
      return;
    }
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      sug.forEach((n) => set.add(n));
      zz.members = [...set];
    });
    status(`Accepted ${sug.length} suggestion(s) — engineer-owned`);
  }

  function highlightTransportZone(zoneName) {
    try {
      if (typeof window.transportHighlightSafetyZone === 'function') {
        window.transportHighlightSafetyZone(zoneName);
      } else if (typeof window.transportBuildRefresh === 'function') {
        // Soft signal via custom event
        window.dispatchEvent(new CustomEvent('siteforge:safety-zone-select', { detail: { zone: zoneName } }));
      }
    } catch (_) { /* ignore */ }
  }

  function renderCounts() {
    const c = state.model?.counts || {};
    const set = (id, v) => { const el = $(id); if (el) el.textContent = String(v ?? '—'); };
    set('sb-count-zones', c.zones);
    set('sb-count-ready', c.ready);
    set('sb-count-review', c.review_required);
    set('sb-count-estops', c.estops);
    const unassigned = c.unassigned != null ? c.unassigned : c.unassigned_estops;
    set('sb-count-unassigned', unassigned);
    set('sb-count-found', c.devices_found != null ? c.devices_found : c.devices);
    set('sb-count-auto', c.automatically_resolved);
    set('sb-count-eng', c.engineer_assigned);
    const pct = c.completion_pct;
    set('sb-count-completion', pct == null ? '—' : `${pct}%`);
  }

  function render() {
    renderCounts();
    renderInventory();
    renderZoneList();
    renderZoneDetail();
    const applyBtn = $('sb-apply');
    if (applyBtn) {
      applyBtn.classList.toggle('opacity-50', !state.dirty && !((state.model?.zones || []).some((z) => z.engineerEdited)));
    }
  }

  function syncReadiness() {
    if (typeof window.ensureAutogenReadiness !== 'function') return;
    const R = window.ensureAutogenReadiness();
    const c = state.model?.counts || {};
    const e = R.safety;
    const unassignedNames = state.model?.unassignedDevices || [];
    const unassignedN = c.unassigned != null ? c.unassigned : unassignedNames.length;
    const reviewN = c.review_required || 0;
    const detected = (c.zones || 0) > 0 || (c.devices_found || c.devices || 0) > 0;
    e.detected = detected;
    if (!detected) {
      e.status = 'NOT_DETECTED';
      e.detail = 'No Safety Zones';
      e.unresolved = 0;
      e.diagnostics = [];
    } else if (reviewN > 0 || unassignedN > 0) {
      // Any unassigned devices OR review zones → never READY
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = reviewN + unassignedN;
      const gaps = (state.model.zones || [])
        .filter((z) => z.status !== 'READY')
        .map((z) => `${z.name}: missing ${(z.hard_missing || ['SafetyDevices']).join(',')}`);
      const unNames = unassignedNames.slice(0, 6);
      const devicesFound = c.devices_found || c.devices || 0;
      const resolvedN = Math.max(0, devicesFound - unassignedN);
      if (unassignedN > 0) {
        gaps.unshift(
          `Unassigned (${unassignedN}): ${unNames.join(', ')}${unassignedN > unNames.length ? '…' : ''}`,
        );
      }
      e.detail = devicesFound
        ? `${resolvedN} / ${devicesFound} devices resolved · Unassigned: ${unNames.join(', ') || unassignedN}${unassignedN > unNames.length ? ', …' : ''} · Open Safety Build`
        : (gaps.slice(0, 4).join(' | ') || 'Safety REVIEW REQUIRED');
      e.diagnostics = gaps;
    } else {
      e.status = state.dirty ? 'CHANGED' : 'READY';
      e.detail = `${c.ready} zone(s) READY · ${c.devices_found || c.devices || 0} device(s) · ${c.completion_pct ?? 100}%`;
      e.unresolved = 0;
      e.diagnostics = [];
    }
    if (typeof window.refreshAutogenCompileHub === 'function') {
      try { window.refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    }
    if (typeof window.renderProjectHealthStrip === 'function') {
      try { window.renderProjectHealthStrip(); } catch (_) { /* ignore */ }
    }
  }

  async function applySafety() {
    persistLocalDraft();
    const AS = ensureAutogenState();
    // Rebuild so devices carry stamped safetyZoneRef/status before persist
    state.model = buildClientModel();
    const payload = {
      version: 1,
      source: 'safety_build',
      appliedAt: new Date().toISOString(),
      zones: (state.model?.zones || []).map((z) => ({
        id: z.id || z.name,
        name: z.name,
        area: z.areaRef || '',
        areaRef: z.areaRef || '',
        conveyors: z.conveyorRefs || [],
        conveyorRefs: z.conveyorRefs || [],
        members: z.members || [],
        eStops: z.eStops || [],
        esrDevices: z.esrDevices || [],
        mcrDevices: z.mcrDevices || [],
        csDevices: z.csDevices || [],
        eslsDevices: z.eslsDevices || [],
        resetSource: z.resetSource || '',
        silenceSource: z.silenceSource || '',
        reset_source: z.resetSource || '',
        silence_source: z.silenceSource || '',
        membersOrigin: z.membersOrigin || 'ENGINEER_ASSIGNED',
        engineerEdited: !!z.engineerEdited,
        status: z.status,
        fields: z.fields || {},
      })),
      devices: (state.model?.devices || []).map(serializeDevice).filter(Boolean),
      unassignedDevices: state.model?.unassignedDevices || [],
      inventory: state.model?.inventory || {},
      inventoryByKind: Object.fromEntries(
        Object.entries(state.model?.inventory || {}).map(([k, rows]) => [
          k,
          (rows || []).map((r) => (typeof r === 'string' ? r : r.name)).filter(Boolean),
        ]),
      ),
      counts: state.model?.counts || {},
      deletedZones: [...state.deletedZones],
    };
    AS.safety_build = payload;
    if (AS.workbook) AS.workbook.safety_build = payload;

    // Persist via workbook save IPC — MERGE into disk workbook so Transport
    // conveyors/areas are never hollowed out by a Safety-only write.
    const A = api();
    try {
      if (typeof A.autogenWorkbookSave === 'function') {
        let disk = {};
        try {
          if (typeof A.autogenWorkbookLoad === 'function') {
            const full = await A.autogenWorkbookLoad();
            if (full?.success && full.workbook) disk = full.workbook;
          }
        } catch (_) { /* ignore */ }
        const mem = AS.workbook || {};
        const wb = {
          ...disk,
          ...mem,
          // Prefer non-empty transport rows from either side
          conveyors: (Array.isArray(mem.conveyors) && mem.conveyors.length)
            ? mem.conveyors
            : (disk.conveyors || mem.conveyors || []),
          areas: (Array.isArray(mem.areas) && mem.areas.length)
            ? mem.areas
            : (disk.areas || mem.areas || []),
          merges_2to1: mem.merges_2to1 || disk.merges_2to1,
          safety_build: payload,
        };
        AS.workbook = wb;
        AS.safety_build = payload;
        const res = await A.autogenWorkbookSave({ workbook: wb });
        if (res && res.success === false) {
          status(`Apply failed: ${res.message || res.error || 'unknown'}`);
          return;
        }
      } else if (typeof window.saveAutogenWorkbook === 'function') {
        await window.saveAutogenWorkbook();
      }
    } catch (err) {
      status(`Apply error: ${err?.message || err}`);
      return;
    }

    state.dirty = false;
    // Do NOT call setAutogenReadinessApplied — it forces READY even when review remains.
    // Hub status comes from syncReadiness only.
    if (typeof window.ensureAutogenReadiness === 'function') {
      try {
        const e = window.ensureAutogenReadiness().safety;
        e.appliedAt = new Date().toISOString();
        e.dirty = false;
      } catch (_) { /* ignore */ }
    }
    syncReadiness();
    const readyN = (payload.zones || []).filter((z) => z.status === 'READY').length;
    const reviewLeft = (payload.counts?.review_required || 0) + (payload.unassignedDevices || []).length;
    status(reviewLeft
      ? `Applied Safety → workbook (${readyN} READY zone(s); review remains — does not block other PLC gen)`
      : `Applied Safety → workbook (${readyN} zone(s) READY)`);
    render();
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bind() {
    $('sb-refresh')?.addEventListener('click', () => {
      refreshModel().then(() => status('Safety model refreshed (engineer overrides kept)'));
    });
    $('sb-apply')?.addEventListener('click', () => applySafety());
    // Restore draft (+ engineer-deleted zone names so they do not re-seed)
    try {
      const raw = localStorage.getItem('siteforge.safetyBuild.v1');
      if (raw) {
        const draft = JSON.parse(raw);
        ensureAutogenState().safety_build = draft;
        state.deletedZones = new Set(
          (draft.deletedZones || []).map((n) => String(n || '').trim()).filter(Boolean),
        );
      }
    } catch (_) { /* ignore */ }
  }

  window.safetyBuildRefresh = () => refreshModel();
  window.safetyBuildGetModel = () => state.model;
  window.safetyBuildApply = () => applySafety();

  /** Wipe in-memory + local draft (called from Clear Current Project). */
  window.safetyBuildClear = function safetyBuildClear() {
    try { localStorage.removeItem('siteforge.safetyBuild.v1'); } catch (_) { /* ignore */ }
    const AS = ensureAutogenState();
    state.deletedZones = new Set();
    AS.safety_build = {
      version: 1,
      source: 'cleared',
      zones: [],
      devices: [],
      unassignedDevices: [],
      inventory: {},
      counts: {},
      deletedZones: [],
    };
    AS.safetyDevices = [];
    state.model = null;
    state.selectedZoneId = null;
    state.filter = '';
    state.inventoryFilter = '';
    state.dirty = false;
    try { render(); } catch (_) { /* ignore */ }
  };

  document.addEventListener('DOMContentLoaded', () => {
    bind();
  });

  // Also bind immediately if DOM already ready
  if (document.readyState !== 'loading') bind();
})();
