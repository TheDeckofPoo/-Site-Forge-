# PLC2 Foundation Reset

**Branch:** `feature/plc2-foundation-reset`  
**Base:** `feature/io-regression-lock` @ `ede3f5d`  
**Oracle (validation only):** `workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X`  
**Freeze:** PLC4 / PLC5 / Sawtooth / Sorter / WCS — no expansion this pass.

## What changed

1. **ControllerScopeModel** (`fortna_controller_scope.py`)
   - LOCAL / EXTERNAL_REFERENCE / OUT_OF_SCOPE / UNRESOLVED
   - Seeded from RUN I/O ownership (`belongs_to_controller` + PE/motor/VFD/Mtrchain) — **not** P-number heuristics
   - Proves `P400` can be LOCAL on PLC2; `P414` stays NOT_CP2 (ORNCCP4)

2. **Transportation filter**
   - Primary nodes = LOCAL only
   - One-hop EXTERNAL_REFERENCE boundaries only (e.g. `→ External P226`)
   - **No** full remote conveyor networks (P600 site clutter removed)

3. **IO_MAP placeholders**
   - Extended existing CP_I/CP_O emit with unused-bit `NO_PointPlaceholder` fill (finished Fortna pattern)
   - Generator core preserved — not rewritten

4. **Foundation candidate**
   - `exports/plc2-foundation/ORNCCP2_foundation_candidate.L5X`
   - Copied to `exports/studio-validation/ORNCCP2_foundation_candidate.L5X`

## Acceptance gate

### CONTROLLER SCOPE
| Metric | Value |
|--------|------:|
| total Conveyor rows in RUN | **284** |
| local PLC2 | **59** |
| external references | **4** |
| out of scope | **147** |
| unresolved | **74** |

### FINISHED VALIDATION (oracle only)
| Metric | Value |
|--------|------:|
| correctly local devices | **47** |
| missing local devices | **11** (mostly lettered finished AOIs `P130A…` / `P145A…` + `P2000`) |
| incorrectly local devices | **10** (RUN-local tags not found as `P###_Conv` in finished naming — investigate, do not copy finished) |

### IO TREE
| Metric | Value |
|--------|------:|
| adapters generated | **7** |
| child modules generated | **32** |
| catalog overlap vs finished | `1756-L83E`, `1756-EN2T`, `1794-AENT`, `1794-IA16/A`, `1794-IB16/A`, `1794-OA8I/A`, `1794-OB16P/A` |
| name family | Generated `T_1794_AENT_*` vs finished `CP2RIO*` / `CP3RIO*` — **rack name ≠ ownership** (finished proves CP3RIO owned by PLC2) |

### CP_I
| Metric | Finished | Generated |
|--------|----------|-----------|
| rungs | **304** | **264** |
| real mappings | **159** | **256** |

### CP_O
| Metric | Finished | Generated |
|--------|----------|-----------|
| rungs | **304** | **155** |
| real mappings | **75** | **144** |

### MAPPINGS
| Metric | Value |
|--------|------:|
| exact (tag+slot+bit+dir, ignoring module name family) | **0** (module rename T_1794 vs CP2RIO) |
| equivalent (tag+direction) | **11** |
| missing tag+direction | **221** |
| extra tag+direction | **23** |

Identity fidelity still needs module-name alignment / tag-family normalization in a follow-on — counts alone are not success.

### TRANSPORT
| Metric | Value |
|--------|-------|
| full remote networks rendered | **NO** |
| external boundaries rendered | **YES** |
| visual | `exports/plc2-foundation/transportation.png` (from Auto Build graph used by Site Forge Transport) |

### STUDIO candidate
`exports/studio-validation/ORNCCP2_foundation_candidate.L5X`

## Artifacts
- `exports/plc2-foundation/controller_scope.json`
- `exports/plc2-foundation/io_map_comparison.json`
- `exports/plc2-foundation/report.json`
- `exports/plc2-foundation/transportation.png`
- `exports/plc2-foundation/ORNCCP2_foundation_candidate.L5X`

## Explicit non-goals this pass
- No PLC4/PLC5 generation
- No Sorter/WCS features
- No copying finished PLC values into generation
- No P1xx=PLC1 number scoping
