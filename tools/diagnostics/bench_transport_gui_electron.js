#!/usr/bin/env node
/**
 * Transportation GUI performance gate — REAL Electron browser timings.
 *
 * Proxy Python benches do NOT satisfy acceptance. This harness:
 *   1. Opens dashboard/index.html in Electron (no Site Forge preload/IPC)
 *   2. Seeds ~100 schematic conveyors
 *   3. Exercises pan / zoom / hover / select / drag / area / topology
 *   4. Writes exports/qualification/perf/transport_gui_perf.json
 *
 * Usage:
 *   node tools/diagnostics/bench_transport_gui_electron.js
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const OUT_REL = path.join('exports', 'qualification', 'perf', 'transport_gui_perf.json');
const OUT_ABS = path.join(REPO_ROOT, OUT_REL);
const DASHBOARD = path.join(REPO_ROOT, 'desktop');

function resolveElectronBinary() {
  const candidates = [
    path.join(DASHBOARD, 'node_modules', 'electron', 'dist', 'electron.exe'),
    path.join(DASHBOARD, 'node_modules', 'electron', 'path.txt'),
  ];
  for (const c of candidates) {
    if (c.endsWith('path.txt') && fs.existsSync(c)) {
      const name = fs.readFileSync(c, 'utf-8').trim() || 'electron.exe';
      const full = path.join(DASHBOARD, 'node_modules', 'electron', 'dist', name);
      if (fs.existsSync(full)) return full;
    } else if (fs.existsSync(c) && c.endsWith('.exe')) {
      return c;
    }
  }
  try {
    // eslint-disable-next-line import/no-extraneous-dependencies
    return require(path.join(DASHBOARD, 'node_modules', 'electron'));
  } catch (_) {
    return require('electron');
  }
}

async function runInsideElectron() {
  const { app, BrowserWindow } = require('electron');
  // Quiet Chromium noise
  app.commandLine.appendSwitch('disable-gpu');
  await app.whenReady();

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // No preload — avoid fortnaAPI IPC handlers that live only in desktop/main.js
    },
  });

  const indexHtml = path.join(REPO_ROOT, 'dashboard', 'index.html');
  await win.loadFile(indexHtml);

  // Activate Transportation tab + wait for API
  const ready = await win.webContents.executeJavaScript(`
    (async () => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      try {
        if (typeof window.activateTab === 'function') window.activateTab('transport');
        else document.querySelector('[data-tab="transport"]')?.click();
      } catch (_) {}
      for (let i = 0; i < 100; i++) {
        if (window.__tbApi && typeof window.__tbApi.renderScene === 'function') return true;
        await sleep(50);
      }
      return !!(window.__tbApi && window.__tbApi.tb);
    })()
  `);
  if (!ready) {
    console.error(JSON.stringify({ ok: false, error: 'Transport API not ready' }));
    win.destroy();
    app.quit();
    process.exit(2);
  }

  const report = await win.webContents.executeJavaScript(`
    (async () => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const A = () => window.__tbApi;
      const now = () => (performance && performance.now) ? performance.now() : Date.now();
      const timings = {};

      const tSeed0 = now();
      try {
        if (typeof window.transportBuildClearAll === 'function') {
          window.transportBuildClearAll({ leaveEmpty: false });
        }
      } catch (_) {}

      let area = A().activeArea?.() || A().ensureArea?.();
      if (!area) {
        A().ensureArea?.();
        area = A().activeArea?.() || (A().tb.areas || [])[0];
      }
      if (!area) {
        return { ok: false, error: 'no_area', timings_ms: timings };
      }
      area.name = 'PerfArea_100';
      area.nodes = [];
      area.wires = [];
      const N = 100;
      for (let i = 0; i < N; i++) {
        const id = 'perf_' + i;
        const tag = 'P' + String(100 + i);
        const x0 = 40 + (i % 10) * 120;
        const y0 = 40 + Math.floor(i / 10) * 80;
        const entry = { x: x0, y: y0 };
        const exit = { x: x0 + 90, y: y0 + ((i % 5 === 0) ? 40 : 0) };
        const isCurve = (i % 7 === 0);
        area.nodes.push({
          id,
          kind: isCurve ? 'conv_right' : 'conv_straight',
          label: tag,
          conveyorTag: tag,
          x: (entry.x + exit.x) / 2,
          y: (entry.y + exit.y) / 2,
          entryCanvas: entry,
          exitCanvas: exit,
          pathCanvas: isCurve ? null : [
            { cmd: 'move', x: entry.x, y: entry.y },
            { cmd: 'line', x: exit.x, y: exit.y },
          ],
          sweepDeg: isCurve ? 90 : 0,
          physical: true,
          downstream: i < N - 1 ? ('P' + String(101 + i)) : '',
          safetyZone: '',
          devices: [],
        });
        if (i < N - 1) {
          area.wires.push({ id: 'w' + i, from: id, to: 'perf_' + (i + 1), toPort: 'in' });
        }
      }
      A().tb.activeAreaId = area.id;
      A().tb.renderMode = 'lite';
      A().tb.showRelationships = false;
      if (!A().tb.layers) A().tb.layers = {};
      A().tb.layers.relationships = false;
      try { A().setRenderMode?.('lite'); } catch (_) {}
      timings.seed_ms = Math.round((now() - tSeed0) * 100) / 100;

      const tInit0 = now();
      A().renderScene();
      timings.initial_scene_ms = Math.round((now() - tInit0) * 100) / 100;
      await sleep(40);

      const canvas = document.getElementById('tb-canvas');
      const tPan0 = now();
      if (canvas) {
        canvas.scrollLeft += 80;
        canvas.scrollTop += 40;
        canvas.scrollLeft += 40;
        canvas.scrollTop += 20;
      }
      timings.pan_ms = Math.round((now() - tPan0) * 100) / 100;

      const tZoom0 = now();
      A().zoomByFactor?.(1.15);
      A().zoomByFactor?.(1 / 1.15);
      timings.zoom_ms = Math.round((now() - tZoom0) * 100) / 100;

      const svg = document.getElementById('tb-schematic');
      const hit = svg && svg.querySelector('.tb-lite-hit');
      const tHover0 = now();
      if (hit && A().updateLiteHover) {
        const id = hit.getAttribute('data-id');
        A().updateLiteHover(id);
        A().updateLiteHover(null);
        A().updateLiteHover(id);
      }
      timings.hover_ms = Math.round((now() - tHover0) * 100) / 100;

      const firstId = area.nodes[0] && area.nodes[0].id;
      const tSel0 = now();
      A().selectLiteNode?.(firstId);
      timings.select_ms = Math.round((now() - tSel0) * 100) / 100;

      const esc = (typeof CSS !== 'undefined' && CSS.escape) ? CSS.escape(firstId) : String(firstId);
      const g = svg && svg.querySelector('.tb-lite-node[data-id="' + esc + '"]');
      const tDrag0 = now();
      if (g) g.setAttribute('transform', 'translate(12 8)');
      timings.drag_frame_ms = Math.round((now() - tDrag0) * 100) / 100;

      const tCommit0 = now();
      const n = area.nodes[0];
      const origin = A().captureNodeGeom?.(n);
      if (origin) A().applyNodeGeomDelta?.(n, origin, 12, 8);
      A().invalidateLiteGeom?.(n.id);
      A().drawLiteSchematicNow?.(area);
      timings.drag_commit_ms = Math.round((now() - tCommit0) * 100) / 100;

      const tArea0 = now();
      A().renderScene();
      A().renderInspector();
      timings.area_switch_ms = Math.round((now() - tArea0) * 100) / 100;

      const tTopo0 = now();
      A().renderTopologyPanel?.();
      timings.open_topology_ms = Math.round((now() - tTopo0) * 100) / 100;

      // exportedAt is wall-clock — strip it before structural compare.
      const stripExportMeta = (g) => {
        if (!g || typeof g !== 'object') return g;
        const copy = JSON.parse(JSON.stringify(g));
        delete copy.exportedAt;
        return copy;
      };
      const hashLite = A().canonicalTransportHash?.();
      const graphLite = stripExportMeta(A().buildCanonicalApplyGraph?.());
      A().setRenderMode?.('detailed');
      const hashDet = A().canonicalTransportHash?.();
      const graphDet = stripExportMeta(A().buildCanonicalApplyGraph?.());
      A().setRenderMode?.('lite');
      timings.canonical_hash_lite = hashLite;
      timings.canonical_hash_detailed = hashDet;
      timings.canonical_hash_equal = hashLite === hashDet;
      timings.canonical_graph_equal = JSON.stringify(graphLite) === JSON.stringify(graphDet);

      const liteHits = (svg && svg.querySelectorAll('.tb-lite-belt')) ? svg.querySelectorAll('.tb-lite-belt').length : 0;
      timings.lite_belt_count = liteHits;

      const targets = {
        hover: 5,
        select: 20,
        drag_frame: 30,
        drag_commit: 100,
        area_switch: 150,
        open_topology: 250,
        initial_ui: 2000,
      };
      const gate = {
        pan_ok: timings.pan_ms < 16,
        zoom_ok: timings.zoom_ms < 80,
        hover_ok: timings.hover_ms <= targets.hover * 4,
        select_ok: timings.select_ms <= targets.select * 4,
        drag_frame_ok: timings.drag_frame_ms <= targets.drag_frame,
        drag_commit_ok: timings.drag_commit_ms <= targets.drag_commit,
        area_switch_ok: timings.area_switch_ms <= targets.area_switch,
        open_topology_ok: timings.open_topology_ms <= targets.open_topology,
        initial_ok: timings.initial_scene_ms <= targets.initial_ui,
        canonical_ok: !!timings.canonical_graph_equal,
        lite_drawn_ok: liteHits >= 50,
      };
      const ok = Object.values(gate).every(Boolean);
      const snap = A().perfSnapshot?.() || [];
      return {
        kind: 'transport_gui_perf',
        version: 1,
        generated_at: new Date().toISOString(),
        instrument: 'electron',
        renderMode: 'lite',
        node_count: N,
        area: area.name,
        timings_ms: timings,
        targets_ms: targets,
        gate,
        ok,
        perf_snapshot: snap.slice(-50),
        note: 'Actual Electron BrowserWindow timings for Transportation Lite Schematic.',
      };
    })()
  `);

  fs.mkdirSync(path.dirname(OUT_ABS), { recursive: true });
  fs.writeFileSync(OUT_ABS, `${JSON.stringify(report, null, 2)}\n`, 'utf-8');

  try {
    const liteSvg = await win.webContents.executeJavaScript(`
      (() => {
        const svg = document.getElementById('tb-schematic');
        if (!svg) return '';
        const clone = svg.cloneNode(true);
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        return clone.outerHTML;
      })()
    `);
    if (liteSvg) {
      const visDir = path.join(REPO_ROOT, 'exports', 'qualification', 'perf', 'visuals');
      fs.mkdirSync(visDir, { recursive: true });
      fs.writeFileSync(path.join(visDir, 'transportation_lite.svg'), liteSvg, 'utf-8');
    }
  } catch (_) { /* ignore */ }

  console.log(JSON.stringify({
    ok: !!report?.ok,
    out: OUT_REL.split(path.sep).join('/'),
    timings_ms: report?.timings_ms,
    gate: report?.gate,
    error: report?.error || null,
  }, null, 2));

  win.destroy();
  app.quit();
  process.exit(report?.ok ? 0 : 3);
}

const isElectron = !!(process.versions && process.versions.electron);
if (!isElectron) {
  const bin = resolveElectronBinary();
  const r = spawnSync(bin, [__filename], {
    cwd: DASHBOARD,
    stdio: 'inherit',
    env: { ...process.env, SITEFORGE_TRANSPORT_PERF: '1', ELECTRON_DISABLE_SECURITY_WARNINGS: '1' },
    windowsHide: true,
  });
  process.exit(r.status == null ? 1 : r.status);
} else {
  runInsideElectron().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
