# REALITY SCORECARD — Site Forge Reality Check V1

**Generated:** 2026-09-20T20:37:36.340729+00:00
**Baseline SHA:** `25b0752d5c364e04b7cd3ee2b0e34a96524a6d24`
**Measurement SHA (may equal baseline if no decoder commits):** `25b0752d5c364e04b7cd3ee2b0e34a96524a6d24`

No marketing language. No inflated scores. Measurement only — blockers not fixed in this task.

| subsystem | Demo A (MSCATL_CP3) | Demo B Pass1 (FISHER_CC9) | what works now | what is incomplete | principal blocker | next engineering action |
|-----------|---------------------|---------------------------|----------------|--------------------|-------------------|-------------------------|
| RUN ingestion | PASS | PASS | Virgin RUN → evidence bundle | Odd TAR members (ABS_CARD) need selective extract | Windows extract edge cases | Keep selective extract; document GUI tar pack |
| source scoping | PASS | PASS | Active vs sibling machine sources | Sibling provenance UX in GUI | — | Surface scope badges in Hardware view |
| hardware topology | PASS (3 racks, 0 unplaced) | PASS/PARTIAL (10 racks) | Rack discovery + AREA_RIO_N presentation aliases | Multi-family edge cases | Unplaced / odd network devices on hard sites | Harden rack discovery on Fisher-class sites |
| physical I/O | PASS 256/256 PROVEN, conservation PASS | PARTIAL 874/971 PROVEN; 97 needs_resolution | Exact IP bridge + direction-aware banks | Unbound PHYSICAL_RESOLUTION_FAILURE families | Missing Fortna binding convention(s) for Fisher cluster | Investigate/promote deterministic rule after review |
| Transportation | PARTIAL | PARTIAL | Native merge discovery exists | Virgin merge presence gaps (Demo A missing P3012A) | Merge proven≠present in L5X | Transport/merge handoff fidelity task |
| Safety | REVIEW_REQUIRED | REVIEW_REQUIRED | Fail-safe virgin (no invented members) | Engineer Apply required for membership | Virgin Safety empty by design | Engineer Safety Apply workflow / discovery honesty |
| Sorter | NOT_APPLICABLE | NOT_APPLICABLE | — | Not in these controllers' focus | — | Leave until sorter site demo |
| VFD | NOT_IMPLEMENTED | NOT_IMPLEMENTED | — | No VFD reality path exercised | VFD contract incomplete | Separate VFD task when scheduled |
| canonical model | PARTIAL | PARTIAL | Machine closure + hardware model | Full-site twin readiness | Cross-subsystem handoff | Canonical model closure task |
| compiler | L5X generated; qual FAIL; PREFLIGHT_PASS | BLOCKED (skip-generate Pass1) | Can emit L5X + static preflight | Qual gates FAIL/REVIEW on virgin | Merge/Safety/provenance gates | Do not claim READY; fix gates after prioritization |
| GUI | PARTIAL (repro pack + instructions) | NOT_APPLICABLE | Electron launch + hardware view path | Automated screenshots not captured | Browse Archive needs tar.gz | Curtis opens Launch-SiteForge with packed tar |
| PostgreSQL | PASS | PASS | Knowledge vs current-site isolation proven | Rule coverage evaluator thin | — | Keep learning separate from site facts |
| provenance | PASS (5 traces) | PARTIAL | Binding + resolver traces | Readable GUI provenance panel | — | Wire traces into GUI |
| AI Investigator | N/A (not needed) | Pass2 live: status=INSUFFICIENT_EVIDENCE; cost=$0.296684 | Structural-family investigation; CANDIDATE only | No auto-promote; shadow incomplete | Candidate≠production | Review candidate; shadow; then decide |
| qualification | FAIL overall (honest) | REVIEW/FAIL expected | Catches merge/Safety/provenance | Virgin full-site not green | Same as Transport/Safety | Use FAIL as roadmap, do not greenwash |

## Demo A headline

- matches prior accepted: **True**
- actual: raw=256, PROVEN=256, needs_resolution=0, racks=3, conservation=PASS
- readiness overall: **HARDWARE_IO_READY__FULL_SITE_PARTIAL**
- compiler: L5X=True, preflight=PREFLIGHT_PASS, qual=FAIL

## Demo B headline

- selected before decode: **True** — FISHER_CC9
- Pass1: PROVEN=874, needs_resolution=97, racks=10, conservation=PASS
- Pass2: live_ai=True, decoder_mutated=False, endpoints_assigned=False, cost_usd=0.296684

## Candidate coverage (NOT resolved)

{
  "candidate_status": "INSUFFICIENT_EVIDENCE",
  "claims_potentially_covered_if_promoted_later": 0,
  "cluster_key": "c363715ca1e83906",
  "note": "Do NOT call these claims resolved. Production counts remain Pass1 until rule promotion after review."
}

