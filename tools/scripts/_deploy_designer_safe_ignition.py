#!/usr/bin/env python3
"""Deploy designer-safe Ignition project: ProjectTest shell + RUN symbols grid."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PT = Path(r"C:\Program Files\Inductive Automation\Ignition\data\projects\ProjectTest")
PROJECTS = Path(r"C:\Program Files\Inductive Automation\Ignition\data\projects")
REPO = Path(__file__).resolve().parent.parent.parent
IGN_BUILD = REPO / "exports" / "ignition-build"


def _latest(name: str, under: Path | None = None) -> Path | None:
    """Newest file matching name under ignition-build exports."""
    root = under or IGN_BUILD
    if not root.is_dir():
        return None
    hits = sorted(root.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resource() -> dict:
    return {
        "scope": "G",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["view.json"],
        "attributes": {
            "lastModification": {"actor": "FortnaPlus", "timestamp": _ts()}
        },
    }


def write_view(folder: Path, view: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "view.json").write_text(json.dumps(view, indent=2), encoding="utf-8")
    (folder / "resource.json").write_text(
        json.dumps(resource(), indent=2), encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Deploy designer-safe Ignition project")
    ap.add_argument(
        "--project-name",
        default="",
        help="Gateway project folder name (default FortnaPlus_ORNCCP5 or from LATEST.json)",
    )
    ap.add_argument(
        "--out-dir",
        default="",
        help="Prefer symbols/tags from this ignition-build export folder",
    )
    args = ap.parse_args()

    if not PT.is_dir():
        raise SystemExit(f"ProjectTest missing: {PT}")

    # Resolve stamp / project name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    latest_meta: dict = {}
    latest_json = IGN_BUILD / "LATEST.json"
    if latest_json.is_file():
        try:
            latest_meta = json.loads(latest_json.read_text(encoding="utf-8"))
            stamp = latest_meta.get("folder_stamp") or stamp
        except Exception:
            latest_meta = {}

    proj_name = (args.project_name or "").strip()
    if not proj_name:
        proj_name = (
            (latest_meta.get("project_name") or "").strip()
            or f"FortnaPlus_ORNCCP5_{stamp}"
        )

    gw = PROJECTS / proj_name
    export_copy = IGN_BUILD / "_designer_safe" / proj_name

    # Prefer symbols from the build that just finished
    out_hint = Path(args.out_dir) if args.out_dir else None
    sym = None
    tags = None
    if out_hint and out_hint.is_dir():
        if (out_hint / "hmi_symbols.json").is_file():
            sym = out_hint / "hmi_symbols.json"
        if (out_hint / "tags_import.json").is_file():
            tags = out_hint / "tags_import.json"
    if not sym:
        sym = _latest("hmi_symbols.json")
    if not tags:
        tags = _latest("tags_import.json")

    # Clone known-good designer shell
    if gw.exists():
        shutil.rmtree(gw)
    shutil.copytree(PT, gw)

    # Drop nested junk paths if present
    nested = (
        gw
        / "com.inductiveautomation.perspective"
        / "views"
        / "FortnaPlus"
        / "FortnaPlus"
    )
    if nested.is_dir():
        shutil.rmtree(nested)

    (gw / "project.json").write_text(
        json.dumps(
            {
                "title": proj_name,
                "description": (
                    f"Designer-safe shell + RUN layout · stamp {stamp}"
                ),
                "enabled": True,
                "inheritable": False,
                "parent": "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    symbols: list[dict] = []
    if sym and sym.is_file():
        symbols = (json.loads(sym.read_text(encoding="utf-8")).get("symbols") or [])
    convs = [s for s in symbols if s.get("kind") == "conveyor"][:24]
    pes = [s for s in symbols if s.get("kind") == "photoeye"][:24]

    views = gw / "com.inductiveautomation.perspective" / "views" / "FortnaPlus"

    # Ensure components are ProjectTest originals (already from clone)
    children: list[dict] = [
        {
            "type": "ia.display.label",
            "meta": {"name": "Title"},
            "position": {"x": 12, "y": 8, "width": 900, "height": 24},
            "props": {
                "text": (
                    f"FortnaPlus ORNCCP5 — {len(convs)} conv + {len(pes)} PE "
                    "(ProjectTest designer shell)"
                ),
                "style": {
                    "color": "#94a3b8",
                    "fontSize": "13px",
                    "fontWeight": "600",
                },
            },
        }
    ]

    x0, y0 = 30, 50
    for i, s in enumerate(convs):
        name = s.get("name") or f"P{i}"
        tag = (s.get("tags") or {}).get("run") or (
            f"[default]Site/Zone5/Conveyors/{name}/Run"
        )
        col, row = i % 6, i // 6
        children.append(
            {
                "type": "ia.display.view",
                "meta": {"name": f"conv_{i}_{name}"[:40]},
                "position": {
                    "x": x0 + col * 140,
                    "y": y0 + row * 36,
                    "width": 120,
                    "height": 22,
                },
                "props": {
                    "path": "FortnaPlus/Components/Conveyor",
                    "params": {
                        "tagPath": tag,
                        "label": str(name),
                        "width": 120,
                        "height": 22,
                    },
                },
            }
        )

    pe_y = y0 + ((len(convs) + 5) // 6) * 36 + 40
    for i, s in enumerate(pes):
        name = s.get("name") or f"PE{i}"
        tag = (s.get("tags") or {}).get("clear") or (
            f"[default]Site/Site/Photoeyes/{name}/Clear"
        )
        col, row = i % 8, i // 8
        children.append(
            {
                "type": "ia.display.view",
                "meta": {"name": f"pe_{i}_{name}"[:40]},
                "position": {
                    "x": x0 + col * 100,
                    "y": pe_y + row * 48,
                    "width": 80,
                    "height": 36,
                },
                "props": {
                    "path": "FortnaPlus/Components/Photoeye",
                    "params": {
                        "tagPath": tag,
                        "label": str(name)[:14],
                        "width": 80,
                        "height": 36,
                    },
                },
            }
        )

    children.append(
        {
            "type": "ia.display.label",
            "meta": {"name": "Hint"},
            "position": {
                "x": 12,
                "y": pe_y + ((len(pes) + 7) // 8) * 48 + 16,
                "width": 920,
                "height": 40,
            },
            "props": {
                "text": (
                    "If this opens without white 'no-project', design surface is OK. "
                    "Tags: already import tags_import.json if needed."
                ),
                "style": {"color": "#64748b", "fontSize": "11px"},
            },
        }
    )

    h = pe_y + ((len(pes) + 7) // 8) * 48 + 70
    plant = {
        "custom": {},
        "params": {},
        "propConfig": {},
        "props": {"defaultSize": {"width": 1000, "height": max(500, h)}},
        "root": {
            "type": "ia.container.coord",
            "meta": {"name": "root"},
            "props": {
                "mode": "fixed",
                "aspectRatio": "",
                "style": {"backgroundColor": "#0a0f14"},
            },
            "children": children,
        },
    }
    write_view(views / "POC" / "Plant_Small", plant)
    write_view(views / "POC" / "Plant_Layout", plant)

    smoke = {
        "custom": {},
        "params": {},
        "propConfig": {},
        "props": {"defaultSize": {"width": 900, "height": 400}},
        "root": {
            "type": "ia.container.coord",
            "meta": {"name": "root"},
            "props": {
                "mode": "fixed",
                "aspectRatio": "",
                "style": {"backgroundColor": "#0a0f14"},
            },
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Title"},
                    "position": {"x": 12, "y": 8, "width": 800, "height": 24},
                    "props": {
                        "text": "SMOKE — cyan bar + green PE = design surface works",
                        "style": {
                            "color": "#22d3ee",
                            "fontSize": "14px",
                            "fontWeight": "600",
                        },
                    },
                },
                {
                    "type": "ia.display.view",
                    "meta": {"name": "demo_conv"},
                    "position": {"x": 40, "y": 80, "width": 200, "height": 24},
                    "props": {
                        "path": "FortnaPlus/Components/Conveyor",
                        "params": {
                            "tagPath": "[default]Site/Zone5/Conveyors/P500/Run",
                            "label": "P500",
                            "width": 200,
                            "height": 24,
                        },
                    },
                },
                {
                    "type": "ia.display.view",
                    "meta": {"name": "demo_pe"},
                    "position": {"x": 40, "y": 140, "width": 80, "height": 36},
                    "props": {
                        "path": "FortnaPlus/Components/Photoeye",
                        "params": {
                            "tagPath": "[default]Site/Site/Photoeyes/PE500_J/Clear",
                            "label": "PE500_J",
                            "width": 80,
                            "height": 36,
                        },
                    },
                },
            ],
        },
    }
    write_view(views / "POC" / "Smoke_Test", smoke)

    if tags and tags.is_file():
        (gw / "tags_import.json").write_bytes(tags.read_bytes())

    (gw / "BUILD_STAMP.txt").write_text(
        "\n".join(
            [
                f"folder_stamp={stamp}",
                f"project_name={proj_name}",
                f"symbols={sym}",
                f"tags={tags}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Export copy for dashboard (also timestamped name)
    if export_copy.exists():
        shutil.rmtree(export_copy)
    export_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(gw, export_copy)

    print("OK deployed designer-safe project")
    print("  stamp:", stamp)
    print("  gateway:", gw)
    print("  export:", export_copy)
    print("  conv", len(convs), "pe", len(pes))
    for p in (views / "POC").rglob("view.json"):
        print(" ", p.parent.name, p.stat().st_size)


if __name__ == "__main__":
    main()
