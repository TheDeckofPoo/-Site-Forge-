#!/usr/bin/env node
/**
 * MSCRENO / MSCRENOPICK Tuesday demo workflow — REAL Electron + Active Project.
 *
 * Measures the actual Site Forge path:
 *   Clear → Load MSCRENOPICK → hydrate I/O/Transport/Safety → interact →
 *   Apply → cross-project isolation → readiness report
 *
 * Writes:
 *   exports/qualification/perf/mscreno_demo_perf.json
 *   exports/demo/MSCRENO_DEMO_READINESS.json
 *   exports/demo/MSCRENO_DEMO_READINESS.md
 *
 * Usage (from repo root):
 *   node tools/diagnostics/bench_mscreno_demo_workflow.js
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const DESKTOP = path.join(REPO_ROOT, 'desktop');
const PICK = path.join(
  REPO_ROOT,
  'workspace',
  'inbox',
  '20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz',
);

function resolveElectron() {
  const pathFile = path.join(DESKTOP, 'node_modules', 'electron', 'path.txt');
  if (fs.existsSync(pathFile)) {
    const name = fs.readFileSync(pathFile, 'utf-8').trim() || 'electron.exe';
    const full = path.join(DESKTOP, 'node_modules', 'electron', 'dist', name);
    if (fs.existsSync(full)) return full;
  }
  const exe = path.join(DESKTOP, 'node_modules', 'electron', 'dist', 'electron.exe');
  if (fs.existsSync(exe)) return exe;
  try {
    return require(path.join(DESKTOP, 'node_modules', 'electron'));
  } catch (_) {
    throw new Error('Electron not found — run npm install in desktop/');
  }
}

function main() {
  if (!fs.existsSync(PICK)) {
    console.error(JSON.stringify({
      ok: false,
      error: 'MSCRENOPICK archive missing',
      expected: PICK,
    }, null, 2));
    process.exit(2);
  }

  const bin = resolveElectron();
  console.log('MSCRENO demo smoke — launching Site Forge Electron…');
  const r = spawnSync(bin, ['.'], {
    cwd: DESKTOP,
    stdio: 'inherit',
    env: {
      ...process.env,
      SITEFORGE_DEMO_SMOKE: '1',
      ELECTRON_DISABLE_SECURITY_WARNINGS: '1',
    },
    windowsHide: true,
    // Import + Transport autobuild + cross-project can exceed 15m on first cold run
    timeout: 1800000,
  });

  const perf = path.join(REPO_ROOT, 'exports', 'qualification', 'perf', 'mscreno_demo_perf.json');
  const readiness = path.join(REPO_ROOT, 'exports', 'demo', 'MSCRENO_DEMO_READINESS.json');
  const summary = {
    exit_code: r.status,
    perf_exists: fs.existsSync(perf),
    readiness_exists: fs.existsSync(readiness),
  };
  if (fs.existsSync(readiness)) {
    try {
      summary.readiness = JSON.parse(fs.readFileSync(readiness, 'utf-8'));
    } catch (_) { /* ignore */ }
  }
  console.log(JSON.stringify(summary, null, 2));
  process.exit(r.status == null ? 1 : r.status);
}

main();
