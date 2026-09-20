"""Archive discovery and sync planning (works offline / dry-run without PostgreSQL)."""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[2]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from siteforge_learning.corpus_models import (  # noqa: E402
    ARCHIVE_COMM,
    ARCHIVE_RUN,
    ARCHIVE_UNKNOWN,
)

from . import EXTRACTOR_VERSION
from .config import resolve_corpus_roots
from .extract import build_bundle_from_run_dir
from .staging import ArchiveEvidenceBundle, validate_bundle

PLAN_NEW = "NEW"
PLAN_UNCHANGED = "UNCHANGED"
PLAN_FAILED = "FAILED"
PLAN_FORCE = "FORCE_REEXTRACT"


@dataclass
class DiscoveredArchive:
    path: str
    archive_sha256: str
    archive_class: str
    kind: str  # tar.gz | run_dir
    filename: str = ""
    size_bytes: int | None = None
    project: str = ""
    machine: str = ""
    timestamp_token: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncPlanItem:
    archive_sha256: str
    path: str
    status: str
    archive_class: str = ""
    filename: str = ""
    reason: str = ""
    extractor_version: str = EXTRACTOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_run_dir(run_dir: Path) -> str:
    """Content identity for a RUN directory (project.cfg + key tables).

    Not a substitute for archive tar SHA256 when a tar exists; used when only a
    RUN directory is available.
    """
    h = hashlib.sha256()
    paths: list[Path] = []
    cfg = run_dir / "project.cfg"
    if cfg.is_file():
        paths.append(cfg)
    for folder in ("FORTNA", "PROJECT"):
        base = run_dir / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                paths.append(p)
    for p in paths:
        rel = str(p.relative_to(run_dir)).replace("\\", "/").encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        with p.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def classify_archive_filename(filename: str) -> dict[str, str]:
    name = Path(filename).name
    upper = name.upper()
    archive_class = ARCHIVE_UNKNOWN
    if "COMM" in upper:
        archive_class = ARCHIVE_COMM
    elif upper.endswith("-RUN.TAR.GZ") or "-RUN.TAR.GZ" in upper or upper.endswith(
        "RUN.TAR.GZ"
    ):
        archive_class = ARCHIVE_RUN

    ts = project = machine = ""
    stem = name
    if stem.lower().endswith(".tar.gz"):
        stem = stem[:-7]
    m = re.match(r"^(\d{8}-\d{4})-(.+)$", stem)
    if m:
        ts = m.group(1)
        rest = m.group(2)
    else:
        rest = stem
    rest2 = re.sub(r"-(RUN|COMM[A-Za-z0-9_]*)$", "", rest, flags=re.I)
    if "-" in rest2:
        project, machine = rest2.rsplit("-", 1)
    else:
        project = rest2
    return {
        "archive_class": archive_class,
        "timestamp": ts,
        "project": project,
        "machine": machine,
        "filename": name,
    }


def discover_archives(roots: list[Path | str] | None = None) -> list[DiscoveredArchive]:
    """Discover *.tar.gz and RUN dirs (with project.cfg) under corpus roots."""
    resolved = resolve_corpus_roots(list(roots or []))
    found: dict[str, DiscoveredArchive] = {}

    for root in resolved:
        root = Path(root)
        if not root.exists():
            continue

        # tar.gz archives
        tar_candidates: list[Path] = []
        if root.is_file() and root.name.lower().endswith(".tar.gz"):
            tar_candidates.append(root)
        elif root.is_dir():
            for p in sorted(root.rglob("*.tar.gz")):
                parts_l = [x.lower() for x in p.parts]
                if "_extract" in parts_l:
                    continue
                tar_candidates.append(p)

        for tar_path in tar_candidates:
            try:
                digest = sha256_file(tar_path)
            except OSError as exc:
                meta = classify_archive_filename(tar_path.name)
                key = f"fail:{tar_path.resolve()}"
                found[key] = DiscoveredArchive(
                    path=str(tar_path.resolve()),
                    archive_sha256="",
                    archive_class=meta["archive_class"],
                    kind="tar.gz",
                    filename=tar_path.name,
                    notes=[f"hash_error:{exc}"],
                )
                continue
            meta = classify_archive_filename(tar_path.name)
            found[digest] = DiscoveredArchive(
                path=str(tar_path.resolve()),
                archive_sha256=digest,
                archive_class=meta["archive_class"],
                kind="tar.gz",
                filename=tar_path.name,
                size_bytes=tar_path.stat().st_size,
                project=meta["project"],
                machine=meta["machine"],
                timestamp_token=meta["timestamp"],
            )

        # RUN directories with project.cfg
        run_dirs: list[Path] = []
        if root.is_dir():
            if root.name.upper() == "RUN" and (root / "project.cfg").is_file():
                run_dirs.append(root)
            if (root / "RUN" / "project.cfg").is_file():
                run_dirs.append(root / "RUN")
            for cfg in sorted(root.rglob("project.cfg")):
                if cfg.parent.name.upper() != "RUN":
                    continue
                if "_extract" in [x.lower() for x in cfg.parts]:
                    continue
                run_dirs.append(cfg.parent)

        # Also accept exports/learning/_extract and workspace peeks as RUN dirs
        for run_dir in sorted({p.resolve() for p in run_dirs}, key=lambda x: str(x).lower()):
            try:
                digest = sha256_run_dir(run_dir)
            except OSError as exc:
                key = f"fail:{run_dir}"
                found[key] = DiscoveredArchive(
                    path=str(run_dir),
                    archive_sha256="",
                    archive_class=ARCHIVE_RUN,
                    kind="run_dir",
                    filename=run_dir.parent.name if run_dir.name.upper() == "RUN" else run_dir.name,
                    notes=[f"hash_error:{exc}"],
                )
                continue
            if digest in found:
                # Prefer tar.gz identity when already discovered
                existing = found[digest]
                if existing.kind == "tar.gz":
                    existing.notes.append(f"also_run_dir:{run_dir}")
                    continue
            found[digest] = DiscoveredArchive(
                path=str(run_dir),
                archive_sha256=digest,
                archive_class=ARCHIVE_RUN,
                kind="run_dir",
                filename=run_dir.parent.name if run_dir.name.upper() == "RUN" else run_dir.name,
                project="",
                machine="",
                notes=["identity=run_dir_content_hash"],
            )

    return sorted(
        found.values(),
        key=lambda d: (d.archive_sha256 or d.path).lower(),
    )


def plan_sync(
    discovered: Iterable[DiscoveredArchive],
    known_complete_shas: Iterable[str] | None = None,
    extractor_version: str = EXTRACTOR_VERSION,
    *,
    force: bool = False,
) -> list[SyncPlanItem]:
    """Build NEW / UNCHANGED / FAILED plan items."""
    known = {str(s).strip().lower() for s in (known_complete_shas or []) if s}
    plan: list[SyncPlanItem] = []
    for d in discovered:
        if not d.archive_sha256:
            plan.append(
                SyncPlanItem(
                    archive_sha256="",
                    path=d.path,
                    status=PLAN_FAILED,
                    archive_class=d.archive_class,
                    filename=d.filename,
                    reason="; ".join(d.notes) or "missing_sha256",
                    extractor_version=extractor_version,
                )
            )
            continue
        sha = d.archive_sha256.lower()
        if force:
            status = PLAN_FORCE
            reason = "force_reextract"
        elif sha in known:
            status = PLAN_UNCHANGED
            reason = "known_complete"
        else:
            status = PLAN_NEW
            reason = "not_in_warehouse"
        plan.append(
            SyncPlanItem(
                archive_sha256=sha,
                path=d.path,
                status=status,
                archive_class=d.archive_class,
                filename=d.filename,
                reason=reason,
                extractor_version=extractor_version,
            )
        )
    return plan


def _find_run_inside(extract_root: Path) -> Path | None:
    if (extract_root / "project.cfg").is_file():
        return extract_root
    if (extract_root / "RUN" / "project.cfg").is_file():
        return extract_root / "RUN"
    for cfg in extract_root.rglob("project.cfg"):
        if cfg.parent.name.upper() == "RUN":
            return cfg.parent
    return None


def materialize_run_dir(
    discovered: DiscoveredArchive,
    *,
    scratch_parent: Path | None = None,
) -> tuple[Path, Path | None]:
    """Return (run_dir, temp_dir_to_cleanup_or_None)."""
    path = Path(discovered.path)
    if discovered.kind == "run_dir":
        return path, None
    if not path.is_file() or not path.name.lower().endswith(".tar.gz"):
        raise FileNotFoundError(f"not a tar.gz archive: {path}")

    # Prefer existing extract under exports/learning/_extract/<sha or name>
    extract_hint = _REPO / "exports" / "learning" / "_extract"
    if extract_hint.is_dir():
        for cand in (
            extract_hint / discovered.archive_sha256[:16],
            extract_hint / path.stem.replace(".tar", ""),
        ):
            run = _find_run_inside(cand) if cand.is_dir() else None
            if run is not None:
                return run, None

    tmp = Path(tempfile.mkdtemp(prefix="siteforge_wh_", dir=str(scratch_parent) if scratch_parent else None))
    # Selective extract — Stage-1 tables only. Avoids Windows extractall failures on
    # odd members (e.g. ABS_CARD_INFO hardlinks) and keeps temp footprint small.
    _KEEP = re.compile(
        r"(project\.cfg$|Configio\.asc|Conveyor\.asc|EIPModules\.asc|EIPAdapters\.asc|"
        r"EIPModuleType\.asc|eipcfg.*\.xml|IOCard\.asc)",
        re.I,
    )
    try:
        with tarfile.open(path, "r:gz") as tf:
            members = [
                m
                for m in tf.getmembers()
                if m.isfile() and _KEEP.search(m.name.replace("\\", "/"))
            ]
            # Ensure parent dirs exist; extract one-by-one for Windows path safety
            for m in members:
                dest = tmp / m.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    tf.extract(m, tmp)
                except (OSError, tarfile.TarError):
                    # Skip unreadable members — Stage-1 continues with what we got
                    continue
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    run = _find_run_inside(tmp)
    if run is None:
        shutil.rmtree(tmp, ignore_errors=True)
        raise FileNotFoundError(f"no RUN/project.cfg inside {path}")
    return run, tmp


def build_bundle_for_discovered(discovered: DiscoveredArchive) -> ArchiveEvidenceBundle:
    run_dir, tmp = materialize_run_dir(discovered)
    try:
        return build_bundle_from_run_dir(
            run_dir,
            archive_sha256=discovered.archive_sha256,
            filename=discovered.filename or Path(discovered.path).name,
            discovered_path=discovered.path,
        )
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def dry_run_sync(
    roots: list[Path | str] | None = None,
    *,
    known_complete_shas: Iterable[str] | None = None,
    extractor_version: str = EXTRACTOR_VERSION,
    force: bool = False,
    build_bundles: bool = True,
) -> dict[str, Any]:
    """Full sync plan + optional staging counts without writing to PostgreSQL."""
    discovered = discover_archives(roots)
    plan = plan_sync(
        discovered,
        known_complete_shas=known_complete_shas,
        extractor_version=extractor_version,
        force=force,
    )
    bundles: list[ArchiveEvidenceBundle] = []
    staging_errors: list[dict[str, Any]] = []
    counts_total: dict[str, int] = {}

    if build_bundles:
        for item in plan:
            if item.status == PLAN_FAILED:
                continue
            if item.status == PLAN_UNCHANGED and not force:
                continue
            disc = next(
                (d for d in discovered if d.archive_sha256 == item.archive_sha256),
                None,
            )
            if disc is None:
                continue
            try:
                bundle = build_bundle_for_discovered(disc)
                errs = validate_bundle(bundle)
                if errs:
                    staging_errors.append(
                        {
                            "archive_sha256": item.archive_sha256,
                            "errors": errs,
                        }
                    )
                    item.status = PLAN_FAILED
                    item.reason = "validate_bundle_failed"
                    continue
                bundles.append(bundle)
                for k, v in bundle.staging_counts().items():
                    counts_total[k] = counts_total.get(k, 0) + v
            except Exception as exc:
                staging_errors.append(
                    {
                        "archive_sha256": item.archive_sha256,
                        "errors": [str(exc)],
                    }
                )
                item.status = PLAN_FAILED
                item.reason = f"extract_error:{exc}"

    status_counts: dict[str, int] = {}
    for item in plan:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1

    return {
        "extractor_version": extractor_version,
        "dry_run": True,
        "roots": [str(p) for p in resolve_corpus_roots(list(roots or []))],
        "discovered": [d.to_dict() for d in discovered],
        "plan": [p.to_dict() for p in plan],
        "status_counts": status_counts,
        "staging_counts": counts_total,
        "staging_errors": staging_errors,
        "bundle_count": len(bundles),
        "bundles": bundles,
    }
