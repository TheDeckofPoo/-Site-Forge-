#!/usr/bin/env python3
"""Permanent Transportation freeze regression (ORNCCP2 merge identities).

Proves frozen MergeBoss / MergeInputs / merge-class / MERGE_316(+324) chain
evidence from RUN + existing CP4/merge helpers. Never invents table data.

RUN resolution:
  1) workspace/active/RUN when present
  2) any PLC2 / ORNCCP2 RUN under workspace/
  3) SkipTest with a clear message (assertions remain encoded)
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_plc2_merge_discovery import (  # noqa: E402
    _clean,
    _load_table,
    _row_dict,
    classify_merge_source,
    discover_plc2_merges,
)
from fortna_semantics.merge import run_merge_adapter  # noqa: E402
from fortna_semantics.mtrchain import run_mtrchain_adapter  # noqa: E402

MACHINE = "ORNCCP2"
REPORT_PATH = ROOT / "exports" / "stabilization" / "transportation_freeze_report.md"

# Encoded freeze assertions (always present even when RUN is skipped).
EXPECTED_BOSSES = (
    "MERGE_406_3-1",
    "MERGE_316_SPUR",
    "MERGE_400_2-1",
    "MERGE_324_SPUR",
)
EXPECTED_LANES: dict[str, tuple[str, str]] = {
    "MERGE_406_3-1": ("LANE1_P404", "LANE2_P138"),
    "MERGE_316_SPUR": ("LANE1_P136", "LANE2_P312"),
    "MERGE_400_2-1": ("LANE1_P242", "LANE2_P150_2-1"),
    "MERGE_324_SPUR": ("LANE1_P150_SPUR", "LANE2_P320"),
}
EXPECTED_TYPES: dict[str, str] = {
    "MERGE_406_3-1": "3-1",
    "MERGE_316_SPUR": "SPUR",
    "MERGE_400_2-1": "2-1",
    "MERGE_324_SPUR": "SPUR",
}
# MERGE_316 MergeInputs + Mtrchain freeze chain
EXPECTED_316_LANE_IO = {
    "LANE1_P136": {"presence": "EZPE136_P1", "release_io": "SSVEZPE136_P1"},
    "LANE2_P312": {"presence": "PE314_P", "release_io": "M314"},
}
EXPECTED_M314 = {
    "Motor_Ndx": "M314",
    "Motor_Chained1": "P314",
    "Motor_Aux": "LATCH_MERGE_316",
    "Enabled": "M136_AUX",
}
EXPECTED_316_PHYS = ("M314", "P314", "P316", "CURVE")

# MERGE_324 analogous chain when evidence exists
EXPECTED_324_LANE_IO = {
    "LANE1_P150_SPUR": {"presence": "EZPE150_P1", "release_io": "SSVEZPE150_P1"},
    "LANE2_P320": {"presence": "PE322_P", "release_io": "M322"},
}
EXPECTED_M322 = {
    "Motor_Ndx": "M322",
    "Motor_Chained1": "P322",
    "Motor_Aux": "LATCH_MERGE_324",
}
EXPECTED_324_PHYS = ("M322", "P322", "P324", "CURVE")


def _is_ornccp2_run(run_dir: Path) -> bool:
    if not (run_dir / "project.cfg").is_file() and not (run_dir / "FORTNA").is_dir():
        return False
    fortna = run_dir / "FORTNA"
    if (fortna / "MergeBoss.asc.ORNCCP2").is_file():
        return True
    # identity.cfg / project.cfg machine hint
    for cfg in (run_dir / "identity.cfg", run_dir / "project.cfg"):
        if cfg.is_file():
            try:
                text = cfg.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "ORNCCP2" in text:
                return True
    return False


def resolve_ornccp2_run() -> Path | None:
    """Prefer workspace/active/RUN; else any PLC2 ORNCCP2 RUN under workspace."""
    active = ROOT / "workspace" / "active" / "RUN"
    if active.is_dir() and _is_ornccp2_run(active):
        return active.resolve()

    peek = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
    if peek.is_dir() and _is_ornccp2_run(peek):
        return peek.resolve()

    workspace = ROOT / "workspace"
    if not workspace.is_dir():
        return None
    candidates: list[Path] = []
    for run_dir in workspace.rglob("RUN"):
        if not run_dir.is_dir():
            continue
        if run_dir == active or run_dir == peek:
            continue
        if _is_ornccp2_run(run_dir):
            candidates.append(run_dir.resolve())
    if not candidates:
        return None
    # Prefer shortest path (closest to workspace root)
    candidates.sort(key=lambda p: (len(p.parts), str(p).lower()))
    return candidates[0]


def _named_rows(fortna: Path, stem: str, name_keys: tuple[str, ...]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ent in _load_table(fortna, stem, MACHINE):
        row = _row_dict(ent)
        name = ""
        for k in name_keys:
            name = _clean(row.get(k))
            if name:
                break
        if name:
            out.append(row)
    return out


def _conveyor_type(fortna: Path, io_name: str) -> str:
    target = io_name.upper()
    for ent in _load_table(fortna, "Conveyor", MACHINE):
        row = _row_dict(ent)
        if _clean(row.get("IO_Name")).upper() == target:
            return _clean(row.get("Type")).upper()
    return ""


def _mtrchain_by_motor(fortna: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for ent in _load_table(fortna, "Mtrchain", MACHINE):
        row = _row_dict(ent)
        motor = _clean(row.get("Motor_Name")).upper()
        if motor and motor not in out:
            out[motor] = row
    return out


def _mergeinputs_by_boss(fortna: Path) -> dict[str, list[dict[str, str]]]:
    by_boss: dict[str, list[dict[str, str]]] = {}
    for row in _named_rows(fortna, "MergeInputs", ("Name",)):
        boss = _clean(row.get("MergeBoss"))
        if not boss:
            continue
        by_boss.setdefault(boss, []).append(row)
    return by_boss


def _load_cp4_merge_and_mtr(run_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """Load CP4 Merge + Mtrchain objects from active decoder, artifacts, or rebuild."""
    active_merge = ROOT / "workspace" / "active" / "decoder" / "cp4-merge-active.json"
    active_mtr = ROOT / "workspace" / "active" / "decoder" / "cp4-mtrchain-active.json"
    if active_merge.is_file() and active_mtr.is_file():
        return (
            json.loads(active_merge.read_text(encoding="utf-8")),
            json.loads(active_mtr.read_text(encoding="utf-8")),
            str(active_merge),
        )

    art_merge = ROOT / "artifacts" / "cp4-merge-plc2.json"
    art_mtr = ROOT / "artifacts" / "cp4-mtrchain-plc2.json"
    if art_merge.is_file() and art_mtr.is_file():
        return (
            json.loads(art_merge.read_text(encoding="utf-8")),
            json.loads(art_mtr.read_text(encoding="utf-8")),
            str(art_merge),
        )

    graph = ROOT / "artifacts" / "fortna-reference-graph-plc2.json"
    try:
        from fortna_semantics.evidence import load_or_build_cp3_index

        if graph.is_file():
            cp3 = load_or_build_cp3_index(graph_path=graph)
            src = str(graph)
        else:
            cp3 = load_or_build_cp3_index(run_dir=run_dir, ac_name=MACHINE)
            src = f"built_from:{run_dir}"
        mtr = run_mtrchain_adapter(cp3)
        merge = run_merge_adapter(cp3, mtrchain_public=mtr.to_dict())
        return merge.to_dict(), mtr.to_dict(), src
    except Exception as exc:  # pragma: no cover - optional CP4 path
        return None, None, f"unavailable:{exc}"


def collect_freeze_evidence(run_dir: Path) -> dict[str, Any]:
    """Gather freeze evidence from RUN helpers — no fabricated values."""
    fortna = run_dir / "FORTNA"
    discovery = discover_plc2_merges(run_dir, MACHINE)
    by_name = {m.get("name"): m for m in (discovery.get("merges") or [])}

    mergeboss_rows = _named_rows(fortna, "MergeBoss", ("Name",))
    mergeinputs_rows = _named_rows(fortna, "MergeInputs", ("Name",))
    jamcheck_rows = _named_rows(fortna, "Jamcheck", ("Sensor_Name", "Desc", "Name"))
    jamzones_rows = _named_rows(fortna, "Jamzones", ("Zone Name", "Zone_Name", "Name"))
    mtrchain_rows = _named_rows(fortna, "Mtrchain", ("Motor_Name",))

    # CURVE count from Conveyor.Type (machine-merged)
    curve_names: list[str] = []
    for ent in _load_table(fortna, "Conveyor", MACHINE):
        row = _row_dict(ent)
        if _clean(row.get("Type")).upper() == "CURVE":
            n = _clean(row.get("IO_Name"))
            if n:
                curve_names.append(n)

    areas_count = 0
    unresolved_count = 0
    site_model_path = run_dir.parent / "site_model.json"
    site_summary: dict[str, Any] = {}
    if site_model_path.is_file():
        site = json.loads(site_model_path.read_text(encoding="utf-8"))
        areas_count = len(site.get("areas") or [])
        unresolved = site.get("unresolved") or []
        unresolved_count = len(unresolved) if isinstance(unresolved, list) else 0
        site_summary = site.get("summary") or {}
        if not unresolved_count and isinstance(site_summary.get("unresolved"), int):
            unresolved_count = int(site_summary["unresolved"])

    mi_by_boss = _mergeinputs_by_boss(fortna)
    mtr_by_motor = _mtrchain_by_motor(fortna)
    m314 = mtr_by_motor.get("M314") or {}
    m322 = mtr_by_motor.get("M322") or {}

    cp4_merge, cp4_mtr, cp4_src = _load_cp4_merge_and_mtr(run_dir)
    cp4_bosses = {
        o.get("identity"): o for o in ((cp4_merge or {}).get("objects") or [])
    }
    cp4_mtr_objs = {
        o.get("identity"): o for o in ((cp4_mtr or {}).get("objects") or [])
    }

    review_statuses = []
    for adapter_name, blob in (
        ("Merge", cp4_merge),
        ("Mtrchain", cp4_mtr),
    ):
        if blob and blob.get("status") in {"REVIEW", "FAIL"}:
            review_statuses.append(f"{adapter_name}:{blob.get('status')}")

    return {
        "run_dir": str(run_dir),
        "machine": MACHINE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery": discovery,
        "by_name": by_name,
        "counts": {
            "MergeBoss": len(mergeboss_rows),
            "MergeInputs": len(mergeinputs_rows),
            "Jamcheck": len(jamcheck_rows),
            "Jamzones": len(jamzones_rows),
            "Mtrchain": len(mtrchain_rows),
            "CURVE": len(curve_names),
            "Areas": areas_count,
            "review_unresolved": unresolved_count
            + len(review_statuses)
            + int((discovery.get("counts") or {}).get("unresolved") or 0),
        },
        "count_detail": {
            "discovery": discovery.get("counts") or {},
            "site_model_summary": site_summary,
            "cp4_review": review_statuses,
            "curve_sample": curve_names[:12],
        },
        "mergeboss_names": sorted(_clean(r.get("Name")) for r in mergeboss_rows),
        "mergeinputs_by_boss": {
            boss: [_clean(r.get("Name")) for r in rows]
            for boss, rows in mi_by_boss.items()
        },
        "mergeinputs_rows_by_boss": mi_by_boss,
        "m314": {k: _clean(m314.get(k)) for k in (
            "Motor_Name", "Motor_Ndx", "Motor_Chained1", "Motor_Chained2",
            "Motor_Aux", "Enabled",
        )},
        "m322": {k: _clean(m322.get(k)) for k in (
            "Motor_Name", "Motor_Ndx", "Motor_Chained1", "Motor_Chained2",
            "Motor_Aux", "Enabled",
        )},
        "p316_type": _conveyor_type(fortna, "P316"),
        "p324_type": _conveyor_type(fortna, "P324"),
        "cp4_source": cp4_src,
        "cp4_bosses": sorted(cp4_bosses),
        "cp4_m314": cp4_mtr_objs.get("M314"),
        "cp4_m322": cp4_mtr_objs.get("M322"),
        "cp4_merge_proofs": (cp4_merge or {}).get("proofs") or {},
        "cp4_merge_counts": (cp4_merge or {}).get("counts") or {},
        "cp4_mtr_counts": (cp4_mtr or {}).get("counts") or {},
        "cp4_jam_counts": _optional_jam_counts(),
    }


def _optional_jam_counts() -> dict[str, Any]:
    for path in (
        ROOT / "workspace" / "active" / "decoder" / "cp4-jam-active.json",
        ROOT / "artifacts" / "cp4-jam-plc2.json",
    ):
        if path.is_file():
            try:
                return (json.loads(path.read_text(encoding="utf-8")).get("counts") or {})
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def render_report(ev: dict[str, Any], *, checks: list[tuple[str, bool, str]]) -> str:
    lines: list[str] = []
    lines.append("# Transportation Freeze Report (ORNCCP2)")
    lines.append("")
    lines.append(f"- Generated: `{ev.get('generated_at')}`")
    lines.append(f"- Machine: `{ev.get('machine')}`")
    lines.append(f"- RUN: `{ev.get('run_dir')}`")
    lines.append(f"- CP4 evidence source: `{ev.get('cp4_source')}`")
    lines.append(
        "- Helpers: `fortna_plc2_merge_discovery`, `fortna_asc` / table merge, "
        "`fortna_semantics.merge` / `mtrchain` (when available)"
    )
    lines.append("- Policy: RUN-proven only — no invented merge identities or lanes")
    lines.append("")

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    lines.append("## Result")
    lines.append("")
    lines.append(
        f"**{'PASS' if failed == 0 else 'FAIL'}** — {passed} passed / {failed} failed"
    )
    lines.append("")

    lines.append("## Encoded freeze assertions")
    lines.append("")
    lines.append("### MergeBoss identities")
    for b in EXPECTED_BOSSES:
        lines.append(f"- `{b}` (type `{EXPECTED_TYPES[b]}`)")
    lines.append("")
    lines.append("### MergeInputs lanes")
    for boss, (l1, l2) in EXPECTED_LANES.items():
        lines.append(f"- `{boss}`: `{l1}`, `{l2}`")
    lines.append("")
    lines.append("### MERGE_316 chain")
    lines.append(
        "- LANE1_P136 Presence `EZPE136_P1` ReleaseIO `SSVEZPE136_P1`"
    )
    lines.append("- LANE2_P312 Presence `PE314_P` ReleaseIO `M314`")
    lines.append(
        "- M314 Motor_Ndx `M314` Motor_Chained1 `P314` "
        "Motor_Aux `LATCH_MERGE_316` Enabled `M136_AUX`"
    )
    lines.append("- Physical chain `M314 -> P314 -> P316 CURVE`")
    lines.append("")
    lines.append("### MERGE_324 chain (when evidence available)")
    lines.append(
        "- LANE1_P150_SPUR Presence `EZPE150_P1` ReleaseIO `SSVEZPE150_P1`"
    )
    lines.append("- LANE2_P320 Presence `PE322_P` ReleaseIO `M322`")
    lines.append(
        "- M322 Motor_Ndx `M322` Motor_Chained1 `P322` Motor_Aux `LATCH_MERGE_324`"
    )
    lines.append("- Physical chain `M322 -> P322 -> P324 CURVE`")
    lines.append("")

    lines.append("## Counts")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|------:|")
    for key in (
        "MergeBoss",
        "MergeInputs",
        "Jamcheck",
        "Jamzones",
        "Mtrchain",
        "CURVE",
        "Areas",
        "review_unresolved",
    ):
        lines.append(f"| {key} | {(ev.get('counts') or {}).get(key, 0)} |")
    disc = (ev.get("count_detail") or {}).get("discovery") or {}
    lines.append("")
    lines.append(
        f"Discovery classes: proven=`{disc.get('proven')}` "
        f"candidate=`{disc.get('candidate')}` unresolved=`{disc.get('unresolved')}`"
    )
    jam_cp4 = ev.get("cp4_jam_counts") or {}
    if jam_cp4:
        lines.append(
            f"CP4 Jam adapter: jamcheckRecordsTouched=`{jam_cp4.get('jamcheckRecordsTouched')}` "
            f"jamzonesIdentities=`{jam_cp4.get('jamzonesIdentities')}`"
        )
    merge_cp4 = ev.get("cp4_merge_counts") or {}
    if merge_cp4:
        lines.append(
            f"CP4 Merge adapter: mergeBossObjects=`{merge_cp4.get('mergeBossObjects')}` "
            f"lanes=`{merge_cp4.get('lanes')}` byClass=`{merge_cp4.get('byClass')}`"
        )
    mtr_cp4 = ev.get("cp4_mtr_counts") or {}
    if mtr_cp4:
        lines.append(
            f"CP4 Mtrchain adapter: entries=`{mtr_cp4.get('entries')}` "
            f"facts=`{mtr_cp4.get('facts')}`"
        )
    lines.append("")

    lines.append("## Observed MergeBoss / lanes")
    lines.append("")
    for boss in EXPECTED_BOSSES:
        m = (ev.get("by_name") or {}).get(boss) or {}
        lanes = (ev.get("mergeinputs_by_boss") or {}).get(boss) or []
        lines.append(
            f"- `{boss}` class=`{m.get('sourceClassification') or classify_merge_source(boss)}` "
            f"discovery=`{m.get('classification')}` lanes={lanes}"
        )
    lines.append("")

    lines.append("## MERGE_316 evidence")
    lines.append("")
    m316 = (ev.get("by_name") or {}).get("MERGE_316_SPUR") or {}
    lines.append(
        f"- discovery inductLane=`{m316.get('inductLane')}` "
        f"phys=`{m316.get('inductPhysicalRelease')}` "
        f"next=`{m316.get('inductNext')}`"
    )
    lines.append(f"- Mtrchain M314 row: `{ev.get('m314')}`")
    lines.append(f"- Conveyor P316 Type: `{ev.get('p316_type')}`")
    if ev.get("cp4_m314"):
        cm = ev["cp4_m314"]
        lines.append(
            f"- CP4 M314: ndx=`{(cm.get('motorNdx') or {}).get('raw')}` "
            f"aux=`{(cm.get('motorAux') or {}).get('raw')}` "
            f"enabled=`{(cm.get('enabled') or {}).get('raw')}` "
            f"chained1=`{next((c.get('raw') for c in (cm.get('chained') or []) if c.get('slot')==1), None)}`"
        )
    proof = (ev.get("cp4_merge_proofs") or {}).get("MERGE_316_SPUR") or {}
    if proof:
        lines.append(f"- CP4 merge proof status: `{proof.get('status')}`")
    lines.append("")

    lines.append("## MERGE_324 evidence")
    lines.append("")
    m324 = (ev.get("by_name") or {}).get("MERGE_324_SPUR") or {}
    if m324:
        lines.append(
            f"- discovery inductLane=`{m324.get('inductLane')}` "
            f"phys=`{m324.get('inductPhysicalRelease')}` "
            f"next=`{m324.get('inductNext')}`"
        )
        lines.append(f"- Mtrchain M322 row: `{ev.get('m322')}`")
        lines.append(f"- Conveyor P324 Type: `{ev.get('p324_type')}`")
    else:
        lines.append("- No MERGE_324_SPUR discovery evidence in this RUN")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        lines.append(f"- **{mark}** {name}{suffix}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Merge types SPUR / 2-1 / 3-1 are preserved from MergeBoss name tokens "
        "(`classify_merge_source`) and discovery `sourceClassification`."
    )
    lines.append(
        "- Physical chain M314→P314→P316 is Mtrchain Motor_Chained* + Conveyor.Type=CURVE; "
        "not an invented topology edge."
    )
    lines.append(
        "- `review_unresolved` aggregates site_model unresolved + discovery unresolved + "
        "CP4 adapter REVIEW/FAIL flags."
    )
    lines.append("")
    return "\n".join(lines)


def evaluate_checks(ev: dict[str, Any]) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    by_name = ev.get("by_name") or {}
    mi_by_boss = ev.get("mergeinputs_by_boss") or {}
    mi_rows = ev.get("mergeinputs_rows_by_boss") or {}

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    # MergeBoss identities (discovery + ASC)
    boss_names = set(ev.get("mergeboss_names") or [])
    for boss in EXPECTED_BOSSES:
        add(f"mergeboss_asc:{boss}", boss in boss_names, ",".join(sorted(boss_names)))
        add(f"mergeboss_discovery:{boss}", boss in by_name, str(sorted(by_name)))

    # Merge types preserved
    for boss, expected in EXPECTED_TYPES.items():
        got = (by_name.get(boss) or {}).get("sourceClassification") or classify_merge_source(boss)
        add(f"merge_type:{boss}", got == expected, f"got={got}")

    # MergeInputs lanes
    for boss, (l1, l2) in EXPECTED_LANES.items():
        lanes = set(mi_by_boss.get(boss) or [])
        add(f"mergeinputs:{boss}:LANE1", l1 in lanes, str(sorted(lanes)))
        add(f"mergeinputs:{boss}:LANE2", l2 in lanes, str(sorted(lanes)))

    # MERGE_316 presence / release
    rows316 = {_clean(r.get("Name")): r for r in (mi_rows.get("MERGE_316_SPUR") or [])}
    for lane, expect in EXPECTED_316_LANE_IO.items():
        row = rows316.get(lane) or {}
        add(
            f"merge316:{lane}:presence",
            _clean(row.get("Presense") or row.get("Presence")) == expect["presence"],
            _clean(row.get("Presense") or row.get("Presence")),
        )
        add(
            f"merge316:{lane}:release_io",
            _clean(row.get("ReleaseIO")) == expect["release_io"],
            _clean(row.get("ReleaseIO")),
        )

    # M314 mtrchain fields
    m314 = ev.get("m314") or {}
    for field, expect in EXPECTED_M314.items():
        add(f"m314:{field}", m314.get(field) == expect, str(m314.get(field)))

    # Physical chain M314 -> P314 -> P316 CURVE
    m316 = by_name.get("MERGE_316_SPUR") or {}
    add(
        "merge316:phys_chain_discovery",
        m316.get("inductPhysicalRelease") == "P314" and m316.get("inductNext") == "P316",
        f"phys={m316.get('inductPhysicalRelease')} next={m316.get('inductNext')}",
    )
    add(
        "merge316:phys_chain_mtrchain",
        m314.get("Motor_Chained1") == "P314" and m314.get("Motor_Chained2") == "P316",
        str(m314),
    )
    add("merge316:p316_curve", ev.get("p316_type") == "CURVE", str(ev.get("p316_type")))

    # CP4 models when available
    cp4_bosses = set(ev.get("cp4_bosses") or [])
    if cp4_bosses:
        for boss in EXPECTED_BOSSES:
            add(f"cp4_merge_boss:{boss}", boss in cp4_bosses, ",".join(sorted(cp4_bosses)))
        proof = (ev.get("cp4_merge_proofs") or {}).get("MERGE_316_SPUR") or {}
        add("cp4_merge316_proof", proof.get("status") == "PROVEN", str(proof.get("status")))
        cm = ev.get("cp4_m314") or {}
        if cm:
            chained1 = next(
                (c.get("raw") for c in (cm.get("chained") or []) if c.get("slot") == 1),
                None,
            )
            add(
                "cp4_m314_fields",
                (cm.get("motorNdx") or {}).get("raw") == "M314"
                and chained1 == "P314"
                and (cm.get("motorAux") or {}).get("raw") == "LATCH_MERGE_316"
                and (cm.get("enabled") or {}).get("raw") == "M136_AUX",
                str({
                    "ndx": (cm.get("motorNdx") or {}).get("raw"),
                    "chained1": chained1,
                    "aux": (cm.get("motorAux") or {}).get("raw"),
                    "enabled": (cm.get("enabled") or {}).get("raw"),
                }),
            )
    else:
        add("cp4_models_available", False, str(ev.get("cp4_source")))

    # MERGE_324 when evidence present
    m324 = by_name.get("MERGE_324_SPUR")
    if m324:
        rows324 = {_clean(r.get("Name")): r for r in (mi_rows.get("MERGE_324_SPUR") or [])}
        for lane, expect in EXPECTED_324_LANE_IO.items():
            row = rows324.get(lane) or {}
            add(
                f"merge324:{lane}:presence",
                _clean(row.get("Presense") or row.get("Presence")) == expect["presence"],
                _clean(row.get("Presense") or row.get("Presence")),
            )
            add(
                f"merge324:{lane}:release_io",
                _clean(row.get("ReleaseIO")) == expect["release_io"],
                _clean(row.get("ReleaseIO")),
            )
        m322 = ev.get("m322") or {}
        for field, expect in EXPECTED_M322.items():
            add(f"m322:{field}", m322.get(field) == expect, str(m322.get(field)))
        add(
            "merge324:phys_chain_discovery",
            m324.get("inductPhysicalRelease") == "P322" and m324.get("inductNext") == "P324",
            f"phys={m324.get('inductPhysicalRelease')} next={m324.get('inductNext')}",
        )
        add(
            "merge324:phys_chain_mtrchain",
            m322.get("Motor_Chained1") == "P322" and m322.get("Motor_Chained2") == "P324",
            str(m322),
        )
        add("merge324:p324_curve", ev.get("p324_type") == "CURVE", str(ev.get("p324_type")))
    else:
        add("merge324:evidence_optional_absent", True, "MERGE_324_SPUR not in discovery")

    # Counts sanity (non-fabricated, positive for core tables)
    counts = ev.get("counts") or {}
    add("count:MergeBoss>=4", int(counts.get("MergeBoss") or 0) >= 4, str(counts.get("MergeBoss")))
    add("count:MergeInputs>=8", int(counts.get("MergeInputs") or 0) >= 8, str(counts.get("MergeInputs")))
    add("count:Mtrchain>0", int(counts.get("Mtrchain") or 0) > 0, str(counts.get("Mtrchain")))
    add("count:Jamcheck>0", int(counts.get("Jamcheck") or 0) > 0, str(counts.get("Jamcheck")))
    add("count:Jamzones>0", int(counts.get("Jamzones") or 0) > 0, str(counts.get("Jamzones")))
    add("count:CURVE>0", int(counts.get("CURVE") or 0) > 0, str(counts.get("CURVE")))

    return checks


def write_report(ev: dict[str, Any], checks: list[tuple[str, bool, str]]) -> Path:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(ev, checks=checks), encoding="utf-8")
    return REPORT_PATH


class TestTransportationFreeze(unittest.TestCase):
    """Permanent freeze regression for ORNCCP2 transportation merges."""

    run_dir: Path | None = None
    evidence: dict[str, Any] | None = None
    checks: list[tuple[str, bool, str]] | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.run_dir = resolve_ornccp2_run()
        if cls.run_dir is None:
            raise unittest.SkipTest(
                "ORNCCP2 RUN missing — expected workspace/active/RUN or any "
                "PLC2 ORNCCP2 RUN under workspace/. Freeze assertions remain "
                f"encoded: bosses={list(EXPECTED_BOSSES)} lanes={EXPECTED_LANES}"
            )
        cls.evidence = collect_freeze_evidence(cls.run_dir)
        cls.checks = evaluate_checks(cls.evidence)
        write_report(cls.evidence, cls.checks)

    def test_encoded_assertions_present(self) -> None:
        self.assertEqual(len(EXPECTED_BOSSES), 4)
        self.assertEqual(set(EXPECTED_TYPES.values()), {"SPUR", "2-1", "3-1"})
        self.assertIn("LANE2_P312", EXPECTED_LANES["MERGE_316_SPUR"])
        self.assertEqual(EXPECTED_316_PHYS[-1], "CURVE")

    def test_all_freeze_checks(self) -> None:
        self.assertIsNotNone(self.checks)
        failures = [f"{n}: {d}" for n, ok, d in (self.checks or []) if not ok]
        self.assertFalse(failures, "freeze failures:\n- " + "\n- ".join(failures))

    def test_report_written(self) -> None:
        self.assertTrue(REPORT_PATH.is_file(), str(REPORT_PATH))


def main() -> int:
    run_dir = resolve_ornccp2_run()
    if run_dir is None:
        msg = (
            "SKIP: ORNCCP2 RUN missing. Encoded assertions:\n"
            f"  bosses={list(EXPECTED_BOSSES)}\n"
            f"  lanes={EXPECTED_LANES}\n"
            f"  types={EXPECTED_TYPES}\n"
            f"  merge316_chain={EXPECTED_316_LANE_IO} / {EXPECTED_M314} / {EXPECTED_316_PHYS}\n"
        )
        print(msg)
        # Still emit a stub report documenting skip + encoded assertions
        stub = {
            "run_dir": None,
            "machine": MACHINE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "discovery": {},
            "by_name": {},
            "counts": {
                "MergeBoss": 0,
                "MergeInputs": 0,
                "Jamcheck": 0,
                "Jamzones": 0,
                "Mtrchain": 0,
                "CURVE": 0,
                "Areas": 0,
                "review_unresolved": 0,
            },
            "count_detail": {"discovery": {}, "note": "RUN missing — counts not measured"},
            "mergeboss_names": [],
            "mergeinputs_by_boss": {},
            "mergeinputs_rows_by_boss": {},
            "m314": {},
            "m322": {},
            "p316_type": "",
            "p324_type": "",
            "cp4_source": "skipped",
            "cp4_bosses": [],
            "cp4_m314": None,
            "cp4_m322": None,
            "cp4_merge_proofs": {},
            "cp4_merge_counts": {},
            "cp4_mtr_counts": {},
            "cp4_jam_counts": {},
        }
        checks = [("run_available", False, "ORNCCP2 RUN missing — SkipTest")]
        path = write_report(stub, checks)
        print(f"Wrote skip report: {path}")
        return 0

    ev = collect_freeze_evidence(run_dir)
    checks = evaluate_checks(ev)
    path = write_report(ev, checks)
    failed = [n for n, ok, _ in checks if not ok]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    print(f"\nReport: {path}")
    print(f"Result: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
