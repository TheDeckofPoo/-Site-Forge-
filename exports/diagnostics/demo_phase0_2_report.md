# Demo Phase 0–2 Report — Overnight Presentation Sprint

| Field | Value |
|---|---|
| MISSION | PHASES 0–2: contract guard + Conv_PE/PI root cause + Control_Station |
| REPOSITORY | `C:\dev\worktree\FortnaPlus-demo-ship` |
| BRANCH | `demo/reno-ship-sorter-readiness` |
| START SHA | `a935a22a86f93dceb0f3910d9f5c8f506a0c1a27` |
| FINAL SHA | `8f989817a250c8154851383ddc817e3c36bc76b9` |
| GOLD PICK (READ ONLY) | `C:\dev\worktree\FortnaPlus-anton\exports\current\MSCRENOPICK_2026_10_13_1725.L5X` |
| APPROVED LIBRARY | `tools/libraries/OReilly_Library_v3.L5X` |
| POLICY | CURRENT APPROVED LIBRARY WINS |

---

## PHASE 0 — Contract Version Guard

Artifact: [`exports/diagnostics/demo_greensboro_contract_guard.json`](demo_greensboro_contract_guard.json)

### Finished PLC refs used

| PLC | Path | Bytes |
|---|---|---|
| PLC2 | `C:\dev\Autogen Excel\1 PLC2\2026-08-11\PLC2_v3.L5X` | 3,557,072 |
| PLC4 | `C:\dev\Autogen Excel\2 PLC4\ORLY_Greensboro_NC_PLC4.L5X` | 8,366,423 |
| PLC5 | `C:\dev\Autogen Excel\3 PLC5\7-9-26\ORLY_Greensboro_NC_PLC5.L5X` | 3,910,047 |

### Contract notes (LIBRARY WINS)

| Contract | Library | vs PLC2 | vs PLC4 | vs PLC5 | Verdict |
|---|---|---|---|---|---|
| **AOI_SNTP_QUERY** | present rev 1.0 | MATCH params | MATCH | MATCH | LIBRARY_WINS |
| **Slow_ControlStation** | enc rev 1.1 sig `8C8CF333` | MATCH | MATCH | MATCH | LIBRARY_WINS |
| **Fast_Conv** | enc rev 1.1 sig `4FB60BA6` | MATCH | MATCH | MATCH | LIBRARY_WINS |
| **Slow_Flt** | enc rev 1.6 sig `E0341258` | VARIANT sig `050161DE` (params match) | MATCH sig (later ts) | VARIANT sig `050161DE` | **LIBRARY_WINS** (record older PLC sig) |
| **CommDiag_UDT** | **ABSENT** | ABSENT | PRESENT (`Index`,`IndexMax`,`Init`) | ABSENT | **LIBRARY_WINS_ABSENT** — do not import from PLC4 (PD-0029) |
| **Area_UDT** | 17 visible members incl EngMgmt* | MATCH | MATCH | VARIANT missing `EngMgmtTime/EngMgmtTmr_Dn/EngMgmt_AreaStop` | LIBRARY_WINS |
| **Area_PI** | 16 visible members incl `EngMgmt` | MATCH | MATCH | VARIANT missing `EngMgmt` | LIBRARY_WINS |
| **Conv_PI** (UDT) | 7 visible members | MATCH | MATCH | MATCH | LIBRARY_WINS |
| **CS_UDT** | 11 visible members | MATCH | MATCH | MATCH | LIBRARY_WINS |

### Variants to remember (oracle only — not emit authority)

1. **Slow_Flt** body signature: library/PLC4 = `E0341258`; older PLC2/PLC5 = `050161DE`. Params identical across all four.
2. **CommDiag_UDT**: finished PLC4-only datatype. Approved library does not carry it → production emit must not pull it from finished controllers.
3. **PLC5 Area_UDT / Area_PI**: older EngMgmt member set. Library (with EngMgmt) is the emit contract.

---

## PHASE 1 — Why Pick lacks Conv_PE / Conv_PI

### Gold Pick inventory (READ ONLY anton artifact)

| Program | Routines present | Missing vs finished Greensboro |
|---|---|---|
| `MSCRENOPICK_Area_Slow` | Main_Routine, Area_Logic, Area_PI, Control_Station, Conv_Flt, Conv_Jam, Stacklight | **Conv_PI** |
| `MSCRENOPICK_Area_Fast` | Main_Routine, Conv_Fast, Conv_Full | **Conv_PE** |

Finished PLC oracle (PLC2/4/5 Area_Fast/Slow): every Area carries `Conv_PE` + `Conv_PI`.

### Emission gates in `fortna_autogen.py`

```
Conv_PE  ← emitted iff rungs_pe contains PE_Logic(...) after per-conveyor clone
Conv_PI  ← emitted iff Slow_ConvPI20 in library AND pi_convs AND safety zone ∈ _pi_writer_zones
```

Empty shells are intentionally omitted (no NOP Conv_PE / Conv_PI).

### ROOT CAUSE — Conv_PE

**FIRST POINT OF FAILURE:** per-conveyor PE role binding → `clone_template_for_conveyor` → `pe_tags_needed` for non-Full eyes.

Evidence on gold Pick:

- **Full_PE path works:** 8× `Full_PE(...)` in `Conv_Full` (EZPEP1_F, EZPE60_F, …).
- **PE_Logic path empty:** `PE_Logic(` call count = **0** → `rungs_pe` empty → **no Conv_PE routine / no JSR**.
- Presence/jam/HF PE **tags exist** (IO_MAP writers + PE_Logic AOI backing structs), e.g. `PE72_P`, `PE68_P`, `EZPE47_P`, `PE105B_J`, `EZPE45_HF` (37 PE_UDT tags total).
- `Conv_Jam` uses **all `NO_PE`** — jam/product roles never reached Slow_Jam / PE_Logic.
- Upstream rule ORI-079: when a sensor→conveyor topology map is present, unbound sensors **must not** fall back to PE-digit→P-tag invention. Fullline apparently bound `_F` eyes; Jamcheck/product topology did not bind the `_P`/`_J`/`_HF` eyes → tags created from I/O map, but no conveyor InOut for `PE_Logic(aoi, pe, conv, ...)`.

**Generic emission decision:** **BLOCKED.**

Implementing Conv_PE for those orphan PE tags would require inventing conveyor ownership (name similarity `PE72_P`→`P72` is evidence only — Constitution §7). No empty shells. Fix belongs in topology/sensor→conveyor binding (Fullline/Jamcheck/product map completeness), then existing emit path will create PE_Logic + Conv_PE automatically.

### ROOT CAUSE — Conv_PI

**FIRST POINT OF FAILURE:** `_pi_writer_zones` membership check (PD-0003).

Evidence:

- Gold Pick: `Slow_ConvPI20` count = **0**; no `Conv_PI` routine.
- Emit requires a safety zone that is a proven PI writer (not invented `{Area}_Safe`).
- Without a writer-backed zone, code sets `REVIEW_REQUIRED_NO_PI_WRITER` and omits the pack.

**Generic emission decision:** **BLOCKED (correct omission).**

Do not invent `_Safe` / fake PI writers. When Safety PI writers exist in the active model, existing `_slow_conv_pi_rungs` path emits Conv_PI.

### Punch-list (discovered, not fixed)

- Gold Pick `Conv_Fast` is **29× NOP** (Fast_Conv not emitted) — separate Transportation defect, out of Phase 1 scope.
- Presence PE tags mapped in IO_MAP but unbound to conveyors — topology binding gap.

---

## PHASE 2 — Control_Station

### Gold Pick defect

| Routine | Behavior |
|---|---|
| `Area_Logic` | HMI Start/Reset/Silence → Area.*; Run seal-in (ORI-097) |
| `Control_Station` | **Exact duplicate** of Area_Logic rungs → **dual writers** on Area.Start/Reset/Silence/Run |
| `Area_PI` | Thin 3-rung mirror (Run/Start/Stop only) |
| `Slow_ControlStation(` | **0 calls**; no CS_UDT tags; no Slow_ControlStation instances |

### Finished / library oracle

PLC4 `ModuleA_Area_Slow` / library `Main_Area_Slow`:

1. `Control_Station`: `Slow_ControlStation(Area_CS1, CS_UDT_slots…, 10000);`
2. `Area_PI`: aggregates `CS*.O_Start/Stop/Rst/AntiTiedown` + JamRst/Mtr_FltRst + Area.Run + Conv_PI fault packs + ES Silenced_Tripped
3. `Area_Logic`: `Slow_Area(...)` on finished PLC4 (library also has Slow_Area)

### ROOT CAUSE

**FIRST POINT OF FAILURE:** Control_Station body generation when no proven CS_UDT.

Historical gold path re-emitted Area_HMI writers into Control_Station (dual writer). Demo-branch code already withheld Slow_ControlStation without CS and used a REVIEW stub — but **Area_PI was still built before the CS decision** as the thin 3-rung HMI mirror, so even when Slow_ControlStation *is* emitted, Area_PI did not consume AOI outputs.

### Repair implemented (demo branch only)

In `tools/scripts/fortna_autogen.py` (from START SHA `a935a22`):

- **Single-writer fix:** when no proven CS_UDT, Control_Station no longer duplicates Area_Logic HMI→Area.* OTEs (gold Pick dual-writer defect). Emits REVIEW stub + proven RUN MCR/horn writers only.
- Rebuild **Area_PI after** Control_Station decision.
- **If** proven CS_UDT + library has `Slow_ControlStation`: Area_PI follows library contract from `{Area}_CS1.O_*` outputs (Start/Stop/Rst/AntiTiedown/JamRst/Mtr_FltRst) + Area.Run + optional Conv_PI fault packs.
- **Else:** Area_PI mirrors Area_Logic/HMI only (Start/Stop/Rst/JamRst/Mtr_FltRst/Run) — Area_Logic remains sole Area.* writer.
- Anti-tiedown bits emitted only when Slow_ControlStation AOI is present (no invented CS).
- `_control_station_status` reports `REVIEW_REQUIRED` / `Area_HMI_SINGLE_WRITER` when CS withheld (truthful — not fake FUNCTIONAL).

### Implementation status

| Item | Status |
|---|---|
| Dual-writer Control_Station (gold Pick defect) | **FIXED** — REVIEW stub, no Area.* OTE |
| Area_PI ← Slow_ControlStation outputs | **IMPLEMENTED** |
| Emit Slow_ControlStation without CS_UDT evidence | **NOT done** (correct — would invent InOuts) |
| Slow_Area in Area_Logic | **NOT done** this mission (punch-list; needs System tag + AOI wiring evidence) |

---

## FILES CHANGED

| File | Change |
|---|---|
| `tools/scripts/fortna_autogen.py` | Area_PI rebuilt after CS decision; library Slow_ControlStation aggregation when proven |
| `exports/diagnostics/demo_greensboro_contract_guard.json` | Phase 0 contract guard |
| `exports/diagnostics/demo_phase0_2_report.md` | This report |

## TESTS RUN

- `ast.parse` on `fortna_autogen.py` — syntax OK
- No full site regen in this phase (diagnosis + targeted emit repair only)

## FORBIDDEN SHORTCUT CHECK

**PASS**

- Did not import CommDiag_UDT from PLC4 into library/emit
- Did not invent PE→conveyor ownership for Conv_PE
- Did not invent `{Area}_Safe` / PI writers for Conv_PI
- Did not invent CS_UDT / Slow_ControlStation InOuts
- Did not lower auditor thresholds

## KNOWN REMAINING FAILURES

1. Conv_PE still absent until sensor→conveyor topology binds non-Full PEs (upstream).
2. Conv_PI still absent until Safety PI-writer zones exist for the Area (upstream / PD-0003).
3. Gold Pick Conv_Fast NOP shell (out of scope).
4. Slow_Area AOI not yet used in Area_Logic on demo emit path.
5. Sites without proven CS_UDT still get Control_Station REVIEW stub (honest — not fake FUNCTIONAL Slow_ControlStation).

## NEW PUNCH-LIST ITEMS DISCOVERED

1. PE topology binding gap: IO-mapped presence/jam PEs without conveyor ownership → no PE_Logic/Conv_PE.
2. Pick Conv_Fast all-NOP (Fast_Conv not emitted) — Transportation completeness.
3. Optional: adopt Slow_Area AOI for Area_Logic when System tag + library AOI available.
4. PLC5 EngMgmt member drift vs library (oracle note only).

## WARDEN READY

**NO**

WHY: Phase 0–2 is diagnosis + partial Control_Station/Area_PI emit repair on the demo branch. Conv_PE/Conv_PI remain correctly withheld without model evidence; no target-site regen/cross-site regression package was produced for Warden acceptance of a ship-sorter demo candidate.
