# Studio Empty Controller Organizer — Root Cause

**Subject:** `exports/current/ORNCCP4_2026_09_13_1710.L5X`  
**Symptom:** Studio 5000 opens controller **ORNCCP4**, but Tags / Programs appear **empty** in Controller Organizer.  
**XML reality:** NOT hollow — 838 tags, 8 programs, 31 modules, Git=`11c51ed`.  
**vs history:** Byte-identical to `exports/autogen/history/ORNCCP4_2026_09_13_1517.L5X` after stripping provenance (`Owner` / `ExportDate` / `ProjectCreationDate` / `LastModifiedDate` / Controller `<Description>`).

This is a **Studio visibility / import abort** problem, not a hollow workbook emit.

---

## Most likely root cause

**Broken DataType dependency left by AOI/UDT pruning:**

`fortna_autogen.py` → `_strip_udts_for_missing_aois()` drops every `Track_*` / `TRK*` DataType when no `TRK_*` AOIs are kept (CP4 transport builds do not keep sorter track AOIs). That correctly removes 13 library track UDTs, including **`Track_TestOffset`**.

It does **not** remove **`Divert_CFG`**, which still declares:

- `TestOffset_DivertPE` → `DataType="Track_TestOffset"`
- `TestOffset_DivertConfPE` → `DataType="Track_TestOffset"`

| Check | Result |
|-------|--------|
| `Track_TestOffset` in library DataTypes | Present |
| `Track_TestOffset` in 1710 DataTypes | **Missing** |
| `Divert_CFG` in 1710 DataTypes | Present, still references `Track_TestOffset` |
| Tags typed `Divert_CFG` | 0 (unused — but Studio still validates the UDT) |
| Other broken member deps in 1710 | **Only this one** |

Studio imports DataTypes before Tags/Programs. A UDT whose member type does not exist is a classic cause of **controller shell retained, Tags/Programs discarded** (partial / aborted content import). Prior repo note of the same class: `exports/plc2-fidelity/studio_import_fixes.md` (Curtis 26-error log → partial import counts, not generator hollowness).

Closure simulation: dropping DataTypes with unresolved member types removes exactly `Divert_CFG` and leaves 197 healthy UDTs.

---

## Investigation results (all 7 asks)

### 1. AOI EncodedData Fast_Conv / Slow_Flt vs `OReilly_Library_v3.L5X`

| AOI | cur sha12 | lib sha12 | overlay | Verdict |
|-----|-----------|-----------|---------|---------|
| Fast_Conv | `a3d844fb778f` | same | n/a | Exact match — **not truncated** |
| Slow_Flt | `2c5c707b7489` | same | `Slow_Flt_AOI.L5X` same | Exact match — **host/signature intact** |
| Slow_Jam / PE_Logic / Full_PE / Merge_2to1 / … | match lib | — | — | All kept sealed AOIs byte-identical to library |

No EncodedData truncation or host-revision mismatch on transport AOIs.

### 2. DataTypes — invalid member / missing dependency

**Yes — smoking gun above.**  
`Divert_CFG` → missing `Track_TestOffset` is the only unresolved UDT member dependency in the file.  
`BIT` / `CONNECTION_STATUS` appear as member types without local DataType elements; same as library / Rockwell builtins — not treated as defects.

### 3. Modules ConfigTag / Communications

| Check | Result |
|-------|--------|
| Modules | 31; no dangling `ParentModule` |
| ConfigTag | 25× `ConfigSize="0"` (intentional strip; Studio recreates catalog defaults — see `studio_import_fixes.md`) |
| Local Communications | Absent — **same as finished PLC2** |
| Bus Address overflow | None found |

Modules are **unlikely** to explain empty Tags/Programs.

### 4. SoftwareRevision 35.01 vs finished 35.05

| Artifact | SoftwareRevision | MajorRev / MinorRev |
|----------|------------------|---------------------|
| 1710 / library | **35.01** | 35 / **0** |
| Finished PLC2 (`ORLY_GreensboroPLC2_NC_Finished.L5X`) | **35.05** | 35 / 11 |
| Reference PLC5 edited | 35.05 | — |

Mismatch can prompt conversion / warnings when Studio ≠ export host, but **newer Studio opening 35.01 normally still loads content**. Alone it does **not** best explain name-only organizer emptiness when XML content is complete. Secondary risk only; fix DataType closure first.

### 5. Prior "Studio empty" / partial import notes

- `exports/plc2-fidelity/studio_import_fixes.md` — partial import after module/AOI/NO_PS errors (counts looked hollow; XML was not).
- `exports/plc2-validation/hollow_l5x_audit.md` — engineer L5X **NOT hollow**; hollow risk is empty workbook emit (different failure mode).
- `docs/STUDIO_IMPORT_PRECHECK.md` — static precheck ≠ Studio PASS; does not yet flag unresolved UDT member deps.
- No prior note specifically titled "empty organizer", but the partial-import pattern matches this symptom class.

### 6. Description / Owner injection after `<Controller>`

Provenance inject (`fortna_autogen.py` ~6365–6402):

```xml
<Controller … Name="ORNCCP4" …>
<Description>SiteForge ORNCCP2 build | Controller=ORNCCP4 | … | Git=11c51ed</Description>
<RedundancyInfo …/>
```

- Placement is valid (before `RedundancyInfo`).
- `Owner="SiteForge 11c51ed"` is the only non-date provenance delta vs 1517.
- Structural identity after provenance strip ⇒ injection is **not** corrupting Tags/Programs XML.

(Cosmetic: description says `ORNCCP2 build` for an ORNCCP4 controller — unrelated to empty organizer.)

### 7. Dual L5K + Decorated on Conv_UDT

788 tags carry both `Format="L5K"` and `Format="Decorated"` (71 Conv-like).  
Library templates do the same (`P1000_Conv` etc.). `ExportOptions` includes `L5KData DecoratedData`.  
`NO_PS` is Decorated-only (already fixed for Studio).  
**Dual data is normal here — not the root cause.**

---

## Minimal `fortna_autogen.py` fix recommendation

**Do not** re-add all `Track_*` sorter UDTs / `TRK_*` AOIs for CP4.

**Do** close DataType dependencies after `_strip_udts_for_missing_aois`:

1. After the existing Track_/missing-AOI strip, iteratively drop any remaining `<DataType>` whose `<Members>` reference a type not in:
   - remaining DataType names, **or**
   - kept AOI names, **or**
   - Rockwell builtins (`BOOL`, `INT`, `TIMER`, `BIT`, `CONNECTION_STATUS`, `STRING*`, …)
2. That removes `Divert_CFG` (unused on CP4) and prevents Studio from aborting content import.
3. Optional belt-and-suspenders: if prefix-stripping `Track_*`, **exempt** plain helper UDTs with no AOI members (e.g. keep `Track_TestOffset`) **or** also drop known dependents (`Divert_CFG`). Closure alone is enough.
4. Add a static preflight check: fail build / warn when any DataType member type is unresolved (would have caught 1710 before Studio).

No Hardware UI work. No claim that the workbook/XML is hollow — XML is populated; Studio is discarding dependent content on import.
