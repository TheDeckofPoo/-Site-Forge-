/* FortnaPlus Control — dashboard frontend */

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
const ALL_TABS = ['search', 'workspace', 'io', 'recipes', 'plc', 'autogen', 'ignition'];

// Tabs
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    ALL_TABS.forEach((t) => {
      const pane = $(`tab-${t}`);
      if (pane) pane.classList.toggle('hidden', t !== tab);
    });
    if (tab === 'recipes') renderRecipeList();
    if (tab === 'io') {
      // Reload banks from RUN, then re-apply any OCR print params (don't wipe PRINT column)
      refreshIoBanks().then(() => {
        if (ioState.ocrResult) mergeOcrPrintParamsIntoDrives(ioState.ocrResult);
      }).catch(() => {});
    }
  });
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
  setBusy(true);
  setIoRunStatus(`Importing ${name || 'archive'}…`, 'busy');
  setStatus('workspace-status', 'Importing…', 'busy');
  log(`Importing ${name || path}…`, 'info');
  const res = await fortnaAPI.importRun(path);
  setBusy(false);
  if (!res.success) {
    log(res.message || 'Import failed', 'err');
    setStatus('workspace-status', 'Import failed', 'error');
    setIoRunStatus(res.message || 'Import failed', 'error');
    return false;
  }
  state.workspace = res.meta;
  if ($('drop-filename')) {
    $('drop-filename').textContent = name || path.split(/[/\\]/).pop();
    $('drop-filename').classList.remove('hidden');
  }
  const devCount = res.meta.device_count || res.meta.devices?.length || 0;
  const machine = res.meta.machine || 'RUN';
  log(`Loaded ${machine} — ${devCount} devices`, 'ok');
  setStatus('workspace-status', `${machine} loaded`, 'ready');
  setIoRunStatus(`${machine} loaded · ${devCount} devices`, 'ready');
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
  return true;
}

$('btn-clear-workspace')?.addEventListener('click', async () => {
  if (!confirm('Clear active workspace?\n\nThis removes the imported RUN from FortnaPlus (workspace/active).\nOriginal .tar.gz files on D:\\ are not deleted.')) {
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
    if (results[0].result?.files?.l5x) fortnaAPI.openPath(results[0].result.files.l5x);
  } else {
    renderPlcBatchSummary(results);
    // Open exports/plc root after batch
    fortnaAPI.openPath('exports/plc');
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
  if (res.result?.files?.l5x) fortnaAPI.openPath(res.result.files.l5x);
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

/** Resolve electrical drawing page for a device name (ASC Print #). */
function resolveDevicePrintPage(name, fallback) {
  if (fallback != null && fallback !== '' && Number(fallback) > 0) {
    return Number(fallback);
  }
  const map = ioState.banks?.print_pages || ioState.printPages || {};
  if (!name) return null;
  const hit = map[name] ?? map[String(name).toUpperCase()] ?? map[String(name).toLowerCase()];
  if (hit != null && Number(hit) > 0) return Number(hit);
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
      const page = resolveDevicePrintPage(
        name,
        p.drawing_page || p.print_page || null,
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
        is_vfd: false,
        vfd_from_print: false,
      });
    }
  }
  for (const d of ioState.drives || []) {
    const name = d.name || '';
    if (!name) continue;
    const key = name.toUpperCase();
    const type = classifyDevice(name, d.equipment_kind || d.device_type || d.device_class, d);
    const existing = byName.get(key);
    const cleanedPrint = filterVfdPrintParamsClient(
      d.print_param_list || Object.values(d.print_params || {}),
    );
    const page = resolveDevicePrintPage(
      name,
      d.drawing_page || d.print_page || existing?.drawing_page || null,
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
      print_params: d.print_params || {},
      print_sources: d.print_sources || [],
      program_params: d.program_params || {},
      drawing_page: page,
      print_file: d.print_file || existing?.print_file || '',
      print_page: page,
      // is_vfd only for real VFD### names — never P### conveyors
      is_vfd: type.key === 'vfd' || (/^VFD/i.test(name) && !/^P\d/i.test(name)),
      vfd_from_print: !!d.vfd_from_print && type.key === 'vfd',
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
  const hasMaster = typeof getMasterPanel === 'function' ? !!getMasterPanel() : false;
  const hasOcr = !!(ioState.ocrResult?.crosswalk);
  const matchN = ioState.ocrResult?.crosswalk?.matched_count || 0;
  const ready = hasRun && hasPrints && hasMaster;

  const list = $('plc-ready-checklist');
  if (list) {
    const row = (ok, text) =>
      `<div class="${ok ? 'text-emerald-400' : 'text-slate-500'}">${ok ? '✓' : '○'} ${text}</div>`;
    list.innerHTML = [
      row(hasRun, `RUN tar.gz loaded${ioState.banks?.machine ? ` (${ioState.banks.machine})` : state.workspace?.machine ? ` (${state.workspace.machine})` : ''}`),
      row(hasMaster, 'Master panel set'),
      row(hasPrints, `Print PDFs assigned (${printFiles} file${printFiles === 1 ? '' : 's'})`),
      row(hasOcr, hasOcr ? `OCR compare done (${matchN} matches)` : 'OCR compare not run yet (optional for export)'),
    ].join('');
  }

  const btn = $('btn-plc-generate');
  if (btn) {
    btn.disabled = !ready || plcState.busy;
    if (ready && !plcState.busy) {
      btn.className = 'w-full py-3 rounded-xl text-sm font-semibold border-2 border-emerald-500 bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/40 cursor-pointer transition';
      btn.innerHTML = '<i class="fa-solid fa-industry mr-2"></i>Generate Studio 5000 + Factory I/O';
      btn.title = 'Export complete L5X + Factory I/O from active RUN';
    } else {
      btn.className = 'w-full py-3 rounded-xl text-sm font-semibold border-2 border-slate-700 bg-slate-900 text-slate-500 cursor-not-allowed';
      btn.innerHTML = '<i class="fa-solid fa-industry mr-2"></i>Generate Studio 5000 + Factory I/O';
      btn.title = 'Load tar.gz + assign prints first';
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

  if (remoteCount) remoteCount.textContent = `${remotes.length} remote${remotes.length === 1 ? '' : 's'}`;

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
    $('btn-run-ocr').disabled = ioState.busy || totalPrintFiles() === 0 || !getMasterPanel();
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
      msg = 'Drive list failed to load — relaunch FortnaPlus and click refresh.';
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

  // Index OCR drive print params by base name
  const byBase = new Map();
  for (const d of ocrDrives) {
    const b = baseName(d.base_name || d.name);
    if (!b) continue;
    const prev = byBase.get(b) || { print_param_list: [], print_sources: [], print_params: {} };
    const list = [...(prev.print_param_list || []), ...(d.print_param_list || [])];
    const sources = [...new Set([...(prev.print_sources || []), ...(d.print_sources || [])])];
    byBase.set(b, {
      print_param_list: list,
      print_sources: sources,
      print_params: { ...(prev.print_params || {}), ...(d.print_params || {}) },
      print_param_count: list.length || Object.keys(d.print_params || {}).length,
      vfd_from_print: !!(d.vfd_from_print || d.print_param_count),
    });
  }
  // Free-floating print VFD params: prefer per-param device_id (title-block OCR),
  // else Device_ID entries on the same source file (PowerFlex tables on drawings).
  const cleanVfdId = (v) => {
    let id = String(v || '').replace(/[_\s\-]/g, '').toUpperCase();
    id = id.replace(/(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$/i, '');
    if (!id) return '';
    if (!id.startsWith('VFD')) id = `VFD${id}`;
    return /^VFD[A-Z0-9]{1,8}$/i.test(id) ? id : '';
  };

  const idsByFile = new Map(); // file -> Set of VFD ids
  for (const p of printVfd) {
    if ((p.param || '') === 'Device_ID' && p.value) {
      const id = cleanVfdId(p.value);
      if (!id) continue;
      const f = p.source || p.file || '_';
      if (!idsByFile.has(f)) idsByFile.set(f, new Set());
      idsByFile.get(f).add(id);
      if (!byBase.has(id)) {
        byBase.set(id, { print_param_list: [], print_sources: [], print_params: {}, print_param_count: 0 });
      }
    }
    // device_id stamped on param rows during OCR
    if (p.device_id) {
      const id = cleanVfdId(p.device_id);
      if (id && !byBase.has(id)) {
        byBase.set(id, { print_param_list: [], print_sources: [], print_params: {}, print_param_count: 0 });
      }
    }
  }
  for (const p of printVfd) {
    if ((p.param || '') === 'Device_ID') continue;
    const f = p.source || p.file || '_';
    const fromParam = p.device_id ? cleanVfdId(p.device_id) : '';
    const ids = fromParam
      ? [fromParam]
      : (idsByFile.get(f) && idsByFile.get(f).size
        ? [...idsByFile.get(f)]
        : []);
    for (const id of ids) {
      if (!id || !/^VFD/i.test(id)) continue;
      const prev = byBase.get(id) || { print_param_list: [], print_sources: [], print_params: {} };
      prev.print_param_list = [...(prev.print_param_list || []), p];
      prev.print_params[p.param || 'param'] = p;
      prev.print_param_count = prev.print_param_list.length;
      prev.vfd_from_print = true;
      if (f && f !== '_') prev.print_sources = [...new Set([...(prev.print_sources || []), f])];
      byBase.set(id, prev);
    }
  }

  let merged = 0;
  const matchedIds = new Set();
  for (const d of ioState.drives || []) {
    const b = baseName(d.base_name || d.name);
    const bNorm = cleanVfdId(b) || b;
    const hit = byBase.get(b) || byBase.get(bNorm) || byBase.get(cleanVfdId(d.name));
    if (!hit || !(hit.print_param_count || hit.print_param_list?.length)) continue;
    const cleaned = filterVfdPrintParamsClient(hit.print_param_list || Object.values(hit.print_params || {}));
    if (!cleaned.length) continue;
    d.print_params = Object.fromEntries(cleaned.map((p) => [p.param, p]));
    d.print_param_list = cleaned;
    d.print_param_count = cleaned.length;
    d.print_sources = hit.print_sources || d.print_sources || [];
    d.vfd_from_print = true;
    // Capture print file/page for repository click-through
    for (const p of cleaned) {
      if (p.page != null && d.print_page == null) d.print_page = p.page;
      if (p.source && !d.print_file) d.print_file = p.source;
    }
    if (!d.drawing_page && d.print_page) d.drawing_page = d.print_page;
    // Only reclassify as VFD when the device name is a VFD tag (not P### conveyor)
    if ((/^VFD\d/i.test(b) || /^VFD\d/i.test(bNorm)) && !/^P\d/i.test(b)) {
      d.is_vfd = true;
      d.equipment_kind = 'vfd';
    }
    matchedIds.add(bNorm || b);
    merged += 1;
  }

  // Print-only VFDs (on drawings, not in tar.gz under same tag) — still show in Devices
  // so PRINT column is never blank when OCR found real PowerFlex tables.
  let addedPrintOnly = 0;
  for (const [id, hit] of byBase.entries()) {
    if (!/^VFD/i.test(id)) continue;
    if (!(hit.print_param_count || hit.print_param_list?.length)) continue;
    if (matchedIds.has(id)) continue;
    const already = (ioState.drives || []).some((d) => {
      const b = cleanVfdId(baseName(d.base_name || d.name)) || baseName(d.base_name || d.name);
      return b === id;
    });
    if (already) continue;
    const cleaned = filterVfdPrintParamsClient(hit.print_param_list || Object.values(hit.print_params || {}));
    if (!cleaned.length) continue;
    ioState.drives.push({
      name: id,
      base_name: id,
      device_type: 'VFD',
      equipment_kind: 'vfd',
      is_vfd: true,
      vfd_from_print: true,
      from_print_only: true,
      description: 'From electrical prints (not in tar.gz under this tag)',
      program_params: {},
      print_params: Object.fromEntries(cleaned.map((p) => [p.param, p])),
      print_param_list: cleaned,
      print_param_count: cleaned.length,
      print_sources: hit.print_sources || [],
      print_file: cleaned[0]?.source || (hit.print_sources || [])[0] || '',
      print_page: cleaned.find((p) => p.page != null)?.page || null,
      drawing_page: cleaned.find((p) => p.page != null)?.page || null,
    });
    addedPrintOnly += 1;
  }

  ioState.printVfdParams = printVfd;
  rebuildDeviceList();
  const withPrint = (ioState.drives || []).filter((d) => (d.print_param_count || 0) > 0).length;
  if ($('io-drives-status')) {
    $('io-drives-status').textContent =
      `${ioState.drives.length} rows · ${withPrint} w/ print params`;
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
      ['With print params', withPrint],
      ['Print VFD hits', printVfd.length || 0],
    ].map(([k, v]) => `
      <div class="bg-[#101820] border border-slate-800 rounded-lg px-2 py-2 text-center">
        <div class="text-[10px] text-slate-500">${k}</div>
        <div class="text-sm font-semibold text-cyan-300 mono">${v}</div>
      </div>`).join('');
  }
  if (merged > 0 || addedPrintOnly > 0) {
    ioLog(
      `Merged print params into ${merged} tar.gz device(s)`
      + (addedPrintOnly ? ` + ${addedPrintOnly} print-only VFD(s)` : '')
      + ` — ${withPrint} device(s) now have PRINT parameters.`,
      'ok',
    );
  } else {
    ioLog(
      `OCR finished but PRINT column is still empty (0 VFD matches). `
      + `Extracted ${printVfd.length} raw print param(s). `
      + `Re-run OCR after relaunch (reads all ~80 pages + PowerFlex tables + title-block VFD tags).`,
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
    'Clear loaded RUN from FortnaPlus?\n\n'
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
    ocrBtn.disabled = totalPrintFiles() === 0 || !getMasterPanel();
    ocrBtn.innerHTML = ocrBtnHtml || '<i class="fa-solid fa-code-merge mr-2"></i>OCR · merge remotes → master · vs tar.gz';
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
};

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
  renderWorkbook();
}

function renderWorkbook() {
  const wb = autogenState.workbook;
  const tbody = $('autogen-wb-tbody');
  const ioBody = $('autogen-wb-io-tbody');
  const countEl = $('autogen-wb-count');
  const typeBar = $('autogen-wb-type-bar');
  const areasEl = $('autogen-wb-areas');
  if (!wb) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-6 px-3 text-slate-500 text-center">Build workbook from RUN to fill this table (like Excel Inputdata).</td></tr>';
    }
    if (countEl) countEl.textContent = '0 rows';
    if (typeBar) { typeBar.classList.add('hidden'); typeBar.innerHTML = ''; }
    if (areasEl) areasEl.textContent = '—';
    return;
  }
  const rows = wb.conveyors || [];
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
    autogenLog('Workbook API missing — relaunch FortnaPlus desktop app', 'warn');
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
  // Prefer full workbook shape
  const wb = {
    project_name: r.project_name,
    stats: r.stats,
    type_counts: r.type_counts,
    areas: r.areas,
    autogen_types: r.autogen_types,
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
  setAutogenStatus('Workbook ready', 'ready');
  const s = r.stats || {};
  autogenLog(
    `Workbook ready — ${s.conveyor_count || 0} conveyors, ${s.io_mapped || 0}/${s.io_point_count || 0} IO mapped, `
    + `${s.area_count || 0} areas. Edit TYPE/area then Generate L5X.`,
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
  const res = await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
  if (!res?.success) {
    autogenLog(res?.message || 'Save failed', 'err');
    return;
  }
  autogenLog(`Workbook saved: ${res.path || 'workspace/active/autogen_workbook.json'}`, 'ok');
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
          + ' — use Preview / Generate from RUN',
          'info',
        );
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
    autogenLog('For Excel path: Browse workbook first. Preferred: Generate from RUN after loading tar.gz.', 'warn');
    return;
  }
  if (mode === 'run' && !autogenState.workbook) {
    autogenLog('No workbook yet — building from RUN first…', 'info');
    await buildAutogenWorkbook();
    if (!autogenState.workbook) {
      autogenLog('Build workbook from RUN before Generate (load tar.gz on I/O & Prints first)', 'warn');
      return;
    }
  }
  autogenState.busy = true;
  setAutogenStatus('Generating…', 'busy');
  if ($('btn-autogen-generate')) $('btn-autogen-generate').disabled = true;
  if ($('btn-autogen-from-run')) $('btn-autogen-from-run').disabled = true;
  if ($('btn-autogen-workbook-build')) $('btn-autogen-workbook-build').disabled = true;
  autogenLog(
    mode === 'run'
      ? 'Python autogen: workbook + RUN → library templates → L5X…'
      : 'Legacy Excel path: generating L5X…',
    'info',
  );
  // Program pack: Sys (recommended) + optional gold Excel IO_MAP + site sorter/WCS
  const includePrograms = [];
  if ($('autogen-opt-shippingsorter')?.checked) includePrograms.push('ShippingSorter_Area_L3');
  if ($('autogen-opt-wcs')?.checked) includePrograms.push('WCS_Interface_TCP_IP');
  if ($('autogen-opt-sorter-track')?.checked) includePrograms.push('Sorter_Track');
  const noSys = !($('autogen-opt-sys')?.checked ?? true);
  // Gold Excel IO_MAP is OFF by default — RUN/tar.gz banks drive the map
  const ioMapGold = !!($('autogen-opt-iomap')?.checked);
  const packBits = [];
  if (!noSys) packBits.push('Sys');
  packBits.push(ioMapGold ? 'IO_MAP(gold Excel)' : 'IO_MAP(RUN tar.gz banks→RIO)');
  if (includePrograms.length) packBits.push(...includePrograms);
  autogenLog(`Program pack: ${packBits.join(' + ')}`, 'info');

  // Persist workbook edits before generate
  if (mode === 'run' && autogenState.workbook && typeof fortnaAPI.autogenWorkbookSave === 'function') {
    try {
      await fortnaAPI.autogenWorkbookSave({ workbook: autogenState.workbook });
    } catch (_) { /* generate still runs from memory path */ }
  }

  let res;
  try {
    res = await fortnaAPI.autogenGenerate({
      mode,
      excel: excel || undefined,
      library: library || undefined,
      includePrograms,
      noSys,
      noIoMapGold: !ioMapGold,
      ioMapGold,
      workbook: mode === 'run' ? (autogenState.workbook || undefined) : undefined,
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
      autogenLog('Tip: I/O & Prints → Load RUN .tar.gz first, wait until machine status is ready, then Generate from RUN.', 'warn');
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
          L5X generated via Python${mode === 'run' ? ' from RUN' : ' from Excel'}
          ${r.recovered ? ' <span class="text-amber-400 text-xs">(recovered from disk)</span>' : ''}
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
}

$('btn-autogen-verify')?.addEventListener('click', async () => {
  if (typeof fortnaAPI.autogenVerify !== 'function') {
    autogenLog('Verify API missing — relaunch FortnaPlus', 'warn');
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
$('btn-autogen-open-l5x')?.addEventListener('click', () => {
  if (autogenState.lastL5x) fortnaAPI.openPath(autogenState.lastL5x);
});

// --- Ignition Build (layout + tag seed toward .gwbk) ---
const ignitionState = { lastOut: '', lastResult: null, busy: false };

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
    ignitionLog('API missing — relaunch FortnaPlus', 'warn');
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
  if ($('btn-ignition-open-project')) {
    $('btn-ignition-open-project').disabled = !ignitionState.projectDir;
  }
  const dep = r.gateway_deploy;
  const stamp = r.folder_stamp || dep?.folder_stamp || '';
  const localT = r.generated_local || '';
  const projNm = r.project_name || dep?.project_name || '';
  if (dep?.ok) {
    ignitionLog(
      `Built ${stamp || ''} (${localT || 'now'}) → gateway project ${projNm || 'FortnaPlus_*'} `
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
      `2) Designer → open ${projNm || 'FortnaPlus_*'} → Smoke_Test first`,
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
$('btn-ignition-perspective')?.addEventListener('click', async () => {
  if (typeof fortnaAPI.ignitionPackPerspective !== 'function') {
    ignitionLog('Pack API missing — relaunch FortnaPlus', 'warn');
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
      '1) Copy FortnaPlus_POC →',
      '   C:\\Program Files\\Inductive Automation\\Ignition\\data\\projects\\',
      '2) Gateway → Platform → System → Projects → Scan Filesystem',
      '3) Designer → open FortnaPlus_POC → Views → FortnaPlus/POC/Plant_Layout',
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