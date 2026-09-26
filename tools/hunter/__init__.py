"""HUNTER — read-only PDF engineering-print evidence extractor.

Hunter READS PDF prints, EXTRACTS device/electrical evidence, PRESERVES
provenance, IDENTIFIES ambiguity and PRODUCES structured evidence.

Hunter is an evidence collector, NOT an engineering authority:
  * it never modifies Site Forge engineering state;
  * it never creates Areas, Safety zones, PLC code or I/O assignments;
  * it never parses RUN archives, never reconciles print vs RUN;
  * it has no LLM / network dependency and performs no OCR by default.

If a print does not prove a fact, REVIEW_REQUIRED beats a guess.
"""
from __future__ import annotations

HUNTER_VERSION = "0.1.0"
EXTRACTOR_VERSION = f"hunter-{HUNTER_VERSION}"

# The ONLY states Hunter may emit.  ENGINEER_ASSIGNED (or any other
# authority state) is deliberately absent: Hunter is not an authority.
ALLOWED_STATES = ("PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN")

__all__ = ["HUNTER_VERSION", "EXTRACTOR_VERSION", "ALLOWED_STATES"]
