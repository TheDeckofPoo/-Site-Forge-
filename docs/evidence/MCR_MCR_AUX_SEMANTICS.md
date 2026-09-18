# MCR vs MCR_Aux Semantics

**Gate:** J (archaeology before compiler behavior)  
**Evidence roots (blind-test constrained):** PLC2 / PLC4 / PLC5 RUN `FORTNA/Conveyor.asc`, Configio-backed `physical_io_map.csv`, `fortna.mnu` / `project.mnu` / `artifacts/mnu-schema.json`, FortnaPlus consumers (`fortna_autogen.py`, `fortna_motor_logic.py`, `fortna_safety_model.py`, `fortna_es_compiler.py`).  
**Held-back virgin site:** not inspected.

---

## 1. Are `MCR` / `MCR_Aux` schema fields?

**No.** There is no `fortna.mnu` / `project.mnu` definition field literally named `MCR` or `MCR_Aux`.

They are **Conveyor catalog named objects** (`IO_Name` patterns):

| IO_Name pattern | Example | General_Description (RUN) |
|-----------------|---------|---------------------------|
| `{n}MCR{m}` | `2MCR1`, `5MCR1` | `ENERGIZE MASTER CONTROL RELAY …` |
| `{n}MCR{m}_AUX` | `2MCR1_AUX`, `5MCR1_AUX` | `MASTER CONTROL RELAY … IS ENERGIZED` |

Plant catalog (shared across allowed RUN peeks) lists **8 coils + 8 aux** for panel indices 1–8, owned by Machine_Name:

| Machine | Coils | Aux |
|---------|-------|-----|
| ORNCCP2 | `2MCR1`, `3MCR1` | `2MCR1_AUX`, `3MCR1_AUX` |
| ORNCCP4 | `1MCR1`, `4MCR1`, `8MCR1` | matching `_AUX` |
| ORNCCP5 | `5MCR1`, `6MCR1`, `7MCR1` | matching `_AUX` |

---

## 2. Proven distinctions (not name inference)

| Axis | MCR coil (`nMCR1`) | MCR_Aux (`nMCR1_AUX`) |
|------|--------------------|------------------------|
| Description | ENERGIZE … | … IS ENERGIZED |
| Semantic role | **Command / coil** — energize master control relay | **Status / aux feedback** — relay is energized |
| Typical direction | **OUTPUT** | **INPUT** |
| Addresses | Distinct word/bit from aux | Distinct word/bit from coil |
| Configio proof (CP2) | `2MCR1` → word `200` bit `2` → `CP2RIO0:0:O.Data.2` (1794-OA8I) | `2MCR1_AUX` → word `201` bit `2` → `CP2RIO0:1:I.Data.2` (1794-IA16) |
| Configio proof (CP5) | `5MCR1` → `500/2` OA8I out | `5MCR1_AUX` → `501/2` IA16 in |

They are a **paired command/status relationship**, not aliases for one signal.

`Type` on these Conveyor rows is often `INVALID` (also seen `STRAIGHT` / `MOTOR` catalog noise). Per FortnaPlus taxonomy, Conveyor `Type=INVALID` with a real `IO_Name` remains a **valid named object** — not “delete / unused”.

---

## 3. Cardinality and equivalence

| Question | Answer |
|----------|--------|
| Cardinality | **1:1 pair** per panel MCR index when the panel exists (coil + aux both cataloged) |
| Equivalent? | **No** — coil ≠ aux |
| Can aux substitute for coil? | **No** |
| INVALID field token vs row Type | Field value INVALID elsewhere = ABSENT_REFERENCE; row Type INVALID ≠ discard |

---

## 4. Generation / consumer map

| Consumer | Coil (`nMCR1`) | Aux (`nMCR1_AUX`) |
|----------|----------------|-------------------|
| `fortna_autogen` IO_MAP / ES_UDT ensure | Energize output path; finished-style `CPn_MCR1` / `T_nMCR1` as `ES_UDT` | `*MCR*_AUX` → `.I.ES_OK` |
| `fortna_motor_logic.build_mcr_rungs` | OTL/OTU target from start/stop PB | Optional `XIC(mcr)OTE(mcr_aux)` mirror |
| `fortna_safety_model` | Classified device kind `MCR` for zone membership | Same name family (`\d+MCR\d*\w*`) |
| `fortna_es_compiler` | Zone MCR membership readiness | Same |

Known generated PLC:

- ORNCCP2: `T_2MCR1`, `CP2_MCR1`, `T_3MCR1`, `CP3_MCR1` as `ES_UDT` (coil-side safety objects)
- ORNCCP5: `T_5MCR1` / `CP5_MCR1`, `T_6MCR1` / `CP6_MCR1`, `T_7MCR1` / `CP7_MCR1`

Physical map still carries both coil and aux as discrete I/O endpoints.

---

## 5. INVALID / unconfigured frequency

- Catalog **lists both** whenever the panel MCR identity exists.
- Site instance may leave a point unmapped in Configio / IO_MAP → engineering UI: **OPTIONAL / NOT CONFIGURED**, do not fabricate.
- Safety zone membership is separate: device existence ≠ automatic zone assignment (see stabilization build notes for unassigned `CP3_MCR1`).

---

## 6. Site Forge policy (Curtis: both available)

1. Keep **both** MCR coil and MCR_Aux available as engineering options.  
2. Do not auto-collapse Aux → coil or invent missing Aux.  
3. Prove semantics from description + Configio direction/address before assigning compiler emit rules.  
4. If Aux is catalog-valid but unused on a site build → show **OPTIONAL / NOT CONFIGURED**, never invent a mapping.

---

## 7. Compiler behavior (deferred assignment)

Gate J proves semantics only. Emit rules already present in autogen/safety may continue; any change that treats Aux as optional feedback vs required ES_OK must cite this evidence and Configio provenance — not the substring `_AUX` alone.
