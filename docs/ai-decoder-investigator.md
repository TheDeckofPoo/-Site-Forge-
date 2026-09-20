# Site Forge AI — Decoder Investigator (Stage 1)

**Baseline:** `80c22d0`  
**Role change:** AI is **not** a parallel I/O decoder. Site Forge remains the decoder and PLC compiler.

## Permanent learning loop

```
TAR file
    ↓
Site Forge deterministic decoding
    ↓
claim conservation
    ↓
failure clustering
    ↓
background AI investigation  (read-only tools)
    ↓
DecoderRuleCandidate
    ↓
Anton / Site Forge implements deterministic rule
    ↓
cross-site regression + virgin-site regression
    ↓
rule accepted or rejected
    ↓
Site Forge permanently understands that Fortna variation
```

Future sites matching an accepted rule must **not** require AI again.

## What AI may output

A **`DecoderRuleCandidate`** — an engineering hypothesis:

- failure pattern + affected claims
- observed facts + evidence refs
- candidate deterministic rule + transformation
- supporting examples + **counterexamples**
- ambiguities + missing evidence + tests required
- status: `CANDIDATE` | `REVIEW_REQUIRED` | `INSUFFICIENT_EVIDENCE`

**Never** compiler authority. **Never** Autogen / L5X / READY from AI alone.

`REVIEW IS NOT PASS.`  
`UNKNOWN / INSUFFICIENT_EVIDENCE` is better than guessing.  
`conservation PASS` ≠ `evidence_status READY`.

## What AI must not do

- Promote endpoint mappings to `ai_derived` / READY / Autogen / compiler
- Modify Site Forge state
- Write L5X or Autogen
- Accept engineer assignments
- Use finished/reference PLC as discovery evidence
- Site-name special cases

## Failure clustering

Unresolved physical claims are grouped by shared decoding dimensions
(machine, adapter, family, catalog, direction, Configio fields, word band,
bit encoding class, failure reason, …).

Goal: hundreds of unresolved claims → a few pattern investigations.  
Every claim_id appears in **exactly one** cluster (conservation).

## Read-only tools (contract)

| Tool | Purpose |
|------|---------|
| `get_project_identity` | project / machine |
| `get_machine` | machine identity |
| `get_io_claim` | one claim by id |
| `get_configio_word` / `get_configio_rows` | Configio evidence |
| `get_adapter` / `get_module` | EIP topology |
| `get_neighbor_claims` | same word / adapter neighbours |
| `get_proven_io_examples` | known-good ASSIGNED examples |
| `get_failure_cluster` | one cluster |
| `get_source_rows` | Conveyor/Configio row |
| `get_hardware_family` | catalog → family |
| `get_physical_word_resolution_trace` | resolver hit for a claim |
| `compare_candidate_rule_against_site` | schema + coverage check |

All Stage 1 tools are **read-only**. Mutation ops are refused.

## Product goal (Stage 1)

Multiple Fortna TAR files → Site Forge identifies I/O hardware/modules and
physical I/O with minimal engineer assistance. Known patterns decode
automatically; unknown patterns become clusters → candidate rules →
Anton implements → Site Forge gets progressively more independent.

## Modules

| File | Role |
|------|------|
| `fortna_ai_decoder_schema.py` | DecoderRuleCandidate schema + validation |
| `fortna_ai_failure_cluster.py` | clustering |
| `fortna_ai_readonly_tools.py` | read-only tool surface |
| `fortna_ai_investigate_reno_oa4.py` | first offline investigation fixture |
| `fortna_ai_io_validate.py` | `AI_ENDPOINT_AUTHORITY = False` |
