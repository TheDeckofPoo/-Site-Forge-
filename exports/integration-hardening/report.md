# Integration Hardening Report

Generated: `2026-09-12T22:05:39.571576+00:00`

## Area
{
  "inferred_high_confidence": 0,
  "suggested": 17,
  "engineer_required": 1,
  "counts": {
    "CONFIRMED": 0,
    "HIGH_CONFIDENCE": 0,
    "CANDIDATE": 16,
    "ENGINEER_REQUIRED": 1,
    "suggested": 17
  }
}

## E-stop
{
  "devices": 90,
  "circuits": 0,
  "zones": 1,
  "memberships_proven": 0,
  "memberships_engineer_required": 1
}

## Sorter leaves
{
  "capabilities_modeled": 8,
  "capabilities_newly_generatable": 4,
  "capabilities_generated": 4,
  "generated_names": [
    "encoder_speed",
    "induct_detection",
    "reason_code",
    "scanner_association"
  ],
  "remaining_unsupported": [
    "destination_response",
    "divert_confirmation",
    "divert_rate_limiting",
    "divert_trigger",
    "recirculation",
    "track_offset"
  ],
  "synthetic_leak_ok": true
}

## WCS
{
  "modeled": [
    "connection_transport",
    "event_reporting",
    "inbound_parsing",
    "outbound_fifo",
    "route_request"
  ],
  "generatable": [],
  "unsupported": [
    "divert_confirmation",
    "heartbeat",
    "route_response"
  ]
}

## UI subsystem status
{
  "ORNCCP5": {
    "Transport": "READY",
    "Safety": "CONFIGURATION REQUIRED",
    "Sawtooth": "N/A",
    "Sorter": "PARTIAL GENERATION",
    "WCS": "GENERATION NOT SUPPORTED"
  }
}

## Studio precheck
{
  "CP2": {
    "ok": true,
    "errors": 0
  },
  "CP4": {
    "ok": true,
    "errors": 0
  },
  "CP5": {
    "ok": true,
    "errors": 0
  }
}

Studio pack: `C:\dev\worktree\FortnaPlus\exports\studio-validation`

Ready for Studio manual test: **YES**
Ready for main merge: **NO**
