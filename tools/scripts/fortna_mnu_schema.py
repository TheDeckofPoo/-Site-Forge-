#!/usr/bin/env python3
"""FortnaPlus .mnu schema decoder — archaeology / tooling only.

Parses authentic fortna.mnu / project.mnu files into a deterministic
machine-readable schema. Does NOT integrate into production RUN decode,
canonical models, or the PLC compiler.

Proven grammar (from supplied files; not assumed beyond evidence):
  - Line 1 is a dual header split by token "***"
  - Left of ***: menu/definition header column names
  - Right of ***: field/column definition column names
  - Definition blocks: menu-header row (FLAGS = 16 chars of 0/1), then
    zero+ field rows, then a blank line
  - Cross-table name tokens appear in the DLIST field when the quoted
    value is non-blank; whether DLIST is a foreign key is NOT asserted —
    we only record that the raw value names another definition when it
    matches an MNUNAME present in the loaded schema(s).

Unknown numeric semantics remain UNKNOWN; raw values are preserved.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]

FLAGS_RE = re.compile(r"^[01]{16}$")
SITEFORGE_INTEREST = (
    "Conveyor",
    "Mtrchain",
    "Convpath",
    "Configio",
    "FORTNADT",
    "EStop",
    "Jamcheck",
    "Jamzones",
    "MergeBoss",
    "MergeInputs",
    "MergeRoute",
    "Machine",
    "MsgMap",
    "Area",
    "Sorter",
    "Sawtooth",
)


# ---------------------------------------------------------------------------
# Tokenization / provenance
# ---------------------------------------------------------------------------


def tokenize(line: str) -> list[str]:
    """Split a .mnu line into tokens, preserving single-quoted strings."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "'":
            j = i + 1
            while j < n and line[j] != "'":
                j += 1
            out.append(line[i : j + 1] if j < n else line[i:])
            i = j + 1 if j < n else n
            continue
        j = i
        while j < n and not line[j].isspace():
            j += 1
        out.append(line[i:j])
        i = j
    return out


def unquote(tok: str | None) -> str:
    if tok is None:
        return ""
    if len(tok) >= 2 and tok[0] == "'" and tok[-1] == "'":
        return tok[1:-1]
    return tok


def load_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    # Supplied files are LF / latin-1. Preserve undecodable bytes via latin-1.
    return raw.decode("latin-1").splitlines()


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Provenance:
    sourceFile: str
    origin: str  # FORTNA | PROJECT | OTHER
    line: int
    kind: str  # header | definition | field


@dataclass
class MnuField:
    name: str
    rawDatatype: str
    rawLength: str
    rawLow: str
    rawHigh: str
    rawList: str
    rawDataSource: str
    rawMetadata: dict[str, str]
    rawTokens: list[str]
    provenance: dict[str, Any]
    # Explicit cross-table name evidence from rawList (DLIST), if any
    listReference: str | None = None


@dataclass
class MnuDefinition:
    name: str
    rawMetadata: dict[str, str]
    rawTokens: list[str]
    fields: list[MnuField] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class MnuSchema:
    sourceFile: str
    origin: str
    headerLine: str
    menuColumns: list[str]
    fieldColumns: list[str]
    definitions: list[MnuDefinition]
    parseNotes: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossReference:
    sourceDefinition: str
    sourceField: str
    targetDefinition: str
    rawReference: str
    rawColumn: str  # which .mnu column held the reference token (evidence: DLIST)
    resolved: bool
    sourceOrigin: str
    sourceFile: str
    sourceLine: int


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_mnu_file(path: Path | str, *, origin: str | None = None) -> MnuSchema:
    path = Path(path)
    if origin is None:
        upper = path.name.upper()
        if upper == "FORTNA.MNU":
            origin = "FORTNA"
        elif upper == "PROJECT.MNU":
            origin = "PROJECT"
        else:
            origin = "OTHER"

    lines = load_lines(path)
    notes: list[str] = []
    if not lines:
        return MnuSchema(
            sourceFile=str(path),
            origin=origin,
            headerLine="",
            menuColumns=[],
            fieldColumns=[],
            definitions=[],
            parseNotes=["empty file"],
            stats={"definitions": 0, "fields": 0, "lines": 0},
        )

    header_toks = tokenize(lines[0])
    if "***" not in header_toks:
        raise ValueError(f"{path}: header missing *** separator; cannot parse safely")
    star = header_toks.index("***")
    menu_cols = header_toks[:star]
    field_cols = header_toks[star + 1 :]
    if not menu_cols or not field_cols:
        raise ValueError(f"{path}: empty menu/field column lists")

    # Column indices used for raw* convenience fields (names from file header)
    def _idx(cols: list[str], name: str) -> int | None:
        try:
            return cols.index(name)
        except ValueError:
            return None

    i_colname = _idx(field_cols, "COLNAME")
    i_dtype = _idx(field_cols, "DTYPE")
    i_dlen = _idx(field_cols, "DLEN")
    i_dlow = _idx(field_cols, "DLOW")
    i_dhigh = _idx(field_cols, "DHIGH")
    i_dlist = _idx(field_cols, "DLIST")
    i_dsrc = _idx(field_cols, "DSRC")

    definitions: list[MnuDefinition] = []
    current: MnuDefinition | None = None
    skipped_rows = 0
    field_token_mismatches = 0

    def _tok_at(toks: list[str], idx: int | None) -> str:
        if idx is None or idx < 0 or idx >= len(toks):
            return ""
        return toks[idx]

    def _finish() -> None:
        nonlocal current
        if current is not None:
            definitions.append(current)
            current = None

    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            _finish()
            continue
        toks = tokenize(line)
        if not toks:
            continue

        # Definition header: token count matches menu columns AND FLAGS pattern
        if len(toks) == len(menu_cols) and FLAGS_RE.fullmatch(toks[-1] or ""):
            _finish()
            meta = {menu_cols[i]: toks[i] for i in range(len(menu_cols))}
            name = unquote(meta.get("MNUNAME") or toks[0])
            current = MnuDefinition(
                name=name,
                rawMetadata=meta,
                rawTokens=list(toks),
                fields=[],
                provenance={
                    "sourceFile": str(path),
                    "origin": origin,
                    "line": line_no,
                    "kind": "definition",
                },
            )
            continue

        # Field row belonging to current definition
        if current is None:
            skipped_rows += 1
            notes.append(f"line {line_no}: field-like row before any definition header (skipped)")
            continue

        if len(toks) != len(field_cols):
            field_token_mismatches += 1
            notes.append(
                f"line {line_no}: field row token count {len(toks)} != {len(field_cols)} "
                f"(kept with rawTokens only)"
            )
            # Still keep the row with best-effort mapping
            meta = {field_cols[i]: toks[i] for i in range(min(len(field_cols), len(toks)))}
        else:
            meta = {field_cols[i]: toks[i] for i in range(len(field_cols))}

        raw_list = unquote(_tok_at(toks, i_dlist) if i_dlist is not None else meta.get("DLIST", ""))
        list_ref = raw_list.strip() if raw_list.strip() else None
        fname = unquote(_tok_at(toks, i_colname) if i_colname is not None else meta.get("COLNAME", toks[0]))
        current.fields.append(
            MnuField(
                name=fname,
                rawDatatype=_tok_at(toks, i_dtype) if i_dtype is not None else meta.get("DTYPE", ""),
                rawLength=_tok_at(toks, i_dlen) if i_dlen is not None else meta.get("DLEN", ""),
                rawLow=_tok_at(toks, i_dlow) if i_dlow is not None else meta.get("DLOW", ""),
                rawHigh=_tok_at(toks, i_dhigh) if i_dhigh is not None else meta.get("DHIGH", ""),
                rawList=raw_list,
                rawDataSource=_tok_at(toks, i_dsrc) if i_dsrc is not None else meta.get("DSRC", ""),
                rawMetadata=meta,
                rawTokens=list(toks),
                provenance={
                    "sourceFile": str(path),
                    "origin": origin,
                    "line": line_no,
                    "kind": "field",
                },
                listReference=list_ref,
            )
        )

    _finish()

    if skipped_rows:
        notes.append(f"skipped_rows_before_definition={skipped_rows}")
    if field_token_mismatches:
        notes.append(f"field_token_mismatches={field_token_mismatches}")

    field_count = sum(len(d.fields) for d in definitions)
    schema = MnuSchema(
        sourceFile=str(path.resolve()) if path.exists() else str(path),
        origin=origin,
        headerLine=lines[0],
        menuColumns=menu_cols,
        fieldColumns=field_cols,
        definitions=definitions,
        parseNotes=notes,
        stats={
            "definitions": len(definitions),
            "fields": field_count,
            "lines": len(lines),
            "menuColumnCount": len(menu_cols),
            "fieldColumnCount": len(field_cols),
        },
    )
    return schema


def schema_to_dict(schema: MnuSchema, *, compact: bool = True) -> dict[str, Any]:
    """Serialize schema.

    compact=True (default for artifacts): keep provenance + convenience raw*
    columns, omit bulky rawTokens / full rawMetadata maps (regenerable via parse).
    compact=False: include full rawTokens + rawMetadata for forensic dumps.
    """
    defs: list[dict[str, Any]] = []
    for d in schema.definitions:
        drec: dict[str, Any] = {
            "name": d.name,
            "line": d.provenance.get("line"),
            "menuRaw": {
                k: d.rawMetadata.get(k, "")
                for k in ("TYPE", "#RECS", "LOC", "CURR", "MXCR", "DREC", "DISPMAX", "FLAGS")
                if k in d.rawMetadata
            },
            "fields": [],
        }
        if not compact:
            drec["provenance"] = dict(d.provenance)
            drec["rawMetadata"] = dict(d.rawMetadata)
            drec["rawTokens"] = list(d.rawTokens)
        for f in d.fields:
            frec: dict[str, Any] = {
                "name": f.name,
                "rawDatatype": f.rawDatatype,
                "rawLength": f.rawLength,
                "rawLow": f.rawLow,
                "rawHigh": f.rawHigh,
                "rawList": f.rawList,
                "rawDataSource": f.rawDataSource,
                "listReference": f.listReference,
                "line": f.provenance.get("line"),
            }
            if not compact:
                frec["rawMetadata"] = dict(f.rawMetadata)
                frec["rawTokens"] = list(f.rawTokens)
                frec["provenance"] = dict(f.provenance)
            drec["fields"].append(frec)
        defs.append(drec)
    return {
        "kind": "MnuSchema",
        "version": 1,
        "compact": compact,
        "sourceFile": schema.sourceFile,
        "origin": schema.origin,
        "headerLine": schema.headerLine,
        "menuColumns": list(schema.menuColumns),
        "fieldColumns": list(schema.fieldColumns),
        "parseNotes": list(schema.parseNotes),
        "stats": dict(schema.stats),
        "definitions": defs,
    }


# ---------------------------------------------------------------------------
# Combine FORTNA + PROJECT (no silent precedence)
# ---------------------------------------------------------------------------


def combine_schemas(
    schemas: Iterable[MnuSchema],
) -> dict[str, Any]:
    """Combine schemas retaining provenance. Collisions are reported, not resolved."""
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_defs: list[dict[str, Any]] = []
    origins_present: list[str] = []

    for schema in schemas:
        origins_present.append(schema.origin)
        for d in schema.definitions:
            rec = {
                "name": d.name,
                "origin": schema.origin,
                "sourceFile": schema.sourceFile,
                "line": d.provenance.get("line"),
                "rawMetadata": dict(d.rawMetadata),
                "fieldNames": [f.name for f in d.fields],
                "fieldCount": len(d.fields),
                "fields": [
                    {
                        "name": f.name,
                        "rawDatatype": f.rawDatatype,
                        "rawLength": f.rawLength,
                        "rawLow": f.rawLow,
                        "rawHigh": f.rawHigh,
                        "rawList": f.rawList,
                        "rawDataSource": f.rawDataSource,
                        "listReference": f.listReference,
                        "provenance": dict(f.provenance),
                    }
                    for f in d.fields
                ],
            }
            by_name[d.name].append(rec)
            all_defs.append(rec)

    collisions: list[dict[str, Any]] = []
    for name, copies in sorted(by_name.items()):
        if len(copies) < 2:
            continue
        origins = sorted({c["origin"] for c in copies})
        # Compare field name sets + selected raw columns
        fingerprints = []
        for c in copies:
            fp = tuple(
                (
                    f["name"],
                    f["rawDatatype"],
                    f["rawLength"],
                    f["rawLow"],
                    f["rawHigh"],
                    f["rawList"],
                    f["rawDataSource"],
                )
                for f in c["fields"]
            )
            fingerprints.append(fp)
        identical = len(set(fingerprints)) == 1
        collisions.append(
            {
                "definition": name,
                "copies": len(copies),
                "origins": origins,
                "identicalFieldFingerprint": identical,
                "sources": [
                    {
                        "origin": c["origin"],
                        "sourceFile": c["sourceFile"],
                        "line": c["line"],
                        "fieldCount": c["fieldCount"],
                        "fieldNames": c["fieldNames"],
                    }
                    for c in copies
                ],
                "note": (
                    "Collision retained — no silent precedence applied. "
                    "FortnaPlus machine/generic ASC rule is separate from .mnu ownership."
                ),
            }
        )

    # Compact ownership index (no full field bodies — those live on per-origin schemas)
    ownership = {
        name: [
            {
                "origin": c["origin"],
                "sourceFile": c["sourceFile"],
                "line": c["line"],
                "fieldCount": c["fieldCount"],
                "fieldNames": c["fieldNames"],
            }
            for c in copies
        ]
        for name, copies in sorted(by_name.items())
    }
    return {
        "kind": "CombinedMnuSchema",
        "version": 1,
        "origins": origins_present,
        "definitionCount": len(all_defs),
        "uniqueDefinitionNames": len(by_name),
        "collisions": collisions,
        "collisionCount": len(collisions),
        "ownershipIndex": ownership,
        "precedencePolicy": "NONE_APPLIED_REPORT_ONLY",
    }


# ---------------------------------------------------------------------------
# Cross-table references / relationship graph
# ---------------------------------------------------------------------------


def extract_references(*schemas: MnuSchema) -> dict[str, Any]:
    known: set[str] = set()
    for schema in schemas:
        for d in schema.definitions:
            known.add(d.name)

    refs: list[CrossReference] = []
    for schema in schemas:
        for d in schema.definitions:
            for f in d.fields:
                if not f.listReference:
                    continue
                target = f.listReference
                refs.append(
                    CrossReference(
                        sourceDefinition=d.name,
                        sourceField=f.name,
                        targetDefinition=target,
                        rawReference=f.rawList,
                        rawColumn="DLIST",
                        resolved=target in known,
                        sourceOrigin=schema.origin,
                        sourceFile=schema.sourceFile,
                        sourceLine=int(f.provenance.get("line") or 0),
                    )
                )

    forward: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in refs:
        item = {
            "sourceField": r.sourceField,
            "targetDefinition": r.targetDefinition,
            "rawReference": r.rawReference,
            "rawColumn": r.rawColumn,
            "resolved": r.resolved,
            "origin": r.sourceOrigin,
            "sourceFile": r.sourceFile,
            "sourceLine": r.sourceLine,
        }
        forward[r.sourceDefinition].append(item)
        reverse[r.targetDefinition].append(
            {
                "sourceDefinition": r.sourceDefinition,
                "sourceField": r.sourceField,
                "rawReference": r.rawReference,
                "rawColumn": r.rawColumn,
                "resolved": r.resolved,
                "origin": r.sourceOrigin,
                "sourceFile": r.sourceFile,
                "sourceLine": r.sourceLine,
            }
        )

    unresolved = [asdict(r) for r in refs if not r.resolved]
    return {
        "kind": "MnuRelationships",
        "version": 1,
        "referenceCount": len(refs),
        "resolvedCount": sum(1 for r in refs if r.resolved),
        "unresolvedCount": len(unresolved),
        "knownDefinitionCount": len(known),
        "forward": {k: v for k, v in sorted(forward.items())},
        "reverse": {k: v for k, v in sorted(reverse.items())},
        "unresolved": unresolved,
        "semanticsNote": (
            "References are taken from non-blank DLIST quoted values that appear in "
            "field rows. This decoder does NOT assert that DLIST is a foreign key — "
            "only that the raw token names another MNUNAME when resolved=true."
        ),
    }


# ---------------------------------------------------------------------------
# Semantic version diff
# ---------------------------------------------------------------------------


def _def_fingerprint(d: MnuDefinition) -> dict[str, Any]:
    return {
        "name": d.name,
        "menuMetadata": {k: d.rawMetadata.get(k, "") for k in sorted(d.rawMetadata) if k != "MNUNAME"},
        "fields": [
            {
                "name": f.name,
                "rawDatatype": f.rawDatatype,
                "rawLength": f.rawLength,
                "rawLow": f.rawLow,
                "rawHigh": f.rawHigh,
                "rawList": f.rawList,
                "rawDataSource": f.rawDataSource,
            }
            for f in d.fields
        ],
    }


def _classify_def_change(a: MnuDefinition, b: MnuDefinition) -> list[str]:
    """Return change tags for one definition pair. Empty => IDENTICAL."""
    tags: list[str] = []
    if a.name != b.name:
        tags.append("UNKNOWN_CHANGE")
        return tags

    # Menu metadata (non-name)
    meta_a = {k: v for k, v in a.rawMetadata.items() if k != "MNUNAME"}
    meta_b = {k: v for k, v in b.rawMetadata.items() if k != "MNUNAME"}
    meta_changed = meta_a != meta_b

    # Capacity-ish keys observed in header: #RECS, MXCR, DISPMAX, DREC, CURR
    capacity_keys = {"#RECS", "MXCR", "DISPMAX", "DREC", "CURR"}
    capacity_changed = any(meta_a.get(k) != meta_b.get(k) for k in capacity_keys)
    other_meta_changed = any(
        meta_a.get(k) != meta_b.get(k) for k in set(meta_a) | set(meta_b) if k not in capacity_keys
    )

    fields_a = {f.name: f for f in a.fields}
    fields_b = {f.name: f for f in b.fields}
    added = sorted(set(fields_b) - set(fields_a))
    removed = sorted(set(fields_a) - set(fields_b))
    common = sorted(set(fields_a) & set(fields_b))

    for name in added:
        tags.append("FIELD_ADDED")
    for name in removed:
        tags.append("FIELD_REMOVED")

    for name in common:
        fa, fb = fields_a[name], fields_b[name]
        core_a = (fa.rawDatatype, fa.rawLength, fa.rawLow, fa.rawHigh, fa.rawDataSource)
        core_b = (fb.rawDatatype, fb.rawLength, fb.rawLow, fb.rawHigh, fb.rawDataSource)
        if core_a != core_b:
            tags.append("FIELD_DEFINITION_CHANGED")
        if (fa.rawList or "") != (fb.rawList or ""):
            # Reference add/remove/change via DLIST evidence
            a_ref = (fa.listReference or "").strip()
            b_ref = (fb.listReference or "").strip()
            if a_ref and not b_ref:
                tags.append("REFERENCE_REMOVED")
            elif b_ref and not a_ref:
                tags.append("REFERENCE_ADDED")
            elif a_ref != b_ref:
                tags.append("REFERENCE_REMOVED")
                tags.append("REFERENCE_ADDED")
            else:
                # rawList text changed but both blank or same ref token — still a field def change
                tags.append("FIELD_DEFINITION_CHANGED")

    if capacity_changed:
        tags.append("CAPACITY/LIMIT_CHANGED")
    if other_meta_changed and not capacity_changed:
        tags.append("METADATA_ONLY_CHANGED")
    elif other_meta_changed and capacity_changed:
        # capacity already tagged; residual non-capacity meta also counts as metadata
        tags.append("METADATA_ONLY_CHANGED")

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    if not out and meta_changed:
        out.append("UNKNOWN_CHANGE")
    return out


def diff_schemas(
    schemas: list[tuple[str, MnuSchema]],
) -> dict[str, Any]:
    """Semantic multi-version diff across labeled schemas (typically fortna.mnu copies)."""
    if not schemas:
        return {"kind": "MnuVersionDiff", "version": 1, "labels": [], "summary": {}}

    labels = [lab for lab, _ in schemas]
    by_label: dict[str, dict[str, MnuDefinition]] = {
        lab: {d.name: d for d in sch.definitions} for lab, sch in schemas
    }
    all_names = sorted(set().union(*[set(m) for m in by_label.values()]))

    identical = 0
    changed = 0
    added_removed = 0
    reference_changes = 0
    details: list[dict[str, Any]] = []

    # Pairwise against first as baseline, plus presence across all
    baseline_lab, baseline = schemas[0]
    baseline_map = by_label[baseline_lab]

    common_to_all = [n for n in all_names if all(n in by_label[lab] for lab in labels)]

    for name in all_names:
        present_in = [lab for lab in labels if name in by_label[lab]]
        missing_in = [lab for lab in labels if name not in by_label[lab]]
        if missing_in and present_in:
            added_removed += 1
            details.append(
                {
                    "definition": name,
                    "changeTags": (
                        ["DEFINITION_ADDED"] if baseline_lab in missing_in else ["DEFINITION_REMOVED"]
                    )
                    + (["DEFINITION_ADDED"] if any(lab != baseline_lab and lab in present_in and name not in baseline_map for lab in labels) else [])
                    + (["DEFINITION_REMOVED"] if any(lab != baseline_lab and lab in missing_in and name in baseline_map for lab in labels) else []),
                    "presentIn": present_in,
                    "missingIn": missing_in,
                }
            )
            # normalize tags unique
            details[-1]["changeTags"] = sorted(set(details[-1]["changeTags"])) or ["UNKNOWN_CHANGE"]
            continue

        if name not in baseline_map:
            continue
        # Compare each other version to baseline
        tags_union: set[str] = set()
        per_version: list[dict[str, Any]] = []
        for lab, sch in schemas[1:]:
            other = by_label[lab].get(name)
            if other is None:
                continue
            tags = _classify_def_change(baseline_map[name], other)
            if not tags:
                tags = ["IDENTICAL"]
            else:
                tags_union.update(t for t in tags if t != "IDENTICAL")
            per_version.append({"label": lab, "changeTags": tags})
            if any(t in {"REFERENCE_ADDED", "REFERENCE_REMOVED"} for t in tags):
                reference_changes += 1

        if not tags_union:
            identical += 1
            details.append(
                {
                    "definition": name,
                    "changeTags": ["IDENTICAL"],
                    "presentIn": present_in,
                    "perVersion": per_version,
                }
            )
        else:
            changed += 1
            details.append(
                {
                    "definition": name,
                    "changeTags": sorted(tags_union),
                    "presentIn": present_in,
                    "perVersion": per_version,
                }
            )

    summary = {
        "labels": labels,
        "baseline": baseline_lab,
        "definitionsUnion": len(all_names),
        "definitionsCommonToAll": len(common_to_all),
        "identicalDefinitions": identical,
        "changedDefinitions": changed,
        "addedOrRemovedDefinitions": added_removed,
        "referenceChangeEvents": reference_changes,
    }
    return {
        "kind": "MnuVersionDiff",
        "version": 1,
        "summary": summary,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Site Forge interest inventory
# ---------------------------------------------------------------------------


def inventory_siteforge_interest(*schemas: MnuSchema) -> dict[str, Any]:
    known: set[str] = set()
    for schema in schemas:
        for d in schema.definitions:
            known.add(d.name)

    rel = extract_references(*schemas)
    referenced = set(rel["reverse"].keys()) | {
        r["targetDefinition"] for rows in rel["forward"].values() for r in rows
    }

    # Also match prefix families Sorter / Srt* and Sawtooth / Saw*
    def_names = sorted(known)
    extras = [
        n
        for n in def_names
        if n.startswith("Srt")
        or n.startswith("Sorter")
        or n.startswith("Saw")
        or n.upper().startswith("SAW")
    ]

    def status_for(name: str) -> str:
        if name in known:
            return "PRESENT"
        if name in referenced:
            return "REFERENCED_ONLY"
        return "NOT_FOUND"

    items = []
    for name in SITEFORGE_INTEREST:
        st = status_for(name)
        entry: dict[str, Any] = {"name": name, "status": st}
        if st == "PRESENT":
            origins = sorted(
                {
                    schema.origin
                    for schema in schemas
                    for d in schema.definitions
                    if d.name == name
                }
            )
            entry["origins"] = origins
            entry["fieldCount"] = max(
                (
                    len(d.fields)
                    for schema in schemas
                    for d in schema.definitions
                    if d.name == name
                ),
                default=0,
            )
            entry["referencedByCount"] = len(rel["reverse"].get(name) or [])
        elif st == "REFERENCED_ONLY":
            entry["referencedBy"] = rel["reverse"].get(name) or []
        items.append(entry)

    family = {
        "SorterFamily": sorted({n for n in def_names if n.startswith("Srt") or n.startswith("Sorter")}),
        "SawFamily": sorted(
            {
                n
                for n in def_names
                if n.startswith("Saw") or n.upper().startswith("SAW") or "Sawtooth" in n
            }
        ),
    }

    return {
        "kind": "SiteForgeMnuInterest",
        "version": 1,
        "items": items,
        "familiesPresent": family,
        "extraRelatedNames": extras,
    }


# ---------------------------------------------------------------------------
# Machine-specific ASC resolver (documented helper — not production-wired)
# ---------------------------------------------------------------------------


def resolve_asc_path(
    table: str,
    *,
    directory: Path | str,
    ac_name: str,
) -> dict[str, Any]:
    """Deterministic ASC resolution per developer evidence.

    Rule (exact):
      if Table.asc.<AC_NAME> exists → use it
      else → use Table.asc

    Does not invent other fallbacks.
    """
    directory = Path(directory)
    table = str(table or "").strip()
    ac = str(ac_name or "").strip()
    specific_name = f"{table}.asc.{ac}" if ac else ""
    generic_name = f"{table}.asc"
    specific = directory / specific_name if specific_name else None
    generic = directory / generic_name

    if specific is not None and specific.is_file():
        return {
            "table": table,
            "acName": ac,
            "directory": str(directory),
            "chosen": str(specific),
            "chosenKind": "MACHINE_SPECIFIC",
            "machineSpecificPath": str(specific),
            "machineSpecificExists": True,
            "genericPath": str(generic),
            "genericExists": generic.is_file(),
            "rule": "Table.asc.<AC_NAME> if exists else Table.asc",
        }
    return {
        "table": table,
        "acName": ac,
        "directory": str(directory),
        "chosen": str(generic) if generic.is_file() else None,
        "chosenKind": "GENERIC" if generic.is_file() else "MISSING",
        "machineSpecificPath": str(specific) if specific is not None else None,
        "machineSpecificExists": bool(specific and specific.is_file()),
        "genericPath": str(generic),
        "genericExists": generic.is_file(),
        "rule": "Table.asc.<AC_NAME> if exists else Table.asc",
    }


# ---------------------------------------------------------------------------
# Artifact / report builders
# ---------------------------------------------------------------------------


def default_mnu_corpus() -> list[Path]:
    """Discover workspace .mnu files under FortnaPlus (analysis corpus)."""
    paths = sorted(ROOT.glob("workspace/**/*.mnu"))
    return [p for p in paths if p.is_file()]


def build_analysis_bundle(
    *,
    fortna_paths: list[Path],
    project_path: Path | None,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed_fortna: list[tuple[str, MnuSchema]] = []
    for p in fortna_paths:
        label = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
        parsed_fortna.append((label, parse_mnu_file(p, origin="FORTNA")))

    project_schema = parse_mnu_file(project_path, origin="PROJECT") if project_path else None

    # Primary fortna for combined/relationships (first path)
    primary_label, primary = parsed_fortna[0]
    schemas_for_rel: list[MnuSchema] = [primary]
    if project_schema:
        schemas_for_rel.append(project_schema)

    combined = combine_schemas(schemas_for_rel)
    relationships = extract_references(*schemas_for_rel)
    interest = inventory_siteforge_interest(*schemas_for_rel)
    version_diff = diff_schemas(parsed_fortna)

    files_analyzed = [
        {
            "path": lab,
            "origin": "FORTNA",
            "definitions": sch.stats.get("definitions"),
            "fields": sch.stats.get("fields"),
            "lines": sch.stats.get("lines"),
            "bytes": Path(sch.sourceFile).stat().st_size if Path(sch.sourceFile).is_file() else None,
        }
        for lab, sch in parsed_fortna
    ]
    if project_schema:
        files_analyzed.append(
            {
                "path": str(project_path.relative_to(ROOT))
                if project_path and project_path.is_relative_to(ROOT)
                else str(project_path),
                "origin": "PROJECT",
                "definitions": project_schema.stats.get("definitions"),
                "fields": project_schema.stats.get("fields"),
                "lines": project_schema.stats.get("lines"),
                "bytes": Path(project_schema.sourceFile).stat().st_size
                if Path(project_schema.sourceFile).is_file()
                else None,
            }
        )

    schema_artifact = {
        "kind": "MnuSchemaBundle",
        "version": 1,
        "filesAnalyzed": files_analyzed,
        "primaryFortna": primary_label,
        "fortna": schema_to_dict(primary),
        "project": schema_to_dict(project_schema) if project_schema else None,
        "combined": combined,
        "uninterpreted": {
            "note": (
                "Numeric DTYPE/DLEN/DLOW/DHIGH/DSRC/DSECR/… meanings are preserved as raw "
                "values only. This decoder does not map them to application datatypes."
            ),
            "observedDsrcValues": sorted(
                {
                    f.rawDataSource
                    for sch in schemas_for_rel
                    for d in sch.definitions
                    for f in d.fields
                    if f.rawDataSource != ""
                }
            )[:50],
            "menuMetadataKeysUnknownSemantics": [
                c for c in primary.menuColumns if c != "MNUNAME"
            ],
            "fieldMetadataKeysUnknownSemantics": [
                c
                for c in primary.fieldColumns
                if c
                not in {
                    "COLNAME",
                    # Named for convenience mapping only — semantics still unknown:
                    "DTYPE",
                    "DLEN",
                    "DLOW",
                    "DHIGH",
                    "DLIST",
                    "DSRC",
                }
            ],
        },
    }

    (out_dir / "mnu-schema.json").write_text(_stable_json(schema_artifact), encoding="utf-8")
    (out_dir / "mnu-relationships.json").write_text(
        _stable_json(
            {
                **relationships,
                "siteForgeInterest": interest,
                "filesAnalyzed": files_analyzed,
            }
        ),
        encoding="utf-8",
    )
    (out_dir / "mnu-version-diff.json").write_text(_stable_json(version_diff), encoding="utf-8")

    return {
        "filesAnalyzed": files_analyzed,
        "primary": primary,
        "project": project_schema,
        "combined": combined,
        "relationships": relationships,
        "interest": interest,
        "versionDiff": version_diff,
        "outDir": str(out_dir),
    }


def write_docs(bundle: dict[str, Any]) -> None:
    docs = ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    primary: MnuSchema = bundle["primary"]
    rel = bundle["relationships"]
    interest = bundle["interest"]
    vdiff = bundle["versionDiff"]
    files = bundle["filesAnalyzed"]
    combined = bundle["combined"]

    schema_md = []
    schema_md.append("# FortnaPlus `.mnu` Schema (Proven Grammar)\n")
    schema_md.append(
        "Archaeology checkpoint. This document records only what the supplied "
        "`fortna.mnu` / `project.mnu` files prove. Unknown column semantics remain unknown.\n"
    )
    schema_md.append("## Files analyzed\n")
    for f in files:
        schema_md.append(
            f"- `{f['path']}` · origin={f['origin']} · definitions={f['definitions']} · "
            f"fields={f['fields']} · lines={f['lines']} · bytes={f['bytes']}\n"
        )
    schema_md.append("\n## Proven top-level grammar\n")
    schema_md.append(
        "1. Line 1 is a dual header split by the literal token `***`.\n"
        "2. Tokens left of `***` name **menu/definition** columns.\n"
        "3. Tokens right of `***` name **field/column** columns.\n"
        "4. A **definition** begins on a row whose token count equals the menu-column "
        "count and whose final token matches `[01]{16}` (the `FLAGS` column).\n"
        "5. Subsequent non-blank rows are **fields** until a blank line.\n"
        "6. Blank lines separate definition blocks.\n"
        "7. Encoding observed: Latin-1 / LF.\n"
    )
    schema_md.append("\n### Menu columns (from file header)\n\n```\n")
    schema_md.append(" ".join(primary.menuColumns) + "\n```\n")
    schema_md.append("\n### Field columns (from file header)\n\n```\n")
    schema_md.append(" ".join(primary.fieldColumns) + "\n```\n")
    schema_md.append("\n## Convenience raw field mapping\n")
    schema_md.append(
        "For readability the decoder exposes these header names as convenience fields "
        "without asserting application datatype meaning:\n\n"
        "| Convenience | Header token |\n|---|---|\n"
        "| `name` | `COLNAME` / `MNUNAME` |\n"
        "| `rawDatatype` | `DTYPE` |\n"
        "| `rawLength` | `DLEN` |\n"
        "| `rawLow` | `DLOW` |\n"
        "| `rawHigh` | `DHIGH` |\n"
        "| `rawList` | `DLIST` |\n"
        "| `rawDataSource` | `DSRC` |\n"
    )
    schema_md.append("\n## Cross-table name evidence\n")
    schema_md.append(
        "When `DLIST` is a non-blank quoted string, the decoder records "
        "`listReference = <unquoted DLIST>`.\n"
        "If that string equals an `MNUNAME` present in the loaded schema(s), "
        "`resolved=true`.\n\n"
        "**Not asserted:** that `DLIST` is a foreign key, that `DSRC` selects a "
        "join key, or that any numeric code maps to a PLC type.\n"
    )
    schema_md.append("\n## FORTNA vs PROJECT combination\n")
    schema_md.append(
        f"Combined unique definition names: **{combined['uniqueDefinitionNames']}**.\n"
        f"Name collisions across origins (reported, not auto-resolved): "
        f"**{combined['collisionCount']}**.\n\n"
        "Policy: `NONE_APPLIED_REPORT_ONLY` — both copies are retained with provenance.\n"
    )
    schema_md.append("\n## Multi-version fortna.mnu summary\n")
    s = vdiff.get("summary") or {}
    schema_md.append(
        f"- Definitions union: {s.get('definitionsUnion')}\n"
        f"- Common to all versions: {s.get('definitionsCommonToAll')}\n"
        f"- Identical (vs baseline): {s.get('identicalDefinitions')}\n"
        f"- Changed (vs baseline): {s.get('changedDefinitions')}\n"
        f"- Added/removed: {s.get('addedOrRemovedDefinitions')}\n"
        f"- Reference change events: {s.get('referenceChangeEvents')}\n"
    )
    schema_md.append("\n## Machine-specific ASC resolution (documented helper only)\n")
    schema_md.append(
        "Developer-provided rule (not wired into production):\n\n"
        "```\n"
        "if Table.asc.<AC_NAME> exists:\n"
        "    use Table.asc.<AC_NAME>\n"
        "else:\n"
        "    use Table.asc\n"
        "```\n\n"
        "Implemented as `resolve_asc_path()` in `tools/scripts/fortna_mnu_schema.py` "
        "with unit tests. Not integrated into Site Forge production loaders.\n"
    )
    schema_md.append("\n## What remains UNKNOWN\n")
    schema_md.append(
        "- Meaning of numeric `DTYPE`, `DLEN`, `DLOW`, `DHIGH`, `DSRC`, and other "
        "menu/field metadata columns beyond their header names.\n"
        "- Whether `DLIST` is always a definition reference, a pick-list name, or both.\n"
        "- FortnaPlus runtime precedence between colliding `fortna.mnu` and "
        "`project.mnu` definitions (collisions reported only).\n"
    )
    (docs / "FORTNAPLUS_MNU_SCHEMA.md").write_text("".join(schema_md), encoding="utf-8")

    rel_md = []
    rel_md.append("# FortnaPlus `.mnu` Relationships (Site Forge interest)\n")
    rel_md.append(
        "Explicit cross-table name tokens from `DLIST` in the analyzed "
        "`fortna.mnu` + `project.mnu`. Similar equipment names are **not** evidence.\n"
    )
    rel_md.append(
        f"\nTotal DLIST name tokens: **{rel['referenceCount']}** · "
        f"resolved: **{rel['resolvedCount']}** · "
        f"unresolved: **{rel['unresolvedCount']}**\n"
    )
    rel_md.append("\n## Site Forge-relevant definitions\n\n")
    rel_md.append("| Name | Status | Notes |\n|---|---|---|\n")
    for item in interest["items"]:
        notes = ""
        if item["status"] == "PRESENT":
            notes = (
                f"origins={item.get('origins')}; fields={item.get('fieldCount')}; "
                f"referencedBy={item.get('referencedByCount')}"
            )
        elif item["status"] == "REFERENCED_ONLY":
            notes = "named in DLIST but no MNUNAME definition in loaded schemas"
        else:
            notes = "not present as MNUNAME and not named in DLIST"
        rel_md.append(f"| `{item['name']}` | **{item['status']}** | {notes} |\n")

    fam = interest.get("familiesPresent") or {}
    if fam.get("SorterFamily") or fam.get("SawFamily"):
        rel_md.append("\n### Related family names present as definitions\n")
        if fam.get("SorterFamily"):
            rel_md.append("- Sorter/Srt*: " + ", ".join(f"`{n}`" for n in fam["SorterFamily"][:40]) + "\n")
        if fam.get("SawFamily"):
            rel_md.append("- Saw*/Sawtooth: " + ", ".join(f"`{n}`" for n in fam["SawFamily"][:40]) + "\n")

    # Highlight a few high-value forward graphs
    highlight = [
        "HeightWidth",
        "Mtrchain",
        "EStop",
        "MergeBoss",
        "MergeInputs",
        "Jamcheck",
        "Jamzones",
        "Conveyor",
    ]
    rel_md.append("\n## Forward references (selected)\n")
    for name in highlight:
        rows = rel["forward"].get(name) or []
        if not rows and name not in {d for d in rel["forward"]}:
            # still show if definition exists with zero refs
            continue
        rel_md.append(f"\n### `{name}`\n")
        if not rows:
            rel_md.append("_No non-blank DLIST tokens on fields._\n")
            continue
        for r in rows:
            mark = "→" if r["resolved"] else "↛ (unresolved)"
            rel_md.append(
                f"- `{r['sourceField']}` {mark} `{r['targetDefinition']}` "
                f"(origin={r['origin']}, line={r['sourceLine']})\n"
            )

    rel_md.append("\n## Reverse lookup — `Conveyor`\n")
    conv_rev = rel["reverse"].get("Conveyor") or []
    rel_md.append(f"Referenced by **{len(conv_rev)}** field(s).\n\n")
    for r in conv_rev[:80]:
        rel_md.append(
            f"- `{r['sourceDefinition']}.{r['sourceField']}` "
            f"(origin={r['origin']}, line={r['sourceLine']})\n"
        )
    if len(conv_rev) > 80:
        rel_md.append(f"- … +{len(conv_rev) - 80} more (see `artifacts/mnu-relationships.json`)\n")

    rel_md.append(
        "\n## Semantics caution\n"
        "These edges are **schema name tokens from DLIST**, not proven runtime joins, "
        "not physical topology, and not PLC tag ownership.\n"
    )
    (docs / "FORTNAPLUS_MNU_RELATIONSHIPS.md").write_text("".join(rel_md), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FortnaPlus .mnu schema archaeology decoder")
    ap.add_argument(
        "--fortna",
        action="append",
        default=[],
        help="Path to fortna.mnu (repeatable for version diff)",
    )
    ap.add_argument("--project", default="", help="Path to project.mnu")
    ap.add_argument(
        "--out-dir",
        default=str(ROOT / "artifacts"),
        help="Directory for JSON artifacts",
    )
    ap.add_argument("--write-docs", action="store_true", help="Write docs/*.md")
    ap.add_argument(
        "--corpus-default",
        action="store_true",
        help="Use workspace/**/FORTNA/fortna.mnu + one project.mnu from plc2 peek",
    )
    args = ap.parse_args(argv)

    fortna_paths = [Path(p) for p in args.fortna]
    project_path = Path(args.project) if args.project else None

    if args.corpus_default or not fortna_paths:
        fortna_paths = sorted(ROOT.glob("workspace/**/FORTNA/fortna.mnu"))
        if project_path is None:
            cand = ROOT / "workspace/_plc2_run_peek/RUN/PROJECT/project.mnu"
            if cand.is_file():
                project_path = cand

    if not fortna_paths:
        print("No fortna.mnu paths found")
        return 2

    bundle = build_analysis_bundle(
        fortna_paths=fortna_paths,
        project_path=project_path if project_path and project_path.is_file() else None,
        out_dir=Path(args.out_dir),
    )
    if args.write_docs:
        write_docs(bundle)

    print("Analyzed", len(bundle["filesAnalyzed"]), "file(s)")
    for f in bundle["filesAnalyzed"]:
        print(
            f"  {f['origin']:7} defs={f['definitions']:4} fields={f['fields']:5}  {f['path']}"
        )
    rel = bundle["relationships"]
    print(
        f"References: total={rel['referenceCount']} resolved={rel['resolvedCount']} "
        f"unresolved={rel['unresolvedCount']}"
    )
    print(f"Artifacts -> {bundle['outDir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
