"""SWITCHBOARD — coordination / handoff data plane for Site Forge missions.

Switchboard normalizes missions and results, tracks ORI (defect) state,
routes work to the next owner, and generates handoff packets and a morning
brief.  It never makes engineering decisions, never writes PLC logic, and
never changes Site Forge compiler behavior.  Stdlib only.
"""

__version__ = "0.1.0"
