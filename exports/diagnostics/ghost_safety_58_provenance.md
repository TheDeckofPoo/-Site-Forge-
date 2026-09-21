# Ghost Safety inventory — 58-device provenance

**Verdict: A_ONE_CONTROLLER_CORRECT_INVENTORY_RETAINED_AFTER_CLEAR (case A)**

Exact set equality with discover_safety_devices(ORNCCP2): 58/58. All Conveyor.asc Machine_Name values are ORNCCP2. T_* names are alias forms of the same stems. 2MCR/3MCR and 2ESR/3ESR coexist because ORNCCP2's own Conveyor table contains both numeric families under Machine_Name=ORNCCP2 — not because sibling Reno controllers were unioned.

## Discovery vs scope

DISCOVERY IMPROVED: inventory includes MCR/ESR AUX + T_ aliases (2ESR1_AUX, T_2ESR1_AUX, 2MCR1_AUX, 3MCR1, …) that earlier incomplete Safety surfaces often omitted. SCOPE/LIFETIME BUG: that correct ORNCCP2 inventory was retained with NO active RUN via unscoped localStorage siteforge.safetyBuild.v1 hydrate (addressed in 94aee34 — hasActiveSite + never restore devices).

- archive_sha: `ff84f240ac83c1c15aaeecaff200c724ed02bf4deb1429438afafbd092974eab`
- project: OReillyGreensboro
- machine: **ORNCCP2** (all 58)
- kinds: {'ESTOP': 10, 'ESLS': 24, 'ESR': 16, 'MCR': 8}
- MSCRENOSHIP overlap: 0

## Device provenance

| name | kind | machine | source | row | fact_uid |
| --- | --- | --- | --- | ---: | --- |
| `2ES` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 707 | `sf_e0bedd285503199b` |
| `3ES` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 889 | `sf_113ea1aea93a94ec` |
| `ES1002` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 709 | `sf_0e98b26f4f0919f3` |
| `ES1008` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 891 | `sf_742fca95cbae7854` |
| `ES1014` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 892 | `sf_050f29fb03e5b780` |
| `ES1018` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 893 | `sf_0d4196b13c1f903b` |
| `ES400` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 890 | `sf_10e3836b1b10910a` |
| `ES406` | ESTOP | ORNCCP2 | Conveyor.asc via discover_safety_devices | 708 | `sf_89ef307037face67` |
| `T_2ES` | ESTOP | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 707 | `sf_e0bedd285503199b` |
| `T_3ES` | ESTOP | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 889 | `sf_113ea1aea93a94ec` |
| `ESLS125` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 710 | `sf_df2f3eb9bebdd9c2` |
| `ESLS125A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1334 | `sf_fcc270cf3d20b6b0` |
| `ESLS127` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 711 | `sf_cfb2b2125a77580b` |
| `ESLS127A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1335 | `sf_0c48778d2cce5b78` |
| `ESLS141` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 896 | `sf_8c987adff182ae84` |
| `ESLS141A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1340 | `sf_8c95f8f3dd23a3ff` |
| `ESLS143` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 894 | `sf_cae5b207380226e1` |
| `ESLS143A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1341 | `sf_1eada90c1f6a094f` |
| `ESLS221` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 712 | `sf_da1ab5a5566ee792` |
| `ESLS221A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1336 | `sf_6f4fd555c32a0ab1` |
| `ESLS223` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 713 | `sf_f0eaa646da156716` |
| `ESLS223A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1337 | `sf_b15f7906c1efb504` |
| `ESLS235` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 895 | `sf_b3db2e98b78a605e` |
| `ESLS235A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1342 | `sf_160bbe5019bb7c4b` |
| `ESLS237` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 874 | `sf_9bb59ef27c14371e` |
| `ESLS237A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1343 | `sf_78a63afac7d2a449` |
| `ESLS311` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 714 | `sf_188c1a630c88d449` |
| `ESLS311A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1338 | `sf_24cdad08e554c64d` |
| `ESLS313` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 715 | `sf_3e7af2b14f6b3df5` |
| `ESLS313A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1339 | `sf_26e94e9d62222e43` |
| `ESLS319` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 875 | `sf_1254ccbda2dc2486` |
| `ESLS319A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1344 | `sf_83032ac7ff3825d5` |
| `ESLS321` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 876 | `sf_6da9c21c2fd3e4e8` |
| `ESLS321A` | ESLS | ORNCCP2 | Conveyor.asc via discover_safety_devices | 1345 | `sf_447ec4aac2f6f806` |
| `2ESR1_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 704 | `sf_8a3f6aeb381cfefd` |
| `2ESR2_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 705 | `sf_088d2c10c4b5b1b8` |
| `2ESR3_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 706 | `sf_2a7bbb04bfd3514b` |
| `3ESR1_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 884 | `sf_98854129dd8a0c19` |
| `3ESR2_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 885 | `sf_45e3458d0fd451f6` |
| `3ESR3_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 886 | `sf_c93fc2083bc1d6fd` |
| `3ESR4_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 887 | `sf_7ff1f99ad9ae1024` |
| `3ESR5_AUX` | ESR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 888 | `sf_33e023f251cced51` |
| `T_2ESR1_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 704 | `sf_8a3f6aeb381cfefd` |
| `T_2ESR2_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 705 | `sf_088d2c10c4b5b1b8` |
| `T_2ESR3_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 706 | `sf_2a7bbb04bfd3514b` |
| `T_3ESR1_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 884 | `sf_98854129dd8a0c19` |
| `T_3ESR2_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 885 | `sf_45e3458d0fd451f6` |
| `T_3ESR3_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 886 | `sf_c93fc2083bc1d6fd` |
| `T_3ESR4_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 887 | `sf_7ff1f99ad9ae1024` |
| `T_3ESR5_AUX` | ESR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 888 | `sf_33e023f251cced51` |
| `2MCR1` | MCR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 698 | `sf_6d2870fddcc61a39` |
| `2MCR1_AUX` | MCR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 703 | `sf_8fe94dd4541c4bcc` |
| `3MCR1` | MCR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 901 | `sf_1a6bcd939f3b7fe6` |
| `3MCR1_AUX` | MCR | ORNCCP2 | Conveyor.asc via discover_safety_devices | 883 | `sf_03aaac34dce1b739` |
| `T_2MCR1` | MCR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 698 | `sf_6d2870fddcc61a39` |
| `T_2MCR1_AUX` | MCR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 703 | `sf_8fe94dd4541c4bcc` |
| `T_3MCR1` | MCR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 901 | `sf_1a6bcd939f3b7fe6` |
| `T_3MCR1_AUX` | MCR | ORNCCP2 | claim_ledger_T_alias_of_Conveyor | 883 | `sf_03aaac34dce1b739` |