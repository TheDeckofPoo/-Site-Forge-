# Area Discovery Research Notes

**Branch:** `feature/cp5-gap-closure`  
**Scope:** How Engineering Areas might be inferred from RUN — research only.  
**Not targets:** Finished PLC Area program names (e.g. Redroom) must never be copied into the compiler or SiteModel as generation defaults.

---

## Current fact

RUN has **no reliable Area table** for Engineering Area membership.

When Area cannot be proven from RUN:

1. Emit default **`Area_1`** (controller-scoped label such as `ORNCCP5_Area` is an engineer rename choice, not RUN-derived).
2. Mark provenance **`ENGINEER_CONFIGURED_REQUIRED`**.
3. Place INCLUDED equipment under that default.
4. Do **not** claim the default came from RUN.

Operational groups (E-stop, StartStop, Jam, Full, Sorter host zones) are **not** Engineering Areas and must stay in their own catalogs.

---

## Candidate evidence sources (unproven until linked)

Each candidate Area proposal must cite RUN evidence. Unproven proposals stay engineer-required.

| Candidate source | What it might suggest | Caveat |
|------------------|-----------------------|--------|
| `StartStopZones` | Island / ownership clusters that sometimes align with Area programs | StartStop ≠ Area; many-to-one / many-to-many possible |
| `Jamzones` `Zone Owner` | Process / owner name near Area boundaries | Owner may be process, machine, or free text — not Area |
| `Machine` / `Process` | Controller and process identity | Machine scope ≠ Engineering Area |
| Control stations | Local HMI/station grouping | Station geography ≠ Area program split |
| E-stop ownership (`EStop`) | Safety circuit membership | Safety zones must not be conflated with Area |
| `Mtrchain` `Stop Zone` | Motor-chain → StartStop linkage | Useful for chains; weak Area proof alone |
| Sorter grouping (`Sorters`, `SrtZoneLane`, host zones) | Sortation host clusters | Sorter zones are tracking/host concepts, not Area |
| `PROJECT` tables / overlays | Site-specific extras under `PROJECT/` | Schema varies; treat as optional evidence only |

None of these alone is accepted as a production Area membership rule until a generic, multi-site proof exists.

---

## Evidence rule

For every candidate Area:

- Attach RUN table + row / field evidence on the SiteModel object.
- Record confidence (`HIGH` / `MEDIUM` / `LOW` / `UNKNOWN`).
- If membership is unproven → keep **engineer-required** default; do not auto-split equipment into named Areas.
- Engineer rename / assign in the editor remains the supported path.

---

## Forbidden

- Copying finished PLC Area names (Redroom, ModuleB, ShippingSorter, …) into discovery or Autogen as targets.
- Using answer-sheet Area counts or program lists as generation rules.
- Silently renaming Jam / E-Stop / StartStop zones when Area renames (`fortna_area_ops` contract).
- Treating P-number ranges or Greensboro layout lore as Area discovery.

---

## Related

- `docs/RUN_DISCOVERY_MODEL.md` — default `Area_1`
- `docs/FORTNAPLUS_RELATIONSHIP_MODEL.md` — EngineeringArea vs operational zones
- `docs/SOURCE_OF_TRUTH_POLICY.md` — validation barrier
- `docs/DISCOVERY_TO_COMPILER_CONTRACT.md` — Area required for conveyor emit
