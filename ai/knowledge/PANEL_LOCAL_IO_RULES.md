# Panel-Local I/O Rules

## A. PANEL-LOCAL AUTHORITY

Physical endpoint mapping must come from evidence belonging to the **target**
panel / controller / adapter.

Similarity of any of the following does **not** authorize cross-panel physical
mapping:

- word number
- bank number
- offset
- module order
- naming
- another controller's topology

Cross-panel evidence may inform semantics (e.g. "this looks like an MCR AUX")
but may never establish physical endpoint authority.

Bank namespaces are **per adapter / panel**. Numeric bank collision across
panels is expected and must not join modules across ownership scopes.

## B. DIRECTION GRANULARITY

Do not assume an entire logical word has one I/O direction.

Direction may require resolution at:

- adapter
- byte range
- module
- channel / half-word

A single octal word may split Low=Input / High=Output (or the reverse) when
Configio In_Out masks and module banks prove it.

## C. MEMORY / NONPHYSICAL ROWS

Memory and nonphysical configuration rows must not become physical I/O
endpoints. Visibility for review is allowed; operational endpoint emission is
not.

## D. PHYSICAL VS LOGIX RENDERING CONFIDENCE

Separate conclusions:

1. Physical panel / module / channel tuple
2. Rendered Logix `Data[]` address

Relay may hold **DERIVED** confidence on (1) while leaving (2) as
`REVIEW_REQUIRED` when indexing conventions are not independently proven.

## E. COIL / AUX CONSISTENCY

Command coils and AUX feedback may be used as a **consistency check**.

Do **not** use naming alone as physical endpoint authority.

## Required Relay reporting

Every physical claim must record whether cross-panel evidence was encountered
and must set `cross_panel_physical_mapping_used: false` for valid claims.
