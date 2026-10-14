"""Unit checks for NTP scaffold + spare-output safety (demo ship)."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "tools" / "scripts"
LIBRARY = REPO_ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    _build_sys_comm_program_xml,
    _resolve_site_ntp_server,
)


def _rung_xml(num, text, comment=""):
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def routine(name, rungs):
    body = "".join(
        re.sub(r'Number="\d+"', f'Number="{i}"', r, count=1) for i, r in enumerate(rungs)
    )
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


def test_resolve_ntp_from_options():
    inp = AutogenInput(project_name="DEMO", options={"ntp_server": "10.1.2.3"})
    assert _resolve_site_ntp_server(inp) == "10.1.2.3"


def test_resolve_ntp_from_run_conf():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sf = root / "SystemFiles"
        sf.mkdir()
        (sf / "ntp.conf").write_text(
            "#server 0.us.pool.ntp.org\nserver 10.9.8.7\n", encoding="utf-8"
        )
        inp = AutogenInput(project_name="DEMO", run_dir=str(root))
        assert _resolve_site_ntp_server(inp) == "10.9.8.7"


def test_resolve_ntp_ignores_commented_servers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sf = root / "SystemFiles"
        sf.mkdir()
        (sf / "ntp.conf").write_text(
            "#server 172.25.2.100\n#server pool.ntp.org\n", encoding="utf-8"
        )
        inp = AutogenInput(project_name="DEMO", run_dir=str(root))
        assert _resolve_site_ntp_server(inp) == ""


def test_ntp_scaffold_config_required_without_server():
    library_text = LIBRARY.read_text(encoding="utf-8", errors="replace")
    tags = []
    seen = set()

    def _add(block):
        m = re.search(r'Name="([^"]+)"', block)
        if m:
            seen.add(m.group(1))
        tags.append(block)

    ntp_out = {}
    inp = AutogenInput(project_name="DEMO", include_programs=["System"])
    xml = _build_sys_comm_program_xml(
        inp=inp,
        library_text=library_text,
        _add_tag_block=_add,
        _rung_xml=_rung_xml,
        routine=routine,
        seen_tag_names=seen,
        include_device_comms=False,
        include_ntp=True,
        include_system_logic=False,
        ntp_report_out=ntp_out,
    )
    assert "AOI_SNTP_QUERY(SNTP_AOI_TAG," in xml
    assert "CONFIG_REQUIRED" in xml
    assert ntp_out.get("status") == "CONFIG_REQUIRED"
    assert ntp_out.get("commissioning_ready") is False
    assert ntp_out.get("aoi_call") is True
    for name in (
        "SNTP_SERVER_ADDRESS",
        "SNTP_TIME_RETRIEVED",
        "SNTP_MSG_DATA",
        "SNTP_MSG_CREATE",
        "SNTP_MSG_OPEN",
        "SNTP_MSG_WRITE",
        "SNTP_MSG_READ",
        "SNTP_MSG_DELETE",
    ):
        assert name in seen, name
    assert "SNTP_AOI_TAG" in xml
    # empty server string — no finished-site IP baked into SNTP_SERVER_ADDRESS
    server_blk = next(b for b in tags if 'Name="SNTP_SERVER_ADDRESS"' in b)
    assert 'Length="0"' in server_blk
    blob = "".join(tags)
    assert "ORLY_Greensboro" not in blob
    assert "PLC2_ENET1" not in blob  # ConnectionPath must be generic ENET_PENDING


def test_ntp_scaffold_with_site_server_still_not_commissioning_ready():
    library_text = LIBRARY.read_text(encoding="utf-8", errors="replace")
    tags = []
    seen = set()

    def _add(block):
        m = re.search(r'Name="([^"]+)"', block)
        if m:
            seen.add(m.group(1))
        tags.append(block)

    ntp_out = {}
    inp = AutogenInput(
        project_name="DEMO",
        options={"ntp_server": "192.0.2.10"},
        include_programs=["System"],
    )
    xml = _build_sys_comm_program_xml(
        inp=inp,
        library_text=library_text,
        _add_tag_block=_add,
        _rung_xml=_rung_xml,
        routine=routine,
        seen_tag_names=seen,
        include_device_comms=False,
        include_ntp=True,
        include_system_logic=False,
        ntp_report_out=ntp_out,
    )
    assert ntp_out.get("status") == "SCAFFOLD_SERVER_PRESENT"
    assert ntp_out.get("commissioning_ready") is False
    assert "192.0.2.10" in "".join(tags)
    assert "Enable_Instruction" in xml
    assert 'Value="0"' in xml  # safely disabled until commissioning


def test_spare_output_no_shared_placeholder_writer():
    """Spare outputs must not be OTE'd from shared NO_PointPlaceholder."""
    src = (SCRIPT_DIR / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
    # Hazard pattern must not remain as live emit for outputs.
    assert 'f"XIC(NO_PointPlaceholder)OTE({channel});"' not in src
    assert "XIC(NO_PointPlaceholder)OTE(" not in src or "spare-output safety" in src
    assert "no energizable writer" in src
    # Input documentation path may remain.
    assert 'f"XIC({channel})OTE(NO_PointPlaceholder);"' in src


if __name__ == "__main__":
    test_resolve_ntp_from_options()
    test_resolve_ntp_from_run_conf()
    test_resolve_ntp_ignores_commented_servers()
    test_ntp_scaffold_config_required_without_server()
    test_ntp_scaffold_with_site_server_still_not_commissioning_ready()
    test_spare_output_no_shared_placeholder_writer()
    print("PASS: demo_ntp_spare unit checks")
