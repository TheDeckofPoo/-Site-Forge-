# CP6 Sorter Pipeline — Handoff Trace

**Machine:** ORINDYAC6 (virgin RUN `workspace/_virgin_orindy/RUN`)  
**Branch:** `feature/plc2-transport-fidelity`  
**Date:** 2026-09-19

## First failed boundary

**Boundary:** `build_canonical_sorter_model` → `field_authority.transport_area` / sorter area program emit

Discovery already proved:

- `application_structure.apps = ['Shipping Sorter']`
- `sections_under_app = {'Shipping Sorter': ['SORTER']}`
- divert IO `SSV610_LN*` on Outpoints⋈SrtZoneLane

…but the canonical model left:

- `transport_area = None` / authority `UNKNOWN`
- `shipping_sorter_supported` unset
- Phase 1 UI status claimed “PLC generation supported” while only `Sorter_Track` emitted

Transport therefore bound sorter belts to generic `{Machine}_Area_*` / `Zone_Area1_Area_*` instead of `{ShippingSorter}_Area_Fast/Slow/L1/L2`.

## Root cause (proven — do not re-litigate)

1. **Area identity never derived** from AppSorter → no `sorter_area_name` / `ShippingSorter` program prefix.
2. **Divert UDT hosts** stayed on pack-template `P506_Divert*` because:
   - encoder ordinal remap double-counted identical induct+first-tracking rows, and
   - word-boundary rename of `P506` does **not** rewrite `P506_Divert1` (explicit DivertN pairs required).
3. **MachineClosure / native_shadow** not used to scope divert ownership.
4. L3 / area packs gated on hardcoded checkbox / shoe enum instead of RUN `shipping_sorter_supported`.

## Fix summary (this pass)

| Layer | Change |
|-------|--------|
| Discovery | `sanitize_sorter_area_name` / `derive_sorter_area_identity`; set `transport_area`, `sorter_area_name`, `shipping_sorter_supported`, `divert_host_conveyor=P610`, DERIVED `shoe_sorter`; machine-scope filter; prefer `resolve_active_asc` |
| Sorter build | encoder (enc,conv) dedupe; `_build_divert_rename_pairs` → `P610_DivertN` |
| Autogen | `bind_sorter_area_conveyors`; auto-include L3 when `shipping_sorter_supported`; remap L3 tokens; seed native `merges_2to1` (P600) without Sawtooth |
| UI | status “Sorter Track + Area programs”; `shippingSorterEvidence` accepts discovery flags/apps |
| Provenance | why `Sorter_Track` / `P610_Divert*` / orphan ERROR `P506_Divert1` / native merge |

## Smoke expectation (virgin ORINDYAC6)

- Model: `ShippingSorter`, `shipping_sorter_supported=True`, divert host `P610`
- Compiled tags: `P610_Divert1` present, `P506_Divert1` absent
- Area bind: `P606`/`P610` → `ShippingSorter` → programs `{ShippingSorter}_Area_Fast/...`
- Native merge seed includes `P600`
- Safety path untouched

## Compatibility note � SrtZoneLane identity collapse

`merge_table_rows` / `resolve_active_asc` collapses rows by `row_identity_key` (Name).
SrtZoneLane pairs two destination lanes under one Name (`SHIP_18_19`), so native
identity merge drops Enabled=Y multiplicity (ORNCCP5 32?15).

Sorter discovery therefore reads the active overlay file via `resolve_asc` +
`read_asc` (overlay-only, all rows) � not via identity-collapsed merge.
