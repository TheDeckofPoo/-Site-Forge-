# PARTIAL BUILD CONTRACT

**Product requirement** — not a temporary test-mode exception.

## Vocabulary

| State | Meaning |
|-------|---------|
| **FOUND** | Discovered from RUN / decoder |
| **CONFIGURED** | Engineer has assigned metadata (Area, zone, alias, …) |
| **INCLUDED** | Engineer chose this object for the current PLC build (Apply / include=true) |
| **GENERATED** | Object actually emitted into the L5X |

## Non-equivalences (mandatory)

```
UNASSIGNED ≠ ERROR
UNASSIGNED ≠ ACTIVE
UNASSIGNED ≠ INCLUDED
UNASSIGNED ≠ GENERATED
UNASSIGNED ≠ SAFE

FOUND ≠ GENERATED
```

## Pipeline

```
RUN → FOUND OBJECTS
        ↓
Engineer configuration / assignment
        ↓
INCLUDED OBJECTS   (effective model)
        ↓
Autogen
        ↓
GENERATED OBJECTS
```

## Compile Hub

| Status | Blocks Build PLC? |
|--------|-------------------|
| READY | No |
| REVIEW REQUIRED | **No** |
| NOT DETECTED | No |
| ERROR (INCLUDED / mandatory) | **Yes** |

Example allowed hub:

```
Transportation     READY          (small Area Applied)
Safety             REVIEW REQUIRED (38 devices unassigned)
Saw/Merge          NOT DETECTED / REVIEW (found, not included)
Sorter             NOT DETECTED
Hardware/I/O       READY
System             READY

BUILD PLC: ALLOWED
```

## Safety

- Do not guess membership from CP2/CP3/T_2 names.
- Unassigned devices stay conspicuous in Safety Build.
- Fail-safe ES shell allowed; `COMMISSIONING READY = NO`.
- Never emit permissive `ES_OK = TRUE` because a device was omitted.

## Permanent fixture

```text
python tools/scripts/test_partial_build_acceptance.py
```

Evidence: `exports/stabilization/partial_build_acceptance.json`
