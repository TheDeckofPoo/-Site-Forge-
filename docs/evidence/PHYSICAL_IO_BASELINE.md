# Physical I/O Baseline

Training docs for Configio / View I/O / IOCard (Desktop + `docs/training/`):

- `FPC-IOCard-Interfaces.docx`
- `FPC-FastIO-Configuration.docx`
- `FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx`

See [`EXTERNAL_REFERENCE_MATERIALS.md`](EXTERNAL_REFERENCE_MATERIALS.md).

Three separate concepts — never collapse them:

---

## 1. LOGICAL IDENTITY

Exact Fortna / engineer names.

Example: **`M220_AUX` ≠ `M220A_AUX`**

Fuzzy normalization / lettered-suffix stripping must **not** establish ownership.

Reproduce: `python tools/scripts/test_m220_aux_identity.py`

---

## 2. RUN PHYSICAL IDENTITY

Configio (and related) evidence:

- logical I/O name  
- Bank  
- bit / channel  
- EIP / module relationship (EIPModules)  
- adapter  

PLC5 note: Configio may use **PANEL-NODE** Descs (`CP5-NODE53-1A`), not only PANEL-CATALOG.

---

## 3. LOGIX PHYSICAL ENDPOINT

- Adapter (AENT)  
- Slot  
- `:I` / `:O`  
- `Data[n].bit`  

---

## Pipeline

```
Configio logical record
        ↓
Bank + bit
        ↓
EIPModules relationship (OutputBank / InputBank → adapter + slot)
        ↓
physical module
        ↓
Logix module name
        ↓
:I.Data[n].bit / :O.Data[n].bit
```

**Do NOT** derive physical slot solely from bank arithmetic / shared Bank number.

Example (PLC5, proven after `8c28daf`):

| Word.bit | Must NOT share endpoint with |
|----------|------------------------------|
| Bank **516**.0 (NODE52 / IA16 InputBank=40) | Bank **520**.0 (NODE53 / OB16P OutputBank=40) |
| Bank **520**.0 | Bank **522**.0 (OB16P OutputBank=**44**, different slot) |

Classification for that class of bug: **SITE_FORGE_ADDRESS_TRANSLATION_COLLISION** (not “same physical point”).

Evidence: `exports/stabilization/plc5_io_collision_report.md`  
Reproduce: `python tools/scripts/test_plc5_io_endpoint_collision.py`

---

## Duplicate-owner validator

Runs **after** physical resolution.

Detects: two distinct logical owners → same proven Logix OUTPUT endpoint.

**Keep** this diagnostic. Do not mute Generate, pick winners, or merge names to silence it.

PLC2 regression: INT229 vs M402 on same OTE target still ERROR.  
Reproduce: `python tools/scripts/test_iomap_duplicate_output_ownership.py` (needs PLC2 RUN)

---

## P220 / P220A

- Distinct AUX OTEs when both conveyors exist  
- Bare `M{n}` must not steal lettered `P{n}A`  
- Parent suppress skipped when bare motor exists on controller  

Reproduce: `test_m220_aux_identity.py`
