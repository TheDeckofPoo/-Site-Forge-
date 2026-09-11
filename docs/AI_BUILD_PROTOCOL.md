# Site Forge AI Build Protocol

This document defines how Site Forge development is coordinated between:

```
Curtis
  ↓
Architecture / Review AI
  ↓
GitHub
  ↓
Local Coding AI
  ↓
GitHub PR
  ↓
Architecture / Review AI
  ↓
Curtis acceptance
```

The goal is to stop manually copying large prompts/results between the local coding AI and ChatGPT.

**GitHub is the shared source of truth.**

---

## Roles

### Product owner / field acceptance — Curtis

Defines what Site Forge needs to accomplish in real controls/recontrol work.

Provides:

- workflow requirements
- field observations
- screenshots
- RUN archives
- prints/reference material
- Studio 5000 observations
- usability feedback
- final acceptance

Curtis is not responsible for translating every request into code architecture.

### Architecture / review agent

Responsible for:

- understanding the requested workflow
- inspecting the current GitHub source
- defining implementation boundaries
- writing acceptance criteria
- reviewing PRs/diffs
- validating architecture
- reviewing tests
- checking workbook/L5X evidence
- comparing against known-good projects
- issuing correction tasks
- approving engineering checkpoints

This agent should prefer reviewing **actual committed source** over local-AI summaries.

### Local coding AI

Responsible for implementation.

For each assigned build task:

1. read the full task/spec
2. inspect existing implementation
3. implement only requested scope
4. preserve existing contracts unless explicitly changed
5. run existing regression tests
6. add appropriate new tests
7. generate runtime evidence
8. push changes to a feature branch
9. create/update a PR
10. **stop for review**

The local coding AI must **not** automatically begin unrelated improvements after completing the requested task.

---

## Git workflow

`main` is the stable baseline.

Significant work should occur on feature branches such as:

- `feature/transport-ux-pass2`
- `feature/transport-stabilization`
- `feature/l5x-comparator`
- `feature/autogen-merge3`
- `fix/transport-area-topology`

Do **not** develop substantial features directly on `main`.

Each coherent build pass gets its own branch or clearly scoped PR.

---

## Build task format

Development tasks should contain:

### TITLE

### WHY

What engineering problem are we solving?

### CURRENT BEHAVIOR

What Site Forge does today.

### REQUIRED BEHAVIOR

What it must do after this pass.

### ARCHITECTURAL BOUNDARIES

What must not be changed.

### ACCEPTANCE TESTS

Concrete behaviors proving the feature works.

### REGRESSION TESTS

Existing functionality that must remain working.

### DELIVERABLES

Code, reports, generated workbook/L5X, screenshots, etc.

### STOP CONDITION

Where the local AI must stop and request review.

---

## Local AI completion report

Every completed implementation must report:

- branch
- commit SHA
- PR number/link
- files changed
- architecture changes
- behavior implemented
- tests executed
- pass/fail results
- runtime tests performed
- workbook evidence where relevant
- generated L5X evidence where relevant
- known limitations
- assumptions made
- deferred work

Do **not** report simply:

> tests pass

Describe what the tests actually prove.

---

## Testing hierarchy

Site Forge uses multiple levels of testing.

### 1. Unit tests

Appropriate for:

- parsers
- normalization
- graph operations
- chain parsing
- deterministic helpers

These do **not** prove the complete application works.

### 2. Integration tests

Examples:

```
Transport topology → workbook
workbook → Autogen
Autogen → L5X
```

These are required for changes that affect generated PLC behavior.

### 3. Regression fixtures

Greensboro is a known-answer/reference project.

It may be used to compare:

- discovered conveyors
- areas
- PE assignments
- downstream relationships
- merge configuration
- Fast_Conv calls
- Slow logic
- generated program structure

**Greensboro must NOT be hardcoded into production behavior.**

Other sites may have completely different topology, equipment counts, area structure, and equipment combinations.

### 4. Real engineering acceptance

Curtis builds real sections of a site using Site Forge.

This validates:

- speed
- usability
- engineering correctness
- repetitive work
- missing workflow features
- field practicality

Automated tests cannot replace this stage.

---

## Evidence hierarchy

Prefer:

1. runtime behavior
2. generated workbook
3. generated L5X
4. structural comparison
5. actual application interaction

over:

- source string assertions
- existence-only tests
- mocked success
- static screenshots alone

Static tests are useful but must not be represented as runtime proof.

---

## Autogen safety boundary

Never silently invent PLC behavior for an unsupported equipment pattern.

Use:

- **CONFIRMED**
- **SUPPORTED**
- **CONFIGURATION REQUIRED**
- **GENERATION NOT YET SUPPORTED**

where appropriate.

A topology being representable does **not** mean its PLC generation pattern has been validated.

Example:

> 3:1 merge topology

may exist in Transport Build while PLC generation remains unsupported.

---

## Source-of-truth rules

GitHub committed source is the shared implementation truth.

Generated reports and local AI summaries are evidence, but they do not override the actual code.

For Autogen work, the chain should remain traceable:

```
RUN evidence
  ↓
workbook
  ↓
equipment/topology configuration
  ↓
Autogen
  ↓
generated L5X
```

---

## Review cycle

Normal development cycle:

```
Curtis gives goal
       ↓
architecture/review agent inspects repo
       ↓
task + acceptance criteria
       ↓
local AI implements
       ↓
local AI tests
       ↓
push branch / PR
       ↓
architecture/review agent reviews actual diff
       ↓
┌───────────────┴──────────────┐
│                              │
PASS                         REVISE
│                              │
merge/checkpoint          correction task
                               │
                               └→ same PR
```

Do not create a fresh implementation branch for every review correction unless necessary.

Prefer updating the same PR until the task is accepted.

---

## Review requests

Once a PR is ready, the local AI should stop.

Curtis can then tell the architecture/review agent simply:

> Site Forge PR #17 is ready for review.

or:

> Transport stabilization is pushed.

The review agent can inspect the repository/PR directly.

Large implementation reports do not need to be manually copied unless there is local-only runtime evidence not available through GitHub.

---

## Generated artifacts

Do not commit huge transient build outputs by default.

Keep useful small regression/evidence artifacts when appropriate.

Large:

- RUN extracts
- temporary L5X outputs
- `node_modules`
- temporary OCR
- temporary exports

should follow repository ignore/storage rules.

Known-good regression fixtures should be handled deliberately rather than casually committed.

---

## Stop rule

When a scoped task is complete:

1. test
2. document
3. commit
4. push
5. PR
6. **STOP**

Do not continue into the next feature merely because time remains.

Review determines the next task.

---

## Transport-specific notes (current baseline)

- Transport Build is a Fortna transportation topology editor, not a generic Node-RED clone.
- Physical topology is engineer-defined (often from weak PDF prints / site knowledge).
- **PDF parsing is not required** and must not be a dependency of Transport Build or Autogen.
- Canonical conveyor relationship: `node.downstream` (tag-based). Visual `wires[]` are area-scoped renderings.
- Area / ES Zone are organizational metadata — changing Area must not destroy topology.
- 3:1 merge topology may be represented; L5X generation remains **GENERATION NOT YET SUPPORTED** until a confirmed Fortna pattern exists.
