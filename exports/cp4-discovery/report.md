# CP4 Discovery Report — ORNCCP4

Generated: 2026-09-12T06:07:16.455355+00:00
RUN dir: `C:\dev\worktree\FortnaPlus\workspace\cp4-run\RUN`
Output: `C:\dev\worktree\FortnaPlus\exports\cp4-discovery`
Tar provenance (extract source only): `C:\Users\curtiskricke\Desktop\ORielly Green\Greensboro Tar.gz\20251016-0933-OReillyGreensboro-ORNCCP4-RUN.tar.gz`

## Firewall / scope

- **Finished PLC4 L5X was not read, parsed, or used.**
- **CP4 PLC generation / autogen was not implemented.**
- Discovery uses **CP4 RUN only** (controller-scoped overlays when present).

## Executive summary

| Item | Count |
|------|------:|
| Mechanical equipment (CP4-linked) | 76 |
| Placed (has geometry) | 76 |
| Unplaced | 0 |
| VFD device rows | 32 |
| Unique VFD bases | 13 |
| VFD→conveyor explicit mappings | 13 |
| VFD unknown conveyor mapping | 0 |
| Sawtooth merges | 1 |
| Sawtooth lanes | 5 |
| Saw lanes with conveyor in Name | 5 |
| Saw lanes with physical geometry | 5 |
| Saw lanes without geometry | 0 |
| Encoders | 2 |
| Tracking tables with active rows | 3 |
| SrtTrack active rows (all) | 98 |
| WCSEvents enabled | 84 |
| Connection candidates | 183 |

## Provenance mix

Codes used on relationships: `RUN_EXPLICIT` | `RUN_INFERRED` | `ENGINEER_REQUIRED` | `UNKNOWN`.

- **RUN_EXPLICIT**: 706
- **RUN_INFERRED**: 183
- **UNKNOWN**: 8

## ENGINEER_REQUIRED / gaps

- No hard ENGINEER_REQUIRED gaps on saw-lane conveyor identity; review UNKNOWN VFD mappings and unplaced equipment before generation.

## Sawtooth

Controller overlay used for merges: `FORTNA/SawMerge.asc.ORNCCP4` (controller_overlay).
Controller overlay used for lanes: `FORTNA/SawLane.asc.ORNCCP4` (controller_overlay).

Lane identity is **not** inferred from LaneNdx or P-number order; conveyor comes from the explicit Name token (e.g. `LANE_0_P219` → `P219`).

- Merge **SAWTOOTH_MERGE** motor_io=`VFD414_AUX` reservation=`SAW_RESERVATION` lanes=['LANE_0_P219', 'LANE_1_P408', 'LANE_3_P116', 'LANE_4_P214', 'LANE_5_P832']
- Lane **LANE_0_P219** conveyor=`P219` index=1 pe=`PE219_P` drive=`VFD219` slice=3.0s reserve=10.0s
- Lane **LANE_1_P408** conveyor=`P408` index=2 pe=`PE410_P` drive=`VFD410_EN` slice=18.0s reserve=20.0s
- Lane **LANE_3_P116** conveyor=`P116` index=3 pe=`PE118_P` drive=`VFD118_EN` slice=8.0s reserve=20.0s
- Lane **LANE_4_P214** conveyor=`P214` index=4 pe=`PE216_P` drive=`VFD216_EN` slice=6.0s reserve=15.0s
- Lane **LANE_5_P832** conveyor=`P832` index=5 pe=`PE834_P` drive=`VFD834_EN` slice=3.0s reserve=10.0s

## VFD

Scoped to ORNCCP4 via Machine_Name / EIP word map. Conveyor links only when Mtrchain, Motor column, or saw tables explicitly relate them.

- **VFD118** devices=['VFD118_AUX', 'VFD118_EN', 'VFD118_FLT'] conveyors=['P118'] (prov=RUN_EXPLICIT) saw_lanes=['LANE_3_P116']
- **VFD120** devices=['VFD120_AUX', 'VFD120_EN'] conveyors=['P120'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD216** devices=['VFD216_AUX', 'VFD216_EN', 'VFD216_FLT'] conveyors=['P216'] (prov=RUN_EXPLICIT) saw_lanes=['LANE_4_P214']
- **VFD218** devices=['VFD218_AUX', 'VFD218_EN'] conveyors=['P218'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD219** devices=['VFD219_AUX', 'VFD219_FLT', 'VFD219'] conveyors=['P219'] (prov=RUN_EXPLICIT) saw_lanes=['LANE_0_P219']
- **VFD219A** devices=['VFD219A_AUX', 'VFD219A'] conveyors=['P219A'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD410** devices=['VFD410_AUX', 'VFD410_EN', 'VFD410_FLT'] conveyors=['P410'] (prov=RUN_EXPLICIT) saw_lanes=['LANE_1_P408']
- **VFD412** devices=['VFD412_AUX', 'VFD412_EN'] conveyors=['P412'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD414** devices=['VFD414_AUX', 'VFD414_EN'] conveyors=['P414', 'P416'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD422** devices=['VFD422_AUX', 'VFD422_EN', 'VFD422_FLT'] conveyors=['P422'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD424** devices=['VFD424_AUX', 'VFD424_EN'] conveyors=['P424', 'P424A'] (prov=RUN_EXPLICIT) saw_lanes=[]
- **VFD834** devices=['VFD834_AUX', 'VFD834_EN', 'VFD834_FLT'] conveyors=['P834'] (prov=RUN_EXPLICIT) saw_lanes=['LANE_5_P832']
- **VFD836** devices=['VFD836_AUX', 'VFD836_EN'] conveyors=['P836'] (prov=RUN_EXPLICIT) saw_lanes=[]

## Encoders

- **ENC414** io=`ENC414` tpf=6.0 target_fpm=150.0 enable=`VFD414_AUX` jamzone=`SAWTOOTH MERGE` assoc=[encoder_enable_vfd→VFD414_AUX, encoder_to_saw_merge_via_motor_io→SAWTOOTH_MERGE, encoder_jamzone_sawtooth→SAWTOOTH MERGE]
- **ENC424** io=`ENC424` tpf=6.0 target_fpm=225.0 enable=`VFD424_AUX` jamzone=`CITY COUNTER` assoc=[encoder_enable_vfd→VFD424_AUX]

## Tracking / WCS (inventory only)

- **MsgTrack**: Empty / zero-byte on this CP4 RUN — no active tracking message records.
- **MsgWCS**: Active outbound WCS message queue with 1999 rows carrying Destination topics. Runtime event traffic, not static topology.
- **SrtTrack**: SrtTrack named-slot counts: SrtTrack1=98, SrtTrack2=0, SrtTrack3=0, SrtTrack4=0, SrtTrack5=0. Relationships exposed when active: ScanZoneID, ConfirmScan, SorterLane.
- **XfrTrack**: No named active transfer-track rows on this RUN.
- **WCSEvents**: 84 events with WCSEnable=Y. Exposes event→topic (WCSDestination) and category/service relationships. Not conveyor topology.

## Equipment / layout

Geometry uses `fortna_physical_geometry` infeed-origin model (same as CP2). Placed=76 unplaced=0. Saw lanes with geometry=5 / without=0.

Connection candidates are geometric exit→entry only; P-number order is never used as adjacency evidence.

## Artifacts

- `equipment.json`
- `vfd.json`
- `sawtooth.json`
- `encoders.json`
- `tracking_wcs.json`
- `layout_metrics.json`
- `report.md`

