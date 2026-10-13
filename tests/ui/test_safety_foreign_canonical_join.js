#!/usr/bin/env node
/**
 * P0 — Safety UI must preserve FOREIGN_CONTROLLER from canonical ledger.
 * Gold: ESLS1 / ESLS13P7-* are FOREIGN_CONTROLLER — MSCRENOSHIP in escalation,
 * but safety_model stamped UNKNOWN_OWNER with blank machine.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const REPO = path.join(__dirname, '..', '..');
const SB = fs.readFileSync(path.join(REPO, 'dashboard', 'safety-build.js'), 'utf8');

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== Safety FOREIGN canonical ownership join ===');

check('canonicalOwnershipByName helper exists', () => {
  assert.ok(SB.includes('function canonicalOwnershipByName'));
  assert.ok(SB.includes('function enrichDeviceFromCanonicalOwnership'));
  assert.ok(SB.includes('provenance_non_actionable'));
});

check('filterDevicesToActiveMachine honors already-FOREIGN before UNKNOWN stamp', () => {
  const start = SB.indexOf('function filterDevicesToActiveMachine');
  const end = SB.indexOf('function renderInventory');
  const body = SB.slice(start, end);
  assert.ok(body.includes('alreadyForeign'));
  assert.ok(body.includes('enrichDeviceFromCanonicalOwnership'));
  assert.ok(body.includes("inventory_scope: 'UNRELATED_FOREIGN'"));
  assert.ok(body.includes('FOREIGN_CONTROLLER'));
});

check('formatNonAssignableReason renders FOREIGN_CONTROLLER — ctrl', () => {
  const start = SB.indexOf('function formatNonAssignableReason');
  const end = SB.indexOf('function isAssignablePhysicalSafetyDevice');
  const body = SB.slice(start, end);
  assert.ok(body.includes('FOREIGN_CONTROLLER${ctrl'));
  assert.ok(body.includes('Not assignable to'));
});

check('loadDevicesFromRun prefetches Workbench provenance for join', () => {
  assert.ok(SB.includes('getIoReviewWorkbench'));
  assert.ok(SB.includes('canonicalIoOwnership'));
  assert.ok(SB.includes('Prefetch canonical I/O ownership') || SB.includes('FOREIGN_CONTROLLER'));
});

check('gold escalation foreign facts', () => {
  const diag = path.join(REPO, 'exports', 'diagnostics');
  const dirs = fs.readdirSync(diag).filter((d) => d.startsWith('gold_repro_7c08e71'));
  assert.ok(dirs.length >= 1);
  const snap = path.join(
    diag,
    dirs.sort().slice(-1)[0],
    'workspace',
    'io_canonical_escalation_snapshot.json',
  );
  const data = JSON.parse(fs.readFileSync(snap, 'utf8'));
  const byName = Object.fromEntries(
    (data.devices || []).map((d) => [d.canonical_name || d.name, d]),
  );
  for (const n of ['ESLS1', 'ESLS13P7-1', 'ESLS13P7-2', 'ESLS13P9-1']) {
    assert.ok(byName[n], `${n} missing from gold escalation`);
    assert.strictEqual(byName[n].final_status, 'FOREIGN_CONTROLLER');
    assert.strictEqual(byName[n].evidence_class, 'FOREIGN_CONTROLLER');
    const ctrl = byName[n].controller
      || (byName[n].peer_controllers || [])[0]
      || byName[n].peer_controller;
    assert.strictEqual(ctrl, 'MSCRENOSHIP', `${n} controller`);
  }
});

if (process.exitCode) {
  console.error('FAILED');
  process.exit(1);
}
console.log('OK');
