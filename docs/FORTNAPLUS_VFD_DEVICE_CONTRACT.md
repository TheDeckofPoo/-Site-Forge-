# FortnaPlus VFD Device Contract

**Gates:** E (source signal model), F (canonical model), I (generation contract)  
**Evidence roots (blind-test constrained):** `workspace/cp4-run`, `workspace/cp5-run`, `workspace/_plc2_run_peek`, FortnaPlus source, `fortna.mnu` / `project.mnu`, cataloged artifacts, `OReilly_Library_v3.L5X`.  
**Held-back virgin site:** not inspected.

---

## 1. Source model (what Fortna actually stores)

### 1.1 Discrete drive points — `FORTNA/Conveyor.asc` (universal catalog)

Known-site VFDs appear as Conveyor `IO_Name` rows owned by `Machine_Name` (ORNCCP4 / ORNCCP5; ORNCCP2 has **zero** VFD rows):

| Pattern | Example description | Role | Typical direction (when Configio-proven) |
|---------|---------------------|------|------------------------------------------|
| `VFD###_EN` or bare `VFD###` | `START VFD###` | **START_ENABLE_CMD** | OUTPUT |
| `VFD###_AUX` | `VFD### IS RUNNING` | **RUNNING_FEEDBACK** | INPUT |
| `VFD###_FLT` | `VFD### HAS FAULTED` | **FAULT_STATUS** | INPUT |

Observed on PLC2/4/5 plant catalog: suffixes **AUX / EN / FLT / bare only**. No JOG / MOP / AT_SPEED / READY / CLR_FLT Conveyor rows on these known sites.

- `Type` is usually `MOTOR` (sometimes blank/`INVALID` on FLT rows) — catalog class noise, not Ethernet proof.
- `IO_Module_Type` is often `N/A` on the Conveyor row; **physical family comes from Configio word ownership** (e.g. CP5 `524`/`525` → 1794-OB16P / 1794-IB16).
- These points are **physical discrete I/O** when Configio maps the word/bit. They are **not** Ethernet module members by themselves.

### 1.2 Speed-control network fields — `PROJECT/SpdControl.asc` + `project.mnu`

| Field | Menu | DLIST target | Known-site values (PLC2/4/5) |
|-------|------|--------------|------------------------------|
| `VFD_NetCTRL` | SpdControl | Conveyor | **INVALID** (unconfigured) |
| `VFD_NetREF` | SpdControl | Conveyor | **INVALID** |
| `VFD_Reset` | SpdControl | Conveyor | **INVALID** |
| `VFD_Aux` | SpdControl | Conveyor | **INVALID** |
| `VFD_RstTimer` | SpdControl | timemenu | **N/A** |

These are the Fortna schema hooks for **networked / Ethernet VFD control** (selection → Conveyor named objects + IOAction). On known sites they are present in schema but **not configured** — do not fabricate mappings.

### 1.3 Graphics belt fields — `FORTNA/GpxBelt.asc` + `fortna.mnu`

`VFD_EN`, `VFD_S1`, `VFD_S2`, `VFD_S3` → DLIST Conveyor. On known sites every row is **INVALID**. Treat as OPTIONAL / NOT CONFIGURED graphics bindings, not generation inputs.

### 1.4 Library Ethernet object (capability, not known-site RUN population)

`VFD_UDT` (`NO_VFD` tag datatype) carries networked drive identity/status:

- `VFDIn` / `VFDOut` (`VFD_PF525_VFDIn` / `VFD_PF525_VFDOut`) — Ready, Faulted, AtReference, Start/Stop/Jog, ClearFaults, MOPIncrement/Decrement, Accel/Decel rate selects, Forward/Reverse, ForceKeypadCtrl, Comm counters, etc.
- `Sts_CommFlt`, `IP_Address`, `MACId`, `Comm_Code` — communication / identity
- AOIs `AB_VFD35` / `AB_VFD525` / `AB_VFD750` exist in the library catalog map

**Known-site generation does not bind real `VFD_UDT` instances** for transport conveyors: `Fast_Conv` / `Slow_Flt` pass `NO_VFD` for the Ethernet `IO_VFD` slot.

---

## 2. Canonical model choice (Gate F)

| Concern | Model | Rationale |
|---------|-------|-----------|
| Physical FLEX/Point channel | **HardwareIOModel** | Word/bit → module `.Data` only |
| Discrete VFD feeder device | **VFDDeviceModel** binding `DISCRETE_MOTOR_STARTER` | Proven CP4/CP5 path: one `P###_VFD` `Motor_Starter_UDT` owns EN/AUX/FLT |
| Ethernet / networked drive | **VFDDeviceModel** binding `ETHERNET_VFD_UDT` | Library-capable; activate only when SpdControl/network + module evidence proves it |
| Logical SpdControl / Gpx selections | Selection refs on VFDDeviceModel / control graph | INVALID = ABSENT_REFERENCE — never invent BOOL |

**Do not** collapse VFD command/status into HardwareIOModel *as the device* merely because IO_MAP aliases a FLEX bit onto a UDT member. HardwareIOModel holds channels; VFDDeviceModel owns drive identity, signal roles, PLC tag binding, and provenance.

Reuse existing emitters:

- `fortna_autogen._vfd_ms_member` / Motor_Starter ensure-loop for discrete path
- `clone_template_for_conveyor` uses `P###_VFD` as `IO_MS` and `NO_VFD` as `IO_VFD`
- SiteModel `vfds` / `drives` buckets remain discovery lists; VFDDeviceModel is the typed contract

---

## 3. Command / status role map

### 3.1 Discrete Motor_Starter path (known-site proven)

| Role | Fortna evidence | PLC member (`Motor_Starter_UDT`) |
|------|-----------------|----------------------------------|
| START_ENABLE_CMD | `VFD###_EN` / bare `VFD###` (desc START…) | `.O.Run` |
| RUNNING_FEEDBACK | `VFD###_AUX` (IS RUNNING) | `.I.Auxiliary_Forward` |
| FAULT_STATUS | `VFD###_FLT` (HAS FAULTED) | `.Flt.PS_Flt` (`Flt` → `PS_Fault`) |

Optional MS-shaped suffixes (CONT_FLT, MS_OK, …) follow `_vfd_ms_member` only when Fortna names prove them.

### 3.2 Ethernet VFD_UDT path (library roles — emit only when configured)

Command-ish library bits: Start, Stop, Jog, ClearFaults, Forward/Reverse, ForceKeypadCtrl, MOPIncrement/MOPDecrement, AccelRate1/2, DecelRate1/2, FreqCommand / LogicCommand.  
Status-ish: Ready, Active, Faulted, AtReference, Accelerating/Decelerating, ActualDir/CommandDir, DigIn*, Comm counters, FaultCode, Sts_CommFlt.

**Do not invent** these as Conveyor BOOL tags on sites that only have AUX/EN/FLT.

---

## 4. Generation contract (Gate I) — known-site checks

### ORNCCP5 (`exports/stabilization/plc5_hotbuild_full/ORNCCP5.L5X`)

| Check | Result |
|-------|--------|
| `Motor_Starter_UDT` present | YES |
| `VFD_UDT` dtype + `NO_VFD` | YES (null Ethernet slot) |
| `P###_VFD` tags | 29 × `Motor_Starter_UDT` |
| Bare `VFD*` BOOL tags | **0** (no dangling BOOL stubs) |
| IO_MAP member refs | `.I.Auxiliary_Forward`, `.O.Run`, `.Flt.PS_Flt` |
| `Fast_Conv` / `Slow_Flt` `IO_VFD` | **NO_VFD** only |
| PowerFlex Ethernet modules | **none** in this build |
| Duplicate device ownership | One `P###_VFD` per drive number; no BOOL+UDT pair |

### ORNCCP2 (`exports/stabilization/ORNCCP2.L5X`)

| Check | Result |
|-------|--------|
| VFD Conveyor rows for ORNCCP2 | **0** |
| `P###_VFD` tags | **0** (correct — no discrete VFD feeder on CP2) |
| `IO_VFD` | NO_VFD |

### Policy

- Missing required discrete member for a proven AUX/EN/FLT point → **FATAL** with provenance  
- SpdControl / Gpx VFD fields INVALID → **OPTIONAL / NOT CONFIGURED**  
- Ethernet `VFD_UDT` instance without network module + configured SpdControl → do not emit  

---

## 5. Blind-test note

Contract derived only from allowed known-site RUNs + FortnaPlus library/source. No held-back site identifiers or archives were used as evidence.
