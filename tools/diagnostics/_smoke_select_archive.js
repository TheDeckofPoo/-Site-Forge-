#!/usr/bin/env node
/**
 * Headless smoke: verify Load RUN wiring without opening a GUI dialog.
 * Exit 0 only if renderer syntax + preload + main contracts hold.
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const checks = [];

function check(id, ok, detail) {
  checks.push({ id, ok: !!ok, detail: String(detail || '') });
}

const fp = path.join(ROOT, 'dashboard', 'fortna-plus.js');
const syn = spawnSync('node', ['--check', fp], { encoding: 'utf8' });
check('renderer_syntax', syn.status === 0, syn.stderr || syn.stdout || 'ok');

const js = fs.readFileSync(fp, 'utf8');
check('browse_helper', js.includes('browseAndImportRunArchive'), 'function present');
check('picker_error_text', js.includes('Unable to open RUN archive picker'), 'user feedback');
check('io_button_wired', js.includes("btn-io-browse-run") && js.includes('browseAndImportRunArchive'), 'Load RUN uses helper');

const pre = fs.readFileSync(path.join(ROOT, 'desktop', 'preload.js'), 'utf8');
check('preload_selectArchive', /selectArchive\s*:/.test(pre), 'exposed');
check('preload_importRun', /importRun\s*:/.test(pre), 'exposed');

const main = fs.readFileSync(path.join(ROOT, 'desktop', 'main.js'), 'utf8');
check('main_ipc', main.includes("ipcMain.handle('select-archive'"), 'handler');
check('main_all_files', main.includes('All Files'), 'filter');
check('main_error_path', main.includes('Unable to open RUN archive picker'), 'catch');

const ps1 = fs.readFileSync(path.join(ROOT, 'desktop', 'Launch-Electron.ps1'), 'utf8');
check('launcher_ascii', ps1.includes(' -> ') && !ps1.includes('→'), 'ASCII arrow');

const ok = checks.every((c) => c.ok);
console.log(JSON.stringify({ ok, checks }, null, 2));
process.exit(ok ? 0 : 1);
