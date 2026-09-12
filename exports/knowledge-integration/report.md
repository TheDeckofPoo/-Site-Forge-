# Knowledge-Driven Compiler Integration Report

Generated: `2026-09-12T19:33:20.782178+00:00`

Source firewall: CURRENT RUN + engineer overrides + FPC docs + generic libraries.
Finished PLC2/PLC4 were **not** used for generation or discovery gap-fill.

## Document inventory (deterministic)

- Documents: **101**
- CRITICAL: **7**
- HIGH: **11**
- Deep review: **18**

## ORNCCP2

```json
{
  "TRANSPORT": {
    "Included": 63,
    "Available": 0,
    "Excluded": 0,
    "relationships_need_review": 220
  },
  "SAWTOOTH": {
    "detected": 0,
    "lanes": 0,
    "configuration_resolved_pct": 0.0,
    "engineer_decisions": 0
  },
  "SORTER": {
    "detected": 0,
    "configuration_modeled": false,
    "encoder_resolved": false,
    "scan_zones_resolved": false,
    "divert_map_required": true,
    "generation": "none"
  },
  "PE": {
    "auto_resolved": 22,
    "engineer_required": 22
  }
}
```

- PE auto-resolved: 22
- Motor chains: 176

## ORNCCP4

```json
{
  "TRANSPORT": {
    "Included": 76,
    "Available": 0,
    "Excluded": 0,
    "relationships_need_review": 253
  },
  "SAWTOOTH": {
    "detected": 1,
    "lanes": 5,
    "configuration_resolved_pct": 75.0,
    "engineer_decisions": 5
  },
  "SORTER": {
    "detected": 1,
    "configuration_modeled": true,
    "encoder_resolved": true,
    "scan_zones_resolved": true,
    "divert_map_required": true,
    "generation": "partial"
  },
  "PE": {
    "auto_resolved": 32,
    "engineer_required": 23
  }
}
```

- Sawtooth detected: True
- Sorter detected: True

## Validation

- CP2 ok: `True`
- CP4 ok: `True`

## Ambiguity

- CP2 ambiguity reduced: `True`
- CP4 ambiguity reduced: `True`
