# Autogen Provenance Auditor

## Purpose

Answer: **“Why did you generate this?”** for important Autogen decisions.

Site Forge is a compiler:

```
RUN evidence
  → decoder / FortnaPlus semantics
  → canonical model
  → engineer review / Apply
  → effective Autogen model/workbook
  → L5X
```

A finished PLC is a **validation oracle only**. It is **never** discovery or generation input, and it must not participate in provenance creation.

The auditor prevents accidental brownfield copying, stale-site inheritance, hidden defaults, and “it matches an old PLC so it must be right” generation.

## Trust model

Provenance travels **forward** from the evidence/model that caused generation.

Do **not** compare L5X to Brownsburg (or any finished PLC) and assign provenance afterward.

## Provenance classes

| Class | Meaning |
|-------|---------|
| **PROVEN** | RUN explicitly establishes the fact |
| **DERIVED** | Deterministic transform of PROVEN/ENGINEER facts |
| **ENGINEER_ASSIGNED** | Engineer Apply / override |
| **REVIEW_REQUIRED** | Evidence incomplete or ambiguous |
| **UNKNOWN** | No accepted evidence |

Do not invent GUESSED / ASSUMED / INFERRED_FROM_REFERENCE_PLC.

## Data flow (v1)

```
RUN (+ optional safety_build / autogen_report)
  → fortna_autogen_provenance.audit()
      → I/O collector (HardwareIOModel)
      → Safety collector (SafetyModel + Apply payload)
      → Transport collector (physical layout)
      → Program inclusion (autogen report when present)
      → Anti-copy checks
  → autogen_provenance.json
  → autogen_provenance_report.md
```

Version 1 is **additive / observational**. It does not rewrite CP1–CP4 or change generation semantics.

## Covered subsystems (v1)

- Physical I/O endpoints + owners
- Safety zone existence + membership
- Transport layout mode / RUN XY authority
- Program inclusion / ES emit policy (when report provided)
- Anti-copy / integrity scans

## Uncovered (future)

- Per-rung ladder provenance for every AOI call
- Full Sorter divert packing decisions
- Every structured-tag serializer choice
- Ignition / HMI generation

## How to run

```bash
# Full audit
python tools/scripts/fortna_autogen_provenance.py audit ^
  --run-dir workspace/cp5-run/RUN ^
  --machine ORNCCP5 ^
  --out exports/stabilization

# With Safety Apply payload
python tools/scripts/fortna_autogen_provenance.py audit ^
  --run-dir workspace/_virgin_orindy/RUN ^
  --machine ORINDYAC6 ^
  --safety-build path/to/safety_build.json ^
  --out exports/stabilization

# Why query
python tools/scripts/fortna_autogen_provenance.py why ^
  --run-dir workspace/cp5-run/RUN ^
  --machine ORNCCP5 ^
  --query 5MCR1
```

## Interpreting REVIEW_REQUIRED / UNKNOWN

- **REVIEW_REQUIRED**: Site Forge found something incomplete/ambiguous (empty Safety membership, unresolved owner, unknown family with Flex-shaped endpoint, etc.). This is **success of the auditor**, not a greenwash failure.
- **UNKNOWN**: No accepted evidence for the fact.
- Do not “fix” these by inventing defaults so the report looks green.

## Adding provenance for a new generator

1. Emit or expose the decision inputs (sources + transform) where the generator decides.
2. Add a collector branch in `fortna_autogen_provenance.py` (or attach records into the autogen report).
3. Add:
   - known-site test
   - blind/virgin test (no finished PLC)
   - **negative/counterfactual** test (remove evidence → output changes / REVIEW / UNKNOWN)
4. Never cite finished PLC as a source.

## Anti-copy / negative-test philosophy

If deleting the evidence does not change a supposedly evidence-derived output, the output is not evidence-derived. Investigate.

Anti-copy checks also flag site-name production conditionals, finished-PLC-as-RUN paths, Safety membership without accepted class, and PROVEN claims without sources.
