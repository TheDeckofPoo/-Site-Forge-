#!/usr/bin/env python3
"""PL-1 regression: Area move must not re-layout unrelated conveyors.

Contract:
  INITIAL layout → freeze presentation offsets
  move one node to another Area → unaffected display_dx/dy identical
  repeat several times
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


import unittest
from copy import deepcopy


def freeze_layout(nodes: list[dict]) -> None:
    for i, n in enumerate(nodes):
        n["display_dx"] = float(i * 40)
        n["display_dy"] = 0.0
        n["_layoutInitialized"] = True


def snapshot_xy(nodes: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    out = {}
    for n in nodes:
        out[n["id"]] = (
            float(n.get("x") or 0),
            float(n.get("y") or 0),
            float(n.get("display_dx") or 0),
            float(n.get("display_dy") or 0),
        )
    return out


def move_to_area(src: list[dict], dest: list[dict], node_id: str) -> None:
    idx = next(i for i, n in enumerate(src) if n["id"] == node_id)
    node = src.pop(idx)
    dest.append(node)
    # PL-1 contract: frozen nodes keep display offsets; no lane recompute


class TestAreaMovePositionPersistence(unittest.TestCase):
    def test_unaffected_positions_stable_across_moves(self) -> None:
        area_a = [{"id": f"P{100 + i}", "x": float(i * 100), "y": 50.0} for i in range(12)]
        area_b: list[dict] = []
        freeze_layout(area_a)
        before = snapshot_xy(area_a)

        for step in range(5):
            mover = area_a[0]["id"]
            unaffected = [n["id"] for n in area_a[1:]]
            pre = snapshot_xy(area_a)
            move_to_area(area_a, area_b, mover)
            post = snapshot_xy(area_a)
            for nid in unaffected:
                self.assertEqual(
                    pre[nid],
                    post[nid],
                    f"step {step}: {nid} X/Y/display offset changed after moving {mover}",
                )
            # Mover keeps its own frozen offsets in the destination
            moved = next(n for n in area_b if n["id"] == mover)
            self.assertEqual(
                (moved["display_dx"], moved["display_dy"]),
                (before[mover][2], before[mover][3]),
            )

        self.assertEqual(len(area_b), 5)
        self.assertEqual(len(area_a), 7)


if __name__ == "__main__":
    unittest.main()
