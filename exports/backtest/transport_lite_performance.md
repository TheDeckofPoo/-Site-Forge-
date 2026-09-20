# Transport Lite performance notes (f2cf46f hierarchy changes)

## Change cost

Stroke hierarchy and far-zoom label LOD were implemented as:

- CSS / inline `stroke-width` on existing path elements
- Conditional label emission (overview: merges/selected only)

No additional SVG nodes per conveyor for girth.

## Expectation

Negligible FPS impact vs prior Lite (same path count; fewer labels at far zoom).

## Measurement

Automated Electron timing for multiple corpus densities was **not** collected in this
pass (noisy without a dedicated harness run). Prior Lite existence already documents
why heavy detailed geometry stays optional.

## Recommendation

When Curtis returns, use Fit System + pan/zoom on a dense site and compare feel.
If needed, add `perfRecord` CSV export for node/label counts next.
