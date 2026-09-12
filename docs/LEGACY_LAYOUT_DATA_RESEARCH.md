# Fortna Legacy GUI Layout Data Research (Parts E–F)

**Date:** 2026-09-12  
**Branch:** `feature/site-forge-integration-checkpoint`  
**Scope:** Accessible RUN extracts, configs, training docs, HELP, and allowed binary string inventory  
**Constraints:** No decompilation; no license defeat. Formats not invented — confidence labeled HIGH / MEDIUM / LOW.

---

## Executive summary

Legacy FortnaPlus draws the plant schematic from **`Conveyor.asc` geometry columns** (`X_cord`, `Y_cord`, `Width`, `Length`, `Angle`, plus curve fields), filtered by **layer sets** and framed by **Photon views / maps**. There is **no separate proprietary layout file** in the RUN archives for conveyor body geometry — the ASC tables *are* the layout database.

Site Forge already uses the core geometry fields correctly under `docs/RUN_GEOMETRY_CALIBRATION.md` (`greensboro-infeed-v1`). Additional GUI tables (`PhView`, `PhMap`, `edworld`, `Layerset`/`Layerson`, `gui.cfg`, color tables) describe **operator screen presentation**, not mechanical topology.

**Topology** (downstream / merge lanes) is **not** encoded as a populated conveyor-successor graph in this Greensboro RUN: `Convpath.asc` / `Pathsets.asc` are placeholders; merge topology lives in control tables (`MergeInputs.asc.<machine>`, `MergeBoss`, etc.).

---

## Sources searched

| Location | Present | Role for layout |
|----------|---------|-----------------|
| `workspace/active/RUN` | Yes (primary Greensboro ORNCCP2) | Full FORTNA ASC + GUI binaries + configs |
| `workspace/cp4-run/RUN` | Yes | Same schema; different PhView camera positions |
| `workspace/active_rio_audit/RUN` | Yes | Same schema family |
| `workspace/_reno_peek/*/RUN` | Yes (PACK/PICK/SHIP) | Same schema; site-specific PhView names |
| `docs/training/` | Yes | Screen-capture / dashboard wallpaper setup; ViewIO docs |
| `tools/scripts/` | Yes | Geometry consumers (`fortna_physical_geometry.py`, etc.) |
| QNX ELF binaries in RUN | **Yes** (`fpgui`, `fpctrl`, `fpserv`, `fpsort`, `fpsrv1`, `fpsrv2`, …) | String/path evidence only (Part F) |

Non-layout binaries also present (`clrram.bin`, `ktxpcl.bin`, `Scanner.bin`, Ignition `data.bin`) — not schematic layout sources.

---

## 1. Primary layout data: `Conveyor.asc`

### 1.1 Schema (60 columns)

Delimiter: `~`. Header present on line 1. Active Greensboro table: **6000 rows** (many `Type=INVALID` placeholders).

Mechanical conveyors on active RUN (`STRAIGHT`/`CURVE`/`BELT`/`ZEROPRESSURE`/`TRIANG`): **485**.

### 1.2 Fields already used by Site Forge (geometry / identity)

| Field | Semantic meaning | Confidence | Site Forge use |
|-------|------------------|------------|----------------|
| `IO_Name` | Equipment tag (P###) | **HIGH** | Identity |
| `Type` | Draw/object class (`STRAIGHT`, `CURVE`, `BELT`, `ZEROPRESSURE`, `TRIANG`, …) | **HIGH** | Body renderer / curve branch |
| `X_cord`, `Y_cord` | **Infeed / ENTRY end** (not footprint center) | **HIGH** | Placement |
| `Angle` | Flow direction at infeed, deg CCW from +X | **HIGH** (non-curve) | Orientation |
| `Length` | Centerline body length; **`-1` sentinel on CURVE** | **HIGH** | Linear body; curve skip |
| `Width` | Cross-belt / frame width (drawing units) | **HIGH** | Body width |
| `Inside_Radius` | Inner radius of curve | **HIGH** | Curve body |
| `Infeed_Tangent`, `Discharge_Tangent` | Tangent **stub lengths** (drawing units), not topology FKs | **HIGH** | Curve stubs |
| `IO_Address_Word` / `Bit` | Controller scoping | **HIGH** | Ownership filter |
| `In Motor Chain` | Motor-chain membership flag | **HIGH** | Drive association assist |
| `Machine_Name` | Sparse on mechanical rows; denser on devices | **MEDIUM** | Ownership hint |
| `Infeed_Elevation`, `Discharge_Elevation` | Vertical elevations (drawing units) | **MEDIUM** | Future 3D / grade; unused in 2D schematic today |
| `NoseOver` | Equipment feature (`Double Noseover`, …) | **MEDIUM** | Annotation only; not topology |
| `Drive` | Drive index / presence (numeric when set) | **MEDIUM** | Drive classification assist |
| `Part_Number`, `Electrical Drawing Page No.`, `General_Description` | Engineering metadata | **MEDIUM** | Labels / print cross-ref |
| `Motor` | Direct motor column on mechanical rows | **LOW** on this sample (empty) — use `Mtrchain.asc` | Prefer Mtrchain |

Binding transform: `docs/RUN_GEOMETRY_CALIBRATION.md`. Implementation: `tools/scripts/fortna_physical_geometry.py`.

### 1.3 Present but unused / weak for Site Forge geometry

| Field | Observed fill (mech 485) | Likely meaning | Confidence | Recommendation |
|-------|--------------------------|----------------|------------|-----------------|
| `Layer` | 10/485 non-zero on mech; many motors Layer=9, PEs Layer=4 | GUI display layer (0 = always shown) | **HIGH** (HELP) | Optional Site Forge layer filter; **not** mechanical elevation |
| `Default Colors` | 485/485 (`CONV_RUNNING`, `GRAVITY`, …) | Runtime colorset name for draw state | **HIGH** | Optional status styling; not geometry |
| `Drawstate` / `Was_Drawstate` | 403/485 | Runtime draw/IO visual state | **MEDIUM** | Live HMI only; ignore for static import |
| `Font`, `Underline` | Font always `char8`; Underline often `250` on ZP | Text / ZP zone pitch? | Font **HIGH**; Underline **LOW** | Ignore for geometry |
| `c`, `b` | CURVE: `b` often 0/90/180/270/450; ZP: `c=30`, `b`≈Length/250 | See §1.4 hypotheses | **MEDIUM** / **LOW** | Investigate before use; do not invent |
| `Belt_Width` | 24/485; typically 150 while `Width`=200 | Physical belt vs frame width | **MEDIUM** | Optional annotation; keep using `Width` for body |
| `Belt_Info` | 0/485 | Belt type lookup (`belt.asc`) | **LOW** on this sample | Skip unless populated elsewhere |
| `Roller_Centers` | 283/485 (e.g. 33.333) | Mechanical roller pitch | **MEDIUM** | Spec data, not schematic topology |
| `Tapered_Rollers` | 0/485 | Flag | **LOW** | Skip |
| `Supports` | 250/485 (`Tri`, …) | Support style catalog | **MEDIUM** | Spec / BOM, not layout graph |
| `Price` | 0/485 | Cost | **HIGH** unused | Skip |
| `Good_color` / `Bad_color` | 0/485 | Per-part color overrides | **LOW** | Prefer `Default Colors` + `Colors*.asc` |
| `Gen_Flag`, triggers, `ErrLink`, `ErrTime`, `Gen_Security` | Mostly empty | Logic / security hooks | **LOW** for layout | Skip for Site Forge layout |
| `Speed` | 211/485 | Design FPM | **MEDIUM** | Metadata only |
| `Contact_Type`, `Recomended_Spares`, `IO_Module_Type`, `Device_Description` | Empty on mech | Catalog fields | **LOW** here | Skip |

### 1.4 Hypotheses (not binding)

**Curve field `b` as absolute exit bearing (MEDIUM):**  
On sampled CURVE rows, `b` (mod 360) matches a **90° CW** exit from `Angle` (e.g. P108 Angle=270 → b=180; P112 Angle=0 → b=270; P104 Angle=90 → b=0; P434 Angle=180 → b=450≡90). If confirmed, Site Forge can replace the current CW/CCW heuristic with an explicit exit angle. **Not confirmed in HELP text** — treat as investigation item, not calibration.

**ZEROPRESSURE `c`/`b`/`Underline` as zone parameters (LOW–MEDIUM):**  
All ZP rows sampled have `c=30`, `Underline=250`, and `b ≈ Length/250`. Suggests accumulation zone count / pitch for `ph_draw_zp`, not conveyor topology. Do not map to downstream.

---

## 2. GUI presentation tables (screen, not mechanical twin)

### 2.1 Views, maps, world extents

| Table / file | Fields | Meaning | Confidence | Site Forge use |
|--------------|--------|---------|------------|----------------|
| `PhView.asc` | `Name`, `X`, `Y`, `Z`, `Fill Color`, `State`, `Layer_Set`, `Map`, `Lock`, `RotateV`, `RotateH` | Named operator camera / viewport bookmarks (site-specific names differ active vs reno vs cp4-run) | **HIGH** | Optional “Fit to legacy view” presets |
| `PhMap.asc` | `UpperLeftX/Y`, `LowerRightX/Y`, `RotateV/H` | Map = sub-rectangle of conveyor screen | **HIGH** (HELP `Map.htm`) | Optional region bookmarks; Greensboro Map #0 extents often zeroed |
| `edworld.asc` | `View_Name`, `Left`, `Right`, `Bottom`, `Top`, `Layer_Set`, `BackGround_Color` | Virtual world / clip extents (“Set World Views”) | **MEDIUM** | Diagnostic bounds; active sample mostly placeholder except `ALL` |
| `PhPos.asc` | `Owner`, `X`, `Y`, `W`, `H` | **Window** positions (Help, IO, Start Stop, …) — **not** plant XY | **HIGH** | Do **not** import as equipment coords |
| `Layerset.asc` / `Layerson.asc` | Set name; Y/N per layer 0–20 | Layer 0 always drawn; other layers toggled per set | **HIGH** (HELP) | Optional visibility groups |
| `gui.cfg` | `DrawConveyor`, `AnimateGear`, `DrawCursorPosition`, refresh ms | GUI draw toggles | **HIGH** | Confirms conveyor drawing is first-class; no extra geometry |
| `ScreenCapture.asc` | `StartPageX/Y`, `EndPageX/Y`, `FileName` | Dashboard wallpaper capture rectangle (e.g. 0,0–1200,1200 → `fpcscreen`) | **HIGH** (training txt) | Not plant layout; image export pipeline |
| `Animate.asc` | `X_COORD`, `Y_COORD`, `Conv`, `Angle`, `Progress`, … | Runtime carton animation slots (placeholders here) | **HIGH** schema / **LOW** data | Ignore for static import |
| `PeDisplay.asc` | `ConveyorRec`, `Location`, … | PE display overlays (unpopulated here) | **MEDIUM** schema | Future PE callouts |
| `Colors.asc` / `Colorset.asc` / `Convclr.asc` / `ColorsGUI.asc` | RGB + named sets | HMI palette | **HIGH** | Optional theming |
| `convtype.asc` | `Object_type` | Enum of drawable types incl. `ZOOMBOX`, `DASHLINE`, `IMAGE` | **HIGH** | Type allow-lists |
| `Images.wgtp` | Photon widget pack | Icons (zoombox, buttons, …) | **HIGH** (strings) | Not vector layout |
| `dds.xml` | `control_posX/Y/width/height` | Print-and-Apply status GUI layout | **HIGH** | Unrelated to plant schematic |
| `Display.config.*` / `Display.dat.*` | HistData menu wiring | Separate `/usr/local/bin/Display` stats app | **HIGH** | Not conveyor layout |

### 2.2 Training / HELP evidence

- `docs/training/.../SendConvImage.txt` and `ConvPhs2Png_Setup.txt`: GUI process captures conveyor **screen** to PHS/BMP/PNG for Dashboard wallpaper — confirms schematic is drawn live from ASC, then rasterized.
- HELP `Layerset.htm`: parts belong to numbered layers; layer 0 always displayed.
- HELP `Map.htm`: maps are coordinate rectangles on the conveyor screen.
- HELP `PhView.htm`: virtual screen dimensions mapped onto actual screen.
- HELP `GUIProcs.htm`: Zoom In/Out, Map, Focus to conveyor, Rotate conveyor V/H.

---

## 3. Topology / route / link tables (adjacent to layout)

| Table | Finding on Greensboro active | Confidence | Site Forge use |
|-------|------------------------------|------------|----------------|
| `Convpath.asc` | 1000 placeholder rows; **0** P→P edges | **HIGH** | Do not expect topology |
| `Pathsets.asc` | Unpopulated named paths | **HIGH** | Same |
| `MergeInputs.asc.<machine>` | Populated lane/boss/PE/release links (e.g. `MergeInputs.asc.ORNCCP2`) | **HIGH** | Merge control topology (not XY) |
| `MergeBoss.asc` / `MergeRoute.asc` / `HSSawMerge.asc` / … | Control merge families | **HIGH** schema | Existing merge modules |
| `Mtrchain.asc` | Motor → chained P-tags | **HIGH** | Drive grouping |
| `Trigrset.asc` | `loc`/`loc2`/`loc3` trigger locations | **MEDIUM** | Logic hotspots, not body geometry |
| `Connect.asc` / `Machine.asc` | Host/machine comms | **HIGH** | Not plant layout |

---

## 4. Conveyor.asc: used vs unused (checklist for Site Forge)

### Used today for physical schematic

`X_cord`, `Y_cord`, `Angle`, `Length`, `Width`, `Type`, `Inside_Radius`, `Infeed_Tangent`, `Discharge_Tangent` (+ identity / scoping columns listed in §1.2).

### Noted but not driving body geometry

`NoseOver`, elevations, `Drive`, `In Motor Chain`, drawing page, part number, `Layer` (overlap research only).

### Unused for Site Forge layout (safe to defer)

`Belt_Info`, `Belt_Width` (prefer `Width`), `Roller_Centers`, `Tapered_Rollers`, `Supports`, `Price`, `Good_color`/`Bad_color`, `Font`/`Underline`, `c`/`b` (until hypothesis proven), `Drawstate`/`Was_Drawstate`, trigger columns, `ErrLink`/`ErrTime`, `Gen_Security`, `Gen_Flag`, `Bitstate`/`Was_Bitstate`, `Contact_Type`, `Recomended_Spares`.

---

## 5. Site Forge recommendations

1. **Keep** `greensboro-infeed-v1` as binding geometry (`docs/RUN_GEOMETRY_CALIBRATION.md`). Do not reintroduce footprint-center placement.
2. **Import** mechanical `Conveyor.asc` rows with usable XY as PhysicalConveyor bodies; derive exit anchors via existing curve model.
3. **Optionally import** `PhView.asc` named views as camera presets (per-RUN, not portable across sites without remapping).
4. **Optionally honor** `Layer` + `Layerson` for display filtering (motors on 9, some PEs on 4) — presentation only.
5. **Do not** treat `PhPos`, `Display.dat`, `dds.xml`, or `Animate.asc` as plant coordinates.
6. **Do not** expect `Convpath`/`Pathsets` to supply downstream; continue geometric mating + engineer Transport Build + merge ASC tables.
7. **Investigate** CURVE column `b` as exit bearing (MEDIUM) before changing curve turn logic — validate against known mates (P102→P104, P126→P128, etc.).
8. **Machine-scoped ASC**: prefer `*.asc.<MACHINENAME>` overlays when present (e.g. `MergeInputs.asc.ORNCCP2`).
9. **Units**: drawing units are site-consistent floats (Greensboro examples ~5e4); canvas applies uniform scale + Y flip without mutating RUN values.

---

## 6. Part F — QNX binary investigation plan

### 6.1 Binaries found in this repo

ELF binaries **are present** under RUN roots (example: `workspace/active/RUN/`):

| File | Approx size | Magic | Role (from startup scripts / strings) |
|------|-------------|-------|----------------------------------------|
| `fpgui` | ~8.4 MB | ELF 32-bit LE | GUI / Photon drawing process |
| `fpctrl` | ~4.9 MB | ELF | Control process |
| `fpserv` / `fpsrv1` / `fpsrv2` | ~8.9 MB | ELF | Service processes |
| `fpsort` | ~4.9 MB | ELF | Sort process |
| `rtadrv` | ~0.45 MB | ELF | RTA driver |
| `watcher` | ~73 KB | ELF | Watchdog |
| `OptomuxEthernet` | ~127 KB | ELF | I/O |

Startup: `Start_UPS_Batch` → `UPS_Batch` → `./fortna` under `/SortPlus/RUN`, with sibling processes `fpgui|fpctrl|fpsort|fpserv|fpsrv1|fpsrv2|watcher`.  
`project.cfg`: `FORTNADIR=./FORTNA`, `PROJECTDIR=./PROJECT`, `MACHINENAME=ORNCCP2`.  
`SystemFiles/Fortna.tgt`: `target = /SortPlus/RUN/Start_UPS_Batch`.

**Allowed tooling only:** `file`, `strings`, `readelf` (or equivalent). **Do not** decompile, disassemble for logic reconstruction, or bypass licensing (`support.cfg` license checks exist in strings).

### 6.2 Already observed via strings on `fpgui` (repo copy)

Useful path / table evidence (no decompile):

- Loads `/gui.cfg`, `project.cfg`, `identity.cfg`, `./FORTNA`, `/SortPlus/`.
- ASC path patterns: `%s/%s.asc`, `%s/%s.asc.%s`, `%s/PROJECT/%s.asc.%s`.
- Menu binaries: `fortna.mnu`, `project.mnu`.
- Table symbols: `edworld`, `PhView`, `PhPos`, `PhMap`, `Layerset`, `Layerson`, `Animate`, `ScreenCapture`, `Convpath`, `Pathsets`, `DrawConveyor`.
- Geometry symbols: `X_cord`, `Y_cord`, `inside_radius`, `Single Noseover` / `Double Noseover`.
- Draw helpers: `ph_draw_straight`, `ph_draw_curve`, `ph_draw_belt`, `ph_draw_zp`, `ph_draw_triang`, `ph_draw_zoombox`, `ph_get_bound_4_curve`, `getcurveout`.
- Legacy note: `assuming obsolete wxypos.wx and wy==0 ....for QNX6 Conversion`.
- Widget pack: `Images.wgtp`.
- Version breadcrumb: `Version-11.36.0-Release-0`.

### 6.3 Plan when investigating on a Fortna PC (or these ELFs)

Run only:

```text
file fpgui fpctrl fpserv fpsort
readelf -h fpgui
readelf -d fpgui          # NEEDED libs (Photon, etc.)
strings -a fpgui | grep -E '\.asc|\.cfg|\.mnu|SortPlus|FORTNA|X_cord|ph_draw|gui\.cfg|edworld|PhView|PhMap|Inside|Tangent|Nose'
strings -a fpctrl | grep -E '\.asc|Convpath|Merge|Mtrchain|project\.cfg'
```

**Look for (checklist):**

1. Confirmed layout file paths → expect `FORTNA/Conveyor.asc` (+ machine suffix), not a hidden `.lay`/`.dwg` runtime file.
2. Config paths → `/SortPlus/RUN/gui.cfg`, `project.cfg`, `identity.cfg`, optional `support.cfg`.
3. Draw entry symbols → `ph_draw_*`, `PrintMainScreen`, `fpcscreen`.
4. Any remaining references to obsolete `wxypos` or alternate coordinate stores.
5. Shared-memory names (`/dev/shmem/fortna_%s`) — runtime only; not portable layout export.
6. On a live QNX panel: locate `/SortPlus/RUN`, confirm ASC mtimes match on-screen schematic, capture one `ScreenCapture` PNG for visual regression against Site Forge render (optional).

### 6.4 If binaries were absent

They are **not** absent in this worktree. If a future extract omits ELFs, the ASC/`gui.cfg`/HELP evidence above still defines layout; repeat §6.3 on the Fortna PC’s `/SortPlus/RUN` copy.

---

## 7. Confidence summary

| Claim | Confidence |
|-------|------------|
| Conveyor body layout lives in `Conveyor.asc` XY/Angle/Length/Width (+ curve fields) | **HIGH** |
| XY = infeed/entry end | **HIGH** |
| CURVE `Length=-1`; use IR + tangents | **HIGH** |
| Tangents are not topology FKs | **HIGH** |
| Layer is GUI visibility, not elevation | **HIGH** |
| PhView/PhMap are operator views/maps | **HIGH** |
| Convpath empty ⇒ no RUN successor graph | **HIGH** |
| `b` on CURVE = exit bearing | **MEDIUM** (hypothesis) |
| ZP `b`/`c`/`Underline` = zone pitch/count | **LOW–MEDIUM** |
| No other binary layout blob required for first-pass twin | **HIGH** |

---

## 8. Artifacts

- This document: `docs/LEGACY_LAYOUT_DATA_RESEARCH.md`
- Inventory JSON: `exports/layout-research/source_inventory.json`
- Prior binding geometry: `docs/RUN_GEOMETRY_CALIBRATION.md`, `docs/RUN_GEOMETRY_INVESTIGATION.md`, `docs/RUN_SITE_MODEL_DISCOVERY.md`
