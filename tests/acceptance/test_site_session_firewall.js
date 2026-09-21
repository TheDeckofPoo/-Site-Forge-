#!/usr/bin/env node
/**
 * Current-site session firewall — unit hooks.
 *
 * Covers:
 *  - stale async rejection (session mismatch / missing tag)
 *  - Clear boundary bumps loadEpoch and drops identity
 *  - Autogen card dedupe by build_id / sha256 / path
 *  - I/O pipeline: loading phases never emit DISCOVERY FAILED text
 *  - Engineer area names like Area_1lksadfj are preserved
 *
 * Run: node tests/acceptance/test_site_session_firewall.js
 */
'use strict';

const path = require('path');
const SS = require(path.join(__dirname, '..', '..', 'dashboard', 'site-session.js'));

let failed = 0;

function check(name, cond, detail) {
  if (cond) {
    console.log(`  [PASS] ${name}`);
  } else {
    failed += 1;
    console.log(`  [FAIL] ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

SS._test.reset();

// --- stale async rejection ---
console.log('stale async rejection');
{
  const s1 = SS.beginSiteSession({ archive_sha: 'aaa', machine: 'MSCATL', reason: 't1' });
  check('begin bumps epoch', s1.loadEpoch === 1, `epoch=${s1.loadEpoch}`);
  const tagged = SS.tagWithSession({ gaps: [1] });
  check('tag carries session', SS.sessionEquals(tagged.session, s1));
  check('accept matching', SS.acceptAsyncResult(tagged, { label: 't', logFn: () => {} }));

  SS.beginSiteSession({ archive_sha: 'bbb', machine: 'MSCRENOSHIP', reason: 't2' });
  check(
    'reject prior session after machine change',
    SS.acceptAsyncResult(tagged, { label: 'stale', logFn: () => {} }) === false,
  );
  check(
    'reject missing session tag',
    SS.acceptAsyncResult({ gaps: [] }, { label: 'missing', logFn: () => {} }) === false,
  );
}

// --- Clear boundary ---
console.log('Clear boundary');
{
  SS._test.reset();
  SS.beginSiteSession({ archive_sha: 'fff', machine: 'MSCRENOSHIP', reason: 'load' });
  SS.markAutogenCardPresented({ l5x_sha256: 'deadbeef', l5x: 'X.L5X' });
  check('card tracked pre-clear', SS._test.getPresentedKeys().length === 1);

  const before = SS.getActiveSiteSession();
  const cleared = SS.invalidateSiteSession({ reason: 'clear-project' });
  check('clear bumps epoch', cleared.loadEpoch === before.loadEpoch + 1);
  check('clear drops machine', cleared.machine === '');
  check('clear drops archive_sha', cleared.archive_sha === '');
  check('clear resets card dedupe', SS._test.getPresentedKeys().length === 0);
  check('clear sets pipeline IDLE', SS.getIoPipelinePhase() === SS.IO_PIPELINE.IDLE);

  const stale = { session: before };
  check(
    'post-clear rejects pre-clear async',
    SS.acceptAsyncResult(stale, { label: 'post-clear', logFn: () => {} }) === false,
  );
}

// --- Autogen card dedupe ---
console.log('Autogen card dedupe');
{
  SS._test.reset();
  SS.beginSiteSession({ archive_sha: 'c1', machine: 'MSCRENOSHIP' });
  const r1 = { build_id: 'b1', l5x_sha256: 'sha1', l5x: 'a.L5X', controller_name: 'MSCRENOSHIP' };
  const r1b = { build_id: 'b1', l5x_sha256: 'sha1', l5x: 'a.L5X', controller_name: 'MSCRENOSHIP' };
  const r2 = { l5x_sha256: 'sha2', l5x: 'b.L5X', controller_name: 'MSCRENOSHIP' };
  check('first present ok', SS.shouldPresentAutogenCard(r1) === true);
  SS.markAutogenCardPresented(r1);
  check('duplicate build_id rejected', SS.shouldPresentAutogenCard(r1b) === false);
  check('different sha accepted', SS.shouldPresentAutogenCard(r2) === true);

  SS.beginSiteSession({ archive_sha: 'c2', machine: 'MSCATL' });
  check('new machine load clears dedupe', SS.shouldPresentAutogenCard(r1) === true);
}

// --- I/O pipeline banner ---
console.log('I/O pipeline loading ≠ failure');
{
  SS._test.reset();
  SS.setIoPipelinePhase(SS.IO_PIPELINE.LOADING_ARCHIVE);
  const loadingText = SS.ioPipelineBannerText(SS.IO_PIPELINE.LOADING_ARCHIVE);
  check('loading banner has no FAILED', !/FAILED/i.test(loadingText), loadingText);
  check('isIoPipelineLoading true', SS.isIoPipelineLoading());

  SS.setIoPipelinePhase(SS.IO_PIPELINE.BUILDING_MODEL);
  check(
    'building banner progress',
    /Building/i.test(SS.ioPipelineBannerText()),
  );

  const failedPhase = SS.resolveIoPipelineFromModel({
    success: true,
    claim_discovery_status: 'FAILED',
  });
  check('model FAILED → phase FAILED', failedPhase === SS.IO_PIPELINE.FAILED);
  const failText = SS.ioPipelineBannerText(SS.IO_PIPELINE.FAILED);
  check('FAILED banner mentions DISCOVERY FAILED', /DISCOVERY FAILED/i.test(failText));

  check(
    'READY model',
    SS.resolveIoPipelineFromModel({ success: true, claim_discovery_status: 'OK' })
      === SS.IO_PIPELINE.READY,
  );
}

// --- bind identity without bump ---
console.log('bind identity mid-load');
{
  SS._test.reset();
  const s0 = SS.beginSiteSession({ archive_sha: '', machine: '', reason: 'load-start' });
  const s1 = SS.bindSiteSessionIdentity({
    archive_sha: '9b57e100',
    machine: 'MSCRENOSHIP',
  });
  check('bind keeps epoch', s1.loadEpoch === s0.loadEpoch);
  check('bind sets machine', s1.machine === 'MSCRENOSHIP');
  check('bind sets archive_sha', s1.archive_sha === '9b57e100');
  const tagged = { session: s0 };
  // sessionEquals compares full identity — after bind, old empty identity mismatches.
  // Callers must capture session AFTER bind, or compare by epoch only for mid-load.
  // Documented contract: capture at async start; bind fills identity for new work.
  check(
    'pre-bind capture mismatches post-bind identity',
    SS.acceptAsyncResult(tagged, { label: 'pre-bind', logFn: () => {} }) === false,
  );
  const tagged2 = SS.tagWithSession({});
  check('post-bind tag accepts', SS.acceptAsyncResult(tagged2, { label: 'post-bind', logFn: () => {} }));
}

// --- Area_1lksadfj preservation ---
console.log('engineer area persistence');
{
  check(
    'Area_1lksadfj preserved',
    SS.shouldPreserveEngineerAreaName('Area_1lksadfj') === true,
  );
  check(
    'empty area rejected',
    SS.shouldPreserveEngineerAreaName('   ') === false,
  );
}

if (failed) {
  console.error(`FAIL — ${failed} site-session check(s)`);
  process.exit(1);
}
console.log('PASS — site-session firewall hooks');
process.exit(0);
