# Transport Build — Rectangle Selection & Area from Selection

**Status:** UI workflow (Pass 2)  
**Scope:** `dashboard/transport-build.js`, `dashboard/transport-build-pass2.js`, `dashboard/index.html`  
**Firewall:** Does **not** change fortna_autogen transport/IO, conveyor section model, physical layout placement, or Fast/Slow generation.

---

## What Area means

**Area is engineer metadata** — an organizational label the engineer assigns so Apply→Autogen can map conveyors into workbook / `main_area` rows.

| Concept | Role | Affects PLC ownership? |
|---------|------|------------------------|
| **Area** | Engineer-named group for Autogen area mapping | Indirectly via existing Apply `main_area` mapping only |
| **ES Zone** | Safety zone string on conveyors | Yes — engineer-configured safety |
| **Control Panel (CP)** | Presentation / print grouping | **No** — UI only |
| **Controller / Machine_Name** | True PLC ownership | **Yes** — never invented by Area tools |

Area assignment:

- Is **never inferred from geometry** (marquee box, pathCanvas extents, or spatial clusters).
- Always comes from an explicit engineer action: name prompt, Build Context, or bulk Area dropdown + Apply.
- Uses `moveNodeToArea`, which **preserves tag topology** (`node.downstream`) across area moves.

Control Panel grouping remains **separate** from Area. CP filters / Set CP do not create or rename Areas.

---

## Rectangle (marquee) selection

Drag on empty canvas to draw a selection box.

### Hit-testing

Hits use generous extents:

1. Prefer `pathCanvas` / `entryCanvas` / `exitCanvas` bounds (Pass1 `nodesBBox`) so **schematic** conveyors are selectable even when the DOM proxy is a small center handle.
2. Else fall back to the node card box (~130×70).

### Modifiers (mouseup)

| Modifier | Result |
|----------|--------|
| *(none)* | **Replace** selection with hits |
| **Ctrl** / **Meta** | **Add** (union) hits into selection |
| **Alt** | **Subtract** hits from selection |
| **Ctrl+Shift** (or Meta+Shift) | **Subtract** (alternate to Alt) |

Tiny drags (&lt; 4px) do not change selection membership beyond the replace-clear that already ran on plain mousedown.

### Node clicks (unchanged roles)

| Gesture | Action |
|---------|--------|
| Click | Select / start move |
| **Shift-click** | **Connect** selected source → clicked destination (EXIT→ENTRY) |
| **Ctrl/Meta-click** | **Toggle** select (add/remove from multi-select) |

**Shift remains connect-only.** Do not overload Shift for additive select — use Ctrl/Meta.

---

## Bulk bar — Area actions

When conveyors are selected, the bulk bar shows:

**`Selected: N conveyors`**

Near **Apply Area / ES**:

| Button | Behavior |
|--------|----------|
| **Create Area from Selection** | `askText` for Area name → create empty Area → `moveNodeToArea` for every selected conveyor → select the new Area / update Build Context. **Does not** infer the name or membership from geometry. If Build Context already has an ES Zone, optionally offers **Apply ES** (Yes/No — never forced). |
| **Add Selection to Area** | Prompt for an existing Area name (defaults to **Build Context** area) → `moveNodeToArea` for selection. |
| **Remove Selection from Area** | Prompt for destination (default **`Unassigned`**) → create that Area if missing → move selection there. Organizational only — **does not** invent controller ownership. |

Existing **Apply Area / ES** and **Set CP** behaviors are unchanged.

---

## Topology & Apply rules (preserved)

- `moveNodeToArea` keeps `node.downstream`; visual `wires[]` stay area-scoped.
- Cross-area product flow remains tag-based until both ends share an Area again.
- Apply→Autogen PLC ownership / `main_area` mapping is **not** redefined here — only the engineer’s Area metadata feeding the existing path.
- Creating or using **Unassigned** does not assign Machine_Name, IO banks, or ControllerScope.

---

## Suggested engineer workflow

1. Auto Build / import conveyors onto the canvas.
2. Marquee (and Ctrl-add / Alt-subtract) the runs that belong together.
3. **Create Area from Selection** → type the real Area name used in Autogen.
4. Optionally accept Apply ES when Build Context already has the zone.
5. Use **Add / Remove Selection from Area** (or Apply Area / ES) for corrections.
6. Keep CP tags for panel organization; they stay independent of Area.
7. Apply to Autogen as today.
