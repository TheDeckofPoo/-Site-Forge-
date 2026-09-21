# Site Forge Learning Status

Generated: 2026-09-21T04:21:51.040968+00:00

## Totals

- **archives_complete:** 71
- **controllers:** 62
- **field_tests:** 3
- **structural_signatures:** 3
- **failure_events:** 50
- **unknown_clusters:** 8
- **shadow_evaluations:** 1

## Rule candidates

- `panel_catalog_numeric_alpha_low_a_slot` status=CANDIDATE_RULE auto_promote=False — PANEL_CATALOG_NUMERIC_ALPHA Low/A slot join (CP8 investigation)
- `direction_aware_bank_binding` status=PRODUCTION_RULE auto_promote=False — Direction-aware Configio bank binding
- `exact_adapter_ip_bridge` status=PRODUCTION_RULE auto_promote=False — Exact EIPAdapters TargetIP bridge
- `reject_numeric_suffix_as_cross_rack_binding_key` status=INSUFFICIENT_EVIDENCE auto_promote=False — reject_numeric_suffix_as_cross_rack_binding_key
- `duplicate_word_bit_owner_conflict_requires_review` status=CANDIDATE_RULE auto_promote=False — duplicate_word_bit_owner_conflict_requires_review
- `rta_32pt_token_direct_bank_span_match` status=CANDIDATE auto_promote=False — RTA 32pt token Desc mid-span DirectSize bank match

## AI investigations

- `DET_rta_32pt_token_direct_bank_span_match_CP1` model=deterministic cost=$0.00 disposition=CANDIDATE

**AI invoked this session:** False ($0.00)

## Success metric

unknown pattern → investigate once → deterministic rule → next site with same pattern requires no AI

### This session

- Rule `rta_32pt_token_direct_bank_span_match`
- Discovered from MSCATL_CP1
- AI cost: $0.00 (deterministic)
- Resolver enabled: True
- 842/842 physical claims ASSIGNED after enable

## Top failure codes (warehouse)

- `no_eipmodules_bank_match` × 50
