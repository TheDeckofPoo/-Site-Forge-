#!/usr/bin/env python3
"""
fortna_prism_build.py — Build best-effort ladder program from Fortna export + PRISM refs.

Usage:
  py tools/scripts/fortna_prism_build.py --export-dir exports/plc/20260630-132318-OReillyDC27_ORDENCOMM
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_device_logic import build_routine_rungs  # noqa: E402
from fortna_mhs_sorter import build_mhs_program_specs  # noqa: E402
from fortna_motor_logic import build_mcr_rungs, build_motor_chain_rungs  # noqa: E402
from fortna_prism_seed import (  # noqa: E402
    CORPUS_FILE_HINTS,
    _l5x_routine_export,
    load_manifest,
    prism_root,
    scan_corpus_l5x,
)

# O'Reilly FMS shoe sorter — only AOIs referenced in generated ladder logic.
REQUIRED_AOIS: list[tuple[str, str]] = [
    (
        'MGE9_MCP05/programs/MCP05_aoFMS_Splitter.L5X',
        'aoFMS_Splitter.L5X',
    ),
]


def write_routine(out_dir: Path, filename: str, **kwargs) -> dict:
    path = out_dir / filename
    path.write_text(_l5x_routine_export(**kwargs), encoding='utf-8')
    return {'filename': filename, 'path': str(path), 'rungs': len(kwargs.get('rungs', []))}


def build_system_routines(controller: str, tags: list[dict]) -> list[dict]:
    """FMS enable + inhibits adapted from MGE9/MQJ9 PRISM references."""
    rungs: list[tuple[str, str]] = [
        (
            'PRISM ref: MGE9/MQJ9 RT_Inhibits — create BOOL tag FMS_Enabled (controller scope)',
            'NOP();',
        ),
        (
            'System enable — any zone MCR latched enables FMS (adapt HMI tags as needed)',
            'XIC(IO_1MCR1)XIC(IO_2MCR1)XIC(IO_3MCR1)XIC(IO_4MCR1)OTL(FMS_Enabled);',
        ),
        (
            'All zones stopped — drop FMS enable',
            'XIO(IO_1MCR1)XIO(IO_2MCR1)XIO(IO_3MCR1)XIO(IO_4MCR1)OTU(FMS_Enabled);',
        ),
        (
            'PRISM ref: MQJ9 RT_Inhibits Rung0 — inhibit output when FMS disabled',
            'XIO(FMS_Enabled)OTU(Out_Inhibit)TND();',
        ),
        (
            'PRISM ref: MGE9 CIP01 RT_FMS_INIT — one-shot data reset (add OSR/FMS_Data_Reset tags)',
            'XIC(FMS_Data_Reset)OTL(FMS_Init_Done);',
        ),
        (
            'PRISM ref: aoFMS_Seq_Zones — import AOI from corpus before calling in zone programs',
            'NOP();',
        ),
    ]
    return [{
        'routine': 'RT_FMS_Control',
        'program': 'PG_ORDENCOMM',
        'device_class': 'System',
        'filename': 'RT_FMS_Control.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_FMS_Control',
            'rungs': rungs,
            'reference_note': 'MGE9 RT_Inhibits, MQJ9 RT_Inhibits, CIP01 RT_FMS_INIT',
        },
    }]


def build_area_routines(
    scaffold: dict,
    area: str,
    *,
    include_motor: bool = False,
) -> list[dict]:
    tags = scaffold.get('tags') or []
    motor_chains = scaffold.get('motor_chains') or []
    controller = scaffold.get('system') or 'FortnaSite'
    area_tags = [t for t in tags if (t.get('area') or '') == area]
    if not area_tags:
        return []

    prog = f'PG_{area}' if area != 'ORDENCOMM' else 'PG_ORDENCOMM'
    safe = re.sub(r'[^A-Z0-9]', '', area.upper())[:10] or 'MAIN'
    out: list[dict] = []

    pe_tags = [t for t in area_tags if t.get('device_class') == 'Photoeye']
    pe_rungs = build_routine_rungs(pe_tags, all_tags=tags, motor_chains=motor_chains) if pe_tags else []
    if area == 'ORDENCOMM' and pe_tags:
        covered = {r[1] for r in pe_rungs}
        for tag in pe_tags:
            stub = f"XIC({tag['tag']})NOP();"
            if stub not in covered and tag.get('type', 'IN') == 'IN':
                pe_rungs.append((
                    f"{tag.get('fortna_name')} @ {tag.get('fortna_address')} — PE input (PRISM: use aoFMS_Array_PE)",
                    stub,
                ))
    if pe_rungs:
        out.append({
            'routine': f'RT_PE_{safe}',
            'program': prog,
            'device_class': 'Photoeye',
            'filename': f'RT_PE_{safe}.L5X',
            'kwargs': {
                'controller': controller,
                'program': prog,
                'routine_name': f'RT_PE_{safe}',
                'rungs': pe_rungs[:120],
                'reference_note': 'fortna_device_logic + MGE9/MQJ9 PE patterns',
            },
        })

    conv_tags = [
        t for t in area_tags
        if t.get('device_class') in ('Conveyor', 'Photoeye')
        and (t.get('fortna_name') or '').upper().startswith(('SSV', 'EZPWS'))
    ]
    if not conv_tags:
        conv_tags = [t for t in area_tags if (t.get('fortna_name') or '').upper().startswith(('SSV', 'EZPWS'))]
    conv_rungs = build_routine_rungs(conv_tags, all_tags=tags, motor_chains=motor_chains) if conv_tags else []
    if conv_rungs:
        out.append({
            'routine': f'RT_Conveyor_{safe}',
            'program': prog,
            'device_class': 'Conveyor',
            'filename': f'RT_Conveyor_{safe}.L5X',
            'kwargs': {
                'controller': controller,
                'program': prog,
                'routine_name': f'RT_Conveyor_{safe}',
                'rungs': conv_rungs[:80],
                'reference_note': 'SSV/EZPWS hold — MQJ9 conveyor refs',
            },
        })

    bc_tags = [t for t in area_tags if t.get('device_class') == 'Beacon']
    bc_rungs = build_routine_rungs(bc_tags, all_tags=tags, motor_chains=motor_chains) if bc_tags else []
    if bc_rungs:
        out.append({
            'routine': f'RT_Beacon_{safe}',
            'program': prog,
            'device_class': 'Beacon',
            'filename': f'RT_Beacon_{safe}.L5X',
            'kwargs': {
                'controller': controller,
                'program': prog,
                'routine_name': f'RT_Beacon_{safe}',
                'rungs': bc_rungs[:80],
                'reference_note': 'Zone MCR gated beacons',
            },
        })

    if include_motor:
        mcr = build_mcr_rungs(tags)
        mc = build_motor_chain_rungs(motor_chains, tags, area=area if area != 'ORDENCOMM' else None)
        motor_rungs = [(c, t) for c, t in (mcr + mc)[:100]]
        if motor_rungs:
            out.append({
                'routine': 'RT_Motor_Chains',
                'program': 'PG_ORDENCOMM',
                'device_class': 'MotorChain',
                'filename': 'RT_Motor_Chains.L5X',
                'kwargs': {
                    'controller': controller,
                    'program': 'PG_ORDENCOMM',
                    'routine_name': 'RT_Motor_Chains',
                    'rungs': motor_rungs,
                    'reference_note': 'Mtrchain.asc + MGE9 motor interlock patterns',
                },
            })

    return out


def copy_required_aois(aoi_dir: Path, *, mhs_guidelines: bool) -> list[dict]:
    """Copy only AOIs used by generated routines (no corpus dump)."""
    aoi_dir.mkdir(parents=True, exist_ok=True)
    if not mhs_guidelines:
        return _copy_legacy_aoi_references(aoi_dir)
    copied: list[dict] = []
    corpus = prism_root() / 'knowledge-corpus'
    for rel_path, dest_name in REQUIRED_AOIS:
        src = corpus / rel_path.replace('/', '\\').replace('\\', '/')
        src = corpus / Path(rel_path)
        if not src.is_file():
            continue
        dest = aoi_dir / dest_name
        shutil.copy2(src, dest)
        copied.append({'aoi': dest_name, 'source': str(src), 'dest': str(dest)})
    return copied


def _copy_legacy_aoi_references(aoi_dir: Path) -> list[dict]:
    """PoC mode — limited AOI set for non-MHS builds."""
    hints = ('aofms_splitter', 'aofms_seq_zones', 'aofms_array_pe')
    corpus = prism_root() / 'knowledge-corpus'
    copied: list[dict] = []
    aoi_dir.mkdir(parents=True, exist_ok=True)
    for site_dir in corpus.iterdir():
        if not site_dir.is_dir():
            continue
        prog = site_dir / 'programs'
        if not prog.is_dir():
            continue
        for l5x in prog.glob('*.L5X'):
            if not any(h in l5x.name.lower() for h in hints):
                continue
            dest = aoi_dir / l5x.name
            if dest.exists():
                continue
            shutil.copy2(l5x, dest)
            copied.append({'site': site_dir.name, 'source': str(l5x), 'dest': str(dest)})
    return copied


def build_program(export_dir: Path, *, mhs_guidelines: bool = False) -> dict:
    scaffold, base = load_manifest(export_dir, None)
    if mhs_guidelines:
        studio = base / 'studio_import'
        routines_dir = studio / '04_routines'
        aoi_dir = studio / '03_aois'
        out_dir = studio
    else:
        seeded = base / 'prism_seeded'
        out_dir = seeded / 'built_program'
        routines_dir = out_dir / 'import_routines'
        aoi_dir = out_dir / 'aoi_import'
    routines_dir.mkdir(parents=True, exist_ok=True)

    controller = scaffold.get('system') or 'OReillyDC27_ORDENCOMM'
    specs: list[dict] = []
    if mhs_guidelines:
        specs.extend(build_mhs_program_specs(scaffold))
    else:
        specs.extend(build_system_routines(controller, scaffold.get('tags') or []))
        areas = sorted({t.get('area') for t in scaffold.get('tags', []) if t.get('area')})
        for area in areas:
            specs.extend(build_area_routines(
                scaffold, area, include_motor=(area == 'ORDENCOMM'),
            ))

    written = []
    total_rungs = 0
    for spec in specs:
        kw = spec['kwargs']
        entry = write_routine(routines_dir, spec['filename'], **kw)
        entry.update({
            'routine': spec['routine'],
            'program': spec['program'],
            'device_class': spec['device_class'],
        })
        written.append(entry)
        total_rungs += entry['rungs']

    aoi_copies = copy_required_aois(aoi_dir, mhs_guidelines=mhs_guidelines)
    corpus_refs = scan_corpus_l5x(sum(CORPUS_FILE_HINTS.values(), []), limit=15)

    build_label = (
        'OReillyDC27_ORDENCOMM — Studio 5000 Import Package'
        if mhs_guidelines
        else 'OReillyDC27_ORDENCOMM — PRISM Built Program (PoC)'
    )
    out_rel = 'studio_import' if mhs_guidelines else out_dir.name
    report_lines = [
        build_label,
        '=' * 60,
        f'Generated: {datetime.now(timezone.utc).isoformat()}',
        f'Controller: {controller}',
        f'MHS guidelines mode: {mhs_guidelines}',
        f'I/O points: {scaffold.get("stats", {}).get("total")}',
        f'Routines written: {len(written)}',
        f'Total ladder rungs: {total_rungs}',
        f'AOI reference files copied: {len(aoi_copies)}',
        '',
        'MHS GUIDELINE SOURCES' if mhs_guidelines else 'STUDIO 5000 IMPORT ORDER',
        '-' * 40,
    ]
    if mhs_guidelines:
        report_lines.extend([
            '  D:\\MHS Guidlines\\Non Con Guidlines.txt',
            '  D:\\MHS Guidlines\\Quick Notes Docs\\fms_shoesorter.docx',
            '  D:\\MHS Guidlines\\Quick Notes Docs\\Quick divert arm set up code.docx',
            '',
            'REQUIRED AOI (only one)',
            '-' * 40,
            '  studio_import/03_aois/aoFMS_Splitter.L5X',
            '',
            'CONTROLLER BOOL TAGS TO ADD MANUALLY',
            '-' * 40,
            '  FMS_Enabled, Out_Inhibit, FMS_Data_Reset, FMS_Init_Done',
            '  xSOL_SSV506A1_Fire … xSOL_SSV506E2_Fire (one per solenoid)',
            '  xGL_Lvl2, xGL_Lvl3, Start_Cmd, Stop_Cmd, SYS_Ready',
            '',
        ])
    report_lines.extend([
        'STUDIO 5000 IMPORT ORDER',
        '-' * 40,
        '1. Import tags:     studio_import/01_tags/ORiellys_Controller_Tags.csv',
        '2. Import programs: studio_import/02_programs/PG_*.L5X',
        '3. Import AOI:      studio_import/03_aois/aoFMS_Splitter.L5X',
        '4. Import routines: studio_import/04_routines/*.L5X into matching PG_* programs',
        '5. Add controller BOOL tags listed above',
        '6. Map Bank*.bit BOOL tags to PointIO/Local aliases before download',
        '',
        'ROUTINES',
        '-' * 40,
    ])
    for w in written:
        report_lines.append(
            f"  {w['program']}/{w['routine']} — {w['rungs']} rungs — {w['filename']}"
        )
    report_lines.extend([
        '',
        'PRISM REFERENCES USED',
        '-' * 40,
        '  MGE9_MCP05: RT_Inhibits, RT_Paddle_Divert, aoFMS_Splitter',
        '  MQJ9: RT_Inhibits, aoFMS_Seq_Zones, aoFMS_LaneInhibit',
        '  AMAZON_FMS: aoFMS_Splitter, aoFMS_Seq_Zones, aoFMS_Array_PE',
        '  MGE9 CIP01: RT_FMS_INIT',
        '',
        'LIMITATIONS (not production-ready)',
        '-' * 40,
        '  - xSOL_*_Fire bits must be wired from aoFMS_Splitter / RT_Paddle_Divert',
        '  - Jam PE / conv run tag names need drawing cross-check',
        '  - Gridlock tags (adiPPH_Sorter_*) need FMS flow logic or HMI simulation',
        '  - Review all rungs in Factory I/O simulation before site download',
    ])
    report_path = base / 'IMPORT_GUIDE.txt' if mhs_guidelines else out_dir / 'BUILD_REPORT.txt'
    report_path.write_text('\n'.join(report_lines), encoding='utf-8')

    manifest = {
        'ok': True,
        'controller': controller,
        'mhs_guidelines': mhs_guidelines,
        'built_program_dir': str(out_dir),
        'routines_dir': str(routines_dir),
        'aoi_dir': str(aoi_dir),
        'routine_count': len(written),
        'total_rungs': total_rungs,
        'routines': written,
        'aoi_copies': aoi_copies,
        'corpus_refs': corpus_refs,
        'report': str(report_path),
    }
    manifest_path = base / 'PROGRAM_MANIFEST.json' if mhs_guidelines else out_dir / 'PROGRAM_MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest['manifest'] = str(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description='Build PRISM-referenced Fortna ladder program')
    parser.add_argument('--export-dir', required=True)
    parser.add_argument(
        '--mhs-guidelines',
        action='store_true',
        help='Rewrite per D:\\MHS Guidlines (Non-Con + AOI Guide + FMS shoe sorter)',
    )
    args = parser.parse_args()
    try:
        result = build_program(Path(args.export_dir), mhs_guidelines=args.mhs_guidelines)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())