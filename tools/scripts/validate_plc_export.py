#!/usr/bin/env python3
"""Validate FortnaPlus L5X + FACTORYIO export artifacts."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def validate_l5x(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding='utf-8')
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        errors.append(f'L5X XML parse error: {exc}')

    tags = set(re.findall(r'<Tag Name="([^"]+)"', text))
    xic = set(re.findall(r'XIC\(([^)]+)\)', text))
    missing = sorted(xic - tags)
    if missing:
        errors.append(f'Routines reference undefined tags ({len(missing)}): {missing[:5]}')

    bad = [t for t in tags if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', t)]
    if bad:
        errors.append(f'Invalid Logix tag names ({len(bad)}): {bad[:5]}')

    prog_idx = text.find('<Programs>')
    tags_idx = text.find('<Tags>')
    if prog_idx >= 0 and tags_idx > prog_idx:
        errors.append('Tags section appears after Programs (Studio import may fail)')

    if 'SoftwareRevision="32.00"' not in text:
        errors.append('Unexpected SoftwareRevision (expected 32.00)')

    return errors


def validate_factoryio(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding='utf-8-sig')
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        errors.append(f'FACTORYIO XML parse error: {exc}')

    if 'BulbLamp' in text:
        errors.append('BulbLamp prefab invalid in Factory IO 2.5+ (use WarningLight)')
    if 'AllenBradleyLogix5000' not in text:
        errors.append('Missing AllenBradleyLogix5000 driver section')
    if 'CurrentDriver="32768"' not in text:
        errors.append('Logix5000 driver not set as CurrentDriver')
    if 'OrbitCamera' not in text:
        errors.append('Missing OrbitCamera (scene may not open)')
    if 'BitInputPrefix="BOOL_IN_"' not in text:
        errors.append('Missing BOOL_IN_ driver prefix')

    input_keys = re.findall(r'<BinaryInput[^>]+Key="([^"]+)"', text)
    output_keys = re.findall(r'<BinaryOutput[^>]+Key="([^"]+)"', text)
    bound_in = re.findall(r'<BitInput\d+ PointIOKey="([^"]+)"', text)
    bound_out = re.findall(r'<BitOutput\d+ PointIOKey="([^"]+)"', text)

    if m := re.search(r'BitInputCount="(\d+)" BitOutputCount="(\d+)"', text):
        declared_in, declared_out = int(m.group(1)), int(m.group(2))
        if declared_in != len(bound_in):
            errors.append(f'BitInputCount ({declared_in}) != BitInput bindings ({len(bound_in)})')
        if declared_out != len(bound_out):
            errors.append(f'BitOutputCount ({declared_out}) != BitOutput bindings ({len(bound_out)})')

    if len(bound_in) != len(input_keys):
        errors.append(f'BitInput bindings ({len(bound_in)}) != BinaryInput count ({len(input_keys)})')
    if len(bound_out) != len(output_keys):
        errors.append(f'BitOutput bindings ({len(bound_out)}) != BinaryOutput count ({len(output_keys)})')

    frac = re.findall(r'<Position X="\d+\.\d+"', text)
    if frac:
        errors.append(f'Fractional object positions ({len(frac)}) — Factory I/O may reject scene')

    missing_in = [k for k in bound_in if k not in input_keys]
    missing_out = [k for k in bound_out if k not in output_keys]
    if missing_in:
        errors.append(f'BitInput PointIOKey mismatch ({len(missing_in)} orphans)')
    if missing_out:
        errors.append(f'BitOutput PointIOKey mismatch ({len(missing_out)} orphans)')

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: validate_plc_export.py <export_dir>')
        return 1

    export_dir = Path(sys.argv[1])
    fio_files = list(export_dir.glob('*.FACTORYIO'))
    studio_tags = list((export_dir / 'studio_import' / '01_import_tags_here').glob('*_Controller_Tags.csv'))
    studio_progs = list((export_dir / 'studio_import' / '02_import_programs_here').glob('*.L5X'))
    studio_rts = list((export_dir / 'studio_import' / '03_import_routines_into_MainProgram').glob('*.L5X'))
    if not fio_files or not studio_tags or not studio_progs or not studio_rts:
        print('ERROR: missing studio_import bundle or FACTORYIO in export_dir')
        return 1

    all_errors: list[str] = []
    tags_csv = studio_tags[0]
    tags_text = tags_csv.read_text(encoding='utf-8')
    lines = [ln for ln in tags_text.replace('\r\n', '\n').split('\n') if ln != '']
    if not lines or lines[0] != 'remark,"CSV-Import-Export"':
        all_errors.append('Controller tags CSV line 1 must be remark,"CSV-Import-Export"')
    if len(lines) < 2 or lines[1].strip() != '0.3':
        got = lines[1].strip() if len(lines) > 1 else 'missing'
        all_errors.append(f'Controller tags CSV line 2 must be 0.3 (got {got!r})')
    if 'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES' not in tags_text:
        all_errors.append('Controller tags CSV missing column header row')
    if ',BOOL,,' not in tags_text and ',"BOOL",' not in tags_text:
        all_errors.append('Controller tags CSV has no BOOL tag rows')
    for prog_path in studio_progs:
        prog_text = prog_path.read_text(encoding='utf-8')
        if 'TargetType="Program"' not in prog_text:
            all_errors.append(f'{prog_path.name}: missing TargetType=Program')
        if re.search(r'<Routine\s+Use="Context"', prog_text):
            all_errors.append(
                f'{prog_path.name}: routines must not use Use="Context" (Studio program import)'
            )
        if not re.search(r'<Routine\s+Name="[^"]+"\s+Type="RLL">', prog_text):
            all_errors.append(f'{prog_path.name}: no MGE9-style <Routine Name=... Type=RLL> blocks')
    rt_text = studio_rts[0].read_text(encoding='utf-8')
    if 'TargetType="Routine"' not in rt_text:
        all_errors.append('Routine L5X missing TargetType=Routine')
    all_errors.extend(validate_factoryio(fio_files[0]))

    if all_errors:
        print('VALIDATION FAILED')
        for err in all_errors:
            print(f'  - {err}')
        return 1

    print('VALIDATION OK')
    print(f'  Studio tags CSV: {tags_csv.name}')
    print(f'  Studio programs: {len(studio_progs)} file(s)')
    print(f'  Studio routines: {len(studio_rts)} file(s)')
    print(f'  FACTORYIO: {fio_files[0].name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())