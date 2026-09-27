# I/O Handbook (Generic Verified Lessons)

Generic Site Forge I/O knowledge. **No site-specific endpoint answers.**

## Purpose

Give Relay (and future agents) a durable, controller-agnostic baseline for
interpreting Fortna RUN physical I/O evidence.

## Core distinctions

| Concept | Meaning |
|---------|---------|
| Physical endpoint | Panel / adapter / module / slot / direction / channel tuple |
| Rendered Logix address | Studio-facing `Data[]` tag string |
| Device | Canonical engineered Safety / I/O device identity |
| Signal | Named claim / AUX / feedback / command row |
| Signal role | PRIMARY / AUX / FEEDBACK / COMMAND / etc. |

These conclusions are separate. Strong evidence for one does not invent the other.

## Evidence hierarchy (summary)

1. Current-machine RUN tables + EIP topology for the **target panel/adapter**
2. Engineer-assigned physical overrides (explicit)
3. Corroborating semantics (names, AUX/coil consistency) — never sole authority
4. Finished L5X — validation only

## Forbidden shortcuts

- Cross-panel bank/number coincidence → physical endpoint
- Whole-word direction assumed without half/module/channel proof
- Memory / nonphysical Configio rows → physical endpoint
- Naming alone → physical endpoint
- Finished PLC → discovery parent

## Related files

- `PANEL_LOCAL_IO_RULES.md`
- `ROCKWELL_ADDRESSING.md`
- `OWNERSHIP_AND_PROVENANCE.md`
- `SIGNAL_ROLES.md`
