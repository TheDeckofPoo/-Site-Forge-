#!/usr/bin/env node
/** Safety inventory filter must not destroy the search input (focus persistence). */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const src = fs.readFileSync(
  path.join(__dirname, '..', '..', 'dashboard', 'safety-build.js'),
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

console.log('=== safety filter focus ===');

check('in-place row filter without renderInventory on device-filter', () => {
  assert.ok(src.includes('Filter without destroying the search input'));
  assert.ok(src.includes("row.style.display = show ? '' : 'none'"));
  const idx = src.indexOf("sb-device-filter')?.addEventListener('input'");
  assert.ok(idx > 0);
  const block = src.slice(idx, idx + 900);
  assert.ok(!block.includes('renderInventory()'));
  assert.ok(block.includes('style.display'));
});

check('inv filter wires once (_sbFilterWired)', () => {
  assert.ok(src.includes('_sbFilterWired'));
});

check('physical partition for assignable inventory', () => {
  assert.ok(src.includes('isAssignablePhysicalSafetyDevice'));
  assert.ok(src.includes('nonphysical_aliases_suppressed'));
});

if (process.exitCode) {
  console.error('FAIL');
  process.exit(1);
}
console.log('PASS — safety filter focus');
