# Device Comms / NTP — Generic Contract Gap (diagnosis only)

**BASE SHA:** `a935a22`  
**GOLD L5X:** `MSCRENOPICK_2026_10_13_1725.L5X`  
**Library:** `tools/libraries/OReilly_Library_v3.L5X`  
**Rule:** Do NOT copy finished-site code.

---

## Device_Comm_Logic

| Field | Result |
|---|---|
| GENERIC CONTRACT | **UNKNOWN / INCOMPLETE** |
| L5X tonight | `REVIEW_REQUIRED — CommDiag_UDT absent from approved generic library (PD-0029…); Device Comms deferred` → NOP |
| `CommDiag_UDT` in OReilly_Library_v3 | **ABSENT** |
| Safe-to-generate | **0%** until approved generic UDT+AOI lands in library |

### Required to enable safely (spec)

1. **UDT:** `CommDiag_UDT` (or approved generic equivalent) in OReilly_Library_v3  
2. **AOI / routines:** generic Device Comm diagnostic AOI (inputs/outputs/status)  
3. **Inputs:** module/adapter health signals proven from RUN EIP topology (not finished-site hard-codes)  
4. **Outputs:** operator/HMI diag bits with single-writer rules  
5. **Parameters:** timeouts, poll rates — site-tunable, not copied from Greensboro/Reno finished PLC  
6. **Site-specific assumptions:** none for emit gate; site only supplies adapter inventory evidence  

**Implementation status:** deferred (correct). No code change this overnight.

---

## NTP / SNTP

| Field | Result |
|---|---|
| GENERIC CONTRACT | **UNKNOWN / INCOMPLETE** |
| L5X tonight | NTP/SNTP deferred — generic evidence insufficient |
| Library tokens | `SKT_SNTP_Data` / SNTP members appear in library XML; **not** a complete approved Site Forge NTP emit contract |
| NTP AOI name match | partial token presence ≠ commissionable generator path |
| Safe-to-generate | **0%** without explicit generic contract + evidence ladder |

### Required to enable safely (spec)

1. **UDT:** approved generic NTP/SNTP data UDT (not finished-site SKT_* alone)  
2. **AOI:** generic time-sync AOI with documented InOuts  
3. **Inputs:** time source / gateway evidence from RUN or engineer commissioning sheet  
4. **Outputs:** controller wall-clock / sync status tags  
5. **Parameters:** server IP, poll interval, timezone — engineer-provided  
6. **Site-specific assumptions:** server address is NEVER invented from another site  

**Implementation status:** deferred (correct). Diagnosis only.

---

## Recommendation

Keep PD-0029 quarantine. Add a future mission: “Approve generic CommDiag_UDT + NTP contract into OReilly_Library_v3 with fixture tests” before any emit.
