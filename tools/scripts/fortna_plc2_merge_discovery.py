#!/usr/bin/env python3
"""BLIND PLC2 2:1 merge discovery from RUN tables only.

SOURCE OF TRUTH: PLC2 RUN extract (MergeBoss / MergeInputs / MergeRoute /
Mtrchain / Jamcheck / Fulljam / Fullline / Conveyor / Configio / FORTNADT).
Never reads finished PLC2/PLC4/PLC5 L5X. Never hardcodes merge names
(P316 etc.) — names and lanes come from RUN rows + cross-table evidence.

Preserves section conveyors (P136_P1 / P136_P2); never flattens to P136.

Discovery only — does NOT emit AOI / L5X.

Usage:
  python tools/scripts/fortna_plc2_merge_discovery.py \\
    --run-dir workspace/_plc2_run_peek/RUN \\
    --machine ORNCCP2 \\
    --out exports/plc2-merge-discovery
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

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_conveyor_section_model import (  # noqa: E402
    _motor_to_section,
    _section_from_pe_or_ssv,
    discover_sections,
    infer_downstream_from_mtrchain,
)
from fortna_site_model import merge_table_rows  # noqa: E402

CLASS_CANDIDATE = "CANDIDATE"
CLASS_PROVEN = "PROVEN"
CLASS_UNRESOLVED = "UNRESOLVED"

BLANK = frozenset({"", "N/A", "INVALID", "NONE", "~", "N/A~", "n/a", "0", "0.000"})
_CHAIN_COLS = tuple(f"Motor_Chained{i}" for i in range(1, 11))
_P_TOKEN_RE = re.compile(r"(P\d{2,4}(?:_P\d+)?)", re.I)
_BOSS_NUM_RE = re.compile(r"(?:MERGE[_ ]*)?(\d{2,4})", re.I)
_TIMER_PE_RE = re.compile(
    r"(?:tm(?:fc)?)?(?:SSV)?(?:EZ)?PE(\d{2,4})(?:_([Pp]\d+))?",
    re.I,
)
_SECTION_SUFFIX_RE = re.compile(r"^P\d{2,4}_P\d+$", re.I)

# Paths that must never be opened by this discovery module.
FORBIDDEN_PATH_NEEDLES = (
    "Finished.L5X",
    "PLC2Finished",
    "PLC4Finished",
    "PLC5Finished",
    "ORLY_Greensboro_NC_PLC2",
    "ORLY_Greensboro_NC_PLC4",
    "ORLY_Greensboro_NC_PLC5",
    "ORLY_Greensboro_NC_PLC2s",
    "ORLY_Greensboro_NC_PLC4S",
    "ORLY_Greensboro_NC_PLC5S",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(val: Any) -> str:
    s = str(val or "").strip().strip('"')
    if not s or s.upper() in BLANK or s.startswith("==="):
        return ""
    return s


def _norm_run_dir(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return (run_dir / "RUN").resolve()
    if (run_dir / "project.cfg").is_file():
        return run_dir.resolve()
    return run_dir.resolve()


def _is_valid_flag(val: Any) -> bool:
    return _clean(val).upper() in {"Y", "YES", "1", "TRUE"}


def _active_name(row: dict[str, str], *keys: str) -> str:
    for k in keys:
        v = _clean(row.get(k))
        if v:
            return v
    return ""


def _p_token(text: str) -> str | None:
    m = _P_TOKEN_RE.search(text or "")
    return m.group(1).upper() if m else None


def _sections_from_timer(timer: str) -> list[str]:
    """Extract conveyor section ids from MergeInputs timer names (keep _P1/_P2)."""
    t = _clean(timer)
    if not t:
        return []
    out: list[str] = []
    for m in _TIMER_PE_RE.finditer(t):
        digits = m.group(1)
        sec = (m.group(2) or "").upper()
        if sec:
            out.append(f"P{digits}_{sec}")
        else:
            out.append(f"P{digits}")
    return out


def _prefer_section(candidates: list[str]) -> str | None:
    """Pick best section id: prefer explicit _P1/_P2 over bare parent; never invent."""
    cleaned = [c.upper() for c in candidates if c]
    if not cleaned:
        return None
    # Prefer explicit section suffixes.
    suffixed = [c for c in cleaned if _SECTION_SUFFIX_RE.match(c)]
    pool = suffixed or cleaned
    counts = Counter(pool)
    best, n = counts.most_common(1)[0]
    # Require uniqueness at top count unless only one distinct value.
    tops = [k for k, v in counts.items() if v == n]
    if len(tops) == 1:
        return tops[0]
    # Tie: prefer suffix form.
    for t in tops:
        if _SECTION_SUFFIX_RE.match(t):
            return t
    return tops[0]


def _boss_number(boss_name: str) -> str | None:
    """Extract numeric token from RUN boss name (e.g. MERGE_316_SPUR → 316)."""
    n = _clean(boss_name)
    if not n:
        return None
    m = re.search(r"MERGE[_ ]*(\d{2,4})", n, re.I)
    if m:
        return m.group(1)
    m = _BOSS_NUM_RE.search(n)
    return m.group(1) if m else None


def classify_merge_source(boss_name: str) -> str:
    """Classify MergeBoss by RUN name tokens only — no invented semantics.

    Returns one of: SPUR | 2-1 | 3-1 | UNKNOWN
    """
    n = (_clean(boss_name) or "").upper()
    if not n:
        return "UNKNOWN"
    if "SPUR" in n:
        return "SPUR"
    if re.search(r"3\s*[-_/]?\s*1", n) or "3-1" in n or "3_1" in n:
        return "3-1"
    if re.search(r"2\s*[-_/]?\s*1", n) or "2-1" in n or "2_1" in n:
        return "2-1"
    return "UNKNOWN"


def _index_mtrchain_by_motor(fortna: Path, machine: str) -> dict[str, dict[str, str]]:
    """Motor_Name → Mtrchain row (first hit). Shared across MergeInput ReleaseIO lookups."""
    out: dict[str, dict[str, str]] = {}
    for ent in _load_table(fortna, "Mtrchain", machine):
        row = _row_dict(ent)
        motor = _clean(row.get("Motor_Name")).upper()
        if motor and motor not in out:
            out[motor] = row
    return out


def _index_conveyor_types(fortna: Path, machine: str) -> dict[str, str]:
    """IO_Name → Type from Conveyor.asc (machine-merged)."""
    out: dict[str, str] = {}
    for ent in _load_table(fortna, "Conveyor", machine):
        row = _row_dict(ent)
        name = _clean(row.get("IO_Name")).upper()
        typ = _clean(row.get("Type")).upper()
        if name and typ:
            out[name] = typ
    return out


def _resolve_release_io_mtrchain(
    release_io: str,
    *,
    mtr_by_motor: dict[str, dict[str, str]],
    conveyor_types: dict[str, str],
) -> dict[str, Any]:
    """ReleaseIO → Mtrchain → physical conveyor + Next.

    Fortna relationship (do NOT collapse):
      ReleaseIO (e.g. M314)
        → Motor_Chained1 = physical release conveyor (P314)
        → Motor_Chained2 = Next (P316 when a P-tag)
        → Timer / Aux (latch)
    """
    release = _clean(release_io).upper()
    result: dict[str, Any] = {
        "release_io": release or None,
        "physical_release_conveyor": None,
        "next_conveyor": None,
        "next_conveyor_type": None,
        "physical_release_type": None,
        "timer": None,
        "latch_aux": None,
        "mtrchain_row_found": False,
        "evidence": [],
        "unresolved": [],
    }
    if not release:
        result["unresolved"].append("release_io:missing")
        return result

    # SSV / PE release (e.g. SSVEZPE136_P1) — not a motor chain release
    if release.startswith("SSV") or "PE" in release and not re.match(r"^M\d+", release):
        pe_sec = _section_from_pe_or_ssv(release)
        result["evidence"].append(
            {
                "kind": "release_io_ssv_or_pe",
                "table": "MergeInputs.asc",
                "release_io": release,
                "section_from_name": pe_sec.upper() if pe_sec else None,
                "note": "ReleaseIO is SSV/PE — no Mtrchain Motor_Chained1/Next path",
            }
        )
        if pe_sec:
            result["physical_release_conveyor"] = pe_sec.upper()
            result["physical_release_type"] = conveyor_types.get(pe_sec.upper())
        else:
            result["unresolved"].append(f"release_io:{release}:ssv_unresolved")
        return result

    row = mtr_by_motor.get(release)
    if not row:
        # Try motor→section then M{n} from section
        sec = _motor_to_section(release)
        if sec:
            row = mtr_by_motor.get(f"M{sec[1:]}") or mtr_by_motor.get(release)
        if not row:
            result["unresolved"].append(f"release_io:{release}:mtrchain_missing")
            result["evidence"].append(
                {
                    "kind": "release_io_mtrchain_miss",
                    "table": "Mtrchain.asc",
                    "release_io": release,
                }
            )
            return result

    result["mtrchain_row_found"] = True
    chained1 = _clean(row.get("Motor_Chained1")).upper()
    chained2 = _clean(row.get("Motor_Chained2")).upper()
    timer = _clean(row.get("Timer_Name"))
    aux = _clean(row.get("Motor_Aux"))
    result["timer"] = timer or None
    result["latch_aux"] = aux or None

    # Motor_Chained1 is the physical conveyor under this motor
    phys = None
    if chained1 and re.match(r"^P\d{2,4}(?:_P\d+)?$", chained1, re.I):
        phys = chained1
    elif chained1:
        pe = _section_from_pe_or_ssv(chained1)
        if pe:
            phys = pe.upper()
    if not phys:
        # Fallback: motor name M314 → P314
        phys = (_motor_to_section(release) or "").upper() or None

    nxt = None
    if chained2 and re.match(r"^P\d{2,4}(?:_P\d+)?$", chained2, re.I):
        nxt = chained2

    result["physical_release_conveyor"] = phys
    result["next_conveyor"] = nxt
    if phys:
        result["physical_release_type"] = conveyor_types.get(phys)
    if nxt:
        result["next_conveyor_type"] = conveyor_types.get(nxt)

    result["evidence"].append(
        {
            "kind": "release_io_mtrchain",
            "table": "Mtrchain.asc",
            "release_io": release,
            "motor_chained1": chained1 or None,
            "motor_chained2": chained2 or None,
            "physical_release_conveyor": phys,
            "next_conveyor": nxt,
            "timer": timer or None,
            "latch_aux": aux or None,
            "rule": (
                "ReleaseIO → Mtrchain.Motor_Name → Motor_Chained1=physical conveyor; "
                "Motor_Chained2=Next when P-tag"
            ),
        }
    )
    if not phys:
        result["unresolved"].append(f"release_io:{release}:physical_conveyor_unresolved")
    return result


def _load_table(fortna: Path, stem: str, machine: str) -> list[dict[str, Any]]:
    merged = merge_table_rows(fortna, f"{stem}.asc", machine)
    return list(merged.get("rows") or [])


def _row_dict(entry: dict[str, Any]) -> dict[str, str]:
    return dict(entry.get("row") or {})


def _resolve_lane_section(
    row: dict[str, str],
    *,
    known_sections: set[str],
    mtr_ssv_by_merge: dict[str, set[str]],
    boss_name: str,
) -> tuple[str | None, list[dict[str, Any]], list[str]]:
    """Resolve one MergeInputs lane to a section conveyor with evidence votes."""
    evidence: list[dict[str, Any]] = []
    unresolved: list[str] = []
    votes: list[tuple[str, str]] = []  # (section, source)

    name = _active_name(row, "Name")
    presence = _clean(row.get("Presense") or row.get("Presence"))
    release = _clean(row.get("ReleaseIO"))

    pe_sec = _section_from_pe_or_ssv(presence) if presence else None
    if pe_sec:
        votes.append((pe_sec.upper(), "mergeinputs_presense"))
        evidence.append(
            {
                "kind": "mergeinputs_presense",
                "table": "MergeInputs.asc",
                "lane": name,
                "presense": presence,
                "section": pe_sec.upper(),
            }
        )

    rel_sec = None
    if release:
        rel_sec = _section_from_pe_or_ssv(release) or _motor_to_section(release)
        if rel_sec:
            votes.append((rel_sec.upper(), "mergeinputs_releaseio"))
            evidence.append(
                {
                    "kind": "mergeinputs_releaseio",
                    "table": "MergeInputs.asc",
                    "lane": name,
                    "release_io": release,
                    "section": rel_sec.upper(),
                }
            )

    timer_secs: list[str] = []
    for key in (
        "FullClearTimerName",
        "ClrTimerName",
        "RunTimerName",
        "LnClrTimerName",
    ):
        timer_secs.extend(_sections_from_timer(row.get(key) or ""))
    # Prefer suffix forms from timers when present.
    for ts in timer_secs:
        votes.append((ts.upper(), "mergeinputs_timer"))
    if timer_secs:
        evidence.append(
            {
                "kind": "mergeinputs_timer",
                "table": "MergeInputs.asc",
                "lane": name,
                "sections": sorted({t.upper() for t in timer_secs}),
            }
        )

    lane_tok = _p_token(name)
    if lane_tok:
        # Lane name often lacks _P1/_P2 — keep as weak vote only when no suffix
        # vote exists for the same family, else ignore bare parent.
        votes.append((lane_tok.upper(), "mergeinputs_lane_name"))
        evidence.append(
            {
                "kind": "mergeinputs_lane_name",
                "table": "MergeInputs.asc",
                "lane": name,
                "section": lane_tok.upper(),
            }
        )

    # Collapse lane-local votes first (do not flood with all merge Mtrchain tags).
    by_source: dict[str, list[str]] = defaultdict(list)
    for sec, src in votes:
        by_source[src].append(sec)

    source_for_section: dict[str, set[str]] = defaultdict(set)
    for src, secs in by_source.items():
        pick = _prefer_section(secs)
        if not pick:
            continue
        if src == "mergeinputs_timer":
            suff = [s for s in secs if _SECTION_SUFFIX_RE.match(s)]
            pick = _prefer_section(suff or secs) or pick
        source_for_section[pick].add(src)
        parent = re.sub(r"_P\d+$", "", pick)
        if parent != pick:
            source_for_section[parent].discard(src)

    # Drop bare parent when a suffix child of same family has PE/timer support.
    for sec in list(source_for_section.keys()):
        if _SECTION_SUFFIX_RE.match(sec):
            parent = re.sub(r"_P\d+$", "", sec)
            if parent in source_for_section:
                child_sources = source_for_section[sec]
                if child_sources & {
                    "mergeinputs_presense",
                    "mergeinputs_releaseio",
                    "mergeinputs_timer",
                }:
                    source_for_section.pop(parent, None)

    # Corroborate with Mtrchain SSV only when it matches an existing lane-local vote.
    boss_num = _boss_number(boss_name)
    mtr_secs = set()
    if boss_num:
        mtr_secs = {s.upper() for s in mtr_ssv_by_merge.get(boss_num, set())}
        if mtr_secs:
            evidence.append(
                {
                    "kind": "mtrchain_merge_ssv",
                    "table": "Mtrchain.asc",
                    "boss_number": boss_num,
                    "sections": sorted(mtr_secs),
                }
            )
            for sec in list(source_for_section.keys()):
                if sec in mtr_secs:
                    source_for_section[sec].add("mtrchain_merge_ssv")

    if not source_for_section:
        unresolved.append(f"lane:{name or '?'}:no_section_votes")
        return None, evidence, unresolved

    # Weight: timer + lane_name are stronger than presence/release alone when they
    # disagree (spur induct PE often sits on curve motor P{n+2} while lane is P{n}).
    def _score(sec: str, srcs: set[str]) -> tuple:
        weight = 0
        if "mergeinputs_timer" in srcs:
            weight += 3
        if "mergeinputs_lane_name" in srcs:
            weight += 3
        if "mergeinputs_presense" in srcs:
            weight += 1
        if "mergeinputs_releaseio" in srcs:
            weight += 1
        if "mtrchain_merge_ssv" in srcs:
            weight += 2
        return (
            weight,
            len(srcs),
            1 if _SECTION_SUFFIX_RE.match(sec) else 0,
            sec,
        )

    ranked = sorted(source_for_section.items(), key=lambda kv: _score(kv[0], kv[1]), reverse=True)
    best_sec, best_sources = ranked[0]
    best_score = _score(best_sec, best_sources)
    tied = [s for s, srcs in ranked if _score(s, srcs)[:3] == best_score[:3]]
    if len(tied) > 1:
        # Prefer section corroborated by Mtrchain SSV among ties.
        mtr_tied = [s for s in tied if s in mtr_secs]
        if len(mtr_tied) == 1:
            best_sec = mtr_tied[0]
            best_sources = source_for_section[best_sec]
        else:
            suff_tied = [s for s in tied if _SECTION_SUFFIX_RE.match(s)]
            if len(suff_tied) == 1:
                best_sec = suff_tied[0]
                best_sources = source_for_section[best_sec]
            else:
                unresolved.append(
                    f"lane:{name or '?'}:ambiguous_sections:{','.join(sorted(tied))}"
                )
                return None, evidence, unresolved

    if best_sec not in known_sections and known_sections:
        evidence.append(
            {
                "kind": "section_not_in_discover_sections",
                "section": best_sec,
                "note": "Derived from MergeInputs/Mtrchain; not listed in discover_sections",
            }
        )

    evidence.append(
        {
            "kind": "lane_section_resolution",
            "lane": name,
            "section": best_sec,
            "sources": sorted(best_sources),
            "source_count": len(best_sources),
            "score": list(best_score[:3]),
        }
    )
    if len(best_sources) < 2:
        unresolved.append(f"lane:{name or '?'}:{best_sec}:single_source_only")
    return best_sec, evidence, unresolved


def _collect_merge_mtrchain(
    fortna: Path, machine: str
) -> tuple[dict[str, list[dict[str, str]]], dict[str, set[str]], dict[str, str]]:
    """Index Mtrchain merge-latch rows by boss number.

    Returns:
      by_num: boss_number → list of mtrchain rows
      ssv_sections: boss_number → chained SSV-derived sections
      discharge_hint: boss_number → Motor_Name section when Motor_Name is P-tag
    """
    by_num: dict[str, list[dict[str, str]]] = defaultdict(list)
    ssv_sections: dict[str, set[str]] = defaultdict(set)
    discharge_hint: dict[str, str] = {}

    # Pass 1: gather all rows (need sibling lookup for named 2-1 latch → P600).
    all_rows: list[dict[str, str]] = []
    for ent in _load_table(fortna, "Mtrchain", machine):
        all_rows.append(_row_dict(ent))

    for row in all_rows:
        timer = _clean(row.get("Timer_Name"))
        aux = _clean(row.get("Motor_Aux"))
        blob = f"{timer} {aux}"
        if "MERGE" not in blob.upper():
            continue
        nums = set(re.findall(r"MERGE[_ ]*(\d{2,4})", blob, flags=re.I))
        nums |= set(re.findall(r"P(\d{2,4})_\d+-\d+_MERGE", blob, flags=re.I))
        nums |= set(re.findall(r"LATCH_P(\d{2,4})_", blob, flags=re.I))
        # LATCH_MERGE_316 / LATCH_MERGE_316_A (no P prefix)
        nums |= set(re.findall(r"LATCH_MERGE[_ ]*(\d{2,4})", blob, flags=re.I))
        # Named 2-1 latch (LATCH_2-1_MERGE_CP6): derive number from Motor_Chained1
        # on this row or Aux-linked sibling (VFD600_EN → P600).
        if not nums and re.search(r"LATCH_.*2\s*[-_/]?\s*1.*MERGE|2\s*[-_/]?\s*1.*MERGE", blob, re.I):
            chained1 = _clean(row.get("Motor_Chained1")).upper()
            if re.match(r"^P(\d{2,4})$", chained1):
                nums.add(re.match(r"^P(\d{2,4})$", chained1).group(1))
            else:
                # Follow Aux into sibling motor whose Motor_Aux matches and
                # Motor_Chained1 is the discharge P-tag (VFD600_EN → P600).
                tip = aux.upper() if aux else ""
                if tip:
                    for sib in all_rows:
                        if _clean(sib.get("Motor_Aux")).upper() != tip:
                            continue
                        c1 = _clean(sib.get("Motor_Chained1")).upper()
                        m = re.match(r"^P(\d{2,4})$", c1)
                        if m:
                            nums.add(m.group(1))
                            break
        if not nums:
            continue
        motor = _clean(row.get("Motor_Name"))
        motor_sec = _motor_to_section(motor) if motor else None
        for num in nums:
            by_num[num].append(row)
            if motor_sec and re.match(r"^P\d{2,4}$", motor_sec, re.I):
                # Discharge hint ONLY when the latch motor identity is P{num}
                # (e.g. M406 / LATCH_P406_3-1_MERGE). Induct-side motors on
                # SPUR merges (M314 + LATCH_MERGE_316) must not become discharge.
                if motor_sec.upper() == f"P{num}":
                    discharge_hint[num] = motor_sec.upper()
                elif re.search(rf"LATCH_P{num}[_ ]", blob, re.I) and motor_sec.upper() == f"P{num}":
                    discharge_hint[num] = motor_sec.upper()
            # Named latch discharge: Motor_Chained1 == P{num} on merge latch row
            c1 = _clean(row.get("Motor_Chained1")).upper()
            if c1 == f"P{num}":
                discharge_hint.setdefault(num, c1)
            for col in _CHAIN_COLS:
                chained = _clean(row.get(col))
                if not chained:
                    continue
                pe_sec = _section_from_pe_or_ssv(chained)
                if pe_sec:
                    ssv_sections[num].add(pe_sec.upper())
                elif re.match(r"^P\d{2,4}(?:_P\d+)?$", chained, re.I):
                    ssv_sections[num].add(chained.upper())
    # Second pass: VFD600_EN-style rows where Aux links to 2-1 latch family and
    # Motor_Chained1 is the discharge conveyor — fill discharge_hint when empty.
    for row in all_rows:
        c1 = _clean(row.get("Motor_Chained1")).upper()
        m = re.match(r"^P(\d{2,4})$", c1)
        if not m:
            continue
        num = m.group(1)
        if num in discharge_hint:
            continue
        aux = _clean(row.get("Motor_Aux")).upper()
        timer = _clean(row.get("Timer_Name")).upper()
        blob = f"{timer} {aux} {_clean(row.get('Motor_Name')).upper()}"
        if "600" in num or re.search(r"2\s*[-_/]?\s*1|MERGE", blob):
            # Only adopt when some merge-latch row already keyed this number
            if num in by_num:
                discharge_hint[num] = c1
    return by_num, ssv_sections, discharge_hint


def _collect_jamchecks(
    fortna: Path, machine: str
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ent in _load_table(fortna, "Jamcheck", machine):
        row = _row_dict(ent)
        owner = _clean(row.get("Jam_Owner"))
        if owner and owner != machine:
            continue
        zone = _clean(row.get("Zone"))
        conv = _clean(row.get("Conveyor_Name"))
        blob = f"{zone} {conv}".upper()
        # MERGE or abbreviated MRG (e.g. "Recirc Spur Mrg")
        if "MERGE" not in blob and not re.search(r"\bMRG\b", blob):
            continue
        rows.append(row)
    return rows


def _match_jam_for_boss(
    jam_rows: list[dict[str, str]], boss_name: str, boss_num: str | None
) -> dict[str, str] | None:
    """Match Jamcheck row to MergeBoss via number and/or zone name tokens.

    Numeric bosses (MERGE_400_2-1 → 400) match P{num} / zone digits.
    Named bosses (2-1 SERVO, RECIRC SPUR) match zone class tokens from RUN
    (e.g. "2-1 Merge CP6", "Recirc Spur Mrg") — never invent from geometry.
    """
    source_class = classify_merge_source(boss_name)
    boss_u = (_clean(boss_name) or "").upper()
    boss_tokens = {t for t in re.split(r"[\s_\-/]+", boss_u) if len(t) >= 3}

    if boss_num:
        for row in jam_rows:
            zone = _clean(row.get("Zone"))
            conv = _clean(row.get("Conveyor_Name"))
            sensor = _clean(row.get("Sensor_Name") or row.get("Desc"))
            blob = f"{zone} {conv} {sensor}"
            if re.search(rf"\b{re.escape(boss_num)}\b", blob):
                return row
            if conv.upper() == f"P{boss_num}":
                return row
        for row in jam_rows:
            zone = _clean(row.get("Zone"))
            if boss_num and boss_num in zone:
                return row

    # Named / non-numeric bosses: zone class + token overlap (RUN-explicit only).
    scored: list[tuple[int, dict[str, str]]] = []
    for row in jam_rows:
        zone = _clean(row.get("Zone"))
        if not zone:
            continue
        zone_u = zone.upper()
        if "MERGE" not in zone_u and "MRG" not in zone_u:
            continue
        score = 0
        if source_class == "2-1" and re.search(r"2\s*[-_/]?\s*1", zone_u):
            score += 3
        if source_class == "3-1" and re.search(r"3\s*[-_/]?\s*1", zone_u):
            score += 3
        if source_class == "SPUR" and "SPUR" in zone_u:
            score += 3
        zone_tokens = {t for t in re.split(r"[\s_\-/]+", zone_u) if len(t) >= 3}
        overlap = boss_tokens & zone_tokens
        # Drop weak class-only tokens from overlap credit
        overlap -= {"MERGE", "MRG", "CTRL"}
        score += len(overlap)
        if score >= 3:
            scored.append((score, row))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    # Ambiguous equal top scores → no match (do not invent)
    tops = [r for s, r in scored if s == scored[0][0]]
    if len(tops) != 1:
        return None
    return tops[0]


def _build_topology_edges(
    *,
    downstream_map: dict[str, str],
    mtr_by_num: dict[str, list[dict[str, str]]],
    ssv_by_num: dict[str, set[str]],
    discharge_hint: dict[str, str],
    jam_by_num: dict[str, dict[str, str]],
) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    """Build directed section→downstream edges; return indegree map + edge evidence."""
    edges: dict[str, set[str]] = defaultdict(set)  # dst → srcs
    edge_ev: list[dict[str, Any]] = []

    for src, dst in (downstream_map or {}).items():
        if not src or not dst:
            continue
        edges[dst.upper()].add(src.upper())
        edge_ev.append(
            {
                "kind": "mtrchain_fullline_downstream",
                "from": src.upper(),
                "to": dst.upper(),
            }
        )

    # Enrich from merge-latch chaining: inbound SSV/PE sections → discharge
    for num, secs in ssv_by_num.items():
        dst = discharge_hint.get(num)
        jam = jam_by_num.get(num)
        if not dst and jam:
            dst = _clean(jam.get("Conveyor_Name")).upper() or None
        if not dst:
            continue
        for sec in secs:
            su = sec.upper()
            # Don't self-loop discharge onto itself
            if su == dst:
                continue
            # Skip mechanical body tags that equal jam body when dst is different
            edges[dst].add(su)
            edge_ev.append(
                {
                    "kind": "mtrchain_merge_latch_inbound",
                    "boss_number": num,
                    "from": su,
                    "to": dst,
                }
            )
    return edges, edge_ev


def _resolve_downstream(
    *,
    boss_name: str,
    boss_num: str | None,
    main_lane: str | None,
    induct_lane: str | None,
    jam_row: dict[str, str] | None,
    discharge_hint: dict[str, str],
    known_sections: dict[str, Any],
    topology_edges: dict[str, set[str]],
) -> tuple[str | None, list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    unresolved: list[str] = []
    candidates: list[tuple[str, str]] = []

    if boss_num and boss_num in discharge_hint:
        d = discharge_hint[boss_num]
        candidates.append((d, "mtrchain_latch_motor"))
        evidence.append(
            {
                "kind": "mtrchain_latch_discharge",
                "table": "Mtrchain.asc",
                "boss_number": boss_num,
                "section": d,
            }
        )

    jam_conv = _clean(jam_row.get("Conveyor_Name")).upper() if jam_row else ""
    if jam_conv:
        evidence.append(
            {
                "kind": "jamcheck_conveyor",
                "table": "Jamcheck.asc",
                "conveyor": jam_conv,
                "zone": _clean(jam_row.get("Zone")) if jam_row else "",
                "sensor": _clean(jam_row.get("Sensor_Name")) if jam_row else "",
            }
        )

    spur = "SPUR" in (boss_name or "").upper()
    if spur and main_lane and _SECTION_SUFFIX_RE.match(main_lane):
        parent = re.sub(r"_P\d+$", "", main_lane)
        p2 = f"{parent}_P2"
        if p2 in known_sections or p2.upper() in {s.upper() for s in known_sections}:
            # Require independent reference: topology inbound or section provenance
            info = known_sections.get(p2) or known_sections.get(p2.upper()) or {}
            if info or any(p2 in srcs for srcs in topology_edges.values()):
                candidates.append((p2, "spur_main_p2_continuation"))
                evidence.append(
                    {
                        "kind": "spur_downstream_p2",
                        "rule": (
                            "SPUR MergeBoss + mainLane P{n}_P1 + proven section "
                            "P{n}_P2 → downstream continuation"
                        ),
                        "main_lane": main_lane,
                        "downstream": p2,
                    }
                )

    # Topology convergence target that includes both lanes as sources
    if main_lane and induct_lane:
        for dst, srcs in topology_edges.items():
            if main_lane.upper() in srcs and induct_lane.upper() in srcs:
                candidates.append((dst, "topology_indegree_lanes"))
                evidence.append(
                    {
                        "kind": "topology_convergence",
                        "downstream": dst,
                        "sources": sorted(srcs),
                    }
                )

    if not candidates:
        # Non-spur: jam conveyor is discharge when matched to this boss.
        # Numeric bosses require P{boss_num}; named bosses (2-1 SERVO → P600)
        # trust the Jamcheck row already matched via zone tokens.
        if jam_conv and not spur:
            if boss_num and jam_conv == f"P{boss_num}":
                candidates.append((jam_conv, "jamcheck_discharge"))
            elif not boss_num and jam_row:
                candidates.append((jam_conv, "jamcheck_discharge"))
                evidence.append(
                    {
                        "kind": "jamcheck_named_boss_discharge",
                        "conveyor": jam_conv,
                        "boss": boss_name,
                        "zone": _clean(jam_row.get("Zone")),
                        "rule": "Named MergeBoss matched Jamcheck zone → Conveyor_Name discharge",
                    }
                )
            elif boss_num and jam_row and jam_conv.startswith("P"):
                # Boss number present but discharge tag differs (rare) — only when
                # jam was matched to this boss and zone carries the class token.
                zone_u = _clean(jam_row.get("Zone")).upper()
                if "MERGE" in zone_u or "MRG" in zone_u:
                    if boss_num in zone_u or boss_num in jam_conv:
                        candidates.append((jam_conv, "jamcheck_discharge"))
        elif jam_conv and spur:
            # Spur jam body is mergeSection3, not necessarily downstream
            evidence.append(
                {
                    "kind": "jamcheck_merge_body",
                    "conveyor": jam_conv,
                    "note": "SPUR jam conveyor treated as merge body, not discharge",
                }
            )

    if not candidates:
        unresolved.append("downstream:unresolved")
        return None, evidence, unresolved

    # Prefer spur _P2 continuation over latch/topology when boss is SPUR.
    priority = {
        "spur_main_p2_continuation": 5,
        "topology_indegree_lanes": 3,
        "mtrchain_latch_motor": 4,
        "jamcheck_discharge": 2,
    }
    if spur:
        # Topology edges seeded from induct latch motors are not discharge.
        candidates = [c for c in candidates if c[1] != "mtrchain_latch_motor"] or candidates
        priority["topology_indegree_lanes"] = 1
    candidates.sort(key=lambda c: (priority.get(c[1], 0), c[0]), reverse=True)
    best = candidates[0][0]
    # If latch and jam agree on same P{num} for non-spur → strong
    evidence.append(
        {
            "kind": "downstream_resolution",
            "downstream": best,
            "method": candidates[0][1],
            "all_candidates": [{"section": s, "method": m} for s, m in candidates],
        }
    )
    return best, evidence, unresolved


def discover_plc2_merges(
    run_dir: Path | str,
    machine: str = "ORNCCP2",
) -> dict[str, Any]:
    """Discover 2:1 merges from RUN only. Returns MergeModel-like report dict."""
    run_dir = _norm_run_dir(run_dir)
    machine = (machine or "").strip()
    fortna = run_dir / "FORTNA"
    if not fortna.is_dir():
        raise FileNotFoundError(f"No FORTNA tables under {run_dir}")

    # Guard: this function only touches RUN paths under run_dir.
    tables_read = [
        "Conveyor",
        "MergeBoss",
        "MergeInputs",
        "MergeRoute",
        "MergeRunOutputs",
        "Mtrchain",
        "Jamcheck",
        "Fulljam",
        "Fullline",
        "Configio",
        "FORTNADT",
        "Stop",
    ]

    section_model = discover_sections(run_dir, machine)
    known_sections: dict[str, Any] = dict(section_model.get("sections") or {})
    known_ids = set(known_sections.keys())
    prefer = section_model.get("preferred_induct") or {}
    downstream_map = infer_downstream_from_mtrchain(run_dir, preferred_induct=prefer)

    mtr_by_num, ssv_by_num, discharge_hint = _collect_merge_mtrchain(fortna, machine)
    jam_rows = _collect_jamchecks(fortna, machine)
    jam_by_num: dict[str, dict[str, str]] = {}
    for jr in jam_rows:
        conv = _clean(jr.get("Conveyor_Name"))
        m = re.match(r"^P(\d{2,4})$", conv, re.I)
        if m:
            jam_by_num[m.group(1)] = jr
        zone = _clean(jr.get("Zone"))
        for num in re.findall(r"(\d{2,4})", zone):
            jam_by_num.setdefault(num, jr)

    # Scope Mtrchain merge latch indexes to this machine's bosses + jam numbers
    # (shared Mtrchain.asc also contains other-controller merge latches).
    boss_nums_scoped: set[str] = set()
    for ent in _load_table(fortna, "MergeBoss", machine):
        brow = _row_dict(ent)
        bname = _active_name(brow, "Name")
        if not bname or not _is_valid_flag(brow.get("Valid")):
            continue
        owner = _clean(brow.get("Owner"))
        if owner and owner != machine:
            continue
        bn = _boss_number(bname)
        if bn:
            boss_nums_scoped.add(bn)
    boss_nums_scoped |= set(jam_by_num.keys())
    mtr_by_num = {k: v for k, v in mtr_by_num.items() if k in boss_nums_scoped}
    ssv_by_num = {k: v for k, v in ssv_by_num.items() if k in boss_nums_scoped}
    discharge_hint = {k: v for k, v in discharge_hint.items() if k in boss_nums_scoped}

    topology_edges, topo_edge_ev = _build_topology_edges(
        downstream_map=downstream_map,
        mtr_by_num=mtr_by_num,
        ssv_by_num=ssv_by_num,
        discharge_hint=discharge_hint,
        jam_by_num=jam_by_num,
    )
    indegree2 = {
        dst: sorted(srcs)
        for dst, srcs in sorted(topology_edges.items())
        if len(srcs) == 2
    }
    # Also keep >=2 as convergence candidates (true 2:1 focus on ==2)
    convergence_candidates = {
        dst: sorted(srcs)
        for dst, srcs in sorted(topology_edges.items())
        if len(srcs) >= 2
    }

    boss_entries = _load_table(fortna, "MergeBoss", machine)
    input_entries = _load_table(fortna, "MergeInputs", machine)
    route_entries = _load_table(fortna, "MergeRoute", machine)
    mtr_by_motor = _index_mtrchain_by_motor(fortna, machine)
    conveyor_types = _index_conveyor_types(fortna, machine)

    inputs_by_boss: dict[str, list[dict[str, str]]] = defaultdict(list)
    for ent in input_entries:
        row = _row_dict(ent)
        name = _active_name(row, "Name")
        boss = _clean(row.get("MergeBoss"))
        if not name or not boss:
            continue
        if not _is_valid_flag(row.get("Valid")):
            continue
        inputs_by_boss[boss].append(row)

    routes_by_name = {}
    for ent in route_entries:
        row = _row_dict(ent)
        name = _active_name(row, "Name")
        if name:
            routes_by_name[name] = row

    merges: list[dict[str, Any]] = []
    seen_bosses: set[str] = set()

    for ent in boss_entries:
        row = _row_dict(ent)
        boss_name = _active_name(row, "Name")
        if not boss_name:
            continue
        if not _is_valid_flag(row.get("Valid")):
            continue
        owner = _clean(row.get("Owner"))
        if owner and owner != machine:
            continue
        try:
            num_inputs = int(float(_clean(row.get("NumInputs") or "0") or "0"))
        except ValueError:
            num_inputs = 0
        source_class = classify_merge_source(boss_name)
        # Enumerate every Valid MergeBoss — do not drop 3-input bosses silently.
        if num_inputs < 2:
            continue

        seen_bosses.add(boss_name)
        boss_num = _boss_number(boss_name)
        lanes_raw = list(inputs_by_boss.get(boss_name) or [])
        # Stable main/induct: Index asc, then Name
        def _lane_key(r: dict[str, str]) -> tuple:
            idx = _clean(r.get("Index"))
            try:
                idx_n = int(float(idx)) if idx else 0
            except ValueError:
                idx_n = 0
            return (idx_n, _active_name(r, "Name"))

        lanes_raw.sort(key=_lane_key)

        evidence: list[dict[str, Any]] = [
            {
                "kind": "mergeboss",
                "table": "MergeBoss.asc",
                "name": boss_name,
                "num_inputs": num_inputs,
                "owner": owner or machine,
                "operable_input": _clean(row.get("OperableInput")),
                "valid": _clean(row.get("Valid")),
                "source_classification": source_class,
            }
        ]
        unresolved: list[str] = []

        if len(lanes_raw) < 2:
            unresolved.append(f"expected_ge2_mergeinputs_got_{len(lanes_raw)}")

        resolved_lanes: list[dict[str, Any]] = []
        for lane_row in lanes_raw:
            # Legacy vote still used as logical-lane corroboration for _P1/_P2 mains
            sec, lane_ev, lane_un = _resolve_lane_section(
                lane_row,
                known_sections=known_ids,
                mtr_ssv_by_merge=ssv_by_num,
                boss_name=boss_name,
            )
            evidence.extend(lane_ev)
            # Do not treat single-source as fatal when Mtrchain ReleaseIO resolves
            soft_un = [u for u in lane_un if "single_source_only" not in u]
            unresolved.extend(soft_un)
            idx = _clean(lane_row.get("Index"))
            try:
                idx_n = int(float(idx)) if idx else 0
            except ValueError:
                idx_n = 0
            route_name = _clean(lane_row.get("MergeRoute"))
            if route_name and route_name in routes_by_name:
                evidence.append(
                    {
                        "kind": "mergeroute",
                        "table": "MergeRoute.asc",
                        "name": route_name,
                        "merge_inputs": _clean(routes_by_name[route_name].get("MergeInputs")),
                    }
                )
            input_name = _active_name(lane_row, "Name")
            logical = (_p_token(input_name) or "").upper() or None
            presence = _clean(lane_row.get("Presense") or lane_row.get("Presence"))
            release_io = _clean(lane_row.get("ReleaseIO"))
            rel = _resolve_release_io_mtrchain(
                release_io,
                mtr_by_motor=mtr_by_motor,
                conveyor_types=conveyor_types,
            )
            evidence.extend(rel.get("evidence") or [])
            unresolved.extend(rel.get("unresolved") or [])

            # Three-level model: logical lane ≠ physical release ≠ next/curve
            # Prefer lane-name token as logical; keep vote section for main _P1/_P2.
            if sec and _SECTION_SUFFIX_RE.match(sec):
                logical_out = sec
            else:
                logical_out = logical or sec

            resolved_lanes.append(
                {
                    "input_name": input_name,
                    "index": idx_n,
                    "logical_lane": logical_out,
                    "section": logical_out,  # backward-compat alias = logical
                    "presense": presence,
                    "presence": presence,
                    "release_io": release_io or None,
                    "physical_release_conveyor": rel.get("physical_release_conveyor"),
                    "physical_release_type": rel.get("physical_release_type"),
                    "next_conveyor": rel.get("next_conveyor"),
                    "next_conveyor_type": rel.get("next_conveyor_type"),
                    "timer": rel.get("timer"),
                    "latch_aux": rel.get("latch_aux"),
                    "merge_route": route_name,
                }
            )

        main_lane = resolved_lanes[0]["logical_lane"] if resolved_lanes else None
        induct_lane = resolved_lanes[1]["logical_lane"] if len(resolved_lanes) > 1 else None
        # Role labels from Index / LANE naming (RUN-explicit)
        if len(resolved_lanes) >= 2:
            evidence.append(
                {
                    "kind": "lane_role_assignment",
                    "rule": "MergeInputs Index ascending: 0→mainLane(logical), 1→inductLane(logical)",
                    "main_input": resolved_lanes[0]["input_name"],
                    "induct_input": resolved_lanes[1]["input_name"],
                    "mainLane": main_lane,
                    "inductLane": induct_lane,
                    "main_physical_release": resolved_lanes[0].get("physical_release_conveyor"),
                    "induct_physical_release": resolved_lanes[1].get("physical_release_conveyor"),
                    "main_next": resolved_lanes[0].get("next_conveyor"),
                    "induct_next": resolved_lanes[1].get("next_conveyor"),
                    "note": (
                        "logical_lane / physical_release_conveyor / next_conveyor "
                        "are distinct — do not collapse"
                    ),
                }
            )

        jam_row = _match_jam_for_boss(jam_rows, boss_name, boss_num)
        jam_pe = _clean(jam_row.get("Sensor_Name")) if jam_row else ""
        jam_conv = _clean(jam_row.get("Conveyor_Name")).upper() if jam_row else ""
        jam_zone = _clean(jam_row.get("Zone")) if jam_row else ""
        # Named bosses (2-1 SERVO) inherit discharge number from matched Jamcheck
        # conveyor (P600) so Mtrchain discharge_hint / topology stay aligned.
        if jam_conv and not boss_num:
            m_jc = re.match(r"^P(\d{2,4})$", jam_conv, re.I)
            if m_jc:
                boss_num = m_jc.group(1)
                evidence.append(
                    {
                        "kind": "boss_number_from_jamcheck",
                        "boss": boss_name,
                        "boss_number": boss_num,
                        "conveyor": jam_conv,
                        "zone": jam_zone,
                    }
                )

        downstream, ds_ev, ds_un = _resolve_downstream(
            boss_name=boss_name,
            boss_num=boss_num,
            main_lane=main_lane,
            induct_lane=induct_lane,
            jam_row=jam_row,
            discharge_hint=discharge_hint,
            known_sections=known_sections,
            topology_edges=topology_edges,
        )
        evidence.extend(ds_ev)
        unresolved.extend(ds_un)

        # Topology candidate linkage
        topo_hit = None
        if downstream and downstream in convergence_candidates:
            topo_hit = {
                "downstream": downstream,
                "inbound": convergence_candidates[downstream],
                "indegree": len(convergence_candidates[downstream]),
            }
            evidence.append({"kind": "topology_candidate_match", **topo_hit})
        elif main_lane and induct_lane:
            for dst, srcs in indegree2.items():
                if main_lane in srcs or induct_lane in srcs:
                    evidence.append(
                        {
                            "kind": "topology_partial_match",
                            "downstream": dst,
                            "inbound": srcs,
                        }
                    )

        merge_section1 = main_lane
        merge_section2 = induct_lane
        merge_section3 = None
        # Spur/body curve: prefer induct lane's Mtrchain Next when it is a CURVE
        induct_next = (
            resolved_lanes[1].get("next_conveyor") if len(resolved_lanes) > 1 else None
        )
        induct_phys = (
            resolved_lanes[1].get("physical_release_conveyor")
            if len(resolved_lanes) > 1
            else None
        )
        main_phys = resolved_lanes[0].get("physical_release_conveyor") if resolved_lanes else None
        if induct_next and induct_next not in {main_lane, induct_lane, downstream}:
            merge_section3 = induct_next
            evidence.append(
                {
                    "kind": "merge_curve_from_induct_next",
                    "table": "Mtrchain.asc",
                    "induct_release_io": resolved_lanes[1].get("release_io") if len(resolved_lanes) > 1 else None,
                    "physical_release": induct_phys,
                    "next_curve": induct_next,
                    "next_type": resolved_lanes[1].get("next_conveyor_type") if len(resolved_lanes) > 1 else None,
                }
            )
        elif jam_conv and jam_conv not in {main_lane, induct_lane, downstream}:
            merge_section3 = jam_conv
        elif boss_num and f"P{boss_num}" in known_ids:
            body = f"P{boss_num}"
            if body not in {main_lane, induct_lane, downstream}:
                merge_section3 = body

        pes = {
            "main": resolved_lanes[0]["presense"] if resolved_lanes else "",
            "induct": resolved_lanes[1]["presense"] if len(resolved_lanes) > 1 else "",
            "jam": jam_pe,
        }

        # Area: jam zone text is descriptive only — not a plant Area id.
        area = None
        if jam_zone:
            evidence.append(
                {
                    "kind": "jam_zone_label",
                    "zone": jam_zone,
                    "note": "Zone label is not plant Area; Area remains engineer-configured",
                }
            )

        # Confidence / classification (PROVEN/CANDIDATE/UNRESOLVED)
        # Source type (SPUR/2-1/3-1) is separate — never collapse into Merge_2to1-only.
        lane_ok = bool(main_lane and induct_lane and main_lane != induct_lane)
        mtr_ok = any(
            (ln.get("physical_release_conveyor") or ln.get("mtrchain_row_found"))
            for ln in resolved_lanes
        ) or any(e.get("kind") == "release_io_mtrchain" for e in evidence)
        evidence_kinds = {e.get("kind") for e in evidence if e.get("kind")}
        cross_table = len(
            {
                k
                for k in evidence_kinds
                if k
                in {
                    "mergeboss",
                    "mergeinputs_presense",
                    "mergeinputs_releaseio",
                    "mergeinputs_timer",
                    "mtrchain_merge_ssv",
                    "mtrchain_latch_discharge",
                    "release_io_mtrchain",
                    "jamcheck_conveyor",
                    "topology_convergence",
                    "spur_downstream_p2",
                    "mergeroute",
                    "merge_curve_from_induct_next",
                }
            }
        )
        lane_sources_ok = not any("ambiguous_sections" in u for u in unresolved)
        critical_unresolved = [
            u
            for u in unresolved
            if u.startswith("expected_")
            or "ambiguous_sections" in u
            or (u.startswith("lane:") and "no_section" in u)
        ]

        if (
            lane_ok
            and lane_sources_ok
            and not critical_unresolved
            and cross_table >= 3
            and (downstream or (source_class == "SPUR" and merge_section3))
        ):
            classification = CLASS_PROVEN
            confidence = "HIGH"
            if not downstream and source_class == "SPUR" and merge_section3:
                # Spur proven on ReleaseIO→Next curve even when main _P2 discharge soft
                unresolved = [u for u in unresolved if not u.startswith("downstream:")]
        elif lane_ok and cross_table >= 2 and not critical_unresolved:
            classification = CLASS_CANDIDATE
            confidence = "MEDIUM"
            if not downstream:
                unresolved.append("downstream:missing_for_proven")
        elif num_inputs >= 2 and boss_name:
            classification = CLASS_CANDIDATE if lane_ok else CLASS_UNRESOLVED
            confidence = "LOW"
        else:
            classification = CLASS_UNRESOLVED
            confidence = "LOW"

        # Preserve section suffixes in all emitted lane fields
        for label, val in (
            ("mainLane", main_lane),
            ("inductLane", induct_lane),
            ("downstream", downstream),
            ("mergeSection1", merge_section1),
            ("mergeSection2", merge_section2),
            ("mergeSection3", merge_section3),
        ):
            if val and _SECTION_SUFFIX_RE.match(val):
                evidence.append(
                    {
                        "kind": "section_suffix_preserved",
                        "field": label,
                        "value": val,
                        "rule": "Never flatten P{n}_P1/_P2 to P{n}",
                    }
                )

        # AOI type hint — SPUR/3-1 are NOT blindly identical to Merge_2to1 behavior
        aoi_hint = "Merge_2to1"
        if source_class == "SPUR":
            aoi_hint = "Merge_2to1"  # structural AOI may still be 2:1; semantics differ
        elif source_class == "3-1":
            aoi_hint = "Merge_2to1"  # NumInputs may still be 2 in this RUN; keep explicit

        merges.append(
            {
                "type": aoi_hint,
                "name": boss_name,
                "bossNumber": boss_num,
                "sourceClassification": source_class,
                "mainLane": main_lane,
                "inductLane": induct_lane,
                "mainPhysicalRelease": main_phys,
                "inductPhysicalRelease": induct_phys,
                "inductNext": induct_next,
                "mergeSection1": merge_section1,
                "mergeSection2": merge_section2,
                "mergeSection3": merge_section3,
                "downstream": downstream,
                "PEs": pes,
                "area": area,
                "jamZone": jam_zone or None,
                "numInputs": num_inputs,
                "lanes": resolved_lanes,
                "topology": topo_hit,
                "evidence": evidence,
                "unresolved": sorted(set(unresolved)),
                "resolvedFields": [
                    k
                    for k, v in {
                        "mainLane": main_lane,
                        "inductLane": induct_lane,
                        "mainPhysicalRelease": main_phys,
                        "inductPhysicalRelease": induct_phys,
                        "inductNext": induct_next,
                        "mergeSection3": merge_section3,
                        "downstream": downstream,
                    }.items()
                    if v
                ],
                "confidence": confidence,
                "classification": classification,
            }
        )

    # Topology-only convergence nodes scoped to this machine's merge numbers /
    # jam conveyors — ignore other-controller latch rows in shared Mtrchain.
    machine_merge_nums = {m.get("bossNumber") for m in merges if m.get("bossNumber")}
    machine_merge_nums |= set(jam_by_num.keys())
    covered_ds = {m.get("downstream") for m in merges if m.get("downstream")}
    covered_lanes = set()
    for m in merges:
        if m.get("mainLane"):
            covered_lanes.add(m["mainLane"])
        if m.get("inductLane"):
            covered_lanes.add(m["inductLane"])

    for dst, srcs in indegree2.items():
        if dst in covered_ds:
            continue
        if set(srcs) <= covered_lanes:
            continue
        dst_num = None
        m_dst = re.match(r"^P(\d{2,4})$", dst or "", re.I)
        if m_dst:
            dst_num = m_dst.group(1)
        # Only emit topology-only candidates tied to this controller's merges/jams
        if dst_num and dst_num not in machine_merge_nums:
            continue
        if not dst_num:
            continue
        merges.append(
            {
                "type": "Merge_2to1",
                "name": f"TOPOLOGY_{dst}",
                "bossNumber": dst_num,
                "mainLane": srcs[0] if srcs else None,
                "inductLane": srcs[1] if len(srcs) > 1 else None,
                "mergeSection1": srcs[0] if srcs else None,
                "mergeSection2": srcs[1] if len(srcs) > 1 else None,
                "mergeSection3": None,
                "downstream": dst,
                "PEs": {"main": "", "induct": "", "jam": ""},
                "area": None,
                "jamZone": None,
                "numInputs": 2,
                "lanes": [],
                "topology": {"downstream": dst, "inbound": srcs, "indegree": 2},
                "evidence": [
                    {
                        "kind": "topology_indegree_eq_2",
                        "downstream": dst,
                        "inbound": srcs,
                        "note": "Topology convergence without MergeBoss row",
                    }
                ],
                "unresolved": ["no_mergeboss_row"],
                "confidence": "LOW",
                "classification": CLASS_CANDIDATE,
            }
        )

    # Counts
    n_cand = sum(1 for m in merges if m["classification"] == CLASS_CANDIDATE)
    n_proven = sum(1 for m in merges if m["classification"] == CLASS_PROVEN)
    n_unres = sum(1 for m in merges if m["classification"] == CLASS_UNRESOLVED)

    # Section preservation audit
    section_fields = []
    for m in merges:
        for fld in ("mainLane", "inductLane", "downstream", "mergeSection1", "mergeSection2", "mergeSection3"):
            val = m.get(fld)
            if val and _SECTION_SUFFIX_RE.match(str(val)):
                section_fields.append({"merge": m.get("name"), "field": fld, "value": val})

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": (
            "RUN tables only — MergeBoss/MergeInputs/MergeRoute/Mtrchain/"
            "Jamcheck/Fulljam/Fullline/Conveyor; finished PLC L5X not read"
        ),
        "firewall": {
            "finished_l5x_read": False,
            "hardcoded_merge_names": False,
            "forbidden_path_needles": list(FORBIDDEN_PATH_NEEDLES),
            "tables_read": tables_read,
        },
        "counts": {
            "candidate": n_cand,
            "proven": n_proven,
            "unresolved": n_unres,
            "total": len(merges),
            "topology_indegree_eq_2": len(indegree2),
            "mergeboss_2to1": len(seen_bosses),
        },
        "topology_indegree_2": indegree2,
        "section_suffix_preserved": section_fields,
        "merges": merges,
        "section_model_summary": {
            "section_count": len(known_sections),
            "preferred_induct": prefer,
            "suffix_sections": sorted(
                s for s in known_sections if _SECTION_SUFFIX_RE.match(s)
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    c = report.get("counts") or {}
    lines.append("# PLC2 Blind 2:1 Merge Discovery")
    lines.append("")
    lines.append(f"- Generated: `{report.get('generated_at')}`")
    lines.append(f"- Machine: `{report.get('machine')}`")
    lines.append(f"- RUN: `{report.get('run_dir')}`")
    lines.append(f"- Source: {report.get('source_of_truth')}")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"| Class | Count |")
    lines.append(f"|-------|------:|")
    lines.append(f"| PROVEN | {c.get('proven', 0)} |")
    lines.append(f"| CANDIDATE | {c.get('candidate', 0)} |")
    lines.append(f"| UNRESOLVED | {c.get('unresolved', 0)} |")
    lines.append(f"| Total | {c.get('total', 0)} |")
    lines.append(f"| Topology indegree==2 | {c.get('topology_indegree_eq_2', 0)} |")
    lines.append("")
    lines.append("## Merges")
    lines.append("")
    for m in report.get("merges") or []:
        lines.append(f"### `{m.get('name')}` — **{m.get('classification')}** ({m.get('confidence')})")
        lines.append("")
        lines.append(f"- type: `{m.get('type')}`")
        lines.append(f"- sourceClassification: `{m.get('sourceClassification')}`")
        lines.append(f"- mainLane (logical): `{m.get('mainLane')}`")
        lines.append(f"- inductLane (logical): `{m.get('inductLane')}`")
        lines.append(f"- mainPhysicalRelease: `{m.get('mainPhysicalRelease')}`")
        lines.append(f"- inductPhysicalRelease: `{m.get('inductPhysicalRelease')}`")
        lines.append(f"- inductNext: `{m.get('inductNext')}`")
        lines.append(f"- mergeSection1/2/3: `{m.get('mergeSection1')}` / `{m.get('mergeSection2')}` / `{m.get('mergeSection3')}`")
        lines.append(f"- downstream: `{m.get('downstream')}`")
        pes = m.get("PEs") or {}
        lines.append(
            f"- PEs: main=`{pes.get('main')}` induct=`{pes.get('induct')}` jam=`{pes.get('jam')}`"
        )
        lines.append(f"- area: `{m.get('area')}` zone=`{m.get('jamZone')}`")
        for ln in m.get("lanes") or []:
            lines.append(
                f"- lane[{ln.get('index')}] `{ln.get('input_name')}`: "
                f"logical=`{ln.get('logical_lane')}` presence=`{ln.get('presence') or ln.get('presense')}` "
                f"ReleaseIO=`{ln.get('release_io')}` phys=`{ln.get('physical_release_conveyor')}` "
                f"Next=`{ln.get('next_conveyor')}` ({ln.get('next_conveyor_type') or '—'}) "
                f"timer=`{ln.get('timer')}` latch=`{ln.get('latch_aux')}`"
            )
        un = m.get("unresolved") or []
        if un:
            lines.append(f"- unresolved: {', '.join(un)}")
        lines.append(f"- evidence chain ({len(m.get('evidence') or [])} facts):")
        for ev in (m.get("evidence") or [])[:12]:
            kind = ev.get("kind")
            lines.append(f"  - `{kind}`: {json.dumps({k: v for k, v in ev.items() if k != 'kind'}, sort_keys=True)}")
        lines.append("")
    lines.append("## Firewall")
    lines.append("")
    fw = report.get("firewall") or {}
    lines.append(f"- finished_l5x_read: `{fw.get('finished_l5x_read')}`")
    lines.append(f"- hardcoded_merge_names: `{fw.get('hardcoded_merge_names')}`")
    lines.append(f"- tables_read: {', '.join(fw.get('tables_read') or [])}")
    lines.append("")
    lines.append("STOP — discovery artifact only; no AOI/L5X generation.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "blind_report.json"
    md_path = out_dir / "blind_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def discovery_to_autogen_merges_2to1(
    report: dict[str, Any],
    *,
    tag_area: dict[str, str] | None = None,
    proven_only: bool = True,
) -> list[dict[str, Any]]:
    """Map native MergeBoss discovery → fortna_autogen merges_2to1 rows.

    Does not invent lanes from geometry/name similarity — only RUN-proven
    (or CANDIDATE when proven_only=False) MergeBoss relationships.
    """
    tag_area = tag_area or {}
    rows: list[dict[str, Any]] = []
    for m in report.get("merges") or []:
        cls = str(m.get("classification") or "").upper()
        if proven_only and cls != CLASS_PROVEN:
            continue
        if not proven_only and cls not in {CLASS_PROVEN, CLASS_CANDIDATE}:
            continue
        discharge = str(m.get("downstream") or m.get("discharge") or "").strip()
        main = str(m.get("mainLane") or "").strip()
        induct = str(m.get("inductLane") or "").strip()
        # SPUR may prove on mergeSection3 without downstream — use body as name key
        if not discharge and str(m.get("sourceClassification") or "").upper() == "SPUR":
            discharge = str(m.get("mergeSection3") or "").strip()
        if not discharge or not main or not induct:
            continue
        area = (
            tag_area.get(discharge.upper())
            or tag_area.get(main.upper())
            or str(m.get("area") or "").strip()
            or ""
        )
        pes = m.get("PEs") or {}
        rows.append(
            {
                "name": discharge,
                "area": area,
                "lanes": int(m.get("numInputs") or 2),
                "lane_a": main,
                "lane_b": induct,
                "lane_c": str(m.get("mergeSection3") or "").strip(),
                "discharge": discharge,
                "pe_a": str(pes.get("main") or "").strip(),
                "pe_b": str(pes.get("induct") or "").strip(),
                "pe_c": "",
                "jam_pe": str(pes.get("jam") or "").strip(),
                "allow_undefined_pe": False,
                "hold_mode": "runhold",
                "source": "native_merge_discovery",
                "discovery_name": str(m.get("name") or ""),
                "discovery_machine": str(report.get("machine") or ""),
                "suggested_aoi": "Merge_2to1",
                "mergeSection1": str(m.get("mergeSection1") or main),
                "mergeSection2": str(m.get("mergeSection2") or induct),
                "mergeSection3": str(m.get("mergeSection3") or "") or None,
                "sourceClassification": m.get("sourceClassification"),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BLIND PLC2 2:1 merge discovery (RUN only)")
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "workspace" / "_plc2_run_peek" / "RUN",
        help="PLC2 RUN directory (not workspace/active)",
    )
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "exports" / "plc2-merge-discovery",
    )
    args = ap.parse_args(argv)

    report = discover_plc2_merges(args.run_dir, args.machine)
    json_path, md_path = write_report(report, Path(args.out))
    c = report["counts"]
    print(
        f"PLC2 merge discovery: proven={c['proven']} candidate={c['candidate']} "
        f"unresolved={c['unresolved']} total={c['total']}"
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    for m in report.get("merges") or []:
        print(
            f"  [{m['classification']}] {m.get('name')}: "
            f"main={m.get('mainLane')} induct={m.get('inductLane')} "
            f"down={m.get('downstream')} secs={m.get('mergeSection1')}/"
            f"{m.get('mergeSection2')}/{m.get('mergeSection3')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
