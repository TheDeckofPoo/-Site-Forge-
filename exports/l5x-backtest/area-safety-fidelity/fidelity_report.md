# Autogen Area/Safety Fidelity — Greensboro

Before area accuracy: **0.0%** (0 / 18)
Before safety accuracy: **0.0%**

After area accuracy: **100.0%** (53 / 53)
After safety accuracy: **100.0%** (53 / 53)

Overlap workbook fidelity: area 53/53, safety 53/53

## Example corrected conveyors

- **P1000** area=`Trash_Area` safety=`Trash_ESZone1` (reference area=`Trash_Area` safety=`Trash_ESZone1`)
- **P1001** area=`Trash_Area` safety=`Trash_ESZone1` (reference area=`Trash_Area` safety=`Trash_ESZone1`)
- **P1002** area=`Trash_Area` safety=`Trash_ESZone1` (reference area=`Trash_Area` safety=`Trash_ESZone1`)
- **P1004** area=`Trash_Area` safety=`Trash_ESZone1` (reference area=`Trash_Area` safety=`Trash_ESZone1`)
- **P1005** area=`Trash_Area` safety=`Trash_ESZone1` (reference area=`Trash_Area` safety=`Trash_ESZone1`)
- **P1006** area=`Trash_Area` safety=`Trash_ESZone2` (reference area=`Trash_Area` safety=`Trash_ESZone2`)

## Root cause

RUN seed assigns {machine}_Area / {machine}_ESZone1. apply_workbook_to_input previously rebuilt inp.safety_zones as always '{AreaBase}_ESZone1', dropping engineer zones like ModuleB_ESZone2 from the zone list. Conveyor row main_area/safety_zone overlays were already applied to ConveyorRow; Fast_Conv uses those row fields. Fix preserves explicit conveyor safety zones in inp.safety_zones and regenerates with workbook metadata present.
