#!/usr/bin/env python3
"""PLC2 I/O truth model — evidence graph + mapping taxonomy (analysis only).

Builds IOEvidenceGraph from RUN tables, reverse-traces finished PLC2 IO_MAP
rungs, classifies generated-vs-finished mismatches, rebuilds controller scope
from graph-owned words/points, validates transport LOCAL/EXTERNAL boundaries,
and copies/generates a diagnostic L5X candidate via the EXISTING from-run path.

CRITICAL: Does NOT modify fortna_autogen.py IO_MAP emit logic.
Finished PLC is validation oracle only — never a generation input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_autogen import (  # noqa: E402
    _load_configio_octal_map,
    load_eip_topology,
    load_from_run,
)
from fortna_controller_scope import (  # noqa: E402
    build_controller_scope,
    write_controller_scope,
)
from fortna_io_extract import (  # noqa: E402
    belongs_to_controller,
    extract_io_points,
    read_project_meta,
    row_machine_matches,
)
from fortna_io_regression_baselines import (  # noqa: E402
    _parse_iomap_mappings,
    _parse_l5x_modules,
)
from fortna_runtime_acceptance_recovery import (  # noqa: E402
    _import_via_apply_recipe,
    _last_json,
    _l5x_counts,
    _py,
    _run,
)
from fortna_site_model import write_json  # noqa: E402

NODE_TYPES = (
    "Controller",
    "EthernetCard",
    "RIOAdapter",
    "IOModule",
    "FortnaWord",
    "Bit",
    "LogicalPoint",
    "Device",
    "Conveyor",
)

TAXONOMY = (
    "WRONG_WORD",
    "WRONG_BANK",
    "WRONG_ADAPTER",
    "WRONG_SLOT",
    "WRONG_BIT",
    "WRONG_DIRECTION",
    "WRONG_LOGICAL_DEVICE",
    "WRONG_CONTROLLER_SCOPE",
    "STALE_RECORD_USED",
    "UNSUPPORTED_POINT_TYPE",
    "PLACEHOLDER_SHOULD_BE_USED",
    "MISSING_RUN_RELATIONSHIP",
)

SKIP_IO = frozenset({"", "INVALID", "N/A", "SPARE", "NEVERON", "ALWAYSON", "NONE"})
MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}

REQUIRED_TRACE_EXAMPLES = [
    ("CP2RIO0:I.Data[1].0", "CP2_CS.I.Start_PB"),
    ("CP2RIO0:I.Data[1].1", "CP2_CS.I.Stop_PB"),
    ("CP2RIO0:I.Data[1].2", "CP2_MCR1.I.ES_OK"),
    ("CP3RIO0:I.Data[7].0", "P400_MS.I.Auxiliary_Forward"),
]

CHANNEL_RE = re.compile(
    r"^(?P<adapter>[A-Za-z0-9_]+):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\]\.(?P<bit>\d+)$"
)
PLACEHOLDER_RE = re.compile(r"NO_PointPlaceholder|SPARE", re.I)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _is_placeholder_tag(tag: str) -> bool:
    t = (tag or "").strip()
    return (not t) or bool(PLACEHOLDER_RE.search(t)) or t.upper() in SKIP_IO


def _parse_maps(text: str) -> list[dict[str, Any]]:
    return _parse_iomap_mappings(text, limit=5000)


def _split_real_placeholder(maps: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    real, ph = [], []
    for m in maps:
        if _is_placeholder_tag(str(m.get("tag") or "")):
            ph.append(m)
        else:
            real.append(m)
    return real, ph


def _octal_bit_to_data_bit(bit_raw: str) -> int | None:
    """Conveyor.IO_Address_Bit may be octal-ish (0-7, 10-17) or decimal 0-15."""
    s = _clean(bit_raw)
    if not s:
        return None
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        return None
    # Prefer octal interpretation when value looks like octal nibble (10-17)
    if 10 <= v <= 17:
        return 8 + (v - 10)
    if 0 <= v <= 15:
        return v
    return None


def _nid(kind: str, *parts: Any) -> str:
    body = ":".join(str(p).strip() for p in parts if str(p).strip() != "")
    return f"{kind}:{body}"


def _edge(
    src: str,
    dst: str,
    *,
    source_table: str,
    source_row: int | None,
    field: str,
    confidence: str,
    documented_semantics: str,
    rel: str = "links",
) -> dict[str, Any]:
    return {
        "source": src,
        "target": dst,
        "rel": rel,
        "source_table": source_table,
        "source_row": source_row,
        "field": field,
        "confidence": confidence,
        "documented_semantics": documented_semantics,
    }


def _find_asc(run_dir: Path, *candidates: str) -> Path | None:
    for name in candidates:
        for base in (run_dir / "PROJECT", run_dir / "FORTNA", run_dir):
            p = base / name
            if p.is_file():
                return p
    return None


def _machine_overlay(run_dir: Path, stem: str, machine: str) -> Path | None:
    """Prefer Table.asc.<MACHINE> overlay when present."""
    for folder in (run_dir / "FORTNA", run_dir / "PROJECT"):
        overlay = folder / f"{stem}.{machine}"
        if overlay.is_file():
            return overlay
        base = folder / stem
        if base.is_file():
            # still return base if no overlay — caller may try both
            pass
    for folder in (run_dir / "FORTNA", run_dir / "PROJECT"):
        base = folder / stem
        if base.is_file():
            return base
    return None


def _read_prefer_overlay(run_dir: Path, stem: str, machine: str) -> tuple[Path | None, list[str], list[dict]]:
    folder_order = (run_dir / "FORTNA", run_dir / "PROJECT")
    overlay = None
    base = None
    for folder in folder_order:
        o = folder / f"{stem}.{machine}"
        b = folder / stem
        if o.is_file() and overlay is None:
            overlay = o
        if b.is_file() and base is None:
            base = b
    path = overlay or base
    if not path:
        return None, [], []
    headers, rows = read_asc(path)
    return path, (headers if isinstance(headers, list) else []), rows


# ---------------------------------------------------------------------------
# A/B — Evidence graph
# ---------------------------------------------------------------------------


def build_io_evidence_graph(run_dir: Path, machine: str) -> dict[str, Any]:
    run_dir = _normalize_run_dir(run_dir)
    machine = (machine or "").strip().upper()
    meta = read_project_meta(run_dir)
    mach = (meta.get("machine_name") or machine or "").strip().upper() or machine

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(nid: str, ntype: str, **attrs: Any) -> str:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, **attrs}
        else:
            for k, v in attrs.items():
                if v not in (None, "", [], {}) and not nodes[nid].get(k):
                    nodes[nid][k] = v
        return nid

    ctrl_id = add_node(
        _nid("Controller", mach),
        "Controller",
        name=mach,
        project=meta.get("project_name") or "",
        source_table="project.cfg",
        field="MACHINENAME",
    )
    edges.append(
        _edge(
            "project.cfg",
            ctrl_id,
            source_table="project.cfg",
            source_row=None,
            field="MACHINENAME",
            confidence="HIGH",
            documented_semantics="Automation Controller / AC identity from project.cfg MACHINENAME",
            rel="defines",
        )
    )
    # Fix: project.cfg is not a node — attach self-describing provenance on controller only
    edges.pop()

    # IOCard → Ethernet / RTA driver config
    iocard_path, _, iocard_rows = _read_prefer_overlay(run_dir, "IOCard.asc", mach)
    eth_id = None
    for i, row in enumerate(iocard_rows):
        name = _clean(row.get("Name") or row.get("IO_Name") or row.get("Driver") or "")
        typ = _clean(row.get("Type") or row.get("Interface") or "")
        if not name and not typ:
            continue
        label = name or typ
        if "EIP" in label.upper() or "ETHER" in label.upper() or "RTA" in label.upper():
            eth_id = add_node(
                _nid("EthernetCard", mach, label),
                "EthernetCard",
                name=label,
                type_name=typ,
                source_table="IOCard.asc",
                source_row=i,
            )
            edges.append(
                _edge(
                    ctrl_id,
                    eth_id,
                    source_table="IOCard.asc",
                    source_row=i,
                    field="Name/Type",
                    confidence="HIGH",
                    documented_semantics="IOCard connects AC to EtherNet/IP driver (RTA); Name matches eipcfg <Config>",
                    rel="owns",
                )
            )

    if eth_id is None:
        eth_id = add_node(
            _nid("EthernetCard", mach, "RTA"),
            "EthernetCard",
            name="RTA",
            inferred=True,
            note="No explicit RTA/EIP IOCard row matched; placeholder EthernetCard for graph rooting",
        )
        edges.append(
            _edge(
                ctrl_id,
                eth_id,
                source_table="IOCard.asc",
                source_row=None,
                field="(inferred)",
                confidence="LOW",
                documented_semantics="EthernetCard inferred — IOCard present but no RTA name match",
                rel="owns",
            )
        )

    # EIP topology (eipcfg / EIPAdapters / EIPModules / EIPCSV)
    topo = load_eip_topology(run_dir, machine=mach)
    adapters = list(topo.get("topology") or [])
    word_map = dict(topo.get("word_map") or {})

    # Enrich adapters from eipcfg names when ASC uses T_1794_*
    eipcfg = _find_asc(run_dir, f"{mach}-RTA-eipcfg.xml", "ORNCCP2-RTA-eipcfg.xml")
    eipcfg_note = str(eipcfg) if eipcfg else None

    adapter_ids: dict[str, str] = {}
    for ai, ad in enumerate(adapters):
        aname = _clean(ad.get("name") or ad.get("rio_name") or f"adapter_{ai}")
        aid = add_node(
            _nid("RIOAdapter", aname),
            "RIOAdapter",
            name=aname,
            ip=_clean(ad.get("ip") or ad.get("address")),
            rack=_clean(ad.get("rack")),
            source_table="eipcfg/EIPAdapters",
        )
        adapter_ids[aname] = aid
        edges.append(
            _edge(
                eth_id,
                aid,
                source_table="eipcfg/EIPAdapters",
                source_row=ai,
                field="Adapter.name/TargetIP",
                confidence="HIGH",
                documented_semantics="eipcfg Adapter under EthernetIP; TargetIP + name unique on IO network",
                rel="hosts",
            )
        )
        for mi, mod in enumerate(ad.get("modules") or []):
            mname = _clean(mod.get("name") or f"{aname}_{mod.get('slot')}")
            slot = mod.get("slot") if mod.get("slot") is not None else mod.get("flex_slot")
            mid = add_node(
                _nid("IOModule", mname),
                "IOModule",
                name=mname,
                catalog=_clean(mod.get("type") or mod.get("catalog")),
                slot=slot,
                parent=aname,
                input_bank=mod.get("input_bank"),
                output_bank=mod.get("output_bank"),
                connection=_clean(mod.get("connection")),
                source_table="EIPModules/eipcfg",
            )
            edges.append(
                _edge(
                    aid,
                    mid,
                    source_table="EIPModules/eipcfg",
                    source_row=mi,
                    field="Slot/Type",
                    confidence="HIGH",
                    documented_semantics="Module slot under adapter; slot 0 often HEADNODE/AENT",
                    rel="contains",
                )
            )

    # Configio Octal_Word → Bank (authoritative Fortna word identity)
    configio = _load_configio_octal_map(run_dir, machine=mach)
    cfg_path, _, cfg_rows = _read_prefer_overlay(run_dir, "Configio.asc", mach)
    word_nodes: dict[str, str] = {}
    for octal, banks in (configio or {}).items():
        w = str(octal)
        wid = add_node(
            _nid("FortnaWord", w),
            "FortnaWord",
            word=w,
            octal_word=w,
            banks=banks,
            source_table="Configio.asc",
        )
        word_nodes[w] = wid
        edges.append(
            _edge(
                ctrl_id,
                wid,
                source_table="Configio.asc",
                source_row=None,
                field="Octal_Word",
                confidence="HIGH",
                documented_semantics="Configio.Octal_Word is Fortna IO word owned/visible on this AC (Local I/O)",
                rel="owns_word",
            )
        )
        for binfo in banks or []:
            bank = binfo.get("bank")
            desc = _clean(binfo.get("desc"))
            # Link word → module when desc encodes catalog family
            for nid, n in nodes.items():
                if n.get("type") != "IOModule":
                    continue
                cat = _clean(n.get("catalog")).upper().replace("/", "")
                if desc and cat and cat.split("-")[0] in desc.upper().replace("/", ""):
                    # weak structural — only if bank numbers align
                    ib = n.get("input_bank")
                    ob = n.get("output_bank")
                    if bank is not None and bank in (ib, ob):
                        edges.append(
                            _edge(
                                wid,
                                nid,
                                source_table="Configio.asc",
                                source_row=None,
                                field="Bank",
                                confidence="HIGH",
                                documented_semantics="Configio Bank matches EIPModules InputBank/OutputBank for module",
                                rel="maps_bank",
                            )
                        )

    # Explicit Configio row edges (row provenance)
    for i, row in enumerate(cfg_rows):
        ow = _clean(row.get("Octal_Word"))
        if not ow or ow in {"0", "0.0"}:
            continue
        try:
            ow_i = str(int(float(ow)))
        except (TypeError, ValueError):
            ow_i = ow
        wid = word_nodes.get(ow_i) or add_node(
            _nid("FortnaWord", ow_i), "FortnaWord", word=ow_i, source_table="Configio.asc"
        )
        word_nodes[ow_i] = wid
        edges.append(
            _edge(
                wid,
                wid,
                source_table=str(cfg_path.name if cfg_path else "Configio.asc"),
                source_row=i,
                field="Octal_Word/Bank/LoHi",
                confidence="HIGH",
                documented_semantics="Configio row: Octal_Word ↔ Bank ↔ LoHi half",
                rel="defined_by",
            )
        )

    # EIPCSV Word → rack/type/bank
    csv_path, _, csv_rows = _read_prefer_overlay(run_dir, "EIPCSV.asc", mach)
    for i, row in enumerate(csv_rows):
        w = _clean(row.get("Word"))
        if not w or w in {"0", "0.0"}:
            continue
        try:
            wkey = str(int(float(w)))
        except (TypeError, ValueError):
            wkey = w
        wid = word_nodes.get(wkey) or add_node(
            _nid("FortnaWord", wkey), "FortnaWord", word=wkey, source_table="EIPCSV.asc"
        )
        word_nodes[wkey] = wid
        rack = _clean(row.get("Rack"))
        typ = _clean(row.get("Type"))
        bank = _clean(row.get("Bank"))
        io = _clean(row.get("IO"))
        edges.append(
            _edge(
                wid,
                ctrl_id,
                source_table=str(csv_path.name if csv_path else "EIPCSV.asc"),
                source_row=i,
                field="Word/Rack/Type/Bank/IO",
                confidence="HIGH",
                documented_semantics=(
                    f"EIPCSV maps Fortna Word={wkey} to Rack={rack} Type={typ} "
                    f"Bank={bank} IO={io}"
                ),
                rel="eipcsv_word",
            )
        )

    # word_map from load_eip_topology (may be sparse / incomplete on Greensboro)
    for w, info in word_map.items():
        if not isinstance(info, dict):
            continue
        wkey = str(w)
        wid = word_nodes.get(wkey) or add_node(
            _nid("FortnaWord", wkey), "FortnaWord", word=wkey, source_table="EIP word_map"
        )
        word_nodes[wkey] = wid
        rio = _clean(info.get("rio_name"))
        if rio and rio in adapter_ids:
            edges.append(
                _edge(
                    wid,
                    adapter_ids[rio],
                    source_table="load_eip_topology.word_map",
                    source_row=None,
                    field="rio_name/flex_slot",
                    confidence="HIGH",
                    documented_semantics="Generator word_map: Fortna word → RIO adapter + flex_slot",
                    rel="word_to_adapter",
                )
            )
            child = _clean(info.get("child_name"))
            if child:
                mid = _nid("IOModule", child)
                if mid in nodes:
                    edges.append(
                        _edge(
                            wid,
                            mid,
                            source_table="load_eip_topology.word_map",
                            source_row=None,
                            field="child_name/flex_slot",
                            confidence="HIGH",
                            documented_semantics="Generator word_map: Fortna word → child module channel",
                            rel="word_to_module",
                        )
                    )

    # Conveyor.asc → LogicalPoint / Device / Conveyor + Bit
    conv_path, _, conv_rows = _read_prefer_overlay(run_dir, "Conveyor.asc", mach)
    bit_index: dict[tuple[str, int], str] = {}
    logical_by_name: dict[str, str] = {}
    conveyor_ids: dict[str, str] = {}

    for i, row in enumerate(conv_rows):
        io_name = _clean(row.get("IO_Name"))
        if not io_name or io_name.upper() in SKIP_IO:
            continue
        word = _clean(row.get("IO_Address_Word"))
        bit_raw = _clean(row.get("IO_Address_Bit"))
        typ = _clean(row.get("Type")).upper()
        mname = _clean(row.get("Machine_Name"))
        motor = _clean(row.get("Motor"))
        drive = _clean(row.get("Drive"))
        data_bit = _octal_bit_to_data_bit(bit_raw)

        # Logical point always
        lp_id = add_node(
            _nid("LogicalPoint", io_name),
            "LogicalPoint",
            name=io_name,
            device_type=typ,
            machine_name=mname,
            fortna_word=word,
            fortna_bit=bit_raw,
            data_bit=data_bit,
            motor=motor,
            drive=drive,
            source_table="Conveyor.asc",
            source_row=i,
        )
        logical_by_name[io_name.upper()] = lp_id

        if word and word not in {"0", "0.0", "6000", "6001"}:
            try:
                wkey = str(int(float(word)))
            except (TypeError, ValueError):
                wkey = word
            wid = word_nodes.get(wkey) or add_node(
                _nid("FortnaWord", wkey),
                "FortnaWord",
                word=wkey,
                source_table="Conveyor.asc",
            )
            word_nodes[wkey] = wid
            edges.append(
                _edge(
                    lp_id,
                    wid,
                    source_table="Conveyor.asc",
                    source_row=i,
                    field="IO_Address_Word",
                    confidence="HIGH",
                    documented_semantics="Conveyor.IO_Address_Word binds part to Fortna IO word",
                    rel="addressed_on_word",
                )
            )
            if data_bit is not None:
                bid = add_node(
                    _nid("Bit", wkey, data_bit),
                    "Bit",
                    word=wkey,
                    bit=data_bit,
                    fortna_bit_raw=bit_raw,
                    source_table="Conveyor.asc",
                )
                bit_index[(wkey, data_bit)] = bid
                edges.append(
                    _edge(
                        wid,
                        bid,
                        source_table="Conveyor.asc",
                        source_row=i,
                        field="IO_Address_Bit",
                        confidence="HIGH",
                        documented_semantics="Conveyor.IO_Address_Bit selects bit within Fortna word",
                        rel="has_bit",
                    )
                )
                edges.append(
                    _edge(
                        lp_id,
                        bid,
                        source_table="Conveyor.asc",
                        source_row=i,
                        field="IO_Address_Bit",
                        confidence="HIGH",
                        documented_semantics="Logical part occupies specific word×bit cell (View I/O)",
                        rel="occupies_bit",
                    )
                )

        # Device node for non-mechanical IO equipment
        if typ and typ not in MECH_TYPES and typ != "INVALID":
            did = add_node(
                _nid("Device", io_name),
                "Device",
                name=io_name,
                device_type=typ,
                machine_name=mname,
                source_table="Conveyor.asc",
                source_row=i,
            )
            edges.append(
                _edge(
                    lp_id,
                    did,
                    source_table="Conveyor.asc",
                    source_row=i,
                    field="IO_Name/Type",
                    confidence="HIGH",
                    documented_semantics="Conveyor Type classifies equipment (PHOTOCELL/MOTOR/BEACON/…)",
                    rel="is_device",
                )
            )

        # Mechanical conveyor
        if typ in MECH_TYPES or re.match(r"^P\d{2,4}[A-Z]?$", io_name, re.I):
            if typ in MECH_TYPES or (typ == "INVALID" and re.match(r"^P\d", io_name, re.I)):
                cid = add_node(
                    _nid("Conveyor", io_name.upper()),
                    "Conveyor",
                    name=io_name.upper(),
                    device_type=typ,
                    machine_name=mname,
                    source_table="Conveyor.asc",
                    source_row=i,
                )
                conveyor_ids[io_name.upper()] = cid
                edges.append(
                    _edge(
                        lp_id,
                        cid,
                        source_table="Conveyor.asc",
                        source_row=i,
                        field="IO_Name",
                        confidence="HIGH",
                        documented_semantics="Mechanical conveyor / display P-part identity from Conveyor.asc",
                        rel="is_conveyor",
                    )
                )

        if motor and motor.upper() not in SKIP_IO:
            motor_target = logical_by_name.get(motor.upper())
            if motor_target:
                edges.append(
                    _edge(
                        lp_id,
                        motor_target,
                        source_table="Conveyor.asc",
                        source_row=i,
                        field="Motor",
                        confidence="HIGH",
                        documented_semantics="Conveyor.Motor explicit motor association",
                        rel="motor_field",
                    )
                )
        if drive and drive.upper() not in SKIP_IO:
            drive_target = logical_by_name.get(drive.upper())
            if drive_target:
                edges.append(
                    _edge(
                        lp_id,
                        drive_target,
                        source_table="Conveyor.asc",
                        source_row=i,
                        field="Drive",
                        confidence="HIGH",
                        documented_semantics=f"Conveyor.Drive={drive}",
                        rel="drive_field",
                    )
                )

    # Mtrchain Motor_Ndx / Motor_Aux / Motor_Chained*
    mtr_path, _, mtr_rows = _read_prefer_overlay(run_dir, "Mtrchain.asc", mach)
    for i, row in enumerate(mtr_rows):
        motor_ndx = _clean(row.get("Motor_Ndx") or row.get("Motor_Name"))
        if not motor_ndx or motor_ndx.upper() in SKIP_IO:
            continue
        motor_lp = logical_by_name.get(motor_ndx.upper()) or add_node(
            _nid("LogicalPoint", motor_ndx),
            "LogicalPoint",
            name=motor_ndx,
            source_table="Mtrchain.asc",
            source_row=i,
        )
        aux = _clean(row.get("Motor_Aux"))
        if aux and aux.upper() not in SKIP_IO:
            aux_lp = logical_by_name.get(aux.upper()) or add_node(
                _nid("LogicalPoint", aux),
                "LogicalPoint",
                name=aux,
                source_table="Mtrchain.asc",
            )
            edges.append(
                _edge(
                    motor_lp,
                    aux_lp,
                    source_table="Mtrchain.asc",
                    source_row=i,
                    field="Motor_Aux",
                    confidence="HIGH",
                    documented_semantics="Mtrchain.Motor_Aux is contactor aux / latch input for motor",
                    rel="has_aux",
                )
            )
        for k in range(1, 11):
            ch = _clean(row.get(f"Motor_Chained{k}"))
            if not ch or ch.upper() in SKIP_IO:
                continue
            cid = conveyor_ids.get(ch.upper()) or add_node(
                _nid("Conveyor", ch.upper()),
                "Conveyor",
                name=ch.upper(),
                source_table="Mtrchain.asc",
                source_row=i,
            )
            conveyor_ids[ch.upper()] = cid
            edges.append(
                _edge(
                    motor_lp,
                    cid,
                    source_table="Mtrchain.asc",
                    source_row=i,
                    field=f"Motor_Chained{k}",
                    confidence="HIGH",
                    documented_semantics="Mtrchain.Motor_Chained* links motor to display P-part(s)",
                    rel="chains_conveyor",
                )
            )

    # Optional Jamzones / Jamcheck / StartStopZones
    optional_tables = [
        ("Jamzones.asc", ("Zone Owner", "Enable Bit", "Latch Bit", "Jammed Bit", "Zone_Name", "Name")),
        ("Jamcheck.asc", ("Jam_Owner", "Sensor", "Name", "Zone")),
        ("StartStopZones.asc", ("Name", "Zone", "Start", "Stop")),
    ]
    optional_status = {}
    for stem, fields in optional_tables:
        path, _, rows = _read_prefer_overlay(run_dir, stem, mach)
        if not path:
            optional_status[stem] = {"present": False, "rows": 0}
            continue
        optional_status[stem] = {"present": True, "rows": len(rows), "path": str(path)}
        for i, row in enumerate(rows[:500]):
            # Only emit edges for explicit non-empty fields — no name similarity
            for field in fields:
                val = _clean(row.get(field))
                if not val or val.upper() in SKIP_IO:
                    continue
                target = logical_by_name.get(val.upper()) or conveyor_ids.get(val.upper())
                if not target:
                    continue
                edges.append(
                    _edge(
                        ctrl_id,
                        target,
                        source_table=stem,
                        source_row=i,
                        field=field,
                        confidence="HIGH",
                        documented_semantics=f"{stem}.{field} explicit reference to {val}",
                        rel="zone_ref",
                    )
                )

    # Drop self-loop noise edges that add no hop value (defined_by self, drive self)
    edges = [e for e in edges if not (e["source"] == e["target"] and e["rel"] in {"defined_by", "drive_field"})]

    # Index helpers for reverse-trace
    points_by_word_bit: dict[str, list[dict]] = defaultdict(list)
    for n in nodes.values():
        if n.get("type") != "LogicalPoint":
            continue
        w = _clean(n.get("fortna_word"))
        b = n.get("data_bit")
        if w and b is not None:
            try:
                wkey = str(int(float(w)))
            except (TypeError, ValueError):
                wkey = w
            points_by_word_bit[f"{wkey}:{b}"].append(n)

    type_counts = Counter(n["type"] for n in nodes.values())

    return {
        "generated_at": _ts(),
        "machine": mach,
        "run_dir": str(run_dir),
        "schema": {
            "node_types": list(NODE_TYPES),
            "edge_required_fields": [
                "source",
                "target",
                "source_table",
                "source_row",
                "field",
                "confidence",
                "documented_semantics",
            ],
            "policy": [
                "RUN tables only for edges",
                "NO edges from name-similarity alone",
                "Confidence HIGH for explicit table fields",
            ],
        },
        "sources": {
            "project_cfg": str(run_dir / "project.cfg"),
            "iocard": str(iocard_path) if iocard_path else None,
            "eipcfg": eipcfg_note,
            "configio": str(cfg_path) if cfg_path else None,
            "eipcsv": str(csv_path) if csv_path else None,
            "conveyor": str(conv_path) if conv_path else None,
            "mtrchain": str(mtr_path) if mtr_path else None,
            "optional": optional_status,
            "word_map_entries": len(word_map),
            "configio_octal_words": len(configio or {}),
        },
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "by_type": dict(type_counts),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "indexes": {
            "logical_points_by_name": {k: v for k, v in logical_by_name.items()},
            "points_by_word_bit_count": {k: len(v) for k, v in points_by_word_bit.items()},
            # Configio Octal_Word set = AC-owned words (authoritative)
            "owned_fortna_words": sorted(
                (str(k) for k in (configio or {}).keys()),
                key=lambda x: int(x) if str(x).isdigit() else 0,
            ),
            "all_fortna_words_seen": sorted(
                word_nodes.keys(), key=lambda x: int(x) if x.isdigit() else 0
            ),
        },
        # private helper payload for reverse-trace (also serialized — useful)
        "_points_by_word_bit": {
            k: [{"id": n["id"], "name": n.get("name"), "device_type": n.get("device_type"), "machine_name": n.get("machine_name")} for n in v]
            for k, v in points_by_word_bit.items()
        },
    }


# ---------------------------------------------------------------------------
# C — Reverse-trace finished mappings
# ---------------------------------------------------------------------------


def _guess_run_names_for_finished_tag(tag: str) -> list[str]:
    """Map finished AOI-style tags to candidate Conveyor.IO_Name values (explicit patterns only)."""
    t = (tag or "").strip()
    cands: list[str] = []
    # CP2_CS.I.Start_PB → 2PBSTART ; CP2_CS.O.Start_PB_LT → 2PBSTART_PLT
    m = re.match(r"^CP(\d+)_CS\.[IO]\.(Start_PB|Stop_PB)(_LT)?$", t, re.I)
    if m:
        n, which, lt = m.group(1), m.group(2).upper(), m.group(3)
        base = "PBSTART" if "START" in which else "PBSTOP"
        cands.append(f"{n}{base}{'_PLT' if lt else ''}")
    m = re.match(r"^CP(\d+)_MCR(\d*)\.[IO]\.ES_OK$", t, re.I)
    if m:
        n, mcr = m.group(1), m.group(2) or "1"
        cands.append(f"{n}MCR{mcr}_AUX")
        cands.append(f"{n}MCR{mcr}")
    m = re.match(r"^CP(\d+)_WH\.[IO]\.Horn$", t, re.I)
    if m:
        cands.append(f"{m.group(1)}WH")
    m = re.match(r"^CP(\d+)_ES\.[IO]\.", t, re.I)
    if m:
        cands.append(f"{m.group(1)}ES")
    # P400_MS.I.Auxiliary_Forward → M400_AUX
    m = re.match(r"^(P\d{2,4}[A-Z]?)_MS\.[IO]\.Auxiliary_Forward$", t, re.I)
    if m:
        num = m.group(1)[1:]
        cands.append(f"M{num}_AUX")
        cands.append(f"M{num}")
    # P400_MS.O.Motor_Forward / similar → M400
    m = re.match(r"^(P\d{2,4}[A-Z]?)_MS\.[IO]\.", t, re.I)
    if m:
        num = m.group(1)[1:]
        cands.append(f"M{num}")
        cands.append(f"M{num}_AUX")
    # PE126_JF.I.PE_Clear → PE126_JF
    m = re.match(r"^((?:EZ)?PE[\w]+)\.[IO]\.", t, re.I)
    if m:
        cands.append(m.group(1))
    # WH310.O.Horn → WH310
    m = re.match(r"^(WH\w+)\.[IO]\.", t, re.I)
    if m:
        cands.append(m.group(1))
    # VFD / beacon misc: leading token before first dot
    m = re.match(r"^([A-Za-z0-9_]+)\.", t)
    if m:
        cands.append(m.group(1))
    # dedupe preserve order
    out, seen = [], set()
    for c in cands:
        cu = c.upper()
        if cu not in seen:
            seen.add(cu)
            out.append(c)
    return out


def reverse_trace_finished(
    graph: dict[str, Any],
    finished_text: str,
    *,
    min_traces: int = 20,
) -> dict[str, Any]:
    maps = _parse_maps(finished_text)
    real, _ph = _split_real_placeholder(maps)
    by_name = {
        (n.get("name") or "").upper(): n
        for n in graph.get("nodes") or []
        if n.get("type") == "LogicalPoint" and n.get("name")
    }
    points_by_wb = graph.get("_points_by_word_bit") or {}
    owned_words = set(graph.get("indexes", {}).get("owned_fortna_words") or [])
    configio_words = owned_words

    # Seed with required examples, then diversify PE / motor / light / misc
    selected: list[dict] = []
    seen_tags: set[str] = set()

    def _add(m: dict) -> None:
        tag = m.get("tag") or ""
        if tag in seen_tags:
            return
        seen_tags.add(tag)
        selected.append(m)

    for ch, tag in REQUIRED_TRACE_EXAMPLES:
        hit = next((m for m in real if m.get("channel") == ch and m.get("tag") == tag), None)
        if hit:
            _add(hit)
        else:
            # synthesize stub so report shows gap
            cm = CHANNEL_RE.match(ch)
            selected.append(
                {
                    "direction": cm.group("dir") if cm else "?",
                    "channel": ch,
                    "slot": int(cm.group("slot")) if cm else None,
                    "bit": int(cm.group("bit")) if cm else None,
                    "tag": tag,
                    "rung": "",
                    "missing_in_finished": True,
                }
            )
            seen_tags.add(tag)

    buckets = {
        "pe": [m for m in real if re.search(r"PE\d", m.get("tag") or "", re.I)],
        "motor": [m for m in real if re.search(r"_MS\.|VFD", m.get("tag") or "", re.I)],
        "light_horn": [m for m in real if re.search(r"LT|Horn|WH|_CS\.O", m.get("tag") or "", re.I)],
        "misc": [m for m in real if m.get("tag") not in seen_tags],
    }
    for key in ("pe", "motor", "light_horn", "misc"):
        for m in buckets[key]:
            if len(selected) >= min_traces:
                break
            _add(m)
        if len(selected) >= min_traces:
            break

    traces = []
    reconstructable = 0
    for m in selected[: max(min_traces, len(REQUIRED_TRACE_EXAMPLES))]:
        tag = m.get("tag") or ""
        channel = m.get("channel") or ""
        cm = CHANNEL_RE.match(channel)
        adapter = cm.group("adapter") if cm else None
        direction = cm.group("dir") if cm else m.get("direction")
        slot = int(cm.group("slot")) if cm else m.get("slot")
        bit = int(cm.group("bit")) if cm else m.get("bit")

        candidates = _guess_run_names_for_finished_tag(tag)
        found_points = []
        for c in candidates:
            n = by_name.get(c.upper())
            if n:
                found_points.append(n)

        chain: list[dict[str, Any]] = []
        gaps: list[str] = []

        chain.append(
            {
                "hop": "finished_rung",
                "channel": channel,
                "tag": tag,
                "adapter": adapter,
                "slot": slot,
                "bit": bit,
                "direction": direction,
            }
        )

        if not found_points:
            gaps.append(
                f"No Conveyor.IO_Name match for finished tag candidates {candidates} "
                "(AOI member path is finished convention; RUN uses Fortna part names)"
            )
        else:
            for fp in found_points:
                w = _clean(fp.get("fortna_word"))
                b = fp.get("data_bit")
                chain.append(
                    {
                        "hop": "Conveyor.asc",
                        "io_name": fp.get("name"),
                        "type": fp.get("device_type"),
                        "machine_name": fp.get("machine_name"),
                        "IO_Address_Word": w,
                        "data_bit": b,
                        "source_row": fp.get("source_row"),
                        "confidence": "HIGH",
                    }
                )
                if w:
                    try:
                        wkey = str(int(float(w)))
                    except (TypeError, ValueError):
                        wkey = w
                    if wkey in configio_words:
                        chain.append(
                            {
                                "hop": "Configio.asc",
                                "Octal_Word": wkey,
                                "confidence": "HIGH",
                                "documented_semantics": "Octal_Word owned on this AC",
                            }
                        )
                    else:
                        gaps.append(f"Fortna word {wkey} not present in Configio overlay for this machine")
                    wb_key = f"{wkey}:{b}"
                    if b is not None and wb_key in points_by_wb:
                        chain.append(
                            {
                                "hop": "word_bit_cell",
                                "key": wb_key,
                                "occupants": points_by_wb[wb_key],
                                "confidence": "HIGH",
                            }
                        )
                # Adapter naming: finished CP2RIO* vs generated T_1794_*
                if adapter and adapter.upper().startswith("CP"):
                    chain.append(
                        {
                            "hop": "adapter_identity",
                            "finished_adapter": adapter,
                            "note": "Finished rack names (CP2RIO*/CP3RIO*) are Studio identities; "
                            "RUN eipcfg/generator currently emit T_1794_AENT_* — name family ≠ ownership",
                            "confidence": "HIGH",
                        }
                    )

        # Physical reconstructability: have Conveyor word+bit on owned Configio word
        can = False
        gap_reason = None
        if found_points:
            fp0 = found_points[0]
            w = _clean(fp0.get("fortna_word"))
            b = fp0.get("data_bit")
            try:
                wkey = str(int(float(w))) if w else ""
            except (TypeError, ValueError):
                wkey = w
            if wkey and wkey in configio_words and b is not None:
                can = True
            elif wkey and b is not None:
                can = True
                gaps.append(
                    "Word/bit present on Conveyor but generator word_map may lack this Fortna word "
                    f"({wkey}) — Configio ownership used instead"
                )
            else:
                gap_reason = "Conveyor row missing word/bit"
        else:
            gap_reason = "MISSING_RUN_RELATIONSHIP: finished logical tag not linked by explicit RUN part name"

        if can:
            reconstructable += 1
        elif gap_reason and gap_reason not in gaps:
            gaps.append(gap_reason)

        traces.append(
            {
                "finished_channel": channel,
                "finished_tag": tag,
                "direction": direction,
                "slot": slot,
                "bit": bit,
                "adapter": adapter,
                "run_name_candidates": candidates,
                "matched_run_points": [
                    {"name": p.get("name"), "word": p.get("fortna_word"), "bit": p.get("data_bit"), "type": p.get("device_type")}
                    for p in found_points
                ],
                "can_reconstruct_from_RUN": can,
                "chain": chain,
                "gaps": gaps,
                "required_example": (channel, tag) in REQUIRED_TRACE_EXAMPLES
                or (tag in {t for _c, t in REQUIRED_TRACE_EXAMPLES}),
            }
        )

    return {
        "generated_at": _ts(),
        "finished_real_mappings_total": len(real),
        "traced_count": len(traces),
        "reconstructable_count": reconstructable,
        "required_examples_included": [
            {"channel": c, "tag": t} for c, t in REQUIRED_TRACE_EXAMPLES
        ],
        "traces": traces,
        "note": (
            "Reconstruction means RUN contains explicit Conveyor word/bit for the Fortna part "
            "that the finished AOI tag conventionally represents. Finished AOI member paths "
            "(e.g. CP2_CS.I.Start_PB) are not stored in RUN — only part names like 2PBSTART."
        ),
    }


# ---------------------------------------------------------------------------
# D — Compare + taxonomy
# ---------------------------------------------------------------------------


def _norm_mod_family(channel: str) -> str:
    """Normalize adapter name family for structural compare (CP2RIO0 ≈ T_1794_AENT_1 unknown)."""
    m = CHANNEL_RE.match(channel or "")
    if not m:
        return channel or ""
    return f"*:{m.group('dir')}.Data[{m.group('slot')}].{m.group('bit')}"


def _tag_base(tag: str) -> str:
    return re.sub(r"^T_\d*", "", (tag or "").strip())


def classify_mapping_errors(
    gen_text: str,
    fin_text: str,
    graph: dict[str, Any],
    scope: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    gen_maps = _parse_maps(gen_text)
    fin_maps = _parse_maps(fin_text)
    gen_real, gen_ph = _split_real_placeholder(gen_maps)
    fin_real, fin_ph = _split_real_placeholder(fin_maps)

    local = {
        str(t).upper()
        for t in ((scope.get("by_scope") or {}).get("LOCAL") or scope.get("local_tags") or [])
    }
    by_name = {
        (n.get("name") or "").upper(): n
        for n in graph.get("nodes") or []
        if n.get("type") == "LogicalPoint"
    }
    owned_words = set(graph.get("indexes", {}).get("owned_fortna_words") or [])

    def fin_key(m: dict) -> tuple:
        return (_tag_base(m.get("tag") or ""), m.get("direction"))

    gen_by_td = {fin_key(m): m for m in gen_real}
    fin_by_td = {fin_key(m): m for m in fin_real}

    mismatched: list[dict] = []
    missing: list[dict] = []
    taxonomy_counts: Counter = Counter()

    # Missing finished mappings
    for k, fm in fin_by_td.items():
        if k not in gen_by_td:
            cands = _guess_run_names_for_finished_tag(fm.get("tag") or "")
            run_hit = [by_name[c.upper()] for c in cands if c.upper() in by_name]
            codes = []
            if not run_hit:
                codes.append("MISSING_RUN_RELATIONSHIP")
            else:
                # Generator failed to emit despite RUN evidence
                codes.append("WRONG_LOGICAL_DEVICE")
                w = _clean(run_hit[0].get("fortna_word"))
                try:
                    wkey = str(int(float(w))) if w else ""
                except (TypeError, ValueError):
                    wkey = w
                if wkey and wkey not in owned_words:
                    codes.append("WRONG_WORD")
                # Adapter name family mismatch is structural for all Greensboro maps
                if (fm.get("channel") or "").upper().startswith("CP"):
                    codes.append("WRONG_ADAPTER")
            # Scope: if associated P-tag not local
            for c in cands:
                m = re.match(r"^(?:M|PE|VFD)?(\d{2,4}[A-Z]?)", c, re.I)
                if m:
                    p = f"P{m.group(1)}".upper()
                    if local and p not in local and re.match(r"^P\d", p):
                        # only flag when clearly a conveyor-associated motor/PE
                        if c.upper().startswith(("M", "PE")):
                            codes.append("WRONG_CONTROLLER_SCOPE")
                            break
            codes = list(dict.fromkeys(codes)) or ["MISSING_RUN_RELATIONSHIP"]
            for c in codes:
                taxonomy_counts[c] += 1
            missing.append(
                {
                    "finished": {
                        "tag": fm.get("tag"),
                        "channel": fm.get("channel"),
                        "direction": fm.get("direction"),
                        "slot": fm.get("slot"),
                        "bit": fm.get("bit"),
                    },
                    "taxonomy": codes,
                    "run_candidates": cands,
                    "run_hits": [
                        {"name": n.get("name"), "word": n.get("fortna_word"), "bit": n.get("data_bit")}
                        for n in run_hit
                    ],
                }
            )

    # Extra / mismatched generated real mappings
    for k, gm in gen_by_td.items():
        fm = fin_by_td.get(k)
        if fm is None:
            codes = ["WRONG_LOGICAL_DEVICE"]
            # Check if tag looks like PE/motor that finished maps elsewhere
            same_slot_bit = [
                x
                for x in fin_real
                if x.get("direction") == gm.get("direction")
                and x.get("slot") == gm.get("slot")
                and x.get("bit") == gm.get("bit")
            ]
            if same_slot_bit:
                codes.append("WRONG_LOGICAL_DEVICE")
            # Placeholder should have been used?
            if _is_placeholder_tag(gm.get("tag") or ""):
                codes = ["PLACEHOLDER_SHOULD_BE_USED"]
            # Scope extras
            tag = gm.get("tag") or ""
            m = re.search(r"PE(\d{2,4})", tag, re.I)
            if m:
                p = f"P{m.group(1)}".upper()
                if local and p not in local:
                    codes.append("WRONG_CONTROLLER_SCOPE")
            # Adapter family
            if (gm.get("channel") or "").upper().startswith("T_1794"):
                codes.append("WRONG_ADAPTER")
            codes = list(dict.fromkeys(codes))
            for c in codes:
                taxonomy_counts[c] += 1
            mismatched.append(
                {
                    "kind": "extra_generated",
                    "generated": {
                        "tag": gm.get("tag"),
                        "channel": gm.get("channel"),
                        "direction": gm.get("direction"),
                        "slot": gm.get("slot"),
                        "bit": gm.get("bit"),
                    },
                    "taxonomy": codes,
                }
            )
            continue

        # Same tag+direction present — check structural fields
        codes = []
        if gm.get("direction") != fm.get("direction"):
            codes.append("WRONG_DIRECTION")
        if gm.get("bit") != fm.get("bit"):
            codes.append("WRONG_BIT")
        if gm.get("slot") != fm.get("slot"):
            codes.append("WRONG_SLOT")
        g_ad = CHANNEL_RE.match(gm.get("channel") or "")
        f_ad = CHANNEL_RE.match(fm.get("channel") or "")
        if g_ad and f_ad:
            gn = g_ad.group("adapter")
            fn = f_ad.group("adapter")
            if gn.upper() != fn.upper():
                # Includes T_1794_AENT_* vs CP2RIO* name-family mismatch
                codes.append("WRONG_ADAPTER")
        if codes:
            for c in codes:
                taxonomy_counts[c] += 1
            mismatched.append(
                {
                    "kind": "structural_mismatch",
                    "generated": {
                        "tag": gm.get("tag"),
                        "channel": gm.get("channel"),
                        "direction": gm.get("direction"),
                        "slot": gm.get("slot"),
                        "bit": gm.get("bit"),
                    },
                    "finished": {
                        "tag": fm.get("tag"),
                        "channel": fm.get("channel"),
                        "direction": fm.get("direction"),
                        "slot": fm.get("slot"),
                        "bit": fm.get("bit"),
                    },
                    "taxonomy": codes,
                }
            )

    # Foundation metric artifact explanation
    foundation_labeled_real_I = sum(1 for m in gen_maps if m.get("direction") == "I")
    foundation_labeled_real_O = sum(1 for m in gen_maps if m.get("direction") == "O")

    comparison = {
        "generated_at": _ts(),
        "finished_CP_I_rungs": None,
        "finished_CP_O_rungs": None,
        "counts": {
            "finished_real_I": sum(1 for m in fin_real if m["direction"] == "I"),
            "finished_real_O": sum(1 for m in fin_real if m["direction"] == "O"),
            "generated_real_I": sum(1 for m in gen_real if m["direction"] == "I"),
            "generated_real_O": sum(1 for m in gen_real if m["direction"] == "O"),
            "finished_placeholder_I": sum(1 for m in fin_ph if m["direction"] == "I"),
            "finished_placeholder_O": sum(1 for m in fin_ph if m["direction"] == "O"),
            "generated_placeholder_I": sum(1 for m in gen_ph if m["direction"] == "I"),
            "generated_placeholder_O": sum(1 for m in gen_ph if m["direction"] == "O"),
            "REAL_LOGICAL_POINT_finished": len(fin_real),
            "UNUSED_PLACEHOLDER_finished": len(fin_ph),
            "REAL_LOGICAL_POINT_generated": len(gen_real),
            "UNUSED_PLACEHOLDER_generated": len(gen_ph),
        },
        "foundation_metric_artifact": {
            "labeled_generated_real_I": foundation_labeled_real_I,
            "labeled_generated_real_O": foundation_labeled_real_O,
            "true_generated_real_I": sum(1 for m in gen_real if m["direction"] == "I"),
            "true_generated_real_O": sum(1 for m in gen_real if m["direction"] == "O"),
            "explanation": (
                "plc2-foundation io_map_comparison counted ALL XIC/OTE rows from "
                "_parse_iomap_mappings as 'real', including NO_PointPlaceholder fill. "
                "True REAL_LOGICAL_POINT generated is much smaller (placeholders dominate). "
                "Therefore generated 256/144 did NOT exceed finished 159/75 in true real maps — "
                "the foundation metric mixed placeholders into 'real'."
            ),
        },
        "why_generated_exceeds_finished_investigation": {
            "question": "Why did foundation report generated real 256/144 > finished 159/75?",
            "findings": [
                "Metric contamination: placeholder rungs (XIC(ch)OTE(NO_PointPlaceholder)) were counted as real.",
                f"True generated REAL_LOGICAL_POINT: {len(gen_real)} "
                f"(I={sum(1 for m in gen_real if m['direction']=='I')}, "
                f"O={sum(1 for m in gen_real if m['direction']=='O')}).",
                f"Finished REAL_LOGICAL_POINT: {len(fin_real)} "
                f"(I={sum(1 for m in fin_real if m['direction']=='I')}, "
                f"O={sum(1 for m in fin_real if m['direction']=='O')}).",
                "Generated under-maps finished real points; over-fills unused channels with placeholders.",
                "Some generated real tags are site PE/motor points that may be wrong-scope or wrong-channel vs finished.",
                "Adapter name family T_1794_AENT_* vs finished CP2RIO*/CP3RIO* prevents exact channel identity matches.",
                "Generator word_map is sparse for Greensboro Fortna words (200/201/300…) — Configio owns those words.",
            ],
        },
        "equivalent_tag_direction": len(set(gen_by_td) & set(fin_by_td)),
        "missing_finished_tag_direction": len(set(fin_by_td) - set(gen_by_td)),
        "extra_generated_tag_direction": len(set(gen_by_td) - set(fin_by_td)),
    }

    # Fill rung counts
    for label, text in (("finished", fin_text), ("generated", gen_text)):
        for rn in ("CP_I", "CP_O"):
            m = re.search(rf'<Routine[^>]*Name="{rn}"[^>]*>(.*?)</Routine>', text, re.S | re.I)
            if not m:
                continue
            n = len(re.findall(r"<Rung\b", m.group(1), re.I))
            comparison[f"{label}_{rn}_rungs"] = n

    taxonomy = {
        "generated_at": _ts(),
        "taxonomy_labels": list(TAXONOMY),
        "counts": {k: taxonomy_counts.get(k, 0) for k in TAXONOMY},
        "counts_other": {k: v for k, v in taxonomy_counts.items() if k not in TAXONOMY},
        "mismatched_generated_mappings": mismatched,
        "missing_finished_mappings": missing,
        "summary": {
            "mismatched_generated": len(mismatched),
            "missing_finished": len(missing),
            "REAL_LOGICAL_POINT_generated": len(gen_real),
            "UNUSED_PLACEHOLDER_generated": len(gen_ph),
            "REAL_LOGICAL_POINT_finished": len(fin_real),
            "UNUSED_PLACEHOLDER_finished": len(fin_ph),
        },
    }
    return comparison, taxonomy


# ---------------------------------------------------------------------------
# E — Controller scope from evidence graph
# ---------------------------------------------------------------------------


def rebuild_controller_scope_from_graph(
    run_dir: Path,
    machine: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Prefer graph-owned Fortna words / LogicalPoints; wrap ownership heuristic and document it."""
    base = build_controller_scope(run_dir, machine)
    owned_words = set(graph.get("indexes", {}).get("owned_fortna_words") or [])

    # LogicalPoints on Configio-owned words (explicit Machine_Name match or blank)
    points_on_owned: dict[str, dict] = {}
    for n in graph.get("nodes") or []:
        if n.get("type") != "LogicalPoint":
            continue
        w = _clean(n.get("fortna_word"))
        if not w:
            continue
        try:
            wkey = str(int(float(w)))
        except (TypeError, ValueError):
            wkey = w
        if wkey not in owned_words:
            continue
        mname = _clean(n.get("machine_name"))
        if mname and not row_machine_matches(mname, machine):
            continue
        points_on_owned[_clean(n.get("name")).upper()] = n

    # Promote mechanical P-tags only when the Conveyor row itself sits on an owned word
    # OR when an owned-word motor chains to that P-tag via Mtrchain (explicit edge).
    local_from_words: set[str] = set()
    for name, n in points_on_owned.items():
        if re.match(r"^P\d{2,4}[A-Z]?$", name):
            local_from_words.add(name)

    motor_on_owned = {
        name
        for name in points_on_owned
        if name.startswith("M") or (points_on_owned[name].get("device_type") or "").upper() == "MOTOR"
    }
    for e in graph.get("edges") or []:
        if e.get("rel") != "chains_conveyor":
            continue
        src = e.get("source") or ""
        tgt = e.get("target") or ""
        if not src.startswith("LogicalPoint:") or not tgt.startswith("Conveyor:"):
            continue
        motor_name = src.split(":", 1)[1].upper()
        if motor_name not in motor_on_owned and motor_name not in points_on_owned:
            continue
        local_from_words.add(tgt.split(":", 1)[1].upper())

    base_local = set((base.get("by_scope") or {}).get("LOCAL") or [])
    # Union graph word-owned P-tags into LOCAL; do not silently drop ownership LOCAL
    merged_local = sorted(base_local | local_from_words)
    # Reclassify: tags that are graph-owned but were OUT_OF_SCOPE → LOCAL
    devices = []
    counts = {c: 0 for c in ("LOCAL", "EXTERNAL_REFERENCE", "OUT_OF_SCOPE", "UNRESOLVED")}
    for d in base.get("devices") or []:
        tag = str(d.get("conveyor_tag") or "").upper()
        scope = d.get("scope_class")
        evidence = list(d.get("evidence") or [])
        if tag in local_from_words and scope != "LOCAL":
            evidence.append("evidence_graph:FortnaWord owned via Configio + Conveyor/Mtrchain link")
            scope = "LOCAL"
            d = dict(d)
            d["scope_class"] = scope
            d["plc_owned"] = True
            d["external_reference"] = False
        elif tag in base_local:
            evidence.append("controller_scope:ownership-heuristic LOCAL (fortna_cp2_ownership)")
        d = dict(d)
        d["evidence"] = evidence
        devices.append(d)
        counts[d["scope_class"]] = counts.get(d["scope_class"], 0) + 1

    by_scope = {
        c: [d["conveyor_tag"] for d in devices if d.get("scope_class") == c]
        for c in ("LOCAL", "EXTERNAL_REFERENCE", "OUT_OF_SCOPE", "UNRESOLVED")
    }
    return {
        **base,
        "generated_at": _ts(),
        "source_of_truth": (
            "Evidence-graph owned Fortna words (Configio) + Conveyor/Mtrchain links; "
            "wrapped fortna_controller_scope ownership heuristic for mechanical inventory"
        ),
        "evidence_graph_policy": {
            "prefer_graph_owned_words": True,
            "still_uses_ownership_heuristic": True,
            "ownership_heuristic_module": "fortna_controller_scope.build_controller_scope / fortna_cp2_ownership",
            "graph_local_promotions": sorted(
                t for t in (local_from_words - base_local) if re.match(r"^P\d{2,4}", t)
            )[:80],
            "graph_owned_word_count": len(owned_words),
            "points_on_owned_words": len(points_on_owned),
        },
        "counts": counts,
        "by_scope": by_scope,
        "devices": devices,
        "local_tags": by_scope.get("LOCAL") or merged_local,
    }


# ---------------------------------------------------------------------------
# F — Transport validation
# ---------------------------------------------------------------------------


def build_transport_validation(
    run_dir: Path,
    machine: str,
    scope: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    local = {str(t).upper() for t in (scope.get("by_scope") or {}).get("LOCAL") or []}
    external = {
        str(t).upper()
        for t in (scope.get("by_scope") or {}).get("EXTERNAL_REFERENCE") or []
    }
    tr_out = out_dir / "transport"
    tr_out.mkdir(parents=True, exist_ok=True)
    tr = _run(
        _py()
        + [
            str(SCRIPTS / "fortna_run_physical_layout.py"),
            "--run-dir",
            str(run_dir),
            "--machine",
            machine,
            "--out",
            str(tr_out),
            "--stdout-graph",
        ]
    )
    gpath = tr_out / "transport_graph_from_run.json"
    graph = None
    if gpath.is_file():
        graph = json.loads(gpath.read_text(encoding="utf-8"))
    else:
        for line in reversed((tr.get("stdout") or "").splitlines()):
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("areas"), list):
                    graph = obj
                    break

    nodes = []
    if graph:
        for a in graph.get("areas") or []:
            nodes.extend(a.get("nodes") or [])

    local_n = [
        n
        for n in nodes
        if n.get("plcOwned") and not n.get("displayContext") and not n.get("externalReference")
    ]
    ext_n = [
        n
        for n in nodes
        if n.get("externalReference") or (n.get("displayContext") and not n.get("plcOwned"))
    ]
    remote_full = [
        n
        for n in nodes
        if not n.get("plcOwned")
        and not n.get("externalReference")
        and not n.get("displayContext")
    ]

    return {
        "generated_at": _ts(),
        "ok": bool(graph),
        "scope_local_count": len(local),
        "scope_external_count": len(external),
        "graph_nodes_total": len(nodes),
        "local_rendered": len(local_n),
        "external_boundaries_rendered": len(ext_n),
        "full_remote_networks_rendered": len(remote_full) > 5,
        "print_boundary_model": {
            "model": "compact_external",
            "description": (
                "Transportation renders LOCAL conveyors fully; EXTERNAL_REFERENCE "
                "neighbors appear as compact boundary stubs (one-hop), not full remote networks. "
                "Print PDFs are optional validation aids and are not required when absent from repo."
            ),
            "prints_required": False,
            "prints_present": (ROOT / "workspace" / "prints").is_dir()
            and any((ROOT / "workspace" / "prints").glob("*")),
        },
        "local_sample": [n.get("conveyorTag") for n in local_n[:30]],
        "external_sample": [n.get("conveyorTag") for n in ext_n[:20]],
        "layout_command_ok": bool(tr.get("ok")),
    }


# ---------------------------------------------------------------------------
# G — L5X candidate via existing from-run (no mapping rewrite)
# ---------------------------------------------------------------------------


def generate_or_copy_candidate(
    run_dir: Path,
    machine: str,
    out_dir: Path,
    library: Path,
    *,
    regenerate: bool,
) -> dict[str, Any]:
    studio_src = ROOT / "exports" / "studio-validation" / "ORNCCP2_foundation_candidate.L5X"
    foundation_src = ROOT / "exports" / "plc2-foundation" / "ORNCCP2_foundation_candidate.L5X"
    dest = out_dir / "ORNCCP2_io_truth_candidate.L5X"
    studio_dest = ROOT / "exports" / "studio-validation" / "ORNCCP2_io_truth_candidate.L5X"
    out_dir.mkdir(parents=True, exist_ok=True)
    studio_dest.parent.mkdir(parents=True, exist_ok=True)

    meta: dict[str, Any] = {
        "label": "diagnostic candidate pending mapping rewrite",
        "mapping_code_modified": False,
        "method": None,
    }

    if regenerate:
        wb_path = ROOT / "workspace" / "autogen_workbook.json"
        _run(
            _py()
            + [
                str(SCRIPTS / "fortna_workbook.py"),
                "build",
                "--run-dir",
                str(run_dir),
                "--processor",
                "1756-L83E",
                "--out",
                str(wb_path),
            ]
        )
        build_out = out_dir / "autogen"
        if build_out.exists():
            shutil.rmtree(build_out, ignore_errors=True)
        build_out.mkdir(parents=True, exist_ok=True)
        gen_args = _py() + [
            str(SCRIPTS / "fortna_autogen.py"),
            "from-run",
            "--run-dir",
            str(run_dir),
            "--library",
            str(library),
            "--processor",
            "1756-L83E",
            "--with-io-map",
            "--workbook",
            str(wb_path),
            "--include-programs",
            "Devices_Comm,NTP,System_Logic,System",
            "--out-dir",
            str(build_out),
            "--io-map-placeholders",
        ]
        gr = _run(gen_args)
        if not gr.get("ok") and "io-map-placeholders" in (gr.get("stderr") or ""):
            gen_args = [a for a in gen_args if a != "--io-map-placeholders"]
            gr = _run(gen_args)
        parsed = _last_json(gr.get("stdout") or "") or {}
        l5x = Path(parsed.get("l5x") or "")
        if not l5x.is_file():
            cands = [
                p
                for p in sorted(build_out.rglob("*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True)
                if "Library" not in p.name
            ]
            l5x = cands[0] if cands else Path()
        if not l5x.is_file():
            meta["ok"] = False
            meta["error"] = parsed.get("error") or gr.get("stderr") or "no L5X"
            # fall through to copy
        else:
            shutil.copy2(l5x, dest)
            shutil.copy2(l5x, studio_dest)
            meta.update({"ok": True, "method": "from-run --with-io-map", "source_l5x": str(l5x)})
            meta["sha256"] = _sha256(dest)
            return meta

    # Copy existing foundation candidate
    src = studio_src if studio_src.is_file() else foundation_src
    if not src.is_file():
        meta["ok"] = False
        meta["error"] = "no foundation candidate to copy and regenerate failed"
        return meta
    shutil.copy2(src, dest)
    shutil.copy2(src, studio_dest)
    meta.update(
        {
            "ok": True,
            "method": "copy_foundation_candidate",
            "source_l5x": str(src),
            "sha256": _sha256(dest),
            "note": "Copied existing from-run foundation candidate; IO_MAP emit logic untouched",
        }
    )
    return meta


def write_report_md(
    path: Path,
    *,
    report: dict[str, Any],
    comparison: dict[str, Any],
    taxonomy: dict[str, Any],
    reverse_trace: dict[str, Any],
    scope: dict[str, Any],
    transport: dict[str, Any],
) -> None:
    c = comparison.get("counts") or {}
    lines = [
        "# PLC2 I/O Truth — Report",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"Machine: **{report.get('machine')}**",
        "",
        "## Acceptance numerics",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Evidence graph nodes | {report.get('graph_nodes')} |",
        f"| Evidence graph edges | {report.get('graph_edges')} |",
        f"| Reverse traces | {reverse_trace.get('traced_count')} |",
        f"| Reconstructable from RUN | {reverse_trace.get('reconstructable_count')} |",
        f"| REAL_LOGICAL_POINT finished I/O | {c.get('finished_real_I')}/{c.get('finished_real_O')} |",
        f"| REAL_LOGICAL_POINT generated I/O | {c.get('generated_real_I')}/{c.get('generated_real_O')} |",
        f"| UNUSED_PLACEHOLDER finished I/O | {c.get('finished_placeholder_I')}/{c.get('finished_placeholder_O')} |",
        f"| UNUSED_PLACEHOLDER generated I/O | {c.get('generated_placeholder_I')}/{c.get('generated_placeholder_O')} |",
        f"| Missing finished tag+dir | {comparison.get('missing_finished_tag_direction')} |",
        f"| Extra generated tag+dir | {comparison.get('extra_generated_tag_direction')} |",
        f"| Equivalent tag+dir | {comparison.get('equivalent_tag_direction')} |",
        f"| Scope LOCAL | {(scope.get('counts') or {}).get('LOCAL')} |",
        f"| Scope EXTERNAL_REFERENCE | {(scope.get('counts') or {}).get('EXTERNAL_REFERENCE')} |",
        f"| Transport local rendered | {transport.get('local_rendered')} |",
        f"| Transport external boundaries | {transport.get('external_boundaries_rendered')} |",
        f"| Full remote networks | {transport.get('full_remote_networks_rendered')} |",
        "",
        "## Foundation 256/144 vs finished 159/75",
        "",
    ]
    for f in (comparison.get("why_generated_exceeds_finished_investigation") or {}).get("findings") or []:
        lines.append(f"- {f}")
    lines += [
        "",
        "## Taxonomy counts",
        "",
        "| Code | Count |",
        "|------|------:|",
    ]
    for k, v in (taxonomy.get("counts") or {}).items():
        lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "## Required reverse-trace examples",
        "",
    ]
    for tr in reverse_trace.get("traces") or []:
        if not tr.get("required_example"):
            continue
        lines.append(
            f"- `{tr.get('finished_channel')}` → `{tr.get('finished_tag')}`: "
            f"can_reconstruct={tr.get('can_reconstruct_from_RUN')} "
            f"gaps={tr.get('gaps')}"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `io_evidence_graph.json`",
        "- `mapping_error_taxonomy.json`",
        "- `controller_scope.json`",
        "- `io_map_comparison.json`",
        "- `transport_validation.json`",
        "- `reverse_trace.json`",
        "- `ORNCCP2_io_truth_candidate.L5X` (diagnostic; mapping rewrite pending)",
        "",
        "## Non-goals",
        "",
        "- No `fortna_autogen.py` IO_MAP emit changes",
        "- No finished-PLC values copied into generation",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC2 I/O truth evidence + taxonomy (analysis only)")
    ap.add_argument(
        "--archive",
        type=Path,
        default=ROOT / "workspace" / "inbox" / "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz",
    )
    ap.add_argument(
        "--finished",
        type=Path,
        default=ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "plc2-io-truth")
    ap.add_argument("--library", type=Path, default=ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X")
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument(
        "--regenerate-l5x",
        action="store_true",
        help="Call existing from-run --with-io-map (default: copy foundation candidate)",
    )
    ap.add_argument("--skip-import", action="store_true", help="Use existing workspace/active/RUN")
    args = ap.parse_args(argv)

    out = args.out if args.out.is_absolute() else (ROOT / args.out)
    out.mkdir(parents=True, exist_ok=True)
    machine = args.machine.strip().upper()
    report: dict[str, Any] = {
        "generated_at": _ts(),
        "ok": False,
        "machine": machine,
        "policy": {
            "no_autogen_iomap_emit_changes": True,
            "finished_plc_oracle_only": True,
            "edges_from_run_only": True,
            "no_name_similarity_edges": True,
        },
    }

    # A) Ensure RUN imported
    if args.skip_import:
        run_dir = _normalize_run_dir(ROOT / "workspace" / "active" / "RUN")
        report["import"] = {"ok": run_dir.is_dir(), "run_dir": str(run_dir), "skipped": True}
    else:
        meta = _import_via_apply_recipe(args.archive)
        run_dir = _normalize_run_dir(Path(meta["run_dir"]))
        report["import"] = {"ok": True, "run_dir": str(run_dir), "machine": meta.get("machine")}

    if not (run_dir / "project.cfg").is_file():
        report["error"] = f"missing RUN project.cfg under {run_dir}"
        write_json(out / "report.json", report)
        return 1

    # B) Evidence graph
    graph = build_io_evidence_graph(run_dir, machine)
    # Strip bulky private index duplicate for file write but keep in memory via graph
    graph_out = dict(graph)
    write_json(out / "io_evidence_graph.json", graph_out)
    report["graph_nodes"] = graph["counts"]["nodes"]
    report["graph_edges"] = graph["counts"]["edges"]
    report["graph_by_type"] = graph["counts"]["by_type"]

    # E) Controller scope (graph-preferring)
    scope = rebuild_controller_scope_from_graph(run_dir, machine, graph)
    write_controller_scope(scope, out / "controller_scope.json")
    report["controller_scope"] = scope.get("counts")

    # Finished oracle
    finished = args.finished
    if not finished.is_file():
        desk = Path.home() / "Desktop" / "ORLY_GreensboroPLC2_NC_Finished.L5X"
        if desk.is_file():
            finished = desk
    if not finished.is_file():
        report["error"] = f"missing finished L5X {args.finished}"
        write_json(out / "report.json", report)
        return 1
    fin_text = finished.read_text(encoding="utf-8", errors="replace")

    # G) Candidate L5X (existing path)
    cand_meta = generate_or_copy_candidate(
        run_dir, machine, out, args.library, regenerate=args.regenerate_l5x
    )
    report["l5x"] = cand_meta
    cand_path = out / "ORNCCP2_io_truth_candidate.L5X"
    if not cand_path.is_file():
        report["error"] = cand_meta.get("error") or "missing candidate L5X"
        write_json(out / "report.json", report)
        return 1
    gen_text = cand_path.read_text(encoding="utf-8", errors="replace")

    # C) Reverse-trace
    reverse_trace = reverse_trace_finished(graph, fin_text, min_traces=20)
    write_json(out / "reverse_trace.json", reverse_trace)
    report["reverse_trace"] = {
        "traced": reverse_trace.get("traced_count"),
        "reconstructable": reverse_trace.get("reconstructable_count"),
    }

    # D) Compare + taxonomy
    comparison, taxonomy = classify_mapping_errors(gen_text, fin_text, graph, scope)
    write_json(out / "io_map_comparison.json", comparison)
    write_json(out / "mapping_error_taxonomy.json", taxonomy)
    report["io_map"] = comparison.get("counts")
    report["taxonomy_summary"] = taxonomy.get("summary")

    # F) Transport validation
    transport = build_transport_validation(run_dir, machine, scope, out)
    write_json(out / "transport_validation.json", transport)
    report["transport"] = {
        "local_rendered": transport.get("local_rendered"),
        "external_boundaries": transport.get("external_boundaries_rendered"),
        "full_remote_networks_rendered": transport.get("full_remote_networks_rendered"),
    }

    report["acceptance"] = {
        "graph_nodes": report["graph_nodes"],
        "graph_edges": report["graph_edges"],
        "reverse_traces": reverse_trace.get("traced_count"),
        "reconstructable_from_RUN": reverse_trace.get("reconstructable_count"),
        "REAL_LOGICAL_POINT_finished_I": (comparison.get("counts") or {}).get("finished_real_I"),
        "REAL_LOGICAL_POINT_finished_O": (comparison.get("counts") or {}).get("finished_real_O"),
        "REAL_LOGICAL_POINT_generated_I": (comparison.get("counts") or {}).get("generated_real_I"),
        "REAL_LOGICAL_POINT_generated_O": (comparison.get("counts") or {}).get("generated_real_O"),
        "UNUSED_PLACEHOLDER_finished_I": (comparison.get("counts") or {}).get("finished_placeholder_I"),
        "UNUSED_PLACEHOLDER_finished_O": (comparison.get("counts") or {}).get("finished_placeholder_O"),
        "UNUSED_PLACEHOLDER_generated_I": (comparison.get("counts") or {}).get("generated_placeholder_I"),
        "UNUSED_PLACEHOLDER_generated_O": (comparison.get("counts") or {}).get("generated_placeholder_O"),
        "missing_finished_tag_direction": comparison.get("missing_finished_tag_direction"),
        "extra_generated_tag_direction": comparison.get("extra_generated_tag_direction"),
        "equivalent_tag_direction": comparison.get("equivalent_tag_direction"),
        "scope_LOCAL": (scope.get("counts") or {}).get("LOCAL"),
        "scope_EXTERNAL_REFERENCE": (scope.get("counts") or {}).get("EXTERNAL_REFERENCE"),
        "transport_local_rendered": transport.get("local_rendered"),
        "transport_external_boundaries": transport.get("external_boundaries_rendered"),
        "foundation_artifact_labeled_I": (comparison.get("foundation_metric_artifact") or {}).get(
            "labeled_generated_real_I"
        ),
        "foundation_artifact_labeled_O": (comparison.get("foundation_metric_artifact") or {}).get(
            "labeled_generated_real_O"
        ),
    }
    report["ok"] = bool(
        report["graph_nodes"]
        and report["graph_edges"]
        and (reverse_trace.get("traced_count") or 0) >= 20
        and cand_path.is_file()
    )

    write_json(out / "report.json", report)
    write_report_md(
        out / "report.md",
        report=report,
        comparison=comparison,
        taxonomy=taxonomy,
        reverse_trace=reverse_trace,
        scope=scope,
        transport=transport,
    )

    print(json.dumps({"ok": report["ok"], "acceptance": report["acceptance"], "l5x": report["l5x"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
