# Site Forge

**Import RUN → discover site content → engineer corrects → Build PLC.**

Site Forge (repo folder: FortnaPlus) is an Electron app plus Python engines for Fortna FPC / SortPlus **RUN** archives. It auto-discovers transport, drives, sensors, and supported subsystems (Sawtooth, Sorter when evidenced), lets the engineer fix the uncertain remainder, and compiles **supported** Rockwell Studio 5000 **L5X**.

It does **not** launch Studio 5000.

---

## Normal workflow

```
Import RUN
     ↓
Discover site / machine content   (automatic on import / Auto Build)
     ↓
Auto-populate engineering editors
     ↓
Review / Correct / Include–Exclude
     ↓
Apply to canonical Site Model
     ↓
Build PLC
```

| Step | What the engineer sees |
|------|-------------------------|
| **Import RUN** | Drop `.tar.gz` → extract + **unified discovery** |
| **Editors** | Transport / Sawtooth / Sorter views of the **same** canonical model |
| **Review** | Fix Area, ES zone, topology, PE roles; move INCLUDED ↔ AVAILABLE ↔ EXCLUDED |
| **Apply** | Persist engineer overrides into the site workbook / model |
| **Build PLC** | Generate only what evidence + libraries support |

**Product rule:** Site Forge should do **80–95%** of data entry. The engineer fixes the uncertain **5–20%**. Site Forge must **never guess** that remainder.

**UX rule:** Complexity stays inside Site Forge — no top-level “Discover Sawtooth / Build VFD / Build Sorter” button farms. See `docs/UX_PRINCIPLES.md`.

---

## What a RUN means

A RUN archive is a **machine / control scope**, not “one tar = one L5X” by fiat.

- A site may have **multiple** RUNs (e.g. CP2 / CP4 / CP5).
- Discovery uses controller-scoped tables (`*.asc.<CONTROLLER>`) with documented precedence (`docs/RUN_TABLE_PRECEDENCE.md`).
- **Record exists ≠ generate.** Stale / historical ASC rows stay visible as AVAILABLE or EXCLUDED.

Generation inputs only:

1. Current RUN  
2. Engineer Site Forge edits (overrides)  
3. Approved generic L5X libraries  

Finished / gold PLCs are **validation oracles only** — never generation input (`docs/SOURCE_OF_TRUTH_POLICY.md`).

---

## Subsystems

| Subsystem | On import |
|-----------|-----------|
| **Transport** | Auto-populated from RUN geometry + relationships |
| **Sawtooth** | Auto-detected from SawLane/SawMerge (etc.); editor filled from evidence |
| **Sorter** | Auto-detected when tables/evidence exist; generation only where supported — see `docs/SORTER_COMPILER_MODEL.md` |

Unsupported behaviors stay marked **GENERATION NOT YET SUPPORTED** (e.g. full Tracking/WCS until the support matrix says otherwise).

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

## Repository map

```
dashboard/        UI editors (Transport, Autogen, …)
desktop/          Electron + IPC
tools/scripts/    Discovery, semantics, compilers
tools/libraries/  Generic Rockwell packs
workspace/        Active RUN + workbook (local)
exports/          Discovery packs, L5X, research
docs/             Policy + engineering models
```

| Path | Role |
|------|------|
| `workspace/active/RUN` | Current extract (wiped on re-import) |
| `workspace/autogen_workbook.json` | Engineer workbook (outside `active/`) |
| `exports/run-discovery/` | Canonical discovered site model |
| `docs/RUN_DISCOVERY_MODEL.md` | SiteModel / activity / overrides |

---

## Key docs

| Doc | Topic |
|-----|--------|
| `docs/SOURCE_OF_TRUTH_POLICY.md` | Generation vs validation firewall |
| `docs/UX_PRINCIPLES.md` | Simple by default |
| `docs/RUN_DISCOVERY_MODEL.md` | Canonical discovery model |
| `docs/RUN_TABLE_PRECEDENCE.md` | Base vs controller ASC overlays |
| `docs/TRANSPORT_FREEZE_GATE.md` | Transport demo-ready freeze |
| `docs/SAWTOOTH_CONTROL_MODEL.md` | Sawtooth semantics |
| `docs/SORTER_COMPILER_MODEL.md` | Sorter discovery / support boundary |

---

## License / internal use

Internal Fortna / LPS Engineering tooling. Treat customer RUN data and gold libraries per site policy.
