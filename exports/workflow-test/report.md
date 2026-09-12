# RUN-driven workspace foundation — acceptance

Generated: 2026-09-12T17:06:35.202598+00:00

## Result: FOUNDATION PASS

### Discovery counts

| Metric | CP4 (ORNCCP4) | CP2 (ORNCCP2) |
|--------|--------------:|--------------:|
| Equipment INCLUDED | 76 | 63 |
| Transport nodes | 72 | 59 |
| Transport edges | 40 | 28 |
| Sawtooth merges | 1 | 0 |
| Sawtooth lanes | 5 | 0 |
| VFDs | 13 | 0 |
| Encoders | 2 | 0 |
| Sorters (stub) | 2 | 0 |
| Areas | 1 (Area_1 default) | 1 (Area_1 default) |

### Gate checks

- PASS: `site_model_shape`
- PASS: `table_precedence`
- PASS: `activity_buckets`
- PASS: `cp4_transport`
- PASS: `cp4_sawtooth`
- PASS: `cp2_transport`
- PASS: `cp2_no_fake_sawtooth`
- PASS: `area_1_default`
- PASS: `inactive_not_included`
- PASS: `sorter_not_generated`
- PASS: `no_finished_plc_inputs`
- PASS: `change_report`

### Hard rules honored

- No finished PLC4 inputs
- No Greensboro hardcoding in new discovery modules
- Explicit RUN relationships beat numbering
- Sorter/WCS generation not faked (`NOT_SUPPORTED`)
- Transport visual freeze (data hooks only)
- CP2 sawtooth not invented when overlay has no active merges

### Artifacts

- `exports/run-discovery/` (CP4)
- `exports/run-discovery-cp2/` (CP2)
- `exports/workflow-test/*.json` + this report
- Docs: `docs/RUN_DISCOVERY_MODEL.md`, `docs/RUN_TABLE_PRECEDENCE.md`
