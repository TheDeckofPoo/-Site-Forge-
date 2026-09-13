# Aug28 Autogen Forensics — MSCRENO SHIP Transport

**Branch:** `feature/plc2-transport-fidelity`  
**Purpose:** Historical Site Forge regression — compare 2026-08-28 MSCRENO SHIP L5X / `fortna_autogen.py` against current `from-run` output. Do **not** invent new I/O systems; prove transport generation is still present.

## Executive verdict

| Question | Answer |
|----------|--------|
| Generating era / commits | **2026-08-28 ~14:45** L5X; code around **`0ce9e1e` / `88581bf`** (suite backup `suite-20260828-163000`) |
| Historical generator deleted? | **NO** — same stack in `tools/scripts/fortna_autogen.py` |
| Conv / Conv_AOI / MS / Area Fast·Slow·L1·L2 emitters intact? | **YES** (`clone_template_for_conveyor`, `build_l5x` area family) |
| CURRENT thinner on Conv/AOI? | **YES (−10)** — intentional identity fix, not missing emitters |
| Real CP_I / CP_O recovered? | **YES** — identical real counts (164 / 87) |
| Historical transport generation recovered? | **YES** (structural gates pass; see compare.json) |

## 1. Generating commit / files

| Artifact | Path / ref |
|----------|------------|
| Historical L5X | `workspace/validation/MSCRENO_MSCRENOSHIP_AUG28.L5X` (mtime **2026-08-28 14:45:50**) |
| Source RUN | `workspace/inbox/20260813-1132-MSCRENO-MSCRENOSHIP-RUN.tar.gz` |
| Aug28 code snapshot | `exports/backups/suite-20260828-163000/FortnaPlus/tools/scripts/fortna_autogen.py` (5274 lines) |
| PACK good-autogen (08/26) | `exports/backups/good-autogen-20260826-184506/scripts/fortna_autogen.py` |
| Git era | `b2e94d9` → `7b0ed46` (08/26) → `0ce9e1e` / `88581bf` (08/28 EOD + suite backup) |
| Current engine | `tools/scripts/fortna_autogen.py` (5839 lines) |
| CURRENT regenerate | `exports/mscreno-aug28-regression/MSCRENO_MSCRENOSHIP_CURRENT.L5X` |
| Structural compare | `exports/mscreno-aug28-regression/compare.json` |

## 2. Diff focus: Aug28 vs current `fortna_autogen.py`

### Preserved (do not rewrite)

| Piece | Functions / locus | Role |
|-------|-------------------|------|
| RUN → input | `load_from_run` | Conveyors, PE, IO points, EIP, Configio |
| Configio banks | `_load_configio_octal_map`, `_resolve_via_configio`, `_resolve_fortna_bank` | Reno empty-EIPCSV word→module |
| EIP tree | `load_eip_topology`, `_load_eip_adapters` | AENTR + child cards |
| Conv_UDT / Conv_AOI / MS | `clone_template_for_conveyor` | Clones library `P1000`/`P3000` → `P###_Conv` / `_Conv_AOI` / `_MS` |
| PE_UDT | same + `build_l5x` PE ensure loop | Photoeye UDT + PE_Logic / Full_PE |
| Area Slow/Fast/L1/L2 | `build_l5x` area emit block | `*_Area_Slow/Fast/L1/L2` programs + routine families |
| IO_MAP CP_I / CP_O | `build_l5x` IO_MAP section | Real XIC/OTE maps from RUN banks |
| CLI | `from-run --with-io-map` / `--io-map-placeholders` | Defaults keep IO_MAP on |

### Changed (post-Aug28, still generic)

| Change | Effect on MSCRENO SHIP |
|--------|------------------------|
| Untagged conveyor gate → `fortna_identity.linked_owns_conveyor` | Stops `P60` prefix-owning `P600` / `P13`→`P130` / `P41`→`P410` / `P52`←`P520` |
| Configio-primary `PhysicalWordResolver` hook in `load_from_run` | Greensboro-style PANEL descs; Reno Configio path unchanged when descs don't parse |
| IO_MAP placeholders default **on** | Extra `NO_PointPlaceholder` rungs; **real** map counts unchanged |
| Empty Fast/Slow/L2 routines omitted | No NOP `Conv_Full` / `Conv_Merge` / empty `Merge` scaffolds |
| Fail-closed `_generation_assertion_failures` | Empty IO_MAP / PE scaffolds fail build |
| Optional `System` (Sys_Comm) | Only with `--include-programs System` (Aug28 L5X included it) |
| M###_AUX → `P###_MS` Motor_Starter stubs | **More** MS tags than Aug28 |

### Removed / bypassed

| Piece | Classification |
|-------|----------------|
| String-prefix untagged conveyor ownership | **Removed on purpose** (false positives) |
| Always-emit empty Fast Conv_Full/Merge / L2 Merge | **Bypassed** (omit empty) — families still emit when content exists |
| Gold Excel IO_MAP as default | **Bypassed** (CLI `--io-map-gold` only); RUN CP_I/CP_O remains default |
| UI workbook bridge regressions | Covered in `docs/IO_REGRESSION_FORENSICS.md` — **not** generator deletion |

### Regression points (Aug28 L5X vs CURRENT)

| Metric | AUG28 | CURRENT | Notes |
|--------|------:|--------:|-------|
| Modules | 68 | 68 | Identical catalogs |
| Adapters (AENTR) | 4 | 4 | AENTR15 / 15RP1 / 15RP2 / 16 |
| CP_I real | 164 | 164 | Recovered |
| CP_O real | 87 | 87 | Recovered |
| CP_I placeholder | 0 | 105 | Default fill |
| CP_O placeholder | 0 | 38 | Default fill |
| Conv_UDT | 44 | 34 | −10 prefix false-positives |
| Conv_AOI | 43 | 33 | Same −10 belts |
| MS (`*_MS`) | 42 | 56 | +AUX→MS stubs; −false-positive belt MS |
| PE_UDT | 94 | 94 | Match |
| Area Fast/Slow/L1/L2 | yes | yes | `MSCRENOSHIP_Area_*` |
| Programs | 7 (incl. System) | 6 | System optional |

**Only-in-AUG28 Conv tags:** `P130`, `P410`, `P52`, `P600`, `P601`, `P602`, `P604`, `P606`, `P608`, `P610` — all `Machine_Name=N/A` in Conveyor.asc; pulled by Aug28 prefix rule from PE-linked shorter bases (`P13`, `P41`, `P60`, `P520`).

**Follow-up (transport-fidelity):** motor-owned belts are now linked generically (`M###` / `M###_AUX` → `P###` exact family). That correctly recovers belts like `P52` (MSCRENOSHIP `M52`) and PLC2 `P123` (`M123`) without restoring digit-prefix false positives (`P60` ↛ `P600`).

## 3. Emitters that produce Conv / AOI / MS / Area families

Still in current `fortna_autogen.py` (same roles as Aug28):

1. **`load_from_run`** — selects conveyor rows (`CONVEYOR_ASC_TYPES`) scoped by Machine_Name or linked PE/VFD.
2. **`clone_template_for_conveyor`** — emits `P###_Conv` (Conv_UDT), `P###_Conv_AOI`, `P###_MS` / `P###_VFD` (Motor_Starter_UDT), PE_UDT clones, Fast_Conv / Slow_Jam / Slow_Flt / PE_Logic rungs.
3. **`build_l5x`** — aggregates tags; builds `*_Area_Slow` (Conv_Flt/Jam/PE), `*_Area_Fast` (Conv_Fast/Full/Merge/PE), `*_Area_L1` (Area/Conv/CS/MS_Time/…), `*_Area_L2` (Conv_Speed/FullTime/Merge/PETime); emits IO_MAP `CP_I`/`CP_O`.

**No port/restore performed:** emitters were never deleted. Restoring Aug28 prefix ownership would reintroduce cross-belt pollution and is **not** generic fidelity.

## 4. Recovery plan

1. Keep `from-run --with-io-map` (placeholders default on) as the product CLI path — already regenerates transport + real IO_MAP.
2. Do **not** reintroduce string-prefix conveyor ownership; use workbook / Transport Build overlay for engineer-added belts.
3. Optional: `--include-programs System` when Sys_Comm / NTP cookie-cutter is required (parity with Aug28 program list).
4. Lock structural gates via `tools/scripts/test_mscreno_aug28_regression.py` (not byte-identical).
5. I/O identity / UI bypass remains under `docs/IO_REGRESSION_FORENSICS.md`.

## 5. Regenerate recipe (this regression)

```text
python tools/scripts/apply_recipe.py import workspace/inbox/20260813-1132-MSCRENO-MSCRENOSHIP-RUN.tar.gz
python tools/scripts/fortna_autogen.py from-run --run-dir workspace/active/RUN --with-io-map --io-map-placeholders --out-dir exports/mscreno-aug28-regression
copy MSCRENO_MSCRENOSHIP.L5X → MSCRENO_MSCRENOSHIP_CURRENT.L5X
```

## 6. Bottom line

Historical MSCRENO transport generation is **recovered** under current code: modules, real CP_I/CP_O, PE_UDT, MS, and full Area Slow/Fast/L1/L2 families all emit. The Conv/AOI count drop is an **identity correctness fix**, not a missing IO/transport subsystem.
