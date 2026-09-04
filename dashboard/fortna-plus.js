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
const ALL_TABS = ['search', 'workspace', 'io', 'recipes', 'plc', 'autogen', 'ignition', 'transport', 'sorter', 'sawtooth'];

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
  if (tab === 'sorter') {
    try { renderSorterBuild(); } catch (_) { /* ignore */ }
    try { updateSorterSummary(); } catch (_) { /* ignore */ }
  }
  if (tab === 'sawtooth') {
    try { renderSawtoothBuild(); } catch (_) { /* ignore */ }
    try { updateSawtoothSummary(); } catch (_) { /* ignore */ }
  }
}

/** PLC Autogen compile hub — status from Transport Apply + Sorter Save */
function refreshAutogenCompileHub() {
  const tEl = $('autogen-hub-transport');
  const sEl = $('autogen-hub-sorter');
  const wEl = $('autogen-hub-workbook');
  const merges = autogenState.merges_2to1 || [];
  const wb = autogenState.workbook;
  const tbRows = (wb?.conveyors || []).filter((r) => r && (r.transport_build || r.source === 'transport_build_graph'));
  let hasTransportGraph = false;
  try {
    const raw = localStorage.getItem('siteforge.transportBuild.v1');
    if (raw) {
      const data = JSON.parse(raw);
      hasTransportGraph = Array.isArray(data.areas) && data.areas.some((a) => (a.nodes || []).length);
    }
  } catch (_) { /* ignore */ }
  if (tEl) {
    tEl.textContent = merges.length || tbRows.length
      ? `${tbRows.length} transport row(s) · ${merges.length} merge(s)`
      : (hasTransportGraph ? 'Graph on Transport Build — Apply when ready' : 'Empty — open Transport Build');
  }
  const s = autogenState.sorter || {};
  const trackN = Number(s.tracking_count || 0);
  const divertN = Number(s.divert_count || 0);
  const stype = s.sorter_type === 'shoe_sorter' ? 'shoe' : (s.sorter_type === 'popup_divert' ? 'popup' : '');
  const hasSorter = !!(s.induct_conveyor || trackN || divertN || stype);
  if (sEl) {
    sEl.textContent = hasSorter
      ? `${stype || 'type?'} · induct ${s.induct_conveyor || '—'} · track ${trackN} · divert ${divertN}`
      : 'Empty — open Sorter Build';
  }
  const saw = autogenState.sawtooth || {};
  const sawEl = $('autogen-hub-sawtooth');
  const hasSaw = !!saw.collector_conveyor;
  if (sawEl) {
    const ln = Number(saw.lane_count || (saw.lanes || []).length || 0);
    const enc = saw.collector_has_encoder === 'no'
      ? 'NO_Enc'
      : (saw.collector_encoder || 'enc?');
    sawEl.textContent = hasSaw
      ? `Collector ${saw.collector_conveyor} · enc ${enc} · ${ln} lane(s) · MRG${saw.mrg_id || '—'}`
      : 'Empty — open Sawtooth Merge';
  }
  const convN = (wb?.conveyors || []).filter((r) => r?.include !== false).length;
  if (wEl) {
    wEl.textContent = convN
      ? `${convN} conveyor(s) · ${(wb.areas || []).length || '—'} area(s)`
      : 'Empty — load RUN to build site config';
  }
  // Show Apply/Save only when there is something to apply
  const showTransportActions = hasTransportGraph || tbRows.length > 0 || merges.length > 0;
  $('autogen-hub-transport-actions')?.classList.toggle('hidden', !showTransportActions);
  $('autogen-hub-empty-hint')?.classList.toggle(
    'hidden',
    !!(convN || hasTransportGraph || hasSorter || hasSaw || merges.length)
  );
}

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
    ioState.drives = [];
    ioState.devices = [];
    ioState.motorChains = [];
    ioState.printVfdParams = [];
    ioState.selectedDriveName = '';
    ioState.deviceTypeFilter = 'all';
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
async function importRunPackage(path, name) {
  if (!path) return false;
  if (typeof fortnaAPI?.importRun !== 'function') {
    const msg = 'Site Forge API missing — relaunch via Launch-SiteForge.bat (not a browser tab).';
    log(msg, 'err');
    setIoRunStatus(msg, 'error');
    return false;
  }
  setBusy(true);
  setIoRunStatus(`Importing ${name || 'archive'}…`, 'busy');
  setStatus('workspace-status', 'Importing…', 'busy');
  log(`Importing ${name || path}…`, 'info');
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
  if (!res || !res.success) {
    log(res?.message || 'Import failed', 'err');
    setStatus('workspace-status', 'Import failed', 'error');
    setIoRunStatus(res?.message || 'Import failed', 'error');
    return false;
  }
  state.workspace = res.meta;
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
    return;
  }
  if ($('io-banks-status')) {
    $('io-banks-status').textContent = 'Loading…';
    $('io-banks-status').className = 'status-pill status-busy';
  }
  const res = await fortnaAPI.getIoBanks();
  renderIoBanks(res);
}

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
  wbTab: 'conveyors',
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
};

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
    induct_conveyor: '',
    induct_pe: '',
    induct_has_encoder: 'no',
    induct_encoder_type: 'Enc_RIOCard',
    induct_encoder_tag: '',
    tracking_count: 0,
    tracking: [],
    divert_count: 0,
    tracking_pe_count: 0,
    tracking_pes: [],
  };
}

function defaultSawtoothConfig() {
  return {
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
  };
}

function normalizeSawLaneRow(row) {
  const r = { ...emptySawLaneRow(), ...(row || {}) };
  r.has_encoder = (r.has_encoder === 'yes' || r.has_encoder === true) ? 'yes' : 'no';
  if (!['Enc_RIOCard', 'Enc_CounterCard', 'Enc_Virtual_DistBased'].includes(r.encoder_type)) {
    r.encoder_type = 'Enc_RIOCard';
  }
  r.encoder_tag = r.encoder_tag || r.enc_tag || '';
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
  return [...new Set(names)].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
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
  if (s.induct_conveyor) bits.push(`induct ${s.induct_conveyor}`);
  if (s.tracking_count) bits.push(`${s.tracking_count} track`);
  if (s.divert_count) bits.push(`${s.divert_count} divert`);
  if (s.tracking_pe_count) bits.push(`${s.tracking_pe_count} PE`);
  const encN = (s.tracking || []).filter((t) => t && t.has_encoder === 'yes').length
    + (s.induct_has_encoder === 'yes' ? 1 : 0);
  if (encN) bits.push(`${encN} enc`);
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
  const convs = conveyorNameList();
  const pes = photoeyeNameList();
  const encs = encoderNameList();

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
        return `<div class="rounded-lg border border-slate-800/80 bg-[#0a1016] p-2 space-y-1.5" data-track-i="${i}">
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-[10px] text-slate-600 w-6 mono">#${i + 1}</span>
            <select class="sorter-track-conv flex-1 min-w-[9rem] bg-[#101820] border border-slate-700 rounded-lg px-2 py-1 text-[10px] mono text-slate-200" data-i="${i}">
              <option value="">Tracking conveyor…</option>${convOpts}
            </select>
            <select class="sorter-track-pe flex-1 min-w-[9rem] bg-[#101820] border border-slate-700 rounded-lg px-2 py-1 text-[10px] mono text-sky-300" data-i="${i}">
              <option value="">Tracking photoeye…</option>${peOpts}
            </select>
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

  trackCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(40, parseInt(trackCount.value, 10) || 0));
    trackCount.value = String(n);
    autogenState.sorter.tracking_count = n;
    const arr = (autogenState.sorter.tracking || []).map(normalizeSorterTrackRow);
    while (arr.length < n) arr.push(emptySorterTrackRow());
    autogenState.sorter.tracking = arr.slice(0, n);
    renderSorterBuild();
  });
  divertCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(64, parseInt(divertCount.value, 10) || 0));
    divertCount.value = String(n);
    autogenState.sorter.divert_count = n;
    updateSorterSummary();
  });
  peCount?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(64, parseInt(peCount.value, 10) || 0));
    peCount.value = String(n);
    autogenState.sorter.tracking_pe_count = n;
    const arr = autogenState.sorter.tracking_pes || [];
    while (arr.length < n) arr.push('');
    autogenState.sorter.tracking_pes = arr.slice(0, n);
    renderSorterBuild();
  });
  inductC?.addEventListener('change', () => {
    autogenState.sorter.induct_conveyor = inductC.value || '';
    updateSorterSummary();
  });
  inductP?.addEventListener('change', () => {
    autogenState.sorter.induct_pe = inductP.value || '';
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
    updateSorterSummary();
  });
  inductEncType?.addEventListener('change', () => {
    autogenState.sorter.induct_encoder_type = inductEncType.value || 'Enc_RIOCard';
    updateSorterSummary();
  });
  inductEncTag?.addEventListener('change', () => {
    autogenState.sorter.induct_encoder_tag = inductEncTag.value || '';
    updateSorterSummary();
  });

  $('sorter-type')?.addEventListener('change', () => {
    autogenState.sorter.sorter_type = $('sorter-type').value || '';
    updateSorterSummary();
  });

  $('btn-sorter-save')?.addEventListener('click', async () => {
    if ($('sorter-type')) autogenState.sorter.sorter_type = $('sorter-type').value || '';
    persistSorterToWorkbook();
    const st = $('sorter-save-status');
    // Auto-enable Program pack · Sorter Track when config has real content
    const s = autogenState.sorter || {};
    const hasData = !!(
      s.induct_conveyor
      || (s.tracking_count || 0) > 0
      || (s.divert_count || 0) > 0
      || (s.tracking || []).some((t) => t && t.conveyor)
      || s.sorter_type
    );
    if (hasData) {
      const pack = $('autogen-opt-sorter-track');
      if (pack && !pack.checked) {
        pack.checked = true;
        autogenLog('Saved sorter config → checked Program pack · Sorter Track for next generate.', 'ok');
      }
      if (s.sorter_type === 'shoe_sorter' && $('autogen-opt-shippingsorter')) {
        $('autogen-opt-shippingsorter').checked = true;
        autogenLog('Shoe Sorter → checked ShippingSorter (Shoe) pack.', 'ok');
      }
      if (s.sorter_type === 'popup_divert' && $('autogen-opt-shippingsorter-popup')) {
        $('autogen-opt-shippingsorter-popup').checked = true;
        autogenLog('Pop-Up Divert → checked ShippingSorter (PopUp) pack.', 'ok');
      }
    }
    try {
      if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
        await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
      }
      // Always mirror to localStorage for demo safety
      try {
        localStorage.setItem('fortna_sorter_build', JSON.stringify(autogenState.sorter));
      } catch (_) { /* ignore */ }
      if (st) {
        st.textContent = hasData ? 'Saved · Sorter Track pack ON' : 'Saved';
        st.className = 'text-[10px] text-emerald-500 mono';
      }
      autogenLog('Sorter build config saved (workbook + localStorage).', 'ok');
    } catch (e) {
      if (st) { st.textContent = 'Save failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Sorter save failed: ${e?.message || e}`, 'err');
    }
  });
  $('btn-sorter-clear')?.addEventListener('click', () => {
    autogenState.sorter = defaultSorterConfig();
    persistSorterToWorkbook();
    renderSorterBuild();
    const st = $('sorter-save-status');
    if (st) { st.textContent = 'Cleared'; st.className = 'text-[10px] text-slate-500 mono'; }
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
  const s = autogenState.sawtooth || {};
  const n = Number(s.lane_count || (s.lanes || []).length || 0);
  const enc = s.collector_has_encoder === 'no'
    ? 'NO_Enc'
    : (s.collector_encoder || 'enc?');
  const laneEnc = (s.lanes || []).filter((l) => l && l.has_encoder === 'yes').length;
  el.textContent = s.collector_conveyor
    ? `${s.collector_conveyor} · enc ${enc} · ${n} lane(s)${laneEnc ? ` · ${laneEnc} lane-enc` : ''} · MRG${s.mrg_id || '?'}`
    : 'no config';
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
  if ($('saw-area-name')) $('saw-area-name').value = s.area_name || '';
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

  const n = Math.max(1, Math.min(12, Number(s.lane_count) || 4));
  s.lane_count = n;
  while ((s.lanes || []).length < n) s.lanes.push(emptySawLaneRow());
  s.lanes = (s.lanes || []).slice(0, n).map((l) => normalizeSawLaneRow(l));

  const host = $('saw-lane-rows');
  if (host) {
    host.innerHTML = s.lanes.map((lane, i) => {
      const showEnc = lane.has_encoder === 'yes';
      return `
      <div class="rounded-lg border border-slate-800 bg-[#070b12] p-2 space-y-2" data-saw-lane="${i}">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Lane ${i + 1} conveyor</label>
            <select data-saw-field="conveyor" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-slate-200"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Lane PE</label>
            <select data-saw-field="pe" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Jam PE</label>
            <select data-saw-field="jam_pe" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300"></select>
          </div>
          <div>
            <label class="block text-[9px] text-slate-500 mb-0.5">Merge-point PE</label>
            <select data-saw-field="merge_pe" class="w-full bg-[#101820] border border-slate-700 rounded px-1.5 py-1 text-[10px] mono text-sky-300"></select>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-2 border-t border-slate-800/80 pt-2">
          <div>
            <label class="block text-[9px] text-amber-600/90 mb-0.5">Lane encoder?</label>
            <select data-saw-field="has_encoder" class="w-full bg-[#101820] border border-amber-900/40 rounded px-1.5 py-1 text-[10px] text-slate-200">
              <option value="no" ${lane.has_encoder !== 'yes' ? 'selected' : ''}>No → NO_Enc</option>
              <option value="yes" ${lane.has_encoder === 'yes' ? 'selected' : ''}>Yes</option>
            </select>
          </div>
          <div class="${showEnc ? '' : 'hidden'}" data-saw-enc-opts>
            <label class="block text-[9px] text-amber-600/90 mb-0.5">Encoder type</label>
            <select data-saw-field="encoder_type" class="w-full bg-[#101820] border border-amber-900/40 rounded px-1.5 py-1 text-[10px] text-slate-200">
              ${sorterEncTypeOptionsHtml(lane.encoder_type || 'Enc_RIOCard')}
            </select>
          </div>
          <div class="${showEnc ? '' : 'hidden'}" data-saw-enc-opts>
            <label class="block text-[9px] text-amber-600/90 mb-0.5">Encoder tag</label>
            <select data-saw-field="encoder_tag" class="w-full bg-[#101820] border border-amber-900/40 rounded px-1.5 py-1 text-[10px] mono text-amber-200/90">
              ${sorterEncTagOptionsHtml(lane.encoder_tag || '', encFallback)}
            </select>
          </div>
        </div>
      </div>`;
    }).join('');
    host.querySelectorAll('[data-saw-lane]').forEach((row) => {
      const i = Number(row.dataset.sawLane);
      const lane = s.lanes[i] || emptySawLaneRow();
      row.querySelectorAll('[data-saw-field]').forEach((sel) => {
        const field = sel.dataset.sawField;
        if (field === 'conveyor') fillSawSelect(sel, convs, lane.conveyor || '');
        else if (field === 'pe' || field === 'jam_pe' || field === 'merge_pe') {
          fillSawSelect(sel, pes, lane[field] || '');
        } else if (field === 'has_encoder') {
          sel.value = lane.has_encoder === 'yes' ? 'yes' : 'no';
        } else if (field === 'encoder_type') {
          sel.value = lane.encoder_type || 'Enc_RIOCard';
        } else if (field === 'encoder_tag') {
          // already painted via sorterEncTagOptionsHtml
          if (lane.encoder_tag) sel.value = lane.encoder_tag;
        }
        sel.addEventListener('change', () => {
          s.lanes[i] = normalizeSawLaneRow(s.lanes[i] || emptySawLaneRow());
          if (field === 'has_encoder') {
            s.lanes[i].has_encoder = sel.value === 'yes' ? 'yes' : 'no';
            renderSawtoothBuild();
            return;
          }
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

  $('saw-lane-count')?.addEventListener('change', () => {
    const n = Math.max(1, Math.min(12, parseInt($('saw-lane-count').value, 10) || 4));
    autogenState.sawtooth.lane_count = n;
    renderSawtoothBuild();
  });
  $('saw-track-pe-count')?.addEventListener('change', () => {
    const n = Math.max(0, Math.min(16, parseInt($('saw-track-pe-count').value, 10) || 0));
    autogenState.sawtooth.track_pe_count = n;
    renderSawtoothBuild();
  });
  const bind = (id, fn) => $(id)?.addEventListener('change', fn);
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
  bind('saw-collector-enc', () => { autogenState.sawtooth.collector_encoder = $('saw-collector-enc').value || ''; updateSawtoothSummary(); });
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
    renderSawtoothBuild();
    const st = $('saw-save-status');
    if (st) { st.textContent = 'PLC4 example filled — review then Save'; st.className = 'text-[10px] text-amber-400 mono'; }
  });

  $('btn-saw-save')?.addEventListener('click', async () => {
    persistSawtoothToWorkbook();
    const s = autogenState.sawtooth || {};
    const hasData = !!(s.collector_conveyor || (s.lanes || []).some((l) => l && l.conveyor));
    if (hasData && $('autogen-opt-sawtooth')) {
      $('autogen-opt-sawtooth').checked = true;
      autogenLog('Saved sawtooth config → checked Program pack · Sawtooth Merge.', 'ok');
    }
    try {
      if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
        await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
      }
      try { localStorage.setItem('fortna_sawtooth_build', JSON.stringify(autogenState.sawtooth)); } catch (_) { /* ignore */ }
      const st = $('saw-save-status');
      if (st) { st.textContent = hasData ? 'Saved · Sawtooth pack ON' : 'Saved'; st.className = 'text-[10px] text-emerald-500 mono'; }
      updateSawtoothSummary();
      autogenLog('Sawtooth merge config saved.', 'ok');
    } catch (e) {
      const st = $('saw-save-status');
      if (st) { st.textContent = 'Save failed'; st.className = 'text-[10px] text-red-400 mono'; }
      autogenLog(`Sawtooth save failed: ${e?.message || e}`, 'err');
    }
  });

  $('btn-saw-clear')?.addEventListener('click', () => {
    autogenState.sawtooth = defaultSawtoothConfig();
    persistSawtoothToWorkbook();
    renderSawtoothBuild();
    const st = $('saw-save-status');
    if (st) { st.textContent = 'Cleared'; st.className = 'text-[10px] text-slate-500 mono'; }
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
  await buildAutogenWorkbook();
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
        // Keep safety zone in sync with area when area changes
        const base = (sel.value || '').replace(/_Area$/i, '');
        if (base) {
          const sz = `${base}_ESZone1`;
          wb.conveyors[i].safety_zone = sz;
          if (!safetyOpts.includes(sz)) safetyOpts.push(sz);
          if (wb.options) {
            wb.options.safety_zones = safetyOpts;
            if (!wb.options.areas.includes(sel.value)) wb.options.areas.push(sel.value);
          }
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
}

function switchWbTab(tab) {
  autogenState.wbTab = tab || 'conveyors';
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

async function buildAutogenWorkbook() {
  if (typeof fortnaAPI.autogenWorkbookBuild !== 'function') {
    autogenLog('Workbook API missing — relaunch Site Forge desktop app', 'warn');
    return;
  }
  if (autogenState.busy) return;
  autogenState.busy = true;
  setAutogenStatus('Building workbook…', 'busy');
  autogenLog('Building AutoGen workbook from active RUN (Inputdata auto-fill)…', 'info');
  let res;
  try {
    res = await fortnaAPI.autogenWorkbookBuild({ mergeExisting: true });
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
  const s = r.stats || {};
  autogenLog(
    `Site config ready — ${s.conveyor_count || 0} conveyors, ${s.io_mapped || 0}/${s.io_point_count || 0} IO mapped, `
    + `${s.area_count || 0} areas. Use dropdowns for Area/Safety/TYPE/Exit PE, set program pack, then Generate PLC Project.`,
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
  switchWbTab('conveyors');
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
  const sz = `${area.replace(/_Area$/i, '')}_ESZone1`;
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
    if (!wb.options.safety_zones.includes(sz)) wb.options.safety_zones.push(sz);
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
  // Program pack: Sys + optional IO_MAP (RUN banks) + site sorter/WCS
  const includePrograms = [];
  // ShippingSorter (Shoe Sorter) still maps to existing gold program; PopUp Divert is UI placeholder
  if ($('autogen-opt-shippingsorter')?.checked) includePrograms.push('ShippingSorter_Area_L3');
  if ($('autogen-opt-shippingsorter-popup')?.checked) {
    includePrograms.push('ShippingSorter_PopUp_Divert');
    autogenLog('ShippingSorter (PopUp Divert) selected — pack mapping TBD (no L5X merge yet).', 'warn');
  }
  if ($('autogen-opt-wcs')?.checked) includePrograms.push('WCS_Interface_TCP_IP');
  if ($('autogen-opt-sawtooth')?.checked) includePrograms.push('Sawtooth_Merge');
  // Merges → workbook.merges_2to1 (emitted when pack checkbox on)
  const mergeOn = !!$('autogen-opt-merges-2to1')?.checked;
  const mergeRows = (autogenState.merges_2to1 || []).filter((m) => m && (m.name || m.lane_a));
  const merge2 = mergeRows.filter((m) => (Number(m.lanes) || 2) <= 2);
  const merge3 = mergeRows.filter((m) => (Number(m.lanes) || 2) >= 3);
  if (mergeOn && mergeRows.length) {
    persistMergesToWorkbook();
    autogenLog(
      `Merge ON — ${mergeRows.length} configured (${merge2.length}× 2:1 emit, ${merge3.length}× 3+:1 saved for later)`,
      'ok',
    );
    if (merge3.length) {
      autogenLog('3:1+ merges are stored in the workbook; L5X scaffold still emits 2:1 only.', 'warn');
    }
  } else if (mergeRows.length && !mergeOn) {
    autogenLog('Merge rows present but Merge pack is OFF — not emitting Conv_Merge.', 'warn');
  } else if (mergeOn && !mergeRows.length) {
    autogenLog('Merge pack ON but no merge rows — set count in the Merge panel.', 'warn');
  }
  const sorterCfg = autogenState.sorter || defaultSorterConfig();
  const sorterConfigured = !!(
    sorterCfg.induct_conveyor
    || (sorterCfg.tracking_count || 0) > 0
    || (sorterCfg.divert_count || 0) > 0
    || (sorterCfg.tracking || []).some((t) => t && (t.conveyor || t.has_encoder === 'yes'))
  );
  // Sorter Track pack: checkbox OR auto-on when Sorter build has real data
  // (good automation — user still sees the box flip on so it's visible)
  let sorterTrackChecked = !!$('autogen-opt-sorter-track')?.checked;
  if (sorterConfigured && !sorterTrackChecked) {
    const el = $('autogen-opt-sorter-track');
    if (el) el.checked = true;
    sorterTrackChecked = true;
    autogenLog(
      'Sorter build has data → auto-checked Program pack · Sorter Track (emits Sorter_Track_Program).',
      'ok',
    );
  }
  if (sorterTrackChecked) includePrograms.push('Sorter_Track');
  if (sorterConfigured) {
    persistSorterToWorkbook();
    const encYes = (sorterCfg.tracking || []).filter((t) => t && t.has_encoder === 'yes').length
      + (sorterCfg.induct_has_encoder === 'yes' ? 1 : 0);
    autogenLog(
      `Sorter build: induct=${sorterCfg.induct_conveyor || '—'} · `
      + `track=${sorterCfg.tracking_count || 0} · diverts=${sorterCfg.divert_count || 0} · encYes=${encYes}`,
      'info',
    );
  }
  if (sorterTrackChecked && !sorterConfigured) {
    autogenLog(
      'Sorter Track pack ON — Sorter build panel empty (full gold pack, no site renames).',
      'warn',
    );
  }
  const noSys = !($('autogen-opt-sys')?.checked ?? true);
  // IO_MAP checkbox: checked = include RUN bank map; unchecked = omit IO_MAP from L5X
  const includeIoMap = !!($('autogen-opt-iomap')?.checked ?? true);
  // System program routines (independent of Sys constants pack)
  // Device Comms checkbox includes NTP (cookie-cutter) in the same pack.
  const wantDeviceComms =
    !!($('autogen-opt-system')?.checked ?? $('autogen-opt-device-comms')?.checked ?? true);
  const wantNtp = wantDeviceComms; // NTP rides with Device Comms
  const wantSystemLogic = !!($('autogen-opt-system-logic')?.checked ?? true);
  if (wantDeviceComms) {
    includePrograms.push('Devices_Comm');
    includePrograms.push('NTP');
  }
  if (wantSystemLogic) includePrograms.push('System_Logic');
  // Back-compat token so older exporters still emit the System program shell
  if (wantDeviceComms || wantSystemLogic) includePrograms.push('System');
  const packBits = [];
  if (!noSys) packBits.push('Sys');
  if (wantDeviceComms) packBits.push('DeviceComms+NTP');
  if (wantSystemLogic) packBits.push('SystemLogic');
  packBits.push(includeIoMap ? 'IO_MAP(RUN banks→RIO)' : 'IO_MAP(off)');
  const packExtra = includePrograms.filter(
    (p) => !['System', 'Devices_Comm', 'NTP', 'System_Logic'].includes(p)
  );
  if (packExtra.length) packBits.push(...packExtra);
  autogenLog(`Program pack: ${packBits.join(' + ')}`, 'info');

  // Disk workbook is source of truth for Transport Apply (areas/stubs/merges).
  // Do NOT save in-memory workbook over disk here — that previously wiped MERGE5 stubs
  // and left Conv_Fast with only P55.
  if (mode === 'run' && typeof fortnaAPI.autogenWorkbookLoad === 'function') {
    try {
      const full = await fortnaAPI.autogenWorkbookLoad();
      if (full?.success && full.workbook) {
        const disk = full.workbook;
        autogenState.workbook = disk;
        if (Array.isArray(disk.merges_2to1)) autogenState.merges_2to1 = disk.merges_2to1;
        const stubNames = (disk.conveyors || [])
          .filter((r) => r && (r.transport_build || r.source === 'transport_build_graph'))
          .map((r) => r.conveyor)
          .filter(Boolean);
        const mergeN = Array.isArray(disk.merges_2to1) ? disk.merges_2to1.length : 0;
        if (stubNames.length || mergeN) {
          autogenLog(
            `Transport workbook on disk: ${stubNames.length} stub/bound row(s)`
              + (stubNames.length ? ` [${stubNames.slice(0, 12).join(', ')}${stubNames.length > 12 ? '…' : ''}]` : '')
              + (mergeN ? ` · ${mergeN} merge(s)` : ''),
            'ok',
          );
        }
        try { if (typeof renderWorkbook === 'function') renderWorkbook(); } catch (_) { /* ignore */ }
      }
    } catch (_) { /* keep memory workbook */ }
  }

  let res;
  try {
    res = await fortnaAPI.autogenGenerate({
      mode,
      excel: excel || undefined,
      library: library || undefined,
      includePrograms,
      noSys,
      includeIoMap,
      noIoMap: !includeIoMap,
      // Path only — Electron resolves stable workspace/autogen_workbook.json.
      // Avoids passing a stale in-memory object that overwrites Transport Apply.
      workbook: undefined,
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
    if (/no active run/i.test(msg)) {
      autogenLog('Tip: I/O & Prints → Load RUN .tar.gz first, wait until machine status is ready, then Generate PLC Project.', 'warn');
    }
    autogenLog('Tip: click Verify engine — if a recent L5X exists under exports/autogen, generation may have succeeded on disk.', 'warn');
    return;
  }
  const r = res.result || {};
  const rep = r.report || {};
  autogenState.lastOut = r.out_dir || '';
  autogenState.lastL5x = r.l5x || '';
  setAutogenStatus(r.recovered ? 'Complete (recovered)' : 'Complete', 'ready');
  if ($('autogen-summary')) {
    $('autogen-summary').innerHTML = `
      <div class="space-y-1 text-sm">
        <div class="text-emerald-400 font-semibold">
          L5X package exported${mode === 'run' ? ' (site config + RUN)' : ' (legacy Excel)'}
          ${r.recovered ? ' <span class="text-amber-400 text-xs">(recovered from disk)</span>' : ''}
          <span class="block text-[10px] text-slate-500 font-normal mt-0.5">Studio not launched — use Show L5X / Out when you want the files</span>
        </div>
        <div class="mono text-xs text-slate-400 break-all">${escapeHtml(r.l5x || '')}</div>
        <div class="text-xs text-slate-500">${escapeHtml(rep.note || r.note || '')}</div>
      </div>`;
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
    $('autogen-detail').textContent = JSON.stringify(rep, null, 2);
  }
  if ($('btn-autogen-open-out')) $('btn-autogen-open-out').disabled = !autogenState.lastOut;
  if ($('btn-autogen-open-l5x')) $('btn-autogen-open-l5x').disabled = !autogenState.lastL5x;
  autogenLog(
    `Done (Python) — ${rep.conveyor_count || 0} conveyors, ${rep.tag_count || 0} tags, `
    + `${rep.program_count || 0} programs`
    + (r.l5x_bytes ? ` · ${(r.l5x_bytes / 1024 / 1024).toFixed(1)} MB L5X` : ''),
    'ok',
  );
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
        const raw = localStorage.getItem('siteforge.transportBuild.v1');
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
 * Full project wipe: site-config table + Transport/Sorter/Sawtooth + merges + prints + workbook file.
 * Does not delete the original .tar.gz on disk; clears in-app Autogen state so you start empty.
 */
async function clearProjectBuilds() {
  const ok = confirm(
    'Clear ALL project builds (start empty)?\n\n'
    + 'This will wipe:\n'
    + '• Site config table — Conveyors / IO map / Areas / Report\n'
    + '• workspace/autogen_workbook.json on disk\n'
    + '• Transport Build areas and PE role selections\n'
    + '• Sawtooth + Sorter configs and merge rows\n'
    + '• Panel prints + OCR / merge-crosswalk results\n'
    + '• Program-pack checkboxes\n\n'
    + 'You will need to load a RUN again to refill the table.\n'
    + 'This cannot be undone from the UI. Continue?'
  );
  if (!ok) return;

  const ok2 = confirm(
    'Final warning: wipe site config + Transport / Sawtooth / Sorter / merges / prints now?'
  );
  if (!ok2) return;

  try {
    if (typeof window.transportBuildClearAll === 'function') {
      window.transportBuildClearAll();
    } else {
      try { localStorage.removeItem('siteforge.transportBuild.v1'); } catch (_) { /* ignore */ }
    }
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
    // Core packs stay recommended-on after a full wipe (user can uncheck)

    // Wipe entire Autogen workbook (conveyors / IO / areas / report) and persist empty file
    const emptyWb = {
      version: 1,
      kind: 'fortna_autogen_workbook',
      generated_utc: new Date().toISOString(),
      source: 'cleared',
      site: '',
      conveyors: [],
      io_map: [],
      areas: [],
      merges_2to1: [],
      options: { areas: [], safety_zones: [], exit_pe: [], types: [] },
      stats: { conveyor_count: 0, io_mapped: 0 },
      type_counts: {},
    };
    autogenState.workbook = emptyWb;
    autogenState.selected = new Set();
    if (typeof fortnaAPI?.autogenWorkbookSave === 'function') {
      await fortnaAPI.autogenWorkbookSave({ workbook: emptyWb });
    }
    try { setWorkbook(emptyWb); } catch (_) {
      try { renderWorkbook(); } catch (__) { /* ignore */ }
    }

    if ($('autogen-summary')) {
      $('autogen-summary').innerHTML =
        'Cleared — load a <strong class="text-slate-300">.tar.gz</strong> on I/O &amp; Prints to refill site config.';
    }
    if ($('autogen-stats')) {
      $('autogen-stats').classList.add('hidden');
      $('autogen-stats').innerHTML = '';
    }
    if ($('autogen-wb-count')) $('autogen-wb-count').textContent = '0 rows';
    if ($('autogen-detail')) $('autogen-detail').textContent = '—';
    setAutogenStatus('Cleared', 'idle');

    try {
      clearIoCompareState({ clearPanels: true });
    } catch (_) { /* ignore */ }

    refreshAutogenCompileHub();
    autogenLog('Project cleared — site config + Transport / Sorter / Sawtooth / merges / prints wiped.', 'ok');
  } catch (e) {
    autogenLog(`Clear project builds failed: ${e?.message || e}`, 'err');
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
  const st = $('merge-save-status');
  if (st) {
    st.textContent = `Transport: ${nAreas} area(s), ${nConv} conv, ${n} merge(s)`;
    st.className = 'text-[10px] text-emerald-500 mono';
  }
  if (typeof autogenLog === 'function') {
    autogenLog(
      `Transport Build → Autogen: ${res.summary || `${nAreas} areas / ${n} merges`} `
      + `(${res.workbook_path || 'workbook saved'}). `
      + `Simple transport follows area names; check Merge pack if merges present, then Generate.`,
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
        const raw = localStorage.getItem('siteforge.transportBuild.v1');
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
  if (autogenState.lastOut) fortnaAPI.openPath(autogenState.lastOut);
});
$('btn-autogen-open-l5x')?.addEventListener('click', async () => {
  // Reveal folder only — never shell-open the .L5X (that launches Studio 5000)
  const l5x = autogenState.lastL5x;
  if (!l5x) return;
  const folder = l5x.replace(/[\\/][^\\/]+$/, '');
  if (folder && typeof fortnaAPI.openPath === 'function') {
    fortnaAPI.openPath(folder || autogenState.lastOut || l5x);
    autogenLog(`L5X folder: ${folder || autogenState.lastOut}`, 'info');
    autogenLog('Open the .L5X yourself in Studio when ready (File → Open as new project).', 'info');
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