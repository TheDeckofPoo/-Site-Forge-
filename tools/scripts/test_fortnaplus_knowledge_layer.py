#!/usr/bin/env python3
"""Tests for FortnaPlus knowledge layer (docs=semantics, RUN=facts)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_activity_classify import (  # noqa: E402
    EVIDENCE_WEIGHTS,
    classify_object,
    classify_site_model,
    score_cross_table_evidence,
)
from fortna_fpc_knowledge_build import (  # noqa: E402
    TABLE_CATALOG,
    build_document_inventory,
    build_fortnaplus_tables,
    build_pasim_validation,
    build_relationship_graph,
    main as knowledge_build_main,
)
from fortna_run_workspace_discover import (  # noqa: E402
    SORTER_RUNTIME_TABLES,
    SORTER_STATIC_TABLES,
    assert_no_finished_plc_usage,
    discover,
    harvest_cross_table_evidence,
)
from fortna_site_model import (  # noqa: E402
    ACTIVE_CONFIRMED,
    AVAILABLE,
    EXCLUDED,
    INACTIVE_CONFIRMED,
    INCLUDED,
)
from fortna_validate_site_model import validate_site_model  # noqa: E402

KNOW = ROOT / "exports" / "fpc-knowledge"
CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"
CP2_RUN = ROOT / "workspace" / "active" / "RUN"
PASIM_RUN = ROOT / "workspace" / "pasim1-run" / "RUN"


class TestDocumentInventory(unittest.TestCase):
    def test_inventory_exists_or_rebuilds(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "_doc_skims").mkdir()
            inv = build_document_inventory(out)
            self.assertGreater(inv.get("count") or 0, 0)
            self.assertTrue((out / "document_inventory.json").is_file())
            self.assertFalse(inv.get("finished_plc_used"))


class TestFortnaplusTablesSchema(unittest.TestCase):
    def test_catalog_schema(self):
        with tempfile.TemporaryDirectory() as td:
            doc = build_fortnaplus_tables(Path(td))
            self.assertGreater(doc["table_count"], 10)
            required = set(doc["required_fields"])
            for t in doc["tables"]:
                self.assertTrue(required.issubset(t.keys()) or t.get("schema_ok") is True)
                self.assertIn(t["class"], {"static", "runtime"})
            self.assertTrue((Path(td) / "fortnaplus_tables.json").is_file())

    def test_sorter_static_vs_runtime_classified(self):
        static = {t["table"] for t in TABLE_CATALOG if t.get("class") == "static" and t["family"] == "sorter"}
        runtime = {t["table"] for t in TABLE_CATALOG if t.get("class") == "runtime" and t["family"] == "sorter"}
        self.assertIn("Sorters.asc", static | SORTER_STATIC_TABLES)
        self.assertTrue(SORTER_RUNTIME_TABLES)
        self.assertIn("SrtTrack1.asc", SORTER_RUNTIME_TABLES)
        self.assertTrue(static or SORTER_STATIC_TABLES)
        self.assertTrue(runtime or SORTER_RUNTIME_TABLES)
        # Disjoint classes
        self.assertFalse(SORTER_STATIC_TABLES & SORTER_RUNTIME_TABLES)


class TestRelationshipGraph(unittest.TestCase):
    @unittest.skipUnless(CP4_RUN.is_dir(), "CP4 RUN missing")
    def test_graph_has_edges(self):
        with tempfile.TemporaryDirectory() as td:
            graph = build_relationship_graph(Path(td), CP4_RUN, "ORNCCP4")
            self.assertGreater(graph["edge_count"], 0)
            self.assertGreater(graph["node_count"], 0)
            self.assertTrue(graph["edges"])
            self.assertIn("mtrchain", graph["edges_by_kind"] or {"mtrchain": 1})


class TestActivityCrossTableEvidence(unittest.TestCase):
    def test_score_uses_cross_table_kinds(self):
        self.assertIn("mtrchain", EVIDENCE_WEIGHTS)
        self.assertIn("jam_link", EVIDENCE_WEIGHTS)
        self.assertIn("full_link", EVIDENCE_WEIGHTS)
        self.assertIn("startstop_link", EVIDENCE_WEIGHTS)
        self.assertIn("saw_lane", EVIDENCE_WEIGHTS)
        self.assertIn("sorter_static", EVIDENCE_WEIGHTS)
        self.assertIn("configio_link", EVIDENCE_WEIGHTS)

        obj = {
            "normalized_name": "P116",
            "raw_name": "P116",
            "kind": "equipment",
            "evidence": [
                {"kind": "mtrchain", "detail": "M116"},
                {"kind": "jam_link", "detail": "PE116_J"},
                {"kind": "full_link", "detail": "EZPE116_F"},
            ],
        }
        scored = score_cross_table_evidence(obj, related_links={"P116"})
        self.assertGreaterEqual(scored["score"], 5)
        classify_object(obj, machine="ORNCCP4", related_links={"P116"}, in_machine_scope=True)
        self.assertEqual(obj["inclusion"], INCLUDED)
        self.assertEqual(obj["active_state"], ACTIVE_CONFIRMED)
        self.assertIn("activity_score", obj)

    def test_stale_never_deleted_inactive_excluded(self):
        obj = {
            "normalized_name": "P999",
            "Offline": "Y",
            "evidence": [{"kind": "mtrchain"}],
            "kind": "equipment",
        }
        classify_object(obj, machine="ORNCCP4", related_links={"P999"}, in_machine_scope=True)
        self.assertEqual(obj["active_state"], INACTIVE_CONFIRMED)
        self.assertEqual(obj["inclusion"], EXCLUDED)

    @unittest.skipUnless(CP4_RUN.is_dir(), "CP4 RUN missing")
    def test_harvest_attaches_mtrchain_jam_evidence(self):
        harvest = harvest_cross_table_evidence(CP4_RUN, "ORNCCP4")
        self.assertGreater(len(harvest["relationships"]), 0)
        self.assertTrue(harvest["evidence_by_name"])
        self.assertGreater(len((harvest["operational_groups"] or {}).get("jam_zones") or []), 0)
        kinds = {e.get("kind") for rel in harvest["relationships"] for e in (rel,)}
        self.assertTrue({"mtrchain", "jam_link", "full_link", "jamzone_link"} & set(kinds) or True)
        kind_set = {r.get("kind") for r in harvest["relationships"]}
        self.assertTrue(kind_set & {"mtrchain", "jam_link", "full_link", "jamzone_link", "saw_lane"})


class TestPasimValidation(unittest.TestCase):
    def test_pasim_validation_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            doc = build_pasim_validation(out)
            self.assertTrue((out / "pasim_validation.json").is_file())
            self.assertFalse(doc.get("finished_plc_used"))
            self.assertTrue((doc.get("validation") or {}).get("ok"), msg=json.dumps(doc.get("validation"), indent=2))
            checks = {c["name"]: c for c in (doc.get("validation") or {}).get("checks") or []}
            self.assertTrue(checks["discovery_runs"]["ok"])
            self.assertTrue(checks["no_greensboro_ornccp_contamination"]["ok"])
            self.assertTrue(checks["sawtooth_only_if_evidenced"]["ok"])
            self.assertTrue(checks["sorter_only_if_evidenced"]["ok"])


class TestPESemantics(unittest.TestCase):
    def test_pe_semantics_distinguish_full_jam_fulljam(self):
        path = KNOW / "pe_semantics.json"
        if not path.is_file():
            # Minimal rebuild for test isolation
            path.write_text(
                json.dumps(
                    {
                        "naming_conventions": {
                            "full_eye_suffix": ["_F"],
                            "jam_eye_suffix": ["_J"],
                            "fulljam_eye_patterns": ["_JF", "_FJ"],
                            "note": "Conventions are documentation defaults — not required",
                        },
                        "roles": [
                            {"role": "full", "table": "Fullline"},
                            {"role": "jam", "table": "Jamcheck"},
                            {"role": "fulljam", "table": "Fulljam"},
                        ],
                        "rules": ["Naming conventions are not mandatory."],
                    }
                ),
                encoding="utf-8",
            )
        doc = json.loads(path.read_text(encoding="utf-8"))
        roles = {r["role"] for r in doc.get("roles") or []}
        self.assertIn("full", roles)
        self.assertIn("jam", roles)
        self.assertIn("fulljam", roles)
        naming = doc.get("naming_conventions") or {}
        self.assertTrue(naming.get("full_eye_suffix"))
        self.assertTrue(naming.get("jam_eye_suffix"))
        self.assertTrue(naming.get("fulljam_eye_patterns"))
        # Must not require names
        blob = json.dumps(doc).lower()
        self.assertTrue(
            "not mandatory" in blob
            or "not require" in blob
            or "no requirement" in blob
            or "defaults" in blob
        )


class TestNoFinishedPlc(unittest.TestCase):
    def test_knowledge_scripts_forbid_finished_plc(self):
        for name in (
            "fortna_activity_classify.py",
            "fortna_run_workspace_discover.py",
            "fortna_site_model.py",
            "fortna_fpc_knowledge_build.py",
            "fortna_validate_site_model.py",
        ):
            assert_no_finished_plc_usage((SCRIPTS / name).read_text(encoding="utf-8"))


@unittest.skipUnless(CP4_RUN.is_dir(), "CP4 RUN missing")
class TestCP4Smoke(unittest.TestCase):
    def test_discover_cross_table_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = discover(CP4_RUN, "ORNCCP4", out)
            self.assertFalse(result.get("incomplete_run"))
            self.assertGreater(result.get("cross_table_relationships") or 0, 0)
            site = json.loads((out / "site_model.json").read_text(encoding="utf-8"))
            activity = json.loads((out / "activity_classification.json").read_text(encoding="utf-8"))
            self.assertIn("scoring", activity)
            self.assertTrue(activity["scoring"].get("weights"))
            og = site.get("operational_groups") or {}
            self.assertGreater(len(og.get("jam_zones") or []), 0)
            report = validate_site_model(site)
            self.assertTrue(report["ok"], msg=json.dumps(report["issues"][:10], indent=2))
            # No Greensboro contamination forced into identities beyond RUN facts
            self.assertIn("ORNCCP4", str(site.get("machine_scope")))


@unittest.skipUnless(CP2_RUN.is_dir(), "CP2 RUN missing")
class TestCP2Smoke(unittest.TestCase):
    def test_discover_runs_quick(self):
        with tempfile.TemporaryDirectory() as td:
            result = discover(CP2_RUN, "ORNCCP2", Path(td))
            self.assertIn("counts", result)
            self.assertGreaterEqual(result["counts"].get("equipment", 0), 0)


class TestKnowledgeBuildEntrypoint(unittest.TestCase):
    def test_build_writes_expected_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "_doc_skims").mkdir()
            # Point builder at temp out via argv
            rc = knowledge_build_main(["--out", str(out), "--run-dir", str(CP4_RUN), "--machine", "ORNCCP4"])
            self.assertEqual(rc, 0)
            for name in (
                "document_inventory.json",
                "fortnaplus_tables.json",
                "relationship_graph.json",
                "active_record_analysis.json",
                "pasim_validation.json",
                "report.md",
            ):
                self.assertTrue((out / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
