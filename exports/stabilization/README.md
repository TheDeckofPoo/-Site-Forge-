# Stabilization / Offline Continuity Pack

**Purpose:** Preserve everything needed to resume Site Forge work **without chat history**.

**Branch:** `feature/plc2-transport-fidelity`  
**Handoff HEAD:** `928e77db97ea377d4e0e44e8330d338ef6bab7f1`  
**Lineage:** `928e77d` → `9866dfd` (docs) → `8231b5a` (partial-build) → `8d46fd2` (punch-list) → `58fb309` → `61c7949`

---

## Read in this order

1. **This file** — index
2. `partial_build_contract.md` — FOUND≠INCLUDED≠GENERATED (product law)
3. `../README.md` (repo root) — full Site Forge + handoff table
4. `../../docs/REGRESSION_MANIFEST.md` — accepted layers + test commands
5. Individual reports below as needed

---

## Artifacts in this folder

| File | Why it exists |
|------|----------------|
| `partial_build_contract.md` | Incremental commissioning rules; Compile Hub REVIEW ≠ block |
| `partial_build_acceptance.json` | Evidence from `test_partial_build_acceptance.py` |
| `area_inclusion_report.md` | `ORNCCP2_Area` + engineer Area `test1` — do not delete by name |
| `io_edit_persistence_checklist.md` | Hardware I/O alias Electron acceptance (REVIEW) |
| `l5x_hygiene_notes.md` | Structural hygiene + lettered collision candidates |
| `python_script_inventory.md` | Classification of `tools/scripts/*.py` |
| `python_script_inventory.json` | Machine-readable twin of inventory |
| `README.md` | This index |

---

## Related generated outputs (outside this folder)

| Path | Role |
|------|------|
| `exports/current/ORNCCP2.L5X` | Latest generated PLC2 |
| `exports/current/build_manifest.json` | Provenance + Safety `es_program` |
| `exports/current/autogen_input.json` | Effective Autogen input (INCLUDED conveyors) |
| `exports/current/LATEST.json` | Last export pointer |
| `workspace/autogen_workbook.json` | Engineer Safety/Transport workbook |

---

## Key product contracts (compressed)

### Partial build

```
RUN → FOUND → engineer config → INCLUDED → Autogen → GENERATED
```

- Unassigned equipment: **REVIEW REQUIRED**, not ERROR
- Build fails only for structural ERROR on **INCLUDED** / mandatory content
- Safety unassigned: never guess membership; never treat as SAFE

### Transport UI

- Area move must **not** re-layout unrelated conveyors (frozen presentation offsets)
- Hit targets must track visible geometry (CTM + live offsets)
- CURVE: UNKNOWN orientation → diagonal **symbol** (UI-only), conveyor visual weight

### I/O identity

- `M220_AUX` → `P220_MS.I.Auxiliary_Forward`
- `M220A_AUX` → `P220A_MS.I.Auxiliary_Forward`
- Never map bare `M{n}` onto lettered `P{n}A`

### Safety structure

- Program `ES` + task `P01_Safety_20ms` + `Main_Routine` shell allowed
- `Safe_Logic` / `Safe_PI` only when members proven/engineer-assigned
- Status: STRUCTURE READY · MEMBERSHIP REVIEW · COMMISSIONING READY = NO

---

## Recovery commands

```bat
cd C:\dev\worktree\FortnaPlus
git status -sb
git log -5 --oneline
python tools\scripts\test_partial_build_acceptance.py
python tools\scripts\fortna_autogen.py from-json exports\current\autogen_input.json --library tools\libraries\OReilly_Library_v3.L5X --out-dir exports\current
python tools\scripts\fortna_studio_preflight.py exports\current\ORNCCP2.L5X
```

Launch app: `desktop\Launch-SiteForge.bat`

---

## Do not

- Rewrite CP1–CP4
- Delete/consolidate Python scripts from the inventory
- Commit mass `exports/` deletions present as dirty worktree noise
- Invent Safety membership
- Start SawMerge / Sorter as the next automatic checkpoint
