# Autogen L5X Structural Backtest

- Generated: `C:\dev\worktree\FortnaPlus\exports\cp2-gate\generated\OReillyGreensboro_ORNCCP2.L5X`
- Reference: `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X`

## Summary metrics

```
AUTOGEN L5X BACKTEST

Conveyor coverage        18 / 57   31.6%
Downstream accuracy      4 / 18   22.2%
Area accuracy            0 / 18   0.0%
Safety-zone accuracy     0 / 18   0.0%
Exit-PE accuracy         4 / 18   22.2%

Fast_Conv coverage       18 / 57  (gen 37)
Slow_Flt coverage        18 / 57  (gen 37)
Slow_Jam coverage        18 / 57  (jam cfg matches 12)
Full_PE                  0 / 7  (gen 11)
Merge_2to1               0 / 0  (gen 0)
```

No single overall accuracy is reported. Category metrics are independent. The reference PLC may be unfinished/manual; differences are classifications, not always errors.

## Classification counts

- `AREA_MISMATCH`: 18
- `EXTRA_GENERATED`: 19
- `MISSING_GENERATED`: 39
- `PE_MISMATCH`: 20
- `PROGRAM_STRUCTURE_DIFFERENCE`: 24
- `SAFETY_MISMATCH`: 18
- `TOPOLOGY_MISMATCH`: 14

## Conveyor inventory

- Generated Fast_Conv conveyors: **37**
- Reference Fast_Conv conveyors: **57**
- Exact tag overlap: **18**
- Missing (in reference only): P1001, P1005, P1007, P1011, P1015, P1016, P123, P124, P128, P130A, P130B, P130C, P130D, P130E, P132, P136_P1_Conv, P136_P2_Conv, P139, P140, P144, P145A, P145B, P145C, P145D, P145E, P146, P150_P1_Conv, P150_P2_Conv, P220, P220A, P222, P233, P234, P236, P240, P309, P310, P317, P318
- Extra (in generated only): P100, P101, P126, P134, P136, P136A, P142, P148, P150, P150A, P215, P226, P229, P230, P232, P238, P316, P324, P408

## Per-conveyor differences (mismatches / missing / extra)

### P1001 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone1`
- downstream   MISSING  gen=`None` ref=`P1002`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P1005 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone1`
- downstream   MISSING  gen=`None` ref=`P1002`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P1007 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone2`
- downstream   MISSING  gen=`None` ref=`P1008`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P1011 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone2`
- downstream   MISSING  gen=`None` ref=`P1008`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P1015 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone2`
- downstream   MISSING  gen=`None` ref=`P1016`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P1016 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`Trash_Area`
- safety_zone  MISSING  gen=`None` ref=`Trash_ESZone2`
- downstream   MISSING  gen=`None` ref=`P1018`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P123 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P124`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P124 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P128`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P128 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P130A`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P130A — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P130B`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P130B — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P130C`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P130C — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P130D`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P130D — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P130E`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P130E — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P132`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P132 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P136_P1_Conv`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P136_P1_Conv — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P136_P2_Conv`
- exit_pe      MISSING  gen=`None` ref=`PE136_P1`

### P136_P2_Conv — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`P138`
- exit_pe      MISSING  gen=`None` ref=`PE136_P2`

### P139 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P140`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P140 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P144`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P144 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P145A`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P145A — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P145B`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P145B — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P145C`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P145C — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P145D`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P145D — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P145E`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P145E — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P146`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P146 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P150_P1_Conv`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P150_P1_Conv — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P150_P2_Conv`
- exit_pe      MISSING  gen=`None` ref=`PE150_P1`

### P150_P2_Conv — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P400`
- exit_pe      MISSING  gen=`None` ref=`PE150_P2`

### P220 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P222`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P220A — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P220`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P222 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone2`
- downstream   MISSING  gen=`None` ref=`NO_CONV`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P233 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P234`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P234 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P236`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P236 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P240`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P240 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone2`
- downstream   MISSING  gen=`None` ref=`P242`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P309 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P310`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P310 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleB_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleB_ESZone1`
- downstream   MISSING  gen=`None` ref=`P312`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P317 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P318`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P318 — `MISSING_GENERATED`

- area         MISSING  gen=`None` ref=`ModuleC_Area`
- safety_zone  MISSING  gen=`None` ref=`ModuleC_ESZone1`
- downstream   MISSING  gen=`None` ref=`P320`
- exit_pe      MISSING  gen=`None` ref=`NO_PE`

### P100 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P101 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P126 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE126_JF` ref=`None`

### P134 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE134_JF` ref=`None`

### P136 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`EZPE136_P1` ref=`None`

### P136A — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P142 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE142_JF` ref=`None`

### P148 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE148_JF` ref=`None`

### P150 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`EZPE150_P1` ref=`None`

### P150A — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P215 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE215_J` ref=`None`

### P226 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE226_JF` ref=`None`

### P229 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P230 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`EZPE230_P` ref=`None`

### P232 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE232_P` ref=`None`

### P238 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE238_JF` ref=`None`

### P316 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE316_J` ref=`None`

### P324 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`PE324_J` ref=`None`

### P408 — `EXTRA_GENERATED`

- area         EXTRA    gen=`ORNCCP2_Area` ref=`None`
- safety_zone  EXTRA    gen=`ORNCCP2_ESZone1` ref=`None`
- downstream   EXTRA    gen=`NO_CONV` ref=`None`
- exit_pe      EXTRA    gen=`NO_PE` ref=`None`

### P1000 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone1`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1001`
- exit_pe      MISMATCH
    - generated: `PE1000_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1002 — `AREA_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone1`
- downstream   MATCH      `NO_CONV`
- exit_pe      MISMATCH
    - generated: `PE1002_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1004 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone1`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1005`
- exit_pe      MISMATCH
    - generated: `PE1004_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1006 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1007`
- exit_pe      MISMATCH
    - generated: `PE1006_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1008 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1014`
- exit_pe      MISMATCH
    - generated: `PE1008_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1010 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1011`
- exit_pe      MISMATCH
    - generated: `PE1010_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1014 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P1015`
- exit_pe      MISMATCH
    - generated: `PE1014_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P1018 — `AREA_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `Trash_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `Trash_ESZone2`
- downstream   MATCH      `NO_CONV`
- exit_pe      MISMATCH
    - generated: `PE1018_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `Trash_Area_Area_Fast`

### P138 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P406`
- exit_pe      MATCH      `PE138_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

### P242 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleC_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleC_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P400`
- exit_pe      MISMATCH
    - generated: `EZPE242_P`
    - reference: `PE242_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleC_Area_Area_Fast`

### P312 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone1`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P314`
- exit_pe      MISMATCH
    - generated: `EZPE312_P`
    - reference: `PE312_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

### P314 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P136_P2_Conv`
- exit_pe      MATCH      `PE314_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

### P320 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleC_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleC_ESZone1`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P322`
- exit_pe      MISMATCH
    - generated: `EZPE320_P`
    - reference: `PE320_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleC_Area_Area_Fast`

### P322 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleC_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleC_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P150_P2_Conv`
- exit_pe      MATCH      `PE322_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleC_Area_Area_Fast`

### P400 — `AREA_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleC_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleC_ESZone2`
- downstream   MATCH      `NO_CONV`
- exit_pe      MISMATCH
    - generated: `PE400_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleC_Area_Area_Fast`

### P402 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P404`
- exit_pe      MISMATCH
    - generated: `EZPE402_P`
    - reference: `PE402_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

### P404 — `TOPOLOGY_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone2`
- downstream   MISMATCH
    - generated: `NO_CONV`
    - reference: `P406`
- exit_pe      MATCH      `PE404_P`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

### P406 — `AREA_MISMATCH`

- area         MISMATCH
    - generated: `ORNCCP2_Area`
    - reference: `ModuleB_Area`
- safety_zone  MISMATCH
    - generated: `ORNCCP2_ESZone1`
    - reference: `ModuleB_ESZone2`
- downstream   MATCH      `NO_CONV`
- exit_pe      MISMATCH
    - generated: `PE406_J`
    - reference: `NO_PE`
- add_pe       MATCH      `NO_PE`
- program      MISMATCH
    - generated: `ORNCCP2_Area_Fast`
    - reference: `ModuleB_Area_Area_Fast`

## Slow_Jam

- Coverage: gen 37 / ref 57; jam config matches on overlap: 12
- Missing conveyors: P1001, P1005, P1007, P1011, P1015, P1016, P123, P124, P128, P130A, P130B, P130C, P130D, P130E, P132, P136_P1_CONV, P136_P2_CONV, P139, P140, P144, P145A, P145B, P145C, P145D, P145E, P146, P150_P1_CONV, P150_P2_CONV, P220, P220A, P222, P233, P234, P236, P240, P309, P310, P317, P318
- Extra conveyors: P100, P101, P126, P134, P136, P136A, P142, P148, P150, P150A, P215, P226, P229, P230, P232, P238, P316, P324, P408
- P242: gen=['EZPE242_P'] ref=['PE242_P']
- P312: gen=['EZPE312_P'] ref=['PE312_P']
- P314: gen=['PE314_P'] ref=['PE314_P', 'PE316_J']
- P320: gen=['EZPE320_P'] ref=['PE320_P']
- P322: gen=['PE322_P'] ref=['PE322_P', 'PE324_J']
- P402: gen=['EZPE402_P'] ref=['PE402_P']

## Full_PE

- gen 11 / ref 7; matched PE tags 0
- Missing PEs: PE136_F1, PE136_F2, PE150_F1, PE150_F2, PE242_F, PE312_F, PE320_F
- Extra PEs: EZPE136_F1, EZPE136_F2, EZPE150_F1, EZPE150_F2, EZPE229_F, EZPE230_F, EZPE242_F, EZPE312_F, EZPE320_F, EZPE402_F, EZPE408_F

## Merge_2to1

- Generated merges: 0
- Reference merges: 0
- No Merge_2to1 call sites found in either L5X (not necessarily an error).

## Programs

| Program | Status | Gen class | Ref class |
|---|---|---|---|
| ES | MISSING | — | other |
| HMI | MISSING | — | other |
| IO_MAP | MATCH | io_map | io_map |
| MSG | MISSING | — | other |
| ModuleB_Area_Area_Fast | MISSING | — | area_fast |
| ModuleB_Area_Area_L1 | MISSING | — | area_l1 |
| ModuleB_Area_Area_L2 | MISSING | — | area_l2 |
| ModuleB_Area_Area_L3 | MISSING | — | area_l3 |
| ModuleB_Area_Area_Slow | MISSING | — | area_slow |
| ModuleC_Area_Area_Fast | MISSING | — | area_fast |
| ModuleC_Area_Area_L1 | MISSING | — | area_l1 |
| ModuleC_Area_Area_L2 | MISSING | — | area_l2 |
| ModuleC_Area_Area_L3 | MISSING | — | area_l3 |
| ModuleC_Area_Area_Slow | MISSING | — | area_slow |
| ORNCCP2_Area_Fast | EXTRA | area_fast | — |
| ORNCCP2_Area_L1 | EXTRA | area_l1 | — |
| ORNCCP2_Area_L2 | EXTRA | area_l2 | — |
| ORNCCP2_Area_Slow | EXTRA | area_slow | — |
| PLC_Fast | MISSING | — | other |
| Sys | MATCH | system | system |
| System | MISSING | — | system |
| Trash_Area_Area_Fast | MISSING | — | area_fast |
| Trash_Area_Area_L1 | MISSING | — | area_l1 |
| Trash_Area_Area_L2 | MISSING | — | area_l2 |
| Trash_Area_Area_L3 | MISSING | — | area_l3 |
| Trash_Area_Area_Slow | MISSING | — | area_slow |
