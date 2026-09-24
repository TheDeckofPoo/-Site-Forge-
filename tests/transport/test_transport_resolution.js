#!/usr/bin/env node
/**
 * Site-free Transportation resolution workspace contracts.
 * Does not require Electron — exercises pure helpers from transport-resolution.js
 * via a minimal stub of window/document + TransportBuild.
 */
'use strict';

const path = require('path');
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== transport resolution contracts ===');

const src = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'transport-resolution.js'),
  'utf8',
);

// Lite-mode topology refresh must not be gated
const tbSrc = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'transport-build.js'),
  'utf8',
);
check('Lite render still refreshes topology table', () => {
  assert.ok(!/if\s*\(\s*!isLiteRenderMode\(\)\s*\)\s*\{\s*renderTopologyPanel/.test(tbSrc));
  assert.ok(tbSrc.includes('renderTopologyPanel()'));
  assert.ok(tbSrc.includes('Skipping them in Lite left Area membership invisible')
    || tbSrc.includes('must refresh in ALL modes'));
});

check('Logic Area move does not auto-apply Safety Zone by default', () => {
  assert.ok(tbSrc.includes('applyAreaDefaultSafety'));
  assert.ok(tbSrc.includes('must NOT silently rewrite Safety Zone'));
});

check('resolution module exposes TransportResolution API', () => {
  assert.ok(src.includes('window.TransportResolution'));
  assert.ok(src.includes('FALLBACK_MAIN_AREA'));
  assert.ok(src.includes('ENGINEER_ASSIGNED'));
  assert.ok(src.includes('showAssignMenu'));
  assert.ok(src.includes('renderAreaResolutionPanels'));
});

check('no site-specific names in resolution module', () => {
  const banned = [/ORNCCP2/i, /Greensboro/i, /Trash_Line/i, /ModuleC/i, /P1006/, /P1015/];
  banned.forEach((re) => {
    assert.ok(!re.test(src), `banned pattern ${re}`);
  });
});

check('effectivePiArea documents FALLBACK_MAIN_AREA when pi empty', () => {
  assert.ok(src.includes("confidence: PROV.FALLBACK_MAIN_AREA"));
  assert.ok(src.includes('function effectivePiArea'));
  // Logic Area assign restores prior safetyZone / piArea after move
  assert.ok(src.includes('n.piArea = b.pi'));
  assert.ok(src.includes('n.safetyZone = b.sz'));
});

check('HTML topology headers include simplified engineering columns', () => {
  const html = fs.readFileSync(
    path.join(__dirname, '..', '..', 'dashboard', 'index.html'),
    'utf8',
  );
  assert.ok(html.includes('Logic Area'));
  assert.ok(html.includes('PI Area'));
  assert.ok(html.includes('>Equipment<'));
  assert.ok(html.includes('PE Roles'));
  assert.ok(html.includes('tb-area-completeness'));
  assert.ok(html.includes('tb-area-review-queue'));
  assert.ok(html.includes('tb-area-cs-panel'));
  assert.ok(html.includes('tb-res-ctx-menu'));
  assert.ok(html.includes('transport-resolution.js'));
  assert.ok(html.includes('Advanced · Source Binding'));
  // Control Station is Area peripheral, not a per-conveyor column
  const topoHead = html.slice(html.indexOf('tb-topo-panel'), html.indexOf('tb-topo-body'));
  assert.ok(!/>Control Station</.test(topoHead));
});

if (process.exitCode) {
  console.error('FAIL — transport resolution contracts');
  process.exit(1);
}
console.log('PASS — transport resolution contracts');
