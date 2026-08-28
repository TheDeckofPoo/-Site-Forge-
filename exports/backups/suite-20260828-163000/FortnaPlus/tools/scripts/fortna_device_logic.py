#!/usr/bin/env python3
"""Device-class ladder logic from Fortna I/O tags + motor chains."""
from __future__ import annotations

import re

from fortna_motor_logic import resolve_tag, tag_by_fortna_name, _motor_zone, _mcr_tags_for_zone

_PE_PRESENT_RE = re.compile(r'_(P|P1|P2|_P\d*)$', re.I)
_SSV_RE = re.compile(r'^SSV(?:EZ)?PE(\d+)', re.I)
_EZPWS_RE = re.compile(r'^EZPWS(\d+)', re.I)


def _zone_from_bank(fortna_address: str) -> int | None:
    m = re.search(r'Bank(\d+)', fortna_address or '')
    if not m:
        return None
    bank = int(m.group(1))
    if bank >= 100:
        return bank // 100
    return None


def _conveyor_id(tag: dict) -> str:
    conv = (tag.get('conveyor') or '').strip().upper()
    if conv:
        return conv
    fname = (tag.get('fortna_name') or tag.get('tag') or '').upper()
    m = re.search(r'P(\d{3})', fname)
    return f'P{m.group(1)}' if m else ''


def _motor_for_conveyor(conveyor: str, motor_chains: list[dict], lookup: dict[str, str]) -> str | None:
    conv = (conveyor or '').strip().upper()
    if not conv:
        return None
    for chain in motor_chains:
        motor_tag = resolve_tag(chain['motor'], lookup)
        if not motor_tag:
            continue
        sections = {s.upper() for s in chain.get('sections', [])}
        if conv in sections:
            return motor_tag
    return None


def _find_pe_present_for_conveyor(conveyor: str, tags: list[dict]) -> str | None:
    conv = (conveyor or '').strip().upper()
    if not conv:
        return None
    num = conv.removeprefix('P')
    candidates = [
        f'EZPE{num}_P',
        f'EZPE{num}P',
        f'PE{num}_P',
        f'PE{num}P',
    ]
    lookup = tag_by_fortna_name(tags)
    for name in candidates:
        hit = resolve_tag(name, lookup)
        if hit:
            return hit
    for tag in tags:
        if tag.get('device_class') != 'Photoeye':
            continue
        if _conveyor_id(tag) == conv and _PE_PRESENT_RE.search(tag.get('fortna_name', '')):
            return tag['tag']
    return None


def build_tag_rung(
    tag: dict,
    *,
    all_tags: list[dict],
    motor_chains: list[dict],
    io_map: bool = False,
) -> tuple[str, str] | None:
    """Return (comment, ladder_text) or None to skip the tag."""
    tname = tag['tag']
    fname = tag.get('fortna_name', tname)
    faddr = tag.get('fortna_address', '')
    dc = tag.get('device_class', 'IO')
    io_type = tag.get('type') or tag.get('io_type') or 'IN'
    desc = tag.get('description') or fname
    lookup = tag_by_fortna_name(all_tags)
    comment = f'{fname} ({faddr}) - {dc}'

    if dc == 'Motor':
        return None

    if fname.upper().startswith('SSV') or fname.upper().startswith('SSVEZPE'):
        pe = _find_pe_present_for_conveyor(_conveyor_id(tag), all_tags)
        if pe:
            return (
                f'{desc} — hold when product present',
                f'XIC({pe})OTE({tname});',
            )
        motor = _motor_for_conveyor(_conveyor_id(tag), motor_chains, lookup)
        if motor:
            return (
                f'{desc} — energize with section motor',
                f'XIC({motor})OTE({tname});',
            )

    if fname.upper().startswith('EZPWS'):
        motor = _motor_for_conveyor(_conveyor_id(tag), motor_chains, lookup)
        if motor:
            return (
                f'{desc} — EZLogic supply follows motor {motor}',
                f'XIC({motor})OTE({tname});',
            )

    if dc == 'Beacon' and io_type == 'OUT':
        zone = _zone_from_bank(faddr)
        if zone:
            mcr = _mcr_tags_for_zone(zone, lookup)[0]
            if mcr:
                return (
                    f'{desc} — on when zone {zone} MCR energized',
                    f'XIC({mcr})OTE({tname});',
                )

    if dc == 'Photoeye' and io_type == 'IN':
        if _PE_PRESENT_RE.search(fname):
            conv = _conveyor_id(tag)
            if conv:
                num = conv.removeprefix('P')
                for ssv in (f'SSVEZPE{num}_P', f'SSVEZPE{num}_P1', f'SSVEZPE{num}_P2'):
                    ssv_tag = resolve_tag(ssv, lookup)
                    if ssv_tag and ssv_tag != tname:
                        return (
                            f'{desc} — product present drives {ssv}',
                            f'XIC({tname})OTE({ssv_tag});',
                        )
        if io_map:
            return (comment, f'XIC({tname})NOP();')
        return None

    if dc == 'Conveyor' and io_type == 'OUT':
        motor = _motor_for_conveyor(_conveyor_id(tag), motor_chains, lookup)
        if motor and not fname.upper().startswith(('SSV', 'EZPWS')):
            return (
                f'{desc} — conveyor output with motor {motor}',
                f'XIC({motor})OTE({tname});',
            )

    if io_type == 'OUT':
        zone = _zone_from_bank(faddr) or _motor_zone(fname)
        if zone:
            mcr = _mcr_tags_for_zone(zone, lookup)[0]
            if mcr:
                return (
                    f'{desc} — enabled under zone {zone} MCR',
                    f'XIC({mcr})OTE({tname});',
                )
        return (f'{desc} — output active', f'OTE({tname});')

    if io_type == 'IN':
        if io_map:
            return (comment, f'XIC({tname})NOP();')
        return None

    return None


def build_routine_rungs(
    tags: list[dict],
    *,
    all_tags: list[dict],
    motor_chains: list[dict],
    io_map: bool = False,
) -> list[tuple[str, str]]:
    rungs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag['tag']
        if key in seen:
            continue
        seen.add(key)
        hit = build_tag_rung(
            tag,
            all_tags=all_tags,
            motor_chains=motor_chains,
            io_map=io_map,
        )
        if hit:
            rungs.append(hit)
    return rungs