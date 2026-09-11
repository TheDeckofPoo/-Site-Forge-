# PR draft — Transport UX Pass 1+2 + Stabilization

**Branch:** `feature/transport-ux-pass2-stabilization`  
**Commit:** `58f61881dc94347242bb4a347b2e8b6b2f65a892`  
**Create PR:** https://github.com/TheDeckofPoo/-Site-Forge-/pull/new/feature/transport-ux-pass2-stabilization  
(also pushed to `origin` / FortnaPlus redirect)

## Summary

Implements Transport Build UX Pass 1 (topology-first) and Pass 2 (rapid engineering workflow), then stabilizes:

1. **Cross-area Area moves preserve topology** — `moveNodeToArea` no longer clears `node.downstream`.
2. **Explicit Pass 2 render hook** — `window.__tbOnTransportRender` called from Pass 1 `render()`; MutationObserver removed.
3. **AI Build Protocol** — `docs/AI_BUILD_PROTOCOL.md`.

## Architecture note (cross-area)

- Visual `wires[]` remain **area-scoped** (drawn only when both ends share an area).
- Canonical topology is tag-based **`node.downstream`** (area-independent).
- `apply_graph_to_workbook` already prefers wires, then falls back to `node.downstream` across the whole graph.
- Therefore Area is organizational metadata; changing Area must not destroy product-flow relationships.
- Cross-area **visual** wires are not drawn yet (deferred); tag topology + Apply + L5X remain intact.

## What this proves (tests)

| Suite | Result | What it proves |
|-------|--------|----------------|
| `test_transport_ux_pass1.py` | **16/16 PASS** | Pass 1 asMerge/downstream Apply contract + ModuleB merge |
| `test_transport_ux_pass2.py` | **78/78 PASS** | Build Chain graph, branch/merge+P408, bulk Area/ES undo snapshot, Pass1 regression |
| `test_transport_pass2_parse.js` | **9/9 PASS** | Chain text parsing |
| `test_transport_cross_area_move.py` | **13/13 PASS** | P136→P138→P140 survives P138 Area A→B; workbook + **runtime L5X Fast_Conv** P136→P138 and P138→P140 |

## Known limitations

- Cross-area visual wires not rendered (tag topology only until a later canvas pass).
- 3:1 merge: topology representable; **GENERATION NOT YET SUPPORTED** (unchanged).
- No PDF parsing (by design).
- `gh` CLI not authenticated in this environment — PR must be opened via the link above (or after `gh auth login`).
- Large/transient exports under `exports/transport-*` not committed (L5X already gitignored).

## Out of scope / STOP

- No Pass 3
- No Sorter/Sawtooth/Autogen redesign
- No PDF parsing
- Stop after PR for human Greensboro use + external review of the GitHub diff
