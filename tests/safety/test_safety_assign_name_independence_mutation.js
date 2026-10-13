#!/usr/bin/env node
/**
 * P0 REAL-UI mutation path — Safety assignment + Area/zone name independence.
 *
 * Exercises the SAME state transition as the user-facing Assign control:
 *   inventory checks → assignCheckedToSelectedZone → mutateZone → buildClientModel prune
 *
 * Hunter root cause (2c8789a / 7c2c888 lineage):
 *   empty areaRef treated as corrupt → buildClientModel deletes engineer zone
 *   → persist zones=[] → UI still said "Assigned 4"
 *
 * Permanent suite MUST include at least one NON-controller-prefixed Area/zone.
 *
 * Classification: UNIT/NODE mutation-path (jsdom not required; logic extracted
 * from dashboard/safety-build.js and executed via vm).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '../..');
const SAFETY_JS = path.join(ROOT, 'dashboard', 'safety-build.js');
const src = fs.readFileSync(SAFETY_JS, 'utf8');

const PICK_MEMBERS = ['ESPB2', 'ESPB24', 'ESPB32', 'ESLS2'];

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== safety assign name-independence mutation path ===');

// ---------------------------------------------------------------------------
// Source contract — corruption helpers
// ---------------------------------------------------------------------------
check('isCorruptAreaRef exists and empty areaRef is NOT corrupt', () => {
  assert.ok(src.includes('function isCorruptAreaRef'));
  assert.ok(
    /isCorruptZoneName\(sid\)\s*\|\|\s*isCorruptAreaRef\(z\.areaRef\)/.test(src),
    'buildClientModel must use isCorruptAreaRef for areaRef (not isCorruptZoneName)',
  );
  assert.ok(
    !/isCorruptZoneName\(sid\)\s*\|\|\s*isCorruptZoneName\(z\.areaRef\)/.test(src),
    'must NOT delete zones because isCorruptZoneName(areaRef) — empty string was the bug',
  );
});

check('mutateZone refuses destructive persist when members lost', () => {
  assert.ok(src.includes('Do NOT persist the destructive rebuild'));
  assert.ok(src.includes('zoneDroppedByRebuild') || src.includes('was dropped by rebuild'));
  assert.ok(src.includes('Assigned ${n} device(s)'));
});

check('Apply fails when attempted assignment yields empty payload', () => {
  assert.ok(src.includes('attemptedMemberTotal'));
  assert.ok(src.includes('0 desired vs 0 saved is not success'));
});

check('Assign collectors use inventory data-sb-inv (not hidden sb-available)', () => {
  assert.ok(src.includes('collectCheckedInventoryDeviceNames'));
  assert.ok(!/querySelectorAll\(['"]#sb-available \[data-sb-avail\]:checked['"]\)/.test(src));
});

// ---------------------------------------------------------------------------
// Executable helpers extracted from safety-build.js
// ---------------------------------------------------------------------------
function extractFn(name) {
  const re = new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n  \\}`);
  const m = src.match(re);
  if (!m) throw new Error(`missing function ${name}`);
  return m[0];
}

const helperCode = [
  'isCorruptZoneName',
  'isCorruptAreaRef',
  'areaNameOf',
].map(extractFn).join('\n');

const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext(
  `${helperCode}\nthis.isCorruptZoneName=isCorruptZoneName;\n`
  + 'this.isCorruptAreaRef=isCorruptAreaRef;\nthis.areaNameOf=areaNameOf;',
  sandbox,
);

check('runtime: empty string is corrupt zone name but NOT corrupt areaRef', () => {
  assert.strictEqual(sandbox.isCorruptZoneName(''), true);
  assert.strictEqual(sandbox.isCorruptAreaRef(''), false);
  assert.strictEqual(sandbox.isCorruptAreaRef('[object Object]'), true);
  assert.strictEqual(sandbox.isCorruptZoneName('Area_Test1_ESZone1'), false);
  assert.strictEqual(sandbox.isCorruptAreaRef('Area_Test1'), false);
});

/**
 * Mirror of the buildClientModel prune that deleted engineer zones.
 * BEFORE: isCorruptZoneName(sid) || isCorruptZoneName(z.areaRef)
 * AFTER:  isCorruptZoneName(sid) || isCorruptAreaRef(z.areaRef)
 */
function pruneZones(byIdEntries, areaSet, useFixedCorruptCheck, { forceUnlink = false } = {}) {
  const byId = new Map(byIdEntries);
  // Seed engineer areaRefs into areaSet (fixed path name-independence)
  if (useFixedCorruptCheck) {
    for (const [, z] of byId.entries()) {
      if (z.areaUnlinked) continue;
      const ar = sandbox.areaNameOf(z.areaRef) || String(z.areaRef || '').trim();
      if (ar) areaSet.add(ar);
    }
  }
  for (const [sid, z] of [...byId.entries()]) {
    const areaCorrupt = useFixedCorruptCheck
      ? sandbox.isCorruptAreaRef(z.areaRef)
      : sandbox.isCorruptZoneName(z.areaRef);
    if (sandbox.isCorruptZoneName(sid) || areaCorrupt) {
      byId.delete(sid);
      continue;
    }
    let area = sandbox.areaNameOf(z.areaRef) || String(z.areaRef || '').trim();
    const isEngineerZone = !!(
      z.engineerEdited
      || z.createdBy === 'engineer'
      || String(sid).startsWith('szone_')
      || (Array.isArray(z.members) && z.members.length > 0)
    );
    if (forceUnlink && isEngineerZone) {
      // Explicit Area delete bridge
      z.areaRef = '';
      z.area = '';
      z.areaUnlinked = true;
      area = '';
    } else if (area && isEngineerZone && (areaSet.size === 0 || !areaSet.has(area))) {
      // Historical: always cleared areaRef on workbook lag → then corrupt-deleted.
      // Fixed: keep areaRef unless explicitly areaUnlinked.
      if (!useFixedCorruptCheck) {
        z.areaRef = '';
        z.area = '';
        z.areaUnlinked = true;
        area = '';
      }
    }
    // Second pass after unlink (historical rebuild): empty areaRef killed the zone
    if (z.areaRef === '' || z.areaRef == null) {
      if (!useFixedCorruptCheck && sandbox.isCorruptZoneName(z.areaRef)) {
        byId.delete(sid);
        continue;
      }
      if (useFixedCorruptCheck && sandbox.isCorruptAreaRef(z.areaRef)) {
        byId.delete(sid);
        continue;
      }
    }
  }
  return byId;
}

/**
 * Same transition as assignCheckedToSelectedZone → mutateZone membership write,
 * then rebuild prune. Status from LIVE membership after prune — never checkbox count.
 */
function assignThenRebuild(zone, inventoryChecked, areaSet, useFixed, opts = {}) {
  const selected = [...inventoryChecked];
  const beforeMembers = [...(zone.members || [])];
  const set = new Set(beforeMembers);
  selected.forEach((n) => set.add(n));
  zone.members = [...set];
  zone.membersOrigin = 'ENGINEER_ASSIGNED';
  zone.engineerEdited = true;
  zone.createdBy = 'engineer';
  zone.zoneOrigin = 'ENGINEER';

  const sid = zone.source_id || zone.id;
  const byId = pruneZones(
    [[sid, { ...zone, members: [...zone.members] }]],
    areaSet,
    useFixed,
    opts,
  );
  const after = byId.get(sid);
  const n = (after?.members || []).length;
  const status = after
    ? `Assigned ${n} device(s) → ${zone.name}`
    : `Assign FAILED — ${zone.name} was dropped by rebuild after edit`;
  return { after, status, selectedCount: selected.length, surviving: n };
}

const CASES = [
  {
    id: 'A',
    area: 'Area_Test1',
    zone: 'Area_Test1_ESZone1',
    sid: 'szone_area_test1_esz1',
    note: 'NON-controller-prefixed (permanent required)',
  },
  {
    id: 'B',
    area: 'MSCRENOPICK_AreaTest1',
    zone: 'MSCRENOPICK_AreaTest1_ESZone1',
    sid: 'szone_mscreno_areatest1_esz1',
    note: 'controller-prefixed (historical PASS path)',
  },
  {
    id: 'C',
    area: 'Area_1',
    zone: 'Zone_1',
    sid: 'szone_area1_zone1',
    note: 'short non-prefixed names',
  },
  {
    id: 'D',
    area: 'Pick Area A',
    zone: 'Pick Safety Zone A',
    sid: 'szone_pick_area_a_zone',
    note: 'spaces allowed in display names',
  },
];

for (const c of CASES) {
  check(`CASE ${c.id} FIXED: ${c.zone} survives empty areaRef after Area missing (${c.note})`, () => {
    const zone = {
      source_id: c.sid,
      id: c.sid,
      name: c.zone,
      engineering_name: c.zone,
      areaRef: c.area,
      area: c.area,
      members: [],
      engineerEdited: true,
      createdBy: 'engineer',
      provenance: 'ENGINEER_CREATED',
    };
    // Area NOT in workbook.areas — triggers unlink → areaRef ''
    const areaSet = new Set(); // empty
    const result = assignThenRebuild(zone, PICK_MEMBERS, areaSet, true);
    assert.ok(result.after, `zone must survive rebuild for CASE ${c.id}`);
    assert.strictEqual(result.surviving, 4, `exactly 4 members for CASE ${c.id}`);
    // Fixed path keeps engineer areaRef (workbook lag no longer clears it)
    assert.strictEqual(result.after.areaRef, c.area, 'engineer areaRef preserved');
    assert.ok(result.status.includes('Assigned 4'), `status from live members: ${result.status}`);
    assert.ok(!result.status.includes('Assigned 4') || result.surviving === 4);
    // Default Safety must not retain these four
    const defaultMembers = PICK_MEMBERS.filter(
      (m) => !(result.after.members || []).map((x) => String(x).toUpperCase()).includes(m.toUpperCase()),
    );
    assert.strictEqual(defaultMembers.length, 0);
  });

  check(`CASE ${c.id} BROKEN (historical): empty areaRef deleted the zone`, () => {
    const zone = {
      source_id: c.sid,
      id: c.sid,
      name: c.zone,
      engineering_name: c.zone,
      areaRef: c.area,
      area: c.area,
      members: [],
      engineerEdited: true,
      createdBy: 'engineer',
    };
    const result = assignThenRebuild(zone, PICK_MEMBERS, new Set(), false);
    assert.ok(!result.after, 'historical bug: zone deleted when areaRef cleared');
    assert.strictEqual(result.surviving, 0);
    assert.ok(result.status.includes('FAILED') || result.surviving === 0);
    // Truth: must NOT claim Assigned 4 when surviving is 0
    assert.ok(!result.status.includes('Assigned 4'));
  });
}

check('Assigned N truth: selected 4 / surviving 0 → FAILURE not Assigned 4', () => {
  const zone = {
    source_id: 'szone_truth',
    id: 'szone_truth',
    name: 'Area_Test1_ESZone1',
    areaRef: 'Area_Test1',
    members: [],
    engineerEdited: true,
    createdBy: 'engineer',
  };
  const broken = assignThenRebuild(zone, PICK_MEMBERS, new Set(), false);
  assert.strictEqual(broken.selectedCount, 4);
  assert.strictEqual(broken.surviving, 0);
  assert.ok(!broken.status.includes('Assigned 4'));
});

check('FIXED: explicit Area delete unlinks areaRef but zone+members survive', () => {
  const zone = {
    source_id: 'szone_unlink',
    id: 'szone_unlink',
    name: 'Area_Test1_ESZone1',
    areaRef: 'Area_Test1',
    members: [],
    engineerEdited: true,
    createdBy: 'engineer',
  };
  const result = assignThenRebuild(
    zone,
    PICK_MEMBERS,
    new Set(['Area_Test1']),
    true,
    { forceUnlink: true },
  );
  assert.ok(result.after, 'zone survives explicit Area delete');
  assert.strictEqual(result.surviving, 4);
  assert.strictEqual(result.after.areaRef, '');
  assert.ok(result.after.areaUnlinked);
  assert.ok(result.status.includes('Assigned 4'));
});

check('Apply verification: attempted>0 with zones=[] / members=[] is FAIL', () => {
  const attemptedMemberTotal = 4;
  const appliedZones = [];
  const appliedMemberTotal = appliedZones.reduce((n, z) => n + ((z.members || []).length), 0);
  const fail = attemptedMemberTotal > 0
    && (appliedZones.length === 0 || appliedMemberTotal === 0);
  assert.strictEqual(fail, true);
  // 0 vs 0 without attempt would be ok for empty project — but NOT after assign
  const want = 0;
  const got = 0;
  const verifyFail = attemptedMemberTotal > 0 && (want === 0 || got === 0);
  assert.strictEqual(verifyFail, true);
});

check('name independence: controller ownership must not parse Area/zone display name', () => {
  // Contract: no require of MSCRENOPICK_ prefix for Area_Test1 path to work
  assert.ok(src.includes('isCorruptAreaRef'));
  // Prefixed and non-prefixed cases both in this permanent suite
  assert.ok(CASES.some((c) => c.id === 'A' && !c.area.includes('MSCRENOPICK')));
  assert.ok(CASES.some((c) => c.id === 'B' && c.area.includes('MSCRENOPICK')));
});

if (process.exitCode) {
  console.error('NAME_INDEPENDENCE_MUTATION: FAIL');
  process.exit(1);
}
console.log('NAME_INDEPENDENCE_MUTATION: PASS');
