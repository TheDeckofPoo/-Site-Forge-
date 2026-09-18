# Sorter_Track Program Pack (Gate F / H)

**Status:** Architecture contract from validation oracle — **not** a compiler implementation.  
**Oracle used:** `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X`  
(Newest local `*RTfinished*.L5X`; no `RTfinished(3)` copy found. Same bytes also under `workspace/validation/`.)  
**Machine-readable twin:** [`config/program_packs/sorter_track_contract.json`](../../config/program_packs/sorter_track_contract.json)

Finished PLC is a **validation oracle only** — never a discovery source. Site identities below are labeled as validation-oracle examples.

---

## Gate E context (PLC5 oracle structure)

| Item | Value (oracle) | Class |
|------|----------------|-------|
| Controller | `ORLY_Greensboro_NC_PLC5` / 1756-L83E v35.11 | SITE_CONFIGURATION |
| Programs | ES, HMI, IO_MAP, PLC_Fast, Redroom_Area_{Fast,L1,L2,L3,Slow}, ShippingSorter_Area_{Fast,L1,L2,L3,Slow}, **Sorter_Track**, Sys, System, **WCS_Interface_TCP_IP** | mix (see below) |
| Sorter_Track task | `P02_Track_5ms` PERIODIC Rate=5 Priority=2 | STANDARD_ARCHITECTURE (class=`tracking`) |
| WCS task | `P03_WCS_10ms` PERIODIC Rate=10 Priority=3 | STANDARD_ARCHITECTURE (class=`wcs`) |
| Area Fast/Slow | P10 50ms / P11 200ms | STANDARD_ARCHITECTURE |
| Area L1/L2/L3 + Sys | P15_* EVENT | STANDARD_ARCHITECTURE |
| IO_MAP | Present but **not scheduled** on any task in this finished export | UNKNOWN / CUSTOM_ENGINEERING |
| Open AOI defs | 4 (`AOI_SNTP_QUERY`, `AOI_TIME_*`, `Z_AO_DELTA`) — track AOIs are sealed EncodedData | STANDARD_ARCHITECTURE (library) |
| UDT count | 219 user types | STANDARD_ARCHITECTURE + SITE_CONFIGURATION |
| Modules | 68 | SITE_CONFIGURATION / EQUIPMENT_INSTANCE |

### Program classification (PLC5)

| Program | Class |
|---------|-------|
| Sorter_Track | STANDARD_ARCHITECTURE (reusable pack candidate) |
| WCS_Interface_TCP_IP | STANDARD_ARCHITECTURE (optional pack; not sorter-mandatory — see WCS pack) |
| ShippingSorter_Area_* / Redroom_Area_* | EQUIPMENT_INSTANCE / SITE_CONFIGURATION (area instances) |
| ES | STANDARD_ARCHITECTURE (safety) |
| Sys / System / HMI / PLC_Fast / IO_MAP | STANDARD_ARCHITECTURE (platform) |

---

## Exact routine list (PLC5 Sorter_Track)

Main routine name: **`Main`** (not `Main_Routine`).

JSR order from `Main` (oracle):

1. Encoder  
2. Track_Pointer  
3. Track_Induct_Package  
4. Track_Manual_Destination  
5. Scanner  
6. Track_Package  
7. Track_Lost_Package  
8. Divert_Lane_Status  
9. Track_Divert_Package  
10. Wave_Divert  
11. Divert_Rate_Limit  
12. Track_Divert_Confirm  
13. Track_Offset_Find  
14. Gridlock_Prevention  
15. Response_Time  
16. RT_Virtual_Enc  

| Routine | Type | Rungs (oracle) | Purpose |
|---------|------|---------------:|---------|
| Main | RLL | 17 | Scheduler — JSR only |
| Encoder | RLL | 10 | Encoder pulse / speed AOI (`Enc_RIOCard`, virtual enc) |
| Track_Pointer | RLL | 5 | `TRK_Pointer` advance along track groups |
| Track_Induct_Package | RLL | 2 | Induct PE → token generate/update |
| Track_Manual_Destination | RLL | 2 | Manual destination override |
| Scanner | RLL | 8 | Scan associate; raise decision-request handshake |
| Track_Package | RLL | 14 | Token search / transfer / exit PE tracking |
| Track_Lost_Package | RLL | 5 | Lost-package detect → WCS-facing token latches |
| Divert_Lane_Status | RLL | 56 | Map lane Full PE → `Divert.PI.Full` |
| Track_Divert_Package | RLL | 48 | `Track_Divert_AOI` fire / destination consume |
| Wave_Divert | RLL | 16 | `TRK_Divert_WaveFunction` |
| Divert_Rate_Limit | RLL | 18 | Rate limiting |
| Track_Divert_Confirm | RLL | 1 | Confirm divert → WCS confirm/recirc signals |
| Track_Offset_Find | RLL | 24 | `TRK_OffsetFind_PE` commissioning offsets |
| Gridlock_Prevention | RLL | 9 | Gridlock inhibit (PLC5 present; PLC4 gold pack lacks) |
| Response_Time | RLL | 4 | WCS response-time metrics |
| RT_Virtual_Enc | ST | — | Virtual encoder ST (PLC5 present; gold pack **missing**) |

**PLC4 Sorter_Track routines (for delta):** same set **minus** `Gridlock_Prevention` and `RT_Virtual_Enc`.

**Gold pack** `tools/libraries/programs/Sorter_Track_Program.L5X`: matches PLC5 list **minus** `RT_Virtual_Enc` — Greensboro-fixed validation asset, not a generic library.

---

## Per-routine contract summary

| Routine | Required tags / UDTs / AOIs | Relationships | Value classes |
|---------|----------------------------|---------------|---------------|
| Encoder | `Enc_UDT`, `Enc_RIOCard`, `Enc_Virtual_DistBased`, `ENC*_Direct_In_Pulse` | Encoders / sorter motor enable | STANDARD + COMMISSIONING (scale/FPM) + EQUIPMENT_INSTANCE |
| Track_Pointer | `TRK_Pointer`, `Track_Group_*` | Tracking conveyors / slot groups | STANDARD + SITE_CONFIGURATION (group size) |
| Track_Induct_Package | `TRK_Induct_TokenGenerate`, `TRK_Induct_TokenUpdate`, `Track_Induct_UDT`, induct PE | Induct PE / tracking conveyor | STANDARD + EQUIPMENT_INSTANCE |
| Scanner | Scanner raw/results, `Token_SCN*`, decision-request BOOL | Scanner device / WCS decision point | STANDARD + SITE_CONFIGURATION |
| Track_Package | `TRK_SearchToken_*`, `TRK_Token_Transfer`, exit PE | Tracking PEs / exit confirm | STANDARD + EQUIPMENT_INSTANCE |
| Track_Lost_Package | `TRK_Lost_Package`, `*_WCS_Token_Lost_Package` | Exit path → WCS | STANDARD + EQUIPMENT_INSTANCE |
| Divert_Lane_Status | Full PE → `Track_Divert_UDT.PI.Full` | Downstream Full PE | EQUIPMENT_INSTANCE mapping |
| Track_Divert_Package | `Track_Divert_AOI`, `Track_Divert_UDT`, destination | Divert solenoid / lane CFG | STANDARD + COMMISSIONING (offsets) + EQUIPMENT_INSTANCE |
| Wave_Divert | `TRK_Divert_WaveFunction` | Divert timing wave | STANDARD + COMMISSIONING |
| Divert_Rate_Limit | rate timers / enables | Divert traffic shaping | STANDARD + COMMISSIONING_VALUE |
| Track_Divert_Confirm | `Divert.O.Conf_MSG*`, recirc BOOL/DINT | → WCS confirm messages | STANDARD interface + EQUIPMENT_INSTANCE |
| Track_Offset_Find | `TRK_OffsetFind_PE` | Encoder counts induct→divert | COMMISSIONING_VALUE / currently NOT_SUPPORTED to synthesize |
| Gridlock_Prevention | gridlock UDT / inhibits | Area full / prevent | SITE_CONFIGURATION / CUSTOM_ENGINEERING |
| Response_Time | `WCS_Response_Time_*` metrics | WCS latency monitor | STANDARD + COMMISSIONING_VALUE |
| RT_Virtual_Enc | virtual enc ST | Encoder substitute | STANDARD_ARCHITECTURE (optional) |
| Track_Manual_Destination | `Manual_Destination` UDT | HMI / WCS gate | SITE_CONFIGURATION |

**RUN-populatable (discovery):** sorter identity, encoder link, scan zone, divert lane topology (`Sorters`, `Encoders`, `SrtScanBoss`, `SrtZoneLane`).  
**Engineer-required:** divert output IO (often INVALID in RUN), track offsets/triggers, wave timing, rate limits, gridlock policy, socket/decision-point wiring when WCS present.

---

## Reusable PROGRAM CONTRACT

```
INPUT MODEL (canonical — origin-agnostic):
  SorterModel { sorters[], encoders[], scan_zones[], divert_lanes[], induct_pes[], tracking_pes[] }
  LogicalSignalModel (enable/jam/latch refs when sorter areas participate)
  optional WCSModel (only if site requires host messaging)

GENERATED PROGRAM: Sorter_Track
TASK CLASS: tracking  (oracle example rate 5 ms — not a universal constant)
ROUTINES: Main + list above (Gridlock / RT_Virtual_Enc optional leaves)
DEPENDENCIES:
  sealed track AOI library (Enc_*, TRK_*, Track_Divert_*)
  Token / Track_Group / Divert UDTs
  optional WCS handshake tags (see interface matrix)
AUTO-POPULATED: structure from SorterModel when PROVEN
ENGINEER-REQUIRED: divert IO, offsets, wave/rate, confirm mapping
VALIDATION: routine set ⊇ core track leaves; no silent gold-pack clone;
  divert trigger remains NOT_SUPPORTED until generic timing contract exists
```

---

## Sorter ↔ WCS interface (Gate H) — proven shared controller tags

Proven = identifier appears in **both** `Sorter_Track` and `WCS_Interface_TCP_IP` logic of the PLC5 oracle, and exists as a controller tag.

**Count: 34 controller-scoped shared roots** (16 are divert-instance UDTs).

| NAME | SCOPE | DATATYPE | WRITER (heuristic) | READER | PURPOSE | PROVENANCE |
|------|-------|----------|--------------------|--------|---------|------------|
| P504_Induct_Decision_Request_Helix | Controller | BOOL | BOTH (ST sets; WCS consumes/clears) | WCS Outbound router / ST Scanner | Decision-request handshake | PLC5 oracle dual-ref |
| P504_Induct_WCS_Token_Found | Controller | DINT | Sorter_Track | WCS | Induct token id to host | PLC5 oracle dual-ref |
| Token_SCN504 | Controller | Token_Sorter[1000] | Sorter_Track (primary) | WCS | Shared token store | PLC5 oracle dual-ref |
| Track_Group_SCN504 | Controller | Track_Group_UDT | Sorter_Track | WCS | Track group state | PLC5 oracle dual-ref |
| P504_ManualDest | Controller | Manual_Destination | HMI/ST | WCS Main + ST | Manual dest gate | PLC5 oracle dual-ref |
| P5xx_Exit_Lost_Package_Detect | Controller | TRK_Lost_Package | Sorter_Track | WCS | Lost-package event | PLC5 oracle dual-ref |
| P5xx_WCS_Token_Lost_Package | Controller | DINT | Sorter_Track | WCS | Lost token id | PLC5 oracle dual-ref |
| P510_Send_WCS_MSG_Recirc | Controller | BOOL | BOTH | WCS / ST | Recirc confirm pulse | PLC5 oracle dual-ref |
| P510_WCS_Token_Recirc | Controller | DINT | Sorter_Track | WCS | Recirc token id | PLC5 oracle dual-ref |
| P506/508/509/510_DivertN | Controller | Track_Divert_UDT | Sorter_Track (AOI) | WCS (`O.Conf_MSG`, `O.Conf_MSG_WCS_Token`, `CFG.Lane_Number`) | Divert confirm → DecisionUpdate | PLC5 oracle dual-ref |
| PLC | Controller | PLC_UDT | Sys/other | both | Timestamp / DTS helper | PLC5 oracle dual-ref |

Member-level WCS read pattern (proven): `XIC(P*_Divert*.O.Conf_MSG)` + `Conf_MSG_WCS_Token` + `Token_SCN504[token].{ID,Barcode,Diverted_Lane}` → `SBR_DecisionUpdate_MSG`.

No guesses beyond these dual-referenced tags.

---

## Readiness verdict

**SORTER_TRACK PACK: MORE_EVIDENCE_REQUIRED**

Why:
1. Core architecture + routine set is proven from oracle + gold pack, but **generic sealed AOI library / open parameter contracts** are not yet packaged for emit.
2. Divert **trigger/offset** synthesis remains `NOT_SUPPORTED` (no complete RUN→offset map).
3. Gold `Sorter_Track_Program.L5X` is Greensboro-fixed (lane/PE/divert instances) — cloning it would violate anti-cheat / library policy.
4. PLC4 vs PLC5 routine delta (`Gridlock_Prevention`, `RT_Virtual_Enc`) needs explicit optional-leaf policy before READY_TO_IMPLEMENT.

Do **not** mark compilers COMPLETE. Do **not** emit hollow Sorter_Track programs.
