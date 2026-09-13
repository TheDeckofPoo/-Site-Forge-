# TRANSPORT AUTOGEN FROZEN PENDING CURTIS ACCEPTANCE

**Status:** ACTIVE freeze  
**Branch:** `feature/plc2-transport-fidelity`  
**Reason:** Curtis cannot perform another full Transportation acceptance check. Preserve the accepted Autogen Transportation compiler and semantic model.

## Frozen (do not change)

Unless required to repair a **hard automated regression** caused directly by other work:

- Configio physical resolver
- IO_MAP semantic resolver
- `ConveyorSectionModel` (`fortna_conveyor_section_model.py`)
- Transport object generation (`*_Conv`, `*_Conv_AOI`, MS/VFD)
- Fast / Slow / L1 / L2 transport generation
- Upstream / downstream compiler semantics
- Conveyor type classification rules
- Physical Auto Build topology / placement algorithm

## Allowed in this freeze window

- Transportation **UI-only** editing (selection, Area metadata, Control Panel grouping, pan/zoom, group move)
- Sawtooth Merge RUN auto-discovery / editor / Apply (separate subsystem)
- Provenance / `exports/current` engineer output path
- Documentation and regression tests that assert freeze boundaries

## Hierarchy reminder

```
PLC / Controller
  ├── Control Panel CP1 / CP2 / CP3   (physical/org metadata)
  └── Areas (engineer-defined logical groups)
```

Control Panel ≠ Area. Neither alters I/O or controller ownership.
