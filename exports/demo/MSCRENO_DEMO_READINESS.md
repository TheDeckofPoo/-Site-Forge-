# MSCRENO Demo Readiness

Generated: 2026-09-19T22:51:25.095Z
Target: MSCRENO / MSCRENOPICK
Overall: **PASS**

| Gate | Status |
|---|---|
| active_project_synchronization | PASS |
| hardware_io_loads | PASS |
| transportation_auto_hydrates | PASS |
| transportation_responsiveness | PASS |
| safety_inventory_visible | PASS |
| safety_assignment_workflow | PASS |
| project_save_reload | PASS |
| cross_project_isolation | PASS |
| gui_autogen_generation | PASS |
| foreign_machine_artifact_count | 0 |
| studio_import | NOT TESTED |

## Timings (ms)

```json
{
  "clear_ms": 0,
  "api_ready_ms": 0.8,
  "hydrate_ms": 7713,
  "transport_build": {
    "ok": true,
    "built": true,
    "summary": "Auto Build (cp5a-mapper): 75 placed, 39 auto connections, 95 ambiguous, 231 decoder unplaced candidates",
    "reason": "demo smoke import"
  },
  "safety_build": {
    "ok": true,
    "device_count": 18,
    "unassigned_count": 18,
    "reason": "demo smoke import"
  },
  "import_hydrate_ms": 49435.1,
  "transport_tab_ms": 523,
  "transport_conveyors": 75,
  "first_lite_paint_ms": 19.7,
  "lite_belt_count": 75,
  "pan_ms": 10.7,
  "zoom_ms": 3,
  "select_ms": 33.1,
  "safety_ms": 1761.2,
  "safety_devices": 18,
  "safety_unassigned": 18,
  "safety_assigned_demo": 3,
  "switch_io_transport_ms": 35.6,
  "switch_transport_safety_ms": 3.1,
  "relaunch_hydrate_ms": 5074.5,
  "cross_project_ms": 61787.7
}
```

## Notes

- One Active Project — I/O, Transportation, and Safety hydrate from the same RUN.
- Studio import is NOT TESTED in this automated gate.
- Foreign P120_Conv count must be 0; P120C may remain when lineage proves it.

