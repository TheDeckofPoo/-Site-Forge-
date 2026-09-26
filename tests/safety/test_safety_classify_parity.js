#!/usr/bin/env node
/**
 * ORI-043: execute the ACTUAL dashboard classifyDevName against the corpus.
 * Usage: node tests/safety/test_safety_classify_parity.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '../..');
const CORPUS = path.join(__dirname, 'safety_classify_vectors.json');
const SAFETY_JS = path.join(ROOT, 'dashboard', 'safety-build.js');

const src = fs.readFileSync(SAFETY_JS, 'utf8');
const m = src.match(/function classifyDevName\(name\)\s*\{[\s\S]*?\n  \}/);
if (!m) {
  console.error('FAIL: classifyDevName not found in safety-build.js');
  process.exit(1);
}

const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext(`${m[0]}\nthis.classifyDevName = classifyDevName;`, sandbox);

const corpus = JSON.parse(fs.readFileSync(CORPUS, 'utf8'));
let failed = 0;
for (const row of corpus.vectors) {
  const got = sandbox.classifyDevName(row.name);
  const expect = row.expect || '';
  if (got !== expect) {
    console.error(`FAIL ${row.name}: got ${JSON.stringify(got)} want ${JSON.stringify(expect)}`);
    failed += 1;
  }
}
if (failed) {
  console.error(`${failed} failures`);
  process.exit(1);
}
console.log(`PASS ${corpus.vectors.length} vectors via actual JS classifyDevName`);
