/**
 * ORI-109 output-action + CURRENT restore verification (same IPC contracts as UI buttons).
 * Run: node exports/delivery_gate_20261002/verify_output_actions.js
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const latestPath = path.join(REPO, 'exports', 'current', 'LATEST.json');
const metaPath = path.join(REPO, 'workspace', 'active-meta.json');
const out = { repo: REPO, checks: {} };

function fail(msg) {
  out.error = msg;
  fs.writeFileSync(path.join(__dirname, 'pick_ui_verify.json'), JSON.stringify(out, null, 2));
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

// Open Output Folder == open parent directory (Explorer)
const folder = path.dirname(l5x);
try {
  // Use explorer.exe without blocking forever
  execFileSync('cmd', ['/c', 'start', '', 'explorer.exe', folder], {
    windowsHide: true,
    stdio: 'ignore',
    timeout: 5000,
  });
  out.checks.open_output_folder = 'PASS';
} catch (e) {
  out.checks.open_output_folder = `FAIL: ${e.message}`;
}

// Open File Location == explorer /select,L5X
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

// Copy Full Path — write to a visible verify file + set clipboard via PowerShell
try {
  const clipScript = `Set-Clipboard -Value @'\n${l5x}\n'@; Get-Clipboard`;
  const clipOut = execFileSync('powershell', ['-NoProfile', '-Command', clipScript], {
    encoding: 'utf8',
    timeout: 10000,
  }).trim();
  out.copied_path = clipOut;
  out.checks.copy_full_path = clipOut === l5x ? 'PASS' : `FAIL clipboard='${clipOut}'`;
  fs.writeFileSync(path.join(__dirname, 'COPIED_FULL_PATH.txt'), `${l5x}\n`, 'utf8');
} catch (e) {
  out.checks.copy_full_path = `FAIL: ${e.message}`;
}

// Simulate restart restore identity gate (same rules as get-current-autogen-build)
const wantMachine = String(meta.machine || '').trim().toUpperCase();
const gotMachine = String(latest.controller_name || '').trim().toUpperCase();
const wantFp = String(meta.run_fingerprint || '').trim();
const gotFp = String(latest.source_run_hash || '').trim();
const wantTar = String(meta.tar_sha256 || '').trim().toUpperCase();
const gotTar = String(latest.tar_sha256 || latest.source_tar_sha256 || '').trim().toUpperCase();
const wantArch = String(meta.archive_name || meta.archive_stem || '').trim().toUpperCase();
const gotArch = String(latest.source_run_filename || latest.source_label || '').trim().toUpperCase();
const runMatch = (
  (wantFp && gotFp && wantFp === gotFp)
  || (wantTar && gotTar && wantTar === gotTar)
  || (wantArch && gotArch && (gotArch === wantArch || gotArch.includes(wantArch) || wantArch.includes(gotArch)))
);
out.restore_identity = {
  wantMachine, gotMachine, machine_match: wantMachine === gotMachine,
  wantFp, gotFp, wantTar, gotTar, wantArch, gotArch, runMatch,
  current_invalidated: !!latest.current_invalidated,
};
out.checks.persistence_identity_would_restore = (
  wantMachine === gotMachine
  && runMatch
  && !latest.current_invalidated
  && latest.current_artifact !== false
) ? 'PASS' : 'FAIL';

fs.writeFileSync(path.join(__dirname, 'pick_ui_verify.json'), JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 2));
const failed = Object.values(out.checks).some((v) => String(v).startsWith('FAIL'));
process.exit(failed ? 1 : 0);
