# Relay Shadow Mode

Operational analysis/review path only. **No production endpoint authority.**

## Default

- `SITEFORGE_RELAY_SHADOW` unset / false → no AI invocation
- Startup loads knowledge only (`RELAY KNOWLEDGE: READY`) — **zero API calls**
- Explicit IPC: `relay-shadow-run` with `{ machine, points, enable: true }`

## Flow

1. Deterministic Site Forge I/O points
2. Trigger classifier (skip clean PROVEN)
3. Panel-local evidence packet (never whole TAR / L5X / ACD)
4. Durable knowledge bundle
5. Optional AI invoke
6. Schema + policy validation
7. Grouped engineer review queue

## Scripts

| Module | Role |
|--------|------|
| `fortna_relay_trigger.py` | Eligibility |
| `fortna_relay_evidence_packet.py` | Minimal packet |
| `fortna_relay_invoke.py` | Provider adapter |
| `fortna_relay_schema.py` | Schema / policy |
| `fortna_relay_review_queue.py` | Queue + grouping |
| `fortna_relay_shadow.py` | Orchestrator + cache/audit |

## Forbidden

- `APPLY ENDPOINT`
- `cross_panel_physical_mapping_used=true` as actionable
- Auto API spend on app open
- Candidate/eval conclusions as VERIFIED knowledge
