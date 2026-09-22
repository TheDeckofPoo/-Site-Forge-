#!/usr/bin/env node
/**
 * I/O Map binding presentation — uses shared binder fields only (no GUI M→P).
 */
'use strict';

const path = require('path');
const assert = require('assert');
const mod = require(path.join(
  __dirname,
  '..',
  '..',
  'dashboard',
  'hw-io-binding-presentation.js'
));

const { formatIoEquipmentBindingView, equipmentBindingDetailLines } = mod;

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('=== I/O binding presentation ===');

check('MOTOR OUTPUT M59 → P59 Motor_Starter_UDT O.Run', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M59',
    role: 'RUN_COMMAND',
    canonical_id: 'P59',
    logix_tag: 'P59',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P59.O.Run',
    driven_conveyor: 'MP86',
    rule: 'motor_starter_m_to_p_canonicalization',
    confidence: 'PROVEN',
  });
  assert.ok(v);
  assert.strictEqual(v.raw, 'M59');
  assert.strictEqual(v.canonical, 'P59');
  assert.strictEqual(v.editValue, 'P59');
  assert.strictEqual(v.udt, 'Motor_Starter_UDT');
  assert.strictEqual(v.member, 'O.Run');
  assert.ok(v.line1Raw.includes('M59'));
  assert.ok(v.line1Canon.includes('P59'));
  assert.ok(v.line2.includes('Motor_Starter_UDT'));
  assert.ok(v.line2.includes('O.Run'));
  assert.strictEqual(v.confidence, 'PROVEN');
  // Must not invent arrow string as edit value
  assert.ok(!v.editValue.includes('→'));
  assert.ok(!v.editValue.includes('M59'));
});

check('MOTOR AUX M59_AUX → P59 I.Auxiliary_Forward', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M59_AUX',
    role: 'AUXILIARY_FORWARD',
    canonical_id: 'P59',
    logix_tag: 'P59',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P59.I.Auxiliary_Forward',
    driven_conveyor: 'MP86',
    rule: 'motor_starter_m_to_p_canonicalization',
    confidence: 'PROVEN',
  });
  assert.strictEqual(v.raw, 'M59_AUX');
  assert.strictEqual(v.canonical, 'P59');
  assert.strictEqual(v.member, 'I.Auxiliary_Forward');
  assert.ok(v.line2.includes('Motor_Starter_UDT'));
  assert.ok(v.line2.includes('I.Auxiliary_Forward'));
});

check('LETTERED MOTOR M128A → P128A', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M128A',
    canonical_id: 'P128A',
    logix_tag: 'P128A',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P128A.O.Run',
    confidence: 'PROVEN',
    rule: 'motor_starter_m_to_p_canonicalization',
  });
  assert.strictEqual(v.canonical, 'P128A');
  assert.ok(v.line2.includes('O.Run'));
});

check('POWER SUPPLY EZPWS10 → PS_UDT I.PS_OK', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'EZPWS10',
    canonical_id: 'EZPWS10',
    logix_tag: 'EZPWS10',
    equipment_class: 'POWER_SUPPLY',
    datatype: 'PS_UDT',
    member_path: 'EZPWS10.I.PS_OK',
    role: 'PS_OK',
    rule: 'power_supply_pws_to_ps_udt',
    confidence: 'PROVEN',
  });
  assert.strictEqual(v.raw, 'EZPWS10');
  assert.strictEqual(v.canonical, 'EZPWS10');
  assert.strictEqual(v.udt, 'PS_UDT');
  assert.strictEqual(v.member, 'I.PS_OK');
  assert.ok(v.line2.includes('PS_UDT'));
  assert.ok(v.line2.includes('I.PS_OK'));
});

check('AMBIGUOUS PS999 REVIEW — must NOT show PS_UDT', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'PS999',
    canonical_id: 'PS999',
    logix_tag: '',
    equipment_class: 'UNKNOWN_PS_PREFIX',
    datatype: '',
    member_path: '',
    confidence: 'REVIEW_REQUIRED',
    review_reason: 'PS_PREFIX_AMBIGUOUS_NO_AIR_OR_POWER_EVIDENCE',
  });
  assert.strictEqual(v.mode, 'review_only');
  assert.strictEqual(v.showUdt, false);
  assert.strictEqual(v.udt, '');
  assert.ok(!String(v.line2 || '').includes('PS_UDT'));
  assert.ok(String(v.confidenceLabel).includes('REVIEW'));
  assert.ok(v.reviewReason.includes('PS_PREFIX_AMBIGUOUS'));
});

check('REVIEW motor remains REVIEW not PROVEN', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M100_AUX',
    canonical_id: 'P100',
    logix_tag: 'P100',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P100.I.Auxiliary_Forward',
    confidence: 'REVIEW_REQUIRED',
    review_reason: 'AUX_WITHOUT_MATCHING_BASE',
    rule: 'motor_starter_m_to_p_canonicalization',
  });
  assert.strictEqual(v.confidence, 'REVIEW_REQUIRED');
  assert.ok(String(v.confidenceLabel).includes('REVIEW'));
  assert.ok(!String(v.confidenceLabel).includes('PROVEN'));
});

check('detail lines include raw/canonical/udt/member/rule/confidence', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M59',
    logix_tag: 'P59',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P59.O.Run',
    driven_conveyor: 'MP86',
    rule: 'motor_starter_m_to_p_canonicalization',
    confidence: 'PROVEN',
  });
  const lines = equipmentBindingDetailLines(v, 'AENTR1:O.Data[5].1').join('\n');
  assert.ok(lines.includes('M59'));
  assert.ok(lines.includes('P59'));
  assert.ok(lines.includes('Motor_Starter_UDT'));
  assert.ok(lines.includes('O.Run'));
  assert.ok(lines.includes('P59.O.Run'));
  assert.ok(lines.includes('MP86'));
  assert.ok(lines.includes('motor_starter_m_to_p_canonicalization'));
  assert.ok(lines.includes('PROVEN'));
  assert.ok(lines.includes('AENTR1:O.Data[5].1'));
});

check('null bind → null view (no GUI invention)', () => {
  assert.strictEqual(formatIoEquipmentBindingView(null), null);
  assert.strictEqual(formatIoEquipmentBindingView(undefined), null);
});

if (process.exitCode) {
  console.error('FAIL — binding presentation checks');
  process.exit(1);
}
console.log('PASS — binding presentation checks');
