"""Sorter_Track from FortnaPlus Sorter build UI.

Primary path: load tools/libraries/programs/Sorter_Track_Program.L5X (gold Fortna
sorter pack — diverts, encoders, track, wave, scanner) and **configure** it from
the Sorter build panel (divert count, ENC tags, tracking/induct conveyors).

Fallback: minimal live scaffold if the pack file is missing.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LIB_DIR = REPO_ROOT / "tools" / "libraries"
PROGRAM_DIR = LIB_DIR / "programs"
SORTER_TRACK_PACK = PROGRAM_DIR / "Sorter_Track_Program.L5X"
WAVE_AOI_PATH = LIB_DIR / "TRK_Divert_WaveFunction_AOI.L5X"
ENC_ROUTINE_PATH = LIB_DIR / "Enc_Routine_ST.L5X"

# Gold Greensboro encoder / track conveyors in pack order (Encoder routine)
GOLD_ENC_CONVEYORS = ("P504", "P506", "P508", "P509", "P510")


def _safe(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    if s and s[0].isdigit():
        s = "T_" + s
    return s[:40]


def _xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def extract_tag_block(library_text: str, tag_name: str) -> str | None:
    pat = rf'<Tag Name="{re.escape(tag_name)}"[^>]*>.*?</Tag>'
    m = re.search(pat, library_text, re.S)
    return m.group(0) if m else None


def load_wave_aoi_xml() -> str:
    path = WAVE_AOI_PATH
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r'<EncodedData\b[^>]*Name="TRK_Divert_WaveFunction"[^>]*>.*?</EncodedData>',
        text,
        re.S,
    )
    if m:
        return m.group(0)
    m = re.search(
        r'<AddOnInstructionDefinition\b[^>]*Name="TRK_Divert_WaveFunction"[^>]*>'
        r".*?</AddOnInstructionDefinition>",
        text,
        re.S,
    )
    return m.group(0) if m else ""


def sorter_build_is_configured(sorter: dict | None) -> bool:
    if not sorter or not isinstance(sorter, dict):
        return False
    if (sorter.get("induct_conveyor") or "").strip():
        return True
    if int(sorter.get("tracking_count") or 0) > 0:
        return True
    if int(sorter.get("divert_count") or 0) > 0:
        return True
    if any((t or {}).get("conveyor") for t in (sorter.get("tracking") or [])):
        return True
    return False


def _collect_encoder_rows(sorter: dict) -> list[dict]:
    rows: list[dict] = []
    if (sorter or {}).get("induct_has_encoder") == "yes":
        conv = (sorter.get("induct_conveyor") or "").strip()
        rows.append({
            "conveyor": conv,
            "encoder_type": sorter.get("induct_encoder_type") or "Enc_RIOCard",
            "encoder_tag": (sorter.get("induct_encoder_tag") or "").strip(),
            "role": "induct",
        })
    for t in sorter.get("tracking") or []:
        if not t or t.get("has_encoder") != "yes":
            continue
        rows.append({
            "conveyor": (t.get("conveyor") or "").strip(),
            "encoder_type": t.get("encoder_type") or "Enc_RIOCard",
            "encoder_tag": (t.get("encoder_tag") or "").strip(),
            "role": "tracking",
            "pe": (t.get("pe") or "").strip(),
        })
    return rows


def resolve_enc_tag_name(row: dict) -> str:
    et = (row.get("encoder_tag") or "").strip()
    if et:
        return _safe(et)
    conv = (row.get("conveyor") or "").strip()
    m = re.match(r"^P(\d+[A-Z]?)$", conv, re.I)
    if m:
        return _safe(f"ENC{m.group(1)}")
    if conv:
        return _safe(f"{conv}_Enc")
    return "NO_Enc"


def _load_program_export(path: Path) -> dict | None:
    """Same shape as fortna_autogen.load_program_export (avoid circular import)."""
    path = Path(path)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
    m = re.search(r'<Program\s+Use="Target"\s+([^>]+)>(.*?)</Program>', text, re.S)
    if not m:
        m = re.search(r'<Program\s+Name="([^"]+)"([^>]*)>(.*?)</Program>', text, re.S)
        if not m:
            return None
        name = m.group(1)
        attrs = f'Name="{name}"' + m.group(2)
        body = m.group(3)
    else:
        attrs = m.group(1)
        body = m.group(2)
        nm = re.search(r'Name="([^"]+)"', attrs)
        name = nm.group(1) if nm else "Sorter_Track"

    program_xml = f"<Program {attrs}>{body}</Program>"
    program_xml = re.sub(r'\s*Use="Target"', "", program_xml, count=1)
    # Force program name Sorter_Track
    program_xml = re.sub(
        r'Name="[^"]+"',
        'Name="Sorter_Track"',
        program_xml,
        count=1,
    )

    tags: list[str] = []
    ctx = re.search(r'<Tags\s+Use="Context"[^>]*>(.*?)</Tags>', text, re.S)
    if ctx:
        for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", ctx.group(1), re.S):
            tags.append(tm.group(0))
    prog_tags = re.search(r"<Program[^>]*>\s*<Tags>(.*?)</Tags>", text, re.S)
    if prog_tags and prog_tags.group(1).strip():
        for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", prog_tags.group(1), re.S):
            tags.append(tm.group(0))

    dt = re.search(r"<DataTypes\b[^>]*>.*?</DataTypes>", text, re.S)
    aoi = re.search(
        r"<AddOnInstructionDefinitions\b[^>]*>.*?</AddOnInstructionDefinitions>",
        text,
        re.S,
    )
    dt_xml = ""
    if dt:
        dt_xml = re.sub(r"<DataTypes\b[^>]*>", "<DataTypes>", dt.group(0), count=1)
    aoi_xml = ""
    if aoi:
        aoi_xml = re.sub(
            r"<AddOnInstructionDefinitions\b[^>]*>",
            "<AddOnInstructionDefinitions>",
            aoi.group(0),
            count=1,
        )
    return {
        "name": "Sorter_Track",
        "program_xml": program_xml,
        "tags": tags,
        "datatypes_xml": dt_xml,
        "aois_xml": aoi_xml,
        "source": str(path),
        "tag_count": len(tags),
    }


def _apply_token_renames(text: str, pairs: list[tuple[str, str]]) -> str:
    """Replace gold tokens with site names (longest first, word-ish boundaries)."""
    if not pairs or not text:
        return text
    # Longest old first to avoid P50 eating P504
    ordered = sorted(pairs, key=lambda kv: -len(kv[0]))
    for old, new in ordered:
        if not old or not new or old == new:
            continue
        # Tag names / ladder operands: match token boundaries
        text = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])",
            new,
            text,
        )
    return text


def _limit_wave_divert_rungs(program_xml: str, divert_n: int) -> tuple[str, int, int]:
    """Keep first divert_n TRK_Divert_WaveFunction rungs; NOP the rest."""
    divert_n = max(0, min(64, int(divert_n or 0)))
    m = re.search(
        r'(<Routine Name="Wave_Divert"[^>]*>)(.*?)(</Routine>)',
        program_xml,
        re.S,
    )
    if not m:
        return program_xml, 0, 0
    head, body, tail = m.group(1), m.group(2), m.group(3)
    kept = 0
    total = 0

    def _rung_repl(rm: re.Match) -> str:
        nonlocal kept, total
        rung = rm.group(0)
        if "TRK_Divert_WaveFunction" not in rung:
            return rung
        total += 1
        if kept < divert_n:
            kept += 1
            return rung
        # Disable extra gold lanes
        rung = re.sub(
            r"<Text>\s*<!\[CDATA\[.*?\]\]>\s*</Text>",
            "<Text><![CDATA[NOP();]]></Text>",
            rung,
            count=1,
            flags=re.S,
        )
        # Soften comment
        if "<Comment>" in rung:
            rung = re.sub(
                r"<Comment>\s*<!\[CDATA\[.*?\]\]>\s*</Comment>",
                f"<Comment><![CDATA[DISABLED — Sorter build divert_count={divert_n}]]></Comment>",
                rung,
                count=1,
                flags=re.S,
            )
        return rung

    new_body = re.sub(r"<Rung\b[^>]*>.*?</Rung>", _rung_repl, body, flags=re.S)
    new_prog = program_xml[: m.start()] + head + new_body + tail + program_xml[m.end() :]
    return new_prog, kept, total


def _limit_encoder_rungs(program_xml: str, keep_n: int) -> tuple[str, int, int]:
    """Keep first keep_n Enc_RIOCard (or Enc_*) rungs in Encoder routine; NOP rest."""
    keep_n = max(0, min(40, int(keep_n or 0)))
    m = re.search(
        r'(<Routine Name="Encoder"[^>]*>)(.*?)(</Routine>)',
        program_xml,
        re.S,
    )
    if not m:
        return program_xml, 0, 0
    head, body, tail = m.group(1), m.group(2), m.group(3)
    kept = 0
    total = 0

    def _rung_repl(rm: re.Match) -> str:
        nonlocal kept, total
        rung = rm.group(0)
        if not re.search(r"Enc_(?:RIOCard|CounterCard|Virtual)", rung):
            return rung
        total += 1
        if kept < keep_n:
            kept += 1
            return rung
        rung = re.sub(
            r"<Text>\s*<!\[CDATA\[.*?\]\]>\s*</Text>",
            "<Text><![CDATA[NOP();]]></Text>",
            rung,
            count=1,
            flags=re.S,
        )
        if "<Comment>" in rung:
            rung = re.sub(
                r"<Comment>\s*<!\[CDATA\[.*?\]\]>\s*</Comment>",
                f"<Comment><![CDATA[DISABLED — Sorter build encoder count={keep_n}]]></Comment>",
                rung,
                count=1,
                flags=re.S,
            )
        return rung

    new_body = re.sub(r"<Rung\b[^>]*>.*?</Rung>", _rung_repl, body, flags=re.S)
    new_prog = program_xml[: m.start()] + head + new_body + tail + program_xml[m.end() :]
    return new_prog, kept, total


def _build_rename_pairs(sorter: dict) -> list[tuple[str, str]]:
    """
    Map gold P504/P506/… encoder conveyors → site conveyors + ENC tags.

    Also map induct if provided onto first free gold slot.
    """
    pairs: list[tuple[str, str]] = []
    enc_rows = _collect_encoder_rows(sorter)
    # Site tracking conveyors in order (for Conv renames)
    track_convs: list[str] = []
    for t in sorter.get("tracking") or []:
        c = ((t or {}).get("conveyor") or "").strip()
        if c:
            track_convs.append(_safe(c) if not c.upper().startswith("P") else c)

    # Encoder slots: gold P504 → site ENC/P_Enc + P_Conv
    for i, gold in enumerate(GOLD_ENC_CONVEYORS):
        if i < len(enc_rows):
            row = enc_rows[i]
            site_conv = (row.get("conveyor") or "").strip() or (
                track_convs[i] if i < len(track_convs) else ""
            )
            site_enc = resolve_enc_tag_name(row)
            if site_enc and site_enc != "NO_Enc":
                pairs.append((f"{gold}_Enc_AOI", f"{site_enc}_AOI"))
                pairs.append((f"{gold}_Enc", site_enc))
            if site_conv:
                sc = _safe(site_conv)
                # Conv UDT: P504_Conv → P509_Conv
                pairs.append((f"{gold}_Conv", f"{sc}_Conv" if not sc.endswith("_Conv") else sc))
                # bare conveyor token less common — still map gold base last
                pairs.append((gold, sc))
        elif i < len(track_convs):
            sc = _safe(track_convs[i])
            pairs.append((f"{gold}_Conv", f"{sc}_Conv" if not sc.endswith("_Conv") else sc))
            pairs.append((gold, sc))

    # Induct conveyor → often maps to first track gold if not already used
    induct = (sorter.get("induct_conveyor") or "").strip()
    if induct:
        pairs.append(("Induct_Conv", f"{_safe(induct)}_Conv"))

    # Deduplicate keeping first mapping for each old
    seen_old: set[str] = set()
    out: list[tuple[str, str]] = []
    for old, new in sorted(pairs, key=lambda kv: -len(kv[0])):
        if old in seen_old or not new:
            continue
        seen_old.add(old)
        out.append((old, new))
    return out


def _append_build_config_routine(program_xml: str, sorter: dict, renames: list) -> str:
    """Add Build_Config ST routine + JSR from Main if missing."""
    lines = [
        '// FortnaPlus configured Sorter_Track_Program.L5X',
        f'// Induct={(sorter.get("induct_conveyor") or "—")} PE={(sorter.get("induct_pe") or "—")}',
        f'// Tracking={int(sorter.get("tracking_count") or 0)} '
        f'diverts={int(sorter.get("divert_count") or 0)}',
        f'// Encoders Yes={len(_collect_encoder_rows(sorter))}',
    ]
    for i, (old, new) in enumerate(renames[:40]):
        lines.append(f"// Map {old} → {new}")
    st_body = "".join(
        f'<Line Number="{i}"><Text><![CDATA[{_xml_escape(ln)}]]></Text></Line>'
        for i, ln in enumerate(lines)
    )
    routine = (
        f'<Routine Name="Build_Config" Type="ST">'
        f"<STLines>{st_body}</STLines></Routine>"
    )
    if 'Name="Build_Config"' in program_xml:
        return program_xml
    # Insert before </Routines>
    if "</Routines>" in program_xml:
        program_xml = program_xml.replace("</Routines>", routine + "</Routines>", 1)
    # JSR on Main if present
    main_m = re.search(
        r'(<Routine Name="Main"[^>]*>.*?<RLLContent>)(.*?)(</RLLContent>.*?</Routine>)',
        program_xml,
        re.S,
    )
    if main_m and "JSR(Build_Config" not in main_m.group(0):
        # Find max rung number
        nums = [int(x) for x in re.findall(r'Rung Number="(\d+)"', main_m.group(2))]
        n = (max(nums) + 1) if nums else 0
        jsr = (
            f'<Rung Number="{n}" Type="N">'
            f"<Comment><![CDATA[Sorter build config snapshot]]></Comment>"
            f"<Text><![CDATA[JSR(Build_Config,0);]]></Text></Rung>"
        )
        program_xml = (
            program_xml[: main_m.start(2)]
            + main_m.group(2)
            + jsr
            + program_xml[main_m.end(2) :]
        )
    return program_xml


def _merge_aoi_xml(pack_aoi: str, extra: str) -> str:
    if not extra:
        return pack_aoi or ""
    if not pack_aoi:
        return (
            f"<AddOnInstructionDefinitions>{extra}</AddOnInstructionDefinitions>"
            if not extra.strip().startswith("<AddOnInstructionDefinitions")
            else extra
        )
    if "TRK_Divert_WaveFunction" in pack_aoi:
        return pack_aoi
    # Insert before closing
    if "</AddOnInstructionDefinitions>" in pack_aoi:
        return pack_aoi.replace(
            "</AddOnInstructionDefinitions>",
            extra + "</AddOnInstructionDefinitions>",
            1,
        )
    return pack_aoi + extra


def build_configured_sorter_track(
    sorter: dict,
    library_text: str,
    *,
    io_points: list | None = None,
    word_map: dict | None = None,
    pack_path: Path | None = None,
) -> dict:
    """
    Load Sorter_Track_Program.L5X and apply Sorter build configuration.

    Returns {name, program_xml, tags, aoi_xml, datatypes_xml, report}.
    """
    path = Path(pack_path) if pack_path else SORTER_TRACK_PACK
    pack = _load_program_export(path)
    if not pack:
        # Fallback minimal scaffold
        return build_live_sorter_track(
            sorter,
            library_text,
            io_points=io_points,
            word_map=word_map,
        )

    sorter = sorter or {}
    divert_n = max(0, min(64, int(sorter.get("divert_count") or 0)))
    enc_rows = _collect_encoder_rows(sorter)
    enc_n = len(enc_rows)

    program_xml = pack["program_xml"]
    tags = list(pack.get("tags") or [])
    aoi_xml = pack.get("aois_xml") or ""
    dt_xml = pack.get("datatypes_xml") or ""

    # 1) Divert count → Wave_Divert
    if divert_n > 0:
        program_xml, wave_kept, wave_total = _limit_wave_divert_rungs(
            program_xml, divert_n
        )
    else:
        # 0 means leave all gold lanes (user did not set count)
        wave_kept, wave_total = -1, -1
        # Still count
        wave_total = len(re.findall(r"TRK_Divert_WaveFunction\(", program_xml))
        wave_kept = wave_total

    # 2) Encoder count → Encoder routine (only when user set Yes rows)
    if enc_n > 0:
        program_xml, enc_kept, enc_total = _limit_encoder_rungs(program_xml, enc_n)
    else:
        enc_kept, enc_total = -1, len(re.findall(r"Enc_RIOCard\(", program_xml))

    # 3) Rename gold P504/… → site conveyors / ENC###
    renames = _build_rename_pairs(sorter)
    if renames:
        program_xml = _apply_token_renames(program_xml, renames)
        tags = [_apply_token_renames(t, renames) for t in tags]

    # 4) Build_Config ST snapshot
    program_xml = _append_build_config_routine(program_xml, sorter, renames)

    # 5) Ensure WaveFunction AOI present
    wave_extra = load_wave_aoi_xml()
    aoi_xml = _merge_aoi_xml(aoi_xml, wave_extra)

    # 6) Optional: inject Enc ST presets from Enc_Routine_ST for site enc tags
    #    (pack already has Encoder RLL; ST presets help HMI ratios)
    if enc_rows and ENC_ROUTINE_PATH.is_file():
        # Add Enc_UDT tags for site names if rename left gaps
        for row in enc_rows:
            en = resolve_enc_tag_name(row)
            if en == "NO_Enc":
                continue
            # Tag may already exist after rename from P504_Enc
            if not any(f'Tag Name="{en}"' in t for t in tags):
                src = extract_tag_block(library_text, "NO_Enc") or extract_tag_block(
                    library_text, "P504_Enc"
                )
                if src:
                    tags.append(
                        re.sub(
                            r'Tag Name="[^"]+"',
                            f'Tag Name="{_xml_escape(en)}"',
                            src,
                            count=1,
                        )
                    )

    report = {
        "mode": "configured_pack",
        "source": str(path),
        "divert_count": divert_n,
        "wave_rungs_kept": wave_kept,
        "wave_rungs_in_pack": wave_total,
        "encoder_count": enc_n,
        "encoder_rungs_kept": enc_kept,
        "encoders": [resolve_enc_tag_name(r) for r in enc_rows],
        "renames": [{"from": a, "to": b} for a, b in renames[:40]],
        "induct": (sorter.get("induct_conveyor") or ""),
        "tracking_count": int(sorter.get("tracking_count") or 0),
        "tag_count": len(tags),
        "wave_aoi_merged": bool(wave_extra),
    }
    return {
        "name": "Sorter_Track",
        "program_xml": program_xml,
        "tags": tags,
        "aoi_xml": aoi_xml,
        "datatypes_xml": dt_xml,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Minimal live scaffold (fallback only)
# ---------------------------------------------------------------------------

def _rung_xml(n: int, text: str, comment: str = "") -> str:
    c = ""
    if comment:
        body = _xml_escape(comment).replace("]]>", "]] >")
        c = f"<Comment><![CDATA[{body}]]></Comment>"
    return (
        f'<Rung Number="{n}" Type="N">{c}'
        f"<Text><![CDATA[{text}]]></Text></Rung>"
    )


def _st_line(n: int, text: str) -> str:
    return f'<Line Number="{n}"><Text><![CDATA[{text}]]></Text></Line>'


def _bool_tag(name: str, val: int = 0) -> str:
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="BOOL" '
        f'Radix="Decimal" Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{val}]]></Data>'
        f'<Data Format="Decorated"><DataValue DataType="BOOL" Value="{val}"/></Data></Tag>'
    )


def _dint_tag(name: str, val: int = 0) -> str:
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="DINT" '
        f'Radix="Decimal" Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{val}]]></Data>'
        f'<Data Format="Decorated">'
        f'<DataValue DataType="DINT" Radix="Decimal" Value="{val}"/></Data></Tag>'
    )


def _enc_udt_tag(name: str, library_text: str) -> str:
    src = extract_tag_block(library_text, "NO_Enc") or extract_tag_block(
        library_text, "P504_Enc"
    )
    if src:
        return re.sub(
            r'Tag Name="[^"]+"', f'Tag Name="{_xml_escape(name)}"', src, count=1
        )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Enc_UDT" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="Decorated"><Structure DataType="Enc_UDT"/></Data></Tag>'
    )


def _enc_aoi_tag(name: str, aoi_type: str, library_text: str) -> str:
    for cand in ("P504_Enc_AOI", "P506_Enc_AOI"):
        src = extract_tag_block(library_text, cand)
        if src:
            return re.sub(
                r'Tag Name="[^"]+"', f'Tag Name="{_xml_escape(name)}"', src, count=1
            )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" '
        f'DataType="{_xml_escape(aoi_type)}" Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="Decorated"><Structure DataType="{_xml_escape(aoi_type)}"/></Data></Tag>'
    )


def _pulse_operand(
    enc_name: str,
    io_points: list | None,
    word_map: dict | None,
) -> str:
    want = _safe(enc_name).upper()
    alts = {want, want.removeprefix("T_"), (enc_name or "").upper()}
    for p in io_points or []:
        dn = _safe(getattr(p, "device_name", None) or "").upper()
        raw = (getattr(p, "device_name", None) or "").upper()
        if dn not in alts and raw not in alts:
            if not re.match(r"^ENC\d", raw) and not re.match(r"^ENC\d", dn):
                continue
            if want not in (dn, raw) and want.replace("ENC", "") not in (
                dn.replace("ENC", ""),
                raw.replace("ENC", ""),
            ):
                continue
        word = str(getattr(p, "fortna_bank", None) or "").strip()
        fbit = str(getattr(p, "fortna_bit", None) or "").strip()
        info = (word_map or {}).get(word) or {}
        if not info and word.isdigit():
            info = (word_map or {}).get(str(int(word))) or {}
        if not info:
            continue
        try:
            bit = int(str(fbit).strip())
        except Exception:
            bit = None
        if bit is None or bit < 0 or bit > 15:
            continue
        rio = info.get("rio_name") or ""
        slot = int(info.get("flex_slot") or 0)
        if rio:
            return f"{rio}:I.Data[{slot}].{bit}"
    return "AlwaysOff"


def build_live_sorter_track(
    sorter: dict,
    library_text: str,
    *,
    io_points: list | None = None,
    word_map: dict | None = None,
    area_start_tag: str = "AlwaysOn",
) -> dict:
    """Minimal fallback when Sorter_Track_Program.L5X is missing."""
    sorter = sorter or {}
    divert_n = max(0, min(64, int(sorter.get("divert_count") or 0)))
    enc_rows = _collect_encoder_rows(sorter)
    tags: list[str] = []
    seen: set[str] = set()

    def add_tag(block: str) -> None:
        m = re.search(r'Tag Name="([^"]+)"', block)
        if not m or m.group(1) in seen:
            return
        seen.add(m.group(1))
        tags.append(block)

    for lib_tag in ("AlwaysOff", "AlwaysOn", "HMI_StatsClear", "Enc_Type0", "NO_Enc"):
        b = extract_tag_block(library_text, lib_tag)
        if b:
            add_tag(b)
        elif lib_tag in ("AlwaysOff", "AlwaysOn", "HMI_StatsClear"):
            add_tag(_bool_tag(lib_tag, 1 if lib_tag == "AlwaysOn" else 0))

    st_lines = [
        _st_line(0, "// Fallback live scaffold — pack L5X missing"),
    ]
    enc_rungs = [_rung_xml(0, "NOP();", "Encoder")]
    rn = 1
    for row in enc_rows:
        en = resolve_enc_tag_name(row)
        if en == "NO_Enc":
            continue
        add_tag(_enc_udt_tag(en, library_text))
        add_tag(_enc_aoi_tag(f"{en}_AOI", "Enc_RIOCard", library_text))
        pulse = _pulse_operand(en, io_points, word_map)
        conv = row.get("conveyor") or ""
        conv_udt = f"{_safe(conv)}_Conv" if conv else "NO_Conv"
        enc_rungs.append(
            _rung_xml(
                rn,
                f"Enc_RIOCard({en}_AOI,{pulse},Enc_Type0,"
                f"{en}.HMI.PPI_Ratio,{conv_udt}.Spd,{conv_udt}.Run,"
                f"{en}.HMI.Allowable_DiffSpd,{en}.HMI.Allowable_PPIDiff,"
                f"{en}.HMI.Disable_PPIFlt,{area_start_tag},HMI_StatsClear,{en});",
                en,
            )
        )
        rn += 1

    wave_rungs = [
        _rung_xml(0, "NOP();", f"Wave divert × {divert_n}"),
    ]
    for i in range(1, divert_n + 1):
        add_tag(_bool_tag(f"Divert{i}_Cmd", 0))
        add_tag(_dint_tag(f"Divert{i}_Output", 0))
        add_tag(
            f'<Tag Name="Divert{i}_Wave" TagType="Base" '
            f'DataType="TRK_Divert_WaveFunction" Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><Structure DataType="TRK_Divert_WaveFunction"/></Data></Tag>'
        )
        wave_rungs.append(
            _rung_xml(
                i,
                f"TRK_Divert_WaveFunction(Divert{i}_Wave,AlwaysOff,"
                f"Divert{i}_Cmd,Divert{i}_Output);",
                f"Divert {i}",
            )
        )

    main = [
        _rung_xml(0, "JSR(Encoder,0);", ""),
        _rung_xml(1, "JSR(Wave_Divert,0);", ""),
    ]
    program_xml = (
        '<Program Name="Sorter_Track" TestEdits="false" MainRoutineName="Main_Routine" '
        'Disabled="false" UseAsFolder="false"><Tags/><Routines>'
        f'<Routine Name="Main_Routine" Type="RLL"><RLLContent>{"".join(main)}</RLLContent></Routine>'
        f'<Routine Name="Encoder" Type="RLL"><RLLContent>{"".join(enc_rungs)}</RLLContent></Routine>'
        f'<Routine Name="Wave_Divert" Type="RLL"><RLLContent>{"".join(wave_rungs)}</RLLContent></Routine>'
        f"</Routines></Program>"
    )
    return {
        "name": "Sorter_Track",
        "program_xml": program_xml,
        "tags": tags,
        "aoi_xml": load_wave_aoi_xml(),
        "datatypes_xml": "",
        "report": {
            "mode": "live_fallback",
            "divert_count": divert_n,
            "encoder_count": len(enc_rows),
            "encoders": [resolve_enc_tag_name(r) for r in enc_rows],
        },
    }


def build_sorter_track(
    sorter: dict,
    library_text: str,
    *,
    io_points: list | None = None,
    word_map: dict | None = None,
) -> dict:
    """Public entry: configured pack preferred, live fallback if pack missing."""
    if SORTER_TRACK_PACK.is_file():
        return build_configured_sorter_track(
            sorter,
            library_text,
            io_points=io_points,
            word_map=word_map,
            pack_path=SORTER_TRACK_PACK,
        )
    return build_live_sorter_track(
        sorter,
        library_text,
        io_points=io_points,
        word_map=word_map,
    )
