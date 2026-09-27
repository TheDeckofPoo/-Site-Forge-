# Relay POC #1

## Baseline

Site Forge SHA: `69ef524e026f7d0e9bef69f356eb87378d7b4f95`

## Scope

| Set | Count |
|-----|------:|
| ULTAPICK | 5 |
| Held-out ORINDYAC3 | 5 |
| **Total** | **10** |

## Recorded result

| Metric | Value |
|--------|------:|
| Site Forge physical interpretation matches | 10 |
| Mismatches | 0 |
| Unsupported confident claims | 0 |
| Cross-panel violations | 0 |
| Provenance present for every claim | yes |

## Important caveat

**Agreement with Site Forge ≠ independent proof.**

Both systems may share the same inference path. Matching Site Forge does not
alone prove ground truth.

## Open questions

- 1734 POINT I/O byte / slot / `Data[]` convention
- 1794 FLEX I/O byte / slot / `Data[]` convention
- Appropriate PROVEN vs DERIVED threshold for rendered Logix addresses

## Notes

- Finished PLC was not used as discovery parent.
- Site-specific endpoints were not promoted into handbooks.
