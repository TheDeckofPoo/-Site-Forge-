# Permanent Integration Qualification Gate

Future changes touching **I/O**, **Safety**, **Transportation**, **workbook state**,
or **Autogen** must not be accepted unless **all** of the following still pass on
the **same SHA**:

## Mandatory gates

```
1. python exports/delivery_gate_20261002/run_overnight_rc_qualification.py
2. python exports/delivery_gate_20261002/run_pick_golden_gate.py
3. python exports/delivery_gate_20261002/run_virgin_second_site_gate.py
4. python exports/delivery_gate_20261002/run_orl_ac3_safety_gate.py
5. python -m unittest tests.acceptance.test_l5x_acceptance_auditor -q
6. python -m unittest tests.acceptance.test_overnight_rc_qualification_gates -q
7. python -m unittest tests.acceptance.test_io_source_conservation_gate -q
8. python -m pytest tests/acceptance/test_integration_qualification_gate.py -q
9. python -m pytest tests/safety/test_ori110_safety_configuration_gate.py -q
```

**I/O source conservation (mandatory):** Coverage denominator is
`RUN_IO_SOURCE_LEDGER` (upstream RUN evidence), never `physical_io_map.csv`
row count alone. Require `silently_missing == 0`. Incomplete ledger →
`NOT_PROVEN` / `REVIEW_REQUIRED`, never false 100%. Auditor emits
`IO:SOURCE_CONSERVATION_FAILURE:<device>` and blocks CURRENT promotion.

**Production repair rule:** AUDIT_FAIL → diagnose → modify model/library/parser/generator →
REGENERATE complete L5X → re-audit. Direct staging-L5X mutation is forbidden on real builds
(fixture-only inside auditor tests / autonomous_repair_proof harness).

ORI-111 L5X acceptance auditor (EXPECTED→STAGING→AUDIT→CURRENT) is mandatory.
Only `AUDIT_PASS` may promote to `exports/current`.

| # | Fixture | Contract |
|---|---------|----------|
| 1 | **MSCRENOPICK golden** | I/O + Transportation + Safety + populated ES Main/Safe_Logic/Safe_PI + explained core routines + BUILD_ISSUES + L5X |
| 2 | **TFCP1 virgin second-site** | Clear→restart→virgin load; retain I/O/Transport/Safety; **zero** prior-site (MSCRENO) residue |
| 3 | **ORL_AC3 Safety** | Engineer-assigned Safety still emits populated Main_Routine + Safe_Logic + Safe_PI |

## Hard-fail criteria (acceptance tests)

Gates / acceptance coverage must **FAIL** on:

- I/O regression
- RUN physical device present in source evidence but silently missing before `physical_io_map.csv`
- CSV-only "100%" when source ledger is incomplete (`NOT_PROVEN`)
- Missing Transportation programs (Area Slow/Fast/L1/L2 + System/Sys/PLC_Fast/ES/IO_MAP)
- Blank/placeholder core routines without REVIEW/UNSUPPORTED/WITHHELD/… explanation
- Missing Safe_Logic / Safe_PI / Main_Routine (when Safety READY)
- Malformed / open / blank Logix instruction operands
- Missing / unnamed referenced tags
- Foreign-site residue on virgin builds
- Missing BUILD_ISSUES explanation
- Missing output L5X under `exports/current/`

## Frozen delivery SHA

See `FINAL_SHA.txt` after a successful qualification run.

ORI-110 / integration baseline: `2c583c39724eb955f2ce5a487c739f02a29cec5e`
