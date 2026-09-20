#!/usr/bin/env python3
"""Four-site AI I/O blind evaluation harness (offline / mocked).

Sites: ORINDYAC6, MSCATL_CP3, MSCRENOPICK, ORDENCP3

Never exposes finished/reference L5X to the AI.
Does not make live OpenAI calls — uses empty/mock proposals for BEFORE/AFTER
baseline stamps unless --mock-dir provides per-site mock JSON.

Produces: exports/ai-io/<site>/evaluation.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from apply_recipe import extract_run  # noqa: E402
from fortna_ai_io_analyze import analyze  # noqa: E402

SITES: list[dict[str, Any]] = [
    {
        "site": "ORINDYAC6",
        "machine": "ORINDYAC6",
        "run_candidates": [
            REPO_ROOT / "workspace" / "_virgin_orindy" / "RUN",
        ],
        "tar_candidates": [
            REPO_ROOT / "workspace" / "inbox" / "20260624-1641-OReillyindy-ORINDYAC6-RUN.tar.gz",
        ],
    },
    {
        "site": "MSCATL_CP3",
        "machine": "MSCATL_CP3",
        "run_candidates": [
            REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN",
        ],
        "tar_candidates": [
            REPO_ROOT / "workspace" / "inbox" / "20260813-1428-MSCATL-MSCATL_CP3-RUN.tar.gz",
            Path(r"C:\Users\curtiskricke\Desktop\MSC ATL\20260813-1428-MSCATL-MSCATL_CP3-RUN.tar.gz"),
        ],
        "related_tar_note": (
            "Pass --fixture MSCATL_CP3=<RUN_DIR_OR_TAR> when not in default locations. "
            "Never silently substitute MSCATL_CP4."
        ),
    },
    {
        "site": "MSCRENOPICK",
        "machine": "MSCRENOPICK",
        "run_candidates": [
            REPO_ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN",
        ],
        "tar_candidates": [
            REPO_ROOT / "workspace" / "inbox" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz",
        ],
    },
    {
        "site": "ORDENCP3",
        "machine": "ORDENCP3",
        "run_candidates": [
            REPO_ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN",
            REPO_ROOT / "workspace" / "_orden_peek" / "ORDENCP3" / "RUN",
        ],
        "tar_candidates": [
            REPO_ROOT / "workspace" / "inbox" / "20260622-1013-OReillyDC27-ORDENCP3-RUN.tar.gz",
        ],
        "fixture_role": "alternate_evidence",
    },
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_run_dir(path: Path) -> Path | None:
    """Accept a RUN dir or a parent that contains RUN/project.cfg."""
    path = Path(path)
    if (path / "project.cfg").is_file():
        return path
    nested = path / "RUN"
    if (nested / "project.cfg").is_file():
        return nested
    return None


def resolve_run(
    site: dict[str, Any],
    *,
    extract: bool = True,
    explicit_fixture: Path | None = None,
) -> tuple[Path | None, str]:
    # Explicit --fixture SITE=PATH wins (RUN dir or .tar.gz)
    if explicit_fixture is not None:
        fx = Path(explicit_fixture)
        if fx.is_dir():
            run = _as_run_dir(fx)
            if run is not None:
                return run, f"explicit_fixture_dir:{fx}"
            return None, f"explicit_fixture_dir_missing_project_cfg:{fx}"
        if fx.is_file() and (
            fx.name.endswith(".tar.gz") or fx.suffix.lower() in {".tgz", ".gz", ".zip"}
        ):
            dest = REPO_ROOT / "workspace" / f"_{site['site'].lower()}_peek" / site["site"]
            dest.mkdir(parents=True, exist_ok=True)
            try:
                run_dir = extract_run(fx, dest)
            except Exception as exc:
                return None, f"explicit_fixture_extract_failed:{fx.name}:{exc}"
            run = _as_run_dir(Path(run_dir)) or _as_run_dir(dest / "RUN")
            if run is not None:
                return run, f"explicit_fixture_tar:{fx.name}"
            return None, f"explicit_fixture_tar_no_project_cfg:{fx.name}"
        return None, f"explicit_fixture_unusable:{fx}"

    for cand in site.get("run_candidates") or []:
        run = _as_run_dir(Path(cand))
        if run is not None:
            return run, "extracted_run"
    if not extract:
        return None, "missing"
    for tar in site.get("tar_candidates") or []:
        tar = Path(tar)
        if not tar.is_file():
            continue
        dest = REPO_ROOT / "workspace" / f"_{site['site'].lower()}_peek" / site["site"]
        dest.mkdir(parents=True, exist_ok=True)
        marker = dest / "RUN" / "project.cfg"
        if marker.is_file():
            return dest / "RUN", "cached_extract"
        try:
            run_dir = extract_run(tar, dest)
        except Exception as exc:
            return None, f"extract_failed:{tar.name}:{exc}"
        run = _as_run_dir(Path(run_dir)) or _as_run_dir(dest / "RUN")
        if run is not None:
            # Normalize to dest/RUN when extract_run returns nested path
            run_dest = dest / "RUN"
            if run.resolve() != run_dest.resolve():
                if run_dest.exists():
                    shutil.rmtree(run_dest, ignore_errors=True)
                shutil.move(str(run), str(run_dest))
                return run_dest, f"extracted_from:{tar.name}"
            return run, f"extracted_from:{tar.name}"
        return None, f"tar_extracted_but_no_project_cfg:{tar.name}"
    note = site.get("related_tar_note")
    if note:
        return None, f"missing_run_and_archive ({note})"
    return None, "missing_run_and_archive"


def _empty_mock(project: str, machine: str) -> dict[str, Any]:
    """Offline mock: no AI proposals — measures deterministic BEFORE baseline."""
    return {
        "project": project,
        "machine": machine,
        "claims": [],
        "unresolved": [],
        "warnings": ["offline_eval_stub: no live OpenAI call"],
    }


def evaluate_site(
    site: dict[str, Any],
    *,
    extract: bool = True,
    mock_path: Path | None = None,
    explicit_fixture: Path | None = None,
) -> dict[str, Any]:
    name = site["site"]
    machine = site["machine"]
    run_dir, how = resolve_run(site, extract=extract, explicit_fixture=explicit_fixture)
    out_dir = REPO_ROOT / "exports" / "ai-io" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    if run_dir is None:
        evaluation = {
            "kind": "ai_io_evaluation",
            "version": 1,
            "generated_at": _ts(),
            "project": name,
            "machine": machine,
            "run_available": False,
            "resolve_note": how,
            "related_tar_note": site.get("related_tar_note"),
            "fixture_role": site.get("fixture_role"),
            "BEFORE_AI": {
                "raw_physical_claims": None,
                "accounted_claims": None,
                "lost_claims": None,
                "note": "RUN not available — not an empty PASS",
            },
            "AFTER_AI": {
                "raw_physical_claims": None,
                "accounted_claims": None,
                "ai_proposed": 0,
                "ai_validator_accepted": 0,
                "ai_validator_rejected": 0,
                "lost_claims": None,
                "note": "skipped — no RUN",
            },
            "lost_claims": None,
            "accounted_claims": None,
            "conservation_ok": False,
            "token_usage": {},
            "api_latency_ms": 0,
            "mode": "offline_stub_missing_run",
            "compiler_advisory_only": True,
            "use_for_build": False,
        }
        (out_dir / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
        return evaluation

    mock_payload = _empty_mock(name, machine)
    if mock_path and mock_path.is_file():
        mock_payload = json.loads(mock_path.read_text(encoding="utf-8"))

    result = analyze(
        run_dir,
        machine,
        project=name,
        mock_response=mock_payload,
        use_for_build=False,
    )
    evaluation = result.get("evaluation") or {}
    evaluation["run_available"] = True
    evaluation["resolve_note"] = how
    evaluation["run_dir"] = str(run_dir)
    evaluation["fixture_role"] = site.get("fixture_role")
    evaluation["mode"] = "offline_mock"
    evaluation["compiler_advisory_only"] = True
    evaluation["use_for_build"] = False
    # Ensure site-level path (analyze may write project_machine subdir)
    site_eval = out_dir / "evaluation.json"
    site_eval.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    # Also copy last summary
    if result.get("summary"):
        (out_dir / "summary.json").write_text(
            json.dumps(result["summary"], indent=2), encoding="utf-8"
        )
    return evaluation


def _parse_fixture_args(values: list[str] | None) -> dict[str, Path]:
    """Parse --fixture SITE=PATH entries."""
    out: dict[str, Path] = {}
    for raw in values or []:
        if "=" not in raw:
            raise SystemExit(f"--fixture requires SITE=PATH, got: {raw}")
        site, path = raw.split("=", 1)
        out[site.strip().upper()] = Path(path.strip().strip('"'))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Four-site AI I/O offline evaluation")
    ap.add_argument("--no-extract", action="store_true", help="Do not extract tar.gz archives")
    ap.add_argument("--mock-dir", type=Path, default=None, help="Dir of <site>_mock.json files")
    ap.add_argument("--site", action="append", default=None, help="Limit to site name(s)")
    ap.add_argument(
        "--fixture",
        action="append",
        default=None,
        help="Explicit fixture SITE=RUN_DIR_OR_TAR (repeatable). Overrides defaults.",
    )
    args = ap.parse_args(argv)

    fixtures = _parse_fixture_args(args.fixture)
    wanted = {s.upper() for s in (args.site or [])} or None
    results = []
    for site in SITES:
        if wanted and site["site"].upper() not in wanted:
            continue
        mock_path = None
        if args.mock_dir:
            mock_path = Path(args.mock_dir) / f"{site['site']}_mock.json"
        print(f"=== {site['site']} ===", flush=True)
        ev = evaluate_site(
            site,
            extract=not args.no_extract,
            mock_path=mock_path,
            explicit_fixture=fixtures.get(site["site"].upper()),
        )
        before = ev.get("BEFORE_AI") or {}
        after = ev.get("AFTER_AI") or {}
        results.append(
            {
                "site": site["site"],
                "run_available": ev.get("run_available"),
                "raw_physical_claims": before.get("raw_physical_claims")
                or after.get("raw_physical_claims"),
                "accounted_claims": after.get("accounted_claims"),
                "lost_claims": after.get("lost_claims")
                if after.get("lost_claims") is not None
                else ev.get("lost_claims"),
                "duplicate_accounting": after.get("duplicate_accounting"),
                "conservation_ok": ev.get("conservation_ok"),
                "BEFORE_AI": before,
                "AFTER_AI": after,
                "resolve_note": ev.get("resolve_note"),
                "fixture_role": site.get("fixture_role"),
            }
        )
        print(json.dumps(results[-1], indent=2), flush=True)

    summary_path = REPO_ROOT / "exports" / "ai-io" / "four_site_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "kind": "ai_io_four_site_summary",
                "generated_at": _ts(),
                "mode": "offline_mock",
                "compiler_advisory_only": True,
                "sites": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
