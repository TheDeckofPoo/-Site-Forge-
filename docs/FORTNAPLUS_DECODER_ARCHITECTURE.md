# FortnaPlus Decoder Architecture (Authoritative Compact Map)

Conversation memory is **not** authoritative engineering evidence.  
Repository source / docs / tests / artifacts are.

## Layer map

| Layer | SHA | Responsibility |
|-------|-----|----------------|
| **CP1** | `bedcb7a` | `.mnu` schema/runtime decode (`find_data_source`, datatypes) |
| **CP2** | `83dc7bb` | Generic typed RUN/ASC loader (`FortnaTable/Record/Value`) |
| **CP3** | `d43abd6` | Generic reference resolver + complete reverse graph |
| **CP4** | *(this commit)* | Modular engineering **semantic adapters** (not Site Model) |
| **CP5** | — | Canonical Site Forge Site Model (**not started**) |
| **CP6** | — | PLC compiler (**not started**) |

## Pipeline

```
CP1 schema/runtime
      ↓
CP2 typed records
      ↓
CP3 relationship graph
      ↓
CP4 modular semantic adapters
      ↓
(future) CP5 Site Model → CP6 PLC
```

## CP4 adapter compartments

| Adapter | Module | Artifact |
|---------|--------|----------|
| Transportation | `fortna_semantics/transportation.py` | `cp4-transportation-<site>.json` |
| Mtrchain | `fortna_semantics/mtrchain.py` | `cp4-mtrchain-<site>.json` |
| Merge | `fortna_semantics/merge.py` | `cp4-merge-<site>.json` |
| Jam | `fortna_semantics/jam.py` | `cp4-jam-<site>.json` |
| Safety Evidence | `fortna_semantics/safety.py` | `cp4-safety-evidence-<site>.json` |
| I/O Evidence | `fortna_semantics/io.py` | `cp4-io-evidence-<site>.json` |
| Bundle | `fortna_semantics/bundle.py` | `cp4-semantic-bundle-<site>.json` |

Adapters fail/review **independently**. Bundle does not reinterpret.

## Evidence states

| State | Meaning |
|-------|---------|
| PROVEN | Directly supported by CP3 edge + schema/runtime |
| DERIVED | Deterministic composition of proven facts (not speculation) |
| REVIEW_REQUIRED | Incomplete; engineer must decide |
| UNKNOWN | Not established |
| CONFLICT | Contradictory proven evidence |

Rule classes: `SOURCE_PROVEN` · `RUN_PROVEN` · `DETERMINISTIC_DERIVATION` · `UNKNOWN`

## Frozen architectural rules

- CP4 consumes CP3; does not rediscover RUN relationships by ASC re-parse.
- No string-similarity relationship guessing.
- Mtrchain ≠ automatic physical topology.
- MergeInputs logical lane ≠ physical release conveyor.
- EStop refs ≠ Safety zone membership.
- No PLC2/4/5 special cases in generic adapters.
- Production Site Forge / PLC compiler untouched.

## Blind validation sites

- PLC2 `ORNCCP2` — `workspace/_plc2_run_peek/RUN`
- PLC4 `ORNCCP4` — `workspace/cp4-run/RUN`
- PLC5 `ORNCCP5` — `workspace/cp5-run/RUN`

## Acceptance commands

```powershell
# CP1–CP3
python tools/scripts/fortna_decoder_acceptance.py --out-dir artifacts

# CP4
python tools/scripts/fortna_semantic_acceptance.py --out-dir artifacts
```

## Known UNKNOWN

- Physical conveyor adjacency / geometry
- Safety zone membership assignment
- I/O physical endpoint ownership
- `.rom` binary storage decode
- Whether every Conveyor identity is a belt vs PE/motor/display part
