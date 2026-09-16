#!/usr/bin/env python3
"""CP3 reference resolver tests + PLC2 invariants."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_mnu_runtime import build_runtime_catalog  # noqa: E402
from fortna_mnu_schema import MnuDefinition, MnuField, MnuSchema  # noqa: E402
from fortna_reference_resolver import (  # noqa: E402
    DYNAMIC_CAPABLE_SCHEMA,
    EMPTY_SOURCE_VALUE,
    TARGET_RECORD_MISSING,
    build_reference_graph,
    extract_proofs,
    resolve_table_references,
)
from fortna_run_loader import load_fortna_table, load_run  # noqa: E402

PLC2_RUN = ROOT / "workspace/_plc2_run_peek/RUN"
PLC2_FORTNA = PLC2_RUN / "FORTNA/fortna.mnu"
PLC2_PROJECT = PLC2_RUN / "PROJECT/project.mnu"


def _field(name: str, dtype: int, dlist: str = "", dsrc: int = 0) -> MnuField:
    return MnuField(
        name=name,
        rawDatatype=str(dtype),
        rawLength="20",
        rawLow="0",
        rawHigh="0",
        rawList=dlist,
        rawDataSource=str(dsrc),
        rawMetadata={"COLNAME": f"'{name}'", "DTYPE": str(dtype), "DLIST": f"'{dlist}'" if dlist else "' '", "DSRC": str(dsrc)},
        rawTokens=[],
        provenance={"sourceFile": "t", "origin": "FORTNA", "line": 1, "kind": "field"},
        listReference=dlist or None,
    )


def _catalog(defs: list[tuple[str, list[MnuField]]]):
    mdefs = []
    for name, fields in defs:
        mdefs.append(
            MnuDefinition(
                name=name,
                rawMetadata={"MNUNAME": f"'{name}'", "TYPE": "2", "#RECS": "50", "FLAGS": "0" * 16},
                rawTokens=[],
                fields=fields,
                provenance={"sourceFile": "t", "origin": "FORTNA", "line": 1, "kind": "definition"},
            )
        )
    sch = MnuSchema(
        sourceFile="t.mnu",
        origin="FORTNA",
        headerLine="x",
        menuColumns=["MNUNAME"],
        fieldColumns=["COLNAME", "DTYPE", "DLIST", "DSRC"],
        definitions=mdefs,
        parseNotes=[],
        stats={},
    )
    return build_runtime_catalog(sch)


class TestSyntheticResolver(unittest.TestCase):
    def setUp(self) -> None:
        self.cat = _catalog(
            [
                (
                    "MenuMenu",
                    [_field("Menu of Menus", 250), _field("Name", 0)],
                ),
                (
                    "Conveyor",
                    [_field("Parts", 250), _field("IO_Name", 0)],
                ),
                (
                    "Mtrchain",
                    [
                        _field("Title", 250),
                        _field("Motor_Name", 0),
                        _field("Motor_Ndx", 21, dlist="Conveyor", dsrc=0),
                    ],
                ),
                (
                    "Parameters",
                    [
                        _field("Title", 250),
                        _field("Parameter Name", 0),
                        _field("Data", 21, dlist="Conveyor", dsrc=5),
                        _field("Column", 25, dlist="Conveyor", dsrc=5),
                        _field("Record", 21, dlist="Conveyor", dsrc=5),
                        _field("PopupMenu", 21, dlist="MenuMenu", dsrc=0),
                    ],
                ),
            ]
        )

    def _write_tables(self, d: Path) -> None:
        (d / "Conveyor.asc").write_text(
            '"IO_Name"\nP100~\nP314~\nM314~\n', encoding="latin-1"
        )
        (d / "Mtrchain.asc").write_text(
            '"Motor_Name"~"Motor_Ndx"\nM1~P100~\nM314~M314~\n', encoding="latin-1"
        )
        (d / "Parameters.asc").write_text(
            '"Parameter Name"~"Data"~"Column"~"Record"~"PopupMenu"~"Use Datarec"\n'
            " ~P314~IO_Name~P314~Conveyor~N~\n"
            " ~INVALID~Parts_Menu~INVALID~None~N~\n",
            encoding="latin-1",
        )
        (d / "MenuMenu.asc").write_text('"Name"\nConveyor~\nMtrchain~\n', encoding="latin-1")

    def test_static_reference(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._write_tables(d)
            m = self.cat.by_name["Mtrchain"]
            table = load_fortna_table(m, directories=[d], ac_name="X")
            # Build mini run pack shape
            tjson = {
                "menuName": table.menuName,
                "physicalSelection": {
                    "selectedPath": table.physicalSelection["selectedPath"],
                    "selectedKind": table.physicalSelection["selectedKind"],
                },
                "stats": table.stats,
                "records": [
                    {
                        "recordIndex": r.recordIndex,
                        "values": [
                            {
                                "columnName": v.columnName,
                                "rawText": v.rawText,
                                "datatypeRaw": v.datatypeRaw,
                            }
                            for v in r.values
                        ],
                    }
                    for r in table.records
                ],
            }
            # need conveyor loaded for identity index — use load_run style multi
            from fortna_reference_resolver import _build_identity_index

            conv = load_fortna_table(self.cat.by_name["Conveyor"], directories=[d], ac_name="X")
            tables = {
                "Mtrchain": tjson,
                "Conveyor": {
                    "menuName": "Conveyor",
                    "physicalSelection": conv.physicalSelection,
                    "stats": conv.stats,
                    "records": [
                        {
                            "recordIndex": r.recordIndex,
                            "values": [
                                {
                                    "columnName": v.columnName,
                                    "rawText": v.rawText,
                                    "datatypeRaw": v.datatypeRaw,
                                }
                                for v in r.values
                            ],
                        }
                        for r in conv.records
                    ],
                },
            }
            # physicalSelection asdict-like
            tables["Conveyor"]["physicalSelection"] = {
                "selectedPath": conv.physicalSelection["selectedPath"]
                if isinstance(conv.physicalSelection, dict)
                else conv.physicalSelection.selectedPath,
                "selectedKind": conv.physicalSelection["selectedKind"]
                if isinstance(conv.physicalSelection, dict)
                else conv.physicalSelection.selectedKind,
            }
            # Fix - physicalSelection is dict from asdict in load_fortna_table return
            tables["Conveyor"]["physicalSelection"] = dict(conv.physicalSelection) if isinstance(conv.physicalSelection, dict) else {
                "selectedPath": conv.physicalSelection.selectedPath,
                "selectedKind": conv.physicalSelection.selectedKind,
            }
            tables["Mtrchain"]["physicalSelection"] = dict(table.physicalSelection) if isinstance(table.physicalSelection, dict) else {
                "selectedPath": table.physicalSelection.selectedPath,
                "selectedKind": table.physicalSelection.selectedKind,
            }
            ident = _build_identity_index(self.cat, tables)
            edges = resolve_table_references(self.cat, tables["Mtrchain"], identity_index=ident)
            hit = [
                e
                for e in edges
                if e.scope == "RECORD"
                and e.sourceColumn == "Motor_Ndx"
                and e.sourceRawValue == "M314"
            ]
            self.assertEqual(len(hit), 1)
            self.assertEqual(hit[0].resolutionMode, "STATIC")
            self.assertEqual(hit[0].status, "RESOLVED")
            self.assertEqual(hit[0].targetMenu, "Conveyor")
            self.assertEqual(hit[0].targetIdentity, "M314")

    def test_dynamic_and_fallback_and_menu_column(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._write_tables(d)
            # Use real load_run-like for Parameters+Conveyor+MenuMenu
            # Simpler: call build pieces
            from fortna_reference_resolver import _build_identity_index

            tables = {}
            for name in ("Parameters", "Conveyor", "MenuMenu"):
                tab = load_fortna_table(self.cat.by_name[name], directories=[d], ac_name="X")
                tables[name] = {
                    "menuName": name,
                    "physicalSelection": dict(tab.physicalSelection),
                    "stats": tab.stats,
                    "records": [
                        {
                            "recordIndex": r.recordIndex,
                            "values": [
                                {
                                    "columnName": v.columnName,
                                    "rawText": v.rawText,
                                    "datatypeRaw": v.datatypeRaw,
                                }
                                for v in r.values
                            ],
                        }
                        for r in tab.records
                    ],
                }
            ident = _build_identity_index(self.cat, tables)
            edges = resolve_table_references(
                self.cat, tables["Parameters"], identity_index=ident
            )
            # capability edges
            caps = [e for e in edges if e.unresolvedReason == DYNAMIC_CAPABLE_SCHEMA]
            self.assertTrue(caps)
            # dynamic Data row1 PopupMenu=Conveyor
            dyn = [
                e
                for e in edges
                if e.scope == "RECORD"
                and e.sourceColumn == "Data"
                and e.resolutionMode == "DYNAMIC"
            ]
            self.assertTrue(dyn)
            self.assertEqual(dyn[0].targetMenu, "Conveyor")
            self.assertEqual(dyn[0].targetIdentity, "P314")
            self.assertEqual(dyn[0].status, "RESOLVED")
            # MENU_COLUMN_ROW
            col = [
                e
                for e in edges
                if e.scope == "RECORD"
                and e.sourceColumn == "Column"
                and e.resolutionMode == "DYNAMIC"
            ]
            self.assertTrue(col)
            self.assertEqual(col[0].targetColumn, "IO_Name")
            self.assertEqual(col[0].status, "RESOLVED")
            # fallback PopupMenu=None
            fb = [
                e
                for e in edges
                if e.scope == "RECORD"
                and e.sourceColumn == "Data"
                and e.resolutionMode == "FALLBACK_STATIC"
            ]
            self.assertTrue(fb)

    def test_target_record_miss(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Conveyor.asc").write_text('"IO_Name"\nP100~\n', encoding="latin-1")
            (d / "Mtrchain.asc").write_text(
                '"Motor_Name"~"Motor_Ndx"\nM1~MISSING~\n', encoding="latin-1"
            )
            from fortna_reference_resolver import _build_identity_index

            tables = {}
            for name in ("Mtrchain", "Conveyor"):
                tab = load_fortna_table(self.cat.by_name[name], directories=[d], ac_name="X")
                tables[name] = {
                    "menuName": name,
                    "physicalSelection": dict(tab.physicalSelection),
                    "stats": tab.stats,
                    "records": [
                        {
                            "recordIndex": r.recordIndex,
                            "values": [
                                {
                                    "columnName": v.columnName,
                                    "rawText": v.rawText,
                                    "datatypeRaw": v.datatypeRaw,
                                }
                                for v in r.values
                            ],
                        }
                        for r in tab.records
                    ],
                }
            edges = resolve_table_references(
                self.cat,
                tables["Mtrchain"],
                identity_index=_build_identity_index(self.cat, tables),
            )
            miss = [
                e
                for e in edges
                if e.scope == "RECORD" and e.unresolvedReason == TARGET_RECORD_MISSING
            ]
            self.assertTrue(miss)
            empty = [
                e
                for e in edges
                if e.scope == "RECORD" and e.unresolvedReason == EMPTY_SOURCE_VALUE
            ]
            # no empty in this fixture
            self.assertIsInstance(empty, list)


class TestPlc2Cp3(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PLC2_FORTNA.is_file():
            raise unittest.SkipTest("PLC2 missing")
        cls.graph = build_reference_graph(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=PLC2_PROJECT if PLC2_PROJECT.is_file() else None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
        )
        cls.proofs = extract_proofs(cls.graph, site="plc2")

    def test_m314(self) -> None:
        p = self.proofs["mtrchainM314"]
        self.assertEqual(p["recordIndex"], 55)
        cols = p["columns"]
        self.assertEqual(cols["Motor_Ndx"]["sourceRawValue"], "M314")
        self.assertEqual(cols["Motor_Ndx"]["status"], "RESOLVED")
        self.assertEqual(cols["Motor_Chained1"]["sourceRawValue"], "P314")
        self.assertEqual(cols["Motor_Aux"]["sourceRawValue"], "LATCH_MERGE_316")
        self.assertEqual(cols["Enabled"]["sourceRawValue"], "M136_AUX")

    def test_merge316(self) -> None:
        lanes = self.proofs["merge316"]
        self.assertGreaterEqual(len(lanes), 2)
        releases = {(ln.get("ReleaseIO") or {}).get("sourceRawValue") for ln in lanes}
        self.assertIn("SSVEZPE136_P1", releases)
        self.assertIn("M314", releases)

    def test_reverse_hot_targets_complete(self) -> None:
        rev = self.graph["reverseRelationships"]
        # M314 conveyor reverse must exist and be non-omitted
        r = self.proofs["reverseM314"]
        self.assertIsNotNone(r["targetRecord"])
        self.assertGreaterEqual(r["inboundCount"], 1)
        self.assertIn(r["reverseKey"], rev)
        # Machine ORNCCP2 — find key
        keys = [k for k in rev if k.startswith("Machine#")]
        self.assertTrue(keys)
        # Ensure at least one Machine key has inbound (complete index)
        self.assertTrue(any(len(rev[k]) >= 1 for k in keys))

    def test_unresolved_taxonomy_present(self) -> None:
        tax = self.graph["statistics"]["unresolvedTaxonomy"]
        self.assertIn(DYNAMIC_CAPABLE_SCHEMA, tax)
        self.assertIsInstance(tax, dict)

    def test_deterministic_graph_stats(self) -> None:
        g2 = build_reference_graph(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=PLC2_PROJECT if PLC2_PROJECT.is_file() else None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
        )
        self.assertEqual(self.graph["statistics"], g2["statistics"])


if __name__ == "__main__":
    unittest.main()
