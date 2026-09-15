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

  const state = {
    model: null,
    selectedZoneId: null,
    filter: '',
    dirty: false,
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

    // Merge transport + engineer zones
    const byName = new Map();
    transportZones.forEach((z) => {
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
      if (!name) return;
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

    const classify = (n) => {
      const u = String(n || '').toUpperCase();
      if (u.includes('ESR')) return 'ESR';
      if (u.includes('MCR')) return 'MCR';
      return 'ESTOP';
    };

    const zones = [...byName.values()].map((z) => {
      z.eStops = (z.members || []).filter((m) => classify(m) === 'ESTOP');
      z.esrDevices = (z.members || []).filter((m) => classify(m) === 'ESR');
      z.mcrDevices = (z.members || []).filter((m) => classify(m) === 'MCR');
      const fields = {
        Area: z.areaRef ? 'READY' : 'UNRESOLVED',
        Conveyors: (z.conveyorRefs || []).length ? 'READY' : 'NONE',
        SafetyDevices: (z.members || []).length ? 'READY' : ((z.conveyorRefs || []).length ? 'UNRESOLVED' : 'NONE'),
        'E-Stops': z.eStops.length ? 'READY' : ((z.conveyorRefs || []).length ? 'UNRESOLVED' : 'NONE'),
        ESR: z.esrDevices.length ? 'READY' : 'N/A',
        MCR: z.mcrDevices.length ? 'READY' : 'N/A',
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
      z.status = hard.length || !(z.members || []).length ? 'REVIEW_REQUIRED' : 'READY';
      if (!(z.conveyorRefs || []).length && !(z.members || []).length) z.status = 'REVIEW_REQUIRED';
      // Digit-match suggestions
      const digs = new Set();
      (z.conveyorRefs || []).forEach((c) => (String(c).match(/\d{2,4}/g) || []).forEach((d) => digs.add(d)));
      (String(z.areaRef).match(/\d{2,4}/g) || []).forEach((d) => digs.add(d));
      const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
      z.suggestions = (devices || [])
        .map((d) => (typeof d === 'string' ? { name: d } : d))
        .filter((d) => d && d.name && !assigned.has(String(d.name).toUpperCase()))
        .filter((d) => (String(d.name).match(/\d{2,4}/g) || []).some((x) => digs.has(x)))
        .map((d) => ({ name: d.name, kind: d.kind || classify(d.name), origin: 'SUGGESTED_DIGIT_MATCH' }));
      return z;
    });

    const assignedAll = new Set(zones.flatMap((z) => (z.members || []).map((m) => String(m).toUpperCase())));
    const deviceList = (devices || []).map((d) => (typeof d === 'string' ? { name: d, kind: classify(d) } : d));
    const unassigned = deviceList.filter((d) => d && d.name && !assignedAll.has(String(d.name).toUpperCase()));

    return {
      kind: 'SafetyModel',
      version: 1,
      devices: deviceList,
      zones,
      unassignedDevices: unassigned.map((d) => d.name),
      counts: {
        zones: zones.length,
        ready: zones.filter((z) => z.status === 'READY').length,
        review_required: zones.filter((z) => z.status === 'REVIEW_REQUIRED').length,
        devices: deviceList.length,
        estops: deviceList.filter((d) => (d.kind || classify(d.name)) === 'ESTOP').length,
        unassigned_estops: unassigned.filter((d) => (d.kind || classify(d.name)) === 'ESTOP').length,
        unresolved_io: zones.filter((z) => (z.hard_missing || []).includes('SafetyDevices')).length,
      },
    };
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
      const kind = (typeof d === 'object' && d?.kind) || classifyDevName(nm);
      if (!kind) return; // only Safety-looking names
      seen.add(nm.toUpperCase());
      out.push({ name: nm, kind, origin: (d && d.origin) || 'AUTO_RUN_PROVEN' });
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
      return `<button type="button" data-sb-zone="${escapeHtml(z.name)}" class="w-full text-left rounded-xl border ${sel} px-3 py-2.5 mb-2 transition">
        <div class="flex items-center gap-2">
          <span class="mono text-sm text-rose-200 font-semibold">${escapeHtml(z.name)}</span>
          <span class="ml-auto text-[10px]">${st}</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-1">Area ${escapeHtml(z.areaRef || '—')} · Conv ${(z.conveyorRefs || []).length} · Devices ${(z.members || []).length}</div>
      </button>`;
    }).join('');
    host.querySelectorAll('[data-sb-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.selectedZoneId = btn.getAttribute('data-sb-zone');
        render();
        highlightTransportZone(state.selectedZoneId);
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
        <span class="text-[11px]">${z.status === 'READY' ? badge('READY') : badge('REVIEW')}</span>
        <button type="button" id="sb-show-on-transport" class="ml-auto btn-ghost text-[10px] px-2 py-1 rounded-lg border border-slate-700">
          <i class="fa-solid fa-route mr-1"></i>Show on Transportation
        </button>
      </div>
      <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 mb-3">
        ${row('Area', escapeHtml(z.areaRef || '—'), f.Area, z.areaOrigin)}
        ${row('Conveyors', `${(z.conveyorRefs || []).length}`, f.Conveyors, z.conveyorsOrigin)}
        ${row('E-Stops', z.eStops.length ? escapeHtml(z.eStops.join(', ')) : 'none assigned', f['E-Stops'], z.membersOrigin)}
        ${row('ESR', z.esrDevices.length ? escapeHtml(z.esrDevices.join(', ')) : '—', f.ESR, z.membersOrigin)}
        ${row('MCR', z.mcrDevices.length ? escapeHtml(z.mcrDevices.join(', ')) : '—', f.MCR, z.membersOrigin)}
        ${row('Reset', escapeHtml(z.resetSource || '—'), f.Reset, z.resetOrigin)}
        ${row('Silence', escapeHtml(z.silenceSource || '—'), f.Silence, z.silenceOrigin)}
      </div>
      ${(z.hard_missing || []).length ? `<div class="mb-3 text-[11px] text-amber-200/90 border border-amber-900/40 bg-amber-950/20 rounded-lg px-3 py-2">Missing: <span class="mono">${escapeHtml((z.hard_missing || []).join(', '))}</span></div>` : ''}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 flex flex-col min-h-[18rem]">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Available Safety Devices</span>
            <input id="sb-device-filter" type="search" placeholder="Filter…" class="ml-auto bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-[10px] w-36" value="${escapeHtml(state.filter)}">
          </div>
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
      renderDeviceLists(z);
    });
    $('sb-add-selected')?.addEventListener('click', () => addSelectedDevices(z));
    $('sb-remove-selected')?.addEventListener('click', () => removeSelectedDevices(z));
    $('sb-accept-suggestions')?.addEventListener('click', () => acceptSuggestions(z));
  }

  function renderDeviceLists(z) {
    const availHost = $('sb-available');
    const asgnHost = $('sb-assigned');
    if (!availHost || !asgnHost || !state.model) return;
    const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
    const filt = String(state.filter || '').trim().toUpperCase();
    const avail = (state.model.devices || [])
      .filter((d) => d && d.name && !assigned.has(String(d.name).toUpperCase()))
      .filter((d) => !filt || String(d.name).toUpperCase().includes(filt));
    const suggested = new Set((z.suggestions || []).map((s) => String(s.name).toUpperCase()));
    availHost.innerHTML = avail.map((d) => {
      const sug = suggested.has(String(d.name).toUpperCase());
      return `<label class="flex items-center gap-2 px-1.5 py-0.5 rounded hover:bg-slate-900/80 cursor-pointer ${sug ? 'bg-sky-950/30' : ''}">
        <input type="checkbox" data-sb-avail="${escapeHtml(d.name)}" class="rounded border-slate-600">
        <span class="${sug ? 'text-sky-300' : 'text-slate-300'}">${escapeHtml(d.name)}</span>
        <span class="ml-auto text-[8px] text-slate-600">${escapeHtml(d.kind || '')}${sug ? ' · SUGGESTED' : ''}</span>
      </label>`;
    }).join('') || '<div class="text-slate-600 p-2">No available devices</div>';

    asgnHost.innerHTML = (z.members || []).map((m) => `
      <label class="flex items-center gap-2 px-1.5 py-0.5 rounded hover:bg-slate-900/80 cursor-pointer">
        <input type="checkbox" data-sb-asgn="${escapeHtml(m)}" class="rounded border-slate-600">
        <span class="text-fuchsia-200">${escapeHtml(m)}</span>
      </label>
    `).join('') || '<div class="text-slate-600 p-2">No devices assigned — zone cannot become READY</div>';
  }

  function mutateZone(z, mutator) {
    mutator(z);
    z.membersOrigin = 'ENGINEER_ASSIGNED';
    z.engineerEdited = true;
    z.eStops = (z.members || []).filter((m) => !String(m).toUpperCase().includes('ESR') && !String(m).toUpperCase().includes('MCR'));
    z.esrDevices = (z.members || []).filter((m) => String(m).toUpperCase().includes('ESR'));
    z.mcrDevices = (z.members || []).filter((m) => String(m).toUpperCase().includes('MCR'));
    state.dirty = true;
    // Persist engineer draft FIRST so rebuild keeps membership
    persistLocalDraft();
    state.model = buildClientModel();
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
    AS.safety_build = {
      version: 1,
      source: 'safety_build',
      zones,
      devices: (state.model?.devices || []).map((d) => ({ name: d.name, kind: d.kind })),
      draft: true,
      dirty: state.dirty,
    };
    try {
      localStorage.setItem('siteforge.safetyBuild.v1', JSON.stringify(AS.safety_build));
    } catch (_) { /* ignore */ }
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
    set('sb-count-unassigned', c.unassigned_estops);
  }

  function render() {
    renderCounts();
    renderZoneList();
    renderZoneDetail();
    const applyBtn = $('sb-apply');
    if (applyBtn) {
      applyBtn.classList.toggle('opacity-50', !state.dirty && !((state.model?.zones || []).some((z) => z.engineerEdited)));
    }
  }

  function syncReadiness() {
    const AS = ensureAutogenState();
    if (typeof window.ensureAutogenReadiness !== 'function') return;
    const R = window.ensureAutogenReadiness();
    const c = state.model?.counts || {};
    const e = R.safety;
    const detected = (c.zones || 0) > 0;
    e.detected = detected;
    if (!detected) {
      e.status = 'NOT_DETECTED';
      e.detail = 'No Safety Zones';
      e.unresolved = 0;
    } else if ((c.review_required || 0) > 0) {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = c.review_required;
      const gaps = (state.model.zones || [])
        .filter((z) => z.status !== 'READY')
        .map((z) => `${z.name}: missing ${(z.hard_missing || ['SafetyDevices']).join(',')}`);
      e.detail = gaps.slice(0, 4).join(' | ') || 'Safety REVIEW REQUIRED';
      e.diagnostics = gaps;
    } else {
      e.status = state.dirty ? 'CHANGED' : 'READY';
      e.detail = `${c.ready} zone(s) READY · ${c.estops || 0} E-Stops`;
      e.unresolved = 0;
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
        resetSource: z.resetSource || '',
        silenceSource: z.silenceSource || '',
        reset_source: z.resetSource || '',
        silence_source: z.silenceSource || '',
        membersOrigin: z.membersOrigin || 'ENGINEER_ASSIGNED',
        engineerEdited: !!z.engineerEdited,
        status: z.status,
        fields: z.fields || {},
      })),
      devices: (state.model?.devices || []).map((d) => ({ name: d.name, kind: d.kind })),
      counts: state.model?.counts || {},
    };
    AS.safety_build = payload;
    if (AS.workbook) AS.workbook.safety_build = payload;

    // Persist via workbook save IPC (does NOT rediscover / wipe)
    const A = api();
    try {
      if (typeof A.autogenWorkbookSave === 'function') {
        const wb = { ...(AS.workbook || {}), safety_build: payload };
        AS.workbook = wb;
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
    if (typeof window.setAutogenReadinessApplied === 'function') {
      try {
        window.setAutogenReadinessApplied(
          'safety',
          `${payload.zones.filter((z) => z.status === 'READY').length} zone(s) READY`,
        );
      } catch (_) { /* ignore */ }
    }
    syncReadiness();
    status('Applied Safety → workbook (assignments preserved)');
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
    // Restore draft
    try {
      const raw = localStorage.getItem('siteforge.safetyBuild.v1');
      if (raw) {
        const draft = JSON.parse(raw);
        ensureAutogenState().safety_build = draft;
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
    AS.safety_build = { version: 1, source: 'cleared', zones: [], devices: [] };
    AS.safetyDevices = [];
    state.model = null;
    state.selectedZoneId = null;
    state.dirty = false;
    try { render(); } catch (_) { /* ignore */ }
  };

  document.addEventListener('DOMContentLoaded', () => {
    bind();
  });

  // Also bind immediately if DOM already ready
  if (document.readyState !== 'loading') bind();
})();
