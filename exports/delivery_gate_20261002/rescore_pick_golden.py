"""Re-score MSCRENOPICK golden gate against existing L5X (no rebuild)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_pick_golden_gate import core_routine_completeness  # noqa: E402

OUT = Path(__file__).resolve().parent
summary_path = OUT / "pick_golden_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8"))
l5x = Path(summary["l5x"])
issues_path = Path(summary.get("build_issues_path") or "")
issues = {}
if issues_path.is_file():
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
elif (OUT.parent / "current" / "MSCRENOPICK_BUILD_ISSUES.json").is_file():
    issues = json.loads(
        (OUT.parent / "current" / "MSCRENOPICK_BUILD_ISSUES.json").read_text(encoding="utf-8")
    )

core = core_routine_completeness(l5x, issues)
summary["gates"]["Core_routine_completeness"] = {
    "pass": core["pass"],
    "unexplained_count": core["unexplained_count"],
    "unexplained": core["unexplained"],
    "empty_or_nop_core_routines": core["empty_or_nop_core_routines"],
}
summary["MSCRENOPICK"]["Core_routine_completeness"] = "PASS" if core["pass"] else "FAIL"
summary["golden_pass"] = all(
    summary["MSCRENOPICK"][k] in ("PASS", "YES")
    for k in (
        "I/O",
        "Transportation",
        "Safety",
        "ES_Main_Routine_populated",
        "Safe_Logic_populated",
        "Safe_PI_populated",
        "Core_routine_completeness",
        "BUILD_ISSUES_explanations",
    )
)
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("GOLDEN", summary["golden_pass"])
print(json.dumps(summary["MSCRENOPICK"], indent=2))
print(json.dumps(summary["gates"]["Core_routine_completeness"], indent=2))
