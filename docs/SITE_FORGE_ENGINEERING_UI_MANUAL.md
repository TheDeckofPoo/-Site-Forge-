# Site Forge Engineering UI Manual

**Gates L / M / N / O — CURRENT implementation traced from source (feature/plc2-transport-fidelity).**  
Sources: `dashboard/index.html`, `dashboard/fortna-plus.js`, `dashboard/transport-build.js`, `dashboard/transport-build-pass2.js`, `dashboard/safety-build.js`, `desktop/main.js`, `desktop/preload.js`.  
This document describes the UI that exists today. It does not invent screens or held-back sites.

In-product help: header **?** opens a Help drawer (`#sf-help-drawer`) keyed by control `id` via `SITE_FORGE_HELP` in `fortna-plus.js`.

---

## GATE O — Engineering workflow

```
RUN Import (.tar.gz on I/O & Prints or Workspace)
  → Auto Build (silent Transport layout from RUN physical geometry)
  → Canonical Engineering Model
        (same project model edited by every tab:
         Transport canvas · Safety · Sorter · Sawtooth · Hardware I/O · Autogen workbook)
  → Review / Correct (engineer edits; REVIEW_REQUIRED is soft unless ERROR on INCLUDED)
  → Apply (per subsystem → workspace/autogen_workbook.json + readiness appliedAt)
  → Autogen (Export L5X Package → fortna_autogen.py)
  → PLC Compiler (Studio 5000 opens L5X as a NEW project; Site Forge never launches Studio)
```

Transport strip (`#tb-workflow-strip`): **Import RUN → Layout → Review/Correct → Apply to Autogen → Build PLC**.

### Same canonical project model

All primary tabs edit facets of **one** project:

| Facet | Live draft | Published on Apply |
|-------|------------|--------------------|
| Transport Areas / topology / PE / ES zone names | localStorage `siteforge.transportBuild.v2` | workbook conveyors / areas / merges via `transport-apply-autogen` |
| Safety Zones / membership | `siteforge.safetyBuild.v1` | `workbook.safety_build` |
| Sorter induct / track / divert | `fortna_sorter_build` | `workbook.sorter_build` |
| Sawtooth collector / lanes | `fortna_sawtooth_build` | `workbook.sawtooth_build` |
| Hardware channel Name / Generate | (immediate IPC) | `workspace/hardware_io_overrides.json` |
| Site config / packs | memory `autogenState.workbook` | `workspace/autogen_workbook.json` |

### Lifecycle vocabulary (Found / Active / Included / Generated)

From `autogenBuildPreflight()` / Compile Hub / Safety emit contract (`FOUND≠INCLUDED≠GENERATED`):

| Term | Meaning in product |
|------|--------------------|
| **FOUND** | RUN evidence discovered; not yet Applied / not INCLUDED. Soft — does **not** hard-block Export. |
| **ACTIVE** | Currently selected panel / zone / selection in the editor (UI focus). Not a publish state. |
| **CONFIGURED** | Engineer edited the local draft model (dirty / CHANGED since last Apply). |
| **INCLUDED** | Apply wrote into workbook + readiness `appliedAt` (or READY). Pack is eligible for emit. |
| **GENERATED** | Present in last L5X emit report (e.g. Safe_Logic members actually emitted). |
| **UNASSIGNED** | Discovered but not membership-assigned. ≠ ERROR ≠ SAFE. |

Hub labels: `NOT DETECTED` · `DETECTED — REVIEW REQUIRED` · `CHANGED SINCE LAST APPLY` · `READY FOR AUTOGEN` · `ERROR / BLOCKED`.

Hard-block Export only when: mandatory pack ERROR, an **INCLUDED** subsystem is ERROR, or Safety emit ERROR. Soft REVIEW_REQUIRED (partial Safety, unapplied Saw/Sorter, FOUND conveyors) allows Partial Build when `partialBuildAllowed`.

### Provenance / authority vocabulary (where they exist)

| Token | Where used | Meaning |
|-------|------------|---------|
| **PROVEN** / **PROVEN_RUN** / **AUTO_RUN_PROVEN** / **RUN_EXPLICIT** | Transport geometry, Safety membership, Sorter divert/track PE | Direct RUN / decoder evidence |
| **DERIVED** / **RUN_DERIVED** | Sorter divert PE / tracking offset; Transport presentation offsets | Computed from RUN — Accept or Edit; never invent |
| **ENGINEER_ASSIGNED** / **ENGINEER** | Area/ES bulk apply, Safety assign/rename, geometry override | Engineer authored |
| **ENGINEER_ACCEPTED** | Sorter review Accept derived | Engineer accepted DERIVED without changing value |
| **ENGINEER_REQUIRED** | Sorter / Saw unresolved fields | Must edit before READY |
| **REVIEW_REQUIRED** | Hub, Safety zones, Sorter review panel | Soft review; fail-safe membership |
| **COMMISSIONING** | Sorter tracking offset / divert Mark Commissioning | Field deferred to site commission |
| **OPTIONAL** | Sorter optional fields | Informational — never merged into REVIEW_REQUIRED |
| **UNKNOWN** | Missing PE role, CURVE orientation, unplaced geometry | Not inventable; may block PE ROLE REQUIRED emit |
| **FALLBACK_LAYOUT** / **DERIVED_TOPOLOGY** | Transport Auto Layout | Presentation only; never overwrites PROVEN_RUN / ENGINEER_ASSIGNED |

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
| Workspace | `workspace` / `#tab-workspace` | import / clear workspace |
| Recipes | `recipes` / `#tab-recipes` | recipe apply IPC |
| *(hidden in `ALL_TABS`)* | `plc`, `ignition` | legacy PLC export / Ignition |

Landing tab: **I/O & Prints**. Switch: `activateTab()` in `fortna-plus.js`.  
Compile-hub readiness keys: `hardware`, `transport`, `sawtooth`, `sorter`, `system`, `safety` (`ensureAutogenReadiness()`).

---

## 1. I/O & Prints (RUN Import / Workspace entry + Hardware I/O)

### PURPOSE
Owns the **active RUN**. Loads `.tar.gz`, drives HardwareIOModel CAD (tree / FLEX rack / channel table), optional panel PDF OCR vs RUN banks. Autogen and Transport consume this RUN — other tabs do not re-import.

### RUN / Fortna evidence
PhysicalWordResolver / HardwareIOModel banks, modules, channels; conveyor/device lists used by SiteModel editors after import.

### CANONICAL MODEL
- Workspace active extract (`fortnaAPI.importRun` / `getWorkspace`)
- HardwareIOModel via `getHardwareIo` (+ engineer channel overrides → `workspace/hardware_io_overrides.json`)
- I/O banks / OCR crosswalk (diagnostics only)

### AUTO BUILD populates
On successful RUN import, Transport `transportAutoBuildFromRun({ silent: true })` runs from the load path; SiteModel editors populate Sorter/Sawtooth.

### ENGINEER edits
Channel **Name** / **Generate** on selected module; panel/RIO filter selects; print PDFs for OCR.

### APPLY does
No named Apply button. Channel edits call `saveHardwareIoChannel` immediately on blur/change.

### PERSISTS
Active workspace under `workspace/active*`; `hardware_io_overrides.json`; OCR last-result cache.

### Reaches AUTOGEN
RUN banks → always-on IO_MAP; workbook refresh uses active RUN.

### Reaches PLC COMPILER
IO_MAP + Flex tree in L5X from `fortna_autogen.py`.

### REVIEW / ERROR
Hardware hub soft-review if banks incomplete; IO_MAP generate failure → hub `hardware` **ERROR**.

### Controls

| Label | Tab | Purpose | Handler | Model mutation | Display vs eng | Persist | Downstream | Prerequisite | Review/error |
|-------|-----|---------|---------|----------------|----------------|---------|------------|--------------|--------------|
| **Load RUN** `#btn-io-browse-run` | I/O | Browse `.tar.gz` | browse + `importRun` | Sets active workspace | Engineering (project root) | Disk extract | Triggers Transport auto-build, SiteModel | Electron | Invalid archive fails |
| Dropzone `#io-run-dropzone` | I/O | Drop `.tar.gz` | same import path | Same | Engineering | Disk | Same | `.tar.gz` only | Same |
| **Clear** `#btn-io-clear-run` | I/O | Clear loaded RUN UI | clear RUN handler | Clears presentation / related | Engineering | May clear active | Stale Autogen until re-import | Confirm in handler | — |
| **Control Panel** `#hw-io-panel-select` | I/O | Filter CAD by panel | change → filter | Display filter | Display | Session | None | RUN loaded | — |
| **Remote I/O** `#hw-io-rio-select` | I/O | Filter by RIO | change → filter | Display filter | Display | Session | None | RUN loaded | — |
| Module / channel select | I/O | Select module/channel | tree / rack click | Selection only | Display | Session | Enables Name/Generate | RUN + banks | — |
| Channel **Name** `.hw-ch-name-input` | I/O | Engineer override emit name | blur → `saveHardwareIoChannel` | Override channel name | Engineering-authoritative | `hardware_io_overrides.json` | Autogen IO_MAP | Module selected; IPC | Invalid Logix name flagged |
| Channel **Generate** `.hw-ch-gen-input` | I/O | Mute/include in IO_MAP | change → `saveHardwareIoChannel` | `generate` flag; Spare when off | Engineering-authoritative | overrides JSON | Autogen IO_MAP | Module selected | Muted = Spare (visible, not emitted) |
| Status ● Active / ○ Spare | I/O | Show emit status | render only | None | Display | — | — | — | Spare ≠ deleted |
| **Add Remote** `#btn-add-remote` | I/O | Add remote panel name | add remote | Print panel list | Engineering (prints) | Session / OCR | OCR only | — | — |
| **Browse panel PDFs** `#btn-browse-remote-prints` | I/O | Attach PDFs | browse prints | Print file set | Engineering (prints) | OCR cache | OCR crosswalk | — | — |
| **Clear prints** `#btn-io-clear-prints` | I/O | Clear PDFs + merge | clear prints | Clears prints/OCR | Engineering | Cache clear | Diagnostics | — | — |
| **Run OCR** `#btn-run-ocr` | I/O | OCR prints vs tar.gz | `ocrPrints` | PRINT column | Display / diagnostic | Last OCR | Does not rewrite Autogen | Prints + master; disabled else | Soft |
| **Refresh banks** `#btn-refresh-banks` | I/O | Re-read banks from RUN | `refreshIoBanks` | Refresh display | Display refresh | None new | Diagnostics | RUN loaded | — |
| **Print repo** `#btn-print-repo` | I/O | Browse loaded PDFs | open print list | None | Display | — | — | Prints loaded | — |
| Crosswalk tabs matched/Remote/Print/tar.gz/Panels | I/O | Filter OCR table | `data-cw-tab` | Display filter | Display | — | — | OCR ran | — |

Hidden legacy (aria-hidden): `#btn-set-master`, `#btn-browse-master-prints`, `#btn-browse-prints`.

---

## 2. Transport Build

### PURPOSE
Author **Areas**, conveyor topology, merges, PE roles, ES Zone names on conveyors, and presentation geometry. Primary engineering surface for Transportation IR.

### RUN / Fortna evidence
`transport-auto-build-from-run` → physical layout → nodes with RUN X/Y/Angle/Length, high-confidence wires, decoder inventory for unplaced tags. Does **not** invent Area/ES names.

### CANONICAL MODEL
In-memory `tb` graph (`areas[]`, `safetyZones[]`, `buildContext`, layers/view); localStorage `STORE_KEY` (`siteforge.transportBuild.v2`); on Apply → `buildCanonicalApplyGraph()` → IPC `transport-apply-autogen` → workbook.

### AUTO BUILD populates
Silent on RUN load (`autoBuildFromRun({ silent: true })`). Manual **Rebuild Layout** replaces positions/wires from RUN only.

### ENGINEER edits
Area name/membership; `safetyZone` / ES Zone; `downstream` / wires; `terminal`; merge PE fields; attached devices + PE roles; conveyor tags; curve display angle (presentation); geometry overrides when mode = Engineering Override.

### APPLY does
`#tb-apply-autogen` → `applyMergesToAutogenUi()` → `buildCanonicalApplyGraph()` → `transportApplyAutogen`. Serializes topology + Area/ES/PE/relationships only — **excludes** pathCanvas, view, layers, presentationOffset. Sets hub transport READY via `setAutogenReadinessApplied('transport', …)`.

### PERSISTS
localStorage on `save()`; workbook on Apply.

### Reaches AUTOGEN
Areas → `main_area`; merges; PE roles; safety zone conveyor refs.

### Reaches PLC COMPILER
Area programs, merge AOIs, transport stubs when Export runs.

### REVIEW / ERROR
Unassigned/unplaced conveyors are FOUND (soft). After Apply, canvas edits → `markAutogenReadinessDirty('transport')` → CHANGED until re-Apply. PE ROLE REQUIRED blocks emit until resolved.

### Transportation controls (required inventory)

| Label | Tab | Purpose | Handler | Model mutation | Display vs eng | Persist | Downstream | Prerequisite | Review/error |
|-------|-----|---------|---------|----------------|----------------|---------|------------|--------------|--------------|
| **Connect** `#tb-connect-mode` | Transport | EXIT→ENTRY wire mode | `toggleConnectMode` | Wire mode; wire on click | Authoritative when wired | `save()` on connect | Apply topology | — | — |
| **Fit System** `#tb-fit` / `#tb-fit-system` | Transport | Fit width, X-centered, top-biased | `fitSystem` / `fitVisible` fallback | Viewport zoom/pan | **Display-only** | None | None | Nodes present | — |
| Zoom − `#tb-zoom-out` | Transport | Zoom out | `zoomByFactor` | Viewport | Display-only | None | None | — | — |
| Zoom + `#tb-zoom-in` | Transport | Zoom in | `zoomByFactor` | Viewport | Display-only | None | None | — | — |
| **Home** `#tb-home` / `#tb-zoom-reset` | Transport | Reset zoom/pan | `resetView100` | Viewport | Display-only | None | None | — | — |
| **100%** `#tb-zoom-100` | Transport | Reset view 100% | `resetView100` | Viewport | Display-only | None | None | — | — |
| Fit Visible / Fit All / Center Selected / Fit Area / Fit Site | Transport | Viewport variants | `fitVisible`, `fitAll`, `centerSelected`, `fitArea`, `fitSite` | Viewport | Display-only | None | None | — | — |
| **Geometry** `#tb-geometry-mode` | Transport | RUN/Physical · Override · Diagnostic | `setGeometryAuthorityMode` | `tb.geometryAuthorityMode` | Display authority (diagnostic → geom-debug) | Not in Apply payload | Presentation / override edit | Default RUN/Physical | — |
| **Undo** `#tb-undo` | Transport | Undo (Ctrl+Z) | `undo()` pass2 | Restores areas/selection | Authoritative restore | `save()` | Dirty hub if Applied | Empty stack → status | — |
| **Redo** `#tb-redo` | Transport | Redo (Ctrl+Y) | `redo()` | Restores snapshot | Authoritative | `save()` | Dirty hub | Empty stack | — |
| **Apply Area / ES** `#tb-bulk-apply` | Transport | Area + ES Zone on selection | `applyBulkEdit()` | `moveNodeToArea`; `n.safetyZone`; `provenance.area/safetyZone='ENGINEER'` | Authoritative | `save()` | Autogen after Apply to Autogen | Selection; Area and/or ES text | Status if neither set |
| **Create Area from Selection** `#tb-bulk-create-area` | Transport | New Area from selection | `createAreaFromSelection()` | New area; move selection; optional defaultSafetyZone | Authoritative | `save()` | Workbook on Apply | Selection; name prompt | Never inferred from geometry |
| **Add Selection to Area** `#tb-bulk-add-to-area` | Transport | Move into existing Area | `addSelectionToArea()` | Moves nodes; `provenance.area='ENGINEER'` | Authoritative | `save()` | Workbook on Apply | Selection; area pick | — |
| **Remove Selection from Area** `#tb-bulk-remove-from-area` | Transport | Move to Unassigned | `removeSelectionFromArea()` | Membership clear | Authoritative organizational | `save()` | Workbook on Apply | Selection | Does not invent PLC ownership |
| **Select Chain** `#tb-bulk-chain` | Transport | Expand selection via wires BFS | `selectChainFromPrimary()` | `selectedIds` | Display selection | None | None | Active area + selection | — |
| **Mark Terminal** `#tb-bulk-terminal` | Transport | Mark conveyor terminal | `markTerminalSelection(true)` | `n.terminal=true` | Authoritative topology | `save()` | Canonical Apply includes `terminal` | Selection or ctx node | — |
| Bulk **Delete** `#tb-bulk-delete` | Transport | Delete selection | `deleteSelection` | Removes nodes/wires | Authoritative | `save()` | Apply | Selection | — |
| Right-click **Continue Run…** | Transport | Place unplaced downstream | `openContinueRun` | Continue-run UI → place | Engineering | On commit | Topology | Unplaced inventory | — |
| Right-click **Mark / Clear Terminal** | Transport | Toggle terminal | `markTerminalSelection` | `terminal` | Authoritative | `save()` | Apply | — | — |
| Right-click **Select Chain** | Transport | Expand selection | `selectChainFromPrimary` | Selection | Display | None | None | — | — |
| Right-click **Add to New/Existing Area…**, **→ area**, **Remove from Area…** | Transport | Area membership | create/add/move/remove area helpers | Area membership | Authoritative | `save()` | Apply | — | — |
| Right-click **CURVE display angle** | Transport | Elbow paint L/R display | `setCurveDisplayAngle` | `curveDisplayAngle` | **Presentation only** | `save()` | Not PLC L/R | Curve kinds | Orientation may be UNKNOWN |
| Right-click **Delete** | Transport | Delete under cursor | `deleteSelection` | Removes | Authoritative | `save()` | Apply | — | — |
| Inspector **Rotate** `#tb-insp-rotate` | Transport | Rotate node 90° | bindUi rotate | Node rotation | Geometry / presentation | `save()` | Presentation; override mode | Node selected | — |
| Inspector Downstream / Terminal / Merge PEs / Devices / PE roles | Transport | Topology + PE authoring | bindUi / topo listeners | Tags, downstream, merge PEs, PE roles | Authoritative when changed | `save()` | Apply PE roles | PE ROLE REQUIRED until resolved | Blocks emit if UNKNOWN role required |
| **Apply to Autogen** `#tb-apply-autogen` | Transport | Publish Transport IR | `applyMergesToAutogenUi` | Workbook via IPC; hub READY | Authoritative publish | Workbook + localStorage | Autogen/Export | Desktop IPC | Failure dialog |
| **Build PLC** `#tb-goto-build-plc` | Transport | Jump to Autogen Export | `activateTab('autogen')` + scroll | Navigation only | Display | None | Highlights Export | Shown after successful Apply | — |
| **Rebuild Layout** `#tb-auto-build-run` | Transport | Recovery rebuild from RUN | `autoBuildFromRun({ rebuild:true })` | Replaces canvas from RUN | Authoritative layout recovery | `save()` after build | Unplaced inventory | Confirm; IPC | Does not invent Areas/Safety |
| **New** area `#tb-area-new` | Transport | Create Area | toolbar new-area | Area list | Authoritative | `save()` | Apply | — | Optional default Safety Zone |
| **Delete** area `#tb-area-delete-btn` / `#tb-area-delete` | Transport | Delete current area | `deleteActiveArea` | Area list | Authoritative | `save()` | Apply | — | — |
| Area select `#tb-area-select` | Transport | Switch active area | change handler | View focus | Display + build context | Session | — | — | — |
| **Build Chain…** `#tb-build-chain` | Transport | Create/connect chain | `openChainDialog` / `commitChain` | Conv nodes in Build Context | Authoritative | `save()` | Apply | Unknown tags blocked unless allow-unknown | — |
| **Continue Run** `#tb-continue-run` | Transport | Place unplaced P### | `continueRunTo` | Places downstream | Authoritative | `save()` | Apply | Selected conveyor | — |
| **Auto Layout (topology)** `#tb-auto-layout` | Transport | Fallback positions | `autoLayoutArea` / selection | Positions fallback-eligible only | Presentation (skips PROVEN_RUN / ENGINEER_ASSIGNED) | `save()` | Not Autogen geometry | — | Skipped count in status |
| Advanced layers / relationships / lane separate / geom debug | Transport | Viz toggles | layer checkboxes | `tb.layers` / `viewMode` | Display-only | localStorage layers | Ignored by Apply | — | — |
| **Export geometry diagnostic…** `#tb-export-geom-diag` | Transport | Report artifact | `exportGeometryDiagnostic` | Writes diagnostic | Report only | File export | None | Node selected | — |

IPC: `preload.js` → `transportApplyAutogen`, `transportAutoBuildFromRun`; `main.js` → `transport-apply-autogen`, `transport-auto-build-from-run`.

---

## 3. Safety Build

### PURPOSE
Complete Safety Zone membership (E-Stop / ESR / MCR / reset / silence) seeded from Transport + RUN discovery. **Area ≠ Safety Zone.**

### RUN / Fortna evidence
`build-safety-model` IPC + Transport canvas zones; proven membership vs REVIEW_REQUIRED membership.

### CANONICAL MODEL
Client model from `buildClientModel()`; draft `localStorage siteforge.safetyBuild.v1`; applied `workbook.safety_build`.

### AUTO BUILD populates
Zones ingest on refresh / Transport seed (`ingestRunDiscoveredZones`). No separate Auto Build button.

### ENGINEER edits
Zone rename (`engineering_name` only; `source_id` immutable); add/remove devices; accept suggestions; delete zone; reset/silence sources.

### APPLY does
**Apply Safety** `#sb-apply` → `applySafety()`: merge-save workbook via `autogenWorkbookSave` (never hollow Transport conveyors). Hub status from `syncReadiness()` — does **not** force READY via `setAutogenReadinessApplied`.

### PERSISTS
Local draft continuously; workbook `safety_build` on Apply.

### Reaches AUTOGEN / PLC
Program ES from READY zones; partial/fail-safe shell when review remains.

### REVIEW / ERROR
Unassigned device or non-READY zone → hub soft REVIEW_REQUIRED; Export allowed. INCLUDED Safety ERROR hard-blocks.

### Controls

| Label | Tab | Purpose | Handler | Model mutation | Display vs eng | Persist | Downstream | Prerequisite | Review/error |
|-------|-----|---------|---------|----------------|----------------|---------|------------|--------------|--------------|
| **Refresh discovery** `#sb-refresh` | Safety | Rebuild model; keep overrides | `refreshModel` | Rebuild zones/devices | Mix | Draft | Hub sync | — | — |
| **Apply Safety** `#sb-apply` | Safety | Publish safety_build | `applySafety` | Write `safety_build` | Authoritative | Workbook merge | ES emit | Model present | Soft review OK |
| **Assign Devices…** `#sb-inv-assign` | Safety | Wizard: pick zone + confirm | `openAssignDevicesWizard` | Membership; `membersOrigin=ENGINEER_ASSIGNED` | Authoritative | Draft until Apply | Apply Safety | Checked inventory + zones | Prompt/confirm |
| **Assign Selected → Zone** `#sb-inv-assign-selected` | Safety | Assign checks → selected zone | `assignCheckedToSelectedZone` | Membership ENGINEER_ASSIGNED | Authoritative | Draft | Apply Safety | Checks + selected zone | Status if missing |
| **Assign Selected** `#sb-add-selected` | Safety | Add available → zone | `addSelectedDevices` | Members | Authoritative | Draft | Apply | Zone selected | — |
| **← Remove** `#sb-remove-selected` | Safety | Unassign from zone | `removeSelectedDevices` | Members | Authoritative | Draft | Apply | — | — |
| **Suggestions** `#sb-accept-suggestions` | Safety | Accept digit-match suggestions | `acceptSuggestions` | Members ENGINEER | Authoritative | Draft | Apply | Suggestions present | — |
| **Rename** `#sb-rename-zone` | Safety | Rename engineering_name | `renameSafetyZone` | `engineering_name` / `name`; source_id fixed | Authoritative | Draft | Apply | Logix ident rules | Collision cancelled |
| **Delete zone** `#sb-delete-zone` / zone trash | Safety | Delete Safety Zone | `deleteSafetyZone` | Remove zone | Authoritative | Draft | Apply | Confirm | — |
| **Show on Transportation** `#sb-show-on-transport` | Safety | Highlight + jump Transport | `highlightTransportZone` + `activateTab` | Navigation / highlight | Display | None | None | Zone selected | — |
| Zone list cards | Safety | Select zone | `data-sb-zone` click | Selection ACTIVE | Display | Session | Detail render | — | READY vs REVIEW chip |
| Inventory filter `#sb-inv-filter` / `#sb-device-filter` | Safety | Filter device lists | input handlers | Filter only | Display | Session | None | — | — |

Counts strip: Zones / Ready / Review / E-Stops / Devices Found / Auto Resolved / Engineer Assigned / Unassigned / Completion — display from model.

---

## 4. Sorter Build

### PURPOSE
Configure sorter induct / tracking / diverts from RUN + SiteModel; publish `sorter_build` for Sorter_Track pack.

### RUN / Fortna evidence
SiteModel sorter objects; divert PE authorities (PROVEN / DERIVED / COMMISSIONING / ENGINEER_REQUIRED / REVIEW_REQUIRED / OPTIONAL / UNKNOWN).

### CANONICAL MODEL
`autogenState.sorter` (+ workbook `sorter_build`); localStorage `fortna_sorter_build`.

### AUTO BUILD populates
SiteModel populate on import (`applySiteModelToEditors`) — no dedicated button.

### ENGINEER edits
Type, Transportation Area, induct conv/PE/encoder, track count/rows, divert count/PEs, PE list, tracking offset + state; review Accept/Edit/Commissioning.

### APPLY does
**Apply sorter → Autogen** `#btn-sorter-save`: merge workbook save; READY only if data + phase1 OK + `configuration_required` empty; else REVIEW_REQUIRED (may still set `appliedAt`).

### PERSISTS
localStorage on touch; workbook on Apply.

### Reaches AUTOGEN / PLC
Sorter_Track when hub READY / opt checked during `runAutogenGenerate`.

### REVIEW / ERROR
Review panel counts Review Required / Engineer Required / Commissioning / Optional / Resolved. Soft until INCLUDED ERROR.

### Controls

| Label | Tab | Purpose | Handler | Model mutation | Display vs eng | Persist | Downstream | Prerequisite | Review/error |
|-------|-----|---------|---------|----------------|----------------|---------|------------|--------------|--------------|
| **Accept All Derived** `#btn-divert-accept-derived` | Sorter | Bulk accept DERIVED divert PE | divert accept handler | DERIVED → ENGINEER_ACCEPTED; **never UNKNOWN→PROVEN** | Authoritative | Draft / localStorage | Apply | Derived rows | Soft |
| **Apply PE to Selected** `#btn-divert-apply-pe` | Sorter | Bulk set divert_pe | bulk PE handler | divert_pe + ENGINEER_REQUIRED if not PROVEN | Authoritative | Draft | Apply | Bulk PE value + checkboxes | — |
| **Mark Selected for Commissioning** `#btn-divert-mark-commission` | Sorter | Mark divert_pe COMMISSIONING | commission handler | `authority.divert_pe=COMMISSIONING` | Authoritative | Draft | Apply | Selection | Soft |
| Review **Accept derived** `.sorter-review-accept` | Sorter | Accept DERIVED item | `acceptSorterReviewItem` | `review_resolutions`; ENGINEER_ACCEPTED | Authoritative | Draft | Hub dirty | Review item | — |
| Review **Acknowledge** | Sorter | Accept PROVEN acknowledgment | `acceptSorterReviewItem` | Resolution ACCEPTED | Authoritative | Draft | — | — | — |
| Review **Edit** / **Edit field** / **Enter / commission** `.sorter-review-edit` | Sorter | Focus field for edit | `focusSorterReviewField` | Focus only until edit | Display → eng on change | — | — | focusId | — |
| Review **Confirm commissioning** | Sorter | Confirm COMMISSIONING value | accept with `data-mode=commission` | tracking_offset_authority=COMMISSIONING | Authoritative | Draft | Apply | Offset field | Soft |
| Review **Mark reviewed** | Sorter | Mark field reviewed | `acceptSorterReviewItem` | Resolution | Authoritative | Draft | — | divert_pe / tracking_offset | — |
| **Apply sorter → Autogen** `#btn-sorter-save` | Sorter | Publish sorter_build | sorter save listener | workbook.sorter_build; hub | Authoritative | Workbook | Sorter_Track | Merge-safe vs Transport/Safety | READY or REVIEW_REQUIRED |
| **Clear sorter fields** `#btn-sorter-clear` | Sorter | Reset config | `defaultSorterConfig` | Clear sorter | Engineering reset | localStorage clear | Readiness reset | — | — |
| Type / Area / Induct / Track / Divert / PE / Offset editors | Sorter | Author config | change → `touchSorter` | `autogenState.sorter` | Authoritative draft | localStorage | Apply | RUN / SiteModel | Dirties hub |

---

## 5. Sawtooth Merge

### PURPOSE
Collector / lane saw-merge design (PLC4 pattern) → `Sawtooth_Merge` pack.

### RUN / Fortna evidence
SawMerge/SawLane (and HS*) tables via SiteModel auto-populate on import. Lane count is RUN-owned (readonly `#saw-lane-count`).

### CANONICAL MODEL
`autogenState.sawtooth` / `workbook.sawtooth_build`; localStorage `fortna_sawtooth_build`.

### AUTO BUILD populates
`applySiteModelToEditors` on import.

### ENGINEER edits
Collector/downstream conv, encoder, speeds, jam/EOW PEs, area, track PEs, gap/timer/IPP params, enable flags.

### APPLY does
**Apply sawtooth → Autogen** `#btn-saw-save`: `persistSawtoothToWorkbook` + workbook save; READY iff configured and `configuration_required` empty; else REVIEW_REQUIRED.

### PERSISTS
localStorage on touch; workbook on Apply.

### Reaches AUTOGEN / PLC
Sawtooth_Merge when READY / opt checked.

### REVIEW / ERROR
Unresolved keys → REVIEW_REQUIRED; FOUND-not-INCLUDED does not hard-block Partial Build.

### Controls

| Label | Tab | Purpose | Handler | Model mutation | Notes |
|-------|-----|---------|---------|----------------|-------|
| **Apply sawtooth → Autogen** `#btn-saw-save` | Sawtooth | Publish | saw-save listener | workbook + hub READY/REVIEW | Merge-safe |
| **Reload from RUN** `#btn-saw-reload-sitemodel` | Sawtooth | Discard local; reload SiteModel | `applySiteModelToEditors` | Reset from RUN | Confirm intent via title |
| **Clear** `#btn-saw-clear` | Sawtooth | Reset | `defaultSawtoothConfig` | Clear + readiness | — |
| **Prefill PLC4 demo** `#btn-saw-defaults-plc4` | Sawtooth | DEV hardcoded | demo fill | **Not for acceptance** | Hidden/dev |
| Lane/collector/encoder/PE/param fields | Sawtooth | Author config | renderSawtoothBuild binders | `autogenState.sawtooth` | Engineer edits |

*(Merge is not a separate primary nav tab; 2-to-1 merges live on Transport canvas + Autogen opt `merges-2to1`.)*

---

## 6. PLC Autogen (Autogen / Build / Export)

### PURPOSE
Compile hub: readiness cards + **Export L5X Package** (`#btn-autogen-from-run` → `runAutogenGenerate('run')` → `fortnaAPI.autogenGenerate` → `fortna_autogen.py`).

### RUN / Fortna evidence
Active RUN + merged workbook (Transport, Safety, Saw, Sorter, Hardware overrides).

### CANONICAL MODEL
`workspace/autogen_workbook.json` (stable; survives RUN clear unless project clear).

### AUTO BUILD populates
Workbook build / Refresh site config re-scans RUN (keeps edits).

### ENGINEER edits
Pack checkboxes, site config table, catalog chips, Twin patches, Excel path (advanced).

### APPLY does
Subsystem Applies elsewhere; hub **From Transport** / **Save** / workbook Save publish workbook facets. Export is Build, not Apply.

### PERSISTS
Workbook on Save / subsystem Apply; L5X under `exports/autogen` (+ current).

### Reaches PLC COMPILER
Engineer opens L5X in Studio 5000 manually. App **does not launch Studio**.

### REVIEW / ERROR
Soft reviews logged; Safety partial → `BUILD GENERATED WITH REVIEW ITEMS`. Hard ERROR blocks Export.

### Controls

| Label | Tab | Purpose | Handler | Mutation / effect |
|-------|-----|---------|---------|-------------------|
| **Export L5X Package** `#btn-autogen-from-run` | Autogen | Build PLC package | `runAutogenGenerate('run')` | Writes exports; preflight soft/hard; no Studio launch |
| **Refresh site config** `#btn-autogen-workbook-build` | Autogen | Re-scan RUN | workbook build IPC | Keeps edits |
| **Save** `#btn-autogen-workbook-save` | Autogen | Persist workbook | `autogenWorkbookSave` | Disk workbook |
| Browse library / Excel / Inspect / Generate | Autogen | Advanced/legacy | various | Excel path optional |
| Twin Refresh / Search / Propose / Apply | Autogen | Gap patches | twin IPC | Patches into workbook |
| Open out / Reveal L5X / Copy path | Autogen | Open outputs | `openPath` / clipboard | Display of outputs |
| Catalog Add buttons | Autogen | Site config rows | cat add handlers | Catalog chips |
| Pack opts Sys/System/Logic/IO_MAP/merges/sorter/saw/wcs… | Autogen | Include packs | checkbox change | Generate options (IO_MAP always on) |
| Hub **From Transport** `#btn-hub-from-transport` | Autogen | Pull Transport graph | `applyTransportMergesToAutogen` | Workbook |
| Hub **Save Transport WB** `#btn-hub-save-transport-wb` | Autogen | Save workbook | workbook save | Disk |
| **Clear current project builds** `#btn-clear-project-builds` | Autogen | Wipe project state | `clearCurrentProject` | Clears RUN/edits/Transport/Saw/Sorter/outs — not libraries |
| Tab jumps to I/O / Transport / Saw / Sorter / Safety | Autogen | Navigation | `data-jump-tab` | Display |

Always-included packs: Sys · Devices_Comm · NTP · System_Logic · System · IO_MAP.  
Evidence packs: Sawtooth_Merge, Sorter_Track, merges, WCS / ShippingSorter when SiteModel supports.

---

## 7. Workspace / Docs / Recipes / System (secondary)

### Workspace `#tab-workspace`
| Control | Handler | Role |
|---------|---------|------|
| Browse archive `#btn-browse-archive` | `selectArchive` / import | Alternate RUN Import |
| Open folder / Exports | `openPath` | Display |
| Clear workspace `#btn-clear-workspace` | `clearWorkspace` | Keeps workbook by design in main |
| Dropzone | import | Same as browse |

### Docs `#tab-search`
Search + quick badges → `searchDocs`; **Reindex** `#btn-reindex` → `reindexDocs`. Display-only vs engineering models.

### Recipes `#tab-recipes`
Recipe list + params; **Apply** `#btn-apply` → `fortnaAPI.applyRecipe`. Mutates RUN tables (clone device, add PE, etc.); **not** Autogen workbook Apply.

### Hidden System panes
`#tab-plc` / `#tab-ignition` — legacy PLC export / Ignition builders (`exportPlc`, `ignitionBuildLayout`). Not in primary nav. Window chrome Minimize/Maximize/Close → `fortnaAPI.*`.

---

## Persistence map (engineering-authoritative)

| Surface | Local draft | Published artifact | Consumer |
|---------|-------------|--------------------|----------|
| Transport canvas | localStorage `siteforge.transportBuild.v2` | workbook via `transport-apply-autogen` | Autogen areas/merges |
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
| `importRun` | `import-run` | I/O / Workspace Load RUN |
| `transportAutoBuildFromRun` | `transport-auto-build-from-run` | Transport Auto Build / Rebuild |
| `transportApplyAutogen` | `transport-apply-autogen` | Apply to Autogen |
| `autogenGenerate` | `autogen-generate` | Export L5X Package (Build PLC) |
| `autogenWorkbookBuild/Save/Load` | `autogen-workbook-*` | Site config / Apply merges |
| `buildSafetyModel` | `build-safety-model` | Safety discovery |
| `getHardwareIo` / `saveHardwareIoChannel` | hardware IO | I/O CAD Name/Generate |
| `clearCurrentProject` | `clear-current-project` | Hub clear |
| `applyRecipe` / `searchDocs` / `reindexDocs` | recipe / docs | Recipes / Docs |

---

## GATE N — In-product help

| Affordance | Location | Behavior |
|------------|----------|----------|
| **?** Help button `#btn-sf-help` | Title bar | Opens `#sf-help-drawer` |
| Help drawer | Right slide-over | Section list (this manual outline) + control lookup from `SITE_FORGE_HELP` keyed by control `id` |
| Contextual | Optional “Inspect” toggle in drawer (`#sf-help-inspect`) | Next click on a control with an `id` shows its purpose from the map (no giant modal) |

Source of truth for copy: this manual + the JS map kept in sync for high-traffic controls.

**Still present:** Help **?** (`#btn-sf-help`) and **Inspect next control click** (`#sf-help-inspect`) — unchanged handlers in `initSiteForgeHelp()`.

---

## Runtime provenance controls (handler-traced)

| Affordance | Control id | Handler / IPC | Behavior |
|------------|------------|---------------|----------|
| Title-bar SHA chip | `#sf-runtime-sha` | click → `sfHelpSetOpen(true)` + `loadRuntimeProvenance()` + `runSiteForgeFeatureSelfCheck()` | Shows short Git SHA; opens Help → Runtime |
| Help → Runtime panel | `#sf-help-runtime` | filled by `loadRuntimeProvenance()` → `fortnaAPI.getRuntimeProvenance` → IPC `get-runtime-provenance` | Git SHA, branch, startedAt, repo/source root, dashboard path, python/compiler, mode |
| Copy Runtime Info | `#sf-help-copy-runtime` | `copyRuntimeInfo()` → `fortnaAPI.clipboardWriteText` | Copies provenance + diagnostics JSON |
| Help → Diagnostics | `#sf-help-diagnostics` | `runSiteForgeFeatureSelfCheck()` (+ IPC `runtime-feature-self-check`) | Live checks: Help DOM, `hwChannelEndpointLabel(UNRESOLVED_OWNER)`, `classifyDevice` VFD rules, python `classify_cp_io_operand` |
| Diagnostics Re-run | `#sf-help-run-selfcheck` | `runSiteForgeFeatureSelfCheck()` | Re-exercises the same live functions |
| Help → Logs path | `#sf-help-logs` | IPC `list-latest-log` / `get-logs-dir` | Shows latest `exports/logs/site_forge_*.log` path (no full viewer) |
| Reveal logs folder | `#sf-help-reveal-logs` | `openPath(logsDir)` via IPC `get-logs-dir` | Opens `exports/logs` in Explorer |

Launch provenance write path: `desktop/Launch-Electron.ps1` → `desktop/.runtime_build.json`; collector `tools/scripts/fortna_runtime_provenance.py`.  
Full launcher audit: `docs/SITE_FORGE_LAUNCH_RUNTIME_PROVENANCE.md`.

### Gate 7 — Site Forge logs + I/O trace CLI

| Item | Path / command |
|------|----------------|
| Log writer | `tools/scripts/fortna_site_forge_log.py` → `append_log(event_type, payload)` |
| Log files | `exports/logs/site_forge_<timestamp>.log` (JSON lines; runtime SHA via `fortna_runtime_provenance` when available) |
| Hardware I/O build summary | `python tools/scripts/fortna_hardware_io_model.py --run-dir <RUN>` emits `hardware_io_model_build` log line |
| I/O channel trace CLI | `python tools/scripts/fortna_io_channel_trace.py [--run-dir <RUN>]` — emits `io_channel_trace` summary log line via `append_log` |
| Latest / dir helpers | `python tools/scripts/fortna_site_forge_log.py --latest` · `--logs-dir` · `--list` |

---

## Counts (this gate)

| Metric | Count |
|--------|-------|
| Visible primary engineering tabs | **6** (I/O, Transport, Safety, Sorter, Sawtooth, Autogen) |
| Secondary tool tabs | **3** (Docs, Workspace, Recipes) |
| Tab panes in `ALL_TABS` | **11** (includes hidden plc + ignition) |
| Documented user-facing controls (inventory rows) | **92** (Controls sections; +vocab/persist/IPC tables elsewhere) |
| Transportation-specific controls traced to real handlers | **Yes** — Connect, Fit System, zoom −/+, Home, 100%, Geometry mode, Undo, Redo, Apply Area/ES, Create/Add/Remove Area, Select Chain, Mark Terminal, right-click/context, Apply to Autogen, Build PLC |
| Safety / Sorter / Hardware specifics | **Yes** — Assign Devices, Apply Safety, Safety rename, Sorter Accept/Edit/Commissioning, divert bulk, module/channel selection, Name, Generate, Spare/Status |
| In-product help | **YES** — Help drawer + `SITE_FORGE_HELP` map |
| Runtime provenance UI | **YES** — Help → Runtime + `#sf-runtime-sha` + Copy Runtime Info |
| Feature self-check (31add80) | **YES** — Help → Diagnostics (live function exercise) |
| Site Forge logs (Gate 7) | **YES** — `exports/logs` + Help → Reveal logs folder |

---

*End of Gates L/M/N/O Engineering UI Manual. Implementation-traced; no UI redesign; no held-back site search.*
