# Sawtooth merge — data sources

## Logix gold (Greensboro PLC4)
- File: `C:\dev\Autogen Excel\2 PLC4\ORLY_Greensboro_NC_PLC4v4.L5X`
- Task: `P02_Track_5ms` schedules program **`Sawtooth_Merge`**
- Collector example: **P414** (+ P418), encoder **P414_Enc**, HMI `P414_SawMerge_HMI`
- Lane conveyors in IO map include **P412, P120, P218** (and buffers)
- Site Forge pack: `tools/libraries/programs/Sawtooth_Merge_Program.L5X`

## FortnaPlus RUN tar.gz (QNX / C-side)
Yes — tables under `RUN/FORTNA/`:
- `SawMerge.asc` — MotorIO, ReserveIN, EOW_*, slice timing
- `SawLane.asc` / `HSSawLane.asc` — LanePE, Slow/Fast, gap timers, SawMerge link
- `HSSawParm.asc` — reservation spacing / priority
- Menu modules: `SawMerge`, `HSSawMerge` (compiled C on the QNX side; not source in this repo)

Site Forge **Sawtooth Merge** tab designs Logix pack inputs; Asc import for live site params is a later step.

## CP4 fidelity generation

See [`docs/CP4_SAWTOOTH_FIDELITY.md`](CP4_SAWTOOTH_FIDELITY.md) and `exports/cp4-sawtooth-pass/`.
Generation inputs are CP4 RUN + frozen discovery + generic `Sawtooth_Merge_Program.L5X` only — finished PLC4 is never read.
