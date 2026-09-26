"""Packet history + derived state files.

Layout under a Switchboard root (default: this package directory):

    config.json                 roles + Night Shift defaults (falls back to package config)
    packets/NNNN-<type>-<id>.json   append-only packet history (the source of truth)
    state/current.json          derived; rebuilt from packets on every post
    state/subsystem_status.json derived
    handoffs/HANDOFF-*.json     derived handoff packets (never inputs)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .engine import Engine
from .validator import validate

PACKAGE_DIR = Path(__file__).resolve().parent
PACKET_RE = re.compile(r"^(\d{4,})-([a-z]+)-(.+)\.json$")
PACKET_SCHEMAS = {"mission": "mission", "result": "result", "defect": "defect", "decision": "decision"}


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def detect_type(packet: Any) -> str | None:
    if not isinstance(packet, dict):
        return None
    t = packet.get("packet_type")
    if t in PACKET_SCHEMAS:
        return t
    if "handoff_id" in packet:
        return "handoff"
    if packet.get("kind") in ("switchboard.current", "switchboard.subsystem_status"):
        return "state"
    return None


def validate_packet(packet: Any, expected: str | None = None) -> tuple[str | None, list[str]]:
    t = detect_type(packet)
    if t is None:
        return None, ["cannot determine packet type (missing/invalid packet_type)"]
    if expected and t != expected:
        return t, [f"expected a {expected} packet, got {t}"]
    return t, validate(packet, PACKET_SCHEMAS.get(t, t))


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


class Store:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else PACKAGE_DIR
        self.packets_dir = self.root / "packets"
        self.state_dir = self.root / "state"
        self.handoffs_dir = self.root / "handoffs"

    # config ------------------------------------------------------------
    def config(self) -> dict:
        p = self.root / "config.json"
        return load_json(p if p.exists() else PACKAGE_DIR / "config.json")

    # history -----------------------------------------------------------
    def packet_files(self) -> list[Path]:
        if not self.packets_dir.exists():
            return []
        files = [p for p in self.packets_dir.iterdir() if PACKET_RE.match(p.name)]
        return sorted(files, key=lambda p: int(PACKET_RE.match(p.name).group(1)))

    def history(self) -> list[tuple[int, str, dict]]:
        return [(int(PACKET_RE.match(p.name).group(1)), p.name, load_json(p)) for p in self.packet_files()]

    def _packet_name(self, seq: int, packet: dict) -> str:
        t = packet["packet_type"]
        ident = {"mission": lambda p: p["mission_id"],
                 "result": lambda p: f"{p['mission_id']}-{p['agent']}",
                 "defect": lambda p: p["ori_id"],
                 "decision": lambda p: p["decision_id"]}[t](packet)
        return f"{seq:04d}-{t}-{_safe(ident)}.json"

    # state ---------------------------------------------------------------
    def build(self) -> tuple[Engine, dict[int, list[dict]]]:
        eng = Engine(self.config())
        per: dict[int, list[dict]] = {}
        for seq, name, packet in self.history():
            t, errs = validate_packet(packet)
            if errs:
                raise ValueError(f"history packet {name} is invalid: {errs}")
            per[seq] = eng.apply(seq, name, packet)
        return eng, per

    def rendered_state(self) -> tuple[str, str]:
        eng, _ = self.build()
        return dumps(eng.current()), dumps(eng.subsystem_status())

    def rebuild(self) -> Engine:
        eng, _ = self.build()
        self._write_state(eng)
        return eng

    def _write_state(self, eng: Engine) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "current.json").write_text(dumps(eng.current()), encoding="utf-8")
        (self.state_dir / "subsystem_status.json").write_text(dumps(eng.subsystem_status()), encoding="utf-8")

    def check(self) -> list[str]:
        """Return names of state files that differ from a fresh rebuild."""
        cur, sub = self.rendered_state()
        diffs = []
        for fname, want in (("current.json", cur), ("subsystem_status.json", sub)):
            p = self.state_dir / fname
            if not p.exists() or p.read_text(encoding="utf-8") != want:
                diffs.append(str(p))
        return diffs

    def load_state(self) -> dict:
        p = self.state_dir / "current.json"
        return load_json(p) if p.exists() else self.rebuild().current()

    def load_subsystems(self) -> dict:
        p = self.state_dir / "subsystem_status.json"
        return load_json(p) if p.exists() else self.rebuild().subsystem_status()

    # posting -------------------------------------------------------------
    def post(self, packet: dict, expected: str | None = None) -> dict:
        """Validate, append to history, rebuild state.

        Returns {"accepted": bool, "stored": path|None, "errors": [...], "flags": [...]}.
        Schema-invalid packets are NOT stored.  Schema-valid packets are always
        stored (even if the engine rejects them) so rejections are auditable and
        reproduced by ``rebuild``.
        """
        t, errs = validate_packet(packet, expected)
        if errs:
            return {"accepted": False, "stored": None, "errors": errs, "flags": [], "type": t}
        files = self.packet_files()
        seq = (int(PACKET_RE.match(files[-1].name).group(1)) + 1) if files else 1
        self.packets_dir.mkdir(parents=True, exist_ok=True)
        path = self.packets_dir / self._packet_name(seq, packet)
        path.write_text(dumps(packet), encoding="utf-8")
        eng, per = self.build()
        self._write_state(eng)
        flags = per.get(seq, [])
        accepted = not any(f["severity"] == "REJECT" for f in flags)
        return {"accepted": accepted, "stored": str(path), "errors": [], "flags": flags, "type": t}
