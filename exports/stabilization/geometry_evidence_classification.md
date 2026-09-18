# Geometry Evidence Classification (CURVE display)

| Field | Class | Notes |
|-------|-------|-------|
| entryCanvas | PROVEN | Used for midpoint + display direction vector |
| exitCanvas | PROVEN | Used for midpoint + display direction vector |
| pathCanvas | PROVEN | Chord fallback for display heading |
| sourceAngle | PROVEN | Display heading fallback only |
| b / runB | PROVEN | Raw RUN; not used to invent elbow L/R |
| sweepDeg | PROVEN | Raw RUN; elbow paint remains UNKNOWN |
| insideRadius | PROVEN | Raw RUN; elbow paint remains UNKNOWN |
| display heading (UI) | DERIVED | atan2(exit−entry) when length > ε |
| physical L/R elbow | UNKNOWN | Never synthesized |
| presentation_offsets | DERIVED | Site Forge layout only |

Implementation: `curveDisplayDirectionRad()` in `dashboard/transport-build.js`  
aligns the purple oblong CURVE with the proven display vector when available.
