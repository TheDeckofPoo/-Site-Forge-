# Final Completion Report — CP2 Visual Gate + PLC4 Sawtooth Fidelity

**Branch:** `feature/cp4-sawtooth-fidelity`  
**Base:** `feature/transport-physical-layout-pass2`  
**Date:** 2026-09-12

---

## 1. CP2 visual comparison result

**Verdict:** `RECOGNIZABLE_BUT_IMPERFECT` (demo-usable)

Print (`cp2_print_reference.png`) used as **human visual validation only** — not geometry/topology input.

| Region | Classification |
|--------|----------------|
| Red-box spiral / curve bank | Was missing → fixed via generic same-IO-word dense CURVE-bank display-context → **RECOGNIZABLE_BUT_IMPERFECT** |
| West / east hairpins | **MATCHES_WELL** |
| Long straights / parallels | **RECOGNIZABLE_BUT_IMPERFECT** |
| Curve arcs | **MATCHES_WELL** |
| Labels / no Area-ES clutter | **MATCHES_WELL** |
| Merges | **UNKNOWN** (CP2 Autogen `merges_detected=0`) |

Details: `exports/layout-research/cp2_print_comparison.md` / `.json`

---

## 2. Transport demo freeze

# TRANSPORT_DEMO_READY

Recorded in `docs/TRANSPORT_FREEZE_GATE.md`.

Major visual Transport work is frozen unless a clear generic geometry bug appears.

---

## 3. Remaining Transport limitations

- Spiral bank is **display_context** (not PLC-owned); Apply excludes it
- Print sheet framing ≠ canvas framing (intentional)
- Merge approach geometry not exercised on CP2 Autogen set
- Field `b` exit-bearing = MEDIUM hypothesis
- Large display-context density → use Fit Visible
- No CAD-perfect / pixel match

---

## 4. PLC4 Sawtooth generation completed

**Yes** — candidate L5X from RUN + discovery + generic libraries + explicit parameter map.

Path:

- `exports/cp4-sawtooth-pass/generated/OReillyGreensboro_ORNCCP4.L5X`
- `exports/cp4-sawtooth-pass/generated/Sawtooth_Merge_Parameterized.L5X`

Preserved: 5 lanes, lane indices, `LANE_3_P116`→`PE118_P`/`VFD118_EN`, slice/reserve timing, VFD414/VFD424 shared relationships, ENC414/ENC424.

---

## 5. CONFIGURATION REQUIRED (highlights)

- Area / ES / downstream for conveyors (engineer)
- ~69 unmapped gold-pack symbols (`EZPE127_F`, `P422_SawMerge_HMI`, `MRG422_*`, staging neighbors, feature enables)
- `LANE_0` ReserveTM `EZPE217_F` — no pack counterpart
- `LANE_4` ReserveTM `EZPE212_F1` vs pack `EZPE212_F2` — confirm

See `exports/cp4-sawtooth-pass/configuration_required.json`.

---

## 6. GENERATION NOT YET SUPPORTED

Tracking / WCS programs (inventory only):

- `SrtTrack`, `MsgTrack`, `MsgWCS`, `WCSEvents`, `XfrTrack`

Do not silently add because finished PLC4 contained them.

---

## 7. Tests run / results

| Suite | Result |
|-------|--------|
| `test_cp4_sawtooth_fidelity.py` | PASS (L5X parse + leakage) |
| `test_cp4_compiler_pass2.py` | PASS |
| `test_cp4_discovery_no_leakage.py` | PASS |
| `test_auto_build_physical_layout.py` | PASS (incl. spiral display-context) |
| `test_transport_physical_drawing.py` | PASS |
| `test_display_layout_offsets.py` | PASS |
| `test_fortna_physical_geometry.py` | PASS |
| `test_transport_physical_presentation.py` | PASS |
| `test_cp2_completion_gate_artifacts.py` | PASS |
| `test_source_truth_no_leakage.py` | PASS |

Finished PLC4 present/absent/renamed must not change generated digests (covered by sawtooth fidelity + discovery leakage tests).

---

## 8. Generated candidate L5X path

`exports/cp4-sawtooth-pass/generated/OReillyGreensboro_ORNCCP4.L5X`

Architecture/review compares to finished PLC4 **after** push — not done in this agent pass.

---

## 9. Known risks

1. Gold pack still carries staging/collector neighbor symbols marked CONFIG REQUIRED  
2. `Conv_*` fills are binding/provenance aids — not full Fast_Conv AOI rewrite  
3. Full-eye EZPE mismatches on lanes 0/4 need engineer confirm  
4. Candidate L5X not Studio-download-validated here  
5. Transport spiral display-context increases canvas density  

---

## UX rule

No new top-level buttons. Workflow remains Import → Auto Build → Review → Apply → Build PLC.
