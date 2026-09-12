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
| **Transport** | Auto-populated from RUN geometry + relationships; PE roles + motor chains from knowledge |
| **Sawtooth** | Auto-detected from SawLane/SawMerge (etc.); editor V2 filled from evidence |
| **Sorter** | Auto-detected when tables/evidence exist; **proven leaves only** — see `docs/SORTER_COMPILER_MODEL.md` |

Unsupported behaviors stay marked **GENERATION NOT YET SUPPORTED** / **CONFIGURATION_REQUIRED** (e.g. full Tracking/WCS, divert maps, gold `Sorter_Track` clones).

### Knowledge-executable discovery (SiteModel V2)

On import / Auto Build, Site Forge loads FortnaPlus table semantics (docs = meaning, RUN = facts) and enriches a **SiteModel V2**:

- Distinct operational groups (Engineering Area ≠ Jam ≠ EStop ≠ StartStop)
- Area rename propagates to equipment / Autogen L5X tags — **not** to jam / ES / SS zones
- PE roles from Jamcheck / Fullline / Fulljam / SawLane evidence
- Motor chains ordered from `Mtrchain` relationships
- Editors V2 auto-populate Transport / Sawtooth / Sorter from the same model
- Inclusion reasons + supersession signals for Review

See `docs/SITEMODEL_V2.md` and `docs/INTEGRATION_READINESS.md`.

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
| `docs/SITEMODEL_V2.md` | SiteModel V2 shape (zones, PE roles, chains, editors) |
| `docs/INTEGRATION_READINESS.md` | Knowledge-compiler promote-or-not status |
| `docs/RUN_TABLE_PRECEDENCE.md` | Base vs controller ASC overlays |
| `docs/FPC_TRAINING_DOCUMENT_INDEX.md` | FortnaPlus training corpus index |
| `docs/FORTNAPLUS_TABLE_REFERENCE.md` | ASC table semantics knowledge base |
| `docs/TRANSPORT_FREEZE_GATE.md` | Transport demo-ready freeze |
| `docs/SAWTOOTH_CONTROL_MODEL.md` | Sawtooth semantics |
| `docs/SORTER_COMPILER_MODEL.md` | Sorter discovery / support boundary |
| `docs/SORTER_GENERATION_ROADMAP.md` | What is / is not generatable for sorter |
| `docs/UI_STATUS_SUMMARY.md` | `ui_status_summary` JSON for status cards |

Training documents under `docs/training/` inform **generic** FortnaPlus table semantics. They do **not** replace the current RUN as site truth, and finished PLCs remain validation-only.

---

## License / internal use

Internal Fortna / LPS Engineering tooling. Treat customer RUN data and gold libraries per site policy.
