# Safety lifecycle root cause (b8b5d1c field failure)

## First failing boundary

**UI model assembly (`buildClientModel` → `classifyZoneProvenance`)**

Transport/Area-seeded empty shells such as `ORINDYAC6_ESZone1` (conveyors present, **members=[]**) were classified **`AUTO_DEFAULT`** because:

```
/_ESZone1$/ && !members && !engineer
```

Then `isMeaningfulZone` dropped `AUTO_DEFAULT` → **zone disappeared from Safety UI** before Assign.

Engineer could only see Default/Unassigned → could not assign → Apply had no operational zone with members → Autogen ES emitted NOP-only `Main_Routine`.

## Secondary UI contradiction

Unassigned devices were stamped `safetyZoneRef = "Default Safety"` while `status = UNASSIGNED`, producing **Assigned=127 and Unassigned=127** style contradictions.

## Fix

1. Empty Transport-seeded ES shells → `LEGACY_CANONICAL` (stay visible for Assign).
2. Do not stamp unassigned devices onto Default as if assigned.
3. E2E test: assign → Apply payload → ES emit Safe_Logic/Safe_PI.

## Not the ES generator

ES correctly refused to invent membership. Fixing membership persistence/UI reachability is the root cause — not manufacturing members in the compiler.
