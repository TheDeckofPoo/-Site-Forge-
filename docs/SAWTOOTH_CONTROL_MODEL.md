# Sawtooth Control Model (draft)

**Status:** draft semantic model from generic `Sawtooth_Merge_Program.L5X` + CP4 RUN tables  
**Finished PLC4 used:** NO  
**Branch intent:** `feature/cp4-sawtooth-semantics`

This document describes the **actual** state/sequence vocabulary found in the library and RUN. It does **not** force names like “idle / lane available” unless those strings appear in sources.

---

## 1. Dual vocabularies (do not conflate)

| Layer | Source | Vocabulary |
|-------|--------|------------|
| RUN lane status display | `SawState.asc` | `ERROR`, `IDLE`, `HOLDING`, `WAITING`, `RELEASING`, `HANGING` |
| RUN HS lane FSM labels | `HSSawState.asc` | `Stopped`, `Wait PE On`, `Wait Resrv`, `Feed Slow`, `Feed Fast`, `Wait PE Off Slow`, `Wait PE Off Fast` |
| Library collector merge mode | `RT_CollTrackResvMngr` comments | `0` Not Running AUTO · `1` Startup run-out · `2` Startup wait lanes · `3` Normal |
| Library per-lane mode | `SR_LaneCntrl` comments (`diLaneMode`) | `0` Stopped · `1` Startup · `2` Normal · `3` Manual/Maint |

Observed live RUN `SawLane.pState` samples on this site include `IDLE`, `WAITING` (and historically `RELEASING` / `HANGING` in older overlays). Mapping RUN `pState` ↔ library `diLaneMode` is **not yet proven** and remains an open semantic item.

---

## 2. Program shape (library)

Entry: `Main_Routine`

1. Always JSR: `Conv_Fast`, `Conv_PE`, `Conv_Enc` (empty stubs in generic pack; fidelity pass fills from RUN).
2. Gated by `Enable_Merge2_Trk` + `Use_GapStore_Belts`:
   - `XIO(Use_GapStore_Belts)` → `RT_DeltaDist_NoGapStore`, `RT_IO_Map_NoGapStore`
   - Also sets collector HMI speed (400 FPM gap-store vs 140 FPM no-gap-store).
3. Gated by `Enable_Merge2_Trk` + `Enable_Merge1_Reserv` → `RT_CollTrackMain`:
   - init / reset counts / hist / PE cal / lane merge capture / lane offset find
   - `RT_CollTrackResvMngr` (slot search/reserve/clear/check)
   - `SR_LaneCntrl` (per-lane slug + reservation handshake)

See `exports/cp4-semantics/sawtooth_routine_graph.md`.

---

## 3. Collector reservation modes (`RT_CollTrackResvMngr`)

Library evidence (routine comments):

| Mode | Entry (summary) | Controlling signals | Exit | Outputs / effects | Confidence |
|------|-----------------|---------------------|------|-------------------|------------|
| **0 – Not Running AUTO** | Collector not running in auto | Collector running/auto status | When collector returns to auto / startup path | Revoke/remove reservations; clear queues | high (commented) |
| **1 – Startup run-out** | Enter startup; clear queues | Startup path after stopped | When run-out complete → mode 2 | Clear reservation queues; prepare lanes | high (commented) |
| **2 – Startup wait lanes** | Waiting for all lanes to complete merge | Lane complete / OK-to-run flags; startup safety timer | All lanes complete → mode 3; else wait | `xOkToReleaseLane` style enable to lanes | high (commented) |
| **3 – Normal** | Normal merging | Reservation request queue; priority; fault revoke; slot-at-merge checks | Fault / stop → back toward 0 | Grant/revoke slots; call `SR_CollTrackSrchSlot` / `Rsrv` / `Clr` / `Chk` / `SlotAtMrgPnt` | high (commented) |

**RUN evidence:** `SawMerge` provides `MotorIO=VFD414_AUX`, `ReserveIN=SAW_RESERVATION`, `LaneEnableDelayTM=tmSawMerge_DLY`, `pSliceSeconds=18`. HSSaw* tables are present but **empty of active named rows** on this machine overlay.

---

## 4. Per-lane modes (`SR_LaneCntrl` / `diLaneMode`)

Library evidence (`SR_LaneCntrl` header comments):

| Mode | Name (library) | Entry | Controlling signals | Exit | Outputs / side effects | Confidence |
|------|----------------|-------|---------------------|------|------------------------|------------|
| **0** | Stopped | `xLaneStop` OR NOT `xLaneStartupEnable` OR NOT `xOkToReleaseLane` | stop / enable / OK-to-release | When enables return → can go Startup (1) | Clears startup-complete when leaving ≠1 path | high |
| **1** | Startup | Transition from mode 0 | Merge parcels still on power-turn / inject | `xStartupComplete` → mode 2 | Startup merge behavior | high |
| **2** | Normal | Startup complete | Slug ready / reservation handshake bits | Stop/maint/fault conditions | Slot search, wait-for-resv, wait-for-slot, merging | high |
| **3** | Manual/Maint | `xLaneMaintMode` | maint bit | Leaving maint | Forces mode 3 while maint true | high |

### 4.1 Normal-mode subconditions (library bits — not RUN `pState` names)

These are **actual library signals** used inside mode 2:

| Condition | Entry | Controlling signals | Timers | Exit | Outputs | Confidence |
|-----------|-------|---------------------|--------|------|---------|------------|
| Search for slot | Slug approaching collector / ready | `xSearchForSlot`, `xSlugApproachClctrSrch`, `xSlugReadyToRelease_Q2` | (slug measure timers on Q1/Q2) | Slot reserved ack | Reservation request toward resv manager | medium-high |
| Waiting for reservation | Search asserted | `xLaneWaitingForResv` | — | `xSlotReserved` | Stay held until grant | high |
| Waiting for slot at merge | Slot reserved | `xLaneWaitingForslot` + `xSlotReserved` | — | `xSlotAtMergePoint` → merging; `xSlotPastMergePoint` → abort/clear | Hold lane until merge window | high |
| Lane merging / releasing slug | Slot at merge point | `xLaneMerging`, `xSlugReleasing_Q2`, `xOkToReleaseLane` | `tmrSlugReleased_Q2`, `tmrSlugHalted_Q2` | `xSlugReleased_Q2` (and mode=2) clears merging/search/wait bits; halt/collector not at speed aborts | Drive release / clear slot via `SR_CollTrackClrSlot` | high |
| Full-eye affects slug length | N/A (IO map) | `EZPE*.Full` in `RT_IO_Map_NoGapStore` | — | — | Selects `ReleaseLengthFull` vs `ReleaseLength` per HMI lane | high |

**RUN evidence (lane row fields):** `PhotoEyeIO`, `DisableIO`, `SliceSeconds`, `ReserveSeconds`, `ReserveTM`, `ReserveWhen=ReserveTM=red`, `ApproachUP`, `CollisionUP`, `LaneIN`, `AllowedToRun`, live `pState`.

---

## 5. Full-eye / ReserveTM semantics (critical)

Two related but **not identical** roles appear:

1. **RUN `SawLane.ReserveTM`** (e.g. `tmfcEZPE217_F`) — Fortna-side reservation timing tied to a full-eye clear timer (`Fullline.Clr_Timer_Name`).
2. **Pack `EZPE*.Full`** in `RT_IO_Map_NoGapStore` — selects slug **release length** when gap-store belts are not used.

| Site lane | ReserveTM (RUN) | Pack `EZPE*.Full` (library) | Notes |
|-----------|-----------------|----------------------------|-------|
| LANE_0_P219 | `tmfcEZPE217_F` | `EZPE127_F` | No pack `EZPE217_F`; **do not** digit-map 127→217 |
| LANE_1_P408 | `tmfcEZPE408_F` | `EZPE408_F` | Exact match |
| LANE_3_P116 | `tmfcEZPE116_F` | `EZPE116_F` | Exact match |
| LANE_4_P214 | `tmfcEZPE212_F1` | `EZPE212_F2` | **Conflict** — see reserve eye analysis |
| LANE_5_P832 | `tmfcEZPE832_F` | `EZPE832_F` | Exact match |

Details: `exports/cp4-semantics/reserve_eye_analysis.md`.

---

## 6. Feature gates (engineer configured)

| Tag | Effect in `Main_Routine` | Confidence |
|-----|--------------------------|------------|
| `Enable_Merge2_Trk` | Enables tracking / delta-dist / IO map / (with reserv) coll track | high |
| `Enable_Merge1_Reserv` | With Merge2, enables `RT_CollTrackMain` | high |
| `Use_GapStore_Belts` | Selects gap-store vs no-gap-store path + collector speed | high |
| `Enable_hold` | Present on conveyor UDT members; site policy | medium |

---

## 7. Encoder / VFD seeds (from discovery / pass)

- Collector motor / enable path: `SawMerge.MotorIO = VFD414_AUX` (RUN_EXPLICIT).
- Encoder `ENC414`: ticks/ft=6, target 150 FPM, enable `VFD414_AUX`, jamzone `SAWTOOTH MERGE` (RUN_EXPLICIT).
- Encoder `ENC424`: city-counter associated; not sawtooth primary.
- Lane drives (RUN_EXPLICIT): `VFD219`, `VFD410_EN`, `VFD118_EN`, `VFD216_EN`, `VFD834_EN`.

See `exports/cp4-semantics/merge_signal_map.json` and `encoder_vfd_notes_seed.json`.

---

## 8. Open items for parent refinement

1. Proven mapping between RUN `SawLane.pState` / `SawState.asc` names and library `diLaneMode` + wait/merge bits.
2. Whether HSSaw* empty tables mean Logix-only control on this site (no HS sawtooth C-side active).
3. LANE_0 pack bind `EZPE217_F` (add tag + replace `EZPE127_F.Full`).
4. LANE_4 decide `EZPE212_F1` (ReserveTM) vs `EZPE212_F2` (pack Full / Fullline→P214) — may be two different roles.
5. Which pack conveyors beyond the five lane UDTs are required on the collector train (`P412`, `P418`, jam eyes `PE414*_J`, etc.).

---

Finished PLC4 was not read. Draft only — parent may refine after generation.
