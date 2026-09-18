#!/usr/bin/env python3
"""Compare virgin-RUN HardwareIOModel channels vs finished-PLC IO_MAP (validation only).

Finished L5X is an oracle for classification — never a generation input.
Does not invent RUN relationships from finished PLC. No machine/site branches.

Outputs:
  exports/stabilization/orindyac6_io_oracle_diff.json
  exports/stabilization/orindyac6_io_oracle_diff.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_family import data_index_for_module  # noqa: E402
from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    build_hardware_io_model,
)
from fortna_io_regression_baselines import _parse_l5x_modules  # noqa: E402
from fortna_plc2_io_truth import (  # noqa: E402
    CHANNEL_RE,
    _guess_run_names_for_finished_tag,
)

DEFAULT_RUN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
DEFAULT_ORACLE = Path(
    r"C:\Users\curtiskricke\Desktop\ORiellys Browns\PLC Progrms\ORLY_Brownsburg_IN_PLC6_TEST2.L5X"
)
DEFAULT_SITEFORGE_L5X = ROOT / "exports" / "current" / "ORINDYAC6_2026_09_18_1448.L5X"
DEFAULT_OUT_JSON = ROOT / "exports" / "stabilization" / "orindyac6_io_oracle_diff.json"
DEFAULT_OUT_MD = ROOT / "exports" / "stabilization" / "orindyac6_io_oracle_diff.md"

CLASSIFICATIONS = (
    "EXACT_MATCH",
    "OWNER_MATCH_ENDPOINT_MISMATCH",
    "ENDPOINT_MATCH_OWNER_MISMATCH",
    "MISSING_SITEFORGE_OWNER",
    "EXTRA_SITEFORGE_OWNER",
    "FINISHED_PLACEHOLDER",
    "ENGINEER_MODIFIED",
    "AMBIGUOUS",
    "NOT_COMPARABLE",
)

CHANNEL_IN_RE = re.compile(
    r"(?P<adapter>[A-Za-z0-9_]+):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\]\.(?P<bit>\d+)"
)
OTE_RE = re.compile(r"OTE\(([^)]+)\)")
EMU_RE = re.compile(r"_EMU_[A-Za-z0-9_]+")
PLACEHOLDER_RE = re.compile(r"NO_PointPlaceholder", re.I)
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Virgin RUN fingerprint inputs (machine overlays + shared tables).
FINGERPRINT_RELS = (
    "project.cfg",
    "info.cfg",
    "identity.cfg",
    "FORTNA/Configio.asc.ORINDYAC6",
    "FORTNA/Conveyor.asc",
    "PROJECT/EIPModules.asc.ORINDYAC6",
    "PROJECT/EIPAdapters.asc.ORINDYAC6",
    "PROJECT/EIPCSV.asc.ORINDYAC6",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return ""


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _norm_token(s: str) -> str:
    t = _clean(s).upper()
    t = re.sub(r"^T_", "", t)
    t = re.sub(r"[^A-Z0-9]+", "", t)
    return t


def virgin_run_fingerprint(run_dir: Path) -> dict[str, Any]:
    """Content fingerprint of virgin RUN authority tables (not whole tree)."""
    files: list[dict[str, Any]] = []
    h = hashlib.sha256()
    for rel in FINGERPRINT_RELS:
        p = run_dir / rel
        if not p.is_file():
            files.append({"path": rel, "missing": True})
            continue
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(raw)
        h.update(b"\0")
        files.append({"path": rel, "size": len(raw), "sha256": digest})
    return {
        "run_dir": str(run_dir),
        "combined_sha256": h.hexdigest(),
        "files": files,
    }


def parse_finished_iomap(text: str) -> list[dict[str, Any]]:
    """Parse finished IO_MAP rungs including [XIC(ch),XIC(_EMU_…)]OTE(tag) form.

    Input style:  XIC(RIO:I.Data[s].b)OTE(LOGICAL);
                  [XIC(RIO:I.Data[s].b) ,XIC(_EMU_…)]OTE(LOGICAL);
    Output style: XIC(LOGICAL)OTE(RIO:O.Data[s].b);
                  [XIC(LOGICAL) ,XIC(_EMU_…)]OTE(RIO:O.Data[s].b);
    """
    m = re.search(r'<Program[^>]*Name="IO_MAP"[^>]*>(.*?)</Program>', text, re.I | re.S)
    if not m:
        return []
    section = m.group(1)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for rung in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", section, re.S):
        logic = rung.group(1).strip()
        if not logic or logic.startswith("$") or ("NOP()" in logic and "XIC(" not in logic):
            continue
        channels = list(CHANNEL_IN_RE.finditer(logic))
        if not channels:
            continue
        ote_m = OTE_RE.search(logic)
        ote_raw = _clean(ote_m.group(1) if ote_m else "")
        emu_tags = sorted(set(EMU_RE.findall(logic)))

        # Prefer the physical RIO channel (skip pure _EMU_ operands).
        phys = None
        for cm in channels:
            adapter = cm.group("adapter")
            if adapter.startswith("_EMU_"):
                continue
            phys = cm
            break
        if phys is None:
            continue
        adapter = phys.group("adapter")
        direction = phys.group("dir").upper()
        data_index = int(phys.group("slot"))
        bit = int(phys.group("bit"))
        channel = f"{adapter}:{direction}.Data[{data_index}].{bit}"

        # Logical tag: OTE for inputs; XIC operand for outputs when OTE is the channel.
        tag = ote_raw
        if direction == "O" and ote_raw == channel:
            xics = re.findall(r"XIC\(([^)]+)\)", logic)
            logical = None
            for x in xics:
                xu = x.strip()
                if xu.startswith("_EMU_"):
                    continue
                if CHANNEL_IN_RE.fullmatch(xu):
                    continue
                logical = xu
                break
            tag = _clean(logical or "")
        elif direction == "I" and ote_raw == channel:
            # Degenerate / comment-only — skip
            tag = ""

        is_ph = bool(PLACEHOLDER_RE.search(tag)) or tag.upper() in {
            "SPARE",
            "INVALID",
            "N/A",
            "NONE",
        }
        key = (adapter, direction, data_index, bit)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "adapter": adapter,
                "direction": direction,
                "data_index": data_index,
                "bit": bit,
                "channel": channel,
                "tag": tag,
                "placeholder": is_ph,
                "emu_tags": emu_tags,
                "engineer_modified": bool(emu_tags),
                "rung": logic,
            }
        )
    return rows


def finished_adapter_ips(text: str) -> dict[str, str]:
    """Map finished adapter module name → IPv4 from Port Address."""
    out: dict[str, str] = {}
    for mod in _parse_l5x_modules(text):
        name = _clean(mod.get("name"))
        addr = _clean(mod.get("address"))
        cat = _clean(mod.get("catalog")).upper()
        if not name or not IPV4_RE.match(addr):
            continue
        if "AENT" in cat or re.search(r"RIO\d+$", name, re.I):
            out[name] = addr
    return out


def _aent_index(name: str) -> int | None:
    m = re.search(r"(?:AENT_|RIO)(\d+)$", _clean(name), re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def map_adapters_by_ip_or_order(
    sf_adapters: list[dict[str, Any]],
    finished_ips: dict[str, str],
) -> dict[str, Any]:
    """Generic T_1794_AENT_N ↔ finished CPxRIO{N-1} via IP, else ordered index.

    No machine/site hardcoding. IP wins; fallback pairs by sorted IP then by
    ascending adapter index (Site Forge 1-based AENT_N ↔ finished RIO N-1).
    """
    sf_flex = []
    for ad in sf_adapters:
        rio = _clean(ad.get("rio_name") or ad.get("name"))
        ip = _clean(ad.get("targetip"))
        fam = _clean(ad.get("family"))
        cat_hint = " ".join(
            _clean(m.get("type") or m.get("catalog")) for m in (ad.get("modules") or [])[:1]
        )
        if fam and fam not in ("1794", "1734", ""):
            # Skip drives / non-discrete adapters for IO_MAP compare.
            if fam == "ETHERNET_DRIVE" or "POWERFLEX" in rio.upper():
                continue
        if "POWERFLEX" in rio.upper():
            continue
        if not rio:
            continue
        sf_flex.append({"rio_name": rio, "ip": ip, "family": fam or "1794", "catalog_hint": cat_hint})

    fin_items = [{"name": n, "ip": ip} for n, ip in finished_ips.items()]
    mapping: dict[str, str] = {}  # sf_rio -> finished adapter
    reverse: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []

    # Pass 1: exact IP
    fin_by_ip = {item["ip"]: item["name"] for item in fin_items if item["ip"]}
    used_fin: set[str] = set()
    used_sf: set[str] = set()
    for ad in sf_flex:
        ip = ad["ip"]
        if ip and ip in fin_by_ip:
            fin = fin_by_ip[ip]
            mapping[ad["rio_name"]] = fin
            reverse[fin] = ad["rio_name"]
            used_fin.add(fin)
            used_sf.add(ad["rio_name"])
            evidence.append(
                {
                    "siteforge": ad["rio_name"],
                    "finished": fin,
                    "how": "ip",
                    "ip": ip,
                }
            )

    # Pass 2: adapter index — SF AENT_N ↔ finished RIO (N-1) when both present
    fin_by_idx: dict[int, str] = {}
    for item in fin_items:
        if item["name"] in used_fin:
            continue
        idx = _aent_index(item["name"])
        if idx is not None:
            fin_by_idx[idx] = item["name"]
    for ad in sf_flex:
        if ad["rio_name"] in used_sf:
            continue
        idx = _aent_index(ad["rio_name"])
        if idx is None:
            continue
        # Site Forge T_1794_AENT_1 ↔ finished …RIO0
        cand = fin_by_idx.get(idx - 1) if idx >= 1 else None
        if cand and cand not in used_fin:
            mapping[ad["rio_name"]] = cand
            reverse[cand] = ad["rio_name"]
            used_fin.add(cand)
            used_sf.add(ad["rio_name"])
            evidence.append(
                {
                    "siteforge": ad["rio_name"],
                    "finished": cand,
                    "how": "adapter_index",
                    "sf_index": idx,
                    "finished_index": idx - 1,
                }
            )

    # Pass 3: stable order by IP then name
    rem_sf = sorted(
        [a for a in sf_flex if a["rio_name"] not in used_sf],
        key=lambda a: (a["ip"] or "999", a["rio_name"]),
    )
    rem_fin = sorted(
        [i for i in fin_items if i["name"] not in used_fin],
        key=lambda i: (i["ip"] or "999", i["name"]),
    )
    for ad, fin in zip(rem_sf, rem_fin):
        mapping[ad["rio_name"]] = fin["name"]
        reverse[fin["name"]] = ad["rio_name"]
        evidence.append(
            {
                "siteforge": ad["rio_name"],
                "finished": fin["name"],
                "how": "order",
                "ip_sf": ad["ip"],
                "ip_fin": fin["ip"],
            }
        )

    return {
        "sf_to_finished": mapping,
        "finished_to_sf": reverse,
        "evidence": evidence,
        "unmapped_siteforge": [a["rio_name"] for a in sf_flex if a["rio_name"] not in mapping],
        "unmapped_finished": [i["name"] for i in fin_items if i["name"] not in reverse],
    }


def siteforge_autogen_owner_candidates(run_owner: str) -> list[str]:
    """Logical tags Site Forge autogen emits for a RUN Conveyor IO_Name.

    Mirrors fortna_autogen._device_member cookie-cutter patterns only.
    """
    raw = _clean(run_owner)
    core = re.sub(r"^T_", "", raw)
    out: list[str] = []

    m = re.match(r"^(\d+)PBSTART(_PLT)?$", core, re.I)
    if m:
        n, lt = m.group(1), m.group(2)
        if lt:
            out.append(f"CP{n}_CS.O.Start_PB_LT")
        else:
            out.append(f"CP{n}_CS.I.Start_PB")
            out.append("*.Start_PB")  # finished may rename CS AOI instance
    m = re.match(r"^(\d+)PBSTOP(_PLT)?$", core, re.I)
    if m:
        n, lt = m.group(1), m.group(2)
        if lt:
            out.append(f"CP{n}_CS.O.Stop_PB_LT")
        else:
            out.append(f"CP{n}_CS.I.Stop_PB")
            out.append("*.Stop_PB")
    m = re.match(r"^(\d+)(MCR|ESR)(\d*)_?AUX$", core, re.I)
    if m:
        out.append(f"CP{m.group(1)}_{m.group(2).upper()}{m.group(3) or '1'}.I.ES_OK")
    m = re.match(r"^(\d+)ES$", core, re.I)
    if m:
        out.append(f"CP{m.group(1)}_ES.I.ES_OK")
    if re.match(r"^(?:EZ)?PE\d", core, re.I):
        out.append(f"{core}.I.PE_Clear")
        out.append(f"{raw}.I.PE_Clear")
    m = re.match(r"^M(\d{2,4}[A-Z]?)_AUX$", core, re.I)
    if m:
        out.append(f"P{m.group(1)}_MS.I.Auxiliary_Forward")
    m = re.match(r"^ES\d", core, re.I)
    if m:
        out.append(f"{core}.I.ES_OK")
        out.append(f"{raw}.I.ES_OK")
    # Always include bare / member-stripped forms for exact compare
    out.append(core)
    out.append(raw)
    # dedupe
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        cu = c.upper()
        if cu not in seen:
            seen.add(cu)
            uniq.append(c)
    return uniq


def owners_equivalent(run_owner: str | None, finished_tag: str | None) -> tuple[str, str]:
    """Return (status, reason) where status is match|mismatch|ambiguous|empty.

    Proven cookie-cutter renames from Site Forge autogen only. Unsure → ambiguous.
    """
    ro = _clean(run_owner)
    ft = _clean(finished_tag)
    if not ro and not ft:
        return "empty", "both_empty"
    if not ro or not ft:
        return "empty", "one_empty"
    if PLACEHOLDER_RE.search(ft):
        return "empty", "finished_placeholder"

    # Exact / normalized equality (strip T_ and non-alnum)
    if _norm_token(ro) == _norm_token(ft):
        return "match", "normalized_equal"
    # Root before first dot
    ft_root = ft.split(".", 1)[0]
    if _norm_token(ro) == _norm_token(ft_root):
        return "match", "root_equal"

    cands = siteforge_autogen_owner_candidates(ro)
    ft_u = ft.upper()
    for c in cands:
        if c.startswith("*."):
            # Member-only wildcard allowed for PBSTART/PBSTOP per task
            member = c[1:].upper()  # .START_PB
            if ft_u.endswith(member):
                return "match", f"autogen_member_wildcard:{c}"
            continue
        if ft_u == c.upper():
            return "match", f"autogen_exact:{c}"
        # Allow finished CS AOI rename: CP6_*_CS.I.Start_PB vs CP6_CS.I.Start_PB
        if c.upper().endswith(".I.START_PB") and ft_u.endswith(".I.START_PB"):
            m_c = re.match(r"^CP(\d+)_", c, re.I)
            m_f = re.match(r"^CP(\d+)_", ft, re.I)
            if m_c and m_f and m_c.group(1) == m_f.group(1) and "_CS." in ft_u:
                return "match", "autogen_cs_panel_member"
        if c.upper().endswith(".I.STOP_PB") and ft_u.endswith(".I.STOP_PB"):
            m_c = re.match(r"^CP(\d+)_", c, re.I)
            m_f = re.match(r"^CP(\d+)_", ft, re.I)
            if m_c and m_f and m_c.group(1) == m_f.group(1) and "_CS." in ft_u:
                return "match", "autogen_cs_panel_member"

    # Reverse: finished tag → candidate RUN names (proven patterns only)
    guessed = _guess_run_names_for_finished_tag(ft)
    ro_u = ro.upper()
    for g in guessed:
        if g.upper() == ro_u or _norm_token(g) == _norm_token(ro):
            return "match", f"reverse_guess:{g}"

    # Sure mismatch only when both look like structured device tags with different roots
    if "." in ft and _norm_token(ro) and _norm_token(ft_root):
        # e.g. PE600 vs ES600 — different
        if any(ch.isdigit() for ch in ro) and any(ch.isdigit() for ch in ft_root):
            # Still ambiguous if no shared stem — do not invent synonymy
            return "ambiguous", "unproven_rename"
    return "ambiguous", "unproven_rename"


def iter_siteforge_channels(model: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ad in model.get("adapters") or []:
        rio = _clean(ad.get("rio_name") or ad.get("name"))
        ip = _clean(ad.get("targetip"))
        fam = _clean(ad.get("family"))
        if "POWERFLEX" in rio.upper() or fam == "ETHERNET_DRIVE":
            continue
        for mod in ad.get("modules") or []:
            if mod.get("is_adapter_card"):
                continue
            slot = mod.get("slot")
            data_index = mod.get("data_index")
            if data_index is None and slot is not None:
                data_index = data_index_for_module(int(slot), fam or "1794")
            for ch in mod.get("channels") or []:
                ep = ch.get("physical_endpoint") if isinstance(ch.get("physical_endpoint"), dict) else {}
                direction = _clean(ch.get("direction") or ep.get("direction")).upper()
                if direction in ("IN", "INPUT"):
                    direction = "I"
                elif direction in ("OUT", "OUTPUT"):
                    direction = "O"
                bit = ch.get("bit")
                if bit is None:
                    bit = ch.get("fortna_bit")
                if bit is None:
                    bit = ep.get("bit")
                di = ch.get("data_index")
                if di is None:
                    di = ep.get("data_index", data_index)
                addr = _clean(ch.get("physical_address") or ep.get("channel"))
                if not direction or di is None or bit is None:
                    continue
                prov = ch.get("provenance") if isinstance(ch.get("provenance"), dict) else {}
                rows.append(
                    {
                        "rio_name": rio,
                        "ip": ip,
                        "family": fam,
                        "module_slot": mod.get("slot") or ep.get("module_slot"),
                        "module_type": mod.get("type") or mod.get("catalog"),
                        "direction": direction,
                        "data_index": int(di),
                        "bit": int(bit),
                        "channel": addr or f"{rio}:{direction}.Data[{int(di)}].{int(bit)}",
                        "engineering_owner": _clean(ch.get("engineering_owner")) or None,
                        "owner_state": _clean(ch.get("owner_state")) or None,
                        "fortna_word": ch.get("fortna_word")
                        if ch.get("fortna_word") is not None
                        else ep.get("bank_word"),
                        "assign_how": ch.get("assign_how") or prov.get("assign_how"),
                    }
                )
    return rows


def _endpoint_key(adapter: str, direction: str, data_index: int, bit: int) -> str:
    return f"{adapter}|{direction}|Data[{data_index}]|{bit}"


def classify_channel(
    *,
    sf: dict[str, Any] | None,
    fin: dict[str, Any] | None,
    endpoint_aligned: bool,
) -> dict[str, Any]:
    """Classify one SF↔finished channel pair."""
    sf_owner = _clean((sf or {}).get("engineering_owner"))
    sf_state = _clean((sf or {}).get("owner_state"))
    fin_tag = _clean((fin or {}).get("tag"))
    fin_ph = bool((fin or {}).get("placeholder"))
    fin_emu = bool((fin or {}).get("engineer_modified"))
    emu_tags = list((fin or {}).get("emu_tags") or [])

    owner_status, owner_reason = owners_equivalent(sf_owner, fin_tag if not fin_ph else "")
    owner_match = owner_status == "match"
    notes: list[str] = []

    if sf is None and fin is None:
        cls = "NOT_COMPARABLE"
    elif sf is None:
        if fin_ph:
            cls = "FINISHED_PLACEHOLDER"
        elif fin_emu:
            cls = "ENGINEER_MODIFIED"
        else:
            cls = "MISSING_SITEFORGE_OWNER"
            notes.append("finished channel has no Site Forge HardwareIOModel counterpart")
    elif fin is None:
        if sf_owner and sf_state == OWNER_ASSIGNED:
            cls = "EXTRA_SITEFORGE_OWNER"
        else:
            cls = "NOT_COMPARABLE"
            notes.append("no finished IO_MAP rung for this endpoint")
    elif fin_emu:
        cls = "ENGINEER_MODIFIED"
        if endpoint_aligned and owner_match:
            notes.append("underlying cookie-cutter map aligns; _EMU_ parallel is engineer overlay")
        elif endpoint_aligned and owner_status == "ambiguous":
            notes.append("endpoint aligns; owner equivalence unproven under _EMU_ overlay")
    elif fin_ph:
        if sf_owner and sf_state == OWNER_ASSIGNED:
            cls = "EXTRA_SITEFORGE_OWNER"
            notes.append("Site Forge has RUN owner; finished uses NO_PointPlaceholder")
        else:
            cls = "FINISHED_PLACEHOLDER"
    elif (not sf_owner or sf_state != OWNER_ASSIGNED) and fin_tag and not fin_ph:
        cls = "MISSING_SITEFORGE_OWNER"
    elif owner_status == "ambiguous":
        cls = "AMBIGUOUS"
        notes.append(f"owner_reason={owner_reason}")
    elif endpoint_aligned and owner_match:
        cls = "EXACT_MATCH"
    elif endpoint_aligned and not owner_match:
        cls = "ENDPOINT_MATCH_OWNER_MISMATCH"
    elif (not endpoint_aligned) and owner_match:
        cls = "OWNER_MATCH_ENDPOINT_MISMATCH"
    else:
        cls = "AMBIGUOUS"
        notes.append("endpoint and owner both disagree or incomplete")

    return {
        "classification": cls,
        "endpoint_aligned": endpoint_aligned,
        "owner_status": owner_status,
        "owner_reason": owner_reason,
        "owner_match": owner_match,
        "siteforge_owner": sf_owner or None,
        "siteforge_owner_state": sf_state or None,
        "finished_tag": fin_tag or None,
        "finished_placeholder": fin_ph,
        "engineer_modified": fin_emu,
        "emu_tags": emu_tags,
        "notes": notes,
    }


def build_diff(
    *,
    run_dir: Path,
    machine: str,
    oracle_path: Path,
    siteforge_l5x: Path | None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    git_sha = _git_head(ROOT)
    fp = virgin_run_fingerprint(run_dir)
    oracle_sha = _sha256_file(oracle_path) if oracle_path.is_file() else ""
    oracle_size = oracle_path.stat().st_size if oracle_path.is_file() else 0

    model = build_hardware_io_model(run_dir, machine)
    sf_channels = iter_siteforge_channels(model)

    oracle_text = oracle_path.read_text(encoding="utf-8", errors="replace")
    fin_maps = parse_finished_iomap(oracle_text)
    fin_ips = finished_adapter_ips(oracle_text)
    adapter_map = map_adapters_by_ip_or_order(model.get("adapters") or [], fin_ips)

    sf_by_key: dict[str, dict[str, Any]] = {}
    for ch in sf_channels:
        k = _endpoint_key(ch["rio_name"], ch["direction"], ch["data_index"], ch["bit"])
        sf_by_key[k] = ch

    fin_by_sf_key: dict[str, dict[str, Any]] = {}
    fin_unmapped: list[dict[str, Any]] = []
    for row in fin_maps:
        sf_rio = adapter_map["finished_to_sf"].get(row["adapter"])
        if not sf_rio:
            fin_unmapped.append(row)
            continue
        k = _endpoint_key(sf_rio, row["direction"], row["data_index"], row["bit"])
        fin_by_sf_key[k] = {**row, "siteforge_rio": sf_rio}

    all_keys = sorted(set(sf_by_key) | set(fin_by_sf_key))
    comparisons: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    for key in all_keys:
        sf = sf_by_key.get(key)
        fin = fin_by_sf_key.get(key)
        # Endpoint alignment: same mapped adapter + direction + data_index + bit
        endpoint_aligned = sf is not None and fin is not None
        result = classify_channel(sf=sf, fin=fin, endpoint_aligned=endpoint_aligned)
        totals[result["classification"]] += 1
        comparisons.append(
            {
                "key": key,
                "siteforge": {
                    "channel": (sf or {}).get("channel"),
                    "rio_name": (sf or {}).get("rio_name"),
                    "direction": (sf or {}).get("direction"),
                    "data_index": (sf or {}).get("data_index"),
                    "bit": (sf or {}).get("bit"),
                    "fortna_word": (sf or {}).get("fortna_word"),
                    "assign_how": (sf or {}).get("assign_how"),
                    "module_slot": (sf or {}).get("module_slot"),
                    "module_type": (sf or {}).get("module_type"),
                }
                if sf
                else None,
                "finished": {
                    "channel": (fin or {}).get("channel"),
                    "adapter": (fin or {}).get("adapter"),
                    "direction": (fin or {}).get("direction"),
                    "data_index": (fin or {}).get("data_index"),
                    "bit": (fin or {}).get("bit"),
                    "tag": (fin or {}).get("tag"),
                    "emu_tags": (fin or {}).get("emu_tags"),
                    "rung": (fin or {}).get("rung"),
                }
                if fin
                else None,
                **result,
            }
        )

    for row in fin_unmapped:
        totals["NOT_COMPARABLE"] += 1
        comparisons.append(
            {
                "key": f"UNMAPPED|{row['channel']}",
                "siteforge": None,
                "finished": row,
                "classification": "NOT_COMPARABLE",
                "endpoint_aligned": False,
                "owner_status": "empty",
                "owner_reason": "finished_adapter_unmapped",
                "owner_match": False,
                "siteforge_owner": None,
                "siteforge_owner_state": None,
                "finished_tag": row.get("tag"),
                "finished_placeholder": row.get("placeholder"),
                "engineer_modified": row.get("engineer_modified"),
                "emu_tags": row.get("emu_tags") or [],
                "notes": ["finished adapter not mapped to Site Forge RIO"],
            }
        )

    # Word 600.0–600.9 detail (Fortna octal word on SF channels)
    word600: list[dict[str, Any]] = []
    for bit in range(10):
        matches = [
            c
            for c in comparisons
            if c.get("siteforge")
            and str((c["siteforge"] or {}).get("fortna_word") or "") in ("600", "600.0")
            and (c["siteforge"] or {}).get("bit") == bit
        ]
        if not matches:
            # Also accept by known endpoint T_* Data[0].bit after bank match
            matches = [
                c
                for c in comparisons
                if c.get("siteforge")
                and (c["siteforge"] or {}).get("data_index") == 0
                and (c["siteforge"] or {}).get("bit") == bit
                and (c["siteforge"] or {}).get("direction") == "I"
                and str((c["siteforge"] or {}).get("channel") or "").endswith(f"Data[0].{bit}")
                and "AENT_1" in str((c["siteforge"] or {}).get("rio_name") or "")
            ]
        if matches:
            word600.append(matches[0])
        else:
            word600.append(
                {
                    "key": f"word600.{bit}",
                    "classification": "NOT_COMPARABLE",
                    "notes": ["word 600 bit not present in compare set"],
                    "bit": bit,
                }
            )

    # Confirm 600.0 → Data[0].0
    w600_0 = next(
        (
            c
            for c in comparisons
            if c.get("siteforge")
            and (c["siteforge"] or {}).get("bit") == 0
            and str((c["siteforge"] or {}).get("fortna_word") or "") == "600"
        ),
        None,
    )
    if w600_0 is None:
        w600_0 = next(
            (
                c
                for c in comparisons
                if (c.get("siteforge") or {}).get("channel", "").endswith(":I.Data[0].0")
                and "AENT_1" in str((c.get("siteforge") or {}).get("rio_name") or "")
            ),
            None,
        )

    siteforge_l5x_meta = None
    if siteforge_l5x and Path(siteforge_l5x).is_file():
        p = Path(siteforge_l5x)
        siteforge_l5x_meta = {
            "path": str(p),
            "size": p.stat().st_size,
            "sha256": _sha256_file(p),
            "note": "Optional compare only — primary Site Forge side is HardwareIOModel from virgin RUN",
        }

    return {
        "ok": True,
        "generated_at": _ts(),
        "policy": {
            "finished_plc": "validation_oracle_only",
            "no_run_relationships_from_finished": True,
            "no_machine_specific_branches": True,
        },
        "gate0": {
            "runtime_sha": git_sha,
            "virgin_run_fingerprint": fp,
            "oracle": {
                "path": str(oracle_path),
                "size": oracle_size,
                "sha256": oracle_sha,
            },
            "machine": machine,
            "siteforge_l5x": siteforge_l5x_meta,
        },
        "adapter_map": adapter_map,
        "finished_adapter_ips": fin_ips,
        "counts": {
            "siteforge_channels": len(sf_channels),
            "finished_iomap_channels": len(fin_maps),
            "comparisons": len(comparisons),
            "by_classification": {k: int(totals.get(k, 0)) for k in CLASSIFICATIONS},
        },
        "word600_confirm": {
            "fortna_word_bit": "600.0",
            "siteforge_channel": (w600_0 or {}).get("siteforge", {}) or {},
            "finished_channel": (w600_0 or {}).get("finished", {}) or {},
            "classification": (w600_0 or {}).get("classification"),
            "maps_to_data0_0": bool(
                w600_0
                and (w600_0.get("siteforge") or {}).get("data_index") == 0
                and (w600_0.get("siteforge") or {}).get("bit") == 0
                and str((w600_0.get("siteforge") or {}).get("channel") or "").endswith(
                    "Data[0].0"
                )
            ),
            "assign_how": (w600_0 or {}).get("siteforge", {})
            and (w600_0.get("siteforge") or {}).get("assign_how"),
        },
        "word600_detail": word600,
        "comparisons": comparisons,
        "hardware_stats": model.get("stats") or {},
        "gate2_data_index": {
            "rule": "Data[n] = Flex Logix image index = data_index_for_module(slot) = slot-1 for 1794 when slot>0",
            "first_bad_transform": "catalog_word_bank false name match used Bank trailing digit as module-name index → wrong slot/Data[2]",
            "fix": "configio_bank_match joins Configio.Bank ↔ EIPModules InputBank/OutputBank only",
        },
    }


def render_md(report: dict[str, Any]) -> str:
    g0 = report.get("gate0") or {}
    fp = g0.get("virgin_run_fingerprint") or {}
    oracle = g0.get("oracle") or {}
    counts = report.get("counts") or {}
    by = counts.get("by_classification") or {}
    w600 = report.get("word600_confirm") or {}
    lines: list[str] = []
    lines.append("# ORINDYAC6 I/O Oracle Diff (HardwareIOModel vs finished PLC)")
    lines.append("")
    lines.append("Finished PLC is **validation oracle only**. No RUN relationships invented from it.")
    lines.append("")
    lines.append("## GATE 0 — Provenance")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Runtime SHA | `{g0.get('runtime_sha')}` |")
    lines.append(f"| Machine | `{g0.get('machine')}` |")
    lines.append(f"| Virgin RUN | `{fp.get('run_dir')}` |")
    lines.append(f"| Virgin fingerprint (combined SHA256) | `{fp.get('combined_sha256')}` |")
    lines.append(f"| Oracle path | `{oracle.get('path')}` |")
    lines.append(f"| Oracle size | `{oracle.get('size')}` |")
    lines.append(f"| Oracle SHA256 | `{oracle.get('sha256')}` |")
    sf_meta = g0.get("siteforge_l5x")
    if sf_meta:
        lines.append(
            f"| Site Forge L5X (optional) | `{sf_meta.get('path')}` "
            f"size={sf_meta.get('size')} sha256=`{sf_meta.get('sha256')}` |"
        )
    lines.append("")
    lines.append("### Virgin RUN fingerprint files")
    lines.append("")
    lines.append("| Path | Size | SHA256 |")
    lines.append("|------|------|--------|")
    for f in fp.get("files") or []:
        if f.get("missing"):
            lines.append(f"| `{f.get('path')}` | MISSING | |")
        else:
            lines.append(f"| `{f.get('path')}` | {f.get('size')} | `{f.get('sha256')}` |")
    lines.append("")
    lines.append("## Adapter map (IP / order — generic)")
    lines.append("")
    lines.append("| Site Forge | Finished | How | Detail |")
    lines.append("|------------|----------|-----|--------|")
    for ev in (report.get("adapter_map") or {}).get("evidence") or []:
        detail = ev.get("ip") or ev.get("ip_sf") or ""
        if ev.get("how") == "adapter_index":
            detail = f"sf={ev.get('sf_index')} → fin={ev.get('finished_index')}"
        lines.append(
            f"| `{ev.get('siteforge')}` | `{ev.get('finished')}` | {ev.get('how')} | {detail} |"
        )
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Site Forge channels: **{counts.get('siteforge_channels')}**")
    lines.append(f"- Finished IO_MAP channels: **{counts.get('finished_iomap_channels')}**")
    lines.append(f"- Comparisons: **{counts.get('comparisons')}**")
    lines.append("")
    lines.append("| Classification | Count |")
    lines.append("|----------------|------:|")
    for k in CLASSIFICATIONS:
        lines.append(f"| {k} | {by.get(k, 0)} |")
    lines.append("")
    lines.append("## Word 600.0–600.9 detail")
    lines.append("")
    lines.append(
        f"**Confirm 600.0 → Data[0].0:** "
        f"{'YES' if w600.get('maps_to_data0_0') else 'NO'} "
        f"(assign_how=`{w600.get('assign_how')}`, "
        f"channel=`{(w600.get('siteforge_channel') or {}).get('channel')}`)"
    )
    lines.append("")
    lines.append("| Bit | SF channel | SF owner | Finished channel | Finished tag | Class |")
    lines.append("|----:|------------|----------|------------------|--------------|-------|")
    for row in report.get("word600_detail") or []:
        sf = row.get("siteforge") or {}
        fin = row.get("finished") or {}
        bit = sf.get("bit")
        if bit is None:
            bit = row.get("bit")
        lines.append(
            f"| {bit} | `{sf.get('channel')}` | `{row.get('siteforge_owner')}` | "
            f"`{fin.get('channel')}` | `{row.get('finished_tag')}` | "
            f"**{row.get('classification')}** |"
        )
    lines.append("")
    lines.append("## GATE 2 — What `Data[]` means")
    lines.append("")
    g2 = report.get("gate2_data_index") or {}
    lines.append("For **1794 Flex I/O**:")
    lines.append("")
    lines.append("```")
    lines.append("chassis slot S  (AENT head = slot 0)")
    lines.append("Logix module Data image index = data_index_for_module(S)")
    lines.append("                            = S − 1   when S > 0")
    lines.append("```")
    lines.append("")
    lines.append(
        "`Data[n]` is the **Flex Logix image index**, not Configio.Bank and not Fortna Octal_Word."
    )
    lines.append("")
    lines.append(f"- Rule: {g2.get('rule')}")
    lines.append(f"- First bad transform: {g2.get('first_bad_transform')}")
    lines.append(f"- Fix: {g2.get('fix')}")
    lines.append("")
    lines.append(
        "Word 600 Configio Desc `1794-IA16-600-4` must assign via "
        "`configio_bank_match` (Bank↔InputBank) → slot 1 → `T_1794_AENT_1:I.Data[0].*`. "
        "The false `catalog_word_bank` name match previously selected module "
        "`1794-IA16-4` at slot 3 → **Data[2]**."
    )
    lines.append("")
    lines.append("## Classification legend")
    lines.append("")
    lines.append("| Class | Meaning |")
    lines.append("|-------|---------|")
    lines.append("| EXACT_MATCH | Endpoint + owner (cookie-cutter / normalized) agree |")
    lines.append("| OWNER_MATCH_ENDPOINT_MISMATCH | Owner equivalent; Data[]/adapter/bit disagree |")
    lines.append("| ENDPOINT_MATCH_OWNER_MISMATCH | Same endpoint; owners disagree |")
    lines.append("| MISSING_SITEFORGE_OWNER | Finished has real tag; HardwareIOModel lacks ASSIGNED owner |")
    lines.append("| EXTRA_SITEFORGE_OWNER | HardwareIOModel ASSIGNED; finished placeholder or absent |")
    lines.append("| FINISHED_PLACEHOLDER | Finished `NO_PointPlaceholder` (cookie-cutter unused fill) |")
    lines.append("| ENGINEER_MODIFIED | Finished rung includes `_EMU_*` parallel (engineer overlay) |")
    lines.append("| AMBIGUOUS | Owner equivalence unproven — both values retained |")
    lines.append("| NOT_COMPARABLE | Adapter/endpoint outside discrete Flex IO_MAP compare |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--machine", default="ORINDYAC6")
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--siteforge-l5x", type=Path, default=DEFAULT_SITEFORGE_L5X)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(argv)

    if not args.oracle.is_file():
        print(f"ERROR: finished oracle missing: {args.oracle}", file=sys.stderr)
        return 2
    run_dir = args.run_dir
    if not (run_dir / "project.cfg").is_file() and (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    if not (run_dir / "project.cfg").is_file():
        print(f"ERROR: virgin RUN missing project.cfg under {args.run_dir}", file=sys.stderr)
        return 2

    report = build_diff(
        run_dir=run_dir,
        machine=args.machine,
        oracle_path=args.oracle,
        siteforge_l5x=args.siteforge_l5x if args.siteforge_l5x.is_file() else None,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_md(report), encoding="utf-8")

    by = (report.get("counts") or {}).get("by_classification") or {}
    w600 = report.get("word600_confirm") or {}
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    print("TOTALS", json.dumps(by, sort_keys=True))
    print(
        "WORD600.0",
        "maps_to_Data[0].0=" + str(w600.get("maps_to_data0_0")),
        "channel=" + str((w600.get("siteforge_channel") or {}).get("channel")),
        "class=" + str(w600.get("classification")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
