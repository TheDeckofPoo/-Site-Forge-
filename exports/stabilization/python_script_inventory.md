# Python Script Inventory - tools/scripts

**Inventory only.** No files were deleted, moved, renamed, consolidated, or rewritten.

- **Total `.py` files:** 227
- **Scope:** `tools/scripts/` (including `fortna_semantics/`)
- **Related Site Forge production callers scanned:** `desktop/main.js`, `desktop/Launch-*.ps1|bat`, `dashboard/*.js`, and in-tree script imports/subprocess references
- **safe-to-remove:** always `DO NOT DECIDE YET`

## Counts by classification

| Classification | Count |
|---|---:|
| TEST | 68 |
| DIAGNOSTIC | 33 |
| ARCHAEOLOGY | 30 |
| DECODER_CORE | 29 |
| SEMANTIC_CORE | 25 |
| COMPILER | 15 |
| PRODUCTION_RUNTIME | 13 |
| ACCEPTANCE | 6 |
| CP5_INTEGRATION | 5 |
| LEGACY_CANDIDATE | 3 |

## Production subprocess entrypoints (`desktop/main.js`)

- `tools/scripts/_deploy_designer_safe_ignition.py`
- `tools/scripts/apply_recipe.py`
- `tools/scripts/fix_ignition_project_attrs.py`
- `tools/scripts/fortna_autogen.py`
- `tools/scripts/fortna_cp5a_orchestrator.py`
- `tools/scripts/fortna_cp5a_transport_mapper.py`
- `tools/scripts/fortna_hardware_io_model.py`
- `tools/scripts/fortna_ignition_build.py`
- `tools/scripts/fortna_io_banks.py`
- `tools/scripts/fortna_perspective_pack.py`
- `tools/scripts/fortna_plc_export.py`
- `tools/scripts/fortna_prism_ingest.py`
- `tools/scripts/fortna_prism_twin.py`
- `tools/scripts/fortna_run_physical_layout.py`
- `tools/scripts/fortna_run_workspace_discover.py`
- `tools/scripts/fortna_safety_model.py`
- `tools/scripts/fortna_transport_graph.py`
- `tools/scripts/fortna_workbook.py`
- `tools/scripts/index_docs.py`

## File inventory

| path | classification | known caller/importer | subprocess caller | test dependency | production dependency | safe-to-remove |
|---|---|---|---|---|---|---|
| `tools/scripts/_audit_hollow_l5x.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_audit_vfd_flt_semantics.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_deploy_designer_safe_ignition.py` | PRODUCTION_RUNTIME | `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/_deploy_smoke_view.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_aent_ports.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_aoi_main.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_audit_l5x.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_compare_fin.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_configtag_l5k.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_diff_l5x.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_dtype_diff.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_extract_st_types.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_fin_programs.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_find_st_types.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_header_dtypes.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_missing_tag_types.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_modules.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_nops_sntp.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_saw_dtypes.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_slot_config.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_st_members.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_studio_struct.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_tasks_mods.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_emergency_verify_1754.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_check_aoi.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_cp4.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_cp4b.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_cp4c.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_excel_io_pattern.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_fc.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_find_quoted_cdata.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_io_map_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_io_map_audit2.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_l5x_mod_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_opt.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_rewrite_studio_tags.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_studio_dtype_probe.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_studio_dtype_probe2.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_studio_dtype_probe3.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_update_topology_accounting.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_verify.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_verify_es_l5x.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/_tmp_verify_fresh_l5x.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/apply_recipe.py` | PRODUCTION_RUNTIME | `tools/scripts/fortna_plc_export.py`; `desktop/main.js`; `tools/scripts/fortna_io_regression_baselines.py`; `tools/scripts/fortna_runtime_acceptance_recovery.py` | `desktop/main.js`; `tools/scripts/fortna_io_regression_baselines.py`; `tools/scripts/fortna_runtime_acceptance_recovery.py` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/diagnose_plc2_merge_pipeline.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/diagnose_plc2_topology_merges.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fix_ignition_project_attrs.py` | PRODUCTION_RUNTIME | `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_activity_classify.py` | SEMANTIC_CORE | `tools/scripts/fortna_activity_closure.py`; `tools/scripts/fortna_run_workspace_discover.py`; `tools/scripts/test_fortnaplus_knowledge_layer.py`; `tools/scripts/test_run_driven_workspace.py` | `tools/scripts/test_fortnaplus_knowledge_layer.py`; `tools/scripts/test_run_driven_workspace.py` | test_activity_classification_closure.py, test_fortnaplus_knowledge_layer.py, test_knowledge_driven_compiler.py, test_run_driven_workspace.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_activity_closure.py` | DECODER_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_answer_sheet_compare.py` | ARCHAEOLOGY | `tools/scripts/fortna_cp5_gap_closure.py`; `tools/scripts/test_validation_firewall.py` | `tools/scripts/fortna_cp5_gap_closure.py`; `tools/scripts/test_validation_firewall.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_area_discovery.py` | DECODER_CORE | `tools/scripts/fortna_integration_hardening.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_area_ops.py` | DECODER_CORE | (none found) | (none) | test_area_rename_l5x.py, test_engineer_defaults.py, test_knowledge_driven_compiler.py, test_multi_area_e2e.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_asc.py` | DECODER_CORE | `tools/scripts/apply_recipe.py`; `tools/scripts/diagnose_plc2_topology_merges.py`; `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_build_table_knowledge.py`; `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_conveyor_section_model.py` … | `tools/scripts/fortna_sorter_discovery.py` | test_cp3rio2_release_ssv.py, test_iomap_duplicate_output_ownership.py, test_plc2_configio_compiler.py, test_vfd_flt_iomap_member.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_autogen.py` | COMPILER | `tools/scripts/fortna_area_ops.py`; `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_cp2_ownership.py`; `tools/scripts/fortna_cp4_pass1.py` … | `dashboard/fortna-plus.js`; `desktop/main.js`; `tools/scripts/diagnose_plc2_merge_pipeline.py`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py` … | test_area_rename_l5x.py, test_autogen_area_safety_fidelity.py, test_cp4_compiler_pass1.py, test_cp4_sawtooth_fidelity.py, test_cp4_sawtooth_semantics.py, test_export_current_single_l5x.py, test_hardware_family_1734.py, test_iomap_duplicate_output_ownership.py… | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_build_table_knowledge.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_connectivity_sorter_closure.py` | DECODER_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_connectivity_validate.py` | DECODER_CORE | `tools/scripts/fortna_connectivity_sorter_closure.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_controller_scope.py` | DECODER_CORE | `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_fidelity_audit.py`; `tools/scripts/fortna_plc2_foundation_reset.py`; `tools/scripts/fortna_plc2_io_channel_matrix.py`; `tools/scripts/fortna_plc2_io_truth.py` | (none) | test_controller_scope.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_conveyor_section_model.py` | SEMANTIC_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_plc2_merge_discovery.py`; `tools/scripts/fortna_run_physical_layout.py` | (none) | test_cp3rio2_release_ssv.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp2_completion_gate.py` | ACCEPTANCE | `tools/scripts/test_cp2_completion_gate_artifacts.py` | `tools/scripts/test_cp2_completion_gate_artifacts.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp2_demo_closure.py` | ACCEPTANCE | `tools/scripts/test_cp2_demo_closure_artifacts.py` | `tools/scripts/test_cp2_demo_closure_artifacts.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp2_ownership.py` | DECODER_CORE | `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_plc2_foundation_reset.py`; `tools/scripts/fortna_run_geometry_investigate.py`; `tools/scripts/test_cp2_ownership.py` | `tools/scripts/test_cp2_ownership.py` | test_cp2_ownership.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_discovery.py` | DECODER_CORE | `tools/scripts/fortna_run_workspace_discover.py`; `tools/scripts/fortna_sawtooth_merge_model.py`; `tools/scripts/fortna_sawtooth_param.py`; `tools/scripts/fortna_sorter_discovery.py`; `tools/scripts/test_cp4_discovery_no_leakage.py` | `tools/scripts/fortna_sorter_discovery.py`; `tools/scripts/test_cp4_discovery_no_leakage.py` | test_cp4_discovery_no_leakage.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_pass1.py` | COMPILER | `tools/scripts/fortna_cp4_pass2.py`; `tools/scripts/fortna_cp4_sawtooth.py`; `tools/scripts/fortna_cp4_semantics_compile.py` | (none) | test_cp4_compiler_pass1.py, test_cp4_sawtooth_semantics.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_pass1_self_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_pass2.py` | COMPILER | `tools/scripts/fortna_cp4_sawtooth.py`; `tools/scripts/test_cp4_compiler_pass2.py` | `tools/scripts/test_cp4_compiler_pass2.py` | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_sawtooth.py` | COMPILER | `tools/scripts/fortna_cp4_semantics_compile.py`; `tools/scripts/test_cp4_sawtooth_fidelity.py` | `tools/scripts/test_cp4_sawtooth_fidelity.py` | test_cp4_sawtooth_fidelity.py, test_cp4_sawtooth_semantics.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp4_semantics_compile.py` | COMPILER | (none found) | (none) | test_cp4_sawtooth_semantics.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp5_blind_build.py` | CP5_INTEGRATION | `tools/scripts/test_validation_firewall.py` | `tools/scripts/test_validation_firewall.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp5_gap_closure.py` | CP5_INTEGRATION | `tools/scripts/test_validation_firewall.py` | `tools/scripts/test_validation_firewall.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp5a_acceptance.py` | CP5_INTEGRATION | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp5a_orchestrator.py` | CP5_INTEGRATION | `tools/scripts/fortna_cp5a_acceptance.py`; `desktop/main.js` | `desktop/main.js` | test_cp5a_integration.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_cp5a_transport_mapper.py` | CP5_INTEGRATION | `tools/scripts/fortna_cp5a_acceptance.py`; `desktop/main.js` | `desktop/main.js` | test_cp5a_integration.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_curve_validation.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_decoder_acceptance.py` | ACCEPTANCE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_device_logic.py` | COMPILER | `tools/scripts/fortna_mhs_sorter.py`; `tools/scripts/fortna_plc_export.py`; `tools/scripts/fortna_prism_build.py`; `tools/scripts/fortna_prism_seed.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_equipment_plan.py` | DECODER_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_sorter_discovery.py` | `tools/scripts/fortna_sorter_discovery.py` | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_es_compiler.py` | COMPILER | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_safety_model.py` | (none) | test_es_compiler.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_estop_model.py` | SEMANTIC_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_connectivity_sorter_closure.py`; `tools/scripts/fortna_integration_hardening.py`; `tools/scripts/fortna_safety_model.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_fpc_document_inventory.py` | ARCHAEOLOGY | `tools/scripts/fortna_knowledge.py` | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_hardware_family.py` | SEMANTIC_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_hardware_io_model.py`; `tools/scripts/fortna_physical_word_resolver.py`; `dashboard/hardware/hardware-family.js` | `dashboard/hardware/hardware-family.js` | test_hardware_family_1734.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_hardware_io_model.py` | PRODUCTION_RUNTIME | `desktop/main.js` | `desktop/main.js` | test_hardware_family_1734.py, test_hardware_io_model.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_hardware_io_overrides.py` | PRODUCTION_RUNTIME | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_hardware_io_model.py`; `tools/scripts/fortna_safety_model.py` | (none) | test_hardware_io_overrides.py, test_iomap_engineer_logical_name.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_identity.py` | DECODER_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_conveyor_section_model.py`; `tools/scripts/fortna_cp4_pass2.py` | (none) | test_cp4_compiler_pass2.py, test_display_layout_offsets.py, test_fortna_identity_sections.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_ignition_build.py` | COMPILER | `tools/scripts/fortna_autogen.py`; `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_ignition_extract.py` | PRODUCTION_RUNTIME | `tools/scripts/fortna_plc_export.py` | (none) | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_integration_hardening.py` | DECODER_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_io_banks.py` | PRODUCTION_RUNTIME | `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_io_extract.py` | DECODER_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_conveyor_section_model.py`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_cp2_ownership.py` … | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_io_regression_baselines.py` | DECODER_CORE | `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_fidelity_audit.py`; `tools/scripts/fortna_plc2_foundation_reset.py`; `tools/scripts/fortna_plc2_io_channel_matrix.py`; `tools/scripts/fortna_plc2_io_truth.py` | (none) | test_cp3rio2_release_ssv.py, test_io_regression_lock.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_knowledge.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_knowledge_enrich.py`; `tools/scripts/fortna_knowledge_integration.py`; `tools/scripts/test_fortna_knowledge.py` | `tools/scripts/test_fortna_knowledge.py` | test_fortna_knowledge.py, test_knowledge_driven_compiler.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_knowledge_enrich.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_knowledge_integration.py`; `tools/scripts/fortna_run_workspace_discover.py`; `tools/scripts/fortna_sitemodel_to_autogen.py`; `tools/scripts/test_validation_firewall.py` | `tools/scripts/test_validation_firewall.py` | test_knowledge_driven_compiler.py, test_runtime_acceptance_recovery.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_knowledge_integration.py` | DECODER_CORE | `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_cp5_gap_closure.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_l5x_compare.py` | DIAGNOSTIC | `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py` | `tools/scripts/fortna_cp2_completion_gate.py` | test_autogen_area_safety_fidelity.py, test_fortna_l5x_compare.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_l5x_structured_data.py` | COMPILER | `tools/scripts/fortna_autogen.py` | (none) | test_l5x_structured_data.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_layout_overlap_research.py` | ARCHAEOLOGY | `tools/scripts/test_display_layout_offsets.py` | `tools/scripts/test_display_layout_offsets.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_legacy_layout.py` | ARCHAEOLOGY | (none found) | (none) | test_display_layout_offsets.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_mhs_sorter.py` | LEGACY_CANDIDATE | `tools/scripts/fortna_prism_build.py`; `tools/scripts/fortna_sorter_discovery.py` | `tools/scripts/fortna_sorter_discovery.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_mnu_runtime.py` | DECODER_CORE | `tools/scripts/fortna_reference_resolver.py`; `tools/scripts/fortna_run_loader.py` | (none) | test_fortna_mnu_runtime.py, test_fortna_reference_resolver.py, test_fortna_run_loader.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_mnu_schema.py` | DECODER_CORE | `tools/scripts/fortna_decoder_acceptance.py`; `tools/scripts/fortna_mnu_runtime.py`; `tools/scripts/fortna_reference_resolver.py`; `tools/scripts/fortna_run_loader.py` | (none) | test_fortna_mnu_runtime.py, test_fortna_mnu_schema.py, test_fortna_reference_resolver.py, test_fortna_run_loader.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_motor_logic.py` | COMPILER | `tools/scripts/fortna_device_logic.py`; `tools/scripts/fortna_mhs_sorter.py`; `tools/scripts/fortna_plc_export.py`; `tools/scripts/fortna_prism_build.py`; `tools/scripts/fortna_prism_seed.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_perspective_pack.py` | COMPILER | `tools/scripts/fix_ignition_project_attrs.py`; `tools/scripts/fortna_ignition_build.py`; `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_physical_geometry.py` | SEMANTIC_CORE | `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_cp4_discovery.py`; `tools/scripts/fortna_curve_validation.py`; `tools/scripts/fortna_layout_overlap_research.py`; `tools/scripts/fortna_legacy_layout.py`; `tools/scripts/fortna_physical_overlap_audit.py` … | `tools/scripts/fortna_curve_validation.py` | test_fortna_physical_geometry.py, test_transport_physical_drawing.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_physical_overlap_audit.py` | DIAGNOSTIC | `tools/scripts/fortna_cp2_demo_closure.py` | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_physical_runs.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_physical_word_resolver.py` | SEMANTIC_CORE | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_hardware_io_model.py`; `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_io_channel_matrix.py`; `tools/scripts/test_plc2_configio_compiler.py` | `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/test_plc2_configio_compiler.py` | test_cp3rio2_release_ssv.py, test_hardware_family_1734.py, test_hardware_io_model.py, test_iomap_duplicate_output_ownership.py, test_plc2_configio_compiler.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_configio_compiler.py` | COMPILER | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_fidelity_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_foundation_reset.py` | DECODER_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_io_channel_matrix.py` | DECODER_CORE | (none found) | (none) | test_cp3rio2_release_ssv.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_io_truth.py` | DECODER_CORE | `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_fidelity_audit.py`; `tools/scripts/fortna_plc2_io_channel_matrix.py` | (none) | test_cp3rio2_release_ssv.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc2_merge_discovery.py` | DECODER_CORE | `tools/scripts/test_plc2_merge_discovery.py` | `tools/scripts/test_plc2_merge_discovery.py` | test_plc2_merge_discovery.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_plc_export.py` | COMPILER | `tools/scripts/fortna_autogen.py`; `desktop/main.js`; `tools/scripts/fortna_ignition_extract.py` | `desktop/main.js`; `tools/scripts/fortna_ignition_extract.py` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_prism_build.py` | LEGACY_CANDIDATE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_prism_ingest.py` | PRODUCTION_RUNTIME | `tools/scripts/apply_recipe.py`; `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_ignition_build.py`; `tools/scripts/fortna_plc_export.py`; `tools/scripts/fortna_prism_twin.py`; `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_prism_seed.py` | LEGACY_CANDIDATE | `tools/scripts/fortna_plc_export.py`; `tools/scripts/fortna_prism_build.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_prism_twin.py` | PRODUCTION_RUNTIME | `desktop/main.js` | `desktop/main.js` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_reference_resolver.py` | DECODER_CORE | `tools/scripts/fortna_cp5a_orchestrator.py`; `tools/scripts/fortna_decoder_acceptance.py`; `tools/scripts/fortna_semantics/evidence.py` | (none) | test_fortna_reference_resolver.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_autobuild_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_geometry_investigate.py` | ARCHAEOLOGY | `tools/scripts/fortna_controller_scope.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_cp2_ownership.py`; `tools/scripts/fortna_cp4_discovery.py`; `tools/scripts/fortna_cp4_pass1_self_audit.py`; `tools/scripts/fortna_curve_validation.py` … | `tools/scripts/fortna_run_physical_layout.py` | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_loader.py` | DECODER_CORE | `tools/scripts/fortna_decoder_acceptance.py`; `tools/scripts/fortna_reference_resolver.py` | (none) | test_fortna_reference_resolver.py, test_fortna_run_loader.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_physical_layout.py` | PRODUCTION_RUNTIME | `tools/scripts/diagnose_plc2_topology_merges.py`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_cp5a_transport_mapper.py`; `tools/scripts/fortna_run_autobuild_audit.py`; `tools/scripts/fortna_run_workspace_discover.py` … | `desktop/main.js`; `tools/scripts/fortna_curve_validation.py`; `tools/scripts/fortna_plc2_foundation_reset.py`; `tools/scripts/fortna_plc2_io_truth.py`; `tools/scripts/test_source_truth_no_leakage.py` | test_auto_build_physical_layout.py, test_source_truth_no_leakage.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_site_model_discovery.py` | DECODER_CORE | `tools/scripts/fortna_cp2_completion_gate.py` | `tools/scripts/fortna_cp2_completion_gate.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_run_workspace_discover.py` | DECODER_CORE | `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_knowledge_integration.py`; `tools/scripts/fortna_ui_workflow_smoke.py`; `desktop/main.js`; `tools/scripts/fortna_runtime_acceptance_recovery.py`; `tools/scripts/test_fortnaplus_knowledge_layer.py` … | `desktop/main.js`; `tools/scripts/fortna_runtime_acceptance_recovery.py`; `tools/scripts/test_fortnaplus_knowledge_layer.py`; `tools/scripts/test_run_driven_workspace.py`; `tools/scripts/test_validation_firewall.py` | test_fortnaplus_knowledge_layer.py, test_project_workspace_isolation.py, test_run_driven_workspace.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_runtime_acceptance_recovery.py` | ACCEPTANCE | `tools/scripts/fortna_io_regression_baselines.py`; `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_fidelity_audit.py`; `tools/scripts/fortna_plc2_foundation_reset.py`; `tools/scripts/fortna_plc2_io_truth.py` | (none) | test_io_regression_lock.py, test_runtime_acceptance_recovery.py | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_safety_model.py` | SEMANTIC_CORE | `dashboard/safety-build.js`; `desktop/main.js` | `dashboard/safety-build.js`; `desktop/main.js` | test_safety_model.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_sawtooth_library_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_sawtooth_merge_model.py` | SEMANTIC_CORE | `tools/scripts/fortna_run_workspace_discover.py` | (none) | test_sawtooth_merge_model_cp4.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_sawtooth_param.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp4_pass2.py`; `tools/scripts/fortna_cp4_sawtooth.py`; `tools/scripts/fortna_cp4_semantics_compile.py`; `tools/scripts/fortna_sawtooth_semantics.py`; `tools/scripts/fortna_unresolved_symbol_audit.py` | (none) | test_cp4_sawtooth_semantics.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_sawtooth_semantics.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp4_semantics_compile.py`; `tools/scripts/fortna_run_workspace_discover.py` | (none) | test_cp4_sawtooth_semantics.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_schematic_svg_export.py` | PRODUCTION_RUNTIME | (none found) | (none) | no | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantic_acceptance.py` | ACCEPTANCE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/__init__.py` | SEMANTIC_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/bundle.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp5a_orchestrator.py`; `tools/scripts/fortna_semantic_acceptance.py`; `tools/scripts/fortna_semantics/__init__.py` | (none) | test_cp4_bundle.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/common.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/evidence.py`; `tools/scripts/fortna_semantics/io.py`; `tools/scripts/fortna_semantics/jam.py`; `tools/scripts/fortna_semantics/merge.py`; `tools/scripts/fortna_semantics/mtrchain.py`; `tools/scripts/fortna_semantics/safety.py` … | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/evidence.py` | SEMANTIC_CORE | `tools/scripts/fortna_cp5a_orchestrator.py`; `tools/scripts/fortna_semantic_acceptance.py`; `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_io.py, test_cp4_jam.py, test_cp4_merge.py, test_cp4_mtrchain.py, test_cp4_safety.py, test_cp4_transportation.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/io.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_io.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/jam.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_jam.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/merge.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_merge.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/mtrchain.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_merge.py, test_cp4_mtrchain.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/safety.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_safety.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_semantics/transportation.py` | SEMANTIC_CORE | `tools/scripts/fortna_semantics/bundle.py` | (none) | test_cp4_transportation.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_site_model.py` | SEMANTIC_CORE | `tools/scripts/fortna_activity_classify.py`; `tools/scripts/fortna_activity_closure.py`; `tools/scripts/fortna_area_discovery.py`; `tools/scripts/fortna_area_ops.py`; `tools/scripts/fortna_build_table_knowledge.py`; `tools/scripts/fortna_connectivity_sorter_closure.py` … | `tools/scripts/test_fortnaplus_knowledge_layer.py`; `tools/scripts/test_run_driven_workspace.py` | test_activity_classification_closure.py, test_area_rename_l5x.py, test_blind_genericity_fixtures.py, test_cp5_blind_identity.py, test_engineer_defaults.py, test_fortnaplus_knowledge_layer.py, test_knowledge_driven_compiler.py, test_multi_area_e2e.py… | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_sitemodel_to_autogen.py` | COMPILER | `tools/scripts/fortna_cp5_gap_closure.py`; `tools/scripts/fortna_runtime_acceptance_recovery.py`; `tools/scripts/test_validation_firewall.py` | `tools/scripts/test_validation_firewall.py` | test_runtime_acceptance_recovery.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_sorter_build.py` | COMPILER | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_sorter_discovery.py` | `tools/scripts/fortna_sorter_discovery.py` | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_sorter_discovery.py` | DECODER_CORE | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_sorter_divert_research.py` | ARCHAEOLOGY | `tools/scripts/fortna_connectivity_sorter_closure.py` | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_sorter_leaves.py` | DECODER_CORE | `tools/scripts/fortna_connectivity_sorter_closure.py`; `tools/scripts/fortna_integration_hardening.py` | (none) | test_sorter_leaves_blind.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_source_id.py` | DECODER_CORE | `tools/scripts/apply_recipe.py`; `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_ignition_build.py`; `tools/scripts/fortna_plc_export.py`; `tools/scripts/fortna_prism_ingest.py`; `tools/scripts/fortna_prism_twin.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_spiral_area_analysis.py` | ARCHAEOLOGY | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_studio_preflight.py` | DIAGNOSTIC | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_connectivity_sorter_closure.py`; `tools/scripts/fortna_integration_hardening.py` | (none) | test_iomap_duplicate_output_ownership.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_supersession.py` | SEMANTIC_CORE | `tools/scripts/fortna_activity_closure.py`; `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_knowledge_integration.py`; `tools/scripts/fortna_run_workspace_discover.py` | (none) | no | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_transport_graph.py` | SEMANTIC_CORE | `desktop/main.js`; `tools/scripts/diagnose_plc2_merge_pipeline.py` | `desktop/main.js`; `tools/scripts/diagnose_plc2_merge_pipeline.py` | test_project_lifecycle_clear.py, test_project_workspace_isolation.py, test_transport_apply_persistence.py, test_transport_cross_area_move.py, test_transport_ux_pass1.py, test_transport_ux_pass2.py | yes | DO NOT DECIDE YET |
| `tools/scripts/fortna_ui_workflow_smoke.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_unresolved_symbol_audit.py` | DIAGNOSTIC | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/fortna_validate_site_model.py` | DECODER_CORE | `tools/scripts/fortna_cp5_blind_build.py`; `tools/scripts/fortna_knowledge_integration.py`; `tools/scripts/test_fortnaplus_knowledge_layer.py` | `tools/scripts/test_fortnaplus_knowledge_layer.py` | test_fortnaplus_knowledge_layer.py, test_knowledge_driven_compiler.py | likely | DO NOT DECIDE YET |
| `tools/scripts/fortna_workbook.py` | PRODUCTION_RUNTIME | `tools/scripts/fortna_autogen.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_cp4_pass1.py`; `tools/scripts/fortna_prism_twin.py`; `desktop/main.js`; `tools/scripts/fortna_cp2_completion_gate.py` … | `desktop/main.js`; `tools/scripts/fortna_cp2_completion_gate.py`; `tools/scripts/fortna_cp2_demo_closure.py`; `tools/scripts/fortna_plc2_configio_compiler.py`; `tools/scripts/fortna_plc2_foundation_reset.py` … | test_autogen_area_safety_fidelity.py, test_source_truth_no_leakage.py | yes | DO NOT DECIDE YET |
| `tools/scripts/index_docs.py` | PRODUCTION_RUNTIME | `desktop/Launch-Electron.ps1`; `desktop/main.js`; `tools/scripts/apply_recipe.py` | `desktop/Launch-Electron.ps1`; `desktop/main.js`; `tools/scripts/apply_recipe.py` | no | yes | DO NOT DECIDE YET |
| `tools/scripts/test_activity_classification_closure.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_area_rename_l5x.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_auto_build_physical_layout.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_autogen_area_safety_fidelity.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_blind_genericity_fixtures.py` | TEST | (none found) | (none) | test_knowledge_driven_compiler.py | no | DO NOT DECIDE YET |
| `tools/scripts/test_controller_scope.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp2_completion_gate_artifacts.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp2_demo_closure_artifacts.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp2_ownership.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp3rio2_release_ssv.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_bundle.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_compiler_pass1.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_compiler_pass2.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_discovery_no_leakage.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_io.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_jam.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_merge.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_mtrchain.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_safety.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_sawtooth_fidelity.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_sawtooth_semantics.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp4_transportation.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp5_blind_identity.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_cp5a_integration.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_display_layout_offsets.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_engineer_defaults.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_es_compiler.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_export_current_single_l5x.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_identity_sections.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_knowledge.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_l5x_compare.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_mnu_runtime.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_mnu_schema.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_physical_geometry.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_reference_resolver.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortna_run_loader.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_fortnaplus_knowledge_layer.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_hardware_family_1734.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_hardware_io_model.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_hardware_io_overrides.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_io_regression_lock.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_iomap_duplicate_output_ownership.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_iomap_engineer_logical_name.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_knowledge_driven_compiler.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_l5x_datatype_closure.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_l5x_structured_data.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_mscreno_aug28_regression.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_multi_area_e2e.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_plc2_configio_compiler.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_plc2_merge_discovery.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_project_lifecycle_clear.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_project_workspace_isolation.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_run_driven_workspace.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_runtime_acceptance_recovery.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_safety_model.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_sawtooth_enable_tags.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_sawtooth_merge_model_cp4.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_sorter_leaves_blind.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_source_truth_no_leakage.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_apply_persistence.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_cross_area_move.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_hit_geometry.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_physical_drawing.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_physical_presentation.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_ux_pass1.py` | TEST | `tools/scripts/test_transport_ux_pass2.py` | `tools/scripts/test_transport_ux_pass2.py` | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_transport_ux_pass2.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_validation_firewall.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/test_vfd_flt_iomap_member.py` | TEST | (none found) | (none) | no | no | DO NOT DECIDE YET |
| `tools/scripts/validate_plc_export.py` | ACCEPTANCE | (none found) | (none) | no | no | DO NOT DECIDE YET |

## Notes

- `_emergency_*` → **ARCHAEOLOGY**; `_tmp_*` / `_audit_*` → **DIAGNOSTIC**; `_deploy_*` used by desktop → **PRODUCTION_RUNTIME** when wired from `desktop/main.js`.
- `test_*.py` → **TEST**.
- `fortna_semantics/*` → **SEMANTIC_CORE**.
- Scripts that are both compilers and desktop entrypoints (e.g. `fortna_autogen.py`) are labeled **COMPILER** with `production_dependency=yes`.
- Classifications are inventory labels based on naming, import graph, and desktop subprocess wiring — not deletion authority.
- Twin JSON: `exports/stabilization/python_script_inventory.json`
