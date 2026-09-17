/* Transport Build UX Pass 2 — Rapid Engineering Workflow
 * Companion to transport-build.js (Pass 1 topology API via window.__tbApi).
 * No PDF parsing. Topology remains engineer-defined.
 */
(function () {
  const HISTORY_MAX = 50;
  const LAYOUT_DX = 140;
  const LAYOUT_DY = 90;
  const NODE_W = 110;

  function api() {
    return window.__tbApi || null;
  }

  function A() {
    const a = api();
    if (!a) throw new Error('Transport Pass1 API missing');
    return a;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function deepClone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  /* ---------- Undo / Redo ---------- */
  function snapshot() {
    const { tb } = A();
    return {
      areas: deepClone(tb.areas),
      activeAreaId: tb.activeAreaId,
      buildContext: deepClone(tb.buildContext || {}),
      selectedId: tb.selectedId,
      selectedIds: [...(tb.selectedIds || [])],
    };
  }

  function restoreSnapshot(snap) {
    const { tb, render, migrateGraphTopology } = A();
    tb.areas = deepClone(snap.areas || []);
    tb.activeAreaId = snap.activeAreaId;
    tb.buildContext = deepClone(snap.buildContext || { areaId: null, areaName: '', safetyZone: '' });
    tb.selectedId = snap.selectedId || null;
    tb.selectedIds = [...(snap.selectedIds || [])];
    tb.selectedDeviceId = null;
    migrateGraphTopology();
    render();
    refreshPass2Chrome();
  }

  function pushHistory(label) {
    const { tb } = A();
    if (!tb.history) tb.history = { past: [], future: [], max: HISTORY_MAX };
    tb.history.past.push({ label: label || 'edit', snap: snapshot() });
    if (tb.history.past.length > (tb.history.max || HISTORY_MAX)) tb.history.past.shift();
    tb.history.future = [];
  }

  function undo() {
    const { tb, status, save } = A();
    if (!tb.history?.past?.length) {
      status('Nothing to undo');
      return false;
    }
    const cur = snapshot();
    const entry = tb.history.past.pop();
    tb.history.future.push({ label: entry.label, snap: cur });
    restoreSnapshot(entry.snap);
    save();
    status(`Undo: ${entry.label || 'edit'}`);
    return true;
  }

  function redo() {
    const { tb, status, save } = A();
    if (!tb.history?.future?.length) {
      status('Nothing to redo');
      return false;
    }
    const cur = snapshot();
    const entry = tb.history.future.pop();
    tb.history.past.push({ label: entry.label, snap: cur });
    restoreSnapshot(entry.snap);
    save();
    status(`Redo: ${entry.label || 'edit'}`);
    return true;
  }

  /* ---------- Build Context ---------- */
  function defaultEsZone(areaName) {
    const base = String(areaName || 'Transport').replace(/_Area$/i, '').trim() || 'Transport';
    return `${base}_ESZone1`;
  }

  function ensureBuildContext() {
    const { tb, activeArea, safetyForAreaName } = A();
    const area = activeArea();
    if (!tb.buildContext) tb.buildContext = { areaId: null, areaName: '', safetyZone: '' };
    if (area) {
      if (!tb.buildContext.areaId || !tb.areas.some((a) => a.id === tb.buildContext.areaId)) {
        tb.buildContext.areaId = area.id;
        tb.buildContext.areaName = area.name || '';
      }
      // Keep name in sync with area tab
      const ctxArea = tb.areas.find((a) => a.id === tb.buildContext.areaId);
      if (ctxArea) tb.buildContext.areaName = ctxArea.name || '';
    }
    if (!tb.buildContext.safetyZone) {
      tb.buildContext.safetyZone =
        (typeof safetyForAreaName === 'function'
          ? safetyForAreaName(tb.buildContext.areaName)
          : defaultEsZone(tb.buildContext.areaName)) || defaultEsZone(tb.buildContext.areaName);
    }
    return tb.buildContext;
  }

  function refreshBuildContextUi() {
    const { tb, escapeHtml } = A();
    ensureBuildContext();
    const sel = $('tb-ctx-area');
    if (sel) {
      sel.innerHTML = (tb.areas || [])
        .map(
          (a) =>
            `<option value="${escapeHtml(a.id)}" ${a.id === tb.buildContext.areaId ? 'selected' : ''}>${escapeHtml(a.name)}</option>`
        )
        .join('');
    }
    const es = $('tb-ctx-eszone');
    if (es && document.activeElement !== es) es.value = tb.buildContext.safetyZone || '';
    const dl = $('tb-ctx-eszone-list');
    if (dl) {
      const opts = new Set();
      (tb.areas || []).forEach((a) => opts.add(defaultEsZone(a.name)));
      (tb.areas || []).forEach((a) => {
        (a.nodes || []).forEach((n) => {
          if (n.safetyZone) opts.add(n.safetyZone);
        });
      });
      if (tb.buildContext.safetyZone) opts.add(tb.buildContext.safetyZone);
      // workbook safety zones if present
      try {
        const wb = typeof autogenState !== 'undefined' ? autogenState.workbook : null;
        (wb?.options?.safety_zones || []).forEach((z) => opts.add(String(z)));
      } catch (_) { /* ignore */ }
      dl.innerHTML = [...opts]
        .filter(Boolean)
        .map((z) => `<option value="${escapeHtml(z)}"></option>`)
        .join('');
    }
  }

  function applyContextToSelection() {
    const { tb, save, render, status, moveNodeToArea } = A();
    const ids = tb.selectedIds?.length ? tb.selectedIds : tb.selectedId ? [tb.selectedId] : [];
    if (!ids.length) {
      status('Select conveyors first');
      return;
    }
    pushHistory('Apply Build Context to selection');
    ensureBuildContext();
    const destId = tb.buildContext.areaId;
    const zone = tb.buildContext.safetyZone || '';
    ids.forEach((id) => {
      if (destId) moveNodeToArea(id, destId);
      // moveNodeToArea re-renders; find node again
      for (const a of tb.areas) {
        const n = (a.nodes || []).find((x) => x.id === id);
        if (n) {
          n.safetyZone = zone;
          break;
        }
      }
    });
    save();
    render();
    status(`Applied Area “${tb.buildContext.areaName}” + ES ${zone} to ${ids.length} conveyor(s)`);
    refreshPass2Chrome();
  }

  /* ---------- Chain parse / Build Chain ---------- */
  function parseChainText(text) {
    const raw = String(text || '')
      .replace(/→/g, '>')
      .replace(/->/g, '>')
      .replace(/,/g, ' ')
      .replace(/\r/g, '\n');
    const parts = raw.split(/[\s>]+/).map((s) => s.trim()).filter(Boolean);
    const out = [];
    const seen = new Set();
    parts.forEach((p) => {
      const t = p.toUpperCase();
      // keep original casing from first occurrence-ish
      const tag = p.trim();
      const key = tag.toUpperCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(tag);
    });
    return out;
  }

  // Expose for Node unit tests
  window.__tbParseChainText = parseChainText;

  function analyzeChainTags(tags) {
    const { conveyorOptions, assignedConveyorTags, isConveyorTag } = {
      conveyorOptions: A().conveyorOptions,
      assignedConveyorTags: A().assignedConveyorTags,
      isConveyorTag: (t) => /^P\d{2,4}[A-Za-z0-9_]*$/i.test(String(t || '').trim()),
    };
    const inventory = new Set(conveyorOptions().map((c) => c.toUpperCase()));
    const placed = assignedConveyorTags();
    const known = [];
    const unknown = [];
    const already = [];
    tags.forEach((t) => {
      const u = t.toUpperCase();
      if (!isConveyorTag(t)) {
        unknown.push(t);
        return;
      }
      if (!inventory.has(u)) unknown.push(t);
      else known.push(t);
      if (placed.has(u)) already.push(t);
    });
    return { known, unknown, already, inventory };
  }

  function workbookRowForTag(tag) {
    try {
      const wb = typeof autogenState !== 'undefined' ? autogenState.workbook : null;
      const u = String(tag || '').toUpperCase();
      return (wb?.conveyors || []).find((r) => String(r.conveyor || '').toUpperCase() === u) || null;
    } catch (_) {
      return null;
    }
  }

  function knownMotorForConveyor(tag) {
    // Only use explicit workbook associations — never invent
    const row = workbookRowForTag(tag);
    if (!row) return '';
    const m = (row.motor_tag || row.motor || row.vfd_tag || '').trim();
    if (m && /^M\d|^VFD\d/i.test(m)) return m;
    return '';
  }

  function knownSubtype(tag) {
    const row = workbookRowForTag(tag);
    if (!row) return '';
    return String(row.type || row.template || row.drive || '').trim();
  }

  function createConvNode({ tag, x, y, area, safetyZone, kind }) {
    const { uid, KIND_META, isConv } = A();
    const k = kind || 'conv_straight';
    const meta = KIND_META[k] || {};
    const ctx = ensureBuildContext();
    const node = {
      id: uid('node'),
      kind: k,
      label: tag || meta.title || 'Straight',
      conveyorTag: tag || '',
      x: Math.max(20, x || 40),
      y: Math.max(20, y || 40),
      devices: [],
      rotation: 0,
      inPorts: 1,
      downstream: '',
      terminal: false,
      asMerge: false,
      safetyZone: safetyZone || ctx.safetyZone || '',
      plcOwned: true,
      scopeClass: 'LOCAL',
    };
    // Prefill motor only if known from workbook
    const motor = tag ? knownMotorForConveyor(tag) : '';
    if (meta.isConv && !meta.isMerge && !meta.isSpiral) {
      const mid = uid('dev');
      node.devices.push({
        id: mid,
        kind: 'motor',
        tag: motor || '',
        name: motor || '',
      });
    }
    (area.nodes || (area.nodes = [])).push(node);
    return node;
  }
  // Expose for topology blank-row Add Conveyor (no palette drag required)
  window.__tbPass2CreateConv = createConvNode;

  function findOrCreateInContext(tag, index, total) {
    const { tb, findNodeByTag, moveNodeToArea } = A();
    const ctx = ensureBuildContext();
    let area = tb.areas.find((a) => a.id === ctx.areaId) || A().activeArea();
    if (!area) {
      A().ensureArea();
      area = A().activeArea();
    }
    // Prefer existing node anywhere; move into context area if needed
    let node = null;
    let srcArea = null;
    for (const a of tb.areas) {
      const n = findNodeByTag(a, tag);
      if (n) {
        node = n;
        srcArea = a;
        break;
      }
    }
    const baseX = 60 + index * LAYOUT_DX;
    const baseY = 120;
    if (node) {
      if (srcArea && srcArea.id !== area.id) {
        moveNodeToArea(node.id, area.id);
        area = tb.areas.find((a) => a.id === area.id) || area;
        node = findNodeByTag(area, tag) || node;
      }
      node.x = baseX;
      node.y = baseY;
      if (!node.safetyZone) node.safetyZone = ctx.safetyZone || '';
      return node;
    }
    return createConvNode({
      tag,
      x: baseX,
      y: baseY,
      area,
      safetyZone: ctx.safetyZone,
    });
  }

  function commitChain(tags, { allowUnknown } = {}) {
    const { tb, setDownstream, save, render, status, selectNode, syncDownstreamFromWires } = A();
    if (!tags.length) {
      status('Build Chain: no tags');
      return false;
    }
    const analysis = analyzeChainTags(tags);
    if (analysis.unknown.length && !allowUnknown) {
      status(`Unknown tags blocked: ${analysis.unknown.join(', ')}`);
      return false;
    }
    pushHistory(`Build Chain (${tags.length})`);
    ensureBuildContext();
    // Switch active area to context
    if (tb.buildContext.areaId) tb.activeAreaId = tb.buildContext.areaId;

    const nodes = tags.map((t, i) => findOrCreateInContext(t, i, tags.length));
    for (let i = 0; i < nodes.length - 1; i++) {
      setDownstream(nodes[i].id, nodes[i + 1].id, { silent: true, skipMergePrompt: true });
      nodes[i].terminal = false;
    }
    const area = A().activeArea();
    syncDownstreamFromWires(area);
    // Auto-layout the chain row (presentation)
    nodes.forEach((n, i) => {
      n.x = 60 + i * LAYOUT_DX;
      n.y = 120;
    });
    const last = nodes[nodes.length - 1];
    tb.selectedId = last.id;
    tb.selectedIds = [last.id];
    save();
    render();
    status(`Built chain ${tags.join(' → ')} (${tags.length} conveyors, ${tags.length - 1} links)`);
    refreshPass2Chrome();
    return true;
  }

  function openChainDialog() {
    const dlg = $('tb-chain-dialog');
    if (!dlg) return;
    dlg.classList.remove('hidden');
    dlg.style.display = 'flex';
    const input = $('tb-chain-input');
    if (input) {
      input.value = '';
      setTimeout(() => input.focus(), 30);
    }
    updateChainPreview();
  }

  function closeChainDialog() {
    const dlg = $('tb-chain-dialog');
    if (!dlg) return;
    dlg.classList.add('hidden');
    dlg.style.display = 'none';
  }

  function updateChainPreview() {
    const { escapeHtml } = A();
    const tags = parseChainText($('tb-chain-input')?.value || '');
    const prev = $('tb-chain-preview');
    if (prev) prev.textContent = tags.length ? tags.join(' → ') : '—';
    const analysis = analyzeChainTags(tags);
    const warn = $('tb-chain-warnings');
    if (!warn) return;
    const parts = [];
    if (analysis.unknown.length) {
      parts.push(
        `<div class="tb-val-err">Unknown (not in RUN/workbook): ${escapeHtml(analysis.unknown.join(', '))}</div>`
      );
    }
    if (analysis.already.length) {
      parts.push(
        `<div class="tb-val-warn">Already placed (will reuse): ${escapeHtml(analysis.already.join(', '))}</div>`
      );
    }
    if (tags.length && !analysis.unknown.length) {
      parts.push(`<div class="tb-val-ok">${tags.length} conveyors · ${Math.max(0, tags.length - 1)} links</div>`);
    }
    warn.innerHTML = parts.join('');
  }

  /* ---------- Continue Run ---------- */
  function openContinueRun() {
    const { tb, status, isConv, activeArea } = A();
    const area = activeArea();
    const n = area?.nodes.find((x) => x.id === tb.selectedId);
    if (!n || !isConv(n.kind)) {
      status('Select a conveyor to Continue Run from');
      return;
    }
    tb.continueOpen = true;
    const bar = $('tb-continue-bar');
    bar?.classList.remove('hidden');
    if ($('tb-continue-from')) {
      $('tb-continue-from').textContent = n.conveyorTag || n.label || n.id;
    }
    const input = $('tb-continue-input');
    if (input) {
      input.value = '';
      setTimeout(() => input.focus(), 20);
    }
    refreshContinueHits();
  }

  function closeContinueRun() {
    const { tb } = A();
    tb.continueOpen = false;
    $('tb-continue-bar')?.classList.add('hidden');
  }

  function unplacedConveyors(filter) {
    const { conveyorOptions, assignedConveyorTags } = A();
    const used = assignedConveyorTags();
    const q = String(filter || '').trim().toUpperCase();
    return conveyorOptions()
      .filter((t) => !used.has(t.toUpperCase()))
      .filter((t) => !q || t.toUpperCase().includes(q));
  }

  function refreshContinueHits() {
    const { escapeHtml } = A();
    const host = $('tb-continue-hits');
    if (!host) return;
    const q = $('tb-continue-input')?.value || '';
    const hits = unplacedConveyors(q).slice(0, 40);
    host.innerHTML = hits
      .map((t) => {
        const sub = knownSubtype(t);
        const mot = knownMotorForConveyor(t);
        const extra = [sub, mot].filter(Boolean).join(' · ');
        return `<button type="button" data-tb-cont="${escapeHtml(t)}" class="text-[10px] mono px-1.5 py-0.5 rounded border border-slate-700 text-cyan-300 hover:border-cyan-600">${escapeHtml(t)}${extra ? `<span class="text-slate-600 ml-1">${escapeHtml(extra)}</span>` : ''}</button>`;
      })
      .join('') || `<span class="text-[10px] text-slate-600">No unused conveyors match</span>`;
    host.querySelectorAll('[data-tb-cont]').forEach((btn) => {
      btn.addEventListener('click', () => continueRunTo(btn.getAttribute('data-tb-cont')));
    });
  }

  function continueRunTo(tag) {
    const { tb, activeArea, isConv, findNodeByTag, setDownstream, save, render, status, selectNode } =
      A();
    const raw = String(tag || '').trim();
    if (!raw) return false;
    const area = activeArea();
    const src = area?.nodes.find((x) => x.id === tb.selectedId);
    if (!src || !isConv(src.kind)) {
      status('Select a source conveyor first');
      return false;
    }
    const analysis = analyzeChainTags([raw]);
    if (analysis.unknown.length && !$('tb-chain-allow-unknown')?.checked) {
      // Continue Run: require known RUN tag
      status(`“${raw}” is not in RUN/workbook inventory`);
      return false;
    }
    pushHistory(`Continue ${src.conveyorTag || src.id} → ${raw}`);
    ensureBuildContext();
    let dst = findNodeByTag(area, raw);
    if (!dst) {
      // place to the right of source
      dst = createConvNode({
        tag: raw,
        x: (Number(src.x) || 40) + LAYOUT_DX,
        y: Number(src.y) || 120,
        area,
        safetyZone: src.safetyZone || tb.buildContext.safetyZone,
      });
    }
    setDownstream(src.id, dst.id, { silent: true, skipMergePrompt: true });
    src.terminal = false;
    tb.selectedId = dst.id;
    tb.selectedIds = [dst.id];
    save();
    render();
    status(`${src.conveyorTag || src.id} → ${raw}`);
    // Keep continue bar open for rapid entry
    if ($('tb-continue-from')) $('tb-continue-from').textContent = raw;
    if ($('tb-continue-input')) {
      $('tb-continue-input').value = '';
      $('tb-continue-input').focus();
    }
    refreshContinueHits();
    refreshPass2Chrome();
    // Merge prompt after connect
    A().maybeConfirmMerge(dst);
    return true;
  }

  /* ---------- Multi-select / bulk ---------- */
  function selectedConvNodes() {
    const { tb, activeArea, isConv } = A();
    const area = activeArea();
    const ids = tb.selectedIds?.length ? tb.selectedIds : tb.selectedId ? [tb.selectedId] : [];
    return ids
      .map((id) => area?.nodes.find((n) => n.id === id))
      .filter((n) => n && isConv(n.kind));
  }

  function refreshBulkBar() {
    const { tb, escapeHtml, normalizeControlPanel } = A();
    const bar = $('tb-bulk-bar');
    if (!bar) return;
    const n = (tb.selectedIds || []).length || (tb.selectedId ? 1 : 0);
    // Show for multi-select, or single select when Area/ES still required, or any selection for CP assign
    const nodes = selectedConvNodes();
    const needsConfig = nodes.some((x) => x.areaRequired || x.esZoneRequired);
    if (n < 1) {
      bar.classList.add('hidden');
      return;
    }
    if (n < 2 && !needsConfig) {
      // Still show when a single node is selected so CP can be assigned
      bar.classList.remove('hidden');
    } else {
      bar.classList.remove('hidden');
    }
    if ($('tb-bulk-count')) {
      $('tb-bulk-count').textContent = n === 1
        ? `Selected: 1 conveyor`
        : `Selected: ${n} conveyors`;
      $('tb-bulk-count').title =
        'Marquee: drag empty canvas · Ctrl/Meta = add · Alt (or Ctrl+Shift) = subtract · Shift-click node = connect · Ctrl-click node = toggle select';
    }
    const areaSel = $('tb-bulk-area');
    if (areaSel) {
      areaSel.innerHTML = (tb.areas || [])
        .map(
          (a) =>
            `<option value="${escapeHtml(a.id)}" ${a.id === tb.activeAreaId ? 'selected' : ''}>${escapeHtml(a.name)}</option>`
        )
        .join('');
    }
    const zones = [...new Set(nodes.map((x) => x.safetyZone || '').filter(Boolean))];
    if ($('tb-bulk-eszone') && document.activeElement !== $('tb-bulk-eszone')) {
      $('tb-bulk-eszone').value = zones.length === 1 ? zones[0] : ensureBuildContext().safetyZone || '';
    }
    const cpSel = $('tb-bulk-cp');
    if (cpSel && document.activeElement !== cpSel) {
      const cps = [...new Set(nodes.map((x) => (normalizeControlPanel
        ? normalizeControlPanel(x.controlPanel)
        : String(x.controlPanel || '').trim())).filter(Boolean))];
      cpSel.value = cps.length === 1 ? cps[0] : '';
    }
  }

  function applyControlPanelToSelection(value) {
    const { tb, save, render, status, normalizeControlPanel } = A();
    const ids = [...(tb.selectedIds || [])];
    if (!ids.length && tb.selectedId) ids.push(tb.selectedId);
    if (!ids.length) {
      status('Select conveyors first');
      return;
    }
    const raw = String(value || '').trim();
    const next = raw === '' || raw.toLowerCase() === 'clear'
      ? ''
      : (normalizeControlPanel ? normalizeControlPanel(raw) : raw);
    pushHistory(`Assign Control Panel (${ids.length})`);
    let n = 0;
    ids.forEach((id) => {
      for (const a of tb.areas) {
        const node = (a.nodes || []).find((x) => x.id === id);
        if (!node) continue;
        node.controlPanel = next;
        node.controlPanelProvenance = next ? 'ENGINEER' : 'CLEARED';
        n += 1;
      }
    });
    save();
    render();
    status(next
      ? `Control Panel ${next} → ${n} conveyor(s) (presentation only)`
      : `Cleared Control Panel on ${n} conveyor(s)`);
    refreshPass2Chrome();
  }

  /** Rebuild Control Panel checkboxes from RUN-discovered tags (not hard-coded CP1/CP2/CP3). */
  function refreshCpFilterUi() {
    const { tb, escapeHtml, discoveredControlPanels } = A();
    if (!tb.cpFilters || typeof tb.cpFilters !== 'object') tb.cpFilters = {};
    const host = $('tb-cp-filters');
    const panels = typeof discoveredControlPanels === 'function'
      ? discoveredControlPanels()
      : [];
    // Keep filter keys for panels that still exist; drop stale hard-coded ones
    Object.keys(tb.cpFilters).forEach((k) => {
      if (!panels.includes(k)) delete tb.cpFilters[k];
    });
    panels.forEach((cp) => {
      if (tb.cpFilters[cp] == null) tb.cpFilters[cp] = false;
    });
    // Bulk CP dropdown options from discovered panels
    const bulk = $('tb-bulk-cp');
    if (bulk) {
      const cur = bulk.value;
      const opts = ['<option value="">—</option>']
        .concat(panels.map((cp) =>
          `<option value="${escapeHtml(cp)}">${escapeHtml(cp)}</option>`))
        .concat(['<option value="Other">Other</option>', '<option value="clear">Clear</option>']);
      bulk.innerHTML = opts.join('');
      if ([...bulk.options].some((o) => o.value === cur)) bulk.value = cur;
    }
    if (!host) return;
    const sig = panels.join('|') + '::' + panels.map((cp) => (tb.cpFilters[cp] ? '1' : '0')).join('');
    if (host.dataset.cpSig === sig) return;
    host.dataset.cpSig = sig;
    if (!panels.length) {
      host.innerHTML = '<span class="text-[10px] text-slate-600">No Control Panels on this graph yet — Auto Build or assign CP on selection</span>';
      return;
    }
    const palette = ['text-cyan-300/90 border-cyan-900/50', 'text-violet-300/90 border-violet-900/50',
      'text-amber-300/90 border-amber-900/50', 'text-emerald-300/90 border-emerald-900/50',
      'text-rose-300/90 border-rose-900/50', 'text-sky-300/90 border-sky-900/50'];
    host.innerHTML = panels.map((cp, i) => {
      const tone = palette[i % palette.length];
      const checked = tb.cpFilters[cp] ? 'checked' : '';
      const id = `tb-cp-filter-${cp.replace(/[^A-Za-z0-9_-]/g, '_')}`;
      const sid = `tb-cp-select-${cp.replace(/[^A-Za-z0-9_-]/g, '_')}`;
      return `<label class="flex items-center gap-1 ${tone.split(' ')[0]} cursor-pointer" title="Highlight ${escapeHtml(cp)}">
        <input type="checkbox" id="${id}" data-tb-cp="${escapeHtml(cp)}" class="rounded border-slate-600 bg-slate-900" ${checked}> ${escapeHtml(cp)}
      </label>
      <button type="button" id="${sid}" data-tb-cp-select="${escapeHtml(cp)}" class="btn-ghost text-[9px] px-1.5 py-0.5 rounded border ${tone}" title="Select all ${escapeHtml(cp)} nodes">Select</button>`;
    }).join('');
    host.querySelectorAll('[data-tb-cp]').forEach((el) => {
      el.addEventListener('change', () => {
        const cp = el.getAttribute('data-tb-cp') || '';
        if (!cp) return;
        if (!tb.cpFilters) tb.cpFilters = {};
        tb.cpFilters[cp] = !!el.checked;
        host.dataset.cpSig = ''; // force rebuild after save/render
        try { A().save(); } catch (_) { /* ignore */ }
        A().render();
        A().status(`CP filter ${cp}: ${tb.cpFilters[cp] ? 'ON' : 'OFF'} (highlight only)`);
      });
    });
    host.querySelectorAll('[data-tb-cp-select]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const cp = btn.getAttribute('data-tb-cp-select') || '';
        if (cp) selectCpGroup(cp);
      });
    });
  }

  function selectCpGroup(cp) {
    const { tb, activeArea, isConv, render, status, normalizeControlPanel } = A();
    const want = normalizeControlPanel ? normalizeControlPanel(cp) : String(cp || '').trim();
    if (!want) return;
    const area = activeArea();
    const ids = (area?.nodes || [])
      .filter((n) => isConv(n.kind))
      .filter((n) => (normalizeControlPanel
        ? normalizeControlPanel(n.controlPanel)
        : String(n.controlPanel || '').trim()) === want)
      .map((n) => n.id);
    tb.selectedIds = ids;
    tb.selectedId = ids[0] || null;
    render();
    refreshPass2Chrome();
    status(ids.length
      ? `Selected ${want} group · ${ids.length} conveyor(s) — drag moves as a unit`
      : `No conveyors tagged ${want}`);
  }

  function applyBulkEdit() {
    const { tb, save, render, status, moveNodeToArea } = A();
    const ids = [...(tb.selectedIds || [])];
    if (!ids.length && tb.selectedId) ids.push(tb.selectedId);
    if (ids.length < 1) return;
    pushHistory(`Bulk Area/ES (${ids.length})`);
    const destArea = $('tb-bulk-area')?.value || '';
    const zone = ($('tb-bulk-eszone')?.value || '').trim();
    if (!destArea && !zone) {
      status('Select an Area and/or type an ES Zone, then Apply Area / ES');
      return;
    }
    ids.forEach((id) => {
      if (destArea) moveNodeToArea(id, destArea);
      for (const a of tb.areas) {
        const n = (a.nodes || []).find((x) => x.id === id);
        if (!n) continue;
        if (destArea) {
          n.areaRequired = false;
          if (!n.provenance) n.provenance = {};
          n.provenance.area = 'ENGINEER';
        }
        if (zone) {
          n.safetyZone = zone;
          n.esZoneRequired = false;
          if (!n.provenance) n.provenance = {};
          n.provenance.safetyZone = 'ENGINEER';
        }
      }
    });
    // Also rename active area if engineer is assigning a real name via build context later
    save();
    render();
    status(`Area/ES applied to ${ids.length} conveyor(s) — engineer configuration`);
    refreshPass2Chrome();
  }

  function selectionIds() {
    const { tb } = A();
    const ids = [...(tb.selectedIds || [])];
    if (!ids.length && tb.selectedId) ids.push(tb.selectedId);
    return ids;
  }

  function markAreaEngineer(node) {
    if (!node) return;
    node.areaRequired = false;
    if (!node.provenance) node.provenance = {};
    node.provenance.area = 'ENGINEER';
  }

  function findNodeAnywhere(nodeId) {
    const { tb } = A();
    for (const a of tb.areas || []) {
      const n = (a.nodes || []).find((x) => x.id === nodeId);
      if (n) return { node: n, area: a };
    }
    return null;
  }

  function ensureNamedArea(name) {
    const { tb, uid } = A();
    const want = String(name || '').trim();
    if (!want) return null;
    let a = (tb.areas || []).find(
      (x) => String(x.name || '').trim().toLowerCase() === want.toLowerCase()
    );
    if (!a) {
      tb.suppressDefaultArea = false;
      a = { id: uid('area'), name: want, nodes: [], wires: [] };
      tb.areas.push(a);
    }
    return a;
  }

  function resolveAreaByNameOrId(raw) {
    const { tb } = A();
    const key = String(raw || '').trim();
    if (!key) return null;
    return (
      (tb.areas || []).find((a) => a.id === key) ||
      (tb.areas || []).find(
        (a) => String(a.name || '').trim().toLowerCase() === key.toLowerCase()
      ) ||
      null
    );
  }

  async function pickExistingArea(title, message) {
    const { tb, askText } = A();
    ensureBuildContext();
    const names = (tb.areas || []).map((a) => a.name).filter(Boolean);
    const def =
      tb.buildContext?.areaName ||
      (tb.areas || []).find((a) => a.id === tb.buildContext?.areaId)?.name ||
      names[0] ||
      '';
    const detail = names.length
      ? `Existing areas:\n${names.map((n) => `• ${n}`).join('\n')}`
      : 'No areas yet — create one first.';
    const typed = await askText(
      title || 'Pick Area',
      `${message || 'Area name (or leave Build Context area):'}\n\n${detail}`,
      def
    );
    if (typed === null) return null;
    const trimmed = String(typed).trim();
    if (!trimmed) return resolveAreaByNameOrId(def);
    const resolved = resolveAreaByNameOrId(trimmed);
    if (!resolved) {
      A().status(`Unknown area “${trimmed}”`);
      return null;
    }
    return resolved;
  }

  function moveSelectionToArea(dest, label) {
    const { tb, moveNodeToArea, save, render, status } = A();
    const ids = selectionIds();
    if (!ids.length) {
      status('Select conveyors first');
      return 0;
    }
    if (!dest) {
      status('No destination area');
      return 0;
    }
    // Keep full selection across per-node moveNodeToArea calls.
    // Do NOT switch activeAreaId — assignment must leave the current view alone.
    const keepView = tb.activeAreaId;
    tb.selectedIds = [...ids];
    tb.selectedId = ids[0];
    ids.forEach((id) => {
      moveNodeToArea(id, dest.id);
      const found = findNodeAnywhere(id);
      if (found) markAreaEngineer(found.node);
    });
    tb.activeAreaId = keepView;
    tb.selectedIds = ids.filter((id) => (dest.nodes || []).some((n) => n.id === id));
    tb.selectedId = tb.selectedIds[0] || null;
    save();
    render();
    status(
      `${label || 'Moved'} ${tb.selectedIds.length} conveyor(s) → area “${dest.name}” (view unchanged · topology preserved)`
    );
    refreshPass2Chrome();
    return tb.selectedIds.length;
  }

  /** Create a new Area from the current selection (name prompted — never inferred from geometry). */
  async function createAreaFromSelection() {
    const { tb, askText, askYesNo, uid, save, render, status } = A();
    const ids = selectionIds();
    if (!ids.length) {
      status('Select conveyors first');
      return;
    }
    const def = `Transport_${(tb.areas || []).length + 1}`;
    const name = await askText(
      'Create Area from Selection',
      'Area name (operational grouping — not a Safety Zone):',
      def
    );
    if (name === null || !(String(name).trim())) return;
    const areaName = String(name).trim();
    const { listSafetyZoneNames, ensureSafetyZone } = A();
    const zoneHint = String(tb.buildContext?.safetyZone || '').trim()
      || (typeof listSafetyZoneNames === 'function' ? (listSafetyZoneNames()[0] || '') : '');
    const zoneIn = await askText(
      'Default Safety Zone',
      `Optional default Safety Zone for conveyors in “${areaName}”.\n`
        + 'Area ≠ Safety Zone. Conveyor-level value stays authoritative.',
      zoneHint
    );
    const defaultZone = zoneIn === null ? '' : String(zoneIn || '').trim();
    if (defaultZone && typeof ensureSafetyZone === 'function') ensureSafetyZone(defaultZone);
    pushHistory(`Create Area from Selection (${ids.length})`);
    tb.suppressDefaultArea = false;
    const a = {
      id: uid('area'),
      name: areaName,
      nodes: [],
      wires: [],
      defaultSafetyZone: defaultZone,
    };
    tb.areas.push(a);
    // Re-assert selection in case focus/dialog churn cleared it
    tb.selectedIds = [...ids];
    tb.selectedId = ids[0];
    const moved = moveSelectionToArea(a, 'Moved');
    ensureBuildContext();
    tb.buildContext.areaId = a.id;
    tb.buildContext.areaName = a.name;
    if (defaultZone) tb.buildContext.safetyZone = defaultZone;
    // Apply default Safety Zone to moved conveyors that have none yet
    if (defaultZone) {
      (a.nodes || []).forEach((n) => {
        if (!String(n.safetyZone || '').trim()) {
          n.safetyZone = defaultZone;
          if (!n.provenance) n.provenance = {};
          n.provenance.safetyZone = 'AREA_DEFAULT';
        }
      });
    }
    save();
    render();
    status(
      `Created area “${a.name}” with ${moved} conveyor(s)`
      + (defaultZone ? ` · default Safety Zone “${defaultZone}”` : '')
      + ' (view unchanged)'
    );
    refreshPass2Chrome();
  }

  /** Move selection into an existing Area (prompted; defaults to Build Context area). */
  async function addSelectionToArea() {
    const { status } = A();
    const ids = selectionIds();
    if (!ids.length) {
      status('Select conveyors first');
      return;
    }
    const dest = await pickExistingArea(
      'Add Selection to Area',
      'Move selected conveyors into which existing Area? (defaults to Build Context)'
    );
    if (!dest) {
      status('Add to Area cancelled');
      return;
    }
    pushHistory(`Add Selection to Area (${ids.length} → ${dest.name})`);
    moveSelectionToArea(dest, 'Added');
    ensureBuildContext();
    const { tb, save } = A();
    tb.buildContext.areaId = dest.id;
    tb.buildContext.areaName = dest.name;
    save();
    refreshPass2Chrome();
  }

  /**
   * Remove selection from its current Area(s) into dedicated Unassigned
   * (or a prompted destination). Does not invent controller ownership.
   */
  async function removeSelectionFromArea() {
    const { askText, status } = A();
    const ids = selectionIds();
    if (!ids.length) {
      status('Select conveyors first');
      return;
    }
    const typed = await askText(
      'Remove Selection from Area',
      'Destination area (default Unassigned — organizational only, not PLC ownership):',
      'Unassigned'
    );
    if (typed === null) return;
    const destName = String(typed).trim() || 'Unassigned';
    pushHistory(`Remove Selection from Area (${ids.length} → ${destName})`);
    const dest = ensureNamedArea(destName);
    if (!dest) return;
    moveSelectionToArea(dest, 'Removed to');
  }

  function deleteSelection() {
    const { tb, activeArea, save, render, status, syncDownstreamFromWires } = A();
    const area = activeArea();
    if (!area) return;
    const ids = new Set(tb.selectedIds?.length ? tb.selectedIds : tb.selectedId ? [tb.selectedId] : []);
    if (!ids.size) return;
    pushHistory(`Delete ${ids.size}`);
    area.nodes = (area.nodes || []).filter((n) => !ids.has(n.id));
    area.wires = (area.wires || []).filter((w) => !ids.has(w.from) && !ids.has(w.to));
    tb.selectedId = null;
    tb.selectedIds = [];
    syncDownstreamFromWires(area);
    save();
    render();
    status(`Deleted ${ids.size} node(s)`);
    refreshPass2Chrome();
  }

  function selectChainFromPrimary() {
    const { tb, activeArea, outboundWire, inboundWires, selectNode, status } = A();
    const area = activeArea();
    if (!area || !tb.selectedId) return;
    const seen = new Set();
    const queue = [tb.selectedId];
    while (queue.length) {
      const id = queue.pop();
      if (seen.has(id)) continue;
      seen.add(id);
      const out = outboundWire(area, id);
      if (out?.to) queue.push(out.to);
      inboundWires(area, id).forEach((w) => queue.push(w.from));
    }
    tb.selectedIds = [...seen];
    tb.selectedId = tb.selectedIds.includes(tb.selectedId) ? tb.selectedId : tb.selectedIds[0];
    A().render();
    status(`Selected chain: ${tb.selectedIds.length} conveyor(s)`);
    refreshPass2Chrome();
  }

  function alignSelection() {
    const nodes = selectedConvNodes();
    if (nodes.length < 2) return;
    pushHistory('Align selection');
    const y = Math.min(...nodes.map((n) => Number(n.y) || 0));
    nodes.forEach((n) => {
      n.y = y;
    });
    A().save();
    A().render();
    A().status('Aligned selection');
  }

  function spaceEvenlySelection() {
    const nodes = selectedConvNodes().slice().sort((a, b) => (a.x || 0) - (b.x || 0));
    if (nodes.length < 3) {
      // still space 2
      if (nodes.length < 2) return;
    }
    pushHistory('Space evenly');
    const left = Number(nodes[0].x) || 0;
    for (let i = 0; i < nodes.length; i++) {
      nodes[i].x = left + i * LAYOUT_DX;
    }
    A().save();
    A().render();
    A().status('Spaced selection evenly');
  }

  function markTerminalSelection(on) {
    const { save, render, status } = A();
    const nodes = selectedConvNodes();
    if (!nodes.length) {
      // single from context
      const { tb, activeArea } = A();
      const n = activeArea()?.nodes.find((x) => x.id === tb.selectedId);
      if (n) nodes.push(n);
    }
    if (!nodes.length) return;
    pushHistory(on ? 'Mark Terminal' : 'Clear Terminal');
    nodes.forEach((n) => {
      n.terminal = !!on;
    });
    save();
    render();
    status(on ? `Marked ${nodes.length} terminal` : `Cleared terminal on ${nodes.length}`);
    refreshPass2Chrome();
  }

  /* ---------- Auto layout (presentation only) ---------- */
  function autoLayoutNodes(nodes, area) {
    const { outboundWire, inboundWires } = A();
    if (!nodes.length) return;
    const idSet = new Set(nodes.map((n) => n.id));
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    // longest-path layering
    const outs = {};
    const ins = {};
    nodes.forEach((n) => {
      outs[n.id] = [];
      ins[n.id] = [];
    });
    nodes.forEach((n) => {
      const w = outboundWire(area, n.id);
      if (w && idSet.has(w.to)) {
        outs[n.id].push(w.to);
        ins[w.to].push(n.id);
      }
    });
    const layer = {};
    const visiting = new Set();
    function depth(id) {
      if (layer[id] != null) return layer[id];
      if (visiting.has(id)) return 0;
      visiting.add(id);
      const preds = ins[id] || [];
      const d = preds.length ? Math.max(...preds.map(depth)) + 1 : 0;
      visiting.delete(id);
      layer[id] = d;
      return d;
    }
    nodes.forEach((n) => depth(n.id));
    const byLayer = {};
    nodes.forEach((n) => {
      const L = layer[n.id] || 0;
      (byLayer[L] || (byLayer[L] = [])).push(n);
    });
    Object.keys(byLayer)
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((L) => {
        const col = byLayer[L];
        // Sort: nodes with more inbound near center; stable by tag
        col.sort((a, b) => {
          const ia = (ins[a.id] || []).length;
          const ib = (ins[b.id] || []).length;
          if (ib !== ia) return ib - ia;
          return String(a.conveyorTag || '').localeCompare(String(b.conveyorTag || ''), undefined, {
            numeric: true,
          });
        });
        const total = col.length;
        col.forEach((n, i) => {
          n.x = 60 + L * LAYOUT_DX;
          const mid = (total - 1) / 2;
          n.y = 100 + (i - mid) * LAYOUT_DY;
          // Separated inbound branches into a merge: offset slightly
          if ((ins[n.id] || []).length === 0 && (outs[n.id] || []).length) {
            /* source */
          }
        });
      });
    // Extra: for merge discharges, pull inbound branches above/below
    nodes.forEach((n) => {
      const preds = (ins[n.id] || []).map((id) => byId[id]).filter(Boolean);
      if (preds.length >= 2) {
        preds
          .slice()
          .sort((a, b) => (a.y || 0) - (b.y || 0))
          .forEach((p, i) => {
            const mid = (preds.length - 1) / 2;
            p.y = (n.y || 100) + (i - mid) * LAYOUT_DY;
            p.x = (n.x || 60) - LAYOUT_DX;
          });
      }
    });
  }

  function autoLayoutArea() {
    const { activeArea, isConv, save, render, status } = A();
    const area = activeArea();
    if (!area) return;
    const nodes = (area.nodes || []).filter((n) => isConv(n.kind));
    if (!nodes.length) return;
    pushHistory('Auto Layout Area');
    autoLayoutNodes(nodes, area);
    save();
    render();
    status(`Auto-laid out ${nodes.length} conveyor(s) (positions only)`);
  }

  function autoLayoutSelection() {
    const { activeArea, save, render, status } = A();
    const area = activeArea();
    const nodes = selectedConvNodes();
    if (!nodes.length) {
      autoLayoutArea();
      return;
    }
    pushHistory('Auto Layout Selection');
    autoLayoutNodes(nodes, area);
    save();
    render();
    status(`Auto-laid out selection (${nodes.length})`);
  }

  /* ---------- Inventory palette ---------- */
  function renderInventoryPalette() {
    const { escapeHtml, runInventory, tb, selectNode } = A();
    const sum = $('tb-inv-summary');
    const list = $('tb-inv-list');
    if (!sum || !list) return;
    const inv = runInventory();
    sum.innerHTML = `
      <div>Conveyors <span class="text-cyan-400">${inv.conveyors.detected}</span>
        · placed <span class="text-emerald-400">${inv.conveyors.assigned}</span>
        · unplaced <span class="text-amber-400">${inv.conveyors.unassigned}</span></div>
      <div>Photoeyes <span class="text-cyan-400">${inv.photoeyes.detected}</span>
        · assigned <span class="text-emerald-400">${inv.photoeyes.assigned}</span></div>`;
    const q = String($('tb-inv-filter')?.value || '').trim().toUpperCase();
    const placed = inv.usedConv;
    const selectedTags = new Set();
    (tb.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        if ((tb.selectedIds || []).includes(n.id) || n.id === tb.selectedId) {
          const t = (n.conveyorTag || '').trim().toUpperCase();
          if (t) selectedTags.add(t);
        }
      });
    });
    const rows = [];
    // Unplaced first
    inv.conveyors.list.forEach((t) => {
      if (q && !t.toUpperCase().includes(q)) return;
      const u = t.toUpperCase();
      const isPlaced = placed.has(u);
      const isSel = selectedTags.has(u);
      const cls = isSel ? 'selected' : isPlaced ? 'placed' : 'unplaced';
      const sub = knownSubtype(t);
      const mot = knownMotorForConveyor(t);
      const meta = [sub, mot].filter(Boolean).join(' · ');
      rows.push(
        `<div class="tb-inv-item ${cls}" data-tb-inv-tag="${escapeHtml(t)}" title="${isPlaced ? 'Placed' : 'Unplaced — double-click to Continue Run'}">${escapeHtml(t)}${meta ? `<span class="text-slate-600 ml-1">${escapeHtml(meta)}</span>` : ''}${isPlaced ? ' · placed' : ''}</div>`
      );
    });
    // Other device kinds (compact)
    const pushDev = (label, items, used) => {
      items.forEach((t) => {
        if (q && !t.toUpperCase().includes(q)) return;
        const usedB = used.has(t.toUpperCase());
        rows.push(
          `<div class="tb-inv-item ${usedB ? 'placed' : 'free'}">${escapeHtml(label)} ${escapeHtml(t)}${usedB ? ' · used' : ''}</div>`
        );
      });
    };
    if (q) {
      pushDev('PE', inv.photoeyes.list, inv.usedDev);
      pushDev('', inv.motors.list, inv.usedDev);
      pushDev('ENC', inv.encoders.list, inv.usedDev);
    }
    list.innerHTML = rows.slice(0, 150).join('') || `<div class="text-slate-600 px-1">No RUN tags match.</div>`;
    list.querySelectorAll('[data-tb-inv-tag]').forEach((el) => {
      el.addEventListener('dblclick', () => {
        const tag = el.getAttribute('data-tb-inv-tag');
        const { activeArea, isConv } = A();
        const src = activeArea()?.nodes.find((n) => n.id === tb.selectedId);
        if (src && isConv(src.kind) && !placed.has(String(tag).toUpperCase())) {
          continueRunTo(tag);
        } else if (!placed.has(String(tag).toUpperCase())) {
          // No source: place via mini chain of one under context
          pushHistory(`Place ${tag}`);
          ensureBuildContext();
          if (tb.buildContext.areaId) tb.activeAreaId = tb.buildContext.areaId;
          const area = A().activeArea();
          const node = createConvNode({
            tag,
            x: 80 + (area.nodes?.length || 0) * 20,
            y: 100,
            area,
            safetyZone: tb.buildContext.safetyZone,
          });
          tb.selectedId = node.id;
          tb.selectedIds = [node.id];
          A().save();
          A().render();
          A().status(`Placed ${tag} from inventory`);
          refreshPass2Chrome();
        } else {
          // Focus placed node
          for (const a of tb.areas) {
            const n = (a.nodes || []).find(
              (x) => String(x.conveyorTag || '').toUpperCase() === String(tag).toUpperCase()
            );
            if (n) {
              tb.activeAreaId = a.id;
              selectNode(n.id);
              break;
            }
          }
        }
      });
    });
  }

  /* ---------- Compact flow node patch ---------- */
  function driveBadge(driveType) {
    const d = String(driveType || 'UNKNOWN').toUpperCase();
    if (d.includes('VFD')) return '<span class="tb-drive-badge tb-drive-vfd">VFD</span>';
    if (d.includes('CONTACTOR') || d.includes('STARTER')) {
      return '<span class="tb-drive-badge tb-drive-ms">CONTACTOR</span>';
    }
    if (!driveType) return '';
    return '<span class="tb-drive-badge tb-drive-unk">UNKNOWN</span>';
  }

  function patchNodeAppearance() {
    // After Pass1 render, rewrite conveyor node inner content to flow style + multi-sel class.
    // Schematic / physical bodies are drawn in #tb-schematic — do not expand into info cards.
    const {
      tb, activeArea, isConv, escapeHtml, peRolesOnNode, peRoleBadgesHtml, KIND_META,
      isPhysicalSeg, isSchematicNode, detailLevel,
    } = A();
    const area = activeArea();
    const lod = typeof detailLevel === 'function' ? detailLevel() : 'mid';
    (area?.nodes || []).forEach((n) => {
      if (!isConv(n.kind)) return;
      const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
      if (!el) return;
      if ((tb.selectedIds || []).includes(n.id) && tb.selectedIds.length > 1) {
        el.classList.add('tb-multi-sel');
      }
      if (n.physical) el.classList.add('tb-physical');
      if (String(n.equipmentType || '').toUpperCase() === 'CURVE' || n.kind === 'conv_right' || n.kind === 'conv_left') {
        el.classList.add('tb-curve');
      }
      if ((n.ambiguousInbound || []).length) el.classList.add('tb-ambiguous');

      // Conveyor-first: never paint motors / PE / AMB / safety onto the canvas.
      // Those details belong in the inspector + hover tooltip only.
      if (
        el.classList.contains('tb-schematic-proxy')
        || el.classList.contains('tb-seg')
        || (typeof isSchematicNode === 'function' && isSchematicNode(n))
        || (typeof isPhysicalSeg === 'function' && isPhysicalSeg(n))
      ) {
        el.querySelector('.tb-seg-detail')?.remove();
        return;
      }

      const tag = (n.conveyorTag || '').trim() || 'P???';
      const head = el.querySelector('.tb-head');
      const body = el.querySelector('.tb-body');
      if (head) {
        head.innerHTML = `<div class="tb-flow" title="${escapeHtml(tag)}">${escapeHtml(tag)}</div>`;
      }
      if (body) body.innerHTML = '';
    });
  }

  /* ---------- Merge 3:1 unsupported ---------- */
  async function maybeConfirmMergePass2(dst) {
    const { activeArea, inboundWires, KIND_META, askYesNo, save, render, status, nodeLabel, isConv } =
      A();
    const area = activeArea();
    if (!area || !dst || !isConv(dst.kind)) return;
    if (KIND_META[dst.kind]?.isMerge || dst.asMerge) return;
    const inbound = inboundWires(area, dst.id);
    if (inbound.length < 2) return;
    const tag = nodeLabel(dst) || 'this conveyor';
    if (inbound.length === 2) {
      const ok = await askYesNo(
        'Configure 2:1 Merge?',
        `${tag} has 2 incoming conveyors.\nConfigure as 2:1 Merge?\n\nUses hold_mode=runhold (Greensboro PLC2 pattern).`
      );
      if (!ok) return;
      pushHistory('Confirm 2:1 merge');
      dst.asMerge = true;
      dst.inPorts = 2;
      dst.mergeGenSupported = true;
      inbound.forEach((w, i) => {
        w.toPort = `in${i}`;
      });
      save();
      render();
      status(`${tag} marked as 2:1 merge discharge`);
      return;
    }
    const ok = await askYesNo(
      'Configure 3:1 Merge?',
      `${tag} has ${inbound.length} incoming conveyors.\nConfigure as 3:1 Merge?\n\n` +
        `Site Forge does not yet generate 3:1 L5X call sites.\n` +
        `Topology will be kept and marked:\nCONFIGURATION REQUIRED / GENERATION NOT YET SUPPORTED`
    );
    if (!ok) return;
    pushHistory('Confirm 3:1 merge (unsupported gen)');
    dst.asMerge = true;
    dst.inPorts = Math.max(3, inbound.length);
    dst.mergeGenSupported = false;
    dst.mergeNote = 'CONFIGURATION REQUIRED / GENERATION NOT YET SUPPORTED';
    inbound.forEach((w, i) => {
      w.toPort = `in${i}`;
    });
    save();
    render();
    status(`${tag}: 3:1 topology saved — generation not yet supported`);
  }

  function installHooks() {
    window.__tbHooks = window.__tbHooks || {};
    window.__tbHooks.maybeConfirmMerge = maybeConfirmMergePass2;
    window.__tbHooks.renderInventoryPanel = renderInventoryPalette;
  }

  /* ---------- Context menu ---------- */
  function hideCtxMenu() {
    const m = $('tb-ctx-menu');
    if (m) {
      m.classList.add('hidden');
      m.style.display = 'none';
    }
  }

  /** Keep multi-select when right-clicking an already-selected conveyor. */
  function ensureCtxSelection(nodeId) {
    const { tb, selectNode } = A();
    if (!nodeId) return;
    if ((tb.selectedIds || []).includes(nodeId)) {
      tb.selectedId = nodeId;
    } else {
      selectNode(nodeId);
    }
  }

  function showCtxMenu(x, y, nodeId) {
    const m = $('tb-ctx-menu');
    if (!m) return;
    m.dataset.nodeId = nodeId || '';
    // Populate quick-move choices from existing areas (exclude current home of node)
    const moveHost = $('tb-ctx-move-areas');
    if (moveHost) {
      const { tb, escapeHtml } = A();
      let homeId = '';
      (tb.areas || []).forEach((a) => {
        if ((a.nodes || []).some((n) => n.id === nodeId)) homeId = a.id;
      });
      const areas = (tb.areas || []).filter((a) => a.id !== homeId);
      if (!areas.length) {
        moveHost.innerHTML = '<div class="px-3 py-1 text-slate-600">No other areas yet — use Add to New Area</div>';
      } else {
        moveHost.innerHTML = areas.map((a) =>
          `<button type="button" data-tb-ctx-move="${escapeHtml(a.id)}" class="w-full text-left px-3 py-1.5 hover:bg-slate-800 text-fuchsia-200">→ ${escapeHtml(a.name || a.id)}</button>`
        ).join('');
        moveHost.querySelectorAll('[data-tb-ctx-move]').forEach((btn) => {
          btn.addEventListener('click', () => {
            const destId = btn.getAttribute('data-tb-ctx-move');
            hideCtxMenu();
            const dest = (tb.areas || []).find((a) => a.id === destId);
            if (!dest) return;
            ensureCtxSelection(nodeId);
            moveSelectionToArea(dest, 'Moved');
          });
        });
      }
    }
    m.classList.remove('hidden');
    m.style.display = 'block';
    m.style.left = `${x}px`;
    m.style.top = `${y}px`;
  }

  /* ---------- Marquee ---------- */
  /** True when marquee should subtract hits (Alt, or Ctrl/Meta+Shift). */
  function marqueeSubtract(ev) {
    if (!ev) return false;
    if (ev.altKey) return true;
    if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey) return true;
    return false;
  }

  /** True when marquee should union hits (Ctrl/Meta without Shift). */
  function marqueeAdd(ev) {
    if (!ev) return false;
    if (marqueeSubtract(ev)) return false;
    return !!(ev.ctrlKey || ev.metaKey);
  }

  /**
   * Generous AABB hit-test: prefer pathCanvas / entryCanvas / exitCanvas extents
   * (via Pass1 nodesBBox) so schematic proxies are selectable by the box; else card box.
   */
  function nodeIntersectsMarquee(n, x, y, w, h) {
    const { nodesBBox } = A();
    const bb = typeof nodesBBox === 'function' ? nodesBBox([n]) : null;
    if (bb && Number.isFinite(bb.minX)) {
      return bb.maxX > x && bb.minX < x + w && bb.maxY > y && bb.minY < y + h;
    }
    const nx = Number(n.x) || 0;
    const ny = Number(n.y) || 0;
    const cardW = Math.max(NODE_W, 130);
    const cardH = 70;
    return nx + cardW > x && nx < x + w && ny + cardH > y && ny < y + h;
  }

  function onCanvasMouseDown(ev) {
    const { tb, canvasPointFromEvent } = A();
    if (ev.button !== 0) return;
    if (ev.target.closest?.('.tb-node') || ev.target.closest?.('.tb-port')) return;
    if (ev.target.closest?.('#tb-topo-panel')) return;
    const canvas = $('tb-canvas');
    // Empty-scene left-drag = pan (CAD hand). Alt+drag keeps marquee select.
    // Space held also forces pan.
    const wantPan = !ev.altKey || !!tb.spacePan;
    if (wantPan && !marqueeAdd(ev) && !marqueeSubtract(ev)) {
      if (!canvas) return;
      ev.preventDefault();
      tb.panning = {
        sx: ev.clientX,
        sy: ev.clientY,
        sl: canvas.scrollLeft,
        st: canvas.scrollTop,
      };
      canvas.classList.add('tb-panning');
      canvas.style.cursor = 'grabbing';
      return;
    }
    // Alt (or Ctrl-add / Alt-subtract) → marquee
    const pt = canvasPointFromEvent(ev);
    tb.marquee = { x0: pt.x, y0: pt.y, x1: pt.x, y1: pt.y };
    if (!marqueeAdd(ev) && !marqueeSubtract(ev)) {
      tb.selectedIds = [];
      tb.selectedId = null;
    }
    const box = $('tb-marquee');
    if (box) {
      box.style.display = 'block';
      box.style.left = `${pt.x}px`;
      box.style.top = `${pt.y}px`;
      box.style.width = '0px';
      box.style.height = '0px';
    }
  }

  function onCanvasMouseMove(ev) {
    const { tb, canvasPointFromEvent } = A();
    if (!tb.marquee) return;
    const pt = canvasPointFromEvent(ev);
    tb.marquee.x1 = pt.x;
    tb.marquee.y1 = pt.y;
    const box = $('tb-marquee');
    if (box) {
      const x = Math.min(tb.marquee.x0, tb.marquee.x1);
      const y = Math.min(tb.marquee.y0, tb.marquee.y1);
      const w = Math.abs(tb.marquee.x1 - tb.marquee.x0);
      const h = Math.abs(tb.marquee.y1 - tb.marquee.y0);
      box.style.left = `${x}px`;
      box.style.top = `${y}px`;
      box.style.width = `${w}px`;
      box.style.height = `${h}px`;
    }
  }

  function onCanvasMouseUp(ev) {
    const { tb, activeArea, isConv, render } = A();
    if (tb.moving && tb._moveHistoryPushed) {
      // history already pushed on move start
      tb._moveHistoryPushed = false;
    }
    if (!tb.marquee) return;
    const x = Math.min(tb.marquee.x0, tb.marquee.x1);
    const y = Math.min(tb.marquee.y0, tb.marquee.y1);
    const w = Math.abs(tb.marquee.x1 - tb.marquee.x0);
    const h = Math.abs(tb.marquee.y1 - tb.marquee.y0);
    tb.marquee = null;
    const box = $('tb-marquee');
    if (box) box.style.display = 'none';
    if (w < 4 && h < 4) {
      render();
      refreshPass2Chrome();
      return;
    }
    const area = activeArea();
    const hit = [];
    (area?.nodes || []).forEach((n) => {
      if (!isConv(n.kind)) return;
      if (nodeIntersectsMarquee(n, x, y, w, h)) hit.push(n.id);
    });
    if (marqueeSubtract(ev)) {
      const remove = new Set(hit);
      tb.selectedIds = (tb.selectedIds || []).filter((id) => !remove.has(id));
    } else if (marqueeAdd(ev)) {
      const set = new Set(tb.selectedIds || []);
      hit.forEach((id) => set.add(id));
      tb.selectedIds = [...set];
    } else {
      tb.selectedIds = hit;
    }
    tb.selectedId = tb.selectedIds[0] || null;
    render();
    refreshPass2Chrome();
  }

  /* ---------- Wire history into mutating ops ---------- */
  function patchHistoryHooks() {
    const a = A();
    // Wrap setDownstream
    if (a.setDownstream && !a.setDownstream.__pass2hist) {
      const orig = a.setDownstream.bind(a);
      const wrapped = function (fromId, toIdOrTag, opts = {}) {
        if (!opts.silent && !opts._noHistory) pushHistory('Set downstream');
        return orig(fromId, toIdOrTag, opts);
      };
      wrapped.__pass2hist = true;
      a.setDownstream = wrapped;
    }
  }

  /* ---------- Node click: multi-select + shift-connect ---------- */
  function patchNodeMouseHandlers() {
    // Rebind after each render via event delegation on #tb-nodes
    const host = $('tb-nodes');
    if (!host || host.__pass2Delegate) return;
    host.__pass2Delegate = true;
    host.addEventListener('mousedown', (ev) => {
      const nodeEl = ev.target.closest?.('.tb-node');
      if (!nodeEl) return;
      if (ev.target.classList.contains('tb-port')) return;
      const { tb, isConv, activeArea, setDownstream, selectNode, canvasPointFromEvent, status } = A();
      const id = nodeEl.dataset.id;
      const area = activeArea();
      const n = area?.nodes.find((x) => x.id === id);
      if (!n) return;

      // Connect mode handled by Pass1; if active, let it — but Pass1 binds per-node.
      // Shift-click = connect (EXIT→ENTRY). Ctrl/Meta-click = toggle select (not Shift).
      if (ev.shiftKey && !tb.connectMode && isConv(n.kind) && tb.selectedId && tb.selectedId !== id) {
        ev.preventDefault();
        ev.stopPropagation();
        pushHistory('Shift-connect');
        setDownstream(tb.selectedId, id, { skipMergePrompt: false });
        selectNode(id);
        return;
      }

      // Ctrl/Meta = toggle membership in multi-select (Shift remains connect-only)
      if (ev.ctrlKey || ev.metaKey) {
        ev.preventDefault();
        ev.stopPropagation();
        selectNode(id, { additive: true });
        refreshPass2Chrome();
        return;
      }

      if (tb.connectMode && isConv(n.kind)) {
        // Pass1 handler also fires — OK
        return;
      }

      // Normal select + move; push history once when move starts
      if (!ev.shiftKey && ev.button === 0) {
        const groupIds = moveGroupIdsForNode(n);
        if (groupIds.length > 1) {
          // Keep / expand selection to the move group (multi-select or CP filter group)
          tb.selectedIds = groupIds;
          tb.selectedId = groupIds.includes(id) ? id : groupIds[0];
        } else if (!(tb.selectedIds || []).includes(id) || (tb.selectedIds || []).length <= 1) {
          selectNode(id);
        } else {
          tb.selectedId = id;
        }
        const pt = canvasPointFromEvent(ev);
        if (!tb._moveHistoryPushed) {
          pushHistory(groupIds.length > 1 ? 'Group Move' : 'Move');
          tb._moveHistoryPushed = true;
        }
        const { captureNodeGeom } = A();
        const ids = groupIds.length ? groupIds : [id];
        // Multi-drag: full canvas geometry origins (pathCanvas/entry/exit)
        tb.moving = {
          id,
          ox: pt.x - n.x,
          oy: pt.y - n.y,
          origins: ids.map((sid) => {
            const nn = area.nodes.find((x) => x.id === sid);
            return nn && captureNodeGeom ? captureNodeGeom(nn) : (nn ? { id: sid, x: nn.x, y: nn.y } : null);
          }).filter(Boolean),
          startX: n.x,
          startY: n.y,
        };
        ev.preventDefault();
        ev.stopPropagation(); // prevent Pass1 from overwriting tb.moving / collapsing selection
      }
    }, true);

    host.addEventListener('contextmenu', (ev) => {
      const nodeEl = ev.target.closest?.('.tb-node');
      if (!nodeEl) return;
      ev.preventDefault();
      const id = nodeEl.dataset.id;
      ensureCtxSelection(id);
      showCtxMenu(ev.clientX, ev.clientY, id);
    });

    // Schematic belt bodies live in #tb-schematic (not .tb-node) — restore right-click Area workflow
    // Hit target is wider than the visible belt; pick uses closest centerline when overlaps.
    const canvas = $('tb-canvas');
    canvas?.addEventListener('contextmenu', (ev) => {
      if (A().tb.connectMode) return;
      const hit = ev.target.closest?.('.tb-schematic-hit, .tb-schematic-body');
      if (!hit) return;
      ev.preventDefault();
      ev.stopPropagation();
      const area = A().activeArea?.() || null;
      const picked = typeof A().pickSchematicNodeAt === 'function'
        ? A().pickSchematicNodeAt(ev.clientX, ev.clientY, area)
        : null;
      const id = picked?.id || hit.getAttribute('data-id');
      if (!id) return;
      ensureCtxSelection(id);
      showCtxMenu(ev.clientX, ev.clientY, id);
    });
  }

  function patchMultiDrag() {
    // Pass1 mousemove now applies captureNodeGeom deltas (incl. pathCanvas/entry/exit).
    // Keep this hook as a no-op guard so older dual-handlers don't fight.
    window.addEventListener('mousemove', (ev) => {
      if (A().tb.panning) {
        const canvas = $('tb-canvas');
        const p = A().tb.panning;
        if (!canvas || !p) return;
        canvas.scrollLeft = p.sl - (ev.clientX - p.sx);
        canvas.scrollTop = p.st - (ev.clientY - p.sy);
      }
    });
  }

  /** Resolve which node ids should move together (multi-select or active CP filter group). */
  function moveGroupIdsForNode(n) {
    const { tb, activeArea, isConv, normalizeControlPanel, cpFilterActive } = A();
    const area = activeArea();
    if (!n || !area) return [];
    const sel = tb.selectedIds || [];
    if (sel.length > 1 && sel.includes(n.id)) return [...sel];
    const cp = normalizeControlPanel ? normalizeControlPanel(n.controlPanel) : String(n.controlPanel || '').trim();
    if (cp && typeof cpFilterActive === 'function' && cpFilterActive()) {
      const f = tb.cpFilters || {};
      const filteredOn = (cp === 'CP1' && f.CP1) || (cp === 'CP2' && f.CP2) || (cp === 'CP3' && f.CP3);
      if (filteredOn) {
        return (area.nodes || [])
          .filter((x) => isConv(x.kind))
          .filter((x) => (normalizeControlPanel
            ? normalizeControlPanel(x.controlPanel)
            : String(x.controlPanel || '').trim()) === cp)
          .map((x) => x.id);
      }
    }
    return [n.id];
  }

  /* ---------- Keyboard ---------- */
  function bindPass2Keys() {
    window.addEventListener('keydown', (ev) => {
      const tab = $('tab-transport');
      if (!tab || tab.classList.contains('hidden')) return;
      const tag = (ev.target && ev.target.tagName) || '';
      const typing =
        tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || ev.target?.isContentEditable;
      if (ev.key === 'Escape') {
        if ($('tb-chain-dialog') && !$('tb-chain-dialog').classList.contains('hidden')) {
          closeChainDialog();
          ev.preventDefault();
          return;
        }
        if (A().tb.continueOpen) {
          closeContinueRun();
          ev.preventDefault();
          return;
        }
        hideCtxMenu();
      }
      if (typing) {
        // Allow Enter in continue / chain
        if (ev.key === 'Enter' && ev.target?.id === 'tb-continue-input') {
          ev.preventDefault();
          const q = ev.target.value.trim();
          const hits = unplacedConveyors(q);
          const pick =
            hits.find((t) => t.toUpperCase() === q.toUpperCase()) || (hits.length === 1 ? hits[0] : '');
          if (pick) continueRunTo(pick);
        }
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
        ev.preventDefault();
        undo();
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && (ev.key.toLowerCase() === 'y' || (ev.shiftKey && ev.key.toLowerCase() === 'z'))) {
        ev.preventDefault();
        redo();
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'a') {
        ev.preventDefault();
        const { tb, activeArea, isConv, render } = A();
        const area = activeArea();
        tb.selectedIds = (area?.nodes || []).filter((n) => isConv(n.kind)).map((n) => n.id);
        tb.selectedId = tb.selectedIds[0] || null;
        render();
        refreshPass2Chrome();
        return;
      }
      if (ev.key === 'Delete' || ev.key === 'Backspace') {
        // Pass1 also handles — if multi, prefer our delete
        if ((A().tb.selectedIds || []).length > 1) {
          ev.preventDefault();
          ev.stopPropagation();
          deleteSelection();
        }
      }
    }, true);
  }

  /* ---------- Chrome refresh ---------- */
  function refreshPass2Chrome() {
    refreshBuildContextUi();
    refreshBulkBar();
    renderInventoryPalette();
    patchNodeAppearance();
    appendPass2Validation();
    if (A().tb.continueOpen) {
      const n = A().activeArea()?.nodes.find((x) => x.id === A().tb.selectedId);
      if ($('tb-continue-from')) {
        $('tb-continue-from').textContent = n?.conveyorTag || n?.label || '—';
      }
      refreshContinueHits();
    }
  }

  /**
   * Explicit render integration (stabilization):
   * Pass1 render() ends with window.__tbOnTransportRender().
   * Do NOT rely on MutationObserver to infer state changes.
   */
  function onTransportRender() {
    try {
      ensureBuildContext();
      const canvas = $('tb-canvas');
      if (canvas) canvas.classList.toggle('tb-show-ports', !!A().tb.showPorts);
      refreshCpFilterUi();
      refreshPass2Chrome();
    } catch (err) {
      try {
        console.warn('[TransportBuild Pass2] onTransportRender', err);
      } catch (_) { /* ignore */ }
    }
  }

  /**
   * Build Transport canvas from imported RUN physical layout.
   * opts.silent — skip confirm/dialogs (used on RUN load auto-build).
   * opts.rebuild — engineer recovery "Rebuild Layout" (warns about visual replace).
   */
  async function autoBuildFromRun(opts) {
    opts = opts || {};
    const silent = !!opts.silent;
    const rebuild = !!opts.rebuild;
    const { tb, save, render, status, askYesNo, showInfo, migrateGraphTopology } = A();
    const api = window.fortnaAPI || window.api;
    if (!api?.transportAutoBuildFromRun) {
      if (!silent) {
        await showInfo(
          'Rebuild Layout',
          'Needs the desktop Site Forge app (Electron IPC).\nImport a RUN, then try again.'
        );
      }
      return { ok: false, error: 'IPC missing' };
    }
    if (!silent) {
      const title = rebuild ? 'Rebuild Layout' : 'Rebuild Layout from RUN';
      const ok = await askYesNo(
        title,
        'Rebuild visual conveyor layout from the imported RUN?\n\n'
          + '• Places conveyors from RUN X/Y/Angle/Length\n'
          + '• Auto-connects only high-confidence OUT→IN mates\n'
          + '• Ambiguous mates are flagged for review\n'
          + '• Does not invent Area/ES Zone names\n\n'
          + 'WARNING: Canvas node positions/wires are replaced from RUN.\n'
          + 'Prefer this only for recovery. Normal commissioning auto-builds on RUN load.\n'
          + 'Undo is available after rebuild.'
      );
      if (!ok) return { ok: false, cancelled: true };
    }
    pushHistory(silent ? 'Auto Build From RUN (load)' : 'Rebuild Layout From RUN');
    status(silent ? 'Building Transportation from RUN…' : 'Rebuild Layout From RUN…');
    let res;
    try {
      // Pass active machine so Auto Build uses ControllerScope, not plant-wide Conveyor.asc
      let machine = '';
      try {
        const ws = await api.getWorkspace?.();
        machine = ws?.active?.machine || ws?.active?.controller || '';
        if (!machine && ws?.active?.project_name) {
          const m = String(ws.active.project_name).match(/_([A-Z0-9]+)$/i);
          if (m) machine = m[1].toUpperCase();
        }
      } catch (_) { /* ignore */ }
      res = await api.transportAutoBuildFromRun(machine ? { machine } : {});
    } catch (err) {
      if (!silent) await showInfo('Rebuild Layout failed', String(err?.message || err));
      status(`Rebuild Layout error: ${err?.message || err}`);
      return { ok: false, error: String(err?.message || err) };
    }
    if (!res?.ok || !res.graph) {
      if (!silent) await showInfo('Rebuild Layout failed', res?.error || 'No graph returned');
      status(`Rebuild Layout failed: ${res?.error || 'unknown'}`);
      return { ok: false, error: res?.error || 'No graph returned' };
    }
    const g = res.graph;
    // ONE transport equipment source: ControllerScope LOCAL + EXTERNAL_REFERENCE only.
    // displayContext neighbors used for geometry mating must NOT paint the whole site.
    tb.suppressDefaultArea = false;
    const rawAreas = Array.isArray(g.areas) ? g.areas : [];
    const keptNodeIds = new Set();
    tb.areas = rawAreas.map((area) => {
      const nodes = (area.nodes || []).filter((n) => {
        const external = !!(n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE');
        const local = n.plcOwned !== false && !n.displayContext && !external
          && n.scopeClass !== 'OUT_OF_SCOPE' && n.scopeClass !== 'UNRESOLVED';
        // Keep compact external stubs; drop non-owned displayContext expansion
        const keep = local || external;
        if (keep && n.id) keptNodeIds.add(n.id);
        return keep;
      }).map((n) => {
        if (n.externalReference || n.scopeClass === 'EXTERNAL_REFERENCE') {
          return {
            ...n,
            displayContext: true,
            plcOwned: false,
            externalReference: true,
            scopeClass: 'EXTERNAL_REFERENCE',
            label: n.label || `→ External ${n.conveyorTag || n.label || ''}`.trim(),
            schematic: true,
            controlPanel: n.controlPanel || '',
          };
        }
        return {
          ...n,
          scopeClass: n.scopeClass || 'LOCAL',
          plcOwned: true,
          displayContext: false,
          controlPanel: n.controlPanel || '',
        };
      });
      const wires = (area.wires || []).filter((w) => keptNodeIds.has(w.from) && keptNodeIds.has(w.to));
      return { ...area, nodes, wires };
    }).filter((a) => (a.nodes || []).length > 0);
    // Auto-populate controlPanel ONLY when RUN evidence is clear; else leave empty
    {
      const { ensureControlPanel } = A();
      (tb.areas || []).forEach((area) => {
        (area.nodes || []).forEach((n) => {
          if (typeof ensureControlPanel === 'function') ensureControlPanel(n, { forceInfer: true });
          else if (n.controlPanel == null) n.controlPanel = '';
        });
      });
    }
    tb.activeAreaId = g.activeAreaId || tb.areas[0]?.id || null;
    tb.selectedId = null;
    tb.selectedIds = [];
    tb.selectedDeviceId = null;
    // CP5A: decoder catalog for unplaced inventory (no invented geometry)
    try {
      tb.decoderInventoryTags = g.decoderInventoryTags || null;
      tb.cp5a = g.cp5a || null;
      if (g.cp5a?.metrics || g.metrics?.cp5a) {
        const c = g.metrics?.cp5a || {};
        status(
          `Decoder map: ${c.cp4ConveyorFamilyObjects ?? '—'} found · `
          + `${c.placedNodes ?? '—'} placed · `
          + `${c.unplacedConveyorCandidates ?? 0} unplaced candidates (geometry UNKNOWN)`
        );
      }
    } catch (_) { /* ignore */ }
    if (tb.areas[0]) {
      tb.buildContext.areaId = tb.areas[0].id;
      tb.buildContext.areaName = tb.areas[0].name || '';
      // Do not invent ES zone from RUN
      tb.buildContext.safetyZone = tb.buildContext.safetyZone || '';
    }
    migrateGraphTopology();
    ensureBuildContext();
    // Presentation transform only — preserve RUN sourceX/Y/Angle/Length/Width
    tb.physicalLayout = !!g.physicalLayout;
    tb.metrics = mSafe(res.metrics || g.metrics || {});
    const localN = (tb.areas || []).reduce((s, a) => s + (a.nodes || []).filter((n) => n.plcOwned && !n.externalReference).length, 0);
    const extN = (tb.areas || []).reduce((s, a) => s + (a.nodes || []).filter((n) => n.externalReference).length, 0);
    tb.metrics = {
      ...tb.metrics,
      ui_local_displayed: localN,
      ui_external_displayed: extN,
      ui_controller_scoped: true,
    };
    if (!tb.view) tb.view = { zoom: 1, canvasScale: null, mode: 'site' };
    if (!tb.layers) tb.layers = {};
    Object.assign(tb.layers, {
      physical: false,
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
    });
    const cs = Number(tb.metrics.canvas_scale || g.canvasScale);
    if (cs && cs > 0) tb.view.canvasScale = cs;
    // Prefer controller-scoped area name (matches Autogen ORNCCP2_Area family).
    // Transport_1 is only the empty-canvas placeholder — rename after Auto Build.
    let mach = '';
    try {
      const ws = await api.getWorkspace?.();
      mach = String(ws?.active?.machine || ws?.active?.controller || '').toUpperCase();
      if (!mach && ws?.active?.project_name) {
        const mm = String(ws.active.project_name).match(/_([A-Z0-9]+)$/i);
        if (mm) mach = mm[1].toUpperCase();
      }
    } catch (_) { /* ignore */ }
    (tb.areas || []).forEach((area) => {
      const nm = String(area.name || '');
      if (/^Transport_\d+$/i.test(nm) || /Imported/i.test(nm) || !nm) {
        area.name = mach ? `${mach}_Area` : (g.areas?.[0]?.name || area.name || 'Transport');
      }
      (area.nodes || []).forEach((n) => {
        if (n.physical && (n.pathCanvas || n.entryCanvas)) n.schematic = true;
      });
    });
    save();
    render();
    // Mark Area / ES as required when RUN did not supply confirmed values
    (tb.areas || []).forEach((area) => {
      const suggested = /_Imported$/i.test(area.name || '') || /RUN_Imported/i.test(area.name || '');
      (area.nodes || []).forEach((n) => {
        const areaName = area.name || '';
        const hasRealArea = areaName && !suggested && !/^ORNCCP\d+_Imported$/i.test(areaName);
        n.areaRequired = !hasRealArea;
        const es = String(n.safetyZone || '').trim();
        const esDefault = !es || /_ESZone1$/i.test(es) || /^UNKNOWN$/i.test(es);
        n.esZoneRequired = esDefault;
        if (esDefault) n.safetyZone = n.safetyZone || '';
      });
    });
    tb.viewMode = 'schematic';
    if (tb.layers) tb.layers.physical = false;
    if (tb.workflow) tb.workflow.autobuild = true;
    // Seed first-class Safety Zones from RUN-proven conveyor.safetyZone only
    // (never invent from Area names). Engineer zones remain authoritative later.
    try {
      if (typeof A().seedSafetyZonesFromNodes === 'function') {
        A().seedSafetyZonesFromNodes({ preserveEngineer: true });
      }
    } catch (_) { /* ignore */ }
    try { A().setWorkflowStep?.('review', { done: true }); } catch (_) { /* ignore */ }
    // Frame visible working set (single Fit semantics)
    try {
      if (typeof A().fitVisible === 'function') A().fitVisible();
      else if (typeof A().fitSite === 'function') A().fitSite();
    } catch (_) { /* ignore */ }
    const m = tb.metrics || {};
    const needArea = (tb.areas || []).reduce((s, a) => s + (a.nodes || []).filter((n) => n.areaRequired).length, 0);
    const needEs = (tb.areas || []).reduce((s, a) => s + (a.nodes || []).filter((n) => n.esZoneRequired).length, 0);
    const detail = [
      `Conveyors placed: ${m.conveyors_placed ?? '—'} / ${m.conveyors_discovered ?? '—'}`,
      `Auto connections: ${m.auto_connections ?? '—'} · Ambiguous: ${m.ambiguous_connections ?? '—'}`,
      `AREA REQUIRED: ${needArea} · ES ZONE REQUIRED: ${needEs}`,
      '',
      'Next: Review / Correct → Apply to Autogen → Build PLC',
      'Clean schematic is the normal view. Geometry debug is under Advanced.',
    ].join('\n');
    if (!silent) {
      await showInfo('Rebuild Layout complete', res.summary || 'Layout imported — review & correct.', detail);
    }
    status(
      silent
        ? (res.summary || 'Transportation built from RUN · Top-Centered')
        : (res.summary || 'Rebuild Layout complete — Review / Correct, then Apply to Autogen')
    );
    return { ok: true, summary: res.summary || '', metrics: m };
  }

  // Expose for RUN-load auto-build (silent) and recovery Rebuild Layout
  window.transportAutoBuildFromRun = autoBuildFromRun;

  function mSafe(obj) {
    return obj && typeof obj === 'object' ? obj : {};
  }

  function bindUi() {
    $('tb-auto-build-run')?.addEventListener('click', () => {
      autoBuildFromRun({ rebuild: true }).catch((err) => A().status(`Rebuild Layout error: ${err?.message || err}`));
    });
    $('tb-show-unresolved-topo')?.addEventListener('click', () => {
      try {
        if (typeof A().showUnresolvedTopology === 'function') A().showUnresolvedTopology();
        else A().status('Show Unresolved Topology unavailable');
      } catch (err) {
        A().status(`Unresolved topology: ${err?.message || err}`);
      }
    });
    $('tb-fit')?.addEventListener('click', () => {
      try { A().fitVisible?.(); } catch (err) { A().status(`Fit: ${err?.message || err}`); }
    });
    $('tb-fit-visible')?.addEventListener('click', () => {
      try { A().fitVisible?.(); document.getElementById('tb-fit-menu')?.removeAttribute('open'); } catch (err) { A().status(`Fit Visible: ${err?.message || err}`); }
    });
    $('tb-fit-all')?.addEventListener('click', () => {
      try { A().fitAll?.(); document.getElementById('tb-fit-menu')?.removeAttribute('open'); } catch (err) { A().status(`Fit All: ${err?.message || err}`); }
    });
    $('tb-fit-site')?.addEventListener('click', () => {
      try { A().fitSite?.(); document.getElementById('tb-fit-menu')?.removeAttribute('open'); } catch (err) { A().status(`Fit Site: ${err?.message || err}`); }
    });
    $('tb-fit-area')?.addEventListener('click', () => {
      try { A().fitArea?.(); document.getElementById('tb-fit-menu')?.removeAttribute('open'); } catch (err) { A().status(`Fit Area: ${err?.message || err}`); }
    });
    $('tb-fit-selection')?.addEventListener('click', () => {
      try { A().fitSelection?.(); document.getElementById('tb-fit-menu')?.removeAttribute('open'); } catch (err) { A().status(`Frame Selection: ${err?.message || err}`); }
    });
    const reset100 = () => {
      try {
        if (typeof A().resetView100 === 'function') A().resetView100();
        else {
          const { tb, applyViewportZoom, render, status } = A();
          if (!tb.view) tb.view = { zoom: 1, canvasScale: null, mode: 'site' };
          tb.view.zoom = 1;
          applyViewportZoom?.();
          const c = $('tb-canvas');
          if (c) { c.scrollLeft = 0; c.scrollTop = 0; }
          render?.();
          status?.('Reset View · 100% (presentation only)');
        }
        document.getElementById('tb-fit-menu')?.removeAttribute('open');
      } catch (err) {
        A().status(`Reset View: ${err?.message || err}`);
      }
    };
    $('tb-zoom-100')?.addEventListener('click', reset100);
    $('tb-zoom-reset')?.addEventListener('click', reset100);
    $('tb-zoom-in')?.addEventListener('click', () => {
      try {
        if (typeof A().zoomByFactor === 'function') A().zoomByFactor(1.15);
        else A().status('Zoom + unavailable');
      } catch (err) { A().status(`Zoom +: ${err?.message || err}`); }
    });
    $('tb-zoom-out')?.addEventListener('click', () => {
      try {
        if (typeof A().zoomByFactor === 'function') A().zoomByFactor(1 / 1.15);
        else A().status('Zoom − unavailable');
      } catch (err) { A().status(`Zoom −: ${err?.message || err}`); }
    });
    $('tb-advanced-debug')?.addEventListener('change', (ev) => {
      const { tb, render, status } = A();
      tb.viewMode = ev.target.checked ? 'geom-debug' : 'schematic';
      if (!tb.layers) tb.layers = {};
      tb.layers.physical = !!ev.target.checked;
      const phys = $('tb-layer-physical');
      if (phys) phys.checked = !!ev.target.checked;
      render();
      status(ev.target.checked ? 'Geometry debug ON (Advanced)' : 'Clean schematic (normal)');
    });
    $('tb-lane-separate')?.addEventListener('change', (ev) => {
      const { tb, render, status } = A();
      tb.laneSeparate = !!ev.target.checked;
      render();
      status(`Lane separation ${tb.laneSeparate ? 'ON' : 'OFF'} (presentation only)`);
    });
    $('tb-layer-physical')?.addEventListener('change', (ev) => {
      const { tb, render, status } = A();
      if (!tb.layers) tb.layers = {};
      tb.layers.physical = !!ev.target.checked;
      tb.viewMode = ev.target.checked ? 'geom-debug' : 'schematic';
      const adv = $('tb-advanced-debug');
      if (adv) adv.checked = !!ev.target.checked;
      render();
      status(`Physical debug ${tb.layers.physical ? 'on' : 'off'}`);
    });
    const bindLayer = (id, key) => {
      $(id)?.addEventListener('change', (ev) => {
        const { tb, render, save, status } = A();
        if (!tb.layers) tb.layers = {};
        tb.layers[key] = !!ev.target.checked;
        try { save(); } catch (_) { /* ignore */ }
        render();
        status(`Layer ${key}: ${tb.layers[key] ? 'ON' : 'OFF'}`);
      });
    };
    bindLayer('tb-layer-conv-tags', 'conveyorTags');
    bindLayer('tb-layer-motors', 'motors');
    bindLayer('tb-layer-pe', 'photoeyes');
    bindLayer('tb-layer-other', 'otherDevices');
    bindLayer('tb-layer-device-labels', 'deviceLabels');
    bindLayer('tb-layer-external', 'externalRefs');
    $('tb-goto-build-plc')?.addEventListener('click', () => {
      try {
        if (typeof window.activateTab === 'function') window.activateTab('autogen');
        else document.querySelector('[data-tab="autogen"]')?.click();
        setTimeout(() => $('btn-autogen-from-run')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 150);
        A().status('PLC Autogen — use Export L5X Package to Build PLC');
      } catch (err) {
        A().status(`Build PLC: ${err?.message || err}`);
      }
    });
    $('tb-build-chain')?.addEventListener('click', () => openChainDialog());
    $('tb-chain-cancel')?.addEventListener('click', () => closeChainDialog());
    $('tb-chain-input')?.addEventListener('input', () => updateChainPreview());
    $('tb-chain-ok')?.addEventListener('click', () => {
      const tags = parseChainText($('tb-chain-input')?.value || '');
      const allow = !!$('tb-chain-allow-unknown')?.checked;
      const analysis = analyzeChainTags(tags);
      if (analysis.unknown.length && !allow) {
        updateChainPreview();
        A().status('Resolve unknown tags or check “Allow unknown…”');
        return;
      }
      if (commitChain(tags, { allowUnknown: allow })) closeChainDialog();
    });

    $('tb-continue-run')?.addEventListener('click', () => openContinueRun());
    $('tb-continue-close')?.addEventListener('click', () => closeContinueRun());
    $('tb-continue-input')?.addEventListener('input', () => refreshContinueHits());
    $('tb-continue-go')?.addEventListener('click', () => {
      const q = ($('tb-continue-input')?.value || '').trim();
      const hits = unplacedConveyors(q);
      const pick = hits.find((t) => t.toUpperCase() === q.toUpperCase()) || hits[0];
      if (pick) continueRunTo(pick);
    });

    $('tb-auto-layout')?.addEventListener('click', () => {
      if ((A().tb.selectedIds || []).length > 1) autoLayoutSelection();
      else autoLayoutArea();
    });
    $('tb-undo')?.addEventListener('click', () => undo());
    $('tb-redo')?.addEventListener('click', () => redo());

    $('tb-ctx-area')?.addEventListener('change', (e) => {
      const { tb, save } = A();
      const a = tb.areas.find((x) => x.id === e.target.value);
      if (!a) return;
      tb.buildContext.areaId = a.id;
      tb.buildContext.areaName = a.name;
      // Don't overwrite custom ES unless empty / default-like
      if (!tb.buildContext.safetyZone || /_ESZone1$/i.test(tb.buildContext.safetyZone)) {
        tb.buildContext.safetyZone = defaultEsZone(a.name);
      }
      // Switch canvas to that area for convenience
      tb.activeAreaId = a.id;
      save();
      A().render();
      refreshPass2Chrome();
    });
    $('tb-ctx-eszone')?.addEventListener('change', (e) => {
      A().tb.buildContext.safetyZone = e.target.value.trim();
      A().save();
    });
    $('tb-ctx-apply-sel')?.addEventListener('click', () => applyContextToSelection());

    $('tb-bulk-apply')?.addEventListener('click', () => applyBulkEdit());
    $('tb-bulk-create-area')?.addEventListener('click', () => {
      createAreaFromSelection().catch((err) => A().status(`Create Area error: ${err?.message || err}`));
    });
    $('tb-bulk-add-to-area')?.addEventListener('click', () => {
      addSelectionToArea().catch((err) => A().status(`Add to Area error: ${err?.message || err}`));
    });
    $('tb-bulk-remove-from-area')?.addEventListener('click', () => {
      removeSelectionFromArea().catch((err) => A().status(`Remove from Area error: ${err?.message || err}`));
    });
    $('tb-bulk-delete')?.addEventListener('click', () => deleteSelection());
    $('tb-bulk-chain')?.addEventListener('click', () => selectChainFromPrimary());
    $('tb-bulk-align')?.addEventListener('click', () => alignSelection());
    $('tb-bulk-space')?.addEventListener('click', () => spaceEvenlySelection());
    $('tb-bulk-layout')?.addEventListener('click', () => autoLayoutSelection());
    $('tb-bulk-terminal')?.addEventListener('click', () => markTerminalSelection(true));
    $('tb-bulk-cp-apply')?.addEventListener('click', () => {
      applyControlPanelToSelection($('tb-bulk-cp')?.value || '');
    });
    $('tb-bulk-cp')?.addEventListener('change', (e) => {
      // Immediate assign on choose (CP1/CP2/CP3/Other/clear). Ignore placeholder "—".
      const v = String(e.target.value || '').trim();
      if (!v) return;
      applyControlPanelToSelection(v === 'clear' ? '' : v);
    });
    // CP filter checkboxes are bound dynamically in refreshCpFilterUi() after Auto Build

    $('tb-inv-filter')?.addEventListener('input', () => renderInventoryPalette());

    document.querySelectorAll('#tb-ctx-menu [data-tb-ctx]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const act = btn.getAttribute('data-tb-ctx');
        const id = $('tb-ctx-menu')?.dataset.nodeId;
        hideCtxMenu();
        if (id) ensureCtxSelection(id);
        if (act === 'continue') openContinueRun();
        else if (act === 'terminal') markTerminalSelection(true);
        else if (act === 'unterminate') markTerminalSelection(false);
        else if (act === 'select-chain') selectChainFromPrimary();
        else if (act === 'area-new') {
          createAreaFromSelection().catch((err) => A().status(`Add to New Area: ${err?.message || err}`));
        } else if (act === 'area-existing') {
          addSelectionToArea().catch((err) => A().status(`Add to Existing Area: ${err?.message || err}`));
        } else if (act === 'area-remove') {
          removeSelectionFromArea().catch((err) => A().status(`Remove from Area: ${err?.message || err}`));
        } else if (act === 'delete') deleteSelection();
      });
    });
    document.addEventListener('click', (ev) => {
      if (!ev.target.closest?.('#tb-ctx-menu')) hideCtxMenu();
    });

    const canvas = $('tb-canvas');
    canvas?.addEventListener('mousedown', (ev) => {
      // Middle-mouse drag = pan (CAD-style); scrollbars remain as fallback
      if (ev.button === 1) {
        ev.preventDefault();
        const { tb } = A();
        tb.panning = {
          sx: ev.clientX,
          sy: ev.clientY,
          sl: canvas.scrollLeft,
          st: canvas.scrollTop,
        };
        canvas.classList.add('tb-panning');
        canvas.style.cursor = 'grabbing';
        return;
      }
      onCanvasMouseDown(ev);
    });
    window.addEventListener('mousemove', onCanvasMouseMove);
    window.addEventListener('mouseup', (ev) => {
      const { tb, save } = A();
      if (tb.panning) {
        tb.panning = null;
        canvas?.classList.remove('tb-panning');
        if (canvas) canvas.style.cursor = tb.spacePan ? 'grab' : '';
      }
      if (tb.moving && tb._moveHistoryPushed) {
        tb._moveHistoryPushed = false;
        try { save(); } catch (_) { /* ignore */ }
      }
      onCanvasMouseUp(ev);
    });
    // CAD-style navigation (presentation only — does not mutate equipment coordinates)
    // CTRL+wheel = zoom @ cursor · plain wheel = native scroll · Mid/empty-drag = pan
    canvas?.addEventListener('wheel', (ev) => {
      const { tb, render, applyViewportZoom, viewportZoomLimits, status } = A();
      if (!tb.view) tb.view = { zoom: 1, canvasScale: null, mode: 'site' };

      // Zoom ONLY with Ctrl/Meta + wheel (around cursor). Plain wheel must not zoom.
      if (!(ev.ctrlKey || ev.metaKey)) {
        // Shift+wheel → horizontal pan convenience; otherwise let native scroll work
        if (ev.shiftKey) {
          ev.preventDefault();
          const delta = Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY;
          canvas.scrollLeft += delta;
        }
        return;
      }

      ev.preventDefault();
      const lim = typeof viewportZoomLimits === 'function'
        ? viewportZoomLimits()
        : { min: tb.physicalLayout ? 0.05 : 0.25, max: 3 };
      const before = Math.max(lim.min, Number(tb.view.zoom) || 1);
      const factor = ev.deltaY < 0 ? 1.1 : 0.9;
      const next = Math.max(lim.min, Math.min(lim.max, before * factor));
      if (Math.abs(next - before) < 0.001) return;
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left + canvas.scrollLeft;
      const my = ev.clientY - rect.top + canvas.scrollTop;
      const cx = mx / before;
      const cy = my / before;
      tb.view.zoom = next;
      if (typeof applyViewportZoom === 'function') applyViewportZoom();
      else render();
      canvas.scrollLeft = cx * next - (ev.clientX - rect.left);
      canvas.scrollTop = cy * next - (ev.clientY - rect.top);
      status(`Zoom ${Math.round(next * 100)}% (Ctrl+wheel · presentation only)`);
      render();
    }, { passive: false });
    // Prevent middle-click autoscroll chrome behavior
    canvas?.addEventListener('auxclick', (ev) => {
      if (ev.button === 1) ev.preventDefault();
    });
    // Space = temporary hand/pan cursor (does not mutate topology)
    document.addEventListener('keydown', (ev) => {
      if (ev.code !== 'Space' || ev.repeat) return;
      if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/i.test(ev.target.tagName)) return;
      const { tb } = A();
      tb.spacePan = true;
      if (canvas && !tb.panning) canvas.style.cursor = 'grab';
    });
    document.addEventListener('keyup', (ev) => {
      if (ev.code !== 'Space') return;
      const { tb } = A();
      tb.spacePan = false;
      if (canvas && !tb.panning) canvas.style.cursor = '';
    });

    // When area select changes, sync build context area id if matching
    $('tb-area-select')?.addEventListener('change', () => {
      setTimeout(() => {
        ensureBuildContext();
        const { tb } = A();
        const area = A().activeArea();
        if (area && tb.buildContext.areaId === area.id) {
          tb.buildContext.areaName = area.name;
        }
        refreshPass2Chrome();
      }, 0);
    });

    patchNodeMouseHandlers();
    patchMultiDrag();
    bindPass2Keys();
  }

  function appendPass2Validation() {
    const el = $('tb-validation');
    if (!el) return;
    const { tb, isConv, escapeHtml } = A();
    const extra = [];
    (tb.areas || []).forEach((area) => {
      (area.nodes || []).forEach((n) => {
        if (!isConv(n.kind)) return;
        if (n.mergeGenSupported === false) {
          extra.push(
            `<div class="tb-val-warn">• ${escapeHtml(n.conveyorTag || n.label)}: CONFIGURATION REQUIRED / GENERATION NOT YET SUPPORTED (3:1+)</div>`
          );
        }
        if ((n.ambiguousInbound || []).length) {
          const froms = n.ambiguousInbound.map((x) => x.from).filter(Boolean).join(', ');
          extra.push(
            `<div class="tb-val-warn">• ${escapeHtml(n.conveyorTag || n.label)}: ambiguous inbound (${escapeHtml(froms)}) — confirm OUT→IN</div>`
          );
        }
      });
    });
    if (extra.length) el.insertAdjacentHTML('beforeend', extra.join(''));
  }

  function initPass2() {
    if (!api()) {
      setTimeout(initPass2, 50);
      return;
    }
    ensureBuildContext();
    installHooks();
    patchHistoryHooks();
    window.__tbOnTransportRender = onTransportRender;
    bindUi();
    onTransportRender();
    A().status('Transport Build Pass 2 ready — Build Chain · Continue Run · Build Context');
  }

  window.__tbPass2Init = initPass2;
  window.__tbPass2OnRefresh = onTransportRender;

  // Self-test hooks for acceptance C (undo)
  window.__tbPass2SelfTest = {
    parseChainText,
    pushHistory,
    undo,
    redo,
    snapshot,
    restoreSnapshot,
    commitChain,
    continueRunTo,
    autoLayoutArea,
    defaultEsZone,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initPass2, 0));
  } else {
    setTimeout(initPass2, 0);
  }
})();
