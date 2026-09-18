# PLC5 Physical I/O Endpoint Collision Report

**Machine:** ORNCCP5  
**RUN:** `workspace/cp5-run/RUN`  
**Date:** 2026-09-17  
**Scope:** Configio Octal_Word → EIPModules → Logix `CPxRIOn:I/O.Data[n].bit`  
**Policy:** Do not mute Generate, pick winners, or suppress duplicate-OTE diagnostics.

---

## Root cause

PLC5 Configio Descs use **PANEL-NODE-slotHalf** form (`CP5-NODE53-1A`), not PLC2’s PANEL-CATALOG-INDEX (`CP2-1794-IA16-3`).

`fortna_physical_word_resolver.parse_configio_desc` only understood catalog Descs, so the physical map produced **0 words** for ORNCCP5. Autogen then fell through to `_resolve_via_configio` / bank_index:

1. Configio **Bank column** (EIP bank) was matched without NODE→adapter scoping.
2. Words **516** and **520** both carry Configio Bank **40**, so both hit the only indexed `OutputBank=40` card (`1794-AENT-3` slot1 OB16P).
3. Autogen flex addressing kept EIP chassis slot as Data index when max slot &lt; 8 → `T_1794_AENT_3:O.Data[1].0`.
4. Word **516** is actually NODE52 slot7 **IA16 InputBank=40** (input on AENT-2), not an AENT-3 output.

**False collision class:** `B. SITE_FORGE_ADDRESS_TRANSLATION_COLLISION`

Bank→slot was effectively “first OutputBank match,” not the EIPModules relationship.

---

## EIPModules truth (AENT-3 / related)

From `PROJECT/EIPModules.asc.ORNCCP5`:

| Module | Adapter | Slot | InputBank | OutputBank |
|--------|---------|-----:|----------:|-----------:|
| 1794-IA16-17 | 1794-AENT-2 | 7 | **40** | 0 |
| 1794-OB16P-19 | 1794-AENT-3 | 1 | 0 | **40** |
| 1794-IB16-20 | 1794-AENT-3 | 2 | **54** | 0 |
| 1794-OB16P-21 | 1794-AENT-3 | 3 | 0 | **44** |
| 1794-IB16-22 | 1794-AENT-3 | 4 | **58** | 0 |
| 1794-OB16P-23 | 1794-AENT-3 | 5 | 0 | **48** |
| 1794-IB16-24 | 1794-AENT-3 | 6 | **62** | 0 |

Adapters: AENT-2 = `192.168.1.52` (NODE52), AENT-3 = `192.168.1.53` (NODE53).

Configio (authoritative Octal_Word → Bank + Desc):

| Octal_Word | Bank (Low) | Desc | In_Out (Low) |
|-----------:|-----------:|------|--------------|
| 516 | 40 | CP5-NODE52-7A | all 0 (input card) |
| 520 | 40 | CP5-NODE53-1A | has 1s (output card) |
| 522 | 44 | CP5-NODE53-3A | has 1s |
| 524 | 48 | CP5-NODE53-5A | has 1s |

Same Configio Bank **number** on different NODE adapters is normal — identity is **(adapter, EIPModules bank field)**, not the integer alone.

---

## Classification taxonomy (task A–E)

| Code | Meaning |
|------|---------|
| **A** | `RUN_PROVEN_SAME_PHYSICAL_POINT` — RUN tables intentionally share one physical channel |
| **B** | `SITE_FORGE_ADDRESS_TRANSLATION_COLLISION` — Site Forge collapsed distinct RUN banks/modules |
| **C** | `NAME_NORMALIZATION_COLLISION` — logical name stripping/aliasing merged owners |
| **D** | `ENGINEER_OVERRIDE_COLLISION` — override forced shared endpoint |
| **E** | `REVIEW_REQUIRED` — insufficient / conflicting RUN evidence |

---

## Evidence table

| logical_name | RUN source | Bank (Octal_Word.bit) | Configio Bank | EIP bank field | module type | adapter | physical slot | Logix endpoint (after) | authority | classification |
|---|---|---|---:|---|---|---|---:|---|---|---|
| EZPWS442 | Conveyor.asc IO_Address_Word/Bit | 516.0 | 40 | InputBank=40 | 1794-IA16 | 1794-AENT-2 / CP5RIO1 | 7 | `CP5RIO1:I.Data[6].0` | Configio+EIPModules+eipcfg | **B** (was false collision; fixed) |
| SSVEZPE442_P | Conveyor.asc | 520.0 | 40 | OutputBank=40 | 1794-OB16P | 1794-AENT-3 / CP5RIO2 | 1 | `CP5RIO2:O.Data[0].0` | Configio+EIPModules+eipcfg | **B** (was false collision; fixed) |
| SSV506A1 | Conveyor.asc | 522.0 | 44 | OutputBank=44 | 1794-OB16P | 1794-AENT-3 / CP5RIO2 | 3 | `CP5RIO2:O.Data[2].0` | Configio+EIPModules+eipcfg | **B** risk if ordinal math used; now distinct |
| VFD444_EN | Conveyor.asc | 524.0 | 48 | OutputBank=48 | 1794-OB16P | 1794-AENT-3 / CP5RIO2 | 5 | `CP5RIO2:O.Data[4].0` | Configio+EIPModules+eipcfg | distinct OB16P |
| PE600D_J | Conveyor.asc | 512.0 | 32 | InputBank=32 | 1794-IA16 | 1794-AENT-2 / CP5RIO1 | 3 | `CP5RIO1:I.Data[2].0` | Configio+EIPModules | see 517 |
| *(no bit0 Conveyor)* | Configio only | 517.0 | 32 | InputBank=32 | 1794-IA16 | 1794-AENT-2 / CP5RIO1 | 3 | `CP5RIO1:I.Data[2].0` | Configio Desc NODE52-**8** but rack has no slot 8 | **E** REVIEW_REQUIRED |

Finished PLC5 oracle corroboration (validation only, not generation input):

- `XIC(CP5RIO1:I.Data[6].0)OTE(EZPWS442.I.PS_OK);` matches after-fix 516.0.
- `XIC(P442_Conv.O.Release)OTE(CP5RIO2:O.Data[0].0);` matches AENT-3 OB16P Data[0] family used by word 520.

---

## Before / after (sample collisions)

| Octal_Word.bit | Part | BEFORE (broken bank_index path) | AFTER (EIPModules + NODE) |
|---|---|---|---|
| 516.0 | EZPWS442 | `T_1794_AENT_3:O.Data[1].0` | `CP5RIO1:I.Data[6].0` |
| 520.0 | SSVEZPE442_P | `T_1794_AENT_3:O.Data[1].0` (**same**) | `CP5RIO2:O.Data[0].0` |
| 522.0 | SSV506A1 | `T_1794_AENT_3:O.Data[3].0` (slot-as-Data, no Flex−1) | `CP5RIO2:O.Data[2].0` |

516 and 520 no longer share a Logix channel.

---

## Fix (minimal)

**Files:**

1. `tools/scripts/fortna_physical_word_resolver.py`
   - Parse `CP5-NODEnn-sA/B` Descs.
   - Load `EIPModules.asc*` and stamp InputBank/OutputBank onto eipcfg modules by slot.
   - Resolve Configio word via **NODE→TargetIP adapter** + **EIPModules bank match** → chassis Slot → family-aware Data\[slot−1\] (1794).
   - Do **not** derive slot from bank arithmetic.
2. `tools/scripts/fortna_autogen.py` (caller only)
   - Activate physical word map when either PANEL-CATALOG or PANEL-NODE Configio evidence exists (PLC5 was previously skipped).

**Not changed:** CP1–CP4 decoder semantics; Generate mute; duplicate-OTE preflight; P220 lettered-motor ownership rules.

---

## Regressions

- `tools/scripts/test_plc5_io_endpoint_collision.py` — Bank516.0 ≠ Bank520.0; 520 ≠ 522; P220 AUX + duplicate OTE still enforced.
- `tools/scripts/test_m220_aux_identity.py` — still PASS.
- PLC2 INT229/M402 physical distinctness covered when a PLC2 RUN is available (`active_rio_audit` / `_plc2_run_peek`).

---

## Remaining diagnostics (intentionally kept)

| Item | Notes |
|------|-------|
| Word 517 vs 512 | Same Configio Bank 32 on NODE52; Desc claims slot 8 (no such card). Class **E** — do not invent an endpoint or suppress. |
| Duplicate OTE preflight | Still ERROR on two writers of one OUTPUT bit. |
