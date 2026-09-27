# Rockwell Addressing Notes (Generic)

## Families

Site Forge commonly sees:

- **1734 POINT I/O** — slot-indexed `Data[slot]` (no Flex slot−1 shift)
- **1794 FLEX I/O** — often `Data[slot-1]` when slot > 0 (family-aware scheme)

Exact byte/slot/`Data[]` conventions remain under independent validation.
When indexing proof is incomplete:

- Keep physical tuple as DERIVED if adapter/module/bank evidence is strong
- Leave rendered Logix candidate as `REVIEW_REQUIRED`

## Open validation (do not invent)

- 1734 POINT I/O byte / slot / `Data[]` convention confirmation
- 1794 FLEX I/O byte / slot / `Data[]` convention confirmation
- Appropriate PROVEN vs DERIVED threshold for rendering confidence

## Rendering vs physical

A correct physical channel may still have an uncertain Studio rendering string.
Never force a rendered address to close a case without proof.
