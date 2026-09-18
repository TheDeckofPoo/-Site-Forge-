# FortnaPlus Parts / Conveyor Model (Gate C)

**Branch:** `feature/plc2-transport-fidelity`  
**Status:** Documentation only this checkpoint — **do not** replace frozen Transport / physical-layout geometry in production code here.  
**UI name:** FortnaPlus `Parts_Menu` (fortna.mnu) edits the **Conveyor** table.

Finished / gold PLCs are **validation oracles only**.

---

## Purpose

Document Curtis Parts_Menu / Conveyor field semantics, classify evidence confidence, and separate:

1. Equipment identity  
2. Display geometry  
3. Physical geometry  
4. I/O  
5. Logical references  

Also record how Site Forge should prioritize FortnaPlus geometry fields vs current physical-layout-derived geometry — **document only** unless a later checkpoint proves a conclusive code change.

---

## Schema source (PROVEN)

RUN header (delimiter `~`) from `Conveyor.asc` — 60 columns. Primary identity: `IO_Name`.

FortnaPlus UI title `Parts_Menu` maps to this table (`artifacts/mnu-schema.json` first field label `Parts_Menu`; DLIST name token `Parts` → `Conveyor`).

### Field groups

#### 1. Equipment identity — PROVEN

| Field | Class | Notes |
|-------|-------|-------|
| `IO_Name` | **PROVEN** | Catalog identity (P-tag, motor, PE, PB, logical name, …) |
| `Type` | **PROVEN** | `convtype` vocabulary — discriminates class; `INVALID` ≠ delete row |
| `General_Description` | **PROVEN** | Free text |
| `Device_Description` | **PROVEN** | Lookup `convdesc` |
| `Part_Number` | **PROVEN** | Lookup `partnum` |
| `Machine_Name` | **PROVEN** | Owner controller → `Machine` |
| `ProcNum` | **PROVEN** | Process type lookup |
| `Layer` | **PROVEN** | Drawing layer filter |

#### 2. Display geometry — DERIVED in Site Forge (from physical + presentation)

FortnaPlus itself draws from the same ASC geometry columns (see `LEGACY_LAYOUT_DATA_RESEARCH.md`). Site Forge additionally maintains presentation fields that are **not** RUN ASC columns:

| Concept | Class | Notes |
|---------|-------|-------|
| `entryCanvas` / `exitCanvas` / `pathCanvas` | **DERIVED** | Site Forge schematic presentation |
| `sourceAngle` / display offsets | **DERIVED** / presentation | Not elbow chirality proof |
| `display_*` / `controlPanel` layout | **DERIVED** | Stripped on Canonical Apply |

These must never be written back as if they were FortnaPlus Parts fields.

#### 3. Physical geometry — PROVEN (RUN) with known limits

| Field | Class | Notes |
|-------|-------|-------|
| `X_cord`, `Y_cord` | **PROVEN** | Infeed / ENTRY end (not footprint center) — calibrated HIGH |
| `Length` | **PROVEN** | Centerline body length; `CURVE` uses sentinel `-1` |
| `Width` | **PROVEN** | Cross-belt / frame width |
| `Angle` | **PROVEN** | Flow deg CCW from +X at infeed (non-curve HIGH) |
| `Inside_Radius` | **PROVEN** | Inner curve radius |
| `Infeed_Tangent`, `Discharge_Tangent` | **PROVEN** | Stub lengths — not topology FKs |
| `Belt_Width` | **PROVEN** when populated | May duplicate/relate Width |
| `Infeed_Elevation`, `Discharge_Elevation` | **PROVEN** when populated | Z hints |
| `NoseOver` | **PROVEN** feature flag | Equipment feature, not FK |
| `b`, `c`, `sweep` analogs | **PROVEN** raw / **REVIEW_REQUIRED** for chirality | Do not invent L/R elbows |
| Curve physical L/R elbow | **UNKNOWN** | Explicitly not proven |

Binding transform (already accepted for Transport schematic): [`docs/RUN_GEOMETRY_CALIBRATION.md`](../RUN_GEOMETRY_CALIBRATION.md).

#### 4. I/O — PROVEN when populated

| Field | Class | Notes |
|-------|-------|-------|
| `IO_Address_Word`, `IO_Address_Bit` | **PROVEN** | Soft addressing hints; Configio remains physical endpoint authority |
| `IO_Module_Type` | **PROVEN** | Optional → IOCard vocabulary |
| `Contact_Type` | **PROVEN** | Lookup |
| `Disable I/O`, `Overide I/O` | **PROVEN** bit masks when used | Optional force paths |
| `Important_IO` | **PROVEN** flag | |
| Physical endpoint truth | **PROVEN** via Configio | Never fuzzy-collapse lettered identities |

#### 5. Logical / relationship refs — PROVEN schema, mixed instance

| Field | Class | Notes |
|-------|-------|-------|
| `Motor` | **PROVEN** schema; often empty on mechanical rows | Same-table Conveyor identity when set |
| `Drive` | **PROVEN** schema; often empty | VFD/drive identity when set |
| `In Motor Chain` | **DERIVED** relationship flag | Membership proven by Mtrchain reverse lookup |
| `Trigger1..4` | **PROVEN** when not INVALID | → Trigrset |
| `TriggerLink_Name` / `TriggerLink_NDX` | **PROVEN** when set | |
| `ErrLink`, `ErrTime` | **PROVEN** when set | |
| Jamzones / Mtrchain selections **to** this IO_Name | **PROVEN** via CP3 | Row may be Type=INVALID logical signal |

---

## Curtis Parts_Menu ↔ RUN ASC equivalence

| Curtis / UI concern | RUN Conveyor field | Confidence |
|---------------------|--------------------|------------|
| Part name / IO_Name | `IO_Name` | **PROVEN** |
| X / Y | `X_cord` / `Y_cord` | **PROVEN** |
| Length / Width | `Length` / `Width` | **PROVEN** |
| Angle | `Angle` | **PROVEN** |
| Type | `Type` | **PROVEN** |
| Inside_Radius | `Inside_Radius` | **PROVEN** |
| Motor | `Motor` (+ Mtrchain for chains) | **PROVEN** schema; instance often via Mtrchain |
| In Motor Chain | `In Motor Chain` | **PROVEN** flag; chain members via Mtrchain |

No separate proprietary layout file exists in RUN archives for conveyor body geometry — ASC **is** the layout database (`LEGACY_LAYOUT_DATA_RESEARCH.md`).

---

## Separation rules

```
EQUIPMENT IDENTITY     IO_Name + Type + Machine_Name
        │
        ├── PHYSICAL GEOMETRY   X/Y/Length/Width/Angle/Inside_Radius/tangents
        │         └── interpreter → entry/exit anchors (DERIVED)
        │
        ├── DISPLAY GEOMETRY    canvas path / presentation offsets (DERIVED)
        │
        ├── I/O                 word/bit + Configio endpoint authority
        │
        └── LOGICAL REFS        other tables SELECTION → this IO_Name
                                (Type=INVALID rows remain valid targets)
```

Mechanical emit filters (`STRAIGHT`/`CURVE`/…) apply only to **transport belt generation**, not to catalog retention for LogicalSignalModel.

---

## Geometry authority recommendation (Site Forge)

**Question:** Should Site Forge prioritize FortnaPlus X/Y/Length/Width/Angle/Type/Inside_Radius over current physical-layout-derived geometry?

**Answer (this checkpoint — conclusive for authority, non-conclusive for code rewrite):**

| Layer | Authority | Recommendation |
|-------|-----------|----------------|
| Raw physical placement | FortnaPlus / RUN `X_cord`…`Inside_Radius` | **PRIMARY** — already the calibrated source in `RUN_GEOMETRY_CALIBRATION.md` / `fortna_physical_geometry.py` |
| Interpreted anchors | Deterministic transform of RUN fields | **DERIVED** — keep interpreter; do not invent chirality |
| Display canvas | Site Forge presentation (`pathCanvas`, offsets) | **SECONDARY** — may mate/nudge for readability; never mutate raw RUN; stripped on Apply |
| Engineer override | ENGINEER_ASSIGNED workbook edits | Wins for effective model when explicitly set |
| Finished PLC / prints | Validation oracle / visual confirm only | Never discovery |

**Code action this checkpoint:** **NONE.** Transport physical-layout path is frozen for PLC2 fidelity work. Document prioritization only:

1. Prefer RUN Parts geometry as physical truth.  
2. Treat display geometry as derived presentation.  
3. Do not replace Transport geometry implementation here.  
4. Do not drive physical layout from Type=INVALID logical catalog rows (geometry usually zeroed / non-mechanical).

If a future checkpoint finds divergence between “physical-layout-derived” caches and RUN fields, RUN Parts fields win unless ENGINEER_ASSIGNED says otherwise.

---

## Confidence vocabulary used

| Level | Meaning |
|-------|---------|
| **PROVEN** | Explicit RUN / schema |
| **DERIVED** | Deterministic from PROVEN |
| **ENGINEER_REQUIRED** / **ENGINEER_ASSIGNED** | Must be supplied or confirmed |
| **UNKNOWN** | No accepted evidence (e.g. curve L/R elbow) |
| **REVIEW_REQUIRED** | Evidence exists but ambiguous |

**Never:** GUESSED / ASSUMED / PROBABLY.

---

## Related

- [`FORTNAPLUS_OBJECT_TAXONOMY.md`](FORTNAPLUS_OBJECT_TAXONOMY.md)
- [`../RUN_GEOMETRY_CALIBRATION.md`](../RUN_GEOMETRY_CALIBRATION.md)
- [`../RUN_GEOMETRY_INVESTIGATION.md`](../RUN_GEOMETRY_INVESTIGATION.md)
- [`../LEGACY_LAYOUT_DATA_RESEARCH.md`](../LEGACY_LAYOUT_DATA_RESEARCH.md)
- [`../TRANSPORT_PHYSICAL_DRAWING.md`](../TRANSPORT_PHYSICAL_DRAWING.md)
- [`LOGICAL_SIGNAL_MODEL.md`](LOGICAL_SIGNAL_MODEL.md)
