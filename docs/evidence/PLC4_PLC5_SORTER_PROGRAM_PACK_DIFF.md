# PLC4 vs PLC5 Sorter_Track Program Pack Diff (Gates B / C)

**Branch:** `feature/plc2-transport-fidelity`  
**Scope:** Archaeology / docs / contracts only — **no compiler implementation**.  
**Machine-readable twin:** [`config/program_packs/plc4_plc5_sorter_pack_diff.json`](../../config/program_packs/plc4_plc5_sorter_pack_diff.json)

Finished L5X files are **validation oracles only** (never discovery). Site names below are oracle examples.

---

## Oracles

| Controller | Path | SHA256 (prefix) |
|------------|------|-----------------|
| PLC5 | `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC5_RTfinished.L5X` | `27B55EED…` |
| PLC4 | `C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_Greensboro_NC_PLC4 finished.L5X` | `370CD3F1…` |
| Gold pack (validation asset) | `tools/libraries/programs/Sorter_Track_Program.L5X` | — |

Also referenced: [`SORTER_TRACK_PROGRAM_PACK.md`](SORTER_TRACK_PROGRAM_PACK.md), [`config/program_packs/sorter_track_contract.json`](../../config/program_packs/sorter_track_contract.json).

---

## Tag naming normalization (CP4 / CP5)

Structural comparison uses digit-family normalization:

| Oracle family | Normalized pattern |
|---------------|--------------------|
| `P4xx_*` / `P5xx_*` | `P{sorter}_*` |
| `ENC4xx` / `ENC5xx` | `ENC{id}` |
| `Token_SCN4xx` / `Token_SCN5xx` | `Token_SCN{scan}` |
| `P424_Divert1` / `P506_Divert1` | `P{sorter}_Divert{n}` |

After normalization, **datatype families and routine roles match**; instance **counts** differ.

---

## Task / scheduling

| Item | PLC4 | PLC5 | Class |
|------|------|------|-------|
| Tracking task | `P02_Track_5ms` PERIODIC Rate=5 Priority=2 | same | **PACK_STANDARD** (`task_class=tracking`) |
| Rate / priority | 5 ms / 2 | 5 ms / 2 | **PARAMETERIZED** (oracle evidence — not a universal hardcoded constant) |
| P02 scheduled programs | `Sawtooth_Merge`, `Sorter_Track` | `Sorter_Track` only | Sawtooth co-schedule = **OPTIONAL_STANDARD** |
| WCS task | `P03_WCS_10ms` → `WCS_Interface_TCP_IP` | same | **OPTIONAL_STANDARD** (separate pack) |

**Gate C:** Sawtooth on P02 is **not** explained by sorter/divert multiplicity — it is an independent pack selection on the PLC4 oracle.

---

## Program

| Item | Value | Class |
|------|-------|-------|
| Program name | `Sorter_Track` | **PACK_STANDARD** |
| Main routine | `Main` (not `Main_Routine`) | **PACK_STANDARD** |

Related (outside Sorter_Track body): Area Fast/Slow/L* (equipment + StartStop/Jam), `WCS_Interface_TCP_IP`, PLC4 `Sawtooth_Merge`. LogicalSignalModel may feed encoder enables — not Sorter_Track routine names.

---

## Routine lists

### PLC4 Sorter_Track (15) — JSR order

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
14. Response_Time  

### PLC5 Sorter_Track (17) — JSR order

Same core **plus**:

15. **Gridlock_Prevention** (before Response_Time)  
16. Response_Time  
17. **RT_Virtual_Enc** (ST)

### Delta

| Routine | PLC4 | PLC5 | Gold pack | Class |
|---------|:----:|:----:|:---------:|-------|
| Core 14 (Main leaves excl. optional) | yes | yes | yes | **PACK_STANDARD** |
| Gridlock_Prevention | no | yes | yes | **OPTIONAL_STANDARD** (content often **CUSTOM_ENGINEER**) |
| RT_Virtual_Enc (ST) | no | yes | **no** | **OPTIONAL_STANDARD** |

---

## Rung-count deltas vs multiplicity (Gate C)

| Routine | PLC4 rungs | PLC5 rungs | Multiplicity explains? | Candidate rule |
|---------|----------:|----------:|:----------------------:|----------------|
| Main | 15 | 17 | yes (optional JSR leaves) | JSR core + enabled optional leaves |
| Encoder | 1 | 10 | **yes** | FOR EACH sorter encoder → `Enc_RIOCard` (+ optional virtual) |
| Track_Pointer | 1 | 5 | **yes** | FOR EACH tracking path → `TRK_Pointer` |
| Track_Induct_Package | 2 | 2 | yes (both 1 induct) | FOR EACH induct/decision point |
| Track_Manual_Destination | 2 | 2 | yes | per manual-dest group |
| Scanner | 8 | 8 | yes (both 1 SCN group) | FOR EACH scan/decision group |
| Track_Package | 2 | 14 | **yes** | FOR EACH tracking PE/path (+ transfers) |
| Track_Lost_Package | 1 | 5 | **yes** | FOR EACH exit lost-detect path |
| Divert_Lane_Status | 7 | 56 | **yes** | FOR EACH divert → Full PE map |
| Track_Divert_Package | 3 | 48 | **yes** | FOR EACH divert → `TRK_Divert` cluster |
| Wave_Divert | 1 | 16 | **yes** | FOR EACH divert → wave AOI |
| Divert_Rate_Limit | 3 | 18 | **yes** | FOR EACH divert → rate limit |
| Track_Divert_Confirm | 1 | 1 | partial | confirm often via divert UDT members → WCS |
| Track_Offset_Find | 5 | 24 | **yes** (shell) | FOR EACH divert/offset PE pair — **values NOT_SUPPORTED to synthesize** |
| Response_Time | 4 | 4 | yes | metrics block |
| Gridlock_Prevention | — | 9 | **no** | optional leaf / engineer policy |
| RT_Virtual_Enc | — | ST 34 lines | **no** | optional leaf |

**Never hardcode 32** (or 16). PLC5 RUN `SrtZoneLane` can show **32** rows while finished oracle has **16** `Track_Divert_UDT` instances — emit only **model-approved divert instances**, not raw zone-lane row count.

---

## Instance multiplicity (oracle)

| Family | PLC4 | PLC5 |
|--------|-----:|-----:|
| `Track_Divert_UDT` / `_AOI` | **1** (`P424_Divert1`) | **16** (P506×6, P508×6, P509×1, P510×3) |
| Active encoders in Encoder routine | **1** | **5** |
| `Track_Conv_UDT` | 1 | 5 |
| `Track_Induct_UDT` | 1 | 1 |
| `Token_Sorter` / `Track_Group_UDT` | SCN424 | SCN504 |

Classification:

- Instance tags / expanded rungs → **MODEL_GENERATED**  
- Scale, offsets, wave, rate numbers → **PARAMETERIZED**  
- Divert trigger from RUN alone → **UNKNOWN** / emit **NOT_SUPPORTED**

---

## AOI / UDT

| Level | Observation | Class |
|-------|-------------|-------|
| AOI | Sealed `Enc_*` / `TRK_*` / divert families called from routines; open defs not in finished export | **PACK_STANDARD** (library dependency) |
| UDT | Shared: `Enc_UDT`, `Track_*`, `Token_Sorter`, `Manual_Destination`, divert CFG/PI/O | **PACK_STANDARD** |
| Partial open libs | `Enc_Routine_ST.L5X`, `TRK_Divert_WaveFunction_AOI.L5X` | incomplete vs full sealed set |

Compiler must **consume** approved sealed AOI binaries — not invent AOI bodies, not clone gold program instances.

---

## External domains (scanner / WCS / StartStop / Jam / logical)

| Domain | Inside Sorter_Track? | Class | Notes |
|--------|:--------------------:|-------|-------|
| Scanner | yes (`Scanner`) | PACK_STANDARD | decision-request handshake tags |
| WCS | no (sibling program) | OPTIONAL_STANDARD | Phase 1: optional pack; sorter emits handshake surface only when enabled |
| StartStop | no | PARAMETERIZED | Area Slow / zones; may gate enables |
| Jam | no | PARAMETERIZED | Area Slow; encoder EnableBit may ref VFD/jam via LogicalSignalModel |
| Logical signals | cross-cutting model | PARAMETERIZED | not Sorter_Track routine names |

---

## Component classification summary

Allowed classes: `PACK_STANDARD` | `MODEL_GENERATED` | `PARAMETERIZED` | `OPTIONAL_STANDARD` | `CUSTOM_ENGINEER` | `UNKNOWN`

| Component | Level | Class |
|-----------|-------|-------|
| Tracking task | TASK | PACK_STANDARD (rate PARAMETERIZED) |
| Sorter_Track | PROGRAM | PACK_STANDARD |
| Core routines | ROUTINE | PACK_STANDARD |
| Gridlock / RT_Virtual_Enc | ROUTINE | OPTIONAL_STANDARD |
| Per encoder/divert/path bodies | tags / rungs | MODEL_GENERATED |
| Offsets / wave / rate / FPM | tags | PARAMETERIZED |
| Gridlock policy content | ROUTINE body | CUSTOM_ENGINEER |
| Divert trigger synthesis | tags | UNKNOWN |
| Sealed AOI + track UDTs | AOI / UDT | PACK_STANDARD |
| WCS / Sawtooth co-pack | PROGRAM | OPTIONAL_STANDARD |

---

## Gate C verdict

Almost all **rung-count** differences between PLC4 and PLC5 Sorter_Track are explained by **SorterModel multiplicity** (encoders, tracking paths, divert instances).  

**Not** explained by multiplicity:

1. Presence of `Gridlock_Prevention` / `RT_Virtual_Enc`  
2. PLC4 co-scheduling `Sawtooth_Merge` on P02  
3. Area program set (ShippingSorter vs Sawtooth/CityCounter)  
4. Commissioning numeric values  

Candidate expansion rules must always be **FOR EACH model instance** — never site literals like 32 diverts.
