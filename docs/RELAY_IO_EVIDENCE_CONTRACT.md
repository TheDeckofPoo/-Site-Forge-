# RELAY I/O Evidence Contract (Site Forge data plane)

**Status:** Advisory evidence only  
**AI_ENDPOINT_AUTHORITY:** `false`  
**use_for_build:** `false`

This document describes the deterministic evidence plane that Site Forge exposes
to the AI Investigator and that future **RELAY** (I/O specialist agent) will
consume. RELAY is **not** implemented here — only the contract.

---

## Authority

| Layer | May do | Must not do |
|---|---|---|
| Deterministic decoder | Resolve RTA/EIP endpoints when proven | Invent AC51/Pamux endpoints |
| Investigator / RELAY | Inspect, compare, hypothesize, propose candidates | Assign production endpoints, mutate RUN/PRISM, emit L5X, mark PROVEN |
| Compiler / Autogen | Consume only Site Forge–validated DERIVED/PROVEN | Accept AI output as authority |

---

## EvidenceRecord fields

| Field | Meaning | May be empty? |
|---|---|---|
| `evidence_id` | Stable id for the row | No |
| `controller` | Controller / machine scope | Prefer filled |
| `owner_state` | Ownership disposition | Yes → `UNKNOWN` |
| `source` | Evidence family (CONFIGIO, CLAIM_LEDGER, …) | Prefer filled |
| `source_location` | File / table path | Prefer filled |
| `interface_family` | e.g. `RTA1`, `PAMUX_AC51` | Yes |
| `raw_address` | Word / word.bit as in source | Yes |
| `normalized_address_candidate` | Rockwell path **only if proven** | Yes — never invent |
| `direction_evidence` | In/Out as in source | Yes |
| `adapter_evidence` | Adapter name if proven | Yes — never invent |
| `module_evidence` | Module/catalog if proven | Yes |
| `channel_evidence` | Channel / Data[n].b if proven | Yes |
| `tag_name` / `signal_name` | Logical names | Yes |
| `device_candidate` | Device guess | Yes — never invent ownership |
| `confidence_state` | `PROVEN` / `REVIEW_REQUIRED` / `UNKNOWN` | Prefer filled |
| `unresolved_reason` | Why not READY | Yes when proven |
| `provenance` | Table/row/kind | Prefer filled |

**Rule:** `DETERMINISTIC DECODER DOES NOT SUPPORT IT ≠ EVIDENCE DOES NOT EXIST.`

Unsupported interfaces remain:

- `status = UNSUPPORTED_INTERFACE`
- `confidence_state = REVIEW_REQUIRED`

---

## What Site Forge knows (deterministic)

- RTA Configio words joined to EIPModules / eipcfg when evidence proves the path
- Claim ledger dispositions for physical word.bit claims
- Hardware identity / rack discovery for supported families
- Conservation accounting (raw vs assigned vs unresolved)

## What remains UNKNOWN

- Pamux / AC51 physical Rockwell endpoints (not invented)
- Adapter/module/channel for unsupported families
- Ownership when source does not prove it

---

## Read-only Investigator tools (RELAY surface)

| Tool | Purpose |
|---|---|
| `list_unsupported_interfaces` | Unsupported interface families + counts |
| `get_raw_configio_records` | RTA + unsupported Configio rows |
| `get_neighboring_io_records` | Neighbors by word/adapter |
| `get_controller_hardware_context` | EIP / rack context |
| `get_endpoint_evidence` | Claim / word.bit resolution trace |
| `get_signal_group_evidence` | All EvidenceRecords for a signal/word/interface |
| `get_ownership_evidence` | Owner state for a claim/name |
| `list_evidence_records` | Full structured EvidenceRecord list |

All tools are **read-only**. Mutation ops are refused.

---

## Future RELAY output

RELAY may emit **advisory candidates** only:

- Must pass schema validation (`affected_count == len(affected_claims/ids)`)
- Invalid → `INVALID_CANDIDATE_SCHEMA` / `REVIEW_REQUIRED`
- Never alters compiler state, never becomes endpoint authority, never writes L5X

---

## Offline AC51 acceptance

Success for AC51 visibility:

```
raw AC51 Configio rows > 0
investigator-visible unsupported evidence > 0
```

Success does **not** require AC51 to be decoded.
