# PLC Build Provenance

**Hard requirement:** The engineer-facing L5X generated on the PC must be uniquely identifiable. Studio screenshots of the wrong file have already caused false I/O defect reports.

## Authoritative output location

| Role | Path |
|------|------|
| **CURRENT engineer L5X** | `exports/current/{Controller}_{YYYY_MM_DD_HHMM}.L5X` |
| **Stable latest pointer** | `exports/current/{Controller}_LATEST.L5X` |
| **Build manifest** | `exports/current/build_manifest.json` |
| **Per-build manifest** | `exports/current/{stem}.manifest.json` |
| **Result pointer** | `exports/current/LATEST.json` |
| Diagnostics / IPC recovery | `workspace/.internal/builds/{build_id}/` |
| Historical copies (not engineer-facing) | `exports/autogen/history/` |

Do **not** open random L5X files under `exports/autogen/` (except `history/`), `exports/studio-validation/`, `exports/plc2-fidelity/`, `exports/plc2-semantic-graph/`, or candidate folders as production outputs. Those are diagnostic/historical.

`exports/autogen/README_CURRENT_OUTPUT.txt` points engineers at `exports/current/`.

## Studio-safe naming

Engineer basenames must:

- not begin with digits
- not contain hyphens (`-`)
- not contain double underscores (`__`)

Example (good):

```text
ORNCCP2_2026_09_13_1113.L5X
```

Example (bad — rejected / confusing):

```text
20251016-0933-OReillyGreensboro-ORNCCP2-RUN__2026-09-13_0801.L5X
ORNCCP2__2026_09_13_1113.L5X
```

Controller `TargetName` inside the L5X remains the short panel id (e.g. `ORNCCP2`).

## Build PLC UI contract

After Generate / Build PLC, the Autogen hub shows:

```text
GENERATED PLC
Controller: ORNCCP2
Source RUN: <exact tar.gz filename>
Generated: <local date/time>
Output: <exact L5X filename>

CURRENT PLC BUILD
File: <absolute Windows path>
Generated: …
SHA256: …
Git: …
```

Actions:

- **Open Output Folder** → `exports/current`
- **Open File Location** → reveal folder containing the L5X (does not launch Studio)
- **Copy Full Path** → clipboard

## Manifest schema

`build_manifest.json` fields:

| Field | Meaning |
|-------|---------|
| `controller` | Studio controller / panel id |
| `source_run_filename` | Exact intake `.tar.gz` name |
| `source_run_hash` | RUN fingerprint from active-meta |
| `generation_timestamp` | Local wall clock |
| `git_commit` | Short SHA when available |
| `generator_version` | Engine label |
| `output_filename` | Basename only |
| `output_path` | Absolute path |
| `output_hash` / `output_sha256` | SHA-256 of L5X bytes |

## Embedded L5X provenance

Where safe, Site Forge also embeds:

- `RSLogix5000Content/@Owner` → `SiteForge {git}`
- `<Controller><Description>…</Description>` → short `Controller=… | SourceRUN=… | Generated=… | Output=… | Git=…`

Full detail always lives in `build_manifest.json`.

## Artifact ambiguity (resolved)

Previously, Build PLC wrote dated names under `exports/autogen/` **and** nested dated folders, while smoke tests wrote alternate paths (`plc2-semantic-graph`, `studio-validation`, …). Engineers could open an older L5X in Studio and report I/O defects that were already fixed in a newer file.

**Rule:** one obvious current file under `exports/current/`. Everything else is historical/diagnostic.

## Transport Build vs PLC output

Transport Build canvas state (including **Control Panel** grouping, presentation offsets, zoom/pan) is **organizational / schematic only**.

- It does **not** change controller ownership, I/O, Area, or generated L5X contents.
- Apply to Autogen still emits canonical topology only (see `buildCanonicalApplyGraph`).
- After Build PLC, **`exports/current/` is authoritative** — open `{Controller}_LATEST.L5X` or the dated file named in `build_manifest.json`, not Transport localStorage and not diagnostic trees under `exports/autogen/` / `exports/studio-validation/`.

See also: `docs/CONTROL_PANEL_TRANSPORT_MODEL.md`.
