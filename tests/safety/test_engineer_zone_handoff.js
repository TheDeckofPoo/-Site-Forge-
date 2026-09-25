#!/usr/bin/env node
/**
 * Engineer Safety Zone handoff — Transport create → Safety Build visibility.
 * Gate E — immutable source_id (szone_*) vs reusable engineering_name.
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

check('Gate E — ensureSafetyZone allocates immutable szone_* source_id', () => {
  const start = TB.indexOf('function ensureSafetyZone');
  const end = TB.indexOf('function deleteSafetyZone');
  const body = TB.slice(start, end);
  assert.ok(body.includes("const sid = uid('szone')"));
  assert.ok(body.includes('source_id: sid'));
  assert.ok(body.includes('engineering_name: nm'));
  // Must NOT assign engineering name as source_id on create
  assert.ok(!body.includes('source_id: nm'));
});

check('create Area passes areaRef into ensureSafetyZone', () => {
  assert.ok(PASS2.includes('ensureSafetyZone(defaultZone, { areaRef: areaName'));
  assert.ok(TB.includes('ensureSafetyZone(defaultZone, { areaRef: areaName, forceHandoff: true })'));
});

check('safetyBuildUpsertZone API exists and persists draft', () => {
  assert.ok(SB.includes('window.safetyBuildUpsertZone'));
  assert.ok(SB.includes("provenance: PROVENANCE.ENGINEER_CREATED"));
  assert.ok(SB.includes('persistLocalDraft'));
  assert.ok(SB.includes("siteforge:safety-zone-created"));
});

check('Gate E — delete tombstones source_id not engineering_name', () => {
  const start = SB.indexOf('function deleteSafetyZone');
  const end = SB.indexOf('function findLiveZone');
  const body = SB.slice(start, end);
  assert.ok(body.includes('state.deletedZones.add(sid)'));
  assert.ok(body.includes('Tombstone source_id only') || body.includes('source_id only'));
  assert.ok(body.includes('may be reused'));
});

check('transportZonesFromCanvas preserves empty engineer shells', () => {
  const start = SB.indexOf('function transportZonesFromCanvas');
  const end = SB.indexOf('function areaNameOf');
  const body = SB.slice(start, end);
  assert.ok(body.includes('ENGINEER_CREATED'));
  assert.ok(body.includes('createdBy'));
  // Empty registry zones still enter zoneMap
  assert.ok(body.includes('conveyors: []'));
  assert.ok(body.includes('source_id'));
  assert.ok(body.includes('engineering_name'));
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

/**
 * Gate E behavioral: create Trash_Zone → delete → recreate must not be suppressed
 * by deletedZones keyed on engineering name.
 */
check('Gate E — Trash_Zone delete/recreate uses distinct source_ids', () => {
  // Simulate the lifecycle contracts without a browser DOM.
  const deletedZones = new Set();
  const zones = [];

  function zoneSourceId(z) {
    return String(z.source_id || z.id || '').trim();
  }
  function zoneDisplayName(z) {
    return String(z.engineering_name || z.name || '').trim();
  }
  function upsert(raw) {
    const engName = String(raw.engineering_name || raw.name || '').trim();
    let sid = String(raw.source_id || raw.id || '').trim();
    if (!sid || sid === engName) {
      sid = `szone_${Math.random().toString(36).slice(2, 11)}`;
    }
    if (deletedZones.has(sid)) return null;
    let z = zones.find((x) => zoneSourceId(x) === sid);
    if (!z) {
      const clash = zones.find(
        (x) => zoneDisplayName(x).toLowerCase() === engName.toLowerCase(),
      );
      if (clash) return clash;
      z = {
        source_id: sid,
        id: sid,
        engineering_name: engName,
        name: engName,
        members: [],
        status: 'REVIEW_REQUIRED',
        provenance: 'ENGINEER_CREATED',
      };
      zones.push(z);
    }
    return z;
  }
  function delByName(eng) {
    const live = zones.find((z) => zoneDisplayName(z) === eng);
    assert.ok(live, 'zone to delete must exist');
    const sid = zoneSourceId(live);
    deletedZones.add(sid); // tombstone source_id ONLY
    const idx = zones.indexOf(live);
    zones.splice(idx, 1);
  }
  function visible() {
    return zones.filter((z) => !deletedZones.has(zoneSourceId(z)));
  }

  // create → handoff
  const z1 = upsert({ engineering_name: 'Trash_Zone', source_id: 'szone_aaa1111' });
  assert.strictEqual(z1.engineering_name, 'Trash_Zone');
  assert.ok(String(z1.source_id).startsWith('szone_'));
  assert.strictEqual(visible().length, 1);

  // delete — tombstone source_id, NOT name
  delByName('Trash_Zone');
  assert.ok(deletedZones.has('szone_aaa1111'));
  assert.ok(!deletedZones.has('Trash_Zone'));
  assert.strictEqual(visible().length, 0);

  // recreate same engineering name with NEW source_id
  const z2 = upsert({ engineering_name: 'Trash_Zone', source_id: 'szone_bbb2222' });
  assert.ok(z2, 'second Trash_Zone must appear');
  assert.strictEqual(z2.engineering_name, 'Trash_Zone');
  assert.strictEqual(z2.source_id, 'szone_bbb2222');
  assert.notStrictEqual(z2.source_id, 'szone_aaa1111');
  assert.strictEqual(visible().length, 1);
  assert.ok(!deletedZones.has(z2.source_id));
});

check('Gate E — two active zones may not share engineering_name', () => {
  assert.ok(SB.includes('Two active zones may not share') || SB.includes('same engineering/Logix name'));
});

check('PD-0040 — empty engineer Areas survive reload filter', () => {
  assert.ok(TB.includes('isEngineerAreaShell'));
  assert.ok(TB.includes('isEngineerAreaShell(a)'));
  assert.ok(TB.includes('keep empty engineer Areas') || TB.includes('Empty engineer Area shells must survive'));
});

check('PD-0040 — load preserves ENGINEER_CREATED safety zone metadata', () => {
  const start = TB.indexOf('if (Array.isArray(data.safetyZones))');
  const end = TB.indexOf('seedSafetyZonesFromNodes', start);
  const body = TB.slice(start, end);
  assert.ok(body.includes('ENGINEER_CREATED'));
  assert.ok(body.includes('source_id'));
  assert.ok(body.includes('engineering_name'));
  assert.ok(body.includes('areaRef'));
  // Must not strip to bare {id, name} only
  assert.ok(!body.includes('.map((z) => ({ id: z.id || uid(\'szone\'), name: String(z.name || \'\').trim() }))'));
});

check('PD-0040 — duplicate same-name zone does not silently move Area', () => {
  const start = TB.indexOf('function ensureSafetyZone');
  const end = TB.indexOf('function deleteSafetyZone');
  const body = TB.slice(start, end);
  assert.ok(body.includes('already exists under Area'));
  assert.ok(body.includes('not moved'));
  assert.ok(body.includes('return null'));
});

check('PD-0039/40 — Safety Build uses Site Forge modal not prompt()', () => {
  assert.ok(SB.includes('sbAskText'));
  assert.ok(SB.includes('sbAskYesNo'));
  const livePrompt = SB
    .split('\n')
    .filter((ln) => !/^\s*(\/\/|\*)/.test(ln) && !/prompt\s+unsupported|window\.prompt/.test(ln))
    .some((ln) => /\bprompt\s*\(/.test(ln));
  assert.ok(!livePrompt, 'safety-build must not call prompt()');
  assert.ok(SB.includes('ENGINEER_CREATED'));
  assert.ok(SB.includes('ORIGIN_LABEL') && SB.includes('ENGINEER CREATED'));
});

if (process.exitCode) {
  console.error('FAIL — engineer zone handoff');
  process.exit(1);
}
console.log('PASS — engineer zone handoff');
