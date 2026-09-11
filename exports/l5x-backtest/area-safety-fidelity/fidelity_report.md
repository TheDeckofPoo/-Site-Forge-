# Autogen Area/Safety Fidelity — Separated Scores

## REFERENCE-SEEDED FIDELITY TEST (plumbing only)

> **Not** the real Greensboro end-to-end accuracy score.
> Workbook was temporarily populated from finished Fast_Conv area/safety args
> to prove Autogen preserves supplied metadata.

Plumbing fidelity:
- Area **75 / 75**
- Safety **75 / 75**

## ACTUAL WORKFLOW BACKTEST (truthful baseline)

> Uses `workspace/active/RUN` + `workspace/autogen_workbook.json` as Site Forge left them.
> Finished Greensboro L5X is used **only** as the comparator reference.
> The workbook is never populated or repaired from the finished L5X.

Actual workflow:
- Conveyor coverage **18 / 57** (31.6%)
- Area accuracy **0 / 18** (0.0%)
- Safety accuracy **0 / 18** (0.0%)
- Downstream accuracy **4 / 18** (22.2%)

Generated L5X: `C:\dev\worktree\FortnaPlus\exports\l5x-backtest\area-safety-fidelity\actual_workflow_generated\OReillyGreensboro_ORNCCP2.L5X`
Workbook: `C:\dev\worktree\FortnaPlus\workspace\autogen_workbook.json`

