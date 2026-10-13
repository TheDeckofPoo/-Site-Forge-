# Engineer I/O Confirmations — Scope, Fingerprint, Migration

## Identity (P0)

An engineer confirmation **never** applies merely because the device name matches.

Durable key:

```
site | controller | canonical device name
```

Example: `MSCRENO|MSCRENOPICK|ESPB22`

Also persisted: **evidence fingerprint** containing, where available:

- RUN hash
- raw word / bit
- parsed bit
- active-controller Configio evidence
- endpoint / module evidence
- evidence class / ownership

## Load rule

A confirmation applies only when **all** of:

1. site matches
2. controller matches
3. canonical device matches
4. evidence fingerprint is still compatible with current discovery

Cross-controller confirmations **MUST NOT APPLY**. They may appear read-only as peer history.

## Legacy / unscoped records

Name-only (v1) records:

- are **not** auto-applied
- are migrated into `legacy_confirmations` as `STALE_LEGACY_CONFIRMATION`
- require engineer re-confirm under current site|controller|device scope
- **do not** invent missing site/controller/endpoint/zone by guessing

## Stale evidence

If current evidence changes materially (RUN, word/bit, Configio, endpoint, ownership),
the old confirmation becomes `STALE_EVIDENCE` and is not kept as `ENGINEER_CONFIRMED`.

## inject_missing

Engineer confirmation must **never** inject a missing Safety/device row into a
**different** controller.

Same-controller missing records may only be surfaced as `REVIEW_REQUIRED` unless
current evidence independently proves them (e.g. endpoint present).

## Git / workspace policy

`workspace/engineer_io_confirmations.json` is **runtime-local** and **gitignored**.

Production/runtime engineer decisions must not ship as active seeded decisions
to every worktree / clone.

On first load of a v1 name-keyed store:

1. A backup is written beside the live file:
   `workspace/engineer_io_confirmations.legacy_v1_backup.json`
2. Active `confirmations` become empty (or only already-scoped rows)
3. Historical rows move to `legacy_confirmations` with `STALE_LEGACY_CONFIRMATION`
4. Store `version` becomes `2`

## Re-confirm after migration

Engineers must re-confirm devices under the active controller after migration.
Prior decisions remain visible as stale/legacy peer history for audit.

## Module

`tools/scripts/fortna_io_engineer_confirm.py`
