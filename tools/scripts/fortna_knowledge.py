#!/usr/bin/env python3
"""Executable FortnaPlus knowledge API (docs=semantics, RUN=facts).

Loads `tools/knowledge/fortnaplus_tables.json` (fallback: exports/fpc-knowledge/)
plus optional PE / motor-chain / zone / document-inventory artifacts.

SOURCE FIREWALL: never reads finished PLC L5X. No site-constant hardcoding.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent

KB_PRIMARY = REPO_ROOT / "tools" / "knowledge" / "fortnaplus_tables.json"
KB_FALLBACK = REPO_ROOT / "exports" / "fpc-knowledge" / "fortnaplus_tables.json"
KNOW_DIR = REPO_ROOT / "exports" / "fpc-knowledge"

PLACEHOLDERS = {
    "",
    "N/A",
    "INVALID",
    "NONE",
    "~",
    "N/A~",
    "n/a",
    "Invalid",
    "RECZERO",
}

PE_ROLE_SET = frozenset(
    {
        "DETECTION",
        "JAM",
        "FULL",
        "FULL_JAM",
        "RESERVE",
        "MERGE",
        "SCAN_TRIGGER",
        "UNKNOWN",
    }
)

# Distinct operational zone kinds — do not conflate.
ZONE_KIND_ALIASES: dict[str, str] = {
    "engineeringarea": "EngineeringArea",
    "engineering_area": "EngineeringArea",
    "engineering": "EngineeringArea",
    "area": "EngineeringArea",
    "startstop": "StartStop",
    "startstopzone": "StartStop",
    "start_stop": "StartStop",
    "start_stop_zone": "StartStop",
    "estop": "EStop",
    "estopzone": "EStop",
    "e_stop": "EStop",
    "jam": "Jam",
    "jamzone": "Jam",
    "jam_zone": "Jam",
    "full": "Full",
    "fullline": "Full",
    "fulljam": "Full",
    "full_zone": "Full",
    "sortertracking": "SorterTracking",
    "sorter_tracking": "SorterTracking",
    "sortertrackingzone": "SorterTracking",
    "tracking": "SorterTracking",
}

CANONICAL_ZONE_KINDS = (
    "EngineeringArea",
    "StartStop",
    "EStop",
    "Jam",
    "Full",
    "SorterTracking",
)

# Evidence kinds → KB interpretation (weights mirror activity classifier semantics).
EVIDENCE_KIND_KB: dict[str, dict[str, Any]] = {
    "mtrchain": {
        "weight": 3,
        "tables": ["Mtrchain"],
        "implies": ["motor_chain_participant"],
        "doc": "FPC-Motor-Startup-Chains",
    },
    "mtrchain_aux": {
        "weight": 2,
        "tables": ["Mtrchain", "Jamzones"],
        "implies": ["latch_aux"],
        "doc": "FPC-Motor-Startup-Chains",
    },
    "mtrchain_stop_zone": {
        "weight": 2,
        "tables": ["Mtrchain", "StartStopZones"],
        "implies": ["stop_zone_link"],
        "doc": "FPC-Motor-Startup-Chains",
    },
    "jam_link": {
        "weight": 3,
        "tables": ["Jamcheck", "Jamzones"],
        "implies": ["jam_pe"],
        "pe_role": "JAM",
        "doc": "FPC-Fulls-Jams-Fulljams",
    },
    "jamcheck_link": {
        "weight": 3,
        "tables": ["Jamcheck"],
        "implies": ["jam_pe"],
        "pe_role": "JAM",
        "doc": "FPC-Fulls-Jams-Fulljams",
    },
    "jamzone_link": {
        "weight": 3,
        "tables": ["Jamzones"],
        "implies": ["jam_zone"],
        "doc": "FPC-StartStopZones",
    },
    "full_link": {
        "weight": 2,
        "tables": ["Fullline"],
        "implies": ["full_pe"],
        "pe_role": "FULL",
        "doc": "FPC-Fulls-Jams-Fulljams",
    },
    "fullline_link": {
        "weight": 2,
        "tables": ["Fullline"],
        "implies": ["full_pe"],
        "pe_role": "FULL",
        "doc": "FPC-Fulls-Jams-Fulljams",
    },
    "fulljam_link": {
        "weight": 2,
        "tables": ["Fulljam"],
        "implies": ["fulljam_pe"],
        "pe_role": "FULL_JAM",
        "doc": "FPC-Fulls-Jams-Fulljams",
    },
    "startstop_link": {
        "weight": 2,
        "tables": ["StartStopZones", "Jamzones"],
        "implies": ["start_stop_zone"],
        "doc": "FPC-StartStopZones",
    },
    "saw_lane": {
        "weight": 3,
        "tables": ["SawLane", "HSSawLane"],
        "implies": ["lane_pe"],
        "pe_role": "DETECTION",
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
    "saw_merge": {
        "weight": 3,
        "tables": ["SawMerge", "HSSawMerge"],
        "implies": ["merge_participant"],
        "pe_role": "MERGE",
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
    "hssaw_link": {
        "weight": 3,
        "tables": ["HSSawLane", "HSSawMerge"],
        "implies": ["hs_sawtooth"],
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
    "hssaw_lane": {
        "weight": 3,
        "tables": ["HSSawLane"],
        "implies": ["lane_pe"],
        "pe_role": "DETECTION",
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
    "hssaw_merge": {
        "weight": 3,
        "tables": ["HSSawMerge"],
        "implies": ["merge_participant"],
        "pe_role": "MERGE",
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
    "merge_link": {
        "weight": 2,
        "tables": ["MergeBoss", "MergeInputs", "SimpleMerge", "Merges"],
        "implies": ["merge_participant"],
        "pe_role": "MERGE",
        "doc": "FPC-Merge-Modules",
    },
    "sorter_static": {
        "weight": 2,
        "tables": ["Sorters", "SrtAppControl", "SrtZoneLane"],
        "implies": ["sorter_static"],
        "doc": "FPC-Sorter-Control-Module",
    },
    "sorter_runtime": {
        "weight": 1,
        "tables": ["SrtTrack", "XfrTrack", "MsgTrack"],
        "implies": ["sorter_runtime"],
        "doc": "FPC-Sorter-Control-Module",
    },
    "sorter_table": {
        "weight": 2,
        "tables": ["Sorters"],
        "implies": ["sorter_static"],
        "doc": "FPC-Sorter-Control-Module",
    },
    "configio_link": {
        "weight": 2,
        "tables": ["Configio"],
        "implies": ["io_assignment"],
        "doc": "FPC-The-ViewIO-Screen-and-FORTNADT-Table",
    },
    "fortnadt_link": {
        "weight": 1,
        "tables": ["FORTNADT"],
        "implies": ["io_word_state"],
        "doc": "FPC-The-ViewIO-Screen-and-FORTNADT-Table",
    },
    "iocard_link": {
        "weight": 2,
        "tables": ["IOCard"],
        "implies": ["io_card"],
        "doc": "FPC-IOCard-Interfaces",
    },
    "controller_io": {
        "weight": 3,
        "tables": ["Configio", "IOCard", "Conveyor"],
        "implies": ["io_assignment"],
        "doc": "FPC-The-ViewIO-Screen-and-FORTNADT-Table",
    },
    "io_assignment": {
        "weight": 3,
        "tables": ["Configio", "Conveyor"],
        "implies": ["io_assignment"],
        "doc": "FPC-The-ViewIO-Screen-and-FORTNADT-Table",
    },
    "pe_assignment": {
        "weight": 2,
        "tables": ["Conveyor", "PeList"],
        "implies": ["detection_pe"],
        "pe_role": "DETECTION",
        "doc": "FPC-Photoeye-Status-Reporting",
    },
    "motor_link": {
        "weight": 2,
        "tables": ["Conveyor", "Mtrchain"],
        "implies": ["motor"],
        "doc": "FPC-Motor-Startup-Chains",
    },
    "path_link": {
        "weight": 2,
        "tables": ["Convpath"],
        "implies": ["path_slot"],
        "doc": None,
    },
    "convpath_link": {
        "weight": 2,
        "tables": ["Convpath"],
        "implies": ["path_slot"],
        "doc": None,
    },
    "encoder_link": {
        "weight": 2,
        "tables": ["Encoders"],
        "implies": ["encoder"],
        "doc": "FPC-Sorter-Control-Module",
    },
    "scan_trigger": {
        "weight": 2,
        "tables": ["Scanners", "SrtScanBoss"],
        "implies": ["scan_trigger_pe"],
        "pe_role": "SCAN_TRIGGER",
        "doc": "FPC-Scanner-Control-Configuration",
    },
    "reserve": {
        "weight": 2,
        "tables": ["SawLane", "Fullline"],
        "implies": ["reserve_pe"],
        "pe_role": "RESERVE",
        "doc": "FPC-HighSpeedSawtoothMerge",
    },
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_placeholder(value: Any) -> bool:
    s = str(value or "").strip()
    if s in PLACEHOLDERS:
        return True
    if s.startswith("==="):
        return True
    return False


def _norm_table_key(name: str) -> str:
    s = str(name or "").strip()
    if s.lower().endswith(".asc"):
        s = s[:-4]
    return s


def _slug_id(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return s or "unknown"


def make_decision_trace(
    decision: Any,
    run_evidence: Any,
    knowledge_rule: Any,
    document_source: Any,
    confidence: Any,
) -> dict[str, Any]:
    """Structured rule-traceability record for compiler / discovery decisions."""
    return {
        "decision": decision,
        "run_evidence": run_evidence,
        "knowledge_rule": knowledge_rule,
        "document_source": document_source,
        "confidence": confidence,
    }


class KnowledgeStore:
    """In-memory FortnaPlus knowledge base with query helpers."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        kb_path: Path | None = None,
        knowledge_dir: Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else (
            self.repo_root / "exports" / "fpc-knowledge"
        )
        self.kb_path = self._resolve_kb_path(kb_path)
        self._kb: dict[str, Any] = {}
        self._tables_by_name: dict[str, dict[str, Any]] = {}
        self._pe_semantics: dict[str, Any] | None = None
        self._motor_chain: dict[str, Any] | None = None
        self._zone_model: dict[str, Any] | None = None
        self._document_inventory: dict[str, Any] | None = None
        self._rel_graph: dict[str, Any] | None = None
        self.reload()

    def _resolve_kb_path(self, kb_path: Path | None) -> Path:
        if kb_path is not None:
            return Path(kb_path)
        primary = self.repo_root / "tools" / "knowledge" / "fortnaplus_tables.json"
        fallback = self.knowledge_dir / "fortnaplus_tables.json"
        if primary.is_file():
            return primary
        if fallback.is_file():
            return fallback
        return primary

    def reload(self) -> None:
        if not self.kb_path.is_file():
            raise FileNotFoundError(f"Knowledge base not found: {self.kb_path}")
        raw = _load_json(self.kb_path)
        if not isinstance(raw, dict):
            raise ValueError(f"Unexpected KB root type: {type(raw)}")
        self._kb = raw
        self._tables_by_name = {}
        tables = raw.get("tables") or []
        if isinstance(tables, dict):
            iterable = tables.values()
        else:
            iterable = tables
        for entry in iterable:
            if not isinstance(entry, dict):
                continue
            name = entry.get("table_name") or entry.get("table") or ""
            key = _norm_table_key(str(name))
            if not key:
                continue
            self._tables_by_name[key.lower()] = entry
            self._tables_by_name[key] = entry
        # Optional sidecar artifacts — load lazily on first access, clear cache.
        self._pe_semantics = None
        self._motor_chain = None
        self._zone_model = None
        self._document_inventory = None
        self._rel_graph = None

    # ------------------------------------------------------------------
    # Core table API
    # ------------------------------------------------------------------

    @property
    def table_count(self) -> int:
        counted = self._kb.get("table_count")
        if isinstance(counted, int):
            return counted
        return len({k.lower() for k in self._tables_by_name if isinstance(k, str)})

    def table_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for key, entry in self._tables_by_name.items():
            if not key or key != key.lower():
                continue
            name = str(entry.get("table_name") or entry.get("table") or key)
            low = name.lower()
            if low in seen:
                continue
            seen.add(low)
            names.append(_norm_table_key(name))
        return sorted(names, key=str.lower)

    def table_semantics(self, table_name: str) -> dict[str, Any] | None:
        """Return the KB table entry for `table_name`, or None."""
        key = _norm_table_key(table_name)
        if not key:
            return None
        return self._tables_by_name.get(key) or self._tables_by_name.get(key.lower())

    def subsystem_for_table(self, table_name: str) -> str | None:
        entry = self.table_semantics(table_name)
        if not entry:
            return None
        sub = entry.get("subsystem")
        return str(sub) if sub is not None else None

    def generation_implications(self, table_name: str) -> list[str]:
        entry = self.table_semantics(table_name)
        if not entry:
            return []
        raw = entry.get("generation_implications") or []
        return [str(x) for x in raw]

    def relationships_for(self, entity_or_table: str) -> dict[str, Any]:
        """Relationship field defs for a table, plus optional graph edge kinds."""
        entry = self.table_semantics(entity_or_table)
        fields = list((entry or {}).get("relationship_fields") or [])
        edge_kinds: list[str] = []
        seen_kinds: set[str] = set()
        for rel in fields:
            et = str((rel or {}).get("edge_type") or "")
            if et and et not in seen_kinds:
                seen_kinds.add(et)
                edge_kinds.append(et)

        # Optional expanded edges from table_relationship_graph.json
        graph_edges: list[dict[str, Any]] = []
        graph = self._load_rel_graph()
        if graph:
            tname = _norm_table_key(entity_or_table).lower()
            for edge in graph.get("edges") or []:
                frm = str(edge.get("from") or "").lower()
                to = str(edge.get("to") or "").lower()
                if frm == tname or to == tname:
                    graph_edges.append(dict(edge))
                    et = str(edge.get("edge_type") or "")
                    if et and et not in seen_kinds:
                        seen_kinds.add(et)
                        edge_kinds.append(et)

        return {
            "table": _norm_table_key(entity_or_table) if entry else None,
            "relationship_fields": fields,
            "edge_kinds": edge_kinds,
            "graph_edges": graph_edges,
            "references": list((entry or {}).get("references") or []),
        }

    def resolve_reference(
        self, table_name: str, field: str, value: Any = None
    ) -> dict[str, Any] | None:
        """Resolve a relationship_fields entry → target_table + edge_type."""
        entry = self.table_semantics(table_name)
        if not entry:
            return None
        field_l = str(field or "").strip().lower()
        for rel in entry.get("relationship_fields") or []:
            if str(rel.get("field") or "").strip().lower() != field_l:
                continue
            return {
                "table": _norm_table_key(table_name),
                "field": rel.get("field"),
                "value": value,
                "target_table": rel.get("target_table"),
                "edge_type": rel.get("edge_type"),
                "note": rel.get("note") or "",
            }
        return None

    def classify_row(self, table_name: str, row_dict: dict[str, Any] | None) -> str:
        """ACTIVE / INACTIVE / UNKNOWN from KB active_row_rules / inactive_row_rules.

        Heuristic string matching only — does not invent site-specific logic.
        """
        entry = self.table_semantics(table_name)
        if not entry:
            return "UNKNOWN"
        row = row_dict or {}
        active_rules = [str(r) for r in (entry.get("active_row_rules") or [])]
        inactive_rules = [str(r) for r in (entry.get("inactive_row_rules") or [])]
        identity_fields = [str(f) for f in (entry.get("identity_fields") or [])]
        key_fields = [str(f) for f in (entry.get("key_fields") or [])]

        # Collect identity-ish values for placeholder checks.
        id_vals = []
        for f in identity_fields or key_fields[:2]:
            if f in row:
                id_vals.append(row.get(f))
        if not id_vals:
            # Fall back to common name columns present on the row.
            for f in (
                "IO_Name",
                "Name",
                "Sensor_Name",
                "Desc",
                "Zone Name",
                "Motor_Name",
            ):
                if f in row:
                    id_vals.append(row.get(f))

        all_blank = bool(id_vals) and all(_is_placeholder(v) for v in id_vals)
        any_present = any(not _is_placeholder(v) for v in id_vals) if id_vals else False

        inactive_hit = False
        for rule in inactive_rules:
            rl = rule.lower()
            if "blank" in rl or "placeholder" in rl:
                if all_blank or (id_vals and all(_is_placeholder(v) for v in id_vals)):
                    inactive_hit = True
                    break
            if "old." in rl:
                src = str(row.get("_source") or row.get("source") or row.get("file") or "")
                if "old." in src.lower():
                    inactive_hit = True
                    break
            if "type=invalid" in rl.replace(" ", ""):
                if str(row.get("Type") or "").strip().upper() == "INVALID":
                    inactive_hit = True
                    break
            if "enabled" in rl and ("off" in rl or "disable" in rl or "false" in rl):
                en = str(row.get("Enabled") or "").strip().upper()
                if en in {"N", "NO", "FALSE", "0", "OFF", "DISABLE", "DISABLED"}:
                    inactive_hit = True
                    break

        if inactive_hit:
            return "INACTIVE"

        active_hit = False
        for rule in active_rules:
            rl = rule.lower()
            if "present" in rl and "not placeholder" in rl:
                # Which field(s) does the rule name?
                named = [
                    f
                    for f in (identity_fields + key_fields)
                    if f.lower() in rl
                ]
                if named:
                    if any(not _is_placeholder(row.get(f)) for f in named if f in row):
                        active_hit = True
                        break
                elif any_present:
                    active_hit = True
                    break
            if "or" in rl and "present" in rl:
                # e.g. "Sensor_Name or Desc present"
                candidates = [
                    f
                    for f in (identity_fields + key_fields + list(row.keys()))
                    if f.lower() in rl
                ]
                if any(not _is_placeholder(row.get(f)) for f in candidates):
                    active_hit = True
                    break
            if "assigned" in rl or "armed" in rl:
                # Supporting timer / enable fields — only confirm when identity present.
                timerish = [
                    f
                    for f in row
                    if "timer" in f.lower() or f.lower() in {"enabled", "enable bit"}
                ]
                if any_present and any(not _is_placeholder(row.get(f)) for f in timerish):
                    active_hit = True
                    break
            if "type not invalid" in rl:
                t = str(row.get("Type") or "").strip().upper()
                if t and t != "INVALID" and any_present:
                    active_hit = True
                    break

        if active_hit:
            return "ACTIVE"
        if all_blank:
            return "INACTIVE"
        if any_present:
            # Identity present but rules inconclusive.
            return "UNKNOWN"
        return "UNKNOWN"

    def evidence_for_device(
        self, name: str, evidence_list: list[Any] | None
    ) -> dict[str, Any]:
        """Interpret evidence kinds for a device using the KB catalog."""
        evidence_list = evidence_list or []
        kinds: list[str] = []
        interpreted: list[dict[str, Any]] = []
        pe_roles: list[str] = []
        tables: set[str] = set()
        docs: set[str] = set()
        score = 0

        for item in evidence_list:
            if isinstance(item, str):
                kind = item
                detail = None
            elif isinstance(item, dict):
                kind = str(item.get("kind") or item.get("type") or "")
                detail = item.get("detail") or item.get("value")
            else:
                continue
            if not kind:
                continue
            kinds.append(kind)
            meta = dict(EVIDENCE_KIND_KB.get(kind) or {})
            # Also allow table-name kinds: "Jamcheck", "Fullline", …
            if not meta:
                t_entry = self.table_semantics(kind)
                if t_entry:
                    meta = {
                        "weight": 1,
                        "tables": [_norm_table_key(kind)],
                        "implies": [f"table:{_norm_table_key(kind)}"],
                        "doc": None,
                    }
                    docs_list = t_entry.get("document_sources") or []
                    if docs_list and isinstance(docs_list[0], dict):
                        title = docs_list[0].get("title")
                        if title:
                            meta["doc"] = title
            weight = int(meta.get("weight") or 0)
            score += weight
            for t in meta.get("tables") or []:
                tables.add(str(t))
            if meta.get("doc"):
                docs.add(str(meta["doc"]))
            role = meta.get("pe_role")
            if role and role not in pe_roles:
                pe_roles.append(str(role))
            interpreted.append(
                {
                    "kind": kind,
                    "detail": detail,
                    "weight": weight,
                    "tables": list(meta.get("tables") or []),
                    "implies": list(meta.get("implies") or []),
                    "pe_role": role,
                    "document_source": meta.get("doc"),
                }
            )

        return {
            "name": name,
            "kinds": kinds,
            "score": score,
            "interpreted": interpreted,
            "tables": sorted(tables),
            "document_sources": sorted(docs),
            "suggested_pe_roles": pe_roles,
            "trace": make_decision_trace(
                decision={"device": name, "score": score, "pe_roles": pe_roles},
                run_evidence=kinds,
                knowledge_rule="evidence_kind_catalog",
                document_source=sorted(docs),
                confidence="HIGH" if score >= 5 else ("MEDIUM" if score >= 2 else "LOW"),
            ),
        }

    # ------------------------------------------------------------------
    # PE role helpers
    # ------------------------------------------------------------------

    def _load_optional(self, name: str) -> dict[str, Any] | None:
        path = self.knowledge_dir / name
        if not path.is_file():
            return None
        try:
            data = _load_json(path)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def pe_semantics(self) -> dict[str, Any]:
        if self._pe_semantics is None:
            self._pe_semantics = self._load_optional("pe_semantics.json") or {}
        return self._pe_semantics

    def _pe_document_sources(self) -> list[str]:
        pe = self.pe_semantics()
        docs = pe.get("document_sources") or []
        return [str(d) for d in docs]

    def _suffix_role_hints(self, pe_name: str) -> list[tuple[str, str, str]]:
        """Return [(role, confidence, evidence)] from naming conventions only."""
        pe = self.pe_semantics()
        naming = pe.get("naming_conventions") or {}
        name = str(pe_name or "").strip().upper()
        hints: list[tuple[str, str, str]] = []

        def _has_suffix(suffixes: list[str]) -> str | None:
            for sfx in suffixes:
                s = str(sfx).upper()
                if name.endswith(s):
                    return s
            return None

        jam = _has_suffix(list(naming.get("jam_eye_suffix") or ["_J"]))
        # Prefer fulljam patterns before plain _F / _J.
        fj = _has_suffix(list(naming.get("fulljam_eye_patterns") or ["_JF", "_FJ", "_JF_F"]))
        full = _has_suffix(list(naming.get("full_eye_suffix") or ["_F"]))

        # Also consult role_suffixes list when present.
        for item in (pe.get("naming") or {}).get("role_suffixes") or []:
            sfx = str(item.get("suffix") or "").upper()
            if not sfx:
                continue
            token = f"_{sfx}" if not sfx.startswith("_") else sfx
            if not name.endswith(token) and not name.endswith(sfx):
                continue
            meaning = str(item.get("meaning") or "").lower()
            conf = str(item.get("confidence") or "MEDIUM")
            # Suffix alone is supporting — never raise above MEDIUM here.
            conf = "MEDIUM" if conf == "HIGH" else conf
            if "jam/full" in meaning or "fulljam" in meaning or "combined jam" in meaning:
                hints.append(("FULL_JAM", conf, f"suffix {token} (supporting)"))
            elif meaning.startswith("jam") or "jam photoeye" in meaning:
                hints.append(("JAM", conf, f"suffix {token} (supporting)"))
            elif meaning.startswith("full") or "full photoeye" in meaning:
                hints.append(("FULL", conf, f"suffix {token} (supporting)"))
            elif "presence" in meaning or "detection" in meaning:
                hints.append(("DETECTION", conf, f"suffix {token} (supporting)"))
            elif "induct" in meaning or "infeed" in meaning:
                hints.append(("DETECTION", conf, f"suffix {token} (supporting)"))

        if fj:
            hints.append(("FULL_JAM", "MEDIUM", f"suffix {fj} (supporting)"))
        else:
            if jam:
                hints.append(("JAM", "MEDIUM", f"suffix {jam} (supporting)"))
            if full and not name.endswith("_JF") and not name.endswith("_FJ"):
                # Avoid treating _JF as plain full.
                if not any(h[0] == "FULL_JAM" for h in hints):
                    hints.append(("FULL", "MEDIUM", f"suffix {full} (supporting)"))

        # Deduplicate keeping first (higher priority) entry per role.
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for role, conf, ev in hints:
            if role in seen:
                continue
            seen.add(role)
            out.append((role, conf, ev))
        return out

    def classify_pe_roles(
        self,
        pe_name: str,
        *,
        jamcheck: bool = False,
        fullline: bool = False,
        fulljam: bool = False,
        saw_lane: bool = False,
        reserve: bool = False,
        merge: bool = False,
        scan_trigger: bool = False,
        engineer_roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Classify PE roles. Table evidence beats suffix; suffix is supporting only.

        One PE may have multiple roles. Returns role records with confidence,
        evidence, knowledge_rule, and document_source.
        """
        docs = self._pe_document_sources()
        doc_source = docs[0] if docs else "exports/fpc-knowledge/pe_semantics.json"
        pe = self.pe_semantics()
        roles_meta = {str(r.get("role") or "").lower(): r for r in (pe.get("roles") or [])}

        # Table / flag evidence (authoritative).
        table_hits: list[tuple[str, str, str, str]] = []
        # (role, confidence, evidence, knowledge_rule)
        if jamcheck:
            table_hits.append(
                (
                    "JAM",
                    "HIGH",
                    f"Jamcheck.Sensor_Name references {pe_name}",
                    "RUN_EXPLICIT Jamcheck row (table evidence beats suffix)",
                )
            )
        if fullline:
            table_hits.append(
                (
                    "FULL",
                    "HIGH",
                    f"Fullline.Sensor_Name references {pe_name}",
                    "RUN_EXPLICIT Fullline row (table evidence beats suffix)",
                )
            )
        if fulljam:
            table_hits.append(
                (
                    "FULL_JAM",
                    "HIGH",
                    f"Fulljam.Sensor_Name references {pe_name}",
                    "RUN_EXPLICIT Fulljam row (table evidence beats suffix)",
                )
            )
        if saw_lane:
            table_hits.append(
                (
                    "DETECTION",
                    "HIGH",
                    f"SawLane/HSSawLane PE field references {pe_name}",
                    "RUN_EXPLICIT saw lane PhotoEyeIO/LanePE",
                )
            )
        if reserve:
            table_hits.append(
                (
                    "RESERVE",
                    "HIGH",
                    f"SawLane.ReserveTM / reserve link for {pe_name}",
                    "RUN_EXPLICIT ReserveTM → Fullline clear timer/sensor",
                )
            )
        if merge:
            table_hits.append(
                (
                    "MERGE",
                    "HIGH",
                    f"Merge table presence/release eye references {pe_name}",
                    "RUN_EXPLICIT merge presence/release relationship",
                )
            )
        if scan_trigger:
            table_hits.append(
                (
                    "SCAN_TRIGGER",
                    "HIGH",
                    f"Scanner/trigger configuration references {pe_name}",
                    "DOCUMENTED_RELATIONSHIP + RUN when present",
                )
            )

        by_role: dict[str, dict[str, Any]] = {}

        def _add(
            role: str,
            confidence: str,
            evidence: str,
            knowledge_rule: str,
            *,
            source: str | None = None,
        ) -> None:
            role_u = str(role or "").strip().upper().replace(" ", "_")
            # Normalize aliases from pe_semantics role names.
            aliases = {
                "JAM": "JAM",
                "FULL": "FULL",
                "FULLJAM": "FULL_JAM",
                "FULL_JAM": "FULL_JAM",
                "DETECTION": "DETECTION",
                "DETECTION_PE": "DETECTION",
                "RESERVE": "RESERVE",
                "RESERVE_PE": "RESERVE",
                "MERGE": "MERGE",
                "SCAN_TRIGGER": "SCAN_TRIGGER",
                "SCAN_TRIGGER_PE": "SCAN_TRIGGER",
                "UNKNOWN": "UNKNOWN",
            }
            role_u = aliases.get(role_u, role_u)
            if role_u not in PE_ROLE_SET:
                role_u = "UNKNOWN"
            existing = by_role.get(role_u)
            rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(confidence, 0)
            if existing:
                prev_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(
                    str(existing.get("confidence")), 0
                )
                if rank > prev_rank:
                    existing["confidence"] = confidence
                    existing["knowledge_rule"] = knowledge_rule
                ev = existing.setdefault("evidence", [])
                if evidence not in ev:
                    ev.append(evidence)
                return
            meta = roles_meta.get(role_u.lower()) or roles_meta.get(
                role_u.lower().replace("_", "")
            )
            # Map FULL_JAM → fulljam etc.
            if not meta:
                soft = {
                    "JAM": "jam",
                    "FULL": "full",
                    "FULL_JAM": "fulljam",
                    "DETECTION": "detection_pe",
                    "RESERVE": "reserve_pe",
                    "SCAN_TRIGGER": "scan_trigger_pe",
                }.get(role_u)
                if soft:
                    meta = roles_meta.get(soft)
            by_role[role_u] = {
                "role": role_u,
                "confidence": confidence,
                "evidence": [evidence],
                "knowledge_rule": knowledge_rule
                or ((meta or {}).get("provenance_rule") if meta else None)
                or "pe_semantics",
                "document_source": source or doc_source,
            }

        for role, conf, evidence, rule in table_hits:
            _add(role, conf, evidence, rule)

        # Suffix is supporting only — never overrides / upgrades past table evidence.
        for role, conf, evidence in self._suffix_role_hints(pe_name):
            if role in by_role:
                # Attach as supporting evidence only.
                ev = by_role[role].setdefault("evidence", [])
                if evidence not in ev:
                    ev.append(evidence)
                continue
            _add(role, conf, evidence, "naming_convention_supporting_only")

        for raw in engineer_roles or []:
            _add(
                str(raw),
                "HIGH",
                f"engineer_roles override: {raw}",
                "ENGINEER_CONFIGURED",
                source="engineer_roles",
            )

        if not by_role:
            _add(
                "UNKNOWN",
                "LOW",
                f"No table evidence or recognized suffix for {pe_name}",
                "pe_role_unresolved",
            )

        # Stable order.
        order = [
            "DETECTION",
            "JAM",
            "FULL",
            "FULL_JAM",
            "RESERVE",
            "MERGE",
            "SCAN_TRIGGER",
            "UNKNOWN",
        ]
        return [by_role[r] for r in order if r in by_role]

    # ------------------------------------------------------------------
    # Motor chain helpers
    # ------------------------------------------------------------------

    def motor_chain_model(self) -> dict[str, Any]:
        if self._motor_chain is None:
            self._motor_chain = self._load_optional("motor_chain_model.json") or {}
        return self._motor_chain

    def motor_chain_fields(self) -> dict[str, Any]:
        model = self.motor_chain_model()
        return dict(model.get("fields") or {})

    def motor_chain_rules(self) -> list[str]:
        model = self.motor_chain_model()
        return [str(r) for r in (model.get("rules") or [])]

    def motor_chain_sample(self, motor_name: str) -> dict[str, Any] | None:
        model = self.motor_chain_model()
        target = str(motor_name or "").strip().upper()
        for sample in model.get("samples") or []:
            if str(sample.get("Motor_Name") or "").strip().upper() == target:
                return dict(sample)
        return None

    def chained_motors(self, motor_name: str) -> list[str]:
        sample = self.motor_chain_sample(motor_name)
        if not sample:
            return []
        chained = sample.get("Motor_Chained")
        if isinstance(chained, list):
            return [str(x) for x in chained if str(x).strip()]
        fields = self.motor_chain_fields().get("followers") or []
        out: list[str] = []
        for f in fields:
            v = sample.get(f)
            if v and not _is_placeholder(v):
                out.append(str(v).strip())
        return out

    def is_motor_chain_head(self, motor_name: str) -> bool | None:
        """True/False when samples present; None if motor_chain_model absent."""
        model = self.motor_chain_model()
        if not model:
            return None
        return self.motor_chain_sample(motor_name) is not None

    # ------------------------------------------------------------------
    # Zone kind helpers
    # ------------------------------------------------------------------

    def zone_model(self) -> dict[str, Any]:
        if self._zone_model is None:
            self._zone_model = self._load_optional("zone_model.json") or {}
        return self._zone_model

    def zone_kinds(self) -> list[dict[str, Any]]:
        """Canonical distinct zone kinds (EngineeringArea ≠ StartStop ≠ …)."""
        model = self.zone_model()
        raw = list(model.get("zone_kinds") or [])
        by_canon: dict[str, dict[str, Any]] = {}
        for item in raw:
            kind = str(item.get("kind") or "")
            canon = self.canonicalize_zone_kind(kind) or kind
            entry = dict(item)
            entry["canonical_kind"] = canon
            by_canon[canon] = entry

        # Ensure Full is represented even if zone_model folds it under Jam.
        if "Full" not in by_canon:
            by_canon["Full"] = {
                "kind": "Full",
                "canonical_kind": "Full",
                "definition": (
                    "Full / full-jam detection distinct from Jam zones; "
                    "Fullline and Fulljam tables."
                ),
                "run_tables": ["Fullline", "Fulljam"],
                "provenance": "RUN_EXPLICIT",
                "confidence": "HIGH",
            }
        # Normalize StartStopZone → StartStop etc. for the public API.
        ordered: list[dict[str, Any]] = []
        for canon in CANONICAL_ZONE_KINDS:
            if canon in by_canon:
                ordered.append(by_canon[canon])
            else:
                ordered.append(
                    {
                        "kind": canon,
                        "canonical_kind": canon,
                        "definition": f"{canon} zone kind",
                        "run_tables": [],
                    }
                )
        return ordered

    def canonicalize_zone_kind(self, kind: str) -> str | None:
        key = re.sub(r"[^a-z0-9]+", "", str(kind or "").strip().lower())
        if not key:
            return None
        if key in ZONE_KIND_ALIASES:
            return ZONE_KIND_ALIASES[key]
        # Soft match: startswith / contains.
        for alias, canon in ZONE_KIND_ALIASES.items():
            if key.startswith(alias) or alias.startswith(key):
                return canon
        return None

    def zone_kind_info(self, kind: str) -> dict[str, Any] | None:
        canon = self.canonicalize_zone_kind(kind) or str(kind or "")
        for item in self.zone_kinds():
            if item.get("canonical_kind") == canon or item.get("kind") == kind:
                return item
        return None

    def zone_kinds_are_distinct(self) -> bool:
        kinds = [z.get("canonical_kind") for z in self.zone_kinds()]
        return len(kinds) == len(set(kinds)) == len(CANONICAL_ZONE_KINDS)

    def zone_kind_for_table(self, table_name: str) -> str | None:
        t = _norm_table_key(table_name).lower()
        mapping = {
            "startstopzones": "StartStop",
            "estop": "EStop",
            "jamzones": "Jam",
            "jamcheck": "Jam",
            "combinedjamzones": "Jam",
            "fullline": "Full",
            "fulljam": "Full",
            "srtzonelane": "SorterTracking",
            "srttrack": "SorterTracking",
            "srttrack1": "SorterTracking",
            "srttrack2": "SorterTracking",
            "srttrack3": "SorterTracking",
            "srttrack4": "SorterTracking",
            "srttrack5": "SorterTracking",
            "srtscanboss": "SorterTracking",
            "xfrtrack": "SorterTracking",
        }
        if t in mapping:
            return mapping[t]
        for item in self.zone_kinds():
            for rt in item.get("run_tables") or []:
                if _norm_table_key(str(rt)).lower() == t:
                    return str(item.get("canonical_kind") or item.get("kind"))
        return None

    # ------------------------------------------------------------------
    # Relationship graph (optional)
    # ------------------------------------------------------------------

    def _load_rel_graph(self) -> dict[str, Any]:
        if self._rel_graph is None:
            self._rel_graph = (
                self._load_optional("table_relationship_graph.json")
                or self._load_optional("relationship_graph.json")
                or {}
            )
        return self._rel_graph

    # ------------------------------------------------------------------
    # Document metrics
    # ------------------------------------------------------------------

    def document_inventory(self) -> dict[str, Any]:
        if self._document_inventory is None:
            self._document_inventory = (
                self._load_optional("document_inventory.json") or {}
            )
        return self._document_inventory

    def _reviewed_stems(self) -> set[str]:
        stems: set[str] = set()
        try:
            import fortna_fpc_document_inventory as inv_mod  # type: ignore

            stems |= set(getattr(inv_mod, "REVIEWED", {}) or {})
        except Exception:
            pass
        inv = self.document_inventory()
        for stem in (inv.get("skims") or {}):
            stems.add(str(stem))
        return stems

    def _normalize_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Ensure document_id, canonical_path, classification, deep_review."""
        file_rel = str(
            doc.get("canonical_path")
            or doc.get("file")
            or doc.get("path")
            or ""
        ).replace("\\", "/")
        stem = Path(file_rel).stem if file_rel else str(doc.get("title") or "")
        doc_id = str(
            doc.get("document_id") or doc.get("id") or _slug_id(stem or file_rel)
        )
        # classification: prefer explicit, else document_type, else category.
        classification = (
            doc.get("classification")
            or doc.get("document_type")
            or doc.get("category")
            or "unclassified"
        )
        relevance = doc.get("relevance")
        if relevance is None:
            # Infer light relevance from REVIEWED catalog when available.
            try:
                import fortna_fpc_document_inventory as inv_mod  # type: ignore

                meta = (getattr(inv_mod, "REVIEWED", {}) or {}).get(stem) or {}
                relevance = meta.get("relevance")
                if not doc.get("classification") and not doc.get("document_type"):
                    classification = meta.get("document_type") or classification
            except Exception:
                relevance = None
        if relevance is None:
            relevance = "UNKNOWN"

        deep = doc.get("deep_review")
        if deep is None:
            deep = doc.get("reviewed")
        if deep is None:
            deep = stem in self._reviewed_stems()
        deep_review = bool(deep)

        # Prefer repo-relative training path when file is corpus-relative.
        canonical = file_rel
        if canonical and not canonical.startswith("docs/"):
            canonical = f"docs/training/{canonical.lstrip('/')}"

        return {
            "document_id": doc_id,
            "canonical_path": canonical,
            "classification": str(classification),
            "relevance": str(relevance),
            "deep_review": deep_review,
            "title": doc.get("title"),
        }

    def document_metrics(
        self, inventory: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Exact integer document metrics (no ranges).

        Returns total, by_classification, by_relevance, deep_review true/false
        counts, plus a normalized documents list.
        """
        inv = inventory if inventory is not None else self.document_inventory()
        docs_in = list(inv.get("documents") or [])
        normalized = [self._normalize_document(d) for d in docs_in if isinstance(d, dict)]

        by_classification = Counter(d["classification"] for d in normalized)
        by_relevance = Counter(d["relevance"] for d in normalized)
        deep_true = sum(1 for d in normalized if d["deep_review"] is True)
        deep_false = sum(1 for d in normalized if d["deep_review"] is False)
        total = len(normalized)

        # Prefer explicit inventory counts when they are already exact ints.
        if isinstance(inv.get("count"), int) and inv["count"] == total:
            pass
        counts_block = inv.get("counts") if isinstance(inv.get("counts"), dict) else {}
        if isinstance(counts_block.get("documents_total"), int):
            # Rich inventory may have authoritative totals; trust when lengths match.
            if counts_block["documents_total"] == total:
                if isinstance(counts_block.get("by_relevance"), dict):
                    by_relevance = Counter(
                        {str(k): int(v) for k, v in counts_block["by_relevance"].items()}
                    )
                if isinstance(counts_block.get("by_document_type"), dict):
                    by_classification = Counter(
                        {
                            str(k): int(v)
                            for k, v in counts_block["by_document_type"].items()
                        }
                    )
                if isinstance(counts_block.get("reviewed"), int):
                    deep_true = int(counts_block["reviewed"])
                    deep_false = total - deep_true

        return {
            "total": int(total),
            "by_classification": {str(k): int(v) for k, v in sorted(by_classification.items())},
            "by_relevance": {str(k): int(v) for k, v in sorted(by_relevance.items())},
            "deep_review": {
                "true": int(deep_true),
                "false": int(deep_false),
            },
            "documents": normalized,
        }


# Module-level helpers mirroring the conceptual API.
_STORE: KnowledgeStore | None = None


def get_store(**kwargs: Any) -> KnowledgeStore:
    global _STORE
    if kwargs:
        return KnowledgeStore(**kwargs)
    if _STORE is None:
        _STORE = KnowledgeStore()
    return _STORE


def table_semantics(table_name: str) -> dict[str, Any] | None:
    return get_store().table_semantics(table_name)


def relationships_for(entity_or_table: str) -> dict[str, Any]:
    return get_store().relationships_for(entity_or_table)


def classify_row(table_name: str, row_dict: dict[str, Any] | None) -> str:
    return get_store().classify_row(table_name, row_dict)


def resolve_reference(
    table_name: str, field: str, value: Any = None
) -> dict[str, Any] | None:
    return get_store().resolve_reference(table_name, field, value)


def evidence_for_device(name: str, evidence_list: list[Any] | None) -> dict[str, Any]:
    return get_store().evidence_for_device(name, evidence_list)


def subsystem_for_table(table_name: str) -> str | None:
    return get_store().subsystem_for_table(table_name)


def generation_implications(table_name: str) -> list[str]:
    return get_store().generation_implications(table_name)


def classify_pe_roles(pe_name: str, **kwargs: Any) -> list[dict[str, Any]]:
    return get_store().classify_pe_roles(pe_name, **kwargs)


def document_metrics(inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_store().document_metrics(inventory)


if __name__ == "__main__":
    store = KnowledgeStore()
    print(f"table_count={store.table_count}")
    jam = store.table_semantics("Jamcheck")
    print("Jamcheck semantics:")
    print(json.dumps(jam, indent=2, ensure_ascii=False))
