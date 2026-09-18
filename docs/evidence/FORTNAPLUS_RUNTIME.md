# FortnaPlus Runtime Knowledge (Accepted Archaeology)

Summarizes **proven** FortnaPlus behavior from CP1–CP4.  
Claims here must remain backed by accepted tests/docs — do not invent.

**Human-readable FPC module docs** (what each RUN table *means* for configuration):

- Desktop: `C:\Users\curtiskricke\Desktop\Fortna Plus` (and nested `Fortna Training Docs\`)
- Repo mirror: `docs/training/` + index `docs/FPC_TRAINING_DOCUMENT_INDEX.md`
- Catalog: [`EXTERNAL_REFERENCE_MATERIALS.md`](EXTERNAL_REFERENCE_MATERIALS.md)

**FortnaPlus C / `.mnu` sources** (runtime archaeology):

- Desktop: `C:\Users\curtiskricke\Desktop\Fortna Plus\FortnaPlus files\`
  (`fortna.mnu`, `project.mnu`, `table_api.c`, `menu_api.c`, `fortna.c`, …)
- Also appears inside RUN extracts as `RUN/FORTNA/fortna.mnu`

---

## File resolution precedence

When FortnaPlus opens a logical table `Table` for a machine:

1. `Table.rom.<MACHINE>`
2. `Table.rom`
3. `Table.asc.<MACHINE>`
4. `Table.asc`

**This is FILE RESOLUTION only.** It does not mean ROM outranks every ASC semantic fact globally.

Reproduce: CP1/CP2 loader tests · `docs/RUN_TABLE_PRECEDENCE.md`

---

## Core runtime concepts

| Concept | Meaning | Proof / docs |
|---------|---------|----------------|
| `fortna.mnu` / `project.mnu` | Menu/table/column schema for FPC tables | `docs/FORTNAPLUS_MNU_SCHEMA.md` |
| `find_data_source` | Resolves which physical table file supplies a field | CP1 archaeology · `docs/FORTNAPLUS_MNU_RUNTIME.md` |
| Typed RUN loader | Loads ASC/ROM into typed records | CP2 · `docs/FORTNAPLUS_RUN_LOADER.md` |
| STATIC relationships | Configuration-time links declared by schema | CP3 · relationship model docs |
| DYNAMIC relationships | Runtime/live tables (tracks, status, queues) | CP3/CP4 · relationship model |
| Reference graph | Cross-table identity resolution | `docs/FORTNAPLUS_REFERENCE_RESOLVER.md` |
| SELECTION_UNIQUE / MenuMenu | Accepted menu semantics where proven | CP1 schema docs — do not extend without evidence |

---

## Machine-specific overlays

Example: `MergeInputs.asc.ORNCCP2` correctly takes precedence over `MergeInputs.asc` for file open.

Semantic authority for “merge lane membership” remains **MergeInputs** (schema), not Configio.

---

## Reproduction

```bat
python tools/scripts/test_fortna_mnu_schema.py
python tools/scripts/test_fortna_mnu_runtime.py
python tools/scripts/test_fortna_run_loader.py
python tools/scripts/test_cp4_bundle.py
```

If a claim has no command: mark **REPRODUCTION GAP** in the baseline that cites it.
