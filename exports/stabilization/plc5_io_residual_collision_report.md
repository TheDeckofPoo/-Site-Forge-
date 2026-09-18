# PLC5 Residual I/O Collision Report

**Machine:** ORNCCP5  
**RUN:** `workspace/cp5-run/RUN`  
**Date:** 2026-09-17  
**Prior fix:** Bank516 vs Bank520 (`fortna_physical_word_resolver.py` NODE+EIPModules)  
**Policy:** Do not mute Generate, pick winners, invent endpoints, or suppress duplicate-OTE diagnostics.

Companion: [`plc5_io_collision_report.md`](plc5_io_collision_report.md)

---

## Classification taxonomy

| Code | Name | Meaning |
|------|------|---------|
| **A** | `RUN_PROVEN_DUPLICATE` | RUN tables intentionally share one physical channel |
| **B** | `SITE_FORGE_ADDRESS_TRANSLATION_COLLISION` | Site Forge collapsed distinct RUN banks/modules onto one Logix endpoint |
| **C** | `LOGICAL_IDENTITY_COLLISION` | Logical name stripping/aliasing merged owners (e.g. M220→P220A) |
| **D** | `ENGINEER_OVERRIDE_COLLISION` | Override forced a shared endpoint |
| **E** | `REVIEW_REQUIRED` | Insufficient / conflicting RUN evidence — do not invent |

---

## Scan method

1. Build `build_physical_word_map(cp5-run, ORNCCP5)`.
2. Group resolved words by `channel_base`.
3. List Configio Low rows that share `(node, bank)` or share bank across nodes.
4. Corroborate with `EIPModules.asc.ORNCCP5` + Conveyor.asc ownership + finished L5X (validation only).

---

## Residual findings (after Bank516/520 fix, before this residual pass)

| Words | Shared / symptom | Evidence | Classification | Action |
|------:|-------------------|----------|----------------|--------|
| **516 vs 520** | Was same `T_1794_AENT_3:O.Data[1]` | Different NODE; IB40 vs OB40 | **B** (prior) | Already fixed — distinct `CP5RIO1:I.Data[6]` vs `CP5RIO2:O.Data[0]` |
| **512 vs 517** | Both → `CP5RIO1:I.Data[2]` | Same NODE52 bank **32**; Desc 517=`NODE52-8` but AENT-2 has **no slot 8**; EIPModules bank 32 = IA16 slot **3** only; In_Out 517 looks output-like; **no Conveyor.asc owners** on 517; finished L5X maps PE600D_J→Data[2].0 (word 512) | **E** `REVIEW_REQUIRED` | Stop collapsing 517 onto 512; leave 517 unresolved |
| **526, 527** | Unresolved (no channel) | NODE53-7/8 banks 52/66; AENT-3 slots only 1–6; no EIPModules bank match | **E** `REVIEW_REQUIRED` | Keep unresolved — no invent |
| Cross-node banks 40/82/86/100/104/108/130/148/150 | Same Configio bank **number**, different NODE | EIPModules+NODE scoping | Not a collision after prior fix | Verify distinct (pass) |
| P220 / M220 AUX | N/A on PLC5 map | PLC2 lettered-motor identity | **C** guard still enforced | No change |
| Duplicate OUTPUT OTE preflight | Diagnostic kept | Two writers → one `O.Data[n].bit` | Diagnostic (not muted) | No change |

No residuals classified as **A** `RUN_PROVEN_DUPLICATE` or **D** `ENGINEER_OVERRIDE_COLLISION` on this PLC5 physical map scan.

No additional **B** cases where EIPModules/NODE proved a *second* distinct endpoint that we could wire (517 has no card at Desc slot 8).

---

## Word 517 deep dive (primary residual)

| Field | Word 512 | Word 517 |
|-------|----------|----------|
| Configio Desc | `CP5-NODE52-3A/B` | `CP5-NODE52-8A/B` |
| Configio Bank Low/High | 32 / 33 | 32 / 33 (**duplicate**) |
| In_Out | `0000000000000000` (input-like) | `0000000011111111` (output-like) |
| EIPModules on AENT-2 | IA16-13 slot **3** InputBank=**32** | **No slot 8 module** |
| Conveyor.asc | PE600D_J, PE600E_J, PB*_JR, … | *(none)* |
| Finished L5X | `XIC(CP5RIO1:I.Data[2].0)OTE(PE600D_J…)` | *(no Bank517 / NODE52-8)* |

**Why not class B?** Class B requires Site Forge merging two *proven* distinct physical modules. Here EIPModules does **not** prove a second endpoint for 517 — only conflicting Configio (bank clone + missing slot). Inventing `Data[7]` or an OA8I would violate policy.

**Why not class A?** No RUN table shows two logicals intentionally sharing 517 with 512; 517 has no logical owners at all.

---

## Before / after (this residual pass)

| Octal_Word | BEFORE (post-516/520 fix) | AFTER (desc_slot corroboration) |
|-----------:|---------------------------|----------------------------------|
| 512 | `CP5RIO1:I.Data[2]` (IA16-13 slot3, bank32) | **unchanged** `CP5RIO1:I.Data[2]` |
| 517 | `CP5RIO1:I.Data[2]` (**false share** with 512) | **unresolved** `REVIEW_REQUIRED` (`desc_slot_mismatch_eipmodules_bank`) |
| 516 | `CP5RIO1:I.Data[6]` | unchanged |
| 520 | `CP5RIO2:O.Data[0]` | unchanged |
| 526 | unresolved (no bank match) | unresolved `REVIEW_REQUIRED` (`no_eipmodules_bank_match`) |
| 527 | unresolved (no bank match) | unresolved `REVIEW_REQUIRED` (`no_eipmodules_bank_match`) |

Shared `channel_base` count after fix: **0**.

---

## Fix (minimal)

**File:** `tools/scripts/fortna_physical_word_resolver.py`

- When NODE Desc → EIPModules bank match succeeds but **Desc slot ≠ EIPModules slot**, do **not** assign the bank-matched channel.
- Record unresolved with `classification=REVIEW_REQUIRED` and `reason=desc_slot_mismatch_eipmodules_bank` (word 517).
- Unmatched banks keep `reason=no_eipmodules_bank_match` (words 526/527).
- Still never derive slot from bank arithmetic; still never pick a winner between 512 and 517.

**Not changed:** Generate mute; duplicate-OTE preflight; P220 lettered-motor rules; CP1–CP4 decoder semantics; inventing modules for missing slots.

---

## Cross-node bank pairs still distinct (smoke)

| Banks | Words | Endpoints |
|------:|------:|-----------|
| 40 | 516 / 520 | `CP5RIO1:I.Data[6]` ≠ `CP5RIO2:O.Data[0]` |
| 82 | 603 / 611 | `CP5RIO3:I.Data[3]` ≠ `CP6RIO0:O.Data[1]` |
| 100 | 610 / 620 | `CP6RIO0:I.Data[0]` ≠ `CP6RIO1:O.Data[0]` |
| 148 | 701 / 716 | `CP6RIO2:I.Data[0]` ≠ `CP7RIO0:O.Data[4]` |

---

## Regressions

- `tools/scripts/test_plc5_io_endpoint_collision.py`
  - 516 ≠ 520; 520 ≠ 522 (prior)
  - **512 stays** `CP5RIO1:I.Data[2].0`
  - **517 not collapsed** onto 512; unresolved REVIEW
  - **526/527** remain REVIEW unresolved
  - P220 AUX + duplicate OTE still enforced
- `tools/scripts/test_m220_aux_identity.py` — PASS

---

## Classification summary

| Item | Classification |
|------|----------------|
| 516 vs 520 (historical false share) | `SITE_FORGE_ADDRESS_TRANSLATION_COLLISION` — **fixed previously** |
| Cross-node reused bank numbers (82, 86, 100, …) | Not residual — NODE scoping keeps endpoints distinct |
| 512 vs 517 channel collapse | `REVIEW_REQUIRED` — **stopped false assign**; no distinct endpoint to wire |
| 526, 527 missing EIPModules cards | `REVIEW_REQUIRED` — leave unresolved |
| P220 / M220A AUX | `LOGICAL_IDENTITY_COLLISION` guard — still enforced |
| Duplicate OUTPUT OTE | Diagnostic retained (not muted) |
| RUN_PROVEN_DUPLICATE / ENGINEER_OVERRIDE | None found on this scan |
