#!/usr/bin/env python3
"""I/O bank inventory + optional print PDF OCR crosswalk for FortnaPlus recontrol."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from fortna_asc import read_asc  # noqa: E402
from fortna_io_extract import (  # noqa: E402
    extract_io_points,
    parse_drawing_page,
    read_project_meta,
)

PRINTS_DIR = REPO_ROOT / 'workspace' / 'prints'
SKIP_NAME_VALUES = frozenset({'', 'INVALID', 'N/A', 'SPARE', 'NEVERON', 'ALWAYSON', 'N/A~', 'NONE', '~'})

# OCR progress (Electron parses FORTNA_PROGRESS lines on stderr)
_progress_lock = threading.Lock()
_progress_state: dict = {
    'phase': 'idle',
    'file': '',
    'panel': '',
    'file_index': 0,
    'file_total': 0,
    'page': 0,
    'pages_in_file': 0,
    'pages_done': 0,
    'pages_total': 0,
    'pct': 0,
    'message': '',
    'workers': 1,
}


def _progress_path() -> Path | None:
    raw = (os.environ.get('FORTNA_OCR_PROGRESS') or '').strip()
    return Path(raw) if raw else None


def emit_progress(**kwargs) -> None:
    """Publish OCR progress for the dashboard (stderr JSON + optional progress file)."""
    with _progress_lock:
        _progress_state.update(kwargs)
        _progress_state['ts'] = time.time()
        pages_total = int(_progress_state.get('pages_total') or 0)
        pages_done = int(_progress_state.get('pages_done') or 0)
        if pages_total > 0:
            _progress_state['pct'] = round(100.0 * min(pages_done, pages_total) / pages_total, 1)
        payload = dict(_progress_state)
    line = 'FORTNA_PROGRESS ' + json.dumps(payload, separators=(',', ':'))
    print(line, file=sys.stderr, flush=True)
    p = _progress_path()
    if p:
        try:
            p.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
        except Exception:
            pass


def _ocr_worker_count() -> int:
    """Use multiple Tesseract processes — machine has headroom (was single-threaded)."""
    env = (os.environ.get('FORTNA_OCR_WORKERS') or '').strip()
    if env.isdigit() and int(env) >= 1:
        return max(1, min(12, int(env)))
    cpus = os.cpu_count() or 4
    # Leave 1–2 cores free; cap so we don't thrash RAM on large page images
    return max(2, min(8, cpus - 1))


def resolve_run_dir(run_dir: str = '', use_active: bool = True) -> Path | None:
    if run_dir:
        p = Path(run_dir)
        if (p / 'project.cfg').is_file():
            return p
        if (p / 'RUN' / 'project.cfg').is_file():
            return p / 'RUN'
        return None
    if use_active:
        for cand in (
            REPO_ROOT / 'workspace' / 'active' / 'RUN',
            REPO_ROOT / 'workspace' / 'active_work' / 'RUN',
        ):
            if (cand / 'project.cfg').is_file():
                return cand
    return None


def extract_configio_banks(run_dir: Path) -> list[dict]:
    """Parse Configio.asc (+ machine override if present) into bank rows."""
    meta = read_project_meta(run_dir)
    machine = (meta.get('machine_name') or '').strip()
    fortna = run_dir / 'FORTNA'
    candidates = []
    if machine:
        candidates.append(fortna / f'Configio.asc.{machine}')
        candidates.append(fortna / f'Configio.asc.{machine.upper()}')
    candidates.extend([fortna / 'Configio.asc', fortna / 'ConfigIO.asc'])

    path = next((p for p in candidates if p.is_file()), None)
    if not path:
        return []

    _, rows = read_asc(path)
    banks: list[dict] = []
    for i, row in enumerate(rows):
        bank = (row.get('Bank') or row.get('bank') or '').strip()
        word = (row.get('Octal_Word') or row.get('Octal_word') or row.get('Word') or '').strip()
        lohi = (row.get('LoHi') or '').strip()
        in_out = (row.get('In_Out') or '').strip()
        io_type = (row.get('I_O_Type') or row.get('IO_Type') or '').strip()
        interface = (row.get('Interface') or '').strip()
        status = (row.get('Status') or '').strip()
        desc = (row.get('Desc') or row.get('Description') or '').strip()
        # Skip completely empty padding rows
        if not any([bank, word, desc, interface]) and not any(c == '1' for c in in_out):
            # still count if bank/word numeric zero with type
            if not io_type or io_type.upper() in ('', 'N/A'):
                continue
        banks.append({
            'row': i + 1,
            'bank': bank,
            'octal_word': word,
            'lo_hi': lohi,
            'in_out_mask': in_out,
            'io_type': io_type,
            'interface': interface,
            'status': status,
            'description': desc[:120],
            'source': path.name,
        })
    return banks


# Columns that are pure GUI chrome — omit from "dynamic" program parameter lists
_DRIVE_SKIP_COLS = frozenset({
    'c', 'b', 'Good_color', 'Bad_color', 'Font', 'Underline', 'Gen_Flag',
    'Bitstate', 'Was_Bitstate', 'Drawstate', 'Was_Drawstate', 'Default Colors',
    'Logic_Help_Num', 'Gen_Security', 'Disable I/O', 'Overide I/O',
})
_EMPTY_DRIVE_VALS = frozenset({
    '', '0', '0.0', '0.000', 'N/A', 'INVALID', 'N', 'Y', ' ', '~', 'NONE', 'char8',
})


def _row_dynamic_params(row: dict[str, str]) -> dict[str, str]:
    """Every non-empty, non-chrome ASC column → dynamic parameter map."""
    params: dict[str, str] = {}
    for k, v in row.items():
        if not k or k in _DRIVE_SKIP_COLS:
            continue
        val = (v or '').strip()
        if not val or val in _EMPTY_DRIVE_VALS:
            continue
        if val.startswith('0000000000'):
            continue
        params[k] = val
    return params


def _base_equip_name(name: str) -> str:
    """VFD500A_EN / VFD500A_AUX → VFD500A for matching prints."""
    n = (name or '').strip()
    n = re.sub(r'(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$', '', n, flags=re.I)
    return n


def _vfd_number_token(name: str) -> str:
    """VFD444_AUX / VFD500A_EN → '444' / '500A' (digits + optional letter suffix)."""
    n = _base_equip_name(name).upper()
    m = re.match(r'^VFD([0-9]{2,4}[A-Z]?)$', n)
    return m.group(1) if m else ''


def _conveyor_page_map(rows: list[dict]) -> dict[str, int]:
    """P444 / P500A → Electrical Drawing Page No. from Conveyor.asc."""
    out: dict[str, int] = {}
    for row in rows:
        name = (row.get('IO_Name') or '').strip().upper()
        if not re.match(r'^P\d', name):
            continue
        page = parse_drawing_page(row)
        if page:
            out[name] = page
            # Also index bare number token P444 → 444 key for VFD444 lookup
            m = re.match(r'^P([0-9]{2,4}[A-Z]?)$', name)
            if m:
                out[f'#{m.group(1)}'] = page
    return out


def inherit_drawing_pages_for_vfd_io(
    items: list[dict],
    *,
    name_key: str = 'name',
    page_keys: tuple[str, ...] = ('drawing_page', 'print_page'),
    conveyor_pages: dict[str, int] | None = None,
) -> int:
    """
    VFD###_AUX / _EN / _FLT almost always have Electrical Drawing Page = 0 in ASC.
    The parent conveyor P### (and the VFD name on the print) carries the real sheet.

    Inherit:
      VFD444_AUX → page from P444 (or any VFD444* that already has a page)
      VFD500A_EN → page from P500A / P500

    Returns how many items received a page.
    """
    # Index pages already known on items
    by_base: dict[str, int] = {}
    by_num: dict[str, int] = {}
    for it in items:
        name = (it.get(name_key) or it.get('fortna_name') or it.get('io_name') or '').strip()
        if not name:
            continue
        page = None
        for k in page_keys:
            v = it.get(k)
            if v not in (None, '', 0, '0'):
                try:
                    page = int(v)
                    break
                except (TypeError, ValueError):
                    pass
        if not page:
            continue
        base = _base_equip_name(name).upper()
        if base.startswith('VFD'):
            by_base[base] = page
        num = _vfd_number_token(name)
        if num:
            by_num[num] = page
        if re.match(r'^P\d', name.upper()):
            by_num[re.sub(r'^P', '', name.upper())] = page

    if conveyor_pages:
        for k, v in conveyor_pages.items():
            if k.startswith('#'):
                by_num[k[1:]] = v
            elif k.startswith('P'):
                by_num[k[1:]] = v

    filled = 0
    for it in items:
        name = (it.get(name_key) or it.get('fortna_name') or it.get('io_name') or '').strip()
        if not name or not re.match(r'^VFD\d', name, re.I):
            continue
        cur = it.get(page_keys[0]) if page_keys else None
        if cur not in (None, '', 0, '0'):
            continue
        base = _base_equip_name(name).upper()
        num = _vfd_number_token(name)
        page = by_base.get(base)
        if not page and num:
            # Prefer exact P500A then P500
            page = by_num.get(num)
            if not page:
                # strip trailing letter: 500A → try 500
                m = re.match(r'^(\d+)', num)
                if m:
                    page = by_num.get(m.group(1))
        if not page and conveyor_pages:
            page = conveyor_pages.get(f'P{num}') or (
                conveyor_pages.get(f'P{re.match(r"^(\d+)", num).group(1)}')
                if num and re.match(r'^(\d+)', num) else None
            )
            if not page and num:
                page = conveyor_pages.get(f'#{num}') or conveyor_pages.get(
                    f'#{re.match(r"^(\d+)", num).group(1)}' if re.match(r'^(\d+)', num) else ''
                )
        if not page:
            continue
        for k in page_keys:
            it[k] = page
        filled += 1
    return filled


def extract_drive_parameters(run_dir: Path) -> dict:
    """Drive rows from Conveyor.asc with full dynamic parameter maps + motor chains.

    Scoped to this master PLC when Machine_Name / EIP word map allow.
    """
    from fortna_io_extract import (  # local import — avoid cycles at module load
        belongs_to_controller,
        equipment_kind,
        read_project_meta,
    )

    conv = run_dir / 'FORTNA' / 'Conveyor.asc'
    drives: list[dict] = []
    # Controller scope
    controller = ''
    word_map: dict = {}
    try:
        meta = read_project_meta(run_dir)
        controller = (meta.get('machine_name') or '').strip()
        if controller:
            from fortna_autogen import load_eip_topology
            word_map = dict((load_eip_topology(run_dir) or {}).get('word_map') or {})
    except Exception:
        controller = ''
        word_map = {}

    if conv.is_file():
        _, rows = read_asc(conv)
        for row in rows:
            name = (row.get('IO_Name') or '').strip()
            if name.upper() in SKIP_NAME_VALUES:
                continue
            device_type = (row.get('Type') or '').strip()
            if device_type.upper() in ('INVALID', 'IMAGE'):
                continue
            drive = (row.get('Drive') or '').strip()
            speed = (row.get('Speed') or '').strip()
            motor = (row.get('Motor') or '').strip()
            belt = (row.get('Belt_Info') or '').strip()
            in_chain = (row.get('In Motor Chain') or row.get('In_Motor_Chain') or '').strip()
            word = (row.get('IO_Address_Word') or '').strip()
            bit = (row.get('IO_Address_Bit') or '').strip()
            desc = (row.get('General_Description') or row.get('Device_Description') or '')[:120]
            # Scope to this master PLC — skip devices on other CPs
            if controller:
                if not belongs_to_controller(
                    machine_name=(row.get('Machine_Name') or '').strip(),
                    io_word=word,
                    controller=controller,
                    word_map=word_map,
                ):
                    continue
            kind = equipment_kind(name, device_type, desc, drive=drive)
            is_drive_row = bool(drive) or bool(speed and speed not in ('0', '0.0', '')) or (
                motor and motor.upper() not in ('N/A', '', 'INVALID')
            ) or device_type.upper() in (
                'STRAIGHT', 'BELT', 'CURVE', 'MERGE', 'SKEW', 'ACCUM', 'SPUR', 'TRIANG', 'MOTOR'
            ) or kind in ('vfd', 'motor', 'conveyor', 'power_supply')
            if not is_drive_row and not name.upper().startswith(('P', 'M', 'CV', 'VFD', 'EZPWS')):
                continue

            dyn = _row_dynamic_params(row)
            is_vfd = kind == 'vfd'
            # Drawing page from ASC — for VFDs leave blank until PDF OCR.
            # ASC "Electrical Drawing Page" is often a conveyor layout page, not the
            # VFD wiring sheet (user saw pages populate before OCR finished).
            drawing_page = parse_drawing_page(row)
            if is_vfd or re.match(r'^VFD\d', name, re.I):
                drawing_page = None
            drives.append({
                'name': name,
                'base_name': _base_equip_name(name),
                'drive': drive,
                'speed': speed,
                'motor': motor if motor.upper() not in ('N/A',) else '',
                'in_motor_chain': in_chain,
                'belt_info': belt if belt.upper() not in ('N/A',) else '',
                'device_type': device_type,
                'equipment_kind': kind,
                'is_vfd': is_vfd,
                'vfd_from_print': False,
                'description': desc,
                'part_number': (row.get('Part_Number') or '').strip(),
                'io_word': word,
                'io_bit': bit,
                'io_address': f'Bank{word}.{bit}' if word or bit else '',
                # Full dynamic map — every populated ASC field for this device
                'program_params': dyn,
                'param_count': len(dyn),
                # Convenience geometry (also inside program_params)
                'x': (row.get('X_cord') or row.get('X_COORD') or '').strip(),
                'y': (row.get('Y_cord') or row.get('Y_COORD') or '').strip(),
                'width': (row.get('Width') or '').strip(),
                'length': (row.get('Length') or '').strip(),
                'angle': (row.get('Angle') or '').strip(),
                'belt_width': (row.get('Belt_Width') or '').strip(),
                'infeed_elevation': (row.get('Infeed_Elevation') or '').strip(),
                'discharge_elevation': (row.get('Discharge_Elevation') or '').strip(),
                'roller_centers': (row.get('Roller_Centers') or '').strip(),
                'nose_over': (row.get('NoseOver') or '').strip(),
                'machine_name': (row.get('Machine_Name') or '').strip(),
                # Print repository link (OCR fills VFD pages; ASC page for other devices)
                'drawing_page': drawing_page,
                'print_file': '',
                'print_page': drawing_page,
                'print_panel': '',
                # Filled later from print OCR when available
                'print_params': {},
                'print_param_count': 0,
                'print_param_list': [],
                'print_sources': [],
            })

    # Motor startup chains — dynamic params from each chain row
    chains: list[dict] = []
    mtr = run_dir / 'FORTNA' / 'Mtrchain.asc'
    if mtr.is_file():
        _, rows = read_asc(mtr)
        for row in rows:
            motor_name = (row.get('Motor_Name') or '').strip()
            if not motor_name or motor_name.upper() in SKIP_NAME_VALUES:
                continue
            chained = []
            for i in range(1, 11):
                c = (row.get(f'Motor_Chained{i}') or '').strip()
                if c and c.upper() not in SKIP_NAME_VALUES:
                    chained.append(c)
            dyn = _row_dynamic_params(row)
            chains.append({
                'motor_name': motor_name,
                'motor_ndx': (row.get('Motor_Ndx') or '').strip(),
                'timer_name': (row.get('Timer_Name') or '').strip(),
                'timer_preset': (row.get('Timer_Preset') or '').strip(),
                'run_timer': (row.get('RUN Timer_Name') or '').strip(),
                'enabled': (row.get('Enabled') or '').strip(),
                'stop_zone': (row.get('Stop Zone') or row.get('StopZone') or '').strip(),
                'horn': (row.get('Horn') or '').strip(),
                'chained_motors': chained,
                'chain_count': len(chained),
                'program_params': dyn,
                'param_count': len(dyn),
            })

    drive_ids: dict[str, int] = defaultdict(int)
    for d in drives:
        key = d['drive'] or '(blank)'
        drive_ids[key] += 1

    # VFD I/O bits have ASC drawing page 0. Do NOT copy parent conveyor pages
    # (those are layout sheets, not VFD param sheets). Print # is set only after
    # PDF OCR finds VFD444 / VFD500 etc. on a real electrical page.

    return {
        'drives': drives,
        'drive_count': len(drives),
        'drive_id_summary': [
            {'drive_id': k, 'count': v}
            for k, v in sorted(drive_ids.items(), key=lambda x: (x[0] == '(blank)', x[0]))
        ],
        'motor_chains': chains,
        'motor_chain_count': len(chains),
    }


# VFD / drive print OCR — PowerFlex tables + generic patterns
# Prints look like:
#   Par | Parameter Name      | Programmed Value
#   31  | Motor NP Volts      | 460 VAC
#   33  | Motor OL Current    | 3.1 Amps
#   70  | Preset Freq 0       | 50.0 Hz
_VFD_PARAM_PATTERNS = [
    (re.compile(
        r'\bP\s*0*(\d{1,4})\s*[=:]\s*([-+]?\d+(?:\.\d+)?)\s*(Hz|HZ|RPM|A|V|VAC|Amps?|s|Sec(?:s)?|sec|%|kW|HP)?',
        re.I), 'P{num}'),
    (re.compile(
        r'\b(?:Param(?:eter)?|PR)\s*0*(\d{1,4})\s*[=:]\s*([-+]?\d+(?:\.\d+)?)\s*(Hz|HZ|RPM|A|V|VAC|Amps?|s|Sec(?:s)?|sec|%|kW|HP)?',
        re.I), 'Param{num}'),
    (re.compile(
        r'\b(Max(?:imum)?\s*Freq(?:uency)?|Min(?:imum)?\s*Freq(?:uency)?|'
        r'Accel(?:eration)?(?:\s*Time)?(?:\s*\d+)?|Decel(?:eration)?(?:\s*Time)?(?:\s*\d+)?|'
        r'Motor\s*(?:FLA|Amps|Current|HP|Voltage|NP\s*Volts?|OL\s*Current)|'
        r'Preset\s*Freq(?:uency)?(?:\s*\d+)?|Speed\s*Reference|Start\s*Source|Relay\s*Out\s*Sel)\s*[=:]?\s*'
        r'([-+]?\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9\-/]*)\s*'
        r'(Hz|HZ|RPM|A|V|VAC|Amps?|s|Sec(?:s)?|sec|%|kW|HP|wire)?',
        re.I), 'named'),
]

# PowerFlex table rows (PF4 / PF70 / PF525) after OCR / Y-sorted rebuild:
#   "31 Motor NP Volts 460 VAC"
#   "P031 MOTOR NP VOLTS 460 VAC"   ← Fortna title-block style (Image red-box)
#   "T062 DIGIN TERMBLK 2 (48) 2-WIRE FWD"
#   "A544 REVERSE DISABLE (1) REV DISABLED"
_PF_PARAM_NAMES = (
    r'Motor\s+NP\s+Volts?|Motor\s+OL\s+Current|Motor\s+NP\s+(?:Hertz|FLA|RPM|Power)|'
    r'Mtr\s+NP\s+Pwr\s+Units|Motor\s+NP\s+Pwr\s+Units|'
    r'Speed\s+Reference\s*\d*|Speed\s+Ref\s+A\s+Sel|Start\s+Source\s*\d*|'
    r'Maximum\s+(?:Freq(?:uency)?|Speed)|Compensation|Stop\s+Mode|'
    r'Accel(?:eration)?\s*Time\s*\d*|Decel(?:eration)?\s*Time\s*\d*|'
    r'Relay\s+Out\s*\d*\s*Sel|Preset\s+(?:Freq(?:uency)?|Speed)\s*\.?\s*\d*|'
    r'Digital\s+(?:In|Out)\d*\s+Sel|Dig\s+Out\d*\s+Level|'
    r'Digin\s+Termblk\s*\d*|Dig\s*In\s*Termblk\s*\d*|'
    r'DB\s+Resistor\s+(?:Type|Sel)|DC\s+Brake\s+(?:Time|Level)|'
    r'Reverse\s+Disable|Bus\s+Reg\s+Mode\s*A?|Param\s+Access\s+Lvl|Language'
)
_PF_LINE = re.compile(
    r'\b(\d{1,3})\s+'
    rf'({_PF_PARAM_NAMES})\s+'
    r'([-+]?\d+(?:\.\d+)?\s*(?:VAC|V|A|Amps?|Hz|HZ|Sec(?:s)?|s|RPM|HP|%)?|'
    r'Preset\s*(?:Freq(?:uency)?|Spd)\s*\d*|2[\-\s]?wire|At\s*Freq|Coast|Ramp|'
    r'Both\s*DB[^|\n]{0,16}|Internal|Not\s*Used|English|Advance|Horsepower|Run|'
    r'[A-Za-z][A-Za-z0-9\-/ ]{0,28})',
    re.I,
)
# Fortna electrical sheet: "P031 MOTOR NP VOLTS 460 VAC" / "A544 REVERSE DISABLE …"
_PF_CODED_LINE = re.compile(
    r'\b([PTA])0*(\d{1,3})\s+'
    rf'({_PF_PARAM_NAMES})\s+'
    r'(?:\(\s*\d+\s*\)\s*)?'
    r'([-+]?\d+(?:\.\d+)?\s*(?:VAC|V|A|Amps?|Hz|HZ|Sec(?:s)?|s|RPM|HP|%)?|'
    r'2[\-\s]?WIRE[^\n]{0,20}|AT\s*FREQUENCY|RAMP[^\n]{0,12}|'
    r'REV\s*DISABLED?|DIGIN[^\n]{0,16}|'
    r'[A-Za-z(][A-Za-z0-9\-/()% .]{1,36})',
    re.I,
)
# Catalog line under VFD title: (25B-D4P0N104/25-JBAA)
_VFD_CATALOG_RE = re.compile(
    r'\(\s*(25[A-Z]?-[A-Z0-9]+(?:/[A-Z0-9\-]+)?)\s*\)',
    re.I,
)

# Known PowerFlex name → typical Par # (PF4 defaults; PF70 may reuse names with other #s)
_PF_NAME_TO_PAR = {
    'motor np volts': 31,
    'motor ol current': 33,
    'start source': 36,
    'speed reference': 38,
    'accel time 1': 39,
    'decel time 1': 40,
    'relay out sel': 55,
    'preset freq 0': 70,
    'maximum speed': 82,
    'maximum freq': 55,
    'motor np hertz': 32,
    'motor np fla': 34,
    'motor np power': 35,
    'motor np rpm': 37,
    'dc brake time': 53,
    'dc brake level': 158,
    'db resistor type': 163,
    'mtr np pwr units': 46,
    'motor np pwr units': 46,
    'compensation': 56,
    'speed ref a sel': 90,
    'preset speed 7': 107,
    'bus reg mode a': 161,
    'param access lvl': 196,
    'language': 201,
    'digital in1 sel': 361,
    'digital in2 sel': 362,
    'digital in3 sel': 363,
    'digital out2 sel': 384,
    'dig out2 level': 385,
}

# Allowed Par numbers when the name looks like a real PowerFlex table row.
# Covers PF4 (~8 params) and PF70 (longer programmed list like VFD444).
# Not every integer 1–399 — only known Fortna sheet ranges.
_PF_CANONICAL_PARS = {
    # PowerFlex 4 / 40 / 525 common (P031 family on Fortna sheets)
    31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 53, 55, 62, 70, 76, 80, 82,
    # PowerFlex 70 motor / limits (VFD444 sheet)
    43, 56, 90, 91, 92, 101, 102, 103, 104, 105, 106, 107,
    140, 141, 142, 143, 158, 159, 160, 161, 163, 196, 201,
    361, 362, 363, 364, 365, 380, 381, 382, 383, 384, 385,
    # PF525 A-params seen on Fortna VFD sheets (A410 preset, A434 brake, A544 reverse)
    410, 434, 435, 437, 544,
}

# Hard cap so a bad OCR page never dumps 100+ junk rows again
_PF_MAX_PARAMS_PER_DRIVE = 32

_PF_CANONICAL_NAME_RE = re.compile(
    r'^(?:[PTA]0*\d+\s+)?'
    r'(?:Motor\s+NP\s+(?:Volts?|Hertz|FLA|RPM|Power)|'
    r'Mtr\s+NP\s+Pwr\s+Units|Motor\s+NP\s+Pwr\s+Units|'
    r'Motor\s+OL\s+Current|Stop\s+Mode|'
    r'Start\s+Source\s*\d*|Speed\s+Reference\s*\d*|Speed\s+Ref\s+A\s+Sel|'
    r'Accel(?:eration)?\s*Time\s*\d*|Decel(?:eration)?\s*Time\s*\d*|'
    r'Relay\s+Out\s*\d*\s*Sel|Preset\s+(?:Freq(?:uency)?|Speed)\s*\.?\s*\d*|'
    r'Maximum\s+(?:Freq(?:uency)?|Speed)|Compensation|'
    r'DC\s+Brake\s+(?:Time|Level)|DB\s+Resistor\s+(?:Type|Sel)|Reverse\s+Disable|'
    r'Digin\s+Termblk\s*\d*|Dig\s*In\s*Termblk\s*\d*|'
    r'Bus\s+Reg\s+Mode\s*A?|Param\s+Access\s+Lvl|Language|'
    r'Digital\s+(?:In|Out)\d*\s+Sel|Dig\s+Out\d*\s+Level)$',
    re.I,
)


def _par_number_from_param(param: str) -> int | None:
    """Extract PowerFlex Par # from 'P031 Motor NP Volts', 'A544 …', or '31'."""
    s = (param or '').strip()
    m = re.match(r'^[PTA]\s*0*(\d{1,3})\b', s, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r'^0*(\d{1,3})\s+', s)
    if m:
        return int(m.group(1))
    key = re.sub(r'^[PTA]0*\d+\s+', '', s, flags=re.I).strip().lower()
    key = re.sub(r'\s+', ' ', key)
    if key in _PF_NAME_TO_PAR:
        return _PF_NAME_TO_PAR[key]
    return None


def is_canonical_vfd_param(param: str) -> bool:
    """True only for real PowerFlex program-table params (not ASC geometry / noise)."""
    s = (param or '').strip()
    if not s or s == 'Device_ID' or s.startswith('Device_ID:'):
        return False
    # Drop free-text ASC-ish keys that sometimes leak in
    if s.lower() in (
        'type', 'length', 'width', 'motor fla', 'motor np fla',
        'general_description', 'machine_name', 'procnum',
    ):
        # allow Motor NP FLA via par map only (P034)
        if s.lower() == 'motor np fla':
            return True
        if s.lower() in ('type', 'length', 'width', 'general_description', 'machine_name', 'procnum'):
            return False
    par = _par_number_from_param(s)
    if par is not None:
        return par in _PF_CANONICAL_PARS
    # Name-only match (no par #)
    name = re.sub(r'^P0*\d+\s+', '', s, flags=re.I).strip()
    if _PF_CANONICAL_NAME_RE.match(name):
        return True
    return False


def filter_canonical_vfd_params(params: list[dict]) -> list[dict]:
    """
    Keep one clean entry per PowerFlex Par # (prefer 'P031 Motor NP Volts' form).

    Dynamic: PF4 sheets ~8 rows, PF70 sheets ~20+ (e.g. VFD444). Hard cap avoids floods.
    Prefer explicit table Par # over name→PF4 defaults when both appear.
    """
    # Bare names that already have an explicit P### from the table
    explicit_bare: set[str] = set()
    for p in params or []:
        if not isinstance(p, dict):
            continue
        param = str(p.get('param') or '')
        if re.match(r'^P\s*0*\d{1,3}\b', param, re.I):
            bare = re.sub(r'^P\s*0*\d{1,3}\s+', '', param, flags=re.I).strip().lower()
            bare = re.sub(r'\s+', ' ', bare)
            if bare:
                explicit_bare.add(bare)

    by_par: dict[int, dict] = {}
    extras: list[dict] = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        param = str(p.get('param') or '')
        if not is_canonical_vfd_param(param):
            continue
        has_explicit = bool(re.match(r'^P\s*0*\d{1,3}\b', param, re.I))
        par = _par_number_from_param(param)
        # Normalize display name
        name = re.sub(r'^P\s*0*(\d{1,3})\s+', '', param, flags=re.I).strip()
        if not name:
            name = param
        bare_key = re.sub(r'\s+', ' ', name.lower())
        # Skip name-only rows when the same parameter already has a real table Par #
        if not has_explicit and bare_key in explicit_bare:
            continue
        if par is not None:
            bare = re.sub(r'^P\s*0*\d{1,3}\s+', '', name, flags=re.I).strip() or name
            label = f'P{par:03d} {bare}'
            row = dict(p)
            row['param'] = label
            row['par_num'] = par
            row['_explicit'] = has_explicit
            prev = by_par.get(par)
            if not prev:
                by_par[par] = row
            else:
                # Prefer explicit P### rows over name-mapped defaults
                if has_explicit and not prev.get('_explicit'):
                    by_par[par] = row
                else:
                    score = len(str(row.get('display') or row.get('value') or '')) + len(label)
                    pscore = len(str(prev.get('display') or prev.get('value') or '')) + len(
                        str(prev.get('param') or '')
                    )
                    if score >= pscore:
                        by_par[par] = row
        else:
            extras.append(p)
    out = sorted(by_par.values(), key=lambda x: int(x.get('par_num') or 999))
    # Dedup extras by normalized name
    seen_names = {re.sub(r'\s+', ' ', str(x.get('param') or '')).lower() for x in out}
    for p in extras:
        key = re.sub(r'\s+', ' ', str(p.get('param') or '')).lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        out.append(p)
    # Dynamic length is fine (PF4≈8, PF70≈20+) but never flood the UI
    if len(out) > _PF_MAX_PARAMS_PER_DRIVE:
        out = out[:_PF_MAX_PARAMS_PER_DRIVE]
    return out

_VFD_ID_RE = re.compile(r'\bVFD[\s\-_]*([A-Z0-9]*\d[A-Z0-9\-]{0,6})\b', re.I)
# Title block: "VFD WIRING – (VFD312, VFD412)" — authoritative IDs for that sheet
_VFD_WIRING_TITLE_RE = re.compile(
    r'VFD\s*WIRING\s*[-–—:]*\s*\(([^)]{3,80})\)',
    re.I,
)
# Plausible drive tags only: VFD312, VFD500A, VFD501B1, VFD501B-1 → VFD501B1
# Reject OCR junk like VFD141711 / VFD12311 (5–6 digit noise).
# Number body is 2–4 digits; optional letter suffix + optional trailing digit.
_VFD_PLAUSIBLE_RE = re.compile(r'^VFD\d{2,4}(?:[A-Z]{1,2}\d?)?$', re.I)


def _normalize_vfd_id(raw: str) -> str:
    """VFD 500A / vfd-500a / VFD500A_EN / VFD501B-1 → VFD500A / VFD501B1. '' if junk."""
    s = re.sub(r'[\s\-]+', '', (raw or '').upper())
    s = re.sub(r'(_EN|_AUX|_FLT|_RUN|_OK|_CMD|_REF|_FB)$', '', s)
    if not s:
        return ''
    # Only accept real VFD tags — do not invent VFD + conveyor name
    if not s.startswith('VFD'):
        if re.fullmatch(r'[A-Z0-9]*\d[A-Z0-9]{0,6}', s) and re.search(r'\d', s):
            # bare "500A" / "836" from OCR after stripping VFD
            s = 'VFD' + s
        else:
            return ''
    if not re.search(r'\d', s):
        return ''
    if not re.fullmatch(r'VFD[A-Z0-9]{1,10}', s):
        return ''
    # Reject OCR noise (VFD141711, VFD12311) — real Fortna drives are 2–4 digit + optional letter
    if not _VFD_PLAUSIBLE_RE.fullmatch(s):
        return ''
    return s


def _vfd_ids_from_wiring_title(text: str) -> list[str]:
    """Parse VFD IDs from 'VFD WIRING – (VFD312, VFD412)' title-block lines."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _VFD_WIRING_TITLE_RE.finditer(text or ''):
        chunk = m.group(1) or ''
        for part in re.split(r'[,;/]|and', chunk, flags=re.I):
            vid = _normalize_vfd_id(part.strip())
            if vid and vid not in seen:
                seen.add(vid)
                out.append(vid)
        # Also catch bare VFD### tokens inside the parens
        for m2 in _VFD_ID_RE.finditer(chunk):
            vid = _normalize_vfd_id('VFD' + m2.group(1))
            if vid and vid not in seen:
                seen.add(vid)
                out.append(vid)
    return out


def _rebuild_text_from_words(page, y_tol: float = 4.0, x_min: float | None = None, x_max: float | None = None) -> str:
    """Rebuild page text in reading order using word positions.

    CAD electrical PDFs often emit columns out of order in get_text('text').
    Sorting by Y then X restores PowerFlex rows like:
      31 Motor NP Volts 460 VAC

    Optional x_min/x_max crops to one column (side-by-side VFD410 | VFD412).
    """
    try:
        words = page.get_text('words') or []
    except Exception:
        return ''
    if not words:
        return ''
    # words: x0, y0, x1, y1, word, block_no, line_no, word_no
    filtered = []
    for w in words:
        cx = (float(w[0]) + float(w[2])) / 2.0
        if x_min is not None and cx < x_min:
            continue
        if x_max is not None and cx > x_max:
            continue
        filtered.append(w)
    words = filtered
    if not words:
        return ''
    words = sorted(words, key=lambda w: (round(float(w[1]) / y_tol) * y_tol, float(w[0])))
    rows: list[str] = []
    cur_y: float | None = None
    cur: list = []
    for w in words:
        y = round(float(w[1]) / y_tol) * y_tol
        if cur_y is None:
            cur_y = y
        if abs(y - cur_y) > y_tol:
            rows.append(' '.join(str(t[4]) for t in cur))
            cur = [w]
            cur_y = y
        else:
            cur.append(w)
    if cur:
        rows.append(' '.join(str(t[4]) for t in cur))
    return '\n'.join(rows)


def _vfd_title_x_positions(page) -> list[tuple[str, float]]:
    """Find VFD### tokens and their X center on the page (for column split)."""
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    try:
        words = page.get_text('words') or []
    except Exception:
        return out
    # Reconstruct nearby tokens: sometimes "VFD" and "412" are separate words
    for i, w in enumerate(words):
        tok = str(w[4] or '')
        cx = (float(w[0]) + float(w[2])) / 2.0
        vid = ''
        m = _VFD_ID_RE.search(tok)
        if m:
            vid = _normalize_vfd_id('VFD' + m.group(1))
        elif re.fullmatch(r'VFD', tok, re.I) and i + 1 < len(words):
            nxt = str(words[i + 1][4] or '')
            if re.fullmatch(r'[A-Z0-9]*\d[A-Z0-9]{0,6}', nxt, re.I):
                vid = _normalize_vfd_id('VFD' + nxt)
                cx = (cx + (float(words[i + 1][0]) + float(words[i + 1][2])) / 2.0) / 2.0
        if vid and vid not in seen:
            seen.add(vid)
            out.append((vid, cx))
    out.sort(key=lambda t: t[1])
    return out


def extract_vfd_params_from_page_spatial(
    page,
    source_file: str = '',
    *,
    page_num: int | None = None,
    extra_ids: list[str] | None = None,
) -> list[dict]:
    """
    Extract params from a PDF page, splitting side-by-side VFD columns by X.

    Fixes VFD410 (left, PF70) + VFD412 (right, PF4) on the same drawing:
    full-page Y-then-X text interleaves the two tables; column crop does not.
    """
    titles = _vfd_title_x_positions(page)
    # Merge title-block OCR ids that lack coordinates — append with guessed X later
    known = {v for v, _ in titles}
    for raw in extra_ids or []:
        vid = _normalize_vfd_id(raw)
        if vid and vid not in known:
            titles.append((vid, -1.0))
            known.add(vid)
    titles = [(v, x) for v, x in titles if v]
    if len(titles) <= 1:
        # Single VFD or none — full page text path
        text = _rebuild_text_from_words(page)
        ids = [v for v, _ in titles] or list(extra_ids or [])
        return extract_vfd_params_from_text(
            text, source_file, device_ids=ids or None, page=page_num
        )

    # Place unknown-X ids at end; sort known by X
    placed = [(v, x) for v, x in titles if x >= 0]
    unplaced = [v for v, x in titles if x < 0]
    placed.sort(key=lambda t: t[1])
    if not placed:
        text = _rebuild_text_from_words(page)
        return extract_vfd_params_from_text(
            text, source_file, device_ids=[v for v, _ in titles], page=page_num
        )

    try:
        rect = page.rect
        page_w = float(rect.width)
    except Exception:
        page_w = 1000.0

    # Column boundaries midway between sorted VFD title X positions
    xs = [x for _, x in placed]
    bounds: list[tuple[str, float, float]] = []
    for i, (vid, x) in enumerate(placed):
        left = 0.0 if i == 0 else (xs[i - 1] + x) / 2.0
        right = page_w if i == len(placed) - 1 else (x + xs[i + 1]) / 2.0
        bounds.append((vid, left, right))

    all_params: list[dict] = []
    seen: set[str] = set()
    try:
        page_w = float(page.rect.width) or page_w
    except Exception:
        pass
    for vid, left, right in bounds:
        col_text = _rebuild_text_from_words(page, x_min=left, x_max=right)
        # Graphics tables: CAD words empty → OCR this column later if needed
        # (caller may also run full table OCR; stamp device_id here when we have text)
        if vid not in (col_text or '').upper():
            col_text = f'{vid}\n{col_text}'
        before = len(all_params)
        all_params.extend(
            _extract_params_in_segment(
                col_text,
                device_id=vid,
                source_file=source_file,
                page=page_num,
                seen=seen,
            )
        )
        # If column CAD text had no params, try Tesseract on that X band
        col_real = sum(
            1 for p in all_params[before:]
            if (p.get('param') or '') != 'Device_ID' and is_canonical_vfd_param(str(p.get('param') or ''))
        )
        if col_real < 3:
            try:
                import pytesseract
                from PIL import Image as _Image
                x0f = max(0.0, left / page_w - 0.02)
                x1f = min(1.0, right / page_w + 0.02)
                ocr_col = _ocr_page_region_text(
                    page, pytesseract, _Image,
                    y0_frac=0.12, y1_frac=0.92, x0_frac=x0f, x1_frac=x1f,
                )
                if ocr_col.strip():
                    if vid not in ocr_col.upper():
                        ocr_col = f'{vid}\n{ocr_col}'
                    all_params.extend(
                        _extract_params_in_segment(
                            ocr_col,
                            device_id=vid,
                            source_file=source_file,
                            page=page_num,
                            seen=seen,
                        )
                    )
            except Exception:
                pass
        # Device_ID inventory
        sk = f'ID|{vid}'
        if sk not in seen:
            seen.add(sk)
            all_params.append({
                'param': 'Device_ID',
                'value': vid,
                'unit': '',
                'display': vid,
                'source': Path(source_file).name if source_file else '',
                'raw': vid,
                'device_id': vid,
                **({'page': page_num} if page_num is not None else {}),
            })

    # Unplaced IDs: no free params (avoid cross-bleed); just register Device_ID
    for vid in unplaced:
        sk = f'ID|{vid}'
        if sk not in seen:
            seen.add(sk)
            all_params.append({
                'param': 'Device_ID',
                'value': vid,
                'unit': '',
                'display': vid,
                'source': Path(source_file).name if source_file else '',
                'raw': vid,
                'device_id': vid,
                **({'page': page_num} if page_num is not None else {}),
            })
    return all_params


def _page_has_powerflex_table(text: str) -> bool:
    t = (text or '').upper()
    return (
        ('MOTOR NP VOLTS' in t or 'MOTOR OL CURRENT' in t or 'PRESET FREQ' in t)
        and ('PARAMETER' in t or 'PROGRAMMED' in t or re.search(r'\bPAR\b', t) is not None)
    ) or bool(re.search(r'\b31\s+Motor\s+NP\s+Volts', text or '', re.I))


def _ocr_regions_for_vfd_ids(page, pytesseract, Image, mat_scale: float = 2.0) -> list[str]:
    """OCR the same visual landmarks a human uses on Fortna VFD sheets:

    Red-box landmarks (any one is enough to identify the drive):
      1) Title above the PowerFlex box:  VFD501B-2  +  (25B-D4P0N104/25-JBAA)
      2) Terminal block under POWERFLEX 525 / 70 header
      3) Param table: PAR # | PARAMETER NAME | PROGRAMMED VALUE  (P031…)
      4) Bottom drawing title: VFD WIRING – (VFD312, VFD412)

    Avoid full-height side strips (they invent junk like VFD141711 from page #s).
    """
    ids: list[str] = []
    seen: set[str] = set()

    def _harvest(text: str) -> None:
        if not text:
            return
        for vid in _vfd_ids_from_wiring_title(text):
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)
        for m in _VFD_ID_RE.finditer(text):
            vid = _normalize_vfd_id('VFD' + m.group(1))
            if vid and vid not in seen:
                seen.add(vid)
                ids.append(vid)
        # Catalog under title is a strong page marker (stored later via Device_ID)
        # — also try to recover VFD from nearby text when catalog is present
        if _VFD_CATALOG_RE.search(text) and not ids:
            for m in re.finditer(r'VFD\s*([0-9]{2,4}[A-Z]{0,2}(?:-\d+)?)', text, re.I):
                vid = _normalize_vfd_id('VFD' + m.group(1))
                if vid and vid not in seen:
                    seen.add(vid)
                    ids.append(vid)

    try:
        mat = __import__('fitz').Matrix(mat_scale, mat_scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
        w, h = img.size
        # Landmark crops matching the red boxes on typical Fortna sheets
        regions = [
            img.crop((0, int(h * 0.82), w, h)),                          # 4) bottom VFD WIRING title
            img.crop((int(w * 0.08), int(h * 0.06), int(w * 0.92), int(h * 0.28))),  # 1) VFD title + catalog
            img.crop((int(w * 0.08), int(h * 0.18), int(w * 0.92), int(h * 0.58))),  # 2) POWERFLEX terminal box
            img.crop((int(w * 0.08), int(h * 0.52), int(w * 0.92), int(h * 0.88))),  # 3) PAR # table
            img.crop((0, 0, w, max(40, int(h * 0.18)))),                 # top strip fallback
        ]
        for region in regions:
            try:
                text = pytesseract.image_to_string(region) or ''
            except Exception:
                continue
            _harvest(text)
    except Exception:
        pass
    return ids


def _split_text_by_vfd(text: str) -> list[tuple[str, str]]:
    """
    Split a multi-VFD sheet into (device_id, segment_text) chunks.

    Fortna drawings often put VFD410 (PF70) and VFD412 (PF4) on the same page.
    Params after a VFD title belong to that drive until the next VFD title.
    """
    text = text or ''
    hits: list[tuple[int, str]] = []
    for m in _VFD_ID_RE.finditer(text):
        vid = _normalize_vfd_id('VFD' + m.group(1))
        if not vid:
            continue
        # Prefer first occurrence of each ID as section start
        if any(v == vid for _, v in hits):
            continue
        hits.append((m.start(), vid))
    if not hits:
        return [('', text)]
    hits.sort(key=lambda x: x[0])
    segments: list[tuple[str, str]] = []
    # Preamble before first VFD — keep unassigned (rarely has tables)
    if hits[0][0] > 0:
        segments.append(('', text[: hits[0][0]]))
    for i, (start, vid) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        segments.append((vid, text[start:end]))
    return segments


def _extract_params_in_segment(
    text: str,
    *,
    device_id: str,
    source_file: str,
    page: int | None,
    seen: set[str],
) -> list[dict]:
    """Extract PowerFlex table params from one VFD section only."""
    found: list[dict] = []
    src_name = Path(source_file).name if source_file else ''
    text = text or ''

    def _add(param: str, val: str, unit: str = '', raw: str = '') -> None:
        param = re.sub(r'\s+', ' ', (param or '').strip())
        val = re.sub(r'\s+', ' ', (val or '').strip())
        unit = (unit or '').strip()
        if not param or not val:
            return
        if param.lower() in ('par', 'parameter name', 'programmed value', 'parameter'):
            return
        if val.lower() in ('parameter name', 'programmed value', 'par', 'name'):
            return
        if re.fullmatch(r'1[34]\d{4}', val):
            return
        if re.fullmatch(r'1[34]\d{4}', unit):
            unit = ''
        if param.lower() == 'start source' and re.fullmatch(r'\d+', val):
            if re.search(r'\b' + re.escape(val) + r'[\-\s]?wire\b', text, re.I):
                val = f'{val}-wire'
        display = f'{val} {unit}'.strip() if unit and unit.lower() not in val.lower() else val
        did = device_id or ''
        sk = f'{did}|{param}|{display}'.upper()
        if sk in seen:
            return
        seen.add(sk)
        row = {
            'param': param,
            'value': val,
            'unit': unit,
            'display': display,
            'source': src_name,
            'raw': (raw or f'{param}={display}')[:100],
        }
        if did:
            row['device_id'] = did
        if page is not None:
            row['page'] = page
        found.append(row)

    # Prefer Fortna coded table rows first: P031 / T062 / A544 …
    for m in _PF_CODED_LINE.finditer(text):
        prefix = (m.group(1) or 'P').upper()
        par_num = int(m.group(2))
        pname = re.sub(r'\s+', ' ', m.group(3).strip())
        pval = re.sub(r'\s+', ' ', m.group(4).strip())
        unit = ''
        um = re.search(r'\b(VAC|V|A|Amps?|Hz|HZ|Sec(?:s)?|s|RPM|HP|%)\s*$', pval, re.I)
        if um:
            unit = um.group(1)
            core = pval[: um.start()].strip()
            if core:
                pval = core
        _add(f'{prefix}{par_num:03d} {pname}', pval, unit, m.group(0))

    # Bare "31 Motor NP Volts 460 VAC" (CAD rebuild / PF4 style)
    for m in _PF_LINE.finditer(text):
        par_num = m.group(1)
        pname = re.sub(r'\s+', ' ', m.group(2).strip())
        pval = re.sub(r'\s+', ' ', m.group(3).strip())
        unit = ''
        um = re.search(r'\b(VAC|V|A|Amps?|Hz|HZ|Sec(?:s)?|s|RPM|HP|%)\s*$', pval, re.I)
        if um:
            unit = um.group(1)
            core = pval[: um.start()].strip()
            if core:
                pval = core
        _add(f'P{int(par_num):03d} {pname}', pval, unit, m.group(0))

    # Pipe / table OCR: "41 | Motor NP Volts | 460 VAC" (PF70 sheets, Tesseract)
    if len(found) < 4:
        for m in re.finditer(
            r'\b(\d{1,3})\s*[|]\s*'
            rf'({_PF_PARAM_NAMES})\s*[|]\s*'
            r'([^\n|]{1,40})',
            text,
            re.I,
        ):
            par_num = int(m.group(1))
            pname = re.sub(r'\s+', ' ', m.group(2).strip())
            pval = re.sub(r'\s+', ' ', m.group(3).strip())
            unit = ''
            um = re.search(
                r'\b(VAC|V|A|Amps?|Hz|HZ|Sec(?:s)?|s|RPM|HP|%)\s*$', pval, re.I
            )
            if um:
                unit = um.group(1)
                core = pval[: um.start()].strip()
                if core:
                    pval = core
            _add(f'P{par_num:03d} {pname}', pval, unit, m.group(0))

    # Named / P-code patterns only if table rows were sparse (legacy prints)
    if len(found) < 3:
        for rx, kind in _VFD_PARAM_PATTERNS:
            for m in rx.finditer(text):
                if kind.startswith('P') or kind.startswith('Param'):
                    num, val = m.group(1), m.group(2)
                    unit = (m.group(3) or '').strip()
                    key = f'P{int(num):03d}' if kind.startswith('P') else f'Param{int(num)}'
                    _add(key, val, unit, m.group(0))
                else:
                    key = re.sub(r'\s+', ' ', m.group(1).strip())
                    val = m.group(2)
                    unit = (m.group(3) or '').strip() if m.lastindex and m.lastindex >= 3 else ''
                    _add(key, val, unit, m.group(0))

    return found


def extract_vfd_params_from_text(
    text: str,
    source_file: str = '',
    *,
    device_ids: list[str] | None = None,
    page: int | None = None,
) -> list[dict]:
    """
    Parse VFD/drive parameters from OCR.

    Multi-VFD pages (e.g. VFD410 PF70 + VFD412 PF4 side-by-side) are split by
    VFD title so each drive only gets its own parameter table — no cross-bleed.
    """
    found: list[dict] = []
    seen: set[str] = set()
    src_name = Path(source_file).name if source_file else ''
    text = text or ''
    id_list = [_normalize_vfd_id(x) for x in (device_ids or []) if _normalize_vfd_id(x)]

    segments = _split_text_by_vfd(text)
    # If title-block OCR found IDs but text split found none/one, still try per known ID
    segment_ids = {vid for vid, _ in segments if vid}
    if id_list and not (segment_ids & set(id_list)) and len(segments) <= 1:
        # Fallback: whole page once per known ID is BAD (cross-bleed).
        # Instead assign whole page only if single ID.
        if len(id_list) == 1:
            segments = [(id_list[0], text)]
        else:
            # Keep text-split only; IDs without a text hit get no free-float params
            pass

    for vid, seg in segments:
        # Device_ID marker for inventory
        if vid and f'ID|{vid}' not in seen:
            seen.add(f'ID|{vid}')
            found.append({
                'param': 'Device_ID',
                'value': vid,
                'unit': '',
                'display': vid,
                'source': src_name,
                'raw': vid,
                'device_id': vid,
                **({'page': page} if page is not None else {}),
            })
        # Only extract params for a real VFD section (skip preamble)
        if not vid and len(segments) > 1:
            continue
        found.extend(
            _extract_params_in_segment(
                seg,
                device_id=vid,
                source_file=source_file,
                page=page,
                seen=seen,
            )
        )

    # Ensure title-block-only IDs are listed even if no text segment
    for vid in id_list:
        if f'ID|{vid}' not in seen:
            seen.add(f'ID|{vid}')
            found.append({
                'param': 'Device_ID',
                'value': vid,
                'unit': '',
                'display': vid,
                'source': src_name,
                'raw': vid,
                'device_id': vid,
                **({'page': page} if page is not None else {}),
            })

    return found


def attach_print_params_to_drives(
    drives: list[dict],
    ocr_results: list[dict],
) -> list[dict]:
    """
    Merge print-OCR VFD parameters onto program drive rows (from tar.gz).

    Does NOT remove or replace tar.gz devices — only adds print_params.
    Matching: VFD500A on print ↔ VFD500A_EN / VFD500A_AUX in RUN.
    Also matches by per-param device_id from title-block OCR.
    """
    # Build per-file param lists + full text + device ids
    file_params: list[tuple] = []  # file, text, params, ids
    # Global index: VFD id → list of non-Device_ID params
    by_device: dict[str, list[dict]] = defaultdict(list)
    by_device_sources: dict[str, set[str]] = defaultdict(set)

    # device_id → votes for (page, source_file)
    # Weight: wiring_title >> title_ocr >> param row. Avoid one noisy page (e.g. 27)
    # winning every drive via equal Device_ID stamps.
    page_hits: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    file_hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    page_hit_detail: dict[str, list[dict]] = defaultdict(list)  # for ocr log

    for ocr in ocr_results:
        if ocr.get('error'):
            continue
        src = ocr.get('file') or ''
        text = ocr.get('full_text') or ocr.get('text_preview') or ''
        # Prefer precomputed per-page vfd_params (has device_id + page)
        params: list[dict] = list(ocr.get('vfd_params') or [])
        if not params and text:
            params = extract_vfd_params_from_text(text, src)
        # Device IDs found on this sheet (VFD500A, etc.)
        ids: set[str] = set()
        for p in params:
            if p.get('param') == 'Device_ID' and p.get('value'):
                vid = _normalize_vfd_id(str(p['value']))
                if vid:
                    ids.add(vid)
                    try:
                        pg = int(p['page']) if p.get('page') is not None else None
                    except (TypeError, ValueError):
                        pg = None
                    id_src = str(p.get('id_source') or 'title_ocr')
                    # wiring_title = authoritative; plain title_ocr = weaker
                    w = 10 if id_src == 'wiring_title' else 2
                    if pg:
                        page_hits[vid][pg] += w
                        page_hit_detail[vid].append({
                            'page': pg, 'weight': w, 'why': id_src,
                            'file': Path(src).name if src else '',
                        })
                    if src:
                        file_hits[vid][src] += w
            did = _normalize_vfd_id(str(p.get('device_id') or ''))
            if did:
                ids.add(did)
                try:
                    pg = int(p.get('page')) if p.get('page') is not None else None
                except (TypeError, ValueError):
                    pg = None
                if p.get('param') != 'Device_ID':
                    # Real PowerFlex param row on a page — medium confidence
                    if pg:
                        page_hits[did][pg] += 1
                        page_hit_detail[did].append({
                            'page': pg, 'weight': 1, 'why': 'param_row',
                            'param': p.get('param'),
                            'file': Path(src).name if src else '',
                        })
                    if src:
                        file_hits[did][src] += 1
                    by_device[did].append(p)
                    by_device_sources[did].add(Path(src).name)
        # Do NOT harvest free-floating VFD tokens from full_text into page_hits
        # (that was collapsing many drives onto one page with OCR noise).
        for m in re.finditer(r'\bVFD[A-Z0-9]{2,8}\b', (text or '').upper()):
            vid = _normalize_vfd_id(m.group(0))
            if vid:
                ids.add(vid)
        ids = {i for i in ids if i}
        file_params.append((src, (text or '').upper(), params, ids))

        # Attach params with device_id. Orphans: stamp to primary VFD ids on sheet
        # (1 id → that drive; 2–4 primary ids → clone table to each — good-not-perfect).
        primary_ids = _primary_vfd_ids(ids)
        for p in params:
            if p.get('param') == 'Device_ID':
                continue
            did = _normalize_vfd_id(str(p.get('device_id') or ''))
            if did:
                by_device[did].append(p)
                by_device_sources[did].add(Path(src).name)
                continue
            # Orphan PowerFlex rows
            if not is_canonical_vfd_param(str(p.get('param') or '')):
                continue
            targets = primary_ids or (list(ids) if len(ids) == 1 else [])
            if not targets:
                continue
            for tid in targets:
                row = dict(p)
                row['device_id'] = tid
                by_device[tid].append(row)
                by_device_sources[tid].add(Path(src).name)

    for d in drives:
        name = (d.get('name') or '').upper()
        base = _normalize_vfd_id(d.get('base_name') or _base_equip_name(d.get('name') or ''))
        # base_name may not start with VFD (e.g. conveyors) — fall back to plain base
        base_plain = (d.get('base_name') or _base_equip_name(d.get('name') or '')).upper()
        motor = (d.get('motor') or '').upper()
        matched_params: list[dict] = []
        sources: list[str] = []

        # 1) Direct device_id match only (params already scoped to one VFD on multi-drive sheets)
        for candidate in (base, base_plain, _normalize_vfd_id(name), name):
            if not candidate:
                continue
            key = candidate if candidate.startswith('VFD') else _normalize_vfd_id(candidate)
            if key and key in by_device:
                matched_params.extend(by_device[key])
                sources.extend(by_device_sources.get(key) or [])
                break
            if candidate in by_device:
                matched_params.extend(by_device[candidate])
                sources.extend(by_device_sources.get(candidate) or [])
                break

        # 2) Single-VFD sheet legacy: sheet has exactly one VFD id and it matches this drive
        if not matched_params:
            for src, text_u, params, sheet_ids in file_params:
                if len(sheet_ids) != 1:
                    continue
                only = next(iter(sheet_ids))
                drive_keys = {
                    k for k in (base, base_plain, _normalize_vfd_id(name), name) if k
                }
                if only not in drive_keys and not any(
                    only.startswith(k) or k.startswith(only) for k in drive_keys if len(k) >= 4
                ):
                    continue
                sources.append(Path(src).name)
                for p in params:
                    if p.get('param') == 'Device_ID':
                        continue
                    # Prefer params already tagged; else orphan on single-VFD sheet
                    did = _normalize_vfd_id(str(p.get('device_id') or ''))
                    if did and did != only:
                        continue
                    matched_params.append(p)

        # Resolve best page even when PowerFlex table OCR failed (title-only hit)
        def _best_page_for(keys: list[str]) -> tuple[int | None, str]:
            votes: dict[int, int] = {}
            fvotes: dict[str, int] = {}
            for k in keys:
                if not k:
                    continue
                for pg, n in page_hits.get(k, {}).items():
                    votes[pg] = votes.get(pg, 0) + n
                for f, n in file_hits.get(k, {}).items():
                    fvotes[f] = fvotes.get(f, 0) + n
            for p in matched_params:
                try:
                    pg = int(p.get('page')) if p.get('page') is not None else None
                except (TypeError, ValueError):
                    pg = None
                if pg and pg > 0:
                    votes[pg] = votes.get(pg, 0) + 1
                src = str(p.get('source') or '')
                if src:
                    fvotes[src] = fvotes.get(src, 0) + 1
            bp = max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0] if votes else None
            bf = max(fvotes.items(), key=lambda kv: kv[1])[0] if fvotes else ''
            return bp, bf

        cand_keys = [base, base_plain, _normalize_vfd_id(name), name]
        best_page, best_file = _best_page_for([k for k in cand_keys if k])

        if not matched_params and best_page is None:
            # leave existing print_params if any; do not wipe tar.gz row
            continue

        # Keep only real PowerFlex program-table params (≈8 on a typical VFD sheet)
        cleaned = filter_canonical_vfd_params(matched_params) if matched_params else []
        if cleaned:
            by_key: dict[str, dict] = {}
            for p in cleaned:
                key = p.get('param') or 'param'
                by_key[key] = p
            d['print_params'] = dict(by_key)
            d['print_param_count'] = len(by_key)
            d['print_sources'] = sorted(set(sources))
            d['print_param_list'] = list(by_key.values())
            d['vfd_from_print'] = True
        elif best_page is not None:
            # Title-block page only (no param table) — still link PRINT #
            d['vfd_from_print'] = True
            if sources:
                d['print_sources'] = sorted(set(sources))

        if best_file:
            d['print_file'] = best_file
        if best_page is not None:
            d['print_page'] = int(best_page)
            # OCR page wins over ASC conveyor-page inherit for VFD rows
            d['drawing_page'] = int(best_page)
            d['_page_votes'] = dict(page_hits.get(base) or page_hits.get(_normalize_vfd_id(name)) or {})
        elif not d.get('drawing_page') and d.get('print_page'):
            d['drawing_page'] = d['print_page']
        # Only promote to VFD when the *name* is a VFD tag — never P### conveyors
        # (print params may still attach to a conveyor that has an associated drive).
        from fortna_io_extract import is_vfd_name
        if d.get('equipment_kind') != 'power_supply' and (
            is_vfd_name(name) or is_vfd_name(base_plain) or str(base or '').upper().startswith('VFD')
        ):
            d['is_vfd'] = True
            d['equipment_kind'] = 'vfd'
        elif is_vfd_name(name):
            d['is_vfd'] = True
            d['equipment_kind'] = 'vfd'

    # Share OCR params + print page across VFD444_EN / VFD444_AUX / VFD444_FLT siblings
    by_base_params: dict[str, list[dict]] = {}
    by_base_meta: dict[str, dict] = {}
    for d in drives:
        name = (d.get('name') or '')
        base = _normalize_vfd_id(_base_equip_name(name))
        if not base:
            continue
        if d.get('print_param_list') or d.get('print_params'):
            by_base_params[base] = list(d.get('print_param_list') or []) or list(
                (d.get('print_params') or {}).values()
            )
            by_base_meta[base] = {
                'print_page': d.get('print_page') or d.get('drawing_page'),
                'drawing_page': d.get('drawing_page') or d.get('print_page'),
                'print_file': d.get('print_file') or '',
                'print_sources': list(d.get('print_sources') or []),
                'print_params': dict(d.get('print_params') or {}),
                'print_param_count': d.get('print_param_count') or 0,
                'vfd_from_print': True,
            }
    for d in drives:
        name = (d.get('name') or '')
        base = _normalize_vfd_id(_base_equip_name(name))
        if not base or base not in by_base_params:
            continue
        if not (d.get('print_param_list') or d.get('print_params')):
            meta = by_base_meta[base]
            plist = by_base_params[base]
            d['print_param_list'] = list(plist)
            d['print_params'] = dict(meta.get('print_params') or {})
            d['print_param_count'] = meta.get('print_param_count') or len(plist)
            d['print_sources'] = list(meta.get('print_sources') or [])
            d['print_file'] = meta.get('print_file') or d.get('print_file') or ''
            d['vfd_from_print'] = True
            if not d.get('drawing_page') and meta.get('drawing_page'):
                d['drawing_page'] = meta['drawing_page']
                d['print_page'] = meta.get('print_page') or meta['drawing_page']

    # After OCR: only drives that actually matched a PDF keep print_page.
    # Clear any leftover ASC conveyor-page numbers on VFD rows that never OCR-matched
    # (prevents "all VFDs on page 18" from parent P### layout sheets).
    log_rows: list[dict] = []
    for d in drives:
        name = (d.get('name') or '')
        if not re.match(r'^VFD\d', name, re.I):
            continue
        has_ocr = bool(
            d.get('vfd_from_print')
            or d.get('print_param_count')
            or d.get('print_param_list')
            or d.get('print_sources')
        )
        if not has_ocr:
            d['drawing_page'] = None
            d['print_page'] = None
            d['print_file'] = ''
        base = _normalize_vfd_id(_base_equip_name(name))
        in_by_device = base in by_device if base else False
        raw_in_bucket = len(by_device.get(base) or []) if base else 0
        log_rows.append({
            'name': name,
            'base': base,
            'print_page': d.get('print_page'),
            'print_file': Path(str(d.get('print_file') or '')).name,
            'param_count': d.get('print_param_count') or 0,
            'param_keys': list((d.get('print_params') or {}).keys())[:20],
            'vfd_from_print': bool(d.get('vfd_from_print')),
            'page_votes': d.get('_page_votes') or dict(page_hits.get(base) or {}),
            'page_hit_detail': list(page_hit_detail.get(base) or [])[:20],
            'by_device_has_base': in_by_device,
            'by_device_raw_rows': raw_in_bucket,
            'why_no_params': (
                '' if (d.get('print_param_count') or 0) > 0
                else (
                    'no_print_page' if not d.get('print_page')
                    else (
                        'base_not_in_param_buckets'
                        if not in_by_device
                        else 'params_filtered_or_empty_after_canonical'
                    )
                )
            ),
        })
        d.pop('_page_votes', None)

    # Write page + param debug logs (exports/ocr-logs/)
    try:
        log_dir = REPO_ROOT / 'exports' / 'ocr-logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as _dt
        stamp = _dt.now().strftime('%Y%m%d-%H%M%S')
        log_path = log_dir / f'vfd_page_assign_{stamp}.json'
        from collections import Counter as _Counter
        winners = _Counter(
            str(r.get('print_page')) for r in log_rows if r.get('print_page')
        )
        with_params = sum(1 for r in log_rows if (r.get('param_count') or 0) > 0)
        log_path.write_text(
            json.dumps({
                'generated': stamp,
                'drive_count': len(log_rows),
                'drives_with_params': with_params,
                'page_winner_histogram': dict(winners.most_common()),
                'note': (
                    'Page log: if one page dominates, check page_hit_detail. '
                    'Param log: see vfd_param_extract_*.json for per-PDF-page OCR. '
                    'VFD816 often works because single-drive sheets have CAD text; '
                    'dual sheets need table OCR (+tableocr in mode).'
                ),
                'drives': log_rows,
            }, indent=2),
            encoding='utf-8',
        )
        (log_dir / f'vfd_page_assign_{stamp}.txt').write_text(
            '\n'.join([
                f'VFD print-page + param attach log {stamp}',
                f'Drives: {len(log_rows)} · with PowerFlex params: {with_params}',
                f'Page histogram: {dict(winners.most_common())}',
                '',
                'name | page | params | why_no_params | file',
                *([
                    f"{r['name']}: page={r.get('print_page')} params={r.get('param_count')} "
                    f"why={r.get('why_no_params') or 'ok'} "
                    f"keys={r.get('param_keys')} file={r.get('print_file')}"
                    for r in log_rows
                ]),
                '',
                f'Full JSON: {log_path}',
                f'Also see: vfd_param_extract_{stamp}.json (per-page table OCR)',
            ]),
            encoding='utf-8',
        )
        # Store stamp so caller can write param extract log with same stamp
        attach_print_params_to_drives._last_log_stamp = stamp  # type: ignore[attr-defined]
    except Exception:
        pass

    return drives


def summarize_points_by_bank(points: list[dict]) -> list[dict]:
    by_bank: dict[str, dict] = {}
    for p in points:
        bank = str(p.get('fortna_bank') or '?')
        if bank not in by_bank:
            by_bank[bank] = {
                'bank': bank,
                'point_count': 0,
                'inputs': 0,
                'outputs': 0,
                'points': [],
            }
        b = by_bank[bank]
        b['point_count'] += 1
        if p.get('io_type') == 'OUT':
            b['outputs'] += 1
        else:
            b['inputs'] += 1
        if len(b['points']) < 40:
            page = p.get('drawing_page') or p.get('print_page')
            b['points'].append({
                'tag': p.get('tag'),
                'fortna_name': p.get('fortna_name') or p.get('io_name'),
                'address': p.get('fortna_address'),
                'bit': p.get('fortna_bit'),
                'io_type': p.get('io_type'),
                'device_class': p.get('device_class'),
                'description': (p.get('description') or '')[:80],
                'drawing_page': page,
                'print_page': page,
                'machine_name': p.get('machine_name') or '',
            })
    return sorted(by_bank.values(), key=lambda x: (len(x['bank']), x['bank']))


def _count_real_vfd_params(params: list[dict]) -> int:
    """Count PowerFlex table rows (exclude Device_ID markers)."""
    n = 0
    for p in params or []:
        if not isinstance(p, dict):
            continue
        if (p.get('param') or '') == 'Device_ID':
            continue
        if is_canonical_vfd_param(str(p.get('param') or '')):
            n += 1
    return n


def _primary_vfd_ids(ids: list[str] | set[str] | None) -> list[str]:
    """Keep real drive IDs (VFD500, VFD700A). Drop OCR noise (VFD500R, VFD444S, …)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        vid = _normalize_vfd_id(str(raw))
        if not vid or vid in seen:
            continue
        # Plausible Fortna: VFD + 2–4 digits + optional letter (A–P common)
        if not re.fullmatch(r'VFD\d{2,4}[A-P]?', vid, re.I):
            continue
        # Reject trailing R/S/T/U/V/W noise from OCR of wire labels
        if re.search(r'[RSTUVW]$', vid, re.I) and not re.search(r'\d[A-P]$', vid, re.I):
            # VFD500R — drop; VFD700A — keep
            if re.search(r'[RSTUVW]$', vid):
                continue
        seen.add(vid)
        out.append(vid)
    return out


def _stamp_orphan_params_to_vfds(
    page_params: list[dict],
    page_vfd_ids: list[str],
) -> list[dict]:
    """
    When a sheet has PowerFlex table rows but no device_id (common multi-VFD CAD
    extract), stamp / clone params onto each *primary* VFD on that page.

    Good-not-perfect: dual sheets may share one table → both drives get the same
    params (better than 0% in the UI). Column OCR still preferred when it works.
    """
    primary = _primary_vfd_ids(page_vfd_ids)
    if not primary:
        primary = [
            _normalize_vfd_id(x) for x in (page_vfd_ids or [])
            if _normalize_vfd_id(x)
        ]
        primary = list(dict.fromkeys(primary))[:4]
    if not primary:
        return page_params

    id_rows = [p for p in page_params if (p.get('param') or '') == 'Device_ID']
    data_rows = [p for p in page_params if (p.get('param') or '') != 'Device_ID']
    stamped = [
        p for p in data_rows
        if _normalize_vfd_id(str(p.get('device_id') or ''))
        and is_canonical_vfd_param(str(p.get('param') or ''))
    ]
    orphans = [
        p for p in data_rows
        if not _normalize_vfd_id(str(p.get('device_id') or ''))
        and is_canonical_vfd_param(str(p.get('param') or ''))
    ]
    other = [
        p for p in data_rows
        if p not in stamped and p not in orphans
    ]

    if not orphans:
        return page_params

    # Single primary: just stamp in place
    if len(primary) == 1:
        only = primary[0]
        for p in orphans:
            p['device_id'] = only
        return page_params

    # Multi primary: clone each orphan row to every primary VFD on the page
    cloned: list[dict] = []
    for vid in primary:
        for p in orphans:
            row = dict(p)
            row['device_id'] = vid
            cloned.append(row)
    return id_rows + stamped + cloned + other


def _ocr_page_region_text(
    page,
    pytesseract,
    Image,
    *,
    y0_frac: float = 0.0,
    y1_frac: float = 1.0,
    x0_frac: float = 0.0,
    x1_frac: float = 1.0,
    mat_scale: float = 2.0,
) -> str:
    """Tesseract a fractional crop of a PDF page (graphics param tables)."""
    try:
        mat = __import__('fitz').Matrix(mat_scale, mat_scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
        w, h = img.size
        x0 = max(0, int(w * x0_frac))
        x1 = min(w, int(w * x1_frac))
        y0 = max(0, int(h * y0_frac))
        y1 = min(h, int(h * y1_frac))
        if x1 <= x0 or y1 <= y0:
            return ''
        crop = img.crop((x0, y0, x1, y1))
        if crop.width > 2200:
            ratio = 2200 / crop.width
            resample = getattr(getattr(Image, 'Resampling', Image), 'BILINEAR', Image.BILINEAR)
            crop = crop.resize((int(crop.width * ratio), int(crop.height * ratio)), resample)
        return _tesseract_page(crop, pytesseract)
    except Exception:
        return ''


def _tesseract_page(img, pytesseract) -> str:
    """Faster Tesseract settings for electrical prints (still good for tags/params)."""
    # OEM 1 = LSTM only; PSM 6 = assume a block of text (schematics / tables)
    cfg = '--oem 1 --psm 6'
    try:
        return pytesseract.image_to_string(img, config=cfg) or ''
    except Exception:
        return pytesseract.image_to_string(img) or ''


def ocr_pdf_tokens(
    pdf_path: Path,
    max_pages: int = 80,
    *,
    progress_ctx: dict | None = None,
    page_done_callback=None,
) -> dict:
    """Extract text from a PDF/image: native PDF text first, then Tesseract OCR.

    VFD PowerFlex tables on Fortna prints often sit past page 24 and use CAD
    text that is columnar in get_text('text'). We:
      1. Process up to max_pages (default 80 — covers full panel sets)
      2. Rebuild each page from word positions (Y then X) so table rows align
      3. On pages with PowerFlex tables, OCR title strips for VFD### tags

    Progress hooks:
      progress_ctx: {file, panel, file_index, file_total, ...}
      page_done_callback: called once per finished page (for global page counter)
    """
    import pytesseract
    from PIL import Image

    tess = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    if tess.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(tess)

    # Allow env override (e.g. FORTNA_OCR_MAX_PAGES=120)
    try:
        env_max = int((os.environ.get('FORTNA_OCR_MAX_PAGES') or '').strip() or '0')
        if env_max > 0:
            max_pages = env_max
    except ValueError:
        pass

    pages_text: list[str] = []
    pages_native = 0
    pages_ocr = 0
    pages_title_ocr = 0
    all_vfd_params: list[dict] = []
    # Per-page param extraction diagnostics (why VFD816 works but others don't)
    page_param_log: list[dict] = []
    suffix = pdf_path.suffix.lower()
    ctx = progress_ctx or {}
    file_label = pdf_path.name

    def _page_progress(page_i: int, pages_in_file: int, mode: str) -> None:
        emit_progress(
            phase='reading',
            file=file_label,
            panel=ctx.get('panel') or '',
            file_index=ctx.get('file_index') or 0,
            file_total=ctx.get('file_total') or 0,
            page=page_i,
            pages_in_file=pages_in_file,
            message=f"{file_label}: page {page_i}/{pages_in_file} ({mode})",
            mode=mode,
        )
        if page_done_callback:
            page_done_callback()

    if suffix == '.pdf':
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        n = min(len(doc), max_pages)
        # Full-page tesseract only when native text is sparse (slow path)
        mat = fitz.Matrix(1.5, 1.5)
        for i in range(n):
            page = doc[i]
            # Word-position rebuild restores PowerFlex rows from CAD PDFs
            rebuilt = _rebuild_text_from_words(page).strip()
            plain = (page.get_text('text') or '').strip()
            # Prefer whichever yields better VFD table structure
            if _page_has_powerflex_table(rebuilt) or len(rebuilt) >= len(plain):
                native = rebuilt if rebuilt else plain
            else:
                native = plain if plain else rebuilt

            page_mode = 'text'
            if len(native) >= 40:
                pages_native += 1
            else:
                # Sparse/empty page — full tesseract
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                if img.width > 2200:
                    ratio = 2200 / img.width
                    resample = getattr(getattr(Image, 'Resampling', Image), 'BILINEAR', Image.BILINEAR)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)), resample)
                native = _tesseract_page(img, pytesseract)
                pages_ocr += 1
                page_mode = 'ocr'

            # Title-block OCR for VFD tags (often graphics, not CAD text)
            page_vfd_ids: list[str] = []
            if _page_has_powerflex_table(native) or _VFD_ID_RE.search(native or ''):
                # Always try title strips when a param table is present — tags are
                # almost never in the native CAD text layer on these drawings.
                if _page_has_powerflex_table(native):
                    page_vfd_ids = _ocr_regions_for_vfd_ids(page, pytesseract, Image)
                    if page_vfd_ids:
                        pages_title_ocr += 1
                        page_mode = 'text+vfd'
                # Also harvest any IDs already in native/OCR text
                for m in _VFD_ID_RE.finditer(native or ''):
                    vid = _normalize_vfd_id('VFD' + m.group(1))
                    if vid and vid not in page_vfd_ids:
                        page_vfd_ids.append(vid)

            # Also harvest VFD WIRING title IDs from native/rebuilt text
            for vid in _vfd_ids_from_wiring_title(native or ''):
                if vid not in page_vfd_ids:
                    page_vfd_ids.append(vid)

            # Always try title-region OCR when native might be CAD-only (IDs are graphics)
            if not page_vfd_ids:
                page_vfd_ids = _ocr_regions_for_vfd_ids(page, pytesseract, Image)
                if page_vfd_ids:
                    pages_title_ocr += 1
                    page_mode = (page_mode + '+vfd') if page_mode else 'vfd'

            pages_text.append(native)
            # PDF page index is 1-based (i+1). Viewer #page=N matches this.
            # Multi-VFD sheets (typically 2 drives) share this same page number.
            pdf_page_1based = i + 1
            n_ids = len(set(page_vfd_ids or []))
            title_xs = _vfd_title_x_positions(page)
            cad_param_n = 0
            table_ocr_tried = False
            table_ocr_raw = 0
            table_ocr_kept = 0
            table_ocr_sample = ''

            if n_ids >= 2 or len(title_xs) >= 2:
                page_params = extract_vfd_params_from_page_spatial(
                    page,
                    str(pdf_path),
                    page_num=pdf_page_1based,
                    extra_ids=page_vfd_ids,
                )
                page_mode = (page_mode + '+cols') if page_mode else 'cols'
            else:
                page_params = extract_vfd_params_from_text(
                    native,
                    str(pdf_path),
                    device_ids=page_vfd_ids,
                    page=pdf_page_1based,
                )
            cad_param_n = _count_real_vfd_params(page_params)
            # How many real params already stamped with a device_id?
            # Multi-VFD sheets often extract a shared CAD table (cad_param_n high) but
            # leave device_id empty → attach only works for single-VFD pages (e.g. VFD816).
            stamped_n = 0
            for p in page_params:
                if (p.get('param') or '') == 'Device_ID':
                    continue
                if not is_canonical_vfd_param(str(p.get('param') or '')):
                    continue
                if _normalize_vfd_id(str(p.get('device_id') or '')):
                    stamped_n += 1
            n_ids = len(set(page_vfd_ids or []))
            need_column_ocr = (
                cad_param_n < 5
                or (n_ids >= 2 and stamped_n < 3)
            )

            # Graphics param tables: CAD word rebuild empty OR multi-VFD unstamped.
            # Why VFD816 often works alone: single-drive sheet + orphan→single-id attach.
            # Dual sheets need column OCR even when CAD already found unstamped rows.
            if need_column_ocr and (
                page_vfd_ids
                or _page_has_powerflex_table(native)
                or 'POWERFLEX' in (native or '').upper()
                or 'VFD' in (native or '').upper()
                or 'PAR' in (native or '').upper()
            ):
                table_ocr_tried = True
                ocr_params: list[dict] = []
                ids_unique = list(dict.fromkeys(page_vfd_ids or []))
                # Prefer physical X order from title words when available
                placed = sorted(
                    [(v, x) for v, x in title_xs if x >= 0],
                    key=lambda t: t[1],
                )
                if len(placed) >= 2:
                    try:
                        pw = float(page.rect.width) or 1.0
                    except Exception:
                        pw = 1.0
                    xs = [x for _, x in placed]
                    for i, (vid, x) in enumerate(placed):
                        left = 0.0 if i == 0 else (xs[i - 1] + x) / 2.0
                        right = pw if i == len(placed) - 1 else (x + xs[i + 1]) / 2.0
                        x0f = max(0.0, left / pw - 0.02)
                        x1f = min(1.0, right / pw + 0.02)
                        col = _ocr_page_region_text(
                            page, pytesseract, Image,
                            y0_frac=0.35, y1_frac=0.95, x0_frac=x0f, x1_frac=x1f,
                        )
                        if not col.strip():
                            # Full height column fallback
                            col = _ocr_page_region_text(
                                page, pytesseract, Image,
                                y0_frac=0.10, y1_frac=0.95, x0_frac=x0f, x1_frac=x1f,
                            )
                        if not col.strip():
                            continue
                        if not table_ocr_sample:
                            table_ocr_sample = col[:400].replace('\n', ' | ')
                        part = extract_vfd_params_from_text(
                            f'{vid}\n{col}',
                            str(pdf_path),
                            device_ids=[vid],
                            page=pdf_page_1based,
                        )
                        for p in part:
                            if (p.get('param') or '') != 'Device_ID' and not p.get('device_id'):
                                p['device_id'] = vid
                        ocr_params.extend(part)
                elif len(ids_unique) >= 2:
                    halves = [
                        (ids_unique[0], 0.02, 0.50),
                        (ids_unique[1], 0.50, 0.98),
                    ]
                    for vid, x0, x1 in halves:
                        col = _ocr_page_region_text(
                            page, pytesseract, Image,
                            y0_frac=0.35, y1_frac=0.95, x0_frac=x0, x1_frac=x1,
                        )
                        if not col.strip():
                            col = _ocr_page_region_text(
                                page, pytesseract, Image,
                                y0_frac=0.10, y1_frac=0.95, x0_frac=x0, x1_frac=x1,
                            )
                        if not col.strip():
                            continue
                        if not table_ocr_sample:
                            table_ocr_sample = col[:400].replace('\n', ' | ')
                        part = extract_vfd_params_from_text(
                            f'{vid}\n{col}',
                            str(pdf_path),
                            device_ids=[vid],
                            page=pdf_page_1based,
                        )
                        for p in part:
                            if (p.get('param') or '') != 'Device_ID' and not p.get('device_id'):
                                p['device_id'] = vid
                        ocr_params.extend(part)
                else:
                    # Single VFD: OCR full lower param table (and mid band if thin)
                    for y0, y1 in ((0.40, 0.95), (0.25, 0.95), (0.10, 0.98)):
                        ocr_text = _ocr_page_region_text(
                            page, pytesseract, Image,
                            y0_frac=y0, y1_frac=y1, x0_frac=0.04, x1_frac=0.96,
                        )
                        if not ocr_text.strip():
                            continue
                        if not table_ocr_sample:
                            table_ocr_sample = ocr_text[:400].replace('\n', ' | ')
                        only = ids_unique[0] if ids_unique else None
                        part = extract_vfd_params_from_text(
                            (f'{only}\n' if only else '') + ocr_text,
                            str(pdf_path),
                            device_ids=ids_unique or None,
                            page=pdf_page_1based,
                        )
                        if only:
                            for p in part:
                                if (p.get('param') or '') != 'Device_ID' and not p.get('device_id'):
                                    p['device_id'] = only
                        ocr_params.extend(part)
                        if _count_real_vfd_params(ocr_params) >= 4:
                            break

                table_ocr_raw = len([
                    p for p in ocr_params if (p.get('param') or '') != 'Device_ID'
                ])
                table_ocr_kept = _count_real_vfd_params(ocr_params)
                if table_ocr_kept > cad_param_n:
                    ids_only = [
                        p for p in page_params if (p.get('param') or '') == 'Device_ID'
                    ]
                    table_rows = [
                        p for p in ocr_params if (p.get('param') or '') != 'Device_ID'
                    ]
                    page_params = ids_only + table_rows
                    page_mode = (page_mode or 'text') + '+tableocr'
                    pages_ocr += 1

            # Stamp untagged table rows onto VFD(s) on this page.
            # Single VFD: stamp in place. Multi VFD with CAD orphans: clone to each
            # primary id (VFD500/VFD502) so UI gets params (was 0% after multi-id guard).
            if page_vfd_ids:
                page_params = _stamp_orphan_params_to_vfds(page_params, page_vfd_ids)

            # Stamp Device_ID only for IDs found on THIS page (title/wiring).
            # Prefer primary IDs for attach (drop VFD500R noise).
            wiring_ids = set(_vfd_ids_from_wiring_title(native or ''))
            ids_for_device = _primary_vfd_ids(page_vfd_ids) or list(
                dict.fromkeys(page_vfd_ids or [])
            )
            for vid in ids_for_device:
                page_params.append({
                    'param': 'Device_ID',
                    'value': vid,
                    'device_id': vid,
                    'page': pdf_page_1based,
                    'source': str(pdf_path),
                    'id_source': 'wiring_title' if vid in wiring_ids else 'title_ocr',
                })
            all_vfd_params.extend(page_params)

            # Per-device param counts on this page (for debug log)
            by_id_n: dict[str, int] = {}
            for p in page_params:
                if (p.get('param') or '') == 'Device_ID':
                    continue
                did = _normalize_vfd_id(str(p.get('device_id') or ''))
                if did and is_canonical_vfd_param(str(p.get('param') or '')):
                    by_id_n[did] = by_id_n.get(did, 0) + 1
            page_param_log.append({
                'file': file_label,
                'page': pdf_page_1based,
                'mode': page_mode,
                'native_chars': len(native or ''),
                'vfd_ids': list(ids_for_device or page_vfd_ids or []),
                'title_x_ids': [v for v, _ in title_xs],
                'cad_params': cad_param_n,
                'table_ocr_tried': table_ocr_tried,
                'table_ocr_raw_rows': table_ocr_raw,
                'table_ocr_kept': table_ocr_kept,
                'final_params': _count_real_vfd_params(page_params),
                'params_per_device_id': by_id_n,
                'ocr_text_sample': table_ocr_sample[:300] if table_ocr_sample else '',
                'why_no_params': (
                    '' if _count_real_vfd_params(page_params) > 0
                    else (
                        'no_vfd_ids_on_page' if not page_vfd_ids
                        else (
                            'table_ocr_empty_or_filtered'
                            if table_ocr_tried
                            else 'cad_text_no_table_and_ocr_skipped'
                        )
                    )
                ),
            })
            _page_progress(pdf_page_1based, n, page_mode)
        doc.close()
    elif suffix in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'):
        img = Image.open(pdf_path)
        if img.width > 2200:
            ratio = 2200 / img.width
            resample = getattr(getattr(Image, 'Resampling', Image), 'BILINEAR', Image.BILINEAR)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), resample)
        text = _tesseract_page(img, pytesseract)
        pages_text.append(text)
        pages_ocr += 1
        all_vfd_params.extend(extract_vfd_params_from_text(text, str(pdf_path), page=1))
        _page_progress(1, 1, 'ocr')
    else:
        raise ValueError(f'Unsupported print file type: {suffix}')

    full = '\n'.join(pages_text)
    # I/O names + points
    token_re = re.compile(
        r'\b(?:'
        r'PE\d{2,5}|M\d{2,5}|WB\d{2,4}|BCN\d{0,4}|'
        r'P\d{2,4}|'  # conveyors P100…
        r'Bank\s*\d+\s*[./]\s*\d+|'
        r'[IO]:\d+/\d+|'
        r'Local:\d+:[IO]\.\w+(?:\.\d+)?|'
        r'[A-Z][A-Z0-9_]{2,24}'
        r')\b',
        re.I,
    )
    raw_tokens = token_re.findall(full)
    tokens: list[str] = []
    seen: set[str] = set()
    noise = {
        'THE', 'AND', 'FOR', 'WITH', 'FROM', 'THIS', 'THAT', 'PAGE', 'SHEET',
        'DRAWING', 'REV', 'DATE', 'RACK', 'PANEL', 'LOCAL', 'REMOTE', 'MASTER',
    }
    for t in raw_tokens:
        n = re.sub(r'\s+', '', t.upper().replace('BANK', 'Bank'))
        n = n.replace('..', '.')
        if n in seen or n in noise:
            continue
        seen.add(n)
        tokens.append(n)

    # Rack / panel names on prints (for remote → master merge)
    rack_names: list[str] = []
    rack_seen: set[str] = set()
    for m in re.finditer(
        r'\b(?:'
        r'RACK\s*#?\s*([A-Z0-9\-]{1,12})|'
        r'(MCP\s*\d{1,3})|'
        r'(PANEL\s*[A-Z0-9\-]{1,12})|'
        r'(LOCAL\s*RACK)|'
        r'(REMOTE\s*RACK\s*\d*)|'
        r'(ENET\s*RACK\s*\d*)|'
        r'(DROP\s*\d{1,3})'
        r')\b',
        full,
        re.I,
    ):
        raw = next((g for g in m.groups() if g), m.group(0))
        name = re.sub(r'\s+', ' ', str(raw).strip().upper())
        if name and name not in rack_seen:
            rack_seen.add(name)
            rack_names.append(name)

    # Conveyor names (P100, CV-12, etc.) for remote panel population
    conveyor_names: list[str] = []
    conv_seen: set[str] = set()
    for m in re.finditer(r'\b(P\d{2,4}|CV[\-_]?[A-Z0-9]{1,8}|CONV[\-_]?[A-Z0-9]{1,8})\b', full, re.I):
        cn = m.group(1).upper().replace('_', '-')
        if cn not in conv_seen:
            conv_seen.add(cn)
            conveyor_names.append(cn)

    # Prefer per-page params (with device_id/page); fall back to whole-doc extract
    vfd_params = all_vfd_params
    if not vfd_params:
        vfd_params = extract_vfd_params_from_text(full, str(pdf_path))

    # Dedupe Device_ID + param rows across pages
    deduped: list[dict] = []
    dseen: set[str] = set()
    for p in vfd_params:
        sk = f"{p.get('device_id','')}|{p.get('param')}|{p.get('display') or p.get('value')}".upper()
        if sk in dseen:
            continue
        dseen.add(sk)
        deduped.append(p)
    vfd_params = deduped

    return {
        'file': str(pdf_path),
        'pages_ocrd': len(pages_text),
        'pages_native_text': pages_native,
        'pages_tesseract': pages_ocr,
        'pages_title_ocr': pages_title_ocr,
        'char_count': len(full),
        'text_preview': full[:2500],
        'full_text': full,
        'tokens': tokens[:500],
        'token_count': len(tokens),
        'io_names': [t for t in tokens if re.match(r'^(PE|M|WB|BCN|P)\d', t, re.I) or 'BANK' in t.upper() or ':' in t][:300],
        'rack_names': rack_names[:80],
        'conveyor_names': conveyor_names[:200],
        'vfd_params': vfd_params,
        'vfd_param_count': len(vfd_params),
        'page_param_log': page_param_log,
    }


def build_remote_merge_package(ocr_results: list[dict]) -> dict:
    """
    From remote panel prints: collect I/O names + rack names to add onto the master.
    Also collect conveyor names + VFD params (for remote panels).
    """
    io_names: dict[str, dict] = {}
    racks: dict[str, dict] = {}
    conveyors: dict[str, dict] = {}
    vfd_by_panel: dict[str, list] = defaultdict(list)

    for ocr in ocr_results:
        if ocr.get('error'):
            continue
        panel = ocr.get('panel') or 'Unassigned'
        role = (ocr.get('role') or 'remote').lower()
        src = Path(ocr.get('file') or '').name

        for tok in ocr.get('io_names') or ocr.get('tokens') or []:
            key = _normalize_token(tok)
            if len(key) < 2:
                continue
            if key not in io_names:
                io_names[key] = {
                    'io_name': tok,
                    'panels': [],
                    'roles': [],
                    'files': [],
                }
            row = io_names[key]
            if panel not in row['panels']:
                row['panels'].append(panel)
            if role not in row['roles']:
                row['roles'].append(role)
            if src and src not in row['files']:
                row['files'].append(src)

        for rack in ocr.get('rack_names') or []:
            rk = rack.upper()
            if rk not in racks:
                racks[rk] = {'rack_name': rack, 'panels': [], 'roles': [], 'files': []}
            if panel not in racks[rk]['panels']:
                racks[rk]['panels'].append(panel)
            if role not in racks[rk]['roles']:
                racks[rk]['roles'].append(role)
            if src and src not in racks[rk]['files']:
                racks[rk]['files'].append(src)

        # Conveyors + VFD primarily from remote panels (still capture master if present)
        for cn in ocr.get('conveyor_names') or []:
            ck = cn.upper()
            if ck not in conveyors:
                conveyors[ck] = {
                    'conveyor_name': cn,
                    'panels': [],
                    'roles': [],
                    'vfd_params': [],
                    'files': [],
                }
            c = conveyors[ck]
            if panel not in c['panels']:
                c['panels'].append(panel)
            if role not in c['roles']:
                c['roles'].append(role)
            if src and src not in c['files']:
                c['files'].append(src)

        if role == 'remote':
            for vp in ocr.get('vfd_params') or []:
                item = dict(vp)
                item['panel'] = panel
                vfd_by_panel[panel].append(item)
                # Attach VFD params to conveyors named on same sheet when possible
                text_u = (ocr.get('full_text') or ocr.get('text_preview') or '').upper()
                for ck, c in conveyors.items():
                    if ck in text_u and panel in c['panels']:
                        c['vfd_params'].append(item)

    # Remote-only lists for "add to master"
    remote_io = [
        v for v in io_names.values()
        if 'remote' in v['roles']
    ]
    remote_racks = [
        v for v in racks.values()
        if 'remote' in v['roles']
    ]
    remote_conveyors = [
        v for v in conveyors.values()
        if 'remote' in v['roles']
    ]

    # Deduplicate VFD params on conveyors
    for c in conveyors.values():
        seen = set()
        uniq = []
        for p in c['vfd_params']:
            sk = f"{p.get('param')}|{p.get('display')}"
            if sk in seen:
                continue
            seen.add(sk)
            uniq.append(p)
        c['vfd_params'] = uniq
        c['vfd_param_count'] = len(uniq)

    return {
        'remote_io_names': sorted(remote_io, key=lambda x: x['io_name']),
        'remote_io_count': len(remote_io),
        'remote_racks': sorted(remote_racks, key=lambda x: x['rack_name']),
        'remote_rack_count': len(remote_racks),
        'remote_conveyors': sorted(remote_conveyors, key=lambda x: x['conveyor_name']),
        'remote_conveyor_count': len(remote_conveyors),
        'all_io_names': sorted(io_names.values(), key=lambda x: x['io_name']),
        'all_racks': sorted(racks.values(), key=lambda x: x['rack_name']),
        'vfd_by_panel': {k: v for k, v in vfd_by_panel.items()},
        'note': (
            'Remote I/O names + rack names are collected to add onto the master controller. '
            'Compare these names to the tar.gz program I/O. '
            'Remote panels also supply conveyor names and VFD parameters.'
        ),
    }


def _normalize_token(tok: str) -> str:
    return re.sub(r'\s+', '', str(tok or '').upper()).replace('_', '')


def crosswalk_prints_to_io(points: list[dict], ocr_results: list[dict]) -> dict:
    """
    Cross-reference OCR print tokens with program I/O from the RUN tar.gz.

    Architecture note (recontrol): typically one master controller holds local I/O;
    remaining panels are remote I/O. Panel sets carry role=master|remote so we can
    report where each matched point was found on the drawings.
    """
    name_map: dict[str, dict] = {}
    for p in points:
        for key in (
            p.get('fortna_name'), p.get('io_name'), p.get('tag'),
            p.get('fortna_address'), p.get('conveyor'),
        ):
            if not key:
                continue
            k = _normalize_token(key)
            name_map[k] = p
            name_map[k.replace('_', '')] = p
            # Bank6000.20 without "Bank" prefix sometimes on prints
            m = re.match(r'BANK(\d+)\.(\d+)', k)
            if m:
                name_map[f'{m.group(1)}.{m.group(2)}'] = p
                name_map[f'{m.group(1)}/{m.group(2)}'] = p

    matched = []
    unmatched_print = []
    matched_keys: set[str] = set()
    # tag -> set of panels where seen
    tag_panels: dict[str, set[str]] = defaultdict(set)
    tag_roles: dict[str, set[str]] = defaultdict(set)

    all_tokens: list[tuple[str, str, str, str]] = []  # tok, file, panel, role
    for ocr in ocr_results:
        src = Path(ocr.get('file', '')).name
        panel = ocr.get('panel') or ocr.get('panel_set') or 'Unassigned'
        role = (ocr.get('role') or 'remote').lower()
        if role not in ('master', 'remote'):
            role = 'remote'
        for tok in ocr.get('tokens') or []:
            all_tokens.append((tok, src, panel, role))

    for tok, src, panel, role in all_tokens:
        key = _normalize_token(tok)
        bank_m = re.match(r'BANK(\d+)[./](\d+)', key)
        hit = None
        if bank_m:
            addr = f'Bank{bank_m.group(1)}.{bank_m.group(2)}'
            hit = name_map.get(_normalize_token(addr))
        if not hit:
            # Logix-style I:1/0 or O:2/5 — map weakly by trailing numbers only if unique later
            hit = name_map.get(key) or name_map.get(tok.upper())
        if hit:
            mk = hit.get('tag') or hit.get('fortna_name')
            tag_panels[mk].add(panel)
            tag_roles[mk].add(role)
            if mk not in matched_keys:
                matched_keys.add(mk)
                matched.append({
                    'print_token': tok,
                    'print_file': src,
                    'panel': panel,
                    'role': role,
                    'program_tag': hit.get('tag'),
                    'fortna_name': hit.get('fortna_name'),
                    'fortna_address': hit.get('fortna_address'),
                    'fortna_bank': hit.get('fortna_bank'),
                    'device_class': hit.get('device_class'),
                    'io_type': hit.get('io_type'),
                    'description': (hit.get('description') or '')[:80],
                    'scope_hint': 'master_local' if role == 'master' else 'remote_io',
                })
            else:
                # Update existing match with additional panel sightings
                for row in matched:
                    if (row.get('program_tag') or row.get('fortna_name')) == mk:
                        panels = set(row.get('panels') or [row.get('panel')])
                        panels.add(panel)
                        row['panels'] = sorted(panels)
                        roles = set(row.get('roles') or [row.get('role')])
                        roles.add(role)
                        row['roles'] = sorted(roles)
                        if 'master' in roles and 'remote' in roles:
                            row['scope_hint'] = 'both'
                        elif 'master' in roles:
                            row['scope_hint'] = 'master_local'
                        else:
                            row['scope_hint'] = 'remote_io'
                        break
        else:
            if len(unmatched_print) < 400:
                unmatched_print.append({
                    'token': tok,
                    'print_file': src,
                    'panel': panel,
                    'role': role,
                })

    # Finalize panels list on matched rows
    for row in matched:
        mk = row.get('program_tag') or row.get('fortna_name')
        if mk in tag_panels:
            row['panels'] = sorted(tag_panels[mk])
            row['roles'] = sorted(tag_roles[mk])
            if 'master' in row['roles'] and 'remote' in row['roles']:
                row['scope_hint'] = 'both'
            elif 'master' in row['roles']:
                row['scope_hint'] = 'master_local'
            else:
                row['scope_hint'] = 'remote_io'

    program_only = []
    for p in points:
        mk = p.get('tag') or p.get('fortna_name')
        if mk not in matched_keys and len(program_only) < 300:
            program_only.append({
                'program_tag': p.get('tag'),
                'fortna_name': p.get('fortna_name'),
                'fortna_address': p.get('fortna_address'),
                'fortna_bank': p.get('fortna_bank'),
                'device_class': p.get('device_class'),
                'io_type': p.get('io_type'),
            })

    # Per-panel rollup
    panel_stats: dict[str, dict] = {}
    for ocr in ocr_results:
        panel = ocr.get('panel') or 'Unassigned'
        role = ocr.get('role') or 'remote'
        if panel not in panel_stats:
            panel_stats[panel] = {
                'panel': panel,
                'role': role,
                'files': 0,
                'pages_ocrd': 0,
                'tokens': 0,
                'matched_io': 0,
                'print_only': 0,
            }
        st = panel_stats[panel]
        st['files'] += 1
        st['pages_ocrd'] += int(ocr.get('pages_ocrd') or 0)
        st['tokens'] += int(ocr.get('token_count') or 0)
    for row in matched:
        for panel in row.get('panels') or [row.get('panel')]:
            if panel in panel_stats:
                panel_stats[panel]['matched_io'] += 1
    for row in unmatched_print:
        panel = row.get('panel') or 'Unassigned'
        if panel in panel_stats:
            panel_stats[panel]['print_only'] += 1

    master_matched = sum(1 for r in matched if r.get('scope_hint') == 'master_local')
    remote_matched = sum(1 for r in matched if r.get('scope_hint') == 'remote_io')
    both_matched = sum(1 for r in matched if r.get('scope_hint') == 'both')

    return {
        'matched': matched,
        'matched_count': len(matched),
        'print_only_tokens': unmatched_print,
        'print_only_count': len(unmatched_print),
        'program_only': program_only,
        'program_only_count': len(program_only),
        'program_total': len(points),
        'coverage_pct': round(100.0 * len(matched) / len(points), 1) if points else 0.0,
        'master_local_matched': master_matched,
        'remote_io_matched': remote_matched,
        'both_panels_matched': both_matched,
        'panels': sorted(panel_stats.values(), key=lambda x: (x['role'] != 'master', x['panel'])),
        'architecture_note': (
            'Typical recontrol: one master controller keeps local rack I/O; '
            'other panels are remote I/O. Assign each print set as Master or Remote.'
        ),
    }


def cmd_banks(run_dir: Path, *, sample_points: int = 8) -> dict:
    """Build I/O banks + drives payload for the dashboard.

    Points per bank are sampled for the UI so Electron spawnSync does not blow
    the default 1MB stdout buffer on large sites (e.g. 800+ I/O points).
    """
    meta = read_project_meta(run_dir)
    points = extract_io_points(run_dir, include_spares=False)
    configio = extract_configio_banks(run_dir)
    by_bank = summarize_points_by_bank(points)
    drive_info = extract_drive_parameters(run_dir)

    # Slim bank cards: keep counts + a short sample, not every point
    slim_banks = []
    for b in by_bank:
        pts = b.get('points') or []
        slim = dict(b)
        if sample_points and len(pts) > sample_points:
            slim['points'] = pts[:sample_points]
            slim['points_truncated'] = len(pts) - sample_points
        else:
            slim['points_truncated'] = 0
        slim_banks.append(slim)

    # Slim drives hard — large sites have 900+ conveyor rows; full program_params
    # per row used to blow Electron's stdout buffer and dump JSON into the UI.
    # Keep table fields + a short param sample; detail view still usable.
    PREFERRED_PROG = (
        'Drive', 'Speed', 'Motor', 'BeltInfo', 'DeviceType', 'Description',
        'IOAddress', 'Name', 'VFD', 'Accel', 'Decel', 'Hz', 'FLA', 'HP',
    )
    slim_drives = []
    for d in drive_info.get('drives') or []:
        prog = d.get('program_params') or {}
        if not isinstance(prog, dict):
            prog = {}
        # Prefer known fields, then fill up to 12 keys total
        slim_prog = {}
        for k in PREFERRED_PROG:
            if k in prog and prog[k] not in (None, ''):
                slim_prog[k] = prog[k]
        if len(slim_prog) < 12:
            for k in sorted(prog.keys()):
                if k in slim_prog:
                    continue
                if prog[k] in (None, ''):
                    continue
                slim_prog[k] = prog[k]
                if len(slim_prog) >= 12:
                    break
        from fortna_io_extract import is_vfd_name, is_real_drive_id
        name = d.get('name') or ''
        kind = d.get('equipment_kind') or ''
        # P### = conveyor always; VFD only for VFD### names / kind==vfd
        if is_vfd_name(name) or kind == 'vfd':
            is_vfd = True
            kind = 'vfd'
        else:
            is_vfd = False
            if re.match(r'^P\d', name, re.I) and kind in ('', 'other', 'vfd'):
                kind = 'conveyor'
        page = d.get('drawing_page') or d.get('print_page')
        slim_drives.append({
            'name': name,
            'base_name': d.get('base_name') or _base_equip_name(name),
            'drive': d.get('drive') or '',
            'speed': d.get('speed') or '',
            'motor': d.get('motor') or '',
            'belt_info': d.get('belt_info') or '',
            'device_type': d.get('device_type') or '',
            'equipment_kind': kind,
            'description': d.get('description') or '',
            'io_address': d.get('io_address') or '',
            'machine_name': d.get('machine_name') or '',
            'program_params': slim_prog,
            'program_params_truncated': max(0, len(prog) - len(slim_prog)),
            'print_params': d.get('print_params') or {},
            'print_param_list': (d.get('print_param_list') or [])[:40],
            'print_param_count': d.get('print_param_count') or 0,
            'print_sources': d.get('print_sources') or [],
            # Electrical drawing page from Conveyor.asc (Print # column)
            'drawing_page': page,
            'print_page': page,
            'print_file': d.get('print_file') or '',
            'is_vfd': is_vfd,
            # Title-only OCR still counts (print_page set, params may be 0)
            'vfd_from_print': bool(
                is_vfd and (
                    d.get('print_param_count')
                    or d.get('print_page')
                    or d.get('vfd_from_print')
                )
            ),
            'has_real_drive_id': is_real_drive_id(d.get('drive') or ''),
        })

    # Full name → page map (not truncated). UI uses this so bank sampling
    # never drops Print # for pushbuttons / PE / ES that aren't in the sample.
    print_pages: dict[str, int] = {}
    for p in points:
        name = (p.get('fortna_name') or p.get('io_name') or p.get('tag') or '').strip()
        page = p.get('drawing_page') or p.get('print_page')
        if name and page:
            try:
                print_pages[name] = int(page)
            except (TypeError, ValueError):
                pass
    for d in drive_info.get('drives') or []:
        name = (d.get('name') or '').strip()
        page = d.get('drawing_page') or d.get('print_page')
        if name and page:
            try:
                print_pages[name] = int(page)
            except (TypeError, ValueError):
                pass

    return {
        'ok': True,
        'machine': meta.get('machine_name') or '',
        'project': meta.get('project_name') or '',
        'run_dir': str(run_dir),
        'point_count': len(points),
        'bank_count': len(by_bank),
        'banks': slim_banks,
        'configio_rows': configio[:50],
        'configio_count': len(configio),  # full count from Configio.asc — not capped
        'configio_source': configio[0]['source'] if configio else None,
        'drives': slim_drives,
        'drive_count': drive_info['drive_count'],
        'drive_id_summary': drive_info['drive_id_summary'],
        'motor_chains': (drive_info.get('motor_chains') or [])[:100],
        'motor_chain_count': drive_info['motor_chain_count'],
        'drives_with_print_params': sum(1 for d in slim_drives if d.get('print_param_count')),
        'vfd_drive_count': sum(1 for d in slim_drives if d.get('is_vfd')),
        'drives_with_drawing_page': sum(1 for d in slim_drives if d.get('drawing_page')),
        'print_pages': print_pages,
        'print_page_count': len(print_pages),
    }


def _estimate_pdf_pages(path: Path, max_pages: int = 80) -> int:
    if path.suffix.lower() != '.pdf':
        return 1
    try:
        import fitz
        doc = fitz.open(path)
        n = min(len(doc), max_pages)
        doc.close()
        return max(1, n)
    except Exception:
        return max_pages


def _ocr_one_file(
    src: Path,
    panel: str,
    role: str,
    dest_dir: Path,
    *,
    progress_ctx: dict | None = None,
    page_done_callback=None,
    max_pages: int = 80,
) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    # Avoid clobber when same filename appears in multiple panels
    if dest.exists() and src.resolve() != dest.resolve():
        dest = dest_dir / f'{panel}__{src.name}'
    if src.resolve() != dest.resolve():
        dest.write_bytes(src.read_bytes())
    try:
        ocr = ocr_pdf_tokens(
            dest,
            max_pages=max_pages,
            progress_ctx=progress_ctx,
            page_done_callback=page_done_callback,
        )
    except Exception as exc:
        ocr = {
            'file': str(dest),
            'error': str(exc),
            'tokens': [],
            'token_count': 0,
            'pages_ocrd': 0,
            'text_preview': '',
            'vfd_params': [],
            'vfd_param_count': 0,
        }
        if page_done_callback:
            # Still advance progress so a failed file doesn't stall the bar
            est = _estimate_pdf_pages(src, max_pages)
            for _ in range(est):
                page_done_callback()
    ocr['panel'] = panel
    ocr['panel_set'] = panel
    ocr['role'] = role if role in ('master', 'remote') else 'remote'
    ocr['saved_as'] = str(dest)
    return ocr


def cmd_ocr_print(paths: list[Path], run_dir: Path | None, *, panel: str = 'Unassigned', role: str = 'remote') -> dict:
    """OCR a flat list of prints under one panel set (legacy entry point)."""
    return cmd_ocr_print_sets(
        [{'name': panel or 'Unassigned', 'role': role or 'remote', 'paths': [str(p) for p in paths]}],
        run_dir,
    )


def cmd_ocr_print_sets(sets: list[dict], run_dir: Path | None) -> dict:
    """
    OCR multiple panel print sets and crosswalk to program I/O.

    sets: [ { name: 'MCP01', role: 'master'|'remote', paths: ['a.pdf', ...] }, ... ]
    Parallel file OCR when the machine has free cores (FORTNA_OCR_WORKERS).
    """
    PRINTS_DIR.mkdir(parents=True, exist_ok=True)
    ocr_results: list[dict] = []
    saved: list[str] = []
    set_summaries: list[dict] = []

    # Flatten jobs so we can parallelize across panels/files
    jobs: list[dict] = []
    for s in sets or []:
        panel = (s.get('name') or s.get('panel') or 'Unassigned').strip() or 'Unassigned'
        role = (s.get('role') or 'remote').strip().lower()
        if role not in ('master', 'remote'):
            role = 'remote'
        panel_dir = PRINTS_DIR / re.sub(r'[^A-Za-z0-9_-]+', '_', panel)[:40]
        file_count = 0
        for raw in s.get('paths') or []:
            src = Path(raw)
            if not src.is_file():
                continue
            jobs.append({
                'src': src,
                'panel': panel,
                'role': role,
                'panel_dir': panel_dir,
            })
            file_count += 1
        set_summaries.append({
            'name': panel,
            'role': role,
            'file_count': file_count,
        })

    file_total = len(jobs)
    # Default 80 pages — VFD PowerFlex tables often live past page 24
    ocr_max_pages = 80
    try:
        env_max = int((os.environ.get('FORTNA_OCR_MAX_PAGES') or '').strip() or '0')
        if env_max > 0:
            ocr_max_pages = env_max
    except ValueError:
        pass
    pages_total = sum(_estimate_pdf_pages(j['src'], ocr_max_pages) for j in jobs) or 1
    pages_done_box = {'n': 0}
    pages_lock = threading.Lock()
    workers = min(_ocr_worker_count(), max(1, file_total)) if file_total else 1

    def _bump_page() -> None:
        with pages_lock:
            pages_done_box['n'] += 1
            done = pages_done_box['n']
        emit_progress(
            phase='reading',
            pages_done=done,
            pages_total=pages_total,
            file_total=file_total,
            workers=workers,
            message=f'Pages {done}/{pages_total}',
        )

    emit_progress(
        phase='starting',
        file='',
        panel='',
        file_index=0,
        file_total=file_total,
        page=0,
        pages_in_file=0,
        pages_done=0,
        pages_total=pages_total,
        pct=0,
        workers=workers,
        message=f'Starting OCR: {file_total} file(s), ~{pages_total} page(s), {workers} worker(s)',
    )

    def _run_job(idx: int, job: dict) -> dict:
        ctx = {
            'panel': job['panel'],
            'file_index': idx + 1,
            'file_total': file_total,
        }
        emit_progress(
            phase='file',
            file=job['src'].name,
            panel=job['panel'],
            file_index=idx + 1,
            file_total=file_total,
            message=f"File {idx + 1}/{file_total}: {job['src'].name} ({job['panel']})",
            workers=workers,
        )
        return _ocr_one_file(
            job['src'],
            job['panel'],
            job['role'],
            job['panel_dir'],
            progress_ctx=ctx,
            page_done_callback=_bump_page,
            max_pages=ocr_max_pages,
        )

    if file_total == 0:
        emit_progress(phase='done', message='No print files to OCR', pct=100, pages_done=0, pages_total=0)
    elif workers <= 1 or file_total == 1:
        for i, job in enumerate(jobs):
            ocr_results.append(_run_job(i, job))
            saved.append(ocr_results[-1].get('saved_as') or str(job['src']))
    else:
        # Parallel files — each Tesseract is its own process, so threads scale well
        results_by_idx: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_run_job, i, job): i for i, job in enumerate(jobs)}
            for fut in as_completed(futs):
                idx = futs[fut]
                try:
                    results_by_idx[idx] = fut.result()
                except Exception as exc:
                    job = jobs[idx]
                    results_by_idx[idx] = {
                        'file': str(job['src']),
                        'error': str(exc),
                        'tokens': [],
                        'token_count': 0,
                        'pages_ocrd': 0,
                        'vfd_params': [],
                        'vfd_param_count': 0,
                        'panel': job['panel'],
                        'panel_set': job['panel'],
                        'role': job['role'],
                        'saved_as': str(job['src']),
                    }
        for i in range(file_total):
            ocr_results.append(results_by_idx[i])
            saved.append(ocr_results[i].get('saved_as') or str(jobs[i]['src']))

    emit_progress(
        phase='crosswalk',
        message='OCR pages done — matching I/O + VFD params…',
        pages_done=pages_total,
        pages_total=pages_total,
        pct=99,
        file_total=file_total,
        workers=workers,
    )

    points: list[dict] = []
    machine = ''
    drive_payload: dict = {
        'drives': [],
        'drive_count': 0,
        'drive_id_summary': [],
        'motor_chains': [],
        'motor_chain_count': 0,
    }
    if run_dir and run_dir.is_dir():
        points = extract_io_points(run_dir, include_spares=False)
        machine = read_project_meta(run_dir).get('machine_name') or ''
        drive_payload = extract_drive_parameters(run_dir)
        drive_payload['drives'] = attach_print_params_to_drives(
            drive_payload['drives'], ocr_results,
        )
        drive_payload['drives_with_print_params'] = sum(
            1 for d in drive_payload['drives'] if d.get('print_param_count')
        )
        # Per-page param extraction log (table OCR diagnostics)
        try:
            log_dir = REPO_ROOT / 'exports' / 'ocr-logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = getattr(attach_print_params_to_drives, '_last_log_stamp', None)
            if not stamp:
                from datetime import datetime as _dt
                stamp = _dt.now().strftime('%Y%m%d-%H%M%S')
            pages = []
            for o in ocr_results:
                for row in (o.get('page_param_log') or []):
                    pages.append(row)
            with_final = [p for p in pages if (p.get('final_params') or 0) > 0]
            path_j = log_dir / f'vfd_param_extract_{stamp}.json'
            path_j.write_text(
                json.dumps({
                    'generated': stamp,
                    'pdf_pages_logged': len(pages),
                    'pages_with_params': len(with_final),
                    'note': (
                        'Each row is one PDF page. final_params>0 means PowerFlex table '
                        'rows were kept. If table_ocr_tried and final_params=0, OCR text '
                        'did not match P031/… patterns (see ocr_text_sample). '
                        'VFD816 typically has cad_params>0 (CAD text layer present).'
                    ),
                    'pages': pages,
                }, indent=2),
                encoding='utf-8',
            )
            (log_dir / f'vfd_param_extract_{stamp}.txt').write_text(
                '\n'.join([
                    f'VFD PowerFlex param extract log {stamp}',
                    f'Pages logged: {len(pages)} · pages with params: {len(with_final)}',
                    '',
                    'file | page | mode | ids | cad | ocr_kept | final | why',
                    *([
                        f"{p.get('file')}: p{p.get('page')} mode={p.get('mode')} "
                        f"ids={p.get('vfd_ids')} cad={p.get('cad_params')} "
                        f"ocr={p.get('table_ocr_kept')} final={p.get('final_params')} "
                        f"per_id={p.get('params_per_device_id')} "
                        f"why={p.get('why_no_params') or 'ok'}"
                        for p in pages
                        if p.get('vfd_ids') or (p.get('final_params') or 0) > 0
                        or p.get('table_ocr_tried')
                    ]),
                    '',
                    '--- OCR text samples (first pages with sample) ---',
                    *([
                        f"p{p.get('page')} {p.get('file')}: {p.get('ocr_text_sample')}"
                        for p in pages if p.get('ocr_text_sample')
                    ][:12]),
                    '',
                    f'Full JSON: {path_j}',
                ]),
                encoding='utf-8',
            )
        except Exception:
            pass

    if points:
        crosswalk = crosswalk_prints_to_io(points, ocr_results)
    else:
        crosswalk = {
            'matched': [],
            'matched_count': 0,
            'print_only_tokens': [],
            'print_only_count': 0,
            'program_only': [],
            'program_only_count': 0,
            'program_total': 0,
            'coverage_pct': 0.0,
            'panels': [],
            'note': 'No active RUN loaded — OCR only. Import a tar.gz to crosswalk vs program I/O.',
            'architecture_note': (
                'Typical recontrol: one master controller keeps local rack I/O; '
                'other panels are remote I/O.'
            ),
        }

    all_print_vfd: list[dict] = []
    for ocr in ocr_results:
        for p in ocr.get('vfd_params') or []:
            pp = dict(p)
            pp['panel'] = ocr.get('panel')
            pp['role'] = ocr.get('role')
            all_print_vfd.append(pp)

    remote_merge = build_remote_merge_package(ocr_results)

    # Prefer remote-panel VFD/conveyor population on drives that match remote conveyors
    remote_conv_names = {
        c['conveyor_name'].upper() for c in remote_merge.get('remote_conveyors') or []
    }
    for d in drive_payload.get('drives') or []:
        n = (d.get('name') or '').upper()
        d['from_remote_print'] = n in remote_conv_names or any(
            n in (c.get('conveyor_name') or '').upper()
            for c in remote_merge.get('remote_conveyors') or []
        )
        # If print params empty but remote conveyor has VFD params, attach them
        if d.get('from_remote_print') and not d.get('print_param_count'):
            for c in remote_merge.get('remote_conveyors') or []:
                if (c.get('conveyor_name') or '').upper() == n and c.get('vfd_params'):
                    by_key = {p['param']: p for p in c['vfd_params']}
                    d['print_params'] = by_key
                    d['print_param_count'] = len(by_key)
                    d['print_param_list'] = list(by_key.values())
                    d['print_sources'] = c.get('files') or c.get('panels') or []
                    break

    drive_payload['drives_with_print_params'] = sum(
        1 for d in (drive_payload.get('drives') or []) if d.get('print_param_count')
    )

    # Flag real VFDs only — never mark P### conveyors as VFD (Drive="1" is a flag, not a VFD id)
    from fortna_io_extract import is_vfd_name
    for d in drive_payload.get('drives') or []:
        name = d.get('name') or ''
        if is_vfd_name(name) or d.get('equipment_kind') == 'vfd':
            d['is_vfd'] = True
            d['equipment_kind'] = 'vfd'
            # Keep title-only page hits (params may be 0) — do not clear vfd_from_print
            d['vfd_from_print'] = bool(
                d.get('print_param_count')
                or d.get('print_page')
                or d.get('drawing_page')
                or d.get('vfd_from_print')
            )
        else:
            d['is_vfd'] = False
            d['vfd_from_print'] = False
            if re.match(r'^P\d', name, re.I) and (d.get('equipment_kind') or '') in (
                '', 'other', 'vfd'
            ):
                d['equipment_kind'] = 'conveyor'

    emit_progress(
        phase='done',
        message=(
            f"Done — {file_total} file(s), "
            f"{drive_payload.get('drives_with_print_params') or 0} drive(s) with print VFD params, "
            f"{len(all_print_vfd)} VFD param hit(s)"
        ),
        pages_done=pages_total,
        pages_total=pages_total,
        pct=100,
        file_total=file_total,
        workers=workers,
    )

    payload = {
        'ok': True,
        'machine': machine,
        'saved_prints': saved,
        'print_sets': set_summaries,
        'print_set_count': len(set_summaries),
        'master_panels': [s for s in set_summaries if s.get('role') == 'master'],
        'remote_panels': [s for s in set_summaries if s.get('role') == 'remote'],
        'ocr': [
            {k: v for k, v in o.items() if k != 'full_text'}
            for o in ocr_results
        ],
        'crosswalk': crosswalk,
        'remote_merge': remote_merge,
        'drives': drive_payload.get('drives') or [],
        'drive_count': drive_payload.get('drive_count') or 0,
        'drive_id_summary': drive_payload.get('drive_id_summary') or [],
        'motor_chains': drive_payload.get('motor_chains') or [],
        'motor_chain_count': drive_payload.get('motor_chain_count') or 0,
        'drives_with_print_params': drive_payload.get('drives_with_print_params') or 0,
        'print_vfd_params': all_print_vfd,
        'print_vfd_param_count': len(all_print_vfd),
        'ocr_workers': workers,
        'ocr_pages_total': pages_total,
    }

    # Persist last OCR/crosswalk so UI can reload after restart
    try:
        out_dir = REPO_ROOT / 'workspace'
        out_dir.mkdir(parents=True, exist_ok=True)
        slim = {
            'ok': True,
            'machine': machine,
            'print_sets': set_summaries,
            'print_set_count': len(set_summaries),
            'crosswalk': {
                k: v for k, v in (crosswalk or {}).items()
                if k not in ('program_only',)  # can be huge
            },
            # Keep sample of program_only for UI
            'crosswalk_program_only_sample': (crosswalk or {}).get('program_only', [])[:100],
            'remote_merge': remote_merge,
            'ocr_summary': [
                {
                    'file': o.get('file'),
                    'panel': o.get('panel'),
                    'role': o.get('role'),
                    'pages_ocrd': o.get('pages_ocrd'),
                    'token_count': o.get('token_count'),
                    'vfd_param_count': o.get('vfd_param_count'),
                    'error': o.get('error'),
                }
                for o in ocr_results
            ],
            'drives_with_print_params': drive_payload.get('drives_with_print_params') or 0,
            'print_vfd_param_count': len(all_print_vfd),
            'ocr_pages_total': pages_total,
            'ocr_workers': workers,
        }
        # Restore program_only sample into crosswalk for display
        if 'crosswalk' in slim and isinstance(slim['crosswalk'], dict):
            slim['crosswalk']['program_only'] = slim.pop('crosswalk_program_only_sample', [])
            slim['crosswalk']['program_only_count'] = (crosswalk or {}).get('program_only_count', 0)
        (out_dir / 'ocr-last-result.json').write_text(
            json.dumps(slim, separators=(',', ':')), encoding='utf-8'
        )
    except Exception:
        pass

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='FortnaPlus I/O banks + print OCR crosswalk')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_banks = sub.add_parser('banks', help='List I/O banks from active or given RUN')
    p_banks.add_argument('--run-dir', default='')
    p_banks.add_argument('--no-active', action='store_true')

    p_ocr = sub.add_parser('ocr-prints', help='OCR print PDFs/images and crosswalk to program I/O')
    p_ocr.add_argument('paths', nargs='*', help='PDF or image paths (single panel)')
    p_ocr.add_argument('--panel', default='Unassigned', help='Panel set name (e.g. MCP01)')
    p_ocr.add_argument('--role', default='remote', choices=['master', 'remote'])
    p_ocr.add_argument('--sets-json', default='', help='JSON file with multiple panel sets')
    p_ocr.add_argument('--run-dir', default='')
    p_ocr.add_argument('--no-active', action='store_true')

    args = parser.parse_args()
    try:
        if args.cmd == 'banks':
            rd = resolve_run_dir(args.run_dir, use_active=not args.no_active)
            if not rd:
                print(json.dumps({'ok': False, 'error': 'No active RUN. Import a .tar.gz on Workspace first.'}))
                return 1
            # Compact JSON — large sites exceed Electron's old 1MB stdout buffer when pretty-printed
            print(json.dumps(cmd_banks(rd), separators=(',', ':')))
            return 0

        if args.cmd == 'ocr-prints':
            rd = resolve_run_dir(args.run_dir, use_active=not args.no_active)
            if args.sets_json:
                payload = json.loads(Path(args.sets_json).read_text(encoding='utf-8'))
                sets = payload.get('sets') or payload
                print(json.dumps(cmd_ocr_print_sets(sets, rd), separators=(',', ':')))
            else:
                paths = [Path(p) for p in (args.paths or [])]
                if not paths:
                    print(json.dumps({'ok': False, 'error': 'No print paths provided.'}))
                    return 1
                print(json.dumps(cmd_ocr_print(paths, rd, panel=args.panel, role=args.role), separators=(',', ':')))
            return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
