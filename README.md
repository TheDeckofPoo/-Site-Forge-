# Site Forge

**RUN → Site Model → engineer correction → Rockwell L5X generation.**

Site Forge (repo folder: FortnaPlus) is an Electron dashboard plus Python engines that import Fortna FPC / SortPlus **RUN** archives, help an engineer correct the site model in Transport Build, and compile supported Rockwell Studio 5000 **L5X** packages.

It does **not** launch Studio 5000. You open the generated L5X yourself.

---

## Main workflow

```
Import RUN
    ↓
Auto Build
    ↓
Review / Correct
    ↓
Apply to Autogen
    ↓
Build PLC
```

| Step | Where | What happens |
|------|-------|----------------|
| **Import RUN** | I/O & Prints | Extract `.tar.gz` → `workspace/active/RUN` |
| **Auto Build** | Transport Build | Place conveyors from RUN geometry (first-pass layout) |
| **Review / Correct** | Transport Build | Fix topology, Area, ES Zone, PE roles |
| **Apply to Autogen** | Transport Build | Persist approved Site Model into `workspace/autogen_workbook.json` |
| **Build PLC** | PLC Autogen | Export L5X package under `exports/autogen/` |

**Complexity stays inside Site Forge.** New compiler packs (VFD, encoder, sawtooth) do **not** add top-level buttons. Prefer inspector context and **Advanced / Evidence**.

See `docs/UX_PRINCIPLES.md`.

---

## What a RUN archive means

A RUN `.tar.gz` represents a **Fortna machine / control scope** (its ASC tables, EIP map, and related configuration).

- A **site** may contain **multiple** RUN archives (e.g. area masters CP2 / CP4 / CP5).
- Each import is associated with the scope evidenced by **that** archive (`project.cfg`, `Machine.asc`, controller overlays such as `*.asc.ORNCCP4`).
- Site Forge **discovers** scope from the archive — it does **not** assume one fixed site↔controller relationship, and it does **not** mean “one tar = one L5X” as a universal rule.

Source of truth for generation:

1. **Current RUN**
2. **Engineer Site Forge edits**
3. **Approved generic L5X libraries**

Finished / gold PLC files are **validation oracles only** — never generation input. See `docs/SOURCE_OF_TRUTH_POLICY.md`.

---

## Install & launch

**Prerequisites:** Windows, Git, Node.js/npm, Python 3.x.

```bat
cd C:\dev\worktree\FortnaPlus\desktop
npm install
```

Daily: run **`desktop\Launch-SiteForge.bat`**.

Do not open `dashboard\index.html` in a bare browser — Electron preload (`window.fortnaAPI`) is required.

---

## Repository map (short)

```
dashboard/     UI (Transport Build, Autogen, I/O)
desktop/       Electron shell + IPC
tools/scripts/ Python engines (autogen, discovery, layout, …)
tools/libraries/  Generic O'Reilly L5X + program packs
workspace/     Active RUN + workbook (do not commit extracts)
exports/       Generated L5X / reports / discovery packs
docs/          Engineering policy + pass notes
```

| Stable path | Role |
|-------------|------|
| `workspace/active/RUN` | Current RUN extract (wiped on re-import) |
| `workspace/autogen_workbook.json` | Engineer Autogen workbook (outside `active/`) |
| `workspace/inbox/` | Drop `.tar.gz` archives |
| `tools/libraries/OReilly_Library_v3.L5X` | Default AOI library |

---

## Tabs (normal use)

| Tab | Role |
|-----|------|
| **I/O & Prints** | Import RUN, inspect I/O |
| **Transport Build** | Site model: areas, conveyors, PE, merges → Apply |
| **PLC Autogen** | Build PLC (Export L5X) |
| **Docs / Workspace** | Search docs, paths, meta |

Sorter / Sawtooth / Ignition / Factory I/O / Site Twin tooling may still exist in code or under **Advanced** — they are **not** the primary workflow. Compiler features (e.g. CP4 sawtooth) are driven by RUN recognition + Autogen packs, not separate “Build Sawtooth” buttons.

---

## Multi-controller sites

Import each machine’s RUN when you work that scope. Discover controller ownership from RUN evidence (Machine_Name, EIP, PE/motor/VFD links). Do not invent Area/ES names from finished PLCs.

Engineering pass notes (CP2/CP4, layout research, gold inventories) live under `docs/` — not in this README.

---

## Key docs

| Doc | Topic |
|-----|--------|
| `docs/SOURCE_OF_TRUTH_POLICY.md` | Generation vs validation firewall |
| `docs/UX_PRINCIPLES.md` | Simple-by-default UI rules |
| `docs/INTEGRATION_CHECKPOINT.md` | Current integration lineage & tests |
| `docs/RUN_GEOMETRY_CALIBRATION.md` | RUN X/Y = infeed model |
| `docs/CP4_COMPILER_PASS2.md` | CP4 generation status |

---

## License / internal use

Internal Fortna / LPS Engineering tooling. Treat RUN customer data and gold L5X libraries according to your site policies.
