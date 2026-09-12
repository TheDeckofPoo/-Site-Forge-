# CP4 Compiler Pass 1

Generated: 2026-09-12T07:16:14.938692+00:00
Finished PLC4 used: **NO**

## Inputs
- Discovery snapshot: `C:\dev\worktree\FortnaPlus\exports\cp4-discovery` (immutable)
- RUN: `C:\dev\worktree\FortnaPlus\workspace\cp4-run\RUN`
- Library: `C:\dev\worktree\FortnaPlus\tools\libraries\OReilly_Library_v3.L5X`

## Outputs
- L5X under `generated/`
- Reports: generation_summary, conveyor_provenance, vfd_generation, encoder_generation,
  sawtooth_generation, configuration_required, library_provenance

## Counts
- Conveyors generated: 80
- VFD forced from explicit discovery: 15
- Sawtooth lanes bound in report: 5
- Encoders: 2

## Sawtooth
Template: `tools\libraries\programs\Sawtooth_Merge_Program.L5X`
Status: INCLUDED_WITH_RUN_BINDINGS
Lane identities preserved from RUN Name tokens (not PE/VFD number equality).

## Tracking / WCS
**GENERATION NOT YET SUPPORTED** — evidence preserved; Sorter_Track / WCS_Interface not auto-included.

## Configuration required
See `configuration_required.json` for Area / ES / downstream / sawtooth parameterization gaps.
