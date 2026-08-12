#!/usr/bin/env python3
"""Parse and edit Fortna Plus tilde-delimited .asc tables."""
from __future__ import annotations

import io
import re
from copy import deepcopy
from pathlib import Path

NAME_COLUMNS = (
    'IO_Name', 'Name', 'ProductIO', 'Beacon', 'Conveyor', 'Motor', 'Scanner',
    'Printer', 'Machine', 'Destination', 'Source', 'Zone', 'Area',
)
TYPE_COLUMN = 'Type'
COORD_COLUMNS = ('X_cord', 'Y_cord', 'Angle', 'X_COORD', 'Y_COORD')
SKIP_NAME_VALUES = {'', 'N/A', 'INVALID', 'N/A~', 'NONE', 'n/a', '~', ' '}
SKIP_FILE_PREFIXES = ('old.', 'backup.', '.bak')
CONVEYOR_TYPES = frozenset({'STRAIGHT', 'BELT', 'CURVE', 'MERGE', 'SKEW', 'ACCUM', 'SPUR', 'TRIANG'})
SCAN_FOLDERS = ('FORTNA', 'PROJECT')


def read_asc(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], []
    header_line = lines[0].strip()
    if header_line.startswith('"') and '~' in header_line:
        headers = [h.strip().strip('"') for h in header_line.split('~')]
    else:
        headers = [h.strip() for h in header_line.split('~')]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = line.split('~')
        if len(parts) < len(headers):
            parts.extend([''] * (len(headers) - len(parts)))
        row = {headers[i]: parts[i] if i < len(parts) else '' for i in range(len(headers))}
        rows.append(row)
    return headers, rows


def write_asc(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    out = io.StringIO()
    out.write('~'.join(f'"{h}"' if not h.startswith('"') else h for h in headers))
    out.write('\n')
    for row in rows:
        vals = [row.get(h, '') for h in headers]
        out.write('~'.join(vals))
        out.write('\n')
    path.write_text(out.getvalue(), encoding='utf-8')


def detect_name_columns(headers: list[str]) -> list[str]:
    cols = [h for h in NAME_COLUMNS if h in headers]
    if cols:
        return cols
    return [headers[0]] if headers else []


def row_names(row: dict[str, str], name_cols: list[str]) -> list[str]:
    names = []
    for col in name_cols:
        val = (row.get(col) or '').strip()
        if val and val not in SKIP_NAME_VALUES:
            names.append(val)
    return names


JUNK_TYPE_PATTERN = re.compile(
    r'^(INVALID|N/A|NONE|0|1|COUNT|IMAGE|LOGIN|LOGOUT|USER |SYSTEM |ELAPSED|AUTO )',
    re.I,
)


def categorize_device(table_file: str, row: dict[str, str], primary_name: str) -> str | None:
    typ = (row.get(TYPE_COLUMN) or '').strip().upper()
    name_u = primary_name.upper()
    table_u = Path(table_file).stem.upper()

    if typ == 'PHOTOCELL' or name_u.startswith(('PE', 'EZPE', 'PH')):
        return 'photoeye'
    if typ in CONVEYOR_TYPES:
        return 'conveyor'
    if typ == 'MOTOR' or name_u.startswith('M'):
        return 'motor'
    if typ == 'BEACON':
        return 'beacon'
    if typ == 'ZEROPRESSURE':
        return 'zeropressure'
    if 'SPIRAL' in name_u or table_u == 'NEWGAPPER':
        return 'spiral'
    if 'SCAN' in table_u or typ == 'SCANNER':
        return 'scanner'
    if 'SORT' in table_u or 'DIVERT' in name_u:
        return 'sorter'
    if 'PRINT' in table_u:
        return 'printer'
    if typ and not JUNK_TYPE_PATTERN.match(typ) and typ not in ('INVALID', '0'):
        return typ.lower()
    if any(k in table_u for k in ('CONVEYOR', 'GAPPER', 'MOTOR', 'SCANNER', 'SORT', 'PRINT', 'FULLLINE')):
        return 'device'
    return None


def iter_asc_tables(run_dir: Path):
    for folder in SCAN_FOLDERS:
        base = run_dir / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob('*.asc')):
            if path.name.lower().startswith(SKIP_FILE_PREFIXES):
                continue
            yield path, path.relative_to(run_dir).as_posix()


def scan_devices(run_dir: Path, machine: str = '') -> list[dict]:
    devices: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for path, rel in iter_asc_tables(run_dir):
        headers, rows = read_asc(path)
        if not headers:
            continue
        name_cols = detect_name_columns(headers)
        type_col = TYPE_COLUMN if TYPE_COLUMN in headers else ''

        for idx, row in enumerate(rows):
            names = row_names(row, name_cols)
            if not names:
                continue
            primary = names[0]
            key = (rel, primary.upper())
            if key in seen:
                continue
            seen.add(key)

            row_machine = (row.get('Machine_Name') or '').strip()
            if machine and row_machine not in ('', 'N/A', machine):
                continue

            category = categorize_device(rel, row, primary)
            if not category:
                continue

            devices.append({
                'id': f'{rel}::{primary}',
                'name': primary,
                'table': rel,
                'category': category,
                'type': (row.get(type_col) or '').strip() or category,
                'row_index': idx,
                'machine': row_machine or machine or '',
                'description': (row.get('General_Description') or row.get('Debug') or row.get('pState') or '').strip()[:120],
                'has_coords': any(row.get(c) for c in COORD_COLUMNS),
            })

    devices.sort(key=lambda d: (d['category'], d['table'], d['name']))
    return devices


def summarize_device_categories(devices: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in devices:
        counts[d['category']] = counts.get(d['category'], 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def find_row_by_name(rows: list[dict[str, str]], name: str, name_cols: list[str]) -> tuple[int, dict[str, str]] | None:
    key = (name or '').strip().upper()
    for idx, row in enumerate(rows):
        for col in name_cols:
            if (row.get(col) or '').strip().upper() == key:
                return idx, row
    return None


def find_conveyor(rows: list[dict[str, str]], name: str) -> dict[str, str] | None:
    hit = find_row_by_name(rows, name, ['IO_Name', 'Name'])
    return hit[1] if hit else None


def find_photoeyes_on_conveyor(rows: list[dict[str, str]], conveyor: str) -> list[dict[str, str]]:
    conv = (conveyor or '').strip().upper()
    hits = []
    for row in rows:
        if (row.get('Type') or '').upper() != 'PHOTOCELL':
            continue
        desc = (row.get('General_Description') or '').upper()
        io_name = (row.get('IO_Name') or '').upper()
        if f' {conv} ' in f' {desc} ' or f'ON {conv}' in desc or conv in io_name:
            hits.append(row)
    return hits


def clone_row(
    template: dict[str, str],
    headers: list[str],
    old_name: str,
    new_name: str,
    name_cols: list[str],
    *,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    machine: str = '',
    io_word: str = '',
    io_bit: str = '',
) -> dict[str, str]:
    row = deepcopy(template)
    for h in headers:
        if h not in row:
            row[h] = ''

    old_u = old_name.upper()
    new_u = new_name.upper()

    for h in headers:
        val = row.get(h, '')
        if not val:
            continue

        if h in name_cols:
            if val.strip().upper() == old_u:
                row[h] = new_name
            continue

        if h in ('IO_Address_Word',) and io_word:
            row[h] = io_word
            continue
        if h in ('IO_Address_Bit',) and io_bit:
            row[h] = io_bit
            continue
        if h == 'Machine_Name' and machine:
            row[h] = machine
            continue

        if h in ('X_cord', 'X_COORD') and offset_x:
            try:
                row[h] = f'{float(val) + offset_x:.3f}'
            except ValueError:
                pass
            continue
        if h in ('Y_cord', 'Y_COORD') and offset_y:
            try:
                row[h] = f'{float(val) + offset_y:.3f}'
            except ValueError:
                pass
            continue

        if old_name in val:
            row[h] = val.replace(old_name, new_name)
        elif old_u in val.upper():
            row[h] = re.sub(re.escape(old_name), new_name, val, flags=re.IGNORECASE)

    return row


def clone_photoeye_row(template: dict[str, str], headers: list[str], **overrides: str) -> dict[str, str]:
    row = deepcopy(template)
    for h in headers:
        if h not in row:
            row[h] = ''
    row.update(overrides)
    return row


def next_spare_io(rows: list[dict[str, str]], bank: int = 104, device_type: str = 'PHOTOCELL') -> tuple[str, str]:
    used_bits: set[tuple[int, int]] = set()
    for row in rows:
        if device_type and (row.get('Type') or '').upper() != device_type.upper():
            continue
        try:
            word = int(float(row.get('IO_Address_Word') or 0))
            bit = int(float(row.get('IO_Address_Bit') or 0))
            if word == bank:
                used_bits.add(bit)
        except ValueError:
            continue
    bit = 0
    while bit in used_bits and bit < 16:
        bit += 1
    if bit >= 16:
        bank += 1
        bit = 0
    return str(bank), str(bit)


def _all_device_names(run_dir: Path) -> set[str]:
    names: set[str] = set()
    for path, _rel in iter_asc_tables(run_dir):
        headers, rows = read_asc(path)
        for row in rows:
            for col in detect_name_columns(headers):
                val = (row.get(col) or '').strip()
                if val and val not in SKIP_NAME_VALUES:
                    names.add(val)
    return names


def derive_linked_name(old_ref: str, template_name: str, new_name: str) -> str:
    if template_name in old_ref:
        return old_ref.replace(template_name, new_name)
    m_old = re.search(r'LANE\s*(\d+)', template_name, re.I)
    m_new = re.search(r'LANE\s*(\d+)', new_name, re.I)
    if m_old and m_new:
        return re.sub(rf'LANE_?{m_old.group(1)}', f'LANE_{m_new.group(1)}', old_ref, flags=re.I)
    if old_ref.upper().startswith('PE') and template_name.upper().startswith('P'):
        return f'PE{new_name}_A'
    return f'{old_ref}_NEW'


def find_linked_names(template_row: dict[str, str], known_names: set[str], template_name: str) -> set[str]:
    linked = set()
    for val in template_row.values():
        v = (val or '').strip()
        if v and v not in SKIP_NAME_VALUES and v in known_names and v.upper() != template_name.upper():
            linked.add(v)
    return linked


def find_related_rows(
    run_dir: Path,
    template_name: str,
    primary_table: str,
    template_row: dict[str, str] | None = None,
    new_name: str = '',
) -> list[tuple[Path, str, dict[str, str], list[str], str, str]]:
    """Find rows to clone: same name elsewhere + rows referenced by template field values."""
    old_u = template_name.upper()
    known = _all_device_names(run_dir)
    target_names: set[str] = {template_name}
    if template_row:
        target_names.update(find_linked_names(template_row, known, template_name))

    name_map = {
        n: derive_linked_name(n, template_name, new_name) if new_name else f'{n}_NEW'
        for n in target_names
    }

    hits: list[tuple[Path, str, dict[str, str], list[str], str, str]] = []
    seen: set[tuple[str, str]] = set()

    for path, rel in iter_asc_tables(run_dir):
        if rel == primary_table:
            continue
        headers, rows = read_asc(path)
        name_cols = detect_name_columns(headers)
        for row in rows:
            for col in name_cols:
                val = (row.get(col) or '').strip()
                if not val or val.upper() not in {n.upper() for n in target_names}:
                    continue
                key = (rel, val.upper())
                if key in seen:
                    break
                seen.add(key)
                hits.append((path, rel, row, name_cols, val, name_map.get(val, derive_linked_name(val, template_name, new_name))))
                break

    return hits