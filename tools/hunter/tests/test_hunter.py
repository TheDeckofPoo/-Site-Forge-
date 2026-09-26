"""Hunter MVP tests — evidence contract, conservation, determinism, safety laws.

Run from the repo root:
    python -m pytest tools/hunter/tests -q
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.hunter import ALLOWED_STATES, EXTRACTOR_VERSION
from tools.hunter.device_grammar import classify_token, normalize_label
from tools.hunter.evidence_records import EvidenceRecord
from tools.hunter.pipeline import run_hunter

HERE = Path(__file__).resolve().parent
PRINTS = HERE / "fixtures" / "prints"
SET_A = PRINTS / "print_set_a.pdf"
SCHEMAS = HERE.parent / "schemas"
REPO_ROOT = HERE.parents[2]
FIXED_TS = "2026-01-01T00:00:00+00:00"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("hunter_out")
    res = run_hunter(PRINTS, out, project="SYNTH", controller="PLC01", generated_at=FIXED_TS)
    return out, res


def _evidence(out: Path):
    return [json.loads(l) for l in (out / "hunter_evidence.jsonl").read_text(encoding="utf-8").splitlines()]


def _labels(ev, label):
    return [r for r in ev if r["raw_device_label"] == label and r["evidence_type"] == "DEVICE_LABEL"]


# ----------------------------------------------------------------- outputs
def test_all_outputs_written(run_dir):
    out, _ = run_dir
    for name in ("hunter_manifest.json", "hunter_evidence.jsonl", "hunter_device_index.csv",
                 "hunter_summary.json", "hunter_review_queue.json", "hunter_sheet_index.json"):
        assert (out / name).is_file(), name


def test_manifest_hashes_and_metadata(run_dir):
    out, _ = run_dir
    m = json.loads((out / "hunter_manifest.json").read_text())
    assert m["read_only"] is True and m["llm_used"] is False and m["ocr_enabled"] is False
    assert m["project"] == "SYNTH" and m["controller_scope_hint"] == "PLC01"
    names = [i["source_document"] for i in m["inputs"]]
    assert names == ["print_set_a.pdf", "print_set_b.pdf"]
    for i in m["inputs"]:
        assert i["sha256"] == hashlib.sha256((PRINTS / i["source_document"]).read_bytes()).hexdigest()


# -------------------------------------------------------------- provenance
def test_every_record_has_provenance(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    assert ev
    for r in ev:
        assert r["source_document"] and re.fullmatch(r"[0-9a-f]{64}", r["source_document_hash"])
        assert r["extractor_version"] == EXTRACTOR_VERSION
        assert r["evidence_id"].startswith("HE-")
        if r["evidence_type"] in ("TEXT_LAYER_MISSING", "DOCUMENT_READ_ERROR"):
            assert r["notes"], "failure records must explain themselves"
        else:
            assert r["page_number"] >= 1
            assert r["raw_text"].strip()
            assert r["bbox"] is not None
            if r["raw_device_label"]:
                assert r["raw_device_label"] in r["raw_text"], "raw label must be literally in printed text"


def test_why_does_hunter_think_esls161_exists(run_dir):
    out, _ = run_dir
    recs = _labels(_evidence(out), "ESLS161")
    assert recs
    r = [x for x in recs if x["state"] == "PROVEN"][0]
    assert r["source_document"] == "print_set_a.pdf"
    assert r["page_number"] == 2 and r["sheet_number"] == "E-102"
    assert r["sheet_title"] == "SAFETY CIRCUIT" and r["drawing_revision"] == "A"
    assert r["raw_text"] == "PULL CORD ESLS161"
    assert set(r["bbox"]) == {"x0", "top", "x1", "bottom"}


def test_provenance_law_enforced_by_constructor():
    with pytest.raises(ValueError):
        EvidenceRecord(project=None, controller_scope_hint=None, source_document="x.pdf",
                       source_document_hash="0" * 64, page_number=1, evidence_type="DEVICE_LABEL",
                       raw_text="", state="DERIVED", confidence=0.5)
    with pytest.raises(ValueError):
        EvidenceRecord(project=None, controller_scope_hint=None, source_document="x.pdf",
                       source_document_hash="0" * 64, page_number=1, evidence_type="DEVICE_LABEL",
                       raw_text="P1300", state="ENGINEER_ASSIGNED", confidence=0.5)


# ------------------------------------------------------------ states / law
def test_only_allowed_states_never_engineer_assigned(run_dir):
    out, _ = run_dir
    for r in _evidence(out):
        assert r["state"] in ALLOWED_STATES
    for p in out.iterdir():
        assert "ENGINEER_ASSIGNED" not in p.read_text(encoding="utf-8"), p.name


def test_no_safety_zone_or_area_membership_from_naming(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    forbidden_keys = re.compile(r"zone|area|safety_group", re.I)
    for r in ev:
        for k in r:
            assert not forbidden_keys.search(k), k
        assert "ZONE" not in (r["evidence_type"] or "")
        assert "ZONE" not in (r["relationship_kind"] or "")
        assert "zone" not in (r["entity_type_candidate"] or "").lower()
    # "SAFETY ZONE Z1" printed text must not create any relationship
    assert not [r for r in ev if r["evidence_type"] == "RELATIONSHIP" and "ZONE" in r["raw_text"]]
    # safety labels are explicitly marked as carrying no zone membership
    for r in ev:
        if r["evidence_type"] == "DEVICE_LABEL" and r["entity_type_candidate"] in ("esls", "espb", "estop", "esr", "mcr"):
            assert any("no Safety-zone" in n for n in r["notes"])


def test_no_plc_build_instructions(run_dir):
    out, _ = run_dir
    bad = re.compile(r"<RSLogix5000Content|\.L5X\b|\bXIC\(|\bOTE\(|\bOTL\(|\bJSR\(|\bRung\b|\bAOI\b", re.I)
    for p in out.iterdir():
        assert not bad.search(p.read_text(encoding="utf-8")), p.name


def test_controller_hint_is_metadata_only(run_dir, tmp_path):
    out, _ = run_dir
    other = run_hunter(PRINTS, tmp_path, project="SYNTH", controller="SOME_OTHER_PLC", generated_at=FIXED_TS)
    a = [(r["raw_device_label"], r["evidence_type"], r["state"], r["page_number"]) for r in _evidence(out)]
    b = [(r.raw_device_label, r.evidence_type, r.state, r.page_number) for r in other["records"]]
    assert a == b


# ------------------------------------------------------- conservation etc.
def test_unknown_token_conserved_and_queued(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    unk = [r for r in ev if r["raw_device_label"] == "XQ7731"]
    assert len(unk) == 1
    u = unk[0]
    assert u["state"] == "UNKNOWN" and u["evidence_type"] == "UNKNOWN_DEVICE_TOKEN"
    assert u["page_number"] == 4 and "XQ7731 SPARE" in u["raw_text"] and u["context_text"]
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "UNRECOGNIZED_DEVICE_TOKEN" and i["raw_device_label"] == "XQ7731" for i in q)
    rows = list(csv.DictReader((out / "hunter_device_index.csv").open()))
    assert any(r["raw_label"] == "XQ7731" and r["state"] == "UNKNOWN" for r in rows)
    s = json.loads((out / "hunter_summary.json").read_text())
    assert s["unknown_token_count"] == 1


def test_ambiguous_token_review_required(run_dir):
    out, _ = run_dir
    amb = [r for r in _evidence(out) if r["raw_device_label"] == "S1300"]
    assert amb and amb[0]["state"] == "REVIEW_REQUIRED" and amb[0]["evidence_type"] == "AMBIGUOUS_DEVICE_TOKEN"
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "AMBIGUOUS_TYPE" and i["raw_device_label"] == "S1300" for i in q)


@pytest.mark.parametrize("label,family", [
    ("P1300", "conveyor"), ("M1300", "motor"), ("VFD1300", "vfd"), ("PE1300", "photoeye"),
    ("MCP1", "control_panel"), ("CP2", "control_panel"), ("PLC01", "controller"),
    ("RIO1", "remote_io_panel"), ("SCN1600", "scanner"), ("MRG1400", "merge"),
    ("DIV1500", "divert"), ("CS1300", "control_station"), ("SL1300", "stacklight"),
    ("ESPB101", "espb"), ("1ES3", "estop"), ("ESLS161", "esls"), ("ESR1", "esr"),
    ("ESR-2A", "esr"), ("MCR1", "mcr"),
])
def test_fixture_families_detected(run_dir, label, family):
    out, _ = run_dir
    recs = _labels(_evidence(out), label)
    assert recs, label
    assert {r["entity_type_candidate"] for r in recs} == {family}


def test_naming_alone_is_not_proven(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    cp2 = _labels(ev, "CP2")[0]  # printed with no descriptive text
    assert cp2["state"] == "DERIVED"
    esr2a = _labels(ev, "ESR-2A")[0]
    assert esr2a["state"] == "DERIVED"
    esls = [r for r in _labels(ev, "ESLS161") if r["raw_text"] == "PULL CORD ESLS161"][0]
    assert esls["state"] == "PROVEN"


def test_same_device_on_multiple_sheets_not_merged(run_dir):
    out, _ = run_dir
    recs = _labels(_evidence(out), "P1300")
    places = {(r["source_document"], r["sheet_number"], r["page_number"]) for r in recs}
    assert ("print_set_a.pdf", "E-101", 1) in places
    assert ("print_set_a.pdf", "E-102", 2) in places
    assert ("print_set_b.pdf", "E-201", 1) in places
    s = json.loads((out / "hunter_summary.json").read_text())
    obs = [o for o in s["duplicate_raw_label_observations"] if o["normalized_name_candidate"] == "P1300"]
    assert obs and obs[0]["occurrence_count"] == len(_evidence_label_all(out, "P1300"))


def _evidence_label_all(out, norm):
    return [r for r in _evidence(out) if r["evidence_type"] == "DEVICE_LABEL"
            and r["normalized_name_candidate"] == norm]


def test_raw_labels_preserved_and_not_auto_merged(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    dash = _labels(ev, "P-1300")
    assert dash and dash[0]["normalized_name_candidate"] == "P1300"
    assert dash[0]["raw_device_label"] == "P-1300"
    # both raw forms remain separate records
    assert _labels(ev, "P1300")
    s = json.loads((out / "hunter_summary.json").read_text())
    variants = [o for o in s["duplicate_raw_label_observations"] if o["kind"] == "RAW_LABEL_VARIANTS"]
    assert any(o["raw_labels"] == ["P-1300", "P1300"] for o in variants)
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "POSSIBLE_CONFLICTING_LABELS" for i in q)
    rows = list(csv.DictReader((out / "hunter_device_index.csv").open()))
    assert any(r["raw_label"] == "P-1300" for r in rows) and any(r["raw_label"] == "P1300" for r in rows)


# ----------------------------------------------------------- relationships
def _rels(ev):
    return [r for r in ev if r["evidence_type"] == "RELATIONSHIP"]


def test_explicit_relationships_proven(run_dir):
    out, _ = run_dir
    rels = {(r["raw_device_label"], r["related_device_text"] or r["physical_address_text"] or r["module_or_terminal_text"]): r
            for r in _rels(_evidence(out)) if r["state"] == "PROVEN"}
    assert rels[("M1300", "P1300")]["state"] == "PROVEN"  # "MOTOR M1300 DRIVES P1300"
    assert rels[("PE1300", "P1300")]["state"] == "PROVEN"  # "PE1300 MOUNTED ON P1300"
    assert rels[("ESLS161", "ESR1")]["state"] == "PROVEN"  # "ESLS161 IN SAFETY CIRCUIT ESR1"
    assert rels[("PE1301", "TB1-12")]["state"] == "PROVEN"  # "TB1-12 -> PE1301"
    assert rels[("PE1302", "I:1/3")]["state"] == "PROVEN"  # "I:1/3 TO PE1302"


def test_weak_relationships_not_proven(run_dir):
    out, _ = run_dir
    rels = _rels(_evidence(out))
    weak = [r for r in rels if r["page_number"] == 4 and r["source_document"] == "print_set_a.pdf"]
    assert weak and all(r["state"] == "REVIEW_REQUIRED" for r in weak)  # "M1300 P1300"
    row = [r for r in rels if r["physical_address_text"] == "Local:3:I.Data.0"]
    assert row and row[0]["state"] == "DERIVED"
    multi = [r for r in rels if r["physical_address_text"] == "Local:3:I.Data.2"]
    assert len(multi) == 2 and all(r["state"] == "REVIEW_REQUIRED" for r in multi)
    # nothing relates devices merely for being on the same page
    assert not [r for r in rels if r["raw_device_label"] == "SCN1600"]


def test_printed_io_extracted_and_never_invented(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    io = sorted(r["physical_address_text"] for r in ev if r["evidence_type"] == "IO_REFERENCE")
    assert "Local:3:I.Data.0" in io and "I:1/3" in io and "SLOT 3" in io
    # every I/O text anywhere in the evidence is literally in its printed line
    for r in ev:
        for k in ("physical_address_text", "module_or_terminal_text"):
            if r[k]:
                assert r[k] in r["raw_text"]
    assert any(r["evidence_type"] == "IO_MODULE_REFERENCE" and r["module_or_terminal_text"] == "1734-IB8" for r in ev)
    assert any(r["evidence_type"] == "TERMINAL_REFERENCE" and r["module_or_terminal_text"] == "TB1-12" for r in ev)
    # devices that have no printed I/O carry none
    rows = {r["raw_label"]: r for r in csv.DictReader((out / "hunter_device_index.csv").open())}
    assert rows["SCN1600"]["printed_io"] == ""


def test_continuation_references(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    cont = {(r["page_number"], r["continuation_reference"]): r for r in ev if r["evidence_type"] == "CONTINUATION_REFERENCE"
            and r["source_document"] == "print_set_a.pdf"}
    assert cont[(1, "E-102")]["state"] == "PROVEN"
    assert any("present in input set" in n for n in cont[(1, "E-102")]["notes"])
    assert any("not in input set" in n for n in cont[(2, "E-999")]["notes"])
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "CONTINUATION_TARGET_NOT_IN_INPUT_SET" for i in q)


# ------------------------------------------------------- sheets / failures
def test_sheet_index_and_missing_title_block(run_dir):
    out, _ = run_dir
    sheets = json.loads((out / "hunter_sheet_index.json").read_text())["sheets"]
    by = {(s["source_document"], s["page_number"]): s for s in sheets}
    s1 = by[("print_set_a.pdf", 1)]
    assert (s1["sheet_number"], s1["sheet_title"], s1["drawing_revision"]) == ("E-101", "CONVEYOR POWER", "B")
    assert s1["state"] == "PROVEN"
    s4 = by[("print_set_a.pdf", 4)]
    assert s4["sheet_number"] is None and s4["state"] == "REVIEW_REQUIRED"
    assert "sheet_number" in s4["missing_fields"]
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "MISSING_TITLE_BLOCK" and i["page_number"] == 4 for i in q)


def test_image_only_page_text_layer_missing(run_dir):
    out, _ = run_dir
    ev = _evidence(out)
    p5 = [r for r in ev if r["source_document"] == "print_set_a.pdf" and r["page_number"] == 5]
    assert len(p5) == 1, "nothing may be hallucinated for an image-only page"
    assert p5[0]["evidence_type"] == "TEXT_LAYER_MISSING" and p5[0]["state"] == "REVIEW_REQUIRED"
    q = json.loads((out / "hunter_review_queue.json").read_text())["review_queue"]
    assert any(i["category"] == "TEXT_LAYER_MISSING" and i["page_number"] == 5 for i in q)
    s = json.loads((out / "hunter_summary.json").read_text())
    assert any(w["page_number"] == 5 for w in s["pages_with_extraction_warnings"])


# ------------------------------------------------------------- determinism
def test_deterministic_rerun(run_dir, tmp_path):
    out, _ = run_dir
    run_hunter(PRINTS, tmp_path, project="SYNTH", controller="PLC01", generated_at="2030-12-31T23:59:59+00:00")
    for name in ("hunter_evidence.jsonl", "hunter_device_index.csv", "hunter_summary.json",
                 "hunter_review_queue.json", "hunter_sheet_index.json"):
        assert (out / name).read_bytes() == (tmp_path / name).read_bytes(), name
    m1 = json.loads((out / "hunter_manifest.json").read_text())
    m2 = json.loads((tmp_path / "hunter_manifest.json").read_text())
    m1.pop("generated_at"); m2.pop("generated_at")
    m1.pop("input_path"); m2.pop("input_path")
    assert m1 == m2


def test_deterministic_across_locations(run_dir, tmp_path):
    out, _ = run_dir
    copy = tmp_path / "elsewhere"
    shutil.copytree(PRINTS, copy)
    run_hunter(copy, tmp_path / "o", project="SYNTH", controller="PLC01", generated_at=FIXED_TS)
    assert (out / "hunter_evidence.jsonl").read_bytes() == (tmp_path / "o" / "hunter_evidence.jsonl").read_bytes()


# ------------------------------------------------------------------ schema
def test_outputs_validate_against_schemas(run_dir):
    jsonschema = pytest.importorskip("jsonschema")
    out, _ = run_dir
    ev_schema = json.loads((SCHEMAS / "evidence_record.schema.json").read_text())
    mf_schema = json.loads((SCHEMAS / "hunter_manifest.schema.json").read_text())
    for r in _evidence(out):
        jsonschema.validate(r, ev_schema)
    jsonschema.validate(json.loads((out / "hunter_manifest.json").read_text()), mf_schema)


# --------------------------------------------------------------------- CLI
def test_cli_single_pdf(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "tools.hunter.cli", "--input", str(SET_A), "--out", str(tmp_path),
         "--project", "SYNTH", "--controller", "PLC01"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    m = json.loads((tmp_path / "hunter_manifest.json").read_text())
    assert m["input_mode"] == "file" and [i["source_document"] for i in m["inputs"]] == ["print_set_a.pdf"]


def test_cli_directory(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "tools.hunter.cli", "--input", str(PRINTS), "--out", str(tmp_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    m = json.loads((tmp_path / "hunter_manifest.json").read_text())
    assert m["input_mode"] == "directory" and len(m["inputs"]) == 2


def test_cli_missing_input(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "tools.hunter.cli", "--input", str(tmp_path / "nope.pdf"), "--out", str(tmp_path / "o")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 2


def test_corrupt_pdf_is_recorded_not_crashed(tmp_path):
    bad = tmp_path / "in" / "broken.pdf"
    bad.parent.mkdir()
    bad.write_bytes(b"%PDF-1.4\nthis is not really a pdf\n")
    res = run_hunter(bad.parent, tmp_path / "o", generated_at=FIXED_TS)
    types = [r.evidence_type for r in res["records"]]
    assert "DOCUMENT_READ_ERROR" in types
    assert any(q["category"] == "DOCUMENT_READ_ERROR" for q in res["review_queue"])


# ----------------------------------------------------------------- grammar
def test_grammar_units_and_vocabulary_not_devices():
    for t in ("24VDC", "120VAC", "480V", "AWG14", "REV1", "ESR", "MCR"):
        assert classify_token(t) is None, t
    assert normalize_label("p-1300") == "P1300"


def test_no_site_names_or_llm_in_core():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (HERE.parent).glob("*.py"))
    for banned in ("ORL", "TOPB", "Brownsburg", "Greensboro", "openai", "xai", "anthropic", "grok"):
        assert not re.search(r"\b" + banned + r"\b", src, re.I), banned
    assert not re.search(r"^\s*(import|from)\s+(fitz|pytesseract|easyocr|requests)\b", src, re.M)


def test_fixture_pdfs_regenerate_identically(tmp_path):
    pytest.importorskip("reportlab")
    sys.path.insert(0, str(HERE / "fixtures"))
    try:
        import make_fixtures
    finally:
        sys.path.pop(0)
    make_fixtures.build_all(tmp_path)
    for name in ("print_set_a.pdf", "print_set_b.pdf"):
        assert (tmp_path / name).read_bytes() == (PRINTS / name).read_bytes(), name
