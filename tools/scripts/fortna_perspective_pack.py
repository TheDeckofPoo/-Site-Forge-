#!/usr/bin/env python3
"""
fortna_perspective_pack.py — Generate importable Perspective views/components.

Creates a minimal Ignition *project folder* you can:
  1) Copy into  <Ignition>/data/projects/FortnaPlus_POC/
  2) Or zip and import via Designer (File → Import)

Layout strategy (match dashboard Ignition Build):
  - Gold geometry = RUN Conveyor.asc X/Y/Length/Angle (via hmi_symbols + layout.svg)
  - Plant view uses plant-space uniform scale + true rotation (not H/V snap)
  - Optional SVG underlay = exact same drawing as dashboard layout_conveyors_only.svg
  - Interactive Conveyor/Photoeye embeds sit on top with tagPath params

Usage:
  py tools/scripts/fortna_perspective_pack.py pack --use-latest-symbols
  py tools/scripts/fortna_perspective_pack.py pack --symbols path/to/hmi_symbols.json
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


def _ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _stamp_folder(dt: datetime | None = None) -> str:
    """Filesystem-safe local timestamp for export folder names."""
    d = dt or _now_local()
    return d.strftime("%Y%m%d-%H%M%S")


def _stamp_human(dt: datetime | None = None) -> str:
    """Human-readable local time for titles / COPY notes / history."""
    d = dt or _now_local()
    # e.g. 2026-08-10 15:41:54 (local)
    return d.strftime("%Y-%m-%d %H:%M:%S %Z").strip() or d.strftime("%Y-%m-%d %H:%M:%S")


def _resource_json(files: list[str] | None = None) -> dict:
    return {
        "scope": "G",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": files or ["view.json"],
        "attributes": {
            "lastModification": {
                "actor": "FortnaPlus",
                "timestamp": _ts_utc(),
            }
        },
    }


def _clear_readonly_tree(root: Path) -> None:
    """Clear ReadOnly flags. OneDrive/copy often sets them; Designer then shows
    'no-project' and fails commit because it cannot write resources."""
    root = Path(root)
    if not root.exists():
        return
    try:
        import os
        import stat

        for p in [root, *root.rglob("*")]:
            try:
                mode = p.stat().st_mode
                if not (mode & stat.S_IWRITE):
                    os.chmod(p, mode | stat.S_IWRITE)
                # Windows ReadOnly attribute
                if os.name == "nt":
                    import ctypes

                    FILE_ATTRIBUTE_READONLY = 0x01
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
                    if attrs != -1 and (attrs & FILE_ATTRIBUTE_READONLY):
                        ctypes.windll.kernel32.SetFileAttributesW(
                            str(p), attrs & ~FILE_ATTRIBUTE_READONLY
                        )
            except Exception:
                pass
    except Exception:
        pass


def _ensure_global_props_bin(dest: Path) -> None:
    """Write a valid ignition/global-props/data.bin (gzip+binary GlobalProps).

    An empty data.bin causes Designer to open views as a blank white canvas
    labeled "no-project" even when the project name is correct in the title bar.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    candidates = [
        Path(r"C:\Program Files\Inductive Automation\Ignition\data\projects")
        / "ProjectTest"
        / "ignition"
        / "global-props"
        / "data.bin",
        REPO_ROOT / "tools" / "templates" / "ignition_global_props_data.bin",
    ]
    # Prefer any non-empty data.bin already on this gateway
    projects_root = Path(r"C:\Program Files\Inductive Automation\Ignition\data\projects")
    if projects_root.is_dir():
        for p in projects_root.glob("*/ignition/global-props/data.bin"):
            if p.is_file() and p.stat().st_size > 32:
                candidates.insert(0, p)
                break
    for src in candidates:
        try:
            if src.is_file() and src.stat().st_size > 32:
                dest.write_bytes(src.read_bytes())
                return
        except Exception:
            continue
    # Last resort: keep non-empty placeholder so resource loader does not treat
    # the file as missing (still better than 0-byte). Prefer fixing via copy.
    if not dest.is_file() or dest.stat().st_size == 0:
        dest.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00")



def _write_view(folder: Path, view: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "view.json").write_text(
        json.dumps(view, indent=2), encoding="utf-8"
    )
    (folder / "resource.json").write_text(
        json.dumps(_resource_json(), indent=2), encoding="utf-8"
    )


def make_conveyor_component() -> dict:
    """Reusable embedded view: params.tagPath = BOOL Run tag.

    Matches ProjectTest style (known-good in Designer 8.3). Label is the
    device name only (e.g. \"P508\") — no print-page suffix on the HMI face.
    Do NOT use string '+' in expressions (Designer returns null / no-project).
    """
    return {
        "custom": {
            "fill": "#22d3ee",
            "stateText": "IDLE",
        },
        "params": {
            "tagPath": "[default]Site/Zone1/Conveyors/P100/Run",
            "label": "P100",
            "width": 90,
            "height": 18,
        },
        "propConfig": {
            "params.tagPath": {"paramDirection": "input", "persistent": True},
            "params.label": {"paramDirection": "input", "persistent": True},
            "params.width": {"paramDirection": "input", "persistent": True},
            "params.height": {"paramDirection": "input", "persistent": True},
            "custom.fill": {
                "binding": {
                    "type": "expr",
                    "config": {
                        # Same pattern as ProjectTest (no try(), no string +)
                        "expression": (
                            'if(len({view.params.tagPath}) = 0, "#64748b", '
                            'if(tag({view.params.tagPath}), "#22c55e", "#22d3ee"))'
                        )
                    },
                },
                "persistent": True,
            },
            "custom.stateText": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            'if(len({view.params.tagPath}) = 0, "NO TAG", '
                            'if(tag({view.params.tagPath}), "RUN", "IDLE"))'
                        )
                    },
                },
                "persistent": True,
            },
        },
        "props": {
            "defaultSize": {"width": 90, "height": 18},
        },
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "props": {
                "direction": "column",
                "justify": "center",
                "alignItems": "stretch",
                "style": {
                    "classes": "",
                    "borderRadius": 4,
                    "borderStyle": "solid",
                    "borderWidth": 1,
                    "borderColor": "#1e293b",
                    "padding": 2,
                    "opacity": 0.95,
                },
            },
            "propConfig": {
                "props.style.backgroundColor": {
                    "binding": {
                        "type": "property",
                        "config": {"path": "view.custom.fill"},
                    }
                }
            },
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "Label"},
                    "position": {"grow": 1, "shrink": 1, "basis": "auto"},
                    "props": {
                        "text": "P100",
                        "alignVertical": "center",
                        "style": {
                            "textAlign": "center",
                            "color": "#0f172a",
                            "fontSize": "9px",
                            "fontWeight": "bold",
                            "fontFamily": "monospace",
                        },
                    },
                    "propConfig": {
                        "props.text": {
                            "binding": {
                                "type": "expr",
                                # concat() is valid; string + is NOT (null → no-project)
                                "config": {
                                    "expression": (
                                        'concat({view.params.label}, " · ", '
                                        "{view.custom.stateText})"
                                    )
                                },
                            }
                        }
                    },
                }
            ],
        },
    }


def _make_dot_component(
    *,
    name: str,
    default_fill: str,
    tag_expr_true: str,
    tag_expr_false: str,
    tag_expr_empty: str = "#64748b",
    default_size: int = 6,
    default_tag: str = "",
    default_label: str = "",
) -> dict:
    """
    Small circular symbol (PE / power supply / beacon).

    Root IS the disc (flex + borderRadius) — no nested children. That matches
    ProjectTest-style views that Designer 8.3 imports cleanly, and stays round
    at 6×6 embeds next to 16px-thick belts.
    """
    return {
        "custom": {
            "fill": default_fill,
        },
        "params": {
            "tagPath": default_tag,
            "label": default_label or name,
            "width": default_size,
            "height": default_size,
        },
        "propConfig": {
            "params.tagPath": {"paramDirection": "input", "persistent": True},
            "params.label": {"paramDirection": "input", "persistent": True},
            "params.width": {"paramDirection": "input", "persistent": True},
            "params.height": {"paramDirection": "input", "persistent": True},
            "custom.fill": {
                "binding": {
                    "type": "expr",
                    "config": {
                        "expression": (
                            f'if(len({{view.params.tagPath}}) = 0, "{tag_expr_empty}", '
                            f'if(tag({{view.params.tagPath}}), "{tag_expr_true}", "{tag_expr_false}"))'
                        )
                    },
                },
                "persistent": True,
            },
        },
        "props": {
            "defaultSize": {"width": default_size, "height": default_size},
        },
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "props": {
                "direction": "column",
                "justify": "center",
                "alignItems": "center",
                "style": {
                    "backgroundColor": default_fill,
                    "borderRadius": 999,
                    "borderStyle": "solid",
                    "borderWidth": 1,
                    "borderColor": "#0f172a",
                    "overflow": "hidden",
                },
            },
            "propConfig": {
                "props.style.backgroundColor": {
                    "binding": {
                        "type": "property",
                        "config": {"path": "view.custom.fill"},
                    }
                }
            },
            "children": [],
        },
    }


def make_photoeye_component() -> dict:
    """Small green/red PE disc (Clear true = green)."""
    return _make_dot_component(
        name="Photoeye",
        default_fill="#34d399",
        tag_expr_true="#34d399",
        tag_expr_false="#ef4444",
        default_size=6,
        default_tag="[default]Site/Zone1/Photoeyes/EZPE116_P/Clear",
        default_label="PE",
    )


def make_beacon_component() -> dict:
    """Small amber beacon disc (same size as PE, different color)."""
    return _make_dot_component(
        name="Beacon",
        default_fill="#fbbf24",
        tag_expr_true="#fbbf24",
        tag_expr_false="#78716c",
        tag_expr_empty="#fbbf24",
        default_size=6,
        default_tag="",
        default_label="WB",
    )


def make_power_supply_component() -> dict:
    """Small pink/magenta power-supply disc (same size as PE)."""
    return _make_dot_component(
        name="PowerSupply",
        default_fill="#f472b6",
        tag_expr_true="#f472b6",
        tag_expr_false="#9f1239",
        tag_expr_empty="#f472b6",
        default_size=6,
        default_tag="",
        default_label="PS",
    )


def _svg_data_url(svg_path: Path | None) -> str | None:
    if not svg_path or not Path(svg_path).is_file():
        return None
    raw = Path(svg_path).read_bytes()
    # Keep under ~1.5MB base64 for Designer comfort
    if len(raw) > 900_000:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def make_plant_view(
    instances: list[dict],
    *,
    title: str = "FortnaPlus plant layout",
    canvas_w: int = 1400,
    canvas_h: int = 900,
    svg_underlay: str | None = None,
    generated_at: str = "",
) -> dict:
    """
    Coordinate container with optional SVG underlay + embedded Conveyor/Photoeye.

    instances: [{kind, label, tagPath, x, y, width, height, rotate?}, ...]
    rotate is Perspective coord-container degrees (screen space, Y-down).
    """
    n_c = sum(1 for i in instances if i.get("kind") == "conveyor")
    n_p = sum(1 for i in instances if i.get("kind") == "photoeye")
    n_other = sum(
        1 for i in instances if i.get("kind") in ("beacon", "power_supply")
    )
    children: list[dict] = []

    # 0) Exact plant drawing under interactive symbols (dashboard parity)
    if svg_underlay:
        children.append(
            {
                "type": "ia.display.image",
                "meta": {"name": "PlantSvgUnderlay"},
                "position": {
                    "x": 0,
                    "y": 36,
                    "width": canvas_w,
                    "height": max(100, canvas_h - 72),
                },
                "props": {
                    "source": svg_underlay,
                    "fit": "contain",
                    "style": {"opacity": 0.55},
                },
            }
        )

    _KIND_PATH = {
        "conveyor": "FortnaPlus/Components/Conveyor",
        "photoeye": "FortnaPlus/Components/Photoeye",
        "beacon": "FortnaPlus/Components/Beacon",
        "power_supply": "FortnaPlus/Components/PowerSupply",
    }
    for i, inst in enumerate(instances):
        kind = inst.get("kind") or "conveyor"
        path = _KIND_PATH.get(kind, "FortnaPlus/Components/Photoeye")
        # Dots (PE/PS/beacon) = 6×6 circles; belts keep length×thickness
        if kind == "conveyor":
            w = int(inst.get("width") or 90)
            h = int(inst.get("height") or 10)
        else:
            w = int(inst.get("width") or 6)
            h = int(inst.get("height") or 6)
        lab = re.sub(r"[^A-Za-z0-9_]", "_", str(inst.get("label") or i))[:32]
        rotate = float(
            inst.get("rotate") if inst.get("rotate") is not None else inst.get("angle") or 0
        )
        # Opacity: when underlay is present, interactive belts are translucent hit-targets
        opacity = 0.55 if (svg_underlay and kind == "conveyor") else 1.0
        pos: dict = {
            "x": int(inst.get("x") or 20 + (i % 5) * 100),
            "y": int(inst.get("y") or 40 + (i // 5) * 50),
            "width": w,
            "height": h,
        }
        # Perspective coordinate container supports rotate (degrees, around top-left)
        if abs(rotate) > 0.05:
            pos["rotate"] = round(rotate, 2)

        # HMI face label = device name only (no "p.18" print-page clutter).
        # Print page stays on instance meta for crosswalk/OCR — not the visual.
        base_label = str(inst.get("label") or "").strip()
        # Strip any legacy "P508 p.18" / "P508 · print #18" that older packs baked in
        base_label = re.sub(r"\s+p\.\d+\s*$", "", base_label, flags=re.I)
        base_label = re.sub(r"\s*·\s*print\s*#\d+\s*$", "", base_label, flags=re.I)

        children.append(
            {
                "type": "ia.display.view",
                "meta": {"name": f"{kind}_{lab}_{i}"},
                "position": pos,
                "props": {
                    "path": path,
                    "params": {
                        "tagPath": inst.get("tagPath") or "",
                        "label": base_label,  # name only — never "p.18"
                        "width": w,
                        "height": h,
                    },
                    "style": {"opacity": opacity},
                },
            }
        )

    when = generated_at or _stamp_human()
    children.insert(
        0,
        {
            "type": "ia.display.label",
            "meta": {"name": "Title"},
            "position": {"x": 12, "y": 6, "width": min(1100, canvas_w - 24), "height": 26},
            "props": {
                "text": (
                    f"{title}  ·  {n_c} conv + {n_p} PE"
                    + (f" + {n_other} PS/beacon" if n_other else "")
                    + f"  ·  {when}"
                    + ("  ·  SVG underlay + tagPath embeds" if svg_underlay else "")
                ),
                "style": {
                    "color": "#94a3b8",
                    "fontSize": "12px",
                    "fontWeight": "600",
                },
            },
        },
    )
    children.insert(
        1,
        {
            "type": "ia.display.label",
            "meta": {"name": "Legend"},
            "position": {"x": 12, "y": canvas_h - 30, "width": min(900, canvas_w - 24), "height": 20},
            "props": {
                "text": (
                    "Underlay = dashboard plant SVG (geometry gold). "
                    "Cyan/green bars = interactive conveyors (tagPath). "
                    "Dots = PE Clear. Red border = missing tag (toggle Memory tags)."
                ),
                "style": {"color": "#64748b", "fontSize": "10px"},
            },
        },
    )

    return {
        "custom": {},
        "params": {},
        "propConfig": {},
        "props": {
            "defaultSize": {"width": canvas_w, "height": canvas_h},
        },
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


# Back-compat alias
def make_plant_small_view(instances: list[dict]) -> dict:
    return make_plant_view(instances, title="FortnaPlus POC plant", canvas_w=1100, canvas_h=700)


def _plant_spans(symbols: dict) -> tuple[float, float, float, float]:
    """Return min_x, max_x, min_y, max_y in plant units (from bounds or symbols)."""
    b = symbols.get("bounds_plant") or {}
    if all(k in b for k in ("min_x", "max_x", "min_y", "max_y")):
        return float(b["min_x"]), float(b["max_x"]), float(b["min_y"]), float(b["max_y"])

    # Recover from percent coords using fake 0..100 plant if no bounds
    xs, ys = [0.0, 100.0], [0.0, 100.0]
    for s in symbols.get("symbols") or []:
        xs.append(float(s.get("x_pct") or 0))
        ys.append(float(s.get("y_pct") or 0))
    return min(xs), max(xs), min(ys), max(ys)


def _is_physical_p(name: str) -> bool:
    """Physical belts only: P100, P100A, P1014… — drop AUX/ENC/G###/PB junk."""
    return bool(re.match(r"^P\d", name or "", re.I))


def _safe_tag_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip()) or "Tag"


def _area_for_name(name: str) -> str:
    """P309 / PE309 / EZPE602_F / WB500 → ZoneN (first digit of equipment #)."""
    u = (name or "").upper().strip()
    m = re.match(r"^P(\d)", u)
    if m:
        return f"Zone{m.group(1)}"
    m = re.match(r"^(?:EZ)?PE(\d)", u)
    if m:
        return f"Zone{m.group(1)[0]}"
    m = re.match(r"^(?:WB|WH|PS|ES|VFD)(\d)", u)
    if m:
        return f"Zone{m.group(1)[0]}"
    m = re.match(r"^(\d)", u)
    if m:
        return f"Zone{m.group(1)}"
    return "Site"


def _pct_to_plant(
    xp: float, yp: float, min_x: float, max_x: float, min_y: float, max_y: float
) -> tuple[float, float]:
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    px = min_x + (xp / 100.0) * span_x
    py = max_y - (yp / 100.0) * span_y
    return px, py


def _conv_plant_geom(
    s: dict, min_x: float, max_x: float, min_y: float, max_y: float
) -> tuple[float, float, float, float, float, float]:
    """Return plant (x0,y0,x1,y1,L,angle_deg) for a conveyor symbol."""
    span_x = max(max_x - min_x, 1.0)
    xp = float(s.get("x_pct") or 0)
    yp = float(s.get("y_pct") or 0)
    L = max((float(s.get("length_pct") or 2) / 100.0) * span_x, 200.0)
    ang = float(s.get("angle") or 0)
    x0, y0 = _pct_to_plant(xp, yp, min_x, max_x, min_y, max_y)
    rad = math.radians(ang)
    x1 = x0 + L * math.cos(rad)
    y1 = y0 + L * math.sin(rad)
    return x0, y0, x1, y1, L, ang


def _dist_point_to_seg(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float
) -> tuple[float, float, float]:
    """Return (dist, closest_x, closest_y) from point to segment."""
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    if denom < 1e-9:
        return math.hypot(px - x0, py - y0), x0, y0
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / denom))
    cx, cy = x0 + t * dx, y0 + t * dy
    return math.hypot(px - cx, py - cy), cx, cy


def select_cluster(
    symbols: dict,
    *,
    max_conv: int = 10,
    max_pe: int = 10,
) -> tuple[list[dict], list[dict]]:
    """
    Pick a tight connected neighborhood of physical conveyors + nearby PEs.

    Seed = longest physical P### near the plant median (avoids mezzanine islands).
    Grow by nearest-neighbor until max_conv. PEs = closest to those belts, snapped later.
    """
    all_syms = list(symbols.get("symbols") or [])
    min_x, max_x, min_y, max_y = _plant_spans(symbols)
    convs = [
        s for s in all_syms
        if s.get("kind") == "conveyor" and _is_physical_p(str(s.get("name") or ""))
    ]
    pes = [s for s in all_syms if s.get("kind") == "photoeye"]
    if not convs:
        return [], []

    # Plant midpoints for distance
    geom: dict[str, tuple] = {}
    mids: list[tuple[float, float, dict]] = []
    for s in convs:
        x0, y0, x1, y1, L, ang = _conv_plant_geom(s, min_x, max_x, min_y, max_y)
        name = str(s.get("name") or "")
        geom[name] = (x0, y0, x1, y1, L, ang)
        mids.append(((x0 + x1) / 2, (y0 + y1) / 2, s))

    xs = [m[0] for m in mids]
    ys = [m[1] for m in mids]
    # Median of main plant (robust to far islands)
    xs_s, ys_s = sorted(xs), sorted(ys)
    med_x = xs_s[len(xs_s) // 2]
    med_y = ys_s[len(ys_s) // 2]

    # Seed: long belt close to median
    def seed_score(item: tuple) -> tuple:
        mx, my, s = item
        L = float(s.get("length_pct") or 0)
        d = math.hypot(mx - med_x, my - med_y)
        return (d / 5000.0 - L * 2.0, d)  # prefer long + near center

    seed = min(mids, key=seed_score)[2]
    selected: list[dict] = [seed]
    selected_names = {str(seed.get("name") or "")}

    while len(selected) < max_conv:
        best = None
        best_d = 1e18
        for mx, my, s in mids:
            name = str(s.get("name") or "")
            if name in selected_names:
                continue
            # distance to nearest already-selected midpoint
            dmin = 1e18
            for s2 in selected:
                g = geom[str(s2.get("name") or "")]
                mx2, my2 = (g[0] + g[2]) / 2, (g[1] + g[3]) / 2
                dmin = min(dmin, math.hypot(mx - mx2, my - my2))
            if dmin < best_d:
                best_d = dmin
                best = s
        if best is None:
            break
        selected.append(best)
        selected_names.add(str(best.get("name") or ""))

    # PEs nearest to any selected belt centerline
    def pe_dist(pe: dict) -> float:
        px, py = _pct_to_plant(
            float(pe.get("x_pct") or 0),
            float(pe.get("y_pct") or 0),
            min_x, max_x, min_y, max_y,
        )
        best = 1e18
        for s in selected:
            g = geom[str(s.get("name") or "")]
            d, _, _ = _dist_point_to_seg(px, py, g[0], g[1], g[2], g[3])
            best = min(best, d)
        return best

    pes_sel = sorted(pes, key=pe_dist)[:max_pe]
    return selected, pes_sel


def select_named_group(
    symbols: dict,
    conveyor_names: list[str],
    *,
    max_pe: int = 12,
    pe_names: list[str] | None = None,
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Select an explicit connected group by conveyor name (e.g. merge P500).

    Returns (convs, pes, missing_names).
    PE selection:
      1) explicit pe_names if given
      2) PE whose name contains a selected conveyor number (442, 500, …)
      3) nearest to selected belt centerlines (fill up to max_pe)
    """
    all_syms = list(symbols.get("symbols") or [])
    by_name = {str(s.get("name") or ""): s for s in all_syms}
    min_x, max_x, min_y, max_y = _plant_spans(symbols)

    missing: list[str] = []
    selected: list[dict] = []
    for n in conveyor_names:
        key = n.strip()
        if not key:
            continue
        # Allow bare numbers → P###
        if re.fullmatch(r"\d+[A-Za-z]?", key):
            key = f"P{key}"
        s = by_name.get(key)
        if not s:
            # case-insensitive
            s = next((v for k, v in by_name.items() if k.upper() == key.upper()), None)
        if not s:
            missing.append(key)
            continue
        if s.get("kind") != "conveyor":
            # still include if it has geometry
            pass
        selected.append(s)

    if not selected:
        return [], [], missing

    # Geometry for PE distance
    geom: dict[str, tuple] = {}
    for s in selected:
        name = str(s.get("name") or "")
        geom[name] = _conv_plant_geom(s, min_x, max_x, min_y, max_y)

    # Numbers embedded in conveyor names for PE matching (442 from P442)
    conv_nums = set()
    for s in selected:
        m = re.search(r"(\d{2,4})", str(s.get("name") or ""))
        if m:
            conv_nums.add(m.group(1))

    pes_all = [s for s in all_syms if s.get("kind") == "photoeye"]
    picked: list[dict] = []
    picked_names: set[str] = set()

    if pe_names:
        for n in pe_names:
            key = n.strip()
            s = by_name.get(key) or next(
                (v for k, v in by_name.items() if k.upper() == key.upper()), None
            )
            if s and str(s.get("name")) not in picked_names:
                picked.append(s)
                picked_names.add(str(s.get("name")))

    # Name-linked PEs (EZPE442_F, PE500_J, PE544_P, …)
    for pe in pes_all:
        pname = str(pe.get("name") or "")
        if pname in picked_names:
            continue
        if any(num in pname for num in conv_nums):
            picked.append(pe)
            picked_names.add(pname)

    def pe_dist(pe: dict) -> float:
        px, py = _pct_to_plant(
            float(pe.get("x_pct") or 0),
            float(pe.get("y_pct") or 0),
            min_x, max_x, min_y, max_y,
        )
        best = 1e18
        for g in geom.values():
            d, _, _ = _dist_point_to_seg(px, py, g[0], g[1], g[2], g[3])
            best = min(best, d)
        return best

    # Fill with nearest if under max_pe
    remain = [p for p in pes_all if str(p.get("name")) not in picked_names]
    remain.sort(key=pe_dist)
    for pe in remain:
        if len(picked) >= max_pe:
            break
        # only if reasonably close to the group
        if pe_dist(pe) > 8000:  # plant units
            continue
        picked.append(pe)
        picked_names.add(str(pe.get("name")))

    picked = picked[:max_pe]
    return selected, picked, missing


def build_memory_tags_import(instances: list[dict]) -> dict:
    """
    Ignition Designer Tag Import JSON.

    Designer 8.x import expects a **JSON object** (one root folder), NOT an array.
    Error if array: "Not a JSON Object: [{...}]".

    Memory tags so colors work without a PLC/device.
    Paths match component tagPath: [default]Site/ZoneN/Conveyors/Pxxx/Run
    """
    # tree[area][bucket][device] = list of atomic members
    tree: dict[str, dict[str, dict[str, list]]] = {}

    for inst in instances:
        kind = inst.get("kind") or "conveyor"
        label = str(inst.get("label") or "")
        safe = _safe_tag_name(label)
        area = _area_for_name(label)
        # Prefer area from tagPath if present
        tp = inst.get("tagPath") or ""
        m = re.match(r"\[default\]Site/([^/]+)/", tp)
        if m:
            area = m.group(1)
        bucket = "Conveyors" if kind == "conveyor" else "Photoeyes"
        area_node = tree.setdefault(area, {})
        buck = area_node.setdefault(bucket, {})
        if kind == "conveyor":
            buck[safe] = [
                {
                    "name": "Run",
                    "tagType": "AtomicTag",
                    "dataType": "Boolean",
                    "valueSource": "memory",
                    "value": False,
                    "tooltip": label,
                },
                {
                    "name": "Fault",
                    "tagType": "AtomicTag",
                    "dataType": "Boolean",
                    "valueSource": "memory",
                    "value": False,
                },
                {
                    "name": "Jam",
                    "tagType": "AtomicTag",
                    "dataType": "Boolean",
                    "valueSource": "memory",
                    "value": False,
                },
            ]
        else:
            buck[safe] = [
                {
                    "name": "Clear",
                    "tagType": "AtomicTag",
                    "dataType": "Boolean",
                    "valueSource": "memory",
                    "value": True,  # default clear (green)
                    "tooltip": label,
                },
                {
                    "name": "Jam",
                    "tagType": "AtomicTag",
                    "dataType": "Boolean",
                    "valueSource": "memory",
                    "value": False,
                },
            ]

    area_folders = []
    for area in sorted(tree.keys()):
        buckets = []
        for bname in sorted(tree[area].keys()):
            devices = []
            for dname in sorted(tree[area][bname].keys()):
                devices.append({
                    "name": dname,
                    "tagType": "Folder",
                    "tags": tree[area][bname][dname],
                })
            buckets.append({"name": bname, "tagType": "Folder", "tags": devices})
        area_folders.append({"name": area, "tagType": "Folder", "tags": buckets})

    # Single root object (Designer import rejects a top-level array)
    return {
        "name": "Site",
        "tagType": "Folder",
        "tags": area_folders,
    }


def instances_from_symbols(
    symbols: dict,
    *,
    max_conv: int = 10,
    max_pe: int = 10,
    canvas_w: int = 1200,
    canvas_h: int = 800,
    margin: int = 48,
    prefer_longest: bool = False,
    cluster: bool = True,
    snap_pe: bool = True,
    fit_selected: bool = True,
    conveyor_names: list[str] | None = None,
    pe_names: list[str] | None = None,
) -> list[dict]:
    """
    Place conveyors/PEs with plant-true geometry.

    conveyor_names: explicit connected group (preferred for calibration).
    cluster=True: nearest-neighbor neighborhood of physical P###.
    """
    all_syms = list(symbols.get("symbols") or [])
    min_x, max_x, min_y, max_y = _plant_spans(symbols)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    missing_names: list[str] = []

    if conveyor_names:
        convs, pes, missing_names = select_named_group(
            symbols,
            conveyor_names,
            max_pe=max_pe,
            pe_names=pe_names,
        )
    elif cluster:
        convs, pes = select_cluster(symbols, max_conv=max_conv, max_pe=max_pe)
    else:
        convs_all = [
            s for s in all_syms
            if s.get("kind") == "conveyor" and _is_physical_p(str(s.get("name") or ""))
        ]
        convs_all = sorted(
            convs_all,
            key=lambda s: (-float(s.get("length_pct") or 0), s.get("name") or ""),
        )
        convs = convs_all[:max_conv]
        pes_all = [s for s in all_syms if s.get("kind") == "photoeye"]

        def pe_score(pe: dict) -> float:
            px, py = float(pe.get("x_pct") or 0), float(pe.get("y_pct") or 0)
            best = 1e9
            for c in convs:
                dx = px - float(c.get("x_pct") or 0)
                dy = py - float(c.get("y_pct") or 0)
                best = min(best, dx * dx + dy * dy)
            return best

        pes = sorted(pes_all, key=pe_score)[:max_pe]

    if not convs and not pes:
        return []

    # Build plant geoms for selected conveyors
    conv_geom: list[tuple[dict, tuple]] = []
    for s in convs:
        g = _conv_plant_geom(s, min_x, max_x, min_y, max_y)
        conv_geom.append((s, g))

    # Bounds for fit: selected only (tight crop) vs full plant
    if fit_selected:
        xs: list[float] = []
        ys: list[float] = []
        for _s, (x0, y0, x1, y1, _L, _a) in conv_geom:
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        for pe in pes:
            px, py = _pct_to_plant(
                float(pe.get("x_pct") or 0),
                float(pe.get("y_pct") or 0),
                min_x, max_x, min_y, max_y,
            )
            xs.append(px)
            ys.append(py)
        fit_min_x, fit_max_x = min(xs), max(xs)
        fit_min_y, fit_max_y = min(ys), max(ys)
        # pad 8%
        pad_x = max((fit_max_x - fit_min_x) * 0.08, 400)
        pad_y = max((fit_max_y - fit_min_y) * 0.08, 400)
        fit_min_x -= pad_x
        fit_max_x += pad_x
        fit_min_y -= pad_y
        fit_max_y += pad_y
    else:
        fit_min_x, fit_max_x, fit_min_y, fit_max_y = min_x, max_x, min_y, max_y

    fit_span_x = max(fit_max_x - fit_min_x, 1.0)
    fit_span_y = max(fit_max_y - fit_min_y, 1.0)

    top_band, bot_band = 36, 32
    usable_w = max(200, canvas_w - margin * 2)
    usable_h = max(200, canvas_h - top_band - bot_band - margin)
    # Fill ~96% of usable canvas so small sites aren't a tiny blob in the middle
    scale = min(usable_w / fit_span_x, usable_h / fit_span_y) * 0.96
    draw_w = fit_span_x * scale
    draw_h = fit_span_y * scale
    ox = margin + (usable_w - draw_w) / 2
    oy = top_band + (usable_h - draw_h) / 2

    def plant_to_screen(px: float, py: float) -> tuple[float, float]:
        sx = ox + (px - fit_min_x) * scale
        sy = oy + (fit_max_y - py) * scale
        return sx, sy

    out: list[dict] = []
    for i, (s, (x0, y0, x1, y1, L, plant_ang)) in enumerate(conv_geom):
        sx0, sy0 = plant_to_screen(x0, y0)
        sx1, sy1 = plant_to_screen(x1, y1)
        length_px = max(36.0, math.hypot(sx1 - sx0, sy1 - sy0))
        screen_ang = math.degrees(math.atan2(sy1 - sy0, sx1 - sx0))
        belt_h = 18  # thick enough to read labels on dense plants
        # Prefer true angle for all belts (cleaner plant geometry).
        # Snap only near-H / near-V to axis-aligned for Designer stability.
        a = abs(screen_ang) % 180.0
        if a < 12 or a > 168:
            w, h = int(round(length_px)), belt_h
            x = int(round(min(sx0, sx1)))
            y = int(round((sy0 + sy1) / 2 - h / 2))
            rotate = 0.0
        elif 78 < a < 102:
            w, h = belt_h, int(round(length_px))
            x = int(round((sx0 + sx1) / 2 - w / 2))
            y = int(round(min(sy0, sy1)))
            rotate = 0.0
        else:
            w, h = int(round(length_px)), belt_h
            pr = math.radians(screen_ang + 90.0)
            x = int(round(sx0 - (belt_h / 2.0) * math.cos(pr)))
            y = int(round(sy0 - (belt_h / 2.0) * math.sin(pr)))
            rotate = round(screen_ang, 2)
        name = s.get("name") or f"C{i}"
        area = _area_for_name(str(name))
        tag_path = (
            (s.get("tags") or {}).get("run")
            or f"[default]Site/{area}/Conveyors/{_safe_tag_name(str(name))}/Run"
        )
        page = s.get("drawing_page") or s.get("print_page")
        out.append({
            "kind": "conveyor",
            "label": name,
            "tagPath": tag_path,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "rotate": rotate,
            "angle": plant_ang,
            "printPage": page,
            "drawing_page": page,
            "plant": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        })
    pe_screen_used: set[tuple[int, int]] = set()
    for i, s in enumerate(pes):
        px, py = _pct_to_plant(
            float(s.get("x_pct") or 0),
            float(s.get("y_pct") or 0),
            min_x, max_x, min_y, max_y,
        )
        # Snap PE onto nearest selected conveyor centerline (lateral only)
        if snap_pe and conv_geom:
            best_d = 1e18
            cx, cy = px, py
            for _cs, g in conv_geom:
                d, qx, qy = _dist_point_to_seg(px, py, g[0], g[1], g[2], g[3])
                if d < best_d:
                    best_d = d
                    cx, cy = qx, qy
            # Only snap if reasonably near a selected belt (avoid flinging orphans)
            if best_d < max(fit_span_x, fit_span_y) * 0.15:
                px, py = cx, cy

        sx, sy = plant_to_screen(px, py)
        # Tiny round PE vs 16px belt thickness
        w = h = 6
        ix, iy = int(round(sx - w / 2)), int(round(sy - h / 2))
        # De-overlap stacked PEs (same snap target)
        key = (ix // 3, iy // 3)
        nudge = 0
        while key in pe_screen_used and nudge < 12:
            nudge += 1
            ix += 5
            iy += 4
            key = (ix // 3, iy // 3)
        pe_screen_used.add(key)

        name = s.get("name") or f"PE{i}"
        tag_path = (s.get("tags") or {}).get("clear") or ""
        if not tag_path:
            pe_area = _area_for_name(str(name))
            tag_path = (
                f"[default]Site/{pe_area}/Photoeyes/{_safe_tag_name(str(name))}/Clear"
            )
        page = s.get("drawing_page") or s.get("print_page")
        out.append({
            "kind": "photoeye",
            "label": name,
            "tagPath": tag_path,
            "x": ix,
            "y": iy,
            "width": w,
            "height": h,
            "rotate": 0,
            "angle": 0,
            "printPage": page,
            "drawing_page": page,
            "plant": {"x": px, "y": py},
            "snapped": bool(snap_pe),
        })

    # Power supplies + beacons — same 6×6 disc size, different colors
    for kind in ("power_supply", "beacon"):
        devices = [s for s in all_syms if s.get("kind") == kind]
        # Cap extras so plant stays readable
        devices = devices[: max(max_pe, 40)]
        for i, s in enumerate(devices):
            px, py = _pct_to_plant(
                float(s.get("x_pct") or 0),
                float(s.get("y_pct") or 0),
                min_x, max_x, min_y, max_y,
            )
            if snap_pe and conv_geom:
                best_d = 1e18
                cx, cy = px, py
                for _cs, g in conv_geom:
                    d, qx, qy = _dist_point_to_seg(px, py, g[0], g[1], g[2], g[3])
                    if d < best_d:
                        best_d = d
                        cx, cy = qx, qy
                if best_d < max(fit_span_x, fit_span_y) * 0.2:
                    # Offset slightly off the belt so PE/PS don't stack
                    px, py = cx + (8 if kind == "beacon" else -8), cy + (8 if kind == "beacon" else -8)

            sx, sy = plant_to_screen(px, py)
            w = h = 6
            ix, iy = int(round(sx - w / 2)), int(round(sy - h / 2))
            name = s.get("name") or f"{kind}_{i}"
            tags = s.get("tags") or {}
            tag_path = tags.get("status") or tags.get("run") or tags.get("clear") or ""
            page = s.get("drawing_page") or s.get("print_page")
            out.append({
                "kind": kind,
                "label": name,
                "tagPath": tag_path,
                "x": ix,
                "y": iy,
                "width": w,
                "height": h,
                "rotate": 0,
                "angle": 0,
                "printPage": page,
                "drawing_page": page,
                "plant": {"x": px, "y": py},
            })
    return out


def default_demo_instances() -> list[dict]:
    """Grid of sample conveyors/PEs when no symbols file is available."""
    out = []
    for i in range(12):
        out.append({
            "kind": "conveyor",
            "label": f"P{100 + i * 2}",
            "tagPath": f"[default]Site/Zone1/Conveyors/P{100 + i * 2}/Run",
            "x": 40 + (i % 4) * 160,
            "y": 55 + (i // 4) * 40,
            "width": 140,
            "height": 10,
            "rotate": 0,
        })
    for i in range(12):
        out.append({
            "kind": "photoeye",
            "label": f"PE{i + 1}",
            "tagPath": f"[default]Site/Zone1/Photoeyes/PE{i + 1}/Clear",
            "x": 40 + (i % 6) * 100,
            "y": 220 + (i // 6) * 48,
            "width": 6,
            "height": 6,
            "rotate": 0,
        })
    return out


def _find_svg_near_symbols(symbols_path: str | Path | None) -> Path | None:
    if not symbols_path:
        return None
    d = Path(symbols_path).resolve().parent
    for name in (
        "layout_conveyors_only.svg",
        "layout.svg",
        "poc_layout.svg",
    ):
        p = d / name
        if p.is_file():
            return p
    return None


def _append_export_history(entry: dict) -> Path:
    """Append one line of export history so progress is auditable over time."""
    hist = REPO_ROOT / "exports" / "ignition-build" / "EXPORT_HISTORY.md"
    hist.parent.mkdir(parents=True, exist_ok=True)
    if not hist.is_file():
        hist.write_text(
            "# FortnaPlus Ignition / Perspective export history\n\n"
            "Each pack/export is logged here so you can track layout iterations.\n\n"
            "| Local time | Folder | Counts | Notes |\n"
            "|---|---|---|---|\n",
            encoding="utf-8",
        )
    line = (
        f"| {entry.get('local_time', '')} "
        f"| `{entry.get('folder', '')}` "
        f"| {entry.get('counts', '')} "
        f"| {entry.get('notes', '')} |\n"
    )
    with hist.open("a", encoding="utf-8") as f:
        f.write(line)
    return hist


def pack_perspective_project(
    out_dir: Path,
    *,
    project_name: str = "FortnaPlus_POC",
    symbols: dict | None = None,
    max_conv: int = 10,
    max_pe: int = 10,
    canvas_w: int = 1200,
    canvas_h: int = 800,
    symbols_source: str = "",
    svg_path: Path | None = None,
    generated_at: datetime | None = None,
    cluster: bool = True,
    with_tags: bool = True,
    embed_svg: bool = False,
    conveyor_names: list[str] | None = None,
    pe_names: list[str] | None = None,
) -> dict:
    """Write project folder + zip for Designer/gateway import."""
    out_dir = Path(out_dir)
    gen = generated_at or _now_local()
    human = _stamp_human(gen)
    stamp = _stamp_folder(gen)
    proj = out_dir / project_name
    views_root = proj / "com.inductiveautomation.perspective" / "views"

    # Components
    _write_view(
        views_root / "FortnaPlus" / "Components" / "Conveyor",
        make_conveyor_component(),
    )
    _write_view(
        views_root / "FortnaPlus" / "Components" / "Photoeye",
        make_photoeye_component(),
    )
    _write_view(
        views_root / "FortnaPlus" / "Components" / "Beacon",
        make_beacon_component(),
    )
    _write_view(
        views_root / "FortnaPlus" / "Components" / "PowerSupply",
        make_power_supply_component(),
    )

    # Default: NO SVG underlay. Huge base64 data: URLs + empty global-props caused
    # Designer to open Plant_Layout as a blank white "no-project" canvas.
    # SVG is still written next to the project for Image component / Media import.
    svg_underlay = _svg_data_url(svg_path) if embed_svg else None

    missing_convs: list[str] = []
    if symbols and (symbols.get("symbols") or []):
        if conveyor_names:
            # resolve missing for report
            _, _, missing_convs = select_named_group(
                symbols, conveyor_names, max_pe=max_pe, pe_names=pe_names
            )
        instances = instances_from_symbols(
            symbols,
            max_conv=max_conv,
            max_pe=max_pe,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            cluster=cluster and not conveyor_names,
            snap_pe=True,
            fit_selected=True,
            conveyor_names=conveyor_names,
            pe_names=pe_names,
        )
        machine = symbols.get("machine") or "Site"
        group_label = "merge group" if conveyor_names else "calibration"
        title = f"FortnaPlus · {machine} · {group_label}"
    else:
        instances = default_demo_instances()
        title = "FortnaPlus · demo layout"

    plant = make_plant_view(
        instances,
        title=title,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        svg_underlay=svg_underlay,
        generated_at=human,
    )

    _write_view(views_root / "FortnaPlus" / "POC" / "Plant_Small", plant)
    _write_view(views_root / "FortnaPlus" / "POC" / "Plant_Layout", plant)

    # Minimal smoke view (2 embeds) — always opens in Designer for folder checks
    smoke_instances = [
        {
            "kind": "conveyor",
            "label": "P500",
            "tagPath": "[default]Site/Zone5/Conveyors/P500/Run",
            "x": 40,
            "y": 120,
            "width": 280,
            "height": 22,
            "printPage": 20,
        },
        {
            "kind": "photoeye",
            "label": "PE500",
            "tagPath": "[default]Site/Zone5/Photoeyes/PE500_J/Clear",
            "x": 40,
            "y": 180,
            "width": 6,
            "height": 6,
            "printPage": 20,
        },
        {
            "kind": "beacon",
            "label": "WB500",
            "tagPath": "",
            "x": 60,
            "y": 180,
            "width": 6,
            "height": 6,
        },
        {
            "kind": "power_supply",
            "label": "PS500",
            "tagPath": "",
            "x": 80,
            "y": 180,
            "width": 6,
            "height": 6,
        },
    ]
    smoke = make_plant_view(
        smoke_instances,
        title="FortnaPlus · SMOKE (if you see cyan bar + green PE, project is OK)",
        canvas_w=900,
        canvas_h=400,
        generated_at=human,
    )
    _write_view(views_root / "FortnaPlus" / "POC" / "Smoke_Test", smoke)

    proj.mkdir(parents=True, exist_ok=True)

    # Memory tags that match component tagPaths (Designer import format = object root)
    tags_import_path = ""
    tags_payload: dict | None = None
    tag_instances: list[dict] = list(instances or [])
    if with_tags:
        # Prefer FULL symbol set for tags (all zone conveyors), not just view embeds.
        # View may be capped for Designer comfort; tags must still list every belt.
        if symbols and (symbols.get("symbols") or []):
            try:
                full_tags = instances_from_symbols(
                    symbols,
                    max_conv=max(int(max_conv), 500),
                    max_pe=max(int(max_pe), 500),
                    canvas_w=canvas_w,
                    canvas_h=canvas_h,
                    cluster=False,
                    snap_pe=False,
                    fit_selected=False,
                )
                if full_tags:
                    tag_instances = full_tags
            except Exception:
                pass
        if tag_instances:
            tags_payload = build_memory_tags_import(tag_instances)
            tags_import_path = str(out_dir / "tags_import.json")
            (out_dir / "tags_import.json").write_text(
                json.dumps(tags_payload, indent=2), encoding="utf-8"
            )
            # Also inside project folder so it travels with the copy
            (proj / "tags_import.json").write_text(
                json.dumps(tags_payload, indent=2), encoding="utf-8"
            )
            # Device map for QA
            device_map = [
                {
                    "kind": i.get("kind"),
                    "label": i.get("label"),
                    "tagPath": i.get("tagPath"),
                    "x": i.get("x"),
                    "y": i.get("y"),
                    "rotate": i.get("rotate"),
                }
                for i in tag_instances
            ]
            (out_dir / "DEVICE_MAP.json").write_text(
                json.dumps(device_map, indent=2), encoding="utf-8"
            )

    n_tag_conv = sum(1 for i in tag_instances if i.get("kind") == "conveyor")
    n_view_conv = sum(1 for i in instances if i.get("kind") == "conveyor")
    # Minimal project.json — long titles/descriptions have contributed to Designer
    # design-surface failures ("no-project") on some gateways.
    (proj / "project.json").write_text(
        json.dumps(
            {
                "title": project_name,
                "description": f"FortnaPlus layout · {n_view_conv} conv · {human}",
                "parent": "",
                "enabled": True,
                "inheritable": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Never ship ReadOnly trees (OneDrive / robocopy often set this).
    _clear_readonly_tree(proj)

    gp = proj / "ignition" / "global-props"
    gp.mkdir(parents=True, exist_ok=True)
    (gp / "resource.json").write_text(
        json.dumps(
            {
                "scope": "A",
                "version": 1,
                "restricted": False,
                "overridable": True,
                "files": ["data.bin"],
                "attributes": {
                    "lastModification": {
                        "actor": "FortnaPlus",
                        "timestamp": _ts_utc(),
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Empty data.bin breaks Designer (white canvas shows "no-project").
    # Prefer a real GlobalProps blob from a known-good Ignition project.
    _ensure_global_props_bin(gp / "data.bin")
    _clear_readonly_tree(proj)

    counts = {
        "conveyors": sum(1 for i in instances if i.get("kind") == "conveyor"),
        "photoeyes": sum(1 for i in instances if i.get("kind") == "photoeye"),
        "total": len(instances),
    }
    device_names = [str(i.get("label") or "") for i in instances]

    # Export metadata (audit trail per pack folder)
    meta = {
        "generated_local": human,
        "generated_utc": _ts_utc(),
        "folder_stamp": stamp,
        "project_name": project_name,
        "instance_counts": counts,
        "device_names": device_names,
        "requested_conveyors": conveyor_names or [],
        "missing_conveyors": missing_convs,
        "canvas": {"width": canvas_w, "height": canvas_h},
        "symbols_source": symbols_source or "",
        "cluster": cluster and not conveyor_names,
        "tags_import": tags_import_path,
        "svg_embedded": bool(svg_underlay),
        "layout_notes": (
            "Named connected group or tight P### cluster; "
            "axis-aligned H/V belts; PE snapped to centerline; "
            "Memory tags_import.json matches component tagPaths."
        ),
    }
    (out_dir / "EXPORT_META.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    readme = out_dir / "IMPORT_TO_IGNITION.md"
    readme.write_text(
        f"""# Import FortnaPlus Perspective project + tags

**Generated (local):** `{human}`  
**Folder stamp:** `{stamp}`  
**Project:** `{project_name}`  
**Devices:** {counts['conveyors']} conveyors + {counts['photoeyes']} photoeyes

## Why tags need a one-click import

Ignition keeps tags in the **gateway tag provider**, not inside the project folder.
Copying `FortnaPlus_POC` alone will never create tags. This pack includes
`tags_import.json` (Memory tags) that match every component `tagPath`.

## Steps

1. **Copy project**  
   Copy `{project_name}/` →  
   `C:\\\\Program Files\\\\Inductive Automation\\\\Ignition\\\\data\\\\projects\\\\`

2. **Scan**  
   Gateway → Platform → System → Projects → **Scan Filesystem**

3. **Import tags** (required for green/cyan live colors)  
   Designer → Tag Browser → provider **default** → right-click root →  
   **Import Tags** → select:

   ```
   {tags_import_path or "tags_import.json (next to FortnaPlus_POC)"}
   ```

   Format is a single JSON **object** (root folder `Site`) with `valueSource: memory`.
   No PLC / OPC device required.

4. **Open view**  
   Views → **FortnaPlus / POC / Plant_Layout**

5. **Test**  
   Tag Browser → flip `Site/.../Run` or `.../Clear` → component color should change.

## Devices in this pack

{chr(10).join(f"- `{n}`" for n in device_names)}

## Files

| File | Purpose |
|------|---------|
| `{project_name}/` | Perspective project (copy to data/projects) |
| `tags_import.json` | Memory tags for Import Tags |
| `DEVICE_MAP.json` | label ↔ tagPath ↔ x/y audit |
| `EXPORT_META.json` | timestamp + counts |
""",
        encoding="utf-8",
    )

    zip_path = out_dir / f"{project_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in proj.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=str(Path(project_name) / f.relative_to(proj)))

    return {
        "ok": True,
        "project_dir": str(proj),
        "zip": str(zip_path),
        "readme": str(readme),
        "generated_local": human,
        "generated_utc": meta["generated_utc"],
        "folder_stamp": stamp,
        "views": [
            "FortnaPlus/Components/Conveyor",
            "FortnaPlus/Components/Photoeye",
            "FortnaPlus/POC/Plant_Small",
            "FortnaPlus/POC/Plant_Layout",
        ],
        "instances": instances,
        "instance_counts": counts,
        "device_names": device_names,
        "requested_conveyors": conveyor_names or [],
        "missing_conveyors": missing_convs,
        "canvas": {"width": canvas_w, "height": canvas_h},
        "tags_import": tags_import_path,
        "svg_underlay": str(svg_path) if (embed_svg and svg_path) else "",
        "svg_embedded": bool(svg_underlay),
        "export_meta": str(out_dir / "EXPORT_META.json"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack FortnaPlus Perspective components for Ignition")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="Write project folder + zip")
    p.add_argument("--out-dir", default="")
    p.add_argument("--project-name", default="FortnaPlus_POC")
    p.add_argument("--symbols", default="", help="Optional hmi_symbols.json / hmi_symbols_poc.json")
    p.add_argument("--use-active-poc", action="store_true", help="Use latest *-POC export symbols")
    p.add_argument(
        "--use-latest-symbols",
        action="store_true",
        help="Prefer latest full hmi_symbols.json from exports/ignition-build (fallback POC)",
    )
    p.add_argument("--max-conv", type=int, default=10)
    p.add_argument("--max-pe", type=int, default=10)
    p.add_argument("--canvas-w", type=int, default=1200)
    p.add_argument("--canvas-h", type=int, default=800)
    p.add_argument("--svg", default="", help="Optional layout SVG path (only with --embed-svg)")
    p.add_argument("--cluster", action="store_true", help="Tight physical-P### neighborhood")
    p.add_argument("--no-cluster", action="store_true", help="Disable cluster selection")
    p.add_argument("--with-tags", action="store_true", help="Write tags_import.json Memory tags")
    p.add_argument("--no-tags", action="store_true", help="Skip tags_import.json")
    p.add_argument("--embed-svg", action="store_true", help="Embed full-plant SVG underlay")
    p.add_argument("--prefer-longest", action="store_true", help="Legacy longest-first")
    p.add_argument(
        "--conveyors",
        default="",
        help="Comma-separated conveyor names for a connected group "
        "(e.g. P542,P544,P442,P444,P500,P440). P522 not in RUN → use P544.",
    )
    p.add_argument(
        "--photoeyes",
        default="",
        help="Optional comma-separated PE names (default: name-match + nearest)",
    )
    args = ap.parse_args()
    try:
        if args.cmd == "pack":
            gen = _now_local()
            stamp = _stamp_folder(gen)
            human = _stamp_human(gen)
            out = Path(args.out_dir) if args.out_dir else (
                REPO_ROOT / "exports" / "ignition-build" / f"{stamp}-perspective-pack"
            )
            out.mkdir(parents=True, exist_ok=True)
            symbols = None
            symbols_src = ""
            if args.symbols and Path(args.symbols).is_file():
                symbols = json.loads(Path(args.symbols).read_text(encoding="utf-8"))
                symbols_src = str(Path(args.symbols).resolve())
            elif args.use_latest_symbols or args.use_active_poc:
                base = REPO_ROOT / "exports" / "ignition-build"
                full_syms: list[Path] = []
                poc_syms: list[Path] = []
                if base.is_dir():
                    for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                        if not d.is_dir() or "perspective" in d.name.lower():
                            continue
                        full = d / "hmi_symbols.json"
                        poc = d / "hmi_symbols_poc.json"
                        if full.is_file() and "POC" not in d.name:
                            full_syms.append(full)
                        if poc.is_file():
                            poc_syms.append(poc)
                        if full.is_file() and "POC" in d.name:
                            poc_syms.append(full)
                if args.use_active_poc and not args.use_latest_symbols:
                    candidates = poc_syms + full_syms
                else:
                    candidates = full_syms + poc_syms
                if candidates:
                    symbols = json.loads(candidates[0].read_text(encoding="utf-8"))
                    symbols_src = str(candidates[0].resolve())

            svg_path = Path(args.svg) if args.svg else _find_svg_near_symbols(symbols_src)
            # Defaults: cluster + tags ON unless explicitly disabled
            use_cluster = not args.no_cluster
            use_tags = not args.no_tags
            conv_names = [x.strip() for x in (args.conveyors or "").split(",") if x.strip()]
            pe_names = [x.strip() for x in (args.photoeyes or "").split(",") if x.strip()]
            result = pack_perspective_project(
                out,
                project_name=args.project_name,
                symbols=symbols,
                max_conv=args.max_conv,
                max_pe=args.max_pe,
                canvas_w=args.canvas_w,
                canvas_h=args.canvas_h,
                symbols_source=symbols_src,
                svg_path=svg_path,
                generated_at=gen,
                cluster=use_cluster and not conv_names,
                with_tags=use_tags,
                embed_svg=bool(args.embed_svg),
                conveyor_names=conv_names or None,
                pe_names=pe_names or None,
            )
            result["out_dir"] = str(out)
            result["symbols_source"] = symbols_src

            copy_txt = out / "COPY_TO_IGNITION.txt"
            proj_dir = result.get("project_dir") or ""
            ign_dest = "C:\\Program Files\\Inductive Automation\\Ignition\\data\\projects\\"
            counts = result.get("instance_counts") or {}
            names = result.get("device_names") or []
            copy_txt.write_text(
                "\n".join([
                    "FortnaPlus -> Ignition project pack (10+10 calibration)",
                    "=" * 50,
                    f"Generated (local): {human}",
                    f"Generated (UTC):   {result.get('generated_utc')}",
                    f"Folder stamp:      {stamp}",
                    "",
                    "Project folder to copy:",
                    f"  {proj_dir}",
                    "",
                    "1) Copy FortnaPlus_POC to:",
                    f"  {ign_dest}",
                    "",
                    "2) Gateway -> Platform -> System -> Projects -> Scan Filesystem",
                    "",
                    "3) IMPORT TAGS (required — projects do not auto-load tags):",
                    "   Designer Tag Browser -> default provider -> right-click -> Import Tags",
                    f"   File: {result.get('tags_import') or str(out / 'tags_import.json')}",
                    "   Memory tags (no PLC). Toggle Run/Clear to test component colors.",
                    "",
                    "4) Designer -> Open FortnaPlus_POC",
                    "   Views -> FortnaPlus -> POC -> Plant_Layout",
                    "",
                    f"Devices: {', '.join(names)}",
                    f"Counts: {json.dumps(counts)}",
                    f"Zip: {result.get('zip')}",
                    f"Meta: {result.get('export_meta')}",
                    "",
                ]),
                encoding="utf-8",
            )
            result["copy_instructions"] = str(copy_txt)

            hist = _append_export_history({
                "local_time": human,
                "folder": out.name,
                "counts": f"{counts.get('conveyors', 0)}c/{counts.get('photoeyes', 0)}pe",
                "notes": (
                    f"cluster={use_cluster}; tags={'yes' if use_tags else 'no'}; "
                    f"src={Path(symbols_src).name if symbols_src else 'demo'}"
                ),
            })
            result["export_history"] = str(hist)

            slim = {k: v for k, v in result.items() if k != "instances"}
            slim["instance_sample"] = (result.get("instances") or [])[:4]
            print(json.dumps(slim, separators=(",", ":")))
            return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
