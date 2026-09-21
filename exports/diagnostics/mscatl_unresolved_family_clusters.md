# MSCATL unresolved family clusters

## CP1 unresolved signatures

- `no_eipmodules_bank_match|POINT_OR_BLOCK_32|IB32DATA|H|SAME|UNKNOWN` × 22
- `no_eipmodules_bank_match|POINT_OR_BLOCK_32|OB32PDATA|H|SAME|UNKNOWN` × 22
- `no_eipmodules_bank_match|ROCKWELL_CATALOG|1794-AENT|H|SAME|UNKNOWN` × 14
- `no_eipmodules_bank_match|POINT_OR_BLOCK_32|IB32STATUS|H|SAME|UNKNOWN` × 2

## Recurring across corpus

- `FAMILY|ROCKWELL_CATALOG|1794-AENT` · machines=['FISHER_CC9', 'PMARTOTW_AC3', 'CP2', 'ORLUBCP1', 'ORDETCP1', 'CP3', 'ORL_AC3', 'CP7', 'CP1', 'CP6', 'PMARTOTW_AC1', 'PMartGa_CP1', 'CP5', 'MSCATL_CP1', 'MSCATL_CP2'] · n=304

## Refined recurrence audit (AI gate)

CP1 unresolved Desc families:

| Family | CP1 unresolved words | Other corpus Configio machines | AI-eligible |
| --- | ---: | --- | --- |
| IB32DATA | 22 | MSCATL_CP1 only | NO |
| OB32PDATA | 22 | MSCATL_CP1 only | NO |
| IB32STATUS | 2 | MSCATL_CP1 only | NO |
| 1794-AENT | 14 | many (adapter status) | NO |

Related hardware elsewhere: PETPAAC1 has 1794-IB32 / 1794-OB32P modules but Configio Desc form 1794-IB32-CP1-52-S2 (panel-catalog) — **different structural signature**.

**AI not called** — no multi-controller recurring unexplained failure dialect.
