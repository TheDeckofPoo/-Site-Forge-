#!/usr/bin/env python3
"""One-shot Site Forge tools/scripts cleanup executor.

NOT part of production runtime. Classifies, deletes dead archaeology,
moves diagnostics and tests, writes manifests. Does not change compiler
semantics.

Usage (from repo root):
  python tools/scripts/_cleanup_scripts_executor.py --dry-run
  python tools/scripts/_cleanup_scripts_executor.py --apply
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
DIAG = ROOT / "tools" / "diagnostics"
TESTS = ROOT / "tests"
MANIFEST = ROOT / "exports" / "stabilization" / "script_cleanup_manifest.json"
DOC = ROOT / "docs" / "SCRIPT_CLEANUP.md"
GRAPH = ROOT / "exports" / "stabilization" / "script_cleanup_dependency_graph.json"
INV = ROOT / "exports" / "stabilization" / "python_script_inventory.json"

# Desktop/dashboard production entrypoints (from desktop/main.js)
PRODUCTION_ENTRYPOINTS = {
    "_deploy_designer_safe_ignition.py",
    "apply_recipe.py",
    "fix_ignition_project_attrs.py",
    "fortna_autogen.py",
    "fortna_cp5a_orchestrator.py",
    "fortna_cp5a_transport_mapper.py",
    "fortna_hardware_io_model.py",
    "fortna_ignition_build.py",
    "fortna_io_banks.py",
    "fortna_perspective_pack.py",
    "fortna_plc_export.py",
    "fortna_prism_ingest.py",
    "fortna_prism_twin.py",
    "fortna_run_physical_layout.py",
    "fortna_run_workspace_discover.py",
    "fortna_runtime_provenance.py",
    "fortna_safety_model.py",
    "fortna_transport_graph.py",
    "fortna_workbook.py",
    "index_docs.py",
}

# Protected — never DELETE even if callers look empty
PROTECTED_STEMS = {
    "fortna_autogen",
    "fortna_site_model",
    "fortna_safety_model",
    "fortna_estop_model",
    "fortna_es_compiler",
    "fortna_cp4_discovery",
    "fortna_cp4_pass1",
    "fortna_cp4_pass2",
    "fortna_cp4_sawtooth",
    "fortna_cp4_semantics_compile",
    "fortna_autogen_provenance",
    "fortna_studio_preflight",
    "fortna_l5x_structured_data",
    "fortna_l5x_studio_structure",
    "fortna_operand_validator",
    "fortna_hardware_io_model",
    "fortna_hardware_family",
    "fortna_hardware_io_overrides",
    "fortna_transport_graph",
    "fortna_mnu_runtime",
    "fortna_mnu_schema",
    "fortna_run_loader",
    "fortna_asc",
    "fortna_schema_ir",
    "fortna_machine_closure",
    "fortna_fortna_table_resolver",
    "fortna_plc2_merge_discovery",
    "validate_plc_export",
}

# Reusable diagnostics to KEEP and MOVE (not delete)
# Only move diagnostics with NO non-test Python importers in tools/scripts.
# Modules imported by acceptance/core gates stay in tools/scripts/ (KEEP_DIAGNOSTIC KEPT).
MOVE_DIAGNOSTIC = {
    "diagnose_plc2_merge_pipeline.py",
    "diagnose_plc2_topology_merges.py",
    "_audit_hollow_l5x.py",
    "_audit_vfd_flt_semantics.py",
    "fortna_plc2_fidelity_audit.py",
    "fortna_run_autobuild_audit.py",
    "fortna_sawtooth_library_audit.py",
    "fortna_unresolved_symbol_audit.py",
    "fortna_cp4_pass1_self_audit.py",
    "fortna_ui_workflow_smoke.py",
    "_deploy_smoke_view.py",
    "_gen_geometry_acceptance.py",
    "fortna_io_channel_trace.py",
    "fortna_io_oracle_diff.py",
}
# Imported by CP2 gates / tests — stay put to avoid import path risk
STAY_IN_SCRIPTS_DIAGNOSTIC = {
    "fortna_l5x_compare.py",
    "fortna_physical_overlap_audit.py",
}

# Explicit DELETE_DEAD filename prefixes / names (still need zero callers)
DELETE_PREFIXES = ("_emergency_", "_tmp_")
# Only delete when zero importers AND zero text refs. Items explore marked REVIEW
# stay REVIEW even if archaeology-named.
DELETE_EXACT: set[str] = set()  # prefer prefix-based deletes; REVIEW otherwise

TEST_GROUP_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("decoder", re.compile(r"^test_fortna_(asc|mnu|run_loader|reference|identity|knowledge|control_model|physical_geometry|geometry)|test_fortna_asc|test_source_truth|test_symbol_closure|test_canonical_subsystem|test_blind_genericity|test_fortnaplus", re.I)),
    ("semantics", re.compile(r"^test_cp4_|test_sawtooth|test_activity|test_controller_scope|test_cp2_ownership|test_transportation_freeze|test_operand|test_program_pack|test_partial_build|test_live_canonical", re.I)),
    ("compiler", re.compile(r"^test_l5x_|test_es_compiler|test_autogen_|test_export_current|test_area_rename|test_m220|test_curve_display|test_display_layout|test_mscreno|test_project_", re.I)),
    ("safety", re.compile(r"^test_safety_|test_default_area_safety|test_estop_|test_multi_area", re.I)),
    ("transport", re.compile(r"^test_transport_|test_native_merge|test_plc2_merge|test_auto_build_physical", re.I)),
    ("io", re.compile(r"^test_io|test_hardware|test_iomap|test_vfd|test_plc2_configio|test_plc5_io", re.I)),
    ("sorter", re.compile(r"^test_sorter|test_plc5_sorter|test_cp5", re.I)),
    ("acceptance", re.compile(r"^test_cp2_|test_validation|test_runtime_acceptance|test_decoder_acceptance|test_engineer|test_knowledge_driven|test_cp5a|test_machine_closure|test_fortna_p406|test_run_driven", re.I)),
]


def _git_tracked() -> set[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "tools/scripts"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return set()
    return {ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


_IGNORE_REF_SUFFIXES = (
    "docs/SCRIPT_CLEANUP.md",
    "exports/stabilization/script_cleanup_manifest.json",
    "exports/stabilization/script_cleanup_dependency_graph.json",
    "exports/stabilization/script_cleanup_dependency_summary.md",
    "exports/stabilization/script_cleanup_baseline.json",
    "exports/stabilization/script_cleanup_baseline_tests.json",
    "tools/scripts/_cleanup_scripts_executor.py",
)


def _scan_text_refs(stems: set[str]) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = defaultdict(set)
    files: list[Path] = []
    for base, patterns in [
        (ROOT / "desktop", ["*.js", "*.ps1", "*.bat"]),
        (ROOT / "dashboard", ["*.js"]),
        (ROOT / "docs", ["*.md"]),
        (ROOT, ["*.bat", "*.ps1"]),
    ]:
        if not base.exists() and base != ROOT:
            continue
        if base == ROOT:
            files.extend(ROOT.glob("*.bat"))
            files.extend(ROOT.glob("*.ps1"))
            continue
        for pat in patterns:
            files.extend(base.rglob(pat))
    # Also scan scripts for subprocess string refs
    files.extend(SCRIPTS.rglob("*.py"))
    for path in files:
        txt = _read_text(path)
        if not txt:
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in _IGNORE_REF_SUFFIXES or rel.startswith("exports/stabilization/script_cleanup"):
            continue
        for stem in stems:
            if f"{stem}.py" in txt or f"'{stem}'" in txt or f'"{stem}"' in txt:
                # avoid self
                if path.stem == stem:
                    continue
                refs[stem].add(rel)
    return refs


def _scan_imports() -> dict[str, set[str]]:
    importers: dict[str, set[str]] = defaultdict(set)
    for path in SCRIPTS.rglob("*.py"):
        src = _read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
                # also from fortna_semantics.x
                parts = node.module.split(".")
                if parts[0] == "fortna_semantics" and len(parts) > 1:
                    mods.append(parts[1])
            for m in mods:
                if m.startswith("fortna_") or m.startswith("_") or m in {
                    "apply_recipe",
                    "index_docs",
                    "validate_plc_export",
                    "diagnose_plc2_merge_pipeline",
                    "diagnose_plc2_topology_merges",
                }:
                    if path.stem != m:
                        importers[m].add(rel)
    return importers


def _test_group(name: str) -> str:
    for group, rx in TEST_GROUP_RULES:
        if rx.search(name):
            return group
    return "regression"


def _patch_test_bootstrap(text: str, group: str) -> str:
    """Ensure SCRIPTS points at tools/scripts after move to tests/<group>/."""
    # Insert/replace common bootstrap patterns.
    marker = "# --- siteforge test path bootstrap (cleanup) ---"
    if marker in text:
        return text
    bootstrap = (
        f"{marker}\n"
        "from pathlib import Path as _SFPath\n"
        "import sys as _SFSys\n"
        "_SF_REPO = _SFPath(__file__).resolve().parents[2]\n"
        "_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'\n"
        "if str(_SF_SCRIPTS) not in _SFSys.path:\n"
        "    _SFSys.path.insert(0, str(_SF_SCRIPTS))\n"
        "# Prefer canonical names used by existing tests:\n"
        "SCRIPTS = _SF_SCRIPTS\n"
        "ROOT = _SF_REPO\n"
        "REPO_ROOT = _SF_REPO\n"
        "# --- end bootstrap ---\n\n"
    )
    # Place after future import / module docstring if present
    lines = text.splitlines(keepends=True)
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    # skip module docstring
    i = insert_at
    if i < len(lines) and lines[i].lstrip().startswith('"""'):
        if lines[i].count('"""') >= 2 and lines[i].strip() != '"""':
            insert_at = i + 1
        else:
            i += 1
            while i < len(lines) and '"""' not in lines[i]:
                i += 1
            insert_at = min(i + 1, len(lines))
    # skip from __future__
    while insert_at < len(lines) and (
        lines[insert_at].startswith("from __future__")
        or lines[insert_at].strip() == ""
    ):
        insert_at += 1
        if insert_at < len(lines) and lines[insert_at - 1].startswith("from __future__"):
            break
    # If file already defines SCRIPTS = Path(__file__).resolve().parent, comment it later via rewrite
    new_text = "".join(lines[:insert_at]) + bootstrap + "".join(lines[insert_at:])
    # Neutralize old SCRIPTS = Path(__file__).resolve().parent assignments
    new_text = re.sub(
        r"^(SCRIPTS\s*=\s*Path\(__file__\)\.resolve\(\)\.parent)\s*$",
        r"SCRIPTS = _SF_SCRIPTS  # was: \1",
        new_text,
        flags=re.M,
    )
    new_text = re.sub(
        r"^(SCRIPT_DIR\s*=\s*Path\(__file__\)\.resolve\(\)\.parent)\s*$",
        r"SCRIPT_DIR = _SF_SCRIPTS  # was: \1",
        new_text,
        flags=re.M,
    )
    return new_text


def classify_all() -> dict[str, dict]:
    tracked = _git_tracked()
    py_files = sorted(
        p for p in SCRIPTS.rglob("*.py") if p.is_file() and "__pycache__" not in p.parts
    )
    stems = {p.stem for p in py_files}
    importers = _scan_imports()
    text_refs = _scan_text_refs(stems)
    inv_by_path: dict[str, dict] = {}
    if INV.is_file():
        inv = json.loads(INV.read_text(encoding="utf-8"))
        for f in inv.get("files") or []:
            inv_by_path[f["path"].replace("\\", "/")] = f

    records: dict[str, dict] = {}
    for path in py_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        stem = path.stem
        name = path.name
        is_sem = "fortna_semantics" in path.parts
        is_test = name.startswith("test_") and name.endswith(".py")
        is_js_test = False
        imp = sorted(importers.get(stem) or [])
        refs = sorted(text_refs.get(stem) or [])
        # filter self-ish refs
        refs = [r for r in refs if not r.endswith("/" + name) and r != rel]
        inv = inv_by_path.get(rel) or {}
        prev = inv.get("classification")

        status = "REVIEW"
        reason = "insufficient evidence"
        action = "KEPT"

        if is_sem or name == "__init__.py":
            status = "KEEP_CORE"
            reason = "fortna_semantics package / init"
        elif name == "_cleanup_scripts_executor.py":
            status = "REVIEW"
            reason = "one-shot cleanup executor — leave until after apply commit; delete in follow-up if desired"
        elif name in PRODUCTION_ENTRYPOINTS:
            status = "KEEP_PRODUCTION"
            reason = "desktop/main.js or production subprocess entrypoint"
        elif stem in PROTECTED_STEMS:
            status = "KEEP_CORE"
            reason = "protected core/compiler/decoder"
        elif is_test:
            status = "KEEP_TEST"
            reason = "permanent regression/unit test"
            action = "MOVED"
        elif name.startswith("test_") and name.endswith(".js"):
            status = "KEEP_TEST"
            reason = "js transport test"
            action = "MOVED"
        elif name in STAY_IN_SCRIPTS_DIAGNOSTIC:
            status = "KEEP_DIAGNOSTIC"
            reason = "diagnostic imported by acceptance/core — keep in tools/scripts"
            action = "KEPT"
        elif name in MOVE_DIAGNOSTIC:
            # Only move if no non-test importers
            non_test_imp = [
                x
                for x in (importers.get(stem) or [])
                if "/test_" not in x and not Path(x).name.startswith("test_")
            ]
            if non_test_imp:
                status = "KEEP_DIAGNOSTIC"
                reason = f"diagnostic has importers {non_test_imp[:3]} — keep in tools/scripts"
                action = "KEPT"
            else:
                status = "KEEP_DIAGNOSTIC"
                reason = "reusable developer diagnostic (no non-test importers)"
                action = "MOVED"
        elif name.startswith(DELETE_PREFIXES):
            if not imp and not refs:
                status = "DELETE_DEAD"
                reason = "emergency/tmp archaeology with no callers"
                action = "DELETED"
            else:
                status = "REVIEW"
                reason = f"emergency/tmp but has refs: imp={imp[:3]} refs={refs[:3]}"
        elif name in DELETE_EXACT:
            if not imp and not refs and stem not in PROTECTED_STEMS:
                status = "DELETE_DEAD"
                reason = "one-off research/investigate with no callers"
                action = "DELETED"
            else:
                status = "REVIEW"
                reason = f"delete-candidate but refs present: {imp[:2]} {refs[:2]}"
        elif name.startswith("fortna_") or name.startswith("apply_") or name.startswith("validate_") or name.startswith("fix_"):
            # Core-looking modules
            if "compiler" in name or name.endswith("_compiler.py"):
                status = "KEEP_CORE"
                reason = "compiler-named module retained even if callers sparse"
            elif imp or (inv.get("production_dependency") == "yes"):
                status = "KEEP_CORE"
                reason = "imported or production-dependent module"
            elif any(r.startswith("desktop/") or r.startswith("dashboard/") for r in refs):
                status = "KEEP_PRODUCTION"
                reason = "desktop/dashboard text reference"
            elif prev in {"ACCEPTANCE", "CP5_INTEGRATION"}:
                status = "KEEP_ACCEPTANCE"
                reason = f"inventory {prev}"
            elif prev == "DIAGNOSTIC" or name in MOVE_DIAGNOSTIC:
                status = "KEEP_DIAGNOSTIC"
                reason = "diagnostic — keep unless explicitly in MOVE set with no importers"
                action = "KEPT"
            elif prev == "ARCHAEOLOGY" and not imp and not refs:
                status = "DELETE_DEAD"
                reason = "inventory ARCHAEOLOGY + zero live callers"
                action = "DELETED"
            elif prev == "LEGACY_CANDIDATE":
                status = "REVIEW"
                reason = "legacy candidate — do not delete without proof"
            else:
                status = "REVIEW"
                reason = "fortna_* with no live callers — leave in place"
        else:
            if not imp and not refs:
                status = "REVIEW"
                reason = "unknown script, no callers — leave in place"
            else:
                status = "KEEP_CORE"
                reason = "has callers"

        # Acceptance tooling
        if status == "REVIEW" and prev in {"ACCEPTANCE", "CP5_INTEGRATION"}:
            status = "KEEP_ACCEPTANCE"
            reason = f"inventory {prev} retained"

        # Never delete protected / production
        if status == "DELETE_DEAD" and (
            name in PRODUCTION_ENTRYPOINTS or stem in PROTECTED_STEMS or is_test
        ):
            status = "KEEP_CORE"
            action = "KEPT"
            reason = "blocked delete of protected/production/test"

        records[rel] = {
            "old_path": rel,
            "action": action if status.startswith("KEEP") and action == "MOVED" else (
                "DELETED" if status == "DELETE_DEAD" else (
                    "MOVED" if status == "KEEP_TEST" or (status == "KEEP_DIAGNOSTIC" and name in MOVE_DIAGNOSTIC) else "KEPT"
                )
            ),
            "new_path": None,
            "previous_classification": prev,
            "proposed_status": status,
            "known_callers": imp[:20],
            "subprocess_or_text_refs": refs[:20],
            "reason": reason,
            "tracked": rel in tracked,
            "stem": stem,
            "name": name,
        }
        # refine action for KEEP_TEST / MOVE diagnostic
        if status == "KEEP_TEST":
            records[rel]["action"] = "MOVED"
        elif status == "KEEP_DIAGNOSTIC" and name in MOVE_DIAGNOSTIC:
            records[rel]["action"] = "MOVED"
        elif status == "DELETE_DEAD":
            records[rel]["action"] = "DELETED"
        else:
            records[rel]["action"] = "KEPT"

    return records


def apply_actions(records: dict[str, dict], *, dry_run: bool) -> dict[str, dict]:
    DIAG.mkdir(parents=True, exist_ok=True)
    for group in {g for g, _ in TEST_GROUP_RULES} | {"regression"}:
        (TESTS / group).mkdir(parents=True, exist_ok=True)

    # Also move JS tests under tools/scripts/test_*.js
    for path in sorted(SCRIPTS.glob("test_*.js")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel not in records:
            records[rel] = {
                "old_path": rel,
                "action": "MOVED",
                "new_path": None,
                "previous_classification": "TEST",
                "proposed_status": "KEEP_TEST",
                "known_callers": [],
                "subprocess_or_text_refs": [],
                "reason": "js transport test",
                "tracked": True,
                "stem": path.stem,
                "name": path.name,
            }

    for rel, rec in list(records.items()):
        old = ROOT / rel
        if not old.exists():
            rec["note"] = "missing on disk"
            continue
        status = rec["proposed_status"]
        name = rec["name"]

        if status == "DELETE_DEAD":
            rec["action"] = "DELETED"
            rec["new_path"] = None
            if not dry_run:
                if rec.get("tracked"):
                    subprocess.check_call(["git", "rm", "-f", "--", rel], cwd=ROOT)
                else:
                    old.unlink()
            continue

        if status == "KEEP_TEST" and name.startswith("test_"):
            group = _test_group(name) if name.endswith(".py") else "transport"
            dest = TESTS / group / name
            rec["action"] = "MOVED"
            rec["new_path"] = str(dest.relative_to(ROOT)).replace("\\", "/")
            if dry_run:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith(".py"):
                text = _read_text(old)
                text = _patch_test_bootstrap(text, group)
                dest.write_text(text, encoding="utf-8")
                if rec.get("tracked"):
                    subprocess.check_call(["git", "rm", "-f", "--", rel], cwd=ROOT)
                else:
                    old.unlink()
                subprocess.check_call(["git", "add", "-f", "--", rec["new_path"]], cwd=ROOT)
            else:
                if rec.get("tracked"):
                    subprocess.check_call(["git", "mv", "-f", rel, rec["new_path"]], cwd=ROOT)
                else:
                    shutil.move(str(old), str(dest))
                    subprocess.check_call(["git", "add", "-f", "--", rec["new_path"]], cwd=ROOT)
            continue

        if status == "KEEP_DIAGNOSTIC" and name in MOVE_DIAGNOSTIC:
            dest = DIAG / name
            rec["action"] = "MOVED"
            rec["new_path"] = str(dest.relative_to(ROOT)).replace("\\", "/")
            if dry_run:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rec.get("tracked"):
                subprocess.check_call(["git", "mv", "-f", rel, rec["new_path"]], cwd=ROOT)
            else:
                shutil.move(str(old), str(dest))
                subprocess.check_call(["git", "add", "-f", "--", rec["new_path"]], cwd=ROOT)
            continue

        rec["action"] = "KEPT"
        rec["new_path"] = rel

    return records


def write_manifest(records: dict[str, dict], baseline_sha: str) -> None:
    counts: dict[str, int] = defaultdict(int)
    actions: dict[str, int] = defaultdict(int)
    for rec in records.values():
        counts[rec["proposed_status"]] += 1
        actions[rec["action"]] += 1
    doc = {
        "kind": "ScriptCleanupManifest",
        "version": 1,
        "baseline_sha": baseline_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts_by_status": dict(counts),
        "counts_by_action": dict(actions),
        "files": list(records.values()),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    GRAPH.write_text(
        json.dumps(
            {
                "baseline_sha": baseline_sha,
                "scripts": {
                    k: {
                        "proposed_status": v["proposed_status"],
                        "importers": v.get("known_callers"),
                        "subprocess_or_text_refs": v.get("subprocess_or_text_refs"),
                        "reason": v.get("reason"),
                        "tracked": v.get("tracked"),
                    }
                    for k, v in records.items()
                },
                "counts": dict(counts),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Script Cleanup Manifest",
        "",
        f"- Baseline SHA: `{baseline_sha}`",
        f"- Generated: {doc['generated_at']}",
        "",
        "## Counts by status",
        "",
        "```",
    ]
    for k in sorted(counts):
        lines.append(f"{k:20} {counts[k]}")
    lines.extend(["```", "", "## Counts by action", "", "```"])
    for k in sorted(actions):
        lines.append(f"{k:12} {actions[k]}")
    lines.extend(["```", "", "## Deleted", ""])
    deleted = [r for r in records.values() if r["action"] == "DELETED"]
    if not deleted:
        lines.append("_None._")
    else:
        for r in sorted(deleted, key=lambda x: x["old_path"]):
            lines.append(f"- `{r['old_path']}` — {r['reason']}")
    lines.extend(["", "## Moved tests (sample)", ""])
    moved_t = [r for r in records.values() if r["action"] == "MOVED" and r["proposed_status"] == "KEEP_TEST"]
    for r in sorted(moved_t, key=lambda x: x["old_path"])[:40]:
        lines.append(f"- `{r['old_path']}` → `{r['new_path']}`")
    if len(moved_t) > 40:
        lines.append(f"- … {len(moved_t) - 40} more")
    lines.extend(["", "## Moved diagnostics", ""])
    moved_d = [r for r in records.values() if r["action"] == "MOVED" and r["proposed_status"] == "KEEP_DIAGNOSTIC"]
    for r in sorted(moved_d, key=lambda x: x["old_path"]):
        lines.append(f"- `{r['old_path']}` → `{r['new_path']}`")
    lines.extend(["", "## REVIEW (left in place)", ""])
    review = [r for r in records.values() if r["proposed_status"] == "REVIEW"]
    for r in sorted(review, key=lambda x: x["old_path"]):
        lines.append(f"- `{r['old_path']}` — {r['reason']}")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Git history is the archive; no junk `archive/` folder.",
            "- New tests belong under `tests/`.",
            "- New diagnostics belong under `tools/diagnostics/`.",
            "- Do not commit `_tmp_*` / `_emergency_*` under `tools/scripts/`.",
            "- Core modules were not consolidated in this cleanup.",
            "",
        ]
    )
    DOC.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 2
    dry = not args.apply
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    records = classify_all()
    records = apply_actions(records, dry_run=dry)
    write_manifest(records, sha)
    counts: dict[str, int] = defaultdict(int)
    actions: dict[str, int] = defaultdict(int)
    for r in records.values():
        counts[r["proposed_status"]] += 1
        actions[r["action"]] += 1
    print(json.dumps({"dry_run": dry, "counts": dict(counts), "actions": dict(actions)}, indent=2))
    print(f"manifest: {MANIFEST}")
    print(f"doc: {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
