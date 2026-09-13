# PLC2 I/O Truth Model

**Branch:** `feature/plc2-io-truth`  
**Orchestrator:** `tools/scripts/fortna_plc2_io_truth.py`  
**Artifacts:** `exports/plc2-io-truth/`  
**Policy:** RUN tables are the generation source. Finished PLC2 is validation/oracle only. This pass does **not** modify `fortna_autogen.py` IO_MAP emit logic.

---

## Canonical hop chain

```
Automation Controller (project.cfg MACHINENAME)
  → IOCard / EthernetCard (RTA EtherNet/IP driver)
  → <Machine>-RTA-eipcfg.xml + EIPAdapters / EIPModules / EIPCSV
  → RIOAdapter (TargetIP, name) + IOModule (slot, catalog, banks)
  → FortnaWord (Configio.Octal_Word ↔ EIPCSV.Word ↔ module banks)
  → Bit (Conveyor.IO_Address_Bit within word)
  → LogicalPoint (Conveyor.IO_Name)
  → Device / Conveyor (Type, Motor, Drive, Machine_Name)
  → Mtrchain (Motor_Ndx / Motor_Aux / Motor_Chained*) equipment closure
```

Optional corroboration (do not fail if missing): `Jamzones`, `Jamcheck`, `StartStopZones`.

**Forbidden:** edges justified only by name similarity (e.g. “P4xx looks like PLC4”).

---

## IOEvidenceGraph schema

### Node types

| Type | Meaning | Typical source |
|------|---------|----------------|
| `Controller` | Automation Controller / AC | `project.cfg` `MACHINENAME` |
| `EthernetCard` | IO NIC / RTA EIP driver | `IOCard.asc` |
| `RIOAdapter` | Remote I/O adapter | eipcfg / `EIPAdapters` |
| `IOModule` | Slot card under adapter | eipcfg / `EIPModules` |
| `FortnaWord` | Fortna IO word (octal/decimal key) | `Configio.asc` `Octal_Word`, `EIPCSV.Word` |
| `Bit` | Bit within a Fortna word | `Conveyor.IO_Address_Bit` |
| `LogicalPoint` | Named I/O part | `Conveyor.IO_Name` |
| `Device` | Non-mechanical equipment | Conveyor `Type` ∈ PHOTOCELL/MOTOR/BEACON/… |
| `Conveyor` | Mechanical / display P-part | Conveyor mechanical types + `Mtrchain.Motor_Chained*` |

### Edge fields (required)

| Field | Purpose |
|-------|---------|
| `source` / `target` | Node ids |
| `source_table` | RUN table / file that justifies the hop |
| `source_row` | Row index when applicable |
| `field` | Column / attribute used |
| `confidence` | `HIGH` for explicit table fields |
| `documented_semantics` | Short statement of documented meaning |

No edge may be emitted from string similarity alone.

---

## Reverse-trace (finished → RUN)

Finished CP_I/CP_O rungs look like:

```
XIC(CP2RIO0:I.Data[1].0)OTE(CP2_CS.I.Start_PB);
```

Truth reconstruction:

1. Parse adapter / direction / Data[slot].bit from the channel.
2. Map finished AOI tag → Fortna part name candidates by **documented conventions only**  
   (e.g. `CP2_CS.I.Start_PB` → `2PBSTART`; `P400_MS.I.Auxiliary_Forward` → `M400_AUX`).
3. Resolve `Conveyor.asc` row → `IO_Address_Word` / `IO_Address_Bit`.
4. Confirm word ownership via `Configio.asc.<MACHINE>` `Octal_Word` (and EIPCSV when present).
5. Note adapter **name family** separately: finished `CP2RIO*` / `CP3RIO*` vs generated `T_1794_AENT_*` — rack name ≠ ownership.

`can_reconstruct_from_RUN=true` means the Fortna part + word/bit exist on this AC’s owned words. It does **not** require the finished AOI member path string to appear in RUN.

---

## Mapping error taxonomy

Every mismatched generated mapping and every missing finished mapping is classified into one or more of:

| Code | Meaning |
|------|---------|
| `WRONG_WORD` | Fortna word identity incorrect / missing from owned Configio set |
| `WRONG_BANK` | Configio/EIP bank alignment wrong |
| `WRONG_ADAPTER` | Adapter identity/name-family mismatch (incl. T_1794 vs CPxRIO) |
| `WRONG_SLOT` | `Data[slot]` incorrect |
| `WRONG_BIT` | Bit incorrect |
| `WRONG_DIRECTION` | I vs O incorrect |
| `WRONG_LOGICAL_DEVICE` | Tag/part binding incorrect or unfinished AOI mapping missing |
| `WRONG_CONTROLLER_SCOPE` | Point belongs to non-LOCAL equipment |
| `STALE_RECORD_USED` | Stale/non-overlay table row used |
| `UNSUPPORTED_POINT_TYPE` | Point type not supported by current generator |
| `PLACEHOLDER_SHOULD_BE_USED` | Channel should be `NO_PointPlaceholder` / SPARE |
| `MISSING_RUN_RELATIONSHIP` | No explicit RUN table path to reconstruct the finished point |

Counts separate:

- **REAL_LOGICAL_POINT** — XIC/OTE to a non-placeholder device tag  
- **UNUSED_PLACEHOLDER** — `NO_PointPlaceholder` / SPARE fill

---

## Foundation metric artifact (256/144 vs 159/75)

`exports/plc2-foundation/io_map_comparison.json` labeled generated “real” as **256 / 144**. That count came from `_parse_iomap_mappings` **without filtering** `NO_PointPlaceholder`, so placeholder fill was counted as real.

True REAL_LOGICAL_POINT on the foundation candidate is far lower (on the order of ~12 I / ~22 O), while finished real is **159 I / 75 O**. Generated does **not** exceed finished on true real maps; it under-maps real points and over-fills unused channels with placeholders. Adapter rename and sparse generator `word_map` for Greensboro Fortna words (200/201/300…) further prevent exact identity matches.

---

## Controller scope

`controller_scope.json` prefers evidence-graph owned Fortna words (Configio) plus Conveyor/Mtrchain links, and still wraps `fortna_controller_scope` / `fortna_cp2_ownership` for mechanical inventory. The JSON documents when ownership-heuristic LOCAL is retained vs graph promotions.

Classes: `LOCAL` / `EXTERNAL_REFERENCE` / `OUT_OF_SCOPE` / `UNRESOLVED`.

---

## Transport validation

Transportation uses a **compact external** print-boundary model:

- LOCAL conveyors render fully  
- EXTERNAL_REFERENCE neighbors render as one-hop boundary stubs  
- Full remote networks must not render  
- Print PDFs are optional and not required when absent from the repo  

See `exports/plc2-io-truth/transport_validation.json`.

---

## Diagnostic L5X

`ORNCCP2_io_truth_candidate.L5X` is produced via the **existing** `fortna_autogen.py from-run --with-io-map` path (or copy of that foundation candidate). It is labeled **diagnostic — pending mapping rewrite**. Mapping emit logic is intentionally unchanged in this pass.

---

## Related docs

- `docs/PLC2_FORTNAPLUS_IO_SEMANTICS.md` — training-corpus hop semantics  
- `docs/PLC2_FOUNDATION_RESET.md` — prior foundation gate (metric caveat above)  
- `docs/IO_REGRESSION_FORENSICS.md` — generator preservation / UI bypass history  
