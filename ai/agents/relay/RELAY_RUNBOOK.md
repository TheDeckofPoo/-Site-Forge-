# Relay Runbook

## Fresh session bootstrap

1. Confirm knowledge pack status is READY (or understand DEGRADED gaps)
2. Read current state
3. Identify eval / case scope
4. Load only RUN evidence for the target machine/panel
5. Produce schema-conformant claims
6. Compare to Site Forge when requested — note that agreement ≠ independent proof

## Case workflow

1. Record `case_id`, source controller/panel, raw address
2. Collect evidence[] with source tables and scope
3. Resolve adapter → module → slot → direction → channel **inside panel scope**
4. Separate physical_endpoint_candidate vs rendered_logix_candidate
5. List contradictions[] and missing_proof[]
6. Assign confidence
7. Set cross_panel flags honestly
8. Recommend deterministic check if Site Forge should encode the lesson

## Refusal conditions

Stop proposing physical endpoints when:

- target-panel bank/module proof is absent
- only cross-panel numeric coincidence exists
- row is memory/nonphysical
- direction cannot be resolved at required granularity

## After a POC

Update `ai/evals/relay/poc_NNN/` with scores and open questions.
Do **not** write site-specific answers into handbooks.
Do **not** auto-move candidates to verified.
