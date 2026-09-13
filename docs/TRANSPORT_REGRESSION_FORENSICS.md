# Transport Regression Forensics

**Branch:** `feature/plc2-transport-fidelity`  
**Purpose:** Separate (a) historical Site Forge Autogen regression recovery from (b) finished-PLC behavioral fidelity. Prove transport emitters were preserved; document what is still thinner than a commissioned controller.  
**Cross-link:** `docs/AUG28_AUTOGEN_FORENSICS.md` (primary Aug28 structural compare). Companion I/O product-path forensics: `docs/IO_REGRESSION_FORENSICS.md`.

---

## Executive verdict

| Question | Answer |
|----------|--------|
| Were Conv / Conv_AOI / PE / Area Fast·Slow·L1·L2 / IO_MAP emitters deleted? | **NO** — still in `tools/scripts/fortna_autogen.py` (`clone_template_for_conveyor`, `build_l5x`) |
| Is historical Site Forge transport generation recoverable? | **YES** — structural gates; see Aug28 compare |
| Does recovered Autogen equal finished PLC fidelity? | **NO** — different bar (structure + RUN identity vs commissioned logic/names) |
| Is current output thinner than Aug28 on some Conv/AOI counts? | **YES (−prefix false-positives)** — intentional identity fix, not missing emitters |
| Real IO_MAP CP_I / CP_O from RUN? | **Recovered** on the CLI / product `--with-io-map` path |

---

## 1. Two fidelity bars (do not conflate)

```text
HISTORICAL SITE FORGE REGRESSION
  Compare: prior Autogen L5X / suite backup era (e.g. Aug28)
        ↔ current from-run L5X
  Goal: prove emitters + RUN identity still produce transport structure
        (Conv_UDT, Conv_AOI, PE_UDT, Area families, real CP_I/CP_O)

FINISHED PLC FIDELITY (oracle only)
  Compare: generated L5X ↔ commissioned / finished controller export
  Goal: validate gaps (areas, lettered AOIs, exact channels, CS/Merge presets)
  Forbidden: copy finished names/constants into generation
            (docs/SOURCE_OF_TRUTH_POLICY.md, docs/PLC2_FOUNDATION_RESET.md)
```

Historical regression **passing** does not claim finished parity. Finished gaps belong under PLC2 IO truth / Configio / ownership docs — not “restore deleted generator.”

---

## 2. Emitter inventory (recovered — still present)

| Concern | Historical locus | Current locus | Status |
|---------|------------------|---------------|--------|
| `P###_Conv` (`Conv_UDT`) | `clone_template_for_conveyor` | same | **recovered / intact** |
| `P###_Conv_AOI` | clone from `{template}_AOI` | same | **recovered / intact** |
| `P###_MS` / `P###_VFD` | clone `NO_MS` → drive tag | same + AUX/VFD IO stubs | **recovered**; MS count may be **higher** via `M###_AUX` stubs |
| PE_UDT + PE_Logic / Full_PE | clone + PE ensure loop | same | **recovered / intact** |
| Area Slow (`Conv_Flt` / `Jam` / `PE`) | `build_l5x` area emit | same | **recovered / intact** |
| Area Fast (`Conv_Fast` / `Full` / `Merge` / `PE`) | same | same; empty Full/Merge omitted | **recovered**; empty scaffolds **thinner by design** |
| Area L1 (`Area` / `Conv` / `CS` / `MS_Time` / …) | same | same | **recovered / intact** |
| Area L2 (`Conv_Speed` / `FullTime` / `Merge` / `PETime`) | same | Merge omitted when no merges | **recovered**; empty Merge **thinner by design** |
| IO_MAP `CP_I` / `CP_O` | `build_l5x` IO_MAP section | same + optional placeholders | **real maps recovered**; placeholders are additive |
| Control-station `CPn_CS` | IO point → CS_UDT | same | **recovered** (IO-driven, not conveyor-class) |

Era anchors (detail in Aug28 doc): generating commits around `0ce9e1e` / `88581bf`; suite backup `suite-20260828-163000`; PACK good-autogen `good-autogen-20260826-184506`. Current engine: `tools/scripts/fortna_autogen.py`.

Contract for *what each class must emit*: `docs/TRANSPORT_CONVEYOR_COMPILER_CONTRACT.md`.

---

## 3. What changed after the historical era (still generic)

| Change | Effect on transport regression | Classification |
|--------|--------------------------------|----------------|
| Untagged conveyor ownership → `fortna_identity.linked_owns_conveyor` | Drops string-prefix false belts (`P60`↛`P600`, etc.) | **identity fix** (Conv/AOI counts can fall) |
| Motor IO → conveyor link (`M123`/`M123_AUX` → `P123`) | Recovers motor-owned untagged belts (e.g. PLC2 `P123`, MSCRENO `P52`) without prefix pollution | **ownership recovery** |
| Empty Fast Full/Merge / L2 Merge omitted | Fewer empty routines vs older always-emit | **intentional thinner scaffold** |
| IO_MAP placeholders default on | Extra `NO_PointPlaceholder` rungs; **real** map counts unchanged | **additive** |
| Fail-closed `_generation_assertion_failures` | Empty IO_MAP / PE when evidence exists → build fail | **hardening** |
| Optional `System` / Sys_Comm | Only with `--include-programs System` | **optional parity** |
| `M###_AUX` → `P###_MS` stubs | More MS tags than older L5X | **richer stubs** |
| Configio-primary physical word resolver | Better adapter/channel identity on Configio sites | **IO fidelity** (see `docs/PLC2_CONFIGIO_COMPILER.md`) |

**Not** classified as generator deletion: UI workbook/`workbook: undefined` bypass (see `docs/IO_REGRESSION_FORENSICS.md`).

---

## 4. Recovered vs still thinner (PLC2 / transport controllers)

Use finished PLC2 only as an **oracle**. Numbers below are pattern-level, not site locks.

| Layer | Historical Autogen regression | vs finished PLC (typical remaining thinness) |
|-------|-------------------------------|-----------------------------------------------|
| Conv_UDT / Conv_AOI emitters | Present; counts track RUN inclusion + identity rules | Finished may add lettered AOIs (`P130A`…) or engineer belts not in RUN mechanical rows — **do not invent** |
| Drive MS / VFD UDT | Present; VFD discrete → `P###_VFD` Motor_Starter_UDT | Finished may refine member presets / Ethernet VFD programs beyond discrete MS path |
| PE_UDT + logic | Present when RUN PE exists | Role/exit accuracy and debounce constants may lag finished |
| Area Fast/Slow/L1/L2 structure | Present | Finished multi-area names (ModuleB/Trash/…) require workbook overlay — RUN seeds one provisional `{Machine}_Area` |
| Merge_2to1 + L2 Merge ST | Present when merges configured | Hold/timer nuance vs finished; 3:1+ not codegen’d yet |
| IO_MAP real XIC/OTE | Recovered when word map + banks resolve | Adapter **name family**, exact slot/bit, and logical-device mapping still thinner than finished without Configio/EIP completeness (`docs/PLC2_IO_TRUTH_MODEL.md`) |
| Control stations | CS_UDT from PB I/O | L1 `CS` ST often scaffold-only vs finished presets |
| System / NTP / Device Comms | Optional include | Finished often always has System pack |

**Summary:** Structure that Site Forge historically emitted is **recovered**. Thinness vs finished PLC is mostly **configuration depth, naming family, and commissioned constants** — not missing `clone_template_for_conveyor` / area-family code.

---

## 5. Aug28 structural snapshot (pointer)

Full tables live in [`docs/AUG28_AUTOGEN_FORENSICS.md`](AUG28_AUTOGEN_FORENSICS.md). Headline pattern:

| Metric family | Historical Autogen L5X | Current regenerate | Reading |
|---------------|------------------------|--------------------|---------|
| Modules / adapters | match | match | hardware tree recovered |
| Real CP_I / CP_O | match | match | real IO_MAP recovered |
| Placeholder CP_* | 0 historically | may be >0 | fill-on default |
| Conv_UDT / Conv_AOI | higher if prefix rule | lower after identity fix | **not** emitter loss |
| PE_UDT | match | match | PE path recovered |
| Area Fast/Slow/L1/L2 | yes | yes | families recovered |
| System program | often present | optional flag | parity opt-in |

Do **not** reintroduce string-prefix conveyor ownership to chase historical Conv counts.

---

## 6. Generic seed probe (`P123`)

`P123` appears in ownership / completion samples as a **CONFIRMED** mechanical identity on a transport controller seed — it is **not** a hardcoded compiler branch.

Validation expectations (same rules as any `P###`):

1. If RUN + inclusion say `P123` is a local mechanical conveyor → expect `P123_Conv` + `P123_Conv_AOI`.  
2. Drive class → `P123_MS` or `P123_VFD` per contract.  
3. Linked PE → PE_UDT + Fast/Slow participation; no PE → no empty PE routines.  
4. Absence of `P123_*` when ownership is EXTERNAL / OUT_OF_SCOPE is **correct**, not regression.  
5. Finished PLC having extra lettered children around a parent belt does **not** authorize inventing those tags from the seed name alone.

Use `P123` in regression checklists as a readable probe; keep implementation data-driven via `load_from_run` + identity helpers.

---

## 7. How to re-prove (no new I/O systems)

1. Regenerate with `fortna_autogen.py from-run --with-io-map` (placeholders per product default).  
2. Structural-compare against the historical Autogen artifact (Aug28 recipe in `docs/AUG28_AUTOGEN_FORENSICS.md`).  
3. Optionally oracle-compare finished PLC for gap taxonomy — never feed finished tags back into AutogenInput.  
4. Lock identity with existing regression tests (`test_mscreno_aug28_regression.py`, `test_io_regression_lock.py`) without restoring false-positive ownership.

---

## 8. Related docs

| Doc | Role |
|-----|------|
| `docs/AUG28_AUTOGEN_FORENSICS.md` | Aug28 vs current structural forensics |
| `docs/TRANSPORT_CONVEYOR_COMPILER_CONTRACT.md` | Per-class tag/routine contract |
| `docs/IO_REGRESSION_FORENSICS.md` | UI bypass vs preserved IO generator |
| `docs/PLC2_FOUNDATION_RESET.md` | Controller scope + foundation candidate |
| `docs/PLC2_CONFIGIO_COMPILER.md` | Configio-primary word ownership |
| `docs/PLC2_IO_TRUTH_MODEL.md` | RUN hop chain / reverse-trace |
| `docs/DISCOVERY_TO_COMPILER_CONTRACT.md` | Discovery → AutogenInput eligibility |
