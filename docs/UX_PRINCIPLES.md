# Site Forge — UX Principles

**Status:** Binding product principle  
**Effective:** Integration checkpoint

---

## Complexity belongs inside Site Forge, not in front of the engineer

The normal workflow must be understandable by a controls engineer who has never seen the parser architecture.

### Default design principle

```
SIMPLE BY DEFAULT
ADVANCED WHEN NEEDED
```

### Prefer

- one obvious primary action
- contextual inspector controls
- dropdown / menu for secondary actions
- expandable **Advanced / Evidence** section
- automatic behavior when safe

### Avoid

- toolbars full of actions
- duplicate controls
- parser-specific buttons
- VFD-specific / encoder-specific / sawtooth-specific build buttons
- permanent debug controls

### Before adding any visible control

Ask: **Does the engineer need this during the normal workflow?**

If **NO**, do not put it on the main toolbar.

---

## Main workflow (dominant actions)

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

New compiler capabilities (VFD packs, encoders, sawtooth, tracking) are **compiler responsibilities**.

They do **not** automatically deserve new top-level buttons.

The engineer edits the **Site Model**.  
The compiler decides which supported equipment packs to generate.

---

## Contextual editing

| Selection | Show |
|-----------|------|
| Ordinary conveyor | Conveyor properties, Area, ES, PE roles |
| VFD-driven conveyor | + drive / VFD badges and inspector fields |
| Encoder-equipped | + encoder fields |
| Sawtooth merge | + sawtooth configuration |

Do not show all possible fields for all equipment at once.

---

## Presentation vs engineering

Display layout (lane separation, label placement, Fit) is **presentation-only**.

Never mutate:

- RUN coordinates
- workbook topology
- PLC downstream
- engineering geometry

to make the screen look better.
