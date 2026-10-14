# Overnight toolbar audit — Phases 3 / 10 / 11

**Date:** 2026-10-14  
**Branch:** `demo/reno-ship-sorter-readiness`  
**Worktree:** `C:\dev\worktree\FortnaPlus-demo-ship`  
**Scope:** Visible engineering controls on Transport Build + I/O & Prints sticky toolbars.  
**Policy:** Do not delete capability casually. Normal engineer workflow → frequent actions only. Debug/layout under Advanced.

---

## Classification legend

| Class | Meaning |
|-------|---------|
| **PRIMARY** | Normal engineer path — stays on main toolbar |
| **SECONDARY** | Common but not every session — compact / menu |
| **ADVANCED** | Evidence, recovery, layout tools — Advanced menu |
| **DEVELOPER** | Diagnostics / shadow / geometry debug |
| **REDUNDANT** | Duplicate control; keep ID for wiring, hide or demote |

---

## Transport Build toolbar

### PRIMARY (main bar)

| ID | Label | Notes |
|----|-------|-------|
| `tb-area-select` | Area | Shows `Name (N)` conveyor count |
| `tb-area-new` | New | Create engineer Area; optional Safety default |
| `tb-area-delete-btn` | Delete | Delete active Area |
| `tb-connect-mode` | Connect | EXIT → ENTRY topology |
| `tb-fit` | Fit System | Presentation-only viewport |
| `tb-undo` / `tb-redo` | Undo / Redo | Edit recovery |
| `tb-apply-autogen` | Apply to Autogen | Persist topology / Area / Safety / PE |

### SECONDARY (main bar or Zoom/Fit ▾)

| ID | Label | Notes |
|----|-------|-------|
| `tb-style-raw` | Raw | RUN XY display |
| `tb-style-readable` | Readable | Display-only spread |
| `tb-fit-menu` | Zoom / Fit ▾ | Hosts zoom ±, Home, 100%, Fit variants |
| `tb-zoom-out` / `tb-zoom-in` | Zoom −/+ | **Moved into Zoom/Fit ▾** |
| `tb-home` / `tb-zoom-100` / `tb-zoom-reset` | Home / 100% | **Moved into Zoom/Fit ▾** |
| `tb-fit-visible` / `tb-fit-all` / `tb-fit-area` / `tb-fit-site` / `tb-fit-selection` | Fit variants | Already under Fit menu |
| `tb-active-run` / `tb-active-run-label` | Active RUN badge | Status only |

### ADVANCED (Advanced ▾)

| ID | Label | Notes |
|----|-------|-------|
| `tb-auto-build-run` | Rebuild Layout | **Moved off main bar** — recovery |
| `tb-rebuild-active-run` | Rebuild from Active RUN | **Moved off main bar** — recovery |
| `tb-adv-mode-detailed` / `tb-adv-mode-lite` | Detailed / Lite | Presentation |
| `tb-style-packed` | Packed Components | Display-only |
| `tb-geometry-mode` | Geometry authority | RUN / Override / Diagnostic |
| `tb-lane-separate` | Separate stacked labels | Presentation opt-in |
| `tb-show-relationships` | Show Relationships | Viz only |
| `tb-build-chain` | Build Chain… | Topology authoring |
| `tb-continue-run` | Continue Run | Topology authoring |
| `tb-auto-layout` | Auto Layout | Topology layout |
| `tb-auto-connect` | Auto Connect New | Opt-in |
| `tb-layer-*` | Display layers | Tags / motors / PE / … |
| `tb-area-rename` | Rename area | Infrequent |
| `tb-open-exports` | Open exports | File helper |

### DEVELOPER (Advanced ▾)

| ID | Label | Notes |
|----|-------|-------|
| `tb-advanced-debug` | Geometry debug view | Gate K |
| `tb-export-geom-diag` | Export geometry diagnostic | Report artifact |
| `tb-layer-physical` | Physical debug | Layer |
| `tb-wizard` | Wizard | Legacy helper |
| `tb-clear-canvas` | Clear canvas | Destructive recovery |

### REDUNDANT (kept for wiring / hidden)

| ID | Notes |
|----|-------|
| `tb-fit-system` | Same as Fit System — kept in Fit menu |
| `tb-center-selected` | Hidden duplicate of Fit Selection |
| `tb-mode-lite` / `tb-mode-detailed` | Hidden hosts; Advanced buttons drive mode |
| `tb-area-delete` | Alt of `tb-area-delete-btn` — Advanced only |
| `tb-ctx-*` / `tb-bulk-cp*` | Hidden Build Context / CP chrome (model retained) |

---

## I/O & Prints sticky toolbar

### PRIMARY

| ID | Label | Notes |
|----|-------|-------|
| `hw-io-panel-select` | Control Panel | Filter |
| `hw-io-rio-select` | Remote I/O | Filter |
| `btn-io-browse-run` | Load RUN | **Promoted leftmost in action cluster** |
| `btn-io-clear-run` | Clear | Clear active RUN |

### SECONDARY

| ID | Label | Notes |
|----|-------|-------|
| `btn-ai-io-analyze` | Analyze Remaining | Advisory AI after deterministic |
| `btn-relay-escalate-remaining` | Escalate to Relay | Normal escalation ladder |

### DEVELOPER (I/O Advanced ▾)

| ID | Label | Notes |
|----|-------|-------|
| `btn-relay-shadow-run` | Run Relay Shadow Review | **Moved under Advanced** — not normal path |
| `relay-shadow-status` | RELAY READY | Status host |
| `ai-io-auto-status` | AI status | Hidden until active |

### Already Advanced elsewhere (unchanged)

- Autogen pack overrides / workbook tables (`autogen-advanced-diagnostics`)
- Hub workbook tools
- Learning largest-tables details
- AI I/O Resolver “Use validated AI-derived I/O for build” (dev opt-in)

---

## Safety / Area UX note (Phase 3 cross-check)

Visible Safety zone summary now shows **CONVEYORS** and **Area** explicitly.  
Empty Area (`CONVEYORS: 0`) does not invent or push Safety onto transport motion in other Areas.

---

## Topology / inspector note (Phase 10 cross-check)

Selected conveyor inspector exposes canonical:

Upstream · Downstream · Equipment · Motor · PE roles · Area · Safety Zone · Status

Topology table columns: Conveyor · Upstream · Area · Downstream · Equipment · Motor · PE Roles · Safety Zone · Status · (PI Area hidden when redundant).

---

## Implementation summary

| Action | Result |
|--------|--------|
| Rebuild Layout / Rebuild Active RUN | Moved → Transport Advanced |
| Zoom ± / Home / 100% | Moved → Zoom / Fit ▾ |
| Lite Schematic main toggle | Demoted (Advanced still drives) |
| Relay Shadow Review | Moved → I/O Advanced ▾ |
| Capability removed? | **No** — all IDs retained |

---

## Known limits

- Keyboard zoom (Ctrl+wheel) remains primary zoom path; menu zoom is secondary.
- Bulk bar Align / Space / Auto Layout Selection stay hidden (presentation helpers).
- Full app chrome outside Transport + I/O sticky bars not exhaustively reclassified in this pass.
