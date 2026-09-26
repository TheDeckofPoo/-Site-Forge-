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
    ENGINEER_CREATED: 'ENGINEER CREATED',
    SUGGESTED_DIGIT_MATCH: 'SUGGESTED',
    UNRESOLVED: 'UNRESOLVED',
  };

  /** Site Forge modal — Electron does not support window.prompt(). */
  async function sbAskText(title, message, defaultValue) {
    const fn = window.__tbApi?.askText || window.askText;
    if (typeof fn === 'function') return fn(title, message, defaultValue);
    status('Text dialog unavailable — reload Site Forge');
    return null;
  }

  async function sbAskYesNo(title, message) {
    const fn = window.__tbApi?.askYesNo || window.askYesNo;
    if (typeof fn === 'function') return fn(title, message);
    return false;
  }

  async function sbShowInfo(title, message, detail) {
    const fn = window.__tbApi?.showInfo || window.showInfo;
    if (typeof fn === 'function') return fn(title, message, detail);
    status(`${title}: ${message}`);
  }

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
    'default_safety',
    'unassigned_safety',
    'default_safety_zone',
    'unassigned_safety_zone',
  ]);
  const PLACEHOLDER_AREA_RE = /^Zone([1-9])_Area$/i;
  const PLACEHOLDER_ZONE_RE = /^Zone([1-9])_ESZone\d*$/i;
  const NUMERIC_STEM_ZONE_RE = /^(\d{2,})_ESZone\d*$/i;

  function isDefaultSafetyName(name) {
    const s = String(name || '').trim().toLowerCase();
    if (!s) return true;
    if (DEFAULT_SAFETY_ALIASES.has(s)) return true;
    const su = s.replace(/[\s\-]+/g, '_');
    if (DEFAULT_SAFETY_ALIASES.has(su)) return true;
    if (su.startsWith('default_') && su.includes('eszone')) return true;
    if (su.startsWith('unassigned_') && su.includes('eszone')) return true;
    return false;
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

  const KIND_ORDER = ['ESTOP', 'ESLS', 'ESR', 'MCR', 'CS', 'OTHER'];
  const KIND_LABEL = {
    ESTOP: 'E-Stops',
    ESLS: 'ESLS',
    ESR: 'ESR',
    MCR: 'MCR',
    CS: 'CS',
    OTHER: 'Other',
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
    /** Inventory membership filter: ALL | UNASSIGNED | IN_ZONE | ELSEWHERE | SHARED */
    membershipFilter: 'ALL',
    dirty: false,
    /** Zone source_ids engineer deleted — must not reappear from Transport / RUN seeds. */
    deletedZones: new Set(),
  };

  const MEMBERSHIP_FILTERS = [
    { id: 'ALL', label: 'All' },
    { id: 'UNASSIGNED', label: 'Unassigned' },
    { id: 'IN_ZONE', label: 'In this zone' },
    { id: 'ELSEWHERE', label: 'Assigned elsewhere' },
    { id: 'SHARED', label: 'Shared / multiple' },
  ];

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
        const areaStem = String(aname).replace(/_Area$/i, '');
        const areaDefault = String(area.defaultSafetyZone || '').trim();
        (area.nodes || []).forEach((n) => {
          const tag = String(n.conveyorTag || '').trim();
          const zname = String(n.safetyZone || '').trim();
          if (!zname || !tag) return;
          // Area→ESZone1 suggestion on nodes is NOT an operational/RUN zone seed.
          const zStem = zname.replace(/_ESZone\d*$/i, '');
          const areaDerived = !!(areaStem && zStem && areaStem.toLowerCase() === zStem.toLowerCase()
            && /_ESZone1$/i.test(zname));
          const fromAreaDefault = !!(areaDefault && areaDefault.toLowerCase() === zname.toLowerCase());
          if (!zoneMap.has(zname)) {
            zoneMap.set(zname, {
              name: zname,
              area: aname,
              areaRef: aname,
              conveyors: [],
              members: [],
              // Mark Area-derived so buildClientModel classifies AUTO_DEFAULT (not RUN)
              provenance: (areaDerived || fromAreaDefault) ? 'AUTO_DEFAULT' : '',
              origin: (areaDerived || fromAreaDefault) ? 'AUTO_DEFAULT' : '',
              areaOrigin: (areaDerived || fromAreaDefault) ? 'AUTO_DEFAULT' : '',
            });
          }
          const z = zoneMap.get(zname);
          if (!z.area && aname) z.area = aname;
          if (!z.areaRef && aname) z.areaRef = aname;
          if (!z.conveyors.includes(tag)) z.conveyors.push(tag);
          if ((areaDerived || fromAreaDefault) && !z.createdBy) {
            z.provenance = z.provenance || 'AUTO_DEFAULT';
            z.origin = z.origin || 'AUTO_DEFAULT';
          }
        });
      });
      // Registry shells — including empty engineer-created zones with zero conveyors.
      // Gate E — key by immutable source_id when present; display engineering_name.
      (data.safetyZones || []).forEach((z) => {
        const eng = String(z.engineering_name || z.name || '').trim();
        if (!eng) return;
        const sid = String(z.source_id || z.id || '').trim();
        const mapKey = sid || eng;
        const existing = zoneMap.get(mapKey) || (sid ? null : zoneMap.get(eng));
        const engineer = !!(
          z.createdBy === 'engineer'
          || z.provenance === 'ENGINEER_CREATED'
          || z.origin === 'ENGINEER_CREATED'
        );
        if (!existing) {
          // Drop name-keyed stub if we now have a proper source_id entry
          if (sid && zoneMap.has(eng) && !zoneMap.get(eng).source_id) zoneMap.delete(eng);
          zoneMap.set(mapKey, {
            name: eng,
            source_id: sid || eng,
            engineering_name: eng,
            area: z.areaRef || z.area || '',
            areaRef: z.areaRef || z.area || '',
            conveyors: [],
            members: Array.isArray(z.members) ? [...z.members] : [],
            createdBy: engineer ? 'engineer' : (z.createdBy || ''),
            provenance: engineer ? 'ENGINEER_CREATED' : (z.provenance || ''),
            origin: engineer ? 'ENGINEER_CREATED' : (z.origin || ''),
            operational: z.operational !== false,
            status: z.status || 'REVIEW_REQUIRED',
          });
        } else {
          if (engineer) {
            existing.createdBy = 'engineer';
            existing.provenance = 'ENGINEER_CREATED';
            existing.origin = 'ENGINEER_CREATED';
          }
          if (!existing.areaRef && (z.areaRef || z.area)) {
            existing.areaRef = z.areaRef || z.area;
            existing.area = existing.areaRef;
          }
          if (sid) existing.source_id = sid;
          existing.engineering_name = eng;
          existing.name = eng;
        }
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
    // GATE 4 — honor persisted RUN only with current-session runIds OR genuine
    // RUN evidence. Area→${stem}_ESZone1 empty shells must not stick as RUN
    // after restart merely because a prior Transport seed was mis-labeled.
    if (z.provenance === PROVENANCE.RUN_DISCOVERED || z.origin === PROVENANCE.RUN_DISCOVERED
      || z.runDiscovered) {
      if (isPlaceholderOrTestZoneName(sid) || isPlaceholderOrTestZoneName(disp)) {
        return PROVENANCE.TEST_FIXTURE;
      }
      if (runIds.has(sid) || runIds.has(disp)) {
        return PROVENANCE.RUN_DISCOVERED;
      }
      const hasMembers = Array.isArray(z.members) && z.members.length > 0;
      const conf = String(z.membership_confidence || '').toUpperCase();
      const memOrigin = String(z.membersOrigin || '').toUpperCase();
      const genuineRun = hasMembers && (
        ['CONFIRMED', 'HIGH', 'HIGH_CONFIDENCE', 'PROVEN'].includes(conf)
        || ['AUTO_RUN_PROVEN', 'AUTO', 'PROVEN'].includes(memOrigin)
      );
      if (genuineRun) return PROVENANCE.RUN_DISCOVERED;
      // Area-derived default shell (ORNCCP2_Area → ORNCCP2_ESZone1)
      const stem = String(sid || disp).replace(/_ESZone\d*$/i, '');
      const areaStem = String(area || '').replace(/_Area$/i, '');
      if (!hasMembers && stem && areaStem && stem.toLowerCase() === areaStem.toLowerCase()
        && /_ESZone1$/i.test(sid || disp)) {
        return PROVENANCE.AUTO_DEFAULT;
      }
      if (!hasMembers) return PROVENANCE.AUTO_DEFAULT;
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

  function hasActiveSiteSession() {
    try {
      if (typeof window.SiteSession?.hasActiveSite === 'function') {
        return !!window.SiteSession.hasActiveSite();
      }
      const s = typeof window.getActiveSiteSession === 'function'
        ? window.getActiveSiteSession()
        : null;
      return !!(s && String(s.archive_sha || '').trim() && String(s.machine || '').trim());
    } catch (_) {
      return false;
    }
  }

  function activeSiteIdentity() {
    try {
      return typeof window.getActiveSiteSession === 'function'
        ? window.getActiveSiteSession()
        : { archive_sha: '', machine: '', loadEpoch: 0 };
    } catch (_) {
      return { archive_sha: '', machine: '', loadEpoch: 0 };
    }
  }

  function safetyDraftStorageKey(identity) {
    const sha = String(identity?.archive_sha || '').trim();
    const mach = String(identity?.machine || '').trim();
    if (sha && mach) return `siteforge.safetyBuild.v1::${sha}::${mach}`;
    return '';
  }

  /**
   * HARD LAW: no active RUN/archive/machine → Safety inventory must be empty.
   * Unscoped localStorage / workbook / PG must never hydrate live site devices.
   */
  function emptySafetyShell(reason) {
    return {
      version: 1,
      kind: 'SafetyModel',
      devices: [],
      zones: [],
      unassignedDevices: [],
      inventoryByKind: {
        ESTOP: [], ESLS: [], ESR: [], MCR: [], CS: [], OTHER: [],
      },
      counts: {
        devices: 0,
        devices_found: 0,
        estops: 0,
        esls: 0,
        esr: 0,
        mcr: 0,
        cs: 0,
        other_safety: 0,
        unassigned: 0,
        automatically_resolved: 0,
        engineer_assigned: 0,
        ready: 0,
        review_required: 0,
        zones: 0,
        zones_ready: 0,
        zones_review: 0,
        completion_pct: 0,
        conservation_ok: true,
      },
      safety_evidence_complete: false,
      no_active_run: true,
      no_active_run_reason: reason || 'NO_ACTIVE_RUN',
    };
  }

  function buildClientModel() {
    /** Client-side SafetyModel assembly (mirrors Python fortna_safety_model). */
    if (!hasActiveSiteSession()) {
      return emptySafetyShell('NO_ACTIVE_RUN');
    }
    const AS = ensureAutogenState();
    const wb = AS.workbook || {};
    // GATE B: never let a hollow AS.safety_build shadow disk memberships.
    // Member-rich engineer state wins; empty {zones:[]} must not wipe Apply.
    const preferFn = (typeof window.preferSafetyBuild === 'function')
      ? window.preferSafetyBuild
      : ((a, b) => {
        const az = (a && Array.isArray(a.zones)) ? a.zones : [];
        const bz = (b && Array.isArray(b.zones)) ? b.zones : [];
        const aMem = az.reduce((n, z) => n + ((z.members || []).length), 0);
        const bMem = bz.reduce((n, z) => n + ((z.members || []).length), 0);
        if (bMem > aMem) return b || a || { zones: [] };
        if (aMem > bMem) return a || b || { zones: [] };
        return a || b || { zones: [] };
      });
    const eng = preferFn(AS.safety_build, wb.safety_build) || { zones: [] };
    // Keep AS aligned so Apply cannot snapshot hollow state
    if (eng && Array.isArray(eng.zones) && eng.zones.some((z) => (z.members || []).length)) {
      AS.safety_build = eng;
    }
    const transportZones = transportZonesFromCanvas();
    const areaConvs = areaConveyorsFromWorkbook();
    // Normalize areas → string names (objects from Transport must not coerce via String())
    const areas = (Array.isArray(wb.areas) ? wb.areas : [])
      .map(areaNameOf)
      .filter(Boolean);
    // Prefer live discovered devices from current RUN. After Load/Clear/refresh,
    // AS.safetyDevices is authoritative (possibly empty) — never revive prior ESPB*.
    // Never fall back to eng.devices when safetyDevices was never set for this session
    // (that path hydrated ghost inventory from unscoped localStorage).
    const live = normalizeDeviceList(AS.safetyDevices || []);
    const devices = Array.isArray(AS.safetyDevices) ? live : [];

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
      const sid = String(z.source_id || z.name || '').trim();
      if (!sid || deleted.has(sid) || isCorruptZoneName(sid)) return;
      const engineerShell = !!(
        z.createdBy === 'engineer'
        || z.provenance === PROVENANCE.ENGINEER_CREATED
        || z.origin === PROVENANCE.ENGINEER_CREATED
      );
      // Empty placeholder names only drop when NOT engineer-created
      if (!engineerShell && isPlaceholderOrTestZoneName(sid) && !(z.conveyors || []).length) return;
      const areaRef = areaNameOf(z.areaRef || z.area) || String(z.areaRef || z.area || '').trim();
      if (isCorruptZoneName(areaRef)) return;
      const existing = findZone(sid);
      if (existing) {
        if (!(existing.conveyorRefs || []).length && (z.conveyors || []).length) {
          existing.conveyorRefs = [...z.conveyors];
          existing.conveyorsOrigin = 'AUTO_RUN_PROVEN';
        }
        if (!existing.areaRef && areaRef) {
          existing.areaRef = areaRef;
          existing.areaOrigin = engineerShell ? 'ENGINEER_CREATED' : 'AUTO_RUN_PROVEN';
        }
        if (engineerShell) {
          existing.createdBy = 'engineer';
          existing.provenance = PROVENANCE.ENGINEER_CREATED;
          existing.origin = PROVENANCE.ENGINEER_CREATED;
          existing.engineerEdited = true;
          existing.operational = true;
        }
        return;
      }
      const areaDefaultSeed = !!(
        z.provenance === PROVENANCE.AUTO_DEFAULT
        || z.origin === PROVENANCE.AUTO_DEFAULT
        || z.areaOrigin === 'AUTO_DEFAULT'
      );
      const zStem = String(sid).replace(/_ESZone\d*$/i, '');
      const aStem = String(areaRef || '').replace(/_Area$/i, '');
      const areaDerived = !engineerShell && !!(zStem && aStem
        && zStem.toLowerCase() === aStem.toLowerCase()
        && /_ESZone1$/i.test(sid)
        && !(z.members || []).length);
      // Area→ESZone1 suggestions are NOT operational Safety rows
      if (areaDefaultSeed || areaDerived) return;
      putZone({
        id: sid,
        source_id: sid,
        name: String(z.engineering_name || z.name || sid).trim(),
        engineering_name: String(z.engineering_name || z.name || sid).trim(),
        areaRef: areaRef,
        areaOrigin: engineerShell ? 'ENGINEER_CREATED' : (areaRef ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED'),
        conveyorRefs: [...(z.conveyors || [])],
        conveyorsOrigin: (z.conveyors || []).length ? 'AUTO_RUN_PROVEN' : 'UNRESOLVED',
        // Zone existence ≠ membership — empty engineer shells are valid
        members: Array.isArray(z.members) ? [...z.members] : [],
        membersOrigin: (z.members || []).length ? 'ENGINEER_ASSIGNED' : 'UNRESOLVED',
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        resetSource: areaRef ? `${areaRef}.Reset` : '',
        silenceSource: areaRef ? `${areaRef}.Silence` : '',
        resetOrigin: areaRef ? (engineerShell ? 'ENGINEER_CREATED' : 'AUTO_RUN_PROVEN') : 'UNRESOLVED',
        silenceOrigin: areaRef ? (engineerShell ? 'ENGINEER_CREATED' : 'AUTO_RUN_PROVEN') : 'UNRESOLVED',
        suggestions: [],
        engineerEdited: engineerShell,
        createdBy: engineerShell ? 'engineer' : '',
        status: z.status || 'REVIEW_REQUIRED',
        fields: {},
        operational: true,
        // Engineer shells stay ENGINEER_CREATED even when empty (never AUTO_DEFAULT)
        provenance: engineerShell ? PROVENANCE.ENGINEER_CREATED : PROVENANCE.LEGACY_CANONICAL,
        origin: engineerShell ? PROVENANCE.ENGINEER_CREATED : PROVENANCE.LEGACY_CANONICAL,
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
      // GATE 4 — restore persisted RUN/engineer identity on Apply/reopen,
      // but NEVER revive Area→ESZone1 empty shells as RUN (ORNCCP2_ESZone1).
      const ezArea = areaNameOf(ez.area || ez.areaRef) || '';
      const ezStem = String(sid || engName).replace(/_ESZone\d*$/i, '');
      const ezAreaStem = String(ezArea).replace(/_Area$/i, '');
      const ezAreaDerived = !!(ezStem && ezAreaStem
        && ezStem.toLowerCase() === ezAreaStem.toLowerCase()
        && /_ESZone1$/i.test(sid || engName)
        && !(ez.members || []).length
        && !ez.engineerEdited && ez.createdBy !== 'engineer');
      const ezGenuineRun = !!(ez.members || []).length && membersAreProven(
        ez.membersOrigin, ez.membership_confidence,
      );
      if (!ezAreaDerived && ezGenuineRun && (
        ez.runDiscovered || ez.provenance === PROVENANCE.RUN_DISCOVERED
        || ez.origin === PROVENANCE.RUN_DISCOVERED
      )) {
        cur.runDiscovered = true;
      }
      if (ezAreaDerived) {
        // Skip putting Area-default suggestion into operational model
        return;
      }
      if (ez.provenance && ez.provenance !== PROVENANCE.AUTO_DEFAULT) cur.provenance = ez.provenance;
      if (ez.origin && ez.origin !== PROVENANCE.AUTO_DEFAULT) cur.origin = ez.origin;
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
        // Per-membership provenance (many-to-many edges); never invent PROVEN.
        if (ez.memberMeta && typeof ez.memberMeta === 'object') {
          cur.memberMeta = { ...(cur.memberMeta || {}), ...ez.memberMeta };
        }
      } else if (Array.isArray(ez.members) && !ez.members.length && (cur.members || []).length) {
        // Never let an empty eng overlay wipe existing members (handoff race)
        cur.membersOrigin = cur.membersOrigin || 'ENGINEER_ASSIGNED';
        cur.engineerEdited = true;
      }
      if (ez.memberMeta && typeof ez.memberMeta === 'object' && !Array.isArray(ez.members)) {
        cur.memberMeta = { ...(cur.memberMeta || {}), ...ez.memberMeta };
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

    // Same display name from RUN + ENGINEER must not silently coexist as duplicates.
    // Reconcile by source_id/origin: keep engineer row, fold RUN evidence, mark REVIEW.
    (() => {
      const byDisp = new Map(); // lower(display) → [zones]
      for (const z of byId.values()) {
        if (isDefaultSafetyZone(z)) continue;
        const d = zoneDisplayName(z).toLowerCase();
        if (!d) continue;
        if (!byDisp.has(d)) byDisp.set(d, []);
        byDisp.get(d).push(z);
      }
      for (const [, group] of byDisp) {
        if (group.length < 2) continue;
        const eng = group.find((z) =>
          z.engineerEdited
          || z.createdBy === 'engineer'
          || z.provenance === PROVENANCE.ENGINEER_CREATED
          || z.origin === PROVENANCE.ENGINEER_CREATED
        );
        const run = group.find((z) =>
          z.runDiscovered
          || z.provenance === PROVENANCE.RUN_DISCOVERED
          || z.origin === PROVENANCE.RUN_DISCOVERED
        );
        if (eng && run && zoneSourceId(eng) !== zoneSourceId(run)) {
          eng.runDiscovered = true;
          eng.runEvidenceSourceId = zoneSourceId(run);
          eng.nameConflict = {
            kind: 'DISPLAY_NAME_COLLISION',
            run_source_id: zoneSourceId(run),
            engineer_source_id: zoneSourceId(eng),
            display_name: zoneDisplayName(eng),
          };
          eng.status = 'REVIEW_REQUIRED';
          eng.membership_status = 'REVIEW_REQUIRED';
          // Prefer engineer conveyors; fill from RUN if empty
          if (!(eng.conveyorRefs || []).length && (run.conveyorRefs || []).length) {
            eng.conveyorRefs = [...run.conveyorRefs];
            eng.conveyorsOrigin = eng.conveyorsOrigin || 'AUTO_RUN_PROVEN';
          }
          byId.delete(zoneSourceId(run));
          continue;
        }
        // Multiple engineer or multiple RUN with same display — keep first, mark rest conflict
        const keep = group[0];
        keep.status = 'REVIEW_REQUIRED';
        keep.nameConflict = {
          kind: 'DISPLAY_NAME_COLLISION',
          peers: group.slice(1).map((z) => zoneSourceId(z)),
          display_name: zoneDisplayName(keep),
        };
        group.slice(1).forEach((z) => byId.delete(zoneSourceId(z)));
      }
    })();

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
      // RUN_DISCOVERED only survives when present in *current* session runIds
      const runLive = !!(z.runDiscovered || z.provenance === PROVENANCE.RUN_DISCOVERED)
        && (runIds.has(sid) || runIds.has(disp));
      if ((z.runDiscovered || z.provenance === PROVENANCE.RUN_DISCOVERED) && !runLive
        && !z.engineerEdited && z.provenance !== PROVENANCE.ENGINEER_CREATED
        && z.createdBy !== 'engineer') {
        // Stale RUN shell from a prior session/project — drop
        byId.delete(sid);
        continue;
      }
      const keep = transportNames.has(sid)
        || transportNames.has(disp)
        || runLive
        || z.engineerEdited
        || z.provenance === PROVENANCE.ENGINEER_CREATED
        || z.createdBy === 'engineer'
        || z.provenance === PROVENANCE.LEGACY_CANONICAL
        || (area && areaSet.has(area) && !isPlaceholderOrTestZoneName(sid) && runLive);
      // If we have current areas and this zone's area is gone → drop (unless live RUN/engineer)
      if (areaSet.size > 0 && area && !areaSet.has(area)
        && !transportNames.has(sid) && !transportNames.has(disp)
        && !runLive && !z.engineerEdited
        && z.provenance !== PROVENANCE.ENGINEER_CREATED
        && z.createdBy !== 'engineer') {
        byId.delete(sid);
        continue;
      }
      // Orphan zone with no area and not on canvas → drop (unless live RUN/engineer shell)
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

    // Zone membership → many-to-many device.safetyZoneRefs + primary safetyZoneRef.
    // Default/Unassigned Safety is an OWNERSHIP BUCKET, not an operational zone —
    // never treat its members as AUTO_RESOLVED / ENGINEER_ASSIGNED.
    // A device may participate in multiple engineer zones without duplication.
    const memberToZones = new Map(); // UPPER → [{ zone, origin }]
    zones.forEach((z) => {
      if (isDefaultSafetyZone(z)) return;
      const zOrigin = z.membersOrigin || (z.engineerEdited ? 'ENGINEER_ASSIGNED' : 'AUTO_RUN_PROVEN');
      const zName = zoneDisplayName(z) || z.name;
      (z.members || []).forEach((m) => {
        const key = String(m).toUpperCase();
        const meta = (z.memberMeta && (z.memberMeta[m] || z.memberMeta[key])) || {};
        const edge = {
          zone: zName,
          origin: String(meta.origin || zOrigin).toUpperCase(),
        };
        if (!memberToZones.has(key)) memberToZones.set(key, []);
        const list = memberToZones.get(key);
        if (!list.some((x) => x.zone.toUpperCase() === zName.toUpperCase())) {
          list.push(edge);
        }
      });
    });

    const deviceList = (devices || []).map((d) => {
      const base = typeof d === 'string'
        ? { name: d, kind: classifyDevName(d) || 'OTHER' }
        : { ...d };
      const key = String(base.name || '').toUpperCase();
      const memberships = memberToZones.get(key) || [];
      // Drop any Default-bucket stamps from backend
      const cleanMemberships = memberships.filter((x) => x.zone && !isDefaultSafetyName(x.zone));
      base.kind = base.kind || classifyDevName(base.name) || 'OTHER';
      base.classification = base.classification || base.kind;
      base.safetyZoneRefs = cleanMemberships.map((x) => x.zone);
      base.memberships = cleanMemberships;
      const zoneRef = cleanMemberships.length ? cleanMemberships.map((x) => x.zone).join(', ') : '';
      base.safetyZoneRef = zoneRef || null;
      if (cleanMemberships.length) {
        const anyEng = cleanMemberships.some((x) => x.origin === 'ENGINEER_ASSIGNED');
        const assignOrigin = anyEng
          ? 'ENGINEER_ASSIGNED'
          : (cleanMemberships[0].origin || base.origin || 'AUTO_RUN_PROVEN');
        if (cleanMemberships.length > 1) {
          base.status = 'SHARED';
          base.origin = assignOrigin;
        } else if (assignOrigin === 'ENGINEER_ASSIGNED') {
          base.status = 'ENGINEER_ASSIGNED';
          base.origin = 'ENGINEER_ASSIGNED';
        } else {
          base.status = 'AUTO_RESOLVED';
          if (!base.origin || base.origin === 'UNRESOLVED') base.origin = assignOrigin || 'AUTO_RUN_PROVEN';
        }
        base.defaultSafety = false;
      } else {
        base.status = 'UNASSIGNED';
        base.safetyZoneRef = null;
        base.safetyZoneRefs = [];
        base.memberships = [];
        base.defaultSafety = true;
      }
      return base;
    });

    const unassigned = deviceList.filter((d) => d && d.name && d.status === 'UNASSIGNED');
    const autoResolved = deviceList.filter((d) => d.status === 'AUTO_RESOLVED');
    const engAssigned = deviceList.filter((d) =>
      d.status === 'ENGINEER_ASSIGNED' || d.status === 'SHARED');
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
        safetyZoneRefs: d.safetyZoneRefs || [],
        memberships: d.memberships || [],
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
    // Keep aligned with fortna_safety_model._classify_device (ESPB*, ESLS, ESR, MCR, …)
    // Deterministic device identity only — INT_* interlocks and embedded …1ESR1 never classify.
    // ORI-041/043: no free \w* tails; failed MCR must not fall through to ESTOP.
    const u = String(name || '').trim().toUpperCase().replace(/-/g, '_');
    if (!u) return '';
    if (u.startsWith('INT_')) return '';
    if (/(?:^|_)MEM(?:_|$)/.test(u) || u.includes('_NOT_OK')) return '';
    if (u.includes('ESLS')) return 'ESLS';
    // ESR — optional _AUX only (reject 6ESR_NOT_OK logical/memory bits)
    if (
      /^T_\d+ESR\d*(?:_?AUX)?$/.test(u)
      || /^CP\d+_ESR\d*(?:_?AUX)?$/.test(u)
      || /^\d+ESR\d*(?:_?AUX)?$/.test(u)
      || /^ESR\d+(?:_?AUX)?$/.test(u)
      || /^ESR\d*$/.test(u)
    ) return 'ESR';
    // MCR — deterministic device identity only (ORI-037 / ORI-043).
    if (
      /^T_\d+MCR\d+(?:_?AUX)?$/.test(u)
      || /^CP\d+_MCR\d+(?:_?AUX)?$/.test(u)
      || /^\d+MCR\d+(?:_?AUX)?$/.test(u)
      || /^MCR\d+(?:_?AUX)?$/.test(u)
    ) return 'MCR';
    // Failed MCR-ish tokens must not become ESTOP
    if (/(?:^|_|T_)(?:CP\d+_)?MCR/.test(u) || /^\d+MCR/.test(u)) return '';
    if (/^CP\d+_CS\d*$/.test(u) || /_CS\d*$/.test(u) || u.endsWith('_CS')) return 'CS';
    // E-stop pushbuttons: ESPB24 / ESPB2 (ES+PB — not matched by ES\d alone)
    if (/^ESPB\d/.test(u) || /(^|_)ESPB\d/.test(u)) return 'ESTOP';
    // T_2ES, CP2_ES…, 2ES, ES400, ES406, ES-JES2
    if (
      /^T_\d+ES\d*\w*$/.test(u)
      || /^CP\d+_ES\d*\w*$/.test(u)
      || /^ES\d[\w]*$/.test(u)
      || /^\d+ES\d*\w*$/.test(u)
      || /(^|_)ES\d/.test(u)
      || /^ES[_]?JES/.test(u)
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
   * Gate H — ingest ONLY genuine RUN-proven zone shells into the session cache.
   * Area→ESZone1 / AUTO_DEFAULT / Transport suggestions must NEVER enter
   * AS.runSafetyZones (that path was resurrecting ORNCCP2_ESZone1 as RUN).
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
      const prov = String(z.provenance || z.origin || '').toUpperCase();
      if (prov === PROVENANCE.AUTO_DEFAULT || prov === 'SUGGESTED') return;
      // Require an explicit RUN birth certificate from the model — do not promote
      // every zone row (engineer / Area-default) into AS.runSafetyZones.
      const claimedRun = !!(z.runDiscovered || prov === PROVENANCE.RUN_DISCOVERED);
      if (!claimedRun) return;
      const proven = membersAreProven(z.membersOrigin, z.membership_confidence);
      const hasMembers = Array.isArray(z.members) && z.members.length > 0;
      // Area-derived empty shell — never RUN even if wrongly flagged
      const stem = String(sid).replace(/_ESZone\d*$/i, '');
      const areaStem = String(areaRef || '').replace(/_Area$/i, '');
      const areaDerived = !!(stem && areaStem && stem.toLowerCase() === areaStem.toLowerCase()
        && /_ESZone1$/i.test(sid) && !hasMembers);
      if (areaDerived) return;
      // Hollow false-RUN without proven membership — skip (suggestion, not RUN)
      if (!hasMembers && !proven) return;
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
    // Session-only RUN cache — never merge into persisted safety_build.zones.
    // Persisting RUN shells caused Trash_ESZone1 — RUN to survive restart without
    // current RUN evidence (stale state across Site Forge restart).
    AS.runSafetyZones = shells;
    return shells;
  }

  /** Durable engineer zones only — RUN_DISCOVERED shells are session/rebuild only. */
  function isPersistedEngineerZone(z) {
    if (!z || isDefaultSafetyZone(z) || isDefaultSafetyName(zoneSourceId(z) || z.name)) {
      return false;
    }
    if (z.engineerEdited || z.createdBy === 'engineer') return true;
    const prov = String(z.provenance || z.origin || '').trim();
    return prov === PROVENANCE.ENGINEER_CREATED;
  }

  /** UNION helper — merge device lists by name; never first-non-empty-wins. */
  function unionDeviceLists(...lists) {
    const by = new Map();
    lists.flat().forEach((d) => {
      if (!d || !d.name) return;
      const key = String(d.name).toUpperCase();
      const cur = by.get(key);
      if (!cur) {
        by.set(key, { ...d });
        return;
      }
      // Merge provenance / physical fields; prefer richer record
      const merged = { ...cur };
      ['kind', 'classification', 'physicalEndpoint', 'engineerName', 'source', 'status'].forEach((k) => {
        if (!merged[k] && d[k]) merged[k] = d[k];
      });
      const ev = [...(cur.evidence || []), ...(d.evidence || [])];
      if (ev.length) merged.evidence = ev;
      const srcs = new Set([...(cur.sources || []), ...(d.sources || [])]);
      if (d.source) srcs.add(d.source);
      if (srcs.size) merged.sources = [...srcs];
      by.set(key, merged);
    });
    return [...by.values()];
  }

  async function loadDevicesFromRun() {
    const A = api();
    const AS = ensureAutogenState();
    let lastErr = '';
    const buckets = [];
    let evidenceComplete = null;

    // ORI-039: discovery in progress — block assignment against partial inventory
    AS.safetyDiscoveryInProgress = true;
    state.discoveryInProgress = true;

    // Wipe prior inventory so foreign/stale ESPB* from another controller cannot survive
    AS.safetyDevices = [];
    if (!AS.safety_build) AS.safety_build = { zones: [] };
    AS.safety_build.devices = [];
    AS.safetyDevicesGrouped = [];
    AS.safetyEvidenceComplete = null;

    if (!hasActiveSiteSession()) {
      AS.safetyEvidenceComplete = false;
      AS.safetyDiscoveryInProgress = false;
      state.discoveryInProgress = false;
      return [];
    }

    // 1) Canonical SafetyModel (evidence UNION via fortna_safety_model.py)
    // ORI-035: pass active machine explicitly — NEVER omit (desktop must not default).
    const identity = activeSiteIdentity();
    const activeMachine = String(identity.machine || '').trim();
    if (!activeMachine) {
      AS.safetyEvidenceComplete = false;
      AS.safetyDiscoveryInProgress = false;
      state.discoveryInProgress = false;
      lastErr = 'ACTIVE_MACHINE_REQUIRED — load a RUN/project so Safety discovery uses the correct controller';
      status(lastErr);
      return [];
    }
    if (typeof A.buildSafetyModel === 'function') {
      try {
        const res = await A.buildSafetyModel({ machine: activeMachine });
        if ((res?.ok || res?.success) && res.model) {
          // Refuse cross-controller inventory even if IPC mishandles identity
          const modelMach = String(res.model.machine || '').trim().toUpperCase();
          if (modelMach && modelMach !== activeMachine.toUpperCase()) {
            lastErr = `Safety model machine mismatch: got ${res.model.machine}, active ${activeMachine}`;
            status(lastErr);
          } else {
            try { ingestRunDiscoveredZones(res.model.zones || []); } catch (_) { /* ignore */ }
            const mapped = normalizeDeviceList(res.model.devices || []);
            buckets.push(mapped);
            AS.safetyDevicesGrouped = res.model.safetyDevices || res.model.evidence_union?.devices || [];
            evidenceComplete = res.model.safety_evidence_complete;
            if (res.model.evidence_union) {
              AS.safetyEvidenceUnion = res.model.evidence_union;
            }
          }
        } else {
          lastErr = res?.error || res?.message || 'buildSafetyModel failed';
          if (res?.code === 'ACTIVE_MACHINE_REQUIRED') {
            status(lastErr);
            return [];
          }
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
        if (mapped.length) buckets.push(mapped);
      } catch (_) { /* ignore */ }
    }

    // 3) Hardware I/O — engineer Names + proven name classifications + safetyRole
    // UNION with model inventory (never skip because ESTOP/ESLS already found).
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
          // Prefer engineer safetyRole / proven channel names; skip unresolved-only noise
          const role = String(obj.safetyRole || '').trim().toUpperCase();
          const owner = String(obj.owner_state || obj.ownerState || '').trim().toUpperCase();
          const nm = obj.engineer_name || obj.engineerName || obj.sourceName || obj.source_name
            || obj.Name || obj.name || obj.tag || obj.effectiveName;
          if (nm && (role || classifyDevName(String(nm)))) {
            if (owner && ['UNRESOLVED_OWNER', 'UNKNOWN'].includes(owner) && !role) {
              // Foreign/unresolved named points must not pollute current-site inventory
            } else {
              names.push(role
                ? { name: String(nm), kind: role, source: 'HARDWARE_IO', physicalEndpoint: obj.physical_address || '' }
                : String(nm));
            }
          }
          Object.values(obj).forEach((v) => {
            if (v && typeof v === 'object') walk(v);
          });
        };
        walk(res);
        const mapped = normalizeDeviceList(names);
        if (mapped.length) buckets.push(mapped);
      } catch (_) { /* ignore */ }
    }

    let merged = unionDeviceLists(...buckets);
    // ORI-033: stamp active machine + drop foreign-controller rows from engineer layers
    merged = merged.map((d) => {
      if (!d || typeof d !== 'object') return d;
      if (!d.machine) return { ...d, machine: activeMachine };
      return d;
    });
    const scoped = filterDevicesToActiveMachine(merged, activeMachine);
    AS.safetyForeignExcluded = scoped.foreign;
    merged = scoped.local;
    // Scope grouped canonical devices the same way
    if (Array.isArray(AS.safetyDevicesGrouped)) {
      const gScoped = filterDevicesToActiveMachine(
        AS.safetyDevicesGrouped.map((d) => (
          d && typeof d === 'object' && !d.machine ? { ...d, machine: activeMachine } : d
        )),
        activeMachine,
      );
      AS.safetyDevicesGrouped = gScoped.local;
      AS.safetyForeignExcluded = [
        ...(AS.safetyForeignExcluded || []),
        ...gScoped.foreign,
      ];
    }
    AS.safetyDevices = merged;
    AS.safety_build.devices = merged;
    AS.safetyEvidenceComplete = evidenceComplete;
    AS.safetyDiscoveryInProgress = false;
    state.discoveryInProgress = false;
    if (!merged.length) {
      status(`No Safety devices loaded — ${lastErr || 'unknown'}. Click Refresh discovery.`);
    }
    return merged;
  }

  async function refreshModel() {
    if (!hasActiveSiteSession()) {
      const AS = ensureAutogenState();
      AS.safetyDevices = [];
      AS.safetyDevicesGrouped = [];
      AS.safetyEvidenceUnion = null;
      AS.safetyEvidenceComplete = false;
      AS.runSafetyZones = []; // clear stale RUN cache
      if (AS.safety_build) {
        AS.safety_build.devices = [];
        AS.safety_build.unassignedDevices = [];
      }
      state.model = emptySafetyShell('NO_ACTIVE_RUN');
      render();
      syncReadiness();
      status('NO ACTIVE RUN — Safety inventory empty until a site is loaded.');
      return;
    }
    status('Discovering Safety devices…');
    // Clear prior-session RUN zone cache before rediscovery from active RUN
    try {
      const AS = ensureAutogenState();
      AS.runSafetyZones = [];
      // Strip any RUN-only shells that leaked into persisted engineer draft
      if (AS.safety_build && Array.isArray(AS.safety_build.zones)) {
        AS.safety_build.zones = AS.safety_build.zones.filter((z) =>
          isDefaultSafetyZone(z) || isPersistedEngineerZone(z)
        );
      }
    } catch (_) { /* ignore */ }
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
    const o = String(origin || '').toUpperCase();
    const cls = (o === 'ENGINEER_ASSIGNED' || o === 'ENGINEER_CREATED')
      ? 'text-fuchsia-300'
      : o === 'AUTO_RUN_PROVEN'
        ? 'text-emerald-400/90'
        : o === 'SUGGESTED_DIGIT_MATCH'
          ? 'text-sky-400/90'
          : 'text-amber-300/90';
    return `<span class="text-[9px] ${cls}">${label}</span>`;
  }

  function statusChip(status, zoneRef) {
    const st = String(status || '').toUpperCase();
    if (st === 'ENGINEER_ASSIGNED' || st === 'AUTO_RESOLVED' || st === 'ASSIGNED'
      || st === 'SHARED') {
      const z = zoneRef ? ` → ${escapeHtml(zoneRef)}` : '';
      const label = st === 'ENGINEER_ASSIGNED' ? 'ENGINEER'
        : (st === 'AUTO_RESOLVED' ? 'AUTO'
          : (st === 'SHARED' ? 'SHARED' : 'ASSIGNED'));
      return `<span class="text-[8px] text-emerald-400/90">${label}${z}</span>`;
    }
    return '<span class="text-[8px] text-amber-300/90">UNASSIGNED</span>';
  }

  /**
   * Many-to-many: every operational zone that lists this device as a member.
   * Returns [{ zone, source_id, origin }].
   */
  function zonesForDevice(devName) {
    const want = String(devName || '').trim().toUpperCase();
    if (!want || !state.model) return [];
    const out = [];
    const seen = new Set();
    (state.model.zones || []).forEach((z) => {
      if (isDefaultSafetyZone(z)) return;
      const members = (z.members || []).map((m) => String(m).toUpperCase());
      if (!members.includes(want)) return;
      const zn = zoneDisplayName(z);
      const key = zn.toUpperCase();
      if (!zn || seen.has(key)) return;
      seen.add(key);
      const meta = (z.memberMeta && (z.memberMeta[devName] || z.memberMeta[want])) || {};
      out.push({
        zone: zn,
        source_id: zoneSourceId(z),
        origin: String(meta.origin || z.membersOrigin || z.provenance || 'UNKNOWN').toUpperCase(),
      });
    });
    return out;
  }

  /** Compact secondary membership line for inventory / assign views. */
  function formatMembershipHint(devName, opts) {
    const zones = zonesForDevice(devName);
    const cur = selectedZone();
    const curName = cur && !isDefaultSafetyZone(cur) ? zoneDisplayName(cur) : '';
    const curU = curName.toUpperCase();
    const inThis = curU && zones.some((z) => z.zone.toUpperCase() === curU);
    const others = zones.filter((z) => z.zone.toUpperCase() !== curU);
    const sharedReview = zones.length > 1
      && /ES\d|ESTOP/i.test(String(devName || ''))
      ? ' · <span class="text-amber-400/80">REVIEW — shared across multiple zones</span>'
      : '';
    if (!zones.length) {
      return '<div class="text-[8px] text-amber-300/80 leading-tight">Unassigned</div>';
    }
    if (opts?.context === 'zone' && curName) {
      if (inThis && others.length) {
        return `<div class="text-[8px] text-slate-500 leading-tight">In this zone · Also in: ${
          others.map((z) => escapeHtml(z.zone)).join(', ')
        }${sharedReview}</div>`;
      }
      if (inThis) {
        return '<div class="text-[8px] text-emerald-500/80 leading-tight">In this zone</div>';
      }
      return `<div class="text-[8px] text-slate-500 leading-tight">In: ${
        zones.map((z) => escapeHtml(z.zone)).join(', ')
      }${sharedReview}</div>`;
    }
    if (zones.length === 1) {
      return `<div class="text-[8px] text-slate-500 leading-tight">In zone: ${escapeHtml(zones[0].zone)}</div>`;
    }
    return `<div class="text-[8px] text-slate-500 leading-tight">In zones: ${
      zones.map((z) => escapeHtml(z.zone)).join(', ')
    }${sharedReview}</div>`;
  }

  function deviceMatchesMembershipFilter(devName, filterId) {
    const f = String(filterId || state.membershipFilter || 'ALL').toUpperCase();
    if (f === 'ALL') return true;
    const zones = zonesForDevice(devName);
    const cur = selectedZone();
    const curName = cur && !isDefaultSafetyZone(cur) ? zoneDisplayName(cur).toUpperCase() : '';
    const inThis = curName && zones.some((z) => z.zone.toUpperCase() === curName);
    if (f === 'UNASSIGNED') return zones.length === 0;
    if (f === 'IN_ZONE') return !!inThis;
    if (f === 'ELSEWHERE') return zones.length > 0 && !inThis;
    if (f === 'SHARED') return zones.length > 1;
    return true;
  }

  /** Stamp per-membership provenance when engineer adds a device to a zone. */
  function ensureMemberMeta(z, names, origin) {
    if (!z) return;
    z.memberMeta = z.memberMeta && typeof z.memberMeta === 'object' ? z.memberMeta : {};
    const orig = String(origin || 'ENGINEER_ASSIGNED').toUpperCase();
    const now = new Date().toISOString();
    (names || []).forEach((n) => {
      const nm = String(n || '').trim();
      if (!nm) return;
      const prev = z.memberMeta[nm] || {};
      // Never upgrade an engineer edge to PROVEN; preserve existing RUN provenance.
      if (prev.origin && /PROVEN|RUN/i.test(prev.origin) && /ENGINEER/i.test(orig)) {
        z.memberMeta[nm] = { ...prev };
        return;
      }
      if (prev.origin === 'ENGINEER_ASSIGNED' && /PROVEN|RUN/i.test(orig)) {
        // Do not turn engineer-created membership into PROVEN
        z.memberMeta[nm] = { ...prev };
        return;
      }
      z.memberMeta[nm] = {
        origin: orig,
        assignedAt: prev.assignedAt || now,
        assignedBy: prev.assignedBy || ( /ENGINEER/i.test(orig) ? 'engineer' : 'run'),
      };
    });
  }

  function dropMemberMeta(z, names) {
    if (!z?.memberMeta) return;
    const drop = new Set((names || []).map((n) => String(n).toUpperCase()));
    Object.keys(z.memberMeta).forEach((k) => {
      if (drop.has(k.toUpperCase())) delete z.memberMeta[k];
    });
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
      <div class="mt-2 text-[9px] text-slate-600 leading-snug">Assign devices in the zone detail panel. Site inventory above lists every current-machine Safety device.</div>`;
  }

  function categoryStats(rows) {
    let assigned = 0;
    let unassigned = 0;
    let review = 0;
    (rows || []).forEach((d) => {
      const st = String(d.status || '').toUpperCase();
      const disp = String(d.disposition || '').toUpperCase();
      if (disp === 'REVIEW_REQUIRED' || st === 'REVIEW_REQUIRED' || st === 'ORPHAN_REVIEW_REQUIRED') {
        review += 1;
      } else if (st === 'ENGINEER_ASSIGNED' || st === 'AUTO_RESOLVED' || st === 'ASSIGNED'
        || st === 'SHARED') {
        assigned += 1;
      } else {
        unassigned += 1;
      }
    });
    return { found: (rows || []).length, assigned, unassigned, review };
  }

  /**
   * Assignable Safety inventory = canonical SafetyDevices with current-site physical I/O.
   * Prefer grouped devices (safetyDevices / evidence_union / AS.safetyDevicesGrouped).
   * Flat signal aliases remain in diagnostics/provenance only.
   */
  /**
   * PD-0034 / PD-0002: bare MCR energize coils (1MCR1 / T_1MCR1 / CP1_MCR1)
   * are COMMAND — never zone-member eligible. MCR*_AUX is FEEDBACK / ES_OK.
   * Keep aligned with fortna_es_compiler.is_mcr_energize_coil.
   */
  function isMcrEnergizeCoil(name) {
    let n = String(name || '').trim();
    if (!n) return false;
    n = n.replace(/^T_/i, '');
    if (/_AUX$/i.test(n)) return false;
    return /^\d*MCR\d*$/i.test(n)
      || /^CP\d+_MCR\d*$/i.test(n)
      || /^MCR\d*$/i.test(n);
  }

  function isMcrAuxFeedback(name) {
    // ORI-036: plain 1MCR1_AUX must match WITHOUT needing a T_ sibling.
    // Accept underscore and no-underscore Fortna forms.
    const n = String(name || '').trim();
    if (!n) return false;
    return /^T_\d*MCR\d*_?AUX$/i.test(n)
      || /^CP\d+_MCR\d*_?AUX$/i.test(n)
      || /^\d+MCR\d*_?AUX$/i.test(n)
      || /^MCR\d*_?AUX$/i.test(n)
      || /(?:^|_)MCR\d+_?AUX$/i.test(n);
  }

  /**
   * Classify a related signal under a canonical SafetyDevice.
   * Device grouping ≠ I/O aliasing — do not call these "aliases".
   */
  function classifyRelatedSafetySignal(sig, deviceName) {
    const name = String(
      typeof sig === 'string' ? sig : (sig?.name || ''),
    ).trim();
    const phys = String(
      (typeof sig === 'object' && (sig.physicalEndpoint || sig.physical_address)) || '',
    ).trim();
    const role = String(
      (typeof sig === 'object' && (sig.role || sig.signalRole)) || '',
    ).toUpperCase();
    const upper = name.toUpperCase();
    const isT = /^T_/.test(upper);
    const isAux = /_AUX$/i.test(name);
    let kind = 'TAG/NAME variant';
    let zoneMemberEligible = true;
    // PD-0034: MCR command vs feedback under the canonical MCR device
    if (isMcrEnergizeCoil(name)) {
      kind = 'COMMAND — not zone-member eligible';
      zoneMemberEligible = false;
    } else if (isMcrAuxFeedback(name) || (isAux && /MCR/i.test(name))) {
      kind = 'FEEDBACK / ES_OK — Safety-member eligible';
      zoneMemberEligible = true;
    } else if (isAux && phys) {
      kind = 'AUX physical signal';
    } else if (isAux && !phys) {
      kind = 'nonphysical RUN evidence';
    } else if (isT && !phys) {
      kind = 'TAG/NAME variant';
    } else if (isT && phys) {
      kind = 'TAG/NAME variant';
    } else if (role === 'PRIMARY' || upper === String(deviceName || '').toUpperCase()) {
      kind = phys ? 'PRIMARY physical signal' : 'nonphysical RUN evidence';
    } else if (phys) {
      kind = 'PRIMARY physical signal';
    } else {
      kind = 'nonphysical RUN evidence';
    }
    return {
      name,
      physicalEndpoint: phys,
      kind,
      zoneMemberEligible,
      sources: (typeof sig === 'object' && sig.sources) || [],
    };
  }

  function formatSafetySignalEvidence(d) {
    const sigs = Array.isArray(d.signals) && d.signals.length
      ? d.signals
      : (d.signalNames || []).map((n) => ({ name: n }));
    if (!sigs.length) return '';
    const rows = sigs.map((s) => classifyRelatedSafetySignal(s, d.name));
    const n = rows.length;
    const details = rows.map((r) => {
      const ep = r.physicalEndpoint
        ? ` · <span class="text-sky-400/80">${escapeHtml(r.physicalEndpoint)}</span>`
        : ' · <span class="text-slate-600">no separate physical endpoint</span>';
      const elig = r.zoneMemberEligible === false
        ? ' · <span class="text-amber-400/90">not assignable</span>'
        : '';
      return `<div class="mono">${escapeHtml(r.name)} — ${escapeHtml(r.kind)}${ep}${elig}</div>`;
    }).join('');
    return `<details class="text-[8px] text-slate-600 mt-0.5"><summary class="cursor-pointer">${n} related signal${n === 1 ? '' : 's'}</summary>${details}</details>`;
  }

  function deviceHasPhysicalClaim(d) {
    if (!d || typeof d !== 'object') return false;
    const phys = String(
      d.physicalEndpoint || d.physical_address || d.physical_endpoint || '',
    ).trim();
    if (phys) return true;
    if (d.engineerPhysical === true || d.physicalAssigned === true) return true;
    if (String(d.io_word || d.ioWord || '').trim()) return true;
    if (d.physicalIoRef && (d.physicalIoRef.io_word || d.physicalIoRef.physical_address)) {
      return true;
    }
    if (d.configio_backed === true || d.configIoBacked === true) return true;
    const sigs = d.signals || d.members || d.raw_names || d.relatedSignals || [];
    if (Array.isArray(sigs) && sigs.some((s) => {
      if (!s || typeof s === 'string') return false;
      return !!(s.physicalEndpoint || s.physical_address || s.physical_endpoint
        || s.io_word || s.configio_backed);
    })) return true;
    return false;
  }

  function isAssignablePhysicalSafetyDevice(d) {
    if (!d || !(d.name || d.id)) return false;
    // ORI-041: logical/memory names are never assignable physical devices
    const bareName = String(d.name || d.id || d.canonicalTag || '').trim();
    if (!classifyDevName(bareName)) return false;
    // Canonical MCR device is assignable when it carries AUX feedback evidence.
    // Bare command coil without AUX is not a Safety feedback member.
    if (isMcrEnergizeCoil(bareName)) {
      const sigs = d.signals || d.signalNames || d.relatedSignals || [];
      const hasAux = Array.isArray(sigs) && sigs.some((s) => {
        const sn = typeof s === 'string' ? s : (s?.name || '');
        return isMcrAuxFeedback(sn);
      });
      if (!hasAux && !isMcrAuxFeedback(bareName)) return false;
    }
    // ORI-030: name-only / unknown-owner candidates are NOT assignable.
    // Physical endpoint (or inherited related-signal phys / configio claim) required.
    // Strong RUN evidence without endpoint → review/diagnostic, not assignable.
    if (!deviceHasPhysicalClaim(d)) return false;
    return true;
  }

  /** Normalize a grouped SafetyDevice into inventory row shape. */
  function normalizeCanonicalSafetyDevice(g) {
    if (!g || typeof g !== 'object') return null;
    const name = String(g.name || g.id || g.canonicalTag || '').trim();
    if (!name) return null;
    const signals = Array.isArray(g.signals) ? g.signals : [];
    const signalNames = Array.isArray(g.signalNames)
      ? g.signalNames
      : signals.map((s) => (typeof s === 'string' ? s : s?.name)).filter(Boolean);
    let phys = String(
      g.physicalEndpoint
      || g.physical_address
      || g.physical_endpoint
      || '',
    ).trim();
    if (!phys) {
      for (const s of signals) {
        if (!s || typeof s === 'string') continue;
        const ep = String(s.physicalEndpoint || s.physical_address || s.physical_endpoint || '').trim();
        if (ep) { phys = ep; break; }
      }
    }
    if (!phys && (g.io_word || g.ioWord) && (g.io_bit != null || g.ioBit != null)) {
      phys = `${g.io_word || g.ioWord}.${g.io_bit != null ? g.io_bit : g.ioBit}`;
    }
    const kind = String(g.kind || classifyDevName(name) || 'OTHER').toUpperCase();
    return {
      name,
      id: g.id || name,
      kind: KIND_ORDER.includes(kind) ? kind : (classifyDevName(name) || 'OTHER'),
      canonicalTag: g.canonicalTag || name,
      stem: g.stem || '',
      groupKey: g.groupKey || '',
      signals,
      signalNames,
      physicalEndpoint: phys,
      io_word: g.io_word || g.ioWord || '',
      io_bit: g.io_bit != null ? g.io_bit : (g.ioBit != null ? g.ioBit : ''),
      physicalIoRef: g.physicalIoRef || null,
      status: g.status || 'GROUPED',
      origin: g.origin || '',
      source: g.source || '',
      sources: g.sources || [],
      safetyZoneRef: g.safetyZoneRef || null,
      evidence: g.evidence || [],
      review_reason: g.reason || g.review_reason || '',
      inventory_scope: g.inventory_scope || '',
    };
  }

  function collectCanonicalSafetyDevices() {
    const AS = ensureAutogenState();
    const grouped = AS.safetyDevicesGrouped
      || state.model?.safetyDevices
      || state.model?.evidence_union?.devices
      || AS.safetyEvidenceUnion?.devices
      || [];
    if (Array.isArray(grouped) && grouped.length) {
      return grouped.map(normalizeCanonicalSafetyDevice).filter(Boolean);
    }
    // Fallback: flat SafetyModel devices (preserve physicalEndpoint / io evidence)
    return (state.model?.devices || []).map((d) => {
      if (!d || typeof d !== 'object') {
        const nm = String(d || '').trim();
        if (!nm) return null;
        return normalizeCanonicalSafetyDevice({ name: nm, kind: classifyDevName(nm) });
      }
      return normalizeCanonicalSafetyDevice(d);
    }).filter(Boolean);
  }

  function partitionSafetyInventory(devices, opts) {
    const signalCount = opts?.signalsDiscovered != null
      ? opts.signalsDiscovered
      : (devices || []).reduce((n, d) => {
        const sigs = d.signalNames || d.signals;
        if (Array.isArray(sigs) && sigs.length) return n + sigs.length;
        return n + 1;
      }, 0);
    const assignable = [];
    const nonphysical = [];
    const reviewAmbiguous = [];
    const rejectReasons = {};
    (devices || []).forEach((d) => {
      if (String(d.status || '').toUpperCase() === 'REVIEW_REQUIRED'
        && /ambiguous/i.test(String(d.review_reason || d.reason || ''))) {
        reviewAmbiguous.push(d);
        return;
      }
      if (isAssignablePhysicalSafetyDevice(d)) assignable.push(d);
      else {
        nonphysical.push(d);
        let why = 'NON_PHYSICAL_OR_ALIAS';
        const bare = String(d.name || '').trim();
        if (isMcrEnergizeCoil(bare) && !isMcrAuxFeedback(bare)) why = 'BARE_MCR_COMMAND';
        else if (!String(d.physicalEndpoint || '').trim()) why = 'NO_PHYSICAL_ENDPOINT';
        rejectReasons[why] = (rejectReasons[why] || 0) + 1;
      }
    });
    // ORI-030: do NOT promote name-only / nonphysical rows into assignable.
    // Valid canonical devices must carry a physical claim (direct or inherited).
    return {
      assignable,
      nonphysical,
      reviewAmbiguous,
      reject_reasons: rejectReasons,
      signals_discovered: signalCount,
      raw_signals: signalCount,
      canonical_physical: assignable.length,
      nonphysical_aliases_suppressed: Math.max(0, signalCount - assignable.length),
      review_required_physical: assignable.filter(
        (d) => String(d.status || '').toUpperCase().includes('REVIEW'),
      ).length + reviewAmbiguous.length,
    };
  }

  /** ORI-033: active machine owns flat + Default + assignable layers. */
  function filterDevicesToActiveMachine(devices, activeMachine) {
    const mach = String(activeMachine || '').trim().toUpperCase();
    const local = [];
    const foreign = [];
    (devices || []).forEach((d) => {
      if (!d) return;
      const row = typeof d === 'string' ? { name: d } : d;
      const dm = String(
        row.machine || row.Machine_Name || row.controller || '',
      ).trim().toUpperCase();
      const cross = !!(row.crossControllerDependency || row.remote_dependency || row.isRemoteDependency);
      if (cross) {
        local.push({ ...row, inventory_scope: 'REMOTE_DEPENDENCY' });
        return;
      }
      if (!mach || !dm || dm === mach || ['N/A', 'NA', 'ALL', 'NONE'].includes(dm)) {
        local.push({ ...row, inventory_scope: 'LOCAL_PHYSICAL' });
      } else {
        foreign.push({ ...row, inventory_scope: 'UNRELATED_FOREIGN' });
      }
    });
    return { local, foreign, active_machine: mach };
  }

  function renderInventory() {
    // Engineer-facing assignable inventory = canonical physical SafetyDevices.
    const host = $('sb-inventory');
    if (!host) return;
    renderZoneSummary();
    if (!state.model) {
      host.innerHTML = '<div class="text-[10px] text-slate-600 p-2">No devices yet — Refresh discovery.</div>';
      return;
    }
    const filt = String(state.inventoryFilter || state.filter || '').trim().toUpperCase();
    const AS = ensureAutogenState();
    const flatSignals = state.model.devices || [];
    const canonical = collectCanonicalSafetyDevices();
    const part = partitionSafetyInventory(canonical, {
      signalsDiscovered: flatSignals.length || canonical.reduce(
        (n, d) => n + ((d.signalNames || d.signals || []).length || 1),
        0,
      ),
    });
    // Surface ambiguous groupings as REVIEW rows (not invented devices)
    const devices = [
      ...part.assignable,
      ...part.reviewAmbiguous.map((d) => ({
        ...d,
        status: 'REVIEW_REQUIRED',
        name: d.name || d.stem || 'AMBIGUOUS',
      })),
    ];
    state.safetyInventoryPartition = part;
    const byKind = {};
    KIND_ORDER.forEach((k) => { byKind[k] = []; });
    devices.forEach((d) => {
      if (!d || !d.name) return;
      if (filt && !String(d.name).toUpperCase().includes(filt)
        && !String(d.safetyZoneRef || '').toUpperCase().includes(filt)
        && !(d.safetyZoneRefs || []).some((z) => String(z).toUpperCase().includes(filt))
        && !String(d.kind || '').toUpperCase().includes(filt)) return;
      if (!deviceMatchesMembershipFilter(d.name, state.membershipFilter)) return;
      const k = KIND_ORDER.includes(d.kind) ? d.kind : 'OTHER';
      byKind[k].push(d);
    });
    const c = state.model.counts || {};
    // Engineer-facing PHYSICAL = canonical devices (not raw signal aliases).
    // Do not reuse flat-signal unassigned counts — that produced FOUND 120 / PHYSICAL 0.
    const found = part.canonical_physical;
    const physUnassigned = devices.filter((d) => {
      const st = String(d.status || '').toUpperCase();
      return st === 'UNASSIGNED' || st === 'GROUPED' || !st
        || d.defaultSafety === true;
    }).length;
    const left = physUnassigned;
    const autoN = devices.filter((d) => String(d.status || '').toUpperCase() === 'AUTO_RESOLVED').length;
    const engN = devices.filter((d) => {
      const st = String(d.status || '').toUpperCase();
      return st === 'ENGINEER_ASSIGNED' || st === 'SHARED';
    }).length;
    const mismatch = !filt && Number(found) !== part.assignable.length;
    const evidenceOk = AS.safetyEvidenceComplete === true
      || state.model.safety_evidence_complete === true;
    const zonesReady = Number(c.ready || c.zones_ready || 0);
    const zonesReview = Number(c.review_required || c.zones_review || 0);
    let cols = '';
    KIND_ORDER.forEach((k) => {
      const rows = byKind[k] || [];
      const st = categoryStats(rows);
      // Always show category header with counts (even when empty after filter)
      cols += `<div class="min-w-0">
        <div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold mb-1 sticky top-0 bg-[#0a1018] py-0.5">
          ${KIND_LABEL[k] || k}
          <span class="text-slate-600 font-normal normal-case">
            found ${st.found} · assigned ${st.assigned} · unassigned ${st.unassigned}${st.review ? ` · review ${st.review}` : ''}
          </span>
        </div>
        <div class="space-y-0.5">${rows.length ? rows.map((d) => {
          const phys = String(d.physicalEndpoint || d.physical_address || '').trim();
          const viewIo = phys
            ? `<button type="button" class="text-[8px] text-sky-400/90 hover:text-sky-300 shrink-0" data-sb-view-io="${escapeHtml(phys)}" title="Physical ${escapeHtml(phys)}">View I/O</button>`
            : '';
          const signalHint = formatSafetySignalEvidence(d);
          const memHint = formatMembershipHint(d.name, { context: 'zone' });
          const inSelected = (() => {
            const cur = selectedZone();
            if (!cur || isDefaultSafetyZone(cur)) return false;
            const want = String(d.name).toUpperCase();
            return (cur.members || []).some((m) => String(m).toUpperCase() === want);
          })();
          return `
          <label class="flex items-start gap-1.5 px-1 py-0.5 rounded hover:bg-slate-900/80 cursor-pointer" data-sb-inv-row="${escapeHtml(d.name)}" ${phys ? `data-physical-endpoint="${escapeHtml(phys)}"` : ''}>
            <input type="checkbox" data-sb-inv="${escapeHtml(d.name)}" class="rounded border-slate-600 mt-0.5"${inSelected ? ' checked' : ''}>
            <div class="flex-1 min-w-0">
              <button type="button" data-sb-inv-pick="${escapeHtml(d.name)}" class="w-full text-left mono text-[11px] text-slate-300 hover:text-rose-200 truncate">${escapeHtml(d.name)}</button>
              ${memHint}
              ${signalHint}
            </div>
            ${viewIo}
            ${statusChip(d.status, (d.safetyZoneRefs || []).length > 1 ? `${(d.safetyZoneRefs || []).length} zones` : (d.safetyZoneRefs || [])[0] || d.safetyZoneRef)}
          </label>`;
        }).join('') : '<div class="text-[9px] text-slate-700 px-1">—</div>'}</div>
      </div>`;
    });
    if (!hasActiveSiteSession()) {
      host.innerHTML = `
        <div class="flex items-center gap-2 mb-2 flex-wrap">
          <span class="text-[10px] uppercase tracking-wider text-cyan-400/90 font-semibold">Site Safety Inventory</span>
          <span class="text-[10px] mono text-slate-300">FOUND 0 · AUTO 0 · ENGINEER 0 · UNASSIGNED 0</span>
          <span class="text-[9px] mono text-amber-300/90" title="Safety inventory requires an active RUN/archive/machine">NO ACTIVE RUN</span>
        </div>
        <div class="text-slate-500 text-[11px] p-3 rounded-lg border border-slate-800 bg-[#070b12]">
          No active RUN loaded. Safety inventory stays empty until a site archive is loaded.
          PostgreSQL learning knowledge never hydrates live Safety devices.
        </div>`;
      return;
    }
    const memFilt = String(state.membershipFilter || 'ALL').toUpperCase();
    const memChips = MEMBERSHIP_FILTERS.map((f) => {
      const on = memFilt === f.id;
      return `<button type="button" data-sb-mem-filt="${f.id}" class="text-[9px] px-2 py-0.5 rounded border ${
        on
          ? 'border-cyan-500/60 bg-cyan-950/40 text-cyan-200'
          : 'border-slate-700 text-slate-400 hover:border-slate-500'
      }" title="Membership filter: ${escapeHtml(f.label)}">${escapeHtml(f.label)}</button>`;
    }).join('');
    host.innerHTML = `
      <div class="flex items-center gap-2 mb-2 flex-wrap">
        <span class="text-[10px] uppercase tracking-wider text-cyan-400/90 font-semibold">Site Safety Inventory</span>
        <span class="text-[10px] mono text-slate-300" title="PHYSICAL = canonical Safety devices (not raw signal aliases)">PHYSICAL ${found} · AUTO ${autoN} · ENGINEER ${engN} · UNASSIGNED PHYS ${Math.max(0, found - engN - autoN)}</span>
        <span class="text-[9px] mono text-slate-500" title="RAW SIGNALS are evidence rows; aliases may be suppressed only when a canonical physical device survives">RAW SIGNALS ${part.raw_signals || part.signals_discovered} · aliases suppressed ${part.nonphysical_aliases_suppressed} · phys review ${part.review_required_physical}</span>
        <span class="text-[9px] mono ${mismatch ? 'text-rose-300' : 'text-emerald-400/80'}">${mismatch ? `GUI ${devices.length} ≠ physical ${found}` : `GUI ${devices.length} = physical ${found}`}</span>
        <span class="text-[9px] mono ${evidenceOk ? 'text-emerald-400/80' : 'text-amber-300/90'}" title="Evidence union vs zone Apply completion are separate">
          ${evidenceOk ? 'SAFETY_EVIDENCE_COMPLETE' : 'EVIDENCE_REVIEW'} · zones ready ${zonesReady} / review ${zonesReview}
        </span>
        <input id="sb-inv-filter" type="search" placeholder="Filter…" class="ml-auto bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-[10px] w-28" value="${escapeHtml(state.inventoryFilter || '')}">
      </div>
      <div class="flex items-center gap-1 mb-2 flex-wrap" title="Many-to-many membership filters — devices assigned elsewhere stay selectable">${memChips}</div>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-3">${cols || '<div class="text-slate-600 p-2 text-[10px]">No devices match</div>'}</div>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <button type="button" id="sb-inv-assign-selected" class="btn-primary text-[10px] px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 border border-emerald-500/40 text-white font-semibold" title="Assign checked devices into the currently selected Safety Zone">
          Assign Selected → Zone
        </button>
        <button type="button" id="sb-inv-assign" class="btn-ghost text-[10px] px-3 py-1.5 rounded-lg border border-emerald-900/50 text-emerald-300" title="Pick zone + confirm list">
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
    // Filter without destroying the search input (preserves keyboard focus).
    const applyInvFilter = (raw) => {
      const filt = String(raw || '').trim().toUpperCase();
      state.inventoryFilter = raw || '';
      state.filter = state.inventoryFilter;
      host.querySelectorAll('[data-sb-inv-row]').forEach((row) => {
        const name = String(row.getAttribute('data-sb-inv-row') || '').toUpperCase();
        const show = !filt || name.includes(filt);
        row.style.display = show ? '' : 'none';
      });
      // Update per-kind empty hints only; do not rebuild DOM.
      refreshAssignLabel();
    };
    const filtEl = $('sb-inv-filter');
    if (filtEl && !filtEl._sbFilterWired) {
      filtEl._sbFilterWired = true;
      filtEl.addEventListener('input', (ev) => {
        applyInvFilter(ev.target.value || '');
      });
    }
    // Apply current filter once after paint (without focus steal)
    if (filt) applyInvFilter(state.inventoryFilter || '');
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
    host.querySelectorAll('[data-sb-mem-filt]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        state.membershipFilter = btn.getAttribute('data-sb-mem-filt') || 'ALL';
        renderInventory();
      });
    });
    host.querySelectorAll('[data-sb-view-io]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const addr = btn.getAttribute('data-sb-view-io') || '';
        status(`View I/O — physical ${addr || '—'} (open Hardware I/O and locate this address)`);
      });
    });
  }

  /**
   * PD-0034: map inventory picks to zone-member-eligible tags.
   * Bare MCR command coils → AUX feedback when present; otherwise rejected.
   */
  function resolveZoneMemberEligibleNames(rawNames) {
    const devices = collectCanonicalSafetyDevices();
    const byUpper = new Map();
    devices.forEach((d) => {
      const key = String(d.name || d.id || '').toUpperCase();
      if (key) byUpper.set(key, d);
    });
    const out = [];
    const rejected = [];
    const remapped = [];
    const seen = new Set();
    (rawNames || []).forEach((raw) => {
      const name = String(raw || '').trim();
      if (!name) return;
      let member = name;
      if (isMcrEnergizeCoil(name)) {
        const d = byUpper.get(name.toUpperCase());
        const sigs = [
          ...((d && d.signalNames) || []),
          ...((d && d.signals) || []).map((s) => (typeof s === 'string' ? s : s?.name)).filter(Boolean),
        ];
        // Remap COMMAND → FEEDBACK only when a real AUX signal exists in inventory.
        // Never invent `${name}_AUX` — that created ES_UDT members while IO_MAP
        // still OTEd the physical coil (GATE C / Warden 4MCR1AUX defect).
        const aux = sigs.find((s) => isMcrAuxFeedback(s)) || '';
        if (aux) {
          remapped.push(`${name} → ${aux} (FEEDBACK)`);
          member = aux;
        } else {
          rejected.push(`${name} (COMMAND — not zone-member eligible)`);
          return;
        }
      }
      const key = member.toUpperCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(member);
    });
    return { members: out, rejected, remapped };
  }

  function safetyDiscoveryBlocking() {
    const AS = ensureAutogenState();
    if (state.discoveryInProgress || AS.safetyDiscoveryInProgress) return true;
    if (AS.safetyEvidenceComplete === false) return true;
    // Incomplete when discovery flag is null AND no grouped inventory yet
    if (AS.safetyEvidenceComplete == null
      && !(AS.safetyDevicesGrouped || []).length
      && !(AS.safetyDevices || []).length) {
      return true;
    }
    return false;
  }

  /** Primary action: assign checked inventory devices to the currently selected zone. */
  function assignCheckedToSelectedZone() {
    // ORI-039: refuse assignment against incomplete/stale discovery
    if (safetyDiscoveryBlocking()) {
      status('SAFETY_DISCOVERY_IN_PROGRESS — wait for Safety discovery to finish before assigning');
      return;
    }
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
    const rawNames = [...(host?.querySelectorAll('[data-sb-inv]:checked') || [])]
      .map((el) => el.getAttribute('data-sb-inv'))
      .filter(Boolean);
    if (!rawNames.length) {
      status('Check devices in Device Inventory first');
      return;
    }
    const resolved = resolveZoneMemberEligibleNames(rawNames);
    const names = resolved.members;
    if (!names.length) {
      status(resolved.rejected.length
        ? `Nothing assignable — ${resolved.rejected.join('; ')}`
        : 'Check devices in Device Inventory first');
      return;
    }
    const live = findLiveZone(z);
    if (!live || isDefaultSafetyZone(live)) return;
    // Many-to-many: ADD membership to this zone only. Never strip from other zones.
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
      ensureMemberMeta(zz, names, 'ENGINEER_ASSIGNED');
    });
    const notes = [];
    if (resolved.remapped.length) notes.push(`remapped ${resolved.remapped.join(', ')}`);
    if (resolved.rejected.length) notes.push(`skipped ${resolved.rejected.join(', ')}`);
    status(
      `Assigned ${names.length} device(s) → ${zoneDisplayName(live)}`
      + (notes.length ? ` (${notes.join('; ')})` : '')
      + ' (Apply Safety to persist)',
    );
  }

  /** Gate E — guided bulk assign: select → choose zone → confirm list → Apply later */
  async function openAssignDevicesWizard() {
    if (safetyDiscoveryBlocking()) {
      status('SAFETY_DISCOVERY_IN_PROGRESS — wait for Safety discovery to finish before assigning');
      return;
    }
    const host = $('sb-inventory');
    const detail = $('sb-zone-detail');
    const checked = [
      ...(host?.querySelectorAll('[data-sb-inv]:checked') || []),
      ...(detail?.querySelectorAll('[data-sb-inv]:checked') || []),
    ];
    const seen = new Set();
    const rawNames = [];
    checked.forEach((el) => {
      const n = el.getAttribute('data-sb-inv');
      if (!n || seen.has(n.toUpperCase())) return;
      seen.add(n.toUpperCase());
      rawNames.push(n);
    });
    if (!rawNames.length) {
      status('Check devices first (Default Safety list or inventory), then Assign Devices…');
      return;
    }
    const resolved = resolveZoneMemberEligibleNames(rawNames);
    const names = resolved.members;
    if (!names.length) {
      status(resolved.rejected.length
        ? `Nothing assignable — ${resolved.rejected.join('; ')}`
        : 'Check devices first (Default Safety list or inventory), then Assign Devices…');
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
    const remapNote = resolved.remapped.length
      ? `\nRemapped COMMAND→FEEDBACK:\n${resolved.remapped.map((r) => `  • ${r}`).join('\n')}\n`
      : '';
    const rejectNote = resolved.rejected.length
      ? `\nSkipped (not zone-member eligible):\n${resolved.rejected.map((r) => `  • ${r}`).join('\n')}\n`
      : '';
    // Electron: Site Forge modal (window.prompt unsupported)
    const zonePick = await sbAskText(
      'Assign devices to Safety Zone',
      `Assign ${names.length} device(s) to which Safety Zone?\n\n`
      + `Zones:\n${zones.map((z) => `  • ${z}`).join('\n')}\n\n`
      + 'Type the destination zone name exactly:',
      defaultZone,
    );
    if (zonePick == null) return;
    const dest = String(zonePick || '').trim();
    if (!zones.includes(dest)) {
      status(`Unknown zone “${dest}” — cancelled`);
      await sbShowInfo('Unknown Safety Zone', `“${dest}” is not an engineer Safety Zone — assignment cancelled.`);
      return;
    }
    const ok = await sbAskYesNo(
      'Confirm assignment',
      `Destination: ${dest}\n`
      + `Devices (${names.length}):\n`
      + names.map((n) => `  • ${n}`).join('\n')
      + remapNote
      + rejectNote
      + `\nNothing is persisted until you click Apply Safety.`,
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
    // Many-to-many: ADD only — never strip from other zones.
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
      ensureMemberMeta(zz, names, 'ENGINEER_ASSIGNED');
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
      const conflictNote = (!isDef && z.nameConflict)
        ? `<div class="text-[9px] text-amber-400 mt-0.5">REVIEW — display-name collision with ${
            escapeHtml(z.nameConflict.run_source_id || (z.nameConflict.peers || []).join(', ') || 'another origin')
          }</div>`
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
          ${conflictNote}
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
        // Must await — deleteSafetyZone is async (modal confirm)
        Promise.resolve(deleteSafetyZone(btn.getAttribute('data-sb-zone-del')))
          .catch((err) => status(`Delete failed: ${err?.message || err}`));
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
        ${row(
          'Engineering name',
          escapeHtml(disp),
          'READY',
          (z.engineerEdited || z.createdBy === 'engineer' || z.provenance === PROVENANCE.ENGINEER_CREATED)
            ? 'ENGINEER_CREATED'
            : 'AUTO_RUN_PROVEN',
        )}
        ${row(
          'Source identity',
          escapeHtml(sid),
          'READY',
          (z.provenance === PROVENANCE.ENGINEER_CREATED || z.createdBy === 'engineer' || String(sid).startsWith('szone_'))
            ? 'ENGINEER_CREATED'
            : 'AUTO_RUN_PROVEN',
        )}
        ${row('Area', escapeHtml(z.areaRef || '—'), f.Area, z.areaOrigin)}
        ${row('Conveyors', `${(z.conveyorRefs || []).length}`, f.Conveyors, z.conveyorsOrigin)}
        ${row('E-Stops', z.eStops.length ? escapeHtml(z.eStops.join(', ')) : 'none assigned', f['E-Stops'], z.membersOrigin)}
        ${row('ESR', z.esrDevices.length ? escapeHtml(z.esrDevices.join(', ')) : 'none assigned', f.ESR, z.membersOrigin)}
        ${row('MCR', z.mcrDevices.length ? escapeHtml(z.mcrDevices.join(', ')) : 'none assigned', f.MCR, z.membersOrigin)}
        ${row('CS', (z.csDevices || []).length ? escapeHtml(z.csDevices.join(', ')) : 'none assigned', f.CS || 'UNRESOLVED', z.membersOrigin)}
        ${row('ESLS', (z.eslsDevices || []).length ? escapeHtml(z.eslsDevices.join(', ')) : 'none assigned', f.ESLS || 'UNRESOLVED', z.membersOrigin)}
        ${row('Reset', escapeHtml(z.resetSource || 'none assigned'), f.Reset, z.resetOrigin)}
        ${row('Silence', escapeHtml(z.silenceSource || 'none assigned'), f.Silence, z.silenceOrigin)}
      </div>
      <div class="rounded-xl border border-rose-900/40 bg-rose-950/10 p-3 mb-3">
        <div class="text-[11px] uppercase tracking-wider text-rose-300/90 font-semibold mb-2">Required zone roles</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
          ${['E-STOPS', 'ESR', 'MCR', 'CS', 'ESLS', 'RESET'].map((role) => {
            const map = {
              'E-STOPS': { members: z.eStops || [], status: f['E-Stops'], assign: 'ESTOP' },
              ESR: { members: z.esrDevices || [], status: f.ESR, assign: 'ESR' },
              MCR: { members: z.mcrDevices || [], status: f.MCR, assign: 'MCR' },
              CS: { members: z.csDevices || [], status: f.CS, assign: 'CS' },
              ESLS: { members: z.eslsDevices || [], status: f.ESLS, assign: 'ESLS' },
              RESET: { members: z.resetSource ? [z.resetSource] : [], status: f.Reset, assign: null },
            };
            const info = map[role];
            const has = (info.members || []).filter(Boolean).length > 0;
            const st = has ? (info.status || 'READY') : 'UNRESOLVED';
            return `<div class="rounded-lg border border-slate-800 bg-[#0c1219] px-2.5 py-2">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-slate-200">${role}</span>
                <span class="ml-auto">${badge(st)}</span>
              </div>
              <div class="mono text-[10px] text-slate-400 mt-1 break-all">${has ? escapeHtml(info.members.join(', ')) : 'none assigned'}</div>
              ${(!has && info.assign) ? `<button type="button" class="sb-role-assign mt-1.5 text-[10px] px-2 py-1 rounded border border-emerald-800/50 text-emerald-300 hover:bg-emerald-950/40" data-sb-role="${info.assign}">Assign ${role}…</button>` : ''}
            </div>`;
          }).join('')}
        </div>
      </div>
      ${(z.hard_missing || []).length ? `<div class="mb-3 text-[11px] text-amber-200/90 border border-amber-900/40 bg-amber-950/20 rounded-lg px-3 py-2">Missing: <span class="mono">${escapeHtml((z.hard_missing || []).join(', '))}</span></div>` : ''}
      <div class="rounded-xl border border-emerald-900/40 bg-[#0c1219] p-4 mb-3">
        <div class="text-[11px] text-slate-400 leading-relaxed">
          Use the <strong class="text-cyan-300">top SITE SAFETY INVENTORY</strong> to select devices,
          then assign them here. Duplicate full-list panels were removed (field request).
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" id="sb-add-selected" class="btn-primary text-[11px] py-2 px-3 rounded-lg bg-emerald-800 hover:bg-emerald-700 border border-emerald-500/40 text-white font-semibold">Assign checked inventory → this zone</button>
          <button type="button" id="sb-accept-suggestions" class="btn-ghost text-[11px] py-2 px-3 rounded-lg border border-sky-900/50 text-sky-300" title="Accept digit-match suggestions (engineer action)">Suggestions</button>
          <input id="sb-device-filter" type="search" placeholder="Filter inventory…" class="bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-[11px] w-48" value="${escapeHtml(state.filter)}">
        </div>
        <div id="sb-available" class="hidden" aria-hidden="true"></div>
      </div>
      <div class="rounded-xl border border-slate-800 bg-[#0c1219] p-4 flex flex-col min-h-[12rem]">
        <div class="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Zone membership</div>
        <div id="sb-assigned" class="flex-1 min-h-[8rem] space-y-1 text-[12px] mono leading-relaxed"></div>
        <button type="button" id="sb-remove-selected" class="mt-3 btn-ghost w-full text-[11px] py-2 rounded-lg border border-rose-900/50 text-rose-300">← Remove from zone</button>
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
    // Filter zone available/assigned lists in place — do not re-render inventory
    // (that destroyed #sb-inv-filter focus mid-typing).
    $('sb-device-filter')?.addEventListener('input', (ev) => {
      const filt = String(ev.target.value || '').trim().toUpperCase();
      state.filter = ev.target.value || '';
      state.inventoryFilter = state.filter;
      const avail = $('sb-available');
      const asgn = $('sb-assigned');
      [avail, asgn].forEach((box) => {
        if (!box) return;
        box.querySelectorAll('label').forEach((lab) => {
          const name = String(
            lab.querySelector('input')?.getAttribute('data-sb-avail')
            || lab.querySelector('input')?.getAttribute('data-sb-assigned')
            || lab.textContent
            || '',
          ).toUpperCase();
          lab.style.display = !filt || name.includes(filt) ? '' : 'none';
        });
      });
      // Mirror filter onto site inventory rows without rebuilding the search input
      const invHost = $('sb-inventory');
      invHost?.querySelectorAll('[data-sb-inv-row]').forEach((row) => {
        const name = String(row.getAttribute('data-sb-inv-row') || '').toUpperCase();
        row.style.display = !filt || name.includes(filt) ? '' : 'none';
      });
    });
    $('sb-add-selected')?.addEventListener('click', () => addSelectedDevices(z));
    $('sb-remove-selected')?.addEventListener('click', () => removeSelectedDevices(z));
    $('sb-accept-suggestions')?.addEventListener('click', () => acceptSuggestions(z));
    $('sb-delete-zone')?.addEventListener('click', () => {
      Promise.resolve(deleteSafetyZone(zoneSourceId(z) || z.name))
        .catch((err) => status(`Delete failed: ${err?.message || err}`));
    });
    $('sb-rename-zone')?.addEventListener('click', () => renameSafetyZone(z));
    host.querySelectorAll('.sb-role-assign').forEach((btn) => {
      btn.addEventListener('click', () => {
        const role = btn.getAttribute('data-sb-role') || '';
        state.filter = '';
        state.inventoryFilter = '';
        // Pre-filter eligible devices by required role kind
        const avail = $('sb-available');
        if (avail) {
          avail.querySelectorAll('label').forEach((lab) => {
            const name = lab.querySelector('input')?.getAttribute('data-sb-avail') || '';
            const kind = classifyDevName(name);
            const show = !role || kind === role || (role === 'ESTOP' && kind === 'ESTOP');
            lab.classList.toggle('hidden', !show);
            if (show && kind === role) {
              const cb = lab.querySelector('input[type="checkbox"]');
              if (cb) cb.checked = false;
            }
          });
        }
        status(`Select ${role} device(s) below, then Assign Selected → ${zoneDisplayName(z)}`);
        $('sb-add-selected')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    });
  }

  /**
   * Gate I — rename engineering_name only. source_id stays immutable.
   * Does not duplicate the zone, drop members, or break reload/provenance.
   */
  async function renameSafetyZone(z) {
    const sid = zoneSourceId(z);
    const cur = zoneDisplayName(z);
    // Electron: Site Forge modal (window.prompt unsupported)
    const next = await sbAskText(
      'Rename Safety Zone',
      `Rename engineering name\n\n`
      + `Source identity (immutable): ${sid}\n`
      + `Logix rules: letter/_ start, letters/digits/_ only, max 80.`,
      cur,
    );
    if (next == null) return;
    const eng = String(next || '').trim();
    if (!eng || eng === cur) return;
    const v = validateLogixIdent(eng);
    if (!v.ok) {
      status(v.error);
      await sbShowInfo('Invalid name', v.error);
      return;
    }
    // Collision: another zone already uses this engineering_name
    const clash = (state.model?.zones || []).find((oz) =>
      zoneSourceId(oz) !== sid
      && zoneDisplayName(oz).toLowerCase() === eng.toLowerCase()
    );
    if (clash) {
      status(`Name “${eng}” already used by another zone — cancelled`);
      await sbShowInfo('Name in use', `“${eng}” already used by another zone — rename cancelled.`);
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

  /**
   * Shared Safety device relationships — one canonical device, many zone/area uses.
   * Returns [{zone, area, confidence}] excluding the current zone.
   */
  function secondaryUsagesForDevice(devName, currentZone) {
    const want = String(devName || '').trim().toUpperCase();
    const cur = String(currentZone?.name || currentZone || '').trim().toUpperCase();
    if (!want || !state.model) return [];
    const out = [];
    const seen = new Set();
    (state.model.zones || []).forEach((z) => {
      const zn = String(z.name || z.engineering_name || '').trim();
      const zu = zn.toUpperCase();
      if (!zn || zu === cur || isDefaultSafetyName(zn)) return;
      const members = (z.members || []).map((m) => String(m).toUpperCase());
      if (!members.includes(want)) return;
      const key = zu;
      if (seen.has(key)) return;
      seen.add(key);
      const area = String(z.areaRef || z.area || '').trim();
      const conf = String(
        z.membersOrigin || z.provenance || z.origin || 'UNKNOWN',
      ).toUpperCase() || 'UNKNOWN';
      out.push({ zone: zn, area, confidence: conf });
    });
    return out;
  }

  function groupedDeviceHtml(devices, { suggested, checkboxAttr, showSecondary, precheck, currentZone }) {
    const byKind = {};
    KIND_ORDER.forEach((k) => { byKind[k] = []; });
    (devices || []).forEach((d) => {
      const k = KIND_ORDER.includes(d.kind) ? d.kind : 'OTHER';
      byKind[k].push(d);
    });
    const pre = precheck instanceof Set ? precheck : null;
    let html = '';
    KIND_ORDER.forEach((k) => {
      const rows = byKind[k] || [];
      if (!rows.length) return;
      html += `<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold mt-1.5 mb-0.5">${KIND_LABEL[k] || k}</div>`;
      html += rows.map((d) => {
        const sug = suggested && suggested.has(String(d.name).toUpperCase());
        const refs = d.safetyZoneRefs || [];
        const chipZone = refs.length > 1 ? `${refs.length} zones` : (refs[0] || d.safetyZoneRef);
        const chip = statusChip(d.status, chipZone);
        let secondaryHtml = '';
        if (showSecondary) {
          secondaryHtml = formatMembershipHint(d.name, { context: 'zone' });
          const secs = secondaryUsagesForDevice(d.name, currentZone || selectedZone());
          if (secs.length && !secondaryHtml.includes('Also in')) {
            const bits = secs.map((s) => {
              const loc = s.area ? `${s.area} / ${s.zone}` : s.zone;
              return `${escapeHtml(loc)}${s.confidence ? ` · ${escapeHtml(s.confidence)}` : ''}`;
            });
            secondaryHtml += `<div class="text-[8px] text-amber-500/90 pl-6">Also in: ${bits.join(', ')}</div>`;
          }
        } else {
          // Available list: still show where else the device already lives
          const elsewhere = zonesForDevice(d.name)
            .filter((x) => {
              const cur = zoneDisplayName(currentZone || selectedZone() || {});
              return x.zone.toUpperCase() !== String(cur || '').toUpperCase();
            });
          if (elsewhere.length) {
            secondaryHtml = `<div class="text-[8px] text-slate-500 pl-6">Also in: ${
              elsewhere.map((s) => escapeHtml(s.zone)).join(', ')
            }</div>`;
          } else if (!(d.safetyZoneRefs || []).length && d.status === 'UNASSIGNED') {
            secondaryHtml = '<div class="text-[8px] text-amber-300/80 pl-6">Unassigned</div>';
          }
        }
        const checked = pre && pre.has(String(d.name).toUpperCase());
        return `<div class="rounded hover:bg-slate-900/80">
          <label class="flex items-center gap-2 px-1.5 py-0.5 cursor-pointer ${sug ? 'bg-sky-950/30' : ''}">
          <input type="checkbox" ${checkboxAttr}="${escapeHtml(d.name)}" class="rounded border-slate-600"${checked ? ' checked' : ''}>
          <span class="${sug ? 'text-sky-300' : 'text-slate-300'}">${escapeHtml(d.name)}</span>
          <span class="ml-auto flex items-center gap-1">${chip}${sug ? '<span class="text-[8px] text-sky-400">SUGGESTED</span>' : ''}</span>
        </label>${secondaryHtml}</div>`;
      }).join('');
    });
    return html;
  }

  function isAssignableToZoneDevice(d, zone) {
    /**
     * Many-to-many: any canonical device may be added to this zone unless it is
     * already a member here. Devices assigned elsewhere remain selectable.
     */
    if (!d || !d.name) return false;
    if (isDefaultSafetyZone(zone)) return false;
    const assigned = new Set((zone.members || []).map((m) => String(m).toUpperCase()));
    if (assigned.has(String(d.name).toUpperCase())) return false;
    return true;
  }

  function renderDeviceLists(z) {
    const availHost = $('sb-available');
    const asgnHost = $('sb-assigned');
    if (!availHost || !asgnHost || !state.model) return;
    const assigned = new Set((z.members || []).map((m) => String(m).toUpperCase()));
    const filt = String(state.filter || '').trim().toUpperCase();
    // AVAILABLE = devices not yet in THIS zone (including assigned elsewhere).
    // Default Safety is NOT an operational zone — its members remain assignable.
    // DEVICE INVENTORY (left rail) remains the full ledger including assigned.
    const avail = (state.model.devices || [])
      .filter((d) => d && d.name && isAssignableToZoneDevice(d, z))
      .filter((d) => !filt || String(d.name).toUpperCase().includes(filt)
        || String(d.kind || '').toUpperCase().includes(filt)
        || String(d.safetyZoneRef || '').toUpperCase().includes(filt)
        || (d.safetyZoneRefs || []).some((r) => String(r).toUpperCase().includes(filt)));
    const suggested = new Set((z.suggestions || []).map((s) => String(s.name).toUpperCase()));
    availHost.innerHTML = groupedDeviceHtml(avail, {
      suggested,
      checkboxAttr: 'data-sb-avail',
      currentZone: z,
    })
      || '<div class="text-slate-600 p-2">No available devices</div>';

    const asgnDevices = (z.members || []).map((m) => {
      const found = (state.model.devices || []).find((d) => String(d.name).toUpperCase() === String(m).toUpperCase());
      return found || {
        name: m,
        kind: classifyDevName(m) || 'OTHER',
        status: 'ENGINEER_ASSIGNED',
        safetyZoneRef: z.name,
        safetyZoneRefs: [z.name],
        assignedZone: z.name,
      };
    }).map((d) => ({ ...d, assignedZone: z.name }));
    asgnHost.innerHTML = groupedDeviceHtml(asgnDevices, {
      suggested: null,
      checkboxAttr: 'data-sb-asgn',
      showSecondary: true,
      precheck: assigned,
      currentZone: z,
    })
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
      memberMeta: z.memberMeta && typeof z.memberMeta === 'object' ? { ...z.memberMeta } : {},
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
    // Project-scoped engineer durability only — never persist transient RUN shells.
    const zones = (state.model?.zones || [])
      .filter((z) => isDefaultSafetyZone(z) || isPersistedEngineerZone(z))
      .map(serializeZone)
      .filter(Boolean);
    const devices = (state.model?.devices || []).map(serializeDevice).filter(Boolean);
    const identity = activeSiteIdentity();
    AS.safety_build = {
      version: 1,
      source: 'safety_build',
      zones,
      devices: [], // devices always from current RUN evidence union
      unassignedDevices: state.model?.unassignedDevices || [],
      inventory: state.model?.inventory || {},
      counts: state.model?.counts || {},
      deletedZones: [...state.deletedZones],
      draft: true,
      dirty: state.dirty,
      archive_sha: identity.archive_sha || '',
      machine: identity.machine || '',
      projectIdentity: {
        archive_sha: identity.archive_sha || '',
        machine: identity.machine || '',
      },
    };
    try {
      const scopedKey = safetyDraftStorageKey({
        archive_sha: AS.safety_build.archive_sha
          || AS.safety_build.projectIdentity?.archive_sha
          || activeSiteIdentity().archive_sha,
        machine: AS.safety_build.machine
          || AS.safety_build.projectIdentity?.machine
          || activeSiteIdentity().machine,
      });
      const persistPayload = { ...AS.safety_build, devices: [] };
      if (scopedKey) localStorage.setItem(scopedKey, JSON.stringify(persistPayload));
      try { localStorage.removeItem('siteforge.safetyBuild.v1'); } catch (_) { /* ignore */ }
    } catch (_) { /* ignore */ }
  }

  /** Clear zone off Transportation conveyors + tb.safetyZones registry (by source_id or eng name). */
  function clearZoneFromTransport(zoneRef) {
    const zref = String(zoneRef || '').trim();
    if (!zref) return;
    try {
      if (typeof window.transportDeleteSafetyZone === 'function') {
        window.transportDeleteSafetyZone(zref);
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
      const lower = zref.toLowerCase();
      const matchZ = (z) => {
        const sid = String(z.source_id || z.id || '').trim().toLowerCase();
        const eng = String(z.engineering_name || z.name || '').trim().toLowerCase();
        return sid === lower || eng === lower;
      };
      const doomedEng = new Set(
        (data.safetyZones || [])
          .filter(matchZ)
          .map((z) => String(z.engineering_name || z.name || '').trim().toLowerCase())
          .filter(Boolean),
      );
      if (!doomedEng.size) doomedEng.add(lower);
      (data.areas || []).forEach((area) => {
        (area.nodes || []).forEach((n) => {
          const zn = String(n.safetyZone || '').trim().toLowerCase();
          if (doomedEng.has(zn) || zn === lower) n.safetyZone = '';
        });
      });
      data.safetyZones = (data.safetyZones || []).filter((z) => !matchZ(z));
      localStorage.setItem(key, JSON.stringify(data));
    } catch (_) { /* ignore */ }
  }

  /**
   * Gate E — delete tombstones immutable source_id in deletedZones.
   * Also tombstones any RUN twin that shares the same display name so restart
   * cannot resurrect a deleted engineer zone as Trash_ESZone1 — RUN.
   * engineering_name remains reusable after delete (new source_id).
   */
  async function deleteSafetyZone(zoneNameOrId) {
    const key = String(zoneNameOrId || '').trim();
    if (!key) return false;
    if (isDefaultSafetyName(key)) {
      status('Default/Unassigned Safety cannot be deleted — it is the ownership bucket');
      return false;
    }
    const live = (state.model?.zones || []).find((z) =>
      zoneSourceId(z) === key
      || zoneDisplayName(z) === key
      || String(z.name || '').trim() === key
    );
    const sid = zoneSourceId(live) || String(live?.source_id || live?.id || '').trim() || key;
    const disp = zoneDisplayName(live) || key;
    if (isDefaultSafetyName(sid) || isDefaultSafetyZone(live)) {
      status('Default/Unassigned Safety cannot be deleted — it is the ownership bucket');
      return false;
    }
    const ok = await sbAskYesNo(
      'Delete Safety Zone',
      `Delete Safety Zone "${disp}"?\n\n`
      + '• Removes it from Safety Build\n'
      + '• Clears this zone off conveyors on Transportation\n'
      + '• Assigned devices return to Default / Unassigned Safety\n'
      + `• Tombstones source_id ${sid} (name “${disp}” may be reused)\n\n`
      + 'This does not delete physical devices — only the zone membership.',
    );
    if (!ok) return false;

    // Collect all source_ids that share this display name (engineer + RUN twins)
    const tombstoneIds = new Set([sid]);
    const dispLower = disp.toLowerCase();
    (state.model?.zones || []).forEach((z) => {
      if (zoneDisplayName(z).toLowerCase() === dispLower) {
        const zs = zoneSourceId(z);
        if (zs) tombstoneIds.add(zs);
      }
    });
    // Also tombstone current-session RUN shells with same display name
    const AS = ensureAutogenState();
    (AS.runSafetyZones || []).forEach((z) => {
      const dn = String(z.engineering_name || z.name || '').trim().toLowerCase();
      if (dn === dispLower) {
        const zs = zoneSourceId(z) || String(z.name || '').trim();
        if (zs) tombstoneIds.add(zs);
      }
    });
    tombstoneIds.forEach((id) => state.deletedZones.add(id));

    clearZoneFromTransport(sid);
    if (disp && disp !== sid) clearZoneFromTransport(disp);

    const dropZone = (z) => {
      const zs = zoneSourceId(z);
      const dn = zoneDisplayName(z);
      if (tombstoneIds.has(zs)) return false;
      if (dn && dn.toLowerCase() === dispLower) return false;
      return true;
    };
    if (AS.safety_build && Array.isArray(AS.safety_build.zones)) {
      AS.safety_build.zones = AS.safety_build.zones.filter(dropZone);
      AS.safety_build.deletedZones = [...state.deletedZones];
    }
    if (AS.workbook?.safety_build && Array.isArray(AS.workbook.safety_build.zones)) {
      AS.workbook.safety_build.zones = AS.workbook.safety_build.zones.filter(dropZone);
      AS.workbook.safety_build.deletedZones = [...state.deletedZones];
    }
    // Drop from session RUN cache so rebuild cannot resurrect
    AS.runSafetyZones = (AS.runSafetyZones || []).filter((z) => {
      const zs = zoneSourceId(z) || String(z.name || '').trim();
      const dn = String(z.engineering_name || z.name || '').trim();
      if (tombstoneIds.has(zs)) return false;
      if (dn && dn.toLowerCase() === dispLower) return false;
      return true;
    });

    if (
      state.selectedZoneId === sid
      || state.selectedZoneId === disp
      || state.selectedZoneId === key
      || tombstoneIds.has(String(state.selectedZoneId || ''))
    ) {
      state.selectedZoneId = null;
    }
    state.dirty = true;
    state.model = buildClientModel();
    if (!state.selectedZoneId && (state.model.zones || []).length) {
      state.selectedZoneId = zoneSourceId(state.model.zones[0]) || state.model.zones[0].name;
    }
    persistLocalDraft();
    // Also stamp deletedZones onto workbook so Apply/persist survives restart
    try {
      if (AS.workbook) {
        if (!AS.workbook.safety_build) AS.workbook.safety_build = { zones: [] };
        AS.workbook.safety_build.deletedZones = [...state.deletedZones];
        AS.workbook.safety_build.zones = (AS.workbook.safety_build.zones || []).filter(dropZone);
      }
    } catch (_) { /* ignore */ }
    render();
    syncReadiness();
    status(`Deleted Safety Zone ${disp} (${tombstoneIds.size} source_id(s) tombstoned)`);
    return true;
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
    // Many-to-many ADD — does not remove from other zones.
    mutateZone(live, (zz) => {
      const set = new Set(zz.members || []);
      names.forEach((n) => set.add(n));
      zz.members = [...set];
      ensureMemberMeta(zz, names, 'ENGINEER_ASSIGNED');
    });
  }

  function removeSelectedDevices(z) {
    const names = new Set([...document.querySelectorAll('#sb-assigned [data-sb-asgn]:checked')]
      .map((el) => el.getAttribute('data-sb-asgn')));
    if (!names.size) return;
    const live = findLiveZone(z);
    if (!live) return;
    // Remove only THIS zone's membership relationship — other zones keep the device.
    mutateZone(live, (zz) => {
      zz.members = (zz.members || []).filter((m) => !names.has(String(m).toUpperCase()));
      dropMemberMeta(zz, [...names]);
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
      ensureMemberMeta(zz, sug, 'ENGINEER_ASSIGNED');
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
    // Prefer partition physical counts when inventory has been rendered — never
    // show raw-signal totals as if they were assignable physical devices.
    const part = state.safetyInventoryPartition;
    const physN = part && typeof part.canonical_physical === 'number'
      ? part.canonical_physical
      : null;
    const assignable = part?.assignable || [];
    const physUnassigned = physN != null
      ? assignable.filter((d) => {
        const st = String(d.status || '').toUpperCase();
        return st === 'UNASSIGNED' || st === 'GROUPED' || !st || d.defaultSafety === true;
      }).length
      : null;
    const physEng = physN != null
      ? assignable.filter((d) => {
        const st = String(d.status || '').toUpperCase();
        return st === 'ENGINEER_ASSIGNED' || st === 'SHARED';
      }).length
      : null;
    const physAuto = physN != null
      ? assignable.filter((d) => String(d.status || '').toUpperCase() === 'AUTO_RESOLVED').length
      : null;
    // Gate 7 — site devices, Default/Unassigned, engineer zones, assigned, E-stop, review
    set('sb-count-zones', c.engineer_zones != null ? c.engineer_zones : c.zones);
    set('sb-count-ready', c.ready);
    set('sb-count-review', c.review_required);
    // E-stop count from physical assignable when available
    const estopPhys = physN != null
      ? assignable.filter((d) => String(d.kind || '').toUpperCase() === 'ESTOP').length
      : c.estops;
    set('sb-count-estops', estopPhys);
    const unassigned = physUnassigned != null
      ? physUnassigned
      : (c.default_safety != null
        ? c.default_safety
        : (c.unassigned != null ? c.unassigned : c.unassigned_estops));
    set('sb-count-unassigned', unassigned);
    set('sb-count-default', unassigned);
    // FOUND label in HTML historically meant site devices — prefer physical canonical
    set('sb-count-found', physN != null
      ? physN
      : (c.site_devices != null ? c.site_devices : (c.devices_found != null ? c.devices_found : c.devices)));
    set('sb-count-assigned', physN != null
      ? Math.max(0, physN - (physUnassigned || 0))
      : (c.assigned != null ? c.assigned : (
        Math.max(0, (c.devices_found || c.devices || 0) - (unassigned || 0))
      )));
    set('sb-count-auto', physAuto != null ? physAuto : c.automatically_resolved);
    set('sb-count-eng', physEng != null ? physEng : c.engineer_assigned);
    const pct = c.completion_pct;
    const cons = c.conservation_ok === false ? ' · CONSERVATION FAIL' : '';
    set('sb-count-completion', pct == null ? '—' : `${pct}%${cons}`);
  }

  function render() {
    renderZoneSummary();
    renderInventory(); // builds safetyInventoryPartition used by renderCounts
    renderCounts();
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
    if (!hasActiveSiteSession()) {
      e.detected = false;
      e.status = 'NOT_DETECTED';
      e.detail = 'NO ACTIVE RUN';
      e.unresolved = 0;
      e.diagnostics = ['NO_ACTIVE_RUN'];
      return;
    }
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
    const applyBtn = $('sb-apply');
    const fb = window.sfActionFeedback;
    fb?.begin(applyBtn, 'APPLYING…');
    persistLocalDraft();
    const AS = ensureAutogenState();
    // Snapshot engineer members BEFORE rebuild — buildClientModel must not erase Apply.
    const memberSnap = new Map();
    (state.model?.zones || []).forEach((z) => {
      const sid = zoneSourceId(z);
      if (!sid || isDefaultSafetyZone(z)) return;
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
      if (members.length || z.engineerEdited) {
        memberSnap.set(sid, {
          members,
          memberMeta: z.memberMeta && typeof z.memberMeta === 'object' ? { ...z.memberMeta } : {},
          membersOrigin: z.membersOrigin || 'ENGINEER_ASSIGNED',
          engineerEdited: !!z.engineerEdited || members.length > 0,
          name: zoneDisplayName(z),
          areaRef: z.areaRef || '',
          conveyorRefs: z.conveyorRefs || [],
          eStops: z.eStops || [],
          esrDevices: z.esrDevices || [],
          mcrDevices: z.mcrDevices || [],
          csDevices: z.csDevices || [],
          eslsDevices: z.eslsDevices || [],
          resetSource: z.resetSource || '',
          silenceSource: z.silenceSource || '',
          provenance: z.provenance,
          origin: z.origin,
          createdBy: z.createdBy,
          runDiscovered: z.runDiscovered,
          membership_confidence: z.membership_confidence,
          status: z.status,
          fields: z.fields || {},
        });
      }
    });
    // Also keep draft/AS members if live model was already hollowed
    const draftZones = [
      ...((AS.safety_build && AS.safety_build.zones) || []),
    ];
    draftZones.forEach((z) => {
      const sid = String(z.source_id || z.id || z.name || '');
      if (!sid || memberSnap.has(sid)) return;
      const members = Array.isArray(z.members) ? z.members.filter(Boolean) : [];
      if (!members.length) return;
      memberSnap.set(sid, {
        members,
        memberMeta: z.memberMeta && typeof z.memberMeta === 'object' ? { ...z.memberMeta } : {},
        membersOrigin: z.membersOrigin || 'ENGINEER_ASSIGNED',
        engineerEdited: true,
        name: z.name || sid,
        areaRef: z.areaRef || z.area || '',
        conveyorRefs: z.conveyorRefs || z.conveyors || [],
        eStops: z.eStops || [],
        esrDevices: z.esrDevices || [],
        mcrDevices: z.mcrDevices || [],
        csDevices: z.csDevices || [],
        eslsDevices: z.eslsDevices || [],
        resetSource: z.resetSource || z.reset_source || '',
        silenceSource: z.silenceSource || z.silence_source || '',
        provenance: z.provenance,
        origin: z.origin,
        createdBy: z.createdBy || 'engineer',
        runDiscovered: z.runDiscovered,
        membership_confidence: z.membership_confidence,
        status: z.status,
        fields: z.fields || {},
      });
    });

    // Rebuild so devices carry stamped safetyZoneRefs/status before persist
    state.model = buildClientModel();
    // Restore snapped members if rebuild dropped them
    (state.model?.zones || []).forEach((z) => {
      const sid = zoneSourceId(z);
      const snap = memberSnap.get(sid);
      if (!snap) return;
      if (!(z.members || []).length && snap.members.length) {
        z.members = [...snap.members];
        z.membersOrigin = snap.membersOrigin;
        z.engineerEdited = true;
        splitZoneMembers(z);
      }
      if (snap.memberMeta && Object.keys(snap.memberMeta).length) {
        z.memberMeta = { ...(z.memberMeta || {}), ...snap.memberMeta };
      }
    });

    // Apply = reconcile/update by zone identity. Never emit coercion artifacts.
    // Gate 3 — Default/Unassigned Safety is ownership-only; never persist as ES zone.
    // Never persist Area-derived AUTO_DEFAULT / false-RUN empty shells (they rehydrate
    // as ORNCCP2_ESZone1 — RUN after restart).
    const appliedZones = (state.model?.zones || [])
      .filter((z) => z && zoneSourceId(z) && !isCorruptZoneName(zoneSourceId(z)) && !isDefaultSafetyZone(z))
      .filter((z) => {
        const prov = z.provenance || classifyZoneProvenance(z, {});
        if (prov === PROVENANCE.AUTO_DEFAULT) return false;
        const sid = zoneSourceId(z);
        const disp = zoneDisplayName(z);
        const area = areaNameOf(z.areaRef || z.area) || '';
        const stem = String(sid || disp).replace(/_ESZone\d*$/i, '');
        const areaStem = String(area || '').replace(/_Area$/i, '');
        const areaDerived = !!(stem && areaStem && stem.toLowerCase() === areaStem.toLowerCase()
          && /_ESZone1$/i.test(sid || disp)
          && !(z.members || []).length
          && !z.engineerEdited && z.createdBy !== 'engineer');
        if (areaDerived) return false;
        if (z.runDiscovered && !(z.members || []).length && !z.engineerEdited
          && prov !== PROVENANCE.ENGINEER_CREATED) {
          // Hollow false-RUN without engineer authorship — drop from persist
          return false;
        }
        return true;
      })
      .map((z) => {
        const areaRef = areaNameOf(z.areaRef) || '';
        const sid = zoneSourceId(z);
        const eng = zoneDisplayName(z);
        const snap = memberSnap.get(sid);
        const members = [];
        const seenM = new Set();
        const srcMembers = (z.members && z.members.length)
          ? z.members
          : (snap?.members || []);
        srcMembers.forEach((m) => {
          const nm = String(m || '').trim();
          if (!nm) return;
          const key = nm.toUpperCase();
          if (seenM.has(key)) return;
          seenM.add(key);
          members.push(nm);
        });
        if (members.length) splitZoneMembers({ ...z, members });
        return {
          id: sid,
          source_id: sid,
          name: eng,
          engineering_name: eng,
          area: areaRef || snap?.areaRef || '',
          areaRef: areaRef || snap?.areaRef || '',
          conveyors: z.conveyorRefs || snap?.conveyorRefs || [],
          conveyorRefs: z.conveyorRefs || snap?.conveyorRefs || [],
          members,
          eStops: z.eStops || members.filter((m) => classifyDevName(m) === 'ESTOP'),
          esrDevices: z.esrDevices || members.filter((m) => classifyDevName(m) === 'ESR'),
          mcrDevices: z.mcrDevices || members.filter((m) => classifyDevName(m) === 'MCR'),
          csDevices: z.csDevices || members.filter((m) => classifyDevName(m) === 'CS'),
          eslsDevices: z.eslsDevices || members.filter((m) => classifyDevName(m) === 'ESLS'),
          resetSource: z.resetSource || snap?.resetSource || '',
          silenceSource: z.silenceSource || snap?.silenceSource || '',
          reset_source: z.resetSource || snap?.resetSource || '',
          silence_source: z.silenceSource || snap?.silenceSource || '',
          membersOrigin: members.length
            ? (z.membersOrigin || snap?.membersOrigin || 'ENGINEER_ASSIGNED')
            : (z.runDiscovered ? 'UNRESOLVED' : 'ENGINEER_ASSIGNED'),
          memberMeta: {
            ...((snap?.memberMeta && typeof snap.memberMeta === 'object') ? snap.memberMeta : {}),
            ...((z.memberMeta && typeof z.memberMeta === 'object') ? z.memberMeta : {}),
          },
          membership_confidence: z.membership_confidence || snap?.membership_confidence,
          engineerEdited: !!z.engineerEdited || !!snap?.engineerEdited || members.length > 0,
          createdBy: z.createdBy || snap?.createdBy
            || ((z.engineerEdited || members.length) && !z.runDiscovered ? 'engineer' : undefined),
          runDiscovered: !!z.runDiscovered
            || z.provenance === PROVENANCE.RUN_DISCOVERED
            || z.origin === PROVENANCE.RUN_DISCOVERED,
          provenance: z.provenance
            || snap?.provenance
            || (z.runDiscovered ? PROVENANCE.RUN_DISCOVERED : null)
            || (z.engineerEdited || members.length
              ? PROVENANCE.ENGINEER_CREATED
              : PROVENANCE.UNKNOWN),
          origin: z.origin
            || z.provenance
            || snap?.origin
            || (z.runDiscovered ? PROVENANCE.RUN_DISCOVERED : null)
            || (z.engineerEdited || members.length
              ? PROVENANCE.ENGINEER_CREATED
              : PROVENANCE.UNKNOWN),
          status: z.status || snap?.status,
          fields: z.fields || snap?.fields || {},
        };
      });
    // Ensure snapped zones survive even if rebuild dropped the zone row
    memberSnap.forEach((snap, sid) => {
      if (appliedZones.some((z) => z.source_id === sid || z.id === sid)) return;
      if (isDefaultSafetyName(sid) || isCorruptZoneName(sid)) return;
      const members = snap.members || [];
      appliedZones.push({
        id: sid,
        source_id: sid,
        name: snap.name || sid,
        engineering_name: snap.name || sid,
        area: snap.areaRef || '',
        areaRef: snap.areaRef || '',
        conveyors: snap.conveyorRefs || [],
        conveyorRefs: snap.conveyorRefs || [],
        members,
        eStops: members.filter((m) => classifyDevName(m) === 'ESTOP'),
        esrDevices: members.filter((m) => classifyDevName(m) === 'ESR'),
        mcrDevices: members.filter((m) => classifyDevName(m) === 'MCR'),
        csDevices: members.filter((m) => classifyDevName(m) === 'CS'),
        eslsDevices: members.filter((m) => classifyDevName(m) === 'ESLS'),
        resetSource: snap.resetSource || '',
        silenceSource: snap.silenceSource || '',
        reset_source: snap.resetSource || '',
        silence_source: snap.silenceSource || '',
        membersOrigin: 'ENGINEER_ASSIGNED',
        engineerEdited: true,
        createdBy: 'engineer',
        provenance: PROVENANCE.ENGINEER_CREATED,
        origin: PROVENANCE.ENGINEER_CREATED,
        status: snap.status,
        fields: snap.fields || {},
      });
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
          const reason = res.message || res.error || 'unknown';
          status(`Apply failed: ${reason}`);
          fb?.fail(applyBtn, reason);
          return;
        }
      } else if (typeof window.saveAutogenWorkbook === 'function') {
        await window.saveAutogenWorkbook();
      }
    } catch (err) {
      status(`Apply error: ${err?.message || err}`);
      fb?.fail(applyBtn, err?.message || String(err));
      return;
    }

    // Verify persistence: reload disk and confirm member counts match Apply payload.
    let verifiedMembers = 0;
    let verifyOk = true;
    let verifyDetail = '';
    try {
      if (typeof A.autogenWorkbookLoad === 'function') {
        const full = await A.autogenWorkbookLoad();
        const diskSb = full?.workbook?.safety_build;
        const want = (payload.zones || []).reduce((n, z) => n + ((z.members || []).length), 0);
        const got = (diskSb?.zones || []).reduce((n, z) => n + ((z.members || []).length), 0);
        verifiedMembers = got;
        if (want > 0 && got < want) {
          verifyOk = false;
          verifyDetail = `disk members=${got} expected=${want}`;
        }
        if (want > 0 && (!diskSb?.appliedAt || diskSb?.source === 'transport_engineer')) {
          verifyOk = false;
          verifyDetail = (verifyDetail ? `${verifyDetail}; ` : '')
            + `source=${diskSb?.source || 'missing'} appliedAt=${diskSb?.appliedAt || 'missing'}`;
        }
      }
    } catch (err) {
      verifyOk = false;
      verifyDetail = err?.message || String(err);
    }

    if (!verifyOk) {
      status(
        `Apply Safety FAILED persistence check — ${verifyDetail}. `
        + 'BUILD/SAFETY BLOCKED until members are on disk. Do not Build PLC yet.',
      );
      fb?.fail(applyBtn, verifyDetail || 'persistence check failed');
      state.dirty = true;
      render();
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
    const roleCounts = { ESTOP: 0, ESLS: 0, ESR: 0, MCR: 0, CS: 0, OTHER: 0 };
    (payload.zones || []).forEach((z) => {
      (z.members || []).forEach((m) => {
        const k = classifyDevName(m) || 'OTHER';
        roleCounts[k] = (roleCounts[k] || 0) + 1;
      });
    });
    const zoneLines = (payload.zones || [])
      .filter((z) => (z.members || []).length)
      .map((z) => {
        const unresolvedRoles = [];
        if (!(z.eStops || []).length) unresolvedRoles.push('E-STOPS');
        // ESR/MCR/CS/ESLS are required when zone has conveyors — report honestly
        const req = ['ESR', 'MCR', 'CS', 'ESLS'];
        const have = {
          ESR: (z.esrDevices || []).length,
          MCR: (z.mcrDevices || []).length,
          CS: (z.csDevices || []).length,
          ESLS: (z.eslsDevices || []).length,
        };
        req.forEach((r) => { if (!have[r]) unresolvedRoles.push(r); });
        return `Zone: ${z.name} · Members persisted: ${(z.members || []).length}`
          + ` · E-Stops: ${(z.eStops || []).length}`
          + ` · ESLS: ${(z.eslsDevices || []).length}`
          + ` · ESR: ${(z.esrDevices || []).length || 'none assigned'}`
          + ` · MCR: ${(z.mcrDevices || []).length || 'none assigned'}`
          + ` · CS: ${(z.csDevices || []).length || 'none assigned'}`
          + (unresolvedRoles.length
            ? ` · unresolved required roles: ${unresolvedRoles.join(', ')}`
            : '');
      });
    const okMsg = `SAFETY APPLIED ✓ (verified on disk)\n`
      + `${zoneLines.join('\n') || 'No zones with members'}\n`
      + `Total members persisted: ${verifiedMembers}`
      + ` · E-STOPS ${roleCounts.ESTOP} · ESLS ${roleCounts.ESLS}`
      + ` · ESR ${roleCounts.ESR} · MCR ${roleCounts.MCR} · CS ${roleCounts.CS}`;
    status(okMsg);
    // Stay on Safety — PLC Autogen is reached via tab nav (compile destination).
    fb?.success(
      applyBtn,
      'APPLIED ✓ Safety',
      `Members ${verifiedMembers} · ESR ${roleCounts.ESR} · MCR ${roleCounts.MCR}`,
    );
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
    // HARD LAW: never hydrate Safety devices from unscoped localStorage without
    // a matching active site (archive_sha + machine). Ghost inventory bug:
    // siteforge.safetyBuild.v1 restored 58 devices with NO RUN loaded.
    try {
      const AS = ensureAutogenState();
      const active = activeSiteIdentity();
      const scopedKey = safetyDraftStorageKey(active);
      let draft = null;
      if (hasActiveSiteSession() && scopedKey) {
        const scopedRaw = localStorage.getItem(scopedKey);
        if (scopedRaw) draft = JSON.parse(scopedRaw);
      }
      // Legacy unscoped key: only accept if identity matches active site; never
      // restore devices when there is no active RUN.
      if (!draft) {
        const legacy = localStorage.getItem('siteforge.safetyBuild.v1');
        if (legacy) {
          const parsed = JSON.parse(legacy);
          const draftSha = String(
            parsed?.projectIdentity?.archive_sha
            || parsed?.archive_sha
            || parsed?.projectIdentity?.run_fingerprint
            || '',
          ).trim();
          const draftMachine = String(
            parsed?.projectIdentity?.machine || parsed?.machine || '',
          ).trim();
          if (
            hasActiveSiteSession()
            && draftMachine
            && draftMachine === String(active.machine || '').trim()
            && (!draftSha || draftSha === String(active.archive_sha || '').trim())
          ) {
            draft = parsed;
          } else {
            // Stale / unscoped — remove so it cannot ghost-hydrate later
            try { localStorage.removeItem('siteforge.safetyBuild.v1'); } catch (_) { /* ignore */ }
          }
        }
      }
      if (draft && hasActiveSiteSession()) {
        // Engineer zones only — strip persisted RUN_DISCOVERED shells (stale across restart).
        const engZones = (draft.zones || []).filter((z) =>
          isDefaultSafetyZone(z) || isPersistedEngineerZone(z)
        );
        const zonesOnly = {
          ...draft,
          zones: engZones,
          devices: [],
          unassignedDevices: [],
          inventory: {},
          counts: {},
          deletedZones: draft.deletedZones || [],
        };
        AS.safety_build = zonesOnly;
        AS.safetyDevices = [];
        AS.safetyDevicesGrouped = [];
        AS.runSafetyZones = []; // rebuild from current RUN only
        state.deletedZones = new Set(
          (draft.deletedZones || []).map((n) => String(n || '').trim()).filter(Boolean),
        );
      } else {
        AS.safety_build = {
          version: 1,
          source: 'no_active_run',
          zones: [],
          devices: [],
          unassignedDevices: [],
          inventory: {},
          counts: {},
          deletedZones: [],
        };
        AS.safetyDevices = [];
        AS.safetyDevicesGrouped = [];
        AS.safetyEvidenceUnion = null;
        AS.safetyEvidenceComplete = false;
        state.deletedZones = new Set();
        state.model = emptySafetyShell('NO_ACTIVE_RUN');
      }
    } catch (_) { /* ignore */ }
    try { render(); } catch (_) { /* ignore */ }
  }

  window.safetyBuildRefresh = () => refreshModel();
  window.safetyBuildGetModel = () => state.model;
  window.safetyBuildApply = () => applySafety();

  /**
   * Canonical engineer-zone handoff from Transportation (or any creator).
   * Gate E — source_id is immutable (szone_*); engineering_name is Logix/display.
   * Zone existence is immediate — members may be empty; status REVIEW_REQUIRED.
   * deletedZones tombstones source_id only — a new zone may reuse a deleted name.
   */
  window.safetyBuildUpsertZone = function safetyBuildUpsertZone(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const engName = String(raw.engineering_name || raw.name || '').trim();
    // Prefer immutable source_id / id — never key tombstones on engineering_name
    let sid = String(raw.source_id || raw.id || '').trim();
    if (!sid || sid === engName || isDefaultSafetyName(sid)) {
      // Allocate szone_* when caller still passes name-as-id (legacy / migration)
      sid = `szone_${Math.random().toString(36).slice(2, 11)}`;
    }
    if (!engName || isCorruptZoneName(engName) || isDefaultSafetyName(engName)) return null;
    if (isCorruptZoneName(sid)) return null;
    // Tombstoned source_id must not reappear; a NEW source_id with same eng name is OK
    if (state.deletedZones.has(sid)) return null;
    const areaRef = areaNameOf(raw.areaRef || raw.area) || String(raw.areaRef || raw.area || '').trim();
    const AS = ensureAutogenState();
    if (!AS.safety_build || typeof AS.safety_build !== 'object') {
      AS.safety_build = { version: 1, source: 'engineer_handoff', zones: [], draft: true };
    }
    if (!Array.isArray(AS.safety_build.zones)) AS.safety_build.zones = [];
    const zones = AS.safety_build.zones;
    let z = zones.find((x) => zoneSourceId(x) === sid);
    // Two active zones may not share the same engineering/Logix name
    if (!z) {
      const clash = zones.find((x) => {
        if (state.deletedZones.has(zoneSourceId(x))) return false;
        return zoneDisplayName(x).toLowerCase() === engName.toLowerCase();
      });
      if (clash) {
        // PD-0040 — do not silently move an existing same-name zone to another Area
        const existingArea = String(clash.areaRef || clash.area || '').trim();
        if (
          areaRef
          && existingArea
          && existingArea.toLowerCase() !== areaRef.toLowerCase()
        ) {
          status(
            `Safety Zone “${engName}” already exists under Area “${existingArea}” — not moved to “${areaRef}”`,
          );
          try {
            sbShowInfo(
              'Safety Zone name in use',
              `“${engName}” already belongs to Area “${existingArea}” — not moved.`,
            );
          } catch (_) { /* ignore */ }
          return null;
        }
        // Enrich existing active zone with same eng name (do not fork)
        z = clash;
        sid = zoneSourceId(clash) || sid;
      }
    }
    if (!z) {
      z = {
        id: sid,
        source_id: sid,
        name: engName,
        engineering_name: engName,
        area: areaRef,
        areaRef,
        conveyors: [],
        conveyorRefs: [],
        members: Array.isArray(raw.members) ? [...raw.members] : [],
        eStops: [],
        esrDevices: [],
        mcrDevices: [],
        csDevices: [],
        eslsDevices: [],
        resetSource: areaRef ? `${areaRef}.Reset` : '',
        silenceSource: areaRef ? `${areaRef}.Silence` : '',
        membersOrigin: 'UNRESOLVED',
        engineerEdited: true,
        createdBy: 'engineer',
        provenance: PROVENANCE.ENGINEER_CREATED,
        origin: PROVENANCE.ENGINEER_CREATED,
        operational: true,
        status: 'REVIEW_REQUIRED',
        fields: {},
      };
      zones.push(z);
    } else {
      z.engineering_name = engName || z.engineering_name;
      z.name = z.engineering_name || engName;
      z.source_id = z.source_id || sid;
      z.id = z.source_id;
      if (areaRef && !z.areaRef) {
        z.areaRef = areaRef;
        z.area = areaRef;
      }
      z.createdBy = 'engineer';
      z.provenance = PROVENANCE.ENGINEER_CREATED;
      z.origin = PROVENANCE.ENGINEER_CREATED;
      z.engineerEdited = true;
      z.operational = true;
      if (!z.status) z.status = 'REVIEW_REQUIRED';
      if (!Array.isArray(z.members)) z.members = [];
    }
    // Patch live model if present — key by source_id; display engineering_name
    if (!state.model) state.model = buildClientModel();
    if (state.model) {
      const live = (state.model.zones || []).find(
        (x) => zoneSourceId(x) === zoneSourceId(z),
      );
      if (!live) {
        state.model.zones = state.model.zones || [];
        state.model.zones.push({ ...z });
      } else {
        Object.assign(live, {
          source_id: z.source_id,
          id: z.source_id,
          engineering_name: z.engineering_name,
          name: z.engineering_name,
          createdBy: 'engineer',
          provenance: PROVENANCE.ENGINEER_CREATED,
          origin: PROVENANCE.ENGINEER_CREATED,
          engineerEdited: true,
          operational: true,
          areaRef: live.areaRef || areaRef,
          status: live.status || 'REVIEW_REQUIRED',
        });
      }
      // Ensure Default Safety remains present
      if (!(state.model.zones || []).some((x) => isDefaultSafetyZone(x))) {
        try {
          state.model = buildClientModel();
        } catch (_) { /* ignore */ }
      }
    }
    try { persistLocalDraft(); } catch (_) { /* ignore */ }
    state.dirty = true;
    try { render(); } catch (_) { /* ignore */ }
    try { syncReadiness(); } catch (_) { /* ignore */ }
    return z;
  };

  window.addEventListener('siteforge:safety-zone-created', (ev) => {
    try {
      if (ev?.detail) window.safetyBuildUpsertZone(ev.detail);
    } catch (_) { /* ignore */ }
  });

  /** Wipe in-memory + local draft (called from Clear Current Project / machine change). */
  window.safetyBuildClear = function safetyBuildClear() {
    try { localStorage.removeItem('siteforge.safetyBuild.v1'); } catch (_) { /* ignore */ }
    // Drop any scoped drafts for the session being cleared (best-effort)
    try {
      const sess = activeSiteIdentity();
      const sk = safetyDraftStorageKey(sess);
      if (sk) localStorage.removeItem(sk);
    } catch (_) { /* ignore */ }
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
    AS.safetyDevicesGrouped = [];
    AS.safetyEvidenceUnion = null;
    AS.safetyEvidenceComplete = false;
    AS.runSafetyZones = [];
    if (AS.workbook && AS.workbook.safety_build) {
      AS.workbook.safety_build = {
        ...(AS.workbook.safety_build || {}),
        zones: [],
        devices: [],
        unassignedDevices: [],
        deletedZones: [],
      };
    }
    state.model = emptySafetyShell('CLEARED');
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
    const sess = activeSiteIdentity();
    const mergedIdentity = {
      ...(identity || {}),
      machine: identity?.machine || sess.machine || '',
      archive_sha: identity?.archive_sha || identity?.run_fingerprint || sess.archive_sha || '',
    };
    AS.safety_build.projectIdentity = mergedIdentity;
    AS.safety_build.machine = mergedIdentity.machine || '';
    AS.safety_build.archive_sha = mergedIdentity.archive_sha || '';
    // Persist engineer zones only under site-scoped key — never dump devices into
    // unscoped siteforge.safetyBuild.v1 (that caused ghost inventory with no RUN).
    const scopedKey = safetyDraftStorageKey({
      archive_sha: mergedIdentity.archive_sha,
      machine: mergedIdentity.machine,
    });
    const payload = {
      ...AS.safety_build,
      devices: [], // devices are current-evidence only; not restored from disk
      deletedZones: [...(state.deletedZones || [])],
    };
    try {
      if (scopedKey) localStorage.setItem(scopedKey, JSON.stringify(payload));
      localStorage.removeItem('siteforge.safetyBuild.v1');
    } catch (_) { /* ignore */ }
  };

  window.safetyBuildHasActiveSite = hasActiveSiteSession;
  window.safetyBuildEmptyShell = emptySafetyShell;

  /**
   * ORI-032: Transport Area delete bridge — clear dangling areaRef/area on
   * Safety zones without deleting the zones themselves.
   */
  window.sfClearSafetyAreaRefs = function sfClearSafetyAreaRefs(areaName) {
    const doomed = String(areaName || '').trim();
    if (!doomed) return 0;
    const key = doomed.toUpperCase();
    let cleared = 0;
    const clearZone = (z) => {
      if (!z || typeof z !== 'object') return;
      const ref = String(z.areaRef || z.area || '').trim();
      if (ref && ref.toUpperCase() === key) {
        z.areaRef = '';
        z.area = '';
        cleared += 1;
      }
    };
    (state.model?.zones || []).forEach(clearZone);
    const AS = ensureAutogenState();
    ((AS.safety_build && AS.safety_build.zones) || []).forEach(clearZone);
    ((AS.workbook && AS.workbook.safety_build && AS.workbook.safety_build.zones) || [])
      .forEach(clearZone);
    try { render(); } catch (_) { /* ignore */ }
    return cleared;
  };

  document.addEventListener('DOMContentLoaded', () => {
    bind();
  });

  // Also bind immediately if DOM already ready
  if (document.readyState !== 'loading') bind();
})();
