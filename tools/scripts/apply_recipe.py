#!/usr/bin/env python3
"""Site Forge workspace automation — extract RUN packages and apply recipes."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

from fortna_asc import (
    categorize_device,
    clone_photoeye_row,
    clone_row,
    detect_name_columns,
    find_conveyor,
    find_photoeyes_on_conveyor,
    find_related_rows,
    find_row_by_name,
    next_spare_io,
    read_asc,
    scan_devices,
    summarize_device_categories,
    write_asc,
)

ROOT = Path(__file__).resolve().parents[2]


def load_recipes() -> dict:
    path = ROOT / 'tools' / 'recipes' / 'recipes.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _ensure_dir(path: Path) -> None:
    """Create directory, renaming a same-path-different-case file if needed (QNX fortna vs FORTNA)."""
    if path.is_dir():
        return
    if path.exists() and path.is_file():
        backup = path.parent / f'_{path.name}_qnx_case'
        if backup.exists():
            backup.unlink()
        path.rename(backup)
    if path.parent and not path.parent.exists():
        _ensure_dir(path.parent)
    path.mkdir(parents=True, exist_ok=True)


def _clear_readonly(path: Path) -> None:
    """Strip read-only bit so OneDrive / Windows locks don't block overwrite."""
    try:
        import stat

        if path.exists():
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except OSError:
        pass


def _rmtree_force(path: Path) -> None:
    """Best-effort delete; ignores missing paths."""
    if not path.exists() and not path.is_symlink():
        return

    def _onerror(func, p, _exc_info):
        try:
            import stat

            Path(p).chmod(stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    try:
        _clear_readonly(path)
        shutil.rmtree(path, onerror=_onerror)
    except OSError:
        # Last resort: clear children only (keep directory node — OneDrive reparse points)
        if path.is_dir():
            for child in list(path.iterdir()):
                try:
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child, onerror=_onerror)
                    else:
                        _clear_readonly(child)
                        child.unlink(missing_ok=True)
                except OSError:
                    pass


def clear_workspace_dir(workspace: Path) -> Path:
    """
    Prepare an empty workspace directory for a new RUN extract.

    OneDrive-backed folders are often reparse points with Deny-delete ACLs.
    Deleting the folder itself fails with WinError 5; clearing *contents* works.
    If the folder is unusable, fall back to workspace/active_work.
    """
    workspace = Path(workspace)
    parent = workspace.parent
    parent.mkdir(parents=True, exist_ok=True)

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    # Prefer emptying in place (keep OneDrive reparse point / ACL container)
    try:
        for child in list(workspace.iterdir()):
            _rmtree_force(child) if child.is_dir() and not child.is_symlink() else None
            if child.exists():
                try:
                    if child.is_dir():
                        _rmtree_force(child)
                    else:
                        _clear_readonly(child)
                        child.unlink(missing_ok=True)
                except OSError:
                    pass
        # Verify we can write
        probe = workspace / '.__write_probe__'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return workspace
    except OSError:
        pass

    # Fallback: alternate folder next to active (avoids locked OneDrive node)
    alt = parent / f'{workspace.name}_work'
    try:
        if alt.exists():
            _rmtree_force(alt)
        alt.mkdir(parents=True, exist_ok=True)
        probe = alt / '.__write_probe__'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return alt
    except OSError as exc:
        raise PermissionError(
            f'Access denied clearing workspace {workspace}. '
            f'Close Explorer windows on that folder, pause OneDrive sync for worktree, '
            f'or run Site Forge from a non-OneDrive path. ({exc})'
        ) from exc


def _safe_extract_tar(tf: tarfile.TarFile, workspace: Path) -> None:
    extract_kw = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
    for member in tf.getmembers():
        target = workspace.joinpath(*Path(member.name).parts)
        if member.isdir():
            _ensure_dir(target)
            continue
        _ensure_dir(target.parent)
        tf.extract(member, workspace, **extract_kw)


def extract_run(archive: Path, workspace: Path) -> Path:
    """Extract a Fortna RUN archive into workspace (emptied first, OneDrive-safe)."""
    archive = Path(archive)
    workspace = clear_workspace_dir(Path(workspace))

    if archive.suffix.lower() == '.gz' or archive.name.endswith('.tar.gz') or archive.suffix.lower() == '.tgz':
        with tarfile.open(archive, 'r:gz') as tf:
            _safe_extract_tar(tf, workspace)
    elif archive.suffix.lower() == '.zip':
        shutil.unpack_archive(str(archive), str(workspace))
    else:
        raise ValueError(f'Unsupported archive: {archive}')

    run_dir = workspace / 'RUN'
    if not run_dir.is_dir():
        candidates = list(workspace.rglob('project.cfg'))
        if candidates:
            run_dir = candidates[0].parent
        else:
            raise FileNotFoundError(f'No RUN folder found in archive {archive.name}')
    return run_dir


def resolve_conveyor_asc(run_dir: Path, machine: str) -> Path:
    fortna = run_dir / 'FORTNA'
    for name in (f'Conveyor.asc.{machine}', 'Conveyor.asc'):
        p = fortna / name
        if p.is_file():
            return p
    raise FileNotFoundError(f'Conveyor.asc not found for machine {machine}')


def list_devices(run_dir: Path, machine: str = '', category: str = '') -> list[dict]:
    devices = scan_devices(run_dir, machine=machine)
    if category:
        cat = category.strip().lower()
        devices = [d for d in devices if d['category'] == cat or d['type'].lower() == cat]
    return devices


def list_conveyors(run_dir: Path, machine: str) -> list[str]:
    path = resolve_conveyor_asc(run_dir, machine)
    _, rows = read_asc(path)
    names = []
    for row in rows:
        t = (row.get('Type') or '').upper()
        if t in ('STRAIGHT', 'BELT', 'CURVE', 'MERGE', 'SKEW', 'ACCUM'):
            names.append(row.get('IO_Name', ''))
    return sorted(n for n in names if n)


def add_photoeye(
    run_dir: Path,
    machine: str,
    conveyor: str,
    pe_name: str = '',
    io_word: str = '',
    io_bit: str = '',
    offset_x: float = 500.0,
    offset_y: float = 0.0,
) -> dict:
    conv_path = resolve_conveyor_asc(run_dir, machine)
    headers, rows = read_asc(conv_path)
    conv = find_conveyor(rows, conveyor)
    if not conv:
        raise ValueError(f'Conveyor not found: {conveyor}')

    templates = find_photoeyes_on_conveyor(rows, conveyor)
    if not templates:
        templates = [r for r in rows if (r.get('Type') or '').upper() == 'PHOTOCELL']
    if not templates:
        raise ValueError('No photoeye template row found in Conveyor.asc')
    template = templates[0]

    pe_name = (pe_name or f'PE_{conveyor}_NEW').strip().upper()
    if any((r.get('IO_Name') or '').upper() == pe_name for r in rows):
        raise ValueError(f'Photoeye already exists: {pe_name}')

    if not io_word or not io_bit:
        io_word, io_bit = next_spare_io(rows)

    try:
        cx = float(conv.get('X_cord') or 0)
        cy = float(conv.get('Y_cord') or 0)
        angle = float(conv.get('Angle') or 0)
    except ValueError:
        cx, cy, angle = 0.0, 0.0, 0.0

    new_row = clone_photoeye_row(
        template,
        headers,
        IO_Name=pe_name,
        General_Description=f'PRODUCT PRESENT AT {pe_name} ON {conveyor}',
        IO_Address_Word=io_word,
        IO_Address_Bit=io_bit,
        X_cord=f'{cx + offset_x:.3f}',
        Y_cord=f'{cy + offset_y:.3f}',
        Angle=str(angle),
        Type='PHOTOCELL',
        Machine_Name=machine,
    )
    rows.append(new_row)
    write_asc(conv_path, headers, rows)

    return {
        'conveyor': conveyor,
        'photoeye': pe_name,
        'io_word': io_word,
        'io_bit': io_bit,
        'file': str(conv_path.relative_to(run_dir)),
        'machine': machine,
    }


def clone_device(
    run_dir: Path,
    table: str,
    template_name: str,
    new_name: str,
    machine: str = '',
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    clone_related: bool = True,
) -> dict:
    table = table.replace('\\', '/').strip()
    template_name = (template_name or '').strip()
    new_name = (new_name or '').strip()
    if not table or not template_name or not new_name:
        raise ValueError('table, template_name, and new_name are required')
    if template_name.upper() == new_name.upper():
        raise ValueError('new_name must differ from template_name')

    asc_path = run_dir / table.replace('/', '\\')
    if not asc_path.is_file():
        raise FileNotFoundError(f'Table not found: {table}')

    headers, rows = read_asc(asc_path)
    name_cols = detect_name_columns(headers)
    hit = find_row_by_name(rows, template_name, name_cols)
    if not hit:
        raise ValueError(f'Device not found in {table}: {template_name}')
    _, template_row = hit

    if any((row.get(c) or '').strip().upper() == new_name.upper() for row in rows for c in name_cols):
        raise ValueError(f'Device already exists: {new_name}')

    category = categorize_device(table, template_row, template_name) or 'device'
    io_word, io_bit = '', ''
    if category == 'photoeye':
        io_word, io_bit = next_spare_io(rows)

    new_row = clone_row(
        template_row,
        headers,
        template_name,
        new_name,
        name_cols,
        offset_x=offset_x,
        offset_y=offset_y,
        machine=machine,
        io_word=io_word,
        io_bit=io_bit,
    )
    rows.append(new_row)
    write_asc(asc_path, headers, rows)

    cloned = [{
        'table': table,
        'name': new_name,
        'from': template_name,
        'category': category,
    }]

    if clone_related:
        for path, rel, rel_row, rel_name_cols, old_ref, ref_new_name in find_related_rows(
            run_dir, template_name, table, template_row=template_row, new_name=new_name,
        ):
            if old_ref.upper() == template_name.upper():
                continue
            rel_headers, rel_rows = read_asc(path)
            if any((r.get(c) or '').strip().upper() == ref_new_name.upper() for r in rel_rows for c in rel_name_cols):
                continue
            rel_new = clone_row(
                rel_row,
                rel_headers,
                old_ref,
                ref_new_name,
                rel_name_cols,
                offset_x=offset_x,
                offset_y=offset_y,
                machine=machine,
            )
            rel_rows.append(rel_new)
            write_asc(path, rel_headers, rel_rows)
            cloned.append({
                'table': rel,
                'name': ref_new_name,
                'from': old_ref,
                'category': categorize_device(rel, rel_row, old_ref),
            })

    return {
        'template': template_name,
        'new_name': new_name,
        'category': category,
        'machine': machine,
        'primary_table': table,
        'cloned': cloned,
        'offset_x': offset_x,
        'offset_y': offset_y,
    }


def repack_run(run_dir: Path, out_path: Path) -> Path:
    """Build a QNX-compatible tar.gz without requiring fortna + FORTNA on Windows disk."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    root = run_dir if run_dir.name == 'RUN' else run_dir.parent
    arc_root = run_dir.name if run_dir.name == 'RUN' else run_dir.parent.name

    fortna_blob = None
    for candidate in root.glob('_fortna*_qnx_case'):
        fortna_blob = candidate
        break

    with tarfile.open(out_path, 'w:gz') as tf:
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            if fortna_blob and path.resolve() == fortna_blob.resolve():
                arcname = f'{arc_root}/fortna'
            else:
                rel = path.relative_to(root).as_posix()
                arcname = f'{arc_root}/{rel}'
            tf.add(path, arcname=arcname)
    return out_path


def import_package(archive: Path) -> dict:
    inbox = ROOT / 'workspace' / 'inbox'
    active = ROOT / 'workspace' / 'active'
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / archive.name
    if archive.resolve() != dest.resolve():
        shutil.copy2(archive, dest)
    run_dir = extract_run(dest, active)
    machine = 'ORDENCOMM'
    cfg = run_dir / 'project.cfg'
    if cfg.is_file():
        m = re.search(r'MACHINENAME\s*=\s*(\S+)', cfg.read_text(encoding='utf-8', errors='replace'))
        if m:
            machine = m.group(1).strip()
    devices = list_devices(run_dir, machine=machine)

    # Export names follow the .tar.gz basename (raw-test / first-site rule)
    try:
        from fortna_source_id import archive_export_name, run_content_fingerprint
        export_name = archive_export_name(dest)
        fingerprint = run_content_fingerprint(run_dir)
    except Exception:
        export_name = Path(dest.name).stem.replace('.tar', '')
        fingerprint = ''

    meta = {
        'archive': str(dest),
        'archive_name': dest.name,
        'archive_stem': export_name,
        'export_name': export_name,
        'source_label': export_name,
        'run_fingerprint': fingerprint,
        'run_dir': str(run_dir),
        'machine': machine,
        'conveyors': list_conveyors(run_dir, machine)[:200],
        'devices': devices[:500],
        'device_count': len(devices),
        'device_categories': summarize_device_categories(devices),
        'imported': datetime.now().isoformat(timespec='seconds'),
    }
    (ROOT / 'workspace' / 'active-meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

    # Auto-stage into PRISM vector DB (dedupe by fingerprint — same site skipped)
    try:
        from fortna_prism_ingest import after_import
        prism = after_import(archive=dest, run_dir=run_dir, force=False)
        meta['prism'] = {
            'ok': prism.get('ok'),
            'skipped': prism.get('skipped'),
            'site': prism.get('site'),
            'message': prism.get('message'),
            'fingerprint': prism.get('fingerprint'),
        }
        (ROOT / 'workspace' / 'active-meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    except Exception as exc:
        meta['prism'] = {'ok': False, 'error': str(exc)}
        try:
            (ROOT / 'workspace' / 'active-meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        except OSError:
            pass

    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Site Forge recipe runner")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_import = sub.add_parser('import')
    p_import.add_argument('archive')

    p_list = sub.add_parser('list-conveyors')
    p_list.add_argument('--machine', default='')

    p_dev = sub.add_parser('list-devices')
    p_dev.add_argument('--machine', default='')
    p_dev.add_argument('--category', default='')

    p_clone = sub.add_parser('clone-device')
    p_clone.add_argument('--table', required=True)
    p_clone.add_argument('--template', required=True)
    p_clone.add_argument('--new-name', required=True)
    p_clone.add_argument('--machine', default='')
    p_clone.add_argument('--offset-x', type=float, default=0.0)
    p_clone.add_argument('--offset-y', type=float, default=0.0)
    p_clone.add_argument('--no-related', action='store_true')
    p_clone.add_argument('--repack', action='store_true')

    p_add = sub.add_parser('add-photoeye')
    p_add.add_argument('--conveyor', required=True)
    p_add.add_argument('--pe-name', default='')
    p_add.add_argument('--io-word', default='')
    p_add.add_argument('--io-bit', default='')
    p_add.add_argument('--machine', default='')
    p_add.add_argument('--offset-x', type=float, default=500.0)
    p_add.add_argument('--offset-y', type=float, default=0.0)
    p_add.add_argument('--repack', action='store_true')

    p_idx = sub.add_parser('index-docs')

    args = parser.parse_args()

    if args.cmd == 'index-docs':
        subprocess.run(['py', str(ROOT / 'tools' / 'scripts' / 'index_docs.py')], check=True)
        return 0

    if args.cmd == 'import':
        meta = import_package(Path(args.archive))
        print(json.dumps(meta, indent=2))
        return 0

    meta_path = ROOT / 'workspace' / 'active-meta.json'
    if not meta_path.is_file():
        print('ERROR: No active workspace. Import a RUN package first.', file=__import__('sys').stderr)
        return 1
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    run_dir = Path(meta['run_dir'])
    machine = args.machine or meta.get('machine', 'ORDENCOMM')

    if args.cmd == 'list-conveyors':
        print(json.dumps(list_conveyors(run_dir, machine), indent=2))
        return 0

    if args.cmd == 'list-devices':
        payload = {
            'devices': list_devices(run_dir, machine=machine, category=args.category),
            'categories': summarize_device_categories(list_devices(run_dir, machine=machine)),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == 'clone-device':
        result = clone_device(
            run_dir,
            table=args.table,
            template_name=args.template,
            new_name=args.new_name,
            machine=machine,
            offset_x=args.offset_x,
            offset_y=args.offset_y,
            clone_related=not args.no_related,
        )
        if args.repack:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            out = ROOT / 'exports' / f'{stamp}-modified-RUN.tar.gz'
            result['export'] = str(repack_run(run_dir, out))
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == 'add-photoeye':
        result = add_photoeye(
            run_dir,
            machine=machine,
            conveyor=args.conveyor,
            pe_name=args.pe_name,
            io_word=args.io_word,
            io_bit=args.io_bit,
            offset_x=args.offset_x,
            offset_y=args.offset_y,
        )
        if args.repack:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            out = ROOT / 'exports' / f'{stamp}-modified-RUN.tar.gz'
            result['export'] = str(repack_run(run_dir, out))
        print(json.dumps(result, indent=2))
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(main())