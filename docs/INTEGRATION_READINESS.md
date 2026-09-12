# Knowledge-Driven Compiler — Integration Readiness

**Branch:** `feature/cp5-gap-closure`  
**Do NOT merge to main** from this document. Architecture review decides.

---

## Lineage

```text
cp4-sawtooth-semantics
  → run-driven-workspace
    → fortnaplus-knowledge-layer
      → knowledge-driven-compiler
        → cp5-blind-build
          → cp5-gap-closure   (this branch)
```

| Ref | Role |
|-----|------|
| `feature/knowledge-driven-compiler` | CP2/CP4 knowledge enrich → editors → validator V2 → candidate L5X |
| `feature/cp5-blind-build` | PLC5 (ORNCCP5) blind discovery + frozen candidate under `exports/cp5-blind/` |
| `feature/cp5-gap-closure` | Close blind v1 compiler gaps (full AutogenInput path, no arbitrary conveyor cap); docs contracts |

Finished PLC2/PLC4/PLC5 were **not** used as generation input. Blind freeze artifacts under `exports/cp5-blind/` remain read-only baseline for this branch — do not rewrite them as answer sheets.

---

## Is lineage safe to promote to an integration checkpoint?

**Yes — as an integration review checkpoint. Not as a merge-to-main.**

Safe to review because:

- Source firewall intact (RUN + overrides + FPC docs + generic libraries).
- SiteModel V2 enrichment, PE roles, motor chains, editors V2, validator V2 remain in lineage.
- CP5 blind pack froze discovery + genericity-identical candidate without finished PLC.
- Gap-closure work targets honest AutogenInput (`load_from_run` + SiteModel roles), not answer-sheet fill.

Still **not** merge-ready:

- 19 SiteModel INCLUDED conveyors remain CONFIGURATION_REQUIRED (no controller I/O / word_map ownership proof for Autogen scope).
- Tracking / WCS / divert AOI / full Sorter_Track generation remain unsupported.
- Engineering Area membership still engineer-required (provisional `ORNCCP5_Area` only).
- E-stop taxonomy corrected in reports (90 devices ≠ 90 zones); operational ES zones still thin.
- UI does not yet render `ui_status_summary` cards end-to-end.
- Studio 5000 download validation **not** claimed.

**Do not merge main.**

---

## CP2 / CP4 / CP5 status

| Scope | Status |
|-------|--------|
| CP2 rediscovery (knowledge-driven) | Green path in `exports/run-discovery-cp2/` + knowledge-integration pack |
| CP2 TRANSPORT | Included set modeled; relationships still need review |
| CP2 PE | Mix of auto-resolved + engineer-required; CFG roles where docs+RUN prove |
| CP2 Area / ES | Default / engineer Area path; ES inventory distinct from Area |
| CP2 candidate L5X | Generated historically; XML parses; Studio download **not** claimed |
| CP4 rediscovery | Green path in `exports/run-discovery/` + CP4 packs |
| CP4 TRANSPORT | Frozen discovery realization baseline (~76) still useful |
| CP4 SAWTOOTH | Detected; lanes modeled; unknowns stay CONFIGURATION_REQUIRED; no invented gold values |
| CP4 SORTER | Detected + modeled; divert / tracking / WCS leaves NOT_SUPPORTED or CFG |
| CP4 PE | Auto-resolved + engineer-required mix |
| CP4 validation V2 | `ok: true` on knowledge-integration path |
| CP4 candidate L5X | Generated; XML parses; Studio download **not** claimed |
| CP5 blind discovery | Frozen under `exports/cp5-blind/` — 79 INCLUDED equipment, 5 sorters, 0 sawtooth, Area engineer-required |
| CP5 blind L5X | Frozen candidate: 40 conveyors / 0 PE / 0 IO_MAP (known bridge defect) — **immutable** under `exports/cp5-blind/` |
| CP5 gap-closure v2 | `ORNCCP5_candidate_v2.L5X`: **60** conveyors, **94** PE devices, **81** PE logic rungs, **61** IO modules, **368** IO_MAP rungs, **5** encoders in L5X; frozen baseline preserved |
| Source-of-truth / no-leakage | PASS (builder + Autogen decoy identical); validation firewall test PASS |
| Knowledge / compiler unit tests | PASS on this tip (workspace, CP4 leakage, area rename, knowledge, identity, firewall) |

---

## Transport / Sawtooth / Sorter / IO / PE / Area / WCS

| Subsystem | Status |
|-----------|--------|
| **Transport** | SiteModel + editor V2 auto-populate; PE roles, motor chains, zones, inclusion why. Blind CP5: 79 Included, relationships need review. |
| **Sawtooth** | CP4 path detected/modeled. CP5 blind: **0** sawtooth merges. |
| **Sorter** | Discovery + editor modeled (STATIC/RUNTIME/COMM/ENGINEER). Divert map / tracking / WCS generation **NOT_SUPPORTED**. CP5: 5 sorters detected; generation partial at best. |
| **IO** | `load_from_run` extracts banks / EIP / points. Blind v1 omitted IO from AutogenInput — gap to close. |
| **PE** | Knowledge+RUN roles; many engineer-required. Blind v1 emitted **0** PE devices — gap to close. |
| **Area / ES** | No reliable RUN Area table → `Area_1` engineer-required. ES / StartStop / Jam stay separate. Do not copy finished Area names into compiler. |
| **WCS** | Inventory / communications discovered; PLC generation **NOT_SUPPORTED**. |
| **UI** | `ui_status_summary` produced on enrich; dashboard end-to-end cards **unverified**. |

---

## Regressions / unsupported

| Item | Status |
|------|--------|
| CP2 / CP4 rediscovery packs | Treat as regression baselines; re-run suites before tip-wide PASS claims |
| CP4 Pass 2 freeze (`exports/cp4-pass2/`) | Useful compiler baseline; not automatically re-proven on every tip |
| CP5 blind freeze | Baseline only; gap-closure compares against it without rewriting it |
| Tracking / divert / Sorter_Track / WCS emit | **Unsupported** |
| Behavioral / Studio download validation | **Not claimed** |
| Greensboro answer-sheet constants as generation rules | **Forbidden** |

---

## Known blockers

- Full CP5 AutogenInput (all INCLUDED conveyors + PE + IO) not yet proven on gap-closure tip.
- Many INCLUDED conveyors still CONFIGURATION_REQUIRED for motor / PE wiring.
- Stale / historical ASC rows must stay AVAILABLE/EXCLUDED — never silently generated.
- Finished PLC paths must never enter generation or discovery gap-fill.
- Area rename must not silently rename Jam / E-Stop / StartStop zones.

---

## Explicit non-claims

- **Do not** claim merge to main.
- **Do not** claim Studio 5000 download validation.
- **Do not** claim full sorter or WCS generation.
- **Do not** claim finished PLC2/4/5 influenced output.
- **Do not** claim blind v1 L5X realized all 79 conveyors or PE/IO (it did not).

---

## Related contracts

- `docs/DISCOVERY_TO_COMPILER_CONTRACT.md`
- `docs/AREA_DISCOVERY_RESEARCH.md`
- `docs/TASK_PROGRAM_ARCHITECTURE.md`
- `docs/SOURCE_OF_TRUTH_POLICY.md`
- `docs/CP5_BLIND_DISCOVERY.md`
