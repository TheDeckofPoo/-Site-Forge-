#!/usr/bin/env python3
"""Score virgin candidates for simplicity + I/O presence."""
from __future__ import annotations

import re
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

CANDS = [
    "20260624-1641-OReillyindy-ORINDYAC3-RUN.tar.gz",
    "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz",
    "20260813-1428-MSCATL-MSCATL_CP1-RUN.tar.gz",
    "20251016-0933-OReillyGreensboro-ORNCCP4-RUN.tar.gz",
    "20260624-1641-OReillyindy-ORINDYAC6-RUN.tar.gz",
    "20251016-0933-OReillyGreensboro-ORNCCP5-RUN.tar.gz",
    "20260803-0815-OReillyDC27-ORDENCP4-RUN.tar.gz",
]
INBOX = Path("workspace/inbox")


def main() -> None:
    for name in CANDS:
        p = INBOX / name
        if not p.is_file():
            print(f"MISSING {name}")
            continue
        with tarfile.open(p, "r:gz") as tf:
            members = tf.getnames()
            eip_hits = [
                m
                for m in members
                if re.search(r"(EIP|ConfigIO|IOMap|DeviceNet)", m, re.I)
            ][:8]
            conv = next(
                (
                    n
                    for n in members
                    if n.replace("\\", "/").endswith("Conveyor.asc")
                ),
                None,
            )
            cfg = next((n for n in members if n.endswith("project.cfg")), None)
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                for need in (conv, cfg):
                    if need:
                        tf.extract(need, td_path)
                cfg_m = ""
                for cp in td_path.rglob("project.cfg"):
                    t = cp.read_text(encoding="utf-8", errors="replace")
                    mm = re.search(r"MACHINENAME\s*=\s*(\S+)", t, re.I)
                    if mm:
                        cfg_m = mm.group(1)
                owned = 0
                total = 0
                types: Counter[str] = Counter()
                for cv in td_path.rglob("Conveyor.asc"):
                    lines = cv.read_text(encoding="utf-8", errors="replace").splitlines()
                    hdr = [c.strip('"') for c in lines[0].strip('"').split("~")]
                    oi = hdr.index("Machine_Name") if "Machine_Name" in hdr else None
                    ti = None
                    for key in ("Type", "Conveyor_Type", "Conv_Type"):
                        if key in hdr:
                            ti = hdr.index(key)
                            break
                    for ln in lines[1:]:
                        parts = ln.split("~")
                        total += 1
                        own = (
                            parts[oi].strip()
                            if oi is not None and oi < len(parts)
                            else ""
                        )
                        if own.upper() == cfg_m.upper():
                            owned += 1
                            if ti is not None and ti < len(parts):
                                types[parts[ti].strip() or "?"] += 1
        print(f"=== {name}")
        print(f"  cfg={cfg_m} owned={owned}/{total} eip_files={len(eip_hits)}")
        print(f"  types_top={types.most_common(8)}")
        print(f"  eip_sample={eip_hits[:4]}")


if __name__ == "__main__":
    main()
