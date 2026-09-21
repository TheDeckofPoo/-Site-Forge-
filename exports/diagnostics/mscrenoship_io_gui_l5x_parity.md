# MSCRENOSHIP I/O GUI vs L5X parity

Generated: `2026-09-21T06:00:37Z`  
**Machine:** `MSCRENOSHIP`  
**RUN:** `C:\dev\worktree\FortnaPlus\workspace\_reno_peek\20260813-1132-MSCRENO-MSCRENOSHIP-RUN\RUN`  
**Field-validation L5X:** `exports\diagnostics\mscrenoship_io_conservation_regen\MSCRENOSHIP.L5X`

## Method

- GUI authority: `build_hardware_io_model` per-channel `physical_address`, `owner_state`, occupancy, logical names
- GUI claimed = `owner_state == ASSIGNED` (UI occupancy **CLAIMED**)
- L5X: parse IO_MAP `CP_I` / `CP_O` for `T_…:I.Data` / `:O.Data` patterns (here `AENTR_n:I|O.Data[s].b`)
- Compare **identity sets** of physical addresses (not counts alone)
- Flag modules where `gui_claimed_n != l5x_mapped_n`
- Audit L5X `mapping_count>1` duplicates with explicit classification

## Summary

| Metric | Count |
| --- | ---: |
| GUI ASSIGNED / CLAIMED physical | 250 |
| GUI UNRESOLVED_OWNER physical | 7 |
| GUI physical channels | 348 |
| L5X named rungs | 258 |
| L5X unique named physical | 254 |
| Identity both (claimed ∩ L5X) | 250 |
| Claimed only (GUI − L5X) | 0 |
| Mapped only (L5X − GUI claimed) | 4 |
| UNRESOLVED also present in L5X | 4 |
| L5X duplicate physical addresses | 4 |
| Modules with count mismatch | 3 / 62 |
| Modules with set mismatch | 3 / 62 |

### Duplicate classifications

| Class | Count |
| --- | ---: |
| `PROVEN_ALIAS` | 0 |
| `PROVEN_SHARED_SEMANTIC` | 4 |
| `OWNER_CONFLICT` | 0 |
| `DUPLICATE_CLAIM` | 0 |
| `DECODER_ERROR` | 0 |
| `REVIEW_REQUIRED` | 0 |

## Focus examples (Curtis/Gilfoyle)

### `AENTR_1` slot 6 (1734-IA4)

Note: GUI ~3/4 vs gen 4?

| Field | Value |
| --- | --- |
| capacity | 4 |
| GUI claimed_n (ASSIGNED) | 3 |
| GUI unresolved_n | 1 |
| L5X unique mapped_n | 3 |
| L5X named rung count | 3 |
| count_mismatch | False |

**Hypothesis:** IA4 high-half banks join the correct adjacent module, so capacity is 4. GUI claimed_n=3 because one channel is OWNER_CONFLICT (two Conveyor names on the same Bank.word.bit). L5X unique mapped_n=4 because it still emits a named rung on the conflicted bit (often mapping_count=2).

| bit | physical | owner_state | occupancy | logical |
| ---: | --- | --- | --- | --- |
| 0 | `AENTR_1:I.Data[6].0` | `ASSIGNED` | CLAIMED | `M45_AUX` |
| 1 | `AENTR_1:I.Data[6].1` | `ASSIGNED` | CLAIMED | `M46_AUX` |
| 2 | `AENTR_1:I.Data[6].2` | `UNRESOLVED_OWNER` | UNRESOLVED OWNER | `M48A_AUX` |
| 3 | `AENTR_1:I.Data[6].3` | `ASSIGNED` | CLAIMED | `M49_AUX` |

### `AENTR_1` slot 7 (1734-IA4)

Note: GUI ~3/4 vs gen 4?

| Field | Value |
| --- | --- |
| capacity | 4 |
| GUI claimed_n (ASSIGNED) | 3 |
| GUI unresolved_n | 1 |
| L5X unique mapped_n | 3 |
| L5X named rung count | 3 |
| count_mismatch | False |

**Hypothesis:** IA4 high-half banks join the correct adjacent module, so capacity is 4. GUI claimed_n=3 because one channel is OWNER_CONFLICT (two Conveyor names on the same Bank.word.bit). L5X unique mapped_n=4 because it still emits a named rung on the conflicted bit (often mapping_count=2).

| bit | physical | owner_state | occupancy | logical |
| ---: | --- | --- | --- | --- |
| 0 | `AENTR_1:I.Data[7].0` | `ASSIGNED` | CLAIMED | `M50_AUX` |
| 1 | `AENTR_1:I.Data[7].1` | `UNRESOLVED_OWNER` | UNRESOLVED OWNER | `M51_AUX` |
| 2 | `AENTR_1:I.Data[7].2` | `ASSIGNED` | CLAIMED | `M54_AUX` |
| 3 | `AENTR_1:I.Data[7].3` | `ASSIGNED` | CLAIMED | `M55_AUX` |

### `AENTR_2` slot 5 (1734-IB8)

Note: GUI 1/8 vs many?

| Field | Value |
| --- | --- |
| capacity | 8 |
| GUI claimed_n (ASSIGNED) | 8 |
| GUI unresolved_n | 0 |
| L5X unique mapped_n | 8 |
| L5X named rung count | 8 |
| count_mismatch | False |

**Hypothesis:** Word 1111 Low bank 76 joins AENTR_2 slot5 IB8, but High bank 4 is the adapter OutputAddress / OB8E output_bank — not an input module. High-half Conveyor bits (octal 11-17 → SSVD3..SSVD9) therefore fan onto Data[5].1-.7 and collide with Low claims; GUI keeps 1 ASSIGNED + 7 UNRESOLVED_OWNER while L5X emits both owners per channel.

| bit | physical | owner_state | occupancy | logical |
| ---: | --- | --- | --- | --- |
| 0 | `AENTR_2:I.Data[5].0` | `ASSIGNED` | CLAIMED | `MPA2_AUX` |
| 1 | `AENTR_2:I.Data[5].1` | `ASSIGNED` | CLAIMED | `EZPWS-PA2` |
| 2 | `AENTR_2:I.Data[5].2` | `ASSIGNED` | CLAIMED | `EZPE-PA2_F` |
| 3 | `AENTR_2:I.Data[5].3` | `ASSIGNED` | CLAIMED | `MPA3_AUX` |
| 4 | `AENTR_2:I.Data[5].4` | `ASSIGNED` | CLAIMED | `EZPWS-PA3` |
| 5 | `AENTR_2:I.Data[5].5` | `ASSIGNED` | CLAIMED | `EZPE-PA3_F` |
| 6 | `AENTR_2:I.Data[5].6` | `ASSIGNED` | CLAIMED | `VFDS1_FLT` |
| 7 | `AENTR_2:I.Data[5].7` | `ASSIGNED` | CLAIMED | `VFDS1D17_FLT` |

### `AENTR_3` slot 10 (1734-OB8E)

Note: GUI ~6/8 vs +1?

| Field | Value |
| --- | --- |
| capacity | 8 |
| GUI claimed_n (ASSIGNED) | 6 |
| GUI unresolved_n | 1 |
| L5X unique mapped_n | 7 |
| L5X named rung count | 8 |
| count_mismatch | True |

**Hypothesis:** High half of word 1124 correctly lands on OB8E slot10. GUI claimed_n=6 with one UNRESOLVED_OWNER on Data[10].5 where MSORTTR1 and VFDSSVSOL1 share Bank1124.15 (REVIEW_SHARED_OUTPUT). L5X unique mapped_n=7 (+1 vs GUI ASSIGNED) because the conflicted bit is still named.

Duplicate physical on module:

- `AENTR_3:O.Data[10].5` ×2 → **PROVEN_SHARED_SEMANTIC** · targets `['MSORTTR1', 'VFDSSVSOL1']`

| bit | physical | owner_state | occupancy | logical |
| ---: | --- | --- | --- | --- |
| 0 | `AENTR_3:O.Data[10].0` | `ASSIGNED` | CLAIMED | `M13P1A` |
| 1 | `AENTR_3:O.Data[10].1` | `ASSIGNED` | CLAIMED | `M13P2` |
| 2 | `AENTR_3:O.Data[10].2` | `ASSIGNED` | CLAIMED | `M13P3` |
| 3 | `AENTR_3:O.Data[10].3` | `ASSIGNED` | CLAIMED | `VFD13RB` |
| 4 | `AENTR_3:O.Data[10].4` | `ASSIGNED` | CLAIMED | `SSV-SOL1` |
| 5 | `AENTR_3:O.Data[10].5` | `UNRESOLVED_OWNER` | UNRESOLVED OWNER | `MSORTTR1` |
| 6 | `AENTR_3:O.Data[10].6` | `ASSIGNED` | CLAIMED | `SSVP13-P2` |
| 7 | `AENTR_3:O.Data[10].7` | `UNUSED_MAPPED` | UNCLAIMED | `` |

## Root-cause hypotheses

### `owner_conflict_emitted_in_l5x`

HardwareIOModel marks OWNER_CONFLICT channels as UNRESOLVED_OWNER (not ASSIGNED/CLAIMED), while IO_MAP still emits every RUN-proven logical target on that physical address. Module claimed_n therefore undercounts vs L5X unique mapped_n by the conflicted bits.

**Evidence modules:** `AENTR_1:6`, `AENTR_1:7`, `AENTR_3:10`

**Recommended gate:** Parity gate should compare (ASSIGNED ∪ UNRESOLVED_OWNER) occupancy OR require IO_MAP to suppress/REVIEW conflicted inputs the same way GUI refuses CLAIMED. Do not treat claimed_n alone as conservation.

### `high_half_bank_join_collapse_word_1111`

MSCRENOSHIP Configio word 1111 High bank=4 does not match any 1734 input module (bank 4 is AENTR_2 OutputAddress / OB8E output_bank). PWR falls back to the Low IB8 and fans high-half octal bits onto Data[5].0-7, creating systematic Low+High duplicate physical addresses.

**Evidence modules:** `AENTR_2:5`

**Recommended gate:** Decoder gate: when High bank lookup fails for expected_direction, do NOT silently inherit Low module — emit unresolved half / REVIEW_REQUIRED instead of colliding module_bits. Also validate Configio High banks against synthesized POINT input banks before emit.

**Production fix:** Not applied in this diagnostic pass — needs generalized half-join failure handling plus Configio bank sanity check; small safe fix is not obvious without broader POINT empty-Desc corpus coverage.

### `review_shared_output_vs_gui_conflict`

Shared physical OUTPUTs with all RUN-proven owners are annotated REVIEW_SHARED_OUTPUT and kept in L5X, while GUI occupancy stays UNRESOLVED_OWNER. This is intentional compiler policy, not lost claims.

**Evidence modules:** `AENTR_3:10`

**Recommended gate:** Classify PROVEN_SHARED_SEMANTIC separately from DECODER_ERROR in parity dashboards; do not fail conservation solely on ASSIGNED count.

## Modules with claimed_n ≠ mapped_n

| Adapter | Slot | Type | GUI claimed | GUI unresolved | L5X mapped | Δ |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| `AENTR_4` | 9 | `1734-OB8E` | 5 | 2 | 7 | +2 |
| `AENTR_3` | 15 | `1734-OA4` | 3 | 1 | 4 | +1 |
| `AENTR_3` | 10 | `1734-OB8E` | 6 | 1 | 7 | +1 |

## Duplicate physical addresses (L5X)

| Physical | n | Class | Targets |
| --- | ---: | --- | --- |
| `AENTR_3:O.Data[10].5` | 2 | **PROVEN_SHARED_SEMANTIC** | `MSORTTR1`, `VFDSSVSOL1` |
| `AENTR_3:O.Data[15].3` | 2 | **PROVEN_SHARED_SEMANTIC** | `M39`, `T_10WH` |
| `AENTR_4:O.Data[9].0` | 2 | **PROVEN_SHARED_SEMANTIC** | `P27_MS.I.Auxiliary_Forward`, `SSVL1_1UP` |
| `AENTR_4:O.Data[9].2` | 2 | **PROVEN_SHARED_SEMANTIC** | `M37_AUX`, `ML2` |

## Mapped-only sample (L5X − GUI ASSIGNED)

These are typically UNRESOLVED_OWNER conflict bits that IO_MAP still named:

- `AENTR_3:O.Data[10].5`
- `AENTR_3:O.Data[15].3`
- `AENTR_4:O.Data[9].0`
- `AENTR_4:O.Data[9].2`

## Artifacts

- JSON: `exports\diagnostics\mscrenoship_io_gui_l5x_parity.json`
- MD: `exports\diagnostics\mscrenoship_io_gui_l5x_parity.md`
- Helper: `tools/diagnostics/_build_mscrenoship_io_gui_l5x_parity.py`

Production decoder was **not** changed; recommended gates are recorded above.
