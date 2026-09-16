#!/usr/bin/env python3
"""CP4 evidence helpers — load CP3 graphs without rediscovering relationships."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fortna_reference_resolver import build_reference_graph
from fortna_semantics.common import index_cp3_graph


def load_or_build_cp3_index(
    *,
    graph_path: Path | None = None,
    run_dir: Path | None = None,
    ac_name: str | None = None,
    fortna_mnu: Path | None = None,
    project_mnu: Path | None = None,
) -> dict[str, Any]:
    """Prefer an existing CP3 artifact; optionally rebuild via frozen CP3 API."""
    if graph_path and Path(graph_path).is_file():
        graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        return index_cp3_graph(graph)
    if not (run_dir and ac_name):
        raise ValueError("Need graph_path or run_dir+ac_name")
    run_dir = Path(run_dir)
    fortna = Path(fortna_mnu) if fortna_mnu else run_dir / "FORTNA" / "fortna.mnu"
    project = Path(project_mnu) if project_mnu else run_dir / "PROJECT" / "project.mnu"
    if not project.is_file():
        project = None
    graph = build_reference_graph(
        fortna_mnu=fortna,
        project_mnu=project,
        run_dir=run_dir,
        ac_name=ac_name,
    )
    return index_cp3_graph(graph)


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
