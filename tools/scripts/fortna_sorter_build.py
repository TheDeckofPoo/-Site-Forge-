"""Sorter_Track from Site Forge Sorter build UI.

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

# Pack-template encoder/track slot tokens inside Sorter_Track_Program.L5X
# (PACK_STANDARD placeholders — remapped by model order; not site decision logic).
PACK_TEMPLATE_ENC_SLOTS = ("P504", "P506", "P508", "P509", "P510")
# Extra gold-pack equipment placeholders sometimes present beside encoder slots.
# These are never site evidence; prune when no SorterModel row maps them.
PACK_TEMPLATE_EXTRA_SLOTS = ("P500", "P502", "P512")
PACK_TEMPLATE_ALL_SLOTS = PACK_TEMPLATE_ENC_SLOTS + PACK_TEMPLATE_EXTRA_SLOTS
# Back-compat alias for older callers/tests
GOLD_ENC_CONVEYORS = PACK_TEMPLATE_ENC_SLOTS


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
    """Collect unique encoder rows (induct + tracking).

    Identical induct encoder/conveyor must not consume a second pack-template
    slot — that previously pushed the real divert-host encoder (e.g. ENC610)
    off the early slots and left P506_Divert* pack hosts unremapped.
    """
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(row: dict) -> None:
        enc = (row.get("encoder_tag") or "").strip().upper()
        conv = (row.get("conveyor") or "").strip().upper()
        key = (enc, conv)
        if enc and key in seen:
            return
        if enc:
            seen.add(key)
        rows.append(row)

    if (sorter or {}).get("induct_has_encoder") == "yes":
        conv = (sorter.get("induct_conveyor") or "").strip()
        _add(
            {
                "conveyor": conv,
                "encoder_type": sorter.get("induct_encoder_type") or "Enc_RIOCard",
                "encoder_tag": (sorter.get("induct_encoder_tag") or "").strip(),
                "role": "induct",
            }
        )
    for t in sorter.get("tracking") or []:
        if not t or t.get("has_encoder") != "yes":
            continue
        _add(
            {
                "conveyor": (t.get("conveyor") or "").strip(),
                "encoder_type": t.get("encoder_type") or "Enc_RIOCard",
                "encoder_tag": (t.get("encoder_tag") or "").strip(),
                "role": "tracking",
                "pe": (t.get("pe") or "").strip(),
            }
        )
    return rows


def _field_plain(v: object) -> str:
    if isinstance(v, dict):
        return str(v.get("value") or "").strip()
    return str(v or "").strip()


def _divert_host_conveyor(sorter: dict) -> str:
    """Primary divert-host conveyor from model (not pack-template slots).

    Prefer tracking row whose encoder/section is associated with divert lanes
    (sorter_build.divert_host_conveyor or known_sorters / tracking with conveyor).
    """
    explicit = (sorter.get("divert_host_conveyor") or sorter.get("sorter_conveyor") or "").strip()
    if explicit:
        return explicit
    # Prefer tracking conveyor that is not the induct-only scan belt when multiple exist
    induct = (sorter.get("induct_conveyor") or "").strip().upper()
    tracking = list(sorter.get("tracking") or [])
    for t in tracking:
        conv = (t or {}).get("conveyor") or ""
        conv = str(conv).strip()
        if not conv:
            continue
        if induct and conv.upper() == induct and len(tracking) > 1:
            continue
        if (t or {}).get("has_encoder") == "yes" or (t or {}).get("encoder_tag"):
            return conv
    for t in tracking:
        conv = str((t or {}).get("conveyor") or "").strip()
        if conv:
            return conv
    # known_sorters may carry encoder → find matching tracking conveyor later
    return (sorter.get("induct_conveyor") or "").strip()


def _build_divert_rename_pairs(sorter: dict) -> list[tuple[str, str]]:
    """Map pack-template P###_Divert* family → RUN divert-host conveyor.

    Pack tags include P506_Divert1, P506_Divert1_AOI, P506_Divert1_Wave, …
    Word-boundary rename of P506 alone does NOT rewrite those. Prefix-family
    pairs (longest first via _apply_token_renames) are required.
    """
    host = _divert_host_conveyor(sorter)
    if not host:
        return []
    host_tok = _safe(host)
    if host_tok.upper().endswith("_CONV"):
        host_tok = host_tok[:-5]
    divert_n = max(0, min(64, int(sorter.get("divert_count") or 0)))
    if divert_n <= 0 and (sorter.get("divert_rows") or []):
        divert_n = len(sorter.get("divert_rows") or [])
    if divert_n <= 0:
        divert_n = 24
    suffixes = (
        "_AOI",
        "_Wave",
        "_Output",
        "_Cmd",
        "_RateLimit",
        "",  # bare P506_DivertN last (shorter)
    )
    pairs: list[tuple[str, str]] = []
    template_hosts = list(PACK_TEMPLATE_ALL_SLOTS)
    for slot in template_hosts:
        if slot.upper() == host_tok.upper():
            continue
        # Family prefix pair covers AOI/Wave/Output descendants when applied
        # with longest-first ordering on full DivertN+suffix tokens.
        for n in range(1, divert_n + 1):
            for suf in suffixes:
                pairs.append(
                    (f"{slot}_Divert{n}{suf}", f"{host_tok}_Divert{n}{suf}")
                )
    return pairs


def resolve_enc_tag_name(row: dict) -> str:
    """Encoder tag from explicit model field only — never invent ENC### from P###."""
    et = (row.get("encoder_tag") or "").strip()
    if et:
        return _safe(et)
    # Do not derive ENC504 from conveyor P504 — Gate G / anti-cheat.
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

    # Controller-scope only: Tags Use="Context".
    # Program <Tags> stay inside program_xml — merging them here caused
    # Duplicate tag (controller + program) for shared BOOLs like P542_Sorter_At_Speed.
    tags: list[str] = []
    ctx = re.search(r'<Tags\s+Use="Context"[^>]*>(.*?)</Tags>', text, re.S)
    if ctx:
        for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", ctx.group(1), re.S):
            tags.append(tm.group(0))
    program_local_tags: list[str] = []
    prog_tags = re.search(r"<Program[^>]*>\s*<Tags>(.*?)</Tags>", text, re.S)
    if prog_tags and prog_tags.group(1).strip():
        for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", prog_tags.group(1), re.S):
            program_local_tags.append(tm.group(0))

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
        "program_local_tags": program_local_tags,
        "datatypes_xml": dt_xml,
        "aois_xml": aoi_xml,
        "source": str(path),
        "tag_count": len(tags),
        "program_local_tag_count": len(program_local_tags),
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
    """Keep/expand TRK_Divert_WaveFunction rungs to model divert_n (cap 64).

    If model needs more slots than the pack template, clone the first wave
    rung pattern and renumber Divert indices (MODEL_EXPANDED).
    """
    divert_n = max(0, min(64, int(divert_n or 0)))
    m = re.search(
        r'(<Routine Name="Wave_Divert"[^>]*>)(.*?)(</Routine>)',
        program_xml,
        re.S,
    )
    if not m:
        return program_xml, 0, 0
    head, body, tail = m.group(1), m.group(2), m.group(3)
    rungs = re.findall(r"<Rung\b[^>]*>.*?</Rung>", body, flags=re.S)
    wave_rungs = [r for r in rungs if "TRK_Divert_WaveFunction" in r]
    other_rungs = [r for r in rungs if "TRK_Divert_WaveFunction" not in r]
    pack_total = len(wave_rungs)
    if divert_n <= 0:
        return program_xml, pack_total, pack_total

    # Expand by cloning first template rung when model > pack slots
    if divert_n > pack_total and wave_rungs:
        template = wave_rungs[0]
        # Find a DivertN token to renumber
        base_m = re.search(r"(Divert)(\d+)", template)
        base_idx = int(base_m.group(2)) if base_m else 1
        for i in range(pack_total, divert_n):
            new_idx = base_idx + i
            cloned = template
            # Renumber rung number later
            cloned = re.sub(
                r"(Divert)\d+",
                rf"\g<1>{new_idx}",
                cloned,
            )
            if "<Comment>" in cloned:
                cloned = re.sub(
                    r"<Comment>\s*<!\[CDATA\[.*?\]\]>\s*</Comment>",
                    f"<Comment><![CDATA[MODEL_EXPANDED divert lane {i + 1}]]></Comment>",
                    cloned,
                    count=1,
                    flags=re.S,
                )
            wave_rungs.append(cloned)

    kept_waves = wave_rungs[:divert_n]
    # NOP any leftover pack waves beyond divert_n
    disabled = []
    for extra in wave_rungs[divert_n:]:
        rung = re.sub(
            r"<Text>\s*<!\[CDATA\[.*?\]\]>\s*</Text>",
            "<Text><![CDATA[NOP();]]></Text>",
            extra,
            count=1,
            flags=re.S,
        )
        if "<Comment>" in rung:
            rung = re.sub(
                r"<Comment>\s*<!\[CDATA\[.*?\]\]>\s*</Comment>",
                f"<Comment><![CDATA[DISABLED — Sorter build divert_count={divert_n}]]></Comment>",
                rung,
                count=1,
                flags=re.S,
            )
        disabled.append(rung)

    # Re-number all rungs sequentially
    ordered = other_rungs + kept_waves + disabled
    renumbered = []
    for i, rung in enumerate(ordered):
        rung = re.sub(r'Rung Number="\d+"', f'Rung Number="{i}"', rung, count=1)
        renumbered.append(rung)
    new_body = "".join(renumbered)
    # Studio requires RLL rungs inside <RLLContent>…</RLLContent>. The rewrite
    # extracts bare <Rung> nodes — always re-wrap (do not emit raw Rungs).
    if new_body and "<RLLContent>" not in new_body:
        new_body = f"<RLLContent>{new_body}</RLLContent>"
    new_prog = program_xml[: m.start()] + head + new_body + tail + program_xml[m.end() :]
    return new_prog, len(kept_waves), pack_total


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


def _mapped_template_slots(sorter: dict) -> dict[str, str]:
    """Map pack-template slots → proven site conveyors by SorterModel order.

    Only slots with a matching model/tracking/encoder row are returned.
    Unmapped template placeholders must NOT be emitted (not remapped to divert_host).
    """
    mapped: dict[str, str] = {}
    enc_rows = _collect_encoder_rows(sorter)
    track_convs: list[str] = []
    for t in sorter.get("tracking") or []:
        c = str(((t or {}).get("conveyor") or "")).strip()
        if c:
            track_convs.append(_safe(c))

    for i, slot in enumerate(PACK_TEMPLATE_ENC_SLOTS):
        site_conv = ""
        if i < len(enc_rows):
            site_conv = str((enc_rows[i] or {}).get("conveyor") or "").strip()
        if not site_conv and i < len(track_convs):
            site_conv = track_convs[i]
        if site_conv:
            mapped[slot] = _safe(site_conv)
    return mapped


def _unmapped_template_slots(sorter: dict) -> tuple[str, ...]:
    """Template placeholders with no SorterModel row — must not be emitted.

    Encoder/track slots (P504…) are unmapped when model rows are exhausted.
    Extra gold placeholders (P500/P502/P512) are always unmapped unless the
    target machine independently proves that exact conveyor identity.
    """
    mapped = _mapped_template_slots(sorter)
    proven_convs = {v.upper() for v in mapped.values()}
    # Also treat divert_host / induct / tracking conveyors as proven identities
    for key in ("divert_host_conveyor", "induct_conveyor", "sorter_conveyor"):
        v = str((sorter or {}).get(key) or "").strip().upper()
        if v:
            proven_convs.add(v)
    for t in (sorter or {}).get("tracking") or []:
        v = str(((t or {}).get("conveyor") or "")).strip().upper()
        if v:
            proven_convs.add(v)

    out: list[str] = [s for s in PACK_TEMPLATE_ENC_SLOTS if s not in mapped]
    for s in PACK_TEMPLATE_EXTRA_SLOTS:
        if s.upper() not in proven_convs:
            out.append(s)
    return tuple(out)


def _prefix_remap_slot_family(text: str, slot: str, site: str) -> str:
    """Rename every ``{slot}_*`` / bare ``{slot}`` token to the site conveyor family.

    Divert* tokens are excluded — they are remapped separately to divert_host.
    """
    if not text or not slot or not site or slot.upper() == site.upper():
        return text
    # Family members: P504_Conv_Track → P606_Conv_Track (not Divert*)
    text = re.sub(
        rf"(?<![A-Za-z0-9_]){re.escape(slot)}_(?!Divert\d*)",
        f"{site}_",
        text,
    )
    # Bare slot token (exact)
    text = re.sub(
        rf"(?<![A-Za-z0-9_]){re.escape(slot)}(?![A-Za-z0-9_])",
        site,
        text,
    )
    return text


def _drop_tag_blocks_for_slots(tag_blocks: list[str], slots: tuple[str, ...]) -> list[str]:
    """Remove controller/program tag declarations owned by unmapped template slots."""
    if not slots:
        return tag_blocks
    keep: list[str] = []
    slot_re = re.compile(
        rf'Tag Name="(?:{"|".join(re.escape(s) for s in slots)})(?:_|")',
        re.I,
    )
    for block in tag_blocks:
        if slot_re.search(block or ""):
            continue
        keep.append(block)
    return keep


def strip_program_tags_by_slot_prefix(program_xml: str, slots: tuple[str, ...]) -> str:
    """Drop program-scoped <Tag> declarations whose names belong to unmapped slots."""
    if not program_xml or not slots:
        return program_xml
    slot_re = re.compile(
        rf'Tag Name="(?:{"|".join(re.escape(s) for s in slots)})(?:_|")',
        re.I,
    )

    def _tag_repl(tm: re.Match) -> str:
        block = tm.group(0)
        return "" if slot_re.search(block) else block

    # Only strip inside the program's own <Tags>…</Tags> (first Tags under Program).
    m = re.search(r"(<Program\b[^>]*>\s*<Tags>)(.*?)(</Tags>)", program_xml, re.S)
    if not m:
        return program_xml
    head, body, tail = m.group(1), m.group(2), m.group(3)
    new_body = re.sub(r"<Tag\b[^>]*>.*?</Tag>", _tag_repl, body, flags=re.S)
    return program_xml[: m.start()] + head + new_body + tail + program_xml[m.end() :]


def _nop_rungs_referencing_slots(program_xml: str, slots: tuple[str, ...]) -> tuple[str, int]:
    """NOP rungs that still reference unmapped template equipment slots.

    Does not delete rung structure (Studio numbering preserved); disables logic
    so unused pack placeholders are never live equipment in the target PLC.
    """
    if not program_xml or not slots:
        return program_xml, 0
    slot_tok = re.compile(
        rf"(?<![A-Za-z0-9_])(?:{'|'.join(re.escape(s) for s in slots)})(?:_|[^A-Za-z0-9_]|$)",
        re.I,
    )
    disabled = 0

    def _rung_repl(rm: re.Match) -> str:
        nonlocal disabled
        rung = rm.group(0)
        if not slot_tok.search(rung):
            return rung
        # Already NOP?
        if re.search(r"<!\[CDATA\[\s*NOP\(\);\s*\]\]>", rung):
            return rung
        new = re.sub(
            r"<Text>\s*<!\[CDATA\[.*?\]\]>\s*</Text>",
            "<Text><![CDATA[NOP();]]></Text>",
            rung,
            count=1,
            flags=re.S,
        )
        if new is rung or new == rung:
            return rung
        disabled += 1
        if "<Comment>" in new:
            new = re.sub(
                r"<Comment>\s*<!\[CDATA\[.*?\]\]>\s*</Comment>",
                "<Comment><![CDATA[DISABLED — unmapped pack-template slot "
                "(no SorterModel row)]]></Comment>",
                new,
                count=1,
                flags=re.S,
            )
        return new

    out = re.sub(r"<Rung\b[^>]*>.*?</Rung>", _rung_repl, program_xml, flags=re.S)
    return out, disabled


def _scrub_unmapped_slot_tokens(text: str, slots: tuple[str, ...]) -> tuple[str, int]:
    """Remove residual unmapped template identity tokens from kept XML/text.

    Used for Decorated/L5K string payloads and any leftover operands after
    tag-drop + rung NOP. Replaces ``P508_Induct``-style tokens with
    ``UNUSED_SLOT_Induct`` so foreign-site equipment names cannot survive.
    """
    if not text or not slots:
        return text, 0
    count = 0
    out = text
    for slot in sorted(slots, key=len, reverse=True):
        def _repl(m: re.Match, _slot: str = slot) -> str:
            full = m.group(0)
            # Preserve suffix after slot stem when present (P508_Induct → UNUSED_SLOT_Induct)
            if "_" in full:
                return "UNUSED_SLOT_" + full.split("_", 1)[1]
            return "UNUSED_SLOT"

        out, n = re.subn(
            rf"(?<![A-Za-z0-9_]){re.escape(slot)}(?:_[A-Za-z0-9_]+)?",
            _repl,
            out,
        )
        count += n
    return out, count


def _apply_mapped_slot_families(
    text: str, mapped: dict[str, str]
) -> str:
    """Prefix-remap mapped template slot families onto proven site conveyors."""
    if not text or not mapped:
        return text
    # Longest slot first (defensive)
    for slot, site in sorted(mapped.items(), key=lambda kv: -len(kv[0])):
        text = _prefix_remap_slot_family(text, slot, site)
    return text


def _build_rename_pairs(sorter: dict) -> list[tuple[str, str]]:
    """
    Map pack-template encoder slots → model conveyors + explicit ENC tags by order.

    Template slot tokens live in Sorter_Track_Program.L5X (PACK_STANDARD).
    Multiplicity comes from SorterModel / sorter_build — never a fixed site count.
    Unmapped slots are omitted here; they are pruned (not remapped) later.
    """
    pairs: list[tuple[str, str]] = []
    enc_rows = _collect_encoder_rows(sorter)
    mapped = _mapped_template_slots(sorter)

    for i, slot in enumerate(PACK_TEMPLATE_ENC_SLOTS):
        site_conv = mapped.get(slot, "")
        if not site_conv:
            continue
        row = enc_rows[i] if i < len(enc_rows) else {}
        site_enc = resolve_enc_tag_name(row) if row else "NO_Enc"
        if site_enc and site_enc != "NO_Enc":
            pairs.append((f"{slot}_Enc_AOI", f"{site_enc}_AOI"))
            pairs.append((f"{slot}_Enc", site_enc))
        sc = _safe(site_conv)
        pairs.append((f"{slot}_Conv", f"{sc}_Conv" if not sc.endswith("_Conv") else sc))
        pairs.append((slot, sc))

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
    mapped = _mapped_template_slots(sorter)
    unmapped = _unmapped_template_slots(sorter)
    lines = [
        '// Site Forge configured Sorter_Track_Program.L5X',
        f'// Induct={(sorter.get("induct_conveyor") or "—")} PE={(sorter.get("induct_pe") or "—")}',
        f'// Tracking={int(sorter.get("tracking_count") or 0)} '
        f'diverts={int(sorter.get("divert_count") or 0)}',
        f'// Encoders Yes={len(_collect_encoder_rows(sorter))}',
        f'// MappedSlots={len(mapped)} UnmappedPruned={len(unmapped)}',
    ]
    # Do NOT echo raw pack-template equipment tokens (P504_…) into ST — those
    # strings are scanned as live legacy PLC template tag references.
    for i, (slot, site) in enumerate(list(mapped.items())[:16]):
        lines.append(f"// Map template_slot[{i}] → {site}")
    host = _divert_host_conveyor(sorter)
    if host:
        lines.append(f"// DivertHost → {_safe(host)}")
    _ = renames  # retained for call-site compatibility; details stay in report JSON
    # Studio ST: CDATA must be direct child of <Line> — nested <Text> is ignored.
    st_body = "".join(
        f'<Line Number="{i}"><![CDATA[{_xml_escape(ln)}]]></Line>'
        for i, ln in enumerate(lines)
    )
    # Studio ST routines require <STContent>, not <STLines> (ignored → dropped logic).
    routine = (
        f'<Routine Name="Build_Config" Type="ST">'
        f"<STContent>{st_body}</STContent></Routine>"
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
    program_local_tags = list(pack.get("program_local_tags") or [])
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

    # 3) Divert UDT hosts FIRST: pack keeps P506_Divert* unless remapped to the
    #    proven divert_host. Tracking-slot remaps must not steal Divert* tokens.
    renames = _build_rename_pairs(sorter)
    divert_renames = _build_divert_rename_pairs(sorter)
    if divert_renames:
        renames = list(renames) + list(divert_renames)
    if renames:
        program_xml = _apply_token_renames(program_xml, renames)
        tags = [_apply_token_renames(t, renames) for t in tags]
        program_local_tags = [_apply_token_renames(t, renames) for t in program_local_tags]
    # 3a2) Sweep remaining pack-template Divert* family prefixes (AOI/Wave/Output)
    host = _divert_host_conveyor(sorter)
    if host:
        host_tok = _safe(host)
        if host_tok.upper().endswith("_CONV"):
            host_tok = host_tok[:-5]
        for slot in list(PACK_TEMPLATE_ALL_SLOTS):
            if slot.upper() == host_tok.upper():
                continue
            # Prefix replace: P506_Divert → P610_Divert (covers _AOI/_Wave/…)
            pat = rf"(?<![A-Za-z0-9_]){re.escape(slot)}_Divert"
            repl = f"{host_tok}_Divert"
            program_xml = re.sub(pat, repl, program_xml)
            tags = [re.sub(pat, repl, t) for t in tags]
            program_local_tags = [re.sub(pat, repl, t) for t in program_local_tags]

    # 3a3) Prefix-remap mapped tracking/encoder slot families onto proven conveyors.
    #      Example: P504_Conv_Track → P606_Conv_Track when tracking[0]=P606.
    mapped_slots = _mapped_template_slots(sorter)
    if mapped_slots:
        program_xml = _apply_mapped_slot_families(program_xml, mapped_slots)
        tags = [_apply_mapped_slot_families(t, mapped_slots) for t in tags]
        program_local_tags = [
            _apply_mapped_slot_families(t, mapped_slots) for t in program_local_tags
        ]

    # 3a4) PRUNE unmapped template slots at instantiation — do NOT remap them to
    #      divert_host. No SorterModel row ⇒ that placeholder does not exist.
    unmapped_slots = _unmapped_template_slots(sorter)
    pruned_tag_count = 0
    nop_rung_count = 0
    scrubbed_refs = 0
    if unmapped_slots:
        before_n = len(tags) + len(program_local_tags)
        tags = _drop_tag_blocks_for_slots(tags, unmapped_slots)
        program_local_tags = _drop_tag_blocks_for_slots(program_local_tags, unmapped_slots)
        pruned_tag_count = before_n - (len(tags) + len(program_local_tags))
        program_xml = strip_program_tags_by_slot_prefix(program_xml, unmapped_slots)
        program_xml, nop_rung_count = _nop_rungs_referencing_slots(
            program_xml, unmapped_slots
        )
        # Scrub leftover string literals inside Decorated/L5K payloads and any
        # residual operands so unmapped template identities cannot survive as
        # embedded equipment names inside kept tags.
        program_xml, n1 = _scrub_unmapped_slot_tokens(program_xml, unmapped_slots)
        tags = [_scrub_unmapped_slot_tokens(t, unmapped_slots)[0] for t in tags]
        program_local_tags = [
            _scrub_unmapped_slot_tokens(t, unmapped_slots)[0] for t in program_local_tags
        ]
        scrubbed_refs = n1

    # 3b) Shared BOOL roles (e.g. *_Sorter_At_Speed): oracle proves controller scope.
    # Promote program-local declarations → controller tags; strip from program Tags
    # so Studio/preflight do not see Duplicate tag (controller + program).
    from fortna_plc_symbol_registry import (
        is_controller_owned_shared_tag,
        strip_program_tags,
    )

    promote_names: set[str] = set()
    for block in list(program_local_tags):
        nm_m = re.search(r'Tag Name="([^"]+)"', block)
        if not nm_m:
            continue
        tname = nm_m.group(1)
        if is_controller_owned_shared_tag(tname):
            promote_names.add(tname)
            if not any(f'Tag Name="{tname}"' in t for t in tags):
                tags.append(block)
    if promote_names:
        program_xml = strip_program_tags(program_xml, promote_names)

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

    # 7) Controller-scope registry: same name + same dtype → one declaration.
    # Renames can map multiple pack slots onto one model identity (ENC504, P504_Conv).
    from fortna_plc_symbol_registry import PlcSymbolRegistry

    reg = PlcSymbolRegistry()
    deduped: list[str] = []
    reused = 0
    for block in tags:
        res = reg.register(
            scope="controller",
            owner="Sorter_Track",
            source_model="sorter_pack",
            semantic_role="pack_controller_tag",
            block=block,
        )
        if res.get("action") == "declare":
            deduped.append(block)
        elif res.get("action") == "reuse":
            reused += 1
        elif res.get("action") == "fatal_collision":
            # Keep first declaration; record collision in report (do not mute)
            pass
    tags = deduped

    # Rewrite Track_Divert_UDT / Area_UDT Decorated from datatype (library + pack defs).
    # Values preserved from existing Decorated; Decorated must be valid alone.
    try:
        from fortna_l5x_structured_data import (
            parse_datatypes,
            rewrite_tag_decorated_from_datatype,
            UnsupportedStructuredDataError,
            DEFAULT_REWRITE_STRUCTURED_TYPES,
        )

        defs = parse_datatypes((library_text or "") + "\n" + (dt_xml or ""))
        rewritten: list[str] = []
        for block in tags:
            dm = re.search(r'\bDataType="([^"]+)"', block)
            dt = dm.group(1) if dm else ""
            if dt in DEFAULT_REWRITE_STRUCTURED_TYPES and dt in defs:
                try:
                    # Track/Area drop drifted L5K; Comm_UDT / scanner keep L5K.
                    strip = dt in ("Track_Divert_UDT", "Area_UDT")
                    rewritten.append(
                        rewrite_tag_decorated_from_datatype(
                            block, defs, dt_name=dt, strip_l5k=strip
                        )
                    )
                    continue
                except UnsupportedStructuredDataError:
                    pass
            rewritten.append(block)
        tags = rewritten
    except Exception:
        pass

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
        "mapped_template_slots": dict(mapped_slots),
        "unmapped_template_slots": list(unmapped_slots),
        "pruned_unmapped_tag_blocks": pruned_tag_count,
        "nop_rungs_unmapped_slots": nop_rung_count,
        "scrubbed_unmapped_token_refs": scrubbed_refs,
        "induct": (sorter.get("induct_conveyor") or ""),
        "tracking_count": int(sorter.get("tracking_count") or 0),
        "tag_count": len(tags),
        "wave_aoi_merged": bool(wave_extra),
        "promoted_shared_controller_tags": sorted(promote_names),
        "controller_tag_reused": reused,
        "controller_tag_collisions": reg.report().get("fatal") or [],
        "tag_ownership": (
            "Context tags + promoted *_Sorter_At_Speed → controller; "
            "program Tags no longer duplicate those names; "
            "same-name same-dtype renames reuse one declaration; "
            "unmapped pack-template slots pruned (never remapped to divert_host)"
        ),
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
    return f'<Line Number="{n}"><![CDATA[{text}]]></Line>'


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
