# Signal Roles

## Device ≠ signal ≠ role

| Layer | Example |
|-------|---------|
| Device | `6MCR1` (canonical) |
| Signal | `6MCR1_AUX`, `T_6MCR1` |
| Role | COMMAND / AUX / FEEDBACK / PRIMARY |

## Common Safety roles

- **COMMAND** — energize / coil output identity (often BOOL)
- **AUX / FEEDBACK / ES_OK** — feedback identity (often the I/O-written ES path)
- **PRIMARY** — main ESTOP / ESR / ESLS claim

## Compiler vs Relay

- Engineer assigns **canonical devices**
- Compiler resolves proven AUX/feedback for consumers when evidence exists
- Relay may propose role classification; Relay may not invent AUX without evidence

## Consistency checks

Coil ↔ AUX pairing may corroborate semantics.
Naming alone is never physical endpoint authority.
