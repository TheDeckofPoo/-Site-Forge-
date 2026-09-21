# MSCATL_CP2 field follow-up summary

## INT-2ES2-1ESR1 classification root cause

`_classify_device` used `re.search(r"ESR\d*|ESR_", …)` which matched the embedded
substring `ESR1` inside the interlock name `INT-2ES2-1ESR1`.

That is an **interlock/signal reference**, not an ESR device.

**Fix:** reject `INT_*` / `INT-*` prefixes; require structured ESR/MCR/ESTOP
device identity tokens. Autogen never maps INT_* to `.I.ES_OK` (generic BOOL).

## Safety inventory stale?

ESPB* inventory from a prior controller is a **GUI stale-state** risk
(localStorage / uncleared `safety_build.devices`).

Backend `discover_safety_devices(MSCATL_CP2)` does **not** include ESPB*.
Clear/Load now wipe and replace inventory from current-machine evidence.

## Parity (clean RUN)

| Metric | Count |
| --- | ---: |
| Classified current-machine I/O | 10 |
| Surfaced inventory (incl. T_ aliases) | 14 |
| Missing | 0 |
| Foreign/stale | **0** |

By kind (discover): ESTOP 3 · ESR 2 · MCR 4 · ESLS 5

## Owner states (Hardware I/O)

| State | Count |
| --- | ---: |
| ASSIGNED | 221 |
| UNRESOLVED OWNER | **0** |
| UNUSED_MAPPED (true unclaimed capacity) | 51 |
| PROVEN_SPARE token | 0 |

## Build

- L5X: `exports/diagnostics/mscatl_cp2_field_followup/MSCATL_CP2.L5X`
- `io_map_mapped` 221 (141 specialized + 80 generic BOOL)
- `lost_claims` 0
- `generation_assertions.ok` true
- **No** `INT_2ES2_1ESR1.I.ES_OK` dangling reference

## Transport

Raw Geometry / Readable Schematic toggle (display-only offsets; merge stroke ~10px).
