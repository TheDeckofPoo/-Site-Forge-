#!/usr/bin/env python3
"""
fortna_prism_seed.py — PoC: FortnaPlus I/O export + PRISM L5X reference seeding.

After FortnaPlus PLC export, this script:
  1. Reads fortna_io_manifest.json (I/O, areas, device classes)
  2. Searches PRISM vector DB for matching ladder/AOI patterns
  3. Scans knowledge-corpus L5X files for reference routines/AOIs
  4. Writes prism_seeded/ importable routine L5X + AI prompt bundle

Usage:
  py tools/scripts/fortna_prism_seed.py --export-dir exports/plc/20260629-164958-OReillyDC27_ORDENCOMM
  py tools/scripts/fortna_prism_seed.py --manifest path/to/fortna_io_manifest.json

Optional env:
  PRISM_ROOT=C:\\Users\\curtiskricke\\worktrees\\Rockwell_GitHub
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FORTNA_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_PRISM_ROOT = Path(r'C:\Users\curtiskricke\worktrees\Rockwell_GitHub')

sys.path.insert(0, str(SCRIPT_DIR))
from fortna_device_logic import build_routine_rungs  # noqa: E402
from fortna_motor_logic import build_mcr_rungs, build_motor_chain_rungs  # noqa: E402

DEVICE_QUERIES = {
    'Photoeye': 'photoeye present jam clear Fortna FMS ladder logic',
    'Motor': 'motor conveyor run interlock MCR chain startup',
    'Beacon': 'beacon warning light stack light output pattern',
    'Conveyor': 'conveyor zone VFD run enable',
    'Splitter': 'splitter divert paddle chute FMS AOI',
    'Zone': 'FMS zone sequence coverage inhibit',
}

CORPUS_FILE_HINTS = {
    'Photoeye': ['photoeye', 'pe_', 'rt_inhibit', 'ezpe', 'ssv'],
    'Motor': ['motor', 'mcr', 'vfd', 'conv'],
    'Beacon': ['beacon', 'warning', 'stack'],
    'Splitter': ['splitter', 'divert', 'paddle', 'chute', 'artemis'],
    'Zone': ['zone', 'seq_zone', 'coverage', 'inhibit'],
    'AOI': ['aofms_', 'aoi', 'addon'],
}

L5X_EXPORT_OPTIONS = (
    'References NoRawData L5KData DecoratedData Context Dependencies '
    'ForceProtectedEncoding AllProjDocTrans'
)


def local_tag(elem: ET.Element) -> str:
    tag = elem.tag
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def prism_root() -> Path:
    return Path(os.environ.get('PRISM_ROOT', str(DEFAULT_PRISM_ROOT)))


def load_vector_db():
    root = prism_root()
    sys.path.insert(0, str(root / 'rockwell-vector-db'))
    from rockwell_vectordb import RockwellVectorDB  # noqa: E402
    return RockwellVectorDB(root)


def load_manifest(export_dir: Path | None, manifest_path: Path | None) -> tuple[dict, Path]:
    if manifest_path:
        path = Path(manifest_path)
        base = path.parent
    elif export_dir:
        base = Path(export_dir)
        path = base / 'fortna_io_manifest.json'
    else:
        raise ValueError('Provide --export-dir or --manifest')
    if not path.is_file():
        raise FileNotFoundError(f'Manifest not found: {path}')
    return json.loads(path.read_text(encoding='utf-8')), base


def scan_corpus_l5x(hints: list[str], limit: int = 12) -> list[dict]:
    corpus = prism_root() / 'knowledge-corpus'
    if not corpus.is_dir():
        return []
    hits: list[dict] = []
    for l5x in sorted(corpus.rglob('*.L5X'), key=lambda p: p.stat().st_mtime, reverse=True):
        blob = str(l5x).lower()
        if not any(h in blob for h in hints):
            continue
        site = l5x.parent.parent.name if l5x.parent.name == 'programs' else 'unknown'
        hits.append({'site': site, 'path': str(l5x), 'name': l5x.name})
        if len(hits) >= limit:
            break
    for l5x in sorted(corpus.rglob('*.l5x'), key=lambda p: p.stat().st_mtime, reverse=True):
        blob = str(l5x).lower()
        if not any(h in blob for h in hints):
            continue
        site = l5x.parent.parent.name if l5x.parent.name == 'programs' else 'unknown'
        entry = {'site': site, 'path': str(l5x), 'name': l5x.name}
        if entry not in hits:
            hits.append(entry)
        if len(hits) >= limit:
            break
    return hits


def extract_rungs_from_l5x(path: Path, max_rungs: int = 8) -> list[dict]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    rungs = []
    for elem in root.iter():
        if local_tag(elem) != 'Rung':
            continue
        num = elem.get('Number', '?')
        text_el = None
        for child in elem:
            if local_tag(child) == 'Text':
                text_el = child
                break
        text = (text_el.text or '').strip() if text_el is not None else ''
        if text:
            rungs.append({'number': num, 'text': text[:500]})
        if len(rungs) >= max_rungs:
            break
    return rungs


def search_prism(db, query: str, n: int = 5) -> list[dict]:
    try:
        return db.search(query, n_results=n, system=None)
    except Exception:
        return []


def _l5x_routine_export(
    *,
    controller: str,
    program: str,
    routine_name: str,
    rungs: list[tuple[str, str]],
    reference_note: str,
) -> str:
    export_date = datetime.now().strftime('%a %b %d %H:%M:%S %Y')
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="32.00" '
        f'TargetName="{routine_name}" TargetType="Routine" TargetSubType="RLL" '
        f'TargetClass="Standard" ContainsContext="true" ExportDate="{export_date}" '
        f'ExportOptions="{L5X_EXPORT_OPTIONS}">',
        f'<Controller Use="Context" Name="{controller}">',
        f'<Programs Use="Context"><Program Use="Context" Name="{program}">',
        f'<Routines Use="Context"><Routine Use="Target" Name="{routine_name}" Type="RLL">',
        '<RLLContent>',
    ]
    for i, (comment, text) in enumerate(rungs):
        cdata = comment.replace(']]>', ']] >')
        tdata = text.replace(']]>', ']] >')
        lines.extend([
            f'<Rung Number="{i}" Type="N">',
            f'<Comment><![CDATA[{cdata}]]></Comment>',
            f'<Text><![CDATA[{tdata}]]></Text>',
            '</Rung>',
        ])
    if reference_note:
        lines.extend([
            f'<Rung Number="{len(rungs)}" Type="N">',
            f'<Comment><![CDATA[PRISM PoC — reference sources]]></Comment>',
            f'<Text><![CDATA[NOP();]]></Text>',
            '</Rung>',
        ])
    lines.extend([
        '</RLLContent>',
        '</Routine></Routines>',
        '</Program></Programs>',
        '</Controller>',
        '</RSLogix5000Content>',
        '',
    ])
    return '\n'.join(lines)


def build_seeded_routines(scaffold: dict, references: dict) -> list[dict]:
    tags = scaffold.get('tags') or []
    motor_chains = scaffold.get('motor_chains') or []
    controller = scaffold.get('system') or 'FortnaSite'
    programs = scaffold.get('programs') or []
    written = []

    area_tags: dict[str, list] = defaultdict(list)
    for tag in tags:
        area_tags[tag.get('area') or 'MAIN'].append(tag)

    ref_note = '; '.join(
        f"{r['name']}@{r['site']}" for r in references.get('corpus_files', [])[:5]
    )

    for prog in programs:
        area = prog.get('area') or 'MAIN'
        prog_name = prog.get('name') or f'PG_{area}'
        area_tag_list = area_tags.get(area, tags)

        pe_tags = [t for t in area_tag_list if t.get('device_class') == 'Photoeye']
        pe_rungs = build_routine_rungs(
            pe_tags, all_tags=tags, motor_chains=motor_chains,
        ) if pe_tags else []
        if pe_rungs:
            rout = f'RT_PE_{area[:8]}'
            body = [(c, t) for c, t in pe_rungs[:40]]
            out_name = f'{rout}_PrismSeed.L5X'
            written.append({
                'routine': rout,
                'program': prog_name,
                'device_class': 'Photoeye',
                'rung_count': len(body),
                'filename': out_name,
                'content': _l5x_routine_export(
                    controller=controller,
                    program=prog_name,
                    routine_name=rout,
                    rungs=body,
                    reference_note=ref_note,
                ),
            })

        for dc in ('Beacon', 'Motor'):
            dc_tags = [t for t in area_tag_list if t.get('device_class') == dc]
            drungs = build_routine_rungs(
                dc_tags, all_tags=tags, motor_chains=motor_chains,
            ) if dc_tags else []
            if not drungs:
                continue
            rout = f'RT_{dc[:6]}_{area[:8]}'
            body = [(c, t) for c, t in drungs[:30]]
            out_name = f'{rout}_PrismSeed.L5X'
            written.append({
                'routine': rout,
                'program': prog_name,
                'device_class': dc,
                'rung_count': len(body),
                'filename': out_name,
                'content': _l5x_routine_export(
                    controller=controller,
                    program=prog_name,
                    routine_name=rout,
                    rungs=body,
                    reference_note=ref_note,
                ),
            })

    mcr = build_mcr_rungs(tags)
    mc = build_motor_chain_rungs(motor_chains, tags)
    if mcr or mc:
        body = [(c, t) for c, t in (mcr + mc)[:50]]
        rout = 'RT_Motor_Chains_PrismSeed'
        written.append({
            'routine': 'RT_Motor_Chains',
            'program': programs[0]['name'] if programs else 'PG_MAIN',
            'device_class': 'MotorChain',
            'rung_count': len(body),
            'filename': f'{rout}.L5X',
            'content': _l5x_routine_export(
                controller=controller,
                program=programs[0]['name'] if programs else 'PG_MAIN',
                routine_name='RT_Motor_Chains',
                rungs=body,
                reference_note=ref_note,
            ),
        })

    return written


def build_ai_prompt(scaffold: dict, prism_hits: dict, corpus_detail: list[dict]) -> str:
    stats = scaffold.get('stats') or {}
    meta = scaffold.get('fortna_meta') or {}
    lines = [
        'PRISM + FortnaPlus PoC — Program generation request',
        '=' * 60,
        '',
        'NEW SITE (from FortnaPlus .tar export):',
        f"  Controller: {scaffold.get('system')}",
        f"  Project:    {meta.get('project_name')}",
        f"  Machine:    {meta.get('machine_name')}",
        f"  I/O points: {stats.get('total')}",
        f"  Device classes: {json.dumps(stats.get('device_classes') or {})}",
        f"  Areas: {json.dumps(stats.get('areas') or {})}",
        '',
        'TASK:',
        '  Build ladder logic (RLL) for this site using the I/O list below.',
        '  Adapt tag names from REFERENCE PATTERNS — do not copy addresses blindly.',
        '  Prefer AOI calls (aoFMS_Splitter, aoFMS_Seq_Zones, etc.) when device class matches.',
        '',
        'SAMPLE TAGS (first 30):',
    ]
    for tag in (scaffold.get('tags') or [])[:30]:
        lines.append(
            f"  {tag.get('tag')}  [{tag.get('device_class')}]  {tag.get('fortna_name')}  {tag.get('fortna_address')}"
        )

    lines.extend(['', 'PRISM VECTOR SEARCH HITS:'])
    for dc, hits in prism_hits.items():
        lines.append(f'\n  --- {dc} ---')
        for h in hits[:3]:
            m = h.get('metadata') or {}
            lines.append(f"  score={h.get('score')} site={m.get('system')} path={m.get('path')}")
            lines.append(f"  {h.get('text', '')[:600]}")

    lines.extend(['', 'CORPUS L5X REFERENCE FILES (with sample rungs):'])
    for ref in corpus_detail[:10]:
        lines.append(f"\n  [{ref['site']}] {ref['path']}")
        for rung in ref.get('rungs', [])[:3]:
            lines.append(f"    Rung {rung['number']}: {rung['text'][:200]}")

    lines.extend([
        '',
        'OUTPUT REQUEST:',
        '  1. R_Photoeye / R_Motor / R_Beacon routines per zone',
        '  2. Motor chain interlocks per Mtrchain.asc',
        '  3. Note which reference L5X each rung was adapted from',
        '',
    ])
    return '\n'.join(lines)


def run_seed(export_dir: Path | None, manifest_path: Path | None) -> dict:
    scaffold, base = load_manifest(export_dir, manifest_path)
    out_dir = base / 'prism_seeded'
    out_dir.mkdir(parents=True, exist_ok=True)

    db = None
    try:
        db = load_vector_db()
    except Exception as exc:
        prism_db_error = str(exc)
    else:
        prism_db_error = None

    prism_hits: dict[str, list] = {}
    if db:
        for dc, query in DEVICE_QUERIES.items():
            prism_hits[dc] = search_prism(db, query, n=4)

    corpus_files: list[dict] = []
    seen_paths: set[str] = set()
    for hints in CORPUS_FILE_HINTS.values():
        for hit in scan_corpus_l5x(hints, limit=6):
            if hit['path'] in seen_paths:
                continue
            seen_paths.add(hit['path'])
            corpus_files.append(hit)

    corpus_detail = []
    for ref in corpus_files[:15]:
        rungs = extract_rungs_from_l5x(Path(ref['path']))
        corpus_detail.append({**ref, 'rungs': rungs})

    references = {
        'prism_hits': {k: len(v) for k, v in prism_hits.items()},
        'corpus_files': corpus_files,
    }

    routines = build_seeded_routines(scaffold, references)
    routine_files = []
    for rout in routines:
        dest = out_dir / rout['filename']
        dest.write_text(rout['content'], encoding='utf-8')
        routine_files.append({
            'routine': rout['routine'],
            'program': rout['program'],
            'device_class': rout['device_class'],
            'rung_count': rout['rung_count'],
            'path': str(dest),
        })

    prompt = build_ai_prompt(scaffold, prism_hits, corpus_detail)
    prompt_path = out_dir / 'prism_ai_prompt.txt'
    prompt_path.write_text(prompt, encoding='utf-8')

    manifest_out = {
        'ok': True,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'export_dir': str(base),
        'prism_root': str(prism_root()),
        'prism_db_error': prism_db_error,
        'io_stats': scaffold.get('stats'),
        'prism_search_counts': references['prism_hits'],
        'corpus_reference_count': len(corpus_files),
        'seeded_routines': routine_files,
        'files': {
            'prompt': str(prompt_path),
            'seeded_dir': str(out_dir),
        },
        'next_steps': [
            'Open prism_ai_prompt.txt — paste into PRISM Generate or your AI session',
            'Import prism_seeded/*_PrismSeed.L5X into MainProgram in Studio 5000',
            'Compare against studio_import/03_import_routines — seeded version uses same I/O tags',
            'Map Bank*.bit tags to real PointIO aliases before commissioning',
        ],
    }
    manifest_json = out_dir / 'prism_seed_manifest.json'
    manifest_json.write_text(json.dumps(manifest_out, indent=2), encoding='utf-8')
    manifest_out['files']['manifest'] = str(manifest_json)
    return manifest_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Site Forge + PRISM PoC program seeding')
    parser.add_argument('--export-dir', help='FortnaPlus PLC export folder')
    parser.add_argument('--manifest', help='Path to fortna_io_manifest.json')
    args = parser.parse_args()
    try:
        result = run_seed(
            Path(args.export_dir) if args.export_dir else None,
            Path(args.manifest) if args.manifest else None,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())