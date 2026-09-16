#!/usr/bin/env python3
"""Tests for Fortna .mnu runtime archaeology (find_data_source semantics)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_mnu_runtime import (  # noqa: E402
    SELECTION_UNIQUE,
    STRING,
    build_relationship_graph,
    build_runtime_catalog,
    find_data_source,
)
from fortna_mnu_schema import MnuDefinition, MnuField, MnuSchema, resolve_asc_path  # noqa: E402


def _field(
    name: str,
    *,
    dtype: int,
    dlist: str = "",
    dsrc: int = 0,
    line: int = 1,
) -> MnuField:
    return MnuField(
        name=name,
        rawDatatype=str(dtype),
        rawLength="10",
        rawLow="0",
        rawHigh="0",
        rawList=dlist,
        rawDataSource=str(dsrc),
        rawMetadata={
            "COLNAME": f"'{name}'",
            "DTYPE": str(dtype),
            "DLEN": "10",
            "DLOW": "0",
            "DHIGH": "0",
            "DLIST": f"'{dlist}'" if dlist else "' '",
            "DSRC": str(dsrc),
        },
        rawTokens=[],
        provenance={"sourceFile": "synthetic", "origin": "FORTNA", "line": line, "kind": "field"},
        listReference=dlist or None,
    )


def _def(name: str, fields: list[MnuField], *, arrays: int = 10) -> MnuDefinition:
    return MnuDefinition(
        name=name,
        rawMetadata={
            "MNUNAME": f"'{name}'",
            "TYPE": "2",
            "#RECS": str(arrays),
            "FLAGS": "0000000000000000",
        },
        rawTokens=[],
        fields=fields,
        provenance={"sourceFile": "synthetic", "origin": "FORTNA", "line": 1, "kind": "definition"},
    )


def _schema(defs: list[MnuDefinition]) -> MnuSchema:
    return MnuSchema(
        sourceFile="synthetic.mnu",
        origin="FORTNA",
        headerLine="MNUNAME *** COLNAME",
        menuColumns=["MNUNAME", "TYPE", "#RECS", "FLAGS"],
        fieldColumns=["COLNAME", "DTYPE", "DLEN", "DLOW", "DHIGH", "DLIST", "DSRC"],
        definitions=defs,
        parseNotes=[],
        stats={"definitions": len(defs), "fields": sum(len(d.fields) for d in defs)},
    )


class TestFindDataSource(unittest.TestCase):
    def setUp(self) -> None:
        # Menus: None(0) unused conceptually, MenuMenu, Conveyor, Parameters(dynamic), Mtrchain(static)
        # Indices assigned in definition order.
        self.menu_menu = _def(
            "MenuMenu",
            [
                _field("Menu of Menus", dtype=250),
                _field("Name", dtype=STRING),
            ],
        )
        self.conveyor = _def(
            "Conveyor",
            [
                _field("Parts_Menu", dtype=250),
                _field("IO_Name", dtype=STRING),
            ],
        )
        self.mtrchain = _def(
            "Mtrchain",
            [
                _field("Motor_Chains", dtype=250),
                _field("Motor_Name", dtype=STRING),
                _field("Motor_Ndx", dtype=SELECTION_UNIQUE, dlist="Conveyor", dsrc=0),
            ],
        )
        # Parameters: Data(col2) dynamic via PopupMenu(col5) → MenuMenu
        self.parameters = _def(
            "Parameters",
            [
                _field("Parameters", dtype=250),
                _field("Parameter Name", dtype=STRING),
                _field("Data", dtype=SELECTION_UNIQUE, dlist="Conveyor", dsrc=5),
                _field("Column", dtype=25, dlist="Conveyor", dsrc=5),
                _field("Record", dtype=SELECTION_UNIQUE, dlist="Conveyor", dsrc=5),
                _field("PopupMenu", dtype=SELECTION_UNIQUE, dlist="MenuMenu", dsrc=0),
            ],
        )
        self.catalog = build_runtime_catalog(
            _schema([self.menu_menu, self.conveyor, self.mtrchain, self.parameters])
        )

    def test_A_static_selection(self) -> None:
        m = self.catalog.by_name["Mtrchain"]
        col = next(c for c in m.columns if c.name == "Motor_Ndx")
        res = find_data_source(self.catalog, m, col.index)
        self.assertEqual(res["resolutionMode"], "STATIC")
        self.assertEqual(res["targetMenu"], "Conveyor")

    def test_B_dynamic_selection(self) -> None:
        m = self.catalog.by_name["Parameters"]
        col = next(c for c in m.columns if c.name == "Data")
        # PopupMenu record value = Conveyor menu index
        conv_idx = self.catalog.by_name["Conveyor"].index
        res = find_data_source(
            self.catalog, m, col.index, datasource_record_value=conv_idx
        )
        self.assertEqual(res["resolutionMode"], "DYNAMIC")
        self.assertEqual(res["targetMenu"], "Conveyor")
        self.assertEqual(res["targetMenuIndex"], conv_idx)

    def test_C_dynamic_fallback(self) -> None:
        m = self.catalog.by_name["Parameters"]
        col = next(c for c in m.columns if c.name == "Data")
        res = find_data_source(self.catalog, m, col.index, datasource_record_value=0)
        self.assertEqual(res["resolutionMode"], "STATIC")
        self.assertEqual(res["reason"], "dynamic_fallback_datasource_value_le_0")
        self.assertEqual(res["targetMenu"], "Conveyor")

    def test_D_invalid_datasource(self) -> None:
        # Force invalid datasource index beyond mnuitems
        bad = _def(
            "BadDyn",
            [
                _field("Title", dtype=250),
                _field("Name", dtype=STRING),
                _field("Ref", dtype=SELECTION_UNIQUE, dlist="Conveyor", dsrc=99),
            ],
        )
        cat = build_runtime_catalog(_schema([self.menu_menu, self.conveyor, bad]))
        m = cat.by_name["BadDyn"]
        col = next(c for c in m.columns if c.name == "Ref")
        res = find_data_source(cat, m, col.index, datasource_record_value=1)
        self.assertEqual(res["resolutionMode"], "UNRESOLVED")
        self.assertEqual(res["reason"], "invalid_datasource_column")

    def test_E_unresolved_target_record_preserved(self) -> None:
        # Schema says Conveyor, ASC value does not exist in Conveyor name index
        tables = {
            "Mtrchain": {
                "menu": "Mtrchain",
                "menuIndex": self.catalog.by_name["Mtrchain"].index,
                "origin": "FORTNA",
                "physicalFile": "synthetic",
                "chosenKind": "GENERIC",
                "columns": ["Motor_Chains", "Motor_Name", "Motor_Ndx"],
                "recordCount": 1,
                "records": [
                    {
                        "Motor_Chains": "",
                        "Motor_Name": "M1",
                        "Motor_Ndx": "DOES_NOT_EXIST",
                        "_recordIndex": 1,
                    }
                ],
            },
            "Conveyor": {
                "menu": "Conveyor",
                "menuIndex": self.catalog.by_name["Conveyor"].index,
                "origin": "FORTNA",
                "physicalFile": "synthetic",
                "chosenKind": "GENERIC",
                "columns": ["Parts_Menu", "IO_Name"],
                "recordCount": 1,
                "records": [
                    {"Parts_Menu": "", "IO_Name": "P100", "_recordIndex": 1}
                ],
            },
        }
        graph = build_relationship_graph(self.catalog, tables, max_records_per_table=50)
        unresolved_recs = [
            d for d in graph["diagnostics"] if d["kind"] == "UNRESOLVED_TARGET_RECORD"
        ]
        self.assertTrue(unresolved_recs)
        edges = [
            e
            for e in graph["relationships"]
            if e.get("scope") == "RECORD"
            and e["sourceMenu"] == "Mtrchain"
            and e["sourceColumn"] == "Motor_Ndx"
        ]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["targetMenu"], "Conveyor")
        self.assertIsNone(edges[0]["targetRecord"])
        self.assertEqual(edges[0]["targetName"], "DOES_NOT_EXIST")

    def test_dynamic_without_record_is_unresolved_not_guessed(self) -> None:
        m = self.catalog.by_name["Parameters"]
        col = next(c for c in m.columns if c.name == "Data")
        res = find_data_source(self.catalog, m, col.index, datasource_record_value=None)
        self.assertEqual(res["resolutionMode"], "UNRESOLVED")
        self.assertIn("dynamic", res["reason"])

    def test_machine_specific_asc_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Conveyor.asc").write_text("generic\n", encoding="utf-8")
            (d / "Conveyor.asc.ORNCCP2").write_text("machine\n", encoding="utf-8")
            hit = resolve_asc_path("Conveyor", directory=d, ac_name="ORNCCP2")
            self.assertEqual(hit["chosenKind"], "MACHINE_SPECIFIC")


class TestCorpusSmoke(unittest.TestCase):
    def test_plc2_catalog_builds(self) -> None:
        fortna = ROOT / "workspace/_plc2_run_peek/RUN/FORTNA/fortna.mnu"
        project = ROOT / "workspace/_plc2_run_peek/RUN/PROJECT/project.mnu"
        if not fortna.is_file():
            self.skipTest("plc2 fortna.mnu missing")
        from fortna_mnu_schema import parse_mnu_file

        schemas = [parse_mnu_file(fortna, origin="FORTNA")]
        if project.is_file():
            schemas.append(parse_mnu_file(project, origin="PROJECT"))
        cat = build_runtime_catalog(*schemas)
        self.assertIn("Conveyor", cat.by_name)
        self.assertIn("Mtrchain", cat.by_name)
        self.assertIsNotNone(cat.menu_menu_index)
        # Parameters.Data should be dynamic-capable against MenuMenu
        params = cat.by_name.get("Parameters")
        if params:
            data = next(c for c in params.columns if c.name == "Data")
            self.assertTrue(_is_dyn(cat, params, data))


def _is_dyn(cat, menu, col):
    from fortna_mnu_runtime import _is_dynamic_capable

    return _is_dynamic_capable(cat, menu, col)


if __name__ == "__main__":
    unittest.main()
