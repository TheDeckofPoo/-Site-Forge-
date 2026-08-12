"""MHS sorter guideline routine builders (Non-Con + AOI Guide + FMS shoe sorter)."""
from __future__ import annotations

import re
from collections import defaultdict

from fortna_device_logic import build_routine_rungs
from fortna_motor_logic import build_mcr_rungs, build_motor_chain_rungs, tag_by_fortna_name, resolve_tag

# Non-Con commissioning constants (encoder pulses; 2 pulses = 1 inch)
PULSES_PER_SOL = 12
PULSES_PER_SET = 48
PULSES_PER_INTMD = 192
DEFAULT_DEBOUNCE_PULSES = 4

_GUIDELINE_REF = (
    'MHS: Non-Con Guidlines.txt, AOI_Guide_2025_JuneWeek2, fms_shoesorter.docx'
)


def _ssv_solenoids(tags: list[dict]) -> list[dict]:
    out = []
    for tag in tags:
        name = (tag.get('fortna_name') or tag.get('tag') or '').upper()
        if name.startswith('SSV') and 'EZPE' not in name and tag.get('type', 'OUT') == 'OUT':
            out.append(tag)
    return sorted(out, key=lambda t: t.get('tag', ''))


def _group_solenoid_sets(solenoids: list[dict]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for sol in solenoids:
        name = sol.get('fortna_name') or sol.get('tag', '')
        base = re.match(r'^(SSV\d+[A-Z])', name.upper())
        key = base.group(1) if base else name[:8]
        groups[key].append(sol)
    return [groups[k] for k in sorted(groups)]


def _tracking_pe_tags(tags: list[dict], area: str | None = None) -> list[dict]:
    pe = []
    for tag in tags:
        if tag.get('device_class') != 'Photoeye':
            continue
        if area and (tag.get('area') or '') != area:
            continue
        if tag.get('type', 'IN') != 'IN':
            continue
        pe.append(tag)
    return pe


def _jam_pe_for_conveyor(conv_tag: dict, tags: list[dict]) -> str | None:
    conv = (conv_tag.get('conveyor') or '').strip().upper()
    if not conv:
        fname = (conv_tag.get('fortna_name') or '').upper()
        m = re.search(r'P(\d{3})', fname)
        conv = f'P{m.group(1)}' if m else ''
    if not conv:
        return None
    num = conv.removeprefix('P')
    lookup = tag_by_fortna_name(tags)
    for candidate in (f'EZPE{num}_P', f'EZPE{num}P', f'PE{num}_P', f'JAMPE{num}'):
        hit = resolve_tag(candidate, lookup)
        if hit:
            return hit
    for tag in tags:
        if tag.get('device_class') != 'Photoeye':
            continue
        if (tag.get('conveyor') or '').upper() == conv:
            name = (tag.get('fortna_name') or '').upper()
            if 'JAM' in name or name.endswith('_P'):
                return tag['tag']
    return None


def build_fms_support_routines(controller: str, tags: list[dict]) -> list[dict]:
    """FMS-only support routines (no Amazon SR_SORTER UDTs)."""
    solenoids = _ssv_solenoids(tags)
    sets = _group_solenoid_sets(solenoids)
    specs: list[dict] = []

    init_rungs: list[tuple[str, str]] = [
        (
            'FMS shoe sorter — create DINT tag rV_F_Preset (75 = min singulator match %)',
            'MOV(75,rV_F_Preset);',
        ),
        (
            'FMS shoe sorter — create DINT tag diPPH_Limit (tune per site)',
            'MOV(170000,diPPH_Limit);',
        ),
        (
            'MHS Non-Con rule of thumb — 12 pulses between solenoids (commissioning note)',
            'NOP();',
        ),
    ]
    specs.append({
        'routine': 'RT_FMS_Initialize',
        'program': 'PG_ORDENCOMM',
        'device_class': 'System',
        'filename': 'RT_FMS_Initialize.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_FMS_Initialize',
            'rungs': init_rungs,
            'reference_note': _GUIDELINE_REF,
        },
    })

    sol_rungs: list[tuple[str, str]] = [
        (
            'MHS Non-Con §4 RT_SOL_IO — solenoids fire from BOOL xSOL_<tag>_Fire (not MCR OTE)',
            'NOP();',
        ),
        (
            'Wire xSOL_*_Fire from RT_Paddle_Divert / aoFMS_Splitter Out_Divert_Enable',
            'NOP();',
        ),
    ]
    for sol in solenoids:
        tag = sol['tag']
        fire = f'xSOL_{tag}_Fire'
        sol_rungs.append((
            f'{tag} — energized on {fire} when FMS enabled',
            f'XIC({fire})XIC(FMS_Enabled)XIO(Out_Inhibit)OTE({tag});',
        ))
        sol_rungs.append((
            f'{tag} — drop when fire bit clears',
            f'XIO({fire})OTU({tag});',
        ))
    for ch, sol_set in enumerate(sets, start=1):
        sol_names = ', '.join(s['tag'] for s in sol_set)
        sol_rungs.append((
            f'Chute {ch:02d} solenoid fault — create BOOL xCH{ch:02d}_SOL_Fault, map in HMI',
            f'XIC(xCH{ch:02d}_SOL_Fault)NOP();',
        ))
        _ = sol_names
    specs.append({
        'routine': 'RT_SOL_IO',
        'program': 'PG_ORDENCOMM',
        'device_class': 'Solenoid',
        'filename': 'RT_SOL_IO.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_SOL_IO',
            'rungs': sol_rungs,
            'reference_note': _GUIDELINE_REF,
        },
    })

    monitor_rungs: list[tuple[str, str]] = [
        (
            'FMS shoe sorter §Anti-Gridlock L2 — ratio exit/induct when induct > 2000 in/hr',
            'GT(adiPPH_Sorter_Induct,2000)DIV(adiPPH_Sorter_Exit,adiPPH_Sorter_Induct,rGL_Ratio);',
        ),
        (
            'Gridlock L2 — set xGL_Lvl2 when ratio >= 0.5',
            'GE(rGL_Ratio,0.5)OTL(xGL_Lvl2)LT(rGL_Ratio,0.5)OTU(xGL_Lvl2);',
        ),
        (
            'FMS shoe sorter §Anti-Gridlock L3 — chute availability below 20%',
            'LT(rChute_Avail_Pct,20)OTL(xGL_Lvl3);',
        ),
        (
            'Flow management — select slower of singulator command vs calculated PPH speed',
            'NOP();',
        ),
    ]
    specs.append({
        'routine': 'RT_MONITOR',
        'program': 'PG_ORDENCOMM',
        'device_class': 'System',
        'filename': 'RT_MONITOR.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_MONITOR',
            'rungs': monitor_rungs,
            'reference_note': _GUIDELINE_REF,
        },
    })

    return specs


def build_fms_control_routine(controller: str, tags: list[dict]) -> dict:
    """Startup/shutdown + FMS enable per MHS Non-Con §2 and FMS shoe sorter."""
    rungs: list[tuple[str, str]] = [
        (
            'MHS Non-Con §2.1 Startup — downstream takeaway first, then sorter, then infeed',
            'NOP();',
        ),
        (
            'Step 1 — verify E-stops clear, no major faults, downstream healthy',
            'XIC(SYS_Ready)NOP();',
        ),
        (
            'Step 2 — start downstream takeaway (zones 8→1 downstream-first)',
            'XIC(Start_Cmd)OTL(Downstream_Running);',
        ),
        (
            'Step 3 — start sorter main drive after downstream running',
            'XIC(Downstream_Running)OTL(Sorter_Main_Run);',
        ),
        (
            'Step 4 — enable tracking and divert logic',
            'XIC(Sorter_Main_Run)OTL(Tracking_Enabled);',
        ),
        (
            'Step 5 — start upstream infeed last',
            'XIC(Tracking_Enabled)OTL(Infeed_Enabled);',
        ),
        (
            'MHS Non-Con §2.2 Shutdown — reverse order: infeed off, clear sorter, stop drive',
            'XIC(Stop_Cmd)OTU(Infeed_Enabled);',
        ),
        (
            'System enable — any zone MCR latched enables FMS',
            'XIC(IO_1MCR1)XIC(IO_2MCR1)XIC(IO_3MCR1)XIC(IO_4MCR1)OTL(FMS_Enabled);',
        ),
        (
            'All zones stopped — drop FMS enable',
            'XIO(IO_1MCR1)XIO(IO_2MCR1)XIO(IO_3MCR1)XIO(IO_4MCR1)OTU(FMS_Enabled);',
        ),
        (
            'Inhibit outputs when FMS disabled — MQJ9 RT_Inhibits pattern',
            'XIO(FMS_Enabled)OTU(Out_Inhibit)TND();',
        ),
        (
            'FMS data reset one-shot — CIP01 RT_FMS_INIT pattern',
            'XIC(FMS_Data_Reset)OTL(FMS_Init_Done);',
        ),
        (
            'Gridlock stops infeed — FMS shoe sorter infeed interlock',
            'XIC(xGL_Lvl2)OTU(Infeed_Enabled)XIC(xGL_Lvl3)OTU(Infeed_Enabled);',
        ),
    ]
    return {
        'routine': 'RT_FMS_Control',
        'program': 'PG_ORDENCOMM',
        'device_class': 'System',
        'filename': 'RT_FMS_Control.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_FMS_Control',
            'rungs': rungs,
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_pe_routine_mhs(
    controller: str,
    tags: list[dict],
    area: str,
    *,
    motor_chains: list[dict],
) -> dict | None:
    area_tags = [t for t in tags if (t.get('area') or '') == area]
    pe_tags = [t for t in area_tags if t.get('device_class') == 'Photoeye']
    if not pe_tags:
        return None
    prog = 'PG_ORDENCOMM' if area == 'ORDENCOMM' else f'PG_{area}'
    safe = re.sub(r'[^A-Z0-9]', '', area.upper())[:10] or 'MAIN'
    rungs = build_routine_rungs(pe_tags, all_tags=tags, motor_chains=motor_chains, io_map=True)
    if not rungs:
        rungs = [
            (
                'FMS PE inputs — map to PointIO aliases; debounce in hardware or timed logic',
                'NOP();',
            ),
        ]
    rungs = [
        ('MHS AOI Guide PE logic — FMS site uses direct PE mapping (no AO_DEBOUNCE AOI)', 'NOP();'),
        *[(c, t) for c, t in rungs if 'SSV' not in t or 'OTE' not in t],
    ]
    return {
        'routine': f'RT_PE_{safe}',
        'program': prog,
        'device_class': 'Photoeye',
        'filename': f'RT_PE_{safe}.L5X',
        'kwargs': {
            'controller': controller,
            'program': prog,
            'routine_name': f'RT_PE_{safe}',
            'rungs': rungs[:120],
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_conveyor_routine_mhs(
    controller: str,
    tags: list[dict],
    area: str,
    *,
    motor_chains: list[dict],
) -> dict | None:
    area_tags = [t for t in tags if (t.get('area') or '') == area]
    conv_tags = [
        t for t in area_tags
        if (t.get('fortna_name') or '').upper().startswith(('SSV', 'EZPWS'))
        or t.get('device_class') == 'Conveyor'
    ]
    if not conv_tags:
        return None
    prog = 'PG_ORDENCOMM' if area == 'ORDENCOMM' else f'PG_{area}'
    safe = re.sub(r'[^A-Z0-9]', '', area.upper())[:10] or 'MAIN'
    lookup = tag_by_fortna_name(tags)
    rungs: list[tuple[str, str]] = [
        (
            'MHS Non-Con §6 — jam PE logic per conveyor; reset per covered chutes',
            'NOP();',
        ),
        (
            'MHS Non-Con §4 — solenoid outputs moved to RT_SOL_IO (no MCR OTE here)',
            'NOP();',
        ),
    ]
    seen_conveyors: set[str] = set()
    for tag in conv_tags:
        fname = (tag.get('fortna_name') or tag.get('tag') or '').upper()
        if fname.startswith('SSV') and 'EZPE' not in fname:
            continue
        hit = build_routine_rungs([tag], all_tags=tags, motor_chains=motor_chains)
        if hit:
            rungs.extend(hit)
        conv_id = tag.get('conveyor') or ''
        if conv_id and conv_id not in seen_conveyors:
            seen_conveyors.add(conv_id)
            jam_pe = _jam_pe_for_conveyor(tag, tags)
            if jam_pe:
                latch = f'Jam_{safe}_{conv_id}'
                rungs.append((
                    f'{conv_id} jam detect — PE {jam_pe} blocks with belt running',
                    f'XIC({jam_pe})XIC({conv_id}_Run)OTL({latch});',
                ))
                rungs.append((
                    f'{conv_id} jam reset — operator reset or downstream clear',
                    f'XIC({conv_id}_Jam_Reset)OTU({latch});',
                ))
                rungs.append((
                    f'{conv_id} — stop/hold conveyor on jam latched',
                    f'XIC({latch})OTU({conv_id}_Run);',
                ))
    if len(rungs) <= 2:
        return None
    return {
        'routine': f'RT_Conveyor_{safe}',
        'program': prog,
        'device_class': 'Conveyor',
        'filename': f'RT_Conveyor_{safe}.L5X',
        'kwargs': {
            'controller': controller,
            'program': prog,
            'routine_name': f'RT_Conveyor_{safe}',
            'rungs': rungs[:100],
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_paddle_divert_routine(controller: str, tags: list[dict]) -> dict | None:
    """FMS paddle divert — Quick divert arm + MGE9 aoFMS_Splitter pattern."""
    solenoids = _ssv_solenoids([t for t in tags if (t.get('area') or '') == 'ORDENCOMM'])
    if not solenoids:
        return None
    sets = _group_solenoid_sets(solenoids)
    rungs: list[tuple[str, str]] = [
        (
            'Quick divert arm setup — aoDivert_Arm per chute in conv_chute routine',
            'NOP();',
        ),
        (
            'MGE9_MCP05 RT_Paddle_Divert — import aoFMS_Splitter AOI before enabling',
            'NOP();',
        ),
    ]
    for ch, sol_set in enumerate(sets, start=1):
        splitter = f'PS01_{ch:02d}_Splitter'
        wake_pe = _tracking_pe_tags(tags, 'ORDENCOMM')
        wake = wake_pe[ch - 1]['tag'] if ch - 1 < len(wake_pe) else 'PE_WakeUp'
        rungs.append((
            f'Chute {ch:02d} — aoFMS_Splitter wake PE {wake}, downstream path enables',
            (
                f'aoFMS_Splitter({splitter},diCH{ch:02d}_Capacity,diCH{ch+1:02d}_Capacity,'
                f'FMS_Seg_Avg)[XIC({wake})OTE({splitter}.Inp_WakeUp_Photoeye),'
                f'XIC(stFMS_MCP.xData_Reset)OTL({splitter}.Inp_Configuration_Reset)];'
            ),
        ))
        for sol in sol_set:
            rungs.append((
                f'Chute {ch:02d} divert arm {sol["tag"]} — enabled only when belt running',
                f'XIC({splitter}.Out_Divert_Enable)XIC(FMS_Enabled)NOP();',
            ))
    return {
        'routine': 'RT_Paddle_Divert',
        'program': 'PG_ORDENCOMM',
        'device_class': 'Splitter',
        'filename': 'RT_Paddle_Divert.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_Paddle_Divert',
            'rungs': rungs,
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_motor_routine_mhs(
    controller: str,
    tags: list[dict],
    motor_chains: list[dict],
) -> dict | None:
    mcr = build_mcr_rungs(tags)
    mc = build_motor_chain_rungs(motor_chains, tags, area=None)
    if not mcr and not mc:
        return None
    rungs: list[tuple[str, str]] = [
        (
            'MHS Non-Con §2.1 — motor chains start downstream-first on Start_Cmd',
            'NOP();',
        ),
    ]
    rungs.extend((c, t) for c, t in (mcr + mc)[:98])
    return {
        'routine': 'RT_Motor_Chains',
        'program': 'PG_ORDENCOMM',
        'device_class': 'MotorChain',
        'filename': 'RT_Motor_Chains.L5X',
        'kwargs': {
            'controller': controller,
            'program': 'PG_ORDENCOMM',
            'routine_name': 'RT_Motor_Chains',
            'rungs': rungs,
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_beacon_routine_mhs(
    controller: str,
    tags: list[dict],
    area: str,
    *,
    motor_chains: list[dict],
) -> dict | None:
    area_tags = [t for t in tags if (t.get('area') or '') == area]
    bc_tags = [t for t in area_tags if t.get('device_class') == 'Beacon']
    if not bc_tags:
        return None
    prog = 'PG_ORDENCOMM' if area == 'ORDENCOMM' else f'PG_{area}'
    safe = re.sub(r'[^A-Z0-9]', '', area.upper())[:10] or 'MAIN'
    rungs = build_routine_rungs(bc_tags, all_tags=tags, motor_chains=motor_chains)
    if not rungs:
        return None
    rungs = [
        ('Quick divert arm §2.1 — beacon alarm on divert arm fault', 'NOP();'),
        *rungs,
    ]
    return {
        'routine': f'RT_Beacon_{safe}',
        'program': prog,
        'device_class': 'Beacon',
        'filename': f'RT_Beacon_{safe}.L5X',
        'kwargs': {
            'controller': controller,
            'program': prog,
            'routine_name': f'RT_Beacon_{safe}',
            'rungs': rungs[:80],
            'reference_note': _GUIDELINE_REF,
        },
    }


def build_mhs_program_specs(scaffold: dict) -> list[dict]:
    """Full MHS-guideline routine set for a Fortna export scaffold."""
    tags = scaffold.get('tags') or []
    motor_chains = scaffold.get('motor_chains') or []
    controller = scaffold.get('system') or 'OReillyDC27_ORDENCOMM'
    specs: list[dict] = []
    specs.extend(build_fms_support_routines(controller, tags))
    specs.append(build_fms_control_routine(controller, tags))
    paddle = build_paddle_divert_routine(controller, tags)
    if paddle:
        specs.append(paddle)
    areas = sorted({t.get('area') for t in tags if t.get('area')})
    for area in areas:
        pe = build_pe_routine_mhs(controller, tags, area, motor_chains=motor_chains)
        if pe:
            specs.append(pe)
        conv = build_conveyor_routine_mhs(controller, tags, area, motor_chains=motor_chains)
        if conv:
            specs.append(conv)
        bc = build_beacon_routine_mhs(controller, tags, area, motor_chains=motor_chains)
        if bc:
            specs.append(bc)
        if area == 'ORDENCOMM':
            motor = build_motor_routine_mhs(controller, tags, motor_chains)
            if motor:
                specs.append(motor)
    return specs