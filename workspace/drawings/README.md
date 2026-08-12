# Facility drawings (Ignition + print parse)

Drop all site drawings here so FortnaPlus can build **2D Ignition layouts** and improve OCR.

## Where to put files

| Folder | What goes here |
|--------|----------------|
| **`inbox/`** | New zip drops (we unpack from here) |
| **`mechanical/`** | Conveyor plan / elevation PDFs (CP1–CP9 centerlines) |
| **`electrical/`** | Panel / VFD / IO electrical PDFs |
| **`overlay/`** | Building plan / zone plan (e.g. `ORLY Greensboro CP_Layout_…pdf`) |
| **`cad/`** | **DWG / DXF / DWF** (best for geometry — especially `SYS_DL_ForHMI.DWG`) |
| **`oreilly-greensboro/`** | Linked full set (already junctioned to Desktop ORiellys Prints) |

## Preferred types (best → ok)

1. **DWG / DXF** — continuous conveyor polylines (gold)
2. **DWF** — design web format from AutoCAD
3. **Vector PDF** — mechanical plans like your CP5 red-box sheets
4. RUN tar.gz — equipment X/Y + EIP module/IP tables (always keep loaded)

## Current Greensboro assets (linked)

- `oreilly-greensboro/1. Original/2. PDFs/CP1.pdf` … `CP9.pdf`
- `oreilly-greensboro/1. Original/3. DWGs/SYS_DL_ForHMI.DWG` ← **HMI layout CAD**
- `overlay/ORLY Greensboro CP_Layout_20180425.pdf`

## Your zip

Put the full facility zip in:

```text
workspace/drawings/inbox/facility-drawings.zip
```

Then tell the app/agent to import it (or unpack into `mechanical/` + `electrical/` + `overlay/`).
