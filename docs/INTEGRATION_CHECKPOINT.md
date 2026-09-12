# Site Forge — Integration Checkpoint

**Branch:** `feature/site-forge-integration-checkpoint`  
**Do NOT merge to main automatically** — prepare for review only.

---

## Lineage

| Ref | SHA | Notes |
|-----|-----|--------|
| site-forge/main (stale) | `e42d0e17782a` | End Of Day Push 08/17 |
| Integration base (pre-checkpoint docs) | `1de03cdfb104` | Tip of `feature/cp4-compiler-pass2` |
| Integration HEAD | `3b253e51a242` | This checkpoint: README/UX/layout/legacy research |
| Merge-base(main, tip) | `e42d0e17782a` | Tip contains main as ancestor |

### Ancestry (tip contains earlier accepted work)

| Branch | Contained in tip? |
|--------|-------------------|
| `feature/transport-ux-pass2-stabilization` | YES |
| `feature/auto-build-physical-layout-from-run` | YES |
| `feature/source-truth-run-audit` | YES |
| `feature/run-site-model-discovery` | YES |
| `feature/cp2-completion-gate` | YES |
| `feature/cp4-blind-discovery` | YES |
| `feature/cp4-compiler-pass1` | YES |
| `feature/cp4-compiler-pass2` | YES (immediate parent) |

No duplicate cherry-picks — linear first-parent ancestry stacks the work.

### Commit ancestry summary (newest → older)

```
3b253e51a242  feature/site-forge-integration-checkpoint  (this checkpoint)
  └─ 1de03cd  CP4 Pass 2 ownership + Sawtooth param + UX simplicity
       └─ 7f05fec  CP4 Pass1 self-audit 76vs80 + Sawtooth symbols
            └─ d77716d  CP4 Compiler Pass 1 candidate generation
                 └─ 491df25  Freeze CP2 PE/Area + CP4 blind discovery
                      └─ … transport / geometry / source-truth …
                           └─ e42d0e1  site-forge/main
```

---

## Tests run (this checkpoint)

| Suite | Result |
|-------|--------|
| `test_cp4_compiler_pass2.py` | PASS |
| `test_cp4_discovery_no_leakage.py` | PASS |
| `test_cp2_completion_gate_artifacts.py` | PASS |
| `test_transport_physical_presentation.py` | PASS |
| `test_fortna_physical_geometry.py` | PASS |
| `test_display_layout_offsets.py` | PASS |
| `test_source_truth_no_leakage.py` | PASS |
| `test_auto_build_physical_layout.py` | PASS (35 placed after identity fix) |
| `fortna_layout_overlap_research.py` | Ran → `exports/layout-research/` |

CP4 Pass 2 preserved: **76/76** frozen discovery realization, 13 VFD bases, shared VFD relationships, 2 encoders, 5 sawtooth lanes, explicit lane PE/VFD — no finished PLC4 generation input, no silent Tracking/WCS generation.

---

## Known limitations

- `site-forge/main` is stale; merge needs human review (large PR).
- Display lane separation / merge fan / mate nudge are **presentation-only** (`display_dx`/`display_dy`); raw RUN coords untouched.
- Sawtooth Pass 2 uses explicit parameter map; some pack symbols may still need engineer config.
- Tracking / WCS generation remains **NOT YET SUPPORTED**.
- Legacy layout decoder beyond `Conveyor.asc` is scaffold until additional formats confirmed (`docs/LEGACY_LAYOUT_DATA_RESEARCH.md`).
- Generated `.L5X` under `exports/` remain gitignored.
- Connectivity mate nudge only applies to trustworthy physical wires with small gaps; it never invents PLC downstream.

---

## Obsolete / superseded branches

Close separate PRs that only duplicate ancestors of this checkpoint:

- `feature/cp4-compiler-pass2` (immediate parent)
- `feature/cp4-compiler-pass1`
- `feature/cp4-blind-discovery`
- `feature/cp2-completion-gate`
- Earlier geometry / transport / source-truth feature branches

---

## Recommendation for merging to main

1. Review this checkpoint PR against `site-forge/main`.
2. Confirm CP2 workflow + CP4 Pass 2 (76/76) on a clean machine.
3. Merge **only** this checkpoint — do not stack obsolete PRs.
4. Archive/close superseded feature PRs after merge.

**Do not** use finished PLC2/PLC4 as generation input during merge validation.
**Do not** merge automatically — human review required.
