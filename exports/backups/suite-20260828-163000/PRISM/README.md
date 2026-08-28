# PRISM — Knowledge Engine (Vector DB)

Standalone Fortna / Rockwell **knowledge + semantic search** project (ChromaDB).

## Location
`C:\dev\worktree\PRISM`

## Launch
- Desktop: **PRISM**
- Or: `C:\dev\worktree\Launch-PRISM.bat`
- CLI: `Launch-RockwellVectorDatabase.bat` / `py Rockwell-Vector-Database.py stats|search|index`

## Layout
| Path | Purpose |
|------|---------|
| `knowledge-corpus/` | Site folders (prints, I/O, L5X, FortnaPlus ingest) — **local data, not for full GitHub** |
| `rockwell-vector-db/` | ChromaDB engine + collections |
| `dashboard/prism.html` | Electron UI |
| `desktop/` | Electron launcher |

## FortnaPlus
FortnaPlus auto-ingests RUN packages into `knowledge-corpus/<tar.gz-stem>/` and re-indexes.
Set `FORTNA_PRISM_ROOT=C:\dev\worktree\PRISM` if needed.

## GitHub
This repo is **code + config**. Large `knowledge-corpus` and Chroma collections are gitignored.
