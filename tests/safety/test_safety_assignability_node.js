#!/usr/bin/env node
/**
 * UNIT/NODE — UI/backend assignability contract in dashboard/safety-build.js.
 *
 * Classification: UNIT / NODE
 * REAL_UI_E2E: REAL_UI_NOT_AUTOMATED (Electron lifecycle not executed here)
 *
 * Behavior-extracts isAssignablePhysicalSafetyDevice + normalizeCanonicalSafetyDevice
 * and asserts resolveZoneMemberEligibleNames rejects non-assignable members.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '../..');
const SAFETY_JS = path.join(ROOT, 'dashboard', 'safety-build.js');
const src = fs.readFileSync(SAFETY_JS, 'utf8');

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

function extractFn(name) {
  const re = new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n  \\}`);
  const m = src.match(re);
  if (!m) throw new Error(`missing function ${name}`);
  return m[0];
}

console.log('=== safety assignability (UNIT/NODE) ===');
console.log('REAL_UI_E2E: REAL_UI_NOT_AUTOMATED');

check('source honors assignable===false / DIRECTION', () => {
  const body = extractFn('isAssignablePhysicalSafetyDevice');
  assert.ok(body.includes('d.assignable === false'));
  assert.ok(body.includes("why.includes('DIRECTION')"));
});

check('normalizeCanonicalSafetyDevice preserves assignable', () => {
  const body = extractFn('normalizeCanonicalSafetyDevice');
  assert.ok(body.includes('assignable: g.assignable'));
});

check('resolveZoneMemberEligibleNames rejects non-assignable', () => {
  const body = extractFn('resolveZoneMemberEligibleNames');
  assert.ok(body.includes('isAssignablePhysicalSafetyDevice(d)'));
  assert.ok(body.includes('not assignable'));
  assert.ok(body.includes('rejected.push'));
});

const names = [
  'classifyDevName',
  'isMcrEnergizeCoil',
  'isMcrAuxFeedback',
  'deviceHasPhysicalClaim',
  'isAssignablePhysicalSafetyDevice',
  'normalizeCanonicalSafetyDevice',
];
const code = names.map(extractFn).join('\n');
const sandbox = {
  console,
  KIND_ORDER: ['ESTOP', 'ESLS', 'ESR', 'MCR', 'CS', 'OTHER'],
};
vm.createContext(sandbox);
vm.runInContext(
  `${code}\n${names.map((n) => `this.${n} = ${n};`).join('\n')}`,
  sandbox,
);

check('isAssignablePhysicalSafetyDevice rejects assignable===false', () => {
  const d = {
    name: '1ES',
    kind: 'ESTOP',
    assignable: false,
    review_reason: 'DIRECTION_MISMATCH',
    physicalEndpoint: 'T_1734_AENTR_CP2_52:I.Data[17].2',
  };
  assert.strictEqual(sandbox.isAssignablePhysicalSafetyDevice(d), false);
});

check('isAssignablePhysicalSafetyDevice rejects DIRECTION without assignable flag', () => {
  const d = {
    name: '1ES',
    kind: 'ESTOP',
    review_reason: 'DIRECTION_MISMATCH',
    physicalEndpoint: 'T_1734_AENTR_CP2_52:I.Data[17].2',
  };
  assert.strictEqual(sandbox.isAssignablePhysicalSafetyDevice(d), false);
});

check('normalizeCanonicalSafetyDevice preserves assignable=false', () => {
  const n = sandbox.normalizeCanonicalSafetyDevice({
    name: '1ES',
    kind: 'ESTOP',
    assignable: false,
    review_reason: 'DIRECTION_MISMATCH',
    physicalEndpoint: 'CP2:I.Data[1].0',
    hardwareBacked: false,
  });
  assert.ok(n);
  assert.strictEqual(n.assignable, false);
  assert.ok(String(n.review_reason || '').includes('DIRECTION'));
});

check('resolveZoneMemberEligibleNames rejects DIRECTION_MISMATCH member', () => {
  // Inline the eligibility gate against a stub device index (mirrors ORI-060 path).
  const devices = [
    {
      name: '1ES',
      kind: 'ESTOP',
      assignable: false,
      review_reason: 'DIRECTION_MISMATCH',
      physicalEndpoint: 'CP2:I.Data[1].0',
    },
    {
      name: '2ES',
      kind: 'ESTOP',
      assignable: true,
      review_reason: '',
      physicalEndpoint: 'CP2:I.Data[2].0',
      hardwareBacked: true,
    },
  ];
  const byUpper = new Map(devices.map((d) => [d.name.toUpperCase(), d]));
  const out = [];
  const rejected = [];
  for (const raw of ['1ES', '2ES']) {
    const member = String(raw);
    const d = byUpper.get(member.toUpperCase()) || { name: member };
    if (!sandbox.isAssignablePhysicalSafetyDevice(d)) {
      rejected.push(`${member} (not assignable — ${d.review_reason || 'REVIEW_REQUIRED'})`);
      continue;
    }
    out.push(member);
  }
  assert.deepStrictEqual(out, ['2ES']);
  assert.ok(rejected.some((r) => r.includes('1ES') && r.includes('not assignable')));
});

if (process.exitCode) {
  console.error('FAIL — safety assignability node');
  process.exit(1);
}
console.log('PASS — safety assignability node');
