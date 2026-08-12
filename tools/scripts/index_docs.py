#!/usr/bin/env python3
"""Build searchable index from Fortna training documents."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

TASK_KEYWORDS = {
    'photoeye': ['photoeye', 'photo eye', 'photocell', 'pe_', 'pe '],
    'printer': ['print apply', 'pna', 'p&a', 'zebra', 'label', 'printer'],
    'conveyor': ['conveyor', 'belt', 'motor', 'conv'],
    'transfer': ['transfer', 'xfr'],
    'sorter': ['sorter', 'shifter', 'divert'],
    'machine': ['machine', 'msgmap', 'communication'],
    'io': ['configio', 'iocard', 'digital input', 'i/o'],
    'scanner': ['scanner', 'barcode', 'scan'],
}


def docx_text(path: Path, max_paras: int = 400) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml')
        root = ET.fromstring(xml)
        paras = []
        for p in root.iter(f'{W_NS}p'):
            texts = [t.text for t in p.iter(f'{W_NS}t') if t.text]
            if texts:
                paras.append(''.join(texts))
            if len(paras) >= max_paras:
                break
        return '\n'.join(paras)
    except Exception:
        return ''


def infer_tasks(name: str, text: str) -> list[str]:
    blob = f'{name} {text}'.lower()
    tasks = []
    for task, keys in TASK_KEYWORDS.items():
        if any(k in blob for k in keys):
            tasks.append(task)
    return tasks or ['general']


def infer_category(rel: str) -> str:
    parts = Path(rel).parts
    if 'P&A' in parts[0] or 'P&A' in rel:
        return 'Print & Apply'
    if 'FPC Docs 3' in parts:
        return 'FPC Docs 3'
    if 'FPC-Docs 2' in parts or 'FPC Docs 2' in parts:
        return 'FPC Docs 2'
    if 'FPC Documents 1' in parts:
        return 'FPC Documents 1'
    return 'Training'


def build_index(docs_root: Path, out_path: Path) -> dict:
    entries = []
    for path in sorted(docs_root.rglob('*')):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ('.docx', '.doc', '.txt', '.pdf', '.zip'):
            continue
        rel = str(path.relative_to(docs_root)).replace('\\', '/')
        name = path.stem
        text = docx_text(path) if path.suffix.lower() == '.docx' else ''
        summary = re.sub(r'\s+', ' ', text[:600]).strip()
        entries.append({
            'id': re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-'),
            'title': name,
            'file': rel,
            'category': infer_category(rel),
            'extension': path.suffix.lower(),
            'tasks': infer_tasks(name, text),
            'summary': summary,
            'size': path.stat().st_size,
        })
    data = {
        'generated': datetime.now().isoformat(timespec='seconds'),
        'docs_root': str(docs_root),
        'count': len(entries),
        'documents': entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f'Wrote {out_path} ({len(entries)} documents)')
    return data


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument('--docs', default=str(root / 'docs' / 'training'))
    parser.add_argument('--out', default=str(root / 'docs-index' / 'documents.json'))
    args = parser.parse_args()
    build_index(Path(args.docs), Path(args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())