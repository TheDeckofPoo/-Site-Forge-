# Transport + 2:1 merge inventory (equipment pattern)

Gold reference: `ORielly Green\1 PLC2\ORLY_Greensboro_NC_PLC2s.L5X` (and PLC4S / PLC5S merges).

## Role by controller type

| Role | Equipment |
|------|-----------|
| Transport PLC | Lots of **transport** + **2:1 merges** |
| Sawtooth PLC | **Sawtooth_Merge** collector track (+ some transport merges) |
| Sorter PLC | **Sorter_Track** + TRK_* / Enc_* (+ some transport merges) |

## PLC2s merge call sites (4)

Hold mode = **runhold** (BOOL tags):

| Merge | Lanes | Holds |
|-------|-------|-------|
| P316_Merge | P136_P1 / P312 → P136_P2 | `P316_MainLane_Conv_RunHold`, `P316_InductLane_Conv_RunHold` |
| P406_Merge | P136_P2 / P402 → P406 | same pattern |
| P324_Merge | P150_P1 / P320 → P150_P2 | same pattern |
| P400_Merge | P150_P2 / P242 → P400 | same pattern |

## L2 Merge ST presets (equipment standard)

Emitted per merge in `{Area}_L2` / `Merge` ST:

```
{Merge}.I_MergeCX_Enable := 0;
{Merge}.I_InductLane_AddNotlReadyBit := 0;
{Merge}.I_MainLane_AddNotReadyBit := 0;
{Merge}.I_Merge_FltClearTime := 10000;
{TimeA|B}.HMI.ClearTime := 8000;
{TimeA|B}.HMI.NoCartonsTime := 8000;
{TimeA|B}.HMI.ReleaseTime := 10000;
{TimeA|B}.HMI.ReleaseTimeFull := 15000;
```

## PLC5 hold variant

Sorter-area merges often pass `{Conv}.PI.Stop_Next` instead of BOOL RunHold (`hold_mode=stop_next`).

## Site Forge

- Transport Fast/Slow: existing
- Merge_2to1 + Conv_Merge: existing
- Area_L2 Merge ST presets + hold_mode: added from *S harvest
- Slow_Flt Enc on transport gold = **NO_Enc** (leave as-is)
