# Generic I/O Ownership Model

**Branch:** `feature/plc2-transport-fidelity`  
**Machine-readable twin:** [`exports/stabilization/io_ownership_pipeline.json`](../exports/stabilization/io_ownership_pipeline.json)  
**Primary code:** `fortna_physical_word_resolver.py` → `fortna_hardware_io_model.py` → `fortna_plc_symbol_registry.py` → IO_MAP / Hardware UI

Physical endpoint identity and engineering owner are **separate**. Never collapse them.

---

## Pipeline

```
RUN (project.cfg + FORTNA/PROJECT tables)
  → Configio.asc(.MACHINE)          Octal_Word + Desc + Bank + LoHi
  → eipcfg + EIPModules             Adapter / TargetIP / Slot / InputBank / OutputBank
  → Parts (Conveyor.asc)            IO_Name + IO_Address_Word/Bit
  → PhysicalWordResolver            word.bit → CPxRIOn:I|O.Data[s].b
  → HardwareIOModel                 physical_endpoint + owner_state per channel
  → Engineering owner               ASSIGNED | UNRESOLVED_OWNER | ENGINEER_SPARE | PROVEN_SPARE | UNKNOWN
  → Canonical endpoint              exact dimension equality (Gate C)
  → IO_MAP (CP_I / CP_O)            symbol class + provenance (Gate G/H)
  → PLC L5X                         Studio preflight / operand validator
```

Hardware UI and IO_MAP **must** consume the same resolver tree. Disagreement is a model defect.

---

## Gate C — Physical endpoint identity

Canonical `physical_endpoint` dimensions (proven Fortna only):

| Dimension | Source |
|-----------|--------|
| machine | `project.cfg` MACHINENAME |
| panel / node | Configio Desc (`CP5-NODE53-1A` or `CP2-1794-IA16-3`) |
| adapter / rio_name | eipcfg + panel naming |
| module_slot | EIPModules / eipcfg Slot (never bank→slot arithmetic alone) |
| data_index | family-aware (1794 Flex slot−1; 1734 POINT raw) |
| bank_word | Configio Octal_Word |
| bit / channel | Configio bit → `Data[s].b` |
| direction | module type (IA/IB→I, OA/OB→O) |
| module_type | eipcfg / EIPModules catalog |

**Equality** = exact endpoint dimension equality (`endpoint_id` / `physical_endpoints_equal`).  
**Forbidden:** string-similarity ownership, name-prefix collapse (`P220` ≠ `P220A`), bank-number-alone slot invention.

---

## Gate D — Engineering owner states

| State | Meaning | UI |
|-------|---------|-----|
| `ASSIGNED` | Proven RUN or engineer logical owner | Active name |
| `UNRESOLVED_OWNER` | Topology known; owner failed / conflicted | **UNRESOLVED OWNER** (amber) — not SPARE |
| `ENGINEER_SPARE` | Engineer explicitly spared the bit | SPARE |
| `PROVEN_SPARE` | RUN spare / unused Configio bit / capacity | `SPARE — click to name` |
| `UNKNOWN` | Incomplete physical endpoint | warn / review |

`"SPARE — click to name"` is **only** for genuine spare (`PROVEN_SPARE` / `ENGINEER_SPARE`).  
Failed owner resolution must never be labeled SPARE.

---

## Gate G — IO_MAP symbol classes

Every CP_I/CP_O operand resolves to:

- root, semantic class, declaration owner, scope, datatype  
- physical endpoint **if applicable**  
- device binding **if applicable**  
- provenance  

| Class | Physical endpoint? |
|-------|-------------------|
| `PHYSICAL_INPUT` / `PHYSICAL_OUTPUT` | Required when discrete |
| `NETWORK_DEVICE_COMMAND` / `NETWORK_DEVICE_STATUS` | **Never** invent |
| `LOGICAL_SIGNAL` | Always null |
| `MODULE_REFERENCE` | Module path itself |
| `ALIAS` / `TIMER` / `AOI_INSTANCE` | Not required |
| `CONTROLLER_TAG` / `PROGRAM_TAG` | Declared tag |
| `UNKNOWN` | Gate H disposition |

---

## Gate H — Unknown symbol policy

**Forbidden:** auto BOOL, fake modules, TRUE/FALSE stubs, NOP replacement, silent omit, name-prefix guesses.

Disposition (with WHY / provenance):

- `FATAL`  
- `ENGINEER_REQUIRED`  
- `OPTIONAL`  
- `ABSENT_REFERENCE`  

`may_auto_declare_bool()` defaults to **deny**. Engineer-named bare tags in Hardware overrides remain an explicit engineer action, not mystery generation for unknowns.

---

## Assumption classification

| Assumption | Status |
|------------|--------|
| Configio Bank alone determines Logix slot | **REMOVED/FIXED** — EIPModules bank→slot; Desc slot corroboration; REVIEW on mismatch |
| Name equality / prefix implies same owner (`P220`/`P220A`) | **REMOVED/FIXED** — exact identity only; lettered motors preserved |
| All `CP_I`/`CP_O` operands are discrete physical | **REMOVED/FIXED** — class matrix; NETWORK_DEVICE_* / LOGICAL_SIGNAL need no endpoint |
| Missing owner on known topology = SPARE | **REMOVED/FIXED** — `UNRESOLVED_OWNER` vs `PROVEN_SPARE` |
| Unknown symbol → invent BOOL | **REMOVED/FIXED** — Gate H dispositions |
| Configio Desc PANEL-CATALOG / PANEL-NODE forms | **JUSTIFIED** — proven Fortna Desc patterns |
| Family-aware Data[] index (1794 vs 1734) | **JUSTIFIED** — hardware family module |
| Conveyor.asc is engineering owner catalog for discrete points | **JUSTIFIED** — Parts → owner; Type=INVALID may be LOGICAL_SIGNAL |
| PhysicalWordResolver is sole Hardware/IO_MAP topology authority | **JUSTIFIED** — single tree |

---

## Related

- [`docs/evidence/PHYSICAL_IO_BASELINE.md`](evidence/PHYSICAL_IO_BASELINE.md)  
- [`docs/PLC2_IO_TRUTH_MODEL.md`](PLC2_IO_TRUTH_MODEL.md)  
- [`docs/evidence/LOGICAL_SIGNAL_MODEL.md`](evidence/LOGICAL_SIGNAL_MODEL.md)  
- Tests: `test_io_ownership_model.py`, `test_plc5_io_endpoint_collision.py`, `test_hardware_io_model.py`
