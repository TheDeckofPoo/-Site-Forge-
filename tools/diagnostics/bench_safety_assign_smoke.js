#!/usr/bin/env node
/**
 * Real Electron Safety assign smoke — Warden 2c8789a path.
 *
 *   Clear → Import MSCRENOPICK → create Area_Test1_ESZone1 →
 *   check ESPB2/24/32/ESLS2 → click Assign checked inventory → this zone →
 *   verify 4 members / left Default → Apply → refresh
 *
 * Usage (from repo root):
 *   node tools/diagnostics/bench_safety_assign_smoke.js
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
  throw new Error('Electron not found — run npm install in desktop/');
}

function main() {
  if (!fs.existsSync(PICK)) {
    console.error(JSON.stringify({ ok: false, error: 'MSCRENOPICK archive missing', expected: PICK }, null, 2));
    process.exit(2);
  }
  // Stamp runtime provenance before launch so Electron == worktree HEAD
  try {
    const sha = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: REPO_ROOT, encoding: 'utf8' }).stdout.trim();
    const short = spawnSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: REPO_ROOT, encoding: 'utf8' }).stdout.trim();
    const branch = spawnSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: REPO_ROOT, encoding: 'utf8' }).stdout.trim();
    const payload = {
      gitSha: sha,
      gitShaShort: short,
      branch,
      repoRoot: REPO_ROOT,
      sourceRoot: REPO_ROOT,
      dashboardSource: path.join(REPO_ROOT, 'dashboard', 'index.html'),
      desktopDir: DESKTOP,
      mode: 'dev',
      startedAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      provenanceSource: 'git',
      worktree: REPO_ROOT,
    };
    fs.writeFileSync(path.join(DESKTOP, '.runtime_build.json'), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
    console.log('PROVENANCE', short, branch);
  } catch (e) {
    console.warn('runtime stamp failed', e.message);
  }

  const bin = resolveElectron();
  console.log('Safety assign smoke — launching Site Forge Electron…');
  const r = spawnSync(bin, ['.'], {
    cwd: DESKTOP,
    stdio: 'inherit',
    env: {
      ...process.env,
      SITEFORGE_SAFETY_ASSIGN_SMOKE: '1',
      ELECTRON_DISABLE_SECURITY_WARNINGS: '1',
    },
    windowsHide: true,
    timeout: 900000,
  });
  const out = path.join(REPO_ROOT, 'exports', 'demo', 'SAFETY_ASSIGN_SMOKE.json');
  const summary = {
    exit_code: r.status,
    result_exists: fs.existsSync(out),
  };
  if (fs.existsSync(out)) {
    try { summary.result = JSON.parse(fs.readFileSync(out, 'utf8')); } catch (_) { /* ignore */ }
  }
  console.log(JSON.stringify(summary, null, 2));
  process.exit(r.status == null ? 1 : r.status);
}

main();
