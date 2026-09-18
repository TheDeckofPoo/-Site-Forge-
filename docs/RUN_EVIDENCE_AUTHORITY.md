# RUN Evidence Authority Matrix

> Part of the evidence repository — start at [`docs/evidence/README.md`](evidence/README.md).

**Purpose:** Site Forge must not treat every RUN file as equal evidence.  
Authority depends on the **engineering fact** being reconstructed.

**Branch lineage:** `feature/plc2-transport-fidelity`  
**Machine-readable twin:** `config/run_evidence_authority.json`

Finished / gold PLCs are **validation oracles only** — never discovery sources.

---

## Two different concepts (do not conflate)

### 1. File resolution precedence (which physical file FortnaPlus opens)

Proven FortnaPlus runtime order for a logical table `Table`:

1. `Table.rom.<MACHINE>`
2. `Table.rom`
3. `Table.asc.<MACHINE>`
4. `Table.asc`

This answers: *which file is loaded for this machine.*

### 2. Semantic authority (which table establishes this engineering fact)

Example: `MergeInputs.asc.ORNCCP2` wins file resolution over `MergeInputs.asc`,  
but MergeInputs only has authority for facts its schema actually establishes  
(e.g. lane membership) — not for Configio physical endpoints.

---

## Confidence vocabulary

| Level | Meaning |
|-------|---------|
| **PROVEN** | Explicit RUN value or Fortna schema/runtime relationship establishes the fact |
| **DERIVED** | Deterministic transform/cross-table link from PROVEN evidence |
| **ENGINEER_ASSIGNED** | Engineer supplied/corrected in Site Forge; authoritative in effective model |
| **REVIEW_REQUIRED** | Evidence exists but is insufficient for a unique safe interpretation |
| **UNKNOWN** | No accepted evidence |

**Never:** GUESSED / ASSUMED / PROBABLY.

Naming similarity alone must **never** outrank explicit physical or relational evidence  
(e.g. `M220_AUX` ≠ `M220A_AUX` when Configio proves distinct endpoints).

---

## Evidence authority matrix (initial — validated against CP1–CP4 semantics)

| Engineering Fact | Primary Evidence | Supporting Evidence | Fallback |
|------------------|------------------|---------------------|----------|
| Equipment existence | Conveyor | schema relationships | REVIEW_REQUIRED |
| Equipment type (STRAIGHT/CURVE/…) | Conveyor.Type | — | UNKNOWN |
| Motor ↔ conveyor chain | Mtrchain | Conveyor | REVIEW_REQUIRED |
| Merge identity | MergeBoss | schema relationships | UNKNOWN |
| Merge type (SPUR/2-1/3-1) | MergeBoss | MergeInputs | UNKNOWN |
| Merge lane membership | MergeInputs | ReleaseIO / Mtrchain | REVIEW_REQUIRED |
| Jam relationship | Jamcheck / Jamzones | schema relationships | REVIEW_REQUIRED |
| Physical I/O endpoint | Configio | EIPModules / schema | REVIEW_REQUIRED |
| Safety device existence | EStop / Conveyor IO / Safety tables | schema refs | REVIEW_REQUIRED |
| Safety zone membership | ENGINEER_ASSIGNED (Safety Build) | RUN-proven only when confidence HIGH | REVIEW_REQUIRED |
| Display geometry (X/Y/path) | entryCanvas / exitCanvas / pathCanvas / sourceAngle | sweepDeg / insideRadius / b | deterministic Site Forge layout |
| Curve *display* heading | entry→exit vector (PROVEN geometry) | pathCanvas chord / sourceAngle | symbolic fallback angle |
| Curve *physical* L/R elbow | — | — | **UNKNOWN** (do not invent) |
| Sorter existence | `Sorters` (active `Sorter Name` on resolved overlay) | `SrtAppControl` | UNKNOWN |
| Sorter identity | `Sorters.Sorter Name` + `Machine` | encoder link / `SrtAppControl` | UNKNOWN |
| Sorter type class | — (name tokens only) | engineer confirm | REVIEW_REQUIRED |
| Sorter divert lane topology | `SrtZoneLane` | `SrtScanBoss` | REVIEW_REQUIRED |
| Sorter divert **output IO** | `Outpoints` ⋈ `SrtZoneLane.Lane` when PROVEN | LaneEnableSignal (often INVALID) | REVIEW_REQUIRED |
| Sorter induct PE | `Inpoints.Induct I/O Name` | Conveyor Type=PHOTOCELL | REVIEW_REQUIRED |
| Sorter induct / tracking conveyor | Encoders.EnableBit → Mtrchain → Conveyor (**DERIVED**) | — | ENGINEER confirm |
| Sorter tracking PE | `Inpoints` per section | — | REVIEW_REQUIRED |
| Sorter encoder | `Sorters.Encoder` → `Encoders` | ticks/ft | UNKNOWN |
| Sorter track offset / trigger | Outpoint Location (per-lane) / Trig window when present | encoder scale | UNKNOWN / NOT_SUPPORTED |
| WCS interface **presence** | finished-PLC / task schedule = **validation oracle only** | RUN has no WCS program table | UNKNOWN until pack rules proven; PLC2 proves optional |
| WCS configuration (IP/port/…) | engineer / site commissioning | — | ENGINEER_ASSIGNED |
| FortnaPlus field reference target menu | `.mnu` DLIST / `find_data_source` / CP3 graph | `artifacts/mnu-relationships.json` | UNKNOWN |
| Jamzones enable/jam/button refs | Jamzones field → **Conveyor** / **timemenu** / **Machine** / **StartStopZones** (CP3) | Conveyor.Type classifies physical vs logical catalog row — Type=INVALID ≠ void | PROVEN target menu; REVIEW for physical endpoint |
| Mtrchain motor/chain refs | Mtrchain field → **Conveyor** / **timemenu** / **horns** / **Jamzones** (CP3) | Conveyor.Type per member | PROVEN target menu; INVALID slot = absent |
| Timer reference | field → `timemenu` | timer ASC | PROVEN when CP3 RESOLVED |
| Internal / logical Conveyor signal | Conveyor catalog identity selected by Jamzones/Mtrchain (often Type=INVALID) | CP3 edge + Conveyor row | PROVEN as named ref; not a mechanical belt |
| Absent Fortna reference | explicit `INVALID` / empty token | — | keep ABSENT (never invent BOOL) |
| Sorter_Track program architecture | — (not RUN) | PLC5 RTfinished / gold pack **oracle only** | NOT discovery authority |
| Sorter ↔ WCS handshake tags | — (not RUN) | Dual-referenced controller tags in PLC5 oracle (34 roots) | Oracle-only; emit via WCSModel/engineer |
| Physical I/O endpoint | Configio | EIPModules / NODE Desc | REVIEW_REQUIRED |

See also:

- `exports/stabilization/sorter_evidence_inventory.md` / `plc5_sorter_deep_autofill.md`
- [`docs/evidence/LOGICAL_SIGNAL_MODEL.md`](evidence/LOGICAL_SIGNAL_MODEL.md)
- [`docs/evidence/SORTER_TRACK_PROGRAM_PACK.md`](evidence/SORTER_TRACK_PROGRAM_PACK.md)
- [`docs/evidence/WCS_PROGRAM_PACK.md`](evidence/WCS_PROGRAM_PACK.md)
- [`docs/PLC_PROGRAM_PACK_ARCHITECTURE.md`](PLC_PROGRAM_PACK_ARCHITECTURE.md)
- `config/program_packs/*.json`

---

## Explainable evidence (data model requirement)

A reconstructed fact should be able to carry provenance conceptually like:

```json
{
  "value": "CURVE",
  "confidence": "PROVEN",
  "evidence": [
    {
      "table": "Conveyor",
      "record": "P316",
      "field": "Type",
      "value": "CURVE",
      "sourceFile": "Conveyor.asc.ORNCCP2",
      "authority": "PRIMARY"
    }
  ]
}
```

Derived:

```json
{
  "value": "...",
  "confidence": "DERIVED",
  "derivation": "...",
  "evidence": []
}
```

Unresolved:

```json
{
  "value": null,
  "confidence": "REVIEW_REQUIRED",
  "reason": "..."
}
```

UI “Why does Site Forge think this?” may come later; the **model** is required now.

---

## Geometry evidence classification (CURVE display)

| Field | Class | Use |
|-------|-------|-----|
| entryCanvas | PROVEN | Display anchor / direction vector |
| exitCanvas | PROVEN | Display anchor / direction vector |
| pathCanvas | PROVEN | Chord fallback for display heading |
| sourceAngle | PROVEN | Display heading fallback (not elbow chirality) |
| b / runB | PROVEN | Raw RUN; not used to invent L/R |
| sweepDeg | PROVEN | Raw RUN; elbow paint still UNKNOWN |
| insideRadius | PROVEN | Raw RUN; elbow paint still UNKNOWN |
| displayOrientation L/R | UNKNOWN | Do not synthesize elbows |
| presentation_offsets | DERIVED | Site Forge layout only |
