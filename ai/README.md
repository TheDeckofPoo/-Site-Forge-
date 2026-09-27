# Site Forge AI — Durable Machine Memory

This directory is **Relay's durable knowledge pack** inside the Site Forge repository.

## Why persistent bot memory is necessary

A brand-new Relay session must start with the same verified Site Forge I/O laws
without depending on:

- prior chat history
- temporary `/workspace` files
- local bot memory
- a running computer session
- Google Drive availability

The repository is machine memory. Google Drive is human continuity / disaster
recovery only — **not** a runtime dependency.

## STARTUP LOAD ≠ AI CALL

When Site Forge starts:

1. Read local knowledge files via `context_manifest.yaml`
2. Validate the manifest and required files
3. Compute version / SHA-256 hashes
4. Prepare a Relay context bundle
5. Report `RELAY KNOWLEDGE: READY | DEGRADED | ERROR`

**Do not** automatically invoke any AI/API provider because the app started.

## What gets stored

| Path | Purpose |
|------|---------|
| `constitution/` | Permanent Site Forge AI laws |
| `knowledge/` | Generic I/O / ownership / signal handbooks |
| `verified_lessons/relay/` | Lessons that passed promotion |
| `candidate_lessons/relay/` | Promising but unproven observations |
| `negative_examples/relay/` | Anti-patterns / forbidden inferences |
| `evals/relay/` | POC records, hashes, scores (no TARs) |
| `agents/relay/` | Start-here, system prompt, runbook, schema, manifest |
| `current_state/` | Concise live status for a fresh session |

## What does **not** get stored

- API keys, credentials, tokens, passwords
- Full TAR archives / ACD files
- Finished customer PLC/L5X used as discovery parents
- Temporary workspace dumps
- Giant raw evidence dumps
- Machine-specific absolute paths as authoritative config
- Site-specific endpoint answers as permanent handbook rules

## Knowledge promotion

```
Relay observation
  → evidence
  → Curtis engineering review and/or authoritative documentation
  → deterministic implementation if applicable
  → Warden independent validation
  → VERIFIED LESSON (verified_lessons/relay/)
```

**No automatic promotion.** Candidate lessons never enter the verified pack
without the process above.

## Fresh Relay session

1. Load `ai/agents/relay/context_manifest.yaml` (deterministic order)
2. Read `RELAY_START_HERE.md` first among agent files
3. Follow the manifest load order exactly
4. When evidence stops, Relay stops

## Adding a verified lesson

1. Capture observation + evidence under `candidate_lessons/relay/`
2. Complete promotion process
3. Move (or copy) into `verified_lessons/relay/` with provenance notes
4. Bump knowledge-pack version in `context_manifest.yaml` if required

## Adding an eval

1. Create `ai/evals/relay/poc_NNN/`
2. Record source filename + hash (TAR stays outside Git)
3. Record baseline SHA, findings, scores, open questions
4. Do not pre-populate conclusions before the exam finishes

## Invalidating a bad lesson

1. Remove or quarantine from `verified_lessons/relay/`
2. Optionally add a negative example explaining why it failed
3. Bump knowledge-pack version
4. Note revocation in `RELAY_CURRENT_STATE.md`

## Loader

Implementation: `tools/scripts/fortna_relay_knowledge_loader.py`

Startup integration: Electron `app.whenReady` → IPC `relay-knowledge-status`
(read-only; no network; no AI call).

## Shadow mode

See `ai/agents/relay/RELAY_SHADOW_MODE.md`.

Orchestrator: `tools/scripts/fortna_relay_shadow.py`

- Default **disabled** (no API spend)
- Explicit `relay-shadow-run` IPC / **Run Relay Shadow Review** button
- Never writes production endpoints (`production_authority=false`)
