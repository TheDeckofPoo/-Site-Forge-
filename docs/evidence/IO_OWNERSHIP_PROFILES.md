# I/O Ownership Profiles

Site Forge must not assume one FortnaPlus representation for I/O ownership.

```
Fortna Site A ── profile(s) ─┐
Fortna Site B ── profile(s) ─┼→ PhysicalEndpoint + evidence → HardwareIOModel
Fortna Site C ── profile(s) ─┤
Engineer Name ─ ENGINEER_ASSIGNED ┘
```

## Proven profiles

| Profile ID | Topology Desc form | Owner source | Sites (evidence) |
|------------|-------------------|--------------|------------------|
| `CONFIGIO_PANEL_CATALOG` | `CP2-1794-IA16-3` | Conveyor word.bit | PLC2, PLC4 |
| `CONFIGIO_PANEL_NODE` | `CP5-NODE53-1A` | Conveyor word.bit | PLC5 |
| `CONFIGIO_CATALOG_WORD_BANK` | `1794-IA16-600-4` | Conveyor word.bit + Configio.Bank↔EIPModules banks | ORINDYAC6 virgin RUN |
| `CONVEYOR_WORD_BIT` | (owner table) | `IO_Address_Word` / `IO_Address_Bit` | all above |
| `ENGINEER_ASSIGNED` | Hardware Name override | canonical overrides | all |

## Owner states

| State | Meaning |
|-------|---------|
| `ASSIGNED` | Automatic RUN owner bound |
| `ENGINEER_ASSIGNED` | Hardware Name override (persists) |
| `PROVEN_SPARE` | Positive spare token evidence |
| `UNUSED_MAPPED` | Mapped module bit, no owner, **not** proven spare |
| `UNRESOLVED_OWNER` | Conflict / failed named bind / non-topology claim |
| `UNKNOWN` | No topology |

## Virgin RUN root cause (ORINDYAC6)

Configio Desc `1794-IA16-600-4` was unparsed (`parse_ok=0`) → empty word map → Conveyor owners could not join.  
Fix: parse catalog-word-bank + assign by Configio.Bank ↔ EIPModules InputBank/OutputBank.

Finished PLC was **not** inspected.
