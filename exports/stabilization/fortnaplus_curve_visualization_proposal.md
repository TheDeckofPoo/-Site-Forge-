# FortnaPlus Curve Visualization Proposal (short)

**Status:** investigation only — does not block sorter compiler work.

## Problem

Site Forge Transportation currently draws CURVE conveyors as purple geometric proxies that do not resemble FortnaPlus curve symbols (arc / radius / orientation).

## Fortna evidence available (do not copy assets)

| Source | Use |
|--------|-----|
| `Conveyor.asc` type / geometry fields | Classify STRAIGHT vs CURVE vs spur |
| Physical layout / run geometry (`fortna_run_physical_layout`, geometry authority) | Position, angle, length |
| MergeBoss / MergeRoute | Merge leg endpoints |
| Tracking / section models | External continuations |

## Proposed Site Forge renderer approach

1. Keep engineer layout coordinates as authority for placement.
2. For `type=CURVE` (or equivalent RUN classification), render a quadratic/cubic arc whose chord matches conveyor endpoints and whose bulge uses RUN angle/radius when present; fallback: fixed bulge from length.
3. Style: same stroke family as straights (not a separate purple “blob”); optional inner rail line.
4. Merges: draw induct leg as spur polyline into the merge node (MergeRoute evidence).
5. Do **not** import proprietary FortnaPlus bitmaps/SVGs — reproduce semantics with Site Forge primitives.

## Acceptance for a later commit

- Straight / curve / merge-leg / spur distinguishable at Transport zoom.
- No sorter/Safety behavior change.
