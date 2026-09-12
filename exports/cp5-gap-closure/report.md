# PLC5 Gap Closure Report

Generated: `2026-09-12T20:14:49.031847+00:00`

## Frozen blind baseline

- Preserved: **True**
- L5X matches freeze record: **True**

## Bridge fix

Blind v1 omitted `pe_devices` / IO and hard-capped conveyors at 40.
v2 uses `load_from_run` + SiteModel PE role enrichment.

## Discovery → generation

- Equipment SiteModel: `{'total': 79, 'INCLUDED': 79, 'AVAILABLE': 0, 'EXCLUDED': 0}`
- Conveyors compiler-consumed: **60**
- Conveyors generated: **60**
- Dispositions: `{'CONFIGURATION_REQUIRED': 19, 'GENERATED': 60}`
- PE discovered: **94** → generated: **94** (rungs **81**)
- IO points consumed: **395** → modules gen **61** / IO_MAP rungs **368**
- Encoders discovered: **5** → in L5X: **5**

## Taxonomy corrections

- E-stop: `{'legacy_count_labeled_zones': 90, 'estop_devices': 90, 'estop_circuits_or_aliases': 0, 'estop_zones_operational': 0, 'note': "EStop.asc rows were previously counted as 'E-stop zones'. Correct taxonomy: mostly ES devices/circuits; operational zones require explicit zone membership.", 'device_samples': ['4ES', '5ES', '6ES', 'ES422', 'ES500', 'ES610F', 'ES610G', 'ES610H', 'ES610I', 'ES610J', 'ES610K', 'ES612F', 'ES612G', 'ES612H', 'ES612I', 'ES612J', 'ES612K', 'ES708B', 'ES708C', 'ES710B'], 'zone_samples': []}`
- Full/FullJam: `{'legacy_full_groups_count': 79, 'full_pe_detectors': 59, 'fulljam_detectors': 20, 'jamcheck_relationships': 162, 'note': "Prior 'Full groups' counted Full/FullJam PE relationship heads, not operational conveyor groups. Do not treat every conveyor as a Full group."}`

- Structural L5X ok: **True**
- Candidate v2: `C:\dev\worktree\FortnaPlus\exports\cp5-gap-closure\generated\ORNCCP5_candidate_v2.L5X`
- SHA256: `27c5a003f8f5f9fb2e402057a39f7572d1e47cafc957ca9102deea86a6c9d99e`
