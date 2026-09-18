# Gate 2 — Manual end-to-end channel trace (PLC5 evidence)

**Runtime SHA:** `35bbb91` (matches HEAD)  
**Held-back virgin site:** not inspected  
**Subject:** Conveyor `5MCR1` → Hardware channel on ORNCCP5

## Chain

| Stage | Value |
|-------|-------|
| raw RUN file | `workspace/cp5-run/RUN/FORTNA/Conveyor.asc` |
| CP2 typed record | `IO_Name=5MCR1`, `IO_Address_Word=500`, `IO_Address_Bit=2`, `Machine_Name=ORNCCP5`, `Type=INVALID` (logical catalog), Desc=ENERGIZE MASTER CONTROL RELAY |
| CP3 reference | Configio word map join on Octal_Word **500** (not name similarity) |
| Configio physical address | `Configio.asc.ORNCCP5` row Desc=`CP5-NODE51-1A`, Octal_Word=`500`, LoHi=`Low`, Bank=`0`, In_Out=`0000000011111111` |
| EIPModules / eipcfg | NODE51 → adapter IP `192.168.1.51` → `CP5RIO0` / 1794-AENT + child modules |
| physical adapter/module/channel | `CP5RIO0:O.Data[0].2` (slot/data_index scheme 1794) |
| engineering owner | `5MCR1` from Conveyor claim at word.bit |
| HardwareIOModel | `owner_state=ASSIGNED`, `owner_source=RUN_CONVEYOR`, `engineering_owner=5MCR1` |
| dashboard channel object | same HardwareIOModel channel dict |
| `hwChannelEndpointLabel()` | text=`5MCR1`, kind=`ok`, ownerState=`ASSIGNED` |
| rendered text | **5MCR1** |

## First bad transformation (unused bits on same module)

| Stage | Before | After (bug) | After (fix) |
|-------|--------|-------------|-------------|
| Configio Desc | `CP5-NODE51-1A` (topology form `panel_node`) | `_configio_desc_claim` → **occupied** | topology-only → **not** occupancy |
| unused bit e.g. Data[0].0 | no Conveyor owner | `UNRESOLVED_OWNER` | `PROVEN_SPARE` + `CONFIGIO_MAPPED_UNUSED_BIT` |

**Root cause file/function:** `fortna_hardware_io_model.py` → `_configio_desc_claim` / `_channel_configio_claim`  
**Why it failed:** PANEL-NODE / PANEL-CATALOG Desc proves module mapping, not that every bit has an engineering owner.
