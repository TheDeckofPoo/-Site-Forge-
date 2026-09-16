#!/usr/bin/env python3
"""CP2 tests — generic FortnaPlus RUN loader."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_mnu_runtime import RuntimeColumn, RuntimeMenu, build_runtime_catalog  # noqa: E402
from fortna_mnu_schema import MnuDefinition, MnuField, MnuSchema  # noqa: E402
from fortna_run_loader import (  # noqa: E402
    convert_value,
    load_fortna_table,
    load_run,
    resolve_physical_table_file,
    split_asc_row,
)

PLC2_RUN = ROOT / "workspace/_plc2_run_peek/RUN"
PLC2_FORTNA = PLC2_RUN / "FORTNA/fortna.mnu"
PLC2_PROJECT = PLC2_RUN / "PROJECT/project.mnu"


def _field(name: str, dtype: int, **kwargs) -> MnuField:
    return MnuField(
        name=name,
        rawDatatype=str(dtype),
        rawLength=str(kwargs.get("dlen", 20)),
        rawLow="0",
        rawHigh="0",
        rawList=kwargs.get("dlist", ""),
        rawDataSource=str(kwargs.get("dsrc", 0)),
        rawMetadata={"COLNAME": f"'{name}'", "DTYPE": str(dtype)},
        rawTokens=[],
        provenance={"sourceFile": "t", "origin": "FORTNA", "line": 1, "kind": "field"},
        listReference=kwargs.get("dlist") or None,
    )


def _menu(name: str, fields: list[MnuField]) -> RuntimeMenu:
    d = MnuDefinition(
        name=name,
        rawMetadata={"MNUNAME": f"'{name}'", "TYPE": "2", "#RECS": "100", "FLAGS": "0" * 16},
        rawTokens=[],
        fields=fields,
        provenance={"sourceFile": "t", "origin": "FORTNA", "line": 1, "kind": "definition"},
    )
    sch = MnuSchema(
        sourceFile="t.mnu",
        origin="FORTNA",
        headerLine="x",
        menuColumns=["MNUNAME"],
        fieldColumns=["COLNAME", "DTYPE"],
        definitions=[d],
        parseNotes=[],
        stats={},
    )
    cat = build_runtime_catalog(sch)
    return cat.by_name[name]


class TestFileSelection(unittest.TestCase):
    def test_generic_asc_selection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Widget.asc").write_text('"A"~"B"\n1~2\n', encoding="latin-1")
            sel = resolve_physical_table_file("Widget", directories=[d], ac_name="ORNCCP2")
            self.assertEqual(sel.selectedKind, "GENERIC_ASC")
            self.assertTrue(str(sel.selectedPath).endswith("Widget.asc"))

    def test_machine_specific_asc_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Widget.asc").write_text("generic\n", encoding="latin-1")
            (d / "Widget.asc.ORNCCP2").write_text("machine\n", encoding="latin-1")
            sel = resolve_physical_table_file("Widget", directories=[d], ac_name="ORNCCP2")
            self.assertEqual(sel.selectedKind, "MACHINE_SPECIFIC_ASC")
            self.assertTrue(str(sel.selectedPath).endswith("Widget.asc.ORNCCP2"))

    def test_missing_machine_specific_falls_back_to_generic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Widget.asc").write_text("generic\n", encoding="latin-1")
            sel = resolve_physical_table_file("Widget", directories=[d], ac_name="ORNCCP2")
            self.assertEqual(sel.selectedKind, "GENERIC_ASC")

    def test_rom_not_silently_bypassed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Widget.rom.ORNCCP2").write_bytes(b"\x00\x01rom")
            (d / "Widget.asc").write_text("asc\n", encoding="latin-1")
            sel = resolve_physical_table_file("Widget", directories=[d], ac_name="ORNCCP2")
            self.assertEqual(sel.selectedKind, "UNSUPPORTED_ROM")
            self.assertTrue(str(sel.selectedPath).endswith("Widget.rom.ORNCCP2"))


class TestConversions(unittest.TestCase):
    def test_quoted_string_split(self) -> None:
        self.assertEqual(split_asc_row('"A","B",C'), ["A", "B", "C"])

    def test_tilde_split(self) -> None:
        self.assertEqual(split_asc_row("A~B~C"), ["A", "B", "C"])
        # Trailing delimiter (DATA_OBSERVED on PLC2 ASC rows)
        self.assertEqual(split_asc_row("A~B~C~"), ["A", "B", "C"])

    def test_empty_value(self) -> None:
        v, kind, status, _ = convert_value("", datatype_raw=1, column_name="X")
        self.assertEqual(status, "EMPTY")
        self.assertIsNone(v)

    def test_numeric_conversion(self) -> None:
        v, kind, status, evid = convert_value(" 42", datatype_raw=1, column_name="X")
        self.assertEqual((v, kind, status), (42, "int", "OK"))
        self.assertIn("SOURCE_PROVEN", evid)

    def test_boolean_integer(self) -> None:
        self.assertEqual(convert_value("Y", datatype_raw=11, column_name="X")[0], True)
        self.assertEqual(convert_value("N", datatype_raw=11, column_name="X")[0], False)

    def test_hex_oct(self) -> None:
        self.assertEqual(convert_value("FF", datatype_raw=10, column_name="X")[0], 255)
        self.assertEqual(convert_value("17", datatype_raw=12, column_name="X")[0], 15)

    def test_selection_preserves_raw(self) -> None:
        v, kind, status, _ = convert_value("P314", datatype_raw=21, column_name="Motor_Ndx")
        self.assertEqual(v, "P314")
        self.assertEqual(kind, "selection_token")
        self.assertEqual(status, "OK")

    def test_unsupported_datatype(self) -> None:
        v, kind, status, evid = convert_value("x", datatype_raw=999, column_name="X")
        self.assertEqual(status, "UNSUPPORTED")
        self.assertEqual(kind, "unsupported")


class TestRecordShapes(unittest.TestCase):
    def test_short_and_long_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "T.asc").write_text(
                '"Name"~"Qty"\n'
                "onlyone\n"
                "a~1~EXTRA\n"
                "ok~2\n",
                encoding="latin-1",
            )
            menu = _menu(
                "T",
                [
                    _field("Title", 250),
                    _field("Name", 0),
                    _field("Qty", 1),
                ],
            )
            table = load_fortna_table(menu, directories=[d], ac_name="X")
            self.assertEqual(table.stats["recordCount"], 3)
            self.assertEqual(table.records[0].shapeStatus, "SHORT")
            self.assertEqual(table.records[1].shapeStatus, "LONG")
            self.assertEqual(table.records[2].shapeStatus, "OK")
            # extras preserved in diagnostics
            self.assertTrue(
                any(d.get("kind") == "FIELD_COUNT_LONG" for d in table.records[1].diagnostics)
            )


class TestPlc2Loader(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PLC2_FORTNA.is_file():
            raise unittest.SkipTest("PLC2 RUN missing")

    def test_complete_mtrchain_beyond_25_includes_m314(self) -> None:
        pack = load_run(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=PLC2_PROJECT if PLC2_PROJECT.is_file() else None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
            only_menus=["Mtrchain"],
        )
        t = pack["tables"][0]
        self.assertGreaterEqual(t["stats"]["recordCount"], 55)
        rec55 = next(r for r in t["records"] if r["recordIndex"] == 55)
        vals = {v["columnName"]: v["rawText"] for v in rec55["values"]}
        self.assertEqual(vals.get("Motor_Name"), "M314")
        self.assertEqual(vals.get("Motor_Ndx"), "M314")
        self.assertEqual(vals.get("Motor_Chained1"), "P314")
        self.assertEqual(vals.get("Motor_Aux"), "LATCH_MERGE_316")
        self.assertEqual(vals.get("Enabled"), "M136_AUX")

    def test_motor_chained4_beyond_25(self) -> None:
        pack = load_run(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=PLC2_PROJECT if PLC2_PROJECT.is_file() else None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
            only_menus=["Mtrchain"],
        )
        t = pack["tables"][0]
        hits = []
        for r in t["records"]:
            v = next(x for x in r["values"] if x["columnName"] == "Motor_Chained4")
            raw = (v["rawText"] or "").strip().upper()
            if raw and raw not in {"INVALID", "N/A", "NONE", ""}:
                hits.append((r["recordIndex"], v["rawText"]))
        self.assertTrue(any(i > 25 for i, _ in hits), hits[:5])

    def test_mergeinputs_and_trigrset_machine_specific(self) -> None:
        pack = load_run(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=PLC2_PROJECT if PLC2_PROJECT.is_file() else None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
            only_menus=["MergeInputs", "Trigrset"],
        )
        by = {t["menuName"]: t for t in pack["tables"]}
        self.assertEqual(by["MergeInputs"]["physicalSelection"]["selectedKind"], "MACHINE_SPECIFIC_ASC")
        self.assertIn("MergeInputs.asc.ORNCCP2", by["MergeInputs"]["physicalSelection"]["selectedPath"])
        self.assertEqual(by["Trigrset"]["physicalSelection"]["selectedKind"], "MACHINE_SPECIFIC_ASC")
        self.assertIn("Trigrset.asc.ORNCCP2", by["Trigrset"]["physicalSelection"]["selectedPath"])

    def test_deterministic_serialization(self) -> None:
        a = load_run(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
            only_menus=["EStop"],
        )
        b = load_run(
            fortna_mnu=PLC2_FORTNA,
            project_mnu=None,
            run_dir=PLC2_RUN,
            ac_name="ORNCCP2",
            only_menus=["EStop"],
        )
        self.assertEqual(
            json.dumps(a, sort_keys=True),
            json.dumps(b, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
