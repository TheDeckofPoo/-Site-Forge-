# CP4 Sawtooth Fidelity Generation

Generated: 2026-09-12T15:48:57.507560+00:00
Finished PLC4 used: **NO**
Pass: `cp4-sawtooth-fidelity`

## Inputs
- Discovery: `C:\dev\worktree\FortnaPlus\exports\cp4-discovery` (immutable)
- RUN: `C:\dev\worktree\FortnaPlus\workspace\cp4-run\RUN`
- Generic libraries under `tools/libraries/`
- Explicit parameter map (no blind L5X digit replace)

## Outputs
- Controller L5X: `C:\dev\worktree\FortnaPlus\exports\cp4-sawtooth-pass\generated\OReillyGreensboro_ORNCCP4.L5X`
- Parameterized program: `C:\dev\worktree\FortnaPlus\exports\cp4-sawtooth-pass\generated\Sawtooth_Merge_Parameterized.L5X`
- Content digest: `17f3f00f1ad52f39f4943872e9f127af4b021fa06822b59d3a4da397df1825a1`

## Sawtooth
- Lanes: **5** (RUN_EXPLICIT)
- LANE_3_P116 → PE118_P / VFD118_EN preserved
- Slice/reserve timing emitted as `SawFid_L*_SliceSec` / `SawFid_L*_ReserveSec`
- Conv_PE / Conv_Enc / Conv_Fast filled from RUN bindings
- Collector/merge/reservation/encoder parameters inventoried in `parameter_map.json`

## VFD / Encoders (Pass2 preserved)
- VFD bases: **13**
- Shared: VFD414→P414,P416 ; VFD424→P424,P424A
- Encoders: ENC414 / ENC424 parameters emitted

## Tracking / WCS
**GENERATION NOT YET SUPPORTED** — inventory only (SrtTrack, MsgTrack, MsgWCS, WCSEvents, XfrTrack)

## CONFIGURATION REQUIRED (sample)
- `area`: P100
- `es_zone`: P100
- `downstream`: P100
- `area`: P100A
- `es_zone`: P100A
- `downstream`: P100A
- `area`: P102
- `es_zone`: P102
- `downstream`: P102
- `area`: P104
- `es_zone`: P104
- `downstream`: P104
- `area`: P106
- `es_zone`: P106
- `downstream`: P106
- `area`: P108
- `es_zone`: P108
- `downstream`: P108
- `area`: P110
- `es_zone`: P110
- `downstream`: P110
- `area`: P112
- `es_zone`: P112
- `downstream`: P112
- `area`: P114
- `es_zone`: P114
- `downstream`: P114
- `area`: P116
- `es_zone`: P116
- `downstream`: P116
- `area`: P118
- `es_zone`: P118
- `downstream`: P118
- `area`: P120
- `es_zone`: P120
- `downstream`: P120
- `area`: P200
- `es_zone`: P200
- `downstream`: P200
- `area`: P200A

## GENERATION NOT YET SUPPORTED
- `tracking_wcs`: SrtTrack / MsgTrack / MsgWCS / WCSEvents / XfrTrack inventory only

## UI
No new Transport toolbar buttons. Workflow remains Import → Auto Build → Review → Apply → Build PLC.
