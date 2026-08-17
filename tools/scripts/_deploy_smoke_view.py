"""Deploy a minimal Perspective smoke-test view into the gateway project."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

GATEWAY_PROJECT = Path(
    r"C:\Program Files\Inductive Automation\Ignition\data\projects\SiteForge_ORNCCP5"
)
GOOD_GLOBAL = Path(
    r"C:\Program Files\Inductive Automation\Ignition\data\projects\ProjectTest"
    r"\ignition\global-props"
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resource() -> dict:
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
        json.dumps(_resource(), indent=2), encoding="utf-8"
    )


def main() -> None:
    proj = GATEWAY_PROJECT
    proj.mkdir(parents=True, exist_ok=True)

    # Clean project.json
    (proj / "project.json").write_text(
        json.dumps(
            {
                "title": "SiteForge_ORNCCP5",
                "description": "FortnaPlus plant layout for ORNCCP5",
                "enabled": True,
                "inheritable": False,
                "parent": "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Valid global-props (empty data.bin breaks design surface)
    gp = proj / "ignition" / "global-props"
    gp.mkdir(parents=True, exist_ok=True)
    if GOOD_GLOBAL.is_dir():
        (gp / "data.bin").write_bytes((GOOD_GLOBAL / "data.bin").read_bytes())
        (gp / "resource.json").write_text(
            (GOOD_GLOBAL / "resource.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    base = proj / "com.inductiveautomation.perspective" / "views"

    smoke = {
        "custom": {},
        "params": {},
        "propConfig": {},
        "props": {"defaultSize": {"width": 1200, "height": 700}},
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
                    "position": {"x": 20, "y": 16, "width": 900, "height": 28},
                    "props": {
                        "text": (
                            "FortnaPlus ORNCCP5 — SMOKE TEST "
                            "(if you see cyan bar + green PE, project folder is correct)"
                        ),
                        "style": {
                            "color": "#22d3ee",
                            "fontSize": "15px",
                            "fontWeight": "600",
                        },
                    },
                },
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Hint"},
                    "position": {"x": 20, "y": 52, "width": 900, "height": 22},
                    "props": {
                        "text": (
                            "Folder is correct: data/projects/SiteForge_ORNCCP5. "
                            "After this works, rebuild full plant layout."
                        ),
                        "style": {"color": "#94a3b8", "fontSize": "12px"},
                    },
                },
                {
                    "type": "ia.display.view",
                    "meta": {"name": "demo_conv"},
                    "position": {"x": 40, "y": 120, "width": 280, "height": 22},
                    "props": {
                        "path": "FortnaPlus/Components/Conveyor",
                        "params": {
                            "tagPath": "[default]Site/Zone5/Conveyors/P500/Run",
                            "label": "P500",
                            "printPage": "20",
                            "showLabel": True,
                            "width": 280,
                            "height": 22,
                        },
                    },
                },
                {
                    "type": "ia.display.view",
                    "meta": {"name": "demo_pe"},
                    "position": {"x": 40, "y": 180, "width": 48, "height": 48},
                    "props": {
                        "path": "FortnaPlus/Components/Photoeye",
                        "params": {
                            "tagPath": "[default]Site/Photoeyes/PE500_J/Clear",
                            "label": "PE500",
                            "printPage": "20",
                            "showLabel": True,
                        },
                    },
                },
                {
                    "type": "ia.display.label",
                    "meta": {"name": "PrintNote"},
                    "position": {"x": 100, "y": 192, "width": 400, "height": 20},
                    "props": {
                        "text": "p.20 = electrical drawing page (from Conveyor.asc)",
                        "style": {"color": "#fbbf24", "fontSize": "12px"},
                    },
                },
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Legend"},
                    "position": {"x": 40, "y": 250, "width": 520, "height": 20},
                    "props": {
                        "text": "Cyan = conveyor · Green PE · amber p.N = print sheet location",
                        "style": {"color": "#64748b", "fontSize": "11px"},
                    },
                },
            ],
        },
    }

    # Backup previous full layout once
    layout_dir = base / "FortnaPlus" / "POC" / "Plant_Layout"
    full = layout_dir / "view.json"
    if full.is_file() and full.stat().st_size > 20000:
        bak = layout_dir / "view.json.bak_full"
        if not bak.exists():
            bak.write_bytes(full.read_bytes())

    write_view(base / "FortnaPlus" / "POC" / "Plant_Layout", smoke)
    write_view(base / "FortnaPlus" / "POC" / "Plant_Small", smoke)
    write_view(base / "FortnaPlus" / "POC" / "Smoke_Test", smoke)

    # Match working ProjectTest conveyor component shape (+ print page param)
    conv = {
        "custom": {"fill": "#22d3ee", "stateText": "IDLE"},
        "params": {
            "tagPath": "[default]Site/Zone1/Conveyors/P100/Run",
            "label": "P100",
            "printPage": "",
            "showLabel": True,
            "width": 90,
            "height": 18,
        },
        "propConfig": {
            "params.tagPath": {"paramDirection": "input", "persistent": True},
            "params.label": {"paramDirection": "input", "persistent": True},
            "params.printPage": {"paramDirection": "input", "persistent": True},
            "params.showLabel": {"paramDirection": "input", "persistent": True},
            "params.width": {"paramDirection": "input", "persistent": True},
            "params.height": {"paramDirection": "input", "persistent": True},
            "custom.fill": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            'try(if(len({view.params.tagPath})=0, "#22d3ee", '
                            'if(tag({view.params.tagPath}), "#22c55e", "#22d3ee")), '
                            '"#22d3ee")'
                        )
                    },
                    "overlayOptOut": True,
                },
                "persistent": True,
            },
            "custom.stateText": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            'try('
                            'if({view.params.showLabel}, '
                            'if(len({view.params.printPage})>0, '
                            '{view.params.label} + " p." + {view.params.printPage}, '
                            '{view.params.label}), '
                            'if(len({view.params.printPage})>0, "p." + {view.params.printPage}, "")), '
                            '"" )'
                        )
                    },
                    "overlayOptOut": True,
                },
                "persistent": True,
            },
        },
        "props": {"defaultSize": {"width": 90, "height": 18}},
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "props": {
                "direction": "column",
                "justify": "center",
                "alignItems": "stretch",
                "style": {"borderRadius": 2, "padding": 0, "opacity": 0.95},
            },
            "propConfig": {
                "props.style.backgroundColor": {
                    "binding": {
                        "type": "property",
                        "config": {"path": "view.custom.fill"},
                        "overlayOptOut": True,
                    }
                }
            },
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Label"},
                    "position": {"grow": 1, "shrink": 1, "basis": "auto"},
                    "props": {
                        "text": "",
                        "alignVertical": "center",
                        "style": {
                            "textAlign": "center",
                            "color": "#0f172a",
                            "fontSize": "9px",
                            "fontWeight": "600",
                        },
                    },
                    "propConfig": {
                        "props.text": {
                            "binding": {
                                "type": "property",
                                "config": {"path": "view.custom.stateText"},
                                "overlayOptOut": True,
                            }
                        }
                    },
                }
            ],
        },
    }
    write_view(base / "FortnaPlus" / "Components" / "Conveyor", conv)

    pe = {
        "custom": {"fill": "#34d399", "stateText": ""},
        "params": {
            "tagPath": "[default]Site/Photoeyes/PE100/Clear",
            "label": "PE",
            "printPage": "",
            "showLabel": True,
        },
        "propConfig": {
            "params.tagPath": {"paramDirection": "input", "persistent": True},
            "params.label": {"paramDirection": "input", "persistent": True},
            "params.printPage": {"paramDirection": "input", "persistent": True},
            "params.showLabel": {"paramDirection": "input", "persistent": True},
            "custom.fill": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            'try(if(len({view.params.tagPath})=0, "#34d399", '
                            'if(tag({view.params.tagPath}), "#34d399", "#ef4444")), '
                            '"#34d399")'
                        )
                    },
                    "overlayOptOut": True,
                },
                "persistent": True,
            },
            "custom.stateText": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            'try('
                            'if(len({view.params.printPage})>0, "p." + {view.params.printPage}, '
                            'if({view.params.showLabel}, {view.params.label}, "")), '
                            '"" )'
                        )
                    },
                    "overlayOptOut": True,
                },
                "persistent": True,
            },
        },
        "props": {"defaultSize": {"width": 28, "height": 28}},
        "root": {
            "type": "ia.container.coord",
            "meta": {"name": "root"},
            "props": {
                "mode": "percent",
                "style": {"backgroundColor": "rgba(0,0,0,0)"},
            },
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Dot"},
                    "position": {"x": 10, "y": 10, "width": 80, "height": 80},
                    "props": {
                        "text": "",
                        "style": {
                            "backgroundColor": "#34d399",
                            "borderRadius": "50%",
                            "borderStyle": "solid",
                            "borderWidth": 2,
                            "borderColor": "#6ee7b7",
                        },
                    },
                    "propConfig": {
                        "props.style.backgroundColor": {
                            "binding": {
                                "type": "property",
                                "config": {"path": "view.custom.fill"},
                                "overlayOptOut": True,
                            }
                        }
                    },
                },
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Page"},
                    "position": {"x": 0, "y": 78, "width": 100, "height": 22},
                    "props": {
                        "text": "",
                        "style": {
                            "textAlign": "center",
                            "color": "#fbbf24",
                            "fontSize": "8px",
                            "fontWeight": "600",
                        },
                    },
                    "propConfig": {
                        "props.text": {
                            "binding": {
                                "type": "property",
                                "config": {"path": "view.custom.stateText"},
                                "overlayOptOut": True,
                            }
                        }
                    },
                },
            ],
        },
    }
    write_view(base / "FortnaPlus" / "Components" / "Photoeye", pe)

    # Clear ReadOnly (OneDrive / copy often sets it → Designer "Failed to commit")
    try:
        from fortna_perspective_pack import _clear_readonly_tree
        _clear_readonly_tree(proj)
    except Exception as exc:
        print("WARN clear readonly:", exc)

    print("OK deployed smoke views to", proj)
    print("data.bin", (gp / "data.bin").stat().st_size)
    print(
        "Plant_Layout",
        (base / "FortnaPlus/POC/Plant_Layout/view.json").stat().st_size,
    )


if __name__ == "__main__":
    main()
