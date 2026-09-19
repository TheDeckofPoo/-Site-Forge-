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

  /** Gate R — zone provenance classes */
  const PROVENANCE = {
    RUN_DISCOVERED: 'RUN_DISCOVERED',
    ENGINEER_CREATED: 'ENGINEER_CREATED',
    LEGACY_CANONICAL: 'LEGACY_CANONICAL',
    TEST_FIXTURE: 'TEST_FIXTURE',
    AUTO_DEFAULT: 'AUTO_DEFAULT',
    UNKNOWN: 'UNKNOWN',
  };
  /** Gate 3 — non-operational ownership bucket (NOT an E-stop zone). */
  const DEFAULT_SAFETY_NAME = 'Default Safety';
  const UNASSIGNED_SAFETY_NAME = 'Unassigned Safety';
  const DEFAULT_SAFETY_ALIASES = new Set([
    'default safety',
    'unassigned safety',
    'default',
    'unassigned',
  ]);
  const PLACEHOLDER_AREA_RE = /^Zone([1-9])_Area$/i;
  const PLACEHOLDER_ZONE_RE = /^Zone([1-9])_ESZone\d*$/i;
  const NUMERIC_STEM_ZONE_RE = /^(\d{2,})_ESZone\d*$/i;

  function isDefaultSafetyName(name) {
    const s = String(name || '').trim().toLowerCase();
    return !s || DEFAULT_SAFETY_ALIASES.has(s);
  }

  function isDefaultSafetyZone(z) {
    if (!z) return false;
    if (z.isDefault || z.isUnassignedBucket || z.defaultSafety || z.operational === false) {
      if (z.isDefault || z.isUnassignedBucket || z.defaultSafety) return true;
    }
    return isDefaultSafetyName(zoneSourceId(z)) || isDefaultSafetyName(zoneDisplayName(z));
  }

  function makeDefaultSafetyZone(unassignedMembers, devicesFound) {
    const members = (unassignedMembers || []).map((m) => String(m || '').trim()).filter(Boolean);
    return {
      id: DEFAULT_SAFETY_NAME,
      source_id: DEFAULT_SAFETY_NAME,
      name: DEFAULT_SAFETY_NAME,
      engineering_name: DEFAULT_SAFETY_NAME,
      display_name: UNASSIGNED_SAFETY_NAME,
      isDefault: true,
      isUnassignedBucket: true,
      defaultSafety: true,
      operational: false,
      areaRef: '',
      conveyorRefs: [],
      members,
      membersOrigin: 'UNASSIGNED',
      membership_status: 'REVIEW_REQUIRED',
      status: 'REVIEW_REQUIRED',
      provenance: 'SITE_FORGE_DEFAULT',
      origin: 'SITE_FORGE_DEFAULT',
      hard_missing: (members.length || devicesFound) ? ['SafetyDevices'] : [],
      eStops: members.filter((m) => classifyDevName(m) === 'ESTOP'),
      esrDevices: members.filter((m) => classifyDevName(m) === 'ESR'),
      mcrDevices: members.filter((m) => classifyDevName(m) === 'MCR'),
      csDevices: members.filter((m) => classifyDevName(m) === 'CS'),
      eslsDevices: members.filter((m) => classifyDevName(m) === 'ESLS'),
      note: 'Default/Unassigned Safety — ownership bucket only, NOT an operational E-stop zone.',
    };
  }

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

  /** Logix / Studio tag: letter or underscore first, then alnum/underscore. */
  const LOGIX_IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

  const state = {
    model: null,
    selectedZoneId: null,
    filter: '',
    inventoryFilter: '',
    dirty: false,
    /** Zone source_ids engineer deleted — must not reappear from Transport / RUN seeds. */
    deletedZones: new Set(),
  };

  function validateLogixIdent(name) {
    const s = String(name || '').trim();
    if (!s) return { ok: false, error: 'Name required' };
    if (s.length > 80) return { ok: false, error: 'Name too long (max 80)' };
    if (!LOGIX_IDENT_RE.test(s)) {
      return {
        ok: false,
        error: 'Invalid Logix identifier — letters/digits/underscore only; must start with letter or _',
      };
    }
    return { ok: true, error: '' };
  }

  /** Immutable RUN / seed identity for a zone (never changes on rename). */
  function zoneSourceId(z) {
    if (!z) return '';
    return String(z.source_id || z.sourceId || z.id || z.name || '').trim();
  }

  /** Display / emit name — engineering_name when set, else name. */
  function zoneDisplayName(z) {
    if (!z) return '';
    return String(z.engineering_name || z.engineeringName || z.name || '').trim();
  }

  /**
   * Gate J — membership only when PROVEN (CONFIRMED/HIGH) or ENGINEER_ASSIGNED.
   * Digit-match suggestions never become members automatically.
   */
  function membersAreProven(origin, membershipConfidence) {
    const o = String(origin || '').toUpperCase();
    const c = String(membershipConfidence || '').toUpperCase();
    if (o === 'ENGINEER_ASSIGNED' || o === 'ENGINEER') return true;
    if (o === 'AUTO_RUN_PROVEN' || o === 'AUTO') {
      return c === 'CONFIRMED' || c === 'HIGH' || c === 'HIGH_CONFIDENCE' || c === 'PROVEN';
    }
    return false;
  }

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
    // Prefer the shared fortna-plus.js autogenState (window.autogenState alias).
    // Creating a separate {} here caused Sorter Apply to read a hollow Transport
    // safety_build and wipe engineer-assigned members on disk.
    if (window.autogenState && typeof window.autogenState === 'object') {
      return window.autogenState;
    }
    window.autogenState = {};
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

  /**
   * Normalize workbook area entries to string names.
   * Root cause of [object Object]_ESZone1: wb.areas often holds area objects
   * ({id,name,...}); String(area) → "[object Object]" then preferred zone name.
   */
  function areaNameOf(a) {
    if (a == null) return '';
    if (typeof a === 'string' || typeof a === 'number') {
      const s = String(a).trim();
      if (!s || s === '[object Object]') return '';
      return s;
    }
    if (typeof a === 'object') {
      const s = String(a.name || a.id || a.area || a.areaName || '').trim();
      if (!s || s === '[object Object]') return '';
      return s;
    }
    return '';
  }

  function isCorruptZoneName(name) {
    const s = String(name || '');
    return !s || /\[object\s+Object\]/i.test(s);
  }

  function isUiPlaceholderArea(name) {
    return PLACEHOLDER_AREA_RE.test(String(name || '').trim());
  }

  function isPlaceholderOrTestZoneName(name) {
    const s = String(name || '').trim();
    if (!s || isCorruptZoneName(s)) return true;
    if (PLACEHOLDER_ZONE_RE.test(s)) return true;
    if (NUMERIC_STEM_ZONE_RE.test(s)) return true;
    return false;
  }

  /**
   * Gate R — classify zone provenance for persistence / UI filtering.
   * Zone existence ≠ Safety device membership.
   */
  function classifyZoneProvenance(z, ctx) {
    const sid = zoneSourceId(z);
    const disp = zoneDisplayName(z);
    const area = areaNameOf(z.areaRef || z.area) || String(z.areaRef || '').trim();
    const runIds = ctx?.runIds || new Set();
    const convRefs = ctx?.convRefs || new Set();
    if (!sid && !disp) return PROVENANCE.UNKNOWN;
    if (isCorruptZoneName(sid) || isCorruptZoneName(disp)) return PROVENANCE.TEST_FIXTURE;
    // GATE 4 — honor persisted provenance/origin from Apply so reopen cannot
    // demote RUN shells to AUTO_DEFAULT when AS.runSafetyZones is empty.
    if (z.provenance === PROVENANCE.RUN_DISCOVERED || z.origin === PROVENANCE.RUN_DISCOVERED) {
      if (isPlaceholderOrTestZoneName(sid) || isPlaceholderOrTestZoneName(disp)) {
        return PROVENANCE.TEST_FIXTURE;
      }
      return PROVENANCE.RUN_DISCOVERED;
    }
    const engineer = !!(z.engineerEdited
      || String(z.membersOrigin || '').toUpperCase() === 'ENGINEER_ASSIGNED'
      || z.createdBy === 'engineer'
      || z.provenance === PROVENANCE.ENGINEER_CREATED
      || z.origin === PROVENANCE.ENGINEER_CREATED);
    if (engineer && ((z.members || []).length || z.createdBy === 'engineer' || z.engineerEdited
      || z.provenance === PROVENANCE.ENGINEER_CREATED)) {
      if (isPlaceholderOrTestZoneName(sid) || isPlaceholderOrTestZoneName(disp)) {
        return engineer ? PROVENANCE.ENGINEER_CREATED : PROVENANCE.TEST_FIXTURE;
      }
      return PROVENANCE.ENGINEER_CREATED;
    }
    if (z.runDiscovered || runIds.has(sid) || runIds.has(disp)) {
      if (isPlaceholderOrTestZoneName(sid) || isPlaceholderOrTestZoneName(disp)) {
        return PROVENANCE.TEST_FIXTURE;
      }
      return PROVENANCE.RUN_DISCOVERED;
    }
    if (isPlaceholderOrTestZoneName(sid) || isPlaceholderOrTestZoneName(disp)) {
      return PROVENANCE.TEST_FIXTURE;
    }
    if (isUiPlaceholderArea(area) && !engineer) return PROVENANCE.TEST_FIXTURE;
    if (convRefs.has(sid) || convRefs.has(disp)) return PROVENANCE.LEGACY_CANONICAL;
    // Area-named ${stem}_ESZone1 shell with no members / no conveyor refs —
    // ONLY when it is truly an unused auto-default (no canvas/transport link).
    // Field failure b8b5d1c: empty Transport-seeded ORINDYAC6_ESZone1 was
    // classified AUTO_DEFAULT → dropped from UI → engineer could not assign.
    const hasConv = Array.isArray(z.conveyorRefs) && z.conveyorRefs.length > 0;
    if (/_ESZone1$/i.test(sid || disp) && !(z.members || []).length
      && !hasConv
      && !convRefs.has(sid) && !convRefs.has(disp) && !engineer) {
      return PROVENANCE.AUTO_DEFAULT;
    }
    // Transport-seeded empty zone shells remain selectable for assignment
    if ((convRefs.has(sid) || convRefs.has(disp) || hasConv) && !engineer) {
      return PROVENANCE.LEGACY_CANONICAL;
    }
    return PROVENANCE.UNKNOWN;
  }

  /** Meaningful zones for UI / production — drop unused test/default pollution. */
  function isMeaningfulZone(z) {
    if (isDefaultSafetyZone(z)) return true; // Gate 3 — Default/Unassigned always visible
    const p = z.provenance || classifyZoneProvenance(z, {});
    if (p === PROVENANCE.TEST_FIXTURE) {
      return !!(z.engineerEdited && (z.members || []).length);
    }
    if (p === PROVENANCE.AUTO_DEFAULT) {
      return false;
    }
    // Empty Transport/Area-seeded ES zone must stay visible so engineer can Assign
    if (p === PROVENANCE.LEGACY_CANONICAL) return true;
    if (p === PROVENANCE.UNKNOWN && (z.conveyorRefs || []).length) return true;
    return true;
  }

  function areaConveyorsFromWorkbook() {
    const wb = ensureAutogenState().workbook || {};
    const map = {};
    (wb.conveyors || []).forEach((c) => {
      const an = areaNameOf(c.main_area || c.area);
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
    // Normalize areas → string names (objects from Transport must not coerce via String())
    const areas = (Array.isArray(wb.areas) ? wb.areas : [])
      .map(areaNameOf)
      .filter(Boolean);
    // Prefer live discovered devices; workbook cache is fallback only
    const live = normalizeDeviceList(AS.safetyDevices || []);
    const cached = normalizeDeviceList(eng.devices || []);
    const devices = live.length ? live : cached;

    // Merge transport + engineer + RUN-discovered zones (skip engineer-deleted source_ids)
    const deleted = state.deletedZones;
    const byId = new Map(); // key = source_id (immutable)
    const indexByDisplay = new Map(); // engineering_name / name → source_id

    function putZone(z) {
      const sid = zoneSourceId(z);
      if (!sid || deleted.has(sid) || isCorruptZoneName(sid)) return null;
      byId.set(sid, z);
      const disp = zoneDisplayName(z);
      if (disp) indexByDisplay.set(disp.toLowerCase(), sid);
      if (z.name && String(z.name).toLowerCase() !== disp.toLowerCase()) {
        indexByDisplay.set(String(z.name).toLowerCase(), sid);
      }
      return z;
    }

    function findZone(nameOrId) {
      const raw = String(nameOrId || '').trim();
      if (!raw) return null;
      if (byId.has(raw)) return byId.get(raw);
      const sid = indexByDisplay.get(raw.toLowerCase());
      return sid ? byId.get(sid) : null;
    }

    // Gate H — RUN-discovered zone shells (devices=0, membership REVIEW until proven/engineer)
    // Appear immediately after import/model build — not only after Build.
    const runZones = Array.isArray(AS.runSafetyZones) ? AS.runSafetyZones : [];
    runZones.forEach((rz) => {
      const sid = zoneSourceId(rz) || String(rz.name || '').trim();
      if (!sid || deleted.has(sid) || isCorruptZoneName(sid)) return;
      // Gate R — never ingest Zone1..Zone9 / numeric test shells as RUN-discovered
      if (isPlaceholderOrTestZoneName(sid)) return;
      if (findZone(sid)) return;
      const areaRef = areaNameOf(rz.area || rz.areaRef) || '';
      if (isUiPlaceholderArea(areaRef)) return;
      const provenMembers = membersAreProven(rz.membersOrigin, rz.membership_confidence)
        ? [...(rz.members || [])].filter(Boolean)
        : [];
      putZone({
        id: sid,
        source_id: sid,
        name: zoneDisplayName(rz) || sid,
        engineering_name: zoneDisplayName(rz) || sid,
        areaRef,
        areaOrigin: 'AUTO_RUN_PROVEN',
        conveyorRefs: [...(rz.conveyors || rz.conveyorRefs || [])],
        conveyorsOrigin: (rz.conveyors || rz.conveyorRefs || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        // Gate J — do not auto-assign; only PROVEN membership survives
        members: provenMembers,
        membersOrigin: provenMembers.length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        membership_confidence: rz.membership_confidence || 'ENGINEER_REQUIRED',
        membership_status: provenMembers.length ? 'PROVEN' : 'REVIEW_REQUIRED',
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        resetSource: areaRef ? `${areaRef}.Reset` : '',
        silenceSource: areaRef ? `${areaRef}.Silence` : '',
        resetOrigin: areaRef ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        silenceOrigin: areaRef ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        suggestions: [],
        engineerEdited: false,
        status: 'REVIEW_REQUIRED',
        fields: {},
        runDiscovered: true,
        provenance: PROVENANCE.RUN_DISCOVERED,
      });
    });

    transportZones.forEach((z) => {
      const sid = String(z.name || '').trim();
      if (!sid || deleted.has(sid) || isCorruptZoneName(sid)) return;
      if (isPlaceholderOrTestZoneName(sid) && !(z.conveyors || []).length) return;
      const areaRef = areaNameOf(z.area) || String(z.area || '').trim();
      if (isCorruptZoneName(areaRef)) return;
      const existing = findZone(sid);
      if (existing) {
        if (!(existing.conveyorRefs || []).length && (z.conveyors || []).length) {
          existing.conveyorRefs = [...z.conveyors];
          existing.conveyorsOrigin = 'AUTO_RUN_PROVEN';
        }
        if (!existing.areaRef && areaRef) {
          existing.areaRef = areaRef;
          existing.areaOrigin = 'AUTO_RUN_PROVEN';
        }
        return;
      }
      putZone({
        id: sid,
        source_id: sid,
        name: sid,
        engineering_name: sid,
        areaRef: areaRef,
        areaOrigin: 'AUTO_RUN_PROVEN',
        conveyorRefs: [...(z.conveyors || [])],
        conveyorsOrigin: (z.conveyors || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        // Gate J — transport seed never invents device membership
        members: [],
        membersOrigin: 'UNRESOLVED',
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        resetSource: areaRef ? `${areaRef}.Reset` : '',
        silenceSource: areaRef ? `${areaRef}.Silence` : '',
        resetOrigin: areaRef ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        silenceOrigin: areaRef ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        suggestions: [],
        engineerEdited: false,
        status: 'REVIEW_REQUIRED',
        fields: {},
        // Keep visible for Assign — never AUTO_DEFAULT drop of empty Transport shells
        provenance: PROVENANCE.LEGACY_CANONICAL,
        origin: PROVENANCE.LEGACY_CANONICAL,
      });
    });
    (eng.zones || []).forEach((ez) => {
      const sid = zoneSourceId(ez) || String(ez.name || ez.id || '').trim();
      // Drop corrupt identities from prior Apply bug — do not suppress by string match alone;
      // never re-ingest zones whose name is the String(object) coercion artifact.
      if (!sid || deleted.has(sid) || isCorruptZoneName(sid)) return;
      const engName = String(ez.engineering_name || ez.engineeringName || ez.name || sid).trim();
      const cur = findZone(sid) || {
        id: sid,
        source_id: sid,
        name: engName,
        engineering_name: engName,
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
      // GATE 4 — restore persisted RUN/engineer identity on Apply/reopen.
      // Without this, runDiscovered/provenance were dropped and RUN shells were
      // reclassified AUTO_DEFAULT then deleted, leaving only engineer zones.
      if (ez.runDiscovered || ez.provenance === PROVENANCE.RUN_DISCOVERED
        || ez.origin === PROVENANCE.RUN_DISCOVERED) {
        cur.runDiscovered = true;
      }
      if (ez.provenance) cur.provenance = ez.provenance;
      if (ez.origin) cur.origin = ez.origin;
      if (ez.createdBy) cur.createdBy = ez.createdBy;
      if (ez.engineerEdited) cur.engineerEdited = true;
      if (ez.membersOrigin && !cur.membersOrigin) cur.membersOrigin = ez.membersOrigin;
      // Gate I / Gate 8 — engineering_name editable; existing RUN source_id immutable.
      // When overlaying onto a RUN-discovered shell, keep that source_id even if the
      // engineer payload carries a divergent id (match was by display name).
      const priorSid = zoneSourceId(cur);
      const keepRunSid = !!(cur.runDiscovered || cur.provenance === PROVENANCE.RUN_DISCOVERED)
        && priorSid && priorSid !== sid;
      cur.source_id = keepRunSid ? priorSid : sid;
      cur.id = cur.source_id;
      // Gate I — engineering_name is editable; source_id stays immutable
      if (ez.engineering_name || ez.engineeringName) {
        cur.engineering_name = String(ez.engineering_name || ez.engineeringName).trim();
        cur.name = cur.engineering_name;
      } else if (ez.name && ez.name !== sid && ez.engineerEdited) {
        cur.engineering_name = String(ez.name).trim();
        cur.name = cur.engineering_name;
      } else {
        cur.engineering_name = cur.engineering_name || engName;
        cur.name = cur.engineering_name;
      }
      if (ez.area || ez.areaRef) {
        const ar = areaNameOf(ez.area || ez.areaRef);
        if (ar) {
          cur.areaRef = ar;
          cur.areaOrigin = ez.engineerEdited ? 'ENGINEER_ASSIGNED' : (cur.areaOrigin || 'AUTO_RUN_PROVEN');
        }
      }
      const convs = ez.conveyorRefs || ez.conveyors;
      if (Array.isArray(convs) && convs.length) {
        cur.conveyorRefs = [...convs];
        cur.conveyorsOrigin = ez.conveyorsOrigin || 'ENGINEER_ASSIGNED';
      }
      if (Array.isArray(ez.members) && ez.members.length) {
        // Reconcile membership (Apply = update, not append duplicates)
        const seen = new Set();
        cur.members = [];
        ez.members.forEach((m) => {
          const nm = String(m || '').trim();
          if (!nm) return;
          const key = nm.toUpperCase();
          if (seen.has(key)) return;
          seen.add(key);
          cur.members.push(nm);
        });
        cur.membersOrigin = ez.membersOrigin || 'ENGINEER_ASSIGNED';
        cur.engineerEdited = true;
      } else if (Array.isArray(ez.members) && !ez.members.length && (cur.members || []).length) {
        // Never let an empty eng overlay wipe existing members (handoff race)
        cur.membersOrigin = cur.membersOrigin || 'ENGINEER_ASSIGNED';
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
      putZone(cur);
    });

    // Gate R — do NOT auto-create ${stem}_ESZone1 for every workbook area.
    // That AUTO_DEFAULT path minted Zone1_ESZone1..Zone9_ESZone1 / 123456_ESZone1
    // from UI placeholders and leaked them into production canonical.
    // Zones come from: RUN-discovered, Transport conveyor.safetyZone, engineer create.
    const areaSet = new Set(areas.filter((a) => a && !isUiPlaceholderArea(a)));

    // Drop stale zones from prior projects (saved localStorage) unless RUN /
    // engineer / transport-referenced. Never keep unused ZoneN / numeric tests.
    // Also drop coercion artifacts ([object Object]_ESZone*) permanently.
    const transportNames = new Set(
      transportZones.map((z) => String(z.name || '').trim()).filter((n) => n && !isCorruptZoneName(n)),
    );
    const convRefs = new Set(transportNames);
    (eng.zones || []).forEach((ez) => {
      const sid = zoneSourceId(ez);
      if (sid && (ez.engineerEdited || (ez.members || []).length)) convRefs.add(sid);
    });
    const runIds = new Set(
      (Array.isArray(AS.runSafetyZones) ? AS.runSafetyZones : [])
        .map((z) => zoneSourceId(z) || String(z.name || '').trim())
        .filter((n) => n && !isPlaceholderOrTestZoneName(n)),
    );
    const provCtx = { runIds, convRefs };
    for (const [sid, z] of [...byId.entries()]) {
      if (isCorruptZoneName(sid) || isCorruptZoneName(z.areaRef)) {
        byId.delete(sid);
        continue;
      }
      const area = areaNameOf(z.areaRef) || String(z.areaRef || '').trim();
      z.areaRef = area;
      const disp = zoneDisplayName(z);
      z.provenance = classifyZoneProvenance(z, provCtx);
      // Gate R — drop test/default pollution unless engineer-authored with members
      if (!isMeaningfulZone(z)) {
        byId.delete(sid);
        continue;
      }
      const keep = transportNames.has(sid)
        || transportNames.has(disp)
        || z.runDiscovered
        || z.engineerEdited
        || z.provenance === PROVENANCE.RUN_DISCOVERED
        || z.provenance === PROVENANCE.ENGINEER_CREATED
        || z.provenance === PROVENANCE.LEGACY_CANONICAL
        || (area && areaSet.has(area) && !isPlaceholderOrTestZoneName(sid));
      // If we have current areas and this zone's area is gone → drop (unless RUN/engineer)
      if (areaSet.size > 0 && area && !areaSet.has(area)
        && !transportNames.has(sid) && !transportNames.has(disp)
        && !z.runDiscovered && !z.engineerEdited
        && z.provenance !== PROVENANCE.ENGINEER_CREATED
        && z.provenance !== PROVENANCE.RUN_DISCOVERED) {
        byId.delete(sid);
        continue;
      }
      // Orphan zone with no area and not on canvas → drop (unless RUN/engineer shell)
      if (!keep && areaSet.size > 0 && !transportNames.has(sid) && !transportNames.has(disp)) {
        byId.delete(sid);
      }
    }

    const zones = [...byId.values()].map((z) => {
      z.source_id = zoneSourceId(z) || z.name;
      z.engineering_name = zoneDisplayName(z) || z.source_id;
      z.name = z.engineering_name;
      z.id = z.source_id;
      // Gate 8 — canonical origin alongside provenance
      if (z.provenance === PROVENANCE.RUN_DISCOVERED || z.provenance === PROVENANCE.ENGINEER_CREATED) {
        z.origin = z.provenance;
      } else if (z.runDiscovered && !z.engineerEdited) {
        z.origin = PROVENANCE.RUN_DISCOVERED;
      } else if (z.engineerEdited || z.createdBy === 'engineer') {
        z.origin = PROVENANCE.ENGINEER_CREATED;
      } else {
        z.origin = z.provenance || PROVENANCE.UNKNOWN;
      }
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

    // Zone membership → device.safetyZoneRef / status / assignment origin.
    // Default/Unassigned Safety is an OWNERSHIP BUCKET, not an operational zone —
    // never treat its members as AUTO_RESOLVED / ENGINEER_ASSIGNED.
    const memberToZone = new Map();
    const memberOrigin = new Map();
    zones.forEach((z) => {
      if (isDefaultSafetyZone(z)) return;
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
      let zoneRef = memberToZone.get(key) || base.safetyZoneRef || '';
      // Backend may stamp safetyZoneRef = "Default Safety" while status=UNASSIGNED.
      // That is the ownership bucket — treat as unassigned for assignment eligibility.
      if (isDefaultSafetyName(zoneRef)) {
        zoneRef = '';
      }
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
        base.defaultSafety = true;
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

    // Gate 3 — Default/Unassigned Safety bucket always present (not operational).
    // Do NOT stamp safetyZoneRef = "Default Safety" on unassigned devices —
    // that produced contradictory UI (Assigned=127 AND Unassigned=127) and
    // made Default look like an operational assignment target.
    const operationalZones = zones.filter((z) => !isDefaultSafetyZone(z));
    const defaultZone = makeDefaultSafetyZone(
      unassigned.map((d) => d.name),
      devicesFound,
    );
    unassigned.forEach((d) => {
      d.safetyZoneRef = null;
      d.defaultSafety = true;
      d.status = 'UNASSIGNED';
    });
    const zonesOut = [defaultZone, ...operationalZones];

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

    const engineerZoneN = operationalZones.length;
    return {
      kind: 'SafetyModel',
      version: 1,
      devices: deviceList,
      zones: zonesOut,
      unassignedDevices: unassigned.map((d) => d.name),
      inventory,
      counts: {
        // Gate 7 — site totals (canonical inventory; zones are assignment views)
        zones: engineerZoneN, // operational engineer zones only
        engineer_zones: engineerZoneN,
        ready: operationalZones.filter((z) => z.status === 'READY').length,
        review_required: operationalZones.filter((z) => z.status === 'REVIEW_REQUIRED').length
          + (unassigned.length ? 1 : 0),
        devices: devicesFound,
        devices_found: devicesFound,
        site_devices: devicesFound,
        estops: deviceList.filter((d) => kindOf(d) === 'ESTOP').length,
        esr: deviceList.filter((d) => kindOf(d) === 'ESR').length,
        mcr: deviceList.filter((d) => kindOf(d) === 'MCR').length,
        cs: deviceList.filter((d) => kindOf(d) === 'CS').length,
        esls: deviceList.filter((d) => kindOf(d) === 'ESLS').length,
        unassigned_estops: unassigned.filter((d) => kindOf(d) === 'ESTOP').length,
        unassigned: unassigned.length,
        default_safety: unassigned.length,
        assigned: assignedN,
        automatically_resolved: autoResolved.length,
        engineer_assigned: engAssigned.length,
        completion_pct: completionPct,
        unresolved_io: operationalZones.filter((z) => (z.hard_missing || []).includes('SafetyDevices')).length,
        // Conservation law (FAIL if broken):
        // devices_found = automatically_resolved + engineer_assigned + unassigned
        conservation_ok: devicesFound === (
          autoResolved.length + engAssigned.length + unassigned.length
        ),
        conservation_equation: 'devices_found = auto_resolved + engineer_assigned + unassigned',
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

  /**
   * Gate H — ingest RUN-proven zone shells immediately (devices may be 0).
   * Membership stays REVIEW_REQUIRED unless PROVEN. Does not wait for Transport Apply.
   */
  function ingestRunDiscoveredZones(modelZones) {
    const AS = ensureAutogenState();
    const shells = [];
    (modelZones || []).forEach((z) => {
      const sid = zoneSourceId(z) || String(z.name || z.id || '').trim();
      if (!sid || isCorruptZoneName(sid) || state.deletedZones.has(sid)) return;
      // Gate R — placeholders are never RUN-discovered
      if (isPlaceholderOrTestZoneName(sid)) return;
      const areaRef = areaNameOf(z.areaRef || z.area) || String(z.areaRef || z.area || '').trim();
      if (isUiPlaceholderArea(areaRef) && !(z.members || []).length) return;
      const proven = membersAreProven(z.membersOrigin, z.membership_confidence);
      shells.push({
        id: sid,
        source_id: sid,
        name: String(z.engineering_name || z.engineeringName || z.name || sid).trim(),
        engineering_name: String(z.engineering_name || z.engineeringName || z.name || sid).trim(),
        area: areaRef,
        areaRef,
        conveyors: z.conveyorRefs || z.conveyors || [],
        conveyorRefs: z.conveyorRefs || z.conveyors || [],
        // Gate J — never auto-assign; empty unless PROVEN
        members: proven ? [...(z.members || [])].filter(Boolean) : [],
        membersOrigin: proven && (z.members || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        membership_confidence: z.membership_confidence || 'ENGINEER_REQUIRED',
        membership_status: proven && (z.members || []).length ? 'PROVEN' : 'REVIEW_REQUIRED',
        status: 'REVIEW_REQUIRED',
        runDiscovered: true,
        provenance: PROVENANCE.RUN_DISCOVERED,
      });
    });
    AS.runSafetyZones = shells;
    if (!AS.safety_build) AS.safety_build = { zones: [] };
    // Merge shells into draft zones by source_id without wiping engineer membership
    const bySid = new Map();
    (AS.safety_build.zones || []).forEach((z) => {
      const sid = zoneSourceId(z) || String(z.name || '').trim();
      if (sid) bySid.set(sid, z);
    });
    shells.forEach((shell) => {
      const cur = bySid.get(shell.source_id);
      if (!cur) {
        bySid.set(shell.source_id, { ...shell });
        return;
      }
      // Preserve engineer rename + membership; fill missing source_id
      cur.source_id = cur.source_id || shell.source_id;
      if (!cur.engineering_name && !cur.engineeringName) {
        cur.engineering_name = shell.engineering_name;
      }
      cur.runDiscovered = true;
      if (!(cur.members || []).length && shell.members.length) {
        cur.members = [...shell.members];
        cur.membersOrigin = 'AUTO_RUN_PROVEN';
      }
    });
    AS.safety_build.zones = [...bySid.values()];
    return shells;
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
          // Gate H — show RUN zones immediately (even when devices=0)
          try { ingestRunDiscoveredZones(res.model.zones || []); } catch (_) { /* ignore */ }
          const mapped = normalizeDeviceList(res.model.devices || []);
          if (mapped.length || (res.model.zones || []).length) {
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
    const want = String(state.selectedZoneId || '').trim();
    if (!want) return null;
    return (state.model.zones || []).find((z) =>
      zoneSourceId(z) === want
      || z.id === want
      || z.name === want
      || zoneDisplayName(z) === want
    ) || null;
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

  /** Compact selected-zone orientation (replaces giant Device Inventory panel). */
  function renderZoneSummary() {
    const host = $('sb-zone-summary');
    if (!host) return;
    const z = selectedZone();
    const c = state.model?.counts || {};
    const devices = state.model?.devices || [];
    const unassigned = (c.unassigned != null
      ? c.unassigned
      : (state.model?.unassignedDevices || []).length);
    if (!z) {
      host.innerHTML = `
        <div class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Selected zone</div>
        <div class="text-[11px] text-slate-500">Select a Safety Zone to see status.</div>
        <div class="mt-2 grid grid-cols-2 gap-1.5 text-[10px] mono">
          <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Devices</span><span class="float-right text-slate-300">${devices.length}</span></div>
          <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Unassigned</span><span class="float-right text-amber-200">${unassigned}</span></div>
        </div>`;
      return;
    }
    const members = z.members || [];
    const estops = z.eStops || [];
    const eng = members.filter((m) => {
      const d = devices.find((x) => String(x.name).toUpperCase() === String(m).toUpperCase());
      return d && String(d.status || '').toUpperCase() === 'ENGINEER_ASSIGNED';
    }).length;
    const st = z.status === 'READY'
      ? '<span class="text-emerald-400">READY</span>'
      : (z._draftReady
        ? '<span class="text-sky-300">APPLY TO PERSIST</span>'
        : '<span class="text-amber-300">REVIEW</span>');
    const sid = zoneSourceId(z);
    const disp = zoneDisplayName(z);
    host.innerHTML = `
      <div class="flex items-start gap-2 mb-2">
        <div class="min-w-0">
          <div class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Selected zone</div>
          <div class="mono text-sm text-rose-200 font-semibold truncate">${escapeHtml(disp)}</div>
          ${sid && sid !== disp ? `<div class="text-[9px] text-slate-600 mono truncate">RUN ${escapeHtml(sid)}</div>` : ''}
          <div class="text-[10px] text-slate-500 mt-0.5">Area ${escapeHtml(z.areaRef || '—')}</div>
        </div>
        <div class="ml-auto text-[10px] shrink-0">${st}</div>
      </div>
      <div class="grid grid-cols-2 gap-1.5 text-[10px] mono">
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">${isDefaultSafetyZone(z) ? 'Unassigned here' : 'Assigned'}</span><span class="float-right text-slate-200">${members.length}</span></div>
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">E-Stops</span><span class="float-right text-slate-200">${estops.length}</span></div>
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Engineer zones</span><span class="float-right text-fuchsia-300">${eng}</span></div>
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Site unassigned</span><span class="float-right text-amber-200">${unassigned}</span></div>
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Site devices</span><span class="float-right text-slate-300">${devices.length}</span></div>
        <div class="rounded-lg border border-slate-800 px-2 py-1"><span class="text-slate-500">Review</span><span class="float-right text-amber-300">${(z.hard_missing || []).length || (z.status === 'READY' ? 0 : 1)}</span></div>
      </div>
      <div class="mt-2 text-[9px] text-slate-600 leading-snug">Assign devices in the zone detail panel. Full inventory remains available to the model (not shown).</div>`;
  }

  function renderInventory() {
    // Gate F: primary Device Inventory panel removed. Keep a minimal hidden
    // host so assignCheckedToSelectedZone / filter APIs still resolve.
    const host = $('sb-inventory');
    if (!host) return;
    renderZoneSummary();
    if (host.classList.contains('hidden') || host.getAttribute('aria-hidden') === 'true') {
      // Compact stub — no giant ledger
      const devices = state.model?.devices || [];
      const left = state.model?.counts?.unassigned
        ?? (state.model?.unassignedDevices || []).length;
      host.innerHTML = `<div class="text-[9px] text-slate-600 p-1">Inventory model: ${devices.length} devices · ${left} unassigned (UI hidden)</div>`;
      return;
    }
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
    if (isDefaultSafetyZone(z)) {
      status('Select an engineer Safety Zone — Default/Unassigned is not an operational E-stop zone');
      return;
    }
    const names = [...(host?.querySelectorAll('[data-sb-inv]:checked') || [])]
      .map((el) => el.getAttribute('data-sb-inv'))
      .filter(Boolean);
    if (!names.length) {
      status('Check devices in Device Inventory first');
      return;
    }
    const live = findLiveZone(z);
    if (!live || isDefaultSafetyZone(live)) return;
    const liveSid = zoneSourceId(live);
    // Reassign: remove from other zones first (no duplicate membership)
    (state.model.zones || []).forEach((oz) => {
      if (zoneSourceId(oz) === liveSid) return;
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
    status(`Assigned ${names.length} device(s) → ${zoneDisplayName(live)} (Apply Safety to persist)`);
  }

  /** Gate E — guided bulk assign: select → choose zone → confirm list → Apply later */
  function openAssignDevicesWizard() {
    const host = $('sb-inventory');
    const detail = $('sb-zone-detail');
    const checked = [
      ...(host?.querySelectorAll('[data-sb-inv]:checked') || []),
      ...(detail?.querySelectorAll('[data-sb-inv]:checked') || []),
    ];
    const seen = new Set();
    const names = [];
    checked.forEach((el) => {
      const n = el.getAttribute('data-sb-inv');
      if (!n || seen.has(n.toUpperCase())) return;
      seen.add(n.toUpperCase());
      names.push(n);
    });
    if (!names.length) {
      status('Check devices first (Default Safety list or inventory), then Assign Devices…');
      return;
    }
    const zones = (state.model?.zones || [])
      .filter((z) => !isDefaultSafetyZone(z))
      .map((z) => zoneDisplayName(z))
      .filter(Boolean);
    if (!zones.length) {
      status('Create an engineer Safety Zone on Transportation / Safety Build first');
      return;
    }
    const selected = selectedZone();
    const defaultZone = (selected && !isDefaultSafetyZone(selected) ? zoneDisplayName(selected) : '') || zones[0];
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
    const live = (state.model.zones || []).find((x) =>
      zoneDisplayName(x) === dest || zoneSourceId(x) === dest
    );
    if (!live) {
      status(`Zone ${dest} not in model`);
      return;
    }
    state.selectedZoneId = zoneSourceId(live);
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
    });
    status(`Assigned ${names.length} device(s) → ${dest} (Apply Safety to persist)`);
  }

  function membershipStatusLabel(z) {
    const members = z.members || [];
    const origin = String(z.membersOrigin || '').toUpperCase();
    if (members.length && (origin === 'ENGINEER_ASSIGNED' || origin === 'ENGINEER')) {
      return { key: 'ENGINEER_ASSIGNED', html: '<span class="text-fuchsia-300">ENGINEER ASSIGNED</span>' };
    }
    if (members.length && (origin === 'AUTO_RUN_PROVEN' || origin === 'AUTO')) {
      return { key: 'PROVEN', html: '<span class="text-emerald-400">PROVEN</span>' };
    }
    if (members.length) {
      return { key: 'ASSIGNED', html: '<span class="text-sky-300">ASSIGNED</span>' };
    }
    // Gate J/T — unknown membership stays fail-safe REVIEW_REQUIRED
    return { key: 'REVIEW_REQUIRED', html: '<span class="text-amber-300">REVIEW REQUIRED</span>' };
  }

  function renderZoneList() {
    const host = $('sb-zone-list');
    if (!host || !state.model) return;
    // Gate T — show only meaningful zones after reconciliation
    // Gate 3 — Default/Unassigned Safety always first and visually distinct
    const zones = (state.model.zones || []).filter(isMeaningfulZone)
      .sort((a, b) => {
        const da = isDefaultSafetyZone(a) ? 0 : 1;
        const db = isDefaultSafetyZone(b) ? 0 : 1;
        return da - db;
      });
    if (!zones.length) {
      host.innerHTML = '<div class="text-sm text-slate-500 p-4">No Safety Zones yet. RUN-discovered zones appear after import; or create one on Transportation / Safety Build.</div>';
      return;
    }
    host.innerHTML = zones.map((z) => {
      const sid = zoneSourceId(z);
      const isDef = isDefaultSafetyZone(z);
      const disp = isDef ? `${DEFAULT_SAFETY_NAME} / ${UNASSIGNED_SAFETY_NAME}` : zoneDisplayName(z);
      const sel = (sid === state.selectedZoneId || disp === state.selectedZoneId || z.id === state.selectedZoneId
        || (isDef && isDefaultSafetyName(state.selectedZoneId)))
        ? (isDef ? 'border-amber-500/50 bg-amber-950/20' : 'border-rose-500/60 bg-rose-950/20')
        : (isDef ? 'border-amber-900/40 bg-amber-950/10 hover:border-amber-700/50' : 'border-slate-800 hover:border-slate-600');
      const mem = membershipStatusLabel(z);
      const st = isDef
        ? '<span class="text-amber-300">UNASSIGNED</span>'
        : (z.status === 'READY'
          ? '<span class="text-emerald-400">READY</span>'
          : mem.html);
      const prov = z.provenance || classifyZoneProvenance(z, {});
      const provChip = isDef
        ? '<span class="text-[8px] text-amber-300/90">DEFAULT</span>'
        : (prov === PROVENANCE.RUN_DISCOVERED
          ? '<span class="text-[8px] text-sky-400/90">RUN</span>'
          : (prov === PROVENANCE.ENGINEER_CREATED
            ? '<span class="text-[8px] text-fuchsia-300/90">ENGINEER</span>'
            : `<span class="text-[8px] text-slate-600">${escapeHtml(prov)}</span>`));
      const renamed = !isDef && sid && zoneDisplayName(z) && sid !== zoneDisplayName(z)
        ? `<div class="text-[9px] text-slate-600 mono mt-0.5">source ${escapeHtml(sid)}</div>`
        : '';
      const reviewN = isDef
        ? (z.members || []).length
        : ((z.hard_missing || []).length || (z.status === 'READY' ? 0 : 1));
      const delBtn = isDef
        ? ''
        : `<button type="button" data-sb-zone-del="${escapeHtml(sid)}" title="Delete Safety Zone — members return to Default/Unassigned"
          class="shrink-0 mt-0.5 btn-ghost text-[10px] px-2 py-1 rounded-lg border border-rose-900/50 text-rose-300 hover:bg-rose-950/40">
          <i class="fa-solid fa-trash"></i>
        </button>`;
      return `<div class="rounded-xl border ${sel} px-3 py-2.5 mb-2 transition flex items-start gap-2">
        <button type="button" data-sb-zone="${escapeHtml(sid)}" class="flex-1 text-left min-w-0">
          <div class="flex items-center gap-2">
            <span class="mono text-sm ${isDef ? 'text-amber-200' : 'text-rose-200'} font-semibold truncate">${escapeHtml(disp)}</span>
            ${provChip}
            <span class="ml-auto text-[10px] shrink-0">${st}</span>
          </div>
          ${renamed}
          <div class="text-[10px] text-slate-500 mt-1">${isDef
            ? `Ownership bucket · ${(z.members || []).length} unassigned · NOT an E-stop zone`
            : `Area ${escapeHtml(z.areaRef || '—')} · Assigned ${(z.members || []).length} · E-Stops ${(z.eStops || []).length} · Review ${reviewN}`}</div>
        </button>
        ${delBtn}
      </div>`;
    }).join('');
    host.querySelectorAll('[data-sb-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.selectedZoneId = btn.getAttribute('data-sb-zone');
        render();
        const z = selectedZone();
        if (z && !isDefaultSafetyZone(z)) {
          highlightTransportZone(zoneDisplayName(z) || state.selectedZoneId);
        }
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

    const sid = zoneSourceId(z);
    const isDef = isDefaultSafetyZone(z);
    const disp = isDef ? `${DEFAULT_SAFETY_NAME} / ${UNASSIGNED_SAFETY_NAME}` : zoneDisplayName(z);
    if (isDef) {
      const members = z.members || [];
      const c = state.model?.counts || {};
      host.innerHTML = `
        <div class="flex items-center gap-2 mb-3 flex-wrap">
          <h3 class="text-base font-semibold text-amber-200 mono">${escapeHtml(disp)}</h3>
          <span class="text-[11px]">${badge('REVIEW')}</span>
          <span class="text-[9px] text-amber-300/90 border border-amber-800/50 rounded px-1.5 py-0.5">NOT an E-stop zone</span>
        </div>
        <div class="rounded-xl border border-amber-900/40 bg-amber-950/10 p-3 mb-3 text-[11px] text-slate-300 leading-relaxed">
          Site Forge ownership bucket for devices not yet assigned to an engineer Safety Zone.
          <strong class="text-amber-200">UNASSIGNED → REVIEW_REQUIRED</strong> (fail-safe — never permissive).
          Select devices below, then pick an engineer zone and <span class="mono">Assign Selected → Zone</span>.
        </div>
        <div class="grid grid-cols-2 gap-2 text-[10px] mono mb-3">
          <div class="rounded-lg border border-slate-800 px-2 py-1.5"><span class="text-slate-500">Site devices</span><span class="float-right">${c.site_devices ?? c.devices_found ?? '—'}</span></div>
          <div class="rounded-lg border border-amber-900/40 px-2 py-1.5"><span class="text-amber-500/90">Default / Unassigned</span><span class="float-right text-amber-200">${members.length}</span></div>
          <div class="rounded-lg border border-slate-800 px-2 py-1.5"><span class="text-slate-500">Engineer zones</span><span class="float-right">${c.engineer_zones ?? c.zones ?? '—'}</span></div>
          <div class="rounded-lg border border-slate-800 px-2 py-1.5"><span class="text-slate-500">Assigned</span><span class="float-right text-emerald-300">${c.assigned ?? '—'}</span></div>
        </div>
        <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3">
          <div class="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Unassigned devices (${members.length}) — grouped by kind</div>
          <div id="sb-available" class="max-h-[50vh] overflow-y-auto space-y-1 text-[12px] mono">${
            members.length
              ? groupedDeviceHtml(
                members.map((m) => {
                  const found = (state.model.devices || []).find(
                    (d) => String(d.name).toUpperCase() === String(m).toUpperCase(),
                  );
                  return found || { name: m, kind: classifyDevName(m) || 'OTHER', status: 'UNASSIGNED' };
                }),
                { suggested: null, checkboxAttr: 'data-sb-inv' },
              )
              : '<div class="text-slate-600 text-[11px] p-2">All discovered devices are assigned to engineer zones.</div>'
          }</div>
          <button type="button" id="sb-inv-assign-selected" class="mt-3 btn-primary w-full text-[11px] py-2 rounded-lg bg-emerald-800 hover:bg-emerald-700 border border-emerald-500/40 text-white font-semibold">
            Assign Selected → Engineer Zone…
          </button>
        </div>`;
      $('sb-inv-assign-selected')?.addEventListener('click', () => openAssignDevicesWizard());
      return;
    }
    host.innerHTML = `
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <h3 class="text-base font-semibold text-rose-200 mono">${escapeHtml(disp)}</h3>
        <span class="text-[11px]">${
          z.status === 'READY' ? badge('READY')
            : (z._draftReady ? badge('APPLY TO PERSIST') : badge('REVIEW'))
        }</span>
        <button type="button" id="sb-rename-zone" class="btn-ghost text-[10px] px-2 py-1 rounded-lg border border-slate-700" title="Rename engineering name (RUN source_id stays immutable)">
          <i class="fa-solid fa-pen mr-1"></i>Rename
        </button>
        <button type="button" id="sb-show-on-transport" class="ml-auto btn-ghost text-[10px] px-2 py-1 rounded-lg border border-slate-700">
          <i class="fa-solid fa-route mr-1"></i>Show on Transportation
        </button>
        <button type="button" id="sb-delete-zone" class="btn-ghost text-[10px] px-2 py-1 rounded-lg border border-rose-900/50 text-rose-300" title="Delete this Safety Zone — members return to Default/Unassigned">
          <i class="fa-solid fa-trash mr-1"></i>Delete zone
        </button>
      </div>
      <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-3 mb-3">
        ${row('Engineering name', escapeHtml(disp), 'READY', z.engineerEdited ? 'ENGINEER_ASSIGNED' : 'AUTO_RUN_PROVEN')}
        ${row('Source identity (RUN)', escapeHtml(sid), 'READY', 'AUTO_RUN_PROVEN')}
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
      <div class="grid grid-cols-1 gap-3">
        <div class="rounded-xl border border-emerald-900/40 bg-[#0c1219] p-4 flex flex-col min-h-[28rem]">
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <span class="text-[11px] uppercase tracking-wider text-emerald-500/90 font-semibold" title="Eligible unassigned devices for this zone">Assign devices</span>
            <input id="sb-device-filter" type="search" placeholder="Search / filter devices…" class="ml-auto bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-[11px] w-56" value="${escapeHtml(state.filter)}">
          </div>
          <div class="text-[10px] text-slate-500 mb-2 leading-snug">Eligible for <span class="mono text-slate-300">${escapeHtml(z.name)}</span>. Generous scroll viewport — browse the full eligible list.</div>
          <div id="sb-available" class="flex-1 min-h-[22rem] max-h-[55vh] overflow-y-auto space-y-1 text-[12px] mono rounded-lg border border-slate-800 bg-[#0a1018] p-2.5 leading-relaxed"></div>
          <div class="mt-3 flex gap-2">
            <button type="button" id="sb-add-selected" class="btn-primary flex-1 text-[11px] py-2 rounded-lg bg-emerald-800 hover:bg-emerald-700 border border-emerald-500/40 text-white font-semibold">Assign Selected</button>
            <button type="button" id="sb-accept-suggestions" class="btn-ghost text-[11px] py-2 px-3 rounded-lg border border-sky-900/50 text-sky-300" title="Accept digit-match suggestions (engineer action)">Suggestions</button>
          </div>
        </div>
        <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-4 flex flex-col min-h-[14rem]">
          <div class="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Assigned to Zone</div>
          <div id="sb-assigned" class="flex-1 min-h-[10rem] max-h-[40vh] overflow-y-auto space-y-1 text-[12px] mono leading-relaxed"></div>
          <button type="button" id="sb-remove-selected" class="mt-3 btn-ghost w-full text-[11px] py-2 rounded-lg border border-rose-900/50 text-rose-300">← Remove</button>
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
      highlightTransportZone(zoneDisplayName(z) || z.name);
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
    $('sb-delete-zone')?.addEventListener('click', () => deleteSafetyZone(zoneSourceId(z) || z.name));
    $('sb-rename-zone')?.addEventListener('click', () => renameSafetyZone(z));
  }

  /**
   * Gate I — rename engineering_name only. source_id stays immutable.
   * Does not duplicate the zone, drop members, or break reload/provenance.
   */
  function renameSafetyZone(z) {
    const sid = zoneSourceId(z);
    const cur = zoneDisplayName(z);
    const next = prompt(
      `Rename Safety Zone engineering name\n\n`
      + `Source identity (immutable): ${sid}\n`
      + `Logix rules: letter/_ start, letters/digits/_ only, max 80.\n`,
      cur,
    );
    if (next == null) return;
    const eng = String(next || '').trim();
    if (!eng || eng === cur) return;
    const v = validateLogixIdent(eng);
    if (!v.ok) {
      status(v.error);
      return;
    }
    // Collision: another zone already uses this engineering_name
    const clash = (state.model?.zones || []).find((oz) =>
      zoneSourceId(oz) !== sid
      && zoneDisplayName(oz).toLowerCase() === eng.toLowerCase()
    );
    if (clash) {
      status(`Name “${eng}” already used by another zone — cancelled`);
      return;
    }
    const live = (state.model.zones || []).find((x) => zoneSourceId(x) === sid);
    if (!live) return;
    const keptMembers = [...(live.members || [])];
    live.engineering_name = eng;
    live.name = eng;
    live.source_id = sid;
    live.id = sid;
    live.engineerEdited = true;
    live.members = keptMembers;
    state.dirty = true;
    state.selectedZoneId = sid;
    persistLocalDraft();
    state.model = buildClientModel();
    // Ensure members survived rebuild keyed by source_id
    const after = (state.model.zones || []).find((x) => zoneSourceId(x) === sid);
    if (after && !(after.members || []).length && keptMembers.length) {
      after.members = keptMembers;
      after.membersOrigin = 'ENGINEER_ASSIGNED';
      after.engineerEdited = true;
      splitZoneMembers(after);
    }
    persistLocalDraft();
    render();
    syncReadiness();
    status(`Renamed → ${eng} (source_id ${sid} preserved)`);
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

  function isAssignableUnassignedDevice(d) {
    /** Default/Unassigned bucket devices are eligible for engineer zones. */
    if (!d || !d.name) return false;
    const st = String(d.status || '').toUpperCase();
    const ref = String(d.safetyZoneRef || '').trim();
    if (st === 'UNASSIGNED' || st === '' || d.defaultSafety === true) return true;
    if (!ref || isDefaultSafetyName(ref)) return true;
    return false;
  }

  function renderDeviceLists(z) {
    const availHost = $('sb-available');
    const asgnHost = $('sb-assigned');
    if (!availHost || !asgnHost || !state.model) return;
    const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
    const filt = String(state.filter || '').trim().toUpperCase();
    // AVAILABLE = unassigned ownership-bucket devices eligible for THIS engineer zone.
    // Default Safety is NOT another operational zone — its members remain assignable.
    // DEVICE INVENTORY (left rail) remains the full ledger including assigned.
    const avail = (state.model.devices || [])
      .filter((d) => d && d.name && !assigned.has(String(d.name).toUpperCase()))
      .filter((d) => isAssignableUnassignedDevice(d))
      .filter((d) => {
        const ref = String(d.safetyZoneRef || '').trim();
        // Already on a different operational engineer zone → not available here.
        if (ref && !isDefaultSafetyName(ref)
          && ref.toUpperCase() !== String(z.name || '').toUpperCase()) {
          return false;
        }
        return true;
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
    z.createdBy = z.createdBy || 'engineer';
    z.provenance = z.provenance === PROVENANCE.RUN_DISCOVERED
      ? PROVENANCE.RUN_DISCOVERED
      : PROVENANCE.ENGINEER_CREATED;
    z.origin = z.provenance;
    splitZoneMembers(z);
    state.dirty = true;
    const sid = zoneSourceId(z);
    const snapMembers = [...(z.members || [])];
    const snapName = zoneDisplayName(z);
    // Upsert into safety_build BEFORE rebuild so buildClientModel cannot drop members
    const AS = ensureAutogenState();
    if (!AS.safety_build) AS.safety_build = { zones: [], devices: [] };
    const zones = Array.isArray(AS.safety_build.zones) ? [...AS.safety_build.zones] : [];
    const idx = zones.findIndex((x) => zoneSourceId(x) === sid || String(x.name || '') === snapName);
    const row = {
      id: sid,
      source_id: sid,
      name: snapName,
      engineering_name: snapName,
      area: z.areaRef || '',
      areaRef: z.areaRef || '',
      conveyors: z.conveyorRefs || [],
      conveyorRefs: z.conveyorRefs || [],
      members: snapMembers,
      membersOrigin: 'ENGINEER_ASSIGNED',
      engineerEdited: true,
      createdBy: 'engineer',
      provenance: z.provenance,
      origin: z.origin,
      operational: true,
    };
    if (idx >= 0) zones[idx] = { ...zones[idx], ...row, members: snapMembers };
    else zones.push(row);
    AS.safety_build.zones = zones;
    AS.safety_build.draft = true;
    AS.safety_build.dirty = true;
    persistLocalDraft();
    state.model = buildClientModel();
    // Re-assert members if rebuild lost them (source_id mismatch defense)
    const after = (state.model.zones || []).find((x) => zoneSourceId(x) === sid);
    if (after && snapMembers.length && !(after.members || []).length) {
      after.members = snapMembers;
      after.membersOrigin = 'ENGINEER_ASSIGNED';
      after.engineerEdited = true;
      splitZoneMembers(after);
    }
    if (sid) state.selectedZoneId = sid;
    persistLocalDraft();
    render();
    syncReadiness();
    const n = snapMembers.length;
    status(
      `✓ ${snapName}: ${n} device(s) assigned (not yet Applied). `
      + `Zone stays selected — assign more or click Apply Safety.`,
    );
  }

  function serializeZone(z) {
    if (isDefaultSafetyZone(z)) return null; // never persist Default bucket as operational zone
    const sid = zoneSourceId(z);
    const eng = zoneDisplayName(z);
    const provenance = z.provenance
      || (z.runDiscovered ? PROVENANCE.RUN_DISCOVERED : null)
      || (z.engineerEdited || z.createdBy === 'engineer' ? PROVENANCE.ENGINEER_CREATED : PROVENANCE.UNKNOWN);
    return {
      id: sid,
      source_id: sid,
      name: eng,
      engineering_name: eng,
      area: z.areaRef,
      areaRef: z.areaRef,
      conveyors: z.conveyorRefs || [],
      conveyorRefs: z.conveyorRefs || [],
      members: z.members || [],
      membersOrigin: z.membersOrigin,
      membership_confidence: z.membership_confidence,
      resetSource: z.resetSource,
      silenceSource: z.silenceSource,
      engineerEdited: !!z.engineerEdited,
      createdBy: z.createdBy || (z.engineerEdited && !z.runDiscovered ? 'engineer' : undefined),
      runDiscovered: !!z.runDiscovered || provenance === PROVENANCE.RUN_DISCOVERED,
      provenance,
      origin: z.origin || provenance,
      status: z.status,
      operational: true,
    };
  }

  function persistLocalDraft() {
    const AS = ensureAutogenState();
    const zones = (state.model?.zones || []).map(serializeZone).filter(Boolean);
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
    if (isDefaultSafetyName(zname)) {
      status('Default/Unassigned Safety cannot be deleted — it is the ownership bucket');
      return;
    }
    const ok = confirm(
      `Delete Safety Zone "${zname}"?\n\n`
      + '• Removes it from Safety Build\n'
      + '• Clears this zone off conveyors on Transportation\n'
      + '• Assigned devices return to Default / Unassigned Safety\n\n'
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

  function findLiveZone(z) {
    const sid = zoneSourceId(z);
    return (state.model.zones || []).find((x) =>
      zoneSourceId(x) === sid || x.name === z.name
    ) || null;
  }

  function addSelectedDevices(z) {
    const names = [...document.querySelectorAll('#sb-available [data-sb-avail]:checked')]
      .map((el) => el.getAttribute('data-sb-avail'));
    if (!names.length) return;
    const live = findLiveZone(z);
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
    const live = findLiveZone(z);
    if (!live) return;
    mutateZone(live, (zz) => {
      zz.members = (zz.members || []).filter((m) => !names.has(m));
    });
  }

  function acceptSuggestions(z) {
    // Gate J — suggestions are never auto-assigned; this is an explicit engineer action.
    const live = findLiveZone(z);
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
    status(`Accepted ${sug.length} suggestion(s) — engineer-owned (not auto-assign)`);
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
    // Gate 7 — site devices, Default/Unassigned, engineer zones, assigned, E-stop, review
    set('sb-count-zones', c.engineer_zones != null ? c.engineer_zones : c.zones);
    set('sb-count-ready', c.ready);
    set('sb-count-review', c.review_required);
    set('sb-count-estops', c.estops);
    const unassigned = c.default_safety != null
      ? c.default_safety
      : (c.unassigned != null ? c.unassigned : c.unassigned_estops);
    set('sb-count-unassigned', unassigned);
    set('sb-count-default', unassigned);
    set('sb-count-found', c.site_devices != null ? c.site_devices : (c.devices_found != null ? c.devices_found : c.devices));
    set('sb-count-assigned', c.assigned != null ? c.assigned : (
      Math.max(0, (c.devices_found || c.devices || 0) - (unassigned || 0))
    ));
    set('sb-count-auto', c.automatically_resolved);
    set('sb-count-eng', c.engineer_assigned);
    const pct = c.completion_pct;
    const cons = c.conservation_ok === false ? ' · CONSERVATION FAIL' : '';
    set('sb-count-completion', pct == null ? '—' : `${pct}%${cons}`);
  }

  function render() {
    renderCounts();
    renderZoneSummary();
    renderInventory(); // no-op ledger when hidden; keeps model APIs
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
    // Apply = reconcile/update by zone identity. Never emit coercion artifacts.
    // Gate 3 — Default/Unassigned Safety is ownership-only; never persist as ES zone.
    const appliedZones = (state.model?.zones || [])
      .filter((z) => z && zoneSourceId(z) && !isCorruptZoneName(zoneSourceId(z)) && !isDefaultSafetyZone(z))
      .map((z) => {
        const areaRef = areaNameOf(z.areaRef) || '';
        const sid = zoneSourceId(z);
        const eng = zoneDisplayName(z);
        const members = [];
        const seenM = new Set();
        (z.members || []).forEach((m) => {
          const nm = String(m || '').trim();
          if (!nm) return;
          const key = nm.toUpperCase();
          if (seenM.has(key)) return;
          seenM.add(key);
          members.push(nm);
        });
        return {
          id: sid,
          source_id: sid,
          name: eng,
          engineering_name: eng,
          area: areaRef,
          areaRef,
          conveyors: z.conveyorRefs || [],
          conveyorRefs: z.conveyorRefs || [],
          members,
          eStops: z.eStops || [],
          esrDevices: z.esrDevices || [],
          mcrDevices: z.mcrDevices || [],
          csDevices: z.csDevices || [],
          eslsDevices: z.eslsDevices || [],
          resetSource: z.resetSource || '',
          silenceSource: z.silenceSource || '',
          reset_source: z.resetSource || '',
          silence_source: z.silenceSource || '',
          membersOrigin: z.membersOrigin || (
            (z.members || []).length ? 'ENGINEER_ASSIGNED' : (z.runDiscovered ? 'UNRESOLVED' : 'ENGINEER_ASSIGNED')
          ),
          membership_confidence: z.membership_confidence,
          engineerEdited: !!z.engineerEdited,
          createdBy: z.createdBy || (z.engineerEdited && !z.runDiscovered ? 'engineer' : undefined),
          runDiscovered: !!z.runDiscovered
            || z.provenance === PROVENANCE.RUN_DISCOVERED
            || z.origin === PROVENANCE.RUN_DISCOVERED,
          provenance: z.provenance
            || (z.runDiscovered ? PROVENANCE.RUN_DISCOVERED : null)
            || (z.engineerEdited || z.createdBy === 'engineer'
              ? PROVENANCE.ENGINEER_CREATED
              : PROVENANCE.UNKNOWN),
          origin: z.origin
            || z.provenance
            || (z.runDiscovered ? PROVENANCE.RUN_DISCOVERED : null)
            || (z.engineerEdited || z.createdBy === 'engineer'
              ? PROVENANCE.ENGINEER_CREATED
              : PROVENANCE.UNKNOWN),
          status: z.status,
          fields: z.fields || {},
        };
      });
    const payload = {
      version: 1,
      source: 'safety_build',
      appliedAt: new Date().toISOString(),
      zones: appliedZones,
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

  /** Stamp Active Project identity onto Safety draft (Erased Means Erased). */
  window.safetyBuildStampIdentity = function safetyBuildStampIdentity(identity) {
    const AS = ensureAutogenState();
    if (!AS.safety_build) AS.safety_build = { zones: [], devices: [] };
    AS.safety_build.projectIdentity = identity || null;
    AS.safety_build.machine = identity?.machine || '';
    try {
      localStorage.setItem('siteforge.safetyBuild.v1', JSON.stringify({
        ...AS.safety_build,
        deletedZones: [...(state.deletedZones || [])],
      }));
    } catch (_) { /* ignore */ }
  };

  document.addEventListener('DOMContentLoaded', () => {
    bind();
  });

  // Also bind immediately if DOM already ready
  if (document.readyState !== 'loading') bind();
})();
