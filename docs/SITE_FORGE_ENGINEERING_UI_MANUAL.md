# Site Forge Engineering UI Manual

**Gate 1 — Current implementation as traced from dashboard + desktop IPC (feature/plc2-transport-fidelity).**  
Sources: `dashboard/index.html`, `dashboard/fortna-plus.js`, `dashboard/transport-build.js`, `dashboard/transport-build-pass2.js`, `dashboard/safety-build.js`, `desktop/main.js`, `desktop/preload.js`.  
This document describes the UI that exists today. It does not redesign screens.

---

## Compact workflow

```
RUN (.tar.gz)
  → Auto Build (layout from RUN physical geometry; silent on import)
  → Canonical Engineering Model (Transport canvas · Safety · Sorter · Sawtooth · HardwareIO)
  → Engineer Review / Edit
  → Apply (per subsystem → workspace/autogen_workbook.json)
  → Autogen (Export L5X Package → fortna_autogen.py)
  → PLC Compiler (Studio 5000 opens L5X as NEW project; app never launches Studio)
```

Transport strip mirrors the same path: Import RUN → Layout → Review/Correct → Apply to Autogen → Build PLC (`#tb-workflow-strip`).

---

## Tab inventory

| Nav label | `data-tab` / pane | Primary JS |
|-----------|-------------------|------------|
| **I/O & Prints** | `io` / `#tab-io` | `fortna-plus.js` (import, HardwareIO, OCR) |
| **Transport Build** | `transport` / `#tab-transport` | `transport-build.js` + `transport-build-pass2.js` |
| **Safety Build** | `safety` / `#tab-safety` | `safety-build.js` |
| **Sorter Build** | `sorter` / `#tab-sorter` | `fortna-plus.js` sorter section |
| **Sawtooth Merge** | `sawtooth` / `#tab-sawtooth` | `fortna-plus.js` sawtooth section |
| **PLC Autogen** | `autogen` / `#tab-autogen` | `fortna-plus.js` + IPC `autogen-*` |
| Docs | `search` / `#tab-search` | doc index IPC |
| Workspace | `workspace` / `#tab-workspace` | import/clear workspace |
| Recipes | `recipes` / `#tab-recipes` | recipe apply IPC |
| *(hidden panes still in `ALL_TABS`)* | `plc`, `ignition` | legacy PLC export / Ignition |

Landing tab: **I/O & Prints**. Tab switch: `activateTab()` in `fortna-plus.js`.

Compile-hub readiness keys: `hardware`, `transport`, `sawtooth`, `sorter`, `system`, `safety` (`ensureAutogenReadiness()`).

---

## REVIEW_REQUIRED (product contract)

From `autogenBuildPreflight()` / hub cards:

| Concept | Meaning |
|---------|---------|
| **FOUND** | RUN evidence exists; not yet Applied / not INCLUDED |
| **CONFIGURED** | Engineer edited local model |
| **INCLUDED** | Apply wrote into workbook + readiness `appliedAt` set (or READY) |
| **GENERATED** | Present in last L5X emit report |
| **REVIEW_REQUIRED** | Soft review — **does not hard-block** Export |
| **ERROR** | Hard-block only when mandatory pack ERROR, or INCLUDED subsystem ERROR, or Safety emit ERROR |

Labels: `NOT DETECTED` · `DETECTED — REVIEW REQUIRED` · `CHANGED SINCE LAST APPLY` · `READY FOR AUTOGEN` · `ERROR / BLOCKED`.

Partial Build: unassigned Safety, incomplete membership, detected-but-not-Applied Saw/Sorter → soft reviews; Export still allowed when `partialBuildAllowed`.

---

## 1. I/O & Prints (Project / Import + Hardware I/O)

### Purpose
Owns the **active RUN**. Loads `.tar.gz`, drives HardwareIOModel CAD (tree / FLEX rack / channel table), optional panel PDF OCR vs RUN banks. Autogen and Transport consume this RUN — other tabs do not re-import.

### Canonical model(s)
- Workspace active extract (`fortnaAPI.importRun` / `getWorkspace`)
- HardwareIOModel via `getHardwareIo` (+ engineer channel overrides → `workspace/hardware_io_overrides.json`)
- I/O banks / OCR crosswalk (diagnostics)

### RUN evidence consumed
PhysicalWordResolver / HardwareIOModel banks, modules, channels; conveyor/device lists for other tabs after import.

### Engineer-editable fields
Channel **Name** / **Generate** overrides on selected module; panel/RIO filter selects; print PDFs for OCR.

### Apply / Auto Build / Persist / Downstream

| Action | Behavior |
|--------|----------|
| **Apply** | N/A as named button; channel edits call `saveHardwareIoChannel` immediately |
| **Auto Build** | On successful RUN import, Transport `transportAutoBuildFromRun({ silent: true })` runs from load path |
| **Persisted** | Active workspace under `workspace/active*`; channel overrides JSON; OCR last-result cache |
| **→ Autogen** | RUN banks → always-on IO_MAP; workbook refresh uses active RUN |
| **→ PLC compiler** | IO_MAP + Flex tree in L5X from `fortna_autogen.py` |
| **REVIEW_REQUIRED** | Hardware hub soft-review if banks incomplete; IO_MAP generate failure → hub `hardware` **ERROR** |

### Controls

| Label | Handler | Mutation | Authority | Persist | Downstream | Prerequisites / failure |
|-------|---------|----------|-----------|---------|------------|-------------------------|
| **Load RUN** (`#btn-io-browse-run`) | browse + `importRun` | Sets active workspace / machine | Engineering (project root) | Disk extract | Triggers Transport auto-build, SiteModel editors | Needs Electron; fails if archive invalid |
| **Clear** (`#btn-io-clear-run`) | clear RUN UI + related state | Clears loaded RUN presentation | Engineering | May clear active | Stale Autogen until re-import | Confirm path in handler |
| Dropzone `#io-run-dropzone` | same import path | Same as Load RUN | Engineering | Disk | Same | `.tar.gz` only |
| **Control Panel** / **Remote I/O** selects | filter Hardware CAD | Display filter only | Display | Session | None | RUN loaded |
| Channel Name / Generate | `saveHardwareIoChannel` | Override channel emit metadata | Engineering-authoritative for IO_MAP | `hardware_io_overrides.json` | Autogen IO_MAP | Module selected; IPC required |
| **Add Remote** / browse prints / **Clear prints** | print list + OCR prep | Print file set | Engineering (prints) | OCR cache | OCR crosswalk only | PDFs optional |
| **Run OCR** (`#btn-run-ocr`) | `ocrPrints` | PRINT column vs tar.gz | Display / diagnostic | Last OCR result | Does not rewrite Autogen | Needs prints + master; disabled otherwise |
| **Refresh banks** | `refreshIoBanks` | Re-read banks from RUN | Display refresh | None new | Diagnostics | RUN loaded |

Hidden legacy: `#btn-set-master`, `#btn-browse-master-prints`, `#btn-browse-prints` (aria-hidden).

---

## 2. Transport Build

### Purpose
Author **Areas**, conveyor topology, merges, PE roles, ES Zone names on conveyors, and presentation geometry. Primary engineering surface for Transportation IR.

### Canonical model(s)
- In-memory `tb` graph: `areas[]` (nodes, wires), `safetyZones[]`, `buildContext`, layers/view
- localStorage key from `STORE_KEY` in `transport-build.js` (`save()` / `load()`)
- On **Apply**: canonical graph via `buildCanonicalApplyGraph()` → IPC `transport-apply-autogen` → `workspace/autogen_workbook.json` (+ `exports/transport-poc` merges artifact)

### RUN evidence consumed
`transport-auto-build-from-run` → `fortna_cp5a_transport_mapper.py` / physical layout → nodes with RUN X/Y/Angle/Length, high-confidence wires, decoder inventory for unplaced tags. Does **not** invent Area/ES names.

### Engineer-editable fields
Area name/membership; `safetyZone` / ES Zone; `downstream` / wires; `terminal`; merge PE fields; attached devices + PE roles; conveyor tags; curve display angle (presentation); geometry overrides when mode = Engineering Override.

### Apply
`#tb-apply-autogen` → `applyMergesToAutogenUi()` → `buildCanonicalApplyGraph()` → `window.applyTransportMergesToAutogen` / `fortnaAPI.transportApplyAutogen`.  
Serializes topology + Area/ES/PE/relationships only — **excludes** pathCanvas, view, layers, presentationOffset. Sets hub transport READY via `setAutogenReadinessApplied('transport', …)`. Canvas must not mutate during Apply (hash guard).

### Auto Build / Rebuild Layout
- Silent: on RUN load (`autoBuildFromRun({ silent: true })`)
- Manual: **Rebuild Layout** (`#tb-auto-build-run`) → `autoBuildFromRun({ rebuild: true })` with confirm; replaces positions/wires from RUN; pushes undo history; does not invent Areas/Safety

### Persist / Downstream / REVIEW

| Layer | What |
|-------|------|
| **Persisted (local)** | `save()` → localStorage areas/safetyZones/layers + projectIdentity |
| **Persisted (Apply)** | Workbook conveyors/areas/merges_2to1/safetyBuild fragment via Python apply |
| **→ Autogen** | Areas → `main_area`; merges; PE roles; safety zone conveyor refs |
| **→ PLC** | Area programs, merge AOIs, transport stubs when Export runs |
| **REVIEW_REQUIRED** | Unassigned/unplaced conveyors are FOUND (soft). After Apply, canvas edits → `markAutogenReadinessDirty('transport')` → CHANGED until re-Apply |

### Transportation controls (traced)

| Exact label | Source handler | State mutation | Display vs authoritative | Persist | Downstream | Prerequisites / failure |
|-------------|----------------|----------------|--------------------------|---------|------------|-------------------------|
| **Apply Area / ES** | `applyBulkEdit()` (pass2) | `moveNodeToArea`; `n.safetyZone`; `provenance.area/safetyZone='ENGINEER'` | Authoritative engineering | `save()` localStorage | Autogen only after Apply to Autogen | Selection required; needs Area and/or ES text |
| **Create Area from Selection** | `createAreaFromSelection()` | New area; move selection; optional `defaultSafetyZone` | Authoritative (Area metadata) | `save()` | Workbook on Apply | Selection; name prompt; never inferred from geometry |
| **Add Selection to Area** | `addSelectionToArea()` → `moveSelectionToArea` | Moves nodes; `provenance.area='ENGINEER'` | Authoritative | `save()` | Workbook on Apply | Selection; existing area pick |
| **Remove Selection from Area** | `removeSelectionFromArea()` | Move to Unassigned (or typed dest) | Authoritative organizational | `save()` | Workbook on Apply | Selection; does not invent PLC ownership |
| **Select Chain** | `selectChainFromPrimary()` | Expands `selectedIds` via wires BFS | Display selection | None | None | Active area + selection |
| **Mark Terminal** | `markTerminalSelection(true)` | `n.terminal=true` | Authoritative topology | `save()` | Canonical Apply includes `terminal` | Selection or ctx node |
| **Geometry** select (`#tb-geometry-mode`) | `setGeometryAuthorityMode(mode)` | `tb.geometryAuthorityMode` = run/override/diagnostic | Display authority (diagnostic forces geom-debug) | Not in Apply payload | Presentation / override edit path | Default RUN/Physical |
| **Undo** / **Redo** | `undo()` / `redo()` (pass2 history) | Restores snapshot of areas/selection | Authoritative restore of canvas | `save()` on restore | Dirty hub if previously Applied | Empty stack → status only |
| **Fit System** (`#tb-fit`, `#tb-fit-system`) | `fitSystem()` / `fitVisible` fallback | Viewport zoom/pan only | **Display-only** | None | None | Nodes present |
| Fit Visible / Fit All / Center Selected / Fit Area / Fit Site / Home / 100% | `fitVisible`, `fitAll`, `centerSelected`, `fitArea`, `fitSite`, `resetView100` | Viewport only | Display-only | None | None | — |
| Zoom − / + | `zoomByFactor` | Viewport | Display-only | None | None | — |
| Right-click **Continue Run…** | `openContinueRun` | Continue-run UI | Engineering (add unplaced) | On commit | Topology | Unplaced inventory |
| Right-click **Mark / Clear Terminal** | `markTerminalSelection` | `terminal` | Authoritative | `save()` | Apply | — |
| Right-click **Select Chain** | `selectChainFromPrimary` | Selection | Display | None | None | — |
| Right-click **Add to New/Existing Area…**, **→ area**, **Remove from Area…** | `createAreaFromSelection` / `addSelectionToArea` / `moveSelectionToArea` / `removeSelectionFromArea` | Area membership | Authoritative | `save()` | Apply | — |
| Right-click **CURVE display angle** | `setCurveDisplayAngle` | `curveDisplayAngle` | **Presentation only** (also copied in Apply as non-topology) | `save()` | Not PLC L/R | Curve kinds only |
| Right-click **Delete** | `deleteSelection` | Removes nodes/wires | Authoritative | `save()` | Apply | — |
| Inspector **Rotate** (`#tb-insp-rotate`) | rotate handler in `bindUi` | Node rotation 90° | Geometry / presentation | `save()` | Presentation; override mode | Node selected |
| **Apply to Autogen** | `applyMergesToAutogenUi` | Workbook via IPC; hub READY | Authoritative publish | Workbook + localStorage workflow | Autogen/Export | Desktop IPC; shows failure dialog |
| **Build PLC** (`#tb-goto-build-plc`) | `activateTab('autogen')` + scroll to Export | Navigation only | Display | None | Highlights Export L5X | Shown after successful Apply |
| **Rebuild Layout** | `autoBuildFromRun({ rebuild:true })` | Replaces canvas from RUN graph | Authoritative layout recovery | `save()` after build | Unplaced inventory | Confirm; IPC `transportAutoBuildFromRun` |
| **Connect** | `toggleConnectMode` | EXIT→ENTRY wire mode | Authoritative when wired | `save()` on connect | Apply | — |
| **New** / **Delete** area | toolbar new-area / `deleteActiveArea` | Area list | Authoritative | `save()` | Apply | — |
| **Build Chain…** / dialog OK | `openChainDialog` / `commitChain` | Creates/connects conv nodes in Build Context | Authoritative | `save()` | Apply | Unknown tags blocked unless allow-unknown |
| **Continue Run** / Add | `continueRunTo` | Places unplaced P### downstream | Authoritative | `save()` | Apply | Selected conveyor |
| **Auto Layout (topology)** | `autoLayoutArea` / `autoLayoutSelection` | Positions fallback-layout-eligible nodes only | Presentation (skips PROVEN_RUN / ENGINEER_ASSIGNED) | `save()` | Not Autogen geometry | — |
| Advanced layers / relationships / lane separate / geom debug | layer checkboxes | `tb.layers` / `viewMode` | Display-only | localStorage layers | Ignored by Apply | — |
| **Export geometry diagnostic…** | `exportGeometryDiagnostic` | Writes diagnostic artifact | Report only | File export | None | Node selected |
| Topology table / inspector fields | various `bindUi` / topo listeners | Tags, downstream, merge PEs, PE roles, devices | Authoritative when changed | `save()` | Apply PE roles filter RUN/manual | PE ROLE REQUIRED blocks emit until resolved |

IPC backing: `preload.js` → `transportApplyAutogen`, `transportAutoBuildFromRun`, `transportBuildPoc`, `transportLatestMerges`; `main.js` handlers `transport-apply-autogen`, `transport-auto-build-from-run`.

---

## 3. Safety Build

### Purpose
Complete Safety Zone membership (E-Stop / ESR / MCR / reset / silence) seeded from Transport + RUN discovery. Area ≠ Safety Zone.

### Canonical model(s)
- Client model from `buildClientModel()` (zones, devices, unassigned)
- Draft: `localStorage siteforge.safetyBuild.v1`
- Applied: `autogenState.safety_build` / `workbook.safety_build`

### RUN evidence
`build-safety-model` IPC + Transport canvas zones; proven membership vs REVIEW_REQUIRED membership.

### Engineer-editable
Zone rename; add/remove devices; accept suggestions; delete zone; reset/silence sources (detail UI).

### Apply
**Apply Safety** (`#sb-apply`) → `applySafety()`: merge-save workbook via `autogenWorkbookSave` (never hollow Transport conveyors). Hub status from `syncReadiness()` only — **does not** force READY via `setAutogenReadinessApplied`.

### Auto Build
Zones ingest on refresh / Transport seed (`ingestRunDiscoveredZones`); not a separate “Auto Build” button.

### Persist / Downstream / REVIEW
| | |
|--|--|
| Persist | local draft + workbook `safety_build` on Apply |
| → Autogen / PLC | Program ES from READY zones; partial/fail-safe shell when review remains |
| REVIEW_REQUIRED | Any unassigned device or non-READY zone → hub soft review; Export allowed |

### Controls

| Label | Handler | Mutation | Authority | Persist | Downstream | Notes |
|-------|---------|----------|-----------|---------|------------|-------|
| **Refresh discovery** | `refreshModel` | Rebuild model; keep engineer overrides | Mix | Draft | Hub sync | — |
| **Apply Safety** | `applySafety` | Write `safety_build` | Authoritative | Workbook merge | ES emit | Soft review OK |
| Zone list / detail actions (`sb-add-selected`, `sb-remove-selected`, `sb-accept-suggestions`, `sb-delete-zone`, `sb-rename-zone`, `sb-show-on-transport`) | rendered in `renderZoneDetail` | Membership / names | Authoritative | Draft then Apply | Transport highlight | Dynamic DOM |

---

## 4. Sorter Build

### Purpose
Configure sorter induct / tracking / diverts from RUN + SiteModel; publish `sorter_build` for Sorter_Track pack.

### Canonical model
`autogenState.sorter` (+ workbook `sorter_build`); localStorage `fortna_sorter_build`.

### RUN evidence
SiteModel sorter objects, divert PE authorities (PROVEN / DERIVED / COMMISSIONING / ENGINEER_REQUIRED / REVIEW_REQUIRED).

### Apply
**Apply sorter → Autogen** (`#btn-sorter-save`): merge workbook save; READY only if data + phase1 OK + `configuration_required` empty; else REVIEW_REQUIRED with `appliedAt` possible.

### Controls (primary)

| Label | Handler | Mutation | Notes |
|-------|---------|----------|-------|
| **Accept All Derived** | divert accept handler | DERIVED PE → ENGINEER_ACCEPTED; never UNKNOWN→PROVEN | Gate N |
| **Apply PE to Selected** | bulk PE | Sets divert_pe + ENGINEER_REQUIRED if not PROVEN | Needs bulk PE value + checkboxes |
| **Mark Selected for Commissioning** | commission handler | `authority.divert_pe=COMMISSIONING` | — |
| **Apply sorter → Autogen** | sorter save | workbook.sorter_build; hub | Merge-safe vs Transport/Safety |
| **Clear sorter fields** | clear | defaultSorterConfig; readiness reset | — |
| Tracking offset / type / area / row editors | various | `autogenState.sorter` | `touchSorter` dirties hub |

**Auto Build:** SiteModel populate on import (`applySiteModelToEditors`) — no dedicated button.  
**→ PLC:** Sorter_Track when hub READY / opt checked during `runAutogenGenerate`.

---

## 5. Sawtooth Merge

### Purpose
Collector / lane saw-merge design (PLC4 pattern) → `Sawtooth_Merge` pack.

### Canonical model
`autogenState.sawtooth` / `workbook.sawtooth_build`; localStorage `fortna_sawtooth_build`.

### RUN evidence
SawMerge/SawLane (and HS*) tables via SiteModel auto-populate on import.

### Apply
**Apply sawtooth → Autogen** (`#btn-saw-save`): `persistSawtoothToWorkbook` + workbook save; READY iff configured and `configuration_required` empty; else REVIEW_REQUIRED.

### Controls

| Label | Handler | Notes |
|-------|---------|-------|
| **Apply sawtooth → Autogen** | saw-save listener | Hub READY or REVIEW |
| **Reload from RUN** | `applySiteModelToEditors` | Discards local edits |
| **Clear** | `defaultSawtoothConfig` | Resets readiness |
| **Prefill PLC4 demo** | DEV hardcoded | **Not for acceptance** |
| Lane/collector/encoder fields | renderSawtoothBuild binders | Engineer edits |

---

## 6. PLC Autogen (Autogen / Build)

### Purpose
Compile hub: readiness cards + **Export L5X Package** (`#btn-autogen-from-run` → `runAutogenGenerate('run')` → `fortnaAPI.autogenGenerate` → `fortna_autogen.py`).

### Canonical model
`workspace/autogen_workbook.json` (stable path; survives RUN clear unless project clear). Merged disk+memory before generate (Transport conveyors, safety_build, sawtooth_build, sorter_build).

### Always-included packs
Sys · Devices_Comm · NTP · System_Logic · System · IO_MAP.

### Evidence / Apply-driven packs
Sawtooth_Merge, Sorter_Track, merges from workbook, WCS / ShippingSorter when SiteModel supports.

### Key controls

| Label | Handler | Mutation / effect |
|-------|---------|-------------------|
| **Export L5X Package** | `runAutogenGenerate('run')` | Writes `exports/autogen` (+ current); preflight soft/hard; **does not launch Studio** |
| **Refresh site config** | workbook build IPC | Re-scan RUN; keeps edits |
| **Save** workbook (`#btn-autogen-workbook-save`) | `autogenWorkbookSave` | Disk workbook |
| Browse library / Excel / Inspect / Generate | legacy/advanced | Excel path optional |
| Twin Refresh / Search / Propose / Apply | twin IPC | Gap patches into workbook |
| Open out / Reveal L5X / Copy path | `openPath` / clipboard | Presentation of outputs |
| Catalog Add buttons | workbook catalog rows | Site config table |
| **From Transport** / **Save Transport WB** (hub) | `applyTransportMergesToAutogen` / workbook save | Pull graph / persist |
| **Clear current project builds** | `clearCurrentProject` | Wipes RUN extract, edits, Transport/Saw/Sorter, matching autogen outs — not libraries |

### REVIEW_REQUIRED on Build
Soft reviews logged; Safety partial → `BUILD GENERATED WITH REVIEW ITEMS`; ES omit/partial keeps safety hub REVIEW. Hard ERROR blocks Export.

---

## 7. Workspace / Docs / Recipes (secondary)

### Workspace (`#tab-workspace`)
| Control | Handler | Role |
|---------|---------|------|
| Browse archive | `selectArchive` / import | Project/Import alternate to I/O Load RUN |
| Open folder / Exports | `openPath` | Display |
| Clear workspace | `clearWorkspace` | Keeps workbook by design in main |
| **Apply** (`#btn-apply`) | recipes only when on Recipes — also wired as recipe apply | See Recipes |

### Docs (`#tab-search`)
Search input + quick badges → `searchDocs`; **Reindex** → `reindexDocs`. Display-only vs engineering models.

### Recipes (`#tab-recipes`)
Recipe list + params; **Apply** → `fortnaAPI.applyRecipe`. Mutates RUN tables (clone device, add PE, etc.); not Autogen workbook Apply.

### Hidden `#tab-plc` / `#tab-ignition`
Legacy PLC export / Ignition layout builders (`exportPlc`, `ignitionBuildLayout`). Not in primary nav.

---

## Persistence map (engineering-authoritative)

| Surface | Local draft | Published artifact | Consumer |
|---------|-------------|--------------------|----------|
| Transport canvas | localStorage `STORE_KEY` | workbook via `transport-apply-autogen` | Autogen areas/merges |
| Safety | `siteforge.safetyBuild.v1` | `workbook.safety_build` | Program ES |
| Sorter | `fortna_sorter_build` | `workbook.sorter_build` | Sorter_Track |
| Sawtooth | `fortna_sawtooth_build` | `workbook.sawtooth_build` | Sawtooth_Merge |
| Hardware channels | — | `hardware_io_overrides.json` | IO_MAP |
| Workbook | memory `autogenState.workbook` | `workspace/autogen_workbook.json` | `fortna_autogen.py --workbook` |

---

## Desktop IPC (Auto Build / Build PLC)

Exposed on `window.fortnaAPI` (`desktop/preload.js`):

| API | Main channel | Used by |
|-----|--------------|---------|
| `importRun` | `import-run` | I/O Load RUN |
| `transportAutoBuildFromRun` | `transport-auto-build-from-run` | Transport Auto Build / Rebuild |
| `transportApplyAutogen` | `transport-apply-autogen` | Apply to Autogen |
| `autogenGenerate` | `autogen-generate` | Export L5X Package (Build PLC) |
| `autogenWorkbookBuild/Save/Load` | `autogen-workbook-*` | Site config / Apply merges |
| `buildSafetyModel` | `build-safety-model` | Safety discovery |
| `getHardwareIo` / `saveHardwareIoChannel` | hardware IO | I/O CAD |
| `clearCurrentProject` | `clear-current-project` | Hub clear |

---

## Counts (this gate)

| Metric | Approx. |
|--------|---------|
| Visible primary engineering tabs | **6** (I/O, Transport, Safety, Sorter, Sawtooth, Autogen) |
| Secondary tool tabs | **3** (Docs, Workspace, Recipes) |
| Tab panes in `ALL_TABS` | **11** (includes hidden plc + ignition) |
| User-facing controls documented | **~120+** (toolbar, bulk bar, ctx menu, inspector, hub, IO, Safety/Sorter/Saw actions) |
| Transportation-specific controls traced to real handlers | **Yes** — Apply Area/ES, Create/Add/Remove Area, Select Chain, Mark Terminal, geometry mode, undo/redo, Fit System, right-click Area/geometry/orientation, Apply to Autogen, Build PLC (nav to Export) |

---

*End of Gate 1 Engineering UI Manual. Implementation-traced; no UI redesign.*
