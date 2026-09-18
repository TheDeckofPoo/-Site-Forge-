# Transport Geometry Acceptance — Gates B–H / G / Y

Generated: 2026-09-18T08:04:48.540187+00:00

## Schema field spellings confirmed

- `X_cord`, `Y_cord` (NOT `X_coord` / `Y_coord`)
- Also: `Length`, `Width`, `Angle`, `Type`, `Inside_Radius`
- X/Y = infeed/ENTRY end; Angle = flow deg CCW from +X; CURVE Length=-1 → Inside_Radius + tangents

## Authority stack

1. **ENGINEER_ASSIGNED**
2. **PROVEN_RUN**
3. **DERIVED_TOPOLOGY**
4. **FALLBACK_LAYOUT**
5. **UNKNOWN**

Fallback must **not** silently overwrite PROVEN geometry. Source / effective / override provenance stored separately.

## Transform conventions

| Stage | Convention |
|-------|------------|
| RUN source | X_cord/Y_cord = infeed; Angle CCW from +X |
| Physical body | entry→exit along Angle · Length (or curve IR+tangents) |
| Canvas normalize | Uniform translate/scale (+ optional Y flip); relative X/Y preserved |
| Presentation | display_dx/dy offsets only; never mutates source |
| Hit / label / context | ONE authoritative display transform (`getDisplayTransform`) |

## Proven vs derived (sample of first 200 P-tags on PLC2 peek RUN)

- **ENGINEER_ASSIGNED**: 0
- **PROVEN_RUN**: 200
- **DERIVED_TOPOLOGY**: 0
- **FALLBACK_LAYOUT**: 0
- **UNKNOWN**: 0

## Site-specific production branch count

**= 0** (P500/P536 appear only in diagnostic report notes / this acceptance artifact).

## Acceptance example: P500

### RUN fields

- **X_cord**: `42166.667`
- **Y_cord**: `56000.0`
- **Length**: `1200.0`
- **Width**: `500.0`
- **Angle**: `270.0`
- **Type**: `STRAIGHT`
- **Inside_Radius**: `0.0`

### Rendered geometry

- **render_anchor**: `{'x': 42166.667, 'y': 56000.0}`
- **body_center**: `{'x': 42166.667, 'y': 55400.0}`
- **entry_endpoint**: `{'x': 42166.667, 'y': 56000.0}`
- **exit_endpoint**: `{'x': 42166.667, 'y': 54800.0}`
- **hit_target**: `{'center': {'x': 42166.667, 'y': 55400.0}, 'entry': {'x': 42166.667, 'y': 56000.0}, 'exit': {'x': 42166.667, 'y': 54800.0}, 'angle': 270.0}`
- **geometry_provenance**: `PROVEN_RUN`

### Up / down relationships (geometry candidates)

Upstream:
- PE544_P gap=141.421 mate=CONFIRMED
- PE444_P gap=147.432 mate=CONFIRMED
- P544 gap=149.999 mate=CONFIRMED
- P444 gap=150.001 mate=CONFIRMED
- PB500_JR gap=424.995 mate=HIGH_CONFIDENCE

Downstream:
- P502 gap=484.481 mate=HIGH_CONFIDENCE
- P504 gap=484.481 mate=HIGH_CONFIDENCE
- PE500_J gap=625.001 mate=HIGH_CONFIDENCE
- PE504_I gap=680.889 mate=HIGH_CONFIDENCE

### Why the old renderer scattered them

- Incorrect model: XY treated as footprint center; entry/exit = center +/- Length/2
- Entry error under center model: **600.000** drawing units
- Effect: Cards/segments placed on false centers so long runs looked short/misaligned and abutments showed artificial gaps — scattered labeled objects
- **Fixed**: True — Infeed-origin model (greensboro-infeed-v1) via fortna_physical_geometry + fortna_geometry_authority; no site-specific production branches

## Acceptance example: P536

### RUN fields

- **X_cord**: `43216.667`
- **Y_cord**: `56758.334`
- **Length**: `4300.0`
- **Width**: `200.0`
- **Angle**: `90.0`
- **Type**: `ZEROPRESSURE`
- **Inside_Radius**: `0.0`

### Rendered geometry

- **render_anchor**: `{'x': 43216.667, 'y': 56758.334}`
- **body_center**: `{'x': 43216.667, 'y': 58908.334}`
- **entry_endpoint**: `{'x': 43216.667, 'y': 56758.334}`
- **exit_endpoint**: `{'x': 43216.667, 'y': 61058.334}`
- **hit_target**: `{'center': {'x': 43216.667, 'y': 58908.334}, 'entry': {'x': 43216.667, 'y': 56758.334}, 'exit': {'x': 43216.667, 'y': 61058.334}, 'angle': 90.0}`
- **geometry_provenance**: `PROVEN_RUN`

### Up / down relationships (geometry candidates)

Upstream:
- P534 gap=0.001 mate=CONFIRMED

Downstream:
- P538 gap=591.137 mate=AMBIGUOUS

### Why the old renderer scattered them

- Incorrect model: XY treated as footprint center; entry/exit = center +/- Length/2
- Entry error under center model: **2150.000** drawing units
- Effect: Cards/segments placed on false centers so long runs looked short/misaligned and abutments showed artificial gaps — scattered labeled objects
- **Fixed**: True — Infeed-origin model (greensboro-infeed-v1) via fortna_physical_geometry + fortna_geometry_authority; no site-specific production branches

## Canvas UX (Gate H)

- Fit System, Fit Area, Center Selected, Home
- Geometry mode toggle: RUN/Physical (default) | Engineering Override | Diagnostic
- Selected highlight retained; zoom/pan retained

## Tests

`python tools/scripts/test_fortna_geometry_authority.py`

