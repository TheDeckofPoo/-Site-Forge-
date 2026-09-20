# AI Investigation Summary — Reality Check V1 Demo B PASS 2

**Machine:** `FISHER_CC9` (hard blind; selected before decoder outcome)
**Live AI:** YES (authorized)
**Production decoder mutated:** NO
**Endpoints assigned by AI:** NO

## Cluster

| Field | Value |
|-------|-------|
| cluster_key | `c363715ca1e83906` |
| claims_affected | 95 |
| signature failure | `PHYSICAL_RESOLUTION_FAILURE` |
| configio_form | `UNBOUND` |

## Session

| Field | Value |
|-------|-------|
| investigation_id | `REALITY_CHECK_V1_FISHER_CC9_CLUSTER_c363715ca1e83906` |
| model | `gpt-5.6-terra` |
| estimated cost USD | **0.178975** (hard budget 1.5) |
| tool calls | 36 |
| final status | **INSUFFICIENT_EVIDENCE** |

## Candidate

- name: `reject_numeric_suffix_as_cross_rack_binding_key`
- description: Do not infer an adapter, slot, directional bank, or Low/High relationship from the terminal numeric suffix in Configio Desc. Retain the requirement for a complete, direction-compatible hardware-bank match. Where that evidence is absent, retain review status rather than manufacturing a binding.
- confidence: {'level': 'high', 'score': 0.93, 'basis': 'Independent aggregate and raw-row evidence strongly rejects numeric-suffix fallback, while no independent evidence supports a positive resolver convention.'}
- warehouse rule_key: `reject_numeric_suffix_as_cross_rack_binding_key`
- warehouse status: `INSUFFICIENT_EVIDENCE` (NOT promoted)

## Evidence / counterevidence (from candidate)

- observed_facts: ["Independent aggregate evidence from get_configio_binding_cluster_summary reports 19 no_eipmodules_bank_match words, versus 89 BOUND words.", "The no-match set is structurally heterogeneous: 1746-OA16 words 23-25, 1746-IA16 words 1020-1023, 1794-AENT words 276-277 and 2070-2075, and YASKAWA-SI-EN3-ESC words 150-151 and 1150-1151.", "At word 23, Configio Low bank 6 with Desc 1746-OA16-16 encounters only a 1746-IA16 input bank; Configio High bank 7 has no match. This is direction- and catalog-incompatible, not evidence for half pairing.", "At word 2072, banks 88 and 89 have no module-bank records anywhere in the independently derived hardware bank map, despite numeric suffixes 127 and 128.", "The site has valid bound words using the same general descriptor syntax: word 20 is 1746-OA16 suffixes 4/5 with banks 0/1, and word 1000 is 1794-IA16 suffixes 95/96 with banks 68/69. Syntax and terminal number therefore do not supply a universal conversion."]
- supporting_examples: [{"word": 23, "observation": "Low bank 6 is available only as an input bank on T_1747_AENTR_1 slot 5, catalog 1746-IA16, conflicting with Desc 1746-OA16-16; High bank 7 is unmatched."}, {"word": 2072, "observation": "Neither bank 88 nor 89 exists in the hardware module-bank map although Desc suffixes are 127 and 128."}, {"word": 20, "observation": "An independently BOUND 1746-OA16 word has suffixes 4/5 and banks 0/1, demonstrating that descriptor syntax does not establish a universal numeric mapping."}, {"word": 1000, "observation": "An independently BOUND 1794-IA16 word has suffixes 95/96 and banks 68/69, unlike the unbound 1794-AENT ranges."}]
- counterexamples: [{"candidate": "panel_catalog_numeric_alpha_low_a_slot", "reason": "The unresolved population spans 1746, 1794, and YASKAWA descriptor families with no demonstrated common hardware topology; catalog numeric suffix plus Low position is not a proven slot rule."}, {"candidate": "infer_high_from_low", "reason": "Word 23 has a Low-side bank collision with a direction- and catalog-incompatible input module, while its High bank is absent. It cannot establish a Low/High pairing convention."}, {"candidate": "numeric_suffix_to_bank", "reason": "Word 2072 uses suffixes 127/128 with banks 88/89, neither of which exists in the complete hardware-bank map."}]
- ambiguities: ["No raw convention was found that maps the unresolved Configio numeric suffixes to adapter identity, physical slot, or directional module bank.", "The aggregate failure cluster combines heterogeneous descriptor families and both partial and complete half-word bank failures.", "YASKAWA descriptor rows have no demonstrated directional-bank correspondence in the available hardware mapping."]

## Before / after (production counts UNCHANGED)

```json
{
  "kind": "before_after_investigation_comparison",
  "pass1_unchanged_production_counts": {
    "PROVEN": 874,
    "DERIVED": 0,
    "REVIEW_REQUIRED": 97,
    "needs_resolution": 97,
    "UNKNOWN": null,
    "conservation": "PASS"
  },
  "candidate_potential_coverage_NOT_RESOLVED": {
    "cluster_key": "c363715ca1e83906",
    "claims_potentially_covered_if_promoted_later": 0,
    "candidate_status": "INSUFFICIENT_EVIDENCE",
    "note": "Do NOT call these claims resolved. Production counts remain Pass1 until rule promotion after review."
  }
}
```

## Notes

- Secondary clusters left for later if budget consumed by primary family.
- Shadow corpus evaluation: not fully executed; see shadow stub.
- Stopped for Curtis/Gilfoyle review — do not implement/promote from this pass alone.

## Secondary cluster `75c7bfffb16639e2`

- claims: 2
- status: **REVIEW_REQUIRED**
- cost USD: **0.117709**
- candidate: `duplicate_word_bit_owner_conflict_requires_review`
- warehouse: `duplicate_word_bit_owner_conflict_requires_review` / `CANDIDATE_RULE`
