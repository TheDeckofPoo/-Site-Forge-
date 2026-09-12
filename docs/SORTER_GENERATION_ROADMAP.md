# Sorter Generation Roadmap

**Status:** Knowledge-layer roadmap  
**Policy:** Tracking / WCS / Sorter_Track PLC generation is **NOT_SUPPORTED** until a complete generic library path exists. Greensboro gold packs do not qualify.

Companion: `docs/SORTER_CONTROL_MODEL.md`, `docs/SORTER_COMPILER_MODEL.md`, `exports/sorter-research/generation_support_matrix.json`.

---

## Maturity legend

| State | Meaning |
|-------|---------|
| **DISCOVERED** | RUN tables / rows inventoriable with provenance |
| **UNDERSTOOD** | Doc semantics + field meanings captured (training docs) |
| **MODELED** | Generic `SorterModel` / SiteModel fields defined |
| **GENERATABLE** | Complete generic library path can emit L5X from RUN+overrides |
| **VALIDATED** | Emitted L5X checked against non-input oracles / tests |

---

## Capability matrix

| Capability | DISCOVERED | UNDERSTOOD | MODELED | GENERATABLE | VALIDATED | Notes |
|------------|:----------:|:----------:|:-------:|:-----------:|:---------:|-------|
| Sorter entity inventory (`Sorters.asc`) | ✓ | ✓ | ✓ | — | — | Discovery stub in SiteModel |
| Encoder parameter inventory | ✓ | ✓ | ✓ | — | — | Shared with sawtooth path |
| Zone / lane assignment (`SrtZoneLane`) | ✓ | ✓ | ✓ | — | — | HostZone↔Lane relationships |
| Scan boss topology (`SrtScanBoss`) | ✓ | ✓ | ✓ | — | — | Scan zone linkage |
| App sorter config (`SrtAppControl`) | ✓ | ✓ | ✓ | — | — | ErrConfig / msg tables / motor |
| Lane-not-avail / bad-gap / round-robin | ✓ | ✓ | partial | — | — | Tables inventoriable |
| SrtTrack runtime slots | ✓ | ✓ | ✓ | — | — | Runtime ≠ divert map |
| XfrTrack / MsgTrack | ✓ | ✓ | ✓ | — | — | Often empty |
| WCS event / MsgWCS topic map | ✓ | ✓ | ✓ | — | — | Inventory only |
| Static vs runtime table classification | ✓ | ✓ | ✓ | n/a | ✓ | Knowledge-layer tests |
| SorterModel schema | ✓ | ✓ | ✓ | — | — | `SORTER_COMPILER_MODEL.md` |
| Divert IO + lane PLC map | partial | ✓ | — | — | — | Gap: engineer-required |
| Tracking conveyor chain generation | — | partial | — | — | — | Not derivable from tracks alone |
| Sorter_Track PLC generation | — | — | — | **NO** | — | Gold pack ≠ generic path |
| WCS interface PLC generation | — | — | — | **NO** | — | Gold pack ≠ generic path |
| Shipping sorter area L3 generation | — | — | — | **NO** | — | Site wiring engineer-required |
| TRK_Divert_Wave AOI reuse | ✓ | partial | — | CONFIG | — | Divert count / IO mapping needed |
| Encoder routine stub reuse | ✓ | partial | — | CONFIG | — | Site tags required |

---

## Near-term knowledge-layer exits (this branch)

1. Discover sorter entities + static/runtime table classes on import  
2. Score activity with `sorter_static` / `sorter_runtime` evidence  
3. Keep `generation_state=NOT_SUPPORTED` on sorter / tracking / WCS objects  
4. Document control model + roadmap; do not fake generation  

## Future generation gates (not claimed here)

A capability may move to **GENERATABLE** only when:

1. Generic library AOI/program exists (not site-fixed gold rename)  
2. RUN→model mapping covers required IO without finished PLC  
3. Engineer override surface exists for remaining gaps  
4. Validation oracle is separate from generation inputs  

---

## Explicit refusals

- No finished PLC4 / PLC5 as generation input  
- No Greensboro hardcoding in discovery or compilers  
- No claiming VALIDATED generation from discovery inventory alone  
