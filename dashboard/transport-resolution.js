/**
 * Transportation engineer-resolution workspace (site-free).
 * Extends TransportBuild: topology table, right-click area assign,
 * peripherals, completeness / review queue, provenance badges.
 *
 * Effective model = discovered evidence + engineer overrides.
 * Never invent ownership from device existence alone.
 */
(function () {
  'use strict';

  function A() {
    return window.TransportBuild || {};
  }
  function $(id) {
    return document.getElementById(id);
  }
  function esc(s) {
    const { escapeHtml } = A();
    return typeof escapeHtml === 'function' ? escapeHtml(s) : String(s ?? '');
  }

  const PROV = {
    PROVEN: 'PROVEN',
    DERIVED: 'DERIVED',
    ENGINEER_ASSIGNED: 'ENGINEER_ASSIGNED',
    FALLBACK_MAIN_AREA: 'FALLBACK_MAIN_AREA',
    FALLBACK: 'FALLBACK',
    REVIEW_REQUIRED: 'REVIEW_REQUIRED',
    UNKNOWN: 'UNKNOWN',
    AREA_DEFAULT: 'AREA_DEFAULT',
  };

  function ensureResolutionState(tb) {
    if (!tb) return;
    if (!tb.engineerOverrides || typeof tb.engineerOverrides !== 'object') {
      tb.engineerOverrides = { conveyors: {}, areas: {} };
    }
    if (!tb.engineerOverrides.conveyors) tb.engineerOverrides.conveyors = {};
    if (!tb.engineerOverrides.areas) tb.engineerOverrides.areas = {};
    if (!tb.invFilterMode) tb.invFilterMode = 'unplaced';
  }

  function tagKey(tag) {
    return String(tag || '').trim().toUpperCase();
  }

  function nodeOverride(tb, n) {
    ensureResolutionState(tb);
    const t = tagKey(n?.conveyorTag);
    return (t && tb.engineerOverrides.conveyors[t]) || {};
  }

  function areaOverride(tb, areaName) {
    ensureResolutionState(tb);
    const k = String(areaName || '').trim();
    if (!k) return {};
    if (!tb.engineerOverrides.areas[k]) {
      tb.engineerOverrides.areas[k] = {
        controlStations: [],
        stacklights: [],
      };
    }
    return tb.engineerOverrides.areas[k];
  }

  function setNodeField(n, field, value, source) {
    const tb = A().tb;
    if (!n || !tb) return;
    ensureResolutionState(tb);
    const tag = tagKey(n.conveyorTag);
    if (!n.provenance || typeof n.provenance !== 'object') n.provenance = {};
    const discoveredKey = `discovered_${field}`;
    if (n[discoveredKey] == null && n[field] != null && n[field] !== '') {
      n[discoveredKey] = n[field];
    }
    n[field] = value;
    n.provenance[field] = source || PROV.ENGINEER_ASSIGNED;
    if (tag) {
      const ov = tb.engineerOverrides.conveyors[tag] || {};
      ov[field] = value;
      ov[`${field}_source`] = source || PROV.ENGINEER_ASSIGNED;
      ov.updatedAt = new Date().toISOString();
      tb.engineerOverrides.conveyors[tag] = ov;
    }
  }

  function fieldProvenance(n, field) {
    const p = n?.provenance?.[field];
    if (p) return String(p);
    const ov = nodeOverride(A().tb, n);
    if (ov[`${field}_source`]) return String(ov[`${field}_source`]);
    const v = n?.[field];
    if (v == null || v === '') return PROV.UNKNOWN;
    return PROV.DERIVED;
  }

  function badge(prov) {
    const p = String(prov || PROV.UNKNOWN).toUpperCase();
    let cls = 'tb-prov-unknown';
    if (p === PROV.PROVEN) cls = 'tb-prov-proven';
    else if (p === PROV.ENGINEER_ASSIGNED) cls = 'tb-prov-eng';
    else if (p.includes('FALLBACK')) cls = 'tb-prov-fallback';
    else if (p.includes('REVIEW') || p === PROV.UNKNOWN) cls = 'tb-prov-review';
    else if (p === PROV.DERIVED) cls = 'tb-prov-derived';
    return `<span class="tb-prov ${cls}" title="${esc(p)}">${esc(p.replace(/_/g, ' '))}</span>`;
  }

  function displayOrUnknown(v) {
    const s = String(v ?? '').trim();
    return s || 'UNKNOWN';
  }

  function peList(n, role) {
    const { peTagsByRole } = A();
    if (typeof peTagsByRole === 'function') return peTagsByRole(n, role) || [];
    return [];
  }

  function effectivePiArea(n, logicAreaName) {
    const pia = String(n.piArea || n.pi_area || '').trim();
    if (pia) {
      const conf = fieldProvenance(n, 'piArea');
      return { value: pia, confidence: conf || PROV.ENGINEER_ASSIGNED };
    }
    const logic = String(logicAreaName || '').trim();
    if (logic) {
      return { value: logic, confidence: PROV.FALLBACK_MAIN_AREA };
    }
    return { value: '', confidence: PROV.REVIEW_REQUIRED };
  }

  function controlStationForNode(n) {
    const ov = nodeOverride(A().tb, n);
    if (ov.controlStation) return { value: ov.controlStation, confidence: PROV.ENGINEER_ASSIGNED };
    const d = (n.devices || []).find((x) => /control.?station|cs_udt/i.test(String(x.kind || x.tag || '')));
    if (d?.tag) return { value: d.tag, confidence: PROV.DERIVED };
    return { value: '', confidence: PROV.UNKNOWN };
  }

  function peRolesSummary(n) {
    const parts = [];
    const e = peList(n, 'exit');
    const a = peList(n, 'add');
    const j = peList(n, 'jam');
    const f = peList(n, 'full');
    if (e.length) parts.push(`Exit:${e.join(',')}`);
    if (a.length) parts.push(`Add:${a.join(',')}`);
    if (j.length) parts.push(`Jam:${j.join(',')}`);
    if (f.length) parts.push(`Full:${f.join(',')}`);
    return parts.length ? parts.join(' · ') : 'UNKNOWN';
  }

  function equipmentKindLabel(n, KIND_META) {
    const ov = nodeOverride(A().tb, n);
    if (ov.equipmentKind) return { value: ov.equipmentKind, confidence: PROV.ENGINEER_ASSIGNED };
    const meta = (KIND_META && KIND_META[n.kind]) || {};
    const value = n.asMerge ? 'Merge' : (meta.title || n.kind || 'Straight');
    return { value, confidence: PROV.DERIVED };
  }

  /** Active-area topology rows — never suppress unresolved. */
  function renderResolutionTopologyTable() {
    const { tb, isConv, activeArea, KIND_META, getUpstreamTags } = A();
    const body = $('tb-topo-body');
    if (!body || !tb) return false;
    ensureResolutionState(tb);
    const focus = activeArea();
    const areas = focus ? [focus] : (tb.areas || []);
    const rows = [];
    areas.forEach((area) => {
      const logicName = area.name || '';
      (area.nodes || []).forEach((n) => {
        if (!isConv?.(n.kind)) return;
        const tag = (n.conveyorTag || '').trim();
        const up = (typeof getUpstreamTags === 'function' ? getUpstreamTags(area, n.id) : []).join(', ') || '—';
        const ds = String(n.downstream || '').trim();
        const equip = equipmentKindLabel(n, KIND_META);
        const peSum = peRolesSummary(n);
        const pi = effectivePiArea(n, logicName);
        const sz = String(n.safetyZone || '').trim();
        const szProv = fieldProvenance(n, 'safetyZone');
        const dsProv = fieldProvenance(n, 'downstream');
        const logicProv = fieldProvenance(n, 'logicArea') || (n.provenance?.area) || PROV.DERIVED;
        const st = [];
        if (!tag) st.push('unbound');
        if (!ds && !n.terminal) st.push('no-ds');
        if (pi.confidence.includes('FALLBACK') || pi.confidence.includes('REVIEW')) st.push('pi-review');
        if (!sz) st.push('sz-unknown');
        if (logicProv === PROV.ENGINEER_ASSIGNED || dsProv === PROV.ENGINEER_ASSIGNED) st.push('engineer');
        const sel = n.id === tb.selectedId ? ' tb-topo-sel' : '';
        const title = `Upstream (derived): ${up}`;
        rows.push(`<tr class="${sel}" data-topo-id="${esc(n.id)}" data-topo-area="${esc(area.id)}" data-topo-tag="${esc(tag)}" title="${esc(title)}">
          <td class="mono text-cyan-300">${esc(tag || n.label || n.id)}</td>
          <td>
            <button type="button" class="tb-topo-logic-btn text-[10px] mono px-1 py-0.5 rounded border border-slate-700 text-fuchsia-200" data-topo-logic="${esc(n.id)}">${esc(displayOrUnknown(logicName))}</button>
            ${badge(logicProv)}
          </td>
          <td>
            <button type="button" class="tb-topo-ds-btn text-[10px] mono px-1.5 py-0.5 rounded border border-slate-700 text-cyan-300" data-topo-ds-edit="${esc(n.id)}">${esc(displayOrUnknown(ds))}</button>
            ${badge(ds ? dsProv : PROV.REVIEW_REQUIRED)}
          </td>
          <td>
            <button type="button" class="tb-topo-equip-btn text-[10px] mono px-1 py-0.5 rounded border border-slate-700 text-sky-200" data-topo-equip="${esc(n.id)}">${esc(equip.value)}</button>
            ${badge(equip.confidence)}
          </td>
          <td>
            <button type="button" class="tb-topo-pe-btn text-[10px] mono px-1 py-0.5 rounded border border-slate-700 text-emerald-200 max-w-[12rem] truncate" data-topo-pe="${esc(n.id)}" title="${esc(peSum)}">${esc(peSum)}</button>
          </td>
          <td>
            <button type="button" class="tb-topo-sz-btn text-[10px] mono px-1.5 py-0.5 rounded border border-slate-700 text-amber-200" data-topo-sz-edit="${esc(n.id)}">${esc(displayOrUnknown(sz))}</button>
            ${badge(sz ? szProv : PROV.UNKNOWN)}
          </td>
          <td>
            <button type="button" class="tb-topo-pi-btn text-[10px] mono px-1 py-0.5 rounded border border-slate-700 text-violet-200" data-topo-pi="${esc(n.id)}">${esc(displayOrUnknown(pi.value))}</button>
            ${badge(pi.confidence)}
          </td>
          <td class="text-slate-500">${esc(st.join(', ') || 'ok')}</td>
        </tr>`);
      });
    });
    const curArea = focus;
    const addAreaOpts = (tb.areas || [])
      .map((a) => `<option value="${esc(a.id)}" ${curArea && a.id === curArea.id ? 'selected' : ''}>${esc(a.name)}</option>`)
      .join('');
    rows.push(`<tr id="tb-topo-add-row" class="tb-topo-add-row" data-topo-add="1">
      <td><input id="tb-topo-add-tag" type="text" placeholder="Add conveyor…" class="w-full bg-slate-950 border border-fuchsia-900/50 rounded px-1.5 py-1 text-[10px] mono text-cyan-200" /></td>
      <td><select id="tb-topo-add-area" class="bg-slate-950 border border-slate-700 rounded px-1 text-[10px] text-slate-200 max-w-[8.5rem]">${addAreaOpts || '<option value="">—</option>'}</select></td>
      <td class="text-slate-600" colspan="5">Downstream / Equipment / PE / Safety / PI editable after add</td>
      <td><button type="button" id="tb-topo-add-btn" class="btn-ghost text-[10px] px-2 py-0.5 rounded border border-fuchsia-700/60 text-fuchsia-200">+</button></td>
    </tr>`);
    body.innerHTML = rows.join('') || `<tr><td colspan="8" class="text-slate-600 px-2 py-3">No conveyors in this Area — right-click Unplaced to Assign.</td></tr>`;

    wireTopoEditors(body);
    return true;
  }

  function wireTopoEditors(body) {
    const { tb, save, render, status, listSafetyZoneNames, findNodeByTag, isConv, activeArea } = A();
    if (!body || !tb) return;

    body.querySelectorAll('[data-topo-ds-edit]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-ds-edit');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n || !area) return;
        const ds = String(n.downstream || '').trim();
        const sel = document.createElement('select');
        sel.className = 'bg-slate-950 border border-cyan-700 rounded px-1 text-[10px] mono text-cyan-200';
        sel.innerHTML = [`<option value="">UNKNOWN</option>`]
          .concat(
            (area.nodes || [])
              .filter((x) => isConv(x.kind) && x.id !== n.id && (x.conveyorTag || '').trim())
              .map((x) => {
                const t = x.conveyorTag.trim();
                return `<option value="${esc(t)}" ${t === ds ? 'selected' : ''}>${esc(t)}</option>`;
              }),
          )
          .join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          setNodeField(n, 'downstream', sel.value || '', PROV.ENGINEER_ASSIGNED);
          save?.();
          render?.();
          status?.(`Downstream ${n.conveyorTag || n.id} → ${sel.value || 'UNKNOWN'} [ENGINEER]`);
        });
      });
    });

    body.querySelectorAll('[data-topo-sz-edit]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-sz-edit');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n) return;
        const cur = String(n.safetyZone || '').trim();
        const names = (typeof listSafetyZoneNames === 'function' ? listSafetyZoneNames() : []).slice();
        if (cur && !names.includes(cur)) names.push(cur);
        const sel = document.createElement('select');
        sel.className = 'mono text-amber-200 max-w-[9rem] bg-slate-950 border border-amber-800 rounded px-1 text-[10px]';
        sel.innerHTML = [`<option value="">UNKNOWN</option>`]
          .concat(names.map((z) => `<option value="${esc(z)}" ${z === cur ? 'selected' : ''}>${esc(z)}</option>`))
          .join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          setNodeField(n, 'safetyZone', sel.value || '', PROV.ENGINEER_ASSIGNED);
          save?.();
          render?.();
        });
      });
    });

    body.querySelectorAll('[data-topo-pi]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-pi');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n) return;
        const sel = document.createElement('select');
        sel.className = 'bg-slate-950 border border-violet-700 rounded px-1 text-[10px] mono text-violet-200';
        const cur = String(n.piArea || '').trim();
        sel.innerHTML = [`<option value="">FALLBACK → logic area</option>`]
          .concat((tb.areas || []).map((a) => {
            const nm = a.name || '';
            return `<option value="${esc(nm)}" ${nm === cur ? 'selected' : ''}>${esc(nm)}</option>`;
          }))
          .join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          setNodeField(n, 'piArea', sel.value || '', sel.value ? PROV.ENGINEER_ASSIGNED : PROV.FALLBACK_MAIN_AREA);
          if (!sel.value) {
            // clear explicit pi → fallback
            n.piArea = '';
          }
          save?.();
          render?.();
        });
      });
    });

    body.querySelectorAll('[data-topo-logic]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-logic');
        showAssignMenu(ev.clientX, ev.clientY, [nid], { mode: 'move' });
      });
    });

    body.querySelectorAll('[data-topo-equip]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-equip');
        const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
        const n = area?.nodes?.find((x) => x.id === nid);
        if (!n) return;
        const kinds = ['Straight', 'Merge', 'Curve', 'Spiral', 'Belt', 'Other'];
        const cur = equipmentKindLabel(n, A().KIND_META).value;
        const sel = document.createElement('select');
        sel.className = 'bg-slate-950 border border-sky-700 rounded px-1 text-[10px] mono text-sky-200';
        sel.innerHTML = kinds.map((k) => `<option value="${esc(k)}" ${k === cur ? 'selected' : ''}>${esc(k)}</option>`).join('');
        btn.replaceWith(sel);
        sel.focus();
        sel.addEventListener('change', () => {
          const tag = tagKey(n.conveyorTag);
          ensureResolutionState(tb);
          if (tag) {
            const ov = tb.engineerOverrides.conveyors[tag] || {};
            ov.equipmentKind = sel.value;
            ov.equipmentKind_source = PROV.ENGINEER_ASSIGNED;
            tb.engineerOverrides.conveyors[tag] = ov;
          }
          save?.();
          render?.();
        });
      });
    });

    body.querySelectorAll('[data-topo-pe]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const nid = btn.getAttribute('data-topo-pe');
        openPeRolesEditor(nid, btn);
      });
    });

    body.querySelectorAll('tr[data-topo-id]').forEach((tr) => {
      tr.addEventListener('click', () => {
        const nid = tr.getAttribute('data-topo-id');
        if (nid && typeof A().selectNode === 'function') A().selectNode(nid);
      });
    });
  }

  function openPeRolesEditor(nid, anchorBtn) {
    const { tb, save, render, status } = A();
    const area = (tb.areas || []).find((a) => (a.nodes || []).some((x) => x.id === nid));
    const n = area?.nodes?.find((x) => x.id === nid);
    if (!n) return;
    const devices = (n.devices || []).filter((d) => d && (d.kind === 'photoeye' || /PE/i.test(d.tag || d.name || '')));
    if (!devices.length) {
      status?.('No PE devices on this conveyor — attach PEs in inspector first');
      return;
    }
    const host = document.createElement('div');
    host.className = 'fixed z-[240] rounded-lg border border-emerald-800 bg-[#0a1210] shadow-xl p-2 text-[10px] text-slate-200 min-w-[14rem]';
    host.style.left = `${Math.min((anchorBtn.getBoundingClientRect?.().left || 40), window.innerWidth - 240)}px`;
    host.style.top = `${Math.min((anchorBtn.getBoundingClientRect?.().bottom || 40) + 4, window.innerHeight - 200)}px`;
    const roles = ['exit', 'add', 'jam', 'full', 'none'];
    host.innerHTML = `<div class="text-[9px] uppercase text-emerald-400/80 mb-1">PE Roles · ${esc(n.conveyorTag || '')}</div>`
      + devices.map((d) => {
        const tag = d.tag || d.name || '';
        const cur = Array.isArray(d.roles) && d.roles.length ? d.roles[0] : (d.role || 'none');
        return `<div class="flex items-center gap-1 mb-1">
          <span class="mono text-cyan-300 flex-1 truncate">${esc(tag)}</span>
          <select data-pe-tag="${esc(tag)}" class="bg-slate-950 border border-slate-700 rounded text-[10px]">
            ${roles.map((r) => `<option value="${r}" ${String(cur).toLowerCase() === r ? 'selected' : ''}>${r}</option>`).join('')}
          </select>
        </div>`;
      }).join('')
      + `<button type="button" class="mt-1 w-full text-center text-emerald-300 border border-emerald-800 rounded py-0.5" data-pe-done="1">Done</button>`;
    document.body.appendChild(host);
    const close = () => host.remove();
    host.querySelector('[data-pe-done]')?.addEventListener('click', () => {
      host.querySelectorAll('select[data-pe-tag]').forEach((sel) => {
        const tag = sel.getAttribute('data-pe-tag');
        const role = sel.value;
        const d = (n.devices || []).find((x) => (x.tag || x.name) === tag);
        if (!d) return;
        if (!d.discovered_roles && d.roles) d.discovered_roles = [...(d.roles || [])];
        d.roles = role === 'none' ? [] : [role];
        d.rolesManual = true;
        d.peRoleProvenance = PROV.ENGINEER_ASSIGNED;
      });
      save?.();
      render?.();
      status?.(`PE roles updated [ENGINEER_ASSIGNED]`);
      close();
    });
    setTimeout(() => {
      const once = (ev) => {
        if (!host.contains(ev.target)) {
          close();
          document.removeEventListener('mousedown', once);
        }
      };
      document.addEventListener('mousedown', once);
    }, 0);
  }

  function listControlStationCandidates() {
    const { buildableTagCatalog, tb } = A();
    const out = new Set();
    try {
      const cat = typeof buildableTagCatalog === 'function' ? buildableTagCatalog() : {};
      // CS-like names from IO / devices
      Object.values(cat || {}).forEach((set) => {
        if (!(set instanceof Set) && !Array.isArray(set)) return;
        [...set].forEach((t) => {
          if (/_CS\d*$/i.test(t) || /^CP\d+_CS$/i.test(t) || /CS_UDT/i.test(t)) out.add(t);
        });
      });
    } catch (_) { /* ignore */ }
    (tb?.areas || []).forEach((a) => {
      (a.nodes || []).forEach((n) => {
        (n.devices || []).forEach((d) => {
          if (d?.tag && (/_CS/i.test(d.tag) || /station/i.test(d.kind || ''))) out.add(d.tag);
        });
      });
    });
    // Also scan engineer overrides area lists
    Object.values(tb?.engineerOverrides?.areas || {}).forEach((ar) => {
      (ar.controlStations || []).forEach((t) => out.add(t));
    });
    return [...out].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }

  function listStacklightCandidates() {
    const { buildableTagCatalog, tb } = A();
    const out = new Set();
    try {
      const cat = typeof buildableTagCatalog === 'function' ? buildableTagCatalog() : {};
      const beacons = cat.beacon || cat.stacklight || cat.horn || new Set();
      [...beacons].forEach((t) => out.add(t));
    } catch (_) { /* ignore */ }
    Object.values(tb?.engineerOverrides?.areas || {}).forEach((ar) => {
      (ar.stacklights || []).forEach((t) => out.add(t));
    });
    return [...out].sort();
  }

  function hideCtxMenu() {
    const m = $('tb-res-ctx-menu');
    if (m) {
      m.classList.add('hidden');
      m.style.display = 'none';
      m.innerHTML = '';
    }
  }

  function showAssignMenu(x, y, nodeIdsOrTags, opts) {
    const { tb, moveNodesToArea, save, render, status, activeArea, isConv, createConvNode, ensureBuildContext, pushHistory } = A();
    const menu = $('tb-res-ctx-menu');
    if (!menu || !tb) return;
    ensureResolutionState(tb);
    const mode = opts?.mode || 'assign';
    const areas = (tb.areas || []).filter((a) => a && a.name);
    let html = `<div class="px-2 py-1 text-[9px] uppercase tracking-wider text-slate-500">${mode === 'move' ? 'Move to Logic Area' : 'Assign to Logic Area'}</div>`;
    areas.forEach((a) => {
      html += `<button type="button" class="w-full text-left px-3 py-1.5 hover:bg-slate-800 text-slate-200" data-tb-assign-area="${esc(a.id)}">${esc(a.name)}</button>`;
    });
    html += `<div class="border-t border-slate-800 my-1"></div>`;
    html += `<button type="button" class="w-full text-left px-3 py-1.5 hover:bg-slate-800 text-fuchsia-300" data-tb-assign-new="1">Create New Area…</button>`;
    menu.innerHTML = html;
    menu.classList.remove('hidden');
    menu.style.display = 'block';
    menu.style.left = `${Math.min(x, window.innerWidth - 200)}px`;
    menu.style.top = `${Math.min(y, window.innerHeight - 40)}px`;

    const resolveNodeIds = () => {
      const ids = [];
      (nodeIdsOrTags || []).forEach((raw) => {
        const s = String(raw || '');
        // node id?
        let found = null;
        (tb.areas || []).forEach((a) => {
          const n = (a.nodes || []).find((x) => x.id === s);
          if (n) found = n.id;
        });
        if (found) {
          ids.push(found);
          return;
        }
        // conveyor tag — place if unplaced
        const tag = s.trim();
        if (!tag) return;
        let existing = null;
        (tb.areas || []).forEach((a) => {
          const n = (a.nodes || []).find(
            (x) => isConv?.(x.kind) && tagKey(x.conveyorTag) === tagKey(tag),
          );
          if (n) existing = n;
        });
        if (existing) {
          ids.push(existing.id);
          return;
        }
        // create in active/context area first then move
        try {
          pushHistory?.(`Place ${tag}`);
          ensureBuildContext?.();
          const area = activeArea?.();
          if (!area || typeof createConvNode !== 'function') return;
          const node = createConvNode({
            tag,
            x: 80 + (area.nodes?.length || 0) * 24,
            y: 120,
            area,
            safetyZone: '',
          });
          if (node?.id) {
            if (!node.provenance) node.provenance = {};
            node.provenance.logicArea = PROV.ENGINEER_ASSIGNED;
            node.discovered_logic_area = '';
            ids.push(node.id);
            const ov = tb.engineerOverrides.conveyors[tagKey(tag)] || {};
            ov.logicArea = area.name;
            ov.logicArea_source = PROV.ENGINEER_ASSIGNED;
            tb.engineerOverrides.conveyors[tagKey(tag)] = ov;
          }
        } catch (_) { /* ignore */ }
      });
      return ids;
    };

    menu.querySelectorAll('[data-tb-assign-area]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const destId = btn.getAttribute('data-tb-assign-area');
        const dest = (tb.areas || []).find((a) => a.id === destId);
        hideCtxMenu();
        if (!dest) return;
        const ids = resolveNodeIds();
        if (!ids.length) {
          status?.('No conveyors to assign');
          return;
        }
        // Do NOT auto-mutate safetyZone / piArea on Logic Area move
        const before = ids.map((id) => {
          let n = null;
          (tb.areas || []).forEach((a) => {
            const hit = (a.nodes || []).find((x) => x.id === id);
            if (hit) n = hit;
          });
          return n
            ? {
              id,
              pi: n.piArea || '',
              sz: n.safetyZone || '',
              tag: n.conveyorTag || '',
            }
            : null;
        }).filter(Boolean);

        const r = typeof moveNodesToArea === 'function'
          ? moveNodesToArea(ids, destId, { silent: true })
          : { moved: 0 };

        before.forEach((b) => {
          let n = null;
          (tb.areas || []).forEach((a) => {
            const hit = (a.nodes || []).find((x) => x.id === b.id);
            if (hit) n = hit;
          });
          if (!n) return;
          // Restore PI / Safety if move helper touched them
          n.piArea = b.pi;
          n.safetyZone = b.sz;
          setNodeField(n, 'logicArea', dest.name || '', PROV.ENGINEER_ASSIGNED);
          // Keep discovered area if first time
          if (n.discovered_logic_area == null) n.discovered_logic_area = '';
        });

        save?.();
        render?.();
        status?.(
          `Assigned ${r.moved || ids.length} conveyor(s) → Logic Area “${dest.name}” [ENGINEER_ASSIGNED]`,
        );
      });
    });

    menu.querySelector('[data-tb-assign-new]')?.addEventListener('click', async () => {
      hideCtxMenu();
      const name = window.prompt('New Logic Area name');
      if (!name || !String(name).trim()) return;
      const id = typeof A().uid === 'function' ? A().uid('area') : `area_${Date.now()}`;
      const a = {
        id,
        name: String(name).trim(),
        nodes: [],
        wires: [],
        provenance: 'ENGINEER',
      };
      tb.areas = tb.areas || [];
      tb.areas.push(a);
      // Re-open menu targeting new area by simulating assign
      const ids = resolveNodeIds();
      if (ids.length && typeof A().moveNodesToArea === 'function') {
        A().moveNodesToArea(ids, id, { silent: true });
        ids.forEach((nid) => {
          (tb.areas || []).forEach((ar) => {
            const n = (ar.nodes || []).find((x) => x.id === nid);
            if (n) setNodeField(n, 'logicArea', a.name, PROV.ENGINEER_ASSIGNED);
          });
        });
      }
      save?.();
      render?.();
      status?.(`Created Logic Area “${a.name}” and assigned selection`);
    });
  }

  function renderAreaResolutionPanels() {
    const { tb, activeArea, save, render, status } = A();
    if (!tb) return;
    ensureResolutionState(tb);
    const area = activeArea?.();
    const comp = $('tb-area-completeness');
    const review = $('tb-area-review-queue');
    const csPanel = $('tb-area-cs-panel');
    const stackPanel = $('tb-area-stack-panel');
    if (!area) {
      if (comp) comp.textContent = 'Select an Area.';
      if (review) review.textContent = '—';
      if (csPanel) csPanel.textContent = 'Select an Area.';
      if (stackPanel) stackPanel.textContent = 'Select an Area.';
      return;
    }
    const convs = (area.nodes || []).filter((n) => A().isConv?.(n.kind));
    let dsReview = 0;
    let dsOk = 0;
    let peReview = 0;
    let peOk = 0;
    let szOk = 0;
    let szReview = 0;
    let piOk = 0;
    let piReview = 0;
    const reviewItems = [];
    convs.forEach((n) => {
      const tag = (n.conveyorTag || n.label || n.id || '').trim();
      const ds = String(n.downstream || '').trim();
      if (ds || n.terminal) dsOk += 1;
      else {
        dsReview += 1;
        reviewItems.push({ tag, field: 'Downstream', id: n.id });
      }
      const pi = effectivePiArea(n, area.name);
      if (pi.confidence === PROV.FALLBACK_MAIN_AREA || pi.confidence.includes('REVIEW') || !pi.value) {
        piReview += 1;
        reviewItems.push({ tag, field: 'PI Area', id: n.id, detail: pi.confidence });
      } else piOk += 1;
      if (String(n.safetyZone || '').trim()) szOk += 1;
      else {
        szReview += 1;
        reviewItems.push({ tag, field: 'Safety Zone', id: n.id });
      }
      const exit = peList(n, 'exit');
      const jam = peList(n, 'jam');
      if (exit.length || jam.length) peOk += 1;
      else {
        peReview += 1;
        reviewItems.push({ tag, field: 'PE Roles', id: n.id });
      }
    });
    const ao = areaOverride(tb, area.name);
    const csAssigned = ao.controlStations || [];
    const csAvail = listControlStationCandidates().filter((t) => !csAssigned.includes(t));
    const stAssigned = ao.stacklights || [];
    const stAvail = listStacklightCandidates().filter((t) => !stAssigned.includes(t));
    if (!csAssigned.length && csAvail.length) {
      reviewItems.push({ tag: area.name, field: 'Control Station', id: '', detail: `${csAvail.length} available` });
    }
    if (!stAssigned.length) {
      reviewItems.push({ tag: area.name, field: 'Stacklight', id: '', detail: 'REVIEW_REQUIRED' });
    }

    const line = (label, ready, reviewN, blocked) => {
      let state = 'READY';
      let cls = 'text-emerald-400';
      if (blocked) {
        state = 'BLOCKED';
        cls = 'text-red-400';
      } else if (reviewN > 0) {
        state = 'REVIEW';
        cls = 'text-amber-300';
      }
      return `<div><span class="text-slate-400">${esc(label)}</span> · <span class="${cls}">${state}</span> · ${esc(ready)}</div>`;
    };

    if (comp) {
      comp.innerHTML = [
        `<div class="text-fuchsia-300 font-semibold">${esc(area.name)}</div>`,
        line('Conveyors', `${convs.length} assigned`, 0, false),
        line('Downstream', `${dsOk} proven/set, ${dsReview} review`, dsReview, false),
        line('PE Roles', `${peOk} with PE evidence, ${peReview} review`, peReview, false),
        line('Safety Zone', `${szOk} set, ${szReview} unknown`, szReview, false),
        line('PI Area', `${piOk} resolved, ${piReview} fallback/review`, piReview, false),
        line('Control Stations', `${csAssigned.length} assigned, ${csAvail.length} available`, csAssigned.length ? 0 : (csAvail.length ? 1 : 0), false),
        line('Stacklight', stAssigned.length ? `${stAssigned.length} assigned` : 'REVIEW_REQUIRED', stAssigned.length ? 0 : 1, false),
      ].join('');
    }
    if (review) {
      review.innerHTML = reviewItems.slice(0, 40).map((it) =>
        `<button type="button" class="block w-full text-left hover:text-amber-200" data-tb-review-id="${esc(it.id)}" data-tb-review-tag="${esc(it.tag)}"><span class="text-cyan-300 mono">${esc(it.tag)}</span> · ${esc(it.field)}${it.detail ? ` <span class="text-slate-600">${esc(it.detail)}</span>` : ''}</button>`,
      ).join('') || `<div class="text-emerald-400">No review items</div>`;
      review.querySelectorAll('[data-tb-review-id]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-tb-review-id');
          if (id && typeof A().selectNode === 'function') A().selectNode(id);
        });
      });
    }

    const renderAssignList = (host, assigned, available, kind) => {
      if (!host) return;
      const rows = [];
      rows.push(`<div class="text-slate-400">Assigned (${assigned.length})</div>`);
      assigned.forEach((t) => {
        rows.push(`<div class="flex items-center gap-1"><span class="text-emerald-300 mono flex-1">${esc(t)}</span>
          <button type="button" class="text-[9px] text-amber-300" data-tb-periph-remove="${esc(t)}" data-kind="${esc(kind)}">Remove</button></div>`);
      });
      rows.push(`<div class="text-slate-400 mt-1">Available / unassigned (${available.length})</div>`);
      available.slice(0, 30).forEach((t) => {
        rows.push(`<div class="flex items-center gap-1"><span class="text-slate-300 mono flex-1">${esc(t)}</span>
          <button type="button" class="text-[9px] text-cyan-300" data-tb-periph-add="${esc(t)}" data-kind="${esc(kind)}">Assign</button></div>`);
      });
      if (!assigned.length && !available.length) {
        rows.push(`<div class="text-slate-600">FOUND none in RUN/catalog — ownership stays REVIEW</div>`);
      }
      host.innerHTML = rows.join('');
      host.querySelectorAll('[data-tb-periph-add]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const t = btn.getAttribute('data-tb-periph-add');
          const k = btn.getAttribute('data-kind');
          const ao2 = areaOverride(tb, area.name);
          if (k === 'cs') {
            ao2.controlStations = [...new Set([...(ao2.controlStations || []), t])];
          } else {
            ao2.stacklights = [...new Set([...(ao2.stacklights || []), t])];
          }
          save?.();
          render?.();
          status?.(`Assigned ${t} → ${area.name} [ENGINEER_ASSIGNED] (existence ≠ prior ownership)`);
        });
      });
      host.querySelectorAll('[data-tb-periph-remove]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const t = btn.getAttribute('data-tb-periph-remove');
          const k = btn.getAttribute('data-kind');
          const ao2 = areaOverride(tb, area.name);
          if (k === 'cs') ao2.controlStations = (ao2.controlStations || []).filter((x) => x !== t);
          else ao2.stacklights = (ao2.stacklights || []).filter((x) => x !== t);
          save?.();
          render?.();
        });
      });
    };
    renderAssignList(csPanel, csAssigned, csAvail, 'cs');
    renderAssignList(stackPanel, stAssigned, stAvail, 'stack');
  }

  function enhanceInventoryPalette() {
    const { tb, runInventory, escapeHtml, selectNode, isConv, activeArea } = A();
    if (!tb) return;
    ensureResolutionState(tb);
    // Mode buttons
    document.querySelectorAll('[data-tb-inv-mode]').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tb-inv-mode') === (tb.invFilterMode || 'unplaced'));
      btn.onclick = () => {
        tb.invFilterMode = btn.getAttribute('data-tb-inv-mode') || 'unplaced';
        document.querySelectorAll('[data-tb-inv-mode]').forEach((b) => {
          b.classList.toggle('active', b.getAttribute('data-tb-inv-mode') === tb.invFilterMode);
        });
        // Re-render via hook
        if (typeof window.__tbHooks?.renderInventoryPanel === 'function') {
          window.__tbHooks.renderInventoryPanel();
        }
      };
    });
  }

  function unplacedReason(tag, inv) {
    const tb = A().tb;
    const t = tagKey(tag);
    const ov = tb?.engineerOverrides?.conveyors?.[t];
    if (ov?.logicArea) return 'Engineer-assigned area pending place';
    if (!inv?.usedConv?.has(t)) return 'Area unknown';
    return 'Unplaced';
  }

  // Hook: wrap pass2 inventory to add reasons + contextmenu
  function installInventoryContextMenu() {
    const list = $('tb-inv-list');
    if (!list || list._tbResWired) return;
    list._tbResWired = true;
    list.addEventListener('contextmenu', (ev) => {
      const el = ev.target.closest?.('[data-tb-inv-tag]');
      if (!el) return;
      ev.preventDefault();
      const tag = el.getAttribute('data-tb-inv-tag');
      const selected = [];
      list.querySelectorAll('.tb-inv-item.selected[data-tb-inv-tag], .tb-inv-item.unplaced[data-tb-inv-tag].tb-inv-multi').forEach((x) => {
        selected.push(x.getAttribute('data-tb-inv-tag'));
      });
      const tags = selected.length ? selected : [tag];
      // multi-select with Ctrl click
      showAssignMenu(ev.clientX, ev.clientY, tags, { mode: 'assign' });
    });
    list.addEventListener('click', (ev) => {
      const el = ev.target.closest?.('[data-tb-inv-tag]');
      if (!el) return;
      if (ev.ctrlKey || ev.metaKey) {
        el.classList.toggle('tb-inv-multi');
        ev.preventDefault();
      }
    });
  }

  function patchSaveLoad() {
    const api = A();
    const tb = api.tb;
    if (!tb || tb._resolutionSavePatched) return;
    tb._resolutionSavePatched = true;
    const origSave = api.save;
    if (typeof origSave === 'function') {
      // Monkey-patch by wrapping exported save if possible — also patch STORE payload via hook
    }
  }

  function applyOverridesOnLoad(tb) {
    ensureResolutionState(tb);
    const ov = tb.engineerOverrides?.conveyors || {};
    Object.keys(ov).forEach((tagU) => {
      const o = ov[tagU];
      (tb.areas || []).forEach((a) => {
        (a.nodes || []).forEach((n) => {
          if (tagKey(n.conveyorTag) !== tagU) return;
          if (o.downstream != null && o.downstream_source === PROV.ENGINEER_ASSIGNED) {
            n.downstream = o.downstream;
            if (!n.provenance) n.provenance = {};
            n.provenance.downstream = PROV.ENGINEER_ASSIGNED;
          }
          if (o.safetyZone != null && o.safetyZone_source === PROV.ENGINEER_ASSIGNED) {
            n.safetyZone = o.safetyZone;
            if (!n.provenance) n.provenance = {};
            n.provenance.safetyZone = PROV.ENGINEER_ASSIGNED;
          }
          if (o.piArea != null && o.piArea_source === PROV.ENGINEER_ASSIGNED) {
            n.piArea = o.piArea;
            if (!n.provenance) n.provenance = {};
            n.provenance.piArea = PROV.ENGINEER_ASSIGNED;
          }
          if (o.logicArea && o.logicArea_source === PROV.ENGINEER_ASSIGNED) {
            if (!n.provenance) n.provenance = {};
            n.provenance.logicArea = PROV.ENGINEER_ASSIGNED;
            // If node is not in that area, leave conflict flag
            if (String(a.name || '') !== String(o.logicArea || '') && String(o.logicArea || '').trim()) {
              n.provenance.logicAreaConflict = 'SOURCE_CHANGED_OR_MISMATCH — REVIEW';
            }
          }
        });
      });
    });
  }

  function boot() {
    const api = A();
    if (!api || !api.tb) {
      setTimeout(boot, 50);
      return;
    }
    ensureResolutionState(api.tb);
    applyOverridesOnLoad(api.tb);

    // Override topology table renderer
    const prevTopo = api.renderTopologyTable;
    api.renderTopologyTable = function resolutionTopo() {
      try {
        if (renderResolutionTopologyTable()) return;
      } catch (err) {
        console.warn('[TransportResolution] topo', err);
      }
      if (typeof prevTopo === 'function') prevTopo();
    };

    // Patch save to persist engineerOverrides
    const STORE_KEY = 'siteforge.transportBuild.v1';
    const origSave = api.save;
    api.save = function patchedSave() {
      try {
        ensureResolutionState(api.tb);
        const raw = localStorage.getItem(STORE_KEY);
        let data = raw ? JSON.parse(raw) : {};
        // Call original first
        if (typeof origSave === 'function') origSave();
        // Merge overrides into stored blob
        const raw2 = localStorage.getItem(STORE_KEY);
        data = raw2 ? JSON.parse(raw2) : {};
        data.engineerOverrides = api.tb.engineerOverrides;
        localStorage.setItem(STORE_KEY, JSON.stringify(data));
      } catch (_) {
        if (typeof origSave === 'function') origSave();
      }
    };

    // Load overrides when load() finishes — hook via periodic apply + initial
    const origLoad = api.load;
    if (typeof origLoad === 'function') {
      api.load = function patchedLoad() {
        const r = origLoad();
        try {
          const raw = localStorage.getItem(STORE_KEY);
          const data = raw ? JSON.parse(raw) : null;
          if (data?.engineerOverrides) {
            api.tb.engineerOverrides = data.engineerOverrides;
          }
          applyOverridesOnLoad(api.tb);
        } catch (_) { /* ignore */ }
        return r;
      };
    }

    // Wrap pass2 inventory to append reasons
    const prevHook = window.__tbHooks?.renderInventoryPanel;
    window.__tbHooks = window.__tbHooks || {};
    window.__tbHooks.renderInventoryPanel = function () {
      if (typeof prevHook === 'function') prevHook();
      // Annotate unplaced rows with reason
      try {
        const inv = typeof api.runInventory === 'function' ? api.runInventory() : null;
        $('tb-inv-list')?.querySelectorAll('[data-tb-inv-tag]').forEach((el) => {
          if (!el.classList.contains('unplaced')) return;
          const tag = el.getAttribute('data-tb-inv-tag');
          const reason = unplacedReason(tag, inv);
          if (!el.querySelector('.tb-inv-reason')) {
            const span = document.createElement('div');
            span.className = 'tb-inv-reason text-[8px] text-slate-600';
            span.textContent = reason;
            el.appendChild(span);
          }
        });
        // Filter modes
        const mode = api.tb.invFilterMode || 'unplaced';
        $('tb-inv-list')?.querySelectorAll('.tb-inv-item[data-tb-inv-tag]').forEach((el) => {
          const placed = el.classList.contains('placed') || el.classList.contains('selected');
          const unplaced = el.classList.contains('unplaced');
          let show = true;
          if (mode === 'unplaced') show = unplaced;
          else if (mode === 'all') show = true;
          else if (mode === 'review') show = unplaced; // compact: unplaced ≈ needs area
          else if (mode === 'engineer') {
            const tag = tagKey(el.getAttribute('data-tb-inv-tag'));
            show = !!(api.tb.engineerOverrides?.conveyors?.[tag]);
          }
          el.style.display = show ? '' : 'none';
        });
      } catch (_) { /* ignore */ }
      installInventoryContextMenu();
      enhanceInventoryPalette();
    };

    document.addEventListener('click', (ev) => {
      if (!ev.target.closest?.('#tb-res-ctx-menu')) hideCtxMenu();
    });

    // Expose for tests / diagnostics
    window.TransportResolution = {
      renderResolutionTopologyTable,
      renderAreaResolutionPanels,
      showAssignMenu,
      setNodeField,
      effectivePiArea,
      PROV,
      applyOverridesOnLoad,
      listControlStationCandidates,
      listStacklightCandidates,
    };

    // Initial paint
    try { api.renderTopologyTable?.(); } catch (_) { /* ignore */ }
    try { renderAreaResolutionPanels(); } catch (_) { /* ignore */ }
    try { window.__tbHooks.renderInventoryPanel?.(); } catch (_) { /* ignore */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
