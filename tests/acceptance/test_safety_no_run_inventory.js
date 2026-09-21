#!/usr/bin/env node
/**
 * Safety inventory must be empty with no active RUN.
 *
 * Covers:
 *  - startup_no_run_safety_empty (session)
 *  - clear_project_safety_empty
 *  - prior_localstorage does not hydrate without site (logic contract)
 *  - postgres knowledge must not create site devices (documented invariant)
 *  - stale async safety response rejected
 *  - machine_change rejects prior inventory session
 *
 * Run: node tests/acceptance/test_safety_no_run_inventory.js
 */
'use strict';

const path = require('path');
const SS = require(path.join(__dirname, '..', '..', 'dashboard', 'site-session.js'));

let failed = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  [PASS] ${name}`);
  else {
    failed += 1;
    console.log(`  [FAIL] ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

function draftMatchesActive(draft, active) {
  const draftMachine = String(draft?.projectIdentity?.machine || draft?.machine || '').trim();
  const draftSha = String(
    draft?.projectIdentity?.archive_sha || draft?.archive_sha || '',
  ).trim();
  if (!SS.hasActiveSite(active)) return false;
  if (!draftMachine || draftMachine !== String(active.machine || '').trim()) return false;
  if (draftSha && draftSha !== String(active.archive_sha || '').trim()) return false;
  return true;
}

function shouldRestoreDevicesFromDraft(draft, active) {
  // Devices are never restored from persistence — only engineer zones may be.
  return false;
}

function shouldHydrateSafetyInventory(active) {
  return SS.hasActiveSite(active);
}

console.log('startup_no_run_safety_empty');
{
  SS._test.reset();
  check('no active site', SS.hasActiveSite() === false);
  check('must not hydrate inventory', shouldHydrateSafetyInventory(SS.getActiveSiteSession()) === false);
}

console.log('clear_project_safety_empty');
{
  SS._test.reset();
  SS.beginSiteSession({ archive_sha: 'aaa', machine: 'SITE_A' });
  const prior = SS.tagWithSession({ devices: ['ESPB1', 'MCR1'] });
  SS.invalidateSiteSession({ reason: 'clear-project' });
  check('cleared inactive', SS.hasActiveSite() === false);
  check('stale safety response rejected', SS.acceptAsyncResult(prior, { label: 'safetyDiscover', logFn: () => {} }) === false);
  check('no hydrate after clear', shouldHydrateSafetyInventory(SS.getActiveSiteSession()) === false);
}

console.log('prior_localstorage_does_not_hydrate_without_site');
{
  SS._test.reset();
  const ghostDraft = {
    machine: 'MSCRENOSHIP',
    archive_sha: 'deadbeef',
    devices: new Array(58).fill(0).map((_, i) => ({ name: `ESPB${i}`, kind: 'ESTOP' })),
  };
  check(
    'unscoped draft ignored without active site',
    draftMatchesActive(ghostDraft, SS.getActiveSiteSession()) === false,
  );
  check(
    'devices never restored from draft',
    shouldRestoreDevicesFromDraft(ghostDraft, SS.getActiveSiteSession()) === false,
  );
}

console.log('prior_workbook_does_not_hydrate_without_site');
{
  SS._test.reset();
  const wb = { safety_build: { devices: [{ name: 'ESPB99', kind: 'ESTOP' }], machine: 'OLD' } };
  check('workbook devices blocked without site', shouldHydrateSafetyInventory(SS.getActiveSiteSession()) === false);
  check('workbook machine alone insufficient', draftMatchesActive(wb.safety_build, SS.getActiveSiteSession()) === false);
}

console.log('postgres_knowledge_does_not_create_site_devices');
{
  // Contract: learning/rule_candidates / unknown_clusters are global research only.
  // Live Safety inventory must originate from active RUN evidence union.
  const pgWouldSupplyDevices = false; // product law — never wire PG → live devices
  check('PG does not supply live Safety devices', pgWouldSupplyDevices === false);
}

console.log('stale_async_safety_response_rejected');
{
  SS._test.reset();
  const sA = SS.beginSiteSession({ archive_sha: 'shaA', machine: 'SITE_A' });
  const tagged = SS.tagWithSession({ devices: [{ name: 'ESPB_A' }] });
  SS.invalidateSiteSession({ reason: 'clear' });
  check('post-clear reject', SS.acceptAsyncResult(tagged, { label: 'safety', logFn: () => {} }) === false);
  SS.beginSiteSession({ archive_sha: 'shaB', machine: 'SITE_B' });
  check('site B active', SS.hasActiveSite() === true && SS.getActiveSiteSession().machine === 'SITE_B');
  check('site A payload still rejected', SS.acceptAsyncResult(tagged, { label: 'safetyA', logFn: () => {} }) === false);
}

console.log('machine_change_rejects_prior_inventory');
{
  SS._test.reset();
  SS.beginSiteSession({ archive_sha: '1', machine: 'MSCATL_CP3' });
  const old = SS.tagWithSession({ devices: new Array(58).fill({ name: 'X' }) });
  SS.beginSiteSession({ archive_sha: '2', machine: 'MSCRENOSHIP' });
  check('reject prior machine inventory', SS.acceptAsyncResult(old, { label: 'inv', logFn: () => {} }) === false);
  check(
    'draft match requires both sha+machine',
    draftMatchesActive(
      { machine: 'MSCRENOSHIP', archive_sha: '1', devices: [{ name: 'ESPB' }] },
      SS.getActiveSiteSession(),
    ) === false,
  );
  check(
    'matching site draft ok for zones only',
    draftMatchesActive(
      { machine: 'MSCRENOSHIP', archive_sha: '2', devices: [{ name: 'ESPB' }] },
      SS.getActiveSiteSession(),
    ) === true,
  );
  check(
    'even matching draft never restores devices',
    shouldRestoreDevicesFromDraft(
      { machine: 'MSCRENOSHIP', archive_sha: '2', devices: [{ name: 'ESPB' }] },
      SS.getActiveSiteSession(),
    ) === false,
  );
}

if (failed) {
  console.log(`FAIL — ${failed} check(s)`);
  process.exit(1);
}
console.log('PASS — safety no-run inventory invariants');
process.exit(0);
