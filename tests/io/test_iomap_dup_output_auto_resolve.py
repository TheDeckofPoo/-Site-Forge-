#!/usr/bin/env python3
"""Duplicate OUTPUT owners: keep highest-priority, do not hard-fail the build."""
from __future__ import annotations

import unittest


def _output_owner_priority(row: dict) -> int:
    u = str(row.get("tname") or row.get("member") or "").upper()
    if any(k in u for k in ("SSVSTOP", "SSV", "ESTOP")):
        return 120
    if "STOP" in u:
        return 115
    if any(k in u for k in ("ESR", "MCR", "SOL", "GATE")):
        return 100
    if "TRANS" in u:
        return 90
    if any(k in u for k in ("MTR", "CONV", "DISC", "AUX")):
        return 80
    if any(k in u for k in ("PL", "PW", "WH", "HORN", "BEACON", "LIGHT", "CPPW", "CP3PL")):
        return 15
    return 50


def resolve_dups(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    owners: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("mod_dir") != "O":
            continue
        ch = str(row.get("channel") or "")
        if ch:
            owners.setdefault(ch, []).append(row)
    dups = {ch: o for ch, o in owners.items() if len(o) > 1}
    resolved = []
    keep: dict[str, str] = {}
    for ch, ow in sorted(dups.items()):
        ranked = sorted(ow, key=lambda o: (-_output_owner_priority(o), str(o.get("tname") or "")))
        keep[ch] = str(ranked[0].get("tname") or "")
        resolved.append({"channel": ch, "kept": keep[ch], "dropped": [str(o.get("tname") or "") for o in ranked[1:]]})
    out = [
        r for r in rows
        if r.get("mod_dir") != "O"
        or str(r.get("channel") or "") not in keep
        or str(r.get("tname") or "") == keep[str(r.get("channel") or "")]
    ]
    return out, resolved


class TestIoMapDupOutputAutoResolve(unittest.TestCase):
    def test_prefers_ssv_over_pilot_light(self) -> None:
        rows = [
            {"mod_dir": "O", "channel": "AENTR5:O.Data[12].4", "tname": "CP3PL"},
            {"mod_dir": "O", "channel": "AENTR5:O.Data[12].4", "tname": "EZSSV12"},
            {"mod_dir": "I", "channel": "AENTR5:I.Data[1].0", "tname": "PE1"},
        ]
        out, resolved = resolve_dups(rows)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["kept"], "EZSSV12")
        self.assertEqual(resolved[0]["dropped"], ["CP3PL"])
        names = {r["tname"] for r in out if r["mod_dir"] == "O"}
        self.assertEqual(names, {"EZSSV12"})
        self.assertTrue(any(r["tname"] == "PE1" for r in out))

    def test_curtis_collision_set(self) -> None:
        rows = [
            {"mod_dir": "O", "channel": "AENTR3:O.Data[18].2", "tname": "MTRANS"},
            {"mod_dir": "O", "channel": "AENTR3:O.Data[18].2", "tname": "SSVSTOP1"},
            {"mod_dir": "O", "channel": "AENTR5:O.Data[12].7", "tname": "CPPW5"},
            {"mod_dir": "O", "channel": "AENTR5:O.Data[12].7", "tname": "MX14P_MX14SSV"},
        ]
        out, resolved = resolve_dups(rows)
        self.assertEqual(len(resolved), 2)
        by_ch = {r["channel"]: r for r in resolved}
        self.assertEqual(by_ch["AENTR3:O.Data[18].2"]["kept"], "SSVSTOP1")
        self.assertEqual(by_ch["AENTR5:O.Data[12].7"]["kept"], "MX14P_MX14SSV")
        kept = {r["tname"] for r in out}
        self.assertEqual(kept, {"SSVSTOP1", "MX14P_MX14SSV"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
