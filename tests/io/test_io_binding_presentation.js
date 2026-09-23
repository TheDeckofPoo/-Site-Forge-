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

check('MOTOR OUTPUT M124 → P124_Conv Conv_UDT O.Run (not MS.O.Run)', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M124',
    role: 'CONVEYOR_RUN',
    canonical_id: 'P124',
    logix_tag: 'P124_Conv',
    equipment_class: 'CONVEYOR',
    datatype: 'Conv_UDT',
    member_path: 'P124_Conv.O.Run',
    rule: 'motor_out_to_conv_run',
    confidence: 'PROVEN',
  });
  assert.ok(v);
  assert.strictEqual(v.raw, 'M124');
  assert.strictEqual(v.canonical, 'P124_Conv');
  assert.strictEqual(v.editValue, 'P124_Conv');
  assert.strictEqual(v.udt, 'Conv_UDT');
  assert.strictEqual(v.member, 'O.Run');
  assert.ok(v.line2.includes('Conv_UDT'));
  assert.ok(v.line2.includes('O.Run'));
  assert.ok(!v.line2.includes('Motor_Starter_UDT'));
  assert.ok(!v.editValue.includes('→'));
  assert.ok(!v.editValue.includes('M124'));
});

check('MOTOR AUX M124_AUX → P124_MS I.Auxiliary_Forward', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M124_AUX',
    role: 'AUXILIARY_FORWARD',
    canonical_id: 'P124',
    logix_tag: 'P124_MS',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P124_MS.I.Auxiliary_Forward',
    rule: 'motor_starter_aux_to_ms_udt',
    confidence: 'PROVEN',
  });
  assert.strictEqual(v.raw, 'M124_AUX');
  assert.strictEqual(v.canonical, 'P124_MS');
  assert.strictEqual(v.member, 'I.Auxiliary_Forward');
  assert.ok(v.line2.includes('Motor_Starter_UDT'));
  assert.ok(v.line2.includes('I.Auxiliary_Forward'));
});

check('LETTERED MOTOR AUX M128A_AUX → P128A_MS', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M128A_AUX',
    canonical_id: 'P128A',
    logix_tag: 'P128A_MS',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P128A_MS.I.Auxiliary_Forward',
    confidence: 'PROVEN',
    rule: 'motor_starter_aux_to_ms_udt',
  });
  assert.strictEqual(v.canonical, 'P128A_MS');
  assert.ok(v.line2.includes('I.Auxiliary_Forward'));
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
    logix_tag: 'P100_MS',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P100_MS.I.Auxiliary_Forward',
    confidence: 'REVIEW_REQUIRED',
    review_reason: 'AUX_WITHOUT_MATCHING_BASE',
    rule: 'motor_starter_aux_to_ms_udt',
  });
  assert.strictEqual(v.confidence, 'REVIEW_REQUIRED');
  assert.ok(String(v.confidenceLabel).includes('REVIEW'));
  assert.ok(!String(v.confidenceLabel).includes('PROVEN'));
});

check('detail lines include raw/canonical/udt/member/rule/confidence', () => {
  const v = formatIoEquipmentBindingView({
    raw_name: 'M124_AUX',
    logix_tag: 'P124_MS',
    equipment_class: 'MOTOR_STARTER',
    datatype: 'Motor_Starter_UDT',
    member_path: 'P124_MS.I.Auxiliary_Forward',
    driven_conveyor: 'P124',
    rule: 'motor_starter_aux_to_ms_udt',
    confidence: 'PROVEN',
  });
  const lines = equipmentBindingDetailLines(v, 'CP2RIO0:I.Data[3].7').join('\n');
  assert.ok(lines.includes('M124_AUX'));
  assert.ok(lines.includes('P124_MS'));
  assert.ok(lines.includes('Motor_Starter_UDT'));
  assert.ok(lines.includes('I.Auxiliary_Forward'));
  assert.ok(lines.includes('P124_MS.I.Auxiliary_Forward'));
  assert.ok(lines.includes('motor_starter_aux_to_ms_udt'));
  assert.ok(lines.includes('PROVEN'));
  assert.ok(lines.includes('CP2RIO0:I.Data[3].7'));
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
