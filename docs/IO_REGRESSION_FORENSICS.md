# I/O Regression Forensics

**Branch:** `feature/io-regression-lock`  
**Base:** `feature/runtime-acceptance-recovery` @ `1847ca8`  
**Purpose:** Prove the RUN-driven I/O generator was **not deleted** — it was **bypassed** by the UI product path — and permanently lock identity-level regression fixtures.

## Executive verdict

| Question | Answer |
|----------|--------|
| Historical I/O implementation found? | **YES** — still in `tools/scripts/fortna_autogen.py` |
| Last known-good SHA (end-to-end product path) | **`1847ca8`** (`feature/runtime-acceptance-recovery`) |
| Last known-good generator artifact (CLI/hardware tree) | **2026-08-26** backup `exports/backups/good-autogen-20260826-184506/` (PACK: 922 IO_MAP mapped) |
| Was historical generator deleted? | **NO** |
| Was it bypassed? | **YES** |
| Root regression path | UI state/workbook bridge on/before `feature/connectivity-sorter-closure` @ **`54e6a74`** (suite snapshot 2026-08-28 already had `workbook: undefined`) |

## 1. Last known-good I/O history

### Generator stack (preserved — do not rewrite)

| Function / artifact | File | Role |
|---------------------|------|------|
| `load_from_run` | `tools/scripts/fortna_autogen.py` | RUN → conveyors, PE, IO points, EIP, word map, Configio |
| `load_eip_topology` | same | Remote I/O hardware tree + Fortna word→module map |
| `_load_eip_adapters` | same | Adapters / IP / modules / topology / `io_word_map` |
| `_load_configio_octal_map` | same | `Configio.asc` octal word → bank (when EIPCSV empty) |
| `_build_eip_bank_index` | same | Bank → card list |
| `_resolve_via_configio` / `_resolve_fortna_bank` | same | Word/bit → module channel |
| `build_l5x` Modules emit | same | `<Modules>` tree (AENT / child cards) |
| `build_l5x` IO_MAP emit | same | CP_I / CP_O rungs `XIC(mod:I.Data[s].b)OTE(tag)` |
| `_generation_assertion_failures` | same | Fail-closed when mappable IO → 0 mappings |
| CLI `--with-io-map` / `--no-io-map` | same | Explicit IO_MAP include |
| `extract_io_points` | `tools/scripts/fortna_io_extract.py` | Conveyor.asc bank/bit points |
| `load_eip_modules` | `tools/scripts/fortna_ignition_build.py` | eipcfg allowlist |
| `apply_workbook_to_input` | `tools/scripts/fortna_workbook.py` | Engineer overlays (must not strip IO) |

### Timeline (selected)

| When | SHA / ref | Note |
|------|-----------|------|
| 2026-08-12 | `eaebbe4` | Initial FortnaPlus — Modules + EIP foundation present |
| 2026-08-13 | `9e73188` | `include_io_map` / `--with-io-map` wired into Autogen + Electron `main.js` |
| 2026-08-14 | `c06ac7f` | `io_word_map` evolution; sorter_build field added |
| 2026-08-26 | `b2e94d95` + **good-autogen backup** | Named RIO tree fidelity; **922 mapped** PACK proof |
| 2026-08-28 | `0ce9e1ed` + suite backup | Generator intact; UI already passes `workbook: undefined` |
| 2026-09 | `1de03cd` / CP5 gap-closure | Compiler paths that call `load_from_run` remain good |
| 2026-09 | `54e6a74` | `connectivity-sorter-closure` — CLI I/O capable; **UI product path broken** |
| 2026-09-13 | **`1847ca8`** | Runtime recovery — SiteModel→editors, canonical workbook, fail-closed IO |

## 2. What regressed (piece-by-piece)

| Piece | Historical known-good | Broken UI flow (pre-`1847ca8`) | Classification |
|-------|----------------------|--------------------------------|----------------|
| `load_from_run` | Used by CLI `from-run` | Still present; UI invoke path reached it when generate ran | **preserved** |
| EIP module tree generation | Emitted under `--with-io-map` / from-run | Same code path; Electron already passed `--with-io-map` | **preserved** |
| Word/bit map (`io_word_map` + Configio) | Built inside `load_from_run` | Preserved in engine | **preserved** |
| IO_MAP rung generation | Built from RUN banks + word map | Engine OK; empty/misleading when inputs starved or assertions absent | **preserved** (engine) / **bypassed** (product evidence) |
| Electron `--with-io-map` flag | Present since `9e73188` | Still passed by `desktop/main.js` | **preserved** (not disabled by option in default UI) |
| SiteModel after Import | Discovery wrote `editors.*` | Dashboard **ignored** `res.discovery` | **disconnected** |
| Sawtooth/Sorter editor state | Should come from SiteModel | Empty → Prefill / localStorage | **disconnected** / **stale data** |
| Workbook on Build PLC | Should be canonical SiteModel + overrides | UI forced `workbook: undefined`, reloaded disk only | **supplied wrong/incomplete workbook** |
| Cross-machine workbook merge | Fresh RUN should rebuild | `--merge-existing` could leak CP2 rows into CP4 | **overwritten by cross-machine state** |
| Fail-closed IO assertions | Missing historically | Added on recovery | was **absent** (silent bad L5X) |

### Proven conclusion

```
discovery (SiteModel)     = GOOD
from-run --with-io-map    = GOOD (generator never deleted)
UI state / workbook bridge = BAD  ← root product regression
```

Curtis’s Studio FAIL (missing I/O trees / NOP IO_MAP) was an **integration failure**, not loss of the historical I/O engineering work.

## 3. Known-good fixture policy

Chosen RUNs (Greensboro, historically exercised):

| Machine | Archive | Studio candidate |
|---------|---------|------------------|
| ORNCCP2 | `20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz` | `exports/studio-validation/ORNCCP2_ui_candidate.L5X` |
| ORNCCP4 | `…ORNCCP4-RUN.tar.gz` | `…ORNCCP4_ui_candidate.L5X` |
| ORNCCP5 | `…ORNCCP5-RUN.tar.gz` | `…ORNCCP5_ui_candidate.L5X` |

Baselines (identity + mapping, not counts alone):

- `exports/io-regression-lock/cp2_io_baseline.json`
- `exports/io-regression-lock/cp4_io_baseline.json`
- `exports/io-regression-lock/cp5_io_baseline.json`

Each baseline stores:

- module identities / catalogs / parents
- word-map sample (rio, slot, direction, type)
- representative exact IO_MAP mappings (`tag` + `channel` + `slot` + `bit` + `direction`)
- discovered PE points with bank/bit
- L5X module + IO_MAP rung counts as secondary metrics

## 4. Hard regression failures (must stop acceptance)

Product-path tests in `tools/scripts/test_io_regression_lock.py`:

1. Known RUN with supported IO + Site Forge build path + **zero modules** → **FAIL**
2. Known RUN with supported mappings + **IO_MAP NOP-only** → **FAIL**
3. Discovered PE with mapped IO + **PE mapping missing** in L5X → **FAIL**
4. Representative exact mapping expectations from baselines → **FAIL** if tag/channel/slot/bit drift

Also retained from recovery: `_generation_assertion_failures` inside `fortna_autogen.py` (mappable IO > 0 and mapped == 0 → BUILD FAILED).

## 5. Current baselines (summary)

| Machine | Modules (RUN) | Word map | L5X modules | IO_MAP XIC/OTE | NOP-only? |
|---------|---------------|----------|-------------|----------------|-----------|
| CP2 | 37 | 27 | 39 | 68 | No |
| CP4 | 38 | 46 | 40 | 476 | No |
| CP5 | 61 | 67 | 63 | 706 | No |

Example exact mapping (CP2):

```
XIC(T_1794_AENT_1:I.Data[6].11)OTE(PE215_J.I.PE_Clear);
```

## 6. Recovery protections kept

Do **not** remove:

- per-machine SiteModel discovery out + `workspace/active/site_model.json`
- automatic editor population (`applySiteModelToEditors`)
- single canonical workbook into Build PLC
- `--with-io-map` default product path
- no cross-machine workbook merge on fresh Import
- fail-closed generation assertions

## 7. Report card

| Item | Result |
|------|--------|
| historical I/O implementation found | **YES** (`fortna_autogen.py` stack) |
| last known-good SHA | **`1847ca8`** (E2E); generator artifact **2026-08-26 backup** |
| was historical generator deleted | **NO** |
| was it bypassed | **YES** (UI workbook/SiteModel bridge) |
| root regression commit/path | UI path @ **`54e6a74`** / suite `workbook: undefined` ≤ 2026-08-28 |
| CP2 / CP4 / CP5 baselines | **CAPTURED** under `exports/io-regression-lock/` |
| representative exact mapping tests | **PASS** (`test_io_regression_lock.py`) |
| UI-path IO_MAP regression lock | **PASS** (13/13 tests) |
