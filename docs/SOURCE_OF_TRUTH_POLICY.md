# Site Forge — Source of Truth Policy

**Status:** Binding for production generation and acceptance scoring.  
**Effective:** 2026-09-12

---

## Purpose

Prevent false progress.

A finished / reference PLC must never be used to complete missing production inputs.
Known-good L5X files are **post-generation validation oracles only**.

---

## Allowed production inputs

Production Site Forge may use:

1. **Imported RUN / `.tar.gz` data**
2. **Engineer-entered Transport Build data**
3. **Approved generic equipment / pattern libraries**
4. **Published / documented equipment rules**
5. **Explicit configuration supplied by the engineer**

---

## Reference PLC role

A finished / reference PLC may be used **ONLY** as:

> **POST-GENERATION VALIDATION ORACLE**

It must **not**:

- populate the workbook
- create conveyors
- assign area
- assign safety zone
- assign downstream
- assign PE
- identify motors
- classify VFD / contactors
- create merges
- repair topology
- supply missing tags
- change generated logic

The reference PLC must **not** influence generation before the generated L5X is complete.

Engineering PDF prints may be used for **human** acceptance / spot-checking unless a future explicitly approved print-import feature is under test.

---

## Hard separation (validation barrier)

```
INPUT SIDE
  RUN
  engineer configuration
  generic libraries
        ↓
     GENERATE
        ↓
  generated model / workbook / L5X
        ↓
-------- VALIDATION BARRIER --------
        ↓
  reference finished PLC
  prints
  comparator
```

**No data may travel upward across that validation barrier.**

Tests and tools must keep this separation visible:

| Layer | May read | Must not write into generation |
|-------|----------|--------------------------------|
| Input / Generate | RUN, engineer config, libraries | Reference L5X, print OCR as production fill |
| Validation | Generated artifacts + reference L5X | Workbook, Transport graph, Autogen input |

---

## Provenance values

Important generated / configured values should carry provenance where practical:

| Code | Meaning |
|------|---------|
| `RUN` | Taken from imported RUN / ASC tables |
| `ENGINEER` | Explicitly set in Transport Build / workbook UI |
| `INFERRED_GEOMETRY` | Derived from RUN geometry (anchors, mate candidates) under documented assumptions |
| `GENERIC_PATTERN` | From approved library / published pattern |
| `DEFAULT` | Explicit product default (must be documented) |
| `UNKNOWN` | Not supported by evidence |

If a value cannot be supported, leave it **`UNKNOWN`** or mark **`CONFIGURATION REQUIRED`**.

**Do not silently manufacture a plausible answer.**

---

## Evidence hierarchy

Prefer (highest → lowest):

1. Runtime generated workbook / L5X from RUN + engineer config
2. Structural comparison to reference PLC (**after** generation)
3. RUN table dumps / geometry audits
4. Unit tests of parsers and pure helpers
5. Source-string existence checks

Never treat “reference-seeded” plumbing tests as end-to-end accuracy.

---

## Autogen / Transport implications

- Autogen area / safety / downstream / PE / merge inputs must come from workbook / Transport / RUN — never from finished L5X.
- Transport **Auto Build From RUN** may use RUN geometry and RUN tables only.
- Comparator tools (`fortna_l5x_compare.py`) are validation-side and must not feed generation.

---

## Regression requirement

Generation output for Auto Build (and Autogen where practical) must be **identical** whether a finished Greensboro L5X is:

- present
- absent
- renamed

If hiding the finished PLC changes generation, the test **FAILS**.

---

## Authority

The architecture / review agent is the acceptance authority for whether a change respects this policy.
Curtis provides field acceptance; GitHub committed source is the shared implementation truth.
