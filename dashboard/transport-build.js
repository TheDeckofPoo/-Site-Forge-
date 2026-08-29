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
    motor: { icon: 'fa-gear', color: 'text-amber-300', isConv: false, title: 'Motor', svg: 'motor' },
    estop: { icon: 'fa-hand', color: 'text-red-300', isConv: false, title: 'E-Stop', svg: 'estop' },
    pws: { icon: 'fa-bolt', color: 'text-yellow-300', isConv: false, title: 'Power Supply' },
    encoder: { icon: 'fa-compact-disc', color: 'text-violet-300', isConv: false, title: 'Encoder', svg: 'encoder' },
    photoeye: { icon: 'fa-eye', color: 'text-emerald-300', isConv: false, title: 'Photoeye', svg: 'photoeye' },
  };

  /** Fortna PE suffix → Autogen roles (multi-select; Exit+Jam is normal for _P). */
  const PE_ROLE_ORDER = ['exit', 'add', 'jam', 'full'];
  const PE_ROLE_BADGE = {
    exit: { letter: 'P', cls: 'tb-pe-role-exit', title: 'Exit / product (_P) → Fast_Conv ExitPE' },
    add: { letter: 'A', cls: 'tb-pe-role-add', title: 'Add / entrance → Fast_Conv AddPE' },
    jam: { letter: 'J', cls: 'tb-pe-role-jam', title: 'Jam (_J) → Slow_Jam' },
    full: { letter: 'F', cls: 'tb-pe-role-full', title: 'Full (_F) → Full_PE' },
  };

  function inferPeRoles(tag) {
    const u = String(tag || '').trim().toUpperCase();
    if (!u) return ['exit'];
    if (/_F\d*$|_FULL|FULL/.test(u) && !/_JF|_FDJ/.test(u)) return ['full'];
    if (/_J\d*$|_JAM|JAM|_JF|_FDJ/.test(u)) return ['jam'];
    if (/_P\d*$|PRODUCT|PRESENT|DISCHARGE/.test(u) || /_P$/.test(u)) return ['exit', 'jam'];
    return ['exit'];
  }

  function normalizePeRoles(roles) {
    const set = new Set((roles || []).map((r) => String(r || '').toLowerCase()).filter(Boolean));
    return PE_ROLE_ORDER.filter((r) => set.has(r));
  }

  function ensurePeRoles(dev, { forceInfer = false } = {}) {
    if (!dev || dev.kind !== 'photoeye') return [];
    // Keep engineer overrides unless tag change forces a fresh infer
    if (!forceInfer && (dev.rolesManual || (Array.isArray(dev.roles) && dev.roles.length))) {
      dev.roles = normalizePeRoles(dev.roles);
      return dev.roles;
    }
    dev.roles = inferPeRoles(dev.tag || dev.name || '');
    return dev.roles;
  }

  function peRoleBadgesHtml(roles) {
    const list = normalizePeRoles(roles);
    if (!list.length) return '';
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
    // Hit-test conveyors for device drop — padded so 90° curves are easier targets
    const pad = 28;
    for (let i = area.nodes.length - 1; i >= 0; i--) {
      const n = area.nodes[i];
      if (!isConv(n.kind)) continue;
      const el = document.querySelector(`.tb-node[data-id="${n.id}"]`);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      const host = $('tb-nodes').getBoundingClientRect();
      const left = r.left - host.left - pad;
      const top = r.top - host.top - pad;
      const w = r.width + pad * 2;
      const h = r.height + pad * 2;
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
      el.style.transform = ''; // card stays upright — labels always readable
      const rot = Number(n.rotation || 0) % 360;
      const sides = portSides(rot);

      const devices = n.devices || [];
      const chips = devices
        .map((d) => {
          const label = d.tag || d.name || d.kind;
          const sel = d.id === tb.selectedDeviceId ? ' ring-1 ring-fuchsia-500' : '';
          const roles = d.kind === 'photoeye' ? ensurePeRoles(d) : [];
          const badges = d.kind === 'photoeye' ? peRoleBadgesHtml(roles) : '';
          const tip = d.kind === 'photoeye'
            ? `PE roles: ${(roles.length ? roles.join('+') : 'none')} — click to edit`
            : 'Click to assign tag';
          return `<span class="tb-device-chip${sel} cursor-pointer" data-dev-id="${escapeHtml(d.id)}" title="${escapeHtml(tip)}">${kindIconHtml(d.kind)}${escapeHtml(label)}${badges}</span>`;
        })
        .join('');

      const hasWire = (() => {
        const a = activeArea();
        if (!a) return false;
        return (a.wires || []).some((w) => w.from === n.id || w.to === n.id);
      })();
      const bind = n.conveyorTag
        ? `<div class="mono text-cyan-400/90 truncate" title="${escapeHtml(n.conveyorTag)}">${escapeHtml(n.conveyorTag)}</div>`
        : hasWire
          ? `<div class="text-amber-400/90 text-[9px]">Wired — still bind P### tag</div>`
          : `<div class="text-slate-600 italic text-[9px]">Bind P### in inspector</div>`;
      const mergeNote = meta.isMerge
        ? `<div class="text-orange-400/80 text-[9px] mt-0.5">${n.inPorts || 2}:1 merge</div>`
        : '';
      const orientNote = rot
        ? `<div class="tb-orient mt-0.5">flow ${rot}°</div>`
        : '';

      let portsHtml = '';
      if (isConv(n.kind)) {
        const inCount = meta.isMerge ? Math.max(2, Number(n.inPorts) || 2) : 1;
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

      el.innerHTML = `
        <div class="tb-content">
          <div class="tb-head">
            ${kindIconHtml(n.kind, meta.color)}
            <span class="truncate" title="${escapeHtml(n.label || meta.title)}">${escapeHtml(n.label || meta.title)}</span>
          </div>
          <div class="tb-body">
            ${isConv(n.kind) ? bind : ''}
            ${mergeNote}
            ${orientNote}
            <div class="mt-1 flex flex-wrap">${chips || (isConv(n.kind) ? '<span class="text-slate-700 text-[9px]">Drop devices here</span>' : '')}</div>
          </div>
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
        }
      }
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
      const lanes = Math.max(2, Number(n.inPorts) || 2);
      if (laneSel && meta.isMerge) laneSel.value = String(lanes);
      if (meta.isMerge) {
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
            const badges = d.kind === 'photoeye' ? peRoleBadgesHtml(ensurePeRoles(d)) : '';
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

    function resetPeRoleCheckboxes() {
      PE_ROLE_ORDER.forEach((r) => {
        const el = $(`tb-insp-pe-role-${r}`);
        if (el) el.checked = false;
      });
    }

    $('tb-area-delete')?.addEventListener('click', async () => {
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
      status('Area deleted — PE roles reset');
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

  async function applyMergesToAutogenUi() {
    ensurePlaceholderConveyorTags();
    const graph = {
      version: 1,
      exportedAt: new Date().toISOString(),
      areas: tb.areas,
    };
    status('Applying Transport areas + conveyors + merges → Autogen…');
    try {
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
      const areas = (res.areas_applied || []).join(', ') || '(none)';
      const warn = [
        ...(res.area_warnings || []),
        'Note: wires connect flow only — each piece still needs a P### tag (placeholders like Merge5_C1 were auto-assigned if unbound).',
        'Replace placeholders with real RUN tags, then Apply again before Generate.',
      ].join('\n');
      await showInfo(
        'Applied to Autogen',
        `${res.summary || 'Done'}\n\n`
          + `Areas in workbook:\n${areas}\n\n`
          + `1) PLC Autogen site table — conveyors show those area names\n`
          + `2) Generate now (workbook reloads Apply data so Merge5 is not wiped)\n`
          + `3) If merges: keep Program pack · Merge ON\n\n`
          + `Workbook: ${res.workbook_path || 'workspace/autogen_workbook.json'}`,
        warn || undefined
      );
      status(`Applied ${res.summary || ''} → Autogen — Generate when ready`);
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
      const prev = (n.conveyorTag || '').trim();
      n.conveyorTag = e.target.value;
      if (n.conveyorTag && (!n.label || KIND_META[n.kind]?.title === n.label || /^Merge /i.test(n.label || ''))) {
        if (!KIND_META[n.kind]?.isMerge) n.label = n.conveyorTag;
      }
      save();
      render();
      if (!n.conveyorTag && prev) {
        status(`Cleared ${prev} — Apply to remove it from the Transport area L5X`);
        toast(`Cleared ${prev}. Click Apply so the next Generate drops it from MERGE/area routines.`, 'warn');
      }
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
        if (!n || !KIND_META[n.kind]?.isMerge) return;
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
      if (!n || !KIND_META[n.kind]?.isMerge) return;
      n.allow_undefined_pe = !!e.target.checked;
      save();
      status(n.allow_undefined_pe ? 'Will create missing PE tags in L5X' : 'Unknown PEs → NO_PE');
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
      $(`tb-insp-pe-role-${role}`)?.addEventListener('change', () => {
        const a = activeArea();
        const n = a?.nodes.find((x) => x.id === tb.selectedId);
        const d = n?.devices?.find((x) => x.id === tb.selectedDeviceId);
        if (!d || d.kind !== 'photoeye') return;
        const next = PE_ROLE_ORDER.filter((r) => !!$(`tb-insp-pe-role-${r}`)?.checked);
        if (!next.length) {
          // Cleared all roles → restore original tag-inferred defaults (not "stuck on previous")
          d.rolesManual = false;
          d.roles = inferPeRoles(d.tag || d.name || '');
          status(`PE roles cleared → defaults ${(d.roles || []).join('+') || 'exit'}`);
        } else {
          d.roles = next;
          d.rolesManual = true;
          status(`PE roles → ${d.roles.join('+')}`);
        }
        PE_ROLE_ORDER.forEach((r) => {
          const el = $(`tb-insp-pe-role-${r}`);
          if (el) el.checked = (d.roles || []).includes(r);
        });
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
    bindUi();
    paintPaletteIcons();
    render();
    status('Transport Build ready — Wizard assists areas, tags, and merge PEs.');
  }

  // Expose refresh when tab opens (conveyor dropdown)
  window.transportBuildRefresh = function () {
    render();
  };

  /** Wipe all Transport Build areas (Transport1, Merge5, …) and reset PE role UI. */
  window.transportBuildClearAll = function () {
    tb.areas = [];
    tb.activeAreaId = null;
    tb.selectedId = null;
    tb.selectedDeviceId = null;
    try { localStorage.removeItem(STORE_KEY); } catch (_) { /* ignore */ }
    ensureArea();
    resetPeRoleUi();
    save();
    render();
    // Force inspector empty state (PE roles must not linger after Clear project builds)
    $('tb-inspector-empty')?.classList.remove('hidden');
    $('tb-inspector')?.classList.add('hidden');
    status('All transport areas cleared — PE roles reset');
    return true;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
