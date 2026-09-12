# Knowledge-Driven Compiler — Integration Readiness

**Branch:** `feature/knowledge-driven-compiler`  
**Do NOT merge to main** from this document. Architecture review decides.

---

## Lineage

```text
cp4-sawtooth-semantics
  → run-driven-workspace
    → fortnaplus-knowledge-layer
      → knowledge-driven-compiler   (this branch)
```

Artifacts under `exports/knowledge-integration/` record the latest local integration pass
(discovery → knowledge enrich → editors → validator V2 → candidate L5X).
Finished PLC2/PLC4 were **not** used as generation input.

---

## Is lineage safe to promote to an integration checkpoint?

**Yes — as an integration review checkpoint. Not as a merge-to-main.**

Safe to promote for architecture review because:

- Source firewall is intact (RUN + overrides + FPC docs + generic libraries).
- `fortna_knowledge.py` executes table/PE/zone semantics (KB is no longer docs-only).
- SiteModel V2 enrichment, PE roles, motor chains, distinct operational groups, and editor V2 auto-populate are implemented and unit-tested.
- Area rename → model-driven L5X snippet generation has a deterministic test.
- Blind genericity fixtures assert no Greensboro / ORNCCP / PLC2 / PLC4 leakage in synthetic enrichment.
- Validator V2 reports `ok: true` for both live CP2 and CP4 packs after fixing false-positive word-only IO collisions (CONFIGURATION_REQUIRED + WARNING remain — expected).
- Integration `summary.json` has `"ok": true`.

Still **not** merge-ready:

- Tracking / WCS / divert AOI / full Sorter_Track generation remain unsupported.
- Live models still carry many CONFIGURATION_REQUIRED gaps (e.g. missing motors on some INCLUDED conveyors).
- UI does not yet render `ui_status_summary` cards end-to-end.
- AVAILABLE bucket counts remain low on current activity scoring (many rows land INCLUDED); inclusion_why is stored for engineer review.

Treat this branch as **integration-candidate**, awaiting architecture review. **Do not merge main.**

---

## CP2 / CP4 regression status

| Scope | Status |
|-------|--------|
| CP2 rediscovery (knowledge-driven) | Green path in `exports/run-discovery-cp2/` + integration pack |
| CP2 TRANSPORT | 63 Included; relationships still need review |
| CP2 PE | 22 auto-resolved / 22 engineer-required; prior CFG roles resolved where docs+RUN prove |
| CP2 motor chains | 176 chains materialized |
| CP2 validation V2 | `ok: true` (CONFIGURATION_REQUIRED + WARNING only) |
| CP2 candidate L5X | Generated; XML parses; Studio 5000 download **not** claimed |
| CP4 rediscovery (knowledge-driven) | Green path in `exports/run-discovery/` + integration pack |
| CP4 TRANSPORT | 76 Included |
| CP4 SAWTOOTH | detected; 5 lanes; ~75% configuration resolved; capability matrix honest |
| CP4 SORTER | detected; modeled; divert map required; generation partial / proven leaves only |
| CP4 PE | 32 auto-resolved / 23 engineer-required |
| CP4 validation V2 | `ok: true` |
| CP4 candidate L5X | Generated; XML parses; Studio 5000 download **not** claimed |
| CP4 discovery no-leakage | PASS |
| Source-of-truth no-leakage | PASS |
| Knowledge layer unit tests | PASS |
| Knowledge-driven compiler tests | PASS |
| Blind genericity fixtures | PASS |
| Area rename → L5X | PASS |
| RUN-driven workspace tests | PASS |

Earlier CP4 Pass 2 compiler freeze (`exports/cp4-pass2/`) remains a useful baseline; re-run those suites before claiming full compiler regression PASS on every tip.

---

## Transport / Sawtooth / Sorter status

| Subsystem | Status |
|-----------|--------|
| **Transport** | Auto-populated editor V2 from SiteModel; PE roles, motor chains, zones, inclusion why. Demo freeze lineage still applies. |
| **Sawtooth** | Detected from RUN; editor V2 auto-populates lanes/PE/VFD/encoder; unknowns stay CONFIGURATION REQUIRED; no invented gold values. |
| **Sorter** | Discovery + editor V2 modeled with STATIC/RUNTIME/COMM/ENGINEER layers. Generation leaves for WCS / divert / tracking stay **NOT_SUPPORTED** or **CONFIGURATION_REQUIRED**. No gold `Sorter_Track` clone. |

---

## UI smoke-test status

No automated UI smoke suite claimed on this branch. Dashboard does not yet render `site_model.ui_status_summary` cards end-to-end (see `docs/UI_STATUS_SUMMARY.md`). Manual Electron launch smoke is **unverified** here — run locally.

---

## README accuracy

README describes Import → Discover → Review → Build and completed knowledge-executable capabilities (SiteModel V2, Area rename, independent zones, PE roles, motor chains, editors V2, sorter proven leaves only). It is **not** a development diary and does **not** claim merge to main.

---

## Deterministic knowledge metrics

From `exports/knowledge-integration/document_metrics.json`:

| Metric | Count |
|--------|------:|
| Documents | 101 |
| CRITICAL (relevance) | 7 |
| HIGH (relevance) | 11 |
| Deep review true | 18 |
| Deep review false | 83 |

No ranges. Every document carries `document_id`, `canonical_path`, `classification`, `deep_review`.

---

## Known blockers / unsupported behavior

- Tracking / WCS / divert AOI / Sorter_Track generation remain unsupported.
- Sawtooth reservation / collector tracking remain modeled or engineer-required when evidence is incomplete.
- Many INCLUDED conveyors still CONFIGURATION_REQUIRED for motor linkage in validator (engineer review).
- Stale / historical ASC rows must stay AVAILABLE/EXCLUDED — never silently generated.
- Finished PLC paths must never enter generation or discovery gap-fill.
- Area rename must not silently rename Jam / E-Stop / StartStop zones (enforced in `fortna_area_ops`).

---

## Explicit non-claims

- **Do not** claim merge to main.
- **Do not** claim Studio 5000 download validation.
- **Do not** claim full sorter or WCS generation.
- **Do not** claim finished PLC2/4 influenced output.
