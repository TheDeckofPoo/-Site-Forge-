#!/usr/bin/env python3
"""Unit tests for the executable FortnaPlus knowledge API."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from fortna_knowledge import (  # noqa: E402
    KnowledgeStore,
    classify_pe_roles,
    document_metrics,
    make_decision_trace,
    table_semantics,
)


class TestTableSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore()

    def test_jamcheck_has_sensor_name_relationship(self) -> None:
        jam = self.store.table_semantics("Jamcheck")
        self.assertIsNotNone(jam)
        assert jam is not None
        fields = jam.get("relationship_fields") or []
        names = {str(r.get("field")) for r in fields}
        self.assertIn("Sensor_Name", names)

        # Module-level helper matches.
        jam2 = table_semantics("Jamcheck")
        self.assertIsNotNone(jam2)
        assert jam2 is not None
        names2 = {str(r.get("field")) for r in (jam2.get("relationship_fields") or [])}
        self.assertIn("Sensor_Name", names2)

    def test_subsystem_and_generation(self) -> None:
        self.assertEqual(self.store.subsystem_for_table("Jamcheck"), "area_safety")
        impl = self.store.generation_implications("Jamcheck")
        self.assertIsInstance(impl, list)
        self.assertTrue(impl)

    def test_resolve_reference(self) -> None:
        ref = self.store.resolve_reference("Jamcheck", "Sensor_Name", "PE218_J")
        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref["target_table"], "Conveyor")
        self.assertEqual(ref["edge_type"], "EXPLICIT_REFERENCE")


class TestClassifyPeRoles(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore()

    def test_jamcheck_table_evidence_high(self) -> None:
        roles = self.store.classify_pe_roles("PE218_J", jamcheck=True)
        jam = next((r for r in roles if r["role"] == "JAM"), None)
        self.assertIsNotNone(jam, msg=roles)
        assert jam is not None
        self.assertEqual(jam["confidence"], "HIGH")
        self.assertTrue(jam.get("evidence"))
        self.assertTrue(jam.get("knowledge_rule"))
        self.assertTrue(jam.get("document_source"))

        # Module helper
        roles2 = classify_pe_roles("PE218_J", jamcheck=True)
        self.assertTrue(any(r["role"] == "JAM" and r["confidence"] == "HIGH" for r in roles2))

    def test_fullline_table_evidence(self) -> None:
        roles = self.store.classify_pe_roles("EZPE116_F", fullline=True)
        full = next((r for r in roles if r["role"] == "FULL"), None)
        self.assertIsNotNone(full, msg=roles)
        assert full is not None
        self.assertIn(full["confidence"], {"HIGH", "MEDIUM"})
        self.assertEqual(full["role"], "FULL")

    def test_table_beats_suffix_only(self) -> None:
        # Suffix alone is supporting (not HIGH).
        suffix_only = self.store.classify_pe_roles("PE218_J")
        jam_suffix = next((r for r in suffix_only if r["role"] == "JAM"), None)
        self.assertIsNotNone(jam_suffix)
        assert jam_suffix is not None
        self.assertNotEqual(jam_suffix["confidence"], "HIGH")

        with_table = self.store.classify_pe_roles("PE218_J", jamcheck=True)
        jam_table = next((r for r in with_table if r["role"] == "JAM"), None)
        assert jam_table is not None
        self.assertEqual(jam_table["confidence"], "HIGH")

    def test_multiple_roles(self) -> None:
        roles = self.store.classify_pe_roles(
            "EZPE116_F",
            fullline=True,
            reserve=True,
        )
        role_names = {r["role"] for r in roles}
        self.assertIn("FULL", role_names)
        self.assertIn("RESERVE", role_names)


class TestNoGreensboroLiterals(unittest.TestCase):
    def test_no_greensboro_string_in_fortna_knowledge(self) -> None:
        src = (SCRIPTS / "fortna_knowledge.py").read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"greensboro", src, flags=re.I),
            msg="fortna_knowledge.py must not contain Greensboro string literals",
        )


class TestDocumentMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore()

    def test_metrics_are_integers_not_ranges(self) -> None:
        metrics = self.store.document_metrics()
        self.assertIsInstance(metrics["total"], int)
        self.assertNotIsInstance(metrics["total"], bool)
        self.assertNotRegex(str(metrics["total"]), r"\d+\s*[–-]\s*\d+")

        for key, val in metrics["by_classification"].items():
            self.assertIsInstance(val, int, msg=key)
            self.assertNotRegex(str(val), r"\d+\s*[–-]\s*\d+")

        for key, val in metrics["by_relevance"].items():
            self.assertIsInstance(val, int, msg=key)
            self.assertNotRegex(str(val), r"\d+\s*[–-]\s*\d+")

        deep = metrics["deep_review"]
        self.assertIsInstance(deep["true"], int)
        self.assertIsInstance(deep["false"], int)
        self.assertEqual(deep["true"] + deep["false"], metrics["total"])

        # Module helper
        m2 = document_metrics()
        self.assertIsInstance(m2["total"], int)

    def test_normalized_document_fields(self) -> None:
        metrics = self.store.document_metrics()
        self.assertGreater(metrics["total"], 0)
        for doc in metrics["documents"]:
            self.assertIn("document_id", doc)
            self.assertIn("canonical_path", doc)
            self.assertIn("classification", doc)
            self.assertIn("deep_review", doc)
            self.assertIsInstance(doc["deep_review"], bool)
            self.assertTrue(doc["document_id"])
            self.assertTrue(doc["canonical_path"])


class TestClassifyRowAndZones(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore()

    def test_classify_row_active_inactive(self) -> None:
        active = self.store.classify_row(
            "Jamcheck",
            {"Sensor_Name": "PE218_J", "Desc": "Jam", "Timer_Name": "tmJ218"},
        )
        self.assertEqual(active, "ACTIVE")
        inactive = self.store.classify_row(
            "Jamcheck",
            {"Sensor_Name": "", "Desc": "N/A"},
        )
        self.assertEqual(inactive, "INACTIVE")

    def test_zone_kinds_distinct(self) -> None:
        self.assertTrue(self.store.zone_kinds_are_distinct())
        kinds = {z["canonical_kind"] for z in self.store.zone_kinds()}
        for required in (
            "EngineeringArea",
            "StartStop",
            "EStop",
            "Jam",
            "Full",
            "SorterTracking",
        ):
            self.assertIn(required, kinds)
        self.assertEqual(
            self.store.zone_kind_for_table("Jamcheck"),
            "Jam",
        )
        self.assertEqual(
            self.store.zone_kind_for_table("Fullline"),
            "Full",
        )
        self.assertNotEqual(
            self.store.canonicalize_zone_kind("StartStop"),
            self.store.canonicalize_zone_kind("EStop"),
        )

    def test_decision_trace(self) -> None:
        trace = make_decision_trace(
            decision="INCLUDE",
            run_evidence=["jam_link"],
            knowledge_rule="Jamcheck.Sensor_Name",
            document_source="FPC-Fulls-Jams-Fulljams",
            confidence="HIGH",
        )
        self.assertEqual(trace["decision"], "INCLUDE")
        self.assertEqual(trace["confidence"], "HIGH")

    def test_source_firewall_no_l5x_reads(self) -> None:
        src = (SCRIPTS / "fortna_knowledge.py").read_text(encoding="utf-8")
        # Must not open finished PLC artifacts (docstring may mention the policy).
        self.assertIsNone(re.search(r'read_text\([^)]*\.l5x', src, flags=re.I))
        self.assertIsNone(re.search(r'Path\([^)]*\.l5x', src, flags=re.I))
        self.assertIsNone(re.search(r'open\([^)]*\.l5x', src, flags=re.I))


class TestMotorChain(unittest.TestCase):
    def test_motor_chain_optional(self) -> None:
        store = KnowledgeStore()
        model = store.motor_chain_model()
        # File is present in repo exports; fields should load.
        if (ROOT / "exports" / "fpc-knowledge" / "motor_chain_model.json").is_file():
            self.assertTrue(model.get("fields"))
            self.assertIsInstance(store.motor_chain_rules(), list)
            sample = store.motor_chain_sample("M116")
            if sample:
                self.assertEqual(store.chained_motors("M116"), sample.get("Motor_Chained") or [])


if __name__ == "__main__":
    unittest.main()
