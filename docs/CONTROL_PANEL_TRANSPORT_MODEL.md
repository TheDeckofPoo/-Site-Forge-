# Control Panel — Transport Build Model

**Status:** Presentation / organizational metadata  
**Scope:** Transport Build canvas only — does **not** change PLC generation

---

## Hierarchy

```
Site / Plant
  └── PLC / Controller          (e.g. ORNCCP2 — ownership, I/O, Autogen scope)
        └── Control Panel (CP)  (e.g. CP1, CP2, CP3 — organizational grouping)
              └── Conveyor run / Area / ES Zone
```

| Layer | What it means | Affects PLC / Autogen? |
|-------|---------------|------------------------|
| **PLC / Controller** | Machine_Name, IO word banks, ControllerScope | **Yes** — ownership + generation |
| **Control Panel (CP)** | Physical panel / print grouping for engineers | **No** — Transport UI only |
| **Area / ES Zone** | Autogen area + safety zone | **Yes** — engineer-configured |

A single PLC may own equipment drawn across one or more control panels.  
CP tags help the engineer organize the schematic; they are **not** a substitute for controller ownership.

---

## Node property

```js
node.controlPanel = "" | "CP1" | "CP2" | "CP3" | "Other"
```

- Default: `""` (unassigned — engineer fills in)
- Persisted on nodes in `siteforge.transportBuild.v2` localStorage (additive field; no schema bump required)
- **Excluded** from `buildCanonicalApplyGraph()` — Apply to Autogen ignores it
- Must **not** change: controller ownership, I/O mapping, Area, ES Zone, downstream, or L5X

Optional provenance (UI only):

- `controlPanelProvenance: "RUN_EXPLICIT" | "ENGINEER" | "CLEARED" | "UNKNOWN"`

---

## Evidence rules (auto-populate)

Auto-populate **only** when RUN evidence is clear. If unsure → leave `""`.

| Evidence | Action |
|----------|--------|
| `Machine_Name` contains explicit `CP#` token (e.g. `…_CP2_…`) | Set `CP#` |
| `Machine_Name` trailing embed (e.g. `ORNCCP2`, `MSCRENOCP3`) | Set `CP#` |
| `Machine_Name` blank / `N/A` / `NONE` / `ALL` | Leave empty |
| Ambiguous or multi-owner IO word without clear CP token | Leave empty |
| External / display-context stub without clear CP | Leave empty |

IO word ownership remains a **controller-scope** signal. It may *support* human review of which PLC owns a tag; it does **not** by itself invent a Control Panel value unless a CP token is explicit in the machine/panel naming evidence above.

Engineer multi-select assign always wins (`CP1` / `CP2` / `CP3` / `Other` / `Clear`).

---

## UI behavior

- **Filter toggles** (CP1/CP2/CP3): highlight matching bodies; dim others. Multiple toggles may be on.
- **Select** next to each filter: selects that CP group for group-move.
- **Bulk bar**: assign CP to the current selection.
- **Tint / badge**: stroke color + small CP label — connectivity wires unchanged.
- **Group move**: multi-select **or** active CP filter group moves as a unit, preserving relative `pathCanvas` / `entryCanvas` / `exitCanvas` geometry (not `sourceX/Y`). Undo stack entry pushed (≥20; Pass2 history max 50).

---

## Firewall

Never let `controlPanel` flow into:

- workbook conveyor rows as ownership
- Autogen Area / safety zone inference
- L5X generation inputs
- ControllerScope filtering

Canonical Apply still strips presentation fields (`display_*`, `pathCanvas`, `controlPanel`, …).
