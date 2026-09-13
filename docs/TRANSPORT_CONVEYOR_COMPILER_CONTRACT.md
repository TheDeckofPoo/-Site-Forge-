# Transport Conveyor Compiler Contract

**Scope:** Generic Fortna transport Autogen contracts (any site / any transport controller).  
**Emitters:** `clone_template_for_conveyor`, `build_l5x` in `tools/scripts/fortna_autogen.py`.  
**Policy:** RUN device type + drive classification select a library template. Finished / oracle L5X is validation only — never a generation input. See `docs/SOURCE_OF_TRUTH_POLICY.md` and `docs/DISCOVERY_TO_COMPILER_CONTRACT.md`.

---

## 1. Class selection (RUN → Autogen TYPE → library template)

Mechanical Conveyor.asc rows (`STRAIGHT`, `BELT`, `CURVE`, `MERGE`, `SKEW`, `SPUR`, `TRIANG`, `ACCUM`, `ZEROPRESSURE`) map to Excel-style TYPE strings. Drive evidence (`VFD` in name/desc/Drive, or linked VFD number) flips MS → VFD.

| Autogen TYPE | Library template (preferred) | Fallback order |
|--------------|------------------------------|----------------|
| Transport with MS | `P3000_Conv` | `P1000` → `P3000` → `P2000` → `P4000` |
| Accumulation with MS | `P4000_Conv` | same resolve chain |
| Transport with VFD | `P1000_Conv` | same |
| Accumulation with VFD | `P2000_Conv` | same |
| Transport with MDR | `P4000_Conv` | same |
| Accumulation with MDR | `P3000_Conv` | same |
| Gravity | `P3000_Conv` (Excel prefers `P5000_Conv` when present) | same |

`resolve_template()` picks the first template tag that exists in the library. Missing Excel names (`P7000`/`P8000`/`P5000`) are remapped; absence of a resolvable template is `NO_TEMPLATE` / build failure — do not invent site-specific templates.

---

## 2. Tag emit matrix (per conveyor class)

Driven by `clone_template_for_conveyor` (per belt) plus `build_l5x` ensure-loops (orphan PE, motor aux, VFD discrete, control stations).

| Artifact | Transport MS | Accum MS | Transport VFD | Accum VFD | MDR / Gravity |
|----------|:------------:|:--------:|:-------------:|:---------:|:-------------:|
| `P###_Conv` (`Conv_UDT`) | **required** | **required** | **required** | **required** | **required** |
| `P###_Conv_AOI` | **required** | **required** | **required** | **required** | **required** |
| `P###_MS` (`Motor_Starter_UDT`) | **required** | **required** | no* | no* | **required** (MS-named path) |
| `P###_VFD` (`Motor_Starter_UDT`) | no | no | **required** | **required** | no |
| Optional `*_BrakeReleased` / `*_BrakeReleased_Aux` | if in template | if in template | if in template | if in template | if in template |
| PE tags (`PE_UDT` + `*_AOI`) | when PE roles exist | same | same | same | same |
| Control-station tags (`CPn_CS` / `CS_UDT`) | from RUN PB I/O, not class | same | same | same | same |

\* VFD class uses gold discrete naming: tag `P###_VFD` is a **Motor_Starter_UDT** (aux/contactor I/O), not Ethernet `VFD_UDT`. `Fast_Conv` / `Slow_Flt` pass `NO_VFD` for the Ethernet VFD slot and wire `IO_MS=P###_VFD`.

### Always-cloned null / shared objects (`build_l5x`)

`NO_PE`, `NO_Conv`, `NO_VFD`, `NO_Enc`, `NO_MS`, `NO_PS`, `NO_AirPress`, `NO_AdditionalFlt`, `HMIColor`, `HMI_StatsClear`, `Type2`, area `Area_UDT` / safety `ES_Zone_UDT`.

### PE tags — when required

| Condition | Emit |
|-----------|------|
| Jam / product / exit / add PE linked on the belt | `PE_UDT` (+ `PE###_AOI`) via clone; `PE_Logic` / `Full_PE` rungs |
| Full-role PE (`*_F` / full role) | Full PE UDT + `Full_PE` AOI |
| Orphan RUN photoeye (not on a cloned belt) | Still ensure `PE_UDT` (+ AOI) in `build_l5x` PE loop |
| No PE roles on belt | **Do not** emit empty PE NOP rungs; omit empty `Conv_PE` / `Conv_Full` routines |

Jam slots pad to 5 with `NO_PE`. Unused Fast_Conv exit/add slots use `NO_PE`.

### Control-station tags — when required

Not selected by conveyor TYPE. `build_l5x` maps RUN points matching `nPBSTART` / `nPBSTOP` → `CPn_CS` (`CS_UDT`, cloned from `NO_CS` when present). Area L1 always reserves a `CS` ST routine scaffold for site customize. Conveyor workbook field `control_station` is input metadata; tag emit is IO-driven.

### Additional drive stubs (IO path, not class matrix)

| RUN evidence | Tag |
|--------------|-----|
| `M###_AUX` | ensure `P###_MS` |
| `VFD###_*` discrete | ensure `P###_VFD` (`Motor_Starter_UDT`) |

These may create MS/VFD tags for devices without a mechanical conveyor clone in the same build.

---

## 3. Per-belt AOI rung contract (`clone_template_for_conveyor`)

Every mechanical conveyor that clones a template emits:

| Label | AOI call | Class notes |
|-------|----------|-------------|
| Fast | `Fast_Conv(P###_Conv_AOI.Fast, P###_Conv, Area, Safe, Next_or_NO_Conv, ExitPE, AddPE, …, NO_VFD, …)` | All classes |
| Jam | `Slow_Jam(…, PE1..PE5)` | All classes; pad with `NO_PE` |
| Flt | `Slow_Flt(…, NO_VFD, NO_Enc, Type2, P###_MS\|P###_VFD, …)` | MS → `P###_MS`; VFD → `P###_VFD` |
| PE | `PE_Logic` per non-full eye | Only when PE tags exist |
| Full | `Full_PE` per full eye | Only when full PE tags exist |

Comment banners distinguish Transport vs Accumulation and MS vs VFD from template + `is_vfd`.

---

## 4. Area Fast / Slow / L1 / L2 participation by class

Programs are emitted per engineering Area in `build_l5x` (ModuleB-shaped pack). Naming: `{Area}_Area_Fast|Slow|L1|L2` (or `{Area}_Fast|…` when `Area` already ends with `_Area`).

Participation is **capability-driven**, not site-hardcoded. Conveyor class (MS/VFD/Accum) does **not** drop a family; it changes drive tag naming inside Flt/MS_Time.

### `{Area}_Area_Slow`

| Routine | Expectation |
|---------|-------------|
| `Main_Routine` | JSR `Conv_Flt`, `Conv_Jam`; JSR `Conv_PE` only if PE_Logic rungs exist |
| `Conv_Flt` | One `Slow_Flt` per cloned conveyor (MS or VFD MS-tag) |
| `Conv_Jam` | One `Slow_Jam` per cloned conveyor |
| `Conv_PE` | Emit only when real `PE_Logic(` rungs exist — no empty scaffold |

### `{Area}_Area_Fast`

| Routine | Expectation |
|---------|-------------|
| `Main_Routine` | Always JSR `Conv_Fast`; optional JSR `Conv_Full` / `Conv_Merge` / `Conv_PE` when content exists |
| `Conv_Fast` | One `Fast_Conv` per cloned conveyor (all classes) |
| `Conv_Full` | Only when `Full_PE` rungs exist |
| `Conv_Merge` | Only when 2:1 merges configured for the area |
| `Conv_PE` | Only when `PE_Logic` rungs exist |

Empty Fast `Conv_Full` / `Conv_Merge` / PE scaffolds are **omitted** (post-Aug28 behavior) — families still emit when content exists.

### `{Area}_Area_L1` (ST presets)

| Routine | Expectation |
|---------|-------------|
| `Main_Routine` | JSR `Area`, `Conv`, `CS`, `MS_Time`, `PS_Time`, `PWS_Time` |
| `Area` | Area start-time defaults |
| `Conv` | Comment banner per belt (preset hooks) |
| `CS` | Control-station customize scaffold |
| `MS_Time` | Motor starter fault-time defaults for area belts (`*_MS` members; engineer/Sys Init may override) |
| `PS_Time` / `PWS_Time` | Customize scaffolds |

All transport classes participate in L1 when present in the area. Merge-only / PE-only artifacts do not create a conveyor L1 row without a cloned belt.

### `{Area}_Area_L2` (ST presets)

| Routine | Expectation |
|---------|-------------|
| `Main_Routine` | JSR `Conv_Speed`, `FullTime`; JSR `Merge` only if merge ST lines exist; JSR `PETime` |
| `Conv_Speed` | Speed preset scaffold (site customize) |
| `FullTime` | Full PE timer scaffold |
| `Merge` | Gold Merge_2to1 ST presets when merges configured — omit when none |
| `PETime` | PE timer scaffold |

Accumulation vs transport does not gate L2; full-timer content matters when Full PE exists. Merge ST is merge-config-driven (see `docs/PLC2_TRANSPORT_MERGE_INVENTORY.md` for the equipment pattern, not site locks).

---

## 5. Emitter responsibilities (do not rewrite roles)

| Function | Contract role |
|----------|---------------|
| `load_from_run` | Select mechanical conveyors, classify MS/VFD, wire PE roles, attach IO/EIP/Configio |
| `resolve_template` | Map Autogen TYPE → library `P1000`–`P4000` (etc.) Conv tag |
| `clone_template_for_conveyor` | Clone `P###_Conv` / `_Conv_AOI` / drive UDT / PE UDTs; emit Fast/Jam/Flt/PE/Full rungs |
| `build_l5x` | Aggregate tags; ensure orphan PE + MS/VFD/CS stubs; emit Area Slow/Fast/L1/L2; emit IO_MAP `CP_I`/`CP_O` |

CLI product path: `from-run --with-io-map` (placeholders default on). Fail-closed assertions reject empty IO_MAP / PE scaffolds when mappable evidence exists.

---

## 6. Seed validation example (generic — not a special case)

Any included mechanical seed (illustrative name **`P123`**) must, after class resolution, produce:

1. `P123_Conv` + `P123_Conv_AOI` from the resolved library template.  
2. `P123_MS` **or** `P123_VFD` (`Motor_Starter_UDT`) per MS vs VFD class.  
3. Linked PE → `PE_UDT` + logic/full AOI participation; no PE → no empty PE routines.  
4. Membership in that belt’s Area Fast (`Conv_Fast`) and Slow (`Conv_Flt` / `Conv_Jam`) families.  
5. IO_MAP membership only for points with resolvable word/bit ownership — never invented channels.

`P123` is a **validation probe identity**, identical in rules to any other `P###`. Do not hardcode belt lists, area names, or adapter names around it.

---

## 7. Related docs

- `docs/DISCOVERY_TO_COMPILER_CONTRACT.md` — entity eligibility / dispositions  
- `docs/AUG28_AUTOGEN_FORENSICS.md` — historical emitter preservation proof  
- `docs/TRANSPORT_REGRESSION_FORENSICS.md` — recovered vs thinner transport fidelity  
- `docs/GOLD_EQUIPMENT_TO_BUILD.md` — equipment pattern → build action  
- `docs/PLC2_*.md` — controller-scope / Configio / IO truth (validation context)
