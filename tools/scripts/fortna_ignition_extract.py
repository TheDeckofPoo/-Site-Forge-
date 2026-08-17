#!/usr/bin/env python3
"""
fortna_ignition_extract.py — Extract Ignition gateway backup (.gwbk) metadata for Prism.

A .gwbk file is a ZIP archive containing gateway config, OPC/PLC device connections,
tag UDT definitions, Perspective/Vision projects, and HMI tag bindings.

Usage:
  py tools/scripts/fortna_ignition_extract.py extract path/to/backup.gwbk
  py tools/scripts/fortna_plc_export.py ignition path/to/backup.gwbk
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

TAG_REF_PATTERNS = [
    re.compile(r'\[default\]([A-Za-z0-9_/]+)'),
    re.compile(r'\[(?P<device>[A-Za-z0-9_]+)\](?P<path>[A-Za-z0-9_/]+)'),
    re.compile(r'"(?:tagPath|opcItemPath)"\s*:\s*"(?P<path>[^"]+)"'),
    re.compile(r'"binding"\s*:\s*"tag:(?P<path>[^"]+)"'),
    re.compile(r'(?<![A-Za-z0-9_])(?P<device>CC\d|MCC\d|CP\d)/[A-Z][A-Za-z0-9_/]+'),
]

HMI_DOMAIN_KEYS = {
    'conveyor': ['conveyors', 'conv'],
    'destination': ['destinations', 'dest'],
    'divert': ['diverts', 'divert', 'lane'],
    'encoder': ['encoders', 'encoder'],
    'photoeye': ['photoeye', 'photoeyes', 'pe_'],
    'estop': ['estops', 'estop'],
    'sorter': ['sorter', 'sort'],
    'induct': ['induct'],
    'control': ['control', 'hmi_start', 'hmi_stop', 'mcr'],
    'fault': ['fault', 'alarm'],
}


def _parse_backupinfo(xml_text: str) -> dict:
    info: dict = {}
    try:
        root = ET.fromstring(xml_text)
        for child in root:
            if child.text:
                info[child.tag.replace('-', '_')] = child.text.strip()
    except ET.ParseError:
        pass
    return info


def _read_json_member(zf: zipfile.ZipFile, name: str) -> dict | list | None:
    try:
        return json.loads(zf.read(name))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _list_projects(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    projects = []
    for name in sorted(n for n in names if n.endswith('project.json') and n.startswith('projects/')):
        data = _read_json_member(zf, name)
        if not isinstance(data, dict):
            continue
        slug = name.split('/')[1]
        projects.append({
            'name': slug,
            'title': data.get('title', slug),
            'description': data.get('description', ''),
            'enabled': data.get('enabled', True),
            'parent': data.get('parent', ''),
            'path': name,
        })
    return projects


def _extract_opc_devices(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    devices = []
    prefix = 'config/resources/core/com.inductiveautomation.opcua/device/'
    for name in sorted(n for n in names if n.startswith(prefix) and n.endswith('/config.json')):
        data = _read_json_member(zf, name)
        if not isinstance(data, dict):
            continue
        device_name = name[len(prefix):].split('/')[0]
        profile = data.get('profile') or {}
        settings = data.get('settings') or {}
        connectivity = settings.get('connectivity') or {}
        advanced = settings.get('advanced') or {}
        devices.append({
            'name': device_name,
            'driver_type': profile.get('type', ''),
            'hostname': connectivity.get('hostname', ''),
            'port': connectivity.get('port', ''),
            'slot': advanced.get('slotNumber', ''),
            'path': name,
        })
    return devices


def _walk_tag_tree(nodes: list | None, prefix: str = '') -> list[dict]:
    tags: list[dict] = []
    for node in nodes or []:
        name = node.get('name', '')
        path = f'{prefix}/{name}' if prefix else name
        entry = {
            'path': path,
            'name': name,
            'tag_type': node.get('tagType', ''),
            'type_id': node.get('typeId', ''),
            'enabled': node.get('enabled'),
            'data_type': node.get('dataType', ''),
        }
        tags.append(entry)
        if node.get('tags'):
            tags.extend(_walk_tag_tree(node['tags'], path))
    return tags


def _extract_tag_udts(zf: zipfile.ZipFile) -> list[dict]:
    udts_path = 'config/resources/core/ignition/tag-definition/default/udts.json'
    data = _read_json_member(zf, udts_path)
    if not isinstance(data, list):
        return []
    roots = []
    for root in data:
        path = root.get('name', '')
        roots.append({
            'name': path,
            'tag_type': root.get('tagType', ''),
            'type_id': root.get('typeId', ''),
            'tags': _walk_tag_tree(root.get('tags'), path),
        })
    return roots


def _extract_tag_groups(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    groups = []
    prefix = 'config/resources/core/ignition/tag-group/default/'
    for name in sorted(n for n in names if n.startswith(prefix) and n.endswith('/config.json')):
        data = _read_json_member(zf, name)
        rel = name[len(prefix):].replace('/config.json', '')
        cfg = (data or {}).get('config', data) if isinstance(data, dict) else {}
        groups.append({
            'name': rel,
            'rate_ms': cfg.get('rate', ''),
            'path': name,
        })
    return groups


def _scan_tag_refs(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    refs: dict[str, dict] = {}
    project_json = [
        n for n in names
        if n.startswith('projects/') and n.endswith('.json')
    ]
    for name in project_json:
        try:
            text = zf.read(name).decode('utf-8', 'replace')
        except Exception:
            continue
        project = name.split('/')[1] if '/' in name else ''
        for pattern in TAG_REF_PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group(0)
                if raw in ('NOT FOUND',) or raw.startswith('({'):
                    continue
                if raw.startswith('[System]'):
                    continue
                provider = 'default'
                device = ''
                tag_path = raw
                if raw.startswith('['):
                    inner = raw[1:]
                    if ']' in inner:
                        provider, rest = inner.split(']', 1)
                        tag_path = rest.strip('/')
                        device = provider if provider not in ('default', 'System') else rest.split('/')[0]
                elif '/' in raw:
                    device = raw.split('/')[0]
                    tag_path = raw
                key = raw.strip()
                if key not in refs:
                    refs[key] = {
                        'raw': raw,
                        'provider': provider,
                        'device': device,
                        'tag_path': tag_path,
                        'projects': set(),
                        'files': set(),
                    }
                refs[key]['projects'].add(project)
                refs[key]['files'].add(name)
    result = []
    for item in refs.values():
        result.append({
            'raw': item['raw'],
            'provider': item['provider'],
            'device': item['device'],
            'tag_path': item['tag_path'],
            'projects': sorted(item['projects']),
            'file_count': len(item['files']),
            'domain': _infer_domain(item['tag_path']),
        })
    result.sort(key=lambda r: (r['domain'], r['tag_path']))
    return result


def _infer_domain(tag_path: str) -> str:
    blob = tag_path.lower().replace('/', ' ')
    for domain, keys in HMI_DOMAIN_KEYS.items():
        if any(k in blob for k in keys):
            return domain
    return 'general'


def _list_views(zf: zipfile.ZipFile, names: list[str]) -> list[dict]:
    views = []
    for name in sorted(n for n in names if '/views/' in n and n.endswith('/view.json')):
        parts = name.split('/')
        try:
            proj_idx = parts.index('projects') + 1
            project = parts[proj_idx]
            views_idx = parts.index('views')
            view_path = '/'.join(parts[views_idx + 1:-1])
        except ValueError:
            project = ''
            view_path = name
        data = _read_json_member(zf, name)
        title = ''
        if isinstance(data, dict):
            for key in ('params', 'meta'):
                block = data.get(key)
                if isinstance(block, dict) and block.get('title'):
                    title = block['title']
                    break
        views.append({
            'project': project,
            'path': view_path,
            'title': title,
            'file': name,
        })
    return views


def _infer_site_name(gwbk_path: Path, projects: list[dict], backupinfo: dict) -> str:
    for proj in projects:
        title = (proj.get('title') or '').strip()
        if title and title not in ('CONVEYOR CONTROL',):
            cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', title).strip('_')
            if cleaned:
                return cleaned[:40]
    stem = gwbk_path.stem
    for token in ('_optiSort_Ignition-backup-', '_Ignition-backup-', 'Ignition-backup-'):
        if token in stem:
            stem = stem.split(token)[0].strip('_- ')
    return re.sub(r'[^A-Za-z0-9_]+', '_', stem).strip('_')[:40] or 'IgnitionSite'


def _infer_primary_behavior(tag_refs: list[dict], projects: list[dict]) -> str:
    domains = Counter(r['domain'] for r in tag_refs)
    titles = ' '.join(p.get('title', '') for p in projects).lower()
    if domains.get('divert', 0) + domains.get('destination', 0) > domains.get('conveyor', 0):
        return 'sorter'
    if 'sorter' in titles or 'sort' in titles:
        return 'sorter'
    if domains.get('conveyor', 0) > 0:
        return 'transport'
    return 'auxiliary'


def _quality_tier(has_devices: bool, tag_ref_count: int, view_count: int) -> str:
    if has_devices and tag_ref_count >= 20 and view_count >= 10:
        return 'gold'
    if tag_ref_count >= 5 or view_count >= 3:
        return 'silver'
    return 'bronze'


def _cross_reference_fortna(ignition_refs: list[dict], fortna_manifest: dict) -> dict:
    fortna_tags = {t.get('name', '').upper() for t in fortna_manifest.get('tags', [])}
    fortna_areas = {p.get('area', '').upper() for p in fortna_manifest.get('stats', {}).get('by_area', {})}
    if not fortna_areas:
        fortna_areas = {
            (t.get('area') or '').upper()
            for t in fortna_manifest.get('tags', [])
            if t.get('area')
        }
    matches = []
    for ref in ignition_refs:
        path_upper = ref['tag_path'].upper()
        hit_tags = [t for t in fortna_tags if t and t in path_upper]
        hit_areas = [a for a in fortna_areas if a and a in path_upper]
        if hit_tags or hit_areas:
            matches.append({
                'ignition_ref': ref['raw'],
                'fortna_tags': hit_tags[:5],
                'fortna_areas': hit_areas[:5],
                'domain': ref['domain'],
            })
    return {
        'fortna_tag_count': len(fortna_tags),
        'matched_ref_count': len(matches),
        'matches': matches[:200],
    }


def extract_gwbk(
    gwbk_path: Path,
    out_dir: Path | None = None,
    fortna_manifest_path: Path | None = None,
) -> dict:
    gwbk_path = Path(gwbk_path)
    if not gwbk_path.is_file():
        raise FileNotFoundError(f'GWBK not found: {gwbk_path}')
    if gwbk_path.suffix.lower() != '.gwbk':
        raise ValueError(f'Expected .gwbk file: {gwbk_path}')

    with zipfile.ZipFile(gwbk_path) as zf:
        names = zf.namelist()
        entry_count = len(names)
        backupinfo = {}
        if 'backupinfo.xml' in names:
            backupinfo = _parse_backupinfo(zf.read('backupinfo.xml').decode('utf-8', 'replace'))
        projects = _list_projects(zf, names)
        devices = _extract_opc_devices(zf, names)
        tag_udts = _extract_tag_udts(zf)
        tag_groups = _extract_tag_groups(zf, names)
        tag_refs = _scan_tag_refs(zf, names)
        views = _list_views(zf, names)

    site = _infer_site_name(gwbk_path, projects, backupinfo)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = out_dir or (REPO_ROOT / 'exports' / 'ignition' / f'{stamp}-{site}')
    out.mkdir(parents=True, exist_ok=True)

    atomic_tags = [
        t for root in tag_udts for t in root.get('tags', [])
        if t.get('tag_type') == 'AtomicTag'
    ]
    domain_counts = Counter(r['domain'] for r in tag_refs)

    manifest = {
        'source': str(gwbk_path),
        'site': site,
        'backup': backupinfo,
        'entry_count': entry_count,
        'projects': projects,
        'opc_devices': devices,
        'tag_udt_roots': [
            {'name': r['name'], 'type_id': r['type_id'], 'tag_count': len(r.get('tags', []))}
            for r in tag_udts
        ],
        'tag_groups': tag_groups,
        'stats': {
            'project_count': len(projects),
            'opc_device_count': len(devices),
            'udt_tag_node_count': sum(len(r.get('tags', [])) for r in tag_udts),
            'atomic_tag_count': len(atomic_tags),
            'hmi_tag_ref_count': len(tag_refs),
            'view_count': len(views),
            'domains': dict(domain_counts),
        },
        'primary_behavior': _infer_primary_behavior(tag_refs, projects),
    }

    prism_manifest = {
        'site': site,
        'primary': manifest['primary_behavior'],
        'mechanism': '',
        'conveyance_tags': sorted(domain_counts.keys()),
        'quality_tier': _quality_tier(bool(devices), len(tag_refs), len(views)),
        'sources': {
            'gwbk': str(gwbk_path),
            'run': '',
            'l5x': '',
        },
        'ignition': {
            'gateway_version': backupinfo.get('version', ''),
            'backup_timestamp': backupinfo.get('timestamp', ''),
            'projects': [p['name'] for p in projects],
            'plc_devices': [
                {'name': d['name'], 'type': d['driver_type'], 'hostname': d['hostname']}
                for d in devices
            ],
        },
        'exported_at': datetime.now(timezone.utc).isoformat(),
    }

    if fortna_manifest_path:
        fortna_manifest_path = Path(fortna_manifest_path)
        if fortna_manifest_path.is_file():
            fortna_data = json.loads(fortna_manifest_path.read_text(encoding='utf-8'))
            manifest['fortna_cross_reference'] = _cross_reference_fortna(tag_refs, fortna_data)
            prism_manifest['sources']['run'] = str(fortna_manifest_path.parent)
            if fortna_data.get('system'):
                prism_manifest['sources']['l5x'] = str(
                    fortna_manifest_path.parent / f"{fortna_data['system']}.L5X"
                )

    manifest_path = out / 'ignition_manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, default=str)

    prism_path = out / 'prism_manifest.json'
    with open(prism_path, 'w', encoding='utf-8') as fh:
        json.dump(prism_manifest, fh, indent=2, default=str)

    refs_csv = out / 'ignition_tag_refs.csv'
    with open(refs_csv, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=['raw', 'provider', 'device', 'tag_path', 'domain', 'projects', 'file_count'],
        )
        writer.writeheader()
        for row in tag_refs:
            writer.writerow({**row, 'projects': '|'.join(row['projects'])})

    devices_csv = out / 'ignition_devices.csv'
    with open(devices_csv, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=['name', 'driver_type', 'hostname', 'port', 'slot', 'path'],
        )
        writer.writeheader()
        writer.writerows(devices)

    views_csv = out / 'ignition_views.csv'
    with open(views_csv, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['project', 'path', 'title', 'file'])
        writer.writeheader()
        writer.writerows(views)

    report_lines = [
        f'Ignition GWBK extract: {gwbk_path.name}',
        f'Site: {site}',
        f'Gateway: {backupinfo.get("version", "unknown")} @ {backupinfo.get("timestamp", "unknown")}',
        f'Projects: {len(projects)}',
    ]
    for p in projects:
        report_lines.append(f'  - {p["name"]}: {p["title"]}')
    report_lines.append(f'OPC/PLC devices: {len(devices)}')
    for d in devices:
        report_lines.append(f'  - {d["name"]} ({d["driver_type"]}) -> {d["hostname"]}:{d["port"]}')
    report_lines.append(f'HMI tag references: {len(tag_refs)}')
    report_lines.append(f'Perspective/Vision views: {len(views)}')
    report_lines.append(f'Prism tier: {prism_manifest["quality_tier"]} ({manifest["primary_behavior"]})')
    if manifest.get('fortna_cross_reference'):
        xref = manifest['fortna_cross_reference']
        report_lines.append(
            f'Fortna cross-ref: {xref["matched_ref_count"]} of {len(tag_refs)} HMI refs matched'
        )
    report_path = out / 'ignition_export_report.txt'
    report_path.write_text('\n'.join(report_lines) + '\n', encoding='utf-8')

    return {
        'ok': True,
        'site': site,
        'out_dir': str(out),
        'prism_tier': prism_manifest['quality_tier'],
        'primary_behavior': manifest['primary_behavior'],
        'stats': manifest['stats'],
        'files': {
            'manifest': str(manifest_path),
            'prism_manifest': str(prism_path),
            'tag_refs_csv': str(refs_csv),
            'devices_csv': str(devices_csv),
            'views_csv': str(views_csv),
            'report': str(report_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Site Forge — Ignition .gwbk extractor for Prism')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_extract = sub.add_parser('extract', help='Extract metadata from a .gwbk gateway backup')
    p_extract.add_argument('gwbk', help='Path to .gwbk file')
    p_extract.add_argument('--out-dir', default='', help='Output directory')
    p_extract.add_argument(
        '--fortna-manifest',
        default='',
        help='Optional fortna_io_manifest.json for cross-reference',
    )

    args = parser.parse_args()
    try:
        result = extract_gwbk(
            Path(args.gwbk),
            out_dir=Path(args.out_dir) if args.out_dir else None,
            fortna_manifest_path=Path(args.fortna_manifest) if args.fortna_manifest else None,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())