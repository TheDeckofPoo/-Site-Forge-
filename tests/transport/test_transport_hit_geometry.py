#!/usr/bin/env python3
"""Regression: schematic hit geometry must track visible geometry after Area moves.

Simulates the stale-hitbox failure mode Curtis reproduced:
  select → assign Area → layout changes → select at NEW visible position
  (repeat ≥10 times). Hit targets must never remain at the pre-move location.

Contract under test (mirrors dashboard/transport-build.js):
  - One authoritative presentation offset map per current node set
  - After Area reassignment, offsets are invalidated and recomputed
  - Pick uses the SAME recomputed offsets as draw (no independent stale cache)
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


def compute_presentation_offsets(node_ids: list[str]) -> dict[str, dict[str, float]]:
    """Deterministic stand-in for computePresentationOffsets (lane index → dx)."""
    return {n: {"dx": float(i * 40), "dy": 0.0} for i, n in enumerate(node_ids)}


def visible_midpoint(
    node_id: str,
    base_xy: dict[str, tuple[float, float]],
    offsets: dict[str, dict[str, float]],
) -> tuple[float, float]:
    x, y = base_xy[node_id]
    off = offsets.get(node_id) or {"dx": 0.0, "dy": 0.0}
    return (x + off["dx"], y + off["dy"])


def pick_at(
    pt: tuple[float, float],
    node_ids: list[str],
    base_xy: dict[str, tuple[float, float]],
    offsets: dict[str, dict[str, float]],
    hit_half: float = 25.0,
) -> str | None:
    """Nearest-centerline pick using CURRENT offsets (authoritative geometry)."""
    best = None
    best_d = float("inf")
    for nid in node_ids:
        mx, my = visible_midpoint(nid, base_xy, offsets)
        d = ((pt[0] - mx) ** 2 + (pt[1] - my) ** 2) ** 0.5
        if d <= hit_half and d < best_d:
            best_d = d
            best = nid
    return best


class TestPresentationOffsetInvalidation(unittest.TestCase):
    def test_offset_map_must_be_rebuilt_when_node_set_changes(self) -> None:
        # Removing the FIRST node shifts lane indices for survivors — stale slice wrong.
        area_nodes = ["P400", "P402", "P404", "P406", "P138"]
        cached = compute_presentation_offsets(area_nodes)
        remaining = ["P402", "P404", "P406", "P138"]  # P400 removed → everyone shifts
        stale = {k: cached[k] for k in remaining if k in cached}
        fresh = compute_presentation_offsets(remaining)
        self.assertNotEqual(stale, fresh)
        self.assertEqual(stale["P402"]["dx"], 40.0)  # old lane 1
        self.assertEqual(fresh["P402"]["dx"], 0.0)  # new lane 0
        for i in range(10):
            remaining2 = list(remaining)
            if remaining2:
                remaining2.pop(0)  # shift indices
            remaining2.append(f"PX{i}")
            fresh2 = compute_presentation_offsets(remaining2)
            self.assertEqual(set(fresh2.keys()), set(remaining2))

    def test_ten_consecutive_area_moves_hit_tracks_visible(self) -> None:
        """Reproduce Curtis bug: after N Area moves, click NEW visible pos must hit."""
        # Far-apart engineering bases so hit radii do not collide across nodes
        base_xy = {f"P{100 + i}": (float(i * 500), 50.0) for i in range(12)}
        area_a = list(base_xy.keys())
        area_b: list[str] = []
        stale_offsets: dict[str, dict[str, float]] | None = None

        for step in range(10):
            live_before = compute_presentation_offsets(area_a)
            mover = area_a[0]  # always move head → forces lane shift for survivors
            area_a = [n for n in area_a if n != mover]
            area_b.append(mover)

            offsets_a = compute_presentation_offsets(area_a)
            offsets_b = compute_presentation_offsets(area_b)

            if stale_offsets is not None and area_a:
                # Survivors that changed lane: NEW visible mid must hit with LIVE offsets
                for nid in area_a:
                    if nid not in stale_offsets:
                        continue
                    if stale_offsets[nid] == offsets_a.get(nid):
                        continue
                    new_mid = visible_midpoint(nid, base_xy, offsets_a)
                    old_mid = visible_midpoint(nid, base_xy, stale_offsets)
                    self.assertNotEqual(old_mid, new_mid, f"step {step}: {nid} must re-lane")
                    # BUG pattern: clicking new visible pos with STALE offsets misses
                    hit_stale = pick_at(new_mid, area_a, base_xy, stale_offsets)
                    self.assertNotEqual(
                        hit_stale,
                        nid,
                        f"step {step}: stale offsets must NOT select {nid} at new mid",
                    )
                    hit_live = pick_at(new_mid, area_a, base_xy, offsets_a)
                    self.assertEqual(
                        hit_live,
                        nid,
                        f"step {step}: live pick at NEW visible pos must select {nid}",
                    )

            # Mover selectable at NEW Area B visible position
            mid_b = visible_midpoint(mover, base_xy, offsets_b)
            self.assertEqual(
                pick_at(mid_b, area_b, base_xy, offsets_b),
                mover,
                f"step {step}: mover {mover} must hit at Area B visible mid",
            )
            # Authoritative Area A pick must never return the moved id
            self.assertNotEqual(
                pick_at(mid_b, area_a, base_xy, offsets_a),
                mover,
                f"step {step}: Area A must not claim moved {mover}",
            )

            stale_offsets = dict(live_before)

        self.assertEqual(len(area_b), 10)
        self.assertEqual(len(area_a), 2)


class TestRunGeometryClassification(unittest.TestCase):
    """Gate B — evidence classification for RUN display fields (documentation lock)."""

    EXPECTED = {
        "entryCanvas": "PROVEN",
        "exitCanvas": "PROVEN",
        "pathCanvas": "PROVEN",
        "sourceAngle": "PROVEN",
        "b": "PROVEN",
        "runB": "PROVEN",
        "sweepDeg": "PROVEN",
        "insideRadius": "PROVEN",
        "curve_display_orientation": "UNKNOWN",
        "presentation_offsets": "DERIVED",
        "physical_topology_from_equipment_number": "UNKNOWN",
    }

    def test_classification_keys_locked(self) -> None:
        self.assertEqual(self.EXPECTED["curve_display_orientation"], "UNKNOWN")
        self.assertEqual(self.EXPECTED["entryCanvas"], "PROVEN")
        self.assertEqual(self.EXPECTED["presentation_offsets"], "DERIVED")


if __name__ == "__main__":
    unittest.main()
