#!/usr/bin/env python3
"""Score inbox TARs for next ORI-111 virgin proof (owned conveyors + matching machine)."""
from __future__ import annotations

import re
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

INBOX = Path("workspace/inbox")
SKIP = {
    "MSCRENOPICK",
    "MSCRENOSHIP",
    "MSCRENOPACK",
    "TFCP1",
    "ORL_AC3",
    "ORDENCP1",  # proven-empty this mission
}


def score_tar(tar_path: Path) -> dict:
    name = tar_path.name
    # Guess machine from filename
    m = re.search(r"(MSCATL_CP\d+|ORNCCP\d+|ORINDYAC\d+|ORDENCP\d+|ORFPCP\d+|TFCP\d+|ORL_AC\d+)", name, re.I)
    claimed = (m.group(1) if m else "").upper()
    if any(s in name.upper() for s in SKIP) or claimed in {s.upper() for s in SKIP}:
        return {"tar": name, "skip": True, "reason": "fixture_or_proven_empty"}
    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            members = tf.getnames()
            # find Conveyor.asc and project.cfg
            conv_name = next((n for n in members if n.replace("\\", "/").endswith("FORTNA/Conveyor.asc") or n.endswith("Conveyor.asc")), None)
            cfg_name = next((n for n in members if n.replace("\\", "/").endswith("project.cfg")), None)
            if not conv_name:
                return {"tar": name, "claimed": claimed, "skip": True, "reason": "no_conveyor_asc"}
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                for need in (conv_name, cfg_name):
                    if not need:
                        continue
                    tf.extract(need, path=td_path)
                conv = None
                for p in td_path.rglob("Conveyor.asc"):
                    conv = p
                    break
                cfg_machine = ""
                for p in td_path.rglob("project.cfg"):
                    text = p.read_text(encoding="utf-8", errors="replace")
                    mm = re.search(r"MACHINENAME\s*=\s*(\S+)", text, re.I)
                    if mm:
                        cfg_machine = mm.group(1).strip()
                if not conv:
                    return {"tar": name, "claimed": claimed, "skip": True, "reason": "extract_fail"}
                lines = conv.read_text(encoding="utf-8", errors="replace").splitlines()
                hdr = [c.strip('"') for c in lines[0].strip('"').split("~")]
                own_idx = hdr.index("Machine_Name") if "Machine_Name" in hdr else None
                counts: Counter[str] = Counter()
                for ln in lines[1:]:
                    parts = ln.split("~")
                    own = parts[own_idx] if own_idx is not None and own_idx < len(parts) else ""
                    counts[own.strip() or "(empty)"] += 1
                machine = (cfg_machine or claimed).upper()
                owned = counts.get(machine, 0) + counts.get(cfg_machine, 0)
                # also try without case
                for k, v in counts.items():
                    if k.upper() == machine:
                        owned = max(owned, v)
                na = sum(v for k, v in counts.items() if k.upper() in ("N/A", "NA", "(EMPTY)", ""))
                return {
                    "tar": name,
                    "claimed": claimed,
                    "cfg_machine": cfg_machine,
                    "owned_rows": owned,
                    "na_rows": na,
                    "histogram_top": counts.most_common(6),
                    "skip": owned <= 0,
                    "reason": "zero_owned" if owned <= 0 else "candidate",
                    "path": str(tar_path),
                }
    except Exception as ex:  # noqa: BLE001
        return {"tar": name, "skip": True, "reason": f"error:{ex}"}


def main() -> None:
    rows = []
    for p in sorted(INBOX.glob("*.tar.gz")):
        rows.append(score_tar(p))
    cands = [r for r in rows if not r.get("skip") and (r.get("owned_rows") or 0) > 0]
    cands.sort(key=lambda r: (-int(r.get("owned_rows") or 0), r.get("tar") or ""))
    print("CANDIDATES")
    for r in cands[:12]:
        print(f"  {r['owned_rows']:5d} owned  cfg={r.get('cfg_machine')}  {r['tar']}")
    print("SKIPPED sample")
    for r in rows:
        if r.get("skip"):
            print(f"  skip {r.get('reason')} {r.get('tar')}")


if __name__ == "__main__":
    main()
