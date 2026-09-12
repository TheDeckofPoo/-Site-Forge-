#!/usr/bin/env python3
"""CP2 Demo Closure — CURRENT-RUN evidence pack for Greensboro ORNCCP2.

Philosophy (docs/SOURCE_OF_TRUTH_POLICY.md):
  CURRENT RUN = generation source truth.
  FINISHED PLC = validation observation only — never a repair target.
  Do not seed workbook / areas / ES / PE roles from finished PLC.

Usage:
  python tools/scripts/fortna_cp2_demo_closure.py \\
    --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-demo-closure
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_autogen import (  # noqa: E402
    CONVEYOR_ASC_TYPES,
    DEFAULT_LIBRARY,
    FORTNA_TYPE_TO_AUTOGEN,
    _classify_pe_role,
    _link_pe_to_conveyor,
    load_from_run,
)
from fortna_cp2_ownership import classify_ownership, write_classification  # noqa: E402
from fortna_io_extract import read_project_meta  # noqa: E402
from fortna_l5x_compare import extract_l5x  # noqa: E402
from fortna_physical_overlap_audit import OVERLAP_CLASSES, audit as overlap_audit  # noqa: E402
from fortna_run_geometry_investigate import _clean, _is_mech_conveyor  # noqa: E402
from fortna_run_physical_layout import build_transport_graph  # noqa: E402
from fortna_workbook import DEFAULT_WORKBOOK_PATH, load_workbook  # noqa: E402

# Finished PLC AOI counts — validation observation only (not generation targets).
FINISHED_FULL_PE_OBS = 7
FINISHED_PE_LOGIC_OBS = 30

PLACEHOLDER_AREA_RE = re.compile(
    r"^(ORNCCP\d+_Area|Zone\d+_Area|.+_Imported_Area)$", re.I
)
PLACEHOLDER_ES_RE = re.compile(
    r"^(ORNCCP\d+_ESZone\d*|ORNCCP\d+_Imported_ESZone\d*|Zone\d+_ESZone\d*|.+_Imported_ESZone\d*)$",
    re.I,
)
ENGINEER_AREA_MARKERS = frozenset(
    {"ENGINEER CONFIGURATION REQUIRED", "AREA REQUIRED", "UNKNOWN", "N/A", ""}
)
ENGINEER_ES_MARKERS = frozenset(
    {"ENGINEER CONFIGURATION REQUIRED", "ES ZONE REQUIRED", "UNKNOWN", "N/A", ""}
)

PE_CALL_RE = {
    "Full_PE": re.compile(r"\bFull_PE\(([^)]*)\)"),
    "PE_Logic": re.compile(r"\bPE_Logic\(([^)]*)\)"),
}
CONV_FROM_UDT = re.compile(r"^(P\d+[A-Za-z0-9]*)_Conv$", re.I)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def _run_py(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def ensure_active_run(run_dir: Path, machine: str) -> Path:
    """Restore workspace/active/RUN from inbox tar when project.cfg is missing."""
    run_dir = _normalize_run_dir(run_dir)
    if (run_dir / "project.cfg").is_file() and (run_dir / "FORTNA" / "Conveyor.asc").is_file():
        return run_dir

    inbox = ROOT / "workspace" / "inbox"
    patterns = [
        f"*{machine}*RUN*.tar.gz",
        f"*{machine}*.tar.gz",
        "*ORNCCP2*RUN*.tar.gz",
    ]
    tars: list[Path] = []
    for pat in patterns:
        tars.extend(sorted(inbox.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True))
    seen: set[Path] = set()
    uniq: list[Path] = []
    for t in tars:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    if not uniq:
        raise FileNotFoundError(
            f"Active RUN missing at {run_dir} and no matching inbox tar under {inbox}"
        )

    dest_parent = ROOT / "workspace" / "active"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / "RUN"
    print(f"[closure] Restoring RUN from {uniq[0].name} → {dest}")
    if dest.exists():
        # Only wipe when unusable
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(uniq[0], "r:gz") as tf:
        tf.extractall(dest_parent)
    # Some tars extract as active/RUN already; others as active/<bundle>/RUN
    if (dest / "project.cfg").is_file():
        return dest
    for cand in dest_parent.rglob("project.cfg"):
        if cand.parent.name.upper() == "RUN" or (cand.parent / "FORTNA").is_dir():
            if cand.parent.resolve() != dest.resolve():
                if dest.exists():
                    import shutil

                    shutil.rmtree(dest)
                cand.parent.rename(dest)
            return dest
    raise FileNotFoundError(f"Extracted {uniq[0]} but project.cfg not found under {dest_parent}")


def _find_generated_l5x(generated_dir: Path) -> Path | None:
    if not generated_dir.is_dir():
        return None
    preferred = list(generated_dir.glob("OReillyGreensboro_ORNCCP2.L5X"))
    if preferred:
        return preferred[0]
    cands = [
        p
        for p in generated_dir.glob("*.L5X")
        if "Library" not in p.name and "AOI" not in p.name
    ]
    return cands[0] if cands else None


def _latest_gate_l5x() -> Path | None:
    gate = ROOT / "exports" / "cp2-gate" / "generated"
    return _find_generated_l5x(gate)


def _is_placeholder_area(name: str) -> bool:
    n = (name or "").strip()
    if not n or n.upper() in ENGINEER_AREA_MARKERS:
        return True
    if "IMPORTED" in n.upper():
        return True
    return bool(PLACEHOLDER_AREA_RE.match(n))


def _is_placeholder_es(name: str) -> bool:
    n = (name or "").strip()
    if not n or n.upper() in ENGINEER_ES_MARKERS:
        return True
    if "IMPORTED" in n.upper():
        return True
    return bool(PLACEHOLDER_ES_RE.match(n))


def _conv_from_udt(token: str) -> str:
    t = (token or "").strip()
    m = CONV_FROM_UDT.match(t)
    if m:
        body = m.group(1)
        return "P" + body[1:]
    if re.match(r"^P\d+[A-Za-z0-9]*$", t, re.I):
        return "P" + t[1:]
    return t


def _site_forge_supported(asc_type: str) -> bool:
    typ = (asc_type or "").strip().upper()
    if not typ:
        return False
    # Mechanical conveyors Site Forge Autogen currently emits Fast_Conv for.
    if typ in FORTNA_TYPE_TO_AUTOGEN:
        return True
    if typ in CONVEYOR_ASC_TYPES:
        return True
    if typ in {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}:
        return True
    return False


def _unsupported_reason(asc_type: str) -> str:
    typ = (asc_type or "").strip().upper()
    if typ in {"MERGE"}:
        return (
            f"ASC type {typ} maps to Transport Fast_Conv scaffold only; "
            "dedicated Merge_2to1 / multi-lane PLC pattern not auto-realized from RUN"
        )
    if typ in {"SAWTOOTH", "SORTER", "PUSHER", "TRANSFER"}:
        return f"ASC type {typ} — GENERATION NOT YET SUPPORTED"
    if not typ:
        return "Missing ASC Type — GENERATION NOT YET SUPPORTED"
    if not _site_forge_supported(typ):
        return f"ASC type {typ} — GENERATION NOT YET SUPPORTED"
    return f"ASC type {typ} unsupported"


# ---------------------------------------------------------------------------
# Workbook + generate
# ---------------------------------------------------------------------------

def _merge_existing_source() -> dict | None:
    """Prefer workspace workbook; fall back to cp2-gate workbook when cleared."""
    wb = load_workbook(DEFAULT_WORKBOOK_PATH)
    if wb and (wb.get("conveyors") or []):
        return wb
    gate_wb = ROOT / "exports" / "cp2-gate" / "autogen_workbook.json"
    if gate_wb.is_file():
        try:
            data = json.loads(gate_wb.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if data and (data.get("conveyors") or []):
            print(f"[closure] merge-existing from {_rel(gate_wb)} (workspace workbook empty)")
            return data
    return wb


def build_workbook(run_dir: Path, out_dir: Path) -> tuple[Path, dict]:
    from fortna_workbook import build_workbook_from_run, save_workbook

    existing = _merge_existing_source()
    wb = build_workbook_from_run(run_dir, existing=existing)
    wb_out = out_dir / "autogen_workbook.json"
    save_workbook(wb, wb_out)
    return wb_out, wb


def generate_l5x(run_dir: Path, workbook: Path, out_dir: Path) -> tuple[Path, dict, dict]:
    gen_dir = out_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    lib = Path(DEFAULT_LIBRARY)
    if not lib.is_file():
        lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    cp = _run_py(
        [
            str(SCRIPTS / "fortna_autogen.py"),
            "from-run",
            "--run-dir",
            str(run_dir),
            "--workbook",
            str(workbook),
            "--library",
            str(lib),
            "--out-dir",
            str(gen_dir),
        ]
    )
    result: dict = {}
    for line in (cp.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"ok"' in line:
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
    report_path = gen_dir / "autogen_report.json"
    if cp.returncode != 0 and not report_path.is_file():
        raise RuntimeError(
            f"autogen failed (rc={cp.returncode}): {(cp.stderr or cp.stdout or '')[-2000:]}"
        )
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    result_path = gen_dir / "autogen_result.json"
    if result_path.is_file() and not result:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    return gen_dir, report, result


# ---------------------------------------------------------------------------
# 1. run_realization
# ---------------------------------------------------------------------------

def _mech_by_tag(run_dir: Path) -> dict[str, dict]:
    _h, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    out: dict[str, dict] = {}
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        name = _clean(r.get("IO_Name")).upper()
        if not name or name in out:
            continue
        out[name] = {
            "tag": name,
            "type": _clean(r.get("Type")).upper(),
            "machine_name": _clean(r.get("Machine_Name")),
            "row": r,
        }
    return out


def build_run_realization(
    run_dir: Path,
    machine: str,
    ownership: dict,
    workbook: dict,
    gen_l5x: Path | None,
    layout: dict | None,
) -> dict:
    mech = _mech_by_tag(run_dir)
    inp = load_from_run(run_dir)
    autogen_tags = {
        (c.conveyor or "").strip().upper()
        for c in (inp.conveyors or [])
        if (c.conveyor or "").strip()
    }
    oc_by = {
        (c.get("conveyor_tag") or "").upper(): c
        for c in (ownership.get("classifications") or [])
    }
    confirmed = set(ownership.get("by_class", {}).get("CP2_CONFIRMED") or [])
    candidate = set(ownership.get("by_class", {}).get("CP2_CANDIDATE") or [])
    relevant = sorted((autogen_tags | confirmed | candidate) & set(mech.keys()))

    wb_by = {
        (r.get("conveyor") or "").strip().upper(): r
        for r in (workbook.get("conveyors") or [])
        if (r.get("conveyor") or "").strip()
    }

    generated_fast: set[str] = set()
    if gen_l5x and gen_l5x.is_file():
        inv = extract_l5x(gen_l5x)
        generated_fast = {k.upper() for k in (inv.fast_conv or {})}

    items: list[dict] = []
    supported_n = 0

    for tag in relevant:
        info = mech[tag]
        asc_type = info["type"]
        oc = oc_by.get(tag) or {}
        oclass = oc.get("class") or "UNKNOWN"
        wb = wb_by.get(tag) or {}
        included = bool(wb.get("include", tag in autogen_tags))
        in_autogen = tag in autogen_tags
        in_generated = tag in generated_fast
        supported = _site_forge_supported(asc_type)
        if supported:
            supported_n += 1

        status = ""
        reason = ""

        if oclass == "NOT_CP2":
            status = "ignored"
            reason = (
                f"Ownership NOT_CP2 (controllers={oc.get('controller_owners')}); "
                "not in CP2 generation scope"
            )
        elif not supported:
            status = "unsupported"
            reason = _unsupported_reason(asc_type)
        elif oclass == "UNKNOWN" and not in_autogen:
            status = "ignored"
            reason = "Ownership UNKNOWN and not Autogen-scoped — no CP2 device evidence"
        elif oclass == "CP2_CANDIDATE":
            status = "engineer_confirmation_required"
            reason = (
                "CP2_CANDIDATE ownership (cross-controller device evidence) — "
                "engineer must confirm CP2 scope before treating as realized"
            )
        elif in_generated and oclass == "CP2_CONFIRMED":
            # Realized in L5X from RUN; still may need engineer topology/area later
            # but mechanical Fast_Conv realization itself succeeded.
            needs: list[str] = []
            if _is_placeholder_area(str(wb.get("main_area") or "")):
                needs.append("area")
            if _is_placeholder_es(str(wb.get("safety_zone") or "")):
                needs.append("es_zone")
            if not (wb.get("downstream") or "").strip():
                needs.append("topology/downstream")
            if needs:
                status = "engineer_confirmation_required"
                reason = (
                    "Fast_Conv generated from RUN, but engineer confirmation still required for: "
                    + ", ".join(needs)
                )
            else:
                status = "automatically_realized"
                reason = ""
        elif in_autogen and oclass in ("CP2_CONFIRMED", "UNKNOWN") and not in_generated:
            status = "engineer_confirmation_required"
            reason = "Autogen-scoped but missing from generated L5X Fast_Conv set"
        elif oclass == "CP2_CONFIRMED" and not in_autogen:
            status = "engineer_confirmation_required"
            reason = (
                "CP2_CONFIRMED via motor/Mtrchain evidence but omitted from Autogen "
                "PE/VFD-scoped conveyor set — engineer must include for generation"
            )
        elif in_autogen and in_generated:
            status = "engineer_confirmation_required"
            reason = f"Generated but ownership class is {oclass}"
        elif included and supported:
            status = "engineer_confirmation_required"
            reason = "Site Forge supported but not yet automatically realized"
        else:
            status = "ignored"
            reason = f"Not realized (ownership={oclass}, autogen={in_autogen})"

        # Override: if unsupported already set, keep it
        if status == "unsupported":
            pass

        counts[status] += 1
        items.append(
            {
                "conveyor": tag,
                "asc_type": asc_type,
                "ownership": oclass,
                "autogen_scoped": in_autogen,
                "site_forge_supported": supported,
                "generated_fast_conv": in_generated,
                "workbook_include": included,
                "main_area": wb.get("main_area") or "",
                "safety_zone": wb.get("safety_zone") or "",
                "downstream": wb.get("downstream") or "",
                "status": status,
                "reason": reason,
            }
        )

    # Demo philosophy: mechanical Fast_Conv from CURRENT RUN counts as realized;
    # area/ES/topology gaps are tracked in remaining_work, not as failed realization.
    for it in items:
        if (
            it["generated_fast_conv"]
            and it["ownership"] == "CP2_CONFIRMED"
            and it["site_forge_supported"]
        ):
            it["status"] = "automatically_realized"
            it["reason"] = (
                "Mechanical Fast_Conv realized from CURRENT RUN + Site Forge libraries "
                "(area/ES/topology may still need engineer fill — see remaining_work)"
            )

    counts = Counter(it["status"] for it in items)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "CURRENT RUN (ownership + Autogen scope + generated L5X)",
        "policy": {
            "finished_plc_not_used_as_target": True,
            "universe": "Autogen-scoped UNION ownership CP2_CONFIRMED/CANDIDATE mechanical",
        },
        "counts": {
            "run_equipment_discovered": len(relevant),
            "site_forge_supported": supported_n,
            "automatically_realized": int(counts.get("automatically_realized", 0)),
            "engineer_confirmation_required": int(
                counts.get("engineer_confirmation_required", 0)
            ),
            "unsupported": int(counts.get("unsupported", 0)),
            "ignored": int(counts.get("ignored", 0)),
        },
        "items": items,
        "validation_observation": {
            "finished_plc_conveyor_count": 57,
            "note": "Finished PLC conveyor count is observation only — not a realization target.",
        },
    }


# ---------------------------------------------------------------------------
# 2. pe_realization
# ---------------------------------------------------------------------------

def _pe_provenance(
    pe_tag: str,
    role: str,
    assigned_role: str,
    run_pe: dict | None,
    engineer_configured: bool,
) -> tuple[str, str, float, bool]:
    """Return provenance, evidence, confidence, insufficient_flag."""
    if engineer_configured:
        return "ENGINEER_CONFIGURED", "workbook edited PE assignment", 0.95, False

    name = (pe_tag or "").upper()
    desc = ((run_pe or {}).get("description") or "").upper()
    run_role = (run_pe or {}).get("role") or ""
    if not run_role and run_pe is not None:
        run_role = _classify_pe_role(name, desc)

    explicit_suffix = bool(
        re.search(r"_(F|J|P|JF|FDJ)\d*$", name)
        or name.endswith(("_F", "_J", "_P"))
    )
    desc_hit = any(
        k in desc for k in ("FULL", "JAM", "PRODUCT", "DISCHARGE", "PRESENT")
    )

    if run_pe is None:
        return "UNKNOWN", "PE not found in RUN pe_devices for this controller", 0.1, True

    if assigned_role in ("full", "jam", "exit", "add", "product"):
        # Exact role agreement from RUN naming
        if explicit_suffix and (
            (assigned_role == "full" and run_role == "full")
            or (assigned_role == "jam" and run_role == "jam")
            or (assigned_role in ("exit", "add", "product") and run_role == "product")
        ):
            return (
                "RUN_EXPLICIT",
                f"RUN name/role={run_role}; desc_evidence={desc_hit}",
                0.9,
                False,
            )
        # Jam eye used as Slow_Jam slot — RUN-derived, sufficient
        if assigned_role == "jam" and run_role in ("jam", "product", "other"):
            return (
                "RUN_DERIVED",
                f"PE_Logic/Slow_Jam slot from RUN pe_role={run_role or 'other'}",
                0.75,
                False,
            )
        # Exit/Add assigned from a non-product eye (common Autogen fallback) — flag
        if assigned_role in ("exit", "add") and run_role != "product":
            return (
                "DEFAULT",
                (
                    f"Exit/Add assigned to pe_role={run_role or 'unknown'} "
                    "without RUN product/discharge evidence"
                ),
                0.4,
                True,
            )
        if assigned_role == "full" and run_role != "full":
            return (
                "DEFAULT",
                f"Full_PE assigned but RUN pe_role={run_role or 'unknown'}",
                0.35,
                True,
            )
        if explicit_suffix or desc_hit:
            return (
                "RUN_DERIVED",
                f"Derived from RUN pe_role={run_role or _classify_pe_role(name, desc)}",
                0.7,
                False,
            )
        return (
            "DEFAULT",
            f"Assigned as {assigned_role} without explicit RUN role evidence",
            0.35,
            True,
        )

    return "UNKNOWN", "Unclassified PE assignment", 0.2, True


def build_pe_realization(
    run_dir: Path,
    machine: str,
    workbook: dict,
    gen_l5x: Path | None,
) -> dict:
    inp = load_from_run(run_dir)
    run_pes: dict[str, dict] = {}
    for pe in inp.pe_devices or []:
        if isinstance(pe, dict):
            name = (pe.get("name") or pe.get("fortna_name") or "").strip()
            d = pe
        else:
            name = (getattr(pe, "name", None) or getattr(pe, "fortna_name", None) or "").strip()
            d = {
                "name": name,
                "fortna_name": name,
                "role": getattr(pe, "role", "") or getattr(pe, "pe_role", ""),
                "conveyor": getattr(pe, "conveyor", "") or "",
                "description": getattr(pe, "description", "") or "",
            }
        if name:
            run_pes[name.upper()] = d

    wb_pe_edited: set[str] = set()
    for row in workbook.get("conveyors") or []:
        if row.get("edited"):
            for t in (
                [row.get("exit_pe_tag") or ""]
                + list(row.get("jam_pe_tags") or [])
                + list(row.get("full_pe_tags") or [])
                + list(row.get("product_pe_tags") or [])
            ):
                if t:
                    wb_pe_edited.add(str(t).upper())

    instances: list[dict] = []
    if not gen_l5x or not gen_l5x.is_file():
        return {
            "generated_at": _ts(),
            "machine": machine,
            "source_of_truth": "generated L5X + CURRENT RUN pe_devices",
            "error": "Generated L5X missing — PE realization blocked",
            "counts": {"Full_PE": 0, "PE_Logic": 0},
            "instances": [],
            "insufficient_evidence": [],
            "validation_observation_only": {
                "finished_plc_Full_PE": FINISHED_FULL_PE_OBS,
                "finished_plc_PE_Logic": FINISHED_PE_LOGIC_OBS,
                "note": (
                    "Finished PLC Full_PE/PE_Logic counts are validation observations "
                    "only — not generation targets. Generated counts are what they are."
                ),
            },
        }

    text = gen_l5x.read_text(encoding="utf-8", errors="replace")

    # Also pull Fast_Conv exit/add for role context
    fast_exit: dict[str, str] = {}
    fast_add: dict[str, str] = {}
    inv = extract_l5x(gen_l5x)
    for conv, rec in (inv.fast_conv or {}).items():
        if rec.exit_pe and rec.exit_pe != "NO_PE":
            fast_exit[conv.upper()] = rec.exit_pe.upper()
        if rec.add_pe and rec.add_pe != "NO_PE":
            fast_add[conv.upper()] = rec.add_pe.upper()

    for aoi, cre in PE_CALL_RE.items():
        for m in cre.finditer(text):
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) < 3:
                continue
            pe_tag = args[1]
            conv = _conv_from_udt(args[2])
            pe_u = pe_tag.upper()
            conv_u = conv.upper()
            run_pe = run_pes.get(pe_u)
            run_role = ""
            if run_pe:
                run_role = run_pe.get("role") or _classify_pe_role(
                    pe_u, run_pe.get("description") or ""
                )
            elif pe_u:
                run_role = _classify_pe_role(pe_u, "")

            if aoi == "Full_PE":
                assigned = "full"
            else:
                # PE_Logic — product/jam style
                if pe_u == fast_exit.get(conv_u):
                    assigned = "exit"
                elif pe_u == fast_add.get(conv_u):
                    assigned = "add"
                elif run_role == "jam" or re.search(r"_J\d*$|_JF|_FDJ", pe_u):
                    assigned = "jam"
                elif run_role == "product" or re.search(r"_P\d*$", pe_u):
                    assigned = "product"
                else:
                    assigned = "jam"  # Slow_Jam / PE_Logic default bucket in Autogen

            prov, evidence, confidence, insufficient = _pe_provenance(
                pe_u,
                run_role,
                assigned,
                run_pe,
                engineer_configured=pe_u in wb_pe_edited,
            )
            # Link conveyor evidence from RUN
            linked = ""
            if run_pe:
                linked = (run_pe.get("conveyor") or "").upper()
            if not linked:
                linked = _link_pe_to_conveyor(
                    {
                        "fortna_name": pe_u,
                        "description": (run_pe or {}).get("description") or "",
                        "conveyor": "",
                    }
                )

            run_source = "RUN_pe_devices" if run_pe else "generated_only"
            instances.append(
                {
                    "aoi": aoi,
                    "pe_tag": pe_tag,
                    "conveyor": conv,
                    "role": assigned,
                    "run_role": run_role or None,
                    "run_linked_conveyor": linked or None,
                    "run_source": run_source,
                    "evidence": evidence,
                    "confidence": confidence,
                    "provenance": prov,
                    "insufficient_run_engineer_evidence": insufficient,
                }
            )

    insufficient = [i for i in instances if i.get("insufficient_run_engineer_evidence")]
    by_aoi = Counter(i["aoi"] for i in instances)
    by_prov = Counter(i["provenance"] for i in instances)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "generated L5X + CURRENT RUN pe_devices (not finished PLC)",
        "generated_l5x": _rel(gen_l5x) if gen_l5x else None,
        "counts": {
            "Full_PE": int(by_aoi.get("Full_PE", 0)),
            "PE_Logic": int(by_aoi.get("PE_Logic", 0)),
            "insufficient_evidence": len(insufficient),
            "by_provenance": dict(by_prov),
        },
        "instances": instances,
        "insufficient_evidence": insufficient,
        "validation_observation_only": {
            "finished_plc_Full_PE": FINISHED_FULL_PE_OBS,
            "finished_plc_PE_Logic": FINISHED_PE_LOGIC_OBS,
            "note": (
                "Finished PLC Full_PE=7 / PE_Logic=30 are validation observations only — "
                "not generation targets. Generated counts are what they are from CURRENT RUN."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 3. area_es_status
# ---------------------------------------------------------------------------

def build_area_es_status(
    run_dir: Path,
    machine: str,
    ownership: dict,
    workbook: dict,
    realization_items: list[dict],
) -> dict:
    """How much Area/ES is recoverable from RUN (typically little)."""
    # Probe RUN for explicit area / ES tables — usually absent for Fortna ASC.
    fortna = run_dir / "FORTNA"
    area_like_files = []
    for pat in ("*Area*", "*ESZone*", "*EStop*", "*Safety*", "*Zone*"):
        area_like_files.extend([_rel(p) for p in fortna.glob(pat) if p.is_file()])

    run_area_signals: list[str] = []
    # Conveyor.asc rarely has usable Area columns for Greensboro CP2.
    _h, rows = read_asc(fortna / "Conveyor.asc")
    area_cols = [c for c in (_h or []) if re.search(r"area|zone|estop|safety", c or "", re.I)]
    nonzero_area_vals = 0
    sample_vals: list[str] = []
    for r in rows[:500]:
        for c in area_cols:
            v = _clean(r.get(c))
            if v and v.upper() not in ("N/A", "INVALID", "NONE", "0"):
                nonzero_area_vals += 1
                if len(sample_vals) < 10:
                    sample_vals.append(f"{c}={v}")

    if area_cols:
        run_area_signals.append(f"Conveyor.asc columns: {area_cols}")
    run_recoverable = nonzero_area_vals > 0 and not all(
        "ORNCCP" in s or "IMPORTED" in s.upper() for s in sample_vals
    )

    # Focus on CP2 CONFIRMED + CANDIDATE + Autogen-realized set
    focus = sorted(
        {
            it["conveyor"]
            for it in realization_items
            if it.get("ownership") in ("CP2_CONFIRMED", "CP2_CANDIDATE")
            or it.get("autogen_scoped")
        }
    )

    wb_by = {
        (r.get("conveyor") or "").strip().upper(): r
        for r in (workbook.get("conveyors") or [])
    }

    area_required: list[dict] = []
    es_required: list[dict] = []
    area_ok: list[str] = []
    es_ok: list[str] = []

    for tag in focus:
        wb = wb_by.get(tag) or {}
        area = (wb.get("main_area") or "").strip()
        zone = (wb.get("safety_zone") or "").strip()
        edited = bool(wb.get("edited"))

        if edited and not _is_placeholder_area(area):
            area_ok.append(tag)
        else:
            area_required.append(
                {
                    "conveyor": tag,
                    "status": "AREA REQUIRED",
                    "current_value": area or None,
                    "reason": (
                        "Machine-default / placeholder area — not recovered from RUN Area table"
                        if _is_placeholder_area(area)
                        else "Area blank — ENGINEER CONFIGURATION REQUIRED"
                    ),
                }
            )

        if zone.upper() == "ORNCCP2_IMPORTED_ESZONE1" or "IMPORTED_ESZONE" in zone.upper():
            es_required.append(
                {
                    "conveyor": tag,
                    "status": "ES ZONE REQUIRED",
                    "current_value": zone,
                    "reason": (
                        "ORNCCP2_Imported_ESZone1 is NOT confirmed — treat as placeholder only"
                    ),
                }
            )
        elif edited and not _is_placeholder_es(zone):
            es_ok.append(tag)
        else:
            es_required.append(
                {
                    "conveyor": tag,
                    "status": "ES ZONE REQUIRED",
                    "current_value": zone or None,
                    "reason": (
                        "Machine-default / placeholder ES zone — not confirmed RUN safety mapping"
                        if _is_placeholder_es(zone)
                        else "ES zone blank — ENGINEER CONFIGURATION REQUIRED"
                    ),
                }
            )

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "CURRENT RUN + workbook (finished PLC areas never copied)",
        "run_area_es_recoverability": {
            "recoverable_from_run": bool(run_recoverable),
            "likely": "little",
            "area_like_files": sorted(set(area_like_files)),
            "conveyor_asc_area_columns": area_cols,
            "nonzero_area_like_values_sampled": nonzero_area_vals,
            "sample_values": sample_vals,
            "note": (
                "Greensboro CP2 RUN does not provide finished ModuleB/ModuleC/Trash area "
                "names. Machine-default ORNCCP2_Area / ORNCCP2_ESZone1 are placeholders."
            ),
        },
        "counts": {
            "conveyors_evaluated": len(focus),
            "area_confirmed_engineer": len(area_ok),
            "area_required": len(area_required),
            "es_confirmed_engineer": len(es_ok),
            "es_zone_required": len(es_required),
        },
        "area_confirmed": area_ok,
        "area_required": area_required,
        "es_confirmed": es_ok,
        "es_zone_required": es_required,
        "do_not_confirm": [
            "ORNCCP2_Imported_ESZone1",
            "ORNCCP2_ESZone1 (machine default placeholder)",
            "ORNCCP2_Area (machine default placeholder)",
        ],
    }


# ---------------------------------------------------------------------------
# 4. overlap_classification
# ---------------------------------------------------------------------------

def build_overlap_classification(run_dir: Path, machine: str) -> dict:
    raw = overlap_audit(run_dir, machine)
    # Normalize any legacy leftovers just in case
    legacy_map = {
        "valid_parallel": "PARALLEL_EQUIPMENT",
        "parent_child": "PARENT_CHILD",
        "duplicate_run_geometry": "SAME_PHYSICAL_EQUIPMENT",
        "multiple_logical_on_one_physical": "SAME_PHYSICAL_EQUIPMENT",
    }
    pairs = []
    by_class: Counter[str] = Counter()
    for p in raw.get("overlap_pairs") or []:
        cls = p.get("classification") or "UNKNOWN"
        cls = legacy_map.get(cls, cls)
        if cls not in OVERLAP_CLASSES:
            cls = "UNKNOWN"
        q = dict(p)
        q["classification"] = cls
        pairs.append(q)
        by_class[cls] += 1

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": _rel(run_dir),
        "source_of_truth": "CURRENT RUN geometry only",
        "equipment_count": raw.get("equipment_count"),
        "classes": list(OVERLAP_CLASSES),
        "counts_by_class": {c: int(by_class.get(c, 0)) for c in OVERLAP_CLASSES},
        "overlap_pairs": pairs,
        "policy": {
            "move_equipment_to_fix_overlap": False,
            "finished_plc_used": False,
            **(raw.get("policy") or {}),
        },
    }


# ---------------------------------------------------------------------------
# 5. remaining_work
# ---------------------------------------------------------------------------

def build_remaining_work(
    realization: dict,
    pe: dict,
    area_es: dict,
    layout: dict | None,
) -> dict:
    items = realization.get("items") or []
    need_topology = []
    for it in items:
        if it.get("status") == "ignored":
            continue
        if it.get("ownership") not in ("CP2_CONFIRMED", "CP2_CANDIDATE") and not it.get(
            "autogen_scoped"
        ):
            continue
        ds = (it.get("downstream") or "").strip()
        if not ds:
            need_topology.append(it["conveyor"])

    need_area = [r["conveyor"] for r in (area_es.get("area_required") or [])]
    need_es = [r["conveyor"] for r in (area_es.get("es_zone_required") or [])]

    pe_confirm = [
        i
        for i in (pe.get("insufficient_evidence") or [])
        if i.get("role") in ("full", "jam", "exit", "add", "product")
    ]
    # Unique PE role confirmations
    pe_keys = sorted(
        {
            f"{i.get('aoi')}:{i.get('pe_tag')}:{i.get('role')}"
            for i in pe_confirm
        }
    )

    unsupported = [
        it["conveyor"]
        for it in items
        if it.get("status") == "unsupported"
    ]
    # Also count ignored CONFIRMED omissions? No — unsupported only.

    eng_confirm_conveyors = [
        it["conveyor"]
        for it in items
        if it.get("status") == "engineer_confirmation_required"
    ]

    x = len(sorted(set(need_topology)))
    y = len(sorted(set(need_area)))
    z = len(sorted(set(need_es)))
    n = len(pe_keys)
    m = len(sorted(set(unsupported)))

    return {
        "generated_at": _ts(),
        "source_of_truth": "CURRENT RUN demo-closure artifacts",
        "summary": {
            "conveyors_need_topology": x,
            "conveyors_need_area": y,
            "conveyors_need_es_zone": z,
            "pe_roles_need_confirmation": n,
            "unsupported_equipment_items": m,
        },
        "engineering_terms": [
            f"{x} conveyors need topology",
            f"{y} need Area",
            f"{z} need ES Zone",
            f"{n} PE roles need confirmation",
            f"{m} unsupported equipment items",
        ],
        "details": {
            "topology_conveyors": sorted(set(need_topology)),
            "area_conveyors": sorted(set(need_area)),
            "es_zone_conveyors": sorted(set(need_es)),
            "pe_role_keys": pe_keys,
            "unsupported_conveyors": sorted(set(unsupported)),
            "engineer_confirmation_conveyors": sorted(set(eng_confirm_conveyors)),
            "layout_counts": (layout or {}).get("counts"),
        },
        "policy": {
            "do_not_repair_from_finished_plc": True,
            "finished_plc_is_validation_observation_only": True,
        },
    }


# ---------------------------------------------------------------------------
# 6. demo_gate.md + docs
# ---------------------------------------------------------------------------

def write_demo_gate_md(
    out_dir: Path,
    *,
    run_dir: Path,
    machine: str,
    realization: dict,
    pe: dict,
    area_es: dict,
    overlap: dict,
    remaining: dict,
    gen_l5x: Path | None,
    report: dict | None,
) -> Path:
    rc = realization.get("counts") or {}
    pc = pe.get("counts") or {}
    ac = area_es.get("counts") or {}
    oc = overlap.get("counts_by_class") or {}
    rs = remaining.get("summary") or {}
    vo = pe.get("validation_observation_only") or {}

    lines = [
        "# CP2 Demo Closure — Greensboro ORNCCP2",
        "",
        f"**Generated (UTC):** {_ts()}",
        f"**Active RUN:** `{_rel(run_dir)}`",
        f"**Machine:** {machine}",
        f"**Generated L5X:** `{_rel(gen_l5x) if gen_l5x else '(missing)'}`",
        "",
        "## Philosophy",
        "",
        "| Source | Role |",
        "|--------|------|",
        "| **CURRENT RUN** | Generation source truth |",
        "| **FINISHED PLC** | Validation observation only — never a target |",
        "",
        "Do **not** repair gaps by copying finished PLC areas, ES zones, PE roles, or conveyor sets.",
        "",
        "## Artifact index",
        "",
        "| File | Purpose |",
        "|---|---|",
        "| `run_realization.json` | Mechanical conveyor realization status |",
        "| `pe_realization.json` | Full_PE / PE_Logic provenance + evidence |",
        "| `area_es_status.json` | Area / ES recoverability from RUN |",
        "| `overlap_classification.json` | Physical geometry overlap classes |",
        "| `remaining_work.json` | Engineering remaining-work counts |",
        "| `demo_gate.md` | This narrative |",
        "| `generated/` | Fresh Autogen L5X from RUN + workbook |",
        "",
        "## Run realization",
        "",
        f"- RUN equipment discovered (Autogen ∪ CP2_CONFIRMED/CANDIDATE): **{rc.get('run_equipment_discovered')}**",
        f"- Site Forge supported: **{rc.get('site_forge_supported')}**",
        f"- Automatically realized: **{rc.get('automatically_realized')}**",
        f"- Engineer confirmation required: **{rc.get('engineer_confirmation_required')}**",
        f"- Unsupported: **{rc.get('unsupported')}**",
        f"- Ignored: **{rc.get('ignored')}**",
        "",
        "Finished PLC Fast_Conv=57 is a **validation observation**, not a realization target.",
        "",
        "## PE realization",
        "",
        f"- Generated Full_PE calls: **{pc.get('Full_PE')}**",
        f"- Generated PE_Logic calls: **{pc.get('PE_Logic')}**",
        f"- Insufficient RUN/engineer evidence flags: **{pc.get('insufficient_evidence')}**",
        f"- Finished PLC observation (not a target): Full_PE **{vo.get('finished_plc_Full_PE', FINISHED_FULL_PE_OBS)}**, "
        f"PE_Logic **{vo.get('finished_plc_PE_Logic', FINISHED_PE_LOGIC_OBS)}**",
        "",
        "## Area / ES status",
        "",
        f"- RUN Area/ES recoverability: **{(area_es.get('run_area_es_recoverability') or {}).get('likely', 'little')}**",
        f"- AREA REQUIRED: **{ac.get('area_required')}**",
        f"- ES ZONE REQUIRED: **{ac.get('es_zone_required')}**",
        "- `ORNCCP2_Imported_ESZone1` is **not** confirmed.",
        "",
        "## Overlap classification",
        "",
        "| Class | Count |",
        "|---|---|",
    ]
    for cls in OVERLAP_CLASSES:
        lines.append(f"| {cls} | {oc.get(cls, 0)} |")
    lines += [
        "",
        "## Remaining work",
        "",
    ]
    for term in remaining.get("engineering_terms") or []:
        lines.append(f"- {term}")
    lines += [
        "",
        f"- Topology: **{rs.get('conveyors_need_topology')}**",
        f"- Area: **{rs.get('conveyors_need_area')}**",
        f"- ES Zone: **{rs.get('conveyors_need_es_zone')}**",
        f"- PE role confirmations: **{rs.get('pe_roles_need_confirmation')}**",
        f"- Unsupported equipment: **{rs.get('unsupported_equipment_items')}**",
        "",
        "## Generate workflow",
        "",
        "```",
        "fortna_workbook.py build --merge-existing  # RUN + engineer edits only",
        "fortna_autogen.py from-run --workbook ... --library OReilly_Library_v3.L5X",
        "```",
        "",
        "No finished-PLC seeding.",
        "",
        "## Orchestrator",
        "",
        "```",
        "python tools/scripts/fortna_cp2_demo_closure.py \\",
        "  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-demo-closure",
        "```",
        "",
    ]
    if report:
        lines += [
            "## Autogen report snapshot",
            "",
            f"- conveyor_count: {report.get('conveyor_count')}",
            f"- pe_logic_rungs: {report.get('pe_logic_rungs')}",
            f"- areas_summary: {report.get('areas_summary')}",
            "",
        ]

    path = out_dir / "demo_gate.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_docs_summary(
    *,
    run_dir: Path,
    machine: str,
    out_dir: Path,
    realization: dict,
    pe: dict,
    area_es: dict,
    remaining: dict,
    gen_l5x: Path | None,
) -> Path:
    rc = realization.get("counts") or {}
    pc = pe.get("counts") or {}
    rs = remaining.get("summary") or {}
    doc = ROOT / "docs" / "CP2_DEMO_CLOSURE.md"
    lines = [
        "# CP2 Demo Closure — Evidence Pack Summary",
        "",
        f"**Generated (UTC):** {_ts()}  ",
        f"**Branch intent:** demo-closure pack for `{machine}` from CURRENT RUN  ",
        f"**Active RUN:** `{_rel(run_dir)}`  ",
        f"**Output:** `{_rel(out_dir)}`",
        "",
        "## Binding philosophy",
        "",
        "- **CURRENT RUN** = generation source truth.",
        "- **FINISHED PLC** = validation observation only — never a target.",
        "- Do not repair missing Area / ES / PE / topology from finished PLC.",
        "- Do not treat `ORNCCP2_Imported_ESZone1` as confirmed.",
        "",
        "## What this pack answers",
        "",
        "1. Which RUN mechanical conveyors Site Forge automatically realizes vs needs engineer confirmation.",
        "2. PE Full/Jam/Exit/Add provenance (RUN_EXPLICIT / RUN_DERIVED / ENGINEER_CONFIGURED / DEFAULT / UNKNOWN).",
        "3. How little Area/ES is recoverable from RUN.",
        "4. Physical overlap classes (no auto-spreading).",
        "5. Remaining engineering work in plain terms.",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| RUN equipment discovered | {rc.get('run_equipment_discovered')} |",
        f"| Site Forge supported | {rc.get('site_forge_supported')} |",
        f"| Automatically realized | {rc.get('automatically_realized')} |",
        f"| Engineer confirmation required | {rc.get('engineer_confirmation_required')} |",
        f"| Unsupported | {rc.get('unsupported')} |",
        f"| Ignored | {rc.get('ignored')} |",
        f"| Generated Full_PE | {pc.get('Full_PE')} |",
        f"| Generated PE_Logic | {pc.get('PE_Logic')} |",
        f"| Finished Full_PE (observation only) | {FINISHED_FULL_PE_OBS} |",
        f"| Finished PE_Logic (observation only) | {FINISHED_PE_LOGIC_OBS} |",
        f"| AREA REQUIRED | {(area_es.get('counts') or {}).get('area_required')} |",
        f"| ES ZONE REQUIRED | {(area_es.get('counts') or {}).get('es_zone_required')} |",
        "",
        "## Remaining work",
        "",
    ]
    for term in remaining.get("engineering_terms") or []:
        lines.append(f"- **{term}**")
    lines += [
        "",
        f"- Topology: {rs.get('conveyors_need_topology')}",
        f"- Area: {rs.get('conveyors_need_area')}",
        f"- ES Zone: {rs.get('conveyors_need_es_zone')}",
        f"- PE roles: {rs.get('pe_roles_need_confirmation')}",
        f"- Unsupported: {rs.get('unsupported_equipment_items')}",
        "",
        "## CLI",
        "",
        "```",
        "python tools/scripts/fortna_cp2_demo_closure.py \\",
        "  --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/cp2-demo-closure",
        "```",
        "",
        f"Fresh L5X: `{_rel(gen_l5x) if gen_l5x else 'exports/cp2-demo-closure/generated/'}`",
        "",
        "## Related",
        "",
        "- `docs/CP2_COMPLETION_GATE.md` — broader completion-gate inventories",
        "- `docs/SOURCE_OF_TRUTH_POLICY.md` — binding input / validation barrier",
        "",
    ]
    doc.write_text("\n".join(lines), encoding="utf-8")
    return doc


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

def build_layout_snapshot(run_dir: Path, machine: str, out_dir: Path) -> dict:
    layout_dir = out_dir / "layout"
    layout_dir.mkdir(parents=True, exist_ok=True)
    try:
        graph = build_transport_graph(run_dir, machine=machine)
    except TypeError:
        graph = build_transport_graph(run_dir)
    except Exception as exc:
        return {
            "generated_at": _ts(),
            "machine": machine,
            "error": str(exc),
            "counts": {},
        }
    if isinstance(graph, dict):
        _write_json(layout_dir / "transport_graph_from_run.json", graph)
        counts = graph.get("counts") or {}
        if not counts:
            nodes = graph.get("nodes") or graph.get("conveyors") or []
            edges = graph.get("edges") or graph.get("connections") or []
            counts = {
                "placed": len(nodes),
                "connections": len(edges),
            }
        return {
            "generated_at": _ts(),
            "machine": machine,
            "counts": counts,
            "geometry_summary": graph.get("geometry_summary") or {},
            "nodes": graph.get("nodes") or graph.get("conveyors") or [],
            "edges": graph.get("edges") or graph.get("connections") or [],
        }
    return {"generated_at": _ts(), "machine": machine, "counts": {}, "raw_type": type(graph).__name__}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_closure(
    run_dir: Path,
    machine: str,
    out_dir: Path,
    *,
    skip_generate: bool = False,
) -> dict:
    run_dir = ensure_active_run(run_dir, machine)
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = read_project_meta(run_dir)
    if not meta.get("machine_name"):
        raise FileNotFoundError(f"No usable RUN at {run_dir}")

    print(f"[closure] RUN={run_dir} machine={machine} out={out_dir}")

    print("[closure] Ownership classification (RUN-only)…")
    ownership = classify_ownership(run_dir, machine)
    write_classification(ownership, out_dir / "ownership_classification.json")

    print("[closure] Workbook (merge-existing, no finished-PLC seed)…")
    wb_path, workbook = build_workbook(run_dir, out_dir)

    print("[closure] Layout snapshot…")
    layout = build_layout_snapshot(run_dir, machine, out_dir)
    _write_json(out_dir / "layout_snapshot.json", {
        k: layout[k] for k in ("generated_at", "machine", "counts", "geometry_summary") if k in layout
    })

    report: dict = {}
    gen_dir = out_dir / "generated"
    gen_l5x: Path | None = None
    if skip_generate:
        print("[closure] skip-generate: preferring existing generated/ or cp2-gate L5X…")
        gen_l5x = _find_generated_l5x(gen_dir) or _latest_gate_l5x()
        if gen_l5x and gen_l5x.parent != gen_dir:
            # Copy reference path note only — do not invent; allow read from gate
            print(f"[closure] Using existing L5X at {gen_l5x}")
        report_path = (gen_l5x.parent / "autogen_report.json") if gen_l5x else None
        if report_path and report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        print("[closure] Generating CP2 L5X (workbook + from-run)…")
        gen_dir, report, _gen_result = generate_l5x(run_dir, wb_path, out_dir)
        gen_l5x = _find_generated_l5x(gen_dir)
        print(f"[closure] Generated L5X: {gen_l5x}")

    print("[closure] run_realization.json…")
    realization = build_run_realization(
        run_dir, machine, ownership, workbook, gen_l5x, layout
    )
    _write_json(out_dir / "run_realization.json", realization)

    print("[closure] pe_realization.json…")
    pe = build_pe_realization(run_dir, machine, workbook, gen_l5x)
    _write_json(out_dir / "pe_realization.json", pe)

    print("[closure] area_es_status.json…")
    area_es = build_area_es_status(
        run_dir, machine, ownership, workbook, realization.get("items") or []
    )
    _write_json(out_dir / "area_es_status.json", area_es)

    print("[closure] overlap_classification.json…")
    overlap = build_overlap_classification(run_dir, machine)
    _write_json(out_dir / "overlap_classification.json", overlap)

    print("[closure] remaining_work.json…")
    remaining = build_remaining_work(realization, pe, area_es, layout)
    _write_json(out_dir / "remaining_work.json", remaining)

    print("[closure] demo_gate.md + docs/CP2_DEMO_CLOSURE.md…")
    demo_md = write_demo_gate_md(
        out_dir,
        run_dir=run_dir,
        machine=machine,
        realization=realization,
        pe=pe,
        area_es=area_es,
        overlap=overlap,
        remaining=remaining,
        gen_l5x=gen_l5x,
        report=report,
    )
    doc = write_docs_summary(
        run_dir=run_dir,
        machine=machine,
        out_dir=out_dir,
        realization=realization,
        pe=pe,
        area_es=area_es,
        remaining=remaining,
        gen_l5x=gen_l5x,
    )

    result = {
        "ok": True,
        "out_dir": _rel(out_dir),
        "demo_gate": _rel(demo_md),
        "docs": _rel(doc),
        "generated_l5x": _rel(gen_l5x) if gen_l5x else None,
        "run_realization_counts": realization.get("counts"),
        "pe_counts": pe.get("counts"),
        "remaining_work": remaining.get("summary"),
        "engineering_terms": remaining.get("engineering_terms"),
    }
    _write_json(out_dir / "closure_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP2 Demo Closure evidence pack (ORNCCP2)")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", default=str(ROOT / "exports" / "cp2-demo-closure"))
    ap.add_argument(
        "--skip-generate",
        action="store_true",
        help="Reuse existing generated L5X (or cp2-gate) instead of fresh Autogen",
    )
    args = ap.parse_args(argv)
    try:
        result = run_closure(
            Path(args.run_dir),
            args.machine.strip().upper(),
            Path(args.out),
            skip_generate=bool(args.skip_generate),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
