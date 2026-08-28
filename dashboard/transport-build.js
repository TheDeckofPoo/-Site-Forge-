/* Transport Build POC — Node-RED style conveyor graph (visual only).
 * Persists to localStorage. Future: feed graph JSON to fortna_autogen.
 */
(function () {
  const STORE_KEY = 'siteforge.transportBuild.v1';

  const KIND_META = {
    conv_straight: { icon: 'fa-minus', color: 'text-sky-300', isConv: true, title: 'Straight' },
    conv_right: { icon: 'fa-arrow-turn-up fa-rotate-90', color: 'text-sky-300', isConv: true, title: '90° Right' },
    conv_left: { icon: 'fa-arrow-turn-down fa-rotate-270', color: 'text-sky-300', isConv: true, title: '90° Left' },
    conv_merge: { icon: 'fa-code-merge', color: 'text-orange-300', isConv: true, isMerge: true, title: 'Merge' },
    motor: { icon: 'fa-gear', color: 'text-amber-300', isConv: false, title: 'Motor' },
    estop: { icon: 'fa-hand', color: 'text-red-300', isConv: false, title: 'E-Stop' },
    pws: { icon: 'fa-bolt', color: 'text-yellow-300', isConv: false, title: 'Power Supply' },
    encoder: { icon: 'fa-compact-disc', color: 'text-violet-300', isConv: false, title: 'Encoder' },
    photoeye: { icon: 'fa-eye', color: 'text-emerald-300', isConv: false, title: 'Photoeye' },
  };

  const tb = {
    areas: [],
    activeAreaId: null,
    selectedId: null, // conveyor node id
    selectedDeviceId: null, // device id on that conveyor (inspector device mode)
    dragKind: null,
    linkFrom: null, // { nodeId, port }
    moving: null, // { id, ox, oy }
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
        input.style.display = show ? '' : 'none';
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

      dlg.classList.remove('hidden');
      dlg.style.display = 'flex';

      const finish = (val) => {
        dlg.classList.add('hidden');
        dlg.style.display = 'none';
        ok.onclick = null;
        cancel.onclick = null;
        if (input) input.onkeydown = null;
        resolve(val);
      };
      cancel.onclick = () => finish(showInput ? null : false);
      ok.onclick = () => finish(showInput ? (input?.value ?? '') : true);
      if (showInput && input) {
        setTimeout(() => { try { input.focus(); input.select(); } catch (_) { /* ignore */ } }, 30);
        input.onkeydown = (e) => {
          if (e.key === 'Enter') { e.preventDefault(); finish(input.value); }
          if (e.key === 'Escape') { e.preventDefault(); finish(null); }
        };
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
    if (!tb.areas.length) {
      const a = { id: uid('area'), name: 'Transport_1', nodes: [], wires: [] };
      tb.areas.push(a);
      tb.activeAreaId = a.id;
    }
    if (!activeArea()) tb.activeAreaId = tb.areas[0].id;
  }

  function save() {
    try {
      localStorage.setItem(
        STORE_KEY,
        JSON.stringify({ areas: tb.areas, activeAreaId: tb.activeAreaId })
      );
    } catch (_) { /* ignore */ }
  }

  function load() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (Array.isArray(data.areas)) tb.areas = data.areas;
      tb.activeAreaId = data.activeAreaId || (tb.areas[0] && tb.areas[0].id) || null;
    } catch (_) { /* ignore */ }
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
    return [...opts].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  /** Name regex / kind filters for device tag dropdowns. */
  function deviceTagMatches(kind, name, equipmentKind) {
    const n = String(name || '').trim();
    if (!n) return false;
    const ek = String(equipmentKind || '').toLowerCase();
    const u = n.toUpperCase();
    if (kind === 'encoder') {
      return ek === 'encoder' || /^ENC\d/i.test(n) || u.startsWith('ENC');
    }
    if (kind === 'photoeye') {
      // Must contain "PE" (PE208, EZPE116_F, …) — reject random tags
      if (!/PE/i.test(n)) return false;
      return ek === 'photoeye' || /PE/i.test(n);
    }
    if (kind === 'motor') {
      // Strict: M + digits (optional single letter / _AUX) or VFD### — not MSG, MDAY, MDR, MCR…
      if (ek === 'vfd' || /^VFD\d/i.test(n)) return true;
      if (/^M\d+[A-Z]?(?:_AUX)?$/i.test(n)) return true;
      if (ek === 'motor' && /^M\d/i.test(n) && !/^(MCR|MDR|MSG|MDAY|MEM|MX)/i.test(u)) return true;
      return false;
    }
    if (kind === 'estop') {
      return (
        ek === 'estop' ||
        /^ESL?\d/i.test(n) ||
        /^ESTP\d/i.test(n) ||
        /^ESPB\d/i.test(n) ||
        /^\d+ES\d/i.test(n) ||
        /MCR/i.test(n)
      );
    }
    if (kind === 'pws') {
      return ek === 'power_supply' || /^EZPWS/i.test(n) || /^PWS\d/i.test(n) || /^PS\d/i.test(n);
    }
    return false;
  }

  function deviceTagOptions(kind) {
    const opts = new Set();
    const push = (name, ek) => {
      if (deviceTagMatches(kind, name, ek)) opts.add(String(name).trim());
    };
    try {
      if (typeof state !== 'undefined' && Array.isArray(state.devices)) {
        state.devices.forEach((d) => {
          push(d.name || d.fortna_name || d.tag, d.equipment_kind || d.category || d.device_type);
        });
      }
    } catch (_) { /* ignore */ }
    try {
      if (typeof autogenState !== 'undefined' && Array.isArray(autogenState.workbook?.io)) {
        autogenState.workbook.io.forEach((r) => {
          push(r.device || r.fortna_name || r.name, r.device_type || r.equipment_kind);
        });
      }
    } catch (_) { /* ignore */ }
    // Also scan workbook conveyors' linked names is rare — skip
    return [...opts].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  function fillTagSelect(sel, kind, selected) {
    if (!sel) return;
    const opts = deviceTagOptions(kind);
    let html = `<option value="">— select ${kind} tag from RUN —</option>`;
    opts.forEach((t) => {
      html += `<option value="${escapeHtml(t)}" ${t === selected ? 'selected' : ''}>${escapeHtml(t)}</option>`;
    });
    if (selected && !opts.includes(selected)) {
      html += `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} (custom)</option>`;
    }
    sel.innerHTML = html;
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

  function nodeAtPoint(x, y, area) {
    // Hit-test conveyors for device drop (top-most by list order)
    for (let i = area.nodes.length - 1; i >= 0; i--) {
      const n = area.nodes[i];
      if (!isConv(n.kind)) continue;
      const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      const host = $('tb-nodes').getBoundingClientRect();
      const left = r.left - host.left;
      const top = r.top - host.top;
      if (x >= left && x <= left + r.width && y >= top && y <= top + r.height) return n;
    }
    return null;
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

    host.innerHTML = '';
    (area?.nodes || []).forEach((n) => {
      const meta = KIND_META[n.kind] || { icon: 'fa-cube', color: 'text-slate-300', title: n.kind };
      const el = document.createElement('div');
      el.className = `tb-node${n.id === tb.selectedId ? ' selected' : ''}${meta.isMerge ? ' tb-merge' : ''}`;
      el.dataset.id = n.id;
      el.style.left = `${n.x}px`;
      el.style.top = `${n.y}px`;
      const rot = Number(n.rotation || 0) % 360;
      if (rot) el.style.transform = `rotate(${rot}deg)`;

      const devices = n.devices || [];
      const chips = devices
        .map((d) => {
          const dm = KIND_META[d.kind] || {};
          const label = d.tag || d.name || d.kind;
          const sel = d.id === tb.selectedDeviceId ? ' ring-1 ring-fuchsia-500' : '';
          return `<span class="tb-device-chip${sel} cursor-pointer" data-dev-id="${escapeHtml(d.id)}" title="Click to assign tag"><i class="fa-solid ${dm.icon || 'fa-circle'} ${dm.color || ''}"></i>${escapeHtml(label)}</span>`;
        })
        .join('');

      const bind = n.conveyorTag
        ? `<div class="mono text-cyan-400/90 truncate">${escapeHtml(n.conveyorTag)}</div>`
        : `<div class="text-slate-600 italic">No conveyor bound</div>`;
      const mergeNote = meta.isMerge
        ? `<div class="text-orange-400/80 text-[9px] mt-0.5">${n.inPorts || 2}:1 merge</div>`
        : '';

      let portsHtml = '';
      if (isConv(n.kind)) {
        const inCount = meta.isMerge ? Math.max(2, Number(n.inPorts) || 2) : 1;
        if (inCount === 1) {
          portsHtml += `<div class="tb-port in" data-port="in" title="Entrance"></div>`;
        } else {
          for (let i = 0; i < inCount; i++) {
            const pct = ((i + 1) / (inCount + 1)) * 100;
            portsHtml += `<div class="tb-port in" data-port="in${i}" style="top:${pct}%;transform:translateY(-50%)" title="Entrance ${i + 1}"></div>`;
          }
        }
        portsHtml += `<div class="tb-port out" data-port="out" title="Exit"></div>`;
      }

      el.innerHTML = `
        <div class="tb-head">
          <i class="fa-solid ${meta.icon} ${meta.color}"></i>
          <span class="truncate">${escapeHtml(n.label || meta.title)}</span>
        </div>
        <div class="tb-body">
          ${isConv(n.kind) ? bind : ''}
          ${mergeNote}
          <div class="mt-1 flex flex-wrap">${chips || (isConv(n.kind) ? '<span class="text-slate-700 text-[9px]">No devices</span>' : '')}</div>
        </div>
        ${portsHtml}
      `;

      el.addEventListener('mousedown', (ev) => {
        if (ev.target.classList.contains('tb-port')) return;
        const chip = ev.target.closest?.('[data-dev-id]');
        if (chip) {
          ev.stopPropagation();
          tb.selectedId = n.id;
          tb.selectedDeviceId = chip.dataset.devId;
          render();
          return;
        }
        selectNode(n.id);
        tb.moving = {
          id: n.id,
          ox: ev.clientX - n.x,
          oy: ev.clientY - n.y,
        };
        ev.preventDefault();
      });

      el.querySelectorAll('.tb-port').forEach((port) => {
        port.addEventListener('mousedown', (ev) => {
          ev.stopPropagation();
          if (port.dataset.port !== 'out') return;
          tb.linkFrom = { nodeId: n.id, port: 'out' };
          port.classList.add('linking');
          status(`Linking from ${n.label || n.id} exit → drop on another entrance`);
        });
      });

      host.appendChild(el);
    });

    drawWires();
    renderInspector();
  }

  function portCenter(nodeId, port) {
    const el = document.querySelector(`.tb-node[data-id="${nodeId}"]`);
    if (!el) return null;
    const key = port || 'in';
    let p = el.querySelector(`.tb-port[data-port="${key}"]`);
    if (!p && key === 'in') p = el.querySelector('.tb-port.in');
    if (!p && String(key).startsWith('in')) p = el.querySelector(`.tb-port[data-port="${key}"]`);
    const host = $('tb-nodes');
    if (!p || !host) return null;
    const pr = p.getBoundingClientRect();
    const hr = host.getBoundingClientRect();
    return {
      x: pr.left + pr.width / 2 - hr.left,
      y: pr.top + pr.height / 2 - hr.top,
    };
  }

  function drawWires(temp) {
    const svg = $('tb-wires');
    const host = $('tb-nodes');
    if (!svg || !host) return;
    const area = activeArea();
    svg.setAttribute('width', host.scrollWidth || host.offsetWidth);
    svg.setAttribute('height', host.scrollHeight || host.offsetHeight);
    let html = '';
    (area?.wires || []).forEach((w) => {
      const a = portCenter(w.from, 'out');
      const b = portCenter(w.to, w.toPort || 'in');
      if (!a || !b) return;
      const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
      const d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
      html += `<path class="tb-wire" d="${d}" />`;
    });
    if (temp && temp.from && temp.to) {
      const dx = Math.max(40, Math.abs(temp.to.x - temp.from.x) * 0.45);
      const d = `M ${temp.from.x} ${temp.from.y} C ${temp.from.x + dx} ${temp.from.y}, ${temp.to.x - dx} ${temp.to.y}, ${temp.to.x} ${temp.to.y}`;
      html += `<path class="tb-wire tb-wire-temp" d="${d}" />`;
    }
    svg.innerHTML = html;
  }

  function selectNode(id) {
    tb.selectedId = id;
    tb.selectedDeviceId = null;
    render();
  }

  function renderInspector() {
    const empty = $('tb-inspector-empty');
    const panel = $('tb-inspector');
    const area = activeArea();
    const n = area?.nodes.find((x) => x.id === tb.selectedId);
    if (!n) {
      empty?.classList.remove('hidden');
      panel?.classList.add('hidden');
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
          encoder: 'ENC* tags only',
          photoeye: 'Any tag containing PE (PE208, EZPE116_F, …)',
          motor: 'M### / VFD### only',
          estop: 'ES* / ESTP* / MCR* only',
          pws: 'EZPWS* / PWS* only',
        };
        hint.textContent = hints[dev.kind] || 'Tags matching this device type from the active RUN.';
      }
      fillTagSelect($('tb-insp-dev-tag'), dev.kind, dev.tag || dev.name || '');
      return;
    }

    // Conveyor mode
    convPanel?.classList.remove('hidden');
    devPanel?.classList.add('hidden');
    $('tb-insp-kind').textContent = `${meta.title || n.kind} (${n.kind})`;
    if ($('tb-insp-label')) $('tb-insp-label').value = n.label || '';
    if ($('tb-insp-rotation')) $('tb-insp-rotation').textContent = `${Number(n.rotation || 0) % 360}°`;
    const mergeWrap = $('tb-insp-merge-wrap');
    if (mergeWrap) {
      mergeWrap.classList.toggle('hidden', !meta.isMerge);
      const laneSel = $('tb-insp-merge-lanes');
      if (laneSel && meta.isMerge) laneSel.value = String(n.inPorts || 2);
    }

    const convWrap = $('tb-insp-conv-wrap');
    if (convWrap) convWrap.classList.toggle('hidden', !isConv(n.kind));

    const sel = $('tb-insp-conveyor');
    if (sel && isConv(n.kind)) {
      const opts = conveyorOptions();
      sel.innerHTML =
        `<option value="">— select P### from RUN —</option>` +
        opts
          .map(
            (c) =>
              `<option value="${escapeHtml(c)}" ${c === n.conveyorTag ? 'selected' : ''}>${escapeHtml(c)}</option>`
          )
          .join('');
      if (n.conveyorTag && !opts.includes(n.conveyorTag)) {
        sel.innerHTML += `<option value="${escapeHtml(n.conveyorTag)}" selected>${escapeHtml(n.conveyorTag)} (custom)</option>`;
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
            const dm = KIND_META[d.kind] || {};
            const label = d.tag || d.name || d.kind;
            return `<div class="flex items-center gap-2 text-[10px] bg-slate-900/80 border border-slate-800 rounded-lg px-2 py-1 cursor-pointer hover:border-fuchsia-700/50" data-sel-dev="${escapeHtml(d.id)}">
              <i class="fa-solid ${dm.icon || 'fa-circle'} ${dm.color || 'text-slate-400'}"></i>
              <span class="flex-1 truncate">${escapeHtml(label)}</span>
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
    // Prefill attach-row tag list for default kind
    const addKind = $('tb-insp-device-kind')?.value || 'motor';
    fillTagSelect($('tb-insp-device-tag-new'), addKind, '');
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
      if (!target.devices) target.devices = [];
      const newDev = {
        id: uid('dev'),
        kind,
        name: `${meta.title}_${target.devices.length + 1}`,
        tag: '',
      };
      target.devices.push(newDev);
      tb.selectedId = target.id;
      tb.selectedDeviceId = newDev.id; // open tag picker for this device
      save();
      render();
      status(`Attached ${meta.title} — pick a ${kind} tag from the RUN list`);
      return;
    }

    // Don't call prompt() inside drop handlers — Electron/Chromium often cancels the drop.
    // Merges default to 2:1; change lanes in the inspector (or we ask right after render).
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
    };
    area.nodes.push(node);
    tb.selectedId = node.id;
    tb.selectedDeviceId = null;
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
    } else {
      status(`Added ${meta.title} — bind a controller conveyor in the inspector`);
    }
  }

  function connect(fromId, toId, toPort) {
    const area = activeArea();
    if (!area || fromId === toId) return;
    const from = area.nodes.find((n) => n.id === fromId);
    const to = area.nodes.find((n) => n.id === toId);
    if (!from || !to || !isConv(from.kind) || !isConv(to.kind)) {
      status('Only conveyor exit → conveyor entrance links are allowed.');
      return;
    }
    const port = toPort || 'in';
    if (area.wires.some((w) => w.from === fromId && w.to === toId && (w.toPort || 'in') === port)) {
      status('Already connected.');
      return;
    }
    // One wire per merge entrance
    if (port !== 'in') {
      area.wires = area.wires.filter((w) => !(w.to === toId && (w.toPort || 'in') === port));
    }
    area.wires.push({ id: uid('wire'), from: fromId, to: toId, toPort: port });
    save();
    render();
    status(`Connected ${from.label || fromId} → ${to.label || toId} (${port})`);
  }

  function bindToolbar() {
    // Toolbar first — never gated on canvas existing (fixes silent New Area / Build POC)
    $('tb-area-select')?.addEventListener('change', (e) => {
      tb.activeAreaId = e.target.value;
      tb.selectedId = null;
      save();
      render();
    });

    $('tb-area-new')?.addEventListener('click', async () => {
      try {
        const def = `Transport_${tb.areas.length + 1}`;
        // Always create immediately so the click never feels dead, then offer rename.
        const a = { id: uid('area'), name: def, nodes: [], wires: [] };
        tb.areas.push(a);
        tb.activeAreaId = a.id;
        tb.selectedId = null;
        tb.selectedDeviceId = null;
        save();
        render();
        status(`Created area “${a.name}”`);

        const name = await askText(
          'New transport area',
          'Rename this area? (matches a Fast/Slow area in Autogen later)',
          def
        );
        if (name !== null && (name || '').trim() && (name || '').trim() !== a.name) {
          a.name = name.trim();
          save();
          render();
        }
        status(`Area “${a.name}” ready — drag a conveyor onto the grid`);
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

    $('tb-area-delete')?.addEventListener('click', async () => {
      const a = activeArea();
      if (!a) return;
      const ok = await askYesNo('Delete area', `Delete area “${a.name}” and its canvas?`);
      if (!ok) return;
      tb.areas = tb.areas.filter((x) => x.id !== a.id);
      tb.activeAreaId = tb.areas[0]?.id || null;
      tb.selectedId = null;
      tb.selectedDeviceId = null;
      ensureArea();
      save();
      render();
      status('Area deleted');
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
      save();
      render();
      status('Canvas cleared');
    });

    $('tb-export-json')?.addEventListener('click', async () => {
      const payload = {
        version: 1,
        exportedAt: new Date().toISOString(),
        areas: tb.areas,
      };
      const text = JSON.stringify(payload, null, 2);
      try {
        await navigator.clipboard.writeText(text);
        status('Graph JSON copied to clipboard (for Autogen / Python build).');
      } catch (_) {
        console.log('Transport Build graph', payload);
        status('Could not copy — graph logged to console.');
      }
    });

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
          'Next: click Apply to Autogen (or use Merge panel → From Transport Build),',
          'check Program pack · Merge, then Generate.',
        ].filter((l) => l !== undefined).join('\n');
        await showInfo(
          'Transport Build POC OK',
          'Wrote report + merges fragment under exports/transport-poc.\nDoes NOT change Autogen until you Apply.',
          detail
        );
        status(`POC OK — files in exports/transport-poc — click Apply to Autogen`);
        if (exportsDir && api.openPath) {
          try { await api.openPath(exportsDir); } catch (_) { /* ignore */ }
        }
        // Offer apply immediately so Autogen actually gets the rows
        if ((res.merges_2to1_count || 0) > 0) {
          const doApply = await askYesNo(
            'Apply to Autogen workbook?',
            `Push ${res.merges_2to1_count} merge row(s) into PLC Autogen now?\n\n(This is why Generate didn’t show transport code before.)`
          );
          if (doApply) {
            await applyMergesToAutogenUi({ path: res.autogen_merges_path });
          }
        }
      } catch (err) {
        await showInfo('Build POC error', String(err?.message || err));
        status(`POC error: ${err?.message || err}`);
      }
    });

    $('tb-apply-autogen')?.addEventListener('click', async () => {
      await applyMergesToAutogenUi({ path: tb.lastPoc?.autogen_merges_path });
    });

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

  async function applyMergesToAutogenUi(opts = {}) {
    status('Applying Transport merges → Autogen workbook…');
    try {
      let res;
      if (typeof window.applyTransportMergesToAutogen === 'function') {
        res = await window.applyTransportMergesToAutogen(opts);
      } else {
        const api = window.fortnaAPI || window.api;
        if (!api?.transportApplyAutogen) {
          await showInfo('Apply to Autogen', 'Desktop IPC missing — restart Site Forge.');
          return;
        }
        res = await api.transportApplyAutogen(opts);
      }
      if (!res?.ok) {
        await showInfo('Apply failed', res?.error || 'unknown');
        status(`Apply failed: ${res?.error || 'unknown'}`);
        return;
      }
      const warn = (res.area_warnings || []).join('\n');
      await showInfo(
        'Applied to Autogen',
        `Applied ${res.applied_count} merge row(s) (${res.total_count} total in workbook).\n\n`
          + `1) Open PLC Autogen → Merge panel (should list them)\n`
          + `2) Program pack → Merge must be checked\n`
          + `3) Generate again\n\n`
          + `Workbook: ${res.workbook_path || 'workspace/active/autogen_workbook.json'}\n`
          + `Fragment: ${res.path || ''}`,
        warn || undefined
      );
      status(`Applied ${res.applied_count} merge(s) → Autogen — Generate with Merge pack ON`);
    } catch (err) {
      await showInfo('Apply error', String(err?.message || err));
      status(`Apply error: ${err?.message || err}`);
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
    canvas.addEventListener('mousedown', () => { try { canvas.focus(); } catch (_) { /* ignore */ } });

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
      const hr = nodesHost.getBoundingClientRect();
      const x = ev.clientX - hr.left + nodesHost.parentElement.scrollLeft;
      const y = ev.clientY - hr.top + nodesHost.parentElement.scrollTop;
      const area = activeArea();
      let onto = null;
      if (!isConv(kind) && area) {
        onto = nodeAtPoint(x, y, area);
      }
      addNode(kind, x - 70, y - 24, onto);
      tb.dragKind = null;
    });

    window.addEventListener('mousemove', (ev) => {
      if (tb.moving) {
        const area = activeArea();
        const n = area?.nodes.find((x) => x.id === tb.moving.id);
        if (n) {
          n.x = Math.max(0, ev.clientX - tb.moving.ox);
          n.y = Math.max(0, ev.clientY - tb.moving.oy);
          const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
          if (el) {
            el.style.left = `${n.x}px`;
            el.style.top = `${n.y}px`;
          }
          drawWires();
        }
      }
      if (tb.linkFrom) {
        const a = portCenter(tb.linkFrom.nodeId, 'out');
        if (a) {
          const host = $('tb-nodes').getBoundingClientRect();
          drawWires({
            from: a,
            to: { x: ev.clientX - host.left, y: ev.clientY - host.top },
          });
        }
      }
    });

    window.addEventListener('mouseup', (ev) => {
      if (tb.moving) {
        tb.moving = null;
        save();
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

    $('tb-insp-conveyor')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n) return;
      n.conveyorTag = e.target.value;
      if (n.conveyorTag && (!n.label || KIND_META[n.kind]?.title === n.label || /^Merge /i.test(n.label || ''))) {
        if (!KIND_META[n.kind]?.isMerge) n.label = n.conveyorTag;
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

    $('tb-insp-merge-lanes')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      if (!n || !KIND_META[n.kind]?.isMerge) return;
      const lanes = Math.min(4, Math.max(2, parseInt(e.target.value, 10) || 2));
      n.inPorts = lanes;
      n.label = `Merge ${lanes}:1`;
      // Drop wires to removed entrances
      const valid = new Set([...Array(lanes)].map((_, i) => `in${i}`));
      a.wires = a.wires.filter((w) => {
        if (w.to !== n.id) return true;
        return valid.has(w.toPort || 'in0') || valid.has(w.toPort);
      });
      save();
      render();
    });

    // Keyboard: Delete / Backspace remove selection; arrows nudge conveyors
    window.addEventListener('keydown', (ev) => {
      const tab = $('tab-transport');
      if (!tab || tab.classList.contains('hidden')) return;
      const tag = (ev.target && ev.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

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
        tb.selectedId = null;
        tb.selectedDeviceId = null;
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
      const tag = ($('tb-insp-device-tag-new')?.value || '').trim();
      if (!tag) {
        status('Pick a tag from the RUN list for this device type.');
        return;
      }
      if (!n.devices) n.devices = [];
      const newDev = { id: uid('dev'), kind, name: tag, tag };
      n.devices.push(newDev);
      $('tb-insp-add-row')?.classList.add('hidden');
      tb.selectedDeviceId = null;
      save();
      render();
      status(`Added ${kind} ${tag}`);
    });

    $('tb-insp-dev-tag')?.addEventListener('change', (e) => {
      const a = activeArea();
      const n = a?.nodes.find((x) => x.id === tb.selectedId);
      const d = n?.devices?.find((x) => x.id === tb.selectedDeviceId);
      if (!d) return;
      d.tag = e.target.value;
      d.name = d.tag || d.name;
      save();
      render();
      status(`Set ${d.kind} tag → ${d.tag || '(none)'}`);
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

  function init() {
    if (!$('tab-transport')) return;
    load();
    ensureArea();
    bindUi();
    render();
    status('Transport Build POC ready — create an area and drag a conveyor.');
  }

  // Expose refresh when tab opens (conveyor dropdown)
  window.transportBuildRefresh = function () {
    render();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
