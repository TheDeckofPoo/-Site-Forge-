#!/usr/bin/env python3
"""Tests for the knowledge-driven compiler pass (SiteModel V2 enrichment).

Prefers synthetic fixtures. Live RUN paths are skip-if-missing only.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import json
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
# Shared fixtures live under tests/decoder/ after cleanup relocation
_FIXTURES = ROOT / "tests" / "decoder"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from fortna_activity_classify import classify_object, classify_site_model  # noqa: E402
from fortna_area_ops import rename_area  # noqa: E402
from fortna_knowledge import (  # noqa: E402
    KnowledgeStore,
    classify_pe_roles,
    document_metrics,
    make_decision_trace,
    table_semantics,
)
from fortna_knowledge_enrich import (  # noqa: E402
    build_motor_chains,
    build_sawtooth_editor_v2,
    build_sorter_editor_v2,
    enrich_pe_roles,
    enrich_site_model,
)
from fortna_site_model import (  # noqa: E402
    EXCLUDED,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    HISTORICAL_OR_STALE,
    INCLUDED,
    PROV_RUN_EXPLICIT,
    SCOPE_HISTORICAL,
    SiteModel,
    make_object,
    make_relationship,
)
from fortna_validate_site_model import (  # noqa: E402
    GENERATION_BLOCKED,
    WARNING,
    validate_site_model,
)
from test_blind_genericity_fixtures import (  # noqa: E402
    FORBIDDEN_SITE_LEAKS,
    MERGE_SITE,
    SAWTOOTH_SITE,
    SORTER_SITE,
    TRANSPORT_SITE,
)

CP2_RUN = ROOT / "workspace" / "active" / "RUN"
CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"


class TestPeJamAssignment(unittest.TestCase):
    def test_classify_and_enrich_marks_jam_from_jamcheck(self) -> None:
        roles = classify_pe_roles("PE9001_J", jamcheck=True)
        jam = next((r for r in roles if r["role"] == "JAM"), None)
        self.assertIsNotNone(jam, msg=roles)
        assert jam is not None
        self.assertEqual(jam["confidence"], "HIGH")

        site = TRANSPORT_SITE()
        metrics = enrich_pe_roles(site)
        pe = next(p for p in site["photoeyes"] if p["raw_name"] == "PE9001_J")
        self.assertIn("JAM", pe.get("pe_roles") or [])
        self.assertEqual(pe.get("role"), "jam")
        self.assertGreaterEqual(metrics.get("auto_resolved", 0), 1)


class TestFullClearingAndFullJam(unittest.TestCase):
    def test_full_and_fulljam_escalation_roles(self) -> None:
        full_roles = classify_pe_roles("PE9001_F", fullline=True)
        self.assertTrue(any(r["role"] == "FULL" and r["confidence"] == "HIGH" for r in full_roles))

        fj_roles = classify_pe_roles("PE9002_JF", fulljam=True)
        self.assertTrue(
            any(r["role"] == "FULL_JAM" and r["confidence"] == "HIGH" for r in fj_roles)
        )

        # FullJam is the escalation role (distinct from plain FULL).
        both = classify_pe_roles("PE9002_JF", fullline=True, fulljam=True)
        role_names = {r["role"] for r in both}
        self.assertIn("FULL", role_names)
        self.assertIn("FULL_JAM", role_names)

        site = TRANSPORT_SITE()
        enrich_pe_roles(site)
        pe_f = next(p for p in site["photoeyes"] if p["raw_name"] == "PE9001_F")
        pe_jf = next(p for p in site["photoeyes"] if p["raw_name"] == "PE9002_JF")
        self.assertIn("FULL", pe_f.get("pe_roles") or [])
        self.assertIn("FULL_JAM", pe_jf.get("pe_roles") or [])


class TestMotorChainOrdering(unittest.TestCase):
    def test_order_from_relationships(self) -> None:
        site = TRANSPORT_SITE()
        chains = build_motor_chains(site)
        self.assertTrue(chains)
        head = next(c for c in chains if c.get("normalized_name") == "M9001")
        self.assertEqual(head["order"][0], "M9001")
        self.assertIn("M9002", head["order"])
        self.assertEqual(site["motor_chains"], chains)


class TestAreaRenameLeavesZones(unittest.TestCase):
    def test_area_rename_does_not_rename_jam_zones(self) -> None:
        site = TRANSPORT_SITE()
        model = SiteModel(machine_scope=site["machine_scope"], run_dir=site["run_dir"])
        model.areas = list(site["areas"])
        model.equipment = list(site["equipment"])
        model.operational_groups = dict(site["operational_groups"])
        model.estop_zones = list(site["estop_zones"])

        jam_before = model.operational_groups["jam_zones"][0]["raw_name"]
        ss_before = model.operational_groups["startstop_zones"][0]["raw_name"]
        es_before = model.estop_zones[0]["raw_name"]

        rename_area(model, "Alpha_Area", "Shipping_Alpha")
        self.assertEqual(model.areas[0]["raw_name"], "Shipping_Alpha")
        self.assertEqual(model.operational_groups["jam_zones"][0]["raw_name"], jam_before)
        self.assertEqual(model.operational_groups["startstop_zones"][0]["raw_name"], ss_before)
        self.assertEqual(model.estop_zones[0]["raw_name"], es_before)


class TestEstopStartStopIndependent(unittest.TestCase):
    def test_estop_and_startstop_independent_of_area_rename(self) -> None:
        site = TRANSPORT_SITE()
        model = SiteModel(machine_scope=site["machine_scope"], run_dir=site["run_dir"])
        model.areas = list(site["areas"])
        model.equipment = list(site["equipment"])
        model.operational_groups = dict(site["operational_groups"])
        model.estop_zones = list(site["estop_zones"])
        # Assign equipment to zones independently of area.
        for eq in model.equipment:
            if eq.get("inclusion") == INCLUDED:
                eq["es_zone_id"] = "Alpha_ES1"
                eq["startstop_zone_id"] = "Alpha_SS1"
                eq["jam_zone_id"] = "Alpha_Jam1"

        rename_area(model, "Alpha_Area", "Pack_Area_X")
        for eq in model.equipment:
            if eq.get("inclusion") != INCLUDED:
                continue
            self.assertEqual(eq.get("es_zone_id"), "Alpha_ES1")
            self.assertEqual(eq.get("startstop_zone_id"), "Alpha_SS1")
            self.assertEqual(eq.get("jam_zone_id"), "Alpha_Jam1")
            self.assertEqual(eq.get("area_id"), "Pack_Area_X")


class TestSawtoothReservationUnknown(unittest.TestCase):
    def test_reservation_fields_stay_configuration_required(self) -> None:
        site = SAWTOOTH_SITE()
        editor = build_sawtooth_editor_v2(site)
        self.assertTrue(editor.get("detected"))
        self.assertEqual(editor["capability_matrix"]["reservation_semantics"], "MODELED")
        for merge in editor.get("merges") or []:
            for lane in merge.get("lanes") or []:
                cfg = lane.get("configuration_required") or []
                self.assertIn("reservation mode", cfg)
                self.assertIn("reserve eye", cfg)
                # Must not invent a gold reservation value.
                self.assertFalse(lane.get("reservation_mode"))
                self.assertFalse(lane.get("reserve_eye"))


class TestSorterScanZoneWcsLeaves(unittest.TestCase):
    def test_generation_leaves_not_supported_or_config_required(self) -> None:
        site = SORTER_SITE()
        editor = build_sorter_editor_v2(site)
        leaves = editor.get("generation_leaves") or {}
        self.assertIn(
            leaves.get("scan_zone_configuration"),
            {"MODELED", "DISCOVERED", "CONFIGURATION_REQUIRED", "NOT_SUPPORTED"},
        )
        self.assertIn(
            leaves.get("wcs_message_config_tags"),
            {"GENERATION_NOT_SUPPORTED", "NOT_SUPPORTED", "CONFIGURATION_REQUIRED"},
        )
        self.assertIn(
            leaves.get("divert_aoi_instances"),
            {"GENERATION_NOT_SUPPORTED", "NOT_SUPPORTED"},
        )
        self.assertIn(
            leaves.get("transfer_tracking_support"),
            {"GENERATION_NOT_SUPPORTED", "NOT_SUPPORTED"},
        )
        note = str(editor.get("note") or "")
        # Note may mention Sorter_Track only to forbid cloning gold packs.
        self.assertTrue(
            "no sorter_track clone" in note.lower() or "proven leaves" in note.lower(),
            msg=note,
        )
        leaves_blob = json.dumps(leaves)
        self.assertNotRegex(leaves_blob, r'(?i)"generatable".*sorter_track|sorter_track.*"generatable"')


class TestStaleEquipmentExclusion(unittest.TestCase):
    def test_historical_or_stale_not_included_after_classify(self) -> None:
        site = TRANSPORT_SITE()
        # Seed stale equipment that mistakenly looks INCLUDED before classify.
        stale = make_object(
            "equipment",
            "P8500_OLD",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            confidence="MEDIUM",
            source_scope=SCOPE_HISTORICAL,
            active_state_hint=HISTORICAL_OR_STALE,
            equipment_type="STRAIGHT",
        ).to_dict()
        site["equipment"].append(stale)

        classify_object(stale, machine=site["machine_scope"])
        self.assertEqual(stale["active_state"], HISTORICAL_OR_STALE)
        self.assertEqual(stale["inclusion"], EXCLUDED)

        classify_site_model(site, site["machine_scope"])
        enrich_site_model(site)
        for eq in site["equipment"]:
            if eq.get("active_state") == HISTORICAL_OR_STALE:
                self.assertNotEqual(eq.get("inclusion"), INCLUDED)


class TestBlindGenericity(unittest.TestCase):
    def test_enrichment_outputs_have_no_site_leaks(self) -> None:
        for builder in (TRANSPORT_SITE, MERGE_SITE, SAWTOOTH_SITE, SORTER_SITE):
            site = builder()
            enrich_site_model(site)
            blob = json.dumps(site, ensure_ascii=False)
            for leak in FORBIDDEN_SITE_LEAKS:
                self.assertNotIn(
                    leak,
                    blob,
                    msg=f"{builder.__name__} enrichment leaked {leak}",
                )
            # Suffix / stale / overlay / removed / late PE / motor-chain / FullJam present
            # without site-constant injection.
            if builder is TRANSPORT_SITE:
                roles = {
                    p["raw_name"]: p.get("pe_roles") for p in site["photoeyes"]
                }
                self.assertIn("JAM", roles.get("PE9001_J") or [])
                self.assertIn("FULL_JAM", roles.get("PE9002_JF") or [])
                self.assertTrue(site.get("motor_chains"))
                self.assertTrue(site.get("editors", {}).get("transport"))


class TestValidatorV2(unittest.TestCase):
    def test_duplicate_io_generation_blocked(self) -> None:
        site = TRANSPORT_SITE()
        site["photoeyes"][0]["io_address_word"] = "I:10"
        site["photoeyes"][0]["io_address_bit"] = "3"
        site["photoeyes"][0]["inclusion"] = INCLUDED
        site["photoeyes"][1]["io_address_word"] = "I:10"
        site["photoeyes"][1]["io_address_bit"] = "3"
        site["photoeyes"][1]["inclusion"] = INCLUDED
        report = validate_site_model(site)
        dup = [i for i in report["issues"] if i["kind"] == "duplicate_active_io"]
        self.assertTrue(dup)
        self.assertEqual(dup[0]["severity"], GENERATION_BLOCKED)

    def test_active_plus_superseded_warning(self) -> None:
        site = TRANSPORT_SITE()
        target = site["equipment"][0]
        target["inclusion"] = INCLUDED
        site["superseded_candidates"] = [
            {
                "normalized_name": target["normalized_name"],
                "state": "SUPERSEDED_CANDIDATE",
            }
        ]
        report = validate_site_model(site)
        hits = [i for i in report["issues"] if i["kind"] == "active_superseded_conflict"]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["severity"], WARNING)


class TestDocumentMetrics(unittest.TestCase):
    def test_metrics_integers_no_dash_ranges(self) -> None:
        metrics = document_metrics()
        self.assertIsInstance(metrics["total"], int)
        self.assertNotRegex(str(metrics["total"]), r"\d+\s*[–-]\s*\d+")
        for key, val in (metrics.get("by_classification") or {}).items():
            self.assertIsInstance(val, int, msg=key)
            self.assertNotRegex(str(val), r"\d+\s*[–-]\s*\d+")
        for key, val in (metrics.get("by_relevance") or {}).items():
            self.assertIsInstance(val, int, msg=key)
            self.assertNotRegex(str(val), r"\d+\s*[–-]\s*\d+")


class TestTableSemanticsJamcheck(unittest.TestCase):
    def test_jamcheck_table_semantics(self) -> None:
        jam = table_semantics("Jamcheck")
        self.assertIsNotNone(jam)
        assert jam is not None
        fields = {str(r.get("field")) for r in (jam.get("relationship_fields") or [])}
        self.assertIn("Sensor_Name", fields)
        store = KnowledgeStore()
        self.assertIsNotNone(store.table_semantics("Jamcheck"))


class TestDecisionTraces(unittest.TestCase):
    def test_traces_present_after_enrich_pe_roles(self) -> None:
        self.assertTrue(callable(make_decision_trace))
        site = TRANSPORT_SITE()
        enrich_pe_roles(site)
        traces = site.get("decision_traces") or []
        self.assertTrue(traces, msg="expected decision_traces after enrich_pe_roles")
        for t in traces:
            self.assertIn("decision", t)
            self.assertIn("knowledge_rule", t)
            self.assertIn("confidence", t)


@unittest.skipUnless(CP2_RUN.is_dir() or CP4_RUN.is_dir(), "live RUN missing")
class TestLiveRunOptional(unittest.TestCase):
    def test_enrich_live_site_model_if_present(self) -> None:
        path = ROOT / "exports" / "run-discovery" / "site_model.json"
        if not path.is_file():
            self.skipTest("exports/run-discovery/site_model.json missing")
        site = json.loads(path.read_text(encoding="utf-8"))
        enrich_site_model(site)
        self.assertIn("editors", site)
        self.assertIn("ui_status_summary", site)


if __name__ == "__main__":
    unittest.main()
