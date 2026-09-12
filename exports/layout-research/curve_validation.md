# CURVE geometry validation (RUN Conveyor.asc)

Generated: 2026-09-12T15:18:18.913587+00:00

Raw RUN coordinates were **not** modified. Finished PLC was **not** consulted.

## Winning rule

- **Preferred winner:** `H_hybrid`
- **b-as-exit-bearing confidence:** **MEDIUM**
- **Supported?** True
- **Recommend Site Forge patch?** True
- **Hybrid improves vs A:** 16

Treat b as absolute exit bearing candidate (normalize b%360; signed_sweep=shortest_delta(Angle,b)). Include that sweep as a mate-scored candidate alongside default 90° CW/CCW. Prefer b when mate-consistent; otherwise fall back to 90°+mate. Blind b without mate check is NOT safe (20 counterexamples).

### Evidence notes

- CP2 and CP4 mechanical CURVE geometry fingerprints are identical (same plant extract) — not independent multi-site replication.
- On 48/56 classic |shortest(Angle→b%360)|≈90° cases, A and B_short endpoint errors tie — b is consistent with the current 90° model.
- 14 curve(s) where B_short beats A by >10u (non-90° sweep from b), e.g. P446 shallow turn.
- 20 curve(s) where A beats B_short with a good A mate (e.g. P600F family b=190) — blind b is unsafe; require mate consistency.
- 32 curve(s) have b≡Angle (shortest) — b uninformative; fall back to default 90°+mate.
- Hybrid H=mate-min(A, B_short-if-informative): improves 16 vs A, never worse by construction; sources={'A_or_B_tie': 48, 'A_fallback': 74, 'B_short': 16}; stats={'n': 138, 'median': 183.333, 'p90': 568.06, 'mean': 231.206, 'min': 0.0, 'max': 733.523, 'good_lt_50': 54, 'excellent_lt_5': 20, 'good_pct': 39.1}.

## Population

- Curve evaluations (CP2+CP4): **138**
- Shared geometry fingerprints across sites: 69
- Unique geometry fingerprints: 0
- Classic |Δ|≈90° from Angle→b: 56 (A/B agree 48)
- b≡Angle zero-sweep cases: 32

### Preferred wins (tie-break order B_short > C > A > B_cont > D_mag)

```
{
  "B_short": 44,
  "C": 26,
  "A": 56,
  "D_mag": 12
}
```

### Endpoint-error stats by interpretation

| Interp | n | median | p90 | good&lt;50 | excellent&lt;5 | good% |
|--------|---|--------|-----|-----------|----------------|-------|
| A | 138 | 250.005 | 568.06 | 48 | 18 | 34.8% |
| B_short | 106 | 63.185 | 659.335 | 32 | 20 | 30.2% |
| B_cont | 106 | 167.005 | 741.713 | 22 | 10 | 20.8% |
| C | 106 | 142.076 | 453.117 | 26 | 14 | 24.5% |
| D_mag | 126 | 459.656 | 634.647 | 4 | 2 | 3.2% |
| H_hybrid | 138 | 183.333 | 568.06 | 54 | 20 | 39.1% |

## Decisive B_short over A (non-90° signal)

- **ORNCCP2 P446** Angle=-10.0 b=270.0: A_err=72.09 → B_err=4.679 (sweep=-80.0) mate P447
- **ORNCCP2 P806** Angle=90.0 b=35.0: A_err=233.109 → B_err=156.255 (sweep=-55.0) mate P802
- **ORNCCP2 P808** Angle=270.0 b=215.0: A_err=338.758 → B_err=157.115 (sweep=-55.0) mate P802
- **ORNCCP2 P700A** Angle=270.0 b=190.0: A_err=92.045 → B_err=52.521 (sweep=-80.0) mate SSV506B1
- **ORNCCP2 P600M** Angle=270.0 b=190.0: A_err=50.729 → B_err=33.401 (sweep=-80.0) mate SSV509M2
- **ORNCCP2 P600N** Angle=270.0 b=190.0: A_err=83.414 → B_err=33.401 (sweep=-80.0) mate SSV510N1
- **ORNCCP2 P600O** Angle=270.0 b=190.0: A_err=204.203 → B_err=160.257 (sweep=-80.0) mate SSV510O1
- **ORNCCP4 P446** Angle=-10.0 b=270.0: A_err=72.09 → B_err=4.679 (sweep=-80.0) mate P447
- **ORNCCP4 P806** Angle=90.0 b=35.0: A_err=233.109 → B_err=156.255 (sweep=-55.0) mate P802
- **ORNCCP4 P808** Angle=270.0 b=215.0: A_err=338.758 → B_err=157.115 (sweep=-55.0) mate P802
- **ORNCCP4 P700A** Angle=270.0 b=190.0: A_err=92.045 → B_err=52.521 (sweep=-80.0) mate SSV506B1
- **ORNCCP4 P600M** Angle=270.0 b=190.0: A_err=50.729 → B_err=33.401 (sweep=-80.0) mate SSV509M2
- **ORNCCP4 P600N** Angle=270.0 b=190.0: A_err=83.414 → B_err=33.401 (sweep=-80.0) mate SSV510N1
- **ORNCCP4 P600O** Angle=270.0 b=190.0: A_err=204.203 → B_err=160.257 (sweep=-80.0) mate SSV510O1

## Decisive A over B_short (fallback needed)

- **ORNCCP2 P600F** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600G** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600H** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600I** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600J** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600K** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P700B** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P700C** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600D** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP2 P600E** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP4 P600F** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP4 P600G** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP4 P600H** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP4 P600I** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False
- **ORNCCP4 P600J** Angle=270.0 b=190.0: A_err=11.785 B_err=63.185 skipped=False

## Good fits (best endpoint_error < 5)

- **ORNCCP2 P104** Angle=90.0 b=0.0 best=A err=0.001 mate=P106 tied=['A', 'B_short', 'B_cont', 'C']
- **ORNCCP2 P126** Angle=90.0 b=0.0 best=A err=0.001 mate=P128 tied=['A', 'B_short', 'B_cont', 'C']
- **ORNCCP2 P142** Angle=90.0 b=0.0 best=A err=0.0 mate=P144 tied=['A', 'B_short', 'B_cont']
- **ORNCCP2 P428** Angle=0.0 b=270.0 best=A err=0.0 mate=P430 tied=['A', 'B_short']
- **ORNCCP2 P438** Angle=0.0 b=270.0 best=A err=0.002 mate=P440 tied=['A', 'B_short', 'C']
- **ORNCCP2 P446** Angle=-10.0 b=270.0 best=B_short err=4.679 mate=P447 tied=['B_short', 'C']
- **ORNCCP2 P452** Angle=270.0 b=180.0 best=A err=0.001 mate=P454 tied=['A', 'B_short', 'B_cont', 'C']
- **ORNCCP2 P714** Angle=0.0 b=270.0 best=A err=0.0 mate=P716 tied=['A', 'B_short']
- **ORNCCP2 P540** Angle=90.0 b=0.0 best=A err=0.01 mate=P538 tied=['A', 'B_short', 'B_cont', 'C']
- **ORNCCP2 P532** Angle=180.0 b=450.0 best=A err=0.001 mate=P534 tied=['A', 'B_short', 'C', 'D_mag']
- **ORNCCP4 P104** Angle=90.0 b=0.0 best=A err=0.001 mate=P106 tied=['A', 'B_short', 'B_cont', 'C']
- **ORNCCP4 P126** Angle=90.0 b=0.0 best=A err=0.001 mate=P128 tied=['A', 'B_short', 'B_cont', 'C']

## Poor fits (best endpoint_error > 200 or unscored)

- **ORNCCP2 P108** Angle=270.0 b=180.0 best=C err=447.835 errors={'A': 589.26, 'B_short': 589.26, 'B_cont': 589.26, 'C': 447.83, 'D_mag': 733.33}
- **ORNCCP2 P112** Angle=0.0 b=270.0 best=B_cont err=412.401 errors={'A': 506.25, 'B_short': 506.25, 'B_cont': 412.4, 'C': 412.4, 'D_mag': 412.4}
- **ORNCCP2 P134** Angle=0.0 b=270.0 best=A err=275.638 errors={'A': 275.64, 'B_short': 645.82, 'B_cont': 396.69, 'C': 396.69, 'D_mag': 396.69}
- **ORNCCP2 P148** Angle=0.0 b=270.0 best=B_cont err=357.849 errors={'A': 700.0, 'B_short': 700.0, 'B_cont': 357.85, 'C': 357.85, 'D_mag': 357.85}
- **ORNCCP2 P308** Angle=350.0 b=270.0 best=A err=568.06 errors={'A': 568.06, 'B_short': 751.92, 'B_cont': 751.92, 'C': 751.92, 'D_mag': 720.52}
- **ORNCCP2 P316** Angle=350.0 b=270.0 best=C err=453.117 errors={'A': 465.01, 'B_short': 570.56, 'B_cont': 570.56, 'C': 453.12, 'D_mag': 501.43}
- **ORNCCP2 P324** Angle=350.0 b=270.0 best=C err=335.826 errors={'A': 443.73, 'B_short': 581.63, 'B_cont': 581.63, 'C': 335.83, 'D_mag': 338.2}
- **ORNCCP2 P434** Angle=180.0 b=450.0 best=A err=408.333 errors={'A': 408.33, 'B_short': 408.33, 'B_cont': 447.83, 'C': 408.33, 'D_mag': 408.33}
- **ORNCCP2 G604F** Angle=180.0 b=180.0 best=A err=319.07 errors={'A': 319.07, 'B_short': None, 'B_cont': None, 'C': None, 'D_mag': 634.65}
- **ORNCCP2 G604G** Angle=180.0 b=180.0 best=A err=319.07 errors={'A': 319.07, 'B_short': None, 'B_cont': None, 'C': None, 'D_mag': 634.65}
- **ORNCCP2 G604H** Angle=180.0 b=180.0 best=A err=319.07 errors={'A': 319.07, 'B_short': None, 'B_cont': None, 'C': None, 'D_mag': 634.65}
- **ORNCCP2 G604I** Angle=180.0 b=180.0 best=A err=319.07 errors={'A': 319.07, 'B_short': None, 'B_cont': None, 'C': None, 'D_mag': 634.65}

## Recommended Site Forge change

Patch `fortna_physical_geometry.py`:

1. When Conveyor.asc field `b` is present, treat it as an **absolute exit bearing candidate** (normalize `b % 360`, including values like 450→90).
2. `signed_sweep = shortest_delta(Angle, b%360)`.
3. Score that candidate via neighbor mating **alongside** default 90° CW/CCW.
4. If `|signed_sweep| < ε` or `b` missing → only the 90°+mate path (`ASSUMPTION` / `INFERRED_GEOMETRY`).
5. If the b-derived candidate wins the mate score → apply it with `provenance.sweep/turn = RUN_EXPLICIT`.
6. Do **not** invent site-specific constants; do not bind continuous b−Angle (B_cont underperforms B_short).

## SVG Y-flip / pathCanvas

fortna_run_physical_layout.py projects pathCanvas with screen Y flip (cy - (y - sourceY)*scale) and inverts SVG sweep_flag for arc commands. Plant-space signed_sweep from this validator must stay unflipped; only the canvas projection layer inverts sweep_flag.

## Sites

- **ORNCCP2**: mechanical=485, curves_scored=69, asc=`C:\dev\worktree\FortnaPlus\workspace\active\RUN\FORTNA\Conveyor.asc`
- **ORNCCP4**: mechanical=485, curves_scored=69, asc=`C:\dev\worktree\FortnaPlus\workspace\cp4-run\RUN\FORTNA\Conveyor.asc`
