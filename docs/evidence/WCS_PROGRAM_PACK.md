# WCS_Interface_TCP_IP Program Pack (Gate G / H)

**Status:** Architecture contract from validation oracles — **not** a compiler implementation.  
**Machine-readable twin:** [`config/program_packs/wcs_interface_contract.json`](../../config/program_packs/wcs_interface_contract.json)

Finished PLCs are **validation oracles only**. Sorter presence does **not** imply WCS is mandatory until site evidence says so.

---

## Cross-controller presence

| Controller | WCS_Interface_TCP_IP | Task / rate (oracle) | Sorter_Track |
|------------|---------------------:|----------------------|--------------|
| PLC2 finished | **NO** | — | **NO** |
| PLC4 finished | **YES** | `P03_WCS_10ms` PERIODIC Rate=10 Priority=3 | YES (with Sawtooth_Merge on P02) |
| PLC5 RTfinished | **YES** | `P03_WCS_10ms` PERIODIC Rate=10 Priority=3 | YES |

**Conclusion:** WCS is an **optional** STANDARD_ARCHITECTURE pack used when the site has host TCP messaging. PLC2 proves sorter/WCS are not universal. PLC4 proves WCS can coexist with Sorter_Track + Sawtooth without being “sorter-only.”

Oracles:
- PLC5: `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X`
- PLC4: `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC4 finished.L5X`

---

## Exact routine list (PLC4 = PLC5)

Main: **`Main_Routine`**

| Routine | Type | Role | Class |
|---------|------|------|-------|
| Main_Routine | RLL | JSR scheduler | STANDARD_ARCHITECTURE |
| INIT | ST | Socket / buffer init | STANDARD_ARCHITECTURE + COMMISSIONING_VALUE |
| WCS_TCP_Server_Interface | RLL | TCP server accept/read/write | STANDARD_ARCHITECTURE + SITE_CONFIGURATION |
| WCS_Outbound_MSG_FIFO_Unload | RLL | Outbound FIFO unload | STANDARD_ARCHITECTURE |
| WCS_Outbound_MSG_Router | RLL | Route heartbeat / decision request / decision update | STANDARD_ARCHITECTURE |
| WCS_Inbound_MSG_FIFO_Unload | RLL | Inbound FIFO unload | STANDARD_ARCHITECTURE |
| WCS_Interface_Fault_Monitor | RLL | Fault / link monitor | STANDARD_ARCHITECTURE |
| SBR_Inbound_MSG_FIFO_Load | RLL | Load inbound FIFO from socket | STANDARD_ARCHITECTURE |
| SBR_Inbound_MSG_Deconstruct | RLL | Parse STX/ETX framed payload | STANDARD_ARCHITECTURE + SITE_CONFIGURATION (frame chars) |
| SBR_Inbound_MSG_Router | RLL | ACK / NAK / decision response | STANDARD_ARCHITECTURE |
| SBR_Inbound_MSG_ACK | RLL | ACK path | STANDARD_ARCHITECTURE |
| SBR_Inbound_MSG_NAK | RLL | NAK path | STANDARD_ARCHITECTURE |
| SBR_DecisionResponse_Update | RLL | Apply host decision → token Destination | STANDARD_ARCHITECTURE (**Sorter interface**) |
| SBR_Heartbeat_MSG | RLL | Heartbeat compose/send | STANDARD_ARCHITECTURE + COMMISSIONING_VALUE |
| SBR_DecisionRequest_MSG | RLL | Decision request compose/send | STANDARD_ARCHITECTURE (**Sorter interface**) |
| SBR_DecisionUpdate_MSG | RLL | Divert confirm / status update to host | STANDARD_ARCHITECTURE (**Sorter interface**) |

Gold pack `tools/libraries/programs/WCS_Interface_TCP_IP_Program.L5X` matches this routine set (Greensboro-fixed validation asset).

---

## Element classification

| Element | Class | Notes |
|---------|-------|-------|
| Program + routine skeleton | STANDARD_ARCHITECTURE | Identical PLC4/PLC5 |
| Task class `wcs` @ ~10 ms | STANDARD_ARCHITECTURE | Oracle rate is example, not universal law |
| Helix/WCS message UDTs | STANDARD_ARCHITECTURE | Shared datatype family |
| TCP socket endpoint / port | SITE_CONFIGURATION / COMMISSIONING_VALUE | Engineer / IT |
| Decision-point count & lane strings | SITE_CONFIGURATION | Bound to divert topology |
| Heartbeat enable / timers | COMMISSIONING_VALUE | |
| Framing STX/ETX/separators | SITE_CONFIGURATION | Present as tags in oracle |
| Per-sorter divert confirm wiring | EQUIPMENT_INSTANCE | Only when Sorter_Track present |
| Custom message types beyond Helix set | CUSTOM_ENGINEERING / UNKNOWN | Not assumed |

---

## Sorter ↔ WCS interface (Gate H)

See also [`SORTER_TRACK_PROGRAM_PACK.md`](SORTER_TRACK_PROGRAM_PACK.md).

**Proven shared controller tags: 34** (PLC5 oracle, dual-referenced only).

Primary flows:
1. **Decision request:** Sorter `Scanner` raises `*_Induct_Decision_Request_Helix` + token id → WCS `SBR_DecisionRequest_MSG`.
2. **Decision response:** WCS `SBR_DecisionResponse_Update` writes token `Destination` consumed by Sorter divert logic.
3. **Divert confirm:** Sorter sets `Track_Divert_UDT.O.Conf_MSG` / `Conf_MSG_WCS_Token` → WCS `WCS_Outbound_MSG_Router` → `SBR_DecisionUpdate_MSG`.
4. **Lost package / recirc:** Sorter latches token ids → WCS outbound updates.

WCS without Sorter_Track is structurally possible (heartbeat + TCP), but Greensboro PLC4/PLC5 oracles couple them via divert/token tags. PLC2 has neither.

---

## Reusable PROGRAM CONTRACT

```
INPUT MODEL: WCSModel { enabled, endpoint, framing, decision_points[], heartbeat }
             optional SorterModel (when divert confirm / decision request required)
GENERATED PROGRAM: WCS_Interface_TCP_IP
TASK CLASS: wcs  (oracle example 10 ms)
ROUTINES: list above
DEPENDENCIES: WCS_*_MSG_UDT family, socket tags, optional Token_Sorter / Divert UDTs
AUTO-POPULATED: none from RUN alone for TCP endpoint; MsgWCS/MsgMap may hint peers (REVIEW)
ENGINEER-REQUIRED: endpoint, framing, enables, decision-point map, lane strings
VALIDATION: routine set match; no emit unless WCSModel.enabled; never auto-include from sorter discovery alone
```

---

## Readiness verdict

**WCS PACK: MORE_EVIDENCE_REQUIRED**

Why:
1. Routine architecture is stable across PLC4/PLC5, but **message field schema / Helix payload contract** is not yet extracted into a generic, site-independent pack specification.
2. TCP endpoint, framing, and decision-point maps are engineer/commissioning — no complete RUN authority path proven for emit.
3. Gold WCS L5X is Greensboro-fixed; cloning is forbidden.
4. Must not auto-include from sorter discovery (`docs/SORTER_COMPILER_MODEL.md` policy).

Do **not** mark compilers COMPLETE. Do **not** emit hollow WCS programs.
