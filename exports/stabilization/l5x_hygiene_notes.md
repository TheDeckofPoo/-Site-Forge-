# PL-9 — Generated Output Hygiene Notes

Inspect standard architecture only — do not chase finished-PLC tag-count parity.

## Checklist

- [ ] Expected program packs exist (Area Fast/Slow/L1/L2, Sys, System, IO_MAP, ES)
- [ ] Tasks schedule expected programs (incl. `P01_Safety_20ms` → ES)
- [ ] No duplicate IO_MAP OTE writers (preflight)
- [ ] No orphan Programs unscheduled without reason
- [ ] Safety shell not marked READY / COMMISSIONING READY
- [ ] Area packs match ACTIVE+INCLUDED areas only (see `area_inclusion_report.md`)

## Candidate lettered collisions (report only)

| Pair | Notes |
|------|-------|
| M220 / M220A (+_AUX) | Confirmed historical collision; fixed in punch-list |
| M136 / P136_P1 | Assembly PE/SSV pattern — REVIEW if bare AUX appears |
| M150 / P150_P1 / P150A | Same family |
| P130 vs P130A–E | Letter sections; usually no bare M130_AUX |

Do not auto-change those records in this build.
