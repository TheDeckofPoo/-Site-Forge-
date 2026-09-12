# CP4 Compiler Pass 1

**Branch:** `feature/cp4-compiler-pass1`  
**Status:** Candidate L5X generated — **not** compared to finished PLC4 in this pass  
**Firewall:** Finished PLC4 L5X was **not** used as generation input

---

## Inputs (allowed)

1. Frozen discovery: `exports/cp4-discovery/` (immutable)
2. CP4 RUN: `workspace/cp4-run/RUN`
3. Generic libraries under `tools/libraries/`
4. Optional engineer workbook overlay

## Outputs

`exports/cp4-pass1/`

| Artifact | Purpose |
|----------|---------|
| `generated/*.L5X` | Candidate CP4 Studio export |
| `generation_summary.json` | Pass headline |
| `conveyor_provenance.json` | Identity / drive / PE / Area / ES / downstream |
| `vfd_generation.json` | Explicit VFD mapping beat heuristics |
| `encoder_generation.json` | ENC414 / ENC424 parameters preserved |
| `sawtooth_generation.json` | 5-lane RUN bindings + template notes |
| `configuration_required.json` | Area / ES / downstream / sawtooth param gaps |
| `library_provenance.json` | Generic library usage |
| `tracking_wcs_status.json` | **GENERATION NOT YET SUPPORTED** |

## Rules enforced

- Explicit SawLane / Mtrchain / Motor relationships beat naming heuristics
- `LANE_3_P116` + `PE118_P` + `VFD118_EN` is valid RUN evidence
- Multi-equipment VFD (e.g. VFD414 → P414,P416) preserved
- Area / ES not copied from finished PLC4 — `CONFIGURATION REQUIRED` when provisional
- Sorter_Track / WCS_Interface **not** auto-included
- Discovery snapshot is not rewritten from generation results

## Sawtooth template

`tools/libraries/programs/Sawtooth_Merge_Program.L5X` is a reusable **program pack** (gold pattern), not a finished controller used as input. Pass 1 includes it via `include_programs=Sawtooth_Merge` and records RUN lane bindings. Full MRG414/lane PE retarget remains **CONFIGURATION REQUIRED** for Pass 2.

## Reproduce

```
python tools/scripts/fortna_cp4_pass1.py \
  --discovery exports/cp4-discovery \
  --run-dir workspace/cp4-run/RUN \
  --out exports/cp4-pass1

python tools/scripts/test_cp4_compiler_pass1.py
```
