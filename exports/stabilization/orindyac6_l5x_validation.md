# ORINDYAC6 L5X structural validation

- L5X: `exports\stabilization\ORINDYAC6_2026_09_18_1843_studiofix.L5X`
- ok: **False**
- routine language errors: 0
- decorated member errors: 1

## Decorated vs DataType
- `P504_SCN504` (Barcode_Scanner_UDT): DECORATED_MEMBER_ORDER_OR_NAME member `HMI`

## Supplied Studio diagnostic classes

- `merge_structure_init`: **FIXED_generator_full_decorated_template**
- `divert_member_order`: **MITIGATED_strip_L5K_keep_Decorated**
- `ShippingSorter_Area_member_order`: **MITIGATED_strip_L5K_keep_Decorated**
- `Wave_Divert_unexpected_Rung`: **FIXED_RLLContent_wrap**
- `Build_Config_unexpected_STLines`: **FIXED_STContent**

ok_for_supplied_studio_diagnostic_classes: **True**

Engineer must re-import into Studio 5000 to confirm Studio PASS.
