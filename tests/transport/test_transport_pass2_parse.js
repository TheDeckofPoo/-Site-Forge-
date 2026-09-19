#!/usr/bin/env node
/**
 * Transport UX Pass 2 — parseChainText unit checks (Node-runnable).
 *
 * Mirrors the Python parity helper in test_transport_ux_pass2.py.
 * Split on commas / arrows / whitespace; keep ordered unique P###(+suffix) tags.
 */
'use strict';

function parseChainText(text) {
  const raw = String(text || '');
  const parts = raw
    .split(/[\s,;|→>\-–—]+/u)
    .map((p) => p.trim())
    .filter(Boolean);
  const out = [];
  const seen = new Set();
  for (const p of parts) {
    const m = p.match(/^(P\d+[A-Z]?)$/i);
    if (!m) continue;
    const tag = m[1].toUpperCase();
    if (seen.has(tag)) continue;
    seen.add(tag);
    out.push(tag);
  }
  return out;
}

const cases = [
  { input: 'P100, P102, P104', expect: ['P100', 'P102', 'P104'] },
  { input: 'P100→P102→P104', expect: ['P100', 'P102', 'P104'] },
  { input: 'P100 > P102 > P104', expect: ['P100', 'P102', 'P104'] },
  { input: 'P100 P102 P104', expect: ['P100', 'P102', 'P104'] },
  { input: 'p100;p102;p104', expect: ['P100', 'P102', 'P104'] },
  { input: 'P100,P100,P102', expect: ['P100', 'P102'] },
  { input: 'P136A → P138', expect: ['P136A', 'P138'] },
  { input: '', expect: [] },
  { input: 'no tags here', expect: [] },
];

let failed = 0;
for (const c of cases) {
  const got = parseChainText(c.input);
  const ok = JSON.stringify(got) === JSON.stringify(c.expect);
  const mark = ok ? 'PASS' : 'FAIL';
  console.log(`  [${mark}] parseChainText(${JSON.stringify(c.input)}) → ${JSON.stringify(got)}`);
  if (!ok) {
    console.log(`         expected ${JSON.stringify(c.expect)}`);
    failed += 1;
  }
}

if (typeof module !== 'undefined') {
  module.exports = { parseChainText };
}

if (failed) {
  console.error(`FAIL — ${failed} parseChainText case(s)`);
  process.exit(1);
}
console.log(`PASS — ${cases.length}/${cases.length} parseChainText checks`);
process.exit(0);
