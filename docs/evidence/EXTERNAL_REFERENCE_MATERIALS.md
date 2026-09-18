# External Reference Materials (Curtis Desktop)

These folders are **local reference corpora** used to explain FortnaPlus RUN tables, FPC configuration modules, and finished-PLC validation oracles.

They are **not** copied wholesale into Git (customer/site L5X, ISO, and large zips stay local unless already intentionally tracked).

> Documentation indexes these materials. **Raw RUN + accepted decoder proofs still outrank docs.**

---

## Folder A — Fortna Plus training + FortnaPlus sources

**Path (Curtis machine):**

`C:\Users\curtiskricke\Desktop\Fortna Plus`

### Contents (high level)

| Area | What it is | How Site Forge uses it |
|------|------------|-------------------------|
| **FPC / Fortna Training Docs** (root + `Fortna Training Docs\`) | Word modules explaining FPC tables & configuration | Semantic meaning of RUN tables (Merge, Mtrchain, Jam, Sorter, I/O, …) |
| **`FortnaPlus files\`** | FortnaPlus C sources + `fortna.mnu` / `project.mnu` | Runtime archaeology for `find_data_source`, menu schema, table API |
| **`Rel 10 Modules (Module List).docx`** | Module inventory | Map feature → tables |
| **`PASIM1-RUN.tar.gz`** | Example RUN (P&A) | Local experiment only — not a Site Forge generation seed |
| **`rtkit-650-fortna-*.iso`** | Fortna toolkit ISO | Local tooling — **do not commit** |

### In-repo mirrors (preferred for agents)

| Desktop | Repo |
|---------|------|
| FPC training Word docs | `docs/training/` (FPC Documents 1 / FPC-Docs 2 / FPC Docs 3 / P&A Documents) |
| Training index | **`docs/FPC_TRAINING_DOCUMENT_INDEX.md`** |
| FortnaPlus `.mnu` / runtime docs | `docs/FORTNAPLUS_MNU_SCHEMA.md`, `docs/FORTNAPLUS_MNU_RUNTIME.md`, CP1–CP4 |

If Desktop and `docs/training/` diverge, treat **Desktop as Curtis’s working copy** and sync into `docs/training/` when intentionally updating the corpus.

### Critical training docs → RUN tables (from FPC index)

| Doc (under `docs/training/` or Desktop) | RUN / FPC tables it explains |
|----------------------------------------|------------------------------|
| `FPC-Merge-Modules.docx` | MergeBoss, MergeInputs, MergeRoute, SawMerge, … |
| `FPC-HighSpeedSawtoothMerge.docx` | HSSaw*, SawLane, SawMerge, Fullline, … |
| `FPC-Motor-Startup-Chains.docx` | **Mtrchain**, Conveyor, Jamzones, … |
| `FPC-Fulls-Jams-Fulljams.docx` | Fullline, **Jamcheck**, Fulljam, **Jamzones** |
| `FPC-StartStopZones.docx` | StartStopZones, Jamzones, CombinedJamZones, … |
| `FPC-Sorter-Control-Module.docx` | **Sorters**, SrtAppControl, SrtScanBoss, SrtZoneLane, SrtTrack*, … |
| `FPC-Shifter-And-Sorter-Configuration.docx` | Sorters, SortBuff, SortData, Encoders, … |
| `FPC-IOCard-Interfaces.docx` | IOCard, **Configio**, FORTNADT, RIO adapters |
| `FPC-FastIO-Configuration.docx` | FastIO, Configio, Conveyor |
| `FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx` | FORTNADT, Configio, View I/O |
| `FPC-Ctrl-F4-Table-Distribution.docx` | How tables distribute across machines |
| `FPC-Scanner-Control-Configuration.docx` | Scanners, ScnScan*, SrtScanBoss |
| `FPC-SorterConfigurationChecklist.docx` | Commissioning checklist for sorter tables |

Full ranked list: `docs/FPC_TRAINING_DOCUMENT_INDEX.md`.

### FortnaPlus source files (Desktop `FortnaPlus files\`)

| File | Role |
|------|------|
| `fortna.mnu`, `fortna (1..3).mnu` | Menu/table/column schema |
| `project.mnu` | Project menu overlay |
| `table_api.c` / `table_api.h` | Table open / row access |
| `menu_api.c` / `menu_api.h` | Menu API |
| `fmenu.c`, `amenu.c`, `rmenu.c`, `phmenu.c` | Menu implementations |
| `fortna.c`, `fplus.c`, `parse.c` | Core runtime |
| `machine.c` / `machine.h` | Machine context |
| `project.c` / `cproject.c` | Project load |
| `Makefile` | Build |

These support **interpretation semantics** (CP1 archaeology). They are not site RUN evidence.

---

## Folder B — Folder to GPT (validation oracles + latest Site Forge L5X)

**Path (Curtis machine):**

`C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT`

| File | Class | Use |
|------|-------|-----|
| `ORLY_GreensboroPLC2_NC_Finished.L5X` | Finished PLC **validation oracle** | Compare architecture after blind RUN build — **never discovery** |
| `ORLY_Greensboro_NC_PLC4 finished.L5X` | Validation oracle | Same |
| `ORLY_Greensboro_NC_PLC5_RTfinished.L5X` | Validation oracle (Sorter_Track architecture) | Same |
| `ES_Program.L5X` | ES structural reference | Pattern only; also see `docs/es-reference/` |
| `ORNCCP2_2026_09_17_2040.L5X` | Site Forge **generated** output | Field acceptance artifact for that build |

Repo mirrors / related:

- `workspace/validation/` (when present)  
- `docs/es-reference/`  
- `exports/current/` for generated L5X  

**Do not commit** large finished L5X dumps into Git unless repository policy already tracks them.

---

## How to use these materials in a review session

1. Open `docs/evidence/README.md` (product evidence index).  
2. For RUN **table meaning** → FPC training doc from the table above / `FPC_TRAINING_DOCUMENT_INDEX.md`.  
3. For FortnaPlus **file open / find_data_source** → `FORTNAPLUS_RUNTIME.md` + Desktop `FortnaPlus files\` / CP1 docs.  
4. For **“did we match finished PLC architecture?”** → Folder to GPT finished L5X **after** blind RUN derivation.  
5. Never promote training-doc examples or finished-PLC tags into discovery rules without RUN proof.

---

## Reproduction / location check (local)

```bat
dir "C:\Users\curtiskricke\Desktop\Fortna Plus"
dir "C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT"
dir docs\training
type docs\FPC_TRAINING_DOCUMENT_INDEX.md
```
