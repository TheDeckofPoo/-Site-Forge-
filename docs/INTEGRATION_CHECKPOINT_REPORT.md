# Integration Checkpoint Report

**Checkpoint label:** `feature/integration-checkpoint-2026-09`  
**Working branch (content):** `feature/activity-classification-closure`  
**Prior integration tip:** `feature/site-forge-integration-checkpoint` (`b7d1326`)  
**Checkpoint SHA:** 4bad70bf0e322b5804ae6c961adb8694e2a24fcb

**Do NOT merge to main** — architecture review only.

---

## Lineage summary

| Ref | Notes |
|-----|--------|
| `main` / `site-forge/main` merge-base | `7dbc425` (stale relative to tip) |
| Integration checkpoint ancestor | `feature/site-forge-integration-checkpoint` @ `b7d1326` |
| Contained stacks | Transport UX/layout, source-truth, RUN SiteModel discovery, CP2 gate, CP4 blind + Pass1/Pass2/Sawtooth, knowledge layer, CP5 blind + gap-closure bridge |
| Activity-closure tip | Branch `feature/activity-classification-closure` (includes classifier + `exports/activity-closure/`) |

Tip contains earlier accepted feature work as first-parent ancestry — do not re-merge obsolete sibling PRs.

---

## Activity closure outcomes

Authoritative counts and audits:

→ **`exports/activity-closure/summary.json`**

Also present under `exports/activity-closure/`:

- Per-machine reclassified SiteModels / classifications (`cp2_*`, `cp4_*`, `cp5_*`)
- `cp5_19_item_audit.json`
- `cp5_bridge_floor_check.json`
- `supersession_audit.json`

Highlights (from `exports/activity-closure/summary.json` / equipment buckets):

| Machine | Equipment INCLUDED | AVAILABLE | EXCLUDED |
|---------|-------------------:|----------:|---------:|
| CP2 | 63 | 0 | 0 |
| CP4 | 76 | 0 | 0 |
| CP5 | 79 | 0 | 0 |

High INCLUDED ratio is supported by positive cross-table evidence (I/O, Mtrchain, jam/full, ownership) — not forced balance. See `high_included_explanation` in per-machine activity JSON.

- Ambiguous-field policy enforced (`single_field_na_deactivation_used: false`)
- CP5 19 unresolved: engineer-required (MISSING_IO_PROOF / scope) — **0 compiler bugs**; N/A alone not used
- CP5 bridge floor preserved (`cp5_bridge_preserved: true`)
- `SUPERSEDED_CANDIDATE` rows audited — never auto-deleted

Model contract: `docs/ACTIVITY_CLASSIFICATION_MODEL.md`.
Regression pack: `exports/integration-checkpoint/regression_report.json`.

---

## CP5 bridge floor preserved

Floor vs actual (from `exports/activity-closure/cp5_bridge_floor_check.json`):

| Metric | Floor | Actual | OK |
|--------|------:|-------:|:--:|
| Conveyors generated | 60 | 60 | YES |
| PE generated | 94 | 94 | YES |
| I/O modules | 61 | 61 | YES |
| I/O map rungs | 368 | 368 | YES |
| Encoders | 5 | 5 | YES |

Any future reduction requires an explicit evidence-based explanation.  
**Do not modify `exports/cp5-blind/`** in this pass.

---

## AGS Script misclassification

GitHub Linguist previously treated FortnaPlus `.asc` plant tables as **AGS Script**.

Addressed in `.gitattributes`:

- `*.asc` / `*.asc.*` → `linguist-detectable=false`
- Training, exports, libraries, and workspace RUN trees marked vendored / generated as appropriate

Policy: `docs/REPOSITORY_ARTIFACT_POLICY.md`.

---

## Safety gates

| Question | Answer |
|----------|--------|
| Safe for architecture review? | **YES** |
| Safe for main merge? | **NO** (conservative) |
| Merge main now? | **Do not merge main** |

Human review required before any promote. Prefer a single integration PR after review — do not stack superseded feature PRs.
