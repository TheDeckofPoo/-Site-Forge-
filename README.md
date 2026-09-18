# Site Forge

**Import RUN → discover site content → engineer corrects → Build PLC.**

Site Forge (repo: FortnaPlus) is an Electron app plus Python engines for Fortna FPC / SortPlus **RUN** archives. It discovers transport, I/O, Safety, Sorter (when evidenced), and other subsystems; lets the engineer fix the uncertain remainder; and compiles supported Rockwell Studio 5000 **L5X**.

It does **not** launch Studio 5000.

---

## Start here (evidence refresh)

| Doc | Use |
|-----|-----|
| **[`docs/evidence/README.md`](docs/evidence/README.md)** | Primary evidence index |
| **[`docs/evidence/PROJECT_HANDOFF.md`](docs/evidence/PROJECT_HANDOFF.md)** | 5–10 minute orientation |
| [`docs/evidence/ACCEPTED_CHECKPOINTS.md`](docs/evidence/ACCEPTED_CHECKPOINTS.md) | Frozen / accepted registry |
| [`docs/RUN_EVIDENCE_AUTHORITY.md`](docs/RUN_EVIDENCE_AUTHORITY.md) | What evidence owns which fact |
| [`docs/AI_BUILD_PROTOCOL.md`](docs/AI_BUILD_PROTOCOL.md) | Curtis ↔ Review AI ↔ Coding AI |
| [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) | Doc status map |

**Verify tip:** `git rev-parse HEAD` on branch `feature/plc2-transport-fidelity`

---

## Architecture

```
RUN (site evidence)
  ↓
FortnaPlus semantics (.mnu / schema) + CP1–CP4 decoder (FROZEN)
  ↓
Canonical models (Transport / Safety / Sorter / Hardware I/O / …)
  ↓
Engineer review · Include/Exclude · Apply
  ↓
Autogen effective workbook
  ↓
PLC compiler → single L5X
```

| Source | Role |
|--------|------|
| RUN | Site configuration evidence |
| .mnu / FortnaPlus runtime | Semantic meaning |
| Engineer Apply | Effective project configuration |
| Finished PLC | **Validation oracle only** — never discovery/generation input |
| Docs | Index of accepted proofs — never outranks raw evidence |

**Partial builds are first-class:** `FOUND ≠ INCLUDED ≠ GENERATED`. Unassigned equipment is REVIEW, not an automatic fatal build error.

---

## Workflows

### Brownfield (typical)

1. I/O & Prints — Load RUN `.tar.gz`  
2. Review Hardware/I/O, Transportation, Safety, Sorter as applicable  
3. Apply each subsystem  
4. PLC Autogen — Export L5X Package  

### Greenfield

Configure only what you need; Build what is INCLUDED; leave the rest FOUND/UNASSIGNED.

---

## Subsystems (maturity snapshot)

| Subsystem | Maturity |
|-----------|----------|
| **I/O & Prints** | Discovery + engineer aliases; physical endpoint pipeline; dup-OTE protection |
| **Transportation** | Freeze regression PASS (ORNCCP2 four merges); selection/handoff solid |
| **Safety** | Discovery + zone membership + ES architecture; unassigned = REVIEW |
| **Sorter** | Blind RUN discovery + UI foundation; **PLC generation NOT STARTED** |
| **Sawtooth / Merge** | Existing packs; preserve behavior |
| **PLC Autogen** | Single L5X; Compile Hub; partial build allowed |

Details: subsystem baselines under `docs/evidence/`.

---

## Evidence authority (no speculation)

Confidence: **PROVEN · DERIVED · ENGINEER_ASSIGNED · REVIEW_REQUIRED · UNKNOWN**  
Never: GUESSED / ASSUMED / PROBABLY.

File open order (`Table.rom.<MACHINE>` … `Table.asc`) ≠ semantic authority for every fact.  
See `docs/RUN_EVIDENCE_AUTHORITY.md`.

---

## Frozen decoder layers

| Layer | SHA (short) | Status |
|-------|-------------|--------|
| CP1 | `bedcb7a` | **FROZEN** |
| CP2 | `83dc7bb` | **FROZEN** |
| CP3 | `d43abd6` | **FROZEN** |
| CP4 | `e426152` | **FROZEN** |

Do not rewrite CP1–CP4. Registry: `docs/evidence/ACCEPTED_CHECKPOINTS.md`.

---

## Development / run locally

**Prerequisites:** Windows, Git, Node.js/npm, Python 3.x.

```bat
cd C:\dev\worktree\FortnaPlus\desktop
npm install
```

Daily launch: **`desktop\Launch-SiteForge.bat`** (requires Electron preload — do not open `dashboard/index.html` bare).

---

## Testing (representative)

```bat
python tools\scripts\test_transportation_freeze.py
python tools\scripts\test_live_canonical_handoff.py
python tools\scripts\test_safety_membership_handoff.py
python tools\scripts\test_es_compiler.py
python tools\scripts\test_m220_aux_identity.py
python tools\scripts\test_plc5_io_endpoint_collision.py
python tools\scripts\test_plc5_sorter_discovery.py
python tools\scripts\test_cp4_merge.py
```

Full index: `docs/REGRESSION_MANIFEST.md` · baselines: `config/evidence_baselines/`

---

## Repository map

```
dashboard/          UI (Transport, Safety, Hardware, Sorter, Autogen)
desktop/            Electron + IPC
tools/scripts/      Discovery, compilers, tests
tools/libraries/    Generic Rockwell packs
workspace/          Active RUN + workbook (local; not a substitute for evidence docs)
exports/current/    Engineer-facing L5X
exports/stabilization/  Acceptance artifacts
docs/evidence/      Authoritative evidence index (this product’s memory)
config/evidence_baselines/  Machine-readable acceptance expectations
```

---

## AI collaboration

See `docs/AI_BUILD_PROTOCOL.md`. GitHub is the shared source of truth between Review AI and Coding AI.

---

## License / internal use

Internal Fortna / LPS Engineering tooling. Treat customer RUN data and gold libraries per site policy.
