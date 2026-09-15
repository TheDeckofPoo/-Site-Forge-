# PLC2 Merge Pipeline Diagnostic

- Generated: `2026-09-15T00:18:04.215555+00:00`
- Discovery: `C:\dev\worktree\FortnaPlus\exports\plc2-merge-discovery\blind_report.json`
- Discovery counts: proven=4 candidate=0 unresolved=0 total=4
- Workbook: `C:\dev\worktree\FortnaPlus\workspace\autogen_workbook.json` (merges_2to1=0)
- L5X: `C:\dev\worktree\FortnaPlus\exports\current\ORNCCP2_2026_09_14_1948.L5X` (Merge_2to1 call sites=1)

## Why merges get dropped (code filters)

- transport_graph.analyze: topology merges require asMerge|mergeConfirmed AND >=2 inbound wires
- transport_graph.analyze: conv_merge palette nodes always count; non-merge nodes need the flag
- transport_graph.to_autogen_merges_2to1: emits all lane counts; lanes>2 kept as config-only
- transport_graph.apply: transport_build_graph merges dropped when discharge not in graph tag_area
- fortna_autogen emit: only merges_2to1 from workbook; lanes>2 skipped (codegen TBD)
- fortna_autogen emit: merge must resolve a name (name|merge|discharge) and area match (or blank area)
- discovery is frozen evidence only — not auto-seeded into workbook/Apply

## Diagnostic table

| id | class | type | main | induct | sections | downstream | area | evidence | in_wb? | in_l5x? | omit_reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MERGE_406_3-1 | PROVEN | Merge_2to1 | P404 | P138 | P404/P138/— | P406 | — | 22 facts: mergeboss, mergeinputs_presense, merg… | no | yes | — |
| MERGE_316_SPUR | PROVEN | Merge_2to1 | P136_P1 | P312 | P136_P1/P312/P316 | P136_P2 | — | 23 facts: mergeboss, mergeinputs_presense, merg… | no | no | not_in_workbook (merges_2to1 empty — discovery not auto-applied; transport_grap… |
| MERGE_400_2-1 | PROVEN | Merge_2to1 | P242 | P150_P2 | P242/P150_P2/— | P400 | — | 23 facts: mergeboss, mergeinputs_presense, merg… | no | no | not_in_workbook (merges_2to1 empty — discovery not auto-applied; transport_grap… |
| MERGE_324_SPUR | PROVEN | Merge_2to1 | P150_P1 | P320 | P150_P1/P320/P324 | P150_P2 | — | 23 facts: mergeboss, mergeinputs_presense, merg… | no | no | not_in_workbook (merges_2to1 empty — discovery not auto-applied; transport_grap… |

## L5X call sites

- `P406_Merge`: P404 / P138 → P406

## Summary

- Discovered merges: **4** (PROVEN=4)
- In workbook: **0**
- In L5X: **1**
- With omit_reason: **3**
