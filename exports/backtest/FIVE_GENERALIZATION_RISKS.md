# Five biggest generalization risks (post f2cf46f + loader hotfix)

Derived from corpus backtest / taxonomy / merge study. Do not fix all now.

1. **Unknown module capacities**
   - Evidence: many catalogs lack `channel_capacity_for_catalog` contracts → UI may show `N` not `N/C`.
   - Failure: occupancy misread as decoder failure.
   - Fail-safe today: PARTIAL (OW8 fixed; unknowns flagged REVIEW).

2. **Safety device taxonomy is OBSERVED_ONLY**
   - Evidence: corpus patterns for E_STOP/ESLS/RESET exist; ESR/MCR/CS weaker.
   - Failure: Safety Build FOUND under-count / mis-category.
   - Fail-safe: REVIEW_REQUIRED zones; no invented membership.

3. **Merge N>2 + lettered discharge placement**
   - Evidence: P3012A was skipped by emit; GUI geometry may still lack placed P3012A node.
   - Failure: discovery PROVEN but schematic/L5X incomplete.
   - Fail-safe: emit now fixed; placement still geometry-dependent.

4. **Safety handoff vs Transport shells**
   - Evidence: Atlanta field L5X showed transport_engineer hollow members.
   - Failure: engineer assignments silently dropped.
   - Fail-safe: Apply verify + Build parity gate (new).

5. **Renderer/loader fragility**
   - Evidence: `??`/`||` mix syntax error killed entire GUI (Browse Archive dead).
   - Failure: primary workflow unavailable with no obvious button error.
   - Fail-safe: node --check regression + picker user feedback (new).
