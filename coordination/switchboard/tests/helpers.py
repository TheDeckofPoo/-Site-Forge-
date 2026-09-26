"""Shared test helpers (stdlib only)."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from coordination.switchboard.store import PACKAGE_DIR, Store

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "replay_ori052"
SHA_A = "444d222405e1eb11fb98bfead96acbd9b1b5cf4e"
SHA_B = "969eb83a9fe124e0e07614b40c1bd083d3bb1f5d"
SHA_C = "c0de052000000000000000000000000000000052"


def fixture(prefix: str) -> dict:
    [path] = sorted(FIXTURES.glob(f"{prefix}-*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def all_fixtures() -> list[tuple[str, dict]]:
    return [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(FIXTURES.glob("*.json"))]


class SwitchboardCase(unittest.TestCase):
    """Each test gets an isolated Switchboard root in a temp dir."""

    night_shift: dict = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="switchboard-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.make_root(self.tmp / "root", self.night_shift)
        self.store = Store(self.root)

    @staticmethod
    def make_root(root: Path, night_shift: dict | None = None) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        cfg = json.loads((PACKAGE_DIR / "config.json").read_text(encoding="utf-8"))
        cfg["night_shift"].update(night_shift or {})
        (root / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return root

    def post(self, packet: dict, expect_ok: bool | None = True) -> dict:
        res = self.store.post(copy.deepcopy(packet))
        if expect_ok is True:
            self.assertTrue(res["accepted"], f"expected accepted: {res}")
        elif expect_ok is False:
            self.assertFalse(res["accepted"], f"expected rejection: {res}")
        return res

    def post_upto(self, last_prefix: str) -> None:
        for name, pkt in all_fixtures():
            self.post(pkt)
            if name.startswith(last_prefix + "-"):
                return

    def state(self) -> dict:
        return self.store.load_state()

    def defect(self, ori: str = "ORI-052") -> dict:
        return self.state()["defects"][ori]

    @staticmethod
    def codes(res: dict) -> set[str]:
        return {f["code"] for f in res["flags"]}
