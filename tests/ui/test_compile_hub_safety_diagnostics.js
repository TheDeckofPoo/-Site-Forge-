#!/usr/bin/env node
/**
 * P0 Canonical cross-tab truth — Compile Hub Safety diagnostics.
 *
 * Gold repro (Curtis MSCRENOPICK @ 7c08e71):
 *   Area_Test1 / Area_Test1_ESZone1 members ESPB2,ESPB24,ESPB32,ESLS2
 *   workbook.safety_build has eStops=[ESPB2,ESPB24,ESPB32] eslsDevices=[ESLS2]
 *   Compile Hub MUST report E-Stops: 3 RESOLVED · ESLS: 1 RESOLVED
 *   (not UNRESOLVED from broken ESPB* / ESLS* name reclassification)
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

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

function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} not found`);
  let i = src.indexOf('{', start);
  let depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) {
        return src.slice(start, i + 1);
      }
    }
  }
  throw new Error(`unclosed function ${name}`);
}

console.log('=== Compile Hub Safety diagnostics (canonical roles) ===');

const formatSrc = extractFunction(FP, 'formatSafetyZoneDiagnostics');
const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext(formatSrc, sandbox);
const formatSafetyZoneDiagnostics = sandbox.formatSafetyZoneDiagnostics;

const GOLD_ZONE = {
  name: 'Area_Test1_ESZone1',
  engineering_name: 'Area_Test1_ESZone1',
  area: 'Area_Test1',
  areaRef: 'Area_Test1',
  members: ['ESPB2', 'ESPB24', 'ESPB32', 'ESLS2'],
  eStops: ['ESPB2', 'ESPB24', 'ESPB32'],
  eslsDevices: ['ESLS2'],
  esrDevices: [],
  mcrDevices: [],
  conveyors: [],
  safety_device_membership: 'RESOLVED',
};

check('workbook role arrays → E-Stops 3 · ESLS 1 (gold Curtis case)', () => {
  const lines = formatSafetyZoneDiagnostics([GOLD_ZONE]);
  assert.strictEqual(lines.length, 1);
  const text = lines[0];
  assert.ok(text.includes('Area: Area_Test1 · READY'), text);
  assert.ok(text.includes('E-Stops: 3 RESOLVED'), `missing E-Stops 3:\n${text}`);
  assert.ok(text.includes('ESLS: 1 RESOLVED'), `missing ESLS 1:\n${text}`);
  assert.ok(text.includes('ESR: UNRESOLVED · REVIEW'), text);
  assert.ok(text.includes('MCR: UNRESOLVED · REVIEW'), text);
  assert.ok(!/E-Stops: UNRESOLVED/.test(text), text);
  assert.ok(!/ESLS: UNRESOLVED/.test(text), text);
});

check('members-only fallback still classifies ESPB* as ESTOP and ESLS*', () => {
  const z = {
    name: 'Z',
    area: 'A',
    members: ['ESPB2', 'ESPB24', 'ESPB32', 'ESLS2'],
  };
  const text = formatSafetyZoneDiagnostics([z])[0];
  assert.ok(text.includes('E-Stops: 3 RESOLVED'), text);
  assert.ok(text.includes('ESLS: 1 RESOLVED'), text);
});

check('empty roles remain UNRESOLVED (no invent ESR/MCR)', () => {
  const z = {
    name: 'EmptyZone',
    area: 'A',
    members: [],
    eStops: [],
    eslsDevices: [],
  };
  const text = formatSafetyZoneDiagnostics([z])[0];
  assert.ok(text.includes('E-Stops: UNRESOLVED · REVIEW'), text);
  assert.ok(text.includes('ESLS: UNRESOLVED · REVIEW'), text);
  assert.ok(text.includes('ESR: UNRESOLVED · REVIEW'), text);
  assert.ok(text.includes('MCR: UNRESOLVED · REVIEW'), text);
});

check('safetyEvidence prefers workbook zones over lastEsReport (source contract)', () => {
  const body = extractFunction(FP, 'safetyEvidence');
  assert.ok(body.includes('workbookDiagSource') || body.includes('toDiagZone'), body.slice(0, 200));
  assert.ok(body.includes('eStops'), 'must carry eStops into diag zones');
  assert.ok(body.includes('eslsDevices'), 'must carry eslsDevices into diag zones');
  // Must NOT prefer lastZonesRaw when workbook has members
  assert.ok(
    /workbookDiagSource\.length\s*\n?\s*\?/.test(body) || body.includes('workbookDiagSource.length'),
    'workbook must win over lastEsReport',
  );
});

check('gold repro snapshot fixture present', () => {
  const diag = path.join(REPO, 'exports', 'diagnostics');
  const dirs = fs.existsSync(diag)
    ? fs.readdirSync(diag).filter((d) => d.startsWith('gold_repro_7c08e71'))
    : [];
  assert.ok(dirs.length >= 1, 'gold_repro_7c08e71_* snapshot missing');
  const g = path.join(diag, dirs.sort().slice(-1)[0], 'workspace', 'autogen_workbook.json');
  assert.ok(fs.existsSync(g), `workbook missing: ${g}`);
  const wb = JSON.parse(fs.readFileSync(g, 'utf8'));
  const z = (wb.safety_build?.zones || [])[0];
  assert.ok(z, 'gold zone missing');
  assert.deepStrictEqual(z.eStops, ['ESPB2', 'ESPB24', 'ESPB32']);
  assert.deepStrictEqual(z.eslsDevices, ['ESLS2']);
  const text = formatSafetyZoneDiagnostics([{
    ...z,
    name: z.engineering_name || z.name,
    area: z.area || z.areaRef,
  }])[0];
  assert.ok(text.includes('E-Stops: 3 RESOLVED'), text);
  assert.ok(text.includes('ESLS: 1 RESOLVED'), text);
});

if (process.exitCode) {
  console.error('FAILED');
  process.exit(1);
}
console.log('OK');
