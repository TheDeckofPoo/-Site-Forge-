# Repository Artifact Policy

**Status:** Binding for commits on Site Forge / FortnaPlus  
**Related:** `.gitignore`, `.gitattributes`, `docs/AI_BUILD_PROTOCOL.md`, `docs/SOURCE_OF_TRUTH_POLICY.md`

---

## Committed vs local-only

| Path / artifact | Policy |
|-----------------|--------|
| Application source (`dashboard/`, `desktop/*.js`, `tools/scripts/`, `tools/knowledge/`) | **Committed** |
| Binding docs under `docs/*.md` (non-training) | **Committed** |
| `docs/training/` corpus (FPC / P&A docs + zips) | **Committed** as reference corpus; Linguist-vendored |
| `tools/libraries/` generic L5X / pattern libs | **Committed**; Linguist-vendored |
| Checkpoint / discovery JSON under `exports/<gate>/` (reports, inventories, summaries) | **Committed** when they are review evidence for a named gate |
| Generated `.L5X` under `exports/` | **Local-only by default** (gitignored). Force-add only when needed for review (below) |
| `exports/autogen/`, `exports/plc/`, `exports/ignition-build/` bulk outputs | **Local-only** (gitignored; keep `.gitkeep`) |
| `exports/**/*.zip`, `*.svg`, `*.csv`, `LATEST.*` | **Local-only** (gitignored) |
| Workspace RUN extracts (`workspace/**/RUN/**`, `workspace/cp*-run/`, `workspace/active*`) | **Local-only** site data |
| `workspace/prints/`, `workspace/inbox/`, `workspace/reference/` | **Local-only** |
| Office lock files (`~$*`) under training | **Do not commit** |
| `node_modules/`, `__pycache__/`, `.venv/` | **Local-only** |

Known-good regression fixtures are deliberate exceptions — commit on purpose, not casually.

---

## `.gitattributes` (Linguist)

Configured so GitHub language stats reflect product source, not plant data or corpora:

| Rule | Intent |
|------|--------|
| `*.asc` / `*.asc.*` → `linguist-detectable=false` | FortnaPlus ASC tables are **not** AGS Script |
| `**/FORTNA/**` → vendored + undetectable | Vendor FPC tree, not app logic |
| `docs/training/**` → vendored + undetectable | Training corpus, not product source |
| `exports/**/*.{json,md,L5X,l5x}` → `linguist-generated` | Export / gate artifacts |
| `tools/libraries/**` → vendored | Generic Rockwell libraries |
| `workspace/**/RUN/**` → vendored + undetectable | Local RUN extracts |

---

## Regression evidence

- **Do not delete** regression evidence in this pass (activity-closure audits, CP gate JSON, frozen discovery reports, supersession audits, bridge-floor checks).
- Prefer adding corrected artifacts alongside older ones when a gate is still under review.
- Frozen trees such as `exports/cp5-blind/` are review baselines — leave intact unless a later explicit freeze task says otherwise.

---

## Force-add policy (selected L5X)

`.gitignore` ignores `exports/**/*.L5X`. When architecture review needs a specific generated L5X in-tree:

1. Prefer small, named gate paths (e.g. `exports/<gate>/generated/<Controller>_candidate.L5X`).
2. Use `git add -f -- <path>` for **only** those selected files.
3. Mark them Linguist-generated (already covered by `.gitattributes`).
4. Do **not** force-add bulk `exports/plc/` or `exports/autogen/` dumps.
5. Document in the gate report why the L5X was force-added.

---

## RUN fixtures

- Production discovery inputs are local RUN extracts under `workspace/`.
- Small fixture tarballs used by tests/docs (e.g. training PASIM samples) may be committed when intentionally part of the training/docs corpus.
- Never commit full site RUN trees or finished gold PLCs as generation inputs.
