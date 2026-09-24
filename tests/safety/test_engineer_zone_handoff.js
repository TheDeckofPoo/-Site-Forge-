#!/usr/bin/env node
/**
 * Engineer Safety Zone handoff — Transport create → Safety Build visibility.
 * Site-neutral contracts (no Greensboro / ORNCCP2).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const TB = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'transport-build.js'),
  'utf8',
);
const SB = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'safety-build.js'),
  'utf8',
);
const PASS2 = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'transport-build-pass2.js'),
  'utf8',
);

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== engineer Safety Zone handoff ===');

check('ensureSafetyZone stamps ENGINEER_CREATED + areaRef + members=[]', () => {
  const start = TB.indexOf('function ensureSafetyZone');
  const end = TB.indexOf('function deleteSafetyZone');
  const body = TB.slice(start, end);
  assert.ok(body.includes("createdBy: 'engineer'"));
  assert.ok(body.includes("provenance: 'ENGINEER_CREATED'"));
  assert.ok(body.includes('areaRef'));
  assert.ok(body.includes('members: []'));
  assert.ok(body.includes("status: 'REVIEW_REQUIRED'"));
  assert.ok(body.includes('safetyBuildUpsertZone'));
  assert.ok(body.includes('siteforge:safety-zone-created'));
});

check('create Area passes areaRef into ensureSafetyZone', () => {
  assert.ok(PASS2.includes('ensureSafetyZone(defaultZone, { areaRef: areaName'));
});

check('safetyBuildUpsertZone API exists and persists draft', () => {
  assert.ok(SB.includes('window.safetyBuildUpsertZone'));
  assert.ok(SB.includes("provenance: PROVENANCE.ENGINEER_CREATED"));
  assert.ok(SB.includes('persistLocalDraft'));
  assert.ok(SB.includes("siteforge:safety-zone-created"));
});

check('transportZonesFromCanvas preserves empty engineer shells', () => {
  const start = SB.indexOf('function transportZonesFromCanvas');
  const end = SB.indexOf('function areaNameOf');
  const body = SB.slice(start, end);
  assert.ok(body.includes('ENGINEER_CREATED'));
  assert.ok(body.includes('createdBy'));
  // Empty registry zones still enter zoneMap
  assert.ok(body.includes('conveyors: []'));
});

check('buildClientModel does not drop empty engineer *_ESZone1 shells', () => {
  // Engineer shells must not hit the placeholder-only early return
  assert.ok(SB.includes('!engineerShell && isPlaceholderOrTestZoneName'));
  assert.ok(SB.includes("provenance: engineerShell ? PROVENANCE.ENGINEER_CREATED"));
});

check('ENGINEER_CREATED survives rebuild keep filter', () => {
  assert.ok(SB.includes('z.provenance === PROVENANCE.ENGINEER_CREATED'));
});

check('signal evidence says related signals not aliases', () => {
  assert.ok(SB.includes('related signal'));
  assert.ok(SB.includes('PRIMARY physical signal'));
  assert.ok(SB.includes('AUX physical signal'));
  assert.ok(SB.includes('nonphysical RUN evidence'));
  assert.ok(SB.includes('TAG/NAME variant'));
  assert.ok(!/alias\(es\)/.test(SB));
});

check('no site-specific production conditions', () => {
  for (const banned of ['ORNCCP2', 'Greensboro', 'Trash_Line', 'ModuleC']) {
    assert.ok(
      !new RegExp(`if\\s*\\([^)]*${banned}`).test(SB + TB),
      banned,
    );
  }
});

if (process.exitCode) {
  console.error('FAIL — engineer zone handoff');
  process.exit(1);
}
console.log('PASS — engineer zone handoff');
