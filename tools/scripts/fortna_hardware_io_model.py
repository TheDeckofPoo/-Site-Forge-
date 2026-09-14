#!/usr/bin/env python3
"""Hardware / I/O workspace model — thin wrapper over PhysicalWordResolver.

The graphical Hardware view MUST consume this tree (or PhysicalWordResolver
directly). Do NOT rediscover adapters/modules/slots/channels independently.
If Hardware UI and IO_MAP disagree, that is a model defect — fix the resolver.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_hardware_io_overrides import (  # noqa: E402
    apply_overrides_to_hardware_model,
    load_overrides,
)
from fortna_io_extract import extract_io_points, read_project_meta  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402


def _module_channel_capacity(mod_type: str, connection: str = "") -> int:
    """Digital channel capacity from catalog type (same bounds as resolver bits)."""
    u = (mod_type or "").upper()
    conn = (connection or "").upper()
    if conn == "HEADNODE" or "AENT" in u:
        return 0
    if any(x in u for x in ("OA8", "OB8", "IA8", "IB8")):
        return 8
    if any(x in u for x in ("IA16", "IB16", "OB16", "OW16", "OA16")):
        return 16
    if any(x in u for x in ("IA4", "IB4", "OA4", "OB4")):
        return 4
    # Unknown bridged card — capacity unknown; UI shows used only
    return 0


def _logical_by_channel(resolver: PhysicalWordResolver) -> dict[str, dict[str, Any]]:
    """Map physical channel → proven logical endpoint from Conveyor.asc (no invented names)."""
    out: dict[str, dict[str, Any]] = {}
    try:
        points = extract_io_points(resolver.run_dir)
    except Exception:
        points = []
    for p in points:
        word = p.get("fortna_bank")
        bit = p.get("fortna_bit")
        if word in (None, "") or bit in (None, ""):
            continue
        hit = resolver.resolve(word, bit)
        if not hit:
            continue
        ch = (hit.get("channel") or "").strip()
        if not ch:
            continue
        name = (p.get("fortna_name") or p.get("io_name") or p.get("tag") or "").strip()
        if not name:
            continue
        # First proven name wins; do not invent or overwrite with weaker aliases
        if ch not in out:
            out[ch] = {
                "name": name,
                "tag": (p.get("tag") or "").strip() or None,
                "device_class": p.get("device_class"),
                "equipment_kind": p.get("equipment_kind"),
                "fortna_address": p.get("fortna_address"),
                "source_table": p.get("source_table") or "FORTNA/Conveyor.asc",
            }
    return out


def _channels_for_module(
    by_word_bit: dict[str, dict[str, Any]],
    *,
    rio_name: str,
    data_index: int | None,
    direction: str,
    logical_by_ch: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Channels from by_word_bit filtered by rio_name + data_index (flex_slot) + direction."""
    if data_index is None or not direction:
        return []
    want_rio = (rio_name or "").strip()
    want_dir = (direction or "").strip().upper()
    rows: list[dict[str, Any]] = []
    for key, hit in (by_word_bit or {}).items():
        if (hit.get("rio_name") or "").strip() != want_rio:
            continue
        if (hit.get("direction") or "").strip().upper() != want_dir:
            continue
        flex = hit.get("flex_slot")
        if flex is None:
            flex = hit.get("data_index")
        try:
            if int(flex) != int(data_index):
                continue
        except (TypeError, ValueError):
            continue
        parts = str(key).split(":", 1)
        try:
            fortna_word = int(parts[0])
            fortna_bit = int(parts[1]) if len(parts) > 1 else int(hit.get("bit") or 0)
        except (TypeError, ValueError):
            fortna_word = hit.get("octal_word")
            fortna_bit = hit.get("bit")
        physical_address = hit.get("channel")  # same string IO_MAP uses
        logical = logical_by_ch.get(physical_address) if physical_address else None
        rows.append(
            {
                "fortna_word": fortna_word,
                "fortna_bit": fortna_bit,
                "word_bit_key": key,
                "physical_address": physical_address,
                "direction": hit.get("direction"),
                "bit_half": hit.get("bit_half"),
                "logical_endpoint": logical,
                "provenance": hit.get("provenance"),
                "assign_how": hit.get("assign_how"),
                "resolve_how": hit.get("resolve_how"),
                "panel": hit.get("panel"),
                "module_name": hit.get("module_name"),
                "type": hit.get("type"),
            }
        )
    rows.sort(
        key=lambda r: (
            int(r.get("fortna_word") or 0),
            int(r.get("fortna_bit") or 0),
        )
    )
    return rows


def build_hardware_io_model(run_dir: Path | str, machine: str = "") -> dict[str, Any]:
    """Build Hardware/I/O JSON tree exclusively from PhysicalWordResolver."""
    run_dir = Path(run_dir)
    mach = (machine or "").strip()
    if not mach:
        try:
            mach = (read_project_meta(run_dir).get("machine_name") or "").strip()
        except Exception:
            mach = ""

    resolver = PhysicalWordResolver(run_dir, mach)
    pm = resolver.physical_map
    topo = resolver.topology
    panel_order = list(topo.get("panel_order") or [])
    by_word_bit = dict(pm.get("by_word_bit") or {})
    logical_by_ch = _logical_by_channel(resolver)

    adapters_out: list[dict[str, Any]] = []
    adapters_by_panel: dict[str, list[dict[str, Any]]] = {p: [] for p in panel_order}

    for ad in pm.get("adapters") or []:
        rio = ad.get("rio_name") or ""
        panel = ad.get("panel")
        modules_out: list[dict[str, Any]] = []
        for mod in sorted(ad.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
            mtype = mod.get("type") or ""
            conn = mod.get("connection") or ""
            direction = mod.get("direction") or ""
            data_index = mod.get("data_index")
            is_head = (conn or "").upper() == "HEADNODE" or "AENT" in (mtype or "").upper()
            channels = []
            if not is_head and direction:
                channels = _channels_for_module(
                    by_word_bit,
                    rio_name=rio,
                    data_index=data_index,
                    direction=direction,
                    logical_by_ch=logical_by_ch,
                )
            capacity = _module_channel_capacity(mtype, conn)
            used = len(channels)
            unresolved_ch = sum(1 for c in channels if not c.get("logical_endpoint"))
            modules_out.append(
                {
                    "slot": mod.get("slot"),
                    "name": mod.get("name") or "",
                    "type": mtype,
                    "catalog": mtype,
                    "direction": direction,
                    "connection": conn,
                    "family": mod.get("family"),
                    "data_index": data_index,
                    "is_adapter_card": bool(is_head),
                    "channel_capacity": capacity,
                    "channels_used": used,
                    "channels_unresolved": unresolved_ch,
                    "channels": channels,
                }
            )
        adapter_tree = {
            "rio_name": rio,
            "eipcfg_name": ad.get("name") or "",
            "name": ad.get("name") or "",
            "targetip": ad.get("targetip") or "",
            "naming_how": ad.get("naming_how"),
            "panel": panel,
            "input_address": ad.get("input_address"),
            "output_address": ad.get("output_address"),
            "adapter_index": ad.get("adapter_index"),
            "modules": modules_out,
        }
        adapters_out.append(adapter_tree)
        if panel and panel in adapters_by_panel:
            adapters_by_panel[panel].append(adapter_tree)
        elif panel:
            adapters_by_panel.setdefault(panel, []).append(adapter_tree)

    model = {
        "ok": True,
        "controller": {
            "machine": pm.get("machine") or mach,
            "eipcfg_path": pm.get("eipcfg_path") or topo.get("eipcfg_path"),
            "data_index_scheme": pm.get("data_index_scheme") or topo.get("data_index_scheme"),
        },
        "control_panels": {
            # Configio Desc evidence only — UI adds "All Panels"; never invent CPs
            "panels": panel_order,
            "all_panels_label": "All Panels",
            "adapters_by_panel": adapters_by_panel,
        },
        "adapters": adapters_out,
        "unresolved_words": list(pm.get("unresolved") or []),
        "stats": dict(pm.get("stats") or {}),
        "io_word_map": resolver.io_word_map(),
        "provenance": {
            "source": "PhysicalWordResolver",
            "source_tables": ["Configio.asc", "eipcfg", "Conveyor.asc"],
            "configio_row_count": topo.get("configio_row_count"),
            "panel_order": panel_order,
        },
    }
    # Engineer overrides (name / Generate) — do not wipe RUN evidence
    try:
        apply_overrides_to_hardware_model(model, load_overrides())
    except Exception:
        pass
    return model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hardware/I/O model from PhysicalWordResolver")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--save-override",
        action="store_true",
        help="Upsert one channel override from --address / --name / --generate",
    )
    ap.add_argument("--address", default="", help="physical_address for --save-override")
    ap.add_argument("--name", default=None, help="engineer logical name (empty clears)")
    ap.add_argument("--source-name", default="", help="RUN-discovered source name")
    ap.add_argument("--generate", default=None, help="true/false — include in IO_MAP")
    ap.add_argument("--clear-overrides", action="store_true", help="Wipe engineer overrides")
    ap.add_argument("--project-identity", default="", help="JSON identity stamp")
    args = ap.parse_args(argv)

    if args.clear_overrides:
        from fortna_hardware_io_overrides import clear_overrides, empty_overrides, save_overrides

        clear_overrides()
        ident = {}
        if args.project_identity:
            try:
                ident = json.loads(args.project_identity)
            except Exception:
                ident = {}
        save_overrides(empty_overrides(ident))
        print(json.dumps({"ok": True, "cleared": True}))
        return 0

    if args.save_override:
        from fortna_hardware_io_overrides import (
            load_overrides,
            save_overrides,
            upsert_channel_override,
            validate_logical_name,
        )

        ov = load_overrides()
        if args.project_identity:
            try:
                ov["projectIdentity"] = json.loads(args.project_identity)
            except Exception:
                pass
        gen = None
        if args.generate is not None and str(args.generate).strip() != "":
            gen = str(args.generate).strip().lower() in ("1", "true", "yes", "y")
        name = args.name
        clear_eng = False
        if name is not None:
            ok, err = validate_logical_name(name)
            if not ok:
                print(json.dumps({"ok": False, "error": err}))
                return 1
            if not str(name).strip():
                clear_eng = True
                name = ""
        try:
            cur = upsert_channel_override(
                ov,
                physical_address=args.address,
                source_name=args.source_name or "",
                engineer_name=None if clear_eng else name,
                generate=gen,
                clear_engineer=clear_eng,
            )
            save_overrides(ov)
            print(json.dumps({"ok": True, "override": cur, "address": args.address}))
            return 0
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1

    run_dir = args.run_dir
    if run_dir is None:
        for cand in (
            REPO_ROOT / "workspace" / "active" / "RUN",
            REPO_ROOT / "workspace" / "active_work" / "RUN",
        ):
            if (cand / "project.cfg").is_file():
                run_dir = cand
                break
    if run_dir is None or not Path(run_dir).exists():
        err = {"ok": False, "error": "No RUN directory (pass --run-dir or load active RUN)"}
        print(json.dumps(err))
        return 1

    try:
        model = build_hardware_io_model(run_dir, args.machine)
    except Exception as e:
        err = {"ok": False, "error": str(e)}
        print(json.dumps(err))
        return 1

    text = json.dumps(model, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
