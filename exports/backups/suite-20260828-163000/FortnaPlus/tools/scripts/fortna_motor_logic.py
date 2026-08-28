#!/usr/bin/env python3
"""Generate conveyor motor-chain ladder logic from Fortna Mtrchain.asc + I/O tags."""
from __future__ import annotations

import re
from pathlib import Path

from fortna_asc import read_asc
from fortna_io_extract import _sanitize_tag

_SKIP = frozenset({'', 'INVALID', 'N/A', '~', ' ', 'NONE'})
_CHAIN_COLS = tuple(f'Motor_Chained{i}' for i in range(1, 11))


def extract_motor_chains(run_dir: Path) -> list[dict]:
    path = run_dir / 'FORTNA' / 'Mtrchain.asc'
    if not path.is_file():
        return []

    _, rows = read_asc(path)
    chains: list[dict] = []
    for row in rows:
        motor = (row.get('Motor_Name') or '').strip()
        if not motor or motor.upper() in _SKIP:
            continue
        sections = [
            (row.get(col) or '').strip()
            for col in _CHAIN_COLS
            if (row.get(col) or '').strip().upper() not in _SKIP
        ]
        chains.append({
            'motor': motor,
            'sections': sections,
            'upstream_aux': _clean(row.get('Motor_Aux')),
            'enabled': _clean(row.get('Enabled')),
            'heater': _clean(row.get('Heater Bit')),
            'timer': _clean(row.get('Timer_Name')),
            'run_timer': _clean(row.get('RUN Timer_Name')),
            'latch': _latch_name(row.get('RUN Timer_Name')),
            'horn': _clean(row.get('Horn')),
            'stop_zone': _clean(row.get('Stop Zone')),
        })
    return chains


def _clean(value: str | None) -> str:
    val = (value or '').strip()
    return '' if val.upper() in _SKIP else val


def _latch_name(run_timer: str | None) -> str:
    raw = (run_timer or '').strip()
    if not raw or raw.upper() in _SKIP:
        return ''
    if raw.startswith('tmRUN_'):
        return raw.removeprefix('tmRUN_')
    return ''


def tag_by_fortna_name(tags: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for tag in tags:
        for key in ('fortna_name', 'io_name', 'tag'):
            name = (tag.get(key) or '').strip().upper()
            if name:
                lookup[name] = tag['tag']
    return lookup


def resolve_tag(name: str, lookup: dict[str, str]) -> str | None:
    if not name:
        return None
    return lookup.get(name.strip().upper())


def _motor_zone(motor: str) -> int | None:
    m = re.match(r'^M(\d)', motor.upper())
    if m:
        return int(m.group(1))
    m = re.match(r'^VFD(\d+)', motor.upper())
    if m:
        return int(m.group(1)[0])
    m = re.match(r'^SMC(\d+)', motor.upper())
    if m:
        return int(m.group(1)[0])
    return None


def _mcr_tags_for_zone(zone: int, lookup: dict[str, str]) -> tuple[str | None, str | None]:
    coil = resolve_tag(f'{zone}MCR1', lookup)
    aux = resolve_tag(f'{zone}MCR1_AUX', lookup)
    return coil, aux


def _pb_tags_for_zone(zone: int, lookup: dict[str, str]) -> tuple[str | None, str | None]:
    start = resolve_tag(f'{zone}PBSTART', lookup)
    stop = resolve_tag(f'{zone}PBSTOP', lookup)
    return start, stop


def build_mcr_rungs(tags: list[dict]) -> list[tuple[str, str]]:
    """Start/stop pushbuttons and master control relays (zones 1-4)."""
    lookup = tag_by_fortna_name(tags)
    rungs: list[tuple[str, str]] = []
    for zone in range(1, 5):
        mcr, mcr_aux = _mcr_tags_for_zone(zone, lookup)
        pb_start, pb_stop = _pb_tags_for_zone(zone, lookup)
        if not mcr:
            continue
        label = f'Zone {zone} master control'
        if pb_start and pb_stop:
            rungs.append((
                f'{label} — {zone}PBSTART latches {mcr}, {zone}PBSTOP drops it',
                f'XIC({pb_start})XIO({pb_stop})OTL({mcr});',
            ))
            rungs.append((
                f'{label} — stop pushbutton',
                f'XIC({pb_stop})OTU({mcr});',
            ))
        elif pb_start:
            rungs.append((
                f'{label} — start pushbutton',
                f'XIC({pb_start})OTL({mcr});',
            ))
        if mcr_aux:
            rungs.append((
                f'{label} — MCR aux feedback',
                f'XIC({mcr})OTE({mcr_aux});',
            ))
    return rungs


def build_motor_chain_rungs(
    chains: list[dict],
    tags: list[dict],
    *,
    area: str | None = None,
) -> list[tuple[str, str]]:
    """Motor startup chain rungs from Mtrchain.asc (upstream-aux interlocks + aux mirror)."""
    lookup = tag_by_fortna_name(tags)
    tag_areas = {
        (t.get('fortna_name') or t.get('tag') or '').strip().upper(): t.get('area', '')
        for t in tags
    }
    rungs: list[tuple[str, str]] = []

    for chain in chains:
        motor_name = chain['motor']
        motor_tag = resolve_tag(motor_name, lookup)
        if not motor_tag:
            continue
        if area and tag_areas.get(motor_name.upper(), '') != area:
            continue

        zone = _motor_zone(motor_name)
        mcr_tag = _mcr_tags_for_zone(zone, lookup)[0] if zone else None

        section_txt = ', '.join(chain['sections'][:4]) or 'motor chain'
        comment_parts = [f'{motor_name} drives {section_txt}']

        conditions: list[str] = []
        if mcr_tag:
            conditions.append(f'XIC({mcr_tag})')
        if chain['enabled']:
            enabled_tag = resolve_tag(chain['enabled'], lookup)
            if enabled_tag:
                conditions.append(f'XIC({enabled_tag})')
                comment_parts.append(f'enabled by {chain["enabled"]}')
        if chain['upstream_aux']:
            aux_tag = resolve_tag(chain['upstream_aux'], lookup)
            if aux_tag:
                conditions.append(f'XIC({aux_tag})')
                comment_parts.append(f'after upstream {chain["upstream_aux"]}')

        if conditions:
            rungs.append((
                ' — '.join(comment_parts),
                ''.join(conditions) + f'OTE({motor_tag});',
            ))
        else:
            rungs.append((
                ' — '.join(comment_parts),
                f'OTE({motor_tag});',
            ))

        feedback_name = chain['heater'] or chain['upstream_aux']
        if chain['heater']:
            feedback_name = chain['heater']
            feedback_tag = resolve_tag(feedback_name, lookup)
            if feedback_tag and feedback_tag != motor_tag:
                rungs.append((
                    f'{motor_name} running feedback → {feedback_name}',
                    f'XIC({motor_tag})OTE({feedback_tag});',
                ))

    return rungs


def chains_for_area(chains: list[dict], tags: list[dict], area: str) -> list[dict]:
    lookup = tag_by_fortna_name(tags)
    tag_areas = {
        (t.get('fortna_name') or '').strip().upper(): t.get('area', '')
        for t in tags
    }
    out: list[dict] = []
    for chain in chains:
        motor = chain['motor'].upper()
        if tag_areas.get(motor, '') == area and resolve_tag(motor, lookup):
            out.append(chain)
    return out