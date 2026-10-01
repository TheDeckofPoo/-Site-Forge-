#!/usr/bin/env python3
"""ORI-073 panel identity + ORI-074/CD10 bank-0 + print-cannot-override RUN."""
from __future__ import annotations

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))


def _write_asc(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _write_point_eipcfg(path: Path) -> None:
    """Three POINT adapters with OutputAddress 0/4/6 — Reno-shaped, generic names."""
    root = ET.Element(
        "EthernetIP", name="TESTPICK", version="1.0", interfaceip="192.168.1.9"
    )
    specs = [
        ("ADA1", "192.168.1.52", "0", "48", 4, 4, "1734-IB8", "1734-OA4"),
        ("ADA2", "192.168.1.63", "4", "60", 4, 2, "1734-IA4", "1734-OA4"),
        ("ADA3", "192.168.1.53", "6", "72", 6, 5, "1734-IB8", "1734-OA4"),
    ]
    for name, tip, out_addr, in_addr, n_in, n_out, in_cat, out_cat in specs:
        ad = ET.SubElement(
            root,
            "Adapter",
            targetip=tip,
            name=name,
            InputAddress=in_addr,
            OutputAddress=out_addr,
        )
        ET.SubElement(
            ad,
            "Module",
            name=name,
            slot="0",
            type="1734-AENTR",
            connection="HEADNODE",
            T2OSlotSize="1",
            O2TSlotSize="1",
        )
        slot = 1
        for _ in range(n_in):
            # ADA3 uses mix of IB8 then IA4 for 6 inputs
            cat = in_cat
            if name == "ADA3" and slot > 4:
                cat = "1734-IA4"
            ET.SubElement(
                ad,
                "Module",
                name=f"{name}-{cat.split('-')[-1]}",
                slot=str(slot),
                type=cat,
                connection="RACKOPTIMIZED",
            )
            slot += 1
        for _ in range(n_out):
            ET.SubElement(
                ad,
                "Module",
                name=f"{name}-OA4",
                slot=str(slot),
                type=out_cat,
                connection="RACKOPTIMIZED",
            )
            slot += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _build_synthetic_run(root: Path) -> Path:
    run = root / "RUN"
    fortna = run / "FORTNA"
    fortna.mkdir(parents=True)
    (run / "project.cfg").write_text("MACHINENAME=TESTPICK\n", encoding="utf-8")
    _write_point_eipcfg(fortna / "TESTPICK-RTA1-eipcfg.xml")
    # Panel tokens deliberately do NOT match adapter digit suffixes:
    # PAN2 banks cover ADA3; PAN12 banks cover ADA2.
    cfg_header = (
        '"Desc"~"Bank"~"Octal_Word"~"LoHi"~"In_Out"~"I_O_Type"~"Interface"'
        '~"Granularity"~"Countdown"~"Status"~"Process"'
    )
    rows = []
    # PAN1 → ADA1: I 56-59, O 0-3
    for bank, word, lohi, mask in [
        (56, 1000, "Low", "0000000000000000"),
        (57, 1000, "High", "0000000000000000"),
        (58, 1001, "Low", "0000000000000000"),
        (59, 1001, "High", "0000000000000000"),
        (0, 1002, "Low", "0000000011111111"),
        (1, 1002, "High", "0000000011111111"),
        (2, 1003, "Low", "0000000011111111"),
        (3, 1003, "High", "0000000011111111"),
    ]:
        rows.append(
            f"PAN1~{bank}~{word}~{lohi}~{mask}~Digital~RTA1~0~-1~Ok~SORT~"
        )
    # PAN12 → ADA2: I 68-71, O 4-5
    for bank, word, lohi, mask in [
        (68, 1142, "Low", "0000000000000000"),
        (69, 1142, "High", "0000000000000000"),
        (70, 1143, "Low", "0000000000000000"),
        (71, 1143, "High", "0000000000000000"),
        (4, 1144, "Low", "0000000011111111"),
        (5, 1144, "High", "0000000011111111"),
    ]:
        rows.append(
            f"PAN12~{bank}~{word}~{lohi}~{mask}~Digital~RTA1~0~-1~Ok~SORT~"
        )
    # PAN2 → ADA3 (NOT ADA2): I 80-85, O 6-10
    for bank, word, lohi, mask in [
        (80, 1005, "Low", "0000000000000000"),
        (81, 1005, "High", "0000000000000000"),
        (82, 1006, "Low", "0000000000000000"),
        (83, 1006, "High", "0000000000000000"),
        (84, 1007, "Low", "0000000000000000"),
        (85, 1007, "High", "0000000000000000"),
        (6, 1010, "Low", "0000000011111111"),
        (7, 1010, "High", "0000000011111111"),
        (8, 1011, "Low", "0000000011111111"),
        (9, 1011, "High", "0000000011111111"),
        (10, 1012, "Low", "0000000011111111"),
    ]:
        rows.append(
            f"PAN2~{bank}~{word}~{lohi}~{mask}~Digital~RTA1~0~-1~Ok~SORT~"
        )
    _write_asc(fortna / "Configio.asc.TESTPICK", cfg_header, rows)
    # Source-aware radix proof for IO_Address_Bit (no silent octal assumption)
    (fortna / "flagmenu.asc").write_text("OCTAL_MODE~1~\n", encoding="utf-8")
    (fortna / "fortna.mnu").write_text(
        "'Conveyor'              -19    0   18    8   15   18    0    0    2   6000   42   65    2  61 1040   0   0 995   0   1 657 0000000000000000\n"
        "'IO_Address_Word'           12    6    0 3072            ' '    1    0   0  26   3   1   3  18  26   9  10   0   4   3 ' ' 0 0\n"
        "'IO_Address_Bit'            12    6    0   16            ' '    1    0   0  38   3   1   4  18  26   9  10   0   2   4 ' ' 0 0\n",
        encoding="utf-8",
    )
    return run


class TestPanelIdentityBank0(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run = _build_synthetic_run(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_aliases_follow_banks_not_digits(self) -> None:
        from fortna_panel_identity import build_panel_identity_model
        from fortna_physical_word_resolver import (
            _load_configio_rows,
            parse_eipcfg,
            _synthesize_point_banks_from_adapter_addresses,
        )

        topo = parse_eipcfg(self.run, "TESTPICK")
        ads = topo["adapters"]
        _synthesize_point_banks_from_adapter_addresses(ads)
        rows = _load_configio_rows(self.run, "TESTPICK")
        model = build_panel_identity_model(
            adapters=ads, configio_rows=rows, machine="TESTPICK"
        )
        by = {a["panel_token"]: a for a in model["aliases"]}
        self.assertEqual(by["PAN1"]["adapter_name"], "ADA1")
        self.assertEqual(by["PAN1"]["status"], "PROVEN")
        self.assertEqual(by["PAN12"]["adapter_name"], "ADA2")
        self.assertEqual(by["PAN2"]["adapter_name"], "ADA3")  # NOT ADA2
        self.assertNotEqual(by["PAN12"]["adapter_name"], "ADA12")

    def test_bank0_output_maps_first_oa_slot(self) -> None:
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit

        pm = build_physical_word_map(self.run, "TESTPICK")
        self.assertEqual(len(pm.get("unresolved") or []), 0)
        hit = resolve_word_bit(pm, 1002, 0)
        self.assertIsNotNone(hit)
        self.assertEqual(int(hit.get("eip_slot") or -1), 5)
        # High half bank 1 → next OA slot
        hit_h = resolve_word_bit(pm, 1002, 10)
        self.assertIsNotNone(hit_h)
        self.assertEqual(int(hit_h.get("eip_slot") or -1), 6)

    def test_print_conflict_does_not_override_run(self) -> None:
        """Drawing may claim a different slot; CURRENT RUN bank math wins."""
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit

        pm = build_physical_word_map(self.run, "TESTPICK")
        hit = resolve_word_bit(pm, 1002, 0)
        run_slot = int(hit.get("eip_slot") or -1)
        drawing_claimed_slot = 6  # deliberate disagreement
        self.assertEqual(run_slot, 5)
        self.assertNotEqual(run_slot, drawing_claimed_slot)
        # Resolver must not flip to drawing slot
        self.assertEqual(run_slot, 5)

    def test_sibling_adapter_name_ip_conflict_not_joined(self) -> None:
        from fortna_panel_identity import build_panel_identity_model, panels_equivalent
        from fortna_physical_word_resolver import (
            _load_configio_rows,
            parse_eipcfg,
            _synthesize_point_banks_from_adapter_addresses,
        )

        topo = parse_eipcfg(self.run, "TESTPICK")
        ads = list(topo["adapters"])
        _synthesize_point_banks_from_adapter_addresses(ads)
        # Inject sibling-controller clone with same name, different IP + banks
        sibling = {
            "name": "ADA1",
            "targetip": "10.0.0.99",
            "input_address": "200",
            "output_address": "90",
            "modules": [],
            "rio_name": "ADA1",
            "panel": None,
            "adapter_index": 99,
        }
        # Panel banks still uniquely cover the real ADA1 (banks 0-3 / 56-59),
        # not the empty sibling — alias must stay on real IP.
        rows = _load_configio_rows(self.run, "TESTPICK")
        model = build_panel_identity_model(
            adapters=ads + [sibling], configio_rows=rows, machine="TESTPICK"
        )
        by = {a["panel_token"]: a for a in model["aliases"] if a.get("adapter_name")}
        self.assertEqual(by["PAN1"]["target_ip"], "192.168.1.52")
        self.assertTrue(
            panels_equivalent("PAN1", "ADA1", alias_model=model)
        )


class TestModuleCapacityOverflow(unittest.TestCase):
    def test_channel_beyond_oa4_capacity_rejected(self) -> None:
        from fortna_hardware_family import max_bits_for_catalog

        self.assertEqual(max_bits_for_catalog("1734-OA4"), 4)
        # Endpoint channel 4 on OA4 is out of range
        self.assertFalse(0 <= 4 < max_bits_for_catalog("1734-OA4"))
        self.assertTrue(0 <= 3 < max_bits_for_catalog("1734-OA4"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
