# MSCATL CP1+CP2 investigation persist

**Investigation ID:** `MSCATL_CP1_CP2_IO_PIPELINE_20260921`

## Ingest

### MSCATL_CP1
- archive SHA: `dabbf5713b7c39cc5a1cfe14b62e13149b5f389b14229f072b81033a1d28a410`
- ingest status: `REEXTRACTED`
- configio/eipmodules/io_claims staged: 400/46/1864

### MSCATL_CP2
- archive SHA: `9f23b410433b5222617addd60f4c81e44ac886933a6093b90d79ca53f5bf70d3`
- ingest status: `REEXTRACTED`
- configio/eipmodules/io_claims staged: 400/29/1644

## Capture summary

### MSCATL_CP1
- raw physical claims: **842**
- ASSIGNED: **297**
- unresolved claims: **545**
- EIPModules nonzero banks: **39/39**
- discovery: `REVIEW_REQUIRED` / evidence `NEEDS_RESOLUTION`
- unresolved families: `{'IB32DATA': 22, 'OB32PDATA': 22, 'IB32STATUS': 2, '1794-AENT': 14}`
- unresolved reasons: `{'no_eipmodules_bank_match': 60}`

### MSCATL_CP2
- raw physical claims: **605**
- ASSIGNED: **221**
- unresolved claims: **384**
- EIPModules nonzero banks: **0/20**
- discovery: `REVIEW_REQUIRED` / evidence `NEEDS_RESOLUTION`
- unresolved families: `{'POWERFLEX700': 24, '1794-AENT': 6}`
- unresolved reasons: `{'no_eipmodules_bank_match': 30}`

## Unresolved family clusters (CP1-centric)

- Configio rows scanned: **4489**
- Recurring clusters: **1**

- `FAMILY|ROCKWELL_CATALOG|1794-AENT` machines=['FISHER_CC9', 'PMARTOTW_AC3', 'CP2', 'ORLUBCP1', 'ORDETCP1', 'CP3', 'ORL_AC3', 'CP7', 'CP1', 'CP6', 'PMARTOTW_AC1', 'PMartGa_CP1', 'CP5', 'MSCATL_CP1', 'MSCATL_CP2'] count=304 fam=1794-AENT

## AI gate

- AI allowed: **True**
- Recurring structural families found across >=2 machines — one generalized AI investigation permitted on the cluster, not per endpoint.

## Refined AI gate

**AI allowed: false** (\.00 spent)

CP1 unresolved dialects \IB32DATA\ / \OB32PDATA\ / \IB32STATUS\ are **MSCATL_CP1-only** in \evidence.configio_rows\.
PETPAAC1 has 1794-IB32 hardware with a **different** Desc form (94-IB32-CP#-S#\).

No multi-controller recurring unexplained failure cluster → AI not invoked.
