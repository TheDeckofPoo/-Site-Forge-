"""Live Sorter_Track L5X from FortnaPlus Sorter build UI config.

Unlike the Greensboro gold Sorter_Track_Program.L5X (fixed ~15 diverts, site tags),
this builds a site-scoped program from induct / tracking / divert counts / encoders.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LIB_DIR = REPO_ROOT / "tools" / "libraries"
WAVE_AOI_PATH = LIB_DIR / "TRK_Divert_WaveFunction_AOI.L5X"
ENC_ROUTINE_PATH = LIB_DIR / "Enc_Routine_ST.L5X"


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
        f'<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="{val}"/></Data></Tag>'
    )


def extract_tag_block(library_text: str, tag_name: str) -> str | None:
    pat = rf'<Tag Name="{re.escape(tag_name)}"[^>]*>.*?</Tag>'
    m = re.search(pat, library_text, re.S)
    return m.group(0) if m else None


def load_wave_aoi_xml() -> str:
    """Return EncodedData AOI block for TRK_Divert_WaveFunction (or empty)."""
    path = WAVE_AOI_PATH
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Prefer EncodedData blob (sealed) — Studio reseals if signature mismatches host
    m = re.search(
        r'<EncodedData\b[^>]*Name="TRK_Divert_WaveFunction"[^>]*>.*?</EncodedData>',
        text,
        re.S,
    )
    if m:
        return m.group(0)
    m = re.search(
        r'<AddOnInstructionDefinition\b[^>]*Name="TRK_Divert_WaveFunction"[^>]*>'
        r'.*?</AddOnInstructionDefinition>',
        text,
        re.S,
    )
    return m.group(0) if m else ""


def _enc_udt_tag(name: str, library_text: str) -> str:
    src = (
        extract_tag_block(library_text, "NO_Enc")
        or extract_tag_block(library_text, "P504_Enc")
    )
    if src:
        return re.sub(r'Tag Name="[^"]+"', f'Tag Name="{_xml_escape(name)}"', src, count=1)
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Enc_UDT" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="Decorated"><Structure DataType="Enc_UDT"/></Data></Tag>'
    )


def _enc_aoi_tag(name: str, aoi_type: str, library_text: str) -> str:
    """Backing tag for Enc_RIOCard / Enc_CounterCard / Enc_Virtual_DistBased."""
    # Prefer matching type from library samples
    for cand in (f"P504_Enc_AOI", "P506_Enc_AOI"):
        src = extract_tag_block(library_text, cand)
        if src and aoi_type in src:
            return re.sub(
                r'Tag Name="[^"]+"',
                f'Tag Name="{_xml_escape(name)}"',
                src,
                count=1,
            ).replace("Enc_RIOCard", aoi_type)
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="{_xml_escape(aoi_type)}" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="Decorated"><Structure DataType="{_xml_escape(aoi_type)}"/></Data></Tag>'
    )


def _pulse_operand(
    enc_name: str,
    io_points: list | None,
    word_map: dict | None,
) -> str:
    """Resolve ENC### bank → CPxRIOn:I.Data[s].b, else AlwaysOff."""
    want = _safe(enc_name).upper()
    # Also try without T_ prefix
    alts = {want, want.removeprefix("T_"), enc_name.upper()}
    for p in io_points or []:
        dn = _safe(getattr(p, "device_name", None) or "").upper()
        raw = (getattr(p, "device_name", None) or "").upper()
        if dn not in alts and raw not in alts and not any(
            a and (dn == a or raw == a or dn.endswith(a) or a in dn) for a in alts if a
        ):
            # ENC504 match
            if not re.match(r"^ENC\d", raw) and not re.match(r"^ENC\d", dn):
                continue
            if not any(a.replace("ENC", "") in dn or a.replace("ENC", "") in raw for a in alts if a.startswith("ENC")):
                if want not in (dn, raw) and want.removeprefix("ENC") not in (dn, raw):
                    continue
        word = str(getattr(p, "fortna_bank", None) or "").strip()
        fbit = str(getattr(p, "fortna_bit", None) or "").strip()
        info = (word_map or {}).get(word) or {}
        if not info and word.isdigit():
            info = (word_map or {}).get(str(int(word))) or {}
        if not info:
            continue
        try:
            bit = int(str(fbit).strip(), 8) if fbit else None  # Fortna bit often octal-ish
        except Exception:
            bit = None
        # Prefer decimal bit 0-15
        try:
            b2 = int(str(fbit).strip())
            if 0 <= b2 <= 15:
                bit = b2
        except Exception:
            pass
        if bit is None or bit < 0 or bit > 15:
            continue
        rio = info.get("rio_name") or ""
        slot = int(info.get("flex_slot") or 0)
        if rio:
            return f"{rio}:I.Data[{slot}].{bit}"
    return "AlwaysOff"


def _collect_encoder_rows(sorter: dict) -> list[dict]:
    """Flatten induct + tracking rows that have encoder Yes."""
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
    """Prefer ENC### from RUN; else P###_Enc from conveyor."""
    et = (row.get("encoder_tag") or "").strip()
    if et:
        return _safe(et)
    conv = (row.get("conveyor") or "").strip()
    m = re.match(r"^P(\d+[A-Z]?)$", conv, re.I)
    if m:
        # Prefer ENC### name matching conveyor number (RUN style)
        return _safe(f"ENC{m.group(1)}")
    if conv:
        return _safe(f"{conv}_Enc")
    return "NO_Enc"


def build_live_sorter_track(
    sorter: dict,
    library_text: str,
    *,
    io_points: list | None = None,
    word_map: dict | None = None,
    area_start_tag: str = "AlwaysOn",
) -> dict:
    """
    Build site-scoped Sorter_Track program.

    Returns {
      name, program_xml, tags: [str], aoi_xml: str, report: dict
    }
    """
    sorter = sorter or {}
    divert_n = max(0, min(64, int(sorter.get("divert_count") or 0)))
    enc_rows = _collect_encoder_rows(sorter)
    induct = (sorter.get("induct_conveyor") or "").strip()
    induct_pe = (sorter.get("induct_pe") or "").strip()
    tracking = list(sorter.get("tracking") or [])

    tags: list[str] = []
    seen: set[str] = set()

    def add_tag(block: str) -> None:
        m = re.search(r'Tag Name="([^"]+)"', block)
        if not m or m.group(1) in seen:
            return
        seen.add(m.group(1))
        tags.append(block)

    # Shared helpers
    for lib_tag in ("AlwaysOff", "AlwaysOn", "HMI_StatsClear", "Enc_Type0", "NO_Enc"):
        b = extract_tag_block(library_text, lib_tag)
        if b:
            add_tag(b)
        elif lib_tag in ("AlwaysOff", "AlwaysOn", "HMI_StatsClear"):
            add_tag(_bool_tag(lib_tag, 1 if lib_tag == "AlwaysOn" else 0))

    # Enc_Type0 SINT if missing
    if "Enc_Type0" not in seen:
        add_tag(
            '<Tag Name="Enc_Type0" TagType="Base" DataType="SINT" Radix="Decimal" '
            'Constant="false" ExternalAccess="Read/Write">'
            '<Data Format="L5K"><![CDATA[0]]></Data>'
            '<Data Format="Decorated"><DataValue DataType="SINT" Radix="Decimal" Value="0"/></Data></Tag>'
        )

    # --- Enc ST routine (presets like Enc_Routine_ST.L5X) ---
    st_lines: list[str] = [
        _st_line(0, f"// FortnaPlus live Sorter_Track Enc — from Sorter build UI"),
        _st_line(1, f"// Induct={induct or '—'} PE={induct_pe or '—'} encoders={len(enc_rows)}"),
    ]
    line_n = 2
    enc_rll_rungs: list[str] = [
        _rung_xml(0, "NOP();", "Encoder pulse → Enc_* AOI (live from Sorter build)"),
    ]
    rll_n = 1

    for row in enc_rows:
        enc_name = resolve_enc_tag_name(row)
        if enc_name == "NO_Enc":
            continue
        aoi_type = row.get("encoder_type") or "Enc_RIOCard"
        if aoi_type not in (
            "Enc_RIOCard",
            "Enc_CounterCard",
            "Enc_Virtual_DistBased",
        ):
            aoi_type = "Enc_RIOCard"
        aoi_tag = f"{enc_name}_AOI"
        conv = row.get("conveyor") or ""
        conv_udt = _safe(f"{conv}_Conv") if conv else "NO_Conv"
        add_tag(_enc_udt_tag(enc_name, library_text))
        add_tag(_enc_aoi_tag(aoi_tag, aoi_type, library_text))

        # ST presets (from Enc_Routine_ST gold pattern)
        st_lines.append(_st_line(line_n, f"{enc_name}.HMI.PPI_Ratio := 0.5;"))
        line_n += 1
        st_lines.append(_st_line(line_n, f"{enc_name}.Enc_FltTime := 500;"))
        line_n += 1
        st_lines.append(_st_line(line_n, f"{enc_name}.PPI_FltTime := 15000;"))
        line_n += 1

        pulse = _pulse_operand(
            enc_name if enc_name.upper().startswith("ENC") else f"ENC{re.sub(r'^P', '', conv, flags=re.I)}",
            io_points,
            word_map,
        )
        # Also try raw encoder_tag / ENC from conveyor number
        if pulse == "AlwaysOff" and row.get("encoder_tag"):
            pulse = _pulse_operand(row["encoder_tag"], io_points, word_map)

        if aoi_type == "Enc_RIOCard":
            text = (
                f"Enc_RIOCard({aoi_tag},{pulse},Enc_Type0,"
                f"{enc_name}.HMI.PPI_Ratio,{conv_udt}.Spd,{conv_udt}.Run,"
                f"{enc_name}.HMI.Allowable_DiffSpd,{enc_name}.HMI.Allowable_PPIDiff,"
                f"{enc_name}.HMI.Disable_PPIFlt,{area_start_tag},HMI_StatsClear,{enc_name});"
            )
            enc_rll_rungs.append(
                _rung_xml(rll_n, text, f"{enc_name} · {conv or '?'} · {aoi_type}")
            )
            rll_n += 1
        else:
            enc_rll_rungs.append(
                _rung_xml(
                    rll_n,
                    "NOP();",
                    f"{enc_name} · {aoi_type} — AOI call stub (wire inputs next)",
                )
            )
            rll_n += 1

    if not enc_rows:
        st_lines.append(_st_line(line_n, "// No encoders selected (Encoder = No on all rows)"))

    enc_st_xml = (
        f'<Routine Name="Enc" Type="ST">'
        f"<STLines>{''.join(st_lines)}</STLines></Routine>"
    )
    enc_rll_xml = (
        f'<Routine Name="Encoder" Type="RLL">'
        f"<RLLContent>{''.join(enc_rll_rungs)}</RLLContent></Routine>"
    )

    # --- Wave divert: exactly divert_count rungs ---
    wave_rungs: list[str] = [
        _rung_xml(
            0,
            "NOP();",
            f"Wave divert · count={divert_n} (from Sorter build — not gold 15-lane pack)",
        ),
    ]
    # Pulse source for wave: first tracking encoder pulse or AlwaysOff
    wave_pulse = "AlwaysOff"
    if enc_rows:
        en0 = resolve_enc_tag_name(enc_rows[0])
        wave_pulse = _pulse_operand(en0, io_points, word_map)
        if wave_pulse == "AlwaysOff":
            wave_pulse = f"{en0}.PPI"  # BOOL may not exist — prefer AlwaysOff
            wave_pulse = "AlwaysOff"

    for i in range(1, divert_n + 1):
        wave_aoi = f"Divert{i}_Wave"
        divert_cmd = f"Divert{i}_Cmd"
        divert_out = f"Divert{i}_Output"
        # Gold: TRK_Divert_WaveFunction(P506_Divert1_Wave, pulse, Divert.O.Divert, Output)
        # Instance tag type = AOI name (sealed EncodedData defines it on import)
        add_tag(_bool_tag(divert_cmd, 0))
        add_tag(_dint_tag(divert_out, 0))
        add_tag(
            f'<Tag Name="{_xml_escape(wave_aoi)}" TagType="Base" '
            f'DataType="TRK_Divert_WaveFunction" Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated"><Structure DataType="TRK_Divert_WaveFunction"/></Data></Tag>'
        )
        text = (
            f"TRK_Divert_WaveFunction({wave_aoi},{wave_pulse},{divert_cmd},{divert_out});"
        )
        wave_rungs.append(
            _rung_xml(i, text, f"Divert {i} of {divert_n} · live Sorter build")
        )

    wave_xml = (
        f'<Routine Name="Wave_Divert" Type="RLL">'
        f"<RLLContent>{''.join(wave_rungs)}</RLLContent></Routine>"
    )

    # --- Config summary ST ---
    cfg_lines = [
        _st_line(0, "// Sorter build snapshot (FortnaPlus)"),
        _st_line(1, f"// Induct conv={induct or '—'} pe={induct_pe or '—'}"),
        _st_line(2, f"// Tracking rows={len(tracking)} diverts={divert_n} encoders={len(enc_rows)}"),
    ]
    for i, t in enumerate(tracking[:40], start=1):
        cfg_lines.append(
            _st_line(
                2 + i,
                f"// Track{i}: {(t or {}).get('conveyor') or '—'} "
                f"pe={(t or {}).get('pe') or '—'} "
                f"enc={(t or {}).get('has_encoder') or 'no'}",
            )
        )
    cfg_xml = (
        f'<Routine Name="Build_Config" Type="ST">'
        f"<STLines>{''.join(cfg_lines)}</STLines></Routine>"
    )

    main_rungs = [
        _rung_xml(0, "JSR(Enc,0);", "Encoder presets (ST)"),
        _rung_xml(1, "JSR(Encoder,0);", "Encoder AOI rungs"),
        _rung_xml(2, "JSR(Wave_Divert,0);", f"Wave divert × {divert_n}"),
        _rung_xml(3, "JSR(Build_Config,0);", "Config comment snapshot"),
    ]
    main_xml = (
        f'<Routine Name="Main_Routine" Type="RLL">'
        f"<RLLContent>{''.join(main_rungs)}</RLLContent></Routine>"
    )

    program_xml = (
        f'<Program Name="Sorter_Track" TestEdits="false" MainRoutineName="Main_Routine" '
        f'Disabled="false" UseAsFolder="false">'
        f"<Tags/>"
        f"<Routines>"
        f"{main_xml}{enc_st_xml}{enc_rll_xml}{wave_xml}{cfg_xml}"
        f"</Routines></Program>"
    )

    aoi_xml = load_wave_aoi_xml()
    return {
        "name": "Sorter_Track",
        "program_xml": program_xml,
        "tags": tags,
        "aoi_xml": aoi_xml,
        "report": {
            "mode": "live",
            "divert_count": divert_n,
            "encoder_count": len(enc_rows),
            "encoders": [resolve_enc_tag_name(r) for r in enc_rows],
            "induct": induct,
            "tracking_count": len(tracking),
            "wave_aoi": bool(aoi_xml),
        },
    }


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
