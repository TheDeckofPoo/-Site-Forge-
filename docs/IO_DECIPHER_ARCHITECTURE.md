# I/O Decipher Architecture

Site Forge I/O resolution is a **generic Fortna pipeline**, not a CP6/1794 hardcode.

```
RUN evidence
    ↓
Hardware Topology IR          (eipcfg adapters/modules, Configio rows)
    ↓
Hardware Family Profile       (1794 FLEX | 1734 POINT | ETHERNET_DRIVE | UNKNOWN)
    ↓
Physical Endpoint             (adapter, slot, bank/channel, Data[n].bit)
    ↓
Logical Owner                 (Conveyor word.bit / ownership profiles)
    ↓
IO_MAP                        (XIC/OTE binding)
```

## Separated concerns

| Stage | Responsibility | CP6/1794 notes |
|-------|----------------|----------------|
| Topology discovery | Parse eipcfg + Configio | Shared |
| Family/catalog ID | `fortna_hardware_family.detect_family_from_catalog` | 1794 vs 1734 vs drive |
| Channel/bank evidence | Configio Desc forms + Bank column | PANEL_CATALOG, PANEL_NODE, CATALOG_WORD_BANK |
| Physical-image translation | Family profile `data_index_for_module` | **1794:** Data[slot−1]; **1734:** must not reuse 1794 shift |
| Logical owner | `CONVEYOR_WORD_BIT` + profile join | Shared |
| Confidence | PROVEN / CONFLICT / UNKNOWN/REVIEW | Never silent |

## Confidence classes

- **PROVEN** — Configio bank ↔ EIPModules bank (or panel form) + Conveyor word.bit resolve
- **CONFLICT** — multiple owners on one endpoint
- **UNKNOWN/REVIEW** — unknown family translation, or unresolved owner

**Unknown family must not silently reuse 1794 Flex Data[slot−1] rules.**

## Profiles (ownership topology)

See `docs/evidence/IO_OWNERSHIP_PROFILES.md`.

## Preparation for 1734 POINT

Next blind test must implement a **POINT family profile** for channel/image translation.
Do not invent 1734 addressing until that virgin RUN evidence is available.
CP6 1794 mapping must remain bit-identical under this refactor.
