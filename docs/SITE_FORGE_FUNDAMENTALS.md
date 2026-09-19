# Site Forge Fundamentals

**Source:** `Site_Forge_Fundamentals_and_Continuity_Handoff_v1.pdf` (v1.0, 2026-09-19)  
**Status:** Architectural law — executable enforcement lives under `tests/fundamentals/` and compiler gates.  
**Primary principle:** Site Forge is a **compiler**, not a PLC copier.

> GENERALIZE THE RULE, NOT THE SITE.  
> Do not make Site Forge better at fixing one known site. Make it better at understanding any Fortna site.

---

## Non-negotiable rules (executable where marked)

| # | Rule | Executable enforcement |
|---|------|------------------------|
| 1 | **Two-Way Door** — prefer reversible decisions | Process / UX |
| 2 | **Erased Means Erased** — Clear/new identity purges site-specific state | `ProjectIdentity` + `resetProjectScopedState` + virgin/cross-site tests |
| 3 | **No Ghost Equipment** — no evidence ⇒ no site-specific instance | Template-slot prune + final-artifact closure |
| 4 | **Every Site Object Has Lineage** (“birth certificate”) | `MachineScopedRunView` + final lineage assert |
| 5 | **Library Is Not Site State** | Pack placeholders never survive without model rows |
| 6 | **Current Site Owns the Compiler** | Workbook preserve gated by `same_project()` |
| 7 | **Evidence Beats Convenience** | PROVEN / DERIVED / ENGINEER_ASSIGNED / REVIEW_REQUIRED / UNKNOWN |
| 8 | **Finished PLC Is Oracle Only** | Qualification never opens reference L5X during discovery/generation |
| 9 | **Subsystem Isolation** | Transport cannot wipe Safety; Sorter cannot rewrite Safety |
| 10 | **Fail Safe, Not Fail Convenient** | Default/Unassigned Safety never operational |
| 11 | **FOUND ≠ INCLUDED ≠ GENERATED** | Qualification + compile hub |
| 12 | **Same Inputs Same Output** | Deterministic handoff + qualification parity |
| 13 | **Final Artifact Qualification** | Assembled L5X closure scan |
| 14 | **Virgin Site Isolation** | Clear A → load B ⇒ zero A objects |
| 15 | **REVIEW ≠ PASS** | Qualification status policy |
| 16 | **Generalize the Rule Not the Site** | No production site-name conditionals to match a gold PLC |
| 17 | **Physical Geometry Immutable** | Curve anchors never stretched |
| 18 | **Human Intent Survives Pipeline** | Apply → save → reload → Autogen |
| 19 | **Dependencies Explicit** | Programs emitted because canonical model requires them |
| 20 | **Curtis Verifies Engineering** | Qualification absorbs software regression |

---

## Project identity contract

```text
project_key     = stable project/controller identity
run_fingerprint = revision of that RUN content
machine         = target Machinename from project.cfg
```

- **Same project_key + same machine** → engineer decisions may reconcile against new RUN evidence.
- **Different project_key or machine** → no reuse of site-specific state.
- **Explicit Clear/Erase** → purge active site state regardless of identity.

See `tools/scripts/fortna_project_identity.py`.

---

## Machine scope contract

For a Conveyor (or similar) row with **explicit non-empty Machine_Name**:

```text
if explicit_machine != target_machine:
    EXCLUDE
```

No name matching, numeric-prefix family, workbook stub, or template slot may override an explicit foreign `Machine_Name`.

`Machine_Name=N/A` requires a real relationship into the target `MachineClosure` (I/O word, motor chain, PE, topology, or engineer assignment rooted in the current project). **P-number letter family alone is not enough.**

See `tools/scripts/fortna_machine_scoped_run.py`.

---

## Checkpoint report requirement

Major checkpoint / qualification reports must include a short **Fundamentals compliance** section listing which rules were exercised and any REVIEW/UNKNOWN that remain.
