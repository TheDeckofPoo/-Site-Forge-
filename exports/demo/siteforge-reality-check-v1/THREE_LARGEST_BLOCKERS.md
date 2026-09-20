# Three largest blockers

## 1. Physical I/O unbound families on hard sites

- subsystem: physical I/O
- gap: FISHER_CC9 Pass1: 97 / 971 claims PHYSICAL_RESOLUTION_FAILURE (95 in one UNBOUND structural family) despite conservation PASS and strong PROVEN majority.
- why blocks: A trustworthy PLC cannot be emitted while nearly 10% of physical claims lack deterministic binding; UNKNOWN/REVIEW must not be silently assigned.
- next: Review Pass2 CANDIDATE_RULE; run corpus shadow; implement deterministic rule only after promotion gate — do not site-special-case Fisher.
- evidence: `exports/demo/siteforge-reality-check-v1/HARD_BLIND/PASS1/unresolved_cluster_summary.json`

## 2. Virgin Transport/merge handoff gaps

- subsystem: Transportation / compiler qualification
- gap: MSCATL_CP3 virgin qualify FAIL: proven merge P3012A missing from generated L5X present set (merge check FAIL) even with Hardware/I-O PASS.
- why blocks: Hardware readiness is necessary but not sufficient; merge/transport omissions produce incorrect or incomplete PLC programs.
- next: Dedicated virgin merge presence / transport handoff fidelity task using qualification FAIL evidence — do not greenwash Demo A.
- evidence: `exports/demo/siteforge-reality-check-v1/MSCATL_CP3/qualification_virgin/qualification_report.json`

## 3. Safety + cross-subsystem compile readiness

- subsystem: Safety / canonical model / compiler
- gap: Virgin Safety remains REVIEW (no invented membership); final artifact closure REVIEW (ES_NO_SAFE_ROUTINES); overall NOT READY TO COMPILE for one-click trustworthy build.
- why blocks: Without honest Safety membership + handoff into Autogen, compile either invents unsafe logic or emits an incomplete fail-safe shell.
- next: Engineer Safety Apply + membership persistence / handoff hardening; keep virgin no-invent law.
- evidence: `exports/demo/siteforge-reality-check-v1/MSCATL_CP3/build_readiness.json`

**Recommended next task:** Prioritize blocker #1 candidate review + shadow for the Fisher UNBOUND family OR blocker #2 virgin merge presence — Curtis/Gilfoyle choose; do not start both blindly.
