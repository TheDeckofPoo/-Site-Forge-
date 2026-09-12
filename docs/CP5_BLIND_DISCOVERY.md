# PLC5 Blind Discovery Report

Generated: `2026-09-12T19:46:11.173973+00:00`

Strict blind generation: PLC5 RUN + FortnaPlus knowledge + generic libraries only.
Finished PLC5/4/2 were **not** used.

## Controller / RUN

- Machine: **ORNCCP5**
- Project: **OReillyGreensboro**
- Archive: `20251016-0933-OReillyGreensboro-ORNCCP5-RUN.tar.gz`
- Archive SHA256: `35be2761b1ee1fdefc226c3f0f21d22d043faa14141b113a677a709dffb6dab3`
- Controller overlays: **64**
- Tables (unique stems): **439**
- Known high: **35**
- Known partial: **4**
- Unknown: **400**

## Equipment activity

- Equipment: `{"INCLUDED": 79, "AVAILABLE": 0, "EXCLUDED": 0, "total": 79}`
- Motors: `{"INCLUDED": 96, "AVAILABLE": 0, "EXCLUDED": 0, "total": 96}`
- VFDs: `{"INCLUDED": 16, "AVAILABLE": 0, "EXCLUDED": 0, "total": 16}`
- Photoeyes: `{"INCLUDED": 94, "AVAILABLE": 0, "EXCLUDED": 0, "total": 94}`
- Encoders: `{"INCLUDED": 5, "AVAILABLE": 0, "EXCLUDED": 0, "total": 5}`
- Scanners: **1**

## Operational groups

- Engineering areas: **1**
- E-stop zones: **90**
- Start/Stop zones: **8**
- Jam zones: **27**
- Full groups: **79**

## Subsystems

- Merges: **3** detected=True
- Sawtooth merges: **0**
- Sorters: **5** detected=True
- Tracking structures (runtime tables): **11**
- Communications: **201**

## UI status summary

```json
{
  "TRANSPORT": {
    "Included": 79,
    "Available": 0,
    "Excluded": 0,
    "relationships_need_review": 283
  },
  "SAWTOOTH": {
    "detected": 0,
    "lanes": 0,
    "configuration_resolved_pct": 0.0,
    "engineer_decisions": 0
  },
  "SORTER": {
    "detected": 1,
    "configuration_modeled": true,
    "encoder_resolved": false,
    "scan_zones_resolved": true,
    "divert_map_required": true,
    "generation": "partial"
  },
  "PE": {
    "auto_resolved": 66,
    "engineer_required": 28
  }
}
```

## Generation

- Generatable: area_logic, controller_skeleton, conveyor_fast_logic, conveyor_slow_logic, encoder_logic, io_map, pe_logic
- Configuration required: diagnostics_hmi, induct_tracking, jam_full_logic, routing_logic, safety_zones, scanner_structures, simple_merge, sorter_tracking, startstop_zones, vfd_logic
- Unsupported: divert_logic, sorter_tracking, wcs_interface
- L5X generated: **True**
- L5X path: `C:\dev\worktree\FortnaPlus\exports\cp5-blind\generated\ORNCCP5_blind_candidate.L5X`
- L5X SHA256: `22c68474f6239f8c24464d4de52134f3fb4a96f2ae8bf1b4d0f3ba7533ac052b`
- Structural ok: **True**
- Genericity identical: **True**
- Validator ok: **True**

## Biggest uncertainty / gap

- Uncertainty: Engineering Area membership not proven from RUN (default Area_1 engineer-required).
- Compiler gap: Sorter divert / WCS / tracking generation remain NOT_SUPPORTED despite rich PLC5 sorter evidence.

## Frozen

- Commit: `1c8f84e2fd8cbf9f75065072dfabeb05c0c1f0a9`
- SiteModel SHA256: `afd8fa9feee98546e8f3a521dfff1da1789039214b8a391be77858fd9a7a11c6`
- Matrix SHA256: `aad53c5ff4f2f50fa5c7108deeb981f6705c069cce40869d67fda0a4035e9524`
