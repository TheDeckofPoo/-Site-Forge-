# PRISM — Rockwell Vector Database

**PRISM** (Print-Reference Intelligent Search & Matching) is the knowledge engine companion to Rockwell Intake (EDGAR).

Local semantic search over **knowledge-corpus/** — no cloud.

## Quick start

```bat
desktop\Launch-PRISM.bat
Launch-RockwellVectorDatabase.bat stats
Launch-RockwellVectorDatabase.bat search "photoeye jam reset"
```

## What gets indexed

Only `knowledge-corpus/` — create sites manually (+ Site), drop files, Rebuild Index.

| Path | Content |
|------|---------|
| `knowledge-corpus/<site>/programs/` | L5X, XML |
| `knowledge-corpus/<site>/io/` | CSV, summary.json |
| `knowledge-corpus/<site>/prints/` | PDF, DXF, DWG |
| `knowledge-corpus/<site>/layouts/` | PNG, spatial_layout.json |
| `knowledge-corpus/docs/` | Shared `.md` runbooks |

Intake outputs (`intake-outputs/`) and Git merges (`merged-outputs/`) are **not** auto-indexed — copy into the corpus when ready.

## Storage

- ChromaDB at `rockwell-vector-db/collections/` (gitignored)
- Collection: `rockwell_knowledge`

## Files

| File | Role |
|------|------|
| `Rockwell-Vector-Database.py` | CLI at worktree root |
| `rockwell-vector-db/rockwell_vectordb.py` | Indexer + search |
| `desktop/Launch-PRISM.bat` | Visual dashboard |