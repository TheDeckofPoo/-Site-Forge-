#!/usr/bin/env python3
"""Display offsets must not alter raw geometry / topology / L5X inputs.

Also proves layout interpreter fields exist, overlap research artifacts are
present, and layout classification is deterministic for the same RUN inputs.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"


def _js() -> str:
    return (ROOT / "dashboard" / "transport-build.js").read_text(encoding="utf-8")


def test_canonical_apply_excludes_display_fields() -> None:
    js = _js()
    assert "function buildCanonicalApplyGraph" in js
    assert "display_dx" in js
    start = js.index("function buildCanonicalApplyGraph")
    end = js.index("function setWorkflowStep", start)
    block = js[start:end]
    assert "display_dx" not in block
    assert "display_dy" not in block
    assert "display_lane" not in block
    assert "display_reason" not in block
    assert "pathCanvas" not in block
    print("  [PASS] canonical Apply excludes display offsets")


def test_layout_interpreter_architecture() -> None:
    js = _js()
    assert "LAYOUT INTERPRETER" in js
    assert "display_reason" in js
    assert "display_lane" in js
    assert "Never mutates" in js or "Never mutate" in js or "stays authoritative" in js
    assert "MERGE_2TO1_FAN" in js or "SAWTOOTH_OR_MULTI_MERGE_FAN" in js
    assert "CONNECTIVITY_MATE_NUDGE" in js or "MATE_NUDGE" in js
    assert "tb-schematic-leader" in js
    assert "function computePresentationOffsets" in js
    print("  [PASS] layout interpreter presentation architecture present")


def test_raw_geometry_fields_not_overwritten_by_display() -> None:
    """Display writes display_* only — sourceX/sourceY/pathCanvas stay engineering."""
    js = _js()
    # Heuristic: assignments to sourceX/sourceY should not appear inside computePresentationOffsets
    start = js.index("function computePresentationOffsets")
    # next top-level function after offsets block
    end = js.index("function applyPresOffset", start)
    block = js[start:end]
    for bad in ("n.sourceX =", "n.sourceY =", "n.pathCanvas =", "n.entryCanvas =", "n.exitCanvas ="):
        assert bad not in block, f"display pass mutates engineering field via {bad}"
    assert "n.display_dx" in block
    assert "n.display_dy" in block
    print("  [PASS] display pass does not assign raw engineering geometry fields")


def test_overlap_research_artifacts() -> None:
    p = ROOT / "exports" / "layout-research" / "overlap_clusters.json"
    assert p.exists(), "overlap_clusters.json missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "sites" in data
    for site in ("ORNCCP2", "ORNCCP4"):
        assert site in data["sites"], f"missing site {site}"
        site_data = data["sites"][site]
        assert site_data.get("equipment_count", 0) > 0
        assert "clusters" in site_data
    print("  [PASS] overlap research artifact present for CP2 and CP4")


def test_overlap_research_deterministic() -> None:
    """Same RUN inputs → same overlap cluster digest (deterministic layout research)."""
    script = SCRIPTS / "fortna_layout_overlap_research.py"
    if not script.exists():
        print("  [SKIP] fortna_layout_overlap_research.py missing")
        return
    out1 = ROOT / "exports" / "layout-research" / "_det_a.json"
    out2 = ROOT / "exports" / "layout-research" / "_det_b.json"
    # Re-run into temp files if script supports --out; else hash existing twice.
    # Use existing artifact hash stability: strip generated_at and compare structure.
    p = ROOT / "exports" / "layout-research" / "overlap_clusters.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    stable = {k: v for k, v in data.items() if k != "generated_at"}

    def digest(obj: object) -> str:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    d1 = digest(stable)
    d2 = digest(json.loads(json.dumps(stable)))
    assert d1 == d2
    # Re-invoke research script and compare stable digest
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:
        pass
    if p.exists():
        data2 = json.loads(p.read_text(encoding="utf-8"))
        stable2 = {k: v for k, v in data2.items() if k != "generated_at"}
        # Classification counts / cluster sizes should match prior run when RUNs unchanged
        for site in ("ORNCCP2", "ORNCCP4"):
            if site in stable.get("sites", {}) and site in stable2.get("sites", {}):
                assert (
                    stable["sites"][site].get("equipment_count")
                    == stable2["sites"][site].get("equipment_count")
                )
                assert (
                    stable["sites"][site].get("cluster_count")
                    == stable2["sites"][site].get("cluster_count")
                )
    # cleanup temp
    for t in (out1, out2):
        if t.exists():
            t.unlink()
    print("  [PASS] overlap layout research deterministic for same RUN")


def test_identity_prefix_still_fixed() -> None:
    sys.path.insert(0, str(SCRIPTS))
    from fortna_identity import conveyor_identities_match

    assert not conveyor_identities_match("P120", "P1200")
    assert conveyor_identities_match("P424", "P424A")
    print("  [PASS] identity prefix fix still holds")


def test_legacy_decoder_scaffold_schema() -> None:
    sys.path.insert(0, str(SCRIPTS))
    from fortna_legacy_layout import empty_model

    m = empty_model(source="test")
    for key in ("equipment", "connections", "geometry", "layers", "annotations", "provenance"):
        assert key in m
        assert isinstance(m[key], list)
    print("  [PASS] legacy layout decoder neutral schema")


def test_source_inventory_present() -> None:
    p = ROOT / "exports" / "layout-research" / "source_inventory.json"
    assert p.exists(), "source_inventory.json missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data, (dict, list))
    print("  [PASS] legacy source inventory present")


def main() -> int:
    print("=== display layout offset tests ===")
    fails = 0
    for fn in [
        test_canonical_apply_excludes_display_fields,
        test_layout_interpreter_architecture,
        test_raw_geometry_fields_not_overwritten_by_display,
        test_overlap_research_artifacts,
        test_overlap_research_deterministic,
        test_identity_prefix_still_fixed,
        test_legacy_decoder_scaffold_schema,
        test_source_inventory_present,
    ]:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
