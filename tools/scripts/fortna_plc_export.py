#!/usr/bin/env python3
"""
fortna_plc_export.py — Convert Fortna RUN .tar.gz to Studio 5000 L5X + Factory I/O.

Reads Fortna .asc I/O tables (Conveyor.asc, BeaconInfo, project.cfg) and produces:
  - fortna_io_manifest.json   — extracted I/O + layout summary
  - fortna_tags.csv           — tag list for review
  - <controller>_Controller_Tags.csv — Studio 5000 Tools->Import tag CSV
  - factory_io_bindings.csv   — Factory I/O driver binding helper
  - <system>.L5X              — importable Studio 5000 scaffold (tags + programs)
  - <system>.FACTORYIO        — Factory I/O scene (layout + I/O memories)
  - export_report.txt         — human-readable QA summary

Usage:
  py tools/scripts/fortna_plc_export.py import D:\\path\\ORDENCOMM-RUN.tar.gz
  py tools/scripts/fortna_plc_export.py export --run-dir workspace/active/RUN
  py tools/scripts/fortna_plc_export.py export --archive D:\\path\\RUN.tar.gz
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import uuid
from collections import defaultdict
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
sys.path.insert(0, str(SCRIPT_DIR))

from apply_recipe import extract_run, import_package  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    extract_beacon_outputs,
    extract_io_points,
    normalize_coords,
    read_project_meta,
    scaled_fio_coord,
    summarize_io,
)
from fortna_device_logic import build_routine_rungs  # noqa: E402
from fortna_ignition_extract import extract_gwbk  # noqa: E402
from fortna_motor_logic import (  # noqa: E402
    build_mcr_rungs,
    build_motor_chain_rungs,
    extract_motor_chains,
)

FIO_SDK_TEMPLATE = REPO_ROOT / 'tools' / 'templates' / 'SDK_Write_Sample.FACTORYIO'
FIO_SDK_FALLBACK = Path(r'C:\Users\curtiskricke\worktrees\Rockwell_GitHub\tools\factoryio-sdk\factoryio-sdk-master\samples\Saved Scenes\SDK Write Sample.FACTORYIO')

FIO_DRIVER_KEYS = {
    'RunInputKey': 'ca793c02-4ed8-4cbc-95f8-ff692742f818',
    'PauseInputKey': '29ae986d-6f80-46c7-9c0d-02f4a9978b0f',
    'ResetInputKey': 'bbfbe4c0-523a-400a-aa28-ab38a8b906c7',
    'TimeScaleInputKey': 'fd8420d7-68ea-4f8a-991f-25789196fa3d',
}

FIO_PREFABS = {
    'Photoeye': 'DiffusePhotoelectricSensor',
    'DigitalInput': 'DiffusePhotoelectricSensor',
    'Motor': 'RollerConveyor4M',
    'Beacon': 'WarningLight',
    'Conveyor': 'RollerConveyor4M',
    'Scanner': 'DiffusePhotoelectricSensor',
    'IO': 'DiffusePhotoelectricSensor',
}

FIO_OM = {
    'Photoeye': '$$C_DefaultSensor_OM_Binary_NAME',
    'DigitalInput': '$$C_DefaultSensor_OM_Binary_NAME',
    'Motor': '$C_RollerConveyor_OM_SingleBinary_NAME',
    'Beacon': '$C_WarningLight_OM_Default_NAME',
    'Conveyor': '$C_RollerConveyor_OM_SingleBinary_NAME',
    'Scanner': '$$C_DefaultSensor_OM_Binary_NAME',
    'IO': '$$C_DefaultSensor_OM_Binary_NAME',
}

RESERVED_INPUT_BITS = {496, 497, 498}
RESERVED_OUTPUT_BITS = {496, 497, 498}


def new_key() -> str:
    return str(uuid.uuid4())


def _program_name(area: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9_]', '_', area.upper())
    return f'PG_{safe}'[:20]


def _routine_name(device_class: str) -> str:
    return f'R_{device_class}'[:20]


def _controller_name(meta: dict) -> str:
    project = (meta.get('project_name') or 'FortnaSite').strip()
    machine = (meta.get('machine_name') or 'RUN').strip()
    name = f'{project}_{machine}'
    return re.sub(r'[^A-Za-z0-9_]', '_', name)[:40]


def build_scaffold(meta: dict, points: list[dict], beacons: list[dict]) -> dict:
    system = _controller_name(meta)
    programs_map: dict[str, dict] = {}

    for p in points:
        area = p['area']
        if area not in programs_map:
            programs_map[area] = {
                'name': _program_name(area),
                'area': area,
                'tag_count': 0,
                'routines': {},
                'modules': set(),
            }
        prog = programs_map[area]
        prog['tag_count'] += 1
        prog['modules'].add(p.get('module', ''))
        dc = p['device_class']
        rname = _routine_name(dc)
        if rname not in prog['routines']:
            prog['routines'][rname] = {
                'name': rname,
                'device_class': dc,
                'tag_count': 0,
                'tags': [],
            }
        rt = prog['routines'][rname]
        rt['tag_count'] += 1
        if len(rt['tags']) < 50:
            rt['tags'].append(p['tag'])

    programs = []
    for area in sorted(programs_map):
        prog = programs_map[area]
        prog['modules'] = sorted(m for m in prog['modules'] if m)
        prog['routines'] = list(prog['routines'].values())
        programs.append(prog)

    tags = []
    for p in points:
        tags.append({
            'tag': p['tag'],
            'fortna_name': p.get('fortna_name') or p.get('io_name') or p['tag'],
            'alias_for': '',
            'fortna_address': p['fortna_address'],
            'area': p['area'],
            'program': _program_name(p['area']),
            'device_class': p['device_class'],
            'fio_object_type': p['device_class'],
            'type': p['io_type'],
            'module': p.get('module', ''),
            'description': p.get('description') or p.get('fortna_name') or p['tag'],
            'conveyor': p.get('conveyor', ''),
            'x': p.get('x'),
            'y': p.get('y'),
        })

    return {
        'system': system,
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': 'FortnaPlus',
        'fortna_meta': meta,
        'stats': summarize_io(points),
        'beacon_map': beacons,
        'programs': programs,
        'tags': tags,
        'points': points,
    }


def write_tags_csv(tags: list[dict], path: Path) -> None:
    fields = [
        'tag', 'type', 'device_class', 'area', 'program', 'fortna_address',
        'description', 'conveyor', 'module',
    ]
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for t in tags:
            row = dict(t)
            row['fortna_address'] = t.get('fortna_address', '')
            w.writerow(row)


def _studio_csv_description(tag: dict) -> str:
    """Studio CSV import rejects some punctuation in descriptions."""
    fname = tag.get('fortna_name', tag['tag'])
    faddr = tag.get('fortna_address', '')
    desc = tag.get('description') or fname
    text = f'Fortna {fname} @ {faddr} - {desc}'
    text = text.replace('\r\n', '$N').replace('\n', '$N')
    text = text.replace('"', '').replace("'", '')
    text = text.replace('—', '-').replace('=', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def write_studio_tags_csv(
    tags: list[dict],
    path: Path,
    *,
    controller_context: str,
    software_version: str = 'Studio 5000 v32.00',
) -> int:
    """
    Studio 5000 controller tag import CSV (Tools -> Import).

    Studio expects:
      line 1: remark,"CSV-Import-Export"
      line 2: 0.3
      line 3: TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES
    Use CRLF throughout (mixed LF breaks version parsing on Windows).
    Empty SCOPE = controller-scoped tag.
    """
    eol = '\r\n'
    rows: list[list[str]] = []
    seen: set[str] = set()
    for tag in tags:
        tname = tag['tag']
        if tname in seen:
            continue
        seen.add(tname)
        rows.append([
            'TAG',
            '',
            tname,
            _studio_csv_description(tag),
            'BOOL',
            '',
            '(RADIX := Decimal)',
        ])

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator=eol)
    writer.writerow([
        'TYPE', 'SCOPE', 'NAME', 'DESCRIPTION', 'DATATYPE', 'SPECIFIER', 'ATTRIBUTES',
    ])
    writer.writerows(rows)

    preamble = f'remark,"CSV-Import-Export"{eol}0.3{eol}'
    text = preamble + buf.getvalue()
    if not text.endswith(eol):
        text += eol
    path.write_bytes(text.encode('utf-8'))
    return len(rows)


def write_factory_io_bindings(tags: list[dict], path: Path) -> None:
    fields = ['tag', 'alias_for', 'area', 'program', 'device_class', 'fio_object_type', 'type', 'module']
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for t in tags:
            w.writerow({k: t.get(k, '') for k in fields})


def _xml_cdata(text: str) -> str:
    return (text or '').replace(']]>', ']] >')


def _xml_attr(text: str) -> str:
    return (text or '').replace('&', '&amp;').replace('"', '&quot;').replace("'", '&apos;')


L5X_EXPORT_OPTIONS = (
    'References NoRawData L5KData DecoratedData Context Dependencies '
    'ForceProtectedEncoding AllProjDocTrans'
)
DEFAULT_CONTROLLER_CONTEXT = 'ORiellys'
DEFAULT_TARGET_PROGRAM = 'MainProgram'


def _l5x_export_date() -> str:
    return datetime.now().strftime('%a %b %d %H:%M:%S %Y')


def _l5x_open(
    *,
    target_name: str,
    target_type: str,
    contains_context: bool,
    extra_attrs: str = '',
) -> str:
    ctx = 'true' if contains_context else 'false'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="32.00" '
        f'TargetName="{target_name}" TargetType="{target_type}"{extra_attrs} '
        f'ContainsContext="{ctx}" ExportDate="{_l5x_export_date()}" '
        f'ExportOptions="{L5X_EXPORT_OPTIONS}">'
    )


def _l5x_bool_tag_lines(tags: list[dict]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tname = tag['tag']
        if tname in seen:
            continue
        seen.add(tname)
        faddr = tag.get('fortna_address', '')
        fname = tag.get('fortna_name', tname)
        desc = _xml_cdata(tag.get('description') or fname)
        full_desc = _xml_cdata(f'Fortna {fname} @ {faddr} - {desc}')
        lines.extend([
            (
                f'<Tag Name="{tname}" Class="Standard" TagType="Base" DataType="BOOL" '
                f'Radix="Decimal" Constant="false" ExternalAccess="Read/Write">'
            ),
            '<Data Format="L5K">',
            '<![CDATA[0]]>',
            '</Data>',
            '<Data Format="Decorated">',
            '<DataValue DataType="BOOL" Radix="Decimal" Value="0"/>',
            '</Data>',
            f'<Description><![CDATA[{full_desc}]]></Description>',
            '</Tag>',
        ])
    return lines


def _routine_rll_block(
    routine_name: str,
    rungs: list[tuple[str, str]],
    *,
    export_kind: str = 'program',
) -> list[str]:
    """Program exports use bare Routine tags (MGE9 PG_FMS pattern); routine imports use Use=Target."""
    if export_kind == 'routine':
        open_tag = f'<Routine Use="Target" Name="{routine_name}" Type="RLL">'
    else:
        open_tag = f'<Routine Name="{routine_name}" Type="RLL">'
    lines = [open_tag, '<RLLContent>']
    for idx, (comment, text) in enumerate(rungs):
        lines.append(
            f'<Rung Number="{idx}" Type="N">'
            f'<Comment><![CDATA[{_xml_cdata(comment)}]]></Comment>'
            f'<Text><![CDATA[{_xml_cdata(text)}]]></Text></Rung>'
        )
    lines.extend(['</RLLContent>', '</Routine>'])
    return lines


def _area_tags(scaffold: dict, area: str) -> list[dict]:
    return [t for t in scaffold['tags'] if t.get('area') == area]


def _routine_rungs_for_tags(
    tags: list[dict],
    *,
    io_map: bool = False,
    scaffold: dict | None = None,
) -> list[tuple[str, str]]:
    all_tags = (scaffold or {}).get('tags') or tags
    motor_chains = (scaffold or {}).get('motor_chains') or []
    return build_routine_rungs(
        tags,
        all_tags=all_tags,
        motor_chains=motor_chains,
        io_map=io_map,
    )


def write_l5x_tags(scaffold: dict, path: Path, *, controller_context: str) -> None:
    """Import at Controller Tags (NOT MainTask). Matches MGE9 tag export shape."""
    lines = [
        _l5x_open(
            target_name=controller_context,
            target_type='Controller',
            contains_context=True,
        ),
        f'<Controller Use="Context" Name="{controller_context}">',
        '<Tags Use="Target">',
        *_l5x_bool_tag_lines(scaffold['tags']),
        '</Tags>',
        '</Controller>',
        '</RSLogix5000Content>',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_l5x_area_program(
    scaffold: dict,
    path: Path,
    prog: dict,
    *,
    controller_context: str,
) -> None:
    """One Program export per Fortna area — import under controller Programs folder."""
    pname = prog['name']
    area = prog.get('area', '')
    routines = prog.get('routines') or []
    tag_lookup = {t['tag']: t for t in scaffold['tags']}
    routine_blocks: list[str] = []
    main_routine = 'R_MAIN'
    motor_chains = scaffold.get('motor_chains') or []
    chain_rungs = build_motor_chain_rungs(motor_chains, scaffold['tags'], area=area)
    mcr_rungs = build_mcr_rungs(scaffold['tags']) if area == 'ORDENCOMM' else []

    if mcr_rungs:
        routine_blocks.extend(_routine_rll_block('R_MCR', mcr_rungs, export_kind='program'))
        main_routine = 'R_MCR'
    if chain_rungs:
        routine_blocks.extend(
            _routine_rll_block('R_Motor_Chains', chain_rungs, export_kind='program')
        )
        if main_routine == 'R_MAIN':
            main_routine = 'R_Motor_Chains'

    for rt in routines:
        if rt['name'] == 'R_Motor' and chain_rungs:
            continue
        rt_tags = [tag_lookup[name] for name in rt.get('tags', []) if name in tag_lookup]
        if not rt_tags:
            continue
        if main_routine == 'R_MAIN':
            main_routine = rt['name']
        rt_rungs = _routine_rungs_for_tags(rt_tags, scaffold=scaffold)
        if not rt_rungs:
            continue
        routine_blocks.extend(
            _routine_rll_block(rt['name'], rt_rungs, export_kind='program')
        )
    if not routine_blocks:
        main_routine = 'R_MAIN'
        routine_blocks.extend(
            _routine_rll_block('R_MAIN', [('FortnaPlus scaffold', 'NOP();')], export_kind='program')
        )

    lines = [
        _l5x_open(
            target_name=pname,
            target_type='Program',
            contains_context=True,
            extra_attrs=' TargetClass="Standard"',
        ),
        f'<Controller Use="Context" Name="{controller_context}">',
        '<Programs Use="Context">',
        (
            f'<Program Use="Target" Name="{pname}" TestEdits="false" '
            f'MainRoutineName="{main_routine}" Disabled="false" Class="Standard" '
            f'UseAsFolder="false">'
        ),
        '<Tags />',
        '<Routines>',
        *routine_blocks,
        '</Routines>',
        '</Program>',
        '</Programs>',
        '</Controller>',
        '</RSLogix5000Content>',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_l5x_io_map_routine(
    scaffold: dict,
    path: Path,
    *,
    controller_context: str,
    target_program: str,
    routine_name: str,
    area: str | None = None,
) -> None:
    """Routine export — import into MainProgram → Routines (MGE9 RT_Splitter pattern)."""
    tags = _area_tags(scaffold, area) if area else scaffold['tags']
    rungs = _routine_rungs_for_tags(tags, io_map=True, scaffold=scaffold)
    if not rungs:
        rungs = [('No generated I/O logic in scope', 'NOP();')]

    lines = [
        _l5x_open(
            target_name=routine_name,
            target_type='Routine',
            contains_context=True,
            extra_attrs=' TargetSubType="RLL" TargetClass="Standard"',
        ),
        f'<Controller Use="Context" Name="{controller_context}">',
        '<Programs Use="Context">',
        f'<Program Use="Context" Name="{target_program}" Class="Standard">',
        '<Routines Use="Context">',
        *_routine_rll_block(routine_name, rungs, export_kind='routine'),
        '</Routines>',
        '</Program>',
        '</Programs>',
        '</Controller>',
        '</RSLogix5000Content>',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_studio_import_bundle(
    scaffold: dict,
    out_dir: Path,
    *,
    controller_context: str,
    target_program: str,
) -> dict[str, list[str]]:
    """Write MGE9-style import bundle: tags + per-area programs + IO-map routines."""
    studio = out_dir / 'studio_import'
    tags_dir = studio / '01_import_tags_here'
    prog_dir = studio / '02_import_programs_here'
    routine_dir = studio / '03_import_routines_into_MainProgram'
    for d in (tags_dir, prog_dir, routine_dir):
        d.mkdir(parents=True, exist_ok=True)

    tag_csv = tags_dir / f'{controller_context}_Controller_Tags.csv'
    write_studio_tags_csv(
        scaffold['tags'], tag_csv, controller_context=controller_context,
    )

    program_files: list[str] = []
    for prog in scaffold.get('programs', []):
        ppath = prog_dir / f'{prog["name"]}.L5X'
        write_l5x_area_program(scaffold, ppath, prog, controller_context=controller_context)
        program_files.append(str(ppath))

    routine_files: list[str] = []
    all_rt = routine_dir / 'RT_Fortna_IO_Map.L5X'
    write_l5x_io_map_routine(
        scaffold,
        all_rt,
        controller_context=controller_context,
        target_program=target_program,
        routine_name='RT_Fortna_IO_Map',
    )
    routine_files.append(str(all_rt))
    for prog in scaffold.get('programs', []):
        area = prog.get('area', '')
        if not area:
            continue
        rname = f'RT_{prog["name"].removeprefix("PG_")}_IO_Map'
        rpath = routine_dir / f'{rname}.L5X'
        write_l5x_io_map_routine(
            scaffold,
            rpath,
            controller_context=controller_context,
            target_program=target_program,
            routine_name=rname,
            area=area,
        )
        routine_files.append(str(rpath))

    return {
        'tags_csv': [str(tag_csv)],
        'programs': program_files,
        'routines': routine_files,
        'studio_import_dir': str(studio),
    }


def write_l5x_program(scaffold: dict, path: Path, *, controller_context: str) -> None:
    """Legacy single-program export (PG_ORDENCOMM) for backward compatibility."""
    main = next((p for p in scaffold.get('programs', []) if p.get('area') == 'ORDENCOMM'), None)
    if not main:
        main = scaffold['programs'][0]
    write_l5x_area_program(scaffold, path, main, controller_context=controller_context)


def write_l5x(scaffold: dict, path: Path) -> None:
    """Combined controller export for brand-new projects only."""
    sys_name = scaffold['system']
    lines = [
        _l5x_open(target_name=sys_name, target_type='Controller', contains_context=False),
        f'<Controller Use="Target" Name="{sys_name}" ProcessorType="1756-L83ES" '
        f'MajorRev="32" MinorRev="11">',
        '<Tags>',
        *_l5x_bool_tag_lines(scaffold['tags']),
        '</Tags>',
        '</Controller>',
        '</RSLogix5000Content>',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def _next_addr(used: set[int], reserved: set[int]) -> int:
    addr = 0
    while addr in used or addr in reserved:
        addr += 1
    used.add(addr)
    return addr


def _fio_coord(value: float) -> str:
    return str(int(round(value)))


def _render_proxy(prefab: str, x: float, y: float, z: float) -> str:
    return f"""    <Proxy PrefabName="{prefab}" Key="{new_key()}">
      <Position X="{_fio_coord(x)}" Y="{_fio_coord(y)}" Z="{_fio_coord(z)}" />
      <Rotation X="0" Y="0" Z="0" W="1" />
      <Forward X="0" Y="0" Z="1" />
      <Up X="0" Y="1" Z="0" />
      <Right X="1" Y="0" Z="0" />
    </Proxy>"""


def _render_io_object(
    prefab: str, om: str, xml_elem: str, tag: str, address: int, x: float, z: float,
) -> tuple[str, dict]:
    y = 2.0 if xml_elem == 'BinaryInput' else 3.0
    io_key = new_key()
    block = f"""  <Object Locked="False" GroupKey="00000000-0000-0000-0000-000000000000">
{_render_proxy(prefab, x, y, z)}
    <ComponentIO CurrentOperatingMode="0" />
    <OperatingMode Description="{om}">
      <GroupIO Description="Default">
        <{xml_elem} Name="{tag}" Address="{address}" ForcedValue="False" Key="{io_key}" OpenCircuit="False" ShortCircuit="False" UseForcedValue="False" />
      </GroupIO>
    </OperatingMode>
  </Object>"""
    meta = {
        'type': 'io_point',
        'tag': tag,
        'memory_type': 'input' if xml_elem == 'BinaryInput' else 'output',
        'address': address,
        'io_key': io_key,
        'device_class': 'IO',
        'x': x,
        'z': z,
    }
    return block, meta


def _find_fio_template() -> Path:
    for candidate in (FIO_SDK_TEMPLATE, FIO_SDK_FALLBACK):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f'Factory I/O SDK template not found. Expected {FIO_SDK_TEMPLATE}'
    )


def _build_logix_drivers_footer(objects: list[dict]) -> str:
    inputs = sorted(
        [o for o in objects if o.get('memory_type') == 'input'],
        key=lambda o: o['address'],
    )
    outputs = sorted(
        [o for o in objects if o.get('memory_type') == 'output'],
        key=lambda o: o['address'],
    )
    in_count = len(inputs)
    out_count = len(outputs)

    lines = [
        '  <Drivers CurrentDriver="32768"',
        f' RunInputKey="{FIO_DRIVER_KEYS["RunInputKey"]}"',
        f' PauseInputKey="{FIO_DRIVER_KEYS["PauseInputKey"]}"',
        f' ResetInputKey="{FIO_DRIVER_KEYS["ResetInputKey"]}"',
        f' TimeScaleInputKey="{FIO_DRIVER_KEYS["TimeScaleInputKey"]}">',
        '    <AllenBradleyLogix5000>',
        (
            f'      <PointIOCount BitInputCount="{in_count}" BitOutputCount="{out_count}" '
            'FloatInputCount="0" FloatOutputCount="0" IntInputCount="0" IntOutputCount="0" '
            'NumericInputCount="0" NumericOutputCount="0" />'
        ),
        (
            '      <PointIOOffset BitInputOffset="0" BitOutputOffset="0" '
            'FloatInputOffset="0" FloatOutputOffset="0" IntInputOffset="0" '
            'IntOutputOffset="0" NumericInputOffset="0" NumericOutputOffset="0" />'
        ),
    ]
    for idx, obj in enumerate(inputs):
        lines.append(f'      <BitInput{idx} PointIOKey="{obj["io_key"]}" />')
    for idx, obj in enumerate(outputs):
        lines.append(f'      <BitOutput{idx} PointIOKey="{obj["io_key"]}" />')
    lines.extend([
        '      <Properties BitInputPrefix="BOOL_IN_" BitOutputPrefix="BOOL_OUT_" '
        'FloatInputPrefix="FLOAT_IN_" FloatOutputPrefix="FLOAT_OUT_" '
        'IntInputPrefix="INT_IN_" IntOutputPrefix="INT_OUT_" />',
        '    </AllenBradleyLogix5000>',
        '  </Drivers>',
    ])
    return '\n'.join(lines)


def write_fio_driver_bindings(path: Path, objects: list[dict], tags: list[dict]) -> None:
    """CSV mapping Factory I/O memory names (BOOL_IN_n) to Studio 5000 tag names."""
    tag_lookup = {t['tag']: t for t in tags}
    fields = [
        'fio_memory', 'fio_address', 'plc_tag', 'fortna_name', 'fortna_address',
        'memory_type', 'device_class', 'notes',
    ]
    rows = []
    for obj in sorted(objects, key=lambda o: (o.get('memory_type', ''), o['address'])):
        mem = obj.get('memory_type', 'input')
        prefix = 'BOOL_IN_' if mem == 'input' else 'BOOL_OUT_'
        plc_tag = obj['tag']
        src = tag_lookup.get(plc_tag, {})
        rows.append({
            'fio_memory': f'{prefix}{obj["address"]}',
            'fio_address': obj['address'],
            'plc_tag': plc_tag,
            'fortna_name': src.get('fortna_name', plc_tag),
            'fortna_address': src.get('fortna_address', ''),
            'memory_type': mem,
            'device_class': src.get('device_class', obj.get('device_class', 'IO')),
            'notes': 'Bind this FIO memory to plc_tag in Allen-Bradley Logix5000 driver',
        })
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_tag_map_csv(tags: list[dict], path: Path) -> None:
    fields = ['plc_tag', 'fortna_name', 'fortna_address', 'io_type', 'device_class', 'area', 'description']
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for t in tags:
            w.writerow({
                'plc_tag': t['tag'],
                'fortna_name': t.get('fortna_name', ''),
                'fortna_address': t.get('fortna_address', ''),
                'io_type': t.get('type', ''),
                'device_class': t.get('device_class', ''),
                'area': t.get('area', ''),
                'description': t.get('description', ''),
            })


def write_factory_io_scene(
    scaffold: dict, path: Path, *, max_objects: int | None = None,
) -> list[dict]:
    """Build a Factory I/O scene with every I/O point (no artificial cap).

    max_objects: None or <=0 means place all points. Positive value is a rare
    safety override for debugging only.
    """
    template = _find_fio_template().read_text(encoding='utf-8-sig')
    camera_end = template.index('</Camera>') + len('</Camera>')
    instructor_start = template.index('  <Instructor')
    drivers_start = template.index('  <Drivers')
    screenshot_start = template.index('  <Screenshot')
    header = template[:camera_end]
    instructor = template[instructor_start:drivers_start]
    screenshot = template[screenshot_start:]

    system = scaffold['system']
    points = list(scaffold.get('points', []) or [])
    min_x, min_y, span_x, span_y = normalize_coords(points)

    now = datetime.now()
    header = re.sub(
        r'<FactoryIO Type="MySavedScene"[^>]*>',
        (
            f'<FactoryIO Type="MySavedScene" Year="{now.year}" Month="{now.month}" '
            f'Day="{now.day}" Hour="{now.hour}" Minute="{now.minute}" '
            f'Second="{now.second}" Version="1.1.0.6875">'
        ),
        header,
        count=1,
    )
    header = re.sub(
        r'<Description Data="[^"]*"\s*/>',
        f'<Description Data="{_xml_attr(f"FortnaPlus {system} - Logix5000 driver scene (complete I/O)")}" />',
        header,
        count=1,
    )

    used_in: set[int] = set()
    used_out: set[int] = set()
    blocks: list[str] = []
    objects: list[dict] = []
    placed = 0
    grid_i = 0

    # Complete set: points with layout coords first, then remaining (grid-placed)
    with_xy = [p for p in points if p.get('x') is not None and p.get('y') is not None]
    without_xy = [p for p in points if p.get('x') is None or p.get('y') is None]
    ordered = sorted(
        with_xy,
        key=lambda p: (0 if p.get('io_type') == 'IN' else 1, p.get('area', ''), p.get('tag', '')),
    ) + sorted(
        without_xy,
        key=lambda p: (0 if p.get('io_type') == 'IN' else 1, p.get('area', ''), p.get('tag', '')),
    )

    limit = None if (max_objects is None or max_objects <= 0) else int(max_objects)

    for p in ordered:
        if limit is not None and placed >= limit:
            break
        if p.get('x') is not None and p.get('y') is not None:
            fx, fz = scaled_fio_coord(p['x'], p['y'], min_x, min_y, span_x, span_y)
        else:
            # No layout coords — place on a side grid so every tag still appears in FIO
            col = grid_i % 20
            row = grid_i // 20
            fx = float(col * 2)
            fz = float(-8 - row * 2)
            grid_i += 1
        dc = p.get('device_class') or 'IO'
        prefab = FIO_PREFABS.get(dc, 'DiffusePhotoelectricSensor')
        om = FIO_OM.get(dc, '$$C_DefaultSensor_OM_Binary_NAME')
        tag = p['tag']
        if p.get('io_type') == 'OUT':
            addr = _next_addr(used_out, RESERVED_OUTPUT_BITS)
            xml_elem = 'BinaryOutput'
        else:
            addr = _next_addr(used_in, RESERVED_INPUT_BITS)
            xml_elem = 'BinaryInput'
        block, meta = _render_io_object(prefab, om, xml_elem, tag, addr, fx, fz)
        meta['device_class'] = dc
        meta['has_layout'] = p.get('x') is not None and p.get('y') is not None
        blocks.append(block)
        objects.append(meta)
        placed += 1

    drivers = _build_logix_drivers_footer(objects)
    xml_text = header + '\n' + '\n'.join(blocks) + '\n' + instructor + '\n' + drivers + '\n' + screenshot
    path.write_text(xml_text, encoding='utf-8')
    return objects


def write_report(
    scaffold: dict,
    path: Path,
    *,
    controller_context: str = DEFAULT_CONTROLLER_CONTEXT,
) -> None:
    system = scaffold.get('system', '')
    meta = scaffold.get('fortna_meta', {})
    stats = scaffold.get('stats', {})
    lines = [
        'FortnaPlus PLC Export Report',
        '=' * 40,
        f'Generated: {scaffold.get("generated", "")}',
        f'Controller: {scaffold.get("system", "")}',
        f'Project: {meta.get("project_name", "")}',
        f'Machine: {meta.get("machine_name", "")}',
        '',
        'I/O Summary',
        f'  Total points: {stats.get("total", 0)}',
        f'  Inputs:  {stats.get("inputs", 0)}',
        f'  Outputs: {stats.get("outputs", 0)}',
        f'  With layout coords: {stats.get("with_coords", 0)}',
        '',
        'Areas:',
    ]
    for area, count in sorted((stats.get('areas') or {}).items()):
        lines.append(f'  {area}: {count}')
    lines.append('')
    lines.append('Device classes:')
    for dc, count in sorted((stats.get('device_classes') or {}).items()):
        lines.append(f'  {dc}: {count}')
    lines.extend([
        '',
        'IMPORTANT — Review before production use:',
        '  1. Fortna internal I/O banks are exported as BOOL tags with bank/bit in description.',
        '  2. Map each tag to real Logix aliases (Local:/PointIO:/EIP:) using your electrical drawings.',
        '  3. PG_ORDENCOMM has R_MCR + R_Motor_Chains; zone PG_* have PE/SSV/EZPWS + beacon logic.',
        '  4. Factory I/O scene includes Allen-Bradley Logix5000 driver (BOOL_IN_/BOOL_OUT_).',
        '  5. Use fio_driver_bindings.csv to bind FIO memories to plc_tag names in Studio.',
        '  6. Tags starting with digits are prefixed IO_ (see fortna_tag_map.csv).',
        '  7. Motor chain timers/latches/horns are not generated — add per FPC-Motor-Startup-Chains.docx.',
        '',
        'Studio 5000 import (ORiellys / existing project) — use studio_import/ folder:',
        f'  Step 1 TAGS:  Tools -> Import -> studio_import/01_import_tags_here/{controller_context}_Controller_Tags.csv',
        '  Step 2 PROGS: Programs (NOT MainTask) -> Import -> studio_import/02_import_programs_here/PG_*.L5X',
        '  Step 3 RTNS:  MainProgram -> Routines -> Import -> studio_import/03_import_routines_into_MainProgram/RT_*.L5X',
        '  Do NOT import under MainTask (Error 5078). Tags must be .csv (not L5X).',
        '',
        'Factory I/O:',
        f'  - Open {system}.FACTORYIO in Factory I/O (not Studio 5000).',
        '  - Driver should be Allen-Bradley Logix5000; BOOL_IN_/BOOL_OUT_ tags appear on connect.',
    ])
    path.write_text('\n'.join(lines), encoding='utf-8')


def resolve_run_dir(archive: str = '', run_dir: str = '', use_active: bool = False) -> Path:
    if run_dir:
        p = Path(run_dir)
        if (p / 'project.cfg').is_file():
            return p
        if (p / 'RUN' / 'project.cfg').is_file():
            return p / 'RUN'
        raise FileNotFoundError(f'RUN folder not found: {run_dir}')

    if archive:
        return extract_run(Path(archive))

    if use_active:
        for candidate in (
            REPO_ROOT / 'workspace' / 'active' / 'RUN',
            REPO_ROOT / 'workspace' / 'active_work' / 'RUN',  # OneDrive fallback
        ):
            if candidate.is_dir() and (candidate / 'project.cfg').is_file():
                return candidate
        raise FileNotFoundError(
            'No active RUN workspace. Import a .tar.gz first (Workspace tab or PLC Export archive).'
        )

    raise FileNotFoundError('Provide --archive, --run-dir, or --use-active')


def _validate_export_dir(out: Path, system: str) -> list[str]:
    """Lightweight post-export checks (tag names, FIO driver bindings)."""
    errors: list[str] = []
    l5x = out / f'{system}.L5X'
    fio = out / f'{system}.FACTORYIO'
    if not l5x.is_file() or not fio.is_file():
        return ['Missing L5X or FACTORYIO output files']

    l5x_text = l5x.read_text(encoding='utf-8')
    tags = set(re.findall(r'<Tag Name="([^"]+)"', l5x_text))
    bad = [t for t in tags if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', t)]
    if bad:
        errors.append(f'Invalid Logix tag names: {bad[:5]}')
    prog_idx = l5x_text.find('<Programs>')
    tags_idx = l5x_text.find('<Tags>')
    if prog_idx >= 0 and tags_idx > prog_idx:
        errors.append('Tags must appear before Programs in L5X')

    fio_text = fio.read_text(encoding='utf-8-sig')
    if 'AllenBradleyLogix5000' not in fio_text:
        errors.append('FACTORYIO missing AllenBradleyLogix5000 driver')
    if 'OrbitCamera' not in fio_text:
        errors.append('FACTORYIO missing OrbitCamera section')

    m = re.search(r'BitInputCount="(\d+)" BitOutputCount="(\d+)"', fio_text)
    if m:
        declared_in, declared_out = int(m.group(1)), int(m.group(2))
        actual_in = len(re.findall(r'<BitInput\d+', fio_text))
        actual_out = len(re.findall(r'<BitOutput\d+', fio_text))
        if declared_in != actual_in or declared_out != actual_out:
            errors.append(
                f'FIO driver count mismatch: declared in/out={declared_in}/{declared_out} '
                f'but bound={actual_in}/{actual_out}'
            )

    tags_l5x = out / f'{system}_Tags.L5X'
    if tags_l5x.is_file():
        tags_text = tags_l5x.read_text(encoding='utf-8')
        if 'Tags Use="Target"' not in tags_text:
            errors.append('Tags L5X must use Tags Use="Target" for Studio import')
    studio_tag_dir = out / 'studio_import' / '01_import_tags_here'
    studio_csv = list(studio_tag_dir.glob('*_Controller_Tags.csv')) if studio_tag_dir.is_dir() else []
    if not studio_csv:
        errors.append('studio_import controller tags CSV missing')
    else:
        csv_lines = studio_csv[0].read_text(encoding='utf-8').replace('\r\n', '\n').split('\n')
        if len(csv_lines) < 2 or csv_lines[1].strip() != '0.3':
            errors.append('Controller tags CSV line 2 must be 0.3 for Studio import')
        elif 'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES' not in studio_csv[0].read_text(encoding='utf-8'):
            errors.append('Controller tags CSV missing Studio import header')
    studio_prog_dir = out / 'studio_import' / '02_import_programs_here'
    if not studio_prog_dir.is_dir() or not list(studio_prog_dir.glob('*.L5X')):
        errors.append('studio_import program bundle missing')

    return errors


def export_run(
    run_dir: Path,
    out_dir: Path | None = None,
    *,
    include_spares: bool = False,
    max_fio_objects: int | None = None,
    controller_context: str = DEFAULT_CONTROLLER_CONTEXT,
    target_program: str = DEFAULT_TARGET_PROGRAM,
) -> dict:
    meta = read_project_meta(run_dir)
    points = extract_io_points(run_dir, include_spares=include_spares)
    beacons = extract_beacon_outputs(run_dir)
    if not points:
        raise ValueError('No I/O points extracted from Conveyor.asc')

    motor_chains = extract_motor_chains(run_dir)
    scaffold = build_scaffold(meta, points, beacons)
    scaffold['motor_chains'] = motor_chains
    system = scaffold['system']
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    # Prefer tar.gz basename for folder/file stems (raw-test rule)
    try:
        from fortna_source_id import export_label_from_meta
        export_label = export_label_from_meta()
    except Exception:
        export_label = ''
    folder = export_label if export_label else f'{stamp}-{system}'
    file_stem = export_label if export_label else system
    out = out_dir or (REPO_ROOT / 'exports' / 'plc' / folder)
    out.mkdir(parents=True, exist_ok=True)

    manifest_path = out / 'fortna_io_manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as fh:
        json.dump(scaffold, fh, indent=2, default=str)

    write_tags_csv(scaffold['tags'], out / 'fortna_tags.csv')
    write_tag_map_csv(scaffold['tags'], out / 'fortna_tag_map.csv')
    write_factory_io_bindings(scaffold['tags'], out / 'factory_io_bindings.csv')
    controller_tags_csv = out / f'{file_stem}_Controller_Tags.csv'
    tag_csv_count = write_studio_tags_csv(
        scaffold['tags'], controller_tags_csv, controller_context=file_stem,
    )
    write_l5x_tags(
        scaffold, out / f'{file_stem}_Tags.L5X', controller_context=file_stem,
    )
    write_l5x_program(
        scaffold, out / f'{file_stem}_Program.L5X', controller_context=file_stem,
    )
    write_l5x(scaffold, out / f'{file_stem}.L5X')
    studio_bundle = write_studio_import_bundle(
        scaffold,
        out,
        controller_context=file_stem,
        target_program=target_program,
    )
    fio_objects = write_factory_io_scene(
        scaffold, out / f'{file_stem}.FACTORYIO', max_objects=max_fio_objects,
    )
    write_fio_driver_bindings(out / 'fio_driver_bindings.csv', fio_objects, scaffold['tags'])
    write_report(
        scaffold, out / 'export_report.txt', controller_context=file_stem,
    )

    validation_errors = _validate_export_dir(out, file_stem)
    if validation_errors:
        raise ValueError('Export validation failed: ' + '; '.join(validation_errors))

    prism_info: dict = {}
    try:
        from fortna_prism_ingest import after_export
        prism_info = after_export(export_dir=out, kind='plc', site=file_stem)
    except Exception as exc:
        prism_info = {'ok': False, 'error': str(exc)}

    result = {
        'ok': True,
        'system': system,
        'export_name': file_stem,
        'source_label': file_stem,
        'out_dir': str(out),
        'tag_count': len(scaffold['tags']),
        'tag_csv_count': tag_csv_count,
        'fio_object_count': len(fio_objects),
        'program_count': len(scaffold['programs']),
        'stats': scaffold['stats'],
        'validated': True,
        'controller_context': file_stem,
        'target_program': target_program,
        'studio_import': studio_bundle,
        'prism': prism_info,
        'files': {
            'l5x': str(out / f'{file_stem}.L5X'),
            'controller_tags_csv': str(controller_tags_csv),
            'l5x_tags': str(out / f'{file_stem}_Tags.L5X'),
            'l5x_program': str(out / f'{file_stem}_Program.L5X'),
            'studio_import_dir': studio_bundle['studio_import_dir'],
            'factoryio': str(out / f'{file_stem}.FACTORYIO'),
            'manifest': str(manifest_path),
            'tags_csv': str(out / 'fortna_tags.csv'),
            'tag_map_csv': str(out / 'fortna_tag_map.csv'),
            'bindings_csv': str(out / 'factory_io_bindings.csv'),
            'driver_bindings_csv': str(out / 'fio_driver_bindings.csv'),
            'report': str(out / 'export_report.txt'),
        },
    }
    return result


def maybe_prism_seed(out_dir: Path, enabled: bool) -> dict | None:
    if not enabled:
        return None
    from fortna_prism_seed import run_seed  # noqa: E402
    return run_seed(out_dir, None)


def cmd_import_export(archive: str, **kwargs) -> dict:
    prism_seed = kwargs.pop('prism_seed', False)
    meta = import_package(Path(archive))
    run_dir = Path(meta['run_dir'])
    result = export_run(run_dir, **kwargs)
    result['import_meta'] = meta
    seed = maybe_prism_seed(Path(result['out_dir']), prism_seed)
    if seed:
        result['prism_seed'] = seed
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='FortnaPlus — Fortna RUN to Logix L5X + Factory I/O')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_import = sub.add_parser('import', help='Import tar.gz and export PLC artifacts')
    p_import.add_argument('archive', help='Path to RUN .tar.gz')
    p_import.add_argument('--out-dir', default='')
    p_import.add_argument('--include-spares', action='store_true')
    p_import.add_argument(
        '--max-fio',
        type=int,
        default=0,
        help='Max Factory I/O scene objects (0 = complete/all I/O points)',
    )
    p_import.add_argument('--controller-context', default=DEFAULT_CONTROLLER_CONTEXT)
    p_import.add_argument('--target-program', default=DEFAULT_TARGET_PROGRAM)
    p_import.add_argument(
        '--prism-seed',
        action='store_true',
        help='After export, seed ladder routines from PRISM L5X references (PoC)',
    )

    p_export = sub.add_parser('export', help='Export from existing RUN directory')
    p_export.add_argument('--archive', default='')
    p_export.add_argument('--run-dir', default='')
    p_export.add_argument('--use-active', action='store_true')
    p_export.add_argument('--out-dir', default='')
    p_export.add_argument('--include-spares', action='store_true')
    p_export.add_argument(
        '--max-fio',
        type=int,
        default=0,
        help='Max Factory I/O scene objects (0 = complete/all I/O points)',
    )
    p_export.add_argument('--controller-context', default=DEFAULT_CONTROLLER_CONTEXT)
    p_export.add_argument('--target-program', default=DEFAULT_TARGET_PROGRAM)
    p_export.add_argument('--prism-seed', action='store_true')

    p_ignition = sub.add_parser('ignition', help='Extract Ignition .gwbk gateway backup for Prism')
    p_ignition.add_argument('gwbk', help='Path to .gwbk file')
    p_ignition.add_argument('--out-dir', default='')
    p_ignition.add_argument(
        '--fortna-manifest',
        default='',
        help='Optional fortna_io_manifest.json for HMI-to-PLC cross-reference',
    )

    args = parser.parse_args()
    out_dir = Path(args.out_dir) if getattr(args, 'out_dir', '') else None

    try:
        if args.cmd == 'ignition':
            result = extract_gwbk(
                Path(args.gwbk),
                out_dir=out_dir,
                fortna_manifest_path=Path(args.fortna_manifest) if args.fortna_manifest else None,
            )
        else:
            export_kwargs = dict(
                out_dir=out_dir,
                include_spares=args.include_spares,
                max_fio_objects=None if args.max_fio <= 0 else args.max_fio,
                controller_context=args.controller_context,
                target_program=args.target_program,
                prism_seed=getattr(args, 'prism_seed', False),
            )
            if args.cmd == 'import':
                result = cmd_import_export(args.archive, **export_kwargs)
            else:
                run_dir = resolve_run_dir(
                    archive=getattr(args, 'archive', ''),
                    run_dir=getattr(args, 'run_dir', ''),
                    use_active=args.use_active,
                )
                prism_seed = export_kwargs.pop('prism_seed', False)
                result = export_run(run_dir, **export_kwargs)
                seed = maybe_prism_seed(Path(result['out_dir']), prism_seed)
                if seed:
                    result['prism_seed'] = seed
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())