#!/usr/bin/env python3
"""Build FortnaPlus table knowledge base + relationship graph.

Grounded in:
  (1) actual RUN ASC schemas under one or more RUN trees
  (2) optional training-doc inventory (docs-index / FPC_TRAINING_DOCUMENT_INDEX)

SOURCE OF TRUTH: RUN headers = factual schema; training docs = generic semantics.
Never reads finished PLC. No site-specific hardcoding in knowledge rules.

Usage:
  python tools/scripts/fortna_build_table_knowledge.py \\
    --run-dir workspace/cp4-run/RUN --run-dir workspace/active/RUN \\
    --out-kb tools/knowledge/fortnaplus_tables.json \\
    --out-exports exports/fpc-knowledge \\
    --out-docs docs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import NAME_COLUMNS, read_asc  # noqa: E402
from fortna_site_model import (  # noqa: E402
    BLANK,
    SCOPE_BASE_FALLBACK,
    SCOPE_BASE_ONLY,
    SCOPE_HISTORICAL,
    SCOPE_OVERLAY,
    _clean,
    merge_table_rows,
    normalize_name,
    resolve_table_paths,
)

EDGE_EXPLICIT = "EXPLICIT_REFERENCE"
EDGE_DOC = "DOCUMENTED_RELATIONSHIP"
EDGE_DERIVED = "DERIVED_RELATIONSHIP"
EDGE_OPTIONAL = "OPTIONAL_RELATIONSHIP"
EDGE_RUNTIME = "RUNTIME_DATA"

PLACEHOLDER = {"", "N/A", "INVALID", "NONE", "~", "N/A~", "n/a", "Invalid", "RECZERO"}
PLACEHOLDER_PREFIXES = ("===",)


# ---------------------------------------------------------------------------
# Family catalog — purposes / rules grounded in training docs + known ASC use.
# Field lists are candidates; builder intersects with live RUN headers.
# ---------------------------------------------------------------------------

RelSpec = dict[str, Any]


def _rel(
    field: str,
    target: str,
    edge: str,
    *,
    note: str = "",
) -> RelSpec:
    return {
        "field": field,
        "target_table": target,
        "edge_type": edge,
        "note": note,
    }


FAMILY_CATALOG: dict[str, dict[str, Any]] = {
    "Conveyor": {
        "subsystem": "transport_io",
        "purpose": (
            "Primary plant equipment / device table: mechanical conveyors (STRAIGHT/CURVE/BELT/…), "
            "motors, photocells, beacons, and related I/O with geometry and controller ownership."
        ),
        "row_semantics": (
            "One row per named IO_Name. Type discriminates device class (conveyor geometry vs MOTOR vs "
            "PHOTOCELL vs BEACON). Geometry fields apply to mechanical conveyors; Motor / Drive link "
            "ownership; Machine_Name scopes controller."
        ),
        "identity_fields": ["IO_Name"],
        "key_fields": [
            "IO_Name",
            "Type",
            "Motor",
            "Drive",
            "Machine_Name",
            "X_cord",
            "Y_cord",
            "Length",
            "Width",
            "Angle",
            "IO_Address_Word",
            "IO_Address_Bit",
            "In Motor Chain",
        ],
        "relationship_fields": [
            _rel("Motor", "Conveyor", EDGE_EXPLICIT, note="Motor IO_Name in same table"),
            _rel("Drive", "Conveyor", EDGE_EXPLICIT, note="Drive / VFD IO_Name when present"),
            _rel("Machine_Name", "Machine", EDGE_EXPLICIT),
            _rel("In Motor Chain", "Mtrchain", EDGE_DERIVED, note="Flag that motor participates in a chain"),
            _rel("IO_Module_Type", "IOCard", EDGE_OPTIONAL),
            _rel("Type", "convtype", EDGE_OPTIONAL, note="Lookup of conveyor type vocabulary"),
        ],
        "references": ["convtype", "Machine", "Mtrchain", "IOCard"],
        "active_row_rules": [
            "IO_Name present and not placeholder (N/A, INVALID, NONE, ===…===)",
            "Type not INVALID (supporting; mechanical conveyors use CONVEYOR_TYPES)",
        ],
        "inactive_row_rules": [
            "IO_Name blank / placeholder",
            "Type=INVALID with no usable identity",
            "Rows only in old.Conveyor.asc* → HISTORICAL_OR_STALE",
        ],
        "optional_feature_rules": [
            "NoseOver / Infeed_Tangent / Discharge_Tangent are equipment features, not topology FKs",
            "Disable I/O / Overide I/O optional force paths",
        ],
        "controller_scope_behavior": (
            "Prefer Conveyor.asc.<CONTROLLER> overlay when present; else base Conveyor.asc. "
            "Machine_Name further filters ownership; unknown ownership does not delete the row."
        ),
        "generation_implications": [
            "Mechanical conveyors (CONVEYOR_TYPES) feed Transport / area PLC generation when INCLUDED",
            "PHOTOCELL rows seed PE logic; MOTOR/VFD rows seed motor chains and drives",
            "Geometry alone does not prove conveyor successor topology",
        ],
        "doc_keys": [
            "FPC-ConveyorPartsManagement",
            "FPC-Photoeye-Status-Reporting",
            "FPC-Motor-Speed-Control",
        ],
        "confidence": "HIGH",
    },
    "FORTNADT": {
        "subsystem": "io_runtime",
        "purpose": "Runtime bit/force state for View I/O — live forced-on/off and bank state per I/O point.",
        "row_semantics": (
            "Indexed parallel to I/O points (not a named equipment table). Tracks Bits_On_Off, Forced_On/Off, "
            "Inverted, bank, Machine, InOut."
        ),
        "identity_fields": [],
        "key_fields": [
            "Bits_On_Off",
            "Forced_On",
            "Forced_Off",
            "Inverted",
            "HiBank",
            "LoBank",
            "Machine",
            "InOut",
        ],
        "relationship_fields": [
            _rel("Machine", "Machine", EDGE_EXPLICIT),
            _rel("HiBank", "Configio", EDGE_DERIVED, note="Bank coordinates align with Configio"),
            _rel("LoBank", "Configio", EDGE_DERIVED),
        ],
        "references": ["Configio", "Machine"],
        "active_row_rules": ["Row slot corresponding to a configured Configio / Conveyor I/O point"],
        "inactive_row_rules": ["Unused bank slots with no Configio mapping"],
        "optional_feature_rules": ["Forced_On / Forced_Off are operator/debug overrides"],
        "controller_scope_behavior": "Machine column scopes which controller owns the bit image.",
        "generation_implications": [
            "Not a PLC generation source table; HMI/runtime diagnostic only",
        ],
        "doc_keys": ["FPC-The-ViewIO-Screen-and-FORTNADT-Table"],
        "confidence": "HIGH",
    },
    "Configio": {
        "subsystem": "io_map",
        "purpose": "I/O point configuration map: bank/word/bit, direction, interface, and process ownership.",
        "row_semantics": "One configured I/O description per Desc (or bank/word coordinate).",
        "identity_fields": ["Desc"],
        "key_fields": [
            "Desc",
            "Bank",
            "Octal_Word",
            "LoHi",
            "In_Out",
            "I_O_Type",
            "Interface",
            "Process",
            "Status",
        ],
        "relationship_fields": [
            _rel("Interface", "IOCard", EDGE_DOC, note="Interface name ties to IOCard / adapter"),
            _rel("Desc", "Conveyor", EDGE_DERIVED, note="Often matches Conveyor IO_Name"),
            _rel("Process", "Machine", EDGE_OPTIONAL),
        ],
        "references": ["IOCard", "Conveyor", "FORTNADT"],
        "active_row_rules": ["Desc present and not placeholder", "Bank/Octal_Word assigned"],
        "inactive_row_rules": ["Blank Desc with no bank assignment"],
        "optional_feature_rules": ["Granularity / Countdown optional timing"],
        "controller_scope_behavior": "May appear as Configio.asc.<CONTROLLER>; overlay wins collisions.",
        "generation_implications": [
            "Feeds IO_MAP / module addressing when generating PLC I/O",
        ],
        "doc_keys": ["FPC-IOCard-Interfaces", "FPC-FastIO-Configuration"],
        "confidence": "HIGH",
    },
    "IOCard": {
        "subsystem": "io_hardware",
        "purpose": "Physical / logical I/O card and adapter inventory (RIO, EtherNet/IP ABS, Optomux, etc.).",
        "row_semantics": "One row per named card/adapter with Type, ports, machine, and ABS network fields.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Desc",
            "Type",
            "Machine",
            "BasePort",
            "ABS_IP",
            "ABS_HostName",
            "CardNode",
            "Status",
            "Process",
        ],
        "relationship_fields": [
            _rel("Machine", "Machine", EDGE_EXPLICIT),
            _rel("Name", "Configio", EDGE_DOC, note="Configio.Interface / card binding"),
        ],
        "references": ["Machine", "Configio", "ABS_EIP_ADAPTERS", "KTX_RIO_ADAPTERS"],
        "active_row_rules": ["Name present and not placeholder"],
        "inactive_row_rules": ["Blank Name", "historical old.* copies"],
        "optional_feature_rules": [
            "ABS_* fields apply to EtherNet/IP adapters only",
            "ErrorOutput / ErrorACTION / ErrorBIT optional fault signaling",
        ],
        "controller_scope_behavior": "Machine column + optional overlay files scope ownership.",
        "generation_implications": [
            "Defines adapter inventory for I/O mapping; does not invent module catalog entries",
        ],
        "doc_keys": ["FPC-IOCard-Interfaces"],
        "confidence": "HIGH",
    },
    "Jamzones": {
        "subsystem": "area_safety",
        "purpose": "Jam / start-stop zone definitions linking request flags, buttons, and StartStopZones.",
        "row_semantics": "One named Zone Name owning jam latch/jammed bits and optional StartStopZone link.",
        "identity_fields": ["Zone Name"],
        "key_fields": [
            "Zone Name",
            "Start Request Flag",
            "Stop Request Flag",
            "Latch Bit",
            "Jammed Bit",
            "Enable Bit",
            "StartStopZone",
            "Zone Owner ",
            "Start Button",
            "Stop Button",
            "Reset Button",
        ],
        "relationship_fields": [
            _rel("StartStopZone", "StartStopZones", EDGE_EXPLICIT),
            _rel("Zone Name", "Jamcheck", EDGE_DOC, note="Jamcheck.Zone references this name"),
            _rel("Zone Name", "Encoders", EDGE_OPTIONAL, note="Encoders.Jamzone may match zone name"),
        ],
        "references": ["StartStopZones", "Jamcheck", "CombinedJamZones"],
        "active_row_rules": ["Zone Name present and not placeholder"],
        "inactive_row_rules": ["Blank Zone Name", "old.Jamzones.asc* historical"],
        "optional_feature_rules": ["JamEnableDontDelay optional start behavior"],
        "controller_scope_behavior": "Base + optional controller overlay; Zone Owner may name owning process.",
        "generation_implications": [
            "Jam zone membership drives area safety / jam program grouping",
        ],
        "doc_keys": ["FPC-StartStopZones", "FPC-Fulls-Jams-Fulljams", "CombinedJamZones"],
        "confidence": "HIGH",
    },
    "Jamcheck": {
        "subsystem": "area_safety",
        "purpose": "Jam detection points: sensor PE, timer, error, conveyor, and jam zone ownership.",
        "row_semantics": "One jam check per Desc/Sensor_Name linking a PE timer to Conveyor_Name and Zone.",
        "identity_fields": ["Desc", "Sensor_Name"],
        "key_fields": [
            "Desc",
            "Sensor_Name",
            "Timer_Name",
            "Timer_Preset",
            "Error_Name",
            "Conveyor_Name",
            "Zone",
            "Jam_Owner",
            "Motor Under Jam Eye",
        ],
        "relationship_fields": [
            _rel("Sensor_Name", "Conveyor", EDGE_EXPLICIT, note="PHOTOCELL IO_Name"),
            _rel("Conveyor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Zone", "Jamzones", EDGE_EXPLICIT),
            _rel("Motor Under Jam Eye", "Conveyor", EDGE_EXPLICIT, note="Motor IO under jam PE"),
            _rel("Error_Name", "Errors", EDGE_DOC),
        ],
        "references": ["Conveyor", "Jamzones", "Errors"],
        "active_row_rules": [
            "Sensor_Name or Desc present and not placeholder",
            "Timer_Name assigned for armed jam checks",
        ],
        "inactive_row_rules": ["Blank Sensor_Name and Desc", "old.Jamcheck.asc*"],
        "optional_feature_rules": [
            "ClearErrorWithJam / ClearJamSignal / RequireL2Reset optional clear policy",
        ],
        "controller_scope_behavior": "Overlay preferred; Jam_Owner may imply process/controller.",
        "generation_implications": [
            "Generates jam timer / PE monitoring when INCLUDED",
        ],
        "doc_keys": ["FPC-Fulls-Jams-Fulljams", "FPC-StartStopZones"],
        "confidence": "HIGH",
    },
    "Fulljam": {
        "subsystem": "area_safety",
        "purpose": "Full-jam detection: sustained full condition that escalates to jam/error response.",
        "row_semantics": "Named full-jam sensor with set/clear timers, conveyor, motor-under-eye, owner.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Sensor_Name",
            "Enabled",
            "Timer_Name",
            "Clr_Timer_Name",
            "Error_Name",
            "Conveyor_Name",
            "Motor Under Jam Eye",
            "Response IO",
            "Owner",
        ],
        "relationship_fields": [
            _rel("Sensor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Conveyor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor Under Jam Eye", "Conveyor", EDGE_EXPLICIT),
            _rel("Error_Name", "Errors", EDGE_DOC),
            _rel("Response IO", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["Conveyor", "Errors", "Fullline", "Jamcheck"],
        "active_row_rules": ["Name or Sensor_Name present", "Enabled indicates armed when used"],
        "inactive_row_rules": ["Blank Name and Sensor_Name", "old.Fulljam.asc*"],
        "optional_feature_rules": ["DisableBit / Invert / ReSound Horn optional"],
        "controller_scope_behavior": "Owner + overlay scope.",
        "generation_implications": [
            "Full-jam logic pairs with Fullline clear timers; INITERRORS may autogen errors",
        ],
        "doc_keys": [
            "FPC-Fulls-Jams-Fulljams",
            "FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam",
        ],
        "confidence": "HIGH",
    },
    "Fullline": {
        "subsystem": "area_safety",
        "purpose": "Line-full / accumulation full detection with set/clear timers and response I/O.",
        "row_semantics": "One full point per Desc/Sensor_Name; Clr_Timer_* used by sawtooth ReserveTM links.",
        "identity_fields": ["Desc", "Sensor_Name"],
        "key_fields": [
            "Desc",
            "Sensor_Name",
            "Timer_Name",
            "Clr_Timer_Name",
            "Clr_Timer_Preset",
            "Error_Name",
            "Conveyor_Name",
            "Response IO",
            "DontFireResponse",
            "FullClearOutput",
        ],
        "relationship_fields": [
            _rel("Sensor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Conveyor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Clr_Timer_Name", "SawLane", EDGE_DERIVED, note="SawLane.ReserveTM often references tmfc* clear timers"),
            _rel("Error_Name", "Errors", EDGE_DOC),
            _rel("Response IO", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["Conveyor", "Errors", "Fulljam", "SawLane"],
        "active_row_rules": ["Sensor_Name or Desc present", "Timer_Name assigned when armed"],
        "inactive_row_rules": ["Blank identity", "old.Fullline.asc*"],
        "optional_feature_rules": [
            "DontFireResponse / NoGap / FullClear* optional behaviors",
        ],
        "controller_scope_behavior": "Base + overlay; no Greensboro-specific rules.",
        "generation_implications": [
            "Full PE timers feed accumulation and sawtooth reservation timing",
        ],
        "doc_keys": ["FPC-Fulls-Jams-Fulljams"],
        "confidence": "HIGH",
    },
    "Mtrchain": {
        "subsystem": "motor_control",
        "purpose": "Motor startup chains: ordered downstream motors that start after a lead motor/timer.",
        "row_semantics": (
            "One chain head Motor_Name with Motor_Chained1..10 followers, aux, stop zone, heater options."
        ),
        "identity_fields": ["Motor_Name"],
        "key_fields": [
            "Motor_Name",
            "Motor_Ndx",
            "Timer_Name",
            "Timer_Preset",
            "Motor_Chained1",
            "Motor_Chained2",
            "Motor_Aux",
            "Enabled",
            "Stop Zone",
            "Horn",
        ],
        "relationship_fields": [
            _rel("Motor_Name", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained1", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained2", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained3", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained4", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained5", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained6", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained7", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained8", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained9", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Chained10", "Conveyor", EDGE_EXPLICIT),
            _rel("Motor_Aux", "Conveyor", EDGE_EXPLICIT),
            _rel("Stop Zone", "StartStopZones", EDGE_OPTIONAL),
        ],
        "references": ["Conveyor", "StartStopZones"],
        "active_row_rules": ["Motor_Name present and not placeholder"],
        "inactive_row_rules": ["Blank Motor_Name", "old.Mtrchain.asc*"],
        "optional_feature_rules": [
            "Heater Bit / AutoSelectHtr optional",
            "ForceAux / GoUntil optional runtime aids",
        ],
        "controller_scope_behavior": "Overlay wins; chains may cross conveyors owned by one controller.",
        "generation_implications": [
            "Explicit RUN motor topology for startup sequencing — prefer over P-number order",
        ],
        "doc_keys": ["FPC-Motor-Startup-Chains"],
        "confidence": "HIGH",
    },
    "StartStopZones": {
        "subsystem": "area_safety",
        "purpose": "Start/stop zone state machine rows (request flags, owners) referenced by Jamzones.",
        "row_semantics": "One Zone Name with StartReqFlag/StopReqFlag and owner controls.",
        "identity_fields": ["Zone Name"],
        "key_fields": [
            "Zone Name",
            "StartReqFlag",
            "StopReqFlag",
            "State",
            "StartOwnerCtl",
            "StopOwnerCtl",
        ],
        "relationship_fields": [
            _rel("Zone Name", "Jamzones", EDGE_DOC, note="Jamzones.StartStopZone → this name"),
        ],
        "references": ["Jamzones", "ZoneStates"],
        "active_row_rules": ["Zone Name present and not placeholder"],
        "inactive_row_rules": ["Blank Zone Name", "old.StartStopZones.asc*"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Base + overlay; owners name controlling process bits.",
        "generation_implications": [
            "Groups conveyors into start/stop islands for area PLC",
        ],
        "doc_keys": ["FPC-StartStopZones"],
        "confidence": "HIGH",
    },
    "EStop": {
        "subsystem": "area_safety",
        "purpose": "E-stop device / circuit inventory (Desc/Part) with linked Error name.",
        "row_semantics": "One E-stop Desc or Part entry; Error ties to Errors table when populated.",
        "identity_fields": ["Desc", "Part"],
        "key_fields": ["Desc", "Part", "Error"],
        "relationship_fields": [
            _rel("Error", "Errors", EDGE_DOC),
            _rel("Part", "Conveyor", EDGE_OPTIONAL, note="Part may name related equipment when used"),
        ],
        "references": ["Errors"],
        "active_row_rules": ["Desc or Part present and not placeholder"],
        "inactive_row_rules": ["Blank Desc and Part", "old.EStop.asc*"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Present when site configures E-stop table; overlay optional.",
        "generation_implications": [
            "E-stop zones are distinct from StartStop and Jam zones",
            "INITERRORS may autogen related errors",
        ],
        "doc_keys": ["FPC-INITERRORS-Autogeneration-for-Jam-Full-EStop-FullJam"],
        "confidence": "MEDIUM",
    },
    "Convpath": {
        "subsystem": "tracking",
        "purpose": (
            "Carton/piece path tracking slots (Piece + PE_at/PEname). Not a static conveyor successor graph."
        ),
        "row_semantics": (
            "Slot rows for tracked pieces. On many RUNs rows are placeholders (Piece=INVALID, "
            "Input/Output=0) — do not treat as P→P topology."
        ),
        "identity_fields": ["Piece"],
        "key_fields": ["Piece", "Input", "Output", "PE_at", "PEname"],
        "relationship_fields": [
            _rel("PEname", "Conveyor", EDGE_OPTIONAL, note="PE name when populated"),
            _rel("PE_at", "Conveyor", EDGE_OPTIONAL),
            _rel("Input", "Conveyor", EDGE_RUNTIME, note="Runtime path metrics — not static FK"),
            _rel("Output", "Conveyor", EDGE_RUNTIME),
        ],
        "references": ["Conveyor", "Pathsets"],
        "active_row_rules": ["Piece present and not INVALID/placeholder"],
        "inactive_row_rules": ["Piece=INVALID / blank", "Input/Output zero placeholders"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Usually base-only shared tracking table.",
        "generation_implications": [
            "Do not derive Transport topology from Convpath unless active named pieces exist",
            "Physical topology remains engineer/geometry when Convpath unpopulated",
        ],
        "doc_keys": [],
        "confidence": "HIGH",
    },
    "SawLane": {
        "subsystem": "sawtooth",
        "purpose": "Classic sawtooth merge lane configuration (PE, reserve timing, EOW, merge parent).",
        "row_semantics": "One named lane linked to SawMerge with PhotoEyeIO, ReserveTM, slice timing, EOW I/O.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "SawMerge",
            "PhotoEyeIO",
            "DisableIO",
            "SliceSeconds",
            "ReserveWhen",
            "ReserveSeconds",
            "ReserveTM",
            "AllowedToRun",
            "LaneIN",
            "ApproachUP",
            "CollisionUP",
            "pState",
        ],
        "relationship_fields": [
            _rel("SawMerge", "SawMerge", EDGE_EXPLICIT),
            _rel("PhotoEyeIO", "Conveyor", EDGE_EXPLICIT),
            _rel("DisableIO", "Conveyor", EDGE_EXPLICIT),
            _rel("ReserveTM", "Fullline", EDGE_DERIVED, note="Often tmfc* clear timer from Fullline"),
            _rel("LaneIN", "Conveyor", EDGE_OPTIONAL),
            _rel("EndOfWave_PE", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["SawMerge", "Conveyor", "Fullline", "SawState"],
        "active_row_rules": ["Name present and not placeholder", "SawMerge linked for active lanes"],
        "inactive_row_rules": ["Blank Name", "AllowedToRun/explicit disable without merge link"],
        "optional_feature_rules": [
            "EOW_* fields optional End-of-Wave feature",
            "ReserveFLAG / ReserveRATE optional reservation modes",
        ],
        "controller_scope_behavior": "Strongly controller-overlaid (SawLane.asc.<CONTROLLER>).",
        "generation_implications": [
            "Active SawLane+SawMerge → sawtooth_merges discovery; library path still feature-gated",
        ],
        "doc_keys": ["FPC-Merge-Modules", "FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "SawMerge": {
        "subsystem": "sawtooth",
        "purpose": "Classic sawtooth merge collector / boss (motor, reservation input, slice timing).",
        "row_semantics": "One named merge with MotorIO, ReserveIN, LaneEnableDelayTM, live slice status.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "MotorIO",
            "ReserveIN",
            "LaneEnableDelayTM",
            "pSliceSeconds",
            "EOW_RelAllPB",
            "EOW_AutoRel",
        ],
        "relationship_fields": [
            _rel("MotorIO", "Conveyor", EDGE_EXPLICIT),
            _rel("ReserveIN", "Conveyor", EDGE_EXPLICIT),
            _rel("Name", "SawLane", EDGE_DOC, note="SawLane.SawMerge → this Name"),
            _rel("Name", "Sorters", EDGE_OPTIONAL, note="Sorter name may match merge process"),
        ],
        "references": ["SawLane", "Conveyor", "Sorters", "Encoders"],
        "active_row_rules": ["Name present", "MotorIO or ReserveIN assigned for active merges"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["EOW_* optional", "LogMe debug"],
        "controller_scope_behavior": "Controller overlay preferred.",
        "generation_implications": [
            "Collector motor/enable path for sawtooth PLC when generation supported",
        ],
        "doc_keys": ["FPC-Merge-Modules", "FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "HSSawLane": {
        "subsystem": "sawtooth_hs",
        "purpose": "High-speed sawtooth lane FSM: slow/fast/accum I/O, LanePE, opportunistic feed, offsets.",
        "row_semantics": "Named HS lane under HSSawMerge/SawMerge with LanePE and speed action bits.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Enabled",
            "SawMerge",
            "LanePE",
            "LaneSlow",
            "LaneFast",
            "AccumFast",
            "Opportunistic",
            "RunSlowOffset",
            "StopFastOffset",
            "RunFastOffset",
            "pLaneState",
        ],
        "relationship_fields": [
            _rel("SawMerge", "HSSawMerge", EDGE_EXPLICIT),
            _rel("SawMerge", "SawMerge", EDGE_OPTIONAL, note="May reference classic merge name"),
            _rel("LanePE", "Conveyor", EDGE_EXPLICIT),
            _rel("Name", "HSSawParm", EDGE_DOC, note="HSSawParm.SawLane → lane"),
        ],
        "references": ["HSSawMerge", "HSSawParm", "HSSawState", "Conveyor"],
        "active_row_rules": ["Name present", "Enabled when site uses HS module"],
        "inactive_row_rules": ["Blank Name", "Enabled off with no I/O"],
        "optional_feature_rules": [
            "Opportunistic / OpportunSingle optional feed modes",
            "GapError / ResetGapError optional",
        ],
        "controller_scope_behavior": "Often empty of active named rows even when table present.",
        "generation_implications": [
            "HS path is optional upgrade over classic SawLane; only use when active rows exist",
        ],
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "HSSawMerge": {
        "subsystem": "sawtooth_hs",
        "purpose": "High-speed sawtooth merge boss: reservation creation, induct, encoder mode, control machine.",
        "row_semantics": "Named HS merge with MergeRunIO, MergeInduct, TimeBasedEncoder, ControlMachine.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "CreateResrv",
            "MergeRunIO",
            "MergeInduct",
            "TimeBasedEncoder",
            "ControlMachine",
            "pCurrentLane",
        ],
        "relationship_fields": [
            _rel("MergeRunIO", "Conveyor", EDGE_EXPLICIT),
            _rel("MergeInduct", "Conveyor", EDGE_EXPLICIT),
            _rel("ControlMachine", "Machine", EDGE_EXPLICIT),
            _rel("Name", "HSSawLane", EDGE_DOC),
        ],
        "references": ["HSSawLane", "HSSawParm", "Machine", "Conveyor"],
        "active_row_rules": ["Name present and not placeholder"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["pSimOn simulation"],
        "controller_scope_behavior": "ControlMachine scopes HS merge.",
        "generation_implications": [
            "When active, upgrades sawtooth model beyond classic SawMerge fields",
        ],
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "HSSawParm": {
        "subsystem": "sawtooth_hs",
        "purpose": "Per-lane HS parameters: reservation inches/spacing, slug gap, priority, speed, enable.",
        "row_semantics": "Parameter set named and linked to SawLane.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "SawLane",
            "Type",
            "ResrvInches",
            "ResrvTotal",
            "ResrvSpacing",
            "MaxCartonLen",
            "SlugGap",
            "Priority",
            "LaneSpeed",
            "Enable",
        ],
        "relationship_fields": [
            _rel("SawLane", "HSSawLane", EDGE_EXPLICIT),
            _rel("InputSignal", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["HSSawLane", "HSSawMerge"],
        "active_row_rules": ["Name present", "SawLane linked", "Enable when used"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["Override optional"],
        "controller_scope_behavior": "Follows HS lane/merge controller scope.",
        "generation_implications": ["Parameter source for HS reservation geometry"],
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "HSSawState": {
        "subsystem": "sawtooth_hs",
        "purpose": "Lookup vocabulary for HS lane FSM state display names.",
        "row_semantics": "One Name per state label (e.g. Stopped, Wait PE On, Feed Slow).",
        "identity_fields": ["Name"],
        "key_fields": ["Name"],
        "relationship_fields": [
            _rel("Name", "HSSawLane", EDGE_DOC, note="HSSawLane.pLaneState display vocabulary"),
        ],
        "references": ["HSSawLane"],
        "active_row_rules": ["Name present"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Shared lookup; not controller-overlaid typically.",
        "generation_implications": ["Display/state labels only — not control logic source"],
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
        "confidence": "HIGH",
    },
    "HSSawSim": {
        "subsystem": "sawtooth_hs",
        "purpose": "HS sawtooth simulation rows (create boxes, length/gap, force PE).",
        "row_semantics": "Named sim profile linked to SawLane.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "EnableSrt",
            "CreateBoxes",
            "SawLane",
            "LengthInches",
            "GapInches",
        ],
        "relationship_fields": [
            _rel("SawLane", "HSSawLane", EDGE_EXPLICIT),
        ],
        "references": ["HSSawLane"],
        "active_row_rules": ["Name present", "EnableSrt/CreateBoxes when simulating"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Test/sim only.",
        "generation_implications": ["Simulation aid — not production PLC generation input"],
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
        "confidence": "MEDIUM",
    },
    "Merges": {
        "subsystem": "merge_legacy",
        "purpose": "Legacy multi-induct merge table (Presence/Release/Priority/timers per induct 1..5).",
        "row_semantics": "One Merge Table Name with up to five induct columns.",
        "identity_fields": ["Merge Table Name"],
        "key_fields": [
            "Merge Table Name",
            "Valid",
            "Number of Inducts",
            "Operable Input",
            "Presense_Eye1",
            "Release_IO1",
            "Priority1",
        ],
        "relationship_fields": [
            _rel("Presense_Eye1", "Conveyor", EDGE_EXPLICIT),
            _rel("Release_IO1", "Conveyor", EDGE_EXPLICIT),
            _rel("Presense_Eye2", "Conveyor", EDGE_EXPLICIT),
            _rel("Release_IO2", "Conveyor", EDGE_EXPLICIT),
        ],
        "references": ["Conveyor", "SimpleMerge", "MergeBoss"],
        "active_row_rules": ["Merge Table Name present", "Valid when used"],
        "inactive_row_rules": ["Blank name"],
        "optional_feature_rules": ["Inducts 2..5 optional"],
        "controller_scope_behavior": "May be unused when MergeBoss/SimpleMerge preferred.",
        "generation_implications": ["Legacy; prefer MergeBoss/Inputs/Route when present"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "MEDIUM",
    },
    "SimpleMerge": {
        "subsystem": "merge",
        "purpose": "Two-way simple merge: mainline vs lane presence/run with clear timer.",
        "row_semantics": "Named simple merge with MainLineRun, LaneRun, presence eyes, Machine.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "MainLineRun",
            "ClearTimer",
            "MainLinePresence",
            "LanePresence",
            "LaneRun",
            "Machine",
            "NoGap",
        ],
        "relationship_fields": [
            _rel("MainLineRun", "Conveyor", EDGE_EXPLICIT),
            _rel("LaneRun", "Conveyor", EDGE_EXPLICIT),
            _rel("MainLinePresence", "Conveyor", EDGE_EXPLICIT),
            _rel("LanePresence", "Conveyor", EDGE_EXPLICIT),
            _rel("Machine", "Machine", EDGE_EXPLICIT),
        ],
        "references": ["Conveyor", "Machine", "MergeBoss"],
        "active_row_rules": ["Name present", "MainLineRun or LaneRun assigned"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["DontFireLaneRun / NoGap / LaneGoto optional"],
        "controller_scope_behavior": "Machine scopes merge.",
        "generation_implications": ["Simple merge PLC pattern when INCLUDED"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "MergeBoss": {
        "subsystem": "merge",
        "purpose": "Multi-input merge boss: owns inputs count, operable input, switch delay.",
        "row_semantics": "Named boss; MergeInputs rows reference MergeBoss name.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Process",
            "Owner",
            "CurrInput",
            "NumInputs",
            "OperableInput",
            "Valid",
            "SwitchDelayTimer",
        ],
        "relationship_fields": [
            _rel("Name", "MergeInputs", EDGE_DOC),
            _rel("Owner", "Machine", EDGE_OPTIONAL),
        ],
        "references": ["MergeInputs", "MergeRoute"],
        "active_row_rules": ["Name present", "Valid when used"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["IsSwitchDelay optional"],
        "controller_scope_behavior": "Controller overlay common.",
        "generation_implications": ["Parent of MergeInputs/Route graph"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "MergeInputs": {
        "subsystem": "merge",
        "purpose": "Per-input lane under a MergeBoss: presence, release I/O, timers, MergeRoute link.",
        "row_semantics": "Named input with MergeBoss FK and optional MergeRoute.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "MergeBoss",
            "Valid",
            "Index",
            "MergeRoute",
            "Presense",
            "ReleaseIO",
            "Priority",
            "FullClearTimerName",
            "RunTimerName",
        ],
        "relationship_fields": [
            _rel("MergeBoss", "MergeBoss", EDGE_EXPLICIT),
            _rel("MergeRoute", "MergeRoute", EDGE_EXPLICIT),
            _rel("Presense", "Conveyor", EDGE_EXPLICIT),
            _rel("ReleaseIO", "Conveyor", EDGE_EXPLICIT),
            _rel("LaneReadyInput1", "Conveyor", EDGE_OPTIONAL),
            _rel("FullClearTimerName", "Fullline", EDGE_DERIVED),
        ],
        "references": ["MergeBoss", "MergeRoute", "Conveyor"],
        "active_row_rules": ["Name present", "MergeBoss linked", "Valid when used"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": [
            "LaneReadyInput2 / PitchTimer / RouteDisable optional",
        ],
        "controller_scope_behavior": "Follows MergeBoss overlay.",
        "generation_implications": ["Lane arbitration inputs for multi-merge"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "MergeRoute": {
        "subsystem": "merge",
        "purpose": "Merge route binding inputs to outputs with busy/request/priority.",
        "row_semantics": "Named route linking MergeInputs and MergeOutputs signals.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "MergeInputs",
            "MergeOutputs",
            "RouteBusy",
            "RouteRequested",
            "Priority",
        ],
        "relationship_fields": [
            _rel("MergeInputs", "MergeInputs", EDGE_EXPLICIT),
            _rel("MergeOutputs", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["MergeInputs", "MergeBoss"],
        "active_row_rules": ["Name present"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["OutDisabled / InvertOutDisable optional"],
        "controller_scope_behavior": "With merge boss overlay.",
        "generation_implications": ["Route enable graph for multi-merge"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "ZipperMerge": {
        "subsystem": "merge_zipper",
        "purpose": "Zipper merge boss: turn-based reservation, merge motor, speed, induct.",
        "row_semantics": "Named zipper merge with MergeMtr, MergeInduct, MergeRunIO, ControlMachine.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "MergeType",
            "MergeInduct",
            "MergeMtr",
            "MergeRunIO",
            "ControlMachine",
            "MergeSpdFtPerMin",
            "MergeTicksPerInch",
            "GapType",
        ],
        "relationship_fields": [
            _rel("MergeMtr", "Conveyor", EDGE_EXPLICIT),
            _rel("MergeInduct", "Conveyor", EDGE_EXPLICIT),
            _rel("MergeRunIO", "Conveyor", EDGE_EXPLICIT),
            _rel("ControlMachine", "Machine", EDGE_EXPLICIT),
            _rel("Name", "ZipperLane", EDGE_DOC),
        ],
        "references": ["ZipperLane", "Machine", "Conveyor"],
        "active_row_rules": ["Name present"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["CreateResrvFlag / MergeJamUpdate optional"],
        "controller_scope_behavior": "ControlMachine scoped.",
        "generation_implications": [
            "Distinct from sawtooth; only generate when Zipper* rows active",
        ],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "ZipperLane": {
        "subsystem": "merge_zipper",
        "purpose": "Zipper lane under ZipperMerge: turns, reservation lengths, meter/pre speeds, accum I/O.",
        "row_semantics": "Named lane with ZipperMerge FK and extensive meter/merge parameters.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Enabled",
            "ZipperMerge",
            "Turns",
            "ResrvLenInches",
            "MeterSpdFtPerMin",
            "AccumIO",
            "FullClearTimer",
            "PreMergeInduct",
        ],
        "relationship_fields": [
            _rel("ZipperMerge", "ZipperMerge", EDGE_EXPLICIT),
            _rel("AccumIO", "Conveyor", EDGE_EXPLICIT),
            _rel("EnableIO", "Conveyor", EDGE_OPTIONAL),
            _rel("PreMergeInduct", "Conveyor", EDGE_OPTIONAL),
            _rel("FullClearTimer", "Fullline", EDGE_DERIVED),
        ],
        "references": ["ZipperMerge", "Conveyor"],
        "active_row_rules": ["Name present", "Enabled when used", "ZipperMerge linked"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["UseSpdFeedBack / AdjustForDrift optional"],
        "controller_scope_behavior": "Follows ZipperMerge ControlMachine.",
        "generation_implications": ["Lane parameters for zipper merge generation"],
        "doc_keys": ["FPC-Merge-Modules"],
        "confidence": "HIGH",
    },
    "Sorters": {
        "subsystem": "sorter",
        "purpose": "Sorter entity definition: encoder binding, shift buffers, divert enable, machine.",
        "row_semantics": "One Sorter Name with Encoder ioName/tmName and record-range cursors into track tables.",
        "identity_fields": ["Sorter Name"],
        "key_fields": [
            "Sorter Name",
            "Encoder ioName",
            "Encoder tmName",
            "Encoder Type",
            "Machine",
            "Max Cartons",
            "DivertEnableIO",
            "Dump NDX",
            "ShiftOnOff",
        ],
        "relationship_fields": [
            _rel("Encoder ioName", "Encoders", EDGE_EXPLICIT),
            _rel("Machine", "Machine", EDGE_EXPLICIT),
            _rel("DivertEnableIO", "Conveyor", EDGE_OPTIONAL),
            _rel("Sorter Name", "SrtAppControl", EDGE_DOC),
            _rel("Sorter Name", "SrtZoneLane", EDGE_DOC),
        ],
        "references": ["Encoders", "Machine", "SrtAppControl", "SrtTrack1"],
        "active_row_rules": ["Sorter Name present and not placeholder"],
        "inactive_row_rules": ["Blank Sorter Name"],
        "optional_feature_rules": [
            "RecircRate* optional recirculation management",
            "Trig* window/trigger options",
        ],
        "controller_scope_behavior": "Sorters.asc.<CONTROLLER> overlay preferred.",
        "generation_implications": [
            "Discovery-only until complete generic sorter library path exists",
            "Tracking/WCS generation NOT_SUPPORTED by policy",
        ],
        "doc_keys": [
            "FPC-Shifter-And-Sorter-Configuration",
            "FPC-Sorter-Control-Module",
            "FPC-SorterConfigurationChecklist",
        ],
        "confidence": "HIGH",
    },
    "SrtAppControl": {
        "subsystem": "sorter",
        "purpose": "Application sorter control: motor status, host msg tables, scan/data error signaling.",
        "row_semantics": "Named app sorter control with ControlMachine and message table bindings.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "AvailAppSorter",
            "ControlMachine",
            "SorterCnvMtr",
            "CrrMsgTable",
            "DcmMsgTable",
            "ErrConfig",
            "LogLevel",
        ],
        "relationship_fields": [
            _rel("ControlMachine", "Machine", EDGE_EXPLICIT),
            _rel("SorterCnvMtr", "Conveyor", EDGE_EXPLICIT),
            _rel("AvailAppSorter", "Sorters", EDGE_DOC),
            _rel("CrrMsgTable", "MsgMap", EDGE_OPTIONAL),
            _rel("Name", "SrtScanBoss", EDGE_DOC),
        ],
        "references": ["Sorters", "Machine", "SrtScanBoss", "MsgMap"],
        "active_row_rules": ["Name present"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["Second* msg tables optional tandem scanners"],
        "controller_scope_behavior": "ControlMachine scoped.",
        "generation_implications": ["App control skeleton for sorter discovery"],
        "doc_keys": ["FPC-Sorter-Control-Module"],
        "confidence": "HIGH",
    },
    "SrtScanBoss": {
        "subsystem": "sorter",
        "purpose": "Scan zone boss: links AppSorter, ScanZone, update points, lane assignment hooks.",
        "row_semantics": "Named scan boss under an AppSorter with scan error/conflict handling.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "AppSorter",
            "ScanZone",
            "AssignUpdatePt",
            "Lane",
            "SpcLane",
            "TooLateUpdatePt",
            "SendCRRUpdatePt",
        ],
        "relationship_fields": [
            _rel("AppSorter", "SrtAppControl", EDGE_EXPLICIT),
            _rel("ScanZone", "ScnScanZone", EDGE_OPTIONAL),
            _rel("Lane", "SrtZoneLane", EDGE_OPTIONAL),
        ],
        "references": ["SrtAppControl", "SrtZoneLane", "Scanners"],
        "active_row_rules": ["Name present", "AppSorter linked"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["Tote* / SecondScanZone optional"],
        "controller_scope_behavior": "Follows app sorter machine.",
        "generation_implications": ["Scan assignment points — not divert IO map"],
        "doc_keys": ["FPC-Sorter-Control-Module", "FPC-Scanner-Control-Configuration"],
        "confidence": "HIGH",
    },
    "SrtZoneLane": {
        "subsystem": "sorter",
        "purpose": "Host zone → sorter lane assignment with full-clear timer and enable signals.",
        "row_semantics": "Named zone-lane row under AppSorter with HostZone and Lane.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Enabled",
            "AppSorter",
            "Lane",
            "HostZone",
            "FullClearTimer",
            "LaneEnableSignal",
            "RndRobinEnabled",
        ],
        "relationship_fields": [
            _rel("AppSorter", "SrtAppControl", EDGE_EXPLICIT),
            _rel("FullClearTimer", "Fullline", EDGE_DERIVED),
            _rel("LaneEnableSignal", "Conveyor", EDGE_OPTIONAL),
            _rel("Name", "SrtTrack1", EDGE_RUNTIME, note="SrtTrack*.SrtZoneLaneRec runtime link"),
        ],
        "references": ["SrtAppControl", "Sorters", "Fullline"],
        "active_row_rules": ["Name present", "Enabled when assigned"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": [
            "AssignIfFull / AssignLaneZero / TwoSidedShoe optional policies",
        ],
        "controller_scope_behavior": "App sorter machine scope.",
        "generation_implications": [
            "Static lane assignment; divert IO still engineer-required",
        ],
        "doc_keys": ["FPC-Sorter-Control-Module"],
        "confidence": "HIGH",
    },
    "SrtTrack": {
        "subsystem": "sorter_runtime",
        "purpose": (
            "Runtime carton tracking slot tables SrtTrack1..5 — confirm scan, host zone, sorter lane, "
            "dimensions. Not static topology."
        ),
        "row_semantics": (
            "Named-slot or indexed carton records with ConfirmScan, ScanZoneID, SorterLane, SrtAppRec. "
            "Numeric empty slots are inactive."
        ),
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "ConfirmScan",
            "HostZone",
            "ScanZoneID",
            "SorterLane",
            "SrtAppRec",
            "SrtZoneLaneRec",
            "Status",
            "Length",
            "Width",
            "Height",
        ],
        "relationship_fields": [
            _rel("SrtAppRec", "SrtAppControl", EDGE_RUNTIME),
            _rel("SrtZoneLaneRec", "SrtZoneLane", EDGE_RUNTIME),
            _rel("SorterLane", "SrtZoneLane", EDGE_RUNTIME),
            _rel("ScanZoneID", "SrtScanBoss", EDGE_RUNTIME),
        ],
        "references": ["SrtAppControl", "SrtZoneLane", "SrtScanBoss", "MsgTrack"],
        "active_row_rules": [
            "Name present and not placeholder",
            "ConfirmScan / HostZone / ScanZoneID evidence of live track slot",
        ],
        "inactive_row_rules": ["Blank/numeric-only empty slots"],
        "optional_feature_rules": ["P&A verify fields (VerRF/VerSKU) optional"],
        "controller_scope_behavior": "Shared runtime menus; sized per sorter docs.",
        "generation_implications": [
            "Proves tracking activity; does NOT define divert output maps",
            "classification=RUNTIME_DATA",
        ],
        "doc_keys": [
            "FPC-Sorter-Control-Module",
            "FPC-Scanner-Control-Configuration",
        ],
        "table_globs": ["SrtTrack1.asc", "SrtTrack2.asc", "SrtTrack3.asc", "SrtTrack4.asc", "SrtTrack5.asc"],
        "confidence": "HIGH",
    },
    "XfrTrack": {
        "subsystem": "transfer_runtime",
        "purpose": "Transfer tracking runtime slots (scan confirm, route boss/table rec, XfrZoneID).",
        "row_semantics": "Parallel to SrtTrack for transfer path; RouteBossRec / RouteTableRec runtime links.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "ConfirmScan",
            "HostZone",
            "RouteBossRec",
            "RouteTableRec",
            "XfrZoneID",
            "SorterLane",
            "Status",
        ],
        "relationship_fields": [
            _rel("RouteBossRec", "XfRouteBoss", EDGE_RUNTIME),
            _rel("RouteTableRec", "XfRouteTable", EDGE_RUNTIME),
            _rel("SrtAppRec", "SrtAppControl", EDGE_RUNTIME),
        ],
        "references": ["XfRouteBoss", "XfRouteTable", "MsgTrack"],
        "active_row_rules": ["Name present with ConfirmScan/HostZone/route evidence"],
        "inactive_row_rules": ["Empty slots"],
        "optional_feature_rules": ["P&A verify flags optional"],
        "controller_scope_behavior": "Runtime shared.",
        "generation_implications": [
            "RUNTIME_DATA — transfer divert maps still engineer/config",
        ],
        "doc_keys": ["FPC-New-Transfers", "FPC-Transfer-Configuration-Example"],
        "confidence": "HIGH",
    },
    "XfRouteTable": {
        "subsystem": "transfer",
        "purpose": "Transfer route table: host route string → Route under a BossRecord.",
        "row_semantics": "Named route row with Enabled, BossRecord, HostRouteStr, error I/O.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "Enabled",
            "BossRecord",
            "HostRouteStr",
            "Route",
            "ErrorIO",
            "MaximumErrors",
        ],
        "relationship_fields": [
            _rel("BossRecord", "XfRouteBoss", EDGE_EXPLICIT),
            _rel("ErrorIO", "Conveyor", EDGE_OPTIONAL),
        ],
        "references": ["XfRouteBoss", "XfrTrack"],
        "active_row_rules": ["Name present", "Enabled when used"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["DSRRequest / AutoResetCons optional"],
        "controller_scope_behavior": "Boss/machine scoped.",
        "generation_implications": ["Static transfer routes — still not full divert PLC map"],
        "doc_keys": ["FPC-New-Transfers"],
        "confidence": "HIGH",
    },
    "XfRouteBoss": {
        "subsystem": "transfer",
        "purpose": "Transfer route boss: scan zone, msg tables, conveyor motor, error signaling.",
        "row_semantics": "Named boss controlling transfer scan/route decisioning.",
        "identity_fields": ["Name"],
        "key_fields": [
            "Name",
            "ScanZone",
            "XferCnvMtr",
            "CrrMsgTable",
            "AvailTransfer",
            "SystemRun",
            "LogLevel",
        ],
        "relationship_fields": [
            _rel("XferCnvMtr", "Conveyor", EDGE_EXPLICIT),
            _rel("Name", "XfRouteTable", EDGE_DOC),
            _rel("ScanZone", "ScnScanZone", EDGE_OPTIONAL),
            _rel("CrrMsgTable", "MsgMap", EDGE_OPTIONAL),
        ],
        "references": ["XfRouteTable", "XfrTrack", "Machine", "MsgMap"],
        "active_row_rules": ["Name present"],
        "inactive_row_rules": ["Blank Name"],
        "optional_feature_rules": ["ToteSensor / RunNewXfr optional"],
        "controller_scope_behavior": "Process/machine via msg tables.",
        "generation_implications": ["Transfer discovery skeleton"],
        "doc_keys": ["FPC-New-Transfers"],
        "confidence": "HIGH",
    },
    "Machine": {
        "subsystem": "communications",
        "purpose": "Communications endpoint inventory: controllers, hosts, scanners, protocols, ports.",
        "row_semantics": "One Machine_Name with Connection_Type, Communication_Protocol, Machine_Port, Offline.",
        "identity_fields": ["Machine_Name"],
        "key_fields": [
            "Machine_Name",
            "Status",
            "Connection_Type",
            "Communication_Protocol",
            "Machine_Port",
            "Offline",
            "Process",
            "FortnaMachine",
            "LogLevel",
        ],
        "relationship_fields": [
            _rel("Machine_Name", "MsgMap", EDGE_DOC, note="MsgMap.Machine_Name → this"),
            _rel("Machine_Name", "Conveyor", EDGE_DOC),
            _rel("Machine_Name", "IOCard", EDGE_DOC),
        ],
        "references": ["MsgMap", "Protocol", "Connect"],
        "active_row_rules": ["Machine_Name present", "Offline not asserted for live endpoints"],
        "inactive_row_rules": ["Blank Machine_Name", "Offline=Y when confirmed down"],
        "optional_feature_rules": ["Username/Password for TCP auth optional"],
        "controller_scope_behavior": (
            "Machine table lists all peers; controller overlays on other tables filter by Machine_Name."
        ),
        "generation_implications": [
            "Defines peer inventory; TCP endpoints for WCS still may be engineer-required",
        ],
        "doc_keys": ["FPC-Machine-MsgMap-Configuraton"],
        "confidence": "HIGH",
    },
    "MsgMap": {
        "subsystem": "communications",
        "purpose": "Message map: binds Message_Name to Machine_Name, msg types, and Menu_Name queues.",
        "row_semantics": "One Message_Name routing recv/send/ack types to a menu (e.g. MsgWCS).",
        "identity_fields": ["Message_Name"],
        "key_fields": [
            "Message_Name",
            "Machine_Name",
            "Recv_Msg_Type",
            "Send_Msg_Type",
            "Ack_Msg_Type",
            "Menu_Name",
            "Delimiter",
        ],
        "relationship_fields": [
            _rel("Machine_Name", "Machine", EDGE_EXPLICIT),
            _rel("Menu_Name", "MsgWCS", EDGE_DOC, note="WCS_EVENT often maps Menu_Name=MsgWCS"),
            _rel("Menu_Name", "MsgTrack", EDGE_OPTIONAL),
        ],
        "references": ["Machine", "MsgWCS", "MsgTrack", "WCSEvents"],
        "active_row_rules": ["Message_Name present and not placeholder"],
        "inactive_row_rules": ["Blank Message_Name"],
        "optional_feature_rules": ["CheckFile / FieldLength optional framing"],
        "controller_scope_behavior": "MsgMap.asc.<CONTROLLER> overlay common.",
        "generation_implications": ["Comm routing skeleton; not full WCS PLC"],
        "doc_keys": ["FPC-Machine-MsgMap-Configuraton"],
        "confidence": "HIGH",
    },
    "MsgTrack": {
        "subsystem": "communications_runtime",
        "purpose": "Tracking message outbound/inbound queue (runtime). Often empty on RUNs.",
        "row_semantics": "Queue rows for tracking messages when the file is populated.",
        "identity_fields": [],
        "key_fields": [],
        "relationship_fields": [
            _rel("Menu_Name", "MsgMap", EDGE_DOC, note="Referenced from MsgMap when used"),
        ],
        "references": ["MsgMap", "SrtTrack"],
        "active_row_rules": ["Non-empty message payload / destination when file has schema"],
        "inactive_row_rules": ["Empty file or all-blank rows"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Runtime queue; may be zero-byte on archive.",
        "generation_implications": ["RUNTIME_DATA; absence is normal"],
        "doc_keys": ["FPC-Sorter-Control-Module"],
        "confidence": "LOW",
    },
    "MsgWCS": {
        "subsystem": "communications_runtime",
        "purpose": "WCS outbound message queue: MsgText + Destination topic + tx status.",
        "row_semantics": (
            "Queue slots; Destination topic (/topic/…) counts as active even when MsgText blank."
        ),
        "identity_fields": ["Destination"],
        "key_fields": ["MsgText", "Destination", "TxStat", "DbKey", "DbTime"],
        "relationship_fields": [
            _rel("Destination", "WCSEvents", EDGE_DERIVED, note="Topics align with WCSDestination"),
            _rel("Menu_Name", "MsgMap", EDGE_DOC),
        ],
        "references": ["MsgMap", "WCSEvents", "Machine"],
        "active_row_rules": ["Destination present (topic path) OR MsgText present"],
        "inactive_row_rules": ["Blank Destination and MsgText"],
        "optional_feature_rules": [],
        "controller_scope_behavior": "Shared queue; MsgMap selects owning machine.",
        "generation_implications": [
            "Proves WCS messaging activity; TCP peer still configuration",
            "RUNTIME_DATA classification",
        ],
        "doc_keys": ["FPC-Machine-MsgMap-Configuraton"],
        "confidence": "HIGH",
    },
    "WCSEvents": {
        "subsystem": "communications",
        "purpose": "Static WCS/NMS event → destination/category/service enable map.",
        "row_semantics": "One EventName with WCSEnable/WCSDestination and optional NMS fields.",
        "identity_fields": ["EventName"],
        "key_fields": [
            "EventName",
            "WCSEnable",
            "WCSDestination",
            "WCSCategory",
            "WCSService",
            "WCSMachProc",
            "NMSEnable",
        ],
        "relationship_fields": [
            _rel("WCSDestination", "MsgWCS", EDGE_DOC),
            _rel("WCSMachProc", "Machine", EDGE_OPTIONAL),
            _rel("EventName", "MsgMap", EDGE_OPTIONAL),
        ],
        "references": ["MsgWCS", "MsgMap", "Machine", "wcsAlarm", "wcsSeverity"],
        "active_row_rules": ["EventName present", "WCSEnable when event armed"],
        "inactive_row_rules": ["Blank EventName"],
        "optional_feature_rules": ["NMS* optional OpenNMS path"],
        "controller_scope_behavior": "Usually base shared; enable flags select live events.",
        "generation_implications": [
            "Static event catalog for WCS interface discovery",
        ],
        "doc_keys": ["FPC-Machine-MsgMap-Configuraton", "FPC-OpenNMS-Configuration"],
        "confidence": "HIGH",
    },
    "Encoders": {
        "subsystem": "sorter",
        "purpose": "Sorter/merge encoder devices: ticks/ft, target FPM, enable bit, jamzone.",
        "row_semantics": "One Encoder Name with Encoder I/O, timing, speed limits, EnableBit, Jamzone.",
        "identity_fields": ["Encoder Name"],
        "key_fields": [
            "Encoder Name",
            "Encoder I/O",
            "Encoder Timer",
            "Ticks Per Foot",
            "Target FPM",
            "EnableBit",
            "Jamzone",
            "Tolerance_FPM",
            "StoponError",
        ],
        "relationship_fields": [
            _rel("Encoder I/O", "Conveyor", EDGE_EXPLICIT),
            _rel("EnableBit", "Conveyor", EDGE_EXPLICIT),
            _rel("Jamzone", "Jamzones", EDGE_OPTIONAL),
            _rel("Encoder Name", "Sorters", EDGE_DOC, note="Sorters.Encoder ioName"),
        ],
        "references": ["Conveyor", "Sorters", "Jamzones"],
        "active_row_rules": ["Encoder Name present and not placeholder"],
        "inactive_row_rules": ["Blank Encoder Name"],
        "optional_feature_rules": [
            "NoSortonError / NoSortOnSpeed optional sort inhibit",
            "DupToMemBit optional",
        ],
        "controller_scope_behavior": "Encoders.asc.<CONTROLLER> overlay preferred.",
        "generation_implications": [
            "Encoder scale/speed seeds for sorter/sawtooth when generation supported",
        ],
        "doc_keys": [
            "FPC-Shifter-And-Sorter-Configuration",
            "FPC-HighSpeedSawtoothMerge",
        ],
        "confidence": "HIGH",
    },
}


# Extra documented edges not fully captured as single field FKs
EXTRA_EDGES: list[dict[str, Any]] = [
    {
        "from_table": "Jamzones",
        "to_table": "StartStopZones",
        "edge_type": EDGE_DOC,
        "via_fields": ["StartStopZone"],
        "note": "Training: StartStopZones + Jamzones configured together",
        "doc_keys": ["FPC-StartStopZones"],
    },
    {
        "from_table": "CombinedJamZones",
        "to_table": "Jamzones",
        "edge_type": EDGE_DOC,
        "via_fields": ["JamEnableCombined"],
        "note": "Combined jam enable aggregates jam zones",
        "doc_keys": ["CombinedJamZones"],
    },
    {
        "from_table": "SawLane",
        "to_table": "SawMerge",
        "edge_type": EDGE_DOC,
        "via_fields": ["SawMerge"],
        "note": "Lane belongs to merge boss",
        "doc_keys": ["FPC-Merge-Modules"],
    },
    {
        "from_table": "HSSawLane",
        "to_table": "HSSawMerge",
        "edge_type": EDGE_DOC,
        "via_fields": ["SawMerge"],
        "note": "HS lane belongs to HS merge",
        "doc_keys": ["FPC-HighSpeedSawtoothMerge"],
    },
    {
        "from_table": "Sorters",
        "to_table": "SrtTrack",
        "edge_type": EDGE_RUNTIME,
        "via_fields": ["Data LowRec", "Data HighRec", "Buffer LowRec", "Buffer HighRec"],
        "note": "Sorter record ranges index into track/buffer menus",
        "doc_keys": ["FPC-Shifter-And-Sorter-Configuration"],
    },
    {
        "from_table": "MsgMap",
        "to_table": "WCSEvents",
        "edge_type": EDGE_DERIVED,
        "via_fields": ["Message_Name"],
        "note": "WCS_EVENT message name pairs with WCSEvents catalog",
        "doc_keys": ["FPC-Machine-MsgMap-Configuraton"],
    },
    {
        "from_table": "Conveyor",
        "to_table": "PeList",
        "edge_type": EDGE_OPTIONAL,
        "via_fields": ["IO_Name"],
        "note": "PeList/PeDisplay reference conveyor records for PE status reporting",
        "doc_keys": ["FPC-Photoeye-Status-Reporting"],
    },
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_placeholder(val: str) -> bool:
    s = _clean(val)
    if not s or s.upper() in {b.upper() for b in PLACEHOLDER if b}:
        return True
    return s.startswith(PLACEHOLDER_PREFIXES)


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def load_doc_inventory(root: Path) -> dict[str, Any]:
    """Load training doc inventory if present (index md or docs-index JSON)."""
    md = root / "docs" / "FPC_TRAINING_DOCUMENT_INDEX.md"
    js = root / "docs-index" / "documents.json"
    deep_candidates = [
        root / "exports" / "fpc-knowledge" / "document_inventory.json",
        root / "exports" / "fpc-knowledge" / "training_doc_inventory.json",
    ]
    sources: list[dict[str, Any]] = []
    docs_by_title: dict[str, dict[str, Any]] = {}
    docs_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def _remember(doc: dict[str, Any]) -> None:
        title = str(doc.get("title") or doc.get("name") or "")
        if not title:
            return
        # Prefer richer records (tables_mentioned / relevance) over sparse ones.
        prev = docs_by_title.get(title)
        if prev is None or (
            doc.get("tables_mentioned") and not prev.get("tables_mentioned")
        ) or (
            doc.get("relevance") and not prev.get("relevance")
        ):
            docs_by_title[title] = doc
        for tname in doc.get("tables_mentioned") or []:
            tn = str(tname).strip()
            if not tn:
                continue
            docs_by_table[tn].append(
                {
                    "title": title,
                    "file": doc.get("file"),
                    "id": doc.get("id"),
                    "category": doc.get("category") or doc.get("corpus"),
                    "relevance": doc.get("relevance"),
                    "subsystem": doc.get("subsystem"),
                }
            )

    if js.is_file():
        data = json.loads(js.read_text(encoding="utf-8"))
        sources.append({"kind": "docs-index", "path": _repo_rel(js)})
        for d in data.get("documents") or []:
            _remember(
                {
                    "title": d.get("title"),
                    "file": d.get("file"),
                    "id": d.get("id"),
                    "category": d.get("category"),
                    "summary": (d.get("summary") or "")[:400],
                    "tasks": d.get("tasks") or [],
                }
            )

    for deep in deep_candidates:
        if not deep.is_file():
            continue
        data = json.loads(deep.read_text(encoding="utf-8"))
        sources.append({"kind": "document_inventory", "path": _repo_rel(deep)})
        for d in data.get("documents") or data.get("docs") or []:
            _remember(d)

    md_linked = False
    if md.is_file():
        sources.append({"kind": "training_index_md", "path": _repo_rel(md)})
        md_linked = True
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"`(docs/training/[^`]+)`", text):
            rel = m.group(1)
            title = Path(rel).stem
            if title not in docs_by_title:
                _remember({"title": title, "file": rel, "from_index_md": True})
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
            title, rel = m.group(1), m.group(2)
            if title not in docs_by_title:
                _remember({"title": title, "file": rel, "from_index_md": True})

    return {
        "available": bool(docs_by_title),
        "md_index_present": md_linked,
        "sources": sources,
        "docs_by_title": docs_by_title,
        "docs_by_table": dict(docs_by_table),
        "count": len(docs_by_title),
    }


def resolve_schema_file(fortna: Path, basename: str) -> dict[str, Any]:
    """Pick best schema file: prefer non-empty base, else any overlay, else historical."""
    if not basename.endswith(".asc"):
        basename = f"{basename}.asc"
    base = fortna / basename
    overlays = sorted(
        p
        for p in fortna.glob(f"{basename}.*")
        if p.is_file() and not p.name.lower().endswith(".bak")
    )
    historical = sorted(
        p
        for p in fortna.glob(f"old.{basename}*")
        if p.is_file() and not p.name.lower().endswith(".bak")
    )

    headers: list[str] = []
    schema_path: Path | None = None
    scope = SCOPE_BASE_ONLY

    if base.is_file() and base.stat().st_size > 0:
        headers, _ = read_asc(base)
        schema_path = base
        scope = SCOPE_BASE_ONLY
    elif overlays:
        for ov in overlays:
            if ov.stat().st_size > 0:
                headers, _ = read_asc(ov)
                schema_path = ov
                scope = SCOPE_OVERLAY
                break
    elif historical:
        for hp in historical:
            if hp.stat().st_size > 0:
                headers, _ = read_asc(hp)
                schema_path = hp
                scope = SCOPE_HISTORICAL
                break

    return {
        "basename": basename,
        "headers": headers,
        "schema_path": schema_path,
        "scope": scope,
        "base": base if base.is_file() else None,
        "overlays": overlays,
        "historical": historical,
        "exists": schema_path is not None or (base.is_file()),
        "byte_size": schema_path.stat().st_size if schema_path else (base.stat().st_size if base.is_file() else 0),
    }


def count_active_rows(headers: list[str], rows: list[dict[str, str]], identity_fields: list[str]) -> int:
    name_cols = [c for c in identity_fields if c in headers]
    if not name_cols:
        name_cols = [c for c in NAME_COLUMNS if c in headers]
    if not name_cols and headers:
        name_cols = [headers[0]]
    active = 0
    for row in rows:
        ok = False
        for c in name_cols:
            if not _is_placeholder(row.get(c, "")):
                ok = True
                break
        # MsgWCS-style: Destination topic
        if not ok and "Destination" in headers and not _is_placeholder(row.get("Destination", "")):
            ok = True
        if ok:
            active += 1
    return active


def discover_run_schemas(run_dirs: list[Path], machine: str) -> dict[str, Any]:
    """Union schemas for catalog families across RUN trees."""
    by_table: dict[str, dict[str, Any]] = {}

    for run_dir in run_dirs:
        fortna = run_dir / "FORTNA"
        if not fortna.is_dir():
            continue
        for family, spec in FAMILY_CATALOG.items():
            globs = spec.get("table_globs") or [f"{family}.asc"]
            for g in globs:
                stem = g[:-4] if g.endswith(".asc") else g
                info = resolve_schema_file(fortna, stem)
                key = family if not spec.get("table_globs") else stem
                # For SrtTrack family, keep per-file + roll up later
                entry = by_table.get(key)
                if entry is None:
                    entry = {
                        "table_name": key if key != family else family,
                        "family": family,
                        "headers": [],
                        "schema_sources": [],
                        "run_dirs": [],
                        "row_counts": [],
                        "active_counts": [],
                        "scopes_seen": [],
                    }
                    by_table[key] = entry

                if info["headers"] and (
                    not entry["headers"] or len(info["headers"]) >= len(entry["headers"])
                ):
                    entry["headers"] = list(info["headers"])

                if info["schema_path"] is not None:
                    rel = _repo_rel(info["schema_path"])
                    if rel not in entry["schema_sources"]:
                        entry["schema_sources"].append(rel)
                    entry["scopes_seen"].append(info["scope"])
                    _h, rows = read_asc(info["schema_path"])
                    entry["row_counts"].append(len(rows))
                    entry["active_counts"].append(
                        count_active_rows(_h, rows, spec.get("identity_fields") or [])
                    )

                # Also probe merge_table_rows when machine known and single-file family
                if machine and not spec.get("table_globs"):
                    merged = merge_table_rows(fortna, f"{family}.asc", machine)
                    entry.setdefault("merge_probes", []).append(
                        {
                            "run_dir": _repo_rel(run_dir),
                            "machine": machine,
                            "merged_rows": len(merged.get("rows") or []),
                            "base": merged.get("paths", {}).get("base"),
                            "overlay": merged.get("paths", {}).get("overlay"),
                        }
                    )

                rd = _repo_rel(run_dir)
                if rd not in entry["run_dirs"]:
                    entry["run_dirs"].append(rd)

    # Roll SrtTrack* into family aggregate entry
    srt_files = [k for k in by_table if k.startswith("SrtTrack")]
    if srt_files:
        fam = {
            "table_name": "SrtTrack",
            "family": "SrtTrack",
            "headers": [],
            "schema_sources": [],
            "run_dirs": [],
            "row_counts": [],
            "active_counts": [],
            "scopes_seen": [],
            "member_tables": sorted(srt_files),
        }
        for k in sorted(srt_files):
            e = by_table[k]
            if e["headers"] and not fam["headers"]:
                fam["headers"] = e["headers"]
            fam["schema_sources"].extend(e["schema_sources"])
            for rd in e["run_dirs"]:
                if rd not in fam["run_dirs"]:
                    fam["run_dirs"].append(rd)
            fam["row_counts"].extend(e["row_counts"])
            fam["active_counts"].extend(e["active_counts"])
            fam["scopes_seen"].extend(e["scopes_seen"])
        by_table["SrtTrack"] = fam

    return by_table


def _filter_fields(candidates: list[str], headers: list[str]) -> list[str]:
    if not headers:
        return list(candidates)
    header_set = set(headers)
    # preserve order; keep candidates that exist; also keep known-absent noted separately
    return [c for c in candidates if c in header_set]


def _filter_rels(rels: list[RelSpec], headers: list[str]) -> list[RelSpec]:
    if not headers:
        # MsgTrack empty file — keep documented rels with note
        return list(rels)
    hs = set(headers)
    out = []
    for r in rels:
        field = r["field"]
        if field in hs or field in ("Menu_Name",):  # cross-table conceptual
            if field in hs or r["edge_type"] in (EDGE_DOC, EDGE_DERIVED, EDGE_RUNTIME, EDGE_OPTIONAL):
                if field in hs or r["edge_type"] != EDGE_EXPLICIT:
                    out.append(r)
        # EXPLICIT must be in headers
        elif r["edge_type"] != EDGE_EXPLICIT:
            out.append(r)
    # strict: EXPLICIT only if field present
    cleaned = []
    for r in out:
        if r["edge_type"] == EDGE_EXPLICIT and r["field"] not in hs:
            continue
        cleaned.append(r)
    return cleaned


def resolve_document_sources(
    spec: dict[str, Any],
    docs: dict[str, Any],
    *,
    table_name: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not docs.get("available"):
        return out
    by_title = docs["docs_by_title"]
    seen_titles: set[str] = set()

    def _add(d: dict[str, Any], *, key: str | None = None) -> None:
        title = str(d.get("title") or key or "")
        if not title or title in seen_titles:
            return
        seen_titles.add(title)
        item = {
            "title": title,
            "file": d.get("file"),
            "id": d.get("id"),
            "category": d.get("category") or d.get("corpus"),
        }
        if d.get("relevance"):
            item["relevance"] = d.get("relevance")
        if docs.get("md_index_present"):
            item["index"] = "docs/FPC_TRAINING_DOCUMENT_INDEX.md"
        out.append(item)

    for key in spec.get("doc_keys") or []:
        d = by_title.get(key)
        if not d:
            key_norm = re.sub(r"[^a-z0-9]+", "", key.lower())
            for t, dd in by_title.items():
                t_norm = re.sub(r"[^a-z0-9]+", "", t.lower())
                if key_norm and (key_norm in t_norm or t_norm in key_norm):
                    d = dd
                    break
        if d:
            _add(d, key=key)
        else:
            out.append({"title": key, "file": None, "status": "listed_in_catalog_not_in_inventory"})

    # Enrich from inventory tables_mentioned (CRITICAL/HIGH only to avoid noise)
    if table_name:
        aliases = {
            "SrtTrack": ["SrtTrack1", "SrtTrack2", "SrtTrack3", "SrtTrack4", "SrtTrack5"],
        }
        names = [table_name] + aliases.get(table_name, [])
        for tn in names:
            for d in (docs.get("docs_by_table") or {}).get(tn, []):
                rel = str(d.get("relevance") or "").upper()
                if rel in ("CRITICAL", "HIGH"):
                    _add(d)

    return out


def build_table_entries(
    schemas: dict[str, Any],
    docs: dict[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for family, spec in FAMILY_CATALOG.items():
        sch = schemas.get(family) or {}
        headers = list(sch.get("headers") or [])
        # For SrtTrack, headers from members
        if family == "SrtTrack" and not headers:
            for m in sch.get("member_tables") or []:
                if schemas.get(m, {}).get("headers"):
                    headers = schemas[m]["headers"]
                    break

        key_fields = _filter_fields(spec.get("key_fields") or [], headers)
        identity_fields = _filter_fields(spec.get("identity_fields") or [], headers)
        rels = _filter_rels(spec.get("relationship_fields") or [], headers)

        schema_sources = sch.get("schema_sources") or []
        schema_source = schema_sources[0] if schema_sources else None
        if family == "MsgTrack" and not schema_source:
            # record empty path if seen in run_dirs
            for rd in sch.get("run_dirs") or []:
                candidate = Path(ROOT) / rd / "FORTNA" / "MsgTrack.asc"
                if candidate.exists():
                    schema_source = _repo_rel(candidate)
                    break

        conf = spec.get("confidence") or "MEDIUM"
        if not headers and family != "MsgTrack":
            conf = "LOW"
        elif family == "MsgTrack" and not headers:
            conf = "LOW"

        entry = {
            "table_name": family,
            "subsystem": spec["subsystem"],
            "purpose": spec["purpose"],
            "row_semantics": spec["row_semantics"],
            "key_fields": key_fields,
            "identity_fields": identity_fields,
            "relationship_fields": [
                {
                    "field": r["field"],
                    "target_table": r["target_table"],
                    "edge_type": r["edge_type"],
                    "note": r.get("note") or "",
                }
                for r in rels
            ],
            "references": list(spec.get("references") or []),
            "active_row_rules": list(spec.get("active_row_rules") or []),
            "inactive_row_rules": list(spec.get("inactive_row_rules") or []),
            "optional_feature_rules": list(spec.get("optional_feature_rules") or []),
            "controller_scope_behavior": spec.get("controller_scope_behavior") or "",
            "generation_implications": list(spec.get("generation_implications") or []),
            "document_sources": resolve_document_sources(spec, docs, table_name=family),
            "confidence": conf,
            "schema_source": schema_source,
            "schema_headers": headers,
            "schema_sources_all": schema_sources,
            "run_dirs": sch.get("run_dirs") or [],
            "row_count_samples": sch.get("row_counts") or [],
            "active_row_count_samples": sch.get("active_counts") or [],
        }
        if sch.get("member_tables"):
            entry["member_tables"] = sch["member_tables"]
        if not headers:
            entry["schema_note"] = (
                "Header unavailable (empty or missing ASC). Semantics from docs/catalog only; "
                "no invented fields claimed as RUN-present."
            )
        entries.append(entry)
    return entries


def build_relationship_graph(entries: list[dict[str, Any]], docs: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    edges = []
    seen_edge: set[tuple[str, str, str, str]] = set()

    for e in entries:
        nodes.append(
            {
                "id": e["table_name"],
                "subsystem": e["subsystem"],
                "confidence": e["confidence"],
                "schema_source": e.get("schema_source"),
            }
        )
        for r in e.get("relationship_fields") or []:
            key = (e["table_name"], r["target_table"], r["field"], r["edge_type"])
            if key in seen_edge:
                continue
            seen_edge.add(key)
            edges.append(
                {
                    "from": e["table_name"],
                    "to": r["target_table"],
                    "via_field": r["field"],
                    "edge_type": r["edge_type"],
                    "note": r.get("note") or "",
                    "provenance": "RUN_HEADER" if r["edge_type"] == EDGE_EXPLICIT else r["edge_type"],
                }
            )

    for ex in EXTRA_EDGES:
        # only add if both ends in catalog or known
        key = (ex["from_table"], ex["to_table"], ",".join(ex.get("via_fields") or []), ex["edge_type"])
        if key in seen_edge:
            continue
        seen_edge.add(key)
        doc_sources = resolve_document_sources({"doc_keys": ex.get("doc_keys") or []}, docs)
        edges.append(
            {
                "from": ex["from_table"],
                "to": ex["to_table"],
                "via_field": ",".join(ex.get("via_fields") or []),
                "edge_type": ex["edge_type"],
                "note": ex.get("note") or "",
                "document_sources": doc_sources,
                "provenance": ex["edge_type"],
            }
        )

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN ASC headers + training docs (no finished PLC)",
        "edge_types": [
            EDGE_EXPLICIT,
            EDGE_DOC,
            EDGE_DERIVED,
            EDGE_OPTIONAL,
            EDGE_RUNTIME,
        ],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def build_zone_model(schemas: dict[str, Any], entries_by_name: dict[str, Any]) -> dict[str, Any]:
    def hdr(name: str) -> list[str]:
        return list((schemas.get(name) or {}).get("headers") or [])

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN schemas + training docs (FPC-StartStopZones, CombinedJamZones)",
        "note": (
            "Zone kinds are distinct. Do not conflate Engineering Area, StartStop, EStop, Jam, "
            "and Sorter/Tracking zones."
        ),
        "zone_kinds": [
            {
                "kind": "EngineeringArea",
                "definition": (
                    "PLC/generation area grouping for equipment. Often NOT present as a reliable RUN "
                    "geometry/area table; may require ENGINEER_CONFIGURED_REQUIRED default Area_1."
                ),
                "run_tables": [],
                "provenance": "ENGINEER_CONFIGURED_REQUIRED when absent from RUN",
                "confidence": "MEDIUM",
            },
            {
                "kind": "StartStopZone",
                "definition": "Start/stop island with request flags and owners; referenced by Jamzones.",
                "run_tables": ["StartStopZones", "Jamzones"],
                "key_fields": {
                    "StartStopZones": _filter_fields(
                        ["Zone Name", "StartReqFlag", "StopReqFlag", "State"],
                        hdr("StartStopZones"),
                    ),
                    "Jamzones": _filter_fields(
                        ["Zone Name", "StartStopZone", "Start Request Flag", "Stop Request Flag"],
                        hdr("Jamzones"),
                    ),
                },
                "provenance": "RUN_EXPLICIT",
                "confidence": "HIGH",
            },
            {
                "kind": "EStopZone",
                "definition": "E-stop circuit/device entries distinct from start/stop and jam zones.",
                "run_tables": ["EStop"],
                "key_fields": {"EStop": _filter_fields(["Desc", "Part", "Error"], hdr("EStop"))},
                "provenance": "RUN_EXPLICIT when EStop.asc present",
                "confidence": entries_by_name.get("EStop", {}).get("confidence", "MEDIUM"),
            },
            {
                "kind": "JamZone",
                "definition": "Jam ownership zone for Jamcheck / encoder jamzone / combined jam enables.",
                "run_tables": ["Jamzones", "Jamcheck", "CombinedJamZones", "Fulljam"],
                "key_fields": {
                    "Jamzones": _filter_fields(
                        ["Zone Name", "Latch Bit", "Jammed Bit", "Enable Bit"],
                        hdr("Jamzones"),
                    ),
                    "Jamcheck": _filter_fields(
                        ["Sensor_Name", "Zone", "Conveyor_Name", "Timer_Name"],
                        hdr("Jamcheck"),
                    ),
                },
                "provenance": "RUN_EXPLICIT",
                "confidence": "HIGH",
            },
            {
                "kind": "SorterTrackingZone",
                "definition": (
                    "HostZone / ScanZoneID / XfrZoneID on track and zone-lane tables — logical host "
                    "zones for sortation/transfer, not StartStop islands."
                ),
                "run_tables": ["SrtZoneLane", "SrtTrack", "SrtScanBoss", "XfrTrack"],
                "key_fields": {
                    "SrtZoneLane": _filter_fields(
                        ["Name", "HostZone", "Lane", "AppSorter"],
                        hdr("SrtZoneLane"),
                    ),
                    "SrtTrack": _filter_fields(
                        ["HostZone", "ScanZoneID", "SorterLane"],
                        hdr("SrtTrack"),
                    ),
                },
                "provenance": "RUN_EXPLICIT + RUNTIME_DATA",
                "confidence": "HIGH",
            },
        ],
    }


def build_pe_semantics(run_dirs: list[Path]) -> dict[str, Any]:
    suffix_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    sources: list[str] = []

    for run_dir in run_dirs:
        path = run_dir / "FORTNA" / "Conveyor.asc"
        if not path.is_file() or path.stat().st_size == 0:
            continue
        sources.append(_repo_rel(path))
        _h, rows = read_asc(path)
        for row in rows:
            if (row.get("Type") or "").strip().upper() != "PHOTOCELL":
                continue
            name = _clean(row.get("IO_Name"))
            if _is_placeholder(name):
                continue
            type_counts["PHOTOCELL"] += 1
            if "_" in name:
                suf = name.rsplit("_", 1)[-1].upper()
            else:
                suf = "(none)"
            suffix_counts[suf] += 1
            if len(samples[suf]) < 5:
                samples[suf].append(name)

    # Semantics from observed suffixes + training (photoeye status / fulls-jams docs)
    suffix_meanings = {
        "P": {
            "meaning": "Presence photoeye",
            "confidence": "HIGH",
            "evidence": "Common Conveyor PHOTOCELL suffix _P; used as presence in merge/full logic",
        },
        "J": {
            "meaning": "Jam photoeye",
            "confidence": "HIGH",
            "evidence": "Common _J suffix; Jamcheck.Sensor_Name typically jam PE",
        },
        "F": {
            "meaning": "Full photoeye",
            "confidence": "HIGH",
            "evidence": "Common _F suffix; Fullline/Fulljam Sensor_Name; SawLane.ReserveTM tmfc*_F",
        },
        "JF": {
            "meaning": "Combined jam/full photoeye",
            "confidence": "MEDIUM",
            "evidence": "Observed _JF suffix on PHOTOCELL rows",
        },
        "I": {
            "meaning": "Induct / infeed photoeye (site naming)",
            "confidence": "MEDIUM",
            "evidence": "Observed _I suffix; confirm per row General_Description",
        },
        "F1": {
            "meaning": "Full photoeye channel/instance 1",
            "confidence": "MEDIUM",
            "evidence": "Observed _F1/_F2 multi-full eyes on one conveyor",
        },
        "F2": {
            "meaning": "Full photoeye channel/instance 2",
            "confidence": "MEDIUM",
            "evidence": "Observed _F1/_F2 multi-full eyes on one conveyor",
        },
        "P1": {
            "meaning": "Presence photoeye instance 1",
            "confidence": "MEDIUM",
            "evidence": "Observed _P1/_P2 suffixes",
        },
        "P2": {
            "meaning": "Presence photoeye instance 2",
            "confidence": "MEDIUM",
            "evidence": "Observed _P1/_P2 suffixes",
        },
    }

    suffixes_out = []
    for suf, cnt in suffix_counts.most_common():
        meta = suffix_meanings.get(suf, {
            "meaning": "Unspecified PE role — use General_Description / jam-full table links",
            "confidence": "LOW",
            "evidence": "Observed on RUN PHOTOCELL rows; no catalog claim beyond presence",
        })
        suffixes_out.append(
            {
                "suffix": suf,
                "count": cnt,
                "samples": samples.get(suf, []),
                **meta,
            }
        )

    pe_list_headers = []
    pe_disp_headers = []
    for run_dir in run_dirs:
        for name, bucket in (("PeList", "list"), ("PeDisplay", "disp")):
            p = run_dir / "FORTNA" / f"{name}.asc"
            if p.is_file() and p.stat().st_size > 0:
                h, _ = read_asc(p)
                if bucket == "list":
                    pe_list_headers = h
                else:
                    pe_disp_headers = h

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN Conveyor.asc Type=PHOTOCELL + PeList/PeDisplay headers + training docs",
        "schema_sources": sources,
        "photocell_row_count": int(type_counts.get("PHOTOCELL", 0)),
        "naming": {
            "pattern": "Typically EZPE###_<ROLE> or PE###_<ROLE> in IO_Name",
            "role_suffixes": suffixes_out,
        },
        "status_reporting_tables": {
            "PeList": {
                "headers": pe_list_headers,
                "purpose": "PE list status / force tracking tied to ConveyorRec",
                "document_sources": ["FPC-Photoeye-Status-Reporting"],
            },
            "PeDisplay": {
                "headers": pe_disp_headers,
                "purpose": "PE display descriptors tied to ConveyorRec",
                "document_sources": ["FPC-Photoeye-Status-Reporting"],
            },
        },
        "links_to_safety_tables": [
            {"table": "Jamcheck", "field": "Sensor_Name", "role": "jam PE"},
            {"table": "Fullline", "field": "Sensor_Name", "role": "full PE"},
            {"table": "Fulljam", "field": "Sensor_Name", "role": "full-jam PE"},
            {"table": "SawLane", "field": "PhotoEyeIO", "role": "lane PE"},
            {"table": "HSSawLane", "field": "LanePE", "role": "HS lane PE"},
        ],
        "rules": [
            "Do not invent PE roles not evidenced by suffix, General_Description, or safety-table links",
            "PHOTOCELL rows live in Conveyor.asc — there is no separate Photoeye.asc required",
        ],
    }


def build_motor_chain_model(run_dirs: list[Path], machine: str) -> dict[str, Any]:
    headers: list[str] = []
    sources: list[str] = []
    chain_samples: list[dict[str, Any]] = []
    head_count = 0

    for run_dir in run_dirs:
        fortna = run_dir / "FORTNA"
        if not fortna.is_dir():
            continue
        info = resolve_schema_file(fortna, "Mtrchain.asc")
        if info["schema_path"] is None:
            continue
        sources.append(_repo_rel(info["schema_path"]))
        headers = info["headers"] or headers
        if machine:
            merged = merge_table_rows(fortna, "Mtrchain.asc", machine)
            rows = [m["row"] for m in merged.get("rows") or []]
        else:
            _h, rows = read_asc(info["schema_path"])
        for row in rows:
            motor = _clean(row.get("Motor_Name"))
            if _is_placeholder(motor):
                continue
            head_count += 1
            chained = []
            for i in range(1, 11):
                c = _clean(row.get(f"Motor_Chained{i}"))
                if c and not _is_placeholder(c):
                    chained.append(c)
            if len(chain_samples) < 15 and (chained or _clean(row.get("Motor_Aux"))):
                chain_samples.append(
                    {
                        "Motor_Name": motor,
                        "Motor_Chained": chained,
                        "Motor_Aux": _clean(row.get("Motor_Aux")),
                        "Timer_Name": _clean(row.get("Timer_Name")),
                        "Stop Zone": _clean(row.get("Stop Zone")),
                        "Enabled": _clean(row.get("Enabled")),
                        "source": _repo_rel(info["schema_path"]),
                    }
                )

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN Mtrchain.asc (+ overlay merge when machine set)",
        "document_sources": ["FPC-Motor-Startup-Chains"],
        "schema_headers": headers,
        "schema_sources": sources,
        "active_chain_heads_sampled": head_count,
        "fields": {
            "head": "Motor_Name",
            "followers": [f"Motor_Chained{i}" for i in range(1, 11) if not headers or f"Motor_Chained{i}" in headers],
            "aux": "Motor_Aux",
            "timer": ["Timer_Name", "Timer_Preset", "RUN Timer_Name"],
            "stop": "Stop Zone",
        },
        "rules": [
            "Motor_Name and Motor_Chained* reference Conveyor.asc motor/VFD IO_Name values",
            "Explicit Mtrchain edges beat P-number ordering for startup topology",
            "Stop Zone may reference StartStopZones when populated",
        ],
        "samples": chain_samples,
    }


def build_communication_model(entries_by_name: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN Machine/MsgMap/MsgWCS/WCSEvents/MsgTrack schemas",
        "document_sources": [
            "FPC-Machine-MsgMap-Configuraton",
            "FPC-OpenNMS-Configuration",
        ],
        "layers": [
            {
                "layer": "endpoint",
                "table": "Machine",
                "role": "Peers/controllers/hosts with protocol and port",
                "headers": (schemas.get("Machine") or {}).get("headers") or [],
                "static_or_runtime": "static",
            },
            {
                "layer": "message_routing",
                "table": "MsgMap",
                "role": "Binds Message_Name to Machine_Name + Menu_Name queue",
                "headers": (schemas.get("MsgMap") or {}).get("headers") or [],
                "static_or_runtime": "static",
            },
            {
                "layer": "wcs_event_catalog",
                "table": "WCSEvents",
                "role": "EventName enable + destination/category/service",
                "headers": (schemas.get("WCSEvents") or {}).get("headers") or [],
                "static_or_runtime": "static",
            },
            {
                "layer": "wcs_out_queue",
                "table": "MsgWCS",
                "role": "Outbound WCS messages (MsgText/Destination)",
                "headers": (schemas.get("MsgWCS") or {}).get("headers") or [],
                "static_or_runtime": "runtime",
            },
            {
                "layer": "tracking_msg_queue",
                "table": "MsgTrack",
                "role": "Tracking message queue (often empty)",
                "headers": (schemas.get("MsgTrack") or {}).get("headers") or [],
                "static_or_runtime": "runtime",
                "note": entries_by_name.get("MsgTrack", {}).get("schema_note"),
            },
        ],
        "edges": [
            {"from": "MsgMap", "to": "Machine", "via": "Machine_Name", "edge_type": EDGE_EXPLICIT},
            {"from": "MsgMap", "to": "MsgWCS", "via": "Menu_Name", "edge_type": EDGE_DOC},
            {"from": "WCSEvents", "to": "MsgWCS", "via": "WCSDestination", "edge_type": EDGE_DOC},
            {"from": "SrtAppControl", "to": "MsgMap", "via": "CrrMsgTable/DcmMsgTable", "edge_type": EDGE_OPTIONAL},
            {"from": "XfRouteBoss", "to": "MsgMap", "via": "CrrMsgTable/…", "edge_type": EDGE_OPTIONAL},
        ],
        "generation_policy": {
            "wcs_plc": "NOT_SUPPORTED until complete generic library path exists",
            "discovery": "Inventory endpoints, maps, and active queues only",
        },
    }


def build_sawtooth_model(
    run_dirs: list[Path],
    machine: str,
    docs: dict[str, Any],
) -> dict[str, Any]:
    tables = [
        "SawLane",
        "SawMerge",
        "SawState",
        "HSSawLane",
        "HSSawMerge",
        "HSSawParm",
        "HSSawState",
        "HSSawSim",
    ]
    table_info: dict[str, Any] = {}
    classic_lanes: list[dict[str, Any]] = []
    classic_merges: list[dict[str, Any]] = []
    hs_lanes_active = 0
    hs_merges_active = 0

    for t in tables:
        table_info[t] = {"headers": [], "sources": [], "active_named": 0, "row_count": 0}

    for run_dir in run_dirs:
        fortna = run_dir / "FORTNA"
        if not fortna.is_dir():
            continue
        for t in tables:
            info = resolve_schema_file(fortna, f"{t}.asc")
            if info["schema_path"] is None:
                continue
            table_info[t]["headers"] = info["headers"] or table_info[t]["headers"]
            table_info[t]["sources"].append(_repo_rel(info["schema_path"]))
            if machine and t in ("SawLane", "SawMerge", "HSSawLane", "HSSawMerge", "HSSawParm"):
                merged = merge_table_rows(fortna, f"{t}.asc", machine)
                rows = [m["row"] for m in merged.get("rows") or []]
            else:
                _h, rows = read_asc(info["schema_path"])
            table_info[t]["row_count"] = max(table_info[t]["row_count"], len(rows))
            id_field = "Name"
            active = 0
            for row in rows:
                name = _clean(row.get(id_field))
                if _is_placeholder(name):
                    continue
                active += 1
                if t == "SawLane" and len(classic_lanes) < 20:
                    classic_lanes.append(
                        {
                            "Name": name,
                            "SawMerge": _clean(row.get("SawMerge")),
                            "PhotoEyeIO": _clean(row.get("PhotoEyeIO")),
                            "ReserveTM": _clean(row.get("ReserveTM")),
                            "AllowedToRun": _clean(row.get("AllowedToRun")),
                            "pState": _clean(row.get("pState")),
                        }
                    )
                if t == "SawMerge" and len(classic_merges) < 10:
                    classic_merges.append(
                        {
                            "Name": name,
                            "MotorIO": _clean(row.get("MotorIO")),
                            "ReserveIN": _clean(row.get("ReserveIN")),
                            "LaneEnableDelayTM": _clean(row.get("LaneEnableDelayTM")),
                        }
                    )
            table_info[t]["active_named"] = max(table_info[t]["active_named"], active)
            if t == "HSSawLane":
                hs_lanes_active = max(hs_lanes_active, active)
            if t == "HSSawMerge":
                hs_merges_active = max(hs_merges_active, active)

    mode = "classic_sawtooth"
    if hs_lanes_active or hs_merges_active:
        mode = "classic_plus_hs_tables"
    if hs_lanes_active and table_info["SawLane"]["active_named"] == 0:
        mode = "hs_sawtooth"

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN Saw* + HSSaw* headers/rows + FPC-HighSpeedSawtoothMerge / FPC-Merge-Modules",
        "document_sources": resolve_document_sources(
            {"doc_keys": ["FPC-HighSpeedSawtoothMerge", "FPC-Merge-Modules"]},
            docs,
        ),
        "mode": mode,
        "classic": {
            "tables": ["SawMerge", "SawLane", "SawState"],
            "merges": classic_merges,
            "lanes_sample": classic_lanes,
            "state_vocab_table": "SawState",
            "active_lanes": table_info["SawLane"]["active_named"],
            "active_merges": table_info["SawMerge"]["active_named"],
        },
        "high_speed": {
            "tables": ["HSSawMerge", "HSSawLane", "HSSawParm", "HSSawState", "HSSawSim"],
            "active_lanes": hs_lanes_active,
            "active_merges": hs_merges_active,
            "state_vocab_table": "HSSawState",
            "upgrade_rule": (
                "Use HSSaw* field semantics only when active named rows exist; "
                "table presence alone does not imply HS control is configured."
            ),
            "features_from_docs": [
                "Reservation re-use",
                "Opportunistic feeding (HSSawLane.Opportunistic)",
                "Slow/Fast/Accum speed actions",
            ],
        },
        "table_schemas": table_info,
        "relationships": [
            {"from": "SawLane", "to": "SawMerge", "via": "SawMerge", "edge_type": EDGE_EXPLICIT},
            {"from": "SawLane", "to": "Conveyor", "via": "PhotoEyeIO", "edge_type": EDGE_EXPLICIT},
            {"from": "SawLane", "to": "Fullline", "via": "ReserveTM", "edge_type": EDGE_DERIVED},
            {"from": "SawMerge", "to": "Conveyor", "via": "MotorIO", "edge_type": EDGE_EXPLICIT},
            {"from": "HSSawLane", "to": "HSSawMerge", "via": "SawMerge", "edge_type": EDGE_EXPLICIT},
            {"from": "HSSawParm", "to": "HSSawLane", "via": "SawLane", "edge_type": EDGE_EXPLICIT},
        ],
        "generation_implications": [
            "Active classic SawLane+SawMerge → populate sawtooth_merges in SiteModel",
            "HS tables upgrade parameter/FSM vocabulary when active",
            "Do not map RUN pState labels to library diLaneMode without explicit evidence",
        ],
    }


def build_sorter_model(
    run_dirs: list[Path],
    machine: str,
    docs: dict[str, Any],
) -> dict[str, Any]:
    static_tables = [
        "Sorters",
        "Encoders",
        "SrtAppControl",
        "SrtScanBoss",
        "SrtZoneLane",
        "XfRouteBoss",
        "XfRouteTable",
        "WCSEvents",
        "MsgMap",
        "Machine",
    ]
    runtime_tables = [
        "SrtTrack1",
        "SrtTrack2",
        "SrtTrack3",
        "SrtTrack4",
        "SrtTrack5",
        "XfrTrack",
        "MsgTrack",
        "MsgWCS",
        "SortBuff",
        "SortData",
    ]

    def summarize(names: list[str], classification: str) -> list[dict[str, Any]]:
        out = []
        for t in names:
            best = {
                "table": t,
                "classification": classification,
                "headers": [],
                "sources": [],
                "active_named": 0,
                "row_count": 0,
                "exists": False,
            }
            for run_dir in run_dirs:
                fortna = run_dir / "FORTNA"
                info = resolve_schema_file(fortna, f"{t}.asc")
                if info["schema_path"] is None and not (fortna / f"{t}.asc").exists():
                    continue
                best["exists"] = True
                if info["schema_path"] is not None:
                    best["sources"].append(_repo_rel(info["schema_path"]))
                    best["headers"] = info["headers"] or best["headers"]
                    if info["byte_size"] == 0:
                        best["note"] = "Zero-byte ASC"
                        continue
                    id_fields = {
                        "Sorters": ["Sorter Name"],
                        "Encoders": ["Encoder Name"],
                        "WCSEvents": ["EventName"],
                        "MsgMap": ["Message_Name"],
                        "Machine": ["Machine_Name"],
                        "MsgWCS": ["Destination", "MsgText"],
                    }.get(t, ["Name"])
                    if machine and t in static_tables:
                        merged = merge_table_rows(fortna, f"{t}.asc", machine)
                        rows = [m["row"] for m in merged.get("rows") or []]
                        _h = best["headers"]
                    else:
                        _h, rows = read_asc(info["schema_path"])
                    best["row_count"] = max(best["row_count"], len(rows))
                    best["active_named"] = max(
                        best["active_named"], count_active_rows(_h, rows, id_fields)
                    )
            out.append(best)
        return out

    static = summarize(static_tables, "static_config")
    runtime = summarize(runtime_tables, "runtime_data")

    sorters = []
    for run_dir in run_dirs:
        fortna = run_dir / "FORTNA"
        info = resolve_schema_file(fortna, "Sorters.asc")
        paths = []
        if machine:
            overlay = fortna / f"Sorters.asc.{machine}"
            if overlay.is_file() and overlay.stat().st_size > 0:
                paths.append(overlay)
        if info["schema_path"] is not None:
            paths.append(info["schema_path"])
        if not paths:
            continue
        # Prefer overlay file contents for named sorter inventory
        _h, rows = read_asc(paths[0])
        for row in rows:
            name = _clean(row.get("Sorter Name"))
            if _is_placeholder(name):
                continue
            sorters.append(
                {
                    "Sorter Name": name,
                    "Encoder ioName": _clean(row.get("Encoder ioName")),
                    "Machine": _clean(row.get("Machine")),
                    "DivertEnableIO": _clean(row.get("DivertEnableIO")),
                }
            )

    # dedupe sorters by name
    seen = set()
    uniq = []
    for s in sorters:
        k = normalize_name(s["Sorter Name"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)

    return {
        "generated_at": _ts(),
        "source_of_truth": "RUN sorter/transfer/WCS tables — no finished PLC",
        "document_sources": resolve_document_sources(
            {
                "doc_keys": [
                    "FPC-Shifter-And-Sorter-Configuration",
                    "FPC-Sorter-Control-Module",
                    "FPC-New-Transfers",
                    "FPC-Machine-MsgMap-Configuraton",
                ]
            },
            docs,
        ),
        "classification": {
            "static_config": (
                "Identity, encoder binding, app control, scan boss, zone-lane, route boss/table, "
                "machine/msgmap/wcs events"
            ),
            "runtime_data": (
                "SrtTrack*, XfrTrack, MsgTrack, MsgWCS queues, SortBuff/SortData — carton/message slots"
            ),
        },
        "static_tables": static,
        "runtime_tables": runtime,
        "sorters_sample": uniq[:30],
        "gaps_engineer_required": [
            "divert_io_map — RUN lacks complete generic PLC divert-output map",
            "tracking_conveyor_chain — not fully derivable from track slots",
            "wcs_tcp_endpoints — topics discovered; peer/port wiring is configuration",
        ],
        "generation_policy": {
            "sorter_plc": "NOT_SUPPORTED / CONFIGURATION_REQUIRED — discovery only",
            "tracking_wcs_plc": "NOT_SUPPORTED",
            "note": "Do not use Greensboro gold packs as generic generation input",
        },
    }


def render_table_reference_md(kb: dict[str, Any]) -> str:
    lines = [
        "# FortnaPlus Table Reference",
        "",
        f"Generated: `{kb.get('generated_at')}`",
        "",
        "## Source of truth",
        "",
        "- **RUN ASC headers** = factual schema (fields that exist).",
        "- **Training docs** = generic semantic knowledge (purpose, how tables relate).",
        "- Finished PLC is **not** a source for this knowledge base.",
        "- No site-specific hardcoding in knowledge rules.",
        "",
        f"Tables: **{kb.get('table_count')}**",
        "",
        "## Families",
        "",
    ]
    for e in kb.get("tables") or []:
        lines.append(f"### `{e['table_name']}`")
        lines.append("")
        lines.append(f"- **Subsystem:** {e.get('subsystem')}")
        lines.append(f"- **Confidence:** {e.get('confidence')}")
        lines.append(f"- **Schema source:** `{e.get('schema_source') or 'n/a'}`")
        lines.append(f"- **Purpose:** {e.get('purpose')}")
        lines.append(f"- **Row semantics:** {e.get('row_semantics')}")
        if e.get("schema_note"):
            lines.append(f"- **Schema note:** {e['schema_note']}")
        lines.append(f"- **Identity fields:** {', '.join(f'`{x}`' for x in e.get('identity_fields') or []) or '_none_'}")
        lines.append(f"- **Key fields:** {', '.join(f'`{x}`' for x in e.get('key_fields') or []) or '_none in RUN headers_'}")
        lines.append("- **Relationship fields:**")
        rels = e.get("relationship_fields") or []
        if not rels:
            lines.append("  - _(none)_")
        else:
            for r in rels:
                lines.append(
                    f"  - `{r['field']}` → `{r['target_table']}` ({r['edge_type']})"
                    + (f" — {r['note']}" if r.get("note") else "")
                )
        lines.append("- **Active row rules:**")
        for rule in e.get("active_row_rules") or []:
            lines.append(f"  - {rule}")
        lines.append("- **Inactive row rules:**")
        for rule in e.get("inactive_row_rules") or []:
            lines.append(f"  - {rule}")
        if e.get("optional_feature_rules"):
            lines.append("- **Optional feature rules:**")
            for rule in e["optional_feature_rules"]:
                lines.append(f"  - {rule}")
        lines.append(f"- **Controller scope:** {e.get('controller_scope_behavior')}")
        lines.append("- **Generation implications:**")
        for g in e.get("generation_implications") or []:
            lines.append(f"  - {g}")
        docs = e.get("document_sources") or []
        if docs:
            lines.append("- **Document sources:**")
            for d in docs:
                loc = d.get("file") or d.get("status") or ""
                lines.append(f"  - {d.get('title')} ({loc})")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_relationship_model_md(graph: dict[str, Any], zone: dict[str, Any]) -> str:
    lines = [
        "# FortnaPlus Relationship Model",
        "",
        f"Generated: `{graph.get('generated_at')}`",
        "",
        "## Edge types",
        "",
        "| Type | Meaning |",
        "|------|---------|",
        "| `EXPLICIT_REFERENCE` | Field present on RUN header that names another table's identity |",
        "| `DOCUMENTED_RELATIONSHIP` | Training docs describe the link (may mirror an explicit FK) |",
        "| `DERIVED_RELATIONSHIP` | Inferred from naming/timer conventions evidenced in RUN (e.g. ReserveTM→Fullline) |",
        "| `OPTIONAL_RELATIONSHIP` | Field exists but link is situational / often blank |",
        "| `RUNTIME_DATA` | Queue/track slot references — not static topology |",
        "",
        f"**Nodes:** {graph.get('node_count')}  ",
        f"**Edges:** {graph.get('edge_count')}",
        "",
        "## Graph edges",
        "",
    ]
    by_type: dict[str, list] = defaultdict(list)
    for e in graph.get("edges") or []:
        by_type[e["edge_type"]].append(e)
    for et in [
        EDGE_EXPLICIT,
        EDGE_DOC,
        EDGE_DERIVED,
        EDGE_OPTIONAL,
        EDGE_RUNTIME,
    ]:
        lines.append(f"### {et}")
        lines.append("")
        items = by_type.get(et) or []
        if not items:
            lines.append("_None_")
            lines.append("")
            continue
        for e in items:
            note = f" — {e['note']}" if e.get("note") else ""
            lines.append(
                f"- `{e['from']}` → `{e['to']}` via `{e.get('via_field')}`{note}"
            )
        lines.append("")

    lines.append("## Zone model summary")
    lines.append("")
    for zk in zone.get("zone_kinds") or []:
        lines.append(f"### {zk['kind']}")
        lines.append("")
        lines.append(zk.get("definition") or "")
        tables = zk.get("run_tables") or []
        lines.append(f"- RUN tables: {', '.join(f'`{t}`' for t in tables) or '_none_'}")
        lines.append(f"- Provenance: {zk.get('provenance')}")
        lines.append("")

    lines.append("## Rules")
    lines.append("")
    lines.append("- Do not invent fields absent from RUN headers.")
    lines.append("- Convpath/Pathsets empty ⇒ no P→P topology claim.")
    lines.append("- SrtTrack/XfrTrack/MsgWCS are runtime evidence, not divert maps.")
    lines.append("- No Greensboro-specific relationship rules.")
    lines.append("")
    return "\n".join(lines)


def detect_default_machine(run_dirs: list[Path]) -> str:
    for run_dir in run_dirs:
        cfg = run_dir / "project.cfg"
        if cfg.is_file():
            text = cfg.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"MACHINENAME\s*=\s*(\S+)", text, re.I)
            if m:
                return m.group(1).strip()
        # overlay heuristic
        fortna = run_dir / "FORTNA"
        if fortna.is_dir():
            for p in fortna.glob("Sorters.asc.*"):
                suf = p.name.split(".asc.", 1)[-1]
                if suf and not suf.endswith(".bak"):
                    return suf
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir",
        action="append",
        type=Path,
        dest="run_dirs",
        help="RUN root (repeatable). Default: workspace/cp4-run/RUN and workspace/active/RUN",
    )
    ap.add_argument("--machine", default="", help="Controller name for overlay merge (optional)")
    ap.add_argument(
        "--out-kb",
        type=Path,
        default=ROOT / "tools" / "knowledge" / "fortnaplus_tables.json",
    )
    ap.add_argument(
        "--out-exports",
        type=Path,
        default=ROOT / "exports" / "fpc-knowledge",
    )
    ap.add_argument(
        "--out-docs",
        type=Path,
        default=ROOT / "docs",
    )
    args = ap.parse_args()

    run_dirs = args.run_dirs or [
        ROOT / "workspace" / "cp4-run" / "RUN",
        ROOT / "workspace" / "active" / "RUN",
    ]
    run_dirs = [p if p.is_absolute() else ROOT / p for p in run_dirs]
    run_dirs = [p for p in run_dirs if p.is_dir()]
    if not run_dirs:
        print("ERROR: no RUN dirs found", file=sys.stderr)
        return 2

    machine = args.machine or detect_default_machine(run_dirs)
    docs = load_doc_inventory(ROOT)
    schemas = discover_run_schemas(run_dirs, machine)
    entries = build_table_entries(schemas, docs)
    entries_by_name = {e["table_name"]: e for e in entries}
    graph = build_relationship_graph(entries, docs)
    zone = build_zone_model(schemas, entries_by_name)
    pe = build_pe_semantics(run_dirs)
    motor = build_motor_chain_model(run_dirs, machine)
    comm = build_communication_model(entries_by_name, schemas)
    saw = build_sawtooth_model(run_dirs, machine, docs)
    sorter = build_sorter_model(run_dirs, machine, docs)

    kb = {
        "generated_at": _ts(),
        "source_of_truth": "RUN ASC schemas + optional training doc inventory",
        "finished_plc_used": False,
        "run_dirs": [_repo_rel(p) for p in run_dirs],
        "machine_scope": machine or None,
        "training_docs": {
            "available": docs.get("available"),
            "count": docs.get("count"),
            "md_index_present": docs.get("md_index_present"),
            "sources": docs.get("sources"),
        },
        "table_count": len(entries),
        "tables": entries,
    }

    out_kb = args.out_kb if args.out_kb.is_absolute() else ROOT / args.out_kb
    out_exp = args.out_exports if args.out_exports.is_absolute() else ROOT / args.out_exports
    out_docs = args.out_docs if args.out_docs.is_absolute() else ROOT / args.out_docs
    out_kb.parent.mkdir(parents=True, exist_ok=True)
    out_exp.mkdir(parents=True, exist_ok=True)
    out_docs.mkdir(parents=True, exist_ok=True)

    out_kb.write_text(json.dumps(kb, indent=2), encoding="utf-8")
    (out_exp / "table_relationship_graph.json").write_text(
        json.dumps(graph, indent=2), encoding="utf-8"
    )
    (out_exp / "zone_model.json").write_text(json.dumps(zone, indent=2), encoding="utf-8")
    (out_exp / "pe_semantics.json").write_text(json.dumps(pe, indent=2), encoding="utf-8")
    (out_exp / "motor_chain_model.json").write_text(json.dumps(motor, indent=2), encoding="utf-8")
    (out_exp / "communication_model.json").write_text(json.dumps(comm, indent=2), encoding="utf-8")
    (out_exp / "sawtooth_model.json").write_text(json.dumps(saw, indent=2), encoding="utf-8")
    (out_exp / "sorter_model.json").write_text(json.dumps(sorter, indent=2), encoding="utf-8")

    (out_docs / "FORTNAPLUS_TABLE_REFERENCE.md").write_text(
        render_table_reference_md(kb), encoding="utf-8"
    )
    (out_docs / "FORTNAPLUS_RELATIONSHIP_MODEL.md").write_text(
        render_relationship_model_md(graph, zone), encoding="utf-8"
    )

    # key relationships = EXPLICIT + DOCUMENTED
    key_rel = sum(
        1
        for e in graph["edges"]
        if e["edge_type"] in (EDGE_EXPLICIT, EDGE_DOC)
    )
    print(
        json.dumps(
            {
                "ok": True,
                "table_count": kb["table_count"],
                "relationship_edge_count": graph["edge_count"],
                "key_relationship_count": key_rel,
                "out_kb": _repo_rel(out_kb),
                "out_exports": _repo_rel(out_exp),
                "training_docs_available": docs.get("available"),
                "machine_scope": machine or None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
