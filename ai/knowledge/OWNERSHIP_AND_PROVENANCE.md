# Ownership and Provenance

## Active machine owns compiler state

Operational inventory and Default membership belong to the **active machine**.

- Blank / unknown ownership ≠ active machine
- Foreign ownership stays foreign
- Unknown/foreign evidence may be **visible for review**
- Unknown/foreign must not become operational Default membership

## Evidence-strength ordering

```
PROVEN  >  DERIVED  >  UNKNOWN
```

A weaker ownership update must not erase stronger proven ownership.
Conflicts → `REVIEW_REQUIRED` and preserve both provenance records.

## Provenance discipline

- Prefer current-machine RUN tables for discovery
- Finished L5X / ACD: validation only
- Engineer overrides: explicit, never silent
- Synthetic / fixture labels must not masquerade as RUN-proven

## Relay reporting

Every claim needs provenance: source tables, panel/adapter scope, and why the
confidence level was chosen.
