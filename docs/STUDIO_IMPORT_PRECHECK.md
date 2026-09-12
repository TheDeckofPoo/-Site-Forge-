# Studio Import Precheck (Static)

**Tool:** `tools/scripts/fortna_studio_preflight.py`  
**Pack:** `exports/studio-validation/`  
**Hardening reports:** `exports/integration-hardening/STUDIO_IMPORT_PRECHECK_*.md`

---

## What it is

A **static** L5X preflight that runs without Studio 5000. It catches structural problems before a human opens the candidate in Studio.

```text
python tools/scripts/fortna_studio_preflight.py <candidate.L5X> \
  --out-json exports/studio-validation/<name>.json \
  --out-md   exports/studio-validation/<name>.md
```

---

## What it checks

| Check | Severity |
|-------|----------|
| File exists / XML parses | ERROR |
| `Controller` present with `Name` | ERROR |
| `ProcessorType` present | WARNING |
| Duplicate tag names | ERROR |
| Invalid Rockwell tag names | ERROR |
| Programs missing a `Main` routine | WARNING |
| JSR targets not found among routines | WARNING |
| AOI references without definitions block | WARNING |
| Missing `DataTypes` block | WARNING |
| Module presence (informational) | INFO |

`ok: true` means **zero ERROR** issues. Warnings do not fail the static gate.

---

## What it does **not** claim

- **Not** Studio 5000 import PASS
- **Not** download / online verify
- **Not** rung semantics / AOI behavior correctness
- **Not** I/O module hardware match
- **Not** subsystem completeness (Sorter / WCS / Safety)

`studio_import_claimed` is always `false` in preflight output. Curtis (or another engineer) must import each candidate and record results in `exports/studio-validation/validation_checklist.md`.

---

## Validation pack

| Artifact | Role |
|----------|------|
| `exports/studio-validation/*.L5X` | Candidate controllers staged for manual import |
| `exports/studio-validation/SHA256_MANIFEST.json` | Digests of staged files |
| `exports/studio-validation/*_STUDIO_IMPORT_PRECHECK.md` | Per-candidate static reports |
| `exports/studio-validation/validation_checklist.md` | Manual Studio results (engineer fills) |

Static precheck ready ≠ Studio PASS. Do not promote on precheck alone.
