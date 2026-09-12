# Studio 5000 Manual Validation Checklist

Curtis: import each L5X in Studio 5000 and record results.

Do **not** treat static precheck as PASS.

## Candidates

- `ORNCCP2_knowledge_driven_candidate.L5X`
- `ORNCCP4_knowledge_driven_candidate.L5X`
- `ORNCCP5_candidate_v2.L5X`

## Expected unsupported warnings

- Full Sorter_Track / divert trigger may be absent (PARTIAL / NOT SUPPORTED)
- WCS program generation NOT SUPPORTED
- Safety zone logic blocked until engineer confirms ES membership
- Single provisional Engineering Area until engineer splits/renames

## Subsystem UI status (reference)

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

## Results (Curtis fills in)

| Candidate | Import | Opens | Notes |
|-----------|:------:|:-----:|-------|
| CP2 |  |  |  |
| CP4 |  |  |  |
| CP5 |  |  |  |
