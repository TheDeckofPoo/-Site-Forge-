# SiteModel V2

Canonical discovered site shape used by knowledge-driven enrichment, editors, and validators.

**Source firewall:** RUN facts + engineer overrides + FPC training semantics + generic L5X libraries. Finished / gold PLC exports are validation oracles only — never generation input.

Schema marker: `schema_version = "2.0"` (V1 consumers ignore unknown keys).

---

## Shape (concise)

| Bucket | Role |
|--------|------|
| `equipment` / `motors` / `vfds` (`drives`) / `photoeyes` / `encoders` | First-class devices |
| `areas` | Engineering Area groupings (renameable) |
| `operational_groups` | **Distinct** zone catalogs — never conflated with Area |
| `relationships[]` | Typed edges with provenance + confidence |
| `pe_roles` (on photoeyes) | Knowledge+RUN roles (`JAM`, `FULL`, `FULL_JAM`, …) |
| `motor_chains[]` | Ordered chains from `mtrchain*` relationships |
| `editors` | Auto-populated Transport / Sawtooth / Sorter V2 payloads |
| `inclusion_why` / `inclusion_reasons` | Why INCLUDED / AVAILABLE / EXCLUDED |
| `superseded_candidates[]` | Overlay / historical supersession signals |
| `decision_traces[]` | Rule traceability after enrichment |
| `communications` / `tracking` | Msg/WCS inventory (generation mostly NOT_SUPPORTED) |
| `ui_status_summary` | Compact TRANSPORT / SAWTOOTH / SORTER / PE counts |

### Operational groups (distinct)

```text
operational_groups
  engineering_areas[]   # mirror of areas as a group type
  estop_zones[]
  startstop_zones[]
  jam_zones[]
  full_groups[]
  sorter_zones[]
```

Area rename propagates to equipment `area_id` only. Jam / EStop / StartStop / Full / Sorter zones keep their own identities.

### Relationships provenance

Each edge carries `kind`, `provenance` (`RUN_EXPLICIT` | `RUN_DERIVED` | `ENGINEER_CONFIGURED` | …), `confidence`, `evidence[]`, and optional `source_table`. Discovery prefers explicit RUN links over naming similarity.

### PE roles

`enrich_pe_roles` sets `pe_roles[]`, `pe_role_evidence[]`, and legacy `role`. Table evidence (Jamcheck / Fullline / Fulljam / SawLane) beats suffix; suffix is supporting only.

### Motor chains

`build_motor_chains` materializes `motor_chains[].order` / `members` / optional `aux` / `stop_zone` from `mtrchain`, `mtrchain_aux`, `mtrchain_stop_zone` relationships.

### Editors V2

`editors.transport` / `editors.sawtooth` / `editors.sorter` auto-populate from the enriched model. Unknowns stay **CONFIGURATION_REQUIRED**; unsupported sorter/WCS leaves stay **NOT_SUPPORTED** / **GENERATION_NOT_SUPPORTED** — no gold `Sorter_Track` clone.

### Inclusion why

Per-object `inclusion_why` records positive evidence, missing proof, and notes (including historical/stale and engineer exclusion).

### Supersession

`superseded_candidates[]` marks overlay winners vs historical losers. Validator V2 warns when an INCLUDED object is also a `SUPERSEDED_CANDIDATE`.

### Reimport change kinds

`change_report` emits legacy added/removed/changed_inclusion plus V2 events:

`NEW` · `REMOVED_FROM_RUN` · `CHANGED_IO` · `CHANGED_RELATIONSHIP` · `CHANGED_ACTIVITY` · `CHANGED_GEOMETRY`

---

## Related

- `docs/RUN_DISCOVERY_MODEL.md` — V1 canonical discovery contract
- `docs/SOURCE_OF_TRUTH_POLICY.md` — generation vs validation firewall
- `docs/INTEGRATION_READINESS.md` — promote-or-not status for this pass
- `tools/scripts/fortna_knowledge_enrich.py` — enrichment entrypoint
