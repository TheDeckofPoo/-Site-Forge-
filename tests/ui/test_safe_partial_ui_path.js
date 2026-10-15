#!/usr/bin/env node
/**
 * Part E — Safe Partial UI workflow regression (Patch-style gate).
 *
 * Asserts durable Safe Partial control exists and Normal Export Safety gate
 * offers a three-way choice helper (not Cancel→OK hidden flow only).
 *
 * Does not weaken ORI-110: full/normal still blocks without ack.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const htmlPath = path.join(root, 'dashboard', 'index.html');
const jsPath = path.join(root, 'dashboard', 'fortna-plus.js');

function assert(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    process.exitCode = 1;
    throw new Error(msg);
  }
  console.log('OK:', msg);
}

const html = fs.readFileSync(htmlPath, 'utf8');
const js = fs.readFileSync(jsPath, 'utf8');

assert(html.includes('id="btn-autogen-safe-partial"'), 'Safe Partial button present in index.html');
assert(/Safe Partial L5X/.test(html), 'Safe Partial L5X label visible');
assert(/SAFETY NOT GENERATED — ES SHELL ONLY/.test(html), 'Shell-only acknowledgement text near Export');

assert(/function sfChooseSafetyBuildPath/.test(js), 'three-way Safety chooser function exists');
assert(/data-choice="safe_partial"/.test(js), 'chooser offers Continue Safe Partial');
assert(/data-choice="open_safety"/.test(js), 'chooser offers Open Safety Build');
assert(/data-choice="cancel"/.test(js), 'chooser offers Cancel');

assert(
  /runAutogenGenerate\('run',\s*\{\s*safePartial:\s*true\s*\}\)/.test(js),
  'Safe Partial button wires runAutogenGenerate(..., { safePartial: true })',
);
assert(
  /wantSafePartial/.test(js) && /acknowledgeSafetyShellOnly\s*=\s*true/.test(js),
  'Safe Partial path sets acknowledgeSafetyShellOnly',
);

// Full/normal path must still hard-stop without ack (preflight contract).
assert(
  /SAFETY_CONFIGURATION_REQUIRED/.test(js),
  'Normal path still uses SAFETY_CONFIGURATION_REQUIRED blocker',
);
assert(
  /allowOmitUnresolvedSafety/.test(js),
  'omit/ack still gated through allowOmitUnresolvedSafety',
);

// Hidden Cancel→OK-only flow must not be the sole path anymore.
assert(
  !/OK = Open Safety Build\n`\s*\+\s*`Cancel = stay here/.test(js),
  'old Cancel-to-reach-Safe-Partial first-dialog wording removed',
);

if (process.exitCode) {
  console.error('Safe Partial UI regression FAILED');
  process.exit(1);
}
console.log('Safe Partial UI regression PASSED');
