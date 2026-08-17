# Sorter build UI — demo revert notes

**Added:** 2026-08-13 (PLC Autogen tab — collapsible section below existing layout)

## What was added

1. **`dashboard/index.html`**
   - PLC Autogen tab is scrollable.
   - Collapsible **Sorter build** panel *below* the existing two-column UI (collapsed by default).
   - Fields: induct conveyor + PE + **encoder Yes/No**, tracking conveyor count → dynamic rows
     (conveyor · PE · **encoder Yes/No** · type/tag when Yes), divert count, tracking PE count.
   - Encoder **No** = document intent for library null tag `NO_Enc` (Enc_UDT stub — not “missing data”).
   - Encoder **Yes** = type (`Enc_RIOCard` / `Enc_CounterCard` / `Enc_Virtual_DistBased`) + optional tag.

2. **`dashboard/fortna-plus.js`**
   - `autogenState.sorter` + `renderSorterBuild` / `wireSorterBuildUi`
   - Saves into `workbook.sorter_build` + `localStorage.fortna_sorter_build`
   - **Does not change L5X generation yet** — config UI only (Slow_Flt still hardcodes `NO_Enc` until wired).

## Revert for demo (easy)

### Option A — hide only (keep code)

In `dashboard/index.html`, remove or comment out the block:

```html
<details id="autogen-sorter-panel" ...>
  ...
</details>
```

And in `dashboard/fortna-plus.js`, comment out:

```js
wireSorterBuildUi();
```

### Option B — full git revert of these files

```bash
cd C:\dev\worktree\Site Forge
git checkout HEAD -- dashboard/index.html dashboard/fortna-plus.js
```

(Only if this work is uncommitted, or reset to the commit *before* the sorter UI commit.)

### Clear saved sorter data

- Browser DevTools → Application → Local Storage → delete `fortna_sorter_build`
- Or clear via **Clear sorter fields** button in the UI

## Git baseline before this feature

Last known good commit before sorter UI (check with `git log`):

```
9e73188 End of Day Commit
```

To hard reset to that point (destructive — only if needed):

```bash
git checkout 9e73188 -- dashboard/index.html dashboard/fortna-plus.js
```

---

*Safe for demo: existing Program pack + Site config layout is unchanged when Sorter build is collapsed.*
