# MSCATL_CP2 vs MSCATL_CP3 I/O pipeline

## First divergence

**Stage:** PhysicalWordResolver / Configio.Bank → EIPModules.InputBank|OutputBank join

**Predicate:** `no_eipmodules_bank_match`

- CP3: EIPModules banks populated (e.g. IA16 InputBank 4,6,8…) → configio_catalog_prefix_bank ASSIGNED
- CP2: EIPModules banks all 0 → every RTA word unresolved → 605 physical_resolution_failure, 0 ASSIGNED
- Note: CP2 creates 605 physical IoClaims; failure is resolution/binding, not missing Conveyor claims

## MSCATL_CP2

- Configio loaded physical rows: **94**
- EIPModules rows: **20** (nonzero banks **0**)
- eipcfg adapters: **9** / modules **29**
- Physical IoClaims: **605**
- ASSIGNED: **221**
- physical_resolution_failure: **384**
- Resolved words: **20**
- Unresolved reasons: `{'no_eipmodules_bank_match': 30}`

## MSCATL_CP3

- Configio loaded physical rows: **49**
- EIPModules rows: **23** (nonzero banks **23**)
- eipcfg adapters: **3** / modules **26**
- Physical IoClaims: **256**
- ASSIGNED: **256**
- physical_resolution_failure: **0**
- Resolved words: **23**
- Unresolved reasons: `{'no_eipmodules_bank_match': 6}`

## PostgreSQL

corpus.archives has no MSCATL_* rows; evidence.io_claims for MSCATL_CP2 = 0. Live RUN peek shows claims+zero banks. Ingest gap vs claim construction.

## Bank allocation promotion

- Racks tested: 77
- Support: 17
- Counterexamples: 60
- Production promotion justified: **False**
- Decision: STOP at REVIEW_REQUIRED — do not invent CP2 endpoints via bank synthesis

## Why prior corpus backtest falsely passed

- Reported CP2 was **ORNCCP2 (Greensboro PLC2 peek), NOT MSCATL_CP2**
- LOST_CLAIMS = resolved_not_emitted; when ASSIGNED=0, lost=0 is vacuous PASS
- Stage-0 / discovery-failure gate was absent
