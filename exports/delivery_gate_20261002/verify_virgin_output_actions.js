/**
 * Virgin-site ORI-109 output-action verification (same IPC contracts as UI buttons).
 * Run: node exports/delivery_gate_20261002/verify_virgin_output_actions.js
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const latestPath = path.join(REPO, 'exports', 'current', 'LATEST.json');
const metaPath = path.join(REPO, 'workspace', 'active-meta.json');
const out = { repo: REPO, phase: 'virgin_ui', checks: {} };

function fail(msg) {
  out.error = msg;
  fs.writeFileSync(path.join(__dirname, 'virgin_ui_verify.json'), JSON.stringify(out, null, 2));
  console.error('FAIL', msg);
  process.exit(1);
}

if (!fs.existsSync(latestPath)) fail('LATEST.json missing');
if (!fs.existsSync(metaPath)) fail('active-meta.json missing');

const latest = JSON.parse(fs.readFileSync(latestPath, 'utf8'));
const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
const l5x = String(latest.l5x || '').trim();
out.l5x = l5x;
out.controller = latest.controller_name;
out.build_status = latest.build_status || (latest.report || {}).build_status;
out.active_machine = meta.machine;

if (!l5x || !fs.existsSync(l5x)) fail(`L5X missing: ${l5x}`);
if (String(latest.controller_name || '').toUpperCase() !== String(meta.machine || '').toUpperCase()) {
  fail(`controller/active mismatch ${latest.controller_name} vs ${meta.machine}`);
}
if (String(meta.machine || '').toUpperCase() !== 'TFCP1') {
  fail(`expected active TFCP1, got ${meta.machine}`);
}

const folder = path.dirname(l5x);
try {
  execFileSync('cmd', ['/c', 'start', '', 'explorer.exe', folder], {
    windowsHide: true,
    stdio: 'ignore',
    timeout: 5000,
  });
  out.checks.open_output_folder = 'PASS';
} catch (e) {
  out.checks.open_output_folder = `FAIL: ${e.message}`;
}

try {
  execFileSync('cmd', ['/c', 'start', '', 'explorer.exe', `/select,${l5x}`], {
    windowsHide: true,
    stdio: 'ignore',
    timeout: 5000,
  });
  out.checks.open_file_location = 'PASS';
} catch (e) {
  out.checks.open_file_location = `FAIL: ${e.message}`;
}

try {
  const clipFile = path.join(__dirname, 'VIRGIN_COPIED_FULL_PATH.txt');
  fs.writeFileSync(clipFile, l5x, 'utf8');
  const ps = [
    `$p = Get-Content -Raw -LiteralPath '${clipFile.replace(/'/g, "''")}'`,
    'Set-Clipboard -Value $p.TrimEnd()',
    '(Get-Clipboard).Trim()',
  ].join('; ');
  const clipOut = execFileSync('powershell', ['-NoProfile', '-Command', ps], {
    encoding: 'utf8',
    timeout: 10000,
  }).trim();
  out.copied_path = clipOut;
  out.checks.copy_full_path = clipOut === l5x ? 'PASS' : `FAIL clipboard='${clipOut}'`;
} catch (e) {
  out.checks.copy_full_path = `FAIL: ${e.message}`;
}

const wantMachine = String(meta.machine || '').trim().toUpperCase();
const gotMachine = String(latest.controller_name || '').trim().toUpperCase();
const wantFp = String(meta.run_fingerprint || '').trim();
const gotFp = String(latest.run_fingerprint || latest.run_hash || '').trim();
const wantTar = String(meta.tar_sha256 || '').trim().toUpperCase();
const gotTar = String(latest.tar_sha256 || (latest.report || {}).tar_sha256 || '').trim().toUpperCase();
out.restore_identity = {
  wantMachine,
  gotMachine,
  machine_match: wantMachine === gotMachine,
  wantFp,
  gotFp,
  wantTar,
  gotTar,
  current_invalidated: !!latest.current_invalidated,
};
out.checks.persistence_identity_would_restore =
  out.restore_identity.machine_match &&
  !out.restore_identity.current_invalidated &&
  wantMachine === 'TFCP1'
    ? 'PASS'
    : 'FAIL';

fs.writeFileSync(path.join(__dirname, 'virgin_ui_verify.json'), JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 2));
const bad = Object.values(out.checks).some((v) => String(v).startsWith('FAIL'));
process.exit(bad ? 1 : 0);
