#!/usr/bin/env python3
"""Extract I/O points, layout, and project metadata from a Fortna RUN package."""
from __future__ import annotations

import re
from pathlib import Path

from fortna_asc import read_asc

PLACEHOLDER_IO = {('6000', '20'), ('6000', '21')}
SKIP_IO_NAMES = frozenset({'', 'INVALID', 'N/A', 'SPARE', 'NEVERON', 'ALWAYSON'})

INPUT_TYPES = frozenset({'PHOTOCELL', 'PROXPART', 'SCANNER', 'ZEROPRESSURE'})
OUTPUT_TYPES = frozenset({'MOTOR', 'BEACON', 'ANALOGOUTPUT'})
CONVEYOR_TYPES = frozenset({'STRAIGHT', 'BELT', 'CURVE', 'MERGE', 'SKEW', 'ACCUM', 'SPUR', 'TRIANG'})

DEVICE_CLASS_MAP = {
    'PHOTOCELL': 'Photoeye',
    'PROXPART': 'DigitalInput',
    'SCANNER': 'Scanner',
    'MOTOR': 'Motor',
    'BEACON': 'Beacon',
    'ZEROPRESSURE': 'DigitalInput',
    'STRAIGHT': 'Conveyor',
    'BELT': 'Conveyor',
    'CURVE': 'Conveyor',
    'MERGE': 'Conveyor',
    'TRIANG': 'Conveyor',
}


def read_project_meta(run_dir: Path) -> dict:
    meta = {
        'machine_name': '',
        'project_name': '',
        'machine_type': '',
        'fortna_dir': 'FORTNA',
        'project_dir': 'PROJECT',
    }
    cfg = run_dir / 'project.cfg'
    if not cfg.is_file():
        return meta
    text = cfg.read_text(encoding='utf-8', errors='replace')
    for key, field in (
        ('machine_name', 'MACHINENAME'),
        ('project_name', 'PROJECTNAME'),
        ('machine_type', 'MACHINETYPE'),
    ):
        m = re.search(rf'{field}\s*=\s*(\S+)', text, re.I)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def machine_aliases(machine: str) -> set[str]:
    """ORNCCP5 → {ORNCCP5, CP5, ORDENCP5, …} for flexible Machine_Name match."""
    m = (machine or '').strip().upper()
    if not m:
        return set()
    aliases = {m, m.replace(' ', '')}
    mm = re.search(r'CP\s*0*(\d+)', m, re.I)
    if mm:
        n = str(int(mm.group(1)))  # strip leading zeros
        aliases.update({
            f'CP{n}',
            f'ORNCCP{n}',
            f'ORDENCP{n}',
            f'ORLYCP{n}',
        })
    return {a for a in aliases if a}


def row_machine_matches(row_machine: str, machine: str) -> bool:
    """True when ASC Machine_Name is explicitly this controller."""
    rm = (row_machine or '').strip().upper()
    if not rm or rm in ('N/A', 'INVALID', 'NONE', 'ALL', '0'):
        return False
    aliases = machine_aliases(machine)
    if rm in aliases:
        return True
    for a in aliases:
        if len(a) >= 3 and (a in rm or rm in a):
            return True
    return False


def row_is_other_machine(row_machine: str, machine: str) -> bool:
    """True when row is tagged to a *different* controller (exclude)."""
    rm = (row_machine or '').strip().upper()
    if not rm or rm in ('N/A', 'INVALID', 'NONE', 'ALL', '0'):
        return False
    return not row_machine_matches(rm, machine)


def word_on_controller(word: str, word_map: dict | None) -> bool:
    """True if Fortna IO_Address_Word maps to this controller's EIP RIO."""
    if not word_map:
        return False
    w = str(word or '').strip()
    if not w or w in ('0', '6000', '6001'):
        return False
    if w in word_map:
        return True
    try:
        wi = int(float(w))
        if str(wi) in word_map:
            return True
        # high-half bank on 16-bit modules
        if wi % 2 == 1 and str(wi - 1) in word_map:
            return True
    except (TypeError, ValueError):
        pass
    return False


def belongs_to_controller(
    *,
    machine_name: str,
    io_word: str,
    controller: str,
    word_map: dict | None = None,
) -> bool:
    """
    Scope a Conveyor.asc row to one master PLC (e.g. ORNCCP5).

    Rules:
      1) Explicit Machine_Name match → include
      2) Explicit other Machine_Name → exclude
      3) Blank/N/A → include only if Word is on this controller's EIP map
    """
    if not (controller or '').strip():
        return True  # no scoping
    if row_machine_matches(machine_name, controller):
        return True
    if row_is_other_machine(machine_name, controller):
        return False
    return word_on_controller(io_word, word_map)


def _sanitize_tag(name: str) -> str:
    """Studio 5000 tag names must start with a letter or underscore."""
    raw = re.sub(r'[^A-Za-z0-9_]', '_', (name or '').strip())
    raw = re.sub(r'_+', '_', raw).strip('_')
    if not raw:
        return 'Tag'
    if raw[0].isdigit():
        raw = f'IO_{raw}'
    return raw[:40]


def _infer_area(io_name: str, description: str = '') -> str:
    text = f'{io_name} {description}'.upper()
    m = re.search(r'\bP(\d)(\d{2})\b', text)
    if m:
        return f'ZONE_{m.group(1)}'
    m = re.search(r'\bPE(\d{3})', text)
    if m:
        return f'ZONE_{m.group(1)[0]}'
    m = re.search(r'\bWB(\d{3})', text)
    if m:
        return f'ZONE_{m.group(1)[0]}'
    return 'ORDENCOMM'


def _parse_float(value: str) -> float | None:
    try:
        v = float((value or '').strip())
        return v if v != 0.0 else None
    except (TypeError, ValueError):
        return None


def _io_direction(device_type: str) -> str:
    typ = (device_type or '').upper()
    if typ in OUTPUT_TYPES:
        return 'OUT'
    if typ in INPUT_TYPES:
        return 'IN'
    if typ in CONVEYOR_TYPES:
        return 'OUT'
    return 'IN'


def normalize_io_name(io_name: str) -> str:
    """Canonical equipment name without I/O role suffixes (_F/_P/_AUX) or bank prefixes."""
    n = (io_name or '').strip()
    # Strip common status suffixes for matching (keep full name for tags)
    n = re.sub(r'(_F\d*|_P\d*|_AUX|_RUN|_FLT|_OK)$', '', n, flags=re.I)
    return n


def equipment_kind(io_name: str, device_type: str = '', description: str = '', *, drive: str = '') -> str:
    """
    Classify equipment by name + ASC type.

    Naming conventions (site / prints):
      VFD500A, VFD502  → VFD (PowerFlex etc.)
      M100, M102       → motor contactor / starter (NOT VFD)
      EZPWS116         → power supply (NOT VFD)
      EZPE116_F / PE…  → photoeye
      P100, P310       → conveyor
    """
    typ = (device_type or '').upper().strip()
    name = (io_name or '').strip()
    name_u = name.upper()
    desc_u = (description or '').upper()
    drive_u = (drive or '').upper()

    # --- Name prefixes first for known hardware families (override ambiguous ASC types) ---
    # Power supplies (EZPWS…) — never treat as VFD
    if name_u.startswith('EZPWS') or name_u.startswith('PWS') or re.match(r'^PS\d', name_u):
        return 'power_supply'
    # Explicit VFD tag names from prints / program (VFD500A, VFD502)
    if re.match(r'^VFD\d', name_u) or name_u.startswith('VFD_') or re.match(r'^PF\d', name_u):
        return 'vfd'
    if re.search(r'\bVFD\d{2,}', name_u) or re.search(r'\bVFD\d{2,}', desc_u):
        return 'vfd'
    # Photoeyes before bare P…
    if name_u.startswith('EZPE') or re.match(r'^PE\d', name_u) or name_u.startswith('PE_'):
        return 'photoeye'
    # Motor contactors / starters — M### only (not MCR as conveyor)
    if re.match(r'^M\d', name_u) and not name_u.startswith('MCR'):
        return 'motor'

    # --- ASC Type ---
    if typ == 'PHOTOCELL':
        return 'photoeye'
    if typ == 'MOTOR':
        # Still motor contactor unless name is clearly a VFD
        if re.match(r'^VFD\d', name_u):
            return 'vfd'
        return 'motor'
    if typ == 'BEACON':
        return 'beacon'
    if typ == 'SCANNER':
        return 'scanner'
    if typ in CONVEYOR_TYPES:
        return 'conveyor'
    if typ == 'PROXPART':
        if 'PB' in name_u or 'PUSH' in desc_u:
            return 'pushbutton'
        return 'digital_in'
    if typ == 'ZEROPRESSURE':
        # ZP / power-supply related zones — not VFDs
        if name_u.startswith('EZPWS') or 'POWER SUPPLY' in desc_u or 'PWR SUP' in desc_u:
            return 'power_supply'
        return 'conveyor'
    if typ == 'INVALID':
        return 'spare'

    # --- Description / remaining names ---
    # P### conveyors first — never reclassify as VFD from description ("VFD driven", etc.)
    if re.match(r'^P\d', name_u):
        return 'conveyor'
    if 'POWER SUPPLY' in desc_u or 'PWR SUPPLY' in desc_u or 'POWER SUP' in desc_u:
        return 'power_supply'
    if re.search(r'\bPOWER\s*FLEX\b', desc_u) or re.search(r'\bVFD\b', desc_u):
        # Desc says VFD/PowerFlex only for non-conveyor, non-EZPWS names
        if not name_u.startswith('EZPWS') and not re.match(r'^P\d', name_u):
            return 'vfd'
    if name_u.startswith('WB') or name_u.startswith('BCN') or re.match(r'^WH\d', name_u):
        return 'beacon'
    if re.match(r'^ESL?\d', name_u) or ('ESTOP' in desc_u and name_u.startswith('ES')):
        return 'estop'
    if 'PHOTO' in desc_u or 'PHOTOEYE' in desc_u or 'PHOTO EYE' in desc_u:
        return 'photoeye'
    # Drive catalog that looks like a real drive id (not bare "0"/"1")
    if drive_u and drive_u not in ('0', '1', 'N/A', 'N', '~', '') and (
        re.match(r'^VFD\d', drive_u)
        or 'PF525' in drive_u
        or 'POWERFLEX' in drive_u
        or re.match(r'^VFD', drive_u)
    ):
        return 'vfd'
    return 'other'


def is_vfd_name(io_name: str) -> bool:
    """True only for explicit VFD tags (VFD500A), never P### conveyors."""
    n = (io_name or '').strip().upper()
    if re.match(r'^P\d', n):
        return False
    return bool(
        re.match(r'^VFD\d', n)
        or n.startswith('VFD_')
        or re.match(r'^PF\d', n)
    )


def is_real_drive_id(drive: str) -> bool:
    """Fortna ASC Drive field is often '0'/'1' (flag) — that is NOT a VFD id."""
    d = (drive or '').strip().upper()
    if not d or d in ('0', '1', 'N/A', 'N', '~', 'NONE', 'INVALID', 'SPARE'):
        return False
    # Real catalog / tag style
    return bool(
        re.match(r'^VFD\d', d)
        or re.match(r'^PF\d', d)
        or 'POWERFLEX' in d
        or 'PF525' in d
        or (len(d) > 2 and any(c.isalpha() for c in d))
    )


def _device_class(device_type: str, io_name: str, description: str = '', *, drive: str = '') -> str:
    kind = equipment_kind(io_name, device_type, description, drive=drive)
    return {
        'photoeye': 'Photoeye',
        'motor': 'Motor',
        'beacon': 'Beacon',
        'scanner': 'Scanner',
        'conveyor': 'Conveyor',
        'vfd': 'VFD',
        'power_supply': 'PowerSupply',
        'pushbutton': 'Pushbutton',
        'digital_in': 'DigitalInput',
        'estop': 'EStop',
        'spare': 'Spare',
        'other': 'IO',
    }.get(kind, 'IO')


def _linked_conveyor(description: str, io_name: str) -> str:
    text = f'{description} {io_name}'.upper()
    m = re.search(r'\bON\s+(P\d{3})\b', text)
    if m:
        return m.group(1)
    m = re.search(r'\b(P\d{3})\b', text)
    if m:
        return m.group(1)
    return ''


def parse_drawing_page(row: dict | None) -> int | None:
    """Electrical drawing page from Conveyor.asc (links device → print sheet).

    Returns None when blank/0 so the UI can show "—" instead of a fake page.
    """
    if not row:
        return None
    page_raw = (
        row.get('Electrical Drawing Page No.')
        or row.get('Electrical_Drawing_Page_No.')
        or row.get('Drawing_Page')
        or row.get('drawing_page')
        or ''
    )
    if page_raw is None:
        return None
    page_raw = str(page_raw).strip()
    if not page_raw or page_raw in ('0', '0.0', 'N/A', 'INVALID', 'NONE'):
        return None
    try:
        page = int(float(page_raw))
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def extract_io_points(run_dir: Path, *, include_spares: bool = False) -> list[dict]:
    conv_path = run_dir / 'FORTNA' / 'Conveyor.asc'
    if not conv_path.is_file():
        return []

    headers, rows = read_asc(conv_path)
    points: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        io_name = (row.get('IO_Name') or '').strip()
        if io_name.upper() in SKIP_IO_NAMES:
            continue

        word = (row.get('IO_Address_Word') or '').strip()
        bit = (row.get('IO_Address_Bit') or '').strip()
        if (word, bit) in PLACEHOLDER_IO:
            continue

        device_type = (row.get('Type') or '').strip().upper()
        if device_type == 'INVALID' and not include_spares:
            continue

        tag = _sanitize_tag(io_name)
        if tag in seen:
            continue
        seen.add(tag)

        desc = (row.get('General_Description') or row.get('Device_Description') or '').strip()
        drive = (row.get('Drive') or '').strip()
        motor = (row.get('Motor') or '').strip()
        speed = (row.get('Speed') or '').strip()
        area = _infer_area(io_name, desc)
        kind = equipment_kind(io_name, device_type, desc, drive=drive)
        dc = _device_class(device_type, io_name, desc, drive=drive)
        io_type = _io_direction(device_type)
        # VFD only when classified as vfd — never EZPWS power supplies or bare M contactors
        is_vfd = kind == 'vfd'
        drawing_page = parse_drawing_page(row)

        points.append({
            'tag': tag,
            'fortna_name': io_name,
            'io_name': io_name,
            'display_name': normalize_io_name(io_name),
            'equipment_kind': kind,
            'fortna_bank': word,
            'fortna_bit': bit,
            'fortna_address': f'Bank{word}.{bit}',
            'io_type': io_type,
            'device_class': dc,
            'device_type': device_type,
            'description': desc[:200],
            'area': area,
            'conveyor': _linked_conveyor(desc, io_name),
            'drive': drive,
            'motor': motor,
            'speed': speed,
            'is_vfd': is_vfd,
            'machine_name': (row.get('Machine_Name') or '').strip(),
            'drawing_page': drawing_page,
            'print_page': drawing_page,
            'module': f'Fortna_Bank_{word}',
            'catalog': 'Fortna_Internal_IO',
            'x': _parse_float(row.get('X_cord') or row.get('X_COORD') or ''),
            'y': _parse_float(row.get('Y_cord') or row.get('Y_COORD') or ''),
            'angle': _parse_float(row.get('Angle') or ''),
            'width': _parse_float(row.get('Width') or ''),
            'length': _parse_float(row.get('Length') or ''),
            'source_table': 'FORTNA/Conveyor.asc',
        })

    points.sort(key=lambda p: (p['area'], p['io_type'], p['tag']))
    return points


def extract_beacon_outputs(run_dir: Path) -> list[dict]:
    path = run_dir / 'FORTNA' / 'BeaconInfo.asc'
    if not path.is_file():
        return []

    _, rows = read_asc(path)
    beacons: list[dict] = []
    for row in rows:
        name = (row.get('Name') or '').strip()
        output = (row.get('BeaconOutput') or '').strip()
        if not name or name.startswith('===') or output.upper() in SKIP_IO_NAMES:
            continue
        beacons.append({
            'beacon_name': name,
            'output_tag': _sanitize_tag(output),
            'pattern': (row.get('DefaultPattern') or '').strip(),
        })
    return beacons


def summarize_io(points: list[dict]) -> dict:
    stats = {
        'total': len(points),
        'inputs': sum(1 for p in points if p['io_type'] == 'IN'),
        'outputs': sum(1 for p in points if p['io_type'] == 'OUT'),
        'with_coords': sum(1 for p in points if p.get('x') is not None),
        'areas': {},
        'device_classes': {},
    }
    for p in points:
        stats['areas'][p['area']] = stats['areas'].get(p['area'], 0) + 1
        dc = p['device_class']
        stats['device_classes'][dc] = stats['device_classes'].get(dc, 0) + 1
    return stats


def normalize_coords(points: list[dict]) -> tuple[float, float, float, float]:
    xs = [p['x'] for p in points if p.get('x') is not None]
    ys = [p['y'] for p in points if p.get('y') is not None]
    if not xs or not ys:
        return 0.0, 0.0, 1.0, 1.0
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    return min_x, min_y, span_x, span_y


def scaled_fio_coord(x: float | None, y: float | None, min_x: float, min_y: float, span_x: float, span_y: float) -> tuple[int, int]:
    """Map Fortna layout coords to Factory I/O grid (integers — FIO rejects fractions)."""
    if x is None or y is None:
        return 10, 10
    fx = 10.0 + ((x - min_x) / span_x) * 80.0
    fz = 10.0 + ((y - min_y) / span_y) * 80.0
    return int(round(fx)), int(round(fz))