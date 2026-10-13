#!/usr/bin/env node
/**
 * Compile Hub Hardware detail must label denominators explicitly so
 * "0 unresolved" (Workbench) and "17 unresolved owners" (resolver tree)
 * cannot appear as the same metric without scope.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const REPO = path.join(__dirname, '..', '..');
const FP = fs.readFileSync(path.join(REPO, 'dashboard', 'fortna-plus.js'), 'utf8');

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== Compile Hub I/O denominator labels ===');

check('hardware readiness uses canonical unique_review when available', () => {
  assert.ok(FP.includes('Canonical review unresolved'));
  assert.ok(FP.includes('Autogen-mapped I/O'));
  assert.ok(FP.includes('Resolver tree:'));
  assert.ok(FP.includes('unresolved owner channel'));
  assert.ok(FP.includes('unique_review'));
});

check('AI/Relay gated on canonical unresolved = 0', () => {
  assert.ok(FP.includes('function syncIoEscalationActionButtons'));
  assert.ok(FP.includes('function canonicalUnresolvedReviewCount'));
  assert.ok(FP.includes('canonical_unresolved_zero') || FP.includes('canonical unresolved = 0'));
  const html = fs.readFileSync(path.join(REPO, 'dashboard', 'index.html'), 'utf8');
  assert.ok(html.includes('Analyze Remaining with AI'));
  assert.ok(html.includes('Escalate Remaining to Relay'));
  assert.ok(html.includes('btn-relay-escalate-remaining'));
});

if (process.exitCode) {
  console.error('FAILED');
  process.exit(1);
}
console.log('OK');
