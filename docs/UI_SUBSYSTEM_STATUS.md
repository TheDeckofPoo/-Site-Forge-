# UI Subsystem Status Vocabulary

Compact per-controller labels for dashboard / checklist cards. Produced by integration hardening (`exports/integration-hardening/ui_subsystem_status.json`) and related enrich paths. Do not invent site-constant Area or sorter names as status rules.

---

## Status meanings

| Status | Meaning |
|--------|---------|
| **READY** | Discovery + modeling sufficient; generic generation path emitted (or would emit) without outstanding engineer gates for that subsystem. Still not a Studio download claim. |
| **CONFIGURATION REQUIRED** | Modeled / partially discovered; engineer must supply membership, maps, or overrides before honest emit or before treating logic as complete. |
| **PARTIAL GENERATION** | Some capability leaves generated; others remain CFG or unsupported. Do not show as fully READY. |
| **GENERATION NOT SUPPORTED** | Inventory/model may exist; no complete generic library path — do not emit PLC for this subsystem. |
| **BLOCKED** | A hard gate prevents progress (e.g. Safety zone logic waiting on engineer membership confirmation). Distinct from “we chose not to support yet.” |
| **N/A** | Subsystem not present on this controller (e.g. no sawtooth merges). Absence is correct. |

---

## Example — ORNCCP5 (integration-hardening)

```json
{
  "ORNCCP5": {
    "Transport": "READY",
    "Safety": "CONFIGURATION REQUIRED",
    "Sawtooth": "N/A",
    "Sorter": "PARTIAL GENERATION",
    "WCS": "GENERATION NOT SUPPORTED"
  }
}
```

| Card | Why |
|------|-----|
| Transport READY | Included conveyors / PE / IO candidate path exists; Studio still separate |
| Safety CONFIGURATION REQUIRED | Devices known; Area + ES membership engineer gates (zone logic may show BLOCKED until confirmed) |
| Sawtooth N/A | Zero sawtooth merges on this machine |
| Sorter PARTIAL GENERATION | Encoder / induct / scanner / reason leaves only; divert trigger unsupported |
| WCS GENERATION NOT SUPPORTED | Events inventoriable; no generic WCS PLC emit |

Source: `exports/integration-hardening/ui_subsystem_status.json`. Related count cards: `docs/UI_STATUS_SUMMARY.md`.
