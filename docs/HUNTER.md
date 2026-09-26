# HUNTER — read-only PDF engineering-print evidence extractor

> **Hunter is an evidence extractor, NOT an engineering authority.**
> It reads PDF prints, extracts device/electrical evidence, preserves
> provenance, identifies ambiguity and produces structured evidence.
> If a print does not prove a fact, `REVIEW_REQUIRED` beats a
> deterministic-looking guess.

Code: `tools/hunter/` · Tests: `tools/hunter/tests/` · Version: `0.1.0`

## 1. Purpose and boundaries

Hunter answers questions like *"why does Hunter think ESLS161 exists?"* with
the document, sheet, page, location (bbox) and the exact printed text.

Hunter **does not**:

- modify Site Forge engineering state (dashboard, PLC / Safety / Transport
  compilers, shared PRISM) — it only writes its own output directory;
- create Areas or Safety zones, or infer Safety-zone / Area membership;
- guess I/O assignments, PLC endpoints or upstream/downstream flow;
- parse RUN `tar.gz` archives (future bot **Surveyor**) or reconcile print vs
  RUN (future bot **Reconciler**);
- generate PLC code / L5X, use finished PLCs as a source, do UI automation or
  cross-site learning;
- call any LLM / network API (no OpenAI / xAI / Grok) or run OCR by default.

## 2. Architecture

| Module | Pipeline step(s) |
|---|---|
| `pdf_reader.py` | 1 enumerate PDFs (file or recursive dir, sorted) · 2 sha256 · 3 pages · 4 native words · 5 coordinates (pdfplumber, PDF points, top-left origin, rounded 2 dp). Pages with < 3 usable chars → `TEXT_LAYER_MISSING`. |
| `text_blocks.py` | groups words into text lines (same baseline, split on large x gaps), keeps char→word map for bbox tracing, nearby-line context |
| `sheet_index.py` | 6 title block: literal `SHEET:`, `TITLE:`, `REV:`, `DWG NO:`, `DATE:` fields, bottom 25 % region first, whole page fallback (→ REVIEW_REQUIRED) |
| `device_grammar.py` | 7/9 candidate grammar (anchored per-token rules), ambiguous prefixes, unknown device-like shapes, printed I/O / terminal / network / continuation regexes, connector words, family keywords |
| `device_candidates.py` | 7–10, 12: per-line items → DEVICE_LABEL / AMBIGUOUS / UNKNOWN / IO / IO_MODULE / TERMINAL / NETWORK / CONTINUATION / SHEET_METADATA records |
| `relationship_candidates.py` | 11: explicit printed relationships only; weak ones downgraded |
| `evidence_records.py` | 13: `EvidenceRecord` contract, state + provenance enforcement, deterministic IDs, stable sort |
| `review_queue.py` | 14: review queue + duplicate / raw-label observations (never merges) |
| `export.py` | 15: summary + deterministic writers |
| `pipeline.py` / `cli.py` | orchestration / CLI |
| `schemas/*.schema.json` | JSON Schema (2020-12) for evidence records and manifest |

Dependency: **pdfplumber** (MIT, on pdfminer.six MIT), declared in
`tools/hunter/requirements.txt`. PyMuPDF was rejected (AGPL). Dev/test only:
`tools/hunter/requirements-dev.txt` (pytest, reportlab for fixture
regeneration, jsonschema for schema tests — skipped if absent).

## 3. Evidence contract

Each line of `hunter_evidence.jsonl` is one `EvidenceRecord`
(schema: `tools/hunter/schemas/evidence_record.schema.json`):

| Field | Meaning |
|---|---|
| `evidence_id` | `HE-` + sha256(doc hash, page, type, labels/refs, rounded x0/top)[:20] — deterministic |
| `project`, `controller_scope_hint` | run metadata only (hint never assigns devices) |
| `source_document`, `source_document_hash` | path relative to input root, sha256 |
| `page_number`, `sheet_number`, `sheet_title`, `drawing_revision` | location (sheet fields null if not printed) |
| `raw_text` | the exact printed text line supporting the record |
| `raw_device_label` | raw label, original punctuation/case (`P-1300`) |
| `normalized_name_candidate` | candidate only (`P1300`) — never used to merge |
| `entity_type_candidate` | family hypothesis (conveyor, motor, vfd, photoeye, esls, …, ambiguous, unknown) |
| `evidence_type` | `DEVICE_LABEL`, `AMBIGUOUS_DEVICE_TOKEN`, `UNKNOWN_DEVICE_TOKEN`, `IO_REFERENCE`, `IO_MODULE_REFERENCE`, `TERMINAL_REFERENCE`, `NETWORK_REFERENCE`, `CONTINUATION_REFERENCE`, `RELATIONSHIP`, `SHEET_METADATA`, `TEXT_LAYER_MISSING`, `DOCUMENT_READ_ERROR` |
| `physical_address_text`, `panel_or_rack_text`, `module_or_terminal_text` | literal printed text only |
| `related_device_text`, `relationship_kind` | relationship target / kind (`EXPLICIT_DRIVES`, `SAME_PRINTED_ROW`, `WEAK_SAME_LINE_NUMERIC_MATCH`, …) |
| `continuation_reference` | printed cross-reference target sheet |
| `bbox`, `page_size` | PDF points, top-left origin |
| `context_text` | nearby printed lines |
| `confidence` | 0..1 heuristic weight (see §6) |
| `state` | `PROVEN` / `DERIVED` / `REVIEW_REQUIRED` / `UNKNOWN` only |
| `grammar_rule`, `notes`, `extractor_version` | why Hunter produced it |

**Provenance law** (enforced in the constructor and the schema): no record
without `source_document`, hash, `page_number` ≥ 1 and non-empty `raw_text`.
The only exceptions are extraction-failure records (`TEXT_LAYER_MISSING`,
`DOCUMENT_READ_ERROR`), which must explain themselves in `notes` and never
carry inferred content. `ENGINEER_ASSIGNED` (or any authority state) is
rejected by construction.

**Raw vs normalized:** every observation stays its own record. Labels that
normalize alike (`P-1300` / `P1300`) are reported as `RAW_LABEL_VARIANTS`
observations and queued as `POSSIBLE_CONFLICTING_LABELS`; the same label on
several sheets is a `MULTI_SHEET_OCCURRENCE` observation. Nothing is merged.

**Unknown conservation:** device-like tokens the grammar cannot classify are
kept as `UNKNOWN_DEVICE_TOKEN` (state `UNKNOWN`) with raw token, page, sheet,
bbox and context, and queued. *Unsupported ≠ invisible.*

## 4. CLI

```bash
pip install -r tools/hunter/requirements.txt          # runtime
pip install -r tools/hunter/requirements-dev.txt      # tests
python -m tools.hunter.cli --input <pdf-or-dir> --out <dir> [--project X] [--controller Y]
# e.g.
python -m tools.hunter.cli --input tools/hunter/tests/fixtures/prints \
    --out /tmp/hunter_out --project SYNTH-DEMO --controller PLC01
python -m pytest tools/hunter/tests -q
```

Run from the repo root (`tools` resolves as a namespace package; no
`tools/__init__.py` is required or added). Exit code 2 = input not found.

## 5. Outputs

| File | Content |
|---|---|
| `hunter_manifest.json` | inputs (relative path, sha256, size, pages, read status), timestamp, versions, project, controller hint, flags (`read_only`, `ocr_enabled=false`, `llm_used=false`), evidence fingerprint |
| `hunter_evidence.jsonl` | one EvidenceRecord per line, stable order (document, page, type, top, x0, label, id) |
| `hunter_device_index.csv` | `raw_label, normalized_candidate, type, state, sheet, page, panel, printed_io, confidence, notes, source_document, evidence_id` — one row per label observation (not merged); `printed_io` shows linked printed I/O / terminal text with its relationship state |
| `hunter_summary.json` | counts by family / state / evidence type / page / sheet, unknown & ambiguous counts, pages with extraction warnings, duplicate/raw-label observations, review counts |
| `hunter_review_queue.json` | `DOCUMENT_READ_ERROR`, `TEXT_LAYER_MISSING`, `MISSING_TITLE_BLOCK`, `POSSIBLE_CONFLICTING_LABELS`, `AMBIGUOUS_TYPE`, `UNRECOGNIZED_DEVICE_TOKEN`, `WEAK_RELATIONSHIP`, `CONTINUATION_TARGET_NOT_IN_INPUT_SET` |
| `hunter_sheet_index.json` | page → sheet number, title, revision, drawing no., date, missing fields, source lines + bbox, warnings |

**Determinism:** same PDFs + Hunter version + metadata ⇒ byte-identical
outputs except `generated_at` / `input_path` in the manifest. IDs are hashes,
never random UUIDs; JSON uses sorted keys.

## 6. Confidence / state semantics

| State | Meaning | Typical confidence |
|---|---|---|
| `PROVEN` | explicitly supported **by the print only**: literal printed I/O / terminal / network / cross-reference / title-block text; a label printed on the same line as its own descriptive text (`PULL CORD ESLS161`); a printed explicit link (`M1300 DRIVES P1300`, `TB1-12 -> PE1301`, `ESLS161 IN SAFETY CIRCUIT ESR1`). **Not** RUN-proven, **not** field-verified, **not** PLC-ready, **not** an engineering decision. | 0.85–0.9 |
| `DERIVED` | nominated by naming grammar or layout only (label with no descriptive text; device + I/O on the same printed row without a connector) | 0.6–0.75 |
| `REVIEW_REQUIRED` | ambiguous prefix (`S1300`), several devices on one I/O row, same-line numeric similarity (`M1300 P1300`), missing title block, no text layer | 0.0–0.5 |
| `UNKNOWN` | device-like but unclassified token (`XQ7731`) | 0.2 |

A naming pattern is never physical proof. Same page, numeric similarity,
graphic proximity, same panel or similar names are never relationship proof.
A safety device label never implies Safety-zone membership.

## 7. Limitations (MVP)

- Native text layer only; scanned/image-only pages are flagged
  `TEXT_LAYER_MISSING` (no OCR).
- Line grouping is geometric; labels split across words (`P 1300`), rotated
  or vertical text, and text inside complex tables may be missed or grouped
  imperfectly. Wires/graphics are not interpreted, so drawn (non-textual)
  connections are invisible — only printed words count.
- Title-block detection needs literal `SHEET` / `TITLE` / `REV` / `DWG NO`
  keys; vendor title blocks with unlabeled cells will be REVIEW_REQUIRED.
- Grammar is generic; bare `ESR` / `MCR` words (no digit) are not labels;
  prefixes like `S`, `ST`, `PS`, `LS`, `DS`, `SS` are always ambiguous.
- I/O patterns: Logix-style (`Local:3:I.Data.0`, `RIO1:2:I.3`), SLC-style
  (`I:1/3`), `SLOT n`, `CH n`, common I/O catalog numbers; terminals `TB1-12`,
  `X1:3`, `TERM 12`. Others become unknown tokens or are missed.
- Continuation detection needs `SEE/CONT'D/CONTINUED/TO/FROM ... SHEET/SHT/DWG x`.

## 8. Benchmark procedure (live prints)

Use **one known controller** and a small sheet set that includes conveyors,
several safety devices and printed I/O. Curtis builds a truth set by hand
from the prints only (**the finished PLC is not allowed as a construction
aid**).

Run: `python -m tools.hunter.cli --input <sheet set> --out <dir> --project <p> --controller <c>`

Metrics:

| Metric | Target |
|---|---|
| device-label recall vs truth set | ≥ 95 % |
| false positives (labels not in truth set) | reported, reviewed |
| correct page / correct sheet | reported (expect ~100 %) |
| family classification accuracy | reported |
| explicit printed I/O extraction | reported |
| provenance completeness | 100 % |
| invented I/O addresses | 0 |
| invented Safety-zone memberships | 0 |
| silently discarded unknowns | 0 |
| review-queue quality (actionable / noise) | reported |

Rules: do **not** tune extraction to hit the targets on the benchmark set;
each failure becomes a regression fixture/test first, then a fix.

## 9. Future phases

1. Optional OCR / vision for image-only pages (opt-in flag, results marked
   with their own lower-confidence provenance; never default).
2. **Surveyor** — separate bot that reads RUN `tar.gz` archives.
3. **Reconciler** — separate bot comparing Hunter print evidence to Surveyor
   RUN evidence. Hunter itself stays read-only print evidence.
