# CP4 Sawtooth Fidelity Generation

**Branch:** `feature/cp4-sawtooth-fidelity`  
**Status:** Candidate sawtooth portion generated from RUN + discovery + generic libraries  
**Firewall:** Finished PLC4 L5X was **not** used as generation input and was not inspected during generation

---

## Purpose

Complete PLC4 Sawtooth fidelity beyond Pass 1/2 scaffolding:

- Explicit reusable Sawtooth template parameterization (all site-varying params inventoried)
- Real L5X structures: tags, program, routines, lane/merge bindings, encoder/VFD associations, timing
- Provenance on every generated symbol
- Tracking/WCS remains **GENERATION NOT YET SUPPORTED** (inventory only)

## Inputs (allowed)

1. Frozen discovery: `exports/cp4-discovery/` (immutable; 76/76 equipment preserved)
2. CP4 RUN: `workspace/cp4-run/RUN`
3. Generic libraries under `tools/libraries/` (including `programs/Sawtooth_Merge_Program.L5X`)
4. Optional engineer workbook overlay via autogen

## Forbidden

- Finished / reference PLC4 L5X as generation input
- Blind whole-file L5X digit search/replace
- Copying Greensboro finished PLC objects
- Silent Sorter_Track / WCS_Interface activation
- New Transport toolbar buttons
- Mutating frozen discovery from generation results

## Outputs

`exports/cp4-sawtooth-pass/`

| Artifact | Purpose |
|----------|---------|
| `parameter_map.json` | Explicit site-varying parameter inventory + renames + lane bindings |
| `library_provenance.json` | Generic library usage |
| `generated/*.L5X` | Candidate controller + parameterized Sawtooth program |
| `generation_summary.json` | Pass headline + content digest |
| `sawtooth_generation.json` | Lane/merge fidelity report |
| `vfd_generation.json` | Explicit VFD mapping + shared relationships |
| `encoder_generation.json` | ENC414 / ENC424 parameters |
| `configuration_required.json` | Gaps + Tracking/WCS unsupported |
| `provenance.json` | Per-symbol provenance |
| `report.md` | Human summary |

## Parameterization rules

- Explicit RUN relationships beat naming heuristics  
  (`LANE_3_P116` → `PE118_P` / `VFD118_EN` is valid)
- Collector / merge motor / reservation / lane count / index / conveyor / PE / drive / disable / slice / reserve / approach / collision / merge input / encoder params are inventoried in the parameter map
- Pack symbols without RUN binds → **CONFIGURATION REQUIRED**
- Feature enables (`Enable_*` / `Use_*`) → **CONFIGURATION REQUIRED**
- Every symbol provenance ∈ `RUN_EXPLICIT | RUN_DERIVED | ENGINEER_CONFIGURED | GENERIC_LIBRARY` else **CONFIGURATION REQUIRED**

## L5X fidelity emit

- `SawFid_*` tags encode lane count, indices, slice/reserve timing, PE/drive/conveyor markers, encoder params, shared VFD markers
- Empty pack routines `Conv_PE` / `Conv_Enc` / `Conv_Fast` filled with RUN-bound rungs (NOP + provenance comments)
- Explicit symbol renames only (longest-first); no arbitrary digit mangling

## Preserve Pass2

- 13 VFD bases
- Shared VFD relationships (VFD414→P414,P416 ; VFD424→P424,P424A)
- 2 encoders
- 5 sawtooth lanes
- No finished PLC4 generation input
- Discovery 76/76 ownership reconciliation unchanged

## Reproduce

```
python tools/scripts/fortna_cp4_discovery.py ^
  --run-dir workspace/cp4-run/RUN --machine ORNCCP4 --out exports/cp4-discovery

python tools/scripts/fortna_cp4_sawtooth.py ^
  --discovery exports/cp4-discovery ^
  --run-dir workspace/cp4-run/RUN ^
  --out exports/cp4-sawtooth-pass

python tools/scripts/test_cp4_sawtooth_fidelity.py
python tools/scripts/test_cp4_discovery_no_leakage.py
python tools/scripts/test_cp4_compiler_pass2.py
```

## Tracking / WCS

**GENERATION NOT YET SUPPORTED** — `SrtTrack`, `MsgTrack`, `MsgWCS`, `WCSEvents`, `XfrTrack` remain inventory-only. Do not start generation in this pass.
