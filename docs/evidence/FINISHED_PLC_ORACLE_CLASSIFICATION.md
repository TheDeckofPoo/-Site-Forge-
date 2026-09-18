# Finished PLC Oracle Classification

**Policy:** Finished PLC exports are a **validation oracle only**.  
They must not invent RUN relationships, generation rules, or machine/site-specific branches.

Companion diff: [`exports/stabilization/orindyac6_io_oracle_diff.md`](../../exports/stabilization/orindyac6_io_oracle_diff.md)  
Script: `tools/scripts/fortna_io_oracle_diff.py`

---

## Why finished PLC appears in evidence

Site Forge builds physical endpoints and engineering owners from **virgin RUN** tables (`Configio`, `eipcfg` / `EIPModules`, `Conveyor`).  
A finished Studio export (e.g. `ORLY_Brownsburg_IN_PLC6_TEST2.L5X`) is useful only to:

1. Confirm cookie-cutter IO_MAP shapes Site Forge already knows how to emit
2. Separate **engineer overlays** from autogen defaults
3. Quantify endpoint/owner agreement without copying finished logic into the generator

---

## Classification of finished IO_MAP patterns

### `NO_PointPlaceholder` — cookie-cutter placeholder

When present in finished `IO_MAP` as:

```
XIC(CPxRIOn:I.Data[s].b)OTE(NO_PointPlaceholder);
XIC(NO_PointPlaceholder)OTE(CPxRIOn:O.Data[s].b);
```

this is the **standard unused-point fill** already used by Site Forge autogen (`fortna_autogen` placeholder emission).  

| Oracle class | Meaning |
|--------------|---------|
| `FINISHED_PLACEHOLDER` | Finished and (typically) Site Forge agree the bit has no engineering owner |
| `EXTRA_SITEFORGE_OWNER` | Site Forge HardwareIOModel has an ASSIGNED RUN owner while finished still shows placeholder |

**Do not** treat placeholder presence as proof that the RUN lacks an owner. RUN/`HardwareIOModel` remains authoritative for ownership.

### `_EMU_*` — engineer modification

Finished rungs frequently wrap a real map with emulation holds, e.g.:

```
[XIC(CP6RIO0:I.Data[0].2) ,XIC(_EMU_Safety_Hold) ]OTE(CP6_MCR1.I.ES_OK);
```

| Tag / pattern | Oracle class | Meaning |
|---------------|--------------|---------|
| `_EMU_Safety_Hold` | **ENGINEER_MODIFICATION** | Engineer-added parallel permissive for safety/ES paths in the finished program |
| `_EMU_PE_Hold` | **ENGINEER_MODIFICATION** | Same pattern for photoeye paths |
| `_EMU_Motor_Hold`, `_EMU_Force_*`, … | **ENGINEER_MODIFICATION** | Other finished-only emulation overlays |

These `_EMU_*` tags are **not** virgin-RUN Conveyor owners and must not be back-ported into Site Forge generation rules.  
The underlying `CPxRIO*:I\|O.Data[n].b ↔ logical tag` pair may still match cookie-cutter autogen; the `_EMU_` branch is the engineer delta.

Oracle diff classification name: `ENGINEER_MODIFIED`.

---

## Owner rename discipline (validation only)

Site Forge autogen already documents cookie-cutter renames (do not invent new ones from finished):

| RUN `IO_Name` | Autogen logical tag |
|---------------|---------------------|
| `nPBSTART` | `CPn_CS.I.Start_PB` (finished may rename the CS AOI instance; member `.Start_PB` still counts) |
| `nPBSTOP` | `CPn_CS.I.Stop_PB` |
| `nMCR#AUX` | `CPn_MCR#.I.ES_OK` |
| `nESR#AUX` | `CPn_ESR#.I.ES_OK` |
| `nES` | `CPn_ES.I.ES_OK` |

If a finished tag cannot be proven via these patterns (or normalized equality), the oracle marks **AMBIGUOUS** and retains both values — it does **not** create a new synonym rule.

---

## Physical endpoint note (Flex `Data[]`)

For 1794 Flex I/O, `Data[n]` is the Logix image index:

`data_index_for_module(slot) = slot − 1` when `slot > 0`.

Word **600** on ORINDYAC6 virgin RUN assigns via `configio_bank_match` → `T_1794_AENT_1:I.Data[0].*` (not the old false name-match `Data[2]`).
