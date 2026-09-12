# Task / Program Architecture (Generic)

**Branch:** `feature/cp5-gap-closure`  
**Rule:** Model **classes** of tasks and programs. Do **not** hardcode finished PLC5 (or any site) period names, rates, or priorities as generation truth.

---

## Program classes

Logical classes the compiler and SiteModel reason about:

| Class | Role | Typical program shape |
|-------|------|------------------------|
| **safety** | E-stop / safety enable paths | Safety AOIs / zone programs when library path exists |
| **high-speed tracking** | Pulse / track / IO scan that must beat carton motion | Dedicated track-class programs (e.g. IO map; sorter track when supported) |
| **WCS** | Warehouse / host messaging | Optional WCS interface program — generation usually NOT_SUPPORTED |
| **fast equipment** | Per-area fast conveyor / motion logic | `Area_*_Fast` |
| **slow equipment** | Per-area jam / fault / slow equipment logic | `Area_*_Slow` |
| **L1 / L2 / L3 config** | Event-driven or infrequent config / init | `Area_*_L1`, `Area_*_L2`; L3 only when a generic pack exists |
| **system** | NTP, device comms, site System_UDT | `Sys` / System |
| **HMI** | Diagnostics / faceplate support | Often CONFIGURATION_REQUIRED; not assumed generatable |

Classes are portable across controllers. Concrete Studio task **names** and **rates** are binding only when supplied by an approved source below — never by copying one finished site’s schedule.

---

## Sources of rates / priorities

Allowed sources (highest practical authority first):

1. **Training / FPC docs** — documented class intent (fast vs slow vs config).
2. **Library metadata** — program-export or AOI pack guidance shipped with generic libraries.
3. **Engineer config** — explicit site overrides in workbook / build UI.
4. **Platform standards** — Fortna/Site Forge documented defaults for a class (must be written down, not implied from one gold L5X).

**Not allowed as generation rules:** answer-sheet constants harvested from finished Greensboro PLC2/4/5 task blocks (exact `P10_Fast_50ms` / `P11_Slow_200ms` / … values as if they were universal law). Those finished schedules remain **post-generation oracles** only.

When emitting tasks, Autogen may use library-aligned defaults for a class; any site-specific period map belongs in engineer config or future platform-standard docs — not inline Greensboro literals treated as discovery.

---

## Current Autogen emit (when supported)

For a configured Area name `Area_*`, Autogen currently emits:

| Program | Class |
|---------|--------|
| `Area_*_Fast` | fast equipment |
| `Area_*_Slow` | slow equipment |
| `Area_*_L1` | L1 config |
| `Area_*_L2` | L2 config |
| `Sys` | system (when `include_sys`) |
| `IO_MAP` | high-speed tracking / IO (when `include_io_map` and RUN banks / map support it) |

Optional packs (WCS, ShippingSorter L3, Sorter_Track, …) stay off unless a **generic** library path and engineer request exist. Unsupported classes stay `CONFIGURATION_REQUIRED` or `NOT_SUPPORTED` in the capability matrix — never marked `GENERATED` without L5X structure.

---

## Related

- `docs/DISCOVERY_TO_COMPILER_CONTRACT.md` — capability lifecycle / GENERATED rule
- `docs/SOURCE_OF_TRUTH_POLICY.md` — finished PLC is oracle only
- `tools/scripts/fortna_autogen.py` — current emit implementation
