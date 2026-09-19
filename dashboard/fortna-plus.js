/* Site Forge — dashboard frontend */

const state = {
  recipes: [],
  selectedRecipeId: 'clone-device',
  workspace: null,
  conveyors: [],
  devices: [],
  deviceCategories: {},
  selectedDevice: null,
  busy: false,
};

function $(id) { return document.getElementById(id); }

function log(msg, level = 'info') {
  const el = $('activity-log');
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  const colors = { info: 'text-slate-400', ok: 'text-emerald-400', err: 'text-red-400', warn: 'text-amber-400' };
  const line = document.createElement('div');
  line.className = colors[level] || colors.info;
  line.textContent = `[${ts}] ${msg}`;
  el.prepend(line);
}

function setStatus(elId, text, kind) {
  const el = $(elId);
  if (!el) return;
  el.textContent = text;
  el.className = `status-pill status-${kind}`;
}

function setBusy(busy) {
  state.busy = busy;
  $('btn-apply').disabled = busy || !state.workspace;
  $('btn-reindex').disabled = busy;
  $('btn-browse-archive').disabled = busy;
}

// All main panes — must include every data-tab value or that tab stays blank
// plc + ignition kept in DOM (legacy) but removed from nav
const ALL_TABS = ['search', 'workspace', 'io', 'recipes', 'plc', 'autogen', 'ignition', 'transport', 'safety', 'sorter', 'sawtooth'];

function activateTab(tab) {
  if (!tab) return;
  document.querySelectorAll('.tab-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  ALL_TABS.forEach((t) => {
    const pane = $(`tab-${t}`);
    if (pane) pane.classList.toggle('hidden', t !== tab);
  });
  if (tab === 'recipes') renderRecipeList();
  if (tab === 'io') {
    refreshIoBanks().then(() => {
      if (ioState.ocrResult) mergeOcrPrintParamsIntoDrives(ioState.ocrResult);
    }).catch(() => {});
  }
  if (tab === 'autogen') {
    ensureAutogenWorkbookFromRun({ reason: 'opened PLC Autogen tab' }).catch(() => {});
    refreshAutogenCompileHub();
  }
  if (tab === 'transport' && typeof window.transportBuildRefresh === 'function') {
    window.transportBuildRefresh();
  }
  if (tab === 'safety') {
    try {
      if (typeof window.safetyBuildRefresh === 'function') window.safetyBuildRefresh();
    } catch (_) { /* ignore */ }
  }
  if (tab === 'sorter') {
    try { renderSorterBuild(); } catch (_) { /* ignore */ }
    try { updateSorterSummary(); } catch (_) { /* ignore */ }
  }
  if (tab === 'sawtooth') {
    try { renderSawtoothBuild(); } catch (_) { /* ignore */ }
    try { updateSawtoothSummary(); } catch (_) { /* ignore */ }
  }
}

const READINESS_LABELS = {
  NOT_DETECTED: 'NOT DETECTED',
  REVIEW_REQUIRED: 'DETECTED — REVIEW REQUIRED',
  CHANGED: 'CHANGED SINCE LAST APPLY',
  READY: 'READY FOR AUTOGEN',
  ERROR: 'ERROR / BLOCKED',
};

function emptyReadinessEntry(status = 'NOT_DETECTED') {
  return { status, appliedAt: null, unresolved: 0, detail: '', dirty: false };
}

function ensureAutogenReadiness() {
  if (!autogenState.readiness || typeof autogenState.readiness !== 'object') {
    autogenState.readiness = {
      hardware: emptyReadinessEntry(),
      transport: emptyReadinessEntry(),
      sawtooth: emptyReadinessEntry(),
      sorter: emptyReadinessEntry(),
      system: emptyReadinessEntry(),
      safety: emptyReadinessEntry(),
    };
  }
  ['hardware', 'transport', 'sawtooth', 'sorter', 'system', 'safety'].forEach((k) => {
    if (!autogenState.readiness[k]) autogenState.readiness[k] = emptyReadinessEntry();
  });
  return autogenState.readiness;
}

function formatSafetyZoneDiagnostics(zones) {
  /** Actionable per-zone REVIEW lines for Compile hub / activity log. */
  const list = Array.isArray(zones) ? zones : [];
  const classify = (m) => {
    const u = String(m || '').toUpperCase();
    if (/ESR/.test(u)) return 'ESR';
    if (/MCR/.test(u)) return 'MCR';
    if (/(^|_)ES\d|ESTOP|E_STOP|E-STOP/.test(u)) return 'ESTOP';
    return 'OTHER';
  };
  return list.map((z) => {
    if (!z) return '';
    const name = z.name || z.safetyZone || '—';
    const area = z.area || '—';
    const convs = Array.isArray(z.conveyors) ? z.conveyors.length : Number(z.conveyor_count || 0);
    const mems = Array.isArray(z.members) ? z.members : [];
    const buckets = { ESTOP: [], ESR: [], MCR: [], OTHER: [] };
    mems.forEach((m) => { buckets[classify(m)].push(m); });
    const memStatus = z.safety_device_membership
      || z.device_membership_status
      || (mems.length ? 'RESOLVED' : 'UNRESOLVED');
    const gap = z.gap
      || (memStatus === 'UNRESOLVED'
        ? 'No proven RUN relationship currently maps safety devices into this zone.'
        : (z.missing || ''));
    const areaReady = area && area !== '—' ? 'READY' : 'REVIEW';
    const convReady = convs > 0 ? 'READY' : 'REVIEW';
    const lines = [
      `Safety Zone: ${name}`,
      `Area: ${area} · ${areaReady}`,
      `Conveyors: ${convs} · ${convReady}`,
      `E-Stops: ${buckets.ESTOP.length ? `${buckets.ESTOP.length} RESOLVED` : 'UNRESOLVED · REVIEW'}`,
      `ESR: ${buckets.ESR.length ? `${buckets.ESR.length} RESOLVED` : 'UNRESOLVED · REVIEW'}`,
      `MCR: ${buckets.MCR.length ? `${buckets.MCR.length} RESOLVED` : 'UNRESOLVED · REVIEW'}`,
    ];
    if (gap && memStatus !== 'RESOLVED') lines.push(`Reason: ${gap}`);
    return lines.join('\n');
  }).filter(Boolean);
}

function safetyEvidence() {
  const wb = autogenState.workbook || {};
  const build = wb.safety_build || autogenState.safety_build || {};
  const zones = Array.isArray(build.zones) ? build.zones : [];
  const counts = build.counts || {};
  const devices = Array.isArray(build.devices) ? build.devices : [];
  // Safety Build (canonical) + Transportation seeds
  const withConveyors = zones.filter((z) => z && (
    (z.conveyors || z.conveyorRefs || []).length || (z.members || []).length
  ));
  const withMembers = zones.filter((z) => z && (z.members || []).length);
  const last = autogenState.lastEsReport || null;
  const readyN = zones.filter((z) => String(z.status || '').toUpperCase() === 'READY').length;
  const reviewN = zones.filter((z) => String(z.status || '').toUpperCase() === 'REVIEW_REQUIRED'
    || (!(z.members || []).length && (z.conveyors || z.conveyorRefs || []).length)).length;
  const unassignedList = Array.isArray(build.unassignedDevices)
    ? build.unassignedDevices.map((d) => (typeof d === 'string' ? d : (d?.name || ''))).filter(Boolean)
    : devices
      .filter((d) => d && String(d.status || '').toUpperCase() === 'UNASSIGNED')
      .map((d) => d.name)
      .filter(Boolean);
  const unassignedN = Number(counts.unassigned ?? unassignedList.length) || unassignedList.length;
  const devicesFound = Number(counts.devices_found ?? counts.devices ?? devices.length) || devices.length;
  const resolvedN = Math.max(0, devicesFound - unassignedN);
  // PL-5: engineer-facing inventory counts (exact identities preserved in unassignedList)
  const mcrN = Number(counts.mcr ?? devices.filter((d) => String(d.kind || '').toUpperCase() === 'MCR').length) || 0;
  const esrN = Number(counts.esr ?? devices.filter((d) => String(d.kind || '').toUpperCase() === 'ESR').length) || 0;
  const estopN = Number(counts.estops ?? devices.filter((d) => {
    const k = String(d.kind || '').toUpperCase();
    return k === 'ESTOP' || k === 'ES' || k === 'E-STOP';
  }).length) || 0;
  const shellOnly = !!(last && last.shell);
  const safeLogicN = Array.isArray(last?.routines)
    ? last.routines.filter((r) => String(r).endsWith('_Safe_Logic')).length
    : 0;
  const safePiN = Array.isArray(last?.routines)
    ? last.routines.filter((r) => String(r).endsWith('_Safe_PI')).length
    : 0;
  const diagZones = (last && Array.isArray(last.zones) && last.zones.length)
    ? last.zones
    : withConveyors.map((z) => ({
      name: z.name || z.safetyZone,
      area: z.area || z.areaRef || '',
      conveyors: z.conveyors || z.conveyorRefs || [],
      members: z.members || [],
      safety_device_membership: (z.members || []).length ? 'RESOLVED' : 'UNRESOLVED',
      gap: (z.members || []).length
        ? ''
        : 'SafetyDevices unresolved — assign in Safety Build',
      fields: z.fields || {},
    }));
  const diagnostics = formatSafetyZoneDiagnostics(diagZones);
  return {
    detected: withConveyors.length > 0
      || withMembers.length > 0
      || devicesFound > 0
      || (last && last.status && last.status !== 'NOT_DETECTED'),
    zones: withConveyors.length || last?.zones?.length || 0,
    members: withMembers.reduce((n, z) => n + ((z.members || []).length), 0),
    conveyors: withConveyors.reduce((n, z) => n + ((z.conveyors || z.conveyorRefs || []).length), 0),
    ready: readyN,
    reviewRequired: reviewN,
    unassigned: unassignedN,
    unassignedDevices: unassignedList,
    devicesFound,
    resolvedDevices: resolvedN,
    mcr: mcrN,
    esr: esrN,
    estops: estopN,
    shellOnly,
    safeLogicCount: safeLogicN,
    safePiCount: safePiN,
    // Lifecycle vocabulary (PARTIAL BUILD CONTRACT):
    // FOUND = discovered in RUN; CONFIGURED/INCLUDED = zone members assigned;
    // GENERATED = Safe_Logic members actually emitted; UNASSIGNED ≠ SAFE.
    foundDevices: devicesFound,
    configuredDevices: resolvedN,
    includedDevices: resolvedN,
    generatedDevices: safeLogicN > 0
      ? withMembers.reduce((n, z) => n + ((z.members || []).length), 0)
      : 0,
    commissioningReady: !!(last && last.status === 'READY' && !last.shell && unassignedN === 0),
    last,
    diagnostics,
    diagZones,
  };
}

function formatAppliedAt(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  } catch (_) {
    return String(iso);
  }
}

function hasTransportGraphEvidence() {
  try {
    const raw = localStorage.getItem('siteforge.transportBuild.v2')
      || localStorage.getItem('siteforge.transportBuild.v1');
    if (!raw) return false;
    const data = JSON.parse(raw);
    return Array.isArray(data.areas) && data.areas.some((a) => (a.nodes || []).length);
  } catch (_) {
    return false;
  }
}

function transportEvidence() {
  const wb = autogenState.workbook;
  const merges = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const tbRows = (wb?.conveyors || []).filter((r) => r && (r.transport_build || r.source === 'transport_build_graph'));
  const convN = (wb?.conveyors || []).filter((r) => r?.include !== false).length;
  const graph = hasTransportGraphEvidence();
  return {
    detected: !!(graph || tbRows.length || merges.length || convN),
    hasGraph: graph,
    tbRows: tbRows.length,
    merges: merges.length,
    convN,
  };
}

function sawtoothEvidence() {
  const saw = reconcileSawtoothConfigurationRequired(autogenState.sawtooth || {});
  autogenState.sawtooth = saw;
  const lanes = (saw.lanes || []).filter((l) => l && l.conveyor);
  const unresolved = Array.isArray(saw.configuration_required) ? saw.configuration_required.length : 0;
  const detected = !!(saw.collector_conveyor || lanes.length || saw.detected || saw.discovery_source === 'site_model');
  return {
    detected,
    collector: saw.collector_conveyor || '',
    lanes: lanes.length,
    unresolved,
    enc: saw.collector_has_encoder === 'no' ? 'NO_Enc' : (saw.collector_encoder || 'UNRESOLVED'),
  };
}

function sorterEvidence() {
  const s = autogenState.sorter || {};
  const trackN = Number(s.tracking_count || 0);
  const divertN = Number(s.divert_count || 0);
  const gen = String(s.generation_state || '').toUpperCase();
  const plcGen = String(s.plc_generation || '').toUpperCase();
  const unresolved = Array.isArray(s.configuration_required) ? s.configuration_required.length : 0;
  const detected = !!(
    s.induct_conveyor || trackN || divertN || s.sorter_type
    || s.sorter_name || s.induct_encoder_tag || (s.known_sorters || []).length
    || s.detected || s.sorters_detected
  );
  // Phase 1 pack compiler: GENERATABLE / PHASE1_* are supported.
  // Only treat explicit NOT_SUPPORTED (legacy) as hard block.
  const phase1 =
    plcGen.includes('PHASE1')
    || gen.includes('GENERATABLE')
    || gen.includes('GENERATED')
    || plcGen === 'SUPPORTED';
  const notSupported = gen.includes('NOT_SUPPORTED') && !phase1;
  return {
    detected,
    name: s.sorter_name || s.sorter_type || '',
    trackN,
    divertN,
    unresolved,
    gen,
    plcGen,
    phase1,
    notSupported,
  };
}

function shippingSorterEvidence() {
  const s = autogenState.sorter || {};
  const sm = autogenState.workbook?.sorter_model
    || autogenState.workbook?.site_model?.sorter_model
    || {};
  const apps = sm.application_structure?.apps || s.application_structure?.apps || [];
  const appHit = (Array.isArray(apps) ? apps : []).some(
    (a) => /shipping\s*sorter/i.test(String(a || '')),
  );
  const siteOk = !!(
    s.shipping_sorter_supported
    || s.site_model_shippingsorter
    || sm.shipping_sorter_supported
    || appHit
    || s.sorter_area_name
    || sm.sorter_area_name
  );
  const typeShoe = s.sorter_type === 'shoe_sorter' || sm.sorter_type === 'shoe_sorter';
  const typePopup = s.sorter_type === 'popup_divert';
  // Area programs generate when sorter area identity is proven — not only shoe_sorter enum.
  return {
    shoe: siteOk && (typeShoe || !!s.sorter_area_name || !!sm.sorter_area_name || appHit),
    popup: siteOk && typePopup,
    supported: siteOk && (typeShoe || typePopup || !!s.sorter_area_name || !!sm.sorter_area_name || appHit),
    areaName: s.sorter_area_name || s.area_name || sm.sorter_area_name || sm.transport_area || '',
  };
}

function wcsEvidence() {
  const wb = autogenState.workbook;
  const site = wb?.wcs || wb?.site_model?.wcs || autogenState.wcs;
  return !!(site && (site.detected || site.supported === true));
}

function runIsLoaded() {
  const wb = autogenState.workbook;
  if (wb && wb.source === 'cleared') return false;
  if (wb && ((wb.conveyors || []).length || wb.machine || wb.site || wb.source)) return true;
  return !!(state.workspace);
}

/**
 * Recompute compile-hub readiness from evidence + appliedAt / dirty flags.
 * Does not invent Sorter/WCS generation — only reflects Apply state.
 */
function computeCompileHubReadiness() {
  const R = ensureAutogenReadiness();
  const nowDetail = {};

  // Hardware / IO
  {
    const e = R.hardware;
    const hw = (typeof ioState !== 'undefined' && ioState) ? ioState.hardwareIo : null;
    const unresolvedWords = hw
      ? ((hw.unresolved_words || []).length || hw.stats?.unresolved_count || 0)
      : 0;
    const unresolvedOwners = hw
      ? (hw.stats?.unresolved_owner_count || 0)
      : 0;
    const unresolvedN = unresolvedWords + unresolvedOwners;
    const adapterN = hw ? ((hw.adapters || []).length || hw.stats?.adapter_count || 0) : 0;
    if (autogenState.lastGenerateIoMapError) {
      e.status = 'ERROR';
      e.unresolved = 1;
      e.detail = autogenState.lastGenerateIoMapError;
    } else if (!runIsLoaded()) {
      e.status = 'NOT_DETECTED';
      e.unresolved = 0;
      e.detail = 'Load RUN on I/O & Prints';
    } else if (e.dirty && e.appliedAt) {
      e.status = 'CHANGED';
      e.unresolved = unresolvedN;
      e.detail = `Edited since Apply · ${formatAppliedAt(e.appliedAt)}`
        + (hw ? ` · resolver ${adapterN} adapter(s) · ${unresolvedWords} unresolved word(s) · ${unresolvedOwners} unresolved owner(s)` : '');
    } else {
      e.status = unresolvedOwners > 0 ? 'REVIEW_REQUIRED' : 'READY';
      e.unresolved = unresolvedN;
      if (!e.appliedAt) e.appliedAt = new Date().toISOString();
      e.detail = hw
        ? `Resolver tree · ${adapterN} adapter(s) · ${unresolvedWords} unresolved word(s) · ${unresolvedOwners} unresolved owner(s) · IO_MAP included`
          + (e.appliedAt ? ` · applied ${formatAppliedAt(e.appliedAt)}` : '')
        : `RUN loaded · IO_MAP included${e.appliedAt ? ` · applied ${formatAppliedAt(e.appliedAt)}` : ''}`;
    }
    nowDetail.hardware = e;
  }

  // Transport
  {
    const ev = transportEvidence();
    const e = R.transport;
    if (!ev.detected) {
      e.status = 'NOT_DETECTED';
      e.unresolved = 0;
      e.detail = 'No conveyors / Transport graph yet';
    } else if (e.dirty && e.appliedAt) {
      e.status = 'CHANGED';
      e.unresolved = 0;
      e.detail = `Edited since Apply · ${formatAppliedAt(e.appliedAt)}`;
    } else if (e.appliedAt && e.status !== 'ERROR') {
      e.status = 'READY';
      e.detail = `${ev.convN || ev.tbRows} conveyor(s) · ${ev.merges} merge(s) · applied ${formatAppliedAt(e.appliedAt)}`;
    } else {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = ev.hasGraph && !e.appliedAt ? 1 : 0;
      e.detail = ev.hasGraph
        ? 'Graph present — Apply on Transport Build'
        : `${ev.convN} conveyor(s) — Apply on Transport Build`;
    }
    nowDetail.transport = e;
  }

  // Sawtooth
  {
    const ev = sawtoothEvidence();
    const e = R.sawtooth;
    if (!ev.detected) {
      e.status = 'NOT_DETECTED';
      e.unresolved = 0;
      e.detail = 'Not detected on active RUN';
    } else if (ev.unresolved > 0 && !(e.appliedAt && !e.dirty)) {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = ev.unresolved;
      e.detail = `${ev.unresolved} unresolved · collector ${ev.collector || '—'} · ${ev.lanes} lane(s)`;
    } else if (e.dirty && e.appliedAt) {
      e.status = 'CHANGED';
      e.unresolved = ev.unresolved;
      e.detail = `Edited since Apply · ${ev.unresolved ? `${ev.unresolved} unresolved · ` : ''}${formatAppliedAt(e.appliedAt)}`;
    } else if (e.appliedAt) {
      e.status = ev.unresolved > 0 ? 'REVIEW_REQUIRED' : 'READY';
      e.unresolved = ev.unresolved;
      e.detail = ev.unresolved > 0
        ? `${ev.unresolved} unresolved after Apply — review Sawtooth tab`
        : `Collector ${ev.collector || '—'} · enc ${ev.enc} · ${ev.lanes} lane(s) · applied ${formatAppliedAt(e.appliedAt)}`;
    } else {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = ev.unresolved;
      e.detail = `Detected — Apply on Sawtooth Merge${ev.unresolved ? ` · ${ev.unresolved} unresolved` : ''}`;
    }
    nowDetail.sawtooth = e;
  }

  // Sorter (no new generation — readiness / evidence only)
  {
    const ev = sorterEvidence();
    const e = R.sorter;
    if (!ev.detected) {
      e.status = 'NOT_DETECTED';
      e.unresolved = 0;
      e.detail = 'Not detected on active RUN';
    } else if (ev.notSupported) {
      e.status = 'ERROR';
      e.unresolved = Math.max(1, ev.unresolved);
      e.detail = `GENERATION NOT SUPPORTED · ${ev.name || 'sorter'} (data shown only)`;
    } else if (e.appliedAt && ev.phase1) {
      e.status = ev.unresolved > 0 ? 'REVIEW_REQUIRED' : 'READY';
      e.unresolved = ev.unresolved;
      e.detail = `${ev.name || 'sorter'} · Phase 1 Sorter_Track · track ${ev.trackN} · divert ${ev.divertN}`
        + (ev.unresolved ? ` · ${ev.unresolved} engineer/review` : '')
        + ` · applied ${formatAppliedAt(e.appliedAt)}`;
    } else if (e.dirty && e.appliedAt) {
      e.status = 'CHANGED';
      e.unresolved = ev.unresolved;
      e.detail = `Edited since Apply · ${formatAppliedAt(e.appliedAt)}`;
    } else if (e.appliedAt && ev.unresolved === 0) {
      e.status = 'READY';
      e.detail = `${ev.name || 'sorter'} · track ${ev.trackN} · divert ${ev.divertN} · applied ${formatAppliedAt(e.appliedAt)}`;
    } else {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = ev.unresolved;
      e.detail = ev.unresolved
        ? `${ev.unresolved} unresolved — Apply on Sorter Build`
        : 'Detected — Apply on Sorter Build';
    }
    nowDetail.sorter = e;
  }

  // System / Core — mandatory packs once RUN present
  {
    const e = R.system;
    if (!runIsLoaded()) {
      e.status = 'NOT_DETECTED';
      e.detail = 'Sys · Device Comms · System Logic · IO_MAP (pending RUN)';
    } else {
      e.status = 'READY';
      if (!e.appliedAt) e.appliedAt = new Date().toISOString();
      e.unresolved = 0;
      e.detail = `Mandatory · applied ${formatAppliedAt(e.appliedAt)}`;
    }
    nowDetail.system = e;
  }

  // Safety / ES Program — REVIEW REQUIRED ≠ FATAL; partial ES emit for ready zones.
  // Never mark READY when last emit was REVIEW_REQUIRED, unassigned devices remain,
  // or any expected zone is still REVIEW.
  {
    const ev = safetyEvidence();
    const e = R.safety;
    const last = ev.last;
    const diagText = (ev.diagnostics || []).slice(0, 3).join(' | ');
    const unNames = (ev.unassignedDevices || []).slice(0, 6);
    const unSuffix = unNames.length
      ? ` · Unassigned: ${unNames.join(', ')}${(ev.unassignedDevices || []).length > 6 ? ', …' : ''}`
      : (ev.unassigned > 0 ? ` · Unassigned: ${ev.unassigned}` : '');
    const structBits = [
      `Found ${ev.foundDevices || ev.devicesFound || 0}`,
      `Configured ${ev.configuredDevices || ev.resolvedDevices || 0}`,
      `Included ${ev.includedDevices != null ? ev.includedDevices : (ev.resolvedDevices || 0)}`,
      `Unassigned ${ev.unassigned || 0}`,
      `Generated ${ev.generatedDevices || 0}`,
      ev.mcr != null ? `MCR ${ev.mcr}` : null,
      (ev.estops || ev.esr) ? `E-Stop/ESR ${(ev.estops || 0) + (ev.esr || 0)}` : null,
      ev.zones ? `Zones ${ev.zones}` : null,
      ev.shellOnly ? 'ES shell' : null,
      `Safe_Logic ${ev.safeLogicCount || 0}`,
      `Safe_PI ${ev.safePiCount || 0}`,
      ev.commissioningReady ? 'COMMISSIONING READY' : 'COMMISSIONING READY = NO',
    ].filter(Boolean).join(' · ');
    const reviewDetail = (ev.devicesFound > 0)
      ? `${structBits}${unSuffix} · Open Safety Build`
      : (diagText || last?.detail || `${ev.zones} zone(s) need membership · ${structBits}`);
    if (last?.status === 'ERROR') {
      e.status = 'ERROR';
      e.unresolved = last.unresolved || 1;
      e.detail = last.detail || 'ES program emit error';
      e.diagnostics = ev.diagnostics || [];
    } else if (!ev.detected) {
      e.status = 'NOT_DETECTED';
      e.unresolved = 0;
      e.detail = 'No Safety Zone membership (proven or engineer-assigned)';
      e.diagnostics = [];
    } else if (
      last?.status === 'REVIEW_REQUIRED'
      || (ev.unassigned > 0)
      || (ev.reviewRequired > 0)
      || (last?.partial && last?.status !== 'READY')
    ) {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = last?.unresolved || ev.unassigned || ev.reviewRequired || 1;
      e.detail = reviewDetail;
      e.diagnostics = ev.diagnostics || [];
    } else if (last?.status === 'READY' || (ev.zones > 0 && ev.members > 0 && ev.unassigned === 0 && ev.reviewRequired === 0 && e.appliedAt && !e.dirty)) {
      e.status = 'READY';
      e.detail = last?.detail || `${ev.zones} zone(s) · ${ev.members} member(s)`;
      e.diagnostics = ev.diagnostics || [];
    } else {
      e.status = 'REVIEW_REQUIRED';
      e.unresolved = last?.unresolved || Math.max(1, ev.zones - (ev.members > 0 ? 0 : 0) || 1);
      e.detail = reviewDetail;
      e.diagnostics = ev.diagnostics || [];
    }
    nowDetail.safety = e;
  }

  return nowDetail;
}

function setReadinessApplied(key, detail = '') {
  const R = ensureAutogenReadiness();
  const e = R[key] || (R[key] = emptyReadinessEntry());
  e.appliedAt = new Date().toISOString();
  e.dirty = false;
  if (detail) e.detail = detail;
  // Safety: do not blindly force READY — recompute from safetyEvidence / sync
  // (unassigned devices or REVIEW zones must keep REVIEW_REQUIRED).
  if (key === 'safety') {
    try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    return e;
  }
  e.status = 'READY';
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  return e;
}

function markReadinessDirty(key) {
  const R = ensureAutogenReadiness();
  const e = R[key];
  if (!e) return;
  if (!e.appliedAt) {
    // Still detected/unapplied — keep REVIEW_REQUIRED via recompute
    try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    return;
  }
  e.dirty = true;
  e.status = 'CHANGED';
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
}

function readinessDisplayLabel(status, { buildFacing = false } = {}) {
  if (buildFacing && status === 'READY') return 'READY FOR BUILD';
  return READINESS_LABELS[status] || READINESS_LABELS.REVIEW_REQUIRED;
}

function paintHubReadinessCards(map, targets, { buildFacing = false } = {}) {
  targets.forEach(([key, statusId, detailId]) => {
    const e = map[key] || emptyReadinessEntry();
    const status = e.status || 'NOT_DETECTED';
    document.querySelectorAll(`.hub-ready-card[data-ready-key="${key}"]`).forEach((card) => {
      card.setAttribute('data-status', status);
    });
    const sEl = $(statusId);
    if (sEl) sEl.textContent = readinessDisplayLabel(status, { buildFacing });
    const dEl = $(detailId);
    if (dEl) {
      // Safety: show multi-line actionable diagnostics when present
      if (key === 'safety' && Array.isArray(e.diagnostics) && e.diagnostics.length) {
        dEl.style.whiteSpace = 'pre-wrap';
        dEl.textContent = e.diagnostics.slice(0, 4).join('\n\n');
      } else {
        dEl.style.whiteSpace = '';
        const bits = [];
        if (e.detail) bits.push(e.detail);
        if (e.status === 'REVIEW_REQUIRED' && e.unresolved > 0 && !/unresolved/i.test(e.detail || '')) {
          bits.push(`${e.unresolved} unresolved`);
        }
        if (e.status === 'READY' && e.appliedAt && !/applied/i.test(e.detail || '')) {
          bits.push(`applied ${formatAppliedAt(e.appliedAt)}`);
        }
        dEl.textContent = bits.join(' · ') || '—';
      }
    }
  });
}

/**
 * Compact Project Health strip — VIEW of the same Compile Hub readiness map.
 * Does NOT create a second readiness engine.
 */
function paintProjectHealthStrip(map) {
  const el = $('project-health-strip');
  if (!el) return;
  const chips = [
    { key: 'run', label: 'RUN', tab: 'io', get: () => (runIsLoaded() ? { status: 'READY', detail: 'loaded' } : { status: 'NOT_DETECTED', detail: 'none' }) },
    { key: 'hardware', label: 'HW', tab: 'io' },
    { key: 'transport', label: 'TRANSPORT', tab: 'transport' },
    { key: 'safety', label: 'SAFETY', tab: 'safety' },
    { key: 'sawtooth', label: 'SAW', tab: 'sawtooth' },
    { key: 'system', label: 'CORE', tab: 'autogen' },
  ];
  // Optional merge count from real workbook data only
  const merges = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const icon = (st) => {
    if (st === 'READY') return '✓';
    if (st === 'ERROR') return '✕';
    if (st === 'NOT_DETECTED') return '—';
    return '⚠'; // REVIEW / CHANGED / other
  };
  const tone = (st) => {
    if (st === 'READY') return 'text-emerald-400 border-emerald-800/50';
    if (st === 'ERROR') return 'text-red-400 border-red-900/50';
    if (st === 'NOT_DETECTED') return 'text-slate-600 border-slate-800';
    return 'text-amber-300 border-amber-800/40';
  };
  const parts = chips.map((c) => {
    const e = c.get ? c.get() : (map[c.key] || emptyReadinessEntry());
    const st = e.status || 'NOT_DETECTED';
    let extra = '';
    if (c.key === 'hardware' && e.unresolved > 0) extra = String(e.unresolved);
    if (c.key === 'safety' && e.unresolved > 0) extra = String(e.unresolved);
    if (c.key === 'transport') {
      const ev = transportEvidence();
      if (ev.convN) extra = String(ev.convN);
    }
    const title = `${c.label}: ${readinessDisplayLabel(st)}${e.detail ? ` — ${e.detail}` : ''}`;
    return `<button type="button" data-jump-tab="${c.tab}" class="px-1.5 py-0.5 rounded border ${tone(st)} hover:bg-slate-800/60 whitespace-nowrap" title="${escapeHtml(title)}">${icon(st)} ${c.label}${extra ? ` ${extra}` : ''}</button>`;
  });
  if (merges.length) {
    parts.push(
      `<span class="px-1.5 py-0.5 rounded border border-slate-700 text-cyan-300/90 whitespace-nowrap" title="Workbook merges (proven/configured)">MERGES ${merges.length}</span>`
    );
  }
  el.innerHTML = parts.join('');
  el.classList.toggle('hidden', !runIsLoaded() && !(map.transport?.status && map.transport.status !== 'NOT_DETECTED'));
}

/** PLC Autogen compile hub — explicit readiness cards (+ I/O Ready For Build mirror) */
function refreshAutogenCompileHub() {
  const map = computeCompileHubReadiness();
  paintHubReadinessCards(map, [
    ['hardware', 'autogen-hub-hardware', 'autogen-hub-hardware-detail'],
    ['transport', 'autogen-hub-transport', 'autogen-hub-transport-detail'],
    ['sawtooth', 'autogen-hub-sawtooth', 'autogen-hub-sawtooth-detail'],
    ['sorter', 'autogen-hub-sorter', 'autogen-hub-sorter-detail'],
    ['safety', 'autogen-hub-safety', 'autogen-hub-safety-detail'],
    ['system', 'autogen-hub-system', 'autogen-hub-system-detail'],
  ], { buildFacing: false });
  try { paintProjectHealthStrip(map); } catch (_) { /* ignore */ }
  // Ready For Build strip removed from I/O & Prints — Compile hub on Autogen only.

  const evT = transportEvidence();
  const evS = sawtoothEvidence();
  const evR = sorterEvidence();
  $('autogen-hub-empty-hint')?.classList.toggle(
    'hidden',
    !!(runIsLoaded() || evT.detected || evS.detected || evR.detected),
  );
  try { refreshAutogenPackEvidence(); } catch (_) { /* ignore */ }
  try { refreshAutogenBuildTracker(); } catch (_) { /* ignore */ }
  try { updateSubsystemGenerationContract(); } catch (_) { /* ignore */ }
}

/** Autogen Build tracker — live pack / export / integrity (replaces redundant workbook tabs). */
function refreshAutogenBuildTracker() {
  const root = $('autogen-build-tracker');
  if (!root) return;
  const wb = autogenState.workbook;
  const rows = wb?.conveyors || [];
  const on = rows.filter((r) => r && r.include !== false).length;
  const R = ensureAutogenReadiness();
  const hw = ioState?.hardwareIo;
  const machine = (hw?.controller?.machine || hw?.machine
    || wb?.project_name || wb?.controller_name
    || (typeof runIsLoaded === 'function' && runIsLoaded() ? 'RUN loaded' : '—'));
  const ctrlEl = $('bt-controller');
  if (ctrlEl) ctrlEl.textContent = machine || '—';
  const convEl = $('bt-conveyors');
  if (convEl) {
    convEl.textContent = rows.length
      ? `${on}/${rows.length} on · ${wb?.stats?.io_mapped ?? '—'} IO`
      : '0';
  }
  const l5xEl = $('bt-l5x');
  if (l5xEl) {
    const path = autogenState.lastL5x || '';
    l5xEl.textContent = path ? path.split(/[\\/]/).pop() : '— none yet —';
    l5xEl.title = path || '';
  }
  const progEl = $('bt-programs');
  if (progEl) {
    const line = (name, st, tone) =>
      `<div class="${tone || 'text-slate-400'}"><span class="text-slate-500">${name}</span> · ${st}</div>`;
    const hubTone = (st) => (st === 'READY' ? 'text-emerald-400' : st === 'ERROR' ? 'text-red-400' : 'text-slate-400');
    const hubLabel = (st) => (st === 'READY' ? 'READY' : st === 'NOT_DETECTED' ? 'not detected' : (st || '—').toLowerCase());
    progEl.innerHTML = [
      line('HW / IO', hubLabel(R.hardware?.status), hubTone(R.hardware?.status)),
      line('Transport', hubLabel(R.transport?.status), hubTone(R.transport?.status)),
      line('Sawtooth', hubLabel(R.sawtooth?.status), hubTone(R.sawtooth?.status)),
      line('Sorter', hubLabel(R.sorter?.status), hubTone(R.sorter?.status)),
      line('System', hubLabel(R.system?.status), hubTone(R.system?.status)),
    ].join('');
  }
  const intEl = $('bt-integrity');
  if (intEl) {
    const bits = [];
    const man = autogenState.lastManifest;
    const git = man?.git_commit || man?.git || '';
    if (autogenState.lastL5x) {
      bits.push(`<div class="text-emerald-400">Last L5X recorded</div>`);
      if (git) bits.push(`<div>git <span class="text-slate-300">${escapeHtml(String(git).slice(0, 12))}</span></div>`);
      const sha = man?.output_sha256 || man?.l5x_sha256 || '';
      if (sha) bits.push(`<div>SHA <span class="text-slate-500">${escapeHtml(String(sha).slice(0, 12))}…</span></div>`);
    } else {
      bits.push(`<div class="text-slate-500">No export yet — Build PLC when hub is READY</div>`);
    }
    bits.push(`<div class="text-slate-600 mt-1">Desc ≤128 · DataTypes closed · track enables</div>`);
    if (autogenState.lastGenerateIoMapError) {
      bits.push(`<div class="text-red-400 mt-1">${escapeHtml(String(autogenState.lastGenerateIoMapError).slice(0, 120))}</div>`);
    }
    intEl.innerHTML = bits.join('');
  }
  const stagesEl = $('bt-stages');
  if (stagesEl) {
    const pre = typeof autogenBuildPreflight === 'function' ? autogenBuildPreflight() : { ok: false };
    const stages = [
      { id: 'run', label: 'RUN', ok: typeof runIsLoaded === 'function' && runIsLoaded() },
      { id: 'wb', label: 'Workbook', ok: rows.length > 0 },
      { id: 'hub', label: 'Hub READY', ok: !!pre.ok },
      { id: 'l5x', label: 'L5X', ok: !!autogenState.lastL5x },
    ];
    stagesEl.innerHTML = stages.map((s) =>
      `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded border ${
        s.ok ? 'border-emerald-800/60 text-emerald-300 bg-emerald-950/30' : 'border-slate-800 text-slate-500 bg-[#0a1018]'
      }"><span class="w-1.5 h-1.5 rounded-full ${s.ok ? 'bg-emerald-400' : 'bg-slate-600'}"></span>${s.label}</span>`
    ).join('');
  }
}

function refreshAutogenPackEvidence() {
  const el = $('autogen-pack-evidence');
  if (!el) return;
  const R = ensureAutogenReadiness();
  const sawReady = R.sawtooth?.status === 'READY';
  const sorterReady = R.sorter?.status === 'READY';
  const merges = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const ship = shippingSorterEvidence();
  const wcs = wcsEvidence();
  const line = (name, text, tone) =>
    `<div class="${tone || 'text-slate-400'}">${name} · ${text}</div>`;
  el.innerHTML = [
    line('Sawtooth_Merge', sawReady ? 'INCLUDE (READY)' : (sawtoothEvidence().detected ? 'waiting Apply' : 'NOT DETECTED'),
      sawReady ? 'text-emerald-400' : 'text-slate-400'),
    line('Sorter_Track', sorterReady ? 'INCLUDE (READY)' : (sorterEvidence().detected ? 'waiting Apply' : 'NOT DETECTED'),
      sorterReady ? 'text-emerald-400' : 'text-slate-400'),
    line('Merges', merges.length ? `INCLUDE via workbook (${merges.length})` : 'none',
      merges.length ? 'text-emerald-400' : 'text-slate-500'),
    line('ShippingSorter', ship.supported ? 'SiteModel supported' : 'NOT DETECTED / NOT SUPPORTED',
      ship.supported ? 'text-cyan-300' : 'text-slate-500'),
    line('WCS', wcs ? 'SiteModel supported' : 'NOT DETECTED / NOT SUPPORTED',
      wcs ? 'text-cyan-300' : 'text-slate-500'),
  ].join('');
}

/**
 * PARTIAL BUILD CONTRACT (product requirement):
 *
 *   FOUND ≠ CONFIGURED ≠ INCLUDED ≠ GENERATED
 *   UNASSIGNED ≠ ERROR ≠ ACTIVE ≠ INCLUDED ≠ GENERATED ≠ SAFE
 *
 * Build PLC is ALLOWED when all INCLUDED/generated content is structurally valid.
 * REVIEW REQUIRED (unassigned discovered equipment, incomplete Safety membership,
 * detected-but-not-Applied Saw/Sorter) does NOT hard-block Export.
 *
 * Hard-block ERROR only when:
 *   - a mandatory pack (System/Hardware with RUN loaded) is ERROR
 *   - an INCLUDED (Applied) subsystem is ERROR
 *   - Safety emit itself returned ERROR
 *
 * Returns { ok, blockers, softReviews, softSafetyReview, partialBuildAllowed }.
 */
function autogenBuildPreflight({ allowOmitUnresolvedSafety = false } = {}) {
  const map = computeCompileHubReadiness();
  const blockers = [];
  const softReviews = [];
  const runLoaded = runIsLoaded();

  const pushSoft = (key, tab, label, e, extra) => {
    softReviews.push({
      key,
      tab,
      message: `${label}: ${readinessDisplayLabel(e.status)}${e.detail ? ` — ${e.detail}` : ''}`,
      ...(extra || {}),
    });
  };
  const pushHard = (key, tab, label, e) => {
    blockers.push({
      key,
      tab,
      message: `${label}: ${readinessDisplayLabel(e.status)}${e.detail ? ` — ${e.detail}` : ''}`,
    });
  };

  // Mandatory core when RUN is loaded — ERROR only hard-blocks
  [
    { key: 'system', tab: 'autogen', label: 'System / Core' },
    { key: 'hardware', tab: 'io', label: 'Hardware / IO' },
  ].forEach((n) => {
    if (!runLoaded) return;
    const e = map[n.key] || emptyReadinessEntry();
    if (e.status === 'ERROR') pushHard(n.key, n.tab, n.label, e);
    else if (e.status === 'REVIEW_REQUIRED' || e.status === 'CHANGED') {
      pushSoft(n.key, n.tab, n.label, e);
    }
  });

  // Transportation — INCLUDED only after Apply. Unassigned RUN equipment is FOUND, not a blocker.
  {
    const e = map.transport || emptyReadinessEntry();
    const included = !!e.appliedAt;
    if (e.status === 'ERROR' && included) pushHard('transport', 'transport', 'Transportation', e);
    else if (e.status === 'ERROR' && !included) pushSoft('transport', 'transport', 'Transportation', e);
    else if (e.status === 'REVIEW_REQUIRED' || e.status === 'CHANGED') {
      pushSoft('transport', 'transport', 'Transportation', e, {
        note: 'FOUND/unassigned conveyors do not block partial Build',
      });
    }
  }

  // Optional packs — discovered ≠ included. Only Applied ERROR hard-blocks.
  [
    {
      key: 'sawtooth',
      tab: 'sawtooth',
      label: 'Sawtooth',
      detected: sawtoothEvidence().detected,
    },
    {
      key: 'sorter',
      tab: 'sorter',
      label: 'Sorter',
      detected: sorterEvidence().detected && !sorterEvidence().notSupported,
    },
  ].forEach((n) => {
    const e = map[n.key] || emptyReadinessEntry();
    const included = !!e.appliedAt;
    if (!n.detected && e.status === 'NOT_DETECTED') return;
    if (e.status === 'ERROR' && included) pushHard(n.key, n.tab, n.label, e);
    else if (e.status === 'ERROR') pushSoft(n.key, n.tab, n.label, e);
    else if (e.status === 'REVIEW_REQUIRED' || e.status === 'CHANGED') {
      pushSoft(n.key, n.tab, n.label, e, {
        note: included
          ? 'INCLUDED pack needs review'
          : 'FOUND but not INCLUDED — does not block partial Build',
      });
    }
  });

  // Safety — unassigned devices are REVIEW, never SAFE, never hard-block unless ERROR
  {
    const e = map.safety || emptyReadinessEntry();
    const ev = safetyEvidence();
    if (e.status === 'ERROR') {
      pushHard('safety', 'safety', 'Safety / ES', e);
    } else if (
      e.status === 'REVIEW_REQUIRED'
      || e.status === 'CHANGED'
      || (ev.detected && e.status !== 'READY' && e.status !== 'NOT_DETECTED')
    ) {
      pushSoft('safety', 'safety', 'Safety / ES', e, {
        diagnostics: e.diagnostics || ev.diagnostics || [],
        lifecycle: {
          found: ev.devicesFound || 0,
          configured: ev.resolvedDevices || 0,
          included: ev.includedDevices != null ? ev.includedDevices : (ev.resolvedDevices || 0),
          unassigned: ev.unassigned || 0,
          generated: ev.generatedDevices != null ? ev.generatedDevices : (ev.safeLogicCount > 0 ? ev.resolvedDevices : 0),
          commissioningReady: !!ev.commissioningReady,
        },
        note: 'UNASSIGNED Safety ≠ ERROR; partial Build allowed with fail-safe ES shell',
      });
    }
  }

  void allowOmitUnresolvedSafety; // retained for callers; default path is partial emit
  const softSafetyReview = softReviews.filter((r) => r.key === 'safety');
  return {
    ok: blockers.length === 0,
    blockers,
    softReviews,
    softSafetyReview,
    onlySoftSafety: blockers.length === 0 && softSafetyReview.length > 0,
    partialBuildAllowed: blockers.length === 0,
    contract: 'FOUND≠INCLUDED≠GENERATED; REVIEW does not block; ERROR on INCLUDED blocks',
  };
}

window.markAutogenReadinessDirty = markReadinessDirty;
window.setAutogenReadinessApplied = setReadinessApplied;
window.activateTab = activateTab;

// Tabs
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

// Compile hub jump links
document.addEventListener('click', (ev) => {
  const jump = ev.target.closest?.('[data-jump-tab]');
  if (!jump) return;
  ev.preventDefault();
  activateTab(jump.dataset.jumpTab);
});

// Default landing tab: I/O & Prints (recontrol focus)
document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
const defaultTab = document.querySelector('.tab-btn[data-tab="io"]');
if (defaultTab) defaultTab.classList.add('active');
ALL_TABS.forEach((t) => {
  const pane = $(`tab-${t}`);
  if (pane) pane.classList.toggle('hidden', t !== 'io');
});

// Search
let searchTimer = null;
$('search-input').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(e.target.value), 220);
});

document.querySelectorAll('#quick-filters .badge').forEach((btn) => {
  btn.addEventListener('click', () => {
    $('search-input').value = btn.dataset.q;
    runSearch(btn.dataset.q);
  });
});

async function runSearch(query) {
  const box = $('search-results');
  if (!query.trim()) {
    box.innerHTML = `<div class="text-slate-500 text-sm py-8 text-center">Type a keyword to search <span id="doc-count-label">${$('doc-count-label')?.textContent || '0'}</span> training documents.</div>`;
    return;
  }
  box.innerHTML = '<div class="text-slate-500 text-sm py-6 text-center"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Searching…</div>';
  const res = await fortnaAPI.searchDocs(query);
  if (!res.success) {
    box.innerHTML = `<div class="text-red-400 text-sm py-6 text-center">${res.message || 'Search failed'}</div>`;
    return;
  }
  if (!res.results.length) {
    box.innerHTML = `<div class="text-slate-500 text-sm py-8 text-center">No matches for "<strong>${escapeHtml(query)}</strong>". Try photoeye, printer, or conveyor.</div>`;
    return;
  }
  box.innerHTML = res.results.map(renderDocHit).join('');
  box.querySelectorAll('[data-open-doc]').forEach((el) => {
    el.addEventListener('click', () => fortnaAPI.openPath(el.dataset.openDoc));
  });
}

function renderDocHit(doc) {
  const tasks = (doc.tasks || []).map((t) => `<span class="badge">${escapeHtml(t)}</span>`).join(' ');
  return `
    <div class="doc-hit rounded-xl p-4 cursor-pointer" data-open-doc="${escapeHtml(doc.file)}">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-semibold text-sm">${escapeHtml(doc.title)}</div>
          <div class="mono text-[11px] text-slate-500 mt-0.5">${escapeHtml(doc.file)}</div>
        </div>
        <span class="badge shrink-0">${escapeHtml(doc.category)}</span>
      </div>
      <p class="text-xs text-slate-400 mt-2 line-clamp-2">${escapeHtml(doc.summary || 'No preview available.')}</p>
      <div class="flex gap-1.5 mt-2 flex-wrap">${tasks}</div>
    </div>`;
}

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

$('btn-reindex').addEventListener('click', async () => {
  setBusy(true);
  log('Reindexing training documents…', 'info');
  const res = await fortnaAPI.reindexDocs();
  setBusy(false);
  if (res.success) {
    log(`Indexed ${res.count} documents.`, 'ok');
    setDocIndexStatus(res.count || 0);
    if ($('search-input').value.trim()) runSearch($('search-input').value);
  } else {
    log(res.message || 'Reindex failed', 'err');
    setStatus('index-status', 'Index error', 'error');
  }
});

// Recipes
function renderRecipeList() {
  const list = $('recipe-list');
  if (!state.recipes.length) {
    list.innerHTML = '<div class="text-slate-500 text-sm">No recipes loaded.</div>';
    return;
  }
  list.innerHTML = state.recipes.map((r) => `
    <div class="recipe-card rounded-xl p-4 ${r.id === state.selectedRecipeId ? 'selected' : ''}" data-recipe="${escapeHtml(r.id)}">
      <div class="font-semibold text-sm">${escapeHtml(r.title)}</div>
      <p class="text-xs text-slate-400 mt-1">${escapeHtml(r.summary)}</p>
      <div class="flex gap-1 mt-2 flex-wrap">${(r.tasks || []).map((t) => `<span class="badge">${escapeHtml(t)}</span>`).join('')}</div>
    </div>`).join('');
  list.querySelectorAll('[data-recipe]').forEach((el) => {
    el.addEventListener('click', () => {
      state.selectedRecipeId = el.dataset.recipe;
      $('recipe-select').value = state.selectedRecipeId;
      renderRecipeList();
      renderRecipeDetail(state.selectedRecipeId);
      renderRecipeParams();
    });
  });
  renderRecipeDetail(state.selectedRecipeId);
}

function renderRecipeDetail(recipeId) {
  const recipe = state.recipes.find((r) => r.id === recipeId);
  const box = $('recipe-detail');
  if (!recipe) {
    box.innerHTML = '<div class="text-slate-500 text-sm">Recipe not found.</div>';
    return;
  }
  const steps = (recipe.steps || []).map((s, i) => `
    <div class="step-line relative pl-8 pb-4">
      <div class="absolute left-0 top-0 w-6 h-6 rounded-full bg-cyan-900/60 border border-cyan-600 flex items-center justify-center text-[11px] font-bold text-cyan-300">${i + 1}</div>
      <div class="text-sm">${escapeHtml(s)}</div>
    </div>`).join('');
  const docs = (recipe.doc_refs || []).map((d) => `
    <button class="btn-ghost text-left px-3 py-2 rounded-lg text-xs w-full" data-open-doc="${escapeHtml(d)}">
      <i class="fa-regular fa-file-word mr-2 text-cyan-500"></i>${escapeHtml(d.split('/').pop())}
    </button>`).join('');
  const tables = (recipe.tables || []).map((t) => `<span class="badge mono">${escapeHtml(t)}</span>`).join(' ');
  box.innerHTML = `
    <h2 class="text-lg font-semibold mb-1">${escapeHtml(recipe.title)}</h2>
    <p class="text-sm text-slate-400 mb-4">${escapeHtml(recipe.summary)}</p>
    <div class="text-xs uppercase tracking-wider text-slate-500 mb-2">Tables touched</div>
    <div class="flex gap-1 flex-wrap mb-5">${tables}</div>
    <div class="text-xs uppercase tracking-wider text-slate-500 mb-3">How-to steps</div>
    <div class="mb-6">${steps}</div>
    <div class="text-xs uppercase tracking-wider text-slate-500 mb-2">Reference documents</div>
    <div class="space-y-1.5">${docs || '<div class="text-slate-500 text-sm">No linked docs.</div>'}</div>`;
  box.querySelectorAll('[data-open-doc]').forEach((el) => {
    el.addEventListener('click', () => fortnaAPI.openPath(el.dataset.openDoc));
  });
}

function toggleDeviceBrowser(show) {
  const el = $('device-browser');
  const rel = $('clone-related-wrap');
  if (el) el.classList.toggle('hidden', !show);
  if (rel) rel.classList.toggle('hidden', !show);
}

function renderRecipeParams() {
  const recipe = state.recipes.find((r) => r.id === state.selectedRecipeId);
  const box = $('recipe-params');
  const isClone = state.selectedRecipeId === 'clone-device';
  toggleDeviceBrowser(isClone);

  if (!recipe) {
    box.innerHTML = '';
    return;
  }

  if (isClone) {
    box.innerHTML = `
      <label class="text-xs text-slate-400 col-span-2">
        New device name
        <input id="param-newName" type="text" placeholder="P107_NEW or LANE6 SPIRAL"
          class="mt-1 w-full bg-[#101820] border border-slate-700 rounded-lg px-3 py-2 text-sm mono">
      </label>
      <label class="text-xs text-slate-400">
        X offset
        <input id="param-offsetX" type="number" value="0" step="50"
          class="mt-1 w-full bg-[#101820] border border-slate-700 rounded-lg px-3 py-2 text-sm mono">
      </label>
      <label class="text-xs text-slate-400">
        Y offset
        <input id="param-offsetY" type="number" value="0" step="50"
          class="mt-1 w-full bg-[#101820] border border-slate-700 rounded-lg px-3 py-2 text-sm mono">
      </label>`;
    return;
  }

  if (!recipe.params || !recipe.params.length) {
    box.innerHTML = '<div class="col-span-2 text-sm text-slate-500">Follow the how-to steps in the Recipes tab.</div>';
    return;
  }

  box.innerHTML = recipe.params.map((p) => {
    if (p.name === 'conveyor' && state.conveyors.length) {
      const opts = state.conveyors.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
      return `
        <label class="text-xs text-slate-400">
          ${escapeHtml(p.label)}
          <select id="param-conveyor" class="mt-1 w-full bg-[#101820] border border-slate-700 rounded-lg px-3 py-2 text-sm">
            <option value="">— pick conveyor —</option>${opts}
          </select>
        </label>`;
    }
    const id = `param-${p.name}`;
    return `
      <label class="text-xs text-slate-400">
        ${escapeHtml(p.label)}
        <input id="${id}" type="text" placeholder="${escapeHtml(p.example || '')}"
          class="mt-1 w-full bg-[#101820] border border-slate-700 rounded-lg px-3 py-2 text-sm mono">
      </label>`;
  }).join('');
}

function filteredDevices() {
  const cat = ($('device-category')?.value || '').toLowerCase();
  const q = ($('device-filter')?.value || '').trim().toLowerCase();
  return state.devices.filter((d) => {
    if (cat && d.category !== cat) return false;
    if (q && !`${d.name} ${d.table} ${d.type} ${d.description}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

function renderDeviceList() {
  const sel = $('device-template');
  if (!sel) return;
  const list = filteredDevices();
  if (!list.length) {
    sel.innerHTML = '<option value="">No devices match filter</option>';
    $('device-detail').textContent = '';
    state.selectedDevice = null;
    return;
  }
  sel.innerHTML = list.map((d) => {
    const label = `[${d.category}] ${d.name} — ${d.table}`;
    return `<option value="${escapeHtml(d.id)}">${escapeHtml(label)}</option>`;
  }).join('');
  sel.selectedIndex = 0;
  onDeviceSelected();
}

function onDeviceSelected() {
  const sel = $('device-template');
  const id = sel?.value;
  state.selectedDevice = state.devices.find((d) => d.id === id) || null;
  const detail = $('device-detail');
  if (!state.selectedDevice) {
    if (detail) detail.textContent = '';
    return;
  }
  const d = state.selectedDevice;
  detail.innerHTML = `Type: <span class="text-cyan-400">${escapeHtml(d.type)}</span> · Table: ${escapeHtml(d.table)}${d.description ? ` · ${escapeHtml(d.description)}` : ''}`;
  const nameInput = $('param-newName');
  if (nameInput && !nameInput.value) {
    nameInput.placeholder = `${d.name}_NEW`;
  }
}

$('recipe-select').addEventListener('change', (e) => {
  state.selectedRecipeId = e.target.value;
  renderRecipeParams();
  renderRecipeList();
});

$('device-category')?.addEventListener('change', renderDeviceList);
$('device-filter')?.addEventListener('input', () => {
  clearTimeout(window._devFilterTimer);
  window._devFilterTimer = setTimeout(renderDeviceList, 150);
});
$('device-template')?.addEventListener('change', onDeviceSelected);

// Workspace / dropzone (null-safe — missing node must not kill the whole script)
const dropzone = $('dropzone');
if (dropzone) {
  ['dragenter', 'dragover'].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });
  ['dragleave', 'drop'].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });
  dropzone.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (!file) return;
    const p = fortnaAPI.getPathForFile(file);
    if (p) await importArchive(p, file.name);
  });
}

$('btn-browse-archive')?.addEventListener('click', async () => {
  const res = await fortnaAPI.selectArchive();
  if (res.success && res.path) await importArchive(res.path, res.path.split(/[/\\]/).pop());
});

async function importArchive(path, name) {
  return importRunPackage(path, name);
}

function updateWorkspacePanel() {
  const m = state.workspace;
  if (!m) {
    $('workspace-info').textContent = 'No package imported yet.';
    return;
  }
  $('workspace-info').innerHTML = `
    <div class="mono text-xs space-y-1">
      <div><span class="text-slate-500">Machine</span> ${escapeHtml(m.machine)}</div>
      <div><span class="text-slate-500">RUN dir</span> ${escapeHtml(m.run_dir || '')}</div>
      <div><span class="text-slate-500">Imported</span> ${escapeHtml(m.imported || '')}</div>
      <div><span class="text-slate-500">Devices</span> ${m.device_count || m.devices?.length || 0}</div>
      <div><span class="text-slate-500">Conveyors</span> ${(m.conveyors || []).length}</div>
      ${m.device_categories ? `<div class="text-slate-500 mt-1">${Object.entries(m.device_categories).slice(0,6).map(([k,v]) => `${k}:${v}`).join(' · ')}</div>` : ''}
    </div>`;
}

async function refreshDevices() {
  const res = await fortnaAPI.listDevices({});
  if (res.success) {
    state.devices = res.devices || [];
    state.deviceCategories = res.categories || {};
    renderDeviceList();
  } else if (state.workspace?.devices) {
    state.devices = state.workspace.devices;
    state.deviceCategories = state.workspace.device_categories || {};
    renderDeviceList();
  }
}

$('btn-open-active').addEventListener('click', () => {
  if (state.workspace?.run_dir) fortnaAPI.openPath(state.workspace.run_dir);
});

$('btn-open-exports').addEventListener('click', () => {
  fortnaAPI.openPath('exports');
});

function setIoRunStatus(text, kind = 'idle') {
  const el = $('io-run-status');
  if (!el) return;
  el.textContent = text;
  el.className = `mono text-[10px] mt-2 ${
    kind === 'ready' ? 'text-emerald-400' :
    kind === 'busy' ? 'text-amber-400' :
    kind === 'error' ? 'text-red-400' : 'text-slate-500'
  }`;
}

/**
 * Reset Merge & Crosswalk / OCR compare UI (and optional panel PDF sets).
 * Called when clearing tar.gz or clearing all prints so stale results don't linger.
 */
/** Wipe Devices (by type) + I/O banks DOM completely (stale 960-row UI bug). */
function clearDevicesPanelUi() {
  if (typeof ioState !== 'undefined' && ioState) {
    ioState.banks = null;
    ioState.hardwareIo = null;
    ioState.hardwarePanelFilter = '__all__';
    ioState.hardwareRioFilter = '__all__';
    ioState.hardwareTreeExpanded = null;
    ioState._hwTreeInited = false;
    ioState.selectedHwModuleKey = '';
    ioState.selectedHwChannel = null;
    ioState.drives = [];
    ioState.devices = [];
    ioState.motorChains = [];
    ioState.printVfdParams = [];
    ioState.selectedDriveName = '';
    ioState.deviceTypeFilter = 'all';
  }
  // Hardware / I/O
  if ($('hw-io-status')) {
    $('hw-io-status').textContent = 'No RUN';
    $('hw-io-status').className = 'status-pill status-idle';
  }
  if ($('hw-io-controller')) $('hw-io-controller').textContent = 'Controller: —';
  if ($('hw-io-tree')) {
    $('hw-io-tree').innerHTML = '<div class="text-sm text-slate-500 py-6 text-center px-2">Load a RUN to show the resolver tree.</div>';
  }
  if ($('hw-io-racks')) {
    $('hw-io-racks').innerHTML = '<div class="text-sm text-slate-500 py-10 text-center">Load a RUN to show the FLEX assembly from PhysicalWordResolver.</div>';
  }
  if ($('hw-io-channel-table')) {
    $('hw-io-channel-table').innerHTML = 'Select a module on the rack to list channels (physical address · Fortna word.bit · logical endpoint).';
  }
  if ($('hw-io-module-detail')) {
    $('hw-io-module-detail').innerHTML = 'Select a module for the vertical terminal face (CH0●── …).';
  }
  if ($('hw-io-wiring')) {
    $('hw-io-wiring').textContent = 'Select a module — Level A shows proven channel→logical assignments. Catalog schematics (Level B) are not required yet.';
  }
  if ($('hw-io-stats')) $('hw-io-stats').innerHTML = '';
  if ($('hw-io-panel-select')) {
    $('hw-io-panel-select').innerHTML = '<option value="__all__">All Panels</option>';
  }
  if ($('hw-io-rio-select')) {
    $('hw-io-rio-select').innerHTML = '<option value="__all__">All adapters</option>';
  }
  // Banks
  if ($('io-banks-status')) {
    $('io-banks-status').textContent = 'No RUN';
    $('io-banks-status').className = 'status-pill status-idle';
  }
  if ($('io-banks-list')) {
    $('io-banks-list').textContent = 'Load a RUN package (.tar.gz) at the top of this tab to list banks.';
  }
  if ($('io-banks-stats')) {
    $('io-banks-stats').classList.add('hidden');
    $('io-banks-stats').innerHTML = '';
  }
  // Devices panel
  if ($('io-drives-status')) {
    $('io-drives-status').textContent = '—';
    $('io-drives-status').className = 'status-pill status-idle';
  }
  if ($('io-drives-stats')) {
    $('io-drives-stats').classList.add('hidden');
    $('io-drives-stats').innerHTML = '';
  }
  if ($('io-drives-tbody')) {
    $('io-drives-tbody').innerHTML =
      '<tr><td colspan="4" class="py-4 px-2 text-slate-500">Load a RUN package (.tar.gz) to list devices.</td></tr>';
  }
  if ($('device-type-filter')) {
    $('device-type-filter').innerHTML = '<option value="all">All devices</option>';
    $('device-type-filter').value = 'all';
  }
  if ($('device-type-count')) $('device-type-count').textContent = '0';
  if ($('drive-print-only')) $('drive-print-only').checked = false;
  try { showDriveDetail(null); } catch (_) { /* ignore */ }
}

function clearIoCompareState(opts = {}) {
  const { clearPanels = false, clearDevices = false } = opts;
  if (typeof ioState !== 'undefined' && ioState) {
    ioState.ocrResult = null;
    ioState.printVfdParams = [];
    ioState.crosswalkTab = 'matched';
    ioState.selectedDriveName = '';
    if (clearPanels) {
      ioState.panelSets = [];
      ioState.activePanelId = '';
    }
    if (clearDevices) {
      ioState.banks = null;
      ioState.drives = [];
      ioState.devices = [];
      ioState.motorChains = [];
    }
  }
  // Merge & crosswalk card
  if ($('io-crosswalk-summary')) {
    $('io-crosswalk-summary').textContent = 'No OCR run yet.';
  }
  if ($('io-match-heading')) {
    $('io-match-heading').textContent = 'Results';
  }
  if ($('io-match-list')) {
    $('io-match-list').textContent = 'Set master + remotes, drop PDFs, run OCR.';
  }
  // Progress bar
  if ($('ocr-progress-wrap')) $('ocr-progress-wrap').classList.add('hidden');
  if ($('ocr-progress-bar')) $('ocr-progress-bar').style.width = '0%';
  if ($('ocr-progress-pct')) $('ocr-progress-pct').textContent = '0%';
  if ($('ocr-progress-detail')) $('ocr-progress-detail').textContent = '';
  // OCR button idle
  if ($('btn-run-ocr')) {
    const hasPrints = typeof totalPrintFiles === 'function' ? totalPrintFiles() > 0 : false;
    const hasMaster = typeof getMasterPanel === 'function' ? !!getMasterPanel() : false;
    $('btn-run-ocr').disabled = !hasPrints || !hasMaster;
  }
  try { renderCrosswalk(null); } catch (_) { /* ignore */ }
  if (clearPanels) {
    try { renderPanelSets(); } catch (_) { /* ignore */ }
  }
  // Always hard-wipe devices panel when requested (do not rely on renderDriveParameters alone)
  if (clearDevices) {
    try { clearDevicesPanelUi(); } catch (_) { /* ignore */ }
  }
  try { updateRecontrolReady(); } catch (_) { /* ignore */ }
  // Drop persisted OCR so relaunch doesn't restore stale compare
  if (typeof fortnaAPI?.clearLastOcr === 'function') {
    fortnaAPI.clearLastOcr().catch(() => {});
  }
}

function resetWorkspaceUi() {
  state.workspace = null;
  state.devices = [];
  state.deviceCategories = {};
  state.conveyors = [];
  state.selectedDevice = null;
  updateWorkspacePanel();
  setStatus('workspace-status', 'No RUN loaded', 'idle');
  setIoRunStatus('No RUN loaded', 'idle');
  $('btn-apply').disabled = true;
  $('btn-open-active').disabled = true;
  $('btn-open-exports').disabled = true;
  if ($('btn-plc-use-active')) $('btn-plc-use-active').disabled = true;
  if ($('drop-filename')) {
    $('drop-filename').classList.add('hidden');
    $('drop-filename').textContent = '';
  }
  const devSel = $('device-template');
  if (devSel) devSel.innerHTML = '<option value="">Import a RUN package to list devices</option>';
  const detail = $('device-detail');
  if (detail) detail.textContent = '';
  updatePlcExportButtons();
  // Clear I/O banks + devices + merge/crosswalk (stale OCR must not linger)
  clearIoCompareState({ clearDevices: true });
}

/** Import RUN from I/O tab or Workspace — same backend. */
/**
 * Wipe ALL project-scoped site/engineer state before a new RUN loads.
 * Prevents Site A / Controller A caches from contaminating Site B.
 * Does NOT touch cosmetic UI prefs.
 */
function resetProjectScopedState({ reason = 'new RUN' } = {}) {
  // Subsystem editor configs
  try { autogenState.sawtooth = defaultSawtoothConfig(); } catch (_) { /* ignore */ }
  try { autogenState.sorter = defaultSorterConfig(); } catch (_) { /* ignore */ }
  try { autogenState.merges_2to1 = []; } catch (_) { /* ignore */ }
  try { autogenState.wcs = null; } catch (_) { /* ignore */ }
  try {
    if (autogenState.workbook) {
      delete autogenState.workbook.sawtooth_build;
      delete autogenState.workbook.sorter_build;
      delete autogenState.workbook.wcs;
      delete autogenState.workbook.transport_build;
      delete autogenState.workbook.transport_graph;
      autogenState.workbook.merges_2to1 = [];
      // Drop engineer Areas / Safety Zones / conveyor rows — rebuilt from new RUN
      autogenState.workbook.areas = [];
      autogenState.workbook.conveyors = [];
      if (autogenState.workbook.options && typeof autogenState.workbook.options === 'object') {
        autogenState.workbook.options.areas = [];
        autogenState.workbook.options.safety_zones = [];
      }
    }
  } catch (_) { /* ignore */ }

  // Compile-hub readiness — force NOT_DETECTED until current RUN re-detects
  try {
    autogenState.readiness = {
      hardware: emptyReadinessEntry(),
      transport: emptyReadinessEntry(),
      sawtooth: emptyReadinessEntry(),
      sorter: emptyReadinessEntry(),
      system: emptyReadinessEntry(),
      safety: emptyReadinessEntry(),
    };
    autogenState.lastGenerateIoMapError = null;
    autogenState.lastEsReport = null;
    autogenState.safety_build = null;
  } catch (_) { /* ignore */ }

  // Pack option checkboxes that were evidence-driven
  [
    'autogen-opt-merges-2to1',
    'autogen-opt-shippingsorter',
    'autogen-opt-shippingsorter-popup',
    'autogen-opt-sorter-track',
    'autogen-opt-sawtooth',
    'autogen-opt-wcs',
  ].forEach((id) => {
    try { if ($(id)) $(id).checked = false; } catch (_) { /* ignore */ }
  });

  // Project-scoped localStorage keys (identity + subsystem caches)
  [
    'fortna_sawtooth_build',
    'fortna_sorter_build',
    'fortna_merges_2to1',
    'fortna_wcs_build',
    'siteforge.transportBuild.v1',
    'siteforge.transportBuild.v2',
    'siteforge.safetyBuild.v1',
    'siteforge.wcsBuild.v1',
    'siteforge.projectIdentity',
    'fortna_last_equipment_names',
    'siteforge.ocrLastResult',
  ].forEach((k) => {
    try { localStorage.removeItem(k); } catch (_) { /* ignore */ }
  });
  try { autogenState.safetyDevices = []; } catch (_) { /* ignore */ }
  try { autogenState.wcs = null; } catch (_) { /* ignore */ }
  try { state.projectIdentity = null; } catch (_) { /* ignore */ }
  // Hardware I/O engineer overrides (name / Generate) — project-scoped
  try {
    if (typeof fortnaAPI?.clearHardwareIoOverrides === 'function') {
      fortnaAPI.clearHardwareIoOverrides({});
    }
  } catch (_) { /* ignore */ }
  // Global OCR cache must not alter another site's VFD/equipment selection
  try {
    if (typeof fortnaAPI?.clearOcrLastResult === 'function') {
      fortnaAPI.clearOcrLastResult({});
    }
  } catch (_) { /* ignore */ }

  // Transport canvas (Areas, Safety Zones, topology, selection, viewport)
  try {
    if (typeof window.transportBuildClearAll === 'function') {
      window.transportBuildClearAll({ leaveEmpty: true });
    }
  } catch (_) { /* ignore */ }

  // Re-render subsystem UIs empty
  try { renderSawtoothBuild(); } catch (_) { /* ignore */ }
  try { renderSorterBuild(); } catch (_) { /* ignore */ }
  try { renderMergeBuild(); } catch (_) { /* ignore */ }
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }

  log(`Project state reset (${reason}) — prior RUN subsystems cleared`, 'ok');
}

async function importRunPackage(path, name) {
  if (!path) return false;
  if (typeof fortnaAPI?.importRun !== 'function') {
    const msg = 'Site Forge API missing — relaunch via Launch-SiteForge.bat (not a browser tab).';
    log(msg, 'err');
    setIoRunStatus(msg, 'error');
    return false;
  }
  // Identity guard: always wipe prior project before importing a new archive
  resetProjectScopedState({ reason: `loading ${name || path}` });

  setBusy(true);
  setIoRunStatus(`Importing ${name || 'archive'}…`, 'busy');
  setStatus('workspace-status', 'Importing…', 'busy');
  log(`Importing ${name || path}…`, 'info');
  // CP5A: stream decoder progress into status (coarse — no thousands of messages)
  let unsubImportProgress = null;
  try {
    if (typeof fortnaAPI?.onImportProgress === 'function') {
      unsubImportProgress = fortnaAPI.onImportProgress((p) => {
        const phase = p?.phase || 'Decoder';
        const detail = p?.detail ? ` — ${p.detail}` : '';
        setIoRunStatus(`${phase}${detail}`, 'busy');
        setStatus('workspace-status', phase, 'busy');
      });
    }
  } catch (_) { /* ignore */ }
  let res;
  try {
    res = await fortnaAPI.importRun(path);
  } catch (e) {
    setBusy(false);
    const msg = (e && e.message) ? e.message : String(e || 'Import failed');
    log(msg, 'err');
    setStatus('workspace-status', 'Import failed', 'error');
    setIoRunStatus(msg, 'error');
    return false;
  }
  setBusy(false);
  try { if (typeof unsubImportProgress === 'function') unsubImportProgress(); } catch (_) { /* ignore */ }
  if (!res || !res.success) {
    log(res?.message || 'Import failed', 'err');
    setStatus('workspace-status', 'Import failed', 'error');
    setIoRunStatus(res?.message || 'Import failed', 'error');
    return false;
  }
  state.workspace = res.meta;
  // CP5A decoder result (isolated layer errors)
  try {
    const dec = res.decoder;
    if (dec && dec.ok === false) {
      const layer = dec.layer || 'CP5';
      log(`${layer} DECODER ERROR: ${dec.error || 'unknown'}`, 'warn');
    } else if (dec && dec.ok) {
      const tr = dec.adapters?.Transportation?.status || dec.cp4Status || '';
      const mt = dec.adapters?.Mtrchain?.status || '';
      log(
        `FortnaPlus decoder complete`
        + (tr ? ` · Transportation ${tr}` : '')
        + (mt ? ` · Mtrchain ${mt}` : ''),
        'ok',
      );
    }
  } catch (_) { /* ignore */ }
  // Stamp project identity so future restores can refuse cross-site contamination
  try {
    const identity = {
      machine: res.meta?.machine || '',
      run_fingerprint: res.meta?.run_fingerprint || '',
      archive: res.meta?.archive_name || res.meta?.export_name || name || '',
      loadedAt: new Date().toISOString(),
    };
    localStorage.setItem('siteforge.projectIdentity', JSON.stringify(identity));
    state.projectIdentity = identity;
  } catch (_) { /* ignore */ }
  if ($('drop-filename')) {
    $('drop-filename').textContent = name || path.split(/[/\\]/).pop();
    $('drop-filename').classList.remove('hidden');
  }
  const devCount = res.meta.device_count || res.meta.devices?.length || 0;
  const machine = res.meta.machine || 'RUN';
  const exportName = res.meta.export_name || res.meta.archive_stem || res.meta.source_label || '';
  log(`Loaded ${machine} — ${devCount} devices`, 'ok');
  if (exportName) {
    log(`Export label (from tar.gz): ${exportName}`, 'ok');
  }
  // PRISM auto-ingest status (deduped by RUN fingerprint)
  const prism = res.meta.prism || {};
  if (prism.skipped) {
    log(`PRISM: ${prism.message || 'same site already indexed — skipped'}`, 'info');
  } else if (prism.ok) {
    log(`PRISM: ${prism.message || `indexed site ${prism.site || exportName}`}`, 'ok');
  } else if (prism.error || prism.message) {
    log(`PRISM: ${prism.error || prism.message}`, 'warn');
  }
  setStatus('workspace-status', `${machine} loaded`, 'ready');
  setIoRunStatus(
    `${machine} loaded · ${devCount} devices`
    + (exportName ? ` · out=${exportName}` : ''),
    'ready',
  );
  updateWorkspacePanel();
  $('btn-apply').disabled = false;
  $('btn-open-active').disabled = false;
  $('btn-open-exports').disabled = false;
  if ($('btn-plc-use-active')) $('btn-plc-use-active').disabled = false;
  updatePlcExportButtons();
  try {
    await refreshDevices();
    await refreshConveyors();
  } catch (_) { /* optional if workspace tab widgets missing */ }
  await refreshIoBanks();
  // Keep PLC Autogen badge/status in sync with the newly loaded RUN
  try { await initAutogenDefaults(); } catch (_) { /* ignore */ }
  // Auto-fill site config (Area / Safety / TYPE / Exit PE dropdowns) from this RUN
  try {
    await ensureAutogenWorkbookFromRun({ force: true, reason: 'RUN loaded' });
  } catch (_) { /* workbook API may be unavailable in browser-only mode */ }
  // Canonical SiteModel → Sawtooth / Sorter / Transport editors (NO simulator button required)
  try {
    await applySiteModelToEditors({
      discovery: res.discovery || null,
      reason: 'RUN import',
    });
  } catch (e) {
    log(`SiteModel→editors: ${e?.message || e}`, 'warn');
  }
  // Fresh RUN must not keep a prior site-wide Transport canvas (localStorage).
  try {
    ['siteforge.transportBuild.v1', 'siteforge.transportBuild.v2'].forEach((k) => {
      try { localStorage.removeItem(k); } catch (_) { /* ignore */ }
    });
    if (typeof window.transportBuildClearAll === 'function') {
      window.transportBuildClearAll();
    }
    if (typeof window.transportBuildRefresh === 'function') {
      window.transportBuildRefresh();
    }
    log('Transport canvas cleared for new RUN', 'ok');
  } catch (e) {
    log(`Transport clear on import: ${e?.message || e}`, 'warn');
  }
  // Normal commissioning path: RUN load → parse → auto Transport layout (Top-Centered).
  // Engineer does not need to click Rebuild Layout.
  try {
    if (typeof window.transportAutoBuildFromRun === 'function') {
      log('Building Transportation from RUN…', 'info');
      const tbRes = await window.transportAutoBuildFromRun({ silent: true });
      if (tbRes?.ok) {
        log(tbRes.summary || 'Transportation built automatically from RUN · Top-Centered', 'ok');
      } else if (tbRes && !tbRes.cancelled) {
        log(`Transportation auto-build: ${tbRes.error || 'incomplete'} — use Rebuild Layout if needed`, 'warn');
      }
    } else {
      log('Transportation auto-build unavailable — use Rebuild Layout on Transport tab', 'warn');
    }
  } catch (e) {
    log(`Transportation auto-build: ${e?.message || e}`, 'warn');
  }
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  return true;
}

$('btn-clear-workspace')?.addEventListener('click', async () => {
  if (!confirm('Clear active workspace?\n\nThis removes the imported RUN from Site Forge (workspace/active).\nOriginal .tar.gz files on D:\\ are not deleted.')) {
    return;
  }
  setBusy(true);
  const res = await fortnaAPI.clearWorkspace();
  setBusy(false);
  if (!res.success) {
    log(res.message || 'Clear failed', 'err');
    return;
  }
  resetWorkspaceUi();
  log('Workspace cleared — no RUN loaded.', 'ok');
});

async function refreshConveyors() {
  const res = await fortnaAPI.listConveyors();
  if (res.success) {
    state.conveyors = res.conveyors || [];
    renderRecipeParams();
  }
}

function collectParams() {
  const params = {};
  if (state.selectedRecipeId === 'clone-device') {
    params.newName = ($('param-newName')?.value || '').trim();
    params.offsetX = parseFloat($('param-offsetX')?.value || '0') || 0;
    params.offsetY = parseFloat($('param-offsetY')?.value || '0') || 0;
    params.cloneRelated = $('param-cloneRelated')?.checked !== false;
    params.selectedDevice = state.selectedDevice;
    return params;
  }
  const recipe = state.recipes.find((r) => r.id === state.selectedRecipeId);
  if (!recipe?.params) return params;
  for (const p of recipe.params) {
    const el = $(`param-${p.name}`);
    if (el) params[p.name] = el.value.trim();
  }
  const conv = $('param-conveyor');
  if (conv) params.conveyor = conv.value.trim();
  return params;
}

$('btn-apply').addEventListener('click', async () => {
  if (!state.workspace) {
    log('Import a RUN package first.', 'warn');
    return;
  }
  const params = collectParams();
  if (state.selectedRecipeId === 'clone-device') {
    if (!params.selectedDevice) { log('Pick a template device from the RUN list.', 'warn'); return; }
    if (!params.newName) { log('Enter a new device name.', 'warn'); return; }
  }
  if (state.selectedRecipeId === 'add-photoeye' && !params.conveyor) {
    log('Pick a target conveyor.', 'warn');
    return;
  }
  setBusy(true);
  log(`Running recipe: ${state.selectedRecipeId}…`, 'info');
  const res = await fortnaAPI.applyRecipe({
    recipeId: state.selectedRecipeId,
    params,
    repack: true,
  });
  setBusy(false);
  if (!res.success) {
    log(res.message || 'Recipe failed', res.manual ? 'warn' : 'err');
    return;
  }
  const r = res.result || {};
  if (r.new_name) {
    const tables = (r.cloned || []).map((c) => c.table).join(', ');
    log(`Cloned ${r.template} → ${r.new_name} (${r.category}) in ${(r.cloned || []).length} row(s)`, 'ok');
    if (tables) log(`Tables: ${tables}`, 'info');
    await refreshDevices();
  }
  if (r.photoeye) {
    log(`Added ${r.photoeye} on ${r.conveyor} — I/O ${r.io_word}/${r.io_bit}`, 'ok');
  }
  if (r.export) {
    log(`Exported: ${r.export}`, 'ok');
    fortnaAPI.openPath(r.export);
  }
});

function setDocIndexStatus(count) {
  const n = Number(count) || 0;
  if ($('doc-count-label')) $('doc-count-label').textContent = String(n);
  if (n > 0) {
    setStatus('index-status', `${n} docs indexed`, 'ready');
  } else {
    // Explicit zero — not a leftover "99 docs" pill
    setStatus('index-status', '0 docs indexed', 'idle');
  }
}

async function init() {
  const idx = await fortnaAPI.getDocIndex();
  if (idx.success) {
    setDocIndexStatus(idx.count || 0);
  } else {
    setDocIndexStatus(0);
  }

  const recipes = await fortnaAPI.getRecipes();
  if (recipes.success) {
    state.recipes = recipes.recipes || [];
    renderRecipeList();
    renderRecipeParams();
  }

  const ws = await fortnaAPI.getWorkspace();
  if (ws.success && ws.active && ws.active.machine) {
    state.workspace = ws.active;
    updateWorkspacePanel();
    setStatus('workspace-status', `${ws.active.machine} loaded`, 'ready');
    setIoRunStatus(`${ws.active.machine} loaded`, 'ready');
    $('btn-apply').disabled = false;
    $('btn-open-active').disabled = false;
    $('btn-open-exports').disabled = false;
    if ($('btn-plc-use-active')) $('btn-plc-use-active').disabled = false;
    await refreshDevices();
    await refreshConveyors();
    await refreshIoBanks();
  } else {
    resetWorkspaceUi();
  }

  // Restore last PDF↔tar.gz compare if OCR finished previously
  if (typeof fortnaAPI.getLastOcr === 'function') {
    try {
      const last = await fortnaAPI.getLastOcr();
      if (last.success && last.result?.crosswalk) {
        ioState.ocrResult = last.result;
        // Normalize ocr array for summary (saved as ocr_summary)
        if (!ioState.ocrResult.ocr && last.result.ocr_summary) {
          ioState.ocrResult.ocr = last.result.ocr_summary.map((o) => ({
            file: o.file,
            pages_ocrd: o.pages_ocrd,
            token_count: o.token_count,
            panel: o.panel,
            error: o.error,
            vfd_param_count: o.vfd_param_count,
          }));
        }
        renderCrosswalk(ioState.ocrResult);
        ioLog(
          `Restored last OCR compare: ${last.result.crosswalk.matched_count || 0} matches `
          + `(${last.result.crosswalk.coverage_pct || 0}% coverage).`,
          'ok'
        );
      }
    } catch (_) { /* ignore */ }
  }
  updateRecontrolReady();
}

// --- PLC Export tab ---
const plcState = {
  /** @type {string[]} */
  queue: [],
  busy: false,
  lastResult: null,
  /** @type {Array<{path:string, ok:boolean, result?:object, error?:string}>} */
  batchResults: [],
};

function isRunArchivePath(p) {
  return !!p && /\.(tar\.gz|tgz|tar|gz|zip)$/i.test(p);
}

function archiveBaseName(p) {
  return (p || '').split(/[/\\]/).pop() || p;
}

function plcLog(msg, level = 'info') {
  const el = $('plc-activity-log');
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  const colors = { info: 'text-slate-400', ok: 'text-emerald-400', err: 'text-red-400', warn: 'text-amber-400' };
  const line = document.createElement('div');
  line.className = colors[level] || colors.info;
  line.textContent = `[${ts}] ${msg}`;
  el.prepend(line);
}

function setPlcStatus(text, kind) {
  const el = $('plc-export-status');
  if (!el) return;
  el.textContent = text;
  el.className = `status-pill status-${kind}`;
}

function updatePlcExportButtons() {
  // Export uses active RUN from I/O & Prints only (no separate tar.gz queue)
  if ($('btn-plc-use-active')) $('btn-plc-use-active').disabled = plcState.busy || !state.workspace;
  try {
    if (typeof updateRecontrolReady === 'function' && typeof ioState !== 'undefined') {
      updateRecontrolReady();
    }
  } catch (_) { /* ignore early-init */ }
}

function renderPlcQueue() {
  const list = $('plc-queue-list');
  const count = $('plc-queue-count');
  if (count) count.textContent = `${plcState.queue.length} file${plcState.queue.length === 1 ? '' : 's'}`;
  if (!list) return;
  if (!plcState.queue.length) {
    list.innerHTML = '<div class="italic text-slate-500">No archives queued — drop or browse .tar.gz files</div>';
    updatePlcExportButtons();
    return;
  }
  list.innerHTML = plcState.queue.map((p, i) => `
    <div class="flex items-center gap-2 bg-[#101820] border border-slate-800 rounded-lg px-2 py-1.5">
      <span class="text-cyan-500 mono text-[10px] w-5">${i + 1}.</span>
      <span class="flex-1 mono text-[11px] text-slate-300 truncate" title="${p}">${archiveBaseName(p)}</span>
      <button type="button" class="plc-queue-remove text-slate-500 hover:text-red-400 px-1" data-idx="${i}" title="Remove">
        <i class="fa-solid fa-xmark text-[10px]"></i>
      </button>
    </div>
  `).join('');
  list.querySelectorAll('.plc-queue-remove').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx, 10);
      if (!Number.isNaN(idx)) {
        plcState.queue.splice(idx, 1);
        renderPlcQueue();
      }
    });
  });
  updatePlcExportButtons();
}

/** Add one or more paths to the PLC export queue (deduped). */
function addPlcArchives(paths) {
  const list = (Array.isArray(paths) ? paths : [paths]).filter(Boolean);
  let added = 0;
  for (const p of list) {
    if (!isRunArchivePath(p)) {
      plcLog(`Skipped (not a RUN archive): ${archiveBaseName(p)}`, 'warn');
      continue;
    }
    if (plcState.queue.includes(p)) {
      plcLog(`Already in queue: ${archiveBaseName(p)}`, 'warn');
      continue;
    }
    plcState.queue.push(p);
    added += 1;
    plcLog(`Queued: ${archiveBaseName(p)}`, 'info');
  }
  renderPlcQueue();
  return added;
}

function clearPlcQueue() {
  plcState.queue = [];
  renderPlcQueue();
  plcLog('Queue cleared', 'info');
}

function renderPlcResult(result) {
  const summary = $('plc-export-summary');
  const statsBox = $('plc-export-stats');
  const filesBox = $('plc-export-files');
  if (!summary || !filesBox) return;

  if (!result?.ok) {
    summary.textContent = result?.error || 'Export failed.';
    statsBox?.classList.add('hidden');
    filesBox.innerHTML = '';
    return;
  }

  const fioN = result.fio_object_count != null ? result.fio_object_count : '—';
  summary.innerHTML = `<span class="text-emerald-400 font-semibold">${result.system}</span> — ${result.tag_count} tags, ${result.program_count} programs, <span class="text-cyan-300">${fioN} Factory I/O objects</span>`;
  if (statsBox && result.stats) {
    statsBox.classList.remove('hidden');
    const s = result.stats;
    statsBox.innerHTML = [
      ['Total I/O', s.total],
      ['Inputs', s.inputs],
      ['Outputs', s.outputs],
      ['With layout', s.with_coords],
      ['FIO objects', fioN],
    ].map(([k, v]) => `<div class="bg-[#101820] border border-slate-800 rounded-lg px-3 py-2 text-xs"><div class="text-slate-500">${k}</div><div class="text-lg font-semibold text-cyan-300">${v}</div></div>`).join('');
  }

  const files = { ...(result.files || {}) };
  if (result.prism_seed?.files) {
    files.prism_prompt = result.prism_seed.files.prompt;
    files.prism_seeded_dir = result.prism_seed.files.seeded_dir;
  }
  if (result.out_dir) files.out_dir = result.out_dir;
  filesBox.innerHTML = Object.entries(files).map(([key, fpath]) => `
    <button class="w-full text-left doc-hit rounded-lg px-3 py-2 text-sm flex items-center justify-between plc-open-file" data-path="${fpath}">
      <span><i class="fa-solid fa-file-code mr-2 text-cyan-500"></i>${key}: <span class="mono text-xs text-slate-400">${String(fpath).split(/[/\\]/).pop()}</span></span>
      <i class="fa-solid fa-arrow-up-right-from-square text-slate-500 text-xs"></i>
    </button>
  `).join('');

  filesBox.querySelectorAll('.plc-open-file').forEach((btn) => {
    btn.addEventListener('click', () => fortnaAPI.openPath(btn.dataset.path));
  });
}

function renderPlcBatchSummary(results) {
  const summary = $('plc-export-summary');
  const filesBox = $('plc-export-files');
  if (!summary || !filesBox) return;
  const ok = results.filter((r) => r.ok);
  const bad = results.filter((r) => !r.ok);
  summary.innerHTML = `
    <div class="space-y-1">
      <div><span class="text-emerald-400 font-semibold">Batch complete</span> — ${ok.length} ok, ${bad.length} failed of ${results.length}</div>
      <div class="text-xs text-slate-500">Each machine writes its own folder under <span class="mono">exports/plc/</span></div>
    </div>`;
  filesBox.innerHTML = results.map((r) => {
    const name = archiveBaseName(r.path);
    if (r.ok && r.result) {
      const out = r.result.out_dir || r.result.files?.l5x || '';
      return `<button class="w-full text-left doc-hit rounded-lg px-3 py-2 text-sm flex items-center justify-between plc-open-file" data-path="${out}">
        <span><i class="fa-solid fa-circle-check text-emerald-400 mr-2"></i>
          <span class="font-medium">${r.result.system || name}</span>
          <span class="mono text-xs text-slate-400 ml-2">${r.result.tag_count || 0} tags · ${r.result.fio_object_count != null ? r.result.fio_object_count : '—'} FIO</span>
        </span>
        <i class="fa-solid fa-folder-open text-slate-500 text-xs"></i>
      </button>`;
    }
    return `<div class="rounded-lg px-3 py-2 text-sm border border-red-900/50 bg-red-950/30 text-red-300">
      <i class="fa-solid fa-circle-xmark mr-2"></i>${name}: ${r.error || 'failed'}
    </div>`;
  }).join('');
  filesBox.querySelectorAll('.plc-open-file').forEach((btn) => {
    btn.addEventListener('click', () => fortnaAPI.openPath(btn.dataset.path));
  });
}

async function exportOneArchive(archivePath) {
  const payload = {
    mode: 'archive',
    archivePath,
    includeSpares: $('plc-include-spares')?.checked || false,
    prismSeed: $('plc-prism-seed')?.checked || false,
    // 0 = complete Factory I/O scene (all I/O points)
    maxFio: 0,
  };
  const res = await fortnaAPI.exportPlc(payload);
  if (!res.success) {
    return { path: archivePath, ok: false, error: res.message || 'Export failed' };
  }
  return { path: archivePath, ok: true, result: res.result };
}

async function runPlcExportQueue() {
  if (plcState.busy) return;
  if (!plcState.queue.length) {
    plcLog('Queue is empty — drop or browse RUN archives first.', 'warn');
    return;
  }

  plcState.busy = true;
  updatePlcExportButtons();
  const total = plcState.queue.length;
  const results = [];
  setPlcStatus(`Exporting 0/${total}…`, 'busy');
  plcLog(`Starting batch export of ${total} archive(s)…`, 'info');

  for (let i = 0; i < plcState.queue.length; i++) {
    const p = plcState.queue[i];
    setPlcStatus(`Exporting ${i + 1}/${total}…`, 'busy');
    plcLog(`[${i + 1}/${total}] ${archiveBaseName(p)}…`, 'info');
    try {
      const r = await exportOneArchive(p);
      results.push(r);
      if (r.ok) {
        plcLog(`  OK ${r.result.system}: ${r.result.tag_count} tags → ${r.result.out_dir}`, 'ok');
        plcState.lastResult = r.result;
      } else {
        plcLog(`  FAIL ${archiveBaseName(p)}: ${r.error}`, 'err');
      }
    } catch (e) {
      results.push({ path: p, ok: false, error: e.message || String(e) });
      plcLog(`  FAIL ${archiveBaseName(p)}: ${e.message}`, 'err');
    }
  }

  plcState.busy = false;
  plcState.batchResults = results;
  updatePlcExportButtons();

  const okCount = results.filter((r) => r.ok).length;
  const failCount = results.length - okCount;
  if (failCount === 0) {
    setPlcStatus(`Complete ${okCount}/${total}`, 'ready');
  } else if (okCount === 0) {
    setPlcStatus('All failed', 'error');
  } else {
    setPlcStatus(`${okCount} ok / ${failCount} failed`, 'warn');
  }

  if (results.length === 1 && results[0].ok) {
    renderPlcResult(results[0].result);
    // Folder only — never open .L5X (that launches Studio 5000)
    const outDir = results[0].result?.out_dir || 'exports/plc';
    if (typeof fortnaAPI.openPath === 'function') fortnaAPI.openPath(outDir);
    plcLog('Package written — Studio not launched. Open the .L5X yourself when ready.', 'info');
  } else {
    renderPlcBatchSummary(results);
    if (typeof fortnaAPI.openPath === 'function') fortnaAPI.openPath('exports/plc');
  }
  plcLog(`Batch done: ${okCount} succeeded, ${failCount} failed.`, okCount ? 'ok' : 'err');
}

async function runPlcExportActive() {
  if (plcState.busy) return;
  if (!state.workspace) {
    plcLog('No active workspace — import a RUN on the Workspace tab first.', 'warn');
    return;
  }
  plcState.busy = true;
  updatePlcExportButtons();
  setPlcStatus('Exporting active…', 'busy');
  plcLog('Exporting from active workspace…', 'info');

  const payload = {
    mode: 'active',
    includeSpares: $('plc-include-spares')?.checked || false,
    prismSeed: $('plc-prism-seed')?.checked || false,
    maxFio: 0,
  };
  const res = await fortnaAPI.exportPlc(payload);
  plcState.busy = false;
  updatePlcExportButtons();

  if (!res.success) {
    setPlcStatus('Error', 'error');
    plcLog(res.message || 'Export failed', 'err');
    renderPlcResult({ ok: false, error: res.message });
    return;
  }

  plcState.lastResult = res.result;
  setPlcStatus('Complete', 'ready');
  plcLog(`Exported ${res.result.tag_count} tags → ${res.result.out_dir}`, 'ok');
  if (res.result.prism_seed?.seeded_routines?.length) {
    plcLog(`PRISM PoC: ${res.result.prism_seed.seeded_routines.length} seeded routines`, 'ok');
  }
  renderPlcResult(res.result);
  // Folder only — never open .L5X (Studio auto-launch)
  if (res.result?.out_dir && typeof fortnaAPI.openPath === 'function') {
    fortnaAPI.openPath(res.result.out_dir);
  }
  plcLog('Package written — Studio not launched. Open the .L5X yourself when ready.', 'info');
}

// PLC Export uses active RUN from I/O & Prints — no drop zone / multi-queue on this tab.
$('btn-plc-use-active')?.addEventListener('click', () => runPlcExportActive());

// --- I/O banks + prints OCR ---
const ioState = {
  /** @type {Array<{id:string,name:string,role:string,paths:string[]}>} */
  panelSets: [],
  activePanelId: '',
  banks: null,
  /** Hardware/I/O model from PhysicalWordResolver (via fortna_hardware_io_model) */
  hardwareIo: null,
  hardwarePanelFilter: '__all__',
  hardwareRioFilter: '__all__',
  /** Hardware tree: Set of expanded AENT rio_name keys (click AENT to expand modules) */
  hardwareTreeExpanded: null,
  selectedHwModuleKey: '',
  selectedHwChannel: null,
  /** @type {Array<object>} */
  drives: [],
  /** Unified device list (I/O points + drives) for type filter browser */
  devices: [],
  motorChains: [],
  printVfdParams: [],
  selectedDriveName: '',
  deviceTypeFilter: 'all',
  ocrResult: null,
  crosswalkTab: 'matched',
  busy: false,
};

/**
 * Classify device by name prefix / program class.
 * PE… photo eye, M… motor, VFD… drive, ESL… e-stop, etc.
 */
function classifyDevice(name, deviceClass, extra) {
  const raw = String(name || '').trim();
  const n = raw.toUpperCase().replace(/^IO[_-]?/, '');
  const cls = String(deviceClass || extra?.device_type || extra?.equipment_kind || '').toLowerCase();
  const desc = String(extra?.description || '');

  // Order matters — site conventions:
  //   VFD500A = VFD · M100 = motor · EZPWS = power supply · EZPE/PE = photoeye · P100 = conveyor
  // P### is ALWAYS conveyor — never VFD (even if Drive="1" or desc mentions VFD).
  const rules = [
    { key: 'power_supply', label: 'Power Supply (EZPWS)', test: () =>
      /^EZPWS/i.test(n) || /^PWS/i.test(n) || cls === 'powersupply' || cls.includes('power_supply')
      || /power\s*supply/i.test(desc) },
    { key: 'conveyor', label: 'Conveyor (P…)', test: () =>
      /^P\d/.test(n) || cls === 'conveyor' },
    { key: 'vfd', label: 'VFD', test: () =>
      // Explicit VFD tags only — not P###, not bare "is_vfd" from Drive=1
      (/^VFD\d/i.test(n) || /^VFD_/i.test(n) || /^PF\d/i.test(n)
        || (cls === 'vfd' && !/^P\d/.test(n))
        || (extra?.is_vfd === true && /^VFD/i.test(n))
        || /\bVFD\d{2,}/i.test(n))
      && !/^P\d/.test(n) },
    { key: 'photoeye', label: 'Photo Eye (PE)', test: () =>
      /^(EZPE|PE)\d/i.test(n) || cls.includes('photo') || cls === 'photoeye'
      || /photo\s*eye|photocell/i.test(desc) },
    { key: 'motor', label: 'Motor contactor (M)', test: () =>
      (/^M\d/.test(n) && !/^MCR/i.test(n)) || cls === 'motor' },
    { key: 'estop', label: 'E-Stop / ESL', test: () =>
      /^(ESL|ES\d|ESTOP|ESR)/.test(n) || /e-?stop|pull cord/i.test(desc) },
    { key: 'pushbutton', label: 'Pushbutton (PB)', test: () =>
      /(^|\d)PB(START|STOP)/.test(n) || /push\s*button/i.test(desc) },
    { key: 'beacon', label: 'Beacon / Horn (WH)', test: () =>
      /^(WH|BCN|BEACON)/.test(n) || cls === 'beacon' },
    { key: 'encoder', label: 'Encoder (ENC)', test: () => /^ENC/.test(n) },
    { key: 'scanner', label: 'Scanner', test: () => /^(SCN|SCAN)/.test(n) || cls === 'scanner' },
    { key: 'prox', label: 'Prox', test: () => /^(PRX|PROX|PX)/.test(n) || cls.includes('prox') },
    { key: 'solenoid', label: 'Solenoid / Valve', test: () => /^(SOL|SV|VALVE)/.test(n) },
    { key: 'digital_in', label: 'Digital Input', test: () => cls.includes('digitalinput') || cls === 'in' },
    { key: 'digital_out', label: 'Digital Output', test: () => cls.includes('digitaloutput') || cls === 'out' },
  ];
  for (const r of rules) {
    try {
      if (r.test()) return { key: r.key, label: r.label };
    } catch (_) { /* continue */ }
  }
  if (cls && cls !== 'invalid' && cls !== 'n/a') {
    return { key: cls.replace(/\s+/g, '_').slice(0, 24), label: deviceClass || cls };
  }
  return { key: 'other', label: 'Other' };
}

/**
 * Resolve Print # for the device list.
 * VFDs: only pages discovered by PDF OCR (never conveyor layout pages from ASC).
 * Other devices: ASC drawing page map is OK.
 */
function resolveDevicePrintPage(name, fallback, { fromOcr = false, isVfd = false } = {}) {
  if (isVfd || /^VFD\d/i.test(String(name || ''))) {
    // VFD print links only when OCR attached a real PDF page
    if (fromOcr && fallback != null && fallback !== '' && Number(fallback) > 0) {
      return Number(fallback);
    }
    return null;
  }
  if (fallback != null && fallback !== '' && Number(fallback) > 0) {
    return Number(fallback);
  }
  const map = ioState.banks?.print_pages || ioState.printPages || {};
  if (!name) return null;
  const raw = String(name).trim();
  const upper = raw.toUpperCase();
  for (const c of [raw, upper, raw.toLowerCase()]) {
    const hit = map[c];
    if (hit != null && Number(hit) > 0) return Number(hit);
  }
  return null;
}

/** Build unified device cards from banks points + drive rows. */
function rebuildDeviceList() {
  const byName = new Map();
  const banks = ioState.banks?.banks || [];
  // Keep full ASC page map on ioState for detail views / OCR merge
  if (ioState.banks?.print_pages) {
    ioState.printPages = ioState.banks.print_pages;
  }
  for (const b of banks) {
    for (const p of b.points || []) {
      const name = p.fortna_name || p.tag || '';
      if (!name) continue;
      const type = classifyDevice(name, p.device_class, { description: p.description });
      const isVfd = type.key === 'vfd' || /^VFD\d/i.test(name);
      // Bank I/O points alone never get VFD print # (need OCR merge via drives)
      const page = resolveDevicePrintPage(
        name,
        p.drawing_page || p.print_page || null,
        { fromOcr: false, isVfd },
      );
      byName.set(name.toUpperCase(), {
        name,
        typeKey: type.key,
        typeLabel: type.label,
        device_class: p.device_class || '',
        description: p.description || '',
        io_address: p.address || '',
        io_type: p.io_type || '',
        bank: b.bank,
        source: 'io',
        drive: '',
        speed: '',
        print_param_count: 0,
        print_param_list: [],
        print_params: {},
        program_params: {},
        drawing_page: page,
        print_file: '',
        print_page: page,
        machine_name: p.machine_name || '',
        is_vfd: isVfd,
        vfd_from_print: false,
      });
    }
  }
  // Index OCR print params + page by VFD base so AUX/EN siblings can share
  // Prefer rows that already have a Python-assigned print_page.
  const printByVfdBase = new Map();
  for (const d of ioState.drives || []) {
    const nm = d.name || '';
    if (!/^VFD\d/i.test(nm)) continue;
    const base = nm.toUpperCase().replace(/(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$/i, '');
    const list = filterVfdPrintParamsClient(
      d.print_param_list || Object.values(d.print_params || {}),
    );
    const page = d.print_page || d.drawing_page || null;
    if (!list.length && page == null && !d.vfd_from_print) continue;
    const prev = printByVfdBase.get(base);
    const score = (page != null ? 100 : 0) + list.length;
    const prevScore = prev ? ((prev.page != null ? 100 : 0) + (prev.list?.length || 0)) : -1;
    if (!prev || score >= prevScore) {
      printByVfdBase.set(base, {
        list,
        params: d.print_params || {},
        sources: d.print_sources || [],
        file: d.print_file || '',
        page: page != null ? Number(page) : null,
      });
    }
  }

  for (const d of ioState.drives || []) {
    const name = d.name || '';
    if (!name) continue;
    const key = name.toUpperCase();
    const type = classifyDevice(name, d.equipment_kind || d.device_type || d.device_class, d);
    const existing = byName.get(key);
    let cleanedPrint = filterVfdPrintParamsClient(
      d.print_param_list || Object.values(d.print_params || {}),
    );
    // Inherit OCR table from VFD444 onto VFD444_AUX / _EN when only one side has params
    const vfdBase = key.replace(/(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$/i, '');
    const shared = printByVfdBase.get(vfdBase);
    if ((!cleanedPrint || !cleanedPrint.length) && shared?.list?.length) {
      cleanedPrint = shared.list;
    }
    const isVfd = type.key === 'vfd' || (/^VFD/i.test(name) && !/^P\d/i.test(name));
    // Prefer this row's Python page; only fall back to sibling base page
    const ownPage = d.print_page || d.drawing_page || null;
    const fromOcr = !!(
      d.vfd_from_print
      || cleanedPrint.length
      || ownPage != null
      || (d.print_sources && d.print_sources.length)
      || shared?.page != null
      || shared?.list?.length
    );
    // VFD Print # = OCR PDF page only (never conveyor layout page from RUN)
    const page = resolveDevicePrintPage(
      name,
      fromOcr ? (ownPage != null ? ownPage : (shared?.page || null)) : null,
      { fromOcr, isVfd },
    );
    const merged = {
      ...(existing || {}),
      name,
      typeKey: type.key === 'other' && existing ? existing.typeKey : type.key,
      typeLabel: type.key === 'other' && existing ? existing.typeLabel : type.label,
      device_class: d.device_type || d.device_class || existing?.device_class || '',
      description: d.description || existing?.description || '',
      io_address: d.io_address || existing?.io_address || '',
      drive: d.drive || '',
      speed: d.speed || '',
      motor: d.motor || '',
      machine_name: d.machine_name || existing?.machine_name || '',
      print_param_count: cleanedPrint.length || d.print_param_count || 0,
      print_param_list: cleanedPrint.length ? cleanedPrint : (d.print_param_list || []),
      print_params: (d.print_params && Object.keys(d.print_params).length)
        ? d.print_params
        : (shared?.params || {}),
      print_sources: (d.print_sources && d.print_sources.length)
        ? d.print_sources
        : (shared?.sources || []),
      program_params: d.program_params || {},
      drawing_page: page,
      print_file: fromOcr ? (d.print_file || shared?.file || existing?.print_file || '') : '',
      print_page: page,
      // is_vfd only for real VFD### names — never P### conveyors
      is_vfd: isVfd,
      vfd_from_print: fromOcr && isVfd,
      source: existing ? 'both' : 'drive',
    };
    // Hard rules: P### = conveyor; VFD### = VFD; never promote EZPWS / P### to VFD
    if (/^P\d/i.test(name)) {
      merged.typeKey = 'conveyor';
      merged.typeLabel = 'Conveyor (P…)';
      merged.is_vfd = false;
    } else if (/^VFD\d/i.test(name) || type.key === 'vfd') {
      merged.typeKey = 'vfd';
      merged.typeLabel = 'VFD';
      merged.is_vfd = true;
    }
    byName.set(key, merged);
  }
  // Cache ENC* names for Sorter build encoder dropdown (prefix ENC = encoder)
  try {
    const encNames = [...byName.values()]
      .map((d) => d.name || d.fortna_name || '')
      .filter((n) => /^ENC\d/i.test(n) || /^T_\d*ENC\d/i.test(n));
    localStorage.setItem('fortna_last_equipment_names', JSON.stringify(encNames));
    if (autogenState.workbook) {
      autogenState.workbook.encoder_devices = encNames;
    }
  } catch (_) { /* ignore */ }
  ioState.devices = [...byName.values()].sort((a, b) =>
    a.typeLabel.localeCompare(b.typeLabel) || a.name.localeCompare(b.name)
  );
  populateDeviceTypeFilter();
}

function populateDeviceTypeFilter() {
  const sel = $('device-type-filter');
  if (!sel) return;
  const prev = ioState.deviceTypeFilter || sel.value || 'all';
  const counts = new Map();
  for (const d of ioState.devices) {
    counts.set(d.typeKey, (counts.get(d.typeKey) || 0) + 1);
  }
  const opts = [['all', `All devices (${ioState.devices.length})`]];
  const order = ['vfd', 'motor', 'power_supply', 'photoeye', 'conveyor', 'estop', 'pushbutton', 'beacon', 'encoder', 'scanner', 'prox', 'solenoid', 'digital_in', 'digital_out', 'other'];
  const keys = [...counts.keys()].sort((a, b) => {
    const ia = order.indexOf(a); const ib = order.indexOf(b);
    if (ia >= 0 || ib >= 0) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    return a.localeCompare(b);
  });
  for (const k of keys) {
    const sample = ioState.devices.find((d) => d.typeKey === k);
    opts.push([k, `${sample?.typeLabel || k} (${counts.get(k)})`]);
  }
  sel.innerHTML = opts.map(([v, lab]) =>
    `<option value="${escapeHtml(v)}">${escapeHtml(lab)}</option>`
  ).join('');
  if ([...counts.keys(), 'all'].includes(prev)) {
    sel.value = prev;
    ioState.deviceTypeFilter = prev;
  } else {
    sel.value = 'all';
    ioState.deviceTypeFilter = 'all';
  }
}

function updateRecontrolReady() {
  // Guard: called from PLC UI before/without full I/O state
  if (typeof ioState === 'undefined' || !ioState) return;
  const hasRun = !!(state.workspace || ioState.banks?.machine);
  const printFiles = typeof totalPrintFiles === 'function' ? totalPrintFiles() : 0;
  const hasPrints = printFiles > 0;
  const hasOcr = !!(ioState.ocrResult?.crosswalk);
  const matchN = ioState.ocrResult?.crosswalk?.matched_count || 0;
  // Tar alone is enough to export L5X; prints/OCR are optional (VFD PRINT column).
  const ready = hasRun;

  const list = $('plc-ready-checklist');
  if (list) {
    const row = (ok, text) =>
      `<div class="${ok ? 'text-emerald-400' : 'text-slate-500'}">${ok ? '✓' : '○'} ${text}</div>`;
    list.innerHTML = [
      row(hasRun, `RUN tar.gz loaded${ioState.banks?.machine ? ` (${ioState.banks.machine})` : state.workspace?.machine ? ` (${state.workspace.machine})` : ''}`),
      row(hasPrints, `Print PDFs (${printFiles}) — optional for OCR`),
      row(hasOcr, hasOcr ? `OCR compare done (${matchN} matches)` : 'OCR not run yet (optional)'),
    ].join('');
  }

  const btn = $('btn-plc-generate');
  if (btn) {
    btn.disabled = !ready || plcState.busy;
    if (ready && !plcState.busy) {
      btn.className = 'w-full py-3 rounded-xl text-sm font-semibold border-2 border-emerald-500 bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/40 cursor-pointer transition';
      btn.innerHTML = '<i class="fa-solid fa-file-export mr-2"></i>Export PLC Package';
      btn.title = 'Write L5X + Factory I/O under exports/plc — does not launch Studio';
    } else {
      btn.className = 'w-full py-3 rounded-xl text-sm font-semibold border-2 border-slate-700 bg-slate-900 text-slate-500 cursor-not-allowed';
      btn.innerHTML = '<i class="fa-solid fa-file-export mr-2"></i>Export PLC Package';
      btn.title = 'Load a .tar.gz RUN first';
    }
  }
}

function ioLog(msg, level = 'info') {
  log(msg, level);
}

function uidPanel() {
  return 'p_' + Math.random().toString(36).slice(2, 9);
}

function getActivePanel() {
  return ioState.panelSets.find((p) => p.id === ioState.activePanelId) || null;
}

function getMasterPanel() {
  return ioState.panelSets.find((p) => p.role === 'master') || null;
}

function getRemotePanels() {
  return ioState.panelSets.filter((p) => p.role === 'remote');
}

function totalPrintFiles() {
  return ioState.panelSets.reduce((n, p) => n + (p.paths?.length || 0), 0);
}

function panelFileNames(p) {
  return (p.paths || []).map((path) => String(path).split(/[/\\]/).pop());
}

function renderPanelCard(p, { active }) {
  const isMaster = p.role === 'master';
  const border = active
    ? (isMaster ? 'border-emerald-500 bg-emerald-950/40' : 'border-sky-500 bg-sky-950/40')
    : (isMaster ? 'border-emerald-900/50 bg-emerald-950/15' : 'border-slate-800 bg-[#101820]');
  const files = panelFileNames(p);
  const fileLine = files.length
    ? files.map((f) => `<div class="truncate text-slate-500" title="${escapeHtml(f)}">· ${escapeHtml(f)}</div>`).join('')
    : '<div class="text-slate-600 italic">no PDFs yet</div>';
  return `
    <div class="rounded-lg border px-2 py-1.5 cursor-pointer ${border}"
         data-panel-id="${p.id}" data-panel-role="${p.role}">
      <div class="flex items-center gap-2">
        <div class="flex-1 min-w-0">
          <div class="font-semibold text-slate-200 truncate">${escapeHtml(p.name)}</div>
          <div class="text-[10px] ${isMaster ? 'text-emerald-400' : 'text-sky-400'}">
            ${isMaster ? 'Master · local I/O' : 'Remote I/O'} · ${p.paths.length} PDF(s)
          </div>
        </div>
        <button type="button" class="panel-remove text-slate-600 hover:text-red-400 px-1" data-remove="${p.id}" title="Remove">
          <i class="fa-solid fa-xmark text-[10px]"></i>
        </button>
      </div>
      <div class="mt-1 text-[10px] mono leading-snug max-h-14 overflow-y-auto">${fileLine}</div>
    </div>`;
}

/** Stem of a print path → panel name (CP3.pdf → CP3). */
function panelNameFromPath(p) {
  const base = String(p || '').split(/[/\\]/).pop() || 'Panel';
  return base.replace(/\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i, '') || base;
}

/**
 * Add remote print files, keeping them separate from master.
 * Multi-file drops create one remote panel per file (named from filename)
 * unless a specific remote panel is already targeted.
 */
function addRemotePrintPaths(paths, targetPanel) {
  const prints = (paths || []).filter((p) => p && isPrintPath(p));
  if (!prints.length) {
    ioLog('No print PDFs in drop.', 'warn');
    return 0;
  }

  // Explicit target remote: all files go there
  if (targetPanel && targetPanel.role === 'remote') {
    return addPrintPaths(prints, targetPanel);
  }

  // Named input with single or multi: if user typed a name and only one remote intent, use it
  const typed = ($('remote-name-input')?.value || '').trim();
  if (typed && prints.length === 1) {
    const panel = addRemotePanel(typed);
    if ($('remote-name-input')) $('remote-name-input').value = '';
    return addPrintPaths(prints, panel);
  }

  // Default multi-drop: one remote panel per PDF, named from file (CP1, CP2, …)
  // Never attach to master.
  let added = 0;
  for (const path of prints) {
    const name = panelNameFromPath(path);
    let panel = ioState.panelSets.find(
      (p) => p.role === 'remote' && p.name.toLowerCase() === name.toLowerCase()
    );
    if (!panel) {
      // Avoid colliding with master name
      const master = getMasterPanel();
      if (master && master.name.toLowerCase() === name.toLowerCase()) {
        panel = addRemotePanel(`${name}-remote`);
      } else {
        panel = addRemotePanel(name);
      }
    }
    added += addPrintPaths([path], panel);
  }
  if (typed && $('remote-name-input')) $('remote-name-input').value = '';
  ioLog(`Remotes updated: ${getRemotePanels().length} panel(s), separate from master.`, 'ok');
  return added;
}

function bindPanelListClicks(container) {
  if (!container) return;
  container.querySelectorAll('[data-panel-id]').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-remove]')) return;
      ioState.activePanelId = el.dataset.panelId;
      renderPanelSets();
    });
  });
  container.querySelectorAll('[data-remove]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.remove;
      ioState.panelSets = ioState.panelSets.filter((p) => p.id !== id);
      if (ioState.activePanelId === id) {
        ioState.activePanelId = ioState.panelSets[0]?.id || '';
      }
      renderPanelSets();
      // If no print PDFs left, wipe stale merge/crosswalk
      if (totalPrintFiles() === 0 && ioState.ocrResult) {
        clearIoCompareState({ clearPanels: false });
        ioLog('All print PDFs removed — merge/crosswalk cleared.', 'info');
      }
    });
  });
}

function renderPanelSets() {
  const masterCard = $('master-panel-card');
  const remoteList = $('remote-panels-list');
  const remoteCount = $('remote-panel-count');
  const master = getMasterPanel();
  const remotes = getRemotePanels();
  // Keep PLC green-button checklist in sync when prints change
  try { updateRecontrolReady(); } catch (_) { /* early init */ }

  if (remoteCount) remoteCount.textContent = `${remotes.length} panel${remotes.length === 1 ? '' : 's'}`;
  // Auto-expand prints when panels exist; leave collapsed when empty (tar.gz is enough)
  const printsDetails = $('remote-prints-details');
  if (printsDetails && remotes.length > 0) printsDetails.open = true;

  if (masterCard) {
    if (!master) {
      masterCard.innerHTML = '<div class="text-slate-600 italic">Drop master PDF(s) here only — remotes use the blue card.</div>';
    } else {
      masterCard.innerHTML = renderPanelCard(master, { active: master.id === ioState.activePanelId });
      bindPanelListClicks(masterCard);
    }
  }
  const masterFiles = $('master-file-list');
  if (masterFiles) {
    if (!master || !master.paths.length) {
      masterFiles.innerHTML = '';
    } else {
      masterFiles.innerHTML = master.paths.map((path) => {
        const name = String(path).split(/[/\\]/).pop();
        return `<div class="truncate" title="${escapeHtml(path)}">· ${escapeHtml(name)}</div>`;
      }).join('');
    }
  }

  if (remoteList) {
    if (!remotes.length) {
      remoteList.innerHTML = '<div class="text-slate-600 italic">Drop CP1.pdf, CP2.pdf… here — each file becomes its own remote (not master).</div>';
    } else {
      remoteList.innerHTML = remotes.map((p) => renderPanelCard(p, { active: p.id === ioState.activePanelId })).join('');
      bindPanelListClicks(remoteList);
    }
  }

  const active = getActivePanel();
  if ($('prints-active-label')) {
    if (!active) {
      $('prints-active-label').textContent = 'Select master or a remote panel first';
    } else {
      $('prints-active-label').textContent = active.role === 'master'
        ? `Active: ${active.name} (MASTER) — drop local rack prints`
        : `Active: ${active.name} (REMOTE) — drop remote I/O / VFD / conveyor prints`;
    }
  }
  if ($('btn-run-ocr')) {
    $('btn-run-ocr').disabled = ioState.busy || totalPrintFiles() === 0;
  }
  renderPrintsList();
}

function renderPrintsList() {
  const el = $('prints-file-list');
  if (!el) return;
  const active = getActivePanel();
  if (!active || !active.paths.length) {
    el.innerHTML = active
      ? '<div class="text-slate-600 italic">No files in this panel yet</div>'
      : '';
    return;
  }
  el.innerHTML = active.paths.map((p, i) => {
    const name = p.split(/[/\\]/).pop();
    return `<div class="flex items-center gap-1 truncate">
      <span class="flex-1 truncate" title="${p}">${escapeHtml(name)}</span>
      <button type="button" class="print-file-remove text-slate-600 hover:text-red-400" data-idx="${i}">×</button>
    </div>`;
  }).join('');
  el.querySelectorAll('.print-file-remove').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx, 10);
      const pan = getActivePanel();
      if (pan && !Number.isNaN(idx)) {
        pan.paths.splice(idx, 1);
        renderPanelSets();
        if (totalPrintFiles() === 0 && ioState.ocrResult) {
          clearIoCompareState({ clearPanels: false });
          ioLog('All print PDFs removed — merge/crosswalk cleared.', 'info');
        }
      }
    });
  });
}

function setMasterPanel(name) {
  const n = (name || '').trim() || 'Master';
  // Demote any existing master
  ioState.panelSets.forEach((p) => {
    if (p.role === 'master') p.role = 'remote';
  });
  let master = ioState.panelSets.find((p) => p.name.toLowerCase() === n.toLowerCase());
  if (master) {
    master.role = 'master';
  } else {
    master = { id: uidPanel(), name: n, role: 'master', paths: [] };
    ioState.panelSets.unshift(master);
  }
  ioState.activePanelId = master.id;
  renderPanelSets();
  ioLog(`Master set: ${master.name}`, 'ok');
  return master;
}

function addRemotePanel(name) {
  const n = (name || '').trim() || `Remote${getRemotePanels().length + 1}`;
  if (ioState.panelSets.some((p) => p.name.toLowerCase() === n.toLowerCase())) {
    ioLog(`Panel "${n}" already exists — select it to add files.`, 'warn');
    const existing = ioState.panelSets.find((p) => p.name.toLowerCase() === n.toLowerCase());
    if (existing) {
      if (existing.role === 'master') {
        ioLog('That name is the master. Use a different name for remote.', 'warn');
        return existing;
      }
      ioState.activePanelId = existing.id;
      renderPanelSets();
    }
    return existing;
  }
  const panel = { id: uidPanel(), name: n, role: 'remote', paths: [] };
  ioState.panelSets.push(panel);
  ioState.activePanelId = panel.id;
  renderPanelSets();
  ioLog(`Remote panel added: ${n}`, 'ok');
  return panel;
}

function isPrintPath(p) {
  return /\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i.test(p || '');
}

/** Add print paths to a specific panel (or active if omitted). */
function addPrintPaths(paths, panelOrId) {
  let target = null;
  if (panelOrId) {
    if (typeof panelOrId === 'string') {
      target = ioState.panelSets.find((p) => p.id === panelOrId) || null;
    } else {
      target = panelOrId;
    }
  }
  if (!target) target = getActivePanel();
  if (!target) {
    ioLog('Set a master or add a remote panel first.', 'warn');
    return 0;
  }
  ioState.activePanelId = target.id;
  let added = 0;
  for (const p of paths || []) {
    if (!p) continue;
    if (!isPrintPath(p)) {
      ioLog(`Skipped (not a print): ${String(p).split(/[/\\]/).pop()}`, 'warn');
      continue;
    }
    if (!target.paths.includes(p)) {
      target.paths.push(p);
      added += 1;
    }
  }
  if (added) ioLog(`Added ${added} file(s) to ${target.name} (${target.role})`, 'info');
  else if ((paths || []).length) ioLog(`No new print files for ${target.name}`, 'warn');
  renderPanelSets();
  if (!$('print-repo-panel')?.classList.contains('hidden')) renderPrintRepository();
  return added;
}

/** Resolve file paths from a drop event (Electron webUtils). */
function pathsFromDrop(e) {
  const files = [...(e.dataTransfer?.files || [])];
  return files.map((f) => fortnaAPI.getPathForFile(f)).filter(Boolean);
}

/**
 * Wire drag/drop for prints onto a zone.
 * role: 'master' | 'remote' | 'active'
 * - master: auto-creates master if missing, always targets master
 * - remote: targets hovered remote card if any, else active remote (or creates from name input)
 * - active: targets currently selected panel
 */
function bindPrintDropZone(el, role) {
  if (!el) return;
  // Allow dropping files (required in some Electron/Chromium builds)
  el.addEventListener('dragenter', (e) => {
    e.preventDefault();
    e.stopPropagation();
    el.classList.add('dragover');
  });
  el.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    el.classList.add('dragover');
  });
  el.addEventListener('dragleave', (e) => {
    // only clear when leaving the zone itself (not child elements)
    if (e.target === el || !el.contains(e.relatedTarget)) {
      el.classList.remove('dragover');
    }
  });
  el.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    el.classList.remove('dragover');

    const allPaths = pathsFromDrop(e);
    if (!allPaths.length) {
      ioLog('Could not read dropped file path(s). Use Browse instead.', 'warn');
      return;
    }
    const runs = allPaths.filter((p) => isRunArchivePath(p));
    const prints = allPaths.filter((p) => !isRunArchivePath(p));
    if (runs.length) {
      importRunPackage(runs[0], runs[0].split(/[/\\]/).pop());
    }
    if (!prints.length) {
      if (!runs.length) ioLog('Drop PDF/PNG prints (or a .tar.gz RUN package).', 'warn');
      return;
    }

    if (role === 'master') {
      // Always master only — never remotes
      const target = getMasterPanel() || setMasterPanel($('master-name-input')?.value || 'Master');
      addPrintPaths(prints, target);
      return;
    }
    if (role === 'remote') {
      // Prefer an explicit remote card under the cursor; otherwise one panel per file
      const hit = e.target?.closest?.('[data-panel-id][data-panel-role="remote"]');
      let target = null;
      if (hit?.dataset?.panelId) {
        target = ioState.panelSets.find((p) => p.id === hit.dataset.panelId && p.role === 'remote') || null;
      }
      addRemotePrintPaths(prints, target);
      return;
    }
    // legacy active zone
    const active = getActivePanel();
    if (active?.role === 'remote') addRemotePrintPaths(prints, active);
    else {
      const target = active || getMasterPanel() || setMasterPanel($('master-name-input')?.value || 'Master');
      addPrintPaths(prints, target);
    }
  });
}

function renderDriveParameters(data) {
  const tbody = $('io-drives-tbody');
  const stats = $('io-drives-stats');
  const status = $('io-drives-status');
  if (!tbody) return;

  // Explicit empty / clear payload — wipe state so table cannot rebuild from stale banks
  if (!data || data.success === false || data.clear === true) {
    ioState.drives = [];
    ioState.devices = [];
    ioState.motorChains = [];
    if (data?.clear || data?.success === false) {
      // keep banks only if this is a soft message without clear flag
    }
    if (status) {
      status.textContent = '—';
      status.className = 'status-pill status-idle';
    }
    let msg = data?.message || 'Load a RUN package (.tar.gz) to list devices.';
    if (typeof msg === 'string' && (msg.length > 200 || msg.trim().startsWith('{'))) {
      msg = 'Drive list failed to load — relaunch Site Forge and click refresh.';
    }
    tbody.innerHTML = `<tr><td colspan="4" class="py-4 px-2 text-slate-500">${escapeHtml(msg)}</td></tr>`;
    if (stats) {
      stats.classList.add('hidden');
      stats.innerHTML = '';
    }
    if ($('device-type-filter')) {
      $('device-type-filter').innerHTML = '<option value="all">All devices</option>';
    }
    if ($('device-type-count')) $('device-type-count').textContent = '0';
    showDriveDetail(null);
    return;
  }

  // Accept both banks API payload and OCR result payload
  if (data && Array.isArray(data.drives)) {
    ioState.drives = data.drives;
    ioState.motorChains = data.motor_chains || ioState.motorChains || [];
    if (data.print_vfd_params) ioState.printVfdParams = data.print_vfd_params;
    rebuildDeviceList();
  }

  const driveCount = data.drive_count != null ? data.drive_count : (ioState.drives || []).length;
  const withPrint = data.drives_with_print_params != null
    ? data.drives_with_print_params
    : (ioState.drives || []).filter((d) => d.print_param_count > 0).length;

  const vfdCount = (ioState.drives || []).filter(
    (d) => (/^VFD\d/i.test(d.name || '') || d.equipment_kind === 'vfd')
      && !/^P\d/i.test(d.name || ''),
  ).length;
  if (status) {
    status.textContent = withPrint
      ? `${driveCount} rows · ${withPrint} w/ print`
      : `${driveCount} drive rows`;
    status.className = 'status-pill status-ready';
  }
  if (stats) {
    stats.classList.remove('hidden');
    // Never fall back to "drive id" count — that inflated "Program VFDs" to ~300
    stats.innerHTML = [
      ['All rows', driveCount],
      ['VFDs (tar.gz)', vfdCount],
      ['With print params', withPrint],
      ['Print VFD hits', data.print_vfd_param_count || (ioState.printVfdParams || []).length || 0],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-cyan-300 mono">${v}</div>
      </div>`).join('');
  }

  renderDriveTableRows();
}

function updateOcrProgressUI(p) {
  const wrap = $('ocr-progress-wrap');
  const bar = $('ocr-progress-bar');
  const pctEl = $('ocr-progress-pct');
  const detail = $('ocr-progress-detail');
  if (!wrap) return;
  if (!p) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  const pct = Math.max(0, Math.min(100, Number(p.pct) || 0));
  if (bar) bar.style.width = `${pct}%`;
  if (pctEl) pctEl.textContent = `${pct}%`;
  const bits = [];
  if (p.pages_total) bits.push(`pages ${p.pages_done || 0}/${p.pages_total}`);
  if (p.file_total) bits.push(`file ${p.file_index || 0}/${p.file_total}`);
  if (p.workers) bits.push(`${p.workers} worker(s)`);
  if (p.file) bits.push(p.file);
  if (p.panel) bits.push(`panel ${p.panel}`);
  if (p.mode) bits.push(p.mode);
  const line = p.message || bits.join(' · ') || 'Working…';
  if (detail) {
    detail.innerHTML = `<span class="text-slate-400">${escapeHtml(line)}</span>`
      + (bits.length ? `<br><span class="text-slate-600">${escapeHtml(bits.join(' · '))}</span>` : '');
  }
  if (p.phase === 'done' || p.phase === 'error') {
    // Keep visible briefly so user sees completion
    if (p.phase === 'done' && bar) bar.style.width = '100%';
    if (p.phase === 'done' && pctEl) pctEl.textContent = '100%';
  }
}

/**
 * Merge OCR print VFD parameters into existing tar.gz drive list.
 * Keeps all RUN devices; only adds/updates print_params on matches.
 *
 * CRITICAL: Python attach_print_params_to_drives already assigned print_page.
 * The UI must NOT re-vote pages from raw print_vfd_params — that used to assign
 * every orphan param (no device_id) to ALL VFDs on the PDF, collapsing PRINT #
 * to one page (e.g. all 27). Trust ocrResult.drives first.
 */
function mergeOcrPrintParamsIntoDrives(ocrResult) {
  if (!ocrResult) return;
  const ocrDrives = ocrResult.drives || [];
  const printVfd = ocrResult.print_vfd_params || [];

  // If we never loaded banks, accept OCR drives as base (still better than empty)
  if (!(ioState.drives && ioState.drives.length) && ocrDrives.length) {
    renderDriveParameters({
      success: true,
      drives: ocrDrives,
      drive_count: ocrResult.drive_count || ocrDrives.length,
      drives_with_print_params: ocrResult.drives_with_print_params || 0,
      print_vfd_param_count: ocrResult.print_vfd_param_count || printVfd.length,
      print_vfd_params: printVfd,
      motor_chains: ocrResult.motor_chains,
      machine: ocrResult.machine,
    });
    return;
  }

  const baseName = (n) => String(n || '')
    .replace(/(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$/i, '')
    .toUpperCase();

  const cleanVfdId = (v) => {
    let id = String(v || '').replace(/[_\s\-]/g, '').toUpperCase();
    id = id.replace(/(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$/i, '');
    if (!id) return '';
    if (!id.startsWith('VFD')) id = `VFD${id}`;
    return /^VFD\d{2,4}(?:[A-Z]{1,2}\d?)?$/i.test(id) ? id : '';
  };

  // --- Prefer Python-assigned page/params per drive (authoritative) ---
  const byExactName = new Map(); // full name VFD312_EN → drive row from OCR
  const byBase = new Map(); // VFD312 → best page/params from OCR drives
  for (const d of ocrDrives) {
    const nm = (d.name || '').toUpperCase();
    if (!nm) continue;
    byExactName.set(nm, d);
    const b = cleanVfdId(baseName(d.base_name || d.name)) || baseName(d.base_name || d.name);
    if (!b || !/^VFD/i.test(b)) continue;
    const prev = byBase.get(b) || {};
    // Prefer row that has a print_page; then more params
    const prevScore = (prev.print_page ? 100 : 0) + (prev.print_param_count || 0);
    const score = (d.print_page ? 100 : 0) + (d.print_param_count || 0);
    if (!byBase.has(b) || score >= prevScore) {
      byBase.set(b, {
        print_param_list: d.print_param_list || Object.values(d.print_params || {}),
        print_params: d.print_params || {},
        print_param_count: d.print_param_count || 0,
        print_sources: d.print_sources || [],
        print_file: d.print_file || '',
        print_page: d.print_page || d.drawing_page || null,
        drawing_page: d.drawing_page || d.print_page || null,
        vfd_from_print: !!(d.vfd_from_print || d.print_param_count || d.print_page),
      });
    }
  }

  // Device-scoped raw params only (must have device_id). Never broadcast file-wide.
  for (const p of printVfd) {
    if ((p.param || '') === 'Device_ID') continue;
    const id = cleanVfdId(p.device_id || '');
    if (!id) continue; // orphan param — ignore (was the page-27 collapse)
    const prev = byBase.get(id) || {
      print_param_list: [], print_params: {}, print_param_count: 0,
      print_sources: [], print_page: null, vfd_from_print: false,
    };
    // Only add params if this base didn't already get a Python page assignment
    // with a full table — still OK to fill params when page is set but params empty
    const list = [...(prev.print_param_list || []), p];
    prev.print_param_list = list;
    prev.print_params = { ...(prev.print_params || {}), [p.param || 'param']: p };
    prev.print_param_count = list.length;
    prev.vfd_from_print = true;
    if (p.source) {
      prev.print_sources = [...new Set([...(prev.print_sources || []), p.source])];
    }
    // Only set page from param if Python never assigned one
    if (prev.print_page == null && p.page != null && Number(p.page) > 0) {
      prev.print_page = Number(p.page);
      prev.drawing_page = Number(p.page);
    }
    byBase.set(id, prev);
  }

  let merged = 0;
  let pagesFromPython = 0;
  for (const d of ioState.drives || []) {
    const nm = (d.name || '').toUpperCase();
    const b = baseName(d.base_name || d.name);
    const bNorm = cleanVfdId(b) || b;
    // Exact name first (VFD312_EN), then base (VFD312)
    const exact = byExactName.get(nm);
    const hit = exact
      ? {
          print_param_list: exact.print_param_list || Object.values(exact.print_params || {}),
          print_params: exact.print_params || {},
          print_param_count: exact.print_param_count || 0,
          print_sources: exact.print_sources || [],
          print_file: exact.print_file || '',
          print_page: exact.print_page || exact.drawing_page || null,
          drawing_page: exact.drawing_page || exact.print_page || null,
          vfd_from_print: !!(exact.vfd_from_print || exact.print_page || exact.print_param_count),
        }
      : (byBase.get(b) || byBase.get(bNorm) || byBase.get(cleanVfdId(d.name)));

    if (!hit) continue;
    const hasPage = hit.print_page != null && Number(hit.print_page) > 0;
    const cleaned = filterVfdPrintParamsClient(
      hit.print_param_list || Object.values(hit.print_params || {}),
    );
    if (!hasPage && !cleaned.length && !hit.vfd_from_print) continue;

    if (cleaned.length) {
      d.print_params = Object.fromEntries(cleaned.map((p) => [p.param, p]));
      d.print_param_list = cleaned;
      d.print_param_count = cleaned.length;
    } else if (hit.print_param_count) {
      d.print_param_count = hit.print_param_count;
      d.print_param_list = hit.print_param_list || [];
      d.print_params = hit.print_params || {};
    }
    d.print_sources = hit.print_sources || d.print_sources || [];
    if (hit.print_file) d.print_file = hit.print_file;
    // TRUST Python / exact-drive page — do not re-vote from cleaned params
    if (hasPage) {
      d.print_page = Number(hit.print_page);
      d.drawing_page = Number(hit.print_page);
      pagesFromPython += 1;
    } else if (cleaned.length) {
      // Fallback only: params scoped to this device_id
      const pageVotes = new Map();
      for (const p of cleaned) {
        if (p.page != null && Number(p.page) > 0) {
          const pg = Number(p.page);
          pageVotes.set(pg, (pageVotes.get(pg) || 0) + 1);
        }
      }
      if (pageVotes.size) {
        let bestPg = null;
        let bestN = -1;
        for (const [pg, n] of pageVotes) {
          if (n > bestN) { bestPg = pg; bestN = n; }
        }
        d.print_page = bestPg;
        d.drawing_page = bestPg;
      }
    }
    if (!d.drawing_page && d.print_page) d.drawing_page = d.print_page;
    d.vfd_from_print = !!(hasPage || cleaned.length || hit.vfd_from_print);
    if ((/^VFD\d/i.test(b) || /^VFD\d/i.test(bNorm)) && !/^P\d/i.test(b)) {
      d.is_vfd = true;
      d.equipment_kind = 'vfd';
    }
    merged += 1;
  }

  ioState.printVfdParams = printVfd;
  rebuildDeviceList();
  const withPrint = (ioState.drives || []).filter(
    (d) => (d.print_param_count || 0) > 0 || (d.print_page && d.vfd_from_print),
  ).length;
  const withPage = (ioState.drives || []).filter(
    (d) => /^VFD/i.test(d.name || '') && d.print_page,
  ).length;
  if ($('io-drives-status')) {
    $('io-drives-status').textContent =
      `${ioState.drives.length} rows · ${withPage} VFD print # · ${withPrint} w/ print data`;
    $('io-drives-status').className = 'status-pill status-ready';
  }
  if ($('io-drives-stats')) {
    $('io-drives-stats').classList.remove('hidden');
    const vfdN = (ioState.drives || []).filter(
      (d) => (/^VFD\d/i.test(d.name || '') || d.equipment_kind === 'vfd') && !/^P\d/i.test(d.name || ''),
    ).length;
    $('io-drives-stats').innerHTML = [
      ['All rows', ioState.drives.length],
      ['VFDs (tar.gz)', vfdN],
      ['With print #', withPage],
      ['Print VFD hits', printVfd.length || 0],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-cyan-300 mono">${v}</div>
      </div>`).join('');
  }
  if (merged > 0) {
    ioLog(
      `Merged OCR into ${merged} drive(s) · ${pagesFromPython} print page(s) from Python log `
      + `(not re-voted in UI) · ${withPage} VFD(s) show PRINT #.`,
      'ok',
    );
  } else {
    ioLog(
      `OCR finished but PRINT column is still empty (0 VFD matches). `
      + `Extracted ${printVfd.length} raw print param(s). `
      + `Check exports/ocr-logs/vfd_page_assign_*.txt`,
      'warn',
    );
  }
}

function renderDriveTableRows() {
  const tbody = $('io-drives-tbody');
  if (!tbody) return;
  // Only rebuild from banks/drives when we still have source data (never after Clear RUN)
  const hasSource =
    (ioState.drives && ioState.drives.length > 0)
    || (ioState.banks && (ioState.banks.banks || []).length > 0);
  if (!ioState.devices.length && hasSource) {
    rebuildDeviceList();
  }
  if (!hasSource && !ioState.devices.length) {
    tbody.innerHTML =
      '<tr><td colspan="4" class="py-4 px-2 text-slate-500">Load a RUN package (.tar.gz) to list devices.</td></tr>';
    if ($('device-type-count')) $('device-type-count').textContent = '0';
    if ($('io-drives-status')) {
      $('io-drives-status').textContent = '—';
      $('io-drives-status').className = 'status-pill status-idle';
    }
    return;
  }

  const typeFilter = $('device-type-filter')?.value || ioState.deviceTypeFilter || 'all';
  ioState.deviceTypeFilter = typeFilter;
  const printOnly = !!$('drive-print-only')?.checked;

  let rows = ioState.devices || [];
  if (typeFilter && typeFilter !== 'all') {
    rows = rows.filter((d) => d.typeKey === typeFilter);
  }
  if (printOnly) {
    rows = rows.filter((d) =>
      d.vfd_from_print
      || (d.print_param_count || 0) > 0
      || (d.print_param_list || []).length > 0
    );
  }

  if ($('device-type-count')) {
    $('device-type-count').textContent = `${rows.length} shown`;
  }

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="py-4 px-2 text-slate-500">${
      printOnly
        ? 'No print-matched devices yet — run OCR on panel PDFs, then filter again.'
        : (typeFilter !== 'all'
          ? 'No devices of this type in the program.'
          : 'No devices found. Load a RUN package first.')
    }</td></tr>`;
    return;
  }

  const sel = ioState.selectedDriveName || '';
  // Separate each device as its own bordered card-row
  tbody.innerHTML = rows.map((d) => {
    const printN = d.print_param_count || (d.print_param_list || []).length || 0;
    const pageNo = d.drawing_page || d.print_page || null;
    const active = d.name === sel ? 'bg-cyan-950/50 ring-1 ring-cyan-700/50' : 'hover:bg-[#101820]';
    const addr = d.io_address || d.drive || '—';
    const typeColor = {
      vfd: 'text-amber-400',
      photoeye: 'text-sky-400',
      motor: 'text-emerald-400',
      conveyor: 'text-cyan-300',
      estop: 'text-red-400',
      pushbutton: 'text-violet-300',
      beacon: 'text-yellow-400',
    }[d.typeKey] || 'text-slate-400';
    const printCell = pageNo
      ? `<button type="button" class="print-link text-amber-400 hover:text-amber-200 underline decoration-amber-700/60"
           data-print-page="${pageNo}" data-print-file="${escapeHtml(d.print_file || '')}"
           data-machine="${escapeHtml(d.machine_name || '')}" title="Open drawing page ${pageNo}">${pageNo}</button>`
      : (printN
        ? `<span class="text-amber-500/70" title="${printN} OCR params">${printN}p</span>`
        : '<span class="text-slate-600">—</span>');
    return `
    <tr class="border-b border-slate-800/90 cursor-pointer drive-row ${active}" data-drive-name="${escapeHtml(d.name || '')}">
      <td class="py-2 px-2 ${typeColor} text-[10px] whitespace-nowrap font-semibold">${escapeHtml(d.typeLabel || '')}</td>
      <td class="py-2 px-2 text-slate-100 mono whitespace-nowrap">
        ${escapeHtml(d.name || '')}
        ${printN ? '<span class="text-[9px] text-amber-400 ml-1">ocr</span>' : ''}
      </td>
      <td class="py-2 px-2 text-slate-500 mono text-[10px]">${escapeHtml(String(addr))}</td>
      <td class="py-2 px-2 mono text-[11px]">${printCell}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('.drive-row').forEach((tr) => {
    tr.addEventListener('click', (ev) => {
      // Print # is its own click target
      if (ev.target.closest('.print-link')) return;
      const name = tr.dataset.driveName;
      const device = (ioState.devices || []).find((d) => d.name === name)
        || (ioState.drives || []).find((d) => d.name === name);
      ioState.selectedDriveName = name;
      showDriveDetail(device || null);
      renderDriveTableRows();
    });
  });
  tbody.querySelectorAll('.print-link').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openDevicePrint({
        drawing_page: parseInt(btn.dataset.printPage, 10) || null,
        print_page: parseInt(btn.dataset.printPage, 10) || null,
        print_file: btn.dataset.printFile || '',
        machine_name: btn.dataset.machine || '',
      });
    });
  });
}

/** Client-side safety net: PowerFlex program-table params (PF4 ≈8, PF70 more). */
function filterVfdPrintParamsClient(list) {
  // Dynamic: allow known PF4 + PF70 sheet params; hard cap prevents OCR floods
  const CANON = new Set([
    31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 53, 55, 56,
    70, 80, 82, 90, 91, 92, 101, 102, 103, 104, 105, 106, 107,
    140, 141, 142, 143, 158, 159, 160, 161, 163, 196, 201,
    361, 362, 363, 364, 365, 380, 381, 382, 383, 384, 385,
  ]);
  const NAME_RE = /^(?:P0*\d+\s+)?(?:Motor\s+NP\s+(?:Volts?|Hertz|FLA|RPM|Power)|Mtr\s+NP\s+Pwr\s+Units|Motor\s+NP\s+Pwr\s+Units|Motor\s+OL\s+Current|Start\s+Source|Speed\s+Reference|Speed\s+Ref\s+A\s+Sel|Accel(?:eration)?\s*Time\s*\d*|Decel(?:eration)?\s*Time\s*\d*|Relay\s+Out\s+Sel|Preset\s+(?:Freq(?:uency)?|Speed)\s*\d*|Maximum\s+(?:Freq(?:uency)?|Speed)|Compensation|DC\s+Brake\s+(?:Time|Level)|DB\s+Resistor\s+Type|Bus\s+Reg\s+Mode\s*A?|Param\s+Access\s+Lvl|Language|Digital\s+(?:In|Out)\d*\s+Sel|Dig\s+Out\d*\s+Level)$/i;
  const MAX = 32;
  const byPar = new Map();
  for (const p of list || []) {
    if (!p || typeof p !== 'object') continue;
    const param = String(p.param || '');
    if (!param || /^Device_ID/i.test(param)) continue;
    const m = param.match(/^P\s*0*(\d{1,3})\b/i) || param.match(/^0*(\d{1,3})\s+/);
    let par = m ? parseInt(m[1], 10) : null;
    if (par == null) {
      const bare = param.replace(/^P0*\d+\s+/i, '').trim().toLowerCase();
      const map = {
        'motor np volts': 31, 'motor ol current': 33, 'start source': 36,
        'speed reference': 38, 'accel time 1': 39, 'decel time 1': 40,
        'relay out sel': 55, 'preset freq 0': 70, 'maximum speed': 82,
        'maximum freq': 55, 'motor np fla': 42, 'motor np hertz': 43,
        'dc brake time': 159, 'dc brake level': 158, 'db resistor type': 163,
      };
      par = map[bare] || null;
    }
    if (par != null && !CANON.has(par)) continue;
    if (par == null && !NAME_RE.test(param)) continue;
    if (par != null) {
      const bare = param.replace(/^P\s*0*\d{1,3}\s+/i, '').trim() || param;
      const label = `P${String(par).padStart(3, '0')} ${bare.replace(/^P\d+\s*/i, '')}`;
      const row = { ...p, param: label, par_num: par };
      const prev = byPar.get(par);
      if (!prev || String(row.display || row.value || '').length >= String(prev.display || prev.value || '').length) {
        byPar.set(par, row);
      }
    }
  }
  return [...byPar.values()]
    .sort((a, b) => (a.par_num || 0) - (b.par_num || 0))
    .slice(0, MAX);
}

/** Resolve which loaded PDF to open for a drawing page / machine. */
function resolvePrintForDevice(device) {
  const page = device?.drawing_page || device?.print_page || null;
  const explicit = (device?.print_file || '').trim();
  const machine = String(device?.machine_name || '').toUpperCase();
  // Match CP# from machine ORNCCP5 → CP5
  let cpHint = '';
  const mCp = machine.match(/CP\s*(\d+)/i) || machine.match(/ORNCCP(\d+)/i);
  if (mCp) cpHint = `CP${mCp[1]}`;

  const repo = buildPrintRepository();
  if (explicit) {
    const base = explicit.replace(/^.*[\\/]/, '').toLowerCase();
    const hit = repo.find((r) => r.name.toLowerCase() === base || r.path.toLowerCase().endsWith(base));
    if (hit) return { path: hit.path, page: page || 1, label: `${hit.panel || hit.name}${page ? ` p.${page}` : ''}` };
  }
  // Prefer panel PDF matching CP hint
  if (cpHint) {
    const hit = repo.find((r) =>
      r.name.toUpperCase().includes(cpHint)
      || (r.panel || '').toUpperCase().includes(cpHint)
    );
    if (hit) return { path: hit.path, page: page || 1, label: `${hit.panel || hit.name}${page ? ` p.${page}` : ''}` };
  }
  // Any master/remote PDF that has enough pages
  if (page) {
    const hit = repo.find((r) => !r.pages || r.pages >= page) || repo[0];
    if (hit) return { path: hit.path, page, label: `${hit.panel || hit.name} p.${page}` };
  }
  if (repo[0]) return { path: repo[0].path, page: page || 1, label: repo[0].panel || repo[0].name };
  return null;
}

function buildPrintRepository() {
  const out = [];
  const seen = new Set();
  for (const panel of (ioState.panelSets || [])) {
    for (const p of (panel.paths || [])) {
      const path = String(p || '');
      if (!path || seen.has(path.toLowerCase())) continue;
      seen.add(path.toLowerCase());
      const name = path.replace(/^.*[\\/]/, '');
      out.push({
        path,
        name,
        panel: panel.name || panel.role || '',
        role: panel.role || '',
      });
    }
  }
  // Also include workspace/prints folders we know about from OCR sources
  for (const d of (ioState.drives || [])) {
    for (const src of (d.print_sources || [])) {
      const name = String(src || '');
      if (!name || seen.has(name.toLowerCase())) continue;
      seen.add(name.toLowerCase());
      out.push({ path: name, name: name.replace(/^.*[\\/]/, ''), panel: 'OCR', role: 'ocr' });
    }
  }
  return out;
}

function renderPrintRepository() {
  const list = $('print-repo-list');
  if (!list) return;
  const repo = buildPrintRepository();
  if (!repo.length) {
    list.innerHTML = '<div class="text-slate-600">No PDFs assigned yet — drop master/remote CP prints above.</div>';
    return;
  }
  list.innerHTML = repo.map((r) => `
    <div class="flex items-center gap-2 py-0.5 border-b border-slate-800/50">
      <span class="text-slate-500 w-16 shrink-0">${escapeHtml(r.panel || r.role)}</span>
      <button type="button" class="repo-open text-left text-amber-300/90 hover:text-amber-200 underline flex-1 truncate"
        data-path="${escapeHtml(r.path)}" title="${escapeHtml(r.path)}">${escapeHtml(r.name)}</button>
      <button type="button" class="repo-folder text-slate-600 hover:text-slate-300 px-1" data-path="${escapeHtml(r.path)}" title="Show in folder">
        <i class="fa-solid fa-folder-open"></i>
      </button>
    </div>`).join('');
  list.querySelectorAll('.repo-open').forEach((btn) => {
    btn.addEventListener('click', () => openPrintFile(btn.dataset.path, 1));
  });
  list.querySelectorAll('.repo-folder').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (typeof fortnaAPI.openPath === 'function') fortnaAPI.openPath(btn.dataset.path);
    });
  });
}

async function openPrintFile(filePath, page) {
  if (!filePath) {
    ioLog('No print file to open', 'warn');
    return;
  }
  if (typeof fortnaAPI.openPrintPage === 'function') {
    const res = await fortnaAPI.openPrintPage({ path: filePath, page: page || 1 });
    if (!res?.success) {
      ioLog(res?.message || 'Could not open print', 'err');
      return;
    }
    ioLog(res.note || `Opened ${filePath}${page ? ` (page ${page})` : ''}`, 'ok');
    return;
  }
  if (typeof fortnaAPI.openPath === 'function') fortnaAPI.openPath(filePath);
}

async function openDevicePrint(device) {
  const hit = resolvePrintForDevice(device);
  if (!hit) {
    ioLog('No print PDF in repository for this device — load CP PDFs first.', 'warn');
    // Still try workspace/prints by machine
    const page = device?.drawing_page || device?.print_page;
    if (page) ioLog(`Drawing page from RUN: ${page} (assign matching CP PDF to open it)`, 'info');
    return;
  }
  await openPrintFile(hit.path, hit.page);
}

function showDriveDetail(drive) {
  const empty = $('drive-detail-empty');
  const panel = $('drive-detail');
  if (!empty || !panel) return;
  if (!drive) {
    empty.classList.remove('hidden');
    panel.classList.add('hidden');
    return;
  }
  empty.classList.add('hidden');
  panel.classList.remove('hidden');

  const pageNo = drive.drawing_page || drive.print_page || null;
  if ($('drive-detail-name')) $('drive-detail-name').textContent = drive.name || '—';
  if ($('drive-detail-meta')) {
    $('drive-detail-meta').textContent = [
      drive.typeLabel || drive.device_type || drive.device_class,
      drive.io_address,
      drive.drive ? `drv ${drive.drive}` : '',
      drive.motor ? `motor ${drive.motor}` : '',
      drive.speed ? `spd ${drive.speed}` : '',
      pageNo ? `drawing p.${pageNo}` : '',
      (drive.print_sources || []).length ? `prints: ${drive.print_sources.join(', ')}` : 'no print OCR match yet',
    ].filter(Boolean).join(' · ');
  }

  const openBtn = $('btn-open-device-print');
  const openLbl = $('btn-open-device-print-label');
  if (openBtn) {
    if (pageNo || drive.print_file) {
      openBtn.classList.remove('hidden');
      if (openLbl) openLbl.textContent = pageNo ? `#${pageNo}` : '';
      openBtn.onclick = () => openDevicePrint(drive);
    } else {
      openBtn.classList.add('hidden');
      openBtn.onclick = null;
    }
  }

  const progBox = $('drive-program-params');
  const printBox = $('drive-print-params');
  const prog = drive.program_params || {};
  // For VFDs, show key ASC fields only (not geometry clutter)
  const isVfd = drive.is_vfd || drive.typeKey === 'vfd' || /^VFD/i.test(drive.name || '');
  const VFD_ASC_KEEP = new Set([
    'IO_Name', 'General_Description', 'Device_Description', 'IO_Address_Word', 'IO_Address_Bit',
    'Part_Number', 'Type', 'Machine_Name', 'Motor', 'ProcNum', 'Drive', 'Speed',
    'Electrical Drawing Page No.', 'Electrical_Drawing_Page_No.', 'In Motor Chain', 'Important_IO',
  ]);
  let progKeys = Object.keys(prog).sort((a, b) => a.localeCompare(b));
  if (isVfd) {
    const kept = progKeys.filter((k) => VFD_ASC_KEEP.has(k) || /drawing|page|io_|part|motor|machine|type|desc|proc|drive|speed/i.test(k));
    if (kept.length) progKeys = kept;
  }
  if (progBox) {
    if (!progKeys.length) {
      progBox.innerHTML = '<div class="text-slate-600">No populated ASC fields.</div>';
    } else {
      progBox.innerHTML = progKeys.map((k) => `
        <div class="flex gap-2 border-b border-slate-800/60 py-0.5">
          <span class="text-slate-500 shrink-0 w-[45%]">${escapeHtml(k)}</span>
          <span class="text-emerald-300 break-all">${escapeHtml(String(prog[k]))}</span>
        </div>`).join('');
    }
  }

  if (printBox) {
    let plist = drive.print_param_list
      || Object.entries(drive.print_params || {}).map(([param, p]) =>
        (typeof p === 'object' ? p : { param, display: p, value: p }));
    plist = filterVfdPrintParamsClient(plist);
    if (!plist.length) {
      printBox.innerHTML = `
        <div class="text-slate-600 leading-relaxed">
          No PowerFlex program params from prints for this device yet.<br>
          Drop panel PDFs, run <strong class="text-slate-400">OCR · merge</strong>.
          Only table params are kept (P031 Volts, P033 OL Current, P036 Start Source,
          P038 Speed Ref, P039/P040 Accel/Decel, P055 Relay Out, P070 Preset Freq…).
        </div>`;
    } else {
      printBox.innerHTML = plist.map((p) => `
        <div class="flex gap-2 border-b border-slate-800/60 py-0.5">
          <span class="text-amber-500/90 shrink-0 w-[48%]">${escapeHtml(p.param || '')}</span>
          <span class="text-amber-200 break-all">${escapeHtml(p.display || p.value || '')}</span>
        </div>`).join('')
        + `<div class="text-[9px] text-slate-600 mt-1">${plist.length} programmed param(s)</div>`;
    }
  }
}

function renderIoBanks(data) {
  const list = $('io-banks-list');
  const stats = $('io-banks-stats');
  const status = $('io-banks-status');
  if (!list) return;

  // Recover if main process returned raw JSON as an error message (old maxBuffer bug)
  if (data && !data.success && typeof data.message === 'string' && data.message.trim().startsWith('{')) {
    try {
      const parsed = JSON.parse(data.message);
      if (parsed && (parsed.ok || parsed.banks || parsed.point_count != null)) {
        data = { success: true, ...parsed };
      }
    } catch (_) { /* keep original */ }
  }

  renderDriveParameters(data);

  if (!data || !data.success) {
    if (status) {
      status.textContent = 'No RUN';
      status.className = 'status-pill status-idle';
    }
    let msg = data?.message || 'Import a RUN on this tab, then refresh banks.';
    // Never dump multi-KB JSON into the panel
    if (typeof msg === 'string' && (msg.length > 280 || msg.trim().startsWith('{'))) {
      msg = 'Could not load banks (payload too large or parse error). Click refresh after relaunch — this is fixed for large sites.';
    }
    list.innerHTML = `<div class="text-slate-500 text-sm leading-relaxed">${escapeHtml(msg)}</div>`;
    stats?.classList.add('hidden');
    updateRecontrolReady();
    return;
  }

  ioState.banks = data;
  rebuildDeviceList();
  renderDriveTableRows();
  updateRecontrolReady();
  if (status) {
    status.textContent = data.machine ? `${data.machine} banks` : 'Banks loaded';
    status.className = 'status-pill status-ready';
  }
  if (stats) {
    stats.classList.remove('hidden');
    stats.innerHTML = [
      ['Points', data.point_count || 0],
      ['Banks', data.bank_count || 0],
      ['ConfigIO rows', data.configio_count || 0],
      ['Machine', data.machine || '—'],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-cyan-300 mono">${v}</div>
      </div>`).join('');
  }

  const banks = data.banks || [];
  if (!banks.length) {
    list.innerHTML = '<div class="text-slate-500">No bank-mapped I/O points found in Conveyor.asc.</div>';
    return;
  }

  list.innerHTML = banks.map((b) => {
    const sample = (b.points || []).slice(0, 8).map((p) =>
      `<div class="text-[10px] mono text-slate-500 pl-2">· ${p.fortna_name || p.tag} <span class="text-slate-600">${p.address || ''} ${p.device_class || ''}</span></div>`
    ).join('');
    return `
      <div class="rounded-xl border border-slate-800 bg-[#101820] p-3">
        <div class="flex items-center justify-between gap-2">
          <div class="font-semibold text-cyan-300 mono">Bank ${b.bank}</div>
          <div class="text-[10px] text-slate-500">${b.point_count} pts · ${b.inputs} in / ${b.outputs} out</div>
        </div>
        ${sample}
        ${(b.points || []).length > 8 ? `<div class="text-[10px] text-slate-600 pl-2 mt-1">… +${b.points.length - 8} more in this bank</div>` : ''}
      </div>`;
  }).join('');

  if (data.configio_count) {
    list.innerHTML += `<div class="text-[10px] text-slate-600 mt-2">Configio table: ${data.configio_count} rows (${data.configio_source || 'Configio.asc'})</div>`;
  }
}

function renderCrosswalk(result) {
  const summary = $('io-crosswalk-summary');
  const matches = $('io-match-list');
  const heading = $('io-match-heading');
  if (!summary || !matches) return;

  if (!result) {
    summary.textContent = 'No OCR run yet.';
    matches.textContent = 'Add panel sets, drop PDFs, run OCR.';
    return;
  }

  const cw = result.crosswalk || {};
  const ocrPages = (result.ocr || []).reduce((n, o) => n + (o.pages_ocrd || 0), 0);
  const tok = (result.ocr || []).reduce((n, o) => n + (o.token_count || 0), 0);
  const sets = result.print_set_count || (result.print_sets || []).length || 0;

  const rm = result.remote_merge || {};
  const ocrFiles = (result.ocr || []).map((o) => {
    const base = String(o.file || o.saved_as || '').split(/[/\\]/).pop();
    const err = o.error ? ` ERR` : '';
    return `${base || '?'}: ${o.pages_ocrd || 0}p / ${o.token_count || 0} tok${err}`;
  });
  summary.innerHTML = `
    <div class="space-y-1.5 text-xs">
      <div class="text-emerald-300 font-semibold text-sm">PDF ↔ tar.gz compare</div>
      <div><span class="text-emerald-400 font-semibold text-base">${cw.matched_count || 0}</span> names matched
        <span class="text-slate-600">(${cw.coverage_pct || 0}% of ${cw.program_total || 0} program points)</span></div>
      <div class="text-sky-300">
        Remote→master: <strong>${rm.remote_io_count || 0}</strong> I/O ·
        <strong>${rm.remote_rack_count || 0}</strong> racks ·
        <strong>${rm.remote_conveyor_count || 0}</strong> conveyors
      </div>
      <div class="text-slate-400">
        Master local: <span class="text-emerald-400">${cw.master_local_matched || 0}</span> ·
        Remote: <span class="text-sky-400">${cw.remote_io_matched || 0}</span>
      </div>
      <div><span class="text-amber-400">${cw.print_only_count || 0}</span> on prints only ·
        <span class="text-slate-400">${cw.program_only_count || 0}</span> in tar.gz only</div>
      <div class="text-slate-500">${sets} panel(s) · ${ocrPages} pages · ${tok} tokens · ${result.print_vfd_param_count || 0} VFD params from prints</div>
      ${ocrFiles.length ? `<div class="text-[10px] text-slate-600 mt-1 max-h-16 overflow-y-auto leading-relaxed">${ocrFiles.map((l) => escapeHtml(l)).join('<br>')}</div>` : ''}
      <div class="text-[10px] text-cyan-600/80">Use tabs below: <strong>vs tar.gz</strong> = matches · <strong>Print only</strong> / <strong>tar.gz only</strong> = gaps</div>
    </div>`;

  // Default to match list so user immediately sees compare output
  ioState.crosswalkTab = ioState.crosswalkTab || 'matched';
  renderCrosswalkList(cw);
  updateRecontrolReady();
}

function renderCrosswalkList(cw) {
  const matches = $('io-match-list');
  const heading = $('io-match-heading');
  if (!matches) return;
  const tab = ioState.crosswalkTab || 'matched';

  document.querySelectorAll('.cw-tab').forEach((b) => {
    const on = b.dataset.cwTab === tab;
    b.className = on
      ? 'cw-tab text-[10px] px-2 py-1 rounded-lg bg-slate-800 text-cyan-300'
      : 'cw-tab text-[10px] px-2 py-1 rounded-lg bg-slate-900 text-slate-500';
  });

  if (tab === 'remote_merge') {
    if (heading) heading.textContent = 'Remote → master (I/O names + racks + conveyors)';
    const rm = ioState.ocrResult?.remote_merge || {};
    const ios = rm.remote_io_names || [];
    const racks = rm.remote_racks || [];
    const convs = rm.remote_conveyors || [];
    if (!ios.length && !racks.length && !convs.length) {
      matches.innerHTML = '<div class="text-slate-500">No remote merge data yet — add remote panels, OCR, then open this tab.</div>';
      return;
    }
    let html = '';
    if (rm.note) html += `<div class="text-[10px] text-slate-500 mb-2 leading-relaxed">${escapeHtml(rm.note)}</div>`;
    html += `<div class="text-sky-400 font-semibold mb-1">Remote I/O names (${rm.remote_io_count || ios.length}) — add to master</div>`;
    html += ios.slice(0, 80).map((r) => `
      <div class="border-b border-slate-800/80 py-0.5">
        <span class="text-cyan-300">${escapeHtml(r.io_name)}</span>
        <span class="text-slate-600"> · ${(r.panels || []).join(', ')}</span>
      </div>`).join('') || '<div class="text-slate-600 mb-2">None</div>';
    html += `<div class="text-sky-400 font-semibold mt-3 mb-1">Remote racks (${rm.remote_rack_count || racks.length})</div>`;
    html += racks.slice(0, 40).map((r) => `
      <div class="border-b border-slate-800/80 py-0.5">
        <span class="text-amber-300">${escapeHtml(r.rack_name)}</span>
        <span class="text-slate-600"> · ${(r.panels || []).join(', ')}</span>
      </div>`).join('') || '<div class="text-slate-600 mb-2">None</div>';
    html += `<div class="text-sky-400 font-semibold mt-3 mb-1">Remote conveyors + VFD params (${rm.remote_conveyor_count || convs.length})</div>`;
    html += convs.slice(0, 40).map((c) => `
      <div class="border border-slate-800 rounded-lg p-2 mb-1 bg-[#101820]">
        <div class="text-emerald-300 font-semibold">${escapeHtml(c.conveyor_name)}</div>
        <div class="text-[10px] text-slate-600">${(c.panels || []).join(', ')} · ${c.vfd_param_count || 0} VFD params</div>
        ${(c.vfd_params || []).slice(0, 6).map((vp) =>
          `<div class="text-[10px] text-amber-200/90 pl-1">${escapeHtml(vp.param)} = ${escapeHtml(vp.display || vp.value || '')}</div>`
        ).join('')}
      </div>`).join('') || '<div class="text-slate-600">None</div>';
    matches.innerHTML = html;
    return;
  }

  if (tab === 'panels') {
    if (heading) heading.textContent = 'By panel set';
    const panels = cw.panels || [];
    if (!panels.length) {
      matches.innerHTML = '<div class="text-slate-500">No panel stats yet.</div>';
      return;
    }
    matches.innerHTML = panels.map((p) => `
      <div class="border border-slate-800 rounded-lg p-2 mb-1.5 bg-[#101820]">
        <div class="font-semibold text-slate-200">${escapeHtml(p.panel)}
          <span class="text-[10px] ${p.role === 'master' ? 'text-emerald-400' : 'text-sky-400'} ml-1">${p.role}</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">
          ${p.files} file(s) · ${p.pages_ocrd} pages · ${p.tokens} tokens ·
          <span class="text-emerald-400">${p.matched_io}</span> matched ·
          <span class="text-amber-400">${p.print_only}</span> print-only
        </div>
      </div>`).join('');
    return;
  }

  if (tab === 'print_only') {
    if (heading) heading.textContent = 'On prints but not in tar.gz program';
    const rows = (cw.print_only_tokens || []).slice(0, 120);
    if (!rows.length) {
      matches.innerHTML = '<div class="text-slate-500">No unmatched print tokens (or OCR not run).</div>';
      return;
    }
    matches.innerHTML = rows.map((m) => `
      <div class="border-b border-slate-800/80 py-1">
        <span class="text-amber-400">${escapeHtml(m.token)}</span>
        <span class="text-slate-600"> · ${escapeHtml(m.panel || '')}</span>
        <span class="text-slate-700"> ${escapeHtml(m.print_file || '')}</span>
      </div>`).join('');
    return;
  }

  if (tab === 'program_only') {
    if (heading) heading.textContent = 'In tar.gz program but not found on prints';
    const rows = (cw.program_only || []).slice(0, 120);
    if (!rows.length) {
      matches.innerHTML = '<div class="text-slate-500">All sampled program tags appeared on prints (or no RUN).</div>';
      return;
    }
    matches.innerHTML = rows.map((m) => `
      <div class="border-b border-slate-800/80 py-1">
        <span class="text-slate-300">${escapeHtml(m.fortna_name || m.program_tag || '')}</span>
        <span class="text-slate-600">${escapeHtml(m.fortna_address || '')}</span>
        <span class="text-slate-500"> ${escapeHtml(m.device_class || '')}</span>
      </div>`).join('');
    return;
  }

  // matched
  if (heading) heading.textContent = 'Matched print ↔ program I/O';
  const rows = (cw.matched || []).slice(0, 150);
  if (!rows.length) {
    matches.innerHTML = '<div class="text-slate-500">No matches yet — load RUN + panel PDFs, then OCR.</div>';
    return;
  }
  matches.innerHTML = rows.map((m) => {
    const scope = m.scope_hint || '';
    const scopeCls = scope === 'master_local' ? 'text-emerald-400' : scope === 'remote_io' ? 'text-sky-400' : 'text-amber-400';
    const panels = (m.panels || [m.panel]).filter(Boolean).join(', ');
    return `
    <div class="border-b border-slate-800/80 py-1">
      <span class="text-cyan-400">${escapeHtml(m.print_token)}</span>
      <span class="text-slate-600">→</span>
      <span class="text-emerald-400">${escapeHtml(m.fortna_name || m.program_tag || '')}</span>
      <span class="text-slate-600">${escapeHtml(m.fortna_address || '')}</span>
      <span class="${scopeCls} text-[10px]"> ${escapeHtml(scope)}</span>
      <div class="text-[10px] text-slate-600">${escapeHtml(panels)} · ${escapeHtml(m.device_class || '')}</div>
    </div>`;
  }).join('');
}

async function refreshIoBanks() {
  if (!state.workspace) {
    renderIoBanks({ success: false, message: 'No RUN loaded. Import on Workspace first.' });
    renderHardwareIo({ success: false, message: 'No RUN loaded' });
    return;
  }
  if ($('io-banks-status')) {
    $('io-banks-status').textContent = 'Loading…';
    $('io-banks-status').className = 'status-pill status-busy';
  }
  const res = await fortnaAPI.getIoBanks();
  renderIoBanks(res);
  // Also load Hardware / I/O resolver tree (same active RUN)
  refreshHardwareIo().catch(() => {});
}

function hwModuleKey(rioName, slot) {
  return `${rioName || ''}::${slot}`;
}

function findHwModule(model, key) {
  if (!model || !key) return null;
  for (const ad of model.adapters || []) {
    for (const mod of ad.modules || []) {
      if (hwModuleKey(ad.rio_name, mod.slot) === key) {
        return { adapter: ad, module: mod };
      }
    }
  }
  return null;
}

function renderHardwareIo(data) {
  const status = $('hw-io-status');
  const ctrl = $('hw-io-controller');
  const racks = $('hw-io-racks');
  const sel = $('hw-io-panel-select');
  const statsEl = $('hw-io-stats');
  if (!racks) return;

  if (!data || !data.success) {
    ioState.hardwareIo = null;
    ioState.hardwareTreeExpanded = null;
    ioState._hwTreeInited = false;
    if (status) {
      status.textContent = 'No RUN';
      status.className = 'status-pill status-idle';
    }
    if (ctrl) ctrl.textContent = 'Controller: —';
    racks.innerHTML = `<div class="text-sm text-slate-500 py-10 text-center">${escapeHtml(data?.message || 'Load a RUN to show Hardware / I/O.')}</div>`;
    if ($('hw-io-tree')) {
      $('hw-io-tree').innerHTML = `<div class="text-sm text-slate-500 py-6 text-center px-2">${escapeHtml(data?.message || 'Load a RUN to show the resolver tree.')}</div>`;
    }
    if ($('hw-io-channel-table')) {
      $('hw-io-channel-table').innerHTML = 'Select a module on the rack to list channels.';
    }
    if ($('hw-io-module-detail')) {
      $('hw-io-module-detail').innerHTML = 'Select a module for the vertical terminal face (CH0●── …).';
    }
    if ($('hw-io-wiring')) {
      $('hw-io-wiring').textContent = 'Wiring diagram unavailable until a module is selected.';
    }
    try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    return;
  }

  ioState.hardwareIo = data;
  const machine = data.controller?.machine || data.machine || '—';
  if (status) {
    status.textContent = 'CAD · resolver';
    status.className = 'status-pill status-ready';
  }
  if (ctrl) ctrl.textContent = `Controller: ${machine}`;

  // Panel select — Configio evidence only + All Panels (never invent CPs)
  const panels = data.control_panels?.panels || [];
  const allLabel = data.control_panels?.all_panels_label || 'All Panels';
  if (sel) {
    const prev = ioState.hardwarePanelFilter || '__all__';
    sel.innerHTML = `<option value="__all__">${escapeHtml(allLabel)}</option>`
      + panels.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
    sel.value = (prev === '__all__' || panels.includes(prev)) ? prev : '__all__';
    ioState.hardwarePanelFilter = sel.value;
  }

  const st = data.stats || {};
  if (statsEl) {
    statsEl.innerHTML = [
      `${st.adapter_count ?? (data.adapters || []).length} adapters`,
      `${st.word_count ?? '—'} words`,
      `${(data.unresolved_words || []).length} unresolved`,
      `${st.by_word_bit_count ?? '—'} channels`,
    ].map((t) => `<span class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800">${escapeHtml(t)}</span>`).join('');
  }

  renderHardwareRacks();
  renderHardwareModuleDetail();
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
}

function adaptersForSelectedPanel(model) {
  if (!model) return [];
  const filter = ioState.hardwarePanelFilter || '__all__';
  if (filter === '__all__') return model.adapters || [];
  const byPanel = model.control_panels?.adapters_by_panel || {};
  if (byPanel[filter]) return byPanel[filter];
  return (model.adapters || []).filter((a) => a.panel === filter);
}

/** Vendor from resolver module only; AB 1794/1734 family → "1"; else "—". Never invent. */
function hwModuleVendor(mod) {
  if (!mod) return '—';
  if (mod.vendor != null && String(mod.vendor).trim() !== '') return String(mod.vendor).trim();
  const cat = String(mod.catalog || mod.type || '');
  if (/^1794([-_]|$)/i.test(cat) || /^1734([-_]|$)/i.test(cat) || /^1738([-_]|$)/i.test(cat)) return '1';
  return '—';
}

function hwEthernetLabel(model) {
  const c = model?.controller || {};
  const name = c.enet_name || c.ethernet_name || c.enet || model?.enet_name || '';
  return name ? String(name) : 'Ethernet';
}

function ensureHwTreeExpandedSet() {
  if (!(ioState.hardwareTreeExpanded instanceof Set)) {
    ioState.hardwareTreeExpanded = new Set();
  }
  return ioState.hardwareTreeExpanded;
}

/** Scroll selected module face into rack viewport and matching tree row into view. */
function scrollSelectedHwModuleIntoView() {
  const key = ioState.selectedHwModuleKey;
  if (!key) return;
  try {
    const match = (el) => el.getAttribute('data-hw-mod') === key;
    const racks = $('hw-io-racks');
    if (racks) {
      const faces = [...racks.querySelectorAll('[data-hw-mod]')].filter(match);
      const face = faces.find((el) =>
        el.matches('.flex-adapter, .flex-io, .point-adapter, .point-module')) || faces[0];
      face?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
    const tree = $('hw-io-tree');
    if (tree) {
      const rows = [...tree.querySelectorAll('[data-hw-mod]')].filter(match);
      const row = rows.find((el) => el.classList.contains('hw-mod')) || rows[0];
      row?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
  } catch (_) { /* ignore */ }
}

function bindHwModuleClicks(root) {
  if (!root) return;
  // Hardware tree — AENT expand/collapse
  root.querySelectorAll('[data-hw-tree-toggle]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const rio = btn.getAttribute('data-hw-tree-toggle') || '';
      if (!rio) return;
      const set = ensureHwTreeExpandedSet();
      if (set.has(rio)) set.delete(rio);
      else set.add(rio);
      // Selecting AENT keeps tree ↔ rack highlight in sync (expand or collapse)
      const modKey = btn.getAttribute('data-hw-mod') || '';
      if (modKey) {
        ioState.selectedHwModuleKey = modKey;
        ioState.selectedHwChannel = null;
      }
      renderHardwareRacks();
      renderHardwareModuleDetail();
      scrollSelectedHwModuleIntoView();
    });
  });
  root.querySelectorAll('[data-hw-mod]').forEach((btn) => {
    if (btn.hasAttribute('data-hw-tree-toggle')) return;
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      ioState.selectedHwModuleKey = btn.getAttribute('data-hw-mod') || '';
      ioState.selectedHwChannel = null;
      // Ensure parent AENT is expanded in the tree
      const parent = btn.closest('[data-hw-tree-rio]');
      if (parent) {
        const rio = parent.getAttribute('data-hw-tree-rio') || '';
        if (rio) ensureHwTreeExpandedSet().add(rio);
      }
      const card = btn.closest('[data-hw-rio]');
      if (card) {
        const rio = card.getAttribute('data-hw-rio') || '';
        if (rio) ensureHwTreeExpandedSet().add(rio);
      }
      renderHardwareRacks();
      renderHardwareModuleDetail();
      scrollSelectedHwModuleIntoView();
    });
  });
}

/** Physical module face — family dispatcher (1794 FLEX / 1734 POINT). */
function renderFlexModuleCard(ad, mod) {
  const key = hwModuleKey(ad.rio_name, mod.slot);
  const opts = {
    selected: key === ioState.selectedHwModuleKey,
    moduleKey: key,
  };
  if (globalThis.HardwareFamily && typeof HardwareFamily.renderModule === 'function') {
    return HardwareFamily.renderModule(ad, mod, opts);
  }
  if (!globalThis.FlexRack || typeof FlexRack.renderModule !== 'function') {
    return `<button type="button" data-hw-mod="${escapeHtml(key)}" class="flex-phys-mod flex-phys-mod--io">
      <span style="color:#94a3b8;font-size:11px;padding:8px;line-height:1.3">Hardware rack renderer missing</span>
    </button>`;
  }
  return FlexRack.renderModule(ad, mod, opts);
}

function renderHardwareRacksFlex(adapters) {
  const opts = {
    selectedKey: ioState.selectedHwModuleKey || '',
    moduleKeyFn: hwModuleKey,
  };
  // Family registry dispatches 1794→FlexRack, 1734→PointRack
  if (globalThis.HardwareFamily && typeof HardwareFamily.renderRacks === 'function') {
    return HardwareFamily.renderRacks(adapters, opts);
  }
  if (!globalThis.FlexRack || typeof FlexRack.renderRacks !== 'function') {
    return `<div class="text-sm text-slate-500 py-6 text-center">Hardware rack renderer not loaded.</div>`;
  }
  return FlexRack.renderRacks(adapters, opts);
}

function renderHardwareRacksTree(model, adapters) {
  const machine = model.controller?.machine || model.machine || '—';
  const enet = hwEthernetLabel(model);
  const expanded = ensureHwTreeExpandedSet();
  // First paint: expand all AENTs so the tree matches the Studio-like screenshot
  if (!ioState._hwTreeInited) {
    adapters.forEach((ad) => { if (ad.rio_name) expanded.add(ad.rio_name); });
    ioState._hwTreeInited = true;
  }
  const rows = [];
  rows.push(`<div class="hw-io-tree-row"><span class="hw-io-tree-tw">⌄</span><span class="hw-io-tree-ctrl">${escapeHtml(machine)}</span></div>`);
  rows.push(`<div class="hw-io-tree-row" style="padding-left:18px"><span class="hw-io-tree-tw">›</span><span class="hw-io-tree-enet">Ethernet (${escapeHtml(enet)})</span></div>`);

  adapters.forEach((ad) => {
    const aent = (ad.modules || []).find((m) => m.is_adapter_card);
    const aentCat = aent ? (aent.catalog || aent.type || '1794-AENT') : (ad.eipcfg_name || ad.name || 'AENT');
    const ip = ad.targetip || '';
    const panel = ad.panel || '';
    const rio = ad.rio_name || '';
    const open = expanded.has(rio);
    const aentKey = aent ? hwModuleKey(ad.rio_name, aent.slot) : '';
    const aentSelected = aentKey && aentKey === ioState.selectedHwModuleKey;
    const ioMods = [...(ad.modules || [])]
      .filter((m) => !m.is_adapter_card)
      .sort((a, b) => (Number(a.slot) || 0) - (Number(b.slot) || 0));

    rows.push(`<div data-hw-tree-rio="${escapeHtml(rio)}">
      <button type="button" class="hw-io-tree-row hw-aent-toggle ${aentSelected ? 'hw-selected' : ''}"
        data-hw-tree-toggle="${escapeHtml(rio)}"
        ${aentKey ? `data-hw-mod="${escapeHtml(aentKey)}"` : ''}
        title="Click to ${open ? 'collapse' : 'expand'} modules on ${escapeHtml(rio)}"
        style="padding-left:18px">
        <span class="hw-io-tree-tw">${open ? '⌄' : '›'}</span>
        <span class="hw-io-tree-ok">▣</span>
        <span class="hw-io-tree-rio">${escapeHtml(rio || '—')}</span>
        <span class="text-slate-500"> ${escapeHtml(aentCat)}</span>
        ${ip ? `<span class="text-slate-600"> · ${escapeHtml(ip)}</span>` : ''}
        ${panel ? `<span class="text-slate-600"> · ${escapeHtml(panel)}</span>` : ''}
      </button>
      <div class="hw-io-tree-children ${open ? 'open' : ''}">`);

    // Show AENT slot 0 as first child when present
    if (aent) {
      const key = hwModuleKey(ad.rio_name, aent.slot);
      const selected = key === ioState.selectedHwModuleKey;
      rows.push(`<button type="button" data-hw-mod="${escapeHtml(key)}"
        class="hw-io-tree-row hw-mod ${selected ? 'hw-selected' : ''}"
        style="padding-left:40px"
        title="${escapeHtml(aentCat)}">
        <span class="text-slate-500">▥ [${aent.slot ?? 0}]</span>
        <span class="text-slate-200"> ${escapeHtml(aentCat)}</span>
      </button>`);
    }

    ioMods.forEach((mod) => {
      const key = hwModuleKey(ad.rio_name, mod.slot);
      const selected = key === ioState.selectedHwModuleKey;
      const used = mod.channels_used ?? (mod.channels || []).length;
      const total = mod.channel_capacity || 0;
      const cat = mod.catalog || mod.type || '—';
      const chLabel = total ? `${used}/${total}` : `${used}`;
      rows.push(`<button type="button" data-hw-mod="${escapeHtml(key)}"
        class="hw-io-tree-row hw-mod ${selected ? 'hw-selected' : ''}"
        style="padding-left:40px"
        title="${escapeHtml(cat)} slot ${mod.slot}">
        <span class="text-slate-500">▥ [${mod.slot ?? '—'}]</span>
        <span class="text-slate-200"> ${escapeHtml(cat)}</span>
        <span class="text-slate-600"> · ${escapeHtml(chLabel)}</span>
      </button>`);
    });

    rows.push('</div></div>');
  });

  return `<div class="hw-io-tree">${rows.join('')}</div>`;
}

function renderHardwareRacks() {
  const racks = $('hw-io-racks');
  const tree = $('hw-io-tree');
  const model = ioState.hardwareIo;
  if (!racks || !model) return;
  let adapters = adaptersForSelectedPanel(model);
  const rioSel = $('hw-io-rio-select');
  // Populate Remote I/O dropdown from proven adapters only
  if (rioSel) {
    const prev = ioState.hardwareRioFilter || rioSel.value || '__all__';
    const opts = ['<option value="__all__">All adapters</option>']
      .concat(adapters.map((a) =>
        `<option value="${escapeHtml(a.rio_name || '')}">${escapeHtml(a.rio_name || a.name || '')}</option>`));
    rioSel.innerHTML = opts.join('');
    const ok = prev === '__all__' || adapters.some((a) => a.rio_name === prev);
    rioSel.value = ok ? prev : '__all__';
    ioState.hardwareRioFilter = rioSel.value;
    if (!rioSel._hwBound) {
      rioSel._hwBound = true;
      rioSel.addEventListener('change', () => {
        ioState.hardwareRioFilter = rioSel.value || '__all__';
        renderHardwareRacks();
        renderHardwareModuleDetail();
      });
    }
  }
  if (ioState.hardwareRioFilter && ioState.hardwareRioFilter !== '__all__') {
    adapters = adapters.filter((a) => a.rio_name === ioState.hardwareRioFilter);
  }
  if (!adapters.length) {
    const empty = `<div class="text-sm text-slate-500 py-6 text-center">No adapters for this control panel (Configio evidence).</div>`;
    racks.innerHTML = empty;
    if (tree) tree.innerHTML = empty;
    return;
  }

  // Primary: CAD FLEX assembly in center; Studio-like tree on the left
  racks.innerHTML = renderHardwareRacksFlex(adapters);
  if (tree) tree.innerHTML = renderHardwareRacksTree(model, adapters);
  bindHwModuleClicks(racks);
  bindHwModuleClicks(tree);
}

/** Channel endpoint label: effective (engineer) name, RUN source, SPARE, or UNRESOLVED OWNER.
 * Gate D/K: "SPARE — click to name" ONLY for genuine spare — never for failed owner resolution.
 */
function hwChannelEndpointLabel(ch) {
  if (!ch) {
    // No model channel — not a proven spare (capacity hole / unmapped bit)
    return {
      text: 'UNRESOLVED OWNER',
      kind: 'warn',
      source: '',
      engineer: '',
      generate: true,
      ownerState: 'UNRESOLVED_OWNER',
    };
  }
  const ownerState = String(ch.owner_state || ch.resolution_status || '').toUpperCase();
  const engineer = String(
    ch.engineerName
    || (ch.logical_endpoint?.engineer_override ? (ch.logical_endpoint?.name || '') : '')
    || ch.engineering_owner
    || ''
  ).trim();
  const source = String(
    ch.sourceName
    || ch.logical_endpoint?.source_name
    || (!engineer ? (ch.logical_endpoint?.name || '') : '')
    || ''
  ).trim();
  const effective = String(
    ch.effectiveName || engineer || source || ch.logical_endpoint?.name || ch.engineering_owner || ''
  ).trim();
  const generate = ch.generate !== false && !ch.muted;

  // Gate D: UNRESOLVED_OWNER is never displayed as SPARE
  if (ownerState === 'UNRESOLVED_OWNER' || ch.unresolved === true || ch.is_unresolved === true) {
    if (effective && !/^(SPARE|UNRESOLVED)/i.test(effective)) {
      return {
        text: effective,
        kind: 'ok',
        source,
        engineer: engineer || '',
        generate,
        overridden: !!(engineer && engineer !== source),
        ownerState: 'ASSIGNED',
      };
    }
    return {
      text: 'UNRESOLVED OWNER',
      kind: 'warn',
      source,
      engineer: engineer || '',
      generate,
      ownerState: 'UNRESOLVED_OWNER',
    };
  }

  if (effective && !/^(SPARE)$/i.test(effective)) {
    return {
      text: effective,
      kind: 'ok',
      source,
      engineer: engineer || '',
      generate,
      overridden: !!(engineer && engineer !== source),
      ownerState: ownerState || 'ASSIGNED',
    };
  }

  const truly = (typeof FlexRack !== 'undefined' && FlexRack.isTrulyUnresolved)
    ? FlexRack.isTrulyUnresolved(ch)
    : false;
  if (truly) {
    return {
      text: 'UNRESOLVED OWNER',
      kind: 'warn',
      source: '',
      engineer: '',
      generate,
      ownerState: 'UNRESOLVED_OWNER',
    };
  }
  // SPARE face only for explicit spare evidence — never default occupied/unknown → SPARE
  if (
    ownerState === 'PROVEN_SPARE'
    || ownerState === 'ENGINEER_SPARE'
    || ch.configio_spare === true
    || ch.is_spare === true
  ) {
    const spareState = ownerState === 'ENGINEER_SPARE' ? 'ENGINEER_SPARE' : 'PROVEN_SPARE';
    return {
      text: 'SPARE',
      kind: 'spare',
      source: source || '',
      engineer: '',
      generate,
      ownerState: spareState,
    };
  }
  // Mapped unused terminal — not proven spare, not unresolved owner
  if (ownerState === 'UNUSED_MAPPED' || ch.is_unused_mapped === true) {
    return {
      text: 'UNUSED',
      kind: 'unused',
      source: source || '',
      engineer: engineer || '',
      generate,
      ownerState: 'UNUSED_MAPPED',
    };
  }
  // Occupied/claimed or unknown without spare proof → UNRESOLVED OWNER (never SPARE)
  return {
    text: 'UNRESOLVED OWNER',
    kind: 'warn',
    source: source || '',
    engineer: engineer || '',
    generate,
    ownerState: ownerState || 'UNRESOLVED_OWNER',
  };
}
function hwChannelPhysicalAddress(ad, mod, bit, ch) {
  if (ch?.physical_address) return ch.physical_address;
  const dir = (mod.direction || 'I').charAt(0).toUpperCase();
  return `${ad.rio_name}:${dir}.Data[${mod.data_index ?? mod.slot ?? '?'}].${bit}`;
}

function hwChannelDirectionLabel(mod) {
  const cat = mod.catalog || mod.type || '';
  if (mod.direction === 'O' || /OA|OB|OW/i.test(cat)) return 'OUTPUT';
  return 'INPUT';
}

async function saveHwChannelOverride({ address, name, sourceName, generate }) {
  if (typeof fortnaAPI?.saveHardwareIoChannel !== 'function') {
    log('saveHardwareIoChannel missing — relaunch Site Forge desktop app', 'err');
    return { success: false, message: 'API missing' };
  }
  const payload = {
    address,
    projectIdentity: state.projectIdentity || null,
  };
  if (name !== undefined) payload.name = name;
  if (sourceName) payload.sourceName = sourceName;
  if (generate !== undefined) payload.generate = !!generate;
  const res = await fortnaAPI.saveHardwareIoChannel(payload);
  if (!res?.success) {
    log(res?.message || 'Failed to save channel override', 'err');
  }
  return res;
}

/** Patch in-memory HardwareIOModel channel after a successful override save. */
function patchHwChannelInModel(address, patch) {
  const model = ioState.hardwareIo;
  if (!model?.adapters || !address) return;
  for (const ad of model.adapters) {
    for (const mod of ad.modules || []) {
      for (const ch of mod.channels || []) {
        if (ch.physical_address === address) {
          Object.assign(ch, patch);
          if (patch.engineerName) {
            ch.logical_endpoint = {
              ...(ch.logical_endpoint || {}),
              name: patch.engineerName,
              source_name: patch.sourceName || ch.sourceName || '',
              engineer_override: true,
            };
            ch.effectiveName = patch.engineerName;
          } else if (patch.engineerName === '' || patch.engineerName === null) {
            const src = patch.sourceName || ch.sourceName || '';
            ch.engineerName = null;
            ch.effectiveName = src || null;
            if (ch.logical_endpoint) {
              ch.logical_endpoint = {
                ...ch.logical_endpoint,
                name: src || ch.logical_endpoint.source_name || '',
                engineer_override: false,
              };
            }
          }
          if (patch.generate !== undefined) {
            ch.generate = !!patch.generate;
            ch.muted = !patch.generate;
          }
          return;
        }
      }
      // Spare with no channel record yet — create one so override sticks in UI
      if ((mod.channels || []).every((c) => c.physical_address !== address)) {
        const m = String(address).match(/\.Data\[(\d+)\]\.(\d+)$/);
        const bit = m ? Number(m[2]) : null;
        if (bit == null) continue;
        const dir = (mod.direction || 'I').charAt(0);
        const expect = `${ad.rio_name}:${dir}.Data[${mod.data_index ?? mod.slot}].${bit}`;
        if (expect !== address) continue;
        mod.channels = mod.channels || [];
        mod.channels.push({
          fortna_bit: bit,
          physical_address: address,
          direction: mod.direction,
          sourceName: patch.sourceName || '',
          engineerName: patch.engineerName || null,
          effectiveName: patch.engineerName || patch.sourceName || null,
          generate: patch.generate !== false,
          muted: patch.generate === false,
          logical_endpoint: patch.engineerName
            ? { name: patch.engineerName, engineer_override: true, source_name: patch.sourceName || '' }
            : null,
        });
        return;
      }
    }
  }
}

function hwChannelRows(mod) {
  const channels = mod.channels || [];
  const byBit = new Map();
  for (const ch of channels) {
    const bit = ch.fortna_bit;
    if (bit == null || bit === '') continue;
    byBit.set(Number(bit), ch);
  }
  const visual = (typeof FlexRack !== 'undefined' && FlexRack.resolveVisual)
    ? FlexRack.resolveVisual(mod)
    : '';
  const cap = (typeof FlexRack !== 'undefined' && FlexRack.channelCapacity)
    ? FlexRack.channelCapacity(mod, visual)
    : (Number(mod.channel_capacity) || channels.length);
  const maxBit = channels.reduce((m, ch) => Math.max(m, Number(ch.fortna_bit) || 0), -1);
  const n = cap > 0 ? cap : (maxBit >= 0 ? maxBit + 1 : 0);
  const rows = [];
  for (let i = 0; i < n; i += 1) {
    rows.push({ bit: i, ch: byBit.get(i) || null });
  }
  return rows;
}

function renderHardwareChannelTable(ad, mod) {
  if (mod.is_adapter_card) {
    return `<div class="hw-ch-table-wrap"><div class="hw-ch-table-head">
      <div class="title" data-adapter-id="${escapeHtml(ad.rio_name || '')}" data-slot="${escapeHtml(String(mod.slot ?? 0))}">Adapter <span class="mono">${escapeHtml(ad.rio_name || '')}</span> · Slot <span class="mono">${escapeHtml(String(mod.slot ?? 0))}</span> · ${escapeHtml(mod.catalog || 'AENT')}</div>
      <div class="sub">Ethernet adapter — no digital channels</div>
    </div></div>`;
  }
  const rows = hwChannelRows(mod);
  if (!rows.length) {
    return `<div class="p-3 text-slate-500 text-[11px]">No channels for this module in HardwareIOModel.</div>`;
  }
  const selBit = ioState.selectedHwChannel;
  const cat = mod.catalog || mod.type || '';
  const typ = hwChannelDirectionLabel(mod);
  const body = rows.map(({ bit, ch }) => {
    const ep = hwChannelEndpointLabel(ch);
    const selected = selBit != null && Number(bit) === Number(selBit);
    const addr = hwChannelPhysicalAddress(ad, mod, bit, ch);
    // Gate 6: clear ASSIGNED / UNRESOLVED OWNER / UNUSED_MAPPED / PROVEN_SPARE distinction
    const owner = String(ep.ownerState || '').toUpperCase();
    const statusCls = !ep.generate ? 'hw-ch-status-spare'
      : ep.kind === 'ok' || owner === 'ASSIGNED' ? 'hw-ch-status-ok'
      : ep.kind === 'unused' || owner === 'UNUSED_MAPPED' ? 'hw-ch-status-unused'
      : ep.kind === 'warn' || owner === 'UNRESOLVED_OWNER' ? 'hw-ch-status-warn'
      : 'hw-ch-status-spare';
    const statusTxt = !ep.generate ? '○ Muted'
      : (ep.kind === 'ok' || owner === 'ASSIGNED')
        ? (ep.overridden ? '● ASSIGNED (engineer)' : '● ASSIGNED')
      : (ep.kind === 'unused' || owner === 'UNUSED_MAPPED') ? '○ UNUSED_MAPPED'
      : (ep.kind === 'warn' || owner === 'UNRESOLVED_OWNER') ? '● UNRESOLVED OWNER'
      : owner === 'ENGINEER_SPARE' ? '○ ENGINEER_SPARE'
      : '○ PROVEN_SPARE';
    const rowTone = !ep.generate ? ' hw-ch-muted'
      : (ep.kind === 'unused' || owner === 'UNUSED_MAPPED') ? ' hw-ch-unused'
      : (ep.kind === 'warn' || owner === 'UNRESOLVED_OWNER') ? ' hw-ch-unresolved'
      : '';
    const nameVal = (ep.kind === 'spare' || ep.kind === 'warn' || ep.kind === 'unused') && !ep.engineer
      ? ''
      : (ep.text === 'UNUSED' ? '' : ep.text);
    // Gate K: SPARE placeholder only for genuine spare — never for UNRESOLVED OWNER
    const namePlaceholder = ep.kind === 'warn'
      ? 'UNRESOLVED OWNER — assign name'
      : ep.kind === 'unused'
        ? 'UNUSED_MAPPED — mapped bit, no owner'
      : (ep.kind === 'spare' ? 'SPARE — click to name' : (ep.source || 'logical name'));
    return `<tr class="${selected ? 'hw-ch-selected' : ''}${rowTone}" data-hw-ch="${bit}" data-hw-addr="${escapeHtml(addr)}" data-owner-state="${escapeHtml(owner || ep.kind || '')}">
      <td class="mono">${bit}</td>
      <td class="mono text-cyan-200/90">${escapeHtml(addr)}</td>
      <td class="mono text-slate-400">${escapeHtml(typ)}</td>
      <td class="hw-ch-name-cell" onclick="event.stopPropagation()">
        <input type="text" class="hw-ch-name-input mono" data-hw-name="${escapeHtml(addr)}"
          value="${escapeHtml(nameVal === 'SPARE' || nameVal === 'UNUSED' ? '' : nameVal)}"
          placeholder="${escapeHtml(namePlaceholder)}"
          spellcheck="false" autocomplete="off"
          title="${escapeHtml(ep.source ? `RUN source: ${ep.source}` : 'Engineer logical name')}" />
      </td>
      <td class="hw-ch-gen-cell" onclick="event.stopPropagation()" title="Uncheck to mute — keep visible, exclude from IO_MAP">
        <label class="hw-ch-gen-label"><input type="checkbox" class="hw-ch-gen-input" data-hw-gen="${escapeHtml(addr)}" ${ep.generate ? 'checked' : ''} /> Generate</label>
      </td>
      <td class="${statusCls}">${statusTxt}</td>
    </tr>`;
  }).join('');
  return `
    <div class="hw-ch-table-wrap">
      <div class="hw-ch-table-head">
        <div class="title">${escapeHtml(cat)} — ${escapeHtml(typ === 'OUTPUT' ? 'Digital Output' : 'Digital Input')}</div>
        <div class="sub">${escapeHtml(ad.rio_name)} · slot ${mod.slot ?? '—'} · Data[${mod.data_index ?? '—'}] · ${rows.length} channels · Name + Generate are engineer overrides</div>
      </div>
      <table class="hw-ch-table">
        <thead>
          <tr>
            <th>Ch</th>
            <th>Address</th>
            <th>Type</th>
            <th>Name</th>
            <th>Generate</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function renderHardwareTerminalFace(ad, mod) {
  const cat = mod.catalog || mod.type || '';
  const titleEl = $('hw-io-term-title');
  if (titleEl) {
    const ch = ioState.selectedHwChannel;
    const ep = ch != null
      ? hwChannelEndpointLabel((mod.channels || []).find((c) => Number(c.fortna_bit) === Number(ch)))
      : null;
    titleEl.textContent = ch != null
      ? `${ad.rio_name || ''}  |  Channel ${ch}  |  ${ep?.text || '—'}`
      : `${ad.rio_name || ''}  |  ${cat}`;
  }
  if (mod.is_adapter_card) {
    const fam = String(mod.family || ad?.family || '');
    const headLabel = fam === '1734' || /^1734/i.test(cat)
      ? `${cat || '1734-AENTR'} — POINT I/O EtherNet/IP adapter · no digital terminals.`
      : `${cat || '1794-AENT'} — FLEX I/O Ethernet adapter head · no digital terminals.`;
    return `<div class="hw-term-panel">
      <div class="text-slate-500 text-[11px]">${escapeHtml(headLabel)}</div>
    </div>`;
  }
  const rows = hwChannelRows(mod);
  if (!rows.length) {
    return `<div class="hw-term-panel"><div class="text-slate-500 text-[11px]">No proven channels on this module.</div></div>`;
  }
  const sel = ioState.selectedHwChannel;
  const termRows = rows.map(({ bit, ch }) => {
    const ep = hwChannelEndpointLabel(ch);
    const led = ep.kind === 'ok' ? 'on' : ep.kind === 'warn' ? 'warn' : 'off';
    const selected = sel != null && Number(sel) === bit;
    return `<button type="button" class="hw-trow ${selected ? 'selected' : ''}" data-hw-ch="${bit}">
      <div class="hw-tnum">${bit}</div>
      <div class="hw-tscrew"></div>
      <div class="hw-tled ${led}"></div>
    </button>`;
  }).join('');
  const mapRows = rows.map(({ bit, ch }) => {
    const ep = hwChannelEndpointLabel(ch);
    const selected = sel != null && Number(sel) === bit;
    return `<button type="button" class="hw-map-row ${selected ? 'selected' : ''}" data-hw-ch="${bit}">
      <span class="line"></span>
      <span>${escapeHtml(ep.text)}${selected ? ' ← selected' : ''}</span>
    </button>`;
  }).join('');

  let detailHtml = '';
  if (sel != null) {
    const hit = rows.find((r) => r.bit === Number(sel));
    const ch = hit?.ch || null;
    const ep = hwChannelEndpointLabel(ch);
    const addr = hwChannelPhysicalAddress(ad, mod, sel, ch);
    const pep = ch?.physical_endpoint || {};
    const cfg = `${cat.replace(/\/[A-Z]$/i, '')}/${mod.slot ?? pep.module_slot ?? '?'}/${sel}`;
    const typ = hwChannelDirectionLabel(mod);
    const ownerState = ep.ownerState || ch?.owner_state || (ep.kind === 'warn' ? 'UNRESOLVED_OWNER' : (ep.kind === 'spare' ? 'PROVEN_SPARE' : 'ASSIGNED'));
    const statusHtml = !ep.generate
      ? '<span>○ Muted (excluded from IO_MAP)</span>'
      : ep.kind === 'ok' || ownerState === 'ASSIGNED'
        ? `<span class="green">● ${ep.overridden ? 'ASSIGNED (engineer)' : 'ASSIGNED'}</span>`
        : ep.kind === 'unused' || ownerState === 'UNUSED_MAPPED'
          ? '<span class="text-sky-300">○ UNUSED_MAPPED</span>'
        : ep.kind === 'warn' || ownerState === 'UNRESOLVED_OWNER'
          ? '<span class="amber">● UNRESOLVED OWNER</span>'
          : ownerState === 'ENGINEER_SPARE'
            ? '<span>○ ENGINEER_SPARE</span>'
          : '<span>○ PROVEN_SPARE</span>';
    detailHtml = `
      <div class="hw-ch-detail">
        <h3>Channel ${sel} — ${escapeHtml(ep.text)}</h3>
        <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Physical endpoint</div>
        Direction: &nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(typ)} / ${escapeHtml(pep.direction || mod.direction || '—')}<br>
        Module: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(pep.module_type || cat || '—')}<br>
        Slot: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(String(pep.module_slot ?? mod.slot ?? '—'))}<br>
        Channel: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(String(pep.bit ?? sel))}<br>
        PLC Address: &nbsp;&nbsp; ${escapeHtml(pep.channel || addr)}<br>
        ConfigIO: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(cfg)} · word ${escapeHtml(String(ch?.fortna_word ?? pep.bank_word ?? '—'))}<br>
        <div class="text-[10px] uppercase tracking-wider text-slate-500 mt-2 mb-1">Engineering owner</div>
        RUN source: &nbsp;&nbsp;&nbsp; ${escapeHtml(ep.source || ch?.run_source || '—')}<br>
        Owner: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${escapeHtml(ch?.engineering_owner || ep.engineer || ep.text || '—')}<br>
        Owner source: &nbsp; ${escapeHtml(ch?.owner_source || '—')}<br>
        Resolution: &nbsp;&nbsp;&nbsp; ${escapeHtml(ownerState)} · ${statusHtml}<br>
        <span class="text-slate-500">Physical endpoint is immutable. ${ep.kind === 'warn' ? 'UNRESOLVED OWNER is not SPARE — assign a logical name.' : 'Edit Name / Generate in the channel table.'}</span>
      </div>`;
  }

  return `
    <div class="hw-term-panel">
      <div class="hw-term-body">
        <div class="hw-vert-mod">
          <div class="vhead"><b>Allen-Bradley</b><div class="vcat">${escapeHtml(cat)}</div></div>
          <div class="hw-vert-rows">${termRows}</div>
        </div>
        <div class="hw-term-map">${mapRows}</div>
      </div>
      ${detailHtml}
    </div>`;
}

function renderHardwareModuleDetail() {
  const detail = $('hw-io-module-detail');
  const table = $('hw-io-channel-table');
  const model = ioState.hardwareIo;
  if (!detail) return;
  const hit = findHwModule(model, ioState.selectedHwModuleKey);
  if (!hit) {
    detail.innerHTML = 'Select a module for the vertical terminal face.';
    if (table) table.innerHTML = 'Select a module on the rack to list channels.';
    const titleEl = $('hw-io-term-title');
    if (titleEl) titleEl.textContent = 'Module terminals';
    return;
  }
  const { adapter: ad, module: mod } = hit;
  detail.innerHTML = renderHardwareTerminalFace(ad, mod);
  if (table) table.innerHTML = renderHardwareChannelTable(ad, mod);
  const onChClick = (el) => {
    const raw = el.getAttribute('data-hw-ch');
    if (raw == null || raw === '') return;
    ioState.selectedHwChannel = Number(raw);
    renderHardwareModuleDetail();
  };
  detail.querySelectorAll('[data-hw-ch]').forEach((el) => {
    el.addEventListener('click', () => onChClick(el));
  });
  if (table) {
    table.querySelectorAll('tr[data-hw-ch]').forEach((el) => {
      el.addEventListener('click', (ev) => {
        if (ev.target.closest?.('input')) return;
        onChClick(el);
      });
    });
    table.querySelectorAll('.hw-ch-name-input').forEach((inp) => {
      // Prevent Enter→blur double-commit from wiping the engineer name on re-render
      let committing = false;
      let skipBlur = false;
      let lastCommitted = null;
      inp.addEventListener('input', () => { inp.dataset.hwDirty = '1'; });
      const commit = async (reason) => {
        const addr = inp.getAttribute('data-hw-name');
        if (!addr || committing) return;
        const raw = String(inp.value || '').trim();
        // Skip no-op re-commit after Enter already saved the same value
        if (lastCommitted !== null && lastCommitted === raw && reason === 'blur') return;
        committing = true;
        let sourceName = '';
        let chHit = null;
        for (const a of (ioState.hardwareIo?.adapters || model.adapters || [])) {
          for (const m of a.modules || []) {
            const c = (m.channels || []).find((x) => x.physical_address === addr);
            if (c) { chHit = c; break; }
          }
          if (chHit) break;
        }
        // Prefer preserved RUN source — never treat current engineer name as source
        sourceName = String(
          chHit?.sourceName
          || chHit?.logical_endpoint?.source_name
          || (!chHit?.engineerName && !chHit?.logical_endpoint?.engineer_override
            ? (chHit?.logical_endpoint?.name || '')
            : '')
          || ''
        ).trim();
        try {
          // Empty / SPARE / restore-to-source → CLEAR engineer override (purge stale names)
          const clearSentinel = !raw
            || /^(SPARE|N\/A|NONE|—|-)$/i.test(raw)
            || (sourceName && raw.toLowerCase() === sourceName.toLowerCase());
          const nameToSave = clearSentinel ? '' : raw;
          const res = await saveHwChannelOverride({
            address: addr,
            name: nameToSave,
            sourceName,
          });
          if (!res?.success) {
            inp.classList.add('hw-ch-name-invalid');
            committing = false;
            return;
          }
          inp.classList.remove('hw-ch-name-invalid');
          const engOut = clearSentinel ? null : raw;
          const effOut = engOut || sourceName || null;
          // Patch model FIRST so re-render reads cleared/engineer state correctly
          patchHwChannelInModel(addr, {
            engineerName: engOut,
            sourceName,
            effectiveName: effOut,
            generate: chHit?.generate !== false,
          });
          if (!chHit && engOut) {
            // Force stub creation for SPARE bit that was named
            patchHwChannelInModel(addr, {
              engineerName: engOut,
              sourceName: sourceName || '',
              effectiveName: engOut,
              generate: true,
            });
          }
          lastCommitted = nameToSave;
          inp.dataset.hwDirty = '0';
          if (ioState.pendingChannelEdits) delete ioState.pendingChannelEdits[addr];
          // Display: cleared → SPARE/source; else engineer name
          inp.value = engOut || sourceName || 'SPARE';
          skipBlur = true;
          renderHardwareModuleDetail();
          log(
            clearSentinel
              ? `Hardware I/O name cleared → ${addr} (RUN/SPARE; override purged) (${reason})`
              : `Hardware I/O name → ${addr} = ${raw} (logical only; physical ${addr}) (${reason})`,
            'ok',
          );
        } finally {
          committing = false;
        }
      };
      inp.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === 'Tab') {
          // Tab: commit before focus moves so blur does not race a second commit
          // against a re-rendered input (intermittent alias/spare reset).
          if (ev.key === 'Enter') {
            ev.preventDefault();
            ev.stopPropagation();
          }
          skipBlur = true;
          commit(ev.key === 'Enter' ? 'enter' : 'tab');
          if (ev.key === 'Enter') {
            try { inp.blur(); } catch (_) { /* ignore */ }
          }
        }
        if (ev.key === 'Escape') {
          ev.preventDefault();
          skipBlur = true;
          renderHardwareModuleDetail();
        }
      });
      inp.addEventListener('blur', () => {
        if (skipBlur) {
          skipBlur = false;
          return;
        }
        commit('blur');
      });
    });
    table.querySelectorAll('.hw-ch-gen-input').forEach((cb) => {
      cb.addEventListener('change', async () => {
        const addr = cb.getAttribute('data-hw-gen');
        if (!addr) return;
        const generate = !!cb.checked;
        const res = await saveHwChannelOverride({ address: addr, generate });
        if (!res?.success) {
          cb.checked = !generate;
          return;
        }
        patchHwChannelInModel(addr, { generate, muted: !generate });
        renderHardwareModuleDetail();
        log(`Hardware I/O Generate → ${addr} = ${generate ? 'ON' : 'MUTED'}`, 'ok');
      });
    });
  }
}


/** PL-4: in-flight engineer alias/spare edits — survive refresh races. */
if (!ioState.pendingChannelEdits) ioState.pendingChannelEdits = {};

function capturePendingHwChannelEdits() {
  const pending = {};
  document.querySelectorAll('.hw-ch-name-input').forEach((inp) => {
    const addr = inp.getAttribute('data-hw-name');
    if (!addr) return;
    // Always snapshot focused or dirty inputs
    if (document.activeElement === inp || inp.dataset.hwDirty === '1') {
      pending[addr] = String(inp.value || '');
    }
  });
  ioState.pendingChannelEdits = { ...(ioState.pendingChannelEdits || {}), ...pending };
  return ioState.pendingChannelEdits;
}

function reapplyPendingHwChannelEdits() {
  const pending = ioState.pendingChannelEdits || {};
  Object.entries(pending).forEach(([addr, name]) => {
    // PHYSICAL address immutable — only engineer alias metadata restored
    patchHwChannelInModel(addr, {
      engineerName: name && !/^(SPARE|N\/A|NONE|—|-)$/i.test(name) ? name : null,
      effectiveName: name || null,
    });
  });
}

async function refreshHardwareIo() {
  if (!state.workspace) {
    renderHardwareIo({ success: false, message: 'No RUN loaded' });
    return;
  }
  // Do not clobber an in-progress channel rename / spare assignment.
  // PHYSICAL endpoint identity is immutable; engineer alias edits must persist
  // across Enter/Tab/blur — a mid-edit model replace is a known reset race.
  capturePendingHwChannelEdits();
  const activeName = document.activeElement;
  if (
    activeName
    && activeName.classList
    && activeName.classList.contains('hw-ch-name-input')
  ) {
    return;
  }
  if ($('hw-io-status')) {
    $('hw-io-status').textContent = 'Loading…';
    $('hw-io-status').className = 'status-pill status-busy';
  }
  if (typeof fortnaAPI.getHardwareIo !== 'function') {
    renderHardwareIo({ success: false, message: 'getHardwareIo missing — relaunch Site Forge desktop app' });
    return;
  }
  try {
    const res = await fortnaAPI.getHardwareIo();
    // Re-check: focus may have moved into an input while the fetch was in flight
    const stillEditing = document.activeElement?.classList?.contains?.('hw-ch-name-input');
    if (stillEditing) {
      capturePendingHwChannelEdits();
      return;
    }
    renderHardwareIo(res);
    // Re-apply any captured engineer aliases after model replace (physical addr unchanged)
    if (Object.keys(ioState.pendingChannelEdits || {}).length) {
      reapplyPendingHwChannelEdits();
      try { renderHardwareModuleDetail(); } catch (_) { /* ignore */ }
    }
  } catch (e) {
    renderHardwareIo({ success: false, message: e?.message || String(e) });
  }
}

$('hw-io-panel-select')?.addEventListener('change', (e) => {
  ioState.hardwarePanelFilter = e.target?.value || '__all__';
  ioState.selectedHwModuleKey = '';
  renderHardwareRacks();
  renderHardwareModuleDetail();
});

// I/O tab: load RUN tar.gz without using Workspace
const ioRunDrop = $('io-run-dropzone');
if (ioRunDrop) {
  ioRunDrop.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    ioRunDrop.classList.add('dragover');
  });
  ioRunDrop.addEventListener('dragleave', (e) => {
    if (e.target === ioRunDrop || !ioRunDrop.contains(e.relatedTarget)) {
      ioRunDrop.classList.remove('dragover');
    }
  });
  ioRunDrop.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    ioRunDrop.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (!file) return;
    const p = fortnaAPI.getPathForFile(file);
    if (!p) {
      ioLog('Could not read dropped path. Use Browse tar.gz instead.', 'warn');
      return;
    }
    if (!isRunArchivePath(p)) {
      ioLog('Drop a Fortna RUN .tar.gz / .tgz / .zip package.', 'warn');
      return;
    }
    await importRunPackage(p, file.name || p.split(/[/\\]/).pop());
  });
}

$('btn-io-browse-run')?.addEventListener('click', async () => {
  const res = await fortnaAPI.selectArchive({ multi: false });
  if (res.success && res.path) {
    await importRunPackage(res.path, res.path.split(/[/\\]/).pop());
  }
});

$('btn-io-clear-run')?.addEventListener('click', async () => {
  if (!confirm(
    'Clear loaded RUN from Site Forge?\n\n'
    + '• Removes active tar.gz workspace\n'
    + '• Clears banks, Devices (by type), and Merge & Crosswalk\n'
    + '• Original .tar.gz and PDFs on disk are not deleted'
  )) return;
  setBusy(true);
  const res = await fortnaAPI.clearWorkspace();
  setBusy(false);
  if (!res.success) {
    ioLog(res.message || 'Clear failed', 'err');
    // Still wipe UI so the panel is not stuck with 960 stale rows
    resetWorkspaceUi();
    clearDevicesPanelUi();
    clearIoCompareState({ clearDevices: true, clearPanels: false });
    ioLog('Clear reported an error, but device UI was wiped.', 'warn');
    return;
  }
  resetWorkspaceUi();
  clearDevicesPanelUi();
  clearIoCompareState({ clearDevices: true });
  ioLog('RUN cleared — banks, devices, and merge/crosswalk reset.', 'ok');
});

$('btn-io-clear-prints')?.addEventListener('click', () => {
  if (!confirm(
    'Clear all panel print PDFs and OCR compare results?\n\n'
    + 'Master/remote panel assignments are removed. Files on disk are not deleted.\n'
    + '(Device list from tar.gz is kept until you Clear RUN.)'
  )) return;
  clearIoCompareState({ clearPanels: true });
  ioLog('Prints + merge/crosswalk cleared.', 'ok');
});

// Master / remote / selected-panel print drop zones
bindPrintDropZone($('master-dropzone'), 'master');
bindPrintDropZone($('remote-dropzone'), 'remote');
bindPrintDropZone($('prints-dropzone'), 'active');

// Safe to render PLC queue now that ioState exists
try { renderPlcQueue(); } catch (_) { /* ignore */ }
try { updateRecontrolReady(); } catch (_) { /* ignore */ }

$('btn-set-master')?.addEventListener('click', () => {
  setMasterPanel($('master-name-input')?.value || 'Master');
});

$('master-name-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    $('btn-set-master')?.click();
  }
});

$('btn-add-remote')?.addEventListener('click', () => {
  addRemotePanel($('remote-name-input')?.value || '');
  if ($('remote-name-input')) $('remote-name-input').value = '';
});

$('remote-name-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    $('btn-add-remote')?.click();
  }
});

$('btn-browse-master-prints')?.addEventListener('click', async () => {
  const target = getMasterPanel() || setMasterPanel($('master-name-input')?.value || 'Master');
  const res = await fortnaAPI.selectPrints();
  if (res.success && res.paths?.length) addPrintPaths(res.paths, target);
});

$('btn-browse-remote-prints')?.addEventListener('click', async () => {
  const res = await fortnaAPI.selectPrints();
  if (res.success && res.paths?.length) {
    // Multi-select → one remote per file (never master)
    const hit = getActivePanel()?.role === 'remote' ? getActivePanel() : null;
    // Only target active remote if user selected exactly one file; multi = split
    addRemotePrintPaths(res.paths, res.paths.length === 1 ? hit : null);
  }
});

$('btn-browse-prints')?.addEventListener('click', async () => {
  if (!getActivePanel()) setMasterPanel($('master-name-input')?.value || 'Master');
  const res = await fortnaAPI.selectPrints();
  if (res.success && res.paths?.length) {
    const active = getActivePanel();
    if (active?.role === 'remote') addRemotePrintPaths(res.paths, active);
    else addPrintPaths(res.paths, active);
  }
});

$('btn-refresh-banks')?.addEventListener('click', () => refreshIoBanks());

$('device-type-filter')?.addEventListener('change', () => {
  ioState.deviceTypeFilter = $('device-type-filter')?.value || 'all';
  renderDriveTableRows();
});
$('drive-print-only')?.addEventListener('change', () => renderDriveTableRows());
$('btn-print-repo')?.addEventListener('click', () => {
  const panel = $('print-repo-panel');
  if (!panel) return;
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) renderPrintRepository();
});

$('btn-plc-generate')?.addEventListener('click', () => {
  if (plcState.busy) return;
  const hasRun = !!(state.workspace || ioState.banks?.machine);
  const hasPrints = totalPrintFiles() > 0;
  if (!hasRun) {
    plcLog('Load a .tar.gz RUN first (I/O & Prints or queue).', 'warn');
    return;
  }
  if (!hasPrints) {
    plcLog('Assign panel print PDFs on I/O & Prints first.', 'warn');
    return;
  }
  // Prefer active workspace export when RUN is loaded
  runPlcExportActive();
});

// Live OCR page progress from main process
if (typeof fortnaAPI?.onOcrProgress === 'function') {
  fortnaAPI.onOcrProgress((payload) => updateOcrProgressUI(payload));
}

document.querySelectorAll('.cw-tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    ioState.crosswalkTab = btn.dataset.cwTab || 'matched';
    if (ioState.ocrResult?.crosswalk) renderCrosswalkList(ioState.ocrResult.crosswalk);
  });
});

$('btn-run-ocr')?.addEventListener('click', async () => {
  if (totalPrintFiles() === 0 || ioState.busy) return;
  ioState.busy = true;
  const ocrBtn = $('btn-run-ocr');
  const ocrBtnHtml = ocrBtn ? ocrBtn.innerHTML : '';
  if (ocrBtn) {
    ocrBtn.disabled = true;
    ocrBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>OCR running… window stays usable';
  }
  const sets = ioState.panelSets
    .filter((p) => p.paths.length)
    .map((p) => ({ name: p.name, role: p.role, paths: p.paths }));
  ioLog(
    `OCR started: ${sets.length} panel set(s), ${totalPrintFiles()} file(s). `
    + 'Parallel workers + text-first extraction — progress bar updates as pages finish.',
    'info'
  );
  updateOcrProgressUI({
    phase: 'starting',
    pct: 0,
    message: 'Starting OCR…',
    pages_done: 0,
    pages_total: 0,
    file_total: totalPrintFiles(),
  });
  if ($('io-crosswalk-summary')) {
    $('io-crosswalk-summary').innerHTML =
      '<div class="text-amber-400 text-xs">OCR in progress… watch the progress bar above for page status.</div>';
  }
  let res;
  try {
    res = await fortnaAPI.ocrPrints({ sets });
  } catch (e) {
    res = { success: false, message: e?.message || String(e) };
  }
  ioState.busy = false;
  if (ocrBtn) {
    ocrBtn.disabled = totalPrintFiles() === 0;
    ocrBtn.innerHTML = ocrBtnHtml || '<i class="fa-solid fa-code-merge mr-2"></i>OCR · vs tar.gz';
  }
  if (!res.success) {
    ioLog(res.message || 'OCR failed', 'err');
    updateOcrProgressUI({ phase: 'error', pct: 0, message: res.message || 'OCR failed' });
    renderCrosswalk(null);
    return;
  }
  updateOcrProgressUI({
    phase: 'done',
    pct: 100,
    message: `Done — ${res.result?.drives_with_print_params || 0} drive(s) with print VFD params`,
    pages_done: res.result?.ocr_pages_total || 0,
    pages_total: res.result?.ocr_pages_total || 0,
    workers: res.result?.ocr_workers,
  });
  ioState.ocrResult = res.result;
  renderCrosswalk(res.result);
  // Force matched tab so compare results are visible immediately
  ioState.crosswalkTab = 'matched';
  if (res.result?.crosswalk) renderCrosswalkList(res.result.crosswalk);

  // INTEGRATE prints into tar.gz devices — never replace the RUN list with OCR-only rows
  mergeOcrPrintParamsIntoDrives(res.result);
  // Prefer VFD filter so user sees print params on VFDs; keep full list (don't force print-only)
  if ($('device-type-filter')) {
    const hasVfd = (ioState.devices || []).some((d) => d.typeKey === 'vfd' || d.is_vfd);
    if (hasVfd) {
      $('device-type-filter').value = 'vfd';
      ioState.deviceTypeFilter = 'vfd';
    }
  }
  if ($('drive-print-only')) $('drive-print-only').checked = false;
  renderDriveTableRows();
  if (ioState.selectedDriveName) {
    const d = (ioState.devices || []).find((x) => x.name === ioState.selectedDriveName)
      || (ioState.drives || []).find((x) => x.name === ioState.selectedDriveName);
    showDriveDetail(d || null);
  }
  updateRecontrolReady();
  const m = res.result?.crosswalk?.matched_count || 0;
  const cov = res.result?.crosswalk?.coverage_pct || 0;
  const vfdn = res.result?.print_vfd_param_count || 0;
  const rm = res.result?.remote_merge || {};
  ioLog(
    `Done — vs tar.gz: ${m} matches (${cov}%). ` +
    `Remote→master: ${rm.remote_io_count || 0} I/O, ${rm.remote_rack_count || 0} racks, ` +
    `${rm.remote_conveyor_count || 0} conveyors, ${vfdn} VFD params.`,
    'ok',
  );
  // Prefer remote_merge tab after run so user sees what was pulled for master
  ioState.crosswalkTab = 'remote_merge';
  if (res.result?.crosswalk) renderCrosswalkList(res.result.crosswalk);
});

renderPanelSets();

// --- PLC Autogen (native Python fortna_autogen.py — not Excel VBA) ---
const autogenState = {
  excel: '',
  library: '',
  lastOut: '',
  lastL5x: '',
  busy: false,
  workbook: null, // Inputdata replacement — auto from RUN, editable
  wbTab: 'io',
  selected: new Set(),
  // Sorter build UI
  sorter: {
    sorter_type: '', // shoe_sorter | popup_divert
    induct_conveyor: '',
    induct_pe: '',
    tracking_count: 0,
    tracking: [], // [{ conveyor, pe }]
    divert_count: 0,
    tracking_pe_count: 0,
    tracking_pes: [], // [pe name, ...]
  },
  // Sawtooth / collector merge (PLC4 Sawtooth_Merge pattern)
  sawtooth: {
    collector_conveyor: '',
    downstream_conveyor: '',
    collector_has_encoder: 'yes',
    collector_encoder_type: 'Enc_RIOCard',
    collector_encoder: '',
    clctr_speed_fpm: 140,
    clctr_runout_dist: 0,
    clctr_slug_gap_adder: 0,
    clctr_safety_tmr_preset: 0,
    clctr_min_gap: 0,
    slot_reserve_multiple: 1,
    real_enc_ipp: 0,
    pseudo_enc_ipp: 0,
    pseudo_enc_max_cnt: 0,
    track_array_size: 0,
    lane_empty_opt_preset: 0,
    use_gapstore: false,
    lane_count: 4,
    // lanes: [{ conveyor, pe, jam_pe, merge_pe, has_encoder, encoder_type, encoder_tag }]
    lanes: [],
    collector_jam_pe: '',
    collector_jam_pe_b: '',
    collector_jam_pe_c: '',
    collector_jam_pe_d: '',
    eow_pe: '',
    mrg_id: '414',
    area_name: '',
    track_pe_count: 0,
    // track_pes: [{ pe, pls_location, blocked_jam_pre }]
    track_pes: [],
    enable_track: true,
    enable_reserve: true,
    no_carton_check: false,
  },
  // Site Twin gaps / SpaceXAI patches
  twinGaps: [],
  twinPatches: [],
  twinSelectedGapId: null,
  // PLC2-class 2:1 merges → Conv_Merge / Merge_2to1
  merges_2to1: [],
  // Compile hub readiness (Apply-per-tab)
  readiness: {
    hardware: { status: 'NOT_DETECTED', appliedAt: null, unresolved: 0, detail: '', dirty: false },
    transport: { status: 'NOT_DETECTED', appliedAt: null, unresolved: 0, detail: '', dirty: false },
    sawtooth: { status: 'NOT_DETECTED', appliedAt: null, unresolved: 0, detail: '', dirty: false },
    sorter: { status: 'NOT_DETECTED', appliedAt: null, unresolved: 0, detail: '', dirty: false },
    system: { status: 'NOT_DETECTED', appliedAt: null, unresolved: 0, detail: '', dirty: false },
  },
  lastGenerateIoMapError: null,
};

// Single shared Autogen state: Safety Build (safety-build.js) must mutate THIS
// object. Previously window.autogenState was a separate hollow object, so
// Sorter Apply read Transport's empty safety_build and wiped engineer members.
window.autogenState = autogenState;

/**
 * Prefer Applied Safety with members; never let a hollow Transport shell beat disk.
 * Used by Sorter Apply and Autogen Export merge.
 */
function unionSafetyBuild(a, b) {
  if (!a && !b) return null;
  if (!a) return b;
  if (!b) return a;
  const sidOf = (z) => String(
    (z && (z.source_id || z.sourceId || z.id || z.name)) || '',
  ).trim();
  const by = new Map();
  [...(a.zones || []), ...(b.zones || [])].forEach((z) => {
    const sid = sidOf(z);
    if (!sid) return;
    const prev = by.get(sid);
    if (!prev) {
      by.set(sid, { ...z });
      return;
    }
    const next = { ...prev, ...z };
    const prevN = (prev.members || []).length;
    const zN = (z.members || []).length;
    if (prevN && !zN) {
      next.members = prev.members;
      next.membersOrigin = prev.membersOrigin || next.membersOrigin;
    } else if (zN && !prevN) {
      next.members = z.members;
      next.membersOrigin = z.membersOrigin || next.membersOrigin;
    } else if (zN >= prevN) {
      next.members = z.members;
      next.membersOrigin = z.membersOrigin || prev.membersOrigin || next.membersOrigin;
    } else {
      next.members = prev.members;
      next.membersOrigin = prev.membersOrigin || next.membersOrigin;
    }
    next.runDiscovered = !!(prev.runDiscovered || z.runDiscovered);
    if (prev.provenance === 'RUN_DISCOVERED' || z.provenance === 'RUN_DISCOVERED') {
      next.provenance = next.provenance || 'RUN_DISCOVERED';
      next.runDiscovered = true;
    }
    if (prev.provenance === 'ENGINEER_CREATED' || z.provenance === 'ENGINEER_CREATED'
      || prev.engineerEdited || z.engineerEdited) {
      next.engineerEdited = !!(prev.engineerEdited || z.engineerEdited);
      if (!next.runDiscovered) next.provenance = next.provenance || 'ENGINEER_CREATED';
    }
    // Prefer stable source_id
    next.source_id = prev.source_id || z.source_id || sid;
    next.id = next.source_id;
    by.set(sid, next);
  });
  const score = (sb) => {
    if (!sb) return -1;
    const mem = (sb.zones || []).reduce((n, z) => n + ((z.members || []).length), 0);
    return (sb.appliedAt ? 1000 : 0) + mem * 10 + ((sb.zones || []).length);
  };
  const base = score(b) >= score(a) ? b : a;
  return { ...base, zones: [...by.values()] };
}

function preferSafetyBuild(memSb, diskSb) {
  const memScore = (() => {
    if (!memSb) return -1;
    const mem = (memSb.zones || []).reduce((n, z) => n + ((z.members || []).length), 0);
    return (memSb.appliedAt ? 1000 : 0) + mem * 10;
  })();
  const diskScore = (() => {
    if (!diskSb) return -1;
    const mem = (diskSb.zones || []).reduce((n, z) => n + ((z.members || []).length), 0);
    return (diskSb.appliedAt ? 1000 : 0) + mem * 10;
  })();
  if (memScore < 0 && diskScore < 0) return null;
  if (memScore < 0) return diskSb;
  if (diskScore < 0) return memSb;
  // Always union when both present — preserves engineer members across subsystem Apply
  return unionSafetyBuild(memSb, diskSb) || (diskScore >= memScore ? diskSb : memSb);
}

/** Empty tracking-conveyor row (encoder No = Slow_Flt uses NO_Enc UDT stub). */
function emptySorterTrackRow() {
  return {
    conveyor: '',
    pe: '',
    has_encoder: 'no', // 'yes' | 'no'
    encoder_type: 'Enc_RIOCard', // Enc_RIOCard | Enc_CounterCard | Enc_Virtual_DistBased
    encoder_tag: '', // optional ENC### / P###_Enc; blank = auto P###_Enc
  };
}

function defaultSorterConfig() {
  return {
    sorter_type: '', // shoe_sorter | popup_divert
    sorter_name: '',
    area_name: '',
    induct_conveyor: '',
    induct_pe: '',
    induct_has_encoder: 'no',
    induct_encoder_type: 'Enc_RIOCard',
    induct_encoder_tag: '',
    tracking_count: 0,
    tracking: [],
    divert_count: 0,
    divert_rows: [],
    tracking_pe_count: 0,
    tracking_pes: [],
    tracking_offset: '',
    global_track_offset: '',
    tracking_offset_authority: '',
    known_sorters: [],
    field_authority: {},
    review_resolutions: {},
    discovery_source: '',
    generation_state: '',
    plc_generation: 'PHASE1_SUPPORTED',
    configuration_required: [],
  };
}

function sorterAuthorityBadge(auth) {
  const a = String(auth || '').toUpperCase();
  if (a === 'PROVEN' || a === 'RUN_EXPLICIT') {
    return '<span class="px-1 rounded text-[9px] mono bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">PROVEN</span>';
  }
  if (a === 'DERIVED' || a === 'RUN_DERIVED') {
    return '<span class="px-1 rounded text-[9px] mono bg-sky-950/80 text-sky-300 border border-sky-800/60">DERIVED</span>';
  }
  if (a === 'OPTIONAL') {
    return '<span class="px-1 rounded text-[9px] mono bg-slate-900 text-slate-400 border border-slate-700">OPTIONAL</span>';
  }
  if (a === 'COMMISSIONING') {
    return '<span class="px-1 rounded text-[9px] mono bg-rose-950/80 text-rose-300 border border-rose-800/60">COMMISSIONING</span>';
  }
  if (a === 'ENGINEER_REQUIRED' || a.includes('ENGINEER')) {
    return '<span class="px-1 rounded text-[9px] mono bg-fuchsia-950/80 text-fuchsia-300 border border-fuchsia-800/60">ENGINEER</span>';
  }
  if (a.includes('REVIEW')) {
    return '<span class="px-1 rounded text-[9px] mono bg-amber-950/80 text-amber-300 border border-amber-800/60">REVIEW</span>';
  }
  return '<span class="px-1 rounded text-[9px] mono bg-slate-900 text-slate-500 border border-slate-700">UNKNOWN</span>';
}

/** Gate G/I status vocabulary — never treat OPTIONAL as REVIEW_REQUIRED. */
const SORTER_STATUS_CATS = Object.freeze({
  PROVEN: 'PROVEN',
  DERIVED: 'DERIVED',
  REVIEW_REQUIRED: 'REVIEW_REQUIRED',
  ENGINEER_REQUIRED: 'ENGINEER_REQUIRED',
  COMMISSIONING: 'COMMISSIONING',
  OPTIONAL: 'OPTIONAL',
});

/** Gate I resolution types — every active item must declare one. */
const SORTER_RESOLUTION_TYPES = Object.freeze({
  EDIT_REQUIRED: 'EDIT_REQUIRED',
  ACCEPT_DERIVED: 'ACCEPT_DERIVED',
  ACCEPT_PROVEN: 'ACCEPT_PROVEN',
  COMMISSIONING_CONFIRM: 'COMMISSIONING_CONFIRM',
  OPTIONAL: 'OPTIONAL',
  UNRESOLVED: 'UNRESOLVED',
});

const SORTER_REVIEW_ACTIONABLE = new Set([
  'REVIEW_REQUIRED',
  'ENGINEER_REQUIRED',
  'COMMISSIONING',
  'REVIEW',
  'UNKNOWN', // blank required field still needs engineer action
]);

/** Map unresolved field keys → editable control ids (focus on click). Gate L. */
const SORTER_FIELD_FOCUS = Object.freeze({
  induct_conveyor: 'sorter-induct-conv',
  induct_pe: 'sorter-induct-pe',
  induct_encoder: 'sorter-induct-enc-tag',
  sorter_type: 'sorter-type',
  transport_area: 'sorter-area-name',
  area_name: 'sorter-area-name',
  tracking_conveyors: 'sorter-track-count',
  tracking_conveyor_chain: 'sorter-track-rows',
  tracking_pe: 'sorter-pe-count',
  divert_output_io: 'sorter-divert-rows',
  divert_lane_topology: 'sorter-divert-rows',
  divert_pe: 'sorter-divert-rows',
  tracking_offset: 'sorter-tracking-offset',
  global_track_offset: 'sorter-tracking-offset',
  track_offset: 'sorter-tracking-offset',
});

function _normalizeSorterStatus(raw) {
  const a = String(raw || '').toUpperCase().trim();
  if (!a) return '';
  if (a === 'PROVEN' || a === 'RUN_EXPLICIT') return SORTER_STATUS_CATS.PROVEN;
  if (a === 'DERIVED' || a === 'RUN_DERIVED') return SORTER_STATUS_CATS.DERIVED;
  if (a === 'OPTIONAL' || a === 'N/A' || a === 'NOT_APPLICABLE') return SORTER_STATUS_CATS.OPTIONAL;
  if (a === 'COMMISSIONING' || a.includes('COMMISSION')) return SORTER_STATUS_CATS.COMMISSIONING;
  if (a === 'ENGINEER_REQUIRED' || a === 'ENGINEER' || a.includes('ENGINEER_REQUIRED')) {
    return SORTER_STATUS_CATS.ENGINEER_REQUIRED;
  }
  if (a.includes('REVIEW') || a === 'UNKNOWN' || a === 'UNRESOLVED') {
    return SORTER_STATUS_CATS.REVIEW_REQUIRED;
  }
  return a;
}

function _sorterReviewGroup(fieldKey) {
  const k = String(fieldKey || '').toLowerCase();
  if (k.includes('divert') || k.includes('lane') || k.includes('zone_lane')) return 'divert';
  if (k.includes('track') || k.includes('encoder') || k.includes('induct_pe')
    || k === 'tracking_pe' || k.includes('offset')) {
    return 'tracking';
  }
  return 'sorter';
}

function _sorterEvidenceFingerprint(field, value, source, status) {
  return [field || '', _sorterFieldValue(value), source || '', _normalizeSorterStatus(status) || status || '']
    .map((x) => String(x || '').trim())
    .join('|');
}

function _sorterResolveType(status, value, why) {
  const st = _normalizeSorterStatus(status);
  if (st === SORTER_STATUS_CATS.OPTIONAL) return SORTER_RESOLUTION_TYPES.OPTIONAL;
  if (st === SORTER_STATUS_CATS.DERIVED) return SORTER_RESOLUTION_TYPES.ACCEPT_DERIVED;
  if (st === SORTER_STATUS_CATS.PROVEN) return SORTER_RESOLUTION_TYPES.OPTIONAL;
  if (st === SORTER_STATUS_CATS.COMMISSIONING) return SORTER_RESOLUTION_TYPES.COMMISSIONING_CONFIRM;
  const whyL = String(why || '').toLowerCase();
  if (!_sorterFieldValue(value) && (whyL.includes('offset') || whyL.includes('commission'))) {
    return SORTER_RESOLUTION_TYPES.COMMISSIONING_CONFIRM;
  }
  if (st === SORTER_STATUS_CATS.ENGINEER_REQUIRED || st === SORTER_STATUS_CATS.REVIEW_REQUIRED
    || SORTER_REVIEW_ACTIONABLE.has(st)) {
    return _sorterFieldValue(value)
      ? SORTER_RESOLUTION_TYPES.EDIT_REQUIRED
      : SORTER_RESOLUTION_TYPES.EDIT_REQUIRED;
  }
  return SORTER_RESOLUTION_TYPES.UNRESOLVED;
}

/** Gate M — tracking_offset from canonical SorterModel; never invent. */
function _sorterTrackingOffsetReviewItem(cfg) {
  const fa = cfg.field_authority || {};
  const auth = _normalizeSorterStatus(fa.tracking_offset || fa.global_track_offset || cfg.tracking_offset_authority || '');
  const raw = (cfg.tracking_offset != null && cfg.tracking_offset !== '')
    ? cfg.tracking_offset
    : cfg.global_track_offset;
  const value = _sorterFieldValue(raw);
  let provenance = '';
  let source = 'SorterModel';
  let liveAuth = '';
  if (raw && typeof raw === 'object') {
    provenance = String(raw.provenance || raw.source || '');
    source = provenance || source;
    liveAuth = _normalizeSorterStatus(raw.authority || raw.provenance || '');
  }
  if (value && (liveAuth === SORTER_STATUS_CATS.PROVEN || auth === SORTER_STATUS_CATS.PROVEN)) {
    return null; // show in editor with provenance; not active review
  }
  if (value && (liveAuth === SORTER_STATUS_CATS.DERIVED || auth === SORTER_STATUS_CATS.DERIVED)) {
    return {
      field: 'tracking_offset',
      status: SORTER_STATUS_CATS.DERIVED,
      resolution_type: SORTER_RESOLUTION_TYPES.ACCEPT_DERIVED,
      group: 'tracking',
      focusId: SORTER_FIELD_FOCUS.tracking_offset,
      current_value: value,
      provenance: provenance || 'DERIVED',
      source,
      why: 'Derived track offset — Accept or Edit; do not invent.',
      detail: 'derived_offset',
      lifecycle: 'PENDING_REVIEW',
    };
  }
  if (auth === SORTER_STATUS_CATS.OPTIONAL) return null;
  const why = 'Global induct→divert offset not in RUN; Outpoint Location is per-outpoint only. '
    + 'Editable commissioning field — do not invent an offset.';
  let st = auth;
  if (!st || st === 'UNKNOWN') st = SORTER_STATUS_CATS.COMMISSIONING;
  if (st === SORTER_STATUS_CATS.REVIEW_REQUIRED) st = SORTER_STATUS_CATS.COMMISSIONING;
  const rtype = st === SORTER_STATUS_CATS.ENGINEER_REQUIRED
    ? SORTER_RESOLUTION_TYPES.EDIT_REQUIRED
    : SORTER_RESOLUTION_TYPES.COMMISSIONING_CONFIRM;
  return {
    field: 'tracking_offset',
    status: st,
    resolution_type: rtype,
    group: 'tracking',
    focusId: SORTER_FIELD_FOCUS.tracking_offset,
    current_value: value,
    provenance,
    source,
    why,
    detail: value ? 'field_authority' : 'missing_offset_evidence',
    lifecycle: 'PENDING_REVIEW',
  };
}

/** Gate N — divert PE objects needing review (skip PROVEN). */
function _sorterDivertPeObjects(cfg) {
  const out = [];
  (cfg.divert_rows || []).forEach((d, i) => {
    const auth = _normalizeSorterStatus(d?.authority?.divert_pe);
    const pe = _sorterFieldValue(d?.divert_pe);
    if (auth === SORTER_STATUS_CATS.PROVEN && pe) return;
    if (auth === SORTER_STATUS_CATS.OPTIONAL) return;
    if ((auth === SORTER_STATUS_CATS.DERIVED || auth === SORTER_STATUS_CATS.PROVEN) && pe) return;
    const needs = !pe
      || auth === SORTER_STATUS_CATS.REVIEW_REQUIRED
      || auth === SORTER_STATUS_CATS.ENGINEER_REQUIRED
      || auth === SORTER_STATUS_CATS.COMMISSIONING
      || auth === 'UNKNOWN'
      || !auth;
    if (!needs) return;
    out.push({
      index: i,
      name: _sorterFieldValue(d?.name),
      lane: _sorterFieldValue(d?.lane),
      host_zone: _sorterFieldValue(d?.host_zone),
      divert_pe: pe,
      authority: auth || SORTER_STATUS_CATS.REVIEW_REQUIRED,
      provenance: (d?.divert_pe && typeof d.divert_pe === 'object')
        ? String(d.divert_pe.provenance || '')
        : String(d?.authority?.divert_pe || ''),
    });
  });
  return out;
}

/**
 * Gates G/I/M/N — collect actionable unresolved fields with resolution types.
 * Never mix OPTIONAL into the review actionable list.
 * field_authority metadata alone must NOT force REVIEW if value is PROVEN/DERIVED.
 * Do NOT require approving 32 identical PROVEN divert mappings.
 */
function collectSorterReviewItems(s) {
  const cfg = s || {};
  const items = [];
  const seen = new Set();
  const pushItem = (item) => {
    const field = String(item.field || '').trim();
    if (!field) return;
    const group = item.group || _sorterReviewGroup(field);
    const key = `${group}::${field}`;
    if (seen.has(key)) return;
    const st = _normalizeSorterStatus(item.status);
    let rtype = item.resolution_type || '';
    // Never mix OPTIONAL into the review actionable list
    if (st === SORTER_STATUS_CATS.OPTIONAL || rtype === SORTER_RESOLUTION_TYPES.OPTIONAL) return;
    if (st === SORTER_STATUS_CATS.PROVEN && rtype !== SORTER_RESOLUTION_TYPES.ACCEPT_PROVEN) return;
    if (st === SORTER_STATUS_CATS.DERIVED && rtype !== SORTER_RESOLUTION_TYPES.ACCEPT_DERIVED) return;
    if (!rtype) rtype = _sorterResolveType(st, item.current_value, item.why);
    if (rtype === SORTER_RESOLUTION_TYPES.OPTIONAL) return;
    if (!rtype) rtype = SORTER_RESOLUTION_TYPES.UNRESOLVED;
    if (!SORTER_REVIEW_ACTIONABLE.has(st)
      && st !== SORTER_STATUS_CATS.REVIEW_REQUIRED
      && st !== SORTER_STATUS_CATS.ENGINEER_REQUIRED
      && st !== SORTER_STATUS_CATS.COMMISSIONING
      && rtype !== SORTER_RESOLUTION_TYPES.ACCEPT_DERIVED
      && rtype !== SORTER_RESOLUTION_TYPES.ACCEPT_PROVEN
      && rtype !== SORTER_RESOLUTION_TYPES.UNRESOLVED) {
      return;
    }
    // Gate I: every item needs actionable resolution or explicit unresolved reason
    if (rtype === SORTER_RESOLUTION_TYPES.UNRESOLVED && !item.why) {
      item.why = `Unresolved ${field}: need evidence or engineer action.`;
    }
    seen.add(key);
    items.push({
      ...item,
      field,
      status: st || SORTER_STATUS_CATS.REVIEW_REQUIRED,
      resolution_type: rtype,
      detail: item.detail || '',
      group,
      focusId: item.focusId || SORTER_FIELD_FOCUS[field] || '',
      lifecycle: item.lifecycle || 'PENDING_REVIEW',
      item_key: key,
      evidence_fingerprint: item.evidence_fingerprint || _sorterEvidenceFingerprint(
        field, item.current_value, item.source || item.detail || '', st,
      ),
    });
  };

  (cfg.configuration_required || []).forEach((raw) => {
    const field = String(raw || '').trim();
    if (!field) return;
    if (field === 'divert_output_io') {
      const rows = cfg.divert_rows || [];
      if (rows.length && rows.every((r) =>
        _normalizeSorterStatus(r?.authority?.divert_output_io) === SORTER_STATUS_CATS.PROVEN)) {
        return;
      }
    }
    let cur = '';
    if (field === 'transport_area' || field === 'area_name') cur = _sorterFieldValue(cfg.area_name);
    else if (field === 'sorter_type') cur = _sorterFieldValue(cfg.sorter_type);
    else if (field === 'induct_conveyor') cur = _sorterFieldValue(cfg.induct_conveyor);
    else if (field === 'induct_pe') cur = _sorterFieldValue(cfg.induct_pe);
    if (cur && ['sorter_type', 'transport_area', 'area_name', 'induct_pe'].includes(field)) return;
    pushItem({
      field,
      status: SORTER_STATUS_CATS.REVIEW_REQUIRED,
      resolution_type: SORTER_RESOLUTION_TYPES.EDIT_REQUIRED,
      detail: 'configuration_required',
      why: 'Required configuration blank — engineer must enter/select a value.',
      current_value: cur,
      source: 'configuration_required',
    });
  });

  const fa = cfg.field_authority || {};
  Object.entries(fa).forEach(([field, auth]) => {
    const st = _normalizeSorterStatus(auth);
    // field_authority metadata alone must NOT force REVIEW if PROVEN/DERIVED/OPTIONAL
    if (st === SORTER_STATUS_CATS.OPTIONAL || st === SORTER_STATUS_CATS.PROVEN
      || st === SORTER_STATUS_CATS.DERIVED) {
      return;
    }
    if (field === 'tracking_offset' || field === 'global_track_offset' || field === 'track_offset'
      || field === 'divert_pe' || field === 'plc_generation') {
      return;
    }
    if (st !== SORTER_STATUS_CATS.REVIEW_REQUIRED
      && st !== SORTER_STATUS_CATS.ENGINEER_REQUIRED
      && st !== SORTER_STATUS_CATS.COMMISSIONING
      && st !== 'UNKNOWN') {
      return;
    }
    let cur = '';
    if (field === 'transport_area' || field === 'area_name') {
      cur = _sorterFieldValue(cfg.area_name);
      if (cur) return;
    }
    if (field === 'sorter_type') {
      cur = _sorterFieldValue(cfg.sorter_type);
      if (cur) return;
    }
    if (field === 'induct_conveyor') {
      cur = _sorterFieldValue(cfg.induct_conveyor);
      const live = _normalizeSorterStatus(cfg.induct_authority?.conveyor);
      if (cur && (live === SORTER_STATUS_CATS.PROVEN || live === SORTER_STATUS_CATS.DERIVED)) return;
    }
    if (field === 'divert_output_io' || field === 'divert_lane_topology') {
      const rows = cfg.divert_rows || [];
      if (rows.length && rows.every((r) => {
        const a = _normalizeSorterStatus(r?.authority?.divert_output_io);
        const io = _sorterFieldValue(r?.divert_output_io);
        return a === SORTER_STATUS_CATS.PROVEN && io && io.toUpperCase() !== 'INVALID';
      })) return;
    }
    const norm = st === 'UNKNOWN' ? SORTER_STATUS_CATS.REVIEW_REQUIRED : st;
    pushItem({
      field,
      status: norm,
      resolution_type: _sorterResolveType(norm, cur, ''),
      detail: 'field_authority',
      why: `Field authority ${norm} — resolution required.`,
      current_value: cur,
      source: 'field_authority',
    });
  });

  const cov = cfg.coverage || {};
  const gapLists = [
    ...(Array.isArray(cov.gaps) ? cov.gaps : []),
    ...(Array.isArray(cov.coverage_gaps) ? cov.coverage_gaps : []),
    ...(Array.isArray(cov.unresolved) ? cov.unresolved : []),
    ...(Array.isArray(cov.ENGINEER_REQUIRED?.fields) ? cov.ENGINEER_REQUIRED.fields : []),
    ...(Array.isArray(cov.REVIEW_REQUIRED?.fields) ? cov.REVIEW_REQUIRED.fields : []),
  ];
  gapLists.forEach((g) => {
    if (typeof g === 'string') {
      const field = g.trim();
      if (!field) return;
      if (field === 'tracking_offset' || field === 'divert_pe'
        || /Tracking distance/i.test(field) || /Divert PE/i.test(field)) return;
      pushItem({
        field,
        status: SORTER_STATUS_CATS.REVIEW_REQUIRED,
        resolution_type: SORTER_RESOLUTION_TYPES.EDIT_REQUIRED,
        detail: 'coverage',
        why: 'Coverage gap — engineer action required.',
        source: 'coverage',
      });
      return;
    }
    if (g && typeof g === 'object') {
      const field = String(g.field || g.name || g.key || '').trim();
      if (!field) return;
      const st = _normalizeSorterStatus(g.authority || g.status || SORTER_STATUS_CATS.REVIEW_REQUIRED);
      if (st === SORTER_STATUS_CATS.OPTIONAL || st === SORTER_STATUS_CATS.PROVEN
        || st === SORTER_STATUS_CATS.DERIVED) return;
      pushItem({
        field,
        status: st || SORTER_STATUS_CATS.REVIEW_REQUIRED,
        resolution_type: _sorterResolveType(st, g.value, g.why || g.detail),
        detail: g.detail || 'coverage',
        why: g.why || g.detail || 'Coverage gap',
        current_value: _sorterFieldValue(g.value),
        source: 'coverage',
      });
    }
  });

  // Divert output IO — group unresolved only; never mass-approve identical PROVEN rows
  const unresolvedIo = [];
  (cfg.divert_rows || []).forEach((d, i) => {
    const auth = _normalizeSorterStatus(d?.authority?.divert_output_io);
    const io = _sorterFieldValue(d?.divert_output_io);
    if (auth === SORTER_STATUS_CATS.PROVEN && io && io.toUpperCase() !== 'INVALID') return;
    if (auth.includes?.('REVIEW') || auth === SORTER_STATUS_CATS.REVIEW_REQUIRED
      || auth === SORTER_STATUS_CATS.ENGINEER_REQUIRED
      || auth === SORTER_STATUS_CATS.COMMISSIONING
      || auth === 'UNKNOWN' || !auth || !io || io.toUpperCase() === 'INVALID') {
      unresolvedIo.push({
        index: i,
        name: _sorterFieldValue(d?.name),
        lane: _sorterFieldValue(d?.lane),
        divert_output_io: io,
        authority: auth || SORTER_STATUS_CATS.REVIEW_REQUIRED,
      });
    }
  });
  if (unresolvedIo.length) {
    pushItem({
      field: 'divert_output_io',
      status: SORTER_STATUS_CATS.REVIEW_REQUIRED,
      resolution_type: SORTER_RESOLUTION_TYPES.EDIT_REQUIRED,
      detail: `${unresolvedIo.length} divert IO row(s)`,
      why: 'Divert output IO unresolved on listed objects — not mass-approving PROVEN rows.',
      objects: unresolvedIo,
      source: 'divert_rows',
      group: 'divert',
      focusId: SORTER_FIELD_FOCUS.divert_output_io,
    });
  }

  const peObjs = _sorterDivertPeObjects(cfg);
  const faPe = _normalizeSorterStatus(fa.divert_pe);
  if (peObjs.length || faPe === SORTER_STATUS_CATS.REVIEW_REQUIRED
    || faPe === SORTER_STATUS_CATS.ENGINEER_REQUIRED
    || faPe === SORTER_STATUS_CATS.COMMISSIONING) {
    pushItem({
      field: 'divert_pe',
      status: (faPe === SORTER_STATUS_CATS.ENGINEER_REQUIRED || faPe === SORTER_STATUS_CATS.COMMISSIONING)
        ? faPe
        : SORTER_STATUS_CATS.REVIEW_REQUIRED,
      resolution_type: peObjs.length
        ? SORTER_RESOLUTION_TYPES.EDIT_REQUIRED
        : SORTER_RESOLUTION_TYPES.UNRESOLVED,
      detail: peObjs.length ? `${peObjs.length} divert PE object(s)` : 'divert_pe',
      why: peObjs.length
        ? 'Verify I/O INVALID / no distinct confirm PE — map PE on listed objects. '
          + 'Bulk Accept All Derived / Apply Value / Mark Commissioning; never UNKNOWN→PROVEN.'
        : 'divert_pe marked REVIEW but no row objects — need Verify I/O evidence.',
      objects: peObjs,
      source: 'divert_rows',
      group: 'divert',
      focusId: SORTER_FIELD_FOCUS.divert_pe,
      current_value: '',
    });
  }

  const off = _sorterTrackingOffsetReviewItem(cfg);
  if (off) pushItem(off);

  return items;
}

/** Optional fields (informational) — never merged into REVIEW_REQUIRED list. */
function collectSorterOptionalItems(s) {
  const cfg = s || {};
  const fa = cfg.field_authority || {};
  const out = [];
  Object.entries(fa).forEach(([field, auth]) => {
    if (_normalizeSorterStatus(auth) === SORTER_STATUS_CATS.OPTIONAL) {
      out.push({ field, status: SORTER_STATUS_CATS.OPTIONAL, group: _sorterReviewGroup(field) });
    }
  });
  return out;
}

/** Gate J — split active vs resolved; invalidate when evidence fingerprint changes. */
function filterSorterReviewActiveResolved(items, resolutions) {
  const res = resolutions || {};
  const active = [];
  const resolved = [];
  (items || []).forEach((it) => {
    const key = it.item_key || `${it.group}::${it.field}`;
    const rec = res[key] || res[it.field];
    if (!rec) {
      active.push(it);
      return;
    }
    const life = String(rec.lifecycle || rec.status || '').toUpperCase();
    if (!['RESOLVED', 'ACCEPTED', 'EDITED'].includes(life)) {
      active.push(it);
      return;
    }
    const fp = it.evidence_fingerprint || '';
    const priorFp = String(rec.evidence_fingerprint || '');
    if (priorFp && fp && priorFp !== fp) {
      active.push(it);
      return;
    }
    resolved.push({
      ...it,
      lifecycle: 'RESOLVED',
      resolution: rec.resolution || rec.lifecycle || 'ACCEPTED',
      final_value: rec.final_value != null ? rec.final_value : it.current_value,
      original_classification: rec.original_classification || it.status,
      resolved_at: rec.resolved_at,
      source: rec.source || it.source,
      acceptance_kind: rec.acceptance_kind || 'ENGINEER_ACCEPTED',
    });
  });
  return { active, resolved };
}

function sorterReviewStatusCounts(active, optional, resolved) {
  const counts = {
    review_required: 0,
    engineer_required: 0,
    commissioning: 0,
    optional: (optional || []).length,
    resolved: (resolved || []).length,
  };
  (active || []).forEach((it) => {
    const st = _normalizeSorterStatus(it.status);
    if (st === SORTER_STATUS_CATS.ENGINEER_REQUIRED) counts.engineer_required += 1;
    else if (st === SORTER_STATUS_CATS.COMMISSIONING) counts.commissioning += 1;
    else counts.review_required += 1;
  });
  return counts;
}

/** Gate J — PENDING_REVIEW → ACCEPTED/EDITED → RESOLVED (persisted on sorter_build). */
function acceptSorterReviewItem(item, { resolution = 'ACCEPTED', finalValue = null } = {}) {
  if (!autogenState.sorter) autogenState.sorter = defaultSorterConfig();
  if (!autogenState.sorter.review_resolutions) autogenState.sorter.review_resolutions = {};
  const key = item.item_key || `${item.group}::${item.field}`;
  const res = String(resolution || 'ACCEPTED').toUpperCase() === 'EDITED' ? 'EDITED' : 'ACCEPTED';
  const final_value = finalValue != null ? _sorterFieldValue(finalValue) : _sorterFieldValue(item.current_value);
  autogenState.sorter.review_resolutions[key] = {
    field: item.field,
    lifecycle: 'RESOLVED',
    resolution: res,
    resolution_type: item.resolution_type,
    final_value,
    source: item.source || item.provenance || '',
    original_classification: item.status,
    acceptance_kind: 'ENGINEER_ACCEPTED',
    evidence_fingerprint: item.evidence_fingerprint || _sorterEvidenceFingerprint(
      item.field, final_value, item.source || '', item.status,
    ),
    resolved_at: new Date().toISOString(),
  };
  try {
    localStorage.setItem('fortna_sorter_build', JSON.stringify(autogenState.sorter));
  } catch (_) { /* ignore */ }
  try { persistSorterToWorkbook(); } catch (_) { /* ignore */ }
}

function focusSorterReviewField(focusId, meta) {
  if (!focusId) return;
  const el = $(focusId);
  if (!el) return;
  try {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.focus?.();
    el.classList?.add('ring-2', 'ring-amber-500/70');
    setTimeout(() => el.classList?.remove('ring-2', 'ring-amber-500/70'), 1600);
  } catch (_) { /* ignore */ }
  const detail = $('sorter-review-focus-detail');
  if (detail && meta) {
    detail.classList.remove('hidden');
    detail.innerHTML = `
      <div class="text-[9px] uppercase tracking-wider text-cyan-600/90 font-semibold mb-1">Focused field</div>
      <div class="flex flex-wrap gap-2 items-center text-[10px]">
        <span class="mono text-cyan-200">${escapeHtml(meta.field || '')}</span>
        ${sorterAuthorityBadge(meta.status || '')}
        <span class="text-slate-500">value</span>
        <span class="mono text-slate-200">${escapeHtml(String(meta.current_value ?? '—'))}</span>
        <span class="text-slate-500">provenance</span>
        <span class="mono text-slate-400">${escapeHtml(meta.provenance || meta.source || '—')}</span>
      </div>
      <div class="text-[10px] text-amber-200/80 mt-1">${escapeHtml(meta.why || '')}</div>
      <div class="text-[10px] text-slate-500 mt-0.5">Resolution: <span class="mono text-slate-300">${escapeHtml(meta.resolution_type || '')}</span></div>`;
  }
}

function _sorterReviewActionButtons(it) {
  const r = it.resolution_type || '';
  const btns = [];
  if (r === SORTER_RESOLUTION_TYPES.ACCEPT_DERIVED) {
    btns.push(`<button type="button" class="sorter-review-accept px-1.5 py-0.5 rounded border border-sky-800/60 text-sky-300 text-[9px]" data-key="${escapeHtml(it.item_key)}">Accept derived</button>`);
    btns.push(`<button type="button" class="sorter-review-edit px-1.5 py-0.5 rounded border border-slate-700 text-slate-300 text-[9px]" data-key="${escapeHtml(it.item_key)}" data-focus="${escapeHtml(it.focusId || '')}">Edit</button>`);
  } else if (r === SORTER_RESOLUTION_TYPES.ACCEPT_PROVEN) {
    btns.push(`<button type="button" class="sorter-review-accept px-1.5 py-0.5 rounded border border-emerald-800/60 text-emerald-300 text-[9px]" data-key="${escapeHtml(it.item_key)}">Acknowledge</button>`);
  } else if (r === SORTER_RESOLUTION_TYPES.COMMISSIONING_CONFIRM) {
    btns.push(`<button type="button" class="sorter-review-edit px-1.5 py-0.5 rounded border border-rose-800/60 text-rose-300 text-[9px]" data-key="${escapeHtml(it.item_key)}" data-focus="${escapeHtml(it.focusId || '')}">Enter / commission</button>`);
    btns.push(`<button type="button" class="sorter-review-accept px-1.5 py-0.5 rounded border border-rose-800/40 text-rose-200/80 text-[9px]" data-key="${escapeHtml(it.item_key)}" data-mode="commission">Confirm commissioning</button>`);
  } else if (r === SORTER_RESOLUTION_TYPES.EDIT_REQUIRED) {
    btns.push(`<button type="button" class="sorter-review-edit px-1.5 py-0.5 rounded border border-fuchsia-800/60 text-fuchsia-300 text-[9px]" data-key="${escapeHtml(it.item_key)}" data-focus="${escapeHtml(it.focusId || '')}">Edit field</button>`);
    if (it.field === 'divert_pe' || it.field === 'tracking_offset') {
      btns.push(`<button type="button" class="sorter-review-accept px-1.5 py-0.5 rounded border border-amber-800/50 text-amber-200 text-[9px]" data-key="${escapeHtml(it.item_key)}">Mark reviewed</button>`);
    }
  } else if (r === SORTER_RESOLUTION_TYPES.UNRESOLVED) {
    btns.push(`<span class="text-[9px] text-slate-500">Needs evidence</span>`);
  }
  return btns.join(' ');
}

function renderSorterReviewPanel(s) {
  const host = $('sorter-review-required');
  const groupsEl = $('sorter-review-groups');
  const countEl = $('sorter-review-count');
  const countsEl = $('sorter-review-status-counts');
  const completeEl = $('sorter-review-complete');
  const reviewedEl = $('sorter-review-reviewed');
  if (!host || !groupsEl) return;

  const allItems = collectSorterReviewItems(s);
  const optional = collectSorterOptionalItems(s);
  const { active, resolved } = filterSorterReviewActiveResolved(allItems, s?.review_resolutions || {});
  const counts = sorterReviewStatusCounts(active, optional, resolved);

  if (countsEl) {
    countsEl.innerHTML = [
      `<span class="text-amber-300">Review Required <span class="mono">${counts.review_required}</span></span>`,
      `<span class="text-fuchsia-300">Engineer Required <span class="mono">${counts.engineer_required}</span></span>`,
      `<span class="text-rose-300">Commissioning <span class="mono">${counts.commissioning}</span></span>`,
      `<span class="text-slate-400">Optional <span class="mono">${counts.optional}</span></span>`,
      `<span class="text-emerald-400">Resolved <span class="mono">${counts.resolved}</span></span>`,
    ].join('<span class="text-slate-700 mx-1">·</span>');
  }
  if (countEl) {
    countEl.textContent = String(counts.review_required + counts.engineer_required + counts.commissioning);
  }

  const activeN = counts.review_required + counts.engineer_required + counts.commissioning;
  if (completeEl) {
    if (activeN === 0 && ((s && (s.detected || s.sorter_name || (s.known_sorters || []).length)) || resolved.length)) {
      completeEl.classList.remove('hidden');
    } else {
      completeEl.classList.add('hidden');
    }
  }

  if (activeN === 0 && !optional.length) {
    host.classList.add('hidden');
    groupsEl.innerHTML = '';
  } else if (activeN === 0 && optional.length) {
    host.classList.add('hidden');
    groupsEl.innerHTML = '';
  } else {
    host.classList.remove('hidden');
    const byGroup = { sorter: [], tracking: [], divert: [] };
    active.forEach((it) => {
      const g = byGroup[it.group] ? it.group : 'sorter';
      byGroup[g].push(it);
    });
    const label = { sorter: 'Sorter', tracking: 'Tracking', divert: 'Divert' };
    let html = '';
    ['sorter', 'tracking', 'divert'].forEach((g) => {
      const rows = byGroup[g];
      if (!rows.length) return;
      html += `<div class="rounded-lg border border-amber-900/30 bg-[#0a1016] p-2">
        <div class="text-[9px] uppercase tracking-wider text-amber-500/90 font-semibold mb-1">${label[g]}</div>
        <div class="space-y-1.5">`;
      rows.forEach((it) => {
        const objN = Array.isArray(it.objects) ? it.objects.length : 0;
        html += `<div class="sorter-review-item rounded border border-transparent hover:border-amber-800/40 hover:bg-amber-950/30 px-1.5 py-1"
          data-focus="${escapeHtml(it.focusId || '')}" data-field="${escapeHtml(it.field)}" data-key="${escapeHtml(it.item_key || '')}">
          <button type="button" class="sorter-review-focus w-full text-left flex flex-wrap items-center gap-2">
            <span class="mono text-amber-100/90">${escapeHtml(it.field)}</span>
            ${sorterAuthorityBadge(it.status)}
            <span class="text-[9px] mono text-slate-500">${escapeHtml(it.resolution_type || '')}</span>
            <span class="text-slate-600 truncate">${escapeHtml(it.detail || '')}</span>
          </button>
          <div class="text-[10px] text-slate-500 mt-0.5">
            value <span class="mono text-slate-300">${escapeHtml(String(it.current_value ?? '—'))}</span>
            · ${escapeHtml(it.why || '')}
          </div>
          ${objN ? `<div class="text-[9px] text-slate-600 mt-0.5 max-h-16 overflow-y-auto mono">${
            it.objects.slice(0, 12).map((o) => escapeHtml(`${o.name || o.lane || '#' + o.index}${o.divert_pe ? '=' + o.divert_pe : ''}`)).join(', ')
            }${objN > 12 ? ` …+${objN - 12}` : ''}</div>` : ''}
          <div class="flex flex-wrap gap-1 mt-1">${_sorterReviewActionButtons(it)}</div>
        </div>`;
      });
      html += '</div></div>';
    });
    if (optional.length) {
      html += `<div class="rounded-lg border border-slate-800 bg-[#0a1016] p-2">
        <div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Optional (not review)</div>
        <div class="flex flex-wrap gap-1">${optional.map((o) =>
          `<span class="inline-flex items-center gap-1 mono text-slate-500">${escapeHtml(o.field)} ${sorterAuthorityBadge('OPTIONAL')}</span>`
        ).join('')}</div>
      </div>`;
    }
    groupsEl.innerHTML = html || '<div class="text-slate-600">No actionable review items.</div>';
  }

  // Gate J — collapsed REVIEWED ✓ section
  if (reviewedEl) {
    if (!resolved.length) {
      reviewedEl.classList.add('hidden');
      reviewedEl.innerHTML = '';
    } else {
      reviewedEl.classList.remove('hidden');
      reviewedEl.innerHTML = `<details class="rounded-lg border border-emerald-900/40 bg-emerald-950/10 p-2">
        <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-emerald-400/90 font-semibold select-none">
          Reviewed ✓ <span class="mono text-emerald-200/80">${resolved.length}</span>
        </summary>
        <div class="mt-1 space-y-1">${resolved.map((r) => `
          <div class="flex flex-wrap gap-2 items-center text-[10px] mono px-1">
            <span class="text-emerald-200/90">${escapeHtml(r.field)}</span>
            <span class="text-slate-400">${escapeHtml(String(r.final_value ?? '—'))}</span>
            <span class="text-slate-600">${escapeHtml(r.source || '')}</span>
            ${sorterAuthorityBadge(r.original_classification || '')}
            <span class="text-slate-500">${escapeHtml(r.resolution || 'ACCEPTED')}</span>
            <span class="text-slate-600 ml-auto">${escapeHtml(r.resolved_at ? String(r.resolved_at).slice(0, 19) : '')}</span>
          </div>`).join('')}
        </div>
      </details>`;
    }
  }

  const byKey = Object.fromEntries(active.map((it) => [it.item_key, it]));
  groupsEl.querySelectorAll('.sorter-review-focus').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      const row = ev.currentTarget.closest('.sorter-review-item');
      const key = row?.getAttribute('data-key') || '';
      const it = byKey[key];
      focusSorterReviewField(row?.getAttribute('data-focus') || '', it || {
        field: row?.getAttribute('data-field'),
      });
    });
  });
  groupsEl.querySelectorAll('.sorter-review-accept').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const key = btn.getAttribute('data-key') || '';
      const it = byKey[key];
      if (!it) return;
      let finalValue = it.current_value;
      if (it.field === 'tracking_offset') {
        finalValue = $('sorter-tracking-offset')?.value || finalValue || '';
        if (btn.getAttribute('data-mode') === 'commission' || it.resolution_type === SORTER_RESOLUTION_TYPES.COMMISSIONING_CONFIRM) {
          if ($('sorter-tracking-offset')) {
            autogenState.sorter.tracking_offset = $('sorter-tracking-offset').value || finalValue || '';
            autogenState.sorter.global_track_offset = autogenState.sorter.tracking_offset;
            autogenState.sorter.tracking_offset_authority = 'COMMISSIONING';
          }
          finalValue = autogenState.sorter.tracking_offset || finalValue;
        }
      }
      acceptSorterReviewItem(it, { resolution: 'ACCEPTED', finalValue });
      renderSorterBuild();
    });
  });
  groupsEl.querySelectorAll('.sorter-review-edit').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const key = btn.getAttribute('data-key') || '';
      const it = byKey[key];
      focusSorterReviewField(btn.getAttribute('data-focus') || it?.focusId || '', it);
    });
  });
}

function _sorterFieldValue(v) {
  if (v == null) return '';
  if (typeof v === 'object' && !Array.isArray(v)) return v.value != null ? String(v.value) : '';
  return String(v);
}

/** Engineer-built Transportation areas only — never invent from CP / controller name. */
function transportAreaNameList() {
  const names = [];
  const seen = new Set();
  const add = (n) => {
    const s = String(n || '').trim();
    if (!s || seen.has(s)) return;
    seen.add(s);
    names.push(s);
  };
  try {
    const live = window.__tbApi?.tb?.areas;
    if (Array.isArray(live)) live.forEach((a) => add(a && a.name));
  } catch (_) { /* ignore */ }
  try {
    const raw = localStorage.getItem('siteforge.transportBuild.v2')
      || localStorage.getItem('siteforge.transportBuild.v1');
    if (raw) {
      const data = JSON.parse(raw);
      (data.areas || []).forEach((a) => add(a && a.name));
    }
  } catch (_) { /* ignore */ }
  const wb = autogenState.workbook;
  (wb?.areas || []).forEach((a) => add(typeof a === 'string' ? a : (a && a.name)));
  (wb?.options?.areas || []).forEach((a) => add(a));
  (wb?.conveyors || []).forEach((r) => add(r && r.main_area));
  return names;
}

function _sawtoothUnresolvedKey(x) {
  return String(x || '').trim().toLowerCase().replace(/\s+/g, '_');
}

/** True when collector-track encoder requirement is already satisfied (e.g. proven ENC414). */
function sawtoothCollectorEncoderSatisfied(s) {
  const cfg = s || {};
  if (cfg.collector_has_encoder === 'no' || cfg.collector_has_encoder === false) return true;
  return !!(String(cfg.collector_encoder || '').trim());
}

/**
 * Keep configuration_required consistent with filled fields.
 * Proven/filled collector_encoder (ENC414) clears merge_encoder / collector_encoder —
 * do not leave a contradictory unresolved warning beside the proven-role label.
 * Only strips satisfied/optional keys; does not invent new gates on empty configs.
 */
function reconcileSawtoothConfigurationRequired(s) {
  const cfg = s || {};
  let unresolved = Array.isArray(cfg.configuration_required)
    ? [...cfg.configuration_required]
    : [];
  const optional = new Set([
    'discharge_conveyor', 'downstream_conveyor', 'downstream', 'jam_pe',
  ]);
  unresolved = unresolved.filter((x) => !optional.has(_sawtoothUnresolvedKey(x)));
  if (cfg.collector_conveyor) {
    unresolved = unresolved.filter((x) => _sawtoothUnresolvedKey(x) !== 'collector_conveyor');
  }
  if (sawtoothCollectorEncoderSatisfied(cfg)) {
    unresolved = unresolved.filter((x) => {
      const k = _sawtoothUnresolvedKey(x);
      return k !== 'merge_encoder' && k !== 'collector_encoder';
    });
  }
  cfg.configuration_required = unresolved;
  return cfg;
}

function defaultSawtoothConfig() {
  return {
    collector_conveyor: '',
    downstream_conveyor: '',
    collector_has_encoder: 'yes',
    collector_encoder_type: 'Enc_RIOCard',
    collector_encoder: '',
    encoder_role: '', // collector_tracking | city_counter | … from RUN evidence
    clctr_speed_fpm: 140,
    clctr_runout_dist: 0,
    clctr_slug_gap_adder: 0,
    clctr_safety_tmr_preset: 0,
    clctr_min_gap: 0,
    slot_reserve_multiple: 1,
    real_enc_ipp: 0,
    pseudo_enc_ipp: 0,
    pseudo_enc_max_cnt: 0,
    track_array_size: 0,
    lane_empty_opt_preset: 0,
    use_gapstore: false,
    lane_count: 4,
    lanes: [],
    collector_jam_pe: '',
    collector_jam_pe_b: '',
    collector_jam_pe_c: '',
    collector_jam_pe_d: '',
    eow_pe: '',
    mrg_id: '414',
    area_name: '',
    track_pe_count: 0,
    track_pes: [],
    enable_track: true,
    enable_reserve: true,
    no_carton_check: false,
  };
}

/** Derive P### collector from VFD###_AUX / VFD### motor_io. */
function collectorFromMotorIo(motorIo) {
  const m = String(motorIo || '').match(/^VFD(\d+[A-Z]?)/i);
  return m ? `P${m[1]}` : '';
}

/** Map SiteModel editors.sawtooth → dashboard sawtooth_build shape. */
function sawtoothBuildFromSiteModel(site) {
  const ed = (site && site.editors && site.editors.sawtooth) || {};
  const merges = ed.merges || site?.sawtooth_merges || [];
  if (!merges.length) return null;
  const merge = merges[0] || {};
  const lanesSrc = merge.lanes || [];
  const motor = merge.motor || merge.motor_io || '';
  let collector = merge.collector_conveyor || merge.collector || '';
  if (!collector) collector = collectorFromMotorIo(motor);
  // Prefer proven merge_encoder / collector_encoder from SawtoothMergeModel.
  // Never pick the first ENC### in site.encoders — city-counter encoders (ENC424)
  // must not displace collector tracking (ENC414) without association evidence.
  let encoder = merge.collector_encoder || merge.merge_encoder || merge.encoder || '';
  let encoderRole = merge.encoder_role || merge.merge_encoder_role || '';
  if (!encoder && Array.isArray(site?.encoders)) {
    const mergeName = String(merge.merge_identity || merge.normalized_name || merge.raw_name || '').toUpperCase();
    const collectorNum = collector ? String(collector).replace(/^P/i, '') : '';
    let assocHit = '';
    let digitHit = '';
    for (const enc of site.encoders) {
      const name = enc.raw_name || enc.normalized_name || '';
      const jam = String(enc.jamzone || enc.Jamzone || '').toUpperCase();
      const assocs = enc.associations || [];
      const hit = assocs.some((a) => {
        const to = String(a.to || a.rule || '').toUpperCase().replace(/\s+/g, '_');
        return to && mergeName && (to.includes(mergeName) || to.replace(/_/g, ' ') === mergeName.replace(/_/g, ' '));
      });
      if (hit || jam.includes('SAWTOOTH')) {
        assocHit = name;
        encoderRole = 'collector_tracking';
        break;
      }
      if (!digitHit && collectorNum && String(name).toUpperCase() === `ENC${collectorNum}`) {
        digitHit = name;
        encoderRole = 'collector_tracking';
      }
    }
    encoder = assocHit || digitHit || '';
  }
  if (!encoderRole && encoder) encoderRole = 'collector_tracking';
  const lanes = lanesSrc.map((ln) => normalizeSawLaneRow({
    conveyor: ln.lane_conveyor || ln.conveyor || '',
    pe: ln.lane_pe || ln.photoeye || '',
    jam_pe: ln.jam_pe || '',
    merge_pe: ln.merge_pe || '',
    has_encoder: ln.encoder ? 'yes' : 'no',
    encoder_type: 'Enc_RIOCard',
    encoder_tag: ln.encoder || '',
    drive: ln.drive || ln.vfd || '',
    motor: ln.motor || motor || '',
    lane_index: ln.lane_index,
    approach: ln.approach || '',
    collision: ln.collision || '',
    lane_input: ln.lane_input || '',
    slice_seconds: ln.slice_seconds != null ? ln.slice_seconds : (ln.slice_time != null ? ln.slice_time : null),
    reserve_seconds: ln.reserve_seconds != null ? ln.reserve_seconds : (ln.reserve_time != null ? ln.reserve_time : null),
    allowed_to_run: ln.allowed_to_run || '',
    configuration_required: ln.configuration_required || [],
    field_provenance: ln.field_provenance || {},
  }));
  const mrgNum = (collector.match(/(\d+)/) || [])[1] || '';
  // Blocking readiness: collector + merge encoder only. Discharge / lane jam PE stay
  // visible when empty but must not block Apply when RUN left them optional/unresolved.
  // When encoder is proven/filled (ENC414 collector_tracking), strip merge_encoder /
  // collector_encoder from unresolved — requirement is satisfied, not contradictory.
  let unresolved = [...(merge.configuration_required || merge.config_required || [])]
    .filter((x) => !['discharge_conveyor', 'downstream_conveyor', 'downstream conveyor', 'jam_pe'].includes(String(x)));
  if (collector) {
    unresolved = unresolved.filter((x) => _sawtoothUnresolvedKey(x) !== 'collector_conveyor');
  } else if (!unresolved.some((x) => _sawtoothUnresolvedKey(x) === 'collector_conveyor')) {
    unresolved.push('collector_conveyor');
  }
  if (encoder) {
    unresolved = unresolved.filter((x) => {
      const k = _sawtoothUnresolvedKey(x);
      return k !== 'merge_encoder' && k !== 'collector_encoder';
    });
  } else if (!unresolved.some((x) => {
    const k = _sawtoothUnresolvedKey(x);
    return k === 'collector_encoder' || k === 'merge_encoder';
  })) {
    unresolved.push('merge_encoder');
  }
  return normalizeSawtoothConfig({
    ...defaultSawtoothConfig(),
    collector_conveyor: collector,
    downstream_conveyor: merge.downstream_conveyor || merge.downstream || '',
    collector_has_encoder: encoder ? 'yes' : 'no',
    collector_encoder_type: 'Enc_RIOCard',
    collector_encoder: encoder,
    encoder_role: encoderRole || (encoder ? 'collector_tracking' : ''),
    // Do not invent site timing defaults — leave 0 / empty when RUN does not prove them.
    clctr_speed_fpm: Number(merge.clctr_speed_fpm) || 0,
    lane_count: lanes.length || Number(merge.lane_count) || 0,
    lanes,
    mrg_id: String(mrgNum || ''),
    area_name: merge.area_name || '',
    reservation: merge.reservation || '',
    slice_seconds_merge: merge.slice_seconds != null ? merge.slice_seconds : null,
    lane_enable_delay_tm: merge.lane_enable_delay_tm || '',
    enable_track: true,
    enable_reserve: true,
    discovery_source: 'site_model',
    configuration_required: unresolved,
    merge_identity: merge.merge_identity || merge.normalized_name || merge.raw_name || '',
  });
}

/** Map SiteModel editors.sorter → dashboard sorter_build (known fields only). */
function sorterBuildFromSiteModel(site) {
  const ed = (site && site.editors && site.editors.sorter) || {};
  const sm = (site && site.sorter_model) || {};
  const sorters = ed.sorters || site?.sorters || sm.sorters || [];
  if (!sorters.length && !(ed.detected) && !(sm.detected)) return null;
  // Prefer a non-sawtooth sorter (e.g. CITY_LANE / ship) when present; else first.
  const pick = sorters.find((s) => {
    const n = String(s.raw_name || s.normalized_name || s.sorter || _sorterFieldValue(s.name) || '').toUpperCase();
    return n && !n.includes('SAWTOOTH');
  }) || sorters[0] || {};
  const name = pick.raw_name || pick.normalized_name || pick.sorter || _sorterFieldValue(pick.name) || '';
  const enc = pick.encoder_io || (Array.isArray(pick.encoders) ? pick.encoders[0] : '')
    || _sorterFieldValue(pick.encoder_io) || '';
  const scanBosses = ed.scan_bosses || pick.scan_bosses || sm.scan_bosses || [];
  const zoneLanes = ed.zone_lanes || pick.lane_assignments || pick.zone_lanes || sm.zone_lanes || [];
  const divertRowsRaw = ed.divert_rows || sm.divert_rows || zoneLanes || [];
  const trackingPath = ed.tracking_path || sm.tracking_path || [];
  const fieldAuthority = ed.field_authority || sm.field_authority || pick.field_authority || {};

  // Deep evidence: encoder + optional Mtrchain conveyor + Inpoints PE per section.
  const tracking = [];
  for (const tp of trackingPath) {
    const encTag = _sorterFieldValue(tp.encoder_tag) || _sorterFieldValue(tp.encoder_io) || '';
    const conv = _sorterFieldValue(tp.conveyor) || '';
    const pe = _sorterFieldValue(tp.photoeye) || _sorterFieldValue(tp.induct_pe) || '';
    const auth = tp.authority || {};
    tracking.push(normalizeSorterTrackRow({
      conveyor: conv,
      pe,
      has_encoder: encTag ? 'yes' : 'no',
      encoder_type: 'Enc_RIOCard',
      encoder_tag: encTag,
      authority: auth,
      note: `sorter=${_sorterFieldValue(tp.sorter) || ''}`,
    }));
  }
  // Fallback: one row per known sorter encoder when tracking_path empty
  if (!tracking.length) {
    for (const s of sorters) {
      const sEnc = s.encoder_io || (Array.isArray(s.encoders) ? s.encoders[0] : '')
        || _sorterFieldValue(s.encoder_io) || '';
      if (!sEnc) continue;
      tracking.push(normalizeSorterTrackRow({
        conveyor: '',
        pe: '',
        has_encoder: 'yes',
        encoder_type: 'Enc_RIOCard',
        encoder_tag: sEnc,
        authority: { encoder_tag: 'PROVEN', conveyor: 'UNKNOWN' },
        note: `sorter=${s.raw_name || s.normalized_name || s.sorter || ''}`,
      }));
    }
  }

  const inductBlock = ed.induct || sm.induct || {};
  const inductAuth = inductBlock.authority || {};
  const inductConv = _sorterFieldValue(inductBlock.conveyor) || pick.induct_conveyor || '';
  const inductPe = _sorterFieldValue(inductBlock.photoeye) || pick.induct_pe || '';
  const inductEnc = _sorterFieldValue(inductBlock.encoder) || enc || '';
  const trackingPes = tracking.map((t) => t.pe).filter(Boolean);

  const divert_rows = (divertRowsRaw || []).map((d) => {
    const auth = d.authority || {};
    const peAuth = auth.divert_pe || 'REVIEW_REQUIRED';
    const peVal = _sorterFieldValue(d.divert_pe);
    // Preserve RUN candidate + provenance; do not invent PE from timer name hints.
    const peSource = (d.divert_pe && typeof d.divert_pe === 'object')
      ? String(d.divert_pe.source || '')
      : String(d.divert_pe_source || '');
    const peProv = (d.divert_pe && typeof d.divert_pe === 'object')
      ? String(d.divert_pe.provenance || '')
      : String(d.divert_pe_provenance || auth.divert_pe || '');
    return {
      name: _sorterFieldValue(d.name),
      lane: _sorterFieldValue(d.lane),
      host_zone: _sorterFieldValue(d.host_zone),
      app_sorter: _sorterFieldValue(d.app_sorter),
      enabled: _sorterFieldValue(d.enabled),
      divert_output_io: _sorterFieldValue(d.divert_output_io || d.lane_enable_signal),
      divert_pe: peVal,
      divert_pe_source: peSource,
      divert_pe_provenance: peProv,
      outpoint_location: _sorterFieldValue(d.outpoint_location),
      full_clear_timer: _sorterFieldValue(d.full_clear_timer),
      divert_pe_acceptance: d.divert_pe_acceptance || auth.divert_pe_acceptance || '',
      divert_pe_ui_mode: d.divert_pe_ui_mode || '', // '' | 'change' — Change reveals Select
      authority: {
        topology: auth.topology || 'PROVEN',
        divert_output_io: auth.divert_output_io || 'REVIEW_REQUIRED',
        divert_pe: peAuth,
        divert_pe_acceptance: d.divert_pe_acceptance || auth.divert_pe_acceptance || '',
      },
    };
  });

  // Gate X — preserve prior review resolutions across model rebuild when fingerprint still matches
  const priorRes = (autogenState.sorter && autogenState.sorter.review_resolutions)
    || (ed.review_resolutions)
    || {};
  const priorOffset = (autogenState.sorter && (autogenState.sorter.tracking_offset || autogenState.sorter.global_track_offset))
    || ed.tracking_offset || sm.tracking_offset || '';
  const priorOffsetAuth = (autogenState.sorter && autogenState.sorter.tracking_offset_authority)
    || ed.tracking_offset_authority || '';

  const known = sorters.map((s) => {
    const sName = s.raw_name || s.normalized_name || s.sorter || _sorterFieldValue(s.name) || '';
    const sEnc = s.encoder_io || (Array.isArray(s.encoders) ? s.encoders[0] : '')
      || _sorterFieldValue(s.encoder_io) || '';
    const sAuth = s.authority || {};
    return {
      name: sName,
      encoder: sEnc,
      generation_state: s.generation_state || ed.generation_state || 'GENERATABLE',
      authority: {
        name: sAuth.name || 'PROVEN',
        encoder_io: sAuth.encoder_io || (sEnc ? 'PROVEN' : 'UNKNOWN'),
      },
    };
  });

  const cfg = {
    ...defaultSorterConfig(),
    sorter_type: pick.sorter_type || ed.sorter_type || sm.sorter_type || '',
    sorter_name: name,
    area_name: sm.sorter_area_name || sm.transport_area || ed.area_name
      || pick.area_name || pick.main_area || '',
    sorter_area_name: sm.sorter_area_name || sm.transport_area || ed.sorter_area_name || '',
    shipping_sorter_supported: !!(
      sm.shipping_sorter_supported || ed.shipping_sorter_supported
    ),
    divert_host_conveyor: sm.divert_host_conveyor || ed.divert_host_conveyor || '',
    induct_conveyor: inductConv,
    induct_pe: inductPe,
    induct_has_encoder: inductEnc || enc ? 'yes' : 'no',
    induct_encoder_type: 'Enc_RIOCard',
    induct_encoder_tag: inductEnc || enc || '',
    induct_authority: {
      conveyor: inductAuth.conveyor || (inductConv ? 'DERIVED' : 'UNKNOWN'),
      photoeye: inductAuth.photoeye || (inductPe ? 'PROVEN' : 'UNKNOWN'),
      encoder: inductAuth.encoder || (inductEnc || enc ? 'PROVEN' : 'UNKNOWN'),
    },
    tracking_count: tracking.length,
    tracking,
    divert_count: divert_rows.length || (Array.isArray(zoneLanes) ? zoneLanes.length : 0),
    divert_rows,
    tracking_pe_count: trackingPes.length,
    tracking_pes: trackingPes,
    discovery_source: 'site_model',
    generation_state: pick.generation_state || ed.generation_state || ed.generation || 'GENERATABLE',
    generation_boundary: pick.generation_boundary || '',
    plc_generation: ed.plc_generation || sm.plc_generation || 'PHASE1_SUPPORTED',
    field_authority: fieldAuthority,
    application_structure: ed.application_structure || sm.application_structure || null,
    coverage: ed.coverage || sm.coverage || null,
    tracking_offset: _sorterFieldValue(priorOffset) || '',
    global_track_offset: _sorterFieldValue(priorOffset) || '',
    tracking_offset_authority: priorOffsetAuth || fieldAuthority.tracking_offset || '',
    review_resolutions: { ...priorRes },
    scan_zone: (scanBosses[0] && (scanBosses[0].scan_zone?.value || scanBosses[0].scan_zone
      || _sorterFieldValue(scanBosses[0].scan_zone))) || '',
    app_controls: ed.app_controls || sm.app_controls || [],
    scan_bosses: scanBosses,
    known_sorters: known,
    sorters_detected: known.length,
    detected: true,
    configuration_required: [],
  };
  if (!cfg.induct_conveyor) cfg.configuration_required.push('induct_conveyor');
  if (!cfg.induct_pe) cfg.configuration_required.push('induct_pe');
  if (!(cfg.tracking || []).some((t) => t && t.conveyor)) {
    cfg.configuration_required.push('tracking_conveyors');
  }
  // Only flag divert_output_io when unresolved rows exist — not for mass-PROVEN mappings
  if ((cfg.divert_rows || []).some((d) => {
    const a = String(d.authority?.divert_output_io || '').toUpperCase();
    const io = _sorterFieldValue(d.divert_output_io);
    return a.includes('REVIEW') || a === 'UNKNOWN' || !io || io.toUpperCase() === 'INVALID';
  })) {
    cfg.configuration_required.push('divert_output_io');
  }
  if (!(cfg.sorter_type || '').trim()) cfg.configuration_required.push('sorter_type');
  if (!(cfg.area_name || '').trim()) cfg.configuration_required.push('transport_area');
  return cfg;
}

/**
 * Apply canonical SiteModel to Sawtooth / Sorter editors + workbook.
 * Normal RUN import must never require Prefill / simulator buttons.
 */
async function applySiteModelToEditors({ discovery = null, reason = 'discovery' } = {}) {
  let site = null;
  let editors = discovery?.editors || null;
  if (typeof fortnaAPI?.getSiteModel === 'function') {
    try {
      const res = await fortnaAPI.getSiteModel();
      if (res?.success && res.site) {
        site = res.site;
        editors = res.editors || site.editors || editors;
      }
    } catch (_) { /* ignore */ }
  }
  if (!site && !editors) {
    log('SiteModel→editors: no site_model yet', 'warn');
    return { ok: false, reason: 'no_site_model' };
  }
  // Gate X — capture prior sorter review resolutions before clearing stale demo/prefill
  let priorSorterReview = {};
  let priorTrackOffset = '';
  let priorTrackOffsetAuth = '';
  try {
    const prev = autogenState.sorter || {};
    priorSorterReview = { ...(prev.review_resolutions || {}) };
    priorTrackOffset = prev.tracking_offset || prev.global_track_offset || '';
    priorTrackOffsetAuth = prev.tracking_offset_authority || '';
    if (!Object.keys(priorSorterReview).length) {
      const raw = localStorage.getItem('fortna_sorter_build');
      if (raw) {
        const parsed = JSON.parse(raw);
        priorSorterReview = { ...(parsed.review_resolutions || {}) };
        if (!priorTrackOffset) priorTrackOffset = parsed.tracking_offset || parsed.global_track_offset || '';
        if (!priorTrackOffsetAuth) priorTrackOffsetAuth = parsed.tracking_offset_authority || '';
      }
    }
  } catch (_) { /* ignore */ }

  // Fresh import: drop stale localStorage demo/prefill so it cannot override RUN discovery
  try {
    localStorage.removeItem('fortna_sawtooth_build');
    localStorage.removeItem('fortna_sorter_build');
  } catch (_) { /* ignore */ }

  // Stash priors so sorterBuildFromSiteModel can merge (Gate X — no phantom PENDING)
  if (!autogenState.sorter) autogenState.sorter = defaultSorterConfig();
  autogenState.sorter.review_resolutions = priorSorterReview;
  if (priorTrackOffset) {
    autogenState.sorter.tracking_offset = priorTrackOffset;
    autogenState.sorter.global_track_offset = priorTrackOffset;
  }
  if (priorTrackOffsetAuth) autogenState.sorter.tracking_offset_authority = priorTrackOffsetAuth;

  const saw = sawtoothBuildFromSiteModel(site || { editors, sawtooth_merges: discovery?.has_sawtooth ? [{}] : [] });
  const sorter = sorterBuildFromSiteModel(site || { editors, sorters: discovery?.has_sorter ? [{}] : [] });

  const summary = {
    machine: (site && site.machine_scope) || discovery?.machine || '',
    transport: (site?.counts?.equipment_included)
      || (editors?.transport?.items?.length)
      || discovery?.equipment_count
      || 0,
    sawtooth: false,
    sorter: false,
  };

  if (saw && (saw.collector_conveyor || (saw.lanes || []).some((l) => l && l.conveyor))) {
    autogenState.sawtooth = saw;
    persistSawtoothToWorkbook();
    try { renderSawtoothBuild(); } catch (_) { /* ignore */ }
    if ($('autogen-opt-sawtooth')) $('autogen-opt-sawtooth').checked = true;
    summary.sawtooth = true;
    const laneN = (saw.lanes || []).filter((l) => l && l.conveyor).length;
    log(
      `Sawtooth auto-populated from SiteModel (${reason}): collector=${saw.collector_conveyor || '—'} `
      + `enc=${saw.collector_encoder || 'UNRESOLVED'} lanes=${laneN}`,
      'ok',
    );
    if ((saw.configuration_required || []).length) {
      log(`Sawtooth unresolved (visible): ${(saw.configuration_required || []).join(', ')}`, 'warn');
    }
  } else {
    // CRITICAL: no usable Sawtooth editor config from CURRENT RUN.
    // Clear residual prior-project state so Compile Hub is NOT DETECTED
    // and cannot block export. Do not forcibly mark READY.
    if (discovery?.has_sawtooth || (site?.sawtooth_merges || []).length) {
      log('Sawtooth flagged in SiteModel but editor mapping empty — clearing stale editor (FAIL soft)', 'err');
    } else {
      log(`Sawtooth NOT DETECTED on current RUN (${reason}) — prior project Sawtooth cleared`, 'ok');
    }
    autogenState.sawtooth = defaultSawtoothConfig();
    try {
      if (autogenState.workbook) delete autogenState.workbook.sawtooth_build;
    } catch (_) { /* ignore */ }
    try { localStorage.removeItem('fortna_sawtooth_build'); } catch (_) { /* ignore */ }
    try { renderSawtoothBuild(); } catch (_) { /* ignore */ }
    if ($('autogen-opt-sawtooth')) $('autogen-opt-sawtooth').checked = false;
    try {
      Object.assign(ensureAutogenReadiness().sawtooth, emptyReadinessEntry('NOT_DETECTED'));
    } catch (_) { /* ignore */ }
    summary.sawtooth = false;
  }

  const sorterPopulated = !!(
    sorter
    && (
      sorter.sorter_name
      || sorter.induct_encoder_tag
      || (sorter.known_sorters || []).length
      || sorter.detected
      || sorter.sorters_detected
      || (sorter.encoders || []).length
    )
  );
  if (sorterPopulated) {
    // Normalize Python bridge shape → dashboard fields
    if (!sorter.sorter_name && (site?.sorters || []).length) {
      const pick = (site.sorters || []).find((s) => {
        const n = String(s.raw_name || s.normalized_name || '').toUpperCase();
        return n && !n.includes('SAWTOOTH');
      }) || site.sorters[0];
      sorter.sorter_name = pick.raw_name || pick.normalized_name || '';
      if (!sorter.induct_encoder_tag) {
        sorter.induct_encoder_tag = pick.encoder_io || (sorter.encoders || [])[0] || '';
        if (sorter.induct_encoder_tag) sorter.induct_has_encoder = 'yes';
      }
      if (!sorter.generation_state) sorter.generation_state = pick.generation_state || 'NOT_SUPPORTED';
    }
    if (!sorter.induct_encoder_tag && (sorter.encoders || []).length) {
      sorter.induct_encoder_tag = sorter.encoders[0];
      sorter.induct_has_encoder = 'yes';
    }
    autogenState.sorter = sorter;
    persistSorterToWorkbook();
    try { renderSorterBuild(); } catch (_) { /* ignore */ }
    // Do NOT auto-enable Sorter_Track pack when generation is NOT_SUPPORTED —
    // still show discovered data; engineer enables pack when ready.
    const gen = String(sorter.generation_state || '').toUpperCase();
    if (gen && !gen.includes('NOT_SUPPORTED') && $('autogen-opt-sorter-track')) {
      $('autogen-opt-sorter-track').checked = true;
    }
    summary.sorter = true;
    log(
      `Sorter auto-populated from SiteModel (${reason}): ${sorter.sorter_name || `${sorter.sorters_detected || '?'} sorter(s)`} `
      + `enc=${sorter.induct_encoder_tag || '—'} state=${sorter.generation_state || 'PARTIAL'}`,
      'ok',
    );
    if ((sorter.configuration_required || []).length) {
      log(`Sorter unresolved (visible): ${(sorter.configuration_required || []).join(', ')}`, 'warn');
    }
  } else if (discovery?.has_sorter || (site?.sorters || []).length) {
    log('Sorter detected in SiteModel but editor mapping produced empty config — FAIL soft', 'err');
  } else {
    // No proven Sorter on current RUN — clear residual prior-project sorter state
    try { autogenState.sorter = defaultSorterConfig(); } catch (_) { /* ignore */ }
    try {
      if (autogenState.workbook) delete autogenState.workbook.sorter_build;
    } catch (_) { /* ignore */ }
    try { localStorage.removeItem('fortna_sorter_build'); } catch (_) { /* ignore */ }
    try { renderSorterBuild(); } catch (_) { /* ignore */ }
    if ($('autogen-opt-sorter-track')) $('autogen-opt-sorter-track').checked = false;
    if ($('autogen-opt-shippingsorter')) $('autogen-opt-shippingsorter').checked = false;
    if ($('autogen-opt-shippingsorter-popup')) $('autogen-opt-shippingsorter-popup').checked = false;
    try {
      Object.assign(ensureAutogenReadiness().sorter, emptyReadinessEntry('NOT_DETECTED'));
    } catch (_) { /* ignore */ }
    summary.sorter = false;
    log(`Sorter NOT DETECTED on current RUN (${reason}) — prior project Sorter cleared`, 'ok');
  }

  // Persist workbook so Build PLC consumes the same canonical overrides
  try {
    if (typeof fortnaAPI?.autogenWorkbookSave === 'function' && autogenState.workbook) {
      await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
    }
  } catch (e) {
    log(`Workbook save after SiteModel apply failed: ${e?.message || e}`, 'warn');
  }

  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  try { updateSubsystemGenerationContract(site || discovery); } catch (_) { /* ignore */ }

  if (discovery?.ok === false) {
    log(`Discovery warning: ${discovery.error || 'failed'}`, 'warn');
  } else if (summary.machine) {
    log(
      `Discovery complete · ${summary.machine} · transport≈${summary.transport}`
      + ` · sawtooth=${summary.sawtooth ? 'YES' : 'no'} · sorter=${summary.sorter ? 'YES' : 'no'}`,
      'ok',
    );
  }
  return { ok: true, summary };
}

/** Subsystem generation contract shown on Autogen hub (what Build PLC will emit). */
function updateSubsystemGenerationContract(siteOrDiscovery) {
  const hub = $('autogen-compile-hub');
  if (!hub) return;
  let el = $('autogen-subsystem-contract');
  if (!el) {
    el = document.createElement('div');
    el.id = 'autogen-subsystem-contract';
    el.className = 'mt-3 rounded-lg border border-slate-800 bg-[#0c1219] p-3 text-[11px] space-y-1';
    const anchor = $('autogen-hub-readiness');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(el, anchor.nextSibling);
    else hub.appendChild(el);
  }
  const R = ensureAutogenReadiness();
  const map = {
    hardware: R.hardware,
    transport: R.transport,
    sawtooth: R.sawtooth,
    sorter: R.sorter,
    system: R.system,
  };
  // Prefer live recompute when hub refresh already ran; otherwise use stored
  try {
    const live = computeCompileHubReadiness();
    Object.assign(map, live);
  } catch (_) { /* ignore */ }
  const ship = shippingSorterEvidence();
  const wcs = wcsEvidence();
  const rows = [
    ['HARDWARE / IO', readinessDisplayLabel(map.hardware?.status)],
    ['TRANSPORT', readinessDisplayLabel(map.transport?.status)],
    ['SAWTOOTH', map.sawtooth?.status === 'NOT_DETECTED' ? 'N/A' : readinessDisplayLabel(map.sawtooth?.status)],
    ['SORTER', map.sorter?.status === 'NOT_DETECTED' ? 'N/A' : readinessDisplayLabel(map.sorter?.status)],
    ['SAFETY / ES', map.safety?.status === 'NOT_DETECTED' ? 'N/A' : readinessDisplayLabel(map.safety?.status)],
    ['SYSTEM / CORE', readinessDisplayLabel(map.system?.status)],
    ['WCS', wcs ? 'SiteModel supported' : 'NOT DETECTED / NOT SUPPORTED'],
    ['SHIPPING SORTER', ship.supported ? 'SiteModel supported' : 'NOT DETECTED / NOT SUPPORTED'],
  ];
  if (siteOrDiscovery?.ui_status_summary) {
    /* discovery summary available for future badge sync */
  }
  el.innerHTML = `<div class="text-[10px] uppercase tracking-wider text-violet-400 font-semibold mb-1">Subsystem generation contract</div>`
    + rows.map(([k, v]) => {
      const tone = /READY FOR AUTOGEN/.test(v)
        ? 'text-emerald-400'
        : (/N\/A|NOT DETECTED/.test(v) ? 'text-slate-500'
          : (/ERROR|NOT SUPPORTED|BLOCKED/.test(v) ? 'text-amber-400' : 'text-cyan-300'));
      return `<div class="flex justify-between gap-2 mono"><span class="text-slate-500">${k}</span><span class="${tone}">${v}</span></div>`;
    }).join('');
}

function emptySawTrackPeRow() {
  return { pe: '', pls_location: 0, blocked_jam_pre: 60 };
}

function emptySawLaneRow() {
  return {
    conveyor: '',
    pe: '',
    jam_pe: '',
    merge_pe: '',
    has_encoder: 'no',
    encoder_type: 'Enc_RIOCard',
    encoder_tag: '',
    drive: '',
    motor: '',
    lane_index: null,
    approach: '',
    collision: '',
    lane_input: '',
    slice_seconds: null,
    reserve_seconds: null,
    allowed_to_run: '',
    configuration_required: [],
    field_provenance: {},
  };
}

function normalizeSawLaneRow(row) {
  const r = { ...emptySawLaneRow(), ...(row || {}) };
  r.has_encoder = (r.has_encoder === 'yes' || r.has_encoder === true) ? 'yes' : 'no';
  if (!['Enc_RIOCard', 'Enc_CounterCard', 'Enc_Virtual_DistBased'].includes(r.encoder_type)) {
    r.encoder_type = 'Enc_RIOCard';
  }
  r.encoder_tag = r.encoder_tag || r.enc_tag || '';
  r.drive = r.drive || r.vfd || '';
  r.motor = r.motor || '';
  r.approach = r.approach || '';
  r.collision = r.collision || '';
  r.lane_input = r.lane_input || '';
  if (r.slice_seconds === '' || r.slice_seconds === undefined) r.slice_seconds = null;
  if (r.reserve_seconds === '' || r.reserve_seconds === undefined) r.reserve_seconds = null;
  return r;
}

function normalizeSawtoothConfig(raw) {
  const s = { ...defaultSawtoothConfig(), ...(raw || {}) };
  s.collector_has_encoder = (s.collector_has_encoder === 'no' || s.collector_has_encoder === false)
    ? 'no'
    : 'yes';
  // Legacy: encoder tag set ⇒ has encoder
  if (s.collector_encoder && s.collector_has_encoder !== 'no') s.collector_has_encoder = 'yes';
  if (!['Enc_RIOCard', 'Enc_CounterCard', 'Enc_Virtual_DistBased'].includes(s.collector_encoder_type)) {
    s.collector_encoder_type = 'Enc_RIOCard';
  }
  s.lanes = (s.lanes || []).map((l) => normalizeSawLaneRow(l));
  const tpn = Math.max(0, Math.min(16, Number(s.track_pe_count) || 0));
  s.track_pe_count = tpn;
  while ((s.track_pes || []).length < tpn) s.track_pes.push(emptySawTrackPeRow());
  s.track_pes = (s.track_pes || []).slice(0, tpn).map((r) => ({
    ...emptySawTrackPeRow(),
    ...(r || {}),
    pls_location: Number(r?.pls_location) || 0,
    blocked_jam_pre: Number(r?.blocked_jam_pre) || 60,
  }));
  reconcileSawtoothConfigurationRequired(s);
  return s;
}

function normalizeSorterTrackRow(row) {
  const r = { ...emptySorterTrackRow(), ...(row || {}) };
  r.has_encoder = (r.has_encoder === 'yes' || r.has_encoder === true) ? 'yes' : 'no';
  if (!['Enc_RIOCard', 'Enc_CounterCard', 'Enc_Virtual_DistBased'].includes(r.encoder_type)) {
    r.encoder_type = 'Enc_RIOCard';
  }
  r.encoder_tag = r.encoder_tag || r.enc_tag || '';
  return r;
}

function loadSorterFromWorkbook() {
  const wb = autogenState.workbook;
  const src = (wb && wb.sorter_build && typeof wb.sorter_build === 'object')
    ? wb.sorter_build
    : null;
  autogenState.sorter = { ...defaultSorterConfig(), ...(src || {}) };
  // Normalize arrays to counts
  const s = autogenState.sorter;
  if (!s.review_resolutions || typeof s.review_resolutions !== 'object') s.review_resolutions = {};
  if (s.tracking_offset == null) s.tracking_offset = s.global_track_offset || '';
  if (s.global_track_offset == null) s.global_track_offset = s.tracking_offset || '';
  s.tracking_count = Math.max(0, Math.min(40, Number(s.tracking_count) || (s.tracking || []).length || 0));
  s.divert_count = Math.max(0, Math.min(64, Number(s.divert_count) || 0));
  s.tracking_pe_count = Math.max(0, Math.min(64, Number(s.tracking_pe_count) || (s.tracking_pes || []).length || 0));
  s.induct_has_encoder = (s.induct_has_encoder === 'yes' || s.induct_has_encoder === true) ? 'yes' : 'no';
  if (!['Enc_RIOCard', 'Enc_CounterCard', 'Enc_Virtual_DistBased'].includes(s.induct_encoder_type)) {
    s.induct_encoder_type = 'Enc_RIOCard';
  }
  while ((s.tracking || []).length < s.tracking_count) s.tracking.push(emptySorterTrackRow());
  s.tracking = (s.tracking || []).slice(0, s.tracking_count).map(normalizeSorterTrackRow);
  while ((s.tracking_pes || []).length < s.tracking_pe_count) s.tracking_pes.push('');
  s.tracking_pes = (s.tracking_pes || []).slice(0, s.tracking_pe_count);
}

function conveyorNameList() {
  const wb = autogenState.workbook;
  const names = (wb?.conveyors || []).map((r) => r.conveyor || r.name || '').filter(Boolean);
  // Also allow names already chosen in sorter (if RUN not loaded)
  const s = autogenState.sorter || {};
  if (s.induct_conveyor) names.push(s.induct_conveyor);
  for (const t of s.tracking || []) if (t.conveyor) names.push(t.conveyor);
  return [...new Set(names)].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function photoeyeNameList() {
  const wb = autogenState.workbook;
  const names = [];
  const opts = wb?.options?.exit_pe || [];
  for (const p of opts) if (p) names.push(String(p));
  for (const r of wb?.conveyors || []) {
    for (const p of (r.exit_pe_choices || [])) if (p) names.push(String(p));
    if (r.exit_pe_tag) names.push(String(r.exit_pe_tag));
  }
  // IO map / pe devices if present
  for (const p of wb?.pe_devices || []) {
    const n = p.name || p.fortna_name || p.tag || '';
    if (n) names.push(String(n));
  }
  for (const row of wb?.io_map || wb?.io_rows || []) {
    const n = row.device || row.fortna_name || row.name || '';
    const t = (row.type || row.device_type || '').toLowerCase();
    if (n && (t.includes('photo') || t.includes('pe') || /^((ez)?pe)\d/i.test(n))) names.push(String(n));
  }
  const s = autogenState.sorter || {};
  if (s.induct_pe) names.push(s.induct_pe);
  for (const t of s.tracking || []) if (t.pe) names.push(t.pe);
  for (const p of s.tracking_pes || []) if (p) names.push(p);
  return [...new Set(names)].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

/** ENC / encoder tags from workbook + I/O devices (prefix ENC = encoder). */
function encoderNameList() {
  const wb = autogenState.workbook;
  const names = [];
  const pushEnc = (n) => {
    if (!n) return;
    const s = String(n).trim();
    if (!s) return;
    // Fortna RUN: ENC414, ENC504, … (not conveyor P###)
    if (/^ENC\d/i.test(s) || /^T_\d*ENC\d/i.test(s) || /_Enc$/i.test(s) || /encoder/i.test(s)) {
      names.push(s);
    }
  };
  for (const r of wb?.conveyors || []) {
    pushEnc(r.encoder || r.encoder_tag || r.enc_tag);
  }
  for (const n of wb?.encoder_devices || []) pushEnc(n);
  for (const d of wb?.devices || wb?.equipment || wb?.all_devices || wb?.device_list || []) {
    const n = d.name || d.fortna_name || d.tag || d.device || '';
    const t = (d.type || d.device_type || d.device_class || d.typeKey || '').toLowerCase();
    if (/enc/.test(t) || /^ENC/i.test(n)) pushEnc(n);
  }
  // I/O & Prints live list (same session as Sorter build)
  try {
    if (typeof ioState !== 'undefined' && Array.isArray(ioState.devices)) {
      for (const d of ioState.devices) pushEnc(d.name || d.fortna_name);
    }
  } catch (_) { /* ignore */ }
  for (const row of wb?.io_map || wb?.io_rows || wb?.io_points || []) {
    const n = row.device || row.fortna_name || row.name || row.device_name || row.tag || '';
    const t = (row.type || row.device_type || '').toLowerCase();
    if (/enc/.test(t) || /^ENC/i.test(n)) pushEnc(n);
  }
  // pe_devices / io tag rows sometimes carry ENC* misclassified as conveyor
  for (const p of wb?.pe_devices || []) {
    pushEnc(p.name || p.fortna_name || p.tag);
  }
  for (const row of wb?.io_tag_rows || []) {
    pushEnc(row.tag || row.fortna_name || row.name);
  }
  // Dashboard master device list (I/O & Prints tab) if mirrored on workbook
  for (const d of wb?.master_devices || wb?.print_devices || []) {
    pushEnc(d.name || d.fortna_name || d.tag);
  }
  // Live equipment from last autogen workbook build (conveyor table rarely lists ENC)
  try {
    const raw = localStorage.getItem('fortna_last_equipment_names');
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) arr.forEach(pushEnc);
    }
  } catch (_) { /* ignore */ }
  // Scan any string arrays that look like device inventories
  for (const key of Object.keys(wb || {})) {
    const v = wb[key];
    if (!Array.isArray(v) || v.length > 5000) continue;
    for (const item of v) {
      if (typeof item === 'string') pushEnc(item);
      else if (item && typeof item === 'object') {
        pushEnc(item.name || item.fortna_name || item.tag || item.device || item.device_name);
      }
    }
  }
  const s = autogenState.sorter || {};
  if (s.induct_encoder_tag) names.push(s.induct_encoder_tag);
  for (const t of s.tracking || []) if (t.encoder_tag) names.push(t.encoder_tag);
  for (const k of s.known_sorters || []) if (k && k.encoder) names.push(k.encoder);
  for (const e of s.encoders || []) {
    if (typeof e === 'string') names.push(e);
    else if (e) names.push(e.name || e.raw_name || e.normalized_name || '');
  }
  return [...new Set(names.filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

const SORTER_ENC_TYPE_OPTS = [
  { value: 'Enc_RIOCard', label: 'Enc_RIOCard (RIO pulse)' },
  { value: 'Enc_CounterCard', label: 'Enc_CounterCard (HSC)' },
  { value: 'Enc_Virtual_DistBased', label: 'Enc_Virtual_DistBased' },
];

function sorterEncTypeOptionsHtml(selected) {
  return SORTER_ENC_TYPE_OPTS.map((o) =>
    `<option value="${o.value}" ${o.value === selected ? 'selected' : ''}>${escapeHtml(o.label)}</option>`
  ).join('');
}

function sorterEncTagOptionsHtml(selected, encs) {
  const items = [`<option value="">Auto ENC### from conveyor (or pick ENC…)…</option>`];
  const seen = new Set();
  for (const v of encs || []) {
    if (!v || seen.has(v)) continue;
    seen.add(v);
    items.push(`<option value="${escapeHtml(v)}" ${v === selected ? 'selected' : ''}>${escapeHtml(v)}</option>`);
  }
  if (selected && !seen.has(selected)) {
    items.push(`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} *</option>`);
  }
  if (!encs || !encs.length) {
    items.push('<option value="" disabled>— no ENC* in RUN/I/O yet (load tar.gz) —</option>');
  }
  return items.join('');
}

function sorterSelectHtml(id, list, selected, emptyLabel) {
  const items = [`<option value="">${escapeHtml(emptyLabel || 'Select…')}</option>`];
  const seen = new Set();
  for (const v of list || []) {
    if (!v || seen.has(v)) continue;
    seen.add(v);
    items.push(`<option value="${escapeHtml(v)}" ${v === selected ? 'selected' : ''}>${escapeHtml(v)}</option>`);
  }
  if (selected && !seen.has(selected)) {
    items.push(`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} *</option>`);
  }
  return `<select id="${id}" class="w-full bg-[#101820] border border-slate-700 rounded-lg px-2 py-1.5 text-[11px] mono text-slate-200">${items.join('')}</select>`;
}

function updateSorterSummary() {
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  const el = $('autogen-sorter-summary');
  if (!el) return;
  const s = autogenState.sorter || defaultSorterConfig();
  const bits = [];
  const knownN = (s.known_sorters || []).length || s.sorters_detected || 0;
  if (knownN) bits.push(`${knownN} sorter${knownN === 1 ? '' : 's'}`);
  if (s.sorter_name) bits.push(s.sorter_name);
  if (s.induct_conveyor) bits.push(`induct ${s.induct_conveyor}`);
  if (s.tracking_count) bits.push(`${s.tracking_count} track`);
  if (s.divert_count) bits.push(`${s.divert_count} divert`);
  if (s.tracking_pe_count) bits.push(`${s.tracking_pe_count} PE`);
  const encN = (s.tracking || []).filter((t) => t && t.has_encoder === 'yes').length
    + (s.induct_has_encoder === 'yes' ? 1 : 0);
  if (encN) bits.push(`${encN} enc`);
  if (s.plc_generation) bits.push(`PLC ${s.plc_generation}`);
  el.textContent = bits.length ? bits.join(' · ') : 'collapsed · no config';
}

function ensureSorterTrackRow(i) {
  if (!autogenState.sorter.tracking) autogenState.sorter.tracking = [];
  if (!autogenState.sorter.tracking[i]) {
    autogenState.sorter.tracking[i] = emptySorterTrackRow();
  } else {
    autogenState.sorter.tracking[i] = normalizeSorterTrackRow(autogenState.sorter.tracking[i]);
  }
  return autogenState.sorter.tracking[i];
}

function renderSorterBuild() {
  const s = autogenState.sorter || defaultSorterConfig();
  // Keep configuration_required in sync with filled fields (Gate J immediacy)
  const cr = Array.isArray(s.configuration_required) ? [...s.configuration_required] : [];
  s.configuration_required = cr.filter((x) => {
    if (x === 'sorter_type') return !(s.sorter_type || '').trim();
    if (x === 'transport_area' || x === 'area_name') return !(s.area_name || '').trim();
    if (x === 'induct_conveyor') return !(s.induct_conveyor || '').trim();
    if (x === 'induct_pe') return !(s.induct_pe || '').trim();
    if (x === 'divert_output_io') {
      return (s.divert_rows || []).some((d) => {
        const a = String(d.authority?.divert_output_io || '').toUpperCase();
        const io = _sorterFieldValue(d.divert_output_io);
        return a.includes('REVIEW') || a === 'UNKNOWN' || !io || io.toUpperCase() === 'INVALID';
      });
    }
    return true;
  });
  autogenState.sorter = s;
  if ($('sorter-type') && s.sorter_type) $('sorter-type').value = s.sorter_type;
  const convs = conveyorNameList();
  const pes = photoeyeNameList();
  const encs = encoderNameList();

  fillSawSelect($('sorter-area-name'), transportAreaNameList(), s.area_name || '');

  // Discovered sorters list + field authority badges (not Phase-1 counts-only).
  const disc = $('sorter-discovered-list');
  if (disc) {
    const known = s.known_sorters || [];
    const fa = s.field_authority || {};
    if (!known.length) {
      disc.innerHTML = '<div class="text-[10px] text-slate-600">No sorters discovered on current RUN.</div>';
    } else {
      const authBits = Object.entries(fa).slice(0, 8).map(([k, v]) =>
        `<span class="inline-flex items-center gap-1 mr-2 mb-1">${escapeHtml(k)} ${sorterAuthorityBadge(v)}</span>`
      ).join('');
      disc.innerHTML = `
        <div class="flex flex-wrap gap-1 mb-2">${authBits || ''}</div>
        <div class="space-y-1 max-h-40 overflow-y-auto">
          ${known.map((k) => `
            <div class="flex flex-wrap items-center gap-2 text-[10px] mono border border-slate-800/80 rounded-lg px-2 py-1 bg-[#0a1016]">
              <span class="text-cyan-300">${escapeHtml(k.name || '')}</span>
              ${sorterAuthorityBadge(k.authority?.name || 'PROVEN')}
              <span class="text-slate-600">enc</span>
              <span class="text-amber-200/90">${escapeHtml(k.encoder || '—')}</span>
              ${sorterAuthorityBadge(k.authority?.encoder_io || (k.encoder ? 'PROVEN' : 'UNKNOWN'))}
              <span class="ml-auto text-slate-600">${escapeHtml(k.generation_state || '')}</span>
            </div>
          `).join('')}
        </div>`;
    }
  }

  const inductC = $('sorter-induct-conv');
  const inductP = $('sorter-induct-pe');
  if (inductC) {
    const cur = s.induct_conveyor || '';
    inductC.innerHTML = `<option value="">Select induct conveyor…</option>`
      + convs.map((n) => `<option value="${escapeHtml(n)}" ${n === cur ? 'selected' : ''}>${escapeHtml(n)}</option>`).join('');
    if (cur && ![...inductC.options].some((o) => o.value === cur)) {
      inductC.innerHTML += `<option value="${escapeHtml(cur)}" selected>${escapeHtml(cur)} *</option>`;
    }
  }
  if (inductP) {
    const cur = s.induct_pe || '';
    inductP.innerHTML = `<option value="">Select photoeye…</option>`
      + pes.map((n) => `<option value="${escapeHtml(n)}" ${n === cur ? 'selected' : ''}>${escapeHtml(n)}</option>`).join('');
    if (cur && ![...inductP.options].some((o) => o.value === cur)) {
      inductP.innerHTML += `<option value="${escapeHtml(cur)}" selected>${escapeHtml(cur)} *</option>`;
    }
  }
  const inductAuthEl = $('sorter-induct-auth');
  if (inductAuthEl) {
    const ia = s.induct_authority || {};
    inductAuthEl.innerHTML = [
      `conveyor ${sorterAuthorityBadge(ia.conveyor || (s.induct_conveyor ? 'DERIVED' : 'UNKNOWN'))}`,
      `PE ${sorterAuthorityBadge(ia.photoeye || (s.induct_pe ? 'PROVEN' : 'UNKNOWN'))}`,
      `enc ${sorterAuthorityBadge(ia.encoder || (s.induct_encoder_tag ? 'PROVEN' : 'UNKNOWN'))}`,
    ].join(' · ');
  }

  const inductHasEnc = $('sorter-induct-has-enc');
  const inductEncOpts = $('sorter-induct-enc-opts');
  const inductEncType = $('sorter-induct-enc-type');
  const inductEncTag = $('sorter-induct-enc-tag');
  if (inductHasEnc) inductHasEnc.value = s.induct_has_encoder === 'yes' ? 'yes' : 'no';
  if (inductEncOpts) {
    inductEncOpts.classList.toggle('hidden', s.induct_has_encoder !== 'yes');
    inductEncOpts.classList.toggle('flex', s.induct_has_encoder === 'yes');
  }
  if (inductEncType) {
    inductEncType.innerHTML = sorterEncTypeOptionsHtml(s.induct_encoder_type || 'Enc_RIOCard');
  }
  if (inductEncTag) {
    inductEncTag.innerHTML = sorterEncTagOptionsHtml(s.induct_encoder_tag || '', encs);
  }

  const trackCount = $('sorter-track-count');
  if (trackCount) trackCount.value = String(s.tracking_count || 0);
  const divertCount = $('sorter-divert-count');
  if (divertCount) divertCount.value = String(s.divert_count || 0);
  const peCount = $('sorter-pe-count');
  if (peCount) peCount.value = String(s.tracking_pe_count || 0);

  // Gate M — tracking offset editor
  const offEl = $('sorter-tracking-offset');
  const offAuthEl = $('sorter-tracking-offset-auth');
  const offState = $('sorter-tracking-offset-state');
  const offProv = $('sorter-tracking-offset-prov');
  if (offEl) offEl.value = _sorterFieldValue(s.tracking_offset || s.global_track_offset || '');
  const offAuth = s.tracking_offset_authority || s.field_authority?.tracking_offset || '';
  if (offAuthEl) offAuthEl.innerHTML = sorterAuthorityBadge(offAuth || (offEl?.value ? 'COMMISSIONING' : 'REVIEW_REQUIRED'));
  if (offState && offAuth) offState.value = _normalizeSorterStatus(offAuth) || offState.value || '';
  if (offProv) {
    offProv.textContent = offEl?.value
      ? `value=${offEl.value} · authority=${offAuth || '—'} · source=SorterModel/engineer (not invented)`
      : 'No RUN global offset — Outpoint Location is per-outpoint only.';
  }

  const divertBulk = $('sorter-divert-bulk');
  const divertRowsEl = $('sorter-divert-rows');
  if (divertRowsEl) {
    const rows = s.divert_rows || [];
    if (divertBulk) divertBulk.classList.toggle('hidden', !rows.length);
    if (!rows.length) {
      divertRowsEl.innerHTML = '<div class="text-[10px] text-slate-600">No SrtZoneLane divert rows discovered.</div>';
    } else {
      const peOpts = photoeyeNameList();
      divertRowsEl.innerHTML = rows.map((d, i) => {
        const peAuthRaw = d.authority?.divert_pe || 'REVIEW_REQUIRED';
        const peAuth = _normalizeSorterStatus(peAuthRaw) || peAuthRaw;
        const peVal = _sorterFieldValue(d.divert_pe) || '';
        const accepted = String(d.divert_pe_acceptance || d.authority?.divert_pe_acceptance || '');
        const hasCandidate = !!peVal && (
          peAuth === SORTER_STATUS_CATS.DERIVED || peAuth === SORTER_STATUS_CATS.PROVEN
        );
        const forceChange = d.divert_pe_ui_mode === 'change' || (!hasCandidate);
        const peSelect = peOpts.map((p) =>
          `<option value="${escapeHtml(p)}" ${p === peVal ? 'selected' : ''}>${escapeHtml(p)}</option>`
        ).join('');
        // GATE 3 labels — keep contiguous "Derived:" / "Proven:" for contract tests + UI clarity
        const peCandidatePrefix = peAuth === SORTER_STATUS_CATS.PROVEN ? 'Proven: ' : 'Derived: ';
        let peControls = '';
        if (hasCandidate && !forceChange) {
          // GATE 3 — show Derived/Proven candidate with Accept / Change (empty Select only when unknown)
          peControls = `
          <span class="text-sky-200/90">${peCandidatePrefix}<span class="text-sky-300">${escapeHtml(peVal)}</span></span>
          ${sorterAuthorityBadge(peAuth)}
          ${accepted ? `<span class="text-[9px] text-emerald-600/80">${escapeHtml(accepted)}</span>` : `
          <button type="button" class="sorter-divert-pe-accept btn-ghost px-1.5 py-0.5 rounded border border-sky-900/50 text-sky-300" data-i="${i}" title="Accept candidate — stores ENGINEER_ACCEPTED; does not falsify ${escapeHtml(peAuth)}">Accept</button>`}
          <button type="button" class="sorter-divert-pe-change btn-ghost px-1.5 py-0.5 rounded border border-fuchsia-900/50 text-fuchsia-300" data-i="${i}" title="Change Confirm PE">Change</button>`;
        } else {
          peControls = `
          <select class="sorter-divert-pe min-w-[8rem] bg-[#101820] border border-slate-700 rounded px-1 py-0.5 text-[10px] mono text-sky-300" data-i="${i}">
            <option value="">Confirm PE…</option>${peSelect}
            ${peVal && !peOpts.includes(peVal) ? `<option value="${escapeHtml(peVal)}" selected>${escapeHtml(peVal)} *</option>` : ''}
          </select>
          ${sorterAuthorityBadge(peAuth)}
          ${accepted ? `<span class="text-[9px] text-slate-500">${escapeHtml(accepted)}</span>` : ''}`;
        }
        return `
        <div class="flex flex-wrap items-center gap-2 text-[10px] mono border border-slate-800/80 rounded-lg px-2 py-1 bg-[#0a1016]" data-divert-i="${i}">
          <input type="checkbox" class="sorter-divert-sel rounded border-slate-600" data-i="${i}" title="Select for bulk">
          <span class="text-slate-600 w-5">#${i + 1}</span>
          <span class="text-cyan-300">${escapeHtml(d.name || '')}</span>
          ${sorterAuthorityBadge(d.authority?.topology || 'PROVEN')}
          <span class="text-slate-500">lane</span>
          <span class="text-slate-200">${escapeHtml(d.lane || '—')}</span>
          <span class="text-slate-500">host</span>
          <span class="text-slate-300">${escapeHtml(d.host_zone || '—')}</span>
          <span class="text-slate-500">out IO</span>
          <span class="text-amber-200/80">${escapeHtml(d.divert_output_io || 'INVALID')}</span>
          ${sorterAuthorityBadge(d.authority?.divert_output_io || 'REVIEW_REQUIRED')}
          <span class="text-slate-500">PE</span>
          ${peControls}
        </div>`;
      }).join('');
      divertRowsEl.querySelectorAll('.sorter-divert-pe-accept').forEach((btn) => {
        btn.addEventListener('click', () => {
          const i = Number(btn.dataset.i);
          const row = autogenState.sorter.divert_rows[i];
          if (!row) return;
          if (!row.authority) row.authority = {};
          const prev = _normalizeSorterStatus(row.authority.divert_pe);
          // Accept keeps DERIVED/PROVEN class; stores ENGINEER_ACCEPTED; never falsifies PROVEN
          if (prev === SORTER_STATUS_CATS.DERIVED || prev === SORTER_STATUS_CATS.PROVEN) {
            row.authority.divert_pe = prev;
          }
          row.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
          row.authority.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
          row.divert_pe_ui_mode = '';
          try { markReadinessDirty('sorter'); } catch (_) { /* ignore */ }
          renderSorterBuild();
        });
      });
      divertRowsEl.querySelectorAll('.sorter-divert-pe-change').forEach((btn) => {
        btn.addEventListener('click', () => {
          const i = Number(btn.dataset.i);
          const row = autogenState.sorter.divert_rows[i];
          if (!row) return;
          row.divert_pe_ui_mode = 'change';
          renderSorterBuild();
        });
      });
      divertRowsEl.querySelectorAll('.sorter-divert-pe').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          if (!autogenState.sorter.divert_rows[i]) return;
          const row = autogenState.sorter.divert_rows[i];
          row.divert_pe = sel.value || '';
          if (!row.authority) row.authority = {};
          const prev = _normalizeSorterStatus(row.authority.divert_pe);
          // Per-row override — never falsify PROVEN; store ENGINEER_ACCEPTED
          if (prev !== SORTER_STATUS_CATS.PROVEN) {
            row.authority.divert_pe = sel.value ? 'ENGINEER_REQUIRED' : 'REVIEW_REQUIRED';
            row.divert_pe_acceptance = sel.value ? 'ENGINEER_ACCEPTED' : '';
            row.authority.divert_pe_acceptance = row.divert_pe_acceptance;
          } else if (sel.value) {
            // PROVEN kept; engineer change still recorded as acceptance overlay
            row.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
            row.authority.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
          }
          row.divert_pe_ui_mode = '';
          try { markReadinessDirty('sorter'); } catch (_) { /* ignore */ }
          try { renderSorterReviewPanel(autogenState.sorter); } catch (_) { /* ignore */ }
          renderSorterBuild();
        });
      });
    }
  }

  const trackRows = $('sorter-track-rows');
  if (trackRows) {
    const n = s.tracking_count || 0;
    if (!n) {
      trackRows.innerHTML = '<div class="text-[10px] text-slate-600">Set count above to add tracking conveyor rows.</div>';
    } else {
      trackRows.innerHTML = Array.from({ length: n }, (_, i) => {
        const row = normalizeSorterTrackRow((s.tracking || [])[i]);
        const convOpts = convs.map((c) =>
          `<option value="${escapeHtml(c)}" ${c === row.conveyor ? 'selected' : ''}>${escapeHtml(c)}</option>`
        ).join('');
        const peOpts = pes.map((p) =>
          `<option value="${escapeHtml(p)}" ${p === row.pe ? 'selected' : ''}>${escapeHtml(p)}</option>`
        ).join('');
        const showEnc = row.has_encoder === 'yes';
        const tAuth = row.authority || {};
        return `<div class="rounded-lg border border-slate-800/80 bg-[#0a1016] p-2 space-y-1.5" data-track-i="${i}">
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-[10px] text-slate-600 w-6 mono">#${i + 1}</span>
            <select class="sorter-track-conv flex-1 min-w-[9rem] bg-[#101820] border border-slate-700 rounded-lg px-2 py-1 text-[10px] mono text-slate-200" data-i="${i}">
              <option value="">Tracking conveyor…</option>${convOpts}
            </select>
            ${sorterAuthorityBadge(tAuth.conveyor || (row.conveyor ? 'DERIVED' : 'UNKNOWN'))}
            <select class="sorter-track-pe flex-1 min-w-[9rem] bg-[#101820] border border-slate-700 rounded-lg px-2 py-1 text-[10px] mono text-sky-300" data-i="${i}">
              <option value="">Tracking photoeye…</option>${peOpts}
            </select>
            ${sorterAuthorityBadge(tAuth.photoeye || (row.pe ? 'PROVEN' : 'UNKNOWN'))}
            <label class="flex items-center gap-1 text-[10px] text-slate-500 shrink-0">
              <span>Enc</span>
              <select class="sorter-track-has-enc bg-[#101820] border border-slate-700 rounded-lg px-1.5 py-1 text-[10px] text-slate-200" data-i="${i}">
                <option value="no" ${row.has_encoder !== 'yes' ? 'selected' : ''}>No → NO_Enc</option>
                <option value="yes" ${row.has_encoder === 'yes' ? 'selected' : ''}>Yes</option>
              </select>
            </label>
          </div>
          <div class="sorter-track-enc-opts flex flex-wrap gap-2 items-center pl-8 ${showEnc ? '' : 'hidden'}" data-i="${i}">
            <select class="sorter-track-enc-type min-w-[11rem] bg-[#101820] border border-amber-900/40 rounded-lg px-2 py-1 text-[10px] mono text-amber-200/90" data-i="${i}">
              ${sorterEncTypeOptionsHtml(row.encoder_type)}
            </select>
            <select class="sorter-track-enc-tag flex-1 min-w-[10rem] bg-[#101820] border border-amber-900/40 rounded-lg px-2 py-1 text-[10px] mono text-amber-200/90" data-i="${i}">
              ${sorterEncTagOptionsHtml(row.encoder_tag, encs)}
            </select>
          </div>
        </div>`;
      }).join('');
      trackRows.querySelectorAll('.sorter-track-conv').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          ensureSorterTrackRow(i).conveyor = sel.value || '';
          updateSorterSummary();
        });
      });
      trackRows.querySelectorAll('.sorter-track-pe').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          ensureSorterTrackRow(i).pe = sel.value || '';
          updateSorterSummary();
        });
      });
      trackRows.querySelectorAll('.sorter-track-has-enc').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          const row = ensureSorterTrackRow(i);
          row.has_encoder = sel.value === 'yes' ? 'yes' : 'no';
          const opts = trackRows.querySelector(`.sorter-track-enc-opts[data-i="${i}"]`);
          if (opts) opts.classList.toggle('hidden', row.has_encoder !== 'yes');
          updateSorterSummary();
        });
      });
      trackRows.querySelectorAll('.sorter-track-enc-type').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          ensureSorterTrackRow(i).encoder_type = sel.value || 'Enc_RIOCard';
          updateSorterSummary();
        });
      });
      trackRows.querySelectorAll('.sorter-track-enc-tag').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          ensureSorterTrackRow(i).encoder_tag = sel.value || '';
          updateSorterSummary();
        });
      });
    }
  }

  const peRows = $('sorter-pe-rows');
  if (peRows) {
    const n = s.tracking_pe_count || 0;
    if (!n) {
      peRows.innerHTML = '<div class="text-[10px] text-slate-600">Set count above to add tracking PE dropdowns.</div>';
    } else {
      peRows.innerHTML = Array.from({ length: n }, (_, i) => {
        const cur = (s.tracking_pes || [])[i] || '';
        const peOpts = pes.map((p) =>
          `<option value="${escapeHtml(p)}" ${p === cur ? 'selected' : ''}>${escapeHtml(p)}</option>`
        ).join('');
        return `<div class="flex flex-wrap gap-2 items-center">
          <span class="text-[10px] text-slate-600 w-6 mono">#${i + 1}</span>
          <select class="sorter-extra-pe flex-1 min-w-[12rem] bg-[#101820] border border-slate-700 rounded-lg px-2 py-1 text-[10px] mono text-sky-300" data-i="${i}">
            <option value="">Tracking photoeye…</option>${peOpts}
          </select>
        </div>`;
      }).join('');
      peRows.querySelectorAll('.sorter-extra-pe').forEach((sel) => {
        sel.addEventListener('change', () => {
          const i = Number(sel.dataset.i);
          autogenState.sorter.tracking_pes[i] = sel.value || '';
          updateSorterSummary();
        });
      });
    }
  }
  try { renderSorterReviewPanel(s); } catch (_) { /* ignore */ }
  updateSorterSummary();
}

function persistSorterToWorkbook() {
  if (!autogenState.workbook) autogenState.workbook = { conveyors: [], options: {} };
  autogenState.workbook.sorter_build = { ...autogenState.sorter };
}

function wireSorterBuildUi() {
  const trackCount = $('sorter-track-count');
  const divertCount = $('sorter-divert-count');
  const peCount = $('sorter-pe-count');
  const inductC = $('sorter-induct-conv');
  const inductP = $('sorter-induct-pe');
  const inductHasEnc = $('sorter-induct-has-enc');
  const inductEncType = $('sorter-induct-enc-type');
  const inductEncTag = $('sorter-induct-enc-tag');
  const touchSorter = () => { try { markReadinessDirty('sorter'); } catch (_) { /* ignore */ } };

  trackCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(40, parseInt(trackCount.value, 10) || 0));
    trackCount.value = String(n);
    autogenState.sorter.tracking_count = n;
    const arr = (autogenState.sorter.tracking || []).map(normalizeSorterTrackRow);
    while (arr.length < n) arr.push(emptySorterTrackRow());
    autogenState.sorter.tracking = arr.slice(0, n);
    touchSorter();
    renderSorterBuild();
  });
  divertCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(64, parseInt(divertCount.value, 10) || 0));
    divertCount.value = String(n);
    autogenState.sorter.divert_count = n;
    touchSorter();
    updateSorterSummary();
  });
  peCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(64, parseInt(peCount.value, 10) || 0));
    peCount.value = String(n);
    autogenState.sorter.tracking_pe_count = n;
    const arr = autogenState.sorter.tracking_pes || [];
    while (arr.length < n) arr.push('');
    autogenState.sorter.tracking_pes = arr.slice(0, n);
    touchSorter();
    renderSorterBuild();
  });
  inductC?.addEventListener('change', () => {
    autogenState.sorter.induct_conveyor = inductC.value || '';
    touchSorter();
    updateSorterSummary();
  });
  inductP?.addEventListener('change', () => {
    autogenState.sorter.induct_pe = inductP.value || '';
    touchSorter();
    updateSorterSummary();
  });
  inductHasEnc?.addEventListener('change', () => {
    autogenState.sorter.induct_has_encoder = inductHasEnc.value === 'yes' ? 'yes' : 'no';
    const opts = $('sorter-induct-enc-opts');
    if (opts) {
      const show = autogenState.sorter.induct_has_encoder === 'yes';
      opts.classList.toggle('hidden', !show);
      opts.classList.toggle('flex', show);
    }
    touchSorter();
    updateSorterSummary();
  });
  inductEncType?.addEventListener('change', () => {
    autogenState.sorter.induct_encoder_type = inductEncType.value || 'Enc_RIOCard';
    touchSorter();
    updateSorterSummary();
  });
  inductEncTag?.addEventListener('change', () => {
    autogenState.sorter.induct_encoder_tag = inductEncTag.value || '';
    touchSorter();
    updateSorterSummary();
  });

  $('sorter-type')?.addEventListener('change', () => {
    autogenState.sorter.sorter_type = $('sorter-type').value || '';
    // Clear satisfied configuration_required keys immediately
    const cr = autogenState.sorter.configuration_required || [];
    autogenState.sorter.configuration_required = cr.filter((x) => x !== 'sorter_type');
    touchSorter();
    renderSorterBuild();
  });
  $('sorter-area-name')?.addEventListener('change', () => {
    autogenState.sorter.area_name = $('sorter-area-name').value || '';
    const cr = autogenState.sorter.configuration_required || [];
    autogenState.sorter.configuration_required = cr.filter((x) => x !== 'transport_area' && x !== 'area_name');
    touchSorter();
    renderSorterBuild();
  });

  $('sorter-tracking-offset')?.addEventListener('change', () => {
    const v = $('sorter-tracking-offset').value || '';
    autogenState.sorter.tracking_offset = v;
    autogenState.sorter.global_track_offset = v;
    touchSorter();
    try { renderSorterReviewPanel(autogenState.sorter); } catch (_) { /* ignore */ }
  });
  $('sorter-tracking-offset-state')?.addEventListener('change', () => {
    autogenState.sorter.tracking_offset_authority = $('sorter-tracking-offset-state').value || '';
    touchSorter();
    try { renderSorterReviewPanel(autogenState.sorter); } catch (_) { /* ignore */ }
  });

  // Gate N — bulk divert PE actions (never UNKNOWN→PROVEN)
  $('btn-divert-accept-derived')?.addEventListener('click', () => {
    const rows = autogenState.sorter.divert_rows || [];
    rows.forEach((row) => {
      const auth = _normalizeSorterStatus(row?.authority?.divert_pe);
      const pe = _sorterFieldValue(row?.divert_pe);
      if (auth === 'UNKNOWN' || (!pe && auth !== SORTER_STATUS_CATS.DERIVED)) return;
      if (auth !== SORTER_STATUS_CATS.DERIVED) return;
      if (!row.authority) row.authority = {};
      row.authority.divert_pe = 'DERIVED';
      row.authority.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
      row.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
    });
    touchSorter();
    renderSorterBuild();
  });
  $('btn-divert-apply-pe')?.addEventListener('click', () => {
    const val = ($('sorter-divert-bulk-pe')?.value || '').trim();
    if (!val) return;
    const selected = [...(document.querySelectorAll('.sorter-divert-sel:checked') || [])]
      .map((el) => Number(el.dataset.i));
    const rows = autogenState.sorter.divert_rows || [];
    selected.forEach((i) => {
      if (!rows[i]) return;
      rows[i].divert_pe = val;
      if (!rows[i].authority) rows[i].authority = {};
      if (_normalizeSorterStatus(rows[i].authority.divert_pe) !== SORTER_STATUS_CATS.PROVEN) {
        rows[i].authority.divert_pe = 'ENGINEER_REQUIRED';
        rows[i].divert_pe_acceptance = 'ENGINEER_ACCEPTED';
        rows[i].authority.divert_pe_acceptance = 'ENGINEER_ACCEPTED';
      }
    });
    touchSorter();
    renderSorterBuild();
  });
  $('btn-divert-mark-commission')?.addEventListener('click', () => {
    const selected = [...(document.querySelectorAll('.sorter-divert-sel:checked') || [])]
      .map((el) => Number(el.dataset.i));
    const rows = autogenState.sorter.divert_rows || [];
    selected.forEach((i) => {
      if (!rows[i]) return;
      if (!rows[i].authority) rows[i].authority = {};
      rows[i].authority.divert_pe = 'COMMISSIONING';
    });
    touchSorter();
    renderSorterBuild();
  });

  $('btn-sorter-save')?.addEventListener('click', async () => {
    if ($('sorter-type')) autogenState.sorter.sorter_type = $('sorter-type').value || '';
    if ($('sorter-area-name')) autogenState.sorter.area_name = $('sorter-area-name').value || '';
    if ($('sorter-tracking-offset')) {
      autogenState.sorter.tracking_offset = $('sorter-tracking-offset').value || '';
      autogenState.sorter.global_track_offset = autogenState.sorter.tracking_offset;
    }
    if ($('sorter-tracking-offset-state')) {
      autogenState.sorter.tracking_offset_authority = $('sorter-tracking-offset-state').value
        || autogenState.sorter.tracking_offset_authority || '';
    }
    // Keep review_resolutions on Apply (Gate X)
    if (!autogenState.sorter.review_resolutions) autogenState.sorter.review_resolutions = {};
    persistSorterToWorkbook();
    const st = $('sorter-save-status');
    const s = autogenState.sorter || {};
    const hasData = !!(
      s.induct_conveyor
      || (s.tracking_count || 0) > 0
      || (s.divert_count || 0) > 0
      || (s.tracking || []).some((t) => t && (t.conveyor || t.encoder_tag))
      || (s.known_sorters || []).length
      || s.sorter_type
      || s.sorter_name
    );
    const unresolved = (s.configuration_required || []).length;
    const gen = String(s.generation_state || '').toUpperCase();
    const plcGen = String(s.plc_generation || 'PHASE1_SUPPORTED').toUpperCase();
    const phase1Ok = plcGen.includes('PHASE1') || plcGen.includes('GENERATED')
      || gen.includes('GENERATABLE') || gen.includes('GENERATED');
    if (hasData && (!gen.includes('NOT_SUPPORTED') || phase1Ok) && phase1Ok
      && $('autogen-opt-sorter-track')) {
      $('autogen-opt-sorter-track').checked = true;
    }
    try {
      // Safety-style merge: never hollow Transport / Safety by writing sorter alone.
      if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
        let disk = {};
        try {
          if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
            const full = await fortnaAPI.autogenWorkbookLoad();
            if (full?.success && full.workbook) disk = full.workbook;
          }
        } catch (_) { /* ignore */ }
        const mem = autogenState.workbook || {};
        const payload = { ...s, appliedAt: new Date().toISOString(), source: 'sorter_build' };
        const wb = {
          ...disk,
          ...mem,
          conveyors: (Array.isArray(mem.conveyors) && mem.conveyors.length)
            ? mem.conveyors
            : (disk.conveyors || mem.conveyors || []),
          areas: (Array.isArray(mem.areas) && mem.areas.length)
            ? mem.areas
            : (disk.areas || mem.areas || []),
          // CRITICAL: never let hollow Transport safety_build beat Safety Apply on disk.
          safety_build: preferSafetyBuild(
            mem.safety_build || autogenState.safety_build,
            disk.safety_build,
          ),
          sawtooth_build: mem.sawtooth_build || disk.sawtooth_build || null,
          sorter_build: payload,
        };
        // Keep shared state in sync (Safety + Sorter + Autogen)
        if (wb.safety_build) {
          autogenState.safety_build = wb.safety_build;
          try { window.autogenState = autogenState; } catch (_) { /* ignore */ }
        }
        autogenState.workbook = wb;
        autogenState.sorter = { ...s, appliedAt: payload.appliedAt };
        const res = await fortnaAPI.autogenWorkbookSave({ workbook: wb });
        if (res && res.success === false) {
          if (st) {
            st.textContent = `Apply failed: ${res.message || res.error || 'unknown'}`;
            st.className = 'text-[10px] text-red-400 mono';
          }
          return;
        }
      } else if (typeof window.saveAutogenWorkbook === 'function') {
        await window.saveAutogenWorkbook();
      }
      try {
        localStorage.setItem('fortna_sorter_build', JSON.stringify(autogenState.sorter));
      } catch (_) { /* ignore */ }
      // Persist Phase 1 generation flags on Apply
      if (hasData && (!s.plc_generation || String(s.plc_generation).includes('NOT_STARTED'))) {
        s.plc_generation = 'PHASE1_SUPPORTED';
        s.generation_state = s.generation_state && !String(s.generation_state).includes('NOT_SUPPORTED')
          ? s.generation_state
          : 'GENERATABLE';
        autogenState.sorter = s;
        if (autogenState.workbook?.sorter_build) {
          autogenState.workbook.sorter_build.plc_generation = s.plc_generation;
          autogenState.workbook.sorter_build.generation_state = s.generation_state;
        }
      }
      if (hasData && phase1Ok && unresolved === 0) {
        setReadinessApplied('sorter', `${s.sorter_name || s.sorter_type || 'sorter'} applied`);
        const ship = shippingSorterEvidence();
        if (st) {
          st.textContent = ship.supported
            ? `Applied · Sorter_Track + Area programs (${ship.areaName || s.area_name || 'sorter area'})`
            : 'Applied · Sorter_Track (Phase 1) — area programs need sorter area identity';
          st.className = 'text-[10px] text-emerald-500 mono';
        }
        autogenLog(
          ship.supported
            ? `Sorter Apply → Sorter_Track + ${ship.areaName || 'sorter'} Area_Fast/Slow/L1/L2(+L3).`
            : 'Sorter Apply → Compile hub READY (Sorter_Track Phase 1). Area packs need sorter_area_name.',
          'ok',
        );
      } else if (hasData && phase1Ok) {
        const e = ensureAutogenReadiness().sorter;
        e.dirty = false;
        e.appliedAt = new Date().toISOString();
        e.status = 'REVIEW_REQUIRED';
        e.unresolved = unresolved;
        e.detail = `Sorter_Track supported · ${unresolved || 0} engineer/review remaining`;
        refreshAutogenCompileHub();
        if (st) {
          st.textContent = 'Applied · Sorter_Track supported · REVIEW remaining';
          st.className = 'text-[10px] text-amber-400 mono';
        }
        autogenLog(
          `Sorter Apply → workbook.sorter_build (${(s.known_sorters || []).length || 0} sorters, `
          + `${s.divert_count || 0} divert) — PLC generation ${plcGen}`,
          'ok',
        );
      } else if (hasData) {
        const e = ensureAutogenReadiness().sorter;
        e.dirty = false;
        e.appliedAt = new Date().toISOString();
        e.status = 'REVIEW_REQUIRED';
        e.unresolved = unresolved;
        e.detail = gen.includes('NOT_SUPPORTED')
          ? 'GENERATION NOT SUPPORTED'
          : `${unresolved || 0} unresolved — review before Export`;
        refreshAutogenCompileHub();
        if (st) {
          st.textContent = gen.includes('NOT_SUPPORTED')
            ? 'Applied · NOT SUPPORTED'
            : 'Applied · REVIEW REQUIRED';
          st.className = 'text-[10px] text-amber-400 mono';
        }
        autogenLog(
          `Sorter Apply → workbook.sorter_build (${(s.known_sorters || []).length || 0} sorters, `
          + `${s.divert_count || 0} divert) — PLC generation ${plcGen}`,
          'ok',
        );
      } else {
        if (st) { st.textContent = 'Nothing to apply'; st.className = 'text-[10px] text-slate-500 mono'; }
      }
    } catch (e) {
      if (st) { st.textContent = 'Apply failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Sorter Apply failed: ${e?.message || e}`, 'err');
    }
  });
  $('btn-sorter-clear')?.addEventListener('click', () => {
    autogenState.sorter = defaultSorterConfig();
    persistSorterToWorkbook();
    const e = ensureAutogenReadiness().sorter;
    Object.assign(e, emptyReadinessEntry());
    renderSorterBuild();
    const st = $('sorter-save-status');
    if (st) { st.textContent = 'Cleared'; st.className = 'text-[10px] text-slate-500 mono'; }
    refreshAutogenCompileHub();
  });

  // Restore localStorage if workbook empty
  try {
    const raw = localStorage.getItem('fortna_sorter_build');
    if (raw && !autogenState.workbook?.sorter_build) {
      autogenState.sorter = { ...defaultSorterConfig(), ...JSON.parse(raw) };
    }
  } catch (_) { /* ignore */ }
  if ($('sorter-type')) $('sorter-type').value = autogenState.sorter.sorter_type || '';
  renderSorterBuild();
}

/* —— Sawtooth / collector merge design —— */
function updateSawtoothSummary() {
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  const el = $('sawtooth-summary');
  if (!el) return;
  const s = reconcileSawtoothConfigurationRequired(autogenState.sawtooth || {});
  autogenState.sawtooth = s;
  const n = Number(s.lane_count || (s.lanes || []).length || 0);
  const enc = s.collector_has_encoder === 'no'
    ? 'NO_Enc'
    : (s.collector_encoder || 'UNRESOLVED');
  const unresolved = (s.configuration_required || []).length;
  const src = s.discovery_source === 'site_model' ? 'RUN auto' : (s.discovery_source || 'manual');
  const banner = $('sawtooth-detect-banner');
  if (banner) {
    if (s.collector_conveyor || n > 0) {
      banner.classList.remove('hidden');
      banner.innerHTML = `<span class="text-emerald-300 font-semibold">Sawtooth: ${escapeHtml(s.merge_identity || 'merge')} detected</span>`
        + ` · ${n} lane(s) · collector <span class="mono">${escapeHtml(s.collector_conveyor || '—')}</span>`
        + ` · enc <span class="mono">${escapeHtml(enc)}</span>`
        + ` · <span class="text-slate-500">${escapeHtml(src)}</span>`
        + (unresolved ? ` · <span class="text-amber-300">${unresolved} unresolved</span>` : '');
    } else {
      banner.classList.remove('hidden');
      banner.innerHTML = '<span class="text-slate-500">Sawtooth: Not detected on active RUN</span>';
    }
  }
  el.textContent = s.collector_conveyor
    ? `${s.collector_conveyor} · enc ${enc} · ${n} lane(s)${unresolved ? ` · ${unresolved} unresolved` : ''}`
    : 'Not detected';
}

function persistSawtoothToWorkbook() {
  if (!autogenState.workbook) autogenState.workbook = { conveyors: [], options: {} };
  autogenState.workbook.sawtooth_build = { ...autogenState.sawtooth };
}

function fillSawSelect(sel, values, current, allowBlank = true) {
  if (!sel) return;
  const cur = current || '';
  let html = allowBlank ? '<option value="">—</option>' : '';
  (values || []).forEach((v) => {
    html += `<option value="${escapeHtml(v)}" ${v === cur ? 'selected' : ''}>${escapeHtml(v)}</option>`;
  });
  if (cur && !(values || []).includes(cur)) {
    html += `<option value="${escapeHtml(cur)}" selected>${escapeHtml(cur)} (custom)</option>`;
  }
  sel.innerHTML = html;
}

function renderSawtoothBuild() {
  const s = autogenState.sawtooth = normalizeSawtoothConfig(
    autogenState.sawtooth || defaultSawtoothConfig(),
  );
  const convs = typeof conveyorNameList === 'function' ? conveyorNameList() : [];
  const pes = typeof photoeyeNameList === 'function' ? photoeyeNameList() : [];
  const encs = typeof encoderNameList === 'function' ? encoderNameList() : [];
  const encFallback = encs.length ? encs : convs.map((c) => `${c}_Enc`);

  fillSawSelect($('saw-collector-conv'), convs, s.collector_conveyor);
  fillSawSelect($('saw-downstream-conv'), convs, s.downstream_conveyor);
  fillSawSelect($('saw-coll-jam-pe'), pes, s.collector_jam_pe);
  fillSawSelect($('saw-coll-jam-pe-b'), pes, s.collector_jam_pe_b);
  fillSawSelect($('saw-coll-jam-pe-c'), pes, s.collector_jam_pe_c);
  fillSawSelect($('saw-coll-jam-pe-d'), pes, s.collector_jam_pe_d);
  fillSawSelect($('saw-eow-pe'), pes, s.eow_pe);
  if ($('saw-clctr-speed')) $('saw-clctr-speed').value = String(s.clctr_speed_fpm ?? 140);
  if ($('saw-clctr-runout')) $('saw-clctr-runout').value = String(s.clctr_runout_dist ?? 0);
  if ($('saw-slug-gap-adder')) $('saw-slug-gap-adder').value = String(s.clctr_slug_gap_adder ?? 0);
  if ($('saw-safety-tmr')) $('saw-safety-tmr').value = String(s.clctr_safety_tmr_preset ?? 0);
  if ($('saw-min-gap')) $('saw-min-gap').value = String(s.clctr_min_gap ?? 0);
  if ($('saw-slot-resv-mult')) $('saw-slot-resv-mult').value = String(s.slot_reserve_multiple ?? 1);
  if ($('saw-real-enc-ipp')) $('saw-real-enc-ipp').value = String(s.real_enc_ipp ?? 0);
  if ($('saw-pseudo-enc-ipp')) $('saw-pseudo-enc-ipp').value = String(s.pseudo_enc_ipp ?? 0);
  if ($('saw-pseudo-enc-max')) $('saw-pseudo-enc-max').value = String(s.pseudo_enc_max_cnt ?? 0);
  if ($('saw-trk-array-size')) $('saw-trk-array-size').value = String(s.track_array_size ?? 0);
  if ($('saw-lane-empty-opt')) $('saw-lane-empty-opt').value = String(s.lane_empty_opt_preset ?? 0);
  if ($('saw-use-gapstore')) $('saw-use-gapstore').checked = !!s.use_gapstore;
  if ($('saw-lane-count')) $('saw-lane-count').value = String(s.lane_count || 4);
  if ($('saw-track-pe-count')) $('saw-track-pe-count').value = String(s.track_pe_count || 0);
  if ($('saw-mrg-id')) $('saw-mrg-id').value = s.mrg_id || '414';
  fillSawSelect($('saw-area-name'), transportAreaNameList(), s.area_name || '');
  if ($('saw-enable-trk')) $('saw-enable-trk').checked = s.enable_track !== false;
  if ($('saw-enable-resv')) $('saw-enable-resv').checked = s.enable_reserve !== false;
  if ($('saw-no-carton-check')) $('saw-no-carton-check').checked = !!s.no_carton_check;

  // Collector carton-tracking encoder
  const hasEnc = $('saw-collector-has-enc');
  if (hasEnc) hasEnc.value = s.collector_has_encoder === 'no' ? 'no' : 'yes';
  const encOpts = $('saw-collector-enc-opts');
  if (encOpts) {
    const show = s.collector_has_encoder !== 'no';
    encOpts.classList.toggle('hidden', !show);
    encOpts.classList.toggle('flex', show);
  }
  const encType = $('saw-collector-enc-type');
  if (encType) encType.innerHTML = sorterEncTypeOptionsHtml(s.collector_encoder_type || 'Enc_RIOCard');
  const encTag = $('saw-collector-enc');
  if (encTag) encTag.innerHTML = sorterEncTagOptionsHtml(s.collector_encoder || '', encFallback);
  const encRoleEl = $('saw-collector-enc-role');
  const encSatisfied = sawtoothCollectorEncoderSatisfied(s);
  const encReqHint = $('saw-collector-enc-req-hint');
  if (encReqHint) encReqHint.classList.toggle('hidden', encSatisfied && !!(s.collector_encoder || '').trim());
  if (encRoleEl) {
    const role = s.encoder_role || s.collector_encoder_role || '';
    const encName = s.collector_encoder || '';
    if (encName && role === 'collector_tracking') {
      encRoleEl.textContent = `${encName} · proven role: collector tracking (Sawtooth)`;
      encRoleEl.classList.remove('hidden');
    } else if (encName) {
      encRoleEl.textContent = `${encName} · role: ${role || 'review associations'}`;
      encRoleEl.classList.remove('hidden');
    } else {
      encRoleEl.textContent = '';
      encRoleEl.classList.add('hidden');
    }
  }

  // Lane count comes from RUN discovery — do not invent empty lanes when none detected.
  let n = Math.max(0, Math.min(12, Number(s.lane_count) || (s.lanes || []).length || 0));
  if (!n && (s.lanes || []).length) n = s.lanes.length;
  s.lane_count = n;
  if (n > 0) {
    while ((s.lanes || []).length < n) s.lanes.push(emptySawLaneRow());
    s.lanes = (s.lanes || []).slice(0, n).map((l) => normalizeSawLaneRow(l));
  } else {
    s.lanes = [];
  }

  const host = $('saw-lane-rows');
  if (host) {
    host.innerHTML = s.lanes.map((lane, i) => {
      const unresolved = (lane.configuration_required || []).length;
      const idxLabel = lane.lane_index != null ? `Ndx ${lane.lane_index}` : `Lane ${i + 1}`;
      const slice = lane.slice_seconds != null ? lane.slice_seconds : '—';
      const reserve = lane.reserve_seconds != null ? lane.reserve_seconds : '—';
      return `
      <details class="rounded-lg border ${unresolved ? 'border-amber-800/50' : 'border-slate-800'} bg-[#070b12] p-2" data-saw-lane="${i}" open>
        <summary class="cursor-pointer text-[11px] text-amber-200/90 font-medium select-none">
          ${escapeHtml(idxLabel)} · <span class="mono text-slate-300">${escapeHtml(lane.conveyor || 'UNRESOLVED')}</span>
          · PE <span class="mono text-sky-300">${escapeHtml(lane.pe || '—')}</span>
          · Drive <span class="mono text-violet-300">${escapeHtml(lane.drive || '—')}</span>
          ${unresolved ? '<span class="text-amber-400 text-[9px] ml-1">review</span>' : ''}
        </summary>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Conveyor</label>
            <select data-saw-field="conveyor" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-slate-200"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Product PE</label>
            <select data-saw-field="pe" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Drive / VFD</label>
            <input data-saw-field="drive" type="text" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-violet-300" value="${escapeHtml(lane.drive || '')}">
          </div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 text-[10px]">
          <div class="text-slate-500">Slice s: <span class="mono text-slate-300">${escapeHtml(String(slice))}</span></div>
          <div class="text-slate-500">Reserve s: <span class="mono text-slate-300">${escapeHtml(String(reserve))}</span></div>
          <div class="text-slate-500">Approach: <span class="mono text-slate-300">${escapeHtml(lane.approach || '—')}</span></div>
          <div class="text-slate-500">Collision: <span class="mono text-slate-300">${escapeHtml(lane.collision || '—')}</span></div>
        </div>
      </details>`;
    }).join('');
    host.querySelectorAll('[data-saw-lane]').forEach((row) => {
      const i = Number(row.dataset.sawLane);
      const lane = s.lanes[i] || emptySawLaneRow();
      row.querySelectorAll('[data-saw-field]').forEach((sel) => {
        const field = sel.dataset.sawField;
        if (field === 'conveyor') fillSawSelect(sel, convs, lane.conveyor || '');
        else if (field === 'pe') fillSawSelect(sel, pes, lane.pe || '');
        else if (field === 'drive') sel.value = lane.drive || '';
        sel.addEventListener('change', () => {
          s.lanes[i] = normalizeSawLaneRow(s.lanes[i] || emptySawLaneRow());
          s.lanes[i][field] = sel.value || '';
          updateSawtoothSummary();
        });
      });
    });
  }

  // Collector track PE calibration rows (astCollPeCfg)
  const tpn = Math.max(0, Math.min(16, Number(s.track_pe_count) || 0));
  s.track_pe_count = tpn;
  while ((s.track_pes || []).length < tpn) s.track_pes.push(emptySawTrackPeRow());
  s.track_pes = (s.track_pes || []).slice(0, tpn);
  const peHost = $('saw-track-pe-rows');
  if (peHost) {
    if (!tpn) {
      peHost.innerHTML = '<div class="text-[10px] text-slate-600">No collector track PEs configured.</div>';
    } else {
      peHost.innerHTML = s.track_pes.map((row, i) => `
        <div class="rounded-lg border border-slate-800 bg-[#070b12] p-2 grid grid-cols-1 md:grid-cols-3 gap-2" data-saw-tpe="${i}">
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Track PE ${i + 1}</label>
            <select data-saw-tpe-field="pe" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Pulse location</label>
            <input data-saw-tpe-field="pls_location" type="number" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-slate-200" value="${Number(row.pls_location) || 0}">
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Blocked jam preset</label>
            <input data-saw-tpe-field="blocked_jam_pre" type="number" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-slate-200" value="${Number(row.blocked_jam_pre) || 60}">
          </div>
        </div>`).join('');
      peHost.querySelectorAll('[data-saw-tpe]').forEach((rowEl) => {
        const i = Number(rowEl.dataset.sawTpe);
        const row = s.track_pes[i] || emptySawTrackPeRow();
        rowEl.querySelectorAll('[data-saw-tpe-field]').forEach((el) => {
          const field = el.dataset.sawTpeField;
          if (field === 'pe') fillSawSelect(el, pes, row.pe || '');
          el.addEventListener('change', () => {
            s.track_pes[i] = { ...emptySawTrackPeRow(), ...(s.track_pes[i] || {}) };
            if (field === 'pe') s.track_pes[i].pe = el.value || '';
            else s.track_pes[i][field] = Number(el.value) || 0;
            updateSawtoothSummary();
          });
        });
      });
    }
  }
  updateSawtoothSummary();
}

function wireSawtoothBuildOnce() {
  if (wireSawtoothBuildOnce._done) return;
  wireSawtoothBuildOnce._done = true;

  const touchSaw = () => { try { markReadinessDirty('sawtooth'); } catch (_) { /* ignore */ } };
  $('saw-lane-count')?.addEventListener('change', () => {
    const n = Math.max(1, Math.min(12, parseInt($('saw-lane-count').value, 10) || 4));
    autogenState.sawtooth.lane_count = n;
    touchSaw();
    renderSawtoothBuild();
  });
  $('saw-track-pe-count')?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(16, parseInt($('saw-track-pe-count').value, 10) || 0));
    autogenState.sawtooth.track_pe_count = n;
    touchSaw();
    renderSawtoothBuild();
  });
  const bind = (id, fn) => $(id)?.addEventListener('change', () => { touchSaw(); fn(); });
  bind('saw-collector-conv', () => { autogenState.sawtooth.collector_conveyor = $('saw-collector-conv').value || ''; updateSawtoothSummary(); });
  bind('saw-downstream-conv', () => { autogenState.sawtooth.downstream_conveyor = $('saw-downstream-conv').value || ''; updateSawtoothSummary(); });
  bind('saw-collector-has-enc', () => {
    autogenState.sawtooth.collector_has_encoder = $('saw-collector-has-enc').value === 'no' ? 'no' : 'yes';
    if (autogenState.sawtooth.collector_has_encoder === 'no') {
      autogenState.sawtooth.collector_encoder = '';
    }
    renderSawtoothBuild();
  });
  bind('saw-collector-enc-type', () => {
    autogenState.sawtooth.collector_encoder_type = $('saw-collector-enc-type').value || 'Enc_RIOCard';
    updateSawtoothSummary();
  });
  bind('saw-collector-enc', () => {
    autogenState.sawtooth.collector_encoder = $('saw-collector-enc').value || '';
    reconcileSawtoothConfigurationRequired(autogenState.sawtooth);
    renderSawtoothBuild();
  });
  bind('saw-clctr-speed', () => { autogenState.sawtooth.clctr_speed_fpm = Number($('saw-clctr-speed').value) || 140; });
  bind('saw-clctr-runout', () => { autogenState.sawtooth.clctr_runout_dist = Number($('saw-clctr-runout').value) || 0; });
  bind('saw-slug-gap-adder', () => { autogenState.sawtooth.clctr_slug_gap_adder = Number($('saw-slug-gap-adder').value) || 0; });
  bind('saw-safety-tmr', () => { autogenState.sawtooth.clctr_safety_tmr_preset = Number($('saw-safety-tmr').value) || 0; });
  bind('saw-min-gap', () => { autogenState.sawtooth.clctr_min_gap = Number($('saw-min-gap').value) || 0; });
  bind('saw-slot-resv-mult', () => { autogenState.sawtooth.slot_reserve_multiple = Number($('saw-slot-resv-mult').value) || 1; });
  bind('saw-real-enc-ipp', () => { autogenState.sawtooth.real_enc_ipp = Number($('saw-real-enc-ipp').value) || 0; });
  bind('saw-pseudo-enc-ipp', () => { autogenState.sawtooth.pseudo_enc_ipp = Number($('saw-pseudo-enc-ipp').value) || 0; });
  bind('saw-pseudo-enc-max', () => { autogenState.sawtooth.pseudo_enc_max_cnt = Number($('saw-pseudo-enc-max').value) || 0; });
  bind('saw-trk-array-size', () => { autogenState.sawtooth.track_array_size = Number($('saw-trk-array-size').value) || 0; });
  bind('saw-lane-empty-opt', () => { autogenState.sawtooth.lane_empty_opt_preset = Number($('saw-lane-empty-opt').value) || 0; });
  bind('saw-use-gapstore', () => { autogenState.sawtooth.use_gapstore = !!$('saw-use-gapstore').checked; });
  bind('saw-coll-jam-pe', () => { autogenState.sawtooth.collector_jam_pe = $('saw-coll-jam-pe').value || ''; });
  bind('saw-coll-jam-pe-b', () => { autogenState.sawtooth.collector_jam_pe_b = $('saw-coll-jam-pe-b').value || ''; });
  bind('saw-coll-jam-pe-c', () => { autogenState.sawtooth.collector_jam_pe_c = $('saw-coll-jam-pe-c').value || ''; });
  bind('saw-coll-jam-pe-d', () => { autogenState.sawtooth.collector_jam_pe_d = $('saw-coll-jam-pe-d').value || ''; });
  bind('saw-eow-pe', () => { autogenState.sawtooth.eow_pe = $('saw-eow-pe').value || ''; });
  bind('saw-mrg-id', () => { autogenState.sawtooth.mrg_id = $('saw-mrg-id').value || '414'; updateSawtoothSummary(); });
  bind('saw-area-name', () => { autogenState.sawtooth.area_name = $('saw-area-name').value || ''; });
  bind('saw-enable-trk', () => {
    autogenState.sawtooth.enable_track = !!$('saw-enable-trk').checked;
    if (autogenState.sawtooth.enable_track && autogenState.sawtooth.collector_has_encoder === 'no') {
      autogenState.sawtooth.collector_has_encoder = 'yes';
      renderSawtoothBuild();
      return;
    }
    updateSawtoothSummary();
  });
  bind('saw-enable-resv', () => { autogenState.sawtooth.enable_reserve = !!$('saw-enable-resv').checked; });
  bind('saw-no-carton-check', () => { autogenState.sawtooth.no_carton_check = !!$('saw-no-carton-check').checked; });

  $('btn-saw-defaults-plc4')?.addEventListener('click', () => {
    // DEV ONLY — hardcoded Greensboro demo. Normal acceptance uses SiteModel auto-populate.
    if (!confirm('DEV ONLY: load hardcoded Greensboro PLC4 demo tags?\n\nNormal workflow: Import RUN → Sawtooth auto-populates from SiteModel.\nDo not use this for acceptance testing.')) {
      return;
    }
    const s = autogenState.sawtooth;
    s.collector_conveyor = 'P414';
    s.downstream_conveyor = 'P418';
    s.collector_has_encoder = 'yes';
    s.collector_encoder_type = 'Enc_RIOCard';
    s.collector_encoder = 'P414_Enc';
    s.clctr_speed_fpm = 140;
    s.clctr_runout_dist = 0;
    s.clctr_slug_gap_adder = 0;
    s.clctr_safety_tmr_preset = 0;
    s.mrg_id = '414';
    s.area_name = 'CP4_Sawtooth_Area';
    s.lane_count = 4;
    s.lanes = [
      { conveyor: 'P412', pe: 'PE410_P', jam_pe: '', merge_pe: '', has_encoder: 'no', encoder_type: 'Enc_RIOCard', encoder_tag: '' },
      { conveyor: 'P120', pe: 'PE118_P', jam_pe: '', merge_pe: '', has_encoder: 'no', encoder_type: 'Enc_RIOCard', encoder_tag: '' },
      { conveyor: 'P218', pe: 'PE216_P', jam_pe: '', merge_pe: '', has_encoder: 'no', encoder_type: 'Enc_RIOCard', encoder_tag: '' },
      { conveyor: 'P219', pe: 'PE219_P', jam_pe: 'PE219A_J', merge_pe: '', has_encoder: 'no', encoder_type: 'Enc_RIOCard', encoder_tag: '' },
    ];
    s.collector_jam_pe = 'PE414_J';
    s.collector_jam_pe_b = 'PE414A_J';
    s.collector_jam_pe_c = 'PE414B_J';
    s.collector_jam_pe_d = 'PE414C_J';
    s.eow_pe = '';
    s.track_pe_count = 0;
    s.track_pes = [];
    s.enable_track = true;
    s.enable_reserve = true;
    s.use_gapstore = false;
    s.discovery_source = 'dev_prefill_plc4';
    renderSawtoothBuild();
    const st = $('saw-save-status');
    if (st) { st.textContent = 'DEV demo filled — NOT for acceptance'; st.className = 'text-[10px] text-amber-400 mono'; }
    autogenLog('DEV Prefill PLC4 demo used — acceptance requires SiteModel auto-populate from Import RUN.', 'warn');
  });

  $('btn-saw-save')?.addEventListener('click', async () => {
    reconcileSawtoothConfigurationRequired(autogenState.sawtooth || {});
    persistSawtoothToWorkbook();
    const s = autogenState.sawtooth || {};
    const hasData = !!(s.collector_conveyor || (s.lanes || []).some((l) => l && l.conveyor));
    const unresolved = (s.configuration_required || []).length;
    if (hasData && $('autogen-opt-sawtooth')) $('autogen-opt-sawtooth').checked = true;
    try {
      if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
        await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
      }
      try { localStorage.setItem('fortna_sawtooth_build', JSON.stringify(autogenState.sawtooth)); } catch (_) { /* ignore */ }
      const st = $('saw-save-status');
      if (hasData && unresolved === 0) {
        setReadinessApplied(
          'sawtooth',
          `Collector ${s.collector_conveyor || '—'} · ${(s.lanes || []).filter((l) => l && l.conveyor).length} lane(s)`,
        );
        if (st) { st.textContent = 'Applied · READY FOR AUTOGEN'; st.className = 'text-[10px] text-emerald-500 mono'; }
        autogenLog('Sawtooth Apply → Compile hub READY (Sawtooth_Merge included on Export).', 'ok');
      } else if (hasData) {
        const e = ensureAutogenReadiness().sawtooth;
        e.dirty = false;
        e.appliedAt = null;
        e.status = 'REVIEW_REQUIRED';
        e.unresolved = unresolved;
        e.detail = `${unresolved} unresolved — review before Export`;
        refreshAutogenCompileHub();
        if (st) { st.textContent = 'Applied · REVIEW REQUIRED'; st.className = 'text-[10px] text-amber-400 mono'; }
        autogenLog(`Sawtooth Apply stored with ${unresolved} unresolved field(s).`, 'warn');
      } else {
        if (st) { st.textContent = 'Nothing to apply'; st.className = 'text-[10px] text-slate-500 mono'; }
      }
      updateSawtoothSummary();
    } catch (e) {
      const st = $('saw-save-status');
      if (st) { st.textContent = 'Apply failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Sawtooth Apply failed: ${e?.message || e}`, 'err');
    }
  });

  $('btn-saw-reload-sitemodel')?.addEventListener('click', async () => {
    try {
      await applySiteModelToEditors({ reason: 'sawtooth-reload' });
      const st = $('saw-save-status');
      if (st) st.textContent = 'Reloaded from SiteModel';
    } catch (e) {
      autogenLog(`Sawtooth reload failed: ${e?.message || e}`, 'err');
    }
  });
  $('btn-saw-clear')?.addEventListener('click', () => {
    autogenState.sawtooth = defaultSawtoothConfig();
    persistSawtoothToWorkbook();
    Object.assign(ensureAutogenReadiness().sawtooth, emptyReadinessEntry());
    renderSawtoothBuild();
    const st = $('saw-save-status');
    if (st) { st.textContent = 'Cleared'; st.className = 'text-[10px] text-slate-500 mono'; }
    refreshAutogenCompileHub();
  });

  try {
    const raw = localStorage.getItem('fortna_sawtooth_build');
    if (raw && !autogenState.workbook?.sawtooth_build) {
      autogenState.sawtooth = normalizeSawtoothConfig({ ...defaultSawtoothConfig(), ...JSON.parse(raw) });
    }
  } catch (_) { /* ignore */ }
  if (autogenState.workbook?.sawtooth_build) {
    autogenState.sawtooth = normalizeSawtoothConfig({
      ...defaultSawtoothConfig(),
      ...autogenState.workbook.sawtooth_build,
    });
  }
  renderSawtoothBuild();
}

// Boot sawtooth wiring after DOM ready (same pattern as sorter)
setTimeout(() => { try { wireSawtoothBuildOnce(); } catch (_) { /* ignore */ } }, 0);

function autogenLog(msg, level = 'info') {
  const el = $('autogen-log');
  if (!el) return;
  const colors = { info: 'text-slate-400', ok: 'text-emerald-400', err: 'text-red-400', warn: 'text-amber-400' };
  const line = document.createElement('div');
  line.className = colors[level] || colors.info;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.prepend(line);
}

function setAutogenStatus(text, kind) {
  const el = $('autogen-status');
  if (!el) return;
  el.textContent = text;
  el.className = `status-pill status-${kind || 'idle'}`;
}

function setWorkbook(wb) {
  autogenState.workbook = wb || null;
  autogenState.selected = new Set();
  loadSorterFromWorkbook();
  renderWorkbook();
  renderCatalogChips();
  renderSorterBuild();
}

/** Ensure workbook.options catalogs exist for dropdown customization. */
function ensureWorkbookOptions() {
  const wb = autogenState.workbook;
  if (!wb) return null;
  if (!wb.options || typeof wb.options !== 'object') wb.options = {};
  if (!Array.isArray(wb.options.areas)) wb.options.areas = [];
  if (!Array.isArray(wb.options.safety_zones)) wb.options.safety_zones = [];
  if (!Array.isArray(wb.options.exit_pe)) wb.options.exit_pe = [];
  if (!Array.isArray(wb.options.types)) {
    wb.options.types = Array.isArray(wb.autogen_types) ? [...wb.autogen_types] : [];
  }
  return wb.options;
}

function addCatalogValue(kind, raw) {
  const val = String(raw || '').trim();
  if (!val) {
    autogenLog('Enter a value to add', 'warn');
    return;
  }
  if (!autogenState.workbook) {
    autogenLog('Build site config from RUN first', 'warn');
    return;
  }
  const opts = ensureWorkbookOptions();
  const keyMap = {
    area: 'areas',
    safety: 'safety_zones',
    exitpe: 'exit_pe',
    type: 'types',
  };
  const key = keyMap[kind];
  if (!key) return;
  const list = opts[key];
  if (list.some((x) => String(x).toLowerCase() === val.toLowerCase())) {
    autogenLog(`Already in list: ${val}`, 'info');
    return;
  }
  list.push(val);
  if (kind === 'type' && Array.isArray(autogenState.workbook.autogen_types)
    && !autogenState.workbook.autogen_types.includes(val)) {
    autogenState.workbook.autogen_types.push(val);
  }
  // Also refresh bulk TYPE select if needed
  if (kind === 'type') {
    const sel = $('autogen-wb-bulk-type');
    if (sel && ![...sel.options].some((o) => o.value === val)) {
      const opt = document.createElement('option');
      opt.value = val;
      opt.textContent = val;
      sel.appendChild(opt);
    }
  }
  renderWorkbook();
  renderCatalogChips();
  autogenLog(`Added ${kind}: ${val}`, 'ok');
  // Persist quietly
  if (typeof fortnaAPI.autogenWorkbookSave === 'function') {
    fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook }).catch(() => {});
  }
}

function renderCatalogChips() {
  const el = $('autogen-catalog-chips');
  if (!el) return;
  const opts = autogenState.workbook?.options;
  if (!opts) {
    el.innerHTML = '<span class="text-slate-600">Load site config to customize catalogs.</span>';
    return;
  }
  const chip = (label, n) =>
    `<span class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-400">${label} <strong class="text-violet-300">${n}</strong></span>`;
  el.innerHTML = [
    chip('areas', (opts.areas || []).length),
    chip('safety', (opts.safety_zones || []).length),
    chip('exit PE', (opts.exit_pe || []).length),
    chip('types', (opts.types || []).length),
  ].join(' ');
}

/**
 * Ensure site-config table (dropdowns) is filled from the active RUN.
 * Called after tar.gz load and when opening the PLC Autogen tab.
 */
async function ensureAutogenWorkbookFromRun({ force = false, reason = '' } = {}) {
  if (typeof fortnaAPI.autogenWorkbookBuild !== 'function') return false;
  if (autogenState.busy) return false;
  if (autogenState.workbook && !force) return true;
  // Only build when a RUN is actually loaded
  let runLoaded = false;
  try {
    if (typeof fortnaAPI.autogenDefaults === 'function') {
      const d = await fortnaAPI.autogenDefaults();
      runLoaded = !!(d?.success && d.runLoaded);
    }
  } catch (_) { /* ignore */ }
  if (!runLoaded && !state.workspace) return false;
  if (reason) autogenLog(`Site config: scanning RUN (${reason})…`, 'info');
  // Fresh RUN import must not merge a previous machine's workbook (CP2 rows leaking into CP4).
  await buildAutogenWorkbook({ mergeExisting: !force });
  return !!autogenState.workbook;
}

function renderWorkbook() {
  const wb = autogenState.workbook;
  const tbody = $('autogen-wb-tbody');
  const ioBody = $('autogen-wb-io-tbody');
  const countEl = $('autogen-wb-count');
  const typeBar = $('autogen-wb-type-bar');
  const areasEl = $('autogen-wb-areas');
  const rows = wb?.conveyors || [];
  if (!wb || !rows.length) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-6 px-3 text-slate-500 text-center">'
        + 'No site config yet.<br><span class="text-slate-400">Load a .tar.gz on I/O &amp; Prints</span> — '
        + 'conveyors appear here with Area / Safety / TYPE / Exit PE dropdowns.</td></tr>';
    }
    if (ioBody) {
      ioBody.innerHTML = '<tr><td colspan="6" class="py-4 px-2 text-slate-500">IO map fills with workbook build.</td></tr>';
    }
    if (countEl) countEl.textContent = '0 rows';
    if (typeBar) { typeBar.classList.add('hidden'); typeBar.innerHTML = ''; }
    if (areasEl) areasEl.textContent = '—';
    if ($('autogen-detail')) $('autogen-detail').textContent = '—';
    try { refreshAutogenBuildTracker(); } catch (_) { /* ignore */ }
    return;
  }
  const opts = wb.options || {};
  const types = opts.types || wb.autogen_types || [
    'Transport with MS', 'Accumulation with MS', 'Transport with VFD', 'Accumulation with VFD',
  ];
  // Ensure current values appear in option lists even if custom
  const areaOpts = [...(opts.areas || [])];
  const safetyOpts = [...(opts.safety_zones || [])];
  const peOptsGlobal = [...(opts.exit_pe || [])];
  for (const r of rows) {
    if (r.main_area && !areaOpts.includes(r.main_area)) areaOpts.push(r.main_area);
    if (r.safety_zone && !safetyOpts.includes(r.safety_zone)) safetyOpts.push(r.safety_zone);
  }

  // Keep bulk area control as a dropdown of all areas
  const bulkArea = $('autogen-wb-bulk-area');
  if (bulkArea && bulkArea.tagName === 'SELECT') {
    const cur = bulkArea.value;
    bulkArea.innerHTML = '<option value="">Bulk area…</option>'
      + areaOpts.map((a) => `<option value="${escapeHtml(a)}" ${a === cur ? 'selected' : ''}>${escapeHtml(a)}</option>`).join('');
  }

  if (countEl) {
    const on = rows.filter((r) => r.include !== false).length;
    countEl.textContent = `${on}/${rows.length} on · ${wb.stats?.io_mapped ?? '—'} IO mapped`;
  }
  if (typeBar) {
    typeBar.classList.remove('hidden');
    const tc = wb.type_counts || {};
    typeBar.innerHTML = Object.entries(tc).map(([t, n]) =>
      `<span class="text-[9px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-700 text-slate-400">${escapeHtml(t)} <strong class="text-violet-300">${n}</strong></span>`
    ).join('') || '';
  }
  if (areasEl) {
    const areas = wb.areas || [];
    areasEl.innerHTML = areas.length
      ? areas.map((a) =>
        `<div class="flex gap-3 mono"><span class="text-cyan-400">${escapeHtml(a.name)}</span>`
        + `<span class="text-slate-500">${escapeHtml(a.safety_zone || '')}</span>`
        + `<span class="text-slate-600">${a.conveyor_count || 0} conv</span></div>`
      ).join('')
      : 'No areas';
  }

  function selOpts(list, selected, { emptyLabel = '— none —', allowEmpty = true } = {}) {
    const items = [];
    if (allowEmpty) {
      items.push(`<option value="" ${!selected ? 'selected' : ''}>${escapeHtml(emptyLabel)}</option>`);
    }
    const seen = new Set();
    for (const v of list || []) {
      if (v == null || v === '') continue;
      const s = String(v);
      if (seen.has(s)) continue;
      seen.add(s);
      items.push(`<option value="${escapeHtml(s)}" ${s === selected ? 'selected' : ''}>${escapeHtml(s)}</option>`);
    }
    // Current value missing from list (custom) — still show it
    if (selected && !seen.has(selected)) {
      items.push(`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} *</option>`);
    }
    return items.join('');
  }

  if (tbody) {
    tbody.innerHTML = rows.map((r, idx) => {
      const name = r.conveyor || '';
      const sel = autogenState.selected.has(name.toUpperCase()) ? 'checked' : '';
      // Exit PE: row-linked PEs first, then full site list
      const peChoices = (r.exit_pe_choices && r.exit_pe_choices.length)
        ? r.exit_pe_choices
        : peOptsGlobal;
      return `<tr class="border-b border-slate-800/70 hover:bg-[#101820]" data-wb-idx="${idx}">
        <td class="py-1 px-1"><input type="checkbox" class="wb-sel" data-name="${escapeHtml(name)}" ${sel}></td>
        <td class="py-1 px-1"><input type="checkbox" class="wb-include" data-idx="${idx}" ${r.include !== false ? 'checked' : ''}></td>
        <td class="py-1 px-1 text-slate-100 whitespace-nowrap font-semibold">${escapeHtml(name)}</td>
        <td class="py-1 px-1"><select class="wb-area bg-[#101820] border border-slate-700 rounded px-1 text-[10px] max-w-[8.5rem]" data-idx="${idx}">${selOpts(areaOpts, r.main_area || '', { allowEmpty: false, emptyLabel: '' })}</select></td>
        <td class="py-1 px-1"><select class="wb-safe bg-[#101820] border border-slate-700 rounded px-1 text-[10px] max-w-[8.5rem]" data-idx="${idx}">${selOpts(safetyOpts, r.safety_zone || '', { allowEmpty: false, emptyLabel: '' })}</select></td>
        <td class="py-1 px-1"><select class="wb-type bg-[#101820] border border-slate-700 rounded px-1 text-[10px] max-w-[10rem]" data-idx="${idx}">${selOpts(types, r.type || '', { allowEmpty: false })}</select></td>
        <td class="py-1 px-1 text-slate-500 text-[9px]">${escapeHtml(r.template || '')}</td>
        <td class="py-1 px-1"><select class="wb-exitpe bg-[#101820] border border-slate-700 rounded px-1 text-[10px] max-w-[9rem] text-sky-300" data-idx="${idx}">${selOpts(peChoices, r.exit_pe_tag || '', { emptyLabel: '— none —', allowEmpty: true })}</select></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.wb-sel').forEach((cb) => {
      cb.addEventListener('change', () => {
        const n = (cb.dataset.name || '').toUpperCase();
        if (cb.checked) autogenState.selected.add(n);
        else autogenState.selected.delete(n);
      });
    });
    tbody.querySelectorAll('.wb-include').forEach((cb) => {
      cb.addEventListener('change', () => {
        const i = parseInt(cb.dataset.idx, 10);
        if (wb.conveyors[i]) {
          wb.conveyors[i].include = !!cb.checked;
          wb.conveyors[i].edited = true;
        }
      });
    });
    tbody.querySelectorAll('.wb-area').forEach((sel) => {
      sel.addEventListener('change', () => {
        const i = parseInt(sel.dataset.idx, 10);
        if (!wb.conveyors[i]) return;
        wb.conveyors[i].main_area = sel.value;
        wb.conveyors[i].edited = true;
        // Suggest safety zone from area stem — but never promote Zone1..Zone9 /
        // pure-numeric UI placeholders into production options.safety_zones (Gate R).
        const areaVal = sel.value || '';
        const base = areaVal.replace(/_Area$/i, '');
        const placeholderArea = /^Zone[1-9]_Area$/i.test(areaVal) || /^\d{2,}$/.test(base);
        if (base && !placeholderArea) {
          const sz = `${base}_ESZone1`;
          wb.conveyors[i].safety_zone = sz;
          if (!safetyOpts.includes(sz)) safetyOpts.push(sz);
          if (wb.options) {
            wb.options.safety_zones = safetyOpts;
            if (!wb.options.areas.includes(areaVal)) wb.options.areas.push(areaVal);
          }
        } else if (base && placeholderArea) {
          // Engineer explicitly chose a ZoneN / numeric area — keep conveyor
          // assignment local; do not mint a production Safety zone catalog entry.
          wb.conveyors[i].safety_zone = `${base}_ESZone1`;
        }
        // refresh type counts only if needed — re-render for safety dropdown update
        renderWorkbook();
      });
    });
    tbody.querySelectorAll('.wb-safe').forEach((sel) => {
      sel.addEventListener('change', () => {
        const i = parseInt(sel.dataset.idx, 10);
        if (wb.conveyors[i]) {
          wb.conveyors[i].safety_zone = sel.value;
          wb.conveyors[i].edited = true;
        }
      });
    });
    tbody.querySelectorAll('.wb-type').forEach((sel) => {
      sel.addEventListener('change', () => {
        const i = parseInt(sel.dataset.idx, 10);
        if (wb.conveyors[i]) {
          wb.conveyors[i].type = sel.value;
          wb.conveyors[i].edited = true;
          const map = {
            'transport with ms': 'P3000_Conv',
            'accumulation with ms': 'P4000_Conv',
            'transport with vfd': 'P1000_Conv',
            'accumulation with vfd': 'P2000_Conv',
            'transport with mdr': 'P4000_Conv',
            'accumulation with mdr': 'P3000_Conv',
            gravity: 'P3000_Conv',
          };
          wb.conveyors[i].template = map[(sel.value || '').toLowerCase()] || 'P3000_Conv';
          wb.conveyors[i].drive = /vfd/i.test(sel.value) ? 'VFD' : 'MS';
          // refresh type chip bar
          const tc = {};
          for (const row of wb.conveyors || []) {
            if (row.include === false) continue;
            tc[row.type] = (tc[row.type] || 0) + 1;
          }
          wb.type_counts = tc;
          renderWorkbook();
        }
      });
    });
    tbody.querySelectorAll('.wb-exitpe').forEach((sel) => {
      sel.addEventListener('change', () => {
        const i = parseInt(sel.dataset.idx, 10);
        if (wb.conveyors[i]) {
          wb.conveyors[i].exit_pe_tag = sel.value || '';
          wb.conveyors[i].edited = true;
        }
      });
    });
  }
  if (ioBody) {
    const pts = wb.io_points || [];
    const show = pts.slice(0, 300);
    ioBody.innerHTML = show.length
      ? show.map((p) => `
        <tr class="border-b border-slate-800/60">
          <td class="py-1 px-2 text-slate-200">${escapeHtml(p.name || '')}</td>
          <td class="py-1 px-2 text-slate-500">${escapeHtml(p.device_type || '')}</td>
          <td class="py-1 px-2">${escapeHtml(p.direction || '')}</td>
          <td class="py-1 px-2">${escapeHtml(`Bank${p.fortna_bank || '?'}.${p.fortna_bit || '?'}`)}</td>
          <td class="py-1 px-2 text-amber-400/90">${escapeHtml(p.module_ref || '—')}</td>
          <td class="py-1 px-2 ${p.mapped ? 'text-emerald-400' : 'text-red-400'}">${p.mapped ? 'Y' : 'N'}</td>
        </tr>`).join('')
        + (pts.length > 300 ? `<tr><td colspan="6" class="py-2 px-2 text-slate-600">… ${pts.length - 300} more (saved in workbook JSON)</td></tr>` : '')
      : '<tr><td colspan="6" class="py-4 px-2 text-slate-500">No IO points</td></tr>';
  }
  if ($('autogen-summary') && wb.stats) {
    const s = wb.stats;
    $('autogen-summary').innerHTML =
      `<span class="text-emerald-400/90 font-medium">${escapeHtml(wb.project_name || '')}</span>`
      + ` · ${s.conveyor_included ?? s.conveyor_count} conv · ${s.area_count} areas · `
      + `IO ${s.io_mapped}/${s.io_point_count} mapped · `
      + `<span class="text-slate-500">${escapeHtml(wb.human_notes || '')}</span>`;
  }
  if ($('autogen-stats') && wb.stats) {
    const s = wb.stats;
    $('autogen-stats').classList.remove('hidden');
    $('autogen-stats').innerHTML = [
      ['Conveyors', s.conveyor_included ?? s.conveyor_count],
      ['Areas', s.area_count],
      ['IO mapped', `${s.io_mapped}/${s.io_point_count}`],
      ['Modules', s.module_count],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-violet-300 mono">${v}</div>
      </div>`).join('');
  }
  try { refreshAutogenBuildTracker(); } catch (_) { /* ignore */ }
}

function switchWbTab(tab) {
  autogenState.wbTab = tab || 'io';
  document.querySelectorAll('.wb-tab').forEach((btn) => {
    const on = btn.dataset.wbTab === autogenState.wbTab;
    btn.className = on
      ? 'wb-tab text-[10px] px-2.5 py-1.5 rounded-t-lg bg-violet-950/50 text-violet-300 border border-b-0 border-violet-800/40'
      : 'wb-tab text-[10px] px-2.5 py-1.5 rounded-t-lg text-slate-500 hover:text-slate-300';
  });
  ['conveyors', 'io', 'areas', 'report'].forEach((id) => {
    const el = $(`autogen-wb-panel-${id}`);
    if (el) el.classList.toggle('hidden', id !== autogenState.wbTab);
  });
}

async function buildAutogenWorkbook({ mergeExisting = true } = {}) {
  if (typeof fortnaAPI.autogenWorkbookBuild !== 'function') {
    autogenLog('Workbook API missing — relaunch Site Forge desktop app', 'warn');
    return;
  }
  if (autogenState.busy) return;
  autogenState.busy = true;
  setAutogenStatus('Building workbook…', 'busy');
  autogenLog(
    mergeExisting
      ? 'Building AutoGen workbook from active RUN (merge engineer edits)…'
      : 'Building AutoGen workbook from active RUN (fresh — no prior-machine merge)…',
    'info',
  );
  let res;
  try {
    res = await fortnaAPI.autogenWorkbookBuild({ mergeExisting: !!mergeExisting });
  } catch (e) {
    res = { success: false, message: e?.message || String(e) };
  }
  autogenState.busy = false;
  if (!res?.success) {
    setAutogenStatus('Error', 'error');
    autogenLog(res?.message || 'Workbook build failed', 'err');
    return;
  }
  const r = res.result || {};
  // Prefer full workbook shape (options = dropdown catalogs for Area/Safety/TYPE/Exit PE)
  const wb = {
    project_name: r.project_name,
    stats: r.stats,
    type_counts: r.type_counts,
    areas: r.areas,
    autogen_types: r.autogen_types,
    options: r.options || {
      types: r.autogen_types || [],
      areas: (r.areas || []).map((a) => a.name || a).filter(Boolean),
      safety_zones: [],
      exit_pe: [],
    },
    conveyors: r.conveyors || [],
    io_points: r.io_points || [],
    modules: r.modules || [],
    human_notes: r.human_notes,
    automation: r.automation,
    path: r.path || r.full_path,
  };
  // Reload full from disk if available
  if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
    try {
      const full = await fortnaAPI.autogenWorkbookLoad();
      if (full?.success && full.workbook) {
        setWorkbook(full.workbook);
      } else {
        setWorkbook(wb);
      }
    } catch (_) {
      setWorkbook(wb);
    }
  } else {
    setWorkbook(wb);
  }
  setAutogenStatus('Site config ready', 'ready');
  autogenState.lastGenerateIoMapError = null;
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  const s = r.stats || {};
  autogenLog(
    `Site config ready — ${s.conveyor_count || 0} conveyors, ${s.io_mapped || 0}/${s.io_point_count || 0} IO mapped, `
    + `${s.area_count || 0} areas. Apply Transport / Sawtooth / Sorter tabs → Export L5X Package.`,
    'ok',
  );
  if ($('autogen-detail') && r.automation) {
    $('autogen-detail').textContent = JSON.stringify({
      stats: s,
      type_counts: r.type_counts,
      automation: r.automation,
      path: r.path,
    }, null, 2);
  }
  switchWbTab('io');
}

async function saveAutogenWorkbook() {
  if (!autogenState.workbook) {
    autogenLog('Nothing to save — build workbook first', 'warn');
    return;
  }
  if (typeof fortnaAPI.autogenWorkbookSave !== 'function') {
    autogenLog('Save API missing — relaunch app', 'warn');
    return;
  }
  persistSorterToWorkbook();
  const res = await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
  if (!res?.success) {
    autogenLog(res?.message || 'Save failed', 'err');
    return;
  }
  autogenLog(`Workbook saved: ${res.path || 'workspace/autogen_workbook.json'}`, 'ok');
}

function selectedConveyorNames() {
  return [...autogenState.selected];
}

function bulkApplyType() {
  const wb = autogenState.workbook;
  const t = $('autogen-wb-bulk-type')?.value;
  if (!wb || !t) {
    autogenLog('Pick a bulk TYPE first', 'warn');
    return;
  }
  const names = selectedConveyorNames();
  if (!names.length) {
    autogenLog('Select conveyor rows (checkboxes) first', 'warn');
    return;
  }
  const map = {
    'transport with ms': 'P3000_Conv',
    'accumulation with ms': 'P4000_Conv',
    'transport with vfd': 'P1000_Conv',
    'accumulation with vfd': 'P2000_Conv',
  };
  let n = 0;
  for (const row of wb.conveyors || []) {
    if (names.includes((row.conveyor || '').toUpperCase())) {
      row.type = t;
      row.template = map[t.toLowerCase()] || 'P3000_Conv';
      row.drive = /vfd/i.test(t) ? 'VFD' : 'MS';
      row.edited = true;
      n += 1;
    }
  }
  // refresh type_counts
  const tc = {};
  for (const r of wb.conveyors || []) {
    if (r.include === false) continue;
    tc[r.type] = (tc[r.type] || 0) + 1;
  }
  wb.type_counts = tc;
  renderWorkbook();
  autogenLog(`Set TYPE “${t}” on ${n} conveyor(s)`, 'ok');
}

function bulkApplyArea() {
  const wb = autogenState.workbook;
  const area = ($('autogen-wb-bulk-area')?.value || '').trim();
  if (!wb || !area) {
    autogenLog('Pick a bulk area from the dropdown first', 'warn');
    return;
  }
  const names = selectedConveyorNames();
  if (!names.length) {
    autogenLog('Select conveyor rows first', 'warn');
    return;
  }
  const base = area.replace(/_Area$/i, '');
  const sz = `${base}_ESZone1`;
  const placeholderArea = /^Zone[1-9]_Area$/i.test(area) || /^\d{2,}$/.test(base);
  let n = 0;
  for (const row of wb.conveyors || []) {
    if (names.includes((row.conveyor || '').toUpperCase())) {
      row.main_area = area;
      row.safety_zone = sz;
      row.edited = true;
      n += 1;
    }
  }
  if (wb.options) {
    if (!wb.options.areas.includes(area)) wb.options.areas.push(area);
    // Gate R — do not promote Zone1..Zone9 / numeric test shells into catalog
    if (!placeholderArea && !wb.options.safety_zones.includes(sz)) {
      wb.options.safety_zones.push(sz);
    }
  }
  renderWorkbook();
  autogenLog(`Set area “${area}” on ${n} conveyor(s)`, 'ok');
}

// Resolve default library path on load (absolute — relative tools/… fails from Electron cwd)
async function initAutogenDefaults() {
  if (typeof fortnaAPI.autogenDefaults !== 'function') return;
  try {
    const d = await fortnaAPI.autogenDefaults();
    if (d.success && d.library) {
      autogenState.library = d.library;
      if ($('autogen-library-path')) $('autogen-library-path').value = d.library;
      const badge = $('autogen-run-badge');
      if (badge) {
        if (d.runLoaded) {
          badge.textContent = d.machine ? `RUN: ${d.machine}` : 'RUN loaded';
          badge.className = 'status-pill status-ready text-[9px]';
        } else {
          badge.textContent = 'No RUN';
          badge.className = 'status-pill status-idle text-[9px]';
        }
      }
      if (!d.libraryExists) {
        autogenLog('Default library missing — Browse to OReilly_Library_v3.L5X', 'warn');
      } else {
        autogenLog(`Python engine ready · library: ${d.library.split(/[/\\]/).pop()}`, 'ok');
      }
      if (d.runLoaded) {
        autogenLog(
          `Active RUN detected${d.machine ? ` (${d.machine})` : ''}`
          + (d.deviceCount ? ` · ${d.deviceCount} devices` : '')
          + ' — site config dropdowns load automatically',
          'info',
        );
        // Fill site config if empty so engineer sees dropdowns immediately
        ensureAutogenWorkbookFromRun({ reason: 'RUN already active' }).catch(() => {});
      } else {
        autogenLog('No RUN loaded — I/O & Prints → drop/load .tar.gz first', 'info');
      }
    }
  } catch (e) {
    autogenLog(e.message || 'Autogen defaults failed', 'warn');
  }
}

// Progress from Python during Generate (FORTNA_PROGRESS on stderr)
if (typeof fortnaAPI.onAutogenProgress === 'function') {
  fortnaAPI.onAutogenProgress((p) => {
    if (!p || !p.message) return;
    const pct = p.pct != null ? ` (${p.pct}%)` : '';
    autogenLog(`${p.message}${pct}`, 'info');
    if (p.pct != null) setAutogenStatus(`Generating… ${p.pct}%`, 'busy');
  });
}

$('btn-autogen-browse-excel')?.addEventListener('click', async () => {
  const res = await fortnaAPI.autogenSelectExcel();
  if (res.success && res.path) {
    autogenState.excel = res.path;
    if ($('autogen-excel-path')) $('autogen-excel-path').value = res.path;
    autogenLog(`Excel (legacy): ${res.path.split(/[/\\]/).pop()}`, 'ok');
  }
});

$('btn-autogen-browse-lib')?.addEventListener('click', async () => {
  const res = await fortnaAPI.autogenSelectLibrary();
  if (res.success && res.path) {
    autogenState.library = res.path;
    if ($('autogen-library-path')) $('autogen-library-path').value = res.path;
    autogenLog(`Library: ${res.path.split(/[/\\]/).pop()}`, 'ok');
  }
});

$('btn-autogen-inspect')?.addEventListener('click', async () => {
  const excel = autogenState.excel || $('autogen-excel-path')?.value;
  if (!excel) {
    autogenLog('Browse for an Excel workbook first.', 'warn');
    return;
  }
  setAutogenStatus('Inspecting…', 'busy');
  const res = await fortnaAPI.autogenInspectExcel({ excel });
  if (!res.success) {
    setAutogenStatus('Error', 'error');
    autogenLog(res.message || 'Inspect failed', 'err');
    return;
  }
  setAutogenStatus('Inspected', 'ready');
  const r = res.result || {};
  if ($('autogen-summary')) {
    $('autogen-summary').innerHTML = `
      <div class="space-y-1 text-xs">
        <div><span class="text-violet-300 font-semibold">${escapeHtml(r.project_name || '—')}</span>
          · ${escapeHtml(r.processor || '')} · v${escapeHtml(String(r.version || ''))}</div>
        <div>${r.conveyor_rows || 0} conveyor rows · sheets: ${(r.sheets || []).join(', ')}</div>
      </div>`;
  }
  if ($('autogen-detail')) {
    $('autogen-detail').textContent = JSON.stringify(r, null, 2);
  }
  autogenLog(`Inspect OK — ${r.conveyor_rows || 0} conveyors in Inputdata`, 'ok');
});

async function runAutogenGenerate(mode) {
  if (autogenState.busy) return;
  // Prefer absolute library from defaults; ignore broken relative tools/… path in the text box
  let library = autogenState.library || '';
  const boxLib = ($('autogen-library-path')?.value || '').trim();
  if (boxLib && (boxLib.includes(':\\') || boxLib.startsWith('/'))) {
    library = boxLib;
  }
  const excel = autogenState.excel || $('autogen-excel-path')?.value;
  if (mode === 'excel' && !excel) {
    autogenLog('For Excel path: Browse workbook first. Preferred: Generate PLC Project after loading tar.gz.', 'warn');
    return;
  }
  if (mode === 'run' && !autogenState.workbook) {
    autogenLog('No site config yet — scanning RUN for conveyors / zones…', 'info');
    await buildAutogenWorkbook();
    if (!autogenState.workbook) {
      autogenLog('Load tar.gz on I/O & Prints first — site config table needs an active RUN', 'warn');
      return;
    }
  }

  // Preflight: ERROR on INCLUDED/mandatory packs stops Export.
  // REVIEW REQUIRED (unassigned FOUND equipment / incomplete Safety) does NOT.
  // PARTIAL BUILD: FOUND≠INCLUDED≠GENERATED — proceed with effective included model.
  autogenState.omitUnresolvedSafety = false;
  if (mode === 'run') {
    try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    let pre = autogenBuildPreflight();
    if (!pre.ok) {
      setAutogenStatus('Blocked — readiness ERROR', 'error');
      autogenLog('Export blocked — fatal ERROR on included/mandatory content:', 'err');
      (pre.blockers || []).forEach((b) => autogenLog(`  • ${b.message}`, 'err'));
      const first = pre.blockers[0];
      if (first?.tab) {
        try { activateTab(first.tab); } catch (_) { /* ignore */ }
      }
      return;
    }
    // Soft reviews — Build ALLOWED; commissioning incomplete items stay conspicuous
    const softs = pre.softReviews || pre.softSafetyReview || [];
    if (softs.length) {
      autogenLog(
        'PARTIAL BUILD ALLOWED — REVIEW REQUIRED items do not block Export',
        'warn',
      );
      softs.forEach((b) => autogenLog(`  • ${b.message}`, 'warn'));
    }
    if ((pre.softSafetyReview || []).length) {
      autogenLog('SAFETY REVIEW REQUIRED — fail-safe shell / partial zones; UNASSIGNED ≠ SAFE', 'warn');
      const ev = safetyEvidence();
      autogenLog(
        `Safety lifecycle — Found ${ev.foundDevices || 0} · Configured ${ev.configuredDevices || 0}`
        + ` · Included ${ev.includedDevices || 0} · Unassigned ${ev.unassigned || 0}`
        + ` · Generated ${ev.generatedDevices || 0} · COMMISSIONING READY = ${ev.commissioningReady ? 'YES' : 'NO'}`,
        'warn',
      );
      (ev.diagnostics || []).forEach((d) => {
        String(d).split('\n').forEach((line) => autogenLog(`    ${line}`, 'warn'));
      });
      const un = ev.unassignedDevices || [];
      if (un.length) {
        autogenLog(
          `Unassigned Safety devices (${un.length}): ${un.slice(0, 12).join(', ')}${un.length > 12 ? ', …' : ''}`,
          'warn',
        );
      }
    }
  }

  autogenState.busy = true;
  setAutogenStatus('Generating PLC project…', 'busy');
  if ($('btn-autogen-generate')) $('btn-autogen-generate').disabled = true;
  if ($('btn-autogen-from-run')) $('btn-autogen-from-run').disabled = true;
  if ($('btn-autogen-workbook-build')) $('btn-autogen-workbook-build').disabled = true;
  autogenLog(
    mode === 'run'
      ? 'Exporting L5X package (files only — Studio will not open)…'
      : 'Legacy Excel path: exporting L5X files…',
    'info',
  );

  // Mandatory core packs — always on (Advanced checkboxes are display-only)
  const includePrograms = [];
  const noSys = false;
  const includeIoMap = true;
  includePrograms.push('Devices_Comm', 'NTP', 'System_Logic', 'System');

  const R = ensureAutogenReadiness();
  const ship = shippingSorterEvidence();
  const wcsOn = wcsEvidence() || !!$('autogen-opt-wcs')?.checked;
  // ShippingSorter / WCS only when SiteModel proves support (or Advanced override)
  if (ship.shoe || !!$('autogen-opt-shippingsorter')?.checked) {
    includePrograms.push('ShippingSorter_Area_L3');
  }
  if (ship.popup || !!$('autogen-opt-shippingsorter-popup')?.checked) {
    includePrograms.push('ShippingSorter_PopUp_Divert');
    autogenLog('ShippingSorter (PopUp Divert) — pack mapping TBD (no L5X merge yet).', 'warn');
  }
  if (wcsOn) includePrograms.push('WCS_Interface_TCP_IP');

  // Evidence-driven: Sawtooth READY → Sawtooth_Merge
  const sawReady = R.sawtooth?.status === 'READY' || !!$('autogen-opt-sawtooth')?.checked;
  if (sawReady && sawtoothEvidence().detected) includePrograms.push('Sawtooth_Merge');

  // Merges via workbook when present (Transport Apply already persisted)
  const mergeRows = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const merge2 = mergeRows.filter((m) => (Number(m.lanes) || 2) <= 2);
  const merge3 = mergeRows.filter((m) => (Number(m.lanes) || 2) >= 3);
  const mergeOn = mergeRows.length > 0 || !!$('autogen-opt-merges-2to1')?.checked;
  if (mergeRows.length) {
    persistMergesToWorkbook();
    if ($('autogen-opt-merges-2to1')) $('autogen-opt-merges-2to1').checked = true;
    autogenLog(
      `Merges via workbook — ${mergeRows.length} configured (${merge2.length}× 2:1 emit, ${merge3.length}× 3+:1 saved for later)`,
      'ok',
    );
    if (merge3.length) {
      autogenLog('3:1+ merges are stored in the workbook; L5X scaffold still emits 2:1 only.', 'warn');
    }
  } else if (mergeOn) {
    autogenLog('Merge override ON but no merge rows — set merges on Transport Build.', 'warn');
  }

  const sorterCfg = autogenState.sorter || defaultSorterConfig();
  const sorterConfigured = !!(
    sorterCfg.induct_conveyor
    || (sorterCfg.tracking_count || 0) > 0
    || (sorterCfg.divert_count || 0) > 0
    || (sorterCfg.tracking || []).some((t) => t && (t.conveyor || t.has_encoder === 'yes'))
  );
  // Evidence-driven: Sorter READY → Sorter_Track (no new sorter generation beyond pack include)
  const sorterTrackChecked = (R.sorter?.status === 'READY' && sorterConfigured)
    || !!$('autogen-opt-sorter-track')?.checked;
  if (sorterTrackChecked) {
    includePrograms.push('Sorter_Track');
    if ($('autogen-opt-sorter-track')) $('autogen-opt-sorter-track').checked = true;
  }
  if (sorterConfigured) {
    persistSorterToWorkbook();
    const encYes = (sorterCfg.tracking || []).filter((t) => t && t.has_encoder === 'yes').length
      + (sorterCfg.induct_has_encoder === 'yes' ? 1 : 0);
    autogenLog(
      `Sorter build: induct=${sorterCfg.induct_conveyor || '—'} · `
      + `track=${sorterCfg.tracking_count || 0} · diverts=${sorterCfg.divert_count || 0} · encYes=${encYes}`
      + (sorterTrackChecked ? ' · Sorter_Track INCLUDE' : ''),
      'info',
    );
  }

  // Keep Advanced checkboxes in sync with forced core
  if ($('autogen-opt-sys')) $('autogen-opt-sys').checked = true;
  if ($('autogen-opt-system')) $('autogen-opt-system').checked = true;
  if ($('autogen-opt-system-logic')) $('autogen-opt-system-logic').checked = true;
  if ($('autogen-opt-iomap')) $('autogen-opt-iomap').checked = true;
  if (sawReady && $('autogen-opt-sawtooth')) $('autogen-opt-sawtooth').checked = true;

  const packBits = ['Sys', 'DeviceComms+NTP', 'SystemLogic', 'IO_MAP(RUN banks→RIO)'];
  const packExtra = includePrograms.filter(
    (p) => !['System', 'Devices_Comm', 'NTP', 'System_Logic'].includes(p)
  );
  if (packExtra.length) packBits.push(...packExtra);
  autogenLog(`Program pack: ${packBits.join(' + ')}`, 'info');

  // One canonical workbook: merge disk Transport Apply with in-memory Sawtooth/Sorter.
  // Previously we reloaded disk and dropped SiteModel-populated sawtooth_build/sorter_build,
  // so Build PLC emitted Transport-only L5X even after Import discovery.
  if (mode === 'run') {
    const sawCfg = autogenState.sawtooth || {};
    const sawConfigured = !!(
      sawCfg.collector_conveyor
      || (sawCfg.lanes || []).some((l) => l && l.conveyor)
    );
    if (sawConfigured) persistSawtoothToWorkbook();
    if (sorterConfigured) persistSorterToWorkbook();
    try { updateSubsystemGenerationContract(); } catch (_) { /* ignore */ }

    if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
      try {
        const full = await fortnaAPI.autogenWorkbookLoad();
        if (full?.success && full.workbook) {
          const disk = full.workbook;
          const mem = autogenState.workbook || {};
          // ONE canonical workbook: never drop Transport conveyors OR Safety Apply.
          const merged = {
            ...disk,
            ...mem,
            conveyors: (Array.isArray(disk.conveyors) && disk.conveyors.length)
              ? disk.conveyors
              : (mem.conveyors || []),
            areas: (Array.isArray(disk.areas) && disk.areas.length)
              ? disk.areas
              : (mem.areas || disk.areas || mem.areas),
            merges_2to1: disk.merges_2to1 || mem.merges_2to1,
            safety_build: (mem.safety_build && (mem.safety_build.zones || []).length)
              ? mem.safety_build
              : (disk.safety_build || mem.safety_build || null),
            sawtooth_build: mem.sawtooth_build || disk.sawtooth_build || null,
            sorter_build: mem.sorter_build || disk.sorter_build || null,
          };
          if (sawConfigured) merged.sawtooth_build = { ...autogenState.sawtooth };
          if (sorterConfigured) merged.sorter_build = { ...autogenState.sorter };
          // GATE 4 — Prefer Applied safety_build; UNION zones by source_id.
          const diskSb = disk.safety_build;
          const memSb = mem.safety_build || autogenState.safety_build;
          merged.safety_build = preferSafetyBuild(memSb, diskSb);
          autogenState.workbook = merged;
          if (merged.safety_build) autogenState.safety_build = merged.safety_build;
          if (Array.isArray(disk.merges_2to1)) autogenState.merges_2to1 = disk.merges_2to1;
          const stubNames = (disk.conveyors || [])
            .filter((r) => r && (r.transport_build || r.source === 'transport_build_graph'))
            .map((r) => r.conveyor)
            .filter(Boolean);
          const mergeN = Array.isArray(disk.merges_2to1) ? disk.merges_2to1.length : 0;
          const convN = (disk.conveyors || []).length;
          if (stubNames.length || mergeN || convN) {
            autogenLog(
              `Canonical workbook: ${convN} conveyor row(s)`
                + (stubNames.length ? ` · ${stubNames.length} transport stub(s)` : '')
                + (mergeN ? ` · ${mergeN} merge(s)` : '')
                + (merged.sawtooth_build?.collector_conveyor ? ` · sawtooth ${merged.sawtooth_build.collector_conveyor}` : '')
                + (merged.sorter_build?.sorter_name ? ` · sorter ${merged.sorter_build.sorter_name}` : ''),
              'ok',
            );
          }
          try { if (typeof renderWorkbook === 'function') renderWorkbook(); } catch (_) { /* ignore */ }
        }
      } catch (_) { /* keep memory workbook */ }
    }
    // Persist merged workbook so Electron from-run --workbook matches UI editors
    try {
      if (typeof fortnaAPI.autogenWorkbookSave === 'function' && autogenState.workbook) {
        await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
      }
    } catch (e) {
      autogenLog(`Workbook save before generate failed: ${e?.message || e}`, 'warn');
    }
  }

  let res;
  try {
    const wbForGen = (mode === 'run' && autogenState.workbook) ? { ...autogenState.workbook } : undefined;
    if (wbForGen && autogenState.safety_build) {
      wbForGen.safety_build = autogenState.safety_build;
    }
    if (wbForGen && autogenState.omitUnresolvedSafety) {
      wbForGen.options = { ...(wbForGen.options || {}), omit_unresolved_safety: true };
      wbForGen.omit_unresolved_safety = true;
    }
    res = await fortnaAPI.autogenGenerate({
      mode,
      excel: excel || undefined,
      library: library || undefined,
      includePrograms,
      noSys,
      includeIoMap,
      noIoMap: !includeIoMap,
      omitUnresolvedSafety: !!autogenState.omitUnresolvedSafety,
      // Pass merged workbook so Build PLC == editor state (one canonical model).
      workbook: wbForGen,
      sorterBuild: sorterTrackChecked ? sorterCfg : undefined,
    });
  } catch (e) {
    res = { success: false, message: e?.message || String(e) };
  }
  autogenState.busy = false;
  if ($('btn-autogen-generate')) $('btn-autogen-generate').disabled = false;
  if ($('btn-autogen-from-run')) $('btn-autogen-from-run').disabled = false;
  if ($('btn-autogen-workbook-build')) $('btn-autogen-workbook-build').disabled = false;
  if (!res || !res.success) {
    setAutogenStatus('Error', 'error');
    const msg = res?.message || 'Generate failed (unknown error)';
    autogenLog(msg, 'err');
    if ($('autogen-detail')) $('autogen-detail').textContent = msg;
    if (/IO_MAP|io_map|iomap|VFD/i.test(msg)) {
      autogenState.lastGenerateIoMapError = msg;
      try { markReadinessDirty('hardware'); } catch (_) { /* ignore */ }
      const hw = ensureAutogenReadiness().hardware;
      hw.status = 'ERROR';
      hw.detail = msg;
      try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
    }
    if (/no active run/i.test(msg)) {
      autogenLog('Tip: I/O & Prints → Load RUN .tar.gz first, wait until machine status is ready, then Generate PLC Project.', 'warn');
    }
    autogenLog('Tip: click Verify engine — if a recent L5X exists under exports/autogen, generation may have succeeded on disk.', 'warn');
    return;
  }
  const r = res.result || {};
  const rep = r.report || {};
  autogenState.lastOut = r.out_dir || '';
  // Prefer exact timestamped L5X from result / build_manifest — never *_LATEST.L5X
  const manifestL5x = r.manifest?.output_path || '';
  const rawL5x = r.l5x || manifestL5x || '';
  autogenState.lastL5x = /_LATEST\.L5X$/i.test(rawL5x)
    ? (manifestL5x && !/_LATEST\.L5X$/i.test(manifestL5x) ? manifestL5x : '')
    : rawL5x;
  autogenState.lastManifest = r.manifest || null;
  autogenState.lastGenerateIoMapError = null;
  if (rep.es_program) {
    autogenState.lastEsReport = rep.es_program;
    try {
      const st = String(rep.es_program.status || '').toUpperCase();
      const e = ensureAutogenReadiness().safety;
      const omitted = !!(rep.es_program.omitted || autogenState.omitUnresolvedSafety);
      const partial = !!(rep.es_program.partial || (rep.es_program.emitted && st === 'REVIEW_REQUIRED'));
      const emittedZones = rep.es_program.emitted_zones || [];
      const omittedZones = rep.es_program.omitted_zones || [];
      const reviewDevs = rep.es_program.review_required_devices
        || safetyEvidence().unassignedDevices
        || [];
      if (omitted) {
        // Explicit full omit — keep REVIEW REQUIRED; never claim READY
        e.status = 'REVIEW_REQUIRED';
        e.detail = rep.es_program.detail
          || 'Safety omitted from this build — REVIEW REQUIRED';
        e.unresolved = rep.es_program.unresolved || 1;
        e.diagnostics = formatSafetyZoneDiagnostics(rep.es_program.zones || safetyEvidence().diagZones || []);
        autogenLog('BUILD GENERATED WITH REVIEW ITEMS', 'warn');
        autogenLog('SAFETY REVIEW REQUIRED — Program ES omitted', 'warn');
        autogenLog(
          `Omitted: Safety / ES — ${omittedZones.join(', ') || 'unresolved members'}`,
          'warn',
        );
        autogenLog('Controller is NOT complete / commissioning-ready until Safety is READY.', 'warn');
      } else if (partial || st === 'REVIEW_REQUIRED') {
        e.status = 'REVIEW_REQUIRED';
        e.detail = rep.es_program.detail || 'SAFETY REVIEW REQUIRED — partial ES emit';
        e.unresolved = rep.es_program.unresolved || reviewDevs.length || omittedZones.length || 1;
        e.diagnostics = formatSafetyZoneDiagnostics(rep.es_program.zones || safetyEvidence().diagZones || []);
        autogenLog('SAFETY REVIEW REQUIRED — partial Safety generation', 'warn');
        if (rep.es_program.emitted) {
          autogenLog(
            `Emitted Program ES zones (${emittedZones.length}): ${emittedZones.join(', ') || '(ready members)'}`,
            'warn',
          );
        }
        if (omittedZones.length) {
          autogenLog(`Omitted incomplete zones: ${omittedZones.join(', ')}`, 'warn');
        }
        if (reviewDevs.length) {
          autogenLog(
            `Unassigned devices remain: ${reviewDevs.slice(0, 12).join(', ')}${reviewDevs.length > 12 ? ', …' : ''}`,
            'warn',
          );
        }
      } else if (st === 'READY' && rep.es_program.emitted) {
        Object.assign(e, emptyReadinessEntry('READY'));
        e.detail = rep.es_program.detail || 'ES program emitted';
        e.appliedAt = new Date().toISOString();
      } else if (st && st !== 'NOT_DETECTED') {
        e.status = st === 'ERROR' ? 'ERROR' : 'REVIEW_REQUIRED';
        e.detail = rep.es_program.detail || st;
        e.unresolved = rep.es_program.unresolved || 1;
        e.diagnostics = formatSafetyZoneDiagnostics(rep.es_program.zones || []);
      }
    } catch (_) { /* ignore */ }
  } else if (autogenState.omitUnresolvedSafety) {
    try {
      const e = ensureAutogenReadiness().safety;
      e.status = 'REVIEW_REQUIRED';
      e.detail = 'Safety omitted from commissioning review build';
      e.diagnostics = safetyEvidence().diagnostics || [];
      autogenLog('BUILD GENERATED WITH REVIEW ITEMS', 'warn');
      autogenLog('SAFETY REVIEW REQUIRED — Program ES omitted', 'warn');
    } catch (_) { /* ignore */ }
  }
  const esReview = !!(
    autogenState.omitUnresolvedSafety
    || (rep.es_program && (
      String(rep.es_program.status || '').toUpperCase() === 'REVIEW_REQUIRED'
      || rep.es_program.partial
      || rep.es_program.omitted
    ))
  );
  setAutogenStatus(
    r.recovered
      ? 'Complete (recovered)'
      : (esReview ? 'Complete · SAFETY REVIEW REQUIRED' : 'Complete'),
    esReview ? 'warn' : 'ready',
  );
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  try { refreshAutogenBuildTracker(); } catch (_) { /* ignore */ }
  if ($('autogen-summary')) {
    $('autogen-summary').innerHTML = `
      <div class="space-y-1 text-sm">
        <div class="text-emerald-400 font-semibold">
          BUILD SUCCESS — GENERATED PLC${r.recovered ? ' <span class="text-amber-400 text-xs">(recovered from disk)</span>' : ''}
        </div>
        <div class="text-xs text-slate-300">Controller: <span class="mono text-violet-300">${escapeHtml(r.controller_name || '')}</span></div>
        <div class="text-xs text-slate-300">Source RUN: <span class="mono text-slate-400">${escapeHtml(r.source_run_filename || r.source_label || '')}</span></div>
        <div class="text-xs text-slate-300">Generated: <span class="mono text-slate-400">${escapeHtml(r.generated_at || '')}</span></div>
        <div class="text-xs text-slate-300">Output: <span class="mono text-emerald-300/90">${escapeHtml(r.l5x_filename || (autogenState.lastL5x || '').split(/[\\\\/]/).pop() || '')}</span></div>
        <div class="text-[10px] text-emerald-200/90 mono break-all leading-snug mt-1">${escapeHtml(autogenState.lastL5x || '')}</div>
        <div class="text-[10px] text-slate-500 font-normal mt-0.5">Studio not launched — use Open Output Folder / Open File Location. Only the timestamped L5X in exports/current is engineer-facing (no _LATEST.L5X).</div>
      </div>`;
  }
  // CURRENT PLC BUILD provenance card (absolute path + SHA256)
  if ($('autogen-current-build')) {
    const panel = $('autogen-current-build');
    const sha = r.l5x_sha256 || r.manifest?.output_sha256 || '';
    const shaShort = sha ? `${sha.slice(0, 16)}…${sha.slice(-8)}` : '—';
    panel.classList.remove('hidden');
    panel.innerHTML = `
      <div class="text-[11px] font-semibold text-emerald-300 tracking-wide">BUILD SUCCESS — CURRENT PLC BUILD</div>
      <div class="text-[11px] text-slate-300">Controller: <span class="mono text-violet-300">${escapeHtml(r.controller_name || '')}</span></div>
      <div class="text-[10px] text-slate-500">Exact L5X path (open this file in Studio):</div>
      <div class="mono text-[11px] text-emerald-200 break-all leading-snug font-semibold">${escapeHtml(autogenState.lastL5x || r.l5x || '')}</div>
      <div class="text-[11px] text-slate-400">Generated: <span class="mono">${escapeHtml(r.generated_at || '')}</span>
        ${r.git_commit ? ` · git <span class="mono text-slate-500">${escapeHtml(r.git_commit)}</span>` : ''}</div>
      <div class="text-[11px] text-slate-400">SHA256: <span class="mono text-[10px] text-slate-500" title="${escapeHtml(sha)}">${escapeHtml(shaShort)}</span></div>
    `;
  }
  if ($('autogen-stats')) {
    $('autogen-stats').classList.remove('hidden');
    $('autogen-stats').innerHTML = [
      ['Conveyors', rep.conveyor_count || 0],
      ['Tags', rep.tag_count || 0],
      ['Programs', rep.program_count || 0],
      ['I/O pts', rep.io_point_count || 0],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-violet-300 mono">${v}</div>
      </div>`).join('');
  }
  if ($('autogen-detail')) {
    $('autogen-detail').textContent = JSON.stringify({
      provenance: {
        controller: r.controller_name,
        source_run: r.source_run_filename || r.source_label,
        generated_at: r.generated_at,
        l5x: r.l5x,
        sha256: r.l5x_sha256,
        git_commit: r.git_commit,
        build_manifest: r.build_manifest,
      },
      report: rep,
    }, null, 2);
  }
  if ($('btn-autogen-open-out')) $('btn-autogen-open-out').disabled = !autogenState.lastOut;
  if ($('btn-autogen-open-l5x')) $('btn-autogen-open-l5x').disabled = !autogenState.lastL5x;
  if ($('btn-autogen-copy-l5x-path')) $('btn-autogen-copy-l5x-path').disabled = !autogenState.lastL5x;
  autogenLog(
    `Done (Python) — ${rep.conveyor_count || 0} conveyors, ${rep.tag_count || 0} tags, `
    + `${rep.program_count || 0} programs`
    + (r.l5x_bytes ? ` · ${(r.l5x_bytes / 1024 / 1024).toFixed(1)} MB L5X` : '')
    + (r.l5x_filename ? ` · ${r.l5x_filename}` : ''),
    'ok',
  );
  if (r.l5x) autogenLog(`CURRENT: ${r.l5x}`, 'ok');
  // Site Twin panel — prefer gaps embedded in generate result
  if (r.twin_gaps && Array.isArray(r.twin_gaps.gaps)) {
    autogenState.twinGaps = r.twin_gaps.gaps.map((g, i) => ({ ...g, id: g.id || `gap_${i}` }));
    renderTwinGaps();
    const n = r.twin_gaps.gap_count || autogenState.twinGaps.length;
    if ($('twin-status')) {
      $('twin-status').textContent = n
        ? `${n} gap(s) from this Generate — Search PRISM or Propose gap-fill`
        : 'No gaps from this Generate';
    }
    if ($('twin-gap-count')) $('twin-gap-count').textContent = `${n} gaps`;
    if (n) autogenLog(`Site Twin: ${n} gap(s) ready in PLC Autogen · Site Twin panel`, 'info');
  } else {
    refreshTwinGaps({ exportDir: r.out_dir || autogenState.lastOut || '' });
  }
}

function renderTwinGaps() {
  const host = $('twin-gaps-list');
  if (!host) return;
  const gaps = autogenState.twinGaps || [];
  if ($('twin-gap-count')) $('twin-gap-count').textContent = `${gaps.length} gaps`;
  if (!gaps.length) {
    host.innerHTML = `<div class="text-slate-600">No gaps loaded. Export L5X Package, then Refresh.</div>`;
    return;
  }
  host.innerHTML = gaps.map((g) => {
    const id = g.id || '';
    const sel = id && id === autogenState.twinSelectedGapId;
    const label = g.conveyor || g.merge || g.pe || g.type || 'gap';
    const sev = g.severity === 'warn' ? 'text-amber-400' : 'text-slate-400';
    return `<label class="flex items-start gap-1.5 px-1.5 py-1 rounded border ${sel ? 'border-cyan-700 bg-cyan-950/30' : 'border-slate-800/80'} cursor-pointer hover:border-slate-600" data-twin-gap="${escapeHtml(id)}">
      <input type="checkbox" class="twin-gap-cb mt-0.5 rounded border-slate-600" data-gap-id="${escapeHtml(id)}" checked>
      <span class="flex-1 min-w-0">
        <span class="mono ${sev}">${escapeHtml(label)}</span>
        <span class="text-slate-600"> · ${escapeHtml(g.type || '')}</span>
        <div class="text-slate-500 truncate" title="${escapeHtml(g.message || '')}">${escapeHtml(g.message || '')}</div>
      </span>
    </label>`;
  }).join('');
  host.querySelectorAll('[data-twin-gap]').forEach((el) => {
    el.addEventListener('click', (ev) => {
      if (ev.target.classList?.contains('twin-gap-cb')) return;
      autogenState.twinSelectedGapId = el.dataset.twinGap || null;
      renderTwinGaps();
    });
  });
}

function renderTwinPatches() {
  const wrap = $('twin-patches-wrap');
  const host = $('twin-patches-list');
  const btn = $('btn-twin-apply');
  if (!wrap || !host) return;
  const patches = autogenState.twinPatches || [];
  if (!patches.length) {
    wrap.classList.add('hidden');
    if (btn) btn.disabled = true;
    return;
  }
  wrap.classList.remove('hidden');
  host.innerHTML = patches.map((p, i) => {
    const id = p.id || `patch_${i}`;
    const actionable = p.op && p.op !== 'note_only';
    return `<label class="flex items-start gap-1.5 px-1.5 py-1 rounded border border-slate-800 bg-[#0c1219]">
      <input type="checkbox" class="twin-patch-cb mt-0.5 rounded border-slate-600" data-patch-id="${escapeHtml(id)}" ${actionable ? 'checked' : ''} ${actionable ? '' : 'disabled'}>
      <span class="flex-1 min-w-0">
        <span class="mono text-cyan-300">${escapeHtml(p.op || '')}</span>
        <span class="text-slate-500"> ${(p.conveyor || p.merge || '')} → ${escapeHtml(String(p.value || ''))}</span>
        <div class="text-slate-600 truncate" title="${escapeHtml(p.rationale || '')}">${escapeHtml(p.rationale || p.cite || '')}</div>
      </span>
    </label>`;
  }).join('');
  if (btn) btn.disabled = !patches.some((p) => p.op && p.op !== 'note_only');
}

async function refreshTwinGaps(opts = {}) {
  if (typeof fortnaAPI?.twinGapsLoad !== 'function') {
    if ($('twin-status')) $('twin-status').textContent = 'Twin API missing — restart Site Forge desktop app';
    return;
  }
  if ($('twin-status')) $('twin-status').textContent = 'Loading gaps…';
  try {
    const res = await fortnaAPI.twinGapsLoad({
      exportDir: opts.exportDir || autogenState.lastOut || '',
    });
    if (!res?.ok && !res?.success) {
      if ($('twin-status')) $('twin-status').textContent = res?.error || res?.message || 'Load failed';
      return;
    }
    autogenState.twinGaps = (res.gaps || []).map((g, i) => ({ ...g, id: g.id || `gap_${i}` }));
    renderTwinGaps();
    const n = res.gap_count || autogenState.twinGaps.length;
    if ($('twin-status')) {
      $('twin-status').textContent = n
        ? `${n} gap(s) from ${res.source ? res.source.split(/[/\\]/).slice(-3).join('/') : 'twin'}`
        : (res.message || 'No gaps yet — Export L5X Package first');
    }
  } catch (e) {
    if ($('twin-status')) $('twin-status').textContent = e?.message || String(e);
  }
}

function selectedTwinGapIds() {
  return Array.from(document.querySelectorAll('.twin-gap-cb:checked'))
    .map((el) => el.dataset.gapId)
    .filter(Boolean);
}

$('btn-twin-refresh')?.addEventListener('click', () => refreshTwinGaps());

$('btn-twin-search')?.addEventListener('click', async () => {
  if (typeof fortnaAPI?.twinPrismSearch !== 'function') {
    autogenLog('Twin search API missing — restart Site Forge', 'warn');
    return;
  }
  const gaps = autogenState.twinGaps || [];
  const id = autogenState.twinSelectedGapId || selectedTwinGapIds()[0] || gaps[0]?.id;
  const g = gaps.find((x) => x.id === id) || gaps[0];
  if (!g) {
    autogenLog('No gap to search — Refresh after Export L5X', 'warn');
    return;
  }
  const q = [g.type, g.conveyor || g.merge, g.pe, 'Fast_Conv Merge_2to1 photoeye'].filter(Boolean).join(' ');
  if ($('twin-status')) $('twin-status').textContent = `PRISM search: ${q.slice(0, 60)}…`;
  const res = await fortnaAPI.twinPrismSearch({ query: q, limit: 5 });
  const hitsHost = $('twin-search-hits');
  if (!res?.ok) {
    if ($('twin-status')) $('twin-status').textContent = res?.error || 'PRISM search failed';
    return;
  }
  if (hitsHost) {
    hitsHost.classList.remove('hidden');
    hitsHost.innerHTML = (res.hits || []).map((h) =>
      `<div class="mb-1"><span class="text-cyan-600">${escapeHtml(String(h.score ?? ''))}</span> `
      + `${escapeHtml((h.system || '').slice(0, 40))} — ${escapeHtml((h.path || '').split(/[/\\]/).slice(-2).join('/'))}`
      + `<div class="text-slate-600 truncate">${escapeHtml((h.snippet || '').slice(0, 160))}</div></div>`
    ).join('') || '<div>No hits</div>';
  }
  if ($('twin-status')) $('twin-status').textContent = `PRISM: ${res.count || 0} hit(s)`;
  autogenLog(`PRISM search → ${res.count || 0} hit(s) for ${g.conveyor || g.merge || g.type}`, 'ok');
});

$('btn-twin-propose')?.addEventListener('click', async () => {
  if (typeof fortnaAPI?.twinPropose !== 'function') {
    autogenLog('Twin propose API missing — restart Site Forge', 'warn');
    return;
  }
  const ids = selectedTwinGapIds();
  if ($('twin-status')) $('twin-status').textContent = 'Proposing patches (PRISM + SpaceXAI)…';
  autogenLog('Site Twin: Propose gap-fill…', 'info');
  const res = await fortnaAPI.twinPropose({
    gapIds: ids.length ? ids : undefined,
    limitGaps: 8,
  });
  if (!res?.ok) {
    if ($('twin-status')) $('twin-status').textContent = res?.error || 'Propose failed';
    autogenLog(res?.error || 'Propose failed', 'err');
    return;
  }
  autogenState.twinPatches = res.patches || [];
  renderTwinPatches();
  if ($('twin-status')) {
    $('twin-status').textContent = `${res.patch_count || 0} patch(es) · mode=${res.mode || '?'}`
      + (res.note ? ` — ${res.note}` : '');
  }
  autogenLog(
    `Propose: ${res.patch_count || 0} patch(es) via ${res.mode || 'unknown'}`
      + (res.mode === 'prism_heuristic' ? ' (set XAI_API_KEY for SpaceXAI)' : ''),
    res.mode === 'spacexai' ? 'ok' : 'warn',
  );
});

$('btn-twin-apply')?.addEventListener('click', async () => {
  if (typeof fortnaAPI?.twinApplyPatches !== 'function') {
    autogenLog('Twin apply API missing — restart Site Forge', 'warn');
    return;
  }
  const approvedIds = new Set(
    Array.from(document.querySelectorAll('.twin-patch-cb:checked')).map((el) => el.dataset.patchId)
  );
  const patches = (autogenState.twinPatches || []).map((p) => ({
    ...p,
    approved: approvedIds.has(p.id),
  }));
  if (!patches.some((p) => p.approved && p.op !== 'note_only')) {
    autogenLog('Check at least one actionable patch to apply', 'warn');
    return;
  }
  if ($('twin-status')) $('twin-status').textContent = 'Applying patches to workbook…';
  const res = await fortnaAPI.twinApplyPatches({ patches });
  if (!res?.ok) {
    autogenLog(res?.error || 'Apply patches failed', 'err');
    return;
  }
  autogenLog(res.message || `Applied ${res.applied_count || 0} patch(es)`, 'ok');
  if ($('twin-status')) {
    $('twin-status').textContent = res.message || 'Applied — Export L5X Package to refresh Studio files';
  }
  // Reload workbook into UI
  try {
    if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
      const full = await fortnaAPI.autogenWorkbookLoad();
      if (full?.success && full.workbook) {
        setWorkbook(full.workbook);
        if (typeof renderWorkbook === 'function') renderWorkbook();
      }
    }
  } catch (_) { /* ignore */ }
});

// Initial twin load (best-effort)
setTimeout(() => refreshTwinGaps(), 800);

$('btn-autogen-verify')?.addEventListener('click', async () => {
  if (typeof fortnaAPI.autogenVerify !== 'function') {
    autogenLog('Verify API missing — relaunch Site Forge', 'warn');
    return;
  }
  setAutogenStatus('Verifying…', 'busy');
  const res = await fortnaAPI.autogenVerify();
  if (!res.success) {
    setAutogenStatus('Error', 'error');
    autogenLog(res.message || 'Verify failed', 'err');
    return;
  }
  setAutogenStatus(res.runLoaded ? 'Ready' : 'No RUN', res.runLoaded ? 'ready' : 'idle');
  const lines = [
    `Engine: ${res.engine} (fortna_autogen.py)`,
    `Script: ${res.scriptExists ? 'OK' : 'MISSING'}`,
    `Library: ${res.libraryExists ? 'OK' : 'MISSING'} — ${(res.library || '').split(/[/\\]/).pop()}`,
    `RUN: ${res.runLoaded ? res.runDir : 'NOT LOADED — import tar.gz on I/O & Prints'}`,
  ];
  if (res.latestExport) {
    lines.push(
      `Last export: ${res.latestExport.conveyor_count || '?'} conveyors / `
      + `${res.latestExport.tag_count || '?'} tags`,
    );
    lines.push(res.latestExport.l5x || res.latestExport.out_dir || '');
  } else {
    lines.push('Last export: none yet');
  }
  if ($('autogen-detail')) $('autogen-detail').textContent = lines.join('\n');
  if ($('autogen-summary')) {
    $('autogen-summary').innerHTML = `
      <div class="text-sm space-y-1">
        <div class="text-violet-300 font-semibold">Python autogen check</div>
        <div class="text-xs text-slate-400">${escapeHtml(res.note || '')}</div>
        <div class="text-xs ${res.runLoaded ? 'text-emerald-400' : 'text-amber-400'}">
          ${res.runLoaded ? 'RUN loaded — Preview / Generate available' : 'Load .tar.gz on I/O & Prints first'}
        </div>
      </div>`;
  }
  autogenLog(
    res.runLoaded
      ? `Verify OK — Python engine + RUN ready`
      : `Verify: engine OK, but no RUN loaded`,
    res.runLoaded ? 'ok' : 'warn',
  );
  // refresh badge
  initAutogenDefaults();
});

$('btn-autogen-generate')?.addEventListener('click', () => runAutogenGenerate('excel'));
$('btn-autogen-from-run')?.addEventListener('click', () => runAutogenGenerate('run'));
$('btn-autogen-workbook-build')?.addEventListener('click', () => buildAutogenWorkbook());
$('btn-autogen-workbook-save')?.addEventListener('click', () => saveAutogenWorkbook());
$('btn-autogen-wb-apply-type')?.addEventListener('click', () => bulkApplyType());
$('btn-autogen-wb-apply-area')?.addEventListener('click', () => bulkApplyArea());
// 2:1 Merges + Sorter build UI
try { wireMergeBuildUi(); } catch (e) { console.warn('merge UI wire failed', e); }
try { wireSorterBuildUi(); } catch (e) { console.warn('sorter UI wire failed', e); }

/** Compile-hub: pull Transport Build → Autogen (same as legacy merge-from-transport). */
$('btn-hub-from-transport')?.addEventListener('click', () => {
  const legacy = $('btn-merge-from-transport');
  if (legacy && legacy !== $('btn-hub-from-transport')) {
    legacy.click();
    return;
  }
  // Inline path when merge panel button is absent
  (async () => {
    try {
      let graph = null;
      try {
        const raw = localStorage.getItem('siteforge.transportBuild.v2')
      || localStorage.getItem('siteforge.transportBuild.v1');
        if (raw) {
          const data = JSON.parse(raw);
          if (Array.isArray(data.areas)) graph = { version: 1, areas: data.areas };
        }
      } catch (_) { /* ignore */ }
      if (!graph?.areas?.length) {
        autogenLog('No Transport Build areas yet — draw Transport1 / Merge5 on Transport Build, then Apply or use this button.', 'warn');
        return;
      }
      const res = await applyTransportMergesToAutogen({ graph });
      if (!res?.ok) {
        autogenLog(`Transport stub import failed: ${res?.error || 'unknown'}`, 'err');
        return;
      }
      refreshAutogenCompileHub();
      autogenLog(`Transport stubs/merges applied: ${res.summary || 'ok'}`, 'ok');
    } catch (e) {
      autogenLog(`Transport stub import error: ${e?.message || e}`, 'err');
    }
  })();
});

$('btn-hub-save-transport-wb')?.addEventListener('click', async () => {
  await saveAutogenWorkbook();
  refreshAutogenCompileHub();
});

/**
 * Clear Current Project: active RUN extract + workbook edits + Transport/Sawtooth/Sorter
 * + matching exports/autogen outputs. Does NOT delete libraries, docs, fixtures, or
 * original .tar.gz archives on disk.
 */
async function clearProjectBuilds() {
  const ok = confirm(
    'WARNING — Clear Current Project?\n\n'
    + 'This removes for the CURRENT project only:\n'
    + '• Active RUN extract (workspace/active) and active-meta.json\n'
    + '• Workbook edits (workspace/autogen_workbook.json)\n'
    + '• Transport / Sawtooth / Sorter builds and merge rows\n'
    + '• Matching generated outputs under exports/autogen\n'
    + '  (timestamp folders for this archive + MACHINE_LATEST.L5X)\n\n'
    + 'Does NOT delete:\n'
    + '• Original .tar.gz archives on disk\n'
    + '• libraries / docs / fixtures / exports/_archive\n\n'
    + 'You will need to load a RUN again. This cannot be undone from the UI.\n'
    + 'Continue?'
  );
  if (!ok) return;

  const ok2 = confirm(
    'Final WARNING: wipe current project RUN + edits + Transport/Sawtooth/Sorter + generated outputs now?\n\n'
    + '(Libraries, docs, and fixtures are kept.)'
  );
  if (!ok2) return;

  try {
    // Disk wipe first (workspace + workbook + current-project autogen outputs)
    if (typeof fortnaAPI?.clearCurrentProject === 'function') {
      const res = await fortnaAPI.clearCurrentProject();
      if (!res?.success) {
        autogenLog(res?.message || 'clearCurrentProject failed', 'err');
      } else if (res.cleared_outputs?.length) {
        autogenLog(`Removed ${res.cleared_outputs.length} autogen output(s) for this project.`, 'ok');
      }
    } else if (typeof fortnaAPI?.clearWorkspace === 'function') {
      // Fallback if preload is stale — workspace only (workbook cleared below)
      await fortnaAPI.clearWorkspace();
    }
    try { resetWorkspaceUi(); } catch (_) { /* ignore */ }

    // Transport canvas — leave empty (no Transport_1 until Auto Build)
    if (typeof window.transportBuildClearAll === 'function') {
      window.transportBuildClearAll({ leaveEmpty: true });
    }
    // Strip v1+v2 after clearAll so next load stays empty until Auto Build
    ['siteforge.transportBuild.v1', 'siteforge.transportBuild.v2'].forEach((k) => {
      try { localStorage.removeItem(k); } catch (_) { /* ignore */ }
    });
    // Again after any incidental save from refresh/render paths
    ['siteforge.transportBuild.v1', 'siteforge.transportBuild.v2'].forEach((k) => {
      try { localStorage.removeItem(k); } catch (_) { /* ignore */ }
    });
    ['tb-insp-pe-role-exit', 'tb-insp-pe-role-add', 'tb-insp-pe-role-jam', 'tb-insp-pe-role-full'].forEach((id) => {
      const el = $(id);
      if (el) el.checked = false;
    });
    $('tb-insp-pe-roles-wrap')?.classList.add('hidden');
    $('tb-inspector')?.classList.add('hidden');
    $('tb-inspector-empty')?.classList.remove('hidden');
    if (typeof window.transportBuildRefresh === 'function') window.transportBuildRefresh();

    autogenState.merges_2to1 = [];
    try { localStorage.removeItem('fortna_merges_2to1'); } catch (_) { /* ignore */ }
    if ($('merge-2to1-count')) $('merge-2to1-count').value = '0';
    try { renderMergeBuild(); } catch (_) { /* ignore */ }

    autogenState.sawtooth = defaultSawtoothConfig();
    try { localStorage.removeItem('fortna_sawtooth_build'); } catch (_) { /* ignore */ }
    try { renderSawtoothBuild(); updateSawtoothSummary(); } catch (_) { /* ignore */ }

    autogenState.sorter = defaultSorterConfig();
    try { localStorage.removeItem('fortna_sorter_build'); } catch (_) { /* ignore */ }
    try { renderSorterBuild(); } catch (_) { /* ignore */ }

    // Safety Build — wipe draft + in-memory model (old zones must not survive Clear)
    try {
      if (typeof window.safetyBuildClear === 'function') window.safetyBuildClear();
      else localStorage.removeItem('siteforge.safetyBuild.v1');
    } catch (_) {
      try { localStorage.removeItem('siteforge.safetyBuild.v1'); } catch (__) { /* ignore */ }
    }
    try {
      autogenState.safety_build = { version: 1, source: 'cleared', zones: [], devices: [] };
      autogenState.safetyDevices = [];
      autogenState.lastEsReport = null;
    } catch (_) { /* ignore */ }

    autogenState.lastGenerateIoMapError = null;
    autogenState.readiness = {
      hardware: emptyReadinessEntry(),
      transport: emptyReadinessEntry(),
      sawtooth: emptyReadinessEntry(),
      sorter: emptyReadinessEntry(),
      system: emptyReadinessEntry(),
      safety: emptyReadinessEntry(),
    };

    try { localStorage.removeItem('fortna_last_equipment_names'); } catch (_) { /* ignore */ }

    // Uncheck all program-pack options
    [
      'autogen-opt-merges-2to1',
      'autogen-opt-shippingsorter',
      'autogen-opt-shippingsorter-popup',
      'autogen-opt-sorter-track',
      'autogen-opt-sawtooth',
      'autogen-opt-wcs',
    ].forEach((id) => {
      if ($(id)) $(id).checked = false;
    });

    // Empty workbook in memory (+ persist empty file if IPC left a stub)
    const emptyWb = {
      version: 1,
      kind: 'fortna_autogen_workbook',
      generated_utc: new Date().toISOString(),
      source: 'cleared',
      site: '',
      machine: '',
      project_name: '',
      conveyors: [],
      io_map: [],
      areas: [],
      merges_2to1: [],
      safety_build: { version: 1, source: 'cleared', zones: [], devices: [] },
      safety_zones: [],
      options: { areas: [], safety_zones: [], exit_pe: [], types: [] },
      stats: { conveyor_count: 0, io_mapped: 0 },
      type_counts: {},
    };
    autogenState.workbook = emptyWb;
    autogenState.selected = new Set();
    if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
      try { await fortnaAPI.autogenWorkbookSave({ workbook: emptyWb }); } catch (_) { /* ignore */ }
    }
    try { setWorkbook(emptyWb); } catch (_) {
      try { renderWorkbook(); } catch (__) { /* ignore */ }
    }

    if ($('autogen-summary')) {
      $('autogen-summary').innerHTML =
        '<strong class="text-amber-300">NO ACTIVE PROJECT</strong> — load a '
        + '<strong class="text-slate-300">.tar.gz</strong> on I/O &amp; Prints to start.';
    }
    if ($('autogen-stats')) {
      $('autogen-stats').classList.add('hidden');
      $('autogen-stats').innerHTML = '';
    }
    if ($('autogen-wb-count')) $('autogen-wb-count').textContent = '0 rows';
    if ($('autogen-detail')) $('autogen-detail').textContent = '—';
    setAutogenStatus('NO ACTIVE PROJECT', 'idle');
    try { setStatus('workspace-status', 'NO ACTIVE PROJECT', 'idle'); } catch (_) { /* ignore */ }
    try { setIoRunStatus('NO ACTIVE PROJECT', 'idle'); } catch (_) { /* ignore */ }

    try {
      clearIoCompareState({ clearPanels: true });
    } catch (_) { /* ignore */ }

    refreshAutogenCompileHub();
    autogenLog('Current project cleared — NO ACTIVE PROJECT.', 'ok');
  } catch (e) {
    autogenLog(`Clear Current Project failed: ${e?.message || e}`, 'err');
  }
}

$('btn-clear-project-builds')?.addEventListener('click', () => {
  clearProjectBuilds().catch((e) => autogenLog(`Clear failed: ${e?.message || e}`, 'err'));
});

function emptyMergeRow() {
  return {
    name: '',
    area: '',
    lanes: 2, // 2 = 2:1, 3 = 3:1 (from prints)
    lane_a: '',
    lane_b: '',
    lane_c: '',
    discharge: '',
    pe_a: '',
    pe_b: '',
    pe_c: '',
    jam_pe: '',
  };
}

function mergeLaneCount(m) {
  const n = Number(m?.lanes);
  if (n === 3 || n === 4) return n;
  return 2;
}

function persistMergesToWorkbook() {
  if (!autogenState.workbook) autogenState.workbook = { conveyors: [], options: {} };
  autogenState.workbook.merges_2to1 = [...(autogenState.merges_2to1 || [])];
}

/**
 * Apply Transport Build graph → Autogen UI + workbook.
 * Areas (renameable) → conveyor main_area; simple transport + merges.
 * opts.graph required (live Transport canvas). Returns status object.
 */
async function applyTransportMergesToAutogen(opts = {}) {
  if (typeof fortnaAPI?.transportApplyAutogen !== 'function') {
    return { ok: false, error: 'Desktop IPC missing — restart Site Forge.' };
  }
  const graph = opts.graph;
  if (!graph || !Array.isArray(graph.areas)) {
    return { ok: false, error: 'No Transport graph — Apply from the Transport Build tab.' };
  }
  const res = await fortnaAPI.transportApplyAutogen({ graph });
  if (!res?.ok && !res?.success) {
    return { ok: false, error: res?.error || 'Apply failed', exports_dir: res?.exports_dir };
  }
  const merges = Array.isArray(res.merges_2to1) ? res.merges_2to1 : [];
  autogenState.merges_2to1 = merges;
  if (!autogenState.workbook) autogenState.workbook = { conveyors: [], options: {} };
  // Reload full workbook (areas + conveyor main_area updates)
  if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
    try {
      const full = await fortnaAPI.autogenWorkbookLoad();
      if (full?.success && full.workbook) {
        autogenState.workbook = full.workbook;
        if (Array.isArray(full.workbook.merges_2to1)) {
          autogenState.merges_2to1 = full.workbook.merges_2to1;
        }
      }
    } catch (_) {
      autogenState.workbook.merges_2to1 = [...merges];
    }
  } else {
    autogenState.workbook.merges_2to1 = [...merges];
  }
  if ($('merge-2to1-count')) {
    $('merge-2to1-count').value = String(autogenState.merges_2to1.length);
  }
  if (autogenState.merges_2to1.length && $('autogen-opt-merges-2to1')) {
    $('autogen-opt-merges-2to1').checked = true;
  }
  try { localStorage.setItem('fortna_merges_2to1', JSON.stringify(autogenState.merges_2to1 || [])); } catch (_) { /* ignore */ }
  renderMergeBuild();
  updateMergeSummary();
  // Refresh site-config table so new/renamed areas show on conveyor rows
  try {
    if (typeof renderWorkbook === 'function') renderWorkbook();
  } catch (_) { /* optional */ }
  const n = autogenState.merges_2to1.filter((m) => m && (m.name || m.lane_a)).length;
  const nAreas = (res.areas_applied || []).length;
  const nConv = (res.conveyors_updated || []).length + (res.conveyors_created || []).length;
  setReadinessApplied(
    'transport',
    `${nAreas} area(s) · ${nConv} conv · ${n} merge(s)`,
  );
  const st = $('merge-save-status');
  if (st) {
    st.textContent = `Applied · READY · ${nAreas} area(s), ${nConv} conv, ${n} merge(s)`;
    st.className = 'text-[10px] text-emerald-500 mono';
  }
  if (typeof autogenLog === 'function') {
    autogenLog(
      `Transport Apply → Autogen READY: ${res.summary || `${nAreas} areas / ${n} merges`} `
      + `(${res.workbook_path || 'workbook saved'}). Merges follow workbook on Export.`,
      'ok',
    );
    if ((res.areas_applied || []).length) {
      autogenLog(`Areas now in workbook: ${(res.areas_applied || []).join(', ')}`, 'info');
    }
    for (const w of res.area_warnings || []) autogenLog(w, 'warn');
  }
  return {
    ok: true,
    summary: res.summary || '',
    applied_count: res.applied_count || n,
    total_count: res.total_count || n,
    areas_applied: res.areas_applied || [],
    conveyors_updated: res.conveyors_updated || [],
    conveyors_created: res.conveyors_created || [],
    workbook_path: res.workbook_path,
    path: res.path,
    exports_dir: res.exports_dir,
    area_warnings: res.area_warnings || [],
    note: res.note || '',
  };
}
window.applyTransportMergesToAutogen = applyTransportMergesToAutogen;

function updateMergeSummary() {
  try { refreshAutogenCompileHub(); } catch (_) { /* ignore */ }
  const el = $('autogen-merge-summary');
  if (!el) return;
  const list = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const n = list.length;
  if (!n) {
    el.textContent = '0 merges';
    return;
  }
  const n2 = list.filter((m) => mergeLaneCount(m) === 2).length;
  const n3 = list.filter((m) => mergeLaneCount(m) >= 3).length;
  const bits = [];
  if (n2) bits.push(`${n2}×2:1`);
  if (n3) bits.push(`${n3}×3:1`);
  el.textContent = `${n} merge${n === 1 ? '' : 's'}${bits.length ? ` · ${bits.join(' ')}` : ''}`;
}

function renderMergeBuild() {
  const rows = $('merge-2to1-rows');
  const countEl = $('merge-2to1-count');
  if (!rows) return;
  const convs = conveyorNameList();
  const pes = photoeyeNameList();
  const areas = [...new Set((autogenState.workbook?.conveyors || []).map((r) => r.area).filter(Boolean))].sort();
  let n = Math.max(0, Math.min(40, parseInt(countEl?.value, 10) || 0));
  if (countEl) countEl.value = String(n);
  while ((autogenState.merges_2to1 || []).length < n) autogenState.merges_2to1.push(emptyMergeRow());
  autogenState.merges_2to1 = (autogenState.merges_2to1 || []).slice(0, n);
  if (!n) {
    rows.innerHTML = '<div class="text-[10px] text-slate-600">Set “How many merges?” above, then choose lanes per merge (2:1 or 3:1) from the prints.</div>';
    updateMergeSummary();
    return;
  }
  const convOpts = (sel) => convs.map((c) =>
    `<option value="${escapeHtml(c)}" ${c === sel ? 'selected' : ''}>${escapeHtml(c)}</option>`
  ).join('');
  const peOpts = (sel) => pes.map((p) =>
    `<option value="${escapeHtml(p)}" ${p === sel ? 'selected' : ''}>${escapeHtml(p)}</option>`
  ).join('');
  const areaOpts = (sel) => areas.map((a) =>
    `<option value="${escapeHtml(a)}" ${a === sel ? 'selected' : ''}>${escapeHtml(a)}</option>`
  ).join('');
  rows.innerHTML = autogenState.merges_2to1.map((m, i) => {
    const lanes = mergeLaneCount(m);
    const laneLabel = lanes === 2 ? '2:1' : lanes === 3 ? '3:1' : `${lanes}:1`;
    const laneC = lanes >= 3
      ? `<select class="merge-lane-c flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono" data-i="${i}">
          <option value="">Lane C…</option>${convOpts(m.lane_c || '')}
        </select>`
      : '';
    const peC = lanes >= 3
      ? `<select class="merge-pe-c flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300" data-i="${i}">
          <option value="">PE C…</option>${peOpts(m.pe_c || '')}
        </select>`
      : '';
    return `
    <div class="rounded-lg border border-slate-800 bg-[#0a1016] p-2 space-y-1.5" data-merge-i="${i}">
      <div class="flex flex-wrap gap-2 items-center">
        <span class="text-[10px] text-slate-600 w-6 mono">#${i + 1}</span>
        <input class="merge-name w-24 bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-amber-200/90"
          data-i="${i}" placeholder="P316" value="${escapeHtml(m.name || '')}" title="Merge name → P316_Merge">
        <label class="text-[10px] text-slate-500 flex items-center gap-1" title="How many lanes feed this merge?">
          Lanes
          <select class="merge-lanes w-20 bg-[#101820] border border-cyan-900/50 rounded px-1.5 py-1 text-[10px] mono text-cyan-300" data-i="${i}">
            <option value="2" ${lanes === 2 ? 'selected' : ''}>2 (2:1)</option>
            <option value="3" ${lanes === 3 ? 'selected' : ''}>3 (3:1)</option>
            <option value="4" ${lanes === 4 ? 'selected' : ''}>4 (4:1)</option>
          </select>
        </label>
        <span class="text-[9px] mono text-slate-600">${laneLabel}</span>
        <select class="merge-area min-w-[8rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] text-slate-200" data-i="${i}">
          <option value="">Area (optional)…</option>${areaOpts(m.area || '')}
        </select>
      </div>
      <div class="flex flex-wrap gap-2 items-center pl-6">
        <select class="merge-lane-a flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono" data-i="${i}">
          <option value="">Lane A…</option>${convOpts(m.lane_a || '')}
        </select>
        <select class="merge-lane-b flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono" data-i="${i}">
          <option value="">Lane B…</option>${convOpts(m.lane_b || '')}
        </select>
        ${laneC}
        <select class="merge-discharge flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono" data-i="${i}">
          <option value="">Discharge…</option>${convOpts(m.discharge || '')}
        </select>
      </div>
      <div class="flex flex-wrap gap-2 items-center pl-6">
        <select class="merge-pe-a flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300" data-i="${i}">
          <option value="">PE A…</option>${peOpts(m.pe_a || '')}
        </select>
        <select class="merge-pe-b flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300" data-i="${i}">
          <option value="">PE B…</option>${peOpts(m.pe_b || '')}
        </select>
        ${peC}
        <select class="merge-jam-pe flex-1 min-w-[7rem] bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300" data-i="${i}">
          <option value="">Jam PE…</option>${peOpts(m.jam_pe || '')}
        </select>
      </div>
      ${lanes >= 3 ? '<div class="pl-6 text-[9px] text-amber-600/80">3:1+ config saved — L5X emit still 2:1 only (testing).</div>' : ''}
    </div>`;
  }).join('');
  const bind = (cls, key) => {
    rows.querySelectorAll(`.${cls}`).forEach((el) => {
      el.addEventListener('change', () => {
        const i = Number(el.dataset.i);
        if (!autogenState.merges_2to1[i]) autogenState.merges_2to1[i] = emptyMergeRow();
        if (key === 'lanes') {
          autogenState.merges_2to1[i].lanes = Number(el.value) || 2;
          renderMergeBuild(); // rebuild lane C / PE C fields
          return;
        }
        autogenState.merges_2to1[i][key] = el.value || '';
        updateMergeSummary();
      });
      if (el.tagName === 'INPUT') {
        el.addEventListener('input', () => {
          const i = Number(el.dataset.i);
          if (!autogenState.merges_2to1[i]) autogenState.merges_2to1[i] = emptyMergeRow();
          autogenState.merges_2to1[i][key] = el.value || '';
          updateMergeSummary();
        });
      }
    });
  };
  bind('merge-name', 'name');
  bind('merge-area', 'area');
  bind('merge-lanes', 'lanes');
  bind('merge-lane-a', 'lane_a');
  bind('merge-lane-b', 'lane_b');
  bind('merge-lane-c', 'lane_c');
  bind('merge-discharge', 'discharge');
  bind('merge-pe-a', 'pe_a');
  bind('merge-pe-b', 'pe_b');
  bind('merge-pe-c', 'pe_c');
  bind('merge-jam-pe', 'jam_pe');
  updateMergeSummary();
}

function wireMergeBuildUi() {
  $('merge-2to1-count')?.addEventListener('change', () => {
    renderMergeBuild();
  });
  $('btn-merge-save')?.addEventListener('click', async () => {
    persistMergesToWorkbook();
    const st = $('merge-save-status');
    const list = (autogenState.merges_2to1 || []).filter((m) => m && m.name);
    const n = list.length;
    const n2 = list.filter((m) => mergeLaneCount(m) === 2).length;
    const n3 = list.filter((m) => mergeLaneCount(m) >= 3).length;
    if (n && $('autogen-opt-merges-2to1')) $('autogen-opt-merges-2to1').checked = true;
    try {
      if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
        await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
      }
      localStorage.setItem('fortna_merges_2to1', JSON.stringify(autogenState.merges_2to1 || []));
      if (st) {
        st.textContent = `Saved ${n} (${n2}×2:1${n3 ? `, ${n3}×3:1` : ''})`;
        st.className = 'text-[10px] text-emerald-500 mono';
      }
      autogenLog(`Saved ${n} merge row(s) to workbook (${n2}× 2:1, ${n3}× 3:1+).`, 'ok');
    } catch (e) {
      if (st) { st.textContent = 'Save failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Merge save failed: ${e?.message || e}`, 'err');
    }
  });
  $('btn-merge-from-transport')?.addEventListener('click', async () => {
    const st = $('merge-save-status');
    if (st) { st.textContent = 'Importing…'; st.className = 'text-[10px] text-fuchsia-400 mono'; }
    try {
      // Prefer live graph from Transport Build tab
      let graph = null;
      try {
        const raw = localStorage.getItem('siteforge.transportBuild.v2')
      || localStorage.getItem('siteforge.transportBuild.v1');
        if (raw) {
          const data = JSON.parse(raw);
          if (Array.isArray(data.areas)) graph = { version: 1, areas: data.areas };
        }
      } catch (_) { /* ignore */ }
      if (!graph) {
        if (st) { st.textContent = 'Open Transport Build first'; st.className = 'text-[10px] text-amber-400 mono'; }
        autogenLog('From Transport Build: no saved graph — draw/save on Transport Build, then Apply.', 'warn');
        return;
      }
      const res = await applyTransportMergesToAutogen({ graph });
      if (!res?.ok) {
        if (st) { st.textContent = res?.error || 'Import failed'; st.className = 'text-[10px] text-red-400 mono'; }
        autogenLog(`Transport import failed: ${res?.error || 'unknown'}`, 'err');
        return;
      }
      autogenLog(
        `Imported from Transport: ${res.summary || ''}. `
        + (res.applied_count ? 'Merge pack ON — ' : '')
        + 'Generate to emit Fast/Slow (+ merges if any).',
        'ok',
      );
    } catch (e) {
      if (st) { st.textContent = 'Import failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Transport import error: ${e?.message || e}`, 'err');
    }
  });
  $('btn-merge-clear')?.addEventListener('click', () => {
    autogenState.merges_2to1 = [];
    if ($('merge-2to1-count')) $('merge-2to1-count').value = '0';
    persistMergesToWorkbook();
    renderMergeBuild();
    const st = $('merge-save-status');
    if (st) { st.textContent = 'Cleared'; st.className = 'text-[10px] text-slate-500 mono'; }
  });
  try {
    const raw = localStorage.getItem('fortna_merges_2to1');
    if (raw && !(autogenState.workbook?.merges_2to1 || []).length) {
      autogenState.merges_2to1 = JSON.parse(raw) || [];
      if ($('merge-2to1-count')) $('merge-2to1-count').value = String(autogenState.merges_2to1.length);
    }
  } catch (_) { /* ignore */ }
  if (Array.isArray(autogenState.workbook?.merges_2to1)) {
    autogenState.merges_2to1 = autogenState.workbook.merges_2to1;
    if ($('merge-2to1-count')) $('merge-2to1-count').value = String(autogenState.merges_2to1.length);
  }
  renderMergeBuild();
}
$('btn-autogen-cat-area')?.addEventListener('click', () => {
  addCatalogValue('area', $('autogen-cat-area')?.value);
  if ($('autogen-cat-area')) $('autogen-cat-area').value = '';
});
$('btn-autogen-cat-safety')?.addEventListener('click', () => {
  addCatalogValue('safety', $('autogen-cat-safety')?.value);
  if ($('autogen-cat-safety')) $('autogen-cat-safety').value = '';
});
$('btn-autogen-cat-exitpe')?.addEventListener('click', () => {
  addCatalogValue('exitpe', $('autogen-cat-exitpe')?.value);
  if ($('autogen-cat-exitpe')) $('autogen-cat-exitpe').value = '';
});
$('btn-autogen-cat-type')?.addEventListener('click', () => {
  addCatalogValue('type', $('autogen-cat-type')?.value);
  if ($('autogen-cat-type')) $('autogen-cat-type').value = '';
});
// Enter key in catalog fields
['autogen-cat-area', 'autogen-cat-safety', 'autogen-cat-exitpe', 'autogen-cat-type'].forEach((id) => {
  $(id)?.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter') return;
    ev.preventDefault();
    const map = {
      'autogen-cat-area': 'area',
      'autogen-cat-safety': 'safety',
      'autogen-cat-exitpe': 'exitpe',
      'autogen-cat-type': 'type',
    };
    addCatalogValue(map[id], $(id)?.value);
    if ($(id)) $(id).value = '';
  });
});
$('autogen-wb-select-all')?.addEventListener('change', (ev) => {
  const on = !!ev.target.checked;
  autogenState.selected = new Set();
  if (on && autogenState.workbook) {
    for (const r of autogenState.workbook.conveyors || []) {
      if (r.conveyor) autogenState.selected.add(String(r.conveyor).toUpperCase());
    }
  }
  renderWorkbook();
});
document.querySelectorAll('.wb-tab').forEach((btn) => {
  btn.addEventListener('click', () => switchWbTab(btn.dataset.wbTab));
});
// Load saved workbook on autogen init
(async () => {
  if (typeof fortnaAPI.autogenWorkbookLoad === 'function') {
    try {
      const res = await fortnaAPI.autogenWorkbookLoad();
      if (res?.success && res.workbook) {
        setWorkbook(res.workbook);
        autogenLog('Loaded saved AutoGen workbook from disk', 'info');
      }
    } catch (_) { /* ignore */ }
  }
})();
$('btn-autogen-preview-run')?.addEventListener('click', async () => {
  setAutogenStatus('Preview…', 'busy');
  await initAutogenDefaults();
  const res = await fortnaAPI.autogenPreviewRun({});
  if (!res.success) {
    setAutogenStatus('Error', 'error');
    autogenLog(res.message || 'Preview failed', 'err');
    if (/no active run/i.test(res.message || '')) {
      autogenLog('Load the .tar.gz on I/O & Prints first (status must show machine loaded).', 'warn');
    }
    return;
  }
  setAutogenStatus('Preview OK', 'ready');
  const r = res.result || {};
  // conveyor_count is authoritative; fall back to sample array length only if missing
  const convN = Number(r.conveyor_count != null ? r.conveyor_count : (r.conveyors || []).length) || 0;
  const vfdN = Number(r.vfd_conveyor_count) || 0;
  const msN = r.ms_conveyor_count != null ? Number(r.ms_conveyor_count) : Math.max(0, convN - vfdN);
  const ioN = Number(r.io_point_count) || 0;
  const areaN = Array.isArray(r.areas) ? r.areas.length : 0;
  if ($('autogen-summary')) {
    $('autogen-summary').innerHTML = `
      <div class="text-sm space-y-1">
        <div class="text-violet-300 font-semibold">${escapeHtml(r.project_name || 'RUN → Python autogen')}</div>
        <div class="text-xs text-emerald-500/90">Engine: ${escapeHtml(r.engine || 'python')} — not Excel VBA</div>
        <div class="text-xs text-slate-400">${convN} conveyors
          (${vfdN} VFD / ${msN} MS)
          · ${ioN} I/O pts · ${areaN} areas</div>
        <div class="text-[10px] text-slate-500 mt-1">Same table the team used to type into Excel — filled from tar.gz.</div>
        ${convN === 0 ? '<div class="text-[10px] text-amber-400 mt-1">0 conveyors — re-load tar.gz on I/O &amp; Prints, then Preview again (after relaunch).</div>' : ''}
      </div>`;
  }
  if ($('autogen-stats')) {
    $('autogen-stats').classList.remove('hidden');
    $('autogen-stats').innerHTML = [
      ['Conveyors', convN],
      ['VFD type', vfdN],
      ['MS type', msN],
      ['I/O pts', ioN],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-violet-300 mono">${v}</div>
      </div>`).join('');
  }
  if ($('autogen-detail')) {
    // Slim inspect: counts + sample, not a single nested conveyor object
    const slim = {
      ok: r.ok,
      engine: r.engine || 'python',
      project_name: r.project_name,
      processor: r.processor,
      conveyor_count: convN,
      vfd_conveyor_count: vfdN,
      ms_conveyor_count: msN,
      io_point_count: ioN,
      areas: r.areas,
      run_dir: r.run_dir,
      conveyor_sample: (r.conveyors || []).slice(0, 12).map((c) => ({
        conveyor: c.conveyor,
        type: c.type,
        main_area: c.main_area,
        full: c.full,
        jam: c.jam,
        exit_pe: c.exit_pe,
      })),
      note: r.note,
    };
    $('autogen-detail').textContent = JSON.stringify(slim, null, 2);
  }
  autogenLog(
    `Preview OK — ${convN} conveyors from RUN`
    + (vfdN ? ` (${vfdN} VFD templates)` : ''),
    convN > 0 ? 'ok' : 'warn',
  );
});

$('btn-autogen-open-out')?.addEventListener('click', () => {
  // Prefer exports/current (authoritative engineer L5X folder)
  const out = autogenState.lastOut || '';
  if (out && typeof fortnaAPI.openPath === 'function') {
    fortnaAPI.openPath(out);
    autogenLog(`Open Output Folder: ${out}`, 'info');
  }
});
$('btn-autogen-open-l5x')?.addEventListener('click', async () => {
  // Reveal folder of the exact successful-build L5X — never shell-open .L5X (launches Studio)
  const l5x = autogenState.lastL5x;
  if (!l5x) {
    autogenLog('Open File Location: no exact L5X from last successful build (lastL5x empty)', 'warn');
    return;
  }
  if (/_LATEST\.L5X$/i.test(l5x)) {
    autogenLog(`Open File Location refused _LATEST path: ${l5x}`, 'warn');
    return;
  }
  const folder = l5x.replace(/[\\/][^\\/]+$/, '');
  if (folder && typeof fortnaAPI.openPath === 'function') {
    fortnaAPI.openPath(folder);
    autogenLog(`Open File Location (exact L5X): ${l5x}`, 'info');
    autogenLog(`Revealed folder: ${folder}`, 'info');
    autogenLog('Open the timestamped .L5X yourself in Studio (File → Open as new project).', 'info');
  }
});
$('btn-autogen-copy-l5x-path')?.addEventListener('click', async () => {
  const l5x = autogenState.lastL5x;
  if (!l5x) return;
  if (/_LATEST\.L5X$/i.test(l5x)) {
    autogenLog(`Copy Full Path refused _LATEST path: ${l5x}`, 'warn');
    return;
  }
  try {
    if (typeof fortnaAPI?.clipboardWriteText === 'function') {
      await fortnaAPI.clipboardWriteText(l5x);
    } else if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(l5x);
    } else {
      throw new Error('clipboard unavailable');
    }
    autogenLog(`Copied full path: ${l5x}`, 'ok');
  } catch (e) {
    autogenLog(`Copy failed: ${e?.message || e}`, 'err');
  }
});

// --- Ignition Build (layout + tag seed toward .gwbk) ---
const ignitionState = {
  lastOut: '',
  lastResult: null,
  busy: false,
  projectDir: '',
  testHtml: '',
};

function ignitionLog(msg, level = 'info') {
  const el = $('ignition-log');
  if (!el) return;
  const colors = { info: 'text-slate-400', ok: 'text-emerald-400', err: 'text-red-400', warn: 'text-amber-400' };
  const line = document.createElement('div');
  line.className = colors[level] || colors.info;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.prepend(line);
}

function setIgnitionStatus(text, kind) {
  const el = $('ignition-status');
  if (!el) return;
  el.textContent = text;
  el.className = `status-pill status-${kind || 'idle'} mt-3 text-[10px]`;
}

function renderIgnitionResult(r) {
  if (!r) return;
  ignitionState.lastResult = r;
  ignitionState.lastOut = r.out_dir || '';
  if ($('btn-ignition-open-out')) $('btn-ignition-open-out').disabled = !ignitionState.lastOut;

  const host = $('ignition-svg-host');
  if (host && r.svg) {
    host.innerHTML = r.svg;
  }

  const kinds = r.kind_counts || {};
  const eip = r.eip_summary || {};
  if ($('ignition-stats')) {
    $('ignition-stats').innerHTML = [
      ['Conveyors', r.physical_conveyor_count || r.plotted_count || 0],
      ['Equipment', r.equipment_count || 0],
      ['EIP adapters', eip.adapter_count || 0],
      ['EIP modules', eip.module_count || 0],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-orange-300 mono">${escapeHtml(String(v))}</div>
      </div>`).join('');
  }
  if ($('ignition-kind-list')) {
    const eipLines = (eip.adapters || []).slice(0, 12).map((a) =>
      `<div class="text-cyan-600/90">${escapeHtml(a.name || '')} · ${escapeHtml(a.ip || '')} · ${a.module_count || 0} mod</div>`
    ).join('');
    $('ignition-kind-list').innerHTML = (
      (eip.interface_ip ? `<div class="text-slate-400 mb-1">PLC ENET ${escapeHtml(eip.interface_ip)}</div>` : '')
      + eipLines
      + '<div class="mt-2 border-t border-slate-800 pt-2"></div>'
      + Object.entries(kinds)
        .map(([k, v]) => `<div><span class="text-slate-400">${escapeHtml(k)}</span> · ${v}</div>`)
        .join('')
    ) || '<div class="text-slate-600">—</div>';
  }
  if ($('ignition-detail')) {
    const files = r.files || {};
    $('ignition-detail').textContent = [
      r.gwbk_status || '',
      '',
      `PLC IP: ${r.plc_ip || (r.eip_summary && r.eip_summary.interface_ip) || '—'}`,
      `Tag CSV rows: ${r.tag_csv_rows || '—'}`,
      `Drawings drop: ${r.drawings_dir || 'workspace/drawings'}`,
      `Out: ${r.out_dir || ''}`,
      `layout.svg: ${files.layout_svg || ''}`,
      `layout_conveyors_only.svg: ${files.layout_conveyors_only_svg || ''}`,
      `tags_plc_aligned.json: ${files.tags_plc_aligned || ''}`,
      `tags_flat.csv: ${files.tags_flat_csv || ''}`,
      `opc_devices.json: ${files.opc_devices || ''}`,
      `eip_modules.json: ${files.eip_modules || ''}`,
      `DESIGNER_IMPORT.md: ${files.designer_readme || ''}`,
      `devices.json: ${files.devices || ''}`,
    ].join('\n');
  }
}

async function runIgnitionBuild(opts = {}) {
  if (ignitionState.busy) return;
  if (typeof fortnaAPI.ignitionBuildLayout !== 'function') {
    ignitionLog('API missing — relaunch Site Forge', 'warn');
    return;
  }
  ignitionState.busy = true;
  setIgnitionStatus('Building…', 'busy');
  ignitionLog('Building full site layout + tag seed from active RUN…', 'info');
  if ($('btn-ignition-build')) $('btn-ignition-build').disabled = true;
  let res;
  try {
    res = await fortnaAPI.ignitionBuildLayout({});
  } catch (e) {
    res = { success: false, message: e?.message || String(e) };
  }
  ignitionState.busy = false;
  if ($('btn-ignition-build')) $('btn-ignition-build').disabled = false;
  if (!res?.success) {
    setIgnitionStatus('Error', 'error');
    ignitionLog(res?.message || 'Build failed', 'err');
    return;
  }
  setIgnitionStatus('Ready', 'ready');
  const r = res.result || {};
  renderIgnitionResult(r);
  const proj = r.perspective_project || r.files?.perspective_project || '';
  ignitionState.projectDir = proj || ignitionState.projectDir;
  ignitionState.testHtml = r.files?.interactive_test_html
    || r.files?.poc_preview_html
    || (r.out_dir ? `${r.out_dir}\\interactive_test.html` : '');
  if ($('btn-ignition-open-project')) {
    $('btn-ignition-open-project').disabled = !ignitionState.projectDir;
  }
  if ($('btn-ignition-open-test')) {
    $('btn-ignition-open-test').disabled = !ignitionState.testHtml;
  }
  if (ignitionState.testHtml) {
    ignitionLog(`Interactive test: ${ignitionState.testHtml.split(/[/\\]/).pop()} — click Open interactive test`, 'info');
  }
  const dep = r.gateway_deploy;
  const stamp = r.folder_stamp || dep?.folder_stamp || '';
  const localT = r.generated_local || '';
  const projNm = r.project_name || dep?.project_name || '';
  if (dep?.ok) {
    ignitionLog(
      `Built ${stamp || ''} (${localT || 'now'}) → gateway project ${projNm || 'SiteForge_*'} `
      + `(${r.plotted_count || 0} plotted). Scan Filesystem → open Smoke_Test.`,
      'ok',
    );
  } else {
    ignitionLog(
      `Layout OK — stamp ${stamp || '—'} · ${r.plotted_count || 0} plotted`
      + (r.out_dir ? ` · ${r.out_dir}` : '')
      + (dep && !dep.ok ? ` · deploy: ${dep.error || 'failed'}` : ''),
      dep && !dep.ok ? 'warn' : 'ok',
    );
  }
  if ($('ignition-detail')) {
    $('ignition-detail').textContent = [
      '=== BUILD STAMP (track this folder) ===',
      `folder_stamp: ${stamp || '—'}`,
      `generated:    ${localT || '—'}`,
      `export:       ${r.out_dir || '—'}`,
      `project:      ${projNm || '—'}`,
      '',
      '=== GATEWAY ===',
      dep?.gatewayProject || '(not deployed)',
      dep?.ok ? 'Deploy: OK' : `Deploy: ${dep?.error || 'skipped'}`,
      '',
      '1) Gateway → Scan Filesystem',
      `2) Designer → open ${projNm || 'SiteForge_*'} → Smoke_Test first`,
      '3) Import tags_import.json from the export folder if needed',
      '',
      'Tip: exports/ignition-build/LATEST.txt always points at newest build.',
    ].join('\n');
  }
}

$('btn-ignition-build')?.addEventListener('click', () => runIgnitionBuild({}));
$('btn-ignition-refresh')?.addEventListener('click', () => runIgnitionBuild({}));
$('btn-ignition-open-out')?.addEventListener('click', () => {
  if (ignitionState.lastOut) fortnaAPI.openPath(ignitionState.lastOut);
});
$('btn-ignition-open-test')?.addEventListener('click', () => {
  const p = ignitionState.testHtml
    || (ignitionState.lastOut ? `${ignitionState.lastOut}\\interactive_test.html` : '');
  if (!p) {
    ignitionLog('No interactive_test.html yet — run Build first', 'warn');
    return;
  }
  // Open HTML in default browser (not Studio)
  if (typeof fortnaAPI.openPath === 'function') fortnaAPI.openPath(p);
  ignitionLog('Opened interactive test in browser — click belts / PEs to toggle', 'ok');
});
$('btn-ignition-perspective')?.addEventListener('click', async () => {
  if (typeof fortnaAPI.ignitionPackPerspective !== 'function') {
    ignitionLog('Pack API missing — relaunch Site Forge', 'warn');
    return;
  }
  setIgnitionStatus('Exporting…', 'busy');
  ignitionLog('Exporting Perspective project (P500 merge group + PE + tags)…', 'info');
  if ($('btn-ignition-perspective')) $('btn-ignition-perspective').disabled = true;
  let res;
  try {
    // Connected group: P440→P442→P444 + P542/P544 → P500 (merge). P522 not in RUN.
    res = await fortnaAPI.ignitionPackPerspective({
      nConv: 10,
      nPe: 12,
      conveyors: 'P440,P442,P444,P500,P542,P544,P540',
    });
  } catch (e) {
    res = { success: false, message: e?.message || String(e) };
  }
  if ($('btn-ignition-perspective')) $('btn-ignition-perspective').disabled = false;
  if (!res?.success) {
    setIgnitionStatus('Error', 'error');
    ignitionLog(res?.message || 'Perspective pack failed', 'err');
    return;
  }
  const r = res.result || {};
  const counts = r.instance_counts || {};
  const when = r.generated_local || r.folder_stamp || '';
  ignitionState.lastOut = r.out_dir || pathDir(r.project_dir || r.zip || '');
  ignitionState.projectDir = r.project_dir || '';
  if ($('btn-ignition-open-out')) $('btn-ignition-open-out').disabled = !ignitionState.lastOut;
  if ($('btn-ignition-open-project')) $('btn-ignition-open-project').disabled = !ignitionState.projectDir;
  setIgnitionStatus('Project ready', 'ready');
  ignitionLog(
    `Perspective export ${when} — ${counts.conveyors || 0} conv + ${counts.photoeyes || 0} PE`
    + (r.tags_import ? ' + tags_import.json' : '')
    + '. Copy project → Scan → Import tags from pack folder.',
    'ok',
  );
  if ($('ignition-detail')) {
    $('ignition-detail').textContent = [
      '=== COPY THIS TO IGNITION ===',
      `Generated: ${when}`,
      r.project_dir || '',
      '',
      '1) Copy SiteForge_POC →',
      '   C:\\Program Files\\Inductive Automation\\Ignition\\data\\projects\\',
      '2) Gateway → Platform → System → Projects → Scan Filesystem',
      '3) Designer → open SiteForge_POC → Views → SiteForge/POC/Plant_Layout',
      '4) Tag Browser (default) → right-click → Import Tags →',
      `   ${r.tags_import || '(tags_import.json in export folder)'}`,
      '   (Memory tags — toggle Run/Clear in Tag Browser to test colors)',
      '',
      `Counts: ${counts.conveyors || 0} conveyors, ${counts.photoeyes || 0} photoeyes`,
      `Devices: ${(r.device_names || []).join(', ')}`,
      `Zip: ${r.zip || ''}`,
      `Meta: ${r.export_meta || ''}`,
    ].join('\n');
  }
  if (ignitionState.lastOut) fortnaAPI.openPath(ignitionState.lastOut);
});

$('btn-ignition-open-project')?.addEventListener('click', () => {
  if (ignitionState.projectDir) fortnaAPI.openPath(ignitionState.projectDir);
});

function pathDir(p) {
  if (!p) return '';
  const s = String(p).replace(/[/\\]+$/, '');
  const i = Math.max(s.lastIndexOf('\\'), s.lastIndexOf('/'));
  return i > 0 ? s.slice(0, i) : s;
}

// Load banks/drives on startup when a RUN is already active
init().then(() => {
  if (state.workspace) refreshIoBanks();
  return initAutogenDefaults();
}).catch((e) => log(e.message, 'err'));

/* ===== GATE N — In-product Help drawer (manual-backed control map) ===== */
const SITE_FORGE_HELP = Object.freeze({
  sections: [
    { id: 'workflow', title: 'GATE O — Workflow', blurb: 'RUN Import → Auto Build → Canonical Model → Review/Correct → Apply → Autogen → PLC Compiler (Studio). Tabs edit the same project model.' },
    { id: 'io', title: 'I/O & Prints', blurb: 'Owns active RUN + HardwareIO Name/Generate overrides. Import triggers Transport silent Auto Build.' },
    { id: 'transport', title: 'Transport Build', blurb: 'Areas, topology, PE roles, ES zones. Apply to Autogen publishes IR; viewport Fit/Zoom are display-only.' },
    { id: 'safety', title: 'Safety Build', blurb: 'Safety Zone membership (≠ Area). Assign Devices / Rename / Apply Safety → workbook.safety_build.' },
    { id: 'sorter', title: 'Sorter Build', blurb: 'Induct/track/divert. Accept Derived / Edit / Commissioning. Apply sorter → Autogen.' },
    { id: 'sawtooth', title: 'Sawtooth Merge', blurb: 'Collector/lane merge from RUN SawLane. Apply sawtooth → Autogen.' },
    { id: 'autogen', title: 'PLC Autogen', blurb: 'Compile hub + Export L5X Package. Soft REVIEW does not hard-block; INCLUDED ERROR does.' },
    { id: 'tools', title: 'Docs / Workspace / Recipes', blurb: 'Secondary tools. Recipes mutate RUN tables; Workspace is alternate Import.' },
    { id: 'runtime', title: 'Runtime / Diagnostics', blurb: 'Git SHA, branch, source roots, mode. Copy Runtime Info. Feature self-check for Help, I/O ownership, VFD/IO_MAP classifiers. Latest site_forge log path + Reveal logs folder.' },
  ],
  workflow: [
    'RUN Import (.tar.gz)',
    'Auto Build (silent Transport layout)',
    'Canonical Engineering Model (all tabs)',
    'Review / Correct',
    'Apply (per subsystem → workbook)',
    'Autogen Export L5X',
    'Studio 5000 (manual open — app never launches Studio)',
  ],
  controls: {
    'btn-sf-help': { tab: 'Global', purpose: 'Open this Help drawer (manual sections + control map).' },
    'sf-runtime-sha': { tab: 'Global', purpose: 'Runtime provenance chip (short Git SHA). Opens Help → Runtime.' },
    'sf-help-copy-runtime': { tab: 'Global', purpose: 'Copy Runtime Info — provenance JSON + last diagnostics to clipboard.' },
    'sf-help-run-selfcheck': { tab: 'Global', purpose: 'Re-run feature self-check (Help drawer, I/O ownership renderer, VFD/IO_MAP classifiers).' },
    'sf-help-reveal-logs': { tab: 'Global', purpose: 'Reveal exports/logs folder (site_forge_*.log). No full log viewer.' },
    'sf-help-inspect': { tab: 'Global', purpose: 'Inspect next control click — maps control id to SITE_FORGE_HELP purpose.' },
    'btn-io-browse-run': { tab: 'I/O', purpose: 'Load RUN .tar.gz — sets active workspace; triggers Transport Auto Build.' },
    'btn-io-clear-run': { tab: 'I/O', purpose: 'Clear loaded RUN presentation / related state.' },
    'hw-io-panel-select': { tab: 'I/O', purpose: 'Filter Hardware CAD by Control Panel (display).' },
    'hw-io-rio-select': { tab: 'I/O', purpose: 'Filter Hardware CAD by Remote I/O (display).' },
    'btn-add-remote': { tab: 'I/O', purpose: 'Add remote panel name for print OCR.' },
    'btn-browse-remote-prints': { tab: 'I/O', purpose: 'Browse panel PDFs for OCR.' },
    'btn-io-clear-prints': { tab: 'I/O', purpose: 'Clear panel PDFs and OCR/crosswalk results.' },
    'btn-run-ocr': { tab: 'I/O', purpose: 'OCR prints vs tar.gz banks — diagnostic; does not rewrite Autogen.' },
    'btn-refresh-banks': { tab: 'I/O', purpose: 'Refresh I/O banks from active RUN.' },
    'tb-connect-mode': { tab: 'Transport', purpose: 'Connect mode: wire EXIT → ENTRY (authoritative topology when committed).' },
    'tb-fit': { tab: 'Transport', purpose: 'Fit System — viewport only (TOP-CENTER). Display-only.' },
    'tb-fit-system': { tab: 'Transport', purpose: 'Fit System (same as Fit). Display-only.' },
    'tb-zoom-out': { tab: 'Transport', purpose: 'Zoom out (viewport center). Display-only.' },
    'tb-zoom-in': { tab: 'Transport', purpose: 'Zoom in (viewport center). Display-only.' },
    'tb-home': { tab: 'Transport', purpose: 'Home — reset zoom/pan. Display-only.' },
    'tb-zoom-100': { tab: 'Transport', purpose: 'Reset view to 100% zoom. Display-only.' },
    'tb-geometry-mode': { tab: 'Transport', purpose: 'Geometry authority: RUN/Physical · Engineering Override · Diagnostic.' },
    'tb-undo': { tab: 'Transport', purpose: 'Undo canvas edit (Ctrl+Z). Restores areas/selection; save().' },
    'tb-redo': { tab: 'Transport', purpose: 'Redo canvas edit (Ctrl+Y).' },
    'tb-bulk-apply': { tab: 'Transport', purpose: 'Apply Area / ES to selection — provenance ENGINEER. Local until Apply to Autogen.' },
    'tb-bulk-create-area': { tab: 'Transport', purpose: 'Create Area from Selection (name prompt — never inferred from geometry).' },
    'tb-bulk-add-to-area': { tab: 'Transport', purpose: 'Add Selection to an existing Area.' },
    'tb-bulk-remove-from-area': { tab: 'Transport', purpose: 'Remove Selection from Area → Default Area (ownership bucket).' },
    'tb-bulk-chain': { tab: 'Transport', purpose: 'Select Chain — expand selection via connected wires (display).' },
    'tb-bulk-terminal': { tab: 'Transport', purpose: 'Mark Terminal on selection (authoritative topology).' },
    'tb-apply-autogen': { tab: 'Transport', purpose: 'Apply to Autogen — publish topology/Area/ES/PE into workbook. Ignores viewport/layers.' },
    'tb-goto-build-plc': { tab: 'Transport', purpose: 'Build PLC — jump to PLC Autogen Export (navigation).' },
    'tb-auto-build-run': { tab: 'Transport', purpose: 'Rebuild Layout from RUN — equipment lands in Default Area (Site Forge ownership; not RUN provenance).' },
    'tb-area-new': { tab: 'Transport', purpose: 'Create engineer Area (Default Area remains the residual ownership bucket).' },
    'tb-area-delete-btn': { tab: 'Transport', purpose: 'Delete engineer Area — members return to Default Area (cannot delete Default).' },
    'tb-area-delete': { tab: 'Transport', purpose: 'Delete engineer Area — members return to Default Area (cannot delete Default).' },
    'sb-refresh': { tab: 'Safety', purpose: 'Refresh discovery — rebuild Safety model; keep engineer overrides.' },
    'sb-apply': { tab: 'Safety', purpose: 'Apply Safety — write safety_build into workbook (merge-safe).' },
    'sb-rename-zone': { tab: 'Safety', purpose: 'Rename engineering_name only; RUN source_id stays immutable.' },
    'btn-divert-accept-derived': { tab: 'Sorter', purpose: 'Accept All Derived divert PE → ENGINEER_ACCEPTED. Never UNKNOWN→PROVEN.' },
    'btn-divert-apply-pe': { tab: 'Sorter', purpose: 'Apply PE value to selected divert rows.' },
    'btn-divert-mark-commission': { tab: 'Sorter', purpose: 'Mark selected divert PE as COMMISSIONING.' },
    'btn-sorter-save': { tab: 'Sorter', purpose: 'Apply sorter → Autogen workbook; hub READY or REVIEW_REQUIRED.' },
    'btn-sorter-clear': { tab: 'Sorter', purpose: 'Clear sorter fields and reset readiness.' },
    'btn-saw-save': { tab: 'Sawtooth', purpose: 'Apply sawtooth → Autogen workbook; hub READY or REVIEW_REQUIRED.' },
    'btn-saw-reload-sitemodel': { tab: 'Sawtooth', purpose: 'Reload from SiteModel/RUN — discards local edits.' },
    'btn-saw-clear': { tab: 'Sawtooth', purpose: 'Clear sawtooth config.' },
    'btn-autogen-from-run': { tab: 'Autogen', purpose: 'Export L5X Package (Build PLC). Writes exports; does not launch Studio.' },
    'btn-autogen-workbook-build': { tab: 'Autogen', purpose: 'Refresh site config from RUN (keeps edits).' },
    'btn-autogen-workbook-save': { tab: 'Autogen', purpose: 'Save Autogen workbook to disk.' },
    'btn-hub-from-transport': { tab: 'Autogen', purpose: 'Pull Transport Build graph into Autogen workbook.' },
    'btn-hub-save-transport-wb': { tab: 'Autogen', purpose: 'Save Autogen workbook to disk.' },
    'btn-clear-project-builds': { tab: 'Autogen', purpose: 'Clear current project builds (not libraries/docs/fixtures).' },
    'btn-browse-archive': { tab: 'Workspace', purpose: 'Browse RUN archive (alternate Import).' },
    'btn-clear-workspace': { tab: 'Workspace', purpose: 'Clear workspace extract (workbook kept by design).' },
    'btn-apply': { tab: 'Recipes', purpose: 'Apply selected recipe to RUN tables (not Autogen workbook Apply).' },
    'btn-reindex': { tab: 'Docs', purpose: 'Reindex documentation for search.' },
  },
});

function sfHelpSetOpen(open) {
  const drawer = $('sf-help-drawer');
  const backdrop = $('sf-help-backdrop');
  if (!drawer) return;
  const on = !!open;
  drawer.dataset.open = on ? '1' : '0';
  drawer.setAttribute('aria-hidden', on ? 'false' : 'true');
  if (backdrop) {
    backdrop.dataset.open = on ? '1' : '0';
    backdrop.setAttribute('aria-hidden', on ? 'false' : 'true');
  }
  if (!on) {
    const insp = $('sf-help-inspect');
    if (insp) insp.checked = false;
    document.body.classList.remove('sf-help-inspect');
  }
}

function sfHelpShowControl(id, meta) {
  const detail = $('sf-help-detail');
  if (!detail) return;
  const m = meta || SITE_FORGE_HELP.controls[id];
  if (!m) {
    detail.classList.remove('hidden');
    detail.innerHTML = `<div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Control</div>
      <div class="mono text-cyan-200">#${escapeHtml(id || '—')}</div>
      <div class="text-slate-500 mt-1">No help entry yet — see docs/SITE_FORGE_ENGINEERING_UI_MANUAL.md</div>`;
    return;
  }
  detail.classList.remove('hidden');
  detail.innerHTML = `<div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">${escapeHtml(m.tab || 'Control')}</div>
    <div class="mono text-cyan-200">#${escapeHtml(id)}</div>
    <div class="text-slate-300 mt-1 leading-relaxed">${escapeHtml(m.purpose || '')}</div>`;
}

function sfHelpRenderLists(filter) {
  const q = String(filter || '').trim().toLowerCase();
  const secHost = $('sf-help-sections');
  const ctlHost = $('sf-help-controls');
  const wfHost = $('sf-help-workflow');
  if (wfHost && !wfHost.dataset.ready) {
    wfHost.innerHTML = SITE_FORGE_HELP.workflow.map((s) => `<li>${escapeHtml(s)}</li>`).join('');
    wfHost.dataset.ready = '1';
  }
  if (secHost) {
    secHost.innerHTML = SITE_FORGE_HELP.sections
      .filter((s) => !q || s.title.toLowerCase().includes(q) || s.blurb.toLowerCase().includes(q))
      .map((s) => `<li class="rounded-lg border border-slate-800 bg-[#0a1018] px-2 py-1.5">
        <div class="text-cyan-200/90 font-medium">${escapeHtml(s.title)}</div>
        <div class="text-slate-500 leading-relaxed mt-0.5">${escapeHtml(s.blurb)}</div>
      </li>`).join('') || '<li class="text-slate-600">No sections match</li>';
  }
  if (ctlHost) {
    const entries = Object.entries(SITE_FORGE_HELP.controls)
      .filter(([id, m]) => !q
        || id.toLowerCase().includes(q)
        || (m.tab || '').toLowerCase().includes(q)
        || (m.purpose || '').toLowerCase().includes(q));
    ctlHost.innerHTML = entries.map(([id, m]) =>
      `<li><button type="button" class="sf-help-ctl w-full text-left rounded-lg border border-slate-800 hover:border-cyan-800/50 bg-[#0a1018] px-2 py-1.5"
        data-help-id="${escapeHtml(id)}">
        <div class="flex gap-2 items-baseline"><span class="mono text-cyan-300/90 text-[10px]">#${escapeHtml(id)}</span>
          <span class="text-[9px] text-slate-600 uppercase">${escapeHtml(m.tab || '')}</span></div>
        <div class="text-slate-400 leading-snug mt-0.5">${escapeHtml(m.purpose || '')}</div>
      </button></li>`).join('') || '<li class="text-slate-600">No controls match</li>';
    ctlHost.querySelectorAll('.sf-help-ctl').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-help-id') || '';
        sfHelpShowControl(id);
        const el = id ? document.getElementById(id) : null;
        if (el) {
          try {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList?.add?.('ring-2', 'ring-cyan-500/60');
            setTimeout(() => el.classList?.remove?.('ring-2', 'ring-cyan-500/60'), 1400);
          } catch (_) { /* ignore */ }
        }
      });
    });
  }
}

/** Runtime provenance + Gate 2 feature self-check (exercise real functions). */
let _sfRuntimeProvenance = null;
let _sfFeatureSelfCheck = null;

function formatRuntimeProvenanceLines(p) {
  const rows = [
    ['Git SHA', p?.gitSha || 'unknown'],
    ['Branch', p?.branch || 'unknown'],
    ['Started', p?.startedAt || 'unknown'],
    ['Repo / source root', p?.sourceRoot || p?.repoRoot || 'unknown'],
    ['Dashboard source', p?.dashboardSource || 'unknown'],
    ['Python / compiler', `${p?.pythonSource || 'unavailable'} · ${p?.compilerSource || 'unknown'}`],
    ['Mode', p?.mode || 'dev'],
    ['Provenance source', p?.provenanceSource || 'unknown'],
    ['Executable', p?.executable || ''],
    ['CWD', p?.cwd || ''],
  ];
  return rows
    .filter(([, v]) => v !== '')
    .map(([k, v]) => `<div><span class="text-slate-600">${escapeHtml(k)}:</span> <span class="text-slate-300 break-all">${escapeHtml(String(v))}</span></div>`)
    .join('');
}

function updateRuntimeShaChip(p) {
  const chip = $('sf-runtime-sha');
  if (!chip) return;
  const short = p?.gitShaShort || (p?.gitSha && String(p.gitSha).slice(0, 7)) || 'sha?';
  const branch = p?.branch || '?';
  chip.textContent = short;
  chip.title = `Runtime ${short} @ ${branch} — Help → Runtime`;
}

async function loadRuntimeProvenance(force) {
  if (_sfRuntimeProvenance && !force) return _sfRuntimeProvenance;
  const api = window.fortnaAPI;
  if (api?.getRuntimeProvenance) {
    try {
      const res = await api.getRuntimeProvenance();
      _sfRuntimeProvenance = res?.provenance || res || null;
    } catch (e) {
      _sfRuntimeProvenance = { gitSha: 'unavailable', branch: 'unavailable', error: String(e?.message || e) };
    }
  } else {
    _sfRuntimeProvenance = {
      gitSha: 'browser-only',
      gitShaShort: 'n/a',
      branch: 'n/a',
      mode: 'browser',
      startedAt: new Date().toISOString(),
      provenanceSource: 'unavailable',
      note: 'fortnaAPI.getRuntimeProvenance not available (non-Electron)',
    };
  }
  updateRuntimeShaChip(_sfRuntimeProvenance);
  const host = $('sf-help-runtime');
  if (host) host.innerHTML = formatRuntimeProvenanceLines(_sfRuntimeProvenance);
  return _sfRuntimeProvenance;
}

/**
 * Gate 2 — exercise live functions (not source-string greps).
 * - Help drawer DOM
 * - hwChannelEndpointLabel(UNRESOLVED_OWNER) → "UNRESOLVED OWNER"
 * - classifyDevice VFD/IO_MAP symbol rules
 * - optional Python classify_cp_io_operand via IPC
 */
async function runSiteForgeFeatureSelfCheck() {
  const checks = [];

  const drawer = document.getElementById('sf-help-drawer');
  const helpBtn = document.getElementById('btn-sf-help');
  checks.push({
    id: 'help_drawer',
    ok: !!(drawer && helpBtn),
    detail: drawer && helpBtn
      ? '#sf-help-drawer + #btn-sf-help present'
      : 'missing #sf-help-drawer and/or #btn-sf-help',
  });

  try {
    const ep = hwChannelEndpointLabel({ owner_state: 'UNRESOLVED_OWNER' });
    const ok = ep
      && ep.text === 'UNRESOLVED OWNER'
      && ep.ownerState === 'UNRESOLVED_OWNER'
      && ep.kind === 'warn';
    checks.push({
      id: 'io_ownership_renderer',
      ok: !!ok,
      detail: `hwChannelEndpointLabel(UNRESOLVED_OWNER) → "${ep?.text}" (${ep?.ownerState}/${ep?.kind})`,
    });
  } catch (e) {
    checks.push({
      id: 'io_ownership_renderer',
      ok: false,
      detail: String(e?.message || e),
    });
  }

  try {
    const vfd = classifyDevice('VFD500A');
    const conv = classifyDevice('P100');
    const fltName = classifyDevice('VFD216_FLT');
    const ok = vfd.key === 'vfd' && conv.key === 'conveyor' && vfd.key === 'vfd';
    // VFD###_FLT still classifies as VFD family for device browser
    const fltOk = fltName.key === 'vfd';
    checks.push({
      id: 'vfd_symbol_classifier',
      ok: !!(ok && fltOk),
      detail: `classifyDevice VFD500A→${vfd.key}; P100→${conv.key}; VFD216_FLT→${fltName.key}`,
    });
  } catch (e) {
    checks.push({
      id: 'vfd_symbol_classifier',
      ok: false,
      detail: String(e?.message || e),
    });
  }

  const api = window.fortnaAPI;
  if (api?.runtimeFeatureSelfCheck) {
    try {
      const py = await api.runtimeFeatureSelfCheck();
      for (const c of py?.checks || []) checks.push(c);
    } catch (e) {
      checks.push({
        id: 'vfd_iomap_symbol_classifier_py',
        ok: false,
        detail: String(e?.message || e),
      });
    }
  } else {
    checks.push({
      id: 'vfd_iomap_symbol_classifier_py',
      ok: false,
      detail: 'IPC runtimeFeatureSelfCheck unavailable (non-Electron)',
    });
  }

  _sfFeatureSelfCheck = {
    ok: checks.every((c) => c.ok),
    checks,
    at: new Date().toISOString(),
  };
  const host = $('sf-help-diagnostics');
  if (host) {
    const badge = _sfFeatureSelfCheck.ok
      ? '<span class="text-emerald-400">PASS</span>'
      : '<span class="text-amber-400">FAIL</span>';
    host.innerHTML = `<div class="mb-1">${badge} · ${escapeHtml(_sfFeatureSelfCheck.at)}</div>`
      + checks.map((c) =>
        `<div><span class="${c.ok ? 'text-emerald-400' : 'text-amber-400'}">${c.ok ? '✓' : '✗'}</span> `
        + `<span class="text-slate-500">${escapeHtml(c.id)}:</span> `
        + `<span class="text-slate-300">${escapeHtml(c.detail || '')}</span></div>`).join('');
  }
  loadSiteForgeLogInfo().catch(() => {});
  return _sfFeatureSelfCheck;
}

/** Gate 7 — show latest site_forge_*.log path (no full viewer). */
let _sfLogInfo = null;

async function loadSiteForgeLogInfo() {
  const host = $('sf-help-logs');
  const api = window.fortnaAPI;
  if (!api?.listLatestLog && !api?.getLogsDir) {
    _sfLogInfo = { path: null, logsDir: 'exports/logs', note: 'IPC unavailable (non-Electron)' };
    if (host) {
      host.innerHTML = `<div class="text-slate-500">Latest log: n/a (non-Electron)</div>`
        + `<div class="text-slate-600">Folder: exports/logs</div>`;
    }
    return _sfLogInfo;
  }
  try {
    const latest = api.listLatestLog ? await api.listLatestLog() : null;
    const dirRes = (!latest?.logsDir && api.getLogsDir) ? await api.getLogsDir() : null;
    const logsDir = latest?.logsDir || dirRes?.path || 'exports/logs';
    const logPath = latest?.path || null;
    _sfLogInfo = { path: logPath, logsDir, count: latest?.count || 0 };
    if (host) {
      host.innerHTML = `<div><span class="text-slate-500">Latest log:</span> `
        + `<span class="text-slate-300 break-all">${escapeHtml(logPath || '(none yet)')}</span></div>`
        + `<div><span class="text-slate-500">Folder:</span> `
        + `<span class="text-slate-300 break-all">${escapeHtml(logsDir)}</span></div>`;
    }
  } catch (e) {
    _sfLogInfo = { path: null, error: String(e?.message || e) };
    if (host) {
      host.innerHTML = `<div class="text-amber-400">Log path unavailable: ${escapeHtml(String(e?.message || e))}</div>`;
    }
  }
  return _sfLogInfo;
}

async function revealSiteForgeLogsFolder() {
  const api = window.fortnaAPI;
  let dir = _sfLogInfo?.logsDir;
  try {
    if (!dir && api?.getLogsDir) {
      const r = await api.getLogsDir();
      dir = r?.path;
    }
  } catch (_) { /* fall through */ }
  dir = dir || 'exports/logs';
  try {
    if (api?.openPath) {
      await api.openPath(dir);
    }
  } catch (e) {
    console.warn('Reveal logs folder failed', e);
  }
}

async function copyRuntimeInfo() {
  const p = await loadRuntimeProvenance();
  const diag = _sfFeatureSelfCheck || await runSiteForgeFeatureSelfCheck();
  const payload = JSON.stringify({ provenance: p, diagnostics: diag }, null, 2);
  try {
    if (window.fortnaAPI?.clipboardWriteText) {
      await window.fortnaAPI.clipboardWriteText(payload);
    } else if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(payload);
    }
  } catch (e) {
    console.warn('Copy Runtime Info failed', e);
  }
}

function initSiteForgeHelp() {
  const openBtn = $('btn-sf-help');
  if (!openBtn || openBtn.dataset.helpBound) return;
  openBtn.dataset.helpBound = '1';
  openBtn.addEventListener('click', () => {
    sfHelpRenderLists($('sf-help-filter')?.value || '');
    sfHelpSetOpen(true);
    loadRuntimeProvenance();
    runSiteForgeFeatureSelfCheck();
    loadSiteForgeLogInfo();
  });
  $('sf-runtime-sha')?.addEventListener('click', () => {
    sfHelpRenderLists($('sf-help-filter')?.value || '');
    sfHelpSetOpen(true);
    loadRuntimeProvenance();
    runSiteForgeFeatureSelfCheck();
    loadSiteForgeLogInfo();
    $('sf-help-runtime')?.scrollIntoView?.({ block: 'nearest' });
  });
  $('sf-help-close')?.addEventListener('click', () => sfHelpSetOpen(false));
  $('sf-help-backdrop')?.addEventListener('click', () => sfHelpSetOpen(false));
  $('sf-help-filter')?.addEventListener('input', (ev) => sfHelpRenderLists(ev.target.value));
  $('sf-help-inspect')?.addEventListener('change', (ev) => {
    document.body.classList.toggle('sf-help-inspect', !!ev.target.checked);
  });
  $('sf-help-copy-runtime')?.addEventListener('click', () => { copyRuntimeInfo(); });
  $('sf-help-run-selfcheck')?.addEventListener('click', () => { runSiteForgeFeatureSelfCheck(); });
  $('sf-help-reveal-logs')?.addEventListener('click', () => { revealSiteForgeLogsFolder(); });
  document.addEventListener('click', (ev) => {
    if (!$('sf-help-inspect')?.checked) return;
    if (ev.target.closest?.('#sf-help-drawer') || ev.target.closest?.('#btn-sf-help')) return;
    const hit = ev.target.closest?.('[id]');
    if (!hit || !hit.id) return;
    ev.preventDefault();
    ev.stopPropagation();
    sfHelpShowControl(hit.id);
    $('sf-help-inspect').checked = false;
    document.body.classList.remove('sf-help-inspect');
    if ($('sf-help-drawer')?.dataset.open !== '1') {
      sfHelpRenderLists($('sf-help-filter')?.value || '');
      sfHelpSetOpen(true);
    }
  }, true);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && $('sf-help-drawer')?.dataset.open === '1') sfHelpSetOpen(false);
  });
  // Expose classifiers for diagnostics / window API self-check
  window.SiteForgeDiagnostics = {
    classifyDevice,
    hwChannelEndpointLabel,
    runFeatureSelfCheck: runSiteForgeFeatureSelfCheck,
    getRuntimeProvenance: () => _sfRuntimeProvenance,
    getLastSelfCheck: () => _sfFeatureSelfCheck,
    getLogInfo: () => _sfLogInfo,
    loadLogInfo: loadSiteForgeLogInfo,
  };
  loadRuntimeProvenance().catch(() => {});
  loadSiteForgeLogInfo().catch(() => {});
}

try { initSiteForgeHelp(); } catch (e) { console.warn('Site Forge Help init failed', e); }