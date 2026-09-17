# Site Forge

**Import RUN → discover site content → engineer corrects → Build PLC.**

Site Forge (repo folder: FortnaPlus) is an Electron app plus Python engines for Fortna FPC / SortPlus **RUN** archives. It auto-discovers transport, drives, sensors, and supported subsystems (Sawtooth, Sorter when evidenced), lets the engineer fix the uncertain remainder, and compiles **supported** Rockwell Studio 5000 **L5X**.

It does **not** launch Studio 5000.

---

## OFFLINE HANDOFF (read this first if resuming without Curtis)

| Item | Value |
|------|--------|
| **Branch** | `feature/plc2-transport-fidelity` |
| **HEAD (as of this handoff)** | `928e77db97ea377d4e0e44e8330d338ef6bab7f1` |
| **Docs pack commit** | `9866dfdeb32f174de7a0fd557f3ac5f5c700ad32` |
| **Partial-build commit** | `8231b5a741d8ed0b7658068710c0fdecc55ed3c2` |
| **Remote** | `origin/feature/plc2-transport-fidelity` (also mirrored at TheDeckofPoo/-Site-Forge-) |
| **Worktree** | `C:\Dev\worktree\FortnaPlus` |

### Recent commits (stabilization lineage)

| SHA | Summary |
|-----|---------|
| `9866dfd` | **Offline README handoff** — continuity pack + updated READMEs |
| `8231b5a` | **Partial build contract** — FOUND≠INCLUDED≠GENERATED; REVIEW does not block Export |
| `8d46fd2` | Punch-list: layout freeze, CURVE symbol, M220 identity, Safety preflight |
| `58fb309` | Transport hit geometry + Safety ES shell + curve weight |
| `61c7949` | Straight CURVE placeholders + universal body/label selection |
| `9ec550a` | CP5A decoder → RUN import + Transportation |
| `e426152` / `d43abd6` / `83dc7bb` / `bedcb7a` | CP4 / CP3 / CP2 / CP1 (frozen — do not rewrite) |

### Continuity pack (do not delete)

Everything an agent needs to re-read without chat history:

| Path | Contents |
|------|----------|
| **`exports/stabilization/README.md`** | Index of this offline pack |
| `exports/stabilization/partial_build_contract.md` | Incremental commissioning rules |
| `exports/stabilization/partial_build_acceptance.json` | Last partial-build fixture evidence |
| `exports/stabilization/area_inclusion_report.md` | Why `test1` Area is included |
| `exports/stabilization/io_edit_persistence_checklist.md` | I/O alias Electron checklist |
| `exports/stabilization/l5x_hygiene_notes.md` | Output hygiene + lettered collision candidates |
| `exports/stabilization/python_script_inventory.md` (+ `.json`) | 227 scripts classified — **inventory only, do not clean up** |
| `docs/REGRESSION_MANIFEST.md` | CP1–CP5A + critical fixtures + test commands |
| `docs/COMPILE_HUB_READINESS.md` | Hub status vocabulary (see also partial-build update) |

### Current generated PLC (PLC2)

| Path | Notes |
|------|--------|
| `exports/current/ORNCCP2.L5X` | Latest from-json / generate output |
| `exports/current/ORNCCP2_2026_09_17_1106.L5X` | Curtis acceptance build (pre-shell era) |
| `exports/current/build_manifest.json` | Provenance + `es_program` status |
| `exports/current/autogen_input.json` | Effective input used for last generate |
| `exports/current/LATEST.json` | Pointer to last export |

### Workspace state Curtis left

| Path | Notes |
|------|--------|
| `workspace/autogen_workbook.json` | Engineer workbook (Safety Build applied; Transport may be in localStorage) |
| `workspace/active/RUN` | May be **missing** offline — re-import RUN tar.gz if needed |
| `workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X` | Finished PLC **validation oracle only** |

**Uncommitted noise:** the worktree may show mass `exports/**` deletions and untracked POC folders. Those were **intentionally left unstaged** (Gate I — no cleanup). Do **not** commit mass deletes. Prefer `git checkout -- exports/...` only if recovering tracked files.

---

## Normal workflow

```
Import RUN
     ↓
Discover site / machine content   (automatic on import / Auto Build)
     ↓
Auto-populate engineering editors
     ↓
Review / Correct / Include–Exclude   ← PARTIAL builds are first-class
     ↓
Apply to canonical Site Model      ← only INCLUDED objects feed Autogen
     ↓
Build PLC                          ← REVIEW REQUIRED does NOT block
```

| Step | What the engineer sees |
|------|-------------------------|
| **Import RUN** | Drop `.tar.gz` → extract + **unified discovery** |
| **Editors** | Transport / Sawtooth / Sorter / Safety / Hardware views |
| **Review** | Fix Area, ES zone, topology, PE roles; leave the rest **FOUND / UNASSIGNED** |
| **Apply** | Persist engineer overrides into the site workbook / model |
| **Build PLC** | Generate only **INCLUDED** content; soft-review the rest |

**Product rule:** Site Forge should do **80–95%** of data entry. The engineer fixes the uncertain **5–20%**. Site Forge must **never guess** that remainder.

**Partial build rule (mandatory):**

```
FOUND ≠ CONFIGURED ≠ INCLUDED ≠ GENERATED

UNASSIGNED ≠ ERROR ≠ ACTIVE ≠ INCLUDED ≠ GENERATED ≠ SAFE
```

- Unassigned Transport / Safety equipment is **REVIEW REQUIRED**, not a fatal build error.
- Compile Hub: **ERROR** blocks Export; **REVIEW REQUIRED** / **NOT DETECTED** do **not**.
- Autogen consumes the **effective INCLUDED model** (Transport Apply + workbook `include=true`), not every RUN discovery row.
- Safety: never invent zone membership; fail-safe ES shell OK; `COMMISSIONING READY = NO` until members assigned.

See `exports/stabilization/partial_build_contract.md`.

**UX rule:** Complexity stays inside Site Forge — no top-level “Discover Sawtooth / Build VFD / Build Sorter” button farms. See `docs/UX_PRINCIPLES.md`.

---

## What a RUN means

A RUN archive is a **machine / control scope**, not “one tar = one L5X” by fiat.

- A site may have **multiple** RUNs (e.g. CP2 / CP4 / CP5).
- Discovery uses controller-scoped tables (`*.asc.<CONTROLLER>`) with documented precedence (`docs/RUN_TABLE_PRECEDENCE.md`).
- **Record exists ≠ generate.** Stale / historical ASC rows stay visible as AVAILABLE or EXCLUDED.

Generation inputs only:

1. Current RUN  
2. Engineer Site Forge edits (overrides) — **INCLUDED** set  
3. Approved generic L5X libraries  

Finished / gold PLCs are **validation oracles only** — never generation input (`docs/SOURCE_OF_TRUTH_POLICY.md`).

---

## Subsystems

| Subsystem | On import | Partial build |
|-----------|-----------|---------------|
| **Transport** | Auto-populated from RUN geometry + relationships | Apply a small Area; leave rest FOUND |
| **Safety** | Devices discovered into Safety Build | Unassigned → REVIEW; ES shell fail-safe |
| **Sawtooth** | Auto-detected when evidenced | FOUND ≠ INCLUDED — does not block Build |
| **Sorter** | Auto-detected when evidenced | Same — Apply to include |

Unsupported behaviors stay marked **GENERATION NOT YET SUPPORTED** / **CONFIGURATION_REQUIRED**.

### Knowledge-executable discovery (SiteModel V2)

On import / Auto Build, Site Forge loads FortnaPlus table semantics (docs = meaning, RUN = facts) and enriches a **SiteModel V2**. See `docs/SITEMODEL_V2.md` and `docs/INTEGRATION_READINESS.md`.

**Do not rewrite CP1–CP4.** Decoder archaeology is frozen at the SHAs in `docs/REGRESSION_MANIFEST.md`.

---

## Critical identity / UI contracts (recent)

| Topic | Contract |
|-------|----------|
| Transport hit geometry | One authoritative geometry after Area moves; CTM pick + frozen presentation offsets |
| Area move | Model change + redraw — **not** global re-layout (PL-1) |
| CURVE | Type PROVEN; turn orientation UNKNOWN; diagonal UI symbol only |
| I/O | `M220_AUX` ≠ `M220A_AUX`; never strip alphabetic suffix for ownership |
| I/O edit | Physical endpoint immutable; alias survives Enter/Tab/blur/refresh (Electron checklist REVIEW) |
| Safety shell | Program `ES` + `P01_Safety_20ms` + Main_Routine NOP; no invented members |

---

## Install & launch

**Prerequisites:** Windows, Git, Node.js/npm, Python 3.x.

```bat
cd C:\dev\worktree\FortnaPlus\desktop
npm install
```

Daily: **`desktop\Launch-SiteForge.bat`**.

Requires Electron preload (`window.fortnaAPI`) — do not open `dashboard/index.html` bare.

---

## Permanent regression commands

```bat
cd C:\dev\worktree\FortnaPlus
python tools\scripts\test_partial_build_acceptance.py
python tools\scripts\test_transport_hit_geometry.py
python tools\scripts\test_transport_area_move_positions.py
python tools\scripts\test_m220_aux_identity.py
python tools\scripts\test_es_compiler.py
python tools\scripts\test_hardware_io_overrides.py
python tools\scripts\test_iomap_duplicate_output_ownership.py
python tools\scripts\fortna_studio_preflight.py exports\current\ORNCCP2.L5X
```

Full index: `docs/REGRESSION_MANIFEST.md`.

Generate L5X from saved input (no live RUN required if `autogen_input.json` present):

```bat
python tools\scripts\fortna_autogen.py from-json exports\current\autogen_input.json --library tools\libraries\OReilly_Library_v3.L5X --out-dir exports\current
```

---

## Repository map

```
dashboard/                 UI (Transport, Safety, Hardware, Autogen, Compile Hub)
desktop/                   Electron + IPC
tools/scripts/             Discovery, semantics, compilers, tests
tools/libraries/           Generic Rockwell packs (OReilly_Library_v3.L5X)
workspace/                 Active RUN + workbook (local)
exports/current/           Engineer-facing L5X + manifest
exports/stabilization/     Offline continuity pack (this handoff)
docs/                      Policy + engineering models
```

| Path | Role |
|------|------|
| `workspace/active/RUN` | Current extract (wiped on re-import) |
| `workspace/autogen_workbook.json` | Engineer workbook (outside `active/`) |
| `exports/run-discovery/` | Canonical discovered site model |
| `exports/stabilization/` | **Offline handoff artifacts** |
| `docs/REGRESSION_MANIFEST.md` | Accepted layers + fixtures |

---

## Key docs

| Doc | Topic |
|-----|--------|
| `exports/stabilization/README.md` | **Offline continuity index** |
| `exports/stabilization/partial_build_contract.md` | Incremental / partial Build PLC |
| `docs/REGRESSION_MANIFEST.md` | CP1–CP5A + tests |
| `docs/SOURCE_OF_TRUTH_POLICY.md` | Generation vs validation firewall |
| `docs/UX_PRINCIPLES.md` | Simple by default |
| `docs/RUN_DISCOVERY_MODEL.md` | Canonical discovery model |
| `docs/SITEMODEL_V2.md` | SiteModel V2 |
| `docs/COMPILE_HUB_READINESS.md` | Hub readiness vocabulary |
| `docs/PLC2_IO_TRUTH_MODEL.md` | I/O identity truth |
| `tools/scripts/README_PARSERS.md` | Parser / compiler inventory |
| `exports/README_WHICH_FILES.md` | Which L5X to open in Studio |

---

## Non-goals / do-not-touch (current checkpoint)

- Do **not** rewrite CP1–CP4
- Do **not** clean up / delete / consolidate the 50+ Python scripts (inventory only)
- Do **not** start SawMerge or Sorter integration checkpoints
- Do **not** invent Safety membership
- Do **not** equate FOUND → GENERATED

---

## License / internal use

Internal Fortna / LPS Engineering tooling. Treat customer RUN data and gold libraries per site policy.
